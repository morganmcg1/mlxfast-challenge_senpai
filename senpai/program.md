# Poolside Laguna XS 2.1 MLX Inference Autoresearch

This repository is the research target for optimizing the text tower of
Poolside Laguna XS 2.1 NVFP4 on Apple Silicon. The ranked track is
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

Maximize the official paired score:

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
- Score weights: 75% decode and 25% prefill.

The official M5 run also enforces a two-sided acceptance band against the
pinned calibration reference:

```text
decode_speedup:  [0.980, 1.053]
prefill_speedup: [0.952, 1.053]
```

This caps a single ranked submission's apparent gain at about 5%. If a local
candidate is more than about 5% faster, split it into independently measurable
submissions and validate each step. Local modes warn about the fast edge but do
not enforce the band.

Validation numbers are steering evidence. Only the official paired M5 result
is a ranking claim.

The official benchmark compares a candidate with the challenge baseline
currently pinned on the M5 runner. When a validated submission beats the
leaderboard record, its commit is accepted as the new baseline that subsequent
work must beat. Always sync the latest `main`, rerun a same-host local baseline,
and treat results from an older frontier as historical evidence only.

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
- Do not use an automated sudo prompt or change fan controls as part of an
  experiment. Host operators own fan policy.

### Pre-NAX MoE output-layout compatibility

Commit `2225854` fixed a host-dependent correctness bug in the fused sorted
prefill MoE gate/up path. The operation has two physical output contracts:

- The NAX expert-aligned kernel applies rounded-BF16 SwiGLU and packs the
  512-wide activation into the first half of a nominal 1024-wide allocation.
- The generic pre-NAX kernel returns the full 1024-wide, 32-row
  gate/up-interleaved projection. It must be deinterleaved and evaluated as
  `SiLU(gate) * up` by `lagunaInterleavedSwiGLU`.

Before the fix, Swift selected the packed 512-wide interpretation from the
default-on `DARKBLOOM_EXPERT_ALIGNED_GATHER` flag alone. MLX independently
refused the NAX kernel on unsupported hardware or OS versions. On a pre-NAX
GPU, Swift therefore sliced the first half of a generic 1024-wide result as if
it were already activated, corrupting sparse-MoE prefill outputs and logits.
The same mismatch was possible when `DARKBLOOM_STAGE_BM128` selected a tiling
other than packed-compatible variant `4`.

The fixed Swift predicate mirrors backend dispatch. The packed interpretation
is enabled only when all of these are true:

- `DARKBLOOM_EXPERT_ALIGNED_GATHER` is not `0`;
- macOS is 26.2 or newer;
- the Metal architecture is generation 17 or newer for an `s` suffix, or
  generation 18 or newer for a `p` suffix; and
- `DARKBLOOM_STAGE_BM128` is unset, empty, or `4`.

Otherwise the runtime uses the generic 1024-wide reconstruction path.
`DARKBLOOM_EXPERT_ALIGNED_GATHER=0` is also a useful diagnostic ablation, but
the fixed runtime does not require it on pre-NAX hosts.

The Swift predicate and view selection are in
`Sources/MLXFastModel/LagunaRuntimeModel.swift`; the backend capability and
kernel selection are in the vendored MLX `device.cpp`, `quantized.cpp`, and
`fp_quantized_nax.h` files.

The development machine that exposed the bug has these identifying specs:

| Field | Value | Relevance |
| --- | --- | --- |
| Mac | MacBook Pro `Mac16,6` | Reproduction host |
| SoC / GPU | Apple M4 Max, 40 GPU cores | Hardware family |
| Metal architecture | `applegpu_g16s` | Causal: generation 16 is pre-NAX |
| Unified memory | 128 GB | Reproduction context, not the predicate |
| OS | macOS 26.5.2 (`25F84`), Darwin 25.5.0 | OS passes the 26.2 requirement |
| Toolchain | Xcode 26.6 (`17F113`), Swift 6.3.3, arm64 | Reproduction context |
| Relevant overrides | all three variables above unset | Exercised default dispatch |

Do not classify every M4 or M5 by marketing name alone. Inspect the Metal
architecture and relevant overrides:

```bash
system_profiler SPHardwareDataType SPSoftwareDataType \
  -detailLevel mini |
  rg 'Model Name|Model Identifier|Chip:|Total Number of Cores|Memory:|System Version|Kernel Version'

swift -module-cache-path /tmp/mlxfast-swift-module-cache -e \
  'import Metal; if let d = MTLCreateSystemDefaultDevice() { print(d.name); if #available(macOS 14.0, *) { print(d.architecture.name) } }'

env | rg \
  '^(MLX_METAL_GPU_ARCH|DARKBLOOM_EXPERT_ALIGNED_GATHER|DARKBLOOM_STAGE_BM128)='
```

In this vendored MLX build, `applegpu_g16s` is pre-NAX; an `s` architecture
needs generation 17 or later, while a `p` architecture needs generation 18 or
later, and both still require macOS 26.2 or later. A forced
`MLX_METAL_GPU_ARCH` can change the reported dispatch decision and must not
misrepresent the host.

This is an optimization invariant: kernel dispatch and the Swift-side
shape/layout interpretation must share the same complete predicate. Any change
to NAX availability, MoE tiling, packing, or output strides must update both
sides and extend
`Tests/MLXFastTests/LagunaCorrectnessTests.swift`. Rebaseline quality after
changing GPU generation, macOS, these environment variables, or the dispatch
contract.

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

## Sources Of Truth

Read these before proposing or implementing an experiment:

1. `AGENTS.md` — complete working contract and agent-specific operational
   guidance.
2. `TASK.md` — model, scoring, correctness, and serial-track rules.
3. `README.md` — setup, architecture, local workflow, and kernel build forms.
4. `benchmark.json` — authoritative `editablePaths`, commands, and score
   contract.
5. `docs/benchmark-window-freeze.md` — exact charged work and serial decode
   integrity boundary.
6. Recent Git history, merged experiment PRs, and their result comments —
   current frontier and known dead ends.

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
  layer-0 dense MLP, and the untied output head in BF16. The accepted
  submission envelope permits the five attention projections listed below to
  be re-quantized to group-32 affine INT8.
- All layers use GQA with 8 KV heads and head dimension 128.
- Three 512-token sliding-window layers alternate with one full-attention layer.
- Full-attention layers use YaRN partial-rotary RoPE; sliding layers use plain
  RoPE.

### Accepted attention quantization envelope

The live challenge contract permits submissions to re-quantize these attention
projections to **group-32 affine INT8**:

- query projection (`q_proj`),
- key projection (`k_proj`),
- value projection (`v_proj`),
- output projection (`o_proj`),
- per-head gate projection (`g_proj`).

`g_proj` is the newest addition to the established Q/K/V/O envelope and applies
to all new submissions. This is a narrowly scoped representation allowance,
not permission to change the model's overall precision or behavior. The source
checkpoint remains authoritative, exact-token and hidden behavior gates still
apply, and no other BF16 tensor is admitted by this announcement. In
particular, do not infer permission to re-quantize embeddings, Q/K norms,
routers, the layer-0 dense MLP, the untied output head, or other unlisted
projections.

The local trusted harness must understand the expanded envelope. Before
benchmarking or submitting against this rule, refresh it with:

```bash
mlxfast sync --harness-only
```

Do not hand-edit trusted harness validation to admit the new layout. If local
docs or validation still require BF16 `g_proj`, the checkout is stale; sync the
harness and latest `main` before interpreting a failure.

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

Experiment PRs may modify only paths listed under `editablePaths` in
`benchmark.json`. The current surface has four groups:

- `Sources/MLXFastModel/` — primary scored runtime, weight loading, attention,
  MoE, caches, and decode.
- `Sources/MLXFastTransform/` — offline transformation and runtime metadata.
- The individually listed Laguna and `MLXLMCommon` files under
  `Vendor/mlx-swift-lm/`.
- The individually listed MLX Metal dispatch and kernel files under
  `Vendor/mlx-swift/`.

Do not modify the trusted harness, CLI, workflows, benchmark definition, tests,
docs, dependency graph, fixtures, goldens, reference checkpoint, generated
weights, or score files to make an experiment pass. In particular, normal
experiment PRs must not modify:

- `Sources/MLXFastCore/`
- `Sources/MLXFastCLI/`
- `Sources/MLXFastTrustedHarness/`
- `Sources/MLXFastHarness/`
- `Sources/MLXFastRuntimeWorkerCLI/`
- `Package.swift` or `Package.resolved`
- `.github/`, `benchmark.json`, `benchmark.sh`, `setup.sh`, tests, or docs
- `weights/`, `reference_weights/`, `correctness_prompts/`, or any
  `score*.json`

