# Fresh Optimization Ideas v4 — 2026-08-07 (Dispatch Census + Prefill/Decode Opportunities)

Ranked list of fresh, untried bit-exact dispatch-elimination and bandwidth-reduction
opportunities derived from a full dispatch census of the LRM decode and prefill paths,
cross-referenced against all active assignments (PR #314-#317) and exhausted ideas.

## Budget Constraints (verified)

| File | Size | Limit (per-file) | Headroom |
|---|---|---|---|
| LagunaRuntimeModel.swift | 503,371 | 524,288 | **20,917 B** |
| LagunaLmHeadPrune.swift | 46,738 | 524,288 | 477,550 B |

LRM is the binding constraint at 20,917 B headroom. New kernel source must be compact.

## Decode Dispatch Census (per sparse layer, current default flags ON)

Verified by tracing every dispatch-generating call in the LRM decode path:

| # | Dispatch | Function | Line | Dispatches |
|---|---|---|---|---|
| 1 | Input RMSNorm + NVFP4 QKV + gate rows | `lagunaNormAffineQKV` | 5862 | 1 |
| 2 | QK-norm + RoPE + SDPA + cache write | `lagunaSlidingFusedAttention` / `lagunaFullFusedAttention` | 6108/6134 | 1 |
| 3 | NVFP4 O-proj + gate product + softplus | `lagunaGatedAffineOProjNVFP4` | 6322/6338 | 1 |
| 4 | Post-attn residual + RMSNorm + router GEMV | `lagunaResidualRMSNormRouter` | 959 | 1 |
| 5 | Router top-8 selection + normalization | `lagunaDecodeRouterTop8` | 9536 | 1 |
| 6 | Routed + shared gate/up QMV + SwiGLU | `lagunaRoutedSwiGLUQMVPackedTop8` | 10160 | 1 |
| 7 | Routed + shared down + residual | `lagunaRoutedSharedDownResidual` | 8012 | 1 |

**Per sparse layer: 7 dispatches.** Dense layer 0: ~6 (no router, dense MLP).
Total: 39×7 + 6 + 3 (model-level: embedding+RoPE atlas, final RMSNorm, lm_head) ≈ **282 dispatches/step**.
At ~2.5 µs/dispatch: ~705 µs/step ≈ 7% of a ~10ms decode step.

Key correction from v3 analysis: dispatches #2 and #3 (input RMSNorm, NVFP4 QKV) are
already FUSED into 1 dispatch via `lagunaNormAffineQKV` (default ON). Dispatch #4
(gate-softplus) is already eliminated — gate rows ride the QKV bank and softplus is
deferred to the O-proj kernel. The v3 analysis was based on an older code state.

## Prefill Dispatch Census (per layer, current defaults)

| # | Dispatch | Function | Line | Dispatches |
|---|---|---|---|---|
| 1 | Input RMSNorm | `inputNorm(input)` | 6004 | 1 |
| 2 | QKV matmul (fused bank) | `matmul(normalizedInput, fusedQKVWeight.T)` | 6022 | 1 |
| 3 | g_proj matmul | `gProj(normalizedInput)` | 6250 | 1 |
| 4 | QK-norm + RoPE (fused) | `lagunaPrefillSlidingQKNormRoPE` / `lagunaPrefillFullQKNormYaRN` | 6169/6182 | 1 |
| 5 | SDPA + cache update | `attentionWithCacheUpdate` | 6220 | 1 |
| 6 | Gate-softplus + gate product (fused) | `lagunaGateProductSoftplusMultiToken` | 6413 | 1 |
| 7 | O-proj + residual addMM | `addMM(residual, output, wo.weight.T)` | 6442 | 1 |
| 8 | Post-attn residual + RMSNorm | `lagunaResidualRMSNorm` (if flag ON) / stock | 10389 | 1-2 |
| 9 | Router GEMV (if not fused with #8) | stock `x.matmul(weight.T)` or fused | 10351 | 0-1 |
| 10 | Router top-8 tournament | `lagunaPrefillRouterTournament` | 9515 | 1 |
| 11 | Routed gate/up QMM + SiLU | `lagunaFusedSortedRoutedGateUp` (gatherQMM + downQMM) | 10320 | 2 |
| 12 | Shared gate/up QMM + SiLU | `compiledSiluProduct` + QMM | 8615/8627 | 2-3 |
| 13 | MoE tail (weighted sum + residual) | `lagunaPrefillSortedMoETail` / `lagunaPrefillMoETail` | 10361/10407 | 1 |

**Per layer: ~13-15 dispatches (prefill).** With PR #315 (QKV bank) and PR #317 (RMSNorm+router):
~11-13 dispatches. Prefill runs once (512 tokens), so ~440-600 dispatches total.

---

## Idea 1: Fuse g_proj into Prefill QKV Matmul ★★★

**Priority**: 1 (highest)
**Component**: Prefill (25% of score) — all 40 attention layers
**Status**: NOT assigned, NOT tried, NOT in exhausted list

### Current flow (2 dispatches per layer):
1. QKV matmul: `matmul(normalizedInput, fusedQKVWeight.T)` → [1, L, QKVdim]
2. g_proj matmul: `gProj(normalizedInput)` → [1, L, nHeads]

Both consume the SAME input (`normalizedInput`) and are both BF16 `Linear` (bias-free).
The g_proj weight is [nHeads, 2048]; the fused QKV weight is [QKVdim, 2048].

### Proposed flow (1 dispatch per layer):
1. Concatenated QKV+gate matmul: `matmul(normalizedInput, fusedQKVGateWeight.T)`
   → [1, L, QKVdim + nHeads], then slice gate rows from the tail.

### Why this works:
- This is EXACTLY what the decode path already does: gate rows are folded into the
  NVFP4 QKV bank (`_nativeAffineQKVGateRows`) and sliced from the QKV output (line 5923).
- For prefill, the QKV uses a BF16 fused bank (`_fusedQKVWeight`). The g_proj is also
  BF16 `Linear` (bias-free). Concatenating [Wq; Wk; Wv; Wgate] is bit-exact: each output
  row's K-loop is independent of which rows share the dispatch (same argument as the
  existing QKV fusion, line 6019).
- The gate rows add nHeads (48 or 64) output rows to a QKVdim-row matmul
  (QKVdim = 48×128 + 3×8×128 = 9216 for full-attn, 64×128 + 3×8×128 = 11264 for sliding).
  The overhead is <1% of the matmul size.

### Bit-exactness: YES (class A)
- Same weight values, same input, same matmul operation. Each output row is computed
  independently. The gate rows are bit-identical to a separate `gProj(normalizedInput)`
  call. Slicing is a zero-copy view.

### Bandwidth impact: SAVES 2MB/layer
- Eliminates the normalizedInput re-read by g_proj: [1, 512, 2048] BF16 = 2 MB/layer.
- 40 layers × 2 MB = 80 MB saved per prefill pass.
- At ~400 GB/s M5 bandwidth: ~0.2 ms saved (not dominant, but helps).

### Expected speedup:
- 40 dispatches eliminated. At ~2.5 µs/dispatch: ~100 µs.
- 80 MB bandwidth saved: ~0.2 ms.
- Prefill is ~4 ms. Total: ~300 µs / 4 ms = ~7.5% prefill speedup.
- Score: 7.5% × 0.25 (prefill weight) = **~1.9% score**.

### Implementation:
1. Modify `prepareFusedQKVWeight()` (line 5560): concatenate `gProj.weight` into the
   fused bank: `concatenated([wq.weight, wk.weight, wv.weight, gProj.weight], axis: 0)`.
2. Add guard for `gProj.bias == nil`, `gProj.weight.dtype == wq.weight.dtype`,
   `gProj.weight.dim(1) == wq.weight.dim(1)`.
3. Store `_fusedQKVGateRows` (number of gate rows appended).
4. At the call site (line 6022-6027): slice gate logits from the QKV matmul output:
   `qkv[.ellipsis, (queryDim + 2*kvDim) ..< (queryDim + 2*kvDim + nHeads)]`.
5. Pass the gate logits to the gate-softplus kernel (line 6250 → use sliced logits).

### Budget: ~200-300 B in LRM
- ~50 B for prepareFusedQKVWeight modification (add gProj concatenation).
- ~100 B for call site (slice gate from QKV output, pass to gate-softplus).
- ~50 B for new stored property `_fusedQKVGateRows`.
- Well within 20,917 B headroom.

### M4 testability: YES — uses stock MLX matmul, no custom kernels.
### Composes with PR #315: YES — PR #315 re-enables the fused QKV bank; this idea
extends it to include g_proj. Can be implemented on top of PR #315's branch.
### Risk: LOW. Same fusion pattern as decode. No custom kernels. No M5 Metal concerns.

---

## Idea 2: Fuse Router Top-8 into Residual+RMSNorm+Router Kernel (Decode) ★★☆

**Priority**: 2
**Component**: Decode (75% of score) — 39 sparse layers
**Status**: NOT assigned, NOT tried, NOT in exhausted list

### Current flow (2 dispatches per sparse layer):
1. Residual + RMSNorm + router GEMV: `lagunaResidualRMSNormRouter` (line 948)
   → outputs: `summed` [1,1,2048], `normalized` [1,1,2048], `routerLogits` [1,1,256] BF16
2. Router top-8 selection: `lagunaDecodeRouterTop8` (line 9536)
   → outputs: `indices` [1,1,8] uint32, `weights` [1,1,8] float32

### Proposed flow (1 dispatch per sparse layer):
A single kernel that computes the residual add, RMSNorm, router GEMV, AND the top-8
selection (sigmoid + correction bias + bitonic sort + normalization).

### Why this works:
- The router top-8 kernel is a SINGLE threadgroup (grid: 256, threadGroup: 256) — it
  processes all 256 elements in one threadgroup. The residual+RMSNorm+router kernel
  uses multiple tiles (currently `rowsPerGroup=4`, so 64 tiles of 512 threads).
- To fuse, restructure the router GEMV to use `rowsPerGroup=256` (1 tile, 512 threads).
  Each thread computes 256/512 = 0.5 router rows (512 threads for 256 outputs, 2 threads
  per output, each handling 1024 input elements). After the router GEMV, the top-8
  selection runs in the same threadgroup (the 256 router logits are in threadgroup
  memory or registers after the GEMV).
- The top-8 kernel already uses 256 threads (8 simdgroups of 32 lanes). The router GEMV
  with 512 threads (16 simdgroups) would have more threads than needed for top-8, but
  the extra simdgroups can be idle during the selection phase.

### Bit-exactness: YES (with care)
- The RMSNorm reduction (sum of squares + rsqrt) must match the existing kernel's
  reduction order exactly. With 512 threads (16 simdgroups), the reduction uses
  `simd_sum` within each simdgroup, then a threadgroup barrier, then a serial combine
  across 16 simdgroup sums. This is different from the current multi-tile kernel where
  each tile does an independent RMSNorm reduction.
- **CRITICAL**: The current multi-tile kernel has each tile independently computing the
  RMSNorm (all tiles load the full 2048-element residual and compute the same sum-of-
  squares). With 1 tile, the RMSNorm is computed once — but the reduction order across
  16 simdgroups must match the current 1-simdgroup `simd_sum` exactly. The existing
  `lagunaResidualRMSNormRouterSource` (line 761) already handles multi-simdgroup
  reduction — need to verify the 16-simdgroup case matches.
- The router GEMV with `rowsPerGroup=256` changes the tile count from 64 to 1, but each
  router row's K-loop is independent (same accumulation order per row). The BF16→FP32
  cast for the top-8 must match the existing cast-sink path.
- The top-8 bitonic sort network must produce the same indices/weights as the separate
  kernel. Same comparator, same FP32 sigmoid, same correction bias.

### Bandwidth impact: NEUTRAL (dispatch savings only)
- Same data read/written. Saves 1 dispatch boundary (routerLogits write + read).
- The routerLogits buffer (256 BF16 = 512 bytes) is tiny but the dispatch overhead
  is ~2.5 µs.

### Expected speedup:
- 39 dispatches eliminated. At ~2.5 µs/dispatch: ~97.5 µs/step.
- At ~10 ms/step: ~1.0% decode speedup.
- Score: 1.0% × 0.75 = **~0.75% score**.

### Implementation:
1. Create a new kernel variant `lagunaResidualRMSNormRouterTop8` with `rowsPerGroup=256`.
2. Add top-8 selection (sigmoid + correction bias + bitonic sort + normalization) to
   the kernel epilogue, after the router GEMV.
3. Output: `summed`, `normalized`, `routerIndices` [8] uint32, `routerWeights` [8] float32.
   Drop the `routerLogits` output (no longer needed externally).
4. Modify `LagunaRuntimeSparseMoEBlock.forward` to use the fused output directly.

### Budget: ~1500-2500 B in LRM
- ~800-1500 B for the top-8 selection kernel source (bitonic sort network — can be
  copied from `lagunaDecodeRouterTop8KernelSource` and adapted).
- ~300 B for the new kernel definition and dispatch wrapper.
- ~200 B for call site changes.
- Tight but feasible within 20,917 B headroom.

### M4 testability: YES — custom JIT kernel, runs on M4.
### Risk: MEDIUM. The 1-tile router GEMV has 64× less parallelism (512 threads vs 32768).
The router GEMV is tiny (256×2048) so the 1-tile version may be fast enough that
dispatch elimination dominates. But if the GEMV is slower in 1-tile form, the net
effect could be neutral or negative. Must measure.
### Mitigation: The kernel can be designed to support both `rowsPerGroup=256` (fused)
and `rowsPerGroup=4` (unfused) via the existing flag system, so the unfused path
remains as a fallback.

---

## Idea 3: Prefill Shared Expert SiLU-Product Fold into Gate/Up QMM ★★☆

**Priority**: 3
**Component**: Prefill (25% of score) — 39 sparse layers' shared expert
**Status**: NOT assigned, NOT tried

### Current flow (3 dispatches per shared expert per prefill layer):
1. Gate/up QMM: `MLX.quantizedMM(x, fusedWeight, ...)` → [1, L, 2×512] BF16
2. SiLU product: `compiledSiluProduct(gate, up)` → [1, L, 512] BF16 (1 dispatch)
3. Down QMM: `MLX.quantizedMM(act, down.weight, ...)` → [1, L, 2048] BF16

### Proposed flow (2 dispatches):
1. Gate/up QMM with fused SiLU: custom kernel that reads gate/up codes+scales,
   dequantizes, computes SiLU(gate) × up per element, writes [1, L, 512] BF16.
2. Down QMM: unchanged.

### Why this works:
- The SiLU product is an elementwise operation: `silu(gate) * up` where gate and up are
  halves of the QMM output. A custom NVFP4 QMM kernel can compute the SiLU product
  inline, writing only the 512-wide activation instead of the 1024-wide [gate; up]
  intermediate.
- This eliminates the 1024-wide intermediate write + read: [1, 512, 1024] BF16 = 1 MB
  per layer. 39 layers × 1 MB = 39 MB saved per prefill pass.
- The SiLU product itself is cheap (elementwise), but the 1 MB write+read is bandwidth.

### Bit-exactness: YES (with care)
- The NVFP4 dequantization and accumulation must match MLX's `quantizedMM` exactly.
  This requires reproducing the full NVFP4 QMM kernel (codes, scales, group-16, etc.)
  in a custom Metal kernel. The SiLU epilogue (`bfloat(silu(bfloat(gate)) * bfloat(up))`)
  must match `compiledSiluProduct` exactly.
- **RISK**: Reproducing MLX's quantizedMM in a custom kernel is complex. The
  existing decode kernels (lagunaSharedSwiGLUQMV) already do this for the GEMV case.
  The prefill case is a GEMM (M=512, not M=1), which requires a different tiling
  strategy. The existing `lagunaFusedSortedRoutedGateUp` (line 9769) already has a
  GEMM-scale NVFP4 kernel for the routed experts with expert-aligned gather. Could
  the same approach work for the shared expert?

Actually, looking more carefully: the prefill shared expert already has a path through
the existing NVFP4 QMM. The SiLU fold would need a custom GEMM kernel. This is more
complex than the decode SwiGLU QMV fusion.

### Alternative simpler approach:
If the routed expert prefill path already uses `lagunaExpertAlignedGatherEnabled` with
an inline SiLU (line 9819-9829), the same mechanism could be applied to the shared
expert. The shared expert uses the same NVFP4 format. The `lagunaFusedSortedRoutedGateUp`
function already handles the inline SiLU for routed experts — could the shared expert
use a similar path?

### Expected speedup:
- 39 dispatches eliminated (SiLU product). ~97.5 µs.
- 39 MB bandwidth saved. ~0.1 ms.
- Prefill ~4 ms. Total: ~200 µs / 4 ms = ~5% prefill speedup.
- Score: 5% × 0.25 = **~1.25% score**.

### Budget: ~1000-2000 B in LRM (custom kernel or call site changes).
### M4 testability: YES (if using existing expert-aligned mechanism) or NO (if custom GEMM).
### Risk: MEDIUM-HIGH. Custom NVFP4 GEMM kernel is complex. If using the expert-aligned
path, lower risk but needs verification that the shared expert's weight layout matches.

---

## Idea 4: Decode Shared Expert Down Scale Halving (Wire Dead Code) ★★☆

**Priority**: 4
**Component**: Decode (75% of score) — 39 sparse layers' shared expert down QMV
**Status**: NOT assigned. Identified in v3 (Idea 3) but NOT yet implemented.

### Current state:
PR #180 already builds `_halvedSharedDownScales` and `_sharedDownScalesEscape` at load
time. The `fusedSharedDownResidual` function (line 8460) already passes the halved
scales to `lagunaSharedDownResidual` (line 8481). BUT: the `lagunaSharedSwiGLUQMV`
kernel at line 8558-8565 already uses halved scales via `fusedSharedDownInputs`.

Wait — let me re-check. The v3 analysis said the shared SwiGLU QMV (gate/up) uses
FULL scales, not halved. But looking at the current code:

Line 8558-8565:
```swift
lagunaTrace("shared gate/up QMV + SwiGLU")
return downProj(
    lagunaSharedSwiGLUQMV(
        x,
        fusedWeight: fusedWeight,
        packedScales: halvedScales,  // ← ALREADY halved!
        gateUpEscape: gateUpEscape
    )
)
```

And line 8481:
```swift
return lagunaSharedDownResidual(
    inputs.activated,
    downWeight: inputs.downWeight,
    downScales: halvedDownScales,  // ← ALREADY halved!
    downScalesEscape: downScalesEscape,
    routed: routed,
    residual: residual
)
```

**This optimization is ALREADY IMPLEMENTED.** The v3 analysis was based on older code.
Both the shared gate/up QMV and the shared down+residual kernel already use halved
scales. This idea is DEAD — no further work needed.

---

## Idea 5: Prefill Input RMSNorm + QKV GEMM Fusion ★☆☆

**Priority**: 5
**Component**: Prefill (25% of score) — 40 attention layers
**Status**: NOT assigned. Listed in potential next experiments (#6) but NOT tried.

### Current flow (2 dispatches per layer):
1. Input RMSNorm: `inputNorm(input)` → [1, L, 2048] BF16 (1 dispatch)
2. QKV GEMM: `matmul(normalizedInput, fusedQKVWeight.T)` → [1, L, QKVdim] (1 dispatch)

### Proposed flow (1 dispatch per layer):
A custom kernel that normalizes each row (RMSNorm) and immediately does the QKV GEMM,
avoiding the materialization of the normalized [1, L, 2048] intermediate.

### Why this is hard:
- The QKV GEMM is [512, 2048] × [2048, QKVdim] — a real GEMM, not a GEMV. MLX uses
  its highly-optimized steel GEMM for this. A custom Metal GEMM would need to match
  steel GEMM's performance, which is very hard.
- The RMSNorm is bandwidth-cheap (read 2048, write 2048 per row). The GEMM is
  bandwidth-expensive (read [512, 2048] input + [2048, QKVdim] weight). The normalized
  intermediate is [512, 2048] BF16 = 2 MB. Fusing saves the 2 MB write + 2 MB read.
- But the custom GEMM would likely be SLOWER than MLX's steel GEMM, negating the
  bandwidth savings.

### Alternative approach (simpler):
Instead of a full custom GEMM, use a two-phase approach:
1. Phase 1: RMSNorm kernel that also prefetches the QKV weight tiles into L2 cache.
2. Phase 2: Standard steel GEMM (now with warm L2).

This doesn't eliminate a dispatch but improves cache behavior. However, MLX's GEMM
already has its own tiling and prefetching, so this may not help.

### Expected speedup: UNCERTAIN
- 40 dispatches eliminated (if full fusion): ~100 µs.
- 80 MB bandwidth saved: ~0.2 ms.
- But custom GEMM overhead may negate savings.
- If the custom GEMM is 10% slower than steel: ~0.4 ms overhead, net negative.

### Budget: ~3000-5000 B in LRM (custom GEMM kernel — very expensive in code size).
### Risk: HIGH. Custom GEMM performance is the bottleneck. The decode path fuses
norm+QKV because it's a GEMV (1 token), which is simple. Prefill is a GEMM (512
tokens), which is much harder to match.
### Verdict: DEFER until other prefill dispatch eliminations are exhausted. The
risk/reward is poor compared to Ideas 1-3.

---

## Summary

| # | Idea | Component | Savings | Est. Score | Budget (LRM) | M4? | Risk | Priority |
|---|---|---|---|---|---|---|---|---|
| 1 | Fuse g_proj into prefill QKV matmul | Prefill | 40 disp + 80 MB | **~1.9%** | ~200-300 B | YES | LOW | **HIGH** |
| 2 | Fuse router top-8 into residual+RMSNorm+router | Decode | 39 disp | **~0.75%** | ~1500-2500 B | YES | MED | **MEDIUM** |
| 3 | Prefill shared expert SiLU fold | Prefill | 39 disp + 39 MB | **~1.25%** | ~1000-2000 B | MAYBE | MED-HIGH | **MEDIUM** |
| 4 | Shared down scale halving | Decode | — | **0%** | 0 B | — | — | DEAD (already done) |
| 5 | Prefill RMSNorm + QKV GEMM fusion | Prefill | 40 disp + 80 MB | **~1.9%** | ~3000-5000 B | NO | HIGH | LOW |

### Primary Recommendation

**Idea 1** is the strongest fresh opportunity. It's the prefill analog of the decode
gate-into-QKV fusion that already works. It eliminates 40 g_proj dispatches by
concatenating g_proj weight rows into the prefill QKV bank — the same pattern the
decode path uses for NVFP4. It's bit-exact (class A: same matmul, same rows, just
concatenated), requires no custom kernels, and is M4-testable. Expected: ~1.9% score
from 40 dispatch eliminations + 80 MB bandwidth savings. Budget: ~200-300 B in LRM.

