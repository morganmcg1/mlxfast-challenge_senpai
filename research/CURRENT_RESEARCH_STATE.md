# SENPAI Research State — mlxfast-birch-20260805 (FRESH COPY)
- 2026-08-07T21:29Z (updated by advisor session)
- Advisor HEAD: d7758813. 37+ bit-exact changes on current frontier.
- LRM: 502,603/524,288 = 21,685 B headroom. Total surface 2,937,409/3,000,000 = 62,591 B headroom.

## GRID OVER-DISPATCH HYPOTHESIS: REFUTED
MLX's MLXFast API uses dispatchThreads(gridSize, threadgroupSize) where grid = TOTAL THREADS.
The × threadGroupSize multiplier in grid expressions is CORRECT. PR #333 was closed as invalid.
Do NOT revisit this hypothesis.

## M5 SUBMISSION STATUS
  7e974fa: VALIDATING (since 21:20 UTC) — resubmission of d7758813 with M5 fixes.
  66c0555: FAILED — same code with FUSED_QKV OFF, addMM OFF.
  48b8bcb: FAILED — earlier resubmission.
  CRITICAL: 24 consecutive M5 build failures since 68b66c5 PASSED at 9:36 AM (score 2.5520).
  Organizer frontier (3ff3992) PASSED at 6:51 PM (score 2.5213) — confirms M5 works intermittently.
  ad58c92 (=68b66c5) and cdefbb9 have 0 lines diff in Sources/ — identical code passed then failed.
  Best birch score: 2.5817 (df9613a). All prior birch submissions failed or rejected.
  Leaderboard #1: fyrsta7 2.6040 (yudduy). Gap: ~0.94%.

## ACTIVE ASSIGNMENTS (Wave 16, BASE_SHA=d7758813)
  PR #335 (thorfinn): Prefill asyncEval stride sweep — 0-byte env-var sweep. IN PROGRESS.
  PR #337 (alphonse): Decode asyncEval=off re-measurement — 0 bytes, ~1.3% total potential. CREATED.
  PR #338 (edward): Down residual outputs_per_simd 8→4 — ~80B, ~0.4% total. CREATED.

## RECENTLY CLOSED
  PR #334 (askeladd): Prefill router GEMV fusion v2 — FAILED (+2.46% prefill regression).
    Root cause: Metal lacks cross-TG sync → multi-token router kernel redundantly computes
    per-row RMSNorm 32× per row × 512 rows. ~4.8 GB extra bandwidth dwarfs 95 µs savings.
  PR #333 (thorfinn): Grid over-dispatch fix — INVALID. Hypothesis was wrong (MLX grid = total threads).
  PR #331 (askeladd): Broken assignment marker, replaced by PR #334.
  PR #332 (thorfinn): Broken assignment marker, replaced by PR #335.
  PR #330 (alphonse): Prefill shared SwiGLU+down fold — CLOSED (not merged, 203 insertions).
  PR #329 (edward): Dense gate/up fusion — MERGED (bit-exact, LRM-only).

## CLOSED WAVE 13 (all dead/failed)
  PR #317: Prefill norm+router fusion — DEAD. Custom GEMM can't beat MLX's GEMM.
  PR #324: Prefill SiLU+down fusion — DEAD. SiLU dispatch too small.
  PR #325: Prefill g_proj+QKV fusion — DEAD. Regressed +1.2% (tiling).
  PR #326: Decode router top-8 fusion — FAILED. 7.8% slower (1-tile parallelism loss).
  PR #328: Prefill shared halving — DEAD. Target cost too small.

## RESEARCH THEMES
  - M5 is bandwidth-bound (~89% GPU util). Only bandwidth reduction or dispatch elimination helps.
  - Grid over-dispatch hypothesis was REFUTED — MLX grid = total threads, not threadgroups.
  - Custom GEMM/GEMV for small matmuls can't beat MLX's optimized GEMM (PR #317, #325, #326, #334).
  - Multi-token kernel fusion limited by Metal's lack of cross-TG synchronization (PR #334).
  - Dispatch elimination can REGRESS timing if redundant computation > dispatch savings (PR #334).
  - M5 SAFETY: NO simd_sum(vec), NO dot(float4), NO *(thread float4*) casts. Scalar Metal only.
  - M5 build failures: 24 consecutive since 9:36 AM. Intermittent (identical code passed then failed).
  - Decode asyncEval schedule may be suboptimal on heavily-fused base (notes/52: current 1.7% worse
    than no asyncEval). Fresh measurement assigned to alphonse (PR #337).
  - Down kernel outputs_per_simd reduction may improve latency hiding (assigned to edward, PR #338).
  - Remaining research ideas in research/RESEARCH_IDEAS_FRESH_20260807_v7.md (8 ideas).
  - Vendor files were reverted to organizer frontier (d9b2df37, 658e1439) to fix M5 build issues.
    qmm_nax kHalvedScales support was removed. Re-adding is risky until M5 issue is resolved.

## NEXT-WAVE IDEAS (from RESEARCH_IDEAS_FRESH_20260807_v7.md)
  1. Prefill Expert Halved Scales via qmm_nax — ★★★★ ~0.9% total, needs vendor kernel work. RISKY (M5).
  2. Decode AsyncEval=off — ★★★ 0 bytes, ~1.3% total. ASSIGNED to alphonse (PR #337).
  3. Prefill AsyncEval Stride Sweep — ★★☆ 0 bytes, ~0.6% total. ASSIGNED to thorfinn (PR #335).
  4. LM Head TG Doubling — ★★☆ ~150B, ~0.2% total. UNASSIGNED.
  5. Prefill addMM Enablement — ★★☆ 0 bytes, ~0.3% total. CONFLICTS with M5 fix (disabled).
  6. Down Residual outputs_per_simd 8→4 — ★★☆ ~80B, ~0.4% total. ASSIGNED to edward (PR #338).
  7. Compiled Gate+O-proj Multi-Token — ★★☆ ~150B, ~0.3% total. Needs investigation first.
  8. Dense Layer-0 Triple Fusion — ★☆☆ ~3 KB, ~0.2% total. Low value, defer.

## EXHAUSTED DIRECTIONS
  - INT8 dedup, dot4, float4 stores, scale halving (decode), argmax fuse,
    RMSNorm fusion, attention epilogue, asyncEval (pre-grid-fix), KV cache quant,
    ops-800/QHOIST, dense MLP simd_sum, input-vector staging,
    decode router top-8 fusion (1-tile loss), prefill norm+router fusion (custom GEMM),
    prefill g_proj+QKV fusion (tiling degradation), prefill SiLU+down fusion (too small),
    prefill shared halving (too small), simd_sum(vec)/dot(float4)/thread float4* (M5 build failure),
    prefill router GEMV fusion v2 (RMSNorm redundancy, cross-TG sync limitation),
    grid over-dispatch (hypothesis was wrong).
