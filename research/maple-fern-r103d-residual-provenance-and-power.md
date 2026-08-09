# r103-D — residual provenance and power

**The composed-vs-Arm-R residual on the harness's true per-step decode work
`T = D − 4P` is +20.1 µs/step, 95 % CI [−12.3, +52.6] µs/step, and the
reference-tree provenance is *verified* (cryptographically, by git blob SHA
over all 97 `editablePaths` entries).**

On the raw reported decode figure `D` the same residual is **+19.4 µs/step,
95 % CI [−11.6, +50.4]**. Both outcomes agree; `T` is the one the advisor asked
for (feedback `r103-d-fb2`) and is the one this report leads with.

Preregistered null **N-2 fires on both outcomes**: each CI includes zero, so
rung 2 does not run. The ~20 µs/step figure is a real point estimate but it is
a **1.52 σ** observation built from one receipt per arm, and one receipt per
arm cannot resolve anything smaller than **26.0 µs/step** on `T`
(24.8 µs/step on `D`).

**The refit changes one downstream conclusion.** On `D` the control→Arm R
contrast (−31.5 µs/step, CI [−62.5, −0.6]) excluded zero; on `T` it does not
(−30.1 µs/step, CI [−62.6, +2.4]). After the refit **no contrast in the corpus
survives its own CI.** See
[the `T = D − 4P` refit](#the-t--d--4p-refit-advisor-feedback-r103-d-fb2).

Constraints honoured: zero receipts created (read-only `GET /api/submissions`
and unauthenticated `api.github.com` only), zero bytes written under
`Sources/`. Rung-1 specification committed in `3f86e0b` **before** any estimate
existed (`research/maple-fern-r103d-rung1-preregistration.md`).

---

## Rung 0 — provenance: VERIFIED (N-1 does not fire)

The receipt API carries **no digest of the candidate source archive**
(`harness_hash`, `weights_hash`, `golden_hash` describe the harness, weights
and goldens — not our tree). The archive's prior conclusion was that receipt
SHAs are unresolvable locally (`research/frieren-pr35-r5a-certificate.md:468`).

That conclusion is **wrong, and this is the reusable result of rung 0.** Every
`submissionCommitSha` *is* a real public commit in `Layr-Labs/mlxfast-challenge`,
authored by `yukon-autoresearch[bot]` with message `Validate submission <uuid>`
and parent `c5b0a13c`. It is fetchable unauthenticated, so a receipt can be
tied to a tree by content rather than by trust:

```
research/fern_r103d_provenance.py <official-sha...> -- <local-rev...>
```

It fetches the organizer tree (`?recursive=1`, cached), restricts to the 97
`editablePaths` entries, and compares **git blob SHAs** against
`git ls-tree -r`. Result:

| official commit | receipt | cs | local twin | editable-surface diff |
| --- | --- | --- | --- | --- |
| `ef055b9b` | `7ce1262d` Arm R | 2.589321 | `30f752df` | **0 — byte-identical (141/141)** |
| `bd33883e` | `e08d759f` composed | 2.582286 | `e17bdeb` (merge #565) | **0 — byte-identical (142/142)** |
| `e33efe4e` | `59bd72a3` control | 2.575633 | `c6c66344` | **0 — byte-identical** |
| `5a43d329` | `83fd2642` Arm F | 2.588750 | `6ada66c9` | **0 — byte-identical** |
| `4b0e051b` | `25e1f18e` **best ever** | 2.590559 | **none** | 1 file vs `ef055b9b` |

Both trees behind #571/#572 are verified. Three caveats that matter:

1. **Our assignment base `0f6862d0` is not the measured composed tree.** It
   differs from `bd33883e` by exactly one editable file,
   `Sources/MLXFastModel/LagunaRuntimeModel.swift`. Any diff #571/#572 present
   against this base is one file off what the M5 actually timed.
2. **The best-ever receipt `25e1f18e` has no twin in our fork.** That tree
   exists only in the organizer repo, one `LagunaRuntimeModel.swift` from Arm R.
3. **Composed-vs-Arm-R is not a small diff:** 29 files differ, plus
   `LagunaRuntimeLayers.swift` (Arm-R only) and `AffineMetadataCoding.swift` /
   `TiedHeadMetadataCoding.swift` (composed only) — **32 surface differences.**
   Control → composed is 27 differing files, more than "R1 + R2" implies.

---

## Rung 1 — the residual and its CI

Corpus: 1,771 rows, **1,205** with `officialMetrics`, all 1,205 usable. (The
assignment's 1,204 was the advisor's earlier pull; one receipt has landed
since.) Identity `score = cs · L` verified on all 1,205, worst relative error
`3.0e-08`, so `X = −5.1831677111`, `MB_D`, `MB_P` are all confirmed.

### Why n = 1 per arm is forced

**The platform deduplicates by archive content.** A byte-identical resubmit is
refused with `Submission already exists`
(`research/tanjiro-m5-calibration-note-B.md:19-35`). The corpus confirms it: over
1,205 receipts there are **1,205 distinct `(cand_dec, cand_pre)` pairs and zero
repeats**. A tree therefore gets exactly one measurement, and the residual is
irreducibly a **difference of two single receipts**. Its uncertainty must come
from an external noise model, never from within-arm replication.

### The noise model (within-tree, pooled over 3 compile-identical triplets)

Reusing `research/maple-fern-pr137-triplet-cv.py` (rule 58), extended with the
third triplet from `research/maple-fern-pr40-r2-instrument.md`. All 9 receipts
are present in the corpus; 6 dof.

| statistic | pooled within-tree σ | t1 | t2 | t3 | corpus-wide adjacent-pair σ |
| --- | --- | --- | --- | --- | --- |
| `cand_dec` (`D`) | **0.183 %** | 0.168 | 0.222 | 0.151 | 0.456 % |
| `cand_pre` (`P`) | 0.213 % | 0.260 | 0.091 | 0.245 | 0.373 % |
| `T = D − 4P` | **0.227 %** | 0.238 | 0.253 | 0.183 | — |
| `base_dec` | 0.271 % | 0.246 | 0.239 | 0.320 | 0.244 % |
| `base_pre` | 2.578 % | 2.358 | 2.552 | 2.805 | 2.020 % |
| `cs` | **0.135 %** | 0.076 | 0.180 | 0.129 | 0.436 % |
| `officialScore` | 0.654 % | 0.635 | 0.470 | 0.810 | 0.822 % |

`σ(cand_dec) = 0.183 %` at 4 893.7 µs/step is **9.0 µs/step per receipt**, so a
two-receipt difference carries **se = 12.7 µs/step**, and `t95(6) = 2.447`.

### The estimate

```
Arm R      4893.7 us/step   ->   composed  4913.1 us/step
residual   +19.4 us/step,  95% CI [-11.6, +50.4],  |t| = 1.53
cs         2.589321 -> 2.582286 = -0.2721%,  95% CI [-0.7400, +0.1959]%
```

**N-2 fires.** Priced through our decode constant the cs delta is −17.9 µs/step,
agreeing with the direct +19.4 µs/step to well within noise — the two routes
are consistent, but neither is separable from zero.

### The `T = D − 4P` refit (advisor feedback `r103-d-fb2`)

`decode_seconds_per_token = (S + 128·T)/128` with `S = 512·P` is an exact
harness identity, so the reported `D` contains **four whole prefills** of
non-decode work. The advisor is right that `T = D − 4P` is the outcome that
isolates real per-step decode work, and `research/fern_r103d_rung1.py` now
carries `T` through the identical pooled-σ machinery (section 5T).

```
Arm R      D=4893.712  4P=752.171  T=4141.541 us/step
composed   D=4913.117  4P=751.427  T=4161.690 us/step
T residual +20.1 us/step,  95% CI [-12.3, +52.6],  |t| = 1.52
```

Three things the refit settles:

- **The advisor's point estimate reproduces exactly** (+20.149 µs/step,
  matching `research/advisor_r103_T_decomposition.py`), and so does the
  closed-form rung-2 split of the cs gap: decode term −0.2968 %, prefill term
  +0.0247 %, net −0.2721 %. No fit is needed for that split.
- **`σ(T)` is much quieter than predicted.** Advisor predicted 0.345 %
  (14.28 µs/step) by propagating `σ(D)` and `σ(P)` as independent. Measured
  pooled within-tree `σ(T) = 0.227 %` (9.4 µs/step) — 1.52× smaller, because
  `D` and `P` are *not* independent within a tree. That is good news for power
  and it is why the T-CI (±32.5) is only slightly wider than the D-CI (±31.0)
  rather than 1.5× wider.
- **N-2 still fires.** Moving to the better outcome variable does not rescue
  the residual: the CI still spans zero, and MDD at n=1/arm is 26.0 µs/step
  against a 20.1 µs/step effect. Rung 2 stays closed.

### All pairwise contrasts (this is the useful part)

Both outcomes, so the advisor can see exactly where the refit changes a verdict.

| A | B | Δ`D` µs/step | 95 % CI(`D`) | Δ`T` µs/step | 95 % CI(`T`) |
| --- | --- | --- | --- | --- | --- |
| control `59bd72a3` | composed `e08d759f` | −12.1 | [−43.1, +18.9] | −9.9 | [−42.4, +22.6] |
| control | Arm R `7ce1262d` | **−31.5** | **[−62.5, −0.6]** | −30.1 | [−62.6, +2.4] |
| control | Arm F `83fd2642` | −26.3 | [−57.3, +4.7] | −23.1 | [−55.6, +9.4] |
| control | best `25e1f18e` | **−31.1** | **[−62.1, −0.2]** | −28.1 | [−60.6, +4.4] |
| composed | Arm R | −19.4 | [−50.4, +11.6] | −20.1 | [−52.6, +12.3] |
| composed | best | −19.0 | [−50.0, +12.0] | −18.1 | [−50.6, +14.4] |
| Arm R | Arm F | +5.2 | [−25.8, +36.2] | +7.0 | [−25.5, +39.4] |
| Arm R | best | +0.4 | [−30.6, +31.4] | +2.0 | [−30.5, +34.5] |

Conclusions the advisor can act on:

- **The sign flip matters more than the headline.** On `D`, control → Arm R
  (−31.5) and control → best (−31.1) both excluded zero; on `T` **neither
  does**. Part of the revert's apparent decode win was borrowed from prefill:
  Arm R's `4P` is 752.2 µs vs the control's 753.6 µs, and returning that 1.5 µs
  of prefill credit, together with the slightly wider `σ(T)`, costs the
  contrast its significance. **After the refit no contrast in this corpus
  survives its own 95 % CI.**
- **The composed-vs-Arm-R residual is not resolvable either way.** Composed
  recovered 9.9 of the 30.1 µs/step on `T` (12.1 of 31.5 on `D`); the ~20
  µs/step shortfall is a plausible point estimate with no statistical support
  at n=1.
- **`25e1f18e` is not a faster decode tree.** It beats Arm R on `cs` by
  +0.048 % while its `T` is +2.0 µs/step (|t| = 0.15) — the gain is in prefill
  (0.1876 vs 0.1880 ms), not decode. The refit strengthens this: on `T` its
  advantage over Arm R is even smaller than on `D`.

---

## The preregistered outcome `y` was the wrong choice — reported honestly

The prereg named `y = ln(cand_dec) − ln(base_dec)` primary, reasoning that the
same-session baseline would cancel drift. **It does the opposite.**

```
within-tree sigma(y)        = 0.3479 %
within-tree sigma(cand_dec) = 0.1830 %   <- 1.90x quieter
within-tree sigma(cs)       = 0.1352 %   <- quietest
```

Pairing *inflates* the noise 1.90× because the **baseline arm (0.271 %) is
noisier than the candidate arm (0.183 %)**, and cross-arm correlation is ≈0
(archive: `corr(cand_dec, base_dec) = −0.111`, n=1033). There is no common mode
to cancel. On `y` the residual is +0.4174 % [−0.7867, +1.6214] — the same null,
three times wider. The archive's standing rule is confirmed: *never use a
ratio's apparent stability as a noise floor.*

The headline outcome `T = D − 4P` is likewise **post-hoc**, adopted on advisor
feedback `r103-d-fb2` after the estimate existed. This is only defensible
because all three candidate outcomes (`y`, `D`, `T`) reach the *same* verdict —
N-2 fires — so the choice cannot be accused of shopping for significance. It
moves in the opposite direction: `T` **removes** the two contrasts that `D`
called significant.

---

## Preregistered nulls — adjudication

| null | verdict | evidence |
| --- | --- | --- |
| **N-1** provenance unverified | **does not fire** | blob-SHA identity, 141/141 and 142/142 |
| **N-2** residual CI includes zero | **FIRES on both outcomes** | `T`: [−12.3, +52.6] µs/step, \|t\| = 1.52; `D`: [−11.6, +50.4], \|t\| = 1.53 |
| **N-3** too few receipts | does not fire literally | both receipts exist; but n=1/arm by dedup is the binding limit |
| **N-4** noise model inconsistent | **does not fire** | `base_dec` is fixed code in every receipt: within-tree 0.271 % vs corpus 0.244 % = 1.11×; `base_pre` 1.28× |
| **N-5** σ(cs) < σ(cand_dec) is a bug | **does not fire** | it is arithmetic — see below |

### N-5 in full: the tension is arithmetic, not a bug and not anticorrelation

`ln cs = X − 0.75 ln cand_dec − 0.25 ln cand_pre`. The decode leg carries
weight **0.75**, so `0.75 × σ(cand_dec)` is the floor:

```
0.75 * 0.1830%                          = 0.1372%
sqrt((0.75*0.1830)^2 + (0.25*0.2132)^2) = 0.1472%   (independent legs)
observed sigma(cs)                      = 0.1352%   ratio 0.919
```

σ(cs) < σ(cand_dec) **must** hold whenever the prefill leg is small, purely
because the exponent is below 1. No anticorrelation is required. The residual
8 % shortfall below the independent-leg prediction is a mild decode/prefill
cancellation, consistent with the archive's n=3 triplet finding, and it is not
load-bearing. Neither of our reported σ values is a bug.

The advisor asked for the measurement that closes this properly — σ(cand_pre)
and corr(cand_dec, cand_pre) — instead of the algebra. Measured:

| quantity | value |
| --- | --- |
| within-tree σ(cand_pre) | **0.213 %** (advisor's independence solve wanted ≈0.233 %) |
| within-tree corr(`D`, `P`) | **−0.230**, Fisher 95 % CI **[−0.776, +0.513]** (n = 9, dof = 6) |
| predicted from the 4P coupling alone | **+0.152** |
| advisor `r103-d-fb2` prediction | **+0.122** |
| corpus-wide corr(`D`, `P`) | **+0.943** (n = 1,205) |
| within-tree corr(`T`, `P`) | **−0.384** |

**The correlation CI cannot discriminate the competing hypotheses.** It spans
−0.776 to +0.513 and therefore contains the advisor's +0.122, our 4P-derived
+0.152, and exact independence 0.000 alike. Nine receipts across three triplets
is simply not enough to measure a correlation; the honest statement is that all
three are consistent with the data and none is confirmed. Note also that the
*direct* consequence of the 4P coupling — corr(`T`, `P`) = −0.384 — is what
actually makes `σ(T) = 0.227 %` smaller than the independent-propagation
prediction of 0.345 %, so the coupling is doing real work even though its
correlation coefficient is not resolvable.

The **+0.943 corpus-wide** figure is *not* evidence of noise coupling: it is
between-tree quality (a slow tree is slow on both axes, and the corpus spans
every solver, mean 6,830 µs/step decode vs our 4,894). The 4P share is
`4 × 223.1 / 6,830 = 0.131` corpus-wide and `4 × 188.0 / 4,894 = 0.154` on our
own trees. Nothing exotic is needed.

**But the numbers in the assignment are the wrong ones for this question.** The
quoted `σ(cand_dec) = 0.2939 %` and `σ(cs) ≤ 0.228 %` are **mixed-code**
corpus-wide figures: they include real differences between different people's
trees. The within-tree values are 0.183 % and 0.135 %. Use the latter for any
same-instrument comparison.

I could not reproduce the archive's `σ(cand_dec) ≤ 0.2920 %` from the current
corpus at all — the adjacent-pair estimator with the same half-normal constant
now gives:

| subset | n | σ_single |
| --- | --- | --- |
| all adjacent pairs | 1204 | 0.4559 % |
| same solver | 180 | 0.3301 % |
| same solver + same day | 173 | 0.3299 % |

None is 0.292 %. The corpus has grown and diversified since r93; **`0.2920 %`
should be retired as a live constant.**

---

## Power (the assignment's framing question)

At the measured within-tree `σ(cand_dec) = 9.0 µs/step`, for a 95 % CI
half-width `h` the requirement is `n = 2(1.96 σ / h)²` receipts **per arm**:

| target half-width | receipts per arm |
| --- | --- |
| **±0.43 µs/step** (frieren's census) | **3,332** |
| ±5 µs/step | 25 |
| ±10 µs/step | 7 |
| ±19 µs/step | 2 |
| minimum detectable difference at n=1/arm, on `D` | **24.8 µs/step** |
| minimum detectable difference at n=1/arm, on `T` | **26.0 µs/step** |

**Frieren's ±0.43 µs/step census precision is unreachable on the receipt
channel** — it would take 3,332 receipts per arm, and each costs a distinct
archive (dedup forbids free repeats). Receipt-channel and census-channel
numbers are measuring at precisions three orders of magnitude apart and must
never be compared as if commensurable.

---

## Two corrections for the record

1. **The assignment's prefill price is retired.** It specifies
   `prefill 0.3794 %/ms`; `research/CURRENT_RESEARCH_STATE.md:544` says the
   current value is **`0.2592 %/ms`** and that *"the older prefill price
   0.3794 %/ms is retired"*. Decode `0.015228 %/µs-step` and
   `1 % of cs = 65.67 µs/step` are current and were used here. No conclusion
   above depends on the prefill price.
2. **`research/advisor_r103_our_commits.py` reads a field that does not
   exist.** It uses `r.get("commitSha") or r.get("commit")`; the top-level
   field is **`submissionCommitSha`** (`commit` exists only inside
   `officialMetrics`). It silently maps every receipt to `None`.

---

## What this does and does not license

- The composed tree being ~20 µs/step behind Arm R is **unfalsified, not
  established**, on either `T` or `D`. Do not spend a round hunting a 20 µs/step
  mechanism on the strength of this number alone.
- **The control → Arm R gap is no longer established either.** On the raw `D`
  it looked safe (−31.5, CI [−62.5, −0.6]); on the advisor's preferred `T` it is
  −30.1 with CI [−62.6, +2.4]. This supersedes the "the revert damage is real"
  recommendation in the first submission of this result. Nothing in the
  receipt corpus is currently resolvable at n=1/arm.
- To make the residual decisive you need ≈7 receipts per arm (±10 µs/step),
  each a distinct archive perturbed by one compile-neutral host-Swift comment.
  That is ~14 receipts — expensive, and the honest prior is that the effect is
  smaller than the revert it is a fraction of.
- The one thing that *did* get cheaper is the noise model: because `σ(T)` is
  0.227 % rather than the 0.345 % independent propagation predicts, `T` costs
  almost nothing in power relative to `D` while removing the four-prefill
  contamination. Use `T` as the outcome variable in any future receipt-channel
  comparison.

## Reproduce

```bash
python3 research/fern_r103d_pull.py --out /tmp/r103d-subs-raw.json      # read-only
python3 research/fern_r103d_provenance.py ef055b9b… bd33883e… -- 30f752df e17bdeb
python3 research/fern_r103d_rung1.py /tmp/r103d-subs-raw.json \
    --json research/artifacts/fern-r103d/rung1.json
python3 research/fern_r103d_wandb.py \
    --json research/artifacts/fern-r103d/rung1.json --id ycg78e8z
```

Provenance needs full 40-char SHAs (the git-database API rejects abbreviations)
and uses ~15 of the 60/hr unauthenticated budget; trees cache in
`/tmp/r103d-trees/`. Full rung-1 output: `research/artifacts/fern-r103d/rung1.txt`.

W&B run: <https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/ycg78e8z>
(`ycg78e8z`), with every σ, residual, power, and null-verdict metric above and
the three artifact files attached as `fern-r103d-evidence`.
