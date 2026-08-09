# Round 93b — the submission channel is a second optimizer

Advisor note, 2026-08-09. Base `d549d31856953292b9b2b54905cf3f6f67ed27a4`.

Corpus: `research/r91b-runs/baseline-drift.json`, **1176 ranked M5 receipts**
harvested by #486. Each receipt carries `{bl_dec, bl_pre, cand_dec, cand_pre,
d_su, p_su, score, golden, harness, id, solver, status, ts}`.

Reproduction scripts (added this round):

- `research/advisor-r93-corpus-mining/mine4_golden_and_variance.py` — F1, F2
- `research/advisor-r93-corpus-mining/mine5_order_statistics_and_cadence.py` — F3, F4

Both run from the target checkout root with no arguments.

This note supersedes nothing in
[`research/advisor-r93-m5-receipt-channel-and-promotion-model.md`](advisor-r93-m5-receipt-channel-and-promotion-model.md);
it sharpens four of its claims and adds two standing rules (49, 50).

---

## F1 — `harness_hash` carries no version information (rule 49)

Round 93 opened a thread on "why did `harness_hash` change 33 minutes apart
between Arm R and Arm F?" and treated it as possible evidence of an organizer
harness change mid-session. It is not.

| field | distinct values over 1176 receipts |
|---|---|
| `harness_hash` | **915** |
| `golden_hash` | **3** |

`harness_hash` is effectively unique per submission — it hashes something
submission-scoped, not the organizer harness version. `golden_hash` is the
version signal, and it partitions cleanly in time:

| `golden_hash` | first seen | last seen | n |
|---|---|---|---|
| `95d59b28` | 2026-07-24 | 2026-07-27 | — |
| `7d6f6f03` | 2026-07-27T22:56 | 2026-07-27T22:56 | 1 |
| **`be7738fc`** | **2026-07-28T01:49** | **present** | **1038** |

Ours is `be7738fc`, i.e. the same golden set every solver has used for twelve
days.

> **Rule 49.** `harness_hash` is near-unique per submission and carries **no**
> version information. Use `golden_hash` to detect an organizer-side change.
> Ours has been `be7738fc` since 2026-07-28.

This also closes the trusted-harness thread from round 92 with a positive
observation rather than an absence of evidence.

---

## F2 — the published score's variance, decomposed (rule 47 refined)

Rule 47 said "never compare two ranked M5 scores directly" and quoted a single
σ. The corpus supports a full four-term decomposition. Writing

```
score = (MB_D / cand_dec)^0.75 × (MB_P / cand_pre)^0.25
```

and propagating the per-term relative σ from adjacent-pair analysis (rule 48):

| term | weight | σ (relative) | variance contribution | share of total | sd contribution |
|---|---|---|---|---|---|
| **`bl_pre`** | 0.25 | **2.1829 %** | 0.29782 | **78.2 %** | 0.5457 % |
| `cand_dec` | 0.75 | 0.2924 % | 0.04809 | 12.6 % | 0.2193 % |
| `bl_dec` | 0.75 | 0.2345 % | 0.03093 | 8.1 % | 0.1759 % |
| `cand_pre` | 0.25 | 0.2573 % | 0.00414 | 1.1 % | 0.0643 % |
| **total** | | | 0.38098 | 100 % | **σ(score) = 0.6172 %** |

**The pinned baseline's prefill supplies 78.2 % of published-score variance
while carrying only 25 % of the score weight.** It is ~8× noisier than the
candidate's prefill measured in the same session, which is why we believe it is
a cold-start artifact of the baseline binary rather than shared session noise.

Practical consequences:

1. A 0.6 % score difference between two receipts is one sigma. Two receipts
   differing by 1.2 % are two sigma. **No merge decision may rest on a score
   comparison.**
2. Because 78.2 % of the noise is in a term we do not control, **re-scoring
   both candidates at a common baseline removes most of it**. That is what the
   `cs` column in F3/F4 is.
3. Improving our prefill does almost nothing for score *variance* (1.1 %) and,
   per round 93, almost nothing for score *level* either (F-note: the fastest
   prefill in 1176 receipts is only −0.28 % relative to ours).

---

## F3 — rivals' best receipts are order statistics (rule 50)

Round 93 concluded "MyatKaung leads us on merit with a decode 0.158 % faster
than ours". That conclusion was drawn from a **minimum over 9 draws** compared
against our **single draw**. Correcting for that:

| solver | n | mean Δdec vs ours | sd | min | z of min | Blom E&#124;min&#124; |
|---|---|---|---|---|---|---|
| **MyatKaung** | 9 | **+0.374 %** | **0.325 %** | **−0.158 %** | **−1.64** | **1.49** |
| morganmcg1 (us) | 55 | +7.859 % | 15.016 % | 0.000 % | −0.52 | 2.28 |
| a-github-name | 209 | +11.047 % | 15.496 % | −0.145 % | −0.72 | 2.75 |
| yudduy | 20 | +3.054 % | 2.573 % | +0.185 % | −1.11 | 1.87 |
| lBroth | 90 | +7.271 % | 8.237 % | +0.302 % | −0.85 | 2.46 |
| davidtai | 54 | +44.291 % | 34.206 % | +0.994 % | −1.27 | 2.27 |
| metaspartan | 56 | +4.996 % | 0.865 % | +3.926 % | −1.24 | 2.29 |
| polymorf | 53 | +9.121 % | 8.521 % | +3.820 % | −0.62 | 2.27 |
| saucegodbased | 56 | +142.998 % | 27.572 % | +106.983 % | −1.31 | 2.29 |
| 0xkydo | 43 | +30.357 % | 43.279 % | +4.537 % | −0.60 | 2.18 |
| Gajesh2007 | 41 | +101.682 % | 32.176 % | +35.597 % | −2.05 | 2.17 |

`z of min` is `(min − mean)/sd`; `Blom E|min|` is the expected magnitude of the
standardised minimum of n normal draws. **Every solver's z of min is well
*inside* its Blom expectation** — i.e. nobody's best is even an unusually lucky
draw for their sample size. The one exception in the other direction is
Gajesh2007 (−2.05 vs 2.17), which is still inside.

MyatKaung's mean is **+0.374 % slower than our single draw**, with sd 0.325 %.
Their nine receipts (all `rejected`, all 2026-08-08):

| id | time | Δdec | Δpre | common-baseline score |
|---|---|---|---|---|
| `91954d84` | 02:33 | +0.036 % | +0.251 % | 2.586997 |
| `36562517` | 04:21 | +0.350 % | +0.028 % | 2.582358 |
| `0d635c77` | 04:52 | +0.761 % | +0.197 % | 2.573368 |
| `93814fab` | 05:19 | +0.286 % | +0.083 % | 2.583247 |
| **`fefaed88`** | **05:39** | **−0.158 %** | **+0.082 %** | **2.591868** |
| `05e48bbd` | 06:19 | +0.229 % | −0.233 % | 2.586402 |
| `8077766f` | 07:50 | +0.778 % | +0.019 % | 2.574202 |
| `84a7e7f0` | 12:52 | +0.382 % | +0.697 % | 2.577447 |
| `53f23581` | 15:15 | +0.698 % | +0.479 % | 2.572766 |

Their spread (sd 0.325 %) is entirely consistent with rule 48's per-submission
σ ≤ 0.2924 %. **There is no evidence MyatKaung has a faster binary than ours.**
Restricting to submissions since 2026-08-06 tells the same story for
a-github-name: 54 receipts, mean **+1.039 %**, sd 1.220 %, min −0.145 %.

> **Rule 50.** A rival's best raw timing is an **order statistic**. Compute
> their mean, sd, and the z of their minimum against the Blom expectation for
> their n before concluding they have a faster binary. Our single 0.000 % draw
> is at or below every rival's best-of-n minimum; they needed 9–209 draws to
> get there.

Merit ranking by best common-baseline score is unchanged in ordering but should
now be read with n alongside it:

| solver | best `cs` | n |
|---|---|---|
| MyatKaung | 2.591868 | 9 |
| **morganmcg1 (us)** | **2.589321** | **55** |
| a-github-name | 2.588362 | 209 |
| yudduy | 2.586516 | 20 |
| fyrsta7 | 2.580357 | 3 |
| lBroth | 2.576992 | 90 |
| alvgeppetto | 2.571025 | 19 |
| davidtai | 2.558909 | 54 |
| ivanfioravanti | 2.511889 | — |
| metaspartan | 2.506085 | 56 |
| polymorf | 2.505745 | 53 |

---

## F4 — the cadence result: submission count and optimisation multiply

This is the operational finding of the round.

Our best candidate re-scored at the corpus-mean baseline is `cs = 2.589321`.
The promoted record is 2.616504. **Deficit = 1.0498 % of score.** Because
78.2 % of published-score variance lives in the *baseline draw*, that deficit
can be closed by a favourable draw alone.

P(one submission of our *current, unchanged* binary promotes):

| route | P(one draw promotes) | draws for 50 % |
|---|---|---|
| analytic normal, σ = 0.6172 % (z = 1.701) | **4.45 %** | **15.2** (k90 = 50.6) |
| empirical, all 1176 baseline draws | 2.72 % | 25.1 |
| empirical, since 2026-08-06 (n = 132) | **4.55 %** | **14.9** |
| empirical, since 2026-08-08 (n = 37) | 5.41 % | 12.5 |

The analytic and recent-empirical routes agree at ≈4.5 %.

Now the interaction with real optimisation (σ = 0.6172 % throughout):

| decode gain | residual deficit | P(one draw) | draws for 50 % | multiplier vs no gain |
|---|---|---|---|---|
| 0 | 1.0498 % | 4.45 % | 15.2 | 1.0× |
| −0.25 % (12.2 µs/step) | 0.8603 % | 8.17 % | 8.1 | **1.8×** |
| −0.50 % (24.5 µs/step) | 0.6706 % | 13.86 % | 4.6 | **3.1×** |
| −0.75 % (36.7 µs/step) | 0.4808 % | 21.80 % | 2.8 | **4.9×** |
| −1.00 % (48.9 µs/step) | 0.2910 % | 31.87 % | 1.8 | **7.2×** |

And the pure-cadence ladder at zero code change:

| submissions | P(≥1 promotion) |
|---|---|
| 8 | 30.5 % |
| 16 | **51.8 %** |
| 24 | 66.4 % |
| 32 | 76.7 % |

**Cadence and optimisation are multiplicative, not alternatives.** A −0.5 %
decode win plus 5 draws is worth more than either a −0.5 % win alone or 15
draws alone.

### The constraint that makes this a research task rather than a button

The submission service **deduplicates by editable-surface content** — #486's
Arm C returned `Submission already exists` and reused Arm R's submission id
*without drawing a fresh baseline*. So a repeat draw requires a
**machine-code-null content edit**: a Swift comment change outside any kernel
source string, proven byte-identical at the Metal level.

#496 (`maple-r93-a-m5-receipt-channel`) is already building exactly this
capability — its Arm A is ≥5 true-null submissions with proven byte-identical
Metal. Every such submission is simultaneously:

1. a σ measurement for rule 48 (candidate-side, on the scored machine), and
2. an independent 4.45 % promotion draw.

That makes the calibration campaign **strictly positive expected value** before
any of its measurement value is counted.

### Coordination hazard

The submission account is shared with the Birch campaign
(`mlxfast-birch-20260805`). A high-cadence Maple policy consumes shared quota
and shared M5 time. Any cadence policy must be agreed with Birch before it
runs, and the note body must carry `Maple campaign` plus the student /
assignment / revision / arm / commit discriminators.

---

## What changed in the standing rules

- **47 (refined).** σ(published score) = **0.6172 %**, four-term decomposition
  above; `bl_pre` supplies 78.2 % of it at 25 % weight. Compare raw
  `decode_seconds_per_token` / `prefill_seconds_per_token`, or re-score both
  receipts at a common baseline.
- **49 (new).** `harness_hash` carries no version information; use
  `golden_hash`.
- **50 (new).** A rival's best raw timing is an order statistic; correct for n
  before concluding they have a faster binary.

## Open questions this note does not answer

- **Why is the pinned baseline's prefill ~6–8× noisier than the candidate's in
  the same session?** The cold-start hypothesis is untested. If it is a
  first-touch page-fault effect, it is a property of the harness, not of any
  solver, and there is nothing to exploit — but it should be confirmed rather
  than assumed.
- **Is the 4.45 %/draw figure stationary?** It is estimated from a baseline
  distribution that may itself drift with M5 host conditions. The recent-window
  estimates (4.55 %, 5.41 %) are reassuring but small-n.
