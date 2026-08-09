import Foundation
import MLX
import Testing
@testable import MLXFastModel

@Test
func routerBF16CompanionRawDifferentialWhenRuntimeTestsAreEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
        return
    }

    var state = UInt32(0x6d2b_79f5)
    let randomValues = (0..<256).map { _ -> Float in
        state = state &* 1_664_525 &+ 1_013_904_223
        return Float(Int32(bitPattern: state)) / Float(Int32.max) * 12
    }
    let randomBias = (0..<256).map { index in
        Float((index * 37) % 101 - 50) / 512
    }
    let cases: [(String, [Float], [Float], DType)] = [
        ("zeros-and-ties", Array(repeating: 0, count: 256), Array(repeating: 0, count: 256), .float32),
        ("repeated-tiny", (0..<256).map { Float($0 % 9 - 4) * 1e-7 }, (0..<256).map { Float($0 % 5 - 2) * 1e-8 }, .float32),
        ("seeded-random-bf16", randomValues, randomBias, .bfloat16),
        ("extremes", (0..<256).map { $0 % 4 == 0 ? 80 : ($0 % 4 == 1 ? -80 : Float($0 % 13 - 6)) }, (0..<256).map { $0 % 17 == 0 ? 4 : -Float($0 % 7) / 16 }, .float32),
    ]

    for (label, values, biasValues, dtype) in cases {
        let floatLogits = MLXArray(values)
        let logits = dtype == .float32 ? floatLogits : floatLogits.asType(dtype)
        let bias = MLXArray(biasValues)
        let old = lagunaDecodeRouterTop8OrdinalScoreTableForTesting(
            logits: logits,
            correctionBias: bias,
            normalizing: true
        )
        let new = lagunaDecodeRouterTop8OrdinalScoreTableBF16ForTesting(
            logits: logits,
            correctionBias: bias
        )
        let oldBF16 = old.1.asType(.bfloat16)
        eval(old.0, old.1, new.0, new.1, new.2, oldBF16)

        #expect(old.0.asArray(UInt32.self) == new.0.asArray(UInt32.self), Comment(rawValue: label))
        #expect(
            view(old.1, dtype: .uint32).asArray(UInt32.self)
                == view(new.1, dtype: .uint32).asArray(UInt32.self),
            Comment(rawValue: label)
        )
        #expect(
            view(oldBF16, dtype: .uint16).asArray(UInt16.self)
                == view(new.2, dtype: .uint16).asArray(UInt16.self),
            Comment(rawValue: label)
        )
    }
}

@Test
func routerBF16CompanionFusedSourceCaptureWhenRuntimeTestsAreEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
        return
    }

    let data = makeRouterBF16FusedData()
    let weights = MLXArray([Float(0), 0.125, 0.25, 0.375, 0.001, 0.5, 0.75, 1], [1, 1, 8])
    compareFusedOutputs(data: data, weights: weights, label: "source-capture")
}

@Test
func routerBF16CompanionFusedAdversarialDifferentialWhenRuntimeTestsAreEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
        return
    }

    let data = makeRouterBF16FusedData()
    let cases: [(String, [Float])] = [
        ("all-zero", Array(repeating: 0, count: 8)),
        ("all-tied", Array(repeating: 0.125, count: 8)),
        ("tiny-and-rounded", [Float.leastNonzeroMagnitude, 1e-39, 1e-8, 0.001, 0.00390625, 0.1, 0.33333334, 1]),
        ("mixed-lanes", [1, 0, 0.75, 0.0001, 0.5, 0.25, 0.125, 0.0625]),
    ]

    for (label, values) in cases {
        compareFusedOutputs(
            data: data,
            weights: MLXArray(values, [1, 1, 8]),
            label: label
        )
    }
}

