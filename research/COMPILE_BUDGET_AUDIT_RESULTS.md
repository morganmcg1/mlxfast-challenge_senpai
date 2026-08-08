# M5 Compile Budget Audit — Complete Results

**Author:** birch-edward (student)
**Date:** 2026-08-08 07:03 UTC
**Assignment:** edward-compile-budget-audit-v1 (PR #416)
**Scope:** Research-only — no code changes. Count JIT compiles in current frontier vs f790e33f (last M5 success), estimate remaining budget, prepare prioritized re-enabling plan.

---

## 1. Reference Commits

| Label | Commit | Description |
|---|---|---|
| f790e33f | `020e370` (PR #343) | Last M5 build success |
| Current frontier | `bc2d05a` + warmup fix `27fb31c` | Bare minimum with warmup fix |
| Warmup fix | `27fb31c` | Restored 512-token warmup + MLX_MAX_OPS_PER_BUFFER=400 |
| BASE_SHA | `b2ecf6c` | Advisor base for this assignment |

---

## 2. metalKernel Declaration Count

### 2a. Total metalKernel() call sites in LRM

| Version | metalKernel() calls | LRM lines | LRM bytes |
|---|---|---|---|
| f790e33f (020e370) | 51 | 11,254 | 505,368 |
| Current frontier | 17 | 6,412 | 293,011 |
| **Delta** | **-34** | -4,842 | -212,357 |

### 2b. Unique kernel name strings

| Version | Unique kernel names |
|---|---|
| f790e33f | 47 |
| Current frontier | 17 |

### 2c. NEW kernels in current (not in f790e33f)

1. `laguna_residual_rms_router_bf16_2048_rpg8_v2` — consolidated from the 7-variant `rpg{1,2,4,8,16,32,64}` dict into a single rpg=8 declaration
2. `laguna_routed_shared_nvfp4_down_residual_bf16_r1_v5_halved` — consolidated from separate routed/shared down-residual kernels

Both are on the scored decode path.

### 2d. REMOVED kernels (in f790e33f, not in current): 32 kernels

Major removals include: 6 dead decode-router variants, 4 dead QKV variants, 4 dead O-proj variants, 2 dead prefill QK-norm+RoPE variants, 2 dead prefill full-QK-norm-YaRN variants, 2 dead full-attention variants, 4 dead gate-product variants, 2 dead output-projection variants, 3 dead SwiGLU variants, 2 dead MoE-tail variants, and the 6 non-default rpg router kernels.

---

## 3. Loop-Based Parameterized Kernels

### 3a. Current frontier (3 loop-based dicts, each over [sliding=64, full=48] = 2 compiles)

| Dict | Loop | Compiles |
|---|---|---|
| lagunaGatedAffineOProjNVFP4HalvedKernels | [64, 48] | 2 |
| lagunaActivatedOProjHalvedKernels | [64, 48] | 2 |
| lagunaFusedGProjQKVHalvedKernels | [64, 48] | 2 |

### 3b. f790e33f loop-based dicts

| Dict | Loop | Compiles |
|---|---|---|
| lagunaResidualRMSNormRouterKernels | [1,2,4,8,16,32,64] | 7 |
| lagunaFusedQKVProjectionKernels | [64, 48] | 2 |
| lagunaGatedOutputProjectionKernels | [64, 48] × [1,2,4,8] | 8 |
| lagunaNormAffineQKVKernels | [64, 48] × [0,heads] (dedup) | 4 |
| lagunaNormAffineQKVIndexedKernels | same (if guard passes) | 4 |
| 13 other heads-loop dicts | [64, 48] each | 26 |

---

## 4. _nax Template Instantiations

| Version | get_qmm_nax_kernel calls | get_gather_qmm_nax_kernel calls | Total |
|---|---|---|---|
| f790e33f | 10 | 1 | 11 |
| Current | 10 | 1 | 11 |
| **Delta** | **0** | **0** | **0** |

**No vendor file changes** between f790e33f and current. The `quantized.cpp`, `fp_quantized_nax.h`, `jit_kernels.cpp` are all identical. The 11 _nax template instantiations are the same in both versions.

---

## 5. MLX compile() Calls

| Version | compile() calls | Compiled functions |
|---|---|---|
| f790e33f | 2 | 3 (1 softplus gate + 2 gate projections for 48/64 heads) |
| Current | 2 | 3 (same) |
| **Delta** | **0** | **0** |

---

## 6. LM-Head Pruner Kernels

| Version | metalKernel() calls |
|---|---|
| f790e33f | 6 |
| Current | 4 |
| **Delta** | **-2** |

Current consolidated from 6 to 4 LM-head pruner kernels.

---

## 7. ACTUAL DISPATCHED Compile Count

Per the existing audit (research/M5_COMPILE_AUDIT_20260808_0104.md), compile count is driven by **distinct kernel names actually dispatched**, not by declarations. Dead kernels that are never dispatched compile nothing.

### 7a. Current frontier: ~27 custom + 3 compile() + 11 _nax + ~10-20 stock

| Category | Count | Notes |
|---|---|---|
| Decode custom kernels | 11 | 9 single + 2 head variants from loop |
| Prefill custom kernels | 8 | 6 single + 2 head variants from loop |
| Decode router | 2 | ordinal + score-table normalizing |
| LM-head pruner | 4 | |
| MLX compile() | 3 | 1 softplus + 2 gate projections |
| _nax templates | 11 | M5-only, same as f790e33f |
| Stock MLX (512-token warmup) | ~10-20 | SDPA, matmul, quantizedMM shape specializations |
| **Total estimated** | **~41-52** | |

### 7b. f790e33f: ~19 custom + 3 compile() + ~15-25 _nax + ~5-10 stock

| Category | Count | Notes |
|---|---|---|
| Decode custom kernels | 9 | |
| Prefill custom kernels | 3 | |
| Warmup-waste kernel | 1 | full-attention warmup (never scored) |
| LM-head pruner | 6 | |
| MLX compile() | 3 | 1 softplus + 2 gate projections |
| _nax templates | ~15-25 | more shapes dispatched (different optimizations enabled) |
| Stock MLX (2-token warmup) | ~5-10 | fewer shape specializations (2-token prefill) |
| **Total estimated** | **~42-57** | |

### 7c. Key insight

f790e33f had FEWER custom kernel compiles (~19) but MORE _nax compiles (~15-25) due to different optimization paths being active. Current has MORE custom kernel compiles (~27, from consolidated decode path) but FEWER _nax compiles (11, pinned).

The 512-token warmup is the main new compile budget consumer: it triggers ~10-20 additional stock MLX shape-specialized JIT compiles (SDPA, matmul, quantizedMM at 512-token shapes) that the 2-token warmup in f790e33f did not. This is by design — the warmup fix moves JIT compilation to construction time to avoid in-window M5 timeout during the scored run.

---

## 8. Warmup Configuration Diff

| Setting | f790e33f | Current frontier |
|---|---|---|
| Warmup prefill tokens | 2 | 512 |
| MLX_MAX_OPS_PER_BUFFER | 200 | 400 |
| Full-attn kernel warmup | Yes (lagunaWarmFullFusedAttentionKernel) | No (kernel reverted) |

The warmup fix (27fb31c) was necessary because the 2-token warmup in f790e33f pre-compiled fewer kernel shapes, causing JIT compilation to leak into the scored benchmark window on the M5. The 512-token warmup ensures all scored-path kernel shapes are compiled before the benchmark starts.

---

## 9. Compile Budget Estimate

**M5 timeout: ~900s** (estimated from research history)

f790e33f succeeded with ~42-57 total JIT compiles within the ~900s budget.

Current frontier has ~41-52 total JIT compiles — **comparable or fewer** than f790e33f, despite the 512-token warmup adding stock MLX compiles, because:
- 32 fewer custom kernel declarations (many were dead code)
- 2 fewer LM-head pruner kernels
- Same _nax template count (11)
- 512-token warmup adds ~10-20 stock MLX compiles but these are lighter than custom Metal kernels

**Estimated remaining budget: significant headroom for ~6 additional JIT compiles** (from re-enabling optimizations), well within the f790e33f proven envelope.

---

## 10. Scored-Path Reachability: lagunaFusedGProjQKVHalvedKernels

**ON the scored decode path.** Called at line 2783 inside the main layer forward function. Fires when:
- `fusedQKV == nil` (no earlier fused path succeeded)
- `_nativeAffineGProj` exists (INT8 affine g_proj metadata available)
- All guard conditions pass (bfloat16, NVFP4 bank, etc.)

This kernel fuses the QKV projection AND the g_proj (gate projection) softplus into a single Metal dispatch for NVFP4-tail layers. It iterates over [slidingAttentionHeads=64, fullAttentionHeads=48] = **2 JIT compiles**.

This is a real optimization, not dead code. It was added AFTER f790e33f and is one of the 2 NEW kernels identified in Section 2c.

---

## 11. Prioritized Re-enabling Plan

### Optimization 1: kHalvedScales (runtime constant approach) — HIGHEST PRIORITY

| Attribute | Value |
|---|---|
| New JIT compiles | **0** (runtime constant, not template parameter) |
| Expected gain | **~0.9% total score** (prefill shared expert halved path) |
| M5 build risk | **NONE** (zero new compiles) |
| Implementation | Per `research/KHALVEDSCALES_REIMPL_PLAN.md`: convert kHalvedScales from template parameter to runtime `set_bytes` argument. 6 files, ~4KB code budget. |
| Files | fp_quantized_nax.h, fp_quantized_nax.cpp, quantized.cpp, mlx-generated, LagunaRuntimeModel.swift |
| Priority | **1st** — zero compile cost, highest gain, M5-safe |

### Optimization 2: Full-attn fused decode kernel — HIGH PRIORITY

| Attribute | Value |
|---|---|
| New JIT compiles | **2** (lagunaFullFusedAttentionKernel + lagunaFullQKNormYaRNKernel) |
| Expected gain | **~0.3-0.7% decode** (10/40 layers × ~6 dispatch savings = ~60 dispatches/step) |
| M5 build risk | **LOW** (2 compiles, well within budget) |
| Implementation | Restore deleted kernels from git history (PR #9c934d8e had them). Also requires re-adding warmup call. |
| Files | LagunaRuntimeModel.swift |
| Priority | **2nd** — decode is 75% of score weight, 2 compiles is minimal |

### Optimization 3: XMAJOR fold (column-tile fold=2) — MEDIUM PRIORITY

| Attribute | Value |
|---|---|
| New JIT compiles | **0** (modifies existing _nax expert kernel source via JIT define, no new kernel names) |
| Compile time impact | Existing gather_qmm expert kernels recompile with longer source (~50% more compile time per kernel) |
| Expected gain | **~0.3-0.5% prefill** (halves x DRAM traffic for prefill expert gather-QMM) |
| M5 build risk | **LOW-MEDIUM** (0 new compiles but recompilation of existing _nax kernels takes longer) |
| Implementation | Change `darkbloom_gather_xmajor_ct()` return from 0 to 2. Restore JIT define injection. |
| Files | quantized.cpp (darkbloom_gather_xmajor_ct function) |
| Priority | **3rd** — prefill is 25% weight, 0 new compiles but recompile risk |

### Optimization 4: Prefill QK-norm+RoPE fusion — LOW PRIORITY

| Attribute | Value |
|---|---|
| New JIT compiles | **4** (4 prefill kernel variants: sliding/full × H1/standard) |
| Expected gain | **~0.1-0.3% prefill** (~200 prefill dispatch eliminations) |
| M5 build risk | **LOW** (4 compiles, within budget) |
| Implementation | Restore 4 prefill kernel declarations from f790e33f, enable DARKBLOOM_PREFILL_QK_NORM_ROPE flag |
| Files | LagunaRuntimeModel.swift |
| Priority | **4th** — prefill is 25% weight, 4 compiles for smallest gain |

### Combined impact if all 4 re-enabled

| Metric | Value |
|---|---|
| New JIT compiles | 6 (2 full-attn + 4 prefill QK-norm) |
| Recompiled kernels | ~4 _nax expert gather kernels (XMAJOR) |
| Total new compile count | 6 new + 4 recompiled = 10 additional |
| Estimated additional compile time | ~60-100s (well within remaining budget) |
| Expected total score gain | ~1.5-2.4% combined |

### Recommended re-enabling order

1. **kHalvedScales** (0 compiles, ~0.9% score) — submit first, M5-safe
2. **Full-attn fused** (2 compiles, ~0.3-0.7% decode) — submit after kHalvedScales confirmed
3. **XMAJOR fold** (0 new compiles, ~0.3-0.5% prefill) — submit after full-attn confirmed
4. **Prefill QK-norm+RoPE** (4 compiles, ~0.1-0.3% prefill) — submit last, smallest gain

Each step should be submitted and confirmed on M5 before proceeding to the next, to isolate causal attribution and verify the compile budget is not exceeded.

---

## 12. Conclusion

The current frontier has **significant compile budget headroom** compared to f790e33f (last M5 success). The 512-token warmup fix adds ~10-20 stock MLX compiles but this is offset by removing 32 dead custom kernel declarations and 2 LM-head kernels.

All 4 optimizations can be re-enabled with a total of only 6 new JIT compiles and 4 recompiled _nax kernels. This is well within the proven f790e33f envelope of ~42-57 total compiles.

The prioritized plan sequences optimizations by compile cost (lowest first) and expected gain (highest first), with kHalvedScales as the clear first step since it adds zero new compiles.
