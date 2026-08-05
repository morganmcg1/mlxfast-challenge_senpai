# Decode dispatch elasticity census (maple-nezuko, PR #32 r2 deliverable B)

Question set by the advisor: the decode step measures 4.3224 ms on M5 against a
2.941 ms byte roofline. tanjiro's rates 2 and 4 cover 75.5% of per-step bytes
and explain only +0.106 ms of the 1.383 ms residual, so **~1.27 ms of decode is
not explained by any byte-rate model**. Two hypotheses:

- **H-dispatch.** The gap is host-side encode/commit cost that the GPU clock
  cannot see (standing rule 15 / PR #37: +4.1 us per dispatch plus ~1.2 us of
  command-buffer granularity; 406 scored dispatches x 4.1 us = 1.665 ms).
  Signature: residual tracks **dispatch count**, not bytes.
- **H-family.** One kernel family runs below its own byte rate. Signature:
  residual **concentrated** in a nameable target.

This census reads the same residual from the per-family side, by perturbing one
family's GPU work at a time and asking how much of that perturbation reaches
wall time. tanjiro's r2 reads it from the aggregate side by fitting
`dT(n) = max(0, n*c - slack)`. The two readings are deliberately independent;
agreement is evidence, disagreement is itself the finding.

## Instrument

`research/sweep_dispatch_elasticity.sh <steps> <split> <mode:substring> ...`
drives `research/decode_probe.py` with a local-only patch to
`Vendor/.../backend/metal/device.cpp` (restore with
`git checkout 1604524 -- Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.{cpp,h}`;
**not** part of the submitted surface, and HEAD reverts it).

Two injections, both keyed on a substring of the Metal pipeline name:

- `dup` re-dispatches every matching encode a second time behind
  `memoryBarrier(BarrierScopeBuffers)`: a synthetic slowdown of +1x that
  family's serial GPU time.
- `skip` drops the matching `dispatch_threadgroups`/`dispatch_threads` call: a
  synthetic speedup of -1x that family's GPU time.

The critical property: `maybeInsertBarrier()` and `buffer_ops_++` run **before**
either injection, and the duplicate does not increment `buffer_ops_`. Since
`needs_commit()` reads `buffer_ops_`, all three arms encode the **same number of
command buffers with the same boundaries**. Confirmed empirically: every arm in
this census reports `cbs=45.0`.

What `skip` removes is therefore exactly two things:

1. the **GPU execution** of that kernel, and
2. the host cost of `get_command_encoder()` + `dispatchThreadgroups()` -- the
   encode call itself.

All **argument binding** (`setBuffer`/`setBytes`) happens in the caller before
`dispatch_threadgroups` and is untouched, as is barrier insertion and command
buffer commit. So `d(gap)/d(dispatch count)` from a `skip` arm is a **lower
bound** on the exposed per-dispatch host cost, not the whole of it. That lower
bound is still a direct measurement of the quantity H-dispatch is about, which
no byte model can produce.

Both injected arms change decoded tokens by construction, so the probe's
divergence count is expected to be nonzero for them; they are throwaway
instruments, never a candidate. Every arm prints `GPUINJECT <MODE> bound
<name>` for each pipeline it actually matched, because a typo'd substring binds
nothing and is indistinguishable from a null result.

## Pre-registered readings

Per family, from `per steady step`:

- **fidelity** `d(gpu_busy_union) / T_family_isolated`. Should be ~1 for `skip`
  (and ~+1 for `dup`). A large deviation means the perturbation had side
  effects -- NaN-induced slow paths, a changed routing distribution, cache
  effects -- and the arm must be flagged rather than interpreted.
- **carry-through** `d(wall) / d(gpu_busy_union)`. ~1 = the family's GPU time is
  **byte-carrying**: removing it removes wall time. ~0 = **latency-absorbed**:
  the GPU time exists but the step does not get shorter without it.

## Pre-registered hypotheses being separated

The r1 data set a third hypothesis running. On the previous host the whole step
was 8.345 ms of `gpu_busy_union` plus **0.200 ms** of inter-CB host gap across
45 command buffers (~4.4 us per boundary), and `gpu_busy_sum == gpu_busy_union`
to 6 ns, i.e. command buffers never overlap. That geometry predicts a **single
global slack pool**, not a per-family property:

    d(wall) = max(0, d(union) - S),  S ~ 200 us/step

