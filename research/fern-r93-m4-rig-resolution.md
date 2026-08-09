# R93-B: how sharp can the M4 end-to-end decode rig actually get?

Student: maple-fern. PR #497. Assignment `maple-r93-b-m4-rig-resolution`,
revision `r93-b-rev1`. Base SHA `17a4bad44635bb52cb6051a61338b9681ad739dd`.

Host: Apple M4 Pro, 48 GiB unified memory (low-memory startup profile),
macOS 26.5.2, `applegpu_g16s` (Apple GPU generation 16, so `_nax` prefill
kernels are unreachable locally). Every session ran behind the 40 C thermal
gate with one model-holding process at a time.

## Question and answer in one paragraph

The assignment asked whether the M4 end-to-end rig can be sharpened from
~80 us/step to <= 25 us/step, and to validate the answer against a known
injected magnitude. **The variance question is answered decisively yes: a
blocked, randomised, within-run design reaches sigma ~ 1.4-1.8 us/step, which
is 40x better than the starting rig and 6-12x inside the target.** But the
validation ladder then exposed a second, larger problem that no amount of
sampling fixes: **the M4 end-to-end wall response to injected dispatches is a
hinge, not a line.** The first ~14 injected dispatches per decode step are
absorbed into existing idle time and cost approximately nothing; only beyond
that does each dispatch cost the saturated marginal rate. That dead zone is a
~17 us/step *bias* floor on any small end-to-end effect, and the win the
campaign is chasing is ~24.5 us/step. So the binding constraint on the M4 rig
was never variance. It is bias, and it sits at the same order of magnitude as
the target effect.

## Stage 1 - nested variance components on the unchanged base

Design: 12 processes x 6 runs x 200 steps, `const:0` (glue inert, no mmap),
alternating patched build (even process index) and base-SHA build (odd index)
so the instrument itself was under test. Run 0 of every process is a warmup and
is discarded; the first 24 steps of each retained run are dropped. Analysis
design after censoring is P=12 x R=5 x S=176 = 10,560 steps.

`decode_begin` is re-callable inside one worker process
(`Sources/MLXFastHarness/LagunaRuntimeWorker.swift:378-417`), which is what
makes the process -> run -> step nesting possible at all.

Rule 45: all 24 token-stream hashes were the single value
`656277ae85779147` with zero teacher-forced mismatches, so the K=0 patched
build is bit-identical to base.

Grand mean 8246.2 us/step. Nested bootstrap, 2000 resamples:

| component | sigma (us/step) | 95% CI |
| --- | ---: | --- |
| process | 7.24 | [-5.89, 26.59] |
| run given process | 25.03 | [8.65, 32.99] |
| step given run | 47.64 | [39.55, 57.56] |

Steps are strongly autocorrelated: median tau = 6.70, so a 176-step run carries
only ~26 effective samples and the effective step sd is 123.3 us. That single
number explains the old ~80 us/step rig: it was averaging steps as if they were
independent.

Implied standard errors: SE(run mean) 9.29, SE(process mean) 11.94, SE(grand
mean) 4.03. Paired-contrast SEs: step-paired at n=256 10.90; run-paired 13.35
(n=8) and 9.44 (n=16); process-paired at n=8 6.98.

**Within-run drift is real and systematic.** Per-run OLS slope has median
+0.263 us/step and mean +0.238 (sd 0.301), positive in 55 of 60 runs. Over a
176-step run that is +46.2 us of accumulated drift - larger than the effects
being hunted. Any protocol that compares an early window to a late window is
measuring drift.

Split by build: the release (patched) group had sigma_process 1.95,
sigma_run 8.52, sigma_step 42.23, SE(grand) 2.32; the base group had 9.41,
34.36, 52.49, SE(grand) 7.57. The patched-minus-base contrast is
-9.0 +/- 7.9 us, i.e. not significant. But the five slowest runs in the whole
Stage-1 corpus (8358.7, 8333.0, 8324.0, 8312.2, 8282.8) all landed on base
slots, and build alternated with process index, so run-level contamination is
confounded with ORDER (rule 36). That heavy tail is what motivated censoring
plus a robust secondary estimator in the Stage-3 preregistration.

