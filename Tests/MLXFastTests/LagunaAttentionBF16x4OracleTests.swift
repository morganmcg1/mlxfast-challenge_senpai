import Foundation
import MLX
@testable import MLXFastModel
import XCTest

private let timingSlidingScalarKernel = MLXFast.metalKernel(
    name: "laguna_sliding_fused_attn_ring_scalar_timing_v1",
    inputNames: [
        "raw_queries", "raw_keys", "raw_values",
        "query_weight", "key_weight", "angles",
        "k_cache", "v_cache", "params", "scale_arr",
    ],
    outputNames: ["attended"],
    source: """
        constexpr uint head_dim = 128;
        constexpr uint window = 512;
        constexpr uint gqa = 8;
        constexpr int BN = 32;
        constexpr int BD = 32;
        constexpr int qk_per_thread = 4;
        constexpr int v_per_thread = 4;
        constexpr uint rotary_pairs = 64;
        constexpr int N = 512;

        typedef float U;

        uint pair_tg = threadgroup_position_in_grid.x;
        uint head0 = pair_tg * 2;
        uint head1 = head0 + 1;
        uint kv_head = head0 / gqa;
        uint sg = simdgroup_index_in_threadgroup;
        uint lane = thread_index_in_simdgroup;
        uint widx = params[0];
        float scale = scale_arr[0];

        threadgroup bfloat tg_q0[head_dim];
        threadgroup bfloat tg_q1[head_dim];
        threadgroup bfloat tg_k[head_dim];
        threadgroup bfloat tg_v[head_dim];

        // Phase 1: per-head RMSNorm + plain RoPE, textual replica of
        // laguna_sliding_qk_norm_rope_bf16_128_v1 with the device row
        // writes retargeted at threadgroup memory. simdgroups 0/1/2 own
        // q0/q1/k; simdgroup 3 copies the raw V row (stored unmodified).
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
                paired[i] = simd_shuffle(float(normalized[i]), lane ^ 16);
            }
            if (lane < 16) {
                for (uint i = 0; i < 4; ++i) {
                    uint pair = base + i;
                    float first = float(normalized[i]);
                    float second = paired[i];
                    float cosine = angles[pair];
                    float sine = angles[pair + rotary_pairs];
                    outrow[pair] = bfloat(first * cosine - second * sine);
                    outrow[pair + rotary_pairs] =
                        bfloat(first * sine + second * cosine);
                }
            }
        } else if (sg == 3) {
            const device bfloat* vin = raw_values + kv_head * head_dim;
            for (uint i = lane; i < head_dim; i += 32) {
                tg_v[i] = vin[i];
            }
        }
        threadgroup_barrier(mem_flags::mem_threadgroup);

        // Phase 2: one writer threadgroup per KV head persists the new row
        // for future steps. No threadgroup reads slot widx from device this
        // dispatch (all substitute the threadgroup copy), so cross-group
        // ordering is irrelevant; the next step observes the write through
        // command-buffer sequencing.
        if ((head0 % gqa) == 0 && sg == 0) {
            device bfloat* kc = (device bfloat*)k_cache +
                (size_t)kv_head * (window * head_dim) +
                (size_t)widx * head_dim;
            device bfloat* vc = (device bfloat*)v_cache +
                (size_t)kv_head * (window * head_dim) +
                (size_t)widx * head_dim;
            for (uint i = lane; i < head_dim; i += 32) {
                kc[i] = tg_k[i];
                vc[i] = tg_v[i];
            }
        }

        // Phase 3: GQA-pair attention over the ring in slot order, textual
        // replica of the sdpa_vector pair path at fixed kL = 512 (steady
        // ring: the 8-trip two-deep pipeline covers all 16 slots per
        // simdgroup with no tail).
        threadgroup U outputs[4 * BN * BD];
        threadgroup U max_scores[2 * BN];
        threadgroup U sum_exp_scores[2 * BN];

        const device bfloat* pair_keys = k_cache +
            (size_t)kv_head * (window * head_dim) +
            (size_t)sg * head_dim + lane * qk_per_thread;
        const device bfloat* pair_values = v_cache +
            (size_t)kv_head * (window * head_dim) +
            (size_t)sg * head_dim + lane * v_per_thread;
        const int inner_k_stride = BN * int(head_dim);
        const int inner_v_stride = BN * int(head_dim);

        thread U pair_q0[qk_per_thread];
        thread U pair_q1[qk_per_thread];
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

        const bool owns_write_slot = uint(sg) == (widx & 31u);
        int i = sg;
        for (; i + BN < N; i += 2 * BN) {
            const device bfloat* pipe_keys_b = pair_keys + inner_k_stride;
            const device bfloat* pipe_values_b = pair_values + inner_v_stride;
            U pipe_ka[4];
            U pipe_kb[4];
            bfloat pipe_va0, pipe_va1, pipe_va2, pipe_va3;
            bfloat pipe_vb0, pipe_vb1, pipe_vb2, pipe_vb3;
            if (owns_write_slot) {
                const bool sub_a = uint(i) == widx;
                const bool sub_b = uint(i + BN) == widx;
                T_LOAD_K(pipe_ka, sub_a, pair_keys);
                T_LOAD_K(pipe_kb, sub_b, pipe_keys_b);
                T_LOAD_V(pipe_va0, pipe_va1, pipe_va2, pipe_va3, sub_a,
                    pair_values);
                T_LOAD_V(pipe_vb0, pipe_vb1, pipe_vb2, pipe_vb3, sub_b,
                    pipe_values_b);
            } else {
                T_LOAD_DEVICE_K(pipe_ka, pair_keys);
                T_LOAD_DEVICE_K(pipe_kb, pipe_keys_b);
                T_LOAD_DEVICE_V(pipe_va0, pipe_va1, pipe_va2, pipe_va3,
                    pair_values);
                T_LOAD_DEVICE_V(pipe_vb0, pipe_vb1, pipe_vb2, pipe_vb3,
                    pipe_values_b);
            }

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
        // Alpha-skip rescale, replica of sdpa_vector.h's shipped
        // DARKBLOOM_RESCALE_FACTOR (DARKBLOOM_ALPHASKIP == 1 arm).
        #define LAGUNA_RESCALE(dst, delta_expr)         \\
          do {                                          \\
            const float db_delta_ = (delta_expr);       \\
            if (as_type<uint>(db_delta_) == 0u) {       \\
              dst = float(1.0f);                        \\
            } else {                                    \\
              dst = metal::fast::exp(db_delta_);        \\
            }                                           \\
          } while (false)

        // K loads: 8-byte vec loads from the ring, or the threadgroup
        // substitute for the just-written slot. Same elements, same order,
        // same bfloat -> float conversion points as the scalar form.
        #define T_LOAD_DEVICE_K(dst, ptr)                          \\
          do {                                                     \\
            const vec<bfloat, 4> v_ =                              \\
                *reinterpret_cast<const device vec<bfloat, 4>*>(   \\
                    ptr);                                          \\
            dst[0] = v_.x;                                         \\
            dst[1] = v_.y;                                         \\
            dst[2] = v_.z;                                         \\
            dst[3] = v_.w;                                         \\
          } while (false)

        #define T_LOAD_K(dst, substitute, ptr)                     \\
          do {                                                     \\
            if (substitute) {                                      \\
              dst[0] = tg_k[lane * qk_per_thread + 0];             \\
              dst[1] = tg_k[lane * qk_per_thread + 1];             \\
              dst[2] = tg_k[lane * qk_per_thread + 2];             \\
              dst[3] = tg_k[lane * qk_per_thread + 3];             \\
            } else {                                               \\
              T_LOAD_DEVICE_K(dst, ptr);                           \\
            }                                                      \\
          } while (false)

        #define T_LOAD_DEVICE_V(d0, d1, d2, d3, ptr)               \\
          do {                                                     \\
            const vec<bfloat, 4> v_ =                              \\
                *reinterpret_cast<const device vec<bfloat, 4>*>(   \\
                    ptr);                                          \\
            d0 = v_.x;                                             \\
            d1 = v_.y;                                             \\
            d2 = v_.z;                                             \\
            d3 = v_.w;                                             \\
          } while (false)

        #define T_LOAD_V(d0, d1, d2, d3, substitute, ptr)          \\
          do {                                                     \\
            if (substitute) {                                      \\
              d0 = tg_v[lane * v_per_thread + 0];                  \\
              d1 = tg_v[lane * v_per_thread + 1];                  \\
              d2 = tg_v[lane * v_per_thread + 2];                  \\
              d3 = tg_v[lane * v_per_thread + 3];                  \\
            } else {                                               \\
              T_LOAD_DEVICE_V(d0, d1, d2, d3, ptr);                \\
            }                                                      \\
          } while (false)

        // (trailing newline required: the JIT concatenates the generated
        // [[kernel]] signature directly after this header string)

        """,
    ensureRowContiguous: true
)

