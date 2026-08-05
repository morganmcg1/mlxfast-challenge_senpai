# PR #40 r2 — which arm of the ranked receipt is noisy, and what should we rank on?

Student: maple-fern · assignment `maple-2026-08-05a-nax-stage2-double-buffer` · revision r2
Base: `d18ebbbaf724cfc8cc631d9d50de7104f0c879b8`

This document answers r2 item 4 only. Items 1–3 (revert, merge-forward, keep
research files) are mechanical and verified in the PR body.

## The tension to resolve

r1 reported two facts that cannot both be innocent:

- the paired **baseline** arm — pinned code, therefore pure measurement noise —
  shows **1.93%** relative sd on prefill across the receipt history;
- the **candidate**-side spread I used to call r1 a null was **0.18%** on the
  same axis, same machine.

Same quantity, same box, 10× apart. Either my candidate-side σ was a
within-session figure that understates cross-session drift (in which case `ns`
is not a legitimate cross-session screen and every receipt needs its own
control arm), or the noise really does live in one arm only (in which case the
paired ratio is the wrong instrument and `ns` is right).

Reproduce everything below with:

```bash
curl -sS -H "Authorization: Bearer $MLXFAST_API_TOKEN" \
  'https://api.mlx.fast/api/benchmarks/eigenlabs%2Fmlxfast-challenge/submissions' \
  > /tmp/subs_r2.json
python3 research/receipt_arm_asymmetry.py /tmp/subs_r2.json
```

Cohort: 893 passing **current-generation** receipts (`checked_steps == 1344`,
`case_count == 11`), 2026-07-27 … 2026-08-05. The 137 older
`checked_steps == 512` / `case_count == 7` receipts are excluded; mixing the two
generations is what makes naive feed statistics unusable.

`ns` here is the baseline-free content score: the paired baseline is replaced by
the cohort's pooled median baseline (368.434 µs/tok prefill, 13.84858 ms/tok
decode), so `ns = (ref_dec/cand_dec)^0.75 · (ref_pre/cand_pre)^0.25` is a
**pure monotone function of the two candidate timings**. The reference only sets
the scale: this document's `ns` differs from the r1 report's by the constant
factor 1.012994 and every ratio is bit-for-bit preserved. `ns` is therefore the
same instrument as the advisor's new "rank on candidate prefill µs / candidate
decode ms" rule, just scalarised with the official 0.75/0.25 weights.

## (a) Candidate-arm cross-session sd for behaviourally identical code: **≈0.2%**

Three independent estimates agree.

**1. The `program.md` byte-identical control triple** — `f8502e12`, `71586bcf`,
`f3cda678`, three separate ranked sessions on 2026-08-04 at 09:30, 10:02, 10:26:

| series | mean | rel sd |
|---|---|---|
| candidate prefill | 190.842 µs/tok | **0.260%** |
| candidate decode | 5.13516 ms/tok | **0.168%** |
| baseline prefill | 379.463 µs/tok | **2.358%** |
| baseline decode | 13.88257 ms/tok | 0.246% |
| officialScore | 2.503493 | **0.635%** |
| `ns` | 2.480622 | **0.076%** |

**2. My own r1 triple** — `c3ce66ec`/`cdf71faf`/`4058d0b4`, 2026-08-05, three
different kernel arms that turned out behaviourally near-identical: candidate
prefill 0.245%, candidate decode 0.151%, baseline prefill **2.805%**,
officialScore 0.810%, `ns` 0.129%.

**3. A content-inflated upper bound** — the top-decile-`ns` frontier cohort
(n=89, spread over all 10 days): candidate prefill **0.202%**, candidate decode
**0.323%**, baseline prefill **2.082%**. These 89 receipts are *different*
codebases, so their candidate spread is an upper bound on candidate-arm noise,
and it is still an order of magnitude under the baseline arm.

So the candidate arm's cross-session noise is ~0.15–0.26% per axis, **not
1.9%**. My r1 σ was right and the 1.9% belongs to the baseline arm alone.

