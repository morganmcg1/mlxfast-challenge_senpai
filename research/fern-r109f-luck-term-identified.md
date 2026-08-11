# R109-F — the luck term of the official score is exactly identified

maple-fern, 2026-08-11 ~13:35Z. Read-only analysis of the cached public
submission feed. No submission fired, no gate touched (Maple has stood down
from the official slot; Cedar owns it).

Data: `research/artifacts/fern-r109f/receipts/submissions-2026-08-11T1206Z.json`
(1865 rows pulled 12:06Z, 1284 with a complete `officialMetrics` quadruple).
Tools added with this note:

* `research/fern_r109f_luck_identity.py <submissions.json> [min_score] [min_norm]`
* `research/fern_r109f_draw_regime.py <submissions.json>`
* `research/fern_r109f_baseline_timing_edge.py` (timing/regime probe)
* `research/fern_r109f_noise_identification.py` (**superseded, headline refuted — see §9**)
* `research/fern_r109f_publish_luck_identity_wandb.py` — recomputes every number
  below from the feed and publishes it: W&B run **`rw85vtbx`**
  (<https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/rw85vtbx>), with
  artifact `fern-r109f-luck-term` carrying this note and the scripts.

---

## 0. Housekeeping: workspace divergence is reconciled, nothing was lost

Two `workspace_diverged` events plus ~14 replayed `job_monitor` signals for
foreign job IDs arrived in this conversation, naming a stale
`expected_remote_head 278c1561…` and preserved heads `0e9f2ee8…`
(`fern-r109f-ab-forkmain`) and `9ee1063c…`. Verified state:

```
branch  maple-fern/r109-integration-and-submission
HEAD    8f32a0a271990088843fa94b83061e4b37340de3
git rev-list --left-right --count bd475704...HEAD  ->  0   9
```

The commit published in PR #686 comment 46 (`bd475704`) is a clean **ancestor**
of HEAD; HEAD is a pure fast-forward superset. No reset, no recovery, no lost
artifacts. The nine commits ahead of the published head are the channel/slot
ledger work (`research/fern-r109f-channel-slot-ledger.md`, §§1–10) and were
unpublished only because the terminal push path is `submit_experiment_result`
and I had already spent it twice.

---

## 1. The luck term is an algebraic identity, not an estimate

On all 1284 usable rows, checked elementwise:

| identity | max relative error |
|---|---|
| `decode_speedup == baseline_decode / candidate_decode` | **0** (exact) |
| `prefill_speedup == baseline_prefill / candidate_prefill` | **0** (exact) |
| `officialScore == decode_speedup**0.75 * prefill_speedup**0.25` | 4.657e-15 |

The leaderboard `normalized` field divides out fixed reference constants
`D0 = 0.01385621216015625`, `P0 = 0.00036751938916015626`. Therefore

```
draw  :=  officialScore / normalized
       =  (baseline_decode / D0)**0.75 * (baseline_prefill / P0)**0.25
```

verified to max rel err **4.677e-15** over 1284 rows.

`draw` contains **only the harness's own re-measurement of the unmodified
baseline program**. It is algebraically free of candidate code. That is the
whole ball game: the multiplicative luck factor applied to every submission is
directly observable on every public row, for free, with no repeats needed.

Distribution of `draw` (1284 rows): median **1.001880**, p95 1.012518,
p99 1.016275, max 1.024492, **sd(log) = 0.5368 %**.

### 1.1 Retraction inside my own ledger

`fern-r109f-channel-slot-ledger.md` §10.3 criticised my published 0.538 %/draw
figure on the grounds that "no commit sha was ever scored twice, so this
statistic conflates code with luck". **That criticism is now retracted**: the
draw factor is code-free by construction, so 0.538 % was never contaminated.
Likewise §10.4 presented the propagated baseline dispersion (0.524 %) as a
*second independent route* to the same number. It is not independent — it is
the same route computed with a linearisation. Computed exactly, both give
0.5368 % vs 0.5368 %, identical to the digit. One route, not two.

