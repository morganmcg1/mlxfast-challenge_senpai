# PR #23 — decode-step head-region decomposition (maple-2026-08-04e-head-latency)

Student: maple-frieren. Host: AWS M4 Pro, 48 GiB (low-memory startup profile
unless stated otherwise). `BASE_SHA` `969fea003eb6964f702c1f7c3e0234d022406a9f`.

All numbers below are from a research-only instrumentation build that is
**reverted before any scored run**. Two probes:

* `FRIEREN_CBPROF=1` in `Vendor/.../backend/metal/device.cpp` records, per
  Metal command buffer, `{commit_s, kernelStartTime, kernelEndTime,
  GPUStartTime, GPUEndTime, completion_s, ops}`.
* `FrierenStepProf` in `Sources/MLXFastModel/LagunaRuntimeModel.swift` records
  five Swift-side marks per one-token decode step: model entry, pre-layer-loop,
  first `asyncEval`, model return, call return.

Driver: `research/frieren_host_cpu_probe.py` talks the worker JSON protocol
directly (`.build-worker/release/mlxfast-runtime-worker`), so a steady-state
decode measurement costs ~20 s instead of an ~11 min `--local-iterate` pair.
Analyser: `research/frieren_head_region.py`.

Trace used for Part 1: 28 454 command buffers and 361 steps; 278 steady steps
after dropping warmup; clock sanity 0/28 454 ordering violations.

## Part 1 — the three requested numbers, at ranked parity

**Read this table, not the low-memory one below it.** The first pass ran under
this host's default low-memory startup profile, which force-sets a 128
Mi-element command-buffer cap. `DARKBLOOM_STARTUP_MEMORY_PROFILE=full` turns out
to run on a 48 GiB host, so the whole decomposition was re-taken at the shipped
ranked settings (200 Mi-elements / 400 ops). Medians over 278 steady steps,
microseconds, 16 595 command buffers, 0 clock-ordering violations.

| # | Region | µs | se | notes |
| --- | --- | ---: | ---: | --- |
| 1 | step entry → first command-buffer commit | **35.7** | 0.8 | host-side, fully exposed, **editable** |
| 2 | first commit → first GPU kernel start | **67.1** | 0.5 | driver + firmware launch latency, p10 61.9 / p90 83.4 |
| 3 | tail GPU idle after model call returns | **0.0** | 0.0 | median *and* p90; the GPU is still 3.8 ms from done when the call returns |

And the two terms the same trace exposes that are not "head" at all:

| Region | µs | se | notes |
| --- | ---: | ---: | --- |
| previous step's last GPU end → this step's entry | **122.1** | — | trusted harness: worker JSON IPC + the blocking `argMax().item()` readback. **Not on the submission surface.** |
| interior GPU idle at command-buffer boundaries | **75.9** | — | 47 boundaries/step, ~1.6 µs each |
| idle inside the layer loop | **0.0** | 0.0 | median and p90; #14's absorption result holds exactly |
| idle in the head/norm/logits tail region | **0.0** | 0.0 | median and p90 |

Frame at ranked parity:

| Quantity | Value |
| --- | ---: |
| step period | 8834.4 µs |
| GPU busy | 8533.1 µs |
| **total GPU idle** | **300.8 µs** |
| GPU busy fraction | 96.59 % |
| front idle (prev GPU end → first GPU start) | 224.9 µs |
| **command buffers per step** | **48** (mean 44.3) |
| dispatches in first command buffer | 4 |
| forward wall (entry → call return) | 5031.3 µs |
| tail wall (call return → next entry) | 3802.3 µs |
| worker encoding-thread CPU per step | 2.51 ms |

Two things to notice.

**Your 0.29–0.32 ms residual is confirmed to the microsecond, at ranked
settings: total GPU idle is 300.8 µs.** That is a genuinely satisfying
independent landing, because your figure came from a `wall ≈ head + GPU_total`
regression and mine comes from Metal's own per-command-buffer counters.

**But only 35.7 µs of it — 11.9 % — is on the submission surface.** The
composition is:

```
300.8 us total GPU idle per ranked-parity decode step
  122.1  trusted harness (IPC + argmax readback)      not editable
   67.1  driver + firmware launch latency             not editable
   75.9  interior command-buffer boundary gaps        editable only via cb structure
   35.7  step entry -> first commit                   editable host work
    0.0  in-loop / tail / post-return idle            nothing there
```

So the arm's 2.2–4.4 %-of-score prize is 88 % locked behind the trusted harness
and the Metal driver. The head-latency hypothesis as briefed is dead, and I say
so under the stop rule below — but the same trace found the live term, and it is
not a latency term at all. See "The mechanism is not launch latency" below.

### The earlier low-memory-profile reading, for the record

| # | Region | µs | se | notes |
| --- | --- | ---: | ---: | --- |
| 1 | step entry → first command-buffer commit | **26.0** | 0.3 | host-side, fully exposed, **editable** |
| 2 | first commit → first GPU kernel start | **59.1** | 0.6 | driver + firmware launch latency, p10 44.5 / p90 67.1 |
| 3a | tail GPU idle after model call returns | **4.4** | — | mean; GPU still draining async work |
| 3b | interior GPU idle at command-buffer boundaries | **114** | — | 76.8 boundaries/step × ~1.4 µs |

