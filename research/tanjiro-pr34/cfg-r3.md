Receipt **R3 of 4**. The prefill routed knob is back to zero, the decode
attention knob stays exactly where R2 had it, and the two remaining knobs come
on, each again sized to exactly one extra full copy of its block's real per-pass
work:

* one extra decode-step copy of the routed-expert top-8 gate/up NVFP4 QMV plus
  its down-reduce in every one of the 39 routed layers. Added weight traffic:
  **552.08 MB per decode step**, precisely what the scored routed QMV block
  itself reads -- about 31% of the step's total weight traffic.
* one extra 512-row copy of the attention q/k/v/o dense BF16 projections in every
  one of the 40 layers. Added weight traffic: **2,852.13 MB**; added arithmetic:
  **1,460.29 GFLOP**, which is about 52% of the whole prefill forward's
  arithmetic.

The prefill axis is differenced against the anchor, which has both prefill knobs
off, so the attention GEMM rate is measured against the unperturbed tree.

The decode axis is differenced against R2 rather than against the anchor, and
that is deliberate. Both receipts carry the same 40 injected attention copies, so
their difference is purely the routed QMV block. Matched M4 receipts show why it
matters: injected into an otherwise unperturbed decode step the routed block
appears to run at 305 GB/s, above the host's own achievable streaming rate,
because the scored step leaves memory cycles idle and the unchained injected
copies absorb them (that reading replicates: 305 and 294 GB/s in two separate
receipts). Measured in the already loaded step the same block reports 263 GB/s,
and in the exact analogue of this receipt's own pairing 250.5 GB/s -- within
3.1% of @maple-nezuko's isolated per-call figure. The loaded
pairing is the honest estimate of the kernel's own rate; the unloaded one is
reported too, as an upper bound and as a measure of the idle memory slack a
scheduler could exploit.
