# r103-D rung 1 — preregistration

Written and committed **before** any residual estimate was computed. Nothing in
this file was chosen after seeing a rung-1 number. Rung 0 (provenance) was
already complete when this was written; its outcome is stated below only
because it determines whether rung 1 runs at all.

Corpus: `/tmp/r103d-subs-raw.json`, pulled read-only via
`research/fern_r103d_pull.py` (`GET /api/submissions`, no receipt created).
1,771 rows; 1,205 carry `officialMetrics`. The assignment's "1,204" is
reconciled in the report.

Price constants (ours, per the assignment): decode `0.015228 %/µs-step`,
prefill `0.3794 %/ms`, `1 % of cs = 65.67 µs/step`.

## 0. What rung 1 is trying to settle

The advisor's r103 tree reports a composed-vs-Arm-R decode residual of about
19 µs/step. Two things are unknown: (a) whether that number survives a proper
noise model, and (b) how wide its confidence interval actually is. Rung 1
estimates the residual and its 95 % CI from the full receipt corpus.

## 1. Unit of analysis

One official receipt with `officialMetrics != null` and `error == ''`. Each
receipt is a **paired** measurement: it carries both the candidate timing
(`decode_seconds_per_token`, `prefill_seconds_per_token`) and the
same-session baseline timing (`baseline_decode_seconds_per_token`,
`baseline_prefill_seconds_per_token`). Pairing is the whole reason a usable
noise model exists.

## 2. Outcome variables

- `d_c = decode_seconds_per_token * 1e6` (candidate, µs/step)
- `d_b = baseline_decode_seconds_per_token * 1e6` (baseline, µs/step)
- `y = ln(d_c) - ln(d_b)` — the log decode ratio, i.e. `-ln(decode_speedup)`.
  `y` is the preregistered primary outcome because it is the quantity `cs`
  is actually built from, and because the paired baseline cancels
  session-level drift.
- Secondary: `ln cs`, recomputed from
  `ln cs = X - 0.75 ln(cand_dec) - 0.25 ln(cand_pre)` with
  `X = -5.1831677111`, checked against `officialScore`.

## 3. Effect of interest and nuisance structure

Effect of interest: **tree identity**. Two reference trees, both verified
byte-identical at rung 0 over the 97-entry `editablePaths` surface:

- Arm R tree = organizer commit `ef055b9b1956e8056267972308fd7deddd89649d`
- composed frontier tree = organizer commit `bd33883eb89209c9714c8c570e399613ecbaa848`

Nuisance factors, in the order they will be handled:

1. **Session** (the baseline draw). Absorbed by pairing: `y` is a
   within-session contrast.
2. **Day** (`officialMetrics.timestamp`, UTC date). Entered as a fixed
   effect in the day-adjusted variant.
3. **Submitter** (`solverUsername`). Reported as a robustness split only.

## 4. Noise model — stated before the estimate

The corpus contains a fixed-code measurement repeated 1,205 times: the
**baseline**. Therefore:

- `sigma_b = sd(ln d_b)` over all valid receipts is a direct, n>1000 estimate
  of the session-to-session measurement noise of one fixed tree.
- `rho = corr(ln d_c, ln d_b)` estimates how much of that noise is shared
  between candidate and baseline within a session.
- `Var(y) = Var(ln d_c) + Var(ln d_b) - 2 rho sd(ln d_c) sd(ln d_b)`.

`sd(y)` computed **within a single verified tree** is the irreducible
per-receipt noise on the quantity of interest. That within-tree `sd(y)`, not
the corpus-wide spread, is what sets the CI. If a tree has `n` receipts, the
standard error of its mean `y` is `sd(y)/sqrt(n)`.

Residual estimator:

```
residual_log   = mean(y | composed) - mean(y | Arm R)
se(residual)   = sqrt( s_composed^2/n_composed + s_ArmR^2/n_ArmR )   (Welch)
```

converted to µs/step at the Arm-R mean candidate decode:
`residual_us = (exp(residual_log) - 1) * mean(d_c | Arm R)`.

95 % CI: Welch-t interval on `residual_log`, endpoints mapped through the same
conversion. Cross-check: a two-sided permutation test on tree labels
(20,000 shuffles) and, when `n` per tree is small, a bootstrap percentile
interval (20,000 resamples). All three are reported; the Welch interval is the
headline.

## 5. Identifying which receipts belong to which tree

`submissionCommitSha` is unique per receipt (each submission gets its own
`yukon-autoresearch[bot]` validation commit), so it cannot group receipts by
tree on its own. Trees are grouped by **verified content**:

- Primary: for each candidate commit, fetch the organizer tree
  (`?recursive=1`, cached) and compare blob SHAs over the 97 editable paths,
  exactly as rung 0 did. Two receipts are same-tree iff every editable blob
  SHA matches.
- The unauthenticated GitHub API budget is 60 requests/hour, so tree fetches
  are restricted to the candidate commits that plausibly carry the two
  reference trees, selected by `officialScore` and `note`, **not** by their
  timing values.

Selection of which commits to resolve is therefore made on score/note metadata
before any `y` is computed for them.

## 6. Preregistered nulls

Each is a first-class result. If one fires, rung 1 stops there and the report
says so.

- **N-1 — provenance unverified.** Rung 0 already ran: N-1 **does not fire**.
  Both reference trees are cryptographically verified byte-identical to local
  twins over the editable surface.
- **N-2 — the residual CI includes zero.** Then the 19 µs/step figure is not
  distinguishable from measurement noise and rung 2 does not run.
- **N-3 — the two reference trees have too few receipts to estimate a
  residual.** Concretely: fewer than 2 verified receipts on either tree, so no
  within-tree variance is estimable and no CI can be formed. Reported as
  "underpowered", not as "no effect".
- **N-4 — the corpus-wide noise model is inconsistent with the within-tree
  noise.** Fires if within-tree `sd(y)` and the corpus-implied `sd(y)` from
  §4 differ by more than 2x in either direction, which would mean the pairing
  assumption is wrong.
- **N-5 — the `sigma(cs) <= 0.228 %` vs `sigma(cand_dec) = 0.2939 %`
  tension is a bug, not a real anticorrelation.** Preregistered
  discriminator: if `rho = corr(ln d_c, ln d_b) > 0` at a level sufficient to
  make `Var(ln cs)` (propagated through
  `ln cs = X - 0.75 ln d_c - 0.25 ln p_c`, using the *speedup* form actually
  scored) come out below `Var(ln d_c)`, the tension is **real** and N-5 does
  not fire. If the propagated variance cannot be reconciled with the observed
  `sd(ln officialScore)` to within 20 % relative, N-5 **fires** and the
  reported `sigma` values are declared unsafe to reuse.

## 7. Rung 2 (conditional, kept short)

Runs only if N-2 does not fire. Contents, fixed now:

1. Split the residual into its decode and prefill contributions and restate
   each in µs/step and in % of `cs` using our price constants.
2. State the power of frieren's `+-0.43 µs/step` census: the `n` per tree
   needed for a 95 % CI half-width of 0.43 µs/step at the measured
   within-tree `sd(y)`.

Nothing else.

## 8. Constraints honoured

Zero receipts (read-only `GET` only). Zero bytes written under `Sources/`.
Existing scripts reused where they apply; rule-83 archive grep run before any
new analysis file was written.
