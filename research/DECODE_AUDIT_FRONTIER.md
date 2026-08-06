# DECODE AUDIT FRONTIER — Laguna XS 2.1 NVFP4

Comprehensive read-only audit of `Sources/MLXFastModel/LagunaRuntimeModel.swift` (11,176 lines)
and related editable files. All line numbers refer to `LagunaRuntimeModel.swift` unless
otherwise noted.

## Model Constants (from LagunaConfig.swift)

| Parameter | Value |
|---|---|
| vocabSize | 100,352 |
| hiddenSize | 2,048 |
| numHiddenLayers | 40 |
| numKeyValueHeads | 8 (GQA) |
| headDim | 128 |
| fullAttentionHeads | 48 (layers 0, 4, 8, ..., 36) |
| slidingAttentionHeads | 64 (30 layers) |
| slidingWindow | 512 |
| numExperts | 256 |
| numExpertsPerTok | 8 |
| moeIntermediateSize | 512 |
| sharedExpertIntermediateSize | 512 |
| layer 0 | Dense MLP (intermediate 8,192) |
| layers 1-39 | Sparse MoE (256 routed + 1 shared, each 512 intermediate) |

---

## 1. DECODE DISPATCH AUDIT (L=1, steady state)

### 1a. Per-step global dispatches (outside layer loop)

| Dispatch | Lines | Count | Notes |
|---|---|---|---|
| Embedding + RoPE atlas | L10444 | 1 | `lagunaDecodeEmbeddingRoPEAtlasKernel`: fused embedding gather + full/sliding RoPE angle row extraction. Only if `lagunaRoPEAngleAtlasEnabled`. |
| Full attention mask | L10700 | 0 | `n=1` → `.none`, no dispatch |
| Sliding attention mask | L10701 | 0 | `n=1` → `.none`, no dispatch |
| Final RMSNorm | L10808 | 1 | `model.norm(hidden)` — stock RMSNorm, 1 dispatch |
| LM head (pruned) | L10824 | 4 | Coarse + argmax-stage1 + threshold + exact (see §2) |
| **Total global** | | **~6** | |

### 1b. Per-layer dispatches — Full-attention MoE layer (layers 4, 8, ..., 36: ~10 layers)

#### Attention block (L10193 → selfAttn callAsFunction)

| # | Operation | Lines | Dispatches | Notes |
|---|---|---|---|---|
| 1 | Fused Norm + Affine QKV + Gate | L5544 / L5564 | 1 | `lagunaNormAffineQKV` (INT8 affine) OR `lagunaDecodeNVFP4QKVR1` (NVFP4). Fuses input RMSNorm + QKV projection + gate projection into 1 dispatch. |
| 2 | Fused QK-Norm + YaRN RoPE + cache write + SDPA | L5801 | 1 | `lagunaFullFusedAttention`: QK-norm + YaRN RoPE + K/V cache append + sdpa_vector. Replaces 4+ dispatches. |
| 3 | Gated Affine O-proj (INT8) | L5959 | 1 | `lagunaGatedAffineOProj`: softplus + gate×output + INT8 GEMV. 1 dispatch. |
| | **Attention total** | | **3** | |

#### MoE block (L10260 → sparse callAsFunction → forward)

