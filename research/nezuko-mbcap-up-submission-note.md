# One-token submission: MLX command-buffer byte cap 200 MB -> 512 MB

Arm identity, for later attribution via `mlxfast submission-note <id>`:
**`MLX_MAX_MB_PER_BUFFER=512, MLX_MAX_OPS_PER_BUFFER=200`**, everything else at
the base tree's values (`MLX_BFS_MAX_WIDTH=50`).

## Model, effort, harness

- **Underlying model:** Claude Opus 5 (Anthropic), high reasoning effort.
- **Coding agent / harness:** OpenHands, driven by a multi-agent research
  controller — one advisor plus several student agents. Each student owns one
  pre-registered hypothesis and at most one in-flight ranked receipt, and the
  ranked-host channel is a serialised resource handed between students.
- **My role:** I own the MLX dispatch / command-buffer instrumentation axis.
  This is the second and final receipt on that axis. Like the first, the whole
  submitted diff is one numeric literal, because the submission is a
  *measurement* whose job is to pin down a slope, not a tuning attempt.

## Goal

Move MLX's referenced-byte command-buffer threshold from 200 MB to 512 MB and
measure what happens on the ranked M5 Max when command-buffer boundaries are
**removed** rather than added.

The entire submitted diff is one file and one token,
`Sources/MLXFastModel/LagunaRuntimeWeights.swift`:

```swift
 setenv("MLX_BFS_MAX_WIDTH", "50", 0)
 if env["DARKBLOOM_POST_WIRE_COMMAND_BUFFER"] != "0" {
-    setenv("MLX_MAX_MB_PER_BUFFER", "200", 0)
+    setenv("MLX_MAX_MB_PER_BUFFER", "512", 0)
     setenv("MLX_MAX_OPS_PER_BUFFER", "200", 0)
 }
```

`git diff --stat` against the base commit is literally
`Sources/MLXFastModel/LagunaRuntimeWeights.swift | 2 +-`, one insertion, one
deletion, zero file additions or deletions, zero bytes of growth against the
editable-surface budget.

## Where the knob acts, and why it is behaviourally inert

`MLX_MAX_MB_PER_BUFFER` is read once at MLX Metal device construction and
feeds `needs_commit()`. MLX accumulates encoded ops into a Metal command
buffer and force-commits when either the op count exceeds
`MLX_MAX_OPS_PER_BUFFER` or the total *referenced bytes* of the buffer's inputs
and outputs exceed `MLX_MAX_MB_PER_BUFFER`. Raising the byte cap therefore
changes only **where GPU work is cut into command buffers**. It changes no
kernel, no dispatch, no threadgroup geometry, no launch order, no precision, no
memory layout, and no arithmetic. The number of *dispatches* is invariant; only
the number of *commits* changes.

That is what makes it a clean instrument. Every other axis in this challenge
changes work and boundaries at the same time, so a receipt cannot separate the
two. This knob moves boundaries with work held exactly fixed.

## What the previous receipt on this axis established

The first receipt went the other way: 200 MB -> **50 MB**, i.e. *more*
boundaries.

| quantity | control (200 MB) | receipt (50 MB) |
| --- | --- | --- |
| commits per decode step | 34 | 85 |
| commits in the 512-token prefill | 81 | 160 |
| dispatches per decode step | 406 | 406 |
| `cand_pre` | 191.308 us | 195.502521 us |
| `cand_dec` | 5.04644 ms | 5.1195537 ms |
| normalised score `ns` | 2.544360 | 2.503448 |
| delta | — | **-1.608%** |
| `max_abs_diff` | 0 | 0 |

It **refuted** the hypothesis it was sent to test (an M4 Pro wall-clock decode
win of about -1.8% at 50 MB), and in refuting it produced something more
valuable: a calibrated two-axis cost of a command-buffer boundary on the ranked
host. Decomposing the receipt on the score's own axes — where
`S = 512 * cand_pre` is total prefill time and
`T = cand_dec - S/128` is the marginal decode cost per step —

- **decode: +1.1045 us per commit** (56.34 us of extra `T` over 51 extra
  commits)
- **prefill: +27.177 us per commit** (2.147 ms of extra `S` over 79 extra
  commits)

and, via `d(ln score)/dT = -14.862 %/ms` and `d(ln score)/dS = -0.371 %/ms`,

- **+0.016415% of score per removed decode commit**
- **+0.010092% of score per removed prefill commit**

