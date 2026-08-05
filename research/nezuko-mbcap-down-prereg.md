# Pre-registration — PR #44 r3 deliverable A

Committed **before** the sweep runs. No ranked receipt is taken in r3; the
ranked channel is tanjiro's.

## What is on trial

My own r2 section-6 clause 3, which proposed a **new candidate law**: that the
transferable M4 timing proxy for boundary/overhead-class candidates is the
non-overlapped host time

```
gap = wall_per_steady_step - gpu_busy_union_per_steady_step
```

rather than M4 wall time. If true, a ~25 minute ranked receipt on the single
shared channel is replaced by a ~5 minute free M4 pre-screen for every future
dispatch-shape candidate. That is the reason it must be tested rather than
assumed.

The advisor's critique that blocks it: the proxy was only ever compared with M4
wall on the **upward** branch, where both agree that 200 is best. The branch
that matters is **downward**, where M4 wall is known to be wrong.

## Ground truth this proxy must reproduce (ranked M5, `ns`)

| cap | receipt | `ns` | d vs 200 |
| --- | --- | --- | --- |
| 50 MB | `3e6fdcb` | 2.503448 | **-1.608%** |
| 200 MB | `c3ce66e` | 2.544360 | 0 |
| 512 MB | `c747336` | 2.514737 | **-1.164%** |

Both neighbours are worse at 9-12 sigma against the 0.278% single-receipt `ns`
resolution floor, so only the **sign** of a proxy contrast has to be right.

M4 wall is 1-for-2 against this: it ranks 400/512/1024/2048 worse than 200
(correct) but ranks 50 MB **1.98% faster** than 200 (wrong sign, unprofiled r1
ABBA `research/nezuko-mbpb-levels.log`; -2.17% on the profiled r1 binary).

## Prior evidence, and why it is not yet an answer

Two single-replicate profiled sessions exist. They must not be pooled
(critique 2: the r1 profiled 200 anchor is 8.614 ms at 199 steady steps, the r2
profiled 200 anchor is 8.599 ms at 99 steady steps, and the unprofiled r1 200
anchor is 8.876 ms - a 3.2% spread larger than every arm effect).

Session r1-prof, 12:57-13:01Z, STEPS=200 (`research/nezuko-mbpb-profile.log`):

| cap | wall | union | gap | cbs |
| --- | --- | --- | --- | --- |
| 200 | 8.614 | 8.359 | 0.255 | 34 |
| 100 | 8.501 | 8.248 | 0.253 | 52 |
| 50 | 8.427 | 8.174 | 0.253 | 85 |
| 25 | 8.598 | 8.305 | 0.292 | 86 |
| 12 | 8.468 | 8.184 | 0.284 | 86 |

Session r2-prof, 13:41-13:48Z, STEPS=100 (`research/nezuko_mbpb_up_sweep.log`):

| cap | wall | union | gap | cbs |
| --- | --- | --- | --- | --- |
| 200 | 8.599 | 8.335 | 0.265 | 34 |
| 400 | 8.854 | 8.181 | 0.673 | 19 |
| 512 | 8.734 | 8.233 | 0.501 | 18 |
| 1024 | 8.874 | 8.248 | 0.626 | 13 |
| 2048 | 8.915 | 8.271 | 0.644 | 9 |

Correction to the advisor's critique 1 for the record: a profiled `gap` datum at
50 MB **does** exist (r1-prof, 0.253 ms). It is n=1, from a session that cannot
be pooled with the upward table, and it points the wrong way for my own
proposal, which is exactly why r3 runs.

## Design (fixed before running)

- One session, **one profiled binary** (`b6458d9` GPUPROF hooks re-applied),
  one `STEPS=120` recipe, fresh process per arm.
- Levels `{12, 25, 50, 100, 200, 400}`; 400 included so the upward anchor is
  in-session rather than cross-session.
- Order: one discarded warm-up arm at 200, then **F R R F** over the six levels
  (`12 25 50 100 200 400` / reverse / reverse / forward). Every level then has
  the same mean position in the session, so linear thermal or allocator drift
  cancels exactly. n = 4 timing arms per level, 24 measured arms.
- Statistic: `G(cap)` = mean over the 4 arms of per-steady-step `gap`;
  `W(cap)` likewise for `wall`. Contrast `dG(cap) = G(cap) - G(200)`, Welch t
  on n=4 vs n=4.
- Counts pass: one prefill-mode arm per level; prefill cb by differencing
  against the decode arms at the same STEPS.
- Validity checks that must hold in every arm: `dispatches = 406`,
  `divergences = 0`. `mlx_peak_gb` reported per cap to catch any allocator
  profile boundary at small caps.

## Decision rule

**Session validity precondition.** The profiled binary must reproduce the known
M4 wall failure: `W(50) < W(200)` at t >= 3. If wall does *not* fail in this
session, the session cannot discriminate the two proxies and the outcome is
AMBIGUOUS whatever `G` does.

**CONFIRM — gap becomes validated programme law and a standing free
pre-screen.** All three of:

1. `G(200)` is the strict minimum over all six in-session levels;
2. `dG(50) > 0` with t >= 3;
3. `dG(400) > 0` with t >= 3.

**REFUTE — retire clause 3 explicitly in section 6.** Either
`dG(50) <= 0`, or `dG(50) > 0` but t < 3 while the ranked M5 penalty at 50 MB is
-1.608%. In both cases the proxy is blind to a 1.6% ranked regression and cannot
pre-screen a candidate.

- **Sub-case ONE-SIDED (a refutation, not a rescue).** If additionally
  `dG(400) > 0` at t >= 3, the gap is recorded as a one-sided *hazard flag* for
  cap **increases** only: admissible to veto an arm, never to promote one. The
  general law is still retired.

**AMBIGUOUS.** If the pooled within-level sd of `G` exceeds 0.05 ms, or every
contrast including `dG(400)` has |t| < 3, report the spread and draw no law. I
will not round toward the hypothesis.

## Prediction I am committing to

From the r1-prof n=1 row I expect `G` to be **flat at 0.25-0.29 ms for every cap
<= 200** and to step up to ~0.67 ms at 400, i.e. `dG(50) ~ -0.002 ms` and
**REFUTE via the ONE-SIDED sub-case**. I expect `W(50) < W(200)` by about 2%,
reproducing the wall failure.

I am pre-registering the refutation of my own proposal. If the sweep instead
returns CONFIRM, that is a stronger result than my prediction and I will report
it as such.

## Secondary quantities (diagnostic, not decision variables)

- `gap x n_cb` per level, to test the fixed-per-buffer-submit-cost story that
  critique 3 attacks (r2 values 9.01 / 12.79 / 9.02 / 8.19 / 5.77 ms at
  200/400/512/1024/2048 - not constant).
- The 400 MB anomaly: lowest `gpu_busy` (8.181 ms) with the worst `wall`
  (8.854 ms). Whether it survives in-session replication.
- Per-command-buffer GPU idle-interval distribution from the same GPUPROF
  records (deliverable C's named discriminator, free from the stderr files this
  sweep already writes).
