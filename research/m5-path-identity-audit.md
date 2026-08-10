# Ranked M5 path identity audit

## Scope and verdict

- Assignment: PR #659, `cedar-tanjiro-m5-path-identity-audit-20260810`.
- Experiment base: `f3da705e1c7144e1f02f4ad16a18bd5e0d954feb`.
- Audited branch source snapshot: `297bbd87a413af12caf6282c521f6e692c2d0119`.
- Production-source delta from the base: none under `Sources/` or `Vendor/`.
- Frozen scored window: one 512-token prefill, a 512-token teacher-forced seed, and 128 one-token decode steps. This gives 40/40/5120 total layer calls, 10/10/1280 full-attention calls, 30/30/3840 sliding-attention calls, 39/39/4992 sparse-MoE calls, and 1/1/128 dense-layer calls.

**Verdict: NO-GO.** The ranked M5 Max reaches generated NAX sources for regular prefill GEMMs, full-attention prefill, and aligned expert prefill. Every runtime-effective generated/canonical pair inspected is semantically identical after removal of generator scaffolding. The affine `quantized_nax` family is not the default scored Laguna path, and the visibly stale `mlx-generated/metal/fp_quantized_nax.h` mirror has no runtime consumer. Therefore no family satisfies the required conjunction of exact M5 reachability, a real source-identity mismatch, exact semantics, a correction within 8 KiB, and estimated value of at least 18 microseconds/decode token or 2.33 milliseconds/prefill. No correction, build, benchmark, environment change, W&B run, candidate submission, or official submission was performed.

## Selector truth table

Backend NAX selection is in `Vendor/mlx-swift/Source/Cmlx/mlx/device.cpp:913-930`: supported OS, Apple GPU generation at least 17, generation at least 18 for the phone-style `p` suffix, and no `MLX_METAL_NO_NAX` override. The Laguna expert selector in `Sources/MLXFastModel/LagunaRuntimeModel.swift:242-265` independently checks OS/generation and requires aligned expert staging/gather layout; it does not read `MLX_METAL_NO_NAX`.

| Condition | Backend regular/full-attention NAX | Laguna expert prefill NAX | Ranked implication |
|---|---:|---:|---|
| M5 Max, supported OS, defaults | yes | yes when stage/gather checks pass | ranked default |
| generation 17 with `p` suffix | no | no | phone exclusion |
| generation 18 with `p` suffix | yes | yes if layout passes | NAX |
| M4 Pro generation 16 | no | no | local M4 misses ranked NAX |
| unsupported OS | no | no | fallback |
| `MLX_METAL_NO_NAX` set | no | Swift flag may remain true | backend override; not ranked default |
| expert stage/layout unaligned | unaffected | no | expert fallback only |

The ranked contract identifies M5 Max plus supported OS and default environment, so NAX is treated as true. The Swift/backend override asymmetry is a diagnostic caveat, not a source mismatch and not a ranked-default correction.

## Scored family and source-form matrix

The scored model is BF16 attention/dense, NVFP4 sparse experts, hidden size 4096, 40 layers (39 sparse plus dense layer 0), 32 query heads, 8 KV heads, and head dimension 128. `LagunaRuntimeModel.swift` is the scored forward path.

| Scored family | Prefill/seed source on ranked M5 | One-token decode source | NAX/source-identity result |
|---|---|---|---|
| embedding, mask assembly | MLX primitives | MLX primitives | no twin candidate |
| RoPE | AOT metallib | AOT metallib | canonical metallib source, rebuild-bound |
| Q/K/V projections and per-head gate | regular Steel GEMM NAX JIT | native/custom decode paths | generated source registered; pair equal |
| Q/K RMSNorm and YaRN partial rotary | AOT/custom Laguna | AOT/custom Laguna | no generated mismatch |
| full attention (10 layers) | Steel attention NAX JIT | custom Laguna/native SDPA | generated source registered; pair equal |
| sliding attention (30 layers) | custom Laguna JIT | custom Laguna JIT | no generated NAX twin selected |
| attention output projection | regular Steel GEMM NAX JIT | native/custom decode | generated source registered; pair equal |
| residual, router, top-8 routing | MLX/custom Laguna | MLX/custom Laguna | no twin candidate |
| routed expert gate/up | aligned FP/NVFP4 NAX JIT | custom Laguna decode | generated `fp_quantized_nax`; pair equal |
| shared expert gate/up | FP NAX JIT | custom Laguna decode | generated `fp_quantized_nax`; pair equal |
| routed expert down | aligned FP/NVFP4 NAX JIT | custom Laguna decode | generated `fp_quantized_nax`; pair equal |
| shared expert down | FP NAX JIT | custom Laguna decode | generated `fp_quantized_nax`; pair equal |
| dense layer-0 MLP | regular Steel GEMM NAX JIT | native/custom decode | generated source registered; pair equal |
| final RMSNorm | AOT metallib | AOT metallib | canonical metallib source, rebuild-bound |
| LM head | regular Steel GEMM NAX JIT | native GEMV/custom path | generated pair equal for prefill |
| argmax | AOT arg-reduction metallib | AOT arg-reduction metallib | canonical metallib source, rebuild-bound |

