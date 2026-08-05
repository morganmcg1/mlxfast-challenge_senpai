# Novel Optimization Targets — Laguna XS 2.1 NVFP4 Decode Path

**Date:** 2026-08-05 22:45 UTC
**Frontier:** 4058d0b (official M5 score 2.5459; target 2.5523, gap ~0.25%)
**Scope:** Decode path (75% of score weight), kernel dispatch reduction, Metal instruction-level optimization
**Method:** Direct source reading of `LagunaRuntimeModel.swift` (11,225 lines), tracing the full decode dispatch chain from `LagunaRuntimeModelInner.callAsFunction` (line 10665) through attention, MoE, and LM-head kernels.

## Already Assigned / Previously Identified (NOT duplicated here)

**Assigned experiments:** FMA dequant (Edward PR #65), merge shared+routed gate/up QMV (Thorfinn PR #50), LM-head coarse prune (Alphonse PR #51), prefill MoE retile 5→4 (Askeladd PR #52).

**In RESEARCH_IDEAS_2026-08-05_22:20.md:** g_proj fusion into norm+QKV, wider GQA pair=4, threadgroup input sharing in gate/up QMV, denser asyncEval rungs, SDPA output reshape fold, wider 16B weight loads, interleave gate/up codes+scales, extend attn projection async beyond layer 0.

**Already merged in 4058d0b:** STAGE2_GATHER, LM_HEAD_PRUNE, norm+QKV fusion, gated output fusion, sliding/full attention fusion, MoE down 9-slot, outputs_per_simd=4, QKV fused dispatch, depth-4 register prefetch on norm+QKV.

---

## Decode Dispatch Anatomy (per step, 40 layers)

| Phase | Dispatches/layer | Layers | Total dispatches |
|---|---|---|---|
| Embedding + RoPE atlas | 1 | 1 | 1 |
| Norm + QKV (fused, INT8 affine) | 1 | 40 | 40 |
| Fused attention (sliding or full) | 1 | 40 | 40 |
| Gated output projection (INT8 affine or BF16) | 1 | 40 | 40 |
| Residual + norm + router (fused) | 1 | 39 | 39 |
| Router top-8 normalization | 1 | 39 | 39 |
| Routed gate/up QMV (packed, R1) | 1 | 39 | 39 |
| Shared gate/up QMV (fused) | 1 | 39 | 39 |
| Down + residual (9-slot, routed+shared) | 1 | 39 | 39 |
| Final norm | 1 | 1 | 1 |
| LM head (pruned, two-pass) | 2 | 1 | 2 |
| **Total** | | | **~319** |

The router top-8 normalization kernel (39 dispatches) and the routed gate/up QMV's internal top-8 extraction are the primary redundant work identified below.

---

## Novel Target 1: Eliminate Redundant Top-8 Extraction in Routed Gate/Up R1 Kernel

### Source Location
- `lagunaRoutedSwiGLUQMVPackedTop8R1Kernel` (line 7335): kernel source, prologue at line 7359 calls `lagunaRouterTop8PrecomputedPrelude` (line 7299)
- `lagunaRouterTop8PrecomputedPrelude` (line 7299-7310): each threadgroup loads all 256 router keys and runs a full per-slot bitonic extraction loop to select `top8_winner`
- `lagunaDecodeRouterTop8NormalizingKernel` (line 8457): the SEPARATE kernel that already computes `router_indices` and `router_scores` from the same router logits/keys
- Dispatch: `lagunaRoutedSwiGLUQMVPackedTop8` (line 7454) passes `routerKeys` (not `indices`) to the R1 kernel

### The Problem
The decode MoE path has TWO independent top-8 selections from the same 256 router keys:
1. **Separate top-8 kernel** (line 8457): bitonic-sorts 256 keys → produces `router_indices` (8 uint32) + `router_scores` (8 float32). Consumed by the down kernel.
2. **R1 gate/up QMV kernel** (line 7335): each of 2048 threadgroups (8 slots × 256 tiles) re-extracts the same top-8 from `router_keys` in `lagunaRouterTop8PrecomputedPrelude` (line 7306: `for (uint r = 0; r <= expert_slot; ++r) { top8_winner = laguna_router_top8_extract_round(...) }`). This is ~200 ALU ops of bitonic-sort machinery PER threadgroup.

The indices-based non-R1 kernel (`lagunaRoutedSwiGLUQMVPacked`, line 7041) already takes pre-computed `indices` and simply reads `indices[expert_slot]`. The R1 version re-derives them because the precomputed-keys path was designed to avoid the separate top-8 kernel for expert selection — but the separate kernel STILL RUNS for score computation.

### Optimization Mechanism
Pass the top-8 kernel's `router_indices` output to the R1 gate/up kernel as an input. Replace the `lagunaRouterTop8PrecomputedPrelude` prologue (8 lines of key loading + the per-slot extraction loop) with a single `uint expert = indices[expert_slot]` read. The non-R1 indices kernel already demonstrates this pattern (line 7041+).

### Expected Decode Improvement
- **Compute savings:** ~200 ALU ops × 2048 threadgroups × 39 layers = ~16M ALU ops/step eliminated. At M5 ALU throughput, this is ~0.3-0.5 ms/step.
- **Dispatch reduction:** Zero (same dispatch count; only the kernel body changes).
- **Bandwidth:** Slightly increased (8 uint32 indices vs 256 uint32 keys passed per dispatch), but indices are 32 bytes total — negligible.
- **Estimate: 2-4% decode improvement.** The bitonic extraction is the gate/up kernel's prologue; removing it shortens the critical path per threadgroup.

### Correctness Risk
**LOW.** The indices produced by the top-8 kernel are the exact same expert indices the R1 kernel would extract from the keys (same bitonic sort, same ordinal comparison). The non-R1 kernel already proves this path is bit-exact. The only change is consuming pre-computed results instead of re-computing.

### Transform-Side Changes
**None.** Runtime-only change. The `router_indices` output already exists from the top-8 kernel.

---

## Novel Target 2: Pack Down-Projection Scales Into Walk-Order Side Bank

### Source Location
- `lagunaRoutedSharedDownResidualKernel` (line 7649): 9-slot down kernel, reads codes and scales from SEPARATE tensors
  - Line 7712: `const device uint8_t* weight = expert_weight + output_row * packed_row_bytes + lane * 8;`
  - Line 7714: `const device uint8_t* scale = expert_scales + output_row * scale_row_bytes + lane;`
  - Two separate device pointer dereferences per row per threadgroup
- `lagunaRoutedDownReduceKernel` (line 7491): same pattern, separate codes + scales
- `lagunaSharedDownResidualKernel` (line 6698): same pattern
- Contrast with: `DARKBLOOM_PACKED_SCALES` (line 152): packed scales already applied to gate/up bank, NOT down
- Packed gate/up bank: `_packedRoutedGateUpBank` built at transform time, consumed by `lagunaRoutedSwiGLUQMVPackedTop8` (line 9955)

### The Problem
The gate/up QMV path uses `DARKBLOOM_PACKED_SCALES` (default ON, line 152) — a scale-interleaved side bank that groups FP8 scale bytes by K-block walk order for better coalescing. The down projection kernels do NOT use this optimization. The down kernel reads codes (uint2 = 8 bytes) and scales (1 byte) from two separate device pointers per row. Each of the 9 simdgroups × 512 threadgroups = 4608 threadgroups issues these as independent memory transactions.

The down path processes `output_width = 2048` rows × `packed_row_bytes = 256` (codes) + `scale_row_bytes = 32` (scales) = 288 bytes per row. The codes are 8× the scale traffic, but the scale accesses are non-coalesced (1-byte reads strided across the scale tensor).

### Optimization Mechanism
Build a packed down-scales bank at transform time (in `Sources/MLXFastTransform/`) with the same walk-order layout used for gate/up packed scales. The down kernel's scale read changes from a strided `expert_scales + output_row * scale_row_bytes + lane` to a packed walk-order access pattern. The codes access stays unchanged.

For the 9-slot kernel specifically: each of the 9 simdgroups reads a different expert's scales. The packed bank would store all 256 experts' down scales in the same interleaved walk-order format, indexed by `expert * packed_expert_scale_bytes + walk_offset`.

### Expected Decode Improvement
- **Scale traffic:** 8 routed experts × 2048 rows × 32 bytes = 512 KB per layer. Shared expert: 2048 × 32 = 64 KB. Total: 576 KB × 39 layers = ~22 MB/step. This is ~0.7% of the ~3 GB total weight traffic.
- **Coalescing improvement:** The current 1-byte strided scale reads are inefficient on the M5's 128-byte cache line granularity. Packed walk-order layout coalesces 32 lanes' scale reads into a single 32-byte transaction instead of 32 separate 1-byte transactions.
- **Estimate: 0.5-1.5% decode improvement.** The down kernel is bandwidth-bound; even small coalescing improvements compound across 39 layers.

### Correctness Risk
**LOW.** The packed scales for gate/up are already proven bit-exact (DARKBLOOM_PACKED_SCALES is default ON and ranked). The down path has identical scale semantics (per-group FP8 E4M3 scales). The transform builds the same bytes in a different layout order.

### Transform-Side Changes
**Required.** Build a `_packedRoutedDownScales` bank in `Sources/MLXFastTransform/` with the walk-order layout. The runtime reads from the packed bank instead of the stock `_routedDownScales`. The gate/up packed bank construction is the reference implementation.

---

## Novel Target 3: Extend Register Prefetch (Depth 2-4) to Routed Gate/Up R1 Kernel

### Source Location
- `lagunaNormAffineQKVPrefetchSource` (line 4863): depth-4 register prefetch for norm+QKV, proven -12% kernel time
- `DARKBLOOM_NORM_AFFINE_QKV_PF` (line 4833): default depth 4, measured -11.9%/-12.2% kernel-level
- `lagunaRoutedSwiGLUQMVPackedTop8R1Kernel` (line 7335): currently has depth-1 weight staging only (lines 7375-7433)
  - Line 7381-7394: prefetches only the NEXT block's codes/scales (depth-1)
  - Line 7413-7425: loads next block's codes/scales inside the loop, consumed next iteration
  - The kernel has 4 K-block iterations (input_width=2048, block_width=512 → 4 iterations)

### The Problem
The norm+QKV kernel demonstrated that hoisting weight loads above the RMS reduction prologue (depth-4) saves ~12% of kernel time by overlapping weight memory traffic with the norm reduction's compute. The routed gate/up R1 kernel has a similar structure: it loads the 2048-element input vector (BF16, 4KB), then iterates over 4 K-blocks of weight codes/scales. It currently has only depth-1 staging (prefetching one block ahead). The first block's weight load is NOT overlapped with the input vector load.

### Optimization Mechanism
Extend the R1 kernel's weight staging from depth-1 to depth-2 or depth-4:
- **Depth-2:** Issue blocks 0 and 1's weight loads before the input vector load. Consume block 0 from registers during the first iteration, issue block 2 while block 1 is consumed, etc.
- **Depth-4:** Issue all 4 blocks' weight loads before the input vector load. This requires `4 × 2 × 8 = 64 bytes` of register storage per thread for gate codes, `4 × 2 × 8 = 64 bytes` for up codes, plus scale bytes. Total: ~140 bytes/thread, well within register limits.

The gate/up kernel has a simpler structure than norm+QKV (no RMS reduction prologue), so the overlap benefit is between the input vector load and the first weight block's qdot. The input vector load (4 vec<bfloat,4> loads per lane = 64 bytes) is fast, but the weight loads (8 bytes codes + 1 byte scale per lane per block) can be pipelined.

### Expected Decode Improvement
- The gate/up QMV runs 2048 threadgroups × 39 layers = ~80K threadgroups/step. Each kernel's weight traffic is ~1 KB/expert × 8 experts = 8 KB per threadgroup.
- Norm+QKV's depth-4 saved ~12% kernel time by overlapping ~9% of the dispatch's prologue. The gate/up R1 kernel's depth-1 already captures some of this; extending to depth-2-4 captures the remaining overlap.
- **Estimate: 1-3% decode improvement.** Conservative because depth-1 already exists; the marginal gain of depth-2-4 over depth-1 is smaller than depth-4 vs depth-0 on norm+QKV.

### Correctness Risk
**LOW.** The norm+QKV depth-4 prefetch was proven bit-exact (line 4843: "bit-identical, standalone-harness memcmp on all output rows"). The gate/up R1 kernel uses the same `laguna_nvfp4_qdot_codes_16` function with the same accumulation order. Prefetching only changes WHEN bytes are loaded into registers, not the accumulation order.

### Transform-Side Changes
**None.** Runtime-only change. The weight bank layout is unchanged; only the kernel's register allocation and load scheduling changes.

---

## Novel Target 4: Fuse the Gate/Up SwiGLU Activation Into the Down Kernel's Input Load

### Source Location
- `lagunaRoutedSwiGLUQMVPackedTop8R1Kernel` (line 7335): produces `activated[expert_slot * output_width + logical_row]` (line 7445)
- `lagunaRoutedSharedDownResidualKernel` (line 7649): reads `routed_activated + slot * input_width` (line 7688)
- Between these: the gate/up kernel writes 8 × 512 = 4096 BF16 activations to device memory, then the down kernel reads them back. This is 8 KB of activation traffic per layer.

### The Problem
The decode MoE pipeline has a producer-consumer dependency: gate/up QMV → activated tensor → down kernel. The activated tensor (8 experts × 512 BF16 = 8 KB per routed path) is written by the gate/up kernel and read by the down kernel. These are separate dispatches with an implicit encoder-wide barrier between them.

The activation tensor is small (8 KB routed + 1 KB shared = 9 KB), but it forces a dispatch boundary. The down kernel can't start until ALL 8 expert slots' gate/up QMVs complete, because the down kernel reads all 8 activations.

### Optimization Mechanism
For the shared expert only (slot 8 of the 9-slot down kernel): the shared expert's gate/up QMV produces 512 BF16 activations that the down kernel reads. Since the shared gate/up QMV is a separate dispatch, the down kernel waits for it.

The fusion approach: extend the 9-slot down kernel to also compute the shared expert's gate/up SwiGLU activation internally. The down kernel already loads the shared expert's 512-element input (for the down projection). If it also loaded the shared gate/up weight bank and computed the SwiGLU activation on-the-fly, the separate shared QMV dispatch could be eliminated.

This is analogous to how the attention kernel fuses QK-norm+RoPE+SDPA into one dispatch: the activation is computed in threadgroup memory and consumed immediately by the down contraction.

**Important caveat:** The routed expert activations (8 × 512) are too large to compute in the down kernel (would require 8 gate/up QMVs per threadgroup). This fusion targets ONLY the shared expert, which has a single 512-element activation.

### Expected Decode Improvement
- **Dispatch reduction:** -1 dispatch × 39 layers = -39 dispatches/step (the separate shared SwiGLU QMV dispatch). Out of ~319 total, this is ~12% dispatch reduction.
- **Memory:** The shared activation (512 BF16 = 1 KB) is computed in threadgroup memory and consumed by the same threadgroup's down contraction, saving the device write + read.
- **Estimate: 1-2% decode improvement.** Dispatch overhead at ~7µs/launch × 39 = ~273µs saved per step. If step ≈ 5ms, that's ~5.5%. However, the shared QMV overlaps with the routed QMV on the GPU (as noted in the shared-first-down measurement at line 7636), so the actual gain is smaller.

### Correctness Risk
**MEDIUM.** The shared expert's gate/up QMV uses the same NVFP4 dequant path as the routed experts. The down kernel would need to add the gate/up weight bank as input and replicate the SwiGLU activation (sigmoid → SiLU → multiply by up). The accumulation order must match the separate kernel's `simd_sum` order exactly. The threadgroup memory layout changes (adding 512 BF16 for the activation). Test with `LagunaUpstreamEquivalence.swift`.

### Transform-Side Changes
**None for the activation fusion itself.** The shared gate/up weight bank already exists. The down kernel gains two new inputs (shared gate weight, shared up weight) but reads from existing tensors. However, if Thorfinn's "merge shared+routed gate/up" experiment (PR #50) lands first, the shared gate/up bank would already be merged into the routed dispatch, making this fusion redundant. Coordinate with that experiment.

---

## Novel Target 5: Vectorized Online-Softmax in Sliding Attention Using half2 Reduction

### Source Location
- `lagunaSlidingFusedAttentionKernel` (line 1381): sliding attention decode kernel
  - Lines 1546-1556: QK dot product computed as 4 scalar FP32 MACs + `simd_sum`
  - Lines 1559-1570: online-softmax rescale using `metal::fast::exp` and scalar FP32 operations
  - Lines 1573-1580: output accumulation as 4 scalar FP32 MACs per slot
  - The loop processes 512 positions in 8 iterations of 2×BN=64 positions
  - Each iteration: 4 scalar QK MACs + `simd_sum` + rescale + 4 scalar output MACs = ~30 FP32 ops per lane per iteration
  - 30 sliding layers × (heads/2) = 30 × 16 = 480 threadgroups for sliding attention per step

### The Problem
The sliding attention kernel's online-softmax loop uses scalar FP32 arithmetic for the QK dot product and output accumulation. The 4-element dot product (lines 1548-1555) is 4 scalar multiply-adds followed by a `simd_sum` across 32 lanes. The output accumulation (lines 1573-1580) is 4 scalar multiply-adds per slot.

The kernel uses `typedef float U` (line 1405), so all accumulation is in FP32. The QK dot product and output accumulation could use `half2` vectorized operations where precision permits, or `simd_dot` for the QK reduction.

### Optimization Mechanism
Two complementary sub-optimizations:

**5a. simd_dot for QK dot product:**
Replace the 4 scalar MACs + `simd_sum` (lines 1548-1556) with `metal::simd_dot(pair_q, pipe_k, 0.0f)` using `vec<float, 4>` arguments. The M5's simd dot-product unit can execute a 4-element dot in 1 cycle vs 4 cycles for scalar MACs. This halves the QK compute per iteration.

**5b. Vectorized output accumulation:**
Replace the 4 scalar output MACs (lines 1573-1580) with `vec<float, 4>` operations:
```
vec<float, 4> pv = {pipe_va0, pipe_va1, pipe_va2, pipe_va3};
vec<float, 4> po = {pair_o0[0], pair_o0[1], pair_o0[2], pair_o0[3]};
po = po * pair_factor0 + pair_exp0 * pv;
```
This converts 4 scalar FMAs into 1 vectorized FMA, potentially 2-4× faster on the M5's SIMD unit.

### Expected Decode Improvement
- The attention loop is 8 iterations × ~30 FP32 ops/lane = ~240 FP32 ops per lane. The QK dot + output accumulation is ~50% of the compute (the other 50% is exp, rescale, and memory).
- simd_dot saves ~4 cycles per QK dot × 8 iterations × 2 slots = 64 cycles per threadgroup. Vectorized output accumulation saves ~12 cycles per iteration × 8 = 96 cycles.
- Total: ~160 cycles saved per threadgroup out of ~2000 cycles total = ~8% compute reduction.
- **But:** the sliding attention kernel is likely MEMORY-bound (reading 512 × 128 BF16 K values = 128 KB per KV head per threadgroup), not compute-bound. The compute savings may be hidden behind memory latency.
- **Estimate: 0.3-1% decode improvement.** Modest because the kernel is bandwidth-bound, but the simd_dot could improve instruction throughput if memory latency is already hidden by the 2-deep pipeline.

### Correctness Risk
**HIGH.** The online-softmax is numerically sensitive: the rescale factors, exp, and max comparisons must produce bit-identical results. `simd_dot` may use a different internal accumulation order than the scalar MACs. The output accumulation uses the same `bfloat` rounding boundaries as the stock `sdpa_vector` kernel. Any change to the accumulation order risks the hidden 512-token teacher-forcing exactness gate. Must verify with `LagunaUpstreamEquivalence.swift` and the 64-step drift tripwire.

The `metal::fast::exp` is already used (line 1565), so precision there is unchanged. The risk is in the dot-product and output-accumulation reordering.

### Transform-Side Changes
**None.** Runtime-only kernel source change.

---

## Summary Priority Ranking

| # | Target | Est. decode gain | Correctness risk | Transform needed | Effort |
|---|---|---|---|---|---|
| 1 | Eliminate redundant top-8 extraction in gate/up R1 | 2-4% | LOW | No | LOW |
| 3 | Depth-2/4 register prefetch on gate/up R1 | 1-3% | LOW | No | MEDIUM |
| 2 | Pack down-projection scales | 0.5-1.5% | LOW | Yes | MEDIUM |
| 4 | Fuse shared SwiGLU into down kernel | 1-2% | MEDIUM | No | HIGH |
| 5 | Vectorized online-softmax in sliding attention | 0.3-1% | HIGH | No | MEDIUM |

### Recommended Assignment Order
1. **Target 1** (redundant top-8 elimination) — highest expected gain, lowest risk, lowest effort. The indices path is already proven in the non-R1 kernel. This is the clear first pick.
2. **Target 3** (depth-2/4 prefetch on gate/up R1) — proven mechanism from norm+QKV, no transform change, low risk. Second pick.
3. **Target 2** (packed down scales) — proven pattern from gate/up packed scales, requires transform work but low risk. Third pick.
4. **Target 4** (shared SwiGLU fusion into down) — coordinate with Thorfinn's PR #50 (shared+routed gate/up merge); if that merges, this becomes redundant. Higher risk due to threadgroup memory changes.
5. **Target 5** (vectorized softmax) — highest correctness risk due to numerical sensitivity. Attempt only if targets 1-3 don't close the gap.

### Key Insight
The gap to lBroth (2.5523) is only ~0.25%. Target 1 alone (2-4%) should close it if the M5 confirms the M4 directional evidence. The redundancy between the separate top-8 kernel and the R1 gate/up kernel's internal extraction is the single largest unexploited inefficiency in the current decode path.
