# R106-H preregistration — channel economics: merit-hunting vs draw-count

Student: maple-nezuko. PR #616, revision `r106-b-rev2`.
Research base: `7491001264832c2566de65c5cab9f363c6426e09`.
Written and committed **before** any of the estimators below were computed
(Rule 40, Rule 72).

Receipt-free desk work. Read-only with respect to `Sources/` and `Vendor/`.
No benchmark run, no official submission, no `senpai/submit-official.sh`.

## 0. Structural facts established before this design was fixed

These are schema/identity facts, not estimates. They are listed because they
determined the design and it would be dishonest to present them as findings
that emerged from a preregistered test.

- Frozen corpus `/tmp/r106b/receipt-corpus-frozen.json`, sha256
  `d450b5b5dc895f0d2d4de52d790035e88ea2e55255fed1ae04c80a9a7c70c12b`,
  19,936,617 B, frozen 2026-08-10T08:37Z, benchmark
  `1854efdf-feba-4773-bae9-b80520881a74`. 1787 receipts, 1693 with a
  `submissionCommitSha`, **1218 with `officialMetrics`**.
- `officialMetrics` carries `baseline_decode_seconds_per_token` and
  `baseline_prefill_seconds_per_token` on **all 1218** metric-bearing receipts.
- Identity verified exactly on all 1218 rows (worst relative error `0.0`):
  `decode_speedup == baseline_decode_seconds_per_token / decode_seconds_per_token`
  and likewise for prefill. So the ranked score is
  `score = (bl_dec/dec)^0.75 · (bl_pre/pre)^0.25`.
- `bl_dec` spans 0.0137807353515625 … 0.0140472425078125 s/token,
  median 0.01384841096875. `bl_pre` spans 0.000362341796875 …
  0.000396640869140625, median 0.0003685058603515625.
- The pinned common-baseline constants are `MB_D = 0.013855009542` and
  `MB_P = 0.000372473193`; `median(bl_dec)/MB_D = 0.99952`,
  `median(bl_pre)/MB_P = 0.98935`.

**The design-determining observation.** Rule 89.1 is that the campaign has
never submitted the same *candidate* program twice, so every σ in this campaign
is inferred from non-replicates. But the **baseline is the same pinned program
in every one of the 1218 receipts**. The corpus therefore already contains an
n=1218 exact replication of a fixed program on the ranked host. That is the
highest-powered handle on session structure, drift and tail shape available
anywhere in this campaign, and it is what this experiment is built on.

## 1. Model and notation

For receipt `k`, candidate tree `i`, session `j`:

```
ln score = ln cs + ln L
ln cs_ijk = mu + merit_i + c_ijk          (candidate axis, PINNED constants)
ln L_jk   = lambda + l_jk                 (baseline axis, FIXED program)
cs   = (MB_D/dec)^0.75 · (MB_P/pre)^0.25
ln L = 0.75·ln(bl_dec/MB_D) + 0.25·ln(bl_pre/MB_P)
```

`c` is candidate-timing draw noise. `l` is baseline draw noise. Both are
measured in the same session, back to back, behind the same thermal gate.

Attribution of a receipt to a tree is strictly by `submissionCommitSha`, never
by `solverUsername`. Where a sha does not resolve locally, or resolves
ambiguously, the receipt is reported as **attribution uncertain** and excluded
from any tree-level statement rather than guessed (advisor instruction).

Campaign `BASE_SHA` `1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7` is `origin/main`
and is **not** the research base (Rule 89.6-CORRECTION).

## 2. Estimators and degrees of freedom, declared before computing

| id | estimator | dof | relative SE of an sd, `1/sqrt(2(n-1))` |
|----|-----------|-----|-----------------------------------------|
| A1 | `sigma_L = sd(ln L)`, all metric receipts | 1217 | **2.03 %** |
| A1b | `sd(ln bl_dec)`, `sd(ln bl_pre)` separately | 1217 | 2.03 % |
| A2 | semivariogram of `ln bl_dec` vs time lag, binned | per bin | reported per bin |
| A2b | one-way ANOVA of `ln bl_dec` by UTC day | `d-1` / `1218-d` | — |
| A3 | OLS slope `beta` of `ln dec` on `ln bl_dec` within verified replicate groups, group fixed effects | `15-5-1 = 9` | — |
| A4 | tail of standardized `l`: excess kurtosis, exceedance counts, exponential/GPD upper-tail fit above `z=1.5` | 1217 | Poisson intervals on counts |
| A5 | OLS drift of `ln bl_dec` on day index | 1216 | — |
| A6 | `sigma_c` within verified replicate groups (already computed in R106-B, reused) | **10** | **22.4 %** |

