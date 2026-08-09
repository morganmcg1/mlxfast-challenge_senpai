import MLX
import MLXFast

private let lagunaFullPairGateAttentionKernel = MLXFast.metalKernel(
    name: "laguna_full_fused_attn_grow_pair_gate_v1",
    inputNames: [
        "raw_queries", "raw_keys", "raw_values",
        "query_weight", "key_weight", "angles",
        "k_cache", "v_cache", "params", "scale_arr",
    ],
    outputNames: ["attended"],
    source: """
        constexpr uint head_dim = 128;
        constexpr uint gqa = 6;
        constexpr int BN = 32;
        constexpr int BD = 32;
        constexpr int qk_per_thread = 4;
        constexpr int v_per_thread = 4;
        constexpr uint rotary_pairs = 32;
        constexpr float yarn_mscale = 1.3465735912322998f;

        typedef float U;

        uint pair_tg = threadgroup_position_in_grid.x;
        uint head0 = pair_tg * 2;
        uint head1 = head0 + 1;
        uint kv_head = head0 / gqa;
        uint sg = simdgroup_index_in_threadgroup;
        uint lane = thread_index_in_simdgroup;
        uint widx = params[0];
        int N = int(params[1]);
        uint capacity = params[2];
        float scale = scale_arr[0];

        threadgroup bfloat tg_q0[head_dim];
        threadgroup bfloat tg_q1[head_dim];
        threadgroup bfloat tg_k[head_dim];
        threadgroup bfloat tg_v[head_dim];

        // Phase 1: per-head RMSNorm + partial YaRN RoPE, textual replica of
        // laguna_full_qk_norm_yarn_bf16_128_v4 with the device row writes
        // retargeted at threadgroup memory.
        if (sg < 3) {
            const device bfloat* input =
                sg == 0 ? raw_queries + head0 * head_dim
                : sg == 1 ? raw_queries + head1 * head_dim
                          : raw_keys + kv_head * head_dim;
            const device bfloat* weight =
                sg == 2 ? key_weight : query_weight;
            threadgroup bfloat* outrow =
                sg == 0 ? tg_q0 : sg == 1 ? tg_q1 : tg_k;

            uint base = lane * 4;
            thread bfloat normalized[4];
            float sum = 0.0f;
            for (uint i = 0; i < 4; ++i) {
                float value = float(input[base + i]);
                sum += value * value;
            }
            sum = simd_sum(sum);
            float inverse_rms = metal::precise::rsqrt(sum / 128.0f + 1.0e-6f);
            for (uint i = 0; i < 4; ++i) {
                normalized[i] =
                    weight[base + i] *
                    bfloat(float(input[base + i]) * inverse_rms);
            }
            thread float paired[4];
            for (uint i = 0; i < 4; ++i) {
                paired[i] = simd_shuffle(float(normalized[i]), lane ^ 8);
            }
            if (lane < 8) {
                bfloat rounded_mscale = bfloat(yarn_mscale);
                for (uint i = 0; i < 4; ++i) {
                    uint pair = base + i;
                    float first =
                        float(bfloat(normalized[i] * rounded_mscale));
                    float second =
                        float(bfloat(bfloat(paired[i]) * rounded_mscale));
                    float cosine = angles[pair];
                    float sine = angles[pair + rotary_pairs];
                    outrow[pair] = bfloat(first * cosine - second * sine);
                    outrow[pair + rotary_pairs] =
                        bfloat(first * sine + second * cosine);
                }
            } else if (lane >= 16) {
                for (uint i = 0; i < 4; ++i) {
                    outrow[base + i] = normalized[i];
                }
            }
        } else if (sg == 3) {
            const device bfloat* vin = raw_values + kv_head * head_dim;
            for (uint i = lane; i < head_dim; i += 32) {
                tg_v[i] = vin[i];
            }
        }
        threadgroup_barrier(mem_flags::mem_threadgroup);

        // Phase 2: one writer threadgroup per KV head persists the new row.
        if ((head0 % gqa) == 0 && sg == 0) {
            device bfloat* kc = (device bfloat*)k_cache +
                (size_t)kv_head * (capacity * head_dim) +
                (size_t)widx * head_dim;
            device bfloat* vc = (device bfloat*)v_cache +
                (size_t)kv_head * (capacity * head_dim) +
                (size_t)widx * head_dim;
            for (uint i = lane; i < head_dim; i += 32) {
                kc[i] = tg_k[i];
                vc[i] = tg_v[i];
            }
        }

        // Phase 3: GQA-pair attention over the first N rows in slot order,
        // textual replica of the sdpa_vector pair path (runtime N, tail
        // row included).
        threadgroup U outputs[4 * BN * BD];
        threadgroup U max_scores[2 * BN];
        threadgroup U sum_exp_scores[2 * BN];

        const device bfloat* pair_keys = k_cache +
            (size_t)kv_head * (capacity * head_dim) +
            (size_t)sg * head_dim + lane * qk_per_thread;
        const device bfloat* pair_values = v_cache +
            (size_t)kv_head * (capacity * head_dim) +
            (size_t)sg * head_dim + lane * v_per_thread;
        const int inner_k_stride = BN * int(head_dim);
        const int inner_v_stride = BN * int(head_dim);

        thread U pair_q0[qk_per_thread];
        thread U pair_q1[qk_per_thread];
        thread U pair_k[qk_per_thread];
        thread U pair_o0[v_per_thread];
        thread U pair_o1[v_per_thread];

        for (int j = 0; j < qk_per_thread; ++j) {
            pair_q0[j] =
                static_cast<U>(scale) * tg_q0[lane * qk_per_thread + j];
            pair_q1[j] =
                static_cast<U>(scale) * tg_q1[lane * qk_per_thread + j];
        }
        for (int j = 0; j < v_per_thread; ++j) {
            pair_o0[j] = 0;
            pair_o1[j] = 0;
        }

        U pair_max0 = metal::numeric_limits<U>::lowest();
        U pair_max1 = metal::numeric_limits<U>::lowest();
        U pair_sum0 = 0;
        U pair_sum1 = 0;

        int i = sg;
        for (; i + BN < N; i += 2 * BN) {
            const device bfloat* pipe_keys_b = pair_keys + inner_k_stride;
            const device bfloat* pipe_values_b = pair_values + inner_v_stride;
            const bool sub_a = uint(i) == widx;
            const bool sub_b = uint(i + BN) == widx;
            U pipe_ka[4];
            U pipe_kb[4];
            T_LOAD_K(pipe_ka, sub_a, pair_keys);
            T_LOAD_K(pipe_kb, sub_b, pipe_keys_b);
            bfloat pipe_va0, pipe_va1, pipe_va2, pipe_va3;
            bfloat pipe_vb0, pipe_vb1, pipe_vb2, pipe_vb3;
            T_LOAD_V(pipe_va0, pipe_va1, pipe_va2, pipe_va3, sub_a,
                pair_values);
            T_LOAD_V(pipe_vb0, pipe_vb1, pipe_vb2, pipe_vb3, sub_b,
                pipe_values_b);

            U pair_score0 = 0;
            U pair_score1 = 0;
            pair_score0 += pair_q0[0] * pipe_ka[0];
            pair_score1 += pair_q1[0] * pipe_ka[0];
            pair_score0 += pair_q0[1] * pipe_ka[1];
            pair_score1 += pair_q1[1] * pipe_ka[1];
            pair_score0 += pair_q0[2] * pipe_ka[2];
            pair_score1 += pair_q1[2] * pipe_ka[2];
            pair_score0 += pair_q0[3] * pipe_ka[3];
            pair_score1 += pair_q1[3] * pipe_ka[3];
            pair_score0 = simd_sum(pair_score0);
            pair_score1 = simd_sum(pair_score1);

            U pair_new_max0 = metal::max(pair_max0, pair_score0);
            U pair_new_max1 = metal::max(pair_max1, pair_score1);
            U pair_factor0;
            U pair_factor1;
            LAGUNA_RESCALE(pair_factor0, pair_max0 - pair_new_max0);
            LAGUNA_RESCALE(pair_factor1, pair_max1 - pair_new_max1);
            U pair_exp0 = metal::fast::exp(pair_score0 - pair_new_max0);
            U pair_exp1 = metal::fast::exp(pair_score1 - pair_new_max1);

            pair_max0 = pair_new_max0;
            pair_max1 = pair_new_max1;
            pair_sum0 = pair_sum0 * pair_factor0 + pair_exp0;
            pair_sum1 = pair_sum1 * pair_factor1 + pair_exp1;

            pair_o0[0] = pair_o0[0] * pair_factor0 + pair_exp0 * pipe_va0;
            pair_o1[0] = pair_o1[0] * pair_factor1 + pair_exp1 * pipe_va0;
            pair_o0[1] = pair_o0[1] * pair_factor0 + pair_exp0 * pipe_va1;
            pair_o1[1] = pair_o1[1] * pair_factor1 + pair_exp1 * pipe_va1;
            pair_o0[2] = pair_o0[2] * pair_factor0 + pair_exp0 * pipe_va2;
            pair_o1[2] = pair_o1[2] * pair_factor1 + pair_exp1 * pipe_va2;
            pair_o0[3] = pair_o0[3] * pair_factor0 + pair_exp0 * pipe_va3;
            pair_o1[3] = pair_o1[3] * pair_factor1 + pair_exp1 * pipe_va3;

            U pipeb_score0 = 0;
            U pipeb_score1 = 0;
            pipeb_score0 += pair_q0[0] * pipe_kb[0];
            pipeb_score1 += pair_q1[0] * pipe_kb[0];
            pipeb_score0 += pair_q0[1] * pipe_kb[1];
            pipeb_score1 += pair_q1[1] * pipe_kb[1];
            pipeb_score0 += pair_q0[2] * pipe_kb[2];
            pipeb_score1 += pair_q1[2] * pipe_kb[2];
            pipeb_score0 += pair_q0[3] * pipe_kb[3];
            pipeb_score1 += pair_q1[3] * pipe_kb[3];
            pipeb_score0 = simd_sum(pipeb_score0);
            pipeb_score1 = simd_sum(pipeb_score1);

            U pipeb_new_max0 = metal::max(pair_max0, pipeb_score0);
            U pipeb_new_max1 = metal::max(pair_max1, pipeb_score1);
            U pipeb_factor0;
            U pipeb_factor1;
            LAGUNA_RESCALE(pipeb_factor0, pair_max0 - pipeb_new_max0);
            LAGUNA_RESCALE(pipeb_factor1, pair_max1 - pipeb_new_max1);
            U pipeb_exp0 = metal::fast::exp(pipeb_score0 - pipeb_new_max0);
            U pipeb_exp1 = metal::fast::exp(pipeb_score1 - pipeb_new_max1);

            pair_max0 = pipeb_new_max0;
            pair_max1 = pipeb_new_max1;
            pair_sum0 = pair_sum0 * pipeb_factor0 + pipeb_exp0;
            pair_sum1 = pair_sum1 * pipeb_factor1 + pipeb_exp1;

            pair_o0[0] = pair_o0[0] * pipeb_factor0 + pipeb_exp0 * pipe_vb0;
            pair_o1[0] = pair_o1[0] * pipeb_factor1 + pipeb_exp1 * pipe_vb0;
            pair_o0[1] = pair_o0[1] * pipeb_factor0 + pipeb_exp0 * pipe_vb1;
            pair_o1[1] = pair_o1[1] * pipeb_factor1 + pipeb_exp1 * pipe_vb1;
            pair_o0[2] = pair_o0[2] * pipeb_factor0 + pipeb_exp0 * pipe_vb2;
            pair_o1[2] = pair_o1[2] * pipeb_factor1 + pipeb_exp1 * pipe_vb2;
            pair_o0[3] = pair_o0[3] * pipeb_factor0 + pipeb_exp0 * pipe_vb3;
            pair_o1[3] = pair_o1[3] * pipeb_factor1 + pipeb_exp1 * pipe_vb3;

            pair_keys += 2 * inner_k_stride;
            pair_values += 2 * inner_v_stride;
        }
        if (i < N) {
            const bool sub_t = uint(i) == widx;
            T_LOAD_K(pair_k, sub_t, pair_keys);
            bfloat pipe_va0, pipe_va1, pipe_va2, pipe_va3;
            T_LOAD_V(pipe_va0, pipe_va1, pipe_va2, pipe_va3, sub_t,
                pair_values);

            U pair_score0 = 0;
            U pair_score1 = 0;
            pair_score0 += pair_q0[0] * pair_k[0];
            pair_score1 += pair_q1[0] * pair_k[0];
            pair_score0 += pair_q0[1] * pair_k[1];
            pair_score1 += pair_q1[1] * pair_k[1];
            pair_score0 += pair_q0[2] * pair_k[2];
            pair_score1 += pair_q1[2] * pair_k[2];
            pair_score0 += pair_q0[3] * pair_k[3];
            pair_score1 += pair_q1[3] * pair_k[3];
            pair_score0 = simd_sum(pair_score0);
            pair_score1 = simd_sum(pair_score1);

            U pair_new_max0 = metal::max(pair_max0, pair_score0);
            U pair_new_max1 = metal::max(pair_max1, pair_score1);
            U pair_factor0;
            U pair_factor1;
            LAGUNA_RESCALE(pair_factor0, pair_max0 - pair_new_max0);
            LAGUNA_RESCALE(pair_factor1, pair_max1 - pair_new_max1);
            U pair_exp0 = metal::fast::exp(pair_score0 - pair_new_max0);
            U pair_exp1 = metal::fast::exp(pair_score1 - pair_new_max1);

            pair_max0 = pair_new_max0;
            pair_max1 = pair_new_max1;
            pair_sum0 = pair_sum0 * pair_factor0 + pair_exp0;
            pair_sum1 = pair_sum1 * pair_factor1 + pair_exp1;

            pair_o0[0] = pair_o0[0] * pair_factor0 + pair_exp0 * pipe_va0;
            pair_o1[0] = pair_o1[0] * pair_factor1 + pair_exp1 * pipe_va0;
            pair_o0[1] = pair_o0[1] * pair_factor0 + pair_exp0 * pipe_va1;
            pair_o1[1] = pair_o1[1] * pair_factor1 + pair_exp1 * pipe_va1;
            pair_o0[2] = pair_o0[2] * pair_factor0 + pair_exp0 * pipe_va2;
            pair_o1[2] = pair_o1[2] * pair_factor1 + pair_exp1 * pipe_va2;
            pair_o0[3] = pair_o0[3] * pair_factor0 + pair_exp0 * pipe_va3;
            pair_o1[3] = pair_o1[3] * pair_factor1 + pair_exp1 * pipe_va3;
        }

        // Combine: promoted two-plane exchange, textual replica of the
        // sdpa_vector pair path epilogue.
        constexpr int pair_planes = 2;
        constexpr int pair_plane_size = BN * BD;
        if (lane == 0) {
            max_scores[sg] = pair_max0;
            max_scores[BN + sg] = pair_max1;
            sum_exp_scores[sg] = pair_sum0;
            sum_exp_scores[BN + sg] = pair_sum1;
        }
        for (int p = 0; p < pair_planes; ++p) {
            outputs[p * pair_plane_size + lane * BD + sg] = pair_o0[p];
            outputs[
                (pair_planes + p) * pair_plane_size + lane * BD + sg] =
                pair_o1[p];
        }
        threadgroup_barrier(mem_flags::mem_threadgroup);

        pair_max0 = max_scores[lane];
        pair_max1 = max_scores[BN + lane];
        U pair_global_max0 = simd_max(pair_max0);
        U pair_global_max1 = simd_max(pair_max1);
        U pair_global_factor0 = metal::fast::exp(pair_max0 - pair_global_max0);
        U pair_global_factor1 = metal::fast::exp(pair_max1 - pair_global_max1);
        pair_sum0 = simd_sum(sum_exp_scores[lane] * pair_global_factor0);
        pair_sum1 = simd_sum(sum_exp_scores[BN + lane] * pair_global_factor1);

        for (int p = 0; p < pair_planes; ++p) {
            U acc0 = simd_sum(
                outputs[p * pair_plane_size + sg * BD + lane] *
                pair_global_factor0);
            U acc1 = simd_sum(
                outputs[
                    (pair_planes + p) * pair_plane_size + sg * BD + lane] *
                pair_global_factor1);
            pair_o0[p] = pair_sum0 == 0 ? acc0 : (acc0 / pair_sum0);
            pair_o1[p] = pair_sum1 == 0 ? acc1 : (acc1 / pair_sum1);
        }

        threadgroup_barrier(mem_flags::mem_threadgroup);
        for (int p = 0; p < pair_planes; ++p) {
            outputs[p * pair_plane_size + lane * BD + sg] =
                pair_o0[pair_planes + p];
            outputs[
                (pair_planes + p) * pair_plane_size + lane * BD + sg] =
                pair_o1[pair_planes + p];
        }
        threadgroup_barrier(mem_flags::mem_threadgroup);
        for (int p = 0; p < pair_planes; ++p) {
            U acc0 = simd_sum(
                outputs[p * pair_plane_size + sg * BD + lane] *
                pair_global_factor0);
            U acc1 = simd_sum(
                outputs[
                    (pair_planes + p) * pair_plane_size + sg * BD + lane] *
                pair_global_factor1);
            pair_o0[pair_planes + p] =
                pair_sum0 == 0 ? acc0 : (acc0 / pair_sum0);
            pair_o1[pair_planes + p] =
                pair_sum1 == 0 ? acc1 : (acc1 / pair_sum1);
        }

        if (lane == 0) {
            device bfloat* pair_out0 =
                attended + head0 * head_dim + sg * v_per_thread;
            device bfloat* pair_out1 =
                attended + head1 * head_dim + sg * v_per_thread;
            for (int p = 0; p < v_per_thread; ++p) {
                pair_out0[p] = static_cast<bfloat>(pair_o0[p]);
                pair_out1[p] = static_cast<bfloat>(pair_o1[p]);
            }
        }
        """,
    header: """
        #define LAGUNA_RESCALE(dst, delta_expr)         \\
          do {                                          \\
            const float db_delta_ = (delta_expr);       \\
            if (as_type<uint>(db_delta_) == 0u) {       \\
              dst = float(1.0f);                        \\
            } else {                                    \\
              dst = metal::fast::exp(db_delta_);        \\
            }                                           \\
          } while (false)

        #define T_LOAD_K(dst, substitute, ptr)                     \\
          do {                                                     \\
            if (substitute) {                                      \\
              dst[0] = tg_k[lane * qk_per_thread + 0];             \\
              dst[1] = tg_k[lane * qk_per_thread + 1];             \\
              dst[2] = tg_k[lane * qk_per_thread + 2];             \\
              dst[3] = tg_k[lane * qk_per_thread + 3];             \\
            } else {                                               \\
              const vec<bfloat, 4> v_ =                            \\
                  *reinterpret_cast<const device vec<bfloat, 4>*>( \\
                      ptr);                                        \\
              dst[0] = v_.x;                                       \\
              dst[1] = v_.y;                                       \\
              dst[2] = v_.z;                                       \\
              dst[3] = v_.w;                                       \\
            }                                                      \\
          } while (false)

        #define T_LOAD_V(d0, d1, d2, d3, substitute, ptr)          \\
          do {                                                     \\
            if (substitute) {                                      \\
              d0 = tg_v[lane * v_per_thread + 0];                  \\
              d1 = tg_v[lane * v_per_thread + 1];                  \\
              d2 = tg_v[lane * v_per_thread + 2];                  \\
              d3 = tg_v[lane * v_per_thread + 3];                  \\
            } else {                                               \\
              const vec<bfloat, 4> v_ =                            \\
                  *reinterpret_cast<const device vec<bfloat, 4>*>( \\
                      ptr);                                        \\
              d0 = v_.x;                                           \\
              d1 = v_.y;                                           \\
              d2 = v_.z;                                           \\
              d3 = v_.w;                                           \\
            }                                                      \\
          } while (false)

        // (trailing newline required: the JIT concatenates the generated
        // [[kernel]] signature directly after this header string)

        """,
    ensureRowContiguous: true
)

