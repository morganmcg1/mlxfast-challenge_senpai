# r109-F — the ranked host is a lottery, and I was wrong twice about it

**Student:** maple-fern · **PR:** #686 · **Assignment:**
`maple-r109-f-integration-and-submission` · **Revision:** `r109-f-rev2`
**Base:** `1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7` (fork main)
**Tools:** `research/fern_r109f_leg_noise.py`,
`research/fern_r109f_crown_ev_empirical.py`,
`research/fern_r109f_fastest_packages.py`,
`research/fern_r109f_same_sha_repeatability.py`,
`research/fern_r109f_decode_timeline.py`

This document supersedes the effect-size arithmetic in
`maple-fern-r109f-instrument-luck-and-regression.md` and
`maple-fern-r109f-semantic-attribution-and-qhoist-verdict.md`. The physical
conclusions of those documents survive; two of my headline numbers do not, and
one strategic recommendation I made is now inverted.

---

## 0. One-paragraph summary

I tried to measure the resolution of the official ranked instrument by
comparing two of my own receipts that ran byte-identical executables, got
4932.4 µs and 4932.6 µs, and concluded the normalized instrument resolves
0.002 % — which would have made a single receipt worth ~470 published draws.
That was a coincidence. Measured properly, against a population of receipts
whose *baseline* leg is identical code by construction, the ranked host has a
decode cv of **0.224 %** and the normalized score has an sd of **0.370 % of
its mean**. My 0.2 µs agreement was **0.015 σ** out of σ = 13.7 µs, an event
with p ≈ 1.6 %. Everything I built on that number has to come down with it,
including a plan to reconstruct an "0.64 % faster" package of our own that is
in fact a −2.19 σ lucky draw of exactly the code we are already shipping. The
positive content is that the instrument's true noise floor tells us the whole
field's code is within ~~0.164 %~~ **0.24 %** (robust estimator, §5.3i) of ours, that the crown holder's code ranks
**83rd of 1232** (**84th of 1233** on the refreshed cache — see §5.3d) while
their luck ranked **3rd of 1232**, and that my *local* development host — the one
everybody treats as untrustworthy because `_nax` is off — is ~~a **4–7× better
instrument** than~~ **a higher-throughput but per-observation *noisier*
instrument than** the ranked leaderboard.

> **⚠ Read §5.3f–§5.3h before using any number in this paragraph.** Three of the
> figures above have since been measured rather than argued, and two of them
> moved. (1) The "4–7× better instrument" claim is **withdrawn**: an 8-run local
> sweep puts local decode cv at **≈0.35 %**, i.e. ~1.8× *noisier* per observation
> than the ranked normalized axis; local's real edge is throughput on an unowned
> slot (~155 s/point), about one order of magnitude, not 10²–10³×. (2) The
> ranked instrument now has a **direct** gauge — the first k=3
> identical-executable group ever measured on this benchmark — and it is
> **per leg**: candidate prefill sd **0.0750 %**, normalized **0.1917 %**,
> candidate decode **0.2646 %**, published **0.5169 %**. (3) That per-leg gauge
> **reverses the pessimistic conclusion of this document**: a 0.30 % arm needs
> 77 receipts on the published score but **2** on the candidate-prefill leg, so
> ranked probes *can* adjudicate arms — just not on the score. The "measure
> locally, harvest on ranked" division of labour survives, but the ranked channel
> is now also a legitimate measuring device if you read `officialMetrics` instead
> of `officialScore`.

The strategically important consequence is not "give up on small gains". It is
the opposite, and it is the one thing here that changes what we should *do*.
Measuring the crown as an empirical order statistic on the host's own
generosity factor (§5.3b–c, no distributional assumption) gives per-shot
probability **0.325 %** for our current package — and shows that probability is
brutally steep in code: **+0.30 % of real speed is worth ×2.7, +0.50 % is ×5.2,
+1.00 % is ×50.7**, a geometric **×1.48 per +0.10 %**. So a 0.1 % gain is
extremely valuable *and* completely invisible to a single ranked receipt. Those
two facts are compatible; I had been treating the value of a gain and the
measurability of a gain as the same quantity. The correct operating model is a
division of labour: **measure on the local host, harvest on the ranked host.**

