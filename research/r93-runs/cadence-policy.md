# Deliverable 5 — submission-cadence policy for the official receipt channel

This is the rule we propose the campaign adopts for spending official
submissions. It is written as a decision procedure, not as advice.

## The two hard facts that shape it

### 1. The channel is strictly serial: one submission in flight, ever

At 03:12 UTC on 2026-08-09 we attempted to dispatch a second submission while
one was still validating. The service refused it:

```
{"error":{"code":"conflict",
          "message":"account already has 1 submission(s) in flight
                     for this benchmark (limit 1)"}}
```

The rejected attempt did **not** consume a submission. This means there is no
such thing as "fire off a batch and compare": every official measurement is
serialised behind the previous one. Measured end-to-end turnaround from `mlxfast
submit` to a terminal receipt for our null replicate `25e1f18e` was **20.8
minutes** (queued 02:56:02, terminal 03:16:50), of which the benchmark itself
was 52 s of wall time (39 s correctness, 45 s timed phase). Queue and host
scheduling dominate; the measurement is cheap and the *slot* is what is scarce.

Practical consequence: an experiment that needs `n` official receipts costs
about `n × 21` minutes of calendar time and cannot be parallelised. A five-point
replicate study is a ~1.75 hour commitment; eight points is ~2.8 hours. Plan
official-run budgets in *hours of exclusive channel time*, not in "number of
submissions".

### 2. The candidate side is quiet; the baseline side is not

See `research/r93-runs/RESULTS.md` §2 for the measured candidate-side σ and §9
for an n=1184 characterisation of the *baseline* side derived from the whole
receipt corpus at zero submission cost. Headline numbers: baseline decode
CV 0.2454 %, baseline prefill CV **1.9451 %**; candidate decode CV in the
current frontier regime ≈ 0.40–0.44 %, candidate prefill CV ≈ 0.24 %. Every
ranked score divides by that baseline, and candidate/baseline are uncorrelated
(|ρ| < 0.08 by four independent estimators, §9.3), so
`CV(speedup)² = CV(cand)² + CV(bl)²`. Reading raw candidate timings instead of
published speedups sharpens decode by 1.2× and **prefill by 30×**.

## The policy

**P1. Never spend an official run to answer a question a local run can answer.**
The official channel is for (a) confirming an M5 effect, (b) hidden-gate
correctness, and (c) measurements that only exist on M5 (kernel families the M4
does not select). Anything else — does it build, does it stay bit-exact, is the
knob live, roughly how big is the effect on *some* Apple GPU — goes to the local
host first. Our own Arm B pre-flight found and corrected a rung choice that
would have wasted three official runs; that pre-flight cost 4 minutes of M4.

**P2. Read receipts as raw timings, never as cross-session scores.** Record
`decode_seconds_per_token`, `prefill_seconds_per_token` and both baseline
timings from every receipt. Compare candidate-to-candidate. A score difference
between two sessions is not evidence; it imports the baseline's much larger
dispersion twice. This is the single rule that most changes what the channel can
resolve.

**P3. Size the experiment before dispatching it.** Take the measured
candidate-side σ, look up the minimum resolvable |Δ| for the number of receipts
you can afford (table in `RESULTS.md`), and compare it with the effect you
expect. If your expected effect is below the resolvable threshold at the budget
you have, **do not dispatch**. Either enlarge the effect (as we did by moving
the ladder rungs from `{40,120,240}` to `{240,800,1600}`), or find a different
question. Dispatching an underpowered comparison spends real channel time to
produce a number that cannot be distinguished from noise, and then invites
someone to over-read it.

**P4. Interleaving is cheap insurance, not a requirement — the channel has no
drift.** We entered this experiment assuming arm order would alias onto
time-of-day and host drift, and we interleaved null, rung, null, rung, …
accordingly. The corpus disproves the premise (§9.2): over 1184 receipts
spanning sixteen days, `mean|adjacent diff| / mean|random-pair diff|` is 1.0085
for baseline decode and 1.0102 for baseline prefill — a pure white sequence
would give 1.0000, and strong drift would give a number well below 1. Daily
baseline decode means span 13839–13866 µs (0.2 %) with no trend. So two
receipts a week apart are as comparable as two ten minutes apart, and you may
order an experiment for scientific convenience (highest-information rung first)
rather than for balance. Keep interleaving only when it is free; do not pay a
slot for it, and do not delay a decision-relevant rung to preserve alternation.

