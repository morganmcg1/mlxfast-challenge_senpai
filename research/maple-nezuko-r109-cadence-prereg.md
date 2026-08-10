# R109 side-finding, PREREGISTRATION: is the "extra work makes decode faster" effect
# commit cadence, or does it need the work?

Author: maple-nezuko. Written and committed BEFORE any row of the campaign exists.
Host: Apple M4 Pro (20 GPU cores, 48 GiB). Epoch: R109. Branch:
`maple-nezuko/r109-router-hybrid-selector`, tree `0eb218a5` (submitted surface
identical to research base `1a6761bf`: `git diff --numstat 1a6761bf HEAD --
Sources Vendor benchmark.json Package.swift` is empty).

Every number below is a LOCAL MARGINAL `--local-submit` quantity on THIS host.
It is not a census number and not a receipt number.

--------------------------------------------------------------------------------
## 1. Why this experiment exists

The R107-J' dispatch-cost ladder (32 runs, session `20260810T192206Z`, analyser
committed as `maple-nezuko/r107-qkv-packing-replication:research/maple-nezuko-r107j-ladder-analyze.py`
at `835613f7` **before** the data existed) returned a signed result that nobody
predicted, with a clean instrument (one golden hash across all 32 runs, exact
2/2/2/2 position balance, all six prefill contrasts covering zero):

| contrast | paired mean, M4 us/step | CI95 | same-sign pairs |
|---|---|---|---|
| S1 - CTL | -81.731 | [-96.176, -67.286] | 8/8 |
| S0 - CTL | -52.153 | [-65.597, -38.709] | 8/8 |
| N400 - CTL | -109.800 | [-122.720, -96.880] | 8/8 |
| S0 - S1 | +29.578 | [+21.257, +37.899] | 8/8 |
| N400 - S1 | -28.069 | [-37.585, -18.553] | 8/8 |

Adding 40-400 *useless* GPU dispatches per decode step made the step **faster by
52-110 us**, with bit-identical output. The K1 liveness check (added dispatches
must cost time) therefore FAILED with negative sign, which by my own
pre-commitment voids that ladder as a way to measure a positive per-dispatch
cost `c`.

Reading the source explains where the effect can come from.
`lagunaInjectLayerWork` (LagunaRuntimeModel.swift:12098) ends in
`asyncEval(pending)` (:12143), so the injection arms did not only add
dispatches - they added an **extra command-buffer commit point** at every layer
that received work. Baseline decode has only 7 commit points, from
`DARKBLOOM_DECODE_ASYNC_STAGE` default `"at:0,1,7,15,23,31,39"` (:735-760),
turned into `decodeFireMask` (:11477-11487) and fired as `asyncEval(h)` at
:11694 and :11706.

So the R107 arms confounded two things:

* **W (work):** N extra GPU dispatches of `laguna_inject_empty_dispatch_v1`
  (:12039), 160x256 = 40960 threads each, no memory traffic (the write is behind
  `control[0] == 0xFFFFFFFF`, which is false).
* **F (flush):** up to 40 extra `asyncEval` commit points per step.

`S0 - CTL = -52 us` was bought with **+1** flush and N dispatches; `S1 - S0 =
-29.6 us` was bought with **+39** flushes and the same N dispatches. Those two
numbers are not on one line, so the confound is load-bearing, and the two
mechanisms have completely different consequences for this programme.

## 2. Why the answer matters more than the R107 arm did

The advisor's pricing of every "delete a small kernel" arm this round rests on
the premise that **busy_sum ~= busy_union**: nothing overlaps, the ~413 us
busy/wall gap per step is already fully harvested, so removed busy time
transfers to wall at ~0.8-0.93. Arm G (fold RMSNorm into the NVFP4 QKV kernel)
is priced off exactly that transfer factor.

If **F** is the mechanism, then ~80-110 us/step of M4 decode wall is currently
being lost to submission structure alone - about **2x the entire 54 us crown
margin** - it is recoverable with a one-string environment default, it is
bit-exact, and it is evidence that there IS host/GPU latency to hide, i.e. the
premise behind the busy->wall transfer factor is wrong in the optimistic
direction for kernel-deletion arms (deleted busy time can be absorbed rather
than transferred).

If **W** is the mechanism (clock/DVFS residency, occupancy floor, the GPU not
power-gating between steps), then the effect is not shippable as a cadence
change, and the same warning applies for a different reason: wall is not a
monotone function of busy at all near this operating point.

Either answer changes how Arm G's result should be read. That is the point.

## 3. Design

Instrument: `maple-nezuko/r107-qkv-packing-replication:research/maple-nezuko-r107j-certify.sh`
at `835613f7`, used unmodified (blocked, position-balanced, interleaved,
`--local-submit` only, arms differ ONLY by environment gates). Analyser:
`...:research/maple-nezuko-r107j-paired-ci.py` at the same commit. Neither file
is added to this branch; both are referenced by commit so the reader can verify
that the analysis code predates the data.

**Zero code change. Zero rebuild. The submitted surface is untouched.** All
three arms run the same binary built from the pristine baseline tree; the entire
injection instrument (`DARKBLOOM_INJECT_*`, :11954-11981) and the cadence knob
(`DARKBLOOM_DECODE_ASYNC_STAGE`, :735-760) are shipped code on the research
base, not something I added.

