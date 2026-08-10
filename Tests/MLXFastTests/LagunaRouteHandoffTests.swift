import Foundation
import MLX
@testable import MLXFastModel
import Testing

@Suite(.serialized)
struct LagunaRouteHandoffTests {
    private struct Buffers {
        let input: MLXArray
        let fusedGateUpWeight: MLXArray
        let fusedGateUpScales: MLXArray
        let routedActivated: MLXArray
        let routedDownWeight: MLXArray
        let routedDownScales: MLXArray
        let sharedActivated: MLXArray
        let sharedDownWeight: MLXArray
        let sharedDownScales: MLXArray
        let residual: MLXArray
    }

    private func buffers() -> Buffers {
        let hidden = LagunaConstants.hiddenSize
        let intermediate = LagunaConstants.moeIntermediateSize
        let sharedIntermediate = LagunaConstants.sharedExpertIntermediateSize
        let experts = LagunaConstants.numExperts
        let routed = LagunaConstants.numExpertsPerTok
        let inputValues = (0..<hidden).map { i in
            Float((i * 29) % 97 - 48) / 256
        }
        let routedValues = (0..<(routed * intermediate)).map { i in
            let slot = i / intermediate
            return Float(((i * 13) % 61) - 30 + slot * 3) / 128
        }
        let sharedValues = (0..<sharedIntermediate).map { i in
            Float((i * 17) % 43 - 21) / 128
        }
        let residualValues = (0..<hidden).map { i in
            Float((i * 7) % 31 - 15) / 256
        }
        return Buffers(
            input: MLXArray(inputValues, [1, 1, hidden]).asType(.bfloat16),
            fusedGateUpWeight: MLXArray.full(
                [experts, 2 * intermediate, hidden / 8],
                values: MLXArray(UInt32(0x2222_2222)), dtype: .uint32),
            fusedGateUpScales: MLXArray.full(
                [lagunaPackedRoutedGateUpScaleBytes],
                values: MLXArray(UInt8(0x38)), dtype: .uint8),
            routedActivated: MLXArray(
                routedValues, [1, 1, routed, 1, intermediate]
            ).asType(.bfloat16),
            routedDownWeight: MLXArray.full(
                [experts, hidden, intermediate / 8],
                values: MLXArray(UInt32(0x2222_2222)), dtype: .uint32),
            routedDownScales: MLXArray.full(
                [lagunaRoutedDownScaleBytes],
                values: MLXArray(UInt8(0x38)), dtype: .uint8),
            sharedActivated: MLXArray(
                sharedValues, [1, 1, sharedIntermediate]
            ).asType(.bfloat16),
            sharedDownWeight: MLXArray.full(
                [hidden, sharedIntermediate / 8],
                values: MLXArray(UInt32(0x2222_2222)), dtype: .uint32),
            sharedDownScales: MLXArray.full(
                [lagunaScalePatchHeaderBytes + hidden * (sharedIntermediate / 32)],
                values: MLXArray(UInt8(0x38)), dtype: .uint8),
            residual: MLXArray(residualValues, [1, 1, hidden]).asType(.bfloat16)
        )
    }

    private func routeCases() -> [(String, [Float], [Float])] {
        let smooth: [Float] = (0..<256).map { i -> Float in
            let value = (i * 73 + 19) % 257 - 128
            return Float(value) / 16
        }
        let smoothBias: [Float] = (0..<256).map { i -> Float in
            let value = (i * 37 + 11) % 101 - 50
            return Float(value) / 512
        }
        let ties: [Float] = (0..<256).map { i -> Float in
            Float((i / 8) % 9 - 4) / 2
        }
        let tiesBias: [Float] = (0..<256).map { i -> Float in
            Float((i % 8) - 4) / 256
        }
        let extrema: [Float] = (0..<256).map { i -> Float in
            switch i % 6 {
            case 0: return 80
            case 1: return -80
            case 2: return 0
            case 3: return -0.0
            case 4: return 12
            default: return -12
            }
        }
        let extremaBias: [Float] = (0..<256).map { i -> Float in
            let value = (i * 23) % 41 - 20
            return Float(value) / 64
        }
        return [
            ("smooth", smooth, smoothBias),
            ("ties", ties, tiesBias),
            ("extrema", extrema, extremaBias),
        ]
    }

    private func orderedKeys(_ indices: [UInt32]) -> MLXArray {
        var keys = Array(repeating: UInt32.max, count: LagunaConstants.numExperts)
        for (rank, index) in indices.enumerated() {
            keys[Int(index)] = UInt32(rank)
        }
        return MLXArray(keys, [1, 1, LagunaConstants.numExperts])
    }

    private func down(
        _ fixture: Buffers,
        activated: MLXArray,
        indices: MLXArray,
        scores: MLXArray,
        normalizing: Bool
    ) -> MLXArray {
        lagunaRoutedSharedDownResidual(
            routedActivated: activated,
            routedDownWeight: fixture.routedDownWeight,
            routedDownScales: fixture.routedDownScales,
            indices: indices,
            routerWeights: scores,
            sharedActivated: fixture.sharedActivated,
            sharedDownWeight: fixture.sharedDownWeight,
            sharedDownScales: fixture.sharedDownScales,
            residual: fixture.residual,
            staged: true,
            normalizeRouterWeights: normalizing
        )
    }

