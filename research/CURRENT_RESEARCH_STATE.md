# SENPAI Research State
- 2026-08-07T10:40Z (updated by advisor session)
- Campaign mlxfast-birch-20260805. Advisor HEAD: 7252285 (pushed to origin).
  21 composed changes on current frontier (19 previous + PR #253 + PR #254).
  LRM: 521,820/524,288 = 2,468 B headroom. Total surface ~2,970K/3,000,000.

## MERGED FRONTIER (21 changes, all bit-exact)
  1-14. Previous frontier (PR #180, #194, #192, #107, #114, #116, #119, #231, #232, #114, etc.)
  15. PR #230: Fuse g_proj+QKV into NVFP4 QKV R1 kernel (decode, ~2.0% decode, bit-exact)
  16. PR #245: INT8 O-proj dot4 vectorization (decode, ~0.8-1.1% on M5, bit-exact)
  17. PR #243: Prefill shared expert scale halving via qmm_nax kHalvedScales (prefill, ~0.22%, M5-only)
  18. PR #234: Prefill MoE down projection scale halving v2 (prefill, ~0.46%, M5-only)
  19. PR #251: Attention Q·K score dot4 vectorization (MERGED then REVERTED as cdefbb9 — M5 build failure from simd_dot(vec<float,4>) in JIT kernel)
  20. PR #253: Prefill shared expert scale array precomputation (prefill, ~0.375-1.2% score, bit-exact, +140B)
  21. PR #254: Router keys dead output elimination (decode, bit-exact, net-negative ~-300-500B)
  M5 FIX: ad58c92 — removed unused constexpr gate_heads from PR #230 kernel (caused M5 build failures 9500c1f, a69d876)

## M5 SUBMISSION STATUS
  8b5b01d: VALIDATING (since 10:30 UTC) — frontier e0623cf (20 changes, includes PR #253, excludes reverted #251)
  70929a5: FAILED — frontier cdefbb9 (revert of #251, code identical to ad58c92 which scored 2.5520)
  d6c548e: FAILED — frontier 6758db1 (included PR #251 simd_dot → M5 build failure)
  68b66c5: REJECTED, score 2.5520 — frontier ad58c92 (LAST SUCCESSFUL BUILD)
  df9613a: REJECTED, score 2.5817 — frontier before #234/#243 (BEST SCORE)
  Leaderboard: fyrsta7 2.6040 (current #1). Our promoted: 97a5090 2.5888 (maple campaign).
  Gap to close: +0.86% from best (2.5817 → 2.6040).

## VARIANT 3 EXPERIMENT (PREPARED, UNCOMMITTED)
  DARKBLOOM_STAGE_BM128 variant 3: BM128/WM8/WN1 (SM=16, reglocal preserved)
  - Changes: quantized.cpp L1702 (add wn=1 to case 3), L1504 (default 5→3), LRM L235 (add "3" to gate list)
  - Satisfies kSwigluRegLocal: (WN==1) && (BN==64) && ((BM/WM)==16) → 128/8=16 ✓
  - The ONLY variant that preserves WN=1 (reglocal) while reaching SM=16 (proven winning band)
  - Build verified locally on M4 (56.75s). Awaiting 8b5b01d result before committing and submitting.
  - Risk: BM=128 doubles M-tile (M/128 vs M/64 threadgroups in M-dim). M5 has 40 cores; M=512 prefill → 4 vs 8 TGs.
  - This is a prefill-only knob (25% of score). Need M5 measurement for final verdict.

## ACTIVE ASSIGNMENTS (Wave 12, BASE_SHA=7252285)
  PR #258 (edward): Full-attention params atlas — eliminate 1,280 per-decode-window allocations (bit-exact, ~0.0375-0.075% decode, ~+200B)
  PR #259 (alphonse): Prefill values transpose fold — eliminate 40 dispatches/prefill by folding values transpose into QK-norm+RoPE kernel (bit-exact, ~0.125-0.25% prefill, ~+300-500B)
  PR #260 (askeladd): _nax BK padding optimization — reduce BK_padded from 80 to 68 bytes, ~15% threadgroup memory reduction (bit-exact, vendor file, ~0.1-0.3% decode/prefill)

## MERGED WAVE 11
  PR #253 (edward): Prefill shared scale array precomputation — MERGED (~+140B)
  PR #254 (alphonse): Router keys dead output elimination — MERGED (net-negative bytes)

## CLOSED (Wave 10)
  PR #248 (alphonse): Scalar RMSNorm fusion — DEAD (9.2% slower + correctness failure, FP reduction order mismatch)
  PR #247 (askeladd): qdot shared header dot4 — DEAD (compiler auto-vectorizes)
  PR #251 (thorfinn): Q·K simd_dot — MERGED then REVERTED (M5 build failure, simd_dot not supported on M5 Metal compiler)

## NEXT-WAVE IDEAS (from RESEARCH_IDEAS_M5_KNOBS_20260807.md)
  1. Full-attention params atlas — ASSIGNED to edward (PR #258)
  2. Prefill values transpose fold — ASSIGNED to alphonse (PR #259)
  3. _nax BK padding optimization — ASSIGNED to askeladd (PR #260)
  4. DARKBLOOM_EXPERT_GATHER_GROUPS 256→128 — NOT actionable (256 is faster)
  5. Non-expert STAGE_WIDEST/WIDELD — NOT actionable (scored path uses expert-aligned)
  6. callLastPrefillRow QK-norm fuse — UNASSIGNED (marginal, 1 layer only)

## RESEARCH THEMES
  - M5 is bandwidth-bound (~89% GPU util). Only bandwidth reduction or dispatch elimination helps.
  - Instruction-count reduction (dot4) shows gains on M5 but NOT M4 (M4 is bandwidth-bound).
  - Unused constexpr in Metal JIT kernel strings may cause M5 build failure even when M4 compiles fine.
  - RMSNorm fusion is a dead end: stock dispatch is optimal, FP reduction order changes flip near-tie tokens.
  - LRM budget is the binding constraint: 1,832 B headroom. Byte-negative changes (PR #251, #254) are valuable.
  - Prefill path is relatively unoptimized vs decode — prefill dispatch elimination is the main opportunity.
  7. Shared SwiGLU float4 (PR #209): float4 pointer cast stores
  8. Routed MoE scatter float4 (PR #212): float4 pointer cast stores
  9. LM Head argmax+threshold fuse (PR #211): atomic argmax eliminates 1 dispatch
  10. INT8 indexed QKV dedup (PR #214): simd_shuffle broadcast
  11. Standalone shared down halving (PR #216): fallback path, completes halving family
  12. Prefill MoE scale halving FIXED (PR #220): correct up-row-0 escape for
      tile-interleaved layout. M5-only _nax path. ~1% prefill gain.
  Also merged: QKV NVFP4 scale halving (PR #225), O-proj escape fix (PR #226).
  13. Gate-softplus interleaved packing (PR #232): interleaved scale/bias metadata
      for g_proj, halving cache line accesses. +320B in LRM. Bit-exact decode win.
  14. Prefill shared expert gate/up dispatch fusion (PR #231): extends fused bank to
      prefill (L>1), eliminates 1 dispatch per sparse layer × 39 layers. +872B. Bit-exact.

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

## ACTIVE ASSIGNMENTS (Wave 9-10, BASE_SHA=577a9b6)
  MERGED: PR #232 (askeladd gate-softplus interleave) — bit-exact decode win, +320B.
  MERGED: PR #231 (thorfinn prefill shared gate/up fusion) — bit-exact, +872B. NOTE: thorfinn implemented dispatch fusion instead of assigned scale halving.
  CLOSED: PR #236 (askeladd duplicate) — same experiment as PR #231, already merged.
  PR #230 (alphonse): Fuse g_proj into O-proj kernel — ~0.75% decode, bit-exact, M4-testable.
  PR #234 (edward): Prefill MoE down scale halving v2 — ~0.46% prefill, bit-exact, M5-only.
  PR #238 (askeladd): Full-attention params atlas — ~0.05-0.1% decode, bit-exact, M4-testable.
  PR #239 (thorfinn): Shared SwiGLU gate/up scale halving v2 (original assignment) — ~0.11% decode, bit-exact, M4-testable.

## NEXT-WAVE IDEAS (verified, ready to assign)
  Idea 1: Prefill shared expert gate/up fusion — DONE (PR #231, merged).
  Idea 2: Prefill O-proj gate dispatch fusion — REFUTED (documented negative in commit 8841cd9).
  Idea 3: Prefill shared expert scale halving via qmm_nax kHalvedScales — M5-only, ~0.22% score.
  Idea 4: callLastPrefillRow gate fusion — marginal (1 layer only).
  Idea 5: EXPERT_GATHER_GROUPS=256 M5 measurement — 0-byte, M5-only.
  NEW from wave-10 research:
  6. Prefill fused gate+output-projection for L>1 — ~0.06-0.12% score, ~800-1500B.
  7. Prefill fused norm+QKV for L>1 — ~0.12-0.25% score, ~1500-3000B, MEDIUM RISK.
  8. Values transpose folded into prefill QK-norm+RoPE — ~0.025-0.04% score, ~300-500B.
  9. Full-attention params atlas — ASSIGNED to askeladd (PR #238).
  10. Prefill MoE gather-QMM scale halving — ALREADY IMPLEMENTED (PR #220).

## COMPOSITION PLAN
  Current merged: 14 bit-exact changes. Next best: 2.5748.
  In-flight: PR #230 (~0.75%), PR #234 (~0.46%), PR #238 (~0.05%), PR #239 (~0.11%).
  If all succeed: ~0.75% + ~0.46% + ~0.05% + ~0.11% = ~1.37% total.
  Starting from 2.5748 → ~2.612. Would BEAT 2.5888 target.
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
