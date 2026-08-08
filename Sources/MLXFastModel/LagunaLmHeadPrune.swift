import Foundation
import MLX
import MLXFast

private let lagunaLmHeadPruneVocab = 100_352
private let lagunaLmHeadPruneHidden = 2048

let lagunaLmHeadPruneEnabled =
    ProcessInfo.processInfo.environment["DARKBLOOM_LM_HEAD_PRUNE"] != "0"

let lagunaLmHeadPrunePrefillEnabled = true

let lagunaLmHeadPruneHeader = """
    // e4m3fn decode, identical to fp8.h:32-38 (half bit pattern (b&127)<<7,
    // times 256, sign from bit 7). Exact in half/float for all 256 codes.
    static inline float laguna_e4m3_decode(uint8_t b) {
        half converted = as_type<half>(ushort(uint(b & 127u) << 7));
        converted = converted * (half)256.0f;
        return (b & 128u) ? -float(converted) : float(converted);
    }

    // e8m0 decode, identical to fp8.h:70-77 (bits<<7 as bf16; bits==0 ->
    // 0x40 as bf16 = 2^-127). Exponent-bit construction, exact.
    static inline float laguna_e8m0_decode(uint8_t b) {
        if (b == 0u) {
            return as_type<float>(0x00400000u);  // 2^-127
        }
        return as_type<float>(uint(b) << 23);
    }

    // Certified |ratio - code| bound for an e4m3 element: half the enclosing
    // RNE cell (denormal half-ulp 2^-10; normal half-ulp 2^(e-11)), except the
    // saturated top code 0x7E whose cell is open: the e8m0 scale may round
    // down by up to a factor 2^0.5, so ratio <= 448*2^0.5 and the bound is
    // 448*(2^0.5-1) = 185.6, rounded up to 186.
    //
    // Max-form: the denormal branch 2^-10 equals 2^(1-11), so both non-top
    // cases collapse to 2^(max(e,1)-11) -- identical float for all 256 codes
    // to the original three-branch form (e==0 -> 2^-10; e>0 -> 2^(e-11)).
    static inline float laguna_hs8(uint8_t b) {
        uint mag = uint(b) & 127u;
        uint e = mag >> 3;
        float h = as_type<float>((metal::max(e, 1u) + 116u) << 23);  // 2^(max(e,1)-11)
        return (mag == 126u) ? 186.0f : h;
    }

    // Bit-parallel e4m3 decode of one packed word (4 codes) into 4 floats.
    // Per byte b the half bit pattern is sign<<15 | (b&127)<<7, i.e. exactly
    // fp8.h's (b&127)<<7 construction with the sign applied as the half sign
    // bit instead of a post-float negate. IEEE multiply is sign-magnitude
    // symmetric, so (sign-packed half)*256h == sign*((b&127)-half * 256h)
    // bit-for-bit for every code, including -0 (code 0x80). The four decoded
    // floats are byte-order b0,b1,b2,b3 in out.x,out.y,out.z,out.w.
    static inline float4 laguna_e4m3_decode4(uint w) {
        uint lo = ((w & 0x007F007Fu) << 7) | ((w & 0x00800080u) << 8);
        uint hs = w >> 8;
        uint hi = ((hs & 0x007F007Fu) << 7) | ((hs & 0x00800080u) << 8);
        half2 h02 = as_type<half2>(lo) * half2((half)256.0f);
        half2 h13 = as_type<half2>(hi) * half2((half)256.0f);
        return float4(float(h02.x), float(h13.x), float(h02.y), float(h13.y));
    }
    """

/// Fused MXFP8 coarse GEMV + certified bound + BF16 pre-fill.
/// One simdgroup per row; lane covers 64 consecutive elements (2 groups).
///
/// v2 (H3 audit, R1): same grid, same lane->element mapping, same FP
/// accumulation text and j-order -- only the per-element decode plumbing is
/// vectorized. Word-parallel e4m3 decode (laguna_e4m3_decode4, bit-identical
/// construction), vectorized hs8 (max-form, identical floats), x loaded as
/// ushort4 and converted bf16->f32 by the exact bits<<16 construction, and
/// both loops fully unrolled with static trip counts so the packed words and
/// vector components resolve to static indices. Coarse, delta, and coarse_bf

