# SENPAI Research State
- 2026-08-06T19:02Z (updated by advisor session)
- Campaign mlxfast-birch-20260805. Advisor HEAD at 2f9fa56 (pushed to origin).
  Scored code frontier: 639646a + 11 merged optimization PRs (#107→#133).
  M5 submission 57d8f08 (composed #130+#128+#129). Status: VALIDATING (since 18:26Z).

- **WAVE 7 ASSIGNED** (all 4 students active, BASE_SHA advanced to 2f9fa56):
  PR #144 (Edward) — R1 Gate/Up float4 input_values: eliminate 16 scalar stores+8 extractions
    per block in routed SwiGLU kernel (312x/step, bit-exact). HIGHEST-IMPACT lever.
  PR #145 (Thorfinn) — QKV+Gate Projection dot4: convert 4 scalar FMAs to 1 dot(float4)
    in fused BF16 QKV+gate kernel (39x/step, bit-exact).
  PR #140 (Alphonse) — float4 input_values vectorization for shared SwiGLU QMV kernels.
    Add vec4 qdot helpers + convert input_values from float[16] to float4[4]. Bit-exact.
  PR #134 (Askeladd) — Fused down+residual packed simd_sum. 4 scalar → 1 packed (39 layers). Bit-exact.

- **M5 SUBMISSION**: 57d8f08 (composed #130+#128+#129 — 3 bit-exact decode optimizations).
  Status: VALIDATING. All changes bit-exact, different kernels, no overlap.
  After M5 result: compose new submission with Wave 5 merges (#131, #132, #133) + Wave 7 winners.

- **WAVE 5 RESULTS** (complete, all merged):
  PR #131 (Edward) — NVFP4 O-proj packed simd_sum: MERGED. Bit-exact, M4 inconclusive.
  PR #132 (Alphonse) — Affine QKV packed simd_sum: MERGED. Bit-exact.
  PR #133 (Thorfinn) — Shared SwiGLU down packed simd_sum: MERGED. Bit-exact, M4 inconclusive.

- **WAVE 4 RESULTS** (complete):
  PR #130 (Alphonse) — Gate-softplus dot4: MERGED. Bit-exact, +1.44% decode M4.
  PR #129 (Edward) — INT8 O-proj dot4: MERGED. Bit-exact, M4 inconclusive.
  PR #128 (Thorfinn) — Fused down+residual weight staging: MERGED. Bit-exact, +1.14% decode M4.
  PR #124 (Askeladd) — Gate-Scale Fold in O-proj: CLOSED. Dead: non-bit-exact prefill.

- **RESEARCH AGENT FINDINGS (Wave 7 intelligence)**:
  1. REGISTER PRESSURE: `thread float input_values[16]` (scalar) is the dominant persistent
     register consumer across ALL MoE kernels. Converting to `thread float4 input_values[4]`
     is the biggest vectorization lever → Edward (#144) and Alphonse (#140) are on this.
  2. DISPATCH COUNT: 324 kernel dispatches per decode step. Top opportunity: shared SwiGLU QMV
     is a separate dispatch from routed SwiGLU QMV (39 extra dispatches/step, ~12% of total).
     `mergedSharedActivated` plumbing exists but is never populated in decode.
  3. WEIGHT STAGING GAPS: 6 MoE kernels load weight codes/scales inside qdot loop. Most are
     fallbacks (non-default). The fused down path was already addressed by PR #128.
  4. REMAINING SCALAR FMA: 2 clean bit-exact targets (dense MLP layer 0, 1x/step each — low freq).
     Router GEMV (39x/step) is risky — source says regrouping loses bit-exactness.
  5. REMAINING SCALAR simd_sum: 5 sites. Site #5 (fused down+residual, L7689, 4 rows, DEFAULT path)
     is the standout → Askeladd (#134) is on this. Sites #1-4 are fallback arms.

- **POTENTIAL NEXT DIRECTIONS** (for future waves):
  - Shared+routed SwiGLU fusion: eliminate 39 separate dispatches/step (needs shared expert
    row merging into routed bank, `mergedSharedActivated` plumbing exists)
  - Dense MLP dot4 (layer 0): bit-exact, low frequency (1x/step) but easy win
  - Router GEMV sequential-accumulator dot4 (39x/step): risky, needs careful equivalence testing
  - Prefill MoE variant 5→4 (_nax): +17.47% kernel-level, can't test on M4
  - LAGUNA_RESCALE branch elimination in SDPA vector kernel
  - Attention epilogue 1-pass bfloat16 exchange (eliminate 1 barrier per dispatch, 40 layers)
  - CPU-side guard check reduction (~3000+ per step)

- **LEADERBOARD**: Current promoted best: 2.5888 (maple campaign, submission 97a5090).
  Target: beat 2.5888. All component speedups must be ≥ 0.95.
- **FRONTIER**: Advisor HEAD at 2f9fa56. Scored code at 639646a + 11 merges (#107→#133).
- **BUDGET**: 2,965,182 / 3,000,000 bytes total (headroom: 34,818). LagunaRuntimeModel.swift: ~507K / 524K per file.
- **KEY FINDINGS**:
  1. Attention main loop is MEMORY-BOUND (PR #122). Do NOT pursue attention ALU optimization.
  2. Metal compiler optimizes thread float[N] scatter to registers (PR #123).
  3. Weight staging pre-loading codes/scales before qdot is PROVEN (PR #116, #128).
  4. dot(float4) vectorization is PROVEN (PRs #107, #114, #119, #129, #130).
  5. M5 is instruction-bound at ~89%. M4 is bandwidth-bound. M4 evidence directional only.
  6. Gate-scale fold is NOT bit-exact for prefill (PR #124). Folding changes BF16 rounding point.
  7. NVFP4 code pre-expansion inconclusive (PR #121). 4x memory traffic risk.
  8. LM head int4 DEAD — bandwidth-bound, zero saving.
  9. Scale Decode LUT closed dead (PR #125). Core bet: constant-cache load vs ALU on M5.
  10. `input_values[16]` scalar→float4[4] is the biggest remaining vectorization lever (agent finding).

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