The prefill boundary is ~25x more expensive in absolute time but the decode
boundary is worth ~1.6x more score, because decode carries 75% of the exponent
and is amortised over 128 steps.

It also yielded a transfer law that I think is the most portable thing on this
axis:

> **Command-buffer *counts* transfer M4 -> M5 exactly. Command-buffer boundary
> *timing* does not transfer, not even in sign.**

M4 Pro wall-clock said 50 MB was ~1.8% *faster*; the ranked M5 said it was
1.608% *slower*. But the commit counts I measured on M4 (34 at 200 MB, 85 at
50 MB, 81 prefill commits at 200 MB) reproduced the ranked host's counts
exactly. So M4 is a free *counter* and a misleading *stopwatch*.

## This receipt: using the free counter and paying only once

The transfer law says I can map the entire upward direction of the knob on the
local M4 host for zero ranked budget, as long as I only read commit counts and
never wall-clock time. So the whole sweep was done locally first.

Sweep command (single supervised process, all five caps in one pass, one build):

```bash
# from the repo root, one model-holding process
research/nezuko_mbpb_up_sweep.sh    # caps 200 400 512 1024 2048
# raw log preserved at research/nezuko_mbpb_up_sweep.log
```

Every cell reported **406 dispatches per decode step, 0 divergences,
`gpu_busy_sum == gpu_busy_union`, `peak_ram_gb 20.72`** — i.e. the knob is
inert on work, serialisation, and memory across the whole range.

| cap (MB) | decode cb/step | prefill cb | `mlx_peak_gb` | M4 `gpu_busy` decode (ms) | M4 wall decode (ms) | host gap |
| --- | --- | --- | --- | --- | --- | --- |
| 200 (base) | 34.0 | 81 | 36.39 | 8.335 | 8.599 | 0.265 (3.1%) |
| 400 | 19.0 | 42 | 36.94 | 8.181 | 8.854 | 0.673 (7.6%) |
| **512** | **18.0** | **41** | 36.94 | 8.233 | 8.734 | 0.501 (5.7%) |
| 1024 | 13.0 | 41 | 36.94 | 8.248 | 8.874 | 0.626 (7.1%) |
| 2048 | 9.0 | 41 | 36.94 | 8.271 | 8.915 | 0.644 (7.2%) |

Two structural facts fall out:

1. **Prefill has a hard commit floor of 41**, first reached at 512 MB. Beyond
   512 the prefill axis is saturated — those commits are forced by the op cap
   (`MLX_MAX_OPS_PER_BUFFER=200`) and by real synchronisation points, not by
   the byte cap.
2. **Decode has no floor below 2048.** It keeps falling 34 -> 19 -> 18 -> 13 ->
   9.

Applying the calibrated per-commit score costs:

| cap | decode cb delta | prefill cb delta | predicted `d_ns` |
| --- | --- | --- | --- |
| 400 | -15 | -39 | +0.640% |
| **512** | **-16** | **-40** | **+0.666%** |
| 1024 | -21 | -40 | +0.748% |
| 2048 | -25 | -40 | +0.814% |

### Why I picked 512 and not 2048

The naive move is to take the largest predicted number. I did not, for four
reasons, all pre-registered before submitting:

- **512 captures the whole saturating axis.** It takes all 40 removable prefill
  commits — the larger half of the predicted win (+0.404% of +0.666%) — and 16
  of the cheap decode commits.
- **512 -> 2048 is worth +0.148%, which is about 1 sigma.** The repeat
  coefficient of variation of `ns` on this harness is 0.149%. With exactly one
  receipt available, the difference between 512 and 2048 is *undecidable*.
  Spending the receipt on a distinction I cannot resolve wastes it.
- **The local counter shows the linear count law breaking down at the top of
  the range.** M4 `gpu_busy` decode is *minimised at 400* (8.181 ms) and then
  rises monotonically to 2048 (8.271 ms). GPU-busy time is a work measure, not
  a wall measure, so unlike wall clock it is not obviously inadmissible under
  the transfer law. It says something real starts to cost as buffers get very
  large — plausibly reduced overlap between commit-boundary-delimited work, or
  allocator pressure from longer-lived reference sets. 2048 MB is a 3.8x
  extrapolation of a slope fitted at 34-85 commits, into a regime of 9
  commits/step where the local instrument is warning me.
- **512 is not an arbitrary number.** It restores the value this line of the
  runtime held before an earlier commit lowered it, so it is a value the tree
  has already been shaped around.

Memory is a non-issue: `mlx_peak_gb` moves 36.39 -> 36.94 (+0.55 GB) and
saturates immediately at 400, on a 128 GB ranked host.

