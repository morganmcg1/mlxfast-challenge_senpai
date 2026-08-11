# R119-C final result: TG count is inert for the shared-expert SwiGLU QMV

`L-LOAD-BALANCE-GRANULARITY` is **refuted** for this bandwidth-bound kernel.
Pre-registered branch `phi <= 0.15` fired.

## Design

Three arms widen the shared-expert SwiGLU QMV threadgroup while holding the
work byte-identical: 512 rows, 1 row per simdgroup, 512 simdgroups, 16,384
threads in every arm. Only the partition of those simdgroups into threadgroups
changes.

| arm | threads/TG | simdgroups/TG | TGs | local worst-core rows (C=20) | predicted delta |
|---|---|---|---|---|---|
| A | 64 | 2 | 256 | 26 | 0 % |
| B | 128 | 4 | 128 | 28 | +7.69 % |
| C | 256 | 8 | 64 | 32 | +23.08 % |

Ideal is 25.6 rows/core. phi is the measured fractional increase in the
kernel's GPU time divided by the predicted fractional increase in worst-core
rows. Granularity predicts phi ~ 1 and `delta(C)/delta(B) = 3.00`; a pure
threadgroup-size mechanism predicts `delta(C)/delta(B) ~ 1.00`.

## Result (raw SPLIT=1, n=6/arm)

Mirrored `64 128 256 256 128 64` x 3 blocks, 40 C gate per slot, 200 steps.
19/19 runs `rc=0`, 0 divergences.

| arm | qmv us/step | sem | us/call | delta vs A | if phi=1 | phi |
|---|---|---|---|---|---|---|
| A | 289.83 +-1.42 | 0.58 | 7.432 | - | - | - |
| B | 290.38 +-1.07 | 0.44 | 7.446 | +0.55 +-0.73 | +22.29 | +0.025 [-0.039,+0.088] NS |
| C | 294.50 +-0.85 | 0.35 | 7.551 | +4.67 +-0.68 | +66.88 | +0.070 [+0.050,+0.090] |

Through-origin slope over all 18 runs: **phi = +0.065 +-0.007, 95 % CI
[+0.052, +0.079]**. Common-mode-normalized (arm kernel scaled by the in-run sum
of 21 untouched kernels): **phi_norm = +0.072, CI [+0.061, +0.082]**.

## Why this is a confirmation, not a disappointment

Two independent results predicted this null before it was published:

- **nezuko R117-C `N42`** holds TG count at 256 while doubling simdgroups per
  TG, and reproduces her winning decode o_proj arm to within 1.4 us/step. TG
  count inert, per-core simdgroup residency live.
- **alphonse R119-A arm W** widens the same shared-expert host to
  `(256,1,1)` / 64 tiles, i.e. arm C reached from another direction:
  **-1.5 us/step, CI95 [-15.4, +12.5]**.

Arms A/B/C hold residency fixed at 512 simdgroups (25.6/core) by construction
and vary TG count 4x. That is the axis `N42` proved inert, so ~0 is the
predicted outcome. The contribution is the **cross-kernel complement**: `N42`
shows count-inert-at-fixed-residency on a decode attention projection at one
count; A/B/C shows it on a shared-expert MLP QMV over a 4x count range. Two
cells in two kernel families generalise the law from a site to a class.

Agreement is quantitative. My arm C, +4.67 +-0.68 us/step, sits **inside**
alphonse's arm W CI. Both exclude the phi=1 prediction of +59.4 us/step by far
more than 4x, and his point estimate is slightly negative.

## Shape: not a smooth granularity law either

`delta(C)/delta(B)` is +8.48 +-11.26 raw and +7.93 +-5.07 normalized. The CI
spans both 3.00 and 1.00, so the ratio alone cannot discriminate. The
pre-registered discriminator "B ~ C but both != A implies TG size, not
granularity" did **not** fire: B is indistinguishable from A (per-block sign
test B>A in only 2/3 blocks: +1.75, -0.20, +0.10) while C>A in 3/3 (+6.10,
+3.35, +4.55). The residue is a TG=256-specific threshold, not a smooth linear
granularity law. That is a shape-level refutation on top of the magnitude one.

## Negative control: the instrument was demonstrably sharp in these blocks

5 of 21 common untouched kernels drift beyond the +-0.655 us/step atlas
resolution, but all 5 are large kernels, so proportional drift is <= 0.24 %
(2.83/1502.33, 2.05/862.27, 1.98/1360.43, 1.82/1114.78, 0.75/369.65) against
the 1.61 % arm C effect. **Zero of 21 are monotone in arm**, and the largest
drifters trend downward with arm index, opposite in sign to the signal, so
drift cannot manufacture the arm C result and if anything understates it.

## Ranked geometry: the local null is a stronger ranked null

On the ranked 40-core M5 with 512 rows, ideal is 12.8 rows/core and worst-core
rows are `ceil(TGs/40) * rows_per_TG`:

| arm | TGs | ranked worst-core rows | ranked predicted delta | local predicted delta |
|---|---|---|---|---|
| A | 256 | 7 x 2 = 14 | 0 % | 0 % |
| B | 128 | 4 x 4 = 16 | +14.3 % | +7.69 % |
| C | 64 | 2 x 8 = 16 | +14.3 % | +23.08 % |

Arm C's predicted imbalance is 14.3 % ranked versus 23.08 % locally, so **this
host overstates arm C's granularity penalty by 1.61x**. Holding phi fixed, arm
C's ranked local-equivalent cost is 4.67 x (14.3/23.08) = **+2.89 us/step**
before any busy-to-busy transfer. A null measured against the inflated local
prediction is therefore an even stronger null on the ranked host.

Note also that the ranked geometry collapses B and C to the same 14.3 %, so it
cannot separate them at all. The local C=20 geometry is the more discriminating
instrument for this question, which is why the measurement belongs here.

## Correctness

- 64-step free-run decode identical in all three arms: hash
  `1d94c56de672c486`, distinct=49, `TOKENS_IDENTICAL` yes/yes.
- Upstream-equivalence reports byte-identical across all three arms: all 8
  decode steps exactly 0.0 error, every `runtimeToken == upstreamToken`.
- Prefill `maximumAbsoluteLogitError = 0.125` is pre-existing: the unmodified
  base `cd047c00` reproduces the identical report
  (`research/r119c-runs/correctness/equiv-base.log`).
- The wide-codes path (`values_per_lane = 32`) is untouched.

Selection is proved by distinct dispatched pipeline names, which bit-identical
output cannot show: arm A dispatched
`shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1` (name byte-identical to
shipped), B `..._tg128_bf16_v1`, C `..._tg256_bf16_v1`. Distinct names were
required because MLX caches compiled libraries by name; reusing one name
silently returns the first-compiled variant.

## Startup-profile provenance (`L-MEASURE-AT-RANKED-STARTUP-PROFILE`)

Measured by in-process `getenv` after the startup policy runs, not inferred:

| cell | OPS_PER_BUFFER | MB_PER_BUFFER | BFS_MAX_WIDTH | low_memory |
|---|---|---|---|---|
| atlas (nothing exported) | 64 | 128 | unset | true |
| exported 200/200/50 | 64 | 128 | **50** | true |
| ranked M5 (from source) | 200 | 200 | 50 | false |

New sub-finding: the low-memory policy uses `setenv(..., 1)` for the ops and MB
caps, so those exports are discarded, but it never sets `MLX_BFS_MAX_WIDTH`, so
a BFS export **does** survive. A partial export therefore yields a third
configuration that exists on neither host. Only
`DARKBLOOM_STARTUP_MEMORY_PROFILE=full` restores the ranked combination.

This is a GPU-busy kernel-attribution axis rather than a command-buffer
structure axis, so the profile does not invalidate phi; it is recorded as
provenance.

## Caveats

- Raw numbers only. No realized-fraction deflator, no C=40 correction applied
  to the measurement, no end-to-end anchor. Per `L-ONE-TRANSFER-CONSTANT`, each
  link is the advisor's to apply once.
- SPLIT=1 puts one kernel per command buffer, which **prevents** the
  inter-kernel overlap that would absorb the imbalance tail in production.
  Measured phi is therefore an upper bound on deployed cost.
- Minimum detectable phi is ~0.03 (B) and ~0.01 (C): a strong null, not an
  underpowered one.
- The a-priori range was phi ~ [0.2, 1.0] if per-core issue limits bind. The
  measured 0.07 sits below even the pessimistic end, consistent with the
  70.2 % DRAM-peak bandwidth ceiling absorbing the tail.
- The optional SPLIT=0 paired wall leg was not run.

## Suggested follow-up (not implemented)

A TG=32 arm (1 simdgroup/TG, 512 TGs) is the clean discriminator for the
residual TG=256 threshold: the imbalance model predicts it equal to arm A
(worst-core rows still 26), while TG-count or per-TG launch-overhead models
predict it slower than A. It is bit-identical by construction, so it can ride
an official ticket.

Do **not** pursue the residency axis on this kernel. 512 rows at one output row
per simdgroup forces 512 simdgroups; raising residency requires splitting K
across simdgroups and reducing, which regroups a floating-point sum and breaks
bit-identity. `passed_correctness: false` forfeits the whole submission.

## Reproduction

```bash
bash research/maple_r119c_correctness.sh
bash research/maple_r119c_base_equiv.sh
bash research/maple_r119c_atlas.sh
bash research/maple_r119c_envprov.sh
python3 research/maple_r119c_analyze.py research/r119c-runs/atlas
```

W&B group `r119c-shared-qmv-tg-granularity` in
`wandb-applied-ai-team/mlxfast-maple`: `t1efekwt` (A), `szqcqj81` (B),
`rq05afhc` (C), `k8kaa7uq` (summary).
