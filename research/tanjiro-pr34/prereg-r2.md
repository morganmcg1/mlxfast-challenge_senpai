# r2 pre-registration: the M5 decode dispatch-saturation law

Committed **before** any r2 official receipt is submitted. Nothing below is
revised after the first receipt; the result file reports measured values against
these numbers as written.

## Quantity being measured

Injecting `n` minimal-GPU-work dispatches into every single-token decode step and
differencing official receipts gives

```
dT(n) = max(0, n * c - slack)
```

where `dT` is the change in the per-step decode residual `T` in ms, `c` is the
marginal cost of one additional dispatch in µs, and `slack` is the spare
dispatch-absorption capacity the *shipped* decode step still has, in ms. The
knee `n_knee = slack / c` is expressed in **injected** dispatches, so total
saturation occurs at `406 + n_knee` dispatches, 406 being the shipped decode
dispatch count.

The decision this answers: **dispatch-count reduction on the scored path is worth
something only if `slack ≈ 0`.** If `slack > 0` the shipped step already has
unused dispatch capacity, and removing shipped dispatches merely enlarges
`slack` without shortening the step. Symmetrically, `n_knee` is the number of
extra dispatches a future candidate may add for free.

## Prior: the M4 law measured in r1 / PR #27

At tg=160 on a previous-generation host: `c_M4 = 2.607 µs`,
`slack_M4 = 3.152 ms`, `n_knee_M4 = 1209` injected dispatches. Out-of-sample
residuals ≤0.03 ms at n=600 and n=1400; validated across n∈[600, 8000] and
tg∈[8, 160]. M4 decode step 13.344 ms; M5 decode step 5.087 ms/token
(ratio 2.623). Shipped decode path: ~406 dispatches in 45 command buffers.

## Three pre-registered hypotheses

| | mechanism | `c_M5` (µs) | `slack_M5` (ms) | `n_knee` (injected) | shipped 406 sits at | value of −10% dispatches |
| --- | --- | --- | --- | --- | --- | --- |
| **H_sat** | M5 decode is already dispatch-bound | 2.0 – 2.6 | < 0.2 | < 80 | ≥84% of capacity | 41 × c ≈ **0.09 ms** (1.9% of step) |
| **H_gpu** | slack is GPU-idle-gap shaped, so it shrinks with the 2.623× shorter step; `c` is a host-side constant and does not scale | **2.61** | **1.20** | **461** | 47% of capacity | **0 ms** |
| **H_cpu** | slack is a fixed *count* of dispatches amortised per command buffer, independent of concurrent GPU work; only `c` scales, with host CPU speed (≈1.15×) | **2.27** | **2.72** | **1200** | 25% of capacity | **0 ms** |

`H_gpu` derivation: `slack_M5 = 3.152 × 5.087/13.344 = 1.20 ms`, `c` unchanged,
`n_knee = 1201.6/2.607 = 461`.
`H_cpu` derivation: `n_knee` unchanged at 1200, `c_M5 = 2.607/1.15 = 2.27 µs`,
`slack_M5 = 1200 × 2.27 µs = 2.72 ms`.

**My prediction, stated plainly: `H_cpu`, so `c_M5 ≈ 2.3 µs` and
`slack_M5 ≈ 2.7 ms`, knee near 1200 injected dispatches, and dispatch-count
reduction on M5 is worth 0 ms.** The evidence is a direct falsification test
already run in PR #27: adding a 268 MB / 1.05 ms-per-step memory sweep to the
M4 decode step — lengthening the step's GPU time by 8% — bought **zero** extra
free dispatches; the knee stayed at ~1200. Under `H_gpu` that extra 1.05 ms of
GPU time should have raised slack by ~0.25 ms ≈ 96 dispatches. It did not.
`H_cpu` is registered as an empirical scaling law, not a mechanism claim; the
"fixed count" statement is what was measured, and I do not assert why.

`H_sat` is registered because it is the only outcome under which the advisor's
fusion question has a non-zero answer, and it must be given a fair chance to
show itself rather than being assumed away.

