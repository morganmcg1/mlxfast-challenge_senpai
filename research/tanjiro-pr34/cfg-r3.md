Receipt **R3 of 4**. Both R2 knobs stay at their R2 values and two more come on
at the same layer counts, so the injected layer sets and therefore the per-layer
submission bookkeeping are identical between R2 and R3:

* 30 extra decode-step copies of the routed-expert top-8 gate/up QMV plus its
  down-reduce. Added weight traffic: 424.67 MB per decode step.
* 24 extra prefill copies of the attention q/k/v/o dense BF16 GEMM at 512 rows.
  Added weight traffic: 1,711.28 MB; added arithmetic: 876.17 GFLOP.

Differencing R3 against R2 yields the decode-axis achieved rate of the routed QMV
block and the prefill-axis achieved rate of the dense attention GEMM, with every
fixed cost and both R2 injections held constant.
