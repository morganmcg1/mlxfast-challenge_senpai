# Fresh Wave Optimization Ideas — 2026-08-07

Ranked list of genuinely fresh, untried bit-exact optimization opportunities
found by deep analysis of the scored decode/prefill paths, MoE dispatch,
attention dispatch chains, weight preparation, and asyncEval scheduling.
Each idea was verified against all existing research notes and the current
merged frontier (commit 6739b6a) to confirm it is NOT already done or dead.

## Budget Constraints (verified at HEAD 6739b6a)

| File | Size | Limit | Headroom |
|---|---|---|---|
| LagunaRuntimeModel.swift | 505,356 | 524,288 | **18,932 B** |
| Total editable surface | 2,967,227 | 3,000,000 | **32,773 B** |

LRM has 18,932 B headroom (more than the 2,698 B stated in the brief —
the brief figure may predate PR #286 or use a conservative estimate).
Total surface has 32,773 B headroom. Per-file limit is 524,288 B.
Growth limit per review is 262,144 B.

## Current Frontier (25+ merged changes, all bit-exact)

Key merged changes:
- NVFP4 QKV R1 + g_proj fusion (decode, PR #230)
- INT8 O-proj dot4 vectorization (decode, PR #245)
- Prefill shared expert scale halving + array precomputation (PR #243/#253)
- Router keys dead output elimination (decode, PR #254)
- Full-attention params atlas (decode, PR #258)
- Merge shared gate/up QMV into routed dispatch (decode, PR #267)
- LRM doc comment compression (PR #278)
- Down/O-proj tiling results_per_simdgroup doubling (PR #280/#283/#286)
- Shared SwiGLU gate/up halving (wired, was dead code in PR #180)
- Prefill QK-norm+RoPE fusion (default ON)
- Prefill residual+RMSNorm fusion (default ON)
- Prefill MoE tail fusion (default ON)
- asyncEval schedule: at:0,1,7,15,23,31,39 (decode) + stride 1 (prefill)

## Exhausted Directions (confirmed dead, DO NOT re-suggest)

All items from the task brief's EXHAUSTED DIRECTIONS list, plus:
- Prefill O-proj gate dispatch fusion via MLX compile() (REFUTED, commit 8841cd9)
- RMSNorm fusion into NVFP4 QKV (regressed +2.7%)
- Prefill values transpose fold (asyncEval hides overhead)
- BK padding reduction (bank conflicts)
- Register-resident scale pre-loading (already done via prefetch)
- Texture-backed NVFP4 weight storage (no editable path)
- Router GEMV + top-8 fusion (already done)
- Down+residual register prefetch (regressed, compute-bound not latency-bound)
- Down+residual outputs_per_simd 4→8 (regressed, register pressure)
- Variant 4 (BM128/WM4/WN2, loses reglocal SwiGLU)
- SHARED_FIRST_DOWN (dead arm, collapsible ternary)
- RoPE atlas views (measured null, default OFF)

---

## Idea 1: Prefill QKV+Gate Bank Fusion (BF16, LRM-only, no _nax) ★★★

**Priority**: 1 (highest — pure dispatch elimination, bit-exact, proven pattern)
**Component**: Prefill (25% of score) — all 39 sparse layers + layer 0
**Mechanism**: For prefill (L > 1), the attention layer dispatches Q, K, V, and
gate as 4 SEPARATE BF16 matmuls. The fused QKV bank (`_fusedQKVWeight`,
`DARKBLOOM_FUSED_QKV`) is already implemented but disabled (default OFF)
because PR #261 was bundled with _nax changes that caused M5 build failures.
The _nax revert disabled the flag, but the LRM BF16 fusion code is intact
and independent of any _nax vendor file.

This idea has two parts:
1. **Re-enable `DARKBLOOM_FUSED_QKV` default ON** (change `== "1"` to `!= "0"`
   at L113). This activates the existing `_fusedQKVWeight` concatenation
   and single-matmul QKV dispatch for prefill. Eliminates 2 dispatches
   per layer (3 separate matmuls → 1 fused matmul) × 39 sparse layers =
   **78 dispatches per prefill**.

2. **Extend the fused bank to include gate weight** (NextWave2 Idea 4,
   untried). Add `_fusedQKVGateWeight` by concatenating `gProj.weight`
   after the QKV bank, then slice the gate from the fused output. This
   eliminates 1 more dispatch per layer = **39 more dispatches per prefill**.

### Target evidence:
- L108-113: `lagunaFusedQKVEnabled` flag (currently `== "1"`, needs `!= "0"`)
- L5656-5674: `prepareFusedQKVWeight()` — builds concatenated `[Wq; Wk; Wv]`
- L5963-5980: prefill QKV branch — uses `matmul(normalizedInput, fusedQKVWeight.T)`
- L6200-6210: prefill gate path — `gProj(normalizedInput)` as separate dispatch
- L6480-6500: `callLastPrefillRow` already fuses `[Wq; Wgate]` — proven pattern

### Bit-exactness: YES
- Row concatenation of bias-free `Linear` weights is bit-exact: each output
  row's K-loop is independent (proven by `_lastPrefillQGateWeight` at L6480
  which already fuses Q+gate for the terminal layer).
- Same BF16 matmul, same K-loop, same accumulation order.

### Bandwidth impact: NEUTRAL (dispatch savings only)
- Same weight bytes read (fused = concatenated, same total bytes).
- Eliminates 78-117 dispatches per prefill (QKV fusion + optional gate).

### Expected speedup:
- 78 dispatches × ~2.5µs = ~195µs (QKV only) or 117 × 2.5 = ~293µs (with gate)
- If prefill takes ~10-20ms: ~1-2.9% prefill speedup
- Score: ~1-2.9% × 0.25 = **~0.25-0.73% score**

### Budget impact:
- Part 1: ~4 bytes (change `== "1"` to `!= "0"`)
- Part 2: ~+200-400 B (2 new properties, init extension, call site change)
- **Fits within 18,932 B headroom**

### M4 testability: YES
- The fused bank is built at init from the same BF16 weights.
- Verify via `--local-iterate` (max_abs_diff = 0) and upstream equivalence.

### Why it's fresh:
The BF16 QKV fusion (PR #261) was reverted as part of the _nax rollback, but
it's pure LRM — no _nax dependency. Re-enabling it is a 4-byte flag change.
The gate extension (NextWave2 Idea 4) was proposed but never assigned/implemented.

### Risk: LOW
- The fusion code is already implemented and tested (was ON before the revert).
- The revert was triggered by _nax vendor changes, NOT the LRM QKV fusion.
- The ranked runner sets NO env vars, so the source default (`!= "0"`) controls.

### Composability:
- Composes with all decode optimizations (different path, L > 1)
- Composes with prefill QK-norm+RoPE fusion (different stage)
- Composes with prefill MoE tail fusion (different block)

---

## Idea 2: Prefill Residual+RMSNorm+Router GEMM Fusion ★★☆

**Priority**: 2 (medium — eliminates 39 dispatches, but complex kernel)
**Component**: Prefill (25% of score) — all 39 sparse layers
**Mechanism**: For prefill (L > 1), the residual+RMSNorm is fused
(`lagunaPrefillFusedResidualRMSNormEnabled`, L5689) but the router matmul
`x.matmul(weight.T)` is a SEPARATE dispatch. The decode path fuses
residual+RMSNorm+router into ONE dispatch (`lagunaResidualRMSNormRouter`),
but it's guarded by single-token shape (`x.dims(1, 1, hiddenSize)` at L10533).

The prefill path computes:
1. `lagunaResidualRMSNorm(residual, branch, weight)` — 1 dispatch (L5689)
2. `gate(x, logits: nil)` → `x.matmul(weight.T)` — 1 separate dispatch (L9525)

The router is `[256, 2048]` — for 512 input tokens, it's a `[1, 512, 2048] ×
[256, 2048]^T → [1, 512, 256]` GEMM. This could be folded into the
residual+RMSNorm kernel as an additional output stream.

### Target evidence:
- L10530-10547: decode residual+RMSNorm+router fusion guard (requires L==1)
- L10556-10570: prefill residual+RMSNorm path (no router)
- L9523-9525: `gate(x, logits: routerLogits)` → `x.matmul(weight.T)` when nil
- L10446-10449: sparse MoE forward — `routerLogits` is nil for prefill

### Bit-exactness: YES
- The router matmul is a standard GEMM with no reduction order sensitivity
  (each output row is independent). Fusing it into the residual+RMSNorm
  kernel preserves the exact same computation.
- The router uses logit softcapping (`tanh(x/softcap) * softcap`) applied
  AFTER the matmul. The fused kernel would emit raw logits and the
  softcapping would be applied by the downstream `gate` function.

### Bandwidth impact: NEUTRAL (dispatch savings only)
- Same weight bytes read (router weight is the same).
- Eliminates 39 router matmul dispatches per prefill.

### Expected speedup:
- 39 dispatches × ~2.5µs = ~98µs
- If prefill takes ~10-20ms: ~0.5-1% prefill speedup
- Score: ~0.5-1% × 0.25 = **~0.125-0.25% score**

### Budget impact: ~+800-1500 B in LRM
- New kernel variant for prefill (multi-token residual+RMSNorm+router)
- The existing `lagunaResidualRMSNorm` kernel is row-general; the router
  GEMM adds 256 output rows per input row. Threadgroup structure changes.
- **Fits within 18,932 B headroom** but consumes significant budget.

### M4 testability: YES
- Custom JIT kernel, runs on M4.

### Why it's fresh:
The decode residual+RMSNorm+router fusion exists (L10530) but is gated to
single-token. No previous work proposed extending it to prefill. The
prefill path was optimized for residual+RMSNorm fusion (L10556) but the
router was left as a separate dispatch.

### Risk: MEDIUM
- The router GEMM for prefill is 512 rows × 256 outputs — a genuine GEMM,
  not a GEMV. The kernel must handle this differently from the decode
  single-row router GEMV.
- Threadgroup structure for 512-row input + 256-output router may be complex.
- The router matmul uses `tanh` softcapping which must be preserved in the
  downstream path.

---

## Idea 3: Prefill Gate-Product+Softplus Multi-Token Kernel ★☆☆

**Priority**: 3 (lower — eliminates 39-78 dispatches, small per-dispatch gain)
**Component**: Prefill (25% of score) — all 40 attention layers
**Mechanism**: For prefill (L > 1), the attention O-proj gate chain is:
1. `lagunaCompiledSoftplusGate(projectedGate)` — compiled softplus (1 dispatch)
2. `output * gate` — broadcast multiply (1 dispatch)
3. `wo(output)` — quantizedMM (1 dispatch)

The `lagunaGateProductSoftplus` kernel (L3740) fuses softplus + gate product
into 1 dispatch, but it's gated to single-token decode (`output.dims(1, 1, inVec)`).
Extending it to multi-token (L > 1) would eliminate 1 dispatch per layer.

### Target evidence:
- L3740-3770: `lagunaGateProductSoftplus` — single-token gate product+softplus
  kernel with `output.dims(1, 1, inVec)` guard
- L6345-6375: prefill O-proj path — separate softplus + multiply + wo

### Bit-exactness: YES
- The kernel computes the same softplus formula (same log1p/exp) and the
  same broadcast multiply. Extending to L tokens just changes the grid
  dimensions and output shape — the per-element arithmetic is identical.
- No FP reduction order changes (elementwise operations).

### Bandwidth impact: NEUTRAL (dispatch savings only)
- Same inputs, same outputs.
- Eliminates 40-78 dispatches per prefill (softplus+multiply → 1 dispatch).

### Expected speedup:
- 40 dispatches × ~2.5µs = ~100µs
- If prefill takes ~10-20ms: ~0.5-1% prefill speedup
- Score: ~0.5-1% × 0.25 = **~0.125-0.25% score**

### Budget impact: ~+200-400 B in LRM
- Add multi-token variant of the kernel (new grid/output shape).
- Add call site for prefill path.

### M4 testability: YES

### Why it's fresh:
The `lagunaGateProductSoftplus` kernel exists for decode but was never
extended to prefill. The prefill path still uses the separate compiled
softplus + broadcast multiply. Note: the compiled softplus fusion via
`attentionGateProjection` was REFUTED (commit 8841cd9) — but that attempted
to fuse softplus + gate + MATMUL into one compiled graph. This idea only
fuses softplus + gate product (no matmul), leaving the quantizedMM separate.

### Risk: LOW
- The kernel is a simple elementwise operation; extending to L tokens is
  straightforward (change grid from `(inVec, 1, 1)` to `(inVec * L, 1, 1)`).
- The matmul stays separate, so no complex fusion.

---

## Idea 4: Prefill QKV Bank Gate Weight Concatenation (extension of Idea 1) ★★☆

**Priority**: 4 (pairs with Idea 1 part 2)
**Component**: Prefill (25% of score)
**Mechanism**: If `DARKBLOOM_FUSED_QKV` is re-enabled (Idea 1 part 1),
extend `prepareFusedQKVWeight` to concatenate `gProj.weight` after the
QKV bank, producing `[Wq; Wk; Wv; Wgate]`. The prefill path then slices
the gate from the fused output, eliminating the separate `gProj` matmul.

### Target evidence:
- L5656-5674: `prepareFusedQKVWeight()` — builds `[Wq; Wk; Wv]`
- L6200-6210: prefill gate path — `gProj(normalizedInput)` separate dispatch
- L6480-6500: `callLastPrefillRow` already fuses `[Wq; Wgate]` — proven pattern

### Bit-exactness: YES
- Same as Idea 1: row concatenation of bias-free Linear weights is bit-exact.
- The gate weight `[nHeads, hiddenSize]` shares the same hidden dimension
  as QKV weights.

### Bandwidth impact: NEUTRAL (dispatch savings only)
- Eliminates 39 gate matmul dispatches per prefill.

### Expected speedup:
- 39 dispatches × ~2.5µs = ~98µs
- Score: ~0.98% × 0.25 = **~0.125% score** (standalone, composes with Idea 1)

### Budget impact: ~+200-400 B in LRM
- 2 new properties (`_fusedQKVGateWeight`, `_fusedQKVGateSplit`)
- Init extension (~6 lines)
- Call site change (~4 lines)

### M4 testability: YES

### Why it's fresh:
NextWave2 Idea 4 proposed this but it was never assigned or implemented.
It depends on `DARKBLOOM_FUSED_QKV` being enabled (Idea 1 part 1).

### Risk: LOW
- Same pattern as the already-merged `_lastPrefillQGateWeight`.

---

## Idea 5: Dead Code Removal for Budget Recovery ★☆☆

**Priority**: 5 (enabling — frees LRM bytes for larger kernel changes)
**Mechanism**: The `DEAD_CODE_REMOVAL.md` plan identifies ~12,096 B of
removable dead code in LRM:
1. V1 ablation kernels in LmHeadPrune (~4,305 B) — in a DIFFERENT file,
   frees that file's budget but not LRM
2. PREFILL_TAIL_WIDELD dead arm (~2,056 B) — collapsible ternary in LRM
3. SHARED_FIRST_DOWN dead arm (~1,344 B) — collapsible ternary in LRM
4. Measured-null warmup function bodies (~3,125 B) — in LRM

Removing items 2-4 frees ~6,525 B in LRM, increasing headroom from 18,932 B
to ~25,457 B. This enables larger kernel changes (like Idea 2's prefill
residual+RMSNorm+router fusion) without exceeding the budget.

### Target evidence:
- research/DEAD_CODE_REMOVAL.md: full analysis of dead code candidates
- L7770-7776: `lagunaSharedFirstDownOrderEnabled` — dead ternary, never measured
- Various PREFILL_TAIL_* dead arms

### Bit-exactness: YES — removing dead code paths changes nothing.
### Budget impact: NET NEGATIVE (~-6,525 B in LRM)
### M4 testability: YES

### Why it's fresh:
The dead code removal was planned but never executed. It's the cheapest
way to free LRM budget for more ambitious kernel changes.

### Risk: VERY LOW — only removes code paths that are provably unreachable
or measured-null.

---

## Summary Ranking

| # | Idea | Component | Mechanism | Score Est. | Budget (LRM) | M4? | Risk |
|---|---|---|---|---|---|---|---|
| 1 | Re-enable BF16 QKV fusion + gate ext | Prefill | Dispatch elim (78-117) | ~0.25-0.73% | ~200-404 B | YES | LOW |
| 2 | Prefill residual+RMSNorm+router GEMM | Prefill | Dispatch elim (39) | ~0.125-0.25% | ~800-1500 B | YES | MEDIUM |
| 3 | Prefill gate-product+softplus multi-token | Prefill | Dispatch elim (40) | ~0.125-0.25% | ~200-400 B | YES | LOW |
| 4 | QKV bank gate concatenation | Prefill | Dispatch elim (39) | ~0.125% | ~200-400 B | YES | LOW |
| 5 | Dead code removal | N/A | Budget recovery | 0% | -6,525 B | YES | VERY LOW |

### Primary Recommendation

**Idea 1** is the strongest opportunity. Re-enabling `DARKBLOOM_FUSED_QKV`
(the BF16 prefill QKV bank fusion) is a 4-byte flag change that activates
already-implemented, already-tested code. The fusion was reverted only
because it was bundled with _nax vendor changes that caused M5 build
failures — the LRM fusion itself is independent and safe. Extending the
fused bank to include the gate weight (Idea 4) adds ~200-400 B for an
additional ~0.125% score.

**Idea 2** (prefill residual+RMSNorm+router GEMM fusion) is the next
target after Idea 1, but requires a more complex kernel and higher
budget. Idea 5 (dead code removal) should be done first to free budget
if Idea 2 is pursued.

### Key Insight

The prefill path (25% of score) still has significant dispatch elimination
opportunities that the decode path already captured. The decode path is
fully fused (3 dispatches/layer), but the prefill path still uses
separate Q/K/V/gate matmuls and a separate router dispatch. These are
all LRM-only changes (no _nax dependency) and fit within the budget.