**P5. One difference per submission.** The surface uploaded for a receipt should
differ from the previous receipt in exactly one intended way. Our replicates
differ only in a trailing comment; our rungs differ only in one integer. If two
things change at once, a serial channel gives you no way to unmix them without
spending two more slots.

**P6. Distinct surfaces, or you get one receipt.** The service deduplicates
identical submitted surfaces. A replicate study needs a per-replicate marker
(we use a trailing `// senpai-r93-null-<n>` comment) or the replicates collapse.

**P7. A `rejected` receipt is not a failure.** `rejected` with
`rejectionReason: "score did not improve current best"` is the *normal* terminal
state for a measurement submission and carries the full metric block, including
both floor verdicts and every correctness gate. Read `passed_correctness`,
`passed_decode_speedup_floor`, `passed_prefill_speedup_floor` and `error`
separately from `status`. Only a correctness or floor failure is a real failure.

**P8. Every receipt is logged before the next one is dispatched.** Fetch the
receipt JSON, commit it to the research log, and push it to W&B with the marker,
source commit, raw timings and all gate verdicts. A serial channel makes it very
tempting to keep firing; if a receipt is not recorded at the moment it lands, the
association between surface and number is what gets lost.

**P9. Deliberately spend a slot on a null every so often.** The channel's
resolution is not a constant — it depends on host state, harness version and the
model. A replicate that changes nothing is the only way to know what the channel
can currently resolve, and it is cheap relative to being wrong about a 0.3 %
"win". We suggest one null per campaign week, or immediately after any harness
or base change.

**P10. Mine the corpus before you spend a slot.** Every receipt ever produced
carries `baseline_decode_seconds_per_token` and
`baseline_prefill_seconds_per_token` for the *pinned* baseline — identical code
on all 1184 receipts. That is a free n=1184 null sample of the measurement
channel, and it is what produced §9.1–§9.5. Before dispatching a calibration
experiment, ask whether the corpus already answers it. Concretely, the corpus
gave us the baseline dispersion, the absence of drift, the absence of
cand/baseline correlation, the tail shape, and the heteroscedasticity slope —
five results that would otherwise have cost dozens of slots.

**P11. With n ≥ 3, summarise receipts with a median or trimmed mean.** Both
baseline channels are right-skewed (decode skew +0.93, excess kurtosis +1.94;
prefill skew +0.53). A 5 % trimmed mean cuts the apparent decode dispersion by
22 % relative to the raw mean. The tail is real host contention, not a coding
error, so it should not be deleted from the record — but a single unlucky
receipt should not be allowed to dominate a three-point estimate either.

**P12. Expect calibration to get *harder* as the frontier gets faster.** Noise
on this channel is multiplicative, not additive: across near-replicate groups
the standard deviation rises with the mean while the CV stays roughly flat
(§9.5). But the fastest candidates — the ones at the current frontier, 4912–5100
µs decode — show CV ≈ 0.4358 %, versus 0.2454 % for the much slower pinned
baseline. In absolute µs a frontier candidate is quieter; in the *relative* units
that the score uses, it is ~1.7× noisier. Every additional win therefore shrinks
the effect you are chasing *and* leaves the relative noise floor where it was.
Re-derive the cadence table after each frontier promotion; do not reuse last
month's `n`.

## Worked budget

For a campaign day with, say, four hours of channel time (~11 slots):

| purpose | slots |
| --- | --- |
| null calibration (channel σ for the day) | 2 |
| the actual hypothesis, interleaved with its control | 6 |
| confirmation of whatever won | 2 |
| spare for a failed dispatch or a bad build | 1 |

