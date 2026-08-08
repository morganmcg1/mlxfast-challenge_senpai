import Foundation
import MLX
import Testing
@testable import MLXFastModel

private struct RouterSharedFixture {
    let residual: MLXArray
    let branch: MLXArray
    let normWeight: MLXArray
    let routerWeight: MLXArray
    let fusedWeight: MLXArray
    let fusedScales: MLXArray
}

private func loadRouterSharedFixture() throws -> RouterSharedFixture {
    let weightsPath = ProcessInfo.processInfo.environment[
        "MLXFAST_LAGUNA_FUSION_WEIGHTS_PATH"
    ] ?? "weights"
    let store = try DenseTensorStore(weightsPath: weightsPath)
    let bridge = MLXArrayTensorBridge()

    func array(_ name: String) throws -> MLXArray {
        try bridge.makeArray(from: store.materializedTensor(named: name))
    }

    let gateName = LagunaWeightNames.mlp(1, "shared_expert.gate_proj.weight")
    let upName = LagunaWeightNames.mlp(1, "shared_expert.up_proj.weight")
    return try RouterSharedFixture(
        residual: array(LagunaWeightNames.layer(1, "input_layernorm.weight"))
            .reshaped([1, 1, LagunaConstants.hiddenSize]),
        branch: array(LagunaWeightNames.layer(1, "post_attention_layernorm.weight"))
            .reshaped([1, 1, LagunaConstants.hiddenSize]),
        normWeight: array(LagunaWeightNames.layer(2, "input_layernorm.weight")),
        routerWeight: array(LagunaWeightNames.mlp(1, "gate.weight")),
        fusedWeight: concatenated([array(gateName), array(upName)], axis: 0),
        fusedScales: concatenated([
            array(gateName.replacingOccurrences(of: ".weight", with: ".scales")),
            array(upName.replacingOccurrences(of: ".weight", with: ".scales")),
        ], axis: 0)
    )
}

private func deterministicBF16(seed: UInt64, extrema: Bool) -> MLXArray {
    var state = seed
    var values = [Float]()
    values.reserveCapacity(LagunaConstants.hiddenSize)
    for index in 0..<LagunaConstants.hiddenSize {
        state = state &* 6_364_136_223_846_793_005 &+ 1_442_695_040_888_963_407
        let unit = Float((state >> 40) & 0xFFFFFF) / Float(0xFFFFFF)
        let sign: Float = index.isMultiple(of: 2) ? 1 : -1
        values.append(sign * (unit * 8 - 4))
    }
    values[0] = 0
    values[1] = -0.0
    values[2] = Float.leastNormalMagnitude
    values[3] = -Float.leastNormalMagnitude
    if extrema {
        values[4] = 32_768
        values[5] = -32_768
        values[6] = 128
        values[7] = -128
    }
    return MLXArray(values, [1, 1, LagunaConstants.hiddenSize]).asType(.bfloat16)
}

private func rawBF16(_ array: MLXArray) -> [UInt16] {
    array.view(dtype: .uint16).asArray(UInt16.self)
}

private func differingElements(_ lhs: MLXArray, _ rhs: MLXArray) -> Int {
    zip(rawBF16(lhs), rawBF16(rhs)).reduce(into: 0) { count, pair in
        count += pair.0 == pair.1 ? 0 : 1
    }
}

private func controlOutputs(
    residual: MLXArray, branch: MLXArray, fixture: RouterSharedFixture
) -> [MLXArray] {
    let control = lagunaResidualRMSNormRouter(
        residual: residual,
        branch: branch,
        weight: fixture.normWeight,
        routerWeight: fixture.routerWeight
    )
    let shared = lagunaSharedSwiGLUQMV(
        control.normalized,
        fusedWeight: fixture.fusedWeight,
        fusedScales: fixture.fusedScales
    )
    return [control.summed, control.normalized, control.routerLogits, shared]
}

private func fusedOutputs(
    residual: MLXArray, branch: MLXArray, fixture: RouterSharedFixture
) -> [MLXArray] {
    let fused = lagunaResidualRMSNormRouterSharedQMV(
        residual: residual,
        branch: branch,
        weight: fixture.normWeight,
        routerWeight: fixture.routerWeight,
        fusedWeight: fixture.fusedWeight,
        fusedScales: fixture.fusedScales
    )
    return [fused.summed, fused.normalized, fused.routerLogits, fused.sharedActivation]
}

