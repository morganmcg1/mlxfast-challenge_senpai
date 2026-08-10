# Ranked selector attestation contract audit

## Decision

`RANKED_SELECTOR_ATTESTATION_CONTRACT_READY`

This static research artifact defines a prospective, organizer-produced
attestation contract for the selector environment of a single ranked session.
It does **not** attest any existing ranked run, close the ranked environment,
authorize a promotion, establish an official score, or replace organizer
review. No live environment, `/opt` path, secret, receipt, setup, build,
inference, timing, or submission was inspected or executed.

The contract is ready for an organizer to integrate because it defines a
fail-closed evidence format, a separate trust anchor, complete synthetic
positive and negative controls, and deterministic validation. A real session
can be classified only after the organizer captures all required evidence and
supplies trusted expectations independently of the evidence bundle.

## Frozen audit anchors

| Anchor | Value |
| --- | --- |
| Experiment base | `ccbe6fad8fc0923709ae335a83bdbafcc5a3fcdb` |
| Current audit source revision | `ac0e7cf6f283c8ac655af955d7ccf57c5141185e` |
| Pinned baseline revision | `15852ee52858def42ddd4f32bca7e59d275e020e` |
| Prior derived audit JSON SHA-256 | `09dedaf97a31e0be10e679b792587c04142e5c662763486a32e097789f0d4375` |
| Current selector census | 148 rows: 142 `DARKBLOOM_*` implied selectors and 6 literal `MLX_*` selectors |
| Runtime worker forwarding source | `Sources/MLXFastTrustedHarness/LagunaRuntimeWorker.swift:1993-2024` |

The prior derived JSON digest is an audit input, not an attestation contract
and not ranked evidence. The current and pinned selector censuses remain
separate physical artifacts because source revision is part of selector
identity.

## Delivered research-only artifacts

| Artifact | Purpose |
| --- | --- |
| `ranked_selector_attestation.schema.json` | Machine-readable envelope, exact four-phase model, row shape, physical contract, canonical framing, and external trust-boundary declaration. |
| `validate_ranked_selector_attestation.py` | Standard-library, fail-closed validator plus deterministic synthetic bundle generator and self-test. |
| `ranked_selector_attestation_fixtures.json` | Three valid/incomplete scenarios and 24 invalid mutations with expected classifications and error codes. |
| `ranked_selector_attestation_audit.md` | This decision record, evidence matrix, reproduction commands, and non-claims. |

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
collector failed to produce that evidence. This is classified
`SELECTOR_ATTESTATION_INCOMPLETE`. A non-null reference that does not resolve to
an exact declared regular file is contradictory and therefore
`SELECTOR_ATTESTATION_INVALID`.

All four phases must bind to one trusted ranked job ID, run ID, workflow SHA,
host class, collector identity, and capture epoch. The current phases must bind
to the current source revision and census; the baseline timing phase must bind
to the pinned source revision and census.

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
- Physical JSON: strict UTF-8, duplicate object keys forbidden, compact
  `ensure_ascii=false` sorted-key JSON, comma/colon separators, and one trailing
  LF.

This framing prevents delimiter ambiguity, row-order ambiguity, implicit
absence, and a self-referential entry-point file hash.

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
may exist only in one source revision when and only when the separately trusted
revision policy lists its name and exact current/pinned row identifiers, marks
the absent revision explicitly, and states
`reason: "selector_added_or_removed_by_source_revision"`. The validator rejects
an exception for a name present in both censuses, an undeclared revision-only
name, inconsistent row identifiers, and every other reason string.

## Separate trust boundary

Self-consistency is insufficient. The validator requires a separately supplied
trusted expectations JSON object that pins:

- current and pinned source revisions;
- workflow SHA;
- current and pinned census file SHA-256 values;
- ranked job ID and run ID;
- host class;
- collector identity;
- capture epoch; and
- installed-authority foreign digest.

The evidence bundle cannot redefine these values. Mismatch is invalid, not
incomplete. This prevents an internally consistent but foreign or replayed
bundle from becoming authoritative merely by hashing itself.

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
| `SELECTOR_ATTESTATION_INCOMPLETE` | The envelope is otherwise valid, but one or more mandatory evidence references are explicitly `null`. The output reports the first missing reference. |
| `SELECTOR_ATTESTATION_STATIC_RESUME_READY` | All required static evidence exists and every declared invariant validates against separate trusted expectations. This is not an authority, correctness, timing, or promotion decision. |

Invalid always takes precedence over incomplete: the validator first checks
schema, trust, physical files, census, snapshots, hashes, forwarding, and
cross-process equality, then reports explicit missing references only if no
invalid condition exists.

## Synthetic validation matrix

Two independent CLI invocations produced byte-identical JSON output with
SHA-256 `634c1f151541dcb840c8f992a50dc1c5646baf4581204faa016f6a62dfe300da`.
The fixture catalog SHA-256 reported by the validator is
`6c5afed4a8e1fae55841d997d8a10e0d913cfe1bc921dcaf6c67a0dfca3914e3`.
All 27 cases passed their expected classification and, for invalid cases,
expected fail-closed code.

### Valid and incomplete controls

| Fixture | Expected result |
| --- | --- |
| `all_four_explicit_absence` | `SELECTOR_ATTESTATION_STATIC_RESUME_READY` |
| `identical_intentional_map_with_revision_rule` | `SELECTOR_ATTESTATION_STATIC_RESUME_READY` |
| `first_missing_pinned_timed_worker` | `SELECTOR_ATTESTATION_INCOMPLETE`; first missing `pinned_baseline_timed.worker_snapshot` |

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

The self-test materializes bundles only under temporary directories, hashes the
actual physical fixture bytes, validates through the public bundle path, and
removes temporary evidence after each run. It does not inspect the host
environment.

## Reproduction

```bash
PYTHONDONTWRITEBYTECODE=1 python3 \
  research/validate_ranked_selector_attestation.py --help

PYTHONDONTWRITEBYTECODE=1 python3 \
  research/validate_ranked_selector_attestation.py --self-test \
  > /tmp/selector_attestation_run1.json

PYTHONDONTWRITEBYTECODE=1 python3 \
  research/validate_ranked_selector_attestation.py --self-test \
  > /tmp/selector_attestation_run2.json

cmp -s /tmp/selector_attestation_run1.json \
  /tmp/selector_attestation_run2.json

python3 -m json.tool \
  research/ranked_selector_attestation.schema.json >/dev/null
python3 -m json.tool \
  research/ranked_selector_attestation_fixtures.json >/dev/null
```

Prospective real-bundle validation is:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 \
  research/validate_ranked_selector_attestation.py \
  --bundle ORGANIZER_BUNDLE_DIR \
  --expectations ORGANIZER_TRUSTED_EXPECTATIONS.json
```

## Conclusion

The schema, validator, fixtures, and audit form a complete static contract for
organizer-produced ranked selector evidence. They close format, comparison,
physical-integrity, forwarding, revision-policy, and secret-safety ambiguity at
the contract level. They deliberately leave the real ranked environment open
until an organizer captures a real same-session bundle and supplies independent
trusted expectations.

`RANKED_SELECTOR_ATTESTATION_CONTRACT_READY`
