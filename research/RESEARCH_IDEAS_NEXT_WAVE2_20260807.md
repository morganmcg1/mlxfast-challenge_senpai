# Next-Wave 2 Optimization Ideas — 2026-08-07 (Deep Codebase Analysis)

Ranked list of NOVEL, untried bit-exact bandwidth-reduction and
dispatch-elimination opportunities found by deep analysis of the scored
decode/prefill paths, router Top-8 selection, MoE expert gather, attention
dispatch chains, and the shared expert prefill scale reconstruction.

## Context

- Current leaderboard best: **2.6040**. Our frontier (ad58c92) includes
  merged PRs: g_proj+QKV fusion (#230), INT8 O-proj dot4 (#245), prefill
  shared scale halving (#243), prefill MoE down scale halving (#234).
- M5 is bandwidth-bound (~89% GPU utilization). Only levers: read fewer
  bytes or eliminate dependent dispatches.
- Score = decode_speedup^0.75 × prefill_speedup^0.25. Both ≥ 0.95.
- LRM: **523,340 / 524,288 = 948 B headroom** (binding constraint).
- Vendor files: fp_quantized_nax.h (~446KB), quantized.cpp (~440KB) have ample headroom.

## Exhausted Directions (DO NOT re-suggest)

- Scale halving: decode done (routed+shared MoE, QKV, O-proj, shared down).
  Prefill done (shared gate/up, shared down, routed gate/up, routed down).
- RMSNorm fusion (dead), attention epilogue 1-pass (dead), dot4 (done/dead).
- FP reduction order changes in logits-contributing kernels (DEAD — ULP errors flip tokens).
- Prefill O-proj gate dispatch fusion via MLX compile() (REFUTED, commit 8841cd9).
- KV cache quantization (BLOCKED — outside accepted envelope).
- INT8 dedup family (complete), float4 stores (done), argmax fuse (done).
- Vendor _nax scale halving: fully deployed on ALL scored paths (confirmed).

---

## Idea 1: Prefill Shared Expert Scale Array Precomputation ★★★

**Priority**: 1 (highest — pure dispatch elimination, bit-exact, ~0 bytes net)
**Component**: Prefill (25% of score) — all 39 sparse layers
**Mechanism**: The prefill shared expert halved path (LRM L8762-8780)
reconstructs the full halved scale arrays with escapes **EVERY CALL**:

```swift
// L8764-8766: gate/up scale reconstruction (per call)
let cs = concatenated([halvedFusedGateUpScales,
    concatenated([gateUpEscape.reshaped([1, 2]),
        MLXArray.zeros([1, hg - 2], dtype: .uint8)], axis: 1)], axis: 0)

// L8770-8773: down scale reconstruction (per call)
let esc = concatenated([stacked([downScalesEscape[0],
    halvedDownScales[r / 2, 0]]).reshaped([1, 2]),
    MLXArray.zeros([1, nd - 2], dtype: .uint8)], axis: 1)
let cds = concatenated([halvedDownScales, esc], axis: 0)
```

These create **3-5 fresh dispatches per call** (concatenated × 2,
stacked, MLXArray.zeros × 2, reshaped × 2) × 39 sparse layers = **~120-195
dispatches per prefill** that are pure overhead — the exact same arrays
are rebuilt every time from the same resident tensors.

### Proposed change:
Precompute `cs` and `cds` at init time in `prepareFusedSharedGateUp`
(L8446) and store as resident properties:

```swift
// Add 2 new properties (~120 B):
var _prefillGateUpFullScales: MLXArray?
var _prefillDownFullScales: MLXArray?

// In prepareFusedSharedGateUp, after L8506 (after halved scales computed):
let hg = halvedFuse.dim(1)
let cs = contiguous(concatenated([halvedFuse,
    concatenated([fuseEscape.reshaped([1, 2]),
        MLXArray.zeros([1, hg - 2], dtype: .uint8)], axis: 1)], axis: 0))
_prefillGateUpFullScales = cs
// ... similar for down scales ...
```

Then in the prefill halved path (L8762-8780), replace the inline
reconstruction with:
```swift
let cs = _prefillGateUpFullScales!
let cds = _prefillDownFullScales!
```

### Bit-exactness: YES
- The precomputed arrays are **identical** to the inline reconstruction —
  same concatenation order, same escape bytes, same zeros padding.
- `contiguous()` at init ensures the same memory layout the inline
  path would produce (the inline path's `concatenated` output is already
  contiguous by construction).
- `MLX.quantizedMM` receives bit-identical scale tensors either way.

### Bandwidth impact: NEUTRAL (dispatch savings only)
- Same bytes read (same scale arrays, just precomputed).
- Eliminates 3-5 dispatches × 39 layers = **~120-195 dispatches per prefill**.

### Expected speedup:
- 120-195 dispatches × ~2.5µs = **~300-488µs**.
- If prefill takes ~10-20ms: ~1.5-4.9% prefill speedup.
- Score: ~1.5-4.9% × 0.25 = **~0.375-1.2% score**.

### Budget impact: ~+200-300 B in LRM (net)
- 2 new `var` properties (~120 B).
- Init computation: ~6-8 lines (~300 B).
- Call site simplification: removes ~8 lines (~350 B).
- **Net: ~+70-150 B** (additions minus removed inline code).
- Fits within 948 B headroom.

### M4 testability: YES
- The precomputed arrays are built at init from the same resident
  tensors. Verify via `--local-iterate` (max_abs_diff = 0) and upstream
  equivalence.

### Why it's fresh:
No previous PR or research note has identified the per-call scale
reconstruction as a dispatch source. The prefill halved path was added
in PR #243 with the inline reconstruction as a quick implementation, and
the dispatch overhead was never analyzed.

### Risk: VERY LOW
- Pure data-flow optimization: same arrays, precomputed.
- No kernel changes, no arithmetic changes.
- The init-time computation uses the same MLX ops as the inline path.

### Student: Any student (quick win, M4-testable)

---

## Idea 2: Router Keys Dead Output Elimination ★★★

**Priority**: 2 (high — eliminates 1KB write per step × 39 layers)
**Component**: Decode (75% of score) — all 39 sparse layers
**Mechanism**: The `lagunaRouterPrecomputedKeysEnabled` flag (default ON,
LRM L168) makes the fused residual+RMSNorm+router producer kernel emit a
4th output buffer `router_keys` (256-uint32 = 1KB) per sparse layer per
decode step. **NO kernel reads `router_keys` as input.** The keys are
used solely as a nil-check guard (LRM L10485-10488) to select the
R1-halved gate/up dispatch branch. The actual gate/up kernel call at
L10499 passes `indices: inds` (the separate top-8 kernel's output),
never keys.

The producer kernel computes an extra sigmoid + IEEE-754 ordinal
transform per router row (L862-871) and writes 256 uint32 values —
**39 layers × 128 steps × 1KB = ~5MB of write traffic** + 5,120
output allocations per decode window — all wasted.

### Proposed change:
1. Always use the `v2` kernel variant (no keys output, L1003-1009):
   remove the `lagunaRouterPrecomputedKeysEnabled` conditional from
   the kernel registration and dispatch.
2. Replace the `routerKeys` guard at L10485-10488 with a flag check:
   ```swift
   if lagunaRoutedGateUpR1Enabled,
       let halvedBank = _halvedPackedRoutedGateUpBank,
       let gateUpEscape = _packedRoutedGateUpEscape
   // (remove the let routerKeys, routerKeys.dtype, routerKeys.size checks)
   ```
3. Remove `routerKeys` from the `forward` function signature and all
   plumbing (L10434-10436, L10486, L10837, L10877, L10890, L10915,
   L10934, L10962).

### Bit-exactness: YES
- The `router_keys` output is never consumed by any kernel — confirmed
  by grepping every `inputNames:` in the file. The keys are only used
  as a nil-check, not for their values.
- The `router_logits` output (the 3rd output) is byte-identical in both
  the `keys_v1` and `v2` kernel variants — the v2 variant stores
  `router_logits[router_row + r] = bfloat(router_result[r])` exactly
  as the keys variant does before the extra sigmoid/ordinal computation.
- The R1-halved gate/up dispatch selection depends on
  `lagunaRoutedGateUpR1Enabled` and the halved bank presence, not on
  the keys values. Replacing the `routerKeys` guard with these flag
  checks preserves the exact same dispatch path.

### Bandwidth impact: ~5MB write traffic eliminated per decode window
- 1KB/step × 39 layers × 128 steps = 5,120 KB of eliminated writes.
- Eliminates 5,120 output buffer allocations per decode window.
- Eliminates the extra sigmoid + ordinal computation per router row
  in the producer kernel.

### Expected speedup:
- ~5MB writes at ~400 GB/s M5 bandwidth: ~12.5µs.
- 5,120 allocations: ~5,120 × ~1µs (alloc overhead) = ~5ms.
  (But many are likely cached/merged by MLX.)
- Realistic: ~0.1-0.3% decode speedup (mostly allocation overhead).
- Score: ~0.1-0.3% × 0.75 = **~0.075-0.225% score**.

### Budget impact: **NET NEGATIVE** (~-200 to -400 B)
- Removes the conditional kernel registration (~50 B).
- Removes the `routerStore` conditional in the kernel source (~200 B).
- Removes `routerKeys` plumbing in `forward` (~8 lines, ~300 B).
- Adds flag-check replacement (~30 B).
- **Net: ~-300 to -500 B** (frees LRM headroom).

### M4 testability: YES
- The `v2` kernel variant already exists and is the non-keys fallback.
- Verify via `--local-iterate` (max_abs_diff = 0) and upstream
  equivalence.

### Why it's fresh:
The router keys were introduced to pre-compute ordinals for an R1 kernel
that consumed them, but that consumer was later replaced by
`lagunaRoutedSwiGLUQMVPackedTop8` which takes `indices` directly. The
keys output became orphaned but was never cleaned up. Previous research
notes (`NOVEL_OPTIMIZATION_TARGETS.md`) tracked the old R1 kernel's
key extraction but missed that the producer still emits the now-dead
keys buffer.

### Risk: LOW
- The keys output is genuinely dead (no kernel input consumes it).
- The R1-halved dispatch selection is preserved via flag checks.
- Need to verify the `forward` function's `routerKeys` parameter
  is not used by any other code path.

### Student: Any student (M4-testable, quick win)

---

## Idea 3: Full-Attention Params Atlas ★★☆

**Priority**: 3 (medium — eliminates per-step allocation, low absolute gain)
**Component**: Decode (75% of score) — 10 full-attention layers
**Mechanism**: `lagunaFullFusedAttention` (LRM L2276) allocates a fresh
3-element `MLXArray([UInt32(writeIdx), UInt32(writeIdx+1), UInt32(capacity)])`
per call (L2310-2312). This fires for **10 full-attention layers × 128
decode steps = 1,280 fresh 12-byte allocations** per decode window.

The sliding twin (30 layers) is **already fixed** via `lagunaRingIdxAtlas`
(L1816-1826, 512 pre-evaluated 1-element arrays, built once at warmup).
No full-attention atlas exists.

### Proposed change:
The capacity (`cacheKeys.dim(2)`) is constant during the 128-step decode
window (KVCacheSimple grows in 256-element chunks; after the 512-token
seed + first decode step growth to 768, capacity stays 768 for the
remaining 127 steps). `writeIdx` advances 0..127.

Build a parallel atlas mirroring `LagunaRingIdxAtlasStore`:

```swift
// Compact: one resident [128, 3] array + per-step row view
private enum LagunaFullParamsAtlasStore {
    nonisolated(unsafe) static var entries: [MLXArray]?
    static func get(capacity: Int) -> [MLXArray] {
        if let cached = entries { return cached }
        let atlas = (0..<128).map {
            MLXArray([UInt32($0), UInt32($0 + 1), UInt32(capacity)])
        }
        for entry in atlas { eval(entry) }
        entries = atlas
        return atlas
    }
}
```

Then in `lagunaFullFusedAttention` (L2310):
```swift
let params = lagunaFullParamsAtlasEnabled
    ? LagunaFullParamsAtlasStore.get(capacity: capacity)[writeIdx]
    : MLXArray([UInt32(writeIdx), UInt32(writeIdx + 1), UInt32(capacity)])
```

### Bit-exactness: YES
- The atlas carries the exact same `[writeIdx, writeIdx+1, capacity]`
  values the fresh allocation would produce.
- Input-independent: all 128 values built unconditionally at first use.
- Same contract as the RoPE angle atlases and the ring idx atlas.

### Bandwidth impact: NEUTRAL (allocation overhead only)
- Eliminates 1,280 fresh MLXArray allocations per decode window.

### Expected speedup:
- 1,280 allocations × ~0.5-1µs (alloc overhead) = ~640µs-1.3ms.
  (Many are likely merged by MLX's allocator.)
- Realistic: ~0.05-0.1% decode speedup.
- Score: ~0.05-0.1% × 0.75 = **~0.0375-0.075% score**.

### Budget impact: ~+400-600 B in LRM
- Atlas store enum: ~12 lines (~450 B).
- Call site change: ~3 lines (~50 B).
- Guard flag: ~2 lines (~80 B).
- Fits within 948 B headroom (but tight).

### M4 testability: YES
- The atlas is built at first use during warmup. Verify via
  `--local-iterate` (max_abs_diff = 0) and upstream equivalence.

### Why it's fresh:
Identified as "Candidate A, decode, quick win" in
`RESEARCH_IDEAS_NEXT_WAVE_20260807.md` (commit 0e821e6) and assigned as
PR #238 to askeladd, but **never merged** (no merge commit found).
The implementation was never completed. This is a re-assignment with
a more compact implementation strategy (single [128,3] array vs 128
separate arrays).

### Risk: LOW
- Same pattern as the already-merged ring atlas.
- The capacity is constant during the decode window (768), so a
  128-entry atlas is sufficient.
- If capacity changes (e.g., a longer decode window), the atlas
  rebuilds lazily.

### Student: Any student (M4-testable, quick win)

---

## Idea 4: Prefill QKV+Gate Bank Fusion ★★☆

**Priority**: 4 (medium — eliminates 1 dispatch per layer, prefill only)
**Component**: Prefill (25% of score) — all 39 sparse layers (BF16 attention)
**Mechanism**: For prefill (L > 1), the attention QKV projection uses a
fused `[Wq; Wk; Wv]` bank (`_fusedQKVWeight`, L6036) — 1 dispatch. But the
gate projection `gProj(normalizedInput)` (L6275) is a **separate dispatch**.
This is the exact same pattern already used by `callLastPrefillRow` which
fuses `[Wq; Wgate]` into `_lastPrefillQGateWeight` (L6479).

### Proposed change:
Extend `prepareFusedQKVWeight` (L5726) to optionally include the gate
weight when `gProj` is a BF16 `Linear`:

```swift
// In prepareFusedQKVWeight, after building fused [Wq; Wk; Wv]:
if let gProj, type(of: gProj) == Linear.self,
   gProj.bias == nil, gProj.weight.dtype == wq.weight.dtype,
   gProj.weight.dim(1) == wq.weight.dim(1)
{
    let fusedQKVGate = concatenated([fused, gProj.weight], axis: 0)
    _fusedQKVGateWeight = fusedQKVGate
    _fusedQKVGateSplit = fused.dim(0) // gate starts after QKV
}
```

Then in the prefill QKV branch (L6036-6046), slice the gate:
```swift
if let fusedQKVGateWeight = _fusedQKVGateWeight, L > 1 {
    let qkvGate = matmul(normalizedInput, fusedQKVGateWeight.T)
    // ... slice Q, K, V as before ...
    let gateStart = queryDim + 2 * kvDim
    projectedGate = qkvGate[.ellipsis, gateStart ..< (gateStart + nHeads)]
    gateIsActivated = false
    // Skip the separate gProj(normalizedInput) call
}
```

### Bit-exactness: YES
- Row concatenation of bias-free `Linear` weights is bit-exact: each
  output row's K-loop is independent (proven by `_lastPrefillQGateWeight`
  at L6479 which already fuses Q+gate).
- Same BF16 matmul, same K-loop, same accumulation order.
- The gate weight has the same hidden dimension as QKV weights.

### Bandwidth impact: NEUTRAL (dispatch savings only)
- Same weight bytes read (fused = concatenated, same total bytes).
- Eliminates 1 dispatch × 39 layers = **39 dispatches per prefill**.

### Expected speedup:
- 39 dispatches × ~2.5µs = ~98µs.
- If prefill takes ~10-20ms: ~0.5-1% prefill speedup.
- Score: ~0.5-1% × 0.25 = **~0.125-0.25% score**.

### Budget impact: ~+200-400 B in LRM
- 2 new properties (~120 B).
- Init extension: ~6 lines (~250 B).
- Call site change: ~4 lines (~150 B).
- **Total: ~+300-500 B**. Fits within 948 B headroom (but tight
  with Ideas 1+3).

### M4 testability: YES
- The fused bank is built at init from the same BF16 weights.
- Verify via `--local-iterate` (max_abs_diff = 0) and upstream equivalence.

### Why it's fresh:
The QKV bank fusion exists for prefill ([Wq; Wk; Wv]) and the terminal
layer already fuses [Wq; Wgate]. But no previous PR has proposed extending
the QKV bank to include the gate weight for ALL prefill layers. The
gate is a separate BF16 `Linear` with `[nHeads, hiddenSize]` weight — same
hidden dimension as QKV, so concatenation is valid.

### Risk: LOW
- Same pattern as the already-merged `_lastPrefillQGateWeight`.
- The gate is only computed when `fusedNormQKV == nil` (prefill path).
- Decode uses the fused norm+QKV+gate kernel (different mechanism).

### Student: Any student (M4-testable)

---

## Idea 5: Prefill Values Transpose Folding ★☆☆

**Priority**: 5 (low-medium — eliminates 1 dispatch per layer, small)
**Component**: Prefill (25% of score) — all 40 attention layers
**Mechanism**: For prefill (L > 1), values are transposed from
`[B, L, nKVHeads, headDim]` to `[B, nKVHeads, L, headDim]` as a separate
dispatch (LRM L6228-6229). The prefill QK-norm+RoPE kernel
(`lagunaPrefillSlidingQKNormRoPE` L2755, `lagunaPrefillFullQKNormYaRN`
L2800) already transposes Q and K in the same dispatch. Values could be
transposed in the same kernel as a passthrough (no norm, no RoPE needed
for values).

### Proposed change:
Add a `rawValues` input and a third output to the prefill QK-norm+RoPE
kernel that simply reshapes+transposes values:

```metal
// In the kernel epilogue, after Q and K are written:
// Values: just transpose [L, kvHeads, D] -> [kvHeads, L, D]
// Thread group already processes one head per group; add a values
// passthrough that copies the same L rows in transposed order.
```

### Bit-exactness: YES
- Values transpose is a pure data movement (no arithmetic).
- The kernel copies the same bytes in transposed order.

### Bandwidth impact: NEUTRAL (dispatch savings only)
- Same bytes read and written (just transposed).
- Eliminates 1 dispatch × 40 layers = **40 dispatches per prefill**.

### Expected speedup:
- 40 dispatches × ~2.5µs = ~100µs.
- If prefill takes ~10-20ms: ~0.5-1% prefill speedup.
- Score: ~0.5-1% × 0.25 = **~0.125-0.25% score**.

### Budget impact: ~+300-500 B in LRM
- Add `rawValues` to kernel input names (~30 B).
- Add values output shape (~30 B).
- Modify kernel source for values passthrough (~200-300 B).
- Modify call site to pass values and use kernel output (~100 B).
- **Total: ~+350-500 B**. Fits within 948 B headroom (very tight).

### M4 testability: YES
- The kernel is a custom Metal kernel, compiled at runtime.
- Verify via `--local-iterate` (max_abs_diff = 0) and upstream equivalence.

### Why it's fresh:
Listed as Idea 8 in `RESEARCH_IDEAS_NEXT_WAVE_20260807.md` ("Values
transpose folded into prefill QK-norm+RoPE — ~0.025-0.04% score,
~300-500B") but **never assigned or implemented**. The estimate here is
higher (~0.125-0.25%) because the dispatch count is 40 layers, not just
the prefill layers that fire the fused kernel.

### Risk: MEDIUM
- Modifying a working fused kernel to add a third output.
- The values passthrough must not interfere with the Q/K computation
  (different thread groups or a separate phase in the same dispatch).
- Kernel threadgroup memory may be tight for a third output buffer.

### Student: Any student with Metal kernel experience (M4-testable)

---

## Idea 6: Prefill eScoreCorrectionBias Float32 Hoist ★☆☆

**Priority**: 6 (low — eliminates 39 per-prefill type casts)
**Component**: Prefill (25% of score) — 39 sparse layers
**Mechanism**: The prefill router tournament/top8 path calls
`eScoreCorrectionBias.asType(.float32)` at LRM L9834, L9852, L9873, L9892.
Since the checkpoint stores the bias as BF16, this creates a fresh FP32
copy (1KB) per call. For prefill, the router is called once per sparse
layer (39 calls), creating 39 fresh allocations.

### Proposed change:
Precompute a resident FP32 copy at init time:

```swift
// In LagunaRuntimeMoEGate, add:
var _float32CorrectionBias: MLXArray?

// After weights are loaded:
_float32CorrectionBias = eScoreCorrectionBias.asType(.float32)
eval(_float32CorrectionBias!)
```

Then replace `.asType(.float32)` calls with `_float32CorrectionBias!`.

### Bit-exactness: YES
- `asType(.float32)` is a lossless upcast from BF16. The precomputed
  copy carries identical values.

### Bandwidth impact: NEUTRAL (allocation savings only)
- Eliminates 39 fresh 1KB allocations per prefill.

### Expected speedup:
- 39 allocations × ~1µs = ~39µs.
- If prefill takes ~10-20ms: ~0.2-0.4% prefill speedup.
- Score: ~0.2-0.4% × 0.25 = **~0.05-0.1% score**.

### Budget impact: ~+100-200 B in LRM
- 1 new property (~60 B).
- Init computation (~2 lines, ~80 B).
- 4 call site changes (~4 × 20 B = ~80 B).
- **Total: ~+150-250 B**. Fits within 948 B headroom.

### M4 testability: YES

### Why it's fresh:
The `.asType(.float32)` calls are in the prefill router path which was
added in the router tournament kernel PR. No previous analysis has
identified these per-call casts as allocation sources.

### Risk: VERY LOW

### Student: Any student (M4-testable, quick win)

---

## Idea 7: callLastPrefillRow QK-norm+RoPE Fusion ★☆☆

**Priority**: 7 (low — 1 layer only, marginal)
**Component**: Prefill (25% of score) — layer 39 only (last prefill layer)
**Mechanism**: `callLastPrefillRow` (LRM L6455) uses separate dispatches
for Q-norm, K-norm, Q-RoPE, K-RoPE (L6495-6504) — **4 dispatches** —
while regular prefill layers use 1 fused dispatch. Since this is the
last layer (1 call per prefill), the gain is marginal.

### Proposed change:
Reuse the existing prefill QK-norm+RoPE kernel for the last layer's
Q (which has L==1) and K (which has L==L). The kernel already handles
arbitrary L for K. For Q (L==1), the existing decode QK-norm+RoPE
kernel would work.

### Bit-exactness: YES (same fused kernel, same math)

### Expected speedup:
- 1 layer × 2-3 dispatches × ~2.5µs = ~5-7.5µs.
- Score: ~0.025-0.038% × 0.25 = **~0.006-0.009% score**.
- Below 0.05% threshold — marginal.

### Budget impact: ~+200-400 B in LRM

### M4 testability: YES

### Why it's fresh:
Listed as Idea 4 in `RESEARCH_IDEAS_NEXT_WAVE_20260807.md` but
**never assigned**. The last prefill layer has its own attention path
that doesn't use the fused kernels.

### Risk: LOW

### Student: Low priority — fold into a cleanup PR

---

## Summary Table

| # | Idea | Component | Mechanism | Est. Score | Budget (LRM) | M4? | Priority |
|---|---|---|---|---|---|---|---|
| 1 | Prefill shared scale precompute | Prefill | 120-195 dispatch/elim | ~0.375-1.2% | ~+70-150 B net | YES | **HIGH** |
| 2 | Router keys dead output | Decode | 1KB/step write elim | ~0.075-0.225% | **NET NEGATIVE** | YES | **HIGH** |
| 3 | Full-attention params atlas | Decode | 1280 alloc elim | ~0.0375-0.075% | ~+400-600 B | YES | **MEDIUM** |
| 4 | Prefill QKV+gate bank | Prefill | 39 dispatch elim | ~0.125-0.25% | ~+300-500 B | YES | **MEDIUM** |
| 5 | Prefill values transpose fold | Prefill | 40 dispatch elim | ~0.125-0.25% | ~+350-500 B | YES | LOW-MED |
| 6 | eScoreCorrectionBias hoist | Prefill | 39 cast elim | ~0.05-0.1% | ~+150-250 B | YES | LOW |
| 7 | callLastPrefillRow QK-norm fuse | Prefill | 2-3 dispatch (1 layer) | ~0.006% | ~+200-400 B | YES | LOW |

## Composition Plan

### Minimal set (fits 948 B easily):
- **Idea 1** (~+70-150 B net) + **Idea 2** (net negative) = **~+0.45-1.4% score**
  combined, ~~-150 to +150 B net budget. Leaves ~800 B headroom.

### Extended set (fits with careful budgeting):
- Ideas 1+2+3+6 = ~+0.55-1.6% score, ~+450-1000 B net.
  Tight but potentially feasible within 948 B.

### Full set (requires vendor file or careful pruning):
- All 7 ideas = ~+0.85-2.1% score, ~+1500-2500 B net.
  Exceeds 948 B LRM headroom. Would need to move some kernel source
  to vendor files (which have ample headroom).

### Key insight:
Ideas 1 and 2 are the strongest because they are pure dispatch/overhead
elimination with minimal or negative byte cost. Idea 1 targets the
prefill path (relatively unoptimized) and Idea 2 targets the decode
path (75% weight). Both compose with the current frontier (ad58c92)
without interfering with in-flight work.

## Verification Approach

All ideas are M4-testable (no _nax kernel changes). Verify each via:
1. `swift test --force-resolved-versions` (correctness)
2. `./benchmark.sh --local-iterate` (max_abs_diff = 0, timing)
3. `research/run_upstream_equivalence.sh` (oracle equivalence)
4. `./benchmark.sh --local-submit` before promotion

## What Was Checked and Ruled Out (this analysis)

- **Vendor _nax scale halving**: Fully deployed on ALL scored paths
  (confirmed by deep analysis of fp_quantized_nax.h and quantized.cpp).
  Non-halved vendor kernels are unreachable fallbacks on M5.
- **Dense MLP quantization**: 100.6 MB/step BF16 — BLOCKED by accepted
  envelope (only Q/K/V/O + g_proj allowed).
- **Router BF16 weight quantization**: BLOCKED by accepted envelope.
- **Prefill attention mega-fusion** (SDPA + cache + gate + O-proj): HIGH
  risk, 32KB threadgroup limit, killed the 1-pass epilogue. NOT feasible.
- **lm_head optimization**: Already has certified two-pass pruner (int5
  coarse + argmax + threshold + exact). No per-step allocations.
  Fully optimized.
- **KV cache movement**: Both attention families already fuse QK-norm+RoPE
  + in-place KV write + SDPA into 1 dispatch. KV cache quant BLOCKED.
- **Attention dispatch count**: Decode is fully fused (1 dispatch for
  attention, 1 for gate+O-proj). Prefill has ~10-12 dispatches/layer but
  the O-proj gate fusion via MLX compile() was REFUTED.
- **Affine INT8 gather halving**: Not applicable (affine = scale*w+bias,
  NVFP4 pairwise-constancy doesn't apply).
- **Threadgroup geometry tuning**: DARKBLOOM_STAGE_BM128=5 (shipped
  default), variants 0-5 enumerated. 0-byte knob but needs M5
  measurement; AGENTS.md warns geometry can flip sign across core counts.
