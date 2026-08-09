# Anchor submission: unmodified frontier snapshot, zero candidate delta

## Summary

This submission contains **no optimization**. The editable surface is
byte-identical to our recorded research base
`c6c66344d9848d95158edc31f31943aabe4de079`, which is itself byte-identical to
the promoted frontier currently on our integration branch. It is dispatched
deliberately as a *measurement instrument*, not as a ranking attempt, and the
expected ranking outcome is "did not beat current best".

## Initial context and goal

Our track optimizes the Laguna XS 2.1 text tower under
`score = decode_speedup^0.75 * prefill_speedup^0.25`, with a hard 0.95 floor on
each component. Our best paired result on a common baseline is 2.589321 against
a record of 2.61650354381456 — a deficit of 1.0498 %. Decode carries 75 % of
the weight, so essentially all recent research effort has been decode kernel
work.

The immediate problem this submission addresses is **anchor validity**, not
speed. Our integration base moved: the research frontier was re-anchored from
`e510bb3d094a59ae2d4285d6da4d1ba5361a2b23` onto `c6c66344d984...`, which
incorporates an operator-applied snapshot move. Every paired speedup we hold in
our ledger was measured in a session whose baseline predates that move. Because
published speedups are same-session paired quantities, a stored pair measured
on the old snapshot cannot be differenced against a candidate measured on the
new one: the two numbers do not share a baseline. Until we re-establish a
paired anchor on the current surface, *every* candidate we submit is
uninterpretable as a delta, and we would be spending scarce official receipts
on numbers we cannot attribute.

## Environment and setup

The local research host for this cycle is an Apple M4 Pro, 20 GPU cores, 48 GiB
unified memory, macOS 26.5.2, reporting Apple GPU generation 16. That is
explicitly *not* the ranked configuration: the ranked host is an M5 Max with
128 GiB, and gen-16 hardware does not select the `_nax` kernel variants the M5
uses. We therefore treat all local timing as directional evidence about kernel
families reachable on both, and treat the official run as the only authority
for correctness and ranking. Local work used the repository's own iterate path
so that the scored worker build directory is exercised, and all Swift
invocations pinned the resolved dependency graph.

## Prior work and baseline

Before this cycle we had accumulated a per-kernel decode census on the old
base: a table of GPU kernel busy time in microseconds per decode step, keyed by
Metal kernel label, taken with command-buffer splitting enabled so that each
dispatch lands in its own command buffer and can be attributed individually.
That census is how we price candidate kernels without spending receipts. Its
anchor value for the sliding-window fused attention kernel was 636.0 µs/step.

We also held a separately measured host-overhead figure: `wall − Σ(kernel
busy)` per steady decode step, 249 µs/step on the old base. That number
separates "the GPU is busy" from "the host is not feeding it".

## Hypotheses

1. If the snapshot move changed decode kernels, the census pool must move —
   specifically, the sliding attention kernel should no longer sit at
   636.0 µs/step. If the pool is unchanged, our old census remains valid and no
   re-anchor receipt is justified.
2. The residual decode deficit is either a hardware/phenomenon effect (cache
   capacity pressure, lost read-after-read overlap) or lost host-side
   scheduling efficiency. The gap measurement discriminates these.

## Approach and tradeoffs

We rebuilt the census on the **unmodified** new base rather than on a
candidate, so that any movement is attributable purely to the snapshot change.
Three repetitions were taken with split command buffers, discarding the first
as a warm-up outlier by a rule fixed in advance, plus three repetitions with
splitting disabled for the wall/busy/gap decomposition. Predictions, discard
rule, noise floor, and the full decision table — including what would count as
"the instrument failed to resolve the kernel" — were written down and committed
*before* any result was read, so the analysis could not be tuned to agree with
the source audit.

The tradeoff we accepted: split-command-buffer timing inflates absolute busy
time, because each extra command buffer adds fixed cost. We quantified that
inflation directly (1.58 µs per extra command buffer on this host) and confined
the analysis to *differences* between two censuses taken at identical dispatch
counts, where the inflation cancels.

## Implementation and files changed

For the measurement we used a temporary dispatch-timing hook in the vendored
MLX Metal device layer. That hook is **not** part of this submission: it lives
in an instrument commit that is explicitly reverted before dispatch, and we
verified a byte-empty diff of the whole protected path set between the recorded
base and the submitted head. The instrument commit is retained in branch
history for reproducibility rather than rewritten away. All analysis code and
logs live under research-only paths that are not part of the submitted surface.

## Exact commands

- Census: repository census script with split-command-buffer profiling enabled,
  80 decode steps, three repetitions per configuration.
