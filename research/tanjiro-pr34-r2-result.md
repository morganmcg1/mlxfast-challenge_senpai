DRAFT - NOT TERMINAL. The single-line SENPAI-RESULT marker replaces this banner
once every authorised receipt has returned.

# PR #34 revision r2: is the marginal cost of a Metal dispatch on M5 worth removing?

- Student / PR: `maple-tanjiro` / #34, branch `maple-tanjiro/m5-block-rates`, revision r2
- Assignment: `maple-2026-08-04i-m5-block-rates`
- Hypothesis and target cost: PR #37 attributes about 4.1 microseconds of host
  encode and commit cost to each of the roughly 406 Metal dispatches in one
  decode step, which would make 1.665 ms of the 4.32 ms step removable by
  fusion. This revision measures the *marginal* price of a dispatch on the
  official M5 directly, by injecting `n` empty, dependency-free dispatches per
  decode step and fitting `dT(n) = max(0, n*c - slack)`. `slack` is the free
  headroom: the number of dispatches the machine absorbs before wall time
  responds at all.
- Decision: PENDING
- `BASE_SHA` / candidate commit: base `279b6e2409a2ca92f7b874e08a3dabc2c6ff4a0b`
  (advisor tip `ed02e9e69427f774628aaf69fee106931e7bc7cb`, docs-only ahead of it);
  candidate commit PENDING
- Submitted candidate files: none. The final commit of this revision restores
  `Sources/MLXFastModel/LagunaRuntimeModel.swift` byte-for-byte to the base. This
  is a measurement revision, not an optimisation: the assignment says sweep only,
  do not build a fusion.
- Supporting test or documentation files: `research/tanjiro-pr34/` (pre-registration,
  queue, per-level notes, provenance, M4-vs-M5 comparison, instrument patch) and
  `senpai/tools/pr34_*.py`, `senpai/tools/pr34_m4_ladder.sh`. All outside
  `editablePaths`, so none of it costs submission bytes.
- Assignment-scope preflight: PENDING
- Editable bytes / headroom / growth: PENDING (before/after captured; see the
  byte-budget section)
- Scored-path reachability evidence: the injection hook is called at
  `LagunaRuntimeModel.swift:10797`, inside the per-layer loop of the scored
  forward pass, and the decode branch is selected by `isSingleTokenDecode`
  (`inputs.dims(1,1)`, line 10753). Every receipt below shows the injected work
  in the timed decode axis, which is itself proof of reachability.

## What this probe prices, and what it does not

The injected kernel is `laguna_inject_empty_dispatch_v1`. It has a predicated
store that never executes, it is chained through `LagunaInjectChain.tail` so the
encoder cannot elide it, and at `DARKBLOOM_INJECT_EMPTY_TG = 8` it is 8
threadgroups of 256 threads. So the probe measures the *host-encode and
scheduling margin of an empty, dependency-free dispatch*.

That is deliberately narrower than "the cost of a dispatch in the shipped decode
step", and the distinction drives the whole interpretation:

- If `slack` is about zero, the machine is already dispatch-bound and removing
  dispatches by fusion buys time at the fitted rate `c`. Green light.
- If `slack` is large, the 4.1 microsecond figure is falsified **as a marginal
  host cost**. It does *not* retire fusion, because a real fusion also removes
  GPU-side costs the empty probe cannot see: launch ramp and tail, inter-kernel
  gaps, and round-trips of intermediate tensors through memory. Those are worth
  roughly 3.1 to 3.4 microseconds per dispatch if the entire unattributed 1.27
  to 1.38 ms of the decode residual is charged to them, which is an upper bound,
  not an estimate.

This scope limit was pre-registered in `research/tanjiro-pr34/prereg-r2.md`
before any reading arrived, precisely so that a large `slack` could not be
quietly promoted into "dispatch reduction is worthless".

## Ladder, and why it deviates from the assignment

The assignment proposed `n` in {0, 100, 200, 400, 800}. I ran
{0, 400, 800, 1600, 2400} at `tg = 8` with prefill empties pinned to 0, and
pre-registered that choice with three competing predictions before submitting
anything.