**Idea 2** is the decode counterpart: fusing the router top-8 selection into the
residual+RMSNorm+router kernel. It eliminates 39 dispatches but requires a kernel
restructure (1-tile router GEMV) and a top-8 bitonic sort network inside the kernel.
Medium risk: the 1-tile GEMV may be slower due to reduced parallelism. Budget is
tight but feasible.

**Idea 3** is a prefill bandwidth optimization: folding the SiLU product into the
shared expert's NVFP4 QMM, eliminating a 1 MB/layer intermediate. Medium-high risk
due to custom GEMM kernel complexity.

### Key Insight

The decode path is heavily optimized (7 dispatches/layer, close to the 5-6 minimum).
The prefill path has more room: ~13 dispatches/layer with several unfused operations.
Idea 1 (g_proj into QKV) is the highest-impact, lowest-risk prefill optimization
because it reuses a proven decode pattern (gate-into-QKV fusion) and requires no
custom kernels. The prefill path is 25% of the score, so a 7.5% prefill speedup
contributes ~1.9% to the final score — significant when the gap to #1 is ~0.7%.

### Composition

- Ideas 1 + 3 compose (both target prefill, different dispatches).
- Idea 2 composes with Ideas 1 + 3 (targets decode, orthogonal).
- All compose with active PR #315 (QKV bank), PR #316 (gate-softplus→O-proj),
  PR #317 (prefill RMSNorm+router), PR #314 (prefill MoE residual).
