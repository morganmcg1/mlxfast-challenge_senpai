# Shared-expert QMV load staging and packed cross-lane reduction

Assignment `maple-2026-08-04h-shared-qmv-staging` (PR #32), revision `r1`.
Base `9a407ed699f6127754efde955e85756a327af040`.
Host: AWS Mac M4 Pro, 48 GiB (`Mac16,11`), low-memory startup profile.
Measured sequential read ceiling on this host: **260.2 GB/s**.

## Causal question

Does hoisting device loads above the cross-lane reductions in the two
shared-expert QMV kernels reproduce the officially measured M5 `-0.689%`
decode result from the field?

Two separable sub-mechanisms:

- **A1** - stage the next K block's weight words into registers before the
  current block's `simd_sum`. Pure instruction scheduling; bit-identical.
- **A2** - replace N scalar `simd_sum(float)` calls with one
  `simd_sum(vec<float,N>)`.

Two kernels:

- **K1** = `laguna_shared_nvfp4_swiglu_qmv_rows1_bf16_v1` (shared-expert
  gate/up projection).
- **K3** = `laguna_routed_shared_nvfp4_down_residual_bf16_r1_v5` (merged
  routed + shared down projection with residual).

## Answer

**No, not on this tree, and the reason is measurable rather than mysterious.**

A1+A2 makes the K1 *kernel body* reproducibly **4.5% faster**, and that
improvement **decays monotonically to exactly zero as command-buffer
co-residency rises to the shipped level**. At shipped batching the paired
step-level effect is `+8.3 +/- 7.6 us/step` - a null with the wrong sign. The
advisor's `-40 us/step` gate is excluded at more than six standard errors, and
even the arithmetically predicted `-17 us/step` carry-through is excluded at
about three.

K3 is a different story from the field's K3: ours is the *merged* routed+shared
down projection at 89% of this host's read ceiling. It is saturated, and A1
makes it slightly worse.

## Part 0 - structural preconditions

Checked before measuring, because fern's #24 rule 5 (`mem_flags::mem_device`
fences defeat load hoisting) would have killed the arm outright:

| check | result |
| --- | --- |
| `mem_flags::mem_device` in the whole runtime file | **0 occurrences** |
| K1: `threadgroup_barrier` / `simdgroup_barrier` | **0** |
| K3: `threadgroup_barrier` | exactly **1**, line 7722, in the epilogue only |
| K3 row loop | barrier-free |

So rule 5 carries no weight against this arm, and both row loops are
trivially software-pipelineable. Precondition satisfied.

## A2 bit-exactness - verified here, not borrowed

`research/nezuko_simdsum_check.swift` is a standalone `swiftc` + Metal harness.
Each reduction form lives in its own kernel so the compiler cannot CSE them
together.

| comparison | bit-pattern mismatches |
| --- | --- |
| `simd_sum(float4)` vs 4x `simd_sum(float)` | **0 / 131072** |
| 2x `simd_sum(float2)` vs 4x `simd_sum(float)` | **0 / 131072** |
| **power control**: reversed-mask butterfly vs `simd_sum` | **46540 / 131072 (35.5%)** |

The power control is the point: the same corpus provably *does* detect an
association-order change, so the two zeros are evidence rather than an
insensitive test.

Corpus: 8 adversarial families - uniform, magnitude ladder spanning `2^20`,
catastrophic cancellation, mantissa ties, denormal mix, random bit patterns,
one-huge-many-small, and alternating exact powers of two.

Caveat: this is the M4 compiler and hardware. Apple does not document
`simd_sum` vector reduction order, so M5 could in principle differ; the
exact-token gates would catch it.

## Off-path identity

`research/nezuko_offpath_identity.py` asserts that with every flag off, both
kernel source texts are **byte-identical** to `BASE_SHA` (K1 2254 chars, K3
3110 chars). Re-verified after the depth-2 variant was added. So the default
build is provably the unchanged baseline and the env gates cannot leak.

## Measurements

`research/sweep_shared_qmv_staging.sh <split> [steps] [arm ...]`.
`DARKBLOOM_GPU_PROFILE_SPLIT=N` caps dispatches per command buffer, so `N=1`
gives single-dispatch attribution and `N=0` keeps the shipped policy
(~9 dispatches/CB, 45 CBs / 406 dispatches per step).

Every arm below: **0 token divergences** on the teacher-forced check.

### Kernel bodies (SPLIT=1, 39 calls/step, 149 steady steps = 5811 samples/run)

