# R129-Q — is the shared submission channel serial or concurrent?

```
VERDICT: SERIAL, and the serial constraint is a HARD PER-ACCOUNT CAP OF 1 IN FLIGHT
         (enforced by the platform, not by our driver's politeness)
LISTING SCOPE: BOTH scopes exist and we have been mixing them.
         `mlxfast submissions`            = account-scoped (advisor's 12:54Z read, `solver` column)
         `GET /api/benchmarks/{id}/submissions` = GLOBAL/multi-tenant, 1880 rows, 89 distinct
                                            `solverUsername`, ours 178 (9.5 %)
         PROVING FIELD: every row carries `solverUsername` / `solverAccountId` /
         `solverProfileUrl` (present 1880/1880). `mlxfast submissions --all` is the CLI flag
         that reproduces the global scope; we have never passed it.
DRAWS REMAINING (incl. the row now in flight): 2  (range 1-4), because a fresh row
         `c06b1b6d` was created on the account at 13:51:13Z and under a cap of 1 the next
         fire cannot be admitted until it goes terminal (residual forecast below: median
         15:21Z, p90 15:42Z, still `validating` at the 15:05:05Z poll, age 73.9 min).
LAST FIRE FOR A 17:00Z ADJUDICATION: >=80% odds up to 15:33Z; >=50% up to 15:59Z.
         CORRECTED at 15:08Z - the "15:20Z, spread 15:06Z-15:37Z" that stood here (and in my
         first four results) is a ~95% CONFIDENCE FLOOR, not the point of indifference. Do
         NOT read it as "after 15:20Z, don't bother": a flip at 15:40Z is still worth firing
         (74%) and 15:55Z carries 62%. Kaplan-Meier on global sojourns bucketed by in-flight
         depth at creation (depth>=10, n=94, median 60.6 min, p90 111.3) gives P(adjudicated
         before 17:00Z | fire time): 14:55Z 94.6% / 15:15Z 88.0% / 15:35Z 80.4% /
         15:45Z 72.8% / 15:55Z 63.0% / then a CLIFF to 34.8% at 16:05Z and 6.5% at 16:35Z.
         Underlying age-of-queue evidence unchanged: oldest resident row at 13:52Z was
         65.0 min, our last three terminal rows took 82.8 / 99.4 / 46.3 min (NOT the 22.7 min
         the account ran all morning, and NOT the 2.3 h the brief's 14:30Z window rests on).
         See research/r129q_adjudication_odds.py; W&B pnltvn22.
OPERATIONAL RULE: FIRE THE INSTANT `c06b1b6d` FLIPS. Not because the deadline is imminent -
         the slope near the flip is shallow (+10 min costs 3.9 pts) - but because of the
         16:00Z cliff, and because the draw is i.i.d. so waiting buys nothing.
RESIDUAL FORECAST for `c06b1b6d` (filed 15:06Z, BEFORE the outcome): it was admitted at
         global depth 5, so its comparable population is rows admitted at depth 4-7 (n=477).
         Conditioned on having already waited 75 min: p25 flip 15:10Z, median 15:21Z,
         p75 15:34Z, p90 15:42Z. P(my registered 14:30-15:35Z band holds) = 77.1%, so there
         is a 22.9% chance it MISSES HIGH (33.6% on all depths, 46.2% on the depth>=10
         bucket). Recorded before the flip so it cannot be re-authored afterwards.
         See research/r129q_residual_flip_forecast.py; W&B 6lpeg7oa.
VALUE OF THE REMAINING DRAW: E[P(next fire adjudicated)] = 79.6% (69.7-79.6% across
         populations), E[crown] 1.19-1.59%. P(draw effectively worthless because the slot
         frees after ~15:59Z or not at all) = 8.3-15.4%. The dominant risk is NOT firing
         late; it is the slot never freeing in time to fire at all.
WHAT WOULD FLIP THIS VERDICT: one row created on any account while another row of the same
         account was still observed non-terminal. Zero such pairs exist in 1880 rows / 1785
         consecutive same-account fire pairs / 89 accounts / 18 days.
POLLS TAKEN: 12:06:00Z, 12:22Z, 12:50Z, 12:55Z, 13:03Z, 13:10Z (global API snapshots, files
         under research/), 13:52:07.035876Z (fresh global API poll, this document),
         13:52:08.4Z (CLI `--help` text, no API call), 14:02:12Z, 14:16:07Z, 14:44:39Z
         (global API polls), then a read-only watcher every ~2 min from 14:54:49Z
         (research/r129q_flip_watch.py, exits the instant `c06b1b6d` goes terminal):
         14:54:52Z, 14:56:55Z, 14:58:58Z, 15:01:00Z, 15:03:04Z, 15:05:05Z - all
         `validating`, global in-flight 12, exactly ONE own row live at every poll.
```

