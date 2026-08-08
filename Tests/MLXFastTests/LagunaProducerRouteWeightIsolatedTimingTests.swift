import Foundation
import MLX
import Testing
@testable import MLXFastModel

@Test
func fusedRoutedSharedDownIsolatedProductionTiming() {
    guard let label = ProcessInfo.processInfo.environment[
        "MLXFAST_FUSED_DOWN_TIMING_LABEL"
    ] else {
        return
    }

    let inputs = makeFusedDownTimingInputs()
    eval(inputs.materializedArrays)
    let routerWeights = MLXArray(
        [Float(0.31), 0.19, 0.14, 0.11, 0.09, 0.07, 0.05, 0.04],
        [1, 1, 8]
    )
    eval(routerWeights)

    for _ in 0..<4 {
        eval(fusedDownOutput(inputs: inputs, routerWeights: routerWeights))
    }

    let samples = 31
    let repetitions = 16
    let times = (0..<samples).map { _ in
        measureFusedDownBatch(
            inputs: inputs,
            routerWeights: routerWeights,
            repetitions: repetitions
        )
    }
    let sampleMedian = median(times)
    let sampleMAD = median(times.map { abs($0 - sampleMedian) })
    print(
        "FUSED_DOWN_ISOLATED label=\(label) samples=\(samples) " +
        "repetitions=\(repetitions) median_ns=\(sampleMedian) " +
        "mad_ns=\(sampleMAD)"
    )
    print("FUSED_DOWN_ISOLATED_SAMPLES_NS label=\(label) \(times)")
}

private struct FusedDownTimingInputs {
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

private func makeFusedDownTimingInputs() -> FusedDownTimingInputs {
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

    return FusedDownTimingInputs(
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
    inputs: FusedDownTimingInputs,
    routerWeights: MLXArray
) -> MLXArray {
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

private func measureFusedDownBatch(
    inputs: FusedDownTimingInputs,
    routerWeights: MLXArray,
    repetitions: Int
) -> Double {
    let outputs = (0..<repetitions).map { _ in
        fusedDownOutput(inputs: inputs, routerWeights: routerWeights)
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
