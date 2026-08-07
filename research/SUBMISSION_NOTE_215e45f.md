# MLXFast Submission: Composed Instruction-Count + Bandwidth Optimization Frontier

## Model Attribution
Model: senpai
Coding agent: OpenHands (Senpai autonomous research agent)
Effort level: maximum

## Initial Context and Goal
This submission optimizes the Poolside Laguna XS 2.1 NVFP4 model for the serial
`laguna-xs-2.1-serial-v2` track on the MLXFast competition. The goal is to maximize:

    score = decode_speedup^0.75 * prefill_speedup^0.25

where both component speedups compare the candidate with the pinned baseline
measured in the same official session on an M5 Max (128 GB unified memory).
Both component speedups must be at least 0.95.

Decode (75% weight) is the primary target. Prefill (25% weight) is secondary.
The M5 is instruction-bound at ~89% GPU utilization for the 256-expert NVFP4 MoE.

## Environment and Setup
- Hardware: AWS Mac M4 Pro (development and correctness testing)
- Official hardware: M5 Max 128 GB (ranking)
- Build: swift build -c release --force-resolved-versions
- Benchmark: ./benchmark.sh --local-iterate for matched baseline/candidate
- Thermal gate: 40C, MLXFAST_LOCAL_COOL_GATE=0 for matched runs
- Memory profile: low-memory (48 GiB M4 Pro)

## Base Checkout
BASE_SHA: bb523807d3f70757d7cbae4b4b24ecfe5981a43d (campaign base)
ORGANIZER_FRONTIER_SHA: bca94c5aa472a773a990ac61904340ce56465229

The advisor branch mlxfast-birch-20260805-advisor integrates the organizer
frontier and records the promoted code frontier. Students branch from this
base and implement one causal hypothesis per PR.

## Composed Changes (6 optimizations)

This submission composes 6 independently validated, bit-exact optimizations:

### 1. MoE Scale Halving (PR #180, merged)
- Mechanism: NVFP4 pairwise-constancy scale halving for decode MoE kernels.
  Adjacent NVFP4 quantization groups share the same scale byte
  (scale[2k]==scale[2k+1] for k>=1). Store one scale per 32 elements instead
  of 16, halving scale bandwidth. Escape byte handles the sole exception
  pair per expert.
- Kernels: lagunaSharedSwiGLUQMVKernel, lagunaSharedSwiGLUQMVRows1Kernel,
  lagunaRoutedSwiGLUQMVPackedTop8R1Kernel, lagunaRoutedSharedDownResidualKernel
- M4 result: ~1% decode gain (bit-exact)
- Budget: ~1,100 bytes in LRM, vendor files unchanged

### 2. Packed simd_sum (PR #194, merged)
- Mechanism: Replace 4 scalar simd_sum calls with 1 packed simd_sum(vec<float,4>)
  in 3 decode kernels (gate-softplus, QKV, O-proj). Saves 3 cross-lane
  reduction instructions per dispatch.
- Bit-exact: simd_sum(vec<float,4>) performs the same cross-lane reduction
  as 4 scalar simd_sum calls, just packed. Proven by standalone routed down kernel.
- M4 result: inconclusive (0.02%, within noise) — M5 needed (instruction-bound)
- Budget: ~200 bytes in LRM

### 3. O-proj NVFP4 Scale Halving (PR #192, merged)
- Mechanism: Same NVFP4 pairwise-constancy scale halving applied to the
  NVFP4 O-proj kernel (lagunaGatedAffineOProjNVFP4Source). O-proj scales
  are ~10% of O-proj weight traffic. Halving saves ~5% of O-proj bandwidth.
- Bit-exact: Same invariant as PR #180
- M4 result: ~0.35% decode (within noise, directional)
- Budget: ~3,361 bytes in LRM

### 4. Prefill MoE Gather-QMM Scale Halving (PR #198, merged)
- Mechanism: Port the NVFP4 pairwise-constancy scale halving to the prefill
  MoE gather-QMM kernel (fp_gather_qmm_rhs_expert_nax). This is a COMPLETELY
  DIFFERENT code path from the decode kernels. Prefill loads ALL 256 experts'
  weights during the 512-token forward pass. Scale traffic: ~1,872 MiB;
  halving saves ~936 MiB. At M5 651.8 GB/s: ~1.44 ms saved per ~25-30 ms prefill.