/// Fused decode attention for a full-attention layer with spare backing
/// capacity. Returns `[1, heads, 1, headDim]`; the caller advances the
/// cache clock via `KVCacheSimple.fusedAppendAdvance()`.
func lagunaFullPairGateAttention(
    rawQueries: MLXArray,
    rawKeys: MLXArray,
    rawValues: MLXArray,
    queryWeight: MLXArray,
    keyWeight: MLXArray,
    angles: MLXArray,
    cacheKeys: MLXArray,
    cacheValues: MLXArray,
    writeIdx: Int,
    scale: MLXArray
) -> MLXArray {
    let heads = LagunaConstants.fullAttentionHeads
    let kvHeads = LagunaConstants.numKeyValueHeads
    let capacity = cacheKeys.dim(2)
    precondition(rawQueries.dtype == .bfloat16)
    precondition(rawKeys.dtype == .bfloat16)
    precondition(rawValues.dtype == .bfloat16)
    precondition(rawQueries.shape == [1, 1, heads * LagunaConstants.headDim])
    precondition(rawKeys.shape == [1, 1, kvHeads * LagunaConstants.headDim])
    precondition(rawValues.shape == [1, 1, kvHeads * LagunaConstants.headDim])
    precondition(queryWeight.shape == [LagunaConstants.headDim])
    precondition(keyWeight.shape == [LagunaConstants.headDim])
    precondition(angles.dtype == .float32)
    precondition(angles.shape == [1, 1, 1, LagunaConstants.headDim / 2])
    precondition(cacheKeys.dtype == .bfloat16)
    precondition(
        cacheKeys.shape == [1, kvHeads, capacity, LagunaConstants.headDim])
    precondition(
        cacheValues.shape == [1, kvHeads, capacity, LagunaConstants.headDim])
    precondition(writeIdx >= 0 && writeIdx < capacity)
    precondition(scale.dtype == .float32 && scale.size == 1)

    let params = MLXArray([
        UInt32(writeIdx), UInt32(writeIdx + 1), UInt32(capacity),
    ])
    return lagunaFullPairGateAttentionKernel(
        [
            rawQueries, rawKeys, rawValues,
            queryWeight, keyWeight, angles,
            cacheKeys, cacheValues, params, scale,
        ],
        grid: ((heads / 2) * 1024, 1, 1),
        threadGroup: (1024, 1, 1),
        outputShapes: [[1, heads, 1, LagunaConstants.headDim]],
        outputDTypes: [.bfloat16]
    )[0]
}
