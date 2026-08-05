# Fresh Optimization Ideas — MLXFast Laguna XS 2.1 NVFP4 Decode

**Date:** 2026-08-05 13:52 UTC
**Baseline:** commit bb52380, score ~2.455 (126 public promotions)
**Target:** M5 Max 128 GB, Apple GPU gen 17, 614 GB/s unified memory bandwidth
**Scope:** Ideas NOT covered by the four already-assigned experiments

---

## Already Assigned (DO NOT duplicate)

1. Graph-visible KV cache position + compiled decode segments (eliminate ~230µs/step CPU/FFI overhead)
2. Full-attention decode path dependency optimization (10 layers vs 30 sliding)
3. LM-head coarse pass byte reduction and dispatch consolidation
4. Prefill MoE gather-QMM tile geometry retile for short expert runs

---

## Current Decode Step Anatomy (from codebase analysis)

Per decode step with all DARKBLOOM flags ON (the default):

| Component | Dispatches | Key kernels |
|---|---|---|
| Per attention layer (×40) | 3 | `laguna_norm_affine_qkv`, `laguna_fused_sliding_attn`/`laguna_fused_attn`, `laguna_gated_affine_oproj` |
| Per sparse MoE layer (×39) | 4 | `laguna_residual_rmsnorm_router` (1), `laguna_decode_router_top8_norm_v2` (1), `laguna_routed_swiglu_qmv_packed_top8` (1), `laguna_shared_swiglu_qmv` (1), `laguna_routed_shared_nvfp4_down_residual` (1) |
| Per dense layer (×1, layer 0) | ~3 | norm+QKV, `laguna_dense_gate_up_swiglu`, `laguna_dense_down_residual` |
| Final norm + LM head | 2 | RMSNorm + pruned LM head |

**Total: ~280 kernel dispatches per decode step** (3×40 + 5×39 - overlap ≈ 280).

Key weight traffic per decode step:
- Attention QKV/o_proj (INT8 affine): ~10 MB × 40 layers = ~400 MB
- MoE gate/up (NVFP4): ~5.5 MB/expert × 8 routed + 1 shared × 39 layers = ~2.0 GB
- MoE down (NVFP4): ~1.4 MB/expert × 8 routed + 1 shared × 39 layers = ~504 MB
- LM head: ~210 MB (pruned to ~52 MB by two-pass)
- **Total weight read: ~3.1 GB per decode step**

At 614 GB/s peak bandwidth, the theoretical floor is ~3.1 GB / 614 GB/s ≈ **5.0 ms/token**. The M5 likely achieves ~60-70% of peak for non-contiguous access, giving a practical floor of ~7-8 ms/token. The current ~230µs/step suggests the measured steps are already very fast — wait, that's the CPU overhead per step. Actual token latency would be weight-read-bound.

---

## Idea 1: Merge Shared Expert Gate/Up QMV Into Routed Gate/Up Dispatch

### Gain Mechanism
Eliminates **1 kernel dispatch per sparse layer × 39 layers = 39 dispatches per decode step** (≈14% of all dispatches). The shared expert's gate/up QMV currently runs as a separate `laguna_shared_nvfp4_swiglu_qmv_bf16_v1` dispatch, but it consumes the **same input vector** as the routed gate/up and is architecturally identical (same NVFP4 QMV + SwiGLU shape, just 512 output rows instead of 512 per expert).

### The Gap (confirmed in code)
In `LagunaRuntimeSparseMoEBlock.forward` (line 10248), `mergedSharedActivated` is declared as `nil` and **never assigned**. The code comment says it should be set "when the routed and shared gate/up QMVs were issued as one dispatch," but this never happens. The shared expert gate/up always runs as a separate dispatch via `fusedSharedDownInputs` → `lagunaSharedSwiGLUQMV` (line 10322-10325). The down+residual kernel (`laguna_routed_shared_nvfp4_down_residual_bf16_r1_v4`) already fuses both experts in its down-projection — it takes a `shared_activated` input — but that input is always freshly computed by the separate shared QMV dispatch.

### Implementation
The routed gate/up R1 kernel (`laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v1`, line 7529) dispatches with threadgroups grouped as `expert_slot = group % 8`, `tile = group / 8`. Each threadgroup processes one expert slot. To merge the shared expert:

1. **Extend the dispatch from 8 slots to 9 slots** (slots 0-7 = routed, slot 8 = shared). The shared expert's weight bank is a separate NVFP4 array with the same row structure (1024 rows, each 1024 packed bytes).
2. Pass the shared expert's weight + scales as additional kernel inputs alongside the routed bank.
3. In the kernel, if `expert_slot == 8`, read from the shared weight bank instead of the routed bank (using the shared expert's fixed index). The SwiGLU activation is identical.
4. Write the shared activation to a separate output slot (slot 8), which feeds into the already-fused down+residual kernel's `shared_activated` input.

The output shape grows from `[1, 1, 8, 1, 512]` to `[1, 1, 9, 1, 512]` (or two separate outputs). The down+residual kernel already accepts shared activation separately, so the interface doesn't change.

### Files to Change
- `Sources/MLXFastModel/LagunaRuntimeModel.swift`:
  - `lagunaRoutedSwiGLUQMVPackedTop8R1Kernel` (line 7529) — add shared weight/scale inputs, extend to 9 slots
  - `lagunaRoutedSwiGLUQMVPackedTop8` (line 7648) — pass shared bank, extend grid
  - `LagunaRuntimeSparseMoEBlock.forward` (line 10248) — set `mergedSharedActivated` from the merged dispatch output
- `Sources/MLXFastTransform/` — no change needed (shared bank already exists)

### Expected Gain
- **Dispatch reduction:** -39 dispatches/step out of ~280 total (≈14% fewer dispatches). At the M5's flat ops-per-buffer sweep, dispatch count reduction is the primary lever.
- **Bandwidth coalescing:** the shared expert's input read (2048 BF16 = 4KB) is eliminated — it's already in L1/registers from the routed gate/up dispatch.
- **Risk:** LOW. The shared expert has the same weight structure as routed experts. The SwiGLU is identical. The down+residual kernel already handles the shared slot. This is filling a gap the code was designed for but never completed.

### References
- FlashFormer (arXiv:2505.22758): cross-layer fusion reduces kernel launches
- Ada-MK (arXiv:2605.11581): decode switches to mega-kernel engine eliminating launch overhead
- Current code comments at line 10248-10253 explicitly describe this as intended but unimplemented

---

## Idea 2: Interleave FP8 Scales Adjacent to FP4 Codes (Co-located Scale Layout)

### Gain Mechanism
The MoE QMV kernels currently read FP4 codes and FP8 scales from **two separate device pointers**, each requiring independent address calculation and memory transaction. In a bandwidth-bound kernel, combining these into one contiguous read improves effective bandwidth utilization by eliminating redundant address computation and improving coalescing.

### Current Layout
The routed gate/up packed-scales bank has layout `[expert][tile 128][k-block 4][row-pair sub 8]` (scales only), stored separately from the codes bank `[expert][row 1024][512 bytes packed]`. The down-projection kernel reads `expert_weight + output_row * packed_row_bytes + lane * 8` (codes) and `expert_scales + output_row * scale_row_bytes + lane` (scales) as two separate device reads per K-block.

### Proposed Layout (ARCQuant-style interleaved)
For each K-block of 16 FP4 values (8 bytes codes), store the 1-byte FP8 scale immediately adjacent:
```
[expert][row][k_block: 8 bytes codes | 1 byte scale]  // 9 bytes per K-block
```
This allows the kernel to load both codes and scale in one contiguous device read, eliminating one pointer dereference and one address computation per K-block iteration.

### Implementation
1. **Transform side** (`Sources/MLXFastTransform/`): build a new interleaved weight bank that places each FP8 scale byte immediately after its 16-element FP4 code block. The transform must preserve bit-exact dequant values — the bytes are the same, just reordered in memory.
2. **Kernel side** (`LagunaRuntimeModel.swift`): modify the QMV inner loop to read from a single pointer: `uint2 codes = *(device uint2*)(weight + k_block * 9); uint8_t scale = weight[k_block * 9 + 8];` (or a `struct { uint2 codes; uint8_t scale; }` read).
3. The `laguna_nvfp4_qdot_16` function currently takes separate `weight` and `scale` parameters. With interleaving, the scale is loaded from the same pointer offset.

### Files to Change
- `Sources/MLXFastTransform/Transform.swift` — new interleaved bank builder
- `Sources/MLXFastModel/LagunaRuntimeModel.swift`:
  - `lagunaSharedSwiGLUQMVHeader` (line 6547) — update `laguna_nvfp4_qdot_16` to read interleaved layout
  - `lagunaRoutedSwiGLUQMVPackedTop8R1Kernel` (line 7529) — update scale reads
  - `lagunaRoutedSharedDownResidualKernel` (line 7851) — update scale reads
  - `LagunaRuntimeWeights.swift` — build interleaved banks at load time

### Expected Gain
- **Bandwidth:** eliminates ~50% of the address-computation overhead per K-block (one pointer instead of two). For a deeply bandwidth-bound kernel where every cycle matters, this could be 3-8% on the MoE QMV kernels.
- **Coalescing:** the 9-byte read pattern may cause coalescing issues if threads in a SIMD group access different k-blocks. Need to verify that `lane * 9` strides don't break 16-byte coalescing. If they do, pad to 16 bytes per K-block (16 bytes codes + 1 byte scale + 7 padding = 16 bytes, perfectly coalesced).
- **Risk:** MEDIUM. Requires transform + kernel changes and careful coalescing analysis. The 9-byte stride is non-power-of-two, which may cause alignment issues on Metal. A padded 16-byte version trades 7 bytes waste per K-block for perfect coalescing.

### References
- ARCQuant (Meng et al., ACL 2026): "Interleaved Channel Layout" — co-locate scales with codes for continuous coalesced reads. [doi:10.18653/v1/2026.acl-long.388](https://doi.org/10.18653/v1/2026.acl-long.388)
- ReSet C3 (Lee et al., 2026): register-only dequant pipeline with co-located scales. [arXiv:2606.13233](https://doi.org/10.48550/arxiv.2606.13233)
- QUICK (arXiv:2402.10076): expert-contiguous flattened weight layout

---

## Idea 3: RaZeR-Style FP4→FP16 Structural Dequant (Reduce Inner Loop Ops)

### Gain Mechanism
The current NVFP4 dequant inner loop (`laguna_nvfp4_qdot_codes_16`, in `lagunaSharedSwiGLUQMVHeader` line 6547) uses a nibble-split approach: extract 4 nibbles from a 32-bit code word via shift+mask+OR, then build FP16 bit patterns. The `lagunaNvfp4NibbleSplit` flag controls which of 3 extract variants is used, each producing 4 `p0`-`p3` values via ~12 logical ops per 8 nibbles, then converting to `half2` via `as_type`.

The RaZeR approach exploits the **structural similarity between FP4 E2M1 and FP16 E5M10**: both have sign + exponent + mantissa fields. The conversion is a direct field remapping rather than building bit patterns via masks:
1. Sign bit: shift left by 15 (bit 0 → bit 15 of FP16) — 1 op
2. Exponent: mask 2 bits, add bias difference (FP4 bias=1, FP16 bias=15), shift left by 10 — 2 ops
3. Mantissa: already aligned (1 bit → bit 9 of FP16) — 0 ops
4. Subnormals (values 0 and 0.5): handle with a 4-entry register LUT or conditional — 1-2 ops

Total: **~5-6 ops per nibble** vs. the current ~12-13 ops per 4-nibble group.

### Current Approach
The existing code already does a bit-embedding trick: it constructs FP16 half patterns by positioning the FP4 sign, exponent, and mantissa bits into the correct FP16 positions using shift+OR with masks like `0x8E008E00`. This is already a form of structural decode. The question is whether RaZeR's field-remapping approach has fewer live constants and fewer dependency chains.

The three nibble-split variants (`lagunaNvfp4NibbleSplit` 0, 1, 2) each use different masking strategies:
- Variant 0 (default): `((c & 0x00070007) << 9) | ((c & 0x00080008) << 12)` — 2 ops per nibble pair (mask, shift, OR)
- Variant 1: `xe | (xe << 3)` — 2 ops, but needs the initial mask split
- Variant 2: `((c << 9) & 0x0E000E00) | ((c << 12) & 0x80008000)` — 2 ops

Each variant produces 4 `p` values (for 4 nibble pairs in a uint), totaling ~8-12 ops per uint (8 nibbles). The RaZeR approach would produce the same 4 values in ~5-6 ops by avoiding the separate sign/magnitude extraction and instead doing a single field remap.

### Implementation
The key insight: FP4 E2M1 has the layout `[S][E1 E0][M]` (4 bits), and FP16 has `[S][E4 E3 E2 E1 E0][M9..M0]` (16 bits). The remap is:
```
half fp4_to_fp16(uint4_t nibble) {
    uint16_t sign = (nibble & 1) << 15;
    uint16_t exp = ((nibble >> 1) & 3) << 10;  // FP4 exponent → FP16 exponent position
    uint16_t mant = (nibble & 0) << 9;         // mantissa bit (already 0 for FP4)
    // Adjust exponent bias: FP4 bias=1, FP16 bias=15
    // FP4 exp 0 (subnormal) → FP16 exp 0 (subnormal)
    // FP4 exp 1-3 → FP16 exp (1-3) + (15-1) = 15-17
    // But subnormals need special handling
    ...
}
```

The challenge: FP4 E2M1 has subnormals at exp=0 (values 0 and ±0.5), and normals at exp=1-3 (values ±1, ±1.5, ±2, ±3, ±4, ±6). The FP16 exponent bias difference means we can't just shift — we need to add 14 to the exponent field. This adds one more op (add constant to the shifted exponent).

Total RaZeR-style: shift sign (1) + mask+shift+add exponent (3) + OR (1) = 5 ops per nibble, vs ~3 ops per nibble pair in the current approach (but the current approach needs the initial split). The savings are marginal because the current approach is already well-optimized.

### Alternative: 16-Entry Register LUT
Since the FP4 E2M1 alphabet has exactly **16 values** (±{0, 0.5, 1, 1.5, 2, 3, 4, 6}), a 16-entry LUT of FP16 values (32 bytes, fits in registers) can be loaded once and indexed by the 4-bit nibble. The lookup is a single array index — 1 op per nibble — but Metal's register array indexing may not compile to a single instruction (it may use a switch or memory load).

On Metal/AGX, `thread` array indexing with a compile-time-constant size but runtime-variable index typically compiles to a series of conditional moves or a local memory load, which may be **slower** than the current bit manipulation. The research found that register-to-memory bandwidth ratio is ~250:1, and Metal lacks `lop3`, so register LUT indexing is likely not a win.

### Assessment
The current nibble-split approach is already well-optimized and may be near-optimal for Metal's instruction set. The RaZeR approach saves ~1-2 ops per nibble pair but adds exponent bias adjustment complexity. The 16-entry register LUT is likely slower on Metal due to indexed register access.

**Verdict: LOW priority.** The dequant inner loop is already heavily optimized (seed elision, scale fold, scale defer, nibble split variants). The marginal gain from RaZeR-style decode is probably <5% on the QMV kernels, and decode is bandwidth-bound, not compute-bound. The ALU savings only help if they allow higher occupancy or more thread-level parallelism to hide memory latency.

### Files to Change (if pursued)
- `Sources/MLXFastModel/LagunaRuntimeModel.swift`: `lagunaSharedSwiGLUQMVHeader` (line 6547) — alternative extract variants
- Could be tested as `DARKBLOOM_NVFP4_NIBBLE_SPLIT=3` (a new variant) for A/B comparison

### References
- RaZeR (arXiv:2501.04052): FP4→FP16 bit manipulation, ~5 ops, sign at position 0 to avoid masking
- QServe (arXiv:2405.04532): offline weight reordering for 3-instruction unpack
- FLUTE (arXiv:2407.10960): vectorized LUT in shared memory (not recommended for Metal)
- Practical FP4 Training (Zhang et al., 2026): direct FP4→FP8 integer-domain field remapping

---

## Idea 4: Depth-2 K-Tile Staging in MoE QMV Kernels

### Gain Mechanism
The routed SwiGLU QMV R1 kernel already implements depth-1 weight staging: block b+1's codes and scales are loaded before block b's compute, overlapping memory with compute. Depth-2 staging would prefetch TWO blocks ahead, giving more memory latency hiding at the cost of additional registers.

### Current Implementation
In `lagunaRoutedSwiGLUQMVPackedTop8R1Kernel` (line 7529), the staging loop loads `gate_codes`, `up_codes`, `gate_sb`, `up_sb` for the NEXT block before consuming the current block's values in `laguna_nvfp4_qdot_codes_16`. This is depth-1:
```
load block 0 → compute block 0 (while loading block 1) → compute block 1 (while loading block 2) → ...
```

### Proposed Depth-2
Maintain two sets of staged codes/scales and alternate:
```
load block 0,1 → compute block 0 (while loading block 2) → compute block 1 (while loading block 3) → ...
```

This doubles the prefetch window from 512 elements to 1024 elements. For a 2048-wide input with 4 blocks of 512, depth-2 means 2 blocks are always in-flight.

### Register Cost
Each staged set is: 2× `uint2` (codes) + 2× `uint8_t` (scales) = 18 bytes. Depth-2 needs 2 sets = 36 bytes extra registers per thread. The current kernel uses ~40 registers (16 `float` input_values + accumulators + staging). Adding 18 bytes (~5 GPRs) may push into register pressure territory, potentially reducing occupancy.

On Apple GPU gen 17, each threadgroup has 208 KiB register file with up to 128 GPRs/thread. The current kernel likely uses 64-80 GPRs. Adding 5 more should be safe for 64-thread threadgroups.

### Implementation
- Add a second set of staging variables (`gate_codes2`, `up_codes2`, `gate_sb2`, `up_sb2`)
- Unroll the staging prefetch to load 2 blocks ahead
- Alternate between the two staging sets in the compute loop

### Files to Change
- `Sources/MLXFastModel/LagunaRuntimeModel.swift`:
  - `lagunaRoutedSwiGLUQMVPackedTop8R1Kernel` (line 7529) — add depth-2 staging
  - `lagunaSharedSwiGLUQMVKernel` (line 6689) — same pattern for shared expert

### Expected Gain
- **3-8% on MoE QMV kernels** if memory latency is not fully hidden by depth-1. The gain depends on the memory latency vs. compute time ratio. If depth-1 already hides all latency, depth-2 adds nothing.
- **Risk:** LOW-MEDIUM. Easy to A/B test. If register pressure reduces occupancy, the net effect could be negative.

### References
- KBLAS (arXiv:1410.1726): double-buffered K-tile loading
- Absar et al. (arXiv:2602.20204): ping-pong scheduling for prefetch
- Volkov (2016): occupancy as the primary GPU latency-hiding mechanism

---

## Idea 5: Fused Embedding Gather + Layer-0 Norm + QKV Projection

### Gain Mechanism
The decode step starts with an embedding gather dispatch (`embedTokens(inputs)`), then enters the 40-layer loop. Layer 0's attention block fuses norm+QKV into one dispatch. The embedding gather and the first layer's norm+QKV are on the critical path with no asyncEval between them.

Fusing the embedding gather into the first layer's norm+QKV eliminates **1 dispatch** from the critical path and allows the embedding to be consumed directly in registers without a round-trip through device memory.

### Current Flow
```
embedTokens(inputs)  →  [device memory write]  →  layer 0: norm + QKV (reads from device memory)
```

### Proposed Fused Flow
```
fused_kernel(token_ids, embedding_weight, norm_weight, qkv_weights)  →  Q,K,V in one dispatch
```

The kernel reads the token ID, gathers the embedding row (2048 BF16 = 4KB), normalizes it (RMSNorm), and projects to QKV — all in one dispatch, keeping the 2048-element hidden vector in registers/threadgroup memory.

### Implementation
The fused kernel would:
1. Load the token ID (1 int32)
2. Gather the embedding row: `embedding_weight[token_id * 2048 + lane * 16]` — each thread loads 16 BF16 values
3. RMSNorm: compute mean and RMS of the 2048 values (needs a threadgroup reduction)
4. Normalize: multiply by `1/rms * norm_weight[lane * 16]`
5. QKV projection: for each of the 3 output matrices (Q, K, V), compute the QMV against the INT8 affine weights

This is a complex fusion — the RMSNorm needs a full 2048-element reduction across the threadgroup, and the QKV projection is the existing `laguna_norm_affine_qkv` kernel. Merging them requires careful threadgroup design.

### Expected Gain
- **1 dispatch saved** per decode step. At ~280 total dispatches, this is ~0.4%.
- The embedding gather is probably <0.5µs, so the gain is marginal.
- **Risk:** MEDIUM-HIGH. Complex kernel that merges gather + norm + projection. The first layer is a full-attention layer (48 heads, YaRN RoPE), so the QKV projection is larger than sliding layers.

### Verdict
**LOW priority.** The gain is too small relative to the implementation complexity. The embedding gather is already fast and the first layer's norm+QKV is already fused.

---

## Idea 6: KV Cache NHD Layout for Sliding-Window Layers

### Gain Mechanism
The sliding-window KV cache currently uses `[B, H, L, D]` (BHLD) layout — head-major. The research found that NHD layout (`[L, n_kv, d]` — token-major) eliminates per-step transposes and enables perfectly coalesced sequential reads during attention.

For sliding-window decode with window=512, the attention kernel reads all 512 K vectors then all 512 V vectors. With BHLD layout, reading 512 contiguous positions for one head requires a stride of `H * D` between each position (non-contiguous). With NHD layout, reading 512 contiguous positions for one head is a stride of `D` (contiguous if D is the last dimension).

### Current Layout
`RotatingKVCache` stores keys as `[B, H, maxCacheSize, D]` (BHLD). The fused sliding attention kernel (`laguna_fused_sliding_attn`) reads from this layout via `fusedRingPrepare`. The ring buffer stores positions in slot order (not logical order), but the layout is still BHLD.

### Implementation
1. **Cache layout change** (`CompilableRotatingKVCache.swift`, `KVCache.swift`): transpose the backing arrays to `[B, L, H, D]` (BLHD, token-major) or keep BHLD but ensure the attention kernel's access pattern is coalesced.
2. **Attention kernel** (`LagunaRuntimeModel.swift`): update the fused sliding attention kernel to read from NHD layout.

However, the fused kernel already reads the cache in a specific way that may already be coalesced for the BHLD layout. The fused kernel reads `cacheKeys[head, position, dim]` — with BHLD, `dim` is the contiguous dimension, so reading one head's 512 positions × 128 dims is strided by `H * D = 64 * 128 = 8192` elements between positions. This is a stride of 16KB, which means 512 positions are spread across 8MB — NOT coalesced.

With NHD, 512 positions × 128 dims for one head would be contiguous (512 * 128 * 2 bytes = 128KB), which fits in the SLC (~48MB) and is perfectly coalesced.

### Files to Change
- `Vendor/mlx-swift-lm/Libraries/MLXLMCommon/CompilableRotatingKVCache.swift` — change backing array layout
- `Vendor/mlx-swift-lm/Libraries/MLXLMCommon/KVCache.swift` — update `fusedRingPrepare` for new layout
- `Sources/MLXFastModel/LagunaRuntimeModel.swift` — update `laguna_fused_sliding_attn` kernel for NHD reads

### Expected Gain
- **5-15% on sliding attention reads** if the current BHLD layout causes non-coalesced access. The 30 sliding layers × 512 positions × 128 head_dim × 2 bytes = ~3.9 MB per layer × 30 = ~117 MB of K+V reads per step. If these are non-coalesced at 16KB stride, the effective bandwidth could be 40-60% of peak. Coalescing could recover 15-40% of that.
- **Risk:** MEDIUM. Layout change affects the cache update path (prefill writes) and the fused kernel reads. Must preserve bit-exact attention output. The ring buffer's slot-order access pattern complicates the layout change.

### References
- FreeKV (arXiv:2505.13109): NHD layout on GPU for decode
- PiKV (arXiv:2508.06526): ring buffer with O(1) insertion
- BaseRT (arXiv:2607.00501): KV cache layout for coalesced GPU memory access

### Caveat
This may overlap with the already-assigned experiment #2 (full-attention decode path). Need to confirm that experiment #2 only targets the 10 full-attention layers and does not touch the 30 sliding layers' cache layout. If experiment #2 is about the attention computation itself (not the cache layout), this idea is independent.

---

## Idea 7: Double-Buffered Input Vector Across MoE Expert Slots

### Gain Mechanism
In the routed SwiGLU QMV kernel, each threadgroup processes one expert slot and reads the same 2048-element input vector. With 8 expert slots, the input vector is read 8 times from device memory (once per threadgroup). If the input could be staged once in threadgroup memory and shared across expert computations, the input read traffic would be reduced by 8×.

However, the current kernel already reads the input vector with `vec<bfloat, 4>` loads that hit the SLC (the 4KB input was just written by the previous layer's residual+RMSNorm). So the input read is likely already SLC-resident and not a bandwidth bottleneck.

### Alternative: Threadgroup-Shared Input Staging
Instead of each expert slot's threadgroup independently reading the input, a single threadgroup could stage the input in threadgroup memory and process all 8 expert slots sequentially. This would:
1. Read the input ONCE into threadgroup memory
2. For each of 8 experts, compute gate/up QMV from threadgroup memory

This eliminates 7 redundant input reads but serializes the 8 experts (vs. 8 parallel threadgroups). The tradeoff is bandwidth savings vs. parallelism loss. On M5 with 40 GPU cores, running 8 parallel threadgroups per layer may be better than 1 large threadgroup.

### Assessment
**LOW priority.** The input vector is only 4KB and is SLC-resident from the previous layer. The bandwidth savings are negligible (~28KB/step for 7 saved reads × 39 layers). The parallelism loss from serializing experts would likely be worse.

---

## Idea 8: Prefill-Specific: Dequant-to-Cooperative-Tensor for M5 Neural Accelerator

### Gain Mechanism
The M5 introduces Neural Accelerators (tensor cores) in each GPU core, accessible via Metal 4 TensorOps `matmul2d`. The research found that for prefill (25% of score weight), the M5 selects `_nax` kernel variants for large GEMMs. For NVFP4 prefill, dequantizing FP4 weights into a cooperative tensor and feeding to `matmul2d` could leverage the tensor cores for the expert GEMMs.

However, this is **prefill-only** and may overlap with the already-assigned experiment #4 (prefill MoE gather-QMM tile geometry). It also requires Metal 4 APIs that may not be available in the current MLX Swift runtime.

### Assessment
**Monitor but do not pursue now.** The prefill weight is only 25% of the score, and experiment #4 already targets prefill MoE. If experiment #4 shows prefill gains, this could be a complementary direction for the tensor-core path. The M5's `_nax` kernel selection suggests MLX already uses Neural Accelerators where available; the question is whether the NVFP4 expert GEMM is on that path.

---

## Priority Ranking

| Priority | Idea | Expected Gain | Risk | Effort |
|---|---|---|---|---|
| **1** | Merge shared + routed gate/up QMV (Idea 1) | -39 dispatches/step (14%) | LOW | Medium |
| **2** | Interleave FP8 scales with FP4 codes (Idea 2) | 3-8% on MoE QMV bandwidth | MEDIUM | High |
| **3** | KV cache NHD layout for sliding layers (Idea 6) | 5-15% on attention reads | MEDIUM | Medium |
| **4** | Depth-2 K-tile staging (Idea 4) | 3-8% on MoE QMV latency hiding | LOW-MEDIUM | Low |
| **5** | RaZeR-style FP4 dequant (Idea 3) | <5% (already optimized) | LOW | Medium |
| **6** | Fused embedding + layer-0 (Idea 5) | <0.5% | MEDIUM-HIGH | Medium |
| **7** | Double-buffered input across experts (Idea 7) | Negligible | LOW | Low |
| **8** | Prefill cooperative-tensor for NAX (Idea 8) | Unknown (prefill only) | HIGH | High |

---

## Key Research Findings (Supporting Evidence)

### M5-Specific Findings
- **M5 Max bandwidth:** 614 GB/s (512-bit LPDDR5X-9600), 128 GB unified memory, 40-core GPU. Decode is deeply bandwidth-bound (~2 FLOP/byte for NVFP4 vs. ~27 FLOP/byte ridge point).
- **M5 Neural Accelerators:** tensor cores in each GPU core, accessed via Metal 4 `matmul2d`. Used for prefill GEMMs (`_nax` variants); decode stays on SIMD kernels (memory-bound).
- **M5 ops-per-buffer sweep is FLAT:** raising `MLX_MAX_OPS_PER_BUFFER` beyond 50 does not help on M5 (unlike M1-M4 where +11% was seen). The bottleneck is genuine bandwidth, not dispatch-gap idle. ([lablup/mlxcel commit 469ce9b](https://github.com/lablup/mlxcel/commit/469ce9b13546142a3e08c7a36398171aa4b848c1))
- **Register file:** 208 KiB per threadgroup, up to 128 GPRs/thread. Register bandwidth >> threadgroup memory bandwidth (~250:1 ratio).
- **No `lop3` instruction** on Metal/AGX. Bit manipulation uses separate `&`, `|`, `^`, `>>`, `<<`.
- **Apple WWDC 2026 guidance:** dequantize into cooperative tensors (registers), NOT threadgroup memory, to avoid round-trips.

### NVFP4 Dequant Findings
- **FP4 E2M1 alphabet:** exactly 16 values: ±{0, 0.5, 1, 1.5, 2, 3, 4, 6}. A 16-entry LUT (32 bytes) fits in registers but Metal register indexing may not compile to a single instruction.
- **RaZeR approach:** ~5 ops per nibble via FP4→FP16 field remapping (sign shift, exponent bias adjust, mantissa copy). ([arXiv:2501.04052](https://doi.org/10.48550/arxiv.2501.04052))
- **MARLIN/AWQ magic-number:** OR nibble with `0x64006400` to build valid FP16, then subtract. ~2-3 ops but needs `lop3` (unavailable on Metal). ([AWQ dequantize.cuh](https://github.com/mit-han-lab/llm-awq/blob/d6e797a4/awq/kernels/csrc/quantization_new/dequantize.cuh))
- **QServe reordering:** offline reorder 32 weights so `& 0x0F0F0F0F` extracts low nibbles in 3 ops. Requires transform-side change. ([arXiv:2405.04532](https://arxiv.org/html/2405.04532v1))
- **Register LUT vs threadgroup LUT:** register LUT is likely faster, but Metal's indexed register access may not be a single instruction. Threadgroup LUT causes bank conflicts (FLUTE found 8-way conflicts). ([FLUTE arXiv:2407.10960](https://doi.org/10.48550/arxiv.2407.10960))
- **Verdict:** Current nibble-split approach is already near-optimal for Metal. Marginal gains only.

### Command Buffer & Scheduling Findings
- **The dominant win for bandwidth-bound decode is reducing kernel launch count via fusion depth, NOT increasing ops-per-command-buffer.** ([FlashFormer arXiv:2505.22758](https://doi.org/10.48550/arxiv.2505.22758))
- **Mega-kernel approaches** (FlashFormer, MPK, Ada-MK) fuse entire decode steps into single kernels, achieving up to 1.7× latency reduction. These require cooperative groups and global sync — challenging on Metal but conceptually the prize. ([MPK arXiv:2512.22219](https://arxiv.org/abs/2512.22219))
- **Metal 4 unified compute encoder** allows concurrent dispatch without synchronization for independent work. Q/K/V and MoE expert GEMMs are independent within a layer. But the current code already fuses these into single dispatches.
- **CUDA Graph analogue on Metal:** indirect command buffers (ICBs) can be encoded once and replayed, eliminating per-op CPU encoding. Metal 4 + M5 supports GPU-encoded ICBs. ([Apple: Encoding ICBs on GPU](https://developer.apple.com/documentation/metal/encoding-indirect-command-buffers-on-the-gpu))
- **cuSync** (CGO 2024): tile-level synchronization between dependent kernels, up to 15% improvement. Could apply to the MoE down-projection where expert tiles are independent. ([doi:10.1109/cgo57630.2024.10444873](https://doi.org/10.1109/cgo57630.2024.10444873))

### MoE Routing Findings
- **Bitonic top-k** is likely optimal for N=256, k=8 (fits in one threadgroup). The current implementation already uses bitonic sort in one dispatch. ([Shanbhag et al., SIGMOD 2018](https://doi.org/10.1145/2967938.2967952))
- **Fuse softmax+top-k:** compute top-k on raw logits (ordering preserved), then softmax only over the 8 selected values. The current router already fuses sigmoid + top-8 + normalization in one kernel (`laguna_decode_router_top8_norm_v2`). ([SonicMoE arXiv:2512.14080](https://doi.org/10.48550/arxiv.2512.14080))
- **The router is already well-optimized:** 1 dispatch, fused with residual+RMSNorm, bitonic sort in registers. No significant improvement opportunity here.

### Memory Bandwidth Findings
- **Co-located scales (ARCQuant):** interleave FP8 scales adjacent to FP4 codes for coalesced reads. Eliminates redundant address computation. ([ACL 2026](https://doi.org/10.18653/v1/2026.acl-long.388))
- **Register-only dequant (ReSet C3):** dequantize FP4→FP16 in registers, FMA accumulate, never stage in threadgroup. Overlaps load+convert+accumulate across K-tiles. ([arXiv:2606.13233](https://doi.org/10.48550/arxiv.2606.13233))
- **Double-buffered K-tile loading:** ping-pong prefetch of next K-tile while computing current. Already partially implemented (depth-1). ([KBLAS arXiv:1410.1726](https://doi.org/10.48550/arxiv.1410.1726))
- **NHD KV cache layout:** token-major layout eliminates transposes and enables coalesced sequential reads for sliding-window decode. ([FreeKV arXiv:2505.13109](https://doi.org/10.48550/arxiv.2505.13109))
- **SLC residency:** ~48 MB shared SLC. Sliding KV cache (512 × 8 heads × 128 dim × 2 bytes × 2 (K+V) = ~2 MB per layer × 30 = ~60 MB) may partially fit in SLC with NHD layout.

---

## Summary

The **strongest fresh idea** is **Idea 1: Merge shared + routed gate/up QMV into one dispatch**. It fills a gap the code was designed for (`mergedSharedActivated`) but never completed, eliminates 39 dispatches per decode step (14% of total), and has low implementation risk. The down+residual kernel already fuses both experts — only the gate/up phase has the gap.

The **second strongest** is **Idea 2: Interleave FP8 scales with FP4 codes**, which directly addresses the bandwidth-bound bottleneck by reducing device memory transactions. This is a transform+kernel change with medium risk.

The **third** is **Idea 6: KV cache NHD layout**, which could improve coalescing for the 30 sliding layers' attention reads, but requires careful analysis of the current access pattern to confirm the non-coalesced hypothesis.

Ideas 3, 4, and 5 are lower priority due to marginal gains or high implementation complexity.