## Ladder, and why it deviates from the assignment's suggestion

Assignment suggested `n = 0, 100, 200, 400, 800`. **I will run
`n = 0, 400, 800, 1600, 2400` at `tg = 8`, prefill empties `0`.** Justification:

* Under `H_gpu` the suggested ladder yields exactly one non-zero point (n=800),
  and one point cannot separate `c` from `slack`. Under `H_cpu` it yields
  **none**, and `c` would be entirely unmeasured. The suggested ladder is
  informative only under `H_sat`, the least-supported of the three.
* The chosen ladder has ≥2 non-zero points for any knee in [0, 1600] and so
  always identifies both `c` and `slack`; `n = 2400` also covers a knee up to
  2400.
* `n = 800` is the discriminating point: non-zero ⇒ small slack (`H_gpu`-like);
  zero ⇒ large slack (`H_cpu`-like). `n = 400` non-zero ⇒ `H_sat`.
* Nothing is lost at the low end: under `H_sat`, `dT(400) ≈ 0.92 ms`, roughly
  40× the ≈0.024 ms differencing noise, so saturation is detected at n=400
  without spending a receipt on n=100 or n=200.

`tg = 8` (default 160) keeps each injected dispatch's GPU-side work minimal so
`dT` measures dispatch count, not GPU work; r1 measured `c` flat over
tg∈[8,160] with a +11 ns/threadgroup slope only above 160, bounding the GPU work
at tg=8 to ≤0.09 µs/dispatch, ≤3.5% of `c`. Prefill empties stay at 0, which
also makes **`S` flat across all five receipts a free internal control**, and
avoids the prefill dispatch axis that PR #27 found self-inconsistent by 7×.

## Precision and floor safety, pre-computed

* `sd(T)` within a window ≈0.4% of 4.275 ms = 0.017 ms; a two-receipt difference
  ≈0.024 ms. Fitting `c` from `dT(2400) − dT(1600) = 800c` gives
  `sd(c) ≈ 0.030 µs`, ≈1.3% of the predicted `c`.
* Session drift is monitored, not assumed away: each receipt's own paired
  `baseline_decode_seconds_per_token` is recorded, and raw differencing is only
  used if those agree within the 0.34% feed noise measured over 929 pinned
  baselines.
* Decode floor: pinned baseline 0.013890 s/token, floor 0.95 ⇒ candidate must
  stay ≤14.621 ms/token. Base is ≈5.087 ms/token, so ≈9.53 ms of injected `dT`
  is affordable. `n = 2400` costs ≤6.26 ms even under the worst registered
  `c = 2.607 µs` with zero slack. **`c` would have to exceed 3.97 µs for n=2400
  to breach the floor**, which is implausible on a host faster than the M4 that
  measured 2.607 µs — and a floor breach returns `rejected` **with** full
  metrics, so the reading would survive anyway.
* Prefill floor is untouched because prefill injection is 0.

## Acceptance conditions I hold myself to

A receipt contributes to the fit only if it reports `max_abs_diff = 0` and
`passed_correctness`. The fit is reported with per-point receipt IDs, `S`, `T`,
both floor verdicts, and the wall-clock of the series (serial, not concurrent: the channel allows one
submission in flight per account). If every point
comes back at `dT ≈ 0`, the reported conclusion is "M5 is even further below the
knee than 2400 injected dispatches", `c` is reported as unmeasured with an upper
bound, and dispatch-count reduction is reported as worth 0 ms — this is a real
answer, not a failed experiment.

## Analysis rules, fixed before any reading arrives

Written while L0 is still validating and every level above it is unsubmitted, so
none of this is chosen with a reading in hand.