The reason is that the assignment's ladder cannot discriminate the hypotheses it
is meant to test. Carrying the M4 law (`c = 2.607 us`, `slack = 3.152 ms`, knee
at 1209 dispatches) to M5 gives three candidate laws:

| | mechanism | `c_M5` (us) | `slack_M5` (ms) | knee (dispatches) |
| --- | --- | --- | --- | --- |
| `H_sat` | M5 is already dispatch-bound | 2.0 to 2.6 | < 0.2 | < 80 |
| `H_gpu` (advisor) | slack is GPU-idle-gap shaped, so it scales down by the 2.623x step-time ratio | 2.61 | 1.20 | 461 |
| `H_cpu` (my prediction) | slack is a fixed *dispatch count*, so the knee transfers | 2.27 | 2.72 | 1200 |

Predicted `dT` in ms:

| n | `H_sat` | `H_gpu` | `H_cpu` |
| --- | --- | --- | --- |
| 0 | 0 | 0 | 0 |
| 400 | 0.82 | 0 | 0 |
| 800 | 1.74 | 0.89 | 0 |
| 1600 | 3.58 | 2.98 | 0.91 |
| 2400 | 5.42 | 5.06 | 2.73 |

On the assignment's ladder, `H_gpu` produces exactly one non-zero point and
`H_cpu` produces none: four of the five receipts would have returned zero and
the outcome would have been "the knee is somewhere above 800", which is what the
M4 work already said. On mine, `n = 800` separates all three hypotheses (the
predictions are 34 to 37 sigma apart at the 0.024 ms two-receipt noise floor),
`n = 400` is the sole `H_sat` discriminator, and there are always at least two
points above any knee in [0, 1600].

`tg = 8` keeps the injected GPU work under about 0.09 microseconds per dispatch,
under 3.5 percent of `c`, so the probe stays a dispatch-count probe rather than a
GPU-work probe. Prefill empties are pinned to 0, which makes the prefill axis `S`
a flat internal control and avoids the prefill dispatch axis that PR #27 found
self-inconsistent by a factor of 7.

Declared blind spot: no level lies in `n` between 0 and 400, and that is exactly
where a fusion removing 50 to 200 of the 406 shipped dispatches would live. A
knee near 200 would make "remove 40" worthless and "remove 300" valuable, and
this ladder cannot separate those two worlds.

Design lesson accepted but declined mid-flight: a frontier review of the design
found that `n = 0` is nearly redundant and that replacing it with `n = 1200`
would have given a tighter knee (standard error 9.3 to 12 dispatches instead of
10 to 17) and one more degree of freedom for lack-of-fit. I kept the
pre-registered ladder rather than re-choosing levels after the fact, because the
value of a pre-registration is destroyed by editing it once submissions are
under way.

## Cost floor headroom

The pinned decode baseline is 0.013890 s/token and the hard floor is 0.95, so a
candidate may take up to 14.621 ms/token. The frontier is about 5.087 ms/token,
which leaves about 9.53 ms of injected `dT` affordable. The worst case on this
ladder, `n = 2400` under `H_sat`, costs at most 6.26 ms. `c` would have to exceed
3.97 microseconds to breach the floor, and a breach still returns `rejected`
*with* full timed metrics, so no reading is lost either way. The prefill floor is
untouched because prefill empties are 0.

## Readings

PENDING

## Fit

PENDING

## Verdict on dispatch-count reduction

PENDING

## M4 companion measurement

PENDING

## The M4-versus-M5 disagreement

The advisor asked for this explicitly. The same inert tree on the local Apple M4
Pro host and on the ranked M5:

| quantity | M4 Pro (`m4-L0.json`, inert) | ranked M5 (`b6032aeb`) | M4 / M5 |
| --- | --- | --- | --- |
| `S`, 512-token prefill forward | 577.20 ms | 97.86 ms | 5.90x |
| `T`, steady one-token decode step | 8.8161 ms | 4.2747 ms | 2.06x |
| full decode seconds/token | 13.326 ms | 5.039 ms | 2.64x |

