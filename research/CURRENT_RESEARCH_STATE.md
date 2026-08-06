# SENPAI Research State
- 2026-08-06T20:59Z (updated by advisor session)
- Campaign mlxfast-birch-20260805. Advisor HEAD at bfb393a (pushed to origin).
  Scored code frontier: 639646a + 15 merged optimization PRs (#107→#156).
  M5 submission 57d8f08 (composed #130+#128+#129, 3 PRs) still VALIDATING.
  M5 submission of 15-PR composed HEAD blocked by in-flight 57d8f08. Will retry when slot opens.
  Wave 9 assigned: PRs #159-#162 (4 bit-exact kernel optimization experiments).

- **WAVE 8 RESULTS** (3 complete, 1 incomplete):
  PR #156 (Askeladd) — Fused down+residual float4 input_values: MERGED. Bit-exact.
  PR #154 (Edward) — Async-eval Shared Expert: CLOSED. DEAD — MLX already overlaps eval.
  PR #147 (Alphonse) — CPU Guard Hoisting: CLOSED (incomplete, no result submitted).
  PR #155 (Thorfinn) — Attention Epilogue 1-pass: CLOSED (incomplete, no result submitted).

- **WAVE 9 ASSIGNED** (4 students, BASE_SHA=5ec8550, all bit-exact, all distinct arms):
  PR #159 (Edward) — H1: max_total_threads_per_threadgroup attribute. Add Apple-recommended
    occupancy hint to ALL decode MoE kernels (R1 gate/up: 64 threads, shared SwiGLU: 64,
    fused down+residual: 288, QKV, O-proj, gate-softplus). #1 priority: 5-15% decode on M5.
    Bit-exact. References: Apple Tech Talks 10580, WWDC20, MLX discussion #3801.
  PR #160 (Alphonse) — H4: Thread-local array → register-resident float4 values. Replace
    `thread float input_values[16]` with explicit float4 variables in qdot inner loops.
    WWDC16 warns stack arrays force spills. 0-10% if compiler is spilling. Bit-exact.
  PR #161 (Thorfinn) — H5: Threadgroup input sharing across simdgroups. Both simdgroups in
    R1 gate/up kernel load same input independently. Share via threadgroup memory + barrier.
    Eliminates 2.1M redundant bfloat→float conversions per step. 3-5% gate/up kernel. Bit-exact.
  PR #162 (Askeladd) — H8: Eliminate is_shared branch in 9-slot down+residual kernel. Use
    select() or split shared expert into separate template. 1-2% decode. Bit-exact.

- **M5 SUBMISSION**: 57d8f08 (composed #130+#128+#129 — 3 bit-exact decode optimizations).
  Status: VALIDATING. All changes bit-exact, different kernels, no overlap.
  Next submission: 15-PR composed HEAD (0f05798) — blocked by in-flight 57d8f08.

- **WAVE 7 RESULTS** (complete, all merged):
  PR #144 (Edward) — R1 Gate/Up float4 input_values: MERGED. Bit-exact, 312x/step.
  PR #146 (Askeladd) — Prefill MoE BM128 Variant 4: MERGED. Bit-exact, +17.47% kernel-level prefill.
  PR #140 (Alphonse) — float4 input_values shared SwiGLU: MERGED. Bit-exact.
  PR #134 (Askeladd) — Fused down+residual packed simd_sum: MERGED. Bit-exact, 39 layers.
  PR #145 (Thorfinn) — QKV+gate dot4: CLOSED. DEAD — dot4 NOT bit-exact for shared-float accumulation.

- **WAVE 5 RESULTS** (complete, all merged):
  PR #131 (Edward) — NVFP4 O-proj packed simd_sum: MERGED. Bit-exact, M4 inconclusive.
  PR #132 (Alphonse) — Affine QKV packed simd_sum: MERGED. Bit-exact.
  PR #133 (Thorfinn) — Shared SwiGLU down packed simd_sum: MERGED. Bit-exact, M4 inconclusive.

- **WAVE 4 RESULTS** (complete):
  PR #130 (Alphonse) — Gate-softplus dot4: MERGED. Bit-exact, +1.44% decode M4.
  PR #129 (Edward) — INT8 O-proj dot4: MERGED. Bit-exact, M4 inconclusive.
  PR #128 (Thorfinn) — Fused down+residual weight staging: MERGED. Bit-exact, +1.14% decode M4.
  PR #124 (Askeladd) — Gate-Scale Fold in O-proj: CLOSED. Dead: non-bit-exact prefill.

- **RESEARCH AGENT FINDINGS (Wave 8 intelligence)**:
  1. CPU GUARD HOISTING: 5 invariant guard chains (L351-428, L5495-5514, L10265/10314/10327,
     L5696-5747, L10769-10771) re-evaluated 5120 times/step. All depend only on static layer
     identity + startup flags. Precomputable into per-layer `struct LagunaDecodeLayerPlan`.
  2. ASYNC-EVAL: sharedExpert(x) has ZERO data dependency on routed path. Prefill builds ~400-op
     graph with GPU idle until final eval. asyncEval(y) between L10108 and L10129 overlaps routed
     down/scatter with shared gate/up dispatch. mergedSharedActivated (L9938) is dead/nil.
  3. ATTENTION EPILOGUE: Two decode-only fused kernels (L1381-1670, L1841-2176). 3 barriers in
     epilogue (A/B/C). Exchange is float32. 1-pass merge IS bit-exact if buffer doubled to 8
     planes (all 4 pair_o0/o1 reduced in one loop). Constraint: ~33KB vs ~32KB threadgroup limit.
     Alternative: transpose-free reduction via quad_shuffle — changes reduction tree order.
  4. REMAINING FLOAT4: Only 1 DEFAULT-path target left — lagunaRoutedSharedDownResidualKernel
     (L7691). qdot already uses dot4 internally, conversion is bit-exact. All remaining scalar
     FMA loops are shared-float accumulation — NOT bit-exact for dot4 (PR #145 proof).
     Dense gate/up SwiGLU (L7841) is NOT clean — same PR #145 structure.
  5. dot(float4) IS bit-exact for per-word NVFP4 qdot (independent accumulators) but NOT for
     shared-float cross-iteration accumulation (single FP32 register, sequential adds).

- **POTENTIAL NEXT DIRECTIONS (beyond Wave 9)**:
  - H2: Pre-interleaved weight layout (transform-time, 6-10% gate/up) — after H1/H4 results
  - H3: Fused gate/up+down single-dispatch kernel (saves ~39 dispatches/step, 2-5% decode)
  - H6: Instruction diversity / interleaved load+convert+FMA in qdot (0-5%, pipeline overlap)
  - H7: Half2 FMA accumulation (5-8% but HIGH risk — precision change, likely fails exactness)
  - Transpose-free attention reduction via quad_shuffle
  - LAGUNA_RESCALE branch elimination in SDPA vector kernel
  - CPU Guard Hoisting (re-attempt with simpler implementation)

- **LEADERBOARD**: Current promoted best: 2.5888 (maple campaign, submission 97a5090).
  Target: beat 2.5888. All component speedups must be ≥ 0.95.
- **FRONTIER**: Advisor HEAD at 0f05798. Scored code at 639646a + 15 merges (#107→#156).
- **BUDGET**: ~2,964K / 3,000,000 bytes total. LagunaRuntimeModel.swift: ~510K / 524K per file.
- **KEY FINDINGS**:
  1. Attention main loop is MEMORY-BOUND (PR #122). Do NOT pursue attention ALU optimization.
  2. Metal compiler optimizes thread float[N] scatter to registers (PR #123).
  3. Weight staging pre-loading codes/scales before qdot is PROVEN (PR #116, #128).
  4. dot(float4) vectorization is PROVEN for per-word qdot (PRs #107, #114, #119, #129, #130).
  5. dot(float4) is NOT bit-exact for shared-float cross-iteration accumulation (PR #145).
  6. M5 is instruction-bound at ~89%. M4 is bandwidth-bound. M4 evidence directional only.
  7. Gate-scale fold is NOT bit-exact for prefill (PR #124). Folding changes BF16 rounding point.
  8. NVFP4 code pre-expansion inconclusive (PR #121). 4x memory traffic risk.
  9. LM head int4 DEAD — bandwidth-bound, zero saving.
  10. Scale Decode LUT closed dead (PR #125). Core bet: constant-cache load vs ALU on M5.
  11. input_values[16]→float4[4] is bit-exact when qdot uses dot4 internally (PRs #140, #144).
  12. asyncEval adds no operation — only enqueues already-constructed work earlier (L656-658).
  13. mergedSharedActivated (L9938) is dead/nil — never assigned, plumbing unconnected.
  14. Prefill builds ~400-op graph with GPU idle until final eval (comment L719-730).

## Prior Results (DO NOT REPEAT)

| PR | Student | Idea | Result |
|----|---------|------|--------|
| #145 | Thorfinn | QKV+gate projection dot4 | ASSIGNED (Wave 7). Bit-exact, 39x/step. |
| #144 | Edward | R1 gate/up float4 input_values | ASSIGNED (Wave 7). Bit-exact, 312x/step. |
| #140 | Alphonse | float4 input_values shared SwiGLU | IN PROGRESS (Wave 6). Bit-exact. |
| #134 | Askeladd | Fused down+residual packed simd_sum | IN PROGRESS (Wave 6). Bit-exact. |
| #133 | Thorfinn | Shared SwiGLU down packed simd_sum | MERGED. Bit-exact. |
| #132 | Alphonse | Affine QKV packed simd_sum | MERGED. Bit-exact. |
| #131 | Edward | NVFP4 O-proj packed simd_sum | MERGED. Bit-exact. |
| #130 | Alphonse | Gate-softplus dot4 + simd_sum | MERGED. Bit-exact, +1.44% decode M4. |
| #129 | Edward | INT8 O-proj dot4 + simd_sum | MERGED. Bit-exact, M4 inconclusive. |
| #128 | Thorfinn | Fused down+residual weight staging | MERGED. Bit-exact, +1.14% decode M4. |
| #124 | Askeladd | Gate-scale fold in O-proj | CLOSED. Dead: no speedup, non-bit-exact prefill. |
| #121 | Edward | NVFP4 code pre-expansion | CLOSED. Inconclusive, 4x memory traffic risk. |
| #119 | Alphonse | NVFP4 O-proj dot4 | MERGED. Bit-exact. |
| #116 | Edward | Shared SwiGLU staging | MERGED. Bit-exact. |
| #114 | Alphonse | INT8 QKV dot4 | MERGED. Bit-exact. |
| #107 | Alphonse | NVFP4 qdot dot4 | MERGED. Bit-exact. |
| #122 | Thorfinn | Attention ALU optimization | CLOSED. Memory-bound. |
| #123 | Thorfinn | Scatter-to-float4 | CLOSED. Compiler already optimizes. |
| #102 | Thorfinn | Attention threadGroup 1024→128 | CLOSED. Speedup was from doing half the work. |
| #97 | Edward | Prefill dispatch elimination | NEGATIVE. Dispatch overhead negligible. |
| #96 | Thorfinn | Register-prefetch shared SwiGLU | NEGATIVE. Register pressure regression. |
| #93 | Edward | Register-prefetch down+residual | NEGATIVE. Bandwidth-bound. |
| #74 | Edward | Prefetch depth 2→4 | NEGATIVE. Bandwidth-bound. |
| #98 | Askeladd | Prefill O-proj affine | MERGED then reverted (cc63c1c). |
| #125 | Alphonse | Scale Decode LUT | CLOSED dead. |

Note: Orphan PRs (#69, #83, #86, #92, #99, #108, #111, #113, #115, #126) are broken from
prior sessions. Cannot close via close_experiment. Ignore.
