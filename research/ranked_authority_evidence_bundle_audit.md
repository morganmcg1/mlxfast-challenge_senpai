# Ranked Authority Evidence Bundle Audit

## Result

`RANKED_AUTHORITY_EVIDENCE_CONTRACT_READY`

Revision r5 defines a deterministic static evidence contract in which every
READY-driving observation and linkage is covered by the canonical bundle digest,
and that digest is authenticated through a separately pinned verifier-owned trust
document. A bundle may classify as `STATIC_RESUME_READY`, but a synthetic bundle
never authorizes ranked resumption.

This result does **not** upgrade PR #671. Its ranked audit remains
`RANKED_WEIGHT_PROVENANCE_INDETERMINATE`.

## Assignment and scope

- Branch: `cedar-tanjiro/ranked-authority-evidence-contract`
- Pull request: `#674`
- Revision: `cedar-tanjiro-ranked-authority-evidence-contract-20260810-r5-observation-attestation-process-birth`
- Assignment base: `707512704f4d4251aa945aa1bc583a5f010da3c9`
- Bundle schema: `ranked-authority-evidence-bundle/v4`
- External trust schema: `ranked-authority-external-trust/v2`
- Fixture schema: `ranked-authority-evidence-fixtures/v5`
- Authority contract: `pr671-ranked-installed-authority/v4`
- The diff is limited to the assigned schema, validator, fixtures, and audit.
- This static-only task did not access `/opt`, credentials, secrets, a ranked
  worker, model data, timing data, receipts, or submissions.
- No build, benchmark, GPU/model execution, ranked job, receipt polling,
  submission, or W&B run occurred. Runtime and peak memory are not applicable.

## Frozen PR #671 boundary

The ranked trust scope continues to pin only source-backed facts:

| Fact | Exact value |
| --- | --- |
| Assignment PR | `671` |
| Audit terminal | `RANKED_WEIGHT_PROVENANCE_INDETERMINATE` |
| First unavailable path | `/opt/bench/bench-exec.sh` |
| Audited base | `5593d8f4a394023e83dfbfe11ef01fa01a5b7f15` |
| Repository | `morganmcg1/mlxfast-challenge_senpai` |
| Workflow path | `.github/workflows/benchmark.yml` |
| Workflow git blob | `cd045c1b29009a041acb70360c2907a2623a146a` |
| Workflow SHA-256 | `a73f67d041e780371b8bae45de1f94f0649fb9e09fe846e4e5b79062ae6d2e18` |
| `MLXFAST_BENCH_EXEC` | `/opt/bench/bench-exec.sh` |
| `MLXFAST_MEASURE_JOB` | `/opt/bench-runner/measure-job.sh` |

The stopped edge remains:

```text
trusted runner hash of transformed weight tree -> bench-exec-mediated reaper / worker launch / sandbox injection -> worker's independent pathname opens during the load epoch
```

No additional installed ranked pathname is asserted.

## Externally authenticated canonical bundle

The trust document now includes `expected_bundle_sha256`. The trusted collector
attestation covers that field, and the verifier authenticates the complete
canonical trust JSON against its independently supplied lowercase SHA-256 pin.
Only an authenticated trust document can supply the expected bundle digest.

The bundle digest covers the complete canonical bundle, including actors,
immutable process births, event commands, phases, edges, capture window,
artifact identities, environment observations, confinement facts, and all
READY-driving derived linkages. A coherent rewrite therefore cannot establish
a new authority root by updating only bundle-local digests and seals.

The coherent-rewrite control changes PID, PPID, parent, command-process
references, process observations, and event/lifecycle timestamps, then refreshes
bundle-local identities and seals. It retains the original authenticated trust
document and verifier pin. Both validations return the exact sole error
`TRUST_BUNDLE_DIGEST_MISMATCH`.

## Immutable process births