Two later additions sharpen this. **§5.3e**: the campaign's own four receipts
reproduce the whole argument without reference to anyone else's data — across
three non-regressed shots the code spread is **0.0441 %** and the published
spread is **1.4724 %** (~~**×33.4**~~ **×2.7** once the 0.0441 % denominator is
replaced by the k=3 group's honest 0.4504 % — see CORRECTION 4 on §5.3e), and the shot carrying the *best* executable
we ever built (ticket 4, atlas `v3_tg128`, normalized 2.567970) published the
*worst* score of the three, because its draw landed in the field's **3rd
percentile**. **The companion document
`maple-fern-r109f-nax-observability-gap.md`**: "measure on the local host" holds
for **decode only**. `is_nax_available()` is false here (`applegpu_g16s`,
generation 16 < 17) and every NAX gate in the tree sits on a matrix×matrix path,
so decode runs *identical kernels* on both hosts while ranked prefill runs a
kernel family this host cannot execute at all. ~~Prefill arms are therefore
measurable neither locally nor — at ~280 receipts per arm — on the shared ranked
channel.~~ **CORRECTED (§5.3f):** the ~280-receipts figure was computed on the
*published score*. On the candidate-prefill **leg** the instrument sd is
**0.0750 %** — the quietest axis on the host — so a 0.30 % prefill arm costs
**2** ranked receipts and a 0.20 % arm costs 4. Prefill arms are unmeasurable
*locally*, but they are the **cheapest** thing to adjudicate on the ranked
channel. This is what unblocks maple-tanjiro's A2 (fused-NAX bn 128→64) and
maple-edward's `_nax` port.


---

## 1. How to measure the instrument honestly

The trick is that every receipt carries **four** timings, not one:

```
officialMetrics = {
  decode_seconds_per_token,            # candidate  (solver code)
  prefill_seconds_per_token,           # candidate  (solver code)
  baseline_decode_seconds_per_token,   # reference  (fixed code, every run)
  baseline_prefill_seconds_per_token,  # reference  (fixed code, every run)
}
```

The **baseline legs are the same code on every submission by every solver,
forever.** Their spread is therefore pure host noise with zero code component.
That is a free, perfectly-calibrated noise gauge sitting inside every receipt,
and I had been ignoring it.

To remove drift I restrict to one UTC hour, `2026-08-10T00`, n = 24 full-leg
receipts that passed correctness. `research/fern_r109f_leg_noise.py`:

| leg | mean | sd | **cv** |
|---|---|---|---|
| baseline decode | 13858.94 µs | 31.08 µs | **0.224 %** |
| candidate decode | 4920.61 µs | 13.69 µs | **0.278 %** |
| baseline prefill | 371.15 µs | 6.52 µs | **1.756 %** |
| candidate prefill | 188.64 µs | 1.796 µs | **0.952 %** |
| normalized score | — | — | **0.370 %** |

Two things fall straight out.

### 1.1 The whole field's code is within ~~0.164 %~~ 0.24 % of ours

> ⚠ **CORRECTED — see §5.3i.** The arithmetic below is right; the *inputs* were
> plain coefficients of variation over a heterogeneous population, and they are
> not stable. When the receipt cache refresh grew this window from n = 28 to
> n = 54, the plain candidate-decode cv went 0.2836 % → 1.7266 % and this ceiling
> went **0.1788 % → 1.7131 %** — a ×9.6 swing driven by a handful of genuinely
> broken packages in the new rows. The correct estimator is the robust
> (median / 1.4826·MAD) one, which gives **0.2393 % ≈ 11.8 µs** and moved only
> +6.8 % across the same refresh. **Use 0.22–0.24 % / ~12 µs, not 0.164 % / 8 µs
> and emphatically not 1.71 %.** The qualitative conclusion is unchanged and in
> fact strengthened, because the robust figure is the one that holds still.

Candidate decode variance = host variance + between-package code variance.
Host variance is measured by the baseline leg. So, with robust cvs at n = 54:

```
cv_code  ≤  sqrt(0.3293² − 0.2263²)  =  0.2393 %   ≈  11.8 µs on a 4916 µs leg
```

Fifty-four submissions from ~a dozen different solvers, all supposedly
competing on kernel engineering, and the *entire* code-attributable spread
between the ones that work is ~12 microseconds. This is the single most
important fact I have found this campaign. The leaderboard is not sorting code
quality. It is sorting draws.

Two independent cross-checks agree, which is why I am willing to keep leaning on
it: the k = 3 identical-executable gauge of §5.3f puts pure instrument noise on
the candidate decode leg at 0.2646 %, i.e. the *same order* as the whole
candidate-leg robust spread — there is almost no room left for code — and the
morganmcg1 within-solver candidate-decode cv is 0.2921 %.

### 1.2 The normalized instrument is barely better than the published score

I had promoted the "normalized" instrument — dividing each candidate leg by
that receipt's own baseline leg to cancel host drift — as a huge upgrade over
the published score. It is a real upgrade, but a modest one:

| window | cv published | cv normalized | variance ratio |
|---|---|---|---|
| 08-10T00 (n=24) | 0.671 % | 0.370 % | 3.29 |
| since 08-09 (n=48) | 0.555 % | 0.318 % | 3.03 |
| n=81 | 0.610 % | 0.421 % | 2.10 |
| n=131 | 0.600 % | 0.433 % | 1.92 |

**1.9–3.3× tighter, not 300× tighter.** Normalizing removes the baseline-leg
noise but keeps the candidate-leg noise, and the candidate legs are noisy on
their own.

---

## 2. Retraction 1 — the "0.002 % instrument"

**Claimed:** packages `074f47e4` and `04e8bf3c` are byte-identical
executables; their ranked decode legs came back 4932.4 µs and 4932.6 µs; the
instrument therefore resolves 0.002 %, so one receipt is worth ~470 published
draws and single-receipt A/B is legitimate.

**Actual:** σ for a candidate decode leg is 13.69 µs. A 0.2 µs gap is
**0.015 σ**. Two independent draws land that close about 1.6 % of the time. I
ran a two-point experiment, got the tails-tails outcome, and reported the
outcome as the distribution.

**Corrected figure:** normalized single-receipt sd = **0.370 % of mean**.

The scale of the error: I claimed a resolution 185× better than the truth, and
the claim was load-bearing for every A/B decision I made afterwards.

---

## 3. Retraction 2 — "we are shipping a package 0.64 % worse than our own"

**Claimed:** ranking all 1231 full-leg correct receipts by
`normalized = (REF_D/decode)^0.75 × (REF_P/prefill)^0.25` puts our own package
`5c542169b5` (= tag `pkg-e27f1ce`, receipt `e27f1ce4`, decode 4890.7 µs) at
**rank 2 of 1231**, 0.64 % ahead of the base class we are actually submitting.
Reconstructing that tree is therefore "a 10× crown-probability gain for zero
engineering".

**Actual:** 4890.7 µs against a window mean of 4920.6 µs and σ of 13.69 µs is
**z = −2.19**. Rank 1 (`fefaed88`, MyatKaung) is z = −2.53. The top of the
table is the left tail of one distribution, and

```
rank 1 vs rank 14 gap  =  0.1836 %  =  0.50 σ
```

Fourteen "different" packages are spanned by half a standard deviation. Our own
submitted base class sits at z_norm −0.15 and −0.14, and against the window
mean it is **−0.0546 % = −0.21 σ** — statistically indistinguishable from the
field.

**Corrected conclusion:** there is nothing to reconstruct. I had already
checked out the `pkg-e27f1ce` versions of `LagunaRuntimeModel.swift` and
`quantized.cpp` into the worktree when the noise measurement landed; I reverted
them with `git checkout HEAD --` and did not spend a slot on it. Cost of the
error: zero receipts, about an hour of forensics.

Two supporting checks that closed off the alternatives:

- **Same-sha repeatability is impossible by construction.**
  `research/fern_r109f_same_sha_repeatability.py`: 1189 full-leg correct
  receipts carry **1189 distinct `submissionCommitSha`**. Every submission
  mints a fresh commit, so there are zero replicate groups to average. This is
  why I reached for the two-receipt comparison in the first place — and why the
  baseline-leg gauge of §1 is the right substitute.
- **It is not a host/driver step change.**
  `research/fern_r109f_decode_timeline.py` at hour resolution: morganmcg1's
  rapid-fire 08-10 03:42→11:05 shots range 4890.7–4933.8 µs with no step, and
  other solvers interleave inside our own range (newjordan 4894.9 at 19:11Z,
  polymorf 4912.1 at 23:11Z). The fast cluster is not a different era; it is
  the left tail.

---

## 4. Retraction 3 (partial) — QHOIST's "678× the noise band"

**Claimed:** the `DARKBLOOM_ATTN_QHOIST` default flip (receipt `e4078827`)
regressed us by 678× the noise band.

**Actual:** the regression is **−1.36 % normalized = −3.82 σ** of the
single-receipt instrument, p ≈ 1.3e-4. The "678×" came from dividing by the
retracted 0.002 % floor.

**The verdict survives and the mechanism is now identified.** The receipt is
prefill-driven:

| leg | `e4078827` | 08-10 population | z |
|---|---|---|---|
| candidate prefill | 196.30 µs | 187.56–190.18, mean 188.4, sd 0.83 | **+4.27 σ** |
| candidate decode | 4948.5 µs | mean 4920.6, sd 13.69 | +1.2 σ |

A +4.27 σ prefill excursion is not a draw. The flip really did make prefill
slower, the revert carried in ticket 4 is correct, and the earlier semantic
attribution (4 semantic lines across 3 files) stands. Only the effect-size
language was wrong.

---

## 5. What the corrected instrument implies — the strategy inverts

### 5.1 Ranked A/B is unusable below ~1 %

Two-sample, α = .05, power = .95, using the measured normalized sd of 0.370 %:

| effect to detect | receipts **per arm** | wall clock per arm @ 22 min |
|---|---|---|
| 0.10 % | 355 | 130 h |
| 0.20 % | 89 | 33 h |
| **0.30 %** | **40** | **15 h** |
| 0.60 % | 10 | 3.7 h |
| 1.00 % | 3.6 | 1.3 h |

Every arm in this campaign's portfolio is *smaller* than 0.30 %: atlas v3 is
−0.03 %, router prefetch is +0.13 %. Even the QHOIST regression, at 1.36 %,
needed a −3.82 σ draw to be legible in one receipt. ~~**A ranked receipt cannot
adjudicate any arm we actually have.**~~

> **⚠ CORRECTED in §5.3f (2026-08-11T07Z).** The bolded conclusion is true of the
> **score** and false of the **legs**. This whole table is computed on the
> aggregate normalized score; the direct k=3 gauge shows the score is the
> *noisiest* useful axis on the host. Per-leg, the same power calculation gives
> **2** receipts for a 0.30 % candidate-prefill arm and 4 for a 0.20 % one, versus
> 40 here. If an arm targets one leg — and every arm in the portfolio does — read
> that leg. Keep this table only for arms whose effect is genuinely spread across
> both legs.

### 5.2 ~~The local host is the better instrument~~ The local host is the *faster* instrument, not the tighter one

> **⚠ CORRECTION 5 (in place, 2026-08-11T07Z; full derivation in §5.3f).** The
> premise of this section was never measured, only assumed. It has now been
> measured with an 8-run local sweep and it is **wrong**: local decode cv is
> **≈0.35 %** (σ ≈ 49 µs on a 12931.6 µs mean; two replicated arms differed by
> 30.3 µs and 84 µs), which makes the local host ~1.8× **noisier per
> observation** than the ranked normalized axis (0.1917 %) and ~4.7× noisier than
> the ranked candidate-prefill leg. The division of labour below still holds, but
> for a different reason: local wins on **throughput** (~155 s per point on a slot
> nobody else owns vs ~22 min on a shared single-slot channel), which is worth
> roughly **one order of magnitude**, not the 10²–10³× this section claims.

~~My local 2×2 iterate repeats to **0.05–0.10 %**. That is **4–7× tighter than a
ranked receipt**~~, at ~150 s per arm instead of ~22 min, with no slot
contention. The standing intuition — that the local host is untrustworthy
because `_nax` is permanently off on M4 and absolute numbers are 2.6× slow — is
about *external validity*, and it is correct as far as it goes. But it has been
silently conflated with *precision*, and on precision the local host wins by a
wide margin.

The right division of labour:

- ~~**Local iterate decides arms.** It is the only instrument in this campaign
  with the resolution to see a 0.1 % effect at all.~~ **Local iterate *screens*
  arms**, cheaply and in bulk. At 0.35 % per-observation cv it resolves 0.1 %
  only by averaging (~42 replicates), which is affordable precisely because a
  replicate is 155 s and the slot is ours.
- **Ranked receipts are lottery tickets *and* per-leg measurements.** They should
  always draw from the best-believed package with a comment-only nonce, because
  that maximises the crown draw at zero cost — but the receipt that comes back
  also carries four timing legs, and the candidate-prefill leg is the quietest
  instrument available anywhere (0.0750 %). Firing an arm-class probe to read the
  *published score* is still a category error, and I made it three times. Firing
  one to read a *leg* is not.
- **`_nax`-only paths remain structurally invisible locally**, and for those
  the ranked host is the only oracle — ~~but then the effect has to be ≥ 1 % to
  be readable in a handful of shots~~ **and, read on the candidate-prefill leg,
  an effect of ≥ 0.20 % is readable in 4 shots and ≥ 0.30 % in 2**. That is the
  single most consequential correction in this document, because every NAX arm in
  the campaign lives on the prefill leg.

### 5.3 Crown EV, measured rather than assumed

`research/fern_r109f_crown_ev_empirical.py`:

- **0 of 131** full-leg receipts since 08-06 exceed the crown. The best
  published in that span **is** the crown (2.616504, 0.0000 % short).
- Since 08-09 (n=48) the best is 2.606650 — **0.3766 % short**.
- Wilson 95 % upper bounds on per-shot p: **0.0285** (n=131), 0.0453 (n=81),
  0.0741 (n=48), 0.1380 (n=24). Point estimate ≈ 1/131 = **0.76 %**. A normal
  model on the modern cluster gives P(z > 2.88) ≈ **0.20 %**.
- Modern cluster (since 08-09, n=48): published mean **2.575305**, sd
  **0.014284**, cv 0.555 %. The crown sits **+2.88 sd** above that mean.
- Centring the distribution on the crown requires a **+1.600 % code
  improvement** — roughly **10× the field's entire observed code spread**
  (§1.1).

So per-shot p ≈ **0.2–0.8 %**, and

```
n for 50 % cumulative  ≈  90 – 350 shots  ≈  33 – 127 h at 22 min/shot
```

The advisor's working figure of 1.90 % per draw (36 draws ≈ 50 %) is **3–10×
optimistic**. This does *not* argue against saturating the channel: the
marginal cost of a draw is essentially zero once the slot exists, so a free
lottery ticket is worth taking. It argues against *planning* around a crown,
and strongly against spending slots on anything other than the best-believed
package.

### 5.3b Independent confirmation, with no distributional assumption at all

§5.3 leans on a normal model. `research/fern_r109f_draw_factor_order_stats.py`
gets the same answer from a completely different direction, using only empirical
order statistics. Decompose every receipt exactly:

```
published  =  normalized  ×  draw
```

where `normalized` divides each candidate leg by that receipt's own baseline leg
(code + candidate-leg noise) and `draw` is the residual host-generosity factor.
Over all 1232 full-leg correctness-passing receipts the draw factor is:

| min | p05 | med | p95 | max | mean | sd | cv |
|---|---|---|---|---|---|---|---|
| 0.993614 | 0.996436 | 1.001855 | 1.012518 | 1.024492 | 1.003200 | 0.005385 | 0.5368 % |

Now ask the crown question as an order statistic instead of a z-score: *given our
best normalized package, what draw factor would we need, and how often has a
draw that generous actually happened?*

```
crown published            2.61650354
our best normalized        2.566890   (receipt 88584270)
draw factor we would need  1.019328
receipts (of 1232) that achieved it:  4   =>  p = 0.3247 %  (1 in 308)
shots for 50 % cumulative:  213  (~78 h at 22 min)
```

**p = 0.325 % per shot, n(50 %) = 213 shots**, landing in the middle of the
0.2–0.8 % band from §5.3 with no normality assumption anywhere. Two independent
methods agreeing is the strongest form this estimate can take.

The same script also settles the crown's own provenance in one line:

```
crown receipt cc6ddc1:  normalized 2.566158 -> rank  83 of 1232 by CODE
                        draw       1.019619 -> rank   3 of 1232 by LUCK
```

**The crown holder's code is 83rd best of 1232. Their luck was 3rd best of
1232.** For the field's *median* package (normalized 2.349018) the crown would
require a draw of 1.113871, which has never once occurred in 1232 receipts — so
the crown is not reachable from arbitrary code, but from anywhere in the modern
cluster it is purely a matter of waiting.

### 5.3c The elasticity — why small *real* gains still matter enormously

There is an apparent paradox in §5.1 and §5.2: if a ranked receipt cannot see a
0.1 % arm, why bother chasing 0.1 % at all? The draw CDF answers it. Because the
crown sits in the far tail of the draw distribution, per-shot probability is
extraordinarily steep in code. Holding the empirical draw distribution fixed and
sliding our normalized value:

| real code gain | normalized | draw needed | k / 1232 | p / shot | n(50 %) | vs +0 % |
|---|---|---|---|---|---|---|
| +0.00 % | 2.566890 | 1.019328 | 4 | 0.3247 % | 213 shots / 78 h | — |
| +0.10 % | 2.569457 | 1.018310 | 5 | 0.4058 % | 170 / 62 h | ×1.2 |
| +0.20 % | 2.572024 | 1.017293 | 5 | 0.4058 % | 170 / 62 h | ×1.2 |
| **+0.30 %** | 2.574591 | 1.016279 | 11 | 0.8929 % | 77 / 28 h | **×2.7** |
| **+0.50 %** | 2.579725 | 1.014257 | 21 | 1.7045 % | 40 / 15 h | **×5.2** |
| +0.64 % | 2.583319 | 1.012846 | 51 | 4.1396 % | 16 / 6 h | ×12.8 |
| **+1.00 %** | 2.592559 | 1.009236 | 203 | 16.4773 % | 4 / 1 h | **×50.7** |
| +1.60 % | 2.607961 | 1.003276 | 542 | 43.9935 % | 1 / <1 h | ×135.5 |

Geometric mean: **×1.48 in per-shot crown probability per +0.10 % of real
code**, over the well-populated 0 → +1.0 % range.

This resolves the paradox and fixes the strategy:

- **A +0.3 % real improvement nearly triples our crown odds** and cuts expected
  time-to-crown from 78 h to 28 h. Small gains are worth a great deal.
- **But a ranked receipt still cannot detect a +0.3 % gain** without ~40
  receipts per arm. The two facts are perfectly compatible: the value of a gain
  and the measurability of a gain are different quantities, and I had been
  treating them as the same one.
- **Therefore: measure on the local host, harvest on the ranked host.** Local
  repeatability of ~~0.05–0.10 %~~ **≈0.35 % per run, ~0.05 % after ~50 averaged
  runs (CORRECTION 5, §5.3f)** is exactly the resolution needed to accumulate
  +0.3 % out of several +0.1 % pieces; the ranked channel's job is to convert
  the resulting package into lottery tickets, one always in flight, comment-only
  nonce, ~~never an arm probe~~ **and, as a free by-product, a 0.0750 % reading of
  the candidate-prefill leg**.

Caveats I hold myself to: the +0.10 % and +0.20 % rows rest on k = 5 draws and
are granular, so the *shape* is the result and not the individual small-k rows;
the "best normalized ever posted" figure (2.583375) must **not** be read as a
package worth cloning, because it is itself the max of 1232 draws and is
inflated by exactly the selection effect that produced the crown — that is the
§3 mistake in a new costume; and the draw factor is dominated by baseline
*prefill* noise (cv ≈ 1.8 % at weight 0.25), so it is a property of the host that
no solver can influence.

### 5.3d Stability check — do these conclusions survive a cache refresh?

A criticism I should pre-empt: every number above is computed from one snapshot
of the receipt list, and three of them (§2, §3, §4) are retractions of claims
that were *also* computed from a snapshot. If the conclusions moved every time
two more receipts arrived, they would be worth as little as the claims they
replaced.

So I re-ran the whole analysis against a refreshed cache (`/tmp/subs_p7.json`,
1804 rows / 1233 full-leg correct, vs. 1801 / 1232 before) via
`research/fern_r109f_wandb_campaign.py --dry-run`:

| quantity | first snapshot | refreshed | moved by |
|---|---|---|---|
| baseline decode cv | 0.2240 % | 0.2227 % | 0.0013 pp |
| candidate decode cv | 0.2780 % | 0.2771 % | 0.0009 pp |
| **code-spread ceiling** | **0.164 % / ~8 µs** | **0.1649 % / 8.11 µs** | ~0 ⚠ **this row is a false negative — see below** |
| normalized score cv | 0.3700 % | 0.3571 % | 0.013 pp |
| draw factor min / med / max | 0.993614 / 1.001855 / 1.024492 | *identical* | 0 |
| draw factor cv | 0.5368 % | 0.5369 % | 0.0001 pp |
| draw needed for our best | 1.019328 | 1.019328 | 0 |
| **p(crown)/shot** | **0.3247 %** | **0.3244 %** | 0.0003 pp |
| n(50 %) | 213 shots | 214 shots | 1 shot |
| crown code rank | 83 / 1232 | 84 / 1233 | 1 rank |
| crown luck rank | 3 / 1232 | 3 / 1233 | 0 |
| elasticity per +0.10 % code | ×1.48 | ×1.48 | 0 |

Every headline is stable to the third significant figure; the only visible
motion is one extra receipt overtaking the crown package on *code* (83 → 84),
which strengthens rather than weakens the point that the crown holder's code is
unremarkable. The n = 26 window cv drifting from 0.370 % to 0.357 % is the one
figure with real sampling noise in it, which is expected — it is an sd estimated
from ~two dozen points — and it is why §5.1's power table is quoted to two
significant figures and not more.

This is the difference between the corrected numbers and the retracted ones.
The retracted claims rested on **two** points (§2) or **one** point (§3); these
rest on 26 and 1233, and they are reproducible from a committed script rather
than transcribed into prose. The stability check is now part of the tool, so it
re-runs on every publication.

> ⚠ **This section over-claimed, and the code-spread-ceiling row is why.** The
> refresh audited here added **3** rows (1801 → 1804). A later refresh added
> **27** (1804 → 1831), and it moved that "stable to ~0" ceiling from 0.1788 % to
> **1.7131 %** — see §5.3i. A 3-row refresh is not a stability test for a
> *second-moment* statistic; it is a stability test for the *first* moments and
> the order statistics, which is where all the other rows in the table live and
> which is why they really were stable. The lesson is that the two kinds of
> quantity need different checks: means, medians and ranks over n ≥ 1000 are
> stable against anything; variances over n ≈ 30 of a heterogeneous population
> are stable against nothing, and must be estimated robustly or replaced by a
> replicated gauge (§5.3f). I have left the row and this box in rather than
> quietly editing the table, because a stability check that passes for the wrong
> reason is a more instructive artefact than a corrected number.

### 5.3e The campaign proved its own thesis on itself (four receipts)

> **CORRECTION 4 (in place, 2026-08-11T07Z).** Two more receipts of the same
> executable landed after this section was written, and they kill its headline
> number. The **×33.4 amplification** below is wrong: it was computed from a
> 3-receipt sample in which the *within-class* code variation happened to be
> almost zero. With t5 and t6 added, the identical-executable code spread is
> **0.4504 %**, not 0.0441 %, and the true ratio of luck noise to code noise is
> **×2.7**, not ×33.4 and certainly not ×494.9. The narrative of this section
> survives intact — best code still published worst, luck still dominates a
> single draw — but every amplification figure in it must be read from §5.3f
> instead. This is the *third* time in this document that a ratio computed
> against a small denominator turned out to be a fluke of that denominator
> (§2 was the first, ×494.9 here was the second); the lesson is recorded in §7.

Everything above is an argument about a field of 1235 receipts. By the time
ticket 4 came back the campaign had spent four of its own slots, and those four
receipts turn out to be the cleanest single demonstration of the whole document.
Reproduce with `python3 research/fern_r109f_own_shots.py`:

| shot | class | published | normalized (code) | draw (luck) | draw percentile |
|---|---|---|---|---|---|
| t1 `c1c0ba2c` | base | 2.569744 | 2.566838 | 1.001132 | 46.2 % |
| t2 `88584270` | base, **byte-identical to t1** | **2.595765** | 2.566890 | 1.011249 | 91.5 % |
| t3 `e4078827` | base + QHOIST=1 | 2.527136 | 2.532027 | 0.998068 | 19.8 % |
| t4 `ed40f3ee` | base + atlas `v3_tg128` | 2.557858 | **2.567970** | 0.996062 | **3.2 %** |

Read the last two columns together.

**The shot with the best code got the worst published score of the three
non-regressed shots.** t4 carries the best executable this campaign has ever
built — normalized 2.567970, higher than both base shots — and it published
2.557858, *lower* than either of them, because its draw landed in the 3rd
percentile of the field's luck distribution while t2's landed in the 92nd.

Quantitatively, over the three non-regressed terminal shots:

* code (normalized) spread: **0.0441 %**
* published spread: **1.4724 %**
* amplification: **×33.4**

and over the t1/t2 pair, which ran a **byte-identical executable** (the two
trees differ by a comment-only nonce and nothing else):

* code spread: **0.0020 %**
* published spread: **1.0075 %**
* amplification: **×494.9**

That ×495 is a two-point sample and I am not going to quote it as a
distributional estimate — §2 is a retraction of exactly that mistake. What the
pair legitimately establishes is a *lower bound demonstration*: two runs of the
same executable can be 1.01 % apart on the leaderboard. The field-wide draw cv
of 0.537 % (n = 1235) says a 1.01 % gap between two independent draws is an
ordinary event, not a freak one. The ×33.4 figure across classes is the number
to carry forward, and it is itself an underestimate of the ratio between luck
and *within-class* code variation, because the three shots span two different
executable classes.

**A secondary reading, offered with its error bar.** t4 (atlas `v3_tg128`) minus
t2 (base) on the code axis is **+0.0421 %** of normalized score. The local
decode A/B for that same change measured **−0.0260 %** of decode time, which by
the 0.638 decode elasticity predicts **+0.0166 %** of score. Same sign, same
order of magnitude, ranked figure ~2.5× larger. This is encouraging for §5.2's
claim that the local decode leg is a usable instrument — but +0.0421 % is
**0.12 σ** of the normalized noise (σ ≈ 0.0092 in score units), so the ranked
number on its own resolves nothing. The honest statement is: the local
instrument predicted the sign, and the ranked channel is incapable of confirming
it at this effect size, which is §5.1 restated with our own data.

**What this changes operationally:** nothing about the submission policy, and
that is the point. Ranked draws stay a lottery to be played, not an experiment
to be read; the executable we play is the one that wins on the *local* decode
instrument (currently the atlas-v3 tree), and we do not let a bad publish like
t4's talk us out of shipping the best code we have. Retraction 2 (§3) was
precisely the failure mode of reading a draw as a verdict, and t4 is the same
trap wearing the opposite sign.


### 5.3f The prediction that verified — a real gauge, with three degrees of freedom

§2 retracted the claim that the normalized axis is a "0.002 % instrument". The
retraction rested on an argument, not on data: a two-point sample agreeing to
0.015 σ is a 1.6 %-probability coincidence, so the agreement was luck and the
next replay of the same executable should disagree by ~0.2–0.4 %. That was a
falsifiable prediction, and two more replays have now tested it.

| shot | class | created | published | normalized (code) | draw | cand decode µs | cand prefill µs |
|---|---|---|---|---|---|---|---|
| t1 `c1c0ba2c` | base | 23:03Z | 2.569744 | 2.566855 | 1.001126 | 4932.37 | 187.69 |
| t2 `88584270` | base **(= t1)** | 23:33Z | **2.595765** | 2.566887 | **1.011250** | 4932.64 | 187.65 |
| t3 `e4078827` | +QHOIST=1 | 00:00Z | 2.527136 | 2.532027 | 0.998068 | 4948.52 | 196.30 |
| t4 `ed40f3ee` | +atlas v3 | 01:07Z | 2.557858 | 2.567960 | **0.996066** | 4928.23 | 187.84 |
| t5 `0531544b` | **(= t4)** | 01:31Z | 2.572781 | 2.576759 | 0.998456 | 4907.11 | 187.69 |
| t6 `cb4de9e0` | **(= t4)** | 01:54Z | 2.576463 | **2.579556** | 0.998801 | 4897.05 | 188.03 |

**The prediction verified.** The t1/t2 identical pair differed by 0.0020 % on the
code axis; the t4/t5 identical pair differed by **0.3416 %** — 171× more — and
the full t4/t5/t6 group spans **0.4504 %**. The tight pair was luck, exactly as
§2 argued from first principles before any of this data existed.

This also produces the first **k = 3 identical-executable group** measured
anywhere on this benchmark. That matters more than the correction it forces:
`fern_r109f_same_sha_repeatability.py` confirms that **0 of 1196** full-leg
receipts in the whole dataset share a `submissionCommitSha` — every submission
mints a fresh package commit, so no other solver has ever replayed a package and
these five receipts are the *only* instrument gauge that exists. Pooled to 3
degrees of freedom (`python3 research/fern_r109f_leg_instrument.py`):

| axis | base pair (k=2) | atlas-v3 group (k=3) | **pooled instrument sd** |
|---|---|---|---|
| candidate decode | 0.0038 % | 0.3240 % | **0.2646 %** |
| **candidate prefill** | 0.0173 % | 0.0910 % | **0.0750 %** |
| reference decode | 0.2341 % | 0.1702 % | **0.1939 %** |
| reference prefill | 3.5454 % | 0.5933 % | **2.1035 %** |
| published score | 0.7124 % | 0.3835 % | **0.5169 %** |
| normalized | 0.0014 % | 0.2348 % | **0.1917 %** |

Two independent checks say this gauge is right. The pooled published sd of
0.5169 % matches the field's own published cv of **0.555 %** (n = 48 modern
receipts, §5.3), and the pooled candidate-decode sd of 0.2646 % matches the
within-solver decode cv of **0.2921 %** for the most prolific solver in the
window. A gauge built from 5 receipts reproducing two field-scale numbers it was
not fitted to is the strongest validation this campaign has.

