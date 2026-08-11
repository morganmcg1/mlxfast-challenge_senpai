import Foundation
import MLX
import Testing
@testable import MLXFastModel

private struct CedarGate1Bank {
    let fusedWeight: MLXArray
    let packedScales: MLXArray
    let routerKeys: MLXArray
}

private struct CedarGate1Arm {
    let label: String
    let microseconds: Double
}

private func cedarRouterOrdinal(_ key: Float) -> UInt32 {
    let bits = key.bitPattern
    let magnitude = bits & 0x7fff_ffff
    if magnitude > 0x7f80_0000 {
        return 0xffff_ffff
    }
    if magnitude == 0 {
        return 0x8000_0000
    }
    return bits & 0x8000_0000 != 0 ? ~bits : bits ^ 0x8000_0000
}

private func cedarRouterKeys(layer: Int) -> MLXArray {
    let ordinals = (0..<LagunaConstants.numExperts).map { expert in
        let rank = (expert &* 73 &+ layer &* 29) & 255
        return cedarRouterOrdinal(-Float(rank + 1) / 257)
    }
    return MLXArray(ordinals, [LagunaConstants.numExperts])
}

private func cedarGate1Outputs(
    input: MLXArray,
    banks: [CedarGate1Bank],
    useTable: Bool
) -> [MLXArray] {
    banks.map { bank in
        cedarGate1LagunaRoutedSwiGLUQMVPackedTop8(
            input,
            fusedWeight: bank.fusedWeight,
            packedScales: bank.packedScales,
            routerKeys: bank.routerKeys,
            useTable: useTable
        )
    }
}

private func cedarMeasureGate1Arm(
    label: String,
    input: MLXArray,
    banks: [CedarGate1Bank]
) -> CedarGate1Arm {
    let outputs = cedarGate1Outputs(input: input, banks: banks, useTable: label == "B")
    let start = DispatchTime.now().uptimeNanoseconds
    eval(outputs)
    let end = DispatchTime.now().uptimeNanoseconds
    return CedarGate1Arm(label: label, microseconds: Double(end - start) / 1_000)
}

private func cedarRunCoolGate(block: Int, order: String) throws {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/bin/bash")
    process.arguments = ["./benchmark.sh", "--local-cool-gate-only"]
    process.currentDirectoryURL = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
    var environment = ProcessInfo.processInfo.environment
    environment["MLXFAST_LOCAL_COOL_GATE_PHASE"] = "cedar-gate1-block-\(block)-\(order)"
    environment["MLXFAST_LOCAL_COOL_GATE_STRICT_TELEMETRY"] = "1"
    environment["MLXFAST_LOCAL_FAN_PROMPT"] = "0"
    process.environment = environment
    try process.run()
    process.waitUntilExit()
    guard process.terminationReason == .exit, process.terminationStatus == 0 else {
        throw NSError(
            domain: "CedarNVFP4CodeAlphabetGate1",
            code: Int(process.terminationStatus),
            userInfo: [NSLocalizedDescriptionKey: "cool gate failed for block \(block)"]
        )
    }
}

private func cedarMean(_ values: [Double]) -> Double {
    values.reduce(0, +) / Double(values.count)
}

private func cedarLower95(_ values: [Double]) -> Double {
    let mean = cedarMean(values)
    let variance = values.map { value in
        let delta = value - mean
        return delta * delta
    }.reduce(0, +) / Double(values.count - 1)
    return mean - 2.069 * sqrt(variance / Double(values.count))
}

