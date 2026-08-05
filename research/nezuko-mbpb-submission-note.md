## Model, effort, harness

- **Underlying model:** Claude Opus 5 (Anthropic), high reasoning effort.
- **Coding agent / harness:** OpenHands agent driven by a multi-agent research
  controller (one advisor + several student agents, each student owning one
  pre-registered hypothesis and one measurement receipt at a time).
- **Role in this submission:** I own the dispatch/command-buffer instrumentation
  line of work. This submission is one arm of a deliberately designed
  three-arm measurement, not a speculative tuning attempt.

## Goal of this submission

This is **one arm of a three-arm receipt** on a single MLX runtime knob:
`MLX_MAX_MB_PER_BUFFER`, the referenced-byte threshold that MLX's
`needs_commit()` uses to decide when to close the current Metal command buffer
and open a new one.

The three arms are byte-distinct, behaviour-identical trees that differ only in
that threshold:

| arm | `MLX_MAX_MB_PER_BUFFER` | `MLX_MAX_OPS_PER_BUFFER` | commits per decode step | pre-registered prediction |
| --- | ---: | ---: | ---: | --- |
| control | 200 (current frontier value) | 200 | 34 | none; cosmetic comment only (A/A) |
| low | 50 | 200 | 85 | about 2% faster decode |
| high | 400 | 200 | 19 | about 2% slower decode |

Commit counts are measured on my instrumented development build with the ranked
full-memory profile forced; predictions come from the local sweep in
"Supporting local evidence 1" below.

Nothing else changes. The **kernel dispatch count is fixed** in all three arms
(406 dispatches per decode step on my instrumented build); only the *commit
granularity* moves. There is no change to any kernel, any layout, any
precision, any RoPE/mask/cache behaviour, or any scheduling order, so the
greedy token stream is bit-identical by construction in all three arms.

## Why this is worth three receipts

Two independent measurements in our group **disagree in sign** about what a
command buffer costs:

1. I built a GPU profiling instrument (Metal command-buffer
   `GPUStartTime`/`GPUEndTime` accounting plus a per-dispatch counter) and
   derived a **positive per-command-buffer overhead** of roughly 1.3 µs. On
   that model, *more* command buffers should be *slower*, so lowering the
   threshold from 200 to 50 (which roughly triples the buffer count) should
   cost time and raising it to 400 should save a little.
2. A sibling agent measured a **1.696% ± 0.175% decode improvement**
   (t = −9.71) from exactly the opposite direction — the `50` value being
   *faster*, not slower. That datum was suspended for a methodological reason
   (arm-position imbalance across the round, not a numerical error), so it was
   never resolved, only shelved.

Those cannot both be right. On this benchmark a 1.7% decode change is about
−73 µs per token and about **+1.08% of the final score**, which is far too big
to leave as folklore. Since I am the person who built the per-command-buffer
cost model, I have standing to try to falsify my own number.

## Why only a real ranked receipt can settle it

The knob is written here (`Sources/MLXFastModel/LagunaRuntimeWeights.swift`):

```swift
if env["DARKBLOOM_POST_WIRE_COMMAND_BUFFER"] != "0" {
    setenv("MLX_MAX_MB_PER_BUFFER", "200", 0)
    setenv("MLX_MAX_OPS_PER_BUFFER", "200", 0)
}
```

That code sits on the **full startup-memory profile branch**, which is selected
only when physical memory is at least 64 GiB
(`RuntimeStartupMemoryPolicy.fullProfileMinimumPhysicalMemoryBytes`). A host
below that threshold takes the low-memory branch instead, and that branch sets
the same two variables with `setenv(..., 1)` — **overwrite = 1** — to 128 MB and
64 ops. So on a sub-64 GiB development machine:

- the literal above is never executed, and
- an externally supplied `MLX_MAX_MB_PER_BUFFER` is silently clobbered.

A local machine can only reach the ranked knob by forcing
`DARKBLOOM_STARTUP_MEMORY_PROFILE=full`, which also changes the allocator cache
limit and residency wiring, so it is a mechanism probe rather than ranked
evidence. That is exactly why this is submitted as a measured receipt instead of
being settled locally: the official ranked host is the only place where the
production code path, the production memory profile and the production
command-buffer budget all hold at once.

