# Ranked Authority Evidence Bundle Audit

## Result

`RANKED_AUTHORITY_EVIDENCE_CONTRACT_READY`

Revision r4 defines a deterministic static evidence contract in which a
separate verifier-owned trust document is unusable until its complete canonical
JSON representation matches an out-of-band lowercase SHA-256 pin. The bundle
and trust document cannot grant authority to themselves. Validation may classify
a structurally complete bundle as `STATIC_RESUME_READY`, but the command exits
successfully only for an authenticated complete ranked trust root and an
affirmative, non-synthetic authority claim.

This result does **not** upgrade PR #671. Its ranked audit remains
`RANKED_WEIGHT_PROVENANCE_INDETERMINATE`.

## Assignment and scope

- Branch: `cedar-tanjiro/ranked-authority-evidence-contract`
- Pull request: `#674`
- Revision: `cedar-tanjiro-ranked-authority-evidence-contract-20260810-r4-independent-trust-parent-process-binding`
- Required base: `f94cde18cca036a2cb6524335840f9d0b177a50b`
- Implementation parent: `8ebced3f94a5cb17d4643822e89cf786364f0230`
- Authority contract: `pr671-ranked-installed-authority/v3`
- This was a static-only task. It did not access `/opt`, a ranked worker, model
  data, timing data, receipts, submissions, credentials, or secrets.
- No build, benchmark, GPU/model execution, ranked job, submission, receipt
  polling, or W&B run occurred. W&B is not applicable.
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
The verifier must also supply `--external-trust-sha256` out of band. The pin is
exactly 64 lowercase hexadecimal characters and covers the complete canonical
trust JSON: UTF-8, recursively sorted object keys, compact separators, and one
trailing LF. Because the entire document is hashed, `source_kind` is covered;
it is also included in the collector-attestation payload.

Authentication occurs before schema or semantic use of any external-trust
field. Missing trust, missing pin, malformed pin, or digest mismatch returns
`INVALID` immediately with, respectively, `EXTERNAL_TRUST_REQUIRED`,
`EXTERNAL_TRUST_PIN_REQUIRED`, `EXTERNAL_TRUST_PIN_INVALID`, or
`EXTERNAL_TRUST_PIN_MISMATCH`. Consequently, changing and internally resealing
collector identity, authority, census, policy, or `source_kind` cannot establish
a new trust root without the verifier independently changing its pin.

Only after authentication may the external document supply:

- the exact PR #671 source scope above;
- accepted repository, base, workflow, run, and job identity;
- expected bundle authority claims;
- trusted collector identity and collector authority;
- the complete installed role/path census, its digest, and completeness state;
- event command policies for every required event; and
- a collector attestation over trust facts and collector-observed installed
  artifact identities.

A coherent but foreign target and a flipped bundle authority claim remain
rejected. Ranked source mode additionally pins the known repository, base,
workflow identity, and the two source-backed installed paths. Operational
ownership and distribution of both the trust file and its independent digest
remain the verifier's responsibility.

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
primary role, exec-chain roles, and argv digest. For every child actor, each
corresponding event's `process_start.ppid` must also equal the declared parent
actor's `pid`, independently of the child actor's own `ppid` field. The
validator rejects a wrong measure-job path, arbitrary `argv[0]`, argv resealing,
launcher-chain substitution, process-start identity drift, and coherent drift
of both child actor and event PPID. These joins prevent a valid artifact census
from being reused to describe a different launch or a child detached from its
claimed parent.

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
2. the complete external trust document matches the verifier-owned pin;
3. authenticated trust has `source_kind: ranked`;
4. its census is complete;
5. the bundle claims `authoritative: true`; and
6. the bundle claims `synthetic: false`.

The CLI returns zero only for `resumption_authorized: true`. Therefore neither a
bundle without authenticated external trust nor either structurally complete
synthetic positive can authorize PR #671 or produce CLI success.

## Deterministic controls

The fixture runner creates temporary files, hydrates copied and installed
metadata, seals command/process and trust linkage, then applies one named
mutation. It records the verifier pin independently before trust mutation when
the case is testing substitution. Every case declares its exact expected state,
full exact error-code set, `authoritative`, and `resumption_authorized`; subset
matching is not accepted. Every fixture is synthetic and non-authoritative.

Revision r4 adds these focused controls:

- `ranked-trust-detached-pin-positive`: ranked-shaped, correctly pinned,
  `STATIC_RESUME_READY`, but unauthorized because the bundle is synthetic;
- `missing-external-trust-pin`: exactly `EXTERNAL_TRUST_PIN_REQUIRED`;
- `invalid-external-trust-pin`: exactly `EXTERNAL_TRUST_PIN_INVALID`;
- `mismatched-external-trust-pin`: exactly `EXTERNAL_TRUST_PIN_MISMATCH`;
- `self-resealed-substituted-trust`: exactly
  `EXTERNAL_TRUST_PIN_MISMATCH` against the pre-mutation verifier pin;
- `source-kind-drift`: exactly `EXTERNAL_TRUST_PIN_MISMATCH` against that pin;
- `coherent-parent-ppid-drift`: exactly
  `PROCESS_PARENT_ACTOR_PID_MISMATCH` after child actor and event PPID drift
  together.

The earlier external-trust, command, closed-world, physical evidence, path,
identity, environment, actor, event graph, timestamp, generation, and
confinement controls remain with explicit complete error-code expectations.

Control totals:

- 54 of 54 fixture cases pass.
- 2 cases classify `STATIC_RESUME_READY` and remain unauthorized.
- 1 case classifies `INCOMPLETE`.
- 51 cases classify `INVALID`.
- Every case reports `authoritative: false` and
  `resumption_authorized: false` as expected.
- Fixture source SHA-256 reported by the runner:
  `deb4c2c38620e37c76bcd08c7d050bcd71dae57c29daabdfdfbe00c1f06316a6`.
- Both byte-identical result files have SHA-256:
  `7ce767911625c04413bdbd4b5e5562fc3eb8be1d5a0a6fa4a8b9abdecadecb00`.

The fixture suite is the direct contract check: absent trust, absent or invalid
pin, substituted trust, and synthetic positive trust all remain unauthorized.

## Reproduction

```bash
python3 -c 'import json; json.load(open("research/ranked_authority_evidence_bundle.schema.json")); print("schema-json-ok")'
python3 -m py_compile \
  research/validate_ranked_authority_evidence_bundle.py
python3 research/validate_ranked_authority_evidence_bundle.py \
  --run-fixtures \
  research/ranked_authority_evidence_bundle_fixtures.json \
  > /tmp/ranked-authority-r4-a.json
python3 research/validate_ranked_authority_evidence_bundle.py \
  --run-fixtures \
  research/ranked_authority_evidence_bundle_fixtures.json \
  > /tmp/ranked-authority-r4-b.json
cmp -s /tmp/ranked-authority-r4-a.json /tmp/ranked-authority-r4-b.json
shasum -a 256 /tmp/ranked-authority-r4-a.json /tmp/ranked-authority-r4-b.json
```

A future read-only bundle requires an independently supplied trust document and
its verifier-owned canonical SHA-256 pin:

```bash
python3 research/validate_ranked_authority_evidence_bundle.py \
  --bundle-root /path/to/read-only-bundle \
  --manifest /path/to/read-only-bundle/bundle.json \
  --external-trust /verifier-owned/path/external-trust.json \
  --external-trust-sha256 "$TRUST_SHA256"
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