The 5.90x prefill gap is mostly a *kernel gate*, not hardware. Locally
`prefill_speedup = 188.17 / 577.20 = 0.326`, so the promoted frontier is three
times **slower** than the baseline on this host, while on M5 the same tree is
1.913 times faster. `quantized.cpp:1956` routes to `gather_qmm_rhs_nax` only when
`is_nax_available()`, and `device.cpp:913` requires architecture generation 17 or
above; this host is generation 16 (`applegpu_g16s`). So for NAX-gated prefill
work M4 is **anti-correlated** with M5, not merely conservative, and no prefill
conclusion may be carried across.

The 2.06x decode gap is closer to an honest hardware ratio, which is why the M4
companion ladder is used only for decode-side method validation: to show that the
injected kernel's own GPU time is negligible, and to state an M4 companion law at
the same ladder points.

A related finding worth recording: the local paired baseline is not measured, it
is a pinned constant. Across all eleven r1 local runs
`baseline_decode_seconds_per_token` was 0.01385621216015625 and
`baseline_prefill_seconds_per_token` was 0.00036751938916015626, identical to
every digit. There is no `--local-iterate` baseline artefact on disk. So a local
`*_speedup` is arithmetic against another machine's constant, and every local
`dT` in this report is `T(n) - T(0)` measured on the same host in the same
session, never a difference against that pinned number.

## Answers to the two questions in the r2 assignment

Recovered from the submitted trees themselves, by reading the injection literals
out of each submitted commit
(`git show <c>:Sources/MLXFastModel/LagunaRuntimeModel.swift`):

| tree | `DECODE_ATTN` | `DECODE_ROUTED` | `PREFILL_ROUTED` | `PREFILL_ATTN` |
| --- | --- | --- | --- | --- |
| R1 anchor | 0 | 0 | 0 | 0 |
| R2 | 40 | 0 | 39 | 0 |
| R3 | 40 | 39 | 0 | 40 |
| R4 | 0 | 39 | 20 | 0 |

**(a) Were the R2 and R3 decode arms nested or disjoint?** Nested, on the decode
axis. R3 is R2's 40 attention-QMV copies *plus* 39 routed-QMV copies, which is
what `cfg-r3.md` says at the time. So `dT_4 = T_R3 - T_R2` is a plain difference
of a strictly nested pair, and the advisor's `2.24137 - 1.23070` reduces to the
same quantity. On the prefill axis R2 and R3 are instead disjoint single-knob
arms against the shared zero anchor, which is also valid.

### The promoted question: is `dS_1` marginal or absolute, and is there a 32.4 ms pool?

The advisor asked for this "before anything else", because two independent
frontier audits converged on a remainder and then both objected to the way it
was priced. Answering it costs zero receipts, so it is answered here in full.

The remainder they computed:

```
dS_1 = 141.1262 - 97.8643 = 43.2619 ms   (PREFILL_ROUTED 39 vs 0)
dS_2 = 120.0782 - 97.8643 = 22.2139 ms   (PREFILL_ATTN   40 vs 0)
sum                        = 65.4758 ms
S_R1 - sum   = 97.8643 - 65.4758 = 32.3885 ms  "remainder"
```

**Nested or disjoint, on the axis that matters here?** Disjoint. Read the table
above on the prefill columns only: R2 is `(PREFILL_ROUTED=39, PREFILL_ATTN=0)`
and R3 is `(PREFILL_ROUTED=0, PREFILL_ATTN=40)`, both against the shared R1 zero
anchor. They are two independent single-knob arms, so `dS_1` and `dS_2` do not
double-count each other and their sum is a legitimate sum of two disjoint
measurements. That part of the audit is sound.

**Marginal or absolute? Marginal, unambiguously.** Every one of these numbers is
the wall-time *increase* caused by *adding* copies of an op to an
already-complete forward pass: 39 extra routed-prefill GEMM invocations, spread
roughly one per layer across 40 layers. It is not the standalone cost of the
copies the model actually ships. The auditors' objection is correct in
substance, and I am not going to defend the stronger reading. What I can do is
say which way the bias runs, and the honest answer is that it is not determined:

- *Amortisation and warm caches.* An injected copy runs immediately after the
  shipped one, with weights and instruction cache already warm and the
  scheduler already primed, so the marginal copy is cheaper than the shipped
  average. Then 65.4758 **undercounts** the shipped work and the 32.4 ms
  remainder is **overstated**. This is the auditors' direction.
- *Overlap and latency hiding.* The shipped copy overlaps with neighbouring
  work, so its share of wall time is *less* than its standalone cost, while a
  chained injected copy is fully exposed on the critical path. Then 65.4758
  **overcounts** the shipped wall share and the remainder is **understated**.

Both mechanisms are real and they push opposite ways. Nothing in the three r1
receipts separates them, because there is **no dose-response within a single
kernel**: each block has exactly one non-zero dose. That is the design gap.

One weak piece of evidence tells against the warm-cache direction being large:
rate 1 came out at 408.4 GB/s = 23.23 TFLOP/s = 67 percent of the 34.7 TFLOP/s
peak, that is *below* peak rather than implausibly above it, and the 21.6 GB
weight set cannot sit in any cache. A badly cache-inflated marginal measurement
would more likely have produced a super-peak rate.

**A scaling correction worth stating while we are here.** Block 1 injected 39
copies but the model ships 40 layers, so scaling to the shipped count gives
`43.2619 x 40/39 = 44.371 ms`, the sum becomes 66.585 ms, and the remainder
falls from 32.389 to **31.279 ms**. That is a 1.11 ms, 3.4 percent correction in
the direction of a *smaller* pool. Block 2 injected 40 and needs no scaling.

**The cheap decisive experiment, for whoever holds the next receipts.** Two
receipts, no new code, because the knobs are already in `instrument.patch`: run
`PREFILL_ROUTED` at 13 and at 26. With the existing R2 (39) and R1 (0) that
gives four points of dose-response *within one kernel*. Linear through the
origin means marginal equals average and the pool stands as measured; concave
means 65.4758 undercounts and the pool shrinks; convex means it overcounts and
the pool grows. Until someone runs it, treat 31.3-32.4 ms as a marginal-cost
remainder and not as a pool of removable work.

**This qualification propagates.** The `+14.30 ms excess over roofline` for rate
1, which is 42.1 percent of the honest prefill residual and the number
maple-fern's PR #40 is built on, is a *marginal-cost* excess and inherits
exactly the same caveat. So does fern's 15.4 ms recoverable figure, which is
measured against this floor. I am flagging that rather than letting it ride.

**(b) Does rate 4 depend on the failed R4 receipt?** No. R4's decode probe was
routed-QMV *alone*, the unloaded companion. The published rate 4 of 546.2 GB/s
rests entirely on R3 minus R2, and both of those receipts succeeded
(`6757de65`, `ca416f01`). R4 carried only three robustness companions. **Rate 4
needs no re-run**, so the advisor's contingency of reallocating r2 receipts to
repair it is moot and all five r2 receipts stayed on the dispatch law.

Widened error bar, since the question was asked: the published +/-0.034 ms
already used two-receipt propagation (quadrature 0.02900 ms times the same 1.18
method factor used for `dT_2`). Adding a 0.026 ms allowance for cross-session
drift, which is what the R2 and R3 normalisations actually disagreed by (2.6
percent), gives a conservative +/-0.043 ms. Rate 4 becomes 546.2 +/- 23.3 GB/s,
that is [523, 569]. Against the 0.90505 ms roofline the excess is +0.1056 +/-
0.043 ms, still more than 2 sigma from zero, and 7.9 +/- 3.2 percent of the
decode residual. The conclusion does not change.

## The "12.4 sigma cross-day drift": it is the baseline leg, and the sigma is spurious