private func elapsedSeconds(repetitions: Int, _ body: () -> [MLXArray]) -> Double {
    let start = DispatchTime.now().uptimeNanoseconds
    for _ in 0..<repetitions {
        eval(body())
    }
    return Double(DispatchTime.now().uptimeNanoseconds - start) / 1_000_000_000
}

@Test
func lagunaRouterSharedFusionMatchesControlAndMeasuresProducerWhenEnabled() throws {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_ROUTER_SHARED_FUSION_TEST"] == "1"
    else {
        return
    }

    let fixture = try loadRouterSharedFixture()
    let cases: [(String, MLXArray, MLXArray)] = [
        ("checkpoint", fixture.residual, fixture.branch),
        ("random_signed_zero", deterministicBF16(seed: 0xC0FFEE, extrema: false),
         deterministicBF16(seed: 0xBAD5EED, extrema: false)),
        ("random_extrema", deterministicBF16(seed: 0x12345678, extrema: true),
         deterministicBF16(seed: 0x87654321, extrema: true)),
    ]
    let labels = ["summed", "normalized", "router", "shared"]

    for (caseName, residual, branch) in cases {
        let control = controlOutputs(residual: residual, branch: branch, fixture: fixture)
        let fused = fusedOutputs(residual: residual, branch: branch, fixture: fixture)
        eval(control)
        eval(fused)
        let differences = zip(control, fused).map(differingElements)
        print("ROUTER_SHARED_CORRECTNESS case=\(caseName) diffs=\(differences)")
        for index in control.indices {
            #expect(
                differences[index] == 0,
                "\(caseName) \(labels[index]) differs in \(differences[index]) BF16 elements"
            )
        }
    }

    for _ in 0..<12 {
        eval(controlOutputs(
            residual: fixture.residual, branch: fixture.branch, fixture: fixture))
        eval(fusedOutputs(
            residual: fixture.residual, branch: fixture.branch, fixture: fixture))
    }

    let repetitions = 100
    var controlFirstControl = 0.0
    var controlFirstFused = 0.0
    var fusedFirstControl = 0.0
    var fusedFirstFused = 0.0
    for pair in 0..<6 {
        let controlFirst = pair.isMultiple(of: 2)
        let controlSeconds: Double
        let fusedSeconds: Double
        if controlFirst {
            controlSeconds = elapsedSeconds(repetitions: repetitions) {
                controlOutputs(
                    residual: fixture.residual, branch: fixture.branch, fixture: fixture)
            }
            fusedSeconds = elapsedSeconds(repetitions: repetitions) {
                fusedOutputs(
                    residual: fixture.residual, branch: fixture.branch, fixture: fixture)
            }
            controlFirstControl += controlSeconds
            controlFirstFused += fusedSeconds
        } else {
            fusedSeconds = elapsedSeconds(repetitions: repetitions) {
                fusedOutputs(
                    residual: fixture.residual, branch: fixture.branch, fixture: fixture)
            }
            controlSeconds = elapsedSeconds(repetitions: repetitions) {
                controlOutputs(
                    residual: fixture.residual, branch: fixture.branch, fixture: fixture)
            }
            fusedFirstControl += controlSeconds
            fusedFirstFused += fusedSeconds
        }
        print(
            "ROUTER_SHARED_PRODUCER pair=\(pair + 1) order=\(controlFirst ? "AB" : "BA") "
                + "repetitions=\(repetitions) control_s=\(controlSeconds) "
                + "fused_s=\(fusedSeconds) speedup=\(controlSeconds / fusedSeconds)"
        )
    }
    print(
        "ROUTER_SHARED_PRODUCER_SUMMARY order=AB speedup="
            + "\(controlFirstControl / controlFirstFused)"
    )
    print(
        "ROUTER_SHARED_PRODUCER_SUMMARY order=BA speedup="
            + "\(fusedFirstControl / fusedFirstFused)"
    )
}
