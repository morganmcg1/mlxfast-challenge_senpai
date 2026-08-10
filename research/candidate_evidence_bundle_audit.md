# Candidate Evidence Bundle Contract Audit

## Result

`CANDIDATE_EVIDENCE_ROOTS_FAIL_CLOSED`

This result means the static evidence contract now rejects hostile candidate
and artifact filesystem roots deterministically while preserving every merged
scientific control. It is not candidate timing evidence, a ranked result, or
submission authorization.

## Scope

The contract consists of:

- `candidate_evidence_bundle.schema.json`, a JSON Schema 2020-12 contract;
- `validate_candidate_evidence_bundle.py`, a standard-library fail-closed
  validator and deterministic self-test runner;
- `candidate_evidence_bundle_fixtures.json`, four positive fixture profiles,
  45 negative mutations, and 31 filesystem-boundary controls; and
- this audit.

No model code, build, inference, benchmark, W&B run, live receipt, or official
submission was produced. All measurements, candidate files, trusted inputs, and
artifacts in the fixture suite are synthetic contract-test data.

## Frozen benchmark rules

| Rule | Contract value |
| --- | --- |
| Weighted score | `decode_factor ** 0.75 * prefill_factor ** 0.25` |
| Component floors | decode and prefill factors each `>= 0.95` |
| Ranked margin | weighted factor strictly `> 1.0037802719941367788` |
| Prefill window | 512 supplied tokens |
| Decode window | 512-token seed plus 128 one-token teacher-forced steps |
| Ranked hardware | official M5 Max class |
| Local M4 evidence | directional only; never sufficient for ranked status |
| Authorization | evidence classification never grants submission authority |

The score, floors, window, official-hardware distinction, and correctness gates
come from the assignment-authorized benchmark contract, scoring sources, and
research audits. The assignment also names
`research/local_amdahl_realization_audit.md`; that file is absent from this
checkout. The implementation therefore preserves only the supplied lesson that
an incomplete isolated-to-whole-model join is not numeric whole-model evidence,
and does not invent or recompute missing source facts.

## Contract structure

The root schema is versioned as `candidate-evidence-bundle/v3`, rejects unknown
properties, and fixes the immutable terminal hashes named in the assignment.
The validator additionally performs semantic checks that JSON Schema alone
cannot express.

### External trusted context

Bundle claims are not self-authenticating. Validation therefore requires both a
separate trusted-context JSON file and its verifier-owned canonical SHA-256 as a
separate CLI input. The bundle's context digest is only a secondary binding; it
is never the trust root. The context pins:

- assignment, revision, bundle, base commit, and candidate commit;
- canonical candidate-surface records and digest;
- benchmark contract, configuration, fixture, windows, and component IDs;
- exact isolated and whole-model environment/protocol facts: host model, chip,
  OS, toolchain, thermal policy, telemetry policy, and protocol;
- required artifact roles, paths, sizes, and hashes; and
- ranked receipt identity and a digest of the distinct official M5 environment.

A coherent rewrite of the bundle, artifacts, trusted context, and all embedded
hashes still fails without the separately supplied verifier-owned context pin.

### Candidate-surface binding

The candidate surface is canonicalized as a path-sorted list of
`{path,size,sha256}` records using UTF-8 compact JSON with sorted object keys
and one trailing line feed. The validator recursively enumerates
`--candidate-root` from one descriptor-anchored root, opening every child
relative to its already-open parent descriptor. The physical file set must
equal the trusted submitted surface exactly. Extra or unlisted files, omitted
or missing listed files, symlinks, and non-regular entries are rejected. It then
checks every file's physical size and SHA-256, recomputes the surface digest,
and rejoins that digest to every phase and artifact claim.

Candidate and artifact traversal requires an integer `O_RDONLY`, nonzero
`O_CLOEXEC`, `O_DIRECTORY`, `O_NOFOLLOW`, and `O_NONBLOCK`, descriptor-relative
`open`, `stat`, and `readlink`, descriptor-based directory enumeration, and the
`os.stat in os.supports_follow_symlinks` capability signal required for
`stat(dir_fd=..., follow_symlinks=False)`. If any safety primitive is absent,
the validator emits only `DESCRIPTOR_SAFETY_UNAVAILABLE` at
`$verifier.filesystem` and performs no filesystem traversal. A deterministic
capability override proves the exact message
`required descriptor safety is unavailable: stat(dir_fd,follow_symlinks=False)`,
that no filesystem hook fired, and that zero descriptors were opened. Each root
is opened exactly once; root and nested objects are checked with no-follow
metadata, descriptor identity, and directory snapshots before and after their
work. Symlinks are classified only from no-follow metadata, and `readlink` is
used solely for lexical escape reporting; symlink targets are never resolved or
followed. File bytes are opened component-by-component relative to parent
descriptors with no-follow and nonblocking flags, checked again with `fstat`,
and read from that descriptor. All tracked descriptors close on success and
every structured or unexpected exception path. These checks turn root,
nested-directory, and file replacement races into deterministic disappearance,
identity-change, scan-change, unreadable, non-regular, symlink,
inspection-failed, or read-failed errors.

