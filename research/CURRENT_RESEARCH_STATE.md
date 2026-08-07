# SENPAI Research State
- 2026-08-07T11:45Z (updated by advisor session)
- Campaign mlxfast-birch-20260805. Advisor HEAD: ffdcf46 (pushed to origin).
  22 composed changes on current frontier (21 previous + PR #258 full-attn atlas).
  LRM: 523,729/524,288 = 559 B headroom. Total surface ~2,988K/3,000,000.

## CRITICAL FIX THIS SESSION: Variant 3 Revert
  Variant 3 (BM128/WM8/WN1, commit 3c30a3b) SILENTLY DISABLED the expert_aligned
  guard at quantized.cpp:1718 (requires bm==64 && wm==4). This fell back to the
  non-expert kernel, losing SWIGLU_REGLOCAL, STAGE2_GATHER, BSEARCH_HOIST,
  EXPERT_GATHER_GROUPS=256, and ALL expert-aligned optimizations on the prefill
  path. Reverted to variant 5 (BM64/WM4/WN1) in commit 1919be9. Also removed
  "3" from LRM allowed values to prevent the trap.
  Found by vendor kernel audit subagent.

## MERGED FRONTIER (22 changes, all bit-exact)
  1-14. Previous frontier (PR #180, #194, #192, #107, #114, #116, #119, #231, #232, etc.)
  15. PR #230: Fuse g_proj+QKV into NVFP4 QKV R1 kernel (decode, ~2.0% decode, bit-exact)
  16. PR #245: INT8 O-proj dot4 vectorization (decode, ~0.8-1.1% on M5, bit-exact)
  17. PR #243: Prefill shared expert scale halving via qmm_nax kHalvedScales (prefill, ~0.22%, M5-only)
  18. PR #234: Prefill MoE down projection scale halving v2 (prefill, ~0.46%, M5-only)
  19. PR #253: Prefill shared expert scale array precomputation (prefill, bit-exact, +140B)
  20. PR #254: Router keys dead output elimination (decode, bit-exact, net-negative ~-300-500B)
  21. PR #258: Full-attention params atlas (decode, bit-exact, +1914B)
  22. REVERTED: Variant 3 (3c30a3b) → variant 5 (1919be9) — critical fix

  M5 FIX: ad58c92 — removed unused constexpr gate_heads from PR #230 kernel
  REVERTED: PR #251 (simd_dot) — M5 build failure (cdefbb9)

## M5 SUBMISSION STATUS
  6f9ca88: VALIDATING (since 11:41 UTC) — frontier 1919be9 (variant 5 restored, 22 changes)
  d565be6: FAILED — frontier 7727d20 (included variant 3 BUG, disabled expert path)
  8b5b01d: FAILED — frontier e0623cf (20 changes)
  70929a5: FAILED — frontier cdefbb9 (revert of #251, code-identical to ad58c92)
  68b66c5: REJECTED, score 2.5520 — frontier ad58c92 (18 changes, LAST SCORED)
  df9613a: REJECTED, score 2.5817 — frontier before #234/#243 (BEST SCORE)
  Leaderboard: fyrsta7 2.6040 (current #1). Our promoted: 97a5090 2.5888 (maple campaign).
  Gap to close: +0.86% from best (2.5817 → 2.6040).

## ACTIVE ASSIGNMENTS (Wave 13, BASE_SHA=ffdcf46)
  PR #261 (thorfinn): Prefill QKV fusion enable — DARKBLOOM_FUSED_QKV OFF→ON
    (0-byte LRM, bit-exact, prefill, 78 dispatches eliminated)
    Rebase feedback sent to ffdcf46
  PR #263 (edward): STAGE2_GATHER variant 2 — zero-occupancy weight staging overlap
    in _nax prefill kernel (0-byte vendor file, bit-exact, prefill-only, M5-only)
  PR #264 (alphonse): eScoreCorrectionBias F32 hoist — eliminate 39 per-prefill
    BF16→FP32 allocations (~+100-200B LRM, bit-exact, prefill)
  PR #267 (askeladd): Merge shared QMV into routed dispatch — extend routed kernel
    to 9th expert slot, eliminate 39 decode dispatches (~-6.5KB LRM, bit-exact, decode)

## CLOSED THIS SESSION
  PR #265 (askeladd): Non-expert stage flags — DEAD ARM (no scored operation uses non-expert path)
  PR #259 (alphonse): Prefill values transpose fold — DEAD (no gain, asyncEval overlap, budget)
  PR #260 (askeladd): _nax BK padding — DEAD (no gain, bank conflicts)

## NEXT-WAVE IDEAS (from NOVEL_OPTIMIZATION_IDEAS.md)
  1. Fuse RMSNorm+router into O-proj (decode 75%, -2KB, M4-testable, medium risk) — UNASSIGNED
  2. ~~Merge shared QMV into routed dispatch~~ — ASSIGNED to askeladd (PR #267)
  3. Revive XMAJOR fold (prefill 25%, 0B, M5-only, med-high risk) — UNASSIGNED
  4. BK=32 tile reduction (prefill 25%, 0B, M5-only, low-med risk) — UNASSIGNED
  5. asyncEval ladder tuning (decode 75%, 0B, quick A/B test) — UNASSIGNED

## CLOSED PRIOR
  PR #248 (alphonse): Scalar RMSNorm fusion — DEAD (FP reduction order mismatch)
  PR #247 (askeladd): qdot shared header dot4 — DEAD (compiler auto-vectorizes)
  PR #251 (thorfinn): Q·K simd_dot — MERGED then REVERTED (M5 build failure)

## RESEARCH THEMES
  - CRITICAL: Variant 3 (BM128/WM8/WN1) silently disabled expert path. ALWAYS verify
    that bm/wm changes satisfy the expert_aligned guard (bm==64 && wm==4).
  - M5 is bandwidth-bound (~89% GPU util). Only bandwidth reduction or dispatch elimination helps.
  - Instruction-count reduction (dot4) shows gains on M5 but NOT M4 (M4 is bandwidth-bound).
  - Unused constexpr in Metal JIT kernel strings may cause M5 build failure even when M4 compiles fine.
  - RMSNorm fusion is a dead end: stock dispatch is optimal, FP reduction order changes flip near-tie tokens.
  - LRM budget is the binding constraint: 559 B headroom. Byte-negative changes are valuable.
  - Prefill path is relatively unoptimized vs decode — prefill dispatch elimination is the main opportunity.
  - ALL expert-path vendor knobs are at optimal values (SWIGLU_REGLOCAL, BSEARCH_HOIST,
    EXPERT_STAGE_WIDEST/WIDELD, EXPERT_GATHER_GROUPS=256, GATHER_RUNSKIP=100%).
  - Non-expert stage flags (WIDEST/WIDELD/RUNBAR/NOVOL) — DEAD ARM, no scored operation uses non-expert path.
  - Need bigger ideas to close 0.86% gap. Novel ideas documented in NOVEL_OPTIMIZATION_IDEAS.md.
  - PR #267 (merge shared QMV) is highest-value: eliminates 39 decode dispatches AND frees ~6.5KB LRM.

## BUDGET STATUS
  LRM: 523,729/524,288 = 559 B headroom
  Total surface: 2,987,879/3,000,000 = 12,121 B headroom
  Growth: 136/262,144 bytes
  Vendor quantized.cpp: ~84K/524,288 = ~440K B headroom
  Vendor fp_quantized_nax.h: ~78K/524,288 = ~446K B headroom

## EXHAUSTED DIRECTIONS
  Scale halving (all paths), dot4 (done/dead), float4 stores (done),
  RMSNorm fusion (dead), attention epilogue 1-pass (dead), simd_dot (dead),
  KV cache quant (blocked), decode dispatch elimination (fully fused),
  prefill values transpose fold (dead), BK padding (dead), variant 3/4 (dead),
  dense MLP quant (blocked), INT8 dedup (complete), argmax fuse (done),
  prefill O-proj gate fusion via compile() (refuted), asyncEval (near-optimal),
  input-vector staging (dead, barrier overhead), FP reduction order changes (toxic).