The 512-row BF16 matrices meet regular Steel NAX dispatch; full BF16 attention with dimension 128 meets Steel attention NAX dispatch. Sorted sparse prefill stages 4096 rows and satisfies expert-aligned dispatch. One-row decode uses the Laguna/native decode families rather than these generated prefill NAX kernels. Affine `quantized_nax` remains a fallback/default-unreached family here: attention prefill is BF16 Steel, attention decode uses native group-32/custom paths, and MoE uses FP/NVFP4 `fp_quantized_nax`.

## Registry and runtime source identity

`Vendor/mlx-swift/Source/Cmlx/mlx/jit_kernels.cpp` supplies the runtime source strings:

- lines 1432-1453: generated Steel attention NAX;
- lines 1227-1304: generated regular GEMM NAX plus FP and affine quantized NAX;
- lines 979-1102: generated Steel fused, gather, split-K, and segmented GEMM NAX.

The corresponding `Vendor/mlx-swift/Source/Cmlx/mlx-generated/*.cpp` files embed Metal as raw strings and are compiled by JIT. Nearby canonical `.metal`/header files are review/edit sources but are not independently compiled for those runtime JIT registrations. By contrast, RoPE, RMSNorm, SDPA-vector, and arg-reduction are AOT metallib families: editing their source requires rebuilding the metallib, so no generated-runtime fork exists in the scored checkout.

## Canonical/generated twin comparison

For each JIT pair, the generated raw string was extracted after its `#line` marker; generator-only wrappers, flattened include transport, blank lines, and comments were excluded. The comparison retained function names, arguments, template parameters, tile constants, layouts, bounds, scale/bias operations, reductions, and stores.

| Canonical family | Runtime generated family | Result |
|---|---|---|
| `gemm_nax` | `mlx-generated/gemm_nax.cpp` | semantic parity |
| `steel_attention_nax` | `mlx-generated/steel_attention_nax.cpp` | semantic parity |
| `steel_gemm_fused_nax` | `mlx-generated/steel_gemm_fused_nax.cpp` | semantic parity |
| `steel_gemm_fused_gather_nax` | `mlx-generated/steel_gemm_fused_gather_nax.cpp` | semantic parity |
| `steel_gemm_splitk_nax` | `mlx-generated/steel_gemm_splitk_nax.cpp` | semantic parity |
| `steel_gemm_segmented_nax` | `mlx-generated/steel_gemm_segmented_nax.cpp` | semantic parity |
| `fp_quantized_nax` | `mlx-generated/fp_quantized_nax.cpp` | semantic parity |
| `quantized_nax` | `mlx-generated/quantized_nax.cpp` | exact body parity |

The only meaningful textual presentation differences in `fp_quantized_nax` are flattened FP4/FP8 includes and omitted comments/pragmas; dispatch predicates, templates, scales, accumulation, epilogues, and stores agree. `Vendor/mlx-swift/Source/Cmlx/mlx-generated/metal/fp_quantized_nax.h` is much shorter than the active source, but registry and include searches find no consumer; runtime uses the generated `.cpp` string.

**Positive control:** an in-memory comparator mutation changed the first `align_M` identifier to `align_M_SYNTHETIC`; normalized equality failed as required. No repository file was changed by the control.

## History and duplicate gate

Relevant ancestry is `2ebae10` (editable Gemma kernels), `99b974c` (promoted frontier sync), `13beb88` (FP quantized kernels/transform), and `7181803` (promoted organizer frontier sync). The current branch adds no production change.

Prior experiment gate:

- PR #605 tested exact regular-Steel QK-norm/YaRN work; neutral and reverted.
- PR #640 tested exact shared gate/up regular+NAX epilogue work; isolated positive but below the whole-model Amdahl threshold, then reverted.
- PR #649 audited routed-down; it failed the 2.33 ms prefill, ownership, and byte gates.
- PR #652 completed a 17-family ranked path audit and concluded NO-GO at `1fae5317e0ba348b004d69fb94f1b6c3c7f710c0`.

Thus a no-op twin sync would also duplicate an already closed audit class.

## Nomination gate

| Required gate | Finding |
|---|---|
| exact ranked-M5 reach | yes for the active generated NAX families above |
| real canonical/runtime mismatch | **no** |
| exact arithmetic/indexing/dispatch preservation | not applicable without a mismatch |
| correction no larger than 8 KiB | not applicable |
| estimated value >=18 us/decode token or >=2.33 ms/prefill | unsupported; mismatch correction work is zero |
| novel relative to prior PRs | no |

**Final decision: NO-GO.** No narrow correction is nominated. The selector-override asymmetry and inactive stale mirror should remain diagnostic notes only; neither changes ranked-default runtime source identity.

## Validation record

This was a static audit only. The report records both base and audited production-source SHA, source reach, source form, twin status, selector truth table, positive control, history, and the nomination threshold. The working tree was clean before the audit; final cleanliness is checked after committing this report. No model source, generated kernel, metallib, test, harness, dependency, environment variable, or machine configuration was changed. No build, benchmark, correctness run, W&B run, candidate submission, or official submission was performed. W&B: not applicable.
