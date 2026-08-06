# PR170 arm S2 — regime discriminator for `fp_gather_qmm_rhs_expert_nax`

**This is a measurement arm, not a speed attempt. It is expected to be slower
than the promoted frontier and to be rejected on ranking.** It is the second of
three arms that name the binding constraint of the prefill routed gather GEMM.

## Why

On the promoted receipt `97a5090` (commit `3e165fa`) the routed gather GEMM
costs `W = 43.26 ± 0.40 ms` of the `97.89 ms` prefill wall, doing `1005.02
GFLOP` and moving `17.666 GB` of expert weights. Its arithmetic intensity,
`56.89 FLOP/B`, is *exactly* the ridge point of the assumed machine model
(`34.7 TFLOP/s ÷ 610 GB/s = 56.89`), so a roofline chart cannot separate the
compute axis from the bandwidth axis here: the familiar "67% of both rooflines"
is one measurement projected twice, not two independent facts. The binding axis
has to be measured. Arm M2 priced the arithmetic axis; this arm *adds* bit-exact
work on the load+dequant axis and reads the marginal wall cost, needing no
assumption that any theoretical peak is attainable in situ.

## What changed

One template parameter (`int probe`, default `0` = shipped kernel) on
`fp_gather_qmm_rhs_expert_nax`, plus the matching `mlx-generated` JIT twin and
a selector that appends `_pb_<n>` to the kernel name so the JIT library cache
cannot serve the control's binary for a probe arm.

**Arm S2 (`probe = 2`): double the weight load + dequant + staging.** A second
loader reads a neighbouring expert's weight block and dequantises it into the
same `Ws` tile immediately after the WAR barrier; one extra barrier separates
it from the real staging pass, which then overwrites the tile in full. Offline
`metal-objdump` of the optimised AIR confirms the intended effect: device loads
`6 -> 8`, threadgroup stores `+1`, barriers `+1`, and the MMA count unchanged
at 1. Threadgroup memory stays at 9232 B and occupancy at 3 threadgroups/core.

## Bit-exactness

`probe = 0` is the default in every path, so the shipped kernel is unchanged.
The shadow staging pass is fully overwritten by the real `loader_w` staging
before any consumer reads `Ws`, with an intervening threadgroup barrier, so no
value the MMA sees can differ. Every checked greedy token is expected to match
exactly.

## Reading

`ΔS2` is the marginal prefill wall cost of a second weight-load + dequant +
staging stream, read against the measured wall `W`. It also carries the one
extra barrier that bit-exactness requires, which arm B2 prices separately (the
stock k-loop has 2 barriers per iteration; B2 adds 2 and S2 adds 1). Because
two barriers may coalesce rather than cost double, the pure load cost is
reported honestly as the **interval** `[ΔS2 − ΔB2, ΔS2 − ΔB2/2]` rather than a
single point; that interval is only wide enough to flip a verdict when `ΔB2`
already exceeds `0.20·W`, in which case synchronisation is the headline anyway.
Peaks enter once, as a floor: the doubled kernel moves `~35.3 GB`, which at the
most generous sanctioned rate (`651.8 GB/s`) cannot complete in under
`54.21 ms`, so `ΔS2 ≥ 10.95 ms` on any honest measurement, and a measured
`ΔS2 < 9.5 ms` is read as instrument failure rather than as "loads are free".

_Submitted by an AI agent (OpenHands) on behalf of morganmcg1._
