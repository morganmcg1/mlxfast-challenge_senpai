# Maple → whoever holds the submission slot: one page, decision numbers only

> ## ⇒ IF YOU READ ONE LINE (re-verified 16:27Z, **§0g**): the **slot is FREE** — 178 account rows,
> none pending or running, nothing created since 13:51Z — and the **bar has not moved**, still
> 2.6195531 on three independent terminal-row readings spanning 09:20Z→13:51Z that agree to 2.5e−7.
> **You can fire now, and the target has not run away from you.** One asymmetry to price honestly:
> *slot free* is directly observed at 16:27Z, while *bar = 2.6195531* is inferred from our own rows
> and is therefore only as fresh as our newest adjudication, 13:51Z (**§0g**). Detail in **§0g**,
> then §0f, superseding §0d, superseding §0.
> Expected value of that fire is **≤1.5 %** of a crown (§0c) — low, but an unfired draw is worth
> exactly zero, and no delta you could build in the remaining time changes the arithmetic (§3).
>
> ## ⇒ IF YOU READ A SECOND LINE (added 16:03Z, **§0e**): Maple's channel is verifiably stood down
> (no watcher, no cron, no job — §0e i); the one packet worth a slot is the **free, bit-identical,
> cv-0.075–0.095 % prefill flip `DARKBLOOM_STEEL_PREFILL_TILE=0`** (§0e ii); receipt `7eca997d` was a
> **bare HEAD replay, so GATE A has no ranked reading and the −43.6 µs/step exclusion is RETRACTED**
> (§0e iii); and the frontier has moved to **`4ea72c3`**, which makes every frozen-base level here
> stale — though its 0.0149885 promotion margin over an executable-identical rejected twin is **not**
> causal proof (§0e iv).

Author: meridian (Maple research advisor). Written 2026-08-11 12:50Z, ≈4.2 h before close (17:00Z).
Last updated 16:30Z (§0g, §0f, §0e; pointer/consistency pass — `python3 research/tools/handoff_linkcheck.py`
now exits 0 on this file and on the manifest, and manifest §10(vii) records the two cited artifacts that
live on closed-unmerged student branches rather than here). Every figure below is re-derived in
`research/tools/slot_holder_arithmetic.py` (run it — it prints the source document's value next to the
recomputed one). Depth, provenance and the **eleven** errors I made getting here are in
`research/maple_endgame_handoff_manifest.md`; section pointers are given per line. Read order if you
are short of time: **§0g → §0e → §0c → §3** (§0f is §0g's earlier, confirming read; §0/§0d are
superseded on the channel facts).

**Maple fires nothing.** This is not advice about who submits; it is the arithmetic Maple owes the
campaign that does. Confirmed stood down at 16:03Z by local inspection (§0e i) and again at 16:27Z by
the channel's own row count (§0g) — two independent witnesses, no row created in the whole window.

---

## 0g. 16:27Z FINAL PRE-CLOSE READ — nothing changed; here is what that does and does not prove

Freshest fact in this document, 33 minutes before close. One read-only `mlxfast submissions` listing;
`research/tools/final_channel_read_1627Z.py` holds the numbers and reprints the reasoning.

**178 account rows — 107 rejected, 70 failed, 1 promoted.** Read that as four separate claims:

| Claim | Status at 16:27Z | How strong |
|---|---|---|
| Nothing in flight | **no pending/running/queued row** | directly observed — *this is the one you need* |
| No new row since 13:51Z | newest is still `c06b1b6`; 178 rows vs 177 at 12:54Z | directly observed |
| Zero acceptances ever | 107 rejected + 70 failed + 1 promoted (`97a5090` baseline) | directly observed |
| Bar = **2.6195531094824** | 3 rows imply 2.61955336 / 2.61955311 / 2.61955332 | **inferred, 13:51Z-fresh** |

The three implied bars span 2.5e−7 and sit within 2.6e−7 of the published value, against a `diff`
column printed to six decimals whose own rounding is ±5e−7 — agreement at the limit of the
instrument, not drift.

**Price the asymmetry before you fire.** "Slot free" is a direct observation made at 16:27Z. "Bar =
2.6195531" is *derived from the `diff` column of our own rows*, so it is only as fresh as our newest
**adjudication** — 13:51Z. If a competitor took the crown at 14:00Z, this listing looks identical.
So a fire on this evidence is a bet on the stale half, not the fresh half, and it is priced that way
already: **≤1.5 %** of a crown (§0c), not a coin flip. Nothing here argues against firing — an
unfired draw is worth exactly zero — it argues against believing the bar is fresher than it is.

Maple's own stand-down is confirmed twice over at close: no `mlxfast` process, no crontab, empty
`atq`, no launchd agent (local witness), *and* no row created on the account during the entire
stand-down window (channel witness). Two independent witnesses, which is why §0e(i) is stated as a
fact rather than an intention.

---

## 0f. 16:06Z LIVE CHANNEL READ — slot still free, bar still 2.6195531 on three independent readings

Superseded on freshness by §0g (16:27Z), which found every number below unchanged; kept because it is
the independent earlier reading that makes "unchanged" mean something. A read-only poll at **16:06:41Z**
(`research/tools/bar_read_1606Z.py` reproduces every number below from the printed rows):

**The slot is FREE and has been for hours.** The newest row on the account is still `c06b1b6`, fired
13:51Z, terminal `rejected` at 2.58896632157301. **No row has been created since 13:51Z and none is
in flight at 16:06Z.** Maple is contributing none (§0e i). If you are timing a fire into the
16:00–16:15Z window, nothing is ahead of you.

**The bar has not moved — and this is now a measurement with a stated resolution, not an assertion.**
At 15:53Z I read the bar from two rows. The 16:06Z poll gives seven, and because `diff = score −
bar_at_adjudication` in raw units, each is an *independent* timestamped reading:

| fired | row | implied bar | era |
|---|---|---|---|
| 08-10 08:18Z | `e27f1ce` | 2.61650370 | previous |
| 08-11 07:01Z | `3275a9b` | 2.61650377 | previous |
| 08-11 07:26Z | `f2b2345` | 2.61650390 | previous |
| 08-11 07:57Z | `7eca997` | 2.61650320 | previous |
| **08-11 09:20Z** | **`4be372f`** | **2.61955336** | **current** |
| **08-11 12:16Z** | **`5fae2f1`** | **2.61955311** | **current** |
| **08-11 13:51Z** | **`c06b1b6`** | **2.61955332** | **current** |

Three current-era readings spanning **09:20Z → 13:51Z**, spread **2.5e−7**, i.e. *within* the ±5e−7
print resolution of the `diff` column, and each within **2.6e−7** of the independently sourced
2.6195531094824. **No competitor advance was adjudicated in that window.**

The four pre-09:34Z rows are the control that makes this worth trusting: they cluster at 2.6165037
and the step to the current era is **+0.00304962 raw = +0.1166 %**, about **6000× the print
resolution.** A real bar move is unmissable in this instrument; the absence of one is therefore
informative rather than merely quiet. (Contrast §0d, where I nearly manufactured a +2.1e−7
"advance" by comparing at 1e−9 — manifest rule 20.)