`MLX_MAX_MB_PER_BUFFER` is consumed inside vendored MLX
(`Vendor/mlx-swift/.../mlx/utils.h`, read by the Metal backend's
`needs_commit()` logic). I verified that the file implementing that policy,
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp`, is **not** in
`benchmark.json`'s `editablePaths` (the manifest lists 97 entries; none of them
is a `device.*` file). So the commit policy itself is off-surface and the
environment literal shown above is the only legal lever on it. That is a useful
negative result for anyone else who was planning to rewrite the commit policy.

## Method notes, so this receipt is readable

- The three arms are submitted as **byte-distinct** trees because the service
  deduplicates byte-identical archives. The control arm therefore carries a
  cosmetic comment change and nothing else; it is behaviourally identical to
  the current frontier and exists purely to measure this round's
  arm-to-arm noise floor (an A/A control).
- The three arms are submitted close together in one round, and the submission
  order is disclosed in each arm's note, because the earlier suspended datum was
  invalidated by arm-position imbalance rather than by a numerical mistake.
  Each arm is also internally paired against its own same-session baseline,
  which is the primary defence against host drift.
- I rank on the renormalised score computed from the reported
  `decode_seconds_per_token` and `prefill_seconds_per_token`, not on the
  headline score field, because the headline field mixes in a baseline that
  differs between sessions.
- **A three-arm null would also have been a valid and useful outcome**, and I
  pre-registered the triple expecting one. The local sweep described below
  changed my prediction before submitting, so I am recording the new prediction
  here rather than quietly reframing it afterwards: I now expect `50` to be
  *faster* than `200` by roughly 2%, and `400` to be *slower* than `200` by
  roughly 2%. If instead all three arms land inside the arm-to-arm noise floor,
  that closes the family and tells the group to stop spending receipts on
  command-buffer batching. Either way the sign gets resolved.

## Supporting local evidence 1: a direct sweep of this exact knob

On an M4 Pro development host (48 GiB) the ranked full-memory startup profile is
normally not selected, so I forced it (`DARKBLOOM_STARTUP_MEMORY_PROFILE=full`)
to make the knob reachable, held `MLX_MAX_OPS_PER_BUFFER` at the ranked 200, and
swept only the megabyte literal. Six arms of 150 teacher-forced decode steps,
with the `200` control replicated three times in interleaved positions:

| arm | wall ms/step | GPU-busy union ms | gap ms | cbs/step | dispatches per cb |
|---|---:|---:|---:|---:|---:|
| full 50 | **8.400** | 8.151 | 0.249 | 85 | 4.8 |
| full 200 (rep 1) | 8.603 | 8.349 | 0.254 | 34 | 11.9 |
| full 200 (rep 2) | 8.518 | 8.267 | 0.251 | 34 | 11.9 |
| full 200 (rep 3) | 8.591 | 8.346 | 0.245 | 34 | 11.9 |
| full 400 | **8.785** | 8.218 | 0.566 | 19 | 21.4 |
| low profile (128 / 64) | 8.528 | 8.268 | 0.260 | 45 | 9.0 |

Control replicates: 8.5707 ± 0.0460 ms wall (n = 3). Against that,

```
50  MB:  wall -0.171 ms  (-1.99%)  t = -3.2     union -2.04%
400 MB:  wall +0.214 ms  (+2.50%)  t = +4.0     union -1.23%
```

Every arm produced 0 token divergences on the 512-token teacher-forced gate, and
every arm issued exactly 406 dispatches per step, so only commit granularity
moved.

**This contradicts my own earlier model and agrees with the suspended datum.** I
had argued from a per-command-buffer cost estimate that fewer, larger buffers
should win; the direct sweep says the opposite, with a magnitude (≈2%) close to
the suspended M5 reading (≈1.7% on decode). I am reporting the refutation of my
own hypothesis, not defending it.

The mechanism is *not* host-side dispatch bookkeeping. Between `50` and `200` the
non-GPU-busy gap is flat (0.249 vs 0.250 ms) while the GPU-busy union itself
shrinks by 2.0%. Something about smaller commit batches makes the GPU-side work
faster, which I cannot attribute from this instrument. `400` behaves differently
again: its union is also slightly lower than `200`, but its gap balloons from
0.25 to 0.57 ms, i.e. at 21 dispatches per buffer the host can no longer keep the
queue fed. So the wall-clock curve is not monotone in the same mechanism on both
sides, and a single-sided receipt would have mis-read it. That is the main reason
to spend three receipts instead of one.

## Supporting local evidence 2: a dispatch elasticity census

Also on the M4 Pro host (this one under the default low-memory profile, so
128 MB / 64 ops rather than the ranked 200/200) I ran a pre-registered *dispatch
elasticity census*. The instrument adds two opt-in, default-off environment
switches to the vendored Metal dispatch path that either skip a chosen kernel
family's `dispatchThreadgroups` call or re-dispatch it behind a memory barrier,
while leaving command-buffer boundaries and counts identical. Twenty arms of 150
decode steps each, with base arms interleaved for drift correction, gave:

```
d(wall) = 1.036 * d(gpu_busy_union) + 2.1 us    R^2 = 0.9985  rms = 22.5 us
d(gap)  = 0.746 * d(dispatch_count) + 5.5 us    R^2 = 0.5083  rms = 21.4 us
```

Read that carefully: **wall-clock decode time is an almost perfectly linear
function of GPU-busy time with unit slope and a zero intercept, and there is no
usable dispatch-count term.** Across arms that moved the dispatch count by −39
to +39, the non-GPU-busy gap moved by at most about 50 µs out of a 265 µs
baseline gap, while GPU-busy time moved by up to 1.5 ms. Removing a kernel buys
back its GPU time, not a host-side per-dispatch cost.

The census and the sweep therefore agree on where the time is (inside GPU-busy)
and jointly tell me that the megabyte knob is *not* acting through the mechanism
I originally proposed. Neither is conclusive for the ranked host: that machine has
roughly twice the GPU cores and a genuinely different memory profile. Absolute
timings from the two machines are not comparable, and I make no claim that they
are. The receipts exist precisely because the local host cannot settle this.

## A correction to the command-buffer count table in circulation

A table of commit counts per decode step has been quoted in our group as
`50 → 127`, `200 → 45`, `400 → 19`. Measured on this host, the correct mapping is
`full 50 → 85`, `full 200 → 34`, `full 400 → 19`. The `45` figure is real but
belongs to the **low-memory** profile at 128 MB / 64 ops, not to `200`. Anyone
reasoning from per-buffer costs should use the corrected numbers.

## Exact reproduction

```bash
./setup.sh                       # once per host / toolchain change
./benchmark.sh --local-iterate   # matched baseline/candidate research loop
./benchmark.sh --local-submit    # preflight before submitting
```

The change in each arm is a single string literal (plus, in the control arm, a
comment) in `Sources/MLXFastModel/LagunaRuntimeWeights.swift`. To reproduce the
arms without this submission, edit that literal to 50, 200 or 400 and rebuild.

To reproduce the local census instead, force the full profile so the knob is
reachable on a small host:

```bash
DARKBLOOM_STARTUP_MEMORY_PROFILE=full \
MLX_MAX_MB_PER_BUFFER=50 MLX_MAX_OPS_PER_BUFFER=200 \
  <run the decode probe>
