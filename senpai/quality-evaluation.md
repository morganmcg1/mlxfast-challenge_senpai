# Laguna Quality Evaluation

## Decision rule

Run `senpai/quality-eval` only for a named numerical or representation risk,
or to diagnose an observed mismatch. Typical triggers are quantization,
pruning, reduction order, activation math, dispatch/layout contracts, and the
output head.

A threshold `FAIL` is an amber drift alarm, not a submission veto. An invalid,
incomplete, interrupted, or incompatible evaluation is inconclusive. New
exact-reference, integrity, serial-protocol, teacher-forced correctness, or
upstream-equivalence divergence is a hard stop. Official M5 gates decide
acceptance.

## Matched run

Create the baseline before changing the candidate, then run the same profile
on the same host. Prerequisites are a completed `./setup.sh`, `uv` in `PATH`,
and network access for public datasets.

```bash
./senpai/quality-eval run . \
  --profile quick \
  --change-label untouched-baseline \
  --output quality-results/baseline-quick

./senpai/quality-eval run . \
  --profile quick \
  --change-label "describe-the-optimization" \
  --baseline quality-results/baseline-quick \
  --output quality-results/candidate-quick
```

Run only one model-holding command at a time.

A run with `--baseline` exits `0` on threshold pass and `3` on a completed
threshold fail. `compare` has the same semantics;
`compare --report-only` reports a fail without exit `3`. A bare run's `PASS`
means only that evaluation completed with valid outputs. Any other nonzero
exit is inconclusive, not a quality verdict.

Comparisons require the same host, evaluator, tokenizer, profile, prompt set,
selected suites, and pass count. Create a new baseline when any of these
changes.

## Alarm thresholds

The default `quick` profile scores 53 attempts: 20 MMLU-Pro, 9 GPQA greedy,
9 GPQA sampled, 9 AIME, and 6 GSM8K. Ranked GPQA behavior and token-weighted
PPL are separate checks.

Let `B` be the matched baseline's correct-answer count across the included
scoring suites and `C` the candidate count. The aggregate alarm is:

```text
C >= ceil(0.97 * B)
```

When PPL is included:

```text
candidate_ppl <= baseline_ppl / 0.97
```

The remaining default checks are:

- at least 7 of 9 ranked-GPQA decoded prefixes exactly match the baseline;
- the public first-token probe exactly matches the baseline; and
- both runs are complete, valid, and compatible.

Use repeated `--suite` only for a targeted diagnosis. Baseline and candidate
must use the same suite selection, and a subset does not replace the full
`quick` panel before M5 validation when this risk check is required.

Accepted-submission calibration found that this panel does not reproduce
official acceptance, so percentage tuning cannot turn it into a hard gate.
Evidence: [accepted-rank calibration](competition_notes/top15_replication_2026-08-02/QUALITY_CALIBRATION.md).

## M5 upstream-equivalence diagnostic

For risky math or dispatch changes on M5, compare the scored runtime with the
vendored Laguna model:

```bash
research/run_upstream_equivalence.sh
```

The wrapper uses the exact bare Swift Testing filter, repairs the debug
`mlx.metallib` placement from the scored worker build when needed, and fails
if the oracle report is absent. A zero-test invocation is not a pass. On a
non-M5 host, run the unchanged `BASE_SHA` too before attributing a prefill
divergence. This diagnostic supplements, but never replaces, local and
official gates.
