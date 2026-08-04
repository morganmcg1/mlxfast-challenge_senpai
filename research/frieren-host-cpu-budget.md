# Per-step host-CPU budget for the steady one-token decode step

Arm `maple-2026-08-04c-host-cpu-reduction`, PR #14, branch
`maple-frieren/host-cpu-reduction`, `BASE_SHA=51d6a1bd`.

Host: Mac16,11 M4 Pro, 48 GiB, low-memory startup profile. **Not** the ranked
M5 Max. Absolute timings do not transfer; the ratios and the overlap structure
are the transferable results.

All numbers below are steady state: the direct runtime worker
(`.build-worker/release/mlxfast-runtime-worker runtime-worker`) is seeded with
512 synthetic tokens and then driven for 480 one-token steps, of which the last
400 are measured. Instrumentation was reverted before every timing run that
feeds a score.

## 1. The budget

| Quantity | Value | How measured |
| --- | ---: | --- |
| wall per step | 8.86 ms | entry-to-entry in the driver (harness reports 8.769 ms) |
| whole-process CPU per step | 4.83 ms | `getrusage(RUSAGE_SELF)`, all threads, entry to entry |
| main-thread CPU inside the forward | 2.73 ms | `CLOCK_THREAD_CPUTIME_ID` around `callAsFunction` |
| main-thread wall inside the forward | 6.26 ms | so 3.5 ms of the forward is the main thread blocked |
| non-main-thread CPU per step | 2.11 ms | process CPU minus main-thread CPU; `ps -M` shows two threads at ~0.93 ms each |
| GPU dispatches per step | ~406 | earlier `DARKBLOOM_GPU_PROFILE` instrumentation |
| command buffers per step | ~45 | same; see the caveat in section 5 |
| custom-kernel applies per step | ~370 | dispatch census |
| main-thread CPU per apply | ~7.4 us | 2.73 ms / 370 |

Cross-process `proc_pid_rusage` was tried first and is unreliable here; the
`ps -M` per-thread sum independently reproduces the 4.60-4.83 ms figure, so the
in-process `getrusage` number is the one to trust.

`sample` profile of the main thread inside the forward, as a fraction of
running samples:

| Bucket | Share |
| --- | ---: |
| malloc / free | 25.2% |
| MLX `CommandEncoder::set_input_array` / `set_output_array` + hash tables | 16.7% |
| Swift ARC retain / release | 12.6% |
| AGX / IOKit driver | 10.0% |
| MLX eval scheduling | 8.8% |
| `MLXArray` construction | 6.8% |
| custom-kernel dispatch, including a full-source `memcmp` | 6.6% |
| kernel-source string building | 6.0% |
| `MLXFastKernel` apply glue | 3.2% |
| slicing | 1.5% |

## 2. Overlapped versus critical path

This is the decisive part of the budget, and it inverts the premise of the arm.

An `@inline(never)` spin loop with a global sink and self-validating counters was
injected at two sites and swept:

**Per decoder layer, inside the layer loop (40 calls per step):**

| spin per layer | injected CPU per step | wall per step |
| ---: | ---: | ---: |
| 0 us | 0.0 ms | 8.903 ms |
| 50 us | 2.0 ms | 8.669 ms |
| 200 us | 8.0 ms | 14.13 ms |

Two millisecond of extra host CPU inside the layer loop is **completely free**.
Beyond a knee at roughly 2.0-2.8 ms the slope is 0.91, i.e. once the slack is
gone the host pays nearly 1:1.

**Once per step, at the top of `callAsFunction`, before the first dispatch:**

| head spin | wall per step | exposed fraction |
| ---: | ---: | ---: |
| 0 us | 8.8628 ms | - |
| 150 us | 9.0074 ms | 96% |
| 400 us | 9.2376 ms | 94% |
| 1200 us | 9.9404 ms | 90% |

So `wall ~= head_host_latency + GPU_total`. In-loop host CPU hides behind
already-queued GPU work; only the serial region between the previous step's
readback and this step's first dispatch is on the critical path. The earlier
GPU-busy census agrees: GPU-busy **union** was 9.498 ms of a 9.816 ms step, a
0.322 ms idle gap, i.e. 3.3%.

The exposed serial region is therefore ~0.29-0.32 ms of an 8.86 ms step. A 25%
cut of *total* host CPU is worth ~0 ms locally; a 25% cut of the *head* region
is worth ~0.075 ms, i.e. 0.85% of the M4 step.

The step boundary is a hard serialization and not an overlap bug: teacher-forced
decode hands the runtime one token per invocation and the harness must read the
argmax back before supplying the next, so the pipeline drains once per step by
construction. The remaining 0.32 ms is drain-plus-relaunch latency, and the
front-edge overlap that could be recovered has already been taken by
`lagunaDecodeAsyncStage at:0,1,7,15,23,31,39` and
`DARKBLOOM_ATTN_PROJECTION_ASYNC`.

## 3. Where the per-apply 7.4 us goes, and what is reachable

MLX charges every custom-kernel apply for the **full generated kernel source**,
twice:

- `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/common/metal_kernel.cpp:51-175`,
  `write_signature()`: `reserve(header + source + 16384)`, then copies the
  header, the generated signature and the whole source. Called per apply from
  `MetalKernel::operator()` (~line 318).
- `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/custom_kernel.cpp:56-69`:
  compares the whole generated string against the library-cache entry.

The library and pipeline caches key on the short kernel **name**, not on the
source, so neither copy is ever skipped. `MLXFastKernel.callAsFunction`
(`Vendor/mlx-swift/Source/MLX/MLXFastKernel.swift:98`) hands the source to C
only once, at construction, so the whole per-apply source cost is in those two
C++ functions. **Neither file is in `benchmark.json`'s `editablePaths`**, and
neither is `backend/metal/device.cpp`, `Source/MLX/MLXFastKernel.swift`, or
`Source/MLX/MLXArray.swift`.

