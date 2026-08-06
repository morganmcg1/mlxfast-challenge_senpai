# Novel Kernel Fusion & Dispatch Elimination Opportunities — Laguna XS 2.1 Decode Path

**Researcher:** Metal kernel optimization subagent
**Date:** 2026-08-06
**Scope:** `Sources/MLXFastModel/LagunaRuntimeModel.swift` — decode path dispatch audit and fusion hypotheses
**Scoring context:** Decode is 75% of score. `score = decode_speedup^0.75 * prefill_speedup^0.25`. 40 decoder layers (39 sparse MoE + 1 dense layer-0).

---

## Part 1: Complete Decode Dispatch Map (Per Layer)

Each decode step runs through all 40 layers. Below is the dispatch map for the **promoted default configuration** (all fusion flags ON, INT8 affine O-proj, NVFP4 MoE, packed scales, producer router keys).

### Dense Layer (Layer 0) — 5 dispatches

| # | Dispatch | Kernel/Op | Lines | Notes |
|---|---------|-----------|-------|-------|
| 1 | Fused QKV | `lagunaFusedQKV` (if enabled) or 3 separate Q/K/V projections | ~5900 | INT8 affine fusion; NVFP4 fusion is PR #78 (in progress) |
| 2 | Fused QK-norm+RoPE+SDPA+cache | Single kernel | ~5700 | Sliding or full variant |
| 3 | Fused gated O-proj | `lagunaGatedAffineOProj` | 5959 | Gate product + GEMV in one dispatch |
| 4 | Fused residual+RMSNorm | `lagunaResidualRMSNorm` | 10279 | Post-attention residual + norm |
| 5 | Fused dense gate/up+SwiGLU + down+residual | `lagunaDenseGateUpSwiGLU` + `lagunaDenseDownResidual` | 8249, 8256 | 2 dispatches (gate/up fused, down+residual fused) |

**Layer 0 total: ~5 dispatches** (QKV may be 1 or 3 depending on flag; gate/up and down are 2 separate dispatches).

### Sparse MoE Layers (Layers 1–39) — 5 dispatches each

| # | Dispatch | Kernel/Op | Lines | Notes |
|---|---------|-----------|-------|-------|
| 1 | Fused QKV projection | `lagunaFusedQKV` or 3 separate | ~5900 | Same as dense, INT8 affine |
| 2 | Fused QK-norm+RoPE+SDPA+cache | Single kernel | ~5700 | Sliding (layers 1,5,9...) or full (layers 3,7,11...) |
| 3 | Fused gated O-proj | `lagunaGatedAffineOProj` | 5959 | Gate product + INT8 GEMV |
| 4 | Fused residual+RMSNorm+router | `lagunaResidualRMSNormRouter` | 10262 | Post-attention residual + norm + router GEMV (3→1) |
| 5 | Fused routed gate/up SwiGLU QMV | `lagunaRoutedSwiGLUQMVPackedTop8` | 9955 | 8 experts, packed scales, producer keys |
| 6 | Shared gate/up SwiGLU QMV | `lagunaSharedSwiGLUQMV` | 8136 | **UNFUSED** — separate dispatch from routed QMV |
| 7 | Fused routed+shared down+residual | `lagunaRoutedSharedDownResidual` | 10023 | 8 routed down + 1 shared down + 2 residual adds in one dispatch |

