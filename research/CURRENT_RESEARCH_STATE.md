# SENPAI Research State — mlxfast-birch-20260805
- 2026-08-08T07:05Z (updated by advisor session)
- Advisor HEAD: bc2d05a5 (warmup fix 27fb31c0 + research state, pushed to origin).
- Bare minimum frontier (no XMAJOR, no full-attn fused) + warmup fix.
- LRM: 293KB, 17 metalKernel calls. Total surface ~2.77M/3,000,000.
- Last M5 success: f790e33f (score 2.5213). 45 consecutive M5 build failures.
- Leaderboard #1: yudduy 2.6063. Our promoted: 2.5888. Gap: ~0.67%.

## M5 BUILD CRISIS — ROOT CAUSE FOUND (v2)
  46 consecutive M5 build failures since f790e33f (last M5 success, Aug 7 18:51 UTC).
  Warmup fix (512 tokens + MLX_MAX_OPS=400) was necessary but NOT sufficient (6b51632 FAILED).

  TRUE ROOT CAUSE (confirmed by subagent analysis):
  The LRM "nuclear fallback" refactoring (a2cb0a0a) replaced 31 custom Metal kernels with standard MLX ops.
  While JIT compile COUNT is similar (~20-30 in both), JIT compile COST per compile is 5-10x higher:
  - Standard MLX ops compile from large shared headers: quantized.h (2,608 lines), steel_attention (1,160 lines), steel_gemm (718 lines)
  - Custom kernels compile from small source strings (30-300 lines)
  - Total Metal source compiled during warmup is 5-10x larger in current code vs f790e33f
  - This exceeds the M5 ~900s compile timeout

  FIX: Restore custom prefill kernels to replace standard MLX ops on the prefill path.
  Priority: MoE SwiGLU (quantizedMM 2,608-line header) > QKV projection (matmul 718-line header) > QK-norm+RoPE (RMSNorm)
  Keep decode optimizations (fused QKV+g_proj, halved scales, etc.) — they use small custom kernels.

## M5 BUILD ROOT CAUSE (CONFIRMED 2026-08-08T07:30 UTC)
  Deep analysis of f790e33f vs current HEAD: the actual JIT compile delta is only 3 standard MLX compiles:
  1. rope.metal (229 lines) for prefill RoPE — f790e33f used custom lagunaPrefillSlidingQKNormRoPEKernel
  2. rms_norm.metal (391 lines) for prefill QK-norm — f790e33f used same custom kernel
  3. steel_attention (1,160 lines) for decode full-attn — f790e33f used custom lagunaFullFusedAttentionKernel

  CRITICAL: f790e33f used STANDARD gatherQuantizedMM for prefill MoE and STANDARD matmul for QKV/O-proj.
  Custom MoE/QKV kernels were decode-only (x.dim(1)==1 guard). Restoring them for prefill won't reduce JIT compile time.
  The groupSize=32 quantizedMM calls are guarded by lagunaPrefillSharedHalvedEnabled=false — never reached, never compiled.

  FIX PLAN: PR #407 (prefill QK-norm+RoPE, already complete, needs rebase) + PR #420 (full-attn, thorfinn WIP)
  These 2 PRs eliminate the 3 extra JIT compiles. Edward/alphonse redirected to verify and rebasing.

