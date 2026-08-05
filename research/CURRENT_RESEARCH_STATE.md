# SENPAI Research State
- 2026-08-05T19:57:00Z
- Fresh independent research campaign launched (mlxfast-birch-20260805)
- Operator authorized official submissions from AWS Macs; updated submission attribution rules (use `--model "senpai"` first)
- PR #52 (birch-askeladd) first to submit: inconclusive, revision requested (3 bundled changes, no M4-viable _nax evidence, no W&B)
- PRs #49, #50, #51 still in progress (status:wip, ~6 hours since assignment)
- Dead code budget analysis COMPLETE: 4 Tier-1 candidates (~12K bytes) identified, doc at research/DEAD_CODE_REMOVAL.md
- Current best on leaderboard: 2.5523 (lBroth, commit bca94c5 = our ORGANIZER_FRONTIER_SHA). Many recent rejections.
- Advisor branch SHA: 19c909d (doc-only: research state + dead code plan). Accepted without rerun for all students.
- Students' assigned BASE_SHA: bb523807 (original frontier, scored code unchanged)

## Current Research Focus and Themes

Starting from the promoted frontier at score ~2.455 (commit bb52380). The
codebase is already heavily optimized with ~180 DARKBLOOM feature flags. The
campaign brief (synthesized from 126 public leaderboard promotions) identifies
five patterns: read fewer bytes, remove provably unnecessary work, collapse
dependency stages, expose independent work to the GPU, and move one-time work
out of scored windows.

Four independent experiment arms assigned to students, each targeting a
distinct code path:

1. **Compiled decode segments** (birch-edward, PR #49): Make KV cache ring
   position graph-visible (MLXArray instead of host Int) to enable MLX.compile()
   on multi-layer decode segments. Eliminates ~230µs/step CPU/FFI graph
   construction overhead. Highest ceiling (P0 from campaign brief).

2. **Full-attention decode optimization** (birch-thorfinn, PR #50): Audit and
   optimize the 10 full-attention decode layers (indices 0,4,...,36) which use
   KVCacheSimple + YaRN RoPE, compared to the 30 proven sliding layers using
   RotatingKVCache + plain RoPE. Target: identify and remove remaining
   dependency stages or dispatch overhead (P1).

3. **LM-head coarse pass optimization** (birch-alphonse, PR #51): Reduce
   bandwidth or dispatch count of the certified two-pass LM-head pruner's
   coarse pass (currently ~135 MB/step, int5 planar, 4-dispatch sequence).
   Target: byte reduction, dispatch consolidation, or candidate-density
   improvement while maintaining the mathematical certificate (P3).

4. **Prefill MoE gather retile** (birch-askeladd, PR #52): Retune gather-QMM
   tile geometry (BK/BM/BN) to match Laguna's short expert runs (avg 16 tokens
   per expert per layer in prefill). Prefill is 25% score weight (P2).

## Deep Research Findings (2026-08-05T14:00Z)

### M5 Bandwidth Profile
- M5 Max: 614 GB/s peak, 128 GB unified, 40-core GPU. Decode is deeply
  bandwidth-bound (~2 FLOP/byte for NVFP4 vs ~27 FLOP/byte ridge point).
- **M5 ops-per-buffer sweep is FLAT** — bottleneck is genuine bandwidth, not
  dispatch-gap idle. Primary levers: byte reduction and dispatch count reduction.
- Register file: 208 KiB/threadgroup, up to 128 GPRs/thread. No `lop3` on Metal.

### Top Fresh Ideas (from literature + code analysis, NOT yet assigned)
1. **Merge shared + routed gate/up QMV into one dispatch** — eliminates 39
   dispatches/step (14% of ~280 total). Code has `mergedSharedActivated` at
   line 10248 designed for this but never implemented. LOW risk. STRONGEST
   candidate for follow-up experiment.
2. **Interleave FP8 scales with FP4 codes** (ARCQuant-style) — co-located
   layout reduces device memory transactions in bandwidth-bound MoE QMV.
   Transform + kernel change. MEDIUM risk.
3. **KV cache NHD layout for sliding layers** — token-major layout could
   improve coalescing for 30 sliding layers' attention reads. MEDIUM risk.
4. **MoE down kernel: outputs_per_simd 1→2** — halves barrier count, doubles
   input reuse. ~1-2% gain. LOW risk. Small but viable.

### MoE Down Kernel Status
- 2048 threadgroups (1 per output row), 288 threads = 9 SIMDs × 32 lanes.
- At theoretical-minimum weight bandwidth — fully coalesced, no redundant reads.
- Barrier + single-thread combine epilogue are structurally forced (cross-expert
  weighted sum, BF16 accumulation order). Not removable.
- Only viable lever: outputs_per_simd 1→2 (~1-2% gain, bounded by barrier overhead).

### Async Scheduling Status
- 7 fire points (layers 0,1,7,15,23,31,39). Stride MEASURED (66 runs).
- 6-fire ties 40-fire (headroom ~0.08%). Already near-optimal.
- Layer-0 main-mask rung unmeasured but likely marginal.
- Not worth a dedicated experiment.

## Merge Gate/Up QMV Implementation Analysis (2026-08-05T14:30Z)

The "merge shared + routed gate/up QMV" idea was analyzed in depth:

- **Confirmed**: `mergedSharedActivated` at LagunaRuntimeModel.swift:10248 is
  declared nil, never assigned. The intended design was to carry the shared
  expert's gate/up activation from a merged dispatch so `fusedSharedDownInputs`
  (:10322) skips recomputing via the `??` fallback at :8356.
- **Weight bank mismatch (important correction)**: Routed and shared expert
  banks are NOT structurally identical:
  - Routed: 32-tile gate/up-interleaved codes + packed walk-order scales
    (scale_row_bytes=32)
  - Shared: concatenated codes (gate 0-511, up 512-1023) + plain row-major
    scales (scale_row_bytes=128)
  - Merge requires a prepare-time re-layout of the shared bank into routed
    format (bit-exact byte reorder) OR a kernel branch.
- **Dispatch configs**: Routed R1 = 2048 TG (8 slots × 256 tiles), shared R1 =
  256 TG. Combined = 2304 TG across 2 dispatches today. Merged = 2304 TG in
  one dispatch. Compute-neutral.
- **Down+residual kernel needs NO change** — it already takes
  `shared_activated` separately.
- **Cleanly A/B-testable** with a new `DARKBLOOM_MERGED_SHARED_GATEUP` flag.
  OFF = exact current behavior.
- **Risk**: LOW-to-MEDIUM. Main barrier is the bank re-layout (transform side).

## PR #52 Review (2026-08-05T19:38Z)

birch-askeladd submitted first with status:inconclusive. Three changes bundled:
1. Variant 5→4 switch (WN=2, 256 thr/TG) — strongest signal (+17.47% kernel-level)
2. Dead barrier elision on last chunk of last expert slot — provably correct
3. Double-buffered weight staging — well-structured, halves barriers per K-loop

**Decision: Request revision.** Narrow to one change (variant 4 switch), add W&B,
re-measure with thermal gate enabled, then request M5 validation. The double-
buffering and barrier elision should be separate follow-up experiments.

Key concern: all _nax changes are invisible on M4. Only the bm=32→16 non-_nax
dispatch change was M4-testable and showed no improvement (-0.1% prefill).

## Competitor Analysis (2026-08-05T19:49Z)

### Leaderboard State
- **lBroth** at 2.5523 (~4% above our 2.455). Uses context-copy drafting +
  MTPLX turbo kernels (speculative approach — may be on a different track or
  using serial-compatible variants).
- 122 promoted submissions from 30 solvers reached 2.39x by Aug 2. The ~5%
  acceptance band means compounding wins of ~5% each.

### Key Finding: omlx issue #2238
- Profiles the EXACT Laguna architecture (256 experts, top-8, NVFP4, M=1 decode)
- Documents a **fused MoE decode kernel + free gate+up regroup: +6.6-7.6% decode**
- This is the strongest public proxy for our optimization target

### Five Technique Clusters from Public Research
1. **M5 `_nax` tensor-core prefill kernels** (BaseRT papers, Apple WWDC2026)
2. **Fused MoE decode kernels** (SGLang/candle/ExecuTorch/omlx) — confirmed +6.6-7.6%
3. **Inline NVFP4 dequant** (Modular cooperative-SMEM, Apple cooperative tensors)
4. **SWA ring caches** (lucebox) — already implemented in our codebase
5. **Gate+up weight layout fusion** (Blaizzy/mlx-vlm) — partially implemented

### Six Novel Ideas from Competitor Analysis
1. Cooperative-tensor NVFP4 dequant for prefill MoE GEMM
2. Morton-order traversal in `_nax` gather GEMM
3. **Fused down+weighted-sum+shared-expert kernel** — merge all MoE work
4. Backporting upstream adaptive split-K NAX tuning
5. Pre-encoded Metal indirect command buffers (ICBs) — reduces CPU launch overhead
6. JIT-vs-AOT metallib correctness/performance diagnostic

### Student Redirect
- **Thorfinn** redirected from full-attention decode (10/40 layers, 25%) to
  merge shared + routed gate/up QMV (30/40 layers, 75%). This is the single
  biggest available decode win per competitor analysis. Code has `mergedSharedActivated`
  at line 10248 designed for this but never implemented.

## Current Student Status (2026-08-05T19:57Z)

| Student | PR | Hypothesis | Status |
|---------|-----|-----------|--------|
| birch-edward | #49 | Compiled decode segments (graph-visible KV) | Startup guidance sent |
| birch-thorfinn | #50 | **PIVOTED**: Merge shared+routed gate/up QMV | Pivot feedback sent |
| birch-alphonse | #51 | LM-head coarse pass byte reduction | Startup guidance sent |
| birch-askeladd | #52 | Prefill MoE tile geometry (revision) | Revision reminder sent |

All four students idle at ~6h since assignment. No visible code on PRs #49-51.
PR #52 has 4 commits but revision requested (3 bundled changes).

## Potential Next Research Directions

- **Merge shared + routed gate/up QMV** (ASSIGNED to Thorfinn): fill the
  `mergedSharedActivated` gap at LagunaRuntimeModel.swift:10248. Eliminates
  39 dispatches/step. Competitor confirms +6.6-7.6% decode.
- **Metal indirect command buffers (ICBs)**: Pre-encode a sequence of dispatches
  into a single command buffer, reducing CPU-side encoding overhead without
  changing kernel dispatch logic. Alternative to MLX.compile() for Edward's arm.
- **Cooperative-tensor NVFP4 dequant for prefill MoE GEMM**: Apple cooperative
  tensors + inline dequant may improve prefill MoE throughput on M5.
- **Morton-order traversal in `_nax` gather GEMM**: Better cache locality for
  the short expert runs in prefill MoE.
- **MoE down kernel outputs_per_simd 1→2**: small ~1-2% gain, low risk.
  Potential bonus for a student working on MoE path.
- **Interleave FP8 scales with FP4 codes**: transform+kernel change, medium
  risk, targets the bandwidth bottleneck directly.
- **Graph-visible cache + compiled segments expansion**: If Edward's P0
  prototype succeeds, extend to full-model compiled decode.
- **Source budget reclamation**: Remove dormant negative arms to free byte
  budget for new kernel families.
