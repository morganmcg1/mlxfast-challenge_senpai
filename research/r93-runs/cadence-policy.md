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

See `research/r93-runs/RESULTS.md` for the measured candidate-side σ. The
campaign already records (rule 48) that the same-session baseline's prefill
coefficient of variation is roughly eight times the candidate's. Every ranked
score divides by that baseline. So the channel is far more precise when read as
raw candidate timings than when read as scores.

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

**P4. Interleave arms; never run all of arm A then all of arm B.** Because the
channel is serial, arm order aliases directly onto time-of-day and host drift.
Our own schedule alternates null, rung, null, rung, … so that any monotone drift
loads equally onto both arms. If an experiment genuinely cannot interleave,
bracket it: run the control first and last and report the drift between them.

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
