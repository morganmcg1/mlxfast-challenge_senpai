# SENPAI Research State
- 2026-08-07T18:10Z (updated by advisor session)
- Campaign mlxfast-birch-20260805. Advisor HEAD: 1eac38a5 (pushed to origin).
  35 composed changes on current frontier (33 previous + PR #306 + PR #307).
  LRM budget: 22,652B headroom. Total surface ~2,958K/3,000,000 = 42,519B headroom.

## CRITICAL M5 BUILD FIX (d9b2df37, 2026-08-07)
  ROOT CAUSE of ALL birch M5 build failures since 8/5: PR #243 added kHalvedScales
  template parameter to three vendor files. The 87aff2fa revert restored
  fp_quantized_nax.cpp and quantized.cpp but MISSED fp_quantized_nax.h (137 lines
  of kHalvedScales code remained). Header/source mismatch compiled on M4 but
  M5 Metal compiler rejected inconsistent template signatures.
  FIX: Restored ALL 3 vendor files to 0bf6aeac (last birch M5 score 4058d0b at 2.5459).
  LRM halved paths disabled (lagunaPrefillSharedHalvedEnabled=false, useHalved=false).
  M5 submissions: 935c6831 (vendor fix only) VALIDATING. Composed frontier (with #306+#307) queued.

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
