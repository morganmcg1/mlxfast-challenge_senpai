Receipt **R2 of 4**. Two knobs are on:

* 30 extra decode-step copies of the attention q/k/v/o NVFP4 QMV pair, one per
  layer on 30 of the 40 layers, binding the attention bank 20 layers away. Added
  weight traffic: 637.01 MB per decode step.
* 24 extra prefill copies of the sorted routed-expert gather-GEMM block (sort,
  fused gate/up gather-GEMM, down projection, unsort) at 512 rows, one per layer
  on 24 of the 39 routed layers, binding the routed bank 20 layers away. The
  injected routing pattern is uniform over all 256 experts with exactly 16 rows
  each, so each copy streams a complete expert bank once. Added weight traffic:
  10,871.64 MB; added arithmetic: 618.48 GFLOP.

Differencing this receipt against R1 yields the decode-axis achieved rate of the
attention QMV pair and the prefill-axis achieved rate of the routed gather-GEMM.
