# Ranked Authority Evidence Bundle Audit

## Result

`RANKED_AUTHORITY_EVIDENCE_CONTRACT_READY`

Revision r2 closes the ranked-authority evidence contract as a deterministic,
closed-world static validator. It classifies future bundles as `INVALID`,
`INCOMPLETE`, or `STATIC_RESUME_READY`; it does not claim that a ranked run or
worker currently satisfies the contract.

## Assignment and authority boundary

- Branch: `cedar-tanjiro/ranked-authority-evidence-contract`
- Pull request: `#674`
- Assignment: `cedar-tanjiro-ranked-authority-evidence-contract-20260810`
- Revision: `cedar-tanjiro-ranked-authority-evidence-contract-20260810-r2-closed-world-authority`
- Base: `5ae76f3267eff85254b08c4890556d5727ca6f28`
- Authority contract: `pr671-ranked-installed-authority/v1`
- This was a static-only task. It did not access a real `/opt` path, ranked
  worker, model, hidden artifact, credential, secret, receipt, or W&B run.
- No build, GPU/model execution, benchmark, ranked job, submission, or receipt
  polling occurred. `/opt` strings below are synthetic contract data only.
- Every fixture is synthetic and explicitly non-authoritative. A passing
  positive fixture proves contract consistency, not ranked authority.

## Closed-world v2 contract

The committed Draft 2020-12 schema and standard-library validator both enforce
the contract. The schema rejects additional properties at every declared object
boundary. The validator recursively rejects secret-looking keys and secret
values before semantic classification, so an unknown secret field cannot hide
behind ordinary unknown-field handling.

The validator requires exact censuses rather than best-effort subsets:

- all ten artifact roles and their versioned installed paths;
- the complete actor, phase, event, event-edge, capability, and environment
  observation sets;
- exactly one record for every mandatory identity; and
- canonical absolute installed paths with no aliases, dot segments, duplicate
  separators, or alternate spellings.

The `pr671-ranked-installed-authority/v1` role/path census is:

| Mandatory role | Exact installed path |
| --- | --- |
| `workflow_file` | `/synthetic/repository/.github/workflows/benchmark.yml` |
| `installation_recipe` | `/synthetic/authority/install-recipe.json` |
| `bench_exec` | `/opt/bench/bench-exec.sh` |
| `measure_job` | `/opt/bench/measure-job.sh` |
| `reaper` | `/opt/bench/reap-bench-processes.sh` |
| `worker_launcher` | `/opt/bench/worker-launcher.sh` |
| `runtime_worker` | `/synthetic/workspace/.build/release/MLXFastRuntimeWorker` |
| `worker_sandbox_profile_generator` | `/opt/bench/generate-worker-profile.sh` |
| `profile_generator_input` | `/opt/bench/profile-inputs/worker-policy.txt` |
| `worker_sandbox_profile` | `/synthetic/job/worker.sb` |

The `/synthetic/...` values are deliberate closed-world fixture identities. A
future contract version must change the version and census together rather than
silently accepting a different path.

## Independent authority joins

Validation is deliberately non-short-circuiting across semantic domains.
Missing one role cannot mask contradictions in the remaining evidence. The
validator independently joins and checks:

- repository, base, workflow, run, job, host, platform, OS, and capture-window
  identities;
- artifact role, installed path, bundle-relative path, install provenance,
  source digest, physical digest, and physical metadata;
- actor parentage, phase ownership, UID/GID transitions, and confinement actor;
- exact typed events, event actors, phase references, sequence numbers,
  timestamps, and the full required edge census;
- profile generator role, input roles, generated profile role, generation and
  injection events, confinement role, mounts, rights, weights root, and
  capabilities;
- every actor-by-policy environment observation, allowlisted names, redacted
  secret-name accounting, and unknown actors; and
- generation and authority digests over canonical JSON.

The required ordered event chain is:

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

All seven adjacent edges are mandatory. Graph acyclicity, sequence ordering,
and timestamp ordering are checked independently, including early-chain
reversals. Generation-event and confinement references must agree with their
artifact roles and canonical command arguments.

## Physical evidence checks

The validator resolves only bundle-relative evidence beneath the supplied
bundle root and uses `lstat`-based checks. It rejects path escape, symlinks,
non-regular files, missing files, hardlink ambiguity, and drift in bytes,
SHA-256, size, mode, UID/GID, ACL, flags, link count, device, filesystem, or
install provenance. Manifest-only assertions cannot become ready when copied
physical evidence disagrees.

