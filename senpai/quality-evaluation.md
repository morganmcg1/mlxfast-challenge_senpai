# Laguna quality evaluation

`senpai/quality-eval` is a risk-based local regression panel for a modified
Laguna checkout or prepared artifact. Use it when a candidate changes numerical
behavior or representation—such as quantization, pruning, reduction order,
activation math, dispatch/layout contracts, or output-head behavior—or when an
observed mismatch needs diagnosis. It is not a routine requirement for a
scheduling or tiling change whose outputs are already shown equivalent.

It runs one deterministic evaluation trial, prints metrics and PASS/FAIL, and
saves prompts, responses, logs, provenance, and summaries under the selected
output directory.

This panel supplements the challenge's exact-token and hidden behavioral
gates; it does not replace them. Its threshold verdict is an amber drift alarm,
not an automatic M5 submission veto; see [Accepted-rank calibration](#accepted-rank-calibration).

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

## Matched workflow

When the risk-based trigger applies, create and retain a matched baseline before
changing model or kernel code. `quality-results/` is gitignored, so a fresh
checkout does not contain this baseline:

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

`run --baseline` and, by default, `compare` exit `0` on threshold PASS and `3`
on a completed threshold FAIL (`compare --report-only` suppresses exit `3`). A
bare `run` only reports `EVALUATION RUN: PASS`, meaning the evaluator completed
and produced valid outputs; it does not apply the retention gate. Other
nonzero exits mean the evaluation was invalid, incomplete, or interrupted.
Comparison rejects incompatible runs, including different hosts, evaluator
versions, tokenizers, profiles, prompt sets, or pass counts. Run only one
model-holding command at a time; Laguna keeps about 21.6 GB resident.

## Quick panel

The `quick` profile is the bounded regression panel:

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

## Local comparison thresholds

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

The downstream threshold retains at least 97% of the baseline aggregate:

```text
candidate_overall_score >= 0.97 * baseline_overall_score
candidate_correct >= ceil(0.97 * baseline_correct)
```

For example, a baseline score of `10.0` requires `9.7` or higher; `9.6`
fails. Correct answers may move between datasets because only the summed
53-question result is compared.

PPL is checked separately:

```text
candidate_ppl <= baseline_ppl / 0.97
```

The remaining comparison checks are:

- ranked GPQA behavior: at least 7 of 9 decoded prefixes exactly match the
  matched baseline;
- public first-token probe: exact match;
- both runs: complete, valid, and contract-compatible.

These thresholds detect local drift; a FAIL is not proof of official failure.
The official challenge correctness and behavioral gates remain authoritative.

## Accepted-rank calibration

The frozen ranks 112–126 study evaluated all 15 officially accepted snapshots
against the July-30 M4 baseline. Eleven produced formal comparisons and all 11
failed this composite; four length-bounded AIME runs abstained. The only
formally comparable selected official-failure control scored at least as well
as accepted ranks 120–126 on every declared component. Therefore no monotone
adjustment of `97%`, the PPL allowance, or prefix count can make this feature
set reproduce official acceptance.

Operationally:

- keep the existing thresholds as conservative amber alarms;
- use a fresh matched same-host current-frontier baseline for new work (rank
  126 until superseded), not the old cumulative July-30 baseline;
- treat invalid, incompatible, or length-bounded runs as abstentions;
- hard-stop only new exact matched-reference, integrity, protocol,
  upstream-equivalence, or teacher-forced correctness failures; and
- send investigated amber candidates to M5 validation, whose hidden gates are
  authoritative.

The evidence, accepted/control measurements, and next calibration work are in
[`competition_notes/top15_replication_2026-08-02/QUALITY_CALIBRATION.md`](competition_notes/top15_replication_2026-08-02/QUALITY_CALIBRATION.md).

## Historical July-30 reference values

The table below records the untouched Laguna baseline for the frozen
20/9/9/9/6 panel. These absolute values are historical evidence, not thresholds
for new candidates; derive new thresholds from the fresh matched
current-frontier baseline.

| Check | July-30 baseline | Historical threshold |
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
These are reference values, not universal cross-host constants: the operative
gate comes from the contract-compatible baseline supplied to the comparison.
Do not compare against a different host, prompt manifest, or evaluator SHA.

## Faster iteration subset

For a roughly 13-minute edit-loop check on this Mac, use PPL plus MMLU-Pro,
AIME, and GSM8K. It scores 35 attempts and omits the GPQA behavior check.
Create a separate matched subset baseline, then derive
`ceil(0.97 * baseline_correct)` and `baseline_ppl / 0.97` from that artifact.
The old July-30 full-panel components happened to imply `16/35` and PPL
`<=14.386452`; those are examples, not reusable current-frontier limits. Pass
the matched subset artifact with `--baseline` (the full baseline is contract-
incompatible with this subset):

```bash
# Once, before modifying the model:
./senpai/quality-eval run . \
  --profile quick \
  --suite ppl --suite mmlu_pro --suite aime --suite gsm8k \
  --output quality-results/baseline-quick-core

# After each selected risk-bearing candidate:
./senpai/quality-eval run . \
  --profile quick \
  --suite ppl --suite mmlu_pro --suite aime --suite gsm8k \
  --baseline quality-results/baseline-quick-core \
  --output quality-results/candidate-quick-core
```

Use the full 53-attempt panel before M5 validation of a candidate for which
this risk-based panel is required.

## Upstream-equivalence diagnostic

For risky math or dispatch changes on M5, the opt-in upstream-equivalence test
compares the scored runtime with the vendored `MLXLLM.LagunaModel` for one
512-token prefill and eight serial teacher-forced decode steps:

```bash
MLXFAST_RUN_LAGUNA_UPSTREAM_EQUIVALENCE=1 \
MLXFAST_LAGUNA_EQUIVALENCE_WEIGHTS_PATH=weights \
swift test --force-resolved-versions \
  --filter lagunaRuntimeMatchesVendoredUpstreamOnM5WhenEnabled
```

Use it as a diagnostic, not as a replacement for the local or official gates.

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
