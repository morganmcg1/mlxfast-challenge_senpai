# Laguna quality evaluation

`senpai/quality-eval` runs PPL, MMLU-Pro, GPQA-Diamond, AIME, and GSM8K
against a Laguna checkout or artifact. It prints progress and saves all metrics,
prompts, and responses. This is a local regression gate; `compare` decides
pass/fail.

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

`compare` exits 3 on failure and rejects unmatched hosts, evaluator versions,
tokenizers, profiles, prompts, or pass counts. Run only one model-holding
command at a time; Laguna keeps about 21.6 GB resident.

## Quick profile

`quick` is the routine 10–20 minute screen on the 128 GB development M4 Max:

- PPL: 8 records / 256 scored tokens
- MMLU-Pro: 20 questions
- GPQA-Diamond: 9 greedy, 9 sampled, and 9 ranked-behavior questions
- AIME: 3 problems
- GSM8K: 12 questions

Question IDs are frozen under `senpai/quality_eval/manifests/`. GPQA has
balanced gold positions and uses `temperature=0.5`; GSM8K mixes nine baseline
passes with three completed misses.

Full-head quality answers get 1,024 tokens; AIME gets 2,048. A run is invalid
if any of these answers reaches its cap. Ranked GPQA deliberately keeps the
challenge-shaped raw+BOS prompt and 128-token cap.

## Challenge token contract

`task.md` does not define one general answer-token limit. The trusted constants
set:

- hidden behavior/GPQA: at most 2,048 prompt tokens and 128 generated tokens;
- hidden free-run fixtures: at most 256 generated tokens;
- base correctness: 512 prompt tokens plus 64 teacher-forced checks;
- timed decode: a 512-token seed plus 128 teacher-forced steps, not an answer
  budget.

Thus `quick` meets or exceeds the answer budget while preserving a separate
exact 128-token behavioral proxy. Longer quality budgets avoid scoring partial
answers; they do not force the model to consume the full allowance.

## Untouched baseline and local gates

The corrected full-model baseline is:

| Check | Baseline | Local gate |
| --- | ---: | ---: |
| Token-weighted PPL | 13.9549 | ≤ 14.3865 |
| MMLU-Pro | 9/20 (45.0%) | ≥ 43.65% (practically 9/20) |
| GPQA greedy | 6/9 (66.7%) | ≥ 64.67% (practically 6/9) |
| GPQA sampled | 4/9 (44.4%) | ≥ 43.11% (practically 4/9) |
| AIME | 1/3 (33.3%) | ≥ 32.33% (practically 1/3) |
| GSM8K | 9/12 (75.0%) | ≥ 72.75% (practically 9/12) |
| Ranked GPQA behavior | 9 saved 128-token prefixes | ≥ 7/9 exact baseline matches |
| Public first-token probe | 5991 | exact match |

This Mac16,6 M4 Max run took 19:31 (19:41 including preparation) and is stored
at `quality-results/baseline-quick-final-v2-m4-20260730`. Evaluator provenance:
`bdd7b44304868507bac071612fcf94eb7de1533cc6213d46221d1897ca261bc0`; source:
`a6b9b9f177b8f36c664fdf3df06341c3780a96c6a7309247cd92809bee1c21e9`.

The old PPL `262.0863`/all-zero table was invalid: a pre-NAX M4 output-layout
mismatch corrupted the MoE logits. The corrected runtime matches the vendored
model and checked-in M5 probe. See
[`program.md`](program.md#pre-nax-moe-output-layout-compatibility) for the two
layouts, fixed dispatch predicate, affected-host fingerprint, and diagnostics.

Run a fresh baseline after changing the evaluator, tokenizer, OS/hardware, or
base source.

Each metric is independent; improvements in one suite cannot offset a
regression in another.

- Accuracy retention: `candidate / baseline >= 0.97`
- PPL retention: `baseline / candidate >= 0.97`
- Ranked GPQA behavior: at least 7/9 exact decoded-prefix matches in `quick`
- Public probe: exact baseline token
- Both runs: complete, valid, and contract-compatible

The panel is count-sensitive: each practical accuracy gate retains every
current correct answer. `comparison.json` reports
`local_retention_gate_passed`; the hidden `quality_gate_passed` stays `null`.

## What the behavioral gate likely means

The public harness describes reference behavior, not a generic safety
classifier: teacher-forced token checks, hidden logit anchors, short free-runs,
and nine private GPQA prompts. A semantic judge compares answers with pinned
Laguna responses. The local ranked arm mirrors the raw+BOS shape and 128-token
budget, then compares decoded prefixes; hidden prompts and judging remain
official-only.

## Outputs and variants

Each result has `run.json`, `summary.json`, `responses.jsonl`, per-suite logs,
and bridge diagnostics. Always use a new `--output` path. `smoke` checks
plumbing; `standard` is larger; `full` defaults to five long passes. Repeat
`--suite` for subsets. Inspect a checkout or `quality-artifact.json` bundle
without loading it:

```bash
./senpai/quality-eval inspect /path/to/checkout-or-bundle
```

Downstream suites need Hugging Face access; built-in PPL is self-contained.