- **H-slack** predicts carry-through ~0.85 for a large family (`qkv_h64`,
  ~1363 us/step), partial for a mid family (K1, ~243 us), and ~0 for a small
  one (`gate_sp`, ~213 us; router ordinal, ~96 us) -- monotone in size, with a
  single threshold, and a pooled fit `d(wall) = a*d(union) + b` giving `a ~ 1`,
  `b ~ -S`.
- **H-carry** (no slack) predicts carry-through ~1 everywhere and `b ~ 0`.
- **H-family** predicts one family with a carry-through and a byte rate that
  are both out of line with its neighbours.

r1 also reported one-sided elasticity for K1: a saving of -9.4 us/step at N=1
group decaying to ~0 at the shipped N~9, while added work carried through in
full. That decay sat **inside** the r1 gate noise (base 8378.7 +/- 12.0
us/step), so it may be a statistical artefact rather than a regime change.
This census perturbs by 200-1500 us against the same noise floor and settles it.

## Confound control

- Never `skip` a kernel whose output is an **index or address** consumed by a
  later gather: `residual_rms_router` and `decode_router_top8_ordinal` are
  measured with `dup` only. Garbage top-8 indices could produce out-of-bounds
  expert gathers, which is a crash or a bogus timing, not a measurement.
- At batch 1 exactly 8 experts are gathered per step regardless of *which*
  experts routing picks, so a degenerate routing distribution does not change
  gathered bytes. Value-only corruption is therefore safe for the byte model.
- NaN propagation is full-rate on Apple GPUs, so NaN-poisoned arms should not
  change timing; the fidelity metric is the check on that assumption.
- A duplicated read can be served from SLC, so `dup` fidelity below 1x is
  informative about cache residency rather than a bug in the instrument.
- Base arms are interleaved between injected arms so any thermal or DVFS drift
  shows up as base-to-base spread instead of contaminating one family.

## Arm list (as run)

Round 1 (`3fb91a20-3111-4185-8964-5271b16108a1`, 20 arms x 150 steps, SPLIT=0,
901 s, exit 0): 7 interleaved `base:` arms plus 9 `skip:` arms
(`routed_nvfp4_swiglu_qmv`, `oproj_act_h64`, `down_residual`,
`sliding_fused_attn`, `shared_nvfp4_swiglu_qmv`, `gate_sp`, `qkv_h48`,
`full_fused_attn`, `lmhead_int5`, `qkv_h64`) and 3 `dup:` arms
(`residual_rms_router`, `qkv_h64`, `shared_nvfp4_swiglu_qmv`).

Round 2 (`c9893c28-fe05-457b-a56b-56c84c51f8e1`, 14 arms x 150 steps, SPLIT=0):
5 interleaved `base:` arms plus 7 `dup:` arms (`oproj_act_h64`,
`routed_nvfp4_swiglu_qmv`, `down_residual`, `sliding_fused_attn`,
`full_fused_attn`, `gate_sp`, `lmhead_int5`), i.e. the same families as round 1
measured with the clean instrument only.

## Results

### Round 1: base reference

Seven interleaved base arms: wall **8548.7 +/- 34.9** us/step, GPU-busy union
**8283.7 +/- 23.3** us, gap **264.9 +/- 16.5** us, 45.0 commits/step, 406.0
dispatches/step. At SPLIT=0 `gpu_busy_sum == gpu_busy_union`, so no
command-buffer overlap is being double counted. The base-to-base spread means a
difference between two single arms carries about +/- 66 us at 2 sigma.

### Round 1: drift-corrected deltas

