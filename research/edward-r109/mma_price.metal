// R109-D stage 0c: price one simdgroup_float8x8 multiply-accumulate in native
// AGX instructions on both architectures.
//
// The MMA hypothesis for the decode QK reduction only pays if the MMA is a real
// hardware instruction on the ranked arch. If the compiler emulates it with
// shuffles and FMAs, an MMA-shaped QK tile can never beat the 32-lane
// `simd_sum` formulation it replaces.
//
// Each arm chains N MMAs through the accumulator so none can be CSE'd - the
// failure mode that invalidated research/host_flop_ceiling.swift.
//
//   bash senpai/tools/agx-census-probe/census.sh research/edward-r109/mma_price.metal
#include <metal_stdlib>
#include <metal_simdgroup>
#include <metal_simdgroup_matrix>
using namespace metal;

#define MMA_ARM(N)                                                            \
  [[kernel]] void mma_x##N(const device float* in [[buffer(0)]],              \
                           device float* out [[buffer(1)]],                   \
                           uint tg [[threadgroup_position_in_grid]]) {        \
    simdgroup_float8x8 a, b, c;                                               \
    simdgroup_load(a, in + 64 * tg, 8);                                       \
    simdgroup_load(b, in + 64 * tg + 64, 8);                                  \
    simdgroup_load(c, in + 64 * tg + 128, 8);                                 \
    for (uint i = 0; i < N; ++i) {                                            \
      simdgroup_multiply_accumulate(c, a, c, b);                              \
    }                                                                         \
    simdgroup_store(c, out + 64 * tg, 8);                                     \
  }

MMA_ARM(0)
MMA_ARM(1)
MMA_ARM(2)
MMA_ARM(4)
MMA_ARM(8)
MMA_ARM(16)

// Scalar reference at matched signature: N chained 32-lane FMA + simd_sum
// rounds, i.e. the shape the current kernel uses for one key row.
#define SUM_ARM(N)                                                            \
  [[kernel]] void sum_x##N(const device float* in [[buffer(0)]],              \
                           device float* out [[buffer(1)]],                   \
                           uint tg [[threadgroup_position_in_grid]],          \
                           uint lane [[thread_index_in_simdgroup]]) {         \
    float q = in[64 * tg + lane];                                             \
    float k = in[64 * tg + 32 + lane];                                        \
    float s = 0.0f;                                                           \
    for (uint i = 0; i < N; ++i) {                                            \
      s = simd_sum(q * k + s);                                                \
      q = q + s;                                                              \
    }                                                                         \
    out[64 * tg + lane] = s + q;                                              \
  }

SUM_ARM(0)
SUM_ARM(1)
SUM_ARM(2)
SUM_ARM(4)
SUM_ARM(8)
SUM_ARM(16)