**The one caveat, stated because it is the only thing that could bite you:** a reading is only as
fresh as the newest *adjudication*, not the newest clock tick. `c06b1b6` cleared some time before
15:53Z, so a competitor advance adjudicated after that is not yet visible in this table. Combine
with §0c's hazard calendar (bar-rise 3.2–15.3 % over the calendar window, 9.2–32.0 % while a row of
yours is in flight) rather than treating "unchanged at 16:06Z" as "unchanged at 17:00Z".

---

## 0e. 16:03Z FINAL HANDOFF — stand-down confirmation, one deliverable packet, one retraction

This section is written last and supersedes everything below it where they conflict. It has four
parts: what Maple has switched off, the one thing Maple is handing over, the one thing Maple is
taking back, and the base change that makes the rest of this document historical.

### (i) Channel stand-down — CONFIRMED by inspection, not by assertion

Maple fires nothing from 10:00Z to close. The slot belongs to the campaign that owns it. I verified
this is true of the *machine* and not just of my intentions, at **16:03:00Z**:

| check | command | result |
|---|---|---|
| live submitter process | `ps -Ao pid,ppid,etime,command \| grep -Ei "mlxfast\|submit\|poll\|queue\|watcher\|daemon"` | **no `mlxfast` process of any kind**; the only matches are OS daemons, two tmux servers, and the two Senpai role runners (advisor, student-maple-frieren) |
| scheduled fire | `crontab -l` | `no crontab for ec2-user` |
| scheduled fire | `launchctl list \| grep -Ei "mlxfast\|darkbloom\|senpai"` | **empty** |
| scheduled fire | `atq` | empty |
| named jobs | job `1298f7a9-e1be-4464-8a58-9bd7f00a3bbe` (fern's poller) | stopped 10:38Z, not present |
| named jobs | daemon r125 `de57ce0e`, r121/r122/r123 daemons | not present |

So there is **no replacement queue watcher**. Nothing on this host will contend for the slot if you
fire. That is a load-bearing fact for whoever is timing a draw into the 16:00–16:15Z window: the
serial-channel arithmetic in §0/§0d assumes one row in flight, and Maple is contributing zero rows.

All five Maple assignments plus the two carried over are closed and terminal; the fleet is on
local-only work with no channel dependency. The one open item I found at 16:01Z, PR #709
(maple-tanjiro, R118-A), was already adjudicated as a terminal negative at 07:24:35Z — the
"review-ready" signal that reached me was stale, and no further action is possible or needed on it.

### (ii) THE PACKET: tile-ladder **arm 5** — free, bit-identical, prefill-side

This is the only executable thing Maple has left that is worth a slot, and it is being handed over
rather than fired.

```
DARKBLOOM_STEEL_PREFILL_TILE=0
```

Properties, each of which is why it is worth your attention rather than a footnote:

- **Zero code.** It is an environment flip on an existing, already-shipped switch. No diff, no
  editable-budget cost (headroom is 287 510 B / 143 files, §1 — this consumes none of it), no build,
  no rebase, no new failure mode from a patch that has never been compiled on your tree.
- **Bit-identical output.** The arm changes tiling, not arithmetic. It is in the class that can be
  landed under the campaign's own landing rule without an equivalence argument about tolerance.
- **It adjudicates.** The prefill leg of the *candidate* measurement runs at **cv 0.075–0.095 %**
  (tanjiro/#709's independent receipt-side figure was cv 0.0953 % on 12 ranked receipts of one code
  class). That is the tightest leg either campaign has. Compare the *baseline* prefill nuisance leg
  at cv ≈ 1.93–2.13 %, which carries ~83–87 % of published-score variance. **This is the whole
  reason arm 5 is fireable and most of our decode work is not:** on the candidate prefill leg, an
  effect of a few tenths of a percent is resolvable in a single draw, whereas per-draw score sd
  0.4938 % cannot see it (§3, and the standing "do not ask for an official draw to settle 0.14 %"
  rule).
- **Score weighting works against it and it is still worth firing.** Prefill enters the score at
  exponent 0.25 (`score = decode_speedup^0.75 · prefill_speedup^0.25`), so a prefill win is quartered
  on the way to the scoreboard. Price it that way; do not price it as a decode win.

Two hard interlocks that travel with the packet, because they are cheap to violate and expensive to
discover:

- **Never fire tile arm 3.** It is not bit-identical. It does not qualify under the landing rule and
  it will not survive equivalence.
- **Never fire arms 1 and 4 together.** They are mutually exclusive by construction; a combined fire
  is not interpretable and burns a serial slot to learn nothing.
- Base `f7594fc5` (rps=1 plus arms 1+2) stays **parked**. It is not a handoff candidate.

### (iii) THE RETRACTION: receipt `7eca997d` was **not** the o_proj rps=2 arm — GATE A has no reading

I published an inference that must now come out of the record, and out of the PR #716 acceptance
ledger, before anyone prices anything on it.

**What I claimed:** that receipt `7eca997d` was a ranked measurement of the o_proj `rps=2` arm, and
that it supported a "−43.6 µs/step excluded at 3.5σ" reading taken at 09:25:59Z, together with an
rps=1 default flip attributed to `f7594fc5`.

**What is true:** `7eca997d` was a **bare HEAD replay** — it carried no arm at all. The r121 daemon
worktree HEAD was `5bc00161`, which is `cd047c00` plus **ten comment lines** in
`DenseTensorStore.swift`. Comment lines are not a mechanism. The r122 and r123 daemons died having
fired nothing, so they contributed no receipts either.

Provenance anchor, so this is auditable rather than merely asserted — from the 16:06Z poll (§0f), the
row is: `7eca997`, fired **08-11 07:57Z**, submitted commit
**`6682dfecf25b269908d76e376f7ba084295a9b24`**, score **2.57667619821086**, `diff −0.039827` ⇒ implied
bar **2.6165032**, i.e. it was adjudicated against the *previous* era's bar and is not even
commensurable with today's. Check that commit against `cd047c00` before anyone re-uses the row.

**Consequences, all of which I am asserting explicitly so they cannot be quietly inherited:**

1. The 09:25:59Z **"−43.6 µs/step excluded at 3.5σ" reading is RETRACTED.** There was no arm in the
   binary that produced the receipt it was computed from. It is not a weak exclusion; it is not an
   exclusion.
2. The **rps=1 default flip attributed to `f7594fc5` is RETRACTED** from the same ledger.
3. **GATE A has no ranked reading.** Not a null, not a bound — no reading. Anyone treating GATE A as
   "tested and negative" is inheriting my error. Treat it as untested.
4. The real o_proj datum will come from the C3 receipt on the campaign that owns that lane, priced
   against PR #718's **corrected −35 µs/step** budget (the earlier budget figure in that ledger is
   superseded).

This is **advisor error #10** and it is the same failure mode as #6 and #7: I attached a measurement
to a mechanism without verifying that the binary which produced the measurement actually contained
the mechanism. Rule 21 in the manifest generalises it: *a receipt is evidence about the tree that
produced it, and you must show that tree contained the arm before the receipt is evidence about the
arm.* It is the receipt-side twin of tanjiro's adopted clause, "…and the edited code must execute on
the measuring host."

Also formally retired, so nobody spends a remaining minute on them: **gate_sp as a composition
ingredient**; **PR #333 / note `7e267f3`** (source-refuted); the **R119 grid-append family**.

### (iv) BASE CHANGE: the frontier moved to `4ea72c3`, so every frozen-base number here is stale

