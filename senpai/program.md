# Poolside Laguna XS 2.1 MLX Inference Autoresearch

This document defines how advisor and student agents run competition research in this repository.
The goal is to reduce inference latency on the Poolside Laguna XS 2.1 NVFP4 model on a M5 Mac 
and WIN the https://mlx.fast competition. The research team of agents here are fully expected to be able to deliver a winning speedup solution for this competition.

The target is Poolside Laguna XS 2.1 NVFP4 text inference on the serial
`laguna-xs-2.1-serial-v2` track. 

## Mission

Maximize the official paired inference speedup score:

```text
score = decode_speedup^0.75 * prefill_speedup^0.25
```

Higher is better. `decode_speedup` and `prefill_speedup` compare the candidate
with the pinned baseline measured in the same official session on the same M5
Max. Both component speedups must be at least `0.95`.

The official timed window and score weights make decode the primary
optimization target:

- Prefill: one cold, validated 512-token forward.
- Decode: a charged 512-token seed forward followed by 128 validated
  teacher-forced one-token steps.

The deployed ranked wrapper does not enforce the legacy `1.053` candidate-gain
cap described by `AcceptanceBand`. The inner benchmark binary can report a
band failure, but the on-box measurement wrapper owns the timed verdict: it
checks baseline health, then publishes the paired candidate result through
`overlay-paired-timing.sh`, which applies the two `0.95` floors. Accepted
receipts with gains well beyond 5% confirm this behavior. Promotion then
requires beating the current best.

Never throttle, stage, or split a genuine win to fit the legacy band. Split a
mechanism only when the smaller steps are independently correct and improve
causal attribution.

## Correctness

### M4 vs M5

Most student experiments run on M4 Macs. Treat those measurements as
directional only after proving that the M4 and ranked M5 execute the same code
family. M4 Pro hosts expose Apple GPU generation 16 and do not select the
`_nax` prefill kernels used by the M5; threadgroup geometry can also change
sign with core count. M4 remains valuable for correctness, call-path checks,
host-cost measurements, and matched timing of host-independent decode work.

### Correctness gate
Correctness is a hard gate, not a tradeoff. Every checked greedy token must
match the golden behavior. A fast candidate that changes a token, violates the
serial protocol, fails a hidden behavior gate, or only improves an unscored
path is a failed experiment.

Validation numbers are steering evidence. Only the official paired M5 result
is a ranking claim.

Keep two concepts separate:

- The **official timing baseline** is the operator-pinned tree measured beside
  every candidate on the M5. Changing it is a benchmark-contract decision.
- The **promoted code frontier** is the best accepted submission and the code
  starting point that subsequent research must beat.

Start each clean research round from the promoted frontier, record its exact
commit as `BASE_SHA`, and rerun a same-host local baseline. Results from an
older frontier remain useful evidence, but require remeasurement on the current
frontier before promotion.

## Contract Map

Useful files depending on what you're working on are:

