# Fresh Research Ideas — 2026-08-07 v7

## Budget Constraints (verified from CURRENT_RESEARCH_STATE)
- LRM: 502,603 / 524,288 B = 21,685 B headroom
- Total surface: 2,934,676 / 3,000,000 B = 65,324 B headroom
- Per-file cap: 524,288 B
- Growth cap per review: 262,144 B

## CRITICAL CORRECTION: Grid Over-Dispatch Finding is WRONG
The task brief confirms MLX's MLXFast API uses
`dispatchThreads(gridSize, threadgroupSize)` where grid = TOTAL THREADS, not
threadgroups. The `* threadGroupSize` multiplier in grid expressions is
CORRECT and intentional. PR #333 (grid over-dispatch fix) will likely regress
or no-op. All ideas below assume the current grid expressions are correct.

## Verified Dead Ends (confirmed in this analysis)
- **Shared SwiGLU QMV gate/up scale halving** — ALREADY DONE. Kernel
  `lagunaSharedSwiGLUQMVRows1Kernel` (L6776-6855) already has
  `scale_row_bytes = 64`, indexes by `lane / 2`, and handles escape bytes.
  The bandwidth audit (Opportunity 1) was based on an older PR #180 commit.
- **Gate-softplus 4× scale/bias dedup** — ALREADY DONE. The kernel
  `lagunaGateSoftplusSource` (L4317-4367) already uses `simd_shuffle` to
  broadcast scales/biases (L4339-4341).
- **Attention mask elimination for decode** — `makeMask` returns `.none`
  for n==1 (L164-165 KVCache.swift). No GPU dispatch for decode masks.
