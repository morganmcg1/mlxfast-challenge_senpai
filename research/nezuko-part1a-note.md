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
four-receipt factorial design, and its only job is to let the other
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
X   = C0 - 9c1ad1c - 6ca0c71                         (this archive, 2 receipts)
Y   = X + LM-head cascade                            (2 receipts, both landed)

X - C0  = the two deletions alone
Y - X   = the LM-head cascade alone   <- the number that prices the arm
Y - C0  = the two combined, i.e. what a naive family comparison reports
```

The last two receipts go 2/2 rather than 3/1 because that split dominates on
both decomposition contrasts — `Y - X` costs 1.000σ instead of 1.155σ, and
`X - C0` costs 0.913σ instead of 1.155σ — while giving up only 0.10σ on the
combined contrast, which is the one the other two already answer.

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

## Why the decomposition turned out to matter more than I expected

When I planned this design I treated `X` as insurance. The first two `Y`
receipts changed that.

Against the three-receipt control, `Y` moved the renormalised statistic by
**+0.455% ± 0.136%** and the pure decode step `T` by **−0.664% ± 0.203%**,
against a byte-model prediction of **+0.914%** and **−1.422%**. The effect is
real, on the right axis, and the prefill term `S` — which nothing in this
family should touch — moved `−0.080% ± 0.159%`, so the built-in negative
control is clean. But the realised magnitude is **0.50×** the prediction on
both axes simultaneously.

That factor is the whole result of the arm, and it is only attributable to the
cascade if the two deletions in this archive contributed nothing to it. Hence
this receipt. A `0.50×` conversion factor re-prices every remaining
byte-removal experiment on this board by a factor of two; a `0.50×` factor
that is really a larger cascade effect partly cancelled by a deletion
regression prices them differently again. The difference is worth a receipt.

I can already attribute part of that factor without this receipt, and part of
it I cannot. Re-pricing the prediction at the *coarse dispatch* bandwidth the
removed bytes actually move at (264.0 GB/s measured, against the 204.6 GB/s
step average the prediction assumed) accounts for a factor of **0.775**. The
remaining **0.602** is an unexplained residual, and I am deliberately not
propagating it as a rule. Only the 0.775 is transferable.

## The byte numerator is confirmed to 99.3%, so this is not a bookkeeping error

The obvious mundane explanation for a half-size effect is that the advertised
25.69 MB is not actually removed. The cascade's second stage re-reads the
1-bit residual plane for every four-row block that survives its screen, so if
survivors were common the saving would be much smaller than advertised. The
inherited code asserted in a comment that survivors are "single digits per
step". That assertion had never been instrumented.

I instrumented it: an env-gated census (`DARKBLOOM_LMHEAD_PRUNE_STATS=1`,
research-only, not in this archive) that evaluates the screen
`coarse + delta >= thr` on the host and counts surviving rows and live
four-row blocks. Over the 128 timed decode steps of a local `--local-iterate`
run:

| quantity | mean | median | min | max |
| --- | ---: | ---: | ---: | ---: |
| surviving rows | 534 | 288 | 55 | 9193 |
| live 4-row blocks | 458 | 269 | 55 | 7261 |

458 live blocks is **1.83%** of the 25088 blocks, and the re-read costs
`534 × 320 B = 171 KB/step`. Net removal is therefore **25.519 MB of a nominal
25.69 MB — 99.3%**. The numerator is right. Whatever costs the other half of
the predicted effect, it is not un-removed bytes.

The census also corrects the inherited comment by two orders of magnitude:
survivors are hundreds, not single digits. That does not matter for the byte
count, but it does matter for how the sparse-refine dispatch is sized — and
following it through overturns a figure this campaign has been quoting.

That dispatch is on record as running at **6.5 GB/s**, the worst efficiency in
the decode step. Reading the kernel, that numerator counts only the 6 B/row
lane-0 screen (0.602 MB). It misses the fall-through: every block whose
`candidate_mask` is non-zero runs a `gemv_al` replica that reads all four rows
of `lm_head` unconditionally, 16 KB per live block. At the measured 458 live
blocks that is **7.504 MB**, so the dispatch actually moves **8.110 MB unique
/ 9.982 MB issued — 109.6 GB/s, or 42% of this host's ceiling**. The published
numerator is wrong by **16.9×**.

Two consequences. The `simd_broadcast` diagnosis behind the proposed fix
governs 0.602 MB of 8.11 MB, so the "~65–69 µs recovered" sizing needs
re-deriving before anyone builds it. And the same correction kills my *own*
first explanation of the missing half — I had attributed the residual to
survivor re-read, but at 109.6 GB/s the 171 KB costs 1.56 µs, which is 0.018%
of `T`, not the 0.438% I needed. I am withdrawing that explanation rather than
substituting a second guess.

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

- Two receipts. This is the second `X` archive; the first is submission
  `1feeabc`, published `2.500378`. `X` is therefore n=2 against an n=3
  control, which is the planned split, but `X - C0` still carries a larger
  standard error than `Y - C0` and should be read as a decomposition aid, not
  as a standalone claim about the two deletions.
- Local M4 timing does not transfer for these two mechanisms the way byte
  removal does. One of them is a dispatch-batching policy and the other is a
  Metal barrier elision inside an `is_nax_available()` path; both are
  generation-sensitive in a way that a byte count is not. The official run is
  the only measurement of them I will quote.
- This archive is expected to score at or near the promoted base. If it scores
  materially *above* it, that is itself the finding: it would mean the harvest
  shipped a real regression rather than two inert commits.