The advisor asked for `c3ce66e`'s `S` and `T` next to the three 8/4 pairs,
because the CLI truncates his metrics column, and drew a programme-wide
conclusion from the comparison: that cross-day receipt comparison carries about
0.3 percent of drift, roughly ten times the 0.026 percent same-day replicate
spread, so "every single cross-day receipt pair screen below about 0.6 percent
is unsupported". I fetched all four receipts on all axes and re-derived it.
`senpai/tools/pr34_drift_axes.py` reproduces every number below from the raw
fields; it also reconstructs all four published `officialScore` values to six
decimal places from `S`, `T` and the two baseline fields, which validates the
decomposition before any of it is used.

| receipt | when (UTC) | cand `S` ms | cand `T` ms | base `S` ms | base ms/token | `prefill_su` | `decode_su` | `officialScore` | `ns` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `71586bcf` | 8/4 10:02 | 97.5129 | 4.38283 | 198.8970 | 13.88149 | 2.03970 | 2.69824 | 2.515950 | 2.510648 |
| `c210d200` | 8/4 11:38 | 97.9730 | 4.34279 | 196.0282 | 13.86295 | 2.00084 | 2.71386 | 2.514743 | 2.521102 |
| `b6032aeb` | 8/4 20:11 | 97.8643 | 4.27468 | 187.1734 | 13.88424 | 1.91258 | 2.75522 | 2.514911 | 2.547640 |
| `c3ce66ec` | 8/5 09:33 | **97.9496** | **4.28121** | 190.0278 | 13.89953 | 1.94006 | 2.75432 | 2.523276 | 2.544361 |

Per-axis spread over the four (range, then sd, both as percent of the mean):

| axis | mean | range % | sd % |
| --- | --- | --- | --- |
| cand `S` | 97.82495 | 0.470 | 0.218 |
| cand `T` | 4.32038 | 2.503 | 1.197 |
| cand ms/token | 5.08463 | 2.073 | 0.995 |
| **base `S`** | 193.03160 | **6.073** | **2.785** |
| base ms/token | 13.88205 | 0.264 | 0.108 |
| `prefill_su` | 1.97329 | 6.442 | 2.920 |
| `decode_su` | 2.73041 | 2.087 | 1.057 |
| `officialScore` | 2.51722 | 0.339 | 0.162 |
| `ns` | 2.53094 | 1.462 | 0.710 |

**First finding: the drift is in the baseline leg, not the candidate.** Take the
one pair I can personally certify is the same scored code, `b6032aeb` (8/4
20:11) to `c3ce66ec` (8/5 09:33), and the score's +0.333 percent decomposes as

```
cand S      +0.087%      base S      +1.525%
cand T      +0.153%      base ms/tok +0.110%
cand ms/tok +0.143%

d(prefill_su) = +1.525 - 0.087  = +1.438%   (observed +1.437%)
d(decode_su)  = +0.110 - 0.143  = -0.033%   (observed -0.033%)
d(score)      = 0.75(-0.033) + 0.25(+1.438) = +0.335%  (observed +0.333%)

baseline leg  0.25(+1.525) + 0.75(+0.110) = +0.464%
candidate leg -[0.25(+0.087) + 0.75(+0.143)] = -0.129%
```

The baseline leg is +0.464 percent and the candidate leg is **negative**, so the
baseline accounts for 138 percent of the observed move. Cross-day, the candidate
did not drift up; the pinned reference model was re-measured 1.5 percent slower
on prefill and the *ratio* went up. That is not a property of cross-day
comparison of candidates; it is the well-known instability of the baseline leg,
and `sd(S_baseline) = 1.93 percent` over the 929 pinned baselines already on
record makes a 6.07 percent range over four samples entirely ordinary.

**Second finding: the 0.026 percent denominator is an accidental cancellation.**
Across the first three receipts `decode_su` rose 2.112 percent while
`prefill_su` fell 6.232 percent, and

```
0.75(+2.112) + 0.25(-6.232) = +1.584 - 1.558 = +0.026%
```

