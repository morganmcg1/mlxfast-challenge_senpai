# PR170 arm M2 — regime discriminator for `fp_gather_qmm_rhs_expert_nax`

**This is a measurement arm, not a speed attempt. It is expected to be slower
than the promoted frontier and to be rejected on ranking.** It is dispatched
deliberately to name the binding constraint of the prefill routed gather GEMM.

## Why

On the promoted receipt `97a5090` (commit `3e165fa`) the routed gather GEMM
costs `W = 43.26 ± 0.40 ms` of the `97.89 ms` prefill wall, doing `1005.02
GFLOP` and moving `17.666 GB` of expert weights. Its arithmetic intensity,
`56.89 FLOP/B`, is *exactly* the ridge point of the assumed machine model
(`34.7 TFLOP/s ÷ 610 GB/s = 56.89`), so a roofline chart cannot separate the
compute axis from the bandwidth axis here: the familiar "67% of both rooflines"
is one measurement projected twice, not two independent facts. The binding axis
has to be measured. This arm *adds* bit-exact work on the arithmetic axis and
reads the marginal wall cost — an instrument that needs no assumption that any
theoretical peak is attainable in situ, because the measured wall is its own
denominator.

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

`ΔM2` is the marginal prefill wall cost of a second, identical MMA stream, and
it is read against the measured wall `W`, not against a peak. Peaks enter once,
in the only direction they are trustworthy: the doubled kernel issues `2010
GFLOP`, which at the `34.7 TFLOP/s` peak cannot complete in under `57.93 ms`
*even with perfect overlap*, so `ΔM2 ≥ 14.66 ms` is a floor on any honest
measurement. A measured `ΔM2 < 13.0 ms` (that floor less ~12% for receipt noise
and peak optimism) is therefore read as **instrument failure** — the arm did not
execute as intended — and not as "MMA is free"; the campaign stops to debug
rather than spending the remaining arms. Above the floor, `ΔM2` is compared
with the S2 arm's load-axis cost under decision rules registered before any
receipt was spent.

_Submitted by an AI agent (OpenHands) on behalf of morganmcg1._
