# Pre-NAX MoE Layout Troubleshooting

## Invariant

The fused sorted-prefill MoE gate/up call has two output contracts:

- The expert-aligned NAX kernel applies rounded-BF16 SwiGLU and packs the
  512-wide activation into the first half of a nominal 1024-wide allocation.
- The generic kernel returns the full interleaved 1024-wide projection. Swift
  must deinterleave it and run `lagunaInterleavedSwiGLU`.

Swift may use the packed interpretation only when the backend selects the
expert-aligned NAX path. Treat dispatch and layout interpretation as one
invariant.

## Selection boundary

`lagunaExpertAlignedGatherEnabled` covers the dynamic conditions relevant to
the Laguna call: the feature flag, NAX hardware/OS support, and the shipped
stage-4 tiling. The call site supplies the remaining assumptions: sorted
prefill with at least 64 indices, NVFP4, transpose, group size 16, 4-bit
weights, no bias, and Laguna gate/up shapes.

The backend first requires `metal::is_nax_available()`. Within its NAX gather
path, `expert_aligned` also checks the feature flag, mode, transpose, group and
bit sizes, Laguna shape, minimum row count, alignment, and `bm=64`, `wm=4`,
`wn=2`. Do not describe the Swift predicate as a complete copy of the backend
predicate outside these call-site assumptions.

Relevant sources:

- `Sources/MLXFastModel/LagunaRuntimeModel.swift`: Swift selection and view.
- `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp`: backend
  `expert_aligned` selection.
- `Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized_nax.cpp`:
  runtime-effective JIT kernel source. Keep it aligned with
  `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized_nax.h`.
- `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp`:
  `metal::is_nax_available()` for diagnosis only; this file is not editable in
  a submission.

## Diagnose corruption

1. Record the Metal architecture, macOS version, and
   `MLX_METAL_GPU_ARCH`, `DARKBLOOM_EXPERT_ALIGNED_GATHER`, and
   `DARKBLOOM_STAGE_BM128` values.
2. Check whether backend NAX and `expert_aligned` selection agree with Swift's
   packed-layout decision under the call-site assumptions above.
3. Set `DARKBLOOM_EXPERT_ALIGNED_GATHER=0` only as an ablation. Recovery points
   to this boundary; the override is not the fix.
4. Verify that `DARKBLOOM_STAGE_BM128` is unset, empty, or `4` before using the
   packed interpretation.
5. Rerun public correctness and the risk-based checks in
   `quality-evaluation.md` after any dispatch or layout change.

Gross corruption, repetition, or collapsed PPL is consistent with a layout
mismatch. Ordinary cross-generation near-tie drift is not.
