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
- **lBroth** at 2.5523 is the current promoted best (commit bca94c5, Aug 4).
  **This IS our ORGANIZER_FRONTIER_SHA** — our base already includes lBroth's
  winning code. We're optimizing ON TOP of the frontier, not chasing it.
  The local M4 ~2.455 measurement differs from the official M5 2.5523 due to
  architecture differences (M4 GPU gen 16, no _nax kernels).
- Recent promoted: metaspartan 2.528, a-github-name 2.539, lBroth 2.552
- Many rejected submissions in 2.48-2.52 range on Aug 4-5 — not beating 2.5523

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

## Deep Source Analysis Findings (2026-08-05T20:10Z)

### Attention Decode Path
- Per attention layer (40 total): **4 dispatches** — RMSNorm, fused QKV+gate INT8 GEMV, fused SDPA+cache-write, fused gated O-proj
- RoPE and QK-norm fused INTO the attention kernel (not separate dispatches)
- Layer-type rule: `layerIndex % 4 == 0` → full attention (10 layers), else sliding (30 layers)
- SWA uses `RotatingKVCache(maxSize:512, keep:0)` ring buffer; full uses `KVCacheSimple` (growing)
- **Quick win**: Dead mask construction at L11086-11089 (built every step but fused kernels don't use masks)
- **Future opportunity**: Norm+QKV fusion for INT8 path (save 40 dispatches) — NVFP4 tail has `lagunaNormAffineQKV` but INT8 path doesn't
- **Future opportunity**: Deferred-gate softplus for INT8 O-proj (save 40 dispatches) — only fires for NVFP4 OProj

### MoE Down Kernel (`lagunaRoutedSharedDownResidual`, L7851)
- All 8 routed + shared expert in **ONE dispatch** (288 threads = 9 simdgroups × 32 lanes)
- `outputs_per_simd = 1` (lowered from 4 in frontier commit 99b974c1) — key tuning knob
- Serial 8-way reduction on single lane post-barrier (287 threads idle)
- **Opportunity 1**: Raise `outputs_per_simd` 1→2 (amortize barrier+reduce across 2 rows)
- **Opportunity 2**: Parallelize 8-way reduction across lanes 0-7 (O(1) vs O(8))
- Caveat: `DARKBLOOM_SHARED_FIRST_DOWN` reorder regressed +0.10ms/step (barriers are encoder-wide)

### LM-Head Prune Path (`LagunaLmHeadPrune.swift`)
- **CORRECTION**: int6 1600 B/row arm does NOT exist as a kernel — it's comment-only
- Actual shipped default: **v5 int5 planar** (1344 B/row, ~131 MB) with MXFP8/e4m3 fallback
- 4 dispatches: coarse → argmax stage 1 → exact-winner threshold → exact assembly
- Block-level early-exit already implemented (non-candidate blocks skip GEMV)
- **Opportunity**: Merge argmax+threshold dispatches (save 1 dispatch/step, zero certificate risk)
- **Risk**: int4 coarse (1088 B/row, 19% bandwidth saving) would double quantization error, likely inflating candidate tail

### Student Progress Summary
| Student | PR | Branch | Head SHA | Status |
|---------|-----|--------|----------|--------|
| birch-askeladd | #52 | prefill-moe-retile | 711ec75 | **Submitted (inconclusive)** — revision requested: narrow to variant 5→4 only |
| birch-edward | #49 | compiled-decode-segments | eacc663 | No code yet — sent attention analysis + quick-win guidance |
| birch-thorfinn | #50 | full-attn-decode-opt | fd1bf10 | No code yet — sent MoE down findings as bonus |
| birch-alphonse | #51 | lmhead-coarse-opt | 61b1b2d | No code yet — sent LM-head format correction + dispatch consolidation idea |

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
- **MoE down kernel outputs_per_simd 1→2**: amortize barrier+reduce across 2 rows,
  halves threadgroups from 2048→1024. Low risk, stacks with reduction parallelization.
- **MoE down 8-way reduction parallelization**: spread 8 routed slots across lanes
  0-7, O(1) vs O(8) serial reduction. Independent of and stacks with outputs_per_simd.
- **Dead mask construction elimination**: remove wasted fullMask/slidingMask building
  at L11086-11089 (fused kernels don't use masks). Very low risk, quick win.
- **Norm+QKV fusion for INT8 path**: NVFP4 tail has `lagunaNormAffineQKV` (L5722) but
  INT8 group-32 path has no norm-fused kernel. Save 40 dispatches/step. Kernel dev.
- **Deferred-gate softplus for INT8 O-proj**: deferred-gate fusion only fires for NVFP4
  OProj (L3902). INT8 path runs separate softplus dispatch. Save 40 dispatches/step.
- **LM-head dispatch consolidation**: merge argmax+threshold dispatches (#2+#3) into one.
  Save 1 dispatch/step, zero certificate risk.
- **Interleave FP8 scales with FP4 codes**: transform+kernel change, medium
  risk, targets the bandwidth bottleneck directly.
- **Graph-visible cache + compiled segments expansion**: If Edward's P0
  prototype succeeds, extend to full-model compiled decode.
- **Source budget reclamation**: Remove dormant negative arms to free byte
  budget for new kernel families.
