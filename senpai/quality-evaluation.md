# Laguna quality evaluation

`quality-eval` runs the imported PPL, MMLU-Pro, GPQA-Diamond, AIME, and
GSM8K evaluators against the Laguna model built from a challenge checkout.
It prints evaluator progress and the final summary, while preserving the
run manifest, metrics, logs, and raw model responses on disk.

This panel is a regression screen, not a replica of the challenge's hidden
quality or behavioral gates. A passing run does not guarantee a passing
submission; use it alongside `./benchmark.sh --local-submit`.
In particular, `run.json` status `completed` and `evaluation_valid: true`
mean every selected evaluator
completed with a complete, internally consistent result set. It does not mean
the model cleared a quality threshold—the hidden threshold is unknown. Make
submission decisions from a matched baseline `compare` plus `--local-submit`.

## What the challenge's behavioral gate means

The public harness shows that “behavioral” is a reference-behavior regression
gate, not a generic safety classifier or another PPL threshold. Ranked runs
combine exact teacher-forced tokens, hidden logit anchors, short exact
free-runs, and nine private GPQA prompts. GPQA is invoked as an already
formatted raw string with BOS and up to 128 generated tokens; a semantic judge
compares the candidate response with the pinned Laguna reference response.
The current calibrated floor is seven matches out of nine. It intentionally
tests preservation of the reference model's answer behavior, not whether an
alternative answer is factually better.

The hidden prompts and reference answers are unavailable locally, so this
panel cannot reproduce that gate. Its ranked raw+BOS GPQA arm and exact
baseline response comparison are conservative public proxies. PPL,
MMLU-Pro, AIME, and GSM8K add broader quality-regression evidence.

## Run it

Install `uv`, prepare the reference checkpoint with `./setup.sh`, then pass
the checkout directory directly:

```bash
./senpai/quality-eval run . \
  --profile quick \
  --output quality-results/candidate-quick
```

`quick` is the routine one-pass regression gate. It covers all eight built-in
PPL records at 32 scored tokens each, 20 MMLU-Pro questions, nine GPQA-Diamond
questions through full greedy, full sampled, and ranked greedy heads, three
AIME problems distributed across the requested contests, and 12 GSM8K
questions. Full-head generation is capped at 256 tokens, the ranked GPQA proxy
at 128, and model requests are serialized.
The 14,976-token worst-case budget completed in 595.9 seconds (9:56 including
preparation) on the 128 GB M4 Max used for local development. One-time
checkpoint download, setup, and weight transformation are outside that timing.

The downstream quality panel retains the imported evaluators' chat-template
prompts. Its separate ranked GPQA behavior proxy uses a raw single-user prompt
with BOS, matching the challenge's hidden GPQA invocation boundary. `run.json`
records prompt formats per suite and head; PPL uses pretokenized token IDs.

Every checkout run also performs a one-token diagnostic against the checked-in
M5 public fixture. On the development M4 Max, the current checkout produced
token `8550` where the M5 fixture records `5991`; the run records this under
`local_public_correctness_probe` and prints a warning. When that probe differs,
absolute autoregressive accuracy is only diagnostic. Preserve one baseline run
and rely on `compare` for PPL deltas and exact response drift on the same Mac.

The default profile remains the tiny `smoke` plumbing check:

```bash
./senpai/quality-eval run .
```

It exercises every evaluation path with two items per suite, but is not a
meaningful model-quality estimate.

For the exact five-pass downstream-quality shape, use:

```bash
./senpai/quality-eval run . \
  --profile full \
  --passes 5 \
  --output quality-results/candidate-full
```

`full` defaults to five passes when `--passes` is omitted. It uses the
challenge-era evaluator sizes (500 MMLU-Pro, all GPQA-Diamond, 60 AIME, and
500 GSM8K items per pass), the full built-in PPL corpus, and the 6,144-token
generation budget. The historical panel runs unchanged through the full BF16
head; an additional unmasked, 128-token GPQA greedy pass exercises the
submitted/default ranked head as a behavior-gate proxy. It can take many hours
on the serial endpoint. `standard` is the intermediate profile.

Select a subset by repeating `--suite`:

```bash
./senpai/quality-eval run . \
  --profile standard \
  --suite ppl \
  --suite gpqa_diamond \
  --output quality-results/candidate-ppl-gpqa
```

Suite names are `ppl`, `mmlu_pro`, `gpqa_diamond`, `aime`, and `gsm8k`.
The output directory must be new or empty. Use `--keep-going` when you want
the remaining evaluators to run after one fails.

The built-in PPL corpus is self-contained. The downstream suites obtain their
datasets from Hugging Face or its datasets server at run time (or supported
local caches), so they need network access while the model is resident.

## Outputs

Each run directory contains:

- `run.json`: resolved artifact, content hashes for the bridge, Metal library,
  transformed shards, and tokenizer, checkout source identity, profile,
  suites, prompt formats, host hardware/OS identity, commands, per-command and
  per-head timings, total wall time, the optional local public-fixture probe,
  evaluator provenance, status, and failures;
- `summary.json`: aggregate metrics across the completed passes;
- `responses.jsonl`: every HTTP request and full response, including raw
  model text or prompt-token log probabilities;
- `bridge.log`: diagnostics from the persistent Swift model process;
- `ppl_manifest.jsonl` and its metadata when the built-in PPL corpus is used;
- `pass_N/`: evaluator JSON results, raw completions, scored PPL token data,
  and command logs for that pass.

Evaluator output is streamed to the terminal, and the final summary is
printed as JSON. These files are the durable record; assign an explicit
`--output` path in automation.

