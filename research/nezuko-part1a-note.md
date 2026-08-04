# Two deletions, no new mechanism — the decomposition control for the LM-head cascade family

**Model actually run:** Claude Opus 5, high reasoning effort.
**Coding agent / harness:** OpenHands, driven by the Senpai autoresearch
advisor/student controller.
**Local host:** Mac16,11 (M4 Pro), 48 GiB unified memory, 20-core GPU,
low-memory startup profile. The ranked host is an M5 Max / 128 GB, so every
local number below is directional evidence and the official paired M5 run is
the authority.

Student `maple-nezuko`, campaign `mlxfast-maple-20260804`, PR #20,
assignment `maple-2026-08-04d-lmhead-cascade`.

## What this archive is

This archive is **deliberately not a candidate**. It is one arm of a
four-receipt factorial design, and its only job is to let the other three
receipts be read correctly.

It contains the promoted frontier with exactly **two commits reverted and
nothing added**:

| reverted | what it was | files |
| --- | --- | --- |
| `9c1ad1c` | `MLX_MAX_OPS_PER_BUFFER` startup policy `200 -> 400` | `LagunaRuntimeWeights.swift` |
| `6ca0c71` | static-shape barrier elision in the NAX `fp_qmm_t` k-loop | `fp_quantized_nax.cpp`, `fp_quantized_nax.h` |

Three files, +18/−7. Both mechanisms came from a submission-corpus harvest of
seven commits; the other five are untouched and remain in this archive. Both
were measured **individually inert** at harvest time, and one of them was the
prime suspect for a `S +0.236%` prefill regression that the harvest carried,
which is why the correct move is deletion rather than another env switch.

## Why it is worth a receipt

The sibling receipts in this family carry these two deletions *plus* an
LM-head decode cascade that removes ~25.7 MB/token from the read stream. With
only the cascade family and an unmodified-base control, every difference is
the sum of two mechanisms and neither can be priced. This archive is the third
point that separates them:

```
C0  = promoted base                                  (3 banked receipts)
X   = C0 - 9c1ad1c - 6ca0c71                         (this archive)
Y   = X + LM-head cascade                            (3 receipts)

X - C0  = the two deletions alone
Y - X   = the LM-head cascade alone   <- the number that prices the arm
Y - C0  = the two combined, i.e. what a naive family comparison reports
```

The cascade is the mechanism a DRAM-saturation model of the decode step
predicts should be worth `+0.91%` of score. That prediction is about the
cascade, not about the deletions, so testing it requires `Y - X`, not
`Y - C0`. Getting this wrong in either direction — crediting the cascade with
a deletion effect, or hiding a cascade effect behind a deletion regression —
would mis-price every remaining byte-removal experiment on the board.

I am also reporting these families on a renormalised statistic rather than on
the published score. On this account, three byte-identical archives published
`2.491470`, `2.500092` and `2.514743` — a 0.934% spread on *identical code* —
because the pinned baseline's prefill term is bimodal with a ~3.6% mode gap.
Pooled over 27 degrees of freedom the published score carries cv 0.489% while
the renormalised statistic carries 0.149%. A single receipt of anything, this
one included, is not evidence; a family is.

## Correctness

No new mechanism, so there is nothing here that can change an output token
that was not already changed by the promoted frontier. The vendored-Laguna
upstream-equivalence oracle exercises both reverted code paths — the NAX
`fp_qmm_t` k-loop is used by every routed-expert GEMM, and the ops-per-buffer
policy is dispatch-level — and reports, against the bf16 reference:

```
decode-0 .. decode-7   maximumAbsoluteLogitError = 0   all 8 tokens match
prefill                maximumAbsoluteLogitError = 0.125,
                       meanAbsoluteLogitError = 0.011933609, token 5991 == 5991
```

The prefill triple is byte-identical to the value recorded for the unmodified
base, i.e. the reverts are numerically inert as expected. The nonzero prefill
figure is the known bf16-vs-NVFP4 batched-path gap, not a regression.

## Honest limitations

- One receipt. `X` is n=1 against an n=3 control, so `X - C0` carries a larger
  standard error than the other contrasts in this family and should be read as
  a decomposition aid, not as a standalone claim about the two deletions.
- Local M4 timing does not transfer for these two mechanisms the way byte
  removal does. One of them is a dispatch-batching policy and the other is a
  Metal barrier elision inside an `is_nax_available()` path; both are
  generation-sensitive in a way that a byte count is not. The official run is
  the only measurement of them I will quote.
- This archive is expected to score at or near the promoted base. If it scores
  materially *above* it, that is itself the finding: it would mean the harvest
  shipped a real regression rather than two inert commits.
