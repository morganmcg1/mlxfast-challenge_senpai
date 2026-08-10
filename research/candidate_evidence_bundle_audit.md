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
  35 negative mutations; and
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

The root schema is versioned as `candidate-evidence-bundle/v2`, rejects unknown
properties, and fixes the immutable terminal hashes named in the assignment.
The validator additionally performs semantic checks that JSON Schema alone
cannot express.

### External trusted context

Bundle claims are not self-authenticating. Validation therefore requires a
separate trusted-context JSON file whose canonical SHA-256 is supplied inside
the bundle and then recomputed. The context pins:

- assignment, revision, bundle, base commit, and candidate commit;
- canonical candidate-surface records and digest;
- benchmark contract, configuration, fixture, windows, and component IDs;
- required artifact roles, paths, sizes, and hashes; and
- ranked receipt identity, official hardware, toolchain, thermal, and telemetry
  facts.

A coherent attacker rewrite of the bundle, artifacts, revision, and hashes still
fails unless it also changes this independently supplied trusted input.

### Candidate-surface binding

The candidate surface is canonicalized as a path-sorted list of
`{path,size,sha256}` records using UTF-8 compact JSON with sorted object keys
and one trailing line feed. The validator independently reads each regular,
non-symlink file beneath `--candidate-root`, checks its physical size and
SHA-256 against the trusted records, recomputes the surface digest, and rejoins
that digest to every phase and artifact claim.

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

The 35 negative mutations cover:

- base, candidate, payload-surface, benchmark-contract, configuration, fixture,
  window, and revision identity drift;
- actual artifact-byte mutation, manifest hash and size drift, path escape,
  symlink traversal, duplicate role/path, unit drift, and candidate-artifact
  reuse;
- arbitrary ranked bytes with a refreshed manifest hash;
- semantic artifact rewrites with refreshed size and hash;
- physical candidate-surface byte mutation;
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

Each negative fixture declares at least one expected stable error code. The
self-test requires every case to contain every declared code while also proving
that all four positive profiles retain their intended classification.

## Verification

The focused static checks are:

```bash
python3 -m py_compile research/validate_candidate_evidence_bundle.py
python3 research/validate_candidate_evidence_bundle.py --self-test > /tmp/candidate-evidence-a.json
python3 research/validate_candidate_evidence_bundle.py --self-test > /tmp/candidate-evidence-b.json
cmp -s /tmp/candidate-evidence-a.json /tmp/candidate-evidence-b.json
```

A standalone bundle validation requires all three external roots:

```bash
python3 research/validate_candidate_evidence_bundle.py BUNDLE.json \
  --artifact-root ARTIFACT_ROOT \
  --candidate-root CANDIDATE_ROOT \
  --trusted-context TRUSTED_CONTEXT.json
```

Both self-test runs are byte-identical. The result contains 39 cases, reports
`deterministic: true`, uses schema ID
`https://mlxfast.invalid/schemas/candidate-evidence-bundle-v2.json`, and has
canonical result digest:

```text
77177cacc866f268233e5c915e4263436848eec6768e59b8b12556e64ea5d0d9
```

The terminal status is `CANDIDATE_EVIDENCE_CONTRACT_READY`.

## Limitations

- All fixtures are synthetic contract tests, not performance measurements.
- No live M5 receipt exists in this assignment, so no real candidate is ranked.
- The contract intentionally defines no M4-to-M5 transfer model.
- The validator checks trusted-context integrity and all joins, but the caller
  remains responsible for obtaining that context from an authoritative source.
- Receipt uniqueness across separate valid bundles requires an external receipt
  registry; this validator guarantees content and revision binding within the
  bundle it is given.
- The schema and validator classify evidence only. They cannot authorize an
  official submission, and the schema fixes `submission_authorization` to
  `false`.
