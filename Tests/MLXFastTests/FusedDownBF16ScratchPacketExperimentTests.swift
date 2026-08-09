import Foundation
import MLX
@testable import MLXFastModel
import Testing

private struct FusedDownInputs {
    let routedActivated: MLXArray
    let routedDownWeight: MLXArray
    let routedDownScales: MLXArray
    let indices: MLXArray
    let routerWeights: MLXArray
    let sharedActivated: MLXArray
    let sharedDownWeight: MLXArray
    let sharedDownScales: MLXArray
    let residual: MLXArray
}

private func fusedDownInputs(pattern: Int) throws -> FusedDownInputs {
    let routedValues = (0..<(LagunaConstants.numExpertsPerTok * LagunaConstants.moeIntermediateSize))
        .map { index -> Float in
            switch pattern {
            case 0:
                return Float(((index * 13 + index / LagunaConstants.moeIntermediateSize * 7) % 29) - 14) / 16
            default:
                let magnitude = Float((index * 37 + 11) % 127 - 63)
                return index.isMultiple(of: 17) ? -0.0 : magnitude / 32
            }
        }
    let routedActivated = MLXArray(
        routedValues,
        [1, 1, LagunaConstants.numExpertsPerTok, 1, LagunaConstants.moeIntermediateSize]
    ).asType(.bfloat16)
    let routedDownWeight = MLXArray.full(
        [
            LagunaConstants.numExperts,
            LagunaConstants.hiddenSize,
            LagunaConstants.moeIntermediateSize / 8,
        ],
        values: MLXArray(UInt32(pattern == 0 ? 0x1111_1111 : 0x7654_3210)),
        dtype: .uint32
    )
    let routedFullScales = MLXArray.full(
        [
            LagunaConstants.numExperts,
            LagunaConstants.hiddenSize,
            LagunaConstants.moeIntermediateSize / 16,
        ],
        values: MLXArray(UInt8(pattern == 0 ? 0x38 : 0x3A)),
        dtype: .uint8
    )
    let routedDownScales = try #require(
        lagunaHalvedGroup32ScalePlane(routedFullScales, allowedFlatPairs: [0]))
    let indices = MLXArray(
        [UInt32(0), 0, 7, 7, 255, 255, 3, 3],
        [1, 1, LagunaConstants.numExpertsPerTok]
    )
    let routerWeights = MLXArray(
        [Float(0.125), -0.25, 0.375, -0.5, 0.625, -0.75, 1, -1.25],
        [1, 1, LagunaConstants.numExpertsPerTok]
    )

    let sharedValues = (0..<LagunaConstants.sharedExpertIntermediateSize).map { index -> Float in
        switch pattern {
        case 0:
            return Float(((index * 11) % 23) - 11) / 16
        default:
            return index.isMultiple(of: 19)
                ? 0.0
                : Float(((index * 41) % 101) - 50) / 32
        }
    }
    let sharedActivated = MLXArray(
        sharedValues,
        [1, 1, LagunaConstants.sharedExpertIntermediateSize]
    ).asType(.bfloat16)
    let sharedDownWeight = MLXArray.full(
        [
            LagunaConstants.hiddenSize,
            LagunaConstants.sharedExpertIntermediateSize / 8,
        ],
        values: MLXArray(UInt32(pattern == 0 ? 0x5432_1765 : 0x0123_4567)),
        dtype: .uint32
    )
    let sharedFullScales = MLXArray.full(
        [
            LagunaConstants.hiddenSize,
            LagunaConstants.sharedExpertIntermediateSize / 16,
        ],
        values: MLXArray(UInt8(pattern == 0 ? 0x38 : 0x3A)),
        dtype: .uint8
    )
    let sharedDownScales = try #require(
        lagunaHalvedGroup32ScalePlane(sharedFullScales, allowedFlatPairs: [0]))
    let residualValues = (0..<LagunaConstants.hiddenSize).map { index -> Float in
        switch pattern {
        case 0:
            return Float((index % 31) - 15) / 32
        default:
            return index.isMultiple(of: 23) ? -0.0 : Float((index % 47) - 23) / 64
        }
    }
    let residual = MLXArray(
        residualValues,
        [1, 1, LagunaConstants.hiddenSize]
    ).asType(.bfloat16)

    eval(routedActivated, routedDownWeight, routedDownScales, indices, routerWeights)
    eval(sharedActivated, sharedDownWeight, sharedDownScales, residual)
    return FusedDownInputs(
        routedActivated: routedActivated,
        routedDownWeight: routedDownWeight,
        routedDownScales: routedDownScales,
        indices: indices,
        routerWeights: routerWeights,
        sharedActivated: sharedActivated,
        sharedDownWeight: sharedDownWeight,
        sharedDownScales: sharedDownScales,
        residual: residual
    )
}

private func launchFusedDown(
    _ inputs: FusedDownInputs,
    packetizedScratch: Bool
) -> MLXArray {
    lagunaRoutedSharedDownResidual(
        routedActivated: inputs.routedActivated,
        routedDownWeight: inputs.routedDownWeight,
        routedDownScales: inputs.routedDownScales,
        indices: inputs.indices,
        routerWeights: inputs.routerWeights,
        sharedActivated: inputs.sharedActivated,
        sharedDownWeight: inputs.sharedDownWeight,
        sharedDownScales: inputs.sharedDownScales,
        residual: inputs.residual,
        staged: true,
        packetizedScratch: packetizedScratch
    )
}

