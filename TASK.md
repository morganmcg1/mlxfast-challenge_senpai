# mlxfast — Poolside Laguna XS 2.1 Serial Swift Challenge

Optimize serial (one token per decode request) inference for Poolside Laguna
XS 2.1 (MoE text tower, Poolside NVFP4) on Apple Silicon while preserving the model's
exact greedy output.

## Default ranked contract

`benchmark.json` and `.github/workflows/benchmark.yml` define the default —
and only — Yukon track, `laguna-xs-2.1-serial-v2`.

A ranked run on the self-hosted M5 box:

1. Verifies the pre-provisioned reference checkpoint against the pinned
   manifest, builds the trusted CLI and the sandboxed participant worker,
   and transforms the reference checkpoint into `weights/`.
2. Runs the public drift tripwire, then the hidden 512-token-prompt
   teacher-forced base case plus anchor/free-run/behavior/GPQA gates and the
   semantic GPQA judge.
3. Scrubs every hidden byte from the bench workspace, then runs the timed
   paired measurement LAST behind the fixed 40C thermal gate: the pinned
   baseline tree and the candidate are measured back to back on the same
   silicon (`measure-job.sh`, telemetry-validated).

Timing measures a 512-token prompt prefill and a teacher-forced decode window
(512-token decode seed, 128 decode steps; see
`docs/benchmark-window-freeze.md` for the frozen knobs). The published score
is the paired prefill+decode weighted speedup:

```text
score = decode_speedup^0.75 * prefill_speedup^0.25
decode_speedup_floor = 0.95
prefill_speedup_floor = 0.95
```

Both floors are hard: a run below either floor, or with any token mismatch,
publishes no score.

The deployed ranked wrapper does not apply the inner benchmark binary's legacy
two-sided `AcceptanceBand` as a candidate-gain cap. The on-box measurement
wrapper treats baseline and candidate invocations as timing probes, checks the
pinned baseline's calibration health separately, and owns the final paired
verdict. `overlay-paired-timing.sh` applies the two `0.95` component floors;
promotion then requires the score to beat the current best.

The legacy `[0.980, 1.053]` decode and `[0.952, 1.053]` prefill values remain
in `MLXFastCore` for the inner/legacy evaluation path. They do not require a
genuine candidate win to be throttled or split. Accepted official receipts
with gains well beyond 5% confirm the deployed behavior.

Run `./setup.sh`, then `./benchmark.sh --local-iterate` or `--local-submit`.
Local modes write estimated score artifacts only; the official paired score
comes exclusively from the ranked M5 run.

## Model Artifacts

The frozen source checkpoint is
`poolside/Laguna-XS-2.1-NVFP4-mlx@841778bda563a36104dd521e37d99218e46f4f25`.
The benchmark verifies it against the pinned manifest before use.

The Swift transform writes benchmark-ready weights here:

```text
weights/
  config.json
  model.safetensors.index.json
  model-0000N-of-0000M.safetensors
  tokenizer.json
  tokenizer_config.json
```

The generated tree is a runtime artifact, not a required byte-for-byte copy of
the baseline layout. The transform may change the representation through the
editable transform and runtime together, subject to the rules below,
correctness, and the transformed-output size cap. Every expert remains loaded
in RAM; there is no expert-streaming manifest or scored weight streaming.

### Accepted attention quantization envelope

The live challenge contract permits submissions to re-quantize only these
attention projections to **group-32 affine INT8**:

- query projection (`q_proj`),
- key projection (`k_proj`),
- value projection (`v_proj`),
- output projection (`o_proj`),
- per-head gate projection (`g_proj`).

This is a narrow representation allowance, not permission to change the
model's overall precision or behavior. The source checkpoint remains
authoritative, exact-token and hidden behavior gates still apply, and no other
BF16 tensor is admitted. In particular, do not infer permission to re-quantize
embeddings, Q/K norms, routers, the layer-0 dense MLP, the untied output head,
or any other unlisted projection.

The trusted harness must understand this envelope. Do not hand-edit trusted
validation to admit a new layout.

## Editable Surface

`editablePaths` in `benchmark.json` is the exact submission surface. Its
current entries fall into four groups:

| Path | Scope |
|---|---|
| `Sources/MLXFastModel/` | Scored Laguna runtime, custom kernels, cache handling, and prefill/decode execution. |
| `Sources/MLXFastTransform/` | Offline weight transform and runtime metadata. |
| Listed `Vendor/mlx-swift-lm/` files | Laguna model oracle and the `MLXLMCommon` attention, MoE, RoPE, KV-cache, and compiled-decode plumbing used by the runtime. |
| Listed `Vendor/mlx-swift/` files | MLX Metal dispatch plus the AOT and JIT kernel sources reached by Laguna. |

