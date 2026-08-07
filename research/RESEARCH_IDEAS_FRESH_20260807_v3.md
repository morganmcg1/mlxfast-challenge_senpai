# Fresh Optimization Ideas v3 — 2026-08-07 (Deep Codebase Analysis)

Ranked list of fresh, untried bit-exact bandwidth-reduction and dispatch-elimination
opportunities found by analyzing the scored decode/prefill paths, MoE kernels,
attention dispatch sequence, vendor _nax kernels, and weight preparation logic.

## Budget Constraints (verified)

| File | Size | Limit | Headroom |
|---|---|---|---|
| LagunaRuntimeModel.swift | 514,701 | 524,288 | **9,587 B** |
| LagunaLmHeadPrune.swift | 46,738 | 524,288 | 477,550 B |
| Transform.swift | 28,787 | 524,288 | 495,501 B |
| fp_quantized_nax.h | 78,440 | 524,288 | 445,848 B |
| quantized.cpp | 83,766 | 524,288 | 440,522 B |
| quantized_nax.cpp (generated) | 49,903 | 524,288 | 474,385 B |
| **Total surface** | 1,924,633 | 3,000,000 | **1,075,367 B** |

LRM is the binding constraint at 9,587 B. Vendor files and LagunaLmHeadPrune
have ample headroom.

## Decode Dispatch Sequence (per NVFP4 attention layer, verified from code)

With `DARKBLOOM_NATIVE_AFFINE_NVFP4` defaulting ON (all 40 layers use NVFP4
for QKV), the per-layer dispatch sequence is:

| # | Dispatch | Source | Merge Status |
|---|---|---|---|
| 1 | Residual + RMSNorm + router GEMV | `lagunaResidualRMSNormRouter` L856 | Fused (3→1) |
| 2 | Input RMSNorm | `inputNorm(input)` L5769 | **SEPARATE** (NVFP4 norm+QKV removed, +2.7% regression) |
| 3 | NVFP4 QKV R1 GEMV | `lagunaDecodeNVFP4QKVR1` L4826 | **SEPARATE** |
| 4 | Gate-softplus (INT8 g_proj matmul + softplus) | `lagunaGateSoftplus` L4447 | **SEPARATE** |
| 5 | QK-norm + RoPE + SDPA + cache write | `lagunaSlidingFusedAttention` L1760 | Fused (4→1) |
| 6 | NVFP4 O-proj + gate product | `lagunaGatedAffineOProjNVFP4` L4506 | Fused (3→1) |

Per sparse layer (39): 6 attention + 3 MoE = 9 dispatches.
Layer 0 (dense): 6 attention + 2 dense MLP = 8 dispatches.
Total: ~39×9 + 8 + 3 (model) = ~362 dispatches/step.
At ~2.5 µs/dispatch: ~905 µs/step ≈ 9% of a ~10 ms decode step.

**Dispatch #4 (gate-softplus) is the only remaining unfused per-layer dispatch
that can be eliminated.** Dispatches #2 and #3 cannot be fused (norm+NVFP4 QKV
regressed; norm requires global reduction incompatible with MoE down kernel).

---

## Idea 1: Fuse g_proj INT8 Matmul + Softplus into the NVFP4 O-proj Kernel ★★★

**Priority**: 1 (highest)
**Component**: Decode (75% of score) — all 40 attention layers
**Mechanism**: Eliminates dispatch #4 (gate-softplus) by computing the g_proj
INT8 affine matmul + softplus inside the NVFP4 O-proj kernel.

### Current flow (2 dispatches):
1. Gate-softplus dispatch: `normalized` × INT8 g_proj weights → softplus → `gate_values`
2. O-proj dispatch: (`attention_output` × `gate_values`) × NVFP4 O-proj weights → `output`

### Proposed flow (1 dispatch):
1. O-proj dispatch (fused): reads `normalized` + g_proj weights → computes g_proj
   matmul + softplus → reads `attention_output` → gate product → NVFP4 O-proj GEMV → `output`

### Why this works:
- The g_proj matmul produces `heads` values (48 or 64) from 2048 inputs.
  This is tiny compared to the O-proj GEMV (2048 outputs × 6144 inputs).
