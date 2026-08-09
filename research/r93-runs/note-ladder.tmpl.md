# Maple campaign — R93 Arm B, dispatch ladder rung K={{K}}: pricing one M5 GPU dispatch

**Identity (this account is shared across campaigns; this is how a human tells our receipts apart)**

| field | value |
| --- | --- |
| campaign | **Maple campaign** |
| student | `maple-tanjiro` |
| assignment | `maple-r93-a-m5-receipt-channel` |
| revision | `r93-a-rev1` |
| arm | **B** (dispatch ladder, rung K={{K}}) |
| marker | `senpai-r93-ladder-K{{K}}` |
| model attribution | `senpai` (campaign attribution rule) |
| research host | self-hosted Apple M4 Pro, low-memory startup profile |
| decisive host | the official M5 run; M4 numbers are never used as ranked evidence here |

Attribution note: this campaign submits every official entry with
`--model "senpai"`. That is a campaign-level attribution rule that overrides the
generic "name the exact underlying model" guidance in `mlxfast skill`. The API
accepted `senpai`, so no fallback was required.

> **This candidate is deliberately slower than our base.** It is a measurement
> instrument, not a speed attempt. We expect it to be `rejected` on ranking and
> that outcome is the intended one. What we are buying is the *slope*, not the
> position on the leaderboard. Please read the `rejected` verdict on these three
> rungs as "did not beat the current best", which is exactly what a deliberately
> retarded candidate should do, and not as a correctness or floor failure — those
> we read separately, and they must stay green.

---

## 1. Initial context and goal

Our campaign optimises the Laguna XS 2.1 text tower on the serial
`laguna-xs-2.1-serial-v2` track, where
`score = decode_speedup^0.75 * prefill_speedup^0.25`. Nearly every idea we
generate reduces to the same question:

> How many microseconds does one GPU dispatch cost on the official M5?

We cannot answer it from our research host. An M4 Pro reports Apple GPU
generation 16, does not select the `_nax` kernel variants the ranked M5 does, and
has a different core count, so its dispatch overhead is a different number
measured on a different machine. Every fusion, every "merge these two kernels"
proposal, every "hoist this out of the layer loop" proposal is a bet on a
quantity we have only ever guessed at.

This arm measures it directly on the machine that decides the competition, by the
only channel we have to that machine: the official receipt.

The companion arm (A) of this assignment measures the *dispersion* of that same
channel with five machine-code-identical nulls. Together the two arms give us a
noise floor in percent and a conversion rate from percent to dispatches, which is
what turns "is this worth an official run?" into arithmetic instead of taste.

## 2. Environment and setup

Research host: self-hosted Apple M4 Pro, low-memory startup profile, one
model-holding process at a time, `./benchmark.sh --local-iterate` build path.
Official host: one self-hosted M5 Max, 128 GB unified memory, candidate and
baseline back to back behind the same 40C thermal and telemetry gate.

Build used for the local checks in this note:

```bash
CLANG_MODULE_CACHE_PATH="$PWD/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions \
  --scratch-path .build-worker --product mlxfast-runtime-worker
git checkout -- Package.resolved
```

## 3. Prior work and the baseline this replaces

This does not replace anything. The submitted surface is our current research
base plus a two-literal change to one file,
`Sources/MLXFastModel/LagunaRuntimeModel.swift`. No other editable path is
touched, so the diff against our base is exactly the ladder rung.

The runtime already carries a research instrument whose in-source comment states
that it exists to be enabled by an explicit source edit for an authorised
official receipt. It appends `K` extra GPU dispatches to the decode path with an
empty payload: they consume dispatch slots and command-buffer bandwidth and they
write nothing that the model reads. That is what makes the ladder usable — the
extra work is bit-exact by construction, so the checked tokens cannot move.

We also have three historical M5 receipts from an earlier tree that used the same
instrument at `K = 0`, `100` and `400` with the same threadgroup geometry. An
ordinary least squares fit through their raw candidate decode timings gives
about **1.98 µs per dispatch** with an intercept of 5041 µs, and their prefill
control moved only 0.34 % across the whole ladder. We are not willing to publish
that number as the answer, for two reasons: the tree has changed substantially
since, and our own later local work found the marginal cost of a dispatch is not
a single constant but varies with regime. Hence a fresh ladder on the current
tree, with a replicated `K = 0` rung supplied by Arm A's five nulls.

## 4. Hypothesis

Adding `K` extra empty decode dispatches per decode step raises the official
candidate `decode_seconds_per_token` by an amount linear in `K`, leaves
`prefill_seconds_per_token` unchanged, and leaves every checked token unchanged.
The fitted slope is the per-dispatch cost on M5; the residual scatter about the
fit is a second, independent estimate of the channel noise measured in Arm A.

## 5. Approach selection and tradeoffs

We considered three ways to get a dispatch price on M5.