`Sources/MLXFastCore/`, `Sources/MLXFastHarness/`,
`Sources/MLXFastCLI/`, scripts, tests, `benchmark.json`, package manifests,
generated `weights/`, reference checkpoints, golden fixtures, local scores,
and every unlisted vendor file are outside that surface. Trusted correctness,
timing, scoring, and provenance checks are not participant-editable.

The benchmark rejects transformed `weights/` above the default 25 GiB cap.
There is no Python challenge-runtime path.

## Correctness Gates

Correctness is a hard gate. Each base golden case contains exactly 512 prompt
token IDs and at least 64 expected continuation token IDs. The harness checks
the first 64 continuation positions teacher-forced with temperature-zero
behavior: after each accepted step it feeds the golden previous token back into
the model. The first mismatch records only the case, step, expected token, and
actual token in the failed report.

The gate is intended as a first-stage filter: an implementation that fails it is
not eligible for the longer benchmark.

Private golden fixtures may add hidden `correctness_gates` on top of the base
teacher-forced cases:

- `anchors`: one-token checks at selected hidden contexts. These can require an
  exact expected token, explicit accepted tokens, or a bounded top-logit rank
  and delta for near-tie hardware cases.
- `free_run`: short greedy continuations whose exact prefix must match. These
  catch bugs that only appear when the model consumes its own generated tokens.
- `behavior`: GPQA-style or instruction-following prompts whose answer is
  checked exactly against precomputed accepted answer token sequences. Each
  accepted answer sequence must have at most `max_new_tokens` tokens; shorter
  sequences are matched as exact prefixes of the generated answer.

Full benchmark CI adds one more private layer after the correctness and gates
pass (and before the timed measurement, which runs last on the ranked
pipeline): it captures short answers for hidden GPQA cases and asks a Claude
judge whether each candidate is semantically equivalent to the private
reference answer. That semantic gate is pass/fail only and does not affect
the timing score; its pass-count threshold is baseline-calibrated (see
`MLXFastConstants.semanticGPQAMinPassCount`). The uploaded score records only
aggregate semantic counts and the judge model name.

The same hidden GPQA cases are also used for a TTFT guardrail: during the
hidden behavior correctness pass, the workflow times prompt prefill through
the first greedy answer token and verifies that the first token is accepted for
that case. The uploaded score records only
aggregate TTFT pass counts and timing statistics; first-token values and
accepted token sets are not logged or artifacted.

These layers keep the official gate mostly deterministic and token-based while
adding a small semantic backstop against implementations that pass the exact
prefix but damage answer meaning. The benchmark operator should keep private
prompts, accepted answer sequences, reference answers, and judge transcripts
outside the public repository.

The gate intentionally does not port a hidden-state comparison layer. The
benchmark contract cares about the externally observable text-to-text Laguna
output path, and hidden-state tensors are easier to make ambiguous around
normalization than token-level or logit-anchor checks.

VLM/image and audio inputs remain out of scope. Only the Laguna text tower
executes.

### Serial non-speculative rule (default track)

In `benchmark.json`, each model
invocation may compute logits and KV rows only for tokens supplied in that
invocation, and must advance logical and physical KV position by exactly the
supplied input length. A one-token decode request therefore advances exactly
one position and leaves no pending future token, logits, or KV state for a
later request.

This excludes prompt-lookup decoding; n-gram, suffix, or other token-history
drafting; same-target lookahead; and any other mechanism that selects or
evaluates an unsupplied future token. It also excludes two-, three-, or
more-row target-model execution used to verify a draft from a one-token
request, plus cross-request future-logit/KV buffering, deferred cache rows,
and commit, rollback, recommit, or discard markers for such rows. These
mechanisms remain excluded when they are generic, bit-exact, or useful in
production. Warming an excluded speculative pipeline before the worker
protocol hello or during model initialization does not make it eligible.

Ordinary within-request KV reuse remains allowed, as do current-token-only
decode execution and input-independent caches for weights, dequantized
tensors, kernels, masks, or RoPE tables. Multi-row kernels are allowed when
every row corresponds to a token actually supplied in that same invocation,
such as ordinary prefill; the prohibited case is using extra rows to compute
or verify future tokens for a serial one-token request.

Organizer-provided MTP or other speculative decoding would require a
separately declared trusted block protocol, correctness contract, and score;
no such track currently exists, so these
restrictions apply to every ranked submission.

## Local Workflow

```bash
export PATH="${HOME}/.local/bin:${PATH}"
swift test --force-resolved-versions
swift build -c release --force-resolved-versions
git checkout -- Package.resolved
```

Use `./setup.sh` after toolchain, checkpoint, harness, or AOT-kernel changes.
Use `./benchmark.sh --local-iterate` for matched experiments and
`./benchmark.sh --local-submit` before submission.
