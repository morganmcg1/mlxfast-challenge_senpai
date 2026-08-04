# Per-step host-CPU budget for the steady one-token decode step

Arm `maple-2026-08-04c-host-cpu-reduction`, PR #14, branch
`maple-frieren/host-cpu-reduction`. Measured at `BASE_SHA=51d6a1bd`; rebased at
r2 onto `aecc470e` (nezuko's #12), where the diff over `editablePaths` is
**empty**.

**This arm ships no scored change.** Four things it produced are the
deliverable, in descending order of usefulness to a future student:

1. **The host-CPU axis is closed, with a mechanism.** In-loop host CPU is
   provably absorbed; only the step-head serial region is exposed. Section 2.
2. **The ~190 MB KV re-request suspect is refuted** by a context-slope method
   that needs no per-dispatch byte counter. Section 7.
3. **The full-attention path is the least bandwidth-efficient stream in the
   step** — 58.2% of peak against a 78.6% step average, capped at 16.9 MB/step.
   Section 8.
4. Caveats: the command-buffer count here is not the ranked count (section 5),
   and the upstream-equivalence oracle's metallib failure is a host issue that
   reproduces on the unchanged base (section 9).

The two mechanisms that were implemented and measured — a kernel-source
minifier and an output-descriptor literal hoist — were **dropped at r2** and are
kept here only as a measured negative result (section 3, section 4).

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

## 2. Overlapped versus critical path — the spin-injection experiment

This is the decisive part of the budget, and it inverts the premise of the arm.

**Headline, stated once so nobody has to re-derive it: injecting 2.0 ms per step
of extra host CPU inside the decoder-layer loop *reduced* wall time from
8.903 ms to 8.669 ms per step — it was fully absorbed. The identical spin
injected at the step head, before the first dispatch, passed through at 1:1
(0.90-0.96 of the injected time appeared in wall). Therefore
`wall ~= head_host_latency + GPU_total`, and in-loop host CPU is free.**

The consequence for future arms: do not spend an arm shaving host work that
happens between the first and last dispatch of a step. It cannot pay. The only
host time that can pay is the serial region at the step head, measured at
0.29-0.32 ms here.

Method. An `@inline(never)` spin loop with a global sink and self-validating
counters was injected at two sites and swept. The counters confirm the spin
actually executed and was not optimised away; the sink prevents dead-code
elimination. Both sites were reverted before any timing run that feeds a score.

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

### Source bytes: measured elasticity (implemented, measured, then DROPPED)

A minifier was written that strips comments, blank lines, indentation, redundant
intra-line spacing and unnecessary newlines from every kernel source and header
once at construction (`Sources/MLXFastModel/LagunaRuntimeModel.swift`,
`lagunaMinifiedKernelSource`). Every runtime kernel is built through
`lagunaMetalKernel`, so no construction site could keep the unstripped form.
Because MLX's JIT library and pipeline caches key on the kernel **name** and not
on the source, every minified kernel also had to take a `_min` name suffix or a
stale full-source entry would alias it.

**It is not in the tree.** It was reverted at r2 on the advisor's instruction:
`T` moved 0.0% +- 0.2%, its priced value is <= 0.108% of score against a 0.303%
measurement floor, its only real benefit was +9,192 B of surface headroom out of
~67,056 B nobody is near exhausting, and it would have taxed every future kernel
edit by any student with a minifier round-trip and a `_min` suffix. The numbers
below are why the mechanism class is capped, and are the durable part.

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

## 4. Small allocation items (also DROPPED at r2)

`outputShapes` and `outputDTypes` literals are heap-allocated per apply. The 37
dtype literals and the 10 shape literals whose widths are fixed by
`LagunaConstants` were hoisted into `LagunaKernelOutput`, removing roughly a
thousand allocation/release pairs per step. The effect is inside the noise of the
counters above and is included in the v3 measurement, so it cannot be separated
from the minifier; it was reverted with it.

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

## 7. Pricing KV DRAM traffic without a per-dispatch counter

The advisor asked, if per-dispatch DRAM traffic could be priced, to pivot to it
and report. Apple Silicon exposes no per-dispatch byte counter that can be
attributed to an individual MLX custom kernel, so this section prices traffic
*indirectly*, by the slope of steady-step wall time against context length.

The measurement exists because the two attention families scale differently.
`Sources/MLXFastModel/LagunaConfig.swift:14-45` gives 40 layers, of which 10
(indices 0, 4, 8, ... 36) are full attention with 48 query heads and 30 are
sliding-window with 64 query heads and window 512. All layers share
`numKeyValueHeads = 8` and `headDim = 128`, and the cache is BF16, so one
position of one layer is `8 * 128 * 2 (K and V) * 2 bytes = 4096 B` of logical
KV. **Past a 512-token context only the 10 full-attention layers grow; the 30
sliding layers are pinned.** Two sweeps therefore separate the two families.

Each point is one `research/frieren_host_cpu_probe.py` invocation, which drives
the worker directly over its JSON protocol. The mean measured context is
`seed + warmup + measure/2`, a constant offset that cancels in a slope.

**Sweep A, at and above 512** (seeds 512/1536/2560/4096/6144, 100 warmup + 400
measured), isolating the full-attention family:

| seed | 512 | 1536 | 2560 | 4096 | 6144 |
| --- | ---: | ---: | ---: | ---: | ---: |
| wall ms/step | 8.8480 | 9.1171 | 9.4359 | 9.8576 | 10.3569 |

Pairwise slopes 262.8 / 311.3 / 274.5 / 243.8 ns per position show no curvature
across a 21 MB to 252 MB KV footprint, so no cache-residency effect is
distorting the fit. Least squares gives **270.3 ns per position for 10 layers =
27.03 ns per position per layer.**

**Sweep B, below 512**, where the window never fills and all 40 layers scale. The
whole measured window must stay under 512, which caps the lever arm, so this
sweep was run twice. First pass, seeds 100/200/300/400 with 20 warmup + 80
measured:

| seed | 100 | 200 | 300 | 400 |
| --- | ---: | ---: | ---: | ---: |
| wall ms/step | 8.6728 | 8.7784 | 8.8278 | 8.9306 |

Least squares gives 822.8 ns per position for 40 layers, but with only four
single-sample points the standard error is about 134 ns/pos. The replicate
therefore ran seeds 40/156/272/388 with 20 warmup + 96 measured, four samples
each, ordered as two palindromes (40, 156, 272, 388, 388, 272, 156, 40, twice) so
that monotone thermal drift cancels within each seed:

| seed | 40 | 156 | 272 | 388 |
| --- | ---: | ---: | ---: | ---: |
| mean wall ms/step | 8.6209 | 8.7195 | 8.7856 | 8.9192 |
| samples | 8.6358 8.6200 8.6095 8.6183 | 8.7208 8.7171 8.7237 8.7163 | 8.7105 8.8136 8.8128 8.8054 | 8.9129 8.9124 8.9425 8.9092 |

Least squares over all 16 runs gives **828.6 +- 56.2 ns per position for 40
layers**, agreeing with the first pass to well inside its error bar, and a
residual sigma of **29.2 us per point** - which independently confirms the ~30 us
per-point noise that the pairwise scatter of both sweeps implied. One sample,
`i3_s272 = 8.7105`, is a clear outlier: it was the third run of the session and
the other three samples at that seed sit at 8.805-8.814. Excluding it gives a
much tighter **851.6 +- 19.8 ns/pos with a 10.2 us residual sigma**. The looser
all-runs fit is used below; the tighter fit only strengthens every conclusion.

So the sliding family costs `(828.6 - 270.3) / 30 =` **18.61 ns per position per
layer** - 69% of a full-attention layer, despite carrying more query heads.

Converting nanoseconds to bytes needs a bandwidth yardstick. Two are used: the
step-average achieved 204.6 GB/s (the 1.794 GB/token roofline divided by the
8.769 ms step, i.e. the same basis as the budget the waste is charged against),
and this host's measured peak 260.2 GB/s
(`research/host_bandwidth_ceiling.swift`), which attributes *every* inefficiency
- latency, occupancy, partial cache lines - to extra bytes and so yields a
strict upper bound.

| family | ns/pos/layer | effective B at 204.6 GB/s | x logical | effective B at 260.2 GB/s | x logical |
| --- | ---: | ---: | ---: | ---: | ---: |
| full attention | 27.03 | 5531 | 1.35x | 7034 | 1.72x |
| sliding window | 18.61 | 3808 | 0.93x | 4843 | 1.18x |

At the benchmark's average decode context of 576 the logical KV read is
`10 * 576 * 4096 = 23.59 MB` for full attention plus `30 * 512 * 4096 =
62.91 MB` for sliding, **86.51 MB total**, which reproduces the 84-89 MB
independently derived in `research/nezuko-decode-roofline.md`. Charging the
measured slopes against that:

| yardstick | effective KV MB/step | waste vs logical | share of the 1794 MB step | share of score |
| --- | ---: | ---: | ---: | ---: |
| step-average 204.6 GB/s | 90.34 | +3.83 MB | +0.21% | +0.136% |
| peak 260.2 GB/s (upper bound) | 114.89 | <= +28.38 MB | <= 1.58% | <= 1.01% |

**This does not support the open suspect.** A KV re-request from 3-4
threadgroups multiplies KV bytes and is therefore exactly the kind of traffic a
context slope measures. The ~190 MB per step it predicts needs +103.5 MB over
logical, 5.77% of the step budget and 3.68% of score; the strict upper bound
measured here is +28.38 MB, **3.6x smaller than the claimed excess**, and the
like-for-like estimate is +3.83 MB. (The outlier-excluded fit gives a slightly
higher bound, +31.45 MB or <= 1.12% of score, still 3.3x below the claim.)

Statistically, the replicate's residual sigma of 29.2 us per point puts sweep B's
slope at 828.6 +- 56.2 ns/pos. Against that, a sliding-layer amplification of 2x
(which would require 1215 ns/pos) is **6.9 sigma** away, 3x (1687 ns/pos) is
**15.3 sigma**, and 4x (2159 ns/pos) is **23.7 sigma**; 1x (743 ns/pos) is 1.5
sigma below the measurement, i.e. the data prefer a mild 1.1-1.2x over exactly
1.0x but exclude everything at or above 2x outright. Excluding the single outlier
moves 2x to 18.4 sigma and 3x to 42.3 sigma. Note also that the per-point noise
is dominated by process-level offset rather than by within-run averaging, which
is why it is insensitive to the measured-step count (it explains both the
+-250 ns/pos scatter over sweep B's 100-position gaps and the +-25 ns/pos scatter
over sweep A's 1024-position gaps).

Sweep B also refutes a second, more benign hypothesis: if the sliding kernel
read its entire 512-slot ring regardless of how many slots were valid, sweep B's
slope would equal sweep A's 270 ns/pos. It is 3.0x larger, i.e. the kernel reads
only valid positions.

Two honest limits. First, a slope prices only traffic proportional to context; a
fixed per-step over-read would be invisible to it. Second, sweep B's total KV
footprint is 7-66 MB, low enough that system-level cache may absorb part of a
re-read and understate the sliding-family slope, so the 1.18x sliding bound is
weaker than the 1.72x full-attention bound, which was measured out to 252 MB
with no curvature.

### Reusing this method

There is no per-dispatch DRAM byte counter on Apple Silicon that can be
attributed to one MLX custom kernel, so this slope method is the substitute.
The recipe, in case another arm needs it:

1. Find two configurations of the same step where the byte stream you care about
   scales with a knob you control, and everything else does not. Here the knob is
   context length, and the 512-token sliding window is what makes the two
   attention families separable.
2. Sweep the knob over a lever arm large enough that the slope beats the
   per-process offset noise, which here is ~30 us per point and is dominated by
   between-process variation rather than by within-run averaging. Sweep A got
   +-25 ns/pos from 1024-position gaps; sweep B got only +-250 ns/pos from
   100-position gaps and needed 16 runs to reach +-56 ns/pos.
3. Order replicates palindromically (a, b, c, d, d, c, b, a) so monotone thermal
   drift cancels within each knob value.
4. Check the pairwise slopes for curvature before fitting. Curvature means a
   cache-residency effect is contaminating the fit.
5. Convert ns to bytes with two yardsticks: the achieved step-average bandwidth
   for a like-for-like number, and the measured peak for a strict upper bound
   (peak bills latency and occupancy loss as bytes, so it can only overstate
   waste).

## 8. Replacement finding: full attention is the least efficient byte stream

The same two slopes that refute the KV suspect also say where the residual
inefficiency actually is. One position of one layer is 4096 B of logical KV
(8 KV heads * 128 headDim * 2 for K and V * 2 bytes BF16). At this host's
measured peak of 260.2 GB/s that is `4096 / 260.2e9 =` **15.74 ns**. Against the
measured slopes:

| stream | measured ns/pos/layer | ideal at peak | efficiency |
| --- | ---: | ---: | ---: |
| full attention (10 layers) | 27.03 | 15.74 | **58.2%** |
| sliding window (30 layers) | 18.61 | 15.74 | 84.6% |
| whole step, for reference | 1.794 GB / 8.769 ms = 204.6 GB/s | 260.2 GB/s | 78.6% |

So the full-attention layers run at 58.2% of peak while the step as a whole runs
at 78.6%, and the sliding layers — which carry *more* query heads, 64 against
48 — run at 84.6%. Whatever is left to win in the KV stream is in the
full-attention path, not the sliding path.

The cap on it, stated so nobody oversells it. At the benchmark's average decode
context of 576, full-attention logical KV is `10 * 576 * 4096 = 23.59 MB`. Its
strict upper-bound amplification is `7034 / 4096 = 1.717x`, so the most that can
be wasted is `23.59 * 0.717 =` **16.9 MB per step** = 0.94% of the 1794 MB step
budget = **~0.60% of score** at the steady-step elasticity of 0.638. That is
above the 0.303% score floor and so is measurable, but it is a bounded target,
and the bound assumes every non-ideality in that stream is a wasted byte rather
than latency or occupancy loss — the real prize is smaller.

## 9. The upstream-equivalence oracle and the metallib failure — answered

The r1 report said the oracle "could not run here (MLX metallib load failure)".
The advisor asked whether that failure also occurs on the unchanged base. It
does, and the oracle does run once the documented workaround is applied.

Evidence, taken at r2 on this branch tip, whose diff over `editablePaths` against
base `aecc470e` is **empty** — so this *is* the unchanged base:

- `research/run_upstream_equivalence.sh` first invokes the bare
  `swift test --filter lagunaRuntimeMatchesVendoredUpstreamOnM5WhenEnabled`, and
  copies `mlx.metallib` into the debug test bundle **only** inside its
  `grep -q "Failed to load the default metallib"` branch. After the r2 run both
  `.build/arm64-apple-macosx/debug/mlx.metallib` and the copy inside
  `mlxfast-challenge-devPackageTests.xctest/Contents/MacOS/` carry that run's
  timestamp, which proves the fallback fired, i.e. **the load failure occurred on
  a tree with no scored change at all**.
- Cause, already documented by nezuko
  (`research/nezuko-decode-roofline.md`, interim 12): the debug test bundle has
  no colocated `mlx.metallib`; MLX's lookup
  (`Vendor/mlx-swift/.../backend/metal/device.cpp:164-215`) tries the colocated
  path, a SwiftPM bundle, a framework and the compile-time `METAL_PATH`, then
  throws; and `get_metallib_path()` (`backend/metal/metal.cpp:55-61`) is only
  settable in-process, so there is no environment override. It is a property of
  `swift test`, not of any source edit.
- The minifier therefore never broke the AOT metallib build, and could not have:
  it rewrote only JIT kernel source *strings* held in Swift
  (`LagunaRuntimeModel.swift`, `LagunaLmHeadPrune.swift`) and touched no
  `Vendor/` Metal source, so the AOT metallib inputs were byte-identical. The r1
  wording was wrong on the facts available and should not have been reported as a
  can't-run.

Oracle result on the r2 tip, after the metallib is seeded (worker and metallib
rebuilt in the same session against the merged `Vendor/` tree, so the AOT library
is coherent with #12):

| step | max abs logit err | mean abs logit err | runtime token | upstream token |
| --- | ---: | ---: | --- | --- |
| prefill | **0.125** | 0.011933609 | 5991 | 5991 |
| decode-0 .. decode-7 | **0** | **0** | 509/902/5991 cycling | identical |

`EQUIVALENCE_EXACT_STEPS=8`, `EQUIVALENCE_EXIT=1`. The non-zero exit is the
oracle's zero tolerance being applied to prefill as well as decode; the batched
NVFP4 prefill path cannot meet it against the BF16 upstream reference. This is
the same pre-existing 0.125 nezuko recorded on an earlier base. **Every decode
step is bit-exact and every token matches.**

Recorded as a known local limitation: on an M4 Pro host, the oracle requires
seeding `mlx.metallib` into the debug test bundle from
`.build-worker/arm64-apple-macosx/release/`, and it exits 1 on prefill tolerance
regardless of the candidate. Read the per-step table, not the exit code.

## 10. r2 gates, and how to re-run the probes

Gates on the r2 tip, whose `editablePaths` diff against `aecc470e` is empty:

| gate | result |
| --- | --- |
| `git diff aecc470e -- Sources Vendor` | empty |
| `swift test --force-resolved-versions` | **454/454 passed**, exit 0; `Package.resolved` restored |
| `./benchmark.sh --local-iterate` | `passed: true`, `max_abs_diff: 0`, `peak_ram_gb: 21`, decode floor true; decode -0.0% and prefill +0.1% against the recorded baseline artifact, i.e. a no-op as expected |
| `research/run_upstream_equivalence.sh` | 8/8 decode steps exact, prefill 0.125 pre-existing (section 9) |

The `--local-iterate` prefill floor fails here on this tree *and* on the
unchanged base: the pinned baseline artifact carries M5-class prefill seconds,
which an M4 Pro cannot match. It is a host artifact, not a candidate signal.

The two probe scripts are kept as the record of the method, not as runnable
tools on a clean tree:

- `research/frieren_host_cpu_probe.py` drives
  `.build-worker/release/mlxfast-runtime-worker runtime-worker` over its JSON
  protocol with an explicit seed length and warmup/measure split. This part
  works against an unmodified tree and is what produced both context sweeps.
- `research/frieren_host_cpu_arms.sh` additionally sets
  `DARKBLOOM_DECODE_HOST_CPU`, `DARKBLOOM_DECODE_HOST_SPIN_US` and
  `DARKBLOOM_DECODE_HOST_SPIN_HEAD_US`. **Those variables no longer exist**: the
  CPU-clock instrumentation and the spin injection were reverted before every
  timing run (commit `57cba8d` on the r1 history), as the assignment required.
  Re-running section 2 means re-adding the instrumentation first; the script
  documents the arm structure and the sweep values, not a live entry point.