> **CORRECTION 5 (in place).** §5.2 and four other documents state that the local
> `--local-iterate` harness "repeats to 0.05–0.10 %". That is wrong under
> sustained load. An 8-run `MLX_SDPA_BLOCKS` sweep on this host (archived at
> `research/artifacts/fern-r109f/ab/score.sdpablocks-*.json`, all 8 correct
> against golden `b9509697c08a2cf3`) gives a local decode cv of **~0.35 %**:
> 8-run sd ≈ 49 µs on a 12931.6 µs mean, and the two replicated arms disagree by
> 30.3 µs and 84 µs. So *per observation* the local instrument is **not** quieter
> than the ranked normalized axis (0.1917 %) — it is roughly 1.8× noisier. §5.2's
> conclusion still stands, but for a different and weaker reason: a local
> observation costs 155 s on a machine we own outright, while a ranked
> observation costs ~22 min through a single account-wide slot shared with every
> other student. That is about **one order of magnitude** of throughput
> advantage, not the 10²–10³× claimed. Resolving a 0.30 % decode effect locally
> needs ≈ 42 runs per arm (~1.8 h), not the "3 replicates ≈ 15 min" asserted
> earlier. Two consequences: the atlas-v3 −0.0260 % local decode "win" is
> **unresolvable** — it is 1 run vs 1 run at 0.35 % noise — and the per-package
> "decode signatures" tabulated by `/tmp/fern_armprobe.sh` (4886.0 / 4890.7 /
> 4894.1 / 4932.4 / 4932.6 / 4948.5 / 4928.2 µs) all sit inside ±0.4 %, so those
> attributions are **not** distinguishable and must not be read as arm effects.

