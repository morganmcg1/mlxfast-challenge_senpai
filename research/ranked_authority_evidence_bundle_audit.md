# Ranked Authority Evidence Bundle Audit

## Result

`RANKED_AUTHORITY_EVIDENCE_CONTRACT_READY`

Revision r3 defines a deterministic static evidence contract with a mandatory,
separate verifier-owned trust document. The bundle cannot grant authority to
itself. Validation may classify a structurally complete bundle as
`STATIC_RESUME_READY`, but the command exits successfully only for a complete
ranked trust root and an affirmative, non-synthetic authority claim.

This result does **not** upgrade PR #671. Its ranked audit remains
`RANKED_WEIGHT_PROVENANCE_INDETERMINATE`.

## Assignment and scope

- Branch: `cedar-tanjiro/ranked-authority-evidence-contract`
- Pull request: `#674`
- Revision: `cedar-tanjiro-ranked-authority-evidence-contract-20260810-r3-external-trust-command-binding`
- Implementation parent: `8ef3939c748b95cb215f2f9b4775fc75752a7510`
- Authority contract: `pr671-ranked-installed-authority/v2`
- This was a static-only task. It did not access `/opt`, a ranked worker, model
  data, timing data, receipts, submissions, credentials, or secrets.
- No build, benchmark, GPU/model execution, ranked job, submission, receipt
  polling, or W&B run occurred.
- The diff is limited to the schema, validator, fixtures, and this audit.

## Frozen PR #671 boundary

The ranked trust scope pins only source-backed facts:

| Fact | Exact value |
| --- | --- |
| Assignment PR | `671` |
| Audit | `research/ranked-weight-load-provenance-audit.md` |
| Audit terminal | `RANKED_WEIGHT_PROVENANCE_INDETERMINATE` |
| First unavailable path | `/opt/bench/bench-exec.sh` |
| Audited base | `5593d8f4a394023e83dfbfe11ef01fa01a5b7f15` |
| Repository | `morganmcg1/mlxfast-challenge_senpai` |
| Workflow path | `.github/workflows/benchmark.yml` |
| Workflow git blob | `cd045c1b29009a041acb70360c2907a2623a146a` |
| Workflow SHA-256 | `a73f67d041e780371b8bae45de1f94f0649fb9e09fe846e4e5b79062ae6d2e18` |
| `MLXFAST_BENCH_EXEC` | `/opt/bench/bench-exec.sh` |
| `MLXFAST_MEASURE_JOB` | `/opt/bench-runner/measure-job.sh` |

The exact stopped edge is:

```text
trusted runner hash of transformed weight tree -> bench-exec-mediated reaper / worker launch / sandbox injection -> worker's independent pathname opens during the load epoch
```

No other installed ranked pathname is asserted by this revision. A real ranked
trust root must provide the complete collector-attested role/path census. If
that collector cannot establish the next required fact, it must set
`census_complete: false`, name exactly that `first_missing_fact`, and produce an
`INCOMPLETE` result rather than inventing a pathname.

## External trust architecture

The manifest and `--external-trust` document are separate schema instances.
The external document pins:

- the exact PR #671 source scope above;
- accepted repository, base, workflow, run, and job identity;
- expected bundle authority claims;
- trusted collector identity and collector authority;
- the complete installed role/path census, its digest, and completeness state;
- event command policies for every required event; and
- a collector attestation over trust facts and the collector-observed installed
  artifact identities.

Missing external trust is `INVALID` with `EXTERNAL_TRUST_REQUIRED`. A coherent
but foreign target is rejected. Flipping the bundle authority claim is rejected.
The ranked source mode additionally pins the known repository/base/workflow
identity and the two source-backed installed paths.

The external trust file is an invocation trust root, not another field copied
inside the bundle. Operational ownership and distribution of that file remain
the verifier's responsibility.

## Copied versus installed metadata

Each artifact now carries two distinct metadata records:

- `bundle_metadata`: metadata observed for the copied evidence file under the
  read-only bundle root; and
- `installed_metadata`: metadata attested by the trusted collector for the
  installed pathname before copying.

The validator continues to verify copied bytes and `bundle_metadata` with
`lstat`-based checks. It independently authenticates the installed pathname,
content digest, `installed_metadata`, and mount identity through the external
collector attestation. Re-sealing only the bundle after changing installed
metadata cannot restore validity.