| arm | d(dispatch) | d(union) us | d(wall) us | d(gap) us | dup/skip fidelity | d(gap)/d(n) |
|---|---:|---:|---:|---:|---:|---:|
| `skip:routed_nvfp4_swiglu_qmv` | -39 | -1459.5 | -1505.5 | -46.0 | 1.03 | 1.18 |
| `skip:oproj_act_h64` | -30 | -292.0 | -312.7 | -20.7 | 1.07 | 0.69 |
| `skip:down_residual` | -40 | -394.0 | -445.3 | -51.3 | 1.13 | 1.28 |
| `skip:sliding_fused_attn` | -30 | -480.0 | -532.5 | -52.5 | 1.11 | 1.75 |
| `skip:shared_nvfp4_swiglu_qmv` | -39 | **+251.3** | +233.7 | -18.7 | 0.93 | 0.48 |
| `skip:gate_sp` | -40 | -10.3 | +14.3 | +24.7 | -1.39 | -0.62 |
| `skip:qkv_h48` | -10 | -390.3 | -390.3 | +0.0 | 1.00 | -0.00 |
| `skip:qkv_h64` | -30 | -541.0 | -538.0 | +4.0 | 0.99 | -0.13 |
| `skip:full_fused_attn` | -10 | **+62.3** | +60.3 | -2.0 | 0.97 | 0.20 |
| `skip:lmhead_int5` | -1 | -293.2 | -270.8 | +22.6 | 0.92 | -22.60 |
| `dup:residual_rms_router` | +39 | +161.6 | +184.4 | +23.2 | 1.14 | 0.59 |
| `dup:qkv_h64` | +30 | **+1048.4** | +1086.6 | +38.8 | 1.04 | 1.29 |
| `dup:shared_nvfp4_swiglu_qmv` | +39 | +175.2 | +202.8 | +29.4 | 1.16 | 0.75 |

### Round 1: headline fits

```
d(wall) = 1.0364 * d(union) + 2.10 us    R^2 = 0.9985   rms = 22.5 us   n = 13
d(gap)  = 0.7462 * d(n)     + 5.51 us    R^2 = 0.5083   rms = 21.4 us   n = 13
```

**Wall-clock decode time is an almost perfectly linear function of GPU-busy time
with unit slope and a near-zero intercept, and there is no usable
dispatch-count term.** Arms that moved the dispatch count by -40 to +39 moved
the non-GPU-busy gap by at most ~52 us out of a 265 us base gap, while moving
GPU-busy time by up to 1.5 ms. This is the quantitative statement that the
recoverable decode time lives *inside* GPU-busy, not around it, and it demotes
the host-dispatch hypothesis for this class of machine.

### Round 1: instrument validity, and why `skip` is not usable

Every `skip` arm produced 147-150 token divergences out of 150 steps: removing a
kernel removes its output, so downstream kernels consume stale or garbage
buffers and their *data-dependent* cost changes. Dispatch counts stayed exactly
at base+d(n) in every arm, so the confound is within-kernel work only, never
dispatch structure. Every `dup` arm produced **0 divergences**, because
re-dispatching an idempotent kernel behind a barrier recomputes the same result.

**Conclusion: `dup` is the clean instrument and `skip` deltas must be read as
upper bounds contaminated by data-dependent downstream cost.** Round 2 therefore
re-measures every family with `dup` only. Two `skip` arms are visibly broken by
this confound: `skip:shared_nvfp4_swiglu_qmv` and `skip:full_fused_attn` both
came out *positive*, i.e. removing 39 and 10 dispatches respectively made decode
slower.

### Round 1: marginal versus isolated cost

The pair of arms on `qkv_h64` is the most informative single result:

| instrument | d(union) us | per call us | reading |
|---|---:|---:|---|
| `dup:qkv_h64` (+30) | +1048.4 | 34.9 | cost when serialised behind a barrier |
| `skip:qkv_h64` (-30) | -541.0 | 18.0 | cost recovered by deleting it |

The isolated cost is about twice the marginal cost, so **roughly half of this
family's GPU time is already overlapped with neighbouring work**. Any accounting
that ranks optimisation targets by isolated per-call time will overstate the
prize by up to 2x. `skip:gate_sp` is the extreme case: removing 40 dispatches
changed union by -10 +/- 66 us, i.e. `gate_sp` is entirely latency-absorbed and
worth nothing to optimise, despite being 40 dispatches per step.

That asymmetry is the organising result of this census: families divide into
*byte-carrying* work whose time is genuinely on the critical path, and
*latency-absorbed* work that is already hidden. Only the first group is
recoverable.

## Round 2: the clean instrument applied to every large family