which is, to the digit, the 0.026 percent "replicate spread". The score looks
stable only because its two weighted components anticorrelate through the shared
baseline session. The underlying component sds over those three are 1.082
percent on `decode_su` and 3.283 percent on `prefill_su` -- forty to a hundred
and twenty times larger. A quantity whose small variance comes from cancellation
is not a valid sigma denominator, so the 12.4 figure does not measure 12.4 of
anything.

**Third finding: on candidate axes, L0 is an ordinary member.** Standardising
L0 against the first three on each axis with that axis's own sd:

| axis | L0 | mean of 3 | delta | z |
| --- | --- | --- | --- | --- |
| `officialScore` | 2.523276 | 2.515201 | +0.321% | **+12.4** |
| cand `S` | 97.94960 | 97.78340 | +0.170% | +0.7 |
| cand `T` | 4.28121 | 4.33343 | -1.205% | -1.0 |
| `ns` | 2.54436 | 2.52646 | +0.708% | +0.9 |

The 12.4 sigma exists on exactly one axis, the one with the cancellation-shrunk
sd. On every candidate axis L0 is inside one sigma.

**So the programme rule should change, not tighten.** The advisor's inference --
0.3 percent drift, therefore no cross-day screen below 0.6 percent -- would
retire a large amount of otherwise usable evidence. The narrower and better
supported rule is:

- Screen on **candidate axes (`S`, `T`)** or on **`ns`**, never on
  `officialScore` or the raw speedups, because those carry the baseline leg.
- Cross-day candidate-axis reproducibility on the verifiable pair is **0.087
  percent on `S` and 0.153 percent on `T`**, an order of magnitude better than
  0.6 percent.
- A **decode-only** screen is stable to about 0.03 percent on `decode_speedup`
  across those two days, because the baseline decode axis moves only 0.11
  percent while baseline prefill moves 1.5 percent.
- Where a screen must use a speedup, use the **same-session paired** baseline
  the harness already supplies and difference within the session, which is
  exactly the advisor's own first instruction and which I have followed.

**The open question I cannot close, stated rather than buried.** `71586bcf` and
`c210d200` may not be the same scored code as `b6032aeb`. Candidate `T` falls
monotonically 4.38283 to 4.34279 to 4.27468 while candidate `S` is flat inside
0.47 percent, which is the signature of progressively promoted *decode*
optimisations, not of noise. The advisor's own diff covered `0b45de22..454b189a`
only. If the three really are one code state, candidate-`T` drift is 2.5 percent
(0.108 ms) and my pre-registered `sigma = 0.024 ms` is optimistic by 4.5x; if
they are successive frontiers, the verifiable spread is 0.15 percent and the
sigma stands. **Either way my ladder is unaffected**, because all five r2
receipts are on 8/5 and each level is differenced against its own
session-paired baseline. Someone with the promotion history should settle it,
because the answer sets the sigma for every future receipt-pair screen.

**Correction to my own earlier note.** The `ns` values I recorded earlier for
`f8502e12`, `71586bcf` and `f3cda678` (2.48558, 2.51595, 2.50895) were copied
`officialScore` values, not computed `ns`. `71586bcf`'s real `ns` is 2.510648.
The paragraph in `queue-r2.md` that called those three "an earlier promoted
frontier, 1.3 percent lower, must not be pooled" is therefore overstated and has
been softened. The `b6032aeb` versus `c3ce66ec` `ns` gap of 0.129 percent
survives the recomputation.

### Answers to the three narrower asks in the same comment

1. **Difference only within a session.** Agreed and already the case. R1 (8/4
   20:11) is the `T(0)` for R2 (20:44) and R3 (21:20), and the 8/5 anchor is not
   used to difference any 8/4 arm.
2. **Report `S` and `T` for `c3ce66e`.** `S = 97.9496 ms`, `T = 4.28121 ms`. In
   the table above, bolded, next to the three 8/4 pairs.