Supporting frame:

| Quantity | Value |
| --- | ---: |
| step period | 8782.2 µs |
| forward wall (entry → `callAsFunction` return) | 6181.8 µs |
| tail wall (call return → next entry) | 2595.9 µs |
| GPU busy (union of GPU intervals) | 8512.3 µs |
| GPU busy fraction | 96.92 % |
| total GPU idle | 269.9 µs |
| front idle (prev step last GPU end → this step first GPU start) | 152.9 µs |
| command buffers per step | 78 |
| dispatches per step | ~406 |
| worker encoding-thread CPU per step (`ps -M`) | 2.6 ms |

Idle accounting closes: `152.9 (front) + 114 (boundaries) + 4.4 (tail) = 271.3`
against a measured total of `269.9` (the small excess is double-counting of one
boundary that coincides with the front gap in some steps).

### Sub-splits

Region 1 (26.0 µs), from the Swift marks:

| Sub-region | µs |
| --- | ---: |
| entry → pre-layer-loop mark (cache-position verify ×40, RoPE atlas position, two `createAttentionMask` calls that both return `.none` at L==1, fused embedding+RoPE dispatch encode, ~30-predicate layer-0 guard chain) | 5.5 |
| pre-layer-loop → first commit (layer-0 `lagunaNormAffineQKV` encode, MLX graph walk, encoder setup, `commit`) | 20.5 |

The first commit lands 15.3 µs **before** the `markFirstAsync()` timestamp that
follows `asyncEval(qkv, gateLogits)` (`LagunaRuntimeModel.swift:5619`), which
confirms MLX `asyncEval` encodes and commits on the calling thread; entry → the
`asyncEval` mark is 41.4 µs.

Region 2 (59.1 µs), from Metal's own command-buffer counters:

| Sub-region | µs |
| --- | ---: |
| `commit` → `kernelStartTime` (kernel-driver ingest) | 10.5 |
| `kernelStartTime` → `kernelEndTime` (driver submission processing) | 25.5 |
| `kernelEndTime` → `GPUStartTime` (firmware queue → GPU launch) | 30.1 |

Front-idle residual: `152.9 − 26.0 − 59.1 = 67.8 µs` is the trusted,
non-editable segment — parent↔worker JSON IPC over pipes, the blocking
`argMax().item()` readback in `LagunaCorrectness.swift:105-112`, the per-request
`DispatchSourceTimer` watchdog, and token comparison. All of it lives in
`Sources/MLXFastTrustedHarness/*` and `Sources/MLXFastHarness/*`.

## Verdict on the assignment stop rule

The stop rule was: *if the head region is dominated by commit-to-kernel-start
driver latency and the host portion is under ~0.1 ms, report that and stop.*

Both conditions hold at ranked parity. Driver latency (67.1 µs) is 1.9× the host
portion (35.7 µs), and the host portion is 35.7 µs — a third of the 0.1 ms
threshold. Even a perfect, physically impossible elimination of every editable
host microsecond in the head region is worth 35.7 µs, i.e. 0.40 % of this host's
step and **0.82 % of the 4.353 ms ranked M5 step**, which at your 0.638
elasticity is **0.52 % of score** — below the 0.61 % bar, and that is the
*ceiling*, requiring the first command buffer to commit at t = 0.

Part 2 candidate 1 ("commit the embedding gather first") is measurable and
measured: at a 195 Mi-element cap the bf16 embedding table's 196 charge forces a
cut immediately after the fused embedding+RoPE dispatch, which is exactly what
that candidate would implement in Swift. It moves the first commit from 35.7 µs
to 25.6 µs and the whole step by **−0.30 %** (9.1229 vs 9.1506 ms in the same
round), inside the run-to-run spread. So the candidate works mechanically and is
worth ~10 µs, i.e. **0.15 % of score**. I did not spend a submission on it.

What the stop rule does *not* cover, and what the rest of this memo is about,
is that the same instrument found a **123.5 µs GPU-busy** term next door, which
is 4× the entire editable head region and is not a latency term at all.

## Candidate (a) — per-step Swift graph rebuild — is real and is not the term

You were right about the structure and I can confirm it independently: the
scored decode step rebuilds the whole Swift-side MLX graph every token. I
searched every public symbol declared in `CompiledDecode.swift`,
`CompilableKVCache.swift`, `CompilableRotatingKVCache.swift` and
`DynamicSlice.swift` and there are **zero references from anywhere in
`Sources/`**. Their real consumers are `MLXLMCommon/GenerationBatch.swift`,
`MLXLLM/Models/Gemma4Text.swift` and the CBv2 tree, and `GenerationBatch` /
`TokenIterator` are never referenced from `Sources/` at all — the scored driver
calls the model directly (`LagunaRuntimeWorker.swift:208`,
`LagunaRuntimeBenchmark.swift:867,890`), so `setupCompiledDecodeIfEligible` is
unreachable. `RoPEApplication.graphOffsetArray` casts to the compilable cache
subclasses at `RoPEApplication.swift:31,34`, but the runtime constructs
`KVCacheSimple` and `RotatingKVCache(maxSize: 512, keep: 0)`
(`LagunaRuntimeModel.swift:10888-10893`), so those casts always return nil, and
`decodeRoPEAtlasPosition` deliberately excludes the compilable subclasses by
exact `type(of:)` equality (`:10627-10629`). The per-step guard cascades at
`:5498-5515` and `:10241-10251` are re-executed for all 40 layers on every
token. So: rebuilt, every step, confirmed twice.