## Compare matched runs

Run the same profile and suites against a baseline and candidate, then use:

```bash
./senpai/quality-eval compare \
  quality-results/baseline-quick \
  quality-results/candidate-quick \
  --output quality-results/comparison.json
```

`compare` fails closed if either run failed or is incomplete, or if the
profile, effective profile settings, pass count, suite set, prompt-format
policy, host hardware/OS identity, public-fixture identity, evaluator
provenance, tokenizer identity, or PPL manifest differs. It verifies exact
per-suite cardinality, finite and internally consistent metrics, and prompt
hashes for every present downstream suite before reporting metric deltas and
raw-response identity.

The JSON `decision` marks any worse metric, raw-response drift, or changed
public-fixture probe token against the matched baseline as a regression.
`compare` still writes and prints the full report, then returns exit status 3
on regression so an agent can stop a submission. Use `--report-only` only when
that nonzero policy is undesirable. `matched_or_improved` is evidence against
an observed local regression, not a claim that the hidden gate passed.

Create the baseline once for the exact checkout, hardware/OS identity, and
profile you intend to use, then rerun only the candidate after model or kernel
changes. `compare` enforces those identities along with prompt formats,
tokenizer, PPL manifest, and evaluator provenance. This is especially
important off-M5, where a first-token hardware divergence can make absolute
autoregressive scores unrepresentative while same-host response stability
remains a useful regression signal.

The underlying operations are available separately:

```bash
./senpai/quality-eval check-prompts \
  quality-results/baseline-full \
  quality-results/candidate-full

./senpai/quality-eval summarize \
  quality-results/baseline-full \
  quality-results/candidate-full \
  --output quality-results/five-pass-summary.json
```

`check-prompts` validates whichever of MMLU-Pro, GPQA-Diamond, AIME, and
GSM8K are present, and fails if a task is present in only some supplied runs.
`summarize` aggregates completed evaluator outputs; `compare` is the stricter
baseline-versus-candidate command.

## Artifact preparation

For a challenge checkout, `run` and `serve` automatically:

1. transform the reference checkpoint when `weights/` is missing or stale;
2. incrementally build the candidate-linked `laguna-quality-bridge`;
3. rebuild `mlx.metallib` when its source fingerprint is stale.

The transform needs the pinned reference checkpoint installed by
`./setup.sh`. Use `--reference`, `--weights`, `--tokenizer`, `--bridge`, or
`--metallib` only when overriding normal checkout discovery.

`--no-build` disables all preparation. It does not accept stale default
checkout artifacts: the command validates transformed-weight, bridge-source,
and metallib fingerprints and fails with an actionable error. Explicit
artifact-path overrides are caller-owned. This mode is useful in automation
after a separate, controlled build step.

To evaluate a prepared, self-contained bundle instead of a checkout, put a
`quality-artifact.json` file at the directory passed to the CLI:

```json
{
  "weights": "weights",
  "tokenizer": "tokenizer",
  "bridge": "bin/laguna-quality-bridge",
  "metallib": "lib/mlx.metallib"
}
```

Paths are relative to the bundle root unless absolute. `weights` must contain
the transformed model, `tokenizer` must contain Laguna's `tokenizer.json` and
chat template, and `bridge` must be executable. `run` and `serve` require the
Metal library. Check discovery without loading the model with:

```bash
./senpai/quality-eval inspect /path/to/checkout-or-bundle
```

## Serve the evaluator API

The CLI can keep one candidate loaded behind a local OpenAI-compatible API:

```bash
./senpai/quality-eval serve . \
  --port 8765 \
  --request-log quality-results/manual-responses.jsonl
```

It prints a machine-readable `ready` record containing the base URL. The
server exposes `/v1/models`, `/v1/chat/completions`, `/v1/completions`, and
`/v1/tokenize`; integer-token completions support the prompt log probabilities
used by the PPL evaluator. Requests share one persistent Swift bridge and are
serialized through the model.

`serve` defaults to `--head-mode full`, which is required for sampling and
prompt log probabilities. Use `--head-mode ranked` only for unmasked greedy
generation through the submitted/default head; unsupported sampling,
minimum-token masking, and logprob requests fail explicitly.

## PPL corpus compatibility

The imported PPL scorer and its token-weighted perplexity equation are
preserved, but the old Gemma manifest is not reusable: it contains Gemma
token IDs, including IDs outside Laguna's 100,352-token vocabulary.
`quality-eval` therefore tokenizes a small, original Laguna-specific text
corpus and saves the resulting manifest with the run.

The quality bridge retains the candidate's batch-one model and KV path. The
historical quality panel disables the argmax-only LM-head pruner because
sampling, minimum-token stop masking, and PPL require probability-correct
full-vocabulary logits. A second, unmasked greedy GPQA pass restarts the bridge
with the submitted/default ranked head, catching B=1 head-path regressions that
the full-distribution panel would miss. The two model processes never overlap.

Compare PPL only when the tokenizer and manifest hash match. Do not compare
the absolute Laguna result with the old Gemma challenge number. To supply a
different Laguna-tokenized JSON or JSONL manifest, pass
`--ppl-dataset /path/to/manifest.jsonl`; matched baseline and candidate runs
must use the identical file.

## Memory safety

Laguna's text tower is about 21.6 GB before KV state and working buffers.
`run` and `serve` share the benchmark's per-user model lock, reject known
model-holding processes, and clean up their bridge and evaluator children on
exit. They therefore fail instead of intentionally overlapping a local
benchmark or another evaluator. Direct correctness/model commands do not take
that lock; wait for the current model process to exit before starting one.