`program.md` and role instructions are coordination files, not submission
code. Update them only in an explicit research-infrastructure task, never as
part of a performance experiment.

Before reporting a result, inspect the diff:

```bash
git status --short
git diff --name-only "$BASE_SHA"
```

Here `BASE_SHA` is the assigned experiment's recorded baseline commit.
Any source change outside `benchmark.json`'s `editablePaths` invalidates a
normal experiment result. Never restore or overwrite unrelated user changes.

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

Setup is once per host or whenever the toolchain/checkpoint state changes:

```bash
mlxfast sync --harness-only
./setup.sh
```

The first command refreshes the trusted harness and does not authorize manual
harness changes. Setup then builds the Swift tools and Metal library and
downloads or verifies the pinned checkpoint. The host needs at least 40 GiB of
free disk for the default setup. Use a pre-provisioned exact checkpoint or
documented cache path when appropriate; never substitute a different model
revision.

Every research round must begin from the latest advisor frontier, itself based
on current `origin/main`. Do not compare with a score from an older commit,
branch, model cache, toolchain, or thermal state.

For each assigned PR:

1. Record the baseline commit before editing.
2. On the same host, run the unchanged branch through local iterate.
3. Save the ignored baseline score artifact.
4. Implement exactly one hypothesis.
5. Run the candidate on the same host under the same automatic thermal gate.

Example:

```bash
BASE_SHA="$(git rev-parse HEAD)"
./benchmark.sh --local-iterate
cp score.local-iterate.json score.local-iterate.baseline.json

# Implement the assigned hypothesis, then:
swift test --force-resolved-versions
./benchmark.sh --local-iterate
cp score.local-iterate.json score.local-iterate.candidate.json
```

`score.local-*.json`, `score*.baseline.json`, and `score.json` are ignored
artifacts. Never commit them.

Extract the comparison with:

```bash
jq '{
  score,
  passed,
  runtime: .metrics.runtime,
  passed_correctness: .metrics.passed_correctness,
  decode_seconds_per_token: .metrics.decode_seconds_per_token,
  prefill_seconds_per_token: .metrics.prefill_seconds_per_token,
  decode_speedup: .metrics.decode_speedup,
  prefill_speedup: .metrics.prefill_speedup,
  peak_ram_gb: .metrics.peak_ram_gb,
  error: .metrics.error
}' score.local-iterate.baseline.json score.local-iterate.candidate.json
```

Local `score` and speedups are estimates against cached M5 calibration
constants, not a same-session official pair. The most useful local comparison
is the candidate's seconds/token against the freshly measured baseline's
seconds/token on the same Mac.

## Experiment Ladder

Use the cheapest reliable gate that can answer the current question.

### 1. Static and build checks

- Confirm the hypothesis attacks the scored runtime.
- Confirm every proposed file is in `editablePaths`.
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

```bash
swift test --force-resolved-versions
./benchmark.sh --local-iterate
```

This runs the public 64-step correctness tripwire plus a short local timing
pass. It is the normal screening loop.

If the change touches live MLX runtime behavior and the host supports it, also
run:

```bash
MLXFAST_RUN_MLX_RUNTIME_TESTS=1 swift test --force-resolved-versions
```

### 4. Confirmation

For a promising candidate:

- Repeat baseline/candidate measurement when the apparent gain is near the
  host's noise floor.
- Confirm both prefill and decode; never report the aggregate alone.
- Confirm memory remains viable under the applicable startup profile.
- Run the longer pre-submit path:

```bash
./benchmark.sh --local-submit
```

This writes `score.json` and exercises a longer local decode window.

### 5. Official promotion

Only the advisor or human operator may decide to submit a merged candidate with
the Yukon `mlxfast` CLI. Students must not dispatch official submissions.
Official capacity is one serial M5 queue, and the hidden run is expensive.
While an official result is queued, students may continue independent local
experiments, but they must record which baseline commit each result used. If the
queued candidate is accepted, rebase or restart subsequent work on the new
frontier and rebaseline before trusting its timings. Do not dispatch duplicate
ranked submissions in an attempt to get parallel capacity.

Before promotion, require:

```bash
mlxfast sync --harness-only
./setup.sh
swift test --force-resolved-versions
./benchmark.sh --local-submit
```

Then confirm a clean, editable-surface-only diff and summarize why the local
evidence is likely to transfer to M5.

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