Round 1 established that `dup` is the trustworthy instrument (0 divergences in
every `dup` arm; 147-150 in every `skip` arm). Round 2 ran `dup` for the seven
families round 1 had only measured with `skip`, with five interleaved `base`
arms for drift control.

Log `c9893c28-fe05-457b-a56b-56c84c51f8e1`, 14 arms x 150 steps, SPLIT=0, exit 0
in 531 s. **All 14 arms reported 0 divergences**, so every number below comes
from a run that emitted the reference token stream exactly.

Base reference, n=5: wall **8522.2 +/- 9.7** us/step, union **8272.4 +/- 7.8**,
gap **249.6 +/- 13.1**, 45 command buffers, 406 dispatches. Base spread over
five interleaved arms is 19 us on union, so a single-arm delta resolves to about
+/- 16 us at 2 sigma - four times tighter than round 1.

| arm | dn | d(union) us | d(wall) us | d(gap) us | carry d(wall)/d(union) |
| --- | ---: | ---: | ---: | ---: | ---: |
| `dup:routed_nvfp4_swiglu_qmv` | +39 | +1446.3 | +1488.3 | +42.7 | 1.03 |
| `dup:down_residual` | +40 | +753.7 | +814.7 | +62.7 | 1.08 |
| `dup:oproj_act_h64` | +30 | +686.7 | +725.7 | +38.3 | 1.06 |
| `dup:sliding_fused_attn` | +30 | +580.3 | +600.3 | +20.3 | 1.03 |
| `dup:lmhead_int5` | +1 | +405.5 | +464.0 | +58.5 | 1.14 |
| `dup:full_fused_attn` | +10 | +193.7 | +236.3 | +42.7 | 1.22 |
| `dup:gate_sp` | +40 | +178.3 | +218.7 | +40.3 | 1.23 |

`d(wall) = 1.0002 * d(union) + 43.2`, **R^2 = 0.9990**, rms 12.6 us, n=7. The
slope is now indistinguishable from 1.0: added GPU work lands on wall time at
par. `d(gap)` versus `d(n)` fits with **R^2 = 0.0405** and a negative slope.
Across both rounds the gap is insensitive to dispatch count over 366-446
dispatches. That is a second independent refutation of a per-dispatch host cost
model on this host.

## The recovery ratio: what a family is actually worth

> **SUPERSEDED -- DO NOT RANK WORK OFF THIS SECTION.** Round 3 below measures the
> serialised budget directly and shows the `skip` deltas used here under-report
> removable time by about 2x, because every `skip` arm corrupts the residual
> stream and randomises downstream expert routing. The "recovery ratio" column
> and the "46.7% recoverable / 53.3% shared floor" split are retracted. The
> section is kept because the `dup` column in it is still valid and is reused in
> round 3 as a first-touch measurement. Use the round 3 table for ranking.

Combining the instruments gives, per family, the cost of one extra call (`dup`)
and the time returned by not running it at all (`skip`). Their ratio is the
fraction of the family's GPU time that is on the critical path rather than
overlapped with neighbours.

| family | calls | recoverable us/step | isolated us/step | rec us/call | iso us/call | recovery ratio | % of union |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `routed_nvfp4_swiglu_qmv` | 39 | 1459.5 | 1446.3 | 37.42 | 37.08 | **1.01** | 17.64% |
| `decode_nvfp4_qkv_h64` | 30 | 541.0 | 1048.4 | 18.03 | 34.95 | 0.52 | 6.54% |
| `sliding_fused_attn` | 30 | 480.0 | 580.3 | 16.00 | 19.34 | **0.83** | 5.80% |
| `down_residual` | 40 | 394.0 | 753.7 | 9.85 | 18.84 | 0.52 | 4.76% |
| `decode_nvfp4_qkv_h48` | 10 | 390.3 | - | 39.03 | - | - | 4.72% |
| `lmhead_int5` | 1 | 293.2 | 405.5 | 293.20 | 405.50 | 0.72 | 3.54% |
| `oproj_act_h64` | 30 | 292.0 | 686.7 | 9.73 | 22.89 | 0.43 | 3.53% |
| `gate_sp` | 40 | 10.3 | 178.3 | 0.26 | 4.46 | 0.06 | 0.12% |
| `full_fused_attn` | 10 | -62.3 | 193.7 | -6.23 | 19.37 | **-0.32** | -0.75% |
| `shared_nvfp4_swiglu_qmv` | 39 | -251.3 | 175.2 | -6.44 | 4.49 | **-1.43** | -3.04% |
| `residual_rms_router` | 39 | - | 161.6 | - | 4.14 | - | - |

