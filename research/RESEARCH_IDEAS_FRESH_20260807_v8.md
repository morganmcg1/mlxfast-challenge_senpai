# Fresh Research Ideas — 2026-08-07 v8

## Budget Constraints (verified from CURRENT_RESEARCH_STATE)
- LRM: 502,603 / 524,288 B = 21,685 B headroom
- Total surface: 2,937,409 / 3,000,000 B = 62,591 B headroom
- Per-file cap: 524,288 B
- Growth cap per review: 262,144 B

## Context

- Best birch: 2.5817. Leaderboard #1: 2.6040. Gap: ~0.86%.
- M5 is bandwidth-bound (~89% GPU util, ~651.8 GB/s).
- Decode is 75% of score; prefill is 25%. Prefill seed is charged to the
  decode window, so prefill speedup also improves decode score.
- 37+ bit-exact optimizations merged. Many optimization families exhausted.
- Exhausted: INT8 dedup, dot4, float4 stores, scale halving (decode),
  argmax fuse, RMSNorm→LM head fusion (PR #276), attention epilogue,
  asyncEval optimization, dense MLP simd_sum, input-vector staging,
  simd_sum(vec)/dot(float4)/thread float4* (M5 build failure),
  custom GEMM kernels (PR #317, #330), decode router top-8 fusion (PR #326),
  grid over-dispatch (PR #333), prefill norm+router fusion (PR #317),
  prefill g_proj+QKV fusion (PR #325), prefill SiLU+down fusion (PR #324),
  prefill shared halving (PR #328), prefill router GEMV fusion v2 (PR #334),
  KV cache quantization (outside accepted envelope), texture-backed weights,
  threadgroup input staging (PR #75), down outputs_per_simd 4→8 (PR #89),
  down register-prefetch (PR #93), decode asyncEval=off (PR #337),
  down outputs_per_simd 8→4 (PR #338).
- Already implemented: mergedSharedActivated scaffold (shared QMV fused into
  routed R1 kernel), gate-softplus 4× scale/bias dedup (simd_shuffle),
  QKV/O-proj affine 4× scale/bias dedup (simd_shuffle), prefill QK-norm+RoPE
  fusion (lagunaPrefillSlidingQKNormRoPE / lagunaPrefillFullQKNormYaRN,
  DEFAULT ON), prefill MoE tail fusion (lagunaPrefillSortedMoETail, DEFAULT ON
  with deferUnsort), prefill fused QKV weight bank, callLastPrefillRow for
  last layer, RoPE angle atlas for both decode and prefill.

## Architecture Reference
- 40 layers: layer 0 = dense BF16 MLP, layers 1-39 = sparse MoE (NVFP4)
- Attention: 10 full-attention (48 heads, YaRN) + 30 sliding-window (64 heads,
  plain RoPE, window 512). QKV is INT8 affine (group-32). O-proj is INT8 affine
  or NVFP4 (tail layers).
- MoE: 256 routed experts (top-8 per token) + 1 shared expert per sparse layer.
  moeIntermediateSize = 512, sharedExpertIntermediateSize = 512, hiddenSize = 2048.
- Decode: ~324 dispatches/step, ~8 per layer, ~5376 µs/step.
- Prefill: ~600 dispatches, ~1.1 ms. MoE is bandwidth-bound (585 MB weight
  traffic dominates over compute).

## Prefill Dispatch Audit (per sparse layer, default config)

| Phase | Dispatches | Notes |
|-------|-----------|-------|
| Attention: input RMSNorm | 1 | Stock MLX RMSNorm (not fused for L>1) |
| Attention: QKV matmul | 1 | Fused BF16 QKV weight bank (retained) |
| Attention: QK-norm + RoPE | 1 | Fused (lagunaPrefillQKNormRoPE, DEFAULT ON) |
| Attention: SDPA | 1 | Stock MLX SDPA |
| Attention: gate product | 1 | Stock softplus (not fused for L>1) |
| Attention: O-proj matmul | 1 | Stock matmul (or addMM if enabled) |
| MoE: gatherSort | 1 | Sorts tokens by expert (indices.size >= 64) |
| MoE: routed gate/up GEMM | 1 | gatherQuantizedMM (sorted) |
| MoE: SiLU activation | 1 | compiledSiluProduct |
| MoE: routed down GEMM | 1 | gatherQuantizedMM (sorted) |
| MoE: shared gate/up GEMM | 1 | gateProj + upProj (2 separate) |
| MoE: shared SiLU | 1 | compiledSiluProduct |
| MoE: shared down GEMM | 1 | downProj |
| MoE: tail fusion | 1 | lagunaPrefillSortedMoETail (scatterUnsort+reduce+shared+residual) |
| **Total per sparse layer** | **~14** | (6 attention + 8 MoE) |

Decode equivalent: ~8 dispatches per layer. Prefill has ~6 extra dispatches
per layer (3 from attention, 3 from MoE/shared separation).

---

## Idea 1: Prefill — Fuse Input RMSNorm into QKV Matmul ★★★

### Causal Question
Can the prefill input RMSNorm (1 dispatch) be fused into the QKV matmul
dispatch, eliminating 1 dispatch per layer × 40 layers = 40 dispatches per
prefill, as the decode path already does via `lagunaNormAffineQKV`?

### Target Evidence
- Decode fuses RMSNorm + QKV + gate into 1 dispatch (`lagunaNormAffineQKV`).
- Prefill (L > 1) runs RMSNorm separately (L6038: `inputNorm(input)`) then
  the fused QKV weight matmul (L6043: `matmul(normalizedInput, fusedQKVWeight.T)`).
- The RMSNorm over [1, 512, 2048] is a reduction across the last axis
  (2048 elements per token). Each token's norm is independent.
- The QKV matmul is [1, 512, 2048] × [8960, 2048].T. The matmul could
  normalize each token's 2048-element row before the dot product.
- 40 dispatch eliminations at ~2.5 µs each = ~100 µs. Prefill ~1.1 ms.
  ~9% prefill dispatch savings. Actual impact depends on CPU/GPU overlap.

### Expected Signal
- If the CPU is dispatch-bound (many small dispatches saturate the dispatch
  queue), eliminating 40 dispatches saves ~100 µs = ~9% prefill = ~2.3% total.
- If the GPU is compute-bound (GEMMs dominate), dispatch elimination is hidden
  by async overlap and the gain is negligible.
- The prefill seed (512 tokens) is charged to the decode window, so this also
  improves decode score: ~2.3% × 0.25 = ~0.58% total from prefill alone.

### Implementation Approach
1. **Approach A (MLX.compile)**: Wrap `inputNorm(input)` + `matmul(result,
   fusedQKVWeight.T)` in `MLX.compile`. MLX's compiler traces the graph and
   may fuse the RMSNorm reduction into the matmul's input loading stage. Zero
   kernel code. If MLX's compiler can't fuse reduction+GEMM, this is a no-op.
2. **Approach B (Custom kernel)**: Write a multi-token kernel that reads
   [1, L, 2048] BF16 input, computes per-token RMSNorm (2048-element reduction
   per token via threadgroup memory + barrier), then performs the fused QKV
   matmul. This mirrors the decode `lagunaNormAffineQKV` but handles L tokens.
   The kernel would use `num_threadgroups = ceil(L * 8960 / tile_size)` with
   each TG computing one output tile for one token. The RMSNorm reduction
   is per-token (2048 elements), fitting in one TG.

### Bit-Exactness Argument
- The RMSNorm computation (`x * rsqrt(mean(x²) + eps) * weight`) must match
  MLX's stock RMSNorm rounding exactly.
- MLX's RMSNorm computes the mean-of-squares in FP32, applies rsqrt in FP32,
  then multiplies in BF16. The custom kernel must reproduce this exactly.
- The matmul accumulation order must match MLX's steel GEMM. For Approach A
  (MLX.compile), this is guaranteed since MLX's compiler controls both ops.
  For Approach B, the custom kernel must use the same tiling/reduction as MLX.

### M5 Safety Analysis
- Approach A: Uses MLX's built-in `compile`. No custom Metal. 100% safe.
- Approach B: Custom kernel. Must use scalar `simd_sum` (no `simd_sum(vec)`,
  no `dot(float4)`, no `*(thread float4*)`). The RMSNorm reduction uses
  threadgroup memory + barrier, which is standard Metal.
- M5 safe: yes, if scalar-only Metal is used. No forbidden constructs.

### Budget Estimate
- Approach A: 0 bytes (wrapping in MLX.compile, no new code).
- Approach B: ~500-1000 B (new kernel source string + dispatch function).
  Within 21.7 KB LRM headroom.

### Target: Prefill (25% of score)
The prefill input RMSNorm + QKV is a non-GEMM dispatch that can be eliminated.
Prefill seed speedup also improves decode score.

---

## Idea 2: Prefill — Unsorted gatherQuantizedMM to Eliminate gatherSort ★★★

### Causal Question
Does setting `doSort = false` (using `sortedIndices: false` and skipping
`gatherSort`/`scatterUnsort`) for the prefill MoE path reduce dispatch
overhead enough to speed up prefill, despite potentially worse memory access
patterns in the unsorted gather GEMM?

### Target Evidence
- The prefill MoE uses `doSort = indices.size >= 64` (L9822). With 512 tokens
  × 8 experts = 4096 indices, doSort is always true for prefill.
- `gatherSort` (L9829) is 1 dispatch per sparse layer × 39 = 39 dispatches.
- When `deferUnsort = true` (tail fusion ON), scatterUnsort is folded into
  `lagunaPrefillSortedMoETail`, so no separate scatterUnsort dispatch.
  But gatherSort is still 39 dispatches.
- With `doSort = false`: `gatherQuantizedMM` uses `sortedIndices: false`,
  skipping the sort entirely. The GEMM handles unsorted indices directly.
- The decode path already uses `sortedIndices: false` (L10257) for its
  unsorted small-batch path (indices.size < 64). The unsorted path is proven.
- 39 dispatch eliminations at ~2.5 µs each = ~97.5 µs. Prefill ~1.1 ms.
  ~8.9% prefill dispatch savings.

### Expected Signal
- If the unsorted GEMM's memory access pattern is not significantly worse
  than the sorted GEMM (because the GPU's SLC caches expert weights that are
  re-accessed across tokens), the net effect is positive: ~97.5 µs saved.
- For 512 tokens × 8 experts, each expert is selected by ~16 tokens on
  average. The sorted path groups these ~16 tokens together (good locality).
  The unsorted path interleaves experts (poor locality, but expert weights
  are only 256 KB each — likely SLC-resident).
- If the unsorted GEMM regresses by >97.5 µs due to extra memory traffic,
  the net is negative.

### Implementation Approach
1. In `lagunaFusedSortedRoutedGateUp` (L9817), add a flag
   `lagunaPrefillUnsortedMoEEnabled` (env var `DARKBLOOM_PREFILL_UNSORTED_MOE`).
2. When enabled, set `doSort = false` unconditionally, skip `gatherSort`,
   and pass `sortedIndices: false` to both `gatherQuantizedMM` calls.
3. Skip `scatterUnsort` / `deferUnsort` — the output is already in token order.
4. Adjust the tail fusion: `lagunaPrefillMoETail` (non-sorted variant) instead
   of `lagunaPrefillSortedMoETail` (sorted variant with inverseOrder).
5. The `lagunaPrefillMoETail` kernel already exists (L9741) and handles
   unsorted expert outputs.

### Bit-Exactness Argument
- `gatherQuantizedMM` with `sortedIndices: false` computes the same
  per-element dot products as `sortedIndices: true` — only the order of
  expert weight reads changes. The accumulation per output element is
  identical (same weight, same input, same scale, same reduction order).
- `lagunaPrefillMoETail` (non-sorted variant) computes the same weighted
  expert sum as the sorted variant minus the scatterUnsort — the expert
  outputs are already in token order.
- Bit-exact: YES. Same arithmetic, same rounding, different memory access.

### M5 Safety Analysis
- Uses stock `gatherQuantizedMM` and the existing `lagunaPrefillMoETail`
  kernel. No new Metal kernels. No forbidden constructs.
- 100% safe on M5.

### Budget Estimate
- ~200-300 B (flag definition + branch condition + tail kernel selection).
  Within 21.7 KB LRM headroom.

### Target: Prefill (25% of score)
Eliminates 39 gatherSort dispatches. Prefill seed also improves decode score.

---

## Idea 3: JIT Kernel Variant Consolidation via Function Constants ★★★

### Causal Question
Can consolidating per-head/per-rpg/per-depth kernel variants into fewer
metalKernel definitions (using Metal function constants for specialization)
reduce the JIT compile-storm enough to fix M5 build timeouts, while also
reducing per-step dispatch setup overhead?

### Target Evidence
- 51 `MLXFast.metalKernel` definitions expand to 80-110+ distinct Metal
  compilations (loop expansion: heads 64/48, rowsPerGroup 1..64, depth 1/2/4/8).
- Compilation is LAZY and SYNCHRONOUS: each kernel compiles on first dispatch
  via blocking `device newLibrary()`.
- The compile-storm collides with the runner ~900s timeout + 40C thermal gate.
- 25+ consecutive M5 build failures since the only passing run at 9:36 AM.
- Organizer frontier (0 JIT kernels) always passes — confirms compile-storm
  is the root cause.
- Warmup fix (2deac25c) reduces warmup prefill but does not reduce compile count.

### Expected Signal
- Reducing compile count from 80-110+ to ~30-40 should fix M5 build timeouts.
- Each eliminated compile saves ~100-500 ms of compilation time.
- Consolidating 2 per-head variants (48/64) into 1 function-constant kernel
  saves ~20 compiles (10 QKV + 10 attention variants).
- Reducing compile count also reduces the warmup dispatch count, further
  reducing warmup time.
- Secondary benefit: fewer metalKernel objects means less Swift heap
  overhead and faster first-dispatch latency.

### Implementation Approach
1. **Identify consolidation targets**: Find kernels that differ only in a
   constant parameter (e.g., `heads`, `rowsPerGroup`, `depth`).
   - `lagunaDecodeNVFP4QKVR1Kernels`: 2 variants (heads=48, heads=64)
   - `lagunaDecodeNVFP4QKVR1HalvedKernels`: 2 variants (same)
   - `lagunaFullFusedAttention` / `lagunaSlidingFusedAttention`: per-head
   - `lagunaNormAffineQKV` / `lagunaGatedAffineOProj`: per-head
2. **Replace Swift-level loop expansion with Metal function constants**:
   Instead of generating separate kernel source strings per head count,
   use `[[function_constant]]` in the Metal source to select the head count
   at dispatch time. MLX's `MLXFast.metalKernel` supports function constants
   via the `constants` parameter.
3. **Gate registration**: Only register kernel variants that are actually
   dispatched on the scored path. Use `early-return` when the env flag is off
   (as suggested in the CURRENT_RESEARCH_STATE root cause analysis).
4. **Verify**: Count compiled kernels via Metal's `device.newLibrary` callback
   instrumentation or `MTLDevice.registryID` profiling.

### Bit-Exactness Argument
- Function constants select between the same code paths at compile time —
  they are `#if`-like specialization that does not change the generated
  instructions for a given specialization value.
- Each consolidated kernel produces the same Metal ISA as the original
  per-variant kernel for the same parameter value.
- Bit-exact: YES. Same compiled code per parameter value.

### M5 Safety Analysis
- Function constants are a standard Metal feature (Metal 2.0+). M5 supports
  them natively.
- No `simd_sum(vec)`, `dot(float4)`, or `*(thread float4*)` casts introduced.
- The consolidation is a dispatch-time change, not a computation change.
- Risk: LOW. The main risk is a function constant not being supported for a
  specific parameter type (e.g., bool vs uint). Test on M4 first.

### Budget Estimate
- ~300-800 B per consolidated kernel group (function constant declarations +
  dispatch-time constant binding). Net reduction: some kernel source strings
  are removed (negative bytes).
- Total: likely net negative (consolidation removes more source than it adds).
  Well within budget.

### Target: Both decode and prefill (M5 build reliability + dispatch overhead)
Primary: fixes M5 build timeout (enables submissions to pass). Secondary:
reduces per-step dispatch setup by having fewer kernel objects.

---

## Idea 4: Decode — Threadgroup Memory Bank Conflict Elimination in Down+Residual Kernel ★★☆

### Causal Question
Do threadgroup memory bank conflicts in the `lagunaRoutedSharedDownResidualKernel`
cause serialization that reduces memory throughput, and can padding the
threadgroup memory layout eliminate them?

### Target Evidence
- The down+residual kernel (L7600) uses threadgroup memory for cross-simdgroup
  reduction: `down_outputs[9][8]` BF16 values (9 simdgroups × 8 output rows).
  Threadgroup memory usage: 9 × 8 × 2 = 144 B.
- The kernel has 9 simdgroups (8 routed + 1 shared), each with 32 threads.
  Threadgroup = 288 threads (9 × 32).
- Metal threadgroup memory has 32 banks, each 4 bytes wide. If consecutive
  simdgroups write to the same bank, accesses serialize.
- The `down_outputs` array is indexed as `down_outputs[simdgroup][row]`.
  With 8 rows per simdgroup and 2 bytes per BF16, each simdgroup's 8 rows
  occupy 16 bytes = 4 banks. If simdgroup 0 and simdgroup 4 both write to
  bank 0, they conflict.
- Bank conflicts reduce effective memory bandwidth. On a bandwidth-bound M5,
  this directly impacts decode step time.
- The down+residual kernel runs 39 times per decode step (once per sparse layer).

### Expected Signal
- If bank conflicts exist, adding 1-2 padding elements between simdgroup
  entries in `down_outputs` could eliminate them, improving memory throughput
  by 10-30% for the threadgroup memory access phase.
- The kernel is bandwidth-bound (weight reads dominate), so threadgroup
  memory conflicts may be a secondary bottleneck. But if the cross-simdgroup
  reduction phase is a significant fraction of kernel time, fixing bank
  conflicts could yield 1-3% decode speedup.
- The kernel's total time is ~13 ms/step / 324 dispatches ≈ 40 µs per
  dispatch. If the reduction phase is ~5 µs and bank conflicts add 30%, that's
  ~1.5 µs per dispatch × 39 = ~58.5 µs/step = ~1.1% decode speedup.

### Implementation Approach
1. Analyze the `down_outputs` array layout: `bfloat down_outputs[9][8]` =
   9 × 8 = 72 BF16 values = 144 bytes. Bank assignment: element `i` maps to
   bank `(i * 2) / 4 = i / 2` (BF16 = 2 bytes, bank = 4 bytes). So elements
   0-1 → bank 0, 2-3 → bank 1, etc. Simdgroup `sg` row `r` → element
   `sg * 8 + r` → bank `(sg * 8 + r) / 2`. For sg=0: banks 0-3 (rows 0-7).
   For sg=1: banks 4-7 (rows 8-15). For sg=2: banks 0-3 (rows 16-23).
   **Conflict**: sg=0 and sg=2 both access bank 0.
2. Add padding: change `down_outputs[9][8]` to `down_outputs[9][10]` (2 extra
   elements per simdgroup). Now sg=0: banks 0-4 (rows 0-9). sg=1: banks 5-9
   (rows 10-19). sg=2: banks 0-4 (rows 20-29). Still conflicts with sg=0.
3. Better approach: use a stride that avoids bank conflicts. With 32 banks
   and 4 bytes per bank, the array should have a stride that's not a multiple
   of 128 bytes (32 × 4). Current stride: 8 × 2 = 16 bytes. 16 is not a
   multiple of 128, so there shouldn't be systematic conflicts. BUT: if the
   access pattern is `down_outputs[sg][row]` where all simdgroups access the
   SAME row simultaneously (during the reduction phase), the bank is
   `(sg * stride + row) / 2`. With stride=8 (16 bytes), `sg * 8 + row` for
   fixed `row` gives banks `row/2`, `row/2 + 4`, `row/2 + 8`, ...
   For row=0: banks 0, 4, 8, 12, 16, 20, 24, 28, 0 → sg=0 and sg=8 conflict.
4. Fix: pad stride to 9 (or 10): `down_outputs[9][10]`. Stride = 10 × 2 = 20
   bytes. Banks for fixed row: `row/2`, `row/2 + 5`, `row/2 + 10`, ...
   For row=0: banks 0, 5, 10, 15, 20, 25, 30, 3, 8 → no conflicts.

### Bit-Exactness Argument
- The padding elements are never read — they exist only to shift the bank
  assignment. The reduction loop (L7961-7980) reads `down_outputs[e][row]`
  for `e` in 0..8 and `row` in 0..7. The padded elements at indices 8-9 are
  never accessed.
- The arithmetic is unchanged. The BF16 rounding sequence is identical.
- Bit-exact: YES. Only memory layout padding, no computation change.

### M5 Safety Analysis
- Threadgroup memory padding is standard Metal. No forbidden constructs.
- The padded array is 9 × 10 × 2 = 180 B (vs 144 B). Well within the 32 KB
  threadgroup memory limit.
- 100% safe on M5.

### Budget Estimate
- ~50-100 B (change array dimensions in kernel source string).
  Within 21.7 KB LRM headroom.

### Target: Decode (75% of score)
The down+residual kernel is the single largest MoE kernel in decode. Even a
small throughput improvement compounds across 39 layers × 128 steps.

---

## Idea 5: Prefill — MLX.compile to Fuse Shared Expert Gate/Up + SiLU ★★☆

### Causal Question
Can `MLX.compile` fuse the shared expert's separate `gateProj` + `upProj` +
`compiledSiluProduct` dispatches into fewer dispatches during prefill?

### Target Evidence
- The shared expert (LagunaRuntimeMLP) prefill path (L8554-8665) uses:
  1. `gateProj(x)` — stock matmul (1 dispatch)
  2. `upProj(x)` — stock matmul (1 dispatch)
  3. `compiledSiluProduct(gate, up)` — compiled function (1 dispatch)
  4. `downProj(activated)` — stock matmul (1 dispatch)
  Total: 4 dispatches per sparse layer × 39 = 156 dispatches per prefill.
- The shared expert is a standard (non-routed) MLP with BF16 weights. All
  512 tokens pass through it.
- `MLX.compile` traces the computation graph and fuses elementwise ops. If
  `gateProj` and `upProj` share the same input `x`, the compiler may fuse
  the two matmuls + SiLU into fewer dispatches.
- `compiledSiluProduct` is already a compiled function — fusing it with the
  preceding matmuls requires the compiler to see across the compiled boundary.

### Expected Signal
- If MLX.compile can fuse gateProj + upProj into a single matmul (broadcasting
  both weight matrices), it saves 1 dispatch per layer × 39 = 39 dispatches.
  ~97.5 µs = ~8.9% prefill dispatch savings.
- If MLX.compile can additionally fuse the SiLU into the matmul epilogue,
  it saves 2 dispatches per layer × 39 = 78 dispatches. ~195 µs = ~17.7%
  prefill dispatch savings = ~4.4% total.
- The shared expert GEMMs are [512, 2048] × [512, 2048] = 537M FLOPs each.
  At M5's ~5 TFLOPS (BF16), each GEMM is ~107 µs. Two GEMMs = ~214 µs.
  Fusing into one GEMM (concatenated weights) would compute [512, 2048] ×
  [1024, 2048] = 1.07G FLOPs in one dispatch, taking ~214 µs — same compute
  but 1 fewer dispatch.

### Implementation Approach
1. Replace the shared expert's forward path with an `MLX.compile`-wrapped
   function:
   ```swift
   let compiledSharedMLP = MLX.compile { (x: MLXArray) in
       let gateUp = matmul(x, fusedGateUpWeight.T)  // [512, 1024]
       let gate = gateUp[.ellipsis, 0..<512]
       let up = gateUp[.ellipsis, 512..<1024]
       let activated = compiledSiluProduct(gate, up)
       return downProj(activated)
   }
   ```
2. Build `fusedGateUpWeight` at load time by concatenating `gateProj.weight`
   and `upProj.weight` along the output dimension.
3. The `MLX.compile` function traces the graph and may fuse the matmul + slice
   + SiLU into fewer dispatches.

### Bit-Exactness Argument
- The fused matmul `matmul(x, [W_gate; W_up].T)` produces the same output
  as separate `matmul(x, W_gate.T)` and `matmul(x, W_up.T)` concatenated.
  Each output element's dot product uses the same weight and input values
  in the same order. The GEMM accumulation order depends on MLX's tiling,
  which is the same for both the fused and separate matmuls (same steel GEMM
  backend).
- `compiledSiluProduct` is already bit-exact — fusing it with the preceding
  matmul via `MLX.compile` does not change the rounding boundaries (the
  compiled function still produces the same intermediate values).
- Bit-exact: YES, IF MLX.compile does not change the GEMM tiling or the
  SiLU rounding. Must verify with `LagunaUpstreamEquivalence`.

### M5 Safety Analysis
- Uses MLX's built-in `compile` and `matmul`. No custom kernels. No forbidden
  constructs.
- Risk: MEDIUM. MLX.compile may produce different tiling that changes the
  GEMM accumulation order (near-tie tokens could flip). Must verify.
- 100% safe on M5 from a build perspective.

### Budget Estimate
- ~200-400 B (fused weight construction + compiled function wrapper).
  Within 21.7 KB LRM headroom.

### Target: Prefill (25% of score)
The shared expert runs on all 512 tokens for 39 sparse layers. Dispatch
elimination compounds across layers.

---

## Idea 6: Decode — Indexed Metadata LUT for Standalone g_proj ★★☆

### Causal Question
Can deduplicating the g_proj affine INT8 (scale, bias) BF16-bit pairs into a
UInt16-indexed LUT reduce metadata bandwidth enough to speed up the decode
attention gate-softplus dispatch?

### Target Evidence
- From BANDWIDTH_AUDIT Opportunity 4: `lagunaNativeAffineGProjWeight` (L435-450)
  never sets `indexedMetadata`, and `lagunaGateSoftplusSource` has no indexed
  variant (reads raw scales/biases).
- The indexed LUT scheme (`lagunaIndexedAffineMetadata`, L2853-2891) dedups
  (scale, bias) BF16-bit pairs into a UInt16-indexed LUT. It is already wired
  into the fused QKV bank (L5374) and O-proj bank (L5304), but NOT into g_proj.
- g_proj has heads × 64 = 3072-4096 (scale, bias) pairs per layer.
  At 4 bytes per pair (2 BF16), that's 12-16 KB metadata per layer.
  × 40 layers = ~480-640 KB metadata per decode step.
- The gate-softplus kernel reads these scales/biases with 4× redundancy
  (already deduped via `simd_shuffle` broadcast), but the RAW values are
  still loaded from device memory once per group. The LUT would replace
  4-byte (scale, bias) device loads with 2-byte LUT index loads + a small
  LUT lookup.
- Actual savings depend on the dedup ratio (distinct pairs / total pairs).
  If 50% dedup, metadata bandwidth drops by ~50% × 480-640 KB = ~240-320 KB
  per step. At M5 651.8 GB/s, ~0.4-0.5 µs per step. Small.

### Expected Signal
- If dedup ratio is high (>80%), metadata bandwidth drops by ~80% × 480 KB =
  ~384 KB per step = ~0.6 µs per step = ~0.01% decode. Very small.
- The real benefit may be in reducing the number of distinct device memory
  pages accessed (better SLC utilization) rather than raw bandwidth.
- This is a LOW-impact, LOW-risk optimization. Worth trying only if a quick
  census shows high dedup ratio.

### Implementation Approach
1. Run a census: count distinct (scale, bias) BF16-bit pairs across all
   g_proj layers. If dedup ratio < 50%, abort (not worth the complexity).
2. Build the LUT at transform time: `lagunaNativeAffineGProjWeight` sets
   `indexedMetadata = true` and builds the LUT + index array.
3. Add an indexed variant to `lagunaGateSoftplusSource`: use the same
   `metadataLoad` pattern as `lagunaNormAffineQKV` (L3815-3825) which
   already supports the indexed path:
   ```metal
   if (simd_lid == gl) {
       uint pair = metadata_lut[mi[row * in_vec_size_g]];
       scale = float(as_type<bfloat>(ushort(pair)));
       bias = float(as_type<bfloat>(ushort(pair >> 16)));
   }
   scale = simd_shuffle(scale, gl);
   bias = simd_shuffle(bias, gl);
   ```

### Bit-Exactness Argument
- The LUT stores exact BF16 bits: `ushort pair = (scale_bits << 0) | (bias_bits << 16)`.
  Reconstruction: `scale = as_type<bfloat>(ushort(pair))`, `bias = as_type<bfloat>(ushort(pair >> 16))`.
  The BF16 bit patterns are preserved exactly — no precision loss.
- The `simd_shuffle` broadcast is unchanged — only the source of the scale/bias
  values changes (LUT lookup instead of direct device load).
- Bit-exact: YES. Same values, same broadcast, same arithmetic.

### M5 Safety Analysis
- Uses `simd_shuffle` (already used in the kernel). No forbidden constructs.
- The LUT lookup is a scalar `ushort` load + bitcast — standard Metal.
- 100% safe on M5.

### Budget Estimate
- ~200-400 B (indexed metadata setup in g_proj weight prep + indexed kernel
  variant in gate-softplus source).
- Within 21.7 KB LRM headroom.

### Target: Decode (75% of score)
The g_proj gate-softplus runs 40 times per decode step. Small per-step savings
but zero risk.

---

## Idea 7: Prefill — Custom Flash-Attention SDPA for Full-Attention Layers ★★☆

### Causal Question
Can a custom flash-attention kernel for the 10 full-attention prefill layers
(512×512×48 heads) reduce intermediate memory traffic enough to speed up
prefill, compared to stock MLX SDPA?

### Target Evidence
- 10 full-attention layers use stock MLX SDPA for [1, 48, 512, 512] attention.
- Stock MLX SDPA may materialize the full 512×512 attention score matrix
  (48 × 512 × 512 × 4 bytes = 50 MB per layer) in intermediate memory.
- Flash attention computes the attention in tiled blocks, keeping only
  a tile of scores in registers/threadgroup memory, reducing intermediate
  memory traffic from O(L² × H) to O(L × H × tile_size).
- The decode fused attention kernel already implements online softmax (a
  flash-attention variant) for L=1. Extending to L>1 is architecturally
  different (multiple queries, batch SDPA) but the algorithmic foundation
  exists in the codebase.
- Prefill is ~1.1 ms. If SDPA materialization is ~50 MB per layer × 10
  layers = 500 MB at 651.8 GB/s = ~0.77 ms of write+read traffic. Eliminating
  this could save ~0.77 ms = ~70% prefill = ~17.5% total. (Upper bound;
  MLX's SDPA likely already uses tiling internally.)

### Expected Signal
- If MLX's SDPA already tiles internally (likely, since MLX uses Metal
  Performance Shaders or a flash-attention implementation), the savings are
  minimal. The custom kernel would need to match or beat MLX's tiling.
- If MLX's SDPA materializes the full score matrix (less likely), the savings
  could be significant.
- A 10-20% prefill SDPA speedup = ~2.5-5% prefill = ~0.6-1.3% total.
- Risk of regression: custom kernels have repeatedly failed to match MLX's
  optimized GEMMs (PR #317, #330). SDPA is not a GEMM, but the same lesson
  applies — MLX's internal implementation may be highly optimized.

### Implementation Approach
1. First, profile: check if MLX's SDPA materializes the full score matrix
   by measuring intermediate memory allocations during prefill. Use MLX's
   `MLXFast.setMemoryBudget` or inspect the Metal command buffer allocations.
2. If materialization is confirmed, implement a flash-attention kernel:
   - Tile the query dimension (512 queries) into blocks of B_q (e.g., 32).
   - Tile the key/value dimension (512 positions) into blocks of B_kv (e.g., 64).
   - For each (B_q, B_kv) tile: compute Q×K scores, apply online softmax,
     accumulate V contributions. Keep scores in threadgroup memory.
   - Use the existing online softmax code from the decode fused attention
     kernel (L1532-1601) as the algorithmic template.
3. Handle YaRN RoPE: the full-attention layers use YaRN (partial-rotary RoPE).
   The RoPE must be applied to Q and K before the score computation. The
   custom kernel would fuse QK-norm + YaRN RoPE + SDPA (like the decode
   `lagunaFullFusedAttention` but for L>1).

### Bit-Exactness Argument
- The flash-attention online softmax uses a different reduction order than
  stock SDPA. The running max, exp, and sum are accumulated in tile order
  rather than position order.
- This changes the floating-point rounding of the softmax normalization,
  which can change attention scores and outputs.
- NOT bit-exact. Requires `LagunaUpstreamEquivalence` verification.
- Same risk profile as DEEP_RESEARCH_IDEAS #3 (fused pair_a+pair_b online
  softmax). The decode fused attention kernel already uses online softmax
  and passes correctness — so the algorithm is proven correct, but the
  multi-token variant may produce different rounding.

### M5 Safety Analysis
- Custom kernel. Must use scalar `simd_sum` (no forbidden constructs).
- The online softmax uses threadgroup memory for accumulation (same as
  decode kernel). Well within 32 KB limit.
- Risk: MEDIUM. Numerical differences from stock SDPA may flip near-tie
  tokens. Must verify with 64-step drift tripwire + upstream equivalence.

### Budget Estimate
- ~1500-3000 B (new kernel source string + dispatch function + cache write
  fusion). Larger than other ideas.
- Within 21.7 KB LRM headroom, but uses a significant fraction.

### Target: Prefill (25% of score)
Only 10 full-attention layers (not the 30 sliding layers, which use a
different attention pattern). Prefill seed also improves decode score.

---

## Idea 8: Prefill — Fuse Shared Expert Down GEMV into MoE Tail Kernel ★★☆

### Causal Question
Can the shared expert's down projection GEMV (currently a separate dispatch)
be fused into the `lagunaPrefillSortedMoETail` kernel, eliminating 1 dispatch
per sparse layer × 39 layers = 39 dispatches per prefill?

### Target Evidence
- The prefill MoE tail kernel (`lagunaPrefillSortedMoETail`, L9675) currently:
  - Reads `shared_output` [1, L, 2048] (pre-computed by separate shared expert dispatch)
  - Reads `sorted_expert_outputs` [L, 8, 2048]
  - Reads `inverse_order`, `router_weights`, `residual`
  - Computes: scatterUnsort + weighted reduce + shared add + residual add
- The shared expert's forward path (L8554-8665) runs BEFORE the tail kernel:
  1. gateProj + upProj (2 matmuls) = 2 dispatches
  2. compiledSiluProduct = 1 dispatch
  3. downProj = 1 dispatch → produces `shared_output`
- The tail kernel reads `shared_output` — if we fuse the down GEMV into the
  tail kernel, the kernel would read the shared expert's ACTIVATED intermediate
  [1, L, 512] instead of `shared_output` [1, L, 2048], and compute the down
  GEMV inline.
- 39 dispatch eliminations at ~2.5 µs each = ~97.5 µs. Prefill ~1.1 ms.
  ~8.9% prefill dispatch savings = ~2.2% total.

### Expected Signal
- The tail kernel currently does elementwise ops (scatter, weighted reduce,
  add). Adding a GEMV (shared down: [L, 512] × [2048, 512] NVFP4) makes it a
  mixed compute/memory kernel.
- The shared down weight is [2048, 512/8] = 128 KB per layer. × 39 = ~5 MB
  total. The tail kernel would read this weight in addition to its current
  inputs. This is the SAME weight that the separate down dispatch reads — no
  extra bandwidth, just 1 fewer dispatch.
- If the kernel becomes too complex (mixed GEMV + elementwise), occupancy
  may drop, regressing performance.
- The tail kernel's current grid is (512/4, L, 1) with 256-thread TGs. The
  GEMV would need different parallelism (per-output-row, not per-element).
  This is a fundamental conflict.

### Implementation Approach
1. Restructure the tail kernel into two phases within a single dispatch:
   - Phase 1: A subset of threadgroups computes the shared down GEMV
     (one TG per output row, 2048 TGs). Each TG reads the shared activated
     intermediate [512] and shared down weight [2048, 64] NVFP4, computes
     one output row [1], writes to a temporary buffer in threadgroup memory.
   - Phase 2: ALL threadgroups do the original tail kernel work, reading
     the shared down output from threadgroup memory (or device memory if
     the two phases use different TG counts).
   - This requires either (a) a single grid with different TG assignments
     (complex) or (b) a two-kernel dispatch with a barrier (not possible in
     Metal within a single dispatch).
2. Simpler approach: add the shared down GEMV as an additional output channel
   of the tail kernel. The tail kernel currently writes [1, L, 2048]. If the
   kernel also computes the shared down GEMV and adds it inline, each TG
   that processes output element [row, col] also computes the shared down
   contribution for that element. This requires each TG to read the shared
   activated intermediate and shared down weight — but the shared down GEMV
   for element [row, col] needs the full 512-element intermediate, which
   each TG doesn't have (each TG processes 4 columns).
   - This is NOT feasible without restructuring the kernel's parallelism.

### Bit-Exactness Argument
- The shared down GEMV uses `laguna_nvfp4_qdot_16` (same as the decode path).
  The accumulation order is the same per output element.
- The tail kernel's weighted reduction and residual add are unchanged.
- Bit-exact: YES, IF the GEMV uses the same qdot function and accumulation
  order as the separate down dispatch.

### M5 Safety Analysis
- Custom kernel modification. Must use scalar `simd_sum` (no forbidden
  constructs).
- Risk: HIGH. The kernel restructure is complex and may regress due to
  occupancy or parallelism mismatch. The "custom GEMM can't beat MLX" lesson
  applies — the separate down dispatch uses MLX's optimized GEMV, while the
  fused version uses a custom GEMV that may be slower.
- The dispatch savings (~97.5 µs) may not compensate for a slower GEMV.

### Budget Estimate
- ~500-1000 B (kernel source restructure + new input parameters).
  Within 21.7 KB LRM headroom.

### Target: Prefill (25% of score)
Eliminates 39 shared expert down dispatches. High implementation complexity.
Consider only if Ideas 1-2 don't yield enough prefill speedup.

---

## Priority Ranking

| # | Idea | Score Axis | Est. Gain | Bytes | Risk | Priority |
|---|------|-----------|-----------|-------|------|----------|
| 3 | JIT Kernel Variant Consolidation | Both | M5 fix + dispatch | ~0 (net neg) | LOW | **CRITICAL** |
| 2 | Unsorted gatherQuantizedMM | Prefill 25% | ~2.2% total | ~250 B | LOW-MED | **HIGH** |
| 1 | Fuse Input RMSNorm into QKV | Prefill 25% | ~0.6% total | ~500 B | LOW (compile) | **HIGH** |
| 5 | MLX.compile Shared Expert Fusion | Prefill 25% | ~1.1% total | ~300 B | MEDIUM | **MEDIUM** |
| 4 | TG Memory Bank Conflict Fix | Decode 75% | ~0.8% total | ~80 B | LOW | **MEDIUM** |
| 6 | Indexed Metadata LUT for g_proj | Decode 75% | ~0.01% total | ~300 B | LOW | **LOW** |
| 7 | Custom Flash-Attention SDPA | Prefill 25% | ~0.6% total | ~2 KB | MEDIUM | **LOW** |
| 8 | Fuse Shared Down into Tail | Prefill 25% | ~2.2% total | ~800 B | HIGH | **LOW** |

## Recommended Assignment Order

1. **Idea 3** (JIT consolidation) — CRITICAL for M5 build reliability. Without
   M5 passing, no submission can be scored. This is the highest-priority
   systems-level fix. Assign to the most experienced student.
2. **Idea 2** (unsorted gatherQuantizedMM) — 0-byte env flag change, quick to
   test, could yield ~2.2% total. Can be tested immediately on any student host.
3. **Idea 1** (fuse RMSNorm into QKV) — Approach A (MLX.compile) is 0-byte and
   can be tested immediately. If MLX.compile doesn't fuse, try Approach B.
4. **Idea 4** (TG memory bank conflict) — Small, safe, quick to implement and
   test. Can run concurrently with prefill ideas on a different host.
5. **Idea 5** (MLX.compile shared expert) — Requires load-time weight fusion
   + compiled function wrapper. Medium complexity.
6. **Idea 6** (indexed LUT for g_proj) — Run the dedup census first. If dedup
   ratio is low, skip.
7. **Idea 7** (custom flash-attention) — Needs profiling first to confirm MLX
   SDPA materializes the full score matrix. High complexity, uncertain gain.
8. **Idea 8** (fuse shared down into tail) — High complexity, defer unless other
   prefill ideas don't yield enough.

## Key Insight

The **JIT compile-storm** (Idea 3) is the most critical issue: 25+ consecutive
M5 build failures mean no optimization can be scored. Fixing this is a
prerequisite for all other work. The consolidation approach (function
constants) is both a build fix AND a performance optimization (fewer kernel
objects = faster dispatch setup).

For **prefill speedup**, Ideas 1+2 together could yield ~2.8% total score
with low risk. The prefill dispatch audit reveals ~6 extra dispatches per
layer vs decode, and the prefill seed is charged to the decode window, so
prefill improvements compound into decode score.

For **decode speedup**, the remaining bandwidth reduction opportunities are
small (most have been exhausted). The threadgroup memory bank conflict fix
(Idea 4) is the only remaining decode idea with a plausible mechanism, but
its impact is bounded by the kernel's threadgroup memory access fraction.

The **gap to #1** (~0.86%) can be closed by a combination of: M5 build fix
(unlocks scoring), prefill dispatch elimination (~2.8% from Ideas 1+2), and
decode micro-optimization (~0.8% from Idea 4). Together, these could close
the gap if the M5 build fix is successful and the prefill ideas hold up.
