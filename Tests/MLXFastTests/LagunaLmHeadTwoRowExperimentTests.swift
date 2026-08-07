import Foundation
import MLX
import MLXFast
@testable import MLXFastModel
import Testing

private let lmHeadControlSource = """
    constexpr float GAMMA = 0x1p-15f;

    uint row = threadgroup_position_in_grid.x * 16 +
        simdgroup_index_in_threadgroup;
    uint lane = thread_index_in_simdgroup;

    const device uint8_t* lorow = codes_lo + size_t(row) * 1024;
    const device uint8_t* hirow = codes_hi + size_t(row) * 256;
    const device uint8_t* srow = scales + size_t(row) * 64;

    float c_acc = 0.0f;
    float d_acc = 0.0f;
    for (uint gg = 0; gg < 2; ++gg) {
        uint g = 2 * lane + gg;
        float sd = laguna_e8m0_decode(srow[g]);
        uint4 lo4 = ((const device uint4*)(lorow + g * 16))[0];
        uint hb = ((const device uint*)(hirow + g * 4))[0];
        const device ushort4* xrow = (const device ushort4*)(x + g * 32);
        float cg = 0.0f;
        float ag = 0.0f;
        #pragma clang loop unroll(full)
        for (uint w = 0; w < 4; ++w) {
            // Word w: elements 8w..8w+7 of the group. Nibble plane byte
            // b holds elements 2b (low) / 2b+1 (high); 1-bit plane bit j
            // of the group's word holds element j's bit 4.
            uint lw = lo4[w];
            uint hw = hb >> (8u * w);
            uint4 ne = (uint4(lw) >> uint4(0u, 8u, 16u, 24u)) & 15u;
            uint4 no = (uint4(lw) >> uint4(4u, 12u, 20u, 28u)) & 15u;
            uint4 he = (uint4(hw) >> uint4(0u, 2u, 4u, 6u)) & 1u;
            uint4 ho = (uint4(hw) >> uint4(1u, 3u, 5u, 7u)) & 1u;
            // Offset-binary decode: value = u - 16 in [-15, 15], exact.
            float4 ve = float4(ne | (he << 4u)) - 16.0f;
            float4 vo = float4(no | (ho << 4u)) - 16.0f;
            // bf16 -> f32 is exactly bits<<16 for every value class.
            float4 xa = as_type<float4>(uint4(xrow[2 * w]) << 16);
            float4 xb = as_type<float4>(uint4(xrow[2 * w + 1]) << 16);
            float4 xe = float4(xa.x, xa.z, xb.x, xb.z);
            float4 xo = float4(xa.y, xa.w, xb.y, xb.w);
            float4 axe = metal::abs(xe);
            float4 axo = metal::abs(xo);
            #pragma clang loop unroll(full)
            for (uint k = 0; k < 4; ++k) {
                cg += xe[k] * ve[k];
                cg += xo[k] * vo[k];
                ag += axe[k];
                ag += axo[k];
            }
        }
        c_acc += sd * cg;
        d_acc += (0.5f * sd) * ag;
    }
    c_acc = simd_sum(c_acc);
    d_acc = simd_sum(d_acc);
    if (lane == 0) {
        coarse[row] = c_acc;
        // FP32 bound, then rounded UP to BF16 (mask-and-bump, sign clear).
        float d_up = d_acc * (1.0f + 61.0f * GAMMA);
        uint dbits = as_type<uint>(d_up);
        uint dtrunc = dbits & 0xFFFF0000u;
        if (dtrunc != dbits) {
            dtrunc += 0x00010000u;
        }
        delta[row] = as_type<bfloat>(ushort(dtrunc >> 16));
    }
    """

private let lmHeadControlKernel = MLXFast.metalKernel(
    name: "laguna_lmhead_int5_inline_coarse_ratio_bound_delta_bf16_v5_control",
    inputNames: ["x", "codes_lo", "codes_hi", "scales"],
    outputNames: ["coarse", "delta"],
    source: lmHeadControlSource,
    header: lagunaLmHeadPruneHeader,
    ensureRowContiguous: true
)

private struct LmHeadInputs {
    let x: MLXArray
    let lo: MLXArray
    let hi: MLXArray
    let scales: MLXArray
}

private enum LmHeadVariant {
    case control
    case twoRow
}

private func launchLmHead(
    _ variant: LmHeadVariant,
    inputs: LmHeadInputs,
    vocab: Int,
    verbose: Bool = false
) -> [MLXArray] {
    let arguments = [inputs.x, inputs.lo, inputs.hi, inputs.scales]
    switch variant {
    case .control:
        return lmHeadControlKernel(
            arguments,
            grid: (vocab / 16 * 512, 1, 1),
            threadGroup: (512, 1, 1),
            outputShapes: [[vocab], [vocab]],
            outputDTypes: [.float32, .bfloat16],
            verbose: verbose
        )
    case .twoRow:
        return lagunaLmHeadInt5CoarseRatioBoundDeltaBF16Kernel(
            arguments,
            grid: (vocab / 16 * 256, 1, 1),
            threadGroup: (256, 1, 1),
            outputShapes: [[vocab], [vocab]],
            outputDTypes: [.float32, .bfloat16],
            verbose: verbose
        )
    }
}

