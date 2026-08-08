## M5 Correctness Audit V4 — Decode-Path Kernel Source String Differences

**Date**: 2026-08-08
**Organizer frontier**: commit `bca94c5` (passes M5, score 2.5213)
**Our code**: commit `cecdc1ef` (fails M5)
**Scope**: Compare Metal kernel source strings in the 3 editable files that differ:
`Sources/MLXFastModel/LagunaRuntimeModel.swift`, `LagunaLmHeadPrune.swift`, `LagunaRuntimeWeights.swift`

---

## Executive Summary

Our code REWROTE many decode-path kernels with fundamentally different
implementations. The most critical differences are NOT in the Metal source
strings themselves, but in **which kernels are dispatched** during decode.
The current code removed several organizer flags and replaced their code
paths, causing the decode forward pass to take completely different code
paths that produce different FP arithmetic.

**Root cause hypothesis**: The current code assumed all QKV and OProj layers
use NVFP4 quantization, but the organizer's default (`DARKBLOOM_NATIVE_AFFINE_NVFP4`
unset → `lagunaNativeAffineNVFP4From = nil`) means these layers use **INT8 affine**
quantization. The current code removed the INT8 affine kernel paths, causing
guards to fail and fall through to stock `quantizedMM`, which produces different
FP results than the organizer's fused INT8 affine kernels.

---

## Priority 1 (CRITICAL) — Decode-path kernel DISPATCH differences

### 1.1 QKV projection: Fused INT8 affine vs stock quantizedMM

**Impact**: Decode path (75% of score), EVERY layer, token-affecting
**File**: `LagunaRuntimeModel.swift`

**Organizer** (`bca94c5`, lines 5699-5730):
- Checks `lagunaFusedNormAffineQKVEnabled` (default ON)
- If `fusedAffine.mode == .affine, .bits == 8, .groupSize == 32` → calls
  `lagunaNormAffineQKV()` (fused RMSNorm + INT8 affine QKV in ONE kernel)
- Kernel: `lagunaNormAffineQKVBody` (lines 4873-4986) does RMSNorm + affine
  matmul in one dispatch with specific FP accumulation order
- Falls back to `lagunaDecodeNVFP4QKVR1` (NVFP4 tail) if affine fails
- Falls back to `quantizedMM` if NVFP4 also fails

**Current** (`cecdc1ef`, lines 3661-3695):
- Comment says "norm+affine QKV fusion was removed: all QKV layers use NVFP4"
- This assumption is WRONG: `lagunaNativeAffineNVFP4From = nil` means INT8 affine
- `lagunaFusedGProjQKV` guard requires `bank.mode == .nvfp4` → FAILS (bank is .affine)
- `decodeNVFP4QKVR1` is hardcoded to `nil` (line 3685)
- Falls through to stock `quantizedMM` (separate norm dispatch + stock MLX matmul)

**FP difference**:
- Organizer: RMSNorm computed inside the kernel, `float(bfloat(float(residual[column+i]) * laguna_inv_mean))` rounding per element, then affine matmul with `scale * accum + sum * bias` accumulation
- Current: RMSNorm computed by separate `inputNorm(input)` dispatch (MLX standard), then `quantizedMM` with MLX's own accumulation order
- Different rounding boundaries and accumulation order → ULP differences accumulate over 128 decode steps

**Revert needed**: Restore `lagunaNormAffineQKV` function and its kernel definitions
from `bca94c5` (lines 4843-5295). Restore the dispatch at lines 5699-5730.

### 1.2 OProj: Fused INT8 affine gated vs stock quantizedMM

**Impact**: Decode path (75% of score), EVERY layer, token-affecting
**File**: `LagunaRuntimeModel.swift`

**Organizer** (`bca94c5`, lines 6095-6165):
- Primary path: `lagunaGatedAffineOProj` with `affineWO.mode == .affine, .bits == 8, .groupSize == 32`
- This is an INT8 affine fused kernel that does softplus + gate multiply + matmul in ONE dispatch
- Gate applied as `float(bfloat(float(v)*g))` per element INSIDE the kernel
- Falls back to `lagunaGatedAffineOProjNVFP4` if mode is .nvfp4

**Current** (`cecdc1ef`, lines 4054-4095):
- Only checks `affineWO.mode == .nvfp4` → FAILS (weights are INT8 affine)
- Falls back to stock: `lagunaCompiledSoftplusGate` (separate) → `output * gate` (separate BF16 broadcast) → `quantizedMM` (separate)

