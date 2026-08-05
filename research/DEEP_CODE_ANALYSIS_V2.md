# Deep Code Analysis V2 — Laguna XS 2.1 NVFP4 Kernel Optimization

**Date:** 2026-08-05
**Analyst:** Senior GPU kernel optimization researcher (delegated subagent)
**Base commit:** bb52380 (score ~2.455, 126 public promotions)
**Target hardware:** M5 Max 128 GB, Apple GPU gen 17, 40-core GPU, 614 GB/s unified memory
**Score formula:** `decode_speedup^0.75 * prefill_speedup^0.25`, both floors 0.95
**Scored file:** `Sources/MLXFastModel/LagunaRuntimeModel.swift` (11,329 lines)

---

## Architecture Summary (from code + config)

| Parameter | Value | Source |
|---|---|---|
| Hidden size | 2048 | `LagunaConfig.swift:17` |
| Layers | 40 | `LagunaConfig.swift:20` |
| KV heads | 8 | `LagunaConfig.swift:21` |
| Head dim | 128 | `LagunaConfig.swift:22` |
| Full-attention heads | 48 (layers 0,4,8,...,36) | `LagunaConfig.swift:24` |
| Sliding-attention heads | 64 (other 30 layers) | `LagunaConfig.swift:26` |
| Sliding window | 512 | `LagunaConfig.swift:29` |
| Experts | 256, top-8 | `LagunaConfig.swift:30-31` |
| Expert intermediate | 512 | `LagunaConfig.swift:32` |
| Dense intermediate (layer 0) | 8192 | `LagunaConfig.swift:19` |
| MoE routed scaling | 2.5 | `LagunaConfig.swift:34` |
| Layer 0 | Dense BF16 MLP | `docs/laguna-weight-contract.md:104` |
| Layers 1–39 | NVFP4 MoE (256 routed + 1 shared) | `docs/laguna-weight-contract.md:109` |

**Decode dispatch anatomy (all flags ON, per step):**
- Per attention layer (×40): norm+QKV (1), fused attention (1), gated o_proj (1) = 3
- Per sparse MoE layer (×39): residual+rmsnorm+router (1), router top8 (1), routed SwiGLU QMV (1), shared SwiGLU QMV (1), routed+shared down+residual (1) = 5
- Layer 0 dense: ~3
- Final norm + LM head: 2
- **Total: ~280 dispatches/step**

**Weight traffic per decode step (estimated):**
- Attention (INT8 affine QKV+o): ~10 MB × 40 ≈ 400 MB
- MoE gate/up (NVFP4): ~5.5 MB/expert × 9 × 39 ≈ 2.0 GB
- MoE down (NVFP4): ~1.4 MB/expert × 9 × 39 ≈ 504 MB
- LM head (pruned): ~52 MB
- **Total ≈ 3.1 GB → theoretical floor ~5.0 ms at 614 GB/s**

**Critical constraint:** The Poolside v2 weight contract (`docs/laguna-weight-contract.md:131-134`, `Transform.swift:256-269`) **forbids derived layouts and metadata sidecars in the transform**. The runtime loads exactly the 912 indexed checkpoint tensors. Any weight layout change must be a **runtime side copy** (like the existing `DARKBLOOM_PACKED_SCALES` bank at L10151), not a transform-side change. The side copy adds resident memory but is built once during `prepareFusedRuntimeWeights()` (L274), outside the scored window.

---

## Area A: Attention Kernel Threadgroup Geometry

### Current State

**Sliding attention** (`lagunaSlidingFusedAttentionKernel`, L1369):
- Grid: `((heads / 2) * 1024, 1, 1)` = `((64/2) * 1024, 1, 1)` = `(32 * 1024, 1, 1)` = **32,768 threadgroups** (L1788)
- ThreadGroup: `(1024, 1, 1)` = 1024 threads/TG (L1789)
- Each TG handles 2 query heads (a GQA pair) → 32 pairs for 64 heads
- 1024 threads = 32 simdgroups (32 lanes each); 4 simdgroups used for Phase 1 (RMSNorm+RoPE), 32 for Phase 3 (SDPA)

**Full attention** (`lagunaFullFusedAttentionKernel`, L1845):
- Grid: `((heads / 2) * 1024, 1, 1)` = `((48/2) * 1024, 1, 1)` = `(24 * 1024, 1, 1)` = **24,576 threadgroups** (L2304)
- ThreadGroup: `(1024, 1, 1)` (L2305)
- Each TG handles 2 query heads → 24 pairs for 48 heads
- GQA ratio = 6 (48 Q heads / 8 KV heads)
- Phase 1: 4 simdgroups (sg 0-2: q0/q1/k norm+RoPE, sg 3: v copy)
- Phase 3: SDPA over N cached positions (runtime, grows each step)

