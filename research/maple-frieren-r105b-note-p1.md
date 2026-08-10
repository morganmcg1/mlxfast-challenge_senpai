# R105-B Phase B, arm P1 — PR #597, student `maple-frieren`

Marker for receipt identification: **R105-B Phase B, arm P1**.

## 1. What this receipt is

This is the **control half** of a two-receipt paired A/B on the ranked M5. It
restores the shipped value of the router weight-prefetch knob,
`DARKBLOOM_ROUTER_WEIGHT_PREFETCH = 1`, i.e. it keeps the hoisted prefetch
salvo in the fused residual-RMSNorm + router kernel. Its companion, **arm P0**,
was submitted from the same branch immediately before this one and differs by a
single compiled-in constant.

Read the two receipts **as a difference**. Neither is tuned to win; a
`rejected` ranking verdict on either is the expected outcome and carries no
information about the measurement. What carries information is the sign of
`P0 - P1`.

## 2. Context and goal

The `residual_rms_router` kernel opens every MoE block. It fuses the residual
add, the RMSNorm reduction, and the router GEMV. At some point it acquired a
**hoisted weight-prefetch salvo**: four `device` loads of the router weight
tile issued near the top of the kernel, above the threadgroup barrier that
separates the RMS reduction from the router GEMV. The intent was to overlap the
router weight fetch with the reduction. It has shipped as the default ever
since, on the strength of a microbenchmark, and was never adjudicated end to
end on the scored decode path.

R105-B adjudicates it. This receipt establishes what the shipped configuration
scores on M5 under exactly the same conditions as the P0 flip, so that the two
can be differenced.

## 3. Environment

- Research host: Apple M4 Pro, 48 GB unified memory, low-memory startup
  profile, 40C thermal gate honoured on every timed slot.
- Ranked host: self-hosted M5 Max, 128 GB, reachable only through this
  submission API.
- Toolchain: pinned Swift toolchain from `setup.sh`; all builds used
  `--force-resolved-versions` with `Package.resolved` restored afterwards.
- Timing: `./benchmark.sh --local-iterate` for the scored worker build.

**The M4/M5 gap is the reason this pair exists.** M4 Pro reports Apple GPU
generation 16 and does not select the `_nax` kernel variants the ranked M5
uses. `residual_rms_router` is not itself an `_nax` family, so the kernel
source under test is common to both machines — but occupancy limits, register
budget, and the memory system that decides whether a hoisted load is free are
not. M4 evidence is directional about a shared kernel; it is not proof about
M5. Hence a transfer check rather than a confirmation.

## 4. Prior work and baseline

Phase A was a 144-slot position-matched ABBA study on M4 Pro, accepted by the
advisor without qualification. It used five arms so that the *placement* of the
salvo could be separated from the *loads themselves*:

- **P0** — no salvo.
- **P1** — shipped salvo, four loads hoisted above the barrier (this receipt).
- **P1B** — same loads hoisted, different register assignment.
- **P5** — same four loads issued **below** the barrier: loads performed, not
  hoisted.

Result, verdict **V-PLACEMENT**:

```
pooled(P1, P1B) - P0 = +28.00 us/step   CI [+22.23, +33.77]   16/16 positive
                     = +0.426 % of cs
P0 -> P5             = covers zero
P1 -> P5             = -19.37 us/step   CI [-27.92, -10.83]
```

The structure of that result is the interesting part. Doing the four loads
costs nothing (`P0 -> P5` covers zero). Doing them **hoisted across the
barrier** costs 28 us/step. Putting them back below the barrier recovers 19 of
those microseconds. **The cost is cross-barrier placement, not the loads.** The
leading hypothesis is that hoisting extends four register live ranges across
the barrier, raising the kernel's register high-water mark and costing an
occupancy step; contention between the hoisted loads and the reduction's own
traffic is a secondary candidate. I did not instrument register allocation, so
the placement effect is measured and the mechanism is hypothesis.

**Bit-exactness was demonstrated, not assumed.** Across all 144 timed slots
there was exactly **one** distinct sha256 over the emitted token stream, and
the golden tree digest `d93a6d14` was unchanged. `prefetch in {0, 1, 5}` are
bit-exact with one another. This is a scheduling change, not a numerics change;
nothing here approaches the accepted attention quantization envelope.

A secondary arm, A0, returned **A0-INCONCLUSIVE**: the hardware counter read
13.77 against a preregistered threshold of 12 and the N-1 discriminator did not
fire. I am not claiming it.

## 5. Hypotheses

- **H1.** The M4 placement penalty transfers in sign, so P0 scores at least as
  well as this P1 control on M5.
- **H2 (null).** The effect is M4-specific and M5 shows no resolvable
  difference.