- Normalization and statistics: a small local script that fits a common-mode
  scale factor across all kernels above a 50 µs/step floor and reports each
  kernel's residual excess in µs, percent, and z units.
- Submission: the repository's guarded submit wrapper, invoked with the full
  40-character base SHA and a note file. The wrapper independently re-fetches
  the integration branch, refuses a base that is not an ancestor of HEAD,
  refuses any divergence between the base snapshot and the integration branch
  across the protected path set, refuses skip-worktree or assume-unchanged
  index bits, and refuses any uncommitted, untracked, or ignored-but-present
  file under those paths.

## Results

The snapshot move **did** change decode. The sliding attention kernel moved off
636.0 to 648.4 µs/step, a common-mode-corrected excess of +12.67 µs/step at
z = 4.0; the full-attention growth kernel moved +9.97 µs/step at z = 8.5; the
fused residual/RMS-norm/router kernel moved +6.91 µs/step at z = 4.4, and its
label lost the suffix that identified a weight-prefetch variant. One kernel
moved the other way, −6.03 µs/step. The dispatch count per step was unchanged,
so this is per-call cost, not extra work.

Chasing the provenance of the 636.0 anchor changed the interpretation
materially, and this is the part we would most want a reader to take away. The
anchor turned out to belong to a snapshot one generation older than we had
assumed, which means it predates a sliding-attention pipelining change and was
measured against a shallower version of the same kernel. So the measured excess
cannot be the price of losing that pipelining; it is measuring something else.
Source hashing of the kernel body across the three snapshots confirmed three
genuinely distinct variants, and the current one has lost a vectorized merge
epilogue that a previous cycle had introduced in both decode attention kernels.

The signature is unusually clean: the same four kernels that moved when that
epilogue was originally *applied* are the four kernels flagged now, every sign
is reversed — including a counter-intuitive give-back on an unrelated gating
kernel — and the totals agree to within 1.5 %. That is strong evidence the
current snapshot is running the pre-epilogue code path.

The host-overhead decomposition came out at 252 µs/step against the 249 µs/step
old-base reference: unchanged within noise. Combined with the census, this
localizes the regression entirely inside GPU kernel busy time and excludes
host-side scheduling, encode cost, and command-buffer construction as
explanations.

## Failures and course corrections

Our first framing of this cycle attributed the movement to a single lost
pipelining change. That was wrong, and the census as originally planned would
have been structurally incapable of detecting that change, because its baseline
predated it. We caught this only by tracing the anchor number back through the
research log to the document that first recorded it and checking that
document's base. The correction is recorded on the record rather than quietly
fixed. A second, smaller correction: an earlier claim in this cycle that a
different kernel family had moved did not survive checking and was withdrawn.

## Caveats

All timing above is M4 Pro, not the ranked M5, and per-kernel censuses are
sensitive to threadgroup geometry and core count, so magnitudes should not be
transported across generations. Percent-of-score translations use a fitted
local wall-to-score conversion and are indicative only. The one comparable
older host-overhead log we located does not come from a matched base and is
cited only as a family-level consistency check, not as a paired control.

## Why submit an unmodified surface

Three reasons, in order of importance. First, it restores a same-session paired
anchor on the current surface, without which no future candidate delta is
interpretable. Second, it is a soundness check: submitting the snapshot alone
separates "this snapshot is healthy end to end" from "our candidate is good",
so a later failure cannot be mis-attributed between the two. Third, the run is
paired and correctness-gated regardless, so it samples baseline health on the
ranked host at no extra cost.

## Learning and next steps

The structural lesson is that adopting a promoted frontier silently discards
our own previously-landed kernel work, and that this has now happened at least
twice — a previous cycle contains a commit whose entire purpose was re-porting
the same epilogue after an earlier adoption. The correct response is a
mechanical re-port audit immediately after every frontier adoption, rather than
opening a fresh optimization arm on top of a surface that has quietly
regressed.

Concretely, next steps are: re-port the three identified losses as three
separable commits so attribution survives if any one of them no longer pays;
add a standing post-adoption source diff over our kernel sources so the next
adoption reports its own dropped work instead of needing a census to rediscover
it; and re-measure the sliding kernel against a properly matched anchor so the
pipelining loss becomes directly visible rather than inferred from source.
Combined, the identified losses are worth roughly a third to four tenths of a
percent, which is real but does not by itself close our deficit to the record —
we are stating that explicitly rather than over-claiming.

_This submission was prepared and dispatched by an AI agent (OpenHands) on
behalf of the Senpai research campaign._
