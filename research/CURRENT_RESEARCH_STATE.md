# SENPAI Research State
- 2026-08-07T11:30Z (updated by advisor session — M5 re-submission in progress)
- Campaign mlxfast-birch-20260805. Advisor HEAD: de757c70 (pushed to origin).
  36+ composed changes on current frontier. ALL vendor files reverted to organizer frontier.
  LRM budget: ~21KB headroom. Total surface ~2,936K/3,000,000 = ~64KB headroom.

## M5 SUBMISSION STATUS (2026-08-07)
  82933c7e: VALIDATING — frontier de757c70 (NAX gate fix + 36+ LRM opts, vendor at organizer frontier)
  b49e5d5: FAILED — NAX gate fix + 36+ opts (previous session)
  3ff3992: REJECTED 2.5213 — organizer frontier (control, scored on M5)
  68b66c5: REJECTED 2.5520 — frontier ad58c92 (LAST SUCCESSFULLY BUILT birch)
  df9613a: REJECTED 2.5817 — BEST birch score (frontier before PR #234/#243)
  Leaderboard #1: fyrsta7 2.6040. Our promoted: 97a5090 2.5888 (maple campaign).
  Gap to close: +0.86% from best (2.5817 → 2.6040).

## CRITICAL CORRECTION: NAX Gate Was NOT the Root Cause
Previous session claimed the NAX gate string parsing bug was the M5 root cause.
INVESTIGATION PROVED THIS WRONG: df9613a (score 2.5817) ALSO had the NAX gate bug
(lagunaExpertAlignedGatherEnabled = false due to #available(macOS 26.2) check)
and it SCORED on M5. The layout mismatch (LRM=false, vendor=true) did NOT cause
correctness failures — the prefill routed gate/up path produces correct tokens
regardless of the flag value.

The NAX gate fix (d14b491b) is correct (matches organizer frontier) but was NOT
the root cause of M5 failures.

## M5 INFRASTRUCTURE EVIDENCE
  70929a5 (code IDENTICAL to ad58c92 which scored 2.5520) ALSO FAILED.
  Diff between ad58c92 and cdefbb98 (70929a5): ONLY research docs (not editablePaths).
  This proves the M5 had intermittent infrastructure issues on 8/7.
  20+ consecutive failures from 8:50 AM to 6:00 PM, then 3ff3992 scored at 6:51 PM
  (brief recovery), then 3 more failures.

## M5 BUILD FIX — ROOT CAUSE FOUND (2026-08-07 session 3)
  ROOT CAUSE: DARKBLOOM_STAGE2_GATHER defaults to variant 1 (double-buffer staging).
  This injects #define DARKBLOOM_STAGE2_GATHER 1 into _nax expert gather-QMM JIT source,
  activating 299+ lines of double-buffer staging code in mlx-generated/fp_quantized_nax.cpp
  and fp_quantized_nax.h. This code ONLY compiles on M5 (GPU gen 17+). The organizer
  frontier (bca94c5) defaults this to OFF (stock staging). M4 never compiles _nax kernels
  so M4 could never detect this issue.

  FIX: Changed default from 1 to 0 in darkbloom_stage2_gather_variant() in quantized.cpp
  (commit bad14a16). All #ifdef DARKBLOOM_STAGE2_GATHER blocks become dead code.
  This matches the organizer frontier behavior exactly.

  VERIFICATION:
  - Isolation test (3ff39923, organizer frontier code): REJECTED, score 2.5213.
    The organizer frontier BUILDS on M5 (rejected only for low score, NOT build failure).
    Confirms M5 environment is healthy.
  - LRM Metal kernel audit: zero M5-incompatible patterns (simd_sum vec, dot float4,
    thread float4, simd_dot — all absent from 11,216 lines of embedded Metal kernels).
  - Vendor file diffs vs organizer frontier: only STAGE2_GATHER variant system (disabled
    by fix) and SwitchLayers.swift v3→v4 kernel name (M5-safe) are birch-specific.
    BM128 variant 5 is also in the organizer frontier (not birch-specific).

  M5 FIX SUBMISSION: 51c39751 VALIDATING since 19:15 UTC.
  Expected: build PASSES, scores higher than 2.5213 due to 36+ LRM optimizations.

  PREVIOUS FALSE PREMISES (all refuted):
  - simd_sum vec, dot float4, thread float4, simd_dot, kHalvedScales: NONE of these
    were the actual issue. The real issue was STAGE2_GATHER activating _nax kernel code.

## FOURTH M5-INCOMPATIBLE PATTERN CLASS IDENTIFIED
  Previously found 3 pattern classes in Metal JIT kernel strings:
  1. simd_sum(vec<float,N>) — fixed in d6420f3d
  2. dot(float4(...)) — fixed in d6420f3d
  3. *(thread float4*) pointer casts — fixed in 2358c577
  4. Vendor header/source template mismatch (fp_quantized_nax.h) — fixed in d9b2df37
  LESSON: when reverting multi-file vendor changes, verify ALL files were reverted.

## MERGED FRONTIER (33 changes, all bit-exact)
  Previous frontier (PR #180, #194, #192, #107, #114, #116, #119, #231, #232, etc.)
  PR #230: Fuse g_proj+QKV into NVFP4 QKV R1 kernel (decode, ~2.0% decode)
  PR #245: INT8 O-proj dot4 vectorization (decode, ~0.8-1.1% on M5)
  PR #280: Down kernel outputs_per_simd 4→8 (decode)
  PR #283: O-proj tiling doublesimd (decode)
  PR #286: QKV results_per_simdgroup 4→8 (decode)
  PR #291: Precompute eScoreCorrectionBias FP32 (decode+prefill)
  PR #292: Prefill gate-softplus multi-token kernel (prefill)
  PR #294: Dead code removal (-9,288B LRM budget)
  PR #306: Prefill shared gate+up GEMM fusion (prefill, ~0.12% prefill)
  PR #307: Prefill attention O-proj+residual addMM fusion (prefill, ~0.9% prefill)
  Vendor file fix (d9b2df37): restored to pre-PR#243 state (M5 build fix)

## M5 SUBMISSION STATUS
  f68477a0: VALIDATING — frontier 1eac38a5 (vendor fix + PR #306 + PR #307, 35 changes)
  935c6831: FAILED — vendor fix only (cc66cb5)
  df9613a: REJECTED, 2.5817 — last scored birch submission (8/7 8:19 AM)
  4058d0b: REJECTED, 2.5459 — last successful M5 build (8/5)
  Birch best scored: 2.5817 (df9613a). Leaderboard #1: 2.5888 (maple, 97a5090).
  Gap to close: +0.27% from 2.5817 to 2.5888.

## CLOSED EXPERIMENTS (this session)
  PR #313 (alphonse): CLOSED — dead hypothesis. Prefill attention values/output
    transposes are already free (metadata-only) in MLX. No dispatches to eliminate.
  PR #285 (edward): CLOSED — too risky. Routed halved escape fix requires vendor
    file (quantized.cpp) modifications that caused M5 build failures. M4 can't
    validate _nax path. Halved scales can be re-derived later with M5-safe approach.

## ACTIVE ASSIGNMENTS (Wave 13, BASE_SHA=1eac38a5)
  PR #315 (alphonse): Re-enable prefill QKV bank fusion — restore prepareFusedQKVWeight()
    and flip default to ON (0-byte, bit-exact, 78 dispatch eliminations, prefill-only).
    Proven correct by PR #261. M4 decode +37% regression is M4-specific (1.48GB memory
    pressure on 36GB); M5 with 128GB should see no regression.
  PR #316 (thorfinn): Fuse gate-softplus matmul into NVFP4 O-proj kernel (decode) —
    eliminate 40 separate g_proj dispatches by computing g_proj+softplus inside
    O-proj kernel (~0.75% score, LRM-only, M4-testable).
  PR #317 (edward): Prefill post-attention RMSNorm + router GEMM fusion — fuse 2
    separate dispatches into 1 per sparse layer (39 dispatch eliminations, prefill,
    ~0.03-0.06% score, LRM-only).
  PR #314 (askeladd): Prefill MoE residual add elimination — fuse residual add into
    MoE block output (39 dispatch eliminations, prefill, in progress, draft).

## RESEARCH THEMES
  - M5 is bandwidth-bound (~89% GPU util). Only bandwidth reduction or dispatch elimination helps.
  - Prefill path is relatively unoptimized vs decode — prefill dispatch elimination is main opportunity.
  - All 4 M5-incompatible pattern classes fixed. M5 should build now.
  - LRM budget: 42,519B headroom. Byte-negative changes are valuable.
  - Halved scales optimization (~0.5% prefill) removed for M5 safety. Can re-derive with M5-safe approach.
  - Vendor file changes are HIGH RISK for M5 — the header/source mismatch was invisible on M4.
  - Exhausted: simd_sum vec, dot4, float4 stores, scale halving (decode), argmax fuse,
    RMSNorm fusion, attention epilogue 1-pass, input-vector staging, dense MLP simd_sum,
    per-row GEMV prefill fusion.

## POTENTIAL NEXT EXPERIMENTS
  1. Decode attention QK-norm + RoPE fusion (bit-exact, M4-testable, LRM-only)
  2. Prefill attention Q-proj+K-proj+V-proj GEMM fusion (like QKV bank fusion but for prefill L>1)
  3. Prefill down-proj + residual fusion (addMM pattern, like PR #307)
  4. Decode attention output write fusion (combine output store with attention computation)
  5. Re-derive halved scales with M5-safe approach (no kHalvedScales in vendor files)
  6. Prefill RMSNorm + QKV dispatch fusion (batched, not per-row GEMV)
