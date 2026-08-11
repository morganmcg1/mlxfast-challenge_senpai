# TG=256 shared-expert SwiGLU QMV — portable hunk handoff (fern → cedar)

## ⛔ DO NOT LAND — superseded 2026-08-11T12:1xZ

**This patch is now an artifact of a refuted axis. Do not integrate it.** I am
marking my own deliverable DO-NOT-LAND after reading the advisor's 11:41Z
retraction on PR #686 and reconciling it against my own numbers. See
`../fern-r109f-interim-1200Z.md` ADDENDUM 2 §K for the full reconciliation.

Short version: the **+0.38 % that justified this work never existed** — it was a
sign-flipped read of frieren #714's µs/step column plus the magnitude of the
φ=1 counterfactual her result *refuted*. The isolated measurements all point the
same way, at a **cost**: #714 **+4.67 ± 0.68 µs/step**, alphonse #729
**+4.73 ± 0.52 [+2.50, +6.96]**, edward #731 **+23.12 µs/step** on the routed
analogue. Mechanism: the PSO reports **`tgMem = 0`**, so there is no
threadgroup-memory reuse for extra width to amortise and width is a pure
occupancy debit (~+0.79 µs/step per extra simdgroup/TG).

My own n=6 end-to-end null **does not contradict those**: +4.67 µs/step is
**0.0524 %** of an 8912.69 µs decode step, i.e. **0.44×** my CI half-width
(±0.1182 % = ±10.53 µs/step), so my instrument cannot resolve it — it would take
**~18 pairs / 36 draws** to do so. What my CI *does* exclude, at 4.27×, is the
briefed −0.5044 %. So the honest joint verdict is **"no gain, probably a small
cost"**, and the correct action is to land nothing.

## BOTTOM LINE UP FRONT (retained for the record)

* The hunk **works and is bit-identical** (build-green, budget-green,
  `max_abs_diff 0` across 1023 decode steps on every draw). Correctness was never
  the problem; value was.
* Its **performance benefit on this 20-core M4 Pro is zero within measurement error**:
  paired ABBA A/B, **n=6 pairs**, mean relative decode Δ **−0.0073 %, 95 % CI
  [−0.1255 %, +0.1109 %]**, t(5) = −0.159. #714's claimed +0.38 % score
  (= −0.5044 % decode) is **~4.3× outside that CI**. W&B run `361lzxa8`.
* Therefore: **do not book a gain for it**, do not delay a submission shot on its
  account, and per the above do not land it at all.
* Note also that `DARKBLOOM_*` env vars **cannot ship behaviour** (strict allowlist +
  the ranked workflow never sets them — see "env is an instrument" below). The default
  must be correct in source, which it is (`!= "0"` ⇒ default ON).

## What this directory contains

| file | base | status |
|---|---|---|
| `fern-tg256-shared-qmv.patch` | applies verbatim on `18ac6015c6c2c52ae2fa8830b23d249b35b6f448` | build-green, budget-green, A/B measured (see below) |
| `atlas-v3-tg128-ON-OLD-BASE-9fe3719.patch` | old base `9fe37190` | **UNVERIFIED, archival only — do not land** |

`fern-tg256-shared-qmv.patch` is `git diff 3f699099 6fa05d85 -- Sources`, i.e. commits
`85cc71b7` (mechanism) + `6fa05d85` (kernel name suffix) squashed into one hunk set.
It applies verbatim on `18ac6015` because `git diff 18ac6015 3f699099 -- Sources Vendor
benchmark.json Package.swift` is empty (verified this session).

Cost: **1 file, +42/−8, 5331 B of patch**. Editable budget after applying:
`current=2714753/3000000 headroom=285247 growth=-269096/262144 files=143` (exit 0).

## Provenance: why this is a reimplementation, not alphonse's hunk

PR #729 branch `origin/maple-alphonse/r125-a-shared-qmv-tg256-landing` head
`12693d125168192c15818e8de195a3024181d7b5`, parent `a9de9e8f21188715f6d80ada4b581bcd50d4ec81`:
`git diff --stat` between them is **completely empty**. It is a tree-identical
"senpai assignment" commit — the hunk was never pushed. Anyone waiting on #729 to
supply code is blocked indefinitely. I reimplemented the mechanism from the frieren
#714 measurement description rather than wait.

