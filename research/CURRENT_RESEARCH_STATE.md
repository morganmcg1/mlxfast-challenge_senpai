# SENPAI Research State
- 2026-08-07T12:33Z (updated by advisor session)
- Campaign mlxfast-birch-20260805. Advisor HEAD: 3b24586 (pushed to origin).
  25 composed changes on current frontier (24 previous + PR #271 BK=32).
  LRM: 523,729/524,288 = 559 B headroom. Total surface ~2,988K/3,000,000.

## CRITICAL FIX THIS SESSION: Variant 3 Revert
  Variant 3 (BM128/WM8/WN1, commit 3c30a3b) SILENTLY DISABLED the expert_aligned
  guard at quantized.cpp:1718 (requires bm==64 && wm==4). This fell back to the
  non-expert kernel, losing SWIGLU_REGLOCAL, STAGE2_GATHER, BSEARCH_HOIST,
  EXPERT_GATHER_GROUPS=256, and ALL expert-aligned optimizations on the prefill
  path. Reverted to variant 5 (BM64/WM4/WN1) in commit 1919be9. Also removed
  "3" from LRM allowed values to prevent the trap.
  Found by vendor kernel audit subagent.

## MERGED FRONTIER (25 changes, all bit-exact)
  1-14. Previous frontier (PR #180, #194, #192, #107, #114, #116, #119, #231, #232, etc.)
  15. PR #230: Fuse g_proj+QKV into NVFP4 QKV R1 kernel (decode, ~2.0% decode, bit-exact)
  16. PR #245: INT8 O-proj dot4 vectorization (decode, ~0.8-1.1% on M5, bit-exact)
  17. PR #243: Prefill shared expert scale halving via qmm_nax kHalvedScales (prefill, ~0.22%, M5-only)
  18. PR #234: Prefill MoE down projection scale halving v2 (prefill, ~0.46%, M5-only)
  19. PR #253: Prefill shared expert scale array precomputation (prefill, bit-exact, +140B)
  20. PR #254: Router keys dead output elimination (decode, bit-exact, net-negative ~-300-500B)
  21. PR #258: Full-attention params atlas (decode, bit-exact, +1914B)
  22. REVERTED: Variant 3 (3c30a3b) → variant 5 (1919be9) — critical fix
  23. PR #261: Prefill QKV bank fusion (prefill, 0-byte, eliminate 78 dispatches)
  24. PR #263: STAGE2_GATHER variant 2 (prefill, 0-byte, M5-only)
  25. PR #271: BK=32 tile reduction (prefill, 0-byte, M5-only, halve Ws threadgroup memory)

  M5 FIX: ad58c92 — removed unused constexpr gate_heads from PR #230 kernel
  REVERTED: PR #251 (simd_dot) — M5 build failure (cdefbb9)

## CRITICAL BUG FIX: BK=32 Escape Handling (2026-08-07)
  BK=32 (PR #271) broke escape handling in gather_qmm_rhs_nax. When BK=32,
  n_steps_per_read=1 (vs 2 for BK=64), making the i==1 escape branch at
  fp_quantized_nax.h:275 dead code. The escape bytes that correct the k=0
  scale pair (NVFP4 pairwise constancy) were never applied → wrong
  dequantization → token mismatches on M5 with expert path enabled (variant 5).
  REVERTED in commit 1bc2a53 (bk=32 → bk=64). f5dac24 failed because of this bug.
  KEY LESSON: _nax kernel tile parameter changes (BK) interact with escape handling.
  M4 cannot validate _nax changes (GPU gen 16 < 17). Variant 3 masked this bug
  by disabling the expert path. All _nax changes validated only under variant 3 are suspect.

## M5 SUBMISSION STATUS
  29fb82a: VALIDATING — frontier 1bc2a53 (24 changes, BK=32 reverted)
  f5dac24: FAILED — frontier 3b24586 (25 changes, BK=32 BUG)
  b72eef8: FAILED — frontier dd9ab65 (24 changes, cause TBD)
  6f9ca88: FAILED — frontier 1919be9 (variant 5, 22 changes, cause TBD)
  68b66c5: REJECTED, score 2.5520 — frontier ad58c92 (variant 3, expert DISABLED)
  df9613a: REJECTED, score 2.5817 — BEST SCORE
  Leaderboard: fyrsta7 2.6040 (current #1). Gap: +0.86% from best (2.5817 → 2.6040).
  NOTE: Other solvers (a-github-name, yudduy) scored on M5 during our failures.
  This is NOT global infrastructure. BK=32 bug explains f5dac24. Earlier failures
  (6f9ca88, b72eef8) may have other causes (unused constexpr, PR #234/#243 interaction).

## MERGED THIS SESSION (Wave 13, +2 changes)
  PR #263 (edward): STAGE2_GATHER variant 2 — 0-byte, bit-exact, prefill-only, M5-only effect
  PR #261 (thorfinn): QKV bank fusion — 0-byte, bit-exact, prefill-only, 78 dispatches eliminated

## CLOSED THIS SESSION (Wave 13)
  PR #265 (askeladd): Non-expert stage flags — DEAD ARM (no scored operation uses non-expert path)
  PR #264 (alphonse): eScoreCorrectionBias F32 hoist — DEAD (bias already F32, .asType is no-op)

## ACTIVE ASSIGNMENTS (Wave 14, BASE_SHA=dd9ab65)
  PR #267 (askeladd): Merge shared QMV into routed dispatch — ~-6.5KB LRM, eliminate 39 decode dispatches (DECODE)
  PR #271 (alphonse): BK=32 tile reduction — 0-byte, 1-line, prefill-only, M5-only effect (PREFILL)
  PR #272 (edward): Extend RMSNorm+router to multi-token prefill — eliminate 39 router matmul dispatches (PREFILL)

## NEXT-WAVE IDEAS (from NOVEL_OPTIMIZATION_IDEAS.md)
  1. Fuse RMSNorm+router into O-proj — DEAD (incompatible parallelism structures: 16384 TGs vs 1 TG)
  2. ~~Merge shared QMV into routed dispatch~~ — ASSIGNED to askeladd (PR #267)
  3. Revive XMAJOR fold — NOT ASSIGNED (too complex: requires re-implementing removed kernel arms, M5-only)
  4. ~~BK=32 tile reduction~~ — ASSIGNED to alphonse (PR #271)
  5. asyncEval ladder tuning — EXHAUSTED (already swept in notes/52, 66 runs)
  NEW: Extend RMSNorm+router to multi-token prefill — ASSIGNED to edward (PR #272)

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
