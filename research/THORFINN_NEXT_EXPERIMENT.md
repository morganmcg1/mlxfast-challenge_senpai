# Thorfinn Next Experiment: Prefill MoE Gather-QMM Scale Halving

## Recommendation

**Apply the NVFP4 pairwise-constancy scale halving to the prefill MoE
gather-QMM path** (`fp_gather_qmm_rhs_expert_nax` kernel). PRs #169 and #180
halve scales only in the DECODE custom kernels. The PREFILL MoE gather-QMM
still loads FULL (unhalved) uint8 E4M3 scales, wasting ~29 MiB/step of
prefill bandwidth. This experiment ports the proven decode halving mechanism
to the prefill kernel's `QuantizedBlockLoader`.

## Why This Is the Right Experiment

### Untouched cost center

| Work | Cost center | Component |
|------|------------|-----------|
| PR #169 (Askeladd) | DECODE QKV+O-proj scale halving | Decode 75% |
| PR #180 (Alphonse) | DECODE MoE scale halving (revision) | Decode 75% |
| PR #186 (Edward) | Fence overhead (MLX_METAL_FAST_SYNCH) | Decode 75% |
| QHOIST (validating) | PREFILL attention Q-fragment hoist | Prefill 25% |
| BM128 v4 (merged) | PREFILL MoE gather-QMM tiling | Prefill 25% |
| **This experiment** | **PREFILL MoE gather-QMM scale bandwidth** | **Prefill 25%** |

PR #180 halves decode MoE scales in the custom decode kernels
(`lagunaRoutedSwiGLUQMVPackedTop8R1Kernel`, `lagunaRoutedSharedDownResidualKernel`).
The PREFILL MoE path uses a COMPLETELY DIFFERENT kernel
(`fp_gather_qmm_rhs_expert_nax` in `fp_quantized_nax.h`) that has NOT been
touched by any scale halving PR. This is a genuinely different code path.

### Dead experiments ruled out