## Classification contract

- `INVALID`: any schema defect, unknown field, secret leak, malformed or
  contradictory claim, census mismatch, identity/path drift, physical mismatch,
  event/order/timestamp error, or profile-generation/confinement inconsistency.
  Contradictions always dominate missing-authority declarations.
- `INCOMPLETE`: no contradiction exists and exactly the first missing authority
  fact is identified with its reason. Omitting roles jointly, or declaring a
  missing role while retaining generator, confinement, or timestamp drift,
  remains `INVALID`.
- `STATIC_RESUME_READY`: every required static fact is present, physically
  verified, internally consistent, and cryptographically bound. This resumes
  static review only. Ranked authority additionally requires an affirmative
  authority claim and `non_authoritative: false`; the positive synthetic
  fixture never supplies ranked authority.

## Deterministic control matrix

The fixture runner creates temporary synthetic files, hydrates observed
physical metadata, applies one named mutation, recomputes only permitted
derived values, and checks both state and required error codes.

| Expected state | Covered controls |
| --- | --- |
| `STATIC_RESUME_READY` | `complete-synthetic-bundle` |
| `INCOMPLETE` | `missing-profile-generator-input` |
| `INVALID` | Closed world: `unknown-field`, `unknown-secret-field` |
| `INVALID` | Census and paths: `jointly-omitted-mandatory-roles`, `installed-path-alias`, `duplicate-artifact-role`, `missing-capability` |
| `INVALID` | Physical: `physical-byte-drift`, `declared-hash-drift`, `declared-size-drift`, `bundle-path-escape`, `symbolic-link-artifact`, `owner-mismatch`, `mode-mismatch`, `acl-mismatch`, `hardlink-ambiguity`, `absent-self-declared-artifact` |
| `INVALID` | Identity/provenance: `workflow-identity-drift`, `base-identity-drift`, `job-identity-drift`, `stale-capture`, `missing-install-provenance`, `profile-hash-mismatch` |
| `INVALID` | Environment/actors: `secret-value-leak`, `undeclared-environment-name`, `missing-environment-observation`, `unknown-environment-actor`, `uid-gid-transition-contradiction`, `survivor-policy-contradiction` |
| `INVALID` | Event graph/time: `event-cycle`, `event-order-reversal`, `early-chain-edge-reversal`, `timestamp-reversal` |
| `INVALID` | Generator/confinement: `generation-event-drift`, `generator-confinement-drift`, `incomplete-generator-drift`, `incomplete-timestamp-reversal`, `mount-path-contradiction` |

Control totals:

- 39 of 39 fixture cases pass.
- 1 case classifies `STATIC_RESUME_READY`.
- 1 case classifies `INCOMPLETE`.
- 37 cases classify `INVALID`.

These controls specifically prove rejection of unknown secret fields, jointly
omitted roles, installed-path aliases, missing environment observations, unknown
actors, early edge reversals, timestamp reversals, generation-event drift,
confinement drift, and contradictions that coexist with an incomplete claim.

## Reproduction

```bash
python3 -m py_compile \
  research/validate_ranked_authority_evidence_bundle.py
python3 research/validate_ranked_authority_evidence_bundle.py \
  --run-fixtures \
  research/ranked_authority_evidence_bundle_fixtures.json
```

The validator emits canonical compact sorted JSON followed by one newline. A
future read-only bundle can be checked with:

```bash
python3 research/validate_ranked_authority_evidence_bundle.py \
  --bundle-root /path/to/read-only-bundle \
  --manifest /path/to/read-only-bundle/bundle.json
```

## Organizer collection handoff

A future collector should run in the same trusted ranked job after installation
and before replacement is possible. It should copy all ten exact installed
artifacts without following links, record their physical metadata and install
provenance, record the complete identity/actor/phase/event/edge/environment and
profile-confinement censuses, and compute canonical generation and authority
digests last. It must never place a secret value in the manifest, logs, fixtures,
or audit. If one fact is unavailable, it should declare only the first missing
fact without omitting other required records or concealing contradictions.

## Scope verification target

The branch diff is limited to the schema, validator, fixture suite, and this
audit. No runtime, kernel, transform, harness, workflow, model, package, or
ranked-system file is modified.

---

This audit was generated by an AI agent (OpenHands) on behalf of the user.
