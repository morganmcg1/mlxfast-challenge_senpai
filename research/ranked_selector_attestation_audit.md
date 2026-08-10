# Ranked selector attestation contract audit

## Decision

`RANKED_SELECTOR_ATTESTATION_CONTRACT_READY`

This static research artifact closes the selector-attestation contract only for
the future static resumption review identified by
`PR_670_FUTURE_STATIC_RESUMPTION_ONLY`. It does **not** attest any existing
ranked run, close the ranked environment, authorize a run or submission,
authorize promotion, establish an official score, or replace organizer review.
No live environment, `/opt` path, secret, receipt, setup, build, inference,
timing, or submission was inspected or executed.

The contract is ready for PR #670's organizer-controlled static review because
it defines fail-closed evidence, separate trust anchors, precedence-complete
synthetic controls, and deterministic validation. `STATIC_RESUME_READY` means
only that the static evidence satisfies this frozen contract; the validator
always reports `ranked_run_or_submission_authorized: false`.

## Frozen audit anchors

| Anchor | Value |
| --- | --- |
| Authorization scope | `PR_670_FUTURE_STATIC_RESUMPTION_ONLY` |
| Selector audit PR | `670` |
| Experiment base | `ccbe6fad8fc0923709ae335a83bdbafcc5a3fcdb` |
| Current audit source revision | `ac0e7cf6f283c8ac655af955d7ccf57c5141185e` |
| Pinned baseline revision | `15852ee52858def42ddd4f32bca7e59d275e020e` |
| Frozen environment audit SHA-256 | `09dedaf97a31e0be10e679b792587c04142e5c662763486a32e097789f0d4375` |
| Current selector census | 148 rows: 142 `DARKBLOOM_*` implied selectors and 6 literal `MLX_*` selectors |
| Runtime worker forwarding source | `Sources/MLXFastTrustedHarness/LagunaRuntimeWorker.swift:1993-2024` |

The `static_resume_target` object is required in both the attestation and the
trusted expectations and pins all six values above: scope, PR number, base,
frozen audit digest, and both source revisions. The frozen audit digest is an
input, not ranked evidence. Current and pinned censuses remain separate because
source revision is part of selector identity.

## Delivered research-only artifacts

| Artifact | Purpose |
| --- | --- |
| `ranked_selector_attestation.schema.json` | Closed-world machine-readable envelope, exact four-phase model, trust target, row shape, and canonical physical contract. |
| `validate_ranked_selector_attestation.py` | Standard-library, fail-closed validator plus deterministic synthetic bundle generator and self-test. |
| `ranked_selector_attestation_fixtures.json` | Four ready/incomplete scenarios and 33 invalid mutations with expected classifications and error codes. |
| `ranked_selector_attestation_audit.md` | This decision record, validation matrix, reproduction commands, and non-claims. |

No scored or submitted path is modified.

## Exact process model

The contract permits exactly these four process classes and no aliases:

| Phase | Revision role | Required evidence |
| --- | --- | --- |
| `current_public_correctness` | current | Parent snapshot and runtime-worker snapshot |
| `current_hidden_gates` | current | Parent snapshot and runtime-worker snapshot |
| `pinned_baseline_timed` | pinned | Parent snapshot and runtime-worker snapshot |
| `current_candidate_timed` | current | Parent snapshot and runtime-worker snapshot |

Every phase object is mandatory. Every parent and worker reference property is
mandatory. A reference may be JSON `null` only to state explicitly that the
collector failed to produce that evidence. The installed-authority digest is
also mandatory and may be `null` only to state that no authority was captured.
Either kind of missing evidence is `SELECTOR_ATTESTATION_INCOMPLETE`, never
ready. A non-null reference that does not resolve to an exact declared regular
file is contradictory and therefore `SELECTOR_ATTESTATION_INVALID`.

Before reporting any missing reference or authority, the validator semantically
validates every artifact that is present. Invalid evidence therefore wins over
missing evidence. The controls combine a missing worker with both an invalid
selector name and noncanonical snapshot JSON to prove this precedence.

All four phases must bind to one trusted ranked job ID, run ID, workflow SHA,
host class, collector identity, and capture epoch. The current phases must bind
to the current source revision and census; the baseline timing phase must bind
to the pinned source revision and census.