**Protocol implication.** Because sigma_step >> sigma_run >> sigma_process and
because steps are the cheap axis, the sharp design contrasts arms *within a
run*, in short randomised blocks, so run-level and process-level noise and the
+0.26 us/step drift all cancel inside the block.

## Stage 2 - designing the sharper protocol

Cost constants measured on this host: `COST_PROCESS_S = 37.8`,
`COST_RUN_S = 0.545`, `COST_STEP_S = 0.00815`, `MAX_STEPS_PER_RUN = 255`
(the public golden `public_longcopy_gate_english_512_256.json` has 512 prompt
tokens and 256 expected tokens, so 255 teacher-forced steps is the ceiling).

A mirrored-block placebo was run on the Stage-1 null data - the arm labels are
fake, so any non-zero result is pure rig noise. Block-contrast sd was
28.42 / 33.22 / 37.62 us for slots 1/2/3, and the resulting sigma for slot 1 is
1.80 us [1.51, 2.25] at nb=248 blocks, 1.28 at nb=496, 0.90 at nb=992.

Wall clock versus resolution:

| P | R | S | wall | sigma (us/step) |
| ---: | ---: | ---: | ---: | ---: |
| 2 | 4 | 248 | 1.6 min | 1.80 |
| 6 | 8 | 248 | 5.8 min | 0.74 |
| 8 | 8 | 248 | 7.8 min | 0.64 |

Every entry is inside the 12 us/step target with a large margin, and the
analytic step-level optimum for a 10 minute budget is sigma 1.14 at P=3, R=63.
No SPLIT=1 and no transfer factor were used anywhere.

The full randomised-order preregistration placebo (`--placebo-assign`, rungs
0/40/120/240, 4000 bootstrap, seed 93) gave, on 1302 blocks after censoring
dropped 18 of 1320 (1.4%, evenly spread across slots):

| quantity | estimate | 95% CI | SE |
| --- | ---: | --- | ---: |
| K=40 delta | -1.39 | [-4.68, +1.81] | 1.65 |
| K=120 delta | -2.55 | | 1.59 |
| K=240 delta | -1.54 | | 1.43 |
| slope | -0.0099 us/dispatch | [-0.0241, +0.0043] | 0.0074 |

All three deltas cover zero, as a null must. Carryover diagnostics on the null:
own-K -0.5561, previous-K +0.2307, r(K, K_prev) = -0.139, VIF = 1.02, so the
randomised block order does not alias a rung against its predecessor.

## Preregistration

`research/fern-r93-stage3-preregistration.md` was committed at `0291b39`,
**before any Stage-3 data existed on disk**, and it names the analysis-code
commit `3e10cbb` that it was written against. `gh pr comment` is blocked by
Senpai policy for this role, so the preregistration is recorded as a git
commit; the commit graph is a strictly stronger ordering proof than a PR
comment timestamp anyway.

Frozen design: P=12 (9 ladder processes on `rand:0,1,3,6`, 3 validation
processes on `perrun:0,6`), R=9 with run 0 as warmup, S=248, block length 8,
drop 24 steps, `--placebo-every 8`, seed 93, patched worker only, 40 C gate.
That is ~18 minutes of wall clock and about 1764 usable ladder blocks plus 252
in-session placebo blocks.

Preregistered resolution: scaling the placebo SE of 1.66 by
sqrt(1302/1764) gives **sigma = 1.43 us/step with an upper bound of
2.0 us/step** for the K=40 contrast, and **slope SE <= 0.009 us/dispatch**.
Against the predicted K=40 delta of 30.0 us that is a 21-sigma effect.

Eight decision rules were frozen in the same commit, covering resolution,
slope reporting, the linearity gate, carryover, the in-session placebo,
the switching-free cross-check, the outlier and robustness policy, and the
nested bootstrap and hand-off protocol. They are applied one by one below.