private struct RouterBF16FusedData {
    let routedActivated: MLXArray
    let routedDownWeight: MLXArray
    let routedDownScales: MLXArray
    let indices: MLXArray
    let sharedActivated: MLXArray
    let sharedDownWeight: MLXArray
    let sharedDownScales: MLXArray
    let residual: MLXArray
}

private func makeRouterBF16FusedData() -> RouterBF16FusedData {
    let routedValues = (0..<(8 * 512)).map { index in
        Float(index % 29 - 14) / 32
    }
    let routedActivated = MLXArray(routedValues, [1, 1, 8, 1, 512]).asType(.bfloat16)

    let expertCodes = (0..<256).map { expert in
        UInt32((expert % 7) + 1) &* UInt32(0x1111_1111)
    }
    let routedDownWeight = contiguous(
        broadcast(MLXArray(expertCodes, [256, 1, 1]), to: [256, 2_048, 64])
    )
    let routedDownScales = MLXArray.full(
        [256, 2_048, 32],
        values: MLXArray(UInt8(0x38)),
        dtype: .uint8
    )
    let indices = MLXArray([UInt32(0), 7, 42, 255, 3, 128, 17, 99], [1, 1, 8])

    let sharedValues = (0..<512).map { Float($0 % 19 - 9) / 16 }
    let sharedActivated = MLXArray(sharedValues, [1, 1, 512]).asType(.bfloat16)
    let sharedDownWeight = contiguous(
        broadcast(MLXArray([UInt32(0x3333_3333)], [1, 1]), to: [2_048, 64])
    )
    let sharedDownScales = MLXArray.full(
        [2_048, 32],
        values: MLXArray(UInt8(0x38)),
        dtype: .uint8
    )
    let residual = MLXArray(
        (0..<2_048).map { Float($0 % 23 - 11) / 64 },
        [1, 1, 2_048]
    ).asType(.bfloat16)

    return RouterBF16FusedData(
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

private func compareFusedOutputs(
    data: RouterBF16FusedData,
    weights: MLXArray,
    label: String
) {
    let weightsBF16 = weights.asType(.bfloat16)
    let fallbackFP32 = lagunaRoutedDownReduce(
        data.routedActivated,
        downWeight: data.routedDownWeight,
        downScales: data.routedDownScales,
        indices: data.indices,
        routerWeights: weights
    )
    let fallbackBF16 = lagunaRoutedDownReduce(
        data.routedActivated,
        downWeight: data.routedDownWeight,
        downScales: data.routedDownScales,
        indices: data.indices,
        routerWeights: weightsBF16
    )
    let activeFP32 = lagunaRoutedSharedDownResidual(
        routedActivated: data.routedActivated,
        routedDownWeight: data.routedDownWeight,
        routedDownScales: data.routedDownScales,
        indices: data.indices,
        routerWeights: weights,
        sharedActivated: data.sharedActivated,
        sharedDownWeight: data.sharedDownWeight,
        sharedDownScales: data.sharedDownScales,
        residual: data.residual
    )
    let activeBF16 = lagunaRoutedSharedDownResidual(
        routedActivated: data.routedActivated,
        routedDownWeight: data.routedDownWeight,
        routedDownScales: data.routedDownScales,
        indices: data.indices,
        routerWeights: weightsBF16,
        sharedActivated: data.sharedActivated,
        sharedDownWeight: data.sharedDownWeight,
        sharedDownScales: data.sharedDownScales,
        residual: data.residual
    )
    eval(fallbackFP32, fallbackBF16, activeFP32, activeBF16)

    #expect(
        view(fallbackFP32, dtype: .uint16).asArray(UInt16.self)
            == view(fallbackBF16, dtype: .uint16).asArray(UInt16.self),
        Comment(rawValue: "fallback-\(label)")
    )
    #expect(
        view(activeFP32, dtype: .uint16).asArray(UInt16.self)
            == view(activeBF16, dtype: .uint16).asArray(UInt16.self),
        Comment(rawValue: "active-\(label)")
    )
}
