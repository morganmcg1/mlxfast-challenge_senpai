# SENPAI Research State
- 2026-08-05T13:46Z
- Fresh campaign (mlxfast-birch-20260805). All four students assigned distinct causal experiments, all in early implementation (no code pushed yet).
- **SCORE GAP**: Current best 2.5459 vs target 2.5523 (lBroth) = ~0.25% gap
- **FRONTIER**: 12a712d (Edward's PR #84 top-8 elimination merged, bit-exact, -49 lines)
- Current research focus: Four independent decode optimization arms targeting dispatch elimination and kernel tiling
  - Edward (PR #87): Merge shared+routed gate/up SwiGLU QMV into one dispatch — saves 39 dispatches/step (13.7%)
  - Alphonse (PR #88): Fuse RMSNorm into NVFP4 QKV decode kernel — saves 39 norm dispatches/step
  - Thorfinn (PR #89): Double output rows per SIMD in down+residual kernel (4→8, halves threadgroup count)
  - Askeladd (PR #90): Threadgroup input staging for shared SwiGLU QMV kernel (eliminate 2x redundant DRAM reads)
- All 4 arms are on independent code sections of LagunaRuntimeModel.swift, no conflicts
- M4 is bandwidth-bound (GPU gen 16); dispatch elimination may show larger gains on M5
- **PREFILL AUDIT COMPLETE** (2026-08-05): Prefill is 25% of score and partially optimized.
  Key findings:
  - Prefill QK-norm+RoPE already fused (prefill kernels for both sliding and full attention)
  - Prefill O-proj is 3 stock dispatches (softplus→broadcast multiply→matmul) for ALL 40 layers
  - Intermediate tensor: [1,512,8192] BF16 (3.1-4.2 MB) materialized and discarded per layer × 40 = ~150 MB traffic
  - All decode fused O-proj kernels are hard-gated to L==1; prefill gets zero fusion benefit
  - `callLastPrefillRow` (terminal prefill layer) has L=1-shaped O-proj but misses decode kernel reuse — QUICK WIN
  - New prefill GEMM kernel estimated at ~5-7KB, fits within 17,771-byte per-file headroom
- Potential next directions (from RESEARCH_IDEAS_NEXT_WAVE.md and NOVEL_FUSION_IDEAS.md):
  - **Prefill O-proj gate fusion GEMM**: Fuse softplus+gate+matmul into 1 dispatch for L>1 (P0, ~5-7KB, MEDIUM risk)
  - **callLastPrefillRow O-proj reuse**: Add guard to use existing decode BF16 GEMV kernel (P0, <1KB, LOW risk)
  - Register-resident scale pre-loading across blocks (2-4%, LOW risk, bit-exact)
  - Router GEMV + top-8 fusion (2-4%, MEDIUM risk)
  - Texture-backed NVFP4 weight storage (5-15%, MEDIUM risk, needs API investigation)
  - Apply same TG staging to routed SwiGLU QMV (8x redundant reads → 1x, 87.5% savings)
  - Fuse down+residual with shared expert SwiGLU (1-2%, MEDIUM risk)
- Prior negative results to avoid repeating:
  - PR #75 (Edward, TG input staging): NEGATIVE — L1 cache handles 2x redundancy on M4
  - PR #74 (Edward, prefetch depth): NEGATIVE — bandwidth-bound, depth hurts
  - PR #50 (Thorfinn, merge QMV): CLOSED — unresponsive (but idea is sound, now reassigned to Edward as #87)
  - M4 instruction-removal nulls are NOT refutations (M5 is instruction-bound at 89% capacity)

---

## Archive (2026-08-06T01:05:00Z)

Previous campaign state from 2026-08-06T01:05:00Z (all stale PRs closed, 4 new assignments created at that time). See git history for prior frontier state.

### Edward: FMA Dequant for QKV R1 Kernel
- Apply FMA-optimized dequant from `lagunaSharedSwiGLUQMVHeader` (line 6364) to
  `lagunaTailNVFP4QMVHeader` (line 4547). The tail header is a near-verbatim copy of the
  pre-FMA MoE qdot — same split-nibble decode, same accumulation pattern.
- FMA dequant gave end-to-end win for MoE gate/up despite bandwidth-bound. QKV is 802 MB/step.
- MEDIUM risk: FMA changes rounding (7→4 roundings). Signed-zero absorption argument
  needs re-verification for the tail kernel path (seed-elision + scale-defer flags compose).
- M4-testable (decode path, no _nax).

### Thorfinn: Merge Shared + Routed Gate/Up QMV Dispatch
- Fill `mergedSharedActivated` at L10248. Eliminates 39 separate shared expert gate/up
  dispatches. Plumbing already exists — just never assigned.
- MEDIUM risk: requires kernel branch or transform-side bank re-layout (different bank formats).
- M4-testable (decode path).

### Alphonse: Norm+NVFP4 QKV Fusion
- Create NVFP4-twin of `lagunaNormAffineQKV` (line 5120) that fuses RMSNorm + NVFP4 QKV
  into one dispatch. Current: RMSNorm (D1) + QKV (D2) are separate for all 40 NVFP4 layers.
  The INT8 fusion exists but NEVER fires (all layers are NVFP4, guard at 5537-5543 fails).
- Saves 40 dispatches/step. MEDIUM risk (new Metal kernel with inline RMSNorm + NVFP4 dequant).
- M4-testable (decode path).

### Askeladd: Pack Down-Projection Scales into Walk-Order Side Bank
- Reduce MoE down kernel bytes by packing scales into walk-order side bank format.
- EST 0.5-1.5%, LOW risk, bit-exact (same arithmetic, different memory layout).
- Requires transform-side change (`Sources/MLXFastTransform/`).
- M4-testable (decode path).

## CRITICAL RESEARCH FINDING: Prefill Variant 5→4 Switch is DEAD
- Variant 5 (WN=1, 128 thr/TG) is the shipped default and WON end-to-end on 2026-08-01:
  baseline 204.90 → variant 5 201.64 → +steel 198.00 µs (fastest on record)
- Variant 4 (WN=2, 256 thr/TG) showed +17.47% kernel-level but LOST end-to-end.
- Critical interaction: variant 4 LOSES register-local SwiGLU fusion (`kSwigluRegLocal`
  requires WN==1). Falls back to stock threadgroup-staged SwiGLU with extra barriers.
- The +17.47% kernel-level documentation was STALE — not updated when default moved to v5.
- Do NOT re-assign the variant 5→4 switch.
- **M4→M5 TRANSFER WARNING**: Edward's ops=2 showed +6.5% on M4 but 2.502 on M5 (vs 4058d0b's 2.546 = -1.7% M5 regression).
  Threadgroup geometry changes can flip sign across GPU core counts. Instruction-count reductions (FMA) should transfer better.
## Research Findings Summary

### Decode Dispatch Map (403 dispatches/step)
- 40 attention blocks × 5 dispatches = 200
- 39 MoE blocks × 5 dispatches = 195
- 1 dense MLP × 3 = 3
- Final RMSNorm + LM-head = 5
- asyncEval boundaries: 8 fences/step (non-blocking, already tuned near-optimal)
- 0 blocking eval() per decode step (already optimized)

### Top Fusion Opportunities (by dispatch savings)
1. RMSNorm + QKV NVFP4 GEMV (attention 1+2): saves 40/step — `lagunaNormAffineQKV` exists but declines for NVFP4
2. Gate softplus into QKV dispatch (attention 2+3): saves 40/step — prior 3-way failed (+2.7%)
3. Router top-8 into residual+RMSNorm+router (MoE 1+2): saves 39/step — hard (O(256²) reduction)
4. Shared gate/up into routed gate/up (MoE 3+4): saves 39/step — `mergedSharedActivated` plumbing exists
5. O-proj into fused attention (attention 4+5): saves 40/step — architecturally hardest

### Novel Optimization Targets (from research agents)
1. ✅ Eliminate redundant top-8 extraction → DEAD (PR #70, memory-bound, ALU removal doesn't help)
2. Pack down-projection scales into walk-order side bank (EST 0.5-1.5%, LOW risk, transform required)
3. ✅ Extend register prefetch depth 2-4 to routed gate/up R1 → DEAD (PR #74, bandwidth-bound, prefetch depth HURTS: depth-2 8.4% slower, depth-4 10.7% slower due to register pressure)
4. Fuse shared expert SwiGLU into down kernel (EST 1-2%, MEDIUM risk)
5. Vectorized online-softmax in sliding attention (EST 0.3-1%, HIGH risk)

### Next-Wave Research Ideas (from frontier agent, research/RESEARCH_IDEAS_NEXT_WAVE.md)
- P0: Stage activation vector in threadgroup memory (5-10% decode, LOW risk) — ASSIGNED to Edward (PR #75)
  Tests on routed gate/up R1 kernel (2× redundancy, 25% traffic cut). If L1 handles 2× redundancy,
  follow up with shared SwiGLU QMV kernel (4× redundancy, 37.5% traffic cut).
- P0: Depth-2 block unroll / prefetch next block's weights (3-6%, LOW risk) — DEAD (PR #74, negative)
- P1: Register-resident scale pre-loading across blocks (2-4%, LOW risk)
- P1: Texture-backed NVFP4 weight storage (5-15%, MEDIUM risk, needs API investigation)
- Key finding: decode GEMV is bandwidth-bound, NOT compute-bound. Hardware MMA is wrong tool.
  Activation vector (read many times) should be staged in threadgroup memory.
  Weight matrix (read once) should NOT be staged.

### Literature Search Findings (metal-moe-optimization)
1. Single command buffer per decode forward — #1 finding (5.2× in fak case study) — already optimized (0 blocking evals)
2. Free bit-exact gate+up concatenation — +6.6-7.6% — ALREADY DONE (routed SwiGLU QMV is already fused)
3. Fuse SwiGLU into gate gather_qmv epilogue — ALREADY DONE
4. Fuse down projection + score-weighted sum + shared-expert add — ALREADY DONE (lagunaRoutedSharedDownResidual)
5. FMA-optimized dequant inner loop — +12% — MERGED (commit 2268af4)
6. Per-assignment GEMV with high block parallelism — 28% TPOT (vLLM) — potentially applicable
7. Reduce KV-cache movement — sliding-window layers need only latest 512 positions — already implemented

### Eval Count Audit
- Total blocking eval() per decode step: 0 (already optimized)
- Total asyncEval() per decode step: 8 (already tuned to near-optimal)
- No leftover intermediate eval to eliminate

## Campaign State
- Fresh independent research campaign (mlxfast-birch-20260805)
- Advisor branch: `mlxfast-birch-20260805-advisor` @ 651a826
- Fixed experiment BASE_SHA: bb523807d3f70757d7cbae4b4b24ecfe5981a43d
- ORGANIZER_FRONTIER_SHA: bca94c5aa472a773a990ac61904340ce56465229
- Operator authorized official submissions from AWS Macs; use `--model "senpai"` first
- W&B project: wandb-applied-ai-team/mlxfast-birch
- Byte budget: 2,965,156 / 3,000,000 (34,844 headroom)
- LagunaRuntimeModel.swift: 508,548 / 524,288 bytes (15,740 per-file headroom)

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
| birch-edward | #49 | compiled-decode-segments | d53f538 | **MERGED ✅** — outputs_per_simd 1→2, 6.5% decode, 130/130 tokens. New frontier. |
| birch-edward | #65 | fma-dequant | (new) | **ASSIGNED** — FMA-optimized dequant inner loop. Correctness risk: FMA rounding. |
| birch-askeladd | #52 | prefill-moe-retile | 711ec75 | **Revision requested** — narrow to variant 5→4 only. Re-baseline against da9ee49. |
| birch-thorfinn | #50 | full-attn-decode-opt | fd1bf10 | Working — merge shared + routed gate/up QMV (eliminate 39 dispatches). Re-baseline against da9ee49. |
| birch-alphonse | #51 | lmhead-coarse-opt | 61b1b2d | Working — norm+QKV fusion coverage extension. Re-baseline against da9ee49. |

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

## Norm+NVFP4 QKV Fusion Analysis (2026-08-05T13:47Z)

### Key Finding: NVFP4 QKV Path Has NO RMSNorm Fusion

The existing `lagunaNormAffineQKV` kernel fuses RMSNorm + INT8 GEMV into one dispatch,
but it ONLY fires when `fusedAffine.mode == .affine && fusedAffine.bits == 8 && 
fusedAffine.groupSize == 32`. The current frontier uses NVFP4 for QKV on ALL 40 layers
(`DARKBLOOM_NATIVE_AFFINE_NVFP4_FROM` defaults to 0 → all NVFP4), so `foldGateIntoBank = FALSE`
and the fused norm+QKV kernel NEVER fires.

**Current decode path per attention layer (40 layers, all NVFP4 QKV):**
1. **RMSNorm dispatch** → `inputNorm(input)` → normalized [1,1,2048] BF16 (separate dispatch)
2. **NVFP4 QKV GEMV** → `lagunaDecodeNVFP4QKVR1(normalized, fusedAffine, heads)` (separate dispatch)
3. **INT8 Gate GEMV + softplus** → `lagunaGateSoftplus(normalized, affineGate, heads)` (separate dispatch)
4. Fused SDPA + KV cache write
5. Fused gated O-proj

Dispatches 1+2+3 are THREE separate dispatches that all consume the SAME `normalized` vector.
Only 1 (RMSNorm) is needed — the other two read the normalized vector from DRAM.

### Proposed Fusion: RMSNorm + NVFP4 QKV (+ optional Gate)

**Step 1 — Fuse RMSNorm + NVFP4 QKV (save 40 dispatches/step, ~5.3% decode)**
Create `lagunaNormNVFP4QKV` kernel that:
- Computes RMSNorm inline from residual + norm_weight (from `lagunaNormAffineQKVBody` prologue)
- Does NVFP4 QKV GEMV using `laguna_tail_nvfp4_qdot` (from `lagunaDecodeNVFP4QKVR1Source` body)
- Connected via inline normalization (same pattern as existing INT8 inline variant)
- Grid: (rows/2 × 64, 1, 1), ThreadGroup: (64, 1, 1) — matches existing NVFP4 kernel
- Bit-identical: norm produces same BF16 intermediate, NVFP4 dequant functions are shared

**Step 2 — Also fuse INT8 Gate + softplus (save another 40 dispatches/step, ~5.3% decode)**
Extend kernel to include gate rows:
- Grid: ((rows/2 + heads/2) × 64, 1, 1)
- Gate threadgroups use INT8 dequant + softplus (from `lagunaGateSoftplusSource`)
- More complex: mixed dequant formats in one kernel

**Combined: Steps 1+2 eliminate 80 dispatches/step ≈ 10.7% decode improvement**
Score impact: (1.107)^0.75 = 1.079 → ~7.9% score improvement
Projected: 2.5459 × 1.079 = 2.748 — FAR above 2.5523 target

**Byte budget**: LagunaRuntimeModel.swift is 508,548/524,288 bytes (15,740 bytes headroom).
New kernel source ~1.5-2KB — should fit within per-file cap.
Total editable surface: 2,965,156/3,000,000 (34,844 bytes headroom).

**Risk**: MEDIUM. Requires new Metal kernel with NVFP4 dequant + inline RMSNorm.
Correctness verified by: norm+QKV INT8 kernel already proves inline RMSNorm is bit-identical;
NVFP4 dequant functions are shared from `lagunaTailNVFP4QMVHeader`. M4-testable (decode path).
Gate behind `DARKBLOOM_FUSED_NORM_NVFP4_QKV` env var (default ON, A/B testable).

**Model geometry for kernel sizing:**
- Sliding layers (30): QKV rows = (64 + 2×8) × 128 = 10240, Gate rows = 64
- Full-attention layers (10): QKV rows = (48 + 2×8) × 128 = 8192, Gate rows = 48

## Decode Dispatch Anatomy (403 dispatches/step, from explore agent)

A single-token decode step dispatches **403 Metal kernels** across 40 layers + final norm + LM-head:
- Attention block (40 layers × 5): RMSNorm, QKV NVFP4 GEMV, Gate softplus, Fused attention, O-proj gated NVFP4 = 200
- Sparse MoE (39 layers × 5): Residual+RMSNorm+router, Top-8 selection, Routed gate/up GEMV+SwiGLU, Shared gate/up QMV, Fused down+residual = 195
- Dense MLP (layer 0 × 3): Residual+RMSNorm, Dense gate/up+SiLU, Dense down+residual = 3
- Final RMSNorm + LM-head pruner (5): Final RMSNorm, LM coarse, Argmax stage1, Exact-winner threshold, Exact/assembled = 5

### Top 5 Fusion Opportunities (by dispatch savings)
| Rank | Fusion | Saves | Difficulty | Status |
|------|--------|-------|-----------|--------|
| 1 | RMSNorm + QKV NVFP4 GEMV | 40/step | Medium | **ASSIGNED to Alphonse** |
| 2 | Gate softplus into QKV dispatch | 40/step | Med-Hard | NEXT WAVE (after Alphonse) |
| 3 | Router top-8 into residual+RMSNorm+router | 39/step | Hard | Unassigned |
| 4 | Shared gate/up into routed gate/up | 39/step | Medium | **ASSIGNED to Thorfinn** |
| 5 | O-proj into fused attention | 40/step | High | Unassigned (architecturally hardest) |

### Key Note on Gate Softplus Fusion
A prior "fused tail norm+QKV+gate" kernel was removed after a re-sweep measured +2.7% (defusion note, line 5554-5557). The gate fusion must re-win the timing against the current base which has FMA dequant. The defusion was before the FMA optimization, so the calculus may have changed.

## Potential Next Research Directions

### Currently Assigned (In-Flight)
- **Stage activation vector in TG memory for routed R1 gate/up kernel** (Edward, PR #75):
  Stages 2048-element BF16 input in threadgroup memory, eliminating 2× redundant device reads.
  25% total traffic reduction for bandwidth-bound kernel. Bit-exact, LOW risk.
  Follow-up: if positive, extend to shared SwiGLU QMV (4× redundancy, 37.5% traffic cut).
  PR #74 (prefetch depth) CLOSED NEGATIVE: bandwidth-bound, depth-2 8.4% slower, depth-4 10.7% slower.
  PR #70 (top-8 elimination) CLOSED NEGATIVE: memory-bound, ALU removal doesn't help.
- **Merge shared + routed gate/up QMV** (Thorfinn, PR #50): Fill the
  `mergedSharedActivated` gap at L10248. Eliminates 39 dispatches/step. +6.6-7.6% decode.
  Re-baselining against 8130379. Status check-in sent.
- **Fuse RMSNorm + NVFP4 QKV into one dispatch** (Alphonse, PR #51, redirected):
  EST 5.3% decode, eliminates 40 RMSNorm dispatches/step. STRONGEST available win.
  Re-baselining against 8130379. Status check-in sent.
- **Prefill MoE _nax variant 5→4 switch** (Askeladd, PR #52 revision):
  WN=2, 256 thr/TG. Needs M5 validation. +17.47% kernel-level.
  Double-buffering now in base. Re-baselining against 8130379. Status check-in sent.

### High-Priority Next Experiments
- **Fuse RMSNorm + NVFP4 QKV into one dispatch** (STRONGEST): Create
  `lagunaNormNVFP4QKV` kernel combining RMSNorm prologue from `lagunaNormAffineQKVBody`
  with NVFP4 GEMV body from `lagunaDecodeNVFP4QKVR1Source`. Eliminates 40 RMSNorm
  dispatches/step (~5.3% decode). Optionally also fuse INT8 gate+softplus for another
  40 dispatches (~10.7% decode total). See detailed analysis above. MEDIUM risk, M4-testable.
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


## Research Agent Findings (2026-08-06T03:45Z)

### Prefill Optimization Surface (unexplored, 25% of score)
- Prefill O-proj: STOCK BF16 matmul, NOT optimized
- Prefill O-proj gate: SEPARATE softplus + multiply — fuse into 1 dispatch (save 40 dispatches)
- Prefill SDPA: steel_attention_nax bq=64/bk=32/bd=128 — tile tuning possible but M5-only
- Prefill MoE: gather_qmm_rhs_nax NVFP4 — largest prefill compute (78 GEMM dispatches)
- M5 caveat: M4 does NOT select _nax variants; M4 prefill timing is NOT evidence for _nax changes

### MoE Input Read Redundancy (decode path)
- Routed SwiGLU R1 QMV: 2048 threadgroups x 2 simdgroups = 4096 full-input reads (16 MiB)
- Shared SwiGLU QMV: 256 threadgroups x 2 simdgroups = 512 full-input reads (2 MiB)
- Total gate/up: 4608 reads of 4KB input — massive redundancy, but likely L2-cached
- Key insight: This is LSU/instruction pressure, NOT DRAM bandwidth
- M5 (instruction-bound at 89% capacity) may benefit more from staging than M4 (bandwidth-bound)
- Down+residual kernel already uses threadgroup shared memory (for output reduction, not input staging)
- PR #75 (Edward, TG staging) was NEGATIVE on M4 — but M4 is bandwidth-bound, not instruction-bound
- The 9-slot mega-kernel pattern (down+residual) is proven feasible for gate/up fusion