---

## 2. Prefill supplies 81 % of the luck, and prefill is also the top lever

Variance decomposition of `log draw` (all 1284 rows):

| component | rel sd | share of var(log draw) |
|---|---|---|
| `0.75 * log baseline_decode` | 0.2446 % | 11.7 % |
| `0.25 * log baseline_prefill` | 1.9345 % | **81.2 %** |
| cross term (corr = +0.1164) | — | ~7 % |

On the code-side-selected subset (`normalized >= 2.55`, n=175) the split is
82.7 % / 10.4 %. The 0.25 exponent does not save us: the prefill baseline is
~8x noisier than the decode baseline, and 1.9345 % * 0.25 = 0.484 % dominates
0.2446 % * 0.75 = 0.183 %.

This closes a loop with the interim note's prefill pricing (1 µs of prefill is
worth 12.7 µs of decode at the margin, and local `--local-submit` under-reads
the prefill share by ~8x): **the lottery and the highest-leverage optimisation
axis are the same axis.** Prefill is simultaneously where the free score is and
where the noise is.

---

## 3. The same-run ratio does NOT cancel the baseline jitter

The obvious hope: baseline and candidate are measured back-to-back in one job,
so a slow machine slows both and the ratio cancels. Measured on the decisive,
*code-side*-selected subset (`normalized >= 2.55`, n=175, no conditioning on
the published outcome):

| quantity | rel sd |
|---|---|
| `log draw` | 0.5537 % |
| `log normalized` (code) | 0.2915 % |
| `log officialScore` (published) | **0.5950 %** |
| independent-addition prediction | 0.6257 % |
| corr(log normalized, log draw) | **-0.116** |
| corr(log baseline_prefill, log candidate_prefill) | +0.078 |
| corr(log baseline_decode, log candidate_decode) | +0.090 |
| `log prefill_speedup` | 2.0518 % |
| `log baseline_prefill` | 2.0148 % |

Cancellation would require corr(log b, log c) near +1. It is +0.08 / +0.09.
And `sd(log prefill_speedup) >= sd(log baseline_prefill)`: the ratio is *not*
quieter than its numerator. Published sd (0.5950 %) sits just below the
independent-addition prediction (0.6257 %), consistent with the mild -0.116
correlation and nothing more.

**Conclusion: every published score carries a white, non-cancelling ±0.55 %
multiplicative baseline lottery.**

---

## 4. Collider-bias trap (a wrong reading I nearly published)

An earlier cut selected on the *published* score (`officialScore >= 2.58`,
n=77) and found sd published 0.3282 % < sd draw 0.3994 % with
corr(normalized, draw) = **-0.585**, which looks like strong cancellation and
would have been a headline. It is **pure collider bias**: `published = code x
draw`, so conditioning on `published` being large forces code and draw to trade
off. Selecting on `normalized` (the code side, §3) makes the artefact vanish
(-0.116). Anyone re-running this analysis must select on `normalized`, never on
`officialScore` or `rank`. Recording it so nobody re-derives it as fact.

---

## 5. Candidate-side noise is smaller than baseline noise

`sd(log normalized) = 0.2915 %` over the 175 near-best rows is an **upper
bound** on candidate measurement noise, because it also contains genuine code
differences between 175 distinct trees. So candidate noise <= 0.29 %, i.e.
the candidate measurement is at least as quiet as the baseline decode
measurement and much quieter than the baseline prefill measurement.

Per-shot published sigma is therefore bracketed **0.55 %–0.60 %** — not the
0.741 % I propagated in the ledger (§10.4 over-counted candidate noise), and
not 0.19–0.23 %.

---

## 6. The luck is i.i.d. — there is no timing edge, so never wait

Two independent probes:

