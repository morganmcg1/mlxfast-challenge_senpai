import Foundation
import MLX
import MLXLMCommon
import MLXNN
@testable import MLXFastModel
import Testing

@Test
func lagunaSharedGateUpResearchHarness() throws {
    let environment = ProcessInfo.processInfo.environment
    guard environment["MLXFAST_RUN_SHARED_GATE_UP_RESEARCH"] == "1" else {
        return
    }

    let weightsPath = try #require(environment["MLXFAST_SHARED_GATE_UP_WEIGHTS_PATH"])
    let iterations = Int(environment["MLXFAST_SHARED_GATE_UP_ITERATIONS"] ?? "1000") ?? 1000
    let warmupIterations =
        Int(environment["MLXFAST_SHARED_GATE_UP_WARMUP_ITERATIONS"] ?? "10") ?? 10
    let expectsPairedRows = environment["MLXFAST_EXPECT_PAIRED_SHARED_BANK"] == "1"
    let config = try LagunaConfig.load(from: weightsPath)
    let loader = try LagunaWeightLoader(weightsPath: weightsPath)
    let weightCache = LagunaRuntimeWeightCache(loader: loader, config: config)
    let model = try weightCache.requireLibraryModel()
    let sharedExperts = model.model.layers.compactMap {
        ($0.mlp as? LagunaRuntimeSparseMoEBlock)?.sharedExpert
    }
    #expect(sharedExperts.count == 39)

    var mappingRowsChecked = 0
    var positiveControlPassed = false
    for (layerOffset, sharedExpert) in sharedExperts.enumerated() {
        let gate = try #require(sharedExpert.gateProj as? QuantizedLinear)
        let up = try #require(sharedExpert.upProj as? QuantizedLinear)
        let fusedWeight = try #require(sharedExpert._fusedGateUpWeight)
        let fusedScales = try #require(sharedExpert._fusedGateUpScales)
        let gateWeightValues = gate.weight.asArray(UInt32.self)
        let upWeightValues = up.weight.asArray(UInt32.self)
        let gateScaleValues = gate.scales.asArray(UInt8.self)
        let upScaleValues = up.scales.asArray(UInt8.self)
        let fusedWeightValues = fusedWeight.asArray(UInt32.self)
        let fusedScaleValues = fusedScales.asArray(UInt8.self)
        let weightMappingPasses = sharedGateUpMappingMatches(
            gate: gateWeightValues,
            up: upWeightValues,
            fused: fusedWeightValues,
            rows: gate.weight.dim(0),
            depth: gate.weight.dim(1),
            paired: expectsPairedRows
        )
        let scaleMappingPasses = sharedGateUpMappingMatches(
            gate: gateScaleValues,
            up: upScaleValues,
            fused: fusedScaleValues,
            rows: gate.scales.dim(0),
            depth: gate.scales.dim(1),
            paired: expectsPairedRows
        )
        #expect(weightMappingPasses)
        #expect(scaleMappingPasses)
        mappingRowsChecked += 2 * gate.weight.dim(0)

        if layerOffset == 0 {
            var corrupted = fusedWeightValues
            corrupted[0] ^= 1
            #expect(
                !sharedGateUpMappingMatches(
                    gate: gateWeightValues,
                    up: upWeightValues,
                    fused: corrupted,
                    rows: gate.weight.dim(0),
                    depth: gate.weight.dim(1),
                    paired: expectsPairedRows
                )
            )
            #expect(
                sharedGateUpMappingMatches(
                    gate: gateWeightValues,
                    up: upWeightValues,
                    fused: fusedWeightValues,
                    rows: gate.weight.dim(0),
                    depth: gate.weight.dim(1),
                    paired: expectsPairedRows
                )
            )
            positiveControlPassed = true
        }
    }
    #expect(mappingRowsChecked == 39 * 1024)
    #expect(positiveControlPassed)

    let inputValues = (0..<LagunaConstants.hiddenSize).map {
        Float(($0 % 31) - 15) / 16
    }
    let input = MLXArray(inputValues, [1, 1, LagunaConstants.hiddenSize]).asType(.bfloat16)
    var exactLayers = 0
    for sharedExpert in sharedExperts {
        let gate = try #require(sharedExpert.gateProj as? QuantizedLinear)
        let up = try #require(sharedExpert.upProj as? QuantizedLinear)
        let fusedWeight = try #require(sharedExpert._fusedGateUpWeight)
        let fusedScales = try #require(sharedExpert._fusedGateUpScales)
        let actual = lagunaSharedSwiGLUQMV(
            input,
            fusedWeight: fusedWeight,
            fusedScales: fusedScales
        )
        let reference = compiledSiluProduct(gate(input), up(input))
        eval(actual, reference)
        #expect(
            actual.view(dtype: .uint16).asArray(UInt16.self)
                == reference.view(dtype: .uint16).asArray(UInt16.self)
        )
        exactLayers += 1
    }
    #expect(exactLayers == 39)
    try runLocalCoolGate()

    func evaluateSharedGateUp() {
        let outputs = sharedExperts.map { sharedExpert in
            lagunaSharedSwiGLUQMV(
                input,
                fusedWeight: sharedExpert._fusedGateUpWeight!,
                fusedScales: sharedExpert._fusedGateUpScales!
            )
        }
        eval(outputs)
    }

    for _ in 0..<warmupIterations {
        evaluateSharedGateUp()
    }
    let start = DispatchTime.now().uptimeNanoseconds
    for _ in 0..<iterations {
        evaluateSharedGateUp()
    }
    let end = DispatchTime.now().uptimeNanoseconds
    let elapsedSeconds = Double(end - start) / 1_000_000_000
    let launches = iterations * sharedExperts.count
    let result = SharedGateUpResearchResult(
        layout: expectsPairedRows ? "paired" : "halves",
        rowsPerSIMD: environment["DARKBLOOM_SHARED_QMV_R1"] == "0" ? 2 : 1,
        sparseLayers: sharedExperts.count,
        launches: launches,
        iterations: iterations,
        warmupIterations: warmupIterations,
        elapsedSeconds: elapsedSeconds,
        secondsPerLaunch: elapsedSeconds / Double(launches),
        secondsPerStep: elapsedSeconds / Double(iterations),
        mappingRowsChecked: mappingRowsChecked,
        positiveControlPassed: positiveControlPassed,
        exactLayers: exactLayers,
        activeMemoryBytes: Memory.activeMemory
    )
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    print("SHARED_GATE_UP_RESEARCH_RESULT " + String(decoding: try encoder.encode(result), as: UTF8.self))
}

