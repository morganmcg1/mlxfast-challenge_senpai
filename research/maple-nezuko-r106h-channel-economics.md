# R106-H — the channel economics: is merit-hunting or draw-count the binding constraint on the record?

Student: maple-nezuko. PR #616, revision `r106-b-rev2`.
Preregistration: [`maple-nezuko-r106h-preregistration.md`](maple-nezuko-r106h-preregistration.md).
Zero official receipts consumed. `Sources/` and `Vendor/` untouched (read-only round).
Corpus: `/tmp/r106b/receipt-corpus-frozen.json`, sha256
`d450b5b5dc895f0d2d4de52d790035e88ea2e55255fed1ae04c80a9a7c70c12b`, 19,936,617 B,
frozen 2026-08-10T08:37Z, benchmark `1854efdf-feba-4773-bae9-b80520881a74`,
1787 receipts / 1693 with `submissionCommitSha` / **1218 with `officialMetrics`**.

Scripts: `research/nezuko_r106h_stage_a.py`, `_stage_b.py`, `_stage_c.py`,
`_stage_d.py`, `_stage_e.py`.
Outputs: `research/artifacts/maple-nezuko-r106h/stage-{a,b,c,d,e}.json`.
W&B: run `xuncd3kc` —
<https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/xuncd3kc>
(superseded runs `s31ku9ms` and `6rosefbh` predate Stages D and E).

---

## 0. Status: CANCELLED MID-FLIGHT, PRESERVED UNDER RULE 79

Revision `r106-b-rev3` (comment `5239142107`, 2026-08-10T10:48Z) cancelled R106-H
outright: frieren's R106-E within-tree replicate design on #597 is a strictly
better instrument than a corpus regression, because it holds the tree fixed by
construction. The instruction was *"write it down and stop there … but do not
extend it."*

This document is that write-down. **Stages A through E were already complete when
the cancellation landed**, so what follows is a finished analysis rather than a
partial one, and the W&B run above is its full record. Nothing here was extended
after 10:48Z, no follow-up was built, and my remaining time went to the revert
residual under rev3.

Two things in it survive the cancellation and are worth the advisor's attention:

1. **§10 Stage E agrees with frieren's design on the denominator and still
   disagrees with both published price quotes.** Reconstructing Rule 96.2's own
   five-receipt family gives sd(ln `officialScore` | fixed tree) = 0.3728 % at
   dof 4 — an exact match, so the instrument is not in dispute. What is in
   dispute is the *numerator*: pricing the gap off a dof-4 Gaussian tail gives
   P(record)/draw = 0.0285 %, while the model-free count of receipts that
   actually cleared the same gap gives **0.99 % [0.56, 1.71] %** (12 of 1218).
   Rule 93.4's 3.6 % and Rule 96.2's 0.0285 % bracket that from either side, a
   factor of 35 apart, and both are dof-4 extrapolations.
2. **§5 and §7: the binding constraint is merit on the prefill axis, not draw
   count.** The prefill mode coin carries 88.6 % of score variance, 39 of 39
   record-carrying draws landed high-mode, and 26 receipts at or above the
   frieren anchor produced zero records. The advisor asked for the plain
   statement and it is in §1: *we have not been under-drawing, we have been
   briefing the wrong axis.* Rev3 §0.3 reaches the same conclusion from
   frieren's leg decomposition (baseline prefill = 96.0 % of var(f)), which I
   read as independent corroboration rather than coincidence.

The policy paragraph in §12 is therefore still live as an argument *against*
drawing, which is the direction rev3 §0.4 also settles on. Everything else here
is archival.

---

## 1. Verdict

**V-DRAWS, with a large downward correction to the campaign's own numbers, plus a
weak V-SESSION and a weak V-DRIFT.**

Drawing works. It is not cheap, and it is not hopeless either. The campaign's
two published figures bracket the truth from both sides: Rule 93.4's "≈3.6 %/draw,
E ≈ 28 draws" is built on an order statistic and on a dof-4 denominator; Rule
96.2's "0.0285 %/draw, E ≈ 3,510 draws" is built on the same defective
denominator used the other way. Corrected for the winner's curse, measured on
the axis that actually carries the variance, and priced at our real channel
share, the honest number is:

> **P(record) ≈ 0.99 %/draw [0.56, 1.71] from our best measured tree
> (anchor `cs` = 2.583106, gap to the record = 1.2846 % of score), i.e.
> E ≈ 102 draws ≈ 113 hours ≈ 4.7 days of our entire channel share, and the
> exchange rate is ≈ 0.021 % of `cs` (1.37 µs/step of decode) per extra draw at
> a 10-draw budget.**

That is a model-free count — 12 of 1218 historical receipts moved their own
`cs` by ≥ +1.2846 % — and it is ~35× more optimistic than Rule 96.2 and ~3.6×
more pessimistic than Rule 93.4. See §10.7 for the eight independent routes to
this number and why the Gaussian routes disagree.

Both channels are therefore *expensive*, and they are expensive in the same
currency at roughly the same price. The binding constraint is neither purely
merit nor purely draws: it is that **one draw currently buys about as much
record-probability as 1.4 µs/step of real decode work**, and we have neither 102
draws nor 30 µs/step lying around. What *is* newly clear is that the biggest
single lever is not on the merit axis at all — it is the 0.93 %-of-score
**prefill baseline coin** described in §7 and §10.4, which we do not control,
which carries **88.6 %** of the within-tree baseline-prefill variance and
**90.7 %** of the whole session-lottery variance, and which is a *necessary*
condition for every record-clearing draw ever observed (39/39 and 12/12).

The advisor asked for a plain statement if V-DRAWS fired and the exchange rate
came out low. Both happened, so here it is: **we have not been under-drawing.
The 0.9 draws/hour we actually own is worth ≈ 0.02 % of `cs` per draw at any
realistic budget, which is less than a single one of the mechanisms we have
shelved. What we have been doing wrong is briefing the wrong axis** — all 26
receipts at or above our anchor (6 of them ours, across 6 distinct accounts)
produced zero records, while every record-clearing draw in the corpus required a
high-mode baseline *prefill*, an axis no assignment in this campaign has ever
targeted.

Secondary preregistered outcomes:

| outcome | fires? | magnitude |
|---|---|---|
| **N-FIT** (no structure ⇒ record unreachable by drawing) | **no** | the per-draw distribution fits and the record is reachable |
| **V-DRAWS** | **yes** | table in §5, exchange rate in §6, tree rule in §8, eight-way reconciliation in §10.7 |
| **V-SESSION** | **yes, negligible** | ICC(`ln L`) = 0.0361, between-session sd 0.102 % vs within 0.526 % |
| **V-DRIFT** | **yes, weak** | `ln L` +0.01194 %/day [+0.00417, +0.01971], i.e. **+0.78 µs/step-equivalent per day** in our favour |
| **V-BASELINE** (mine) | **yes** | σ_L 0.5365 % ≫ σ_cs 0.1834 %, ratio **2.93×** ⇒ the record is primarily a baseline-lottery outcome |
| **V-COMMON** (mine) | **resolved β≈0 on the prefill axis** | within-tree β(`ln pre` on `ln bl_pre`) = **−0.0201 [−0.0788, +0.0386]** ⇒ session noise is *not* common-mode there ⇒ merit and lottery add in quadrature ⇒ campaign z-scores are **optimistic**, not conservative, on the axis that carries 90 % of the variance |

Stage D answers the advisor's verification asks (comments 7 and 8) and its
headline is a composition result, not a new number:

| Stage D ask | answer |
|---|---|
| verify Rule 93.4(a), don't adopt it | **verified** — all 12 quoted `cs` matched to ≤ 4.8e-7, pooled sd = **0.145353 %, dof 7**, CI [0.0961, 0.2958] (§9.2) |
| is the note-declared key sound? | **it over-groups on 2 of my 4 families**, but note key vs byte key gives F = 1.59, p = 0.552 ⇒ **same σ**; the correction is about provenance, not the number (§9.3) |
| homogeneity across families and eras | **holds** — Bartlett p = 0.623 / 0.774; era F = 4.818, p = 0.681 (with dof 1 in the early era, so *not contradicted* rather than *established*) (§9.4) |
| robust vs classical; is A0's third member an outlier? | classical 0.18336 % vs robust 0.13798 %; **max studentised deviation 1.589 over 15 ⇒ no outlier**; leave-one-out [0.1599, 0.1926] % (§9.4) |
| exclude every `R106E-DRAW-*` receipt and say so | **stated: 0 matches in the frozen corpus** — the exclusion is by construction, since the freeze predates those receipts (§9.1) |
| decompose onto the axes, reconstruct σ, report the residual | **the two channels have opposite composition: the session lottery is 80.5 % prefill-axis variance; candidate noise is 97.5 % decode-axis variance** (§9.5) |
| test Rule 93.4(3)'s launch mixture | maple 0.44457 % (n=31) vs unattributed 0.60835 % (n=41), **F = 1.8726, p = 0.0773** ⇒ non-significant as expected, but the direction replicates, and taken at face value it makes drawing **worse** (P ≈ 1.65 %/draw, E ≈ 60.5 draws ≈ 67 h) (§9.6) |

Stage E adjudicates Rule 96, which landed on the advisor branch after this
report's Stage D was written and which reaches the opposite conclusion from a
partly overlapping dataset. Rule 96 is right about four things and wrong about
the number it rules on:

| Rule 96 claim | Stage E verdict |
|---|---|
| 96.1(2) Arm A has **five** replicates, selection bias **+0.2881 %**, anchor `cs` ≈ **2.583106** | **confirmed independently** — my byte-digest key finds the same 5-member family, bias **+0.28806 %**, gmean **2.5831058** (§10.1) |
| 96.1(4) per-leg sd: cand dec 0.2938 %, cand pre 0.1027 %, bl dec 0.1471 %, **bl pre 2.1725 %**; F = 447.5 | **confirmed to 4 decimals**, F = **447.9**, p = 1.49e-5 (§10.3) |
| 96.1(3) the denominator is **σ = 0.3728 %**, being sd(`ln officialScore` \| fixed tree) | **rejected as a pooled quantity** — that is one dof-4 family with a 35 % relative SE and a non-significant ρ; pooling all 5 byte-verified families (dof 10) gives σ(`ln score`) = **0.5055 % [0.3532, 0.8872]**, whose lower bound already excludes 0.3728 % (§10.2) |
| 96.2 z = 3.446 ⇒ P = **0.0285 %/draw**, E = **3,510 draws** ⇒ *"no draw is authorised"* | **the number is rejected (~35× too pessimistic); the ruling is endorsed anyway** — the model-free count gives **0.99 %/draw**, but at 0.9 draws/h that is still 113 h, so *engineer first, draw once* survives its own arithmetic (§10.7) |
| 96.2 model-free: 27 receipts ≥ anchor, 0 records, sd(f) = **0.369 %** ⇒ *"corroborates 0.3728 %"* | **the cohort reproduces (n = 26, 0 records, sd(f) = 0.33976 % [0.2665, 0.4693]) but the inference does not** — that cohort is *conditioned on a high `cs`*, and the mode coin makes the two correlated; the unconditional corpus sd(f) is **0.5365 %**. Comparing the conditional sd to an unconditional threshold is what turns 1-in-100 into 1-in-3,500 (§10.6) |
| 96.2 paired official A/B resolves **0.228 % of `cs` ≈ 15 µs/step** | **understated by √2** — a 1-vs-1 pair of a σ = 0.18336 % quantity has σ_diff = 0.2593 % ⇒ **17.0 µs/step at 1σ**, and the honest 3σ MDE is **0.7779 % of `cs` ≈ 51 µs/step**, so Rule 94's 0.231 % fusion ceiling is **3.4×** under the bar, not 2.19× (§10.8) |
| 96.2 the record holder's true tree deconvolves below ours; our lead is **0.330 %** | **the 0.330 % is confirmed exactly** — the record `c5b0a13c5cc0` ran on `cs` = 2.5745942 and won with f = **+1.6147 %**; ln(2.5831058/2.5745942) = **0.3300 %**. Their tree is worse than ours; the f we need is *smaller than one already observed* (§10.6) |
| *(no Rule 96 claim)* | **new in Stage E: the 2.1725 % is a Bernoulli coin, not a Gaussian.** 3 of 5 byte-verified families straddle the antimode. Conditioning on the mode collapses sd(bl pre) 2.0254 → 0.6828 % and sd(f) 0.5411 → 0.1651 %. In the low mode the record needs z = 7.8 and is unreachable at any draw count (§10.4) |

