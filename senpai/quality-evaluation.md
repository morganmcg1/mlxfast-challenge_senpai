# Laguna quality evaluation

`senpai/quality-eval` runs PPL, MMLU-Pro, GPQA-Diamond, AIME, and
GSM8K against the Laguna model built from a challenge checkout. It streams
progress and final metrics to stdout, then saves metrics, logs, prompts, and
raw responses under `quality-results/`.

This is a local regression gate, not the hidden challenge gate.
`evaluation_valid: true` means the selected evaluators completed consistently;
use `compare` for the local pass/fail decision.

## Agent workflow

Create a matched baseline before changing model or kernel code:

```bash
./setup.sh

./senpai/quality-eval run . \
  --profile quick \
  --output quality-results/baseline-quick
```

After an optimization:

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

`compare` exits with status 3 when the candidate fails. It rejects incompatible
runs before scoring: baseline and candidate must share the host, evaluator,
tokenizer, profile, prompts, PPL manifest, pass count, and prompt formats.

Do not overlap this command with another model-holding process. Laguna keeps
about 21.6 GB of weights resident.

## Quick profile and corrected baseline

`quick` is the routine 10–20 minute screen on the 128 GB development M4 Max:

- PPL: 8 records / 256 scored tokens
- MMLU-Pro: 20 questions
- GPQA-Diamond: 9 greedy, 9 sampled, and 9 ranked-behavior questions
- AIME: 3 problems
- GSM8K: 12 questions

The full-head multiple-choice arms use concise answer prompts and a 768-token
cap. AIME gets 1,024 tokens. Ranked GPQA deliberately uses the challenge-like
raw+BOS prompt and a 128-token cap.

The corrected full-model baseline is:

| Check | Baseline | Local gate |
| --- | ---: | ---: |
| Token-weighted PPL | 13.9549 | ≤ 14.3865 |
| MMLU-Pro | 9/20 (45.0%) | ≥ 43.65% (practically 9/20) |
| GPQA greedy | 6/9 (66.7%) | ≥ 64.67% (practically 6/9) |
| GPQA sampled | 6/9 (66.7%) | ≥ 64.67% (practically 6/9) |
| AIME | 1/3 (33.3%) | ≥ 32.33% (practically 1/3) |
| GSM8K | 12/12 (100%) | ≥ 97% (practically 12/12) |
| Ranked GPQA behavior | 9 saved 128-token prefixes | ≥ 7/9 exact baseline matches |
| Public first-token probe | 5991 | exact match |

This run completed in 17:04.9, or 17:25.9 including an incremental bridge
build, on a Mac16,6 M4 Max with macOS 26.5.2. It is stored locally at
`quality-results/baseline-quick-corrected-m4-20260730`. Evaluator provenance:
`f38b174557adb85d57401927780c60a4b904f20254cd939f417fdb586af3333e`;
editable source:
`a6b9b9f177b8f36c664fdf3df06341c3780a96c6a7309247cd92809bee1c21e9`.

The earlier PPL `262.0863` and all-zero accuracy table was invalid. A pre-NAX
M4 ran the generic MoE gather kernel, while Swift interpreted its output as
the packed NAX/M5 layout. That corrupted logits and produced repetitive,
truncated text. The runtime now gates the packed interpretation on the same
hardware, OS, and stage variant as the backend. The corrected runtime matches
the vendored model's greedy token behavior and the checked-in M5 probe.

Run a fresh baseline after changing the evaluator, tokenizer, OS/hardware, or
base source. Do not reuse the old
`quality-results/baseline-quick-final-m4-20260730` result.

## Local 97% gate

Each metric is independent; improvements in one suite cannot offset a
regression in another.

- Accuracy retention: `candidate / baseline >= 0.97`
- PPL retention: `baseline / candidate >= 0.97`
- Ranked GPQA behavior: at least 7/9 exact decoded-prefix matches in `quick`
- Public probe: exact baseline token
- Both runs: complete, valid, and contract-compatible

The small panel detects gross regressions, not a statistically precise 3%
change. One MMLU miss is five percentage points. Use `standard` or `full` for
a borderline result.

`comparison.json` contains per-metric thresholds and
`local_retention_gate_passed`. `quality_gate_passed` remains `null` because
the hidden gate is unavailable locally.

## What the behavioral gate likely means

The public harness shows a reference-behavior gate, not a generic safety
classifier. It combines teacher-forced token checks, hidden logit anchors,
short exact free-runs, and nine private GPQA prompts. A semantic judge compares
candidate GPQA answers with the pinned Laguna responses; the published floor is
7/9. The local ranked GPQA arm mirrors the raw+BOS request shape and budget,
then strictly compares decoded 128-token prefixes. It is a trajectory proxy,
not a substitute for the hidden prompts or semantic judge.

## Outputs and other profiles

Each result directory contains:

- `run.json`: artifact/host identities, commands, timings, validity, and probe
- `summary.json`: aggregate metrics
- `responses.jsonl`: requests and raw responses
- `pass_N/`: evaluator results and logs
- `bridge.log`: Swift model-process diagnostics

Always give automation a new `--output` path. `smoke` runs two examples per
suite to check plumbing. `standard` is larger; `full` defaults to five passes
and can take many hours:

```bash
./senpai/quality-eval run . --profile smoke
./senpai/quality-eval run . --profile full --output quality-results/full
```

Repeat `--suite` to select subsets. The positional artifact may be a checkout
or a prepared `quality-artifact.json` bundle. Inspect discovery without
loading the model:

```bash
./senpai/quality-eval inspect /path/to/checkout-or-bundle
```

Checkout runs refresh transformed weights and incrementally rebuild the bridge
and Metal library. Downstream suites require Hugging Face dataset access;
built-in PPL is self-contained.
