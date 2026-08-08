# M5 Correctness Audit: bca94c5 → 59e39127

## Summary

The ONLY successful M5 submission was the organizer frontier code itself (bca94c5, submitted as f790e33f, score 2.5213). Every submission with our modifications has FAILED — over 50 consecutive failures. The fma() reduction order was already fixed (commit 34770ebf), but submission f6b87dc1 (59e39127) still FAILED.

**Only 3 editable files changed** between bca94c5 and 59e39127. **Zero Vendor/ files changed.** All other 149 changed files are non-editable (research docs, tests, harness, etc.) and are not submitted.

## Changed Editable Files

1. `Sources/MLXFastModel/LagunaRuntimeModel.swift` — scored forward pass (10,110 line diff)
2. `Sources/MLXFastModel/LagunaLmHeadPrune.swift` — lm_head projection (2,081 line diff)
3. `Sources/MLXFastModel/LagunaRuntimeWeights.swift` — warmup/init (28 line diff)

## Root Cause: New Decode-Path lm_head Fused Refinement

### CRITICAL — `DARKBLOOM_LMHEAD_FUSED_REFINEMENT` (DEFAULT ON, NEW)

**File:** `Sources/MLXFastModel/LagunaLmHeadPrune.swift`, line 94-96 (59e39127)
**File:** `Sources/MLXFastModel/LagunaRuntimeModel.swift`, line 7321 (59e39127)

This flag does NOT exist in bca94c5. It is DEFAULT ON in 59e39127.

In bca94c5, the decode lm_head path always uses the full int5 coarse pass (both nibble + bit planes, `value = u - 16`) followed by exact BF16 GEMV for candidates.

In 59e39127, the decode path (`useFusedRefinement: inputs.dims(1, 1)` = true) activates **mode 1**:
- **Coarse (mode 1):** nibble-only 2x-coarse, `value = ne*2 - 15.5` (NOT the full int5 decode), `d_acc = sd * ag` (full-cell, not half-cell)
- **Refinement:** re-reads the residual bit plane, computes `correction = sd * sum(x * (bit - 0.5))`, `c_refined = coarse + correction`
- **Refined delta:** `d_up = float(delta[r]) * 0x1.005p-1f` — a NEW constant explicitly noted as a correction from a source `0x1.004p-1f` that "would miss the bound by one gamma"
- **Re-screens:** `c_refined + delta_up >= thr[0]`
- **Exact:** only for rows surviving the refined screen, runs the stock BF16 GEMV

**Classification: NUMERICAL — MUST REVERT**

The decode path now takes a completely different computation: a three-level screen (nibble-only coarse → refinement → exact) instead of the two-level screen (full int5 coarse → exact). Even if the refinement math is sound, the FP rounding order is different, and the `0x1.005p-1f` constant is unproven on M5.

**Specific revert needed:**
- In `LagunaRuntimeModel.swift` line 7321: change `useFusedRefinement: inputs.dims(1, 1)` to `useFusedRefinement: false`
- OR set `DARKBLOOM_LMHEAD_FUSED_REFINEMENT=0` in the environment (but this is a runtime flag, not submitted code)
- OR revert the `logits()` function to not accept `useFusedRefinement` parameter and always use mode 0
- Simplest code fix: change `LagunaLmHeadPrune.swift` line 94-96 to `let lagunaLmHeadFusedRefinementEnabled = false`

### CRITICAL — Coarse kernel changed from v5 to v7

**File:** `Sources/MLXFastModel/LagunaLmHeadPrune.swift`, line 152-153 (59e39127)

- bca94c5: `laguna_lmhead_int5_inline_coarse_ratio_bound_delta_bf16_v5` (4 inputs: x, codes_lo, codes_hi, scales)
- 59e39127: `laguna_lmhead_int5_coarse_delta_bf16_v7` (5 inputs: x, codes_lo, codes_hi, scales, mode)

The int5 plane encoding changed:
- bca94c5: nibble = low 4 bits of `u`, bit plane = bit 4 of `u`; kernel: `ne | (he << 4) - 16`
- 59e39127: nibble = high 4 bits of `u` (`u >> 1`), bit plane = bit 0 of `u`; kernel: `(ne << 1) | he - 16`

Both are self-consistent (encoding matches decoding) and should produce the same coarse logits in mode 0. But mode 1 (nibble-only) uses a DIFFERENT decode: `ne*2 - 15.5` which is a 2x-coarse approximation, not the full int5.

**Classification: LAYOUT (mode 0) / NUMERICAL (mode 1) — mode 0 is safe, mode 1 MUST REVERT**

### CRITICAL — Exact kernel unified with mode dispatch