`recoverable` is `-d(union)` of the round-1 `skip` arm; `isolated` is
`+d(union)` of the `dup` arm. Both are us per decode step.

**Only one family is fully byte-bound.** `routed_nvfp4_swiglu_qmv` has ratio
1.01: every microsecond it spends is on the critical path, and it is 17.6% of the
step by itself. It is the one family where an isolated-time ranking is honest,
and the correct target for work reduction.

**Isolated time overstates most prizes by about 2x.** `decode_nvfp4_qkv_h64`
costs 34.95 us/call isolated but returns 18.03 us/call when removed;
`oproj_act_h64` returns 43% of isolated; `down_residual` 52%. A roofline or
per-kernel-timer ranking - including my own earlier table - inflates those three
by 1.9x, 2.3x and 1.9x. The sum of isolated costs over measured families is
5630 us, 68% of the 8272 us step, but the sum of *recoverable* time is only
3860 us, **46.7%**. The other **53.3% is a shared floor no single family owns**,
which is why per-kernel optimisation on this model keeps returning less than its
microbenchmark promises.

**Two families have a negative prize.** Removing `full_fused_attn` made decode
62 us *slower*; removing all 39 `shared_nvfp4_swiglu_qmv` calls made it **251 us
slower** - both far outside round 1's +/- 66 us resolution. They are not merely
hidden: they occupy capacity the scheduler otherwise fills with something more
expensive, or warm state a later kernel reuses. Either way, no restructuring of
them can pay at the step level.

That closes the hypothesis this PR was originally assigned. The shared-expert
QMV family is 4.49 us/call isolated, 2.1% of the step, with *negative* marginal
value. The r1 gate measured the staged variants at +8.3 +/- 7.6 us/step against
base - a null - and the census explains why a null was the only available
outcome: there was never 243 us of shared-expert critical-path time to win. The
r1 body measurement of -4.5% on the kernel itself was real, and landed entirely
inside the overlapped region.

## Where the recoverable time actually is

1. `routed_nvfp4_swiglu_qmv`, 1459 us, ratio 1.01 - genuinely byte-bound.
2. `decode_nvfp4_qkv_h64` + `_h48`, 931 us combined, ratio ~0.5.
3. `sliding_fused_attn`, 480 us, ratio 0.83 - the highest ratio of any large
   family, so unlike the QMV and oproj families its time is nearly all exposed.
4. `down_residual`, 394 us, ratio 0.52.
5. `lmhead_int5`, 293 us, ratio 0.72, one dispatch.

`sliding_fused_attn` is the interesting entry: only 5.8% of the step, but 0.83 of
its time is exposed, and it is the one large family whose cost is *not* a
weight-streaming bound.

## Sliding attention: geometry, and a correction to my own diagnosis

Static reading of both fused attention kernels in
`Sources/MLXFastModel/LagunaRuntimeModel.swift`:

| | sliding (`ring_v1`) | full (`grow_v1`) |
| --- | --- | --- |
| name literal / dispatch | :1382 / :1793 | :1857 / :2310 |
| heads | 64 (`LagunaConfig.swift:26`) | 48 (`:24`) |
| grid / threadgroup | `((heads/2)*1024,1,1)` :1799 / `(1024,1,1)` :1800 | same :2316 / :2317 |
| threadgroups | **32** | **24** |
| simdgroups per TG | 32 | 32 |
| threadgroup memory | **18432 B** | **18432 B** |
| gqa | 8 :1386 | 6 :1867 |
| kv positions | `constexpr N = 512` :1406 | runtime `writeIdx+1` :1886 |
| layers per step | 30 | 10 |

