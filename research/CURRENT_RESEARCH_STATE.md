# SENPAI Research State
- 2026-08-07T05:50Z (updated by advisor session)
- Campaign mlxfast-birch-20260805. Advisor HEAD: 2f5d630 (pushed to origin).
  9 composed changes on current frontier (PR #198 reverted). LRM: 521,648/524,288 = 2,640 B headroom.

## MERGED FRONTIER (11 changes, all bit-exact)
  1. MoE scale halving (PR #180): 45.5 MiB/step bandwidth savings, decode MoE kernels
  2. Packed simd_sum (PR #194): instruction reduction in cross-lane reductions
  3. O-proj NVFP4 scale halving (PR #192): bandwidth savings for O-proj
  4. INT8 gate-softplus dedup (PR #200): simd_shuffle broadcast
  5. INT8 O-proj dedup (PR #207): simd_shuffle broadcast
  6. INT8 QKV dedup (PR #206): simd_shuffle broadcast
  7. Shared SwiGLU float4 (PR #209): float4 pointer cast stores
  8. Routed MoE scatter float4 (PR #212): float4 pointer cast stores
  9. LM Head argmax+threshold fuse (PR #211): atomic argmax eliminates 1 dispatch
  10. INT8 indexed QKV dedup (PR #214): simd_shuffle broadcast
  11. Standalone shared down halving (PR #216): fallback path, completes halving family

  REVERTED: PR #198 (prefill MoE scale halving) — M5-only correctness bug in
  up-row-0 escape indexing. Fused gate/up bank is tile-interleaved, not
  [gate-half|up-half]. Escape sourced from wrong position. M4 passes (non-halved
  fallback); M5 fails correctness gate. Reverted as 6c81505.

## M5 SUBMISSION STATUS
  0781a45: FAILED (9-change frontier at 215e45f — included buggy PR #198)
  94a8526: FAILED (10-change frontier at b5a8bd0 — included buggy PR #198)
  c03dc11: REJECTED 2.5491 (-4.86%) (attention epilogue float4, single mechanism, commit be504bb)
  Root cause of both failures: PR #198 M5-only correctness bug. Now reverted.
  2d4160d7: VALIDATING (9-change frontier at 2f5d630 — PR #198 removed, PR #216 added)
  Submission note: research/SUBMISSION_NOTE_8change.md (7.5 KiB).
  c03dc11 score (2.5491) confirms single instruction-count reductions regress on bandwidth-bound M5.

## O-PROJ ESCAPE BYTE INVESTIGATION (2026-08-07)
  Subagent confirmed: O-proj kernel is the SAME custom JIT on M4 and M5 (not _nax).
  Quantizer (fp_quantize) is also same on both platforms. If M4 passed with
  halving ON (default, max_abs_diff=0 on 130 steps), M5 also passes.
  PR #192 is SAFE on M5. Research note alarm was a false positive — incorrectly
  applied the PR #198 pattern (_nax, M5-only) to PR #192 (custom JIT, both platforms).
  The escape byte SHOULD still be added for robustness but is NOT blocking.

## WAVE 5 RESULTS
  PR #219 (Edward dense-mlp-simd-sum): CLOSED — INVALID. Not bit-exact (simd_sum
  uses different FP reduction tree than shuffle_down ladder; ULP errors accumulate
  over 124 decode steps, flip near-tie token). Wasted bandwidth hypothesis was
  WRONG: shuffle_down delta 16→1 is a butterfly tree that sums ALL 32 lanes.
  Key lesson: any change to FP reduction order in a logits-contributing kernel
  will accumulate ULP errors over 128 decode steps and may flip near-tie tokens.

  Previous rejections (all included ops-800/QHOIST, now reverted):
  27b9c7c (2.4972), a3e3800 (2.4073), f2160f8 (2.5582),
  ec2b0a5 (2.4839), 0fe73ec (2.4629), 259c265 (2.4522)
  Promoted: 97a5090 (maple campaign), score 2.5888 (+3.64%).
  Birch clean base (12a712d): score 2.5459 on M5. Gap to beat: +1.69%.

## NEW ASSIGNMENTS (Wave 7, created this session)
  PR #220 (thorfinn): Fix and re-apply PR #198 prefill MoE scale halving — correct
    up-row-0 escape indexing for tile-interleaved layout. M5-only (can't test on M4).
    Key fix: up_escape at fused row 32 (not 512).
  PR #221 (alphonse): Input-vector staging to threadgroup shared memory — reduce LSU
    pressure in decode MoE kernels. ~300-400B per kernel. M4-testable.
  PR #222 (askeladd): Fold shared expert gate/up QMV into routed dispatch — eliminate
    39 extra dispatches/step. Budget-tight (~1200-2000B). M4-testable.
  Edward: FREE (PR #219 closed). Next assignment: QKV NVFP4 scale halving
    (23.75 MiB savings, ~0.72% decode gain, ~500-600B budget, bit-exact with escape).

## RESEARCH THEMES
  - CRITICAL DISCOVERY: PR #198 prefill MoE halving had M5-only correctness bug.
    _nax kernels only compile on M5 (GPU gen 17+). M4 cannot validate _nax changes.
    Any change to vendor _nax kernel files MUST be verified by careful code review.
  - M5 is bandwidth-bound, NOT instruction-bound. NVFP4 decode ~2 FLOP/byte vs
    27 FLOP/byte ridge point — 13x below arithmetic intensity.
  - Fresh ideas (research/RESEARCH_IDEAS_FRESH_20260807_v2.md):
    1. QKV NVFP4 scale halving: 23.75 MiB savings, ~0.72% decode, ~500-600B (NEXT for Edward)
    2. O-proj escape byte fix: defensive (confirmed safe but not robust)
    3. Prefill MoE halving fix: correct escape for tile-interleaved (PR #220)
    4. Prefill down scale halving: 8 MiB savings, ~0.46% prefill (M5-only)
    5. EXPERT_GATHER_GROUPS sweep: 0-byte prefill threadgroup sweep
  - KEY LESSON: simd_sum ≠ simd_shuffle_down bit-exactness — different FP
    reduction trees accumulate ULP errors over 128 decode steps. Any change
    to FP reduction order in a logits-contributing kernel risks token flips.
  - O-PROJ HALVING SAFE: custom JIT kernel (not _nax), same on M4/M5.
    Quantizer also same on both platforms. M4 max_abs_diff=0 confirms safe.
  - Exhausted: INT8 dedup family (complete), dot4 (done/dead), float4 stores (done),
    scale halving (decode done, prefill needs fix), argmax fuse (done),
    RMSNorm fusion (dead), attention epilogue 1-pass (dead), asyncEval (near-optimal),
    KV cache quant (not bit-exact), ops-800/QHOIST (toxic, reverted)

## BUDGET STATUS
  LRM: 521,648/524,288 = 2,640 B headroom
  Total surface: ~2,972K/3,000,000 = ~28K B headroom
  LagunaLmHeadPrune.swift: ~43K/524,288 = ~481K B headroom
  fp_quantized_nax.h: ~77K/524,288 = ~447K B headroom
  quantized.cpp: ~83K/524,288 = ~441K B headroom