## Numerical inertness: the control I ran before submitting

The upstream-equivalence oracle (`research/run_upstream_equivalence.sh`)
returns rc=1 on my local host. Before spending the receipt I had to know
whether that was *my token* or *my host*.

So I replayed the **same built binary** at three caps using the environment
override — the runtime uses `setenv(..., 0)` with overwrite=0, so an explicit
environment variable wins and no rebuild is needed, which removes any
build-difference confound:

```bash
research/nezuko_equiv_control.sh   # caps 200 (base), 50 (prior receipt), 512 (this arm)
# raw log at research/nezuko_equiv_control.log
```

| `MLX_MAX_MB_PER_BUFFER` | role | prefill max abs logit err | prefill mean abs err | decode steps exact | argmax tokens match |
| --- | --- | --- | --- | --- | --- |
| 200 | base / revert target | 0.125 | 0.011933609 | 8 / 8 | yes |
| 50 | prior receipt | 0.125 | 0.011933609 | 8 / 8 | yes |
| **512** | **this arm** | 0.125 | 0.011933609 | 8 / 8 | yes |

The three per-cap step blocks are **byte-identical** (md5
`9e46ee364ceaf57dbbab59b28dca78b3` for all three). Every argmax token matches
(5991 / 509 / 902, repeating). All eight decode steps are exactly 0 error at
every cap. The divergence is entirely prefill and entirely invariant to the
submitted token, so it is a property of host + base rather than of this change.

That is the documented local-host case: this machine reports Apple GPU
generation 16 and does not select the `_nax` prefill kernel variants the ranked
M5 uses — and the divergence is prefill-only, i.e. exactly the axis whose
kernel family differs. Decode, which carries 75% of the score weight, is
bit-exact at all three caps.

The independent local gate agrees that nothing is wrong with the token:
`./benchmark.sh --local-iterate` reports `passed_correctness true`,
`max_abs_diff 0`, golden hash `b9509697...` matched, `peak_ram_gb 21`.

## Exact reproduction

```bash
# base checkout: the promoted frontier commit, then one token changed
sed -i '' 's/setenv("MLX_MAX_MB_PER_BUFFER", "200", 0)/setenv("MLX_MAX_MB_PER_BUFFER", "512", 0)/' \
  Sources/MLXFastModel/LagunaRuntimeWeights.swift

./setup.sh
./benchmark.sh --local-iterate      # correctness + directional local timing
research/run_upstream_equivalence.sh
research/nezuko_equiv_control.sh    # 3-cap numerical inertness control
./benchmark.sh --local-submit
mlxfast submit --note-file <this file> --model "Claude Opus 5"
```

Equivalent without touching the source, for anyone who just wants to see the
counts move:

```bash
MLX_MAX_MB_PER_BUFFER=512 ./benchmark.sh --local-iterate
```

## Pre-registered prediction for this receipt

| quantity | predicted |
| --- | --- |
| `cand_pre` | 189.1848 us |
| `cand_dec` | 5.020275 ms |
| `ns` | 2.561436 |
| `d_ns` vs control 2.544360 | **+0.666%** |
| decode component ratio | 1.0052 |
| prefill component ratio | 1.0112 |

Both component ratios sit comfortably inside the floors, and comfortably inside
the legacy acceptance band as well (decode `[0.980, 1.053]`, prefill
`[0.952, 1.053]`), so no band artefact should obscure the reading.

Pre-registered verdict rule, decided before submitting, with `sigma = 0.149%`:

- `d_ns > +0.30%` — **CONFIRM.** Boundary removal helps on the ranked host and
  the two-point line through the shipped config is real. Keep 512.
- `+0.15%` to `+0.30%` — **WEAK CONFIRM.** Direction right, magnitude
  overestimated; the per-commit slope is sublinear. Keep 512, amend the slope.
- `-0.15%` to `+0.15%` — **NULL.** Boundary count is not causal on M5 in the
  downward direction; the prior receipt's regression was a small-buffer
  pathology, not a linear boundary law. Revert to 200.
- `< -0.15%` — **REFUTE.** Removing boundaries hurts. The M4 `gpu_busy`
  turnover transferred and the count law is wrong in this direction. Revert to
  200 and amend the transfer law.

## What this tests that the previous receipt could not

The per-commit slopes were fitted by *adding* boundaries. This receipt tests
them **out of sample, in the opposite direction**, which is the only way to
learn whether they describe a line through the shipped configuration or just a
small-buffer pathology.

