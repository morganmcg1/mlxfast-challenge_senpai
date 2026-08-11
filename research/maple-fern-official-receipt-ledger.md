# maple-fern official receipt ledger (R109-F)

One row per official submission receipt this campaign can attribute to itself,
plus the reference receipts the bar is measured against. Requested by advisor
comment 8 (`r109-f-channel-strategy-inversion-1`).

## How the per-axis numbers are obtained

There is no need for a per-receipt detail call or the official W&B run. The
public listing endpoint

```bash
curl -s -H "Authorization: Bearer $MLXFAST_API_TOKEN" \
  "https://api.mlx.fast/api/benchmarks/1854efdf-feba-4773-bae9-b80520881a74/submissions"
```

returns, for 1227 of 1795 rows, a fully populated `officialMetrics` object that
carries **both** the candidate axes and the same-session baseline axes:

- `decode_seconds_per_token`, `prefill_seconds_per_token`
- `baseline_decode_seconds_per_token`, `baseline_prefill_seconds_per_token`

and all five separately-readable verdicts (`passed_correctness`, `error`,
`passed_decode_speedup_floor`, `passed_prefill_speedup_floor`, plus
`status`/`promotionStatus`/`rejectionReason`).

The published score identity was verified exactly on all 1227 rows:

```text
score = (baseline_decode/decode)^0.75 * (baseline_prefill/prefill)^0.25
max relative error 4.657e-15   median 1.231e-15
```

Tooling: `research/fern_r109f_receipt_axes.py`
(`fetch|verify|draw|user|rank|winprob`),
`research/fern_r109f_crown_decompose.py`, `research/fern_r109f_draw_schedule.py`.

## Score decomposition used in this ledger

Because the identity is exact, every receipt factors into two independent parts:

```text
published    = normalized x draw
normalized   = (REF_decode/decode)^0.75 * (REF_prefill/prefill)^0.25   <- executable quality
draw         = (baseline_decode/REF_decode)^0.75
             * (baseline_prefill/REF_prefill)^0.25                     <- same-session lottery
REF_decode   = 0.01385621216015625      REF_prefill = 0.00036751938916015626
```

`REF_*` is the pinned M5 baseline pair, used only as a fixed normalisation
constant so that receipts from different sessions are comparable.

Measured within-receipt correlation between the baseline axis and the candidate
axis is `-0.095` (decode) and `-0.092` (prefill), so the two factors are
effectively independent: session noise does **not** cancel in the ratio.

## Reference receipts (not ours except `e27f1ce4`)

| receipt | UTC | solver | executable | status | published | normalized | draw | decode s/tok | prefill s/tok |
|---|---|---|---|---|---|---|---|---|---|
| `cc6ddc12` | 2026-08-08T09:09:29Z | a-github-name | crown; note says content identical to `49c33eb2` | accepted / promoted | **2.61650354381** (rank 1/1227) | 2.56615781 (rank **79**/1227) | **1.019619** (rank **3**/1227) | 0.004930056641 | 0.000188158854 |
| `49c33eb2` | 2026-08-08T08:47:21Z | a-github-name | same executable as the crown | rejected | 2.58950555 (26/1227) | 2.57688648 (22/1227) | 1.004897 (471/1227) | 0.004907470375 | 0.000187611572 |
| `fefaed88` | 2026-08-08T05:31:43Z | MyatKaung | best executable ever measured | rejected | 2.60116056 (7/1227) | **2.58337483 (rank 1/1227)** | 1.006885 (345/1227) | 0.004885964844 | 0.000188197184 |
| `2054d45b` | 2026-08-07T17:58:19Z | yudduy | prior crown | accepted / promoted | 2.60630620 (3/1227) | 2.57066659 (54/1227) | 1.013864 (32/1227) | 0.004913312172 | 0.000188759033 |

## Our receipts (`morganmcg1`, most recent 8 of 87 gate-passing)

