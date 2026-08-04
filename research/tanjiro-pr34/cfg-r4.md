Receipt **R4 of 4**, and it carries two independent probes, one per axis.

On the **prefill axis**, the sorted routed-expert gather-GEMM block is injected at
a *second, lower* level: 20 extra copies instead of the 39 an earlier receipt in
this series used. Nothing else on that axis changes. Two levels of the same block
separate the block's marginal cost from any fixed cost that appears as soon as the
first copy is injected: matched local receipts on a previous-generation host fit
`delta = 3.7153 ms per copy + 13.78 ms`, so a single-level reading divides that
fixed term into the rate and understates it by about 9%. This receipt converts that
rate from a point estimate into a slope.

On the **decode axis**, the routed-expert top-8 gate/up QMV plus down-reduce is
injected in every one of the 39 routed layers: **552.08 MB per decode step**, one
extra full copy of that block. Differenced against the anchor it gives that block's
marginal cost in an otherwise unperturbed step; differenced against the receipt that
also carries the 40 attention copies it gives the *attention* block's cost measured
in an already loaded step. Matched local receipts show the loaded reading is the
accurate one -- it agrees with an independent isolated per-call dispatch table to
within 3%, where the unloaded reading is 12-26% optimistic because the unperturbed
step leaves memory cycles idle for unchained work to absorb.

The two probes cannot interfere: the injected decode copies are issued only on
single-token steps and the injected gather-GEMM copies only on multi-token forwards,
and the multi-token contribution to the decode axis is removed by subtracting the
same receipt's own measured prefill.