private let lagunaLmHeadInlineCoarseRatioBoundDeltaBF16Kernel = MLXFast.metalKernel(
    name: "laguna_lmhead_mxfp8_inline_coarse_ratio_bound_delta_bf16_pack16_v1",
    inputNames: ["x", "codes", "scales"],
    outputNames: ["coarse", "delta"],
    source: """
        constexpr float GAMMA = 0x1p-15f;

        uint row = threadgroup_position_in_grid.x * 16 +
            simdgroup_index_in_threadgroup;
        uint lane = thread_index_in_simdgroup;

        const device uint8_t* crow = codes + size_t(row) * 2048;
        const device uint8_t* srow = scales + size_t(row) * 64;

        float c_acc = 0.0f;
        float d_acc = 0.0f;
        for (uint gg = 0; gg < 2; ++gg) {
            uint g = 2 * lane + gg;
            float sd = laguna_e8m0_decode(srow[g]);
            const device uint4* cptr = (const device uint4*)(crow + g * 32);
            uint4 packed0 = cptr[0];
            uint4 packed1 = cptr[1];
            float cg = 0.0f;
            float dg = 0.0f;
            const device ushort4* xrow = (const device ushort4*)(x + g * 32);
            #pragma clang loop unroll(full)
            for (uint w = 0; w < 8; ++w) {
                uint word = (w < 4u) ? packed0[w & 3u] : packed1[w & 3u];
                float4 cv4 = laguna_e4m3_decode4(word);
                float4 xv4 = as_type<float4>(uint4(xrow[w]) << 16);
                float4 ax4 = metal::abs(xv4);
                uint4 b4 = (uint4(word) >> uint4(0u, 8u, 16u, 24u)) & 255u;
                uint4 mag4 = b4 & 127u;
                uint4 e4 = mag4 >> 3;
                float4 hsf =
                    as_type<float4>((metal::max(e4, uint4(1u)) + 116u) << 23);
                float4 hs4 =
                    metal::select(hsf, float4(186.0f), mag4 == 126u);
                #pragma clang loop unroll(full)
                for (uint k = 0; k < 4; ++k) {
                    cg += xv4[k] * cv4[k];
                    dg += ax4[k] * hs4[k];
                }
            }
            c_acc += sd * cg;
            d_acc += sd * dg;
        }
        c_acc = simd_sum(c_acc);
        d_acc = simd_sum(d_acc);
        if (lane == 0) {
            coarse[row] = c_acc;
            // Same FP32 bound as the kernel above, then rounded UP to BF16.
            float d_up = d_acc * (1.0f + 61.0f * GAMMA);
            uint dbits = as_type<uint>(d_up);
            uint dtrunc = dbits & 0xFFFF0000u;
            if (dtrunc != dbits) {
                dtrunc += 0x00010000u;
            }
            delta[row] = as_type<bfloat>(ushort(dtrunc >> 16));
        }
        """,
    header: lagunaLmHeadPruneHeader,
    ensureRowContiguous: true
)