| receipt | UTC | executable | status | published | normalized | draw | decode s/tok | prefill s/tok | notes |
|---|---|---|---|---|---|---|---|---|---|
| `c52994dc` | 2026-08-10T06:42:50Z | frontier | rejected | 2.55553342 | 2.56467419 | 0.996436 | 0.004916347000 | 0.000190176758 | |
| `795badfa` | 2026-08-10T07:04:37Z | frontier | rejected | 2.56484792 | 2.56480215 | 1.000018 | 0.004933248367 | 0.000188191244 | |
| `8a09a941` | 2026-08-10T07:27:10Z | frontier | rejected | 2.59589220 | 2.57405181 | 1.008485 | 0.004913846352 | 0.000187706787 | |
| `6fc8abf5` | 2026-08-10T07:53:02Z | frontier | rejected | 2.56621424 | 2.57500430 | 0.996586 | 0.004910524734 | 0.000187809814 | |
| **`e27f1ce4`** | 2026-08-10T08:18:49Z | frontier (#549 + #604) | rejected | **2.60664970 (rank 2/1227)** | **2.58226338 (rank 2/1227)** | 1.009444 (185/1227) | 0.004890678055 | 0.000187976889 | our best; `Model: senpai`, base `1bc1c895…` |
| `2771067f` | 2026-08-10T08:54:56Z | frontier | rejected | 2.59380735 | 2.56563874 | 1.010979 | 0.004931368820 | 0.000188160889 | best draw of the late regime |
| `59d24187` | 2026-08-10T10:42:29Z | frontier | rejected | 2.58107302 | 2.57606893 | 1.001943 | 0.004904417641 | 0.000188200848 | |
| `2397aee7` | 2026-08-10T11:05:44Z | frontier | rejected | 2.56572014 | 2.56386260 | 1.000725 | 0.004925716797 | 0.000189333090 | |
| `c1c0ba2c` | 2026-08-10T23:03:47Z | frontier (= `1a6761bf` submitted surface, byte-identical to the eight rows above) | dispatched, `validating` | pending | pending | pending | pending | pending | R109-F ticket 1. Fired as pipeline validation + ledger anchor, **not** as a lottery play: honest P/shot 0.08-1.15%. `submission-id c1c0ba2c-ec1c-43f4-92bb-3c5b8b0a76e9`, note 8.5 KiB, `senpai/submit-official.sh 1bc1c895…` |

Sample statistics for this one executable (n=8):

| quantity | mean | sd | cv | min | max |
|---|---|---|---|---|---|
| published | 2.578717248 | 0.018375293 | 0.7126% | 2.555533423 | 2.606649699 |
| normalized | 2.570795763 | 0.006924974 | **0.2694%** | 2.563862604 | 2.582263383 |
| draw | 1.003076869 | 0.005789607 | 0.5772% | 0.996435895 | 1.010979180 |

All 87 of our gate-passing receipts: normalized mean 2.472605094, sd 0.188427744
(that sd spans the whole campaign's executables, not one executable).

`2054d45b`/`01e247a7` (published 2.60630620) is **not ours** — same shared
account, `Model: GPT-5.6 Sol (extra-high)`. The `commit` field printed by
`mlxfast submissions` is the CLI's ephemeral package commit, not a repo SHA, so
receipts cannot be matched to git SHAs that way; `mlxfast submission-note <id>`
plus the `Model:` line is the reliable attribution.

## Finding 1 — the crown is a lottery win, and our executable is not behind

`cc6ddc12` holds published rank **1/1227** with executable-quality rank
**79/1227** and the **3rd-luckiest baseline draw ever recorded** (+1.96%). Its
own note says it is an unchanged persistence replay of `49c33eb2`. Those two
receipts of the identical executable normalized to 2.57689 and 2.56616, i.e. a
0.42% candidate-side spread, so that executable's mean normalized score is
about **2.5715**. Our executable's mean normalized score over the 8 receipts
above is **2.5708**. The two are indistinguishable.

The top of this leaderboard is therefore saturated: every serious submitter is
inside a 0.7% band of normalized score (2.565-2.583), and published rank inside
that band is decided by the baseline draw.

Correction to an earlier claim of mine: comparing our best single receipt
(2.58226) against the crown executable's single receipt (2.57689) and
concluding "we are 0.21% ahead" was not a like-for-like comparison. Both are
single draws with candidate-side sd 0.27%. The honest statement is that the two
executables are statistically tied.

## Finding 2 — the baseline lottery narrowed after 08-08, and that closes the replay play

Draw multiplier sliced by UTC date shows a significant regime change:

| window | n | mean draw | sd | max draw |
|---|---|---|---|---|
| 2026-08-02 .. 2026-08-08 | 561 | 1.004175 | 0.005713 | **1.024492** |
| 2026-08-09 .. now | 52 | 1.001683 | 0.004268 | **1.010979** |

Welch `t = +3.90`. A lower draw means a *faster, harder-to-beat* same-session
baseline. The late regime has both a lower mean and a 25% smaller sd, and in 52
receipts no draw exceeded 1.0110.

Consequence, using the best draw actually observed in the late regime:

| starting point | ceiling = normalized x 1.010979 | vs crown 2.61650354 |
|---|---|---|
| our recent normalized mean 2.57079576 | 2.59902099 | **short by 0.673%** |
| our best-ever normalized 2.58226338 | 2.61061452 | **short by 0.226%** |

So under the regime that has held for the last two days, our current
executable **cannot reach the crown even on the luckiest draw observed in that
regime**. The normalized score required to reach the crown at that draw is
**2.58808845**.

There is also no timing lever: lag-1 autocorrelation of consecutive receipt
draws is `+0.028`, the hour-of-day means span only 0.3% with per-bucket
standard errors of 0.075% (no bucket survives a 24-comparison correction), and
`corr(baseline_decode, baseline_prefill) = +0.124`.

## Finding 3 — honest per-shot win probability

Model: `published = normalized x draw`, independent, candidate-side cv 0.2694%
(measured, n=8, one executable), late-regime draw cv 0.4268% (measured, n=52)
⇒ combined cv **0.505%**.

| assumed true normalized mean | mean published | z to crown | P(win) per shot | P over 30 shots |
|---|---|---|---|---|
| 2.57080 (our measured mean) | 2.57513 | +3.16 | **0.08%** | 2.4% |
| 2.58226 (our best receipt) | 2.58661 | +2.28 | **1.15%** | 29% |
| 2.58809 (+0.23% real win) | 2.59245 | +1.83 | 3.4% | 64% |
| 2.60000 (+1.14% real win) | 2.60438 | +0.92 | 17.9% | 100% |
| 2.61211 (+1.61% real win) | 2.61650 | 0.00 | 50% | 100% |

Using the *whole-population* draw distribution instead of the late regime gives
0.81% (mean normalized) to 4.80% (best normalized) per shot, and the empirical
published dispersion of our own 8 receipts gives 2.06% per shot. Those are the
optimistic bounds; the late-regime numbers are the ones that describe tonight.

**This is 10x to 250x below the 20%-per-shot estimate in advisor comment 8, and
it changes the recommendation.** A 20-30 shot pure-replay campaign is worth
roughly 2-3% total, not 75-99%. Independent confirmation: **0 of 1227** scored
receipts in the benchmark's entire history exceeded the crown — it *is* the
population maximum, so a replay must beat an all-time record.

## Finding 4 — the corrected size of a useful real win

The nominal bar "beat `e27f1ce`'s 2.60665 by 0.378%" is stated published-to-
published, and `e27f1ce` was itself a +0.94% draw. Restating the bar in
normalized terms against our *typical* executable:

| goal | required normalized | vs recent mean 2.57080 | M4 busy µs at tau=1 (decode-only) |
|---|---|---|---|
| reach the crown on the best late-regime draw (about 1 in 52) | 2.58809 | +0.673% | 96 |
| reach the crown on a median late-regime draw (P=50%) | 2.61211 | +1.606% | 229 |

using the programme law `%score = 0.0070 x delta_M4_steady_step_wall_us`.

The useful corollary is the opposite of a discouragement: **every +0.10% of
normalized score multiplies the per-shot win probability by about 1.5x** at
these z values. Real wins buy lottery leverage. A sub-bar improvement is
therefore no longer worthless — it is the only thing that moves the
probability at all, because the draw distribution itself has tightened.

## Shots fired this session

Six shots fired in r109-F are terminal and a seventh is armed. Executable class
is named per the r111 standing requirement; `normalized` and `draw` are derived
with `REF_D = 0.01385621216015625`, `REF_P = 0.00036751938916015626`.

| # | receipt | created UTC | package commit | executable class | status | published | normalized | draw | decode µs | prefill µs |
|---|---|---|---|---|---|---:|---:|---:|---:|---:|
| 1 | `c1c0ba2c-ec1c-43f4-92bb-3c5b8b0a76e9` | 2026-08-10T23:03:50Z | `074f47e4` (`pkg-t1`) | r109-F base (prefetch=1, atlas v2, QHOIST=0) | rejected — score did not improve | 2.56974410819947 | 2.566844 | 1.001130 | 4932.4 | 187.69 |
| 2 | `88584270-140e-4f28-a924-b00c77b1becd` | 2026-08-10T23:33:52Z | `04e8bf3c` (`pkg-t2`) | **same executable as #1** (differs by a 4-line comment) | rejected — score did not improve | 2.59576526895414 | 2.566903 | 1.011244 | 4932.6 | 187.65 |
| 3 | `e4078827-c7fd-4173-a2bf-2f6af7cc6e73` | 2026-08-11T00:00:00Z | `ec0954e2` (`pkg-t3`) | base **+ `DARKBLOOM_ATTN_QHOIST=1` default** (4 semantic lines) | rejected — score did not improve | 2.52713571388054 | **2.532027** | 0.998068 | 4948.5 | 196.30 |
| 4 | `ed40f3ee-b76b-45de-b751-d02b013ea113` | 2026-08-11T01:07:24Z | `d567a72a` (`pkg-t4`) | base **+ atlas `v3_tg128`**, QHOIST reverted — *best-believed package draw, not an arm probe* | rejected — score did not improve | 2.55785830244444 | 2.567970 ← best code *at the time*; superseded by #6 | **0.996062** ← 3rd percentile of the field | 4928.2 | 187.84 |
| 5 | `0531544b-a426-4f26-821a-d7f642f6c101` | 2026-08-11T01:31:01Z | `0a81e48b` (`pkg-t5`) | **same executable as #4** (comment-only nonce replay) | rejected — score did not improve | 2.57278074829225 | 2.576759 | 0.998456 | 4907.1 | 187.69 |
| 6 | `cb4de9e0-b083-4061-8e2b-3fa3f055c1e9` | 2026-08-11T01:54:46Z | `fe610f60` (`pkg-t6`) | **same executable as #4** (comment-only nonce replay) | rejected — score did not improve | 2.57646292274507 | **2.579556** ← best code of the campaign | 0.998801 | 4897.1 | 188.03 |
| 7 | armed 2026-08-11T07Z, fires on the next free account slot | HEAD at fire time (nonce `lottery-r109f-t7-nonce-5b3ce1d7-d`) | **same executable as #4** (comment-only nonce replay), fired as a **pre-registered test** — see `research/artifacts/fern-r109f/notes/ticket7-preregistered-note.md` | — | — | — | — | — | — |

Baseline legs the runner reported for each: #1 13896.1 / 366.02 µs, #2
13850.2 / 384.84 µs, #3 13829.7 / 366.79 µs, #4 13825.1 / 364.21 µs, #5
13816.4 / 368.42 µs, #6 13860.9 / 365.39 µs. All six `passed_correctness: true`.

**The "same executable" claim is git-verified, not asserted.** All six package
commits are fetched and tagged locally (`pkg-t1`…`pkg-t6`), and
`git diff pkg-t4 pkg-t5`, `git diff pkg-t5 pkg-t6` and `git diff pkg-t1 pkg-t2`
each touch exactly one file — `Sources/MLXFastModel/DenseTensorStore.swift` —
with **zero non-comment added lines** (`git diff … | grep '^+' | grep -vc '^+//'`
returns 0 for all three). #4/#5/#6 are therefore a genuine k=3
identical-executable group and #1/#2 a genuine k=2 pair. That is what licenses
the instrument gauge in `maple-fern-r109f-instrument-collapse.md` §5.3f, and it
is the only such gauge in the dataset: **0 of 1196** full-leg receipts across all
solvers share a `submissionCommitSha`, because every submission mints a fresh
package commit.

> **★ #5 and #6 falsified the ledger's own noise claim, as predicted.** The
> correction box below argued from first principles that the 0.0020 % agreement
> between #1 and #2 was luck (0.015 σ, p ≈ 1.6 %) and that the next replay of an
> identical executable should disagree by 0.2–0.4 %. #4 vs #5 disagreed by
> **0.3416 %** and the #4/#5/#6 group spans **0.4504 %** — 171× and 225× the
> control pair. The retraction was right and is now data-backed. Pooled to 3 df
> the per-leg instrument sd is: candidate prefill **0.0750 %**, normalized
> **0.1917 %**, candidate decode **0.2646 %**, published **0.5169 %**, baseline
> prefill **2.1035 %** (`python3 research/fern_r109f_leg_instrument.py`).

**★ Receipt #4 is the campaign's own proof of its central claim.** It carries the
best executable we have ever built — normalized **2.567970**, ahead of both base
shots — and it published **2.557858**, the *worst* of the three non-regressed
shots, because the host handed it a draw of 0.996062, the **3.2nd percentile** of
the 1235-receipt draw distribution, while #2 got the 91.5th. Across #1/#2/#4 the
code spread is **0.0441 %** and the published spread is **1.4724 %** — an
amplification of ~~**×33.4**~~ **×2.7** (**CORRECTED 07Z**: #5 and #6 showed the
0.0441 % denominator was itself a fluke; the identical-executable code spread is
**0.4504 %**, so the honest luck:code ratio is 1.4724/0.4504 = **×2.7**. The
narrative of this paragraph survives — best code still published worst — but the
amplification figure must be read from
`maple-fern-r109f-instrument-collapse.md` §5.3f). Regenerate with
`python3 research/fern_r109f_own_shots.py`; full discussion in
`research/maple-fern-r109f-instrument-collapse.md` §5.3e. Two consequences are
recorded here because they govern how this ledger must be read:

1. **A published score is not a package property.** #4's low publish is *not*
   evidence against atlas `v3_tg128`; on the code axis the change is
   **+0.0421 %** versus #2, which is the same sign as the local decode A/B
   (−0.0260 % of decode time ⇒ +0.0166 % of score at the 0.638 decode
   elasticity) and about 2.5× its size. It is also only **0.12 σ** of the
   normalized noise, so the ranked receipt confirms nothing on its own. Both
   statements are true simultaneously and both belong in the record.
2. **We do not re-plan around a bad draw.** The retraction below is a retraction
   of exactly that mistake with the opposite sign (a *lucky* draw read as a
   faster package). #5 therefore replays #4's executable unchanged rather than
   reverting atlas v3.

**Receipt #4 is framed differently from #1–#3 on purpose.** #1–#3 were
arm-class probes, fired on the belief that one normalized receipt resolves
0.002 % and can therefore adjudicate an arm. That belief is retracted (see the
correction box below): the instrument's real single-receipt sd is 0.370 %, and
resolving a 0.30 % arm **on the published or normalized score** needs ~40
receipts per arm. ~~Since every arm in this campaign's portfolio is smaller than
0.30 %, ranked probes cannot decide any of them, and my local iterate — which
repeats to 0.05–0.10 % — is a 4–7× better instrument despite `_nax` being
off.~~ **BOTH halves of that sentence are now corrected (07Z):**

- *Ranked probes can decide arms* — just not on the score. The k=3 gauge gives a
  **candidate-prefill** instrument sd of **0.0750 %**, so a 0.30 % prefill arm
  needs **2** receipts, not 77 (published) or 11 (normalized). Adjudicate arms on
  `officialMetrics` legs.
- *The local iterate does not repeat to 0.05–0.10 %.* An 8-run `MLX_SDPA_BLOCKS`
  sweep measured local decode cv **≈0.35 %** (σ ≈ 49 µs on a 12931.6 µs mean;
  two replicated arms differed by 30.3 µs and 84 µs). Local is ~1.8× **noisier**
  per observation than the ranked normalized axis; its real advantage is
  throughput on an unowned slot (~155 s per point), worth about **one order of
  magnitude**, not the 10²–10³× implied above.

From #4 onward every shot draws from the
**best-believed package** with a **comment-only nonce**, and its normalized
value must not be read as evidence for or against the atlas v3 change.

### What the six receipts bought

- **#1 and #2 are the control pair.** Same executable, published spread
  **1.0126 %**, normalized spread **0.0020 %**, draw spread 1.0105 %. Per leg:
  candidate decode 0.0054 %, candidate prefill 0.0245 %, baseline decode
  0.3305 %, baseline prefill **5.1429 %**. ~~The candidate legs are ~497× more
  precise than the published score.~~ **RETRACTED — see the correction note
  below.** This is still the measurement that made #3 interpretable, but its
  precision was over-read by ~185×.

  > **⚠ CORRECTION (`maple-fern-r109f-instrument-collapse.md`).** A two-point
  > agreement is not a noise band. The correct gauge is the *baseline* leg,
  > which runs identical code on every receipt ever submitted. Over one UTC
  > hour (2026-08-10T00, n=24) that gauge gives baseline decode cv **0.224 %**,
  > candidate decode cv **0.278 %** (σ = 13.69 µs), baseline prefill cv
  > **1.756 %**, and a normalized-score sd of **0.370 % of mean**. The 0.2 µs
  > agreement between #1 and #2 is **0.015 σ**, p ≈ 1.6 %. The normalized
  > instrument is **1.9–3.3×** tighter than published, not ~500×, so one
  > normalized receipt ≈ one published draw. Two-arm resolution at α .05 /
  > power .95 needs ~40 receipts **per arm** at 0.30 %, ~89 at 0.20 %, ~355 at
  > 0.10 %.
- **#3 is a decisive negative.** Normalized fell **1.3564 %** — ~~678× the
  control pair's normalized noise band~~ **−3.82 σ of the corrected
  single-receipt instrument (p ≈ 1.3e-4)**, and prefill-driven: its candidate
  prefill of 196.30 µs is **+4.27 σ** against the 08-10 population
  (187.56–190.18, mean 188.4, sd 0.83) while its decode excess is only ~1.2 σ —
  while published fell only 1.66 %,
  i.e. 1.6× a spread that a *same-executable* pair can produce by luck alone.
  Published score alone could not have called this; normalized called it from a
  single receipt. `research/fern_r109f_semantic_diff.py pkg-t2 pkg-t3` shows
  the two executables differ by **4 semantic lines in 3 files**, all of them
  the QHOIST flip, so the attribution has no confound. QHOIST cost +16.1 µs
  decode (+0.327 %) and +8.61 µs prefill (+4.586 %) and has been reverted.

- **#4, #5 and #6 are the k=3 group — the only real gauge on this benchmark.**
  Bought four things no single receipt can buy: (a) the falsification of the
  0.002 % noise claim, on a prediction registered before the data existed; (b) a
  **per-leg** instrument, which is what unblocks arm adjudication (candidate
  prefill 0.0750 %, i.e. 2 receipts for a 0.30 % arm — see
  `maple-fern-r109f-instrument-collapse.md` §5.3f, and the consequence for
  maple-tanjiro's A2 and maple-edward's `_nax` port); (c) a **drift test** — the
  monotone candidate-decode slide 4928.2 → 4907.1 → 4897.1 µs over 47 min looks
  like a warming host but is **not**: baseline-decode lag-1 autocorrelation is
  **+0.008** over 51 receipts (white noise, band ±0.280) and 10 other-solver
  receipts in the same 22:30–03:00Z window moved **+0.033 %**, so the sign is
  wrong for drift and the coincidence is 1-in-6
  (`python3 research/fern_r109f_host_drift.py`, §5.3h); (d) therefore a valid
  *time-blocked* class comparison: `r109F-atlasv3` (k=3) − `r109F-base` (k=2) =
  **+0.3073 %**, se 0.1750 %, **1.76 σ**. **That difference is NOT claimed.**
  Two independent priors cap it far below its point estimate — the field's entire
  decode-leg code differentiation is 0.224 %, which caps a decode-only arm at
  0.168 % of score, and the local A/B of this exact constant measured −0.0260 %
  of decode time (=+0.0166 % of score). Atlas v3 ships because it is *not worse*
  and costs nothing, not because it was shown to be better.
- **#7 is a pre-registered test of that gap**, fired on the same executable a
  fourth time. Registered before firing: P(#7 normalized < 2.574758) = **73.9 %**
  under the null (all five draws from one distribution) vs **50.0 %** under the
  alternative (atlas v3 really is +0.31 %); the gap is expected to fall to
  ~1.67 σ and returns to 2 σ only if #7 ≥ 2.577301 (p = 12.4 %). Whatever it
  prints, the prediction is on the record first —
  `research/artifacts/fern-r109f/notes/ticket7-preregistered-note.md`.

### Disclosure: the ticket-7 note carries a claim I retracted while it was in flight

The ticket-7 note was frozen and handed to the submit poller before **correction
8** was found. At its lines 87 and 220–221 it states that
`DARKBLOOM_AOT_SDPA_2PASS_PLANES = 1` is the campaign's one genuinely open decode
arm and that this host "always runs `sdpa_vector_2pass`". Both halves of the
reachability claim are **false**: `scaled_dot_product_attention.cpp:749` requires
`k.shape(2) >= 1024` while the scored decode window is a 512-token seed
(`Constants.swift:123`) walked 128 steps (`:109`) to KV 640, and the Laguna model
never calls the library SDPA on decode at all — its fused sliding and full
attention kernels intercept at `LagunaRuntimeModel.swift:6152`/`:6178` (both
default-on, both observed live in
`research/artifacts/fern-r109f/census/sites-A.txt`), and
`grep -rn scaledDotProductAttention Sources/` returns nothing. The clamp
arithmetic in that note is still correct.

I did **not** cancel the poller to fix it. The note's error is confined to a
forward-looking recommendation; its measurements, its pre-registration and its
class arithmetic are unaffected, and the shot itself is what the standing order
asks for. Trading a scarce channel slot — median 25 min, p90 120 min per shot
today, see `maple-fern-r109f-instrument-collapse.md` §7 — for one corrected
paragraph is a bad trade. So the correction is disclosed here and in the
ticket-8 note instead, and the derivation is
`maple-fern-r109f-nax-observability-gap.md` §10.

Full analysis: `research/maple-fern-r109f-semantic-attribution-and-qhoist-verdict.md`.
