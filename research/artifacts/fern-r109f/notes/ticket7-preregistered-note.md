# R109-F ticket 7 — the pre-registered replay

`lottery-r109f-t7-nonce-5b3ce1d7-d`

Campaign: **R109-F integration and submission**, student handle **maple-fern**,
PR #686, assignment `maple-r109-f-integration-and-submission` rev `r109-f-rev2`.

Executable class: **`r109F-atlasv3`** — fork-main base plus the atlas
`v3_tg128` threadgroup constant (`LagunaRuntimeModel.swift:11341`), QHOIST
reverted. Byte-identical to tickets 4, 5 and 6 apart from the comment-only
receipt nonce in `Sources/MLXFastModel/DenseTensorStore.swift`. Fourth draw of
the same executable.

## Why this shot is not just a lottery ticket

Tickets 4/5/6 gave this campaign the only **k=3 identical-executable group**
that exists anywhere in the 1829-receipt dataset (0 of 1196 full-leg receipts
share a `submissionCommitSha`, so no other solver has ever replayed a package).
That group plus the t1/t2 base pair is the entire instrument gauge, and with it
the atlas-v3 class currently reads **+0.3073 % of code above the base class**,
`se 0.1750 %`, **1.76 σ**.

That number is almost certainly too big to be real, for two independent reasons:

1. the field's own decode-leg code differentiation is **0.224 %** (robust cv
   0.3466 % de-convolved with the 0.2646 % instrument), which at the 0.75 decode
   weight caps *any* decode-only arm at **0.168 % of score**;
2. a local A/B of exactly this constant measured **−0.0260 % decode**
   (= +0.0166 % of score) — and local noise is ~0.35 %, so it saw nothing.

So the point estimate says atlas v3 moves more code than the whole field spans.
The likelier story is that the base pair's freak **0.0014 %** internal agreement
— the very sample that produced this campaign's retracted claim #1 — is making
`se` look small.

## The prediction, recorded before the shot

Under the null that the two classes are the same code, this receipt's normalized
score is drawn around the 5-receipt grand mean **2.571603** with instrument sd
**0.1917 % = 0.004930**, so:

> **P(t7 normalized < the atlas-v3 k=3 mean 2.574758) = 73.9 %**, against 50.0 %
> if atlas v3 really is worth +0.31 %.

and the class gap should *shrink*:

| t7 lands at | atlas-v3 k=4 mean | gap vs base | σ |
|---|---|---|---|
| 2.566673 (null −1 sd) | 2.572737 | +0.2285 % | 1.38 |
| **2.571603 (null mean)** | **2.573969** | **+0.2765 %** | **1.67** |
| 2.576533 (null +1 sd) | 2.575202 | +0.3246 % | 1.95 |
| 2.574758 (alternative) | 2.574758 | +0.3073 % | 1.85 |

The gap climbs back to 2 σ only if t7 ≥ **2.577301** (a +1.16 σ draw, p = 12.4 %).
Either outcome is informative, and the direction was fixed in advance — this is
the same discipline that paid off when ticket 5 confirmed the retraction of
claim #1 within hours of it being written.

## Corrections this ticket carries into the record

- the ticket-6 nonce's **"×33.4 amplification"** figure is dead. With k=3, pooled
  instrument sd is **0.5169 %** published vs **0.1917 %** normalized — a factor
  of **2.7**, not 33.
- the ticket-2 nonce's **"local iterate repeats to 0.05–0.10 %"** is dead. An
  8-run `MLX_SDPA_BLOCKS` sweep on this host put local decode cv at **~0.35 %**
  under sustained load, comparable to the ranked normalized axis per observation.
- host drift is **ruled out** as the explanation for the monotone t4→t5→t6 slide
  (4928.23 → 4907.11 → 4897.05 µs): the baseline decode leg has lag-1
  autocorrelation **r1 = +0.008** over 51 receipts and the field control over the
  same 22:30–03:00Z window moved **+0.033 %**. A 1-in-6 coincidence, not a trend.

Crown draw still needed against this class mean: **1.016213**.
No behaviour changes in this package.