| # | Operation | Lines | Dispatches | Notes |
|---|---|---|---|---|
| 4 | Residual + RMSNorm + Router GEMV | L10213 | 1 | `lagunaResidualRMSNormRouter`: fuses post-attn residual add + RMSNorm + router [256×2048] GEMV. |
| 5 | Router Top-8 selection | L9352 | 1 | `lagunaDecodeRouterTop8`: bitonic sort + top-8 + weight normalization. |
| 6 | Routed SwiGLU QMV (gate/up) | L9906/9928 | 1 | `lagunaRoutedSwiGLUQMVPacked` or `lagunaRoutedSwiGLUQMV`: NVFP4 QMV over 8 experts, gate/up fused, SwiGLU activation. |
| 7 | Shared SwiGLU QMV (gate/up) | L8087 | 1 | `lagunaSharedSwiGLUQMV`: NVFP4 QMV for shared expert gate/up + SwiGLU. (Issued inside `fusedSharedDownInputs` unless merged by PR #87.) |
| 8 | Routed+Shared Down+Residual | L9974 | 1 | `lagunaRoutedSharedDownResidualKernel`: 8-expert down GEMV + router-weighted reduce + shared down GEMV + residual add. Fuses ~5 stock ops into 1. |
| | **MoE total** | | **5** | |
| | **Layer total** | | **8** | |

### 1c. Per-layer dispatches — Sliding-attention MoE layer (30 layers)

Same as full-attention except:
- Dispatch #2 uses `lagunaSlidingFusedAttention` (L5775) instead of `lagunaFullFusedAttention`.
- Same 3 attention dispatches, 5 MoE dispatches = **8 per layer**.

### 1d. Per-layer dispatches — Layer 0 (Dense MLP)

| # | Operation | Lines | Dispatches | Notes |
|---|---|---|---|---|
| 1 | Fused Norm + Affine QKV + Gate | L5544 | 1 | Same as MoE layers (layer 0 is full-attention with 48 heads) |
| 2 | Fused Full Attention | L5801 | 1 | `lagunaFullFusedAttention` |
| 3 | Gated Affine O-proj | L5959 | 1 | `lagunaGatedAffineOProj` |
| 4 | Residual + RMSNorm (no router) | L10230 | 1 | `lagunaResidualRMSNorm` (no router since dense MLP) |
| 5 | Fused Dense GateUp SwiGLU | L7863 | 1 | `lagunaDenseGateUpSwiGLU` |
| 6 | Fused Dense Down + Residual | L8169/7939 | 1 | `lagunaDenseDownResidual` |
| | **Layer 0 total** | | **6** | |

### 1e. Total decode step dispatch count

| Component | Layers | Dispatches/layer | Subtotal |
|---|---|---|---|
| Layer 0 (dense, full-attn) | 1 | 6 | 6 |
| Full-attn MoE (layers 4,8,...,36) | 9 | 8 | 72 |
| Sliding-attn MoE | 30 | 8 | 240 |
| Global (embed+RoPE, final norm, lm_head) | — | — | ~6 |
| **Total per decode step** | | | **~324** |

This is already highly optimized. The original stock MLX path would have been
~30+ dispatches per layer (×40 = 1200+). Current is ~8/layer.

---

## 2. LM HEAD PATH

### Current implementation

The LM head is **BF16** `[100352, 2048]` (411 MB) — the largest single weight in the model.
It is **untied** (not tied to embeddings).

**Already optimized**: The `LagunaLmHeadPruner` (LagunaLmHeadPrune.swift) implements a
certified two-pass int5 coarse screen:

1. **Coarse pass** (L241-256): int5 GEMV over planar int5 copy (1344 B/row, or 1088 B/row
   with fused refinement). Reads ~109 MB instead of 411 MB.
2. **Argmax stage 1** (L259-265): reduction over coarse logits.
3. **Threshold** (L266-272): exact BF16 GEMV for winner row + threshold computation.
4. **Exact pass** (L273-288): BF16 GEMV for candidate rows only (typically very few).

**4 dispatches total**, but reads dramatically less weight data than stock.

### Opportunities

**OPP-2a: Fuse final RMSNorm into LM head coarse pass**
- Lines: L10808 (final norm) + LagunaLmHeadPrune.swift L241
- Current: 1 dispatch for `model.norm(hidden)` + 4 for pruner = 5 dispatches
- Proposed: Fuse the RMSNorm into the coarse kernel's first phase (the coarse kernel
  already reads the hidden vector `x` element-by-element for the GEMV; RMSNorm is a
  pass over the same 2048 elements before the dot products begin). The coarse kernel
  could normalize `x` in threadgroup memory before starting the GEMV accumulation.
- Savings: **1 dispatch** per decode step
- Risk: Numerical change — must reproduce exact RMSNorm rounding in the Metal kernel.
  The coarse kernel currently reads raw `x` values; it would need to compute
  `rsqrt(sum(x²)/2048 + 1e-6)` and multiply each element before the GEMV. The sum
  reduction is across 2048 elements (one threadgroup), feasible with simd_sum.
- Impact: **Low** — saves 1 dispatch but the RMSNorm over 2048 elements is cheap.
- Editable: Yes — LagunaLmHeadPrune.swift is in `Sources/MLXFastModel/`.

**OPP-2b: Quantize LM head to INT8 affine (group-32)**
- Lines: L10766 (lmHead declaration), L10880-10829
- Current: BF16 [100352, 2048] = 411 MB. The pruner reads ~109 MB via int5 coarse,
  but the exact pass still reads full BF16 rows for candidate blocks.
- Proposed: Apply group-32 affine INT8 quantization (the same envelope accepted for
  Q/K/V/O attention weights) to the lm_head weight. This would reduce the exact-pass
  BF16 GEMV reads and the stock fallback by 2×. The coarse int5 screen would still
  work on top.
- Risk: **Numerical change** — INT8 quantization changes logits values. The pruner's
  certificate is built on exact BF16; an INT8 weight would break the bit-identical
  guarantee. Would need a new certificate or acceptance of argmax-level differences.
  **This likely violates the correctness gate** unless the argmax token is preserved.
