# Candidate Evidence Bundle Contract Audit

## Result

`CANDIDATE_EVIDENCE_CONTRACT_READY`

This result means the static evidence contract and its deterministic adversarial
fixture suite are ready. It is not candidate timing evidence, a ranked result,
or submission authorization.

## Scope

This assignment adds only:

- `candidate_evidence_bundle.schema.json`, a JSON Schema 2020-12 contract;
- `validate_candidate_evidence_bundle.py`, a standard-library fail-closed
  validator and deterministic self-test runner;
- `candidate_evidence_bundle_fixtures.json`, four positive fixture profiles and
  28 negative mutations; and
- this audit.

No model code, build, inference, benchmark, W&B run, live receipt, or official
submission was produced.

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

The root schema is versioned as `candidate-evidence-bundle/v1`, rejects unknown
properties, and fixes the immutable terminal hashes named in the assignment.
The validator additionally performs semantic checks that JSON Schema alone
cannot express.

### Identity and content joins

Every phase is joined to one immutable identity tuple:

- assignment, revision, bundle, base commit, and candidate commit;
- canonical candidate-surface digest;
- benchmark-contract and configuration digests;
- fixture, window, and component identities; and
- hardware, toolchain, thermal-policy, and telemetry classes.

The candidate surface is canonicalized as a path-sorted list of
`{path,size,sha256}` records using UTF-8 compact JSON with sorted object keys
and one trailing line feed. Its SHA-256 must match every phase and artifact
claim. Reusing a receipt or candidate artifact under another revision therefore
fails its identity join.

### Physical artifacts

Artifact claims are checked against bytes under an explicit artifact root.
The validator rejects:

- absolute paths and paths escaping the root;
- symlinks in any path component;
- non-regular files;
- duplicate roles or duplicate paths;
- missing or unexpected roles;
- byte-count, declared-size, or SHA-256 drift; and
- unit or identity drift.

The self-test mutates actual artifact bytes and creates an actual symlink; it
does not merely edit manifest strings.

### Phase evidence

Isolated evidence binds exact ABBA and BAAB order sequences, raw rows,
uncertainty estimates, perturbation labels, stop conditions, and chain joins.
Whole-model evidence binds mirrored order rows, raw timings, recomputed means,
component factors, weighted factor, floors, gates, and exact checked-token
counts. Ranked evidence adds a distinct official M5 receipt whose identities,
measurements, gates, and content address all rejoin the bundle.

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

The 28 negative mutations cover:

- base, candidate, payload-surface, benchmark-contract, configuration, fixture,
  window, and revision identity drift;
- actual artifact-byte mutation, manifest hash and size drift, path escape,
  symlink traversal, duplicate role/path, unit drift, and candidate-artifact
  reuse;
- ranked hardware drift, ABBA/BAAB order corruption, label reuse, and missing
  uncertainty;
- zero checked tokens, correctness failure, hidden-gate failure, and memory-gate
  failure;
- component-floor failure and an exact ranked-margin tie;
- fabricated numeric summaries on censored evidence;
- ranked receipt reuse under another revision; and
- terminal classification contradiction.

Each negative fixture declares its expected stable error code. The self-test
requires every case to produce exactly that code.

## Verification

The focused static checks are:

```bash
python3 -m py_compile research/validate_candidate_evidence_bundle.py
python3 research/validate_candidate_evidence_bundle.py --self-test > /tmp/candidate-evidence-a.json
python3 research/validate_candidate_evidence_bundle.py --self-test > /tmp/candidate-evidence-b.json
cmp -s /tmp/candidate-evidence-a.json /tmp/candidate-evidence-b.json
```

Both self-test runs are byte-identical. The result contains 32 cases, reports
`deterministic: true`, and has canonical result digest:

```text
f4ed68e47ab0aa70e0df1f7c68d7da895a522c70baf69b8789bb5a97f0ea94cc
```

The terminal status is `CANDIDATE_EVIDENCE_CONTRACT_READY`.

## Limitations

- All fixtures are synthetic contract tests, not performance measurements.
- No live M5 receipt exists in this assignment, so no real candidate is ranked.
- The contract intentionally defines no M4-to-M5 transfer model.
- Receipt uniqueness across separate valid bundles requires an external receipt
  registry; this validator guarantees content and revision binding within the
  bundle it is given.
- The schema and validator classify evidence only. They cannot authorize an
  official submission, and the schema fixes `submission_authorization` to
  `false`.