## Command and process-start binding

Every event binds the exact command identity used at that edge:

- primary artifact role, installed executable path, and artifact digest;
- complete `argv`, `argv[0]`, and canonical argv digest;
- ordered launcher/profile/worker `exec_chain` entries with role, installed
  path, and digest; and
- process-start identity: actor, parent actor, PID, parent PID, executable path,
  executable digest, and start timestamp.

Verifier-owned command policies bind expected event actor, process actor,
primary role, exec-chain roles, and argv digest. The validator rejects a wrong
measure-job path, arbitrary `argv[0]`, argv resealing, launcher-chain
substitution, and process-start identity drift. These joins prevent a valid
artifact census from being reused to describe a different launch.

The required ordered event chain remains:

```text
transform
  -> trusted_hash
  -> reaper
  -> profile_generated
  -> sandbox_injected
  -> worker_spawn
  -> load_start
  -> load_end
```

## Classification and exit contract

- `INVALID`: schema, trust, identity, census, physical evidence, command,
  process, event, confinement, or authenticated-linkage contradiction.
- `INCOMPLETE`: no contradiction exists, but the externally trusted census
  stops at exactly one declared first missing authority fact.
- `STATIC_RESUME_READY`: all static joins pass. This state alone does not grant
  ranked authority.

`resumption_authorized` is true only when all of these hold:

1. state is `STATIC_RESUME_READY`;
2. external trust exists and has `source_kind: ranked`;
3. its census is complete;
4. the bundle claims `authoritative: true`; and
5. the bundle claims `synthetic: false`.

The CLI returns zero only for `resumption_authorized: true`. Therefore neither a
bundle without external trust nor the structurally complete synthetic fixture
can authorize PR #671 or produce CLI success.

## Deterministic controls

The fixture runner creates temporary files, hydrates copied and installed
metadata, seals command/process and trust linkage, then applies one named
mutation. Every fixture is explicitly synthetic and non-authoritative.

Revision r3 adds controls for:

- `missing-external-trust`;
- `authority-claim-flip`;
- `coherent-foreign-target`;
- `wrong-measure-path`;
- `arbitrary-worker-argv0`;
- `launch-chain-substitution`;
- `process-identity-drift`; and
- `installed-metadata-reseal`.

The earlier closed-world, physical evidence, path, identity, environment,
actor, event graph, timestamp, generation, and confinement controls remain.

Control totals:

- 47 of 47 fixture cases pass.
- 1 case classifies `STATIC_RESUME_READY` and remains unauthorized.
- 1 case classifies `INCOMPLETE`.
- 45 cases classify `INVALID`.
- Fixture source SHA-256 reported by the runner:
  `ea1b6bb389848968a0139f55a924b19184cc25b589805f53940235d1f176d0a4`.

A direct contract check also confirmed:

- absent external trust: `INVALID`, `resumption_authorized: false`, CLI exit 1;
- synthetic external trust: `STATIC_RESUME_READY`,
  `resumption_authorized: false`, CLI exit 1.

## Reproduction

```bash
python3 -m py_compile \
  research/validate_ranked_authority_evidence_bundle.py
python3 research/validate_ranked_authority_evidence_bundle.py \
  --run-fixtures \
  research/ranked_authority_evidence_bundle_fixtures.json
```

A future read-only bundle requires an independently supplied trust document:

```bash
python3 research/validate_ranked_authority_evidence_bundle.py \
  --bundle-root /path/to/read-only-bundle \
  --manifest /path/to/read-only-bundle/bundle.json \
  --external-trust /verifier-owned/path/external-trust.json
```

## Collector handoff

A future trusted collector should run in the ranked job after installation and
before replacement is possible. It should record the complete role/path census,
commands, argv, execution chains, process starts, installed metadata, mount
identity, actors, phases, events, edges, environment observations, and
confinement facts. It should copy evidence without following links, compute
canonical digests last, and never place a secret value in evidence or logs. If
one source fact is unavailable, it must stop at the first missing fact and issue
an incomplete external trust statement.

---

This audit was generated by an AI agent (OpenHands) on behalf of the user.
