# R128-D — Decode wall-vs-busy attribution

Student: maple-alphonse. Assignment `maple-r128-d-decode-wall-vs-busy-attribution`,
revision `r128-d-rev1`. PR #744.
Base `codex/mlxfast-maple-20260804-advisor` @ `67396bb6283cf2765a388b05ce4ac64174bb8ef6`.

**Nothing was fired.** No official submission, no `senpai/submit-official.sh`,
no `--official` run. No landing hunk: `git diff base..HEAD -- Sources/ Vendor/`
is empty (verified at the end of this document).

## Measurement host

All µs/step numbers produced by this assignment were measured on **this M4 Pro**
unless the sentence explicitly names another host (Rule 9).

| property | value |
| --- | --- |
| chip | Apple M4 Pro, 14 CPU cores |
| unified memory | 48 GiB (below 64 GiB ⇒ low-memory startup profile) |
| OS | macOS 26.5.2 (25F84) |
| Apple GPU generation | 16 ⇒ **never selects the `_nax` kernels the ranked M5 selects** |

Consequences that bound every claim below: this host does not execute the
ranked prefill kernel family, its steady decode step is roughly 1.7x the ranked
host's, and threadgroup-geometry-sensitive conclusions do not transfer. What
*does* transfer is the *structural* question this assignment asks — whether a
wall-minus-busy residual of the claimed size exists at all, and what it is made
of — because the residual is dominated by dispatch/encode/completion structure
rather than by kernel arithmetic.

Currencies used for pricing (never 0.00586 %/µs, which is unsourced):

| currency | host / harness | source |
| --- | --- | --- |
| 0.00845 %/µs | 8882 µs/step, nezuko #730 `--local-submit` | measured |
| 0.00913 %/µs | 8213 µs/step, frieren #733 control | measured |
| 0.01527 %/µs | ranked host, 4910.9 µs/step | measured |

## D0 — Provenance of 8919 (wall) and 8567 (busy)

The claim under audit is manifest item 2,
`research/maple_endgame_handoff_manifest.md:977`:

> Decode wall ≈ 8919 µs vs busy ≈ 8567 µs ⇒ ~350 µs (~2 % of score) of
> non-busy time.

§6.6 of the same manifest (lines 961–964) re-prices the same 350 µs at 2.94 %
of score.

### `d0_wall_8919` = **UNSOURCED**

No primary record of 8919 (or 8.919) exists anywhere in the tree or in history.
Searches run:

```
grep -rn --exclude-dir=.git --exclude-dir=.build -E "8919" .
grep -rn --exclude-dir=.git --exclude-dir=.build -E "8\.919" .
git log -S'8919'      --oneline --all -- research/
git log -S'Decode wall' --oneline --all
```

The number enters the tree **already uncited** in commit `9ef3bfcb`
("advisor r125: endgame handoff manifest + measurement tools"). There is no
run log, JSON, or report behind it. Commit `77580a48` contains the author's own
admission that this basis "has not been verified… Treat it as unpriced until
someone does."

Nearby measured clusters exist but none of them is 8919 and none of them is
cited by the manifest: 8876–8908 µs in `research/nezuko-r117-c-final-report.md:708,710`
and manifest:916; and a kernel-census total of 8883.1 µs in
`research/maple-tanjiro-pr73-decode-kernel-census.md:210-212`.

### `d0_busy_8567` = **UNSOURCED as paired**, but the origin is identified

A decisive near-miss was found and personally re-read from the raw artifact:
`research/r87a-runs/control.json`, arm `A0`, n=6:

| field | mean | sd |
| --- | --- | --- |
| `busy_union_us` | **8567.333** | — |
| `busy_sum_us` | 8568.167 | — |
| `wall_us` | **9814.667** | 75.76 |
| `gap_us` | **1247.333** | 53.59 |
| `cbs` | **406.0** | — |

So 8567 almost certainly came from this R87-A control arm. But **its own paired
wall is 9814.7 µs, not 8919**, and **its own paired gap is 1247 µs, not ~350**.
The manifest pairs this busy with a wall from somewhere else entirely.

### The methodological kill

`research/tanjiro-r87a-campaign.sh:64-66` shows that this control was run under

```
DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=1  STEPS=${R87A_STEPS:-200}
```

`SPLIT=1` caps dispatches per command buffer so that each `GPUPROF` record times
a small unit — which is exactly why that arm reports **406 command buffers per
step**. A normal decode step does not submit 406 command buffers. The 8567 busy
is therefore a *heavily instrumented* busy, measured in a configuration whose
command-buffer structure is not the scored one.

Manifest item 2 subtracts a `SPLIT=1`-instrumented busy (8567) from an unsourced,
probably hook-free wall (8919). That is an apples-to-oranges subtraction: the
two terms come from different binaries and different dispatch structures. The
~350 µs residual is an artifact of mismatched pairing, not a measured quantity.

Other numbers close to 8567 that are explicitly **not** the source:
`research/r85b-logs-rebased/contrasts.log:91` ("8548 of 8567 us/step") is
downstream prose, not a primary paired measurement.

