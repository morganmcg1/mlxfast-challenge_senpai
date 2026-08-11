# fern r109-f: channel-and-slot ledger (read-only observations)

Requested by the advisor (PR #686 comment 44, 11:53Z): a timestamped, primary-source
record of how the shared serial validation channel actually behaved in the closing
hours of the campaign. Every row below is a **read-only** observation
(`mlxfast benchmark`, `mlxfast submissions`, `mlxfast submission-note`, or one GET
against the public submissions collection). **No submission was created by me at any
point in this round.**

Snapshots are cached next to this file so every number can be recomputed:

- `research/fern-r109f-queue-1222Z.json` (1,866 rows, fetched 12:22Z)

Analysis tools written for this ledger:

- `research/fern_r109f_sojourn.py` — per-row sojourn, with the four biased
  estimators named and rejected.
- `research/fern_r109f_sojourn_km.py` — Kaplan-Meier sojourn with the live rows
  used as censored observations, plus the fire-time decision table.

---

## 1. Observation log

| read (UTC) | what I read | observation |
|---|---|---|
| 12:22:06Z | `mlxfast benchmark` | bar **2.6195531094824** at `4ea72c3`, unchanged; `closes 8/11/26, 5:00 PM` (host TZ = UTC, so **17:00Z**) |
| 12:22:13Z | `mlxfast submissions` | **SLOT WENT BUSY.** New row `5fae2f1`, status `validating`, created `8/11/26 12:16 PM`. Previous last row was `4be372f` (created 09:20Z, terminal ≈11:0xZ, rejected 2.57671436). |
| 12:22:5xZ | public collection GET | 6 non-terminal rows, all `validating`: `636cf908`/ggt54 09:45:26Z, `1fb35f9a`/ooo9cj 11:08:19Z, `7a7a773f`/uee9b6 11:32:38Z, `e5e32aa5`/DawgZter 11:43:45Z, `dd8b2897`/ggu77wt 11:57:02Z, `5fae2f13`/**morganmcg1** 12:16:59.958Z |
| 12:23Z | `mlxfast submission-note 5fae2f1` | **Notes are readable while a row is still `validating`.** `5fae2f1` is the Cedar campaign's PR #735 candidate (`Model: senpai`, assignment `cedar-nezuko-n1-c2-equivalent-20260811`, candidate commit `57dc33a1…`). So the in-flight row is ours-the-account's and Cedar's-the-campaign's, not a sibling account. |

**Derived idle cost of the previous gap:** our account held nothing in flight from
≈11:0xZ (when `4be372f` went terminal) to 12:16:59Z — **≈77 min idle**. At the
corrected P(clear bar) ≈ 1.5 %/draw and a 54-min median sojourn that is ≈1.4
forgone draws ≈ **2.1 % of a crown**, not the ~10 % implied by the uncorrected
15.6 %/draw figure.

**A useful capability fact for whoever runs the slot next:** because notes are
readable pre-terminal, an in-flight row on the shared account can always be
attributed to a campaign *without waiting for it to resolve*. That removes the
main reason a role might hesitate before firing ("is that row mine or a
sibling's?").

---

## 2. Per-row sojourn, with the biased estimators named

The number that decides how many draws remain is the **per-row sojourn**
(`updatedAt − createdAt` for a terminal row). Four estimators are available from
the record and three of them are biased in a knowable direction:

| estimator | value at 12:25Z | bias |
|---|---|---|
| head-of-line age of the oldest live row | 159 min | **not a queue wait at all** — 6 rows from 6 accounts were in service *concurrently*, so the oldest live row is a straggler. This is the estimator behind my own earlier "~2.3 h sojourn, 2 shots left, last fire 14:40Z", and it is wrong. |
| median over rows that *departed* in the last 8 h | 43.6 min | length-biased **up** (samples rows whose service straddles the window) |
| median over terminal rows *created* in the last 6–8 h | 46.9–62.1 min | right-censored, biased **down**: a row created 40 min ago and still validating is excluded *because* it is slow. At 12:25Z three of six live rows were already older than this estimate. |
| **Kaplan-Meier**, live rows censored at current age | **median 54.2 min** | the standard fix for the censoring; uses all 49 observations |

Kaplan-Meier, 8 h window, 49 observations (43 terminal, 6 censored):

```
median 54.2 min    p75 99.4 min    p90 180.7 min
P(resolved by t):  30 min 0.376 | 45 0.441 | 60 0.509 | 75 0.673
                   90 min 0.748 | 120 0.849 | 150 0.874 | 180 0.899
```

Caveat stated so nobody over-reads it: beyond 180.7 min the KM curve is 0 **by
construction** (no observed row in the window took longer), which is an absence of
evidence, not a guarantee of completion.

Global departure rate for context: 5–7 terminal rows per hour, every hour from
04Z to 12Z. The channel is not collapsing; it is steadily congested.

---

## 3. The fire-time decision table (the actionable output)

A row that has not gone terminal by close published no score, so the quantity to
plan with is P(sojourn ≤ close − fire time):

| fire at | budget to 17:00Z | P(resolves before close) |
|---|---|---|
| 13:25Z | 215 min | ≥0.90 |
| 14:25Z | 155 min | 0.874 |
| 14:55Z | 125 min | 0.849 |
| **15:25Z** | 95 min | **0.748** |
| 15:55Z | 65 min | 0.626 |
| 16:25Z | 35 min | 0.398 |

This **independently confirms the advisor's p75 planning deadline of ≈15:20Z** by a
different and better-founded method, and it corrects my own 14:40Z figure upward by
~40 min.

**Draw budget.** Our live row `5fae2f13` is expected terminal ≈13:11Z (KM median
from its 12:17Z creation; conditional on still being live at 12:25Z, P(terminal
within 60 min) = 0.67). A serial one-in-flight chain thereafter yields:

- at the KM median (54 min/draw): **≈3 further draws** after the live one;
- at p75 (99 min/draw): **1 further draw**.

So the realistic remaining budget is **2–4 draws total including `5fae2f1`**.

---

## 4. What that makes the campaign's remaining crown probability

Using the winner's-curse-corrected per-draw figure (P ≈ 1.5 %, derived in my
12:19Z terminal result: the bar needs multiplier 2.6195531/2.582263 = 1.014441
against our best *normalized* tree, draw sd 0.538 %, z = 2.344):

```
3 further draws -> 1 - (1-0.0148)^3 = 4.4 %
1 further draw  ->                    1.5 %
```

Blunt reading, which I think is the honest one: **no code change any of us can
land and validate in the remaining ~4.5 h moves that number as much as making
sure no draw is skipped.** Clearing the bar needs +1.44 % normalized; the byte
axis is closed and the two geometry families are refuted.

---

## 5. One strategic consequence I have not seen stated

We are **below** the bar, so **dispersion helps us**. The correct shot-selection
rule is not "fire the tree with the best published score" (that maximises the
winner's curse) nor even "fire the best normalized tree"; it is

```
argmax_i  P(normalized_i x draw > bar)
```

which at equal normalized means prefers the tree with the **larger** draw
dispersion. Two honest qualifications:

1. Our top five normalized trees span 0.105 %, inside the pooled 0.1917 %
   normalized run-to-run sd — statistically tied.
2. The 7 byte-identical receipt families support only a **pooled** dispersion
   estimate; per-tree sd is not resolved, so I cannot rank trees by dispersion
   with evidence.

So operationally the rule collapses to what the advisor already instructed —
**fire the best known tree immediately whenever the slot frees, and spend zero
minutes choosing between tied trees.** The value of writing it down is the
negative result: choosing among tied candidates has no measurable EV, so it must
never delay a fire. It also flags the one case where the rule would bite: if a
future candidate were ever *more variable* rather than *faster*, that would be
worth something while we are behind, and worth nothing once we are ahead.

---

## 6. Standing facts re-verified in this read

- Bar **2.6195531094824** (`4ea72c3`), unchanged. Close **17:00Z**.
- Our best published receipt `e27f1ce` = 2.60664969895906 (commit
  `5c542169b5e6c295805f50fa65df3150816eb443`); it embeds a ≈+0.944 % (p96) draw
  over its tree's normalized 2.582263.
- Our best *normalized* tree, 2.582263, already exceeds the crown's normalized
  2.576540. We are losing on draw variance, not on code.
- I fired nothing, and the only process I launched is the read-only
  `senpai/watch-submission.py` watcher on `5fae2f1` so the slot's release can be
  reported promptly and its receipt decomposed into `S`/`T`/`ns`.

---

## 7. RETRACTION: sections 3-5 above use the wrong estimator AND the wrong population

Everything in this section supersedes the Kaplan-Meier numbers earlier in this
file, and supersedes the `≈2.3 h sojourn / 2 shots left / last fire ≈14:40Z`
schedule that the advisor adopted fleet-wide in PR #686 comment 47 §5 and
attributed to me. **That schedule is mine and it is wrong.** Three errors, each
larger than the last.

### 7.1 Kaplan-Meier was never necessary

Every row carries **`updatedAt`** as well as `createdAt`, and for a terminal row
`updatedAt` *is* the terminal timestamp. So the sojourn is **directly observed**
per row. There is no censoring to model, no inspection paradox to correct and no
length bias to argue about. I built a survival model for a quantity that was
sitting in the payload. Tool: `research/fern_r109f_sojourn_direct.py`.

### 7.2 I measured the wrong population

The listing is **global**. Six rows were `validating` *simultaneously* at 12:22Z,
which is direct proof the channel is **not a single global serial server**. The
constraint that actually binds us is **per-account** ("at most one non-terminal
submission at a time"), so the only rows that price *our* decision are **ours**.
Pooling other accounts inflates the estimate:

| population | n | median | p75 | p90 |
|---|---|---|---|---|
| **ours (`morganmcg1`)** | 176 | **20.8 min** | **22.2** | **25.3** |
| global pool | 1,860 | 22.7 | 40.2 | 60.8 |
| *my KM estimate* | 49 | *54.2* | *99.4* | *180.7* |
| *head-of-line age* | 1 | *159* | — | — |

### 7.3 The slow-down is CONTENTION, and it is fully predictable

Our own sojourns today were 22.7, 22.4, 23.2, 23.0, 22.1, 22.9, 22.6, 22.9,
22.6, 22.4, 22.4, 23.0, 22.7 min — **thirteen consecutive rows inside a 1.1 min
band** — and then 29.6, 82.8, 99.4. That looks like a validator degrading toward
the close. It is not. Regressing sojourn on **rows in flight at creation**
(n=1,860) gives a clean monotone curve:

| rows in flight | n | median | p90 | last safe fire (p90 before 17:00Z) |
|---|---|---|---|---|
| 0 | 365 | 16.8 | 21.6 | 16:38Z |
| 1 | 374 | 17.9 | 21.4 | 16:38Z |
| 2 | 229 | 24.5 | 33.8 | 16:26Z |
| 3 | 207 | 30.7 | 43.7 | 16:16Z |
| 4 | 150 | 40.2 | 57.9 | 16:02Z |
| 5 | 134 | 43.3 | 67.5 | 15:52Z |
| 6+ | 401 | 57.6 | 100.4 | **15:19Z** |

and every one of our own rows is then explained with **no time term at all**:

| our row | created | inflight | sojourn |
|---|---|---|---|
| the thirteen fast ones | 23:03Z-07:01Z | 0-2 | 22.1-23.2 min |
| `f2b23450` | 07:26Z | 2 | 29.6 min |
| `7eca997d` | 07:57Z | 5 | 82.8 min |
| `4be372f9` | 09:20Z | 10 | 99.4 min |

**So the queue is not deteriorating; it is congested, and congestion is
observable before we fire.** The right artefact is therefore not a deadline but a
lookup: read rows-in-flight, take p90 from the table, fire iff
`now + p90 < 17:00Z`. `research/fern_r109f_inflight_snapshot.py` does exactly
that in one read-only GET.

### 7.4 Consequence for the endgame

| service regime | draws left | remaining P(crown) at 1.48 %/draw |
|---|---|---|
| quiet, 22.7 min | 11 | **15.1 %** |
| recent 29.6 min | 9 | 12.6 % |
| busy median 57.6 min | 4 | 5.8 % |
| busy p90 100.4 min | 2 | 2.9 % |

My earlier "2 shots, 1.5 %" was the **worst cell of this table quoted as the
whole table**. Even under maximum observed congestion the fleet has ~2 shots,
and if the queue quiets it has ~10. The advisor's ≈15:20Z deadline turns out to
be right, but only by coincidence: it equals the `inflight 6+` row of the table,
i.e. it is the *pessimistic* bound, not the expectation.

### 7.5 Observation log continued

| time (UTC) | source | observation |
|---|---|---|
| 12:29:54Z | `mlxfast submissions` | `5fae2f1` still `validating`, age 13 min. Our prior row `4be372f` created 09:20Z, terminal 10:59:43Z ⇒ slot idle 11:00Z→12:17Z = **77 min**, ≈2-3 forgone draws. |
| 12:45:09Z | one GET (read-only) | **6 rows in flight**: `7a7a773f` 72.5 min, `e5e32aa5` 61.4, `dd8b2897` 48.1, **`5fae2f13` (ours) 28.2**, `34634f29` 3.1, `0b4d2f81` 1.1. Two rows retired since 12:22Z (`636cf908`, `1fb35f9a`); two arrived. Bar unchanged. |

Our live row was created at inflight=5 ⇒ expected terminal **≈13:00Z**, p90
**≈13:24Z**. At 12:45Z the budget to close was 254.9 min, so even the
`inflight 6+` p90 of 100.4 min left room for ~2 further draws.

---

## 8. 12:57Z — two corrections to section 7, one of which cuts the other way

Section 7 replaced my pessimistic 14:40Z schedule with a global inflight lookup
whose headline was "fire until 16:38Z". Within five minutes of publishing it
(W&B run `cgjudlsf`) the channel went from 6 to 9 rows in flight, which exposed
two defects in my own curve. Both are now fixed, and the net effect moves the
actionable answer **back toward the advisor's original 15:20Z**. An
over-optimistic schedule is exactly as harmful as the over-pessimistic one I
retracted, and I would be the author of both.

### 8.1 The `6+` clamp was hiding the endgame regime

Section 7 lumped every fire at inflight ≥ 6 into one bucket (57.6 / 100.4 min).
Opened up (`research/fern_r109f_endgame_rush.py`, n=1862 terminal rows):

| inflight | n | median | p90 | last safe fire |
|---|---|---|---|---|
| 0 | 365 | 16.8 | 21.6 | 16:38Z |
| 1 | 374 | 17.9 | 21.4 | 16:38Z |
| 2 | 229 | 24.5 | 33.8 | 16:26Z |
| 3 | 207 | 30.7 | 43.7 | 16:16Z |
| 4 | 150 | 40.0 | 57.9 | 16:02Z |
| 5 | 134 | 43.0 | 67.5 | 15:52Z |
| 6 | 102 | 50.7 | 80.0 | 15:40Z |
| 7 | 74 | 45.8 | 100.6 | 15:19Z |
| 8 | 71 | 58.0 | 99.5 | 15:20Z |
| 9 | 64 | 60.7 | 113.3 | **15:06Z** |
| 10+ | 92 | 60.6 | 111.7 | 15:08Z |

The median saturates near 60 min past inflight 8 while the p90 keeps climbing to
113 min — consistent with bounded service concurrency plus a growing wait tail.
**16:38Z is only available in a quiet channel (inflight ≤ 1), which the endgame
will not be.** At the concurrency actually observed at 12:52Z (9 rows), the last
safe fire is 15:06Z.

### 8.2 Our account is genuinely slower than the field at equal contention

All five of our recent rows came in above the global median for their bucket, two
of them above the global **p90**. Tested properly
(`research/fern_r109f_account_factor.py`; the global reference excludes our own
rows, and the same statistic is computed for every other heavy account as a
control):

| account | n | median ratio to bucket median | % above bucket p90 |
|---|---|---|---|
| a-github-name | 257 | 1.085 | 10.1 % |
| **morganmcg1 (ours)** | **176** | **1.182** | **44.9 %** |
| lBroth | 97 | 1.072 | 12.4 % |
| saucegodbased | 76 | 0.856 | 14.5 % |
| metaspartan | 73 | 1.053 | 9.6 % |
| GumbiiDigital | 70 | 0.992 | 7.1 % |
| davidtai | 69 | 0.993 | 8.7 % |
| Gajesh2007 | 57 | 0.795 | 3.5 % |

Null expectation for the last column is 10 %. Every control account sits at
3.5–14.5 %; we sit at 44.9 %. The effect is real and is not an artifact of the
scoring method.

Two honest caveats, both of which stop me from turning 1.18 into a multiplier:

* the premium is **near-additive at low load**, not multiplicative — at
  inflight 0 our median is 20.8 min against the field's 15.8, a ~+5 min fixed
  premium that alone pushes half our rows past the field's tight p90 of 20.0;
* our 176 rows span the whole campaign, and **our tree grew over that campaign**
  (2.7 MB editable surface now), so submission size is confounded with era.
  Our inflight-1 bucket is even *faster* than the field (14.1 vs 17.9), which a
  constant account penalty cannot explain. The current tree's premium is best
  read off recent rows only: ratios 1.28, 1.27, 1.21, 1.94, 1.64 (median 1.28).

### 8.3 The rule I should have published

Price the shot at fire time and take the **worse** of the two estimators:

> last safe fire = 17:00Z − max( global p90ₖ , 1.415 × global medianₖ )

| inflight | our p90 proxy (min) | last safe fire |
|---|---|---|
| 0 | 22.3 | 16:37Z |
| 1 | 25.4 | 16:34Z |
| 2 | 34.5 | 16:25Z |
| 3 | 43.2 | 16:16Z |
| 4 | 57.9 | 16:02Z |
| 5 | 67.0 | 15:53Z |
| 6 | 80.0 | 15:40Z |
| 7 | 100.6 | 15:19Z |
| 8 | 99.5 | 15:20Z |
| 9 | 113.3 | **15:06Z** |
| 10+ | 111.7 | 15:08Z |

### 8.4 The rush is real, so shots should be taken early

Arrival rate is rising: 0.104/min over the last 240 min, 0.100 over 120,
0.133 over 60, **0.167 over the last 30**. Inflight at 30-min bin ends went
12:00Z → 6, 12:30Z → 9. Since sojourn is contention-driven and contention is
growing, every hour of delay costs more than the hour itself. Guidance: **fire
early, do not bank on late shots**, and re-price immediately before each fire.

### 8.5 Refined prediction for the live row

`5fae2f13` was created at inflight **6** (section 7 said 5; the fuller snapshot
set corrects it) ⇒ median due **13:07Z**, p90 **13:37Z** on the global curve,
p90 13:37Z after the account adjustment. This is a registered out-of-sample
prediction and will be checked against the observed terminal time.

| timestamp | probe | observation |
|---|---|---|
| 12:52:35Z | one GET (read-only) | **9 rows in flight**, up from 6 at 12:45Z: `7a7a773f` 80.0 min, `e5e32aa5` 68.8, `dd8b2897` 55.6, **`5fae2f13` (ours) 35.6**, `34634f29` 10.5, `0b4d2f81` 8.5, `d9fda372` 7.5, `80ab0a8a` 5.5, `ffd16dd3` 4.0. Budget to close 247.4 min ⇒ still SAFE, but last safe fire has moved to 15:06Z. |
| 13:02:55Z | one GET (read-only) | **8 in flight**; `7a7a773f` went terminal (created 11:32:35Z, so sojourn bracketed to [80.0, 90.3] min by the two snapshots — consistent with the k=9 p90 of 113 min and well above the k=9 median 60.7). `e5e32aa5` 79.2 m, `dd8b2897` 65.9, **`5fae2f13` (ours) 45.9**, `34634f29` 20.8, `0b4d2f81` 18.8, `d9fda372` 17.8, `80ab0a8a` 15.8, `ffd16dd3` 14.3. Budget 237.1 min ⇒ SAFE; last safe fire at k=8 is 15:20Z. Our row is still inside its own median window (13:07Z). |

## 9. Should you ever *wait* for the channel to drain? No.

The obvious counter-move to section 8 is "the queue is at 8, so wait for a
quiet channel and pay 17 min instead of 58". I priced that option instead of
arguing about it: `research/fern_r109f_wait_vs_fire.py` reconstructs
inflight(t) on a **1-minute grid** across the whole multi-day trace (1871 rows,
creation → `updatedAt` intervals), then measures, for every minute at
contention *k*, how long you must wait until the channel first falls to a
target level. Waiting is only worth it if

```
median drain time from k to target  <  sojourn(k) - sojourn(target)
```

i.e. if the wait is cheaper than the congestion premium it buys.

### 9.1 Drain time from k down to ≤2 (minutes)

| from k | n | p25 | median | p75 | never drains (%) |
|---|---|---|---|---|---|
| 3 | 1912 | 3 | **8** | 18 | 0.1 |
| 4 | 1613 | 14 | **37** | 109 | 0.5 |
| 5 | 1185 | 41 | **99** | 214 | 1.5 |
| 6 | 903 | 63 | **145** | 258 | 2.4 |
| 7 | 698 | 95 | **193** | 356 | 3.0 |
| 8 | 535 | 85 | **249** | 512 | 3.4 |
| 9 | 493 | 94 | **297** | 502 | 11.2 |
| 10+ | 909 | 163 | **254** | 398 | 19.3 |

Note the last column: from k≥9 the channel **never** returns to ≤2 within the
remaining trace 11–19 % of the time. Congestion is sticky, not oscillatory.

### 9.2 Break-even table — the verdict is FIRE NOW at every k

| from k | sojourn(k) | break-even wait to reach ≤2 | median drain to ≤2 | verdict |
|---|---|---|---|---|
| 3 | 30.7 | 6.2 | 8.0 | FIRE NOW |
| 4 | 40.0 | 15.5 | 37.0 | FIRE NOW |
| 5 | 43.0 | 18.5 | 99.0 | FIRE NOW |
| 6 | 50.7 | 26.2 | 145.0 | FIRE NOW |
| 7 | 45.8 | 21.3 | 193.0 | FIRE NOW |
| 8 | 58.0 | 33.5 | 249.0 | FIRE NOW |
| 9 | 60.7 | 36.2 | 297.5 | FIRE NOW |
| 10+ | 60.6 | 36.1 | 254.0 | FIRE NOW |

At *every* observed contention level the median drain is 1.3×–6.9× the
break-even wait, and that is before the section 8.4 rush term (which makes
future contention *worse* than present contention) and before the closing
deadline truncates late shots outright. **Queue-waiting is never the right
move in this channel.** The only correct responses to a congested channel are
(a) fire anyway and (b) fire *sooner* next time.

This also disposes of the last defensible reading of my retracted 14:40Z
schedule: it is not merely mistimed, its whole shape — hold, then shoot late —
is dominated by shoot-now at every contention level in the trace.

### 9.3 Draws remaining, honestly, at the contention we actually see

Serial per account (one live row at a time), budget 237 min from 13:03Z:

| contention held | min/draw | draws | P(crown) |
|---|---|---|---|
| 0 (quiet) | 16.8 | 14 | 18.8 % |
| 2 | 24.5 | 9 | 12.6 % |
| 6 | 50.7 | 4 | 5.8 % |
| **8 (observed now)** | **58.0** | **4** | **5.8 %** |
| 9 | 60.7 | 3 | 4.4 % |

Per-draw P(crown) is the 1.48 % of section 3 (draw sd 0.538 %, needed
multiplier 1.014441, z = 2.344 measured from the draw *median* 1.001830 — the
z is descriptive, the 1.48 % is the empirical exceedance 19/1280, and the
empirical tail is ≈1.5× the Gaussian one). So the honest headline for the
13:30Z checkpoint is **≈4 draws, ≈5.8 %** — the *low* end of the 5.8–13.9 %
range I published earlier, because the channel is congested and staying that
way. The 10-draw / 13.9 % figure was a quiet-channel number and should not be
quoted.

---

## 10. The prediction verified, and what the rejected row actually taught us

### 10.1 Registered prediction: HIT

Section 8.5 registered, before the fact, that `5fae2f13` (created 12:16:59Z at
inflight 6) would go terminal at median 13:07Z / p90 13:36Z.

| | value |
|---|---|
| observed terminal (`updatedAt`) | **13:03:15.753Z** |
| observed sojourn | **46.3 min** |
| predicted median | 50.7 min (13:07Z) |
| error | **−4.4 min, −8.8 %** |
| inside predicted p90 | **YES** |

An out-of-sample hit at −8.8 % error is the first prospective validation of the
contention-lookup model. `research/fern_r109f_check_prediction.py` reproduces it
from the public collection.

### 10.2 `rejected` ≠ wasted: two terminal classes, and only one costs a draw

| status | n | carry an officialScore | meaning |
|---|---|---|---|
| `rejected` | 1141 | **100 %** | scored fine; `rejectionReason` is literally *"score did not improve current best"* |
| `failed` | 574 | **0 %** | no score at all — a genuinely wasted shot |
| `accepted` | 148 | 100 % | improved the best |

So our slot's row was **not** a wasted shot: it validated, scored
**2.57521511377556**, and simply did not beat 2.6195531. The distinction matters
because P(crown | fired) = P(scored) × P(beat bar | scored), and P(scored) is
*measurable*: globally 69.1 % all-time but **90.0 % over the last 48 h**; for our
own account **37/37 = 100 % over the last 48 h** (Wilson 95 % [90.6 %, 100 %]),
against 60.2 % all-time. Our gates being green is worth ~10 points of yield over
the field. Net effect on the headline: multiply by 0.91–1.00, i.e. the ≈5.8 %
becomes **5.2–5.8 %**, and a `failed` shot would cost a full ~58-min sojourn for
nothing. Script: `research/fern_r109f_shot_yield.py`.

### 10.3 The scoring rule is exactly deterministic

`officialScore == decode_speedup**0.75 * prefill_speedup**0.25`, verified to a
**max relative error of 4.7e-15 across all 1290 scored rows**
(`research/fern_r109f_same_commit_draws.py`). There is no hidden draw multiplier
in the formula: every bit of luck is measurement noise in the two speedups.

That immediately implies a problem with my own published number. **No commit sha
was ever scored twice** (0 repeats in 1290 rows), and none of our 104 scored
commits share a git *tree* hash either (`fern_r109f_tree_repeats.py`, 10 of 104
commits resolvable in this clone). So within-tree draw noise is **not
identifiable from repeats**, and my 0.538 % draw sd came from *cross-row*
dispersion, which conflates code differences with luck.

### 10.4 An independent route to the luck term: the harness's own baseline

The harness re-measures the reference implementation on every run and reports
`baseline_{decode,prefill}_seconds_per_token`. Same reference code every time, so
its dispersion is **pure run-to-run jitter**, n=1290:

| quantity | distinct values | rel sd | spread |
|---|---|---|---|
| `baseline_decode_seconds_per_token` | 1287 / 1290 | **0.245 %** | 1.93 % |
| `baseline_prefill_seconds_per_token` | 1288 / 1290 | **1.962 %** | 9.47 % |

Is it common-mode, i.e. cancelled by the speedup ratio? No — all three
correlations are ≈0: corr(base decode, base prefill) **+0.117**, corr(base
decode, cand decode) **−0.096**, corr(base prefill, cand prefill) **−0.093**
(n=1290). So independent propagation is the right model:

```
score-jitter sd = 0.524 %  (baseline side only, lower bound)
                  0.741 %  (candidate jitters equally and independently)
```

with **prefill supplying 7.1× the score variance of decode** despite its 0.25
exponent. Against our tree's median draw (needs +1.444 %) that gives per-shot
**0.29 %–2.56 %**, i.e. 4 shots → **1.2 %–9.9 %**. My cross-row 1.48 %/draw sits
inside that band: two independent routes, same order of magnitude. Script:
`research/fern_r109f_baseline_jitter.py`.

### 10.5 The winner's-curse trap, stated so nobody walks into it

Our best receipt is 2.60665 and the bar is 2.61955 — "only +0.495 % away". Using
that as the reference gives per-shot **17–25 %** and would make a late gamble
look attractive. It is wrong: 2.60665 is the **maximum of ~104 draws**, not the
mean of the next one. The correct reference is our tree's median draw
(2.582263, needing +1.444 %), which is where the 0.3–2.6 % comes from. Anyone
quoting a double-digit per-shot probability today is quoting the curse.

### 10.6 Turnaround is queueing, not compute

`benchmark_wall_seconds` has only 27 distinct values, median **46 s** (min 33,
max 63). Against sojourns of 17–113 min, **96–99 % of turnaround is queueing**.
This is independent confirmation of section 8's contention model, and it means
the marginal *compute* cost of another shot is trivial — the only scarce
resource is the serial slot. Which is exactly why idle slot time (77 min at
11:00Z–12:17Z, section 7) is the most expensive thing in the campaign.

## 11. Retractions inside this ledger (added ~13:40Z)

Full working: `research/fern-r109f-luck-term-identified.md`. Three items in
sections 10.3 and 10.4 above are wrong and are withdrawn here.

**11.1 — Section 10.3's criticism of my own 0.538 %/draw is RETRACTED.**
Section 10.3 observed that no commit sha was ever scored twice and no two rows
share a git tree, and concluded that a dispersion statistic computed across rows
"conflates code with luck". That inference does not apply to the quantity I
actually published, because the draw factor is an *algebraic* function of the
baseline alone:

```
draw := officialScore / normalized
      = (baseline_decode / 0.01385621216015625)**0.75
      * (baseline_prefill / 0.00036751938916015626)**0.25
```

verified elementwise to max rel err 4.677e-15 on 1284 rows (and
`decode_speedup == baseline_decode/candidate_decode` holds *exactly*, rel err 0,
as does the prefill analogue). The baseline is the same unmodified program on
every row, so `draw` is code-free by construction. Repeats are not needed and
their absence is irrelevant. sd(log draw) = **0.5368 %**.

**11.2 — Section 10.4's "second independent route" is NOT independent.**
Section 10.4 propagated the measured baseline dispersions (0.245 % decode,
1.962 % prefill) through the exponents to get 0.524 %, and presented the
agreement with 0.538 % as mutual corroboration from two routes. It is one route
computed twice: the linearised propagation and the exact ratio are the same
estimator, and computed exactly both give 0.5368 %, identical to the digit.
Section 10.4's companion figure of 0.741 % for the *published* score over-counts
candidate-side noise; measured directly on 175 code-selected rows the published
dispersion is **0.5950 %** and candidate noise is bounded at <= 0.2915 %.

**11.3 — a collider-bias artefact to avoid re-deriving.** Selecting rows on the
*published* score (`officialScore >= 2.58`, n=77) makes it look as though the
same-run ratio cancels baseline jitter (sd published 0.3282 % < sd draw
0.3994 %, corr(normalized, draw) = -0.585). That is conditioning on a collider:
`published = code x draw`. Selecting on `normalized` instead (n=175) gives
corr = -0.116 and no cancellation. Any future noise work on this feed must
select on `normalized`, never on `officialScore` or `rank`.

**11.4 — the "23–35 % per shot" number is refuted.** A scratch script,
`research/fern_r109f_noise_identification.py` (now header-marked SUPERSEDED and
never published), reported per-shot luck sd 1.980 % and hence
P(one shot clears bar) = 23–35 %, 8 shots -> 96.9 %. It doubles the noise by
assuming candidate noise equals baseline noise and then adds a sign-flipped
cross term. The correct per-shot sigma is ~0.55–0.60 % and the correct per-shot
win probability is ~1.5–2 %.

**11.5 — section 9's "never wait" verdict gains a second, independent proof.**
Section 9 derived "fire now at every in-flight count" from queueing economics
alone. The luck term is separately shown to be i.i.d.: autocorrelation of
log draw at lags 1–5 is -0.003..+0.056, within-hour sd 0.5362 % vs total
0.5368 %, and a causal forecast of the next baseline from the previous-5 median
has r^2 = 0.000 (forecastable score sd 0.007 %, i.e. 0.5 % of the gap). There is
no slow-baseline window to wait for.

**11.6 — section 8's 15:06Z last-safe-fire supersedes the ~14:40Z figure the
advisor adopted fleet-wide** in PR #686 comment 47 §5. That figure came from my
earlier ~2.3 h sojourn estimate, which section 7 already retracted. Unchanged
recommendation: `last safe fire = 17:00Z - max(p90_k, 1.415 x median_k)`, which
is 15:06Z at k=9 and 15:20Z at k=8.
