# SENPAI Research State — mlxfast-birch-20260805
- 2026-08-08T17:46Z (updated by advisor session)
- Advisor HEAD: a333e967 (organizer frontier + STAGE flags, pushed to origin)
- M5 fix v4 (4121270b) VALIDATING — fix v5b queued (capacity occupied)

## M5 CORRECTNESS ROOT CAUSE (AUDIT V4)
The birch campaign's 50+ M5 failures were caused by systematic rewrite of decode-path
kernels with different FP arithmetic. The audit (research/M5_CORRECTNESS_AUDIT_V4_20260808.md)
found 5 critical FP-affecting differences:

1. QKV: Removed INT8 affine fused kernel (lagunaNormAffineQKV) to stock quantizedMM (different FP)
2. OProj: Removed INT8 affine gated fused kernel to 3 separate dispatches (different BF16 rounding)
3. Router: Removed precomputed router_keys to different expert selection pipeline
4. MoE: Rewrote kernels with halved scales (group_size=32 vs 16) to different FP dequantization
5. g_proj: Changed from separate to fused approach to different FP accumulation

## FIX STRATEGY
v5b: Restored ALL 3 editable files from organizer frontier (bca94c5) + enabled
DARKBLOOM_STAGE_* flags (prefill-only, bit-exact). This is exactly the organizer
frontier code that scored 2.5213, plus one FP-safe prefill optimization.

## M5 SUBMISSION STATUS
- 4121270b: VALIDATING (fix v4, MoE halved scales disabled only) — likely to fail
- 3ff39923: REJECTED (fix v5, pure organizer frontier — duplicate of f790e33f)
- Fix v5b: QUEUED (organizer frontier + STAGE flags) — waiting for capacity
- f790e33f: PASSED 2.5213 (organizer frontier, ONLY successful M5)
- Leaderboard #1: a-github-name 2.6165. Our promoted: 2.5888 (maple, 97a5090).

## ACTIVE STUDENT PRs
- PR #446 (alphonse): DARKBLOOM_STAGE_* flags — revision requested (rebase to new base).
  NOTE: The advisor has already applied this change directly (commit a333e967).
- PR #445 (thorfinn): Prefill shared halved scales — CLOSED (re-introduces halved scales)
- PR #447 (askeladd): Prefill shared fusion — CLOSED (OOM dead end)
- PR #448 (edward): Numerical audit — MERGED (identified MoE halved scales as suspect)
- PR #436 (edward): Two-group SDPA — CLOSED (needs new assignment)

## NEXT STEPS
1. Wait for fix v4 (4121270b) to resolve
2. Submit fix v5b (organizer frontier + STAGE flags) when capacity frees
3. If v5b passes M5: we have a working baseline. Re-apply optimizations one at a time.
4. If v5b fails: STAGE flags may not be safe. Revert to pure organizer frontier.
5. Reassign all 4 students to new experiments based on FP-safe optimization directions.

## FP-SAFE OPTIMIZATION DIRECTIONS (for re-application after M5 baseline confirmed)
These are changes that do NOT alter FP arithmetic in logits-contributing kernels:
- Dispatch elimination (fewer dispatches, same kernel source)
- Precompute/preallocation (same kernels, earlier preparation)
- Warmup sequence changes (same kernels, different warmup order)
- Prefill-only kernel staging (store/load width, dead barriers)
- Attention kernel exchange-plane widening (if same FP reduction order)
- Kernel source string changes that preserve exact FP reduction tree

## BUDGET STATUS
- Total surface: 2,996,061/3,000,000 bytes (3,939 bytes headroom)
- Growth limit per submission: 262,144 bytes
- 12 bytes of growth from STAGE flags (4 flag default changes)