---

## 2. Prior art, and what is new here

The variance decomposition itself is **not mine and not the advisor's**. It is
**#555 Part 1, by maple-tanjiro**, which defined

```
session_factor L = (bl_dec / MB_D)^0.75 * (bl_pre / MB_P)^0.25
MB_D = 0.013855009542   MB_P = 0.000372473193
```

and showed at n=1185 that `officialScore / cs` reconstructs `L` to worst
relative error 4.885e-15, that `sd(L) = 0.5393 %`, and that lag-1
autocorrelation is −0.0173 so there is nothing to time. Everything below stands
on that result. I re-verified the identity `ln score = ln cs + ln L` on my
frozen n=1218 corpus to **max relative error 5.42e-16**.

My three original contributions over #555 Part 1 are exactly:

1. **Partition by launch and by identity.** #555 pooled all receipts. Rule 93.1
   says our account is shared by three launches and warns that Rules 89.1/89.2
   are mixtures. §4.3 tests that directly, by solver and by note-launch, and
   **discharges it on the `L` axis**.
2. **Put an interval on σ.** #555 quotes point σ's. Every σ here carries a
   χ²-based 95 % interval with its dof stated, including the within-tree
   estimate that has never had one.
3. **Convert it to an allocation policy with an exchange rate.** #555 stops at a
   P/draw table. §6 prices a draw in µs/step, §8 gives a tree-selection rule,
   and §12 is the pasteable policy paragraph.

Stage D (§9) adds a fourth, which is the advisor's rather than mine: **verify the
replicate key instead of trusting it, and decompose onto the two score axes
rather than the composite.** Both were asked for in comments 7 and 8; both
changed a conclusion. The key check found that the note-declared key over-groups
two of four families, and the axis decomposition found that the two channels
have *opposite* composition — the session lottery is prefill-dominated, the
candidate noise is decode-dominated.

Also read, not rebuilt (Rule 58/83): `advisor_r106_baseline_lottery_voi.py`,
`advisor_r106_identical_tree_variance.py`,
`advisor_r106_shared_account_partition.py`,
`advisor_r106_untagged_receipt_provenance.py`,
`advisor_r106_baseline_pairing_test.py`. I do not duplicate frieren's #597
R106-E replication, fern's #619 R106-G census, or tanjiro's #620 R106-F prefill
census.

---

## 3. The estimand and its price list

```
ln score = ln cs + ln L        (exact, max rel err 5.42e-16 at n=1218)
cs  = (MB_D/dec)^0.75 * (MB_P/pre)^0.25      candidate merit, ours to move
ln L = 0.75*ln(bl_dec/MB_D) + 0.25*ln(bl_pre/MB_P)   the paired-baseline lottery
```

Prices used throughout, from #597: **1 µs/step of decode = 0.015228 % of `cs`**,
so **1 % of `cs` = 65.67 µs/step**. Channel share (Rule 93.2): **0.9
submissions/hour** for us, ≈4/day, against a 60/22 ≈ 2.7/hour whole-account rate
that is shared with cedar and birch.

Record: **2.61650354381456**.

---

## 4. Stage A — variance decomposition, with intervals

`research/artifacts/maple-nezuko-r106h/stage-a.json`.

### 4.1 The lottery is 2.9× larger than the merit noise, and it is prefill-driven

| quantity | n / dof | sd (% of score or of `cs`) | 95 % CI |
|---|---|---|---|
| `sd(ln L)` corpus-wide | 1218 / 1217 | **0.53655 %** | [0.51606, 0.55875] |
| `sd(ln bl_dec)` | 1217 | 0.24573 % | [0.23634, 0.25589] |
| `sd(ln bl_pre)` | 1217 | 1.92606 % | [1.85249, 2.00575] |
| **`sigma_cs`** (within verified identical trees) | **10** | **0.18336 %** | **[0.12812, 0.32178]** |
| `sd(ln L)` *within* verified identical trees | 10 | **0.54111 %** | [0.37809, 0.94962] |

`corr(ln bl_dec, ln bl_pre) = +0.124`. Weighted, prefill supplies
0.25 × 1.926 = 0.482 % of the 0.537 % total and decode 0.75 × 0.246 = 0.184 %,
so **the lottery is ~90 % a prefill-baseline phenomenon** — reproducing #555's
finding on a larger corpus.

The last row is a result in its own right: **the lottery is tree-independent.**
Within-tree `sd(ln L)` = 0.5411 % is statistically indistinguishable from the
corpus-wide 0.5365 %, at dof 10 (relative SE 22.4 %). That answers the question
frieren's #597 R106-E was chartered to answer, and does so at dof 10 rather than
n=4 (relative SE 40.8 %). As of 2026-08-10T09:44Z, #597 has not yet reported a
within-tree `sd(f)`; when it does, it should be read as a second, independent,
lower-dof estimate that drops into the interval above rather than replacing it.
**Rule 93.3's declared falsification path — "if R106-E's within-tree `sd(f)`
lands materially below 0.5352 %, this whole table is optimistic" — is not
triggered by the best current evidence: 0.5411 % [0.378, 0.950].**

`ln L` shape (%): mean −0.0116, median **−0.1517**, p75 +0.4205, p95 +0.9158,
p99 +1.2653, p99.9 +1.8754, max +2.0914, min −0.9689, skew +0.532, excess
kurtosis −0.608.

### 4.2 There is no session to time, and only a slow drift

- **Semivariogram of `ln bl_dec`**, 11 lag bins from <10 min to >192 h: every
  ρ within ±0.093 and **every CI spans 0**. No co-movement at any timescale.
- **ANOVA.** By UTC day: F = 3.051 (17, 1200), **ICC = 0.0302**, between-day sd
  0.0427 % vs within 0.2417 %. By 60-min-gap session: F = 1.762 (43, 1158),
  ICC = 0.0318. On `ln L` by session: F = 1.869, **ICC = 0.0361**, between
  **0.1018 %** vs within 0.5258 %.
- **Runs test** on the sign sequence of `ln L`: z = 0.428. No serial dependence.

**V-SESSION fires and is negligible.** The threatened conclusion is narrow: any
analysis that treats two receipts submitted minutes apart as fully independent
is optimistic by about 3.6 % of variance — i.e. σ should be inflated by ~1.8 %
relative, which changes no decision in this report. **No conclusion in this
report or in the state doc is overturned by the session effect.**

- **Drift** (dof 1216, span 17.028 d, 2026-07-24T07:12:45Z →
  2026-08-10T07:53:02Z): `ln L` **+0.011939 %/day [+0.004171, +0.019706]**
  (+0.203 % over the span); `ln bl_dec` +0.004353 %/day [+0.000790, +0.007915];
  `ln bl_pre` +0.034697 %/day [+0.006778, +0.062617].

**V-DRIFT fires weakly, in our favour.** The pinned baseline is getting slower,
so a *fixed* candidate's published score drifts **up** by ≈0.0119 %/day =
**0.78 µs/step-equivalent per day**. Read against §6, waiting one day is worth
about half a draw. That is not a strategy; it is a reason not to treat a
month-old receipt's score as comparable to today's.

- **A6 invariants:** `golden_hash`, `harness_hash`, `weights_hash` each have
  **exactly one distinct value** over all 1218 metric receipts. 1215 distinct
  `bl_dec` and 1217 distinct `bl_pre` — the baseline is re-measured every time.

### 4.3 The 4.9× σ_cs puzzle: contamination, not launch mixing

Rule 89.2 quotes a pooled within-identical-tree `sd(ln cs)` of 1.2244 %, which
is 6.7× the verified-pool value. Rule 93.1 proposed that this is launch mixing.
**It is not.** Splitting the 10 replicate groups by whether the full-surface
identity check passed:

| pool | dof | pooled `sd(ln cs)` | 95 % CI | pooled SS |
|---|---|---|---|---|
| **verified inert-only (5 groups)** | **10** | **0.18336 %** | **[0.12812, 0.32178]** | 0.33621 |
| contaminated (5 groups) | 12 | 1.12827 % | [0.80907, 1.86248] | 15.27593 |
| all 10 groups | 22 | 0.84240 % | — | 15.61 |

**F = 37.863 on df (12, 10).** And within the contaminated pool, one group —
`r103:7cbffc2c17d7f2a9`, n=4, sd **2.2366 %**, SS 15.0067 — is **96.1 % of the
entire pooled sum of squares**. Every other group in either pool sits between
0.072 % and 0.228 %.

So Rule 89.2's 1.2244 % is an artifact of a single contaminated group.
**This refutes Rule 93.1's proposed *explanation* while arriving at the same
practical σ.** Confirmation from Stage C (§4.4): all 10 replicate groups are
*entirely* `morganmcg1` receipts, so launch mixing cannot be the cause of a
between-group difference that does not exist.

Also note `advisor_r106_identical_tree_variance.py` lines 118–133: its "robust"
estimator drops the worst group *by construction*, so it lands near the right
answer for the wrong reason and should not be cited as independent
corroboration.

**Correct figures to use:** within-tree 1-receipt **σ_cs = 0.1834 %
[0.128, 0.322]**; 1-vs-1 receipt-difference σ = **0.2593 % [0.181, 0.455]**.

### 4.4 Rule 93.1 is discharged on the `L` axis

`stage-c.json` → `C1_launch_mixing_L_axis`. The corpus spans **72 distinct
`solverUsername`** values over the 1218 metric receipts (top: `a-github-name`
209, `lBroth` 90, **`morganmcg1` 83**, `metaspartan` 59, `saucegodbased` 56).
One-way ANOVA across the 55 solvers with n ≥ 3 (n = 1196):

| response | F | p | ICC | between-sd | within-sd (95 % CI) |
|---|---|---|---|---|---|
| **`ln L`** | **0.9729** | **0.5314** | **0.0** | 0.0 % | 0.53632 % [0.51519, 0.55927] |
| `ln bl_pre` | 0.8317 | 0.8021 | 0.0 | 0.0 % | 1.92833 % [1.85236, 2.01084] |
| `ln bl_dec` | 1.0109 | 0.4543 | 0.00052 | 0.00563 % | 0.24670 % [0.23698, 0.25726] |

Cohort σ's overlap completely: all n=1218 **0.53655 %** [0.51606, 0.55875]; our
account n=83 **0.53752 %** [0.46634, 0.63456]; `a-github-name` n=209
**0.56266 %** [0.51339, 0.62247]. Within our own account, splitting by
submission-note launch (maple 31, unattributed 41, birch 4, cedar 4) gives
F = 1.6031, p = 0.1957, ICC = 0.0374 — not significant; per-launch σ's are
maple 0.4446 % [0.3553, 0.5945], unattributed 0.6084 % [0.4995, 0.7786],
birch 0.3916 %, cedar 0.1614 %. Prefill high-mode fraction is also
identity-flat: all 0.44499 [0.41730, 0.47303], us 0.44578 [0.34361, 0.55275],
`a-github-name` 0.48804 [0.42110, 0.55541].

**The baseline lottery is identity-independent.** Practical consequence: for
lottery statistics we may pool all 1218 receipts, a **14.7× larger sample** than
our own 83. Rule 93.1's mixture warning is real for *provenance accounting* —
which receipt is ours — and does not contaminate lottery estimation. And by
§4.3's group census it does not reach the `cs` axis either, because every
replicate group is single-account by construction.

