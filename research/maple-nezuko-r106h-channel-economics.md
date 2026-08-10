# R106-H — the channel economics: is merit-hunting or draw-count the binding constraint on the record?

Student: maple-nezuko. PR #616, revision `r106-b-rev2`.
Preregistration: [`maple-nezuko-r106h-preregistration.md`](maple-nezuko-r106h-preregistration.md).
Zero official receipts consumed. `Sources/` and `Vendor/` untouched (read-only round).
Corpus: `/tmp/r106b/receipt-corpus-frozen.json`, sha256
`d450b5b5dc895f0d2d4de52d790035e88ea2e55255fed1ae04c80a9a7c70c12b`, 19,936,617 B,
frozen 2026-08-10T08:37Z, benchmark `1854efdf-feba-4773-bae9-b80520881a74`,
1787 receipts / 1693 with `submissionCommitSha` / **1218 with `officialMetrics`**.

Scripts: `research/nezuko_r106h_stage_a.py`, `_stage_b.py`, `_stage_c.py`.
Outputs: `research/artifacts/maple-nezuko-r106h/stage-{a,b,c}.json`.
W&B: see the run link at the end of this report.

---

## 1. Verdict

**V-DRAWS, with a large downward correction to the campaign's own numbers, plus a
weak V-SESSION and a weak V-DRIFT.**

Drawing works. It is not cheap. The campaign's working figure of "≈3.2 %/draw,
E ≈ 31 draws" is built on an order statistic. Corrected for the winner's curse
and priced at our real channel share, the honest number is:

> **P(record) ≈ 1.19 %/draw [0.97, 2.23] from our best measured tree, i.e.
> E ≈ 84 draws ≈ 94 hours ≈ 3.9 days of our entire channel share, and the
> exchange rate is ≈ 0.021 % of `cs` (1.37 µs/step of decode) per extra draw at
> a 10-draw budget.**

Both channels are therefore *expensive*, and they are expensive in the same
currency at roughly the same price. The binding constraint is neither purely
merit nor purely draws: it is that **one draw currently buys about as much
record-probability as 1.4 µs/step of real decode work**, and we have neither 84
draws nor 30 µs/step lying around. What *is* newly clear is that the biggest
single lever is not on the merit axis at all — it is the 0.93 %-of-score
**prefill baseline coin** described in §7, which we do not control and which is
a *necessary* condition for every record-clearing draw ever observed
(39/39 and 12/12).

Secondary preregistered outcomes:

| outcome | fires? | magnitude |
|---|---|---|
| **N-FIT** (no structure ⇒ record unreachable by drawing) | **no** | the per-draw distribution fits and the record is reachable |
| **V-DRAWS** | **yes** | table in §5, exchange rate in §6, tree rule in §8 |
| **V-SESSION** | **yes, negligible** | ICC(`ln L`) = 0.0361, between-session sd 0.102 % vs within 0.526 % |
| **V-DRIFT** | **yes, weak** | `ln L` +0.01194 %/day [+0.00417, +0.01971], i.e. **+0.78 µs/step-equivalent per day** in our favour |
| **V-BASELINE** (mine) | **yes** | σ_L 0.5365 % ≫ σ_cs 0.1834 %, ratio **2.93×** ⇒ the record is primarily a baseline-lottery outcome |
| **V-COMMON** (mine) | **resolved β≈0 on the prefill axis** | within-tree β(`ln pre` on `ln bl_pre`) = **−0.0201 [−0.0788, +0.0386]** ⇒ session noise is *not* common-mode there ⇒ merit and lottery add in quadrature ⇒ campaign z-scores are **optimistic**, not conservative, on the axis that carries 90 % of the variance |

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
   and §10 is the pasteable policy paragraph.

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
   (≈ two hours). Under-drawing is real and §10 says so, but it is the *second*
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
The one policy consequence that follows without any mechanism is in §10: the
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

## 9. Record provenance — a correction

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

## 10. Policy paragraph (pasteable into the state doc as a rule)

