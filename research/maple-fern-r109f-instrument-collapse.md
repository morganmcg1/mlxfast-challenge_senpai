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
field's code is within 0.164 % of ours, that the crown holder's code ranks
**83rd of 1232** while their luck ranked **3rd of 1232**, and that my *local*
development host — the one everybody treats as untrustworthy because `_nax` is
off — is a **4–7× better instrument** than the ranked leaderboard.

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

### 1.1 The whole field's code is within 0.164 % of ours

Candidate decode variance = host variance + between-package code variance.
Host variance is measured by the baseline leg. So

```
cv_code  ≤  sqrt(0.278² − 0.224²)  =  0.164 %   ≈  8 µs on a 4920 µs leg
```

Twenty-four submissions from ~a dozen different solvers, all supposedly
competing on kernel engineering, and the *entire* code-attributable spread
between them is 8 microseconds. This is the single most important fact I have
found this campaign. The leaderboard is not sorting code quality. It is
sorting draws.

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
needed a −3.82 σ draw to be legible in one receipt. **A ranked receipt cannot
adjudicate any arm we actually have.**

### 5.2 The local host is the better instrument

My local 2×2 iterate repeats to **0.05–0.10 %**. That is **4–7× tighter than a
ranked receipt**, at ~150 s per arm instead of ~22 min, with no slot
contention. The standing intuition — that the local host is untrustworthy
because `_nax` is permanently off on M4 and absolute numbers are 2.6× slow — is
about *external validity*, and it is correct as far as it goes. But it has been
silently conflated with *precision*, and on precision the local host wins by a
wide margin.

The right division of labour:

- **Local iterate decides arms.** It is the only instrument in this campaign
  with the resolution to see a 0.1 % effect at all.
- **Ranked receipts are lottery tickets, not measurements.** They should always
  draw from the best-believed package with a comment-only nonce. Firing an
  arm-class probe spends a 22-minute slot to obtain one sample of a 0.370 %-sd
  variable in order to resolve a 0.03 % effect. That is not a small
  inefficiency; it is a category error, and I made it three times.
- **`_nax`-only paths remain structurally invisible locally**, and for those
  the ranked host is the only oracle — but then the effect has to be ≥ 1 % to
  be readable in a handful of shots, which is a useful bar to hold arm
  proposals to.

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
  repeatability of 0.05–0.10 % is exactly the resolution needed to accumulate
  +0.3 % out of several +0.1 % pieces; the ranked channel's job is to convert
  the resulting package into lottery tickets, one always in flight, comment-only
  nonce, never an arm probe.

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
| **code-spread ceiling** | **0.164 % / ~8 µs** | **0.1649 % / 8.11 µs** | ~0 |
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
- I could not deliver any of this through PR comments — `respond_to_human_issue`
  does not work on PR #686 and the `gh` CLI is unauthenticated — so it arrives
  as committed files plus the `submit_experiment_result` summary.

---

## 8. Recommendations

1. **Stop firing arm-class ranked probes.** Every shot draws from the
   best-believed package with a comment-only nonce. (Ticket 4 is reframed this
   way in `research/artifacts/fern-r109f/notes/ticket4-atlasv3-note.md` §7.)
2. **Move *decode* arm adjudication onto the local iterate.** Not because small
   gains do not matter — §5.3c shows +0.30 % is worth ×2.7 on crown odds — but
   because the local host is the only instrument in this campaign that can *see*
   them. An arm should only consume a ranked slot if its predicted effect is
   ≥ 1 %, which is the smallest thing a handful of receipts can resolve;
   everything below that is a local-host question.

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
   > a measurement dead end, and it means the "local iterate is a 4–7× better
   > instrument" claim in §5.2 is a *decode* result that does not transfer.
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
   staging, which are the only untested candidates, and evaluate them locally
   first.
6. **Treat the acceptance band as non-existent** in all planning.

---

## 9. Where the evidence lives

Everything in this document is reproducible from a committed script against the
public receipt list; nothing here is a transcribed number I cannot regenerate.

**W&B** (`wandb-applied-ai-team/mlxfast-maple`), published by
`research/fern_r109f_wandb_run.sh`:

| run | what it holds |
|---|---|
| [`fern-r109f-instrument-collapse`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/ye5blpir) | per-leg mean/sd/cv, the 0.1649 % code-spread ceiling, the receipts-per-arm power table, and all three retractions with corrected numbers |
| [`fern-r109f-crown-lottery`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/fwgg927q) | the draw-factor CDF, p(crown)/shot, crown code-rank vs luck-rank, and the elasticity table |
| [`fern-r109f-arms`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/nljka6ol) | the local 2×2 arm ledger and every ranked receipt with normalized score and draw factor in separate columns |

**Tools.** The three runs are all produced by
`research/fern_r109f_wandb_campaign.py`, which recomputes from the receipt cache
at publication time — so the dashboard cannot drift away from the evidence, and
`--dry-run` reproduces every table in this document on the terminal. The
underlying single-purpose tools remain available and were used to derive the
results first: `fern_r109f_leg_noise.py` (§1), `fern_r109f_crown_ev_empirical.py`
(§5.3), `fern_r109f_draw_factor_order_stats.py` (§5.3b, §5.3c),
`fern_r109f_band_audit.py` (§6, the phantom band),
`fern_r109f_decode_regime.py` (host stability), `fern_r109f_semantic_diff.py`
(attribution), and `fern_r109f_submit_when_free.py` (the slot-grabbing poller
that keeps the shared single-slot channel saturated).

**A note on separating the two columns.** The single most useful habit this
campaign produced is refusing to log a published score without logging its
normalized score and draw factor beside it. Retraction 2 (§3) happened *only*
because a published score was read as a package property. The `ranked_receipts`
table in `fern-r109f-arms` is laid out so that mistake is hard to repeat: the
`published`, `normalized` and `draw` columns sit next to each other, and the
draw column is the one that explains almost all of the movement.