**The `* 1024` factor**: The grid multiplies heads/2 by 1024 because the SDPA inner loop (Phase 3) splits the K/V dimension reduction across 1024 threadgroups per head-pair. Each TG covers `BN=32` consecutive K positions (L1381-1382), so `1024 TGs × 32 positions = 32,768` — but the actual window is only 512. Looking more carefully at the code: the SDPA loop iterates `i = sg; i + BN < N; i += 2*BN` where `BN=32` and `N=512` (L1513). So only 8 iterations × 2 planes = the loop runs 8 times, each TG processes its own slice. **Wait — re-examining**: the grid `*1024` means 1024 TGs per head-pair, but only `N/2/BN = 512/64 = 8` iterations are needed. The 1024 factor appears to be a threadgroup count that's much larger than the number of K-positions — this suggests the grid is **not** splitting K-positions across TGs but rather each TG independently computes the full SDPA for its head-pair.

**Re-reading the kernel carefully:** The SDPA loop (L1512-1609) runs entirely within one TG using `sg` (simdgroup index) as the starting offset. Each of the 32 simdgroups processes a different slice of the 512 K positions. The two-deep pipeline processes `2*BN = 64` positions per iteration, and 512/64 = 8 iterations. After the loop, there's a cross-simdgroup reduction (L1611+) that combines all 32 partial results. So **each TG computes the full attention for one head-pair independently** — the `1024` grid factor is NOT used for work distribution; it's a **redundant dispatch of 1024 identical computations per head-pair**.

**Actually, no** — let me re-examine the grid. Looking at the output shape and how the result is used (L5953, L5979): the output is `[1, 1, heads * head_dim]` = a single row. Only one TG per head-pair should write the result. The `1024` factor seems like it could be a legacy artifact or the grid is configured so only TG 0 per head-pair writes. Let me check the output write logic...

Looking at the combine epilogue (L1611+): it writes to `outputs[...]`, `max_scores[...]`, `sum_exp_scores[...]` — all threadgroup-local. Then the final output write must happen after the cross-simdgroup reduce. If only one TG per head-pair actually writes the output, then 1023/1024 of the TGs are wasted compute. **This would be a massive optimization opportunity** — but I need to verify this.

**After deeper analysis**: The grid `(heads/2 * 1024, 1, 1)` with TG `(1024, 1, 1)` means each of the 1024 TGs per head-pair runs the full SDPA independently. The kernel does NOT guard the output write with `if (pair_tg % 1024 == 0)` — all 1024 TGs write to the same output address. **This is either (a) a correctness bug that doesn't manifest because the writes are identical (race condition with same data), or (b) the `1024` is actually 1 in practice**. Given the model has been through 126 promotions with correctness gates, it's likely (b) — the grid factor is 1, not 1024.

Let me verify by checking the actual call:

```swift
// L1788
grid: ((heads / 2) * 1024, 1, 1),
```

`heads` for sliding = 64, so `(64/2) * 1024 = 32768`. For full = 48, so `(48/2) * 1024 = 24576`. These are definitely 1024 TGs per head-pair. But the kernel uses `pair_tg = threadgroup_position_in_grid.x` (L1390) to select the head-pair, and `head0 = pair_tg * 2` — so TG 0 and TG 1 would both try to process head-pair 0 (head0=0, head1=1). **This means all 1024 TGs process the same head-pair** and all write the same output. The writes race but produce identical values, so it's "correct" by coincidence. **This is a 1024× over-dispatch of the SDPA computation.**

### Assessment

**Optimization potential: HIGH**

If the `* 1024` grid factor is truly redundant (all TGs compute the same head-pair), changing it to `* 1` would reduce the SDPA dispatch from 32,768 TGs to 32 TGs (sliding) and 24,576 to 24 TGs (full). This is a **1000× reduction in compute** for the attention SDPA phase, though the kernel also includes RMSNorm+RoPE+KV-write which may need all TGs... but no — the RMSNorm/RoPE is also per head-pair, done once per TG. The KV write (L1461-1472) is guarded on `(head0 % gqa) == 0` so only one TG per KV head writes — meaning 1023 of 1024 TGs redundantly skip it. **The entire kernel is 1024× redundant.**

### Specific Code Changes

1. **Change grid from `(heads/2 * 1024, 1, 1)` to `(heads/2, 1, 1)`** at:
   - L1788 (sliding): `grid: ((heads / 2) * 1024, 1, 1)` → `grid: (heads / 2, 1, 1)`
   - L2304 (full): `grid: ((heads / 2) * 1024, 1, 1)` → `grid: (heads / 2, 1, 1)`

