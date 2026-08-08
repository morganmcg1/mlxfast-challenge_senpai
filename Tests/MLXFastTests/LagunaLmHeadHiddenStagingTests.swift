import Foundation
import MLX
import MLXFast
import Testing
@testable import MLXFastModel

private let lmHeadStagingVocab = 100_352
private let lmHeadStagingHidden = 2_048

private let lmHeadCoarseBaselineKernel = MLXFast.metalKernel(
    name: "laguna_lmhead_int5_inline_coarse_ratio_bound_delta_bf16_v5_two_row_baseline_oracle",
    inputNames: ["x", "codes_lo", "codes_hi", "scales"],
    outputNames: ["coarse", "delta"],
    source: """
        constexpr float GAMMA = 0x1p-15f;

        uint row0 = threadgroup_position_in_grid.x * 16 +
            2 * simdgroup_index_in_threadgroup;
        uint row1 = row0 + 1;
        uint lane = thread_index_in_simdgroup;

        const device uint8_t* lorow0 = codes_lo + size_t(row0) * 1024;
        const device uint8_t* lorow1 = lorow0 + 1024;
        const device uint8_t* hirow0 = codes_hi + size_t(row0) * 256;
        const device uint8_t* hirow1 = hirow0 + 256;
        const device uint8_t* srow0 = scales + size_t(row0) * 64;
        const device uint8_t* srow1 = srow0 + 64;

        float c_acc0 = 0.0f;
        float d_acc0 = 0.0f;
        float c_acc1 = 0.0f;
        float d_acc1 = 0.0f;
        for (uint gg = 0; gg < 2; ++gg) {
            uint g = 2 * lane + gg;
            float sd0 = laguna_e8m0_decode(srow0[g]);
            float sd1 = laguna_e8m0_decode(srow1[g]);
            uint4 lo40 = ((const device uint4*)(lorow0 + g * 16))[0];
            uint4 lo41 = ((const device uint4*)(lorow1 + g * 16))[0];
            uint hb0 = ((const device uint*)(hirow0 + g * 4))[0];
            uint hb1 = ((const device uint*)(hirow1 + g * 4))[0];
            const device ushort4* xrow = (const device ushort4*)(x + g * 32);
            float cg0 = 0.0f;
            float cg1 = 0.0f;
            float ag = 0.0f;
            #pragma clang loop unroll(full)
            for (uint w = 0; w < 4; ++w) {
                uint lw0 = lo40[w];
                uint hw0 = hb0 >> (8u * w);
                uint4 ne0 = (uint4(lw0) >> uint4(0u, 8u, 16u, 24u)) & 15u;
                uint4 no0 = (uint4(lw0) >> uint4(4u, 12u, 20u, 28u)) & 15u;
                uint4 he0 = (uint4(hw0) >> uint4(0u, 2u, 4u, 6u)) & 1u;
                uint4 ho0 = (uint4(hw0) >> uint4(1u, 3u, 5u, 7u)) & 1u;
                float4 ve0 = float4(ne0 | (he0 << 4u)) - 16.0f;
                float4 vo0 = float4(no0 | (ho0 << 4u)) - 16.0f;

                float4 xa = as_type<float4>(uint4(xrow[2 * w]) << 16);
                float4 xb = as_type<float4>(uint4(xrow[2 * w + 1]) << 16);
                float4 xe = float4(xa.x, xa.z, xb.x, xb.z);
                float4 xo = float4(xa.y, xa.w, xb.y, xb.w);
                float4 axe = metal::abs(xe);
                float4 axo = metal::abs(xo);
                #pragma clang loop unroll(full)
                for (uint k = 0; k < 4; ++k) {
                    cg0 += xe[k] * ve0[k];
                    cg0 += xo[k] * vo0[k];
                    ag += axe[k];
                    ag += axo[k];
                }

                uint lw1 = lo41[w];
                uint hw1 = hb1 >> (8u * w);
                uint4 ne1 = (uint4(lw1) >> uint4(0u, 8u, 16u, 24u)) & 15u;
                uint4 no1 = (uint4(lw1) >> uint4(4u, 12u, 20u, 28u)) & 15u;
                uint4 he1 = (uint4(hw1) >> uint4(0u, 2u, 4u, 6u)) & 1u;
                uint4 ho1 = (uint4(hw1) >> uint4(1u, 3u, 5u, 7u)) & 1u;
                float4 ve1 = float4(ne1 | (he1 << 4u)) - 16.0f;
                float4 vo1 = float4(no1 | (ho1 << 4u)) - 16.0f;
                #pragma clang loop unroll(full)
                for (uint k = 0; k < 4; ++k) {
                    cg1 += xe[k] * ve1[k];
                    cg1 += xo[k] * vo1[k];
                }
            }
            c_acc0 += sd0 * cg0;
            d_acc0 += (0.5f * sd0) * ag;
            c_acc1 += sd1 * cg1;
            d_acc1 += (0.5f * sd1) * ag;
        }
        c_acc0 = simd_sum(c_acc0);
        d_acc0 = simd_sum(d_acc0);
        if (lane == 0) {
            coarse[row0] = c_acc0;
            float d_up0 = d_acc0 * (1.0f + 61.0f * GAMMA);
            uint dbits0 = as_type<uint>(d_up0);
            uint dtrunc0 = dbits0 & 0xFFFF0000u;
            if (dtrunc0 != dbits0) {
                dtrunc0 += 0x00010000u;
            }
            delta[row0] = as_type<bfloat>(ushort(dtrunc0 >> 16));
        }
        c_acc1 = simd_sum(c_acc1);
        d_acc1 = simd_sum(d_acc1);
        if (lane == 0) {
            coarse[row1] = c_acc1;
            float d_up1 = d_acc1 * (1.0f + 61.0f * GAMMA);
            uint dbits1 = as_type<uint>(d_up1);
            uint dtrunc1 = dbits1 & 0xFFFF0000u;
            if (dtrunc1 != dbits1) {
                dtrunc1 += 0x00010000u;
            }
            delta[row1] = as_type<bfloat>(ushort(dtrunc1 >> 16));
        }
        """,
    header: lagunaLmHeadPruneHeader,
    ensureRowContiguous: true
)

