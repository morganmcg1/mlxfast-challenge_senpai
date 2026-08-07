# Bandwidth Reduction Audit — 2026-08-07

Comprehensive audit of all remaining bit-exact bandwidth reduction opportunities
on the scored Laguna XS 2.1 NVFP4 decode/prefill path, excluding work already
covered by PR #169 (QKV+O-proj scale halving, WIP) and PR #180 (MoE scale halving,
revision requested).

## Architecture Summary

- **40 layers**: layer 0 = dense MLP (BF16, no quantization, no scales).
  Layers 1-39 = 39 sparse MoE layers with NVFP4 quantization (group_size=16,
  uint8 E4M3 scales, 4-bit codes packed 2-per-byte in uint32).
- **Attention**: 10 full-attention (48 heads, YaRN) + 30 sliding-window (64 heads,
  plain RoPE, window 512). `DARKBLOOM_NATIVE_AFFINE_NVFP4` defaults ON → ALL
  attention layers use NVFP4 (group_size=16, uint8 scales).
- **g_proj**: group_size=32 affine INT8 with bfloat scales. NOT NVFP4 — the
  pairwise-constancy invariant does NOT apply.
- **MoE**: 256 routed experts (top-8 per token) + 1 shared expert per sparse layer.
  moeIntermediateSize = sharedExpertIntermediateSize = 512, hiddenSize = 2048.

## What PR #169 (Askeladd, WIP) Covers

- QKV decode kernel (`lagunaDecodeNVFP4QKVR1Source`, L4604): uint8 scales,
  group_size=16, 128 B/row. Targets ~39 MiB/step savings (scale halving).
- O-proj NVFP4 decode kernel (`lagunaGatedAffineOProjNVFP4Source`, L4129):
  uint8 scales, group_size=16. Scale halving.
- Both are NVFP4 group-16 → pairwise-constancy halving applies.

## What PR #180 (Alphonse, revision requested) Covers

PR #180 was inspected at commit `00c3969` on branch `pr180`:

| Kernel | Lines | Halved? | Wired? |
|--------|-------|---------|--------|
| Routed gate/up packed R1 (`lagunaRoutedSwiGLUQMVPackedTop8R1Kernel`) | L7288 | YES (scale_row_bytes 32→16, lane/2) | YES |
| Routed+shared down fused (`lagunaRoutedSharedDownResidualKernel`) | L7600 | YES (scale_row_bytes 32→16, lane/2) | YES |
| Shared down standalone (`lagunaSharedDownResidualKernel`) | L6698 | NO | N/A (fallback) |
| Shared gate/up QMV (`lagunaSharedSwiGLUQMVRows1Kernel` / `lagunaSharedSwiGLUQMVKernel`) | L6597/L6515 | NO | `_halvedFusedGateUpScales` built but never passed to kernel |

**Critical finding**: PR #180 builds `_halvedFusedGateUpScales` and
`_fusedGateUpScalesEscape` (diff L8023-8024, L8079-8080) but
`fusedSharedDownInputs` (L8152 in PR180) still passes `banks.gateUpScales`
(the FULL scales) to `lagunaSharedSwiGLUQMV`. The halved scales are **dead code**.

---

## Opportunity 1: Shared SwiGLU QMV Gate/Up Scale Halving ★ HIGHEST IMPACT

**Status**: NOT covered by PR #169 or #180. PR #180 prepares the halved tensors
but never wires them.

**Kernel**: `lagunaSharedSwiGLUQMVRows1Kernel` (L6597-6666, default ON) and
`lagunaSharedSwiGLUQMVKernel` (L6515-6593, fallback).

| Metric | Value |
|--------|-------|
| Scale dtype | uint8 (E4M3) |
| Group size | 16 (NVFP4) |
| scale_row_bytes | 128 (2048/16) |
| Fused rows | 1024 (2×512 gate+up) |
| Bytes/layer/step | 1024 × 128 = 131,072 B |
| Total (39 layers) | ~4.87 MiB/step |
| Halving saves | ~2.43 MiB/step |
| Bit-exact | YES (same pairwise-constancy invariant) |
| On scored path | YES (default ON via `lagunaFusedSharedSwiGLUQMVEnabled` + `lagunaSharedSwiGLUQMVRows1Enabled`) |
| Complexity | LOW-MEDIUM |