Each threadgroup handles a query-head *pair* (`head0 = pair_tg*2`, :1409-10 /
:1881), hence `heads/2` threadgroups. Inside a threadgroup the work is
decomposed three ways: 32 simdgroups partition kv positions by residue mod
`BN=32` (`int i = sg` :1529 / :2005, `i += 2*BN` :1530), and the 32 lanes of each
simdgroup split `head_dim` four-wide (`qk_per_thread = 4` :1395). The 18432 B is
`outputs[4*BN*BDP]` float = 16896 B (:1495 / :1972) plus four bfloat[128]
staging arrays at 256 B each (:1416-19 / :1892-95) plus `max_scores[2*BN]` and
`sum_exp_scores[2*BN]` at 256 B each (:1496-97 / :1973-74).

Two claims that were circulating - including in my own earlier notes - are
**wrong** and should stop being repeated:

- "the kernel launches about 8 threadgroups". It launches **32** (sliding) and
  **24** (full).
- "kv-position parallelism is missing, so a split over kv positions is the
  prize". kv parallelism **already exists and is already 32-way**: each simdgroup
  visits only 16 of the 512 sliding slots, eight trips of two with no tail
  (:1512-14). More kv splitting adds nothing *and* would change the reduction
  order.

I also had the mechanism wrong. I attributed the 36%-of-bandwidth reading to
under-occupancy and predicted the deficit would get *worse* from 20 to 40 GPU
cores. An independent design review of the kernel source disagrees on both
points, and I think it is right:

- The 36% figure is **real but not causal**. The DRAM floor for this kernel is
  ~8.1 us/call against ~19-22 us measured; the system-level cache absorbs the
  4x K/V re-read, so the kernel is not starved of bandwidth. The binding
  constraint is the ~18 KiB of threadgroup memory, which permits roughly **one
  resident threadgroup per GPU core** and turns the launch into a two-wave
  latency-limited execution.
- Consequently my "the small machine understates the win" claim is **mostly
  wrong for sliding attention**: at 32 threadgroups on 20 cores and 32 on 40
  cores, both hosts sit about 2x above the packed floor, so the M4 reading does
  not systematically understate M5. It is directionally right only for the
  **full-attention twin**, which offers 24 threadgroups: on a 40-core M5 Max
  that leaves 16 cores provably idle for the 10 full-attention layers of every
  step, a deficit that does not exist on a 20-core host at all.
- The realistic recoverable figure for sliding attention on this host is
  **~250-330 us/step**, not the ~428 us my bandwidth-ceiling arithmetic implied.
  That is consistent with the measured 480 us recoverable total: most, but not
  all, of it is reachable.

The bit-exact direction is **more lanes cooperating inside a threadgroup while
preserving the existing reduction order**, and specifically shrinking the
`outputs` footprint so more threadgroups are resident per core - the review
prices a per-plane combine staging scheme at ~4.2 KB with zero floating-point
risk, since it relocates the existing combine tree rather than re-partitioning
it. The same relocation argument means a 64x512 chain split can be bit-exact if
the existing chains and the existing combine tree are *moved* rather than
re-associated, which contradicts the blanket "split-K is not bit-exact" claim in
`research/maple-occupancy-quantization.md:183-186`. Reassociating the
`simd_sum`/`simd_max` epilogue (:1642-53, :1671-74) is *not* bit-exact and stays
out of scope.

Phase structure worth recording: QK-norm and RoPE run on simdgroups 0-3 only
(`if (sg < 3)` :1425, `else if (sg == 3)` :1463; full :1899), so 28 of 32
simdgroups wait at the barrier (:1471 / :1953); the phase-2 cache write uses
`sg == 0` of the writer threadgroups (:1481). Phase 3 is the only fully parallel
phase. Both kernels hardcode their own head count as `constexpr`, so the "other"
head count in `heads/2` is arithmetic only and not reachable from either kernel.

I am not proposing to implement any of this - attention kernel edits and the
`h*s=64` rebalance are fern's assignment (#30/#36). This section exists so the
corrected geometry, the measured 0.83 recovery ratio that justifies caring, the
residency mechanism, and the two retracted claims are on the record with line
numbers.

## Caveats

- Host is an M4 Pro, 20 GPU cores, 48 GiB, low-memory startup profile. Recovery
  ratios describe how much slack this scheduler has, so they are host-dependent.
  The *ordering* should transfer; the exact ratios should not be quoted for M5.