**Sparse layer total: ~7 dispatches** (with current fusions; without the shared QMV being merged, it's dispatch #6 as a standalone).

**Correction/Refinement:** The routed QMV (dispatch #5) and shared QMV (dispatch #6) are currently **two separate dispatches** despite both reading the same 2048-wide normalized input `x`. The `mergedSharedActivated` variable (line 9931) was scaffolded to merge these but is **never assigned** — always `nil`. The `fusedSharedDownInputs` (line 8125) falls back to `lagunaSharedSwiGLUQMV(...)` at line 8136 whenever `sharedActivation` is nil.

### Full Decode Step Dispatch Budget

| Component | Dispatches | Notes |
|-----------|-----------|-------|
| 39 sparse layers × 7 | 273 | |
| 1 dense layer × 5 | 5 | |
| Final RMSNorm | 1 | Stock MLX `model.norm(...)` — **unfused** |
| lm_head pruner | 4 | Coarse + argmax + threshold + exact |
| Embedding lookup | 1 | |
| **Total per step** | **~284** | |

---

## Part 2: Key Findings — Answering the 6 Research Questions

### Q1: What dispatches remain UNFUSED in the decode path?

**Identified unfused dispatches:**

1. **Shared expert gate/up QMV** (line 8136, `lagunaSharedSwiGLUQMV`) — runs as a separate dispatch from the routed gate/up QMV despite both consuming the identical normalized input `x`. The `mergedSharedActivated` scaffold (line 9931) exists specifically to merge this but was never activated.

2. **Final RMSNorm** (stock MLX `model.norm(...)`) — runs as a standalone dispatch before the lm_head pruner. Not fused with the last layer's output or the lm_head coarse pass.

3. **Dense layer-0 gate/up and down** — these are 2 separate dispatches (`lagunaDenseGateUpSwiGLU` + `lagunaDenseDownResidual`), already fused internally but not fused with each other.

4. **Attention QKV** — when `DARKBLOOM_FUSED_QKV` is OFF (the default!), Q/K/V are 3 separate dispatches. The fusion flag ships opt-in because "ablation showed a mild prefill cost with no decode gain" (line 112). **This is a known null result for decode.**

5. **Post-attention residual add** — when `lagunaFusedResidualRMSNormRouterEnabled` declines (e.g., dtype mismatch), falls back to `h = x + r` (line 10296) as a separate elementwise dispatch before `postAttentionLayerNorm(h)` (line 10297).

### Q2: Can the shared expert gate/up be fused with the routed gate/up dispatch?

**YES — and the code already has the scaffold for it.**

- `mergedSharedActivated` (line 9931) is declared `var mergedSharedActivated: MLXArray?` but is **never assigned** anywhere in the codebase. It is always `nil`.
- `fusedSharedDownInputs` (line 8125) consumes it: `sharedActivation ?? lagunaSharedSwiGLUQMV(...)` (line 8134-8140). Since it's always nil, the shared QMV always fires as a separate dispatch.
- **Both kernels read the identical 2048-wide BF16 input `x`** (the normalized hidden state). The routed QMV reads from `input` parameter (line 7460-7461), the shared QMV reads from `x` (line 8136-8139). Same data, same shape `[1, 1, 2048]`.
- **The kernels have compatible grid geometry:** Routed uses `numExpertsPerTok * 128 * 64 = 65536` threadgroups (line 7481) or `8 * 256 * 64 = 131072` (R1 variant, line 7470). Shared uses `128 * 64 = 8192` threadgroups (line 6691) or `256 * 64 = 16384` (rows1 variant, line 6688-6691). Both use `(64, 1, 1)` threadgroup size.
- **Key challenge:** The routed QMV outputs `[1, 1, 8, 1, 512]` (8 experts × 512 intermediate) while the shared QMV outputs `[1, 1, 512]` (shared expert's 512 intermediate). Different output shapes, different weight bank layouts (routed uses packed scales with producer keys; shared uses fused gate/up weight + scales). A merged kernel would need to handle both weight formats in one dispatch.

**Verdict:** Feasible. The scaffold exists. The input reuse is identical. The main work is writing a single Metal kernel that handles both routed (gather-QMV with 8 expert indices) and shared (direct QMV) weight banks in one grid dispatch, with shared computing its SwiGLU activation in a separate set of threadgroups.

### Q3: Can the post-attention residual add be fused with the next layer's input norm?

**Already done** — but only for sparse layers. The `lagunaResidualRMSNormRouter` kernel (line 10262) fuses:
- Post-attention residual add (`x + r`)
- RMSNorm
- Router GEMV

This produces `h` (residual) and `normalized` (normed + router logits/keys) in one dispatch. The `normalized` output feeds directly into the MoE block.

**However**, the next layer's *input* norm (the `inputLayerNorm` at line 10227) is a **separate concept** — it normalizes the input *before* attention, not after. The current flow is:

```
Layer N output → Layer N+1 input → inputLayerNorm → attention → postAttentionLayerNorm
```

The `inputLayerNorm` is fused into the attention block's QKV projection path (INT8 fusion) but only when `lagunaFusedQKV` is enabled. When it's OFF (default), the input norm runs as a standalone RMSNorm dispatch.

**Opportunity:** Fuse `inputLayerNorm` into the attention QKV projection even for NVFP4 (PR #78 is working on this for INT8; the NVFP4 variant would extend it).

### Q4: Are there MLX elementwise ops that could be fused into adjacent custom kernels?

**Identified candidates:**

1. **Final RMSNorm** (`model.norm(...)`, stock MLX) → could be fused into the lm_head coarse pass. The lm_head pruner's coarse kernel (line 939-954) reads the hidden state `x` (2048 BF16 values). The RMSNorm is a simple `x * rsqrt(mean(x²) + eps) * weight` operation that could be prepended to the coarse kernel's GEMV, eliminating one dispatch.

2. **`h + r2` residual add** (line 10334) — the fallback path when fusion flags decline. Already fused in the promoted path via `lagunaRoutedSharedDownResidual`.

3. **`residual + (reduced + sharedOut)`** (line 10142) — the fallback when `lagunaFusedRoutedSharedDownResidualEnabled` declines. Already handled.

4. **Router weight scaling** (`reduced * routedScalingFactor`, line 10140/10190) — currently a separate elementwise multiply. When `routedScalingFactor == 1.0` (check at line 10018), it's skipped. The constant is `moeRoutedScalingFactor` — need to verify its value.

### Q5: Could the router GEMV be fused with the previous dispatch (attention O-proj or post-attention residual)?

**Already done.** The `lagunaResidualRMSNormRouter` kernel (line 10262) fuses the router GEMV with the post-attention residual add and RMSNorm. This is one of the most aggressive fusions in the codebase (3 ops → 1 dispatch).

**Remaining opportunity:** The router GEMV cannot be fused *further back* into the attention O-proj because:
- The O-proj output (`r`) must be fully computed before the residual add (`x + r`)
- The router GEMV needs the *normalized* residual, not the raw O-proj output
- There's a data dependency chain: O-proj → residual add → RMSNorm → router GEMV

The `lagunaResidualRMSNormRouter` already collapses the last 3 steps. Fusing the O-proj would require the O-proj kernel to also read `x` (the pre-attention residual) and compute the full chain — possible but would make the O-proj kernel much more complex and would break the clean separation between attention and MoE blocks.

### Q6: Is there any opportunity to overlap compute between layers using async dispatch?

**Already extensively explored and optimized.** The `lagunaDecodeAsyncStage` system (line 677) fires `asyncEval` at specific layer boundaries to enqueue already-constructed work earlier. The default schedule `at:0,1,7,15,23,31,39` (line 680) fires after layers 0, 1, 7, 15, 23, 31, 39 — 7 fires per step.

Key findings from the codebase notes (line 660-676):
- `off` is 10.3735 ms, `ladder8` was 9.4533 ms (+9.7% overlap gain)
- The current default `at:0,1,7,15,23,31,39` captures "essentially all" remaining overlap prize
- Adding one rung at layer 1 to `ladder8` is "worth as much as quadrupling the ladder"
- A lone fire at layer 1 alone is worthless (0.9476, worst schedule tested)

**Remaining opportunity is marginal.** The async ladder has been thoroughly swept. The front-edge rung at layer 0 and layer 1 together capture the widest GPU-idle window. Further async optimization would require structural changes to the graph construction order, not just boundary placement.

---

## Part 3: Top 5 Novel Fusion Hypotheses

### Hypothesis 1: Merge Shared Gate/Up QMV into Routed Gate/Up QMV Dispatch (Activate `mergedSharedActivated`)

**What to fuse:** Combine `lagunaRoutedSwiGLUQMVPackedTop8` (line 9955) and `lagunaSharedSwiGLUQMV` (line 8136) into a single Metal kernel dispatch.

**Mechanism:**
- Both kernels read the identical 2048-wide BF16 normalized input `x`
- The merged kernel dispatches both routed (8 experts × 512 output) and shared (512 output) SwiGLU QMV work in one grid
- The shared QMV output is written to a separate output region and returned via `mergedSharedActivated` (already scaffolded at line 9931)
- `fusedSharedDownInputs` (line 8125) receives the pre-computed shared activation, skipping the separate `lagunaSharedSwiGLUQMV` dispatch

**Expected dispatch savings:** **1 dispatch per sparse layer × 39 layers = 39 dispatches per decode step.** From ~284 to ~245 total dispatches (−13.7%).

**Expected time savings:** Each dispatch has ~2.5 µs overhead (from notes/47 empty-dispatch measurements: 2.46 µs per dispatch). 39 × 2.5 µs = ~97.5 µs per step. At ~9.4 ms/step, this is ~1.0% decode speedup. The actual savings may be higher if the shared QMV kernel has additional fixed costs (threadgroup launch, barrier synchronization).

**Additional benefit:** The shared kernel's 2048-wide input read (4 KB) can be amortized with the routed kernel's input read — both read the same `x`. In the merged kernel, threadgroups handling the shared expert reuse the input already loaded by routed-expert threadgroups if they share a threadgroup memory tile. This saves one full 4 KB DRAM read per layer.

**Correctness risk:** LOW. The `mergedSharedActivated` scaffold and `fusedSharedDownInputs` API already exist and are designed for exactly this. The arithmetic is independent per output row (each QMV row has its own K-loop and scale application). The shared expert's SwiGLU activation (gate × sigmoid(gate) × up) is computed identically whether in a separate or merged kernel. The only risk is ensuring the merged kernel writes the shared output to the correct buffer location and that `mergedSharedActivated` is properly assigned before `fusedSharedDownInputs` consumes it.

**Implementation complexity:** MEDIUM. Requires:
1. Writing a new `lagunaRoutedSharedSwiGLUQMVPackedTop8` Metal kernel that handles both routed (gather-QMV with expert indices) and shared (direct QMV) weight banks
2. The kernel needs two output regions: `[1, 1, 8, 1, 512]` for routed and `[1, 1, 512]` for shared
3. Threadgroup assignment: first N threadgroups handle routed experts, remaining handle shared
4. Assign `mergedSharedActivated` in the Swift dispatch code (line ~9960) instead of leaving it nil
5. Verify the `fusedSharedDownInputs` path (line 10005-10006) correctly receives the pre-computed activation

**Priority: HIGH** — scaffold exists, 39 dispatch savings, low correctness risk.

---

### Hypothesis 2: Fuse Final RMSNorm into lm_head Coarse Pass

**What to fuse:** Merge the stock MLX `model.norm(...)` (final RMSNorm, runs before lm_head) into the first dispatch of the lm_head pruner's coarse kernel (line 939-954).

**Mechanism:**
- The final RMSNorm computes `x * rsqrt(mean(x²) + eps) * weight` over the 2048-wide hidden state
- The lm_head coarse kernel (`lagunaLmHeadInt5BaseCoarseKernel` or `lagunaLmHeadInt5CoarseRatioBoundDeltaBF16Kernel`) reads this 2048-wide `x` as its first input
- The RMSNorm can be computed inline at the start of each coarse kernel thread, transforming the input before the int5 GEMV begins
- The norm weight (2048 BF16 values) and eps are passed as additional kernel inputs

**Expected dispatch savings:** **1 dispatch per decode step.** From ~245 to ~244. Small in count, but the final RMSNorm is on the critical path (it's the last op before lm_head, no async overlap possible after it).

**Expected time savings:** One RMSNorm dispatch ≈ 2.5–5 µs. At ~9.4 ms/step, ~0.05% decode speedup. Small but free if the coarse kernel has register/compute headroom.

**Correctness risk:** MEDIUM. The RMSNorm involves a reduction (mean of squares) across the 2048-wide vector, which requires cross-threadgroup communication or a two-phase approach. The coarse kernel uses 512-thread threadgroups with `vocab/16 * 512` grid (line 943). The RMSNorm reduction would need to be computed once and broadcast, or computed redundantly per threadgroup (cheap: 2048 floats, ~8 KB, fits in registers/threadgroup memory). The BF16 rounding boundaries of the RMSNorm must be preserved exactly.

**Implementation complexity:** MEDIUM-HIGH. Requires:
1. Adding RMSNorm weight and eps as kernel inputs
2. Computing the mean-of-squares reduction (either per-threadgroup with threadgroup memory, or as a separate pre-pass within the same dispatch)
3. Applying the normalization before the int5 dequantization GEMV
4. Ensuring BF16 rounding matches stock MLX RMSNorm exactly
5. The coarse kernel has two variants (refine and non-refine); both need the fusion

**Priority: MEDIUM** — only 1 dispatch saving, but it's on the critical path and conceptually clean.

---

### Hypothesis 3: Fuse Dense Layer-0 Gate/Up+SwiGLU with Down+Residual into a Single Dispatch

**What to fuse:** Combine `lagunaDenseGateUpSwiGLU` (line 8249) and `lagunaDenseDownResidual` (line 8256) into one kernel dispatch for layer 0.

**Mechanism:**
- The gate/up kernel produces a 8192-wide BF16 activation
- The down kernel reads this activation and produces a 2048-wide output + residual add
- These are currently 2 separate dispatches with a materialized intermediate activation
- A fused kernel would compute the gate/up GEMV, SwiGLU activation, down GEMV, and residual add in one dispatch
- The 8192-wide intermediate would live only in threadgroup memory or registers, never materialized to DRAM

**Expected dispatch savings:** **1 dispatch** (layer 0 only). From ~244 to ~243.

**Expected time savings:** One dispatch overhead (~2.5 µs) plus elimination of the 8192-element BF16 intermediate write+read (16 KB write + 16 KB read = 32 KB DRAM traffic saved). At ~9.4 ms/step, ~0.05% decode speedup from dispatch + bandwidth savings.

**Correctness risk:** MEDIUM-HIGH. The fused kernel must preserve:
1. The exact BF16 rounding of the SwiGLU activation (gate × sigmoid(gate) × up) — currently a BF16 boundary between the two kernels
2. The down GEMV accumulation order
3. The residual add rounding (`h + down_result`)

The key challenge is that the down GEMV needs the *full* 8192-wide activation as input, but the gate/up kernel produces it row-by-row. A fused kernel would need to either (a) store the activation in threadgroup memory (8192 × 2 bytes = 16 KB, fits in a 32 KB threadgroup memory budget), or (b) use a split-K approach where each down-projection row re-computes its needed activation slice.

**Implementation complexity:** HIGH. The gate/up kernel uses `rows_per_group = 64` with 8192/64 = 128 tiles. The down kernel reads all 8192 input values per output row. A fused kernel would need a two-phase threadgroup approach: phase 1 computes all 8192 gate/up activations into shared memory, phase 2 computes the 2048 down projections from shared memory. This requires barrier synchronization within the threadgroup and careful memory management.

**Priority: LOW** — only 1 dispatch saving for 1 layer, high implementation complexity, and the intermediate is only 16 KB (bandwidth savings are minimal).

---

### Hypothesis 4: Fuse Input RMSNorm into QKV Projection for NVFP4 Attention Layers (Extend PR #78)

**What to fuse:** The `inputLayerNorm` (RMSNorm before attention, line 10227) is currently fused into the QKV projection only for INT8 affine attention layers. For NVFP4 attention layers (the tail layers), the input norm runs as a separate dispatch.

**Mechanism:**
- PR #78 is implementing NVFP4 fused norm+QKV for the attention layers
- This hypothesis extends that to ensure ALL attention layers (both INT8 affine and NVFP4) have the input norm fused into the QKV projection
- The norm is computed inline in the QKV GEMV kernel, reading the raw hidden state and norm weight

**Expected dispatch savings:** Depends on how many layers use NVFP4 vs INT8 attention. If the NVFP4 layers currently run a separate input norm, this saves 1 dispatch per NVFP4 attention layer. With the current architecture, attention layers alternate sliding/full, and the quantization may differ by layer group.

**Expected time savings:** If N layers have unfused NVFP4 input norm, N × ~3 µs = ~3N µs. For N=10, ~30 µs (~0.3% decode speedup).

**Correctness risk:** LOW-MEDIUM. The INT8 fusion (already shipped) proves the pattern works. Extending to NVFP4 requires the same RMSNorm inline computation but with a different dequantization path (NVFP4 4-bit vs INT8 8-bit).

**Implementation complexity:** MEDIUM. This is a natural extension of PR #78's work. The NVFP4 QKV kernel needs to prepend the RMSNorm computation, same as the INT8 variant already does.

**Priority: MEDIUM** — depends on PR #78's scope. If PR #78 already covers all layers, this is moot. If it only covers INT8, this is a natural follow-up.

---

### Hypothesis 5: Fuse Router Weight Scaling into Routed+Shared Down+Residual Kernel

**What to fuse:** The router weight scaling (`reduced * routedScalingFactor`, line 10140/10190) is currently a separate elementwise multiply when `routedScalingFactor != 1.0`. The `lagunaRoutedSharedDownResidual` kernel (line 10023) already handles the router weight application but may not apply the scaling factor.

**Mechanism:**
- Check if `moeRoutedScalingFactor` is 1.0 (in which case this is already a no-op, guarded at line 10018)
- If it's not 1.0, the scaling factor multiply could be folded into the `lagunaRoutedSharedDownResidual` kernel's per-expert reduction, applying `routerWeight * routedScalingFactor` instead of just `routerWeight`
- This eliminates the separate `reduced * routedScalingFactor` dispatch in the fallback paths (lines 10140, 10190)

**Expected dispatch savings:** **0 in the promoted path** (the guard at line 10018 checks `routedScalingFactor == Float(LagunaConstants.moeRoutedScalingFactor)` and the `lagunaRoutedSharedDownResidual` kernel handles the full chain). This only saves dispatches in fallback paths.

**Expected time savings:** Negligible in promoted path. Only relevant for fallback/debugging configurations.

**Correctness risk:** LOW. The scaling is a simple per-element multiply that can be folded into the existing accumulation.

**Implementation complexity:** LOW. One additional multiply in the kernel's reduction loop.

**Priority: LOW** — only benefits fallback paths, not the promoted configuration.

---

## Part 4: Summary & Recommendations

| # | Hypothesis | Dispatch Savings | Correctness Risk | Complexity | Priority |
|---|-----------|-----------------|-----------------|------------|----------|
| 1 | Merge shared QMV into routed QMV (activate `mergedSharedActivated`) | 39/step | LOW | MEDIUM | **HIGH** |
| 2 | Fuse final RMSNorm into lm_head coarse | 1/step | MEDIUM | MEDIUM-HIGH | MEDIUM |
| 3 | Fuse dense layer-0 gate/up + down+residual | 1/step | MEDIUM-HIGH | HIGH | LOW |
| 4 | Fuse input RMSNorm into NVFP4 QKV (extend PR #78) | N/step | LOW-MEDIUM | MEDIUM | MEDIUM |
| 5 | Fuse router scaling into down+residual kernel | 0 (promoted) | LOW | LOW | LOW |

### Primary Recommendation

**Hypothesis 1 is the clear winner.** It has:
- The highest dispatch savings (39 per step, 13.7% reduction)
- An existing code scaffold (`mergedSharedActivated`, `fusedSharedDownInputs`) designed for exactly this purpose
- Low correctness risk (independent per-row arithmetic, identical input)
- Medium implementation complexity (one new Metal kernel + Swift wiring)
- The input reuse benefit (both kernels read the same 2048-wide `x`) provides additional DRAM bandwidth savings beyond the dispatch overhead

The fact that `mergedSharedActivated` was declared but never assigned suggests this fusion was planned but not completed — possibly blocked on the Metal kernel implementation. This is the lowest-hanging fruit in the entire decode path.

### Secondary Recommendation

**Hypothesis 2** (fuse final RMSNorm into lm_head) is worth investigating as a quick win if the coarse kernel has register headroom. It's on the critical path (no async overlap possible after the last layer) and conceptually clean, though the cross-vector reduction adds complexity.

### Notes on Already-Optimized Areas

- **Async dispatch overlap** (Q6) has been thoroughly swept. The default `at:0,1,7,15,23,31,39` schedule captures "essentially all" remaining overlap prize (line 663-664). Further gains require structural graph changes, not boundary tuning.
- **Post-attention residual+norm+router** (Q3, Q5) is already maximally fused via `lagunaResidualRMSNormRouter` (3→1). Cannot fuse further back without breaking attention/MoE separation.
- **Fused QKV** (Q1) is known to be a decode null result (line 112: "mild prefill cost with no decode gain"). Do not pursue unless the NVFP4 variant (PR #78) changes the balance.

---

## Appendix: Key Line References

| Feature | File Line | Description |
|---------|-----------|-------------|
| `mergedSharedActivated` declaration | 9931 | `var mergedSharedActivated: MLXArray?` — always nil |
| `fusedSharedDownInputs` | 8125 | Consumes `sharedActivation ?? lagunaSharedSwiGLUQMV(...)` |
| `lagunaSharedSwiGLUQMV` call (fallback) | 8136 | Always fires because mergedSharedActivated is nil |
| `lagunaRoutedSwiGLUQMVPackedTop8` | 9955 | Routed gate/up QMV (8 experts) |
| `lagunaRoutedSharedDownResidual` | 10023 | Fused down + residual (8 routed + 1 shared) |
| `lagunaResidualRMSNormRouter` | 10262 | Fused residual + norm + router (3→1) |
| `lagunaGatedAffineOProj` | 5959 | Fused gated O-proj (gate + GEMV) |
| `lagunaDenseGateUpSwiGLU` | 8249 | Layer-0 dense gate/up + SwiGLU |
| `lagunaDenseDownResidual` | 8256 | Layer-0 dense down + residual |
| lm_head pruner `logits()` | LagunaLmHeadPrune.swift:924 | 4-dispatch lm_head |
| `lagunaDecodeAsyncStage` default | 680 | `at:0,1,7,15,23,31,39` |
| Final RMSNorm (stock MLX) | ~10851 | `model.norm(...)` before lm_head |