## Schema and validator closure

The schema and validator implement the same closed-world object key sets. The
validator pins the schema byte digest, validates the schema contract before a
bundle, rejects unknown fields, enforces selector strings of at most 160
characters, enforces base64 type and encoded-size bounds, and parses capture
epochs as real UTC instants. A syntactically shaped impossible date is invalid. Dedicated
controls cover schema drift, impossible dates, oversized selectors, and wrong
selector types.

## Selector row contract

Each census row pins:

- the exact selector name;
- a source-derived stable row identifier;
- source revision;
- parser profile; and
- source location and selector origin.

Each snapshot must contain one row for every census row, with no omissions,
duplicates, or additions. Absence is represented by an explicit row with
`state: "ABSENT"`, `value_utf8_b64: null`, and `value_length: 0`; it is never
inferred from omission. Presence is represented by `state: "VALUE"`, exact raw
UTF-8 bytes encoded in base64, exact byte length, parser profile, normalized
semantic value, and a recomputable row digest.

The validator rejects unknown `DARKBLOOM_*` or `MLX_*` names rather than
accepting a prefix-shaped addition. It also rejects invalid UTF-8, noncanonical
base64, parser-profile drift, semantic mismatch, row-set mismatch, and digest
mismatch.

## Canonical binding

The contract uses explicit domain-separated framing:

- Row digest: `RANKED_SELECTOR_ROW_V1\0`, fixed field order,
  length-prefixed UTF-8 metadata, explicit state byte, exact value length and
  bytes, and compact sorted-key semantic JSON.
- Selector-map digest: `RANKED_SELECTOR_MAP_V1\0`, row count, rows sorted by raw
  UTF-8 name bytes, explicit state, and exact value bytes.
- Bundle digest: compact sorted-key UTF-8 JSON of `attestation.json` with only
  `canonical_bundle_sha256` omitted. Manifest hashes transitively bind every
  physical evidence file.
- Physical JSON: `attestation.json`, trusted expectations, every census, and
  every snapshot are physically enforced as strict UTF-8, duplicate-key-free,
  compact `ensure_ascii=false` sorted-key JSON with comma/colon separators and
  one trailing LF.

This framing prevents delimiter ambiguity, row-order ambiguity, implicit
absence, and a self-referential entry-point file hash. Noncanonical bytes are
invalid even when they decode to the same JSON value.

## Parent-to-worker forwarding contract

For every phase, the worker snapshot must equal the parent snapshot for the
revision-specific selector census. The worker may add exactly one forced row:

- `MLXFAST_USE_RUNTIME_WORKER=0`

That forced row must be `VALUE`, must contain the exact single byte `0`, and
must normalize under the boolean parser profile to `false`. Any forwarded value
mutation, missing forced row, or other worker-only addition is invalid. This
models the audited worker behavior where `DARKBLOOM_*` and `MLX_*` variables are
forwarded before the runtime-worker variable is forced to zero.

## Cross-process policy

All shared selector names must have identical exact value bytes across all
process classes. No phase-specific override is permitted.

The sole supported exception is structural, not value-based: a selector row
may exist in only one source revision when the separately trusted revision
policy records exactly `selector`, `present_revision`, `missing_revision`,
`present_stable_row_id`, `reason_code`, `allowed_state`,
`allowed_value_sha256`, and `justification`. `reason_code` must be
`REVISION_ONLY_NO_CONSUMER`; the present row and allowed state/value digest
must match the census and snapshots. The validator rejects policy for a name
present in both censuses, undeclared revision-only names, wrong revisions or
row IDs, unsupported reason codes, and mismatched allowed values.

## Separate trust boundary

Self-consistency is insufficient. The validator requires a separately supplied,
physically canonical trusted expectations JSON object that pins:

- the exact PR #670 `static_resume_target`, including authorization scope,
  experiment base, frozen environment-audit digest, and both revisions;
- workflow SHA, ranked job ID, run ID, host class, collector, and capture epoch;
- current and pinned census file SHA-256 values;
- the installed-authority foreign digest; and
- the attestation's `canonical_bundle_sha256`.