### Physical and semantic artifacts

Artifact claims are checked against bytes under `--artifact-root`. Each artifact
must be canonical UTF-8 JSON with exactly one trailing line feed. Its role-
specific schema and parsed content are validated, and the semantic evidence is
compared exactly with the corresponding bundle phase or ranked receipt. The
validator also rejoins every manifest entry to the separately trusted artifact
pin.

It rejects:

- absolute paths, path escape, symlinks, and non-regular files;
- duplicate roles or paths and missing or unexpected roles;
- byte-count, declared-size, SHA-256, or trusted-pin drift;
- arbitrary bytes even when their manifest hash is refreshed;
- canonical JSON that was semantically rewritten and rehashed;
- unit or identity drift; and
- candidate-surface bytes that differ from the trusted physical records.

The self-test mutates actual artifact and candidate bytes and creates an actual
symlink; it does not merely edit manifest strings.

### Phase evidence

Isolated evidence binds exact ABBA and BAAB order sequences, raw rows,
uncertainty estimates, perturbation labels, stop conditions, and chain joins.
Whole-model evidence binds mirrored order rows, raw timings, recomputed means,
component factors, weighted factor, floors, gates, and exact checked-token
counts. Numeric isolated-to-whole-model evidence requires exact equality of the
trusted host model, chip, OS, toolchain, thermal policy, telemetry policy, and
protocol across both phases. Ranked evidence remains a distinct official M5
receipt; its environment is externally pinned by canonical digest and rebound
inside the receipt along with identities, measurements, gates, and content.

All derived numeric values are recomputed with Python `Decimal` at precision 80
and `ROUND_HALF_EVEN`; serialized summaries are never trusted as authoritative.
The strict ranked comparison uses the exact immutable decimal threshold, so an
exact tie is rejected.

## Classification semantics

| Classification | Required evidence | What it does not prove |
| --- | --- | --- |
| `INVALID` | Any schema, identity, artifact, protocol, arithmetic, gate, or terminal contradiction | Nothing from the rejected bundle |
| `CENSORED_VALID` | A valid censored isolated attempt with stop evidence and no fabricated numeric summary | Isolated completeness, whole-model benefit, or ranked margin |
| `ISOLATED_COMPLETE` | Complete joined ABBA and BAAB isolated evidence with uncertainty | Whole-model realization or ranked performance |
| `WHOLE_MODEL_COMPLETE` | Complete matched whole-model rows, factors, floors, correctness, census, and memory gates | Ranked margin when the evidence is local or non-M5 |
| `RANKED_MARGIN_COMPLETE` | A distinct official M5 receipt, all joins and gates, both floors, and weighted factor strictly above the frozen margin | Permission or authorization to submit |

The local M4 whole-model fixture is deliberately classified
`WHOLE_MODEL_COMPLETE`, never `RANKED_MARGIN_COMPLETE`.

## Fixture coverage

The four positive profiles are:

1. a censored but structurally valid isolated attempt;
2. isolated-only ABBA plus BAAB evidence;
3. complete local M4 whole-model evidence; and
4. official M5 ranked evidence just above the strict margin.

The 45 negative mutations cover:

- base, candidate, payload-surface, benchmark-contract, configuration, fixture,
  window, and revision identity drift;
- actual artifact-byte mutation, manifest hash and size drift, path escape,
  symlink traversal, duplicate role/path, unit drift, and candidate-artifact
  reuse;
- arbitrary ranked bytes with a refreshed manifest hash;
- semantic artifact rewrites with refreshed size and hash;
- physical candidate-surface byte mutation, extra and omitted files, symlinks,
  and non-regular entries;
- coherent isolated-to-whole-model host, toolchain, thermal, telemetry, and
  protocol drift;
- coherent bundle and trusted-context resealing without an external pin;
- coherent revision relabeling across the bundle and artifact;
- local M4 evidence relabeled as official M5 evidence;
- ranked receipt benchmark, base, and component drift;
- ranked hardware drift, ABBA/BAAB order corruption, label reuse, and missing
  uncertainty;
- zero checked tokens, correctness failure, hidden-gate failure, and memory-gate
  failure;
- component-floor failure and an exact ranked-margin tie;
- fabricated numeric summaries on censored evidence;
- ranked receipt reuse under another revision; and
- terminal classification contradiction.

