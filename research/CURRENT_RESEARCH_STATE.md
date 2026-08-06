# SENPAI Research State
- 2026-08-06T19:00Z (updated by advisor session)
- Campaign mlxfast-birch-20260805. Advisor HEAD at 27ff3f8 (pushed to origin).
  Scored code frontier: 639646a + 11 merged optimization PRs (#107→#133).
  M5 submission queued: 57d8f082 (composed #130+#128+#129). Status: validating.
- **WAVE 5 RESULTS** (complete):
  PR #131 (Edward) — NVFP4 O-proj packed simd_sum: MERGED. Bit-exact, M4 inconclusive (bandwidth-bound).
  PR #132 (Alphonse) — Affine QKV packed simd_sum: MERGED. Bit-exact.
  PR #133 (Thorfinn) — Shared SwiGLU down packed simd_sum: MERGED. Bit-exact.
  PR #134 (Askeladd) — Fused down+residual packed simd_sum: IN PROGRESS (draft, no result yet).

- **WAVE 4 RESULTS** (complete):
  PR #130 (Alphonse) — Gate-softplus dot4: MERGED. Bit-exact, +1.44% decode M4.
  PR #129 (Edward) — INT8 O-proj dot4: MERGED. Bit-exact, M4 inconclusive.
  PR #128 (Thorfinn) — Fused down+residual weight staging: MERGED. Bit-exact, +1.14% decode M4.
  PR #124 (Askeladd) — Gate-Scale Fold in O-proj: CLOSED. Dead: non-bit-exact prefill.

- **WAVE 7 ASSIGNED** (created this session):
  PR #144 (Edward) — R1 Gate/Up float4 input_values: eliminate 16 scalar stores+8 extractions
    per block in routed SwiGLU kernel (312x/step, bit-exact). BASE_SHA=27ff3f8.
  PR #145 (Thorfinn) — QKV+Gate Projection dot4: convert 4 scalar FMAs to 1 dot(float4)
    in fused BF16 QKV+gate kernel (39x/step, bit-exact). BASE_SHA=27ff3f8.

- **WAVE 6 IN PROGRESS**:
  PR #140 (Alphonse) — float4 input_values vectorization for shared SwiGLU QMV kernels.
    Add vec4 qdot helpers + convert input_values from float[16] to float4[4].
    Eliminates scalar→vector→scalar→vector round-trip overhead. Bit-exact.
  PR #134 (Askeladd) — Fused down+residual packed simd_sum. Draft, no result yet.
  Research agent (frontier) running for Wave 7+ ideas.

- **M5 SUBMISSION**: Composed #130+#128+#129 (3 bit-exact decode optimizations).
  Submission ID: 57d8f082-b303-4a63-8301-3ad8219db272. Status: validating.
  All changes bit-exact, different kernels, no overlap. Awaiting M5 verdict.
  After M5 result: compose new submission with all Wave 5 merges (#131, #132, #133).

- **POTENTIAL NEXT DIRECTIONS** (for future waves):
  - Prefill MoE variant 5→4 (_nax): +17.47% kernel-level, can't test on M4
  - LAGUNA_RESCALE branch elimination in SDPA vector kernel
  - callLastPrefillRow fused O-proj (1 layer, prefill)
  - Attention epilogue 1-pass bfloat16 exchange (eliminate 1 barrier per dispatch, 40 layers)
  - R1 gate/up prefetch depth increase beyond 1
  - block_width tuning in MoE gate/up kernels

- **LEADERBOARD**: Current promoted best: 2.5888 (maple campaign). Target: beat 2.5888.
- **FRONTIER**: Advisor HEAD at 27ff3f8. Scored code at 639646a + 11 merges (#107→#133).
- **BUDGET**: 2,965,182 / 3,000,000 bytes total (headroom: 34,818). LagunaRuntimeModel.swift: ~507K / 524K per file.
- **M5 SUBMISSION**: 57d8f082 (composed #130+#128+#129). Status: validating.
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
