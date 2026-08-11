# R118-A smoke: the rig converts bytes to wall, and it is calibrated

Two n=1 shakedown sessions, 40 decode steps each, SPLIT=0, one process at a
time, single binary switched by `DARKBLOOM_SHARED_QMV_ARM`.  These are *not*
the campaign; they exist to prove the instrument is wired before spending an
hour of wall clock on it.  Raw: `evidence/smoke/abba.tsv`, `evidence/smoke2/abba.tsv`.

## smoke: the shared-expert gate+up QMV (the target)

| arm  | bytes removed / step | mean ms | median ms | p10 | p90 | greedy divergences |
|------|---------------------:|--------:|----------:|----:|----:|-------------------:|
| ship |    0                 | 8.274   | 8.237     | 8.221 | 8.291 | 0 |
| ctl  |    0 (byte-identical)| 8.265   | 8.233     | 8.203 | 8.296 | 0 |
| d2   |  -21.7 MB            | 8.311   | 8.278     | 8.232 | 8.366 | 7 |
| d1   |  -32.6 MB            | 8.461   | 8.156     | 8.113 | 8.536 | 24 |

## smoke2: the routed gate+up QMV (the positive control)

| arm  | bytes removed / step | mean ms | median ms | p10 | p90 | greedy divergences |
|------|---------------------:|--------:|----------:|----:|----:|-------------------:|
| ship |    0                 | 8.275   | 8.243     | 8.221 | 8.281 | 0 |
| rctl |    0 (byte-identical)| 8.262   | 8.231     | 8.202 | 8.306 | 0 |
| rd2  | -174 MB              | 7.820   | 7.787     | 7.764 | 7.857 | 0 |
| rd1  | -261 MB              | 7.600   | 7.565     | 7.546 | 7.622 | 13 |

## What the positive control already establishes

The routed dose is *linear in bytes to three digits*:

    rd2   -174 MB/step  ->  -456 us/step   ->  2.621 us per MB/step
    rd1   -261 MB/step  ->  -678 us/step   ->  2.598 us per MB/step

so on this machine, in situ, at this dispatch size, removed weight traffic in
the gate+up QMV family converts to wall clock at

    k = 2.61 +- 0.02 us of decode wall per MB/step removed
      = 383 GB/s of effective *marginal* streaming rate.

Two things follow immediately.

1. **The rig is not blind.**  A byte-side effect of the size predicted for the
   shared kernel is far above this rig's resolution: the two byte-identical
   arms (`ctl`, `rctl`) sit 4 and 12 us from `ship`, i.e. the floor is
   ~0.15 % of a step, while the routed dose moved the step by 5.5 %.

2. **My pre-registered P0 band was too generous, and I am saying so before the
   campaign, not after.**  PREREG.md predicted rd2 in 700-900 us on the
   assumption that the routed QMV is byte-limited at its own average rate
   (348 MB/step over 1520 us busy = 229 GB/s).  Measured is 456 us, i.e.
   0.60x of the naive prediction.  That 0.60 is not a failure of the dose - the
   dose is provably linear - it is the busy-to-wall conversion factor tau
   showing up *inside a single kernel family*, and 0.60 sits inside the
   [0.29, 0.79] interval of my own L-PROFILED-BUSY-OVERPREDICTS-WALL-2X.  The
   campaign will measure it directly with a profiled arm pair rather than
   infer it.

## What the smoke says about the target (n=1, not a result)

Applying the measured k = 2.61 us per MB/step to the shared kernel's own dose:

    d2   -21.7 MB/step  ->  predicted -57 us/step
    d1   -32.6 MB/step  ->  predicted -85 us/step

Observed at n=1: d2 was 41 us *slower* than ship, d1 was 81 us faster with a
p10-p90 spread three times ship's.  So the honest reading of the smoke is
"nothing is resolvable at n=1 and the d1 point is consistent with either the
byte model or zero".  That is exactly why the campaign is 10 blocks x 2
mirrored orders and not four runs.  Nothing here is quoted as a result.

The divergence counts (7 for d2, 24 for d1, 13 for rd1) confirm the dose lands
on the scored decode path.  rd2 producing 0 divergences over 40 greedy steps is
luck, not evidence of a no-op: it moved the step by 456 us.