2. **Verify the SDPA reduction still works**: With only `heads/2` TGs, each TG has 1024 threads = 32 simdgroups. The SDPA loop uses `sg` as the starting offset and iterates with stride `2*BN = 64`. With 32 simdgroups and BN=32, the loop covers `32 * 2 * 32 = 2048` positions per iteration set — but N=512. The loop condition `i + BN < N` means the loop runs while `i < 512 - 32 = 480`, starting at `sg` with step `2*BN=64`. Simdgroups 0-7 participate (sg=0..7, i starts at 0..7, step 64, so i=0,64,128,...448 — 8 iterations). Simdgroups 8-31 have `i = 8..31` which exceeds 480 immediately, so they skip the loop. **The reduction combines all 32 simdgroups' partial results** — so with 32 TGs, only 8 simdgroups do real work and 24 are idle during SDPA. With 1024 TGs, ALL simdgroups across ALL TGs repeat the same 8-simdgroup computation. The grid reduction is safe.

3. **ThreadGroup size**: Could reduce from 1024 to 512 or 256 threads to improve occupancy, but this requires restructuring the SDPA loop to use fewer simdgroups. This is higher complexity.

### Risk

- **Correctness: MEDIUM-HIGH**. The current 1024× dispatch is a race-write-the-same-value pattern. Reducing to 1× must produce the identical output. The SDPA reduction uses `simd_sum` within each TG independently, so removing redundant TGs doesn't change the arithmetic. However, the exactness gate must pass. **Must run `LagunaUpstreamEquivalence.swift`**.
- **Complexity: LOW**. One-line grid change per kernel.
- **Budget: NEGLIGIBLE**. No byte growth.
- **M4-testable: YES**. The grid geometry change affects both M4 and M5 identically. No `_nax` involvement.

### Critical Caveat

**I may be wrong about the 1024× redundancy.** The grid `* 1024` might serve a purpose I'm not seeing — perhaps the MLX kernel dispatch system uses threadgroup index differently than standard Metal, or the `ensureRowContiguous` mechanism does something with the grid. The code has been through 126 promotions and extensive correctness testing. If the 1024 factor were truly redundant, it's unlikely to have survived. **More likely interpretation**: the kernel is designed so that each of the 1024 TGs per head-pair computes a partial result, and the cross-TG reduction is done by MLX's output accumulation mechanism. But the kernel source doesn't show cross-TG communication (no `device` atomics, no grid-level barriers). **This needs empirical verification**: run with `DARKBLOOM_TRACE_FUSION=1` and observe whether changing the grid factor breaks correctness.

**Alternative hypothesis**: The `1024` might be the number of output elements per head-pair (2 heads × 128 head_dim = 256, not 1024) or a thread count parameter. Looking at the SDPA reduction: `outputs[4 * BN * BD]` = `4 * 32 * 32 = 4096` floats in threadgroup memory. `max_scores[2 * BN]` = 64. `sum_exp_scores[2 * BN]` = 64. These are per-TG, not per-grid. The final output write (after the combine epilogue, around L1680+) writes `attended[head0 * head_dim + ...]` and `attended[head1 * head_dim + ...]`. If all 1024 TGs write the same output location, it's a race — but Metal's race-with-same-value is technically undefined behavior that happens to work on Apple Silicon. **This is fragile but currently works.**

### Recommendation

**Test this FIRST with a minimal change**: change the grid to `(heads/2, 1, 1)` and run the correctness gate. If it passes, this is a massive win. If it fails, the 1024 factor serves a purpose and should be investigated further.

---

## Area B: KV Cache Movement in Sliding Layers — Incremental Attention

### Current State

Sliding layers (30 of 40) use `RotatingKVCache(maxSize: 512, keep: 0)` (L261). During decode:
- The fused attention kernel reads ALL 512 cached K/V positions every step (L1512-1609)
- Each K position is `head_dim=128` BF16 = 256 bytes per head
- Per KV head per step: 512 positions × 256 bytes × 2 (K+V) = 262 KB
- Per layer: 8 KV heads × 262 KB = 2.1 MB
- 30 sliding layers: 62.7 MB per decode step just for KV cache reads

The KV cache for sliding layers is relatively small compared to weight traffic (2.0 GB for MoE). KV cache reads are ~2% of total weight traffic. **This is a minor contributor.**

### Incremental Attention Proposal

The idea: cache the running softmax denominator and weighted value sum, and only compute the attention score for the NEW position each step. This would reduce the 512-position SDPA loop to a 1-position update.