let lagunaLmHeadInt5CoarseRatioBoundDeltaBF16Kernel = MLXFast.metalKernel(
    name: "laguna_lmhead_int5_inline_coarse_ratio_bound_delta_bf16_v5_two_row",
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

private let lagunaLmHeadLowerMaxHeader = """
    static inline float laguna_lmhead_max_pair(float a, float b) {
        if (metal::isnan(a) || metal::isnan(b)) {
            return NAN;
        }
        return a > b ? a : b;
    }

    static inline float laguna_lmhead_simd_max(float value) {
        if (simd_any(value != value)) {
            return NAN;
        }
        return simd_max(value);
    }
    """

private let lagunaLmHeadLowerMaxStage1DeltaBF16Kernel = MLXFast.metalKernel(
    name: "laguna_lmhead_lower_max_stage1_delta_bf16_v1",
    inputNames: ["coarse", "delta"],
    outputNames: ["partial_max"],
    source: """
        constexpr uint ROW_SIZE = 784;
        constexpr uint READS = 4;
        constexpr uint ACTIVE_THREADS = ROW_SIZE / READS;
        constexpr uint SIMD_GROUPS = 7;

        uint row = threadgroup_position_in_grid.y;
        uint lid = thread_position_in_threadgroup.x;
        uint simd_lane = thread_index_in_simdgroup;
        uint simd_group = simdgroup_index_in_threadgroup;
        threadgroup float shared_vals[32];

        float total = -metal::numeric_limits<float>::infinity();
        if (lid < ACTIVE_THREADS) {
            uint base = row * ROW_SIZE + lid * READS;
            #pragma clang loop unroll(full)
            for (uint i = 0; i < READS; ++i) {
                float lower = coarse[base + i] - float(delta[base + i]);
                total = laguna_lmhead_max_pair(lower, total);
            }
        }

        total = laguna_lmhead_simd_max(total);
        if (simd_lane == 0) {
            shared_vals[simd_group] = total;
        }

        threadgroup_barrier(mem_flags::mem_threadgroup);
        total = lid < SIMD_GROUPS
            ? shared_vals[lid]
            : -metal::numeric_limits<float>::infinity();
        total = laguna_lmhead_simd_max(total);
        if (lid == 0) {
            partial_max[row] = total;
        }
        """,
    header: lagunaLmHeadLowerMaxHeader,
    ensureRowContiguous: true
)

private let lagunaLmHeadLowerMaxThresholdKernel = MLXFast.metalKernel(
    name: "laguna_lmhead_lower_max_threshold_v1",
    inputNames: ["partial_max"],
    outputNames: ["threshold"],
    source: """
        constexpr uint READS = 4;
        uint lid = thread_position_in_threadgroup.x;
        threadgroup float rounded_beta[1];

        float total = -metal::numeric_limits<float>::infinity();
        uint base = lid * READS;
        #pragma clang loop unroll(full)
        for (uint i = 0; i < READS; ++i) {
            total = laguna_lmhead_max_pair(partial_max[base + i], total);
        }
        total = laguna_lmhead_simd_max(total);

        if (lid == 0) {
            rounded_beta[0] = metal::abs(total) * 0x1p-6f;
        }
        threadgroup_barrier(mem_flags::mem_threadgroup);
        if (lid == 0) {
            threshold[0] = total - rounded_beta[0];
        }
        """,
    header: lagunaLmHeadLowerMaxHeader,
    ensureRowContiguous: true
)

/// v5 stage one: partial ARGMAX of `coarse` (value + index), replacing the
/// lower-max stage one on the v5 arm. Same launch shape and read partition
/// as the stock two-pass reduction (grid (224, 128), threadgroup (224, 1),
/// four consecutive values per active thread, 784-element partitions), so
/// its byte traffic is the stage-one kernel's minus the whole `delta` read
/// -- the exact-winner threshold does not consume `L`, so `coarse - delta`
/// is never formed and `delta`'s only remaining reader is the exact pass.
///
/// The reduction carries (value, index) pairs: value primary, LOWEST index
/// on ties, making the selected row deterministic for any input. NaN coarse
/// values lose every `>` comparison and are skipped (no `laguna_lmhead_
/// max_pair` NaN propagation here) -- correctness never depends on WHICH row
/// wins: the exact-winner threshold is sound for ANY row index (see the
/// threshold kernel below), so argmax quality only affects the candidate

private let lagunaLmHeadCoarseArgmaxStage1Kernel = MLXFast.metalKernel(
    name: "laguna_lmhead_coarse_argmax_stage1_v5",
    inputNames: ["coarse"],
    outputNames: ["partial_max", "partial_idx"],
    source: """
        constexpr uint ROW_SIZE = 784;
        constexpr uint READS = 4;
        constexpr uint ACTIVE_THREADS = ROW_SIZE / READS;
        constexpr uint SIMD_GROUPS = 7;

        uint row = threadgroup_position_in_grid.y;
        uint lid = thread_position_in_threadgroup.x;
        uint simd_lane = thread_index_in_simdgroup;
        uint simd_group = simdgroup_index_in_threadgroup;
        threadgroup float shared_vals[32];
        threadgroup uint shared_idxs[32];

        float best = -metal::numeric_limits<float>::infinity();
        uint best_idx = 0xFFFFFFFFu;
        if (lid < ACTIVE_THREADS) {
            uint base = row * ROW_SIZE + lid * READS;
            #pragma clang loop unroll(full)
            for (uint i = 0; i < READS; ++i) {
                float v = coarse[base + i];
                if (v > best || (v == best && base + i < best_idx)) {
                    best = v;
                    best_idx = base + i;
                }
            }
        }

        #pragma clang loop unroll(full)
        for (ushort sn = 16; sn >= 1; sn >>= 1) {
            float ov = simd_shuffle_down(best, sn);
            uint oi = simd_shuffle_down(best_idx, sn);
            if (ov > best || (ov == best && oi < best_idx)) {
                best = ov;
                best_idx = oi;
            }
        }
        if (simd_lane == 0) {
            shared_vals[simd_group] = best;
            shared_idxs[simd_group] = best_idx;
        }

        threadgroup_barrier(mem_flags::mem_threadgroup);
        best = lid < SIMD_GROUPS
            ? shared_vals[lid]
            : -metal::numeric_limits<float>::infinity();
        best_idx = lid < SIMD_GROUPS ? shared_idxs[lid] : 0xFFFFFFFFu;
        #pragma clang loop unroll(full)
        for (ushort sn = 16; sn >= 1; sn >>= 1) {
            float ov = simd_shuffle_down(best, sn);
            uint oi = simd_shuffle_down(best_idx, sn);
            if (ov > best || (ov == best && oi < best_idx)) {
                best = ov;
                best_idx = oi;
            }
        }
        if (lid == 0) {
            partial_max[row] = best;
            partial_idx[row] = best_idx;
        }
        """,
    ensureRowContiguous: true
)

private let lagunaLmHeadExactWinnerBF16PredecessorThresholdKernel = MLXFast.metalKernel(
    name: "laguna_lmhead_exact_winner_bf16_midpoint_threshold_v1",
    inputNames: ["partial_max", "partial_idx", "lm_head", "x"],
    outputNames: ["threshold"],
    source: """
        constexpr uint VOCAB = 100352;
        constexpr uint K = 2048;
        constexpr uint READS = 4;
        uint lid = thread_position_in_threadgroup.x;
        threadgroup uint winner_row[1];

        // Verbatim final argmax over the retained 128 partials.
        float best = -metal::numeric_limits<float>::infinity();
        uint best_idx = 0xFFFFFFFFu;
        uint base = lid * READS;
        #pragma clang loop unroll(full)
        for (uint i = 0; i < READS; ++i) {
            float v = partial_max[base + i];
            uint idx = partial_idx[base + i];
            if (v > best || (v == best && idx < best_idx)) {
                best = v;
                best_idx = idx;
            }
        }
        #pragma clang loop unroll(full)
        for (ushort sn = 16; sn >= 1; sn >>= 1) {
            float ov = simd_shuffle_down(best, sn);
            uint oi = simd_shuffle_down(best_idx, sn);
            if (ov > best || (ov == best && oi < best_idx)) {
                best = ov;
                best_idx = oi;
            }
        }
        if (lid == 0) {
            winner_row[0] = metal::min(best_idx, uint(VOCAB - 1));
        }
        threadgroup_barrier(mem_flags::mem_threadgroup);
        uint r = winner_row[0];

        // --- stock gemv_al replica begin (single row r; gemv.h:151-289) ---
        float result = 0.0f;
        thread bfloat inter[4];
        thread float v_coeff[4];
        uint bn = lid * 4;
        const device bfloat* mrow = lm_head + size_t(r) * K;
        for (uint i = 0; i < 16; ++i) {
            vec<bfloat, 4> xv =
                *((const device vec<bfloat, 4>*)(x + bn));
            v_coeff[0] = float(xv.x);
            v_coeff[1] = float(xv.y);
            v_coeff[2] = float(xv.z);
            v_coeff[3] = float(xv.w);
            vec<bfloat, 4> mv =
                *((const device vec<bfloat, 4>*)(mrow + bn));
            inter[0] = mv.x;
            inter[1] = mv.y;
            inter[2] = mv.z;
            inter[3] = mv.w;
            result += inter[0] * v_coeff[0];
            result += inter[1] * v_coeff[1];
            result += inter[2] * v_coeff[2];
            result += inter[3] * v_coeff[3];
            bn += 128;
        }
        #pragma unroll
        for (ushort sn = 16; sn >= 1; sn >>= 1) {
            result += simd_shuffle_down(result, sn);
        }
        // --- stock gemv_al replica end ---
        if (lid == 0) {
            bfloat rounded = bfloat(result);
            // Expand through the numeric BF16->FP32 conversion, whose bits are
            // exactly `bf16_bits << 16`; do not reinterpret the Metal wrapper.
            ushort bits = ushort(as_type<uint>(float(rounded)) >> 16);
            ushort magnitude = bits & 0x7FFFu;
            ushort predecessor_bits;
            if (magnitude == 0u) {
                predecessor_bits = 0x8001u;  // predecessor of either zero
            } else if ((bits & 0x8000u) == 0u) {
                predecessor_bits = bits - 1u;
            } else {
                predecessor_bits = bits + 1u;
            }
            float predecessor =
                as_type<float>(uint(predecessor_bits) << 16);
            if (true) {
                float rounded_value = as_type<float>(uint(bits) << 16);
                threshold[0] = predecessor +
                    (rounded_value - predecessor) * 0.5f;
            } else {
                threshold[0] = predecessor;
            }
        }
        """,
    ensureRowContiguous: true
)

private let lagunaLmHeadInlineExactDeltaBF16Kernel = MLXFast.metalKernel(
    name: "laguna_lmhead_exact_inline_mask_block_delta_bf16_lane0_mask_v1",
    inputNames: ["coarse", "delta", "thr", "lm_head", "x"],
    outputNames: ["assembled"],
    source: """
        constexpr uint VOCAB = 100352;
        constexpr uint K = 2048;

        uint tgid = threadgroup_position_in_grid.x;
        uint sgid = simdgroup_index_in_threadgroup;
        uint lane = thread_index_in_simdgroup;

        // This simdgroup's fixed four output rows. VOCAB is 3136 * 32, so the
        // grid tiles it exactly; the bounds test is belt-and-braces.
        uint base = tgid * 32 + sgid * 4;

        // The predicate is simdgroup-uniform, so lane 0 forms it once and
        // broadcasts the four row decisions. Reusing the mask below removes
        // the same coarse/delta/threshold reads from the final write path.
        uint candidate_mask = 0;
        if (lane == 0) {
            #pragma unroll
            for (uint tm = 0; tm < 4; ++tm) {
                uint r = base + tm;
                if (r < VOCAB && coarse[r] + float(delta[r]) >= thr[0]) {
                    candidate_mask |= 1u << tm;
                }
            }
        }
        candidate_mask = simd_broadcast(candidate_mask, 0);

        if (candidate_mask == 0) {
            if (lane < 4 && base + lane < VOCAB) {
                assembled[base + lane] = bfloat(coarse[base + lane]);
            }
            return;
        }

        // --- stock gemv_al replica begin (gemv.h:151-289) ---
        thread float result[4] = {0.0f, 0.0f, 0.0f, 0.0f};
        thread bfloat inter[4];
        thread float v_coeff[4];
        uint bn = lane * 4;
        for (uint i = 0; i < 16; ++i) {
            vec<bfloat, 4> xv =
                *((const device vec<bfloat, 4>*)(x + bn));
            v_coeff[0] = float(xv.x);
            v_coeff[1] = float(xv.y);
            v_coeff[2] = float(xv.z);
            v_coeff[3] = float(xv.w);
            #pragma unroll
            for (uint tm = 0; tm < 4; ++tm) {
                const device bfloat* mrow = lm_head + size_t(base + tm) * K;
                vec<bfloat, 4> mv =
                    *((const device vec<bfloat, 4>*)(mrow + bn));
                inter[0] = mv.x;
                inter[1] = mv.y;
                inter[2] = mv.z;
                inter[3] = mv.w;
                result[tm] += inter[0] * v_coeff[0];
                result[tm] += inter[1] * v_coeff[1];
                result[tm] += inter[2] * v_coeff[2];
                result[tm] += inter[3] * v_coeff[3];
            }
            bn += 128;
        }
        #pragma unroll
        for (uint tm = 0; tm < 4; ++tm) {
            #pragma unroll
            for (ushort sn = 16; sn >= 1; sn >>= 1) {
                result[tm] += simd_shuffle_down(result[tm], sn);
            }
        }
        // --- stock gemv_al replica end ---
        if (lane == 0) {
            #pragma unroll
            for (uint tm = 0; tm < 4; ++tm) {
                uint r = base + tm;
                if (r < VOCAB) {
                    assembled[r] = (candidate_mask & (1u << tm)) != 0
                        ? bfloat(result[tm])
                        : bfloat(coarse[r]);
                }
            }
        }
        """,
    ensureRowContiguous: true
)

final class LagunaLmHeadPruner {
    let codes: MLXArray?
    let scales: MLXArray?
    let int5CodesLo: MLXArray?
    let int5CodesHi: MLXArray?
    let int5Scales: MLXArray?

    var residentArrays: [MLXArray] {
        if let lo = int5CodesLo, let hi = int5CodesHi, let scales = int5Scales {
            return [lo, hi, scales]
        }
        return [codes, scales].compactMap { $0 }
    }

    init?(lmHeadWeight: MLXArray) {
        guard lmHeadWeight.shape == [lagunaLmHeadPruneVocab, lagunaLmHeadPruneHidden],
            lmHeadWeight.dtype == .bfloat16
        else {
            FileHandle.standardError.write(
                Data("mlxfast: lm_head prune: unrecognized lm_head shape/dtype; disabled\n".utf8))
            return nil
        }

        if let planes = LagunaLmHeadPruner.buildInt5Planes(lmHeadWeight) {
            self.int5CodesLo = planes.lo
            self.int5CodesHi = planes.hi
            self.int5Scales = planes.scales
            self.codes = nil
            self.scales = nil
            return
        }

        self.int5CodesLo = nil
        self.int5CodesHi = nil
        self.int5Scales = nil
        let (quantizedWeight, quantizedScales, _) = quantized(
            lmHeadWeight, groupSize: 32, bits: 8, mode: .mxfp8)
        self.codes = quantizedWeight.view(dtype: .uint8)
        self.scales = quantizedScales
    }

    private static func buildInt5Planes(
        _ lmHeadWeight: MLXArray
    ) -> (lo: MLXArray, hi: MLXArray, scales: MLXArray)? {
        let vocab = lagunaLmHeadPruneVocab
        let hidden = lagunaLmHeadPruneHidden
        let w = lmHeadWeight.asType(.float32).reshaped([vocab, hidden / 32, 32])
        let gmax = MLX.abs(w).max(axis: 2)  // [V, 64] float32, contiguous
        let gbits = gmax.view(dtype: .uint32)
        let biasedE = (gbits >> 23).asType(.int32)
        let mant = gbits & MLXArray(UInt32(0x007F_FFFF))
        // bump when mantissa >= 0.9375 * 2^23 (i.e. m >= 15.5/8).
        let bump = (mant .>= MLXArray(UInt32(0x78_0000))).asType(.int32)
        let sdByte = clip(biasedE - 3 + bump, min: 0, max: 255)
        let sd = which(
            sdByte .== 0,
            MLXArray(Float(bitPattern: 0x0040_0000)),  // 2^-127, e8m0 semantics
            (sdByte.asType(.uint32) << 23).view(dtype: .float32))
        let q = (w / sd.expandedDimensions(axis: 2)).round()
        // Init-time certificate guard: no code may leave [-15, 15]. The
        // kernel's m <= 30*d ratio bound assumes |q| <= 15 (u in [1, 31]).
        let maxCode = MLX.abs(q).max().item(Float.self)
        guard maxCode <= 15.0 else {
            FileHandle.standardError.write(
                Data(
                    "mlxfast: lm_head coarse v5: int5 code overflow (\(maxCode)); using v4/MXFP8\n"
                        .utf8))
            return nil
        }
        // Offset-binary u = q + 16 in [1, 31]; planar-pack 4+1 bits.
        let u = (q + 16).asType(.uint8).reshaped([vocab, hidden])
        let u16 = u.view(dtype: .uint16)  // [V, 1024]: elem 2b low byte
        let lo =
            ((u16 & MLXArray(UInt16(0x000F)))
            | ((u16 >> 4) & MLXArray(UInt16(0x00F0)))).asType(.uint8)
        // 1-bit plane: bit 4 of each code; element j of each 32-element
        // group lands at bit j of the group's little-endian uint32 word.
        // Step 1: per uint32 word of u (4 codes), gather the four bit-4s
        // (u32 bits 4, 12, 20, 28) into one low nibble.
        let u32 = u.view(dtype: .uint32)  // [V, 512]: elem 4t..4t+3
        let nib =
            (((u32 >> 4) & MLXArray(UInt32(0x01)))
            | ((u32 >> 11) & MLXArray(UInt32(0x02)))
            | ((u32 >> 18) & MLXArray(UInt32(0x04)))
            | ((u32 >> 25) & MLXArray(UInt32(0x08)))).asType(.uint8)
        // Step 2: merge nibble pairs into bytes (byte s = elements 8s..8s+7).
        let nib16 = nib.view(dtype: .uint16)  // [V, 256]
        let hi =
            ((nib16 & MLXArray(UInt16(0x000F)))
            | ((nib16 >> 4) & MLXArray(UInt16(0x00F0)))).asType(.uint8)
        return (lo, hi, sdByte.asType(.uint8))
    }


    func logits(hidden: MLXArray, lmHeadWeight: MLXArray) -> MLXArray {
        precondition(hidden.dtype == .bfloat16 && hidden.size == lagunaLmHeadPruneHidden)
        let vocab = lagunaLmHeadPruneVocab
        let x = hidden.reshaped([lagunaLmHeadPruneHidden])

        if let lo = int5CodesLo, let hi = int5CodesHi, let scales = int5Scales {
            let coarseOutput = lagunaLmHeadInt5CoarseRatioBoundDeltaBF16Kernel(
                [x, lo, hi, scales],
                grid: (vocab / 16 * 256, 1, 1),
                threadGroup: (256, 1, 1),
                outputShapes: [[vocab], [vocab]],
                outputDTypes: [.float32, .bfloat16]
            )
            let coarse = coarseOutput[0]
            let delta = coarseOutput[1]
            let argmaxPartials = lagunaLmHeadCoarseArgmaxStage1Kernel(
                [coarse],
                grid: (224, 128, 1),
                threadGroup: (224, 1, 1),
                outputShapes: [[128], [128]],
                outputDTypes: [.float32, .uint32]
            )
            let threshold = lagunaLmHeadExactWinnerBF16PredecessorThresholdKernel(
                [argmaxPartials[0], argmaxPartials[1], lmHeadWeight, x],
                grid: (32, 1, 1),
                threadGroup: (32, 1, 1),
                outputShapes: [[1]],
                outputDTypes: [.float32]
            )[0]
            let assembled = lagunaLmHeadInlineExactDeltaBF16Kernel(
                [coarse, delta, threshold, lmHeadWeight, x],
                grid: (vocab / 32 * 256, 1, 1),
                threadGroup: (256, 1, 1),
                outputShapes: [[vocab]],
                outputDTypes: [.bfloat16]
            )[0]
            return assembled.reshaped([1, 1, vocab])
        }

        let coarseOutput = lagunaLmHeadInlineCoarseRatioBoundDeltaBF16Kernel(
            [x, codes!, scales!],
            grid: (vocab / 16 * 512, 1, 1),
            threadGroup: (512, 1, 1),
            outputShapes: [[vocab], [vocab]],
            outputDTypes: [.float32, .bfloat16]
        )
        let coarse = coarseOutput[0]
        let delta = coarseOutput[1]
        let lowerMaxPartials = lagunaLmHeadLowerMaxStage1DeltaBF16Kernel(
            [coarse, delta],
            grid: (224, 128, 1),
            threadGroup: (224, 1, 1),
            outputShapes: [[128]],
            outputDTypes: [.float32]
        )[0]
        let threshold = lagunaLmHeadLowerMaxThresholdKernel(
            [lowerMaxPartials],
            grid: (32, 1, 1),
            threadGroup: (32, 1, 1),
            outputShapes: [[1]],
            outputDTypes: [.float32]
        )[0]
        let assembled = lagunaLmHeadInlineExactDeltaBF16Kernel(
            [coarse, delta, threshold, lmHeadWeight, x],
            grid: (vocab / 32 * 256, 1, 1),
            threadGroup: (256, 1, 1),
            outputShapes: [[vocab]],
            outputDTypes: [.bfloat16]
        )[0]
        return assembled.reshaped([1, 1, vocab])
    }
}
