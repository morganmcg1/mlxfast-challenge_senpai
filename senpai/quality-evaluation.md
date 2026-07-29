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

## Run it

Install `uv`, prepare the reference checkpoint with `./setup.sh`, then pass
the checkout directory directly:

```bash
./senpai/quality-eval run .
```

That runs the one-pass `smoke` profile across all five suites and writes a
new directory under `quality-results/`. The smoke profile is intentionally
small: it verifies the entire evaluation path and catches gross regressions,
but it is not a stable model-quality estimate.

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
  suites, commands, evaluator provenance, status, and failures;
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
  quality-results/baseline-full \
  quality-results/candidate-full \
  --output quality-results/comparison.json
```

`compare` fails closed if either run failed or is incomplete, or if the
profile, effective profile settings, pass count, suite set, evaluator
provenance, tokenizer identity, or PPL manifest differs. It verifies exact
per-suite cardinality, finite and internally consistent metrics, and prompt
hashes for every present downstream suite before reporting metric deltas and
raw-response identity.

The JSON `decision` marks any worse metric or raw-response drift against the
matched baseline as a regression. `compare` still writes and prints the full
report, then returns exit status 3 on regression so an agent can stop a
submission. Use `--report-only` only when that nonzero policy is undesirable.
`matched_or_improved` is evidence against an observed local regression, not a
claim that the hidden gate passed.

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