The evidence bundle cannot redefine these values. The trusted canonical-bundle
digest binds the complete manifest-backed evidence bytes rather than trusting
self-consistency alone. A non-null mismatch is invalid. If both the attestation
and expectations record installed authority as `null`, authority is missing and
the result is incomplete, never ready. This prevents an internally consistent
but foreign or replayed bundle from becoming authoritative merely by hashing
itself.

## Physical and secret-safety contract

The entry point is `attestation.json`. Every non-null census and snapshot path
must appear exactly once in the manifest. No other physical bundle file is
allowed. Paths are lexical POSIX relatives; absolute paths, `..`, repeated
manifest paths, symlinks in the root or any path component, non-regular files,
undeclared files, missing files, byte-size drift, and SHA-256 drift are invalid.

The artifact is a selector allowlist, not an environment dump. The validator
rejects credential-shaped variable names, credential-shaped value content,
redaction placeholders, generic environment dump files, and any selector not
in the pinned census. Secret-safe evidence records exact allowed selector bytes
only; it never records credentials or substitutes redacted text for evidence.

## Classification semantics

| Classification | Meaning |
| --- | --- |
| `SELECTOR_ATTESTATION_INVALID` | Evidence is contradictory, malformed, foreign, unsafe, ambiguously framed, or violates an invariant. It must not be resumed. |
| `SELECTOR_ATTESTATION_INCOMPLETE` | All present evidence is valid, but authority or a mandatory census/snapshot reference is explicitly `null`. The output reports the first missing item. |
| `SELECTOR_ATTESTATION_STATIC_RESUME_READY` | All required static evidence validates for `PR_670_FUTURE_STATIC_RESUMPTION_ONLY`. It is not authority, correctness, timing, run, submission, promotion, or score permission. |

Invalid always takes precedence over incomplete: the validator validates the
schema, trust, all present physical files, every present census and snapshot,
hashes, forwarding, and cross-process equality before reporting missing
authority or references. Every non-invalid output includes the frozen static
target and `ranked_run_or_submission_authorized: false`.

## Synthetic validation matrix

Two independent CLI invocations produced byte-identical full JSON output with
SHA-256 `a91e62a1976d035a945c373b6b96b4f57c1be3c7520ef18b2a0be894b7ccda47`.
The output reports:

- fixture catalog SHA-256 `8aae094d0d1d8142959a19c79dd58ce20f7d4022647d9bbe25a54bc9c46763f8`;
- case-results SHA-256 `e703a384e7103ea09aa376142199857155633d627336ff6e9426df0f3ea126dd`; and
- schema SHA-256 `66d11be47fc26211ca27f6cbc1df10b32ab3d6730f7a433a8c35328827a59414`.

All 37 cases passed their expected classification and, for invalid cases,
expected fail-closed code.

### Ready and incomplete controls

| Fixture | Expected result |
| --- | --- |
| `all_four_explicit_absence` | `SELECTOR_ATTESTATION_STATIC_RESUME_READY` |
| `identical_intentional_map_with_revision_rule` | `SELECTOR_ATTESTATION_STATIC_RESUME_READY` |
| `first_missing_pinned_timed_worker` | `SELECTOR_ATTESTATION_INCOMPLETE`; first missing `pinned_baseline_timed.worker_snapshot` |
| `null_authority_is_incomplete` | `SELECTOR_ATTESTATION_INCOMPLETE`; first missing `installed_authority_bundle_digest` |

### Invalid controls

