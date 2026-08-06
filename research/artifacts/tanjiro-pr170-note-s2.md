# PR170 arm S2 — regime discriminator for `fp_gather_qmm_rhs_expert_nax`

**This is a measurement arm, not a speed attempt. It is expected to be slower
than the promoted frontier and to be rejected on ranking.** It is the second of
three arms that name the binding constraint of the prefill routed gather GEMM.

## Why

On the promoted receipt `97a5090` (commit `3e165fa`) the routed gather GEMM
costs `43.26 ± 0.40 ms` of the `97.89 ms` prefill wall while sitting at 67% of
*both* its compute and its bandwidth roofline — a `+14.30 ms` excess that
neither roofline alone explains. This arm *adds* bit-exact work on the
load+dequant axis and reads the marginal wall cost.

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

The extra barrier is shared with arm B2, which isolates barrier cost alone, so
the pure load+dequant cost is reported as `ΔS2 − ΔB2/2` (the stock k-loop has 2
barriers per iteration; B2 adds 2 and S2 adds 1). Both streams cost ~28.99 ms
in isolation, so doubling either must cost between `+14.7 ms` (fully absorbed)
and `+28.99 ms` (fully serial).

_Submitted by an AI agent (OpenHands) on behalf of morganmcg1._
