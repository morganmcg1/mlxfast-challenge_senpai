// Launch-overhead probe: the production sliding dispatch shape (32 threadgroups
// x 1024 threads, 18432 B of threadgroup memory, same 11 buffers) with no
// attention work. Subtracting this from the it1/it2/it4/it8 regression
// intercept separates per-dispatch launch cost from the kernel's own fixed
// prologue and epilogue cost.
#include <metal_stdlib>
#include <metal_simdgroup>
using namespace metal;
typedef bfloat bfloat16_t;

[[kernel]] void custom_kernel_laguna_sliding_launch_probe(
  const device bfloat16_t* raw_queries [[buffer(0)]],
  const device bfloat16_t* raw_keys [[buffer(1)]],
  const device bfloat16_t* raw_values [[buffer(2)]],
  const device bfloat16_t* query_weight [[buffer(3)]],
  const device bfloat16_t* key_weight [[buffer(4)]],
  const device float* angles [[buffer(5)]],
  const device bfloat16_t* k_cache [[buffer(6)]],
  const device bfloat16_t* v_cache [[buffer(7)]],
  const constant uint32_t* params [[buffer(8)]],
  const constant float* scale_arr [[buffer(9)]],
  device bfloat16_t* attended [[buffer(10)]],
  uint simdgroup_index_in_threadgroup [[simdgroup_index_in_threadgroup]],
  uint thread_index_in_simdgroup [[thread_index_in_simdgroup]],
  uint3 threadgroup_position_in_grid [[threadgroup_position_in_grid]]) {
  constexpr int BN = 32;
  constexpr int BDP = 33;
  threadgroup float outputs[4 * BN * BDP];
  threadgroup float max_scores[2 * BN];
  threadgroup float sum_exp_scores[2 * BN];
  uint sg = simdgroup_index_in_threadgroup;
  uint lane = thread_index_in_simdgroup;
  outputs[sg * BDP + lane] = float(raw_queries[sg * 32 + lane]);
  if (lane == 0) {
    max_scores[sg] = float(params[0]);
    sum_exp_scores[sg] = scale_arr[0];
  }
  threadgroup_barrier(mem_flags::mem_threadgroup);
  float value = outputs[lane * BDP + sg] + max_scores[lane % (2 * BN)]
      + sum_exp_scores[lane % (2 * BN)];
  if (sg == 0 && lane == 0 && value == 12345.678f) {
    attended[threadgroup_position_in_grid.x] = bfloat16_t(value);
  }
}