Do not confuse ordinary cross-generation near-tie drift with gross inference
corruption. The pre-NAX layout mismatch above produced PPL `262.0863`,
repetitive or unfinished generations, and zero correct answers across the
small downstream panel. The original quick evaluator also capped every
full-head answer at 256 tokens, which could stop a reasoning trace before its
extractable final answer. That compounded the symptom but could not repair the
logits. After the dispatch/layout fix, the same host reached PPL `13.9549` and
nonzero downstream accuracy. The current quality runner gives normal full-head
questions 1,024 tokens and AIME 2,048 tokens, and invalidates a full-head run
if an answer reaches its cap; its separate ranked-behavior arm intentionally
retains the challenge's 128-token prefix contract.

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

### Existing local quality evidence

Use the repository's existing evidence ladder before proposing new evaluation
infrastructure:

- `./benchmark.sh --local-iterate` checks the public 64-step teacher-forced
  tripwire and produces a short directional timing estimate.
- `./benchmark.sh --local-submit` uses the longer checked-in public fixture and
  is the stronger participant-facing local check.
- `correctness-trace` can diagnose a known mismatch without weakening the gate.
- The opt-in M5 upstream-equivalence test compares the scored runtime with the
  vendored `MLXLLM.LagunaModel` for one 512-token prefill and eight serial
  teacher-forced decode steps. It is an expensive diagnostic for risky math or
  dispatch changes, not a replacement for the official gate:

```bash
MLXFAST_RUN_LAGUNA_UPSTREAM_EQUIVALENCE=1 \
MLXFAST_LAGUNA_EQUIVALENCE_WEIGHTS_PATH=weights \
swift test --force-resolved-versions \
  --filter lagunaRuntimeMatchesVendoredUpstreamOnM5WhenEnabled
```

### Autoresearch quality checkpoint

One-time setup from the repository root:

```bash
./setup.sh
brew install uv  # skip when uv --version already succeeds
```

`setup.sh` downloads the pinned 21.6 GB checkpoint. `senpai/quality-eval`
creates its locked Python environment and fetches the public benchmark data
automatically; no dataset path or Hugging Face token is needed. Internet access
is required, including live Hugging Face access for AIME and GSM8K.

Before modifying untouched `main`, create and preserve separate matched
baselines for the periodic 13-minute core panel and the full quick pre-submit
panel:

```bash
./senpai/quality-eval run . \
  --profile quick \
  --suite ppl --suite mmlu_pro --suite aime --suite gsm8k \
  --change-label untouched-baseline-core \
  --output quality-results/baseline-quick-core

./senpai/quality-eval run . \
  --profile quick \
  --change-label untouched-baseline-full \
  --output quality-results/baseline-quick
```

Run the core gate periodically for promising changes; replace `my-change-001`
with a unique experiment ID because output directories are immutable:

```bash
QUALITY_RUN_ID=my-change-001
./senpai/quality-eval run . \
  --profile quick \
  --suite ppl --suite mmlu_pro --suite aime --suite gsm8k \
  --change-label "${QUALITY_RUN_ID}" \
  --baseline quality-results/baseline-quick-core \
  --output "quality-results/candidate-quick-core-${QUALITY_RUN_ID}"
```

Run the full quick panel before submission:

```bash
QUALITY_RUN_ID=my-change-001
./senpai/quality-eval run . \
  --profile quick \
  --change-label "${QUALITY_RUN_ID}" \
  --baseline quality-results/baseline-quick \
  --output "quality-results/candidate-quick-${QUALITY_RUN_ID}"
```

Only exit `0` with terminal `QUALITY GATE: PASS` permits promotion. Exit `3`
means a completed quality regression; exits `1`, `2`, and `130` mean the run
failed, was invalid, or was interrupted. Any nonzero exit rejects or blocks
promotion. A bare `EVALUATION RUN: PASS` only means the run completed—it is not
a quality decision.

The frozen untouched reference and acceptable thresholds on this Mac are:

| Gate | Baseline | Accept candidate |
| --- | ---: | ---: |
| Periodic core downstream | 16/35 | at least 16/35 |
| Full quick downstream | 26/53 (49.06%) | at least 26/53 |
| Token-weighted PPL | 13.954858 | at most 14.386452 |
| Ranked GPQA response identity (full quick only) | 9 saved prefixes | at least 7/9 exact |
| Public first-token probe | token 5991 | exact match |