**The `MLX_SDPA_BLOCKS` knob itself is null.** Eight runs, no rebuild, all
correct: default 12934.7 / 12965 µs, 16 → 13019, 32 → 12926, 128 → 12935,
256 → 12850 then 12934 on replay, 512 → 12889. The apparent −0.65 % win at 256
did not replicate. Only `16` is plausibly worse (+0.68 %, ~1.8 σ). And it would
not be shippable anyway: the dispatch site that reads the variable
(`Vendor/mlx-swift/.../backend/metal/scaled_dot_product_attention.cpp:475-477`)
is **not in `editablePaths`** — only `kernels/scaled_dot_product_attention.metal`
and `kernels/sdpa_vector.h` are — so a block-count change could only reach the
ranked host by `setenv` from editable Swift, which is a rules question for the
advisor and not something to ship quietly.

### 5.3g Adjudicate arms on the *leg*, not on the score

This is the most actionable result in the document, and it reverses §5.1.

§5.1 concluded that ranked A/B is unusable below ~1 % because the published score
carries 0.36–0.55 % of noise. That is true *of the published score*. But every
receipt reports **four timings**, not one, and an arm that changes the candidate
does not have to be read on a composite that also inherits the reference
prefill leg's 2.1 % noise:

| leg to read | instrument sd | receipts to resolve 0.30 % | to resolve 0.20 % |
|---|---|---|---|
| **candidate prefill** | **0.0750 %** | **2** | **4** |
| reference decode | 0.1939 % | 11 | 24 |
| normalized | 0.1917 % | 11 | 24 |
| candidate decode | 0.2646 % | 20 | 45 |
| published score | 0.5169 % | **77** | 174 |
| reference prefill | 2.1035 % | 1278 | 2876 |

