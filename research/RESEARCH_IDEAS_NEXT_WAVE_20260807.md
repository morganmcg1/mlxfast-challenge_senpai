# Next-Wave Optimization Ideas — 2026-08-07 (Deep Codebase Analysis)

Ranked list of NOVEL, untried bit-exact bandwidth-reduction and
dispatch-elimination opportunities found by deep analysis of the scored
decode/prefill paths, vendor `_nax` kernel dispatch, shared expert prefill
path, prefill O-proj dispatch chain, and the `attentionGateProjection`
compiled function.

## Context

- Current best: 2.5748. Target: 2.5888 (gap: +0.55%).
- M5 is bandwidth-bound at ~89% GPU utilization. Only levers: read fewer
  bytes or eliminate dependent dispatches.
- Score = decode_speedup^0.75 × prefill_speedup^0.25. Both ≥ 0.95.
- Decode is extensively fused (norm+QKV, gate+O-proj, RoPE+SDPA+KV-write,
  routed+shared down+residual, dense SwiGLU+down+residual, lm_head prune).
- Prefill is relatively unoptimized: stock attention, stock shared expert,
  3-dispatch O-proj gate chain, unhalved shared expert scales.

## Budget Constraints (verified)

| File | Size | Limit | Headroom |
|---|---|---|---|
| LagunaRuntimeModel.swift | 514,701 | 524,288 | **9,587 B** |
| fp_quantized_nax.h | 78,440 | 524,288 | 445,848 B |
| quantized.cpp | 83,766 | 524,288 | 440,522 B |
| LagunaLmHeadPrune.swift | 46,738 | 524,288 | 477,550 B |
| Total surface | 2,975,392 | 3,000,000 | **24,608 B** |

LRM is the binding constraint at 9,587 B. Vendor files have ample headroom.

---

## Idea 1: Prefill Shared Expert Gate/Up Dispatch Fusion ★★★

**Priority**: 1 (highest)
**Component**: Prefill (25% of score) — all 39 sparse layers
**Mechanism**: The shared expert's prefill path uses 4 separate dispatches:
1. `gateProj(x)` — NVFP4 `quantizedMM`, 1 dispatch
2. `upProj(x)` — NVFP4 `quantizedMM`, 1 dispatch
3. `compiledSiluProduct(gate, up)` — compiled elementwise, 1 dispatch
4. `downProj(activated)` — NVFP4 `quantizedMM`, 1 dispatch

Dispatches 1 and 2 are independent (same input `x`), but MLX does not
automatically overlap them within a layer — they are separate GEMM
dispatches. The fused gate/up bank (`_fusedGateUpWeight`) is already
built at init time (`prepareFusedSharedGateUp`, L8298) but only used for
decode (gated by `x.dim(1) == 1` at L8556).

### Proposed change:
The decode fallback at L8585-8594 already uses `MLX.quantizedMM` over the
fused bank (gated by `x.dim(1) == 1`). Simply add a prefill branch that
reuses the identical `quantizedMM` call:

```swift
// In LagunaRuntimeMLP.callAsFunction, after the x.dim(1) == 1 block:
// NEW prefill branch (L > 1):
if x.dim(1) > 1,
   let fusedWeight = _fusedGateUpWeight,
   let fusedScales = _fusedGateUpScales,
   x.dtype == .bfloat16,
   fusedWeight.dtype == .uint32,
   fusedScales.dtype == .uint8
{
    lagunaTrace("shared fused [gate; up] bank QMM (prefill)")
    let gateUp = MLX.quantizedMM(
        x, fusedWeight, scales: fusedScales, biases: nil,
        transpose: true, groupSize: 16, bits: 4, mode: .nvfp4)
    let gate = gateUp[.ellipsis, 0 ..< _fusedGateUpSplit]
    let up = gateUp[.ellipsis, _fusedGateUpSplit...]
    return downProj(compiledSiluProduct(gate, up))
}
// Stock fallback:
return downProj(compiledSiluProduct(gateProj(x), upProj(x)))
```

The `quantizedMM` call is identical to the decode fallback (L8585-8594) —
just with L > 1 input. No new kernel needed.

### Bit-exactness: YES
- `quantizedMM` over the fused bank computes the same dot products as
  two separate `quantizedMM` calls. The fused bank concatenates gate and
  up weights along axis 0 (rows). Each output row is an independent dot
  product — the matmul is row-wise independent.