### The noise model closes exactly

Propagating the four measured arm sds through the score definition:

- σ(`ns`) = hypot(0.75·σ_cand_dec, 0.25·σ_cand_pre)
- σ(officialScore) = hypot(0.75·hypot(σ_cand_dec, σ_base_dec), 0.25·hypot(σ_cand_pre, σ_base_pre))

| triple | pred σ(ns) | meas σ(ns) | pred σ(score) | meas σ(score) |
|---|---|---|---|---|
| byte-identical | 0.142% | 0.076% | 0.634% | **0.635%** |
| PR40 r1 arms | 0.129% | **0.129%** | 0.752% | 0.810% |

The officialScore prediction lands on the measurement to three decimal places
on a truly byte-identical triple. **The baseline-prefill draw alone explains
86.5% (byte-identical) / 86.9% (r1) of officialScore variance.** officialScore
is, to first order, a measurement of which baseline prefill the box happened to
draw.

### Consequence: minimum detectable *true* content delta (95% two-sided)

| design | `ns` | officialScore |
|---|---|---|
| paired A/B, 1 receipt per arm | **0.394%** | 1.757% |
| paired A/B, 2 per arm | 0.278% | 1.242% |
| paired A/B, 3 per arm | 0.227% | 1.014% |
| **1 receipt vs a fixed published control** | **0.278%** | 1.242% |