**File:** `Sources/MLXFastModel/LagunaLmHeadPrune.swift`, line 500 (59e39127)

- bca94c5: `laguna_lmhead_exact_inline_mask_block_delta_bf16_lane0_mask_v1` (5 inputs: coarse, delta, thr, lm_head, x)
- 59e39127: `laguna_lmhead_exact_mask_block_v2` (8 inputs: coarse, delta, thr, lm_head, x, codes_bit, scales, mode)

The mode 0 path in 59e39127 is functionally identical to bca94c5's kernel (same GEMV replica, same accumulation). But mode 1 adds the refinement pass described above.

**Classification: DISPATCH — mode 0 safe, mode 1 MUST REVERT (same root cause as above)**

---

## High-Risk Decode MoE Changes

### CRITICAL — Merged 9-slot routed+shared SwiGLU QMV kernel (v1 → v2_halved)

**File:** `Sources/MLXFastModel/LagunaRuntimeModel.swift`, line 4438 (59e39127)

- bca94c5: `laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v1` (4 inputs: input, fused_weight, packed_scales, router_keys)
- 59e39127: `laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2_halved` (8 inputs: input, fused_weight, packed_scales, gate_up_escape, indices, shared_weight, shared_scales, shared_escape)

**Changes:**
1. Uses **halved scales** (`simd_lid / 2` instead of `simd_lid`) — reads every other scale byte
2. Uses **escape bytes** for the k=0 pair (relies on NVFP4 pairwise-constancy invariant: `scale[2k] == scale[2k+1]`)
3. Merges shared expert into the same kernel (9th slot)
4. Replaces `router_keys` with `indices` (different routing input format)

**Classification: NUMERICAL + LAYOUT + DISPATCH — INVESTIGATE**

If the NVFP4 pairwise-constancy invariant (`scale[2k] == scale[2k+1]` for k≥1) does NOT hold on the M5 checkpoint, the halved scales silently return wrong values → wrong MoE output → token mismatch.

**Diagnostic:** Set `DARKBLOOM_NATIVE_AFFINE_NVFP4=0` and check if the routed+shared down residual still works. Or compare `packed_scales` against the halved version at init time.

### HIGH — `lagunaRoutedSharedDownResidual` kernel rewritten with halved scales

**File:** `Sources/MLXFastModel/LagunaRuntimeModel.swift`, ~line 9013 (diff)

- `outputs_per_simd` changed from 1 to 8
- `scale_row_bytes` changed from 32 to 16
- Scale index uses `lane/2` instead of `lane` with escape byte for k=0
- Grid changed from `hiddenSize * 288` to `(hiddenSize/8) * 288`
- Input load expression changed from `vec<bfloat,4>` to `float4` (functionally identical)

**Classification: NUMERICAL + LAYOUT — INVESTIGATE**

Same halved-scales risk as above.

### HIGH — Decode NVFP4 QKV kernel rewritten with halved scales + g_proj fusion

**File:** `Sources/MLXFastModel/LagunaRuntimeModel.swift`, line 3101 (59e39127)

- bca94c5: `laguna_decode_nvfp4_qkv_h{heads}_r1_v1` (source is fixed string)
- 59e39127: `laguna_decode_nvfp4_qkv_h{h}_r1_v1{s}_hs1_fgp` (source is a function with `halvedScales: true, withGProj: true`)

**Changes:**
1. Uses **halved scales** (`simd_lid / 2` instead of `simd_lid`)
2. Uses **escape bytes** (`qkv_escape[0]`, `qkv_escape[1]`, `qkv_escape[2]`)
3. Adds **g_proj fusion** — computing gate values in the same kernel

**Classification: NUMERICAL + LAYOUT — INVESTIGATE**

Same halved-scales risk as above. The g_proj fusion uses `gproj_metadata` which is a new interleaved metadata layout that must be built consistently.

---

## Medium-Risk Changes

### MEDIUM — Attention kernel BDP padding + simd_sum split

**File:** `Sources/MLXFastModel/LagunaRuntimeModel.swift`, lines 1459-1736 (59e39127, sliding kernel only)

1. `threadgroup U outputs[4 * BN * BD]` → `4 * BN * BDP]` where `BDP = BD + 1 = 33`
2. All `pair_plane_size = BN*BD` → `BN*BDP`; all indices `lane*BD + sg` → `lane*BDP + sg`
3. Packed `simd_sum(vec<U,4>)` → 4 separate scalar `simd_sum()` calls

**Classification: LAYOUT (BDP) + NUMERICAL-RISK (simd_sum split)**

