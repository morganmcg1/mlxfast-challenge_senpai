# R105-B Phase B, arm P0 — PR #597, student `maple-frieren`

Marker for receipt identification: **R105-B Phase B, arm P0**.

## 1. Context and goal

The Laguna XS 2.1 text tower runs a fused residual + RMSNorm + router kernel
(`residual_rms_router`) at the head of every MoE block. Some months ago that
kernel acquired a **hoisted weight-prefetch salvo**: four `device` loads of the
router weight tile issued near the top of the kernel, ahead of the threadgroup
barrier that separates the RMS reduction from the router GEMV. The intent was
the classic one — start the router weight fetch early so its latency overlaps
the reduction. The knob controlling it is `DARKBLOOM_ROUTER_WEIGHT_PREFETCH`,
read in `Sources/MLXFastModel/LagunaRuntimeModel.swift` and compiled into the
Metal source that the runtime hands to the shader compiler.

The salvo was never adjudicated end to end. It was introduced on the strength
of a microbenchmark and a plausible latency story, and it has been shipped ever
since as the compiled-in default (`return 1`). R105-B was opened to answer one
question: **does the prefetch salvo actually pay for itself on the scored
decode path, and if not, should the default be flipped?**

The goal of this receipt is not to win the leaderboard. It is to place one half
of a paired A/B on the ranked M5 so the campaign learns whether an effect
measured on M4 Pro transfers to the ranked hardware.

## 2. Environment

- Research host: Apple M4 Pro, 48 GB unified memory, low-memory startup
  profile, 40C thermal gate honoured on every timed slot.
- Ranked host: self-hosted M5 Max, 128 GB. Not available to me directly; the
  only channel to it is this submission API.
- Toolchain: the pinned Swift toolchain from `setup.sh`; every build used
  `--force-resolved-versions` and `Package.resolved` was restored afterwards.
- Timing path: `./benchmark.sh --local-iterate` for the scored worker build,
  never a bare `swift build -c release`.

The M4/M5 gap is the central caveat of this whole experiment and I want it
stated up front rather than buried. **M4 Pro reports Apple GPU generation 16
and does not select the `_nax` kernel variants that the ranked M5 uses.** The
`residual_rms_router` kernel itself is not one of the `_nax` families, so the
kernel under test is the same source on both machines — but the surrounding
dispatch, the occupancy the scheduler can reach, and the memory system that
determines whether a hoisted load is free or costly are all different. An M4
result is directional evidence about a shared kernel, not proof about M5.

## 3. Prior work and baseline

Phase A of R105-B was a 144-slot position-matched ABBA study on M4 Pro,
approved and accepted without qualification by the advisor. Its design used
five arms so that the *placement* of the salvo could be separated from the
*loads* themselves:

- **P0** — no prefetch salvo at all.
- **P1** — the shipped salvo: four loads hoisted above the barrier.
- **P1B** — the same four loads, hoisted, different register assignment.
- **P5** — the same four loads, issued **below** the barrier, i.e. at their
  natural position, so the loads are performed but not hoisted.

The headline result, verdict **V-PLACEMENT**:

```
pooled(P1, P1B) - P0 = +28.00 us/step   CI [+22.23, +33.77]   16/16 positive
                     = +0.426 % of cs
P0 -> P5             = covers zero
P1 -> P5             = -19.37 us/step   CI [-27.92, -10.83]
```

Read that carefully, because it is the interesting part. Performing the four
loads costs nothing (`P0 -> P5` covers zero). Performing them **hoisted above
the barrier** costs 28 us/step. Moving them back down below the barrier
recovers 19 of those microseconds. **The cost is cross-barrier placement, not
the loads.** The most likely mechanism is that hoisting the loads extends the
live range of four registers across the barrier, raising the kernel's register
high-water mark and costing an occupancy step; a secondary possibility is that
the hoisted loads contend with the reduction's own traffic in the same cycle
window. I did not instrument register allocation directly, so I am reporting
the placement effect as measured and the mechanism as hypothesis.

**Bit-exactness was established empirically, not assumed.** Across all 144
timed slots there was exactly **one** distinct sha256 over the emitted token
stream, and the golden tree digest `d93a6d14` was unchanged throughout.
`prefetch in {0, 1, 5}` are bit-exact with each other. This is a scheduling
change, not a numerics change; nothing here approaches the accepted attention
quantization envelope.

A secondary preregistered arm, A0, returned **A0-INCONCLUSIVE**: the hardware
counter read 13.77 against a preregistered threshold of 12, and the N-1
discriminator did not fire. I am not claiming A0.

