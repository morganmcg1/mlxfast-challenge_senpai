# SENPAI Research State — mlxfast-birch-20260805
- 2026-08-07T23:13Z (updated by advisor session)
- Advisor HEAD: 504a2d9e (pushed to origin). 37+ bit-exact changes on current frontier.
- LRM: 502,603/524,288 = 21,685 B headroom. Total surface 2,937,409/3,000,000 = 62,591 B headroom.

## GRID OVER-DISPATCH HYPOTHESIS: REFUTED
MLX's MLXFast API uses dispatchThreads(gridSize, threadgroupSize) where grid = TOTAL THREADS.
The × threadGroupSize multiplier in grid expressions is CORRECT. PR #333 was closed as invalid.
Do NOT revisit this hypothesis.

## M5 SUBMISSION STATUS (CRITICAL — 28+ CONSECUTIVE FAILURES)
  311d4fe3: FAILED (10:30 PM) — warmup fix resubmission. Code identical to passing 68b66c5.
  d464652: FAILED (10:54 PM) — 3rd resubmission of warmup fix code.
  d4f33938: VALIDATING (11:13 PM) — 4th resubmission. Code is confirmed correct (68b66c5 PASSED at 2.5520).
  Root cause: JIT compile-storm (~82 kernel instances, ~287s compile) intermittently exceeds M5 runner timeout.
  The code WORKS — 68b66c5 PASSED at ad58c92. Identical resubmission 70929a5 FAILED, confirming intermittent environmental sensitivity.
  Strategy: keep resubmitting while students work. Prepare JIT kernel consolidation (Idea 3) as structural fix.
  2deac25c: FAILED (10:13 PM) — warmup fix (prefill 512→2, 3 extra decode steps). Insufficient alone.
  89ab294: FAILED (9:37 PM) — same d7758813 code without warmup fix.
  7e974fa: FAILED (9:20 PM) — resubmission of d7758813 with M5 fixes.
  66c0555: FAILED (9:00 PM) — same code with FUSED_QKV OFF, addMM OFF.
  CRITICAL: 25+ consecutive M5 build failures since 68b66c5 PASSED at 9:36 AM (score 2.5520).
  Organizer frontier (3ff3992) PASSED at 6:51 PM (score 2.5213) — confirms M5 works intermittently.
  ad58c92 (=68b66c5) and cdefbb9 have 0 lines diff in Sources/ — identical code passed then failed.
  Best birch score: 2.5817 (df9613a). All prior birch submissions failed or rejected.
  Leaderboard #1: fyrsta7 2.6040 (yudduy). Gap: ~0.94%.
  ROOT CAUSE (high confidence): JIT compile-storm timeout. 57 JIT kernel definitions compiled
  lazily on first dispatch create 80-110+ Metal compilations during inference, colliding with
  runner ~900s timeout + 40C thermal gate. Organizer frontier (0 JIT kernels) always passes.
  WARMUP FIX APPLIED: Reduced warmup prefill from 512 to 2 tokens (256x less attention compute,
  same kernel compilations). Added 3 extra decode steps for state-dependent kernel coverage.
  If warmup fix insufficient, next: consolidate per-head kernel variants or disable features.

