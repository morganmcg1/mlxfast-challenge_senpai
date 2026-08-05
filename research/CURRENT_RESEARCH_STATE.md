# SENPAI Research State
- 2026-08-05T21:47:00Z
- PR #49 (birch-edward): REVIEW-READY WINNER — MoE down outputs_per_simd 1→2.
  6.5% decode improvement, 1.0% prefill improvement, 130/130 tokens match.
  Attempting merge (blocked by GitHub mergeability computation). Score est: 2.455→~2.60.
- PR #52 (birch-askeladd): inconclusive → revision requested (narrow to variant 5→4 only)
- PRs #50, #51: students working on redirected experiments (in progress)
- All 4 student PRs received base-acceptance feedback (advisor branch at 67ea914).
  Students' BASE_SHA bb523807 remains valid (no scored code change on advisor branch).
- Fresh independent research campaign launched (mlxfast-birch-20260805)
- Operator authorized official submissions from AWS Macs; use `--model "senpai"` first
- Sub-agent research complete: eval-count-audit, competitor-analysis, metal-moe-optimization,
  merge-gateup-analysis, lm-head-analysis all returned. Two frontier agents failed (timeout).
- Current best on leaderboard: 2.5523 (lBroth, commit bca94c5 = our ORGANIZER_FRONTIER_SHA)
- Students' assigned BASE_SHA: bb523807 (original frontier, scored code unchanged)
- Current advisor branch HEAD: 67ea914 (research notes only)

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
| birch-edward | #49 | compiled-decode-segments | d53f538 | **REVIEW-READY WINNER** — outputs_per_simd 1→2, 6.5% decode, 130/130 tokens. ATTEMPTING MERGE. |
| birch-askeladd | #52 | prefill-moe-retile | 711ec75 | **Submitted (inconclusive)** — revision requested: narrow to variant 5→4 only |
| birch-thorfinn | #50 | full-attn-decode-opt | fd1bf10 | Working — redirected to merge shared + routed gate/up QMV (eliminate 39 dispatches) |
| birch-alphonse | #51 | lmhead-coarse-opt | 61b1b2d | Working — redirected to norm+QKV fusion coverage extension |

## Frontier Agent Findings (2026-08-05T20:15Z)

### Deep Code Analysis V2 (frontier agent)
- **CORRECTION — "Grid Over-Dispatch" finding is FALSE**: The agent reported
  attention kernels use `grid: ((heads/2) * 1024, 1, 1)` as 1024x over-dispatch.
  Verified: `threadGroup: (1024, 1, 1)` means #threadgroups = grid/threadGroup =
  heads/2. The `* 1024` is the threadGroup size multiplied into the grid — standard
  MLX `metalKernel` convention where `grid` = total threads, NOT threadgroups.
  Same correction for dense MLP (`* 512` with `threadGroup: (512, 1, 1)` = 128 TGs).
  No redundancy exists. Do NOT pursue this.
- **Packed scales for down projection** (new finding, medium potential): The
  `DARKBLOOM_PACKED_SCALES` side-copy pattern (L10151) already proves scale
  interleaving works for routed gate/up. Extending to down projection (~504 MB/step
  traffic) is mechanical but adds ~624 MB resident memory.
- P2 (merge shared gate/up) confirmed — already assigned to Thorfinn.
- P5 (incremental sliding attention) — not worth pursuing (correct).

### Decode Dispatch Inventory (frontier agent — STILL RUNNING)
- Pending: comprehensive per-layer dispatch inventory for the full decode path.

## Competitor Analysis Findings (2026-08-05T21:00Z)

### Leaderboard State (Updated)
- lBroth at 2.5523 IS our ORGANIZER_FRONTIER_SHA — we're optimizing ON TOP of it
- 122 promoted submissions from 30 solvers as of Aug 1; leader at 184.4 decode tok/s
- lBroth's MTPLX repo uses MTP speculative decoding for parallel track (NOT our serial track)
- Serial-track wins must come from kernel-level optimization, dispatch reduction, weight layout

