# Ranked transformed-weight load provenance audit

## Terminal status

**RANKED_WEIGHT_PROVENANCE_INDETERMINATE**

The single unavailable authority required to continue is the ranked-installed
`/opt/bench/bench-exec.sh`. Its exact bytes and metadata were not readable on
this host. The assignment explicitly forbids inferring its behavior from
repository comments, so the audit stopped at that authority boundary.

- Assignment: `cedar-tanjiro-ranked-weight-load-provenance-audit-20260810`
- Pull request: `#671`
- Audited production base: `5593d8f4a394023e83dfbfe11ef01fa01a5b7f15`
- Assignment head before these research artifacts: `a9b25254e1b21d5fb56f7beaacf78b1f5735159f`
- Production changes: none
- W&B: not applicable

This result proves neither a safe no-go nor a provenance defect. It records the
first authority-dependent edge that could not be resolved without violating the
assignment's stop rule.

## Stop condition and unresolved edge

The read-only availability check found no readable ranked bridge at
`/opt/bench/bench-exec.sh`. The audit therefore did not proceed to the later
`/opt/bench-runner/measure-job.sh` or injected Seatbelt authorities.

The unresolved edge is:

```text
trusted runner hash of transformed weight tree
  -> bench-exec-mediated reaper / worker launch / sandbox injection
  -> worker's independent pathname opens during the load epoch
```

The bridge is necessary because the ranked workflow routes participant
transform, gates, correctness, timing, and reaping through it
(`.github/workflows/benchmark.yml:53-67`, `1074-1115`, `1254-1266`). The
repository describes a UID drop and injected worker Seatbelt profile, but those
comments are not the ranked-installed authority. Exact bridge bytes and
metadata are needed to establish:

- effective UID/GID, groups, inherited environment, and working directory;
- process/session ancestry and whether any same-UID process can survive or
  appear between hashing and independent worker opens;
- path, mount, temporary-directory, and weight-tree confinement;
- exact injected Seatbelt profile or generator and its ownership/immutability;
- ordering of reaping, profile injection, worker creation, and the load epoch.

Without those facts, the audit cannot prove that every participant-controlled
actor capable of changing a pathname-visible weight byte is absent for the
entire interval. Absence of that proof is not evidence that such an actor
exists.

## Partial phase DAG

| Phase | Observed authority | Static conclusion | Status |
|---|---|---|---|
| Participant transform | `.github/workflows/benchmark.yml:1074-1115` | Transform is invoked through `MLXFAST_BENCH_EXEC` and authors the ranked weight tree. | Source reviewed |
| Trusted digest | `.github/workflows/benchmark.yml:1120-1122`; `.github/scripts/hash-weights-directory.sh:11-59` | Trusted shell hashes the transformed tree immediately after transform. | Source reviewed |
| Reap and worker launch | `.github/workflows/benchmark.yml:1254-1266`; ranked-installed `/opt/bench/bench-exec.sh` | Reaper and participant phases cross the missing bridge authority. | **Unresolved; stopped** |
| Runtime sandbox | `benchmark.sh:1510-1565`, `2060-2075` | Repository fallback is bypassed when the bridge injects `MLXFAST_RUNTIME_WORKER_SANDBOX_PROFILE`; exact ranked policy is external. | Not evaluated after stop |
| Independent worker opens | Runtime model/loader path | Path-versus-descriptor behavior and all opened shards must be traced only after the bridge edge is resolved. | Not evaluated after stop |
| Gate/timing parity | `.github/scripts/overlay-paired-timing.sh:75-107`; `.github/scripts/validate-benchmark-artifacts.sh:280-313` | Parent-observed hash/count/bytes are compared, but that alone does not identify bytes opened by a worker. | Source reviewed; not decisive |

## Digest and inventory evidence reached before stopping

The trusted shell digest implementation:

- requires the root to be a non-symlink directory;
- rejects non-directory and non-regular entries;
- rejects multiply linked regular files;
- enumerates regular files using NUL-delimited names and `LC_ALL=C sort -z`;
- ignores exactly `.benchmark-source.sha256` and `.gitkeep`; and
- hashes each relative path, a NUL byte, the raw per-file SHA-256 digest, and a
  trailing NUL before hashing the aggregate stream.

These semantics are defined in
`.github/scripts/hash-weights-directory.sh:11-59`. They cover configuration,
index and metadata files, ordinary safetensor shard headers and payload bytes,
and any other regular file not explicitly ignored. Swift-versus-shell parity
and the exact worker-open inventory were not evaluated after the mandatory
stop.

The workflow's copied workspace receives broad bench-identity ACL capability
while selected source and harness paths receive explicit denies
(`.github/workflows/benchmark.yml:701-796`). This is insufficient to decide
load-epoch safety without the installed bridge's identity, confinement, and
process-lifetime behavior. The repository reaper also warns rather than fails
on residual survivors (`.github/scripts/reap-bench-processes.sh:57-70`), making
the missing bridge's process boundary material rather than cosmetic.

## TOCTOU window disposition

| Window | Disposition |
|---|---|
| Transform completion -> trusted digest | Parent ordering is visible; actor lifetime/capability still depends on the missing bridge. |
| Trusted digest -> reaper | Unresolved at the stopped bridge edge. |
| Reaper -> worker spawn | Unresolved at the stopped bridge edge. |
| Worker spawn -> each independent open | Not evaluated after stop. |
| First open -> last shard/header/payload open | Not evaluated after stop. |
| Gates -> timed worker reuse or respawn | Not evaluated after stop. |

No race, permission, descriptor-pinning, symlink-swap, hardlink-swap,
rename/unlink, mmap/private-copy, or forced-partial-read control was executed.
After the required authority was missing, such controls would have been
non-decisive and contrary to the instruction to stop. No build, transform,
worker, model, benchmark, weight mutation, cache mutation, environment mutation,
or official submission occurred.

## Prior-proof search

A bounded search of current authorized ancestry and `research/` for weight
provenance, load-epoch, exact-worker-byte, digest, and bridge terms found no
complete prior proof that closes this edge. Nearby provenance audits concern
other payload classes and do not establish transformed-weight bytes opened by
each ranked worker.

## Smallest next action

An organizer or ranked-box operator should provide, read-only, the exact
ranked-installed `/opt/bench/bench-exec.sh` bytes plus owner, mode, ACL, and the
exact injected worker Seatbelt profile or generator proven to be used for the
audited job. The audit can then resume at the stopped edge; no production patch
or optimization is nominated now.

_This audit was generated by an AI agent (OpenHands) on behalf of the assigned
research student._