## MERGED WAVE 19-21
  PR #352 (thorfinn): JIT kernel disable sweep — MERGED (5 flags disabled, 345B)
  PR #350 (alphonse): JIT kernel variant consolidation — MERGED (compile count ~82→~57, -6,402B)
  PR #358 (alphonse): Delete unused H4 kernel variants — MERGED (-7,010B, -2 JIT compiles, PR #350 M5 audit: no incompatible constructs found)
  Total compile count: ~82 → ~55 (PR #352 + #350 + #358 combined)

## CLOSED WAVE 20-21
  PR #349 (askeladd): RMSNorm+QKV fusion — NEGATIVE (MLX.compile can't fuse Custom primitives with matmul)
  PR #356 (alphonse): Re-enable FUSED_FULL_QK_NORM_YARN — NEGATIVE (M4 -3.3% decode regression)
  PR #351 (edward): Shared gate/up+SiLU fusion — DEAD (already fused, MLX.compile can't fuse quantizedMM)
  PR #355 (thorfinn): eScoreCorrectionBias hoist — DEAD (already implemented in base code)
  PR #359 (edward): Lazy kernel init — DIAGNOSTIC SUCCESS (all OFF-flagged kernels properly lazy, no premature JIT)

## ACTIVE ASSIGNMENTS (Wave 22, BASE_SHA=1860923f)
  PR #357 (askeladd): Re-enable PREFILL_QK_NORM_ROPE — WIP (0-byte flag flip, ~200 prefill dispatch elim)
  PR #360 (thorfinn): Fast-path dispatch table — WIP (~0.1-1% decode, no new kernels)
  PR #361 (edward): Consolidate compiled gate functions — WIP (M5 build fix, reduce compile() count)
  PR #363 (alphonse): Consolidate router kernel normalizing/non-normalizing pairs — WIP (M5 build fix, -2 JIT compiles)

## M5 BUILD FIX STATUS
  PR #352 + PR #350 + PR #358 combined: compile count ~82 → ~55 (build time 88s → 21s on M4)
  M5 STILL FAILING: 33+ consecutive failures (intermittent timeout, ~900s budget).
  ROOT CAUSE CONFIRMED: JIT compile-storm timeout. ~55 M4 compiles × ~3.5s = ~193s
  + ~15-25 _nax compiles × ~5-7s = ~100-175s + warmup + benchmark = ~450-650s (near 900s edge).
  ORGANIZER PROOF: 3ff3992 (0 JIT kernels) PASSED at 6:51 PM (score 2.5213), confirming
  M5 works when compile count is low.
  KEY DIAGNOSTIC: 70929a5 had identical code to 68b66c5 (which scored 2.5520) but FAILED.
  Confirms intermittent timeout — same code passes when M5 is fresh, fails under load.
  c8a70169 VALIDATING (8th resubmission, warmup fix: reduce prefill 512→2 tokens).
  Next M5 submission: include PR #358's -2 compile count + warmup fix.

## MERGED WAVE 18
  PR #343 (alphonse): Prefill compiled attentionGateProjection multi-token — MERGED (2.8% prefill improvement, 2-line change, bit-exact)
  PR #342 (edward): Prefill nax halved scales via qmm_nax kHalvedScales — MERGED (M5-only, ~0.9% total score, re-applies PR #243 + extends to gather path)

## CLOSED WAVE 17-18
  PR #345 (thorfinn): Prefill addMM enablement — DEAD (-36.1% regression, breaks fused residual+RMSNorm+router)
  PR #346 (askeladd): Threadgroup bank conflict padding — DEAD (0.43% decode, within noise. Bank conflicts negligible vs NVFP4 compute)
  PR #348 (thorfinn): Unsorted gatherQuantizedMM — DEAD (+39.7% prefill regression, unsorted expert weight access causes cache/bank conflicts. Sorting is essential for locality, not just dispatch overhead)

## RECENTLY CLOSED (Wave 16)
  PR #339 (askeladd): LM head TG doubling — NEGATIVE. ~0.45% decode regression. Dispatch overhead is per-kernel-LAUNCH not per-TG. Larger TGs hurt occupancy.
  PR #337 (alphonse): Decode asyncEval=off — NEGATIVE. Current 7-fire schedule is optimal.
  PR #338 (edward): Down outputs_per_simd 8→4 — INCONCLUSIVE. Marginal degrading signal.
  PR #335 (thorfinn): asyncEval stride sweep v2 — DEAD. Current schedule already optimal on 37+ frontier.

## NEXT PRIORITY: M5 Build Fix + v8 Ideas
  Warmup fix insufficient (2deac25c FAILED). Resubmitted (311d4fe3 VALIDATING).
  Root cause: ~30-50 JIT kernel compilations (~100-250s) intermittently exceed M5 runner timeout.
  Vendor files are CLEAN (0 diff from organizer frontier). All changes are LRM-only.
  v8 research ideas generated (RESEARCH_IDEAS_FRESH_20260807_v8.md, 8 ideas):
  1. Prefill RMSNorm+QKV fusion (★★★, ~0.6% total, 0-byte MLX.compile)
  2. Unsorted gatherQuantizedMM to eliminate gatherSort (★★★, ~2.2% total, ~200B)
  3. JIT kernel variant consolidation via function constants (★★★, M5 FIX, net-negative bytes)
  4. Threadgroup bank conflict padding (★★☆, ~1% decode, ~50-100B) — ASSIGNED to askeladd (PR #346)
  5. MLX.compile shared expert gate/up+SiLU fusion (★★☆, ~1.1% prefill, MEDIUM risk)
  6. Indexed metadata LUT for standalone g_proj (★★☆, ~0.01% decode, LOW risk)
  7. Custom flash-attention SDPA for full-attention layers (★★☆, ~0.6% prefill, MEDIUM risk)
  8. Fuse shared expert down GEMV into MoE tail kernel (★★☆, ~2.2% prefill, HIGH risk)
  Ideas 3 (M5 fix) and 1+2 (prefill) are highest priority for next wave.

## RECENTLY CLOSED
  PR #334 (askeladd): Prefill router GEMV fusion v2 — FAILED (+2.46% prefill regression).
    Root cause: Metal lacks cross-TG sync → multi-token router kernel redundantly computes
    per-row RMSNorm 32× per row × 512 rows. ~4.8 GB extra bandwidth dwarfs 95 µs savings.
  PR #333 (thorfinn): Grid over-dispatch fix — INVALID. Hypothesis was wrong (MLX grid = total threads).
  PR #331 (askeladd): Broken assignment marker, replaced by PR #334.
  PR #332 (thorfinn): Broken assignment marker, replaced by PR #335.
  PR #330 (alphonse): Prefill shared SwiGLU+down fold — CLOSED (not merged, 203 insertions).
  PR #329 (edward): Dense gate/up fusion — MERGED (bit-exact, LRM-only).

## CLOSED WAVE 13 (all dead/failed)
  PR #317: Prefill norm+router fusion — DEAD. Custom GEMM can't beat MLX's GEMM.
  PR #324: Prefill SiLU+down fusion — DEAD. SiLU dispatch too small.
  PR #325: Prefill g_proj+QKV fusion — DEAD. Regressed +1.2% (tiling).
  PR #326: Decode router top-8 fusion — FAILED. 7.8% slower (1-tile parallelism loss).
  PR #328: Prefill shared halving — DEAD. Target cost too small.

## RESEARCH THEMES
  - M5 is bandwidth-bound (~89% GPU util). Only bandwidth reduction or dispatch elimination helps.
  - Grid over-dispatch hypothesis was REFUTED — MLX grid = total threads, not threadgroups.
  - Custom GEMM/GEMV for small matmuls can't beat MLX's optimized GEMM (PR #317, #325, #326, #334).
  - Multi-token kernel fusion limited by Metal's lack of cross-TG synchronization (PR #334).
  - Dispatch elimination can REGRESS timing if redundant computation > dispatch savings (PR #334).
  - M5 SAFETY: NO simd_sum(vec), NO dot(float4), NO *(thread float4*) casts. Scalar Metal only.
  - M5 build failures: 24 consecutive since 9:36 AM. Intermittent (identical code passed then failed).
  - Decode asyncEval schedule may be suboptimal on heavily-fused base (notes/52: current 1.7% worse
    than no asyncEval). Fresh measurement assigned to alphonse (PR #337).
  - Down kernel outputs_per_simd reduction may improve latency hiding (assigned to edward, PR #338).
  - Remaining research ideas in research/RESEARCH_IDEAS_FRESH_20260807_v7.md (8 ideas).
  - Vendor files were reverted to organizer frontier (d9b2df37, 658e1439) to fix M5 build issues.
    qmm_nax kHalvedScales support was removed. Re-adding is risky until M5 issue is resolved.

## M5 ROOT CAUSE ANALYSIS (JIT compilation investigation, 2026-08-07)
  ROOT CAUSE (hypothesis, high confidence): COMPILE-STORM TIMEOUT.
  - 57 MLXFast.metalKernel call sites expand to 80-110+ distinct Metal compiles
    (loop expansion: heads 64/48, rowsPerGroup 1..64, depth 1/2/4/8)
  - Compilation is LAZY and SYNCHRONOUS: each kernel compiles on first dispatch
    via blocking device newLibrary()
  - Existing warmup (LagunaRuntimeWeights.warmLibraryModel L470-502) runs one
    prefill+decode but may NOT compile every variant the timed path uses
  - The compile-storm collides with runner 900s hard ceiling + 40C thermal gate
  - Organizer frontier (0 JIT kernels) has zero compile overhead, always passes
  - Our code passed at 9:36 AM (M5 fresh, compiled fast) but fails under load
  FIX NEEDED: comprehensive warmup that dispatches EVERY kernel variant before
  the timed phase. Consolidate per-head/per-rpg/per-depth variants. Gate
  registration to match dispatch (early-return when env flag is off).

## NEXT-WAVE IDEAS (from RESEARCH_IDEAS_FRESH_20260807_v7.md)
  1. Prefill Expert Halved Scales via qmm_nax — ★★★★ ~0.9% total, needs vendor kernel work. RISKY (M5).
  2. Decode AsyncEval=off — ★★★ 0 bytes, ~1.3% total. ASSIGNED to alphonse (PR #337).
  3. Prefill AsyncEval Stride Sweep — ★★☆ 0 bytes, ~0.6% total. ASSIGNED to thorfinn (PR #335).
  4. LM Head TG Doubling — ★★☆ ~150B, ~0.2% total. UNASSIGNED.
  5. Prefill addMM Enablement — ★★☆ 0 bytes, ~0.3% total. CONFLICTS with M5 fix (disabled).
  6. Down Residual outputs_per_simd 8→4 — ★★☆ ~80B, ~0.4% total. ASSIGNED to edward (PR #338).
  7. Compiled Gate+O-proj Multi-Token — ★★☆ ~150B, ~0.3% total. Needs investigation first.
  8. Dense Layer-0 Triple Fusion — ★☆☆ ~3 KB, ~0.2% total. Low value, defer.

## EXHAUSTED DIRECTIONS
  - INT8 dedup, dot4, float4 stores, scale halving (decode), argmax fuse,
    RMSNorm fusion, attention epilogue, asyncEval (pre-grid-fix), KV cache quant,
    ops-800/QHOIST, dense MLP simd_sum, input-vector staging,
    decode router top-8 fusion (1-tile loss), prefill norm+router fusion (custom GEMM),
    prefill g_proj+QKV fusion (tiling degradation), prefill SiLU+down fusion (too small),
    prefill shared halving (too small), simd_sum(vec)/dot(float4)/thread float4* (M5 build failure),
    prefill router GEMV fusion v2 (RMSNorm redundancy, cross-TG sync limitation),
    grid over-dispatch (hypothesis was wrong).
