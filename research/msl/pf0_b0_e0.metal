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