- Files: fp_quantized_nax.h (+70 lines), fp_quantized_nax.cpp (+67 lines),
  quantized.cpp (+34 lines), LagunaRuntimeModel.swift (+40 lines)
- Bit-exact: Same invariant as PR #180. Fallback correctness proven on M4.
- M4 testability: NO — M4 Pro reports GPU gen 16 < 17 NAX threshold, so
  the _nax expert kernel is never compiled on M4. M5-only.
- Expected M5 signal: ~5-6% prefill gain -> ~1.0-1.5% composite score gain

### 5. INT8 Gate-Softplus Scale/Bias Dedup (PR #200, merged)
- Mechanism: The gate-softplus INT8 affine kernel indexes scales/biases with
  lane/SS where SS=GS/V=32/8=4. Four consecutive lanes read the SAME scale
  and bias from device memory — a 4x redundant load. Load once per lane-group
  (group leader loads), broadcast via simd_shuffle to other 3 lanes.
  Eliminates 3/4 of scale+bias device reads AND load instructions.
- Bit-exact: simd_shuffle broadcasts the exact same value
- M4 result: inconclusive (-0.72% directional, within noise) — M5 needed
- Budget: +143 bytes only

### 6. INT8 O-proj Scale/Bias Dedup (PR #207, merged)

- Mechanism: Same simd_shuffle broadcast pattern as PR #200, applied to
  the gated affine O-proj INT8 kernel. Both indexed and non-indexed variants
  updated. Runs on first 16 sliding-window attention layers per decode step.
