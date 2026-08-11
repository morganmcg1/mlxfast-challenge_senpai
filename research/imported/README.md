# Vendored copies of artifacts the handoff cites but did not contain

Author: meridian (Maple research advisor, AI agent). Created 2026-08-11 ~17:43Z, after close.

Manifest §10(vii) recorded **error 11**: two files the handoff documents cite by path live on
*closed-unmerged student branches*, not in this checkout, and `git branch -r` in this clone is a stale
cache that will deny they exist. That subsection told a reader the branch and commit and left the
retrieval as an exercise. §10(xvii) closes the hole instead: the branches are still on the remote and
an **explicit-refspec fetch** pulls them even though this clone's default refspec covers only the
advisor branch. Both files are therefore copied here, byte-for-byte.

| vendored path | original path | source branch | source commit | bytes | sha256 |
| --- | --- | --- | --- | --- | --- |
| `research/imported/epoch_gate.py` | `research/tools/epoch_gate.py` | `maple-nezuko/r129-g-preflight-validity-gates` | `c472f6e58efd8f81bcdc913e077f71863ad73330` | 6552 | `b177f6a6aa579fa16a191ae7d2daafd575b77295f2f40c0754302c946c33262a` |
| `research/imported/fern-r109f-interim-1200Z.md` | `research/fern-r109f-interim-1200Z.md` | `maple-fern/r109-integration-and-submission` | `bd47570461dce7471c15a7f7997a93988ff11b5c` | 36632 | `968bd8545f92a8b111a67a0ce5f898c9c321aa3378fe06a76ff2fae5d8334145` |

## How they were retrieved, and how to re-derive them

```
# 1. The heads are real. `git branch -r` in this clone will not show them; ls-remote asks the server.
git ls-remote origin 'refs/heads/maple-nezuko/r129-g*' 'refs/heads/maple-fern/r109-integration-and-submission'

# 2. An explicit refspec overrides the clone's narrow default refspec.
git fetch --no-tags origin \
  refs/heads/maple-nezuko/r129-g-preflight-validity-gates:refs/tmp/r129g \
  refs/heads/maple-fern/r109-integration-and-submission:refs/tmp/r109f

# 3. Copy out, then prove the copy is verbatim (both sides print the sha256 in the table above).
git show refs/tmp/r129g:research/tools/epoch_gate.py > research/imported/epoch_gate.py
git show refs/tmp/r109f:research/fern-r109f-interim-1200Z.md > research/imported/fern-r109f-interim-1200Z.md
git show refs/tmp/r129g:research/tools/epoch_gate.py | shasum -a 256
```

The `refs/tmp/*` refs are local scratch and are not published; nothing here rewrites a student
branch. The student PRs remain closed unmerged, which is the recorded disposition, and this directory
does not change it — the copies exist so a reader can *read the evidence* without network access to a
branch that may one day be garbage-collected.

## What each file is, and the safety note that matters

- **`epoch_gate.py`** — nezuko's R129-G preflight validity gate. It **parses a saved dump** and never
  executes anything: `python3 research/imported/epoch_gate.py --dump <file>` where `<file>` is the
  captured text of a `mlxfast submissions` listing. Verified read-only by inspection (no `subprocess`,
  no `os.system`, no `os.popen`, no shell-out anywhere in its 153 lines) and by `--help` exiting 0.
  The docstring *names* the CLI as the provenance of its input; naming is not invoking.
  **It is deliberately NOT placed in `research/tools/`**, so no `research/tools/*.py` glob can run a
  tool I did not write; `run_all_tools_smoke.sh` nonetheless extends its channel-safety scan over this
  directory, so a future vendored file that *could* invoke the submission CLI fails the suite loudly.
- **`fern-r109f-interim-1200Z.md`** — fern's 12:00Z interim R109-F report, cited from the manifest as
  the primary record for that arm.

Provenance rule this directory exists to satisfy (§8 rule 28): *a citation a reader cannot open is a
claim, not evidence.* If you cite an artifact that lives outside your published branch, either vendor
a verbatim copy with its source commit and checksum, or say plainly that the reader must fetch it.
