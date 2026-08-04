Receipt **R4 of 4**, and it carries two independent probes, one per axis.

On the **prefill axis**, the sorted routed-expert gather-GEMM block is injected at
a *second, lower* level: 20 extra copies instead of the 39 an earlier receipt in
this series used. Nothing else on that axis changes. Two levels of the same block
separate the block's marginal cost from any fixed cost that appears as soon as the
first copy is injected. Four matched local levels on a previous-generation host --
0 (two replicates), 10, 20 (three replicates) and 39 copies -- give segment slopes
of 3.694, 5.039 and 3.788 ms per copy: non-monotone, so the apparent curvature two
levels suggested is scatter rather than a fixed term. A least-squares fit over all
four levels gives 4.138 ms per copy with an intercept of 576.09 ms against a
measured 0-copy anchor of 576.571 ms, i.e. linear through the origin with no fixed
per-forward cost, and the single-level 39-copy reading agrees with the slope to
within 1.3%. This receipt tests that conclusion on the ranked host, where the
single-level rate is already in hand and a disagreeing slope would retract it.

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
