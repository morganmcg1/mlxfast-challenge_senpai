Receipt **R2 of 4**. Two knobs are on, each at the value that makes the injected
work exactly one extra full copy of that block's real per-pass work:

* one extra decode-step copy of the attention q/k/v/o NVFP4 QMV pair in **every**
  one of the 40 layers, each binding the attention bank 20 layers away. Added
  weight traffic: **802.16 MB per decode step**, which is precisely the traffic
  the scored attention QMV pair itself reads in a decode step -- about 45% of the
  step's total weight traffic.
* one extra 512-row copy of the sorted routed-expert gather-GEMM block (sort,
  fused gate/up gather-GEMM, down projection, unsort) in every one of the 39
  routed layers, each binding the routed bank 20 layers away. The injected
  routing pattern is uniform over all 256 experts with exactly 16 rows each, so
  every copy streams a complete expert bank once. Added weight traffic:
  **17,666.41 MB**; added arithmetic: **1,005.02 GFLOP**.

Because each injection duplicates the block exactly, the difference between this
receipt and the anchor is the block's own in-situ cost, and
`block_work / delta_time` is its achieved rate with no extrapolation.

The two knobs land on different axes -- one on the 128 single-token decode steps,
one on the 512-token prefill forward -- so a single receipt yields two
independent rates without confounding either.
