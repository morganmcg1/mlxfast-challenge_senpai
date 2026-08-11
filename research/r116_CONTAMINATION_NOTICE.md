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

## Resolution of the screen incident

Step 1 was run. Dropping block 2 entirely (a stricter cut than dropping the two
flagged cells, because it also removes their same-block control) leaves the
screen ranking intact:

```
arm     pairs  delta_us   sem      t      (blocks 1,3 only; + = slower)
sc0        2     -18.2   23.3   -0.78
qse0       2      -3.2    4.3   -0.75
ns0        2       4.2   20.6    0.21
ns2        2       6.5   19.6    0.33
qmvse0     2       7.5   11.8    0.63
sd0        2       9.0   43.6    0.21
qmvsc0     2      22.4   28.1    0.80
sfd1       2      47.2    0.5   88.50
argmax=sc0 raw=-18.2 debias(+33.2) -> +15.0
```

Same argmax (`sc0`), same sign for every arm except `ns0`/`sd0` — both of which
are indistinguishable from zero in either cut — and the same conclusion that the
debiased best-of-8 argmax is positive, i.e. no screen-level win. Step 2 does not
trigger, so no cell is re-run. Both cuts are published to W&B on the summary run
`q0vai430` as `contrasts` and `contrasts_block2_excluded`.

## Confirmation stage: two further disclosures

**1. Every confirmation run rebuilds the worker, uniformly.**
`Sources/MLXFastModel/LagunaRuntimeModel.swift` has an mtime newer than
`.build-worker/release/mlxfast-runtime-worker` (Aug 10 17:05) with *identical
content*: an earlier checkout touched the file without changing a byte, and a
content-hashing SwiftPM build is then a no-op that never relinks the product.
`swift_build_required` compares mtimes, so the condition can never clear and
every run pays a ~20 s near-no-op build. Unlike the screen incident this is
**symmetric** — all four arms in all eighteen blocks pay it — and
`benchmark.sh` runs the 40 °C gate *after* the build (`log-ctl-b1.txt`: build at
line 1, gate at elapsed 82.5 s, prefill timed at 98.0 s), so the build's heat is
gated away rather than carried into the timed window. It is left in place
deliberately: touching the binary mid-experiment would change conditions between
block groups, which is worse for a paired design than a constant overhead.

**2. One run lost to the host thermal gate.** `qmvsc0` block 1 aborted with
`local GPU cool-down gate failed for prefill with status 1`; GPU temperature
*rose* 41.4 → 43.0 °C across the 180 s budget. `passed=false`, `score=null`, and
the log carries no `checked decode` lines, so `frieren_steady_step.py` drops the
cell and the analyzer's within-block pairing drops that block for that arm only.
The gate was not disabled or relaxed. The runner's resume guard tested only
`[[ -s "${score}" ]]`, which a failed run also satisfies, so failed cells would
have been skipped forever on a re-run; the guard now requires `"passed" : true`
and failed cells are backfilled.

## Prevention

Two conversations share this one worktree. Before any `Sources/` or `Vendor/`
edit: check `git branch --show-current` and `ps aux | grep benchmark.sh`, and do
not edit compiled paths at all while another conversation's job is running.
Writes under `research/` are safe — that path is not in the `find` staleness
list above and cannot trigger a rebuild.