private let timingSlidingVectorKernel = MLXFast.metalKernel(
    name: "laguna_sliding_fused_attn_ring_vector_timing_v1",
    inputNames: [
        "raw_queries", "raw_keys", "raw_values",
        "query_weight", "key_weight", "angles",
        "k_cache", "v_cache", "params", "scale_arr",
    ],
    outputNames: ["attended"],
    source: """
        constexpr uint head_dim = 128;
        constexpr uint window = 512;
        constexpr uint gqa = 8;
        constexpr int BN = 32;
        constexpr int BD = 32;
        constexpr int qk_per_thread = 4;
        constexpr int v_per_thread = 4;
        constexpr uint rotary_pairs = 64;
        constexpr int N = 512;

        typedef float U;

        uint pair_tg = threadgroup_position_in_grid.x;
        uint head0 = pair_tg * 2;
        uint head1 = head0 + 1;
        uint kv_head = head0 / gqa;
        uint sg = simdgroup_index_in_threadgroup;
        uint lane = thread_index_in_simdgroup;
        uint widx = params[0];
        float scale = scale_arr[0];

        threadgroup bfloat tg_q0[head_dim];
        threadgroup bfloat tg_q1[head_dim];
        threadgroup bfloat tg_k[head_dim];
        threadgroup bfloat tg_v[head_dim];

        // Phase 1: per-head RMSNorm + plain RoPE, textual replica of
        // laguna_sliding_qk_norm_rope_bf16_128_v1 with the device row
        // writes retargeted at threadgroup memory. simdgroups 0/1/2 own
        // q0/q1/k; simdgroup 3 copies the raw V row (stored unmodified).
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
                paired[i] = simd_shuffle(float(normalized[i]), lane ^ 16);
            }
            if (lane < 16) {
                for (uint i = 0; i < 4; ++i) {
                    uint pair = base + i;
                    float first = float(normalized[i]);
                    float second = paired[i];
                    float cosine = angles[pair];
                    float sine = angles[pair + rotary_pairs];
                    outrow[pair] = bfloat(first * cosine - second * sine);
                    outrow[pair + rotary_pairs] =
                        bfloat(first * sine + second * cosine);
                }
            }
        } else if (sg == 3) {
            const device bfloat* vin = raw_values + kv_head * head_dim;
            for (uint i = lane; i < head_dim; i += 32) {
                tg_v[i] = vin[i];
            }
        }
        threadgroup_barrier(mem_flags::mem_threadgroup);

        // Phase 2: one writer threadgroup per KV head persists the new row
        // for future steps. No threadgroup reads slot widx from device this
        // dispatch (all substitute the threadgroup copy), so cross-group
        // ordering is irrelevant; the next step observes the write through
        // command-buffer sequencing.
        if ((head0 % gqa) == 0 && sg == 0) {
            device bfloat* kc = (device bfloat*)k_cache +
                (size_t)kv_head * (window * head_dim) +
                (size_t)widx * head_dim;
            device bfloat* vc = (device bfloat*)v_cache +
                (size_t)kv_head * (window * head_dim) +
                (size_t)widx * head_dim;
            for (uint i = lane; i < head_dim; i += 32) {
                kc[i] = tg_k[i];
                vc[i] = tg_v[i];
            }
        }

        // Phase 3: GQA-pair attention over the ring in slot order, textual
        // replica of the sdpa_vector pair path at fixed kL = 512 (steady
        // ring: the 8-trip two-deep pipeline covers all 16 slots per
        // simdgroup with no tail).
        threadgroup U outputs[4 * BN * BD];
        threadgroup U max_scores[2 * BN];
        threadgroup U sum_exp_scores[2 * BN];

        const device bfloat* pair_keys = k_cache +
            (size_t)kv_head * (window * head_dim) +
            (size_t)sg * head_dim + lane * qk_per_thread;
        const device bfloat* pair_values = v_cache +
            (size_t)kv_head * (window * head_dim) +
            (size_t)sg * head_dim + lane * v_per_thread;
        const int inner_k_stride = BN * int(head_dim);
        const int inner_v_stride = BN * int(head_dim);

        thread U pair_q0[qk_per_thread];
        thread U pair_q1[qk_per_thread];
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

        const bool owns_write_slot = uint(sg) == (widx & 31u);
        int i = sg;
        for (; i + BN < N; i += 2 * BN) {
            const device bfloat* pipe_keys_b = pair_keys + inner_k_stride;
            const device bfloat* pipe_values_b = pair_values + inner_v_stride;
            U pipe_ka[4];
            U pipe_kb[4];
            bfloat pipe_va0, pipe_va1, pipe_va2, pipe_va3;
            bfloat pipe_vb0, pipe_vb1, pipe_vb2, pipe_vb3;
            if (owns_write_slot) {
                const bool sub_a = uint(i) == widx;
                const bool sub_b = uint(i + BN) == widx;
                T_LOAD_K(pipe_ka, sub_a, pair_keys);
                T_LOAD_K(pipe_kb, sub_b, pipe_keys_b);
                T_LOAD_V(pipe_va0, pipe_va1, pipe_va2, pipe_va3, sub_a,
                    pair_values);
                T_LOAD_V(pipe_vb0, pipe_vb1, pipe_vb2, pipe_vb3, sub_b,
                    pipe_values_b);
            } else {
                T_LOAD_DEVICE_K(pipe_ka, pair_keys);
                T_LOAD_DEVICE_K(pipe_kb, pipe_keys_b);
                T_LOAD_DEVICE_V(pipe_va0, pipe_va1, pipe_va2, pipe_va3,
                    pair_values);
                T_LOAD_DEVICE_V(pipe_vb0, pipe_vb1, pipe_vb2, pipe_vb3,
                    pipe_values_b);
            }

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
            *reinterpret_cast<device vec<bfloat, 4>*>(pair_out0) =
                vec<bfloat, 4>(
                    static_cast<bfloat>(pair_o0[0]),
                    static_cast<bfloat>(pair_o0[1]),
                    static_cast<bfloat>(pair_o0[2]),
                    static_cast<bfloat>(pair_o0[3]));
            *reinterpret_cast<device vec<bfloat, 4>*>(pair_out1) =
                vec<bfloat, 4>(
                    static_cast<bfloat>(pair_o1[0]),
                    static_cast<bfloat>(pair_o1[1]),
                    static_cast<bfloat>(pair_o1[2]),
                    static_cast<bfloat>(pair_o1[3]));
        }
        """,
    header: """
        // Alpha-skip rescale, replica of sdpa_vector.h's shipped
        // DARKBLOOM_RESCALE_FACTOR (DARKBLOOM_ALPHASKIP == 1 arm).
        #define LAGUNA_RESCALE(dst, delta_expr)         \\
          do {                                          \\
            const float db_delta_ = (delta_expr);       \\
            if (as_type<uint>(db_delta_) == 0u) {       \\
              dst = float(1.0f);                        \\
            } else {                                    \\
              dst = metal::fast::exp(db_delta_);        \\
            }                                           \\
          } while (false)

        // K loads: 8-byte vec loads from the ring, or the threadgroup
        // substitute for the just-written slot. Same elements, same order,
        // same bfloat -> float conversion points as the scalar form.
        #define T_LOAD_DEVICE_K(dst, ptr)                          \\
          do {                                                     \\
            const vec<bfloat, 4> v_ =                              \\
                *reinterpret_cast<const device vec<bfloat, 4>*>(   \\
                    ptr);                                          \\
            dst[0] = v_.x;                                         \\
            dst[1] = v_.y;                                         \\
            dst[2] = v_.z;                                         \\
            dst[3] = v_.w;                                         \\
          } while (false)

        #define T_LOAD_K(dst, substitute, ptr)                     \\
          do {                                                     \\
            if (substitute) {                                      \\
              dst[0] = tg_k[lane * qk_per_thread + 0];             \\
              dst[1] = tg_k[lane * qk_per_thread + 1];             \\
              dst[2] = tg_k[lane * qk_per_thread + 2];             \\
              dst[3] = tg_k[lane * qk_per_thread + 3];             \\
            } else {                                               \\
              T_LOAD_DEVICE_K(dst, ptr);                           \\
            }                                                      \\
          } while (false)

        #define T_LOAD_DEVICE_V(d0, d1, d2, d3, ptr)               \\
          do {                                                     \\
            const vec<bfloat, 4> v_ =                              \\
                *reinterpret_cast<const device vec<bfloat, 4>*>(   \\
                    ptr);                                          \\
            d0 = v_.x;                                             \\
            d1 = v_.y;                                             \\
            d2 = v_.z;                                             \\
            d3 = v_.w;                                             \\
          } while (false)

        #define T_LOAD_V(d0, d1, d2, d3, substitute, ptr)          \\
          do {                                                     \\
            if (substitute) {                                      \\
              d0 = tg_v[lane * v_per_thread + 0];                  \\
              d1 = tg_v[lane * v_per_thread + 1];                  \\
              d2 = tg_v[lane * v_per_thread + 2];                  \\
              d3 = tg_v[lane * v_per_thread + 3];                  \\
            } else {                                               \\
              T_LOAD_DEVICE_V(d0, d1, d2, d3, ptr);                \\
            }                                                      \\
          } while (false)

        // (trailing newline required: the JIT concatenates the generated
        // [[kernel]] signature directly after this header string)

        """,
    ensureRowContiguous: true
)