private func runLocalCoolGate() throws {
    let process = Process()
    process.executableURL = URL(
        fileURLWithPath: FileManager.default.currentDirectoryPath
    ).appendingPathComponent("benchmark.sh")
    process.arguments = ["--local-cool-gate-only"]
    try process.run()
    process.waitUntilExit()
    try #require(process.terminationStatus == 0)
}

private func sharedGateUpMappingMatches<Element: Equatable>(
    gate: [Element],
    up: [Element],
    fused: [Element],
    rows: Int,
    depth: Int,
    paired: Bool
) -> Bool {
    guard gate.count == rows * depth,
        up.count == rows * depth,
        fused.count == 2 * rows * depth
    else {
        return false
    }
    for row in 0..<rows {
        let gatePhysicalRow = paired ? 2 * row : row
        let upPhysicalRow = paired ? 2 * row + 1 : rows + row
        for column in 0..<depth {
            let source = row * depth + column
            if fused[gatePhysicalRow * depth + column] != gate[source]
                || fused[upPhysicalRow * depth + column] != up[source]
            {
                return false
            }
        }
    }
    return true
}

private struct SharedGateUpResearchResult: Encodable {
    let layout: String
    let rowsPerSIMD: Int
    let sparseLayers: Int
    let launches: Int
    let iterations: Int
    let warmupIterations: Int
    let elapsedSeconds: Double
    let secondsPerLaunch: Double
    let secondsPerStep: Double
    let mappingRowsChecked: Int
    let positiveControlPassed: Bool
    let exactLayers: Int
    let activeMemoryBytes: Int

    enum CodingKeys: String, CodingKey {
        case layout
        case rowsPerSIMD = "rows_per_simd"
        case sparseLayers = "sparse_layers"
        case launches
        case iterations
        case warmupIterations = "warmup_iterations"
        case elapsedSeconds = "elapsed_seconds"
        case secondsPerLaunch = "seconds_per_launch"
        case secondsPerStep = "seconds_per_step"
        case mappingRowsChecked = "mapping_rows_checked"
        case positiveControlPassed = "positive_control_passed"
        case exactLayers = "exact_layers"
        case activeMemoryBytes = "active_memory_bytes"
    }
}
