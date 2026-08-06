# PR170 arm M2 — regime discriminator for `fp_gather_qmm_rhs_expert_nax`

**This is a measurement arm, not a speed attempt. It is expected to be slower
than the promoted frontier and to be rejected on ranking.** It is dispatched
deliberately to name the binding constraint of the prefill routed gather GEMM.

## Why

On the promoted receipt `97a5090` (commit `3e165fa`) the routed gather GEMM
costs `43.26 ± 0.40 ms` of the `97.89 ms` prefill wall while sitting at 67% of
*both* its compute and its bandwidth roofline — a `+14.30 ms` excess that
neither roofline alone explains. Reducing work has therefore been guesswork.
This arm *adds* bit-exact work on one resource axis and reads the marginal wall
cost, which is a direct measurement of which axis is binding.

## What changed

One template parameter (`int probe`, default `0` = shipped kernel) on
`fp_gather_qmm_rhs_expert_nax`, plus the matching `mlx-generated` JIT twin and
a selector that appends `_pb_<n>` to the kernel name so the JIT library cache
cannot serve the control's binary for a probe arm.

**Arm M2 (`probe = 1`): pure MMA doubling.** A shadow accumulator tile runs a
second `tile_matmad_nax` per `kk1` step against an already-resident A fragment
and the same staged `Btile`. Offline `metal-objdump` of the optimised AIR
confirms the intended and *only* effect: MMA instruction count `1 -> 2`, with
barriers, device loads, threadgroup loads and threadgroup stores all unchanged.
Threadgroup memory stays at 9232 B and occupancy stays at 3 threadgroups/core.

## Bit-exactness

`probe = 0` is the default in every path, so the shipped kernel is unchanged.
The probe's shadow accumulator is never mixed into `D`; its only consumer is a
sink guarded by `run_skip_pct > 1000`, and `run_skip_pct` is host-clamped to
`[1, 100]`, so the guard is unreachable while still defeating dead-code
elimination. Every checked greedy token is expected to match exactly, and any
mismatch here would be a bug in the instrument rather than a precision change.

## Reading

Both streams cost ~28.99 ms in isolation, so doubling either one must cost
between `+14.7 ms` (added work fully absorbed by the existing stall) and
`+28.99 ms` (fully serial). A near-zero `ΔS` on this arm would mean the arm did
not reach the kernel rather than that MMA is free, and the campaign stops to
debug instead of spending the remaining arms.

_Submitted by an AI agent (OpenHands) on behalf of morganmcg1._
