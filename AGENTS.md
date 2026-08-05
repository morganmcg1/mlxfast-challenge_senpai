# MLXFast Challenge Agent Guide

This is the working contract for the Swift-only Poolside Laguna XS 2.1 NVFP4
inference challenge. `benchmark.json` and the trusted harness are authoritative
when prose disagrees with executable configuration.

## Goal

Optimize the text tower on the serial `laguna-xs-2.1-serial-v2` track without
changing any checked output:

```text
score = decode_speedup^0.75 * prefill_speedup^0.25
```

Each speedup compares the candidate with the pinned baseline measured in the
same official session. Both component speedups must be at least `0.95`.

The deployed ranked wrapper does **not** cap candidate gains at `1.053`.
`AcceptanceBand` remains in the inner benchmark binary, but the on-box
measurement wrapper treats those invocations as timing probes, checks the
baseline's health separately, and publishes the paired candidate verdict with
only the two `0.95` floors. A submission must then beat the current best to be
promoted. Never throttle or split a genuine win to fit the legacy band; split
only when doing so improves causal attribution.

## Official Hardware

Ranked runs use one self-hosted M5 Max with 128 GB of unified memory. Candidate
and baseline run back to back behind the same 40C thermal and telemetry gate.
The official M5 result decides correctness and ranking.

The roughly 21.6 GB text tower, including all 256 routed experts and the shared
expert, stays resident in RAM. There is no expert cache, weight streaming, or
scored disk I/O.

M4 measurements are useful directional evidence when baseline and candidate
run on the same quiet host under the same thermal policy and execute the same
kernel family. M4 Pro hosts report Apple GPU generation 16 and do not select
the `_nax` prefill kernels used by the ranked M5, so an M4 prefill result is not
evidence for an `_nax` change. Threadgroup geometry can also change sign across
core counts. Record kernel reachability and architecture before interpreting a
result. Public fixtures were generated on M5, so a near-tie argmax may also
differ on another Apple Silicon generation.

## What You May Optimize

`editablePaths` in `benchmark.json` is the exact submission surface (currently 97 entries).
Its four groups are:

- `Sources/MLXFastModel/`: scored Laguna runtime, kernels, and decode path.
- `Sources/MLXFastTransform/`: offline weight transformation and metadata.
- Listed `Vendor/mlx-swift-lm/` Laguna and `MLXLMCommon` files used by the
  runtime.
- Listed `Vendor/mlx-swift/` MLX Metal dispatch and kernel sources.

The submitted surface is capped at 3,000,000 bytes total, 524,288 bytes per
file, and 262,144 bytes of growth per submission review. Validate proposed
paths against the experiment base's committed contract and check byte headroom
before build or timing work; local timing can succeed for a candidate the
official static review will refuse. The current editable-file count is a test
fixture, not an official competition rule.

The scored forward pass is
`Sources/MLXFastModel/LagunaRuntimeModel.swift`. Vendored `Laguna.swift` is the
upstream-equivalence oracle; editing it alone does not improve scored timing.
The listed `MLXLMCommon` cache, attention, RoPE, MoE, and decode helpers do run
on the scored path.

For kernel families with an `mlx-generated/*.cpp` twin, that embedded source
is compiled at runtime. Keep it consistent with the corresponding `.metal` or
header source. The M5 selects `_nax` variants where available, so update and
test them. RoPE, RMSNorm, SDPA vector, and `arg_reduce` are AOT; rebuild the
metallib with `tools/build-mlx-metallib.sh` after changing their sources.

Use `./benchmark.sh --local-iterate` for the scored worker build and timing
path. A bare `swift build -c release` writes a different build directory.