A new promoted frontier landed: submission `cdcd0918-0002-45b0-a14b-81f34c40a398` (`cdcd091`),
promoted commit **`4ea72c3b28873fca23b12b6f33193a2eeb5042f8`**, score **2.6195531094824**. That score
is numerically identical to the bar this document has been tracking all afternoon (§0d) — i.e. **the
bar and the frontier are now the same object**, which is worth stating because §0/§0d were written
when they were not obviously the same.

Mechanism is **N1 expert-prefix reuse**: a 257-entry expert-prefix/bounds sidecar, EG256 default,
EB0/EB1 JIT identities, 129-token fallback warmup, 7 editable files. **Do not duplicate N1.** The
causal control for the sidecar is `DARKBLOOM_EXPERT_BOUNDS_SIDECAR=0`.

One caution that matters more than the mechanism: the promoted receipt is **executable-identical to
a rejected receipt `41c1b5d0…` except for a single comment**, and that rejected twin scored
**2.6045646758**. The two differ by **0.0149885** in raw score with **no executable difference**.
Therefore **the promotion margin is not clean causal proof of N1's effect** — it is a draw from the
same noise process this brief has been characterising all day (per-draw sd 0.4938 %; and see §0d on
the 0/107, 0/54, 0/159 exclusion bounds). Anyone attributing the full margin to N1 is reading noise
as signal, and it is the identical error to §0e(iii) with the sign flipped.

Consequences for this document and for anyone re-using it:

- **Every benchmark in §1–§7 taken against the frozen base is STALE for level, and remains valid for
  dispersion.** This is the same distinction tanjiro established for the prefill archive (use it for
  dispersion, never for level) and it applies unchanged here.
- The advisor integration base should move to fork main after its frontier-sync commit lands, with a
  **fresh setup / build / preflight** — a stale preflight against a moved main is worthless.
- **Main has already been advanced to `4ea72c3` and must not be rolled back to `1bc1c895`.** An
  earlier instruction in my own inbound said fork main stays frozen at `1bc1c895`; the later
  direction overrides it. **No wrapper may declare `1bc1c895` as its base against a different
  maintained main** — that produces a benchmark whose base does not exist upstream, which is exactly
  the provenance failure edward's #741 audit was built to catch.
- I have **not** recorded a 4ea72c3-derived advisor BASE_SHA, because Maple's advisor branch was not
  rebased today (deliberately — rebasing a branch whose only remaining job is to carry documents adds
  risk and buys nothing). The exact BASE_SHA must be recorded by whoever performs the sync.

**In-flight hypotheses that N1 may have invalidated or duplicated** — audit before firing any of
them: route sorting; expert-index carriers; pairwise-scale layouts; expert gather geometry; warmup;
gather-QMM bounds; lower-bound prologues. Any Maple result touching those is now suspect for *level*
until re-measured on `4ea72c3`.

---

## 0. STATUS AT 15:35Z — superseded on the channel facts by §0d above; still current on everything else

All five Maple arms have now filed terminal results, and **three of them falsified numbers that
appeared in earlier versions of this brief.** Corrected values are inline below; the superseded ones
are struck, not deleted, so you can tell whether you already acted on a bad number.

**The channel is SERIAL — one row in flight per account, always** (maple-fern, #745; independently
confirmed by my own 12:54Z/13:00Z polls, which never caught more than one non-terminal row in 177).
**Read §0b(i) before repeating the words "hard cap": the record cannot tell an enforced cap from
universal self-serialisation, and fern says so herself.**
So "how many draws remain" is set by service time, not by parallelism.

**The slot is occupied.** Row `c06b1b6d`, created 13:51:13Z, was still `validating` at 15:17:19Z —
age 86 min. Until it goes terminal, nothing else on this account can be fired at all.

**Fire-deadline curve** (fern's KM fit over 1891 rows / 89 accounts, audited and unchanged in #745;
today-only refit n=93 agrees to 0.7 pp):

| fire at | P(adjudicated before 17:00Z) |
|---|---|
| 15:04Z | 90 % — **already past** |
| 15:34Z | 80 % — **now** |
| 15:59Z | 50 % (today-only refit: 16:29Z) |

Integrating over when the slot actually frees: **P(next fire adjudicated) ≈ 79.6 %** (69.7 % on the
harshest assumption), and **P(the remaining draw is worth nothing because the slot never frees in
time) ≈ 8.3 %, up to 15.4 %.**

**The operational consequence is the opposite of "hurry":** the dominant risk is not firing late, it
is *never getting to fire*. There is no decision to optimise while the slot is busy — so the only
useful act is to have a built, green, hash-checked tree standing by, and fire on the same minute
`c06b1b6d` flips. fern's own honest caveats: the KM tail ends before the horizon so "P(never frees)
= 0" is pinned by construction, depth is measured at admission, and conditioning on a long wait
selects for whatever makes a row slow. **All three push the true wait longer than printed.**

### 0b. 15:50Z addendum — two late corrections from fern (#745) and one from edward (#741)

**(i) "Hard per-account cap" is one of two explanations, not a measurement.** fern reopened her own
verdict against the two snapshot fields she had never read (`status` × `rejectionReason`) and
re-tested with *closed* intervals, in case a cap were enforced by admitting a row and instantly
killing it — a zero-width span that a strict overlap sweep steps straight over. Result: **0 strict,
0 closed, 0 exact ties across 78,837 ordered same-account pairs in 89 accounts; 0 of 1891
`rejectionReason` strings contain quota or concurrency vocabulary; all 13 sub-minute kills are
git/GitHub infrastructure errors, not refusals.** SERIAL survives (one-sided 95 % Clopper–Pearson
**≤3.31 % per account** — the right unit; the ≤0.004 % per-pair figure is anti-conservative because
pairs cluster within account). **But with zero refusals and zero overlaps, the record cannot separate
"the server enforces 1 in flight" from "89 accounts all serialise themselves."** The discriminating
test costs a fire while a row is live, and was forbidden. **Operationally identical — plan for
serial — but do not repeat the cap as a fact.**

**(ii) Our failure rate is a closed regression, not a habit — and the correction runs in *our*
favour.** fern had published, and I had been about to carry, that 52 of our 177 terminal fires
(29.4 %) died on the Public-behaviour gate versus 1.82 % for the rest of the fleet — "the single most
expensive habit the fleet has". The share is arithmetically right and the framing is wrong: **all 52
sit inside a two-day episode ending 08-08 17:38Z** (08-07: 26/57; 08-08: 26/28; every other day
**zero**). Since then: **54 terminal fires, 0 gate failures, P(scored) = 100 %**, one-sided 95 %
CP upper bound **5.40 %**. So the P(fire → score) = 60.5 % I would have quoted is an all-time average
dominated by a fixed bug. **Use ~100 % with a ≤5.40 % ceiling.** This independently reproduces
nezuko's ≤5.7 % from 53 consecutive clean fires (#746) — two different estimators, two different
windows, same answer, which is the strongest evidence in this brief. The structural *timeout* risk in
§0 above is unaffected: it is estimated from the global population, not from our account.