That leaves exactly two levers on this path from inside the editable surface:
source **bytes** and apply **count**.

### Source bytes: measured elasticity

A minifier now strips comments, blank lines, indentation, redundant intra-line
spacing and unnecessary newlines from every kernel source and header once at
construction (`Sources/MLXFastModel/LagunaRuntimeModel.swift`,
`lagunaMinifiedKernelSource`). Every runtime kernel is built through
`lagunaMetalKernel`, so no construction site can keep the unstripped form.

| version | static kernel bytes | reduction |
| --- | ---: | ---: |
| off | 124,490 | - |
| v1 comments + indentation | 100,994 | -18.9% |
| v2 + intra-line spacing | 89,342 | -28.2% |
| v3 + line joining | 86,379 | -30.6% |

Three independent A/B pairs, minify off then on, same binary, same host:

| pair | main-thread CPU off | on | delta | proc CPU off | on | delta | wall off | on |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| v1 | 2.8226 | 2.6119 | -7.5% | 4.9839 | 4.7156 | -5.4% | 8.8391 | 8.8361 |
| v2 | 2.7377 | 2.6317 | -3.9% | 4.7717 | 4.7279 | -0.9% | 8.8478 | 8.8578 |
| v3 | 2.7141 | 2.7251 | +0.4% | 4.9222 | 4.7595 | -3.3% | 8.8583 | 8.8522 |
| mean | 2.758 | 2.656 | **-3.7%** | 4.893 | 4.734 | **-3.2%** | 8.848 | 8.849 |

Run-to-run spread on these CPU counters is about 2% one-sigma, so the honest
statement is a **-3 to -4% host-CPU reduction, sign-consistent on process CPU in
all three pairs, with wall unchanged to within 0.1%.** `seed_token` was
identical in every arm.

Taking the byte reduction and the CPU reduction together, source-byte-linear
work is roughly 20% of main-thread CPU. That is the ceiling of this mechanism:
even deleting the source entirely would buy ~20%.

### Apply count

At ~370 applies and ~7.4 us each, apply count is the only large term. Nothing in
the editable surface reduces the fixed per-apply cost, so the remaining host-CPU
levers are all "issue fewer applies", which is dispatch fusion, not host-side
bookkeeping.

## 4. Small allocation items

`outputShapes` and `outputDTypes` literals are heap-allocated per apply. The 37
dtype literals and the 10 shape literals whose widths are fixed by
`LagunaConstants` are now hoisted into `LagunaKernelOutput`, removing roughly a
thousand allocation/release pairs per step. This is inside the noise of the
counters above and is included in the v3 measurement.

Items checked and **dropped** as already free:

- `eScoreCorrectionBias.asType(.float32)`, 39 calls per step: the checkpoint
  already stores it as F32
  (`Sources/MLXFastTransform/LagunaCheckpointValidation.swift:462`) and
  `MLXArray.asType` short-circuits on a matching dtype
  (`Source/MLX/MLXArray.swift:495-496`).
- Command-buffer sizing: already set by prior work in
  `Sources/MLXFastModel/LagunaRuntimeWeights.swift:380-390`.
- Hoisting shared Metal header code into the JIT preamble: `metal::utils()` lives
  in `mlx-generated/utils.cpp`, which is not editable.

## 5. Caveat on the 45 command buffers

This host is forced into the low-memory startup profile, which applies different
`MLX_MAX_OPS_PER_BUFFER` / `MLX_MAX_MB_PER_BUFFER` caps than the ranked profile
(`Sources/MLXFastModel/RuntimeStartupMemoryPolicy.swift:113`). The 45
command buffers per step measured here reflect the low-memory caps, not the caps
the ranked M5 run uses. Any conclusion about command-buffer count must be
re-derived on a host that takes the ranked profile.

## 6. What this means for the axis

1. Total per-step host CPU is 4.83 ms, of which only ~0.29-0.32 ms is on the
   critical path on this host.
2. The per-apply cost is structurally fixed by non-editable MLX C++.
3. Source-byte reduction, the one mechanism that is fully inside the editable
   surface, is worth about 20% of main-thread CPU at best and delivered -3 to
   -4% of total host CPU at -30.6% of bytes.
4. Therefore **the assignment's >=25% host-CPU target is not reachable through
   host-side bookkeeping.** The honest ceiling for this arm's mechanism class is
   under 15%, and even reaching it would not move local wall.

The one lever that would clear 25% is replaying the decode segment through MLX
`compile`, which reuses the traced `CustomKernel` primitive and so deletes
`write_signature`, the kernel-name assembly, the Swift/mlx-c glue, the per-op
`MLXArray`/ARC churn and the ~120 slice nodes for all ~363 applies at once,
estimated at 0.7-0.9 ms per step. The editable infrastructure for it already
exists (`Vendor/mlx-swift-lm/Libraries/MLXLMCommon/CompiledDecode.swift`,
`CompilableKVCache.swift`, `CompilableRotatingKVCache.swift`,
`DynamicSlice.swift`). It is a separate, much larger hypothesis with its own
trap list - trace-time constant baking of `writeIdx` and cache offsets, fusion
and copy elimination versus the in-place ring write, shapeless-compile grid
freezing, the step-1 full-attention branch needing a two-graph selector, and a
known Metal-JIT zero-results bug that needs an untimed self-check fallback - and
it should be assigned as such rather than bolted onto this arm. Note also that
because in-loop host CPU is provably absorbed on this host, its value would come
from the dispatch and graph-node reduction, not from the host-CPU saving.
