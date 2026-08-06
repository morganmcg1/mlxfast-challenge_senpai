# PR170 arm B2 — regime discriminator for `fp_gather_qmm_rhs_expert_nax`

**This is a measurement arm, not a speed attempt. It is expected to be slower
than the promoted frontier and to be rejected on ranking.** It is the third of
three arms that name the binding constraint of the prefill routed gather GEMM.

## Why

On the promoted receipt `97a5090` (commit `3e165fa`) the routed gather GEMM
costs `43.26 ± 0.40 ms` of the `97.89 ms` prefill wall while sitting at 67% of
*both* its compute and its bandwidth roofline — a `+14.30 ms` excess that
neither roofline alone explains. Arms M2 and S2 price the two work streams;
this arm prices the schedule itself.

## What changed

One template parameter (`int probe`, default `0` = shipped kernel) on
`fp_gather_qmm_rhs_expert_nax`, plus the matching `mlx-generated` JIT twin and
a selector that appends `_pb_<n>` to the kernel name so the JIT library cache
cannot serve the control's binary for a probe arm.

**Arm B2 (`probe = 3`): double the k-loop barrier count.** Two extra
`threadgroup_barrier(mem_flags::mem_threadgroup)` calls per k-iteration, both
threadgroup-uniform and outside any divergent region. The stock loop carries 2
barriers per iteration, so this is an exact doubling to 4. Offline
`metal-objdump` of the optimised AIR confirms barriers `+2` with device loads,
threadgroup loads, threadgroup stores and MMA count all unchanged — the
compiler did not merge them. Threadgroup memory stays at 9232 B and occupancy
at 3 threadgroups/core.

## Bit-exactness

`probe = 0` is the default in every path, so the shipped kernel is unchanged.
Additional barriers are pure synchronisation and cannot change any value; every
checked greedy token is expected to match exactly.

## Reading

`ΔB2` is the marginal cost of doubling synchronisation. If it is large, the
kernel's `+14.30 ms` excess over both rooflines is schedule latency rather than
work, and the next mechanism is barrier removal / occupancy rather than fewer
FLOPs or fewer bytes. A small `ΔB2` closes that hypothesis — this arm is
dispatched last precisely so that the large deltas already observed on M2 and
S2 establish that the instrument reaches the kernel, which makes a small `ΔB2`
interpretable instead of ambiguous.

_Submitted by an AI agent (OpenHands) on behalf of morganmcg1._
