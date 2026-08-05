static inline float laguna_tail_nvfp4_scale(uint8_t bits) {
    ushort raw = ushort(bits) << 7;
        return float(as_type<half>(raw));
}

static inline float laguna_tail_nvfp4_qdot(
    const device uint8_t* w,
    const thread float* x_thread,
    float scale
) {
    float accum;
    const device uint2* wq = (const device uint2*)w;
    const uint2 codes = wq[0];
#pragma unroll
    for (int j = 0; j < 2; j++) {
        const uint32_t c = (j == 0) ? codes.x : codes.y;
        // Split-nibble decode: the same eight `half` bit patterns per
        // code word as the original shift+mask sequence, in fewer
        // integer ops with three mask constants instead of eight — the
        // form the current stock `fp_qmv_fast` compiles (every form is
        // an OR of masked shifts, so the decode is bit-identical).
        const uint32_t xe = c & 0x0F0F0F0Fu;
        const uint32_t ge = xe | (xe << 3);
        const uint32_t yo = c & 0xF0F0F0F0u;
        const uint32_t go = yo | (yo >> 3);
        const uint32_t p0 = (ge << 9) & 0x8E008E00u;
        const uint32_t p1 = (go << 8) & 0x8E008E00u;
        const uint32_t p2 = (ge << 1) & 0x8E008E00u;
        const uint32_t p3 = go & 0x8E008E00u;
        const float2 v04 = float2(as_type<half2>(p0));
        const float2 v15 = float2(as_type<half2>(p1));
        const float2 v26 = float2(as_type<half2>(p2));
        const float2 v37 = float2(as_type<half2>(p3));
        if (j == 0) {
                accum =
                    (x_thread[8 * j] * v04.x +
                     x_thread[8 * j + 1] * v15.x +
                     x_thread[8 * j + 2] * v26.x +
                     x_thread[8 * j + 3] * v37.x);
            } else {
                accum +=
                    (x_thread[8 * j] * v04.x +
                     x_thread[8 * j + 1] * v15.x +
                     x_thread[8 * j + 2] * v26.x +
                     x_thread[8 * j + 3] * v37.x);
            }
        accum +=
            (x_thread[8 * j + 4] * v04.y +
             x_thread[8 * j + 5] * v15.y +
             x_thread[8 * j + 6] * v26.y +
             x_thread[8 * j + 7] * v37.y);
    }
    return scale * accum;
}[[kernel]] void custom_kernel_laguna_decode_nvfp4_qkv_h64_r1_v1_se1_sd1_bfloat16_t_uint32_t_uint8_t_bfloat16_t(
  const device bfloat16_t* normalized [[buffer(0)]],
  const device uint32_t* weight_codes [[buffer(1)]],
  const device uint8_t* weight_scales [[buffer(2)]],
  device bfloat16_t* projected [[buffer(3)]],
  uint simdgroup_index_in_threadgroup [[simdgroup_index_in_threadgroup]],
  uint thread_index_in_simdgroup [[thread_index_in_simdgroup]],
  uint3 threadgroup_position_in_grid [[threadgroup_position_in_grid]]) {
constexpr uint axis_size = 2048;
constexpr uint num_simdgroups = 2;
constexpr uint values_per_thread = 16;
constexpr uint block_size = 512;
constexpr uint in_vec_size_w = axis_size / 2;
constexpr uint in_vec_size_g = axis_size / 16;

uint tile = threadgroup_position_in_grid.x;
uint simd_gid = simdgroup_index_in_threadgroup;
uint simd_lid = thread_index_in_simdgroup;
uint out_row = tile * num_simdgroups + simd_gid;

const device uint8_t* ws = (const device uint8_t*)weight_codes +
    out_row * in_vec_size_w + simd_lid * 8;
const device uint8_t* sc = weight_scales +
    out_row * in_vec_size_g + simd_lid;

thread float x_thread[values_per_thread];
thread float result = 0.0f;

uint column = simd_lid * values_per_thread;
for (uint k = 0; k < axis_size; k += block_size) {
    for (uint i = 0; i < values_per_thread; ++i) {
        x_thread[i] = float(normalized[column + i]);
    }
    result += laguna_tail_nvfp4_qdot(
        ws, x_thread, laguna_tail_nvfp4_scale(sc[0]));
    ws += block_size / 2;
    sc += block_size / 16;
    column += block_size;
}

result = simd_sum(result * 4194304.0f);
if (simd_lid == 0) {
    projected[out_row] = bfloat(result);
}
}