| kernel / variant | us/call | vs base |
| --- | --- | --- |
| K1 base (2 independent runs: 7.56, 7.52) | **7.54 +/- 0.03** | - |
| K1 `st1_pk2` = A1+A2 (2 runs: 7.12, 7.27) | **7.20 +/- 0.08** | **-4.5%** |
| K1 `st2_pk2` = stage all 4 K blocks | **8.40** | **+11.7%** |
| K3 base | 22.93 | - |
| K3 A1 (staged) | 23.15 | +0.96% |
| K3 A2 (packed float4) | 22.94 | +0.04% |

K1's improvement is real: consistent sign across two independent runs, and
larger than the run-to-run drift of an unmodified control kernel measured in
the same runs (K3 read 22.92 / 23.33 / 22.94 us/call across three arms whose
K3 code is byte-identical, i.e. `+/-1.8%` drift).

`st2` is a clean regression that independently reproduces the field's
"stack more staging and it gets worse" rung.

### Carry-through to step time - the decay curve

Measured by sweeping dispatches per command buffer. Column 2 sums every
K1-containing dispatch group; column 3 is the same for the `st2` regression.

| dispatches/CB | A1+A2 effect (us/step) | `st2` effect (us/step) |
| --- | --- | --- |
| 1 | **-9.4** | +34.6 |
| 2 | **-6.2** | - |
| 4 | **-1.2** | +28.6 |
| ~9 (shipped) | **~0** | +55 (whole-step union) |

The speedup decays **monotonically to zero** with co-residency. This is the
signature of neighbouring dispatches backfilling K1's memory stalls: the
latency A1 removes from inside the kernel is latency the shipped schedule was
already hiding from outside it. It is *not* a cold-start artifact - a
cold-machine artifact would collapse abruptly at 2 dispatches/CB rather than
decay smoothly across 1 -> 2 -> 4 -> 9.

Note the **asymmetry**: making K1 slower is carried through in full, while
making it faster is absorbed. K1 sits right at the co-residency-hidden
boundary. Step time is elastic to added work on this kernel and inelastic to
removed work - which prices *any* future K1 latency optimisation on this tree
at approximately zero.

### Paired step time at shipped batching (SPLIT=0, 400 steps, 399 steady, interleaved n=3)

| arm | `gpu_busy_union` us/step | mean | vs base |
| --- | --- | --- | --- |
| base | 8378, 8391, 8367 | **8378.7 +/- 12.0** | - |
| A1+A2 both kernels | 8385, 8393, 8383 | **8387.0 +/- 5.3** | **+8.3** |
| K1 only | 8384 (n=1) | - | +5 |
| `st2` deep staging | 8434 (n=1) | - | **+55** |

Welch: `diff = +8.3 us`, `se = 7.58`, `t = 1.10`, `p ~ 0.36`,
95% CI `[-14, +31] us`.

- advisor gate `-40 us`: **6.4 se** below the estimate - excluded.
- predicted carry-through `-17 us`: **3.4 se** below - excluded.

`both > base` on the median in all three pairs (8704/8693/8691 vs
8693/8676/8671), so the sign is consistent, not a coin flip.

An earlier n=1 pair had suggested `-23 us/step`. **That was drift.** The n=3
interleaved repeat falsified it. Recording this because it is exactly the
single-shot number that would have justified spending a receipt.

### Roofline - why K1 and K3 behave differently

Against this host's measured 260.2 GB/s ceiling:

| kernel | weight bytes/step | achieved | % of ceiling |
| --- | --- | --- | --- |
| K1 | 1.18 MB/call x 39 = **46.0 MB** | 157 GB/s (base) -> 162-166 GB/s (A1+A2) | **60% -> 62-64%** |
| K3 | 5.31 MB/call x 39 = **207 MB** | 232 GB/s | **89%** |

(Byte counts independently re-derived from the dispatch shapes: K1 reads 1024
rows x (1024 code B + 128 scale B); K3 reads 8 routed experts x 2048 x (256+32)
plus the shared 2048 x (256+32).)

Staging helps only the kernel with bandwidth headroom. K3 is already
saturated, so hoisting loads cannot add bytes/s and only adds live registers -
consistent with its `+0.96%`.

This also explains why the field's K3 result does not transfer: **their K3 was
the shared-only down projection at ~0.59 MB/call, latency-bound like K1. Ours
is the merged routed+shared kernel at ~5.31 MB/call.** The assignment's
"9x the lanes, so a bigger upside" reasoning inverts - 9x the lanes is
precisely what saturated it.

### Occupancy - no spill signature

