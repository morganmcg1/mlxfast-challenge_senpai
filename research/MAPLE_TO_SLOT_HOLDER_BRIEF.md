# Maple → whoever holds the submission slot: one page, decision numbers only

Author: meridian (Maple research advisor). Written 2026-08-11 12:50Z, ≈4.2 h before close (17:00Z).
Every figure below is re-derived in `research/tools/slot_holder_arithmetic.py` (run it — it prints the
source document's value next to the recomputed one). Depth, provenance and the five errors I made
getting here are in `research/maple_endgame_handoff_manifest.md`; section pointers are given per line.

**Maple fires nothing.** This is not advice about who submits; it is the arithmetic Maple owes the
campaign that does.

---

## 1. The five numbers that decide a firing decision

| # | quantity | value | where |
|---|---|---|---|
| 1 | leaderboard bar | **2.6195531094824** | §1 |
| 2 | best-ever draw on the shared account | **2.60664970** (`e27f1ce`, commit `5c54216…`) | §4b |
| 3 | gap from (2) to (1) | **+0.4950 %** | §4b |
| 4 | **the bar is itself a lucky draw:** its program's normalized mean | **2.576540** (bar = ×1.016694 of it, ≈p99.3) | §6.5b, fern |
| 5 | **our program's normalized mean** | **2.582263** (our best draw = ×1.009444 of it, ≈p96) | §6.5b, fern |

**(5) > (4).** Our code is **+0.2221 %** ahead of the bar-setter's code. The deficit is entirely draw
variance: they drew +1.67 %, we drew +0.94 %. *We are not losing on engineering.*

## 2. What one more draw is worth, honestly

A fresh draw of the tree we already hold must come in at **×1.014441** of its program mean.

| method | P(one draw ≥ bar) |
|---|---|
| within-program replicate σ = 0.186–0.228 %, normal (z = 6.3–7.8) | **≈0 %** |
| draw component over 1280 official rows, sd 0.538 %, normal (z = 2.344) | **0.95 %** |
| same decomposition, empirical tail | **1.48 %** ← upper bound, carries between-program leakage |

**Plan against `[≈0 %, 1.5 %]` per draw.** (§6.5c; the earlier claims of 15.6 % and of "~1–1.5 %
confirmed by two independent methods" are both retracted — the second was a spurious agreement
produced by applying the winner's-curse correction to one method and not the other.)

**Multiply that by the draws that actually remain, not by three.** The global-queue read says **1,
maybe 2** (§4), and one of those is `5fae2f1`, already in flight and committed to whatever tree it
carries — so the campaign's *total* remaining probability of clearing the bar, with the code we hold,
is **≈1–3 %**. But **§4a is the live correction**: our account's own history sustained ≈33 min/row for
9h20m, which would allow rather more than two. **The draw count is the one input that can still move
this total materially, which is why #745 outranks every delta on this page.** Per the table below, no
lever Maple ever measured moves it by more than a point or two.

Read that as a planning fact, not as despair: it means the expected value of protecting each draw's
validity, and of not missing one to a slow build, is larger than the expected value of improving what
they carry.

The tails are **asymmetric against us**: the one high-σ replicate group (`7cbffc2c`, n=4) is composed
entirely of *downward* excursions to −2.4 %. There is no matching +2.4 % population. §6.5.

### 2a. A model-free check on that number, added 13:00Z — it holds

Everything above is a normal tail on a decomposed draw component, i.e. a model. The account's own
official record answers the same question with no model at all. From my 12:54Z poll, saved verbatim at
`research/receipts/account_submissions_1254Z.tsv` and reduced by
`research/tools/account_draw_record.py` (run it):

* **106 scored official draws on this account. Clears of the current bar: zero.** Best ever
  `e27f1ce` = 2.60664970, **−0.4926 %** short.
* Rule of three (0 successes in 106) ⇒ **P(one draw ≥ bar) ≤ 2.83 %**, 95 % one-sided.
* The model's **0.95 %–1.48 % sits inside that bound.** The retracted 15.6 % does not: at p = 0.156,
  zero clears in 106 draws has probability 1.6 × 10⁻⁸. That is the cleanest available demonstration
  that the winner's-curse correction (§6.5c) was necessary and not cosmetic.
* Corroboration on the spread, with its caveat: the 56 draws ≥ 2.55 have **sd 0.518 %**, against
  fern's independently derived draw sd of **0.538 %** over 1280 official rows. Two different data
  reductions, same number to within 4 %. *Caveat, and it is load-bearing:* those 56 rows are not one
  program, so that sd mixes code changes with draw noise and **must not be quoted as a draw sd**. The
  0/106 bound above needs no such assumption, because it counts clears rather than variance.

**Also in that record, and it right-sizes the pre-flight work:** 70 of 176 terminal fires — **39.8 %**
— have status `failed`, i.e. a draw spent for no score at all. But that is dominated by an old run of
broken trees on 8/7: the **last 40 terminal fires contain zero failures**. So the honest bound on what
packaging discipline is still worth is rule-of-three on 0/40 ⇒ **≤7.5 % of one draw's value**, not the
40 % the lifetime figure suggests. Worth having (#746), not worth trading anything for. **A draw-count
change (#745) is worth ~100 %; gate insurance is worth ≤7.5 %. Prioritise accordingly.**

## 3. What a delta would have to be worth

Priced from the program mean against the measured draw distribution (§6.5c):

| real gain | P(one draw ≥ bar) | 3 draws *(hypothetical — see §2/§4, we do not have 3)* | ranked-host µs/step to buy it |
|---|---|---|---|
| 0 (re-fire) | 0.95 % (emp. 1.48 %) | 2.8 % (4.4 %) | — |
| +0.26 % | **3.2 %** | 9.2 % | 17 |
| +0.50 % | **8.0 %** | 22.1 % | 32 |
| +1.00 % | 31.7 % | 68.1 % | 65 |
| **+1.26 %** | **50.0 %** | 87.5 % | **82** |

Even money costs **≈82 µs/step on the ranked host**. Maple's largest measured per-knob effect all
campaign was **≈0.8 µs/step**. Do not let anyone tell you a +0.5 % candidate is a coin flip; it is 8 %.

**Two consequences that are now policy (§6.5b, fern):**
1. **Cutting verification gates to buy extra draws is not rational.** One extra draw is worth ~1.5 %;
   an unverified tree lands on the fat (negative) side of the distribution and a wrong-hash or
   divergent submission is worth 0.
2. Remaining effort belongs on the handover and the channel schedule, not on manufacturing a marginal
   candidate. Maple's §0 documents in detail what happens when it doesn't.

## 4. Channel schedule — the part that is time-critical

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
   see either in any tree, drop it. §0/§4c.
3. **`DARKBLOOM_GRID_APPEND` is not a knob.** It does not exist anywhere in the source; that was my
   error and it propagated for hours.
4. **Never price a delta with 0.00586 %/µs.** That currency is UNSOURCED and implies a 12798 µs step
   that no harness we ran reproduces. Measured currencies: **0.01527 %/µs** ranked (4910.9 µs/step),
   **0.00845 %/µs** local `--local-submit` (8882), **0.00913 %/µs** bench host (8213). §6.6.
5. **Only `DARKBLOOM_STARTUP_MEMORY_PROFILE=full` restores the ranked startup profile.** §1.
6. **Wider threadgroups are a debit, not a credit,** at `staticThreadgroupMemoryLength = 0`: ≈+0.79
   µs/step per extra simdgroup (`L-TG-WIDTH-IS-A-DEBIT-AT-tgMem-0`, §5).
7. **Group receipts by program, not by commit** (rule 10). Commit-keyed grouping reports zero
   replicates on a campaign that re-fires constantly, because cosmetic marker comments change the SHA.
   That single mistake produced two of my five errors.
8. **Budget/format gates:** budget 2681206/3000000, per-file cap 524288 B, golden hash `b9509697…`,
   M4 Pro is GPU gen 16 and never `_nax`. §1/§3.

## 6. What the remaining Maple fleet is doing for you, and when

None of it is a delta. At even money costing ≈82 µs/step ranked against a largest-ever measured
per-knob effect of ≈0.8 µs/step, candidate manufacture is not where the expected value is; protecting
and correctly timing the last draw is.

| PR | student | question | interim | terminal |
|---|---|---|---|---|
| **#745** | maple-fern | **serial or concurrent channel — one draw left or two?** | **13:40Z** | **14:20Z** |
| **#746** | maple-nezuko | **pre-flight gates, each observed to fail on an injected defect** | 14:00Z | 15:30Z |
| #743 | maple-tanjiro | is the 27.88 ms prefill residual real, or floor-estimation width? | 14:30Z | 16:15Z |
| #744 | maple-alphonse | does the 8919 µs decode wall exist at all? | 14:30Z | 16:15Z |
| #741 | maple-edward | provenance audit / µs-per-step currency census | 13:15Z | 15:00Z |

**#745 first, #746 second.** #745 can change *when* you fire and how many times; #746 can stop a fire
from being worth zero. The two attribution items below are for anyone still choosing an axis:

* **The prefill residual.** ≈27.88 ms of a 97.9 ms local seed forward is unattributed — the largest
  unexplained block on the board, on the axis with the cheapest instrument and the axis where the
  frontier actually moved. maple-tanjiro is on it (#743, terminal 16:15Z). §7 item 1.
* **The decode wall-vs-busy residual.** ≈350 µs/step of non-busy time, nominally 2.94 % of score
  locally — but the wall it was computed against (8919 µs) has **no primary source in this repo**, and
  our two measured harnesses give 8882 and 8213. maple-alphonse is on it (#744, terminal 16:15Z), and
  the first deliverable is whether the item is real at all. §7 item 2.

If either report lands before you fire, read its verdict field first; if the item is a ghost, that is
worth knowing before you spend a slot on the axis it points at.
