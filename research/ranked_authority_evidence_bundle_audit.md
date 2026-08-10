# Ranked Authority Evidence Bundle Audit

## Result

`RANKED_AUTHORITY_EVIDENCE_CONTRACT_READY`

Revision r6 preserves the r5 deterministic static evidence contract while
making artifact credential scanning explicitly bounded in both memory and input
size. Every READY-driving observation and linkage remains covered by the canonical
bundle digest, which is authenticated through a separately pinned verifier-owned
trust document. A bundle may classify as `STATIC_RESUME_READY`, but a synthetic
bundle never authorizes ranked resumption.

This result does **not** upgrade PR #671. Its ranked audit remains
`RANKED_WEIGHT_PROVENANCE_INDETERMINATE`.

## Assignment and scope

- Branch: `cedar-tanjiro/ranked-authority-evidence-contract`
- Pull request: `#674`
- Revision: `cedar-tanjiro-ranked-authority-evidence-contract-20260810-r6-bounded-artifact-scan-provenance`
- Historical r5 required base: `72e6dcc6695dcf2aafd6bad60b785b27b444bbe7`
- Current r6 required base: `908050254a6c1358c0fafe56459696bcca13eee8`
- The r6 base was merged by `23c4d2b`; `git merge-base --is-ancestor`
  confirms `908050254a6c1358c0fafe56459696bcca13eee8` is an ancestor of the result.
- Bundle schema: `ranked-authority-evidence-bundle/v4`
- External trust schema: `ranked-authority-external-trust/v2`
- Fixture schema: `ranked-authority-evidence-fixtures/v5`
- Authority contract: `pr671-ranked-installed-authority/v4`
- The submission diff changes only the assigned validator, fixtures, and audit;
  the assigned schema remains unchanged because the evidence shape did not change.
- This static-only task did not access `/opt`, credentials, secrets, a ranked
  worker, model data, timing data, receipts, or submissions.
- No build, benchmark, GPU/model execution, ranked job, receipt polling,
  submission, or W&B run occurred. W&B, model runtime, and peak memory are not
  applicable.

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
artifact bytes are scanned before semantic use. The r5 12-case matrix covering
fictional GitHub tokens, AWS access keys, bearer credentials, and private-key
blocks remains unchanged. Every matrix case returns exact
`SECRET_VALUE_FORBIDDEN`; no real credential is present.

Revision r6 replaces the artifact scanner's whole-file `read_bytes()` with a
64-KiB streaming read, a 512-byte overlap, and a committed 64-MiB per-artifact
input limit. The overlap is larger than the longest explicitly bounded
credential signature and retains the minimum detectable prefix of unbounded
bearer signatures across chunk boundaries. At most one chunk plus the overlap
is decoded at once.

The scanner opens the file before checking `fstat`, so files already larger than
the limit fail without being read. A cumulative byte counter independently
catches growth during scanning. A one-byte-over in-root artifact therefore
returns structured exact `ARTIFACT_SCAN_SIZE_LIMIT_EXCEEDED`, while the exact
64-MiB boundary remains valid. A fictional GitHub signature split across a
chunk boundary returns exact `SECRET_VALUE_FORBIDDEN`. All three controls emit
no stderr and no traceback.

Manifest and trust bytes use the same structured validation entry point.
Malformed manifest JSON returns exact `MANIFEST_JSON_INVALID`; malformed trust
JSON returns exact `EXTERNAL_TRUST_JSON_INVALID`. Each direct CLI result remains
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

The r6 suite preserves all 72 r5 controls and adds exact-limit,
one-byte-over-limit, and cross-chunk credential controls. Every case declares
the complete exact error-code set and runs twice internally. The complete suite
was also invoked twice externally and the aggregate result bytes were identical.

Results:

- 75 of 75 fixture cases pass with zero fixture failures.
- 3 cases classify `STATIC_RESUME_READY`, all unauthorized.
- 1 case classifies `INCOMPLETE`.
- 71 cases classify `INVALID`.
- Every case reports deterministic agreement.
- Exact-limit artifact: `STATIC_RESUME_READY` with no errors.
- One-byte-over artifact: `INVALID` with sole
  `ARTIFACT_SCAN_SIZE_LIMIT_EXCEEDED`.
- Cross-chunk fictional credential: `INVALID` with sole
  `SECRET_VALUE_FORBIDDEN`.
- Fixture source SHA-256:
  `da704dd2eaaae935dbd540347aebc6e6838af0abc08ab8f905f43330dc9616f5`.
- Both byte-identical aggregate results have SHA-256:
  `2286c6e585f4e1cc52463e5c434dec1c0250098c31ebe55263df549840f45e6b`.
- Full-suite wall times were approximately 13.97 and 13.75 seconds.

## Reproduction

```bash
python3 -m py_compile research/validate_ranked_authority_evidence_bundle.py
python3 -c 'import json; json.load(open("research/ranked_authority_evidence_bundle.schema.json")); json.load(open("research/ranked_authority_evidence_bundle_fixtures.json")); print("json-ok")'
python3 research/validate_ranked_authority_evidence_bundle.py --help
python3 research/validate_ranked_authority_evidence_bundle.py \
  --run-fixtures research/ranked_authority_evidence_bundle_fixtures.json \
  > /tmp/cedar-r6-first.json
python3 research/validate_ranked_authority_evidence_bundle.py \
  --run-fixtures research/ranked_authority_evidence_bundle_fixtures.json \
  > /tmp/cedar-r6-second.json
cmp -s /tmp/cedar-r6-first.json /tmp/cedar-r6-second.json
shasum -a 256 research/ranked_authority_evidence_bundle_fixtures.json \
  /tmp/cedar-r6-first.json /tmp/cedar-r6-second.json
git diff --check
```

A future read-only bundle requires a separate verifier-owned trust document and
its independently supplied canonical SHA-256 pin. A trusted collector must
record immutable process births separately from events, scan all evidence for
secrets, compute canonical attestations last, and stop at the first missing
fact rather than inventing authority.

---

This audit was generated by an AI agent (OpenHands) on behalf of the user.