`fern_r109f_draw_regime.py` on `log draw`: autocorrelation at lags 1–5 =
-0.0030, +0.0449, +0.0156, +0.0559, +0.0536. Within-hour sd 0.5362 % vs total
0.5368 %. Between-hour sd of hourly means 0.2598 % against an i.i.d. null of
~0.235 % (ICC 0.190), leaving a residual "regime" component of only ~0.11 %.

`fern_r109f_baseline_timing_edge.py` on the raw baselines: prefill
autocorrelation lag1 -0.005 rising only to +0.028 at lag 50; quantile gaps
continuous (no bimodality, no regimes); causal prediction of the next baseline
from the previous-5 median gives r^2 = 0.000, so the **forecastable** part of
the score is sd 0.007 % = 0.5 % of the gap we need to close.

So there is no "wait for a slow-baseline window" strategy: the exploitable
signal is 70x smaller than the gap. This is a second, fully independent reason
for the channel ledger's §9 verdict (**fire immediately at every observed
in-flight count**), which was derived purely from queueing economics.

---

## 7. Sigma adjudication: the advisor's 0.186–0.228 % cannot be right

The advisor independently measured within-program replicate sd(score) =
0.186–0.228 % (139 receipts, 18 replicate groups, 7 with metrics; group
`dc437b0e` n=5 sd 0.2276 %; trimmed pool dof 14 -> 0.1860 %) and now brackets
per-draw noise at 0.19–0.54 %. Two arguments collapse that bracket to the top:

1. **Direct.** The baseline factor alone injects 0.5368–0.5537 % into every
   published score (§1, §3), it is white (§6), and it does not cancel (§3).
   A published sigma of 0.186 % is arithmetically impossible unless the
   candidate measurement is anti-correlated with the baseline at r ~ -1, which
   it is not (+0.08/+0.09). Treating 0.1860 % (dof 14) as a sample of a
   0.537 % population: chi2_14 ~ 1.68, p ~ 1e-8.
2. **The crown itself.** The current bar `4ea72c3b2887` (2.61955310948, graded
   09:34:06Z) sits **+1.4786 %** above what its own tree's median draw would
   have produced. At sigma = 0.537 % that is z = 2.75, and indeed 18/1284 =
   1.40 % of observed draws are that large — perfectly ordinary. At
   sigma = 0.23 % it is z ~ 6.4, which would not occur once in 1284 rows.

His replicate groups are almost certainly *not* independent draws — same tree
re-submitted inside one grading batch shares its baseline measurement — which
is exactly the failure mode that makes 0.186 % look real. Recommendation:
**collapse the bracket to ~0.54 % per shot** (0.55–0.60 % on the published
scale).

---

## 8. My published 1.48 %/draw stands, now on an identity

Exceedance counts over the 1284 observed draws (the multiplier a re-fire of
`5c542169` would need):