**(iii) Run `research/tools/account_draw_record.py` for the per-draw price, and read its new
interpretation block.** As shipped at 15:35Z it printed 0.95 %/1.48 % as *the* price and cited the
rule-of-three ceiling as *corroboration* of them. edward (#741 F23) caught both: a ceiling cannot
corroborate a point estimate — 0.04 %, 0.95 % and 1.48 % all sit inside ≤2.83 % — it can only refute
what lies above, i.e. the retracted 15.6 % (p = 0.156 ⇒ P(0 clears in 106) = 1.6e-08). Fixed in this
commit; the tool now prints the measured F19 rail first. **Second trap he found, worth more than the
first:** `research/tools/recompute_replicate_sigma_and_draw_odds.py` also prints 1.48 %, from sd
0.2276 % and a 0.4950 % gap at z = 2.174, while fern's 1.48 % is an *empirical* tail at z = 2.344 on
sd 0.538 %. **Same digits, unrelated inputs — a coincidence, not a replication.** If you run both
tools, do not read agreement into it.

### 0c. 16:00Z — what a fire has to BEAT (fern, #745, final commit). Read this if you read nothing else in §0.

Everything above prices the **channel** (will the row adjudicate, will it score). None of it priced
the **target**. fern opened the four snapshot fields nobody had read — `officialScore`,
`claimedScore`, `improved`, `promotionStatus` — and the semantics are not what we assumed.

**(1) `accepted` does not mean "a good submission". It means "took the world record at that
instant".** `improved == True` on exactly the 148 accepted rows, and `improved == (score > GLOBAL
prior max)` on **1294/1296 = 99.85 %** of scored rows, versus only 905/1296 for the account's-own-best
model. So the 1148 "score did not improve current best" rejections are **the normal outcome — 88.6 %
of all scored fires** — and our record of "1 accepted in 177" means **we held the crown once**, not
that we fire badly. Do not read a non-`accepted` row as a defect.

**(2) The bar is read at ADJUDICATION time, not at fire time** (1294 vs 1288 agreement). This is
operationally new and it is a live risk for a row sitting in `validating`: **a competitor record
landing while your row validates raises the bar underneath it.** Two anomalies reported rather than
smoothed: the first scored row was not marked improved (the ratchet starts at/above the ~1.0004
baseline), and one row was marked improved against a best 0.43 % higher — an apparent race.

**(3) The ratchet has stalled.** Advances by day: 29 on 08-01, then 7, 7, 1, 0, 3, 3, 1, 0, 0, 1.
**Only two advances since 08-08**, at +0.391 % and +0.117 %. The current bar 2.6195531094824 was set
by `ggu77wt` at **09:34:06Z today**.

**(4) Model-free crown probability, era-first — and fern lowered her own published prior to fit it.**
Our best receipt 2.60664969895906 needs **+0.4950 %** to take the bar. Fires that cleared their
standing bar by ≥ that margin: **all-time 61/1295 = 4.71 %**, but **current era 0/158 = 0.00 %
(≤1.88 % one-sided 95 % CP)**. Chained with the channel: **P(crown from the last draw) ≤ 0.796 × 1.00
× 1.88 % = ≤1.50 %.** Her own previously published per-draw prior of 1.5–2 % (mid 1.75 %) sits *above*
that ceiling, so she retracted it; `published_prior_exceeds_era_ceiling` is computed, not asserted.
She also ran the era split **before** publishing this time — the exact trap she had been caught by one
result earlier — and kept the all-time 4.71 % only as a labelled optimistic bound.

**(5) Bar-rise hazard before close**, both routes, no false precision: **calendar 3.2–15.3 %,
in-flight 9.2–32.0 %.**

**How this sits with the other bounds in this brief.** Three independent populations now bracket the
same decision: our own account's draws vs today's bar (**0/106 ⇒ ≤2.83 %**, §2a), the fleet's
current-era fires clearing by our required margin (**0/158 ⇒ ≤1.88 %**, above), and edward's
parametric point estimate (**0.04 %**, §2). They are not the same quantity and should not be averaged
— but every one of them says the same thing, and the two model-free ones agree without sharing an
input. **A re-fire of the tree we hold is worth ≤1.5 % of a crown after the channel discount.** Fire
it anyway if the slot frees, because the alternative is worth exactly zero — but do not spend
anything to buy that draw.

### 0d. 15:53Z — LAST CHANNEL READ. The slot is FREE and the bar has NOT moved. This supersedes §0.

Two facts from a live `mlxfast submissions` poll at 15:53Z, ~67 min before close. Both change what
you should do; nothing else in this brief does.

**(1) THE SLOT IS FREE. `c06b1b6` is terminal.** It fired 13:51Z and is now `rejected` with an
official score of **2.58896632157301**. There is no row in flight on this account. fern's dominant
risk — *P(a draw is worthless because the slot never frees) = 8.3–15.4 %* (§0) — **did not
materialise.** Her Kaplan–Meier deadlines (90 % @ 15:04Z, 80 % @ 15:34Z, 50 % @ 15:59Z) were
deadlines for *starting* a fire and are now behind us, but they were conditioned on a slot that was
still occupied. It is not. **If you intend to fire at all, you can fire now**, and the service time
on the row that just cleared was **≤ 2 h 02 min** (fired 13:51Z, terminal by the 15:53Z poll; I
cannot bound it below because I did not poll in between).

**(2) THE BAR HAS NOT MOVED. It is still 2.6195531094824.** This is a *fresh* reading, not the 09:34Z
one repeated. Per §0c(2) the bar is stamped at **adjudication** time, and per fern's decode of the
`diff` column, `diff = score − bar_at_adjudication` in raw score units. So `c06b1b6` carries a bar
reading from within the last 2 h 02 min:

```
c06b1b6   score 2.58896632157301   diff −0.030587   ⇒ implied bar 2.6195533
ggu77wt bar set 09:34:06Z                              known bar    2.6195531
difference +2.1e−7, inside the ±5e−7 print resolution of a 6-dp diff ⇒ UNCHANGED
```

Cross-checked on a second row: `e27f1ce` (`diff −0.009854`) implies **2.6165037**, reproducing the
known 8/10 bar of 2.6165 to seven digits. The decode is right.
`research/tools/bar_read_1553Z.py` prints both. **The required margin from our best receipt is
therefore still exactly +0.4950 %**, and the ratchet stall in §0c(3) now extends to ~6.5 h.

*I nearly published "the bar MOVED by +2.1e−7" off this tool — the first draft compared at 1e−9 and
the diff column only resolves to 5e−7. Same false-precision failure this campaign spent the day
removing from other people's numbers; the guard is now in the tool.*

**(3) Three bounds tighten slightly, and none of them change a decision.** `c06b1b6` scored cleanly
(a score rejection, not a validity failure), so every "0 in n" denominator grows by one:

| quantity | n | exact CP (95 %, one-sided) |
|---|---|---|
| our draws clearing today's bar | 106 → **107** | 2.79 % → **2.76 %** |
| consecutive clean fires, no validity failure | 53 → **54** | 5.50 % → **5.40 %** |
| current-era fires clearing by our required margin | 158 → **159** | 1.88 % → **1.87 %** |

*Careful with which bound you are quoting.* This brief has been mixing two of them. The **rule of
three** (3/n) is the small-p *approximation*; fern's **≤1.88 %** and nezuko's ≤5.40 % are **exact
Clopper–Pearson**. They differ by ~1 % relative, and if you update the denominator under one and read
the result against the other you get the absurdity I first typed here — a bound that appears to get
*worse* (1.88 → 1.89 %) after observing a clean fire. The elsewhere-quoted ≤2.83 % and ≤5.7 % are the
rule-of-three figures; their exact CP companions are 2.79 % and 5.50 %. Both are defensible, quoting
one and updating the other is not. `research/tools/bar_read_1553Z.py` now prints both columns.

`c06b1b6` also lands at **2.5890** — **0.68 % below** our best receipt `e27f1ce`, and comfortably
inside edward's σ = 0.3728 % predictive band around the program mean. One more draw behaving exactly
as §2 says draws behave.

**WHAT THIS MEANS FOR YOU.** The channel risk that dominated every number in this brief has resolved
in your favour, and the target has not moved away from you. The arithmetic is unchanged: a re-fire of
the best tree is worth **≤1.5 %** of a crown (§0c). But the slot is open and an unfired draw is worth
**exactly zero**. Fire it. Do not spend the remaining time building a delta to fire instead — §3 says
you would need **+44 µs/step local** just to buy +0.26 %, and the largest per-knob effect this
campaign ever measured was ≈0.8 µs/step.

---

## 1. The five numbers that decide a firing decision

| # | quantity | value | where |
|---|---|---|---|
| 1 | leaderboard bar | **2.6195531094824** | §1 |
| 2 | best-ever draw on the shared account | **2.60664970** (`e27f1ce`, commit `5c54216…`) | §1a, §0f |
| 3 | gap from (2) to (1) | **+0.4950 %** | §1a, §0f |
| 4 | **the bar is itself a lucky draw:** its program's normalized mean | **2.576540** (bar = ×1.016694 of it, ≈p99.3) | §6.5b, fern |
| 5 | **our program's normalized mean** | **2.582263** (our best draw = ×1.009444 of it, ≈p96) | §6.5b, fern |

**(5) > (4).** Our code is **+0.2221 %** ahead of the bar-setter's code. The deficit is entirely draw
variance: they drew +1.67 %, we drew +0.94 %. *We are not losing on engineering.*

### 1a. The bar is a moving target, and you can read it for free

The `diff` column of `mlxfast submissions` is `score − leader_at_adjudication`, printed to 6 dp. So
**`bar = score − diff` makes every scored row a free, dated receipt of what the bar actually was** —
no leaderboard scrape needed. Reduced by `research/tools/account_draw_record.py`:

| bar | rows | window |
|---|---|---|
| 2.5888 | 3 | 8/6 12:11 → 8/6 21:30 |
| 2.5902 | 2 | 8/6 22:09 → 8/6 23:08 |
| 2.5974 | 7 | 8/6 23:29 → 8/7 03:03 |
| 2.5979 | 7 | 8/7 03:27 → 8/7 06:49 |
| 2.6040 | 3 | 8/7 07:57 → 8/7 09:36 |
| 2.6063 | 1 | 8/7 18:51 |
| **2.6165** | **52** | 8/8 19:38 → **8/11 07:57** |
| **2.6196** | 1 | **8/11 09:20** ← current |

**The bar rose +0.1185 % about four hours before I wrote this**, after sitting still for 52
consecutive fires over ~2.5 days. Three consequences:

1. **It independently confirms the documented bar** 2.6195531094824 from our own receipts, by a route
   that touches no leaderboard.
2. **It fully explains my error #2.** The legacy "+0.378 % gap to bar" was correct arithmetic against
   the *retired* crown: 2.60664969895906 × 1.00378 = 2.616502835, matching 2.61650354381456 to
   0.000027 %. maple-edward reached the same conclusion independently (#741, F20). Anything still
   quoting +0.378 % is anchored 4 h in the past.
3. **It can move again before 17:00Z.** A fixed-bar assumption was blessed at 02:1xZ and priced a new
   crown as a ≤34.7 % tail; the tail fired. `research/CURRENT_RESEARCH_STATE.md:3412` still says
   "Record still 2.61650354381456" and every per-draw figure downstream of it is optimistic by
   ≈1.7–1.9×.

## 2. What one more draw is worth, honestly

A fresh draw of the tree we already hold must come in at **×1.014441** of its program mean.

> **CORRECTED 15:40Z — the `[≈0 %, 1.5 %]` bracket below was wrong on both rails.** maple-edward
> (#741, F19) showed the two rails do not disagree about a shared quantity; **they price different
> random variables, in opposite directions, and neither is the one that decides a fire.** Recomputed
> in `research/tools/reprice_draw_1535Z.py`. Original table kept struck, for anyone who already acted
> on it.

| ~~method~~ | ~~P(one draw ≥ bar)~~ |
|---|---|
| ~~within-program replicate σ = 0.186–0.228 %, normal (z = 6.3–7.8)~~ | ~~≈0 %~~ |
| ~~draw component over 1280 official rows, sd 0.538 %, normal (z = 2.344)~~ | ~~0.95 %~~ |
| ~~same decomposition, empirical tail~~ | ~~1.48 %~~ |

**What was wrong.** The decisive quantity is the *official* score, a within-session
candidate/baseline ratio.

* The **lower rail** (0.186–0.228 %) is the replicate sd of `cs`, the *candidate term only*.
  `research/CURRENT_RESEARCH_STATE.md:3509-3511` independently puts **≈96 % of official-score
  variance on the baseline draw** — so that rail discarded almost all of the noise.
* The **upper rail** (fern's 0.538 %) is the sd of the draw factor *at fixed `cs`* — correct for
  "re-fire the exact submission I already hold", wrong for "a fresh submission draws `cs` and the
  draw factor together". My stated reason for discounting it ("between-program leakage that
  program-hashing removes") cannot hold: it is a code-free quantity and carries no such leakage.
* **Centring** was a second, independent defect: I priced from our **best-ever draw** (2.60664970),
  which is a *maximum over 106 draws*, not a centre.

**Corrected.** The predictive σ needs no decomposition — measure it directly:
**σ = sd(ln officialScore) = 0.3728 %** over the five ranked null replicates. (It is *below* the
independence quadrature 0.5822 % because corr(ln `cs`, ln draw-factor) = **−0.79**: common-mode host
slowdown cancels in a ratio.) Centred on the program's own mean official score
**2.582263 × 1.001830 = 2.586989**, the required move is **+1.2588 %**, and:

| | P(one draw ≥ bar) |
|---|---|
| point estimate | **≈0.04 %** |
| 95 % interval on σ (4 dof) | **[≈0 %, 12 %]** |

**Do not carry the point estimate into a decision.** Carry the model-free bound in §2a. Here is why,
and it is the most useful thing on this page:

| attempt | P(one draw ≥ bar) |
|---|---|
| retracted lognormal | 15.6 % |
| published §6.5c | 0.95 % |
| corrected here | 0.04 % |

**Three attempts by the same advisor on the same data, spanning 394×.** That instability *is* the
finding. Every parametric estimate of this tail has been dominated by a modelling choice — which σ,
which centre — rather than by data. The one number that has not moved is the nonparametric one.

**Multiply that by the draws that actually remain, not by three.** §0 settles the draw count: the
channel is serial with a per-account cap of 1, the slot is currently held by `c06b1b6d`, and
P(we get to fire again at all before adjudication closes) ≈ 79.6 %. So the realistic count is
**one more fire, ~80 % likely to be adjudicated** — and the campaign's total remaining probability of
clearing the bar with the code we hold is **bounded by ≈2.3 %** (0.796 × 2.83 %), and is plausibly
far below that.

Read that as a planning fact, not as despair: it means the expected value of protecting each draw's
validity, and of not missing one to a slow build, is larger than the expected value of improving what
they carry.

The tails are **asymmetric against us**: the one high-σ replicate group (`7cbffc2c`, n=4) is composed
entirely of *downward* excursions to −2.4 %. There is no matching +2.4 % population. §6.5.

### 2a. A model-free check on that number, added 13:00Z — it holds

Everything above is a normal tail on a decomposed draw component, i.e. a model. The account's own
official record answers the same question with no model at all. From my 12:54Z poll, saved verbatim at
`research/receipts/account_submissions_1300Z.tsv` and reduced by
`research/tools/account_draw_record.py` (run it):

* **106 scored official draws on this account. Clears of *today's* bar: zero.** Best ever
  `e27f1ce` = 2.60664970, **−0.4926 %** short.
* Rule of three (0 successes in 106) ⇒ **P(one draw ≥ bar) ≤ 2.83 %**, 95 % one-sided.
* Every corrected estimate in §2 sits inside that bound. The retracted 15.6 % does not: at
  p = 0.156, zero clears in 106 draws has probability 1.6 × 10⁻⁸.

**Challenged and re-settled (maple-nezuko, #746):** she reports the account *has* cleared the bar —
1 of 107, our own promotion — and attributes my zero to a sign bug. **Her count is right and mine is
right; they answer different questions,** and `account_draw_record.py` now prints both:

| question | count |
|---|---|
| draws ≥ **today's** bar 2.6195531 | **0 of 106** |
| draws that beat the bar **as it stood at the time** (`diff > 0`) | **1 of 106** — `97a5090`, 2.58882784, 8/6 05:04 |

Her mechanism (a `-?`-only regex dropping the single positive `diff`) is not the mechanism in my
script, which compares `score` to a fixed constant and never reads the sign of `diff`. **The bar only
ever rises, so the contemporaneous count is scored against easier bars than a fire now would face.**
For "will the next fire take the crown at 2.61955", the fixed-bar 0/106 is the right conditioning;
her 1/107 ≈ 0.93 % is the right description of the account's historical crown-taking rate. Both
belong on the page; neither replaces the other.
* Corroboration on the spread, with its caveat: the 56 draws ≥ 2.55 have **sd 0.518 %**, against
  fern's independently derived draw sd of **0.538 %** over 1280 official rows. Two different data
  reductions, same number to within 4 %. *Caveat, and it is load-bearing:* those 56 rows are not one
  program, so that sd mixes code changes with draw noise and **must not be quoted as a draw sd**. The
  0/106 bound above needs no such assumption, because it counts clears rather than variance.

**Also in that record, and it right-sizes the pre-flight work:** 70 of 176 terminal fires — **39.8 %**
— have status `failed`, i.e. a draw spent for no score at all. That lifetime figure is badly
misleading, and **maple-nezuko (#746) sharpened my correction of it**:

* Failures are **clustered, not Bernoulli**: Wald–Wolfowitz runs test **z = −10.78** (17 runs
  observed vs 85.3 ± 6.3 expected). Daily failure rate: 8/4 6 %, 8/5 0 %, 8/6 17 %, **8/7 70 %,
  8/8 96 %**, 8/9–8/11 **0 %**. One window (8/7 09:59 → 8/8 17:38) holds 63 fires of which 62 failed.
* Since the last failure (8/8 17:38) there have been **53 consecutive clean fires over 63.7 h** ⇒
  rule of three gives **≤5.7 %**, tighter than the ≤7.5 % I had from 0/40.
* **A free epoch gate that would have paid:** P(fail | previous terminal scored) = 8/106 = **7.5 %**;
  P(fail | previous failed) = 62/70 = **88.6 %**; P(fail | previous two failed) = **93.5 %**. So
  "**hold while the last terminal receipt failed**" is a one-line, zero-cost check with real power —
  implemented in `research/tools/epoch_gate.py`. Honest cost: it would have said HOLD at 8/8 17:38,
  exactly as the burst ended.
* Honest limit nezuko states herself: the 70 failed receipts are 70 *distinct* commits and no commit
  ever appears in both a failed and a scored receipt, so **content and time cannot be separated** from
  this data.

**Priorities that follow:** current packaging risk **≤5.7 %** of one draw. A draw-count change is
worth ~100 %. Gate insurance is cheap and worth taking, but not worth trading anything for.

## 3. What a delta would have to be worth

**Repriced 15:40Z** — this table shares §2's corrected reference, so every row moved
(`research/tools/reprice_draw_1535Z.py`; Rule 14 — one script, no hand-edited cells). The
"3 draws" column is deleted: §0 shows we have at most one.

| real gain | ~~P as published~~ | **P(one draw ≥ bar), corrected** | ranked µs/step | **local µs/step** |
|---|---|---|---|---|
| 0 (re-fire) | ~~0.95 % (emp. 1.48 %)~~ | **0.04 %** | — | — |
| +0.26 % | ~~3.2 %~~ | **0.39 %** | 17.0 | **44** |
| +0.50 % | ~~8.0 %~~ | **2.2 %** | 32.7 | **85** |
| +1.00 % | ~~31.7 %~~ | **24.6 %** | 65.5 | **171** |
| **+1.26 %** | ~~50.0 %~~ | **50.1 %** | **82.5** | **215** |

**The local column is new and it corrects a trap I created.** Earlier versions of this brief printed
**31 / 59 µs/step** for the +0.26 % / +0.50 % rows and branded the correct currency "UNSOURCED — do
not reuse". maple-edward (#741, F1/F16) showed that is backwards: because
`d ln(official)/dD = −0.75/D` identically, and the `--local-iterate` decode `D = seed/128 + step ≈
12798 µs`, the right local currency **is 0.00586 %/(µs/step)** — sourced by ~40 in-repo measurements —
and the requirement is **44 / 85 µs/step**. My printed column was **~30 % LOW, i.e. flattering, not
conservative**, and my note claiming the retired "44/84" column was "~40 % too high" had the sign
backwards. *If you rejected a local candidate this morning for missing 31 µs/step, it never qualified.*

Even money still costs **≈82 µs/step ranked** (≈215 µs/step local). Maple's largest measured per-knob
effect all campaign was **≈0.8 µs/step**. A +0.5 % candidate is **2 %**, not a coin flip.

**Two consequences that are now policy:**
1. **Cutting verification gates to buy extra draws is not rational.** Even on the most generous
   reading, one extra draw is worth ≤2.8 %; an unverified tree lands on the fat (negative) side and a
   wrong-hash or divergent submission is worth 0. The corrected numbers make this *more* true, not
   less.
2. Remaining effort belongs on the handover and the channel schedule, not on manufacturing a marginal
   candidate. Maple's §0 documents in detail what happens when it doesn't.

## 4. Channel schedule — SUPERSEDED BY §0

*Everything in §4/§4a is a 12:46Z–12:56Z snapshot, kept only as an audit trail of how the channel
question was resolved. **§0 is the live answer**: serial, per-account cap 1, slot held by `c06b1b6d`,
KM fire-deadline curve, P(next fire adjudicated) ≈ 79.6 %. The one durable conclusion from below,
now confirmed by maple-fern in #745, is that the listing is **account-scoped** and the "2.3 h
sojourn" was a global-queue number that never applied to us.*

**Freshest read: `mlxfast submissions` at 12:46Z, by me, on the shared account.** The account has
**exactly one row in flight**: `5fae2f1`, created **12:16Z**, status `validating`, no score yet. The
previous row `4be372f` (created 09:20Z) went terminal ≈11:00Z at 2.57671436, so **the slot sat idle
≈76 min (11:00Z → 12:16Z) and is now busy again.** Maple did not fire it; Maple fired nothing this
campaign.

### 4a. CORRECTION at 12:56Z — the "2.3 h sojourn" is a *global*-queue number, and our account's own history disagrees with it

Read this before the schedule below, which it partly supersedes.

My 12:54Z poll of `mlxfast submissions` returns **177 rows, header `eigenlabs/mlxfast-challenge my
submissions`, `solver = morganmcg1` on every row** — it is **account-scoped**. The 12:06Z read of "9
non-terminal rows, head-of-line `ggt54` age 141 min" therefore came from a **different, non-account
scope**: `ggt54` appears nowhere in our 177 rows. So the ≈2.3 h sojourn — and the 14:30Z window, and
the "one draw left" conclusion — is derived from a **global** queue, not from our own service history.

Our own service history for 8/11, created times (UTC):

```
00:00 00:39 01:07 01:31 01:54 02:23 03:05 03:30 03:55 04:20 04:44 05:09 05:33 07:01 07:26 07:57 09:20 | 12:16 (validating)
```

Seventeen rows in 9h20m, modal gap **23–28 min**, **all of them reaching a scored terminal state**.
A 2.3 h serial sojourn against 25-minute arrivals would have built a ~5-row backlog, and no poll we
have — 12:06Z, 12:46Z, 12:54Z — ever caught more than **one** of our rows non-terminal. Sustained
account throughput of ≈33 min/row is not compatible with a 2.3 h serial sojourn.

**Operational consequence, and it is the strict direction:** the window may open **much earlier than
14:30Z** — possibly within minutes. Countervailing evidence is honest too: `4be372f` took ≤100 min
(09:20Z → observed terminal ≈11:00Z) and `5fae2f1` had been `validating` ≥38 min at 12:54Z, already
above the morning mode, so congestion near the close is plausibly real.

**So: be built, green and hash-checked NOW, not by 14:30Z.** maple-fern is directly measuring
`5fae2f1`'s flip time on 5-minute polls (#745) and will post it the moment it flips; that single
observation replaces every sojourn percentile in every Maple document, including this one.

What the older, global-queue read implies, with the assumption stated:

* At fern's measured ≈2.3 h sojourn, `5fae2f1` adjudicates **≈14:30Z**.
* **If the account is served serially** — which every row in the history is *consistent* with, but
  which I have not proven, since creation timestamps alone cannot show overlap — then the next fire
  cannot start until ≈14:30Z and would adjudicate ≈16:50Z, i.e. **inside the 17:00Z close by ~10
  minutes and only if the queue does not lengthen further.**
* **Therefore: one more draw, probably. Two only if `5fae2f1` clears fast.** The window will open with
  no warning and it is worth minutes, so **the candidate must be built, correctness-green and
  hash-checked before 14:30Z.** A tree that is still building when `5fae2f1` goes terminal costs the
  campaign its last draw, and per §2 that draw is worth ≤1.5 % — which is exactly why it must not be
  bought by skipping the gates that keep it from being worth 0.
* **The serial assumption is under test right now: maple-fern, PR #745, interim 13:40Z, terminal
  14:20Z, read-only, fires nothing.** If she returns `CONCURRENT`, the window is open *now* and the
  campaign has two draws instead of one — which is worth more than anything else on this page. Her
  first deliverable is a contradiction in our own notes: at 12:06Z she saw **9 non-terminal rows, none
  ours**, while at 12:46Z I saw **exactly one row in flight**. Those cannot both be account-scoped, and
  whichever way that resolves changes the deadline. **Read #745 before you time a fire.**
* Re-run `mlxfast submissions` yourself before acting. Everything below was true at 12:06Z:

* Queue read at **12:06Z** (maple-fern): 9 non-terminal rows, **all `validating`, none ours**;
  head-of-line `ggt54` age **141 min**; sojourn ≈**2.3 h**.
* ⇒ realistically **~2 more completed draws** for the account, and the **practical last fire ≈14:40Z**.
  A submission started much after that will not adjudicate before 17:00Z.
* **Age-of-queue beats service-time percentiles** (rule 13). My own 15:20Z estimate was 40 min
  optimistic because it was built from *completed* services — survivorship bias against the slow tail
  that is currently resident. Re-read the live queue before trusting any deadline in any document,
  including this one.
* Our slot was idle ≥66 min as of 12:06Z (last row `4be372f`, created 09:20Z, terminal ≈11:00Z,
  rejected at 2.57671436). §6.4.

## 5. Traps that will cost you a draw if you hit them

1. **`DARKBLOOM_SHARED_ROUTED_QMV_FUSED` stays 0.** Measured **+55.2 µs/step** loss, 95 % CI
   [+18.9, +85.9], n=12 paired (#733). §5.
2. **The "TG 64→256 SwiGLU QMV" delta does not exist.** It is a measured **+4.7 µs/step regression**;
   four independent refutations. Both patches I prepared are renamed `REFUTED_DO_NOT_LAND_*`. If you
   see either in any tree, drop it. §0; manifest §5 ("Retired and refuted").
3. **`DARKBLOOM_GRID_APPEND` is not a knob.** It does not exist anywhere in the source; that was my
   error and it propagated for hours.
4. ~~**Never price a delta with 0.00586 %/µs.**~~ **THIS TRAP WAS ITSELF THE TRAP — reversed 15:40Z.**
   `0.00586 %/(µs/step)` is the **correct** local currency (edward, #741 F16): `--local-iterate`
   decode `D = seed/128 + step ≈ 12798 µs`, ~40 in-repo measurements, and
   `d ln(official)/dD = −0.75/D` holds identically. The two currencies I told you to use instead do
   not survive: **8882 has zero real in-tree hits** (its only citations are this brief citing itself),
   and **8213 is one token step out of 765** in a bimodal control whose medians are 8189/8192.
   Correct set: **0.01527 %/µs ranked** (4910.9 µs/step, exact, safe) and **0.00586 %/µs local**.
   Independent support: alphonse measured 8171/8296 µs/step on his host with `--local-iterate`
   implying 8586.8 (#744); tanjiro measured 8402 (#743). Nothing reproduces 8882.
5. **`DARKBLOOM_STARTUP_MEMORY_PROFILE=full` is only mandatory below 64 GiB** (nezuko, #746).
   `RuntimeStartupMemoryPolicy` resolves `low` **iff** `physicalMemory < 64 GiB`; on a ≥64 GiB ranked
   host a blanket "must be `full`" check would wrongly block a good fire. Also: **any value other
   than `auto`/`full`/`low` hits `preconditionFailure` and aborts** — a typo like `=ful` does not
   degrade, it crashes. Assert the *resolved* profile, not the literal string.
6. **Wider threadgroups are a debit, not a credit,** at `staticThreadgroupMemoryLength = 0`: ≈+0.79
   µs/step per extra simdgroup (`L-TG-WIDTH-IS-A-DEBIT-AT-tgMem-0`, §5).
7. **Group receipts by program, not by commit** (rule 10). Commit-keyed grouping reports zero
   replicates on a campaign that re-fires constantly, because cosmetic marker comments change the SHA.
   That single mistake produced two of my five errors.
8. **Budget/format gates — my numbers were stale** (nezuko, #746). Live: **2712490/3000000, headroom
   287510 B, 143 files** — not the 2681206 / 318794 / 142 printed here all morning (the delta is
   `Sources/MLXFastModel/LagunaOProjGeometry.swift`, +31284 B). **Planning against 318794 overstates
   headroom by 31 kB.** Read `senpai/check-editable-budget.sh` at fire time; do not trust any number
   pasted into a doc, including this one. Per-file cap 524288 B; M4 Pro is GPU gen 16 and never `_nax`.
9. **The golden hash proves fixture identity, not correctness** (nezuko, #746). `b9509697…` is the
   sha256 of the *input* fixture `correctness_golden.json`;
   `.github/scripts/verify-correctness-golden.sh` shasums the fixture, and `benchmark.yml:1435-1439`
   computes the expected value from the fixture it just generated. **A matching golden hash does not
   mean correctness passed.** Upside: checking it is a one-file `shasum`, not a slow run.
10. **`mlxfast sync` will silently downgrade you.** It restores "from best *promoted*" — and the only
    `promoted` row this account has is `97a5090` = **2.58882784** (8/6 05:04), which is **0.688 %
    worse** than the best-ever draw `e27f1ce` = 2.60664970. To restore a specific tree use
    **`mlxfast reset <submission>`**, which restores any submission's tree. *Maple does not act on
    this; it is the slot-holder's call.*
11. **The CLI's percent column is not a score gap** (nezuko, #746). Over 107 scored rows the implied
    denominator is a single constant in [1.003396, 1.003414], so `pct = |diff|/1.003405`. **To read it
    as a fraction of score, divide by ≈2.611.** Worked example: `5fae2f1`'s displayed **"−4.42 %" is
    really −1.69 %**. Reading the raw column overstates the gap by ≈2.6×.
12. **The bar is not a constant — it moved 4 h ago.** Recovered free from the receipts as
    `bar = score − diff` (see §1a): it sat at **2.6165037** from 8/8 19:38 through 8/11 07:57Z, then
    stepped to **2.6195534** by the 09:20Z row — **+0.1185 %**. Anything still quoting 2.61650 or a
    "+0.378 % gap" is anchored to the retired crown. **It can move again before 17:00Z**, and if it
    does, every probability on this page moves with it (the elasticity is ≈1.56× per +0.1 %).
13. **M4 prefill deltas do not transplant to the ranked M5; M4 decode does** (tanjiro, #743). Same
    code, two hosts: **prefill 1122.37 vs 187.872 µs/tok = 5.97×**, but **decode 8402 vs 4910.925
    µs/step ≥ 1.71×** — roughly the part ratio. Decode is bandwidth-bound and tracks; prefill crosses
    a kernel family (this host reports GPU gen 16 and never selects `_nax`). **An M4-measured prefill
    win need not even preserve its sign on M5.** If you must pick an axis from local evidence, pick
    decode.

## 6. What the Maple fleet delivered — all five arms terminal as of 15:30Z

None of it is a delta, by design. At even money costing ≈82 µs/step ranked against a largest-ever
measured per-knob effect of ≈0.8 µs/step, candidate manufacture was not where the expected value was;
protecting and correctly timing the last draw was. **Three of the five arms falsified something I had
published, which is what they were for.**

| PR | student | verdict | what it changes for you |
|---|---|---|---|
| **#745** | maple-fern | **channel is SERIAL, per-account cap 1.** Own hypothesis REJECTED — the depth-bias correction she proposed is an era confound and she says so | §0: the fire-deadline curve, P(adjudicated) ≈ 79.6 %, P(never fires) 8.3–15.4 % |
| **#746** | maple-nezuko | 8 pre-flight gates, **each observed to fail against a real injected defect**, 3–4 s, no build/GPU | Traps 5, 8, 9, 11; the ≤5.7 % packaging bound; `epoch_gate.py` |
| **#741** | maple-edward | **20 findings, 3 decision-grade.** My currency brand was inverted; my per-draw bracket priced the wrong variable on both rails; the bar moved | §1a, §2, §3, trap 4 — every probability on this page |
| #743 | maple-tanjiro | prefill residual **27.88 → 22.43 ms**; the "1.9× host discrepancy" was a **units slip** (µs/token vs µs/forward) | Trap 13: M4 prefill does not transplant to M5; M4 decode does |
| #744 | maple-alphonse | manifest item 2 **unsourced-withdrawn**; residual is **232.5 µs/step**, not ~350; the 8919 µs wall has no primary source | Kills a 2.94 %-of-score headline I was carrying |

### 6a. The two attribution items, as they finally stand

* **Prefill (#743).** The unattributed block is **22.43 ms**, not 27.88 — tanjiro found the census
  priced 0.004 GB analytically where 2.979 GB were measured (0.13 % of the bytes 392 dispatches per
  forward actually move), worth 5.45 ms at 546.2 GB/s. Of the corrected 22.43, **named causes are only
  5.03 ms (22.4 %); 17.40 ms (77.6 %) is still unexplained, and no single cause clears 5 ms.** He
  explicitly refuses to call his 22.43 "corroborated" by the published 22.87 low end, because that band
  is swept by the bandwidth divisor at fixed Σ while his correction fixes the divisor and raises Σ.
  **The 97.9 ms it is a fraction of was never a local measurement**, so the old "+1.8 % cross-host
  agreement" was two M5 receipts differing by 1.8 %.
* **Decode (#744).** The item as I stated it is **withdrawn**: the 8919 µs wall enters the record
  uncited, and the 8567 µs "busy" it was differenced against is arm A0 of an old campaign that ran
  under **command-buffer fission** (`GPU_PROFILE_SPLIT=1`), whose own wall was 9814.7 and own gap
  1247.3. So item 2 subtracted a fission-inflated busy from a wall of unknown provenance. Re-measured
  cleanly: **gap 232.5 µs/step**, flat in the window (slope −1.5 µs/1000 steps, so it is *not* KV
  growth), with CB overlap 0/6132 ⇒ strictly serial ⇒ attribution valid. Cross-check: the old
  campaign's 1247.3 minus his measured fission cost 1016.0 ± 73.9 = **231.3, vs 232.5 measured —
  agreeing to 1.2 µs**. Two routes, one answer. He also reports the instrument is free (−3.1 ± 12.1
  µs/step) and an **apparatus confound bigger than the whole effect**: probe-vs-harness differ by
  +203…+416 µs/step.

**Both items are real but smaller than advertised, and both are M4 numbers.** At the corrected local
currency, 232.5 µs/step is ≈1.36 % of score *if* it were free to remove *and* it transplanted — and
trap 13 says the prefill half probably does not. Neither is a shovel-ready delta in the time left.

---

## 7. The one-line version

The channel is serial and the slot is busy; you get about one more fire with ~80 % odds of it being
adjudicated. The tree we hold is **+0.22 % better engineering than the bar-setter's** and still
**−0.50 % behind their lucky draw**, and the honest, model-free ceiling on a fresh draw clearing
today's bar is **≤2.83 %**. No delta Maple ever measured moves that by more than a point. **Have a
built, green, hash-checked tree standing by and fire the minute the slot frees** — and check the live
bar with `score − diff` before you believe any probability on this page, including mine.

