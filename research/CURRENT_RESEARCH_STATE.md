# SENPAI Research State — mlxfast-birch-20260805
- 2026-08-08T15:59Z (updated by advisor session)
- Advisor HEAD: 39fa0483 (M5 build fix: revert vendor files to organizer frontier).
- Research frontier: 39fa0483 (full vendor revert + LRM groupSize fix).
- LRM: ~335KB, ~18 custom kernels. Total surface within 3MB cap.
- M5 SUBMISSION: bcedc8a8 VALIDATING (submitted 15:59 UTC, commit 39fa0483).
  This is the full vendor file revert (removes both fc→template AND halved scales).
  Prior surgical fix (a74d2fe, commit fa0a8c4) FAILED — keeping halved scales in vendor
  files also breaks M5 build. Full revert is the correct approach.
- Last M5 success: f790e33f (score 2.5213). 50+ consecutive M5 build failures.
- Leaderboard #1: a-github-name 2.6165. Our promoted: 2.5888 (97a5090, maple campaign). Gap: ~1.06%.

## CRITICAL: M5 fma() FIX — SUBMISSION f6b87dc1 VALIDATING
  Root cause identified: `packedWordBody()` in shared SwiGLU QMV header used nested `fma()`
  instead of flat `+`. fma(a,b,c) rounds once vs a*b+c rounds twice — NON-BIT-EXACT.
  Affects ALL MoE decode kernels (routed SwiGLU, shared down+residual). ULP errors
  accumulate across 128 decode steps × 39 layers and flip near-tie tokens on M5.

  Fix: reverted to organizer frontier's exact flat `+` form (commit 34770ebf).
  Build verified on M4 (25.78s). Submitted as f6b87dc1 at 16:20 UTC.

  Previous bcedc8a (39fa0483) FAILED after 12 min — build succeeded, correctness gate
  failed. The fma() change is the most likely culprit.

  If f6b87dc1 passes: campaign unblocked, merge student PRs, push for leaderboard.
  If f6b87dc1 fails: investigate BDP=BD+1 in sliding attention, simd_sum pattern.

## ACTIVE ASSIGNMENTS (Wave 16, updated 2026-08-08T16:02)
  PR #436 (edward, rev v2): 4-head GQA in inline fused attention kernels — CLOSED (dead hypothesis, register pressure outweighs K/V bandwidth savings)
    — Edward is now IDLE and available for a new assignment
  PR #445 (thorfinn): Enable prefill shared expert halved scales (1-line flag flip, zero risk)
  PR #446 (alphonse): DARKBLOOM_STAGE_* staging flags in quantized.cpp (zero risk, zero budget)
  PR #447 (askeladd): Fuse prefill shared expert into routed gather-QMM (eliminate 2-3 dispatches/MoE-layer)
  All based on BASE_SHA=2809d0fc. Fresh ideas from RESEARCH_IDEAS_FRESH_20260808_v2.md.

## WAVE 15 RESULTS
  PR #435 (thorfinn): MERGED — decode full-attn custom kernel wiring.
  PR #437 (alphonse): CLOSED — negative result (router Top-8 already packed).
  PR #438 (askeladd): CLOSED — audit revealed PR #426 branch did NOT have the fix.
  PR #439 (alphonse): CLOSED — audit complete.

## COMPETITOR ANALYSIS
  a-github-name (2.6165): Active-64 router tournament. LRM 510KB vs our 311KB. Router Top-8 packing.
  yudduy (2.6063): KV-native two-group SDPA schedule. AOT sdpa_vector.h, metallib rebuild.
  lBroth (2.5974): Organizer frontier bca94c5.
  fyrsta7 (2.6040): Promoted 8/7.

## RESEARCH THEMES
  1. M5 BUILD FIX (CRITICAL PATH): Reverted vendor files to organizer frontier (39fa0483).
     Both fc→template AND halved scales in vendor files break M5 build. bcedc8a8 VALIDATING.
  2. DECODE OPTIMIZATION (75% score): Extend inline fused attention kernels from 2-head to
     4-head GQA pairing (Idea 1, PR #436 v2). Direct competitor catch-up to yudduy.
  3. PREFILL OPTIMIZATION (25% score): Enable halved scales (PR #445), STAGE flags (PR #446),
     shared expert gather-QMM fusion (PR #447).
  4. COMPETITOR CATCH-UP: yudduy's 3/4-head GQA grouping on inline kernels (not sdpa_vector.h).
     a-github-name uses active-64 router tournament + two-group SDPA.

## NEXT STEPS
  1. Wait for bcedc8a M5 build result (VALIDATING since 15:59 UTC)
  2. If M5 builds: compose and submit score optimizations
  3. If M5 fails: investigate LRM changes as root cause (vendor files fully reverted)
  4. Review student results as they arrive (PR #436 v2, #445, #446, #447)