`sigma_c` remains the weak link at dof 10 (relative SE 22.4 %, so a 95 % CI on
`sigma_c` of roughly `[0.70, 1.75] x` the point estimate). Every downstream
probability is therefore reported as a function of `sigma_c` across that
interval, never as a single number. `sigma_L` at dof 1217 needs no such hedge.

The 4.9x spread the advisor asked about — pooled `sd(cs)` 1.2244 % vs robust
0.1763 % (Rule 89.2) — has a mechanical candidate explanation that is
**preregistered here as a specific hypothesis**: the "robust" estimator in
`research/advisor_r106_identical_tree_variance.py` (lines 118-133) drops the
single worst group by construction, so it is downward biased as an
order-statistic selection; and R106-B Stage 0 already showed that 5 of 10
candidate r103 replicate groups are **contaminated** by real non-comment
`Vendor/` differences, so the pooled estimator mixes between-candidate signal
into within-candidate noise. Test: decompose the pooled sum of squares by
group and check whether the dominant group is a verified replicate or a
contaminated one.

## 3. Stage B estimators

| id | quantity |
|----|----------|
| B1 | `P(new record per draw) = P(ln cs + ln L > ln 2.61650354381456)`, computed (i) Gaussian in both axes, (ii) semi-empirical: average over the 1218 observed `L` values with Gaussian `c`, (iii) fully empirical where the tail supports it. Propagated across the whole `sigma_c` CI. |
| B2 | `E[draws to record] = 1/P`; wall clock at the measured **2.7 receipts/h** uncontended single-server rate (Rule 88). |
| B3 | Exchange rate `Y`: the merit increment, in % of `cs` and in µs/step, whose effect on `P(record)` equals that of one extra draw. Equivalently the mechanism size at which building beats drawing. |
| B4 | Tree selection: `argmax_i P(record | tree i)`; and a formal check of whether spreading draws over several trees beats repeating the single best tree. |

**Gap correction, declared in advance.** The advisor's stated gap of
"+0.9965 % in log-`cs`" is `ln(2.61650354381456 / 2.590559)`, i.e. it compares
a ranked **score** against a common-baseline **cs**. That implicitly sets
`L = 1`. Since `median(ln L) != 0`, the honest gap is
`ln R - ln cs_best - median(ln L)` and the difference will be reported
explicitly as a bias in the existing sensitivity table.

## 4. Preregistered outcomes (Rule 72; Rule 79 — the null cell gets reported)

- **N-FIT** — no tractable structure, or `P(record)` indistinguishable from
  zero across the whole `sigma_c` CI. Conclusion: the record is unreachable by
  drawing and the campaign must be 100 % mechanism-driven. Full-credit
  terminal result.
- **V-DRAWS** — `P(record)/draw` materially non-zero. Report draw budget,
  exchange rate `Y`, tree-selection rule. If `Y` is low, state plainly that
  the campaign has been under-drawing and over-briefing (advisor instruction).
- **V-SESSION** — session effect present and significant. **Takes priority in
  the writeup.** Quantify it and name which past conclusions it threatens.
- **V-DRIFT** — monotone time trend. Quantify µs/step/day and say which
  comparisons need re-dating.
- **V-BASELINE** *(added here)* — if `sigma_L` is comparable to or larger than
  `sigma_c`, the record is primarily a **baseline-lottery** outcome and the
  merit-vs-draws question must be restated on the score axis. The existing
  sensitivity table omits `L` entirely, so this is a distinct, checkable claim
  rather than a restatement of V-DRAWS.
- **V-COMMON** *(added here)* — if `beta ~ +1` in A3, session noise is
  common-mode and cancels in the ratio, so `sigma_score < sigma_cs` and every
  `z` in this campaign computed on the `cs` axis is **conservative**. If
  `beta ~ 0` the two variances add and every such `z` is **optimistic**. Both
  directions are pre-committed.

## 5. Stopping rule

Stop when (a) N-FIT fires, or (b) Stages A and B are complete and the policy
paragraph is written, or (c) V-SESSION is established with a magnitude. No
mechanism will be proposed or built under this assignment.

## 6. Coupling to #597

frieren's R106-E is submitting one identical tree at n>=4 on the official
channel to measure same-tree `sigma` directly. The Stage B model is
parameterised on `sigma_c` so her measured value drops straight in. If the
retrospective estimate here and her prospective estimate disagree, that
disagreement is itself a headline result: the historical corpus would not be
exchangeable with fresh replication.

## 7. Scope fence

Does not duplicate frieren's replication (#597, R106-E), fern's redundant-read
census (R106-G, #619), or tanjiro's prefill non-GEMM census (R106-F, #620).