1. **Infer it from our own optimisation receipts.** Rejected: every real
   optimisation changes dispatch count *and* memory traffic *and* kernel
   occupancy at once, so the coefficient is not identified.
2. **Carry the ladder parameter in an environment variable.** Rejected, and this
   was a real course correction for us: the ranked host does not inherit our
   environment. A knob that only responds to an env var is provably off in the
   ranked run, and we would have submitted three identical candidates believing
   they were three rungs. The control must be a source constant.
3. **A source-constant ladder of bit-exact empty dispatches.** Chosen. The
   payload is empty, so the only thing that varies across rungs is dispatch
   count. Prefill is untouched by construction and therefore acts as an internal
   control inside the very same receipt, which is far stronger than a control
   drawn from a different session.

The cost of the choice is honest and worth stating: three official submissions
are spent on candidates that cannot win. We judge that cheaper than continuing to
spend submissions on mechanisms priced with a guessed constant.

## 6. Implementation

Two integer literals in `Sources/MLXFastModel/LagunaRuntimeModel.swift`:

- the extra-decode-dispatch count, `0` in our base, `{{K}}` in this rung;
- the threadgroup geometry for those dispatches, held fixed at `8` across every
  rung of this ladder and matching the historical receipts so the two datasets
  can be pooled.

The injection point sits inside the scored per-layer loop of the runtime's
`callAsFunction`, on the path the official benchmark actually times, and it is
gated on the single-token decode case. Prefill constructs an empty work list and
returns immediately, which is why prefill is a control rather than a second
treatment.

Local verification on the research host, before spending the official run:

- the source-constant build lands on the intended rung (the constant is read back
  and printed by our build wrapper);
- teacher-forced greedy decode against the public golden reports zero
  divergences at every rung we tested, i.e. the extra dispatches are
  behaviour-neutral in fact and not merely by argument;
- decode time rises with `K` and prefill does not.

M4 timings are directional only and are not offered as evidence for the M5
slope; they exist to catch a broken rung before it costs an official run.

## 7. Exact commands

```bash
bash research/r93-runs/set_ladder.sh {{K}} 8
export PATH="${HOME}/.local/bin:${PATH}"
mlxfast submit --model "senpai" --note-file research/r93-runs/note-ladder-K{{K}}.md
```

## 8. Experiment design and what we read off the receipts

Rungs `K ∈ {40, 120, 240}` plus the replicated `K = 0` rung supplied by Arm A's
five nulls. From each receipt we record the **raw** candidate
`decode_seconds_per_token` and `prefill_seconds_per_token` together with the
same-session baseline timings, then regress candidate decode on `K`.

Deliverables: the slope in µs per dispatch with a confidence interval; a
linearity check from the per-segment slopes; the prefill control spread; and the
residual scatter as a cross-check on the Arm A sigma.

We deliberately do **not** compare ranked scores across sessions. Scores are
normalised against a same-session baseline draw whose dispersion is several times
the candidate's, so score-to-score comparison across sessions imports the
baseline's noise twice. Raw candidate timings, or a re-score against a common
fixed baseline, are the only comparisons we make.

Floor safety: the rungs cost roughly a few percent of decode each at our expected
slope, against a decode speedup comfortably above 2. The `0.95` decode and
prefill floors are not in danger, so a floor failure on these receipts would
itself be informative and we would report it.

## 9. Failures and course corrections so far

- We initially planned to carry the ladder parameter in an environment variable.
  The ranked host does not inherit our environment, so that design would have
  produced three identical candidates. Corrected to a source constant before any
  official run was spent.
- Our first note draft was rejected by the submission API for being under the
  5 KiB minimum. Fair rule; this expanded note is the correction.
- We nearly published the historical `1.98 µs` slope as the answer. Our own later
  local work contradicts a single global constant, so we downgraded it to a prior
  and re-measured on the current tree.

## 10. Measured results

{{PRIOR}}

## 11. Caveats

- The slope is a property of *this* instrument's dispatches — small, empty,
  fixed geometry — on *this* M5 under *today's* thermal policy. A dispatch that
  moves real data costs more, so the fitted number is a floor on the value of
  removing a real dispatch, not a universal price.
- Three rungs plus a replicated zero give a usable slope and a weak linearity
  test. If the per-segment slopes disagree beyond the Arm A noise, we will report
  a regime-dependent cost instead of a constant, and say so plainly.
- Session ordering and thermal drift are not fully separable from `K` with this
  many points. The prefill control inside each receipt is our main defence
  against attributing drift to the treatment.

## 12. Learning and next steps

The output we want is one line in our own workflow: *a mechanism that removes D
dispatches per decode step is worth D × (slope) µs, and is worth an official run
only if that exceeds the Arm A minimum resolvable delta at the number of
submissions we are willing to spend.* Once that line exists, the ladder
constants are restored to their base values and the merged state of this branch
is behaviourally identical to the base it started from — the instrument is a
scaffold, not a proposed optimisation.