- Each O-proj threadgroup (256 threadgroups for 2048 outputs) redundantly
  computes the g_proj matmul. The g_proj weights (~30 KB: codes + scales +
  biases) are L2-cached after the first threadgroup loads them, so redundant
  reads are free. The `normalized` input (4 KB) is also L2-cached.
- The gate values (heads × 4 bytes = ~200 bytes) are computed in registers
  and used immediately for the gate product — no device memory round-trip.
- The O-proj kernel already handles the gate product (`gateIsActivated: true`
  path). The fusion extends this to compute the gate values from raw weights
  instead of receiving them as an input.

### Bit-exactness: YES
- The g_proj INT8 affine matmul accumulates in the same order (same K-loop
  traversal, same group-32 scale/bias application). The simd_sum reduction
  order is unchanged.
- The softplus is applied identically (same log1p/exp formula).
- The gate product multiplies the same gate value by the same attention
  output element. The only change is WHERE the gate value is computed (inside
  the O-proj kernel vs a separate dispatch). No FP reduction order changes.

### Bandwidth impact: NEUTRAL (dispatch savings only)
- Same weights read from DRAM (g_proj weights ~30 KB, L2-cached for
  redundant reads across threadgroups).
- Same inputs read (normalized, attention_output).
- Eliminates one intermediate buffer write+read (gate_values, ~200 bytes —
  trivially small, but eliminates a dispatch boundary).

### Expected speedup:
- 40 dispatches × ~2.5 µs = ~100 µs per decode step.
- At ~10 ms/step: ~1.0% decode speedup.
- Score: ~1.0% × 0.75 (decode weight) = **~0.75% score**.

### Budget impact: ~800-1200 B in LRM
- Add ~40 lines of Metal source to `lagunaGatedAffineOProjNVFP4Source` for
  the g_proj matmul + softplus computation.
- Add 3 new kernel inputs (`gproj_codes`, `gproj_scales`, `gproj_biases`)
  and 1 new input (`normalized`).
- Add ~10 lines of Swift for dispatch changes (pass g_proj weights + normalized).
- **Fits within 9,587 B headroom** but tight. Could offload some code to
  LagunaLmHeadPrune.swift (477K headroom) if needed, though it's not in the
  same kernel file.

### Target code:
- `LagunaRuntimeModel.swift:4155-4380` (`lagunaGatedAffineOProjNVFP4Source` —
  add g_proj computation before the gate product)
- `LagunaRuntimeModel.swift:4470-4510` (kernel registration — add new inputs)
- `LagunaRuntimeModel.swift:4506-4560` (`lagunaGatedAffineOProjNVFP4` — pass
  g_proj weights + normalized)
- `LagunaRuntimeModel.swift:5800-5850` (call site — eliminate separate
  `lagunaGateSoftplus` call, pass g_proj weights to O-proj instead)

### M4 testability: YES
- The O-proj kernel is a custom JIT kernel (not _nax), runs on M4.
- Verify via `--local-iterate` (max_abs_diff = 0) and upstream equivalence.
- The g_proj matmul is the same INT8 affine computation, just in a different
  kernel. Compare fused vs unfused output bit-for-bit.

### Why it's fresh:
No previous research or PR has proposed fusing the g_proj MATMUL into the
O-proj kernel. The existing O-proj kernels fuse the gate PRODUCT (multiply
attention output by pre-computed gate values) but the g_proj matmul that
PRODUCES those gate values is always a separate dispatch. The
`lagunaGateProductSoftplus` path fuses softplus + gate product but NOT the
initial g_proj matmul. This idea fuses the entire chain: g_proj matmul →
softplus → gate product → O-proj GEMV, all in one dispatch.

### Risk: LOW
The g_proj computation is independent of the O-proj GEMV (different weights,
different input). The fusion just places two independent computations in one
kernel. The g_proj result is used immediately (no cross-threadgroup
dependency). The main risk is LRM budget — the kernel source grows by
~800-1200 bytes, leaving ~8,400-8,800 B headroom.

### Composability:
- Composes with PR #222 (merge shared QMV into routed QMV) — different
  dispatch eliminated.