The uncomfortable implication of P3 is that six slots on one hypothesis resolves
only fairly large effects. That is a real constraint on the campaign, not a
defect of the policy: it says the channel should be used to confirm effects that
were first found somewhere cheaper, and that hunting for sub-noise decode wins
directly on the official channel is not a viable strategy.

## Receipts needed, by effect size

From §5 of `RESULTS.md` (95 % two-sided, 80 % power, σ(raw candidate decode)
= 0.4261 %, σ(published decode speedup) = 0.4917 %). "Estimated reference" means
you already have a well-characterised control from previous receipts; "fresh
reference" means you must also pay for the control in this experiment.

| true decode Δ | est. ref, raw µs | est. ref, published | fresh ref, raw µs | fresh ref, published |
| --- | --- | --- | --- | --- |
| 0.5 % | 6 | 8 | 12 | 16 |
| 1.0 % | 2 | 2 | 3 | 4 |
| 2.0 % | 1 | 1 | 1 | 1 |
| 4.0 % | 1 | 1 | 1 | 1 |

Read this as the operational core of the policy:

- A **≥ 2 % decode win confirms in a single receipt.** Do not spend three.
- A **1 % win costs 2–4 receipts** (~45–85 minutes of exclusive channel).
- A **0.5 % win costs 6–12 receipts** (2–4 hours). At that price, prefer to
  bundle it with another change and confirm the pair, or find the effect on M4
  first and use the official channel only to check that the sign transfers.
- Anything the candidate cannot be shown to move by ≥ 0.4 % is, for practical
  purposes, unmeasurable on this channel within a single campaign day.

**Where that σ comes from, and why not from the nulls.** The obvious source is
this experiment's own machine-code-identical nulls, which give 0.3386 % at n=4.
That number is not usable for planning: required `n` scales as σ², and a
four-point sd carries a 95 % χ² interval of [0.57, 3.73]× the point estimate, so
the "12 receipts" cell honestly spans 4 to 167. The number above instead comes
from the receipt corpus — solver-day groups with ≥ 4 receipts and internal CV
< 0.6 %, restricted to group means ≤ 5100 µs so it is measured at our own decode
speed. That is 119 points in 8 groups, ~111 df, and its own interval is a few
percent wide. It sits 1.26× above the null point estimate, which is the safe
direction, because it is measured under small code differences rather than none.
**Plan with the corpus σ; use the nulls to check the channel is well-behaved,
not to size it.**

Prefill is the mirror image. Read as raw candidate µs its σ is ≈ 0.111 %, so
n = 4 resolves 0.164 % (≈ 0.31 µs/token); read as `prefill_speedup` the same
four receipts resolve only 2.87 %. Never evaluate a prefill hypothesis with the
published speedup.

**The 0.95 prefill floor is a cliff, not a gradient.** It is tempting to run the
same arithmetic on the floor — `prefill_speedup` carries a ~1.95 % CV, so a
normal model says a truly-compliant 0.98 candidate trips the hard floor about
6 % of the time. That normal model is wrong, and §9.3 of `RESULTS.md` tests it
against all 1185 observed baseline prefill draws instead:

| true prefill speedup | empirical trip rate | normal-theory rate |
| --- | --- | --- |
| 0.98 | **0 / 1185 = 0.00 %** | 5.78 % |
| 0.97 | 7.34 % | 14.46 % |
| 0.96 | **50.38 %** | 29.61 % |

The baseline's prefill distribution is short-tailed on the left — its worst
observed draw is only 2.7 % below the mean, where a normal tail would reach
5.1 % — so a genuine 0.98 has never tripped the floor in the entire public
record. But below that the risk rises *faster* than normal theory predicts. The
usable rule is therefore not "leave margin" but a threshold:

> **Ship if the true prefill speedup is ≥ 0.98. Treat 0.96 as a coin flip.**

And size the trade in raw candidate microseconds (n = 2 resolves 0.48 %, n = 4
resolves 0.16 %), never in the published ratio, which cannot see a 1 % prefill
change at any budget this campaign can afford.
