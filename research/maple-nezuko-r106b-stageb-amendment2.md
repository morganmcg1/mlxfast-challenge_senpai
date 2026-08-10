# R106-B Stage B — Amendment 2 (preregistration, written before any evidence run)

Student `maple-nezuko`, PR #616, assignment `maple-r106-b-revert-residual-forensics`,
revision `r106-b-rev3`, research base `446fe987`.

Parent documents: `research/maple-nezuko-r106b-stageb-preregistration.md`
(H4) and `research/maple-nezuko-r106b-stageb-amendment1.md` (PACKRED, D-SIMDSUM).
This amendment changes the **measurement plan only**. No hypothesis, no arm and
no outcome label is redefined, and no number below is filled in yet.

Written at 2026-08-10T12:50Z, before the first `--local-submit` run of the
campaign it describes.

## 1. Why the Amendment 1 triage gate is being retired unexercised

Amendment 1 section 5 gave me a cheap exit: if the `P`-vs-`C` probe delta came
out "smaller than ~2x the 15 us/step `--local-iterate` noise scale", I could
abandon PACKRED *without spending evidence runs* and close Stage B as N-RECOVER.

That gate is **inoperable as written**, and I am retiring it rather than
pretending it fired. The realised `--local-iterate` noise in this session is far
larger than the 15 us/step figure the gate assumed. Two control runs of the
*same binary with the same gates unset*, 4 minutes apart, in triage session
`CKCKPC`:

| idx | arm | decode s/token |
|---|---|---|
| 1 | C | 0.0128923193359375 |
| 3 | C | 0.0130101324921875 |

That is a **118 us/step control-vs-control spread**, ~6x the +19.4 us/step
residual this assignment is chasing and ~8x the 15 us/step figure the gate
assumed. A decision rule whose threshold is `2 x 15 = 30 us/step` cannot be
evaluated against a measurement whose own control noise is 118 us/step: any
verdict it returned would be an artefact. The honest move is to escalate to the
evidence path, where the decode estimate averages 1023 steps instead of 128.

This is a **declared deviation** from Amendment 1, recorded before the fact, and
it deviates in the direction of *spending more* rather than concluding sooner.

Under Rule 86 no `--local-iterate` number — including the two above — appears in
any conclusion. The table above is evidence *about the instrument*, not about any
arm, which is the only role triage is allowed to play.

## 2. Consequence for the H4 arm: it is promoted back into the campaign

H4 was refuted on triage only. By the argument in section 1 that refutation is
worth exactly as much as the gate I just retired — i.e. nothing that may be
headlined. Since the marginal cost of an arm is ~25 minutes of otherwise idle
host time and Stage B has consumed **zero receipts**, H4 rejoins the campaign so
that every Stage B claim rests on the evidence path. If H4 is genuinely dead,
this produces a defensible null instead of an undefended one (Rule 79).

## 3. Design (named, fixed here, no interim stopping)

**Control-anchored position-balanced block design**, one binary, gate-selected,
one continuous host session.

* Arms — `C` all gates unset (the shipped kernel, i.e. the preregistered
  revert); `K` `DARKBLOOM_FUSED_SLIDING_ATTN_PACKRED=1`; `H`
  `DARKBLOOM_FUSED_SLIDING_ATTN_H4=1`; `P`
  `DARKBLOOM_FUSED_SLIDING_ATTN_NOREDUCE=1`.
* Block = 4 runs: `C` first, then a permutation of `K`, `H`, `P`.
* 6 blocks, order fixed now:
  **`C K P H | C P H K | C H K P | C K H P | C P K H | C H P K`**
  (24 runs). Every non-control arm occupies block positions 2, 3 and 4 exactly
  twice each, so within-block drift cannot favour one candidate over another.
* Every candidate run is paired against the `C` run of **its own block**, which
  is the interleaved contemporaneous control required by Rules 40/68.
* Path: `./benchmark.sh --local-submit` (1023 decode steps), thermal gate at
  40 C before each timed phase, `MLXFAST_LOCAL_FAN_PROMPT=0`.
* Runner: `research/maple-nezuko-r106b-packred-paired.sh`, sink
  `/tmp/r106b-packred-evidence.tsv`.

## 4. Estimator and degrees of freedom, declared

For arm `X` in `{K, H, P}`, block `b` in `1..6`:

`D_X = mean_b (X_b - C_b)`, paired t interval `D_X +- t(0.975, 5) * sd(D_X)/sqrt(6)`.

* **declared dof = 5** for each of the three contrasts, `t(0.975, 5) = 2.5706`.
* primary metric `decode_us_per_step`; conversion to score units at
  **0.015228 % of `cs` per us/step** (65.67 us/step = 1 % of `cs`).
* **No interim stopping and no arm dropped mid-campaign.** All 24 runs execute
  unless the host fails. A run lost to a non-arm cause (build flake, thermal
  abort) is re-run at the end of the campaign and labelled as a replacement.
* Multiplicity: three contrasts are tested, so the nominal 95 % intervals are
  read as per-contrast. Only `D_K` and `D_H` can carry a V-label; `D_P` is a
  bound, not a candidate (section 5). I do not apply a family-wide correction and
  I say so here rather than discovering the convenient reading later.

## 5. Arm P is a bound, never a headline

`P` deletes the row-loop cross-lane reduction and uses each lane's partial dot
product as the whole one. Its output is **numerically wrong by construction**,
`passed_correctness = false` is the expected result, and it is deleted from the
final patch. It exists to answer one question the two candidates cannot:

> How much of the sliding decode attention kernel's 670 us/step is the
> main-loop cross-lane reduction *at all*?

`-D_P` is therefore an **upper bound on what any lever targeting that reduction
can ever recover**, PACKRED and the Stage C `P-ROWLANE` proposal included.
Reading rule, fixed now:

* `-D_P` CI excludes 0 and `-D_P >= 5 us/step` — the reduction is a real cost;
  `P-ROWLANE` is handed to Stage C *priced at that bound* and PACKRED's own
  result tells fern whether the butterfly is the wrong way to spend it.
* `-D_P` CI covers 0 — the reduction is not measurably a cost on this host,
  `simd_sum` is behaving as a native reduction, and the **whole reduction family
  is closed**, including `P-ROWLANE`. That is a stronger and more useful result
  than either candidate winning, because it retires a family rather than a patch.

`P`'s number is always reported next to `passed_correctness = false` and is never
converted into a claimed `cs` improvement.

## 6. Outcome labels

Unchanged from Amendment 1 section 4.5 (`V-RECOVER`, `V-ATTRIB`, `N-RECOVER`,
`N-CORRECT`, `N-RESIDUAL`), applied per candidate arm with the section 4
estimator. Stage A's `N-RESIDUAL` already fired and is not revisited.

## 7. What would falsify my own expectation

I expect `N-RECOVER` on both candidates and I expect `-D_P` to be small. Stating
that in advance is what makes the campaign informative: if `K` comes back
faster with a CI excluding zero, the expectation above is wrong and the
V-label fires on the published numbers, not on a rewritten story.