- Impact: **Medium** — 2× reduction in exact-pass weight reads, but only for the
  handful of candidate rows that pass the threshold.
- Editable: Yes, but **high risk** — may fail correctness gates.
- **Recommendation: Do NOT pursue** — the pruner already achieves the bandwidth
  reduction; INT8 would break the certified bit-exactness.

---

## 3. ATTENTION PATH

### Full-attention decode (layers 0, 4, 8, ..., 36)

Current path (3 dispatches):
1. **Fused Norm + QKV + Gate** (L5544): `lagunaNormAffineQKV` — input RMSNorm + INT8
   affine QKV projection + gate projection. 1 dispatch.
2. **Fused QK-norm + YaRN RoPE + cache append + SDPA** (L5801): `lagunaFullFusedAttention`
   — per-head Q/K RMSNorm, YaRN partial RoPE, K/V cache write, scaled dot-product
   attention. 1 dispatch. Replaces ~6 stock dispatches.
3. **Gated Affine O-proj** (L5959): `lagunaGatedAffineOProj` — softplus gate activation
   + gate×attention_output multiply + INT8 affine output projection. 1 dispatch.

### Sliding-attention decode (30 layers)

Same 3 dispatches, but dispatch #2 uses `lagunaSlidingFusedAttention` (L5775) which
attends over the 512-slot rotating ring instead of the growing standard cache.

### Opportunities

**OPP-3a: Fuse QKV projection into the fused attention kernel**
- Lines: L5544 (QKV dispatch) + L5801 (fused attention dispatch)
- Current: 2 separate dispatches — (1) norm+QKV+gate, (2) QK-norm+RoPE+SDPA+cache.
- Proposed: A single kernel that does input RMSNorm → QKV GEMV → per-head QK-norm
  → RoPE → cache write → SDPA → gate×output → O-proj GEMV. This would be a
  "mega-kernel" fusing the entire attention block.
- Savings: **2 dispatches** per layer × 40 layers = 80 dispatches/step
- Risk: **Extreme complexity** — the kernel would need to handle INT8 affine
  dequant, RMSNorm, RoPE, SDPA, and another GEMV in one threadgroup. Register
  pressure and threadgroup memory would be enormous. The QKV GEMV output is
  [1, 1, 48×128 + 2×8×128 + 48] = 8960 elements; the SDPA reads all 512 KV positions.
  Threadgroup memory for Q/K/V + intermediate would be ~40 KB, likely feasible
  but very complex.
- Impact: **Medium** — 2 dispatches saved, but dispatch overhead is ~2-5 μs each,
  so ~160-400 μs/step. At ~324 dispatches/step this is a ~0.5-1.2% reduction.
- Editable: Yes.
- **Recommendation: Low priority** — the complexity and risk of a mega-kernel is
  very high, and the dispatch savings are modest. The asyncEval boundaries already
  hide most dispatch latency.

**OPP-3b: KV cache read optimization for sliding-window layers**
- Lines: L1381-1500 (sliding fused attention kernel), L1403 (`N = 512`)
- Current: The sliding fused attention kernel attends over ALL 512 slots in the ring
  (`constexpr int N = 512`). At decode step `t` (for t < 512), only `t+1` slots have
  valid data, but the kernel reads all 512 positions. The ring is pre-allocated at
  maxSize=512 from the start.
- Observation: For the first 512 decode steps, many of the 512 KV slots contain
  garbage/uninitialized data. However, the attention scores for those positions
  should be masked. Looking at the kernel source (L1492+), it processes all 512
  slots with the GQA-pair schedule. If the mask is applied (positions beyond
  `offset+1` get -inf), the garbage values don't affect output. But the **bandwidth**
  cost of reading 512 slots when only `t+1` are valid is wasted for early decode steps.
- Proposed: Pass the actual valid slot count to the kernel and only iterate over
  `min(offset+1, 512)` slots. This saves bandwidth for the first 512 decode steps.
- Savings: For the 128-step decode benchmark with 512-token prefill seed, the cache
  starts at position 512, so all 512 slots are valid from step 1. **No savings for
  the benchmark scenario** — the prefill already fills the ring.
- Impact: **None for scored benchmark** — the 512-token prefill seed means the
  sliding cache is full from decode step 1.
- **Recommendation: Do NOT pursue** — no benefit for the scored configuration.

**OPP-3c: Reduce full-attention KV cache reads via prefill-seed-aware windowing**
- Lines: L5789-5814 (full fused attention), KVCacheSimple
- Current: Full-attention layers use `StandardKVCache` which grows unboundedly. At
  decode step `t` after a 512-token prefill, the cache has `512 + t` entries. The
  fused full attention kernel reads ALL `512 + t` K/V entries per step.
