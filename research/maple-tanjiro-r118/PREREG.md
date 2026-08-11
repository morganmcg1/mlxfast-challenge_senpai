# R118-A pre-registration — is the shared gate+up QMV excess real, and does it survive tau?

Branch `maple-tanjiro/r118-shared-gateup-qmv-excess`, PR #709, revision
`r118-a-rev1`.  Written before the main campaign was launched; the numbered
predictions below are the ones the campaign is allowed to be judged against.

## 1. What the 66 us/step actually is

The brief prices the target as "58 % of peak, ~66 us/step excess".  I can name
that number exactly, because I generated half of it in R110:

| quantity | value | source |
|---|---|---|
| in-situ cost of `laguna_shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1` | 7.39 us/call, 39 calls/step, 288.0 us/step, 3.35 % of profiled busy | `research/maple-tanjiro-r110/nibble-evidence/p1_0.log` |
| same kernel text, same geometry, standalone cold rig | 5.637 us/call = 197.7 GB/s | R110 F1, `qmv-geometry-evidence/` |
| difference | **1.75 us/call x 39 = 68 us/step** | — |

So the "excess" is the gap between what this kernel costs *in the decode loop*
and what the identical text costs *alone on the same GPU*.  R110 F5b already
showed the gap is not in the kernel text: a sibling-frontier prediction of
`1.01 us + bytes/251.7 GB/s` lands within -0.04 % of the standalone measurement
and 29.96 % below the in-situ one.  R110 F1 further showed the shipped geometry
is the fastest of eight bit-identical arms, so it is not a tiling mistake
either.  What is left is a claim about the *decode loop*, not about the kernel.

## 2. Honest repricing before building anything

The brief prices the target at 0.26 % of score at tau = 1.  Campaign-measured
tau is not 1.  My own measurement is 0.54, CI [0.29, 0.79]
(`L-PROFILED-BUSY-OVERPREDICTS-WALL-2X`); cedar's is [0.27, 0.43] (#699); the
overlap is [0.29, 0.43] and the campaign default is 0.4.

| tau | value of recovering the whole 68 us/step |
|---|---|
| 1.00 | 0.26 % |
| 0.54 (mine) | **0.14 %** |
| 0.40 (campaign default) | 0.10 % |
| 0.35 (cedar) | **0.09 %** |

Against a per-draw sd of 0.4938 % this is 0.19-0.28 sd, i.e. worth roughly
15-19 lottery draws of the ~36-46 remaining.  It is real money and it is worth
one shift of work.  It is **not** worth an official draw: the official channel
cannot resolve 0.14 %, it is hard-limited to one in-flight submission, and
spending a draw to measure this would cost more than the thing is worth.  This
gets settled on my rig or reported as a failure.  No official draw will be
requested on this branch.

Note also that the whole 68 us/step is the *ceiling* of the prize, reached only
by making the in-situ kernel as cheap as the cold standalone one.  Any realistic
change recovers a fraction of it.

## 3. The measurement

One binary, one env var `DARKBLOOM_SHARED_QMV_ARM`, seven arms, all AOT.  Two
builds are not allowed to be compared on this host: build-to-build drift is
1.08 % decode / 2.52 % prefill across provably identical trees, which is ten
times the effect being chased.

| arm | kernel | K blocks read (of 4) | role |
|---|---|---|---|
| `ship` | shared gate+up QMV | 4 | shipped name, shipped MSL, byte for byte |
| `ctl` | shared gate+up QMV | 4 | byte-identical clone under a different name — **negative control** |
| `d2` | shared gate+up QMV | 2 | byte dose, -21.7 MB/step |
| `d1` | shared gate+up QMV | 1 | byte dose, -32.6 MB/step |
| `rctl` | routed gate+up QMV | 4 | byte-identical clone under a different name |
| `rd2` | routed gate+up QMV | 2 | **positive control**, -174 MB/step |
| `rd1` | routed gate+up QMV | 1 | **positive control**, -261 MB/step |

MLX keys its Metal library cache on the kernel name
(`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp:602,770`), so a
renamed clone of identical source forces an independent compile of identical
text.  That is what `ctl`/`rctl` buy: everything that differs between arms
except the bytes.

The dose arms compute a deliberately wrong activation.  They are an instrument,
never a candidate.  `decode_probe.py` is teacher-forced, so every arm walks the
identical token sequence with identical dispatch shapes; only the bytes differ.

Ranking is done at `DARKBLOOM_GPU_PROFILE_SPLIT=0`, no profile hook anywhere:
the hook inflates wall ~2x on this host and mis-ranks.  **The measured quantity
is wall-clock d(wall)/d(byte), so it needs no tau correction at all.**  That is
the point of the design.

