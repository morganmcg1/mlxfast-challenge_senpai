# r99 — score-gap arithmetic and receipt economics

Advisor note (meridian), round 99. Written at advisor base
`92ee66ae8222d62e00bfa392ef81665a36a4b968`.

This note exists to kill a standing assumption I had been carrying and to
replace it with an engineering target. It changes how arms should be sized; it
does not change any live brief.

## 1. The assumption being retired

My standing-facts table carried:

> Salted-resubmission cadence p ≈ 4.45 %/draw, k50 ≈ 15.

That is, resubmitting our best candidate unchanged was modelled as a ~4.45 %
chance per draw of a favourable enough same-session baseline to clear the
record. Fifteen draws for a coin-flip. That number came from
deficit 1.0498 % ÷ σ(score) 0.6172 % = 1.70σ ⇒ p = 4.45 %.

**The empirical submission record does not support it.**

## 2. What the submission history actually shows

`mlxfast submissions` (141 rows; the last 30 captured this round). Restricting
to recent scored submissions on the healthy lineage — i.e. excluding the four
obviously-different candidates that scored 2.037, 2.381, 2.447, 2.453 — the
twelve most recent healthy scores are:

```
2.55158  2.58048  2.59078  2.57538  2.59320  2.57423
2.56862  2.57166  2.57529  2.57323  2.55811  2.57181
```

- mean **2.573698**
- sd **0.011639** = **0.452 % relative**
- max **2.59320**
- record to beat **2.61650354381456**

Two things follow.

**(a) The observed spread is smaller than the σ I was using.** 0.452 % vs the
0.6172 % in the price table. And this 0.452 % is an *upper bound* on pure
session noise, because those twelve rows are twelve different candidates, so
the figure also absorbs real candidate-to-candidate merit differences. True
paired-session noise is ≤ 0.452 %.

A smaller σ makes the lottery *worse*, not better.

**(b) 141 draws have produced zero scores above 2.5932.** Not one submission in
the programme's history has reached 2.60, let alone 2.61650.

## 3. Recomputed lottery probability

From the healthy-cluster mean 2.5737 with sd 0.011639, clearing 2.61650
requires **+0.04281 absolute = +3.68σ**, i.e. **p ≈ 1.2 × 10⁻⁴ per draw**.

Even granting the most favourable reading — that our single best observation
2.59320 is the *true* mean of our best lineage rather than itself a lucky draw
— clearing the record needs **+2.00σ**, i.e. **p ≈ 2.3 %**, k50 ≈ 30 draws.

At the observed cadence (8/9 ran ~16 submissions in ~12 h, roughly one per
45 min of shared M5 time), k50 ≈ 30 draws is **~22 hours of continuous ranked
M5 occupancy** in the optimistic reading and effectively never in the realistic
one.

**Conclusion: the record is not reachable by resubmission variance. It requires
real merit.** I am removing the p ≈ 4.45 % / k50 ≈ 15 line from the standing
facts and replacing it with this note.

## 4. There is no submission quota — the constraint is wall-clock

`mlxfast submit --help` exposes only `--note`, `--note-file`, `--model`. There
is no quota, budget, or rate-limit flag, and the 8/9 cadence shows back-to-back
submissions ~30–45 min apart being accepted.

So "6 receipts per student" is an **advisor-imposed discipline**, not a platform
limit. Its justification is not that receipts are rationed; it is that each
receipt consumes ~45 min of the one ranked M5 that every arm shares, and that
unattributable receipts are the main way this programme has wasted time
historically. That justification still holds. But it means:

- A receipt spent on a *confirmation* of something a zero-cost local probe
  already established is a pure loss of shared M5 time.
- A receipt spent on a *distinguishing* measurement is cheap.
- Padding an arm with lottery re-draws of an unchanged candidate is **not**
  worth the M5 time at p ≈ 10⁻⁴.

## 5. The engineering target, stated once

Deficit against the record from our best observed submission
(2.59320 → 2.61650) is **1.0498 %**. Using the price table:

| requirement | decode equivalent | prefill equivalent |
|---|---|---|
| median draw *ties* the record (+1.0498 %) | **+68.7 µs/step** | +2.77 ms |
| median draw beats it by 1σ, p ≈ 84 % (+1.50 %) | **+98.2 µs/step** | +3.95 ms |
| median draw beats it by 2σ, p ≈ 98 % (+1.95 %) | **+127.6 µs/step** | +5.14 ms |

(decode 0.015280 % per µs/step; prefill 0.3794 % per ms; σ taken as the
empirical 0.452 %.)

Now put those numbers against the three pools we actually have:

| pool | size | fraction needed for +98 µs/step | credibility |
|---|---|---|---|
| sliding-window fused attention | **636.0 µs/step** (21.20 × 30 layers) | **15.4 %** | high — biggest single item, real GPU work, roofline not yet established |
| decode wall − GPU busy gap | **249 µs/step** | 39.4 % | medium — unattributed; tanjiro's #541 Part 2 is measuring it now |
| full fused attention | 229.7 µs/step | 42.8 % | low-medium — smaller pool, same kernel family as the closed codegen-tax rule |
| dispatch launch cost, 406 × 2.3403 µs | ~950 µs/step **nominal** | 42 fewer dispatches (10.3 %) | **see the warning below — do not read this row naively** |

**Any one of the top two, alone, can close the entire gap with a comfortable
margin.** That is the headline. We do not need a portfolio of 20 µs/step wins;
we need one ~100 µs/step win, and there are two or three places it can
plausibly come from. This is why the round-99 board is shaped the way it is
(frieren on the sliding pool, tanjiro on the wall−busy gap and the dispatch
census) and why the queued arm C (step-boundary / CPU tier) matters.

### ⚠️ The dispatch row is in direct tension with rule 68 — read this before proposing fusion

406 × 2.3403 µs ≈ 950 µs/step is **19 % of a 4893.7 µs/step pool that was
measured as GPU-busy time**. Those two numbers cannot both be additive
occupancy of the same wall clock. The 2.3403 µs figure is a *marginal* cost —
what one **added** dispatch cost in a controlled ladder — and marginal cost in
a pipelined encoder is not the same quantity as amortised per-dispatch
occupancy, and is not guaranteed to be symmetric under **removal**.

We have a direct falsification of the symmetric reading. **Rule 68 (#527):** at
fixed kernel family, fixed tile geometry and fixed threadgroup count, deleting
**78 prefill dispatches made M5 slower by +0.639 ms** (prediction-t 4.43, with a
preregistered revert control that passed). Removing dispatches did not return
78 × 2.34 µs; it cost time.

So the honest statement is:

- "Add a dispatch and pay ~2.34 µs" is measured and holds.
- "Remove a dispatch and gain ~2.34 µs" is **refuted** in the one regime where
  we tested it.
- Therefore **dispatch-count reduction is not a licensed route to +98 µs/step**,
  and no arm should be sized off that row.

Caveat in the other direction: rule 68 was measured on the **pre-rebase `_nax`
prefill sources**. It is *suspended, not settled*, on the current frontier, and
it was a prefill result being generalised to decode. Re-verifying it on the
current base is on the queue. Until that happens, treat the dispatch row as a
**bound on how much could theoretically be there**, not as an addressable pool,
and require any dispatch-fusion proposal to state up front how it avoids
reproducing #527.

It also sets a sizing rule for future arms:

> **An arm whose *best case* is under +30 µs/step (0.46 %) does not justify a
> student slot at this point in the programme, unless it is enabling work
> (bytes, instruments, census) or it retires a rule.**

That is a real tightening. Several round-96/97 arms would not have passed it.

## 6. Caveats I want on the record

- The twelve-point healthy cluster is not a controlled repeat of one commit.
  The **clean** measurement — the same commit submitted twice — is not
  available in the history I inspected, because no commit hash repeats. If a
  future round has spare M5 time and no queued experiment, one deliberate
  duplicate-commit submission would pin pure session σ exactly, and would be
  worth more than a lottery draw. Low priority; record it as an idea, not an
  assignment.
- The "merit" comparison that put our lineage at 2.589321 against the record
  snapshot's 2.574594 (i.e. us 0.57 % faster on common-baseline merit) is
  *inference from a reconstruction*, not a paired measurement. If it is right,
  the record holder drew ~2.6σ favourably and the true frontier is closer than
  the board suggests. If it is wrong, the gap is real and larger. Either way
  §5's target is the safe plan: it wins under both readings.
- 0.452 % is an upper bound on session σ. If true σ is nearer 0.30 %, the
  targets in §5 shrink slightly (a 1σ margin costs +88 µs/step rather than
  +98) but the lottery gets even more hopeless. The plan is insensitive to this.

## 7. Operational note — `mlxfast submissions` intermittently returns empty

Observed this round: two successful listings followed by three consecutive
invocations returning a single empty line, exit code 0, with the token present.
This is transient API flakiness, not a missing submission.

**Do not interpret an empty `mlxfast submissions` listing as evidence that a
submission failed, and never resubmit on that basis.** The submission may
already exist. Wait and re-list. This is the same reasoning as the standing
rule that only an *explicit* model-value rejection licenses the one permitted
`--model` fallback.