Full-panel diagnostics are MMLU-Pro `9/20`, GPQA greedy `6/9`, GPQA sampled
`4/9`, AIME `4/9`, and GSM8K `3/6`; only their summed correct count gates.
PPL and ranked GPQA are separate. Always use a same-host, contract-compatible
baseline: `quality-results/` is gitignored and not shipped in a fresh clone.
See `senpai/quality-evaluation.md` for the frozen prompts and output contract.
This advisory panel cannot relax exact-token correctness or replace the hidden
M5 quality and behavioral gates. Run only one model-holding process at a time.

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

Never:

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

## Research Method

The transferable lesson from the Senpai inference guide is a disciplined loop:

1. Define the exact validity contract.
2. Reproduce the current frontier on the measured path.
3. Decompose latency into named costs.
4. Price the maximum and break-even gain before implementation.
5. Test one hypothesis at a time.
6. Reject quickly on correctness, protocol, feasibility, or end-to-end speed.
7. Compose only individually measured winners.
8. Preserve negative results so later agents do not repeat them.

Every experiment PR should state:

```text
Hypothesis:
  What exact mechanism should make inference faster?

Target cost:
  Which measured prefill/decode budget line does it reduce?

Expected gain:
  What is the break-even gain, optimistic gain, and likely noise level?

Validity gate:
  Which exact-token, serial-protocol, build, and memory checks must pass?

Implementation scope:
  Which editable files and runtime-effective kernel forms will change?

Measurement plan:
  What baseline, tests, local mode, repetitions, and promotion gate will run?

Stop rule:
  What result makes the idea green, ambiguous, or dead?
```

Do not assign vague experiments such as "optimize attention." Assign a priced,
falsifiable change such as "avoid materializing this mask on one-token
sliding-window decode; expect X microseconds from the profile; reject if any
token differs or decode improves by less than the measured noise floor."

Use `python3 senpai/exa_search.py "query"` for general web search; add
`--category publication` for research literature. It reads `EXA_API_KEY` from
the environment or `senpai/.env` and prints the Exa response as JSON.

## High-Value Research Areas

Start from profiles and source inspection, not this list alone.

### NVFP4 matmul and MoE

- Quantized matmul dispatch and the M5 `_nax` variants.
- MoE expert gather-GEMM batching and indexing.
- Routed/shared expert projection scheduling.
- Fused or cheaper dequantization that preserves the required result.
- Reuse of input-independent derived weight views.
- Avoiding redundant copies, materializations, and synchronization.

Decode is likely sensitive to weight traffic, but the model is already NVFP4
where the checkpoint permits it. Prove that a proposed representation or kernel
actually reduces the scored path rather than adding conversion overhead.

### Attention and RoPE

- Group-32 affine INT8 re-quantization of Q/K/V/O and the newly admitted
  per-head `g_proj`, including layout, preparation, and decode dispatch.
- Correct dispatch between sliding-window and full attention.
- GQA broadcasting for 8 KV heads at head dimension 128.
- Steel attention behavior at the scored 512-token prefill length.
- Sliding-window masks and cache indices.
- YaRN partial-rotary work on full-attention layers.
- Kernel selection crossovers at the exact scored shapes.

An attention optimization that helps only a tiny context or a different head
shape is not evidence.

### KV cache

- A tighter 512-position ring for sliding-window layers.
- Avoiding copies or unnecessary physical cache movement.
- Cache layout and update scheduling for one-token decode.
- Compilable cache variants and compiled decode interactions.

Logical and physical positions must still advance by exactly the supplied
length.

### Runtime scheduling

- MLX graph construction and compilation reuse.
- Kernel-launch and command-buffer overhead.
- Safe fusion of operations already required by the current request.
- Removal of host synchronization and avoidable materialization.
- Weight preparation during unscored initialization only when it is
  input-independent and does not subsidize charged per-request work
  illegitimately.

### Weight loading and offline transform

- Fewer Data-to-Metal copies.
- Deterministic preparation or transform metadata for the permitted group-32
  affine INT8 Q/K/V/O/`g_proj` layouts.
- Runtime metadata that removes repeated shape/layout work.
- Deterministic transformed layouts that improve scored access.
- Compact artifacts within the default 25 GiB generated-weights cap.

The offline transform is unscored, but its output must be deterministic,
complete, portable to the official runner, and behavior-preserving.

### Output head

- Faster BF16 output projection.
- Better dispatch or layout for the untied 100352-token vocabulary head.
- Fusion only when it computes the full contractually required result.