`ns` is 4.5× tighter, i.e. **20× cheaper in receipts** for the same resolution.
And the cheapest design of all is one receipt compared to a *fixed, already
published* control: 0.278% on `ns`, beating even a 3+3 paired A/B on
officialScore. `c3ce66ec` (`ns` = 2.511722 on this document's scale) is a valid
permanent control. **This validates the advisor's new no-paired-A/B-receipt
policy and makes it strictly cheaper, not just cheaper-and-riskier.**

r1's two arms were −0.250% (v1) and −0.463% (v2) in content terms. Against the
0.278% single-receipt-vs-control resolution, v2's regression was real and v1's
was borderline — both wrong-sign, which is the r1 conclusion, now with a
properly calibrated instrument instead of an assumed σ.

## (b) Do the two arms co-move? **No — r ≈ 0.** This is the decisive result.

`corr(baseline_prefill, candidate_prefill)` and the decode equivalent, Pearson
with Fisher-z 95% CI:

| cohort | base_pre vs cand_pre | base_dec vs cand_dec |
|---|---|---|
| within `harness_hash` epoch residuals (n=291) | **−0.011** [−0.125, +0.105] | **−0.015** [−0.130, +0.100] |
| frontier-tight cohort (n=89) | −0.159 [−0.355, +0.051] | +0.052 [−0.158, +0.258] |
| all receipts, raw (n=893) | −0.132 [−0.196, −0.067] | −0.154 [−0.217, −0.089] |

The raw all-receipts figures are a content/calendar confound: later receipts are
faster *and* the baseline drifted slightly up, which manufactures a spurious
negative. The two content-controlled estimates are indistinguishable from zero.

**The paired baseline carries no information about the conditions the candidate
arm ran under.** A paired ratio only helps when the two arms share a common
factor; here there is none, so dividing by the baseline does not cancel
anything — it strictly *adds* the baseline arm's variance to the candidate's.
That is the whole 4.5× penalty in the table above. **`ns` is the correct
instrument; the paired ratio is not.**

A second nail: within the same epoch, the baseline's own two axes barely
co-move — `corr(base_pre, base_dec)` = **+0.194** [+0.081, +0.302]. Even inside
one arm the prefill noise is prefill-specific. Whatever it is, it is not a
machine-wide session state, because a machine-wide state would move decode too.

## (c) Is baseline-first the real schedule, and what is the mechanism?

**Ordering.** Documented as baseline tree first, then candidate workspace
(`.github/workflows/benchmark.yml:1777-1778`, `:1783`;
`docs/benchmark-window-freeze.md:180-181`). It is *documentation, not readable
code*: the sequencing lives inside the box-owned
`/opt/bench-runner/measure-job.sh`, which is not in this repository
(`benchmark.yml:136`, `:1805`; `senpai/program.md:74`). Note the argv order at
`benchmark.yml:1805-1812` is candidate-first, so **argv is not evidence of
measurement order**, and no test asserts the order. Within an arm the order is
readable and is prefill → decode
(`Sources/MLXFastTrustedHarness/LagunaRuntimeBenchmark.swift:482`, `:499`).

**No per-arm timestamps are published.** `validate-benchmark-artifacts.sh:85-142`
pins a closed metrics key set; the single `timestamp` is inherited from the
gates score via `overlay-paired-timing.sh:130,:136` and never rewritten. So (c)
cannot be settled from the feed — it would need a ranked run's
`paired-results.json` / `measure-verdict.txt` and the runner log.

**The cold-first / warm-second explanation I floated in r1 is refuted by
readable code.** All three of its mechanisms are absent:

- *page cache*: the arms do not share a weights directory (baseline
  `/opt/bench-runner/baseline/.../current`, candidate
  `/Users/Shared/bench-jobs/ranked-...`), and shard reads set
  `F_NOCACHE` + `F_RDAHEAD 0` (`Sources/MLXFastModel/DenseTensorStore.swift:97-98`),
  so there is no buffer-cache carry-over to inherit;
- *warmup*: both arms load ~21.6 GB **and** run a 512-token prefill plus one
  decode step inside the worker constructor, outside every timed window
  (`LagunaRuntimeWeights.swift:404-412`, `:470-480`;
  `LagunaRuntimeWorker.swift:44-48`), and each arm additionally generates its
  own oracle (`benchmark.yml:169`, `:1779-1780`);
- *thermal*: every timed phase, both arms, is behind the same documented 40 °C
  gate (`benchmark.yml:31-33`, `:1780-1781`).

Two further feed results narrow the mechanism:

- It is **per-run, not a session or calendar drift.** Pooled *within-day*
  baseline-prefill rel sd is **1.934%** versus **1.949%** globally, while the sd
  of the nine day-means is only **0.354%**. There is a real slow upward creep
  (370.6 → 374.4 µs/tok over eight days, the effect I over-claimed and retracted
  in r1) but it is a twentieth of the per-run noise.
- It is **baseline-prefill-specific, not a machine state.** Baseline prefill is
  bimodal, low mode 366.56 µs/tok (n=508) / high mode 380.03 (n=385), a **3.67%
  gap**. Splitting the frontier-tight cohort (content ~fixed) on that mode:

  | series | low mode (n=45) | high mode (n=44) | ratio |
  |---|---|---|---|
  | baseline prefill | 366.900 | 380.650 | **+3.75%** |
  | baseline decode | 13.85347 | 13.87550 | +0.16% |
  | candidate prefill | 191.148 | 191.016 | −0.07% |
  | candidate decode | 5.08726 | 5.08994 | +0.05% |
  | `ns` | 2.49713 | 2.49658 | −0.02% |
  | **officialScore** | **2.49518** | **2.52065** | **+1.02%** |

  A 3.75% swing in one arm's prefill moves nothing else on the box — and hands
  the receipt a free **+1.02% officialScore**.

**Best surviving hypothesis** (offered as a hypothesis, not a claim): baseline
prefill is the *first timed measurement of the whole job*, immediately after the
quiescence gate, and prefill is the first phase within its arm. It is therefore
the one measurement maximally exposed to whatever fan / DVFS / power-delivery
history the box carries into the job — state that a 40 °C temperature gate does
not constrain. Every later phase runs in an already-settled machine. This fits
all three observations: baseline prefill 1.95% ≫ baseline decode 0.25% ≈
candidate decode 0.15% ≈ candidate prefill 0.20%; zero cross-arm correlation
(the perturbation has decayed by the time the candidate arm runs); and
bimodality confined to that one series.

**The programme decision does not depend on the mechanism.** Whatever causes
it, it is measured to live in the baseline arm only and to be uncorrelated with
the candidate arm. That is sufficient to prefer `ns`.

## Bonus: what beating the crown actually costs

Define the lottery factor `L = officialScore / ns` — exactly the
baseline-draw multiplier, since `ns` is content-only. Empirically over 893
receipts: rel sd 0.538%, p5 −0.394%, p50 +0.153%, p95 +1.210%, p99 +1.614%,
p100 +2.428%.

The crown, `46eeccf0` (lBroth, officialScore 2.552308), holds **L = 1.024278 =
p100.0 — the single most favourable baseline draw in the entire
current-generation history.**

Our reverted control `c3ce66ec` has `ns` = 2.511722, i.e. its **content is
+0.799% faster than the crown holder's**. To outrank it, that same code needs
L > 1.016159 (≈p99): empirical **P = 1.01%, about 1 in 99 receipts**. Required
further content gain on top of `c3ce66ec` for a one-receipt win:

| target P(outrank) | required `ns` | further content gain needed |
|---|---|---|
| 50% | 2.548409 | **+1.461%** |
| 80% | 2.557696 | +1.830% |
| 95% | 2.562414 | +2.018% |

Two consequences for scheduling, with one submission slot shared by four
students:

1. **Resubmitting current code is a 1-in-99 ticket, not a strategy.** It would
   consume the slot to buy a ~1% chance.
2. **The real target is ~+1.5% content, not "+0.8% and hope".** That is the
   number a candidate mechanism has to clear to be worth a ranked receipt, and
   `ns` can confirm it from a single receipt against `c3ce66ec` at 0.278%
   resolution.

My v1 arm `4058d0b4` drew L = 1.016139 — the p99 value, to five decimals. That
draw, and nothing in the kernel, is what produced the retracted "v1 WON" call.

## Method caveats, stated plainly

- **`harness_hash` is not the byte-identical-archive key.** I had hoped it was.
  It is not: the byte-identical control triple carries three *different*
  `harness_hash` values (`20b79685`, `146a7217`, `6350dc6c`) while my three
  *different*-code r1 arms share one (`26581d97`). Families are ~1.6 h temporal
  clusters (median day-span 0.068 d), 0/82 share a `submissionCommitSha`, and
  within-family candidate-prefill spread is 1.702% — i.e. content, not
  replicates. So the section-2/3 "within-family" figures are **within-epoch**
  and remove epoch effects, not content. The correlation result is unaffected
  (removing an epoch mean can only *help* expose a shared session factor, and
  none appears), but no within-family sd should be read as replicate noise. The
  replicate numbers in (a) come from the two explicit triples and the tight
  cohort instead.
- `officialMetrics.commit` is unique per receipt (1030/1030) and useless as a
  grouping key; `weights_hash` is constant; `golden_hash` has 3 values tracking
  the generation change.
- Both triples are n=3, so each individual sd has wide error bars. The case
  rests on three independent estimates agreeing plus the analytic model closing
  to three decimals, not on any one figure.
- σ(`ns`) measured on the byte-identical triple (0.076%) is *below* its model
  prediction (0.142%) because that triple's prefill and decode errors happened
  to be anti-correlated at n=3. The tables above use the model value (0.142%),
  the conservative choice.

## Recommendations

1. **Rank on `ns` (equivalently on candidate prefill µs and candidate decode
   ms). Never conclude from an officialScore delta.** 86.5–86.9% of its variance
   is the baseline draw. Confirmed programme-wide.
2. **Use `c3ce66ec` as the fixed published control.** One new receipt against
   it resolves 0.278% on `ns` — better than a 3+3 paired A/B on officialScore
   for one sixth of the slots.
3. **Set the bar for spending the shared slot at ~+1.5% content over
   `c3ce66ec`**, not at "beats the crown's officialScore".
4. Screen mechanisms locally to the point where they plausibly clear ~1%, then
   spend one receipt. Sub-0.3% mechanisms are not resolvable in a single receipt
   and should be stacked before submission, not submitted individually.
