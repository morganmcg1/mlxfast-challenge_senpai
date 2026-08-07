# SENPAI Research State
- 2026-08-07T15:10Z (updated by advisor session)
- Campaign mlxfast-birch-20260805. Advisor HEAD: 87b2dd2 (pushed to origin).
  30+ composed changes on current frontier (87aff2f vendor files + LRM optimizations).
  LRM: 505,776/524,288 = 18,512 B headroom (PR #294 pending rebase, will free ~9.3KB more).
  Total surface: 2,969,335/3,000,000 = 30,665 B headroom.

## CRITICAL: _nax VENDOR REVERT (2026-08-07)
  Reverted fp_quantized_nax.cpp and quantized.cpp to pre-PR#243 state (577a9b6).
  Reason: PR #243 (kHalvedScales), PR #263 (STAGE2_GATHER v2), PR #261 (QKV fusion)
  caused 8 consecutive M5 build failures. df9613a (2.5817) was last successful build
  with these pre-PR#243 vendor files.
  Also disabled DARKBLOOM_FUSED_QKV (PR #261 flag set to OFF).
  All 29 LRM-only optimizations retained. useHalved=false crash fix retained.
  M5 submission d417eaa (6739b6a) VALIDATING 105+ min — build likely succeeded.

## M5 SUBMISSION STATUS
  400ba6c: FAILED — vendor files from 68b66c5 had darkbloom_expert_bk128 that LRM doesn't use
  9753441c: VALIDATING — 87aff2f vendor files (organizer frontier) + 30 LRM optimizations
  Root cause: 68b66c5 vendor files have darkbloom_expert_bk128/darkbloom_stage_wide_scale_ok
  functions that the current LRM doesn't call. The 87aff2f vendor files (organizer frontier
  revert of PR #243/#263) are the M5-safe base.
  Best scored: df9613a at 2.5817. Leaderboard #1: 2.6040. Gap: +0.86%.

## ACTIVE ASSIGNMENTS (Wave 15, BASE_SHA=87b2dd2)
  PR #297 (alphonse): Down+residual outputs_per_simd 8→16 — halve grid from 73728 to 36864 TGs (bit-exact, ~50B, decode)
  PR #285 (edward): Routed MoE halved scales escape fix — v2 revision, rebase nudge sent
  PR #292 (askeladd): Prefill gate-product+softplus multi-token extension — rebase nudge sent
  PR #294 (thorfinn): Dead code removal — APPROVED, revision v2 requested (rebase on 87b2dd2, conflict with PR #291)

## CLOSED
  PR #296 (alphonse): RMSNorm→LM head fusion — CLOSED (bandwidth-negative: 25MB extra norm-weight reads across 6272 TGs)

## MERGED WAVE 14
  PR #291 (alphonse): Precompute eScoreCorrectionBias FP32 — MERGED (bit-exact, +0.676% decode, +222B)

## NEXT-WAVE IDEAS (from FRESH_DECODE_IDEAS_20260807.md + research agent)
  1. Fuse final RMSNorm into LM head coarse — CLOSED (bandwidth-negative, 25MB extra reads)
  2. Down+residual outputs_per_simd 8→16 — ASSIGNED to alphonse (PR #297)
  3. NVFP4 OProj results_per_simd 8→16 — UNASSIGNED (~50B, 40 layers)
  4. Gate/up R1 9-simdgroup input sharing — LIKELY DEAD (input-vector staging already failed)
  5. Dense down rows_per_thread 4→8 — LOW IMPACT (1 layer only)
  6. Device-atomic two-phase norm+QKV fusion — UNASSIGNED (saves 40 dispatch boundaries/step, complex)
  7. Device-atomic router top-8 fusion — UNASSIGNED (saves 39 dispatch boundaries/step, complex)
  8. Decode path is extremely well-optimized: 8 dispatches per sparse layer, nearly fully fused
  PR #292 (askeladd): Extend gate-product+softplus kernel to multi-token prefill — 40 dispatches, ~200-400B
  PR #294 (thorfinn): Dead code removal — free ~12KB LRM budget, 4 default-OFF flags, net-negative

## CLOSED (Wave 13)
  PR #290 (thorfinn): QKV fusion re-enable — DEAD (38% decode regression from 312MB extra weight)

## M5 CRASH FIX (CRITICAL — 2026-08-07T13:20Z)
  Root cause found by _nax audit agent: PR #220 and PR #234 passed non-nil `biases`
  to `MLX.gatherQuantizedMM` with `mode: .nvfp4`. Stock MLX `ops.cpp:4508-4513`
  (NON-EDITABLE) throws exception for non-nil biases with nvfp4 mode, crashing the
  process on M5 where `lagunaExpertAlignedGatherEnabled=true` → `useHalved=true` →
  biases non-nil. On M4, `lagunaExpertAlignedGatherEnabled=false` → no crash.
  Fix: set `useHalved=false` and `useHalvedDown=false` (disables ~0.5% prefill gain).
  M5 submission efb6316 VALIDATING (frontier 4bea532).
  PR #285 (edward): Proper fix — embed escape in scales tensor, pass biases:nil.

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
  25. PR #267: Merge shared gate/up QMV into routed dispatch (decode, byte-negative -2,094B, eliminate 39 dispatches)
  BK=32 (PR #271) REVERTED → not on frontier (escape handling bug, commit 1bc2a53)

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
  90d0841: VALIDATING — frontier e73f710 (26 changes, includes PR #267 + PR #278)
  29fb82a: FAILED — frontier 1bc2a53 (24 changes, BK=32 reverted) — BUILD FAILURE
  f5dac24: FAILED — frontier 3b24586 (25 changes, BK=32 BUG)
  b72eef8: FAILED — frontier dd9ab65 (24 changes, cause TBD)
  6f9ca88: FAILED — frontier 1919be9 (variant 5, 22 changes, cause TBD)
  68b66c5: REJECTED, score 2.5520 — frontier ad58c92 (variant 3, expert DISABLED)
  df9613a: REJECTED, score 2.5817 — BEST SCORE
  Leaderboard: fyrsta7 2.6040 (current #1). Gap: +0.86% from best (2.5817 → 2.6040).
  CRITICAL: 29fb82a FAILED even after BK=32 revert. Root cause is in _nax changes
  (PR #234/#243/#263) that only manifest with expert path enabled (variant 5).
  If 90d0841 also fails: revert PR #234, #243, #263 and resubmit.

## MERGED THIS SESSION (Wave 15-17, +5 changes)
  PR #267 (askeladd): Merge shared gate/up QMV into routed dispatch — bit-exact, byte-negative -2,094B,
    eliminates 39 decode dispatches, M4 timing +0.50% (noise, M5 may be better with 40 cores)
  PR #278 (alphonse): Compress LRM doc comments — comment-only, bit-exact, byte-negative -16,572B,
    frees LRM headroom from 604B to 17,252B. Enables future kernel work.
  PR #280 (thorfinn): Double down kernel outputs_per_simd 4→8 — bit-exact, 0-byte, M4 +0.4% decode
  PR #283 (thorfinn): Double NVFP4 O-proj results_per_simdgroup 4→8 — bit-exact, 0-byte, M4 +0.74% (ambiguous, M5 needed)
  M5 FIX: 4bea532 — disable halved scales path (non-nil biases crash on M5 with nvfp4 mode)

## CLOSED THIS SESSION (Wave 15-16)
  PR #276 (edward): RMSNorm→LM head fusion — DEAD (RMSNorm replicated across 6272 TGs costs >1 dispatch saved; +0.1% to +1.8% slower)
  PR #277 (thorfinn): 4-way scale constancy — DEAD (invariant holds only 20-37%, need 95%. 2-way holds 100%)

## ACTIVE ASSIGNMENTS (Wave 16-17, BASE_SHA=e4534e4)
  PR #281 (alphonse): Fuse router GEMV + top-8 tournament into single kernel — eliminate 39 decode dispatches (bit-exact, ~0.2-0.5% decode)
  PR #285 (edward): Fix routed MoE halved scales — embed escape in scales tensor, pass biases:nil (recover ~0.5% prefill, M5-only, bit-exact)
  PR #286 (thorfinn): Double norm+affine QKV kernel results_per_simdgroup 4→8 (bit-exact, 0-byte, decode)
  PR #287 (askeladd): Double INT8 affine O-proj kernel results_per_simdgroup 4→8 (bit-exact, 0-byte, decode)

## DECODE DISPATCH AUDIT (Wave 17, 2026-08-07T13:29Z)
  Full audit by explore agent. ~325 dispatches/decode step (7 for layer 0, 8×39=312 for MoE, 6 global).
  Decode is NEARLY FULLY FUSED under default NVFP4 config. 8 dispatches per MoE layer:
  A-1: Input RMSNorm (stock, separate — norm+NVFP4-QKV fusion tried, +2.7% slower, DEAD)
  A-2: NVFP4 QKV + g_proj gate (fused, PR #230) — LRM JIT, not _nax
  A-3: Fused QK-norm + YaRN RoPE + cache + SDPA — LRM JIT
  A-4: Gated NVFP4 O-proj (PR #230 gate fuse, PR #283 tiling doubled) — LRM JIT
  M-5: Residual + RMSNorm + router GEMV (fused) — LRM JIT
  M-6: Router top-8 selection — LRM JIT (PR #281 IN-FLIGHT to fuse into M-5)
  M-7: Routed SwiGLU QMV + shared merged 9-slot (PR #267) — LRM JIT
  M-8: Routed+shared down + residual (PR #280 tiling doubled) — LRM JIT

  REMAINING OPPORTUNITIES:
  - PR #281: Fuse router top-8 into M-5 (IN-FLIGHT, -39 dispatches)
  - PR #286: QKV tiling 4→8 (IN-FLIGHT)
  - PR #287: INT8 O-proj tiling 4→8 (IN-FLIGHT)
  - PR #285: Halved scales fix (IN-FLIGHT, prefill bandwidth)
  DEAD: RMSNorm→NVFP4-QKV fusion (+2.7% slower), RMSNorm→LM head fusion (PR #276, 6272 TGs)
  UNTRIED BUT HIGH RISK: QMV→down fusion (different parallelism), mega-kernel attention fusion

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
  - LRM budget freed by PR #267: now 14,260B total headroom (was 559B). Enables new kernel work.
  - Prefill dispatch elimination is a DEAD ARM — asyncEval overlap hides dispatch savings on M5.
  - 4-way scale constancy is DEAD — NVFP4 only has 2-way pairwise constancy (100% verified).
  - Need bigger ideas to close 0.86% gap. Novel ideas documented in NOVEL_OPTIMIZATION_IDEAS.md.

## BUDGET STATUS
  LRM: 521,590/524,288 = 2,698 B headroom (freed 2,139B by PR #267)
  Total surface: 2,985,740/3,000,000 = 14,260 B headroom
  Growth limit per submission: 262,144 bytes
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