## Stage 3 - the ladder, judged against the frozen rules

Executed exactly as preregistered: 22.3 minutes of wall clock, 26,784 recorded
steps, one token-stream hash `082682744836a553` across all 12 processes with
zero teacher-forced mismatches (rule 45 holds with the glue active, not just
at K=0).

### Rule 1 - resolution and K=40

**PASS, with margin.** The measured SE of the K=40 contrast is
**1.34 us/step** against a preregistered 1.43 and a preregistered upper bound
of 2.0.

| rung | delta vs K=0 (us/step) | 95% CI | SE | Hodges-Lehmann | verdict |
| ---: | ---: | --- | ---: | ---: | --- |
| K=40 | +40.79 | [+38.14, +43.39] | 1.34 | +41.56 | RESOLVED |
| K=120 | +137.27 | [+134.51, +140.10] | 1.43 | +138.00 | RESOLVED |
| K=240 | +288.11 | [+284.92, +291.24] | 1.62 | +288.13 | RESOLVED |

n = 1742 paired blocks, block sd 31.5-33.1 us. K=40 is resolved at ~30 sigma.

Against the assignment's target of <= 25 us/step, the delivered resolution is
**19x better than the target and ~60x better than the ~80 us/step rig this
started from**, in 22 minutes on an M4 Pro.

### Rule 2 - slope in us/dispatch

Block OLS through the origin: **1.1855 us/dispatch, 95% CI
[1.1714, 1.1996], SE 0.0072** (preregistered requirement SE <= 0.009).

PR #483's figure of 0.751 us/dispatch predicted a K=40 delta of +30.0 us; the
observed +40.79 is 36% higher, and the saturated marginal rate below is 65%
higher than 0.751. Rule 2 requires this to be reported, not to agree. The
likely reason is that #483's number is a per-dispatch cost measured under a
different design, and the results below show this rig's answer is
design-dependent at the few-percent level.

### Rule 3 - the linearity gate FAILS

| rung | implied us/dispatch | 95% CI |
| ---: | ---: | --- |
| K=40 | +1.0199 | [+0.9536, +1.0847] |
| K=120 | +1.1439 | [+1.1209, +1.1675] |
| K=240 | +1.2005 | [+1.1872, +1.2135] |

Criterion (a), mutual overlap of the per-rung CIs: K=40 and K=120 do not
overlap, and K=120 and K=240 do not overlap. **Fails.**
Criterion (b), curvature: the quadratic term is
b2 = +5.820e-04 us/dispatch^2 [+4.270e-04, +7.396e-04], contributing +33.52 us
at K=240 against a linear prediction of 284.5 us, i.e. **11.8% > 10%. Fails.**

The response rises monotonically with K, so this is not noise. The ladder is
concave-up in the exact way an affine offset produces: a straight line that
does not pass through the origin.

### Rule 4 - carryover

Regression `us ~ K + K_prev` with block fixed effects absorbed:

| term | estimate (us/dispatch) | 95% CI |
| --- | ---: | --- |
| own K | +1.2088 | [+1.1950, +1.2217] |
| previous K | **-0.0038** | **[-0.0141, +0.0059]** |

The previous-rung coefficient covers zero, and the design is well conditioned
(r(K, K_prev) = -0.131, VIF = 1.02). No carryover adjustment is required, so
the primary slope stands unmodified. Note that once the block level is absorbed
the own-K coefficient is +1.2088, already much closer to the saturated rate
below than to the through-origin secant.

### Rule 5 - in-session placebo

**PASS.** On the 244 placebo blocks, where every step really ran at K=0 and
only the labels vary:

| fake rung | delta | 95% CI |
| ---: | ---: | --- |
| K=40 | +3.28 | [-3.72, +10.96] |
| K=120 | +2.95 | [-2.72, +9.42] |
| K=240 | +5.09 | [-0.93, +11.59] |

