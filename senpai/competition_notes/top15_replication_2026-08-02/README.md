# Fastest-15 local replication study

This directory defines the reproducible local study for leaderboard ranks
112–126, the 15 fastest promoted submissions in the 2026-08-02 snapshot. The
exact UUIDs, promoted commits, official measurements, and mechanism summaries
are frozen in `candidates.json`.

## Experimental contract

- Host: Apple M4 Max, 128 GB (`Mac16,6`), not the official M5 Max runner.
- Harness: the common rank-126 harness at
  `7702fab8a41fe2f4ff2ae281beeb1548b31e3406`; each candidate is restored
  exactly over the 97 participant-editable paths, matching submission overlay
  semantics.
- Local performance comparator: rank 111, submission
  `0682cc25-40a1-4f0e-bb96-c3b0f768b53c` at source
  `af085760e96a5d719a2ba9c5817454158d9edb86`, the exact promoted parent of
  rank 112. Local phase speedups are computed from this same-contract, same-Mac
  comparator's absolute seconds/token.
- Official score context: the organizer's pinned calibration source and M5
  constants remain in `official_pinned_baseline`. That July source cannot be
  restored wholesale over the August harness because later unrelated Gemma/MTP
  interfaces do not compile against it; it is not used as the local executable
  comparator.
- Performance mode: full local `--local-submit` (1,025 checked tokens, 1,023
  decode steps), correctness-strict by default, one model process at a time,
  behind the repository's 40 °C GPU gate. This is a directional M4 transfer
  measurement, not a direct reproduction of the private official run.
- Quality mode: the complete one-pass `quick` profile: 53 downstream attempts,
  nine ranked-GPQA behavior prefixes, 256 PPL target tokens, and the 512-token
  public first-token probe.
- Quality baseline: `baseline-quick-weave-v3-m4-20260730`, a clean checkout at
  `eec3f82c9adebc99e3ed15c74138e1ab8032d9cd` with editable-source SHA-256
  `a6b9b9f177b8f36c664fdf3df06341c3780a96c6a7309247cd92809bee1c21e9`
  and transform-source SHA-256
  `5929dfd16cedf35645e5a2bab62baa06ae4908382eae16917f1594bafb3715ec`.
  It is neither rank 111 nor rank 126. It records 26/53 correct and PPL
  13.954858.
- Composite local quality decision: exact row-set agreement is a comparability
  prerequisite; a retain then requires both 3% numeric terms (at least 26/53
  correct and PPL no worse than 14.386452), at least 7/9 ranked-GPQA prefix
  matches, and the exact public first token. The 3% label alone is incomplete.

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

The control cohort is complete for the frozen quick-profile contract: **3/3
processed, with one formal local regression, two hash-bound bounded AIME
non-completions, zero pending, and zero invalid**. Default control artifacts
live under `quality-results/leaderboard-top15-controls-20260802`, with the
rolling checkout at `quality-results/.top15-workspace-controls-20260802`.

The quick profile has a fixed 2,048-token AIME response ceiling. If every
evaluator command succeeds and every expected artifact is complete, but one or
more AIME responses ends at that ceiling, the evaluator correctly refuses to
produce a formal comparison. The runner records this once as a provenance- and
hash-bound `terminal-noncompletion.json`. Such an arm is **processed but not
formally comparable**: it gets no `selected-attempt.txt`, no composite local
gate decision, and its raw 53-item vector is diagnostic only. Network, build,
missing-artifact, and other invalid failures remain retryable.

The four successful primary snapshots that stopped on `2024-2024-II-2` were
also rerun with a 6,144-token ceiling as separate diagnostics. All four remained
length-bounded. Known-failing control 203 stopped on that same item at 2,048
tokens, but no rejected control was included in the extended cohort. These
one-class-only diagnostics do not retroactively turn the frozen quick-profile
result into a valid comparison or establish class separation.

## Inference limit

The observed calibration is:

| Frozen official label | Local regression | Local retain | No formal decision |
|---|---:|---:|---:|
| Success, ranks 112–126 | 11 | 0 | 4 |
| Failure, controls 201–203 | 1 | 0 | 2 |

Decision coverage is 11/15 for successes and 1/3 for selected failures; all 12
formal arms reject. Control 202 is at least as strong as successful ranks
120–126 on every predeclared component, so monotone threshold tuning cannot
separate them. This decisively makes the current composite unsuitable as an M5
submission veto for this cohort. It does **not** identify a replacement
threshold or reveal private-gate strictness.

The 11 formal successes belong to a connected promotion lineage and collapse
to three metric signatures, so they are not independent trials. The controls
were deliberately selected, six of 18 total arms are censored by AIME length,
and one pass per arm provides no variance estimate. Treat the local 3%
semantic/PPL suite as advisory. Use matched-reference exact public trajectory,
upstream-equivalence, and correctness traces as hard local evidence, with the
official M5 hidden gates as final authority. A rank-111 quality arm is still
needed to locate inherited drift, and rank 126 should become the same-host
incremental quality baseline for autoresearch.