## M5 SUBMISSION STATUS (2026-08-08T07:51 UTC)
  7f9cce1b: VALIDATING — frontier fc66737f (composition of PR #407 + #402 + #411)
  Partial fix: 2 of 3 JIT compile deltas fixed (rope.metal + rms_norm.metal)
  Missing: steel_attention (1,160 lines) for decode full-attn — PR #420 (thorfinn WIP)
  If build passes: great, add PR #420 v2 (decode full-attn wiring) for further optimization
  If build fails: add PR #420 v2 and resubmit

  CRITICAL: PR #420 v1 has DEAD CODE — decode full-attn kernels defined but NOT wired into dispatch.
  Thorfinn requested revision v2 to wire them in. Askeladd (PR #426) told to wait for v2.

## M5 BUILD FIX ASSIGNMENTS (Wave 13, BASE_SHA=b9394914)
  PR #407 (edward, v2): Prefill QK-norm+RoPE fusion — ACCEPTED, needs rebase onto 3df94c4c (merge conflicts)
  PR #418 (edward): Restore prefill MoE kernels — LIKELY NOT NEEDED (f790e33f used standard gatherQuantizedMM)
  PR #419 (alphonse): Restore QKV+QK-norm+O-proj — REDIRECTED to rebase PR #407 (QKV/O-proj not in f790e33f prefill)
  PR #420 (thorfinn): Restore full-attention kernels — CRITICAL (eliminates steel_attention decode compile)
  PR #402 (askeladd): kHalvedScales runtime constant — ACCEPTED, compose after M5 builds
  PR #411 (thorfinn): _nax compile reduction — ACCEPTED, safe cleanup, merge opportunistically

## ON HOLD (will re-apply once M5 build is fixed)
  PR #407 (edward v2): Prefill QK-norm+RoPE fusion — ACCEPTED on current base, waiting for M5 build fix
  PR #414 (alphonse): XMAJOR fold — CLOSED (blocked, code ready, will re-apply)
  PR #415 (thorfinn): Full-attn fused recovery — CLOSED (blocked, code ready, will re-apply)
  PR #411 (thorfinn): _nax compile reduction — ACCEPTED on current base (dormant path cleanup)

## CLOSED
  PR #412 (alphonse): LM-head RMSNorm fusion — DEAD (+2.5% decode regression)
  PR #416 (edward): Compile budget audit — Complete (confirmed root cause)
  PR #417 (edward): Composition merge — CLOSED (pivoted to M5 build fix)

## GRID OVER-DISPATCH HYPOTHESIS: DEFINITIVELY REFUTED (PR #333 + PR #394)
MLXFast API uses dispatch_threads(grid=TOTAL_THREADS, group=threads_per_tg).
Confirmed in Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/custom_kernel.cpp:117.
The × threadGroupSize multipliers (*32, *64, *512, *1024) are CORRECT — they create
the right number of threadgroups. Removing them causes correctness failures
(fewer threadgroups = fewer items processed). PR #394's 35% improvement was a
false positive: GPU did 28x less work (2 heads instead of 56), hidden by
MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT=1. DO NOT REVISIT.

## M5 BUILD FIX STATUS — REVISED ANALYSIS (2026-08-08)
  PREVIOUS HYPOTHESIS: CUMULATIVE COMPILE-STORM TIMEOUT — NOW QUESTIONED.

  KEY FINDING: f790e33f (last M5 success) had 48 metalKernel calls, 511KB/11313 lines LRM.
  126dc82e (current frontier, M5 fails) has 16 metalKernel calls, 302KB/6624 lines LRM.
  We SHRANK LRM by 40% and reduced kernels by 67%, yet M5 STILL fails!

  Only vendor file changed: sdpa_vector.h (SDPA Phase 1: GROUP_FULL=3, GROUP_SLIDING=2).
  No changes to fp_quantized_nax.h, quantized.cpp, or MLXFastTransform.

  BUT: d5a296c5 (full SDPA revert) also FAILED — so it's not solely SDPA.
  The issue is cumulative but NOT from kernel count or file size.

  POSSIBLE CAUSES:
  1. Per-kernel complexity increased (16 kernels avg ~126 lines vs 48 at ~85 lines)
  2. sdpa_vector.h AOT compile complexity (6 exchange planes, staggered GQA4)
  3. Test file growth (1177 new lines in Tests/) may be included in M5 build
  4. Intermittent — build time at the boundary, slight variance causes pass/fail

  STRATEGY: Nuclear fallback from f790e33f (known to build), then add changes incrementally.

## ACTIVE ASSIGNMENTS (Wave 13, 2026-08-08)
  PR #405 (alphonse): Nuclear fallback — rebuild from f790e33f with only dead kernel deletions
  PR #406 (thorfinn): JIT compile reduction audit — all metalKernel() calls
  PR #402 (askeladd): kHalvedScales runtime constant reimpl (~0.9% score recovery)
  PR #407 (edward): Compile budget engineering — free 2 JIT slots, re-enable prefill QK-norm+RoPE

## FRESH IDEAS (research/FRESH_IDEAS_20260808_v2.md, 8 ideas)
  1. XMAJOR column-tile fold revival (prefill, 0.3-0.5%, M5-only, ~5KB vendor)
  2. Compile budget → re-enable prefill QK-norm+RoPE (prefill, 0.3-0.5%, ≤0 bytes)
  3. Full-attention fused decode kernel (decode, 0.3-0.7%, M5≠M4)
  4. LM-head pruner RMSNorm fusion (decode, 0.05-0.15%, ~300B)
  5. STAGE_* fc→#define conversion (build enabler, 0% direct, negative bytes)
  6. Down-residual reduction occupancy (decode, 0.05-0.2%, ~300B)
  7. KV cache K/V interleaving (decode, 0.1-0.3%, high risk)
  8. Prefill gate-softplus dedup (decode, 0.05-0.1%, ~100B)
  Combined potential: 0.7-1.5% total score, could close the 0.67% gap to 2.6063.

## NEXT ASSIGNMENT READY (when student becomes idle)
  XMAJOR column-tile fold revival (Idea 1):
  - Recover kernel arms: git show 2cad1776~1:...fp_quantized_nax.h lines 1700-1850 (151 lines)
  - Re-enable: change darkbloom_gather_xmajor_ct() return 0→2 in quantized.cpp:1564
  - JIT define injection still in place: jit_kernels.cpp:1169 darkbloom_gather_xmajor_define()
  - Dispatch infrastructure intact: quantized.cpp:1918 grid division by xmajor_ct
  - M5-only (uses _nax kernels, M4 can't test), ~5KB vendor budget, bit-exact

## M5 BUILD BREAKTHROUGH (2026-08-08T06:55Z)
  Root cause identified by subagent code review: LagunaRuntimeWeights.swift changes.

  **Warmup prefill shape 512→2 tokens**: Standard MLX kernels (SDPA, matmul, quantizedMM)
  specialize by shape. A 2-token warmup does NOT pre-compile 512-token scored PSOs.
  M5 JIT-compiles them during the scored run → ~900s timeout. LIKELY PRIMARY CAUSE.

  **MLX_MAX_OPS_PER_BUFFER 400→200**: Halves command-buffer limit, changes MLX fusion
  granularity. SECONDARY CAUSE.

  **New heavy lagunaFusedGProjQKVHalvedKernels**: 2 large fused-g_proj QKV compiles
  (~4x larger source) that f790e33f never had. TERTIARY CAUSE.

  Fix applied (27fb31c0): warmup 2→512 tokens, MLX_MAX_OPS 200→400.
  Waiting for d85aeb0d (bare minimum) to finish before submitting warmup fix.

  ALL vendor files (sdpa_vector.h, fp_quantized_nax.h, quantized.cpp) are IDENTICAL
  to f790e33f. The M5 failure is entirely in LRM/LmHeadPrune/Weights changes.

## M5 SUBMISSION STATUS
  d85aeb0d: VALIDATING (~7 min — longer than usual, may be building)
  db536735: FAILED — nuclear fallback + dead code + SDPA revert + full-attn fused, NO XMAJOR
  5ef630e0: FAILED — sdpa_vector.h revert + XMAJOR fold + dead code (b8c843aa)
  07634617: FAILED — nuclear fallback + SDPA Phase 1 (a2cb0a0a)
  All submissions since f790e33f FAILED (44 consecutive)
  Warmup fix (27fb31c0) READY but blocked by d85aeb0d in flight.
  Leaderboard #1: yudduy 2.6063. Our promoted: 2.5888. Gap: ~0.67%.

## CURRENT FRONTIER (27fb31c0)
  Nuclear fallback + dead code removal + SDPA revert + warmup fix (512 tokens, MLX_MAX_OPS=400)
  NO XMAJOR fold (reverted), NO full-attn fused (reverted to cafa2e47 LRM)
  17 metalKernel calls, 293KB LRM
  SDPA: f790e33f PAIR_HEADS=2
  ALL vendor files identical to f790e33f
  Missing: XMAJOR fold, full-attn fused, kHalvedScales, prefill QK-norm+RoPE

## ACTIVE ASSIGNMENTS (Wave 14, BASE_SHA=987c21c5)
  PR #407 v2 (edward): Prefill QK-norm+RoPE fusion — REBASE REQUESTED onto 987c21c5. v1 succeeded: +0.7% decode, +3.4% prefill, +1.3% est score on M4.
  PR #402 (askeladd): kHalvedScales runtime constant reimpl — recover ~0.9% score. Student working.
  PR #411 (thorfinn): _nax compile count reduction — audit template instantiations, eliminate dormant variants. Just assigned.
  PR #412 (alphonse): LM-head pruner RMSNorm fusion — fuse final RMSNorm into coarse kernel, eliminate 1 dispatch/step. Just assigned.

## KEY FINDINGS (thorfinn audit, PR #406)
  MLX JIT is lazy — dead kernels never compile. Actual JIT compile count is ~13 (not 19).
  Compile-storm is caused by 15-25 _nax compiles + 2 graph compiles, not metalKernel declarations.
  INT8 affine OProj kernels (lagunaGatedAffineOProjKernel, lagunaGatedAffineOProjIndexedKernel) are dead code.
  NVFP4 !gateIsActivated branch is dead (always returns nil).
  lagunaSlidingQKNormRoPEKernel is NOT dead (used during early prefill for sliding layers).
  a46cfdaa (kHalvedScales reverted + SDPA Phase 1): FAILED
  PR #350 (function constants) REDUCED compile count ~82→~40 but may increase per-compile complexity.
  STRATEGY: Nuclear fallback (PR #405, alphonse) — rebuild from f790e33f with only dead kernel deletions.
  This should be below the timeout boundary since f790e33f succeeded and dead kernel deletions reduce compile count.

## GRID OVER-DISPATCH HYPOTHESIS: REFUTED
MLX's MLXFast API uses dispatchThreads(gridSize, threadgroupSize) where grid = TOTAL THREADS.
The × threadGroupSize multiplier in grid expressions is CORRECT. PR #333 was closed as invalid.
Do NOT revisit this hypothesis.

## M5 SUBMISSION STATUS (CRITICAL — INTERMITTENT BUILD FAILURES)
  4d2b9f60: VALIDATING (3:32 AM UTC) — frontier 2035cd14 (SDPA Phase 1+2 + LM-head pruner consolidation, -6 JIT, PR #357 disabled)
  47d9bc08: FAILED — frontier b41681c9 (SDPA Phase 1+2 + dead code cleanup, -4 JIT)
  Last SUCCESSFUL builds: 3ff3992 (2.5213, 8/7 6:51 PM), 68b66c5 (2.5520, 8/7 9:36 AM), df9613a (2.5817, 8/7 8:19 AM)
  Best score: df9613a (2.5817)
  Leaderboard #1: yudduy 2.6063. Our promoted: 97a5090 2.5888 (maple campaign).
  Gap to close: +0.67% from 2.5888 → 2.6063.

  ROOT CAUSE ANALYSIS (from subagent investigation 2026-08-08):
  - Failures are INTERMITTENT, not deterministic — same code passed then failed (68b66c5 vs 70929a5)
  - Compile count math: ~34-44 total compiles at ~3.5s each = ~120-154s, well under ~900s timeout
  - BUT: _nax compiles may take 10-30s each (complex GEMM templates), so total could be 366-766s
  - kHalvedScales (PR #342) adds NEW _nax template instantiations, pushing compile time to edge of timeout
  - kHalvedScales was previously removed for M5 issues (36df2138), then re-added (12eaa973)
  - SDPA metallib was STALE in upstream equivalence test — SDPA changes never validated with fresh metallib
  - Vendor files are NOT clean: 6 files differ from organizer frontier (sdpa_vector.h, fp_quantized_nax.cpp/h, quantized.cpp, jit_kernels.cpp, SwitchLayers.swift)
  - If 4d2b9f60 fails: REVERT kHalvedScales (PR #342) to reduce _nax compile time
  - Dead code deletions are LOW RISK (only Swift metalKernel declarations, not vendor Metal kernels)

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
  PR #357 (askeladd): Re-enable PREFILL_QK_NORM_ROPE — MERGED then TACTICALLY DISABLED (prefill ~1.5%, +76B, +2 JIT compiles — disabled for M5 build)
  PR #361 (edward): Gate compile consolidation — MERGED (-1 MLX graph compile, net -525B, bit-exact)
  PR #367 (askeladd): Router shuffle vectorization — MERGED (uint2 packing, 0-byte, bit-exact, +0.35% decode +2.54% prefill on M4)
  PR #368 (edward): Dead rpg kernel deletion — MERGED (-1,493B code budget, 0-JIT, bit-exact)
  PR #363 (alphonse): Router kernel consolidation — MERGED (-1,578B, bit-exact, 0 JIT savings — non-normalizing variants are dead code)
  PR #370 (askeladd): Dead O-proj variant deletion — MERGED (-1,350B, 0-JIT, bit-exact)
  PR #371 (edward): Dead QKV/SwiGLU variant deletion — MERGED (-27,718B, 6 kernels + 2 functions + 3 env flags, 0-JIT, bit-exact)
  PR #373 (alphonse): Prefill MoE tail unification — MERGED (-1,073B, -1 default JIT compile, bit-exact) ★ LAST JIT LEVER

  Total session: 13 PRs merged, all bit-exact. Net bytes: -121,006B.
  JIT compile reduction: -1 (warmup) + -1 (gate) + -1 (MoE tail) = -3 default compiles.
  SDPA: Phase 1 (GQA6 3-head, 10/40 layers) + Phase 2 (GQA8 4-head, 30/40 layers) = 39.4% K/V reduction.

## ACTIVE ASSIGNMENTS (BASE_SHA=b41681c9)
  PR #380 (askeladd): LM-head pruner kernel consolidation — -2 JIT compiles (6→4), M5 build fix
  PR #381 (edward): DARKBLOOM_STAGE_BM128 variant sweep — prefill GEMM tiling, 0-byte, bit-exact
  alphonse: IDLE — needs new assignment (completed PR #376 dead kernel audit)
  thorfinn: IDLE — completed SDPA Phase 2 (PR #377 merged)
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
