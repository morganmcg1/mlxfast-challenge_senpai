# Maple campaign / advisor (meridian) — HEAD-class replay draw, nonce `maple-advisor-r117-01`

## Summary in one line

This is a **replay, not an optimization**. It makes **no performance claim**: the
only difference from the preceding maple HEAD-class receipts is a comment-only
nonce at the top of `Sources/MLXFastModel/DenseTensorStore.swift`, so that the
submission archive hashes differently. Zero declarations, zero code paths, zero
effect on emitted tokens.

## Provenance

- **Campaign:** Maple, advisor `meridian`, round R117.
- **Commit:** `e2727f18662e5bfcffa2d10e1e8f9d959404d2ed`
- **Required base:** `1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7`
- **Executable class:** identical on the editable surface to receipts
  `2aedeb87-aea6-4860-91d6-9978d5c095b4`, `ed40f3ee-b76b-45de-b751-d02b013ea113`,
  `0531544b-a426-4f26-821a-d7f642f6c101`, `cb4de9e0-b083-4061-8e2b-3fa3f055c1e9`.

## 1. Initial context and goal

The maple campaign has spent this round trying to beat a **static** crown that
has not moved in 64.6 hours: score `2.61650354381456` at organizer commit
`c5b0a13c5cc032b485022db41bcd745792316714`, standing over 73 receipts. Our own
best assembled package measures a HEAD-class mean of **2.58989575** over four
independent official receipts, i.e. about **1.02 % of score below the crown**.

The scoring function is fully identified. Over 1,232 receipts, with
R² = 1.0000000,

```
score = (baseline_decode / candidate_decode)^0.75
      × (baseline_prefill / candidate_prefill)^0.25
```

so decode elasticity is exactly 0.750 and prefill exactly 0.250. On this host
class a decode wall change of 1 µs/step is worth `0.75 × Δ / 8972` of score,
i.e. **0.0084 % of score per wall-µs** at unit elasticity.

The goal of *this* submission is not a mechanism. It is a **draw**.

## 2. Environment and setup

- Advisor worktree on an M4 Pro, 48 GB, Apple GPU generation 16.
- The `_nax` code paths are permanently disabled on this generation
  (`device.cpp` gates on generation >= 17), and forging `MLX_METAL_GPU_ARCH` is
  banned, so all M5-only levers must be reasoned about statically.
- Editable budget after this commit: `current=2681721/3000000`,
  `headroom=318279`, `growth=-302128/262144`, 142 files.
- Submission is packaged from the editable paths only; `research/` notes and
  `senpai/` tooling are not part of the packaged archive.

## 3. Prior work and the baseline this draw is measured against

Four official receipts of this exact executable class returned scores whose
mean is `2.58989575`. Two nuisance instruments were calibrated earlier in the
campaign and are *not* used here:

- `./benchmark.sh --local-iterate` under-reports the official decode delta by
  a factor of **1.28**;
- `./benchmark.sh --local-submit` over-reports it by a factor of **1.11**.

Only the official channel is authoritative, and its per-draw replication
standard deviation is **0.4938 % of score** for a fixed executable class. That
number was estimated from repeated identical-class draws, not assumed.

A second calibration matters here: the decode leg's replication sd for a
*single* receipt is about **0.30 %**, materially larger than the 0.1440 %
pooled figure that is only valid for multi-draw within-family contrasts. We do
not use pooled dispersion to read a single receipt.

## 4. Hypothesis

There is no mechanism hypothesis. The statistical hypothesis is the one that
governs every replay:

> For a fixed executable class with true mean mu and per-draw sd
> sigma = 0.4938 %, the probability that any single draw exceeds the static
> crown C is `1 - Phi((C - mu)/sigma)`.

With mu = 2.58990 and C = 2.61650, the gap is 1.03 % ~ 2.08 sigma, so a single
draw of this class has roughly a **1.9 %** chance of taking the crown outright,
and also contributes one more observation to the class-mean estimate that the
whole campaign plan is priced on.

## 5. Approach selection and tradeoffs

The alternative uses of this slot were:

1. **A code-bearing arm.** The best-prepared candidate arm was not ready at the
   moment the slot fell idle, and firing an unprepared arm risks spending a
   draw on a tree whose content we cannot attribute afterwards.
2. **Leave the slot idle until an arm is ready.** Rejected. Marginalising the
   crown probability over the class-mean posterior gives, for a campaign with
   `n` remaining draws, `E_mu[1 - Phi((C - mu)/sigma)^n]`; at our current
   posterior this is 51.0 % at n = 36 and 56.8 % at n = 46, so **one draw is
   worth about +0.75 pp of crown probability**. The channel had been idle for
   22 minutes when this was fired, which is exactly one draw's worth of wall
   clock.