### Key Public Evidence (from competitor analysis agent)
1. **Fuse gate+up into one gather_qmm** (omlx #2238, mlx-vlm PR #1650): +6.6-7.6% decode,
   bit-exact, zero Metal changes. Reduces gather_qmm calls from 141→94 per token.
   Already partially implemented (DARKBLOOM_FUSED_ROUTED_GATE_UP) — the remaining gap is
   merging the SHARED expert's gate/up with the routed dispatch.
2. **Eliminate AsType/dtype-mismatch dispatches** (vmlx-swift-lm): Swift's MLXArray defaults
   to float32 for scalar literals, forcing AsType casts. Found 1100+ extra AsType ops/step
   in a Swift port = ~22ms overhead/token. MUST AUDIT our codebase for implicit float32
   promotion from scalar literals.
3. **Cooperative SMEM dequant** (Modular AppleM5Fp4MatMul): BK=64 at BM=128 = +34-45% at
   large M, bit-exact. CRITICAL: SIMD arithmetic >16 lanes crashes Metal. BK=64/BM=128 =
   exactly 16 (sweet spot).
4. **Coalesce scale loads into SMEM** (Modular): cooperative threadgroup load of scales
   +7-12%. WARNING: per-thread register caching of scales REGRESSED 20-30% (MLX #3251).
   Must be cooperative load, not per-thread.
5. **FMA-optimized dequant** (flash-moe): Rearrange `(nibble*scale+bias)*x` to
   `fma(nibble, scale*x, bias*x)`. +12% faster dequant inner loop.
6. **Audit eval() call count** (MLX discussion #3801): eval-per-call ~0.33-0.45ms vs
   in-graph dispatch ~105µs = 3.1x difference. Reducing eval() calls per decode step is
   high-leverage.
7. **M5 architecture**: 614 GB/s, decode is bandwidth-bound (~34-50% of roofline for MoE).
   Dense model hits 94% of roofline — gap is the single-token structure itself.

### AsType Audit — HIGH PRIORITY NEW DIRECTION
The vmlx-swift-lm finding (1100+ AsType ops = ~22ms overhead) is the single largest
untested hypothesis for our Swift runtime. Every scalar literal (0.5, 1.0, 2.5, etc.)
and intermediate computation that implicitly promotes to float32 creates an AsType
cast dispatch. This is potentially 10-20% decode improvement with ZERO numerical risk.
Must audit the codebase for: scalar dtype inference, sigmoid cast removal, universal
bfloat16 conversion, identity-weight dtype, MoE gate zero-out dtype.

## Metal MoE Optimization Literature Search (2026-08-05T21:28Z)

A comprehensive search agent (model=smart, agent=search, research-publications
mode) returned state-of-the-art MoE optimization findings for Apple Silicon
Metal GPU. Key results:

### Search Agent's Top Recommendations (ranked by impact × applicability)
1. **Single command buffer per decode forward** — literature's #1 finding.
   fak issue #1382: ~336 separate command buffers/token, each ~360µs launch/sync;
   batching into one buffer hit 59% device BW vs 11% individually = 5.2× faster.
   BaseRT paper (arXiv:2607.00501): native Metal runtime, up to 1.56× decode vs
   llama.cpp. **M5 note**: ops-per-buffer sweep is FLAT on M5 Max — bottleneck is
   genuine bandwidth, not dispatch-gap idle. MLX already lazy-evaluates into one
   command buffer at asyncEval boundaries. The remaining gain is kernel
   *encoding* overhead reduction, not command buffer submission.
2. **Free bit-exact gate+up concatenation** (omlx #2238, SGLang #26188) — concat
   gate/up experts into single gather_qmm, bit-identical, +6.6-7.6%. **Already
   partially implemented** in our codebase (DARKBLOOM_FUSED_ROUTED_GATE_UP). The
   remaining gap is merging the SHARED expert dispatch — assigned to Thorfinn.
3. **Fuse SwiGLU into gate gather_qmv epilogue** (SGLang #26188, ZMLX) — fold
   `silu(gate)*up` into gate matmul write, ~96 fewer dispatches/token at bs=1.
   Our routed gate/up kernel ALREADY does this (`lagunaRoutedSwiGLUQMV`). The
   shared expert kernel also does this (`lagunaSharedSwiGLUQMV`). Already done.
4. **Fuse down projection + score-weighted sum + shared-expert add** (omlx #2238,
   mlx-kquant) — one kernel per layer instead of 3-4. **Already done** in our
   codebase (`lagunaRoutedSharedDownResidual` fuses all 8 routed + shared down +
   residual into ONE dispatch).
5. **Verify M=1 NVFP4 uses dedicated GEMV (not MMA)** (Modular fp4_gemv) — if
   decode routes through MMA, switching to register-resident GEMV is ~1.53×.
   Our decode uses custom GEMV kernels (lagunaRoutedSwiGLUQMV etc.), not MMA.
   Already on the correct path.
6. **FMA-optimized dequant inner loop** (flash-moe) — `fma(nibble, scale*x,
   bias*x)` instead of `(nibble*scale+bias)*x`, +12%. Applies to NVFP4 dequant
   inner loop in our custom kernels. **Not yet tested.** Medium priority.
7. **Per-assignment GEMV with high block parallelism** (vLLM #41379) —
   thousands of small blocks for T≤8 decode, 28% TPOT. May apply to our down
   kernel threadgroup geometry.
8. **Reduce KV-cache movement** — sliding-window layers need only latest 512
   positions. **Already implemented** (RotatingKVCache(512)).

### Search Agent Findings Already Implemented
- Gate+up concatenation (partially) ✓
- SwiGLU fusion into QMV ✓
- Down+weighted-sum+shared+residual fusion ✓
- KV-cache pre-allocation and ring buffer ✓
- AOT metallib ✓
- SIMD matrix multiply in steel_attention ✓

### AsType Audit — CORRECTION (2026-08-05T21:28Z)
The search agent flagged 1100+ AsType ops from a DIFFERENT Swift port (vmlx-
swift-lm), not our codebase. Our codebase has only **28 total AsType calls**
(17 in LagunaRuntimeModel.swift, 11 in LagunaLmHeadPrune.swift), all
intentional numerical operations:
- `softplus(gate.asType(.float32)).asType(.bfloat16)` — necessary for float32 precision
- `correctionBias.asType(.float32)` — router bias needs float32
- `weights.asType(y.dtype)` — necessary dtype conversion for weighted sum
- LM-head pruner AsTypes — bit manipulation (int32/uint32/float32 view casts)

The "implicit float32 promotion from scalar literals" pattern is NOT present in
our codebase. Scalar literals in Metal kernels use explicit `float` types. The
AsType audit is a **non-issue** for our codebase. Downgraded from high priority.

### M5 NVFP4 Correctness Notes (from Modular docs)
- M5 flushes f32/bf16 denormals to zero but **preserves f16 subnormals** — decode
  must stay in f16 domain to decode ±0.5 exactly; exponent-injection trick is
  WRONG on M5. Our kernels use BF16 accumulation — verify this is safe.
- 16-lane SIMD width hard limit — Metal crashes on ≥24-lane 16-bit SIMD arithmetic.
  All accumulation must be fp32 (any width safe). Our kernels use fp32 accumulate.
- NVFP4 tensor-scale (global_scale) is broken on Metal (MLX #3550). Our code uses
  per-group NVFP4 (no global_scale) — unaffected.

## Sub-Agent Research Findings (2026-08-05T21:40Z)

### eval-count-audit (explore agent)
- **Result**: The decode path already has **0 blocking `eval()` calls** and **8 non-blocking `asyncEval()` fences** per step.
- The 6 `eval()` calls in the file are all init/warmup, NOT on the scored decode path.
- The 8 asyncEval fences are measured-tuned (notes/52: off=10.37ms vs ladder8=9.45ms, +9.7% from overlap).
- **Verdict**: This is an "already optimized" finding, not an opportunity. No eliminable eval overhead remains.

### competitor-analysis (search agent)
- **lBroth's MTPLX** uses MTP speculative decoding — FORBIDDEN on our serial track. Their serial-track win must come from kernel-level optimization, dispatch reduction, and weight layout.
- **Fuse gate+up into one gather_qmm**: bit-exact, +6.6-7.6%. Already partially implemented (DARKBLOOM_FUSED_ROUTED_GATE_UP). Remaining gap is shared expert merge — assigned to Thorfinn.
- **AsType/dtype-mismatch audit**: 1100+ AsType ops was from vmlx-swift-lm (different Swift port). Our codebase has only 28 AsType calls, all intentional. **DOWNGRADED TO NON-ISSUE.**
- **FMA-optimized dequant**: `fma(nibble, scale*x, bias*x)` +12% kernel-level. Not yet tested in our codebase.
- **Cooperative SMEM scale loading**: +7-12%, but must be cooperative (not per-thread register caching, which regresses 20-30%).

### metal-moe-optimization (search agent)
- **Single command buffer per forward pass**: #1 finding in literature. Our path already uses lazy eval + asyncEval (confirmed by eval-count-audit).
- **Dedicated M=1 register-resident GEMV for NVFP4 decode**: 1.53x over bf16 GEMV. Our decode already uses custom GEMV kernels, not MMA. Already on correct path.
- **M5 denormal behavior**: f16 domain must be used for NVFP4 decode (correctness-critical). Our kernels use BF16 accumulation — verify safe on M5.
- **16-lane SIMD width hard limit**: Metal crashes on ≥24-lane 16-bit SIMD arithmetic. All accumulation must be fp32.

### merge-gateup-analysis (explore agent)
- Confirmed `mergedSharedActivated` (L10248) is dead plumbing — declared `nil`, never assigned.
- Shared gate/up QMV is always a separate dispatch (1 per layer × 39 sparse layers = 39 dispatches/step).
- The merge opportunity is untouched — confirmed as a viable experiment.

### lm-head-analysis (explore agent)
- LM-head prune path is already maximally optimized — 4-dispatch sequence cannot be collapsed further.
- Argmax stage1 + threshold is a standard two-pass reduction over 100,352 elements.
- Coarse + stage1 cannot merge because coarse outputs must materialize for the exact pass.
- **Verdict**: LM-head dispatch consolidation is a dead end. Alphonse was correctly redirected to norm+QKV fusion.

## Potential Next Research Directions

### Currently Assigned (In-Flight)
- **MoE down kernel outputs_per_simd 1→2** (ASSIGNED to Edward, PR #49): ✅ WINNER —
  6.5% decode improvement, 1.0% prefill, 130/130 tokens. REVIEW-READY, ATTEMPTING MERGE.
  Next: assign Edward a follow-up (reduction parallelization or FMA dequant).
- **Merge shared + routed gate/up QMV** (ASSIGNED to Thorfinn, PR #50): fill the
  `mergedSharedActivated` gap at L10248. Eliminates 39 dispatches/step. +6.6-7.6% decode.
- **Norm+QKV fusion coverage extension** (ASSIGNED to Alphonse, PR #51): extend
  `lagunaNormAffineQKV` to cover INT8 layers. Save 40 dispatches/step.
- **Prefill MoE _nax variant 5→4 switch** (ASSIGNED to Askeladd, PR #52 revision):
  WN=2, 256 thr/TG. Needs M5 validation. +17.47% kernel-level.

### High-Priority Next Experiments
- **FMA-optimized dequant inner loop**: Rearrange NVFP4 dequant to use FMA.
  `fma(nibble, scale*x, bias*x)` instead of `(nibble*scale+bias)*x`. +12% on dequant.
  Applies to our custom MoE QMV kernels. Must verify bit-exactness on M5.
- **Cooperative SMEM scale loading**: Threadgroup-cooperative load of NVFP4 scales into
  shared memory. +7-12%. Must NOT be per-thread register caching (that regresses 20-30%).
- **MoE down 8-way reduction parallelization**: spread 8 routed slots across lanes
  0-7, O(1) vs O(8). Independent of and stacks with outputs_per_simd.
- **Per-assignment GEMV block parallelism** (vLLM #41379): thousands of small blocks
  for T≤8 decode, 28% TPOT improvement. May apply to our down kernel geometry.
- ~~AsType/dtype-mismatch audit~~ — **DOWNGRADED TO NON-ISSUE**: Our codebase has only
  28 total AsType calls, all intentional numerical operations. The 1100+ AsType ops
  finding was from a different Swift port, not our codebase.

### Medium-Priority Directions
- **Metal indirect command buffers (ICBs)**: Pre-encode dispatch sequences, reducing
  CPU-side encoding overhead. Alternative to MLX.compile().
- **Cooperative-tensor NVFP4 dequant for prefill MoE GEMM**: BK=64/BM=128 tiling for
  prefill path. +34-45% at large M (prefill, 25% weight). M5-only validation.
- **Morton-order traversal in `_nax` gather GEMM**: Better cache locality for short runs.
- **Packed scales for down projection**: Extend DARKBLOOM_PACKED_SCALES to down proj.
- **Interleave FP8 scales with FP4 codes**: ARCQuant-style co-located layout.
- **Graph-visible cache + compiled segments**: If Edward's prototype succeeds, expand.
- **Source budget reclamation**: Remove dormant negative arms to free byte budget.

### Non-Issues (Verified Dead Ends)
- Dead mask construction: `createAttentionMask` returns `.none` during decode — no waste.
- Grid over-dispatch: false alarm — MLX grid = total threads, not threadgroups.
- Async scheduling sweep: 66 runs confirm 6-fire ties 40-fire. Already near-optimal.
- LM-head int4: would double quant error, inflate candidate tail. Not worth pursuing.
- LM-head dispatch consolidation: 4-dispatch sequence is already maximally fused.
- AsType audit: only 28 calls in our codebase, all intentional. Not the same as the
  vmlx-swift-lm 1100+ ops finding. Not applicable.