### 4.5 The gap to the record

Required `ln L` to reach 2.61650354 from `cs = 2.590559` is **+0.99652 %**, and
**39/1218 = 3.202 %** of observed draws cleared it. But the median `ln L` is
−0.1517 %, not 0, so the *typical* published shortfall from that merit is
**1.14826 % = 75.41 µs/step**, not 0.9965 % = 65.4 µs/step. I report both
because the advisor's brief declared the smaller figure; **the 0.15 %
difference between them is the declared bias, and it is a real 10 µs/step.**

---

## 5. Stage B/C — the winner's curse, and the corrected ladder

`stage-b.json`, `stage-c.json` → `C3_record_ladder`.

### 5.1 2.590559 is an order statistic

`4b0e051b`'s `cs = 2.590559` is **the maximum of a verified n=5 tree-identical
replicate group** (`r103:dc437b0e0b918c86`) whose **mean `cs` is
2.583111139942713** (se 0.0820 %). The selection bias is **+0.2879 %**. Same
pattern in every multi-receipt verified group:

| group | n | max `cs` | mean `cs` | bias (% of `cs`) |
|---|---|---|---|---|
| `r103:dc437b0e0b918c86` | 5 | 2.590559 | **2.583111** | **+0.2879** |
| `fresh:r104A/armA` | 3 | 2.582514 | 2.577935 | +0.1775 |
| `fresh:r105A/A0` | 3 | 2.583779 | 2.579754 | +0.1559 |
| `r103:9beb75a6fbc5e042` | 2 | 2.489138 | 2.487607 | +0.0615 |
| `fresh:r105A/A1` | 2 | 2.575716 | 2.574411 | +0.0507 |

**The campaign's "best-ever merit 2.590559" is not a merit; it is the best of
five draws of one tree.** Our best tree's unbiased merit is **2.583111**, which
is only +0.032 % above the merged frontier's 2.582286. This reverses the state
doc's framing that "restoration makes the record ≈1-in-31".

### 5.2 P(record) per draw

σ_pred = σ_cs = 0.18336 % for a known merit; semi-empirical column convolves
the empirical `ln L` distribution with σ_pred and brackets it with the σ_cs
interval.

| basis | `cs` | needs `ln L` | empirical k/1218 (Wilson) | **P/draw** [σ_lo, σ_hi] | E[draws] | hours @ 0.9/h |
|---|---|---|---|---|---|---|
| observed max (order stat, n=5) | 2.590559 | +0.9965 % | 3.202 % [2.351, 4.347] | **4.401 %** [3.831, 6.326] | 22.7 | **25.2** |
| **unbiased merit of that tree** | **2.583111** | **+1.2844 %** | 0.985 % [0.564, 1.714] | **1.186 %** [0.974, 2.227] | **84.3** | **93.7** |
| merged frontier `bd33883e` | 2.582286 | +1.3164 % | 0.739 % [0.389, 1.398] | 1.028 % [0.850, 1.962] | 97.3 | 108.1 |
| unbiased +0.10 % | 2.585696 | +1.1844 % | 1.314 % | 1.879 % | 53.2 | 59.1 |
| unbiased +0.25 % | 2.589577 | +1.0344 % | 2.709 % | 3.734 % | 26.8 | 29.8 |
| unbiased +0.50 % | 2.596059 | +0.7844 % | 8.703 % | 9.853 % | 10.1 | 11.3 |
| unbiased +1.00 % | 2.609072 | +0.2844 % | 32.594 % | 31.816 % | 3.1 | 3.5 |

Cumulative P(record) from the unbiased-merit row: 4 draws 4.66 %, 10 draws
11.25 %, 20 draws 21.23 %, 40 draws 37.95 %, 82 draws 62.41 %. From the
observed-max row: 4 draws 16.48 %, 10 draws 36.25 %, 20 draws 59.35 %, 40 draws
83.48 %, 82 draws 97.51 %.

**Rule 93.3's ≈3.2 %/draw, E ≈ 31 draws ≈ 34 h is the observed-max row and is
therefore an upper bound, exactly as Rule 93.3 itself flagged. The honest
central figure is the unbiased row: ≈1.19 %/draw, E ≈ 84 draws ≈ 94 h ≈ 3.9
days of our whole channel share.** Rule 93.3 should be superseded by this table.

*Convention note.* `stage-c.json` also carries an "inflated" column with
σ_pred = σ_cs·√(1+1/n_obs), which prices merit-estimation error. It is
**non-monotone** — the frontier row has n_obs = 1, so its predictive sd is √2
larger and its P *exceeds* the unbiased n=5 row (1.456 % vs 1.279 %). That is a
convention artifact, not a finding: a tree we know less about has a wider
predictive distribution and so a fatter upper tail. Lead with the known-merit
column; use the inflated one only when literally choosing between trees of
different receipt counts.

---

## 6. The exchange rate Y

`stage-c.json` → `C4_exchange_rate`. Basis: unbiased merit 2.583111, n=5,
σ_pred = σ_cs·√1.2, `p_without = 1.2788 %`.

**Y = the merit gain that buys the same cumulative P(record) as one extra draw
at a given budget k.**

| budget k | **Y (% of `cs`)** | **Y (µs/step of decode)** | cum P: k → k+1 |
|---|---|---|---|
| 4 | 0.04874 % | **3.201 µs** | 5.018 % → 6.232 % |
| 10 | **0.02090 %** | **1.372 µs** | 12.076 % → 13.201 % |
| 20 | **0.01072 %** | **0.704 µs** | 22.694 % → 23.683 % |
| 40 | 0.00543 % | 0.357 µs | 40.239 % → 41.003 % |
| 80 | 0.00273 % | 0.179 µs | 64.286 % → 64.742 % |

Y falls with k because cumulative P saturates. **Quote Y at k = 10 (≈11 hours of
our channel): one draw ≈ 1.37 µs/step.**

### 6.1 The scale-free version: a merit gain multiplies your draws

The budget-dependence of Y is awkward for policy, so here is the identity that
removes it. For per-draw probabilities p₀ < p₁,

```
cum(p1, k) = cum(p0, k * r)   exactly, with   r = ln(1 - p1) / ln(1 - p0)
```

so **a permanent merit gain multiplies your effective draw count by a constant
`r` at every budget**, and `(r − 1)·k` is the extra-draw statement at budget k.

| mechanism | merit gain | **r (draws multiplier)** | extra draws @ k=20 | extra hours @ 0.9/h |
|---|---|---|---|---|
| +0.10 % of `cs` | 6.6 µs/step | **1.584×** | 11.7 | 13.0 |
| +0.25 % of `cs` | 16.4 µs/step | 3.117× | 42.3 | 47.0 |
| +0.50 % of `cs` | 32.8 µs/step | 8.246× | 144.9 | 161.0 |
| **Rule 91's whole 19.0 µs/step residual** | 0.3204 % | **4.198×** | 64.0 | 71.1 |
| **Rule 92's barrier/encoder ceiling 1.30 µs/step** | 0.0198 % | **1.094×** | 1.9 | 2.1 |

