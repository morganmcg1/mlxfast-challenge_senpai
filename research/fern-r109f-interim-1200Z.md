# fern r109-f interim, 12:00Z checkpoint

## 0. Host and publication mechanics (asked, answering explicitly)

- **No daemon, no auto-fire loop on this host.** Verified twice with `ps`: no
  benchmark, mlxfast, swift, channel_daemon, watch-submission, queue_probe, or
  poller processes. The ticket-8 poller job `1298f7a9-...` (PID 99102) that the
  operator terminated is confirmed gone and I have not replaced it.
- **I have fired no official submission and will not.** Maple stood down from the
  shared slot; Cedar owns it through close.
- **`git push` from the terminal is blocked** in this runtime ("Terminal use of
  `git push` is not allowed; use the typed Senpai tool for branch publication").
  The only publication path I have is `submit_experiment_result`, which
  lease-pushes `result.commit_sha`. So intermediate publish checkpoints cannot be
  met by a push; everything lands with the terminal result. All work below is
  committed locally on `maple-fern/r109-integration-and-submission`.

## 1. Rebase onto the new base: done, with exact parity

Merged onto `18ac6015c6c2c52ae2fa8830b23d249b35b6f448`. `Sources`, `Vendor`,
`benchmark.json`, `Package.swift`, `Package.resolved` are **bit-identical** to
that base (`git diff --name-only` empty) before my one perf hunk below. The
advisor branch has since moved to `9ef3bfcb`, but
`git diff 18ac6015 9ef3bfcb -- Sources Vendor benchmark.json` is empty, so the
integration surface is unchanged.

My atlas v3_tg128 WIP was on the old base (merge-base `9fe3719`) and is **not**
rebased or verified; it is archived at
`research/fern-r109f-portable-hunks/atlas-v3-tg128-ON-OLD-BASE-9fe3719.patch`
and should be treated as unverified.

**Budget gate PASS** on the merged tree with my hunk:
`editable budget OK: current=2714753/3000000 headroom=285247 growth=-269096/262144 files=143`.

**Build gate PASS**, `swift build -c release --force-resolved-versions`, exit 0.

## 2. The alphonse TG=256 hunk does not exist, so I rebuilt it

PR #729 branch `origin/maple-alphonse/r125-a-shared-qmv-tg256-landing` head is
`12693d125168192c15818e8de195a3024181d7b5`; its parent is `a9de9e8f2118...`; and
`git diff --stat a9de9e8f 12693d12` is **completely empty**. That commit is a
tree-identical "senpai assignment" commit. **The hunk was never pushed**, so
there was nothing to verify and nothing to hand to Cedar.

I implemented it independently instead (commit `85cc71b7`, 3 hunks, 29 insertions
in `LagunaRuntimeModel.swift`):

- The rows1 kernel assigns exactly one fused gate/up output row per simdgroup, so
  total simdgroups is pinned at `sharedExpertIntermediateSize` = 512 regardless
  of packing. Only the threadgroup width is free.
- Old: `row = tile * 2 + simd_group`, `tiles = 256`, `threadGroup: (64,1,1)`.
- New: `row = tile * 8 + simd_group`, `tiles = 64`, `threadGroup: (256,1,1)`.
  Total threads is 16384 in both cases and total simdgroups is 512 in both cases.
- One constant, `lagunaSharedSwiGLUQMVRows1SimdgroupsPerTile`, drives both the
  in-kernel row stride and the dispatch width, so they cannot disagree.
- `DARKBLOOM_SHARED_QMV_TG256=0` restores the old dispatch exactly.
- The variant carries a `_tg256` kernel-name suffix, because both packings
  compile different sources under one family name and a name-keyed kernel cache
  could otherwise serve a stale 2-simdgroup binary to an 8-simdgroup dispatch,
  which would read rows 0..255 twice and leave 256..511 unwritten.

### Retirement (e), settled from source

The dispatch signature refutes the PR #333 / note `7e267f3` "grid
over-dispatch" claim outright: `grid:` in `MLXFast.metalKernel` takes **total
threads**, not threadgroups. `grid: (tiles * 64, 1, 1)` with
`threadGroup: (64,1,1)` is 16384 threads in 256 threadgroups, which is exactly
one thread per lane of work, not a 64x over-dispatch. That family is terminal,
including the R119 grid-append variants built on the same misreading.

## 3. Env cannot ship behaviour (Cedar must know this)

`benchmark.sh:2084` states that the official measure-job timed path runs
`sudo env_reset` + `env -i`, which **strips workflow env**. So no `DARKBLOOM_*`
override can influence an official run. Anything we want measured officially has
to be the **default in source**. Env flags are an A/B instrument locally and
nothing more. My TG=256 hunk therefore defaults **on**, with the kill-switch for
local A/B only.

## 4. New-base `--local-submit` baseline, n=3, on `18ac6015`

Interleave-free baseline ladder, three draws, `MLXFAST_LOCAL_FAN_PROMPT=0`:

| draw | harness score | decode s/tok | prefill s/tok |
|---|---|---|---|
| 1 | 1.056841 | 0.008901522 | 0.00111117570 |
| 2 | 1.053621 | 0.008907030 | 0.00112273454 |
| 3 | 1.056527 | 0.008906144 | 0.00111076497 |

- harness `score` = **1.055663**, sd 0.001775, **cv 0.168 %**, 95 % CI
  [1.053654, 1.057672].
- `ns` under the spec constants (0.013890 / 0.0003845) = **1.069603** sd 0.001799.
  Under the harness-reported official-runner baselines (0.01385621216015625 /
  0.00036751938916015626) `ns` reproduces the harness score to all digits, which
  confirms the harness applies the same normalisation the receipts do.
- **decode leg 0.008904899 s/tok, cv 0.0332 %** (sd 2.96e-6).
- prefill leg 0.001114892 s/tok, cv 0.6095 %.
- Invariant across all three draws: `max_abs_diff = 0`, `passed_correctness true`,
  `passed_decode_speedup_floor true`, `peak_ram_gb 21`,
  `harness_hash d4ac97fda8085e46ac696dab72474f7cc69e681dc19681d642f6c155865cd032`.

**Both golden hashes, as asked.** `--local-submit` gates on
`correctness_prompts/public_longcopy_gate_english_512_1024.json` →
`golden_hash = f49e4c2cbc0d3ceee90195a3a12e1ff082636f8c031587485a9a2c10702b03d2`.
`--local-iterate` gates on the `...512_256.json` prompt set →
`golden_hash = b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63`.
These are different files; quoting one where the other is expected looks like
golden drift when it is not.

**Caveat that matters: local absolute `ns` is not comparable to official.**
`passed_prefill_speedup_floor` is **false** locally on every draw, prefill
0.001115 vs the 0.000368 official-runner baseline, i.e. 0.33x. This box is a
48 GiB M4 Pro, which trips the low-memory startup profile (allocator cache
capped at 6 GiB), and the prefill leg is structurally handicapped as a result.
Local `ns` ~= 1.06 against official ~= 2.6 is that handicap, not a regression.
**Local `ns` is a relative instrument only; adjudicate arms on the raw legs.**

The good news is the decode leg is a far better instrument than I had assumed:
cv 0.0332 % at n=3, roughly 10x tighter than the 0.30-0.35 % I had been
budgeting. A +0.38 % score effect needs a -0.507 % decode move (elasticity 0.75),
which is ~15 sd on this leg. Paired `--local-submit` can therefore adjudicate the
TG=256 effect decisively at small n.

## 5. Item (d): the receipt-replay answer, and a correction

Of 1798 cached submission rows (1187 scored with a sha), only **112 receipt
commits resolve in this fork**.

- Highest-scoring **present** receipt:
  **`c5b0a13c5cc032b485022db41bcd745792316714` = 2.61650354381**, solver
  `a-github-name`, accepted + promoted, 2026-08-08.
- Highest-scoring **Maple** receipt that is present:
  **`5c542169b5e6c295805f50fa65df3150816eb443` = 2.60664969896** (`e27f1ce`,
  rejected).
- **The advisor's candidate `d6a5f9e7346e717d89e769396d732600a994b4cf` (d11026c,
  2.59320) is ABSENT from this fork.** So is `4ea72c3`, the current crown.
  Whatever plan depended on replaying `d6a5f9e7` cannot run as written.