private func hiddenPattern(_ pattern: Int) -> MLXArray {
    let values: [Float] = (0..<2048).map { index in
        switch pattern {
        case 0:
            switch index % 8 {
            case 0: return 0.0
            case 1: return -0.0
            case 2: return Float(index % 17 - 8) / 64.0
            case 3: return Float(index % 13 - 6) / 16.0
            case 4: return 1.0
            case 5: return -1.0
            case 6: return 0.00390625
            default: return -0.0078125
            }
        case 1:
            let numerator = Float((index * 37 + 11) % 257 - 128)
            return numerator / Float(1 << (index % 5 + 3))
        default:
            let magnitudes: [Float] = [65_536, 32_768, 8_192, 1_024, 113, 1, 0.5, 0.00390625]
            let magnitude = magnitudes[index % magnitudes.count]
            return index.isMultiple(of: 2) ? magnitude : -magnitude
        }
    }
    return MLXArray(values).asType(.bfloat16)
}

private func exactnessInputs(vocab: Int, pattern: Int) -> LmHeadInputs {
    let lo: [UInt8] = (0..<(vocab * 1024)).map { index in
        UInt8(truncatingIfNeeded: index * 17 + (index / 1024) * 13)
    }
    let hi: [UInt8] = (0..<(vocab * 256)).map { index in
        UInt8(truncatingIfNeeded: index * 29 + (index / 256) * 7)
    }
    let scales: [UInt8] = (0..<(vocab * 64)).map { index -> UInt8 in
        let exponent = (index * 5 + (index / 64) * 3) % 12
        return UInt8(112 + exponent)
    }
    return LmHeadInputs(
        x: hiddenPattern(pattern),
        lo: MLXArray(lo, [vocab, 1024]),
        hi: MLXArray(hi, [vocab, 256]),
        scales: MLXArray(scales, [vocab, 64])
    )
}

private func timingInputs(vocab: Int) -> LmHeadInputs {
    let loRow: [UInt8] = (0..<1024).map {
        UInt8(truncatingIfNeeded: $0 * 17 + 13)
    }
    let hiRow: [UInt8] = (0..<256).map {
        UInt8(truncatingIfNeeded: $0 * 29 + 7)
    }
    let scaleRow: [UInt8] = (0..<64).map { UInt8(112 + ($0 * 5) % 12) }
    let lo = contiguous(broadcast(MLXArray(loRow, [1, 1024]), to: [vocab, 1024]))
    let hi = contiguous(broadcast(MLXArray(hiRow, [1, 256]), to: [vocab, 256]))
    let scales = contiguous(broadcast(MLXArray(scaleRow, [1, 64]), to: [vocab, 64]))
    let inputs = LmHeadInputs(x: hiddenPattern(1), lo: lo, hi: hi, scales: scales)
    eval(inputs.x, inputs.lo, inputs.hi, inputs.scales)
    return inputs
}