The BDP padding is for bank-conflict avoidance. All indices consistently use BDP (verified — no bare `BD` references without P). The padding should be safe.

The simd_sum split from packed vec4 to 4 scalar calls: the per-component result should be identical since simd_sum is componentwise. However, the Metal compiler on M5 may schedule them differently. This is a low-risk change but worth verifying.

### MEDIUM — NVFP4 scale-fold / scale-defer / seed-elide / nibble-split

**File:** `Sources/MLXFastModel/LagunaRuntimeModel.swift`, various locations (59e39127)

New flags (all DEFAULT ON):
- `DARKBLOOM_NVFP4_SCALE_FOLD` — folds `256*16384 = 2^22` into one multiply
- `DARKBLOOM_NVFP4_SCALE_CARRY` — carries sign bit into half pattern
- `DARKBLOOM_NVFP4_SCALE_DEFER` — defers `2^22` to per-row epilogue
- `DARKBLOOM_NVFP4_QDOT_SEED_ELIDE` — elides `+0.0f` seed
- `DARKBLOOM_NVFP4_NIBBLE_SPLIT` (default 1) — 3-mask nibble-split decode

All documented as bit-exact. The scale-defer comment admits divergence if `0 < |scale*accum| < 2^-104`, claiming ~60 binades of margin. This is a real (if tiny) numerical risk.

**Classification: NUMERICAL (claimed bit-exact) — VERIFY**

### MEDIUM — Gated affine o_proj NVFP4 kernel (NEW)

**File:** `Sources/MLXFastModel/LagunaRuntimeModel.swift`, ~line 2113 (59e39127)

New kernel with halved scales + escape + sign-carry + seed-elide. Same pairwise-constancy dependency.

**Classification: NUMERICAL + LAYOUT — INVESTIGATE**

### MEDIUM — g_proj interleaved metadata (NEW)

**File:** `Sources/MLXFastModel/LagunaRuntimeModel.swift`, lines 198-211 (59e39127)

`LagunaNativeAffineWeight` gains `interleavedMetadata = contiguous(stacked([scales, biases], axis:-1).reshaped(...))`. New metadata layout consumed by the decode QKV kernel. Must be built consistently with how the kernel reads it.

**Classification: LAYOUT — VERIFY**

### MEDIUM — Router loop-interchange

**File:** `Sources/MLXFastModel/LagunaRuntimeModel.swift`, lines 468-480, 9216-9223 (59e39127)

`for (delta...) { for (r...) }` swapped to `for (r...) { for (delta...) }` in the residual+RMSNorm router and dense down. Independent per-row accumulators are interleaved. The final value per row should be identical.

**Classification: NUMERICAL-RISK — VERIFY**

---

## Low-Risk / Safe Changes

### SAFE — Warmup changes

**File:** `Sources/MLXFastModel/LagunaRuntimeWeights.swift`

- Changed from 1 decode warmup to 4 decode warmups (3 in loop + 1 extra)
- Removed `lagunaWarmSlidingFusedAttentionKernel()` and `lagunaWarmDecodeQKVR1Kernels()` calls

**Classification: COSMETIC** — warmup-only, does not affect correctness (affects JIT timing only)

### SAFE — `lagunaPhaseCacheLimitBytes` removal

**File:** `Sources/MLXFastModel/LagunaRuntimeModel.swift`

The `Memory.cacheLimit` override was deleted. Changes allocator retention behavior. Could affect which allocations reuse which buffers, but unlikely to affect FP results.

**Classification: BUDGET — LOW RISK**

### SAFE — `extension MLXArray { dims(...) / sameDims(...) }`

**File:** `Sources/MLXFastModel/LagunaRuntimeModel.swift`, lines 9-37 (59e39127)

New allocation-free shape check helpers replacing `.shape == [...]` preconditions. Semantically identical.

**Classification: BUDGET — SAFE**

### SAFE — Prefill MoE fused gate/up

**File:** `Sources/MLXFastModel/LagunaRuntimeModel.swift`

`lagunaPrefillFusedRoutedGateUpEnabled` is DEFAULT ON in both bca94c5 and 59e39127. The 59e39127 version adds `halvedScales` and `scalesEscape` parameters but hardcodes `useHalved = false`, so the prefill path uses the same `gatherQuantizedMM` with full scales as before.

**Classification: DISPATCH — SAFE (prefill path unchanged)**

### SAFE — Router ordinal/score-table dispatch hardcoded

**File:** `Sources/MLXFastModel/LagunaRuntimeModel.swift`

Previously branched on `lagunaDecodeRouterOrdinalEnabled` (default ON → ordinal) and `lagunaDecodeRouterOrdinalScoreTableEnabled` (default ON → score table). Now hardcoded to the default paths. Behavior unchanged on default flags.