- The splitting (`gateUp[.ellipsis, 0..<split]` and `gateUp[.ellipsis,
  split...]`) is a zero-copy view operation.
- `compiledSiluProduct` receives identical inputs either way.
- No FP reduction order changes — same K-loop, same accumulation.

### Bandwidth impact: NEUTRAL (dispatch savings only)
- Same weight bytes read (fused bank = gate + up concatenated).
- Same input read once (vs twice for separate calls — but x is L2-cached).
- Eliminates 1 dispatch per layer (2 separate GEMMs → 1 fused GEMM).

### Expected speedup:
- 39 layers × 1 dispatch eliminated × ~2.5 µs = ~98 µs.
- If prefill takes ~10-20 ms: ~0.5-1% prefill speedup.
- Score: ~0.5-1% × 0.25 = **~0.125-0.25% score**.

### Budget impact: ~200-300 B in LRM
- Add ~15 lines for the prefill fused gate/up path + guards.
- Fits within 9,587 B headroom.

### M4 testability: YES
- The fused bank is built for both decode and prefill (init-time).
- `quantizedMM` (non-gather) works on M4 (not `_nax`-gated).
- Verify via `--local-iterate` (max_abs_diff = 0) and upstream equivalence.

### Why it's fresh:
The fused gate/up bank is built at init but the `quantizedMM` over it
is gated by `x.dim(1) == 1` (L8556). The prefill path falls to stock
`gateProj(x)` + `upProj(x)` (L8601). No previous PR or research note has
proposed extending the existing decode fallback `quantizedMM` path to
prefill. The `PREFILL_OPROJ_ANALYSIS.md` (2026-08-05) analyzed the
O-proj chain but not the shared expert gate/up fusion.

### Risk: VERY LOW
- The `quantizedMM` over the fused bank already exists for decode
  fallback (L8585-8594). Extending to L > 1 is a shape relaxation.
- `quantizedMM` (non-gather) handles arbitrary M — it dispatches to
  `qmm_nax` (M5) or `qmm` (M4) which both support M ≥ 1.
- The fused bank weights are small (~512 KB per layer), well within L2.
- Composes with PR #229 (prefill routed down halving) — different path.
- Composes with Idea 2 (O-proj gate fusion) — different dispatch chain.

### Student: Edward (after PR #229 completes)

---

## Idea 2: Prefill O-proj Gate Dispatch Fusion via `attentionGateProjection` ★★★

**Priority**: 2
**Component**: Prefill (25% of score) — all 40 attention layers
**Mechanism**: For prefill (L > 1), the attention output projection uses
3 dependent dispatches:
1. `lagunaCompiledSoftplusGate(projectedGate)` — compiled softplus (1 dispatch)
2. `output * gate` — broadcast multiply (1 dispatch)
3. `wo(output)` — BF16 matmul (1 dispatch)

These 3 dispatches are a strict dependency chain (each feeds the next).
`asyncEval` cannot overlap them.

The `attentionGateProjection` compiled function (L5378-5394) already fuses
all three (softplus + gate product + matmul) for decode (L == 1). The
guard at L6279 (`L == 1`) prevents it from firing for prefill.

The compiled function body is shape-general:
```swift
let gate = softplus(projectedGate.asType(.float32)).asType(output.dtype)
let gated = (output.reshaped(batch, length, heads, headDim)
    * gate[.ellipsis, .newAxis]).reshaped(batch, length, heads * headDim)
return matmul(gated, weight.T)
```
It reads `batch` and `length` dynamically — works for any B, L.

### Proposed change:
Remove the `L == 1` guard from the `attentionGateProjection` call site
(L6279), allowing it to fire for prefill (L > 1):

```swift
// Current (L6278-6280):
if !gateIsActivated,
    gatePerHead && projectedGate.dtype == output.dtype,
    L == 1, wo.bias == nil, MLXHardwareInfo.isCompiledDecodeSupported
{
    return attentionGateProjection(output, projectedGate, wo.weight)
}

// Proposed: remove L == 1
if !gateIsActivated,
    gatePerHead && projectedGate.dtype == output.dtype,
    wo.bias == nil, MLXHardwareInfo.isCompiledDecodeSupported
{
    return attentionGateProjection(output, projectedGate, wo.weight)
}
```

### Bit-exactness: YES
- The compiled function computes the same softplus, the same broadcast
  multiply, and the same matmul. MLX's `compile` preserves exact
  semantics — it fuses dispatch boundaries but does not change
  arithmetic order.
