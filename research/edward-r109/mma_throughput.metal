// R109-D stage 0d: what does a simdgroup MMA MAC cost relative to a scalar FMA
// MAC on this host?
//
// The decode QK product is M=2 (one query per head of a GQA pair), so an 8x8x8
// MMA wastes 6 of its 8 M rows and executes 4x the useful MACs. The MMA
// reformulation can only win if an MMA MAC is meaningfully cheaper than a
// scalar FMA MAC. This file measures both peak rates directly.
//
// Every arm keeps N independent dependency chains with distinct seeds. Identical
// seeds are what silently turned 3 of the 4 chains in
// research/host_flop_ceiling.swift into dead code, so its MMA number is invalid.
#include <metal_stdlib>
#include <metal_simdgroup>
#include <metal_simdgroup_matrix>
using namespace metal;

// N independent scalar FMA chains: 2 FLOP each per loop.
#define FMA_ARM(N)                                                            \
  kernel void fma_f32_x##N(device float* out [[buffer(0)]],                   \
                           device atomic_uint* trips [[buffer(1)]],           \
                           constant uint& loops [[buffer(2)]],                \
                           uint gid [[thread_position_in_grid]]) {            \
    float b = 1.0f + 1e-7f * float(gid);                                      \
    float a[N];                                                               \
    for (uint j = 0; j < N; ++j) a[j] = float(j) + 0.5f;                      \
    uint n = 0;                                                               \
    for (; n < loops; ++n) {                                                  \
      for (uint j = 0; j < N; ++j) a[j] = fma(a[j], b, 0.5f);                 \
    }                                                                         \
    float s = 0.0f;                                                           \
    for (uint j = 0; j < N; ++j) s += a[j];                                   \
    out[gid & 1023] = s;                                                      \
    if (gid == 0) atomic_store_explicit(trips, n, memory_order_relaxed);      \
  }

FMA_ARM(1)
FMA_ARM(4)
FMA_ARM(8)
FMA_ARM(16)

// N independent MMA chains: 8*8*8 MACs = 1024 FLOP each per loop per simdgroup.
#define MMA_ARM(N)                                                            \
  kernel void mma_bf16_x##N(device float* out [[buffer(0)]],                  \
                            device atomic_uint* trips [[buffer(1)]],          \
                            constant uint& loops [[buffer(2)]],               \
                            uint gid [[thread_position_in_grid]]) {           \
    /* A is refilled from a scalar recurrence every iteration. With A and B    \
       both loop-invariant the compiler strength-reduces the whole chain to    \
       one product plus a scale and the reported rate is fiction; the arm      \
       times then stay flat as N grows, which is the tell. */                  \
    float av = 0.001f + 1e-9f * float(gid);                                   \
    simdgroup_matrix<bfloat, 8, 8> B = make_filled_simdgroup_matrix<bfloat,    \
        8, 8>(bfloat(0.002f + 1e-9f * float(gid)));                           \
    simdgroup_matrix<float, 8, 8> c[N];                                       \
    for (uint j = 0; j < N; ++j)                                              \
      c[j] = make_filled_simdgroup_matrix<float, 8, 8>(float(j) + 0.5f);      \
    uint n = 0;                                                               \
    simdgroup_matrix<bfloat, 8, 8> A = B;                                     \
    for (; n < loops; ++n) {                                                  \
      av = fma(av, 1.0000001f, 1e-9f);                                        \
      A = make_filled_simdgroup_matrix<bfloat, 8, 8>(bfloat(av));             \
      for (uint j = 0; j < N; ++j)                                            \
        simdgroup_multiply_accumulate(c[j], A, B, c[j]);                       \
    }                                                                         \
    simdgroup_matrix<float, 8, 8> acc = c[0];                                 \
    for (uint j = 1; j < N; ++j)                                              \
      simdgroup_multiply_accumulate(acc, A, B, c[j]);                         \
    simdgroup_store(acc, out + 64 * (gid / 32), 8);                           \
    if (gid == 0) atomic_store_explicit(trips, n, memory_order_relaxed);      \
  }

MMA_ARM(1)
MMA_ARM(2)
MMA_ARM(4)
MMA_ARM(8)
MMA_ARM(16)
