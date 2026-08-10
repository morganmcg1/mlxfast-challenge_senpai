#include <metal_stdlib>
#include <metal_simdgroup>
using namespace metal;
typedef bfloat bfloat16_t;

METAL_FUNC uint laguna_router_key_ordinal(float key) {
    uint bits = as_type<uint>(key);
    uint magnitude = bits & 0x7FFFFFFFu;
    if (magnitude > 0x7F800000u) {
        return 0xFFFFFFFFu;
    }
    if (magnitude == 0u) {
        return 0x80000000u;
    }
    return (bits & 0x80000000u) != 0u ? ~bits : (bits ^ 0x80000000u);
}

METAL_FUNC bool laguna_router_ordinal_before(
    uint a, uint a_index, uint b, uint b_index) {
    if (a < b) {
        return true;
    }
    if (b < a) {
        return false;
    }
    return a_index < b_index;
}

[[kernel]] void custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf0(
  const device bfloat16_t* residual [[buffer(0)]],
  const device bfloat16_t* branch [[buffer(1)]],
  const device bfloat16_t* weight [[buffer(2)]],
  const device bfloat16_t* router_weight [[buffer(3)]],
  const device bfloat16_t* correction_bias [[buffer(4)]],
  device bfloat16_t* summed [[buffer(5)]],
  device bfloat16_t* normalized [[buffer(6)]],
  device bfloat16_t* router_logits [[buffer(7)]],
  device uint* router_keys [[buffer(8)]],
  uint3 threadgroup_position_in_grid [[threadgroup_position_in_grid]],
  uint3 thread_position_in_threadgroup [[thread_position_in_threadgroup]],
  uint thread_index_in_simdgroup [[thread_index_in_simdgroup]],
  uint simdgroup_index_in_threadgroup [[simdgroup_index_in_threadgroup]]) {
constexpr uint axis_size = 2048;
constexpr uint n_reads = 4;
constexpr uint simd_size = 32;
constexpr uint rows_per_group = 8;
constexpr uint rows_per_thread = 1;
constexpr uint active_simd_groups = 8;
constexpr uint block_width = 128;
constexpr uint router_blocks = axis_size / block_width;

uint tile = threadgroup_position_in_grid.x;
uint lid = thread_position_in_threadgroup.x;
uint simd_lane = thread_index_in_simdgroup;
uint simd_group = simdgroup_index_in_threadgroup;
uint base = lid * n_reads;

threadgroup float local_inv_mean[1];
threadgroup float local_sums[simd_size];
threadgroup bfloat normalized_row[axis_size];

thread bfloat values[n_reads];
float acc = 0.0f;
for (uint i = 0; i < n_reads; ++i) {
    bfloat value = bfloat(residual[base + i] + branch[base + i]);
    values[i] = value;
    if (tile == 0) {
        summed[base + i] = value;
    }
    float fv = float(value);
    acc += fv * fv;
}

acc = simd_sum(acc);
if (simd_group == 0) {
            local_sums[simd_lane] = 0.0f;
        }
        threadgroup_barrier(mem_flags::mem_threadgroup);
        if (simd_lane == 0) {
            local_sums[simd_group] = acc;
        }
        threadgroup_barrier(mem_flags::mem_threadgroup);
        if (simd_group == 0) {
            acc = simd_sum(local_sums[simd_lane]);
            if (simd_lane == 0) {
                local_inv_mean[0] = metal::precise::rsqrt(acc / 2048.0f + 1.0e-6f);
            }
        }
        threadgroup_barrier(mem_flags::mem_threadgroup);
        float laguna_inv_mean = local_inv_mean[0];

for (uint i = 0; i < n_reads; ++i) {
    bfloat value =
        weight[base + i] *
        bfloat(float(values[i]) * laguna_inv_mean);
    normalized_row[base + i] = value;
    if (tile == 0) {
        normalized[base + i] = value;
    }
}
threadgroup_barrier(mem_flags::mem_threadgroup);

        if (simd_group < active_simd_groups) {
uint router_row = tile * rows_per_group + simd_group * rows_per_thread;
thread float router_result[rows_per_thread] = {0.0f};
        uint column = simd_lane * n_reads;
        for (uint block = 0; block < router_blocks; block += 4) {
            vec<bfloat, 4> rw[4];
            for (uint u = 0; u < 4; ++u) {
                const device vec<bfloat, 4>* row_values =
                    (const device vec<bfloat, 4>*)(
                        router_weight + router_row * axis_size +
                            column + u * block_width);
                rw[u] = row_values[0];
            }
            for (uint u = 0; u < 4; ++u) {
                uint column_u = column + u * block_width;
                for (uint i = 0; i < n_reads; ++i) {
                    router_result[0] += float(rw[u][i]) *
                        float(normalized_row[column_u + i]);
                }
            }
            column += 4 * block_width;
        }

for (uint r = 0; r < rows_per_thread; ++r) {
    for (ushort delta = 16; delta >= 1; delta >>= 1) {
        router_result[r] +=
            metal::simd_shuffle_down(router_result[r], delta);
    }
}
if (simd_lane == 0) {
    for (uint r = 0; r < rows_per_thread; ++r) {
                bfloat logit = bfloat(router_result[r]);
        router_logits[router_row + r] = logit;
        float x = float(logit);
        float y = 1.0f / (1.0f + metal::exp(metal::abs(x)));
        float score = x < 0.0f ? y : 1.0f - y;
        router_keys[router_row + r] = laguna_router_key_ordinal(
            -(score + float(correction_bias[router_row + r])));
    }
}
        }
}