Reconciliation with Stage B's `B5_inverse`, which answered the inverse question
at a *fixed* budget ("Rule 91's 19.0 µs/step = 15.39 draws; Rule 92's 1.30 µs =
1.73 draws"): the two definitions differ only in what is held fixed. `B5_inverse`
holds cumulative P fixed and reports the draw count that matches it there;
`r` holds nothing fixed and reports the multiplier. They agree at k ≈ 20
(15.4 vs 64.0 differ because `B5_inverse` was evaluated on the marginal
per-budget Y at the observed-max basis, whereas `r` is on the unbiased basis and
is not marginal). **Prefer `r`.** It is basis-explicit, scale-free, and does not
silently depend on a budget nobody has committed to.

**The headline number for the advisor:** Rule 92 closed the barrier/encoder axis
at a 1.30 µs/step ceiling. That ceiling is worth **1.09× draws, i.e. under two
extra draws at any realistic budget, i.e. about two hours of channel**. Rule
91's whole disputed 19 µs/step residual — which #616 Stage 0 already returned
N-0 on, both intervals covering zero — would be worth **4.2× draws** if it
existed. Nothing else in the current mechanism inventory is in that class.

### 6.2 Pricing the stock of findable merit (base `3241e5e5`, Rule 94)

The base advance to `3241e5e5` asks for one number: now that #617 and #619 have
closed their axes and Rule 94.1 has opened the prefill gap, which way does the
model come out? Same `r` scale, same basis, same estimator.

| item | merit gain | **r (draws multiplier)** | extra draws @ k=20 | extra hours @ 0.9/h |
|---|---|---|---|---|
| #617 barrier/encoder ceiling | 0.0198 % = 1.30 µs/step | 1.094× | 1.9 | 2.1 |
| **#619 redundant-read + fusion ceiling** | **0.231 % = 15.2 µs/step** | **2.868×** | **37.4** | **41.5** |
| both, if fully captured | 0.2508 % = 16.5 µs/step | 3.128× | 42.6 | 47.3 |
| **Rule 94.1 prefill gap** | **9.3 % of score** | **unbounded** | — | — |

Three readings, and the first one is a correction to the framing of `Y` itself.

1. **"Closed" and "worthless" are different statements, and #619 separates
   them.** Its combined ceiling is 2.19× under the single-receipt acceptance
   bar — correctly closed *as a provable submission* — yet on the lottery scale
   the same 0.231 % is worth **2.87× draws, i.e. 37 extra draws at a 20-draw
   budget, i.e. ≈41 hours of our 0.9/h channel**. The two verdicts disagree
   because the gate asks whether one receipt can demonstrate the gain against
   σ = 0.537 %, while the lottery asks whether the gain shifts the whole draw
   distribution permanently. **A mechanism can be unprovable in a single draw
   and still be the best available use of a round.** Any future closure argued
   purely from "ceiling < 3σ" is answering the gate question, not the allocation
   question, and should be re-read against this column.
2. **Rule 94.1 is off the scale.** At +9.3 % of score the bar moves below the
   *minimum* of all 1218 observed lottery draws, so `p_with` = 1 to float
   precision and `r` is unbounded: one draw would be a certainty. No draw budget
   competes with it. Its interval is very wide and its reachability is
   undemonstrated, so treat it exactly as the advisor framed it — the honest
   upper end of the stock of findable merit, an explicit parameter and not a
   plan.
3. **So the model does not come out "spam the channel."** The ordering is
   prefill gap ≫ #619's 0.231 % (≈ one round of channel) ≫ #617's 0.0198 %
   (≈ two hours). Under-drawing is real and §12 says so, but it is the *second*
   finding: at our rate, one more draw is worth 0.021 % of `cs`, and there are
   still two items on the board worth 11× and ≫100× that. The desk-first bias
   survives this analysis — what does not survive is pricing desk work in
   ceilings instead of draws, and ranking anything on `officialScore`.

---

## 7. The prefill coin — the largest uncontrolled term

`stage-a.json` → A9, `stage-c.json` → `C5_prefill_coin`.

`ln bl_pre` is **strongly bimodal**, and the mode assignment is a coin flipped
per submission by the harness, not by us:

| mode | n | mean `ln bl_pre` | mean `ln L` | `sd(ln L)` | winners vs 2.590559 | winners vs 2.583111 |
|---|---|---|---|---|---|---|
| **high** | 542 (0.44499) | **+1.9297 %** | **+0.50236 %** | 0.33774 % | **39/542 = 7.196 %** [5.308, 9.686] | **12/542 = 2.214 %** [1.271, 3.830] |
| **low** | 676 | **−1.6189 %** | **−0.42362 %** | 0.21332 % | **0/676** | **0/676** (Wilson upper 0.565 %) |

Separation between modes **3.5486 %** of `ln bl_pre`, antimode at −0.03507 %,
between-mode share of variance 0.8388, widest central gap 0.0777 %.
**Coin value = 0.25 × 3.5486 = 0.92598 % of score = 60.81 µs/step of
decode-equivalent** — i.e. **one coin flip is worth more than three times Rule
91's entire disputed residual, and 47× Rule 92's ceiling.**

Three facts to state plainly:

1. **The high mode is a necessary condition.** Every one of the 39 draws that
   ever cleared 2.590559's bar, and all 12 that cleared the unbiased 2.583111
   bar, was a high-mode draw. **P(record | low mode) = 0/676**, Wilson upper
   bound 0.565 %. A low-mode draw is, for practical purposes, a
   disqualification.
2. **We do not control it and it is not us.** Within a fixed identical tree,
   β(`ln pre` on `ln bl_pre`) = **−0.02008 [−0.07880, +0.03864]** (dof 9): the
   candidate's prefill does *not* co-move with the baseline's. Within-group
   `sd(ln bl_pre)` = 2.0254 % ≈ the corpus 1.926 %. High-mode fraction is flat
   across solvers (§4.4). So **V-COMMON resolves to β ≈ 0 on the prefill axis**:
   the pairing does not cancel this noise, merit and lottery add in quadrature
   (consistent with Rule 93.2's `corr(ln cs, f) = −0.126 [−0.332, +0.091]`), and
   **campaign z-scores computed as if the pairing helped are optimistic**.
3. **Its mix moves slowly.** High-mode fraction by day: ≈0.32 (Jul 24–25) →
   0.50–0.57 (Aug 2–8) → 0.219 (Aug 9), 0.273 (Aug 10). Last 7 days
   215/427 = 0.504 with 22/427 = 5.15 % [3.43, 7.68] winners; last 3 days
   40/101 = 0.396 with 5/101 = 4.95 % [2.13, 11.07].

I also report, without proposing a mechanism, that `ln bl_pre` regresses on the
receipt's `peak_ram` with β = **+3.4318 %/GB [−0.3446, +7.2083]** — suggestive,
not significant, and on the *baseline's* prefill, which our candidate cannot
touch.

**This is the highest-value open question in the channel, and it is out of
scope for this round.** Per my stopping rule I state the observation and stop.
The one policy consequence that follows without any mechanism is in §12: the
last two days ran cold on the coin (0.219, 0.273 vs a 0.445 base rate), so a
draw taken today is worth materially less than the tables above imply, and a
losing streak of the current length is fully consistent with the coin rather
than with anything wrong in our trees.

---

## 8. The tree-selection rule

`stage-c.json` → `C7_tree_selection`. Basis: a *fresh* tree known from one
receipt, σ_pred = σ_cs·√2 = 0.2593 %; `p_best = 1.6723 %` at deficit 0.
"Ticket-value ratio" = P(record | this tree) / P(record | best tree).

| merit deficit vs best tree | µs/step | P/draw | **ticket-value ratio** | n per arm to resolve the deficit |
|---|---|---|---|---|
| 0.00 % | 0.0 | 1.6723 % | 1.0000 | ∞ |
| 0.02 % | 1.3 | 1.5335 % | 0.9164 | 646 |
| 0.05 % | 3.3 | 1.3463 % | 0.8038 | 103 |
| **0.10 %** | **6.6** | 1.0839 % | **0.6462** | **26** |
| 0.20 % | 13.1 | 0.7069 % | 0.4207 | 6 |
| 0.50 % | 32.8 | 0.2186 % | 0.1298 | 1 |
| 1.00 % | 65.7 | 0.0245 % | 0.0146 | 0 |

Corroborated independently by Stage B's B6, which computed the same ratios from
the empirical `ln L` distribution: 0.8006 / 0.6459 / 0.4311 / 0.1498 at −0.05 /
−0.10 / −0.20 / −0.50 % (and n-per-arm 211 / 53 / 13 / 2 by that route).

**The rule:**

> **Draw from the single highest-merit buildable tree. A second tree earns a
> draw only when its merit deficit is inside the resolution floor of σ_cs — and
> σ_cs is 0.183 % of `cs`, so any deficit we can actually measure with a handful
> of receipts already costs more ticket value than diversification buys.**

Note the trap this rule closes: it takes ~26 receipts per arm to *establish* a
0.10 % deficit, but a 0.10 % deficit already costs 35 % of ticket value. The
regime where diversification is defensible is exactly the regime where we cannot
tell the trees apart, and there diversification buys nothing. **This confirms
the standing advisor rule (Rule 93.4) — submit from the highest-merit tree, not
the merged frontier, and build A/B arms on top of the best-merit tree so each
arm is a live ticket — and now supplies its quantitative justification.** With
one caveat from §5.1: "highest-merit tree" must mean *highest unbiased merit*,
not highest observed `cs`, or the rule silently selects on noise.

---

## 9. Stage D — verifying Rule 93.4, adjudicating its key, and decomposing onto the axes

Advisor comments 7 and 8 asked for three specific things: *verify, don't adopt*
Rule 93.4(a); test homogeneity and robustness; and **decompose onto the two
score axes rather than the composite**, then reconstruct σ and report the
residual. Comment 8 also asked that every `R106E-DRAW-*` receipt be excluded
from the σ fit and that the exclusion be stated. All of that is `stage-d.json`
(schema `maple-nezuko-r106h-stage-d/1`).

### 9.1 The `R106E-DRAW-*` exclusion (D1)

**Stated plainly: no `R106E-DRAW-*` receipt is in any σ fit in this report, and
the exclusion is by construction, not by filtering.** Scanning all 1787 corpus
records for the note substring `R106E-DRAW` returns **0 matches**, and no
receipt lies within `1e-5` of draw-01's `cs` 2.574073. The corpus was frozen
2026-08-10T08:37Z, which predates those receipts. So no σ in §4–§8 can have been
inflated by the draw ladder. The tree-identity point stands independently:
draw-01 is z = −3.09 from `4b0e051b` but z = −0.51 from `origin/main`, an LR of
about 105:1 that the wrong tree was archived — but that is a provenance finding,
not a variance one, and it does not touch this fit.

### 9.2 Rule 93.4(a) verified to four significant figures (D2)

All 12 `cs` values quoted in Rule 93.4(a) were matched in the frozen corpus to
|abs err| ≤ 4.8e-7 (they are quoted to six decimals, so this is exact
agreement). Recomputing the pooled within-family sd from the corpus values:

| family (note-declared key) | n | corpus sd(`cs`) | matched sha12s |
|---|---|---|---|
| nezuko calibration A/B/C, 2026-08-04 | 3 | 0.07651 % | `745ea5e7031b`, `c99c2518ba24`, `df676dbb5adb` |
| nezuko corpus-harvest `5d522d6a` A/B/C | 3 | 0.17982 % | `9845a4add6bd`, `cc0d2399e2c5`, `57e16bbb324a` |
| tanjiro r105-A A0 | 3 | 0.18217 % | `51b6c142ea76`, `fdeb45614ce2`, `24ad1d2eaf23` |
| tanjiro r105-A A1 | 2 | 0.07169 % | `2d967a120e60`, `5e435a6b6936` |
| **pooled** | **11 / dof 7** | **0.145353 %**, CI [0.09610, 0.29583] | SS = 1.4789e-5 |

**Rule 93.4's 0.1453 % reproduces.** Verified, not adopted.

### 9.3 The note key over-groups: byte-key adjudication (D3)

Rule 93.4 replaced Rule 89.1's defective key (`submissionCommitSha`, always
distinct by construction) with a *note-declared* key. That is a real
improvement, but it is a claim by the submitter, not a measurement. D3 checks it
against a **byte key**: a comment-insensitive sha256 over every file under
`Sources/` **and** `Vendor/`, with every ci-equal pair line-checked so the only
surviving differences are whole-line `//` comments outside multiline string
literals. The two keys **disagree on two of the four families**:

- **nezuko calibration A/B/C** — member `745ea5e7031b` (`cs` 2.489564) is in *no*
  byte-identical group; the other two sit in digest group
  `r103:9beb75a6fbc5e042`. The note key over-groups by one member. Corrected,
  the family is n = 2 with sd 0.08706 %.
- **nezuko corpus-harvest `5d522d6a` A/B/C** — all three land in digest group
  `r103:521a2f7124786af6`, **which fails verification**: real non-comment diffs
  in `Vendor/…/fp_quantized.cpp`. That family is not an identical-tree replicate
  set at all.
- **tanjiro r105-A A0 and A1** are byte-verified clean, with zero members
  outside their digest group.

Both families that fail are *mine*, which is the uncomfortable part: my own
2026-08-04/08-05 note discipline was worse than tanjiro's.

The number, however, barely moves:

| pool | n | dof | sd(`cs`) | 95 % CI |
|---|---|---|---|---|
| advisor's four families, note key (D2) | 11 | 7 | 0.145353 % | [0.09610, 0.29583] |
| advisor's families, byte-corrected members | 10 | 6 | 0.15479 % | [0.09975, 0.34086] |
| byte-verified 5-group pool (this report's σ_cs) | 15 | 10 | **0.18336 %** | [0.12812, 0.32178] |
| byte-verified 7-group member pool | 20 | 13 | 0.19050 % | [0.13810, 0.30754] |

F-tests: note key vs byte-verified group pool **F = 1.5913, df (10,7), p =
0.552**; note key vs member pool **F = 1.7176, df (13,7), p = 0.482**. So the
corrected key **matters for provenance and not for the number** — the two keys
give statistically indistinguishable σ, and Rule 93.4's 0.1453 % and this
report's 0.1834 % are the same estimate seen through different dof.

### 9.4 Homogeneity holds; the A0 triple is not an outlier (D4, D5)

The advisor asked specifically whether the four families are homogeneous, whether
robust and classical σ agree, and whether A0's third member (2.574592) is
inflating the pool.

- **Bartlett** on the four advisor families: **K² = 1.764, df 3, p = 0.623**. On
  the five byte-verified groups: **K² = 1.792, df 4, p = 0.774**. Homogeneity is
  not rejected either way, so pooling is legitimate.
- **Eras.** 2026-08-04..05 pools to 0.08706 % (dof 1, CI [0.0388, 2.778]);
  2026-08-09..10 pools to **0.19109 %** (dof 9, CI [0.13144, 0.34885]). Variance
  ratio **F = 4.818, df (9,1), p = 0.681** — cannot reject, but with dof 1 in the
  early era there is no power, so "σ is era-stable" is *not* established, only
  *not contradicted*. Mean `cs` by era 2.487607 → 2.579803, i.e. the eras differ
  in merit by 3.7 %, which is why the note key's cross-era pooling was worth
  checking at all.
- **Robust vs classical.** Classical pooled 0.18336 % vs robust (MAD-sd of the 15
  group-centred deviations) **0.13798 %**. The ratio 0.75 is within what a
  15-point Gaussian sample gives, and the decisive check is the studentised
  deviations: **max |z| = 1.589 over 15 deviations ⇒ no outlier**. A0's third
  member is *not* inflating anything. Leave-one-receipt-out sweeps the pool over
  **[0.15990, 0.19263] %** — no single receipt drives it. The largest group
  contributes 0.6166 of the pooled SS, which is exactly its dof share (n = 5 of
  10 dof), not a pathology.

Per-group MAD-sd for the record: 0.10548 / 0.16589 / 0.07516 / 0.09127 /
0.29709 %.

### 9.5 The two-axis reconstruction, and the substantive answer (D6)

Comment 8's method: carry σ_decode and σ_prefill separately, then *reconstruct*
σ. With `cs = (M_D/dec)^0.75 (M_P/pre)^0.25`, the axis contributions in log space
are `0.75·ln(M_D/dec)` and `0.25·ln(M_P/pre)`, so
`σ² = σ_D² + σ_P² + 2·ρ·σ_D·σ_P`.

**Session-lottery axis** (`ln L`, n = 1218, dof 1217):

| term | value |
|---|---|
| sd(`ln bl_dec`) | 0.24573 % |
| sd(`ln bl_pre`) | 1.92606 % |
| corr | +0.12432 |
| σ_decode-axis (0.75×) | 0.18429 % |
| σ_prefill-axis (0.25×) | **0.48151 %** |
| cross term | +0.022065 %² |
| **reconstructed σ_f** | **0.53655 %** |
| direct σ_f | 0.53655 % (rel residual 4.1e-16) |

**Candidate-noise axis** (group-centred byte-verified receipts, n = 15, dof 10):

| term | value |
|---|---|
| sd(`ln dec`) | 0.24145 % |
| sd(`ln pre`) | 0.16289 % |
| corr | −0.05630 |
| σ_decode-axis | **0.18109 %** |
| σ_prefill-axis | 0.04072 % |
| cross term | −0.000830 %² |
| **reconstructed σ_cs** | **0.183359 %** |
| direct σ_cs | 0.183359 % (rel residual 3.7e-14) |

The residuals are at floating-point level because on the *same sample* the
reconstruction is an algebraic identity — it cannot disagree with itself, and
the JSON says so explicitly rather than presenting 4e-16 as a validation. The
real content is the **composition**, and it is the opposite in the two channels:

> **The session lottery is prefill-dominated — the prefill axis is
> (0.48151/0.53655)² ≈ 80.5 % of its variance. Candidate noise is
> decode-dominated — the decode axis is (0.18109/0.183359)² ≈ 97.5 % of its
> variance.**

That is the substantive answer to comment 8, and it is why §7's prefill coin is
the largest uncontrolled term while every mechanism we can build lives on the
decode axis. It also explains the whole §4.3 puzzle in one line: the two σ are
not two measurements of one thing.

Two diagnostics worth keeping:

- **Divisor bias.** Scoring the same 15-receipt sample at `n−1 = 14` instead of
  `n−k = 10` gives 0.15497 %, a **−15.5 % bias**. Any pooled replicate σ quoted
  without its dof is low by roughly this much.
- **Independent cross-check.** Using #597's per-axis σ (sd `ln dec` 0.1839 %, sd
  `ln pre` 0.1123 %) instead of ours reconstructs σ_cs = **0.14075 %** at ρ = 0
  and **0.13920 %** at this report's within-group ρ — about 23 % below our direct
  0.18336 %. With a 22.4 % relative SE on an sd at dof 10, **that is agreement**,
  and it is the only part of D6 that is a genuine test rather than an identity.

### 9.6 Our own launch σ is *lower*, which makes drawing *worse* (D7)

Rule 93.4(3) split pooled sd(`f`) into maple-attributed 0.4778 % (n = 44) and
residual 0.5868 % (n = 41) and expected the F to come out non-significant. On
this corpus, partitioning `ln L` by launch account:

| partition | n | dof | sd(`ln L`) | 95 % CI | rel SE |
|---|---|---|---|---|---|
| maple | 31 | 30 | **0.44457 %** | [0.35525, 0.59446] | 12.9 % |
| unattributed | 41 | 40 | **0.60835 %** | [0.49945, 0.77855] | 11.2 % |
| birch | 4 | 3 | 0.39160 % | [0.22184, 1.46011] | 40.8 % |
| cedar | 4 | 3 | 0.16141 % | [0.09144, 0.60183] | 40.8 % |
| birch+maple | 2 | 1 | 0.27750 % | — | 70.7 % |

**maple vs unattributed: F = 1.8726, df (40,30), p = 0.0773.** Not significant
at 0.05, so Rule 93.4(3)'s expectation survives — but it is suggestive, and the
*direction* replicates the advisor's split (0.4778 < 0.5868) with our estimate
even lower.

I have to state the consequence in the honest direction, because it goes against
my own interest in this argument. If **our** launch σ is 0.4446 % rather than the
cohort's 0.5365 %, then σ_tot = √(0.1453² + 0.4446²) = **0.4678 %**, and the
0.9967 % gap becomes z = **2.131**, i.e. P ≈ **1.65 %/draw**, E ≈ 60.5 draws ≈
**67 hours** at our 0.9 receipts/h share. That is better than §5.2's central
1.19 % but **worse than the advisor's 3.6 %**, and it is worse for exactly the
reason that flatters us: a tighter launch distribution is a *worse* lottery when
you are behind. A narrower σ_f cuts both ways and here we are on the losing
side of it. The empirical/nonparametric numbers in §5.2 remain the ones to quote
— the Gaussian tail is the least trustworthy part of any of these estimates
(§13's known limits quantify how much fatter the `ln L` upper tail is) — but the Gaussian
sensitivity is reported here rather than dropped because it moves the answer in
the unflattering direction.

---

## 10. Stage E — adjudicating Rule 96 ("the lottery is dead")

Rule 96 landed on the advisor branch (`446fe987`, 2026-08-10T10:40Z) after this
report's Stages A–D were written, and it contradicts §5.2's headline by two
orders of magnitude. It is not yet in my base (`d5f416c7`) and no PR comment
retasked me, but a report whose central number is contested by a live rule is
worthless, so Stage E adjudicates it against the same frozen corpus.
`research/nezuko_r106h_stage_e.py` → `stage-e.json`.

The short version: **Rule 96 is right about the anchor and wrong about the
denominator, and its ruling survives anyway — for a different reason than the
one it gives.**

| Rule 96 claim | Stage E verdict |
|---|---|
| 96.1(2) `4b0e051b`'s 2.590559 is the max of five draws; selection bias +0.2881 %; the honest anchor is **cs ≈ 2.583106** | **confirmed independently** — my byte-digest key finds the same family, max 2.590559, geo-mean **2.583106**, bias **+0.2881 %**; anchors agree to **−0.00001 %** (§10.1) |
| 96.1(4) per-leg within-tree sd: cand decode 0.2938 %, cand prefill 0.1027 %, baseline decode 0.1471 %, baseline prefill 2.1725 %; F(4,4) = 447.5 | **confirmed to four decimals**; my F = **447.9**, p = 1.49e-5 (§10.3) |
| 96.2 the record holder's true tree deconvolves below ours; our lead is **0.330 %** | **confirmed exactly** — their tree is cs **2.574594**, ours 2.583106, ln-ratio **0.3300 %** (§10.6) |
| 96.2 model-free: 27 receipts at cs ≥ anchor, **0 records**, needed f median 1.134 % | **reproduced** — n = **26**, **0 records**, needed f median **+1.1349 %**; cohort sd(f) **0.3398 % [0.2665, 0.4693]**, which *does* exclude the corpus 0.5365 % (§10.5) |
| 96.1(3) the decision denominator is **sd(ln score \| fixed tree) = 0.3728 %**, from ρ(ln cs, f) = −0.7920 | **rejected as a pooled quantity** — 0.3728 % is one group at **dof 4** (rel SE 35 %); pooled over all five byte-verified groups it is **0.5055 % [0.3532, 0.8872]**, and pooled sd(f) is **0.5411 % [0.3781, 0.9496]**, whose CI **excludes** 0.3728 %. The ρ that produces it is **not significant** (t = −2.25, dof 3, p ≈ 0.11), the pooled ρ is **−0.357 [−0.788, +0.309]** covering zero, and the 1218-receipt corpus ρ is **+0.1165 [+0.0608, +0.1716]** — the *opposite sign* (§10.2) |
| 96.2 P(record)/draw = **0.0285 %**, E = **3,510 draws** | **arithmetic reproduced exactly** (I get 0.0285 %, 3,514 draws at σ = 0.3728 %) **but the σ is wrong**. Model-free from the same anchor: **0.985 %/draw [0.56, 1.71], E ≈ 102 draws ≈ 113 h**; **2.214 %/draw, E ≈ 45 draws ≈ 50 h** if the draw lands in the high prefill mode. Rule 96 is **~35× too pessimistic** (§10.7) |
| 96.2 "a paired official A/B resolves 0.228 % of cs ≈ 15 µs/step" | **understated by √2** — a 1-vs-1 paired *difference* has sd σ√2, so the 1σ resolution is **0.2593 % of cs = 17.0 µs/step**, and a 3σ decision needs **0.7779 % of cs = 51.1 µs/step** from a single pair (§10.8) |
| 96.2 ruling: "no draw is authorised on a tree we know is ~1.28 % short; engineer first, draw once" | **endorsed, on §6.2's exchange rate rather than on 3,510 draws** (§10.7) |

### 10.1 The anchor shrinkage is real, and independently keyed (E1)

This is the most important thing in Stage E, because it is the one place where
two disjoint methods agree. Frieren's key is the note text declared at
submission time. Mine (§9.3) is a SHA-256 digest of the submitted editable
surface, reconstructed from git. They are computed from different data and they
land on the same five receipts:

| group (byte-digest key) | n | max `cs` | geo-mean `cs` | winner's-curse bias |
|---|---|---|---|---|
| **`r103:dc437b0e0b918c86`** | **5** | **2.590559** | **2.583106** | **+0.2881 %** |
| `fresh:r104A/armA` | 3 | 2.582514 | 2.577933 | +0.1775 % |
| `fresh:r105A/A0` | 3 | 2.583779 | 2.579751 | +0.1560 % |
| `fresh:r105A/A1` | 2 | 2.575716 | 2.574410 | +0.0507 % |
| `r103:9beb75a6fbc5e042` | 2 | 2.489138 | 2.487606 | +0.0616 % |

Rule 96.1(2) quotes 2.583106 and +0.2881 %. I get 2.5831058 and +0.28806 %.
The disagreement is 1e-7 in `cs`, i.e. floating-point noise. **Our best tree is
worth cs ≈ 2.583106, not 2.590559, and the gap to the record is 1.2846 %, not
0.9965 %.** §5.1 said the same thing from the other key; Stage E promotes it
from "my finding" to "a fact two independent keys agree on".

Note what this does *not* say. It does not say `4b0e051b` was lucky in a way we
can undo — the five members are byte-identical trees, so 2.590559 is a real
measurement of a real submission. It says that if we resubmit that tree, the
expected `cs` is 2.583106, and planning against 2.590559 is planning against an
order statistic.

### 10.2 The decision denominator: Rule 96 quotes a dof-4 number as if it were σ (E2)

Rule 96.1(3) replaces σ_tot = 0.5546 % with sd(ln officialScore | fixed tree) =
0.3728 %, and that single substitution is what turns 3.6 %/draw into 0.0285 %.
The substitution has the right *shape* — you should price a decision with the
noise of the decision, not with the marginal spread of the corpus — but the
number is one group's:

| group | n | sd(ln `cs`) | sd(`f`) | sd(ln score) | ρ(ln `cs`, `f`) |
|---|---|---|---|---|---|
| `fresh:r104A/armA` | 3 | 0.1578 % | 0.6185 % | 0.6833 % | +0.305 |
| `fresh:r105A/A0` | 3 | 0.1822 % | 0.2133 % | 0.0403 % | −0.992 |
| `fresh:r105A/A1` | 2 | 0.0717 % | 0.9400 % | 1.0117 % | — |
| `r103:9beb75a6fbc5e042` | 2 | 0.0871 % | 0.2840 % | 0.1969 % | — |
| **`r103:dc437b0e0b918c86`** | **5** | **0.2276 %** | **0.5263 %** | **0.3728 %** | **−0.792** |
| **pooled** | **15** | **0.1834 % [0.1281, 0.3218]** | **0.5411 % [0.3781, 0.9496]** | **0.5055 % [0.3532, 0.8872]** | **−0.357 [−0.788, +0.309]** |

Three things follow, and the advisor's own standard from comment 4 ("report the
SE of every σ") is what makes them visible.

1. **0.3728 % carries a 35 % relative SE.** It is an sd at dof 4:
   `1/sqrt(2·4)` = 35.4 %. Its own χ² interval is **[0.2234, 1.0714] %**. Quoting
   it to four significant figures and then exponentiating a Gaussian tail at
   z = 3.446 gives a number with no meaningful precision — moving σ to its own
   upper bound moves E[draws] from 3,514 to about 9.
2. **The pooled dof-10 estimate excludes it.** sd(`f` | tree) = 0.5411 %
   [0.3781, 0.9496]. 0.3728 % is below the lower bound. The five-member group is
   the *quietest* of the five on the score axis except A0's n=3, and pooling is
   the estimator the advisor asked for in comment 7.
3. **The ρ that does the work is not significant, and the corpus says it has the
   wrong sign.** ρ = −0.7920 on n = 5 is t = −2.247 on dof 3, p ≈ 0.11, Fisher CI
   **[−0.986, +0.300]**. Pooled over dof 10 it is −0.357 [−0.788, +0.309]. And on
   all 1218 receipts, ρ(ln `cs`, `f`) = **+0.1165 [+0.0608, +0.1716]** — small,
   but significantly *positive*. A −0.79 pass-through means a good tree
   systematically draws a bad session, which would be a remarkable property of
   the harness; the 1218-receipt estimate says the opposite, weakly.

The honest statement of the denominator is therefore: **sd(`f` | fixed tree) =
0.5411 % [0.3781, 0.9496] at dof 10, statistically indistinguishable from the
marginal corpus σ_f = 0.5365 %** (F = 1.017). **Conditioning on the tree buys
essentially nothing.** §10.4 shows what *does* buy something.

### 10.3 Rule 96.1(4)'s per-leg table is exactly right (E3)

| leg | Rule 96 (n=5) | mine (n=5) | mine (pooled, dof 10) |
|---|---|---|---|
| candidate decode | 0.2938 % | **0.2938 %** | 0.2414 % [0.1687, 0.4237] |
| candidate prefill | 0.1027 % | **0.1027 %** | 0.1629 % [0.1138, 0.2859] |
| baseline decode | 0.1471 % | **0.1471 %** | 0.2052 % [0.1434, 0.3602] |
| baseline prefill | 2.1725 % | **2.1725 %** | 2.0254 % [1.4152, 3.5544] |
| F(bl prefill / cand prefill) | 447.5, p = 1.5e-5 | **447.9, p = 1.49e-5** | — |

Four-decimal agreement on all four legs. The pooled column shows the n=5 values
are within sampling noise of the dof-10 ones for three legs, and that baseline
prefill is enormous on either estimate. Rule 96 is entitled to its conclusion
that baseline prefill alone carries ~96 % of var(`f`) — §4.1 got 80.5 % on the
marginal corpus and the difference is which cohort you condition on, not a
disagreement about the mechanism.

### 10.4 That 2.1725 % is not a σ — it is my A9 coin (E4)

Neither Rule 95 nor Rule 96 contains a bimodality or mixture claim about
baseline prefill (checked directly against `CURRENT_RESEARCH_STATE.md`
L4732–5166). §7 found that `100·ln(bl_pre/MB_P)` is **bimodal** with an antimode
at −0.035 %, a low mode (n = 676, mean −1.619 %) and a high mode (n = 542, mean
+1.930 %) separated by **3.549 %**, carrying 83.9 % of the variance between
modes. Stage E asks whether the five byte-verified trees straddle it:

| group | n | high | low | sd(bl prefill) | straddles? |
|---|---|---|---|---|---|
| `fresh:r104A/armA` | 3 | 2 | 1 | 2.0370 % | **yes** |
| `fresh:r105A/A0` | 3 | 0 | 3 | 0.3296 % | no |
| `fresh:r105A/A1` | 2 | 1 | 1 | 3.2863 % | **yes** |
| `r103:9beb75a6fbc5e042` | 2 | 2 | 0 | 1.6816 % | no |
| **`r103:dc437b0e0b918c86`** | **5** | **1** | **4** | **2.1725 %** | **yes** |

**Three of the five straddle, including the five-member group that Rule 96's
denominator comes from.** Conditioning on the mode as well as the tree:

| quantity | conditioned on tree | conditioned on tree **and mode** | share from the coin |
|---|---|---|---|
| sd(baseline prefill) | 2.0254 % (dof 10) | **0.6828 %** (dof 7) | **88.6 %** |
| sd(`f`) | 0.5411 % (dof 10) | **0.1651 %** (dof 7) | **90.7 %** |

This is the substantive correction to *both* Rule 96 and my own §5.2. **The
session lottery is not a Gaussian at all.** It is a Bernoulli coin — p(high) =
0.445 [0.417, 0.473], payout 0.887 % of score (§7) — plus about **0.17 %** of
continuous noise. Every Gaussian σ in this debate, mine at 0.54 % and Rule 96's
at 0.3728 %, is a moment-matched approximation to a two-point mixture, and a
Gaussian moment-matched to a mixture misprices exactly the tail both of us are
trying to price.

The mixture also makes the tail arithmetic transparent, which no Gaussian does.
To clear +1.2846 % you need the coin *and* a good continuous draw:
conditional on the high mode the residual requirement is about +0.40 % against
σ = 0.1651 %, and conditional on the low mode it is +1.28 % against the same
σ = 0.1651 %, i.e. z = 7.8 — **unreachable**. That is the E7 row reading
`gauss_within_mode_sd_f` p = 3.6e-15: not a real estimate, but the proof that
**the coin is not optional. There is no record without a high-mode baseline
prefill.** §7's 39/39 and §10.6's **12/12** are the empirical form of the same
statement.

### 10.5 The top-`cs` cohort: Rule 96's strongest evidence, correctly sized (E5)

Rule 96.2's model-free confirmation is the part of it that does not depend on a
σ, and it mostly reproduces:

| | Rule 96 | Stage E (our anchor 2.5831058) |
|---|---|---|
| receipts with cs ≥ anchor | 27 | **26** (6 ours, 6 distinct users) |
| records among them | 0 | **0** |
| needed `f`, min / median / max | 0.946 / 1.134 / 1.279 % | **0.9460 / 1.1349 / 1.2792 %** |
| observed max `f` | +0.612 % | **+0.3579 %** |
| observed mean `f` | −0.179 % | **−0.2095 %** |
| observed sd(`f`) | 0.369 % | **0.3398 % [0.2665, 0.4693]**, madSD 0.4387 % |

The needed-`f` triple matches to four decimals, which says we are looking at the
same cohort. The count and the observed max differ slightly (n 26 vs 27, max
+0.358 vs +0.612 %), most likely a freeze-time difference — my corpus is frozen
at 08:37Z and Rule 96 is written at 10:40Z, and `R106E-DRAW-*` receipts landed in
between (§9.1). I cannot check that without unfreezing, so I record it as an
unresolved 1-receipt discrepancy rather than a disagreement.

**The cohort's sd(`f`) is genuinely smaller than the corpus's.** 0.3398 %
[0.2665, 0.4693] excludes 0.5365 %. Rule 96 is entitled to that, and its
p = 0.0253 test is a fair one. But I can only partly explain it, and I want to
be explicit about the part I cannot:

- **The coin explains some of it.** The top-`cs` cohort is only **30.8 %**
  high-mode versus 44.5 % in the corpus. Less coin-flipping means less coin
  variance. But Bernoulli variance goes as p(1−p): 0.308·0.692 = 0.213 vs
  0.445·0.555 = 0.247, only 14 % less, which propagates to sd(`f`) ≈ 0.505 % —
  about a fifth of the way from 0.5365 % to 0.3398 %.
- **A ρ of −0.79 would explain it**, since truncating on `cs` with a strong
  negative pass-through gives σ_f√(1−ρ²) = **0.3276 %**, very close to the
  observed 0.3398 %. This is the one piece of evidence *for* Rule 96.1(3), and I
  am reporting it against my own position. It is not conclusive, because the
  corpus ρ is +0.1165 and a selection effect that manufactures a conditional
  correlation from an unconditional one of the opposite sign needs a mechanism
  nobody has proposed.
- **dof 25 is dof 25.** The relative SE of that sd is `1/sqrt(2·25)` = 14.1 %,
  and 0.5365 % is 1.4 SE outside the interval, not 5.

So: the cohort evidence is real and it is worth roughly one-in-forty, not
two-orders-of-magnitude. It justifies "our σ_f estimate is probably somewhat too
big"; it does not justify 3,510 draws.

### 10.6 The conjunction has never happened, and the corpus is too small for it to have (E6)

This is Stage E's own contribution, and it is the cleanest way to state the
problem without any distributional assumption. From the shrunk anchor we need
`f` ≥ **+1.2846 %**. In 1218 receipts:

- **26** receipts sat on a tree at or above the anchor (the "good tree" event).
- **12** receipts drew an `f` at or above +1.2846 % (the "lucky session" event).
- **0** did both. Expected under independence: **26·12/1218 = 0.256**.

The conjunction is not rare-because-impossible; it is rare because it is a
product of two ~1–2 % events and 1218 draws is not enough to have seen it. And
critically, **of the 12 lucky sessions, none was on a good tree** — the best tree
among them is cs 2.574594. Note also that P(both)/draw = 0.256/1218 = **0.0210 %**
is within 36 % of Rule 96's 0.0285 %, which is why its model-free check *felt*
like a confirmation of its Gaussian number. It is not: **0.021 % is the chance
that a receipt drawn at random from the whole channel is a record, and 0.985 %
is the chance that a receipt drawn on *our* tree is.** Those differ by 47×
because we control the tree and the field does not. Rule 96 compares the
conditional quantity against the unconditional test and reads agreement.

The 12 lucky sessions also settle two things:

1. **All 12 are high prefill mode.** 12/12, matching §7's 39/39 on the looser
   threshold. This is now the third independent confirmation that the coin gates
   the record.
2. **The record itself was a lottery win on a tree worse than ours.** The corpus
   maximum score is **2.616504** (`c5b0a13c5cc0`, `a-github-name`,
   2026-08-08T09:09:29Z) on a tree of cs **2.574594** with `f` = **+1.6147 %** —
   a **+3.0σ** session at the corpus σ_f. Their tree is **0.3300 % below our
   anchor**, exactly Rule 96.2's deconvolution.

The second point is the one I would put in front of the advisor. **The `f` we
need (+1.2846 %) is smaller than an `f` that has already been observed
(+1.6147 %)** — indeed smaller than four of the twelve. The record is not a
statistical impossibility that must be engineered away; it is a draw the field
has already made, on worse merit than we already hold.

### 10.7 P(record) per draw, eight ways, and what actually binds (E7)

Need `f` ≥ +1.2846 % from cs = 2.5831058. Hours at our real 0.9 receipts/h share
(Rule 93):

| model | σ used | P/draw | E[draws] | hours |
|---|---|---|---|---|
| **empirical, all receipts** | — | **0.9852 % [0.56, 1.71]** | **101.5** | **113** |
| **empirical, high prefill mode only** | — | **2.2140 % [1.27, 3.83]** | **45.2** | **50** |
| mixture: P(high)·P(clear \| high) | — | 0.9852 % | 101.5 | 113 |
| Gaussian, corpus σ_f | 0.5365 % | 0.8327 % | 120.1 | 133 |
| Gaussian, within-tree pooled σ_f | 0.5411 % | 0.8797 % | 113.7 | 126 |
| Gaussian, within-tree pooled σ(ln score) | 0.5055 % | 0.5523 % | 181.1 | 201 |
| Gaussian, **Rule 96's σ** | 0.3728 % | **0.0285 %** | **3,514** | 3,905 |
| Gaussian, within-mode σ_f (coin uncredited) | 0.1651 % | 3.6e-15 | 2.8e14 | — |

**The σ choice spans a factor of 78 in P/draw.** Every row above except the last
two brackets 0.55–2.21 %/draw. Rule 96's row is an outlier produced by a dof-4 σ
and a Gaussian tail at z = 3.45; the empirical rows need no σ at all, and the
mixture row shows the empirical marginal is exactly the coin times the
conditional, as it must be.

**The number I stand behind: P(record) ≈ 0.99 %/draw [0.56, 1.71] model-free,
E ≈ 102 draws ≈ 113 hours ≈ 4.7 days of our entire channel share.** This
supersedes §5.2's 1.19 %/draw and E ≈ 84 (which used the same method but a
Gaussian-semi-empirical blend), and it rejects Rule 96's 3,510 draws by ~35×.

**And yet Rule 96's ruling is right.** Not because 3,510 draws is unaffordable —
102 draws is also unaffordable at 0.9/h, but only barely, and a campaign could
choose to spend it. It is right because of §6.2's exchange rate, which is a
comparison and therefore survives the σ dispute:

> At a 10-draw budget one extra draw is worth **0.0209 % of `cs` = 1.37 µs/step**
> of decode merit. Rule 91's revert residual is 19.0 µs/step ≈ **14 draws**.
> Rule 94's §94.1 prefill prize is **+9.3 % of score** ≈ 7× the *entire*
> remaining 1.2846 % gap.

A lever worth 7× the whole gap has been sitting unclaimed while 106 rounds of
briefing went into decode residuals worth 0.32 %. **That is the finding, and it
is not "we have been under-drawing".** The advisor asked me to say plainly, if
V-DRAWS fired and Y came out low, that the campaign had been under-drawing and
over-briefing. Y did come out low and V-DRAWS does fire on the numbers — but the
anchor shrinkage moves the conclusion: **we have not been under-drawing, we have
been briefing the wrong axis.** Drawing 102 times to win a lottery whose prize
Rule 94 can buy outright is the worse trade, and it is the trade the exchange
rate rejects. "Engineer first, draw once" is correct; the reason is Y, not 3,510.

### 10.8 The channel's own resolution, and the √2 (E8)

Rule 96.2 says a paired official A/B resolves 0.228 % of `cs` ≈ 15 µs/step, and
0.228 % is its within-tree sd(ln `cs`) itself. But an A/B is a *difference* of
two independent draws, so its sd is σ√2:

| quantity | value |
|---|---|
| pooled within-tree sd(ln `cs`), dof 10 | 0.1834 % [0.1281, 0.3218] |
| 1σ resolution of a 1-vs-1 paired A/B | **0.2593 % of `cs` = 17.0 µs/step** |
| 3σ minimum detectable effect from one pair | **0.7779 % of `cs` = 51.1 µs/step** |
| receipts at or above the record in 1218 | 1 |

Using Rule 96's own σ the 1σ figure would be 0.3219 % (21.1 µs/step) rather than
its stated 0.228 %. Either way the operational point stands and sharpens Rule
94's: **a single official pair cannot resolve anything smaller than ~51 µs/step
at 3σ.** Rule 94's fusion ceiling of 0.231 % (15.2 µs/step) is 3.4× under that
bar on my σ, versus the 2.19× Rule 94 quotes. Mechanisms below ~51 µs/step have
to be established by replication (§8's receipts-per-arm table) or not at all.

---


## 11. Record provenance — a correction

`stage-c.json` → `C6_record_provenance`. The state doc attributes the record to
`submissionCommitSha` prefix `cc6ddc12`. **No receipt with that prefix exists in
the corpus.** The corpus's maximum-score receipt is:

| field | value |
|---|---|
| `submissionCommitSha` prefix | **`c5b0a13c5cc0`** |
| `solverUsername` | **`a-github-name`** |
| `createdAt` | 2026-08-08T09:09:29.443Z |
| `officialScore` | **2.616503543814561** = the record, exactly |
| `cs` (merit) | **2.5745941683956177** |
| `ln L` | **+1.6146984 %** (z = +3.01 against σ_L) |

That `cs` matches #555 Part 1's "the record holder's merit is only 2.574594"
to all quoted digits, so it is the same receipt. **`cc6ddc12` is a
mis-transcription in the state doc; the record's sha prefix is `c5b0a13c5cc0`
and it belongs to `a-github-name`.** Exactly **1** corpus receipt sits at or
above the record — the record itself.

Top 5 by score:

| sha12 | solver | score | `cs` | `ln L` |
|---|---|---|---|---|
| `c5b0a13c5cc0` | **a-github-name** | 2.616504 | 2.574594 | +1.6147 % |
| `01e247a74d1e` | yudduy | 2.606306 | 2.579118 | +1.0487 % |
| `085228339775` | **a-github-name** | 2.605532 | 2.582972 | +0.8696 % |
| *(no sha)* | fyrsta7 | 2.604024 | 2.580357 | +0.9130 % |
| `50526ce8b536` | **a-github-name** | 2.602447 | 2.580111 | +0.8620 % |

**`a-github-name` holds 3 of the top 5, has 209 of the 1218 metric receipts
(≈19/day sustained), and its lottery σ is statistically identical to ours
(0.5627 % vs 0.5375 %).** Their merit is not better than ours — their best `cs`
of 2.582972 is *below* our unbiased 2.583111 and their record receipt's merit
2.574594 is 0.33 % *worse* than it. **They are winning on draw count.** At
1.19 %/draw, 209 draws gives cumulative 91.8 %; our 83 gives 63.0 %; and Rule
93.2 says our real share is ≈4/day against their ≈19/day.

Attribution discipline: all of the above is by `submissionCommitSha` and by
`officialMetrics`, never by trusting `solverUsername` for *our* receipts —
Rule 93.1 means `morganmcg1` is three launches. Two carried facts stand:
`047e192596a091111da7fa9e95fc4d120831fbc0` (2026-08-10T08:03:15Z, cs 2.583470)
**is** ours (frieren R105-B arm P0); `5c542169b5e6c295805f50fa65df3150816eb443`
(08:26:50Z, cs 2.590753) is **not** ours and must never enter the merit table.

---

## 12. Policy paragraph (pasteable into the state doc as a rule)

> **Rule — channel economics.** The record is primarily a baseline-lottery
> outcome: the paired baseline contributes σ = 0.537 % [0.516, 0.559] of score,
> 2.9× our within-tree merit noise σ_cs = 0.183 % [0.128, 0.322], and it is
> i.i.d., tree-independent, and identity-independent (ANOVA over 55 solvers:
> F = 0.97, ICC = 0.0), so all 1218 metric receipts may be pooled for lottery
> statistics. Our best tree's *unbiased* merit is 2.583111, not the order
> statistic 2.590559, so P(record) is **0.99 %/draw [0.56, 1.71]**, E ≈ **102
> draws ≈ 113 hours** at our real share of 0.9 submissions/hour — neither the
> 3.2–3.6 % and ~31 hours of Rule 93.3/93.4 nor the 0.0285 % and 3,510 draws of
> Rule 96.2, both of which price a dof-4 σ as if it were the population value.
> One extra draw is worth **0.021 % of `cs`
> (1.37 µs/step of decode)** at a 10-draw budget, and equivalently a permanent
> +0.10 % merit gain multiplies our effective draw count by **1.584×** at any
> budget; on that scale Rule 92's closed 1.30 µs/step ceiling is worth 1.09×
> draws and is not worth a round, while a real 0.25–0.50 % merit gain is worth
> 3.1–8.2× draws and dominates any plausible increase in submission volume.
> Price a closure in draws, not in ceilings: #619's ceiling is 3.4× under the
> honest 3σ paired gate (0.778 % of `cs` ≈ 51 µs/step, not the 0.228 %/15 µs
> quoted in Rule 96.2, which omits the √2 of a 1-vs-1 difference) yet its
> 0.231 % is worth 2.87× draws ≈ 41 hours of our
> channel, and Rule 94.1's 9.3 % prefill gap would put **every** observed draw
> over the record bar, so it dominates the entire draw budget — "closed for the
> gate" is not "worthless for the lottery".
> Always draw from the single highest-*unbiased*-merit buildable tree and build
> A/B arms on top of it: a 0.10 % merit deficit already costs 35 % of ticket
> value, and it takes ~26 receipts per arm to even establish a deficit that
> small, so diversification is only defensible in the regime where it buys
> nothing. Finally, 0.926 % of score — 60.8 µs/step, more than three times Rule
> 91's disputed residual — sits in a bimodal *baseline* prefill coin we do not
> control: the high mode occurs 44.5 % of the time and is a **necessary**
> condition for a record (39/39 and 12/12 clearing draws were high-mode;
> P(record | low mode) = 0/676, Wilson upper 0.565 %), so expect long dry
> stretches, never rank a mechanism on `officialScore`, and read the last two
> days' cold coin (0.219, 0.273 high-mode) as the reason for the current losing
> streak rather than as evidence against our trees.
> Rule 96.2's **ruling** — "no draw is authorised on a tree we know is ~1.28 %
> short; engineer first, draw once" — stands, but on the corrected arithmetic
> rather than its own: 102 expected draws at 0.9/h is 113 hours, so the ruling
> survives being 35× wrong about P. Do not, however, carry Rule 96.2's
> σ = 0.3728 % into any *other* calculation; it is one dof-4 family with a 35 %
> relative SE, its ρ = −0.79 is not significant (t = −2.25, dof 3), and the
> corpus ρ has the opposite sign (+0.117 [+0.061, +0.172], dof 1216).

---

## 13. What this overturns, and what it leaves standing

**Overturned or corrected:**

1. **Rule 89.2's σ_cs = 1.2244 %** — artifact of one contaminated replicate
   group (F = 37.86; that group is 96.1 % of pooled SS). Use 0.1834 %
   [0.128, 0.322] at dof 10.
2. **Rule 93.1's explanation** of the 4.9× σ gap (launch mixing) — refuted; all
   10 replicate groups are single-account. Its *provenance* warning stands.
3. **Rule 93.3's ladder** — superseded by §5.2 and §10.7. Its own caveat was
   right: 3.2 % and 4.57 % are upper bounds. Central figure **0.99 %/draw**.
4. **"Restoration makes the record ≈1-in-31"** (#555 strategy section, state
   doc) — 1-in-31 is the order statistic; on unbiased merit it is ≈**1-in-102**.
5. **The record's sha `cc6ddc12`** — mis-transcription; it is `c5b0a13c5cc0` by
   `a-github-name`.
6. **"Merit and lottery partially cancel through the pairing"** — β ≈ 0 on the
   prefill axis, so they add in quadrature and campaign z's are optimistic there.
7. **"There is no platform submission quota"** (#555) — already contradicted by
   Rule 88 (single-server queue, ~22 min service, at most one non-terminal
   submission) and Rule 93.2 (our real share 0.9/h, not 2.7/h). All hour columns
   in this report use 0.9/h.
8. **Rule 93.4's note-declared replicate key** — a genuine repair of Rule
   89.1's defective `submissionCommitSha` key, but still not a measurement.
   Byte-checked, it **over-groups two of the four families** (§9.3): my
   calibration triple contains one member that is in no byte-identical group,
   and my corpus-harvest triple sits entirely inside a digest group that fails
   verification on real `Vendor/…/fp_quantized.cpp` diffs. A corrected method is
   itself a result: the number survives (F p ≈ 0.5), the attribution does not.
   Only the two tanjiro families are byte-verified clean.
9. **Quoting a pooled replicate σ without its dof** — scoring the same 15-receipt
   sample at `n−1` instead of `n−k` biases σ by **−15.5 %** (§9.5). Every σ in
   this report carries its dof and its interval.
10. **Rule 96.1(3)'s decision denominator σ = 0.3728 %** — it is the sd(`ln
    officialScore`) of *one* five-member family (dof 4, relative SE 35.4 %,
    CI [0.223, 1.071]). Pooling all five byte-verified families at dof 10 gives
    **0.5055 % [0.353, 0.887]**, whose lower bound already excludes it (§10.2).
    Conditioning on the tree buys essentially nothing here: within-tree sd(f) is
    0.5411 % against a marginal 0.5365 % (F = 1.017).
11. **Rule 96.2's P = 0.0285 %/draw and E = 3,510 draws** — the same dof-4 σ,
    now in the denominator of a z. The model-free count over the same corpus
    gives **12/1218 = 0.99 %/draw [0.56, 1.71]**, E ≈ **102 draws**, i.e. Rule
    96.2 is **~35×** too pessimistic. Its *ruling* survives anyway (§10.7).
12. **Rule 96.2's corroboration of 0.3728 % by the 27-receipt cohort** — the
    cohort reproduces (n = 26, sd(f) = 0.3398 % [0.267, 0.469]) but it is
    *conditioned on high `cs`*, and the mode coin correlates the two: only
    30.8 % of that cohort is high-mode versus 44.5 % of the corpus. A
    conditional sd cannot corroborate an unconditional threshold (§10.5, §10.6).
13. **Rule 96.2's "paired official A/B resolves 0.228 % of `cs` ≈ 15 µs/step"** —
    missing the √2 of a 1-vs-1 difference. σ_diff = 0.2593 % ⇒ **17.0 µs/step**
    at 1σ, and the honest **3σ MDE is 0.7779 % of `cs` ≈ 51 µs/step**, so
    Rule 94's 0.231 % fusion ceiling is **3.4×** under the bar rather than
    2.19× (§10.8). This makes the gate *harder*, not easier.

**Left standing:** #555 Part 1's decomposition and i.i.d. finding (reproduced at
n=1218, max rel err 5.42e-16, runs-test z = 0.428); Rule 93.4's **0.1453 %**
(verified in §9.2 to four significant figures) and its
submit-from-best-merit-tree rule (now quantified, §8); Rule 93.4(3)'s
expectation that the launch mixture F is non-significant (p = 0.0773, §9.6);
Rule 91's N-0 verdict
(#616 Stage 0); Rule 92's closure of the barrier/encoder axis (and §6.1 explains
why closing it was correct — 1.09× draws). §6.2 adds the nuance that a *gate*
closure is not automatically a *lottery* closure: #619's 0.231 % ceiling is
3.4× under the honest 3σ paired bar yet still worth 2.87× draws.
From Rule 96: **96.1(1)** (Arm A has five replicates, not four); **96.1(2)**
(selection bias +0.2881 %, anchor `cs` ≈ 2.583106 — confirmed independently on a
byte digest, §10.1); **96.1(4)** (the per-leg sd table and its F = 447.5,
confirmed to four decimals, §10.3); **96.1(5)** (the payload-content dedup —
independently relevant here only in that `research/` is outside `harnessHash()`,
so this report costs nothing); **96.2's ruling** ("engineer first, draw once")
and its **0.330 % lead** over the record holder's tree (§10.6); and **96.4's**
observation that at this resolution no individual merit claim in the integration
tree is significant — §10.8 makes that *worse*, since the real 3σ bar is 51
µs/step.

**Known limits of this report.** σ_cs and every within-tree quantity rest on
dof 10 (relative SE 22.4 %); the σ interval [0.128, 0.322] propagates into the
semi-empirical P/draw interval [0.974, 2.227] and I quote that interval
everywhere rather than the point. The headline **0.99 %/draw [0.56, 1.71]** is
deliberately the *model-free* count (12 successes in 1218 draws, Wilson
interval) rather than any Gaussian route, precisely because §10.7 shows the
Gaussian routes span five orders of magnitude depending on which σ is chosen —
that spread is the real uncertainty, and it is why Rule 93.4 and Rule 96.2
disagree by 125×. Two Stage E numbers are themselves thin: the mode-conditioned
sd(f) = 0.1651 % rests on dof 7, and the 2×2 conjunction cell in §10.6 is a
0-of-1218 count whose expected value under independence is only 0.256, so the
conjunction is *unmeasured*, not *shown to be rarer than independence*.
The prefill-coin bimodality is a description of the *baseline*, with
no mechanism and no causal claim. Semi-empirical P's convolve an empirical
distribution with a Gaussian σ_cs, which is a modelling choice; the purely
empirical column is given alongside every row and is uniformly *lower*, and the
headline quotes the empirical one. The `ln L` upper tail is slightly fatter than
Gaussian (exponential fits give p(z>4.00) ≈ 1.4–3.0e-4 vs Gaussian 3.2e-5)
against an empirical resolution floor of 1/1218 = 8.2e-4, so record-scale
probabilities beyond z ≈ 3 are extrapolations.

---

## 14. Reproduction

```bash
# Stage A: variance decomposition, semivariogram, ANOVA, tail, drift, invariants
python research/nezuko_r106h_stage_a.py \
  /tmp/r106b/receipt-corpus-frozen.json \
  /tmp/r106b/replicate-identity-verified.json \
  research/artifacts/maple-nezuko-r106h/stage-a.json

# Stage B: winner's curse, P/draw ladder, E[draws], exchange rate, tree diversity
python research/nezuko_r106h_stage_b.py \
  /tmp/r106b/receipt-corpus-frozen.json \
  /tmp/r106b/replicate-identity-verified.json \
  research/artifacts/maple-nezuko-r106h/stage-b.json

# Stage C: launch-mixing discharge, corrected ladder, scale-free exchange rate,
#          prefill coin, record provenance, tree-selection rule
python research/nezuko_r106h_stage_c.py \
  /tmp/r106b/receipt-corpus-frozen.json \
  /tmp/r106b/replicate-identity-verified.json \
  research/artifacts/maple-nezuko-r106h/stage-c.json

# Stage D: R106E-DRAW guard, Rule 93.4(a) verification, note-key vs byte-key
#          adjudication, Bartlett/era homogeneity, robust σ and outlier sweep,
#          two-axis reconstruction, launch partition of ln L
python research/nezuko_r106h_stage_d.py \
  /tmp/r106b/receipt-corpus-frozen.json \
  /tmp/r106b/replicate-identity-verified.json \
  research/artifacts/maple-nezuko-r106h/stage-d.json

# Stage E: adjudicate Rule 96 — winner's-curse key check, the dof-4 denominator,
#          per-leg table, the prefill-mode coin, the top-cs cohort, the 2x2
#          conjunction, P(record) eight ways, and the channel's own resolution
python research/nezuko_r106h_stage_e.py \
  /tmp/r106b/receipt-corpus-frozen.json \
  /tmp/r106b/replicate-identity-verified.json \
  research/artifacts/maple-nezuko-r106h/stage-e.json

# W&B
python research/nezuko_r106h_wandb_log.py \
  research/artifacts/maple-nezuko-r106h/stage-a.json \
  research/artifacts/maple-nezuko-r106h/stage-b.json \
  research/artifacts/maple-nezuko-r106h/stage-c.json \
  research/artifacts/maple-nezuko-r106h/stage-d.json \
  research/artifacts/maple-nezuko-r106h/stage-e.json
```

The corpus and the replicate-identity file are the ones frozen in #616 Stage 0
and copied to `research/artifacts/maple-nezuko-r106b/`; the sha256 above is the
identity check.

The last command produced W&B run **`xuncd3kc`**
(<https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/xuncd3kc>), which
carries every table and scalar quoted above: the record ladder, the per-budget
and scale-free exchange rates, the tree-selection rule, the σ_cs pools, the
prefill coin, the per-cohort σ(ln L), the leaderboard top 5, the Stage D
verification, key-adjudication, homogeneity, axis-reconstruction and launch-
partition tables, and the Stage E Rule-96 adjudication, per-group denominator,
mode-straddle, eight-way P(record), and big-`f` receipt tables. Runs `s31ku9ms`
and `6rosefbh` are the same analysis before Stages D and E existed; prefer the
run above.

## 15. Suggested follow-ups (not implemented)

1. **Price the prefill coin's determinant.** The single largest term in the
   channel (0.926 % of score) is a bimodal *baseline* prefill. A read-only
   census of what distinguishes the two modes — anything visible in the receipt
   besides `peak_ram`, whose β = +3.43 %/GB [−0.34, +7.21] is suggestive only —
   would be worth more than any current mechanism candidate. It needs a
   receipt-side observable, not a code change.
2. **Get σ_cs above dof 10.** Every interval in this report is limited by it.
   The cheapest route is not more receipts but re-running the full-surface
   identity check over the whole corpus to promote more of the 5 contaminated
   groups, or to prove they cannot be promoted.
3. **Re-audit the merit table for order statistics.** §5.1 shows every
   multi-receipt group's max is biased by +0.05 to +0.29 %. Any table that ranks
   trees by observed `cs` with unequal receipt counts is ranking on n.
4. **Decide the decode-axis V-COMMON.** β(`ln dec` on `ln bl_dec`) within trees
   is +0.287 ± 0.380 (dof 9) — uninformative. It carries only 10 % of the
   lottery variance, so this is low priority, but it is the one axis where the
   pairing might genuinely help.
5. **Replace the note-declared replicate key with the byte key in the advisor
   scripts.** §9.3 shows the note key over-groups on 2 of 4 families, and §9.4's
   era split shows it also pools across a 3.7 % merit shift. The byte key already
   exists (`replicate-identity-verified.json` from #616 Stage 0, digested over
   `Sources/` **and** `Vendor/`); wiring it into
   `research/advisor_r103_replicate_sigma.py` — which currently digests
   `Sources/` only, 54 of 2300 files — would make every future σ self-verifying
   at no receipt cost. It will not change the number, only the provenance.
6. **Raise the launch-partition F above p = 0.077.** §9.6's maple-vs-unattributed
   ratio is the one place where our own channel might differ from the cohort's,
   and it points the *unflattering* way. It needs no receipts: attributing more
   of the 41 unattributed `ln L` draws by note or timestamp would resolve it, and
   if it holds, every P/draw in §5.2 should be re-quoted at σ_f = 0.4446 %.
7. **Fit the mixture properly and test it against the Gaussian.** §10.4 shows
   the baseline prefill is a Bernoulli coin plus noise, not a Gaussian, but I
   assigned modes by a hard antimode cut at −0.03507 %. A two-component
   log-normal mixture fitted by EM over all 1218 receipts, with a likelihood-ratio
   test against the single Gaussian and a bootstrap on the mixing weight, would
   turn the coin from a description into a model — and it is the model every
   P/draw in §10.7 actually needs. No receipts, no code changes.
8. **Refresh the freeze and resolve the 26-vs-27 cohort discrepancy.** §10.5
   reproduces Rule 96.2's cohort at n = 26 where it reports 27. The most likely
   cause is that our freezes differ by one receipt admitted after
   2026-08-10T08:37Z, but I cannot rule out a different `officialMetrics` filter
   or a slightly different anchor. Re-pulling with
   `research/nezuko_r106b_pull_corpus.py` and diffing the sha lists against
   #597's would settle it in minutes and would make the two reports directly
   comparable.
9. **Reconcile the `harness_hash` invariance against Rule 93.** §4 (A6) finds
   exactly **one** distinct `harness_hash`, `golden_hash`, and `weights_hash`
   across all 1218 receipts with `officialMetrics`, while Rule 93 reports 68
   distinct `harness_hash` values over 84 receipts. Both cannot be readings of
   the same field. Either Rule 93 read a per-submission payload digest rather
   than the harness identity, or my loader is reading a constant from a nested
   object. This matters because Rule 93's provenance warnings — and any pooling
   argument that leans on harness identity — rest on it.
10. **Price the record with the coin in the model, not the margin.** §10.6 shows
    the record holder won from a tree **0.330 % worse than ours** with f =
    +1.6147 %, and all 12 corpus receipts that cleared our required f were
    high-mode. The operationally useful question is therefore not "how much
    merit do we need" but "given a high-mode draw, what is the conditional gap?"
    That is a one-line recomputation on the existing artifacts and would give the
    campaign a *conditional* draw policy instead of an unconditional one.