Process creation is represented once per PID in top-level `process_births`.
Each record fixes actor, PID, PPID, parent actor, executable role, installed
path, executable digest, start time, and observation time. Events reference the
immutable birth PID rather than repeating mutable process-start objects.

The validator requires unique actor and PID births, one birth for every command
actor, consistent parent and executable identity, `started_at <= observed_at`,
and birth observation no later than that actor's first event. Duplicate births,
changed identity, impossible birth times, and lifecycle contradictions are
`INVALID`.

## Secret and malformed-input fail closure

All manifest and external-trust string fields are recursively scanned, and
artifact bytes are scanned before semantic use. Revision r5 adds a 12-case
matrix covering fictional GitHub tokens, AWS access keys, bearer credentials,
and private-key blocks in each of manifest strings, external-trust strings, and
artifact bytes. Every matrix case returns exact `SECRET_VALUE_FORBIDDEN`. The
prior fictional secret control also remains; no real credential is present.

Manifest and trust bytes use the same structured validation entry point.
Malformed manifest JSON returns exact `MANIFEST_JSON_INVALID`; malformed trust
JSON returns exact `EXTERNAL_TRUST_JSON_INVALID`. Each direct CLI result is
byte-identical across two runs, exits 1, emits no stderr, and has no traceback.

## Classification and authorization

- `INVALID`: any schema, trust, digest, identity, process, event, artifact,
  environment, confinement, secret, or parsing contradiction.
- `INCOMPLETE`: no contradiction exists, but authenticated ranked authority
  stops at exactly one declared missing fact.
- `STATIC_RESUME_READY`: every static join passes.

`STATIC_RESUME_READY` is evidence classification, not authority. CLI success
still requires authenticated ranked trust, a complete census, an authoritative
bundle, and `synthetic: false`. All fixtures are synthetic and report
`authoritative: false` and `resumption_authorized: false`.

## Deterministic controls

The r5 suite preserves all r4 controls and adds external bundle-digest
authentication, coherent rewrite, process-birth, secret-matrix, and malformed
JSON controls. Every case declares the complete exact error-code set and runs
twice internally.

Results:

- 72 of 72 fixture cases pass.
- 2 cases classify `STATIC_RESUME_READY`, both unauthorized.
- 1 case classifies `INCOMPLETE`.
- 69 cases classify `INVALID`.
- Every case reports deterministic agreement.
- Fixture source SHA-256:
  `42446bbe632075aa4bd4739a94bd8f825c92b9223b92ed5eecff4ad45afa4b66`.
- Both byte-identical aggregate results have SHA-256:
  `a39468d6188ba8f5656bd7a707cd4c77cf630782cfc0f25d309a2bcb710d1c2a`.

## Reproduction

```bash
python3 -c 'import json; json.load(open("research/ranked_authority_evidence_bundle.schema.json")); json.load(open("research/ranked_authority_evidence_bundle_fixtures.json")); print("json-ok")'
python3 -m py_compile research/validate_ranked_authority_evidence_bundle.py
python3 research/validate_ranked_authority_evidence_bundle.py \
  --run-fixtures research/ranked_authority_evidence_bundle_fixtures.json \
  > /tmp/cedar-r5-first.json
python3 research/validate_ranked_authority_evidence_bundle.py \
  --run-fixtures research/ranked_authority_evidence_bundle_fixtures.json \
  > /tmp/cedar-r5-second.json
cmp -s /tmp/cedar-r5-first.json /tmp/cedar-r5-second.json
shasum -a 256 /tmp/cedar-r5-first.json /tmp/cedar-r5-second.json
```

A future read-only bundle requires a separate verifier-owned trust document and
its independently supplied canonical SHA-256 pin. A trusted collector must
record immutable process births separately from events, scan all evidence for
secrets, compute canonical attestations last, and stop at the first missing
fact rather than inventing authority.

---

This audit was generated by an AI agent (OpenHands) on behalf of the user.
