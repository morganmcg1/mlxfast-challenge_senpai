# Poolside Laguna XS 2.1 MLX Inference Autoresearch

This repository is the research target for optimizing the text tower of
Poolside Laguna XS 2.1 NVFP4 on Apple Silicon. The ranked competition track is
`laguna-xs-2.1-serial-v2`: one 512-token prefill followed by serial,
one-token-at-a-time decode. Improve real inference latency while preserving the
benchmark's exact observable behavior.

This program adapts the measurement discipline and experiment structure from
the
[Senpai LLM inference optimization guide](https://github.com/wandb/senpai/blob/main/LLM-INFERENCE-OPTIMIZATION-SENPAI-GUIDE.md)
to this repository. Generic advice from that guide is subordinate to the local
contract in `AGENTS.md`, `TASK.md`, `README.md`, `benchmark.json`, and
`docs/benchmark-window-freeze.md`. In particular, this track is Swift/MLX on a
single Apple GPU and explicitly forbids speculative decoding.

## Mission

Maximize the official paired inference speedup score:

```text
score = decode_speedup^0.75 * prefill_speedup^0.25
```

Higher is better. `decode_speedup` and `prefill_speedup` compare the candidate
with the pinned baseline measured in the same official session on the same M5
Max. Both component speedups must be at least `0.95`.

Correctness is a hard gate, not a tradeoff. Every checked greedy token must
match the golden behavior. A fast candidate that changes a token, violates the
serial protocol, fails a hidden behavior gate, or only improves an unscored
path is a failed experiment.

The official timed window and score weights make decode the primary
optimization target:

- Prefill: one cold, validated 512-token forward.
- Decode: a charged 512-token seed forward followed by 128 validated
  teacher-forced one-token steps.

The official M5 run also enforces a two-sided acceptance band against the
pinned calibration reference:

```text
decode_speedup:  [0.980, 1.053]
prefill_speedup: [0.952, 1.053]
```

This caps a single ranked submission's apparent gain at about 5%. If a local
candidate is more than about 5% faster, split it into independently measurable
submissions and validate each step. Split only along natural, independently
correct improvements; never add an intentional regression, throttle, or
benchmark-dependent switch to fit the band. Local modes warn about the fast
edge but do not enforce the band.

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

### SENPAI Autoresearch quality checkpoint

The official private competition evaluation includes a hidden quality check.
We maintain a local advisory panel with frozen thresholds for the maximum
acceptable quality degradation in exchange for inference speedup. See
[`quality-evaluation.md`](quality-evaluation.md) for triggers, commands,
thresholds, exit semantics, and the upstream-equivalence diagnostic. This
panel cannot relax exact-token correctness or replace the hidden M5 quality and
behavioral gates. Run only one model-holding process at a time.

### Your fork

This worktree is a fork
(https://github.com/morganmcg1/mlxfast-challenge_senpai). The official
repository (https://github.com/Layr-Labs/mlxfast-challenge) pins the official
baseline. Sync the fork with the official repository before submitting results.

## Non-Negotiable Execution Environment

Benchmarking this target requires macOS on Apple Silicon.

- The stock Linux/CUDA Senpai student environment cannot build or benchmark
  this repository. Students that execute experiments must run on macOS hosts
  with the Xcode Metal toolchain.
- The model is about 21.6 GB and is fully RAM-resident. Roughly 36 GiB of
  unified memory is the practical minimum; 64 GiB or more is strongly
  preferred. The official runner is one M5 Max with 128 GB.
- A host below 64 GiB automatically uses the low-memory startup profile. That
  profile changes memory management, not the ranked code path.
- Run only one model-holding benchmark or correctness process per host.
  `swift test` does not load the real model and may run independently, but
  `benchmark.sh`, direct correctness commands, and other real-model commands
  must never overlap.
- The benchmark waits for the GPU to cool below 40C. A cool-down wait is normal,
  can last several minutes, and must not be killed. If the gate aborts because
  another workload keeps the GPU hot, free the host and retry.
- Do not disable the thermal gate for performance evidence. Hot-start timings
  are debugging data only.
- Students must not change fan controls or automate privilege escalation. Fan
  policy is an operator-owned host-lifecycle setting established before work
  is assigned and held constant across each unchanged-baseline/candidate
  comparison.

### Warning: NAX dispatch and output layout must agree

A prior host-dependent corruption bug occurred when Swift interpreted the
generic pre-NAX MoE gate/up output as the packed NAX layout. The fix in commit
`2225854` made Swift's layout decision mirror the backend's complete capability
and tiling predicate.

Treat dispatch and layout interpretation as one invariant. If sparse-MoE
prefill quality collapses on a non-M5 host, after an OS change, or under a Metal
architecture or tiling override, stop and verify that predicate before tuning
anything else. Changes to NAX availability, packing, strides, or tiling must
update both sides and add or adjust supporting correctness tests.

See [`pre-nax-moe-layout.md`](pre-nax-moe-layout.md) for the output contracts,
dispatch predicate, symptoms, host inspection, and troubleshooting procedure.

If a student cannot access a qualifying Mac, it may do static analysis or
prepare a tightly scoped implementation, but it must report the experiment as
unmeasured. It must not substitute Linux, CUDA, simulator, or projected
performance for a real result.

For Senpai orchestration, pre-provision the pinned checkpoint, Xcode/Metal
toolchain, and build cache on each Mac before assigning experiments. Route at
most one active student to each physical Mac. Set the student command timeout
high enough to cover a possible 900-second thermal cool-down plus incremental
build, model load, correctness, and timing; a controller timeout that kills a
normal cool-down produces no research evidence.

### AWS EC2 Mac thermal provisioning

Concrete capacity discovery, provisioning, sharding, artifact retrieval, and
teardown for AWS EC2 Mac's are in [`infra.md`](infra.md); this section remains the experimental-
validity and thermal contract.

When using AWS Mac's for this competition, prefer the [`mac-m4max.metal`](https://aws.amazon.com/about-aws/whats-new/2026/01/amazon-ec2-m4-max-mac-instances-ga/)
with 128 GB of unified memory. Do not assign real-model experiments to
`mac-m4.metal`: its 24 GiB is below this repository's roughly 36 GiB practical
minimum. `mac-m4pro.metal` has 48 GiB and therefore uses the below-64-GiB
low-memory profile; record that profile and do not compare its absolute timing
with another host or profile. See the current
[EC2 Mac instance specifications](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-mac-instances.html).
All M4 measurements remain directional because the official authority is M5
Max.

During host provisioning, run `./setup.sh` so the pinned `macmon` reader is
present. Before assigning work, verify that GPU temperature telemetry is
plausible and responsive, no other model workload is resident, and
`tools/fan-control.sh status` is understood (`auto`, `manual`, or unsupported
`none`). Quarantine or reschedule a host whose telemetry is frozen or
implausible, or whose quiescent GPU repeatedly cannot reach the 40C gate.
Never bypass the gate to manufacture a timing result.
The local gate retries two transient unusable or at/below-5C samples, then
fails closed; a campaign controller must stop the cohort on that failure so a
broken host sensor cannot contaminate later arms.
After installing each exact experiment snapshot and before loading the model,
audited automation should collect a new persistent five-sample `macmon pipe`
stream (not five fresh one-shot processes), retain the raw JSON, and require
strictly increasing timestamps, plausible CPU/GPU values, and at least two
distinct GPU temperatures. This catches a frozen-but-plausible reading that a
threshold-only gate cannot identify. Bind the receipt to the exact
rank/submission/commit/attempt, cap the handoff to attempt-process launch, reject receipt
reuse, and bind the declared fan policy plus fan status before and after the arm
to the result. The pre-model receipt does not replace the gates immediately
before prefill and decode: strict phase gates should each confirm a fresh
responsive persistent stream before accepting `<=40C`. Bound every real
telemetry-reader invocation with a wall-clock deadline and reap its process
group on timeout or interruption; a dead sensor command must fail the arm, not
hang the campaign.

Long-running campaign wrappers must give the benchmark an isolated process
group and forward HUP, INT, QUIT, and TERM to that whole group, with bounded
TERM-to-KILL escalation. Test cancellation and normal-exit orphan paths with
model-free child-process fixtures. A stopped terminal or agent must not leave
a model-holding worker orphaned in the background.

Manual fan control is optional and capability-verified, not an EC2 Mac
assumption. AWS documents bare-metal Mac hosts and administrator access, but
does not document SMC fan writes as a supported guest interface. Installing a
fan utility is therefore insufficient: an operator must verify that
`tools/fan-control.sh boost` raises observed fan RPM, its SMC read-back passes,
and `tools/fan-control.sh normal` restores automatic control on that exact
instance family and macOS build. If any check fails, leave fan control alone
and cool by idling or rescheduling the host.

A verified boost is an explicit operator action, never an experiment arm. The
repository helper defaults every fan to 70%, refuses to overwrite another
manual controller, and verifies each write. After a verified 70% trial cannot
meet the gate, an operator may explicitly set `MLXFAST_FAN_BOOST_PERCENT=80`
for a bounded campaign; all other values are refused. Apply one recorded
policy to the whole baseline/candidate campaign. Never pipe or store a sudo
password, grant students broad SMC-write privileges, exceed 80%, write
undocumented SMC keys, or ignore failed read-back. Restore automatic control
immediately after an 80% campaign because it adds noise and fan wear.
Changing from manual 70/80% to automatic control (or the reverse) invalidates
the prior timing comparator: rerun the unchanged baseline under the new policy
before timing any candidate.

Unattended jobs have no interactive terminal and cannot accept
`benchmark.sh`'s optional fan prompt. Set `MLXFAST_LOCAL_FAN_PROMPT=0`
explicitly in audited automation; the gate still waits and fails closed. The
benchmark's optional offer also requires a terminal stderr and its process
group to own the foreground tty before prompting, because merely opening
`/dev/tty` in a background job can suspend it on `SIGTTIN`. Direct
`tools/fan-control.sh` calls still require an attended operator; the helper can
invoke `sudo` and has no unattended authorization path. A boost applied before
a run is external state, so the benchmark will not restore it. The
operator/controller needs the out-of-band `./benchmark.sh --fan-speed-normal`
cleanup and `auto` verification only on a host where it applied a manual
boost. A host reporting unsupported `none` has no override to restore;
`macmon` and the `<=40C` gate remain mandatory.
Record the host identifier, chip, memory, macOS build, initial temperature,
fan capability/action, cool-down duration, and accepted telemetry with every
timed result.

## Sources Of Truth

Read these before proposing or implementing an experiment:

1. `~/AGENTS.md` — from the competition organisers: complete working contract
   and agent-specific operational guidance. Note this is operational and not
   our main competition strategy document.
2. `~/TASK.md` — from the competition organisers - model, scoring, correctness, and serial-track rules.
3. `~/README.md` — from the competition organisers — setup, architecture, local workflow, and kernel build forms.
4. `~/benchmark.json` — authoritative `editablePaths`, commands, and score
   contract.
5. `~/docs/benchmark-window-freeze.md` — exact charged work and serial decode
   integrity boundary.

When prose and executable configuration disagree, stop and resolve the
conflict. `benchmark.json` is authoritative for the submission surface, and
the trusted harness plus frozen-window tests are authoritative for scored
behavior.

## Model And Scored Path

Laguna XS 2.1 is a fine-grained mixture-of-experts transformer:

- 256 routed experts plus one shared expert in each sparse layer.
- 8 routed experts per token with per-head gating.
- Layer 0 uses a dense MLP; later layers use sparse MoE blocks.
- Routed and shared expert projections use group-16 NVFP4.
- The source checkpoint stores attention projections, embeddings, routers, the
  layer-0 dense MLP, and the untied output head in BF16. `TASK.md` defines the
  narrow attention-quantization envelope allowed for submissions.
- All layers use GQA with 8 KV heads and head dimension 128.
- Three 512-token sliding-window layers alternate with one full-attention layer.
- Full-attention layers use YaRN partial-rotary RoPE; sliding layers use plain
  RoPE.

### Attention quantization contract

The live precision allowance is defined only in `TASK.md`. Read that section
before changing any BF16 attention projection; do not infer permission for an
unlisted tensor or weaken trusted validation. The exact frontier and harness
refresh workflow is in [`experiment-runbook.md`](experiment-runbook.md).

The scored forward pass is implemented by
`Sources/MLXFastModel/LagunaRuntimeModel.swift` and its runtime helpers.
`Vendor/mlx-swift-lm/Libraries/MLXLLM/Models/Laguna.swift` is primarily an
upstream-equivalence oracle; changing it alone does not speed up the scored
path.

All text-tower tensors are loaded once and remain in unified memory for the
process lifetime. There is no weight streaming, expert cache, or scored-path
disk I/O. Optimize compute, memory traffic within unified memory, scheduling,
and layout—not storage bandwidth or a nonexistent streaming path.

## Editable Surface

The submitted candidate may modify only paths listed under `editablePaths` in
`benchmark.json`. The current surface has four groups:

- `Sources/MLXFastModel/` — primary scored runtime, weight loading, attention,
  MoE, caches, and decode.
- `Sources/MLXFastTransform/` — offline transformation and runtime metadata.
- The individually listed Laguna and `MLXLMCommon` files under
  `Vendor/mlx-swift-lm/`.
- The individually listed MLX Metal dispatch and kernel files under
  `Vendor/mlx-swift/`.

Supporting tests and documentation may accompany a research PR when they make
the experiment easier to validate or understand. They are not packaged by
`mlxfast submit`, cannot weaken or replace trusted gates, and cannot be
necessary for the candidate to work. The performance and correctness claim
must stand on the submitted `editablePaths` diff alone.

Do not modify the trusted harness, CLI, workflows, benchmark definition,
dependency graph, fixtures, goldens, reference checkpoint, generated weights,
or score files to make an experiment pass. In particular, the submitted
candidate must not depend on changes to:

- `Sources/MLXFastCore/`
- `Sources/MLXFastCLI/`
- `Sources/MLXFastTrustedHarness/`
- `Sources/MLXFastHarness/`
- `Sources/MLXFastRuntimeWorkerCLI/`
- `Package.swift` or `Package.resolved`
- `.github/`, `benchmark.json`, `benchmark.sh`, or `setup.sh`
- `weights/`, `reference_weights/`, `correctness_prompts/`, or any
  `score*.json`

`program.md` and role instructions are coordination files, not submission
code, do not update them as part of your experiments unless explicitly instructed to do so by a human researcher.

Before reporting, separate submitted candidate changes from supporting
research-only changes and inspect both against the recorded `BASE_SHA`. Any
runtime or model source outside `editablePaths` invalidates the candidate.
Never restore or overwrite unrelated user changes. Exact inspection commands
are in [`experiment-runbook.md`](experiment-runbook.md).

## Kernel Build Contract

Know which file becomes the running kernel:

- Kernel families with `Vendor/mlx-swift/Source/Cmlx/mlx-generated/*.cpp`
  twins are compiled at runtime from the source strings in those generated C++
  files. The `.cpp` twin is runtime-effective. Keep it and the readable
  `.metal`/`.h` source in sync.
- RoPE, RMSNorm, the SDPA vector kernel, and `arg_reduce` are ahead-of-time
  kernels in `mlx.metallib`. Rebuild with
  `tools/build-mlx-metallib.sh` after changing them.
- `_nax` kernels are the M5-generation variants used by the official runner.
  Tune and validate them as well as the plain variants.
- `./benchmark.sh --local-iterate` rebuilds the trusted and worker binaries when
  inputs change.
- A bare `swift build -c release` is insufficient for the scored worker because
  it writes a different scratch path. Direct Swift builds and tests must always
  use `--force-resolved-versions`.

Every kernel experiment needs an explicit numerical validity gate. Reduction
order changes can flip a near-tie argmax after errors compound across layers,
even when a microbenchmark looks numerically close.

## Setup And Baseline

A clean research round starts with normal `mlxfast sync`, which selects the
best promoted submission. `mlxfast sync --harness-only` is not a frontier sync:
it preserves editable paths and is reserved for refreshing trusted base and
harness files around work already in progress. Never infer the frontier from a
remote name alone.

Record the selected frontier commit as an immutable `BASE_SHA`. Finish and
report the arm against that SHA even if the frontier moves while it runs; then
sync, reapply, and remeasure a promising candidate before promotion. Do not
compare results across a changed base commit, model cache, toolchain, host
profile, or thermal policy.

Setup is once per host or whenever the toolchain/checkpoint state changes. Use
the exact checkpoint and a documented cache path; never substitute another
model revision. Run one causal experiment at a time, with whatever coupled
editable-path changes are necessary to test it, and compare unchanged baseline
and candidate on the same host under the same thermal gate.

See [`experiment-runbook.md`](experiment-runbook.md) for the frontier, setup,
baseline/candidate, metric extraction, and pre-promotion commands.

## Experiment Ladder

Use the cheapest reliable gate that can answer the current question.

### 1. Static and build checks

- Confirm the hypothesis attacks the scored runtime.
- Confirm every submitted candidate file is in `editablePaths`; identify any
  supporting tests or docs separately.
- For a kernel edit, confirm the runtime-effective JIT/AOT source and `_nax`
  variant are covered.
- Review the diff for prompt-, token-, fixture-, or benchmark-specific logic.
- Run targeted unit tests or compile checks.

### 2. Microbenchmark or focused instrumentation

Use this only when it measures a named cost and does not change the scored
harness. Prefer existing profiling surfaces. Temporary local instrumentation
must be removed before the candidate benchmark and must not be reported as an
end-to-end win.

### 3. Fast local screen

Run the standard tests and local-iterate path from the runbook. This is the
normal screen: the public 64-step correctness tripwire plus a short local timing
pass. When live MLX runtime behavior changes and the host supports it, include
the opt-in MLX runtime tests.

### 4. Confirmation

For a promising candidate:

- Repeat baseline/candidate measurement when the apparent gain is near the
  host's noise floor.
- Confirm both prefill and decode; never report the aggregate alone.
- Confirm memory remains viable under the applicable startup profile.
- Run the longer local-submit path from the runbook.

### 5. Official promotion

Only the advisor or human operator may decide to submit a merged candidate with
the Yukon `mlxfast` CLI. Students can dispatch official submissions, but they must ask the Advisor agent to do so first.
The Student should ensure all changes for the submission have been committed.
The advisor will comment in the PR with a confirmation that the submission is ready to be dispatched for official evaluation.

Official capacity is one serial M5 queue, and the hidden run is expensive.
Queue times have been known to be in the range of 6-12 hours so it is important 
that this does not slow down our research process - while waiting for the official result, students may continue independent local
experiments, but they must record which baseline commit each result used. If the
queued candidate is accepted, rebase or restart subsequent work on the new
frontier and rebaseline before trusting its timings. Do not dispatch duplicate
ranked submissions in an attempt to get parallel capacity.

Before promotion, follow the runbook's harness refresh and pre-submit sequence,
confirm a clean candidate diff limited to `editablePaths`, and summarize why
the local evidence is likely to transfer to M5.

## Correctness And Validity

The official gate includes:

- the public 64-step teacher-forced drift tripwire,
- hidden full-length teacher-forced cases,
- hidden anchor, free-run, and behavior gates,
- GPQA TTFT and semantic GPQA evaluation,
- token validation inside the timed phase.

These gate categories and their mechanics are documented in `TASK.md`,
`README.md`, and the trusted harness. Their actual private prompts, accepted
token sequences, reference answers, and semantic-judge transcripts are not in
the repository. Do not claim local coverage of them or try to reconstruct them.
The checked-in public fixture is a drift tripwire, not a complete proxy for the
hidden distribution.

Checked-in fixtures were generated on M5. A correct baseline can encounter a
near-tie argmax divergence on a different Apple generation. When that happens:

1. Reproduce the same failure on unchanged current `main`.
2. Record the baseline and candidate failing token positions.
3. Use `MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT=1` only to obtain timing evidence if
   the unchanged baseline fails identically.
4. Keep `passed_correctness: false` visible in the result.
5. Never use the override when baseline `main` passes or when the candidate
   introduces a new divergence.

The official M5 result remains authoritative.

Correctness recovery has a cost. If a safety path, fallback, or deterministic
reduction restores token identity but removes the speedup, the optimization
failed on end-to-end economics.

### Risk-based local quality evidence

Use local-iterate as the normal screen and local-submit for promotion
candidates. Add the opt-in upstream-equivalence test or the advisory quality
panel when a candidate changes numerical behavior or representation—for
example quantization, pruning, reduction order, activation math,
dispatch/layout contracts, or output-head behavior—or whenever an observed
mismatch needs diagnosis. They are not routine requirements for a scheduling
or tiling change whose outputs are already shown equivalent.

When one of these stronger checks is required, only its documented passing
verdict permits promotion. Use a matched, same-host baseline and never run it
beside another model-holding process. See
[`quality-evaluation.md`](quality-evaluation.md) for triggers, commands,
thresholds, exit semantics, and the upstream-equivalence diagnostic. These
checks are advisory and cannot relax exact-token correctness or replace the
hidden M5 gates.

## Serial Non-Speculative Integrity Boundary

This is a serial, non-speculative track.

Each model invocation may compute logits and KV rows only for tokens supplied
in that invocation. It must advance logical and physical KV position by exactly
the supplied input length. A one-token decode request advances exactly one
position and may not leave a pending future token, future logits, or future KV
state.

The following are prohibited even if generic, production-useful, or bit-exact:

- speculative decoding, drafters, MTP, or same-target lookahead,
- prompt-lookup, n-gram, suffix, or token-history drafting,
- multi-row target verification for a one-token request,
- cross-request future-logit or future-KV buffers,
- deferred cache rows, rollback, recommit, or discard markers,
- initialization or pre-hello warmup of any excluded future-token path.

Allowed examples include:

- ordinary within-request KV reuse,
- current-token-only decode,
- input-independent weight, dequantization, kernel, mask, and RoPE caches,
- multi-row kernels during prefill when every row corresponds to a supplied
  token.

Do not add caches keyed on whole prompts or request token sequences whose only
useful hit would come from benchmark repetition. The benchmark measures
single-pass inference. Input-independent caches and legitimate within-request
state are the correct reuse boundary.

## Benchmark Integrity

Abide by the spirit of the competition rules — no egregious cheating or
rule-breaking.

- hardcode public or hidden prompts, token IDs, expected continuations, or GPQA
  answers,
- specialize behavior for fixture hashes, request lengths, timing mode,
  correctness mode, or process role,
- change or bypass the trusted timing/correctness harness,
- inspect, exfiltrate, regenerate, or infer hidden benchmark artifacts,
- use network access or filesystem side channels from submitted runtime code,
- skip required computation, move charged work outside the timer, or report
  worker-provided timing as the trusted score,
- change the frozen model checkpoint, tokenizer, data, score formula, or
  request protocol,
- exploit repeated whole-prompt work, because no such repetition is part of
  the production contract,
- optimize only the public prompt or only the local machine,
- disable the sandbox, thermal gate, transform verification, or memory guard
  and present the result as rankable evidence.

Optimizations must be prompt-independent and model-general for Laguna.

## Research Autonomy

The advisor assigns a bounded research question or cost center plus the hard
validity and measurement contract; it does not prescribe the implementation.
Within that scope, the student owns source inspection, profiling, hypothesis
refinement, implementation shape, and the cheapest sufficient validation.

A student may narrow an arm, stop when evidence falsifies it, or return an
analysis-only or measurement-only result. It does not owe the program a patch.
Record higher-leverage adjacent ideas as follow-ups instead of silently
broadening scope; a materially different causal mechanism becomes a new arm.

## Research Method

The transferable lesson from the Senpai inference guide is a disciplined loop:

1. Define the exact validity contract.
2. Reproduce the current frontier on the measured path.
3. Decompose latency into named costs.
4. Estimate the plausible gain and noise threshold when evidence permits;
   otherwise make bounding the target cost the first result.
5. Test one causal question at a time.
6. Reject quickly on correctness, protocol, feasibility, or end-to-end speed.
7. Compose only individually measured winners.
8. Preserve negative results so later agents do not repeat them.

Every experiment PR should state:

```text
Question or hypothesis:
  What causal mechanism or uncertainty does this arm test?

Target cost and evidence:
  Which measured budget line matters, and what currently supports that belief?

Expected signal:
  Give a grounded numerical range when possible. Otherwise state what first
  measurement will bound the effect.

Validity gate:
  Which exact-token, serial-protocol, build, and memory checks must pass?

Measurement plan:
  What is the cheapest reliable sequence of checks?

Stop rule:
  What evidence will promote, narrow, revise, or end the arm?
```

Broad directions are acceptable for discovery, but must become falsifiable
before implementation. Prefer an evidence-backed question such as whether a
specific materialization exists on one-token decode; do not invent a numerical
gain before measuring the cost.

Research commands, including literature search, are in
[`experiment-runbook.md`](experiment-runbook.md).

## Non-Prescriptive Research Map

Choose work from fresh profiles, current promoted diffs, prior results, and
source inspection—not from a fixed backlog. Plausible cost centers include
NVFP4 matmul and MoE dispatch, attention and RoPE, KV-cache movement, MLX graph
and launch scheduling, weight/transform layout, and the output head. These are
orientation points, not quotas or an ordering. `TASK.md` remains authoritative
for precision allowances, and every idea must prove that it affects the exact
scored shapes and path.

## Low-Value Or Invalid Directions

Do not spend experiments on:

- disk I/O, expert streaming, or expert-cache hit rates; the model is
  RAM-resident and the bandwidth diagnostic is always zero,
- speculative decoding or any future-token method; this track forbids it,
- CUDA, vLLM, Python-runtime, multi-GPU, or distributed-serving changes,
- changing only the upstream `Laguna.swift` oracle when the scored runtime does
  not call the changed code,
- kernel families or model paths Laguna never dispatches,
- warmup tricks, score-path detection, or benchmark-only caching,
- projected composition of several unmeasured changes,
- broad numerical reassociation without exact-token evidence,
- tiny components whose maximum possible end-to-end gain is below timing noise.

## Measurement And Decision Rules

Use seconds per token as the physical metric:

- Lower `decode_seconds_per_token` is better.
- Lower `prefill_seconds_per_token` is better.
- Higher aggregate `score` is better only when both component floors and
  correctness pass.

For a same-host baseline `B` and candidate `C`, report:

```text
decode_gain  = B.decode_seconds_per_token / C.decode_seconds_per_token
prefill_gain = B.prefill_seconds_per_token / C.prefill_seconds_per_token
paired_estimate = decode_gain^0.75 * prefill_gain^0.25
```

This local paired estimate is for research comparison only; it is not the
official score.

Decision guidance:

- **Invalid candidate:** correctness, protocol, memory, build, or submitted-
  surface failure. Never promote it, but do not call the underlying hypothesis
  dead while a plausible compliant implementation remains.
- **Dead hypothesis:** profiling disproves the target cost, its plausible
  end-to-end gain is below noise or implementation cost, or a valid
  implementation produces no repeatable gain.
- **Ambiguous:** gain near noise, machine-generation-specific correctness
  uncertainty, unstable prefill/decode tradeoff, or incomplete transfer
  evidence. Run only the smallest additional test capable of changing the
  decision; otherwise close with the uncertainty recorded.
- **Green:** correctness and protocol pass, a repeatable same-host end-to-end
  gain, no component-floor risk, and a clean candidate limited to
  `editablePaths`.

A microbenchmark win without an end-to-end win is evidence, not a promotable
candidate. An aggregate gain that materially regresses one axis or threatens
the acceptance band is not a clean winner.

## Results Contract

This repository does not use W&B for benchmark metrics. Do not add W&B logging
to the submitted runtime or trusted harness. Canonical evidence is the ignored
score JSON, exact command output, commits, and the PR result comment.

At terminal reporting time, load and follow
[`result-template.md`](result-template.md). It owns the machine-readable
`SENPAI-RESULT` marker, required reproducibility fields, comparison table, and
negative-result taxonomy. Do not carry that reporting checklist through the
active research loop, and never invent a score when no valid timing exists.

## Advisor Guidance

Allocate arms according to measured bottlenecks, plausible impact, confidence,
uncertainty reduction, and experiment cost. Diversify when evidence is weak or
parallel capacity makes independent information gathering useful; category
balance is not itself a goal.

- Keep one causal question per PR.
- Put the baseline commit, baseline metrics, expected signal, files, validation
  ladder, and stop rule in the PR body.
- Prefer prompt-invariant, by-construction-safe changes.
- Bound risky kernel work before assigning a large implementation.
- Close dead hypotheses once evidence clears the stop rule; distinguish them
  from repairable invalid candidates.
- Search merged/closed PRs before repeating an idea.
- Merge only measured winners based on the current advisor frontier.
- Rebaseline after every merged winner before assigning comparisons against the
  new frontier.
- Do not merge several individually unmeasured optimizations and assume their
  gains add.
- Reserve `--local-submit` and official queue time for candidates that survive
  the fast screen.
- Treat official M5 feedback as new evidence. Record it before the next round.
- Chunk candidates that appear to exceed the single-submission acceptance band
  only along natural, independently valid improvements.

The strongest baseline is already highly tuned. Favor precise, mechanism-backed
experiments over broad refactors. Simpler code is preferred when performance
and correctness are equal.

## Final note

Research is coordinated through Senpai's GitHub advisor/student PR workflow.
The advisor routes bounded questions or cost centers and owns shared-frontier
and official-queue decisions. Students own the investigation within that scope,
including profiling, narrowing, implementation, cheapest sufficient
validation, early termination, and evidence-backed negative results. Human
issues may override or stop work.

Any `instructions/prompt-advisor.md` and `instructions/prompt-student.md` role
overlays must point back to this program and must not weaken the repository
contract.

The goal of this competition is inference speedup, and speedup should also be
the mantra when running experiments and making research decisions. Move
quickly, efficiently, and effectively through the research program, balancing
speed and quality. Scientific discovery and testing of inspired insights should
drive the program—not a wall of verification that slows iteration without
changing decisions.