**FP difference**:
- Organizer: Gate multiply happens at FP32 inside the kernel: `x_thread[i] = float(bfloat(float(xp[i]) * g))` — single BF16 rounding
- Current: Gate multiply happens as separate MLX BF16 broadcast op, then `quantizedMM` reads the gated result
- The BF16 rounding boundary is at a different point in the computation

**Revert needed**: Restore `lagunaGatedAffineOProj` function and `lagunaGatedAffineOProjSource`
from `bca94c5` (lines 3946-4200). Restore the dispatch at lines 6095-6165.

### 1.3 Router precomputed keys removed

**Impact**: Decode path (75% of score), EVERY sparse layer, expert selection
**File**: `LagunaRuntimeModel.swift`

**Organizer** (`bca94c5`):
- `lagunaRouterPrecomputedKeysEnabled` defaults to ON (line 157)
- RMSNorm+router kernel produces `router_keys` output (sigmoid + correction_bias → ordinal)
- MoE kernel `lagunaRoutedSwiGLUQMVPackedTop8R1Kernel` consumes `router_keys` as input
- Uses `lagunaRouterTop8PrecomputedPrelude` to extract winning expert from precomputed keys

**Current** (`cecdc1ef`):
- `lagunaRouterPrecomputedKeysEnabled` REMOVED
- RMSNorm+router kernel does NOT produce `router_keys`
- Comment (line 158): "No kernel ever consumed router_keys as input — it was only used as a nil-check guard"
- This is WRONG: the organizer's MoE kernel DOES consume `router_keys` (line 7480)
- Current uses separate `lagunaDecodeRouterTop8` kernel + passes `indices` to MoE

**FP difference**: The routing selection is done differently (precomputed keys
inside MoE kernel vs separate router kernel), but the expert selection should
be the same if both use the same sigmoid + correction_bias + tournament sort.
However, the MoE kernel itself is different (see 1.4), and the routing key
computation happens at a different point in the pipeline.

**Revert needed**: Restore `lagunaRouterPrecomputedKeysEnabled` and the
`router_keys` output from `lagunaResidualRMSNormRouterSource`. Restore the
`lagunaRoutedSwiGLUQMVPackedTop8` function that takes `routerKeys` parameter.

---

## Priority 2 (HIGH) — Decode-path kernel SOURCE differences

### 2.1 MoE gate/up kernel rewritten

**Impact**: Decode path (75% of score), EVERY sparse layer, token-affecting
**File**: `LagunaRuntimeModel.swift`

**Organizer** (`bca94c5`, lines 7513-7628):
- `lagunaRoutedSwiGLUQMVPackedTop8R1Kernel` with 8 routed experts only
- Scale layout: `scale_row_bytes = 32`, reads `scale[lane]` (full stride)
- Input load: `const vec<bfloat, 4> values = input_vectors[i]` (vec4 loads)
- Expert selection via precomputed `router_keys` + `laguna_router_top8_extract_round`

**Current** (`cecdc1ef`, lines 4447-4640):
- `lagunaRoutedSwiGLUQMVPackedTop8R1Kernel` with 9 slots (8 routed + 1 shared)
- Scale layout: `r_scale_row_bytes = 16` (HALVED), reads `scale[lane / 2]`
- Input load: `float4 _fv = float4(input_vectors[i])` (different load pattern)
- Expert selection via `indices[expert_slot]` (separate router kernel)
- Includes shared expert in same kernel (fused)
- Has `gate_up_escape` and `shared_escape` for scale correction

**FP differences**:
1. Halved scale stride (16 vs 32) — reads different scale bytes
2. Input load uses `float4()` cast vs `vec<bfloat,4>` member access — same values but different codegen
3. Fuses shared expert into same kernel — different threadgroup count and grid geometry
4. Escape byte mechanism for scale correction — organizer doesn't have this

**Revert needed**: Restore `lagunaRoutedSwiGLUQMVPackedSelectedSource`,
`lagunaRoutedSwiGLUQMVPackedTop8R1Kernel`, and `lagunaRoutedSwiGLUQMVPackedTop8`
from `bca94c5` (lines 7352-7660).

### 2.2 MoE down+shared+residual kernel rewritten

**Impact**: Decode path (75% of score), EVERY sparse layer, token-affecting
**File**: `LagunaRuntimeModel.swift`

