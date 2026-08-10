# r106-B Stage 0 preregistration — revert-residual confidence interval

**Author:** maple-nezuko · **Assignment:** `maple-r106-b-revert-residual-forensics`
· **Revision:** `r106-b-rev1` · **PR:** #616
**Base:** `8e8faf28635ad0bba81243ae98b56cd00eeac16d` (advisor-pinned)

This file is committed **before** any number in it is computed. It fixes the
estimand, the estimator, the variance pool, the degrees of freedom, the trimming
rule, and the stop/go criterion. Rule 40 / Rule 72. Nothing below may be revised
after the corpus is read; a later change must appear as a new, dated section that
explicitly labels itself post-hoc.

---

## 1. Estimand

The **revert residual** is the decode-side gap that remains after the frontier
recovered part of the round-95 revert cost:

```
R = (decode of frontier) − (decode of Arm R)
```

measured on two preregistered axes:

- **R_D** on raw decode, `D` = `officialMetrics.decode` in µs/step;
- **R_T** on the prefill-corrected axis, `T = D − 4P`, `P` = `officialMetrics.prefill`
  in µs/token (Rule 58's `T`).

The two arms are identified **strictly by `submissionCommitSha`**, never by
`solverUsername`, never by receipt id, and never by branch name:

| arm | `submissionCommitSha` |
|---|---|
| frontier | `bd33883eb89209c9714c8c570e399613ecbaa848` |
| Arm R | `ef055b9b1956e8056267972308fd7deddd89649d` |

If either sha resolves to more than one receipt in the frozen corpus, the arm's
value is the **arithmetic mean** of its receipts on that axis and its variance is
divided by its own `n`. If either sha resolves to zero receipts, the outcome is
**N-INSTRUMENT** and Stage 0 reports a blocker, not a number.

## 2. Estimator

Both arms are single-draw (the platform de-duplicates byte-identical archives, so
a tree normally admits one receipt; see #576). The estimator is therefore the
difference of two independent means with a **pooled external variance**:

```
SE(R) = sigma_hat * sqrt(1/n_frontier + 1/n_ArmR)
CI_95 = R  ±  t(0.975, dof) * SE(R)
```

`sigma_hat` is the pooled **within-identical-code** standard deviation of the axis
in question, and `dof` is the degrees of freedom of that pool. Student-`t`, not
normal, because `dof` is small. Two-sided, alpha = 0.05.

`R` itself is **not** re-estimated from a model; it is the plain arm difference,
so that the number is comparable to the campaign's published 19.41 / 20.15.

## 3. Variance pool (this is the part that must not move)

**Replicate group.** A *replicate group* is the set of receipts sharing one
identical `submissionCommitSha`. Identical sha ⇒ identical submitted bytes ⇒ any
spread within the group is pure measurement noise. This is the only
identical-code definition used; no note text, no branch, no tree inference.

**Eligibility.** A receipt enters a group iff all of:

1. `officialMetrics.decode` and `officialMetrics.prefill` are both present, finite
   and strictly positive;
2. the receipt has a resolvable creation timestamp (`createdAt`, else
   `officialMetrics.timestamp`);
3. the receipt is not itself one of the two arm receipts named in §1
   (an arm receipt may not contribute to the variance that tests it).

A group is eligible iff it has `n_g >= 2` eligible receipts.

**Primary pool — PP-ALL (no trimming).** All eligible groups.

```
sigma_hat^2 = sum_g sum_i (x_gi - xbar_g)^2  /  sum_g (n_g - 1)
dof         = sum_g (n_g - 1)
```

`dof` is whatever `PP-ALL` yields; it is *defined* here, not chosen after
inspection. No group is dropped for being noisy, for being old, for being
another student's, or for disagreeing with the desired answer. **PP-ALL is the
gate.** It is the conservative choice, and the gate's null-favouring outcome
(N-0) is a full-credit result, so conservatism costs nothing here.

**Sensitivity S1 — PP-TRIM.** `PP-ALL` minus any group whose within-group
`sd(P)` exceeds `5 µs/token`. This threshold is fixed now and is chosen to
reproduce the campaign's published trimmed pool (which excluded exactly one group
at `sd(P) = 13.49 µs/token`) so that my `sigma_hat` is comparable to the
`dof = 14`, `sd(D) = 11.682`, `sd(T) = 12.079` figures already in the research
state. Reported, never decisive.

**Sensitivity S2 — day-decomposed variance (the new work).** For each eligible
group, partition its receipts by UTC calendar day of the resolved timestamp. Fit
the one-way nested decomposition

```
x_gdi = mu_g + a_gd + e_gdi ,   Var(a_gd) = sigma_across^2 ,  Var(e_gdi) = sigma_within^2
```

by the standard ANOVA method of moments on the pooled sums of squares:

- `SS_within  = sum_{g,d} sum_i (x_gdi - xbar_gd)^2`, `dof_within = sum_{g,d} (n_gd - 1)`
- `SS_across  = sum_{g,d} n_gd (xbar_gd - xbar_g)^2`, `dof_across = sum_g (d_g - 1)`
- `sigma_within^2 = SS_within / dof_within`
- `sigma_across^2 = max(0, (MS_across - sigma_within^2) / nbar)` with `nbar` the
  mean day-cell size, floored at zero (Rule: negative variance components are
  reported as zero and flagged, never as negative).

S2 exists to test a specific published claim: the campaign's original power note
observed that the four pre-revert receipts span only `4893.7 - 4900.5` µs/step
(range `6.8`, `sd ≈ 3.3`, `≈ 0.067 %`), which is **implausibly tight** if the
identical-code `sd(D)` really is `11.7 - 14.4 µs`. For `n = 4` from a normal with
`sigma = 11.7`, the expected range is `≈ 2.06 sigma ≈ 24 µs`. Either those four
were drawn from a correlated session (`sigma_within << sigma_across`) or the
pooled `sigma` is inflated by across-day drift. S2 measures which.

**Session-matched CI (S2b).** Only if the two arm receipts of §1 fall on the
**same UTC day**, additionally report the CI computed with
`sigma_hat = sigma_within` and `dof = dof_within`.

## 4. Stop / go criterion — declared now

Let `CI_PP-ALL(R_D)` and `CI_PP-ALL(R_T)` be the two primary intervals.

- **N-0 fires** iff *either* primary interval covers zero. Then Stage 0 is
  terminal: I publish "there is nothing to attribute", I do **not** run Stage 1
  or Stage 2, and the residual is retired as a campaign phantom. This is the
  full-credit outcome named in the assignment.
- **Proceed to Stage 1/2** iff **both** primary intervals exclude zero.
- The sensitivities S1, S2, S2b **cannot** move the gate. If S1 or S2b excludes
  zero while `PP-ALL` covers it, the finding is reported as *"the residual is not
  robust to the choice of variance pool"*, which is itself a null verdict about
  the residual's evidential status, and the run still stops at Stage 0. Lifting
  Stage 1/2 on a sensitivity would require a new assignment revision.
- **N-INSTRUMENT** fires if the corpus cannot be pulled, or an arm sha has zero
  receipts. Then I report the blocker precisely and do not substitute a stale
  corpus number for a fresh one.

## 5. What Stage 0 explicitly does not claim

- No absolute per-kernel µs attribution is quoted from any withdrawn source
  (Rule 82). The campaign has already retracted "20.15 µs/step of missing
  microseconds" as a *priced* quantity at `z ≈ 1.0 - 1.2`; Stage 0 re-derives the
  interval, it does not resurrect the point estimate.
- `L`, the session baseline lottery, is not used. All arithmetic is on `cs`-side
  candidate metrics (`decode`, `prefill`) only, because `L` carries zero candidate
  information.
- No `--local-iterate` delta appears anywhere in the chain (Rule 86).
- `ns`-pinned constants (`NORM_DECODE = 0.013890`, `NORM_PREFILL = 0.0003845`) are
  not mixed with `cs`-pinned constants (`MB_D = 0.013855009542`,
  `MB_P = 0.000372473193`).

## 6. Artifacts this stage must leave behind

- `research/nezuko_r106b_pull_corpus.py` — read-only `GET` corpus puller that
  retains `submissionCommitSha`, `note`, `createdAt` and the full
  `officialMetrics` block. Existing `advisor_r103_freeze_corpus.py` discards
  `submissionCommitSha`, which is the exact key §1 requires, so a new puller is
  needed rather than a rebuild of shared scaffolding (Rule 58 respected: the
  analysis reuses `advisor_r105_ladder_monitor.py` conventions).
- A frozen corpus JSON under `research/artifacts/` with its sha256 and byte size
  recorded (Rule 75).
- `research/nezuko_r106b_stage0_ci.py` — the estimator, implementing exactly §2/§3.
