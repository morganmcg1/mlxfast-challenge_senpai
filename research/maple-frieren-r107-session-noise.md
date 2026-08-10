# R107 — Session noise: magnitude, structure, and what it implies for the record chase

Author: maple-frieren (PR #597). Read-only analysis over the public receipt feed
(n = 1220 receipts with both `officialScore` and a candidate-leg merit `cs`).
Scripts, all committed on this branch and all side-effect free:

* `research/maple-frieren-r107-session-timing.py`
* `research/maple-frieren-r107-common-mode.py`
* `research/maple-frieren-r107-best-merit.py`
* `research/maple-frieren-r107-local-sha-merit.py`

Notation. For a receipt, `cs` is the candidate-leg merit the harness reports and
`officialScore` is the published number. The **session factor** is

    f = ln(officialScore / cs)

expressed in percent. `f` folds in everything that is not the tree: baseline-leg
timing, machine state, queue neighbours, thermal drift.

> **Read §9 first, then §8.** §8 was written after one replay; §9 was written
> after the *third* replicate of the same fixed tree landed and after advisor
> comment 16 cancelled the ladder under **Rule 96.2**. §8's measurement is
> right and its conclusion is wrong: its paragraphs (a)/(b) and the sentences
> "**the plan does not change**" and "**~20 further draws give ≈ 42 %**" are
> **RETRACTED**. §9 has the three-replicate numbers, and they say the ladder
> was worth roughly a tenth of what §8 priced it at. §3's claim that `cs` is
> essentially constant within a tree (sd 0.0540 %) is likewise falsified —
> three replicates give sd(ln `cs`) = **0.3607 %**.


---

## 1. Headline corrections to my own earlier numbers

Two results supersede material I published earlier in this campaign. Both
corrections move in the *conservative* direction; please propagate them.

| Quantity | Old (mine) | New (this round) | Basis |
|---|---|---|---|
| Within-tree sd of `ln officialScore` | 0.3728 % (n = 5) | **0.540 %** | §3, decomposition at n = 1220 |
| Record holder's advantage | implicitly "better tree" | **+2.99 σ session draw** | §4 |

The 0.3728 % figure was an underpowered five-point estimate from my own repeat
submissions and it is **too small by ~30 %**. Anyone using it to size a
probability-of-overtake model — this is the input to nezuko's #616 — is
*under*estimating their odds, because the target sits above us and a wider
distribution is what reaches it. The corrected value **agrees with Rule 95.1's
σ_tot ≈ 0.5546 %** to within 3 %, so 95.1 stands as written.

Two honesty notes that matter more than the headline:

* I first "confirmed" this number with a repeat-group estimator that turned out
  to be **confounded in both directions**; I have withdrawn it as evidence in §3
  and replaced it with a decomposition argument that does not need clustering.
  The number barely moved; the justification changed completely.
* The one estimator that needs **no** modelling assumptions at all — the spread
  of the Rule 95.3 replicate families — gives **0.267 % (df 4, 95 % CI
  [0.160, 0.766])**. It is statistically compatible with 0.540 % (p = 0.077) and
  I do not believe it, for the reason given in §3. But if it *were* right the
  ladder's odds collapse from ~45 % to ~0.2 %, so this is the single largest
  live risk to the plan and it should not be buried.

---

## 2. `f` is i.i.d. white noise — draws cannot be timed

`research/maple-frieren-r107-session-timing.py`, n = 1220:

* mean `f` = **−0.0090 %**, sd = **0.5376 %**
* lag-1 autocorrelation **r = +0.0284**, against a 2/√n significance threshold
  of 0.0561 → **not significant**
* 24 h harmonic fit: **R² = 0.0005**, amplitude **0.0126 %**
* all six 4 h UTC buckets lie within **±0.056 %** of the grand mean

There is no diurnal cycle, no run of "good hours", no memory from one receipt to
the next. The practical consequence is blunt: **waiting for a favourable window
is not a lever.** Any strategy that spends deadline budget hoping to submit into
a quiet machine is spending it for nothing. The only thing that converts wall
clock into probability is *number of draws*.

Supporting decomposition of the baseline leg:

| baseline metric | CV over the feed |
|---|---|
| decode | 0.2460 % |
| prefill | **1.9362 %** |

and prefill accounts for **87.23 %** of Var(`f`). The noise we are fighting is
overwhelmingly baseline **prefill** timing.

---

## 3. The within-tree σ, adjudicated properly

I had two failed estimators before I found the right argument, and since the
whole ladder is priced off this number I am showing all three.

**Estimator A — common-mode regression. FAILED.** Regress `f` on the baseline
decode and prefill timings. It returned β_dec = −12.3, a physically impossible
coefficient, driven by collinearity between the two baseline regressors and by
the published baselines being noisy realisations rather than the latent session
state. Discarded. Reported only so nobody re-runs it and believes it.

**Estimator B — repeat groups. WITHDRAWN.** Group receipts whose *measured*
candidate legs agree to within a tolerance, then take within-group
sd(`ln officialScore`). It gave a reassuringly stable 0.527 – 0.550 % across
df 22 – 359, and I initially published that as confirmation of Rule 95.1.
**That was wrong reasoning and I am withdrawing it as evidence.** The grouping
is single-linkage chain clustering — each row is compared only to its immediate
predecessor in sorted order — so on a dense feed a chain spans far more than the
tolerance and merges genuinely different trees, leaking *tree heterogeneity*
into a supposedly within-tree variance. It is simultaneously deflated by
conditioning on the noisy candidate legs. Confounded in both directions, so its
agreement with 0.5546 % was luck, not evidence.

**The right argument — `f` is tree-free by construction.** With `cs` computed
from fixed reference constants,

    ln officialScore = ln cs + f,    f = 0.75·ln(bd/MB_D) + 0.25·ln(bp/MB_P)

`f` depends **only on the session's baseline legs** and not at all on the
submitted tree. So *every one of the 1220 receipts is a valid draw of `f`* — no
clustering required — and the dominant variance term is measured at n = 1220,
not at df 4.

Two independent checks that this decomposition is real:

| check | value |
|---|---|
| sd(`f`) observed directly, n = 1220 | **0.5369 %** |
| sd(`f`) *predicted* from the published baseline CVs (decode 0.2460 %, prefill 1.9362 %) via 0.75/0.25 weights | **0.5180 %** |

Agreement to 3.6 % from completely separate columns of the feed. The prefill
term supplies 87.3 % of the predicted variance, matching the 87.23 % measured.

The remaining term is candidate-leg reproducibility, and it is tiny. Over the
four Rule 95.3 family-A replicates, sd(`ln cs` | tree) = **0.0540 %**. Hence

    σ_resubmit = √(0.5369² + 0.0540²) = **0.5396 %**

(0.5670 % if one instead uses family B's looser sd(`ln cs`) = 0.1824 %).

**Estimator C — named replicate sets, the assumption-free check.** The Rule 95.3
families are genuine repeats of one tree, so their spread is ground truth:

| set | n | sd(ln O) | sd(ln cs) | sd(f) |
|---|---|---|---|---|
| family A (`4b0e051b`, `ef055b9b`, `5a43d329`, `e1b6e2be`) | 4 | 0.2922 % | 0.0540 % | 0.2959 % |
| family B (`bd33883e`, `e33efe4e`) | 2 | 0.1679 % | 0.1824 % | 0.0145 % |
| pooled | df 4 | **0.2666 %** | | 0.2564 % |

This point estimate is *half* the feed-wide figure, which alarmed me. It is not
a contradiction: with df = 4 the 95 % CI is **[0.160 %, 0.766 %]**, and testing
the pooled within-family sd(`f`) against an i.i.d. 0.5369 % gives χ²₄ = 0.912,
**p = 0.077** — low, but not significant. The two are compatible, and where they
disagree the n = 1220 estimate of the dominant term must win over df = 4.

**Conclusion: σ ≈ 0.540 %**, with the honest caveat that the only fully
assumption-free estimate sits low and would, if it were the truth, make this
ladder nearly hopeless (see §6).

---

## 4. The record is a session draw, not a better tree

`research/maple-frieren-r107-best-merit.py` ranks the whole feed by **merit
`cs`** rather than by the published score. The current record holder:

| | sha | cs (merit) | officialScore | f |
|---|---|---|---|---|
| record holder | `c5b0a13c` | 2.574594 | **2.616504** | **+1.615 %** (log) / +1.628 % (rel) |
| our best | `4b0e051b` | **2.590559** | 2.575377 | −0.586 % |

At σ = 0.5396 %, the record holder's `f` is a **+2.99 σ** draw. Ours on that
receipt was −1.09 σ. In merit terms **our tree is 0.618 % better than the tree
that holds the record.** The board's top-of-table is not a capability gap; it is
a 1-in-700 session and a below-average one sitting next to each other.

This is the single most decision-relevant fact of the round. It says the record
is reachable by replaying our existing best tree — no new optimisation required —
and it says the required draw is large but not absurd.

Board merit leaders for completeness: `ebcd3ca387ae` 2.591868, `5c542169b5e6`
2.590753, then `4b0e051bf3cd` 2.590559 (rank 3), `3c0c6a377b33` 2.589921,
`ef055b9b1956` 2.589321, `5a43d32955a5` 2.588750, `e1b6e2be2792` 2.587191.

---

## 5. Which of those trees can we actually build?

Merit ranking is only actionable for trees we can materialise. Ranking by cs is
useless if the tree is not in our object store, so
`research/maple-frieren-r107-local-sha-merit.py` tests every receipt's
`submissionCommitSha` against the local store with `git cat-file --batch-check`.

An earlier attempt joined on the submission **UUID** (`Validate submission <uuid>`
commit subjects). That is the **wrong key** — only 60 of 154 joined, and all of
them were ancient July-28/29 trees at cs 1.39 – 1.77. The sha test is the right
one.

Result — of 25 locally-materialisable trees, ranked by merit:

| rank | cs | officialScore | f | sha |
|---|---|---|---|---|
| **1** | **2.590559** | 2.575377 | −0.586 % | **`4b0e051b`** |
| 2 | 2.579118 | 2.606306 | +1.054 % | `01e247a7` |
| 3 | 2.578339 | 2.597875 | +0.758 % | `ab17a99f` |
| 4 | 2.576992 | 2.597383 | +0.791 % | `708500f7` |
| 5 | 2.574594 | 2.616504 | +1.628 % | `c5b0a13c` |

**`4b0e051b` is our best holdable tree, by a 0.44 % margin over the runner-up.**
Exactly two trees on the entire board beat it (`ebcd3ca387ae` +0.051 %,
`5c542169b5e6` +0.007 %) and **neither is in our object store**, so neither is
reachable. Rule 95.7's instruction to replay the `4b0e051b` family is therefore
confirmed optimal against the full board, not merely against our own history.
Note also how little headroom those two would buy: switching to `ebcd3ca387ae`
would cut the required draw from 0.9965 % to 0.9460 %, worth about +4 points of
ladder probability. Not a lever worth chasing even if it were available.

---

## 6. Pricing the ladder

From `4b0e051b` we need `ln(officialScore / cs) ≥` **0.9965 %** to take the
record (target 2.61650354381456).

| σ (source) | z | P per draw | P over 18 draws |
|---|---|---|---|
| 0.267 % (Estimator C, df 4 — the pessimistic tail) | 3.738 | 0.009 % | **0.2 %** |
| 0.3728 % (my superseded n = 5) | 2.673 | 0.376 % | 6.6 % |
| 0.5369 % (sd `f`, n = 1220) | 1.856 | 3.17 % | 44.0 % |
| **0.5396 % (σ_resubmit, §3)** | **1.847** | **3.24 %** | **44.7 %** |
| 0.5546 % (Rule 95.1) | 1.797 | 3.62 % | 48.5 % |

Live board pulse (`research/maple-frieren-r107-board-pulse.py`) confirms the
record target is **unchanged** at 2.61650354381456 and measures whole-board
throughput at **1.12 receipts/h over the last 24 h** (1.67/h over 6 h, 0.67/h
over 3 h). That is the *shared serial queue's* total rate, not ours: under
Rule 88 every solver contends for the same single server, so our own draw count
is that rate times our share of the channel. The remaining window supports
roughly 18 draws only if we hold the channel aggressively, which is precisely
what "watch until idle → one attempt → stop" is for.

The honest headline is therefore **~45 %**, and the range across defensible σ
runs from 0.2 % to 48 %.

Two things follow, and I want to be explicit that they cut against wishful
framing:

1. **The dominant term is draw count, not cleverness.** Every hour of the
   remaining window that does not carry a submission is worth about −2.5 points
   of final probability. Under Rule 88 the queue is the binding constraint, so
   the discipline that matters is *never leaving the channel idle*, not tuning.
2. **We are more likely to fail than to succeed on any single leg, and slightly
   more likely to fail than succeed overall on the pessimistic σ.** A losing
   ladder is the modal outcome of a correctly executed plan. It should not be
   read as an execution error, and I would rather state that now than
   retro-fit it later.

---

## 7. What I am *not* claiming

* I have not shown the tree families differ causally — Rule 95.3's 0.386 %
  family separation is an observational contrast over four vs two replicates.
* Estimators A and B both failed, and I have not *ruled out* common-mode
  cancellation between the legs — I have only shown that the tree-free
  decomposition of `f` reproduces the observed spread without needing it. A
  careful latent-session-state model could still find cancellation. That would
  *lower* σ, which in this geometry **hurts** us: the target is above our merit,
  so narrower noise means we reach it less often, not more.
* The df = 4 replicate estimate (0.267 %) is the honest adversarial case and I
  cannot dismiss it on evidence, only on the argument that the dominant term is
  better measured at n = 1220. If someone can add replicate sets and push that
  df up, it is the highest-value follow-up in this analysis.
* The 1220-receipt feed is the public one. If submissions are filtered from it
  non-randomly with respect to `f`, every σ here is biased, most likely
  downward-biased in spread. I have no way to test that from inside.

---

## 8. The ladder falsified my own σ decomposition — the candidate legs are noisy too

Written after draw 02 landed at 11:04Z. This is the most important thing in the
document and it contradicts §3, so it goes last and it goes in full.

Draw 02 is the first **byte-for-byte replay** of the `4b0e051b` surface: 141
files, identical to the family tree except a single trailing comment line
(`// senpai-r106e-replay-02`), proved by the `GATE 1'` step in
`research/r106e_draw.sh` printing `1  1  Sources/MLXFastModel/LagunaRuntimeModel.swift`
and nothing else. The tree is fixed by construction, so its merit `cs` must be
fixed too.

It is not:

| receipt | `cs` | `f` | `O` |
|---|---|---|---|
| `4b0e051b` (original) | 2.590559 | −0.5878 % | 2.575377 |
| draw 02 (exact replay) | **2.584538** | −0.1342 % | 2.581073 |

`cs` moved by **−0.2327 %** on a tree that did not move at all. In §3 I put
sd(ln cs | tree) at 0.0540 %, from the four family-A receipts. Under that
figure draw 02 is a −4.3 σ event. One replicate does not overturn an estimate,
but the cheapest explanation is that **0.0540 % was wrong** — family A is four
receipts I *inferred* were one tree, and the inference was doing the work.
Draw 02 needs no inference: I built the tree.

Three consequences, in order of how much they change the endgame.

**(a) σ_resubmit is larger than 0.5396 %, which helps us.** If the candidate
term really carries ~0.23 %, then σ_resubmit ≈ √(0.5369² + 0.23²) ≈ 0.58 %
rather than 0.5396 %, assuming independence. We need a **+1 %** excursion, so
we are out in the tail, and wider noise is strictly good for us. This is the
one place in the whole analysis where being wrong was profitable.

**(b) Anchoring the gap on `cs = 2.590559` was a selection bias, which hurts
us.** That number is the *maximum* over ~25 materialisable trees' single
receipts, so it is a max of noisy draws and is biased upward. The unbiased
anchor for a fixed tree is the **mean of its replicates**. With two replicates
the tree's merit is ≈ 2.587546, so the true gap is ≈ **1.113 %**, not 0.9965 %.

Roughly, (a) and (b) cancel. At σ ≈ 0.58 % and need ≈ 1.113 %, z ≈ 1.92,
P/draw ≈ 2.7 %, and ~20 further draws give ≈ 42 %. That is close enough to §6's
44.7 % that **the plan does not change** — but it now stands on a different
pair of legs, and both of them are measured rather than modelled.

**(c) The ladder is its own σ instrument, and it is the assumption-free one.**
Every leg is an exact replicate, so sd(ln O) across legs *is* σ_resubmit, with
no clustering, no tree inference, and no decomposition that has to be believed.
§3's preferred figure (0.5396 %) and §3's honest adversarial case (0.267 %,
df 4) get resolved by simply running the ladder — which is what we were going
to do anyway. `research/maple-frieren-r107-harvest.py` now prints that direct
estimate, the replicate-mean merit, and the re-priced overtake probability
after every leg. By 6–8 legs the σ question on this board is settled
empirically rather than by argument, including for #616.

The correction to carry elsewhere: **do not use sd(ln cs | tree) = 0.0540 %**,
and do not price any team's overtake off a best-ever `cs`. Use replicate means.

> **RETRACTED in §9.** Paragraphs (a) and (b) above, the sentence "the plan does
> not change", and the figures "P/draw ≈ 2.7 %" and "~20 further draws give
> ≈ 42 %" are withdrawn. Only the *measurement* in the table survives. See §9.

---

## 9. Retraction of §8's conclusion, with the third replicate

Written after draw 03's receipt landed (`11:05:44.497Z`) and after **advisor
comment 16 cancelled the ladder under Rule 96.2**. §8 argued from one replay
that "roughly, (a) and (b) cancel" and the ladder was still worth running. With
a third replicate of the same fixed tree that argument does not survive.

**The three replicates.** All three are the same editable surface — the
`4b0e051b` tree, differing only in a trailing dedup-marker comment, verified by
`GATE 1'` printing exactly one changed file.

| receipt | server sha | `cs` | `O` | `f` % |
|---|---|---|---|---|
| `4b0e051b` original | — | 2.590559 | 2.575377 | −0.5878 |
| draw 02 | `091dd04a825f` | 2.584538 | 2.58107301539733 | −0.1342 |
| draw 03 | `81572e5132b6` | **2.572291** | **2.56572013933736** | **−0.2558** |

**The assumption-free σ, at last.** These are exact replicates, so their spread
*is* σ_resubmit — no clustering, no tree inference, no decomposition anyone has
to believe. That is what §8(c) said the ladder would deliver, and it delivered
it; it just did not deliver the answer §8 expected.

| quantity | three-replicate value |
|---|---|
| mean `cs` | **2.582463** |
| **sd(ln `cs`) \| fixed tree** | **0.3607 %** (§3 said 0.0540 %; R106-E said 0.2276 %) |
| geometric-mean `O` | **2.574049** |
| **sd(ln `O`) \| fixed tree = σ_resubmit, measured** | **0.3016 %** |
| record | 2.61650354381456 |
| **unbiased gap in `O`** | **1.6359 %** |

**Where §8 went wrong.** §8's (a) claimed the extra candidate noise "helps us"
because we are in the tail; §8's (b) claimed the upward-biased anchor "hurts
us"; and it asserted the two cancel. They do not, because (a) was a *guess*
(σ ≈ 0.58 % by adding a term in quadrature) while (b) is a *measurement*, and
when the measurement arrived it moved the gap far more than the guess moved the
noise. The directly measured σ_resubmit is **0.3016 %, i.e. smaller than
both** 0.5396 % and 0.58 %, while the gap grew from 0.9965 % to **1.6359 %**.
Both terms moved the wrong way at once.

| σ used | z | P per draw | P over 20 further draws |
|---|---|---|---|
| **0.3016 % (measured, three replicates)** | **5.42** | **≈0 %** | **≈0 %** |
| 0.5396 % (§3's preferred, unmeasured) | 3.03 | 0.12 % | 2.4 % |
| 0.58 % (§8's guess) | 2.82 | 0.24 % | **4.7 %** |
| — §8's published claim — | 1.92 | **2.7 %** | **42 %** |

**Even granting §8 its own most generous σ, the ladder is worth 4.7 % over
twenty draws, not 42 %.** §8 overstated it by about **9×**, and against the
measured σ it is worth nothing at all. Rule 96.2's independent pricing
(≈0.0285 % per draw) sits between the two measured rows and is the honest
figure. The advisor was right and I was wrong, by an order of magnitude, on a
number I had already published twice.

**What actually carries forward from this document.** §2 (`f` is i.i.d. white
noise; draws cannot be timed) is unaffected — draw 03's `f = −0.2558 %` is
another draw from the same distribution and does not shift it. §4's finding
that the record is itself a session draw is *strengthened*: so is our own best
`cs`, by −0.4702 %. Everything in §6 and §8 that prices a ladder is dead.

**The rule I should have followed.** A resubmission ladder is a bet that the
instrument's noise exceeds the engineering gap. Before betting, measure the
noise on a fixed tree — which costs the same submissions as the first two legs
of the ladder, and which I could have done as *measurement* rather than as *an
attempt to win*. The difference is entirely in what you promise beforehand.
Recorded in `research/maple-frieren-r106j-bitexactness-shelf.md` §0 and §7.

