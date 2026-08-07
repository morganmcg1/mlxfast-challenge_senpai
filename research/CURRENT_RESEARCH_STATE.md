# SENPAI Research State
- 2026-08-07T07:20Z (updated by advisor session)
- Campaign mlxfast-birch-20260805. Advisor HEAD: 7214e8a (pushed to origin).
  12 composed changes on current frontier (PRs #220, #225, #226 cherry-picked).
  LRM: 514,701/524,288 = 9,587 B headroom. Total: 2,975,392/3,000,000 = 24,608 B headroom.

## MERGED FRONTIER (12 changes, all bit-exact)
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
  12. Prefill MoE scale halving FIXED (PR #220): correct up-row-0 escape for
      tile-interleaved layout. M5-only _nax path. ~1% prefill gain.
  Also merged: QKV NVFP4 scale halving (PR #225), O-proj escape fix (PR #226).

  REVERTED: PR #198 (original prefill MoE scale halving) — M5-only correctness
  bug in up-row-0 escape indexing. Fixed and re-applied as PR #220.

## M5 SUBMISSION STATUS
  Best recent: 08ddee4 at 2.5748 (-2.25% vs 2.5888 target). All submissions rejected.
  Last rejected: 0bc3eb4 at 2.5622 (-3.55%). Submission slot is FREE.
  Target: beat 2.5888 (maple campaign, submission 97a5090, +3.64%).
  Gap to close: +0.55% from best (2.5748 → 2.5888).
  Key: instruction-count reductions REJECTED on M5 (bandwidth-bound). Strategy:
  bandwidth reduction + dispatch elimination only.

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

## ACTIVE ASSIGNMENTS (Wave 8, all 4 students assigned, BASE_SHA=7214e8a)
  CLOSED: PR #222 (askeladd fold-shared-gateup) — DEAD: merged 9-slot kernel 0.55%
    SLOWER. asyncEval already overlaps independent dispatches. Key learning:
    dispatch fusion with if/else branching hurts performance.
  ABANDONED: PR #229 (edward prefill-down-halving-v1) — duplicate assignment marker
    bug blocks ALL typed transitions. Edward reassigned to PR #234 (clean marker).
  PR #234 (edward): Prefill MoE down scale halving v2 — halve 64 MiB prefill down
    scale traffic via NVFP4 pairwise constancy. ~0.46% score, bit-exact, M5-only.
        scales via NVFP4 pairwise constancy. ~0.46% score, bit-exact, M5-only.
  PR #230 (alphonse): Fuse g_proj INT8 matmul + softplus into NVFP4 O-proj kernel —
    eliminate 40 dispatches/step. ~0.75% score, bit-exact, M4-testable. HIGHEST priority.
    KEY: eliminates DEPENDENT dispatch (gate-softplus→O-proj data dependency,
    asyncEval cannot overlap). Different from dead PR #222 (independent dispatches).
  PR #231 (thorfinn): Shared SwiGLU QMV gate/up scale halving — wire dead halved
    tensors into shared expert kernel. ~0.11% score, bit-exact, M4-testable.
  PR #232 (askeladd): Gate-softplus scale/bias interleaved packing — interleave
    scales+biases into single array for cache locality. Bit-exact, ~300B, M4-testable.

## COMPOSITION PLAN
  If 3 main assignments succeed: ~0.46% + ~0.75% + ~0.11% = ~1.32% total.
  Starting from 2.5748 → ~2.609. Would BEAT 2.5888 target.
  Submit independently first, then compose winners for combined submission.

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
    KV cache quant (not bit-exact), ops-800/QHOIST (toxic, reverted),
    dense MLP simd_sum (not bit-exact, wrong hypothesis), input-vector staging (dead,
    barrier overhead > LSU relief)

## BUDGET STATUS
  LRM: 514,701/524,288 = 9,587 B headroom
  Total surface: 2,975,392/3,000,000 = 24,608 B headroom
  LagunaLmHeadPrune.swift: ~47K/524,288 = ~477K B headroom
  fp_quantized_nax.h: ~78K/524,288 = ~446K B headroom
  quantized.cpp: ~84K/524,288 = ~440K B headroom
  Growth limit per submission: 262,144 bytes