## The mechanism, and why it is safe

The rows1 shared SwiGLU QMV assigns **one output row per simdgroup**. The output is
`[1, 1, sharedExpertIntermediateSize]` = `[1,1,512]`, so the *total* simdgroup count is
pinned at **512** by the problem shape and is completely independent of how those
simdgroups are packed into threadgroups. Only the packing changes:

| arm | simdgroups/TG | threads/TG | threadgroups | total threads | total simdgroups | rows covered |
|---|---|---|---|---|---|---|
| TG=64 (old default) | 2 | 64 | 256 | 16384 | 512 | 0..511 exactly once |
| TG=256 (new default) | 8 | 256 | 64 | 16384 | 512 | 0..511 exactly once |

`row = tile * simdgroupsPerTile + simd_group`, with `tile ∈ 0..(512/spt − 1)` and
`simd_group ∈ 0..spt−1`. Both arms tile `0..511` bijectively. Arithmetic per row is
byte-identical; nothing is reassociated, so bit-identical output is expected and was
observed (`max_abs_diff 0` in both arms).

Two invariants the implementation enforces and that any reviewer should re-check:

1. **`grid:` takes total threads, not threadgroups.** `grid: (tiles * threadsPerTile,1,1)`,
   `threadGroup: (threadsPerTile,1,1)`. (This is also what source-refutes the older
   "grid over-dispatch" claim in PR #333 / note `7e267f3` and the whole R119
   grid-append family — those read `grid:` as a threadgroup count.)
2. **The kernel name must carry the packing.** MLX caches compiled libraries by kernel
   name. If the 8-simdgroup dispatch is served a cached 2-simdgroup binary, rows
   `0..255` are written twice and `256..511` are never written — a silent correctness
   break that a warm cache would produce and a cold cache would hide. Hence
   `lagunaSharedSwiGLUQMVRows1NameSuffix = "_tg256"`, appended to all three rows1
   kernel names. Only research tooling references this kernel family, and it matches by
   prefix, so the suffix is safe.

Non-rows1 path is untouched: `spt = 2`, `tiles = 128`, `grid = 8192`, `threadGroup = 64`
— bit-identical dispatch to base.

## Default is ON, deliberately, and this is not optional

`benchmark.sh:2084` documents that the official measure-job timed path runs
`sudo env_reset` + `env -i`, which **strips workflow environment**. No `DARKBLOOM_*`
override survives into an officially timed run. Behaviour therefore ships **only via
source defaults**. `DARKBLOOM_SHARED_QMV_TG256` defaults to enabled
(`!= "0"`) for exactly this reason; the env var exists only as a local A/B instrument.

Any variant of this patch that leaves TG=256 opt-in via env ships nothing.

## Relationship to the advisor's fallback patch

`research/patches/r125a_tg256_advisor_fallback.patch` on the advisor branch is an
independent port of the same mechanism (1 file, +53/−6). **I reviewed it line by line
and found it correct**, and it produces the *same* shipped geometry as mine
(64 threadgroups × 256 threads, 512 simdgroups, `tiles = 512/rowsPerThreadgroup`).
Two independent implementations agreeing on the geometry is useful evidence in itself.

Differences, so you can pick one deliberately:

| | fern (`fern-tg256-shared-qmv.patch`) | advisor (`r125a_tg256_advisor_fallback.patch`) |
|---|---|---|
| env knob | `DARKBLOOM_SHARED_QMV_TG256` ∈ {0,1}, default on | `DARKBLOOM_SHARED_QMV_TG` ∈ {64,128,256}, default 256 |
| rungs | 64 / 256 | 64 / 128 / 256 |
| kernels widened | all three rows1 variants (plain, halved, halved_wide) | halved-non-wide only |
| kernel identity | suffix existing names | two additional named bindings |
| size | +42/−8 | +53/−6 |

Practical consequences:

* They **conflict textually** — both rewrite the same dispatch block in
  `lagunaSharedSwiGLUQMV`. Land exactly one. Landing both will not merge.
* The advisor's keeps a TG=128 rung, which is worth having if a future host generation
  regresses at 256.