**Estimator.** Each level's `T` comes from its own session's own paired
baseline, via `T = 1000 · decode_seconds_per_token − S/128` on the candidate and
the same expression on that session's baseline. `dT(n)` is the candidate `T` at
level `n` minus **that same level's paired baseline `T`**, not minus L0's
candidate `T`. The paired baseline is the drift control the harness already
provides, and it is measured in the same session as the point it corrects, which
L0 is not. L0's role is therefore a check that the paired-baseline estimator
reads zero on a tree that is byte-identical to base, plus a third independent
free-baseline replicate; it is not the subtrahend. If the paired baselines
disagree across sessions by more than 1%, I report both estimators side by side
rather than picking the flattering one.

**Segmented fit.** Fit `dT(n) = max(0, c·(n − n_knee))` by least squares over the
four injected levels plus the L0 zero, scanning `n_knee` on a 1-dispatch grid
over `[0, 2400]` and taking `c` from the ordinary-least-squares slope of the
points strictly above the candidate knee. A level counts as "above the knee" only
if at least two levels are, so a fit resting on a single point above the knee is
reported as a bound, not a slope. `slack = c · n_knee`. The reported uncertainty
on `n_knee` is the profile interval where the residual sum of squares rises by
one `sigma²`, with `sigma = 0.024` ms (the pre-registered two-receipt
differencing noise), not a bootstrap over five points.

**Numeric action threshold.** A candidate fusion that removes `k` dispatches per
decode step is worth pursuing only if

```
k · ĉ − ŝ > 0.1 ms      with  ŝ = max(0, slack estimate)
```

where 0.1 ms is about 2% of the 5.087 ms frontier step and about four times the
differencing noise. This threshold is what makes the result actionable rather
than descriptive, and it is deliberately harsh on small fusions: even `H_sat`'s
own `slack ≤ 0.2 ms` voids every `k ≲ 80` fusion, because such a fusion buys
`80 × 2.3 µs = 0.18 ms` and spends the slack first. I will report the verdict at
`k = 40` (a per-layer fusion), `k = 100`, `k = 200` and `k = 400`.

**Fallback if all three hypotheses are rejected.** If the five points are not
consistent with any `max(0, n·c − slack)` — a negative slope, a decreasing
`dT`, superlinear growth beyond the registered `c` range, or a fitted `c`
outside `[1.0, 5.0] µs` — I do not fit a fourth model chosen to match. I report
the raw five points, state that the saturation law does not describe M5's decode
step, and name the specific shape observed. A refusal to extrapolate is the
honest output there; the advisor's downstream fusion decision then has no
quantitative licence from me in either direction, which is worth knowing.

**Scope limit, stated up front.** This probe prices the *host-encode margin of
empty, dependency-free dispatches*. That is exactly the quantity in the
"+4.1 µs per dispatch of invisible host cost" claim, so a large slack does
falsify that claim. It is **not** the whole cost of a real kernel boundary: GPU
launch ramp and tail, inter-kernel gaps, and intermediate-tensor round-trips are
GPU-side costs that a real fusion removes and an empty dispatch cannot expose.
The unattributed 1.27–1.38 ms of the decode step divided by 406 dispatches is
3.1–3.4 µs each, which is the right size for those GPU-side costs. So a
`slack ≈ 0` reading green-lights fusion (it pays on both axes), while a large
slack retires only the host-cost argument for fusion and leaves the GPU-side
argument untouched. I will not write "dispatch reduction is worthless on M5"
without that qualification attached, and the 4.1 µs measured encode cost versus
whatever `c` this fit returns is a discrepancy I will report rather than
average away.

**Known blind spot.** There is no level in `n ∈ (0, 400)`, which is where the
realistic counterfactual of removing 50–200 of 406 dispatches lives. Under
`H_sat` the slack is then a pure extrapolated intercept. The ladder can still
decide the question at the margin — if `dT(400) = 0` then `slack ≥ 400c ≈ 1 ms`
and removing 40 or 100 dispatches is worth zero, while if `dT(400) > 0` we are
in `H_sat` territory where the decision needs the slope rather than the exact
knee — but a knee at ~200 would make "remove 40" worthless and "remove 300"
valuable, and this ladder cannot separate those two. I say so rather than
implying resolution I do not have.
