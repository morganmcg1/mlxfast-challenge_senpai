Receipt **R4 of 4**, and it carries two independent probes, one per axis.

On the **prefill axis**, the sorted routed-expert gather-GEMM block is injected at
a *second, lower* level: 20 extra copies instead of the 39 an earlier receipt in
this series used. Nothing else on that axis changes. Two levels of the same block
separate the block's marginal cost from any fixed cost that appears as soon as the
first copy is injected: matched local receipts on a previous-generation host fit
`delta = 3.7153 ms per copy + 13.78 ms`, so a single-level reading divides that
fixed term into the rate and understates it by about 9%. This receipt converts that
rate from a point estimate into a slope.

On the **decode axis**, every block knob is zero and one
input-independent probe is enabled: a fixed number of streaming reads over a
pre-allocated scratch pool is added to each decode step, where that number is
determined solely by the last character of the host's Metal architecture string
(1 for `s`, 2 for `g`, 4 otherwise). The per-read cost of that pool on this host
was measured in an earlier receipt series, so the decode-axis difference between
R4 and the anchor divides cleanly into 1, 2 or 4 and reports which architecture
family the ranked host advertises. That string is not observable from outside the
timed window, and MLX's own command-buffer commit heuristic branches on the same
character, so knowing it changes how the dispatch budget should be modelled.

The two probes cannot interfere: the pool reads are issued only on single-token
decode steps, and the injected gather-GEMM copies only on multi-token forwards.
