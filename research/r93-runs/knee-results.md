# R93 Arm B pre-flight: the injected-dispatch cost curve is convex, not linear

Host: Apple M4 Pro, 48 GiB, low-memory startup profile. Worker
`.build-worker/release/mlxfast-runtime-worker`, unmodified base source; the rung
is supplied through `DARKBLOOM_INJECT_DECODE_EMPTY` for the local sweep only.
`DARKBLOOM_INJECT_EMPTY_TG=8`, chained and spread, matching the historical M5
ladder receipts. 120 teacher-forced decode steps per point, one process per
point, sequential.

**This is directional M4 evidence and is not offered as an M5 measurement.** Its
only job was to place the three official rungs somewhere informative.

## Measured curve

| K | mean ms | median ms | p10 | p90 | greedy tokens |
| --- | --- | --- | --- | --- | --- |
| 0 | 8.223 | 8.209 | 8.180 | 8.247 | 0 divergences |
| 240 | 8.131 | 8.105 | 8.062 | 8.211 | 0 divergences |
| 480 | 8.125 | 8.098 | 8.069 | 8.180 | 0 divergences |
| 800 | 8.456 | 8.283 | 8.239 | 8.742 | 0 divergences |
| 1200 | 8.597 | 8.576 | 8.518 | 8.645 | 0 divergences |
| 1600 | 9.409 | 9.368 | 9.232 | 9.575 | 0 divergences |
| 2400 | 11.344 | 11.259 | 11.156 | 11.509 | 0 divergences |
| 0 (repeat) | 8.218 | 8.207 | 8.167 | 8.242 | 0 divergences |

The sweep opened and closed on `K = 0`. Those two points are 4.5 minutes apart
and their medians differ by 0.02 %, so host drift over the sweep is far smaller
than the effects below and the ordering of the points is not driving the shape.

Segment slopes from the medians, in µs per injected dispatch:

| segment | µs/dispatch |
| --- | --- |
| 0 → 240 | −0.43 |
| 240 → 480 | −0.03 |
| 480 → 800 | +0.58 |
| 800 → 1200 | +0.73 |
| 1200 → 1600 | +1.98 |
| 1600 → 2400 | +2.36 |

The marginal price rises monotonically with `K`. Up to a few hundred extra
dispatches per decode step the added time is indistinguishable from zero — the
0 → 480 segment is very slightly negative, which is drift, not a speedup. Past
roughly 500–800 the price climbs and appears to approach something in the
2–2.5 µs range.

The natural reading is that this decode step has slack between CPU-side command
encoding and GPU-side execution. While the encoder is ahead of the GPU, extra
empty dispatches are absorbed. Once the injected encode work exceeds that slack,
the encoder becomes the critical path and every further dispatch is charged
close to its full price.

## Why this matters for the official ladder

The historical M5 ladder receipts (2026-08-05 tree, `c3ce66ec` / `57306132` /
`0411779d`, `K` = 0 / 100 / 400) fit a single straight line at **1.98
µs/dispatch with no free region at all**: the M5 was already paying full price
at `K` = 100. The current tree on M4 pays nothing at `K` = 480. Those two facts
cannot both describe the same instrument on the same code, so one of the
following is true:

1. the free region is an M4-Pro property that the M5 does not have; or
2. the current tree has acquired slack that the 2026-08-05 tree did not have,
   in which case the historical 1.98 µs figure is stale for our purposes.

Either answer changes how we price a dispatch-removing optimisation, so the
official ladder has to be able to tell them apart.

## Rung selection

We had originally planned `K ∈ {40, 120, 240}`. Every one of those points sits
inside the free region on this host, so under hypothesis (2) all three receipts
would have returned "zero" and the experiment would have bought nothing.

Chosen rungs: **`K ∈ {240, 800, 1600}`**, with `K = 0` supplied by the Arm A
nulls in the same submission window.

- `K = 240` is the discriminator. Hypothesis (1) predicts +476 µs (+9.7 % of the
  4894 µs candidate decode we measured on the M5 in `25e1f18e`). Hypothesis (2)
  predicts ~0. Our decode noise floor is 0.29 %, so these are ~33 σ apart. One
  receipt settles it, and if the answer is "zero" it converts into a hard upper
  bound of roughly 0.06 µs/dispatch on the cheap regime.
- `K = 800` sits just past the M4 knee.
- `K = 1600` sits in the expensive regime where the M4 marginal price is near
  2 µs, and gives the large-`K` slope.

Floor safety on M5, using the worst case (the historical linear 1.98 µs/dispatch
and the `25e1f18e` session baseline of 13 819 µs decode):

| K | predicted cand decode µs | predicted decode speedup |
| --- | --- | --- |
| 240 | 5 370 | 2.57 |
| 800 | 6 478 | 2.13 |
| 1600 | 8 062 | 1.71 |

