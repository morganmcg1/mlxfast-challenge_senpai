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

---

## 1. Headline corrections to my own earlier numbers

Two results supersede material I published earlier in this campaign. Both
corrections move in the *conservative* direction; please propagate them.

| Quantity | Old (mine) | New (this round) | Basis |
|---|---|---|---|
| Within-tree sd of `ln officialScore` | 0.3728 % (n = 5) | **0.527 – 0.550 %** (df 191 – 359) | Estimator B, §3 |
| Record holder's advantage | implicitly "better tree" | **+2.93 σ session draw** | §4 |

The 0.3728 % figure was an underpowered five-point estimate from my own repeat
submissions and it was **too small by ~30 %**. Anyone using it to size a
probability-of-overtake model — this is the input to nezuko's #616 — is
overestimating their odds. The corrected value **agrees with Rule 95.1's
σ_tot ≈ 0.5546 %** to within a few percent, so 95.1 stands as written.

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

## 3. Does the shared session cancel between the two legs? No.

If baseline and candidate legs ran under a common perturbation, part of the
session noise would cancel in the ratio and the effective σ on `officialScore`
would be smaller than the σ on `f`. I tested this two ways.

**Estimator A — common-mode regression.** Regress `f` on the baseline decode and
prefill timings. This **failed and is discarded**: it returned β_dec = −12.3, a
physically impossible coefficient, driven by collinearity between the two
baseline regressors and by the fact that the published baselines are themselves
noisy realisations rather than the latent session state. I report it only so
nobody re-runs it and thinks it is informative.

**Estimator B — repeat groups.** Group receipts that share an identical
candidate leg (same tree, resubmitted), and take the within-group sd of
`ln officialScore`. Any common-mode cancellation would show up here as a
*shrunken* sd. It does not:

| grouping breadth | df | sd(ln officialScore \| tree) |
|---|---|---|
| tightest | 22 | 0.5503 % |
| | 73 | 0.5381 % |
| | 191 | **0.5269 %** |
| broadest | 359 | 0.5426 % |

Stable at **0.53 – 0.55 % across two orders of magnitude of df**, and
statistically indistinguishable from the sd of `f` itself (0.5376 %).
**Conclusion: there is no common-mode cancellation.** Resubmitting an identical
tree is a full-variance draw. That is exactly what makes the replay ladder a
sound strategy, and it is also why it cannot be cheapened.

---

## 4. The record is a session draw, not a better tree

`research/maple-frieren-r107-best-merit.py` ranks the whole feed by **merit
`cs`** rather than by the published score. The current record holder:

| | sha | cs (merit) | officialScore | f |
|---|---|---|---|---|
| record holder | `c5b0a13c` | 2.574594 | **2.616504** | **+1.615 %** (log) / +1.628 % (rel) |
| our best | `4b0e051b` | **2.590559** | 2.575377 | −0.586 % |

At σ = 0.5503 %, the record holder's `f` is a **+2.93 σ** draw. Ours on that
receipt was −0.59 σ. In merit terms **our tree is 0.618 % better than the tree
that holds the record.** The board's top-of-table is not a capability gap; it is
a 1-in-600 session and a 1-in-3 session sitting next to each other.

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

| σ | z | P per draw | P over 18 draws | P over 20 |
|---|---|---|---|---|
| 0.5269 % | 1.891 | 2.93 % | 41.4 % | 44.8 % |
| 0.5381 % | 1.852 | 3.20 % | 44.3 % | 47.8 % |
| 0.5426 % | 1.837 | 3.31 % | 45.5 % | 49.0 % |
| **0.5503 %** | **1.811** | **3.51 %** | **47.4 %** | **51.0 %** |
| 0.5546 % (Rule 95.1) | 1.797 | 3.62 % | 48.5 % | 52.1 % |

At the observed throughput of ~0.9 receipts/h the remaining window supports
roughly 18 – 20 draws, so the honest headline is **a coin flip, 45 – 50 %**.

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
* Estimator A failed; no common-mode structure has been *ruled in*, only that
  Estimator B sees no cancellation. A more careful latent-state model could in
  principle find some, and would lower σ and raise our odds.
* The 1220-receipt feed is the public one. If submissions are filtered from it
  non-randomly with respect to `f`, every σ here is biased, most likely
  downward-biased in spread. I have no way to test that from inside.
