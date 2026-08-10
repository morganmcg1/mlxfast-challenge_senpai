#include <metal_stdlib>
#include <metal_simdgroup>
using namespace metal;

[[kernel]] void oproj_g3_h48(
  const device bfloat* attention_output [[buffer(0)]],
  const device bfloat* gate_values [[buffer(1)]],
  const device uint32_t* weight_codes [[buffer(2)]],
  const device uint8_t* scale_nibbles [[buffer(3)]],
  const device uint8_t* scale_bases [[buffer(4)]],
  const device uint8_t* weight_scales [[buffer(5)]],
  device bfloat* projected [[buffer(6)]],
  uint3 threadgroup_position_in_grid [[threadgroup_position_in_grid]],
  uint3 thread_position_in_threadgroup [[thread_position_in_threadgroup]],
  uint simdgroup_index_in_threadgroup [[simdgroup_index_in_threadgroup]],
  uint thread_index_in_simdgroup [[thread_index_in_simdgroup]]) {
constexpr uint in_vec_size = 6144;
constexpr uint out_vec_size = 2048;
constexpr uint gate_heads = 48;
constexpr uint head_shift = 7;
constexpr uint group_size = 16;
constexpr uint values_per_thread = 16;
constexpr uint codes_per_thread = values_per_thread / 8;
constexpr uint block_size = values_per_thread * 32;
constexpr uint results_per_simdgroup = 4;
constexpr uint num_simdgroups = 4;
constexpr uint in_vec_size_g = in_vec_size / group_size;

uint tile = threadgroup_position_in_grid.x;
uint lid = thread_position_in_threadgroup.x;
uint simd_gid = simdgroup_index_in_threadgroup;
uint simd_lid = thread_index_in_simdgroup;



uint out_row = tile * (num_simdgroups * results_per_simdgroup) +
    simd_gid * results_per_simdgroup;
const device uint32_t* ws =
    (const device uint32_t*)weight_codes +
    out_row * (in_vec_size / 8) + simd_lid * codes_per_thread;
const device uint8_t* nq = scale_nibbles +
    out_row * (in_vec_size_g / 4) +
    (simd_lid >> 1) * (in_vec_size_g / 64);
const device uint8_t* bs = scale_bases + out_row;
const device uint8_t* sc = weight_scales +
    out_row * in_vec_size_g + simd_lid;
uint nsh = 0;
const device bfloat* xp = attention_output + simd_lid * values_per_thread;

thread float x_thread[values_per_thread];
thread float result[results_per_simdgroup] = {0.0f, 0.0f, 0.0f, 0.0f};

uint column = simd_lid * values_per_thread;
for (uint k = 0; k < in_vec_size; k += block_size) {
    float g=float(gate_values[column>>head_shift]);
for(uint i=0;i<values_per_thread;++i)
    x_thread[i]=float(bfloat(float(xp[i])*g));

    for (uint row = 0; row < results_per_simdgroup; ++row) {
        const device uint32_t* wl = ws + row * (in_vec_size / 8);
        const uint8_t rb = bs[row];
    const bool esc = rb == 0xFFu;
    const device uint8_t* sp = esc
        ? (sc + row * in_vec_size_g)
        : (nq + row * (in_vec_size_g / 4));
    const uint8_t raw = sp[0];
    uint8_t sbits = esc ? raw : uint8_t(rb + ((raw >> nsh) & 0x0Fu));
        ushort sraw = ushort(sbits) << 7;
        float scale = float(as_type<half>(sraw));
        float accum;
        #pragma unroll
        for (uint j = 0; j < codes_per_thread; ++j) {
            const uint c = wl[j];
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
        result[row] += scale * accum;
    }

    ws += block_size / 8;
    sc += block_size / group_size;
nq += nsh >> 2;
nsh ^= 4;
    xp += block_size;
    column += block_size;
}

for (uint row = 0; row < results_per_simdgroup; ++row) {
    result[row] = simd_sum(result[row] * 4194304.0f);
    if (simd_lid == 0) {
        projected[out_row + row] = bfloat(result[row]);
    }
}
}