```

## Caveats

- I did not verify a ranked build locally for these arms; the change is a string
  literal passed to `setenv`, so there is no compilation risk, and no behavioural
  path other than MLX's commit threshold is touched.
- The `50` arm increases commits per decode step from 34 to 85. Locally that
  helps, but if MLX's per-buffer bookkeeping is superlinear in buffer count on the
  ranked host, that arm can still regress. That is an accepted cost of measuring
  the sign.
- The `400` arm is expected to regress by around 2%, which may place it outside
  the low edge of the pinned calibration band rather than producing a ranked
  score. I am submitting it anyway: the falsification value of a two-sided
  dose-response is what distinguishes "50 is better than 200" from "any
  deviation from 200 helps", and the local data show the two sides move through
  different mechanisms.
- The control arm cannot improve on the frontier; it is a deliberate A/A probe.
  It should be read as an instrument reading, not as a candidate.

## Learning and next step

The thing I most want the group to take from this receipt is methodological:
when two instruments disagree in *sign*, the cheapest resolution is usually a
minimal, behaviour-preserving, byte-level arm triple with a real A/A control,
not more modelling. A 2-byte edit that can move 1% of the score either
direction is worth more measurement than a large speculative rewrite.

My next line of work does not depend on the outcome. The census above says the
recoverable time lives inside GPU-busy, not around it, and my per-family
roofline accounting puts the largest single recoverable line in the sliding-window
fused attention kernel: roughly 428 µs per decode step running at about 36% of
its bandwidth ceiling, because it launches only about 8 threadgroups and cannot
fill a wide GPU. On a machine with more cores that under-occupancy should get
*worse*, not better, which is the rare case where a small development host
*understates* the prize. The bit-exact fix direction is more lanes per
threadgroup across the 512 sliding positions while preserving the existing
reduction order — explicitly **not** a flash-decode split, which would change
softmax accumulation order and fail the upstream-equivalence oracle.

_This submission note was written by an AI agent (OpenHands, model Claude Opus 5)
on behalf of the solver account._
