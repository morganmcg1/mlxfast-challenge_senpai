# Extended AIME diagnostics

`run-extended-aime.py` is a separate, diagnostic-only follow-up for the four
primary quality arms at ranks 116–119. Each primary arm ended in the same
validated bounded condition: the frozen quick-profile item
`2024-2024-II-2` reached its 2,048-token AIME response ceiling.

The follow-up reruns only that exact item with a 6,144-token ceiling. Every
other quick-profile AIME setting remains frozen: greedy decoding, `k=1`,
thinking disabled, seed 1234, `min_tokens=0`, one client, and the pinned
evaluator. It is not a quality comparison or retention gate. A stopped answer
does not retroactively validate the primary quick run, and a second length stop
does not invalidate the candidate.

## Commands

```bash
# Read-only: validate the four primary terminal markers and all bound evidence.
senpai/competition_notes/top15_replication_2026-08-02/run-extended-aime.py preflight

# Build and run all four arms serially, or select one rank/UUID prefix.
senpai/competition_notes/top15_replication_2026-08-02/run-extended-aime.py run all
senpai/competition_notes/top15_replication_2026-08-02/run-extended-aime.py run 116

# Read-only status/integrity checks.
senpai/competition_notes/top15_replication_2026-08-02/run-extended-aime.py status
senpai/competition_notes/top15_replication_2026-08-02/run-extended-aime.py verify --require-complete
```

`preflight`, `status`, and `verify` never build or start a model. `run` is the
only command that does either.

## Provenance and isolation

The runner accepts only ranks 116–119 from `candidates.json`, and only while
each primary arm still has a valid `terminal-noncompletion.json` for the one
frozen ID. It verifies the marker's bound primary run spec, evaluator run, raw
AIME result, wrapper, real bridge source fingerprint, response journal, and
other retained raw artifacts before doing any work. Preflight and execution
also require the frozen `Mac16,6` / Apple M4 Max / 128 GB study host.

For a new diagnostic arm, the runner:

1. takes an exclusive diagnostic lease on the owned rolling workspace and
   refuses to proceed while the primary runner or another workspace model/build
   process is visible;
2. restores the candidate's exact participant-editable snapshot over the
   frozen common harness;
3. installs the evaluator from its frozen Git commit, rebuilds the bridge and
   Metal library, and requires the bridge source fingerprint and Metal-library
   bytes to agree with the primary evidence;
4. copies the bridge, source sidecar, Metal library and fingerprint, transparent
   M4 wrapper, and one-ID manifest into an immutable per-arm artifact bundle;
5. starts pinned `quality-eval serve --no-build` on that bundle and invokes the
   pinned upstream `aime_eval.py` for exactly one request; and
6. stops the server before advancing to the next arm. The evaluator's shared
   model lock provides a second one-model-at-a-time guard.

The default output is the separate sibling tree
`quality-results/leaderboard-top15-20260802-aime-extended-6144`. It is
deliberately outside `quality-results/leaderboard-top15-20260802`; the script
rejects overlapping result paths and contains no write path to the primary
quality arms or their `selected-attempt.txt` files.

Each arm retains immutable build attempts, a preserved executable bundle,
`run-spec.json`, model/evaluator logs, the server readiness record, exact
invocation, request journal, raw AIME JSON, terminal status, and SHA-256 hashes.
Failed or interrupted attempts remain in place. Rerunning creates the next
attempt, while a valid finished attempt without a completion marker is recovered
without another model invocation.

Do not run the primary study runner concurrently with this diagnostic. The
diagnostic checks for an active primary process before mutating the shared
rolling workspace, but `run-study.sh` predates and does not honor the
diagnostic's advisory workspace lease.