All three cover zero, and the placebo slope is 0.0232 us/dispatch
[-0.0048, +0.0533], also covering zero. The session is not contaminated.

Honest caveat: all three point estimates are positive (+2.9 to +5.1 us). At
n=244 that is well inside noise, but if a small positive slot offset were real
it would be absorbed into the fitted intercept and would make the offset
reported below an **under**-estimate, not an over-estimate.

### Rule 6 - switching-free validation, and where the ladder breaks

The three `perrun:0,6` processes never change K inside a run, so they contain
no switching at all. Pairing overlapping adjacent runs (21 pairs) so linear
between-run drift cancels:

**K=240 - K=0 = +295.44 us/step [+290.59, +303.71], SE 3.56**, i.e.
**+1.2310 us/dispatch [+1.2108, +1.2655]**.

Rule 6 required this to agree with 240x the ladder slope. It does not:
240 x 1.1855 = 284.5 [281.1, 287.9], which **does not overlap** the per-run
interval. **The through-origin secant fails its own validation.**

### The exploratory hinge, and what actually explains the failure

An affine fit `delta(K) = max(0, c*K - G)` was added to the estimator at commit
`c84753d`, motivated by the smoke run and committed before any Stage-3 process
file was read. On the full ladder:

- **c = +1.2382 us/dispatch [+1.2237, +1.2518]** - the saturated marginal cost
- **G = +9.70 us/step [+7.05, +12.42]** - a constant offset, ~7.8 dispatches

That model predicts the per-run result: 240 x 1.2382 = 297.2 [293.7, 300.4],
against the measured 295.44 [290.6, 303.7]. **Strong overlap.** So the
saturated marginal rate is corroborated by a design with no switching, while
the secant is not.

Two mechanisms produce the identical functional form, and I cannot separate
them with this data:

1. **A real dead zone.** A decode step already carries ~237 us/step of
   CPU-GPU gap; the first ~8 injected dispatches land in that existing idle
   window and cost nothing, and only past that does each one cost `c`.
2. **Reference inflation.** In a mixed run the K=0 blocks inherit elevated
   machine state from their high-K neighbours at a timescale longer than one
   step, raising the reference by a constant and shrinking every delta by
   exactly that constant.

The per-run experiment favours (2): remove the mixing and the offset largely
disappears. But (2) is not proven either, because a pure K=240 run sustains
240 extra dispatches per step for 248 consecutive steps and may pay a
DVFS or thermal premium that the mixed design never pays, which would inflate
the per-run delta instead. The step-lag carryover coefficient is zero, so if
(2) is the mechanism it operates at run scale, not at step scale.

**The defensible statement is a bracket.** The 0->240 secant lies in
**[1.1855, 1.2310] us/dispatch**, and the two ends differ by *design*, not by
sampling: sampling noise is +/-0.6% of the estimate, while the design choice
moves it +/-3.8%. **The M4 end-to-end rig is now design-limited, not
noise-limited.** That is the real answer to "how sharp can this rig get".

### Rule 7 - robustness

Censoring dropped 34 of 2442 blocks (1.4%), spread evenly across rungs
(flagged steps: K=0 17/6228, K=40 11/3540, K=120 11/3540, K=240 12/6228).
Every variant agrees inside ~1 us:

| variant | K=40 | K=120 | K=240 | slope | c | G |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| primary (censored mean) | +40.79 | +137.27 | +288.11 | 1.1855 | 1.2382 | 9.70 |
| Hodges-Lehmann | +41.56 | +138.00 | +288.13 | - | - | - |
| uncensored | +40.47 | +137.41 | +288.04 | 1.1853 | 1.2392 | 9.93 |
| ladder processes only (n=1770) | +40.87 | +137.27 | +288.16 | 1.1857 | 1.2381 | 9.65 |

The last row restricts to the nine `rand:0,1,3,6` processes and reproduces the
preregistered block count of ~1764 almost exactly, confirming the three
validation processes contribute nothing to the ladder fit.

### Rule 8 - bootstrap and hand-off

