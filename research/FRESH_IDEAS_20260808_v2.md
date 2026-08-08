# Fresh Optimization Ideas — 2026-08-08 v2

**Score gap:** 2.5888 (our best) vs 2.6063 (leaderboard #1, yudduy). Gap: ~0.67%.
**Score formula:** decode_speedup^0.75 × prefill_speedup^0.25. Decode 75%, prefill 25%.
**M5:** bandwidth-bound, ~89% GPU util, ~651.8 GB/s, 40 GPU cores, 128 GB unified memory.
**M5 build timeout:** ~900s. Total compile time (19 custom JIT + 15-25 _nax + 2 graph) at boundary.
**Budget:** LRM ~291KB headroom. Total surface ~267KB headroom. Per-file 512KB cap.

---

## Context: What's Genuinely Exhausted

Based on 30+ prior research files and 40+ merged/closed PRs, the following approaches are DEAD:
- Custom GEMM/GEMV kernels (can't beat MLX's optimized GEMM — PRs #317, #325, #326, #334)
- RMSNorm fusion into matmul kernels (FP reduction order changes flip tokens — PRs #276, #349)
- simd_sum(vec)/dot(float4)/thread float4* casts (M5 build failure)
- Unsorted gatherQuantizedMM (+39.7% prefill regression — sorting essential for locality, PR #348)
- Grid over-dispatch (MLX grid = total threads, not threadgroups — PRs #333, #394)
- Full-attention QK-norm+YaRN fusion on M4 (PR #356: -3.3% decode on M4, but M4 ≠ M5)
- Scale halving for prefill kHalvedScales (M5 compile-storm, reverted in PR #398)
- asyncEval tuning (current 7-fire schedule proven optimal, PRs #337, #335)
- KV cache quantization (outside accepted attention envelope)
- Custom flash-attention SDPA kernel (the SDPA vector kernel is already AOT-optimized)

## Architecture
- 40 layers: layer 0 = dense BF16 MLP, layers 1-39 = sparse MoE (NVFP4)
- 10 full-attention (48 Q heads, 8 KV heads, GQA-6, YaRN) + 30 sliding (64 Q heads, 8 KV heads, GQA-8, window 512)
- MoE: 256 routed experts (top-8) + 1 shared expert. moeIntermediateSize=512, hiddenSize=2048
- Decode: ~324 dispatches/step, ~8 per layer, ~5.4 ms/step
- Bandwidth at 1.0× amplification (each weight byte read once)
- Decode MoE: already 2 dispatches/layer (fused gate/up+SwiGLU + fused down+residual)
- Decode attention: sliding = 4 dispatches (fused), full = ~11 dispatches (STOCK path)

---

## Idea 1: Revive XMAJOR Column-Tile Fold for Prefill Expert Gather-QMM ★★★★

**Path:** Prefill (25%) — but prefill speedup also improves decode score
**Expected impact:** 0.3–0.5% total score
**Risk:** Medium-high (M5-only kernel, needs reimplementation)

### Mechanism
The expert-aligned prefill gather-QMM (`fp_gather_qmm_rhs_expert_nax` in `fp_quantized_nax.h:1573`) currently walks one BN=64 column tile per threadgroup. With an XMAJOR fold of 2, each threadgroup loads the expert's x fragments once per k-tile and reuses them across 2 adjacent column tiles, halving x DRAM traffic.

The kernel arms were DELETED but the dispatch and JIT injection infrastructure remain intact:
- `darkbloom_gather_xmajor_ct()` at `quantized.cpp:1563-1567` returns `0` (pinned OFF)
- `darkbloom_gather_xmajor_define()` at `jit_kernels.cpp:1169-1185` injects `#define DARKBLOOM_GATHER_XMAJOR ct` into the expert kernel source
- Grid dispatch at `quantized.cpp:1915-1921` divides grid.x by `xmajor_ct`
- The comment at `quantized.cpp:1564-1565` says "keep the dispatch/JIT contract coherent by pinning the fold OFF"

### Bandwidth analysis
Prefill expert gather-QMM is ~54% of prefill time (quantized.cpp:1277). The x input is [512, 2048] BF16 = 2 MB per layer. With current 1-tile fold, each x fragment is loaded once per column tile. With fold=2 (BN=64, N=1024 → 16 column tiles → 8 threadgroups), x traffic halves from ~2 MB to ~1 MB per gate/up pass. Over 39 MoE layers × 2 passes (gate/up + down): ~156 MB → ~78 MB saved. At 500 GB/s: ~0.16 ms prefill saving.

### Bit-exactness
x is read-only. The same x fragments are used for both column tiles. MMA chain order is unchanged (k ascending, tiles in order). Store writes to disjoint output regions. **Bit-exact.**

### Budget
- Re-implement XMAJOR kernel arms in `fp_quantized_nax.h`: ~100–150 lines (~5 KB)
- Change `darkbloom_gather_xmajor_ct()` return from 0 to 2: 1 line
- `fp_quantized_nax.h` has ~444 KB headroom (79,620 / 524,288)
- 0 bytes in LRM

### M5 safety
- Uses `#define` injection (not function constants), so exactly one pipeline variant is compiled — no compile count increase
- M4 cannot test this (M4 gen < 17, no `_nax` kernels). M5-only validation required.
- The kernel was previously compiled and bit-exact when the arms existed; reimplementation must match the original tiling pattern

### Implementation
1. In `fp_gather_qmm_rhs_expert_nax` (`fp_quantized_nax.h:1573`), add a column-tile loop under `#ifdef DARKBLOOM_GATHER_XMAJOR`:
   - Load Atile (x fragments) once before the column-tile loop
   - For each column tile `xtile in 0..<DARKBLOOM_GATHER_XMAJOR`: stage Ws, MMA, SwiGLU reglocal epilogue, store
2. Change `darkbloom_gather_xmajor_ct()` to return 2
3. Grid dispatch at `quantized.cpp:1919-1921` already divides by xmajor_ct

---

## Idea 2: Compile Budget Engineering to Re-enable Prefill QK-Norm+RoPE Fusion ★★★★

**Path:** Prefill (25%) — but prefill speedup also improves decode score
**Expected impact:** 0.3–0.5% total score (the fusion itself was measured at +1.5% prefill)
**Risk:** Low for correctness, Medium for M5 build (the core constraint)

### Mechanism
The prefill QK-norm+RoPE fusion (`DARKBLOOM_PREFILL_QK_NORM_ROPE`) was MERGED (PR #357) then TACTICALLY DISABLED because it added 2 JIT compiles that pushed the M5 build over the ~900s timeout. The fusion eliminates 5 dispatches per layer × 40 layers = 200 dispatch eliminations per prefill forward.

The fusion kernels already exist in the LRM source and are bit-exact. The only blocker is compile count.

### Strategy: Free 2 JIT compile slots to make room
Current default JIT compile count: 19 custom + ~15-25 _nax + 2 graph = ~36-46 total.

**Slot 1:** LM-head pruner kernel consolidation. The pruner has 4 `metalKernel` instances (`LagunaLmHeadPrune.swift:152, 276, 362, 499`). PR #380 already proposed reducing from 6→4. Can we go further? The coarse kernel (line 152) has a `mode` input that selects one-pass vs base-plane-only — this is already a unified kernel. The argmax stage-1 (line 276) and threshold kernel (line 362) could potentially be merged into a single 2-phase kernel if the argmax output feeds directly into the threshold computation. **Saves 1 JIT compile.**

**Slot 2:** Delete the `lagunaGatedAffineOProjIndexedKernel` (`LRM:1863`) if the indexed metadata path (`DARKBLOOM_AFFINE_METADATA_INDEXED`) is never the dispatched path during scored execution. The indexed kernel is an alternative to `lagunaGatedAffineOProjKernel` (`LRM:1852`). If the non-indexed path is always taken (default), the indexed kernel's `metalKernel` instance is never accessed and never JIT-compiles. Verify that the indexed path is truly never dispatched in the scored path. If confirmed, deleting the declaration frees budget without reducing compile count (it's already lazy). **But if it IS compiled, deleting saves 1 JIT compile.**

**Alternative slot 2:** Consolidate the 2 compiled gate functions (`lagunaCompiledSoftplusGate` at LRM:2594 and `lagunaAttentionGateProjection` at LRM:2606) into 1. The attention gate projection already infers head count from output shape. The standalone softplus gate is only used for prefill (multi-token). Could the shapeless attention gate projection serve both? **Saves 1 MLX graph compile.**

### Bit-exactness
All changes are dispatch-path or compile-count changes. The prefill QK-norm+RoPE fusion is already proven bit-exact (PR #357). The kernel consolidation is bit-exact if the merged kernel produces identical arithmetic.

### Budget
- Re-enabling prefill QK-norm+RoPE: 0 bytes (kernel source already exists, just flip the flag default)
- Kernel consolidation: potentially negative (removing redundant kernel declarations)

### M5 safety
The entire point is to REDUCE compile count. Net compile change should be ≤0 after consolidation.

---

## Idea 3: Full-Attention Fused Decode Kernel (Offset Compile Cost) ★★★

**Path:** Decode (75%)
**Expected impact:** 0.3–0.7% decode (10/40 layers go from ~11 dispatches to ~4)
**Risk:** Medium (M4 regression was -3.3%, but M5 has 40 cores and uses _nax)

### Mechanism
Full-attention layers (10 of 40) run the STOCK decode path with ~11 dispatches per layer:
1. Fused norm+affine QKV (1 dispatch)
2. qNorm + transpose (1)
3. kNorm + transpose (1)
4. applyRotaryPosition(queries) (1)
5. applyRotaryPosition(keys) (1)
6. values reshape/transpose (1, metadata for L=1)
7. cache.update(keys, values) (2: K write + V write)
8. scaledDotProductAttention (1)
9. attentionGateProjection (1, compiled)
10. wo(output) matmul (1)
= 11 dispatches

The sliding counterpart runs 4 dispatches via `lagunaSlidingFusedAttentionKernel`. Creating a similar fused full-attention kernel would reduce to ~4 dispatches, saving ~7 dispatches × 10 layers = 70 dispatches per decode step.

### Why this is different from PR #356 (which failed)
PR #356 enabled `DARKBLOOM_FUSED_FULL_QK_NORM_YARN` which activates the EXISTING full-attention fusion kernels. It showed -3.3% decode on M4. But:
- M4 has 16 GPU cores (not 40), different pipeline depth
- M4 doesn't select `_nax` kernels
- The regression may be kernel-specific to M4's architecture
- The existing kernel (`lagunaFullFusedAttentionKernel`) may not be as optimized as the sliding kernel
- The test was on M4, which AGENTS.md explicitly says is "directional evidence only" for _nax changes

### Bit-exactness
The full-attention fused kernel (`lagunaFullFusedAttentionKernel`, `LRM:1784`) and `lagunaFullQKNormYaRNKernel` (`LRM:1016`) already exist with documented bit-exactness. The sliding counterpart has been shipping bit-exact since `9e06de6`. The RoPE angle atlas rows are the family's own stock RoPE outputs copied.

### Budget
- 0 bytes (kernel sources already exist in LRM)
- Only the flag default changes from `== "1"` (OFF) to `!= "0"` (ON)
- BUT: adds 2 JIT compiles (the full QK-norm+YaRN kernel + full fused attention kernel)
- Also enables RoPE angle atlas construction (benefits sliding layers too)

### M5 safety
The 2 extra JIT compiles must be offset by consolidation (see Idea 2). The key question is whether the dispatch savings on M5's 40-core GPU outweigh any per-kernel overhead. The sliding counterpart showed +1.73% when enabled. Full-attention is 10/40 = 25% of layers, but with larger per-layer savings (11→4 vs ~5→4 for sliding).

### Risk mitigation
1. First verify M5 build succeeds with the 2 extra compiles (offset by Idea 2's consolidation)
2. If M5 build fails, the flag can be disabled at runtime without code changes
3. Test on M5 directly — M4 results are not valid evidence for this kernel family

---

## Idea 4: LM-Head Pruner — Fuse Final RMSNorm Into Coarse Pass ★★★

**Path:** Decode (75%)
**Expected impact:** 0.05–0.15% decode (1 dispatch elimination per step)
**Risk:** Medium (RMSNorm FP reduction order must match exactly)

### Mechanism
The final RMSNorm (`model.norm()`, `LRM:6511`) is applied to the [1,1,2048] hidden state before the LM-head pruner. This is 1 dispatch per decode step. The pruner's coarse kernel (`lagunaLmHeadCoarseKernel`, `LagunaLmHeadPrune.swift:152`) then reads the normalized hidden state and computes a dot product with each of 100,352 int5 coarse rows.

Fusing the RMSNorm INTO the coarse kernel would eliminate 1 dispatch. The coarse kernel already reads the full 2048-element hidden row — it can compute the RMS in the same pass.

### Why this is different from previous RMSNorm fusion failures
Previous failures (PR #276, PR #349) fused RMSNorm into MATMUL kernels where the K-reduction order changed, flipping tokens. This fusion is different:
- The pruner's coarse kernel is a GEMV (1 token × 100352 vocab rows), not a matmul
- The RMSNorm is over the 2048 hidden elements — computed ONCE, not per-vocab-row
- The norm computation is a single 2048-element reduction, done in one threadgroup
- The pruner already does FP32 reductions per-row for the dot product
- The RMSNorm reduction order can match the stock `rms_norm.metal` AOT kernel if the same `simd_sum` pattern is used

### Bit-exactness concern
The stock RMSNorm (`rms_norm.metal`, AOT) computes `sum(x²)` in FP32 via a threadgroup reduction with a specific lane pattern. The fused coarse kernel must replicate this exact pattern. If the coarse kernel uses the same `simd_sum` + threadgroup reduction tree, the FP32 sum-of-squares is bit-identical. The `rsqrt` and `× weight` operations are deterministic.

**Key risk:** The coarse kernel processes 16 rows per threadgroup. The RMSNorm would need to be computed by a separate reduction pass (either a pre-phase in the same dispatch or a dedicated simdgroup) before the per-row dot products begin. This adds a barrier but eliminates the separate dispatch.

### Budget
- ~200-500 bytes for the RMSNorm computation added to the coarse kernel source
- The coarse kernel source is in `LagunaLmHeadPrune.swift` which has its own budget (880 lines / 512KB)
- Removes the stock RMSNorm dispatch call from `LRM:6511` (saves ~1 line)

### M5 safety
No new JIT compile (modifies existing kernel source, doesn't add a new kernel). The coarse kernel already compiles. Adding RMSNorm computation to its body doesn't change the compile count.

### Implementation
1. Add `normWeight` and `eps` as new inputs to `lagunaLmHeadCoarseKernel`
2. Before the per-row dot product loop, one simdgroup computes:
   - `sum_sq = simd_sum(x[j] * x[j])` for j in 0..<2048 (across lanes)
   - `rms = rsqrt(sum_sq / 2048 + eps)`
   - `x_normed[j] = x[j] * rms * norm_weight[j]`
3. Use `x_normed` instead of `x` in the dot product
4. Share `x_normed` via threadgroup memory (barrier before per-row computation)
5. Remove `model.norm()` from the call site (`LRM:6511`)

---

## Idea 5: Convert Non-Expert STAGE_* Function Constants to #define Injection ★★☆

**Path:** M5 build reliability (compile count reduction)
**Expected impact:** 0% direct timing, but frees compile budget for Ideas 2-3
**Risk:** Low

### Mechanism
The non-expert `fp_gather_qmm_rhs_nax` kernel (`fp_quantized_nax.h:1210`) uses 8 function constants (fc 200-207). Four of these (`stage_widest` fc 204, `stage_wideld` fc 205, `stage_runbar` fc 206, `stage_novol` fc 207) are process-constant (resolved once via env vars) but expressed as function constants, creating 2^4 = 16 possible pipeline specializations.

The expert path already moved these to `#define` injection (`jit_kernels.cpp:1238-1249`), baking them into the kernel source before compilation. The non-expert path still uses function constants.

### Important finding
For Laguna's scored execution, the non-expert `fp_gather_qmm_rhs_nax` path is **DORMANT** — all MoE gather uses the expert-aligned path (`expert_aligned = true` at `quantized.cpp:1659-1662`). The o_proj is INT8 affine (not NVFP4), so no non-gather NVFP4 matmul is dispatched. This means the STAGE_* function constants currently cause **zero compile cost** during scored execution.

However, converting them to `#define` injection would:
1. Eliminate the function constant declarations from `fp_quantized_nax.h` (simplifies the kernel)
2. Prevent accidental compile explosions if the non-expert path is ever used
3. Reduce the theoretical variant space from 2^8 = 256 to 2^4 = 16
4. Make the code consistent with the expert path's approach

### Bit-exactness
The `#define` injection produces the same kernel source as the function constant path when the values are fixed. The only difference is when specialization happens (compile time vs runtime). **Bit-exact.**

### Budget
- ~20-30 lines changed in `fp_quantized_nax.h` (replace `constant bool stage_widest [[function_constant(204)]]` with `#ifndef DARKBLOOM_STAGE_WIDEST\n#define DARKBLOOM_STAGE_WIDEST 0\n#endif` and replace `if (stage_widest)` with `#if DARKBLOOM_STAGE_WIDEST`)
- ~10 lines changed in `jit_kernels.cpp` (add `#define` injection for non-expert kernels, mirroring the expert path)
- Net: potentially negative (preprocessor guards are shorter than function constant declarations)

### M5 safety
No new compiles. If anything, it eliminates potential compiles. 100% safe.

### Why it matters even if dormant
The non-expert path could be activated by future changes (e.g., NVFP4 o_proj for tail layers via `DARKBLOOM_NATIVE_AFFINE_NVFP4_FROM`). Having the function constants pre-converted prevents a future compile-storm. It's defensive engineering that costs nothing.

---

## Idea 6: Down-Residual Kernel Reduction Occupancy Improvement ★★☆

**Path:** Decode (75%)
**Expected impact:** 0.05–0.2% decode (improve GPU utilization in MoE down kernel)
**Risk:** Medium

### Mechanism
The `lagunaRoutedSharedDownResidualKernel` (`LRM:3850`) uses 288 threads per threadgroup (9 simdgroups × 32 lanes). During the reduction phase (`LRM:3939-3959`), only 8 of 288 lanes are active — 280 lanes are idle after the barrier. The reduction computes a weighted sum of 8 expert outputs + shared expert + residual.

The idle lanes could be used to:
1. **Prefetch the next layer's QKV weight** — start loading the next layer's INT8 QKV weight bank while the reduction completes
2. **Compute the router GEMV** — the router weight (256×2048 BF16 = 1 MB) dot product with the normalized hidden state could begin on idle lanes, overlapping with the reduction
3. **Compute the input RMSNorm** for the next layer — the norm weight is tiny (2048 BF16 = 4 KB) and the reduction is over 2048 elements

### Bit-exactness
The reduction itself is unchanged — the idle lanes would perform INDEPENDENT work (prefetch or next-layer computation) that doesn't affect the current layer's output. The next-layer computation would produce the same values as the separate dispatch would. **Bit-exact if the computation is truly independent and doesn't create race conditions on the output buffer.**

### Budget
- ~200-500 bytes for the prefetch/compute logic added to the kernel
- Within LRM's 291KB headroom

### M5 safety
No new JIT compiles (modifies existing kernel source). The kernel already compiles. Adding idle-lane work doesn't change the compile count but increases register pressure — must verify the kernel doesn't spill.

### Risk
The main risk is register pressure. The down-residual kernel already uses significant registers for the 8-expert down projection. Adding prefetch or router computation may cause register spills that slow the kernel more than the overlap saves. **Test on M4 first for correctness, then M5 for timing.**

---

## Idea 7: KV Cache K/V Interleaving for Full-Attention Layers ★★☆

**Path:** Decode (75%)
**Expected impact:** 0.1–0.3% decode (halve KV memory transactions for 10/40 layers)
**Risk:** High (changes vendored KVCache.swift + SDPA kernel indexing)

### Mechanism
Full-attention layers (10/40) use `KVCacheSimple` which stores K and V as **separate** `[1, 8, seq, 128]` BF16 arrays. Each decode step:
1. `cache.update(keys, values)` does 2 separate slice-assigns (K write + V write) — 2 dispatches
2. The SDPA vector kernel reads K from one memory region and V from another — 2 separate memory transactions per KV position

Interleaving K and V into a single `[1, 8, seq, 256]` array (K row followed by V row per position) would:
- Combine the 2 cache writes into 1 (1 dispatch saved per full-attention layer per step)
- Let the SDPA kernel read 256 contiguous bytes per position instead of 2× 128-byte reads from different addresses (better TLB/cache locality)

### Bandwidth analysis
Full-attention KV at steady state: 10 layers × 8 heads × 640 positions × 128 × 2 bytes × 2 (K+V) = 25 MB/step. Interleaving doesn't reduce total bytes but improves memory transaction efficiency (1 transaction instead of 2 per position). The 10 saved dispatches (1 per full-attention layer) at ~1 μs each = 10 μs/step = ~0.2% of 5.4 ms step time.

### Bit-exactness
The K and V values are the same — only their memory layout changes. The kernel adjusts its stride computation: instead of `k_cache + head * (seq * 128) + pos * 128` and `v_cache + head * (seq * 128) + pos * 128`, it becomes `kv_cache + head * (seq * 256) + pos * 256` for K and `+ 128` for V within the same row. **Bit-exact if indexing is correct.**

### Budget
- `KVCache.swift`: ~50-100 lines to change `update()` to write interleaved rows and change `state` to return interleaved arrays
- `sdpa_vector.h`: ~20 lines to change K/V pointer computation
- LRM: ~10 lines to pass interleaved cache to the SDPA kernel
- The fused sliding kernel (`LRM:1063`) would also need updating if it reads from the same cache

### M5 safety
Changes to `sdpa_vector.h` require metallib rebuild (`tools/build-mlx-metallib.sh`). Changes to `KVCache.swift` are Swift-level (no JIT). The SDPA kernel change doesn't add compile count (modifies AOT kernel).

### Risk
HIGH. This touches the vendored KVCache.swift (shared infrastructure) and the AOT SDPA kernel. Any indexing error corrupts all attention. Must be tested with the upstream equivalence check. The sliding layers use a DIFFERENT cache type (`RotatingKVCache`) with a fused kernel that writes K/V inline — interleaving would require changing that fused kernel too.

### Why it's still worth considering
The 10 full-attention layers are the ONLY layers still on the stock path (sliding layers already have a fused kernel). The stock path's 2 separate K/V writes + 2 separate K/V reads per position is the clearest remaining inefficiency in the attention path.

---

## Idea 8: Prefill Gate-Softplus 4× Scale/Bias Dedup ★★☆

**Path:** Decode (75%)
**Expected impact:** 0.05–0.1% decode (reduce redundant scale/bias traffic)
**Risk:** Low

### Mechanism
The gate-softplus computation for attention uses per-head g_proj weights with group-32 INT8 affine quantization. The NVFP4 matmul subagent found that the gate-softplus path has 4× redundant scale/bias reads (~450 KiB/step). The decode path already deduplicates these via `simd_shuffle` (merged), but the PREFILL path (multi-token) may not have the same deduplication.

The prefill gate-softplus uses `lagunaCompiledSoftplusGate` (`LRM:2594`) which is a shapeless compiled function. The compiled graph may or may not deduplicate the scale/bias reads. If it doesn't, the prefill path reads the same scale/bias bytes 4× per step.

### Bit-exactness
The deduplication uses `simd_shuffle` to broadcast scale/bias values from one lane to all 4 lanes that share the same group. The values are identical — only the read pattern changes. **Bit-exact.**

### Budget
- If the prefill path needs the same `simd_shuffle` dedup: ~50-100 bytes in LRM
- If the compiled graph already handles it: 0 bytes

### M5 safety
No new JIT compiles. Modifies existing compiled function or adds a small kernel variant.

---

## Summary Ranking

| Rank | Idea | Path | Expected | Budget | M5 Build | M4 Test | Risk |
|------|------|------|----------|--------|----------|---------|------|
| 1 | **XMAJOR fold revival** (Idea 1) | Prefill 25% | 0.3–0.5% | ~5KB vendor | Safe | No (M5 only) | Med-high |
| 2 | **Compile budget → re-enable prefill QK-Norm+RoPE** (Idea 2) | Prefill 25% | 0.3–0.5% | ≤0 bytes | Improves | Yes | Low-med |
| 3 | **Full-attention fused decode kernel** (Idea 3) | Decode 75% | 0.3–0.7% | 0 bytes | Needs offset | No (M5) | Med |
| 4 | **LM-head pruner RMSNorm fusion** (Idea 4) | Decode 75% | 0.05–0.15% | ~300B | Safe | Yes | Med |
| 5 | **STAGE_* fc→#define conversion** (Idea 5) | Build | 0% (enabler) | Negative | Improves | N/A | Low |
| 6 | **Down-residual reduction occupancy** (Idea 6) | Decode 75% | 0.05–0.2% | ~300B | Safe | Yes | Med |
| 7 | **KV cache K/V interleaving** (Idea 7) | Decode 75% | 0.1–0.3% | ~100B+vendor | Safe | Yes | High |
| 8 | **Prefill gate-softplus dedup** (Idea 8) | Decode 75% | 0.05–0.1% | ~100B | Safe | Yes | Low |

## Recommended Strategy

**Phase 1 — M5 Build Fix + Compile Budget (Idea 5 → Idea 2):**
1. Convert STAGE_* function constants to `#define` injection (Idea 5) — defensive, zero-cost
2. Consolidate LM-head pruner kernels and/or compiled gate functions to free 2 JIT slots (Idea 2)
3. Re-enable prefill QK-norm+RoPE fusion with the freed compile budget

**Phase 2 — Prefill Bandwidth (Idea 1):**
4. Revive XMAJOR column-tile fold for prefill expert gather-QMM (Idea 1)
5. This is M5-only and needs careful testing, but the infrastructure is intact

**Phase 3 — Decode Dispatch Elimination (Ideas 3 + 4):**
6. Enable full-attention fused decode kernel with the compile budget from Phase 1 (Idea 3)
7. Fuse final RMSNorm into LM-head pruner coarse pass (Idea 4)

**Phase 4 — Micro-optimizations (Ideas 6, 7, 8):**
8. Down-residual reduction occupancy (Idea 6) — if register pressure allows
9. KV cache K/V interleaving (Idea 7) — high risk, defer
10. Prefill gate-softplus dedup (Idea 8) — quick win if prefill path lacks it

**Combined potential:** Ideas 1+2+3+4 together could yield 0.7–1.5% total score improvement, potentially closing and exceeding the 0.67% gap to 2.6063.

## What the Competitor (yudduy, 2.6063) Might Be Doing

The 0.67% gap is small. Likely differences:
1. **Cleaner M5 builds** — fewer JIT kernels means more optimizations can be enabled simultaneously
2. **Prefill QK-norm+RoPE enabled** — this was +1.5% prefill for us but disabled for M5 build
3. **XMAJOR fold** — the infrastructure was built and tested, suggesting it was valuable
4. **Scale halving working on M5** — we had it working but it caused compile-storm
5. **Full-attention fusion on M5** — they may have solved the compile budget problem

The key insight: our M5 build timeout is the BINDING CONSTRAINT. Most of our proven optimizations are disabled not because they don't work, but because they add JIT compiles that push us over the ~900s timeout. **Solving the compile budget problem (Ideas 2+5) unblocks the most impactful optimizations (Ideas 1+3).**
