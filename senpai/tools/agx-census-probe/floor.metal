// In-session arch-floor probe (research only; not part of the submission).
//
// Rule 42 states the AGX per-entry-point __compute floor differs between
// applegpu_g16s and applegpu_g17s by a constant 16 bytes, and that a census
// delta must be floor-corrected before the 16-byte noise band is applied.
// This file re-derives that constant in-session instead of inheriting it, at
// several buffer-signature shapes, so the correction used in the r92-b decode
// census rests on a measurement from the same toolchain invocation.
//
// Each kernel does the minimum work that still forces a store, so __compute
// holds the prologue/epilogue floor plus a near-constant handful of bytes.

#include <metal_stdlib>
using namespace metal;

[[kernel]] void floor_buf1(
    device float* out [[buffer(0)]],
    uint tid [[thread_position_in_grid]]) {
  out[tid] = 0.0f;
}

[[kernel]] void floor_buf2(
    const device float* in [[buffer(0)]],
    device float* out [[buffer(1)]],
    uint tid [[thread_position_in_grid]]) {
  out[tid] = in[tid];
}

[[kernel]] void floor_buf4(
    const device float* a [[buffer(0)]],
    const device float* b [[buffer(1)]],
    const device float* c [[buffer(2)]],
    device float* out [[buffer(3)]],
    uint tid [[thread_position_in_grid]]) {
  out[tid] = a[tid] + b[tid] + c[tid];
}

[[kernel]] void floor_buf4_bf16(
    const device bfloat* a [[buffer(0)]],
    const device bfloat* b [[buffer(1)]],
    const device bfloat* c [[buffer(2)]],
    device bfloat* out [[buffer(3)]],
    uint tid [[thread_position_in_grid]]) {
  out[tid] = a[tid] + b[tid] + c[tid];
}

// Same shape as above but with the simdgroup/lane attributes the scored Laguna
// kernels actually declare, in case attribute lowering shifts the floor.
[[kernel]] void floor_buf4_bf16_simd(
    const device bfloat* a [[buffer(0)]],
    const device bfloat* b [[buffer(1)]],
    const device bfloat* c [[buffer(2)]],
    device bfloat* out [[buffer(3)]],
    uint simdgroup_index_in_threadgroup [[simdgroup_index_in_threadgroup]],
    uint thread_index_in_simdgroup [[thread_index_in_simdgroup]],
    uint3 threadgroup_position_in_grid [[threadgroup_position_in_grid]]) {
  uint tid = threadgroup_position_in_grid.x * 32 +
             simdgroup_index_in_threadgroup * 32 + thread_index_in_simdgroup;
  out[tid] = a[tid] + b[tid] + c[tid];
}
