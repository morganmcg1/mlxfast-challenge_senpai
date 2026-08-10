# Ranked Authority Evidence Bundle Audit

## Result

`RANKED_AUTHORITY_EVIDENCE_CONTRACT_READY`

The schema, validator, and synthetic fixture suite define a deterministic static
contract for deciding whether a future ranked-authority evidence bundle is
invalid, incomplete, or ready for static resume review. This result does **not**
claim that any ranked run satisfies the contract.

## Scope and authority boundary

- Assignment branch: `cedar-tanjiro/ranked-authority-evidence-contract`
- Assignment base: `899c08da4c0484b90b95a7fd93ab979b608c783f`
- This audit is contract-only. It did not access `/opt`, a ranked worker, model
  weights, hidden artifacts, credentials, secrets, submission receipts, or
  authoritative ranked evidence.
- No build, model execution, timing run, GPU job, or official submission was
  performed.
- Assignment prior-audit assertions were treated as requirements to encode, not
  as independently verified runtime facts.
- Every fixture is synthetic and marked non-authoritative. Passing the positive
  fixture proves contract self-consistency only.
- W&B: N/A. This static contract task had no experiment run or metric stream.

## Contract artifacts

| Path | Purpose |
| --- | --- |
| `research/ranked_authority_evidence_bundle.schema.json` | Strict Draft 2020-12 manifest schema |
| `research/validate_ranked_authority_evidence_bundle.py` | Standard-library physical and semantic validator |
| `research/ranked_authority_evidence_bundle_fixtures.json` | Synthetic positive, incomplete, and contradiction controls |
| `research/ranked_authority_evidence_bundle_audit.md` | Audit result and organizer collection handoff |

The schema and validator bind evidence to:

- repository, base revision, workflow, run, job, host, platform, OS, and capture
  interval identities;
- exact artifact roles, relative paths, SHA-256 digests, sizes, modes, UID/GID,
  ACLs, flags, link counts, device/filesystem identity, and regular-file status;
- artifact install provenance and install-time source digests;
- actors, process identities, UID/GID transitions, phases, typed events, typed
  graph edges, monotonic ordering, and load-epoch bounds;
- reaper behavior and the exact declared survivor policy;
- sandbox profile generation inputs, injected profile identity, mounts,
  read/write rights, weights-root confinement, and capabilities;
- allowlisted environment variable names and redacted secret-name accounting,
  without accepting secret values;
- generation and authority digests over canonical JSON; and
- exactly one explicitly identified missing authority fact when the bundle is
  incomplete.

The validator reads the declared artifacts from the bundle root and checks the
actual bytes and physical metadata with `lstat`-based controls. Manifest-only
claims cannot produce `STATIC_RESUME_READY` when the physical evidence drifts.

## Required event chain

A complete bundle must establish this ordered chain:

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

Typed `happens_before`, `spawn`, `sandbox_injection`, and
`load_epoch_bounds` edges must form an acyclic graph and agree with event
sequence numbers and timestamps.

The reaper fixture intentionally declares `TERM`, then `KILL`, with residual
survivors classified as `warn`. The reaper event must repeat that policy
exactly and must itself have `failure_behavior: warn`. The validator preserves
that declared semantics; it does not silently promote a warning policy to a
failure policy.

## Classification contract

- `INVALID`: a contradiction, malformed claim, undeclared authority, physical
  mismatch, secret-value leak, identity drift, ordering error, or self-declared
  artifact makes the bundle unsuitable for static resume review.
- `INCOMPLETE`: there is no contradiction, but exactly one first missing
  authority fact is explicitly identified with its reason. An incomplete
  bundle cannot be promoted by inference.
- `STATIC_RESUME_READY`: every required authority is present, physically
  verified, internally consistent, and cryptographically bound. This state
  means only that static evidence review may resume; it is not a ranked verdict.

## Deterministic control matrix

The fixture runner hydrated actual temporary files for every case, updated the
positive manifest with their observed physical metadata, applied one mutation,
and checked the expected state.

