# Autoresearch Experiment Runbook

Load this file when starting, measuring, or promoting an experiment. The active
research policy remains in `program.md`; benchmark and submission contracts
remain in `AGENTS.md`, `TASK.md`, and `benchmark.json`.

## Start from the promoted frontier

Begin with a clean worktree. Normal sync selects the best promoted submission:

```bash
git status --short
mlxfast submissions --all
mlxfast sync
BASE_SHA="$(git rev-parse HEAD)"
```

Do not substitute `git pull origin main` for frontier selection. A remote branch
may contain orchestration work or lag the best promoted submission.

Do not use `--force`; normal `mlxfast sync` intentionally refuses a dirty
worktree. Preserve wanted work first. `mlxfast sync --harness-only` has a
different purpose: it refreshes tracked non-editable base and harness files
while preserving editable paths, so it does not select the promoted frontier.

Keep `BASE_SHA` immutable for the arm. If the frontier advances while work is
running, finish and report against the recorded SHA. Before promotion, preserve
the candidate, sync to the new frontier, reapply it, record the new SHA, and
remeasure.

## Prepare the host

Run setup once per host and whenever the toolchain, checkpoint, or harness
state changes:

```bash
./setup.sh
```

Setup builds the Swift tools and Metal library and downloads or verifies the
pinned checkpoint. The default setup needs at least 40 GiB of free disk. Use a
pre-provisioned exact checkpoint or documented cache path when appropriate;
never substitute another model revision.

## Record a matched baseline and candidate

On the unchanged frontier:

```bash
BASE_SHA="$(git rev-parse HEAD)"
./benchmark.sh --local-iterate
cp score.local-iterate.json score.local-iterate.baseline.json
```

After implementing one causal experiment:

```bash
swift test --force-resolved-versions
./benchmark.sh --local-iterate
cp score.local-iterate.json score.local-iterate.candidate.json
```

If the change touches live MLX runtime behavior and the host supports it, add:

```bash
MLXFAST_RUN_MLX_RUNTIME_TESTS=1 \
swift test --force-resolved-versions
```

Never overlap model-holding commands. Let the automatic thermal gate complete;
a cool-down wait is part of valid measurement.

## Extract the comparison

```bash
jq '{
  score,
  passed,
  runtime: .metrics.runtime,
  passed_correctness: .metrics.passed_correctness,
  decode_seconds_per_token: .metrics.decode_seconds_per_token,
  prefill_seconds_per_token: .metrics.prefill_seconds_per_token,
  decode_speedup: .metrics.decode_speedup,
  prefill_speedup: .metrics.prefill_speedup,
  peak_ram_gb: .metrics.peak_ram_gb,
  error: .metrics.error
}' \
  score.local-iterate.baseline.json \
  score.local-iterate.candidate.json
```

Local `score` and speedups use cached M5 calibration constants. For research,
compare candidate seconds/token with the freshly measured unchanged baseline on
the same host. Repeat the pair when the apparent gain is near the host's noise
floor.

These score files are ignored evidence and must never be committed:

- `score.local-*.json`
- `score*.baseline.json`
- `score.json`

## Inspect submitted and supporting changes

```bash
git status --short
git diff --name-only "$BASE_SHA"
git diff --stat "$BASE_SHA"
```

Separate the candidate's model/runtime diff from supporting tests and docs.
Every submitted candidate file must appear in `benchmark.json`'s
`editablePaths`. Supporting tests and docs are research-only and cannot be
required for the candidate to work or pass trusted validation.

For kernel changes, confirm that the runtime-effective JIT/AOT source and the
relevant `_nax` variant are covered. Rebuild AOT Metal sources through the
repository setup or metallib script as required by `AGENTS.md`.

## Stronger checks for promising or risky candidates

Run the longer local path for a promising candidate:

```bash
./benchmark.sh --local-submit
```

Use `senpai/quality-evaluation.md` when the risk-based trigger in `program.md`
applies. Its commands, thresholds, and exit semantics are authoritative; do not
copy them into an experiment prompt.

## Pre-promotion sequence

First check whether the promoted frontier moved:

```bash
mlxfast submissions --all
```

If it moved, preserve and reapply the candidate on a clean normal
`mlxfast sync`, then repeat the matched measurements. Once the candidate is on
the current frontier, refresh the trusted harness without replacing editable
paths and run the full local preflight:

```bash
mlxfast sync --harness-only
./setup.sh
swift test --force-resolved-versions
./benchmark.sh --local-submit
```

Inspect the final diff again. Only the advisor or human operator may dispatch
an official submission.

## Research search

For general web search:

```bash
python3 senpai/exa_search.py "query"
```

For research literature:

```bash
python3 senpai/exa_search.py "query" --category publication
```

The script reads `EXA_API_KEY` from the environment or `senpai/.env` and prints
the Exa response as JSON.
