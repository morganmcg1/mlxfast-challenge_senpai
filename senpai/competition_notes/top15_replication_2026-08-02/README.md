# Fastest-15 local replication study

This directory defines the reproducible local study for leaderboard ranks
112–126, the 15 fastest promoted submissions in the 2026-08-02 snapshot. The
exact UUIDs, promoted commits, official measurements, and mechanism summaries
are frozen in `candidates.json`.

## Experimental contract

- Host: Apple M4 Max, 128 GB (`Mac16,6`), not the official M5 Max runner.
- Harness: the common rank-126 harness at `7702fab`; each candidate is restored
  exactly over the 97 participant-editable paths, matching submission overlay
  semantics.
- Local performance comparator: rank 111 (`0682cc25`, `af08576`), the exact
  promoted parent of rank 112. Local phase speedups are computed from this
  same-contract, same-Mac comparator's absolute seconds/token.
- Official score context: the organizer's pinned calibration source and M5
  constants remain in `official_pinned_baseline`. That July source cannot be
  restored wholesale over the August harness because later unrelated Gemma/MTP
  interfaces do not compile against it; it is not used as the local executable
  comparator.
- Performance mode: full `--local-submit` (1,025 checked tokens, 1,023 decode
  steps), correctness-strict by default, one model process at a time, behind the
  repository's 40 °C GPU gate.
- Quality mode: the complete one-pass `quick` profile: 53 downstream attempts,
  nine ranked-GPQA behavior prefixes, 256 PPL target tokens, and the 512-token
  public first-token probe.
- Quality baseline: `baseline-quick-weave-v3-m4-20260730`, with 26/53 correct
  and PPL 13.954858. The nominal 3% retention floor is discrete here: at least
  26/53 correct, PPL no worse than 14.386452, at least 7/9 ranked-GPQA prefix
  matches, and an exact public probe.

## M4 compatibility boundary

All 15 historical snapshots predate the architecture-aware expert-gather
layout predicate. On this pre-NAX M4, their default-on M5 path misinterprets a
generic 1,024-wide result as a packed 512-wide result. Every performance arm
therefore sets only `DARKBLOOM_EXPERT_ALIGNED_GATHER=0`.

The quality evaluator intentionally strips all inherited `DARKBLOOM_*`
variables. `quality-bridge-wrapper.sh` restores only that layout selector after
sanitization, preserves the evaluator's full/ranked LM-head choice, unsets its
launcher variable, and executes the real candidate bridge. The evaluator
provenance remains byte-identical to the baseline. Each arm separately retains
and hashes the real bridge binary and its source fingerprint; `run.json` hashes
the transparent wrapper.

These measurements are M4 transfer results, not literal reproductions of M5
kernel scheduling. Architecture-sensitive rank inversions are evidence, not
necessarily replication failures.

## Runner and evidence

```bash
senpai/competition_notes/top15_replication_2026-08-02/run-study.sh prepare
senpai/competition_notes/top15_replication_2026-08-02/run-study.sh perf baseline
senpai/competition_notes/top15_replication_2026-08-02/run-study.sh perf all
senpai/competition_notes/top15_replication_2026-08-02/run-study.sh quality all
senpai/competition_notes/top15_replication_2026-08-02/run-study.sh status
```

The runner uses one owned, ignored rolling workspace and shared transformed
weights. Every arm has a frozen `run-spec.json`. Performance attempts retain
their log, score, benchmark-integrity record, exit status, hashes, and selected
attempt. Quality attempts retain the full evaluator output, comparison, real
bridge, source fingerprint, launcher identity, and selected attempt. Invalid
network/infrastructure attempts are preserved and retried in a fresh directory;
a valid exit 3 is retained as quality-regression data.

### Negative-control quality cohort

`negative-controls.json` records three known official behavior failures and
their public evidence. `control-run.json` freezes numeric control ranks
201–203, the exact source commits, the same harness/evaluator/baseline/host
contract as the primary study, and the SHA-256 of that control definition.
Performance is disabled for this cohort because it calibrates only the local
quality surrogate.

The wrapper forces a separate owned workspace and results tree while reusing
the runner's quality path unchanged: manifest-bound arm specifications, bridge
and evaluator fingerprints, retries, bounded AIME non-completion markers, and
the evaluator's shared per-user one-model-at-a-time lock.

```bash
senpai/competition_notes/top15_replication_2026-08-02/run-quality-controls.sh prepare
senpai/competition_notes/top15_replication_2026-08-02/run-quality-controls.sh quality all
senpai/competition_notes/top15_replication_2026-08-02/run-quality-controls.sh quality 201
senpai/competition_notes/top15_replication_2026-08-02/run-quality-controls.sh quality e40e4013
senpai/competition_notes/top15_replication_2026-08-02/run-quality-controls.sh status
```

The commands above define the future execution path; their presence does not
mean the controls have been run. Default control artifacts live under
`quality-results/leaderboard-top15-controls-20260802`, with the rolling checkout
at `quality-results/.top15-workspace-controls-20260802`.

The quick profile has a fixed 2,048-token AIME response ceiling. If every
evaluator command succeeds and every expected artifact is complete, but one or
more AIME responses ends at that ceiling, the evaluator correctly refuses to
produce a formal comparison. The runner records this once as a provenance- and
hash-bound `terminal-noncompletion.json`. Such an arm is **processed but not
formally comparable**: it gets no `selected-attempt.txt`, no local 3% gate
decision, and its raw 53-item vector is diagnostic only. Network, build,
missing-artifact, and other invalid failures remain retryable.

After all required arms are processed, representative AIME length cases are
rerun with an extended response limit as separate diagnostics. Those runs test
whether the fixed ceiling, rather than a model/runtime failure, caused the
non-completion; they do not retroactively turn the frozen quick-profile result
into a valid comparison.

## Inference limit

All 15 candidates are official successes. They can show that the local gate is
too strict or differently targeted when an official success fails locally.
They cannot prove that the local gate is too loose. After the required 15 are
complete, rejected correctness/quality controls should be added where public
source snapshots exist; conclusions must distinguish exact-prefix local checks
from the private semantic GPQA and hidden-token gates.
