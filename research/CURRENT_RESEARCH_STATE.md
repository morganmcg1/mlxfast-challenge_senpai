# SENPAI Research State — mlxfast-birch-20260805
- 2026-08-08T16:45Z (updated by advisor session)
- Advisor HEAD: cecdc1ef (M5 correctness fix v3 submitted).
- M5 submission 4ac7ad54 VALIDATING since 16:44 UTC.

## M5 CORRECTNESS FIX v3 (CRITICAL PATH)
Root cause: 50+ consecutive M5 failures. Audit found 4 numerical change categories:
1. LM Head fused refinement (mode 1, NEW, default ON) → DISABLED to mode 0 (full int5)
2. Attention BDP=BD+1 padding (NEW) → REVERTED to BD (match organizer)
3. Attention simd_sum: 4 scalar → packed vec4 (NEW) → REVERTED to organizer pattern
4. OPROJ+QKV scale halving (NEW, default ON) → DISABLED (organizer has no halving)

Audit: research/M5_CORRECTNESS_AUDIT_20260808.md
If 4ac7ad54 passes: re-enable optimizations one at a time
If 4ac7ad54 fails: next suspect is MoE halved scales (shared/routed gate/up + down)

## M5 SUBMISSION HISTORY
- 4ac7ad54: VALIDATING — cecdc1ef (fix v3: all 4 fixes)
- f6b87dc: FAILED — 59e39127 (fix v2: fma revert only)
- bcedc8a: FAILED — 39fa0483 (vendor revert + groupSize fix)
- f790e33f: PASSED 2.5213 — bca94c5 (organizer frontier, ONLY successful M5)
- Leaderboard #1: a-github-name 2.6165. Our promoted: 2.5888 (maple, 97a5090).

## ACTIVE STUDENT PRs
- PR #436 (edward): Two-group SDPA — CLOSED. Need new assignment with BDP→BD fix.
- PR #445 (thorfinn): Prefill shared halved scales — WIP, no code yet.
- PR #446 (alphonse): DARKBLOOM_STAGE_* flags — REVIEW READY, safe to merge.
- PR #447 (askeladd): Prefill shared fusion — WIP, no code yet.
- PR #448 (edward): Numerical audit — WIP, redirected (audit done).

## RESEARCH THEMES
- M5 is bandwidth-bound (~89% GPU util). Only bandwidth reduction or dispatch elimination helps.
- The birch campaign NEVER scored on M5 until fix v3 (pending validation).
- LM Head computation changes are extremely sensitive (directly affects token selection).
- Scale halving depends on NVFP4 pairwise-constancy invariant (may not hold on M5).
- Attention kernel BDP padding and simd_sum split are M5 correctness risks.
- NVFP4 scale-fold/carry/defer/nibble-split are safe (exist in organizer with same defaults).
- E4M3 sign domain is safe (same default ON in organizer).
- MoE decode halved scales (shared/routed gate/up + down) are the next suspect if fix v3 fails.

## BUDGET STATUS
- LRM: ~335KB/524KB = ~189KB headroom
- Total surface: ~2.76MB/3.0MB = ~236KB headroom
- Growth limit per submission: 262,144 bytes
