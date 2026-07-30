# Laguna quality evaluation

`senpai/quality-eval` runs PPL, MMLU-Pro, GPQA-Diamond, AIME, and
GSM8K against the Laguna model built from a challenge checkout. It prints
progress and the final JSON summary, and saves the manifest, metrics, logs,
and raw responses.

This is a local regression screen, not the hidden challenge gate.
`status: completed` and `evaluation_valid: true` mean the selected evaluators
finished with consistent outputs; they do not mean the model passed a quality
threshold.

## Agent workflow

Run the baseline before changing model or kernel code:

```bash
# Requires uv on PATH.
./setup.sh

./senpai/quality-eval run . \
  --profile quick \
  --output quality-results/baseline-quick
```

After making an optimization:

```bash
./senpai/quality-eval run . \
  --profile quick \
  --output quality-results/candidate-quick

./senpai/quality-eval compare \
  quality-results/baseline-quick \
  quality-results/candidate-quick \
  --output quality-results/comparison.json

./benchmark.sh --local-submit
```

`compare` returns exit status 3 when the candidate fails the local gate.
Baseline and candidate must use the same recorded host hardware/OS identity,
profile, pass count, evaluator version, tokenizer, PPL manifest, prompts, and
prompt formats. The command checks these identities before comparing results.

`quick` is the routine profile. It runs:

- PPL: 8 records / 256 scored tokens;
- MMLU-Pro: 20 questions;
- GPQA-Diamond: 9 full-greedy, 9 sampled, and 9 ranked-greedy questions;
- AIME: 3 problems across the configured contests;
- GSM8K: 12 questions.

Two cool/warm runs completed in 9:56 and 16:55 on the development 128 GB M4
Max. The final provenance-compatible capture, run immediately after those two,
took 27:20. Create the baseline once, let the Mac cool before candidate runs,
and use roughly 10–17 minutes as the routine target. Initial setup, checkpoint
download, weight transformation, and dependency sync are excluded.

## Current untouched-model baseline

The unmodified challenge model produced this `quick` result on the
development M4 Max:

| Metric | Baseline | Local 97% threshold |
| --- | ---: | ---: |
| Token-weighted PPL | 262.0863 | at most 270.1921 |
| MMLU-Pro | 0/20 | uninformative |
| GPQA full greedy | 0/9 | uninformative |
| GPQA full sampled | 0/9 | uninformative |
| GPQA ranked greedy | 0/9 | uninformative |
| AIME | 0/3 | uninformative |
| GSM8K | 0/12 | uninformative |

This final-schema baseline was captured on 2026-07-30 on a `Mac16,6`
(Apple M4 Max, macOS 26.5.2), at Git commit
`36ce51a14ceeda89b9d4ef6f970c69686e7db731`. The evaluator provenance is
`b5fc971f564cab49f91361bb2244592e4a03efbf88dc2ae73daf0e04189c8d2f`;
the challenge-editable source hash is
`ab236d0ea1363a040d225666e723093e03ba9bf8611d20dc8aef88aefb2b1e1a`.
On this workspace, the reusable result is
`quality-results/baseline-quick-final-m4-20260730`.

PPL is the only meaningful absolute scalar baseline on this Mac. The
untouched model selects token `8550` where the checked-in M5 public fixture
expects `5991`, and the observed downstream generations are repetitive and
truncated. Those zero scores are real outputs of this M4 execution, but they
are not credible measurements of Laguna's M5 quality and a 97% floor of zero
would be vacuous. Use the ranked responses only for same-host comparison;
other response drift is diagnostic.

The official M5 remains the authority. On an M5, collect and compare against
a fresh matched M5 baseline; do not reuse this M4 table.

## Local 97% gate

`compare` evaluates every metric separately; improvements in one suite never
cancel regressions in another.

- Accuracy-like metrics must satisfy `candidate / baseline >= 0.97`.
- PPL is lower-is-better, so it must satisfy
  `baseline / candidate >= 0.97`. For the current baseline this means
  candidate PPL must be at most `262.0863 / 0.97 = 270.1921`.
- A zero accuracy baseline is marked `informative: false`; it is not treated
  as evidence of retained quality.
- In `quick`, at least 7/9 ranked GPQA responses must exactly match the
  same-host baseline. Larger profiles use the same 7/9 proportional floor.
  This is a conservative local proxy for the hidden semantic check.
- When available, the one-token public-fixture probe must exactly match the
  baseline token.
- Both runs must be complete, internally valid, and contract-compatible.

The comparison JSON records each metric's direction, retention, threshold,
and pass/fail result. `local_retention_gate_passed` is the actionable local
decision. `quality_gate_passed` remains `null` because the hidden gate cannot
be run locally. Other completion drift remains visible for diagnosis but is
blocking only for the ranked GPQA proxy; PPL changes are judged by the PPL
threshold rather than exact floating-point identity.

The small `quick` sample is good for detecting gross regressions but cannot
resolve a statistical 3% change precisely: one MMLU miss is five percentage
points. Use `standard` or `full` to adjudicate a borderline result.

## Behavioral gate

The public harness indicates that the hidden behavioral gate preserves
reference-model behavior rather than applying a generic safety classifier.
It combines exact teacher-forced tokens, hidden logit anchors, short exact
free-runs, and nine private GPQA prompts. A semantic judge compares candidate
GPQA responses with the pinned Laguna responses; the published floor is 7/9.

The private prompts and answers are unavailable. Locally, the evaluator uses
raw single-user prompts with BOS for its ranked GPQA arm and compares exact
responses with the baseline. This is useful evidence, not proof that the
hidden semantic gate passes.

## Outputs

Each run directory contains:

- `run.json`: artifact and host identities, profile, commands, timings,
  validity, public probe, and failures;
- `summary.json`: aggregate metrics;
- `responses.jsonl`: complete requests and responses;
- `pass_N/`: evaluator results, completions, PPL rows, and logs;
- `bridge.log`: Swift model-process diagnostics.

Evaluator output is also streamed to the terminal. Always set an explicit
`--output` path in automation; it must be new or empty.

## Other profiles and artifacts

The default `smoke` profile exercises every code path with two examples and
is only a plumbing check:

```bash
./senpai/quality-eval run .
```

`standard` is an intermediate panel. `full` defaults to five passes and can
take many hours on the serial endpoint:

```bash
./senpai/quality-eval run . \
  --profile full \
  --output quality-results/candidate-full
```

Select a subset by repeating `--suite`; valid names are `ppl`, `mmlu_pro`,
`gpqa_diamond`, `aime`, and `gsm8k`.

The positional artifact may be a challenge checkout or a prepared directory
containing `quality-artifact.json` with `weights`, `tokenizer`, `bridge`, and
`metallib` paths. Inspect discovery without loading the model:

```bash
./senpai/quality-eval inspect /path/to/checkout-or-bundle
```

For a checkout, `run` automatically refreshes transformed weights and builds
the candidate-linked bridge and Metal library when needed. The downstream
suites need Hugging Face dataset access; built-in PPL is self-contained.
Laguna holds about 21.6 GB of weights in memory, so do not overlap an
evaluation with another model-holding benchmark or evaluator process.