**Classification: DISPATCH — SAFE**

### SAFE — MXFP8 fallback removed from lm_head prune

**File:** `Sources/MLXFastModel/LagunaLmHeadPrune.swift`

In bca94c5, if int5 build fails, falls back to MXFP8 coarse. In 59e39127, if int5 build fails, returns nil → stock lm_head path. This is SAFER (falls back to bit-exact stock path).

**Classification: DISPATCH — SAFE**

---

## Prioritized Revert List

### PRIORITY 1 — MUST REVERT (most likely cause of M5 correctness failure)

1. **Disable `DARKBLOOM_LMHEAD_FUSED_REFINEMENT` for decode**
   - File: `Sources/MLXFastModel/LagunaRuntimeModel.swift`, line 7321
   - Change: `useFusedRefinement: inputs.dims(1, 1)` → `useFusedRefinement: false`
   - This eliminates the mode 1 decode path (nibble-only coarse + refinement) and falls back to mode 0 (full int5, same as bca94c5)
   - Also add: `let lagunaLmHeadFusedRefinementEnabled = false` in `LagunaLmHeadPrune.swift` line 94

2. **If #1 alone doesn't fix it, disable halved scales in the merged MoE decode kernel**
   - File: `Sources/MLXFastModel/LagunaRuntimeModel.swift`, line 4438
   - The `lagunaRoutedSwiGLUQMVPackedTop8R1Kernel` uses halved scales with escape bytes
   - Revert to v1 kernel (uses `router_keys`, full scales, no shared expert merge)
   - OR add guard: if halved banks are nil, fall through to stock `gatherQuantizedMM`

### PRIORITY 2 — INVESTIGATE (secondary suspects)

3. **Decode NVFP4 QKV kernel halved scales + g_proj fusion**
   - File: `Sources/MLXFastModel/LagunaRuntimeModel.swift`, line ~3101
   - Set `halvedScales: false` in the kernel source generation
   - OR disable `lagunaDecodeNVFP4QKVR1Enabled` entirely

4. **`lagunaRoutedSharedDownResidual` halved scales**
   - File: `Sources/MLXFastModel/LagunaRuntimeModel.swift`, ~line 9013
   - Revert to full scales (scale_row_bytes = 32, lane instead of lane/2)

5. **NVFP4 scale-fold / scale-defer**
   - Set `DARKBLOOM_NVFP4_SCALE_FOLD=0`, `DARKBLOOM_NVFP4_SCALE_DEFER=0`
   - These change the FP multiplication order

### PRIORITY 3 — VERIFY (low risk but unproven on M5)

6. **Attention simd_sum split** (packed vec4 → 4 scalar calls)
   - The results should be identical, but verify on M5

7. **Router loop-interchange**
   - Verify per-row reduction is identical

8. **Attention BDP padding**
   - Verify no off-by-one in index math

---

## Recommended Diagnostic Path

1. **First test:** Set `DARKBLOOM_LMHEAD_FUSED_REFINEMENT=0` in the environment. This disables the mode 1 decode path and uses mode 0 (full int5, same as bca94c5). If this passes correctness, the fused refinement is the root cause.

2. **If #1 passes:** Fix the code to disable fused refinement by default (revert the `useFusedRefinement: inputs.dims(1, 1)` call).

3. **If #1 fails:** The problem is in the MoE decode kernels. Set `DARKBLOOM_NVFP4_SCALE_FOLD=0` and `DARKBLOOM_NVFP4_SCALE_DEFER=0` to disable the scale transforms. If this passes, one of the NVFP4 scale transforms is causing the failure.

4. **If all environment fixes fail:** The problem may be in the halved-scales mechanism. Disable all halved-scales paths by reverting the merged 9-slot kernel to v1 and the decode QKV kernel to non-halved.

5. **Nuclear option:** Revert ALL 3 editable files to bca94c5 versions. This is the guaranteed-correct baseline. Then re-apply changes one at a time, testing correctness after each.

---

## Key Insight

The bca94c5 organizer frontier was the ONLY submission that passed M5 correctness. The 59e39127 advisor branch accumulated MANY changes across the editable surface. The most likely cause is the **new decode-path lm_head fused refinement** (mode 1), which introduces a completely new computation that was never validated on M5. The second most likely cause is the **halved scales mechanism** in the decode MoE kernels, which depends on the NVFP4 pairwise-constancy invariant holding on the M5 checkpoint.

The fix should be incremental: disable the fused refinement first (PRIORITY 1), then if needed, disable the halved scales (PRIORITY 2).