**I fired nothing.** No `mlxfast submit`, no `senpai/submit-official.sh`, no `--official`, no
"test" row. The only network calls in this task are listing GETs and `--help` text. The row
`c06b1b6d` created at 13:51:13Z is **not mine** — its note reads
`# PR #736 - N=1 native affine o_proj R2 geometry`; the slot holder fired it while I was
polling. Maple (fern) remains stood down from the submission slot.

Reproduce: `research/r129q_channel_concurrency.py <out.json> <old.json>` (job
`22a653d8-8670-4d43-afc0-1d6e3e34e376`, exit 0, 1.45 s) and
`research/r129q_cap_test.py <snapshot.json>` (offline).

---

## Q1 — scope: the contradiction is real and it is mine to own

Both reads were correct; they are different endpoints.

| read | command | scope | non-terminal rows seen |
|---|---|---|---|
| my 12:06Z | `GET /api/benchmarks/1854efdf.../submissions` (`research/fern_r109f_refresh_submissions.py`) | **global**, 1865 rows, all solvers | 9, **none ours** |
| advisor 12:46/12:54Z | `mlxfast submissions` | **account**, 177 rows, `solver` = `morganmcg1` on every row | 1 (`5fae2f1`) |
| my 13:52Z | same global GET | **global**, 1880 rows, 89 solvers | 6, **one ours** (`c06b1b6d`) |

The global listing's 9 non-terminal rows at 12:06Z, with owners:

```
636cf908  ggt54        validating   created 2026-08-11T09:45:26.429Z   <- head of line, age 141 min
910f2f1f  fjrth66      validating   created 2026-08-11T10:06:19.140Z
a0962729  uww0n        validating   created 2026-08-11T10:45:23.442Z
1fb35f9a  ooo9cj       validating   created 2026-08-11T11:08:19.909Z
c0542e8b  uu0vg7       validating   created 2026-08-11T11:32:01.083Z
7a7a773f  uee9b6       validating   created 2026-08-11T11:32:38.682Z
e5e32aa5  DawgZter     validating   created 2026-08-11T11:43:45.694Z
dd8b2897  ggu77wt      validating   created 2026-08-11T11:57:02.208Z
87fb88a5  uu6f8        validating   created 2026-08-11T12:02:06.900Z
```

**`ggt54` is a `solverUsername`, not a submission id.** The advisor is right that it is not one
of our submission ids and never appears in the 177 account rows; my 12:06Z label was the
*owner* of head-of-line row `636cf908`. Age check: 12:06:00Z − 09:45:26Z = 140.6 min ✓.
`ggu77wt` is the account that owns the current crown row (commit `4ea72c3b2887`) — a
competitor, not us.

**Consequence, and it is the important one:** the ≈2.3 h sojourn in
`MAPLE_TO_SLOT_HOLDER_BRIEF.md` §4, the 14:30Z window, and my own retracted "~14:40Z last
fire" were all derived from that 141-minute **global** head-of-line age. Our **own** account's
service history is a different and much faster distribution. Planning off the global head-of-line
age over-states our sojourn by 3–6×. This is my error and it propagated into the brief.

**Fresh global poll, 13:52:07Z** (`date -u` equivalent printed by the script itself):