- Composes with all scale-halving work — different mechanism.
- Does NOT compose with the "gate-softplus for INT8 layers" path (those
  layers fold g_proj into the QKV bank, no separate dispatch to eliminate).

---

## Idea 2: Prefill Down Projection Scale Halving ★★☆

**Priority**: 2
**Component**: Prefill (25% of score) — prefill MoE down projection
**Mechanism**: The decode path already halves the routed down scales
(`_halvedRoutedDownScales`, L10038-10049). The prefill path uses the stock
`downProj` (a `QuantizedSwitchLinear`) with non-halved scales via
`MLX.gatherQuantizedMM`. Halving the prefill down scales reduces 8 MiB of
prefill bandwidth.

### Scale traffic:
- Prefill down scales: 256 experts × 2048 rows × 32 B (group-16) = 16 MiB.
- Halving (pairwise constancy): 8 MiB savings.
- Prefill MoE total: ~432 MiB. Savings: 8/432 = 1.85%.
- Score: 1.85% × 0.25 = **~0.46% score**.

### Bit-exactness: YES
Same NVFP4 pairwise constancy invariant as the decode down halving (PR #216,
proven correct). One escape byte per expert (down row 0, byte 1).

### Implementation:
- `LagunaRuntimeModel.swift`: prepare halved down scales + escape for the
  prefill path (~100-200 B, reuse existing decode halving code pattern).
- `quantized.cpp`: detect halved down scales and pass escape bytes to the
  _nax kernel (~50-100 B).
- `fp_quantized_nax.h`: the `fp_gather_qmm_rhs_expert_nax` kernel already
  has halving support from PR #198 (reverted). The down projection uses the
  same kernel. Re-apply with correct escape indexing.

### M4 testability: NO — _nax kernel path, M5 only.
### Budget: ~200 B LRM + ~100 B quantized.cpp. Within headroom.
### Why fresh: Identified in v2 research (Idea 4) but NOT assigned to any PR.

---

## Idea 3: Shared SwiGLU QMV Gate/Up Scale Halving (Wire Dead Code) ★★☆

**Priority**: 3
**Component**: Decode (75% of score) — shared expert gate/up QMV
**Mechanism**: PR #180 already builds `_halvedFusedGateUpScales` and
`_fusedGateUpScalesEscape` at load time (L8079-8080) but `fusedSharedDownInputs`
(L8412) passes the FULL scales to `lagunaSharedSwiGLUQMV`. The halved tensors
are **dead code**. Wiring them saves ~2.43 MiB/step of scale traffic.

### Scale traffic:
- Shared gate/up scales: [1024, 128] uint8 = 131,072 B/layer.
- Total (39 layers): ~4.87 MiB/step.
- Halving saves: ~2.43 MiB/step.
- At ~1597 MiB total decode: 2.43/1597 = 0.15% bandwidth.
- Score: 0.15% × 0.75 = **~0.11% score** (small but 100% free).

### Bit-exactness: YES
NVFP4 group-16 pairwise constancy. Escape bytes for gate row 0 byte 1 and
up row 0 byte 1. Same pattern as all other MoE halved kernels.

### Implementation:
1. Modify `lagunaSharedSwiGLUQMVRows1Kernel` source: `scale_row_bytes`
   128→64, scale pointer `lane`→`lane/2`, add escape byte input.
2. Add `gateUpEscape` parameter to `lagunaSharedSwiGLUQMV`.
3. Change `fusedSharedDownInputs` to pass `_halvedFusedGateUpScales` and
   `_fusedGateUpScalesEscape` instead of `banks.gateUpScales`.

### Budget: ~300-400 B in LRM (kernel source + dispatch changes).
### M4 testability: YES — custom JIT kernel, runs on M4.
### Why fresh: Identified in BANDWIDTH_AUDIT (Opportunity 1) but NOT assigned.

---

## Idea 4: Gate-softplus Scale/Bias Interleaved Packing ★☆☆