- `skip` arms diverge from the reference token stream after the first step.
  Dispatch counts stay exactly `base - dn`, so work *volume* is unchanged, but
  MoE routing selects different experts and weight locality differs. Recoverable
  numbers are good to a few percent, not exact.
- `dup` measures a second back-to-back identical call, which can hit
  system-level cache, biasing isolated cost *low* for the largest weight
  readers. Against the previous host's per-kernel timings,
  `routed_nvfp4_swiglu_qmv` agrees to 1.6% and `down_residual`,
  `sliding_fused_attn` and the shared QMV to within 8%; `oproj_act_h64` and
  `qkv_h64` disagree most and their isolated numbers are lower bounds.
- Undocumented per-core threadgroup-memory residency limits on M4/M5 are the
  central unknown behind the occupancy argument. The ALU-floor estimate carries
  about +/- 30%, and the cache behaviour is inferred from aggregate rates rather
  than hardware counters.
- Both instruments are off-surface: they live in a profiler build of
  `Vendor/mlx-swift/.../backend/metal/device.cpp`, which is **not** in
  `editablePaths`. Nothing in this census is submittable and no census code is in
  this branch's diff.

## Round 3: a serialised budget that refutes the recovery-ratio table

Everything above ranks families by *marginal* effect on the overlapped GPU union.
Round 3 measures the complementary quantity directly: with `SPLIT=1` every
dispatch gets its own command buffer, so each kernel runs alone on the whole
machine and the profiler reports a per-kernel serialised time.

Run `1c8aded9-029b-461e-95bb-9570606f7c47`, exit 0, 45 s, 250 steps, arm `base`,
**0 divergences**. Per steady step: wall 10.154 ms, `gpu_busy_sum` 8.850 ms,
`gpu_busy_union` 8.849 ms, gap 1.305 ms, 406 command buffers, 406 dispatches.
`sum == union` confirms full serialisation.

### The bracket: the decode step is ~93% serial

| quantity | us/step |
| --- | ---: |
| `SPLIT=1` serialised sum (each kernel alone, whole machine) | 8850.3 |
| `SPLIT=0` real overlapped union | 8272.4 |
| excess | 577.9 = **6.99%** of the step, 1.423 us/dispatch |

Giving every kernel the entire GPU to itself, one at a time, costs only 7.0%
more than the real overlapped step. Command-buffer overhead is inside that 7.0%
as well. So **inter-kernel overlap plus command-buffer overhead together account
for at most 7% of decode**: the step is ~93% one-kernel-at-a-time execution, and
per-kernel serialised time is very nearly an honest ranking metric.

That is the opposite of what the recovery-ratio table above concluded.

### The `skip` instrument under-reports by about 2x, and I retract its deltas

The censused families have a serialised total of 7358 us, but their round-1
`skip` deltas sum to only 3860 us of recoverable time -- **52%**. Under a 93%
serial step, removing a family's dispatches should recover nearly its full
serialised cost. It does not, so `skip` is measuring something else.

Likely mechanism: skipping any kernel corrupts the residual stream, so the
router's top-8 selection downstream becomes effectively random across 256
experts instead of correlated between layers. That destroys expert-gather
locality and makes the *surviving* MoE kernels slower, which partly cancels the
work that was removed. Every `skip` arm diverged (147-150 tokens), so every
`skip` arm has this confound, in the same direction, for every family.

Two corrections to my own earlier text:

- I described `skip` deltas as **upper bounds** on removable time. They are
  **lower bounds**, roughly half the true value. Retracted.
- The "46.7% recoverable / 53.3% unattributable shared floor" split is an
  artefact of that confound. The serialised budget accounts for **106.8%** of
  the step across 16 families with only 18.8 us unlisted, so there is no large
  unattributable floor. Retracted.

The `dup` arms remain valid -- 0 divergences, no data confound -- but they
measure the cost of an *additional, cache-warm* call, not the cost of the first.

### What `dup/serialised` actually tells us: first-touch cost

`true/call` is the serialised per-call time minus the 1.33 us command-buffer
floor. `dup/ser` is the round-2 duplicate cost divided by it.

