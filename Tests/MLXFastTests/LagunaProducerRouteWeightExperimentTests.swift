import Foundation
import MLX
import Testing
@testable import MLXFastModel

@Test
func fusedRoutedSharedDownProducerWeightExperiment() {
    guard let mode = ProcessInfo.processInfo.environment[
        "MLXFAST_FUSED_DOWN_EXPERIMENT_MODE"
    ] else {
        return
    }

    let inputs = makeFusedDownExperimentInputs()
    eval(inputs.materializedArrays)

    switch mode {
    case "correctness":
        verifyFusedDownExactness(inputs)
    case "timing-ab":
        measureFusedDownVariants(inputs, baselineFirst: true)
    case "timing-ba":
        measureFusedDownVariants(inputs, baselineFirst: false)
    default:
        Issue.record("unknown experiment mode: \(mode)")
    }
}

private struct FusedDownExperimentInputs {
    let routedActivated: MLXArray
    let routedDownWeight: MLXArray
    let routedDownScales: MLXArray
    let indices: MLXArray
    let sharedActivated: MLXArray
    let sharedDownWeight: MLXArray
    let sharedDownScales: MLXArray
    let residual: MLXArray

    var materializedArrays: [MLXArray] {
        [
            routedActivated, routedDownWeight, routedDownScales, indices,
            sharedActivated, sharedDownWeight, sharedDownScales, residual,
        ]
    }
}

private enum FusedDownVariant {
    case baseline
    case candidate
}

private func makeFusedDownExperimentInputs() -> FusedDownExperimentInputs {
    let routedValues: [Float] = (0..<4_096).map { index in
        let mixed = index &* 37 &+ index / 11
        let centered = mixed % 61 - 30
        return Float(centered) / Float(32)
    }
    let routedActivated = MLXArray(
        routedValues,
        [1, 1, 8, 1, 512]
    ).asType(.bfloat16)

    let packedSeeds = (0..<256).map { expert -> UInt32 in
        let nibble = UInt32((expert &* 11) % 15 + 1)
        return nibble &* UInt32(0x1111_1111)
    }
    let routedDownWeight = contiguous(
        broadcast(
            MLXArray(packedSeeds, [256, 1, 1]),
            to: [256, 2_048, 64]
        )
    )

    let scaleBytes: [UInt8] = (0..<256).map { expert in
        [UInt8(0x30), UInt8(0x38), UInt8(0x40)][expert % 3]
    }
    let routedDownScales = contiguous(
        broadcast(
            MLXArray(scaleBytes, [256, 1, 1]),
            to: [256, 2_048, 32]
        )
    )

    let indices = MLXArray(
        [UInt32(0), 7, 42, 255, 3, 128, 17, 99],
        [1, 1, 8]
    )
    let sharedValues: [Float] = (0..<512).map { index in
        let mixed = index &* 19 &+ 5
        let centered = mixed % 47 - 23
        return Float(centered) / Float(24)
    }
    let sharedActivated = MLXArray(
        sharedValues,
        [1, 1, 512]
    ).asType(.bfloat16)
    let sharedDownWeight = MLXArray.full(
        [2_048, 64],
        values: MLXArray(UInt32(0x6543_2101)),
        dtype: .uint32
    )
    let sharedDownScales = MLXArray.full(
        [2_048, 32],
        values: MLXArray(UInt8(0x38)),
        dtype: .uint8
    )
    let residualValues: [Float] = (0..<2_048).map { index in
        let mixed = index &* 13 &+ 9
        let centered = mixed % 53 - 26
        return Float(centered) / Float(64)
    }
    let residual = MLXArray(
        residualValues,
        [1, 1, 2_048]
    ).asType(.bfloat16)

    return FusedDownExperimentInputs(
        routedActivated: routedActivated,
        routedDownWeight: routedDownWeight,
        routedDownScales: routedDownScales,
        indices: indices,
        sharedActivated: sharedActivated,
        sharedDownWeight: sharedDownWeight,
        sharedDownScales: sharedDownScales,
        residual: residual
    )
}

private func fusedDownOutput(
    _ variant: FusedDownVariant,
    inputs: FusedDownExperimentInputs,
    routerWeights: MLXArray
) -> MLXArray {
    switch variant {
    case .baseline:
        lagunaRoutedSharedDownResidualBaselineForExperiment(
            routedActivated: inputs.routedActivated,
            routedDownWeight: inputs.routedDownWeight,
            routedDownScales: inputs.routedDownScales,
            indices: inputs.indices,
            routerWeights: routerWeights,
            sharedActivated: inputs.sharedActivated,
            sharedDownWeight: inputs.sharedDownWeight,
            sharedDownScales: inputs.sharedDownScales,
            residual: inputs.residual
        )
    case .candidate:
        lagunaRoutedSharedDownResidual(
            routedActivated: inputs.routedActivated,
            routedDownWeight: inputs.routedDownWeight,
            routedDownScales: inputs.routedDownScales,
            indices: inputs.indices,
            routerWeights: routerWeights,
            sharedActivated: inputs.sharedActivated,
            sharedDownWeight: inputs.sharedDownWeight,
            sharedDownScales: inputs.sharedDownScales,
            residual: inputs.residual
        )
    }
}

