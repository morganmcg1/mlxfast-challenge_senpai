# Fresh Optimization Ideas for LagunaRuntimeModel.swift

**Date:** 2026-08-08
**File:** `Sources/MLXFastModel/LagunaRuntimeModel.swift` (11,320 lines, 502KB / 512KB limit)
**Surface budget:** 2.94MB / 3.0MB (56KB headroom); LRM file 491KB / 512KB (21KB headroom)
**Model:** 40 layers (30 sliding + 10 full-attention), 256 routed experts (top-8), 1 shared expert, NVFP4 experts, INT8 QKV/o_proj/g_proj

---

## Executive Summary

The codebase has 41 merged optimizations. Most decode-path fusions are already ON by default.
The single highest-impact finding is that **all 10 full-attention layers run the STOCK 6-dispatch
decode path** because `DARKBLOOM_FUSED_FULL_QK_NORM_YARN` is OFF, which also blocks the full
fused attention kernel AND prevents the RoPE angle atlas from being built. The sliding counterpart
showed +1.73% when enabled. Several other OFF flags exist purely for M5 JIT compile count reduction
and could be selectively re-enabled.

---

## Idea 1: Enable Full-Attention QK-Norm+YaRN Fusion (HIGHEST PRIORITY)

**Causal question:** Are 10 of 40 decode layers running 6 dispatches instead of 1 because a flag
is OFF for JIT compile count, while the 30 sliding layers with the same fusion ON show +1.73%?

**Target evidence:** `LagunaRuntimeModel.swift` lines 526, 5980-5985, 6052-6053, 10819-10826

**Code path analysis:**
- `lagunaFusedFullQKNormYaRNEnabled` (L526): `== "1"` -> DEFAULT **OFF**
- `lagunaFusedSlidingQKNormRoPEEnabled` (L465): `!= "0"` -> DEFAULT **ON** (since `9e06de6`, +1.73%)
- The full fused attention kernel (`lagunaFusedFullAttentionEnabled`, L1774, DEFAULT ON) at L6052
  checks `useFusedFullQKNormYaRN` (L6053), which requires `lagunaFusedFullQKNormYaRNEnabled` ->
  **blocked by the OFF flag**
- `prepareRoPEAngleAtlases()` (L10819) guard requires `lagunaFusedFullQKNormYaRNEnabled` ->
  **atlas NOT built when flag is OFF**, which also means the sliding atlas path falls back to
  probe dispatches (L10948-10954) instead of the zero-copy atlas views (L10907-10920)

**Cascade effect of enabling (`DARKBLOOM_FUSED_FULL_QK_NORM_YARN=1`):**
1. RoPE angle atlas gets built (L10819 guard passes)
2. Both full AND sliding decode paths use the atlas (eliminates 2 probe RoPE dispatches/step)
3. Full-attention layers: QK-norm+YaRN fusion fires (1 dispatch instead of qNorm+kNorm+2xtranspose+2xapplyRotaryPosition = 6)
4. Full fused attention kernel fires (1 dispatch instead of 6+cache_update+SDPA = ~8)
5. Net: ~5-7 dispatch eliminations x 10 full-attention layers = **50-70 fewer dispatches per decode step**