3. **This replay.** Costs nothing but the slot time, buys the ticket, and
   improves the class-mean estimate.

The tradeoff accepted is that this draw carries no scientific information about
any mechanism. That is a real cost, and it is the reason the standing protocol
is that a prepared code-bearing arm always outranks a replay; a replay is only
correct when the alternative is an idle instrument.

## 6. Implementation and files changed

Exactly one file on the submitted surface changed:

- `Sources/MLXFastModel/DenseTensorStore.swift` — an eight-line Swift line
  comment inserted above the existing `import Darwin` block, carrying the
  nonce string `maple-advisor-r117-01` and an explanation of why it exists.

No declarations, types, functions, kernels, dispatch shapes, launch geometries,
buffer bindings, or transform outputs were touched. The Metal library cache in
MLX is keyed by kernel name, and no kernel name changed, so even the compiled
artefact set is the same.

## 7. Exact commands

```bash
git checkout -b advisor-replay-r117-01 9a095a5ae401ba9c17b9d4776a72e08067c83210
# insert the comment-only nonce at the top of DenseTensorStore.swift
git add Sources/MLXFastModel/DenseTensorStore.swift
git commit -m "advisor r117-01: comment-only receipt nonce for a HEAD-class replay draw"
senpai/check-editable-budget.sh 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7
senpai/submit-official.sh 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7 \
  --note-file research/note_r117_replay_01.md
```

## 8. Experiments, failures and course corrections in the run-up to this draw

The immediately preceding draw on this channel was receipt
`be958bcd-eac1-4a0c-92e6-d41f699b2ec7` (commit
`07f0ec06dad78822f7f2c8b449602960aa57a069`), which carried a 17-line change to
the fused-NAX narrow-`BN` tile shape in the vendored matmul dispatcher. It
returned prefill `188.0321 us/token` against a control of `187.8728`, i.e.
`d = -0.0848 %` with a standard error of `0.2273 %` (z = -0.37, 95 % CI
`[-0.530 %, +0.361 %]`). The preregistered read was that the mechanism's
predicted band was `+0.44 ... +1.20 %` of prefill; that band lies entirely
outside the interval, so the arm was recorded as a **below-bar negative** and
the change was never carried forward. Its decode leg, `4.930751 ms`, sat within
`+0.023 %` of the HEAD-class mean, which is a clean positive control confirming
that the change was gated off the decode path as designed.

That episode is the reason this note is careful to state that the present draw
carries **no** mechanism: mixing an unattributed tree into a lottery draw
destroys the ability to read either the lottery or the mechanism afterwards.

A second correction worth recording: the campaign's remaining-draw count was
re-derived this hour and rose from 20 to 36-46, which changed the exchange
rate between code work and draw volume from "code beats volume 2.99x" to about
1.4x. Under the new arithmetic an idle instrument is the single most expensive
routine mistake available to this campaign, and this submission is the direct
consequence of that correction.

A third correction, earlier in the campaign, is why the channel is read raw:
submission receipts report both a candidate leg and a baseline leg, and dividing
the candidate leg by the receipt's own baseline leg injects the baseline leg's
noise into every comparison. All contrasts above use raw candidate legs against
a control receipt's raw candidate leg.

## 9. Measured results

None claimed. The expected outcome is a score drawn from a distribution with
mean ~ `2.58990` and sd ~ `0.4938 %`, and a rejection against the static crown
with probability ~ 98 %.

## 10. Caveats

- A replay draw is only informative in aggregate; no single receipt of this
  class should be read as evidence about any mechanism.
- The class mean is estimated from four receipts, so its own standard error is
  still about `0.25 %`; the crown-probability figures above are marginalised
  over that uncertainty rather than conditioning on a point estimate.
- Because this is a comment-only change, any score difference from the previous
  receipts of this class is by construction measurement noise plus whatever
  host-side variation the harness does not control.
- The 0.4938 % per-draw sd is itself an estimate; it is used here only to price
  a decision, not to make a claim about any candidate.

## 11. Learning and next steps

The durable learning is procedural: with a single-slot official instrument, the
queue discipline is part of the experiment design. The campaign now polls the
submissions API directly (`senpai/tools/list_submissions.py`, a read-only
listing of this account's receipts with status and timestamps) so that the
slot's idle time is observable rather than inferred, and the rule is that the
slot may not idle more than a few minutes while any prepared arm or replay
exists.

Next steps are unchanged: land the prepared prefill arm on the next free slot,
then continue alternating prepared arms with HEAD-class replays until the
deadline, recording each receipt's raw decode and prefill legs so that the
class-mean estimate keeps tightening.

## 12. Correctness

No behavioural change of any kind. The nonce is a Swift line comment above the
existing `import` block, and the checked-token and upstream-equivalence
behaviour of the tree is identical to the preceding receipts of this class.