private let timingFullScalarKernel = MLXFast.metalKernel(
    name: "laguna_full_fused_attn_grow_scalar_timing_v1",
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

private let timingFullVectorKernel = MLXFast.metalKernel(
    name: "laguna_full_fused_attn_grow_vector_timing_v1",
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
            *reinterpret_cast<device vec<bfloat, 4>*>(pair_out0) =
                vec<bfloat, 4>(
                    static_cast<bfloat>(pair_o0[0]),
                    static_cast<bfloat>(pair_o0[1]),
                    static_cast<bfloat>(pair_o0[2]),
                    static_cast<bfloat>(pair_o0[3]));
            *reinterpret_cast<device vec<bfloat, 4>*>(pair_out1) =
                vec<bfloat, 4>(
                    static_cast<bfloat>(pair_o1[0]),
                    static_cast<bfloat>(pair_o1[1]),
                    static_cast<bfloat>(pair_o1[2]),
                    static_cast<bfloat>(pair_o1[3]));
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

final class LagunaAttentionBF16x4OracleTests: XCTestCase {
    private let headDim = 128
    private let kvHeads = 8

    func testRawByteOracle() throws {
        guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1"
        else {
            throw XCTSkip("set MLXFAST_RUN_MLX_RUNTIME_TESTS=1")
        }
        guard let outputPath = ProcessInfo.processInfo.environment[
            "MLXFAST_ATTENTION_ORACLE_OUTPUT"]
        else {
            XCTFail("MLXFAST_ATTENTION_ORACLE_OUTPUT is required")
            return
        }

        var artifact = Data("mlxfast-bf16x4-oracle-v1\n".utf8)
        try appendSpecialConversionOracle(to: &artifact)
        for position in [511, 512, 513, 639] {
            appendSliding(position: position, to: &artifact)
            appendFull(position: position, to: &artifact)
        }
        try artifact.write(to: URL(fileURLWithPath: outputPath), options: .atomic)
        print("bf16x4_oracle_path=\(outputPath) bytes=\(artifact.count)")
    }

    private func appendSpecialConversionOracle(to artifact: inout Data) throws {
        let inputBits: [UInt32] = [
            0x0000_0000, 0x8000_0000,
            0x0000_0001, 0x8000_0001,
            0x0000_8000, 0x8000_8000,
            0x0001_0000, 0x8001_0000,
            0x0001_8000, 0x8001_8000,
            0x3f80_8000, 0xbf80_8000,
            0x3f81_8000, 0xbf81_8000,
            0x7f7f_ffff, 0xff7f_ffff,
            0x7f80_0000, 0xff80_0000,
            0x7fc0_0000, 0xffc0_0000,
            0x7fa0_0001, 0xffa0_0001,
            0x0080_0000, 0x8080_0000,
        ]
        let input = MLXArray(inputBits).view(dtype: .float32)
        let kernel = MLXFast.metalKernel(
            name: "laguna_bf16x4_store_oracle",
            inputNames: ["input"],
            outputNames: ["scalar_out", "vector_out"],
            source: """
                uint base = thread_position_in_grid.x * 4;
                scalar_out[base + 0] = static_cast<bfloat>(input[base + 0]);
                scalar_out[base + 1] = static_cast<bfloat>(input[base + 1]);
                scalar_out[base + 2] = static_cast<bfloat>(input[base + 2]);
                scalar_out[base + 3] = static_cast<bfloat>(input[base + 3]);
                *reinterpret_cast<device vec<bfloat, 4>*>(vector_out + base) =
                    vec<bfloat, 4>(
                        static_cast<bfloat>(input[base + 0]),
                        static_cast<bfloat>(input[base + 1]),
                        static_cast<bfloat>(input[base + 2]),
                        static_cast<bfloat>(input[base + 3]));
                """)
        let outputs = kernel(
            [input],
            grid: (inputBits.count / 4, 1, 1),
            threadGroup: (inputBits.count / 4, 1, 1),
            outputShapes: [[inputBits.count], [inputBits.count]],
            outputDTypes: [.bfloat16, .bfloat16]
        )
        eval(outputs)
        let scalarBits = outputs[0].view(dtype: .uint16).asArray(UInt16.self)
        let vectorBits = outputs[1].view(dtype: .uint16).asArray(UInt16.self)
        XCTAssertEqual(scalarBits, vectorBits)
        append(label: "special/input-f32-bits", bytes: input.asData(access: .copy).data,
               to: &artifact)
        append(array: outputs[0], label: "special/scalar-bf16", to: &artifact)
        append(array: outputs[1], label: "special/vector-bf16", to: &artifact)
        print("bf16x4_special_cases=\(inputBits.count) scalar_vector_mismatches=0")
    }

    private func appendSliding(position: Int, to artifact: inout Data) {
        let heads = 64
        let window = 512
        let writeIndex = position % window
        let query = deterministicBF16(
            shape: [1, 1, heads * headDim], phase: Float(position) * 0.001 + 0.1)
        let key = deterministicBF16(
            shape: [1, 1, kvHeads * headDim], phase: Float(position) * 0.001 + 0.2)
        let value = deterministicBF16(
            shape: [1, 1, kvHeads * headDim], phase: Float(position) * 0.001 + 0.3)
        let queryWeight = deterministicWeight(phase: 0.4)
        let keyWeight = deterministicWeight(phase: 0.5)
        let angles = identityAngles(rotaryDimensions: headDim)
        let cacheShape = [1, kvHeads, window, headDim]
        let cacheKeys = deterministicBF16(shape: cacheShape, phase: 0.6)
        let cacheValues = deterministicBF16(shape: cacheShape, phase: 0.7)
        let output = lagunaSlidingFusedAttention(
            rawQueries: query,
            rawKeys: key,
            rawValues: value,
            queryWeight: queryWeight,
            keyWeight: keyWeight,
            angles: angles,
            cacheKeys: cacheKeys,
            cacheValues: cacheValues,
            writeIdx: writeIndex,
            scale: MLXArray([Float(1.0 / sqrt(Float(headDim)))])
        )
        eval(output)
        append(array: output, label: "sliding/\(position)/output", to: &artifact)
        append(array: cacheKeys, label: "sliding/\(position)/cache-keys", to: &artifact)
        append(array: cacheValues, label: "sliding/\(position)/cache-values", to: &artifact)
        print("bf16x4_sliding_position=\(position) write_index=\(writeIndex)")
    }

    private func appendFull(position: Int, to artifact: inout Data) {
        let heads = 48
        let capacity = 768
        let query = deterministicBF16(
            shape: [1, 1, heads * headDim], phase: Float(position) * 0.001 + 0.8)
        let key = deterministicBF16(
            shape: [1, 1, kvHeads * headDim], phase: Float(position) * 0.001 + 0.9)
        let value = deterministicBF16(
            shape: [1, 1, kvHeads * headDim], phase: Float(position) * 0.001 + 1.0)
        let queryWeight = deterministicWeight(phase: 1.1)
        let keyWeight = deterministicWeight(phase: 1.2)
        let angles = identityAngles(rotaryDimensions: headDim / 2)
        let cacheShape = [1, kvHeads, capacity, headDim]
        let cacheKeys = deterministicBF16(shape: cacheShape, phase: 1.3)
        let cacheValues = deterministicBF16(shape: cacheShape, phase: 1.4)
        let output = lagunaFullFusedAttention(
            rawQueries: query,
            rawKeys: key,
            rawValues: value,
            queryWeight: queryWeight,
            keyWeight: keyWeight,
            angles: angles,
            cacheKeys: cacheKeys,
            cacheValues: cacheValues,
            writeIdx: position,
            scale: MLXArray([Float(1.0 / sqrt(Float(headDim)))])
        )
        eval(output)
        append(array: output, label: "full/\(position)/output", to: &artifact)
        append(array: cacheKeys, label: "full/\(position)/cache-keys", to: &artifact)
        append(array: cacheValues, label: "full/\(position)/cache-values", to: &artifact)
        print("bf16x4_full_position=\(position) capacity=\(capacity)")
    }

    private func deterministicBF16(shape: [Int], phase: Float) -> MLXArray {
        let count = shape.reduce(1, *)
        let axis = MLXArray(0..<count).asType(.float32)
        return (sin(axis * 0.0013 + phase) * 0.125)
            .asType(.bfloat16)
            .reshaped(shape)
    }

    private func deterministicWeight(phase: Float) -> MLXArray {
        let axis = MLXArray(0..<headDim).asType(.float32)
        return (cos(axis * 0.017 + phase) * 0.25 + 1.0).asType(.bfloat16)
    }

    private func identityAngles(rotaryDimensions: Int) -> MLXArray {
        let half = rotaryDimensions / 2
        return MLXArray(
            Array(repeating: Float(1), count: half)
                + Array(repeating: Float(0), count: half)
        ).reshaped([1, 1, 1, rotaryDimensions])
    }

    private func append(array: MLXArray, label: String, to artifact: inout Data) {
        eval(array)
        append(label: label, bytes: array.asData(access: .copy).data, to: &artifact)
    }

    private func append(label: String, bytes: Data, to artifact: inout Data) {
        let labelBytes = Data(label.utf8)
        append(UInt32(labelBytes.count), to: &artifact)
        artifact.append(labelBytes)
        append(UInt64(bytes.count), to: &artifact)
        artifact.append(bytes)
    }

    private func append<T: FixedWidthInteger>(_ value: T, to data: inout Data) {
        var littleEndian = value.littleEndian
        Swift.withUnsafeBytes(of: &littleEndian) { data.append(contentsOf: $0) }
    }
}

final class LagunaAttentionBF16x4TimingTests: XCTestCase {
    private let headDim = 128
    private let kvHeads = 8

    func testIsolatedTiming() throws {
        guard ProcessInfo.processInfo.environment["MLXFAST_RUN_BF16X4_TIMING"] == "1"
        else {
            throw XCTSkip("set MLXFAST_RUN_BF16X4_TIMING=1")
        }
        guard let outputPath = ProcessInfo.processInfo.environment[
            "MLXFAST_ATTENTION_TIMING_OUTPUT"]
        else {
            XCTFail("MLXFAST_ATTENTION_TIMING_OUTPUT is required")
            return
        }

        var rows = ["family,order,cycle,slot,variant,nanoseconds,kernels"]
        benchmarkSliding(rows: &rows)
        benchmarkFull(rows: &rows)
        try (rows.joined(separator: "\n") + "\n").write(
            to: URL(fileURLWithPath: outputPath), atomically: true, encoding: .utf8)
        print("bf16x4_timing_path=\(outputPath) samples=\(rows.count - 1)")
    }

    private func benchmarkSliding(rows: inout [String]) {
        let heads = 64
        let query = deterministicBF16(shape: [1, 1, heads * headDim], phase: 2.1)
        let key = deterministicBF16(shape: [1, 1, kvHeads * headDim], phase: 2.2)
        let value = deterministicBF16(shape: [1, 1, kvHeads * headDim], phase: 2.3)
        let queryWeight = deterministicWeight(phase: 2.4)
        let keyWeight = deterministicWeight(phase: 2.5)
        let angles = identityAngles(rotaryDimensions: headDim)
        let cacheKeys = deterministicBF16(
            shape: [1, kvHeads, 512, headDim], phase: 2.6)
        let cacheValues = deterministicBF16(
            shape: [1, kvHeads, 512, headDim], phase: 2.7)
        let scale = MLXArray([Float(1.0 / sqrt(Float(headDim)))])
        let params = (512..<640).map { MLXArray([UInt32($0 % 512)]) }
        eval([query, key, value, queryWeight, keyWeight, angles,
              cacheKeys, cacheValues, scale] + params)
        Stream.gpu.synchronize()

        let scalar: (MLXArray) -> MLXArray = { param in
            timingSlidingScalarKernel(
                [query, key, value, queryWeight, keyWeight, angles,
                 cacheKeys, cacheValues, param, scale],
                grid: ((heads / 2) * 1024, 1, 1),
                threadGroup: (1024, 1, 1),
                outputShapes: [[1, heads, 1, self.headDim]],
                outputDTypes: [.bfloat16]
            )[0]
        }
        let vector: (MLXArray) -> MLXArray = { param in
            timingSlidingVectorKernel(
                [query, key, value, queryWeight, keyWeight, angles,
                 cacheKeys, cacheValues, param, scale],
                grid: ((heads / 2) * 1024, 1, 1),
                threadGroup: (1024, 1, 1),
                outputShapes: [[1, heads, 1, self.headDim]],
                outputDTypes: [.bfloat16]
            )[0]
        }
        verifyEndpoints(family: "sliding", params: params, scalar: scalar, vector: vector)
        benchmarkFamily(
            family: "sliding", params: params,
            scalar: scalar, vector: vector, rows: &rows)
    }

    private func benchmarkFull(rows: inout [String]) {
        let heads = 48
        let capacity = 768
        let query = deterministicBF16(shape: [1, 1, heads * headDim], phase: 3.1)
        let key = deterministicBF16(shape: [1, 1, kvHeads * headDim], phase: 3.2)
        let value = deterministicBF16(shape: [1, 1, kvHeads * headDim], phase: 3.3)
        let queryWeight = deterministicWeight(phase: 3.4)
        let keyWeight = deterministicWeight(phase: 3.5)
        let angles = identityAngles(rotaryDimensions: headDim / 2)
        let cacheKeys = deterministicBF16(
            shape: [1, kvHeads, capacity, headDim], phase: 3.6)
        let cacheValues = deterministicBF16(
            shape: [1, kvHeads, capacity, headDim], phase: 3.7)
        let scale = MLXArray([Float(1.0 / sqrt(Float(headDim)))])
        let params = (512..<640).map {
            MLXArray([UInt32($0), UInt32($0 + 1), UInt32(capacity)])
        }
        eval([query, key, value, queryWeight, keyWeight, angles,
              cacheKeys, cacheValues, scale] + params)
        Stream.gpu.synchronize()

        let scalar: (MLXArray) -> MLXArray = { param in
            timingFullScalarKernel(
                [query, key, value, queryWeight, keyWeight, angles,
                 cacheKeys, cacheValues, param, scale],
                grid: ((heads / 2) * 1024, 1, 1),
                threadGroup: (1024, 1, 1),
                outputShapes: [[1, heads, 1, self.headDim]],
                outputDTypes: [.bfloat16]
            )[0]
        }
        let vector: (MLXArray) -> MLXArray = { param in
            timingFullVectorKernel(
                [query, key, value, queryWeight, keyWeight, angles,
                 cacheKeys, cacheValues, param, scale],
                grid: ((heads / 2) * 1024, 1, 1),
                threadGroup: (1024, 1, 1),
                outputShapes: [[1, heads, 1, self.headDim]],
                outputDTypes: [.bfloat16]
            )[0]
        }
        verifyEndpoints(family: "full", params: params, scalar: scalar, vector: vector)
        benchmarkFamily(
            family: "full", params: params,
            scalar: scalar, vector: vector, rows: &rows)
    }

    private func verifyEndpoints(
        family: String,
        params: [MLXArray],
        scalar: (MLXArray) -> MLXArray,
        vector: (MLXArray) -> MLXArray
    ) {
        for index in [params.startIndex, params.index(before: params.endIndex)] {
            let old = scalar(params[index])
            let new = vector(params[index])
            eval([old, new])
            Stream.gpu.synchronize()
            XCTAssertEqual(
                old.asData(access: .copy).data,
                new.asData(access: .copy).data,
                "\(family) endpoint \(index) differs")
        }
        print("bf16x4_timing_\(family)_endpoint_mismatches=0")
    }

    private func benchmarkFamily(
        family: String,
        params: [MLXArray],
        scalar: (MLXArray) -> MLXArray,
        vector: (MLXArray) -> MLXArray,
        rows: inout [String]
    ) {
        for _ in 0..<2 {
            materialize(params: params, make: scalar)
            materialize(params: params, make: vector)
        }

        let variants: [(String, (MLXArray) -> MLXArray)] = [
            ("scalar", scalar), ("vector", vector),
        ]
        let orders: [(String, [Int])] = [
            ("ABBA", [0, 1, 1, 0]),
            ("BAAB", [1, 0, 0, 1]),
        ]
        for cycle in 0..<12 {
            for (orderName, order) in orders {
                for (slot, variantIndex) in order.enumerated() {
                    let (variantName, make) = variants[variantIndex]
                    let nanoseconds = timeBatch(params: params, make: make)
                    rows.append(
                        "\(family),\(orderName),\(cycle),\(slot),\(variantName)," +
                        "\(nanoseconds),\(params.count)")
                    print(
                        "bf16x4_timing family=\(family) order=\(orderName) " +
                        "cycle=\(cycle) slot=\(slot) variant=\(variantName) " +
                        "ns=\(nanoseconds) kernels=\(params.count)")
                }
            }
        }
    }

    private func materialize(
        params: [MLXArray], make: (MLXArray) -> MLXArray
    ) {
        let outputs = params.map(make)
        eval(outputs)
        Stream.gpu.synchronize()
    }

    private func timeBatch(
        params: [MLXArray], make: (MLXArray) -> MLXArray
    ) -> UInt64 {
        let outputs = params.map(make)
        let start = DispatchTime.now().uptimeNanoseconds
        eval(outputs)
        Stream.gpu.synchronize()
        return DispatchTime.now().uptimeNanoseconds - start
    }

    private func deterministicBF16(shape: [Int], phase: Float) -> MLXArray {
        let count = shape.reduce(1, *)
        let axis = MLXArray(0..<count).asType(.float32)
        return (sin(axis * 0.0013 + phase) * 0.125)
            .asType(.bfloat16)
            .reshaped(shape)
    }

    private func deterministicWeight(phase: Float) -> MLXArray {
        let axis = MLXArray(0..<headDim).asType(.float32)
        return (cos(axis * 0.017 + phase) * 0.25 + 1.0).asType(.bfloat16)
    }

    private func identityAngles(rotaryDimensions: Int) -> MLXArray {
        let half = rotaryDimensions / 2
        return MLXArray(
            Array(repeating: Float(1), count: half)
                + Array(repeating: Float(0), count: half)
        ).reshaped([1, 1, 1, rotaryDimensions])
    }
}
