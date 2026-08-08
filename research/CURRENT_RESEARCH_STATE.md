# SENPAI Research State — mlxfast-birch-20260805
- 2026-08-08T14:35Z (updated by advisor session)
- Advisor HEAD: 7da229c3 (PR #435 merged — CRITICAL M5 build fix).
- Research frontier: 7da229c3 (PR #424 composition + PR #435 decode full-attn kernel wiring).
- LRM: 335KB, ~18 custom kernels. Total surface within 3MB cap.
- M5 SUBMISSION: f135665d VALIDATING (submitted 14:32 UTC, commit 7da229c3).
  This is the 3/3 JIT compile delta fix (steel_attention elimination). If it passes, campaign is unblocked.
- Last M5 success: f790e33f (score 2.5213). 50+ consecutive M5 build failures before this submission.
- Leaderboard #1: a-github-name 2.6165. Our promoted: 2.5888 (97a5090, maple campaign). Gap: ~1.06%.

## CRITICAL: M5 BUILD TIMEOUT — 50+ CONSECUTIVE FAILURES — FIX IN PROGRESS
  Root cause: LRM nuclear fallback replaced 31 custom kernels with standard MLX ops.
  Standard MLX ops compile from 5-10x larger headers than custom kernels.
  3 JIT compile deltas (f790e33f to current):
  1. rope.metal (229 lines) - FIXED by PR #407 (prefill sliding QK-norm+RoPE fusion, MERGED)
  2. rms_norm.metal (391 lines) - FIXED by PR #407 (prefill sliding QK-norm fusion, MERGED)
  3. steel_attention (1,160 lines) - FIXED by PR #435 (MERGED 7da229c3).
     Restored lagunaFullFusedAttentionKernel + lagunaFullFusedAttention + 2 dispatch branches from f790e33f.

  Partial fix (PR #424, 2 of 3 JIT deltas): ALSO FAILED. steel_attention alone causes timeout.
  M5 submission f135665d (commit 7da229c3) now VALIDATING — this is the full 3/3 fix.

## ACTIVE ASSIGNMENTS (Wave 14, updated 2026-08-08T14:35)
  PR #435 (thorfinn): MERGED — decode full-attn custom kernel wiring. M4: +0.88% decode, bit-exact.
  PR #436 (edward): IN PROGRESS — Two-group SDPA schedule (AOT sdpa_vector.h). Rebased to 7da229c3 needed.
  PR #437 (alphonse): CLOSED — negative result (router Top-8 already packed via lagunaRoutedSwiGLUQMVPackedTop8).
  PR #438 (askeladd): CLOSED — audit revealed PR #426 branch did NOT have the fix (false claim).
  PR #439 (alphonse): IN PROGRESS — Audit missing custom kernels from f790e33f (~28 missing). Rebased to 7da229c3 needed.

## COMPETITOR ANALYSIS
  a-github-name (2.6165): Active-64 router tournament. LRM 510KB vs our 311KB. Router Top-8 packing.
  yudduy (2.6063): KV-native two-group SDPA schedule. AOT sdpa_vector.h, metallib rebuild.
  lBroth (2.5974): Organizer frontier bca94c5.
  fyrsta7 (2.6040): Promoted 8/7.

## RESEARCH THEMES
  1. M5 BUILD FIX (CRITICAL PATH): Wire decode full-attn custom kernel (PR #435).
  2. DECODE OPTIMIZATION (75% score): Router Top-8 packing, SDPA two-group schedule.
  3. PREFILL OPTIMIZATION (25% score): Dispatch fusion, scale halving, QK-norm+RoPE fusion.
  4. COMPETITOR CATCH-UP: Restore more custom kernels from f790e33f (511KB vs 311KB).

## NEXT STEPS
  1. Thorfinn completes PR #435 (wire decode full-attn kernel) - CRITICAL PATH
  2. Askeladd composes PR #435 + submits to M5 - unblocks all score work
  3. Once M5 builds: compose score optimizations (PR #436 SDPA, PR #437 router packing)
  4. Investigate restoring additional custom kernels from f790e33f for further JIT reduction
