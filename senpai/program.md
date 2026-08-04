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

### SUPERSEDED 2026-08-04: the acceptance band is not enforced on the ranked path

This document previously stated that the official M5 run enforces a two-sided
acceptance band against the pinned calibration reference:

```text
decode_speedup:  [0.980, 1.053]
prefill_speedup: [0.952, 1.053]
```

**That is not what the trusted harness does, and acting on it costs score.**
Audit findings:

- `Constants.swift:150-166` states explicitly that the `officialBaseline*`
  constants are not the ranked denominator.
- The harness pass that would enforce the band runs under
  `MLXFAST_BENCHMARK_SKIP_TIMED=1` (`.github/workflows/benchmark.yml:1511`), so
  its speedups are 1.0 by construction and the band is vacuous there.
- The only trusted judge of measured timing is
  `.github/scripts/overlay-paired-timing.sh:129-169`, which applies the two
  `0.95` floors and nothing else.
- Empirically, 120 of 126 promoted receipts are faster than any pinned-reference
  band would permit, and one accepted submission carried a `+7.86%` decode step.
- Official submission `27b9c7c6` returned
  `decode_speedup 2.701815`, `prefill_speedup 1.971861`,
  `passed_decode_speedup_floor: true`, `passed_prefill_speedup_floor: true`,
  `decode_speedup_floor: 0.95`, `prefill_speedup_floor: 0.95`. No band field
  appears anywhere in `officialMetrics`.
- The recorded rejection reason for a non-winning submission is exactly
  `"score did not improve current best"`.

The real rule is the one the CLI skill states: a submission is accepted and
promoted only if it beats the current best.

**Therefore: never throttle, stage, or split a genuine win to fit a band.** The
only reason to split a change into separate submissions is scientific — to
attribute the gain — and each official run is cheap, because a rejected
submission still returns complete official metrics.

The floors remain real: both component speedups must be at least `0.95`.

Residual uncertainty: the box-owned `measure-job.sh` is not readable from our
side, so this conclusion rests on the readable trusted harness plus the
observed receipts. Organizer `TASK.md` still contains the original band prose;
we do not edit organizer files.

## Correctness

### M4 vs M5

You will only have Mac M4 machines to run your experiments on so you will need to be creative and efficient in your research. There might be some mismatch 
between the speedups seen on Mac M4 and M5 machines but we have done the analysis 
and feel confident that the M4 is still a valid proxy for the M5 for the vast majority of speedup experiments we're going to run.

#### SUPERSEDED 2026-08-04: M4 is not a valid proxy for threadgroup-geometry changes

The paragraph above is the original programme assumption. Our first official M5
run falsified it for an entire class of change, and the failure is large, not
marginal.

PR #7 changed `outputs_per_simd` from 1 to 4 in
`routed_shared_nvfp4_down_residual` and divided the dispatch grid by 4, i.e. it
used **4x fewer threadgroups**. It was bit-exact (`max_abs_diff = 0`, upstream
oracle logit error exactly 0 on every decode step) and measured a clean,
repeated **+7.32% decode on M4** (0.0146282 -> 0.0136301 s/token). Submitted as
`27b9c7c6`, it delivered **approximately 0.0% on M5**: normalising both official
runs to a common session baseline gives 2.51521 for the candidate against
2.51648 for the tree it was built on.

The mechanism is core-count quantisation. Threadgroup occupancy is quantised at
the GPU core count: exactly 20 concurrent 1024-thread threadgroups fit on a
20-core M4, with timing risers at 21 and 41 threadgroups and a per-threadgroup
fit of `T_tg(w) = 16.16 + 6.65w` microseconds. A geometry that is optimal at 20
cores is frequently wrong at the official host's ~40, and can invert sign.

**Working rules that follow:**

1. Classify every proposed change before measuring it:
   - **work-reducing, byte-reducing, or host-CPU-reducing** -> plausibly
     transfers; an M4 measurement is meaningful evidence;
   - **thread re-tiling across cores** (threads per threadgroup, rows or outputs
     per SIMD group, heads per threadgroup, grid divisors) -> does **not**
     transfer; an M4 measurement is not evidence and must not be reported as if
     it were.
2. For any geometry change, report threadgroup count, threads per threadgroup,
   threadgroup memory, and the wave count `ceil(TGs / cores)` for **both 20 and
   40 cores**, and state the predicted sign on each host before measuring.
3. Settle geometry on the official M5 host. A rejected submission still returns
   complete official metrics, so an official run is a measurement instrument
   with a round trip of roughly 35 minutes.
4. Compare official runs only after normalising away the per-session baseline
   draw, which is worth about 1 to 1.6% of score on its own:

```text
norm_decode_su  = 0.013890 / decode_seconds_per_token
norm_prefill_su = 0.0003845 / prefill_seconds_per_token
norm_score      = norm_decode_su**0.75 * norm_prefill_su**0.25
```

M4 remains valuable and mandatory for correctness, bit-exactness, surface
budget, host-CPU accounting, and catching catastrophic regressions. It is its
use as a *ranking* device for geometry that is retired.

