Receipt **R3 of 4**. The two R2 knobs are back to zero and the other two come on,
again each sized to exactly one extra full copy of its block's real per-pass
work, and again on two different axes:

* one extra decode-step copy of the routed-expert top-8 gate/up NVFP4 QMV plus
  its down-reduce in every one of the 39 routed layers. Added weight traffic:
  **552.08 MB per decode step**, precisely what the scored routed QMV block
  itself reads -- about 31% of the step's total weight traffic.
* one extra 512-row copy of the attention q/k/v/o dense BF16 projections in every
  one of the 40 layers. Added weight traffic: **2,852.13 MB**; added arithmetic:
  **1,460.29 GFLOP**, which is about 52% of the whole prefill forward's
  arithmetic.

R3 is differenced against the same anchor as R2 rather than against R2 itself, so
each of the four rates is measured against the unperturbed tree. That keeps every
rate independent of the others and avoids reading a second rate out of an already
perturbed machine state.