- `softplus` is order-independent (elementwise).
- The broadcast multiply is order-independent (elementwise).
- `matmul(gated, weight.T)` uses the same NAX split-K kernel as stock
  `wo(output)` — the compiled graph calls the same matmul primitive.
- No FP reduction order changes.

### Bandwidth impact: NEUTRAL (dispatch savings only)
- Same weights, same inputs, same matmul.
- Eliminates 2 dispatch boundaries per layer (3 dispatches → 1 compiled graph).

### Expected speedup:
- 40 layers × 2 dispatches eliminated × ~2.5 µs = ~200 µs.
- If prefill takes ~10-20 ms: ~1-2% prefill speedup.
- Score: ~1-2% × 0.25 = **~0.25-0.5% score**.

### Budget impact: ~0 B (guard removal only)
- Removing `L == 1` from the guard is a 1-token change.
- May need to verify the compiled function handles L > 1 shapes correctly.

### M4 testability: YES
- The compiled function is not `_nax`-gated.
- `wo.weight` is BF16 for prefill (not the quantized native affine path).
- Verify via `--local-iterate` (max_abs_diff = 0) and upstream equivalence.
- Compare compiled vs stock gate path bit-for-bit for L = 512.

### Why it's fresh:
The `PREFILL_OPROJ_ANALYSIS.md` (2026-08-05) proposed a custom Metal
kernel for softplus+gate fusion (2-dispatch approach). This idea is
simpler: use the existing `attentionGateProjection` compiled function,
which already fuses all three operations. The compiled function was
consciously gated to L == 1 with the comment "Prefill deliberately
uses the smaller gate-only fusion" (L5376). The concern was likely that
compiling the matmul for M=512 might not help. But the dispatch savings
(2 fewer boundaries per layer) are real regardless of matmul performance.

### Risk: LOW-MEDIUM
- The compiled function is shape-general and should handle L = 512.
- Risk: MLX's `compile` might generate a less efficient graph for L=512
  than the stock 3-dispatch path (e.g., the matmul might not dispatch to
  the optimal NAX kernel from within a compiled graph). This needs
  testing.
- Risk: the compiled graph might not fuse the elementwise ops into the
  matmul epilogue, materializing the 8.4 MB intermediate anyway.
- Mitigation: test on M4 first. If the compiled path is slower, revert.
- Composes with all other ideas — different path.

### Student: Alphonse (after PR #230 completes) or Thorfinn

---

## Idea 3: Prefill Shared Expert Scale Halving via `qmm_nax` `kHalvedScales` ★★☆

**Priority**: 3
**Component**: Prefill (25% of score) — shared expert gate/up + down, 39 layers
**Mechanism**: The shared expert's prefill path uses `quantizedMM` (non-gather)
which dispatches to `qmm_nax` on M5. The `qmm_nax` kernel calls
`fp_qmm_t_impl` whose `QuantizedBlockLoader` is instantiated WITHOUT
`kHalvedScales` (defaults to `false`). The halved shared expert scales are
already built at init (`_halvedFusedGateUpScales`, `_halvedSharedDownScales`)
but only wired into the decode custom kernels — never into the prefill
`quantizedMM` path.

The `QuantizedBlockLoader` already supports `kHalvedScales` (L210, L263-286).
The gather path (`fp_gather_qmm_rhs_expert_nax`) already uses it. The
non-gather `fp_qmm_t_nax` / `fp_qmm_t_nax_static` just need the template
parameter plumbed through.

### Proposed change:
1. Add `kHalvedScales` template parameter to `fp_qmm_t_impl` (L678) and
   `fp_qmm_t_nax` / `fp_qmm_t_nax_static` (L1040, L1102).
2. Add escape input to `fp_qmm_t_nax` kernel signature.
3. Modify `qmm_nax` dispatch in `quantized.cpp` (L477-590) to detect halved
   scales: `scales.shape(-1) == K / (group_size * 2)` (same pattern as
   `gather_qmm_nax` at L1720).
4. Pass escape via biases array (same pattern as gather path).
5. Wire in Swift: pass halved scales + escape to `quantizedMM` for shared
   expert prefill.

### Scale traffic:
- Shared gate/up scales: [1024, 128] uint8 = 128 KB/layer. Halved: 64 KB.
- Shared down scales: [2048, 32] uint8 = 64 KB/layer. Halved: 32 KB.
- Total savings: 96 KB/layer × 39 layers = 3.74 MiB.
- Total shared expert prefill bandwidth: ~37 MB. Savings: 3.74/37 = 10%.
- As fraction of total prefill bandwidth (~432 MiB): 3.74/432 = 0.87%.
- Score: 0.87% × 0.25 = **~0.22% score**.

