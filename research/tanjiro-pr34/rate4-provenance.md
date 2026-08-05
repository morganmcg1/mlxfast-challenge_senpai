# Rate 4 provenance, the failed R4 receipt, and the retry rule

This answers the two questions the advisor raised on PR #34 before r2's readings
arrive, because the answers change what the r2 receipts have to carry. Both are
settled from my own r1 notebook and from the four submitted trees, so neither
needs a receipt.

## The four r1 knob configurations

Recovered from the submitted trees rather than from prose, with

```
git show <commit>:Sources/MLXFastModel/LagunaRuntimeModel.swift \
  | grep -oE 'DARKBLOOM_INJECT_(DECODE_ATTN|DECODE_ROUTED|PREFILL_ROUTED|PREFILL_ATTN)", [0-9]+'
```

| tree | DECODE_ATTN | DECODE_ROUTED | PREFILL_ROUTED | PREFILL_ATTN |
| --- | --- | --- | --- | --- |
| R1 anchor | 0 | 0 | 0 | 0 |
| R2 | 40 | 0 | 39 | 0 |
| R3 | 40 | 39 | 0 | 40 |
| R4 | 0 | 39 | 20 | 0 |

## (a) R2 and R3 are nested on the decode axis, so rate 4 is a plain difference

R3 keeps R2's forty injected attention QMV copies exactly where R2 had them and
adds thirty-nine routed QMV copies on top. `cfg-r3.md`, written at the time,
says so in as many words: the decode attention knob "stays exactly where R2 had
it ... Both receipts carry the same 40 injected attention copies, so their
difference is purely the routed QMV block."

So `dT4 = T(R3) - T(R2)` is a two-receipt difference between a strictly nested
pair, not a difference of differences. The advisor's arithmetic
`2.24137 - 1.23070` is the same number by a different route: both expressions
reduce to `T(R3) - T(R2)` because the anchor cancels. There is no third receipt
inside rate 4 and no accumulated error from one.

On the prefill axis R2 and R3 are disjoint single-knob arms, each differenced
against the shared zero anchor R1. That is also a valid two-receipt difference,
just a different pairing.

## (b) The failed R4 receipt was not the source of rate 4

R4's decode probe was routed QMV *alone*, with the attention knob back at zero.
That is the unloaded companion to rate 4, an upper bound, not the headline. The
published rate 4 of 546.2 GB/s, labelled "R3-R2, loaded", rests entirely on two
successful receipts, `6757de65` and `ca416f01`.

R4 carried only robustness companions: the second level of rate 1, a loaded
cross-check of rate 2, and that unloaded upper bound for rate 4. Losing it costs
three consistency checks and no headline rate. Rate 4 therefore does not need an
independent re-run, the advisor's contingency for reallocating an r2 receipt is
moot, and all five r2 receipts stay on the dispatch law.

## The rate 4 error bar was already two-receipt, and here is a wider one

With `sd(T)` at 0.34% relative, `sd(T_R2) = 0.01872` ms and
`sd(T_R3) = 0.02216` ms, so the quadrature sum is 0.02900 ms. The published bar
was +-0.034 ms. The ratio 0.034 / 0.029 is the same 1.18 method factor my other
bars carry: for `dT2 = T(R2) - T(R1)` quadrature gives 0.02371 against a
published 0.028. So the published bar already propagated two receipts and was
not the single-receipt figure.

What the published bar did *not* include is that R2 and R3 ran in different
official sessions. Their normalisations agreed to within 2.6%, which on a
1.01 ms difference is a 0.026 ms drift allowance. Adding that in quadrature
gives a fully conservative

```
dT4 = 1.01067 +- 0.043 ms
rate 4 = 546.2 +- 23.3 GB/s  =  [523, 569] GB/s
```

The roofline time for 552.08 MB at 610 GB/s is 0.90505 ms, so the excess is
+0.1056 +- 0.043 ms. Still more than two sigma from zero, still 7.9% +- 3.2% of
the 1.383 ms decode residual. The conclusion does not move.

## Why `afec358a` failed: a code-review gate, not timing

`afec358a-4269-439d-b740-fe4ff3ac5ec6` returned `status=failed` with
`officialScore=None` and no timed metrics at all. The reason string is

> workflow run concluded failure at step "Review submitted code for benchmark
> bypasses"

Created 22:09:28Z, updated 22:53:48Z, so it consumed a full slot and produced
nothing.

I can rule out the obvious explanation. The R4 tree differs from the R3 tree
that passed the same reviewer twenty minutes earlier in exactly four integer
literals: the four knob values in the table above. Every other byte is
identical. In particular `DARKBLOOM_INJECT_ARCH_PROBE` was zero in all four
submitted trees and was introduced in the pre-R1 instrument commit, so the
arch-string branch cannot be the differentiator: the same reviewer saw the same
code three times, passed it, then failed it.

That leaves a non-deterministic reviewer, or an infrastructure error inside that
step. Either way the programme-level fact is the same and worth recording: an
official submission can consume a slot and return no metrics for reasons
unrelated to the candidate.

## Retry rule, declared before it is needed

A receipt that returns `status=failed` with no timed metrics is a retry, not a
data point. I will resubmit the identical tree and record both attempts. The
five authorised receipts are five *readings*, not five API calls. If retries push
the series past a reasonable wall clock I will say so rather than quietly drop a
level.

## Contamination check on the r2 instrument: clear

The r2 hook picks its count with

```swift
let emptyTotal = isSingleTokenDecode ? lagunaInjectDecodeEmpty : lagunaInjectPrefillEmpty
```

and `isSingleTokenDecode` is a `dims(1,1)` test on the input, evaluated once per
forward and consulted inside the layer loop. So the decode empties fire only on
genuine one-token steps. The 512-token seed forward inside the decode pass takes
the prefill branch, which is pinned at zero for the whole r2 series.

That matters because the decode axis is reported as
`T = 1000 * decode_seconds_per_token - S / 128`. If injection had leaked into the
seed forward, `S` would have moved and `T` would have carried an `n`-dependent
bias through the `S / 128` term. With prefill empties at zero, `S` is a flat
control and `T` is clean.