**Expected signal:** Decode speedup proportional to dispatch count reduction on full-attention
layers. Sliding counterpart measured +1.73%. Full-attention is 10/40 = 25% of layers. Expected
decode improvement: ~0.4-0.9% (proportionally less than sliding's 25% weight but with larger
per-layer dispatch savings since full attention has 8 dispatches vs sliding's ~5).

**Bit-exactness argument:** The kernel `lagunaFullQKNormYaRNKernel` (L1016) and
`lagunaFullFusedAttentionKernel` (L1784) already exist in the binary with full exactness
documentation. The sliding counterpart (`lagunaFusedSlidingQKNormRoPEEnabled`) has been
shipping bit-exact since `9e06de6`. The atlas rows are the family's own stock RoPE outputs
copied (L10924-10957). No new math is introduced; only the dispatch path changes.

**Budget estimate:** **ZERO bytes** -- all kernel sources already in the file. Only the flag
default changes from `== "1"` to `!= "0"`.

**M4-testability:** Yes. Set `DARKBLOOM_FUSED_FULL_QK_NORM_YARN=1` and run
`./benchmark.sh --local-iterate`. The M4 has the kernel compiled; it just isn't dispatched.
M4 sweep showed "neutral" but M4 doesn't use `_nax` kernels and has different core count
(16 GPU cores vs M5's 40). The dispatch savings may matter more on M5's deeper pipeline.

**Risk level:** LOW for correctness (kernel already built and bit-exact documented).
MEDIUM for JIT compile count (adds 2 new JIT compiles: `lagunaFullQKNormYaRNKernel` +
`lagunaFullFusedAttentionKernel`). The M5 build failures from JIT compile-storm are the
current blocker -- this adds 2 compiles. Must verify M5 build succeeds.

**Risk mitigation:** Test on M5 first with a build-only check. If the 2 extra JIT compiles
tip it over, disable 2 other OFF-flagged kernels to make room (they're already OFF and
their kernels are never accessed).

---

## Idea 2: Enable Fused Gate Product for Decode (DARKBLOOM_FUSED_GATE_PRODUCT)

**Causal question:** Does fusing softplus+gate-product into one Metal kernel dispatch
outperform the stock compiled-softplus + broadcast-multiply chain on M5's 40-core GPU?

**Target evidence:** `LagunaRuntimeModel.swift` lines 3747-3748, 6287-6302

**Code path analysis:**
- `lagunaFusedGateProductEnabled` (L3747): `== "1"` -> DEFAULT **OFF**
- Used at L6288 in the native affine o_proj path: replaces `lagunaCompiledSoftplusGate` +
  broadcast-multiply (2 dispatches) with `lagunaGateProductSoftplus` kernel (1 dispatch)
- The DEFAULT decode path for non-affine-o_proj layers uses `attentionGateProjection`
  (L6334-6339, compiled fusion of softplus+gate+matmul) which is already 1 dispatch
- So this flag only helps the **native affine o_proj path** (layers with INT8 o_proj),
  saving 1 dispatch per such layer per decode step

**Expected signal:** ~1 dispatch saving x (number of layers with affine o_proj) per decode
step. If o_proj is affine on all 40 layers, that's 40 dispatch savings per step. But the
gate product is tiny (nHeads elements -> broadcast to nHeads x 128), so each dispatch is
trivially fast. Expected improvement: <0.1%.

**Bit-exactness argument:** `lagunaGateProductSoftplusKernel` (L3728) reproduces the
exact BF16 softplus + broadcast product. Documented bit-exact.

**Budget estimate:** ZERO bytes (kernel source already in file).

**M4-testability:** Yes. M4 showed neutral timing.

**Risk level:** LOW for correctness. LOW for JIT compile (kernel already built at file scope,
but enabling dispatch adds 1 JIT compile). Very low expected impact.

---

## Idea 3: Enable Prefill QK-Norm+RoPE Fusion (DARKBLOOM_PREFILL_QK_NORM_ROPE)

**Causal question:** Does eliminating 4-6 prefill dispatches per layer (qNorm, kNorm, 2x
transpose, 2x applyRotaryPosition) into 1 fused kernel improve the 25%-weight prefill score?

**Target evidence:** `LagunaRuntimeModel.swift` lines 483-484, 6096-6130

**Code path analysis:**
- `lagunaPrefillQKNormRoPEEnabled` (L483): `== "1"` -> DEFAULT **OFF**
- 4 prefill kernel variants exist: `lagunaPrefillSlidingQKNormRoPEKernel` (L2314),
  `...H1Kernel` (L2409), `lagunaPrefillFullQKNormYaRNKernel` (L2501), `...H1Kernel` (L2595)
- Default heads-per-group is 1 (L492-497), so only the H1 variants would fire
- Stock prefill path (L6118-6123): `qNorm(queries.reshaped(...).transposed(...))` +
  `kNorm(keys.reshaped(...).transposed(...))` = 2 RMSNorm + 2 reshape/transpose = ~4 dispatches
  + 2x `applyRotaryPosition` (L6138-6139) = **6 total dispatches per layer**
- Fused path: 1 kernel dispatch per layer
- Saving: 5 dispatches x 40 layers = **200 dispatch eliminations per prefill forward**

**Expected signal:** Prefill is 25% of score. 200 dispatch savings is significant if dispatch
overhead is measurable. M4 showed neutral, but M4 doesn't use `_nax` and has different core
count. On M5 with 40 cores, dispatch overhead may be amortized differently.

**Bit-exactness argument:** Prefill kernels consume the same load-time FP32 atlas rows the
stock RoPE would produce (L6094-6101). QK-norm is per-head RMSNorm, same math. Guarded on
shape/dtype/family and offset bounds. Documented bit-exact.

**Budget estimate:** ZERO bytes (kernel sources already in file). Only H1 variants would
be dispatched (H4 variants exist but default OFF via `DARKBLOOM_PREFILL_QK_HEADS`).

**JIT compile cost:** 2 new JIT compiles (sliding H1 + full H1). The H4 variants are built
at file scope but never dispatched (heads-per-group defaults to 1). However, the metalKernel
instances at L2314/L2501 are `private let` at file scope -- they may JIT-compile when first
accessed even if the H4 variant is never called. **Need to verify whether MLX JIT-compiles
on first kernel call or on metalKernel instance creation.**

**M4-testability:** Yes. Set `DARKBLOOM_PREFILL_QK_NORM_ROPE=1` and run prefill benchmark.

**Risk level:** LOW for correctness. MEDIUM for JIT compile count (2-4 new compiles depending
on whether H4 variants also compile). Must verify M5 build succeeds.

---

## Idea 4: Enable Terminal Prefill Fusion (DARKBLOOM_TERMINAL_FUSION)

**Causal question:** Does the terminal-prefill row specialization (computing attention only
for the last query row while still committing all K/V) save prefill time?

**Target evidence:** `LagunaRuntimeModel.swift` lines 514-515, 10574-10759

**Code path analysis:**
- `lagunaTerminalPrefillFusionEnabled` (L514): `== "1"` -> DEFAULT **OFF**
- `callLastPrefillRow` (L10687) uses the terminal path when enabled, reusing the ordinary
  path's accepted row-local fusions (residual+RMSNorm+router, MoE tail)
- The STOCK terminal path (L10752-10758) does: `inputLayerNorm(x)`, `callLastPrefillRow`
  for attention (which projects Q only for last row, K/V for all), then `h + r`, `postAttnNorm`,
  `mlp`, `h + r2`
- The fused terminal path reuses the same residual+RMSNorm+router and MoE tail fusions
  already accepted for the normal path
- This doesn't eliminate dispatches per se -- it reuses existing fusions rather than stock ops
- The last-layer attention already has `callLastPrefillRow` (L6496) which only projects Q for
  the last row. The terminal fusion extends this savings to the MLP side

**Expected signal:** The last layer computes MLP only for the last row (1 token instead of 512).
This is already done in the stock `callLastPrefillRow` path (L10752-10758 uses
`lagunaLastTokenHidden(x)` for residual). The terminal fusion just reuses the accepted
fusion helpers instead of stock ops. Expected improvement: marginal (saves a few dispatches
on the last layer only -- 1 of 40 layers).

**Bit-exactness argument:** Reuses accepted fusions with documented exactness. Falls back to
stock when guards decline.

**Budget estimate:** ZERO bytes.

**M4-testability:** Yes. Set `DARKBLOOM_TERMINAL_FUSION=1`.

**Risk level:** LOW for correctness. LOW for JIT compile (no new kernels -- reuses existing).
LOW expected impact.

---

## Idea 5: JIT Kernel Consolidation to Reduce M5 Build Failures

**Causal question:** Can the M5's 31+ consecutive build failures from JIT compile-storm be
resolved by consolidating redundant kernel variants, freeing JIT compile slots for the
higher-impact fusions in Ideas 1-4?

**Target evidence:** Multiple metalKernel instances at file scope, each a separate JIT compile.

**Analysis of kernel variant counts:**
The file contains ~40 `MLXFast.metalKernel` instances. Key multi-variant families:
- **Prefill QK-norm+RoPE:** 4 variants (sliding H1, sliding H4, full H1, full H4) at L2314/L2409/L2501/L2595.
  Default uses H1 only. **Could delete H4 variants** (saves 2 JIT compiles, ~0 byte budget since
  they exist but are never dispatched).
- **Gate product softplus:** 2 variants (decode + multi-token) at L3728/L3736. Both needed.
- **Compiled functions:** `lagunaCompiledSoftplusGate` (L5491), `attentionGateProjection` x 2
  (L5516/L5521). These use `compile()` not `metalKernel`, so they have different JIT behavior.
- **Router kernels:** Multiple variants for ordinal/float/cast-sink paths.

**Consolidation strategy:**
1. Delete the H4 prefill QK-norm+RoPE kernel variants (L2409, L2595) since
   `lagunaPrefillQKHeadsPerGroup` defaults to 1. This removes 2 JIT compiles.
2. Verify which OFF-flagged kernels are still built at file scope but never dispatched.
   If their metalKernel instance is a `private let`, it may still trigger JIT compilation
   on first access. Moving the `let` inside the guarded function (lazy initialization)
   would defer JIT compile until the flag is ON.
3. Consolidate the decode gate product kernel and multi-token gate product kernel into
   one parameterized kernel (they share the same source, differing only in grid dimensions).

**Expected signal:** Reducing JIT compile count by 2-4 variants could unblock M5 builds,
enabling Ideas 1-3 which add back 2-4 compiles. Net zero or negative compile count change
while gaining dispatch savings.

**Bit-exactness argument:** Deleting unused kernel variants changes nothing (they're never
dispatched). Consolidating same-source kernels with different grid dims is bit-exact (same
kernel, same arithmetic, different dispatch geometry).

**Budget estimate:** NEGATIVE (removes code). Each H4 variant is ~50-100 lines of source.

**M4-testability:** Build-only check on M5 to verify compile count reduction.

**Risk level:** LOW. Only removes dead/unused code. Must verify no other code references
the deleted variants.

---

## Idea 6: Lazy metalKernel Initialization for OFF-Flagged Kernels

**Causal question:** Do OFF-flagged metalKernel instances at file scope still trigger JIT
compilation, consuming M5 build budget even when never dispatched?

**Target evidence:** `MLXFast.metalKernel(...)` declarations at file scope (e.g., L1016,
L1784, L2314, L3728, etc.)

**Analysis:**
`MLXFast.metalKernel` is a Swift `let` at file scope. In Swift, file-scope `let` values are
lazily initialized on first access. If the kernel is never called (flag is OFF), the
`metalKernel` instance is never accessed, so it's never initialized, so **no JIT compile
happens**. This means OFF-flagged kernels should NOT contribute to JIT compile count.

**However:** If any code path references the kernel variable even when the flag is OFF
(e.g., a guard checks `if kernel != nil` or passes it as an argument before the flag check),
the instance would be initialized. Need to verify that all OFF-flagged kernels are only
referenced inside the flag-guarded branch.

**Verification needed:** Grep for each OFF-flagged kernel name and confirm it's only
accessed inside the `if flagEnabled { ... }` block. If any are accessed outside, move the
access inside the guard.

**Expected signal:** If any OFF-flagged kernels are being JIT-compiled due to premature
access, fixing this would reduce M5 build time. If all are properly lazy, this is a no-op.

**Budget estimate:** Zero bytes (moving code, not adding).

**M4-testability:** Build time comparison before/after.

**Risk level:** LOW. Only moves code, no semantic change.

---

## Idea 7: Skip createAttentionMask for Single-Token Decode

**Causal question:** Is the per-step `createAttentionMask` call (2 calls, one per family)
wasting CPU time on invariant single-token decode where the mask is always `.none`?

**Target evidence:** `LagunaRuntimeModel.swift` lines 11095-11097

**Code path analysis:**
- L11095-11097: `fullMask = createAttentionMask(h: h, cache: cache?[fullAttentionIdx])` and
  `slidingMask = createAttentionMask(h: h, cache: cache?[slidingAttentionIdx], windowSize: slidingWindow)`
- For single-token decode (L==1), `createAttentionMask` (KVCache.swift:295) returns `.none`
  when `n == 1` (no mask needed for a single position)
- These are CPU-side function calls, not GPU dispatches
- Called once per forward (not per layer), so 2 calls per decode step
- Each call does: check cache offset, check sequence length, possibly create a mask array

**Expected signal:** Saves 2 CPU function calls per decode step. With 128 decode steps,
that's 256 function calls eliminated. CPU-only savings, likely <0.01% of decode time.

**Bit-exactness argument:** For L==1, the mask is `.none` by construction. Skipping the
call and hardcoding `.none` produces identical behavior.

**Budget estimate:** ~50 bytes (add an `if isSingleTokenDecode` branch).

**M4-testability:** Yes, but impact is below measurement noise.

**Risk level:** LOW. Trivial correctness.

---

## Idea 8: Fuse Final RMSNorm into LM Head Pruner's First Pass

**Causal question:** Can the final RMSNorm (applied to the last hidden row before lm_head)
be folded into the lm_head pruner's first-pass matmul, eliminating one dispatch per decode step?

**Target evidence:** `LagunaRuntimeModel.swift` lines 11202, 11218; `LagunaLmHeadPrune.swift`

**Code path analysis:**
- L11202: `let hidden = model.norm(lagunaLastTokenHidden(fullHidden))` -- RMSNorm on [1,1,2048]
- L11218: `result = pruner.logits(hidden: hidden, ...)` -- two-pass pruner reads hidden, does
  coarse matmul, then refinement
- The RMSNorm is a reduction over 2048 elements (tiny) followed by elementwise multiply
- The pruner's first pass is a [100352, 2048] matmul (dominant cost)
- Fusing RMSNorm into the matmul: each thread loads the 2048-element row, computes RMS,
  normalizes, then accumulates the dot product. This eliminates the separate RMSNorm dispatch.

**Expected signal:** 1 dispatch saving per decode step. With 128 steps, 128 dispatch savings.
The RMSNorm is trivially fast (2048 elements), so the dispatch overhead elimination is the
only gain. Expected: <0.05%.

**Bit-exactness argument:** RMSNorm is `x / sqrt(mean(x^2) + eps) * weight`. Fusing into the
matmul changes the reduction order: the matmul would compute `sum(w * x_norm)` where
`x_norm = x / rms(x)`. The RMS must be computed before the dot product, which means the
kernel must first read the full row, compute RMS, then do the dot product. This is a
two-pass kernel within one dispatch. The RMS computation is bit-exact (same FP32 reduction
as stock RMSNorm). The dot product then uses the same BF16 weight and normalized input.
**Risk:** the matmul's K-loop accumulation order might differ if the normalization changes
the input values' rounding. But the pruner already reads normalized input, so the values
are identical -- only the dispatch boundary changes.

**Budget estimate:** ~200-500 bytes for the fused kernel source. Tight budget (21KB LRM
headroom, but this could go in `LagunaLmHeadPrune.swift` which has its own budget).

**M4-testability:** Yes. Modify the pruner's first-pass kernel to accept un-normalized
input + norm weight + eps.

**Risk level:** MEDIUM. Modifying the certified two-pass pruner requires careful
verification. The pruner is described as "certified" (notes/68) -- changing its input
contract requires re-certification.

---

## Idea 9: Reduce Per-Layer CPU Guard Overhead via Fast-Path Dispatch Table

**Causal question:** Does the per-layer, per-step evaluation of ~15-30 dtype/dims/type
predicates across 40 layers (600-1200 predicates/step) measurably impact decode throughput?

**Target evidence:** `LagunaRuntimeModel.swift` lines 5856-5875 (attention QKV guards),
10605-10648 (residual+RMSNorm guards), 10231-10242 (MoE guards)

**Code path analysis:**
- Each `LagunaRuntimeAttention.callAsFunction` runs extensive guard chains:
  - `lagunaFusedQKVProjectionEnabled` + ~20 dtype/dims/type checks (L5856-5875)
  - `lagunaFusedFullAttentionEnabled` + `useFusedFullQKNormYaRN` + shape checks (L6052-6058)
  - `lagunaFusedSlidingAttentionEnabled` + `useFusedSlidingQKNormRoPE` + shape checks (L6026-6033)
  - Gate product + output projection guards (L6287-6339)
- These guards are INVARIANT across decode steps (same weights, same shapes, same dtypes)
- They're re-evaluated every step x 40 layers

**Optimization:** At init time (after `prepareFusedRuntimeWeights`), pre-compute a per-layer
"fast path" enum that records which fusion branch each layer will take. The decode loop
then dispatches directly to the pre-selected path, skipping all guards.

**Expected signal:** CPU-only savings. If each guard chain takes ~1us and there are 40
layers x 128 steps = 5120 evaluations, that's ~5ms total. If decode takes ~560ms, this is
~1%. However, if guards are <0.1us each, savings are <0.1%.

**Bit-exactness argument:** The fast-path enum selects the same code path the guards would
select. No math changes.

**Budget estimate:** ~500-1000 bytes for the dispatch table + enum + initialization logic.
Tight budget.

**M4-testability:** Yes. Profile CPU time in the decode loop.

**Risk level:** LOW for correctness. MEDIUM for complexity. The main risk is that a guard
that should decline (e.g., due to a runtime condition like cache type) is pre-computed
incorrectly. Must ensure all guards are truly invariant.

---

## Idea 10: Consolidate Compiled Gate Functions to Reduce Compile Count

**Causal question:** Can the 3 `compile()` calls (softplus gate + 2 attention gate
projections) be consolidated into fewer compiled graphs to reduce M5 compile time?

**Target evidence:** `LagunaRuntimeModel.swift` lines 5491, 5513-5521

**Code path analysis:**
- `lagunaCompiledSoftplusGate` (L5491): `compile(shapeless: true)` of softplus
- `lagunaFullAttentionGateProjection` (L5516): `compile(body)` fusing softplus+gate+matmul (48 heads)
- `lagunaSlidingAttentionGateProjection` (L5521): `compile(body)` fusing softplus+gate+matmul (64 heads)
- These are 3 separate MLX graph compilations

**Consolidation:** The two attention gate projections differ only in head count (48 vs 64).
If the compiled function is made shapeless (the head count becomes a runtime dimension),
one compiled graph could serve both. The matmul output dimension would be parameterized.

**Expected signal:** 1 fewer MLX graph compilation. MLX `compile()` graph compilation is
different from metalKernel JIT -- it's a CPU-side graph optimization. The saving is in
compile time, not dispatch count.

**Bit-exactness argument:** A shapeless compiled graph produces the same arithmetic
regardless of head count. The matmul accumulation order is the same (it's the same matmul
primitive with different dimensions).

**Budget estimate:** ~100-200 bytes (simplify the two functions into one parameterized one).

**M4-testability:** Build time comparison.

**Risk level:** LOW for correctness (same compiled graph, different dims). MEDIUM for
complexity (MLX compile shapeless behavior needs verification for matmul with variable
output dims).

---

## Ranking by Expected Score Impact

| Rank | Idea | Score Axis | Expected Impact | Budget | Risk |
|------|------|-----------|----------------|--------|------|
| 1 | **Enable full-attn QK-norm+YaRN** (Idea 1) | Decode (75%) | ~0.4-0.9% | 0 bytes | LOW-MED |
| 2 | **JIT kernel consolidation** (Idea 5) | Build reliability | Unblocks Ideas 1-4 | Negative | LOW |
| 3 | **Enable prefill QK-norm+RoPE** (Idea 3) | Prefill (25%) | ~0.1-0.3% | 0 bytes | LOW-MED |
| 4 | **Lazy metalKernel init** (Idea 6) | Build reliability | Potentially reduces compiles | 0 bytes | LOW |
| 5 | **Fast-path dispatch table** (Idea 9) | Decode (75%) | ~0.1-1% (CPU) | ~1KB | MED |
| 6 | **Enable gate product fusion** (Idea 2) | Decode (75%) | <0.1% | 0 bytes | LOW |
| 7 | **Consolidate compiled gates** (Idea 10) | Build reliability | 1 fewer compile | ~200B | LOW-MED |
| 8 | **Skip mask for single-token** (Idea 7) | Decode (75%) | <0.01% | ~50B | LOW |
| 9 | **Enable terminal prefill fusion** (Idea 4) | Prefill (25%) | Marginal | 0 bytes | LOW |
| 10 | **Fuse final RMSNorm into pruner** (Idea 8) | Decode (75%) | <0.05% | ~500B | MED |

---

## Key Findings Summary

1. **CRITICAL:** `DARKBLOOM_FUSED_FULL_QK_NORM_YARN` is OFF (L526), which blocks:
   - The full-attention QK-norm+YaRN decode fusion (10 layers run stock 6-dispatch path)
   - The full fused attention kernel (already ON but gated by the YaRN flag)
   - The RoPE angle atlas construction (L10819), which also degrades the sliding path
   from atlas views to probe dispatches

2. **All OFF-flagged fusions have zero byte cost** -- kernel sources already exist in the
   file. Only flag defaults need changing.

3. **The M5 JIT compile-storm is the binding constraint.** Ideas 5 and 6 (kernel
   consolidation + lazy init) should be done FIRST to free JIT compile slots, THEN
   Ideas 1 and 3 can be enabled.

4. **Weight traffic is at the quantization floor.** QKV/o_proj are INT8 (envelope-capped),
   experts are NVFP4. No further precision reduction is possible within the accepted
   envelope. The only remaining levers are dispatch elimination and CPU overhead reduction.

5. **The LRM file has only 21KB of headroom.** Any new kernel source must be extremely
   compact. Ideas that add kernel source (8) should be deprioritized in favor of
   zero-budget flag changes (1, 2, 3, 4).

---

## Detailed Decode Path Dispatch Inventory (per step, per layer)

### Full-attention layer (10 layers, CURRENT STOCK PATH):
1. Fused norm+affine QKV kernel (1 dispatch) -- DEFAULT ON
2. qNorm(queries.reshaped.transposed) (1 dispatch) -- STOCK (YaRN flag OFF)
3. kNorm(keys.reshaped.transposed) (1 dispatch) -- STOCK
4. applyRotaryPosition(queries) (1 dispatch) -- STOCK
5. applyRotaryPosition(keys) (1 dispatch) -- STOCK
6. values.reshaped.transposed (1 dispatch, metadata-only for L=1)
7. cache.update(keys, values) (1 dispatch)
8. scaledDotProductAttention (1 dispatch)
9. attended.reshaped (metadata-only for L=1)
10. Gate: attentionGateProjection (1 dispatch, compiled) -- DEFAULT ON
11. wo(output) matmul (1 dispatch)
**Total: ~11 dispatches per full-attention layer per decode step**

### With Idea 1 enabled (FUSED PATH):
1. Fused norm+affine QKV kernel (1 dispatch)
2. Full fused attention kernel (1 dispatch: QK-norm + YaRN + cache append + SDPA)
3. Gate: attentionGateProjection (1 dispatch, compiled)
4. wo(output) matmul (1 dispatch)
**Total: ~4 dispatches per full-attention layer per decode step**
**Savings: ~7 dispatches x 10 layers = 70 dispatches per decode step**

### Sliding layer (30 layers, CURRENT FUSED PATH):
1. Fused norm+affine QKV kernel (1 dispatch)
2. Sliding fused attention kernel (1 dispatch: QK-norm + RoPE + cache ring + SDPA)
3. Gate: attentionGateProjection (1 dispatch, compiled)
4. wo(output) matmul (1 dispatch)
**Total: ~4 dispatches per sliding layer per decode step (already optimal)**

### MoE sparse layer (39 layers):
1. Router (fused residual+RMSNorm+router or separate) (1-2 dispatches)
2. Routed SwiGLU QMV + Shared SwiGLU QMV (1 dispatch, merged) -- DEFAULT ON
3. Routed+shared down+residual (1 dispatch) -- DEFAULT ON
**Total: ~3-4 dispatches per MoE layer per decode step (already optimal)**

### Dense layer 0:
1. RMSNorm (1 dispatch, or fused with QKV)
2. Fused gate/up+SiLU (1 dispatch) -- DEFAULT ON
3. Fused down+residual (1 dispatch) -- DEFAULT ON
**Total: ~3 dispatches (already optimal)**

### Model-level per step:
1. Embedding+RoPE atlas (1 dispatch, or stock embedding + 2 probe RoPE)
2. Final RMSNorm (1 dispatch)
3. LM head pruner (2-3 dispatches)
**Total: ~4-5 dispatches per step (already optimized)**

**Grand total per decode step: ~4x30 (sliding attn) + ~11x10 (full attn stock) + ~4x39 (MoE) + ~3 (dense) + ~5 (model) = ~685 dispatches**
**With Idea 1: ~4x30 + ~4x10 + ~4x39 + ~3 + ~5 = ~434 dispatches (37% reduction)**