All far above the `0.95` decode floor. Prefill is untouched by this knob and
stays an internal control. Wall-clock risk is bounded too: the timed phase in
`25e1f18e` was 45 s, and even a 65 % decode inflation keeps the run well inside
the observed 52 s benchmark envelope plus correctness time.

## The rung really is carried by the source constant

The sweep above drove `K` through the environment. The ranked host never sees
our environment, so before spending an official run we rebuilt with the rung
compiled in and re-ran the probe with **no injection environment set at all**
(`research/r93-runs/verify_source_constant.sh`):

| source constant | worker sha256 | median ms | greedy tokens |
| --- | --- | --- | --- |
| `K = 2400`, TG 8 | `2ad01385…` | 11.276 | 0 divergences |
| `K = 0`, TG 160 (base) | `53fae224…` | 8.199 | 0 divergences |
| `K = 240`, TG 8 | `d98dfe80…` | 8.136 | 0 divergences |

The source-constant `K = 2400` build reproduces the environment-driven `K = 2400`
point (11.276 vs 11.259 ms median) to within 0.15 %, so the two channels agree
and the compiled-in rung is what the ranked host will execute.

## Why small `K` is free: the injected dispatches carry no hazard

A static trace of the dispatch path explains the shape. The injected kernels
bind only their own control/previous/sink buffers; they never touch a tensor the
model reads or writes. MLX inserts ordering (a `MTLFence` wait, or an
intra-encoder `memoryBarrier`) only when a new encoder's inputs intersect a
prior encoder's outputs, so a hazard-free chain has nothing to wait for. With
per-layer `asyncEval` finalisation and a commit cadence of a few tens of ops per
command buffer, these tiny hazard-free command buffers can be scheduled into
whatever gaps already exist between the model's own GPU work, and decode leaves
gaps: roughly a millisecond per step of CPU-side graph building.

That has a direct and uncomfortable consequence for the deliverable. **The empty
ladder measures the price of a dispatch that has no dependency on the model's
data.** A real dispatch that we might delete from the decode path consumes the
previous operation's output, so it does serialise. The ladder slope is therefore
a *lower bound* on the value of removing a real dispatch, and in a regime with
scheduling slack it can be a very weak one. We keep the empty ladder as the
primary instrument because it is exactly the instrument the historical M5
receipts used, and resolving those receipts is the point; but we publish the
number with that ceiling/floor distinction attached rather than as "the price of
a dispatch".

## Correctness

Greedy teacher-forced decode matched the public golden with **zero divergences
at every point in the table**, including `K` = 2400. The injected work reads no
model state and writes nothing that is consumed, so this is expected; we ran it
anyway because "expected" is not evidence.

## Hazard / command-buffer-split control (job `528661f0`, 2026-08-09T03:34Z)

Hypothesis under test: the sub-linear "free region" at low K is an artefact of
MLX splitting the decode step into several Metal command buffers, so injected
kernels ride along inside an already-paid buffer until a split boundary is
crossed.

Control: rerun K in {0, 240, 800} with the buffer-split limits effectively
disabled (`MLX_MAX_OPS_PER_BUFFER=1000000`, `MLX_MAX_MB_PER_BUFFER=1000000`)
and compare against the default-limit arm in the same job, same host, same
120 teacher-forced steps, TG=8.

| K | default mean ms | bigbuf mean ms | delta | default median | bigbuf median |
|---|---|---|---|---|---|
| 0   | 8.219 | 8.260 | +0.50 % | 8.203 | 8.227 |
| 240 | 8.134 | 8.137 | +0.04 % | 8.122 | 8.121 |
| 800 | 8.285 | 8.283 | -0.02 % | 8.255 | 8.254 |

All six points: 0 token divergences.

**Verdict: hypothesis rejected.** Removing the command-buffer split limits does
not move any rung by more than the ~0.5 % run-to-run noise, and it does not
flatten or steepen the 0 -> 240 -> 800 shape. Command-buffer granularity is not
what makes the first few hundred injected dispatches free.

The surviving explanation is the CPU/GPU overlap one: on this M4 Pro a
single-token decode step spends on the order of a millisecond building and
encoding the MLX graph on the CPU, and the injected chain is hazard-free (it
binds only its own control/prev/sink buffers, never a model tensor, so MLX
inserts no `MTLFence` wait), so a few hundred extra GPU dispatches complete
inside that CPU shadow and cost nothing. Past roughly K~800 the injected GPU
chain is longer than the CPU shadow and each further dispatch starts showing up
at ~2 us.

Consequence for the ladder, restated: the empty-kernel ladder prices a
*hazard-free* dispatch. That is a lower bound on the value of deleting a real,
serialising dispatch from the scored path, and on a machine whose CPU shadow is
shorter (or whose GPU is faster) the same K can be entirely visible instead of
entirely free. The historical M5 receipts show exactly that: linear from K=0
with no free region.

