# Pre-NAX MoE Layout Troubleshooting

## TL;DR

The fused sorted prefill MoE gate/up operation has two output layouts. The NAX
kernel returns an already-activated packed view; the generic kernel returns a
full interleaved projection that Swift must reconstruct and activate. If MLX
selects the generic kernel while Swift assumes the packed layout, logits are
severely corrupted.

Commit `2225854` fixed this by making Swift's view selection use the same
complete capability and tiling predicate as backend dispatch. Keep those two
decisions coupled.

## Output contracts

- **NAX expert-aligned path:** applies rounded-BF16 SwiGLU and packs the
  512-wide activation into the first half of a nominal 1024-wide allocation.
- **Generic pre-NAX path:** returns the full 1024-wide, 32-row gate/up-
  interleaved projection. Swift must deinterleave it and evaluate
  `SiLU(gate) * up` with `lagunaInterleavedSwiGLU`.

The historical bug used the default-on `DARKBLOOM_EXPERT_ALIGNED_GATHER` flag
as sufficient evidence for the packed interpretation. MLX independently
refused the NAX kernel when the hardware, OS, or tiling was unsupported. Swift
could therefore slice the first half of a generic result as though it were an
activated packed result.

## Correct dispatch predicate

The packed interpretation is valid only when all of the following are true:

- `DARKBLOOM_EXPERT_ALIGNED_GATHER` is not `0`;
- macOS is 26.2 or newer;
- the Metal architecture is generation 17 or newer for an `s` suffix, or
  generation 18 or newer for a `p` suffix; and
- `DARKBLOOM_STAGE_BM128` is unset, empty, or `4`.

Otherwise use the generic 1024-wide reconstruction path.
`DARKBLOOM_EXPERT_ALIGNED_GATHER=0` is a useful diagnostic ablation, but a
correct runtime does not require it on pre-NAX hosts.

The relevant code is split across:

- `Sources/MLXFastModel/LagunaRuntimeModel.swift` for the Swift predicate and
  view selection;
- the vendored MLX `device.cpp`, `quantized.cpp`, and `fp_quantized_nax.h`
  files for capability and kernel selection.

## Symptoms

This mismatch is gross corruption, not ordinary cross-generation near-tie
drift. The original reproduction showed PPL `262.0863`, repetitive or
unfinished generations, and zero correct answers across the small downstream
panel. After the dispatch/layout fix, the same host reached PPL `13.9549` and
nonzero downstream accuracy.

A separate evaluator issue capped full-head answers at 256 tokens and could
truncate a reasoning trace. It compounded the visible symptoms but did not
cause or repair the corrupted logits. The current quality runner uses its
documented longer limits and treats cap exhaustion as invalid.

## Inspect the host

Do not classify support from the M4 or M5 marketing name alone. Inspect the
Metal architecture and relevant overrides:

```bash
system_profiler SPHardwareDataType SPSoftwareDataType \
  -detailLevel mini |
  rg 'Model Name|Model Identifier|Chip:|Total Number of Cores|Memory:|System Version|Kernel Version'

swift -module-cache-path /tmp/mlxfast-swift-module-cache -e \
  'import Metal; if let d = MTLCreateSystemDefaultDevice() { print(d.name); if #available(macOS 14.0, *) { print(d.architecture.name) } }'

env | rg \
  '^(MLX_METAL_GPU_ARCH|DARKBLOOM_EXPERT_ALIGNED_GATHER|DARKBLOOM_STAGE_BM128)='
```

In this vendored MLX build, `applegpu_g16s` is pre-NAX. An `s` architecture
needs generation 17 or later and a `p` architecture needs generation 18 or
later; both require macOS 26.2 or later. A forced `MLX_METAL_GPU_ARCH` changes
the reported dispatch decision and must not misrepresent the host.

## Troubleshooting procedure

1. Record the exact GPU architecture, macOS version, and all three relevant
   environment overrides.
2. Compare backend NAX eligibility with Swift's packed-layout predicate. A
   disagreement is the first suspect.
3. Set `DARKBLOOM_EXPERT_ALIGNED_GATHER=0` as a diagnostic ablation. Recovery
   strongly implicates the NAX dispatch/layout boundary; it is not the fix.
4. Check `DARKBLOOM_STAGE_BM128`. Only unset, empty, or `4` is compatible with
   the packed interpretation described above.
5. Re-run the public correctness path and, when numerical or layout behavior
   changed, the risk-based checks in `quality-evaluation.md`.
6. Rebaseline after changing the GPU generation, OS, overrides, or dispatch
   contract. Cross-host absolute timings are not comparable.

Any change to NAX availability, MoE tiling, packing, output strides, or view
selection must update both backend and Swift predicates. Add or adjust
supporting tests in `Tests/MLXFastTests/LagunaCorrectnessTests.swift`; those
tests may accompany a research PR but are not part of the submitted
`editablePaths` candidate.

## Original reproduction host

| Field | Value | Relevance |
| --- | --- | --- |
| Mac | MacBook Pro `Mac16,6` | Reproduction host |
| SoC / GPU | Apple M4 Max, 40 GPU cores | Hardware family |
| Metal architecture | `applegpu_g16s` | Causal: generation 16 is pre-NAX |
| Unified memory | 128 GB | Reproduction context, not the predicate |
| OS | macOS 26.5.2 (`25F84`), Darwin 25.5.0 | Passed the OS requirement |
| Toolchain | Xcode 26.6 (`17F113`), Swift 6.3.3, arm64 | Reproduction context |
| Relevant overrides | All unset | Exercised default dispatch |
