#include <metal_stdlib>
#include <metal_simdgroup>
using namespace metal;
typedef bfloat bfloat16_t;

namespace metal {
METAL_FUNC bfloat16_t abs(bfloat16_t x) {
  return static_cast<bfloat16_t>(
      __metal_fabs(static_cast<float>(x), __METAL_MAYBE_FAST_MATH__));
}
METAL_FUNC bfloat16_t exp(bfloat16_t x) {
  return static_cast<bfloat16_t>(
      __metal_exp(static_cast<float>(x), __METAL_MAYBE_FAST_MATH__));
}
}

static inline float laguna_nvfp4_scale(uint8_t bits) {
if (bits < 16u) {
    ushort fast_raw = ushort(bits) << 7;
    return float(as_type<half>(fast_raw));
}
    ushort raw = ushort(uint(bits) << 7);
    half converted = as_type<half>(raw);
    half signed_value = converted;
        return float(signed_value);
}

static inline float laguna_nvfp4_qdot_codes_16(
    uint2 codes,
    const thread float* input,
    float scale
) {
    float accum;
    {
        const uint c = codes.x;
        const uint xe = c & 0x0F0F0F0Fu;
        const uint ge = xe | (xe << 3);
        const uint yo = c & 0xF0F0F0F0u;
        const uint go = yo | (yo >> 3);
        const uint p0 = (ge << 9) & 0x8E008E00u;
        const uint p1 = (go << 8) & 0x8E008E00u;
        const uint p2 = (ge << 1) & 0x8E008E00u;
        const uint p3 = go & 0x8E008E00u;
        const float2 v04 = float2(as_type<half2>(p0));
        const float2 v15 = float2(as_type<half2>(p1));
        const float2 v26 = float2(as_type<half2>(p2));
        const float2 v37 = float2(as_type<half2>(p3));
        accum =
            (input[0] * v04.x +
             input[1] * v15.x +
             input[2] * v26.x +
             input[3] * v37.x);
        accum +=
            (input[4] * v04.y +
             input[5] * v15.y +
             input[6] * v26.y +
             input[7] * v37.y);
    }
    {
        const uint c = codes.y;
        const uint xe = c & 0x0F0F0F0Fu;
        const uint ge = xe | (xe << 3);
        const uint yo = c & 0xF0F0F0F0u;
        const uint go = yo | (yo >> 3);
        const uint p0 = (ge << 9) & 0x8E008E00u;
        const uint p1 = (go << 8) & 0x8E008E00u;
        const uint p2 = (ge << 1) & 0x8E008E00u;
        const uint p3 = go & 0x8E008E00u;
        const float2 v04 = float2(as_type<half2>(p0));
        const float2 v15 = float2(as_type<half2>(p1));
        const float2 v26 = float2(as_type<half2>(p2));
        const float2 v37 = float2(as_type<half2>(p3));
        accum +=
            (input[8] * v04.x +
             input[9] * v15.x +
             input[10] * v26.x +
             input[11] * v37.x);
        accum +=
            (input[12] * v04.y +
             input[13] * v15.y +
             input[14] * v26.y +
             input[15] * v37.y);
    }
    return scale * accum;
}