```
80ab0a8a  fjrth66      validating   created 12:47:05Z  age  65.0 min
70afbd47  ooo9cj       validating   created 13:12:43Z  age  39.4 min
23ad2e18  uww0n        validating   created 13:34:30Z  age  17.6 min
fe6580c6  ggu77wt      validating   created 13:43:40Z  age   8.4 min
f44d82c2  tt7fk        validating   created 13:49:08Z  age   3.0 min
c06b1b6d  morganmcg1   validating   created 13:51:13Z  age   0.9 min   <== OURS
```

### UTC anchor for the CLI's `created` column — verified with a second anchor

| id | API `createdAt` | CLI `created` | agree |
|---|---|---|---|
| `5fae2f13` | `2026-08-11T12:16:59.958Z` | `12:16` | ✓ |
| `4be372f9` | `2026-08-11T09:20:20.768Z` | `09:20` | ✓ |

The column is UTC, truncated to the minute.

---

## Q2 — has any account ever held two rows non-terminal at once? No, and the negative has power

Method: interval sweep. Each row occupies `[createdAt, updatedAt]`; `updatedAt` is the terminal
transition for terminal rows (`rejected` / `failed` / `accepted` / `promoted`) and the poll time
for rows still in flight. This is strictly better than comparing creation times to polls: it
tests every pair of rows that ever existed, not only the instants we happened to look.

`updatedAt` is validated as the terminal transition by a **registered prediction**: at 12:20Z I
predicted `5fae2f13` would go terminal at ≈13:07Z; its `updatedAt` is **13:03:15.753Z**, error
−8.8 % (`research/fern-r109f-channel-slot-ledger.md` §10.1).

```
our account, all 178 rows:                MAX CONCURRENT = 1
every one of the 89 accounts, 1880 rows:  MAX CONCURRENT = 1   (0 of 89 ever reached 2)
GLOBAL, all accounts pooled:              MAX CONCURRENT = 15  (2026-07-29T16:46:14Z)
```

So the **service** is concurrent — the graders run up to 15 rows at once — but **admission is
capped at one row per account**. Those are different things and the campaign has been conflating
them.

### The negative's power: 1785 reaction times, zero negative

For consecutive same-account fires define `r_i = (createdAt_{i+1} − createdAt_i) − sojourn_i`,
i.e. how long after row *i* went terminal row *i+1* was created. If admission were
unconstrained, an eager driver would sometimes fire *before* its previous row finished and `r_i`
would be negative.

```
consecutive fire pairs, all 89 accounts: n = 1785
NEGATIVE r_i (fired while own previous row still non-terminal):  0   (0.000 %)
r_i in [0,1) min:   158   ( 8.9 %)      <- fired within 60 s of its own row going terminal
r_i in [0,2) min:   360   (20.2 %)
r_i in [0,5) min:   696   (39.0 %)
minimum r_i observed: 0.088 min = 5.3 s
our account: n = 176, min 0.10 min, median 5.65 min, 26.7 % inside [0,2) min
```

There is a **hard floor at zero with 158 observations piled within 60 s above it**. Those 158
fires come from drivers polling at sub-minute granularity and firing the instant they are
allowed. A driver that eager, if it were *free* to fire, would land on the other side of the
boundary a large fraction of the time; even at a conservative 10 % per trial, seeing zero
negatives in 158 near-boundary trials has probability `0.9^158 ≈ 6e-8`. The negative is not
"we never happened to look" — it is a censored boundary.

### The honest weakness, stated

On **our own account alone** the negative has almost no power: 0/176 rows had a sojourn longer
than the gap to the next fire, so under *either* hypothesis we would expect zero overlaps.
The power comes entirely from pooling 89 accounts and from the reaction-time floor above.
Also, an interval sweep cannot distinguish "cap enforced by the API" from "every one of 89
independent drivers is voluntarily serial"; the 5.3-second minimum reaction is what makes the
voluntary explanation implausible.

### Throughput cross-check (the advisor's bound, tightened)

Our account's 8/11 rows, with **measured sojourns** rather than inferred ones:

```
00:00:00Z 22.2   00:39:49Z 22.7   01:07:24Z 22.4   01:31:01Z 23.2   01:54:46Z 23.0
02:23:20Z 22.1   03:05:59Z 22.9   03:30:50Z 22.6   03:55:01Z 22.9   04:20:06Z 22.6
04:44:34Z 22.4   05:09:00Z 22.4   05:33:15Z 23.0   07:01:13Z 22.7   07:26:09Z 29.6
07:57:16Z 82.8   09:20:20Z 99.4   12:16:59Z 46.3   13:51:13Z IN FLIGHT
```

Hypothesis **(a) serial and fast** is confirmed and quantified: the morning ran a 22.1–23.2 min
plateau (16 rows, spread ±0.6 min), not 2.3 h. The advisor's 23–28 min modal *gap* is
`sojourn 22.7 + reaction ~1-5 min`, so the gap-based throughput argument was right for the
right reason. Congestion then broke it at 07:57Z: 82.8, 99.4, 46.3 min. Both the morning number
and the close-day number are real; the day is non-stationary in sojourn.

---

## Q3 — documented limit: none. The cap is real but undocumented

```
$ mlxfast --help                 -> no queue/status/quota subcommand
$ mlxfast submissions --help
  Options:
    --all       show all submissions for the benchmark      <== the flag nobody passed
    -h, --help
$ mlxfast submit --help
  Options:
    --note <markdown> | --note-file <path> | --model <name> | -h
```

No per-account in-flight cap, rate limit, quota, queue-position or ETA field is documented
anywhere in the CLI surface, and no listing field carries a position or ETA (row keys are
`benchmarkId, claimedScore, createdAt, id, improved, note, officialMetrics, officialScore,
promotedSourceRef, promotionFinishedAt, promotionReason, promotionSnapshotRef, promotionStatus,
rejectionReason, solverAccountId, solverAvatarUrl, solverProfileUrl, solverUsername, status,
submissionCommitSha, updatedAt`). So the cap of 1 is an **empirical** finding (Q2), and the
only way to get a queue position remains the global listing plus arithmetic.

Finding worth saying loudly: **`--all` means the CLI can produce the global scope directly.**
Any future "how many rows are ahead of us" question should use `mlxfast submissions --all`, not
a hand-rolled API call, and should never be answered from the account-scoped default.

---

## Q4 — deadline arithmetic, age-of-queue, under the winning hypothesis

Rule 13 respected: the estimate below uses the **age of rows currently resident** (a censored
lower bound that sees the slow tail) alongside our own recent completed sojourns, not a
percentile of completed services only.

Age-of-queue evidence at the 13:52:07Z poll: resident ages `0.9, 3.0, 8.4, 17.6, 39.4, 65.0`
min. The 65.0-min row (`80ab0a8a`, created 12:47:05Z) is still unresolved, so the current
service distribution has mass beyond 65 min. Our own last three completed rows: 82.8, 99.4,
46.3 min. Pooling terminal sojourns with current ages (n=183) gives p90 25.9, p95 40.8 min, but
that pool is dominated by 177 morning-regime rows and **understates the close-day regime**; I
use the close-day numbers instead and say so.

Under SERIAL + cap 1, with `c06b1b6d` created 13:51:13Z:

| sojourn budget | channel free | last safe fire (17:00Z − budget) | further draws after `c06b1b6d` |
|---|---|---|---|
| 20.8 min (morning median) | 14:12Z | 16:39Z | 8 |
| 46.3 min (`5fae2f13`, live, 12:16Z) | 14:37Z | 16:14Z | 3 |
| 82.8 min (last-3 median) | 15:14Z | 15:37Z | **1** |
| 99.4 min (last-3 max) | 15:31Z | 15:21Z | 0 |

**Answer: 2 draws total including `c06b1b6d`; 1 if the close-day tail (≥99 min) holds, up to 4
if congestion clears back toward the morning plateau.** The window for the second fire opens
when `c06b1b6d` flips — expected 14:37Z–15:30Z — **not** at the brief's fixed 14:30Z, and the
last safe fire is **15:20Z (spread 15:06Z–15:37Z)**, not 14:30Z/14:40Z.

15:06Z is the conservative end and comes from the independent in-flight-conditioned rule in
`research/fern-r109f-channel-slot-ledger.md` §8 (`last fire = 17:00Z − max(p90_k,
1.415×median_k)`, k = rows in flight at creation). Both routes now agree inside 30 minutes.