Also worth stating plainly: these present commits are organizer
"Validate submission &lt;id&gt;" snapshot commits and are **not ancestors of
`origin/main`** (head `27cb47ba`). Replay is mechanically possible but it is a
whole-tree swap, not a cherry-pick:
`git diff --stat 5c542169 18ac6015 -- Sources Vendor benchmark.json` is 33 files,
+3022/-5346; for `c5b0a13c` it is 33 files, +3010/-5328.

Other present receipts, for the record: `01e247a74d1e` 2.60630619989 (yudduy,
promoted), `ebcd3ca387ae` 2.60116055795, `ab17a99f5bd4` 2.59787481791,
`708500f7343f` 2.59738344238, `26b465352561` 2.59018571539, `3e165fa52be9`
2.58882784082 (Maple's promoted).

## 6. Item (f): the standing bar

**2.61955310948 at `4ea72c3b2887`**, solver `ggu77wt`, accepted + promoted,
created 08:28:04Z, promotion finished 09:34:06.911Z today. No newer promotion as
of the 10:50Z pull (1859 submissions). Runner-up promoted: `c5b0a13c5cc0`
2.61650354381. Notable rejection today: `3fbf2a714af8` 2.60877774470 (uu0vg7,
08:20Z).

## 7. Sub-ask `4be372f`: terminal, rejected, and both floors passed

`4be372f9-bb17-4857-9252-b84c71bc3c1a`, solver morganmcg1, sha
`74593e5afaccdf74870be61d9c4f5fea740d19ce`.

- status **`rejected`**, `rejectionReason` "score did not improve current best",
  `improved=false`, **officialScore 2.57671436417547**.
- created 09:20:20.768Z, updated 10:59:43.760Z, **service time 5963 s = 99.4 min**.
- **Both floor verdicts PASSED**: `passed_correctness=true`,
  `passed_decode_speedup_floor=true`, `passed_prefill_speedup_floor=true`,
  `error=""`, `max_abs_diff=0`,
  `golden_hash=be7738fccd6a28807ae7d18c038cbbc9e1b05dab26b99b2f247358fdc67fcf71`.
- Legs: decode 0.004901157875 (speedup 2.827790682076835), prefill
  0.000188064046875 (speedup 1.9495004361462962), against baselines
  0.0138594485703125 / 0.00036663094140625.

So it was a clean run that simply did not beat the bar. Nothing to debug.

## 8. The queue, measured

From the full 1859-row record:

- **One-in-flight-per-solver holds exactly**: 89 solvers, **0 overlapping
  non-terminal intervals**. There is no way to parallelise our own shots.
- Service time (1849 terminal rows): median **1358 s**, mean 1897 s, p5 557,
  p25 1062, p75 2356, p95 4787, max 10846 s.
- Today degraded hard: 00Z-06Z median ~1300 s; **07Z 1837 s; 08Z 6431 s
  (107 min); 09Z 2835 s**.
- Backlog at 11:04:53Z: **10 non-terminal, all `validating`**; oldest
  `bbb49bc3` (DawgZter) created 08:28:44Z, age 156 min, past p99 of the service
  distribution.
- Recent throughput 31 completions / 5.88 h = **5.3/h**; Little's-law sojourn
  ~1.9 h. A shot fired at ~11:05Z should land ~13:00Z.

**Consequence: with one-in-flight and ~5.9 h to close, Cedar has at most ~3 more
official shots.** Shot selection, not shot count, is the whole game.

## 9. The decomposition that should drive shot selection

Identity `published = normalized x draw`, with `normalized` computed from the
published raw legs under the harness constants and `draw` the residual. 1280
decomposable rows, 50 today.

- Draw distribution: median 1.001830, mean 1.003228, **sd 0.005394 = 0.538 % of
  mean**; p05 0.996446, p25 0.998578, p75 1.007643, p90 1.010890, p95 1.012550,
  p99 1.016275, max 1.024492. This matches the 0.5169 % published-score sd I
  reported in PR #686 §5, from a completely different direction.
- **The crown was won on the lottery, not on engineering.** `4ea72c3` has
  normalized **2.576540** and draw **1.016694** — about p99.3 of the all-record
  draw distribution, and the largest draw observed today.
- **Our executables are already better than the crown's, normalized.**
  `5c542169` normalized **2.582263** (draw 1.009444); `4b0e051b` 2.582070;
  `ef055b9b` 2.580837; `5a43d329` 2.580267; `fe610f60` (08-11T01:54) 2.579556;
  today's `74593e5a` 2.577822 (draw 0.999570). Best normalized anywhere on the
  record is `ebcd3ca387ae` (MyatKaung) 2.583375.

### Gain to win-probability, from our best-ever normalized executable (2.582263)

| normalized gain | P(beat bar) per shot | P(win in 3 shots) |
|---|---|---|
| +0.00 % | 1.48 % | 4.39 % |
| **+0.38 % (TG=256)** | **11.09 %** | **29.73 %** |
| +0.50 % | 15.47 % | 39.60 % |
| +0.75 % | 28.44 % | 63.35 % |
| +1.00 % | 40.08 % | 78.48 % |
| +1.259 % | 50.00 % | 87.50 % |
| +1.50 % | 66.48 % | 96.24 % |
| +2.00 % | 99.61 % | - |

Two things follow, and they are the actionable content of this comment:

1. **Re-firing our best existing executable is close to hopeless** (1.5 %/shot,
   4.4 % over the three shots we have). It needs a p99 draw to win.
2. **A +0.38 % improvement is worth a 7.5x lift in win probability**, from 4.4 %
   to 29.7 % over three shots. That is the entire argument for landing TG=256 and
   the other banked micro-wins before Cedar spends a shot.
3. A coin-flip against the bar needs **+1.259 % normalized** from our best-ever
   executable. Nothing currently banked gets us there alone, which argues for
   composing every confirmed win rather than picking one.

From today's executable (2.579556) instead, +0.38 % gives 7.50 %/shot and
20.85 % over three shots.

## 10. The gen-16 blind spot Cedar must know about

This host reports GPU generation 16 (`applegpu_g16s`, 20 cores), so it **never
selects `_nax` kernels**. Any `_nax`-gated mechanism, including the promoted
frontier mechanism N1, is **unobservable and unmeasurable from this box**. I have
not measured it and cannot. If Cedar's shot depends on an `_nax` path, that path
has had no local verification from me and must be validated somewhere else or
taken on faith.

## 11. In flight now

Interleaved paired A/B, `DARKBLOOM_SHARED_QMV_TG256=0` vs `=1`, three pairs,
alternating A,B,A,B,... so thermal drift is shared equally between the arms
rather than loading onto whichever ran second. Adjudication on the raw decode
leg, with `max_abs_diff` required to stay 0 in both arms. Result, plus the
upstream-equivalence run and the 64-step drift tripwire, in the terminal
`senpai-result:v1` by 15:30Z.