**Mathematical feasibility**: Online softmax (FlashAttention's incremental formulation) maintains `(max_score, sum_exp, weighted_value_sum)`. When a new position arrives:
1. Compute new score `s_new = q · k_new * scale`
2. Update: `new_max = max(old_max, s_new)`, `factor = exp(old_max - new_max)`, `sum = sum * factor + exp(s_new - new_max)`, `output = output * factor + exp(s_new - new_max) * v_new`

**This is EXACTLY the FlashAttention online softmax update** — and the kernel already implements it per-iteration in the loop (L1561-1605). The issue is that it recomputes scores for ALL 512 positions every step, not just the new one.

**Why it can't be done directly**: The RotatingKVCache overwrites old positions in a ring buffer. Position `widx` (L1396) is the new write slot. The 512 positions in the ring are the 512 most recent tokens. At step T, positions `[T-511, T]` are in the cache. At step T+1, position T-511 is evicted and position T+1 is added. The set of 512 positions CHANGES — the old position T-511 is removed. **This means the cached softmax state from step T is invalid at step T+1** because position T-511 is gone. You can't just add the new position; you must subtract the evicted one too.

**Subtractive update**: Maintaining `(max, sum, output)` across eviction requires:
1. `output -= exp(s_evicted - max) * v_evicted` (if s_evicted was part of the sum)
2. `sum -= exp(s_evicted - max)`
3. But if `s_evicted == max`, the rescaling changes — you'd need the second-highest score, requiring a full re-scan.

**This breaks the online softmax invariant**: there's no efficient way to remove a position from the cached softmax state without re-scanning all remaining positions. This is a known limitation of incremental attention with sliding windows.

### Assessment

**Optimization potential: LOW**

The subtractive update is mathematically intractable without a full re-scan (to find the new max after eviction). The KV cache traffic is only ~2% of total weight traffic. The compute saved (512 dot products per head-pair per layer) is small compared to the MoE weight reads.

**Alternative: cache partial scores**: Precompute and store `q · k_i * scale` for all positions in a separate buffer. Each step, only compute the new score and reuse cached scores. But `q` changes every step (it depends on the new token's hidden state), so all cached scores are invalid. **The query is fresh every step — there's nothing to cache.**

### Risk

- **Correctness: HIGH**. The subtractive update is numerically unstable (max eviction requires re-scan). Even if implemented, FP32 rounding in subtractive updates would diverge from the full re-computation.
- **Complexity: HIGH**. Requires a new kernel, a persistent score buffer, and careful eviction logic.
- **Budget: MEDIUM**. New kernel source adds ~2-4 KB.
- **M4-testable: Partially**. The logic is architecture-independent, but near-tie argmax may differ.

### Recommendation

**Do not pursue**. The mathematical intractability of subtractive softmax with eviction, combined with the small traffic contribution (~2%), makes this the lowest-value area.

---

## Area C: MoE Router/Gate Dispatch Fusion

### Current State

Per sparse MoE layer decode (39 layers), the dispatch sequence is:

1. **`lagunaResidualRMSNormRouter`** (L10597, kernel at L839): fused residual add + RMSNorm + `[256, 2048]` BF16 GEMV producing router logits. Grid: `(tiles * 512, 1, 1)` where `tiles = 256/rowsPerGroup`. ThreadGroup: 512. This kernel is ALREADY a fusion of norm + router projection. It outputs `(summed, normalized, routerLogits, routerKeys?)`.

2. **`lagunaDecodeRouterTop8`** (L8703): bitonic top-8 selection over 256 expert logits. Grid: `(1, 1, 1)`, ThreadGroup: 256. Single TG, 256 threads = 8 simdgroups. Runs the full 36-stage bitonic sort network. This is a **separate dispatch** that consumes `routerLogits` from step 1.

3. **`lagunaRoutedSwiGLUQMVPackedTop8`** (L10272): 8-expert NVFP4 gate/up QMV + SwiGLU. Grid: `(8 * tiles, 1, 1)`. Uses precomputed router keys when `DARKBLOOM_ROUTER_PRECOMPUTED_KEYS` is ON (L157, default ON) — this means the top-8 selection is **already embedded into the QMV kernel** via the `top8_winner` mechanism (L7512). When this flag is ON, the separate top-8 dispatch (step 2) is **bypassed** — the QMV kernel reads `routerKeys` directly and extracts the top-8 internally.

4. **`lagunaSharedSwiGLUQMV`** (L6689): shared expert gate/up QMV. Separate dispatch. **This is the gap identified in `MERGE_GATEUP_PLAN.md`** — `mergedSharedActivated` (L10248) is declared but never assigned.

5. **`lagunaRoutedSharedDownResidual`** (L7851): fused 8 routed + 1 shared down projection + residual add. Already merged.

### Assessment

**Optimization potential: MEDIUM-HIGH** for merging shared into routed gate/up dispatch.

The router top-8 selection is ALREADY fused into the QMV kernel (step 3) when `DARKBLOOM_ROUTER_PRECOMPUTED_KEYS=1` (default). The remaining fusion opportunity is:

**C1. Merge shared gate/up QMV into routed gate/up dispatch** (eliminates 39 dispatches):
- The shared expert has the same weight geometry as a routed expert (`sharedExpertIntermediateSize == moeIntermediateSize == 512`, L13 of MERGE_GATEUP_PLAN).
- The code at L10248 declares `mergedSharedActivated: MLXArray?` but never assigns it. The comment says "Set when the routed and shared gate/up QMVs were issued as one dispatch" — **this is explicitly designed for but unimplemented**.
- The down+residual kernel (L7851) already accepts `shared_activated` as a separate input, so the interface is ready.
- **Risk: LOW**. Each expert's gate/up is independent; the merge only changes which TG computes which rows. Bit-exact.
- **Implementation**: extend routed QMV from 8 to 9 slots (slot 8 = shared), pass shared weight/scales as additional inputs, write shared activation to slot 8 output.
- **M4-testable: YES**. No `_nax` involvement.

**C2. Fuse router top-8 into the norm+router kernel** (eliminates 39 dispatches when precomputed keys are OFF):
- When `DARKBLOOM_ROUTER_PRECOMPUTED_KEYS=0`, a separate top-8 dispatch runs. But the default is ON, so this dispatch is already eliminated in the default path. **Low value** — only helps the fallback path.
- When ON, the top-8 selection happens inside the QMV kernel via the `top8_winner` expression. This is already optimal.

**C3. Merge router+norm into QKV** (the norm+router kernel already fuses norm+router; QKV is a separate dispatch). This would merge the attention's QKV projection into the MoE's norm+router. But these are on different layers — attention comes before MLP. **Not applicable** — the norm+router kernel is for the MLP block, which follows attention.

### Specific Code Changes (for C1)

1. **Extend `lagunaRoutedSwiGLUQMVPackedTop8R1Kernel`** (L7529) to accept shared weight/scales as additional inputs:
   - Add `inputNames: [..., "shared_weight", "shared_scales"]`
   - Change `routed_experts` from 8 to 9
   - In the kernel, if `expert_slot == 8`, read from `shared_weight`/`shared_scales` instead of `fused_weight`/`fused_scales`

2. **Extend the grid** from `8 * tiles` to `9 * tiles` (L7529 call site)

3. **Set `mergedSharedActivated`** (L10248) from the slot-8 output of the merged dispatch

4. **Pass the shared activation** to the down+residual kernel via `sharedExpert.fusedSharedDownInputs(x, sharedActivation: mergedSharedActivated)` (L10322-10323)

### Risk (for C1)

- **Correctness: LOW**. Each expert's computation is independent. The merge only changes dispatch grouping, not arithmetic per row.
- **Complexity: MEDIUM**. Kernel source modification + call site changes.
- **Budget: LOW**. ~500 bytes of new kernel code.
- **M4-testable: YES**. NVFP4 QMV is not `_nax`-specific.

### Recommendation

**C1 is the highest-value, lowest-risk optimization in this analysis.** It eliminates 39 dispatches (~14% of total) with zero correctness risk. The infrastructure (`mergedSharedActivated`, fused down+residual) already exists. This is filling an explicitly designed-but-unimplemented gap.

---

## Area D: Weight Layout for NVFP4 Decode

### Current State

NVFP4 weights stored as:
- **Codes**: `uint32` (4 bytes per 8 elements = 4 bits/element). Stored shape `[experts, 512, 256]` for gate/up (256 = 2048/8), `[experts, 2048, 64]` for down (64 = 512/8).
- **Scales**: `uint8` (E4M3 format, 1 byte per 16 elements). Stored shape `[experts, 512, 128]` for gate/up, `[experts, 2048, 32]` for down.
- Group size = 16 (every 16 elements shares one E4M3 scale).

The `DARKBLOOM_PACKED_SCALES` feature (L138-152, default ON) already implements a scale-interleaved side copy for the **routed** gate/up bank (L10151-10189). The packed bank stores scales in the kernel's exact walk order `[tile 128][k-block 4][row-pair sub 8][32 B]`, reducing memory transactions by co-locating scales with the code access pattern. This is already the "ARCQuant-style" interleave mentioned in the task — **it's already implemented**.

### Assessment

**D1. Scale interleaving (ARCQuant-style)**: **Already implemented** via `DARKBLOOM_PACKED_SCALES` for routed gate/up. Could be extended to:
- **Shared expert gate/up**: Currently uses separate `lagunaSharedSwiGLUQMV` (L6689) which reads codes and scales from two separate tensors. A packed-scales variant for the shared expert would reduce its 4 device streams to 2 (codes + packed scales). **Optimization potential: LOW-MEDIUM** — the shared expert is 1/9 of the MoE traffic.
- **Routed/shared down projection**: The `lagunaRoutedSharedDownResidual` kernel (L7851) reads down weights + scales separately. A packed-scales variant for down would reduce memory transactions. **Optimization potential: MEDIUM** — down traffic is ~504 MB/step.

**D2. Weight transposition for coalescing**: The decode GEMV reads weights row-by-row (each threadgroup computes a few output rows, iterating over the K dimension). The current layout is `[out_rows, k_packed]` — row-major, which is optimal for GEMV (each thread reads a contiguous slice of one weight row). Transposing to `[k_packed, out_rows]` would make the K-dimension contiguous but break row access. **This would HURT GEMV performance** — GEMV is row-major by definition. **Optimization potential: NONE**.

**D3. Code+scale interleaving**: Instead of separate code and scale tensors, interleave scales inline with codes (e.g., after every 16 codes, store the scale byte). This eliminates one device stream entirely. The `DARKBLOOM_PACKED_SCALES` bank reorders scales to match the code walk order but keeps them in a separate tensor. True interleaving (scale bytes inline with code bytes) would:
- Reduce from 2 device streams to 1
- But misalign the 4-byte `uint32` code reads (codes are 4-byte aligned, adding 1-byte scales breaks alignment)
- Require repacking codes into a new format that the kernel can read efficiently
- **Optimization potential: LOW-MEDIUM** but **complexity HIGH** and **risk MEDIUM** (format change must be bit-exact).

**D4. NVFP4 scale deferral (`DARKBLOOM_NVFP4_SCALE_DEFER`)**: Already implemented (L6355-6507). Scales are deferred and absorbed into a `2^14` factor, reducing per-element scale multiplications. This is already in the baseline.

### Specific Code Changes (for D1 — shared down packed scales)

1. **Build a packed-scales side bank for routed down weights** in `prepareFusedRuntimeWeights()`:
   - For each expert's down projection `[2048, 64]` codes + `[2048, 32]` scales
   - Reorder scales to match the down kernel's walk order
   - Store as a side copy (~16 MB per sparse layer for 256 experts)

2. **Modify `lagunaRoutedSharedDownResidual`** (L7851) to accept the packed down scales bank instead of separate codes + scales

3. **Add a new `preparePackedRoutedDownBank`** method similar to `preparePackedRoutedGateUpBank` (L10151)

### Risk (for D1)

- **Correctness: MEDIUM**. Scale reordering must be bit-exact. The existing packed-scales bank for gate/up proves this is feasible.
- **Complexity: MEDIUM**. Similar to the existing gate/up packed-scales implementation.
- **Budget: MEDIUM**. ~2-4 KB of new Swift code + ~16 MB resident memory per sparse layer (39 layers × 16 MB = 624 MB additional resident memory). The model is ~21.6 GB, so +624 MB is ~3% growth. Must verify against the 3,000,000 byte editable budget (source only, not runtime memory).
- **M4-testable: YES**. No `_nax` involvement.

### Recommendation

**D1 for shared down is worth pursuing** as a follow-up to C1. The packed-scales pattern is proven for gate/up; extending to down is mechanical. However, the memory growth (624 MB) must be verified against the M5's 128 GB capacity (21.6 GB model + 624 MB side copies = 22.2 GB, well within limits). The source budget impact is small (~2 KB).

---

## Area E: Command Buffer Encoding Overhead

### Current State

With ~280 dispatches per decode step, CPU-side command buffer encoding is a real cost. The codebase already implements several mechanisms:

1. **`asyncEval` scheduling** (L625-698): The `DARKBLOOM_DECODE_ASYNC_STAGE` system enqueues already-constructed work earlier via `asyncEval()`, overlapping GPU execution with CPU graph construction. The default `at:0,1,7,15,23,31,39` schedule fires at 7 boundaries per step. This is already extensively tuned (L646-662: 66-run Latin square sweep, ladder schedules compared).

2. **`MLX.compile()`** (L5363, L5385): The gate projection (softplus + gate product + o_proj) is compiled via `compile(body)` when `MLXHardwareInfo.isCompiledDecodeSupported`. This reduces frontend overhead for the attention gate path.

3. **`compile(shapeless: true, body)`** (L5363): The softplus gate is compiled shapeless for prefill.

4. **Fused custom kernels**: The bulk of dispatches use `MLXFast.metalKernel` (custom Metal kernels) which bypass MLX's graph builder entirely — each dispatch is a direct Metal command buffer encode, not a graph operation. **This means most dispatches already have minimal frontend overhead** — the cost is Metal command encoding, not MLX graph construction.

5. **Compiled decode segments** (PR #49, assigned): Making KV cache ring position graph-visible to enable `MLX.compile()` on multi-layer decode segments. This would eliminate ~230µs/step CPU/FFI overhead. **Already assigned to student birch-edward**.

### Assessment

**Optimization potential: LOW (most already done or assigned)**

The codebase has already aggressively attacked encoding overhead:
- Custom Metal kernels eliminate graph construction for 90%+ of dispatches
- `asyncEval` overlap is tuned via 66-run sweep
- `compile()` is used where applicable
- The remaining overhead (PR #49) is already assigned

**Remaining unaddressed opportunity**:
- **Persistent command buffers**: Metal supports `MTLCommandBuffer` reuse via `MTLCommandBufferEncoder` with retained encoder state. MLX does not expose this. The `MLXFast.metalKernel` dispatch path creates a new encoder per call. There's no MLX-level mechanism to reuse encoders. **Not actionable without MLX framework changes** (which would require editing vendored `mlx-swift` Metal dispatch code — this IS in the editable surface per `benchmark.json` lines 26-105).

- **Batch-encoding dispatches**: Multiple `metalKernel` calls could share a single command buffer if they have no data dependencies. But MLX's `eval()` / `asyncEval()` already manages command buffer boundaries. The `asyncEval` ladder already exposes independent work to the GPU as early as possible.

**Potential MLX dispatch optimization** (in vendored code):
- `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/jit_kernels.cpp` (editable) contains the JIT kernel dispatch machinery. If the dispatch path could batch-encode multiple custom kernels into one command buffer, it would reduce per-dispatch encoding overhead. But this is a deep MLX framework change with HIGH complexity and MEDIUM-HIGH correctness risk.

### Risk

- **Correctness: HIGH** for any MLX dispatch internals change.
- **Complexity: HIGH**. Requires deep understanding of MLX's Metal backend.
- **Budget: VARIABLE**. Depends on the change.
- **M4-testable: YES** for dispatch timing, but `_nax` kernel selection differences mean M4 can't validate ranked-specific paths.

### Recommendation

**Do not pursue independently.** PR #49 (compiled decode segments) already targets the primary encoding overhead. Wait for its results. The MLX framework dispatch internals are too risky for the expected gain.

---

## Area F: Layer 0 Dense MLP

### Current State

Layer 0 has a BF16 dense MLP (not MoE, not NVFP4):
- `gate_proj`: `[8192, 2048]` BF16 = 32 MB
- `up_proj`: `[8192, 2048]` BF16 = 32 MB
- `down_proj`: `[2048, 8192]` BF16 = 32 MB
- Total: 96 MB per decode step (only 1 layer)

The code already implements two fusions:

**F1. Fused gate+up+SwiGLU** (`lagunaDenseGateUpSwiGLU`, L8128):
- Fused weight: `concat([gate_proj, up_proj], axis=0)` = `[16384, 2048]` BF16 = 64 MB
- Kernel: `laguna_dense_gate_up_swiglu_bf16_v1` (L8149 source)
- Grid: `((8192/64) * 512, 1, 1)` = `(128 * 512, 1, 1)` = 65,536 TGs
- ThreadGroup: 512 threads = 16 simdgroups
- Each TG computes 4 output rows (rows_per_group=16, rows_per_thread=4, 4 rows per simdgroup, 16 simdgroups = 64 rows... wait, let me re-check)
- `rows_per_group = 16`, `rows_per_thread = 4`, `blocks_per_thread = 16` (8192/512). Each simdgroup computes `rows_per_thread = 4` rows, 16 simdgroups = 64 rows per TG. `8192/64 = 128` tiles. Grid = `128 * 512 = 65,536` — **this has the same `* 512` over-dispatch pattern as the attention kernels!**

**Wait — same pattern as Area A?** The grid is `((8192/64) * 512, 1, 1)` = 128 tiles × 512 = 65,536 TGs. But there are only 8192 output rows / 64 rows per TG = 128 tiles needed. The `* 512` factor means 512 TGs per tile — **512× over-dispatch**.

**Re-examining the dense down kernel** (`lagunaDenseDownResidual`, L8149):
- Grid: `((2048/16) * 128, 1, 1)` = `(128 * 128, 1, 1)` = 16,384 TGs
- ThreadGroup: 128 threads = 4 simdgroups
- `rows_per_group = 16`, `rows_per_thread = 4`, 4 simdgroups = 16 rows per TG. `2048/16 = 128` tiles needed. Grid = `128 * 128 = 16,384` — **128× over-dispatch**.

**F2. Fused down+residual** (`lagunaDenseDownResidual`, L8208):
- The kernel reads the SwiGLU activation and down weight, computes down projection, adds residual
- Same grid over-dispatch as above

### Assessment

**Optimization potential: HIGH (same over-dispatch as Area A)**

If the `* 512` and `* 128` grid factors are redundant (all TGs per tile compute the same rows and race-write the same output), reducing them to `* 1` would eliminate:
- Gate/up: 65,536 → 128 TGs (512× reduction)
- Down: 16,384 → 128 TGs (128× reduction)

**However**, same caveat as Area A: this may be intentional or the MLX kernel dispatch may handle grid differently. The 128× / 512× over-dispatch would be a massive waste of compute that should have been caught in 126 promotions — unless the extra TGs are needed for occupancy (filling the GPU's 40 cores with enough work) or the `* 512` is a thread count, not a TG count.

**Re-reading the gate/up kernel** (L8029-8124): The kernel uses `tile = threadgroup_position_in_grid.x` to select the row block. If there are 65,536 TGs and only 128 tiles, then TGs 0-511 all compute tile 0's rows and write the same output. The output write (L8119): `activated[row_base + row]` — no guard on tile index. **All 512 TGs per tile write the same output** — same race-write-same-value pattern.

**But wait — the dense kernel has `rows_per_group = 16` and `blocks_per_thread = 16`**. The block loop (L8102+) iterates `block = 0..16`, each block reads `block_width = 128` columns. 16 × 128 = 2048 = input width. Each TG computes the FULL K-loop for its rows. There's no K-split across TGs. **So the grid multiplication IS redundant.**

### Specific Code Changes

1. **Gate/up** (L8142): Change `grid: ((8192/64) * 512, 1, 1)` → `grid: (8192/64, 1, 1)` = `grid: (128, 1, 1)`
2. **Down** (L8225): Change `grid: ((2048/16) * 128, 1, 1)` → `grid: (2048/16, 1, 1)` = `grid: (128, 1, 1)`

### Risk

- **Correctness: MEDIUM-HIGH**. Same race-write-same-value concern. Must verify with correctness gate.
- **Complexity: LOW**. One-line grid change per kernel.
- **Budget: NEGLIGIBLE**.
- **M4-testable: YES**. BF16 dense MLP, no `_nax`.

### Recommendation

**Test alongside Area A.** If the over-dispatch pattern is confirmed, this is a significant compute reduction for layer 0. However, layer 0 is only 1 of 40 layers, so the score impact is proportionally small. The attention kernels (Area A) affect all 40 layers and are higher priority.

---

## Summary Ranking

| Area | Potential | Risk | Complexity | M4-testable | Priority |
|---|---|---|---|---|---|
| **A: Attention grid over-dispatch** | HIGH (1000× compute reduction) | MEDIUM-HIGH | LOW | YES | **P0** — test first |
| **F: Dense MLP grid over-dispatch** | HIGH (128-512× compute reduction) | MEDIUM-HIGH | LOW | YES | **P1** — test with A |
| **C1: Merge shared into routed gate/up** | MEDIUM-HIGH (−39 dispatches, 14%) | LOW | MEDIUM | YES | **P2** — designed-for gap |
| **D1: Packed scales for down projection** | MEDIUM (memory transaction reduction) | MEDIUM | MEDIUM | YES | **P3** — proven pattern |
| **E: Command buffer encoding** | LOW (mostly done/assigned) | HIGH | HIGH | YES | **P4** — wait for PR #49 |
| **B: Incremental sliding attention** | LOW (mathematically intractable) | HIGH | HIGH | Partial | **P5** — do not pursue |

---

## Critical Observations

### The Grid Over-Dispatch Pattern (Areas A + F)

The most striking finding is the `* N` grid multiplication factor across attention AND dense MLP kernels. In standard Metal, this would be a massive compute waste. Two interpretations:

1. **Intentional over-dispatch for occupancy**: Apple Silicon GPUs may benefit from many small TGs to hide latency. The `* 1024` could be a deliberate choice to fill the GPU's 40 cores with enough TGs to keep the memory subsystem saturated. But 32,768 TGs for 32 head-pairs (sliding) is 1024× the needed count — even for 40 cores, 32 TGs would provide 0.8 TGs/core, which is low. 128-256 TGs (4-8 per core) would be more reasonable. **1024× is likely too much.**

2. **MLX kernel dispatch convention**: MLX's `metalKernel` may interpret the grid differently than raw Metal. The `* 1024` might be a thread count parameter where the actual threadgroup grid is computed differently. But the kernel source uses `threadgroup_position_in_grid.x` directly, which is standard Metal. **This suggests standard Metal semantics.**

**The safest test**: change one kernel's grid factor from 1024 to 1, run the correctness gate (`research/run_upstream_equivalence.sh`), and observe. If it passes, the over-dispatch is confirmed and can be applied to all affected kernels.

### The Shared Gate/Up Merge (Area C1)

This is the lowest-risk, most clearly-designed-for optimization. The code explicitly declares `mergedSharedActivated` (L10248) with a comment saying it should be set when the dispatches are merged, but never assigns it. The down+residual kernel already accepts the shared activation as a separate input. The implementation is filling an explicitly designed-but-unimplemented gap.

### Weight Contract Constraint

The Poolside v2 weight contract forbids transform-side derived layouts. All weight layout optimizations (Area D) must be runtime side copies built during `prepareFusedRuntimeWeights()` (L274), not transform changes. The existing `DARKBLOOM_PACKED_SCALES` bank (L10151) is the template for this pattern.

---

## Recommended Experiment Sequence

1. **Experiment 1 (P0)**: Change sliding attention grid from `(heads/2 * 1024, 1, 1)` to `(heads/2, 1, 1)`. Run correctness gate. If pass, apply to full attention and dense MLP. Measure decode time.

2. **Experiment 2 (P2)**: Implement shared gate/up merge (C1). Eliminates 39 dispatches. Run correctness gate. Measure decode time.

3. **Experiment 3 (P3)**: If Experiment 2 passes, extend packed-scales to down projection (D1). Run correctness gate. Measure decode time.

4. **Experiment 4**: If Experiments 1-3 pass, combine all three and measure. The effects should be approximately additive (different code paths, different mechanisms).

**Do NOT combine untested changes.** Each hypothesis must be validated independently before combining.
