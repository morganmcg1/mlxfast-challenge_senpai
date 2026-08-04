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

## Part 1 — the three requested numbers

Medians over 278 steady steps, microseconds. `se` is the standard error of the
median (bootstrap-free, from the interquartile spread).

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

Both conditions hold. Driver latency (59.1 µs) is 2.3× the host portion
(26.0 µs), and the host portion is 26 µs — a quarter of the 0.1 ms threshold.
Even a perfect, physically impossible elimination of every editable host
microsecond in the head region is worth 26 µs, i.e. 0.30 % of this host's step
and **0.60 % of the 4.353 ms ranked M5 step**, which converts to roughly
0.3–0.45 % of score — below the 0.61 % acceptance bar before any measurement
noise. So Part 2 (moving the first commit earlier) cannot clear the bar on its
own and I did not spend a submission on it.

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

How inferred (and note this supersedes the "~45/step" figure I quoted earlier,
which was a low-memory-profile artifact I had not yet traced to its cause):

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

## Serial non-speculative rule

Nothing in this arm changes what is computed. Both probes are read-only
timestamp recorders behind a default-off environment gate, and the arm produced
no candidate change to the scored surface. The measured invocation still
computes logits and KV rows only for the single supplied token, advances
logical and physical KV position by exactly one, and leaves no pending future
token, logits, deferred cache row, or cross-request state. No prompt-lookup,
drafting, lookahead, or multi-row target evaluation is involved anywhere in
this work.

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
```