**Organizer** (`bca94c5`, lines 7946-8018):
- `outputs_per_simd = 1` (one output row per simdgroup)
- `scale_row_bytes = 32` (full scale stride)
- Scale read: `expert_scales + output_row * scale_row_bytes + lane`
- Input load: `const vec<bfloat, 4> values = input_vectors[i]` (vec4 member access)
- No escape byte mechanism

**Current** (`cecdc1ef`, lines 4644-4808):
- `outputs_per_simd = 8` (eight output rows per simdgroup)
- `scale_row_bytes = 16` (HALVED)
- Scale read: `expert_scales + output_row * scale_row_bytes + lane / 2`
- Input load: `float4 _fv = float4(input_vectors[i])` (float4 cast)
- Has `routed_down_escape` and `shared_down_escape` inputs
- Escape byte: `if (output_row == 0 && lane == 1) sb = escape_val`

**FP differences**:
1. `outputs_per_simd = 8` vs 1 — completely different simd_sum reduction scope
2. Halved scale stride — reads different scale bytes
3. Escape byte correction — organizer doesn't have this

**Revert needed**: Restore `lagunaRoutedSharedDownResidualKernel` from `bca94c5`.

### 2.3 OProj NVFP4 kernel rewritten (even if not dispatched)

**Impact**: Would affect NVFP4 OProj layers if they existed, but current
weights are INT8 affine so this kernel is NOT dispatched
**File**: `LagunaRuntimeModel.swift`

**Organizer** (`bca94c5`, lines 4218-4404):
- `results_per_simdgroup = 4`
- Input load: `vec<bfloat,4>` with `#pragma unroll` and per-element `float(bfloat(float(v)*g))`
- Code load: `const uint2 cw = *(const device uint2*)wl` (uint2 paired load)
- simd_sum: packed `vec<float,4> simd_sum(...)` (one call for 4 results)

**Current** (`cecdc1ef`, lines 2670-2847):
- `results_per_simdgroup = 8`
- Input load: simple loop `for(uint i=0;i<values_per_thread;++i) x_thread[i]=float(bfloat(float(xp[i])*g))`
- Code load: `wl[j]` (sequential uint loads)
- simd_sum: 8 separate `simd_sum` calls
- Has `halvedScales` parameter and escape byte mechanism

**FP differences** (if this kernel were dispatched):
1. Different `results_per_simdgroup` → different grid/threadgroup geometry → different simd_sum scope
2. Different input load pattern (unrolled vec4 vs simple loop)
3. Different code load pattern (uint2 paired vs sequential)
4. Different simd_sum (packed vec4 vs 8 separate calls)
5. Halved scales with escape bytes

**Revert needed**: Restore `lagunaGatedAffineOProjNVFP4Source` from `bca94c5`.

### 2.4 QKV NVFP4 kernel rewritten (even if not dispatched)

**Impact**: Would affect NVFP4 QKV layers, but current weights are INT8 affine
so this kernel is NOT dispatched (guard fails, falls to stock quantizedMM)
**File**: `LagunaRuntimeModel.swift`

**Organizer** (`bca94c5`, lines 4725-4764):
- Simple QKV-only kernel: reads from `normalized`, uses `laguna_tail_nvfp4_qdot`
- No g_proj fusion, no halved scales, no escape bytes
- `scale_stride = block_size / 16`

**Current** (`cecdc1ef`, lines 3108-3241):
- Function with `halvedScales` and `withGProj` parameters
- Fuses g_proj into extra threadgroups
- Has escape byte mechanism
- `scale_stride = block_size / 32` when halved
- g_proj branch uses `simd_shuffle` for scale/bias broadcast

**FP differences** (if dispatched):
1. Halved scale stride
2. g_proj fusion changes threadgroup count and grid geometry
3. `simd_shuffle` broadcast for scale/bias
4. Escape byte correction

**Revert needed**: Restore organizer's `lagunaDecodeNVFP4QKVR1Source` and
`lagunaDecodeNVFP4QKVR1` dispatch from `bca94c5`.

### 2.5 g_proj (gate softplus) kernel rewritten

**Impact**: Decode path, every attention layer, token-affecting
**File**: `LagunaRuntimeModel.swift`

**Organizer** (`bca94c5`, lines 4428-4471):
- Separate `lagunaGateSoftplusSource` kernel
- `R=4` (4 output rows per simdgroup), `NS=2` simdgroups → 8 rows per threadgroup
- Uses separate `scales` and `biases` arrays
- `sc = scales + orow*KG + lane/SS`
- `bs = biases + orow*KG + lane/SS`

