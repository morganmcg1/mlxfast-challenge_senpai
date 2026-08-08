# SENPAI Research State — mlxfast-birch-20260805
- 2026-08-08T14:00Z (updated by advisor session after runner upgrade)
- Advisor HEAD: 123c6583 (infrastructure updates merged, pushed to origin).
- Research frontier: fc66737f (PR #424 composition merged).
- LRM: 311KB, 17 JIT compiles. Total surface within 3MB cap.
- Last M5 success: f790e33f (score 2.5213). 50+ consecutive M5 build failures.
- Leaderboard #1: a-github-name 2.6165 (cc6ddc1, promoted 8/8 9:09 AM).
- Our promoted: 2.5888 (97a5090, maple campaign). Gap: ~1.06%.

## CRITICAL: M5 BUILD TIMEOUT — 50+ CONSECUTIVE FAILURES
  Root cause: LRM nuclear fallback replaced 31 custom kernels with standard MLX ops.
  Standard MLX ops compile from 5-10x larger headers than custom kernels.
  3 JIT compile deltas (f790e33f to current):
  1. rope.metal (229 lines) - FIXED by PR #407 (prefill sliding QK-norm+RoPE fusion, MERGED)
  2. rms_norm.metal (391 lines) - FIXED by PR #407 (prefill sliding QK-norm fusion, MERGED)
  3. steel_attention (1,160 lines) - NOT YET FIXED. PR #420 v1 had dead code.
     PR #435 (thorfinn): Wire decode full-attn custom kernel into dispatch chain.
     Must restore lagunaFullFusedAttentionKernel + lagunaFullFusedAttention + 2 dispatch branches from f790e33f.

  Partial fix (PR #424, 2 of 3 JIT deltas): ALSO FAILED. steel_attention alone causes timeout.
  ALL submissions since f790e33f: FAILED (build timeout at ~900s).

## ACTIVE ASSIGNMENTS (Wave 14, 2026-08-08T14:00)
  PR #435 (thorfinn): CRITICAL - Wire decode full-attn custom kernel into dispatch chain.
  PR #436 (edward): Two-group SDPA schedule - halve K/V traffic (AOT sdpa_vector.h).
  PR #437 (alphonse): Router Top-8 (ordinal,index) packing - eliminate redundant expert extraction.
  PR #438 (askeladd): Compose PR #435 + audit remaining JIT compiles.

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
