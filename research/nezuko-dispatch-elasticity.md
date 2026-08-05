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

Filled in with results below.

## Results

Pending.