The 31 filesystem controls require exact error-code and JSON-path sets,
`INVALID` classification, and exit code 1 for missing, symlink, regular-file,
and FIFO roots; listed directory, FIFO, and symlink entries; deterministic
disappearance and unreadability at the read boundary; absence of each required
nonzero descriptor-safety flag; and unavailable no-follow `stat` capability.
The capability control asserts the exact stable code, path, and message before
traversal, plus no hook invocation, zero opened descriptors, and no descriptor
leak. Real filesystem hooks replace candidate and artifact roots after
inspection and after opening, and replace nested directories and files during
candidate and artifact traversal. Each race fixture asserts that its hook fired,
every descriptor opened during that case was closed, and only the declared
stable error set was emitted. The harness separately proves that
`NotADirectoryError`, `PermissionError`, and generic `OSError` are converted to
stable filesystem errors while injected reader and schema `ValueError`
exceptions still propagate and close all tracked descriptors.

Each negative fixture declares at least one expected stable error code. The
self-test requires every case to contain every declared code while also proving
that all four positive profiles retain their intended classification. The
legacy 49-result canonical digest is frozen so the scientific controls cannot
silently change.

## Verification

The focused static checks are:

```bash
python3 -m py_compile research/validate_candidate_evidence_bundle.py
python3 research/validate_candidate_evidence_bundle.py --self-test > /tmp/candidate-evidence-r3-run1.json
python3 research/validate_candidate_evidence_bundle.py --self-test > /tmp/candidate-evidence-r3-run2.json
cmp /tmp/candidate-evidence-r3-run1.json /tmp/candidate-evidence-r3-run2.json
shasum -a 256 /tmp/candidate-evidence-r3-run1.json /tmp/candidate-evidence-r3-run2.json
```

A standalone bundle validation requires the external candidate, artifact, and
trusted-context inputs plus the separately distributed verifier-owned context pin:

```bash
python3 research/validate_candidate_evidence_bundle.py BUNDLE.json \
  --artifact-root ARTIFACT_ROOT \
  --candidate-root CANDIDATE_ROOT \
  --trusted-context TRUSTED_CONTEXT.json \
  --expected-context-sha256 EXPECTED_TRUSTED_CONTEXT_SHA256
```

Both external self-test invocations are byte-identical, and each invocation
executes the legacy and filesystem suites twice internally. The result reports
`deterministic: true`, contains 80 cases (49 legacy and 31 filesystem), and
uses schema ID
`https://mlxfast.invalid/schemas/candidate-evidence-bundle-v3.json`.

```text
legacy_results_digest:        75d8e716d4887e3b4aaac08499d44da281923d7de465ecf35de500bffc444124
prior filesystem subset digest: 33c3cded45453db59079c43850abd54cf2e3cc71b65fcae7778c59a0d5575578
filesystem_results_digest:    af0898822088414fda4c042c742e5bf0826ab05bab75c1eb2c0cffe7e4f2e1ae
results_digest:               d8a53be98de1190fd203151459432f7c0b6b2cece48a72efc76833259847c82b
self-test output SHA-256:      b90979735657db65a6ebc84bf4fcdc21189a79766c05cab2f548ce06f428238b
```

All 80 cases pass. The prior 30 filesystem-control records retain their frozen
r2 digest byte-for-byte. All seven exception-boundary assertions are true:
`descriptor_root_available`, `exception_descriptors_closed`,
`reader_not_a_directory`, `reader_os_error`, `reader_permission_error`,
`reader_value_error`, and `schema_value_error`. Every case reports all opened
descriptors closed, the legacy 49-case digest is unchanged, and the terminal
status is `CANDIDATE_EVIDENCE_ROOTS_FAIL_CLOSED`.

## Research-base non-overlap

The required assignment base is
`185bbee7f2fd9eb2e08a3a384806eace0f26fa83` and is merged into this revision.
The intervening base changes do not overlap the validator, fixture manifest, or
this audit. The exact-base diff remains scoped to these three assigned research
files.

## Limitations

- All fixtures are synthetic contract tests, not performance measurements.
- No live M5 receipt exists in this assignment, so no real candidate is ranked.
- The contract intentionally defines no M4-to-M5 transfer model.
- The validator checks trusted-context integrity and all joins, but the caller
  remains responsible for obtaining both the context and its expected digest
  from an authoritative verifier-owned source.
- Receipt uniqueness across separate valid bundles requires an external receipt
  registry; this validator guarantees content and revision binding within the
  bundle it is given.
- The schema and validator classify evidence only. They cannot authorize an
  official submission, and the schema fixes `submission_authorization` to
  `false`.