private func fusedDownSeconds(
    _ inputs: FusedDownInputs,
    packetizedScratch: Bool
) -> Double {
    let start = Date()
    eval(launchFusedDown(inputs, packetizedScratch: packetizedScratch))
    return Date().timeIntervalSince(start)
}

private func median(_ values: [Double]) -> Double {
    let sorted = values.sorted()
    let midpoint = sorted.count / 2
    return (sorted[midpoint - 1] + sorted[midpoint]) / 2
}

private func medianAbsoluteDeviation(_ values: [Double]) -> Double {
    let center = median(values)
    return median(values.map { abs($0 - center) })
}

private func timingValues(_ values: [Double]) -> String {
    values.map(String.init).joined(separator: ",")
}

private func wordChecksum(_ words: [UInt16]) -> UInt64 {
    words.reduce(UInt64(0xcbf2_9ce4_8422_2325)) { hash, word in
        (hash ^ UInt64(word)) &* 0x0000_0100_0000_01b3
    }
}

@Suite(.serialized)
struct FusedDownBF16ScratchPacketExperimentTests {
    @Test
    func exactnessCompilerAndCorruptionGate() throws {
        guard ProcessInfo.processInfo.environment["MLXFAST_FUSED_DOWN_PACKET_GATE"] == "exactness"
        else { return }

        print(
            "FUSED_DOWN_PACKET_REACHABILITY control=laguna_routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6 "
                + "candidate=laguna_routed_shared_nvfp4_down_residual_bf16_sh_stage4_packet_v7 "
                + "threadgroup=288 grid_groups=512 scratch_bytes=72 packet_alignment=8"
        )
        for pattern in 0..<2 {
            let inputs = try fusedDownInputs(pattern: pattern)
            let control = launchFusedDown(inputs, packetizedScratch: false)
            let candidate = launchFusedDown(inputs, packetizedScratch: true)
            eval(control, candidate)
            let controlWords = control.view(dtype: .uint16).asArray(UInt16.self)
            let candidateWords = candidate.view(dtype: .uint16).asArray(UInt16.self)
            #expect(controlWords == candidateWords)
            #expect(controlWords.count == LagunaConstants.hiddenSize)

            var corrupted = candidateWords
            corrupted[(pattern * 997 + 31) % corrupted.count] ^= 1
            #expect(corrupted != controlWords)
            print(
                "FUSED_DOWN_PACKET_EXACT pattern=\(pattern) words=\(controlWords.count) "
                    + "checksum=\(String(wordChecksum(controlWords), radix: 16)) "
                    + "corruption_negative=detected"
            )
        }
    }

    @Test
    func isolatedTimingBothOrders() throws {
        guard ProcessInfo.processInfo.environment["MLXFAST_FUSED_DOWN_PACKET_GATE"] == "timing"
        else { return }

        let inputs = try fusedDownInputs(pattern: 1)
        for _ in 0..<6 {
            _ = fusedDownSeconds(inputs, packetizedScratch: false)
            _ = fusedDownSeconds(inputs, packetizedScratch: true)
        }

        var abControl: [Double] = []
        var abCandidate: [Double] = []
        var baControl: [Double] = []
        var baCandidate: [Double] = []
        for _ in 0..<24 {
            abControl.append(fusedDownSeconds(inputs, packetizedScratch: false))
            abCandidate.append(fusedDownSeconds(inputs, packetizedScratch: true))
        }
        for _ in 0..<24 {
            baCandidate.append(fusedDownSeconds(inputs, packetizedScratch: true))
            baControl.append(fusedDownSeconds(inputs, packetizedScratch: false))
        }

        let abControlMedian = median(abControl)
        let abCandidateMedian = median(abCandidate)
        let baControlMedian = median(baControl)
        let baCandidateMedian = median(baCandidate)
        let pooledControl = abControl + baControl
        let pooledCandidate = abCandidate + baCandidate
        let pooledControlMedian = median(pooledControl)
        let pooledCandidateMedian = median(pooledCandidate)
        print(
            "FUSED_DOWN_PACKET_TIMING "
                + "ab_control_median=\(abControlMedian) ab_candidate_median=\(abCandidateMedian) "
                + "ab_speedup=\(abControlMedian / abCandidateMedian) "
                + "ba_control_median=\(baControlMedian) ba_candidate_median=\(baCandidateMedian) "
                + "ba_speedup=\(baControlMedian / baCandidateMedian) "
                + "pooled_control_median=\(pooledControlMedian) "
                + "pooled_candidate_median=\(pooledCandidateMedian) "
                + "pooled_speedup=\(pooledControlMedian / pooledCandidateMedian) "
                + "control_mad=\(medianAbsoluteDeviation(pooledControl)) "
                + "candidate_mad=\(medianAbsoluteDeviation(pooledCandidate))"
        )
        print("FUSED_DOWN_PACKET_AB_CONTROL=[\(timingValues(abControl))]")
        print("FUSED_DOWN_PACKET_AB_CANDIDATE=[\(timingValues(abCandidate))]")
        print("FUSED_DOWN_PACKET_BA_CONTROL=[\(timingValues(baControl))]")
        print("FUSED_DOWN_PACKET_BA_CANDIDATE=[\(timingValues(baCandidate))]")
    }
}