**Current** (`cecdc1ef`, lines 3144-3185):
- Fused into QKV kernel's g_proj branch
- 1 row per simdgroup (different from 4)
- Uses `gproj_metadata` (interleaved scales+biases: `gpm[0]=scale, gpm[1]=bias`)
- `simd_shuffle` broadcast for scale/bias within sub-group

**FP differences**:
1. Different rows-per-simdgroup (4 vs 1) → different simd_sum scope
2. Interleaved metadata vs separate scales/biases — same values but different access pattern
3. `simd_shuffle` broadcast — organizer reads directly from `sc[row*KG]` and `bs[row*KG]`

**Note**: This kernel is NOT dispatched in current code because
`lagunaFusedGProjQKV` fails the `bank.mode == .nvfp4` guard. The g_proj
is instead computed by stock `quantizedMM` + separate `softplus`.

**Revert needed**: Restore `lagunaGateSoftplusSource` and its dispatch from `bca94c5`.

---

## Priority 3 (MEDIUM) — LM Head differences

### 3.1 LM Head int5 coarse kernel — mode 0 numerically equivalent

**File**: `LagunaLmHeadPrune.swift`

**Finding**: The int5 coarse kernel in mode 0 is **numerically equivalent**
to the organizer's `lagunaLmHeadInt5CoarseRatioBoundDeltaBF16Kernel`:

- Organizer decode: `float4 ve = float4(ne | (he << 4u)) - 16.0f` (bit 4 = MSB)
- Current mode 0: `float4 ve = float4((ne << 1u) | he) - 16.0f` (bit 0 = LSB)
- Both reconstruct the same `u` value because `buildInt5Planes` encodes them
  consistently (organizer: `lo = u & 0xF, hi = (u >> 4) & 1`; current: `lo = u >> 1, hi = u & 1`)
- Delta accumulation: both use `d_acc += (0.5f * sd) * ag` in mode 0
- Bound multiplier: both use `61.0f * GAMMA` in mode 0

**Verdict**: Mode 0 is FP-equivalent. No action needed.

### 3.2 LM Head exact kernel — mode 0 GEMV equivalent

**File**: `LagunaLmHeadPrune.swift`

**Finding**: The current code's mode 0 path in `lagunaLmHeadExactKernel`
is a **byte-for-byte replica** of the organizer's `lagunaLmHeadInlineExactDeltaBF16Kernel`
GEMV section. The stock `gemv_al` replica code is identical.

**Verdict**: Mode 0 GEMV is FP-equivalent. No action needed.

### 3.3 LM Head threshold kernel — equivalent

The threshold kernel is identical when `lagunaLmHeadBF16MidpointThresholdEnabled`
is ON (default in both). The organizer has a conditional for predecessor
threshold; the current always uses midpoint. Since both default to midpoint,
they're equivalent.

### 3.4 LM Head argmax stage1 kernel — identical

No differences found.

---

## Priority 4 (LOW) — Non-FP differences

### 4.1 RMSNorm router loop interchange

**File**: `LagunaRuntimeModel.swift`, `lagunaResidualRMSNormRouterSource`

**Organizer**: Delta loop interleaves across rows:
```
for (ushort delta = 16; delta >= 1; delta >>= 1) {
    for (uint r = 0; r < rows_per_thread; ++r) {
```

**Current**: Delta loop processes each row fully before next:
```
for (uint r = 0; r < rows_per_thread; ++r) {
    for (ushort delta = 16; delta >= 1; delta >>= 1) {
```

**FP impact**: The tournament sort's comparison results are the same
regardless of loop order (each pair comparison is independent). This
should not change FP results. The comment in the organizer confirms:
"each row's delta sequence (16,8,4,2,1) and += order are unchanged."

### 4.2 Warmup sequence differences

**File**: `LagunaRuntimeWeights.swift`

The current code runs 3 decode warmup steps instead of 1, and removes
`lagunaWarmSlidingFusedAttentionKernel()` and `lagunaWarmDecodeQKVR1Kernels()`
calls. This affects JIT compilation timing but not FP results.

### 4.3 Attention kernels — identical

Both `lagunaSlidingFusedAttentionKernel` and `lagunaFullFusedAttentionKernel`
source strings are **byte-for-byte identical** between organizer and current.

