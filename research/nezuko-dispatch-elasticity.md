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