| Expected state | Fixture cases |
| --- | --- |
| `STATIC_RESUME_READY` | `complete-synthetic-bundle` |
| `INCOMPLETE` | `missing-profile-generator-input` |
| `INVALID` | `physical-byte-drift`, `declared-hash-drift`, `declared-size-drift`, `bundle-path-escape`, `symbolic-link-artifact`, `duplicate-artifact-role` |
| `INVALID` | `owner-mismatch`, `mode-mismatch`, `acl-mismatch`, `hardlink-ambiguity`, `workflow-identity-drift`, `base-identity-drift`, `job-identity-drift`, `stale-capture` |
| `INVALID` | `missing-install-provenance`, `profile-hash-mismatch`, `secret-value-leak`, `undeclared-environment-name`, `uid-gid-transition-contradiction`, `survivor-policy-contradiction` |
| `INVALID` | `event-cycle`, `event-order-reversal`, `mount-path-contradiction`, `absent-self-declared-artifact` |

Control totals:

- 26 cases passed.
- 1 case classified `STATIC_RESUME_READY`.
- 1 case classified `INCOMPLETE`.
- 24 cases classified `INVALID`.
- Fixture source SHA-256:
  `a4c45c43262c132367a812607ba8e67af7247f80a15bdf6f752d27514c3346e9`.
- Two independent fixture-run outputs were byte-identical, each with SHA-256:
  `36fe7495c32c35acc011d7949c2e89dbae6c7d9c6eada5c50fef39e5faf3b15d`.
- The schema passed Draft 2020-12 schema validation, and the hydrated positive
  fixture passed instance validation against it.

## Reproduction

Run the synthetic controls:

```bash
python3 -m py_compile \
  research/validate_ranked_authority_evidence_bundle.py
python3 research/validate_ranked_authority_evidence_bundle.py \
  --run-fixtures \
  research/ranked_authority_evidence_bundle_fixtures.json
```

Check deterministic output:

```bash
python3 research/validate_ranked_authority_evidence_bundle.py \
  --run-fixtures research/ranked_authority_evidence_bundle_fixtures.json \
  > /tmp/ranked-authority-run-1.json
python3 research/validate_ranked_authority_evidence_bundle.py \
  --run-fixtures research/ranked_authority_evidence_bundle_fixtures.json \
  > /tmp/ranked-authority-run-2.json
cmp /tmp/ranked-authority-run-1.json /tmp/ranked-authority-run-2.json
shasum -a 256 /tmp/ranked-authority-run-1.json
```

Validate a future read-only bundle:

```bash
python3 research/validate_ranked_authority_evidence_bundle.py \
  --bundle-root /path/to/read-only-bundle \
  --manifest /path/to/read-only-bundle/bundle.json
```

The validator emits canonical compact sorted JSON followed by one newline.
Organizers should preserve the bundle after collection and review the emitted
state, errors, warnings, and first missing authority fact without editing the
source manifest.

## Organizer collection handoff

Collect the future bundle from a trusted collector in the same ranked job,
after artifact installation and before evidence can be replaced. The collector
should:

1. Copy the exact installed files into a read-only evidence root without
   following symbolic links.
2. Record SHA-256 and size from those copied bytes plus mode, UID/GID, ACL,
   flags, link count, device, filesystem, and install provenance.
3. Record repository/base/workflow/run/job/host/platform/OS identities and the
   capture interval.
4. Record actors, parentage, UID/GID transitions, phases, typed events, event
   edges, and the worker load epoch.
5. Record the reaper signals and residual-survivor disposition exactly as the
   ranked job applied them.
6. Record the sandbox generator, all generator inputs, generated profile,
   injected profile digest, mounts, rights, weights root, and capabilities.
7. Record only environment variable names permitted by policy. Never place
   secret values in the manifest, fixtures, logs, or audit.
8. Compute the canonical generation digest and authority digest only after all
   other fields and physical evidence are final.
9. If one authority fact cannot be collected, identify only the first missing
   fact and its reason; do not infer it from a neighboring phase.

A future authoritative collection may conclude `INVALID`, `INCOMPLETE`, or
`STATIC_RESUME_READY`. This contract intentionally does not predict which.

## Scope verification target

The intended branch diff is exactly the four contract artifacts listed above.
No runtime, kernel, transform, harness, workflow, model, or package file is part
of this result.

---

This audit was generated by an AI agent (OpenHands) on behalf of the user.
