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
    let zeros = Array(repeating: Float(0), count: 256)
    let repeatedTiny = (0..<256).map { Float($0 % 9 - 4) * 1e-7 }
    let repeatedTinyBias = (0..<256).map { Float($0 % 5 - 2) * 1e-8 }
    let extremes = (0..<256).map { index -> Float in
        if index % 4 == 0 { return 80 }
        if index % 4 == 1 { return -80 }
        return Float(index % 13 - 6)
    }
    let extremeBias = (0..<256).map { index -> Float in
        index % 17 == 0 ? 4 : -Float(index % 7) / 16
    }
    let cases: [(String, [Float], [Float], DType)] = [
        ("zeros-and-ties", zeros, zeros, .float32),
        ("repeated-tiny", repeatedTiny, repeatedTinyBias, .float32),
        ("seeded-random-bf16", randomValues, randomBias, .bfloat16),
        ("extremes", extremes, extremeBias, .float32),
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

@Test
func routerBF16CompanionMicrobenchmarkWhenRuntimeTestsAreEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
        return
    }

    let data = makeRouterBF16FusedData()
    let logits = MLXArray(
        (0..<256).map { index in Float((index * 73) % 257 - 128) / 16 },
        [1, 1, 256]
    ).asType(.bfloat16)
    let correctionBias = MLXArray(
        (0..<256).map { index in Float((index * 37) % 101 - 50) / 512 },
        [256]
    )

    let baseline = routerFusedBaselineOutput(
        data: data, logits: logits, correctionBias: correctionBias)
    let candidate = routerFusedCandidateOutput(
        data: data, logits: logits, correctionBias: correctionBias)
    eval(baseline, candidate)
    #expect(
        view(baseline, dtype: .uint16).asArray(UInt16.self)
            == view(candidate, dtype: .uint16).asArray(UInt16.self)
    )

    for _ in 0..<6 {
        eval(routerFusedBaselineOutput(data: data, logits: logits, correctionBias: correctionBias))
        eval(routerFusedCandidateOutput(data: data, logits: logits, correctionBias: correctionBias))
    }

    let repetitions = 6
    let blockCount = 17
    let orders: [(String, [Bool])] = [
        ("ABBA", [false, true, true, false]),
        ("BAAB", [true, false, false, true]),
    ]

    for (orderName, order) in orders {
        var speedups = [Double]()
        speedups.reserveCapacity(blockCount)
        for block in 0..<blockCount {
            var baselineSeconds = 0.0
            var candidateSeconds = 0.0
            for isCandidate in order {
                let seconds: Double
                if isCandidate {
                    seconds = measureRouterFusedBatch(repetitions: repetitions) {
                        routerFusedCandidateOutput(
                            data: data, logits: logits, correctionBias: correctionBias)
                    }
                    candidateSeconds += seconds
                } else {
                    seconds = measureRouterFusedBatch(repetitions: repetitions) {
                        routerFusedBaselineOutput(
                            data: data, logits: logits, correctionBias: correctionBias)
                    }
                    baselineSeconds += seconds
                }
            }
            let speedup = baselineSeconds / candidateSeconds
            speedups.append(speedup)
            print(String(
                format: "ROUTER_BF16_MICROBENCH order=%@ block=%02d baseline_s=%.9f candidate_s=%.9f speedup=%.6f",
                orderName, block, baselineSeconds / 2, candidateSeconds / 2, speedup
            ))
        }

        let medianSpeedup = median(speedups)
        let mad = median(speedups.map { abs($0 - medianSpeedup) })
        let gain = medianSpeedup - 1
        let samples = speedups.map { String(format: "%.6f", $0) }.joined(separator: ",")
        print(String(
            format: "ROUTER_BF16_MICROBENCH_SUMMARY order=%@ blocks=%d repetitions=%d median_speedup=%.6f mad=%.6f gain=%.6f samples=[%@]",
            orderName, blockCount, repetitions, medianSpeedup, mad, gain, samples
        ))
        #expect(
            medianSpeedup >= 1.003,
            Comment(rawValue: "\(orderName) median speedup \(medianSpeedup) is below 1.003")
        )
        #expect(
            gain > 2 * mad,
            Comment(rawValue: "\(orderName) gain \(gain) is not greater than 2x MAD \(mad)")
        )
    }
}

private func routerFusedBaselineOutput(
    data: RouterBF16FusedData,
    logits: MLXArray,
    correctionBias: MLXArray
) -> MLXArray {
    let router = lagunaDecodeRouterTop8OrdinalScoreTableForTesting(
        logits: logits,
        correctionBias: correctionBias,
        normalizing: true
    )
    return lagunaRoutedSharedDownResidual(
        routedActivated: data.routedActivated,
        routedDownWeight: data.routedDownWeight,
        routedDownScales: data.routedDownScales,
        indices: router.0,
        routerWeights: router.1,
        sharedActivated: data.sharedActivated,
        sharedDownWeight: data.sharedDownWeight,
        sharedDownScales: data.sharedDownScales,
        residual: data.residual
    )
}

private func routerFusedCandidateOutput(
    data: RouterBF16FusedData,
    logits: MLXArray,
    correctionBias: MLXArray
) -> MLXArray {
    let router = lagunaDecodeRouterTop8OrdinalScoreTableBF16ForTesting(
        logits: logits,
        correctionBias: correctionBias
    )
    return lagunaRoutedSharedDownResidual(
        routedActivated: data.routedActivated,
        routedDownWeight: data.routedDownWeight,
        routedDownScales: data.routedDownScales,
        indices: router.0,
        routerWeights: router.2,
        sharedActivated: data.sharedActivated,
        sharedDownWeight: data.sharedDownWeight,
        sharedDownScales: data.sharedDownScales,
        residual: data.residual
    )
}

private func measureRouterFusedBatch(
    repetitions: Int,
    makeOutput: () -> MLXArray
) -> Double {
    let start = DispatchTime.now().uptimeNanoseconds
    for _ in 0..<repetitions {
        eval(makeOutput())
    }
    let elapsed = DispatchTime.now().uptimeNanoseconds - start
    return Double(elapsed) / 1_000_000_000 / Double(repetitions)
}

private func median(_ values: [Double]) -> Double {
    let sorted = values.sorted()
    let middle = sorted.count / 2
    if sorted.count.isMultiple(of: 2) {
        return (sorted[middle - 1] + sorted[middle]) / 2
    }
    return sorted[middle]
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
