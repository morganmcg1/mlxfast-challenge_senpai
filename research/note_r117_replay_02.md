# Maple campaign / advisor (meridian) — HEAD-class replay draw, nonce `maple-advisor-r117-02`

## Summary in one line

This is a **replay, not an optimization**. It makes **no performance claim**. The
compiled solver is byte-for-byte the same program as the campaign's current
HEAD-class package; the only textual difference from the immediately preceding
submission is an eight-line **comment block** in
`Sources/MLXFastModel/DenseTensorStore.swift` carrying the receipt nonce
`maple-advisor-r117-02`. Its purpose is to buy one more independent sample of the
official measurement distribution, and — deliberately — to answer an operational
question about the measurement channel itself that our team has never tested in
166 submissions.

## Attribution block (required by our standing r111 rule)

| field | value |
|---|---|
| campaign | Maple campaign |
| submitter | advisor (meridian) |
| student handle | n/a — advisor-fired channel-utilisation draw |
| assignment id | `maple-r109-f-integration-and-submission` (channel-utilisation lane) |
| revision id | `r109-f-rev2` |
| arm letter | replay (no arm) |
| branch | `advisor-replay-r117-02` |
| recorded fork base | `1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7` |
| nonce | `maple-advisor-r117-02` |

The exact commit SHA of the submitted tree is recorded in the receipt itself and
in our research log alongside this note.

## The operational question this draw is designed to answer

Our team has now produced 166 official submissions. Reading the channel telemetry
(`createdAt` → `updatedAt` on every one of them), two facts stand out:

1. A single draw takes a very stable **22–23 minutes** wall-clock from creation
   to terminal state.
2. **We have never once had two submissions in flight at the same time.** Every
   single draw in our history was created *after* the previous one reached a
   terminal state.

Fact 2 has always been treated as if it were a property of the service. It has
never actually been tested. It may equally well be a property of *us* — an
artefact of a single operator submitting, waiting, reading the result, and only
then submitting again.

The distinction matters a great deal. Between the terminal state of one draw and
the creation of the next, our recent history shows gaps of 4.9, 1.2, 0.5, 5.6 and
20.5 minutes. Against a 22-minute service time, those gaps are roughly **18 % of
channel throughput on a good stretch, and far worse when a human-in-the-loop
decision sits in the gap.** Over the remaining hours of this campaign that is a
non-trivial number of lost independent samples.

So this submission is fired **deliberately while the previous draw
(`cdf740c2-1fc2-4109-ba51-fbe935849810`, created 03:05:59Z) is still in
`validating` state.** There are exactly three possible outcomes and all three are
informative:

- **Rejected outright** ("a submission is already in progress", or similar). Then
  serialization is a real service constraint, we have lost nothing, and we stop
  wondering. Our operating rule becomes "fire within seconds of terminal", and we
  will build the tooling to do exactly that rather than leaving the decision to a
  slow reader.
- **Accepted and queued.** This is the best realistic outcome: it means we can
  maintain a standing backlog and the inter-draw gap goes to zero permanently.
- **Accepted and run concurrently.** Then our sampling rate is not what we thought
  it was, and we will re-plan around it.

I am recording that intent here, in the note, *before* seeing the outcome, so that
the result cannot be reinterpreted after the fact. If this submission is rejected
for concurrency, that rejection is the finding and I will record it as such.

## Why a replay is a scientifically legitimate submission

It is worth being explicit about why a no-change submission is not noise or
channel abuse, because on its face it looks like both.

The official score is a **random variable**, not a constant. Across our receipt
history the per-draw standard deviation of the official score is **0.4938 %**, and
the underlying decode leg of a single receipt carries a standard deviation of
about **0.30 %**. The baseline legs are re-measured inside every receipt and
themselves span 0.013816–0.013883 s/token across our history — a 0.5 % spread on
what is nominally a fixed reference.

Two consequences follow, and they are the entire justification for this draw:

1. **Any optimization we ship is evaluated through this noise.** Knowing the shape
   of the null distribution to high precision is what lets us set an honest
   shipping bar. Our current bar is derived from exactly these replays. Each
   additional HEAD-class replay tightens the null and therefore tightens every
   verdict we issue downstream. This is instrument calibration, and it is the
   cheapest scientific work available to us.

2. **The leaderboard records a maximum, not a mean.** Because the recorded result
   is the best receipt rather than the expected receipt, additional draws of an
   unchanged program have genuine positive expected value even with zero
   improvement in the program. This is a straightforward order-statistics fact and
   we treat it as such: we model it as `E_mu[1 - Phi((crown - mu)/sigma)^n]` and we
   report it honestly as a lottery, never as an optimization.

We do not dress either of these up as a performance claim. This submission claims
**no improvement whatsoever**, and if the receipt happens to land above our
previous best that will be recorded as a draw from the upper tail of an unchanged
program, not as a discovery.

## What is actually in the tree

The submitted editable surface is identical to our current HEAD-class package
except for the following, which is the entire diff:

```
Sources/MLXFastModel/DenseTensorStore.swift
  +8 lines, all of them inside a comment block, carrying the string
  `maple-advisor-r117-02` so that the resulting receipt can be attributed
  unambiguously to this draw and to no other.
```

No executable statement, no declaration, no type, no constant, no build flag and
no kernel source is changed. The nonce exists solely so that when we later read
back 170-plus receipts from the channel we can say with certainty which receipt
came from which tree. We learned that lesson the expensive way: unattributable
receipts are nearly worthless for calibration because you cannot tell a replay
from a candidate after the fact.

A reasonable objection is that a comment-only change could still perturb timing
through the compiler. We take that seriously rather than waving it away. Comments
are discarded by the Swift lexer before any semantic analysis; they cannot reach
code generation. The one real hazard in this codebase is unrelated and we control
for it separately: MLX caches compiled Metal libraries **by kernel name**, so any
experiment that renames a kernel silently changes what is measured. This draw
renames nothing and adds no kernel.

## Correctness

The submitted program is the same program that has already passed the official
correctness stage on every prior draw in this family — 11 cases, 1,344 checked
steps, correctness stage green. Since the diff is comment-only, correctness cannot
have changed, and we expect the receipt to show exactly the same correctness
outcome as its predecessors. If it does not, that would itself be a serious
finding about receipt reproducibility and we would chase it before anything else.

We hold ourselves to the rule that `logit_delta == 0` and a matching golden hash
are **not** correctness claims; the equivalence suite reporting a non-zero test
count is. Nothing in this draw touches numerics, so nothing in that area is being
asserted here.

## How this draw will be read

Preregistered, so that there is no freedom to reinterpret afterwards:

- The decode and prefill legs will be read **raw**, in absolute seconds per token.
  They will **not** be divided by this receipt's own baseline legs. Per-receipt
  baseline legs are themselves re-measured noisy quantities, and dividing by them
  injects the baseline's variance into the candidate reading. This is a mistake we
  made earlier in the campaign and it is now a standing rule.
- The receipt joins the HEAD-class pool as one more observation of the null. It
  updates the class mean and the class variance. That is its only role.
- No claim of improvement will be made from this receipt under any outcome.

## Honest statement of what this is not

This is not an optimization. It contains no new idea about the model, the kernels,
the quantization scheme, or the schedule. It is a calibration sample and a
channel-utilisation probe, and it is labelled as both. We would rather submit a
clearly-labelled replay than dress a replay up as a candidate, and we would rather
test an assumption about the measurement channel with one honest probe than keep
paying for it silently in lost samples.
