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

**Plan against `[≈0 %, 1.5 %]` per draw. Three draws ⇒ ≤4.4 %.** (§6.5c; the earlier claims of 15.6 %
and of "~1–1.5 % confirmed by two independent methods" are both retracted — the second was a spurious
agreement produced by applying the winner's-curse correction to one method and not the other.)

The tails are **asymmetric against us**: the one high-σ replicate group (`7cbffc2c`, n=4) is composed
entirely of *downward* excursions to −2.4 %. There is no matching +2.4 % population. §6.5.

## 3. What a delta would have to be worth

Priced from the program mean against the measured draw distribution (§6.5c):

| real gain | P(one draw ≥ bar) | 3 draws | ranked-host µs/step to buy it |
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

What that implies, with the assumption stated:

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

## 6. The two things Maple would spend the next hour on if it held the slot

Neither is a delta; both are cheap and both are unclaimed as of 12:50Z:

* **The prefill residual.** ≈27.88 ms of a 97.9 ms local seed forward is unattributed — the largest
  unexplained block on the board, on the axis with the cheapest instrument and the axis where the
  frontier actually moved. maple-tanjiro is on it (#743, terminal 16:15Z). §7 item 1.
* **The decode wall-vs-busy residual.** ≈350 µs/step of non-busy time, nominally 2.94 % of score
  locally — but the wall it was computed against (8919 µs) has **no primary source in this repo**, and
  our two measured harnesses give 8882 and 8213. maple-alphonse is on it (#744, terminal 16:15Z), and
  the first deliverable is whether the item is real at all. §7 item 2.

If either report lands before you fire, read its verdict field first; if the item is a ghost, that is
worth knowing before you spend a slot on the axis it points at.