Design: 6 blocks of 4 runs per order, every block a permutation of the four arms
drawn from a Latin square, so monotone session drift cancels in the block
contrast.  400 decode steps per run, first 8 discarded, so 2400 measured steps
per arm per order.  `ORDER_B` is the element-wise mirror of `ORDER_A` under
`0<->3, 1<->2` and is analysed and reported **separately**; agreement between
the two mirrored orders is the credibility check.  Bootstrap 95 % CI on the
**median** paired saving, resampling blocks; the mean is reported alongside.
Raw per-step samples go to CSV.  Pooled per-arm samples get a bimodality screen;
bimodal means instrument failure, histogram, stop.

## 4. Byte accounting (pre-registered, from the source)

Shared gate+up QMV, per call: 1024 weight rows x 1024 packed bytes = 1.048 MB,
plus 1024 x 64 B halved scales = 0.066 MB, plus 4 KB of input.  1.118 MB/call
unique, 43.6 MB/step over 39 calls.  One 512-wide K block is 278.5 KB/call =
10.86 MB/step.  Observed rate 1.118 MB / 7.39 us = **151 GB/s**.

Routed gate+up QMV, per call: 8 expert slots x 512 logical rows x 2 rows x 1024 B
= 8.39 MB, plus 0.52 MB of scales.  8.91 MB/call, 348 MB/step.  One K block is
2.23 MB/call = 86.9 MB/step.  Observed rate 8.91 MB / 38.98 us = **228 GB/s**,
i.e. this kernel is already at the measured streaming ceiling (R110 F2: 224-227
GB/s for a ~1.2 MB dispatch).

## 5. Pre-registered predictions

Positive control (must hold or nothing else in the report counts):

* **P0** `rd2` saves 700-900 us/step and `rd1` saves 1050-1350 us/step, both
  intervals excluding zero.  These are the 174 / 261 MB/step removed divided by
  215-250 GB/s.  If the control lands inside this band the rig converts bytes to
  wall at the expected rate and a null on the shared kernel is a statement about
  the shared kernel.  If the control is itself null, the rig is blind, and the
  only publishable finding is a rig report.

Negative control:

* **P1** `ctl`'s paired interval contains zero.  If it does not, stop and
  report the rig (brief's rule, and mine).

The three live hypotheses for the shared kernel, with numbers:

* **H-bw** the excess is bandwidth-side and the kernel sits on the critical
  path at its observed 151 GB/s: `d2` saves **144 us/step**, `d1` saves
  **216 us/step**.
* **H-ceiling** the marginal byte is served at the 225 GB/s streaming ceiling
  and the rest is fixed: `d2` saves **96 us/step**, `d1` saves **145 us/step**.
* **H-fixed / H-hidden** the kernel's cost is fixed (launch, tail, latency,
  occupancy) or is not on the wall critical path at all: `d2` and `d1` save
  **~0**, and the fitted intercept absorbs essentially the whole 7.39 us/call.

`H-fixed` and `H-hidden` are separated by the positive control: under `H-fixed`
the rig still converts the routed kernel's bytes to wall per **P0**; under
`H-hidden` it does not.

## 6. Decision rule, written down before the data

Let `S1` be the measured median paired saving of `d1` (three quarters of this
kernel's bytes removed) with its bootstrap interval.

* If the upper end of `S1`'s interval is **below 68.7 us/step**, then removing
  three quarters of this kernel's device traffic does not even reach the Rule
  105.12 shipping bar (+30 us/step on M5 = +68.7 us/step on M4 = 0.251 % of
  score).  Since no legal transformation can remove more bytes than `d1` does,
  the byte-side of this target is closed: **terminal negative, do not ship,
  publish the law.**
* If the upper end is below 68.7 us/step but the interval excludes zero, the
  target is real but sub-bar; report the size and the price and still do not
  ship.
* If `S1` reaches or exceeds 68.7 us/step with an interval excluding zero, the
  byte side is live, and the follow-up is a real candidate that removes bytes
  without breaking the activation — reported with its tau correction in the same
  paragraph as the busy number, per the brief.

Landing rule, unchanged from the brief: ship only on a verified positive
interval excluding zero; neutral is do-not-land; correctness gate is
`research/run_upstream_equivalence.sh` reporting a non-zero test count
(Rule 105.15).  Nothing but `ship` is ever a shipping candidate.

## 7. Ownership and collisions

Nothing in this instrument touches `lagunaPackedPrefillScaleView`,
`lagunaLaneMajorNVFP4ScaleBank`, `lagunaHalvedGroup32ScalePlane`, the attention
family, or `device.cpp`.  The two kernels doctored here are both gated behind
one env var that defaults to the shipped text and the shipped kernel name, so
the default binary is the shipped binary.