Arms (first arm is the reference), 3 arms x 3 blocks = 9 runs:

| arm | gates | extra dispatches/step | extra commit points/step | total commit points/step |
|---|---|---|---|---|
| `CTL` | none | 0 | 0 | 7 |
| `C` | `DARKBLOOM_INJECT_DECODE_EMPTY=40` | 40 (`lagunaInjectShare(40, layer)` = exactly 1/layer, :12088-12092) | 40 | 47 |
| `D` | `DARKBLOOM_DECODE_ASYNC_STAGE=ladder1` | **0** | 33 | 40 |

`C` reproduces the R107 `S1` arm (`DARKBLOOM_INJECT_EMPTY_SPREAD` defaults to 1,
`..._CHAIN` to 1, `..._TG` to 160). `D` is the new arm: it buys the *same* order
of extra commit points with **no added work at all**, by firing `asyncEval(h)` at
every one of the 40 layers instead of at 7 of them. `D` is therefore the direct
`W` vs `F` discriminator, and `D` is the arm that would be shippable.

Caveat recorded in advance: `D` flushes `h`, a true data dependency of the next
layer, whereas `C` flushes an injected chain independent of `h`. If `D` beats `C`
that asymmetry is the likely reason, and it is a bonus rather than a confound for
the shippability question.

## 4. Preregistered predictions

Point predictions in M4 us/step, `--local-submit`, negative = faster:

* **H_F (cadence is the mechanism):** `C - CTL ~= -82`, `D - CTL ~= -82`, and
  `D - C ~= 0`.
* **H_W (the work is required):** `C - CTL ~= -82`, `D - CTL ~= 0`.
* **H_null (the R107 ladder was an artefact of that tree/session):**
  `C - CTL ~= 0`, which would refute the replication and void everything above.

Replication check with a real interval, not a point: `C - CTL` is predicted to
land in `[-110, -55]`, i.e. to reproduce `S1 - CTL = -81.731 [-96.176, -67.286]`
measured on a different branch, a different tree and 2.5 h earlier.

## 5. Preregistered decision rule

Read in this order. Step (0) is a veto: if it fails, no contrast is reported as
anything but void.

0. **Instrument validity.** (a) exactly one distinct `golden_hash` across all 9
   runs; (b) `passed_correctness` true in all 9; (c) both prefill contrasts
   (`C - CTL`, `D - CTL`) cover zero - the empty-injection path and the decode
   fire mask are both gated on `isSingleTokenDecode`, so prefill MUST be
   untouched, and a prefill move means the gate leaked or the machine drifted;
   (d) position balance exactly 1/1/1 per arm per position (3 blocks x 3 arms
   with rotation by `(b-1) mod 3` gives this by construction); (e) the source
   fingerprint `find Sources Vendor Package.swift benchmark.json -type f | sort
   | xargs stat -f '%N %m %z' | md5` equals `bc73425a7aedd3301b09e1b1f849c042`
   both before and after the campaign - a second conversation of my own role is
   working Arm G in this same worktree, and if it rebuilds mid-campaign the arms
   are contaminated; (f) the harness's own per-arm kernel-set check does not
   fire.
1. **Replication.** If `C - CTL` CI95 does not exclude zero, verdict
   `N-CADENCE-NOT-REPLICATED` and stop: the R107 ladder result does not travel.
2. **Discrimination**, only if (1) passes:
   * `D - CTL` CI95 excludes zero AND its point estimate is <= -40 us
     => verdict `Y-CADENCE-IS-MECHANISM`. Report the shippable size as the
     `D - CTL` point estimate with its CI, price it at 0.0070 %score/wall-us
     (tau=1, elasticity_T=0.638), and hand it to frieren, who owns
     LagunaRuntimeModel.swift:735-800 and :11694-11712 - I must not edit those
     lines myself.
   * `D - CTL` CI95 covers zero AND excludes -55 us
     => verdict `N-WORK-REQUIRED-NOT-CADENCE`. The effect is not shippable as a
     cadence change; report it as a warning about the busy->wall transfer factor
     only.
   * anything else (CI covers both zero and -55, or point in (-40, 0) with a CI
     excluding zero) => verdict `A-CADENCE-AMBIGUOUS`, and the honest statement
     is that 3 blocks were not enough. Extension is preauthorised here and only
     here: 3 more blocks, appended, analysed pooled.
3. `D - C` is reported for completeness with its CI and is not used in any
   verdict.

No verdict is upgraded on the basis of a point estimate whose CI I do not print.
I will report the CI for every number in section 4-5, decode separately from
score, and I will not divide a `--local-submit` level by a receipt level.

## 6. Costs, and what this does not claim

9 runs at ~3.06 min/run (measured: 32 runs in 98 min, same harness, same host)
= ~28 min of exclusive GPU. That is the whole cost, because there is nothing to
build.

This experiment does not measure Arm G, does not touch `gate_sp`, does not
produce a receipt, and cannot by itself justify shipping anything: a
`--local-submit` M4 delta is a local marginal quantity, the shippable claim
would need a paired ABBA certification on the submitted configuration with
`FERN_DEFEAT_SLOTS=64` and a preregistered revert, and the default string lives
in another student's deconflicted region.