private struct LmHeadStagingInputs {
    let hidden: MLXArray
    let codesLo: MLXArray
    let codesHi: MLXArray
    let scales: MLXArray
}

private struct LmHeadStagingBits {
    var coarse: [UInt32]
    var delta: [UInt16]
}

private typealias LmHeadStagingLaunch = (LmHeadStagingInputs) -> [MLXArray]

private func baselineLaunch(_ inputs: LmHeadStagingInputs) -> [MLXArray] {
    launchLmHeadStagingKernel(lmHeadCoarseBaselineKernel, inputs: inputs)
}

private func stagedLaunch(_ inputs: LmHeadStagingInputs) -> [MLXArray] {
    launchLmHeadStagingKernel(
        lagunaLmHeadInt5CoarseRatioBoundDeltaBF16Kernel,
        inputs: inputs
    )
}

@Test
func lmHeadHiddenStagingMatchesBaselineBitwiseWhenRuntimeTestsAreEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
        return
    }

    let randomInputs = makeRandomLmHeadStagingInputs()
    let adversarialInputs = makeAdversarialLmHeadStagingInputs()
    var randomCandidateBits: LmHeadStagingBits?

    for (label, inputs) in [
        ("random", randomInputs),
        ("adversarial", adversarialInputs),
    ] {
        let baselineBits = outputBits(baselineLaunch(inputs))
        let candidateBits = outputBits(stagedLaunch(inputs))
        #expect(outputsMatch(baselineBits, candidateBits))
        print(
            "LMHEAD_HIDDEN_STAGING_ORACLE label=\(label) coarse_bits=\(baselineBits.coarse.count) delta_bits=\(baselineBits.delta.count) exact=true"
        )
        if label == "random" {
            randomCandidateBits = candidateBits
        }
    }

    var corrupted = randomCandidateBits!
    corrupted.coarse[corrupted.coarse.count / 2] ^= 1
    #expect(!outputsMatch(outputBits(baselineLaunch(randomInputs)), corrupted))
    print("LMHEAD_HIDDEN_STAGING_ORACLE positive_corruption_detected=true")
}

@Test
func lmHeadHiddenStagingHasMirroredIsolatedSpeedupWhenRuntimeTestsAreEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
        return
    }

    let inputs = makeRandomLmHeadStagingInputs()
    for _ in 0..<3 {
        eval(baselineLaunch(inputs))
        eval(stagedLaunch(inputs))
    }

    let iterations = Int(
        ProcessInfo.processInfo.environment["MLXFAST_LMHEAD_STAGING_ITERATIONS"] ?? "128"
    ) ?? 128
    let baselineAB = measureLmHeadStagingKernel(
        baselineLaunch,
        inputs: inputs,
        iterations: iterations
    )
    let stagedAB = measureLmHeadStagingKernel(
        stagedLaunch,
        inputs: inputs,
        iterations: iterations
    )
    let stagedBA = measureLmHeadStagingKernel(
        stagedLaunch,
        inputs: inputs,
        iterations: iterations
    )
    let baselineBA = measureLmHeadStagingKernel(
        baselineLaunch,
        inputs: inputs,
        iterations: iterations
    )
    let speedupAB = baselineAB / stagedAB
    let speedupBA = baselineBA / stagedBA

    print(
        "LMHEAD_HIDDEN_STAGING_TIMING iterations=\(iterations) baseline_ab_s=\(baselineAB) staged_ab_s=\(stagedAB) speedup_ab=\(speedupAB) staged_ba_s=\(stagedBA) baseline_ba_s=\(baselineBA) speedup_ba=\(speedupBA)"
    )
    #expect(speedupAB >= 1.005)
    #expect(speedupBA >= 1.005)
}