**And it costs nothing measurable, because it is hidden.** Three independent
readings:

| Reading | Value | Implication |
| --- | ---: | --- |
| worker encoding-thread CPU per step (`ps -M`) | **2.51 ms** | true host graph+encode cost is ~6.2 µs/op over 406 ops, ~9× your 0.7 µs estimate |
| exposed portion of it (entry → first commit) | **35.7 µs** | 1.4 % of the encode cost is on the critical path |
| GPU idle inside the layer loop, median *and* p90 | **0.0 µs** | after the first commit the encoder never starves the GPU again |

The `406 × 0.7 µs = 0.28 ms ≈ 0.30 ms` arithmetic is numerology: the per-op cost
is ~6.2 µs, not 0.7 µs, so the true total is 2.51 ms, and the reason it does not
appear in the step is that the encoding thread runs ~3.4× ahead of a
DRAM-bound GPU. **Predicted gain from compiling the whole decode region: ~0.**
It would remove ~2.5 ms of host work that is already free, and leave the 35.7 µs
that is not, because even a fully compiled graph must still be walked and
submitted before the first kernel can start.

I would not build the compiled region. The evidence that would change my mind is
a trace showing in-loop GPU idle above ~20 µs/step; I measure 0.0 at both the
median and p90 at ranked parity.

Two smaller items from your follow-ups, closed for the same reason:

* **The inert-extra-bindings scaling test.** Its answer is already bounded by
  #14 plus this trace: 2.0 ms/step of injected in-loop host spin was fully
  absorbed *and reduced* wall time, and in-loop GPU idle is 0.0 µs. There is no
  in-loop exposure for extra bindings to grow. The one place bindings could
  matter is the 4-dispatch first command buffer, which is 35.7 µs total.
* **The `DARKBLOOM_ROPE_ATLAS_VIEWS` note that "the two probes overlap the
  embedding gather and the layer-0 front".** On the current base there are no
  two probes to overlap: `lagunaDecodeEmbeddingRoPEAtlas` fuses the embedding
  gather and both RoPE angle rows into **one** dispatch
  (`LagunaRuntimeModel.swift:10665-10674`, kernel `:10440-10494`), and my trace
  confirms the first command buffer holds 4 dispatches and runs 44.5 µs. So that
  note's caveat no longer applies, which is why region 1 is a clean host-only
  measurement.

## The mechanism is not launch latency — it is live temporaries per command buffer

This is the part I did not expect and it changes what the arm is worth.

Lowering MLX's command-buffer volume cap from the shipped 200 Mi-elements to 50
makes this host's decode step **1.56 % faster** (8.9582 ± 0.0023 ms, n = 6,
against 9.1003 ± 0.0198 ms, n = 7, at the shipped cap; t ≈ 7.1 against a 0.20 %
A/A floor). Tracing both arms shows where the time goes, and it is not where a
latency story predicts:

| | cap 50 | cap 200 (shipped) | Δ |
| --- | ---: | ---: | ---: |
| step period | 8678.6 | 8834.4 | **−155.8** |
| **GPU busy** | **8409.6** | **8533.1** | **−123.5** |
| total GPU idle | 269.0 | 300.8 | −31.8 |
| command buffers/step | 140 | 48 | +92 |
| boundaries/layer | 3.5 | 1.2 | — |
| entry → first commit | 25.6 | 35.7 | −10.1 |
| first commit → first GPU start | 45.5 | 67.1 | −21.6 |
| dispatches in first cb | 1 | 4 | — |

**79 % of the win is reduced GPU-busy time.** More command buffers means *more*
boundaries and *more* per-buffer driver latency, and it is still faster. So the
mechanism cannot be launch overhead, dead band, or host exposure. What a lower
cap actually does is bound how much array memory a single command buffer keeps
alive: MLX charges `buffer_sizes_ += a.data_size()` per distinct input buffer and
cuts at `(buffer_sizes_ >> 20) > max_mb` (`device.cpp:393-401`, `:562`), and a
buffer's temporaries cannot be recycled until it completes. Cap 200 holds ~4×
the live footprint of cap 50. On a step that is already at ~79 % of achievable
bandwidth, a smaller live working set is straightforwardly less DRAM traffic.

This also explains why it is invisible to a byte roofline built from *unique*
bytes: the extra traffic is re-reads of data that a smaller footprint would have
kept resident. Per the new team rule — my numerator here is **neither**: I am
reading GPU-busy time from Metal counters, not bytes.

### Why the existing layer-boundary ladder cannot reach it

At cap 200 the step already lands 48 boundaries over 40 layers = 1.2 per layer,
so a rung fired *at a layer boundary* lands essentially on top of a volume cut
and adds nothing. Measured, in the same round as the numbers above:

| arm | ms/step |
| --- | ---: |
| cap 200, default ladder `at:0,1,7,15,23,31,39` | 9.1506 |
| cap 200, `ladder1` (a rung after **every** layer) | 9.1396 |
| cap 200, default ladder, control repeat | 9.0721 |
| cap 50, default ladder | 8.9594 |
| cap 50, `ladder1` | 8.9697 |

`ladder1` at cap 200 captures **none** of the 1.56 %: 9.1396 sits inside the
control spread (9.1506 / 9.0721). And `ladder1` at cap 50 does not add to cap 50
either. The ladder axis is saturated; density is the live variable, and reaching
3.5 boundaries per layer requires rungs *inside* the layer.

### The reachable version works, and the effect is linear in boundary count

`DARKBLOOM_DECODE_SUBLAYER_ASYNC` adds decode-only rungs *inside* the layer:
`a` after the attention output projection (forcing `r`), `b` after the fused
residual+RMSNorm+router (forcing `h`, `normalized`, `routerLogits`,
`routerKeys`), `c` after router top-k (forcing `inds`, `weights`). Each forces
arrays the very next dispatch consumes anyway, so no work is added and no value
can change, and each is guarded on `x.dims(1, 1, hiddenSize)` so prefill keeps
its own schedule.

Traced at ranked parity, `ab` lands exactly on the cap sweep's line:

| arm | cbs/step | GPU-busy µs | GPU idle µs | step µs |
| --- | ---: | ---: | ---: | ---: |
| control | 48 | 8839.8 | 288.1 | 9126.2 |
| rungs `ab` | 90 | 8782.1 | 288.9 | 9070.5 |
| cap 50 (not shippable) | 140 | 8716.3 | 269.0 | 8678.6 |

```
rungs ab:  -57.7 us GPU-busy / +42 boundaries = -1.37 us per boundary
cap 50:   -123.5 us GPU-busy / +92 boundaries = -1.35 us per boundary
```