    @Test
    func payloadAndNormalizedReductionAreBitExact() throws {
        guard ProcessInfo.processInfo.environment["MLXFAST_RUN_ROUTE_HANDOFF_TESTS"] == "1"
        else { return }

        let fixture = buffers()
        for (label, values, biasValues) in routeCases() {
            let logits = MLXArray(values, [1, 1, 256]).asType(.bfloat16)
            let bias = MLXArray(biasValues, [1, 1, 256])
            let (rawIndices, rawScores) = lagunaDecodeRouterTop8AcceptedForTesting(
                logits: logits, correctionBias: bias, normalizing: false)
            eval(rawIndices, rawScores)
            let expectedIndices = rawIndices.asArray(UInt32.self)
            let producer = lagunaRoutedSwiGLUQMVPackedTop8(
                fixture.input,
                fusedWeight: fixture.fusedGateUpWeight,
                packedScales: fixture.fusedGateUpScales,
                routerKeys: orderedKeys(expectedIndices),
                routerLogits: logits
            )
            let handoffIndices = try #require(producer.routeIndices)
            let handoffScores = try #require(producer.routeScores)
            eval(handoffIndices, handoffScores)
            #expect(handoffIndices.asArray(UInt32.self) == expectedIndices, Comment(rawValue: label))
            #expect(
                handoffScores.asArray(Float.self).map(\.bitPattern)
                    == rawScores.asArray(Float.self).map(\.bitPattern),
                Comment(rawValue: label)
            )

            let (normalizedIndices, normalizedScores) =
                lagunaDecodeRouterTop8AcceptedForTesting(
                    logits: logits, correctionBias: bias, normalizing: true)
            let baseline = down(
                fixture,
                activated: fixture.routedActivated,
                indices: normalizedIndices,
                scores: normalizedScores,
                normalizing: false
            )
            let candidate = down(
                fixture,
                activated: fixture.routedActivated,
                indices: handoffIndices,
                scores: handoffScores,
                normalizing: true
            )
            eval(normalizedIndices, normalizedScores, baseline, candidate)
            #expect(normalizedIndices.asArray(UInt32.self) == expectedIndices, Comment(rawValue: label))
            #expect(
                candidate.asArray(Float.self).map(\.bitPattern)
                    == baseline.asArray(Float.self).map(\.bitPattern),
                Comment(rawValue: label)
            )
        }
    }

    @Test
    func isolatedFullBodyTiming() throws {
        guard ProcessInfo.processInfo.environment["MLXFAST_RUN_ROUTE_HANDOFF_BENCH"] == "1"
        else { return }

        let fixture = buffers()
        let (_, values, biasValues) = routeCases()[0]
        let logits = MLXArray(values, [1, 1, 256]).asType(.bfloat16)
        let bias = MLXArray(biasValues, [1, 1, 256])
        let (rawIndices, _) = lagunaDecodeRouterTop8AcceptedForTesting(
            logits: logits, correctionBias: bias, normalizing: false)
        eval(rawIndices)
        let keys = orderedKeys(rawIndices.asArray(UInt32.self))

        func output(handoff: Bool) throws -> MLXArray {
            let producer = lagunaRoutedSwiGLUQMVPackedTop8(
                fixture.input,
                fusedWeight: fixture.fusedGateUpWeight,
                packedScales: fixture.fusedGateUpScales,
                routerKeys: keys,
                routerLogits: logits
            )
            if handoff {
                return down(
                    fixture,
                    activated: producer.activated,
                    indices: try #require(producer.routeIndices),
                    scores: try #require(producer.routeScores),
                    normalizing: true
                )
            }
            let (indices, scores) = lagunaDecodeRouterTop8AcceptedForTesting(
                logits: logits, correctionBias: bias, normalizing: true)
            return down(
                fixture,
                activated: producer.activated,
                indices: indices,
                scores: scores,
                normalizing: false
            )
        }

        for handoff in [false, true, true, false] {
            eval(try output(handoff: handoff))
        }

        var baselineMilliseconds: [Double] = []
        var candidateMilliseconds: [Double] = []
        let order = [false, true, true, false, true, false, false, true]
        for _ in 0..<5 {
            for handoff in order {
                let result = try output(handoff: handoff)
                let start = DispatchTime.now().uptimeNanoseconds
                eval(result)
                let elapsed = DispatchTime.now().uptimeNanoseconds - start
                let milliseconds = Double(elapsed) / 1_000_000
                if handoff {
                    candidateMilliseconds.append(milliseconds)
                } else {
                    baselineMilliseconds.append(milliseconds)
                }
            }
        }

        func median(_ values: [Double]) -> Double {
            let sorted = values.sorted()
            return (sorted[sorted.count / 2 - 1] + sorted[sorted.count / 2]) / 2
        }
        let baselineMedian = median(baselineMilliseconds)
        let candidateMedian = median(candidateMilliseconds)
        print("ROUTE_HANDOFF_BASELINE_MS=\(baselineMilliseconds)")
        print("ROUTE_HANDOFF_CANDIDATE_MS=\(candidateMilliseconds)")
        print("ROUTE_HANDOFF_BASELINE_MEDIAN_MS=\(baselineMedian)")
        print("ROUTE_HANDOFF_CANDIDATE_MEDIAN_MS=\(candidateMedian)")
        print("ROUTE_HANDOFF_SPEEDUP=\(baselineMedian / candidateMedian)")
    }
}
