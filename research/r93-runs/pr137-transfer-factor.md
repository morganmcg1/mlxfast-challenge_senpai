# Deliverable 6 — re-deriving the PR #137 M4 → M5 transfer factor from raw timings

## What the old number was and why it was unusable

The campaign has been carrying `T ≈ −0.40 ± 0.24` as the factor that converts a
measured M4 decode delta into the M5 decode delta for the same change. That
number was computed from **ranked scores**, and it inherited two defects:

1. A ranked score is `decode_speedup^0.75 * prefill_speedup^0.25`, normalised
   against the baseline drawn in that same session. Rule 48 records that the
   baseline's prefill coefficient of variation is roughly eight times the
   candidate's. Dividing by that baseline injects the noisier quantity into the
   comparison, and comparing two scores from two sessions does it twice.
2. The particular pairing used, `+0.803 %` against `7ce1262d`, put 49 hours
   between the two receipts. Over that gap the same-session baseline itself
   moved, so the difference is not attributable to the code change.

The `± 0.24` was therefore not a real confidence interval on a physical ratio;
it was mostly the spread of a badly chosen estimator.

## The correct pairing

PR #137 shipped an arm that could be switched on and off with no other
difference in the submitted surface. Two receipts were taken close together in
the same channel:

| receipt | arm | raw candidate decode s/token |
| --- | --- | --- |
| `08ddee45` | OFF (paired control) | 0.0049164280625 |
| `99b71258` | ON | 0.0049330185546875 |

Raw M5 effect of turning the arm on:

```
Δ = 0.0049330185546875 − 0.0049164280625
  = +1.65905e-05 s = +16.590 µs per decode step
  = +0.3375 %
```

Because both receipts carry their own same-session baseline, we can also compute
the drift-cancelling paired form on `decode_speedup`, which gives **+0.3795 %**.
The two forms agree to within 0.05 percentage points, which is the useful part:
whatever session drift existed between these two receipts is small compared with
the effect, so the raw difference is trustworthy here.

We use **+0.34 %** (raw) as the central M5 value and note **+0.38 %** as the
drift-corrected alternative.

## The M4 side

The M4 measurement of the same change is the corrected balanced census in
`research/maple-fern-pr137-lmhead-cascade.md` (lines 446, 478, 491):
**−64.5 µs, i.e. −0.785 %** of the M4 decode step.

The earlier `−112.5 µs` wall-clock figure from the same investigation was
retracted in that document because it was measured with an unbalanced arm
ordering; it must not be reused.

## The factor

```
T = ΔM5 / ΔM4
raw form:             +0.3375 % / −0.785 % = −0.430
drift-corrected form: +0.3795 % / −0.785 % = −0.483
```

**`T ≈ −0.48`, with a plausible range of −0.43 to −0.49.**

That range is the spread between the two *forms of the arithmetic*, not a
confidence interval, and it must not be read as one.

**The M5 sign is not established.** R93 section 9.3 measures the candidate-side
decode CV at 0.3386 % from machine-code-identical nulls. The M5 side of this
ratio is one receipt against one receipt, so its 95 % resolution is
`1.96 × 0.3386 × √2 = ±0.94 %`, about ±46 µs per step. The measured M5 effect,
`+0.34 % = +16.6 µs`, sits well inside that band. A candidate true value of
`0.00 %` — and hence `T = 0` — is entirely consistent with these two receipts,
as is a modest true improvement.

What *is* established is the asymmetry that matters: the M4 census predicted
`−0.79 %` and the M5 delivered something indistinguishable from zero. The
defensible headline is therefore **`|T| < 0.5`**, not `T = −0.48`. Pinning the
sign would need roughly n=4 receipts per arm on the M5 side, which is more
official budget than this one transfer factor justifies.

## How to use it, and how not to

- `T` is a single-change, two-point estimate. It is a **sign warning**, not a
  calibration constant. One point cannot support a confidence interval, and we
  do not manufacture one.
- The honest operational rule it supports is: *an M4-only decode win of this
  kind is not evidence of an M5 win, and may be evidence against one.* That is
  enough to change our behaviour — it stops us spending official runs on
  M4-derived decode micro-wins — without pretending to a precision we do not
  have.
- It says nothing about prefill, and nothing about changes that alter kernel
  selection. The M4 Pro reports Apple GPU generation 16 and does not select the
  `_nax` prefill kernels the ranked M5 uses, so for any `_nax`-touching change
  the M4 number has no transfer factor at all — it is simply a different
  kernel.
- Any future re-estimate must be built the same way: raw candidate timings from
  two receipts of the same channel taken close together, never a cross-session
  score difference.