The only permitted attention re-quantization is group-32 affine INT8 for
Q/K/V/O and per-head `g_proj`. See the
[accepted envelope](TASK.md#accepted-attention-quantization-envelope).

## What Not To Change

Files outside `benchmark.json`'s `editablePaths` are not submitted. This
includes trusted CLI, harness, scoring, workflow, test, documentation, fixture,
and generated-weight files, plus unlisted vendor code and package manifests.

Do not hardcode prompts, tokens, or answers; read hidden artifacts; bypass the
protocol; specialize for fixtures; or rely on network or filesystem access.
Python is not part of the challenge runtime.

Do not add caches or memos keyed on input tokens whose only
possible hit is the benchmark harness repeating an identical computation.

## Correctness Gates

Correctness is a hard gate. Every checked greedy token must match.

The official stack includes the public 64-step drift tripwire, hidden
512-token teacher-forced cases, hidden anchors and free runs, GPQA behavior and
TTFT checks, a semantic GPQA judge, and token validation during the timed
phase. A mismatch or failed gate publishes no score.

`LagunaUpstreamEquivalence.swift` checks the runtime against the vendored model
oracle. Use it when a change affects numerical behavior, representation,
dispatch, or layout. The M5 remains authoritative for near-tie differences.
Run it through `research/run_upstream_equivalence.sh`; the wrapper uses the
exact bare test filter, repairs the debug metallib placement, and refuses to
call a zero-test invocation a pass.

The serial non-speculative rule at the end of this file is part of
correctness, not an optional optimization constraint.

## Timing And Score Measurement

The frozen window has two axes: one 512-token prefill, and a teacher-forced
decode pass with a 512-token seed and 128 one-token steps. Decode has 75% of the
score weight; prefill remains scored and has its own hard floor.

Published speedups use the same-session paired baseline. The deployed wrapper
uses pinned calibration to check baseline health, not to cap candidate gains.
The final candidate merge in `overlay-paired-timing.sh` enforces correctness
and the paired `0.95` floors. Legacy per-binary band failures are not the final
ranked verdict.

Memory and read timings are diagnostics. `bandwidth_gb_per_token` is always
zero because the full model is RAM-resident.

## Local Workflow

This checkout has two distinct remotes:

- `origin`: the research fork.
- `upstream`: the organizer repository.

The maintained fork `main` is the integration base. Before advisor or student
branches start, it must contain the relevant organizer updates and the current
promoted editable frontier. The advisor owns that integration and records its
exact commit as `BASE_SHA`; students branch from that recorded base.

Before assigning an experiment, list its submitted paths separately from
research-only support files and run
`senpai/validate-assignment-scope.sh "$BASE_SHA" PATH...` followed by
`senpai/check-editable-budget.sh "$BASE_SHA"`. The assignment must also show
that the proposed control reaches the scored runtime path; a knob on an unused
fallback is not a timing experiment.

Do not select the frontier by pulling a remote branch or inferring it from a
branch name. Organizer synchronization, frontier promotion, and harness-only
refresh are different operations. Follow
[`senpai/experiment-runbook.md`](senpai/experiment-runbook.md) for the exact
branch, sync, baseline, and promotion procedure.

Run `./setup.sh` when preparing a host or after toolchain, checkpoint, harness,
or AOT kernel changes. Use `./benchmark.sh --local-iterate` for matched
baseline/candidate research and `--local-submit` before promotion.

Always pass `--force-resolved-versions` to direct `swift build` and `swift
test` commands. The dependency graph is frozen; an unflagged command can
rewrite `Package.resolved`.

```bash
swift test --force-resolved-versions
swift build -c release --force-resolved-versions
git checkout -- Package.resolved
```

## Notes For Autonomous Agents

- A wait at "waiting for GPU to cool down" is expected. Do not kill it or
  disable the gate for comparable timing. If cooling fails, remove the other
  GPU load and retry.
- Run one model-holding process at a time. The local benchmark lock refuses a
  second run but direct correctness and golden commands do not take that lock.
  Inspect reported PIDs before terminating a confirmed orphan.
- Hosts below 64 GiB use the low-memory startup profile. It changes allocator
  management, not ranked code paths. About 36 GiB is the practical minimum;
  an undersized host fails rather than skipping work.
- If a non-M5 host disagrees with a public golden, test the unchanged base. Use
  `MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT=1` only when the base has the same near-tie
  divergence. It records failure and never relaxes official gates.
- Treat local scores as directional. Compare fresh candidate seconds/token
  with a fresh unchanged baseline on the same host.
- Let an existing benchmark finish. Starting overlapping workers can hold two
  copies of the model and exhaust unified memory.

## Submission Workflow

```bash
export PATH="${HOME}/.local/bin:${PATH}"
```

Run `./benchmark.sh --local-submit`, then inspect the candidate against
`benchmark.json`'s `editablePaths`. The Yukon CLI command `mlxfast submit`
uploads only that surface and does not run local preflight for you.

For every official submission from this Senpai campaign, first use
`mlxfast submit --model "senpai"`. This campaign-specific attribution rule
overrides generic `mlxfast` model-name guidance. Only if the submission API
explicitly rejects `senpai` as an invalid or unsupported model value may the
same candidate be retried once with the exact underlying provider/model name.
Do not fall back for a timeout, network error, validation failure, or unrelated
error because the first submission may already exist. In all cases, record the
actual provider/model and reasoning effort in the public note; if the fallback
was required, record the explicit rejection there too.

Only the advisor or human operator dispatches an official submission. The
official M5 run supplies the hidden gates and ranked score. Supporting tests or
docs may aid research but the submitted candidate must work without them.
An authorized campaign role may dispatch from a provisioned AWS research host;
never print or commit its submission credentials. A `rejected` receipt can mean
only that the score did not beat the current best, so inspect correctness,
error, and both floor verdicts separately from ranking status.

## Practical Optimization Ideas

- Reduce NVFP4 quantized matmul and MoE gather-GEMM work, especially routed
  and shared-expert projections.
- Improve attention dispatch for sliding-window versus full attention, GQA,
  and YaRN partial-rotary RoPE.
- Reduce KV-cache movement; sliding-window layers need only the latest 512
  positions.
- Remove redundant MLX operations, materialization, copies, synchronization,
  and command-buffer overhead.
- Prepare reusable weight views, dequantization state, masks, and RoPE tables
  outside the scored hot path.
- Use transform metadata or layout changes that let the runtime skip real work
  without changing behavior.

## Avoid These Wrong Strategies

- Optimizing vendored `Laguna.swift` without reaching the scored runtime.
- Treating disk I/O, expert streaming, or an expert cache as a scored cost.
- Specializing for public prompts, tokens, fixtures, or one machine.
- Caching a whole prompt result or KV state only because a harness might repeat
  the same request. The benchmark measures single-pass inference.
- Trusting hot, unmatched, stale-frontier, or cross-machine timing.
- Using local-only overrides as evidence that a candidate is rankable.
- Changing precision outside the accepted attention envelope.
- Combining several unmeasured mechanisms before any one wins end to end.

### Serial Non-Speculative Track Rules (default)

Each invocation may compute logits and KV rows only for tokens supplied in
that invocation. It must advance logical and physical KV position by exactly
the supplied input length. A one-token decode request advances one position and leaves no pending future token,
logits, or KV state for another request.

Prompt-lookup decoding, token-history drafting, same-target lookahead,
multi-row target evaluation of an unsupplied future token, deferred cache rows,
and cross-request commit/rollback state are excluded even when generic or
bit-exact.

Ordinary within-request KV reuse and input-independent weight, kernel, mask,
dequantization, or RoPE caches are allowed. Multi-row kernels are allowed only
when every row corresponds to a token supplied in that invocation, as in
prefill.