### What this does to the brief

* §4's "one more adjudicated draw, next fire cannot start until ≈14:30Z" — **half right**:
  serial is confirmed, so no doubling from concurrency; but the 2.3 h sojourn behind the 14:30Z
  clock is a **global** head-of-line age, not our account's service time, and the real gate is
  "when `c06b1b6d` flips", which is earlier.
* My own "~14:40Z last fire" (adopted fleet-wide in the #686 disposition §5) is **retracted**;
  it inherited the same global-scope error. Use 15:20Z, floor 15:06Z.
* The advisor's ≈25 min hypothesis (a) is **confirmed as the morning regime** (22.7 min) and
  **superseded for now** (46–99 min under close-day congestion).

## Registered prediction (so this document can be scored after the fact)

`c06b1b6d` (created 13:51:13Z, 5 rows in flight ahead of it in the global listing at creation)
goes terminal between **14:30Z and 15:35Z**, central estimate **≈15:10Z**, and no row of ours
will be created before it does. If a second row of ours appears while `c06b1b6d` is still
`validating`, the SERIAL verdict is refuted and I am wrong.

## Live corroboration at a second poll time — 14:02:12Z (read-only)

Second independent global poll, 1882 rows (2 new since 13:52:07Z). Three things the second poll
adds that the first could not give:

1. **`c06b1b6d` has NOT flipped.** Still `validating` at 14:02:12Z, age **11.0 min**, and **no
   second row of ours exists** — the per-account cap of 1 is holding in real time, not just in the
   18-day reconstruction. Cap recomputed on the larger set: still **1** for our account (now 178
   rows) and still **0 of 89 accounts** ever at >= 2. Prediction (terminal 14:30–15:35Z) is alive
   and unfalsified; at 14:02Z it is not yet informative either way.
2. **Two rows admitted in the SAME second by different accounts:** `e5a4b510` (`ggt54`) and
   `988272ee` (`uu0vg7`), both created **14:00:07Z**. Direct, live proof that admission is *not*
   globally serialised — the cap is per account. This is the cleanest single observation in the
   whole document, and it needed only two polls.
3. **Live global concurrency = 7** (`70afbd47 ooo9cj` 49.5 min, `23ad2e18 uww0n` 27.7,
   `fe6580c6 ggu77wt` 18.5, `f44d82c2 tt7fk` 13.1, `c06b1b6d morganmcg1` 11.0, `e5a4b510 ggt54`
   2.1, `988272ee uu0vg7` 2.1). Seven in flight at once, consistent with the historical pooled
   maximum of 15. **The service is concurrent; only our admission is capped.**

One new sojourn data point falls out for free: `80ab0a8a` (`fjrth66`, created 12:47:05Z) was
non-terminal at 13:52:07Z and terminal at 14:02:12Z, so its service time was in **[65.0, 75.1] min**
— another close-day congested figure, bracketing the 46–99 min regime our own last two rows show and
confirming the congestion is systemic rather than something about our account.

Nothing in the second poll changes the verdict or the numbers: **SERIAL, per-account cap 1,
2 draws remaining (1–4), last safe fire 15:20Z (spread 15:06Z–15:37Z)**. The gate remains "when
`c06b1b6d` flips", and as of 14:02:12Z it has not.

## Third poll — 14:16:07Z (read-only): the fast regime is now formally dead

1885 rows. **`c06b1b6d` is still `validating`, age 24.9 min.** That single number settles the
regime question the advisor's hypothesis (a) raised: 24.9 min is **past the top of the entire
morning plateau** (16 rows, 22.1–23.2 min), so the ~25 min service time is *excluded* for this row,
not merely unlikely. The live budget is the congested one (46–99 min), which is exactly what the
draws-remaining table was built on. **No second row of ours exists** at 24.9 min of waiting — the
cap of 1 has now held across three independent polls (13:52:07Z, 14:02:12Z, 14:16:07Z); cap
recomputed on 1885 rows is still 1 for our account and still **0 of 89 accounts** at >= 2.

**Global concurrency is climbing into the close:** 6 rows in flight at 13:52:07Z, 7 at 14:02:12Z,
**9 at 14:16:07Z** (`23ad2e18 uww0n` 41.6 min, `fe6580c6 ggu77wt` 32.5, `f44d82c2 tt7fk` 27.0,
`c06b1b6d morganmcg1` 24.9, `e5a4b510 ggt54` 16.0, `988272ee uu0vg7` 16.0,
`972e32c5 a-github-name` 6.1, `cf9802d2 uee9b6` 3.7, `7313e81f uu6f8` 3.7). Two more same-second
admissions from different accounts (`cf9802d2` 14:12:25Z / `7313e81f` 14:12:26Z, one second apart).
Rising load is the mechanism behind the 22.7 -> 46-99 min drift, and it argues for taking the
**earlier** end of the last-safe-fire spread.

Two fresh sojourns for other accounts, bracketed by consecutive polls: `80ab0a8a` (`fjrth66`,
created 12:47:05Z) terminal in **[65.0, 75.1] min**; `70afbd47` (`ooo9cj`, created 13:12:43Z)
terminal in **[49.5, 63.4] min**. Both sit inside the 46–99 min congested band our own last two rows
show, so the congestion is systemic, not an artefact of our account.

Verdict and numbers unchanged: **SERIAL, per-account cap 1, 2 draws remaining (1–4), last safe fire
15:20Z** — and after this poll I would advise the slot holder to plan on the **15:06Z floor** rather
than the 15:37Z ceiling. Prediction still alive: terminal 14:30–15:35Z, centre ~15:10Z.

## Fourth poll — 14:44:39Z (read-only): the queue is filling faster than it drains

1891 rows. **`c06b1b6d` is still `validating`, age 53.4 min** — inside the 46–99 min congested band,
still short of the prediction's 15:35Z ceiling, and now firmly in the region where the morning
regime is irrelevant. Still no second row of ours (cap of 1 has held across **four** polls).

**Global in-flight count: 6 (13:52:07Z) -> 7 (14:02:12Z) -> 9 (14:16:07Z) -> 12 (14:44:39Z).**
That is +6 rows in 52 min, ~0.12 rows/min of net accumulation, i.e. arrivals are outrunning
completions as the field rushes the close. Live set at 14:44:39Z: `f44d82c2 tt7fk` 55.5 min,
`c06b1b6d morganmcg1` 53.4, `988272ee uu0vg7` 44.5, `972e32c5 a-github-name` 34.7,
`cf9802d2 uee9b6` 32.2, `7313e81f uu6f8` 32.2, `61c82b30 ooo9cj` 21.4, `f94e59a0 fjrth66` 18.5,
`632a66ba DawgZter` 10.7, `f8ad8157 uww0n` 7.3, `44c71f96 ggu77wt` 7.3, `9ccebec5 ggt54` 7.3.
Two more same-second cross-account admissions (`44c71f96` and `9ccebec5`, both 14:37:21Z) — the
per-account/global distinction is now observed at four separate instants.

**What this changes operationally.** Sojourn is a function of queue depth, and depth is growing, so
every estimate built on today's *earlier* sojourns is an optimistic lower bound for a row fired now.
The decision rule therefore tightens from "last safe fire 15:20Z" to:

> **Fire the instant `c06b1b6d` flips, without deliberation, and treat that fire as possibly the
> last one.** Waiting has no upside — the draw is i.i.d. (autocorr lags 1–5 in [-0.003, +0.056],
> previous-5-median forecast r2 = 0.000), so a later shot is not a better shot, only a riskier one.

Arithmetic behind that: if `c06b1b6d` clears at 60–70 min (14:51Z–15:01Z) and a row fired then takes
70–90 min at depth 12+, it lands 16:01Z–16:31Z — inside the 17:00Z close, but a *third* fire would
not be. So the honest count stays **2 draws total including `c06b1b6d`**, i.e. **~2.9 %** chance of
taking the crown (2 x 1.48 %/draw), and the second of those two must be launched on the flip rather
than at a clock time.

Verdict unchanged and now quadruply witnessed: **SERIAL, per-account cap 1, concurrent service.**
