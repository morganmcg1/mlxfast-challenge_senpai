# SENPAI Research State
- 2026-08-07T20:48Z (updated by advisor session)
- Campaign mlxfast-birch-20260805. Advisor HEAD: ae8c290 (pushed to origin).
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

Fix: Remove * threadGroupSize from each grid. 29 one-line changes (25 LRM + 4 Prune). 0 bytes. Bit-exact.
Expected: 10-50% decode speedup = 7.5-37% total score.
ASSIGNED to thorfinn as PR #333. Advisor verified 29 total sites (25 in LRM + 4 in LagunaLmHeadPrune.swift).

## M5 SUBMISSION STATUS
  48b8bcb: VALIDATING (since 20:38 UTC, ~32+ min — longest validation = promising)
    Code: vendor at organizer frontier + 36+ LRM optimizations + NAX gate fix.
  Previous failures (all before NAX gate fix d14b491b):
    82933c7, b49e5d5, 07f3fd9, 51c3975: all FAILED
  M5 ROOT CAUSE (subagent): lagunaNAXGate() parsed GPU arch incorrectly for M5
    (Int("e1")=nil → always false). Fixed at d14b491b with simple env var check.
  Also fixed: simd_sum(vec), dot(float4), thread float4* — all removed (d6420f3d, 2358c577).
  Best birch score: 2.5817 (df9613a). All prior birch submissions failed or rejected.
  Leaderboard #1: fyrsta7 2.6040 (yudduy). Gap: ~0.94%.

## ACTIVE ASSIGNMENTS (Wave 14-15, BASE_SHA=ae8c290)
  PR #333 (thorfinn): Grid over-dispatch fix — 29 kernel sites, 0 bytes, bit-exact. HIGHEST PRIORITY.
  PR #329 (edward): Prefill dense gate+up fusion — collapse 2 matmuls into 1 via existing BF16 bank. WIP.
  PR #330 (alphonse): Prefill shared SwiGLU+down fold — fuse compiledSiluProduct. WIP.
  PR #331 (askeladd): Prefill router GEMV fusion — fuse router GEMV into prefill residual+RMSNorm kernel. WIP.
  NOTE: askeladd is IDLE (just finished PR #326, needs to pick up #331).

## CLOSED WAVE 13 (5 experiments, all dead/failed)
  PR #317 (edward): Prefill norm+router fusion — DEAD. Custom GEMM can't beat MLX's GEMM (+0.7% noise).
  PR #324 (alphonse): Prefill SiLU+down fusion — DEAD. SiLU dispatch too small (0.013% score).
  PR #325 (thorfinn): Prefill g_proj+QKV fusion — DEAD. Regressed +1.2% (tiling degradation).
  PR #326 (askeladd): Decode router top-8 fusion — FAILED. 7.8% slower (1-tile parallelism loss).
  PR #328 (thorfinn): Prefill shared halving — DEAD. Target cost too small (0.017% bandwidth).

## RESEARCH THEMES
  - CRITICAL: Grid over-dispatch is the biggest finding of the campaign. If confirmed, it could
    unlock 10-50% decode speedup. This is the highest-priority experiment.
  - M5 is bandwidth-bound (~89% GPU util). Redundant TGs waste L2/SLC bandwidth and GPU compute.
  - Custom GEMM/GEMV for small matmuls can't beat MLX's optimized GEMM (PR #317, #325, #326).
  - Dispatch elimination for small matmuls can REGRESS timing (tiling degradation, +1.2%).
  - Reducing GPU parallelism (1-tile) causes massive regression (7.8% slower, PR #326).
  - M5 SAFETY: NO simd_sum(vec), NO dot(float4), NO *(thread float4*) casts. Scalar Metal only.
  - M5 ROOT CAUSE: NAX gate bug (Int("e1")=nil) fixed at d14b491b. All pre-NAX-fix submissions failed.
  - ad58c92 was NOT actually clean on M5 (had the NAX gate bug all along).
  - After grid fix: asyncEval re-optimization (Idea 2), KV cache L2 locality (Idea 6).

## COMPOSITION PLAN
  Current frontier: ae8c290 (36+ bit-exact changes, QKV fusion ON, NAX gate fixed).
  In-flight: PR #333 (7.5-37%), PR #329 (~1.9%), PR #331 (~1.8%), PR #330 (~0.1%).
  If grid fix succeeds: massive score improvement from 2.5817 → 2.78+.
  Submit grid fix independently first, then compose with prefill winners.

## EXHAUSTED DIRECTIONS
  - INT8 dedup, dot4, float4 stores, scale halving (decode), argmax fuse,
    RMSNorm fusion, attention epilogue, asyncEval (pre-grid-fix), KV cache quant,
    ops-800/QHOIST, dense MLP simd_sum, input-vector staging,
    decode router top-8 fusion (1-tile loss), prefill norm+router fusion (custom GEMM),
    prefill g_proj+QKV fusion (tiling degradation), prefill SiLU+down fusion (too small),
    prefill shared halving (too small), simd_sum(vec)/dot(float4)/thread float4* (M5 build failure).

## NEXT-WAVE IDEAS (after grid fix result)
  1. Grid over-dispatch fix — ASSIGNED (PR #333, thorfinn). HIGHEST PRIORITY.
  2. AsyncEval re-optimization — DEPENDS on grid fix. Sweep DARKBLOOM_DECODE_ASYNC_STAGE.
  3. Routed down weight packed scales bank — UNASSIGNED. Bandwidth reduction for down kernel.
  4. KV cache L2 locality — DEPENDS on grid fix. If attention regresses, use 2x-4x multiplier.
  5. LM head threadgroup reduction — covered by grid fix, but further optimization possible.
  6. Embedding + first layer norm fusion — negligible gain (1 dispatch).