@Test
func cedarNVFP4CodeAlphabetGate1() throws {
    let environment = ProcessInfo.processInfo.environment
    guard environment["CEDAR_RUN_NVFP4_GATE1"] == "1" else {
        return
    }

    let weightsPath = environment["MLXFAST_WEIGHTS_PATH"] ?? "weights"
    let config = try LagunaConfig.load(from: weightsPath)
    let loader = try LagunaWeightLoader(weightsPath: weightsPath)
    let weightCache = LagunaRuntimeWeightCache(loader: loader, config: config)
    let model = try weightCache.requireLibraryModel()

    let sparseLayers = model.model.layers.compactMap { layer in
        layer.mlp as? LagunaRuntimeSparseMoEBlock
    }
    try #require(sparseLayers.count == 39)
    let banks = try sparseLayers.enumerated().map { layer, sparse in
        CedarGate1Bank(
            fusedWeight: try #require(sparse._fusedRoutedGateUpWeight),
            packedScales: try #require(sparse._packedRoutedGateUpBank),
            routerKeys: cedarRouterKeys(layer: layer)
        )
    }

    let axis = MLXArray(0..<LagunaConstants.hiddenSize).asType(.float32)
    let input = (sin(axis * 0.013) * 0.125)
        .asType(.bfloat16)
        .reshaped([1, 1, LagunaConstants.hiddenSize])
    eval([input] + banks.map(\.routerKeys))

    let control = cedarGate1Outputs(input: input, banks: banks, useTable: false)
    let candidate = cedarGate1Outputs(input: input, banks: banks, useTable: true)
    eval(control + candidate)
    for layer in banks.indices {
        let controlValues = control[layer].asArray(Float.self)
        let candidateValues = candidate[layer].asArray(Float.self)
        #expect(
            candidateValues == controlValues,
            "table/control mismatch in sparse layer \(layer + 1)"
        )
    }

    for _ in 0..<2 {
        eval(cedarGate1Outputs(input: input, banks: banks, useTable: false))
        eval(cedarGate1Outputs(input: input, banks: banks, useTable: true))
    }

    var csv = "block,order,position,label,microseconds,savings_microseconds\n"
    var combinedSavings: [Double] = []
    var abbaSavings: [Double] = []
    var baabSavings: [Double] = []

    for block in 0..<12 {
        let order = block.isMultiple(of: 2) ? "ABBA" : "BAAB"
        try cedarRunCoolGate(block: block, order: order)
        let labels = order.map { String($0) }
        let arms = labels.map { label in
            cedarMeasureGate1Arm(label: label, input: input, banks: banks)
        }
        let pairs: [(CedarGate1Arm, CedarGate1Arm)]
        if order == "ABBA" {
            pairs = [(arms[0], arms[1]), (arms[3], arms[2])]
        } else {
            pairs = [(arms[1], arms[0]), (arms[2], arms[3])]
        }
        let savings = pairs.map { controlArm, candidateArm in
            controlArm.microseconds - candidateArm.microseconds
        }
        combinedSavings.append(contentsOf: savings)
        if order == "ABBA" {
            abbaSavings.append(contentsOf: savings)
        } else {
            baabSavings.append(contentsOf: savings)
        }
        let pairedSavings = [savings[0], savings[0], savings[1], savings[1]]
        for position in arms.indices {
            csv += "\(block),\(order),\(position),\(arms[position].label),"
                + "\(arms[position].microseconds),\(pairedSavings[position])\n"
        }
        print(
            "cedar_gate1 block=\(block) order=\(order) "
                + "arms_us=\(arms.map(\.microseconds)) savings_us=\(savings)"
        )
    }

    let point = cedarMean(combinedSavings)
    let lower95 = cedarLower95(combinedSavings)
    let abbaMean = cedarMean(abbaSavings)
    let baabMean = cedarMean(baabSavings)
    let summary = "point_savings_us=\(point) lower95_savings_us=\(lower95) "
        + "abba_mean_us=\(abbaMean) baab_mean_us=\(baabMean) "
        + "paired_samples=\(combinedSavings.count) sparse_invocations=\(banks.count)"
    print("cedar_gate1_summary \(summary)")
    try csv.write(
        to: URL(fileURLWithPath: "/tmp/cedar_nvfp4_gate1.csv"),
        atomically: true,
        encoding: .utf8
    )
    try summary.write(
        to: URL(fileURLWithPath: "/tmp/cedar_nvfp4_gate1_summary.txt"),
        atomically: true,
        encoding: .utf8
    )

    #expect(combinedSavings.count == 24)
    #expect(abbaSavings.count == 12)
    #expect(baabSavings.count == 12)
    #expect(point > 35, "point savings did not exceed 35 us/token: \(point)")
    #expect(lower95 > 24.543, "lower 95% CI did not exceed 24.543 us/token: \(lower95)")
    #expect(abbaMean > 0, "ABBA estimate was not positive: \(abbaMean)")
    #expect(baabMean > 0, "BAAB estimate was not positive: \(baabMean)")
}
