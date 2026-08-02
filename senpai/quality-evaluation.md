# Laguna quality evaluation

`senpai/quality-eval` is the local regression gate for a modified Laguna
checkout or prepared artifact. It runs one deterministic evaluation trial,
prints metrics and PASS/FAIL, and saves prompts, responses, logs, provenance,
and summaries under the selected output directory.

This panel supplements the challenge's exact-token and hidden behavioral
gates; it does not replace them.

## First-time setup

From the repository root:

```bash
# Downloads/verifies the 21.6 GB checkpoint and builds the Swift/Metal runtime.
./setup.sh

# Required by senpai/quality-eval; setup.sh does not install it.
brew install uv
```

If `uv --version` already succeeds, skip the Homebrew command. The first
`senpai/quality-eval` invocation creates the locked Python environment and
fetches the public evaluation data automatically; no dataset path or Hugging
Face token is required. Outbound internet access is required: MMLU-Pro and
GPQA use their normal caches, while AIME and GSM8K read the Hugging Face
datasets server on each run.

## Routine workflow

Create and retain a matched baseline on untouched `main` before changing model
or kernel code. `quality-results/` is gitignored, so a fresh checkout does not
contain this baseline:

```bash
./setup.sh

./senpai/quality-eval run . \
  --profile quick \
  --change-label untouched-baseline \
  --output quality-results/baseline-quick
```

Run the same panel after the change, then compare:

```bash
./senpai/quality-eval run . \
  --profile quick \
  --change-label "describe-the-optimization" \
  --baseline quality-results/baseline-quick \
  --output quality-results/candidate-quick
```

`run --baseline` and, by default, `compare` exit `0` on quality PASS and `3`
on a completed quality FAIL (`compare --report-only` suppresses exit `3`). A
bare `run` only reports `EVALUATION RUN: PASS`, meaning the evaluator completed
and produced valid outputs; it does not apply the retention gate. Other
nonzero exits mean the evaluation was invalid, incomplete, or interrupted.
Comparison rejects incompatible runs, including different hosts, evaluator
versions, tokenizers, profiles, prompt sets, or pass counts. Run only one
model-holding command at a time; Laguna keeps about 21.6 GB resident.

## Quick panel

The `quick` profile is the routine bounded screen:

| Component | Questions | Included in overall score |
| --- | ---: | :---: |
| MMLU-Pro greedy | 20 | yes |
| GPQA-Diamond greedy | 9 | yes |
| GPQA-Diamond sampled | 9 | yes |
| AIME | 9 | yes |
| GSM8K | 6 | yes |
| GPQA-Diamond ranked behavior | 9 | no |
| Token-weighted PPL | 256 scored tokens | no |

The scoring panel therefore contains 53 question attempts. Ranked GPQA is a
separate behavior-path check, and PPL is a separate lower-is-better metric.
Individual dataset accuracies are printed for diagnosis but do not gate
independently.

Normal quality answers get up to 1,024 generated tokens; AIME gets 2,048.
Reaching either cap invalidates the run. Ranked GPQA preserves the challenge-
shaped raw+BOS prompt and 128-token generation cap.

## Determinism and reproducibility

Question IDs, few-shot examples, prompt formats, and sampling seeds are frozen
in `senpai/quality_eval/manifests/`; exact prompt membership and content are
validated by hashes. There is no random question selection. Weave evaluation
parallelism is one so the single Laguna model is evaluated serially.

Always compare runs made with the same:

- checkout base, tokenizer, evaluator version, and profile;
- host and OS;
- explicit suite selection and pass count;
- frozen prompt contract.

Create a fresh baseline after any of those inputs changes.

## Local gates

Let:

```text
overall_score = (
    MMLU correct
  + GPQA greedy correct
  + GPQA sampled correct
  + AIME correct
  + GSM8K correct
) / 53
```

The downstream gate retains at least 97% of the baseline aggregate:

```text
candidate_overall_score >= 0.97 * baseline_overall_score
candidate_correct >= ceil(0.97 * baseline_correct)
```

For example, a baseline score of `10.0` requires `9.7` or higher; `9.6`
fails. Correct answers may move between datasets because only the summed
53-question result gates.

PPL is checked separately:

```text
candidate_ppl <= baseline_ppl / 0.97
```

The remaining hard local checks are:

- ranked GPQA behavior: at least 7 of 9 decoded prefixes exactly match the
  matched baseline;
- public first-token probe: exact match;
- both runs: complete, valid, and contract-compatible.

The official challenge correctness and behavioral gates remain authoritative.

## Baseline gate values

Untouched Laguna baseline for the frozen 20/9/9/9/6 panel:

| Check | Untouched baseline | Candidate gate |
| --- | ---: | ---: |
| MMLU-Pro greedy | 9/20 | monitor only |
| GPQA-Diamond greedy | 6/9 | monitor only |
| GPQA-Diamond sampled | 4/9 | monitor only |
| AIME | 4/9 | monitor only |
| GSM8K | 3/6 | monitor only |
| Overall downstream | 26/53 (49.06%) | ≥26/53 |
| Token-weighted PPL | 13.954858 | ≤14.386452 |
| Ranked GPQA behavior | 9 saved prefixes | at least 7/9 exact matches |
| Public first-token probe | token 5991 | exact match |

The one-trial Mac16,6 M4 Max run took 24:59 and is saved at
`quality-results/baseline-quick-weave-v3-m4-20260730`. Evaluator SHA:
`647af7530d7c9bf88801fd92146439fdba5f75407bbee6a363b1a3ede1c90150`.
Do not compare against a different prompt manifest or evaluator SHA.

## Faster iteration subset

For a roughly 13-minute edit-loop check on this Mac, use PPL plus MMLU-Pro,
AIME, and GSM8K. It scores 35 attempts and omits the GPQA behavior check.
The full-panel components imply an expected untouched aggregate of `16/35`,
so the integer 97% gate still requires `16/35`; verify this when creating the
subset baseline. PPL remains at most `14.386452`. Create a separate matched
subset baseline, then pass it with `--baseline` (the full baseline is contract-
incompatible with this subset):

```bash
# Once, before modifying the model:
./senpai/quality-eval run . \
  --profile quick \
  --suite ppl --suite mmlu_pro --suite aime --suite gsm8k \
  --output quality-results/baseline-quick-core

# After each candidate change:
./senpai/quality-eval run . \
  --profile quick \
  --suite ppl --suite mmlu_pro --suite aime --suite gsm8k \
  --baseline quality-results/baseline-quick-core \
  --output quality-results/candidate-quick-core
```

Use the full 53-attempt panel before submission.

## Weave logging

The CLI uses a
[W&B Weave Evaluation](https://docs.wandb.ai/weave/guides/core-types/evaluations)
with one trial. Without `--weave-project`, it runs the same evaluation locally
with tracing disabled while still writing all local artifacts.

To log the evaluation to Weave:

```bash
./senpai/quality-eval run . \
  --profile quick \
  --weave-project ENTITY/PROJECT \
  --change-label "optimization-name" \
  --attribute experiment=laguna-decode \
  --attribute hypothesis="short description" \
  --output quality-results/candidate-quick
```

The evaluation records the git commit and dirty state, source and artifact
hashes, profile, run ID, host identity, change label, and supplied
`--attribute KEY=VALUE` metadata. Authentication follows the normal W&B
environment/login configuration. See
[Weave attributes](https://docs.wandb.ai/weave/guides/tools/attributes).

## Outputs and other commands

Each run saves `run.json`, `summary.json`, `responses.jsonl`, per-suite result
files and logs, bridge diagnostics, and Weave evaluation summaries. The
terminal prints each dataset result, the overall downstream score, PPL, and
the final run or comparison status.

Always use a new `--output` directory. Repeat `--suite` to run a deterministic
subset. `smoke` only checks plumbing; `standard` and `full` are larger panels.
All profiles run one trial unless `--passes` is explicitly set.

Inspect a checkout or `quality-artifact.json` bundle without loading it:

```bash
./senpai/quality-eval inspect /path/to/checkout-or-bundle
```

A portable bundle is a directory containing `quality-artifact.json` plus the
referenced files. Paths are relative to the bundle directory:

```json
{
  "weights": "weights",
  "tokenizer": "tokenizer",
  "bridge": "bin/laguna-quality-bridge",
  "metallib": "lib/mlx.metallib"
}
```

Pass the bundle directory, not the JSON file, to `inspect`, `serve`, or `run`.

Downstream suites need Hugging Face access; built-in PPL is self-contained.
