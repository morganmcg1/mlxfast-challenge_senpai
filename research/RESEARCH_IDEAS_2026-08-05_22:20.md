# Research Ideas — 2026-08-05 22:20 UTC

## Context
- Frontier: 4058d0b code restored (scored 2.5459 on M5)
- Gap to leader (2.5523): 0.0064 (0.25% improvement needed)
- Decode is 75% of score, prefill 25%
- ~320-330 GPU dispatches per decode step, ~7 command-buffer boundaries
- MoE weight traffic: ~376 MB/step (dominant bandwidth cost)
- KV cache read: ~256 KB/layer, already at theoretical minimum for sliding (512 positions = window)
- LM-head coarse: ~109 MB/step (int5 planar, bandwidth-bound)

## Currently Assigned (4 students)
1. FMA dequant inner loop (Edward, PR #65)
2. Merge shared gate/up QMV into routed dispatch (Thorfinn, PR #50)
3. Fuse final RMSNorm into LM-head coarse kernel (Alphonse, PR #51)
4. Prefill MoE tile retuning — variant 5→4 switch (Askeladd, PR #52)

## Unassigned Ideas (ranked by expected decode impact)

### 1. Wider GQA Grouping (pair=4) on Sliding Layers — HIGH impact
**Causal question:** Can 4 query heads share each K/V load on sliding layers (GQA=8) to halve K/V traffic?
**Target evidence:** 30/40 layers are sliding with GQA=8, currently pair=2. Each pair shares K/V. Going to pair=4 halves K/V reads for 75% of layers.
**Expected signal:** ~2-4% decode improvement (K/V read is the dominant attention cost).
**Implementation:** New 4-head SDPA kernel with 4 independent online-softmax states. Grid changes from (heads/2)*1024 to (heads/4)*1024. Threadgroup memory ~4× larger. Must re-prove bit-exactness (reduction tree changes).
**Risk:** HIGH — new kernel, bit-exactness must be re-proven. Register pressure from 4 softmax states.
**Files:** `Sources/MLXFastModel/LagunaRuntimeModel.swift` (kernel + dispatch)

### 2. Batch K+V Projection into One quantizedMM — MEDIUM impact, LOW effort
**Causal question:** Can wk and wv be concatenated and projected in a single GEMV dispatch?
**Target evidence:** wk and wv have identical output dims (nKVHeads*128 = 1024). Currently 3 separate quantizedMM dispatches (Q, K, V) per layer × 40 layers = 120 GEMV dispatches/step. Batching K+V cuts 80 → 40.
**Expected signal:** ~0.5-1% decode improvement (pure dispatch overhead reduction, 40 fewer launches/step).
**Implementation:** Concatenate wk/wv packed weight banks at transform time. One quantizedMM produces [1, 2*nKVHeads*128], split before norm/rope kernel.
**Risk:** LOW — same contraction per element, just batched. Bit-exact if accumulation order preserved.
**Files:** `Sources/MLXFastModel/LagunaRuntimeModel.swift`, possibly `Sources/MLXFastTransform/`

### 3. Threadgroup-Cached Input Sharing in Gate/Up QMV — MEDIUM-HIGH impact
**Causal question:** Can the 2× redundant input read in gate/up QMV be eliminated via threadgroup memory?
**Target evidence:** Both simdgroups in each TG of the R1 kernel read the same 512 BF16 input values independently. 2× input bandwidth. Loading once into TG memory (1 KB) and sharing halves input reads.
**Expected signal:** ~0.5-1.5% decode improvement (input is re-read every K-block iteration, 4 iterations × 512 values).
**Implementation:** Load 512 BF16 input into threadgroup memory (1024 bytes), barrier, both simdgroups read from TG. Adds 1 barrier but saves 2× device reads per iteration.
**Risk:** MEDIUM — barrier cost must be less than saved bandwidth. If L2 hit rate is high on M5, benefit shrinks. Test on M4 first as directional evidence.
**Files:** `Sources/MLXFastModel/LagunaRuntimeModel.swift` (kernel only)

### 4. Denser asyncEval Rungs at Front of Decode Step — MEDIUM impact
**Causal question:** Can adding more asyncEval fires at the beginning of the decode step improve overlap?
**Target evidence:** Currently 7 asyncEval fires at layers 0,1,7,15,23,31,39. The first 2 layers fire immediately, then there's a gap to layer 7. Adding fires at layers 3-4 could overlap more early-layer work.
**Expected signal:** ~0.3-0.5% decode improvement (already near-optimal, diminishing returns).
**Implementation:** Change `DARKBLOOM_DECODE_ASYNC_STAGE` env default from `at:0,1,7,15,23,31,39` to `at:0,1,3,5,7,15,23,31,39` or similar.
**Risk:** LOW — env var change only, easily A/B tested. But may not help if command buffer overhead dominates.
**Files:** `Sources/MLXFastModel/LagunaRuntimeModel.swift` (default value only)

### 5. Fold SDPA Output Reshape into Fused Gated Affine O-Projection — LOW-MEDIUM impact
**Causal question:** Can the SDPA output reshape be absorbed into the O-projection kernel?
**Target evidence:** After SDPA, the output is reshaped before the gated output projection. If the O-proj kernel can consume the pre-reshape layout, one reshape dispatch is eliminated.
**Expected signal:** ~0.2-0.5% decode improvement (one fewer reshape per layer × 40 layers).
**Implementation:** Modify the O-proj kernel to accept the SDPA output layout directly, performing the reshape implicitly during the contraction.
**Risk:** MEDIUM — must preserve exact bit patterns in the reshape. May require kernel changes.
**Files:** `Sources/MLXFastModel/LagunaRuntimeModel.swift`

### 6. Extend Attention Projection Async Beyond Layer 0 — LOW-MEDIUM impact
**Causal question:** Can async attention projection be extended to more layers?
**Target evidence:** `DARKBLOOM_ATTN_PROJECTION_ASYNC` is ON but only for layer 0. Extending to more layers could overlap attention projection with earlier layers' MoE work.
**Expected signal:** ~0.2-0.5% decode improvement (marginal, layer 0 already benefits).
**Implementation:** Extend the guard condition beyond `layerIdx == 0` to cover more layers.
**Risk:** LOW — same mechanism, more coverage. But may not help if layer 0 already covers the critical path.
**Files:** `Sources/MLXFastModel/LagunaRuntimeModel.swift`

### 7. Wider Weight Loads (16B) in Decode QMV Kernels — LOW-MEDIUM impact
**Causal question:** Can uint4 (16B) loads replace uint2 (8B) loads in the QMV inner loop?
**Target evidence:** Prefill kernel already has `kWideLoadShapeOk` 16B loads. Decode uses 8B uint2. Wider loads improve memory throughput.
**Expected signal:** ~0.3-0.5% decode improvement (better memory coalescing).
**Implementation:** Restructure lane-to-byte mapping for 16B alignment, or use `load_unsafe_wide` patterns.
**Risk:** MEDIUM — alignment constraints, lane mapping changes may affect correctness.
**Files:** `Sources/MLXFastModel/LagunaRuntimeModel.swift`

### 8. Interleave Gate/Up Codes with Scales in Single Packed Tensor — MEDIUM impact
**Causal question:** Can codes and scales be interleaved in one contiguous bank to improve memory coalescing?
**Target evidence:** R1 kernel issues 4 separate device streams per iteration (gate codes, up codes, gate scale, up scale). Interleaving into one bank reduces pointer-chasing.
**Expected signal:** ~0.3-0.7% decode improvement (better coalescing, fewer address calculations).
**Implementation:** Create interleaved bank [expert][row][k-block][8B codes | 1B gate-scale | 1B up-scale]. One contiguous read fetches both codes and scales.
**Risk:** MEDIUM — requires transform change + kernel change. Must preserve exact values.
**Files:** `Sources/MLXFastModel/LagunaRuntimeModel.swift`, `Sources/MLXFastTransform/`

## Priority for Next Wave
When current students complete their rebased experiments, assign in this order:
1. **Batch K+V projection** — lowest effort, pure dispatch win, low risk
2. **Threadgroup input sharing** — medium effort, bandwidth win, testable on M4
3. **Wider GQA grouping** — highest impact but highest risk, needs careful kernel work

## Key Insight from Submission History
Edward's MoE down ops=2 change showed +6.5% on M4 but scored 2.502 on M5 (vs 4058d0b's 2.546). This is a **-1.7% M5 regression** — M4→M5 timing diverged significantly. The 4058d0b code with ops=4 is better on M5. **M4 measurements are directional only; never trust them for promotion decisions.**