| Fixture | Expected error code |
| --- | --- |
| `artifact_byte_hash_drift` | `ARTIFACT_HASH_MISMATCH` |
| `artifact_size_drift` | `ARTIFACT_SIZE_MISMATCH` |
| `path_escape` | `PATH_ESCAPE` |
| `symlink_snapshot` | `SYMLINK_FORBIDDEN` |
| `duplicate_phase` | `DUPLICATE_PHASE` |
| `duplicate_manifest_path` | `DUPLICATE_MANIFEST_PATH` |
| `current_census_digest_drift` | `CURRENT_CENSUS_DIGEST_MISMATCH` |
| `pinned_census_digest_drift` | `PINNED_CENSUS_DIGEST_MISMATCH` |
| `source_revision_drift` | `SOURCE_REVISION_MISMATCH` |
| `implicit_omitted_selector_row` | `SELECTOR_ROW_SET_MISMATCH` |
| `unknown_darkbloom_selector` | `UNKNOWN_SELECTOR` |
| `hidden_override_differs_from_candidate` | `CROSS_PROCESS_SELECTOR_MISMATCH` |
| `parent_worker_value_mutation` | `PARENT_WORKER_FORWARDING_MISMATCH` |
| `unauthorized_worker_addition` | `UNAUTHORIZED_WORKER_ADDITION` |
| `missing_forced_runtime_worker` | `FORCED_RUNTIME_WORKER_MISSING` |
| `canonical_framing_mutation` | `CANONICAL_MAP_HASH_MISMATCH` |
| `mixed_capture_epoch` | `CAPTURE_EPOCH_MISMATCH` |
| `authority_foreign_key_mismatch` | `AUTHORITY_DIGEST_MISMATCH` |
| `unsupported_revision_exception` | `UNSUPPORTED_REVISION_POLICY` |
| `credential_variable_inclusion` | `SECRET_NAME_FORBIDDEN` |
| `generic_environment_dump` | `UNDECLARED_FILE` |
| `secret_value_leakage` | `SECRET_VALUE_FORBIDDEN` |
| `redaction_placeholder_leakage` | `REDACTION_PLACEHOLDER_FORBIDDEN` |
| `declared_file_missing` | `DECLARED_FILE_MISSING` |
| `trusted_bundle_digest_mismatch` | `TRUSTED_BUNDLE_DIGEST_MISMATCH` |
| `schema_drift` | `SCHEMA_CONTRACT_DRIFT` |
| `impossible_capture_date` | `CAPTURE_EPOCH_INVALID` |
| `selector_name_too_long` | `SELECTOR_NAME_INVALID` |
| `selector_name_wrong_type` | `SCHEMA_INVALID` |
| `noncanonical_snapshot_json` | `PHYSICAL_JSON_NONCANONICAL` |
| `static_resume_target_mismatch` | `STATIC_RESUME_TARGET_MISMATCH` |
| `missing_worker_with_invalid_selector` | `SELECTOR_NAME_INVALID` |
| `missing_worker_with_noncanonical_snapshot` | `PHYSICAL_JSON_NONCANONICAL` |

The self-test materializes bundles only under temporary directories, hashes the
actual physical fixture bytes plus the trusted expectations and schema bytes,
validates through the public bundle path, and removes temporary evidence after
each run. It does not inspect the host environment.

## Reproduction

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile \
  research/validate_ranked_selector_attestation.py

python3 -m json.tool \
  research/ranked_selector_attestation.schema.json >/dev/null
python3 -m json.tool \
  research/ranked_selector_attestation_fixtures.json >/dev/null

PYTHONDONTWRITEBYTECODE=1 python3 \
  research/validate_ranked_selector_attestation.py --help

PYTHONDONTWRITEBYTECODE=1 python3 \
  research/validate_ranked_selector_attestation.py \
  --schema research/ranked_selector_attestation.schema.json \
  --self-test > /tmp/selector_attestation_run1.json

PYTHONDONTWRITEBYTECODE=1 python3 \
  research/validate_ranked_selector_attestation.py \
  --schema research/ranked_selector_attestation.schema.json \
  --self-test > /tmp/selector_attestation_run2.json

cmp -s /tmp/selector_attestation_run1.json \
  /tmp/selector_attestation_run2.json
shasum -a 256 /tmp/selector_attestation_run1.json
```

Prospective PR #670 static-bundle validation is:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 \
  research/validate_ranked_selector_attestation.py \
  --schema research/ranked_selector_attestation.schema.json \
  --bundle ORGANIZER_BUNDLE_DIR \
  --expectations ORGANIZER_TRUSTED_EXPECTATIONS.json
```

## Conclusion

The schema, validator, fixtures, and audit form a complete static contract for
PR #670's organizer-produced selector evidence. They close trust binding,
format, precedence, schema parity, canonical physical integrity, forwarding,
revision policy, and secret safety at the contract level. A ready result permits
only the frozen future static resumption review. It never authorizes a ranked
run, submission, promotion, or score, and the real ranked environment remains
open until an organizer captures and reviews a real same-session bundle.

`RANKED_SELECTOR_ATTESTATION_CONTRACT_READY`