**Priority**: 4
**Component**: Decode — g_proj metadata (all 40 layers)
**Mechanism**: The gate-softplus kernel reads scales and biases from two
separate device memory arrays. Even with simd_shuffle broadcast (PR #200),
each lane-group issues two separate device loads per K-block: one for
scale, one for bias. If the transform/runtime interleaved them into a
single array `[s0, b0, s1, b1, ...]`, both would be in the same cache line,
halving the number of cache line accesses for g_proj metadata.

### Traffic:
- g_proj scales: heads × 64 B × 2 (bfloat16) = ~6-8 KB/layer
- g_proj biases: same
- Total metadata: ~600 KiB/step (all 40 layers)
- Interleaving halves cache line accesses but not DRAM bytes.

### Bit-exactness: YES
The interleaved array stores the same BF16 bit patterns at alternating
positions. The kernel reads `packed[2*group_id]` for scale and
`packed[2*group_id + 1]` for bias — same values, different addresses.

### Implementation:
- Runtime preparation in `lagunaNativeAffineGProjWeight` (L438): interleave
  scales and biases into a single array.
- Kernel source (`lagunaGateSoftplusSource`): read from interleaved array
  instead of separate `scales` and `biases` inputs.
- ~200 B in LRM for kernel changes, ~100 B for runtime prep.

### Budget: ~300 B in LRM.
### M4 testability: YES.
### Why fresh: The simd_shuffle dedup (PR #200) addressed redundant lane
loads but not the separate-array cache line issue. No previous work
proposed interleaving scale and bias into one array.

### Risk: LOW benefit. The g_proj metadata (~600 KiB/step) is tiny compared
to weight traffic (~526 MiB/step). The benefit is marginal unless the
metadata spills from L1 to L2 (which may happen at ~15 KB/layer).

---

## Idea 5: Routed Down Kernel: Eliminate Redundant Input Re-read via Single-Load Optimization ★☆☆

**Priority**: 5
**Component**: Decode — routed+shared down residual kernel
**Mechanism**: The `lagunaRoutedSharedDownResidualKernel` (L7993) reads the
512-element activated input for each of 9 expert slots. Each slot's
threadgroup loads its 512-element input independently. For the 8 routed
experts, the inputs are different (each expert's SwiGLU output). For the
shared expert, the input is the same 512-element vector every time.

The shared expert's 512-element input (1 KB BF16) is read by 2048/4 = 512
threadgroups (each handling 4 output rows). Each threadgroup's lane loads
16 elements via `vec<bfloat,4>` — 4 loads per threadgroup. With 512
threadgroups, that's 2048 loads of the same 1 KB buffer. This is L2-cached
(1 KB << L2), so DRAM traffic is minimal.

However, the 8 routed experts' inputs are also re-read by all 512
threadgroups. Each expert's input is 512 BF16 = 1 KB. 8 experts × 1 KB =
8 KB total, also L2-cached.

**The optimization opportunity is marginal** — the input reads are L2-cached
and tiny compared to the weight reads (8 × 524 KB = 4 MB per expert set).

### Alternative angle: the routed down kernel's `expert_input` pointer is
computed as `routed_activated + slot * input_width`. The `routed_activated`
buffer is [8, 512] BF16 = 8 KB, laid out as 8 contiguous 1 KB blocks. The
512 threadgroups read from this 8 KB buffer, with each slot reading its
own 1 KB slice. The reads are strided by 2048/4 = 512 threadgroups per
output-row group. This access pattern is already well-coalesced within
each slot.

### Verdict: No actionable optimization. The input traffic is L2-cached and
negligible. Listed as a "checked and ruled out" item for completeness.

---

## What Was Checked and Ruled Out (this analysis)

- **Fuse input RMSNorm into previous layer's down+residual**: RMSNorm
  requires a global reduction across 2048 elements. The down+residual
  kernel has 512 threadgroups (4 rows each), so no single threadgroup can
  compute the global mean. Would need a separate reduction pass = more
  dispatches. NOT feasible.

- **Fuse input RMSNorm into NVFP4 QKV kernel**: Already tried and
  REGRESSED (+2.7%). The RMSNorm computation interferes with the GEMV's
  memory access pattern. NOT worth retrying.

- **Fuse g_proj into residual+RMSNorm+router kernel**: Feasible but only
  covers 39 sparse layers (layer 0 has no router). The g_proj values must
  survive across the attention block (written to device memory). More
  complex than fusing into O-proj. INFERIOR to Idea 1.

- **Fuse g_proj into QKV kernel**: The QKV kernel already has the normalized
  input in threadgroup memory. But the g_proj uses INT8 affine (group-32)
  while the QKV uses NVFP4 (group-16) — different dequantization paths.
  The QKV kernel was already through regression iterations. RISKY.

- **MoE weight L2 reuse across threadgroups**: Each threadgroup reads
  unique weight rows (no data sharing). L2 caching doesn't help across
  non-overlapping row sets.

- **Expert weight transposition for GEMV**: Row-major layout is already
  optimal for GEMV (each thread reads contiguous row data). Transposing
  would hurt, not help.

- **KV cache layout changes**: Current [heads, seq, dim] layout is optimal
  for SDPA's per-head QK^T computation. KV cache quantization is NOT
  bit-exact. No bit-exact layout improvement available.

- **Attention mega-kernel (SDPA + gate + O-proj)**: 32 KB threadgroup memory
  limit (already killed the 1-pass attention epilogue). Adding O-proj GEMV
  would exceed this. NOT feasible.

- **Routed SwiGLU + down fusion**: SwiGLU output (8×512) must be fully
  computed before down can start (down reads all 512 inputs per output
  row). Requires global barrier across 131K threadgroups. Metal has no
  efficient cross-threadgroup barrier. NOT feasible.

- **MoE weight reordering by expert frequency**: Expert selection is
  dynamic and data-dependent. Can't statically reorder for locality.

- **NVFP4 code deduplication**: Codes ARE the weight data. Can't deduplicate
  without changing values. NOT bit-exact.

- **4-wise scale constancy (halve halved scales again)**: NVFP4 quantizer
  only guarantees pairwise constancy (scale[2k]==scale[2k+1]). 4-wise
  constancy is NOT guaranteed. NOT bit-exact.

---

## Summary

| # | Idea | Component | Savings | Score | Budget (LRM) | M4? | Priority |
|---|---|---|---|---|---|---|---|
| 1 | Fuse g_proj matmul+softplus into O-proj | Decode | 40 dispatches | ~0.75% | ~800-1200 B | YES | **HIGH** |
| 2 | Prefill down scale halving | Prefill | 8 MiB | ~0.46% | ~200 B | NO | **MEDIUM** |
| 3 | Shared SwiGLU gate/up halving (wire dead code) | Decode | 2.43 MiB | ~0.11% | ~300-400 B | YES | **MEDIUM** |
| 4 | Gate-softplus scale/bias interleaving | Decode | ~300 KiB cache | <0.05% | ~300 B | YES | LOW |
| 5 | Routed down input re-read | Decode | L2-cached, ~0 | ~0% | 0 B | YES | RULED OUT |

### Primary Recommendation

**Idea 1** is the strongest fresh opportunity. It eliminates 40 dispatches
per decode step (the gate-softplus dispatch) by fusing the g_proj INT8 matmul
+ softplus computation into the NVFP4 O-proj kernel. The g_proj computation
is tiny (~0.8% of the O-proj GEMV's FLOPs) and L2-cached across redundant
threadgroup reads. The fusion is bit-exact (same arithmetic, same reduction
order, just in one kernel instead of two). Expected: ~1% decode speedup =
~0.75% score. Budget: ~800-1200 B in LRM, leaving ~8,400 B headroom.

**Idea 2** (prefill down halving) and **Idea 3** (shared SwiGLU halving)
are smaller bandwidth savings that compose independently with Idea 1.
Idea 3 is particularly low-cost: the halved tensors already exist (built by
PR #180), they just need to be wired into the kernel.

### Key Insight

The M5 is bandwidth-bound, but dispatch overhead (~9% of decode time) is
also significant. Idea 1 targets dispatch elimination (not bandwidth
reduction), which is a different optimization axis from all previous work
(scale halving, dedup, float4 stores — all bandwidth reductions). The
gate-softplus dispatch is the last unfused per-layer dispatch that can be
eliminated without regression.
