# SENPAI Research State
- 2026-08-07T20:42Z (updated by advisor session)
- Campaign mlxfast-birch-20260805. Advisor HEAD: ce8a7de (pushed to origin).
  LRM: 502,603/524,288 = 21,685 B headroom. Total surface 2,934,676/3,000,000 = 65,324 B headroom.

## CRITICAL DISCOVERY: Systematic Grid Over-Dispatch (2026-08-07)
A research agent found that EVERY custom Metal kernel in the decode path has a
CUDA-to-Metal porting bug: grid = logical_tiles * threadGroupSize instead of
grid = logical_tiles. Metal's grid is threadgroup count, not total threads.
This launches 64x to 1024x more threadgroups than needed.

Verified in actual code:
- O-proj NVFP4 (L4493): 64x over-dispatch
- Sliding attention (L1670): 1024x over-dispatch
- Down+residual (L8013): 288x over-dispatch
- 14 more kernel sites (see research/RESEARCH_IDEAS_DECODE_v7.md)

Correct kernels (confirming pattern): gate product softplus (L3761), router top-8 (L8970).

Fix: Remove * threadGroupSize from each grid. 16 one-line changes. 0 bytes. Bit-exact.
Expected: 10-50% decode speedup = 7.5-37% total score.
ASSIGNED to thorfinn as PR #333.

## M5 SUBMISSION STATUS
  48b8bcb: VALIDATING (since 20:38 UTC) — frontier ce8a7de (36+ LRM optimizations, vendor at organizer frontier)
  82933c7: FAILED (infrastructure — n/a metrics, zero checked steps)
  Best birch score: 2.5817 (df9613a). All prior birch submissions failed or rejected.
  Leaderboard #1: fyrsta7 2.6040. Gap to close: +0.86% from best (2.5817 -> 2.6040).

## ACTIVE ASSIGNMENTS (Wave 14-15, BASE_SHA=ce8a7de)
  PR #329 (edward): Prefill g_proj+QKV fusion — concatenate g_proj into [Wq;Wk;Wv] bank (~1.9% score)
  PR #330 (alphonse): Prefill shared SwiGLU+down fold — fuse compiledSiluProduct + down QMM (~0.1-0.2%, HIGH risk)
  PR #331 (askeladd): Prefill router GEMV fusion — fuse router GEMV into residual+RMSNorm kernel (~1.8% score)
  PR #333 (thorfinn): Grid over-dispatch fix — remove * threadGroupSize from 17 Metal kernel grids (10-50% decode, HIGHEST PRIORITY)
  PR #332 (thorfinn): asyncEval stride sweep — BROKEN (duplicate markers), superseded by PR #333

## CLOSED
  PR #328 (thorfinn): Prefill shared scale halving — DEAD (shared expert scale bandwidth 0.017% of total, too small)

## RESEARCH THEMES
  - CRITICAL: Grid over-dispatch is the biggest finding of the campaign. If confirmed, it could
    unlock 10-50% decode speedup. This is the highest-priority experiment.
  - M5 is bandwidth-bound (~89% GPU util). Redundant TGs waste L2/SLC bandwidth and GPU compute.
  - Prefill path is also being optimized (g_proj fusion, router fusion, SwiGLU fold).
  - QKV fusion is already ON in the frontier (DARKBLOOM_FUSED_QKV default ON).
  - LRM budget is tight: 21,685 B headroom. Grid fix is 0-byte (negative).
  - M5 SAFETY: NO simd_sum(vec), NO dot(float4), NO *(thread float4*) casts. Scalar Metal only.

## COMPOSITION PLAN
  Current frontier: ce8a7de (36+ bit-exact changes, QKV fusion ON).
  In-flight: PR #329 (~1.9%), PR #330 (~0.1%), PR #331 (~1.8%), PR #333 (7.5-37%).
  If grid fix + prefill fusions all succeed: massive score improvement.
  Starting from 2.5817, grid fix alone could take us to 2.78+.
  Submit independently first, then compose winners for combined submission.

## EXHAUSTED DIRECTIONS
  - INT8 dedup, dot4, float4 stores, scale halving (decode), argmax fuse,
    RMSNorm fusion, attention epilogue, asyncEval (pre-grid-fix), KV cache quant,
    ops-800/QHOIST, dense MLP simd_sum, input-vector staging,
    decode router top-8 fusion, prefill shared scale halving (dead)