## 4. Hypotheses

- **H1 (primary).** The M4 placement penalty transfers in sign to M5, so
  `prefetch = 0` is at least as fast as `prefetch = 1` on the ranked host.
- **H2 (null).** The effect is M4-specific — different register budget,
  different occupancy cliff — and M5 shows no resolvable difference.
- **H3 (reversal).** M5's memory system rewards the hoist and `prefetch = 1`
  is genuinely faster there. This would be the most valuable outcome of the
  three, because it would be the campaign's first measured instance of a
  microarchitectural optimisation whose sign flips across Apple GPU
  generations, and it would put a hard bound on how far M4 evidence can be
  trusted.

I preregistered all three before drawing any receipt. There is no outcome of
this pair that I will describe as a failure.

## 5. Approach and tradeoffs

The change under test is a **one-token flip of a compiled-in default**:

```swift
// Sources/MLXFastModel/LagunaRuntimeModel.swift, ~line 686-706
if let env = ProcessInfo.processInfo.environment["DARKBLOOM_ROUTER_WEIGHT_PREFETCH"],
   let v = Int(env) { return v }
else { return 0 }        // was: return 1
```

There is a subtlety here that matters for anyone reading this receipt and that
I want on the record, because it is a general law about this benchmark and not
a fact about my patch. **The graded run cannot see the environment variable.**
The grader executes the submitted worktree in its own process environment;
`DARKBLOOM_ROUTER_WEIGHT_PREFETCH` is not set there. So the `if let env`
branch never fires under grading, and the only value that can ever reach the
kernel on the ranked host is **the compiled-in constant in the `else`
branch**. The env var is a research affordance for my local sweeps and is
invisible to the score. That is exactly why this receipt has to be a *commit*
that changes the `else` constant, and why no amount of local env-var
experimentation could ever substitute for it.

Tradeoff considered and rejected: I could have deleted the salvo from the Metal
source entirely rather than gating it. I chose the gate because it keeps P0 and
P1 a one-token difference, which makes the paired receipts trivially auditable
and keeps the revert path to one character if M5 disagrees with M4.

## 6. Implementation and files changed

Submitted surface, one file:

- `Sources/MLXFastModel/LagunaRuntimeModel.swift` — 6 insertions, 4 deletions.
  The functional part is the `return 1` -> `return 0` flip. The remainder
  updates the doc comment above the accessor to record that the salvo was
  adjudicated end to end and that the shipped default was reversed, so the next
  reader does not have to rediscover Phase A.

Nothing else in the 97 `editablePaths` is touched by this commit. Submitted
surface total is 1,736,131 bytes against the 3,000,000 byte cap.

## 7. Exact commands

```bash
# rebase onto the assignment base
git rebase 0954002c16014a03091e1856cdf356fb0e6a3e38

# the flip
$EDITOR Sources/MLXFastModel/LagunaRuntimeModel.swift
git commit -am "R105-B P0: flip DARKBLOOM_ROUTER_WEIGHT_PREFETCH compiled-in default 1 -> 0"

# compile gate
swift build -c release --force-resolved-versions
git checkout -- Package.resolved

# submission
bash senpai/submit-official.sh 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7 \
  --note-file research/maple-frieren-r105b-note-p0.md
```

Phase A reproduction (M4 Pro, 144 slots) is
`research/maple-frieren-r103a-abba.sh` driving the five prefetch arms, analysed
by `research/maple-frieren-r105b-pooled.py` and
`research/maple-frieren-r105b-verdict.py`.

## 8. Experiments performed

1. **Phase A, 144 position-matched slots, M4 Pro.** Five arms, ABBA ordering,
   thermal gate on every slot. Produced V-PLACEMENT above.
2. **Token-identity audit.** sha256 over the emitted token stream for all 144
   slots; one distinct value.
3. **Compile gate on the flip.** `swift build -c release
   --force-resolved-versions`, exit 0 in 33.1 s.
4. **Frontier-relationship audit.** See section 11 — this changed how the
   absolute score of this receipt should be read.
5. **This receipt (P0)** and its companion control (P1), drawn from the ranked
   M5 as a paired A/B.

## 9. Failures and corrections

I am recording these because they cost real time and the next student should
not repeat them.

- **I initially believed this branch's absolute score was not
  frontier-comparable.** The submitted surface differs from `origin/main` on 27
  files and I read that as unpromoted divergence, which would have made only
  the P0-minus-P1 difference interpretable. That was wrong: see section 11.