- STAGE2_GATHER v2 (PR #40): both variants tested, within-noise losses. DEAD.
- DARKBLOOM_STATIC_NVFP4_SHAPES: already default ON (barrier elision harvested
  in commit 6ca0c71, scored 2.51686). No further gain.
- Instruction-count reductions (dot4, simd_sum, float4): all rejected on M5.
- BSEARCH_HOIST: with egroups=256, saves only 1 barrier/TG. Minimal.

### Thorfinn has the right expertise

Thorfinn just completed BM128 v4 (prefill MoE gather-QMM tiling). He is
familiar with the `gather_qmm_rhs_nax` dispatch, the expert-aligned path,
and the `fp_quantized_nax.h` kernel. This experiment builds on that work.

## Exact Files, Line Numbers, and Proposed Changes

### 1. Kernel: `fp_quantized_nax.h` — QuantizedBlockLoader scale halving

The `QuantizedBlockLoader` (L210–257) computes the scale pointer in its
constructor:

```cpp
// L257 (current):
scales(scales_ + bi * src_ld / group_size + group_id)
```

And reads scales in `stage()` (L274) and `commit()` (L454, L461):

```cpp
// L274 (current):
const float scale = fp4nv_scale_x16384(scales[i]);
```

**Proposed change:** Add a `bool kHalvedScales` template parameter to the
`QuantizedBlockLoader` struct. When `kHalvedScales = true`:

```cpp
// Constructor: halve the row stride and group index
scales(scales_ + bi * src_ld / (group_size * 2) + group_id / 2)

// stage(): read halved scales (pairwise-constancy: scale[2k]==scale[2k+1])
const float scale = fp4nv_scale_x16384(scales[i / 2]);
```

When `kHalvedScales = false`, keep the stock indexing (no change).

The escape byte (scale[0] vs scale[1] for row 0) is handled by passing the
escape as a separate small buffer and checking `group_id == 0 && i == 1`.
In practice, the escape affects only 2 bytes across the full expert scale
tensor (see bandwidth audit L70: "gate row 0 byte 1, up row 512 byte 1"),
so the conditional is cheap.

### 2. Kernel: `fp_quantized_nax.h` — Expert kernel template

At L1718–1726, the loader is instantiated:

```cpp
using loader_w_t = QuantizedBlockLoader<
    Wtype, BN, BK, BK_padded, true,
    WM * WN * SIMD_SIZE, group_size, bits>;
```

**Proposed change:** Add `kHalvedScales` as a new template parameter and
pass it through:

```cpp
using loader_w_t = QuantizedBlockLoader<
    Wtype, BN, BK, BK_padded, true,
    WM * WN * SIMD_SIZE, group_size, bits, kHalvedScales>;
```

Where `kHalvedScales` is a new template parameter on the
`fp_gather_qmm_rhs_expert_nax` kernel function.

### 3. Kernel: `fp_quantized_nax.h` — Scale stride

At L1755–1763:

```cpp
const int K_g = kernel_K / group_size;
const size_t stride_s = size_t(kernel_N) * K_g;
const device uint8_t* scale_base = scales + size_t(y_col) * K_g;
```

**Proposed change:** When `kHalvedScales`:

```cpp
const int K_g = kernel_K / (group_size * (kHalvedScales ? 2 : 1));
const size_t stride_s = size_t(kernel_N) * K_g;
const device uint8_t* scale_base = scales + size_t(y_col) * K_g;
```

### 4. Dispatch: `quantized.cpp` — Pass halved scales

In `gather_qmm_rhs_nax` (L1958–1967), add a `halved_scales` parameter and
pass the halved scale array + escape buffer. Gate on `expert_aligned &&
!biases_.has_value() && mode == "nvfp4"`.

### 5. Generated twin: `fp_quantized_nax.cpp`

Apply identical changes to the generated twin to keep JIT source consistent
(AGENTS.md requirement).

### 6. Swift: `LagunaRuntimeModel.swift` — Prepare halved prefill scales

At model init, prepare halved scale tensors for the prefill fused gate/up
and down paths. This mirrors PR #180's `_halvedFusedGateUpScales` /
`_halvedRoutedDownScales` preparation, but for the standard (non-packed)
scale layout used by `gatherQuantizedMM`.

## Bit-Exactness Proof

The NVFP4 pairwise-constancy invariant (verified in
`research/BANDWIDTH_AUDIT_20260807.md` L69 and PR #180's implementation)
guarantees: for every scale row, `scale[2k] == scale[2k+1]` for all k ≥ 1.

With halved indexing `scales[i / 2]`:
- `i = 0` → `scales[0]` = `scale[0]` ✓ (original `scales[0]`)
- `i = 1` → `scales[0]` = `scale[0]` = `scale[1]` ✓ (pairwise-constancy)
- `i = 2` → `scales[1]` = `scale[2]` ✓
- `i = 3` → `scales[1]` = `scale[2]` = `scale[3]` ✓
- General: `i = 2k` → `scales[k]` = `scale[2k]` ✓
- General: `i = 2k+1` → `scales[k]` = `scale[2k]` = `scale[2k+1]` ✓

The escape byte handles `i = 1` for row 0 only (where `scale[0] ≠ scale[1]`
is possible). For all other rows and all other `i`, the halved index gives
the identical value.

No float arithmetic is reassociated or rerounded. The same scale value is
multiplied with the same decoded code bytes in the same order. This is the
exact same bit-exactness argument that PR #180 uses for the decode kernels.

## Estimated M5 Gain

**Plausible: ~4–6% prefill, ~1.0–1.5% composite.**

**IMPORTANT**: Unlike decode (which loads only top-8 experts per step),
prefill loads ALL 256 experts' weights (each expert's weight is loaded once
and reused for all assigned tokens). With 512 tokens × top-8 = 4096 pairs
spread over 256 experts, virtually all 256 experts are active.

Scale traffic per prefill (39 sparse MoE layers, all 256 experts active):

| Projection | Scales/expert | Scales/layer (256 exp) | Total (39 layers) |
|-----------|--------------|----------------------|-------------------|
| Routed gate/up | 1024 × 128 B = 128 KiB | 32 MiB | 1,248 MiB |
| Routed down | 2048 × 32 B = 64 KiB | 16 MiB | 624 MiB |
| **Total** | **192 KiB** | **48 MiB** | **~1,872 MiB** |

Halved savings: **~936 MiB** (half of 1,872 MiB).

At M5's 651.8 GB/s: 936 MiB / 651.8 GB/s ≈ **1.44 ms** saved per prefill.

For context, total MoE weight codes (all 256 experts × 39 layers):
256 × 39 × 1.5 MiB = ~15 GiB, taking ~24 ms at 651.8 GB/s.
Scale traffic (1.83 GiB) is ~11% of total MoE weight bandwidth.

If prefill total ≈ 25–30 ms (bandwidth-dominated): 1.44 / 27.5 ≈ **5.2%
prefill gain** → **~1.3% composite score gain** (prefill is 25% of score).

This is well above the >1% prefill threshold. Decode is flat (the prefill
gather-QMM kernel does not run during decode).

## Implementation Complexity

**~60–75 lines changed** across 4 files:

| File | Change | Est. lines |
|------|--------|-----------|
| `fp_quantized_nax.h` | Add `kHalvedScales` template param, modify loader constructor + `stage()` + `commit()` | ~25 |
| `fp_quantized_nax.cpp` (generated twin) | Same changes | ~25 |
| `quantized.cpp` | Pass halved scales + escape in dispatch, set template param | ~10 |
| `LagunaRuntimeModel.swift` | Prepare halved prefill scale tensors at init | ~15 |

This is more complex than a 1-line env-var change, but the mechanism is
PROVEN by PR #180 (which does the identical halving for decode). The
implementation pattern is directly transferable.

## Submitted Paths

| Path | In editablePaths? | Change |
|------|-----------------|--------|
| `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized_nax.h` | YES | Kernel loader halving |
| `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized_nax.cpp` | YES | Generated twin (identical) |
| `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp` | YES | Dispatch + template param |
| `Sources/MLXFastModel/LagunaRuntimeModel.swift` | YES | Halved scale prep at init |

All four files are in `benchmark.json`'s `editablePaths`.

## Verification Plan

1. Build: `./benchmark.sh --local-iterate` (scored worker build path).
2. Correctness: Run `research/run_upstream_equivalence.sh` — must show 0.0
   decode diff and identical prefill max_abs_error.
3. M4 timing: ABBA pairs. M4 Pro does NOT select `_nax` expert kernels
   (GPU gen 16 < 17), so M4 may show NO signal. Record kernel reachability
   and architecture.
4. M5 submission: If correctness passes, submit via
   `mlxfast submit --model "senpai"`.

## Key Risk

The QuantizedBlockLoader is shared between the expert-aligned gather path
and potentially other non-expert paths. The `kHalvedScales` template
parameter ensures the change is gated to the expert kernel only (where
halved scales are prepared). Non-expert instantiations use
`kHalvedScales = false` (stock behavior, byte-identical).

## Alternative Simpler Experiment (Fallback)

If the full prefill scale halving proves too complex for the timeline, a
simpler fallback is to prepare halved scale tensors in Swift and pass them
via `gatherQuantizedMM` with a modified `group_size` parameter (32 instead
of 16), tricking the kernel into reading every other scale. This requires
NO kernel changes but is a hack that may have unintended side effects on
the dequantization. The full template approach is preferred.