- **H3 (reversal).** M5 rewards the hoist and P1 — this receipt — is genuinely
  faster. This is the most valuable of the three: it would be the campaign's
  first measured sign flip across Apple GPU generations and would bound how far
  M4 evidence can be trusted anywhere else.

All three were preregistered before any receipt was drawn. No outcome of this
pair will be described as a failure.

## 6. Approach, and why this arm needs its own commit

The knob resolves like this:

```swift
// Sources/MLXFastModel/LagunaRuntimeModel.swift
if let env = ProcessInfo.processInfo.environment["DARKBLOOM_ROUTER_WEIGHT_PREFETCH"],
   let v = Int(env) { return v }
else { return 1 }        // P0 sets this to 0
```

A law about this benchmark that is worth stating plainly, because it is general
and not a fact about my patch: **the graded run cannot see the environment
variable.** The grader executes the submitted worktree in its own process
environment, where `DARKBLOOM_ROUTER_WEIGHT_PREFETCH` is unset. The `if let
env` branch therefore never fires under grading, and the only value that can
reach the kernel on the ranked host is **the compiled-in constant in the `else`
branch**. Local env-var sweeps are a research affordance and are invisible to
the score. That is why each arm must be a distinct *commit* changing that
constant, and why no amount of local sweeping could substitute.

This arm restores the shipped constant, so its `Sources/` content would
otherwise be byte-identical to the branch base. To keep it a distinct,
auditable submission rather than a resubmission of an already-seen tree, it
carries **one distinguishing comment line inside the same editable source
file**. The distinguishing byte deliberately lives in a submitted file rather
than in `research/` or in a commit message, so that anyone auditing the
archive — which contains only `editablePaths` — can tell the two arms apart
from the archive alone.

## 7. Implementation and files changed

Submitted surface, one file:

- `Sources/MLXFastModel/LagunaRuntimeModel.swift` — the prefetch accessor
  returns the shipped `1`, plus one comment line identifying this arm and its
  role as the P0 control.

Nothing else in the 97 `editablePaths` is touched. Submitted surface totals
about 1,736,131 bytes against the 3,000,000 byte cap; per-file and
growth-per-review limits are not approached.

## 8. Exact commands

```bash
# base
git rebase 0954002c16014a03091e1856cdf356fb0e6a3e38

# this arm
$EDITOR Sources/MLXFastModel/LagunaRuntimeModel.swift
git commit -am "R105-B P1 control: restore shipped prefetch default with arm marker"

# compile gate
swift build -c release --force-resolved-versions
git checkout -- Package.resolved

# submission
bash senpai/submit-official.sh 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7 \
  --note-file research/maple-frieren-r105b-note-p1.md
```

Phase A reproduction is `research/maple-frieren-r103a-abba.sh` driving the five
prefetch arms, analysed by `research/maple-frieren-r105b-pooled.py` and
`research/maple-frieren-r105b-verdict.py`.

## 9. Experiments performed

1. Phase A, 144 position-matched slots on M4 Pro, five arms, ABBA ordering,
   thermal gate on every slot. Produced V-PLACEMENT.
2. Token-identity audit across all 144 slots: one distinct sha256.
3. Compile gate on both arms: `swift build -c release
   --force-resolved-versions`, exit 0.
4. Frontier-relationship audit (section 12).
5. The P0 receipt and this P1 control, drawn back to back from the ranked M5.

## 10. Failures and corrections

- **I mis-read the frontier relationship at first**, believing this branch's
  absolute score was not comparable to the promoted frontier. It is; see
  section 12.
- **I twice confirmed a submission by the wrong signal**, once by exit code and
  once by "the newest submission id changed". Both gave false positives,
  because this API account is shared and sibling arms land rows between a poll
  and a read. A receipt I briefly believed was mine belonged to another study
  entirely. Confirmation must be by a **unique marker in the note body**, read
  back with `mlxfast submission-note <id>` — hence the marker line at the top
  of this note.
- **A conflict-retry loop is actively harmful.** One submission is permitted in
  flight per account, and a rejected *conflict* attempt still consumes shared
  rate-limit budget, so retrying on conflict burns the budget the successful
  attempt needs. Correct pattern: read-only polling, exactly one fire when the
  channel is observed clear.
- **I wrongly attributed the contending traffic to other campaigns**, reasoning
  that the receipts' SHAs did not resolve in my checkout. That inference is
  invalid — siblings submit from branches I never fetched. Reading the notes by
  marker showed all of it was maple sibling arms. Retracted.
- **Phase A's A0 arm did not resolve** and is reported inconclusive rather than
  rescued with a post-hoc threshold.

## 11. Measured results

Phase A, M4 Pro, 144 slots:

| comparison | delta (us/step) | 95% CI | sign consistency |
|---|---|---|---|
| pooled(P1,P1B) - P0 | +28.00 | [+22.23, +33.77] | 16/16 |
| P0 - P5 | ~0 | covers zero | - |
| P1 - P5 | -19.37 | [-27.92, -10.83] | - |

The M5 numbers are whatever this receipt and its P0 companion return; both raw
halves are reported to the advisor rather than a derived speedup alone.

**Power, stated plainly.** My paired standard deviation across consecutive
non-outlier receipts is sigma_pair(T) = 17.08 us/step, giving a half-width of
**+/-33.5 us/step for one pair** and **+/-23.7 us/step for two pairs**. The M4
effect is +28.00 us/step, so any transfer coefficient below roughly 1.2 leaves
the true M5 effect inside my two-pair noise band. **Two pairs cannot resolve a
x0.436 transfer.** This pair is a sign-and-transfer check, not a magnitude
estimate, and I will not present it as one.

## 12. Caveats

- **Absolute comparability.** `origin/main` (`1bc1c895`) is a strict
  **ancestor** of this branch's base (`0954002c`). The 27-file delta against
  `origin/main` is comment-stripping in vendored files plus already-merged
  105-C/D/E work, not unpromoted divergence. The branch is therefore strictly
  ahead of the promoted frontier and the absolute `cs` here is
  frontier-comparable.
- **`rejected` is a ranking verdict, not a correctness failure.** It can mean
  only that the score did not beat the current best. Correctness, error, and
  the two 0.95 floor verdicts must be read separately from ranking status.
- **One pair is one pair.** Sign agreement would be encouraging, not a
  confirmed magnitude.
- **The shared channel contaminates wall-clock scheduling**, though not the
  paired measurement itself: each receipt is timed against its own same-session
  baseline on the M5.

## 13. Learning

1. **Separate placement from work.** The five-arm design turned "prefetch is
   slow" into "hoisting across the barrier is slow, the loads are free". A
   two-arm A/B would have produced the right sign with the wrong mechanism, and
   the wrong mechanism would have sent the next optimiser hunting bandwidth
   that was never the problem.
2. **Only the compiled-in constant is visible to the grader.** Any knob read
   from the environment is inert under grading. Campaign-wide law.
3. **Confirm by content, not by status.** On a shared submission account, exit
   codes and id ordering are both unreliable; a unique marker in the note is
   the only sound confirmation.
4. **Absence from the local object database is not evidence of foreign
   origin.** That mistake cost me a published misattribution.

## 14. Next steps

- Difference this control against its P0 companion and report the sign with the
  honest two-pair power bound.
- If the sign transfers, the flip is a free bit-exact win and is
  promotion-eligible off this base; if it reverses, publish the reversal as a
  transfer-menu finding and keep `return 1`.
- Either way, instrument register high-water marks in `residual_rms_router` to
  test the occupancy-step hypothesis directly. I did not do this here.
- Campaign-level: the receipt channel needs an explicit token allocation rather
  than parallel arms discovering contention by colliding.


## Preregistered pair-2 decision rule

Recorded here, in the note body, so that it carries this submission's
server-side timestamp. At the moment this receipt is accepted, the companion
P0 receipt (`6fc8abf`) is still `validating` and has published no metrics, so
the rule below cannot be a post-hoc rationalisation of the result.

Sign convention: the M4 Pro result is that the hoisted arm is the slower one,
so the prediction is `dT < 0` for `dT = T(P0) - T(P1)`, with `T = D - 4P` the
rule-58 steady-state per-step time.

Power, stated up front: `sigma_pair(T) = 17.08 us/step` from the 14-receipt
consecutive-draw corpus, so one pair carries a 95% interval of +/-33.5 us/step
and two pairs +/-23.7. The M4 effect is +28.00 us/step and the M4->M5
attenuation seen elsewhere in this campaign is x0.436, giving an expected M5
effect near -12.2 us/step. That is a sign check with roughly 76% power, not a
resolution of the transfer coefficient, and no receipt count inside a
4-receipt ceiling would resolve it.

Rule:

- `dT <= -17.08` (at least 1 sigma, predicted sign): the M4 finding transfers
  with margin. Stop at 2 receipts.
- `-17.08 < dT < +17.08`: inside 1 sigma of zero, ambiguous. Draw pair 2 if the
  channel permits, since this is the only region where doubling n changes the
  verdict.
- `dT >= +17.08` (at least 1 sigma, reversed): contradicts 16/16 M4 slots. Draw
  pair 2, because a reversal is a first-class transfer-menu finding and should
  not rest on a single contested receipt.

The ceiling stays at 4 receipts either way. If pair 2 is indicated but the
channel is saturated by sibling arms, the round terminates at 2 and the
ambiguity is reported as the result rather than papered over.

_This submission note was prepared by an AI agent (OpenHands) on behalf of the
Senpai research campaign._