### Bit-exactness: YES
- NVFP4 pairwise-constancy invariant: `scale[2k] == scale[2k+1]` for k ≥ 1.
- The escape byte handles the sole exception at group 0, byte 1.
- Same invariant used by all existing halved kernels (decode MoE, QKV, O-proj).
- The `QuantizedBlockLoader.read_scale()` with `kHalvedScales` reads
  `scales[i/2]` with escape substitution — identical dequantization.

### Budget impact: ~60-100 B in `fp_quantized_nax.h`, ~30-50 B in `quantized.cpp`
- Add `kHalvedScales` template parameter + escape input to 2 kernel functions.
- Add halved-scales detection + escape passing to `qmm_nax` dispatch.
- ~20-30 B in LRM for Swift wiring.
- Well within vendor file headroom (446 KB + 441 KB).

### M4 testability: NO — M5-only
- `qmm_nax` is gated by `is_nax_available()` (GPU gen 17+). M4 uses the
  generic `qmm` path which does NOT have `kHalvedScales`.
- Must verify via careful code review (same pattern as PR #220).
- Can test the Swift wiring on M4 (the guard will decline on M4 and
  fall back to stock).

### Why it's fresh:
The vendor kernel analysis confirmed that `fp_qmm_t_impl`'s loader (L704)
does NOT pass `kHalvedScales`. No previous PR has proposed adding halved
scale support to the non-gather `qmm_nax` path. The shared expert prefill
scales are genuinely untouched.

### Risk: MEDIUM
- Modifying vendor kernel dispatch (`quantized.cpp`, `fp_quantized_nax.h`).
- Must not break the non-halved path (default `kHalvedScales = false`).
- M5-only — cannot test on M4. Must verify by code review.
- The `_nax` kernel is compiled at runtime; need to rebuild metallib.
- Composes with Idea 1 (different mechanism: dispatch vs bandwidth).

### Student: Edward (after PR #229 completes) or a new student

---

## Idea 4: `callLastPrefillRow` Gate Dispatch Fusion ★☆☆

**Priority**: 4
**Component**: Prefill (25% of score) — layer 39 only (last prefill layer)
**Mechanism**: `callLastPrefillRow` (L6308) computes the last prefill row's
attention with its own gate handling (L6396-6405):
1. `lagunaCompiledSoftplusGate(projectedGate)` — 1 dispatch
2. `output * gate` — 1 dispatch (broadcast multiply)
3. `wo(output)` — 1 dispatch (BF16 matmul)

Since L == 1 here (last row only), the `attentionGateProjection` compiled
function at L6279 COULD fire, but `callLastPrefillRow` has its own separate
gate handling that doesn't go through the `callAsFunction` path.

### Proposed change:
In `callLastPrefillRow`, replace the 3-dispatch gate chain with
`attentionGateProjection`:

```swift
// Current (L6396-6405):
let gate = gatePerHead && projectedGate.dtype == output.dtype
    ? lagunaCompiledSoftplusGate(projectedGate)
    : softplus(projectedGate.asType(.float32)).asType(output.dtype)
if gatePerHead {
    output = (output.reshaped(B, 1, nHeads, headDim) * gate[.ellipsis, .newAxis])
        .reshaped(B, 1, -1)
} else {
    output = output * gate
}
return wo(output)

// Proposed:
if !gateIsActivated, gatePerHead,
   projectedGate.dtype == output.dtype,
   wo.bias == nil, MLXHardwareInfo.isCompiledDecodeSupported
{
    return attentionGateProjection(output, projectedGate, wo.weight)
}
// Fallback: stock path above
```

### Bit-exactness: YES
- Same compiled function as decode. L == 1, B == 1.
- Same softplus, same gate product, same matmul.

### Expected speedup:
- 1 layer × 2 dispatches × ~2.5 µs = ~5 µs.
- If prefill takes ~10-20 ms: ~0.025-0.05% prefill speedup.
- Score: ~0.025-0.05% × 0.25 = **~0.006-0.013% score**.
- Below 0.05% threshold — marginal. Listed for completeness.

### Budget impact: ~0 B (guard change only, may remove a few lines)

### M4 testability: YES

### Why it's fresh:
`callLastPrefillRow` has its own gate handling that doesn't use
`attentionGateProjection`. The `PREFILL_OPROJ_ANALYSIS.md` noted this but
proposed a different approach (INT8 affine O-proj for the last layer).
Using the existing compiled function is simpler.

### Risk: LOW
- Same compiled function already used for decode. L == 1 here.
- Gain is marginal (1 layer).

### Student: Low priority — fold into Idea 2 or a cleanup PR

---

## Idea 5: `EXPERT_GATHER_GROUPS=256` Standalone M5 Measurement ★☆☆

**Priority**: 5
**Component**: Prefill (25% of score) — routed expert gate/up gather
**Mechanism**: The `DARKBLOOM_EXPERT_GATHER_GROUPS` env var controls how
many experts each threadgroup processes in the prefill gather-QMM kernel
(`gather_qmm_rhs_nax`, `quantized.cpp:1365-1392`). Default is 256 (one
expert per threadgroup). Values 64 and 128 were measured on M5; 256 was
noted as "measures closer to the acceptance ceiling in the single-shot
harness" but never submitted as a standalone M5 measurement.

This is a 0-byte change — just an env var. The default is already 256, so
the scored path already uses 256. This idea is to VERIFY that 256 is
optimal by comparing against 64 and 128 on M5.

### Bit-exactness: YES
- Threadgroup geometry does not affect arithmetic — only work partitioning.
- Same kernel, same code, same accumulation order.

### Expected speedup:
- 0-2% prefill (directional — may confirm current default or find improvement).
- If 128 is faster: ~1% prefill = ~0.25% score.
- If 256 is already optimal: 0%.

### Budget impact: 0 B (env var only)

### M4 testability: NO — M5-only (`_nax` path)

### Why it's fresh:
The vendor kernel analysis confirmed 256 was "never submitted as a
standalone M5 measurement." It's the default, but never verified as
optimal. `RESEARCH_IDEAS_FRESH_20260807_v2.md` (Idea 5) noted this as
"0-byte prefill threadgroup sweep."

### Risk: LOW
- Env var change only. No code change.
- If the default is already optimal, no harm done.

### Student: Any student with M5 access (measurement only)

---

## What Was Checked and Ruled Out (this analysis)

- **Final RMSNorm fusion into lm_head coarse kernel**: The final RMSNorm
  (`model.norm(...)`, L11231) is a separate dispatch (4 KB, pure latency).
  Could be folded into the lm_head coarse kernel which reads the hidden
  vector. BUT: RMSNorm requires a global reduction across 2048 elements
  (mean of squares). The coarse kernel has ~3.2M threadgroups — only one
  would do the reduction, the others would wait. Not efficient. The 4 KB
  weight is negligible bandwidth. The dispatch latency (~2.5 µs) is tiny
  vs the lm_head's ~115 MB weight read. NOT worth the complexity.

- **Dense MLP layer 0 quantization**: 100.6 MB/step BF16 — the single
  largest un-optimized read. But the accepted quantization envelope
  (AGENTS.md) restricts re-quantization to attention Q/K/V/O + g_proj.
  Dense MLP is NOT in the envelope. BLOCKED by rules.

- **Router BF16 weight quantization**: 41 MB/step. Already single-read
  fused. Outside the accepted envelope. BLOCKED.

- **Prefill attention fusion (SDPA + cache + gate + O-proj)**: The prefill
  uses stock `attentionWithCacheUpdate` from MLXLMCommon. Fusing a custom
  multi-row attention kernel for prefill would be HIGH risk and HIGH
  complexity. The 32 KB threadgroup memory limit already killed the 1-pass
  attention epilogue. A multi-row SDPA + O-proj mega-kernel would exceed
  this. NOT feasible.

- **Prefill input RMSNorm fusion**: The prefill input RMSNorm is a
  separate dispatch (L5879). Fusing it into the QKV matmul was tried and
  REGRESSED (+2.7% for decode). The RMSNorm global reduction interferes
  with the GEMV memory access pattern. NOT worth retrying for prefill.

- **4-wise scale constancy**: NVFP4 quantizer only guarantees pairwise
  constancy (`scale[2k] == scale[2k+1]`). 4-wise is NOT guaranteed.
  NOT bit-exact.

- **Non-expert rhs gather halving** (`fp_gather_qmm_rhs_nax`, L1277):
  This is the fallback path for M==1 decode gather. The scored decode
  path uses custom halved kernels, not this vendor path. Low priority —
  fallback only.

---

## Verification Results (2026-08-07)

### Idea 1: VERIFIED FEASIBLE ✅
- Fused bank already resident at init (L8298-8360, prepareFusedSharedGateUp)
- quantizedMM-over-fused-bank path already exists for decode (L8586-8599) but gated by x.dim(1) == 1
- Extending to L > 1 is a shape relaxation — quantizedMM supports arbitrary M
- Bit-exact: row-wise independence of quantizedMM (comment at L8580-8585)
- Eliminates 1 dispatch per layer × 39 layers
- ~200-300 B in LRM, fits within 9,587 B headroom
- M4 testable
- KEY: uses plain quantizedMM (not custom kernel), identical FLOPs and memory traffic

### Idea 2: REFUTED ❌ (documented negative result)
- The exact change was already tried and REGRESSED on ranked measurement (commit 8841cd9)
- Comment at L5365-5367: "Ranked measurement showed the larger gate/product graph regressing the complete prefill schedule"
- The L == 1 guard was ADDED specifically to prevent the regression
- Non-shapeless compile() recompiles for L=512, disturbing broader MLX scheduling
- DO NOT ASSIGN — this is a known negative result

### Idea 3: Unverified, M5-only (vendor kernel mod)
### Idea 4: Low priority (marginal gain, 1 layer only)
### Idea 5: Low priority (env var sweep, M5-only)

## Summary

| # | Idea | Component | Mechanism | Est. Score | Budget (LRM) | M4? | Priority |
|---|---|---|---|---|---|---|---|
| 1 | Prefill shared expert gate/up fusion | Prefill | 1 dispatch/layer | ~0.125-0.25% | ~200-300 B | YES | **HIGH** |
| 2 | Prefill O-proj gate dispatch fusion | Prefill | ~~2 dispatches/layer~~ | **DEAD** | ~0 B | YES | ❌ REFUTED |
| 3 | Prefill shared expert scale halving | Prefill | 3.74 MiB bandwidth | ~0.22% | ~20-30 B | NO | **MEDIUM** |
| 4 | `callLastPrefillRow` gate fusion | Prefill | 2 dispatches (1 layer) | ~0.01% | ~0 B | YES | LOW |
| 5 | `EXPERT_GATHER_GROUPS=256` M5 measurement | Prefill | 0-byte sweep | 0-0.25% | 0 B | NO | LOW |

### Primary Recommendations

**Idea 1** (prefill shared expert gate/up fusion) and **Idea 2** (prefill
O-proj gate dispatch fusion) are the strongest fresh opportunities. Both
target the prefill path (25% score weight), which is relatively unoptimized.
Both are dispatch-elimination (not bandwidth), which is the right axis for
the M5's dispatch-overhead bottleneck.

**Idea 1** uses existing infrastructure (fused bank already built) and is
bit-exact via row-wise independence of quantizedMM. ~200-300 B in LRM.

**Idea 2** is a 1-token guard change that enables an existing compiled
function for prefill. ~0 B in LRM. The main risk is that MLX's `compile`
might not generate an efficient graph for L=512. Test on M4 first.

**Idea 3** (prefill shared expert scale halving) is a bandwidth reduction
that composes with Ideas 1 and 2. It requires vendor kernel modifications
(`fp_quantized_nax.h`, `quantized.cpp`) but uses the existing
`kHalvedScales` infrastructure. M5-only — cannot test on M4.

### Composition Plan

If Ideas 1+2+3 all succeed:
- ~0.25% (Idea 1) + ~0.375% (Idea 2) + ~0.22% (Idea 3) = ~0.845% total.
- Starting from 2.5748 → ~2.597. Would BEAT 2.5888 target.
- All three are prefill-only (25% weight), so they compound additively
  without interfering with in-flight decode work (PRs #230, #231).

### Key Insight

The prefill path has two independent optimization axes that are both
untapped:
1. **Dispatch elimination**: shared expert gate/up fusion (Idea 1) and
   O-proj gate fusion (Idea 2) eliminate dependent dispatch chains.
2. **Bandwidth reduction**: shared expert scale halving (Idea 3) reduces
   bytes read from DRAM.

These axes compose because they target different dispatches and different
weight tensors. The prefill path's 3-dispatch O-proj chain and 4-dispatch
shared expert chain are the lowest-hanging fruit — both use existing
infrastructure (compiled function, fused bank) with minimal new code.