**Mechanism**: The shared expert's fused gate/up scales `[1024, 128]` uint8 have
the NVFP4 pairwise-constancy invariant (`scale[2k]==scale[2k+1]` for k≥1).
Halving produces `[1024, 64]` + escape `[2]` (gate row 0 byte 1, up row 512 byte 1).
PR #180 already builds these at L8079-8080 but `fusedSharedDownInputs` (L8152)
passes the full scales to `lagunaSharedSwiGLUQMV`. The kernel source (L6597-6666)
still has `scale_row_bytes = 128` and indexes scales by `lane` (not `lane/2`).

**Implementation**:
1. Modify `lagunaSharedSwiGLUQMVRows1Kernel` source: `scale_row_bytes` 128→64,
   scale pointer `lane` → `lane/2`, add escape byte input.
2. Add `gateUpEscape` parameter to `lagunaSharedSwiGLUQMV` Swift function.
3. Modify `fusedSharedDownInputs` (L8152) to pass `_halvedFusedGateUpScales`
   and `_fusedGateUpScalesEscape` instead of `banks.gateUpScales`.
4. The halved tensors are already built by PR #180 — just wire them.

**At M5 651.8 GB/s**: 2.43 MiB / 651.8 GB/s ≈ 3.7 µs saved per ~5376 µs step
= ~0.07% decode. Small per-step but 100% free (code already exists).

---

## Opportunity 2: Standalone Shared Down Residual Kernel Halving (FALLBACK)

**Status**: NOT covered by PR #180. The fused path (L7600) IS halved; this
standalone fallback (L6698) is not.

**Kernel**: `lagunaSharedDownResidualKernel` (L6698-6760).

| Metric | Value |
|--------|-------|
| Scale dtype | uint8 (E4M3) |
| Group size | 16 (NVFP4) |
| scale_row_bytes | 32 (512/16) |
| Rows | 2048 |
| Bytes/layer/step | 2048 × 32 = 65,536 B |
| Total (39 layers) | ~2.44 MiB/step |
| Halving saves | ~1.22 MiB/step |
| Bit-exact | YES |
| On scored path | FALLBACK only (runs when `lagunaFusedRoutedSharedDownResidualEnabled` declines, which is default ON) |
| Complexity | LOW |

**Priority**: LOW. On the primary decode path, the fused `lagunaRoutedSharedDownResidual`
(L7600) already halves both routed and shared down scales via PR #180. This
standalone kernel only runs when the fusion guard fails. If the guard always
passes (default config), this kernel never executes during scored decode.

---

## Opportunity 3: Gate-Softplus 4× Redundant Scale/Bias Loading

**Status**: NOT covered by PR #169 or #180. Different mechanism (not halving).

**Kernel**: `lagunaGateSoftplusSource` (L4307-4350), compiled as
`laguna_gate_sp_h{heads}_v1`. Runs when `DARKBLOOM_NATIVE_AFFINE_NVFP4` is ON
(default) and g_proj is separate (NVFP4 attention, default config).

| Metric | Value |
|--------|-------|
| Scale dtype | bfloat16 (2 B) |
| Group size | 32 (affine INT8, NOT NVFP4) |
| Scale bytes/row | 64 × 2 = 128 B (scales) + 128 B (biases) = 256 B metadata/row |
| Rows/layer | heads (48 full / 64 sliding) |
| Scales/step (all 40) | ~300 KiB |
| Biases/step (all 40) | ~300 KiB |
| Total metadata/step | ~600 KiB |
| Halving applies | NO (group_size=32, not NVFP4) |
| 4× dedup saves | ~450 KiB/step |
| Bit-exact | YES (broadcast, not reduction change) |
| On scored path | YES (default ON) |
| Complexity | MEDIUM |

**Mechanism**: The kernel indexes scales with `lane/SS` where `SS = GS/V =
32/8 = 4` (L4310, L4316). This means 4 consecutive lanes (0-3, 4-7, ...) read
the SAME scale and bias value from device memory — a 4× redundant device load.
Loading once per lane-group (e.g., `lane%4==0` loads, broadcast via
`simd_shuffle`) saves 3/4 of scale+bias device reads.

**Bit-exactness**: Each lane still computes `r[row] += s*a + sum*b` with the
identical float value — the `simd_sum` reduction is unchanged. The load is
broadcast, not the accumulation.

