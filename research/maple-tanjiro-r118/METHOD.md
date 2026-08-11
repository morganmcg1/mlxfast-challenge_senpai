# R118-A method, in the form the charge asked for

Target: `laguna_shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1`, 39 calls/step,
288.0 µs/step of profiled GPU-busy (3.35 % of the busy census), 7.39 µs/call
in situ against 5.637 µs/call for the same geometry on a standalone cold rig
(R110 F1, n=400) — the ~1.75 µs/call, ~68 µs/step "excess" this assignment
was chartered to adjudicate.

## 1. One binary, switched by an environment variable

`DARKBLOOM_SHARED_QMV_ARM` selects the arm at kernel-source-generation time
inside `LagunaRuntimeModel.swift`. Seven values:

| arm | family | K blocks read | bytes/step vs ship | what it is |
|---|---|---|---|---|
| `ship` | — | 4 | 0 | the shipped binary, byte-identical source |
| `ctl` | shared | 4 | 0 | **negative control**: renamed kernel, identical MSL body |
| `d2` | shared | 2 | −21.72 MB | half the K loop |
| `d1` | shared | 1 | −32.58 MB | a quarter of the K loop |
| `rctl` | routed | 4 | 0 | negative control on the sibling family |
| `rd2` | routed | 2 | −173.8 MB | **positive control**, half the K loop |
| `rd1` | routed | 1 | −260.7 MB | **positive control**, a quarter |

Two properties matter and both were verified by reading the generator, not by
trusting it:

* At `ship` the emitted MSL text **and the kernel name** are byte-identical to
  the shipped build. `lagunaR118Dose()` returns `(4, "")` unless the selected arm
  belongs to that kernel's family, and the name suffix is empty when the dose is
  4. So there is exactly one binary in this experiment and the two-build noise
  floor (2.52 % prefill / 1.08 % decode across provably identical trees) does not
  apply to any comparison below.
* `ctl` differs from `ship` **only** by the `_r118ctl` name suffix: same K bound,
  same prefetch guard, same body. It is the byte-identical negative control the
  charge required. If its interval excludes zero, the rig is reporting itself and
  every other number here is void.

`lagunaPackedPrefillScaleView` is not touched. Neither is `device.cpp`, except
under `pr91-gpuprof-hook.patch`, which is applied and reverted inside
`qmv-dose-profile.sh` and never present in a committed tree.

## 2. Paired, block-randomised, mirrored

Each **block** is one permutation of the four arms of a family, so every block
contains exactly one measurement of each arm and the paired contrast is taken
inside the block. Ten blocks per order for the shared family, six for the
positive control.

`ORDER_B` is the **exact time reversal of `ORDER_A`**, so the mean run index of
each arm is identical over the pair and any monotone drift in the host — thermal,
DVFS, page-cache — cancels between the two orders rather than loading onto one
arm. The two orders are analysed and reported **separately**, never pooled, so a
disagreement between them is visible instead of averaged away.

Each run is a fresh process: model load (~41 s), then teacher-forced decode with
`DARKBLOOM_GPU_PROFILE_SPLIT=0`, the ranking configuration. The first 8 steps of
every run are discarded as DVFS settling; everything after is kept, including
outliers.

## 3. What is measured, and how it is summarised

Per-step wall times are dumped raw and archived to
`evidence/<order>/raw-steps-<order>.csv` — every sample, with a `used` column
rather than a deletion, so the discard rule is auditable.

The statistic is the **median paired saving over blocks**, with a 95 % interval
from a **block bootstrap** (resampling whole blocks, 20 000 resamples), because
blocks are the independent unit here, not steps. The **mean is reported beside
it every time**, and where the two estimators disagree the disagreement is the
headline, not a footnote.

A four-hurdle bimodality screen runs on every arm's pooled sample before any
interval is quoted. If an arm is bimodal the run is an instrument report and the
analyser stops and prints the histogram.

## 4. Pre-registration

`PREREG.md` was committed before the campaign started and contains: the byte
accounting per arm, the four competing hypotheses with their predicted effect
sizes (H-bw, H-ceiling, H-fixed, H-hidden), the negative-control criterion, and
the decision rule stated as an inequality on d1's 95 % upper bound against the
68.7 M4 µs/step landing bar. `SMOKE.md` records, also before the campaign, that
the pre-registered P0 band for the positive control (700–900 µs) was 0.60× too
generous — the observed 2.61 µs/MB was written down as a miss rather than
quietly rescaled.

`PRICING-NOTE.md`, written **after** the data existed and labelled as such,
corrects a factor-2.2 pricing error inside PREREG. The decision rule itself is
applied verbatim and was not touched.