private func launchLmHeadStagingKernel(
    _ kernel: MLXFast.MLXFastKernel,
    inputs: LmHeadStagingInputs
) -> [MLXArray] {
    kernel(
        [inputs.hidden, inputs.codesLo, inputs.codesHi, inputs.scales],
        grid: (lmHeadStagingVocab / 16 * 256, 1, 1),
        threadGroup: (256, 1, 1),
        outputShapes: [[lmHeadStagingVocab], [lmHeadStagingVocab]],
        outputDTypes: [.float32, .bfloat16]
    )
}

private func makeRandomLmHeadStagingInputs() -> LmHeadStagingInputs {
    let hiddenBits = (0..<lmHeadStagingHidden).map { index -> UInt16 in
        let sign = UInt16(index & 1) << 15
        let exponent = UInt16(121 + (index * 17) % 13) << 7
        let mantissa = UInt16((index * 73 + 19) & 0x7f)
        return sign | exponent | mantissa
    }
    let hidden = MLXArray(hiddenBits, [lmHeadStagingHidden])
        .view(dtype: .bfloat16)
        .contiguous()
    let codesLo = MLXRandom.randInt(
        UInt8(0)..<UInt8.max,
        [lmHeadStagingVocab, 1_024],
        key: MLXRandom.key(0x1234)
    ).contiguous()
    let codesHi = MLXRandom.randInt(
        UInt8(0)..<UInt8.max,
        [lmHeadStagingVocab, 256],
        key: MLXRandom.key(0x5678)
    ).contiguous()
    let scales = MLXRandom.randInt(
        UInt8(118)..<UInt8(136),
        [lmHeadStagingVocab, 64],
        key: MLXRandom.key(0x9abc)
    ).contiguous()
    eval(hidden, codesLo, codesHi, scales)
    return LmHeadStagingInputs(
        hidden: hidden,
        codesLo: codesLo,
        codesHi: codesHi,
        scales: scales
    )
}

private func makeAdversarialLmHeadStagingInputs() -> LmHeadStagingInputs {
    let pattern: [UInt16] = [
        0x0000, 0x8000, 0x0001, 0x8001,
        0x3f00, 0xbf00, 0x3f80, 0xbf80,
        0x4000, 0xc000, 0x7f7f, 0xff7f,
        0x0080, 0x8080, 0x3f7f, 0xbf7f,
    ]
    let hiddenBits = (0..<lmHeadStagingHidden).map { pattern[$0 % pattern.count] }
    let hidden = MLXArray(hiddenBits, [lmHeadStagingHidden])
        .view(dtype: .bfloat16)
        .contiguous()
    let codesLo = MLXArray.full(
        [lmHeadStagingVocab, 1_024],
        values: MLXArray(UInt8(0xa5)),
        dtype: .uint8
    )
    let codesHi = MLXArray.full(
        [lmHeadStagingVocab, 256],
        values: MLXArray(UInt8(0x5a)),
        dtype: .uint8
    )
    let scales = MLXArray.full(
        [lmHeadStagingVocab, 64],
        values: MLXArray(UInt8(0)),
        dtype: .uint8
    )
    eval(hidden, codesLo, codesHi, scales)
    return LmHeadStagingInputs(
        hidden: hidden,
        codesLo: codesLo,
        codesHi: codesHi,
        scales: scales
    )
}

private func outputBits(_ outputs: [MLXArray]) -> LmHeadStagingBits {
    eval(outputs)
    return LmHeadStagingBits(
        coarse: outputs[0].view(dtype: .uint32).asArray(UInt32.self),
        delta: outputs[1].view(dtype: .uint16).asArray(UInt16.self)
    )
}

private func outputsMatch(_ lhs: LmHeadStagingBits, _ rhs: LmHeadStagingBits) -> Bool {
    lhs.coarse == rhs.coarse && lhs.delta == rhs.delta
}

private func measureLmHeadStagingKernel(
    _ launch: LmHeadStagingLaunch,
    inputs: LmHeadStagingInputs,
    iterations: Int
) -> Double {
    var outputs = [MLXArray]()
    outputs.reserveCapacity(iterations * 2)
    for _ in 0..<iterations {
        outputs.append(contentsOf: launch(inputs))
    }
    let start = DispatchTime.now().uptimeNanoseconds
    eval(outputs)
    let elapsed = DispatchTime.now().uptimeNanoseconds - start
    return Double(elapsed) / 1_000_000_000.0
}