- Observation: The attention is causal, so all past positions are valid. There's no
  sliding window for full-attention layers — every position must be attended to.
  This is architecturally required; no optimization possible without changing the
  model's attention pattern.
- **No opportunity** — full attention is architecturally required.

---

## 4. KV CACHE MOVEMENT

### Storage

- **Full-attention layers** (10): `StandardKVCache` — keys/values stored as
  `[B, nKVHeads, S, headDim]` BF16 arrays that grow in steps of 256.
- **Sliding-window layers** (30): `RotatingKVCache(maxSize: 512)` — fixed-size
  ring buffer `[nKVHeads, 512, headDim]` BF16. The `fusedRingPrepare()` method
  (L5770) returns the raw backing arrays for the fused kernel.

### Per-step KV read volume

**Sliding layers** (30): Each reads 512 × 128 × 2 (K+V) × 8 (KV heads) × 2 bytes (BF16)
= **2 MB per layer per step**. × 30 layers = **60 MB/step**.

**Full-attention layers** (10): At step 128 (after 512 prefill + 128 decode = 640
positions): 640 × 128 × 2 × 8 × 2 = **2.6 MB per layer**. × 10 layers = **26 MB/step**.
This grows linearly with position.

**Total KV read per decode step**: ~86 MB (sliding) + growing (full). At the model's
21.6 GB size, this is <0.4% of the weight footprint — KV cache movement is NOT the
bottleneck. Weight reads dominate.

### Opportunities

**OPP-4a: KV cache quantization for full-attention layers**
- Current: Full-attention K/V caches are BF16. At 640 positions × 10 layers, that's
  ~6.5 MB of KV data read per step.
- Proposed: Quantize K/V caches to INT8 or FP8 (e.g., e4m3). This would halve the
  KV read bandwidth for full-attention layers.
- Risk: **Numerical change** — quantizing KV cache changes attention scores and
  outputs. This is NOT within the accepted attention quantization envelope (which
  only covers Q/K/V/O weight quantization, not cache quantization). **Likely
  violates correctness gates.**
- Impact: **Low** — KV reads are <0.4% of total bandwidth.
- **Recommendation: Do NOT pursue** — high risk, low reward.

**OPP-4b: Avoid KV cache growth reallocation in StandardKVCache**
- Lines: KVCache.swift L340+ (StandardKVCache.update)
- Current: StandardKVCache grows in steps of 256, using concatenate. The
  `fusedAppendPrepare()` method (L5795) returns the existing arrays for in-place
  write by the fused kernel. Growth only happens every 256 steps.
