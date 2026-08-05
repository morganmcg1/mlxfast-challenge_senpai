# Autoresearch Experiment Runbook

Use this file to start, measure, and promote an experiment. `program.md` owns
research policy; `benchmark.json` owns the submitted surface.

## Start from the promoted frontier

This repository is a fork:

- `origin` is the research fork.
- `upstream` is the organizer repository.
- fork `main` is the maintained research frontier: organizer updates plus the
  best promoted editable-path state.

The advisor, acting as fork maintainer, updates fork `main` before a research
round:

1. Fetch `origin/main` and `upstream/main`.
2. Use `mlxfast submissions --all` to identify and record the current promoted
   organizer commit as `ORGANIZER_FRONTIER_SHA`.
3. In an integration branch based on `origin/main`, cherry-pick only reviewed
   organizer rule or contract commits. Skip bot validation commits and merge
   wrappers.
4. Restore all `benchmark.json` `editablePaths` from
   `ORGANIZER_FRONTIER_SHA` as one snapshot. Submission commits are deltas
   between unrelated solver trees; do not replay them individually.
5. Reapply required fork compatibility fixes, review and test the combined
   tree, then merge it into fork `main`.

Do not run either `mlxfast sync` mode on fork `main` or a research branch.
Normal sync hard-resets to the organizer tip; harness-only sync replaces tracked
non-editable files and can overwrite fork-owned research files.

Advisors and students branch from the same clean fork-main commit:

```bash
git fetch origin main
git switch main
git pull --ff-only origin main
BASE_SHA="$(git rev-parse HEAD)"
RESEARCH_BRANCH="codex/short-topic"
git switch -c "$RESEARCH_BRANCH" "$BASE_SHA"
```

Record `ORGANIZER_FRONTIER_SHA` and `BASE_SHA` in the result. Keep `BASE_SHA`
fixed for the experiment. If `origin/main` advances, finish the current
measurement against its recorded base. Reapply and remeasure a promising
candidate before promotion.

Before assigning work, copy [`assignment-template.md`](assignment-template.md),
list every proposed submitted path, and validate the committed base contract:

```bash
senpai/validate-assignment-scope.sh "$BASE_SHA" PATH [PATH ...]
senpai/check-editable-budget.sh "$BASE_SHA"
```

The assignment must identify how its control reaches the scored shape and who
owns official dispatch. Research-only paths are listed separately and are not
passed to the scope validator.

Run `./setup.sh` when the host, toolchain, checkpoint, or maintained base
changes.

## Record a matched baseline and candidate

Measure the unchanged `BASE_SHA` on the assigned host:

```bash
./benchmark.sh --local-iterate
cp score.local-iterate.json score.local-iterate.baseline.json
```

Implement one causal experiment, then measure it under the same host and
thermal policy:

```bash
./benchmark.sh --local-iterate
cp score.local-iterate.json score.local-iterate.candidate.json
```

Do not overlap model-holding commands. Let the thermal gate finish. Add only a
targeted compile, test, or diagnostic that can resolve a named risk. Repeat the
pair only when noise or inconsistency could change the decision.

## Extract the comparison

```bash
jq -s '
  .[0] as $b | .[1] as $c |
  ($b.metrics.decode_seconds_per_token /
    $c.metrics.decode_seconds_per_token) as $d |
  ($b.metrics.prefill_seconds_per_token /
    $c.metrics.prefill_seconds_per_token) as $p |
  {
    baseline: {
      decode: $b.metrics.decode_seconds_per_token,
      prefill: $b.metrics.prefill_seconds_per_token
    },
    candidate: {
      decode: $c.metrics.decode_seconds_per_token,
      prefill: $c.metrics.prefill_seconds_per_token,
      passed_correctness: $c.metrics.passed_correctness,
      error: $c.metrics.error
    },
    same_host: {
      decode_gain: $d,
      prefill_gain: $p,
      paired_estimate: (pow($d; 0.75) * pow($p; 0.25))
    }
  }
' score.local-iterate.baseline.json score.local-iterate.candidate.json
```

Use the fresh same-host seconds/token comparison for research decisions. Local
`score` and `*_speedup` fields use cached M5 calibration and are secondary.
The paired estimate is not an official score.

Use `--local-iterate` for causal timing. `--local-submit` is the longer final
packaging/correctness gate and can dilute a seed-forward improvement across its
1023 decode steps.

Score files are ignored evidence and must not be committed:

- `score.local-*.json`
- `score*.baseline.json`
- `score.json`

## Inspect the candidate

```bash
git status --short
git diff --name-only "$BASE_SHA"
git diff --stat "$BASE_SHA"
senpai/check-editable-budget.sh "$BASE_SHA"
```

Separate submitted model/runtime changes from research-only tests and docs.
Every submitted file must be in `benchmark.json`'s `editablePaths`. For kernel
changes, cover the runtime-effective JIT or AOT source and relevant `_nax`
variant as described in `AGENTS.md`.

After committing the candidate, run the same base-derived check used by the
trusted workflow:

```bash
BASE_SHA="$BASE_SHA" HEAD_SHA="$(git rev-parse HEAD)" \
  .github/scripts/enforce-modifiable-surface.sh
```

For numerical, representation, dispatch, or layout changes, run
`research/run_upstream_equivalence.sh`. It uses the exact bare Swift Testing
filter and fails if no oracle report was produced; zero selected tests is not
validation.

## Confirm and promote

For a stable winner:

```bash
swift test --force-resolved-versions
./benchmark.sh --local-submit
```

Apply `quality-evaluation.md` only when its risk trigger is present. Before
promotion, commit the candidate, update from `origin/main`, reapply that exact
commit if the base moved, rerun the matched comparison, and inspect the final
diff. An authorized advisor, student, or human operator may dispatch an
official submission while coordinating through the campaign's official queue.
An authorized campaign role may submit from a provisioned AWS host without
printing or committing its credentials.

Submit every official Senpai entry with the campaign attribution first:

```bash
mlxfast submit --model "senpai" --note-file submission-note.md
```

This campaign-specific rule overrides generic `mlxfast` model-name guidance.
Only when the API explicitly says that `senpai` is an invalid or unsupported
model value may the same candidate be retried once as follows, with the exact
rejection and fallback fact recorded in the note:

```bash
mlxfast submit --model "<actual-provider/model>" --note-file submission-note.md
```

Do not use the fallback for a timeout, network failure, validation failure, or
unrelated error because the first request may already have created a
submission. Do not otherwise copy the underlying provider/model into notes or
campaign metadata.

An official `rejected` status can be ranking-only. Inspect `error`,
`passed_correctness`, the hidden-gate fields, and both component-floor verdicts
before classifying the mechanism. A byte-identical editable archive is deduped
as an existing submission: tests, docs, or research notes outside
`editablePaths` do not create a new candidate. Poll with `mlxfast submissions`
and honor retry guidance; never call `mlxfast submit` merely to check status.

## Research search

```bash
python3 senpai/exa_search.py "query" [--category publication]
```

The script reads `EXA_API_KEY` from the environment or `senpai/.env`.