- Total if all compose: ~1.9% (I1) + 0.75% (I2) + 1.25% (I3) ≈ ~3.9% score.
  From 2.5817 to ~2.68 — would surpass the #1 leaderboard score of 2.6040.

### What Was Checked and Ruled Out

- **Shared down scale halving (v3 Idea 3)**: ALREADY IMPLEMENTED in current code.
  The `fusedSharedDownResidual` and `lagunaSharedSwiGLUQMV` both use halved scales.
- **Prefill RMSNorm + QKV GEMM fusion**: Too risky — custom GEMM can't match MLX's
  steel GEMM performance. Defer.
- **Router top-8 + residual+RMSNorm fusion via multi-tile**: The top-8 needs all 256
  values in one threadgroup. With `rowsPerGroup=4` (64 tiles), no single threadgroup
  has all 256 values. Must use `rowsPerGroup=256` (1 tile) to fuse.
- **Attention mega-kernel (SDPA + gate + O-proj)**: Already ruled out in v3 (32 KB
  threadgroup memory limit). Not revisited.
- **Routed SwiGLU + down fusion**: Already ruled out in v3 (global barrier needed,
  Metal has no efficient cross-TG barrier). Not revisited.
- **KV cache quantization**: Not bit-exact. Not revisited.
- **MoE weight L2 reuse**: Each threadgroup reads unique weight rows. Not revisited.
- **Threadgroup input staging**: Already tried and failed (PR #75 negative, L1/SLC
  handles redundancy). Not revisited.
- **Register prefetch on down+residual kernel**: Already tried and failed (PR #93
  negative, kernel is compute-bound not latency-bound). Not revisited.
- **outputs_per_simd 4→8 on down+residual**: Already tried and failed (PR #89
  negative, register pressure). Not revisited.
- **RMSNorm → LM head fusion**: Already tried and failed (PR #276 negative,
  replicated across 6272 TGs costs 3 barriers each). Not revisited.