**Same pattern exists in**: `lagunaNormAffineQKVSource` (L4787,
`simd_lid/scale_step_per_thread` where `scale_step_per_thread = 32/8 = 4`)
and `lagunaGatedAffineOProjSource` (L3869, same divisor). But QKV scales are
NVFP4 group-16 (PR #169's target), and the O-proj affine path is the INT8
variant (not the NVFP4 path). The gate-softplus is the pure INT8 g_proj path.

---

## Opportunity 4: Indexed Metadata LUT for Standalone g_proj

**Status**: NOT covered by PR #169 or #180.

**Mechanism**: The `lagunaIndexedAffineMetadata` scheme (L2853-2891) dedups
(scale, bias) BF16-bit pairs into a UInt16-indexed LUT. It is wired into:
- Fused QKV bank (L5374) + indexed kernel variant
- O-proj bank (L5304) + indexed kernel variant

But `lagunaNativeAffineGProjWeight` (L435-450) never sets `indexedMetadata`,
and `lagunaGateSoftplusSource` has no indexed variant (reads raw scales/biases).

| Metric | Value |
|--------|-------|
| Bit-exact | YES (LUT stores exact BF16 bits) |
| On scored path | YES (default ON) |
| Complexity | MEDIUM-HIGH |
| Savings | Unknown (depends on distinct pair count; g_proj has heads×64 = 3072-4096 pairs/layer) |

**Priority**: MEDIUM. Dedup ratio is unknown without a census. The g_proj is a
tiny projection (heads × 2048) — the metadata is small (~600 KiB/step total)
relative to the weight code traffic (~4.7 MiB/step). Benefit is bounded.

---

## Opportunity 5: Routed Gate/Up Non-R1 Packed Kernel Halving (FALLBACK)

**Status**: NOT covered by PR #180 (only the R1 variant was halved).

**Kernels**: `lagunaRoutedSwiGLUQMVPackedKernel` (L7041-7138),
`lagunaRoutedSwiGLUQMVPackedTop8Kernel` (L7266-7275, non-R1).

| Metric | Value |
|--------|-------|
| Group size | 16 (NVFP4) |
| scale_row_bytes | 32 |
| Halving applies | YES |
| Bit-exact | YES |
| On scored path | FALLBACK (R1 is default ON; non-R1 runs when `DARKBLOOM_ROUTED_GATEUP_R1=0`) |
| Complexity | LOW-MEDIUM |

**Priority**: LOW. The R1 kernel (L7288) is default ON and already halved by
PR #180. These non-R1 variants only run when R1 is explicitly disabled.

---

## Opportunity 6: Routed Down Reduce Kernel Halving (FALLBACK)

**Status**: NOT covered by PR #180 directly; subsumed by fused kernel.

**Kernel**: `lagunaRoutedDownReduceKernel` (L7442-7546).

| Metric | Value |
|--------|-------|
| Group size | 16 (NVFP4) |
| scale_row_bytes | 32 |
| Halving applies | YES |
| Bit-exact | YES |
| On scored path | FALLBACK (fused routed+shared down is default ON) |
| Complexity | LOW |

**Priority**: LOW. The fused `lagunaRoutedSharedDownResidual` (L7600) is
default ON and already halves via PR #180. This standalone runs only when the
fusion guard fails.

---

## Opportunity 7: Routed Gate/Up Raw (Non-Packed) Kernel Halving (FALLBACK)

**Status**: NOT covered by PR #169 or #180.

**Kernels**: `lagunaRoutedSwiGLUQMVKernel` (L6794-6894),
`lagunaRoutedSwiGLUQMVRows1Kernel` (L6899-6993).

| Metric | Value |
|--------|-------|
| Group size | 16 (NVFP4) |
| scale_row_bytes | 128 (fused_scales, raw layout) |
| Halving applies | YES |
| Bit-exact | YES |
| On scored path | FALLBACK (DARKBLOOM_PACKED_SCALES is default ON; raw kernels run when packed disabled) |
| Complexity | MEDIUM (different scale layout than packed) |

**Priority**: LOW. DARKBLOOM_PACKED_SCALES is default ON. These raw kernels
only run when packing is explicitly disabled.

---

## Non-Opportunities (Ruled Out)

### Gate-softplus / g_proj scale halving
- group_size=32 affine INT8 with bfloat scales. NOT NVFP4. The
  pairwise-constancy invariant (`scale[2k]==scale[2k+1]` for k≥1) is specific
  to the NVFP4 group-16 quantizer bug in `fp_quantized.h` L2184-2195. It does
  not apply to group-32 affine INT8. **No halving possible.**

### Dense MoE (layer 0)
- Layer 0 is plain BF16 (no quantization, no scales). `lagunaDenseGateUpSwiGLUKernel`
  (L7785) and `lagunaDenseDownResidualKernel` (L7882) have no scale inputs.
  **Nothing to halve.**

### NVFP4 code packing
- NVFP4 codes are 4-bit, packed 2-per-byte (8-per-uint32). This is the maximum
  possible packing for 4-bit values. All kernels load codes as `uint2` (16
  values per load). **No further packing possible.**

### KV cache quantization
- KV cache is BF16 throughout. Quantizing to INT8/INT4 would cut ~50-75% of
  ~80 MiB/step KV read traffic, but it is **NOT bit-exact** and falls outside
  the accepted attention quantization envelope (which covers projection
  weights, not cache state). **Ruled out by constraints.**

### KV cache movement
- 30 sliding layers read exactly 512 positions (window == ring, no redundant
  rows). 10 full-attention layers read their full growing context (inherent
  to full attention). Fused kernels already: read cache in-place (no
  per-step copy), substitute just-written slot from registers, elide
  single-token mask, avoid host sync. **No bit-exact reduction available.**

### Redundant Swift copies/materializations
- Scored decode path is heavily optimized into single-dispatch fused Metal
  kernels. No `.evaluated()`, `.item()`, or host sync on the scored path.
  All weight prep is load-time. Reshapes/transposes for L==1 are metadata-only.
  **No significant copy reduction available.**

### Minor Swift dispatch findings
- `eScoreCorrectionBias` float32 cast per step (~40 KB, precomputable) —
  negligible bandwidth.
- `routerKeys` output produced but potentially unused as guard predicate —
  needs kernel-equivalence check before removal; negligible bandwidth.

---

## Priority Ranking

| # | Opportunity | Est. savings/step | Path | Complexity | Priority |
|---|-------------|-------------------|------|------------|----------|
| 1 | Shared SwiGLU QMV gate/up halving | ~2.43 MiB | Primary decode | LOW-MEDIUM (code already built by PR #180) | **HIGH** |
| 2 | Gate-softplus 4× scale/bias dedup | ~450 KiB | Primary decode | MEDIUM | **MEDIUM** |
| 3 | Indexed LUT for standalone g_proj | Unknown | Primary decode | MEDIUM-HIGH | LOW-MEDIUM |
| 4 | Standalone shared down halving | ~1.22 MiB | Fallback decode | LOW | LOW |
| 5 | Non-R1 packed kernels halving | — | Fallback decode | LOW-MEDIUM | LOW |
| 6 | Routed down reduce halving | — | Fallback decode | LOW | LOW |
| 7 | Raw (non-packed) kernels halving | — | Fallback decode | MEDIUM | LOW |

---

## Key Recommendation

**Opportunity 1 (Shared SwiGLU QMV halving)** is the highest-value, lowest-cost
remaining opportunity. PR #180 already builds the halved scale tensors
(`_halvedFusedGateUpScales`, `_fusedGateUpScalesEscape`) at load time but never
wires them into the kernel. Completing the wiring requires:
1. Modifying the `lagunaSharedSwiGLUQMVRows1Kernel` source: `scale_row_bytes`
   128→64, scale pointer `lane`→`lane/2`, add escape byte input.
2. Adding `gateUpEscape` parameter to `lagunaSharedSwiGLUQMV`.
3. Changing `fusedSharedDownInputs` to pass the halved tensors.

This can be folded into PR #180's revision (the halved tensors already exist)
or done as a separate follow-up. Estimated savings: ~2.43 MiB/step, all 39
sparse layers, bit-exact, on the primary scored decode path.

**Opportunity 2 (Gate-softplus 4× dedup)** is the next most promising.
It targets a different mechanism (redundant device loads, not halving) on a
different kernel (affine INT8 group-32, not NVFP4 group-16). It is independent
of PRs #169 and #180 and composable with them. Estimated savings: ~450 KiB/step.
