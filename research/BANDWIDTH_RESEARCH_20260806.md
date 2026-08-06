# Bandwidth & Scheduling Research — 2026-08-06

## Context
Promoted submission 97a5090 (+3.64%) was pre-dot4. All post-promotion composed
submissions rejected (-7% to -14%). M5 likely bandwidth-bound, not instruction-bound.
Strategy shifted to bandwidth/scheduling optimization.

## Findings (5 opportunities, ranked by estimated impact)

### 1. MLX_MAX_OPS_PER_BUFFER 200→800 (ASSIGNED: Edward, PR #165)
- Mechanism: Reduces command-buffer boundary overhead, fewer flushes
- Estimated: ~5.2% decode improvement (public metaspartan note)
- Complexity: LOW (one-line change)
- Bit-exact: YES
- Status: In progress

### 2. MoE Scale-Plane Halving (NEW — not yet assigned)
- Mechanism: Extends attention scale halving to MoE experts.
  MoE experts use same NVFP4 groupSize=16 quantizer → same pairwise-constancy
  invariant applies (scale[2k] == scale[2k+1] for k >= 1)
- Estimated traffic savings: ~33 MB/step (comparable to attention's 39 MB)
- Complexity: MEDIUM (transform-time packing + kernel scale access changes)
- Bit-exact: YES (same scale values, just packed)
- Affected: MoE gate/up R1, shared SwiGLU, routed down, fused down+residual
- Risk: Need to verify DARKBLOOM_PACKED_SCALES doesn't already exploit this

### 3. MLX_METAL_FAST_SYNCH=1 (NEW — needs reachability check)
- Mechanism: Fast fence synchronization via fence.cpp:13-20
- Complexity: LOW (environment variable)
- Bit-exact: YES
- Risk: Need to verify this reaches the scored path

### 4. Packed Walk-Order Down-Scales Bank (NEW — not yet assigned)
- Mechanism: gate/up already uses DARKBLOOM_PACKED_SCALES (reorders scales
  to kernel walk order for coalescing). The 3 down kernels do NOT use it.
  Adding packed scales to down kernels improves coalescing.
- Estimated: ~0.5-1.5% decode (NOVEL_OPTIMIZATION_TARGETS Target 2)
- Complexity: MEDIUM
- Bit-exact: YES (same scale values, reordered layout)
- Affected: lagunaRoutedDownReduceKernel, lagunaRoutedSharedDownResidualKernel,
  lagunaDenseDownResidualKernel

### 5. Prefill ATTN_QHOIST in Isolation (needs isolated M5 testing)
- Mechanism: ~17.8% prefill LSU reduction
- Complexity: Already implemented, needs isolated testing
- Bit-exact: YES
- Risk: Was only tested in rejected composed submission (4b06e93).
  Need to test QHOIST alone without the dot4/simd_sum/float4 changes.
  M4 can't test it (M4 gen 16 < 17 NAX threshold).

## Assignment Plan
- Askeladd: Scale plane halving (attention) — PR #169, assigned
- Alphonse (when free): MoE scale-plane halving (#2 above)
- Thorfinn (when free): Packed down-scales bank (#4 above)
- Edward: ops-per-buffer (#1 above) — in progress, PR #165
- QHOIST isolated testing: needs M5 access, advisor-coordinated