- **I twice confirmed a submission by the wrong signal.** Once by exit code,
  once by "the newest submission id changed". Both produced false positives,
  because this API account is shared and other traffic lands between my poll
  and my read. The receipt I briefly believed was mine (`288c702`) belonged to
  another campaign entirely. **Confirmation must be by a unique content marker
  in the note**, retrieved with `mlxfast submission-note <id>`. That is why
  this note carries an explicit marker line at the top.
- **A conflict-retry loop is actively harmful.** The API permits one submission
  in flight per account and enforces a shared rate limit; a rejected
  *conflict* attempt still consumes rate-limit budget. Retrying on conflict
  burns the budget that the successful attempt needs. The correct pattern is
  read-only polling of `mlxfast submissions` and exactly one fire when no
  `validating` or `queued` row exists.
- **Phase A's A0 arm did not resolve.** I reported it inconclusive rather than
  reaching for a post-hoc threshold.

## 10. Measured results

From Phase A, M4 Pro, 144 slots:

| comparison | delta (us/step) | 95% CI | sign consistency |
|---|---|---|---|
| pooled(P1,P1B) - P0 | +28.00 | [+22.23, +33.77] | 16/16 |
| P0 - P5 | ~0 | covers zero | - |
| P1 - P5 | -19.37 | [-27.92, -10.83] | - |

The M5 numbers for this arm are whatever this receipt returns; they are
reported to the advisor alongside the companion P1 control.

**Power, stated plainly.** My paired standard deviation across consecutive
non-outlier receipts is sigma_pair(T) = 17.08 us/step. That gives a half-width
of **+/-33.5 us/step for one pair** and **+/-23.7 us/step for two pairs**. The
M4 effect is +28.00 us/step, and any transfer coefficient below about 1.2 puts
the true M5 effect inside my two-pair noise band. **Two pairs cannot resolve a
x0.436 transfer.** This receipt is a sign-and-transfer check, not a measurement
of magnitude, and I will not present it as one.

## 11. Caveats

- **Absolute score comparability.** I verified that `origin/main`
  (`1bc1c895`) is a strict **ancestor** of this branch's base
  (`0954002c`). The 27-file delta against `origin/main` is comment-stripping in
  vendored files plus already-merged 105-C/D/E work, not unpromoted divergence.
  The branch is therefore **strictly ahead of the promoted frontier**, and the
  absolute `cs` this receipt returns *is* frontier-comparable and
  promotion-eligible. This is a correction to my earlier reading.
- **A `rejected` ranking verdict is not a correctness failure.** It can mean
  only that the score did not beat the current best. Correctness, error, and
  the two 0.95 floor verdicts must be inspected separately from ranking status.
- **One pair is one pair.** Sign agreement between M4 and M5 would be
  encouraging; it would not be a confirmed magnitude.
- **The shared account contaminates timing.** 1,216 sha-bearing rows exist on
  this account; only 60 are commits from this repository. The ~22-minute
  receipt cadence I observe is other campaigns, not mine, and I cannot
  serialise against it.

## 12. Learning

Three things generalise beyond this experiment.

1. **Separate placement from work.** The five-arm design (P0/P1/P1B/P5) is what
   turned "prefetch is slow" into "hoisting across the barrier is slow, the
   loads are free". A two-arm A/B would have produced the right sign and the
   wrong mechanism, and the wrong mechanism would have sent the next optimiser
   hunting for bandwidth that was never the problem.
2. **The compiled-in constant is the only thing the grader sees.** Any research
   knob read from the environment is invisible under grading. This is a
   campaign-wide law, not a property of my patch.
3. **Confirm by content, not by status.** On a shared submission account, exit
   codes and id ordering are both unreliable. A unique marker in the note body
   is the only sound confirmation.

## 13. Next steps

- Draw the companion **P1** control from a distinct commit with `Sources/`
  byte-identical apart from the one-token constant, so the pair is auditable.
- Report both raw halves (`cand_dec`, `cand_pre`, `cs`, `L`, `status`,
  `submissionCommitSha`) to the advisor rather than a derived speedup alone.
- If the sign transfers, the flip is a free bit-exact win and should be
  promoted; if it reverses, publish the reversal as a transfer-menu finding and
  restore `return 1`.
- Either way, the placement mechanism is worth a dedicated look at register
  high-water marks in the `residual_rms_router` kernel, which I did not
  instrument here.

_This submission note was prepared by an AI agent (OpenHands) on behalf of the
Senpai research campaign._
