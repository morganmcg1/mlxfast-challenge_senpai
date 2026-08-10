#include <metal_stdlib>
using namespace metal;
typedef bfloat bfloat16_t;

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

[[kernel]] void laguna_routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6(
  const device bfloat16_t* routed_activated [[buffer(0)]],
  const device uint32_t* routed_down_weight [[buffer(1)]],
  const device uint8_t* routed_down_scales [[buffer(2)]],
  const device uint32_t* indices [[buffer(3)]],
  const device float* router_weights [[buffer(4)]],
  const device bfloat16_t* shared_activated [[buffer(5)]],
  const device uint32_t* shared_down_weight [[buffer(6)]],
  const device uint8_t* shared_down_scales [[buffer(7)]],
  const device bfloat16_t* residual [[buffer(8)]],
  device bfloat16_t* output [[buffer(9)]],
  uint3 threadgroup_position_in_grid [[threadgroup_position_in_grid]],
  uint simdgroup_index_in_threadgroup [[simdgroup_index_in_threadgroup]],
  uint thread_index_in_simdgroup [[thread_index_in_simdgroup]]) {
constexpr uint input_width = 512;
constexpr uint output_width = 2048;
constexpr uint routed_experts = 8;
constexpr uint shared_slot = 8;
constexpr uint outputs_per_simd = 4;
constexpr uint values_per_lane = 16;
constexpr uint packed_row_bytes = 256;
constexpr uint scale_patch_bytes = 128;
constexpr uint shared_scale_row_bytes = 16;
constexpr uint routed_scale_row_bytes = 16;
constexpr uint packed_expert_bytes =
    output_width * packed_row_bytes;
constexpr uint scale_expert_bytes =
    output_width * routed_scale_row_bytes;

uint tile = threadgroup_position_in_grid.x;
uint slot = simdgroup_index_in_threadgroup;
uint lane = thread_index_in_simdgroup;
uint first_row = tile * outputs_per_simd;
bool is_shared = slot == shared_slot;
uint expert = is_shared ? 0 : uint(indices[slot]);

const device bfloat* expert_input = is_shared
    ? shared_activated
    : routed_activated + slot * input_width;
const device uint8_t* expert_weight = is_shared
    ? (const device uint8_t*)shared_down_weight
    : (const device uint8_t*)routed_down_weight +
        expert * packed_expert_bytes;
const device uint8_t* expert_scales = is_shared
    ? shared_down_scales + scale_patch_bytes
    : routed_down_scales + scale_patch_bytes
        + expert * scale_expert_bytes;
uint scale_row_bytes =
    is_shared ? shared_scale_row_bytes : routed_scale_row_bytes;
uint scale_lane = (lane >> 1);

thread float input_values[values_per_lane];
const device vec<bfloat, 4>* input_vectors =
    (const device vec<bfloat, 4>*)(
        expert_input + lane * values_per_lane);
for (uint i = 0; i < values_per_lane / 4; ++i) {
    const vec<bfloat, 4> values = input_vectors[i];
    input_values[4 * i] = values[0];
    input_values[4 * i + 1] = values[1];
    input_values[4 * i + 2] = values[2];
    input_values[4 * i + 3] = values[3];
}

thread float result[outputs_per_simd] = {0.0f};
uint2 row_codes[outputs_per_simd];
uint8_t row_sb[outputs_per_simd];
for (uint row = 0; row < outputs_per_simd; ++row) {
    uint output_row = first_row + row;
    row_codes[row] = *(const device uint2*)(
        expert_weight + output_row * packed_row_bytes + lane * 8);
    const device uint8_t* scale =
        expert_scales + output_row * scale_row_bytes + scale_lane;
    row_sb[row] =
        (output_row == 0 && lane == 1 && (is_shared || expert == 0))
        ? (is_shared ? shared_down_scales[0] : routed_down_scales[0])
        : scale[0];
}
for (uint row = 0; row < outputs_per_simd; ++row) {
    result[row] = laguna_nvfp4_qdot_codes_16(
        row_codes[row],
        input_values,
        laguna_nvfp4_scale(row_sb[row]));
    result[row] = simd_sum(result[row]);
}

threadgroup bfloat down_outputs[
    (routed_experts + 1) * outputs_per_simd
];
if (lane == 0) {
    for (uint row = 0; row < outputs_per_simd; ++row) {
        down_outputs[slot * outputs_per_simd + row] =
            bfloat(result[row] * 4194304.0f);
    }
}
threadgroup_barrier(mem_flags::mem_threadgroup);

if (slot == 0 && lane < outputs_per_simd) {
    bfloat routed_total = bfloat(0);
    for (uint routed_slot = 0;
         routed_slot < routed_experts;
         ++routed_slot) {
        bfloat route_weight =
            bfloat(router_weights[routed_slot]);
        bfloat product = bfloat(
            down_outputs[
                routed_slot * outputs_per_simd + lane
            ] * route_weight);
        routed_total = bfloat(product + routed_total);
    }
    bfloat routed = bfloat(
        routed_total * bfloat(2.5f));
    bfloat shared =
        down_outputs[shared_slot * outputs_per_simd + lane];
    bfloat r2 = bfloat(routed + shared);
    output[first_row + lane] =
        bfloat(residual[first_row + lane] + r2);
}}
