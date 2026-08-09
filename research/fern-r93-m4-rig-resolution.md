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
nested bootstrap and hand-off protocol. They are quoted where they are applied
below.