| pipeline | maxTotalThreadsPerThreadgroup | tgMem |
| --- | --- | --- |
| K1 base | 1024 | 0 |
| K1 `st1_pk2` | 1024 | 0 |
| K1 `st2_pk2` | 1024 | 0 |
| K3 base / staged / packed | 1024 | 80 |

Unchanged everywhere, including the regressing `st2`. Honest reading: this
metric saturates at the device maximum, so it rules out a *severe* spill but
cannot rule out a moderate register increase. The "register pressure"
explanation for `st2` is therefore plausible but **not proven** by this
observable; what is established is that more staging is slower on a
bandwidth-saturating access pattern.

## What this says about the M5 prior

The mechanism found here does not say the field's M5 number is wrong. It says
the *carry-through* depends on per-core co-residency, and that is exactly the
axis on which M4 Pro and M5 Max differ:

- Decode grids are sized by output rows, not by machine width, so an M5 Max
  with roughly twice the cores runs the same fixed decode work at roughly half
  the per-core occupancy.
- The field's own M5 baseline implies a *lower* saturation fraction than this
  host achieves, so intra-kernel latency hiding has room there that it does
  not have here.

The aggregate arithmetic, summed over all 40 layers from the same per-kernel
byte derivation:

| term | bytes/step |
| --- | ---: |
| QKV (11.80 MB x 30 + 9.44 MB x 10) | 448.4 MB |
| o_proj (9.44 x 30 + 7.08 x 10) | 354.0 MB |
| routed MoE gate/up (9.44 x 39) | 368.2 MB |
| K3 routed+shared down (5.31 x 39) | 207.1 MB |
| K1 shared gate/up (1.18 x 39) | 46.0 MB |
| router (1.05 x 39) | 41.0 MB |
| dense layer 0 (67.1 + 33.6) | 100.7 MB |
| g_proj + attention KV (unique) | 92.1 MB |
| **total** | **~1657 MB/step** |

Independent cross-check: the field's officially measured M5 baseline reports
**~1794 MB/token**, about 8% above this derivation - consistent given the
`N=576` assumption for the growing full-attention cache. The table is
therefore corroborated by an official number, not just self-consistent.

- **this host**: 1657 MB / 8.379 ms = **198 GB/s** -> **76%** of its 260.2 GB/s
  ceiling (82% if the 1794 MB figure is used).
- **field's M5**: 1794 MB / 5125.5 us = **350 GB/s** -> **58-64%** of a
  plausible M5 Max ceiling (M4 Max is already 546 GB/s).

So the M5 is quantitatively *less* saturated than this host, which puts it in
the low-co-residency regime where the decay curve above still shows a gain,
while this host is in the high-co-residency regime where it is zero. That is a
falsifiable prediction, not a rescue: the decay curve predicts a *partial*
return, on the order of the field's `-0.24%` K1 rung, not the full `-0.689%`
ladder whose largest rung was their unsaturated shared-only K3.

**This cannot be settled on M4.** The M4 host can only show that the
mechanism exists in the kernel body and that this tree's schedule hides it.

## Disposition

The advisor gate - at least one kernel measurably down **and**
`gpu_busy_union` down by `>= 40 us/step` - is **not met**. The union moved
`+8.3 us`. I did not spend a receipt and did not take the queue slot.

I also did not add a third variation to rescue the result, per the stop rule.
The two obvious rescues are both out of scope anyway: reordering dispatches or
changing command-buffer composition would attack the co-residency term
directly, and the assignment excludes command-buffer caps.

Sub-mechanism verdicts:

- **A1 on K1**: real kernel-body win, zero step-level carry-through here.
- **A2 on K1**: verified bit-exact, small additive body win, no step effect.
- **A1 on K3**: negative. Drop it. Our K3 is saturated, unlike the field's.
- **A2 on K3**: neutral; only worth keeping as free simplification.
- **Depth-2 staging**: regression, do not pursue.

## Suggested follow-ups (not implemented)

1. **The lever on this tree is bytes, not latency.** The elasticity asymmetry
   means K1 latency work prices at zero while K3 sits at 89% of ceiling. Any
   win on K3 has to *remove bytes*.
2. If the advisor wants the M5 answer, the cheapest form is **K1-only A1+A2**
   (`st1_pk2`, K3 untouched): bit-exact, occupancy-neutral, byte-identical when
   gated off, and it is the single rung the field's evidence actually supports
   for a merged-K3 tree.
3. The co-residency decay curve is a **reusable instrument**. Any future
   latency-hiding proposal on this tree can be priced in ~5 minutes by checking
   whether its SPLIT=1 win survives to SPLIT=0, before a receipt is spent.