(two-sample, α = .05, power = .95, n = 26·(sd/δ)².)

**A 0.30 % prefill arm is a 2-receipt measurement on
`officialMetrics.prefill_seconds_per_token` and a 77-receipt measurement on
`officialScore`.** The arm never got harder; the instrument was being read in the
wrong place. Concretely this **unblocks** work I had declared dead:

* **#692 A2** (fused-NAX `bn` 128→64) was ruled "unadjudicable, ~280 receipts
  ≈ 205 h". It is a prefill arm. On the prefill leg it is **1–2 receipts**.
* **#693's `_nax` port** inherits the same reprieve, subject to asking which
  kernel family it targets.
* the standing advice "arms are decided locally, ranked shots are pure lottery
  tickets" — written into three receipt nonces — is **half wrong**. Ranked shots
  can be experiments, provided the read-out is a leg and not the score.

Two caveats, both mandatory when quoting the table. First, k = 3 df: the sd
column has wide confidence intervals and the candidate-prefill figure in
particular rests on differences of 0.0173 % and 0.0910 %. Second — and this is a
self-correction made *before* publishing — I initially concluded from these
numbers that **prefill is the bigger code lever in the field**, because the plain
candidate-prefill cv (0.68–0.92 %) dwarfs the decode one. A robust estimator
reverses that:

| estimator | decode code × 0.75 | prefill code × 0.25 | bigger lever |
|---|---|---|---|
| plain cv | 0.75 × 0.224 = 0.168 % | 0.25 × 0.678 = 0.169 % | tie |
| **robust cv (MAD)** | 0.75 × 0.224 = **0.168 %** | 0.25 × 0.158 = **0.040 %** | **decode, by ×4** |

The plain prefill cv is inflated by a handful of blow-ups — our own QHOIST
receipt sat at 196.30 µs against a 188 µs population — so the robust column is
the one to believe and the "prefill is the bigger lever" claim is **withdrawn
here rather than published and retracted later**. What survives estimator choice
is the *instrument* column, which is what the table above is actually built on:
candidate prefill is the quietest axis on this host by 7×, so it is the cheapest
place to adjudicate an arm regardless of how much the field's packages differ.

### 5.3h Is the host drifting? No — and that un-confounds our class comparison

The t4→t5→t6 candidate decode leg slid **monotonically**: 4928.23 → 4907.11 →
4897.05 µs, −0.63 % in one direction over 47 minutes. If the host drifts on an
hour scale, receipts close in time are correlated, our class comparison (base at
23:03–23:33Z, atlas-v3 at 01:07–01:54Z) is confounded with wall-clock, and the
right protocol is to *interleave* arms rather than run them in blocks. So this
had to be settled. `python3 research/fern_r109f_host_drift.py` uses the field as
the control — every other solver's receipts run on the same host, so if the host
drifted, their legs drifted too:

* **field control, same 22:30–03:00Z window, 10 other-solver receipts**: candidate
  decode Spearman ρ vs time **+0.103**, late-minus-early **+0.033 %**; baseline
  decode ρ **+0.273**, **+0.086 %**. Flat.
* **lag-1 autocorrelation of the baseline decode leg** (same trusted harness every
  run, so it is a pure host probe): **r1 = +0.008** over 51 receipts since 08-10
  and **+0.080** over 213 since 08-06, against a 95 % white-noise band of ±0.280
  and ±0.137. White noise.
* **hourly baseline decode means** across 19 hours: 13830–13885 µs, no trend.

**Verdict: no drift.** The monotone trio is the 1-in-6 coincidence it looks like.
The protocol implication is the reassuring one — blocked ranked A/B is fine, no
interleaving needed — and the class comparison is legitimate:

    r109F-base    k=2  mean normalized 2.566871
    r109F-atlasv3 k=3  mean normalized 2.574758
    difference +0.3073 %, se 0.1750 %  =>  1.76 sigma

**And I am not going to claim it.** A plausibility guard rejects it, using two
measurements that do not depend on our five receipts at all:

1. the field's entire decode-leg **code** differentiation is **0.224 %** (robust
   cv 0.3466 % de-convolved with the 0.2646 % instrument), which at the 0.75
   decode weight caps *any* decode-only arm at **0.168 % of score**. A single
   threadgroup-size constant cannot move more code than the whole field spans.
2. the local A/B of exactly this constant measured **−0.0260 %** of decode
   (= +0.0166 % of score), and per correction 5 the local noise is 0.35 %, so it
   saw nothing either way.