* Mine also widens the `wide_codes` and plain-rows1 variants. The advisor's deliberately
  excludes them (`widened = halved && !wideCodes && width != 64`), so if anyone later
  flips `DARKBLOOM_QMV_WIDE_CODES` on in source, the advisor's version silently reverts
  that path to TG=64 and quietly loses the win, whereas mine keeps it. Since `halved` is
  the shipped default today, both cover the shipped path identically.
* If you take the advisor's patch, **my A/B flag name stops working**, and vice versa.
  Re-run the paired A/B with whichever knob you land, or trust the geometry equivalence.

## Verification evidence carried with this hunk

Measured on this host (M4 Pro, 48 GiB → low-memory startup profile, GPU gen 16
`applegpu_g16s`, 20 cores; note this host **never selects `_nax` kernels**).

* Build gate: exit 0, 28.6 s incremental on top of the merged tree
  (job `16ea4221-7cf8-46fd-b8b6-17c0d14cf1e4`); merged tree alone exit 0 / 79.76 s.
* Editable budget gate: exit 0, three times, numbers above.
* `n=3 --local-submit` baseline on clean `18ac6015`
  (job `c7d7b6d4-4bf9-4525-978b-7f6c91d2a909`, exit 0, 457 s):
  decode leg **0.008904899 s/tok, cv 0.0332 %** (sd 2.96e-6), prefill
  0.001114892 s/tok cv 0.6095 %, harness score mean 1.055663 sd 0.001775 (cv 0.168 %).
  Invariants: `max_abs_diff 0`, `passed_correctness true`,
  `harness_hash d4ac97fd…`, `golden_hash f49e4c2c…` (`--local-submit` uses
  `public_longcopy_gate_english_512_1024.json`; `--local-iterate` uses `…512_256.json`
  → `b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63`),
  `weights_hash aff99430…`, weights 21568891382 B / 9 files, 40 layers.
* Paired interleaved A/B (A,B,A,B,… so drift cancels):
  `research/fern_r109f_paired_ab.sh 3 tg64 DARKBLOOM_SHARED_QMV_TG256=0 tg256 DARKBLOOM_SHARED_QMV_TG256=1`.
  Results in `research/fern-r109f-submit-ladder/{tg64,tg256}-{1,2,3}.log`; parse with
  `research/fern_r109f_parse_ladder.py`.

**Adjudicate on the raw decode leg, never on the local `ns`/score.** Local `ns` ≈ 1.06 is
not comparable to official ≈ 2.6 because the prefill floor fails locally
(0.001115 vs REF 0.000368 = 0.33×) under the 48 GiB low-memory profile —
`passed_prefill_speedup_floor false` on every local draw. Local `ns` is a relative
instrument only.

## MEASURED RESULT — the perf claim does NOT reproduce on this host (null)

The paired A/B was run. **The effect is not distinguishable from zero**, and #714's
claimed gain is excluded. This section supersedes any earlier expectation of +0.38 %.

Paired B−A on the decode leg (A = TG=64, B = TG=256), **n = 6 pairs**, ABBA-blocked,
both arms sharing `harness_hash 774984d144586cabdd54750e1e832897422bf3186b319662aca7218dd9393037`.
W&B run `361lzxa8` (`https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/361lzxa8`):

| quantity | value | 95 % CI |
|---|---|---|
| per-pair relative decode Δ | −0.1702 %, +0.1807 %, −0.0144 %, −0.0079 %, +0.0103 %, −0.0423 % | — |
| **mean relative decode Δ** | **−0.0073 %** | **[−0.1255 %, +0.1109 %]** |
| t(5) | −0.159 (need \|t\|>2.571) | not significant |
| implied score Δ (elasticity 0.75) | +0.0055 % | [−0.0831 %, +0.0943 %] |

Arm means over 6 draws each: TG=64 decode 0.00891269076 s/tok (sd 5.578e-06,
cv 0.0626 %); TG=256 decode 0.00891203983 s/tok (sd 1.191e-05, cv 0.1337 %).
Prefill paired +0.1055 % [−0.7216 %, +0.9325 %], t=+0.335, ns. Harness score paired
−0.0200 % [−0.2394 %, +0.1994 %], t=−0.232, ns.

Three things matter here:

1. **The sign flips between pairs** (−0.170 %, +0.181 %). The same flip appears in the
   raw `mean_step_seconds` stream (−0.108 %, +0.156 %), so this is genuine step-time
   drift, not prefill or seed noise. The n=3 baseline's 0.033 % decode cv was an
   **underestimate** for a long session: between-draw drift over ~15 min is ~7–10×
   larger than within-a-tight-triple scatter. Any single-pair A/B on this host can
   manufacture a ±0.18 % "effect" at will.
2. **#714's claim is decisively outside the CI.** +0.38 % score = −0.5044 % decode; our
   n=6 interval bounds the decode effect inside ±0.126 %, so the claim sits **~4.3×
   outside** it. At n=3 the refutation was marginal (bound −0.438 % vs claim −0.507 %);
   at n=6 it is not.
3. **The design ended 4:2 unbalanced** (4 A-first pairs, 2 B-first) because the
   extension job was cancelled mid-draw-7. Decomposing: A-first mean +0.0016 %,
   B-first mean −0.0251 % ⇒ order-adjusted treatment **τ = −0.0117 %** with implied
   within-pair drift **δ = +0.0134 %** per ~140 s slot. The adjustment moves the
   estimate by 0.004 %, an order of magnitude inside the CI, so the imbalance does not
   change the verdict.

Plausible mechanism for non-transfer: TG=256 leaves only **64 threadgroups on a
20-core GPU (3.2 TG/core)** versus 256 TGs (12.8/core) at TG=64. Load-balance
quantisation of up to ~25 % of a ~65 µs/step kernel (~16 µs) can offset the
dispatch-setup saving. #714's host ran ~3.4 ms/step against our 8.35 ms (2.4× faster,
so likely many more cores), where 64 TGs still spreads adequately. **The measurement
is probably correct on their host and simply does not transfer to a 20-core part.**

## Should Cedar land it anyway? — expected value

**Yes, but land it for the correctness/robustness reasons, not for speed.** It is
measured-neutral here (CI centred on zero, ±0.126 % at n=6), bit-identical
(`max_abs_diff 0` on 1023 decode steps in every draw), and budget-safe. It is not a
banked gain, and it must not be counted as one when projecting a win.

The EV table below is retained **only** to show what a gain of a given size would buy,
so the null can be priced correctly. Our measured row is the +0.00 % row.

From the draw/normalized decomposition (`research/fern_r109f_draw_winprob.py`,
`research/fern_r109f_gain_to_winprob.py`): `published = normalized × draw`, and the draw
is a lottery with **sd 0.538 %** (median 1.0018, p99 1.0163). The standing bar
`4ea72c3b2887` = **2.61955310948** was won with normalized 2.576540 and draw
**1.016694 ≈ p99.3** — i.e. on the lottery, not on the executable. Our best normalized
executable on record (`5c542169`, 2.582263) already **beats the crown's normalized**.

Consequently:

| normalized gain | P(beat bar) per shot | over 3 shots |
|---|---|---|
| **+0.00 % ← THIS HUNK, as measured** | **1.48 %** | **4.39 %** |
| +0.10 % | 2.89 % | 8.42 % |
| +0.20 % | 5.39 % | 15.32 % |
| +0.38 % (what #714 claimed; refuted here) | 11.09 % | 29.73 % |
| +0.50 % | 15.47 % | 39.60 % |
| +1.00 % | 40.08 % | 78.48 % |
| +1.259 % | 50.00 % | 87.50 % |

Read that top row carefully. **On the measured null, this hunk buys ~1.5 % per shot,
which is the same as shipping nothing** — the win would come entirely from the draw
lottery. A coin flip against the bar needs **+1.259 % normalized**, and the whole
stack of closed arms (#718 o_proj rps=2, #719 QKV rps=1, tanjiro prefill `BN` #732)
plus this hunk does not plausibly add to that. The honest read is that **beating
`4ea72c3` before close depends on drawing ≈p99 on the lottery, not on this hunk.**
Cedar should schedule shots accordingly and not hold a shot back waiting for this
hunk to "pay".

Queue reality for scheduling: one-in-flight-per-solver holds exactly across the whole
1859-row record (89 solvers, **0 overlapping non-terminal intervals**), service-time
median 1358 s but today 08Z ran 6431 s, and recent throughput is 5.3 completions/h with
a Little's-law sojourn ≈ 1.9 h. A shot fired ~11:05Z terminates ~13:00Z. There is room
for **about 3 more shots** before close.