Two independent interventions, on different mechanisms (an explicit Swift eval
rung versus MLX's internal volume cut), give the same coefficient to within
1.5 %. GPU **idle** is flat across the rung contrast (288.1 → 288.9), so the win
is not launch overhead, dead band, or host exposure — the GPU executes less.
That is what makes it a real finding rather than a scheduling artifact, and it is
why the term is invisible to a *unique*-byte roofline: it is re-read traffic that
a shorter-lived working set avoids.

Note that only ~half the fires create a boundary (80 fires → +42 command
buffers), because the rest land where a volume cut already happens.

### Sizing, and why the drift correction matters

Wall-time arms in an unbalanced screen could not see this. Controls at positions
1/5/7 of one round measured 9.0356 / 9.1076 / 9.1136 — **~0.8 % of monotone
position drift**, larger than the effect. (This also retires my earlier
"cap-200 bimodality": it was arm order, not two modes.) The traced pair above
sits at adjacent positions, where drift is ~0.07 %, and reads −0.61 % of step.

| variant | cbs/step | predicted Δ step | score at `S` flat |
| --- | ---: | ---: | ---: |
| `ab` (measured) | 90 | −0.61 % | +0.39 % |
| `abc` (extrapolated) | ~115 | −1.02 % | **+0.65 %** |
| cap-50 density (ceiling) | 140 | −1.40 % | **+0.90 %** |

So `ab` alone is under the 0.61 % bar and `abc` is the first variant in this arm
that can clear it. A position-balanced dose screen (`off`/`ab`/`abc`, each at
positions summing to 15, plus a traced `abc` arm) is what decides it.

## The ratio argument the advisor asked for, made explicit and checked

A host-side or driver-side serial microsecond is *absolute*: it does not shrink
when memory bandwidth doubles. So its share of the step grows on a faster box.

Bandwidth-scaling consistency check on the measured split:

```
predicted M5 step = GPU-busy / bandwidth-ratio + serial-idle
4353 µs (advisor's ranked step) = 8512.3 / r + 269.9
                              ⇒ r = 2.085
```

`r = 2.085` is exactly the ratio of *achievable* bandwidths if the M4 Pro
sustains ~240 GB/s of its 273 GB/s nominal (88 %) and the M5 Max sustains
~500 GB/s of its 614 GB/s nominal (81 %) — both inside the advisor's 485–530
GB/s band for the M5. In other words, the measured 8512 µs GPU-busy + 270 µs
serial split reproduces the ranked step time to within the uncertainty of the
bandwidth numbers, using **no** free parameters beyond the achievable-bandwidth
ratio.

Consequences:

* Every serial microsecond removed locally is one microsecond removed on M5.
* As a *fraction*, it is worth `8782.2 / 4353 = 2.02×` more on M5 than here.
* The whole 269.9 µs serial term is 3.07 % of this host's step and **6.20 % of
  the ranked step** — which is the advisor's point, confirmed by measurement
  rather than assumed.
* But only **26.0 of those 269.9 µs are editable host work** (0.60 % of the
  ranked step). 59.1 µs is driver/firmware launch latency, 67.8 µs is trusted
  harness code, 114 µs is GPU-side inter-command-buffer turnaround, 4.4 µs is
  post-return drain.

## Scaling-law decomposition of the head term

| Term | µs (M4 Pro) | Scales with | Expected M5 behaviour |
| --- | ---: | --- | --- |
| Swift pre-encode bookkeeping | 5.5 | CPU single-thread clock/IPC | ~0.85× (M5 P-core is faster) |
| MLX graph walk + encoder setup for the head's 4 ops | ~15 | dispatch count × CPU clock | ~0.85× |
| `commit` (IOKit submit) | ~5 | fixed per-command-buffer OS cost | ~1.0× |
| kernel-driver ingest + submission processing | 36.0 | fixed per-command-buffer driver cost | ~1.0× |
| firmware queue → GPU launch | 30.1 | fixed hardware/firmware latency | ~1.0× |
| trusted IPC + JSON | ~40 (of 67.8) | CPU clock, pipe syscalls | ~0.85× |
| `argMax().item()` readback | ~28 (of 67.8) | fixed GPU→CPU sync latency | ~1.0× |
| inter-command-buffer GPU bubbles | 114 | **command-buffer count** × ~1.4 µs fixed turnaround | ranked count is lower, so lower |
| post-return drain | 4.4 | CPU clock | ~0.85× |

Only the first two rows scale with CPU clock; only the last-but-one scales with
dispatch/command-buffer structure; the rest are fixed OS, driver, firmware, and
sync latencies that a faster CPU and a faster GPU both leave untouched.

## Reconciliation with PR #9's exact zero (δ ≤ 1.05 µs per dispatch)

The advisor's constraint: removing 40 of 406 dispatches returned exactly 0
against a 42 µs A/A floor, so the exposed per-dispatch cost is ≤ 1.05 µs and
the whole ~366-dispatch stream is ≤ 0.38 ms. My decomposition is consistent,
and now explains *why* the answer was exactly zero:

1. The worker's encoding thread uses 2.6 ms of CPU per 8.78 ms step. It is
   ~3.3× ahead of the GPU. After the first commit, encode work for dispatch
   *n+1* is finished long before the GPU reaches it, so **per-dispatch encode
   cost is hidden, not exposed**. My decomposition attributes ~0 exposed cost
   per dispatch, well inside the ≤ 1.05 µs bound.
2. The only place host encode is *not* hidden is the head region, before the
   first commit — and that is the 26 µs I measured, covering only ~4 ops.
3. MLX cuts command buffers on **referenced input volume**, not op count:
   `CommandEncoder::needs_commit()` is
   `(buffer_ops_ > max_ops) || ((buffer_sizes_ >> 20) > max_mb)` with
   `buffer_sizes_ += a.data_size()` per *distinct* input buffer
   (`device.cpp:562`, `device.cpp:393-401`). With 406 dispatches and an op cap
   of 64 (low profile) or 400 (ranked), the op cap would give 7 or 2 command
   buffers per step; the measured 78 means the **volume** term binds. Fusing
   dispatches removes ops but not referenced volume, so it does not change
   command-buffer count and therefore does not change the 114 µs of
   boundary bubbles either.

So PR #9's zero is not evidence that per-dispatch cost is small in principle —
it is evidence that on this decode path *all* per-dispatch cost except the head
is already hidden behind a bandwidth-bound GPU.

## Command buffers per ranked M5 decode step

Belief: **~50 per step, with a plausible range of 40–60.**
**Now measured at ranked parity: median 48, mean 44.3** — the prediction below
was made before the trace and is confirmed. The op cap never binds.

How it was inferred *before* the measurement (and note this supersedes the
"~45/step" figure I quoted earlier, which was a low-memory-profile artifact I had
not yet traced to its cause):

* `Sources/MLXFastModel/RuntimeStartupMemoryPolicy.swift` `apply()` force-sets
  `MLX_MAX_MB_PER_BUFFER=128`, `MLX_MAX_OPS_PER_BUFFER=64` with
  `setenv(..., overwrite=1)` on hosts below 64 GiB — so **an external
  `MLX_MAX_*` value is silently ignored on any <64 GiB host**, which invalidates
  the obvious env-only screen (I burned one 6-arm run discovering this; the run
  became a useful 6-repeat A/A floor instead).
* `Sources/MLXFastModel/LagunaRuntimeWeights.swift:380-390` sets
  `MLX_MAX_MB_PER_BUFFER=200`, `MLX_MAX_OPS_PER_BUFFER=400` with
  `overwrite=0` on the full/ranked profile.
* Measured: 78 command buffers per step at a 128-unit threshold. The threshold
  unit is Mi-**elements**, not megabytes, because `buffer_sizes_` accumulates
  `a.data_size()`.
* Linear volume model: `78 × 128 ≈ 10.0 Gi` referenced elements per step, so a
  200-unit threshold gives `10.0 Gi / 200 Mi ≈ 50` command buffers. The op cap
  of 400 does not bind at 406 dispatches per step.
* The count cannot fall below the number of explicit `asyncEval`/`eval`
  boundaries in the step (~9 from the timeline), and coarse granularity —
  single expert-bank buffers are individually large — biases the real count
  slightly above the linear estimate.

Direct measurement of this at ranked parity is in progress (see below): the
`DARKBLOOM_STARTUP_MEMORY_PROFILE=full` canary shows the ranked profile **does
run on a 48 GiB host**, so the ranked command-buffer settings can be traced
locally rather than inferred.

## Second finding: the command-buffer volume threshold, and why it cannot simply be lowered


The same instrument showed 114 µs/step of GPU idle at command-buffer
boundaries, which made the threshold worth screening. Because the low-memory
profile force-sets the two env vars, this had to be screened under
`DARKBLOOM_STARTUP_MEMORY_PROFILE=full` — and the canary showed the ranked
profile **does** run on a 48 GiB host (a useful capability for the campaign:
ranked-parity command-buffer and BFS settings are locally reachable, at a
~3.4 % absolute step-time penalty from the profile's memory settings, so only
within-profile comparisons are valid).

`MLX_MAX_MB_PER_BUFFER` sweep, `MLX_MAX_OPS_PER_BUFFER=400`, full profile,
2000 steps/arm, parent-side wall ms/step:

| max_mb | ms/step (mean ± se) | n | vs ranked 200 |
| ---: | ---: | ---: | ---: |
| 8 | 9.0297 | 2 | −0.66 % |
| 16 | 9.0402 | 2 | −0.54 % |
| 25 | 9.0196 | 2 | −0.77 % |
| **50** | **8.9579 ± 0.0028** | 5 | **−1.45 %** |
| 100 | 9.0457 | 1 | −0.48 % |
| 200 (ranked default) | 9.0893 ± 0.0318 | 4 | — |
| 4096 | 9.4137 ± 0.0041 | 3 | +3.57 % |

A/A floor for this probe: 6 identical-config repeats spread 8.7460–8.7928
ms/step, sd 0.0176 ms = **0.20 %** of the mean, se 0.082 %. The `mb=50` arm
reproduced to within 16 µs across five separate model loads
(8.9627 / 8.9623 / 8.9472 / 8.9594 / 8.9580; sd 0.070 % of mean), so
`50` vs `200` is `t ≈ 4.1`.

One honesty note on the control: the four `mb=200` arms are **bimodal** —
9.0341, 9.0344 in one cluster and 9.1423, 9.1465 in the other, with nothing in
between. Every other configuration measured is unimodal to within 0.1 %.
Against the *faster* 200 cluster the `mb=50` advantage is 0.85 %; against the
mean it is 1.45 %. I do not know what selects the cluster (it survives a fresh
model load either way), and I would not promote a cap change without
understanding it.

The curve is **non-monotone with a minimum at 50**, not a monotone "smaller is
better". 50 is also MLX's own stock M5 Max default, which the repo raised to
200. `50` is the value at which each large routed expert bank (charged at 64
Mi-elements by the accounting below) lands in a command buffer of its own.

### What the threshold actually counts

`needs_commit()` compares `buffer_sizes_ >> 20` against `max_mb`, and
`buffer_sizes_ += a.data_size()` charges **elements**, once per *distinct input
buffer* per command buffer (`device.cpp:562`, `:393-401`). Three consequences,
all of which matter when reading the sweep:

1. The unit is Mi-**elements**, not MB. A uint32-packed NVFP4 bank is
   undercharged 4× relative to its bytes; a bf16 array 2×. The knob compares
   incommensurable quantities across dtypes.
2. A gather charges the **whole bank**. `gather_qmv`/`gather_qmm` register the
   full `w` and `scales` arrays (`quantized.cpp:700-707`), so each MoE layer
   charges ~144 Mi-elements (gate_up 64 + its scales 32 + down 32 + scales 16)
   while physically reading ~14 MB for its 8 routed experts — roughly a 10×
   overcharge relative to real traffic.
3. The bf16 embedding table is `100352 × 2048 = 205 520 896` elements, i.e.
   **196** after `>> 20`. So the very first `set_input_array` of a decode step
   trips the cut iff `max_mb ≤ 195`. That is why the first command buffer on
   this low-memory host (cap 128) contains exactly one op and commits at 26 µs,
   and it means **my measured front-idle structure does not transfer 1:1 to the
   ranked box**, where cap 200 lets the first command buffer keep growing past
   the embedding. Credit for spotting this goes to a delegated review of my
   trace.

So command-buffer placement is driven by a bookkeeping number that is neither
bytes nor real traffic. The practical implication is that this cap must be
tuned empirically per architecture and cannot be reasoned about as "MB".

### Calibration caveat that applies to the whole campaign

Bytes physically read per decode step, from the model geometry
(`LagunaConfig.swift:14-33`: hidden 2048, 8 KV heads, 39 MoE layers × top-8 of
256, dense layer 0, vocab 100 352) come to **≈2.2–2.9 GB/step**. At the M4 Pro's
273 GB/s nominal that is a 7.9–10.6 ms bandwidth floor, against a measured
GPU-busy region of 8.51 ms.

**This host's decode step is running at roughly 90–100 % of its
memory-bandwidth wall.** That is the structural reason a scheduling or
launch-overhead change tends to measure zero here — including PR #9's dispatch
fusion — and it is *not* evidence the same change is worthless on the ranked M5
Max, which has ~2× the achievable bandwidth for the same byte volume and
therefore exposes serialization that this bus hides. It also means the two
currencies on this host are bytes removed from the busy region and microseconds
removed from the 270 µs of idle; nothing else can move the local number.

That the `mb` sweep moves the local number by 1.45 % at all is therefore
informative: the effect has to live in the idle term, not the busy term. The
`FRIEREN_CBPROF` traces in the running screen test exactly that.

### Why this must not be shipped as a cap change

The ranked corpus already answers the blunt-knob question. From
`research/nezuko-normalised-leaderboard.md` §5.2, three official receipts change
only this cap against a common cap-200 frontier control (`8415f63c`,
S 97.820, T 4.3587 ms):

| cap | `T` vs frontier | `S` vs frontier |
| ---: | ---: | ---: |
| 400 | +0.056 % | +0.130 % |
| 240 | −0.069 % | +2.783 % |
| 160 | **−0.838 %** | **+1.464 %** |

So on the ranked M5 the decode step really does get faster as the cap falls —
the same sign as my M4 sweep — but prefill gets worse in both directions from
200. Scoring the 160 receipt end to end:

```
measured decode s/tok = T + S/128
frontier:  4.3587 + 97.820/128  = 5.1229 ms
cap 160:   4.3222 + 99.252/128  = 5.0976 ms
decode_speedup  = 5.1229 / 5.0976 = 1.00496
prefill_speedup = 97.820 / 99.252 = 0.98557
score ratio = 1.00496^0.75 * 0.98557^0.25 = 1.0001
```

Essentially zero. The cap is a **single knob that trades decode against
prefill**, and at the current operating point the trade is score-neutral. The
env value is read once into a `Device` member at first device construction
(`utils.h:178-188`, `device.h:235-236`), and `device.h`/`device.cpp` are outside
`editablePaths`, so it cannot be made phase-dependent from the submission
surface.

### The reachable version of the same win

Boundaries can be added to **decode only** from editable Swift, and the
machinery already exists: `decodeFireMask` /
`DARKBLOOM_DECODE_ASYNC_STAGE` fires `asyncEval(h)` after selected layers under
an `isSingleTokenDecode` guard (`LagunaRuntimeModel.swift:10517`, `:10768`,
`:10780`). Prefill has its own separate ladder, so a decode-only schedule
change leaves `S` untouched by construction — which is exactly what the cap
change cannot do.

That axis is already tuned at **layer** granularity (default
`at:0,1,7,15,23,31,39`; notes/52, two Latin squares, 66 runs: ladder8 1.0000,
ladder6 1.0064, ladder2 1.0169, ladder1 1.0178, `at:1,7,15,23,31,39` 1.0170).
The open question this arm raises is whether the remaining M4 win at `mb=50` is
**sub-layer** — cap 50 puts roughly one large expert bank per command buffer,
about 4× the boundary density of cap 200, which no layer-granularity schedule
can reproduce. The screen that separates the two is running (`mb ∈ {50, 200}` ×
`{default schedule, ladder1}`, plus the 195/196 crossing that isolates the
first-commit offset), and its result is the single most useful next decision.

## Serial non-speculative rule

Nothing in this arm changes what is computed. Both probes are read-only
timestamp recorders behind a default-off environment gate, and the arm produced
no candidate change to the scored surface. The measured invocation still
computes logits and KV rows only for the single supplied token, advances
logical and physical KV position by exactly one, and leaves no pending future
token, logits, deferred cache row, or cross-request state. No prompt-lookup,
drafting, lookahead, or multi-row target evaluation is involved anywhere in
this work.

## What I recommend next

Ordered by expected value per unit of risk.

1. **Sub-layer decode-only eval boundaries.** If the running screen shows
   `mb=50` still beating `mb=200` under `ladder1`, the remaining win is
   sub-layer and no layer-granularity schedule can reach it. The change is then
   an extra `asyncEval` at one or two intra-layer points under the existing
   `isSingleTokenDecode` guard — decode-only, so `S` is untouched by
   construction, unlike the cap. Bit-exact by construction (`asyncEval` forces
   evaluation of already-defined nodes, changing scheduling only). Local
   evidence for the size of the prize is the 0.85–1.45 % `mb` gap; ranked
   evidence for the sign is the cap-160 receipt's `T −0.838 %`. If the
   decode-only form captures `T −0.8 %` with `S` flat, that is
   `1.00718^0.75 = +0.54 %` of score — just under the 0.61 % bar on its own, so
   it needs either a slightly larger effect or pairing with another accepted
   change.
2. **Resolve the `mb=200` bimodality** before anyone treats the cap as tuned.
   Two clusters 1.2 % apart at an unchanged configuration is a bigger effect
   than most accepted submissions, and if it also occurs on the ranked box it
   contaminates every paired measurement taken at cap 200.
3. **Re-test the PR #9 dispatch-fusion patches on the ranked M5.** The
   bandwidth-wall calibration above says the M4 Pro cannot show a
   launch-overhead win at all. A zero here is not a zero there. This costs one
   official submission and would retire or revive a whole family of local
   negatives.
4. **Not recommended:** anything aimed at the 26 µs editable head region, the
   59 µs driver launch latency, or the 67.8 µs trusted harness segment. The
   first is too small, the other two are not on the submission surface.

A fifth idea surfaced in review and I did **not** pursue it because it needs an
organizer/advisor ruling first: the 30.1 µs `kernelEnd → GPUStart` component
looks like GPU idle-exit, paid once per step because the GPU power-gates during
the 153 µs front gap. A trivial input-independent 1-op command buffer committed
during that gap would pay the ramp earlier. It computes nothing, produces no
token, logits, or KV state, and is input-independent, so I read it as compliant
with the serial non-speculative rule — but it is added work in the timed window
and I would want that confirmed before spending a submission on it.

## Reproduction

```bash
# instrumented worker (research-only commits 0816a72, 9529e3a on this branch)
CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions --scratch-path .build-worker \
  --product mlxfast-runtime-worker

# Part 1 trace + analysis
FRIEREN_CBPROF=1 python3 research/frieren_host_cpu_probe.py \
  --warmup-steps 60 --measure-steps 300 2>/tmp/frcb.txt
python3 research/frieren_head_region.py /tmp/frcb.txt

# A/A floor and command-buffer threshold screens
research/frieren_cb_count_arms.sh
research/frieren_cbprof_ranked.sh

# Part 2 dose screen (10 arms, ~12 min) and its drift-cancelled contrasts
research/frieren_rung_dose.sh
python3 research/frieren_dose_stats.py
```

## Part 2 final: sub-layer boundaries are null-to-negative, and my per-boundary law is retracted

Position-balanced dose screen (`research/frieren_rung_dose.sh`), ranked parity,
2000 steps/arm, positions 1–9 = `off, ab, abc, abc, off, ab, ab, abc, off` so each
level's positions sum to 15 and a linear drift term cancels:

| arm | ms/step (n=3) | se | vs `off` | t |
| --- | ---: | ---: | ---: | ---: |
| `off` | 9.0677 | 0.0361 | — | — |
| `ab` (90 cb/step) | 9.0531 | 0.0140 | −0.161 % ± 0.427 % | −0.38 |
| `abc` (129 cb/step) | 9.2423 | 0.0047 | **+1.925 % ± 0.402 %** | **+4.79** |

Raw arms in script order: 8.9961 / 9.0729 / 9.2404 / 9.2511 / 9.1119 / 9.0260 /
9.0605 / 9.2353 / 9.0951, plus traced `abc` 9.2188.

Traced `abc`: 129 cb/step, GPU idle 265.3 µs, busy fraction 97.10 %, step 9189.9
µs, so GPU busy 8923.4 µs. Against traced control (48 cb, busy 8839.8) and traced
`ab` (90 cb, busy 8782.1), GPU busy across 48 → 90 → 129 boundaries goes
8839.8 → 8782.1 → 8923.4 µs. **Non-monotone**, so the −1.35 µs/boundary slope I
fitted from two points is refuted. Retracted.

Mechanism, corrected: the `max_mb` cap changes only *where a command buffer is
submitted* — same graph, same ops, same fusion, same buffer donation. `asyncEval`
changes the *graph partition*, forcing materialisation that blocks fusion and
buffer donation across the fire point, which adds real byte traffic. That is why
GPU busy rises with rung count. Sub-layer `asyncEval` is therefore not a proxy for
the cap, and since `device.h`/`device.cpp` are outside `editablePaths` the cap's
win is unreachable from the submission surface.

Rung `c` (forcing router top-k `inds`/`weights` before the expert gather) is worst:
it breaks the top-k → gather fusion and cuts a boundary on nearly every layer
(120 fires → 129 cb, i.e. ~39 boundaries from `c` alone against 42 from `ab`'s 80
fires).

Drift caveat: the three `off` arms are not exchangeable — position 1 read 8.9961
against 9.1119 / 9.0951 at positions 5 / 9 — so warm-up drift is *saturating*, not
linear, and linear position balancing does not fully remove it. Excluding position
1 post hoc gives `ab` −0.553 % ± 0.18 % and `abc` +1.524 %. Even the favourable
reading of `ab` is 0.553 % × 1.28 = 0.708 % of M5 step ⇒ `1.00713^0.75` =
**+0.53 % of score**, under the 0.61 % bar. The decision is unchanged either way,
so no further compute was spent sharpening it.

This independently reproduces the advisor's `FUSE=1` correction (comment
5181156130) from the opposite direction: removing 40 dispatches cost +0.228 ms;
adding 81 command buffers cost +1.93 %. **Decode-step graph repartitioning is
priced negative in both directions on this path.**

The sub-layer rung implementation (`DARKBLOOM_DECODE_SUBLAYER_ASYNC`) and the
`FRIEREN_CBPROF` / `FrierenStepProf` instrumentation are preserved in this
branch's history (`0816a72`, `9529e3a`, `9a00e8f`, `e722f65`, `a309168`) but are
reverted out of the branch head, so `Sources/` and `Vendor/` are byte-identical to
the assignment base `7017ba2`.