| family | calls | serialised us/step | % of step | true us/call | dup/ser |
| --- | ---: | ---: | ---: | ---: | ---: |
| `routed_nvfp4_swiglu_qmv` | 39 | 1561.5 | 18.88% | 38.71 | 0.958 |
| `decode_nvfp4_qkv_h64` | 30 | 1402.3 | 16.95% | 45.41 | 0.770 |
| `oproj_act_h64` | 30 | 1183.1 | 14.30% | 38.11 | **0.601** |
| `down_residual` | 39 | 894.8 | 10.82% | 21.61 | 0.872 |
| `sliding_fused_attn` | 30 | 637.7 | 7.71% | 19.93 | 0.971 |
| `lmhead_int5` (4 kernels) | 4 | 505.0 | 6.10% | — | — |
| `decode_nvfp4_qkv_h48` | 10 | 378.7 | 4.58% | 36.54 | — |
| `gate_sp` h64+h48 | 40 | 325.6 | 3.94% | 6.76 | **0.659** |
| `residual_rms_router` | 39 | 319.2 | 3.86% | 6.85 | **0.605** |
| `oproj_act_h48` | 10 | 317.6 | 3.84% | 30.43 | — |
| `shared_nvfp4_swiglu_qmv` | 39 | 295.0 | 3.57% | 6.23 | 0.721 |
| `dense_gate_up_swiglu` | 1 | 267.4 | 3.23% | 266.02 | — |
| `full_fused_attn` | 10 | 259.9 | 3.14% | 24.66 | 0.785 |
| `decode_router_top8_ordinal` | 39 | 205.4 | 2.48% | 3.94 | — |
| `rmsbfloat16` | 41 | 143.3 | 1.73% | 2.17 | — |
| `dense_down_residual` | 1 | 135.0 | 1.63% | 133.65 | — |
| sum of listed | | 8831.5 | 106.76% | | |

A duplicate call costs 60-97% of the first. The spread is the useful signal:

- `dup/ser` near 1 (`routed_nvfp4_swiglu_qmv` 0.958, `sliding_fused_attn` 0.971,
  `lmhead_int5` 0.970) means a second call is as expensive as the first: the
  kernel is bandwidth- or occupancy-bound with nothing left in cache to reuse.
  Improving these needs a better kernel.
- `dup/ser` well below 1 (`oproj_act_h64` 0.601, `residual_rms_router` 0.605,
  `gate_sp` 0.659, `shared_nvfp4_swiglu_qmv` 0.721) means the *first* call pays a
  large first-touch weight-streaming cost that the duplicate does not repeat.
  For these, **fusing with a neighbour so the weights are touched once** is the
  lever, not making the arithmetic faster.

`oproj_act_h64` is the standout: 14.3% of the step, and 40% of its per-call cost
is first-touch. It is the strongest fusion candidate in the model.

### The r1 hypothesis of this PR, closed without the broken instrument

`shared_nvfp4_swiglu_qmv` is 295.0 us/step = **3.57%** of decode. The `-4.5%`
kernel-body win measured in r1 is therefore worth `0.045 x 295.0 = 13.3 us`, or
**0.160% of decode** -- below the `+/- 16 us` resolution of the instrument that
measured it. The r1 result of `+8.3 +/- 7.6 us` is exactly what a 13 us win
looks like through a 16 us aperture.

This closes the hypothesis on arithmetic that does not depend on the discredited
`skip` deltas at all, and it supersedes the "negative recovery ratio" reading:
the shared QMV is not *free*, it is simply too small a share of the step for a
4.5% body win to be measurable, let alone rankable.

### Sliding attention per-call time, cross-checked

This host now reads `sliding_fused_attn_ring_v1` at 21.26 us/call serialised
(19.93 us true), against 22.34 us/call on the previous host -- agreement within
5%, so my figure reproduces across hosts and rebuilds. fern's circulating
~30 us/call does not match either measurement; the nearest kernel to that value
is the full-attention twin `full_fused_attn_grow_v1` at 25.99 us/call. Worth
reconciling before either number is used to price an attention change.

### Reproduction

```bash
research/sweep_shared_qmv_staging.sh 1 250 base   # SPLIT=1 per-kernel table
python3 research/nezuko_serial_budget.py          # bracket + first-touch ratios
```