static inline float laguna_nvfp4_qdot_16(
    const device uint8_t* weight,
    const thread float* input,
    float scale
) {
    const device uint2* packed = (const device uint2*)weight;
    return laguna_nvfp4_qdot_codes_16(packed[0], input, scale);
}
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
METAL_FUNC uint laguna_router_top8_extract_round(
    thread const uint* keys, thread uint& mask, uint lane) {
    uint best_ordinal = 0xFFFFFFFFu;
    uint best_index = 256u;
    for (uint j = 0; j < 8; ++j) {
        if ((mask & (1u << j)) != 0u) continue;
        uint e = lane + 32u * j;
        uint o = keys[j];
        if (laguna_router_ordinal_before(o, e, best_ordinal, best_index)) {
            best_ordinal = o;
            best_index = e;
        }
    }
    // Transport the comparator's (ordinal, expert-index) state as one uint2
    // through each butterfly step. simd_shuffle_xor moves both components
    // bit-for-bit from the same source lane; comparator order is unchanged.
    uint2 best_pair = uint2(best_ordinal, best_index);
    for (ushort offset = 16; offset > 0; offset >>= 1) {
        const uint2 other_pair = simd_shuffle_xor(best_pair, offset);
        if (laguna_router_ordinal_before(
            other_pair.x, other_pair.y, best_pair.x, best_pair.y)) {
            best_pair = other_pair;
        }
    }
    best_index = best_pair.y;
    if ((best_index & 31u) == lane) {
        mask |= 1u << (best_index >> 5u);
    }
    return best_index;
}
[[kernel]] void custom_kernel_laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2(
  const device bfloat16_t* input [[buffer(0)]],
  const device uint32_t* fused_weight [[buffer(1)]],
  const device uint8_t* packed_scales [[buffer(2)]],
  const device uint32_t* router_keys [[buffer(3)]],
  device bfloat16_t* activated [[buffer(4)]],
  uint simdgroup_index_in_threadgroup [[simdgroup_index_in_threadgroup]],
  uint thread_index_in_simdgroup [[thread_index_in_simdgroup]],
  uint3 threadgroup_position_in_grid [[threadgroup_position_in_grid]]) {
constexpr uint input_width = 2048;
constexpr uint output_width = 512;
constexpr uint block_width = 512;
constexpr uint values_per_lane = 16;
constexpr uint routed_experts = 8;
constexpr uint fused_row_bytes = 1024;
constexpr uint fused_expert_bytes = 1024 * fused_row_bytes;
constexpr uint scale_patch_bytes = 128;
constexpr uint scale_row_bytes = 16;
constexpr uint scale_sub_bytes = 8 * scale_row_bytes;
constexpr uint scale_kblock_bytes = scale_sub_bytes;
constexpr uint scale_tile_bytes = 4 * scale_kblock_bytes;
constexpr uint packed_expert_bytes = 128 * scale_tile_bytes;

uint group = threadgroup_position_in_grid.x;
uint expert_slot = group % routed_experts;
uint tile = group / routed_experts;
uint simd_group = simdgroup_index_in_threadgroup;
uint lane = thread_index_in_simdgroup;
uint logical_row = tile * 2 + simd_group;
thread uint top8_keys[8];
    for (uint j = 0; j < 8; ++j) {
        top8_keys[j] = router_keys[lane + 32u * j];
    }
    uint top8_mask = 0u;
    uint top8_winner = 0u;
    for (uint r = 0; r <= expert_slot; ++r) {
        top8_winner = laguna_router_top8_extract_round(
            top8_keys, top8_mask, lane);
    }
uint expert = top8_winner;

const device uint8_t* expert_weight =
    (const device uint8_t*)fused_weight + expert * fused_expert_bytes;
const device uint8_t* row_scales =
    packed_scales + scale_patch_bytes + expert * packed_expert_bytes
    + (logical_row / 4) * scale_tile_bytes;
uint sub = logical_row % 4;
uint gate_row = (logical_row / 32) * 64 + logical_row % 32;
uint up_row = gate_row + 32;

thread float gate_result = 0.0f;
thread float up_result = 0.0f;
thread float input_values[values_per_lane];

uint2 gate_codes;
uint2 up_codes;
uint8_t gate_sb;
uint8_t up_sb;
{
    const device uint8_t* first_scales =
        row_scales + sub * 2 * scale_row_bytes + (lane >> 1);
    bool patch_lane = expert == 0 && logical_row == 0 && lane == 1;
    gate_sb = patch_lane ? packed_scales[0] : first_scales[0];
    up_sb = patch_lane ? packed_scales[1] : first_scales[scale_row_bytes];
    gate_codes = *(const device uint2*)(
        expert_weight + gate_row * fused_row_bytes + lane * 8);
    up_codes = *(const device uint2*)(
        expert_weight + up_row * fused_row_bytes + lane * 8);
}

for (uint block = 0; block < input_width; block += block_width) {
    const device vec<bfloat, 4>* input_vectors =
        (const device vec<bfloat, 4>*) (
            input + block + lane * values_per_lane);
    for (uint i = 0; i < values_per_lane / 4; ++i) {
        const vec<bfloat, 4> values = input_vectors[i];
        input_values[4 * i] = values[0];
        input_values[4 * i + 1] = values[1];
        input_values[4 * i + 2] = values[2];
        input_values[4 * i + 3] = values[3];
    }

    const uint2 cur_gate_codes = gate_codes;
    const uint2 cur_up_codes = up_codes;
    const uint8_t cur_gate_sb = gate_sb;
    const uint8_t cur_up_sb = up_sb;
    const uint next_block = block + block_width;
    if (next_block < input_width) {
        const device uint8_t* next_scales =
            row_scales + (next_block / block_width) * scale_kblock_bytes
            + sub * 2 * scale_row_bytes + (lane >> 1);
        gate_sb = next_scales[0];
        up_sb = next_scales[scale_row_bytes];
        gate_codes = *(const device uint2*)(
            expert_weight + gate_row * fused_row_bytes
            + next_block / 2 + lane * 8);
        up_codes = *(const device uint2*)(
            expert_weight + up_row * fused_row_bytes
            + next_block / 2 + lane * 8);
    }

    // [R107-G dose=16] 16 rounds x 8 independent fp32 fma, seeded from
    // this iteration's live input_values, sunk through an unreachable compare.
    {
        float dz0 = input_values[0];
        float dz1 = input_values[1];
        float dz2 = input_values[2];
        float dz3 = input_values[3];
        float dz4 = input_values[4];
        float dz5 = input_values[5];
        float dz6 = input_values[6];
        float dz7 = input_values[7];
        for (int dd = 0; dd < 16; ++dd) {
            dz0 = metal::fma(dz0, 1.0000001f, 1e-6f);
            dz1 = metal::fma(dz1, 1.0000001f, 1e-6f);
            dz2 = metal::fma(dz2, 1.0000001f, 1e-6f);
            dz3 = metal::fma(dz3, 1.0000001f, 1e-6f);
            dz4 = metal::fma(dz4, 1.0000001f, 1e-6f);
            dz5 = metal::fma(dz5, 1.0000001f, 1e-6f);
            dz6 = metal::fma(dz6, 1.0000001f, 1e-6f);
            dz7 = metal::fma(dz7, 1.0000001f, 1e-6f);
        }
        float dzs = ((dz0 + dz1) + (dz2 + dz3)) + ((dz4 + dz5) + (dz6 + dz7));
        if (dzs == 1e37f) { gate_result += 1.0f; }
    }
    gate_result += laguna_nvfp4_qdot_codes_16(
        cur_gate_codes, input_values,
        laguna_nvfp4_scale(cur_gate_sb));
    up_result += laguna_nvfp4_qdot_codes_16(
        cur_up_codes, input_values,
        laguna_nvfp4_scale(cur_up_sb));
}

gate_result = simd_sum(gate_result);
up_result = simd_sum(up_result);
if (lane == 0) {
    bfloat gate = bfloat(gate_result * 4194304.0f);
    bfloat up = bfloat(up_result * 4194304.0f);
    bfloat exp_abs = metal::exp(metal::abs(gate));
    bfloat denominator = bfloat(1) + exp_abs;
    bfloat y = bfloat(1) / denominator;
    bfloat sigmoid = gate < bfloat(0) ? y : bfloat(1) - y;
    bfloat silu = bfloat(gate * sigmoid);
    activated[expert_slot * output_width + logical_row] =
        bfloat(silu * up);
}
}