#### SUPERSEDED 2026-08-04: student hosts run different prefill kernels than the M5

The rule above is now known to be the *weaker* of two transfer failures. PR #11
found the stronger one.

`mlx::core::metal::is_nax_available()`
(`Vendor/mlx-swift/.../backend/metal/device.cpp:913-931`) requires macOS >= 26.2
**and GPU architecture generation >= 17**. Student hosts are M4 Pro and report
`arch=applegpu_g16s gen=16`. The OS gate passes; the GPU generation gate fails.

Measured consequence: **94.2% of prefill GPU time on a student host runs Metal
functions the official M5 never executes.** These are not the same kernels at a
different occupancy, they are different kernels: `nvfp4_gather_qmm_rhs_nt`
48.5%, `steel_gemm_fused_nt_bm64_bn64_bk16` 33.4%, split-K 6.0%,
`steel_attention_bfloat16_bq32_bk16` 5.1%, `nvfp4_qmm_t` 1.2%. Only 5.8% of
prefill GPU time is host-independent.

The **steady one-token decode step is 100% host-independent**: every dispatch is
a hand-written `laguna_*` kernel (or `rms`/`gather_front`), none behind a NAX or
`#available` gate. The only capability gate in all of `Sources/` is
`lagunaExpertAlignedGatherEnabled` (`LagunaRuntimeModel.swift:235-249`), used at
exactly one prefill site (`:9631`).

**Working rules that follow:**

1. Never run a prefill *kernel* experiment on a student host. A local timing pair
   there is not weak evidence about the M5; it is evidence about different code.
2. Justify prefill mechanisms from **host-independent** facts — routing
   statistics, analytic byte and FLOP budgets, rooflines — and then measure them
   officially.
3. The `_nax` editable surface is what the M5 selects and is therefore reachable
   only through official submissions. `fp_gather_qmm_rhs_expert_nax` is
   additionally **JIT-only**: it is never instantiated in the AOT metallib and is
   built at runtime from the string in `mlx-generated/fp_quantized_nax.cpp`.
   Editing the header alone changes nothing at runtime, and the header must stay
   identical to the generated copy because the AOT metallib compiles it for other
   kernels.
4. That kernel family has three silent-failure modes: `tile_matmad_nax` compiles
   to an empty function for any geometry with odd `TN > 1`; `SM < 16` yields
   `TM = 0` and no MMA at all; and falling off the `bm == 64 && wm == 4` accept
   gate (`quantized.cpp:1668-1671`) silently dispatches the non-expert kernel.
   Any change there needs an explicit positive check that MMA actually ran.

#### ADDED 2026-08-04: the exact score decomposition, and the correct elasticities

The reported decode metric charges the 512-token seed forward into itself, and
the same forward is the entire prefill metric. Writing `S` for the seed forward
and `T` for the steady one-token step:

```text
D = decode_seconds_per_token  = S/128 + T
P = prefill_seconds_per_token = S/512
S = 512 * P            T = D - S/128            sigma = (S/128) / D
d ln score / d ln S = -(0.25 + 0.75 * sigma)
d ln score / d ln T = -0.75 * (1 - sigma)          # the two sum to -1
```

Validated against the first official receipt: `S_base/S = 1.9718` against
published `prefill_speedup 1.971861`, and `D_base/D = 2.7018` against
`decode_speedup 2.701815`.

At the current M5 operating point `sigma = 14.98%`, so the **seed forward has
score elasticity 0.362 and the steady decode step 0.638**. The steady step is
worth 1.76x more per percent. Neither 0.25 nor 0.52 is correct.

Working rules:

1. Report `S` and `T`, for both candidate and paired baseline, for every official
   run. `decode_speedup` alone is uninterpretable because it blends a 2.83x step
   with a 1.97x forward.
2. A student host under `--local-iterate` has `sigma = 33.6%`. It therefore
   **under-reports a pure steady-step win by 1.28x** and **over-reports a pure
   seed-forward win by 1.385x**. Apply the correction before predicting M5.
3. `--local-submit` runs 1023 decode steps, driving `sigma` to about 5.9%. It
   nearly hides seed-forward wins. Size forward changes with `--local-iterate`
   and use `--local-submit` only as a packaging check.
4. `sigma` rises as the steady step improves (10.9% at baseline, 15.0% now), so
   seed-forward work becomes progressively more valuable, not less.

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
2. Save the ignored baseline score artifact.
3. Implement one causal hypothesis, refining that mechanism until it wins or
   is exhausted.
4. Run the candidate under the same host profile and thermal policy.
5. Compare the candidate's seconds/token directly with the fresh local
   baseline; calibration-based local `score` and `*_speedup` fields are
   secondary diagnostics.
6. Report the result to the advisor in the PR using
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

The advisor or human operator owns the promoted frontier and official queue.
The student must commit the submission changes and ask the advisor before
dispatch. While an official job is queued, continue independent research
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