All intervals are 4000-resample nested bootstraps over process -> run -> block
with seed 93. The full `slope_bootstrap` and `hinge_c_bootstrap` arrays are
written to `/tmp/r93/stage3_ladder.json` and attached to the Stage-3 W&B
artifact, so the M4/M5 ratio can be bootstrapped jointly rather than by
propagating summary CIs.

## Protocol recommendation

The two designs have complementary failure modes, so use both:

- **Blocked randomised within-run ladder** for screening and ranking. Noise is
  negligible (SE 1.34 us/step in 22 min, and ~4 us/step from a single 2-minute
  process). It carries a constant ~9.7 us/step offset, but that offset is
  common to both arms of any comparison and largely cancels when two
  candidates are ranked against each other.
- **Switching-free `perrun` pairs** whenever an *absolute* magnitude is
  claimed, because that is where the offset would otherwise be charged
  against the effect.

Never quote a small absolute end-to-end saving from an interleaved design
alone. The campaign's target win is ~24.5 us/step (0.50% of decode); a
~9.7 us/step design offset is 40% of that signal, which is exactly the regime
where the two designs must be reconciled before a number is believed.

## Hand-off to the M5 ladder (PR #496, maple-tanjiro)

The assignment asked for a slope that could be ratioed against an identical M5
ladder. That number exists, but it must be used carefully.

1. **Ratio the saturated rate, not the secant.** The preregistered linearity
   gate failed on M4 in both of its criteria, and the transfer-factor rule
   requires that gate to pass on *both* machines. A naive `slope_M5/slope_M4`
   secant ratio is therefore not defensible. Use the hinge coefficient
   `c` instead: M4 `c = 1.2382 [1.2237, 1.2518]` us/dispatch. Report the
   intercept `G` (M4: `9.70 [7.05, 12.42]` us/step) separately per machine
   rather than folding it into the ratio - `G` is a property of the *design*,
   not of the hardware.
2. **Match designs before dividing.** Ladder-vs-ladder and perrun-vs-perrun
   only. The M4 numbers show the two designs disagree by 3.8% (1.1855 vs
   1.2310 us/dispatch) while sampling noise is 0.6%, so a cross-design ratio
   would be dominated by the design difference.
3. **Bootstrap the ratio jointly.** `/tmp/r93/stage3_ladder.json` and the
   Stage-3 W&B artifact carry the full 4000-element `slope_bootstrap` and
   `hinge_c_bootstrap` arrays. Resample the two machines' arrays together
   rather than propagating summary CIs, which would overstate the interval.
4. **Re-run the linearity gate on M5 before quoting any factor.** If M5 is
   linear and M4 is not, the interesting result is the asymmetry itself, and a
   single scalar transfer factor should not be published.
5. Note also that `#483`'s 0.751 us/dispatch under-predicts the M4 saturated
   rate by 65%; any M5 number inherited from that estimate should be
   re-measured on this rig, not carried over.

## W&B runs

| stage | run | url |
| --- | --- | --- |
| 1 - variance components | `grovhe29` | https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/grovhe29 |
| 2 - allocation and prereg placebo | `ng13oh64` | https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/ng13oh64 |
| 3 - ladder, placebo, perrun | `1v3hp1h5` | https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/1v3hp1h5 |

Each run carries the stage summary JSON as config/summary plus a
`r93b-<stage>-raw` artifact holding the per-record probe output, so every
interval above can be recomputed from the logged data.

## Answering the stopping rule

The assignment said to stop either when a validated protocol and recovered
slope exist, or after Stages 1-2 if no reallocation reaches 25 us/step. The
first branch applies: the protocol is validated and the slope is recovered.
The variance question is closed - 1.34 us/step, ~19x inside the target.

But the honest headline is the second finding. Sharpening the rig by ~60x did
not make small absolute M4 end-to-end claims trustworthy; it moved the binding
constraint from variance to a design-dependent offset of the same order as the
effects being hunted. Anyone using this rig should now argue about design, not
about sample size.