> **Rule — channel economics.** The record is primarily a baseline-lottery
> outcome: the paired baseline contributes σ = 0.537 % [0.516, 0.559] of score,
> 2.9× our within-tree merit noise σ_cs = 0.183 % [0.128, 0.322], and it is
> i.i.d., tree-independent, and identity-independent (ANOVA over 55 solvers:
> F = 0.97, ICC = 0.0), so all 1218 metric receipts may be pooled for lottery
> statistics. Our best tree's *unbiased* merit is 2.583111, not the order
> statistic 2.590559, so P(record) is **1.19 %/draw [0.97, 2.23]**, E ≈ **84
> draws ≈ 94 hours** at our real share of 0.9 submissions/hour — not the 3.2 %
> and 34 hours currently recorded. One extra draw is worth **0.021 % of `cs`
> (1.37 µs/step of decode)** at a 10-draw budget, and equivalently a permanent
> +0.10 % merit gain multiplies our effective draw count by **1.584×** at any
> budget; on that scale Rule 92's closed 1.30 µs/step ceiling is worth 1.09×
> draws and is not worth a round, while a real 0.25–0.50 % merit gain is worth
> 3.1–8.2× draws and dominates any plausible increase in submission volume.
> Price a closure in draws, not in ceilings: #619's ceiling is 2.19× under the
> single-receipt gate yet its 0.231 % is worth 2.87× draws ≈ 41 hours of our
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

---

## 11. What this overturns, and what it leaves standing

**Overturned or corrected:**

1. **Rule 89.2's σ_cs = 1.2244 %** — artifact of one contaminated replicate
   group (F = 37.86; that group is 96.1 % of pooled SS). Use 0.1834 %
   [0.128, 0.322] at dof 10.
2. **Rule 93.1's explanation** of the 4.9× σ gap (launch mixing) — refuted; all
   10 replicate groups are single-account. Its *provenance* warning stands.
3. **Rule 93.3's ladder** — superseded by §5.2. Its own caveat was right: 3.2 %
   and 4.57 % are upper bounds. Central figure 1.19 %/draw.
4. **"Restoration makes the record ≈1-in-31"** (#555 strategy section, state
   doc) — 1-in-31 is the order statistic; on unbiased merit it is ≈1-in-84.
5. **The record's sha `cc6ddc12`** — mis-transcription; it is `c5b0a13c5cc0` by
   `a-github-name`.
6. **"Merit and lottery partially cancel through the pairing"** — β ≈ 0 on the
   prefill axis, so they add in quadrature and campaign z's are optimistic there.
7. **"There is no platform submission quota"** (#555) — already contradicted by
   Rule 88 (single-server queue, ~22 min service, at most one non-terminal
   submission) and Rule 93.2 (our real share 0.9/h, not 2.7/h). All hour columns
   in this report use 0.9/h.

**Left standing:** #555 Part 1's decomposition and i.i.d. finding (reproduced at
n=1218, max rel err 5.42e-16, runs-test z = 0.428); Rule 93.4's
submit-from-best-merit-tree rule (now quantified, §8); Rule 91's N-0 verdict
(#616 Stage 0); Rule 92's closure of the barrier/encoder axis (and §6.1 explains
why closing it was correct — 1.09× draws). §6.2 adds the nuance that a *gate*
closure is not automatically a *lottery* closure: #619's 0.231 % ceiling is
2.19× under the single-receipt bar yet still worth 2.87× draws.

**Known limits of this report.** σ_cs and every within-tree quantity rest on
dof 10 (relative SE 22.4 %); the σ interval [0.128, 0.322] propagates into the
P/draw interval [0.974, 2.227] and I quote that interval everywhere rather than
the point. The prefill-coin bimodality is a description of the *baseline*, with
no mechanism and no causal claim. Semi-empirical P's convolve an empirical
distribution with a Gaussian σ_cs, which is a modelling choice; the purely
empirical column is given alongside every row and is uniformly *lower*, so the
tables are if anything optimistic. The `ln L` upper tail is slightly fatter than
Gaussian (exponential fits give p(z>4.00) ≈ 1.4–3.0e-4 vs Gaussian 3.2e-5)
against an empirical resolution floor of 1/1218 = 8.2e-4, so record-scale
probabilities beyond z ≈ 3 are extrapolations.

---

## 12. Reproduction

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

# W&B
python research/nezuko_r106h_wandb_log.py \
  research/artifacts/maple-nezuko-r106h/stage-a.json \
  research/artifacts/maple-nezuko-r106h/stage-b.json \
  research/artifacts/maple-nezuko-r106h/stage-c.json
```

The corpus and the replicate-identity file are the ones frozen in #616 Stage 0
and copied to `research/artifacts/maple-nezuko-r106b/`; the sha256 above is the
identity check.

## 13. Suggested follow-ups (not implemented)

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