| Topic | Authoritative detail |
| --- | --- |
| Goal, hardware, scored path, timing, and score | [`AGENTS.md`](../AGENTS.md#goal), [`TASK.md`](../TASK.md#default-ranked-contract), and [`docs/benchmark-window-freeze.md`](../docs/benchmark-window-freeze.md) |
| Model artifacts and permitted precision changes | [`TASK.md`](../TASK.md#model-artifacts) |
| Editable submission surface | [`benchmark.json`](../benchmark.json) and [`AGENTS.md`](../AGENTS.md#what-you-may-optimize) |
| Kernel source forms and build behavior | [`AGENTS.md`](../AGENTS.md#what-you-may-optimize) and [`README.md`](../README.md) |
| Correctness, integrity, and serial non-speculation | [`AGENTS.md`](../AGENTS.md#correctness-gates) and [`TASK.md`](../TASK.md#correctness-gates) |
| Local baseline, candidate, and promotion commands | [`experiment-runbook.md`](experiment-runbook.md) |
| Assignment scope and authority | [`assignment-template.md`](assignment-template.md) |
| Macs, memory, thermals, telemetry, fan policy, AWS, and process lifecycle | [`infra.md`](infra.md) |
| Risk-based local quality evaluation | [`quality-evaluation.md`](quality-evaluation.md) |
| NAX/pre-NAX MoE layout troubleshooting | [`pre-nax-moe-layout.md`](pre-nax-moe-layout.md) |
| Terminal PR reporting | [`result-template.md`](result-template.md) |

When prose and executable configuration disagree, stop and resolve the
conflict. `benchmark.json` owns the submission surface; the trusted harness and
frozen-window tests own scored behavior.

This worktree uses the
[research fork](https://github.com/morganmcg1/mlxfast-challenge_senpai) of the
[official challenge repository](https://github.com/Layr-Labs/mlxfast-challenge).
Frontier selection and harness refresh have different meanings; follow the
[frontier workflow](experiment-runbook.md#start-from-the-promoted-frontier)
rather than inferring the current frontier from a remote branch name.

## Infrastructure

All setup mechanics and host gotchas—including memory profiles, the one-model-
process rule, thermal waits, telemetry, fan ownership, orchestration timeouts,
and AWS lifecycle—live in [`infra.md`](infra.md). Students must not improvise
around those controls.

You will mostly be running your experiments on AWS Mac M4 Pro machines.

## Scored Path And Experiment Scope

The detailed model geometry and optimization surface are already documented in
[`AGENTS.md`](../AGENTS.md#what-you-may-optimize) and
[`TASK.md`](../TASK.md#model-artifacts). Three facts are especially useful when
choosing research:

- The scored forward pass is in
  `Sources/MLXFastModel/LagunaRuntimeModel.swift`. The vendored
  `Laguna.swift` is principally an upstream-equivalence oracle, so changing it
  alone does not speed the scored path.
- All text-tower weights remain in unified memory. Target compute, unified-
  memory traffic, scheduling, and layout—not disk I/O, expert streaming, or an
  expert cache.
- `benchmark.json` is the source of truth for candidate files. Supporting
  tests and docs may improve research clarity, but the submitted candidate
  must work from `editablePaths` alone.

Every assignment must list submitted paths separately and validate them
against the committed `benchmark.json` at its full `BASE_SHA` with
`validate-assignment-scope.sh`. It must also run the cheap editable-surface
budget preflight: 3,000,000 bytes total, 524,288 bytes per file, and 262,144
bytes of growth. The current editable-file count is a repository test fixture,
not an official rule.

### Accepted attention quantization envelope

Only Q/K/V/O and per-head `g_proj` may be re-quantized, and only to group-32
affine INT8. Read the full
[accepted attention quantization envelope](../TASK.md#accepted-attention-quantization-envelope)
before changing representation or trusted-harness assumptions.

Before a kernel experiment, identify the runtime-effective JIT or AOT source
and relevant `_nax` form from the organizer docs. Numerical evidence is
required when an experiment changes math, reduction order, precision, packing,
or layout; do not automatically impose the full numerical-quality stack on an
operation-preserving scheduling or tiling change.

Before timing any selector or environment knob, show the call path from that
control to the scored shape. A control that reaches only a dormant fallback is
not an experiment arm.

## Research Pace

Move quickly enough to explore new ground. The default arm is one causal
question followed by the cheapest test that can decide it. Verification is a
tool for resolving uncertainty, not a measure of diligence.

In practice:

- Establish the unchanged baseline once for the arm.
- Reach the end-to-end local screen early.
- Do not rerun a check that has already answered its question.
- Do not run every available test because it exists.
- Escalate validation only for a specific risk, an ambiguous result, or a
  promotion candidate.
- Stop an unpromising arm promptly and record the negative result.

A single clear matched-pair win is enough to advance from exploration to
confirmation. Repetition is useful only when noise or inconsistency could
change the decision.

## Student Workflow

For each assigned PR, the student should:

1. Record `BASE_SHA` and measure the unchanged frontier once on the assigned
   host.
2. Complete the scope, budget, reachability, and authority checks in
   [`assignment-template.md`](assignment-template.md).
3. Save the ignored baseline score artifact.
4. Implement one causal hypothesis, refining that mechanism until it wins or
   is exhausted.
5. Run the candidate under the same host profile and thermal policy.
6. Compare the candidate's seconds/token directly with the fresh local
   baseline; calibration-based local `score` and `*_speedup` fields are
   secondary diagnostics.
7. Report the result to the advisor in the PR using
   [`result-template.md`](result-template.md).

### Running the local harness

The runbook owns the exact
[baseline/candidate commands](experiment-runbook.md#record-a-matched-baseline-and-candidate),
[same-host ratio calculation](experiment-runbook.md#extract-the-comparison),
ignored-artifact rules, and pre-promotion sequence so those commands cannot
drift in multiple documents.

## Student Agent - Experiment Ladder

The ladder is selective, not cumulative. Start low and climb only when the
next step can change the decision.

### 1. Orient

- Confirm the hypothesis reaches the scored runtime and has a plausible
  end-to-end effect.
- Identify candidate files, runtime-effective kernel forms, and any
  research-only support files.
- Inspect for prompt-, token-, fixture-, or benchmark-specific behavior.

Static analysis can close a hypothesis without a build. A targeted compile,
unit test, or microbenchmark is justified when it directly tests the proposed
mechanism; it is not a mandatory ceremony.

### 2. Fast screen

Run `--local-iterate` for the candidate. It rebuilds stale binaries, runs the
public correctness tripwire, and produces the short timing signal. Add a
targeted test only when the changed boundary needs one.

`--local-submit` uses a much longer decode window and is a packaging and final
correctness gate. It can dilute seed-forward improvements, so do not use it as
the primary causal timing screen.

Do not put a full `swift test`, repeated smoke test, upstream-equivalence run,
quality panel, and `--local-submit` in every edit loop. That spends research
time proving the same fact several times.

### 3. Resolve uncertainty

Use the smallest extra check that distinguishes the live alternatives:

- Repeat the matched measurement once when a promising gain is near noise or
  conflicts with another sample.
- Use focused instrumentation or a microbenchmark to identify a named cost,
  then remove instrumentation before end-to-end timing.
- Run opt-in MLX runtime tests, upstream equivalence, or the local quality
  panel when the experiment changes the corresponding risk boundary.

If no available check is likely to change the decision, close the arm with the
uncertainty recorded.

### 4. Confirm for promotion

For a stable winner, run the full Swift tests once, `--local-submit`, and the
final candidate-surface inspection from the runbook. Confirm both prefill and
decode, not only the aggregate. Apply stronger numerical or quality checks
only when their documented risk trigger is present.

### 5. Official promotion

The advisor owns the promoted frontier and coordinates the official queue. An
authorized advisor, student, or human operator may dispatch an official
submission; a student must first commit the candidate and coordinate its queue
entry with the advisor. An authorized campaign role may submit from a
provisioned AWS host, but must never print or commit its credentials.

Every official submission from this Senpai campaign must first use
`mlxfast submit --model "senpai"`. This campaign-specific attribution rule
overrides generic `mlxfast` model-name guidance. Only if the submission API
explicitly rejects `senpai` as an invalid or unsupported model value may the
same candidate be retried once using the exact underlying provider/model name.
Never fall back for a timeout, network error, validation failure, or unrelated
error because the first submission may already exist. The public note must
include the explicit rejection and fallback fact when a fallback was necessary.
Do not otherwise copy the underlying provider/model into notes or campaign
metadata.

Multiple Senpai instances may share account-scoped validation capacity. If the
API reports that the account's current validation slot is occupied, keep the
candidate in the coordinated queue; only the queue owner may poll `mlxfast
submissions`—at most once every ten minutes and no sooner than server retry
guidance—and dispatch it after capacity clears.

While an official job is queued, continue independent research
against its recorded frontier instead of waiting idle; rebase and rebaseline
only if promotion changes that frontier. Queue and host mechanics belong in
[`infra.md`](infra.md).

## Correctness And Validity

Exact-token correctness and the serial protocol are non-negotiable. The full
public/hidden gate stack, non-M5 fixture-drift procedure, and local override
rules live in [`AGENTS.md`](../AGENTS.md#correctness-gates) and
[`AGENTS.md`](../AGENTS.md#notes-for-autonomous-agents). 

The serial boundary has a simple research interpretation: a one-token request
advances one position and cannot create future logits or KV state. Read the
full [serial non-speculative rule](../TASK.md#serial-non-speculative-rule-default-track)
before changing decode state or reuse. Optimizations must be prompt-independent
and useful in single-pass production inference.

Dispatch and output-layout interpretation are one invariant. If sparse-MoE
quality collapses on a pre-NAX host, or an experiment changes NAX capability,
tiling, packing, or strides, use
[`pre-nax-moe-layout.md`](pre-nax-moe-layout.md) rather than debugging from a
condensed description here.

Use `--local-iterate` as the normal correctness screen. Escalate to upstream
equivalence or the advisory quality panel for risk-bearing numerical,
representation, activation, dispatch/layout, pruning, or output-head changes,
or to diagnose an observed mismatch. The complete triggers, tasks, recorded
baseline values, and exit semantics are in
[`quality-evaluation.md`](quality-evaluation.md). These local checks never
relax the official exact-token or hidden M5 gates.

Run upstream equivalence through `research/run_upstream_equivalence.sh`. A
filtered Swift command that selects zero tests is a failed validation even if
it exits zero; the wrapper requires the oracle report marker.

Our local quality panel is expensive and slows experiment throughput. Run it only
for a named risk or unresolved question that cheaper exact checks cannot answer.

Treat new exact matched-reference or upstream-equivalence divergence as a hard
stop. Treat the panel's retention, PPL, and response-prefix verdict as an amber
drift alarm, not an automatic submission veto: accepted-rank calibration shows
that percentage tuning cannot make this proxy reproduce official acceptance.

If a fallback restores correctness but consumes the measured gain, the
candidate is not a winner.

## Research Method

A research loop for inspiration, feel free to deviate if you can move faster and more creatively in the research space:

1. State the causal question and inherited validity boundary.
2. Locate and, when useful, measure the target cost.
3. Estimate the plausible end-to-end signal or make bounding it the first
   result.
4. Test one causal mechanism.
5. Reject quickly on validity, feasibility, or end-to-end speed.
6. Confirm only credible winners.
7. Compose only individually measured winners.
8. Preserve negative results so later agents do not repeat them.

Every experiment PR should state:

```text
Causal question:
  What mechanism or uncertainty does this arm test?

Target evidence:
  Which measured cost or source observation motivates it?

Expected signal:
  What result would be meaningful relative to likely noise?

Cheapest decisive test:
  What is the shortest path to a decision, including any risk-specific gate?

Stop rule:
  What evidence promotes, revises, or ends the arm?
```

Broad directions are acceptable for discovery, but must become falsifiable
before implementation. Do not invent a numerical gain before measuring or
bounding the target cost.

Research and literature-search commands are in
[`experiment-runbook.md`](experiment-runbook.md#research-search).

## Research Map

Choose work from fresh profiles, source inspection, current promoted diffs,
and prior results—not from a fixed checklist. Plausible cost centers include
NVFP4 matmul and MoE dispatch, attention and RoPE, KV-cache movement, MLX graph
and launch scheduling, weight/transform layout, and the output head. The
organizer's [practical optimization ideas](../AGENTS.md#practical-optimization-ideas)
provide insptiration, not direction - feel free to deviate from these if you can move faster and more creatively in the research space.

Reject directions that touch only unscored work, have a maximum plausible gain
below timing noise, or compose several unmeasured ideas. Contract-specific
invalid strategies—including future-token methods, benchmark-only caching,
public-prompt specialization, nonexistent expert streaming, and unrelated
runtime stacks—are catalogued in
[`AGENTS.md`](../AGENTS.md#avoid-these-wrong-strategies) and
[`TASK.md`](../TASK.md#serial-non-speculative-rule-default-track).

## Decision Rules

- **Invalid candidate:** a correctness, protocol, memory, build, or submission-
  surface failure. Repair only if a plausible compliant implementation remains.
- **Dead hypothesis:** the target cost is absent or too small, or a valid
  implementation shows no meaningful end-to-end gain.
- **Ambiguous:** noise, platform transfer, or a prefill/decode tradeoff could
  change the decision. Run only the smallest additional test that resolves it.
- **Green:** a valid, clear same-host baseline/candidate gain with no component-
  floor risk and a candidate limited to the submission surface.

A microbenchmark win without an end-to-end win is useful evidence, not a
promotable candidate. The physical comparison and paired local estimate live
in [`experiment-runbook.md`](experiment-runbook.md#extract-the-comparison),
not in calibration-based local score fields.

## Final Principle

Speedup is both the target and the operating principle of this competition. Explore boldly, test
decisively, and spend verification time only where it changes a research or
promotion decision. It is of the utmost importance that we secure our posisiton at the top of the competition leaderboard - the consequences will be dire for us if we don't, I'm serious.