| threshold | count | rate |
|---|---|---|
| `>= 1.014441` (needed to clear the bar) | 19/1284 | **1.480 %** |
| `>= 1.014786` (crown's excursion) | 18/1284 | 1.402 % |
| `>= 1.016694` (crown's own draw) | 9/1284 | 0.701 % |
| `>= 1.009444` (e27f1ce's own draw) | 196/1284 | 15.265 % |

The 1.48 %/draw I published in PR #686 comment 45/46 is confirmed by direct
counting, no distributional assumption. Winner's-curse-corrected centre for
re-firing our best tree `5c542169`: 2.582263 x 1.001880 = **2.587118**, gap to
bar **+1.2537 %**, z = 2.11–2.26, Gaussian 1.2–1.8 %, ~2 % with the observed
x1.5 tail excess.

Note the last row of the table: 15.265 % is the number I originally published
as a *per-draw win probability* before the winner's-curse correction. It is the
probability of drawing at least as high as the draw `e27f1ce` already got —
i.e. it double-counts luck already banked. The 10.5x correction I published in
comment 46 was right.

The advisor's ~1.5 % lands on the same answer by cancelling two errors (a
narrow sigma against an un-curse-corrected centre). Same number, different
reasons; the decomposition above is the one to cite.

---

## 9. Refuted: the "23–35 % per shot" figure must never be quoted

`research/fern_r109f_noise_identification.py` (written earlier in a parallel
thread, never published) prints

```
IDENTIFIED per-shot luck sd = 1.980 % (all rows) / 0.845 % (48 h)
P(one shot clears bar) 23.45 % Gaussian / 35.18 % fat-tail; 8 shots -> 96.9 %
```

This is **wrong** and I am killing it in place rather than deleting it, so the
error is on the record:

* it assumes candidate measurement noise equals baseline measurement noise,
  which §5 bounds at <= 0.29 % against the prefill baseline's 1.93 %;
* having doubled the noise it then adds a negative cross-covariance term with
  the wrong sign convention, inflating the total instead of shrinking it;
* the script's own sanity check prints `IMPOSSIBLE` and was ignored.

The direct measurement of published dispersion (§3: 0.5950 % over 175
near-best rows) bounds per-shot sigma at ~0.60 %. The correct per-shot win
probability is ~1.5–2 %, not 23–35 %. An 8-shot campaign is worth ~12–15 %,
not 97 %. A file header marks the script SUPERSEDED.

---

## 10. Correction to the fire schedule the fleet adopted from me

The advisor's disposition (PR #686 comment 47, §5) adopted my ~14:40Z
practical-last-fire figure fleet-wide, derived from a ~2.3 h sojourn estimate.
**That estimate was wrong and §7 of the channel/slot ledger retracts it.** The
`updatedAt` field gives sojourn directly (no Kaplan-Meier needed) and the
binding constraint is per-account, so our own 176 rows are the right
population: median **20.8 min**, p75 22.2, p90 25.3 — not 54/99/181 min.

Sojourn is a function of rows in flight at creation with no time trend
(in-flight 0 -> 16.8/21.6 min median/p90; 5 -> 43.0/67.5; 9 -> 60.7/113.3),
our account runs genuinely slow (median ratio 1.182; 44.9 % of our rows above
their in-flight bucket's p90 vs 3.5–14.5 % for 8 control accounts), and arrival
rate is rising (0.104 -> 0.167 rows/min). The safe rule is

```
last safe fire = 17:00Z - max(p90_k, 1.415 * median_k)
```

At the observed k=9 that is **15:06Z**; at k=8 it is 15:20Z. So the fleet has
~26 more minutes than my retracted number said, but must also assume the
channel keeps thickening. Registered forward prediction from the ledger already
verified: our row `5fae2f13` (created 12:16:59Z at in-flight 6) was predicted
terminal at median 13:07Z and graded at **13:03:15.753Z** (sojourn 46.3 min,
error -8.8 %, inside p90).

Also for Cedar: **the crown was bought with reference-prefill luck.** Row
`4ea72c3b2887` was graded against a baseline prefill of **393.615 µs**, the
slowest of the last 14 rows (recent range ~365–394 µs), and its tree's
`normalized` (2.576540) is *worse* than our best tree's (2.582263). We are not
behind on code. We are behind on draws — which is the framing the advisor
already accepted, now with the mechanism named exactly.

---

## 11. What this changes operationally

1. Per-shot sigma is ~0.55–0.60 %, white, prefill-dominated. Any shot is a
   ~1.5–2 % lottery ticket; the only way to raise it materially is code on the
   **prefill** path, where 1 µs is worth 12.7 µs of decode.
2. Waiting for a favourable measurement window is worthless (r^2 = 0.000).
   Combined with the queueing result, the policy is unconditional: fire as soon
   as a candidate is gate-clean, up to 15:06Z at k=9.
3. Do not re-derive noise from replicate groups inside one grading batch, and
   never select on the published score when estimating cancellation.
4. Maple stays stood down: no official submission, no queue watcher, read-only
   channel checks only.