### 4.4 TailNVFP4 helpers — identical

`lagunaTailNVFP4ScaleDecodeSource`, `lagunaTailNVFP4QDotAccumDeclSource`,
`lagunaTailNVFP4QDotFirstGroupSource`, `lagunaTailNVFP4RowScaleSuffixSource`
are all identical.

---

## Missing DARKBLOOM flags

Flags present in organizer but REMOVED from current code:

| Flag | Default | Impact |
|------|---------|--------|
| `DARKBLOOM_FUSED_NORM_AFFINE_QKV` | ON | **CRITICAL**: Controls fused INT8 affine QKV kernel. Current code removed the entire path. |
| `DARKBLOOM_ROUTER_PRECOMPUTED_KEYS` | ON | **CRITICAL**: Controls router_keys output. Current removed it. |
| `DARKBLOOM_ROUTED_GATEUP_R1` | ON | Controls R1 retile for gate/up. Current rewrote kernel entirely. |
| `DARKBLOOM_SHARED_QMV_R1` | ON | Controls R1 retile for shared expert. Current rewrote kernel. |
| `DARKBLOOM_QMV_R1` | ON | Controls R1 QMV. Current rewrote QKV kernel. |
| `DARKBLOOM_FUSED_GATED_OUTPUT` | ON | Controls fused gated output projection. Current removed INT8 path. |
| `DARKBLOOM_FUSED_GATE_PRODUCT` | ON | Controls deferred gate activation. Current changed gate path. |
| `DARKBLOOM_ROUTER_ORDINAL_SCORE_TABLE` | (testing) | Score table variant. Current always uses it. |
| `DARKBLOOM_SEED_ELIDE_RESIDUAL` | ON | Seed elision in RMSNorm. Current may have different default. |
| `DARKBLOOM_SHARED_FIRST_DOWN` | ON | Shared-first input order for down kernel. Current removed. |

New flags in current not in organizer:
| Flag | Default | Impact |
|------|---------|--------|
| `DARKBLOOM_OPROJ_SCALE_HALVING` | ON | Halved scale stride for OProj — changes scale reads |
| `DARKBLOOM_FULL_PARAMS_ATLAS` | (new) | Parameter atlas variant |
| `DARKBLOOM_PREFILL_FUSED_GATE_UP_HALVED` | (new) | Halved gate/up for prefill |

---

## Recommended Revert Strategy

The cleanest fix is to **restore the three editable files from `bca94c5`**
(organizer frontier) and then re-apply only the changes that are known to be
FP-safe (warmup sequence, etc.). This is because the current code has
intertwined changes across multiple kernel systems:

1. **QKV projection**: Restore `lagunaNormAffineQKV` and INT8 affine fused path
2. **OProj**: Restore `lagunaGatedAffineOProj` and INT8 affine gated path
3. **Router**: Restore `lagunaRouterPrecomputedKeysEnabled` and router_keys
4. **MoE gate/up**: Restore `lagunaRoutedSwiGLUQMVPackedSelectedSource` and Top8 with router_keys
5. **MoE down**: Restore `lagunaRoutedSharedDownResidualKernel` with `outputs_per_simd=1`
6. **g_proj**: Restore `lagunaGateSoftplusSource` as separate kernel
7. **QKV NVFP4**: Restore organizer's simple `lagunaDecodeNVFP4QKVR1Source`
8. **OProj NVFP4**: Restore organizer's `lagunaGatedAffineOProjNVFP4Source` with `results_per_simdgroup=4`

If a full file revert is too large, the minimum set of changes to fix M5
correctness (in priority order):

1. Restore `lagunaNormAffineQKV` dispatch (QKV uses fused INT8 affine, not stock quantizedMM)
2. Restore `lagunaGatedAffineOProj` dispatch (OProj uses fused INT8 affine gated, not stock)
3. Restore `lagunaRouterPrecomputedKeysEnabled` and router_keys flow
4. Restore organizer's MoE gate/up and down kernels (with precomputed keys input)
5. Restore `lagunaGateSoftplusSource` as separate g_proj kernel

---

## Verification

To verify the fix:
1. Build with `./benchmark.sh --local-iterate`
2. Run `research/run_upstream_equivalence.sh` to check against the oracle
3. Compare decode tokens against the organizer's output for the same prompt
4. Run local benchmark and compare seconds/token against organizer baseline