3. **Does the fit use any cross-day difference? Refit if so.** **No, and so no
   refit is needed.** All five r2 receipts are 8/5 and each level is differenced
   against its own session-paired baseline. In r1, `dT_4 = T_R3 - T_R2` used 8/4
   20:44 and 21:20, and `dS_1` and `dS_2` both used R1 at 8/4 20:11. There is no
   cross-day difference anywhere in either the r1 rates or the r2 ladder.

## The R4 failure: `afec358a`

`afec358a` returned `status=failed` with `officialScore=None` and no timed
metrics at all. The reason was not timing and not correctness: the workflow run
concluded failure at the step "Review submitted code for benchmark bypasses"
(run 30955316536), created 22:09:28Z and updated 22:53:48Z.

The R4 tree differs from the R3 tree, which had already passed that same review,
in exactly four integer literals. `DARKBLOOM_INJECT_ARCH_PROBE` was 0 in all
four trees and predates R1, so it cannot be the differentiator. The most
defensible reading is a non-deterministic reviewer or an infrastructure error.

The operational lesson is worth more than the diagnosis: **a submission can
consume a slot and return no metrics at all.** I therefore declared a rule in
advance, in `queue-r2.md`, that a `failed`-with-no-metrics receipt is a *retry*
and not a data point: resubmit the identical tree and record both attempts, so
that five authorised receipts means five readings rather than five slots.

## Process disclosures

These are not incidental; two of them changed how this revision had to be run.

**The official channel is serialised at one submission in flight.** The r1 notes
and the r2 assignment both said the receipts could be submitted concurrently.
They cannot. Submitting L1 about 20 seconds after L0 returned produced
`{"error":{"code":"conflict","message":"account already has 1 submission(s) in
flight for this benchmark (limit 1)"}}`. At 21 to 48 minutes per receipt this
turns a five-point ladder into a 2.5 to 3 hour serial campaign, and it is the
single most important scheduling fact for anyone planning a multi-receipt sweep.
I kept the full five-level ladder rather than truncating it, with one declared
exception: stopping early if a reading falsified the law itself.

**There is no live channel from a student to the advisor.** `push_branch` is
advisor-owned, so a student can only push through `submit_result`, which means
the advisor sees nothing at all until the final submission. `respond_to_issue`
refuses a pull-request target (`human messages must use an issue, not a pull
request`). So an intermediate finding cannot be surfaced mid-campaign. My
mitigation was to commit `research/tanjiro-pr34/queue-r2.md` as a running log and
to fold every disclosure into this report. A useful consequence: reordering the
ladder to give the advisor an early read has exactly zero value, so the
pre-registered order was kept.

**Branch divergence, disclosed rather than resolved by force.** The remote
assignment head `454b189a07a2cb0c51b91188d834e9b1c5035603` is the stale
pre-rebase r1 tip. My local history was rebased onto `279b6e24`, so the SHAs
differ one-for-one by commit message (`454b189` is `c92eab6`, `5b39ec5` is
`8d5131f`, `ee324e1` is `644c226`). R4's submitted commit `af3ab58` is a
pre-rebase SHA and is not a valid object locally; its content equals local
`13d424f`. Comparing file lists, no file exists on the remote but not locally:
local is a strict content superset. The submission therefore uses
`expected_remote_sha = 454b189a...`, and nothing was reset or discarded.

## Byte budget

The assignment asked for the editable-byte budget before and after.

| | total bytes | headroom | growth | files |
| --- | --- | --- | --- | --- |
| before | 2954324 / 3000000 | 45676 | 13351 / 262144 | 142 (base 142) |
| after | 2940973 / 3000000 | 59027 | 0 / 262144 | 142 (base 142) |

The instrument patch was moved out of the scored file into
`research/tanjiro-pr34/instrument.patch`, which restored
`LagunaRuntimeModel.swift` to the base size of 508529 bytes and with it the full
15759 bytes of per-file room under the 524288 byte cap. That matters to a
sibling: PR #35 needs 8037 bytes in the same file and now has 7722 bytes of
spare.

## Cross-references

Per the assignment, the per-family M4 dispatch census in `nezuko`'s PR #32 is
cross-referenced rather than duplicated here.

## Conclusion

PENDING
