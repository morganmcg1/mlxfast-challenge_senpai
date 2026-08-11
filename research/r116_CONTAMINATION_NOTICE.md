# R116-A screen: contamination notice for `sc0` b2 and `ns2` b2

**Status: disclose in the R116-A result. Run the sensitivity check below before
trusting the screen argmax.**

## What happened

A *different* conversation (`91f9695e-078d-4bd6-a54f-1c6604ace8a1`, the closed
R109-A assignment) woke on a stale `job_monitor` signal at ~02:44Z, believed
R109-A was still live, and edited a compiled path in this shared checkout while
the R116-A screen job (`49124ac8-…`, PID 92023) was mid-flight:

- ~02:47Z: added a 16-line comment block to
  `Sources/MLXFastModel/LagunaRuntimeModel.swift` (~line 729).
- ~02:49Z: reverted with `git checkout -- Sources/MLXFastModel/LagunaRuntimeModel.swift`.

Worktree was clean again by 02:49Z and no R116 content was lost (the stray diff
was exactly 15 `+//` lines and nothing else).

## Why it touched two runs, not one

`benchmark.sh` decides the worker is stale with an mtime test
(`benchmark.sh:1982-1984`):

```sh
find Package.swift Package.resolved Sources Vendor -newer "${reference}" -print -quit
```

So it is sensitive to **mtime**, not content:

1. The 02:47Z edit bumped the file's mtime → `sc0` b2 (02:48:07→02:51:17)
   rebuilt the worker.
2. The 02:49Z `git checkout --` **rewrote the file, bumping its mtime again**,
   this time *after* the freshly built binary's mtime → `ns2` b2 (02:51:17→…)
   rebuilt too.

Both affected logs carry the marker; no other log does:

```
$ grep -l "missing or stale; building" log-*.txt
log-ns2-b2.txt
log-sc0-b2.txt
```

## Risk assessment

**Correctness risk: none, empirically confirmed.** The edit was comment-only, so
codegen is identical whichever revision the compiler happened to read. Confirmed
in the data: `sc0` b2 has `passed_correctness=true` and golden hash
`b9509697c08a…`, identical to all other screen runs.

**Timing risk: small but real, and not removable after the fact.** A SwiftPM
compile ran immediately before the timed phase of these two runs. `benchmark.sh`
builds first and then times, so there is no CPU contention *inside* the timed
window, and the 40 °C cooldown gate runs before timing — but residual thermal
and cache state is not fully excluded.

**Observed effect: no visible outlier.** `sc0` b1 `dec=0.0130952` → b2
`dec=0.0129727` (b2 faster). That sits inside the ordinary block-to-block
scatter seen across the other arms this block (`sfd1` and `sd0` also got faster
in b2; `qmvsc0`, `qmvse0`, `qse0` got slower), and inside the known M4
between-run drift of ±1.4–2.2 %.

## Required action at analysis time

1. Run the primary analysis twice: all data, and again with `sc0` b2 and `ns2`
   b2 dropped.
2. If the argmax arm, any arm's sign, or any landing decision changes between
   the two, **re-run those two cells** rather than picking a version.
3. Disclose this incident in the R116-A terminal result either way. Do not
   silently keep the flagged cells.

## Prevention

Two conversations share this one worktree. Before any `Sources/` or `Vendor/`
edit: check `git branch --show-current` and `ps aux | grep benchmark.sh`, and do
not edit compiled paths at all while another conversation's job is running.
Writes under `research/` are safe — that path is not in the `find` staleness
list above and cannot trigger a rebuild.