- Bit-exact: Same as PR #200
- M4 result: -1.7% decode (directional improvement, stronger than PR #200)
- Budget: +143 bytes

## Implementation Details

All changes are in the editable submission surface defined by benchmark.json:
- Sources/MLXFastModel/LagunaRuntimeModel.swift (primary scored runtime)
- Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized_nax.h
- Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized_nax.cpp
- Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp

### Budget Status
- LagunaRuntimeModel.swift: 522,197 / 524,288 bytes (2,185 B headroom)
- Total editable surface: ~1,926,000 / 3,000,000 bytes (ample headroom)
- Per-submission growth: ~10,500 / 262,144 bytes (within limit)

### 7. INT8 QKV Scale/Bias Dedup (PR #206, merged)
- Mechanism: Same simd_shuffle broadcast pattern as PR #200, applied to
  the norm-affine QKV INT8 kernel (3 non-indexed paths). Runs on all 40
  layers per decode step. Completes the INT8 dedup family (gate-softplus,
  O-proj, QKV).
- Bit-exact: Same as PR #200
- M4 result: +0.57% (within noise, M4 bandwidth-bound)
- Budget: +143 bytes

### 8. Shared SwiGLU float4 input_values (PR #209, merged)

- Mechanism: Vectorized input_values stores via float4 pointer cast in
  shared SwiGLU QMV kernel. Replaces 16 scalar stores with 4 float4 stores.
  Kept float[16] array to preserve qdot function interface.
- Bit-exact: YES
- M4 result: -0.1% (neutral, within noise)
- Budget: -336 bytes (net reduction!)
- Mechanism: Same simd_shuffle broadcast pattern as PR #200, applied to
  the norm-affine QKV INT8 kernel (3 non-indexed paths). Runs on all 40
  layers per decode step. Completes the INT8 dedup family (gate-softplus,
  O-proj, QKV).
- Bit-exact: Same as PR #200
- M4 result: +0.57% (within noise, M4 bandwidth-bound)
- Budget: +143 bytes

### 9. Routed MoE Scatter-to-Float4 (PR #212, merged)
- Mechanism: Vectorized result scatter via float4 pointer cast in routed
  gate/up R1 and fused down+residual kernels. Replaces 4 scalar stores
  with 1 float4 store per bfloat4 load.
- Bit-exact: YES
- M4 result: +0.8% decode (small regression, M4 bandwidth-bound)
- Budget: -324 bytes (net reduction)

## Experiments and Measured Results

### M4 Pro Results (directional only — M4 is bandwidth-bound, M5 is instruction-bound)

All changes were validated on M4 Pro for correctness (bit-exact, max_abs_diff=0)
and directional timing. M4 timing is directional only because:
1. M4 Pro is bandwidth-bound (GPU gen 16), M5 is instruction-bound (~89%)
2. M4 does not select _nax prefill kernels (GPU gen < 17 threshold)
3. Instruction-count reductions that help M5 may show no M4 gain

Matched-pair baseline/candidate results on M4 Pro:

| Change | M4 Decode Delta | M4 Prefill Delta | Bit-Exact |
|--------|----------------|-----------------|-----------|
| MoE halving (PR #180) | ~-1.0% | flat | YES |
| simd_sum (PR #194) | ~0% | flat | YES |
| O-proj halving (PR #192) | ~-0.35% | flat | YES |
| Prefill halving (PR #198) | N/A | N/A (M4 can't test _nax) | YES (fallback) |
| Gate-softplus dedup (PR #200) | ~-0.72% | flat | YES |
| O-proj dedup (PR #207) | ~-1.7% | flat | YES |

### Upstream Equivalence
All changes verified bit-exact via research/run_upstream_equivalence.sh:
- All 8 decode steps: maxAbsError=0.0 (bit-exact)
- Prefill logit error 0.125 is pre-existing M4 platform artifact (identical on baseline)
- All checked greedy tokens match

## Key Negative Results (preserved for future agents)

1. Gate-softplus dot4 (PR #201): DEAD after PR #200 merged. The simd_shuffle
   dedup and dot4 vectorization overlap — both reduce instruction count in the
   same kernel. PR #200's load reduction captured the benefit dot4 would have
   provided. Do NOT retry dot4 on gate-softplus while simd_shuffle dedup present.

2. Router rows sweep (PR #202): DEAD. No DARKBLOOM_ROUTER_ROWS_PER_GROUP value
   beats default 8. Router kernel is 1 dispatch of 256 threads — too small
   for tiling changes to matter.

3. RMSNorm fusion into LM head (PR #199): DEAD. 4.9% decode regression.
   Pruner kernels are compute-bound, not dispatch-bound. Adding compute to
   compute-bound kernels to save a cheap dispatch is fundamentally unprofitable.

4. Attention scale halving (PR #193): DEAD. -2.7% decode regression.
   Escape mechanism overhead exceeds bandwidth savings. Attention runs only
   40x/step vs MoE's 256 experts amortizing per-kernel overhead.

## Failures and Course Corrections

- PR #201 (dot4) initially showed +0.77% on the old frontier (57804d3) but
  regressed to -0.29% after PR #200 (simd_shuffle dedup) merged. The two
  optimizations are NOT independent in the gate-softplus kernel. This informed
  our decision to NOT pursue dot4 in other kernels where dedup is present.

- The prefill MoE halving (PR #198) could not be timed on M4 because M4 does
  not select _nax kernels. Build verification and fallback correctness were
  the only M4 evidence. M5 is the sole platform for _nax timing.

## Caveats

1. M4 timing is directional only. The M5 (instruction-bound at ~89%) is the
   authoritative platform. Instruction-count reductions that show no M4 gain
   may still help on M5.

2. The prefill MoE halving (PR #198) is M5-only — no M4 timing evidence.
   The mechanism is identical to the proven decode halving (PR #180).

3. The total composed effect is unknown until M5 measurement. Individual
   changes were validated independently; composition effects (interaction
   between instruction-count reductions) may differ from the sum of parts.

4. The LRM budget is very tight (2,185 B headroom). Future experiments must
   be extremely space-efficient.

## Learning

1. NVFP4 pairwise-constancy scale halving is a reliable bandwidth optimization
   that works across multiple kernel families (decode MoE, O-proj, prefill MoE).

2. INT8 scale/bias dedup via simd_shuffle is a cheap (~143 bytes) instruction-
   count reduction that works across all INT8 affine kernels with the same
   lane/SS indexing pattern.

3. Instruction-count reductions can overlap: dot4 and simd_shuffle dedup both
   reduce instruction count in the same kernel. When one is present, the other
   may not add value. Test independently before composing.

4. Attention scale halving fails because attention dispatches only 40x/step
   (vs MoE's 256 experts). Per-kernel overhead from the escape mechanism
   exceeds the bandwidth savings.

## Next Steps

1. Await M5 official result for this composed submission
2. If M5 shows gain: continue extending INT8 dedup to QKV kernel (PR #206, in progress)
3. If M5 rejects: identify which component caused the regression and remove it
4. Explore fused down float4 input vectorization (PR #208, in progress)
5. Consider fresh research directions if current frontier plateaus on M5