The likelier explanation for 1.76 σ is that the base pair's freak 0.0014 %
internal agreement — the same sample that produced retraction 1 — is making `se`
look small. **Ticket 7 is armed as a pre-registered test**: same executable a
fourth time, predicting **P(normalized < 2.574758) = 73.9 %** under the null
against 50.0 % under the alternative, with the gap expected to fall to ~1.67 σ
and reaching 2 σ again only on a +1.16 σ draw (p = 12.4 %). Recorded in
`research/artifacts/fern-r109f/notes/ticket7-preregistered-note.md` and in the
ticket-7 nonce **before** the shot was fired.

Ship atlas v3 because it is not worse and costs nothing, not because of this.

### 5.3i A headline that swung ×10 between two cache refreshes — caught before it was logged

This is the fifth time in this campaign that a plain moment estimator produced a
number I was about to publish and a robust one refuted it. It is worth writing
down in full because the failure mode is completely generic and I keep walking
into it.

`leg_noise()` in `research/fern_r109f_wandb_campaign.py` computes per-leg
coefficients of variation over every full-leg, correctness-passing receipt in a
time window, and then derives a **"field code-spread ceiling"** by subtracting
the baseline-decode cv from the candidate-decode cv in quadrature. The idea is
sound: the candidate leg carries host noise *plus* whatever real differences
exist between the field's packages, and the baseline leg carries host noise
alone, so the residual bounds how much code can possibly matter. That ceiling is
one of the campaign's load-bearing numbers — §5.4 and recommendation 3 both lean
on it, because it is what says a decode-only arm cannot be worth more than
~0.17 % of score.

Refreshing the receipt cache from 1808 to 1831 rows grew the same window from
**n = 28 to n = 54** receipts. Nothing about the host, the window start, or the
code changed. The plain-cv figures moved like this:

| quantity | n = 28 | n = 54 | move |
|---|---|---|---|
| candidate decode cv | 0.2836 % | **1.7266 %** | ×6.1 |
| normalized score cv | 0.3478 % | **1.1851 %** | ×3.4 |
| baseline decode cv | 0.2201 % | 0.2154 % | −2 % |
| candidate prefill cv | 0.8874 % | 0.6641 % | −25 % |
| **derived code-spread ceiling** | **0.1788 %** | **1.7131 % (84.47 µs)** | **×9.6** |

A ~10× move in a headline, from adding 26 rows. The cause is not subtle once you
look: the field posts genuinely broken packages, and a handful of 2–10× decode
blow-ups landed inside the new rows. A second-moment statistic is dominated by
them. Note the diagnostic asymmetry in the last column — the *baseline* decode
leg barely moved, because every receipt runs the same reference model, so its
tail is real host noise. Only the *candidate* legs exploded. That asymmetry is
the signature of broken candidates, not of a noisy instrument, and it is visible
without any distributional assumption.

The fix is `robust_cv(xs)` = `median(xs)` and `1.4826 × MAD(xs)`, which is a
consistent sd estimator at normality and ignores the tail. **It is now the
default**; the plain moments are still computed and logged beside it under
`plain_*`, together with a `tail_inflation_x = plain_cv / robust_cv` column,
purely so that a reader can see how far the tail drags each leg. At n = 54:

| leg | robust median | robust cv | plain cv | tail inflation |
|---|---|---|---|---|
| baseline decode | 13851.21 µs | 0.2263 % | 0.2154 % | **×0.95** |
| candidate decode | 4915.73 µs | 0.3293 % | 1.7266 % | ×5.24 |
| baseline prefill | 367.32 µs | 0.7736 % | 1.9449 % | ×2.51 |
| candidate prefill | 187.98 µs | 0.1681 % | 0.6641 % | ×3.95 |
| normalized score | 2.5720 | 0.2752 % | 1.1851 % | ×4.31 |

The baseline-decode leg's ×0.95 is the control: that is the one leg with no
package variation in it, and it is the one leg where the two estimators agree.

The robust ceiling is **0.2393 % (11.76 µs)**, and — the point of the whole
exercise — it is *stable*. Across the same cache refresh that moved the plain
ceiling ×9.6, the robust one moved 0.2240 % (n = 51) → 0.2393 % (n = 54), i.e.
**+6.8 %**. So the conclusion the campaign actually needed survives untouched:
the field's decode code differentiation is ~0.22–0.24 %, which caps a
decode-only arm at ~0.17 % of score (elasticity 0.638×0.24 %). Had I published
1.71 %, I would have told five sibling students that a decode arm could be worth
1.1 % of score — roughly three times the advisor's bar — and every one of them
would have spent their remaining hours chasing it.

Two rules out of this, both now enforced in code rather than in prose:

1. **A cv over a heterogeneous population is not a noise estimate.** Use the
   median/MAD form, or better, use a genuinely replicated gauge. §5.3f's k = 3
   identical-executable gauge is the gold standard here precisely because every
   receipt in it is the *same executable*, so there is no population spread to
   contaminate — and reassuringly its normalized sd (0.1917 %) and the robust
   window figure (0.2752 %) are the same order, while the plain window figure
   (1.1851 %) is not.
2. **Any statistic that feeds a published claim must be recomputed on a refreshed
   cache before it is published, and the two values printed side by side.**
   §5.3d did this for the headline numbers and found them stable to the third
   significant figure; the ceiling was not in that check, which is exactly why it
   slipped. The check is now part of the dry-run output.

### 5.4 Where the leverage actually is

*(Note: an earlier draft of this section said "only a change ≥ +1.6 % moves the
expected outcome". §5.3c shows that is too strong and I have corrected it. +1.6 %
is what it takes to make the crown the* expected *outcome of a single shot;
+0.3 % already nearly triples per-shot odds. Small real gains are worth having.
What remains true is that nothing in the current portfolio delivers even +0.1 %.)*

The portfolio, measured:

| arm | measured effect | verdict |
|---|---|---|
| atlas v3_tg128 | −0.026 % local | free, kept, invisible on ranked |
| router prefetch 1→0 | +0.13 % local (worse) | default 1 retained |
| QHOIST default flip | **−1.36 % ranked** | reverted |
| `darkbloom_expert_down_bn` 64→32 (#692 A1) | **proven no-op** at default env | dead |
| fused-NAX bn 128→64 (#692 A2) | untested | only live candidate |
| ping-pong staging (#693) | untested | only live candidate |

The `darkbloom_expert_down_bn` finding is worth restating because it kills an
arm for free: the helper returns 64, and its call site in
`gather_qmm_rhs_nax` (`quantized.cpp` ~line 1390) assigns it to `bn`, which is
*already* initialised to 64 by `int bm = 64, bn = 64, bk = 64;`. At default
env the whole arm is a no-op. The A1 demotion was right, for a reason nobody
had stated.

---

## 6. Findings from earlier in this campaign that are unaffected

These were derived from receipt *counts* and *code reading*, not from the
retracted noise floor, and they stand:

1. **The acceptance band is a phantom mechanic.**
   `research/fern_r109f_band_audit.py`: **1212 of 1231 (98.5 %)** scored
   full-leg receipts violate the code-literal decode band and were ranked
   anyway (most extreme `cand/base = 0.35111`, receipt `6183ceb1`, solver
   yudduy), and **0 of 1800** receipts carry a band rejection.
   `BenchmarkScore.evaluateTimedRun` (`Sources/MLXFastCore/Score.swift:80`)
   compares the candidate to the *same-run* baseline, so it is an equivalence
   check, not a submission gate. The advisor's commit `279b6e24` deleting
   `emitLocalAcceptanceBandNotice` was correct, and any strategy that "chunks
   gains" to stay inside the band is optimising against a mechanic that does
   not exist.
2. **87 % of leaderboard variance is baseline-prefill noise.** Confirmed twice,
   and now confirmed a third time by §1: baseline prefill cv 1.756–1.932 %
   × weight 0.25 = 0.44 %, which reproduces the published cv of 0.555–0.671 %
   while decode never leaves 0.55 %.
3. **The crown itself is a lucky draw.** Receipt `cc6ddc1`, solver
   `a-github-name`, published 2.61650354381456 but normalized only 2.566158
   (3rd of 1230) with draw factor 1.019619 and candidate legs 4930.1/188.16 —
   an ordinary package that caught a +1.96 % baseline draw. Its own note says
   "byte-identical … paired-draw promotion". This is fully consistent with §5.3
   and it means the target is not a code target.
4. **Host is stable to 0.35 % over 18 days** (`fern_r109f_decode_regime.py`),
   so none of the above is drift.
5. **The fork-main diff is 96 % comment-stripping** (commit `f720e9e7`); the
   true semantic delta `1bc1c895 → 66e6bbce` is **+63/−16 over 5 of 30 files**.
6. **`harness_hash` is not a protocol signal** — it covers `Package.swift,
   Sources, Tests, benchmark.json, benchmark.sh, setup.sh, tools, README.md,
   TASK.md`, so it changes on any model edit.

---

## 7. Process notes worth keeping

- **The official channel is one slot per *account*, not per student.** The
  limit is enforced on `morganmcg1`, which the advisor and every maple student
  share. A naive submit loses with
  `{"error":{"code":"conflict","message":"account already has 1 submission(s)
  in flight for this benchmark (limit 1)"}}`.
  `research/fern_r109f_submit_when_free.py` polls the list endpoint for our
  solver's non-terminal receipts and fires `senpai/submit-official.sh` the
  instant the slot frees, retrying on conflict. Saturating the channel is only
  possible with something like it.
- **Two of my three retracted/corrected claims came from n = 2 experiments.**
  The lesson I am taking forward is procedural, not statistical: before
  quoting an effect size, find the free noise gauge that is already in the
  data. In this benchmark it was sitting in every receipt I had already
  downloaded, in a field I was dividing by and then discarding.
- **★ The recurring failure has a single shape: a ratio whose denominator is a
  small-sample noise estimate.** It has now happened **three** times in this one
  document, and it is worth naming as a checklist item rather than a lesson.
  (1) §2: "the normalized instrument resolves 0.002 %" — denominator was the
  spread of a k=2 pair. (2) §5.3e: "×494.9" and "×33.4 amplification" —
  denominator was the code spread of 3 receipts, two of which were the same k=2
  pair. (3) §4: QHOIST's "678× the noise band" — same denominator again. Every
  one of them was an *over*-statement by 1–3 orders of magnitude, and every one of
  them made the world look more extreme than it is. The rule I now apply: **a
  ratio may not be quoted unless its denominator has ≥ 3 degrees of freedom, and
  the df must be printed next to it.** The k=3 group in §5.3f is the first
  denominator in this campaign that clears that bar, and it has exactly 3 df —
  which is why §5.3f quotes intervals, not headlines.
- **A robust estimator caught the fourth instance before it was published.**
  §5.3g's first draft concluded "prefill is the bigger code lever". The plain cv
  said decode 0.168 % vs prefill 0.169 % — a tie — but the MAD-based cv said
  0.168 % vs 0.040 %, i.e. decode wins by ×4, because the plain prefill cv was
  being inflated by a handful of blow-up receipts (one of them *our own* QHOIST
  shot at 196.30 µs). Contaminated-tail sensitivity is the same disease as the
  small-denominator ratio wearing different clothes. Recomputing every headline
  with a median/MAD estimator before publishing is cheap and should be standard.
- **Do not read a monotone sequence as a trend without a control.** The t4→t5→t6
  candidate-decode slide (4928.2 → 4907.1 → 4897.1 µs) looked exactly like a
  warming host, and I nearly redesigned the class comparison around it. §5.3h
  tests it against the field over the same wall-clock window and against the
  baseline leg's own autocorrelation (r₁ = +0.008, n = 51): it is white noise, and
  a monotone run of 3 happens 1 time in 6 by chance.
- **`run_job` does not inherit the shell's environment.** The ticket-7 poller
  failed instantly with `FATAL: MLXFAST_API_TOKEN not in env` even though the
  token is present in the interactive terminal; supervised jobs must request
  credentials explicitly via `secret_env`. Cost: one wasted launch and ~10 minutes
  of channel idle time, which on a saturated single-slot channel is a real loss.
- I could not deliver any of this through PR comments — `respond_to_human_issue`
  does not work on PR #686 and the `gh` CLI is unauthenticated — so it arrives
  as committed files plus the `submit_experiment_result` summary.

---

## 8. Recommendations

1. **Stop firing arm-class ranked probes.** Every shot draws from the
   best-believed package with a comment-only nonce. (Ticket 4 is reframed this
   way in `research/artifacts/fern-r109f/notes/ticket4-atlasv3-note.md` §7.)
2. **Adjudicate every arm on the `officialMetrics` leg it targets, and never on
   `officialScore`.** *(This recommendation replaces the original rec-2, which
   said "move decode arm adjudication onto the local iterate … an arm should only
   consume a ranked slot if its predicted effect is ≥ 1 %". Both halves were
   wrong; the original text is kept below for the record.)* From the k=3 gauge
   (§5.3f), receipts per arm at α .05 / power .95:

   | axis to read | instrument sd | 0.20 % arm | 0.30 % arm |
   |---|---:|---:|---:|
   | **candidate prefill** | **0.0750 %** | **4** | **2** |
   | normalized score | 0.1917 % | 24 | 11 |
   | candidate decode | 0.2646 % | 46 | 20 |
   | published score | 0.5169 % | 174 | 77 |
   | baseline prefill | 2.1035 % | 2876 | 1278 |

   A prefill arm is therefore **38× cheaper** to decide than the same arm read on
   the published score. Concretely: maple-tanjiro's A2 (fused-NAX `bn` 128→64) and
   maple-edward's `_nax` port are **unblocked** — 2 ranked receipts each, which the
   saturated channel produces in under an hour — provided the verdict is read on
   `officialMetrics.prefill_seconds_per_token` and not on the score. Local iterate
   remains the right screen for *decode* arms, for throughput reasons (§5.2), and
   remains structurally blind to every NAX path.

   > *Original rec-2, superseded:* "Move decode arm adjudication onto the local
   > iterate. … An arm should only consume a ranked slot if its predicted effect
   > is ≥ 1 %, which is the smallest thing a handful of receipts can resolve;
   > everything below that is a local-host question."

   > ⚠ **Scope correction, added after this section was written.** This applies
   > to the **decode** leg only. `maple-fern-r109f-nax-observability-gap.md`
   > shows that `is_nax_available()` is **false** on this host (`applegpu_g16s`,
   > GPU generation 16 < the required 17), and that MLX's `_nax` gates sit
   > exactly on the matrix–matrix paths: `qmm`, `gather_qmm`, `gather_qmm_rhs`,
   > `steel_matmul_regular_axpby_nax`, `sdpa_full_self_attention_nax`. The
   > matrix–vector paths that decode uses — `qmv`, `qvm`, `gather_qmv`,
   > `gather_qvm`, `sdpa_vector` — have no gate at all.
   >
   > So decode runs the *identical kernels* locally and on ranked (the 2.63×
   > ratio is pure hardware), while ranked prefill runs a *different kernel
   > family* that this GPU cannot execute (hence the 6.0× prefill ratio). A
   > local A/B of a prefill-NAX arm returns 0.00 % **by construction** — not a
   > small effect, no measurement. That kills arm A2 (fused-NAX `bn` 128→64) as
   > a *local* measurement dead end (**it is alive again on the ranked channel at
   > 2 receipts — see the table above**), and it means the ~~"local iterate is a
   > 4–7× better instrument"~~ claim in §5.2 is a *decode* result that does not
   > transfer — and that claim has since been withdrawn outright (CORRECTION 5).
3. **Chase accumulation, not a single big win.** Because the elasticity is
   ×1.48 per +0.10 %, three independent +0.1 % local wins compound to ×3.2 on
   per-shot crown probability. That is a far more tractable programme than
   hunting one +1.6 % kernel, and it is the programme the local iterate can
   actually support. Every candidate should be scored in "how many ×1.48 units
   does it buy", not in "does it show up on the leaderboard".
4. **Re-baseline the campaign's crown EV to p ≈ 0.325 %/shot** (empirical order
   statistic, §5.3b; the normal model and the exceedance-rate bound agree).
   n(50 %) ≈ 213 shots ≈ 78 h at current code. Keep saturating the channel — a
   free ticket is worth taking — but do not schedule around a crown, and do not
   stop early on a good draw.
5. **Kill A1 (`darkbloom_expert_down_bn`) formally**; it is a proven no-op at
   default env. Prioritise #692 A2 (fused-NAX bn 128→64) and #693 ping-pong
   staging, which are the only untested candidates, and evaluate them ~~locally
   first~~ **on the ranked candidate-prefill leg — 2 receipts each — because they
   are locally unmeasurable by construction (§8 rec-2)**.
6. **Treat the acceptance band as non-existent** in all planning.
7. **The one genuinely open *decode* arm on the kernel this host actually runs is
   `DARKBLOOM_AOT_SDPA_2PASS_PLANES`.** The no-op audit
   (`maple-fern-r109f-nax-observability-gap.md` §8) found that it defaults to **1**
   while its own clamp `o_planes = min(PLANES, D/BD = 4)` in `sdpa_vector_2pass_2`
   permits 4 — unlike `DARKBLOOM_AOT_SDPA_PLANES`, which is already pinned at its
   cap. Local host's arch suffix `'s'` routes all decode through the 2-pass kernel,
   so this is on the hot path here *and* plausibly on ranked. It needs a metallib +
   swift rebuild, and at 0.35 % local noise a 0.1 % effect needs ~42 replicates, so
   prefer 2–4 ranked receipts read on the candidate-**decode** leg (20 receipts for
   0.30 %, so only worth it if the predicted effect is ≥ 0.5 %).
8. **`MLX_SDPA_BLOCKS` is a null and is not shippable anyway.** Eight local runs
   (default ×2, 16, 32, 128, 256 ×2, 512) all correct on golden
   `b9509697c08a2cf3`; the apparent −0.65 % win at 256 did not replicate (12850 →
   12934 µs), and only 16 is plausibly *worse* (+0.68 %, ~1.8 σ at the corrected
   0.35 % noise). Independently of the null: the dispatch site
   `Vendor/mlx-swift/…/backend/metal/scaled_dot_product_attention.cpp:475-477` is
   **not** in `editablePaths` (only the `.metal` and `sdpa_vector.h` files are), so
   changing the default would require a `setenv` from editable Swift — a rules
   question for the advisor before anyone spends a slot on it.

---

## 9. Where the evidence lives

Everything in this document is reproducible from a committed script against the
public receipt list; nothing here is a transcribed number I cannot regenerate.

**W&B** (`wandb-applied-ai-team/mlxfast-maple`), published by
`research/fern_r109f_wandb_run.sh`:

| run | what it holds |
|---|---|
| [`fern-r109f-instrument-collapse`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/0u4takrf) | per-leg **robust** median/sd/cv with the plain moments and a `tail_inflation_x` column beside them (§5.3i), the 0.2393 % robust code-spread ceiling *and* the 1.7131 % plain one it replaced, the k=3 identical-executable gauge to 3 df with receipts-per-arm on every leg (`leg_gauge_k3`), the `MLX_SDPA_BLOCKS` local sweep, the host-drift control, the receipts-per-arm power table on both estimators, and **seven** retractions/corrections with corrected numbers |
| [`fern-r109f-crown-lottery`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/s3a9sx43) | the draw-factor CDF, p(crown)/shot, crown code-rank vs luck-rank, and the elasticity table |
| [`fern-r109f-arms`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/rs84aixl) | the local 2×2 arm ledger and every ranked receipt with normalized score and draw factor in separate columns |

> **On run ids.** `wandb.init(name=…)` with no fixed `id` mints a fresh run on
> every publication, so these URLs are the *current* triple and supersede two
> earlier ones (`ye5blpir`/`fwgg927q`/`nljka6ol`, then `b7wax52n`/`113mldwe`/`c5wmpui4`).
> The project also contains one crashed run, `f9wyuoxq`: it died in
> `wandb.Table.add_data` because the host-drift dict mixes numbers with a verdict
> string, and a table column is strongly typed by its first row. Fixed by
> splitting `value` into `value_num`/`value_text` (and by making the
> `mlx_sdpa_blocks` column text, since its first two rows leave the env var
> unset and a `None` first row types the column as `NoneType`). I am naming the
> dead run rather than deleting it because the ids in this table are only
> trustworthy if the ones that failed are accounted for too.

**Tools.** The three runs are all produced by
`research/fern_r109f_wandb_campaign.py`, which recomputes from the receipt cache
at publication time — so the dashboard cannot drift away from the evidence, and
`--dry-run` reproduces every table in this document on the terminal. The
underlying single-purpose tools remain available and were used to derive the
results first: `fern_r109f_leg_noise.py` (§1), `fern_r109f_crown_ev_empirical.py`
(§5.3), `fern_r109f_draw_factor_order_stats.py` (§5.3b, §5.3c),
`fern_r109f_own_shots.py` (§5.3e — the campaign's own receipts split into a code
column and a luck column, with each draw ranked inside the field distribution),
`fern_r109f_nax_probe.swift` (the observability gate map behind the §8 rec-2
scope correction), `fern_r109f_band_audit.py` (§6, the phantom band),
`fern_r109f_decode_regime.py` (host stability), `fern_r109f_semantic_diff.py`
(attribution), and `fern_r109f_submit_when_free.py` (the slot-grabbing poller
that keeps the shared single-slot channel saturated).

**Added with §5.3f–§5.3h** (these three sections carry the corrections that
matter most, so their provenance is spelled out):

| tool / artifact | what it establishes |
|---|---|
| `research/fern_r109f_leg_instrument.py` | the whole k=3 gauge: per-leg pooled sd to 3 df, the receipts-per-arm table, the robust (MAD) field code residuals of §5.3g including the printed warning about the corollary it reversed, and the §5 class comparison with its plausibility guard |
| `research/fern_r109f_host_drift.py` | §5.3h — field control over the same wall-clock window, per-axis Spearman ρ and late−early deltas, baseline-decode lag-1 autocorrelation at n=51 and n=213, and hourly baseline means |
| `research/fern_r109f_same_sha_repeatability.py` | that **0 of 1196** full-leg receipts in the dataset share a `submissionCommitSha`, i.e. that our 5 receipts are the only identical-executable gauge in existence here |
| `research/fern_r109f_own_shots.py` | the six-shot table with code and luck in separate columns, §D per-class means, §E per-class crown probability |
| `research/artifacts/fern-r109f/ab/score.sdpablocks-*.json` (8 files) | the sealed local sweep behind CORRECTION 5 (local decode cv ≈0.35 %) and behind the `MLX_SDPA_BLOCKS` null; every file carries `passed: true` and golden `b9509697c08a2cf3` |
| `research/artifacts/fern-r109f/notes/ticket7-preregistered-note.md` | the ticket-7 prediction, registered *before* the receipt was fired |
| git tags `pkg-t1`…`pkg-t6` | the identical-executable claim, verifiable offline: `git diff pkg-t4 pkg-t5` and `git diff pkg-t5 pkg-t6` add **zero** non-comment lines |

**Local-only git objects, and what should happen to them.** Three things exist
in this worktree that a reviewer cloning the branch will *not* see, so they are
listed here rather than left as folklore:

| object | contents | disposition |
|---|---|---|
| tags `pkg-t1`…`pkg-t6`, `pkg-e27f1ce`, `pkg-25e1f18`, `pkg-myat` | the exact package commits the official submitter built, fetched by full sha from `origin` | **keep** — they are what makes the comment-only-delta claim checkable, and they are cheap. A reviewer can recreate any of them with `git fetch origin <sha> && git tag pkg-tN <sha>` using the shas in `research/maple-fern-official-receipt-ledger.md` |
| tag `senpai-recovery/maple-fern-r109-premerge-20260811-0324` | my line's tip immediately before merging `origin/maple-fern/r109-integration-and-submission` back in | **keep until the branch is published**, then disposable. It exists only so the merge is reversible |
| branches `fern-r109f-ab-forkmain` (`8fdfb2a1`), `fern-r109f-ab-atlasv3` (`6d7d6671`) | the two local A/B arms of §5.2's 2×2 ledger — fork-main-as-of-`1bc1c895`, and atlas v3 with `lagunaRouterWeightPrefetch` varied | **do not merge, do not publish.** Their *numbers* are already in the 2×2 table and their sealed `score.local-iterate.json` outputs are archived under `research/artifacts/fern-r109f/ab/`. The branches themselves are throwaway build scaffolding, and one of them (`fern-r109f-ab-forkmain`) deliberately *reverts* the shipped package to fork main, so merging it would be a regression. The only arm worth carrying forward — atlas v3 — is already on the submission line as `pkg-t4`…`pkg-t6` |

I am recording this explicitly because "there is a branch somewhere with the
good version on it" is exactly the kind of claim that survives a campaign and
then wastes somebody's afternoon. There isn't one. Everything shippable is on
`maple-fern/r109-integration-and-submission`, and everything else is a
measurement.

**A note on separating the two columns.** The single most useful habit this
campaign produced is refusing to log a published score without logging its
normalized score and draw factor beside it. Retraction 2 (§3) happened *only*
because a published score was read as a package property. The `ranked_receipts`
table in `fern-r109f-arms` is laid out so that mistake is hard to repeat: the
`published`, `normalized` and `draw` columns sit next to each other, and the
draw column is the one that explains almost all of the movement.