Vocabulary pruning and candidate-limited output are high-risk because hidden
prompts differ and exact greedy tokens are required. Reject prompt-specific
keep sets and fallbacks whose cost erases the win.

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

- **Green:** correctness/protocol pass, a repeatable same-host end-to-end gain,
  no component floor risk, and a clean editable-surface-only implementation.
- **Ambiguous:** gain near noise, machine-generation-specific correctness
  uncertainty, unstable prefill/decode tradeoff, or incomplete M5 transfer
  evidence. Repeat or narrow the experiment.
- **Red:** any new token mismatch, prohibited computation, invalid surface
  change, OOM, component below `0.95`, or no repeatable end-to-end gain.

A microbenchmark win without an end-to-end win is a negative result. An
aggregate gain that materially regresses one axis or threatens the acceptance
band is not a clean winner.

## Results Contract

This repository does not use W&B for benchmark metrics. Do not add W&B logging
to the submitted runtime or trusted harness. The canonical experiment artifacts
are the ignored score JSON files, exact command output, Git commit, and the PR
result comment. Use an empty `wandb_run_ids` list unless orchestration separately
records a real external run.

Every terminal student result must begin with a single-line marker:

```text
SENPAI-RESULT: {"terminal":true,"status":"complete","pending_arms":false,"wandb_run_ids":[],"primary_metric":{"name":"local_paired_score_estimate","value":1.0123},"test_metric":{"name":"passed_correctness","value":1}}
```

Use `passed_correctness` value `1` for a passing local gate and `0` otherwise.
If no valid timing exists, use a truthful sentinel such as `0` for the primary
metric and explain the failure immediately below; never invent a score.

The result comment must also include:

- student name and PR number,
- hypothesis and target cost,
- baseline commit and candidate commit,
- Mac model, chip generation, unified memory, macOS/Xcode/Swift versions, and
  startup memory profile,
- exact baseline and candidate commands,
- baseline and candidate `score`,
- baseline and candidate decode/prefill seconds per token,
- same-host decode gain, prefill gain, and weighted paired estimate,
- `passed`, `passed_correctness`, checked steps, and any divergent tokens,
- peak RAM and generated weights byte count,
- number of measurements and whether the thermal gate passed normally,
- tests run,
- exact files changed and confirmation that they are in `editablePaths`,
- what happened and the most likely mechanism,
- caveats, especially non-M5 transfer risk,
- suggested follow-ups,
- a clear recommendation: merge, repeat, revise, or close.

Example table:

| Metric | Baseline | Candidate | Ratio / delta |
| --- | ---: | ---: | ---: |
| decode seconds/token | ... | ... | ...x |
| prefill seconds/token | ... | ... | ...x |
| local estimated score | ... | ... | ... |
| passed correctness | ... | ... | — |
| peak RAM GB | ... | ... | ... |

Negative results are first-class research assets. State whether failure came
from correctness, serial-track validity, build feasibility, memory, M5 transfer
risk, measurement noise, or lack of end-to-end speed.

## Advisor Guidance

Maintain a balanced portfolio across MoE/quantized matmul, attention, KV cache,
runtime scheduling, output head, and transform/layout work. Allocate experiments
according to measured budget, not idea novelty.

- Keep one hypothesis per PR.
- Put the baseline commit, baseline metrics, expected gain, files, validation
  ladder, and stop rule in the PR body.
- Prefer prompt-invariant, by-construction-safe changes.
- Price risky kernel work before assigning a large implementation.
- Close dead ends once evidence clears the stop rule.
- Search merged/closed PRs before repeating an idea.
- Merge only measured winners based on the current advisor frontier.
- Rebaseline after every merged winner before assigning comparisons against the
  new frontier.
- Do not merge several individually unmeasured optimizations and assume their
  gains add.
- Reserve `--local-submit` and official queue time for candidates that survive
  the fast screen.
- Treat official M5 feedback as new evidence. Record it before the next round.
- Chunk candidates that appear to exceed the single-submission acceptance band.

The strongest baseline is already highly tuned. Favor precise, mechanism-backed
experiments over broad refactors. Simpler code is preferred when performance
and correctness are equal.

## Roles

Research is coordinated through Senpai's GitHub advisor/student PR workflow.
The advisor proposes and routes hypotheses; students implement only assigned
work, run the benchmark ladder, and report structured results. Human issues may
override or stop work.

Any `instructions/prompt-advisor.md` and `instructions/prompt-student.md` role
overlays must point back to this program and must not weaken the repository
contract.
