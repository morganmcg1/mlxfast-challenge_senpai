# PR170 arm B2 — regime discriminator for `fp_gather_qmm_rhs_expert_nax`

**This is a measurement arm, not a speed attempt. It is expected to be slower
than the promoted frontier and to be rejected on ranking.** It is the third of
three arms that name the binding constraint of the prefill routed gather GEMM.

## Why

On the promoted receipt `97a5090` (commit `3e165fa`) the routed gather GEMM
costs `W = 43.26 ± 0.40 ms` of the `97.89 ms` prefill wall, doing `1005.02
GFLOP` and moving `17.666 GB` of expert weights. Its arithmetic intensity,
`56.89 FLOP/B`, is *exactly* the ridge point of the assumed machine model
(`34.7 TFLOP/s ÷ 610 GB/s = 56.89`), so a roofline chart cannot separate the
compute axis from the bandwidth axis here, and neither axis is known to be the
binding one. Arms M2 and S2 price the two *work* streams by adding one of each;
this arm prices the *schedule* — the cost that no roofline models at all.

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

`ΔB2` is the marginal prefill wall cost of doubling synchronisation, with no
FLOPs and no bytes added. Unlike M2 and S2 it has no peak-derived floor, since
no roofline prices a barrier — which is exactly why a large `ΔB2` would be the
most actionable outcome available here: it would say the wall is schedule
latency, and the next mechanism is barrier removal, deeper pipelining or higher
occupancy rather than fewer FLOPs or fewer bytes. `ΔB2` also calibrates the
barrier that arm S2 unavoidably carries, turning S2's raw delta into the load
interval `[ΔS2 − ΔB2, ΔS2 − ΔB2/2]`. This arm is dispatched **last** on purpose:
the deltas already returned by M2 and S2 establish that the instrument reaches
the kernel at all, which is what makes a *small* `ΔB2` an interpretable
negative result instead of an ambiguous one.

_Submitted by an AI agent (OpenHands) on behalf of morganmcg1._
