# Fresh Optimization Ideas v6 — 2026-08-07 (Deep Prefill Path Analysis)

Ranked list of 8 concrete, falsifiable experiment ideas derived from a
full dispatch census of both the decode and prefill paths in
`LagunaRuntimeModel.swift` (502,603 / 524,288 bytes = 21,685 B headroom).

## Budget Constraints (verified)

| File | Size | Limit | Headroom |
|---|---|---|---|
| LagunaRuntimeModel.swift | 502,603 | 524,288 | **21,685 B** |
| Total surface | 1,897,962 | 3,000,000 | **1,102,038 B** |

LRM is the binding constraint. New kernel source must be compact.
Total growth per submission: 262,144 B cap.

## Prefill Dispatch Census (per layer, current default flags ON)

Verified by tracing every dispatch-generating call in the prefill (L>1) path:

| # | Dispatch | Code Location | Dispatches |
|---|---|---|---|
| 1 | Input RMSNorm | `inputNorm(input)` L6004 | 1 |
| 2 | QKV matmul (fused [Wq;Wk;Wv] bank) | `matmul(normalizedInput, fusedQKVWeight.T)` L6022 | 1 |
| 3 | **g_proj matmul (SEPARATE)** | `gProj(normalizedInput)` L6234 | 1 |
| 4 | QK-norm+RoPE (fused, prefill kernel) | `lagunaPrefillSlidingQKNormRoPE` / `lagunaPrefillFullQKNormYaRN` L6153/6166 | 1 |
| 5 | SDPA + cache update | `attentionWithCacheUpdate` L6204 | 1 |
| 6 | Gate-softplus + gate product (fused) | `lagunaGateProductSoftplusMultiToken` L6397 | 1 |
| 7 | O-proj + residual addMM (fused) | `addMM(residual, output, wo.weight.T)` L6442 | 1 |
| 8 | Post-attn residual + RMSNorm (fused) | `lagunaResidualRMSNorm` L10522 | 1 |
| 9 | **Router GEMV (SEPARATE, not fused with #8)** | `x.matmul(weight.T)` inside gate L9490 | 1 |
| 10 | Router top-8 tournament | `lagunaPrefillRouterTournament` L9515 | 1 |
| 11 | Routed gate/up QMM + down QMM | `lagunaFusedSortedRoutedGateUp` L10303 | 2 |
| 12 | Shared gate/up QMM + **compiledSiluProduct** + down QMM | `quantizedMM` + `compiledSiluProduct` + `quantizedMM` L8598-8611 | 3 |
| 13 | MoE tail (weighted sum + shared + residual) | `lagunaPrefillSortedMoETail` L10344 | 1 |

**Per sparse layer: ~16 dispatches.** Dense layer 0: ~13 (no router, no MoE tail).
With 39 sparse + 1 dense: ~637 dispatches per prefill pass.

### Key Gaps (unfused dispatches):
- **Dispatch #3** (g_proj): separate matmul, NOT fused with QKV bank (decode fuses it)
- **Dispatch #9** (router GEMV): separate, NOT fused with residual+RMSNorm (decode fuses it)
- **Dispatch #12** (shared SiLU): separate compiledSiluProduct, NOT fused with gate/up QMM

### Decode Dispatch Census (for comparison, per sparse layer)

| # | Dispatch | Dispatches |
|---|---|---|
| 1 | Input RMSNorm + NVFP4 QKV + gate rows | 1 (fused) |
| 2 | QK-norm + RoPE + SDPA + cache write | 1 (fused) |
| 3 | NVFP4 O-proj + gate product + softplus | 1 (fused) |
| 4 | Post-attn residual + RMSNorm + router GEMV | 1 (fused) |
| 5 | Router top-8 selection | 1 |
| 6 | Routed + shared gate/up QMV + SwiGLU | 1 (fused) |
| 7 | Routed + shared down + residual | 1 (fused) |
| **Total** | | **7** |

Decode is at 7/layer; prefill is at ~16/layer. Prefill has ~2.3x more dispatches.

---

## Idea 1: Fuse g_proj into Prefill QKV Matmul ★★★

**Priority**: 1 (highest)
**Component**: Prefill (25% of score) — all 40 attention layers
**Status**: NOT assigned, NOT tried, NOT in exhausted list

### Current flow (2 dispatches per layer):
1. QKV matmul: `matmul(normalizedInput, fusedQKVWeight.T)` → [1, L, QKVdim] (L6022)
2. g_proj matmul: `gProj(normalizedInput)` → [1, L, nHeads] (L6234)

Both consume the SAME `normalizedInput` and are both BF16 bias-free `Linear`.

### Proposed flow (1 dispatch per layer):
Concatenate `[Wq; Wk; Wv; Wgate]` at init time into a single bank.
Then: `matmul(normalizedInput, fusedQKVGateWeight.T)` → [1, L, QKVdim + nHeads]
Slice gate rows from the tail (zero-copy view, like decode does at L5923).

### Bit-exactness: YES (class A)
Same weight values, same input, same matmul operation. Each output row's
K-loop is independent of which rows share the dispatch (identical argument to
the existing QKV fusion at L6019). Slicing is a zero-copy view.

### Implementation:
- In `prepareFusedQKVWeight()` (L5544): concatenate `gProj.weight` after the
  QKV bank. Guard on `gProj.bias == nil`, `gProj.weight.dtype == .bfloat16`,
  `gProj.weight.dims(nHeads, hiddenSize)`.
- In the prefill attention path (L5996): when `L > 1` and fused bank present,
  slice gate rows from the QKV+gate output. Gate rows start at `queryDim +
  2*kvDim`. Use as `projectedGate` instead of `gProj(normalizedInput)` (L6234).
- The existing `_fusedQKVWeight` property already stores a concatenated bank.
  Add a parallel `_fusedQKVGateWeight` or extend the existing bank.

### Bandwidth impact:
- Eliminates normalizedInput re-read by g_proj: [1, 512, 2048] BF16 = 2 MB/layer
- 40 layers × 2 MB = 80 MB saved per prefill pass
- At ~400 GB/s: ~0.2 ms saved

### Expected speedup:
- 40 dispatches eliminated × ~2.5 µs = ~100 µs
- 80 MB bandwidth saved → ~200 µs
- Prefill ~4 ms: ~300 µs / 4 ms = ~7.5% prefill speedup
- Score: 7.5% × 0.25 = **~1.9% score**

### Budget: ~200-300 B in LRM (new property + guard + slice logic)
### M4 testability: YES (pure Swift, no Metal kernel)
### Risk: LOW. Identical pattern to existing QKV fusion. No custom kernels.

---

## Idea 2: Fuse Prefill Router GEMV into Prefill Residual+RMSNorm Kernel ★★★

**Priority**: 2
**Component**: Prefill (25% of score) — 39 sparse layers
**Status**: NOT assigned, NOT tried

### Current flow (2 dispatches per sparse layer in prefill):
1. Post-attn residual + RMSNorm: `lagunaResidualRMSNorm` (L10522) → 1 dispatch
   (This is the prefill twin, NOT the router-fused version)
2. Router GEMV: `x.matmul(weight.T)` inside `LagunaRuntimeMoEGate.callAsFunction`
   (L9490) → 1 dispatch

The decode path already fuses both via `lagunaResidualRMSNormRouter` (L932),
but it's gated on `x.dims(1, 1, hiddenSize)` (L==1 only). For prefill (L>1),
the router fusion is NOT used — the router GEMV runs separately.

### Why the decode kernel doesn't work for prefill:
`lagunaResidualRMSNormRouter` (L745-970) processes ONE row at a time
(`threadgroup bfloat normalized_row[axis_size]` is a single row in TG memory).
For prefill with L=512, we'd need 512 rows. The kernel's threadgroup memory
budget (2048 BF16 = 4 KB per row) is fine for 1 row but not for batched rows.

### Proposed approach:
Create a multi-token version that processes each row independently. The
kernel already dispatches `tiles * 512` threadgroups for decode (1 tile = 1
row). For prefill, extend the grid to `L * tiles` and add a row index.
Each threadgroup processes one (token, router_row) pair independently.

Alternatively, since `lagunaResidualRMSNorm` (the non-router version at L970)
already handles multi-token (it uses `row = threadgroup_position_in_grid.x`
and is row-general), extend it to also emit router logits per row.

### Bit-exactness: YES (class A)
The residual add, RMSNorm, and router GEMV are all per-row independent
operations. The router GEMV is `matmul(normalized_row, weight.T)` per row,
identical to the stock `x.matmul(weight.T)`. The fused kernel reproduces the
same per-row FP32 accumulation order.

### Expected speedup:
- 39 router GEMV dispatches eliminated × ~2.5 µs = ~98 µs
- Bandwidth: saves re-reading normalized [1, 512, 2048] BF16 = 2 MB × 39 = 78 MB
- Prefill: ~98 µs + 195 µs = ~293 µs / 4 ms = ~7.3% prefill
- Score: 7.3% × 0.25 = **~1.8% score**

### Budget: ~1500-2500 B in LRM (new kernel source variant)
### M4 testability: YES (Metal kernel, but straightforward per-row extension)
### Risk: MEDIUM. Multi-token kernel needs careful threadgroup memory management.
The existing decode kernel uses `threadgroup bfloat normalized_row[2048]` per
threadgroup; the multi-token version would use the same per-row TG memory but
dispatch L× more threadgroups.

---

## Idea 3: Prefill Shared Expert Inline SiLU (Custom NVFP4 GEMM+SiLU Kernel) ★★☆

**Priority**: 3
**Component**: Prefill (25% of score) — 39 sparse layers
**Status**: NOT assigned, NOT tried

### Current flow (3 dispatches per sparse layer for shared expert):
1. Gate/up QMM: `MLX.quantizedMM(x, fusedWeight, ...)` → [1, L, 2*1024] (L8603)
2. SiLU product: `compiledSiluProduct(gate, up)` → [1, L, 1024] (L8611)
3. Down QMM: `downProj(activated)` → [1, L, 2048] (L8611)

The `compiledSiluProduct` (vendor `SwitchLayers.swift` L19) is:
`MLXNN.silu(gate) * up` — a separate dispatch.

### Proposed flow (2 dispatches):
1. Gate/up QMM + SiLU: custom NVFP4 GEMM kernel that applies SiLU to the
   gate rows and multiplies by up rows as an epilogue → [1, L, 1024]
2. Down QMM: unchanged

The decode path already does this: `lagunaSharedSwiGLUQMV` fuses NVFP4 QMV +
SiLU in one kernel (L6645). For prefill, we need a GEMM (M=512) version.

### Bit-exactness: YES (with care)
Must reproduce MLX's `quantizedMM` NVFP4 dequantization + accumulation exactly,
then apply `bfloat(silu(bfloat(gate)) * bfloat(up))` matching `compiledSiluProduct`.
The decode SwiGLU QMV kernel already does this for M=1; the GEMM version needs
a different tiling but the same per-element math.

### Why this is hard:
- Custom NVFP4 GEMM (M=512) must match MLX's steel GEMM performance
- The routed expert prefill path already uses `lagunaExpertAlignedGatherEnabled`
  with vendor inline-SiLU (via _nax kernel), but the shared expert uses plain
  `quantizedMM` which doesn't have inline SiLU
- Could we route the shared expert through the same _nax path? The shared
  expert is a single expert (not gathered), so `gatherQuantizedMM` doesn't
  apply directly. A custom GEMM kernel is needed.

### Expected speedup:
- 39 SiLU dispatches eliminated × ~2.5 µs = ~98 µs
- Bandwidth: saves materializing [1, 512, 2048] BF16 gate+up = 2 MB × 39 = 78 MB
- Prefill: ~98 µs + 195 µs = ~293 µs / 4 ms = ~7.3% prefill
- Score: 7.3% × 0.25 = **~1.8% score**

### Budget: ~2000-4000 B in LRM (custom Metal kernel source)
### M4 testability: NO (custom GEMM kernel, M4 may not match M5 _nax behavior)
### Risk: HIGH. Custom NVFP4 GEMM is complex; matching MLX's quantizedMM
  performance for M=512 is hard. If the custom GEMM is 10% slower than MLX's,
  the net effect is negative.

---

## Idea 4: Prefill Last-Layer callLastPrefillRow Gate+O-proj Fusion ★☆☆

**Priority**: 4
**Component**: Prefill (25% of score) — 1 layer (last only)
**Status**: NOT assigned, NOT tried

### Current flow (3 dispatches for last layer's attention tail):
In `callLastPrefillRow` (L6437-6510):
1. `lagunaCompiledSoftplusGate(projectedGate)` → softplus (1 dispatch, compiled)
2. Broadcast multiply: `output.reshaped(...) * gate[.ellipsis, .newAxis]` (1 dispatch)
3. `wo(output)` → O-proj matmul (1 dispatch)

The main prefill path fuses steps 1-2 via `lagunaGateProductSoftplusMultiToken`
and step 3 via `addMM`. But `callLastPrefillRow` (which handles the last layer
in prefill, L=1 for Q but L tokens for K/V) does NOT use these fusions.

### Proposed flow (1-2 dispatches):
Use `lagunaGateProductSoftplus` (the decode single-token version, L3749) to
fuse softplus+gate product into 1 dispatch. Then use the existing compiled
`attentionGateProjection` (L5497) or `lagunaGatedOutputProjection` (L3635) to
fuse gate product + O-proj into 1 dispatch.

The decode path already has `lagunaGatedOutputProjection` (L3635) which fuses
gate product + O-proj GEMV. For the last prefill layer, Q length is 1 (single
token), so this is a GEMV — the same shape as decode.

### Bit-exactness: YES (class A)
Same operations, same per-element ordering. The last-row query is length 1,
matching the decode kernel's expected input shape.

### Expected speedup:
- Only 1 layer: 1-2 dispatches saved
- Negligible score impact (~0.025%)
- But: the last layer is on the critical path (no async overlap possible)

### Budget: ~100-200 B in LRM (call site change, reuse existing kernels)
### M4 testability: YES (reuses existing decode kernels)
### Risk: LOW. Reuses existing proven kernels.

---

## Idea 5: Prefill callLastPrefillRow Q+Gate+KV Bank Fusion for Full-Attention ★☆☆

**Priority**: 5
**Component**: Prefill — 1 layer (last, if full-attention type)
**Status**: NOT assigned, NOT tried

### Current state:
`callLastPrefillRow` (L6446) already banks Q+Gate and K+V for SLIDING layers
(`lagunaLastPrefillProjectionBanksEnabled`, L484). But the guard at L6451
requires `isSliding` — the full-attention last layer doesn't get the banking.

Looking at `prepareLastPrefillProjectionWeights` (L5716): it guards on
`isSliding` (L5725). The last layer (layer 39) type depends on config.

If the last layer is full-attention, it falls back to 4 separate projections
(wq, wk, wv, gProj) instead of 2 banked matmuls.

### Proposed change:
Remove the `isSliding` guard from `prepareLastPrefillProjectionWeights` and
the call site. The Q+Gate and K+V banking is type-agnostic (same matmul math).

### Bit-exactness: YES (class A)
Same argument as existing QKV fusion: per-row matmul is independent.

### Expected speedup:
- Only if last layer is full-attention: 2 dispatches saved (1 layer)
- Negligible score impact

### Budget: ~50-100 B (remove guard condition)
### M4 testability: YES
### Risk: LOW. Verify last layer type in config first.

---

## Idea 6: Prefill Shared Expert Scale Halving Re-Enablement ★★☆

**Priority**: 6
**Component**: Prefill (25% of score) — 39 sparse layers
**Status**: NOT assigned. Currently DISABLED (`lagunaPrefillSharedHalvedEnabled = false`, L227)

### Current state:
The prefill shared expert halved-scales path is disabled at L227:
```swift
let lagunaPrefillSharedHalvedEnabled = false
```
Comment says: "qmm_nax reverted to pre-PR#243 state (no kHalvedScales). The
halved path calls quantizedMM with groupSize=32 and scales [N+1, K/32], which
the pre-PR#243 qmm_nax doesn't support."

BUT: the precomputed full scales (`_prefillGateUpFullScales`,
`_prefillDownFullScales`) are already built at init time (L8317-8332). The
halved scales arrays + escapes exist. The ONLY reason it's disabled is the
qmm_nax limitation.

### Proposed investigation:
Check whether the current vendor qmm_nax state supports groupSize=32 with
[N+1, K/32] scales. If the organizer frontier has been updated since the
revert, this path may now work.

If it works: re-enable `lagunaPrefillSharedHalvedEnabled = true`. This would
halve the shared expert scale read traffic in prefill: scales go from
[1024, 128] to [1024, 64] uint8 (saving 64 KB per layer × 39 = 2.5 MB) for
gate/up, and [2048, 32] to [2048, 16] (saving 32 KB × 39 = 1.25 MB) for down.

### Bit-exactness: YES (if qmm_nax supports it)
The halved scale path uses the same NVFP4 pairwise-constancy invariant
already proven in decode. The precomputed full scales are already built.

### Expected speedup:
- Bandwidth: 3.75 MB saved per prefill pass (shared expert scales)
- Small but nonzero: ~0.01% prefill
- Main value: removes the `false` override and uses the already-built arrays

### Budget: ~0 B (change `false` to env check)
### M4 testability: YES (just enable and test)
### Risk: LOW-MEDIUM. Must verify qmm_nax support first.

---

## Idea 7: Prefill asyncEval Stride Optimization ★☆☆

**Priority**: 7
**Component**: Prefill (25% of score) — all layers
**Status**: NOT assigned. Knob exists but may not be optimally tuned.

### Current state:
Prefill has an asyncEval ladder (L10995):
```swift
if lagunaPrefillAsyncLadderStride > 0, h.dim(1) > 1,
    (i + 1) % lagunaPrefillAsyncLadderStride == 0
{ asyncEval(h) }
```

The stride is set by `DARKBLOOM_PREFILL_ASYNC_STRIDE` env var.

### Proposed experiment:
Sweep stride values (1, 2, 4, 8, 10, 13, 20, 40) on the M5 to find the
optimal asyncEval cadence for prefill. The decode path already has a tuned
ladder; prefill may benefit from a different stride since prefill dispatches
are longer-running (GEMM vs GEMV).

### Expected speedup:
- Uncertain. If current stride is suboptimal, could save ~1-3% prefill.
- If already optimal, zero gain.

### Budget: ~0 B (env var knob)
### M4 testability: YES
### Risk: LOW. Pure timing experiment.

---

## Idea 8: Prefill Input RMSNorm + QKV Bank GEMM Cache Prefetch ★☆☆

**Priority**: 8 (lowest)
**Component**: Prefill — 40 layers
**Status**: NOT assigned, NOT tried

### Current state:
Dispatch #1 (RMSNorm) and #2 (QKV GEMM) are separate. The RMSNorm output
([1, 512, 2048] BF16 = 2 MB) is written to GPU memory then re-read by the
GEMM. A full fusion (custom GEMM+norm kernel) was ruled out in v4 (Idea 5)
because custom GEMM can't match MLX's steel GEMM.

### Alternative approach:
Instead of fusing, improve cache locality. The RMSNorm kernel reads input
[1, 512, 2048] and writes output [1, 512, 2048]. If the QKV weight tiles
([QKVdim, 2048] BF16 = ~20-36 MB) could be prefetched into L2 during the
RMSNorm dispatch, the subsequent GEMM would hit warm L2.

This requires either:
1. A modified RMSNorm kernel that issues prefetch instructions for the QKV
   weight (using `metal::prefetch` or similar)
2. Or restructuring the dispatch order to overlap RMSNorm with QKV weight loads

### Why this is speculative:
- Metal's L2 cache on M5 is ~192 KB (shared across all GPU cores). The QKV
  weight is 20-36 MB, far exceeding L2. Prefetching won't help for the full
  weight, only for the first tile.
- MLX's steel GEMM already has its own tiling and prefetching.
- This is unlikely to produce measurable gain.

### Expected speedup: UNCERTAIN, likely <0.5%
### Budget: ~500-1000 B (modified kernel)
### M4 testability: MAYBE
### Risk: HIGH. L2 too small for meaningful prefetch of 20+ MB weights.

---

## Summary

| # | Idea | Component | Savings | Est. Score | Budget (LRM) | M4? | Risk |
|---|---|---|---|---|---|---|---|
| 1 | Fuse g_proj into prefill QKV matmul | Prefill | 40 disp + 80 MB | **~1.9%** | ~200-300 B | YES | LOW |
| 2 | Fuse prefill router GEMV into residual+RMSNorm | Prefill | 39 disp + 78 MB | **~1.8%** | ~1500-2500 B | YES | MED |
| 3 | Prefill shared expert inline SiLU (custom GEMM) | Prefill | 39 disp + 78 MB | **~1.8%** | ~2000-4000 B | NO | HIGH |
| 4 | callLastPrefillRow gate+O-proj fusion | Prefill | 1-2 disp | ~0.025% | ~100-200 B | YES | LOW |
| 5 | callLastPrefillRow Q+Gate+KV bank for full-attn | Prefill | 2 disp | ~0.025% | ~50-100 B | YES | LOW |
| 6 | Re-enable prefill shared scale halving | Prefill | 3.75 MB | ~0.01% | ~0 B | YES | LOW-MED |
| 7 | Prefill asyncEval stride sweep | Prefill | varies | ~0-0.75% | ~0 B | YES | LOW |
| 8 | RMSNorm + QKV GEMM cache prefetch | Prefill | cache only | <0.5% | ~500-1000 B | MAYBE | HIGH |

### Primary Recommendations

**Ideas 1 + 2 compose** and together target the two largest unfused dispatch
gaps in the prefill path. Both are LRM-only, bit-exact, and M4-testable.
Combined: ~3.7% score from prefill alone (40 + 39 = 79 dispatches eliminated
+ 158 MB bandwidth saved).

**Idea 1** is the strongest: lowest risk, highest impact, minimal code, and
directly mirrors the proven decode gate-into-QKV fusion. It should be
assigned first.

**Idea 2** is the second strongest: medium risk but high impact. It requires
a multi-token kernel variant of the existing `lagunaResidualRMSNormRouter`.
The kernel structure is well-understood from the decode version.

**Idea 3** is high-risk but high-reward. If the custom GEMM can match MLX's
quantizedMM performance, it eliminates another 39 dispatches. However, the
v4 analysis already flagged this as difficult. Defer until Ideas 1-2 are
validated.

**Idea 6** is essentially free (change `false` to env check) if the vendor
qmm_nax now supports the halved path. Worth a quick investigation.

### Composition Analysis

- Ideas 1 + 2 + 3: all target prefill, different dispatches, fully composable
- Ideas 4 + 5: target the last layer only, orthogonal to 1-3
- Idea 6: orthogonal to all (scale bandwidth, not dispatches)
- Idea 7: orthogonal (async scheduling)
- Total if 1+2+3 compose: ~5.5% score from prefill = ~1.4% total score

### What Was Verified and Ruled Out

- **Scale halving (decode)**: fully deployed on ALL decode paths
- **Scale halving (prefill)**: shared gate/up + down precomputed at init but
  halved path DISABLED (Idea 6 investigates re-enabling)
- **RMSNorm fusion (decode)**: fully fused including router GEMV
- **RMSNorm fusion (prefill)**: residual+RMSNorm fused, but router GEMV is
  SEPARATE (Idea 2 targets this)
- **Attention QK-norm+RoPE (prefill)**: already fused
- **Gate-softplus+gate product (prefill)**: already fused
- **O-proj+residual addMM (prefill)**: already fused
- **MoE tail (prefill)**: already fused (sorted + unsorted variants)
- **Routed gate/up (prefill)**: already fused via gatherQuantizedMM
- **Shared gate/up (prefill)**: fused bank but SiLU is SEPARATE (Idea 3)
- **Prefill RMSNorm+QKV GEMM full fusion**: ruled out (can't match steel GEMM)
- **Custom GEMM for router**: ruled out (PR #317, can't beat MLX's GEMM)
- **KV cache quantization**: not bit-exact
- **RMSNorm scalar fusion**: FP reduction order changes flip tokens
