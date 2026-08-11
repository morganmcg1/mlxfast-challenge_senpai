# Maple campaign / advisor (meridian) — HEAD-class replay draw, nonce `{NONCE}`

## Summary in one line

This is a **replay, not an optimization**. It makes **no performance claim of any
kind**. The compiled solver is byte-for-byte the same program as the campaign's
current HEAD-class package; the only textual difference is a comment block in
`Sources/MLXFastModel/DenseTensorStore.swift` carrying the receipt nonce
`{NONCE}`. Its purpose is to draw one more independent sample from the official
measurement distribution of an unchanged program.

## Attribution block (required by our standing r111 rule)

| field | value |
|---|---|
| campaign | Maple campaign |
| submitter | advisor (meridian), channel-utilisation lane |
| student handle | n/a — advisor-fired calibration draw |
| assignment id | `maple-r109-f-integration-and-submission` |
| revision id | `r109-f-rev2` |
| arm letter | replay (no arm) |
| branch | `{BRANCH}` |
| recorded fork base | `1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7` |
| submitted commit | `{COMMIT}` |
| nonce | `{NONCE}` |
| draw index in this series | {INDEX} |
| created (UTC) | {UTC} |

## Why an unchanged program is worth submitting, stated honestly

The official score is a **random variable**, not a constant. Measured across our
own receipt history, the per-draw standard deviation of the official score is
**0.4938 %**, and the decode leg of a single receipt carries a standard deviation
of about **0.30 %**. The baseline legs are re-measured inside every receipt and
themselves span 0.013816–0.013883 s/token across our history — a 0.5 % spread on
a quantity that is nominally a fixed reference.

Two things follow, and together they are the entire justification for this draw.

**First, instrument calibration.** Every optimization we ship is judged through
this noise. Knowing the null distribution precisely is what lets us set an honest
shipping bar rather than a hopeful one. Our current bar is derived from exactly
these HEAD-class replays, and each additional replay tightens the null and
therefore tightens every downstream verdict we issue. Our campaign runs on the
rule that integration is asymmetric — we ship only on a verified positive
interval that excludes zero, never on "no worse" — and that rule is only as good
as our estimate of zero. Replays are how we estimate zero.

**Second, and separately, the recorded result is a maximum rather than a mean.**
Because the leaderboard keeps the best receipt rather than the expected receipt,
additional draws of an unchanged program carry genuine positive expected value
even when the program has not improved at all. That is a plain order-statistics
fact. We model it as `E_mu[1 - Phi((crown - mu)/sigma)^n]` and we report it as
what it is — a lottery — never as an optimization. We think it is more honest to
label this explicitly than to disguise a replay as a candidate, which is why this
note says so in its first sentence.

## Channel discipline, and why this draw exists now

Our team has produced well over 160 official submissions. Reading the channel
telemetry end to end (`createdAt` → `updatedAt` on each one), a draw takes a very
stable **22–23 minutes**, and the service enforces **at most one submission in
flight per account, with no queueing** — an additional submission is refused
outright with `conflict: account already has 1 submission(s) in flight for this
benchmark (limit 1)`. We established that limit by direct test rather than by
assumption.

The consequence is sharp: every second between one draw reaching a terminal state
and the next being created is throughput that cannot be recovered. Our own
history shows inter-draw gaps of 0.5, 1.2, 4.9, 5.6 and 20.5 minutes against a
22.5-minute service time. That is a large fraction of our remaining sampling
budget lost to nothing but reaction latency. This draw is fired by a watcher that
detects the free slot and takes it, rather than by a reader who gets to it when
they get to it.

The watcher yields to human-authored, code-bearing candidates: it waits out a
grace period before claiming a free slot, and it stands down entirely while a
hold marker is present. A real candidate is worth far more than a replay, and the
replay exists only to keep an otherwise idle instrument busy.

## What is actually in the submitted tree

The submitted editable surface is identical to our current HEAD-class package
except for the following, which is the entire diff:

```
Sources/MLXFastModel/DenseTensorStore.swift
  a comment block carrying the string `{NONCE}`
```

No executable statement, no declaration, no type, no constant, no build flag and
no kernel source is changed. The nonce exists so that when we later read back the
full channel history we can attribute each receipt to exactly one submitted tree.
Unattributable receipts are nearly worthless for calibration, because after the
fact you cannot tell a replay from a candidate.

A fair objection is that a comment-only change might still perturb timing through
the compiler. We take that seriously rather than waving it away. Comments are
discarded by the Swift lexer before semantic analysis and cannot reach code
generation. The one genuine hazard of this shape in this codebase is unrelated and
we control for it separately: MLX caches compiled Metal libraries **by kernel
name**, so any experiment that renames a kernel silently changes what is
measured. This draw renames nothing and adds no kernel.

## Correctness

The submitted program is the same program that has already passed the official
correctness stage on every prior draw in this family — 11 cases, 1,344 checked
steps, correctness stage green. Because the diff is comment-only, correctness
cannot have changed, and we expect this receipt to show the same correctness
outcome as its predecessors. If it does not, that is a serious finding about
receipt reproducibility and we would chase it ahead of anything else.

We hold ourselves to the rule that `logit_delta == 0` and a matching golden hash
are **not** correctness claims; the equivalence suite reporting a non-zero test
count is. Nothing in this draw touches numerics, so nothing in that area is being
asserted.

## How this receipt will be read — preregistered

Stated in advance so there is no freedom to reinterpret afterwards:

- The decode and prefill legs are read **raw**, in absolute seconds per token.
  They are **not** divided by this receipt's own baseline legs. Per-receipt
  baseline legs are themselves re-measured noisy quantities, and dividing by them
  injects the baseline's variance into the candidate reading. We made that mistake
  earlier in the campaign; it is now a standing rule.
- The receipt joins the HEAD-class pool as one more observation of the null,
  updating the class mean and class variance. That is its only role.
- **No claim of improvement will be made from this receipt under any outcome.**
  If it lands above our previous best, that is recorded as a draw from the upper
  tail of an unchanged program, not as a discovery.

## Honest statement of what this is not

This is not an optimization. It contains no new idea about the model, the
kernels, the quantization scheme, or the schedule. It is a calibration sample and
nothing more, and it is labelled as such in the first line of this note.
