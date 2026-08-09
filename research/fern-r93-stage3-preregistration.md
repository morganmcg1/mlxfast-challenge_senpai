# R93-B Stage 3 preregistration

Committed **before** any Stage-3 data exists. The commit that adds this file is
the ordering proof; the analysis code it names is already committed.

- PR: #497, assignment `maple-r93-b-m4-rig-resolution`, revision `r93-b-rev1`
- Base SHA: `17a4bad44635bb52cb6051a61338b9681ad739dd`
- Analysis code as preregistered: `3e10cbb`
- Host: M4 Pro, 48 GiB, `applegpu_g16s` (gen 16). M4 numbers are M4 numbers;
  the `_nax` prefill kernels the ranked M5 selects are unreachable here.

## Where the number comes from

Stage 1 ran 12 processes x 6 runs x 200 steps at K=0, alternating the patched
worker and a worker built at the base SHA. All 24 token-stream hashes were
`656277ae85779147` with 0 teacher-forced mismatches, so the instrument is
bit-exact and the K=0 arm is numerically the base (rule 45).

Variance components (drop-steps 24, warmup run excluded, 2000 nested
bootstrap resamples):

| component | sd (us/step) | 95% CI |
|---|---|---|
| `sigma_process` | 7.24 | [-5.89, 26.59] |
| `sigma_run\|process` | 25.03 | [8.65, 32.99] |
| `sigma_step\|run` | 47.64 | [39.55, 57.56] |

Step-to-step autocorrelation is large (median tau = 6.70, so a 176-step run
carries only ~26 independent steps). That is why the naive run-mean SE is
poor and why the design below pairs *inside* a block instead of across runs.

Within-run drift is systematic, not noise: median OLS slope **+0.263 us per
step index, positive in 55 of 60 runs**, i.e. +46 us across a 176-step run.
A fixed mirrored rung order would alias that drift monotonically onto the
slope and would also freeze the token-position/rung pairing, a bias that does
not shrink with more data. Stage 3 therefore randomises rung order within
each block.

The predicted sigma is **not** an analytic extrapolation. It is the exact
Stage-3 estimator replayed on Stage-1 null data with the randomised order
imposed (`fern_r93_ladder.py --placebo-assign`), where every true delta is 0
by construction:

```
n=1302 blocks   K=40: SE 1.66   K=120: SE 1.59   K=240: SE 1.46
slope SE 0.0074 us/dispatch,  all deltas cover 0,  VIF 1.02
```

## Design (frozen)

| knob | value |
|---|---|
| processes `P` | 12 (9 ladder, 3 validation) |
| runs/process `R` | 9, first flagged warmup |
| steps/run `S` | 248 (golden allows 255) |
| block | 8 steps, each rung twice, freshly permuted per block |
| `drop-steps` | 24 (block-aligned) |
| ladder schedule | `rand:0,1,3,6` -> K = 0, 40, 120, 240 dispatches |
| validation schedule | `perrun:0,6`, run-constant, 4 runs each arm |
| `placebo-every` | 8 |
| seed | 93 (per-run seed recorded in `runs_meta`) |
| worker | patched build only; K is retargeted through the mmap word |
| thermal gate | 40 C before every process |

Expected wall clock ~18 min. Expected usable ladder blocks ~1764 after the
1-in-8 placebo, ~252 in-session placebo blocks.

## Preregistered sigma

Scaling the placebo SE by `sqrt(1302/1764)`:

- **K=40 vs K=0 contrast: sigma = 1.43 us/step, preregistered upper bound
  `sigma <= 2.0 us/step`.**
- Slope: `SE <= 0.009 us/dispatch`.

Against the assignment's targets this is 12x inside the 25 us/step ask and
6x inside the 12 us/step stretch target. Variance is no longer the binding
constraint on this rig; bias is.

Predicted K=40 delta is 40 x 0.751 = **30.0 us/step**, i.e. ~21 sigma.

## Decision rules (frozen)

1. **Resolution of K=40** — pass if the 95% CI excludes 0.
2. **Slope recovery** — report us/dispatch with CI. Consistency with #483's
   0.751 us/dispatch is *reported*, not required: #483 is an M5 number and the
   whole point of this rung ladder is to measure the M4->M5 ratio.
3. **Linearity** — pass if the per-rung implied us/dispatch CIs mutually
   overlap **and** the quadratic term's implied curvature at K=240 is under
   10% of the linear prediction. R^2 on four points is not reported as a
   linearity test.
4. **Carryover** — fit `us ~ K + K_prev` with block fixed effects absorbed.
   Report lambda-hat with CI. If its CI excludes 0, report the slope both
   with and without the term.
5. **In-session placebo** — every placebo delta must cover 0. If not, the
   ladder result is reported as contaminated.
6. **Validation arm** — the run-paired `perrun` K=240 minus K=0 delta must
   agree with 240x the ladder slope inside its own (much wider) CI. This is
   the switching-free cross-check.
7. **Outliers** — per-rung median + 8 x MAD x 1.4826; any flagged step drops
   its **whole block**. Primary estimator is the censored block mean;
   secondary is Hodges-Lehmann; uncensored is reported as sensitivity. No
   common-threshold winsorising or trimming of the treatment estimate.
8. **Bootstrap** — 4000 nested resamples, process -> run -> block, seed 93.
   The full slope bootstrap array is written to JSON so the M4/M5 transfer
   factor can be formed as a bootstrap-of-ratio.

## Transfer factor

The M5 arm of this ladder is maple-tanjiro's PR #496, run independently. The
ratio is formed afterwards from the two saved bootstrap arrays as an
independent two-machine bootstrap-of-ratio, with the delta method as a
closed-form check. The linearity gate must pass **on both machines** before a
ratio is quoted, and the result is a dispatch-overhead transfer factor only,
not a general M4->M5 factor.

## Known limits, stated up front

- `maximum(y,y)` blocks buffer donation, so a rung is an upper bracket on
  per-dispatch cost, not a per-dispatch floor (rule 46).
- Randomisation removes the drift *bias* but the drift itself is still there;
  block FE absorb it.
- Stage 1 saw heavy-tailed slow runs land unevenly across binaries. That
  motivates the censoring rule and the robust secondary estimator.