- **Final RMSNorm → LM head fusion** — Exhausted (PR #276). Cross-TG barrier
  cost (3 barriers × 6272 TGs) exceeds dispatch savings.

## Architecture Reference
- 40 layers: layer 0 = dense BF16 MLP, layers 1-39 = sparse MoE (NVFP4)
- Attention: 10 full-attention + 30 sliding-window layers
- Decode: 75% of score. Prefill: 25% of score.
- Score = decode_speedup^0.75 × prefill_speedup^0.25
- M5: 40 GPU cores, 128 GB unified memory, ~651.8 GB/s, ~89% GPU util
- M5 is BANDWIDTH-BOUND. Only bandwidth reduction or dispatch elimination helps.

---

## Idea 1: Prefill Expert Halved Scales via qmm_nax kHalvedScales ★★★★

### Causal Question
Does adding NVFP4 halved-scale (group-32 + escape byte) support to the vendored
`qmm_nax` / `gather_qmm_nax` kernel reduce prefill MoE bandwidth enough to
speed up the prefill phase?

### Target Evidence
- `lagunaPrefillSharedHalvedEnabled = false` (L227): disabled because "qmm_nax
  reverted to pre-PR#243 state (no kHalvedScales)."
- The halved scales tensors are ALREADY BUILT at load time:
  - Shared: `_halvedFusedGateUpScales` (L8338), `_prefillGateUpFullScales` (L8341)
  - Routed: `_halvedFusedRoutedGateUpScales` (L9993), `_halvedRoutedDownScales` (L10016)
- The prefill shared halved path (L8611-8625) calls `quantizedMM` with
  `groupSize: 32` and the [N+1, K/32] scales layout, but is gated by the
  disabled flag.
- The prefill routed path (L9848) uses `useHalved = false` (L9847).
- Editable vendor files include `fp_quantized_nax.metal`, `fp_quantized_nax.h`,
  `fp_quantized_nax.cpp`, `quantized_nax.cpp` — all in the editable surface.
- The `qmm_nax` dispatch (L477-590 quantized.cpp) already templates on
  `group_size` and supports group-32 (mxfp4). The NVFP4 e4m3 scale decode is
  the same regardless of group_size (L44-47 fp_quantized_nax.h).

### Expected Signal
- Shared expert gate/up: ~2.43 MiB/step bandwidth saved (39 layers × 131 KB)
- Routed expert gate/up: ~15.7 MiB/step saved (256 experts × 32 B/expert/layer)
- Routed expert down: ~7.8 MiB/step saved
- Total: ~26 MiB/step at M5 651.8 GB/s ≈ 40 µs per prefill step
- Prefill total ~1.1 ms, so ~3.6% prefill speedup = ~0.9% total score
- The `qmm_nax` static Laguna shapes (L508-514) include K=2048,N=1024 and
  K=512,N=2048 — the shared expert gate/up and down shapes. The static
  path may already be the dominant kernel for these shapes.

### Implementation Approach
1. **fp_quantized_nax.h**: Add an escape-aware scale reader. For NVFP4
   group-32 mode with the [N+1, K/32] layout, the kernel reads scales at
   `scales[row * stride + group]` for rows < N. For row 0, group 0, the
   second 16 elements need the escape byte, not the halved scale. Add a
   function-constant `bool use_escape` (default false) and an escape buffer
   input. When `use_escape` is true and `(row == 0 && group == 0)`, the
   second half of the group uses the escape scale.
2. **quantized.cpp**: In `qmm_nax` (L477-590) and `gather_qmm_nax` (L612+),
   detect the [N+1, K/32] scales shape (scales.dim(0) == N+1) and pass
   `use_escape = true` plus the escape bytes from row N.
3. **LagunaRuntimeModel.swift**: Set `lagunaPrefillSharedHalvedEnabled = true`
   (L227), set `useHalved = true` (L9847) and `useHalvedDown = true` (L9870),
   wire the halved scales + escape into the `gatherQuantizedMM` calls.
4. **fp_quantized_nax.cpp**: Update the generated kernel source twin to match.

### Bit-Exactness Argument
- The halved scales exploit the NVFP4 pairwise-constancy invariant:
  `scale[2k] == scale[2k+1]` for k >= 1 (quantizer bug in fp_quantized.h).
- For k = 0, `scale[0]` may differ from `scale[1]`. The escape stores
  `scale[1]`.
- With groupSize=32, the kernel reads one scale per 32 elements. For groups
  k >= 1, the halved scale = full[2k] = full[2k+1] — identical to group-16.
  For group 0, the first 16 elements use `full[0]` (halved[0]) and the second
  16 use `full[1]` (escape). The kernel must apply the correct scale to each
  16-element sub-group.
- The GEMM accumulation order is UNCHANGED — only the dequantized weight
  values change, and they change to the EXACT same values as the full
  group-16 path. No reduction order perturbation.

### M5 Safety Analysis
- Scale reading is a scalar `uint8_t` load + `fp8_e4m3` decode — already
  used in the nax kernel for group-16 NVFP4.
- No `simd_sum(vec)`, `dot(float4)`, or `*(thread float4*)` casts.
- The escape check is a per-threadgroup conditional (row == 0), uniform
  across the TG — no per-lane divergence.
- The static Laguna shape path (L508-514) already specializes these exact
  dimensions. Adding escape support to the static path is a template
  parameter, not a new kernel.
- RISK: The nax kernel uses simdgroup matrix operations (`simdgroup_matrix`).
  The scale is applied in the weight-loading stage, not the accumulation
  stage. Changing the loading stage does not affect the matrix multiply
  accumulation order.

### Budget Estimate
- ~800-1500 B in fp_quantized_nax.h (escape-aware scale loader + function constant)
- ~200-400 B in quantized.cpp (escape detection + buffer binding)
- ~300-500 B in fp_quantized_nax.cpp (generated twin)
- ~200 B in LagunaRuntimeModel.swift (flag flips + escape wiring)
- Total: ~1.5-2.6 KB. Well within 21.7 KB LRM headroom and 65 KB total.
  Note: vendor file changes count toward the total surface budget, not LRM.
  Vendor files have their own per-file 524 KB cap.

---

## Idea 2: Decode AsyncEval Schedule Re-measurement (at:off) ★★★

### Causal Question
Is the current asyncEval decode schedule (at:0,1,7,15,23,31,39) HURTING
decode performance on the current optimized base? Notes/52 measured
ladder8 = 1.000 (baseline) and the current schedule at 1.0170 (1.7% worse).
Has the heavily-fused current base made asyncEval counterproductive?

### Target Evidence
- L613-615: "MEASURED (notes/52, 66 runs, all passed): ladder8=1.000,
  ladder6=1.0064, ladder2=1.0169, ladder1=1.0178, at:1,7,15,23,31,39=1.0170."
- The current default (L619) is `at:0,1,7,15,23,31,39` — 7 fires.
- Ladder8 (5 fires, at:7,15,23,31,39) measured at 1.000 — the SAME as no
  asyncEval.
- The current schedule adds 2 extra fires (at:0 and at:1) which cost 1.7%.
- The current base has 36+ fused kernels that didn't exist when notes/52
  was measured. With more fusion, there are fewer independent ops between
  asyncEval boundaries, so the scheduler round-trip cost dominates.

### Expected Signal
- `DARKBLOOM_DECODE_ASYNC_STAGE=off` should measure ~1.7% decode speedup
  if the old measurement holds.
- Even a 0.5-1.0% decode speedup = 0.375-0.75% total score.
- If asyncEval=off is neutral, the current schedule's extra fires cost
  nothing and there's no regression risk from trying.

### Implementation Approach
- Zero code changes. Set `DARKBLOOM_DECODE_ASYNC_STAGE=off` (or `0`).
- Run `./benchmark.sh --local-iterate` with the env var.
- Compare candidate vs fresh baseline on the same host.
- If positive, also test `ladder8` (at:7,15,23,31,39) and `at:7,15,23,31,39`
  (pure ladder8 without the layer-0 front rung).

### Bit-Exactness Argument
- L609-611: "asyncEval adds no operation, cache row, dtype boundary or
  token — it only enqueues already-constructed work earlier."
- Disabling it changes ONLY when work is enqueued, not what work is done.
- Every token is bit-identical.

### M5 Safety Analysis
- Env-var knob only. No kernel changes. No Metal code.
- 100% safe.

### Budget Estimate
- 0 bytes.

---

## Idea 3: Prefill AsyncEval Stride Sweep ★★☆

### Causal Question
Is prefill asyncEval stride 1 (current default, L671-676) optimal on the
current base, or would a sparser stride (2, 4, 8) reduce scheduler
round-trips enough to speed up prefill?

### Target Evidence
- L658-670: Stride 1 measured 1.88526 vs base 1.87782 (+0.40%) — rejected
  because a larger win promoted mid-queue. The base has since changed
  significantly (36+ fusions, NAX gate fix).
- Stride 1 fires after EVERY layer (40 fires). Each fire is a scheduler
  round-trip. With 40 layers, that's 40 round-trips for a ~400-op graph.
- Stride 2 (20 fires), stride 4 (10 fires), stride 8 (5 fires) trade
  earlier enqueueing for fewer round-trips.
- The prefill phase includes the 512-token seed prefill charged to the
  decode window, so prefill speedup also helps decode score.

### Expected Signal
- Prefill ~1.1 ms. 40 scheduler round-trips at ~5-10 µs each = 200-400 µs.
  Stride 2 saves ~100-200 µs = ~9-18% prefill = ~2.3-4.5% total.
  (These are upper bounds; MLX may overlap scheduling with GPU work.)
- Any positive result on prefill is meaningful since prefill has its own
  0.95 floor.

### Implementation Approach
- Zero code changes. Sweep `DARKBLOOM_PREFILL_ASYNC_LADDER` = 2, 4, 8.
- Run `./benchmark.sh --local-iterate` for each value.
- Compare against stride 1 (current default) on the same host.

### Bit-Exactness Argument
- Same as Idea 2: asyncEval only changes enqueue timing, not computation.

### M5 Safety Analysis
- Env-var knob only. 100% safe.

### Budget Estimate
- 0 bytes.

---

## Idea 4: LM Head Coarse + Exact Kernel Threadgroup Doubling ★★☆

### Causal Question
Does doubling the threadgroup size (halving threadgroup count) for the
LM head coarse and exact kernels reduce dispatch overhead enough to
improve decode step time?

### Target Evidence
- Coarse kernel (L943-944): `grid: (vocab / 16 * 512, 1, 1)`,
  `threadGroup: (512, 1, 1)`. Threadgroups = 100352/16 = 6272. Each TG
  has 512 threads = 16 simdgroups, processing 16 rows (1 simdgroup/row).
- Exact kernel (L975-976): `grid: (vocab / 32 * 256, 1, 1)`,
  `threadGroup: (256, 1, 1)`. Threadgroups = 100352/32 = 3136. Each TG
  has 256 threads = 8 simdgroups, processing 32 rows (4 rows/simdgroup).
- M5 has 40 cores. 6272 TGs = 157 per core; 3136 = 78 per core. Both are
  already well above the core count, so the GPU is saturated. Halving
  TG count reduces dispatch overhead but doesn't change saturation.
- Dispatch overhead per kernel: ~10-20 µs. Four LM head kernels × 128
  decode steps = 512-1024 dispatches. Halving two of them saves ~2.5-5 ms
  over the full decode window (~1664 ms total) = ~0.15-0.3%.

### Expected Signal
- Small but measurable: 0.15-0.3% decode speedup.
- If threadgroup memory (TG shared arrays) benefits from larger TGs
  (better L1 reuse of the input vector x), the gain could be larger.
- The input vector x is 4 KB (2048 BF16). With 16 rows/TG (coarse), each
  TG reads 16 × 4 KB = 64 KB of x, but x is only 4 KB — fully L1 cached.
  With 32 rows/TG, x is still 4 KB — no change.

### Implementation Approach
1. **Coarse kernel** (L943): Change to `grid: (vocab / 32 * 1024, 1, 1)`,
   `threadGroup: (1024, 1, 1)`. Each TG has 32 simdgroups, processing 32
   rows. Modify the row index: `row = threadgroup_position_in_grid.x * 32 +
   simdgroup_index_in_threadgroup`.
2. **Exact kernel** (L975): Change to `grid: (vocab / 64 * 512, 1, 1)`,
   `threadGroup: (512, 1, 1)`. Each TG has 16 simdgroups, processing 64 rows.
   Modify: `base = tgid * 64 + sgid * 4`.
3. Verify M5 max threadgroup size (likely 1024 threads).

### Bit-Exactness Argument
- Same per-row computation, same per-simdgroup reduction. Only the number
  of rows per TG changes. No reduction order changes (simd_sum within each
  simdgroup is unchanged; cross-simdgroup communication is unchanged since
  each simdgroup independently writes its rows).

### M5 Safety Analysis
- Scalar `simd_sum` (already used). No forbidden constructs.
- Larger threadgroups may hit register limits or threadgroup memory limits.
  The coarse kernel uses no threadgroup memory. The exact kernel uses
  threadgroup memory for `down_outputs` (fused refined kernel) — doubling
  the size doubles the TG memory. Need to verify M5's 32 KB TG memory limit.
- RISK: LOW if TG memory fits. MEDIUM if it doesn't.

### Budget Estimate
- ~100-200 B in LagunaLmHeadPrune.swift (grid/threadgroup constants + row
  index formula changes).
- Within 19 KB LRM headroom.

---

## Idea 5: Prefill addMM Enablement Re-measurement ★★☆

### Causal Question
Does enabling `DARKBLOOM_PREFILL_ADDMM=1` (currently OFF) speed up prefill
by fusing the attention output projection with the residual add into a
single `addMM` dispatch?

### Target Evidence
- L10515-10522: `prefillAddMMEnabled` requires `DARKBLOOM_PREFILL_ADDMM == "1"`
  (default OFF).
- When enabled (L6455-6462): `return addMM(residual, output, wo.weight.T)`
  — fuses matmul + residual add into one dispatch.
- When disabled: `return wo(output)` (separate matmul) + later residual add.
- The prefill attention output projection is a BF16 matmul [L, nHeads×D] ×
  [nHeads×D, hiddenSize] for each of 40 layers. The residual add is a separate
  elementwise dispatch. addMM eliminates 1 dispatch × 40 layers = 40 dispatches
  per prefill.
- The flag also passes `prefillResidual` to the attention function (L10530),
  enabling the fused path.

### Expected Signal
- 40 dispatch eliminations per prefill at ~10 µs each = ~400 µs.
- Prefill ~1.1 ms, so ~36% dispatch overhead reduction.
- But addMM may have different tiling than separate matmul+add — could be
  slower if MLX's addMM tiling is worse.
- Previous measurement status unknown — the flag exists but is default OFF,
  suggesting it was measured and didn't help. But the base has changed.

### Implementation Approach
- Zero code changes. Set `DARKBLOOM_PREFILL_ADDMM=1`.
- Run `./benchmark.sh --local-iterate`.
- Compare against default (OFF) on the same host.

### Bit-Exactness Argument
- `addMM(residual, output, wo.weight.T)` computes `residual + output × wo.weight.T`.
  This is the same computation as `wo(output)` followed by `residual + result`.
- MLX's `addMM` uses the same GEMM kernel as `matmul`; the add is fused into the
  epilogue. The matmul accumulation order is unchanged.
- The residual add rounds to BF16 once (in the fused epilogue) vs. once (in
  the separate add). Same rounding.

### M5 Safety Analysis
- Env-var knob. Uses MLX's built-in `addMM`. No custom kernels.
- RISK: The addMM path bypasses the gate product (L6453-6464: the gate is
  applied to `output` before `addMM`). The `output` variable already has the
  gate applied. So `addMM(residual, gated_output, wo.weight.T)` is correct.
- 100% safe.

### Budget Estimate
- 0 bytes.

---

## Idea 6: Routed+Shared Down Residual Kernel outputs_per_simd 8→4 ★★☆

### Causal Question
Does reducing `outputs_per_simd` from 8 to 4 in the fused routed+shared
down+residual kernel improve decode performance by reducing register
pressure and increasing threadgroup count for better latency hiding?

### Target Evidence
- L7888: `constexpr uint outputs_per_simd = 8` in
  `lagunaRoutedSharedDownResidualKernel`.
- The kernel has 9 simdgroups (8 routed + 1 shared), each handling 8 output
  rows. Threadgroup = 288 threads (9 × 32). Grid = 2048/8 × 288 = 256 TGs.
- PR #89 (NEGATIVE_RESULTS L20-26) tested 4→8 on the STANDALONE shared down
  kernel and regressed +2.39% due to register pressure. The FUSED kernel
  already uses 8. Going to 4 is the REVERSE direction — fewer registers,
  more TGs.
- The negative result's lesson: "The down kernel is weight-bandwidth-bound,
  not input-bandwidth-bound." More TGs with fewer registers may not help
  if bandwidth is saturated. BUT — more TGs = more concurrent memory
  requests = better latency hiding on a bandwidth-bound kernel.
- Current: 256 TGs ÷ 40 cores = 6.4 TGs/core. With 4: 512 TGs = 12.8/core.
  This doubles the concurrent TG count, potentially improving memory-level
  parallelism.

### Expected Signal
- If bandwidth-bound with sufficient MLP: neutral or slight regression
  (same bandwidth, more dispatch overhead).
- If latency-hiding-limited: 2-5% decode speedup from doubled TG count.
- The kernel runs once per sparse layer (39) per decode step. It's the
  single largest kernel in the decode MoE path.

### Implementation Approach
1. In the kernel source (L7888): change `outputs_per_simd = 8` to `4`.
2. In the dispatch (L8049): change `grid: (hiddenSize / 8 * 288)` to
   `grid: (hiddenSize / 4 * 288)`. Threadgroup stays at 288.
   New threadgroups = 2048/4 = 512.
3. The threadgroup barrier at L7959 and the reduction at L7961-7980
   remain unchanged — `outputs_per_simd` is used in the loop bounds and
   the `down_outputs` array size. With 4, the array is half the size.
4. The reduction loop (L7963-7972) iterates over `routed_experts` (8),
  not `outputs_per_simd`, so it's unaffected.

### Bit-Exactness Argument
- Each simdgroup still computes the same rows independently. The reduction
  across simdgroups (via threadgroup memory + barrier) is unchanged — it
  sums the same expert outputs in the same order.
- The per-row dot product (`laguna_nvfp4_qdot_16`) is unchanged.
- The BF16 rounding sequence (`bfloat(result[row])`, `bfloat(product)`,
  `bfloat(routed_total)`, `bfloat(r2)`) is identical per row.
- Only the mapping of rows to simdgroups changes — row `r` is still computed
  by exactly one simdgroup with the same K-loop.

### M5 Safety Analysis
- Uses scalar `simd_sum` (already present at L7947). No forbidden constructs.
- The threadgroup memory `down_outputs` shrinks from 9×8=72 to 9×4=36 BF16
  values = 72 B. Well within limits.
- Register pressure: 8→4 result arrays (4 floats each) = 16→8 floats saved.
  The `input_values[16]` array is unchanged. Net register reduction.
- RISK: LOW. The change is a single constexpr + grid expression.

### Budget Estimate
- ~50-100 B (change two constants + grid expression).
- Within 19 KB LRM headroom.

---

## Idea 7: Prefill Compiled attentionGateProjection Multi-Token Extension ★★☆

### Causal Question
Can the compiled `attentionGateProjection` fusion (currently decode-only via
`MLXHardwareInfo.isCompiledDecodeSupported` and `L == 1` guard) be extended
to prefill (L > 1), eliminating the separate gate-product-softplus dispatch
for 40 layers per prefill?

### Target Evidence
- L6421-6426: `attentionGateProjection` is gated by `L == 1` — decode only.
- For prefill, the path is: `lagunaGateProductSoftplusMultiToken` (1 dispatch,
  L6433-6437) → `wo(output)` (1 dispatch, L6464). Total: 2 dispatches.
- The compiled `attentionGateProjection` fuses gate product + output projection
  into 1 dispatch. If it works for L > 1, it eliminates 1 dispatch × 40 layers.
- The prefill o-proj is a BF16 matmul (not quantized for layers using the
  compiled path), so the compiled fusion should work if MLX supports multi-token.

### Expected Signal
- 40 dispatch eliminations at ~10 µs each = ~400 µs per prefill.
- Prefill ~1.1 ms, so ~36% dispatch overhead reduction.
- But `attentionGateProjection` may not support multi-token (the guard
  suggests it's decode-specific). If it doesn't, the idea is dead.

### Implementation Approach
1. Check `MLXHardwareInfo.isCompiledDecodeSupported` — if true on M5, the
   compiled path may support multi-token with a shape guard change.
2. Remove the `L == 1` guard at L6423 (or add a separate `L > 1` path).
3. Verify the compiled kernel handles `[1, L, nHeads * headDim]` input shapes.
4. If it doesn't work, try the `addMM` + pre-gated approach: compute the gated
   output first (1 dispatch via `lagunaGateProductSoftplusMultiToken`), then
   use `addMM(residual, gated, wo.weight.T)` — but this requires the residual
   to be available, which it is when `DARKBLOOM_PREFILL_ADDMM=1`.

### Bit-Exactness Argument
- `attentionGateProjection(output, gate, wo.weight)` computes
  `(output * softplus(gate)) @ wo.weight.T` — the same as the separate
  gate product + matmul.
- MLX's compiled kernel applies the same BF16 rounding boundaries.
- If the compiled kernel is bit-exact for L=1, it should be bit-exact for L>1
  (same per-element math, same matmul tiling).

### M5 Safety Analysis
- Uses MLX's built-in compiled function. No custom Metal kernels.
- RISK: MEDIUM. The compiled path may not support multi-token shapes, or may
  produce different tiling that changes accumulation order. Must verify with
  `LagunaUpstreamEquivalence` test.
- If it doesn't work for multi-token, fall back to Idea 5 (addMM enablement).

### Budget Estimate
- ~100-200 B (guard change + possible shape adaptation).
- Within 19 KB LRM headroom.

---

## Idea 8: Prefill Dense Layer-0 Gate/Up+SiLU+Down Triple Fusion ★☆☆

### Causal Question
Can the dense layer-0 prefill path (currently 3 dispatches: gate/up matmul,
SiLU product, down matmul) be reduced to 2 by fusing the SiLU product into
a custom BF16 GEMM epilogue?

### Target Evidence
- Layer 0 is the only dense (BF16) MLP. Prefill path (L8660+):
  1. `matmul(x, fusedWeight.T)` — gate/up fusion (1 dispatch)
  2. `compiledSiluProduct(gate, up)` — SiLU activation (1 dispatch)
  3. `downProj(activated)` — down projection (1 dispatch)
- Total: 3 dispatches. The SiLU product is a simple elementwise op.
- Decode already fuses all three into 2 dispatches (`lagunaDenseGateUpSwiGLU`
  + `lagunaDenseDownResidual`). Prefill can't use these (they're single-token).
- Layer 0 is 1/40 of prefill, so the gain is bounded at ~2.5% of prefill.

### Expected Signal
- 1 dispatch eliminated × 1 layer = ~10 µs. Prefill ~1.1 ms.
- ~0.9% prefill speedup = ~0.23% total score.
- Very small. Only worth it if the implementation is trivial.

### Implementation Approach
- Build a custom multi-token BF16 GEMM that applies SiLU to the gate/up output
  in its epilogue, writing the activated result directly. Then use stock
  `downProj` (matmul) for the down projection.
- Alternatively: use `matmul` for gate/up (1 dispatch), then a custom kernel
  that fuses SiLU + down matmul. But a custom GEMM for [L, 8192] × [8192, 2048]
  can't beat MLX's optimized GEMM (negative results PR #317, #325).

### Bit-Exactness Argument
- SiLU(gate) * up must round to BF16 once (same as `compiledSiluProduct`).
- A custom kernel would need to reproduce MLX's `compiledSiluProduct` rounding
  exactly: `bfloat(sigmoid(gate) * gate * up)` with the same intermediate casts.

### M5 Safety Analysis
- Custom BF16 GEMM for [L, 8192] × [8192, 2048] — risk of tiling degradation
  (same issue as PR #325 which regressed +1.2%).
- M5 SAFE if using scalar simd_sum and standard matmul patterns.
- RISK: HIGH for the GEMM. The SiLU-only fusion (elementwise) is safe but
  only saves 1 dispatch for 1 layer.

### Budget Estimate
- ~2000-4000 B for a custom multi-token GEMM kernel.
- Within budget but low expected value.

---

## Priority Ranking

| # | Idea | Score Axis | Est. Gain | Bytes | Risk | Priority |
|---|------|-----------|-----------|-------|------|----------|
| 1 | Prefill Expert Halved Scales via qmm_nax | Prefill 25% | ~0.9% total | ~2.6 KB | MEDIUM-HIGH | **HIGH** |
| 2 | Decode AsyncEval=off Re-measurement | Decode 75% | ~1.3% total | 0 | LOW | **HIGH** |
| 3 | Prefill AsyncEval Stride Sweep | Prefill 25% | ~0.6% total | 0 | LOW | **MEDIUM** |
| 5 | Prefill addMM Enablement | Prefill 25% | ~0.3% total | 0 | LOW | **MEDIUM** |
| 6 | Down Residual outputs_per_simd 8→4 | Decode 75% | ~0.4% total | ~80 B | LOW | **MEDIUM** |
| 4 | LM Head TG Doubling | Decode 75% | ~0.2% total | ~150 B | LOW | **LOW-MEDIUM** |
| 7 | Compiled Gate+O-proj Multi-Token | Prefill 25% | ~0.3% total | ~150 B | MEDIUM | **LOW-MEDIUM** |
| 8 | Dense Layer-0 Triple Fusion | Prefill 25% | ~0.2% total | ~3 KB | HIGH | **LOW** |

## Recommended Assignment Order

1. **Idea 2** (asyncEval=off) — 0 bytes, immediate, highest expected ROI.
   Can be tested by any student with a running benchmark.
2. **Idea 1** (qmm_nax halved scales) — highest bandwidth savings, requires
   careful vendor kernel work. Assign to the most experienced student.
3. **Idea 3** (prefill asyncEval stride) — 0 bytes, can run concurrently
   with Idea 2 on a different host.
4. **Idea 5** (addMM enablement) — 0 bytes, can run concurrently.
5. **Idea 6** (down residual outputs_per_simd) — small code change, quick
   to implement and test.
6. **Idea 4** (LM head TG doubling) — small code change, verify M5 TG limit.
7. **Idea 7** (compiled gate multi-token) — needs investigation first.
8. **Idea 8** (dense layer-0 triple fusion) — low value, defer.

## Key Insight
The zero-byte measurement ideas (2, 3, 5) can be dispatched immediately and
concurrently. They test whether the current asyncEval schedule and dispatch
patterns are still optimal on a base that has changed dramatically since
their original measurement. The old measurements predate 36+ kernel fusions
and the NAX gate fix. A fresh measurement is cheap and may reveal that
previously-measured knobs now have different optima.

Idea 1 is the highest-value code change: it unlocks ~26 MiB/step of prefill
bandwidth savings that are already half-implemented (halved tensors built,
flag disabled). The implementation risk is in the vendored nax kernel, but
the scale-reading change does not perturb the GEMM accumulation order.