private func verifyFusedDownExactness(_ inputs: FusedDownExperimentInputs) {
    var cases: [[Float]] = [
        [0.31, 0.19, 0.14, 0.11, 0.09, 0.07, 0.05, 0.04],
        [0, -0.0, 1, -1, 0.5, -0.5, 2, -2],
        [1.003_906_25, 0.996_093_75, 0.333_984_38, -0.333_984_38,
         0.007_843_018, -0.007_843_018, 127.5, -127.5],
    ]
    for caseIndex in 0..<29 {
        cases.append((0..<8).map { slot in
            Float(((caseIndex + 3) * (slot + 5) * 37) % 257 - 128) / 64
        })
    }

    for (caseIndex, weights) in cases.enumerated() {
        let routerWeights = MLXArray(weights, [1, 1, 8])
        let baseline = fusedDownOutput(
            .baseline,
            inputs: inputs,
            routerWeights: routerWeights
        )
        let candidate = fusedDownOutput(
            .candidate,
            inputs: inputs,
            routerWeights: routerWeights
        )
        eval(baseline, candidate)
        let baselineBits = baseline.view(dtype: .uint16).asArray(UInt16.self)
        let candidateBits = candidate.view(dtype: .uint16).asArray(UInt16.self)
        #expect(
            baselineBits == candidateBits,
            "producer weighting changed BF16 output in case \(caseIndex)"
        )
    }
    print("FUSED_DOWN_EXACTNESS cases=\(cases.count) mismatches=0")
}

private func measureFusedDownVariants(
    _ inputs: FusedDownExperimentInputs,
    baselineFirst: Bool
) {
    let routerWeights = MLXArray(
        [Float(0.31), 0.19, 0.14, 0.11, 0.09, 0.07, 0.05, 0.04],
        [1, 1, 8]
    )
    eval(routerWeights)

    for _ in 0..<4 {
        let first: FusedDownVariant = baselineFirst ? .baseline : .candidate
        let second: FusedDownVariant = baselineFirst ? .candidate : .baseline
        eval(
            fusedDownOutput(first, inputs: inputs, routerWeights: routerWeights),
            fusedDownOutput(second, inputs: inputs, routerWeights: routerWeights)
        )
    }

    let samples = 31
    let repetitions = 16
    var baselineTimes: [Double] = []
    var candidateTimes: [Double] = []
    for _ in 0..<samples {
        if baselineFirst {
            baselineTimes.append(
                measureFusedDownBatch(
                    .baseline,
                    inputs: inputs,
                    routerWeights: routerWeights,
                    repetitions: repetitions
                )
            )
            candidateTimes.append(
                measureFusedDownBatch(
                    .candidate,
                    inputs: inputs,
                    routerWeights: routerWeights,
                    repetitions: repetitions
                )
            )
        } else {
            candidateTimes.append(
                measureFusedDownBatch(
                    .candidate,
                    inputs: inputs,
                    routerWeights: routerWeights,
                    repetitions: repetitions
                )
            )
            baselineTimes.append(
                measureFusedDownBatch(
                    .baseline,
                    inputs: inputs,
                    routerWeights: routerWeights,
                    repetitions: repetitions
                )
            )
        }
    }

    let baselineMedian = median(baselineTimes)
    let candidateMedian = median(candidateTimes)
    let pairedDeltas = zip(baselineTimes, candidateTimes).map(-)
    let medianDelta = median(pairedDeltas)
    let deltaMAD = median(pairedDeltas.map { abs($0 - medianDelta) })
    let speedup = baselineMedian / candidateMedian
    let wins = pairedDeltas.filter { $0 > 0 }.count
    let order = baselineFirst ? "AB" : "BA"
    print(
        "FUSED_DOWN_TIMING " +
        "order=\(order) samples=\(samples) repetitions=\(repetitions) " +
        "baseline_median_ns=\(baselineMedian) " +
        "candidate_median_ns=\(candidateMedian) speedup=\(speedup) " +
        "median_delta_ns=\(medianDelta) delta_mad_ns=\(deltaMAD) " +
        "candidate_wins=\(wins)"
    )
    print("FUSED_DOWN_BASELINE_SAMPLES_NS \(baselineTimes)")
    print("FUSED_DOWN_CANDIDATE_SAMPLES_NS \(candidateTimes)")
}

private func measureFusedDownBatch(
    _ variant: FusedDownVariant,
    inputs: FusedDownExperimentInputs,
    routerWeights: MLXArray,
    repetitions: Int
) -> Double {
    let outputs = (0..<repetitions).map { _ in
        fusedDownOutput(variant, inputs: inputs, routerWeights: routerWeights)
    }
    let start = DispatchTime.now().uptimeNanoseconds
    eval(outputs)
    let elapsed = DispatchTime.now().uptimeNanoseconds - start
    return Double(elapsed) / Double(repetitions)
}

private func median(_ values: [Double]) -> Double {
    let sorted = values.sorted()
    let middle = sorted.count / 2
    if sorted.count.isMultiple(of: 2) {
        return (sorted[middle - 1] + sorted[middle]) / 2
    }
    return sorted[middle]
}
