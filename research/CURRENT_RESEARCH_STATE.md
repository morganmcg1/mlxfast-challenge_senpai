# SENPAI Research State
- 2026-08-07T20:35Z (updated by advisor session)
- Campaign mlxfast-birch-20260805. Advisor HEAD: 472e7825 (pushed to origin).
  LRM: 502,603/524,288 = 21,685 B headroom. Total surface 2,934,676/3,000,000 = 65,324 B headroom.

## M5 SUBMISSION STATUS
  82933c7e: VALIDATING (since 20:23 UTC) — frontier de757c70 (36+ LRM optimizations, vendor at organizer frontier, STAGE2_GATHER fix, NAX gate fix)
  Best birch score: 2.5817 (df9613a). All prior birch submissions failed or rejected.
  Leaderboard #1: fyrsta7 2.6040. Gap to close: +0.86% from best (2.5817 -> 2.6040).
  KEY FIXES IN CURRENT FRONTIER:
    - NAX gate fix (d14b491b): Replaced buggy NAX gate with organizer frontier's simple env var check
    - Vendor files reverted to organizer frontier (658e1439): All Vendor/ files match bca94c5 exactly
    - STAGE2_GATHER fix (bad14a16): Changed default from 1 to 0 in darkbloom_stage2_gather_variant()

## ACTIVE ASSIGNMENTS (Wave 14, BASE_SHA=472e7825)
  PR #328 (thorfinn): Prefill shared expert scale halving — flip lagunaPrefillSharedHalvedEnabled from false to env-gated ON (bit-exact, ~0.3-0.6% prefill, 0-byte)
  PR #329 (edward): Prefill dense gate+up fusion -> PIVOTED to g_proj+QKV fusion (Idea 1, ~1.9% score, 40 dispatches + 80MB bandwidth)
  PR #330 (alphonse): Prefill shared SwiGLU+down fold — fuse compiledSiluProduct + down QMM (bit-exact, ~0.1-0.2% prefill, HIGH risk custom GEMM)
  PR #331 (askeladd): Prefill router GEMV fusion — fuse router GEMV into prefill residual+RMSNorm kernel (bit-exact, ~1.8% score, 39 dispatches + 78MB bandwidth)

## RESEARCH THEMES
  - M5 is bandwidth-bound (~89% GPU util). Only bandwidth reduction or dispatch elimination helps.
  - Prefill path is the primary optimization target (25% of score, ~16 dispatches/layer vs decode's 7).
  - Key unfused prefill dispatches: g_proj (separate from QKV), router GEMV (separate from residual+RMSNorm), shared SiLU (separate from gate/up QMM).
  - QKV fusion is already ON in the frontier (DARKBLOOM_FUSED_QKV default ON).
  - LRM budget is tight: 21,685 B headroom. All new experiments must be compact.
  - M5 SAFETY: NO simd_sum(vec), NO dot(float4), NO *(thread float4*) casts. Scalar Metal only.
  - PR #261 (QKV fusion enable): Result accepted, change already in frontier.

## NEXT-WAVE IDEAS (from RESEARCH_IDEAS_FRESH_20260807_v6.md)
  1. Fuse g_proj into prefill QKV matmul — ASSIGNED to edward (PR #329 pivot, ~1.9% score)
  2. Fuse prefill router GEMV into residual+RMSNorm — ASSIGNED to askeladd (PR #331, ~1.8% score)
  3. Prefill shared expert inline SiLU (custom GEMM) — UNASSIGNED (HIGH risk, defer)
  4. callLastPrefillRow gate+O-proj fusion — UNASSIGNED (marginal, 1 layer only)
  5. Prefill shared scale halving — ASSIGNED to thorfinn (PR #328, ~0.3-0.6% prefill)
  6. Prefill shared SwiGLU+down fold — ASSIGNED to alphonse (PR #330, ~0.1-0.2% prefill)
  7. Prefill asyncEval stride sweep — UNASSIGNED (0-byte, env var knob)
  8. RMSNorm + QKV GEMM cache prefetch — UNASSIGNED (speculative, likely <0.5%)

## COMPOSITION PLAN
  Current frontier: 472e7825 (36+ bit-exact changes, QKV fusion ON).
  In-flight: PR #328 (~0.3-0.6%), PR #329/pivot (~1.9%), PR #330 (~0.1-0.2%), PR #331 (~1.8%).
  If all succeed: ~0.3% + ~1.9% + ~0.1% + ~1.8% = ~4.1% total.
  Starting from 2.5817 -> ~2.69. Would BEAT 2.6040 target.
  Submit independently first, then compose winners for combined submission.

## EXHAUSTED DIRECTIONS
  - INT8 dedup family (complete), dot4 (done/dead), float4 stores (done),
    scale halving (decode done, prefill needs fix), argmax fuse (done),
    RMSNorm fusion (dead, FP reduction order changes flip tokens),
    attention epilogue 1-pass (dead), asyncEval (near-optimal),
    KV cache quant (not bit-exact), ops-800/QHOIST (toxic, reverted),
    dense MLP simd_sum (not bit-exact), input-vector staging (dead),
    decode router top-8 fusion (dead, 1-tile parallelism loss)