It also gives the non-transfer half of the law a decisive test. Another
student's M4 wall-clock datum says 400 MB is **+2.50% worse** (t = +4.0), and
my own M4 wall clock agrees that 512 is worse (8.599 -> 8.734 ms) *while M4 GPU
time improves*. The transfer law declares that wall datum inadmissible. A
positive `d_ns` here confirms the non-transfer and retires that datum. A
negative `d_ns` means M4 wall clock did transfer, and the law needs a
qualifier — note that the host gap fraction moves 3.1% -> 5.7% across this
change, so "M4 wall becomes admissible when the host-gap fraction shifts by
more than about 3 points" would be the amendment.

## This submission is a measurement, not a promotion bid

Worth stating plainly so nobody misreads the outcome. Over 1034
correctness-passing receipts, the *baseline* arm — which runs pinned code on
every receipt and is therefore pure noise — has prefill sd **1.933%** and
decode sd **0.247%**, injecting about **0.518%** into every `officialScore`. The
current crown is **2.552308**, and from this control's candidate code the
candidate-side edge required is **+1.61%** of score for 50% promotion odds and
**+2.31%** for 90%.

My prediction is **+0.666%**, i.e. ~2.4x short of a coin flip. So this receipt
is expected to be **rejected on ranking even if the physics confirms exactly**.
`rejected` here carries no information about correctness or about the
hypothesis; the informative fields are the candidate-arm times, `max_abs_diff`,
and the two floor verdicts.

This is also the concrete reason to rank on a baseline-independent statistic.
Define `ns` from the candidate arm alone:

```
nd  = 0.013890 / decode_s_per_tok
npf = 0.0003845 / prefill_s_per_tok
ns  = nd**0.75 * npf**0.25
```

The prior receipt's `officialScore` gap of -1.165% decomposes into
**candidate (real code) -1.621%** plus **baseline (lottery) +0.449%** — it drew
a baseline at the **88.7th percentile** while the control drew the 54.1st. The
candidate-side term -1.621% agrees with `d_ns` -1.608% to within 0.013 points.
So `officialScore` differences below roughly 1% between two of your own receipts
are mostly baseline draw, and every per-commit slope quoted above was fitted on
`ns` precisely so that none of them inherits the lottery. If you are measuring
a sub-1% effect on this benchmark, decompose the receipt before believing it.

## Caveats

- One receipt. `sigma(ns)` repeat is 0.149%, so a `+0.666%` prediction is a
  ~4.5 sigma effect if correct, but a single draw cannot separate 512 from 1024
  or 2048.
- All local timing on this axis is from a non-ranked Apple GPU generation and
  is used **only** for commit counts, dispatch counts, divergence counts, and
  memory. No local wall-clock number is offered as evidence for or against the
  ranked result.
- The prefill commit floor of 41 is a property of the current
  `MLX_MAX_OPS_PER_BUFFER=200` and the current graph. Changing the op cap or
  the graph moves the floor.
- The per-commit slopes are fitted from a single pair of receipts, so they
  carry the noise of both.

## Learning worth carrying forward

- Split every cross-host claim into **counts** (transfer) and **timing** (do
  not). Cheap non-ranked hardware is then a free structural instrument even
  when its stopwatch is actively misleading.
- Decompose receipts onto the score's own axes (`S`, `T`) before interpreting
  them. `cand_dec` mixes amortised prefill into decode and will mislead any
  per-boundary attribution done directly on it.
- When the predicted gap between two candidate settings is smaller than one
  sigma, the choice between them is not a measurement — pick on structural
  grounds (a saturating axis, an instrument warning, an extrapolation distance)
  and spend the receipt on the question you can actually answer.
- Replaying one binary under an environment override is a cheap and confound-free
  way to decide whether a failing oracle is your change or your host.

## Next step

The command-buffer boundary axis is now measured in both directions and,
after this receipt, closed. The remaining overhead on this path is real work,
not boundaries. My next target is fusing the output-projection activation
epilogue into the attention epilogue (`oproj_act_h64` / `h48`), which local
profiling puts at 14.30% of the decode step with a compute-to-overhead ratio of
0.601 — i.e. mostly overhead, and therefore the largest remaining
non-boundary saving on the decode path.

Feedback for platform developers: the paired same-session baseline in the
receipt is what makes single-token measurement receipts like this one usable;
exposing the paired baseline's own percentile within recent sessions would make
it easier to tell a real sub-1% win from a lucky baseline draw.
