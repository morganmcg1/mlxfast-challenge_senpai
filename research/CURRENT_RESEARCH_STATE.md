# SENPAI Research State — mlxfast-birch-20260805
- 2026-08-08T01:25Z (updated by advisor session)
- Advisor HEAD: f59f25b8 (pushed to origin). 38+ bit-exact changes on current frontier. PR #357 merged (prefill QK-norm+RoPE re-enable).
- LRM: 502,603/524,288 = 21,685 B headroom. Total surface 2,937,409/3,000,000 = 62,591 B headroom.

## GRID OVER-DISPATCH HYPOTHESIS: REFUTED
MLX's MLXFast API uses dispatchThreads(gridSize, threadgroupSize) where grid = TOTAL THREADS.
The × threadGroupSize multiplier in grid expressions is CORRECT. PR #333 was closed as invalid.
Do NOT revisit this hypothesis.

## M5 SUBMISSION STATUS (CRITICAL — 33+ CONSECUTIVE FAILURES)
  891582e2: VALIDATING (1:18 AM UTC) — frontier f688a03f (warmup disabled + MLX_MAX_OPS_PER_BUFFER=400)
  f17cf7f6: FAILED — validating ~70 min then failed
  Previous failures: c8a7016, e1a2c89, 3ce7145 (all failed, compile-storm timeouts)
  Last SUCCESSFUL build: 68b66c5 (score 2.5520)
  Best score: df9613a (2.5817)
  Leaderboard #1: yudduy 2.6063. Our promoted: 97a5090 2.5888 (maple campaign).
  Gap to close: +0.67% from 2.5888 → 2.6063.
  Root cause: JIT compile-storm (~19 custom JIT + ~15-25 M5-only _nax compiles) intermittently exceeds M5 runner timeout.

## M5 COMPILE AUDIT (from subagent report, research/M5_COMPILE_AUDIT_20260808_0104.md)
  Default-run custom JIT compiles: 19 (not 55)
  - Decode steady-state: 9 (embedding+RoPE atlas, sliding fused attention, sliding standalone QKNorm [warmup-only],
    fused GProj QKV halved, activated O-proj halved, residual+RMSNorm router rpg8, residual+RMSNorm,
    routed SwiGLU packed top8 R1, routed+shared down residual)
  - LM-head pruner: 6 (both refine + non-refine variants compile — prefill uses non-refine, decode uses refine)
  - Prefill-only: 3 (shared SwiGLU, prefill MoE tail, sorted MoE tail)
  - Warmup waste: 1 — lagunaFullFusedAttentionKernel warmed but NEVER scored-dispatched (FIXED: warmup disabled)
  KEY: The ~15-25 M5-only _nax compiles are INHERENT (M5 GEMM speed path, cannot disable).

## MERGED THIS SESSION
  PR #357 (askeladd): Re-enable PREFILL_QK_NORM_ROPE — MERGED (prefill ~1.5% improvement, bit-exact, +76B)

## ACTIVE ASSIGNMENTS (BASE_SHA=f59f25b8)
  PR #366 (thorfinn): SDPA GQA pair_heads 3/4 — halve K/V traffic for GQA6/GQA8 attention (AOT metallib, ~0.6-1.0% score)
    ★ HIGHEST IMPACT: directly addresses bandwidth-bound decode. yudduy #1 uses pair_heads=3/4.
    887-line plan at research/SDPA_PAIR_HEADS_PLAN.md
  PR #363 (alphonse): Router kernel consolidation — -2 JIT compiles (M5 build fix, net-negative bytes)
  PR #361 (edward): Consolidate compiled gate functions — -1 MLX graph compile (M5 build fix, 0-200B)
  PR #367 (askeladd): Router Top-8 shuffle vectorization — pack 2 scalar shuffles into 1 uint2 vector (0-byte, bit-exact, fyrsta7 #2 approach)
  ROOT CAUSE (high confidence): JIT compile-storm timeout. 19 custom JIT + ~15-25 M5-only _nax
  compiles during warmup + prefill + decode intermittently collide with M5 runner ~900s timeout + 40C thermal gate.
  Organizer frontier (0 custom JIT kernels) always passes.
  WARMUP FIX APPLIED: Disabled full-attention kernel warmup (lagunaWarmFullFusedAttentionKernel, never scored).
  Raised MLX_MAX_OPS_PER_BUFFER 200→400 for M5 graph compile headroom.

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
  CRITICAL REVELATION: Default custom JIT compile count is only **19** (not 55).
  The 55 figure counts metalKernel DECLARATIONS; only 19 are actually DISPATCHED.
  Breakdown: 9 decode + 6 LM-head pruner + 3 prefill + 1 warmup waste = 19 custom.
  Plus ~15-25 _nax (M5-only) = ~34-44 total compiles. At ~3.5s each = ~120-154s.
  Well under ~900s timeout. M5 failure may be LOAD-RELATED (contention with other
  solvers) or a non-compile issue (correctness/runtime).

  APPLIED FIXES:
  1. PR #350: kernel consolidation (~82→~57 declarations, but 19 actual compiles)
  2. PR #352: 5 flags disabled (fewer lazy kernels)
  3. PR #358: H4 variant deletion (-2 declarations, -7KB)
  4. Warmup prefill 512→2 tokens (commit 26e84d88)
  5. Op.1 (commit 715c1ff6): disable full-attn kernel warmup (-1 actual compile)
  6. MLX_MAX_OPS_PER_BUFFER 200→400 (commit 715c1ff6, +0.03 score, competitor-proven)

  M5 SUBMISSIONS: 35+ consecutive failures. f17cf7f6 FAILED (commit 22aaebc, build timeout).
  NEW: 891582e2 VALIDATING (10th attempt with warmup removal + MLX_MAX_OPS_PER_BUFFER=400, from HEAD 7487b620).

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