- Observation: For the 128-step decode benchmark, growth happens at most once
  (at step 128 if the prefill's 512 + 128 = 640 crosses a 256-boundary). The
  growth allocation is a one-time cost, not per-step.
- **No per-step opportunity.**

---

## 5. PREFILL PATH (25% of score)

### Current prefill architecture

The prefill processes 512 tokens in one forward pass. Key differences from decode:

1. **Embedding**: Stock `embedTokens(inputs)` — 1 dispatch (gather).
2. **RoPE angles**: Uses the load-time atlas with offsets (L10676-10693), no
   per-step RoPE dispatch.
3. **Attention masks**: 2 mask dispatches (full + sliding), since `n > 1`.
4. **QKV projection**: Uses retained `[Wq; Wk; Wv]` fused BF16 bank (L5679-5694),
   collapsing 3 GEMMs into 1 `matmul`.
5. **QK-norm + RoPE**: Uses `lagunaPrefillSlidingQKNormRoPE` or
   `lagunaPrefillFullQKNormYaRN` (L5836/L5849) — fused multi-token kernels.
6. **SDPA**: Stock `attentionWithCacheUpdate` — uses MLX's compiled SDPA kernel.
7. **O-proj**: Stock BF16 `wo(output)` or `attentionGateProjection` — no INT8
   affine path for prefill (the affine path is decode-only).
8. **Residual + RMSNorm**: `lagunaResidualRMSNorm` (L10232-10245) for multi-token.
9. **MoE**: `lagunaFusedSortedRoutedGateUp` (L10040) — sorted gather-GEMM over
   the fused bank. Then `lagunaPrefillSortedMoETail` (L10076) for weighted
   combine + residual add.
10. **Shared expert**: Stock `sharedExpert(x)` — 2 dispatches (gate/up QMV +
    down GEMV), or fused via `lagunaSharedSwiGLUQMV`.
11. **Last layer** (layer 39): `callLastPrefillRow` (L10290/6096) — only computes
    Q projection + attention + O-proj for the last query row, but still commits
    K/V for all 512 tokens. Uses `lagunaLastPrefillProjectionBanksEnabled` to
    fuse Q+gate and K+V projections into 2 matmuls instead of 4.
12. **LM head**: Uses the pruner in one-pass mode (no fused refinement).

### Prefill dispatch estimate

| Component | Dispatches | Notes |
|---|---|---|
| Embedding | 1 | Stock gather |
| RoPE angles | 0 | Atlas views, no dispatch |
| Masks | 2 | Full + sliding causal masks |
| Per-layer attention (39 layers) | ~4 each | QKV matmul + QK-norm-RoPE + SDPA + O-proj |
| Layer 39 attention (last) | ~3 | Q+gate matmul + K+V matmul + fused QK-norm-RoPE + SDPA + O-proj |
| Per-layer residual+norm (39) | 1 each | `lagunaResidualRMSNorm` or `lagunaResidualRMSNormRouter` |
| Per-layer MoE (39) | ~3 each | Fused gate/up + shared + tail or down+residual |
| Layer 0 dense MLP | ~2 | Fused gate/up + down+residual |
| Final norm | 1 | |
| LM head (pruned, one-pass) | 4 | |
| **Total prefill** | **~370** | |

### Opportunities

**OPP-5a: Custom prefill MoE gather-GEMM kernel**
- Lines: L10029-10051 (`lagunaFusedSortedRoutedGateUp`)
- Current: Prefill MoE uses MLX's `gatherQuantizedMM` (stock) for the gate/up
  projection, then `lagunaInterleavedSwiGLU` for activation, then stock
  `downProj` (QuantizedSwitchLinear) for the down projection. That's ~3-4
  dispatches per layer for the MoE alone.
- Proposed: A custom fused kernel that does sorted gather + NVFP4 dequant GEMM +
  SwiGLU + down GEMM + weighted reduce + shared expert + residual in fewer
  dispatches, similar to the decode `lagunaRoutedSharedDownResidualKernel`.
- Savings: **1-2 dispatches** per layer × 39 = 39-78 dispatches for prefill.
- Risk: **High complexity** — prefill is a batched GEMM (512 tokens × 8 experts),
  not a GEMV. The kernel would need to handle the sorted gather, scatter, and
  reduction across many tokens. Much more complex than decode GEMV kernels.
- Impact: **Medium** — prefill is 25% of score. Reducing dispatch count helps
  latency, but the dominant cost is the GEMM compute, not dispatch overhead.
- Editable: Yes.
- **Recommendation: Medium priority** — the prefill MoE path is the least
  optimized part of the codebase. A custom kernel here could improve prefill
  speedup, but the compute cost dominates over dispatch savings.

**OPP-5b: Fuse prefill QKV matmul with QK-norm + RoPE**
- Lines: L5689 (QKV matmul) + L5836/5849 (QK-norm+RoPE)
- Current: 2 dispatches: (1) `matmul(normalized, fusedQKVWeight.T)`, (2) fused
  QK-norm+RoPE kernel.
- Proposed: Fuse the QKV matmul output slicing + QK-norm + RoPE into one kernel.
  The matmul produces [1, 512, Q_dim + 2*KV_dim], then QK-norm+RoPE processes it.
- Risk: **High** — fusing a steel GEMM with elementwise normalization requires
  custom kernel work within MLX's GEMM dispatch infrastructure. The GEMM uses
  MLX's `steel_gemm` kernels which are AOT-compiled and heavily optimized.
  Intercepting the output to apply QK-norm+RoPE inline is architecturally
  challenging in the MLX framework.
- Impact: **Low** — 1 dispatch saved × 40 layers = 40 dispatches, but the GEMM
  compute dominates.
- **Recommendation: Low priority** — high complexity, modest gain.

**OPP-5c: Prefill attention — custom SDPA for sliding-window layers**
- Lines: L5887 (`attentionWithCacheUpdate`)
- Current: Stock MLX SDPA for prefill. For sliding layers, the stock SDPA computes
  attention over the full sequence with a sliding-window mask, potentially reading
  more KV than necessary.
- Proposed: A custom SDPA kernel that only reads the window-size context for each
  query position, reducing memory bandwidth.
- Risk: **Medium** — needs to match MLX's SDPA numerics exactly. The sliding
  window means each query only attends to 512 preceding positions.
- Impact: **Low-Medium** — for a 512-token prefill with window 512, every position
  can attend to all preceding positions (the window is the full sequence). So
  the savings are minimal for this specific benchmark. For longer prefills it
  would help more.
- **Recommendation: Low priority** — minimal benefit for the 512-token prefill.

---

## 6. WEIGHT LAYOUT / TRANSFORM OPTIMIZATION

### Current layout

- **Routed expert gate/up**: Fused row-concatenated `[256 experts, 2×512, 2048/8]`
  NVFP4 bank (L9862-9933). The `prepareFusedRoutedGateUp` method concatenates gate
  and up weights per expert.
- **Routed expert down**: `[256, 2048, 512/8]` NVFP4.
- **Shared expert gate/up**: Fused `[2×512, 2048/8]` NVFP4.
- **Shared expert down**: `[2048, 512/8]` NVFP4.
- **Attention QKV**: Group-32 affine INT8 fused bank with gate rows appended.
- **Attention O-proj**: Group-32 affine INT8 (most layers) or NVFP4 (tail layers).
- **LM head**: BF16 with int5 coarse copy for pruning.

### Opportunities

**OPP-6a: Expert weight interleaving for top-8 gather locality**
- Lines: L9862-9933 (fused routed gate/up bank), L7600 (routed down kernel)
- Current: Expert weights are stored contiguously per expert: expert 0's gate/up,
  then expert 1's, etc. The top-8 gather reads 8 experts' weights, which may be
  scattered across the 256-expert bank (depending on which experts are selected).
  Each expert's gate/up is 2×512×256 = 256 KB; 8 experts = 2 MB of weight reads.
- Proposed: Interleave expert weights so that the top-8 most-frequently-selected
  experts are adjacent in memory, improving cache locality. However, expert
  selection is input-dependent and varies per token, so static reordering can't
  guarantee locality.
- Risk: **Bit-exact** if the reordering is just a permutation of the expert
  dimension (the gather indices would need to be remapped). But this requires
  changing the transform to produce a remapped expert order, and the runtime
  would need to remap router indices. **High complexity** for uncertain gain.
- Impact: **Low** — the 8 selected experts' weights (2 MB) are read sequentially
  per expert in the QMV kernel. L1/L2 cache effects from non-adjacent experts
  are minimal since each expert's weights are contiguous within the bank.
- **Recommendation: Do NOT pursue** — the gain is speculative and the
  implementation complexity is high.

**OPP-6b: Pack routed expert down weights contiguously for the fused down kernel**
- Lines: L7600 (lagunaRoutedSharedDownResidualKernel), L9962-9966
- Current: The down weights are `[256, 2048, 512/8]` = `[256, 2048, 64]` uint32.
  The fused down kernel reads 8 experts' down weights via indexed gather.
- Observation: The kernel already handles the gather efficiently. The down
  weight for each expert is 2048×64 = 128 KB. 8 experts = 1 MB. This is read
  sequentially per expert in the kernel's inner loop.
- **No clear opportunity** — the layout is already contiguous per expert and
  the kernel reads them via indexed access.

---

## 7. OTHER OPTIMIZATION OPPORTUNITIES

### OPP-7a: Fuse final RMSNorm into LM head coarse pass (see OPP-2a)
Already covered in §2. **1 dispatch saved per decode step.**

### OPP-7b: Reduce asyncEval boundary count tuning
- Lines: L10510-10521 (decodeFireMask), L10727-10729, L10809-10811, L10834-10836
- Current: `asyncEval` is fired at specific layers based on `lagunaDecodeAsyncStage`.
  The current configuration fires asyncEval at `norm` and `logits` stages, plus
  potentially at specific layer boundaries via the `decodeFireMask`.
- Observation: The asyncEval boundaries allow the GPU to start computing the next
  layer while the previous layer's output is still being written. The optimal
  placement depends on the pipeline depth and kernel sizes.
- Proposed: Systematically sweep the asyncEval stage configuration to find the
  optimal pipeline depth. The `decodeFireMask` can be set to `.ladder(n)` or
  `.explicit(mask)` to control which layers fire asyncEval.
- Risk: **None** — asyncEval doesn't change correctness, only timing.
- Impact: **Low-Medium** — better pipelining can hide dispatch latency. The
  current 8 boundaries may not be optimal.
- Editable: Yes — controlled via environment variable.
- **Recommendation: Low priority** — this is a tuning exercise, not a novel
  optimization. The existing asyncEval placement is already tuned.

### OPP-7c: Embedding gather fusion — fuse embedding into first layer's input norm
- Lines: L10444 (embedding+RoPE atlas kernel) + L5544 (first layer's norm+QKV)
- Current: The embedding+RoPE atlas kernel produces the hidden vector (1 dispatch),
  then layer 0's attention does `lagunaNormAffineQKV` (1 dispatch for norm+QKV).
- Proposed: Fuse the embedding gather into the first layer's norm+QKV kernel.
  The embedding gather reads one row of [100352, 2048] BF16 (4 KB), then the
  norm+QKV kernel reads that row + the QKV weight. Fusing would avoid writing
  the embedding to memory and reading it back.
- Risk: **Medium** — the embedding+RoPE kernel also produces RoPE angle rows
  that are consumed by ALL layers, not just layer 0. Splitting this would
  require the RoPE angle extraction to remain separate.
- Impact: **Low** — saves 1 dispatch and ~4 KB of intermediate memory traffic.
  The embedding is tiny compared to weight reads.
- **Recommendation: Do NOT pursue** — minimal gain, complicates the atlas kernel.

### OPP-7d: Precompute and cache the attention scale factor**
- Lines: L5811 (`scale: _fusedAttnScale`)
- Current: `_fusedAttnScale` is likely computed once at init. No per-step cost.
- **No opportunity** — already cached.

### OPP-7e: Optimize the sliding fused attention kernel's threadgroup configuration**
- Lines: L1381-1500 (kernel source)
- Current: The sliding fused attention uses 32 threadgroups (one per head pair),
  each with 4 simdgroups (128 threads). It processes 512 KV slots with an 8-trip
  two-deep pipeline.
- Observation: The kernel's threadgroup memory usage is:
  - `tg_q0[128]`, `tg_q1[128]`, `tg_k[128]`, `tg_v[128]` = 512 BF16 = 1 KB
  - `outputs[4×32×33]`, `max_scores[2×32]`, `sum_exp_scores[2×32]` = ~18 KB float
  - Total: ~19 KB, well within the 32 KB threadgroup memory limit.
- Proposed: Increase the pipeline depth or adjust the BN/BD tiling to improve
  memory throughput. The current 2-deep pipeline with 32-element blocks may
  not fully saturate memory bandwidth.
- Risk: **Numerical change** — different tiling changes the order of floating-point
  operations in the online softmax, which can change rounding. Must be validated
  against the upstream equivalence checker.
- Impact: **Low-Medium** — the attention kernel is not the dominant cost
  (weight reads are). But for 30 sliding layers, even a small improvement compounds.
- Editable: Yes — the kernel source is inline in LagunaRuntimeModel.swift.
- **Recommendation: Medium priority** — a careful re-tile could improve memory
  throughput for 30 layers. Needs upstream equivalence validation.

### OPP-7f: Eliminate the gate softplus dispatch for layers where gate is deferred**
- Lines: L5636-5651 (deferGateActivation), L5954-5968 (fused gated O-proj)
- Current: When `lagunaFusedGatedAffineOProjEnabled` and the gate is deferred,
  the gate logits are passed raw to the O-proj kernel which applies softplus
  internally. This already saves 1 dispatch (the eager softplus). The code at
  L5636-5651 handles this correctly.
- **Already optimized** — no further opportunity.

### OPP-7g: Fuse the router Top-8 selection into the residual+RMSNorm+router dispatch**
- Lines: L10213 (residual+RMSNorm+router) + L9352 (router top-8)
- Current: 2 dispatches: (1) `lagunaResidualRMSNormRouter` produces router logits,
  (2) `lagunaDecodeRouterTop8` selects top-8 experts from those logits.
- Proposed: Fuse the top-8 bitonic sort into the residual+RMSNorm+router kernel.
  The router GEMV produces 256 logits; the top-8 sort operates on those 256 values.
  Fusing would avoid writing 256 BF16 logits to memory and reading them back.
- Savings: **1 dispatch** per MoE layer × 39 = 39 dispatches/step.
- Risk: **High complexity** — the bitonic sort kernel uses a specific threadgroup
  geometry (256 threads in a specific pattern). The router GEMV kernel uses a
  different geometry. Combining them requires a single kernel that does both the
  GEMV and the sort, which have very different parallelism patterns.
- Impact: **Low** — 39 dispatches saved, but the 256-element router logits are
  tiny (512 bytes). The dispatch overhead (~2-5 μs each) is the real cost, so
  ~80-200 μs/step.
- Editable: Yes.
- **Recommendation: Medium-low priority** — the savings are real but the
  implementation is complex. The router logits are only 256 elements; the sort
  kernel and GEMV kernel have incompatible parallelism patterns.

### OPP-7h: Single-dispatch routed+shared gate/up QMV (PR #87 in-flight)**
- Lines: L9877-9933 (routed gate/up) + L8087 (shared gate/up)
- Current: 2 separate dispatches for routed and shared gate/up QMV.
- **Already in-flight as PR #87** — not a new opportunity.

### OPP-7i: Fuse RMSNorm into QKV decode kernel (PR #88 in-flight)**
- Lines: L5544 (norm+QKV) — already fused via `lagunaNormAffineQKV`.
- **Already in-flight as PR #88** — the current code already has a fused
  norm+QKV path. PR #88 may be extending this to NVFP4-tail layers.

### OPP-7j: Double output rows in down+residual kernel (PR #89 in-flight)**
- Lines: L7600 (lagunaRoutedSharedDownResidualKernel)
- **Already in-flight as PR #89.**

---

## SUMMARY OF NOVEL OPPORTUNITIES

### Tier 1 — Highest potential impact

| ID | Name | Savings | Risk | Impact | Priority |
|---|---|---|---|---|---|
| OPP-5a | Custom prefill MoE gather-GEMM kernel | 1-2 disp/layer × 39 | High complexity | Medium (25% of score) | **Medium** |

### Tier 2 — Moderate impact, lower risk

| ID | Name | Savings | Risk | Impact | Priority |
|---|---|---|---|---|---|
| OPP-2a | Fuse final RMSNorm into LM head coarse pass | 1 disp/step | Numerical (must match RMSNorm rounding) | Low | **Low** |
| OPP-7e | Retile sliding fused attention kernel | 0 disp (better throughput) | Numerical (upstream equiv check) | Low-Medium (30 layers) | **Medium** |
| OPP-7g | Fuse router Top-8 into residual+RMSNorm+router | 1 disp × 39 layers | High complexity | Low | **Medium-low** |

### Tier 3 — Investigated, not recommended

| ID | Name | Reason |
|---|---|---|
| OPP-2b | INT8 quantize LM head | Breaks certified bit-exactness |
| OPP-3a | Mega-kernel for full attention block | Extreme complexity, modest savings |
| OPP-3b | Sliding KV cache early-step skip | No benefit (512-token prefill fills ring) |
| OPP-4a | KV cache quantization | Outside accepted envelope, high risk |
| OPP-5b | Fuse prefill QKV matmul with QK-norm+RoPE | High complexity, low gain |
| OPP-5c | Custom prefill SDPA for sliding layers | Minimal benefit for 512-token prefill |
| OPP-6a | Expert weight interleaving | Speculative gain, high complexity |
| OPP-7c | Fuse embedding into first layer norm+QKV | Minimal gain, complicates atlas kernel |

---

## KEY ARCHITECTURAL OBSERVATIONS

1. **The decode path is already extremely well-optimized.** At ~8 dispatches per
   layer, the codebase has fused nearly everything that can be fused without
   breaking bit-exactness. The remaining unfused sequences are:
   - Router GEMV → Top-8 sort (2 dispatches, hard to fuse due to different
     parallelism patterns)
   - QKV projection → fused attention (2 dispatches, different compute patterns)
   - Final RMSNorm → LM head (2 dispatches, fusing is possible but low impact)

2. **Weight bandwidth dominates.** The model is 21.6 GB resident. Per decode step,
   the routed expert weights (8 experts × ~256 KB gate/up + ~128 KB down = ~3 MB),
   shared expert (~768 KB), attention weights (~2 MB), and lm_head (~109 MB via
   pruner) are the dominant bandwidth consumers. KV cache reads (~86 MB) are
   secondary. Dispatch overhead (~324 × ~3 μs ≈ 1 ms) is a small fraction.

3. **The prefill path is the least optimized.** It relies more on stock MLX
   operations (steel GEMM, stock SDPA, stock gather-quantized-MM) and has fewer
   custom fused kernels. Since prefill is 25% of the score, this is where the most
   headroom likely exists, but the gains are harder to realize because the compute
   is dominated by large GEMMs rather than dispatch overhead.

4. **The score formula (decode^0.75 × prefill^0.25) means decode improvements
   have 3× the weight of prefill improvements.** A 5% decode speedup with no
   prefill change gives `1.05^0.75 = 1.037`, while a 5% prefill-only speedup gives
   `1.05^0.25 = 1.012`. Focus should remain on decode.

5. **The most promising untried direction is kernel-level throughput
   optimization** (OPP-7e) rather than dispatch fusion. The sliding attention
   kernel processes 30 layers per step; even a 5% throughput improvement in that
   kernel would compound across 30 layers. This requires careful Metal kernel
   tuning (threadgroup size, pipeline depth, memory access patterns) and must
   pass the upstream equivalence checker.

6. **The second most promising direction is the prefill MoE path** (OPP-5a).
   The prefill MoE uses stock `gatherQuantizedMM` which may not be optimally tuned
   for the 512-token × 8-expert × 512-intermediate GEMM shape. A custom kernel
   could improve memory access patterns and reduce intermediate materialization.