private func measuredSeconds(
    _ variant: LmHeadVariant,
    inputs: LmHeadInputs,
    vocab: Int
) -> Double {
    let start = Date()
    let output = launchLmHead(variant, inputs: inputs, vocab: vocab)
    eval(output[0], output[1])
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

private func timingJSON(_ values: [Double]) -> String {
    values.map { String($0) }.joined(separator: ",")
}

@Suite(.serialized)
struct LagunaLmHeadTwoRowExperimentTests {
    @Test
    func lmHeadTwoRowExactnessAgainstByteEquivalentControl() {
        guard ProcessInfo.processInfo.environment["MLXFAST_LMHEAD_TWO_ROW_GATE"] == "exactness"
        else { return }

        #expect(lmHeadControlSource.utf8.count == 2521)
        print(
            "LMHEAD_REACHABILITY control=laguna_lmhead_int5_inline_coarse_ratio_bound_delta_bf16_v5_control "
                + "candidate=laguna_lmhead_int5_inline_coarse_ratio_bound_delta_bf16_v5_two_row "
                + "control_source_bytes=2521 control_tg=512 candidate_tg=256 rows_per_tg=16"
        )
        let vocab = 48
        let boundaries = [0, 1, 14, 15, 16, 17, 30, 31, 32, 33, 46, 47]
        for pattern in 0..<3 {
            let inputs = exactnessInputs(vocab: vocab, pattern: pattern)
            let control = launchLmHead(.control, inputs: inputs, vocab: vocab)
            let candidate = launchLmHead(.twoRow, inputs: inputs, vocab: vocab)
            eval(control[0], control[1], candidate[0], candidate[1])

            let controlCoarse = control[0].view(dtype: .uint32).asArray(UInt32.self)
            let candidateCoarse = candidate[0].view(dtype: .uint32).asArray(UInt32.self)
            let controlDelta = control[1].view(dtype: .uint16).asArray(UInt16.self)
            let candidateDelta = candidate[1].view(dtype: .uint16).asArray(UInt16.self)
            #expect(controlCoarse == candidateCoarse)
            #expect(controlDelta == candidateDelta)
            for row in boundaries {
                #expect(controlCoarse[row] == candidateCoarse[row])
                #expect(controlDelta[row] == candidateDelta[row])
            }
            let coarseLast = String(format: "%08x", controlCoarse[vocab - 1])
            let deltaLast = String(format: "%04x", controlDelta[vocab - 1])
            print(
                "LMHEAD_EXACT pattern=\(pattern) rows=\(vocab) boundaries=\(boundaries) "
                    + "coarse_last=\(coarseLast) delta_last=\(deltaLast)"
            )
        }
    }

    @Test
    func lmHeadTwoRowCompilerEvidence() {
        guard ProcessInfo.processInfo.environment["MLXFAST_LMHEAD_TWO_ROW_GATE"] == "resources"
        else { return }

        let inputs = exactnessInputs(vocab: 16, pattern: 1)
        let control = launchLmHead(
            .control, inputs: inputs, vocab: 16, verbose: true)
        eval(control[0], control[1])
        let candidate = launchLmHead(
            .twoRow, inputs: inputs, vocab: 16, verbose: true)
        eval(candidate[0], candidate[1])
        print("LMHEAD_RESOURCE_REACHABILITY control_tg=512 candidate_tg=256 rows_per_tg=16")
    }

    @Test
    func lmHeadTwoRowIsolatedTimingBothOrders() {
        guard ProcessInfo.processInfo.environment["MLXFAST_LMHEAD_TWO_ROW_GATE"] == "timing"
        else { return }

        let vocab = 100_352
        let inputs = timingInputs(vocab: vocab)
        for _ in 0..<4 {
            _ = measuredSeconds(.control, inputs: inputs, vocab: vocab)
            _ = measuredSeconds(.twoRow, inputs: inputs, vocab: vocab)
        }

        var abControl: [Double] = []
        var abCandidate: [Double] = []
        var baControl: [Double] = []
        var baCandidate: [Double] = []
        for _ in 0..<24 {
            abControl.append(measuredSeconds(.control, inputs: inputs, vocab: vocab))
            abCandidate.append(measuredSeconds(.twoRow, inputs: inputs, vocab: vocab))
        }
        for _ in 0..<24 {
            baCandidate.append(measuredSeconds(.twoRow, inputs: inputs, vocab: vocab))
            baControl.append(measuredSeconds(.control, inputs: inputs, vocab: vocab))
        }

        let abControlMedian = median(abControl)
        let abCandidateMedian = median(abCandidate)
        let baControlMedian = median(baControl)
        let baCandidateMedian = median(baCandidate)
        let abSpeedup = abControlMedian / abCandidateMedian
        let baSpeedup = baControlMedian / baCandidateMedian
        print(
            "LMHEAD_TIMING {\"samples_per_order\":24,"
                + "\"warmups_per_variant\":4,\"vocab\":\(vocab),"
                + "\"ab_control_raw_s\":[\(timingJSON(abControl))],"
                + "\"ab_candidate_raw_s\":[\(timingJSON(abCandidate))],"
                + "\"ba_control_raw_s\":[\(timingJSON(baControl))],"
                + "\"ba_candidate_raw_s\":[\(timingJSON(baCandidate))],"
                + "\"ab_control_median_s\":\(abControlMedian),"
                + "\"ab_candidate_median_s\":\(abCandidateMedian),"
                + "\"ab_control_mad_s\":\(medianAbsoluteDeviation(abControl)),"
                + "\"ab_candidate_mad_s\":\(medianAbsoluteDeviation(abCandidate)),"
                + "\"ab_speedup\":\(abSpeedup),"
                + "\"ba_control_median_s\":\(baControlMedian),"
                + "\"ba_candidate_median_s\":\(baCandidateMedian),"
                + "\"ba_control_mad_s\":\(medianAbsoluteDeviation(baControl)),"
                + "\"ba_candidate_mad_s\":\(medianAbsoluteDeviation(baCandidate)),"
                + "\"ba_speedup\":\(baSpeedup)}"
        )
        #expect(abSpeedup >= 1.02)
        #expect(baSpeedup >= 1.02)
    }
}
