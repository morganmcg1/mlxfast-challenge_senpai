# r100-B — the float4 merge epilogue re-port, and the price of a lottery ticket

- PR: [#555](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/555)
- assignment `maple-r100-b-epilogue-report-and-session-factor`, revision `r100-b-rev1`
- base `2aa2f79228d59a3eeba3abc05ec96daa9e0b99a1` (`codex/mlxfast-maple-20260804-advisor`)
- branch `maple-tanjiro/r100-epilogue-report-and-session-factor`
- host: Apple **M4 Pro**, **20 GPU cores**, Apple GPU generation **16**, Metal 4,
  48 GiB unified memory (`hw.memsize` 51539607552 ⇒ low-memory startup profile),
  10 performance CPU cores. Not the ranked M5; `_nax` prefill kernels are not
  selected here.

**Submitted surface touched:** `Sources/MLXFastModel/LagunaRuntimeModel.swift` only.

**Research-only files (not submitted, not in `editablePaths`):**

| file | purpose |
|---|---|
| `research/maple-tanjiro-r100-epilogue-report.md` | this note |
| `research/tanjiro-r100b-session-factor.py` | Part 1 session-factor distribution, autocorrelation, probability tables |
| `research/tanjiro-r100b-commonmode-lottery.py` | Part 1 common-mode cancellation bands, Arm F/R paired receipts |
| `research/tanjiro-r100b-baseline-reuse.py` | Part 1 test of whether the pinned baseline is re-measured per receipt |
| `research/tanjiro-r100b-equiv-base.sh` | runs the equivalence oracle against unchanged base source |
| `research/tanjiro-r100b-census.sh` | anchors the r85-C ABBA census driver on the r100-B base |

---

# Part 1 — The session factor is not what we thought it was

## 1.0 Headline, in one paragraph

`session_factor = officialScore / cs` is **not** a noisy multiplier applied to a
candidate. It is an **exact, closed-form function of the session's own measured
baseline and nothing else**. I verified the identity

```
session_factor ≡ (baseline_decode_s_per_tok / 0.013855009542)^0.75
               · (baseline_prefill_s_per_tok / 0.000372473193)^0.25
```

against all **1185** receipts in `research/r93-runs/receipts-latest.json` with a
worst relative error of **4.885e-15** — floating-point exact. The lottery we
have been calling "session noise" is precisely and only **the draw on the
pinned baseline's re-measurement**, and it is dominated by the *prefill*
baseline even though prefill carries a quarter of the score weight. The record
holder did not write better code than us; they drew a **+1.63 %** baseline.

## 1.1 Corpus

`research/r93-runs/receipts-latest.json`, n = **1185**, window
`2026-07-24T07:24:49Z … 2026-08-09T05:05:16Z`, **1038 rejected / 147 accepted**.
All 1185 commit SHAs are distinct — no candidate is ever resubmitted in this
corpus, so every row is one independent ticket.

Constants (from the `cs` refit validated at 1185/1185, worst rel. err. 3.0e-08):
`MB_D = 0.013855009542`, `MB_P = 0.000372473193`,
record `= 2.61650354381456`.

## 1.2 Distribution of `session_factor` — the σ we have been quoting is too small

`session_factor − 1`, in percent:

| statistic | value |
|---|---|
| n | 1185 |
| mean | **−0.0041 %** |
| **sd** | **0.5393 %** |
| median | −0.1373 % |
| MAD | 0.4133 % (robust sd 0.6127 %) |
| min | −0.9642 % |
| max | **+2.1135 %** |
| range | 3.0777 % |
| skew | **+0.530** |
| excess kurtosis | **−0.610** |

Quantiles (%): p0.1 −0.9487 · p1 −0.7772 · p5 −0.6868 · p25 −0.4716 ·
p50 −0.1373 · p75 +0.4280 · p95 +0.9241 · p99 +1.2733 · p99.9 +1.8931.

**The advisor's σ = 0.452 % is ~19 % too small.** The true draw-to-draw sd is
**0.5393 %**. That is the opposite of the advisor's prior — the σ measured
across 12 different-code scores did *not* overstate session variance, it
**understated** it, because those 12 scores were mostly our own tightly-clustered
candidates and the merit spread among them was smaller than the session spread.

The shape is also wrong for a normal. It is **right-skewed and platykurtic**:
a compressed left side (min only −0.96 %) with a long right tail (max +2.11 %).
That asymmetry is exactly the wrong shape for the pessimistic reading and the
right shape for us — the tail we need is the fat one.

Upper tail, empirical vs normal(0, 0.5393 %):

| threshold | empirical | normal |
|---|---|---|
| > 1σ | 19.662 % | 15.866 % |
| > 1.5σ | 8.270 % | 6.681 % |
| > 2σ | 1.857 % | 2.275 % |
| > 2.5σ | 0.675 % | 0.621 % |
| > 3σ | **0.253 %** | 0.135 % |

The empirical > 3σ mass is **1.9× the normal prediction**. That matters, because
the current frontier needs a ~+2.95σ draw.

## 1.3 Autocorrelation — there is nothing to time

| lag | r |
|---|---|
| 1 | **−0.0173** |
| 2 | +0.0524 |
| 5 | +0.0504 |
| 10 | +0.0535 |
| 25 | +0.0353 |
| 50 | +0.0337 |

2/√n = 0.0581, so **no lag is significant**. Restricting to consecutive pairs
from the same solver (1108 pairs) gives r₁ = **−0.0343** — still nothing.

Burst structure (blocks of receipts separated by less than a gap threshold):

| gap | blocks | blocks n≥3 | within-block sd | between-block sd |
|---|---|---|---|---|
| < 10 min | 708 | 23 | **0.4537 %** | 0.2097 % |
| < 30 min | 120 | 42 | **0.5076 %** | 0.2634 % |
| < 60 min | 47 | 24 | **0.5110 %** | 0.1759 % |

**Almost all the variance is within-burst.** Two receipts submitted a minute
apart are nearly as different as two receipts submitted two weeks apart. This
is a strong, clean result and it has a direct operational consequence:

> **Salted resubmission inside a short window loses essentially nothing.** The
> i.i.d. model is not merely adequate, it is *accurate*. Our resubmission
> cadence was not mispriced by autocorrelation.

Time-of-day (UTC hour) means all sit inside [−0.147 %, +0.134 %] with per-hour
sd 0.436–0.660 %. **There is no hour-of-day edge to exploit.**

There *is* a mild day-level drift: daily mean `session_factor` ran
−0.2306 % (Jul 24) → +0.1869 % (Aug 4) → −0.1099 % (Aug 9), ≈0.4 % peak to
trough. It is small relative to 0.54 % and not forecastable at submission time.

⚠️ **Confound to record:** corr(`cs`, `session_factor`) over the whole corpus is
**+0.1367**, and the top-100-`cs` receipts average +0.0720 % against a corpus
mean of −0.0041 %. This is a **time confound**, not a dependency: merit and the
daily luck term both trended up over the window. Do not read it as "better code
gets luckier".

## 1.4 Why the lottery exists at all — the baseline is re-measured every time

This is the mechanism, and it was worth checking rather than assuming.

- `baseline_decode_s/tok`: **1182 / 1185 distinct** (99.7 %)
- `baseline_prefill_s/tok`: **1184 / 1185 distinct** (99.9 %)
- **0 of 1184 adjacent receipt pairs share either baseline value.**
- The 3 (decode) and 1 (prefill) coincidental repeats are separated by a median
  of 4657.6 and 14511.7 minutes respectively — collisions, not reuse.

⇒ **1.00 receipts per independent baseline draw.** Every submission buys its own
ticket. Nothing is shared, batched, or cached across submissions.

## 1.5 The lottery is a *prefill*-baseline lottery

Re-measurement noise of the *pinned, fixed* baseline code across the corpus:

| axis | sd | min | max |
|---|---|---|---|
| `baseline_decode_s/tok` | **0.2453 %** | −0.536 % | +1.387 % |
| `baseline_prefill_s/tok` | **1.9451 %** | −2.720 % | **+6.488 %** |

The prefill baseline is **7.9× noisier in raw terms**. After the score weights:

| term | sd contribution |
|---|---|
| 0.75-weighted decode | 0.1839 % |
| 0.25-weighted prefill | **0.4845 %** |
| corr(decode term, prefill term) | +0.1245 |

**The prefill baseline draw contributes 2.6× more score variance than the decode
baseline draw despite carrying a quarter of the weight.** The right-skew in
`session_factor` is inherited directly from the prefill baseline's +6.49 % right
tail. Every lottery ticket we buy is, in effect, a bet that the harness measures
the baseline's 512-token prefill slowly.

This also explains why a slow session is *good* for us: `session_factor` rises
when the **baseline** is slow, and the candidate's own slowness is already
divided out inside `cs`. Common-mode cancellation is what limits it (§1.6).

## 1.6 Common-mode cancellation is real but weak

If candidate and baseline were perfectly correlated within a session, the
lottery would not exist. Measured, in bands of `cs` (so merit spread is small):

| band | n | sd(`cs`) | sd(sf) | sd(score) observed | independent prediction | ratio | corr(`cs`, sf) |
|---|---|---|---|---|---|---|---|
| [2.54, 2.60] | 94 | 0.4390 % | 0.5749 % | **0.6321 %** | 0.7234 % | **0.874** | −0.2449 |
| [2.50, 2.62] | 184 | — | — | — | — | 0.976 | −0.0658 |
| [2.40, 2.70] | 557 | — | — | — | — | 1.004 | +0.0132 |

corr(bl_dec, cand_dec) = +0.1929; corr(bl_pre, cand_pre) = +0.1432 in the tight
band. Adjacent same-solver same-day pairs (n = 163):
corr(Δbl_dec, Δcand_dec) = **−0.0395**; corr(Δbl_pre, Δcand_pre) = **+0.0628**.

⚠️ **Caveat I am obliged to state:** banding on `cs` *manufactures* part of the
negative corr(`cs`, sf), because a slow session inflates the candidate timings
and therefore lowers `cs`. The direction is right, the magnitude is an **upper
bound** on cancellation. The honest summary is that cancellation removes at most
~13 % of the variance in the tight band and nothing measurable in wider bands.

**Consequence:** the baseline and the candidate are measured close together in
time but they are *not* measured under a shared session multiplier. There is no
"quiet host" that helps both. The ticket is close to a fair, independent draw.

## 1.7 The record was a draw, not a solver

| field | value |
|---|---|
| receipt id | **`cc6ddc12`** |
| solver | `a-github-name` |
| timestamp | 2026-08-08T09:17:33Z |
| official score | **2.61650354381456** |
| **merit `cs`** | **2.574594** |
| **`session_factor`** | **+1.6278 %** (z = **+3.026**) |

**The record holder's merit is below our current promoted frontier's merit**
(2.575633). We are ahead on code and behind on luck. The record is a +3σ draw on
the 2nd-percentile-from-top of the empirical `session_factor` distribution.

A related selection effect worth naming: accepted receipts average
`session_factor` **+0.3506 %** (sd 0.6020, n = 147) against rejected
**−0.0543 %** (sd 0.5106, n = 1038). **Leaderboard acceptance is itself partly a
luck filter.** Every promoted frontier in this challenge is upward-biased on
session luck and therefore *worse code than its score suggests*. That is the
statistical statement of exactly the phenomenon #541 discovered by census.

## 1.8 The table the assignment asked for

For merit `cs`, the record falls when `session_factor ≥ 2.61650354381456 / cs`.

**Per-draw probability:**

| scenario | `cs` | required sf | z | normal(σ=0.5393 %) | **empirical** |
|---|---|---|---|---|---|
| current frontier | 2.575633 | 1.015868 | +2.950 | 0.159 % | **0.422 % (5/1185)** |
| + epilogue restore only (Part 3) | 2.581709 | 1.013478 | +2.507 | 0.609 % | **0.675 % (8/1185)** |
| + all three reverted wins | 2.585935 | 1.011821 | +2.199 | 1.393 % | **1.350 % (16/1185)** |
| restored to our best `25e1f18e` | 2.590559 | 1.010015 | +1.864 | 3.113 % | **3.291 % (39/1185)** |
| our best + 0.5 % new merit | 2.603512 | 1.004990 | +0.933 | 17.547 % | **21.350 % (253/1185)** |

Merit levels: `+0.236 %` is the un-ratioed r85-C price (§2.1); `+0.40 %` is all
three reverted wins at the *conservative* ratioed reading, deliberately chosen
so the middle row is not optimistic.

**Against the advisor's σ = 0.452 % normal model:** current frontier 0.022 %
(**19× understated**), restored-to-best 1.335 % (2.4× understated), best+0.5 %
12.6 %. Every single one of the advisor's numbers is too pessimistic, and the
error is worst exactly where the decision is hardest.

**Cumulative P(at least one record-beating receipt in k draws), empirical:**

| merit `cs` | k=1 | k=2 | k=3 | k=5 | k=10 | k=20 | E[draws] |
|---|---|---|---|---|---|---|---|
| 2.575633 frontier | 0.42 % | 0.84 % | 1.26 % | 2.09 % | 4.14 % | 8.11 % | **237.0** |
| + r85-C epilogue | 0.68 % | 1.35 % | 2.01 % | 3.33 % | 6.55 % | 12.67 % | **148.1** |
| + all three reverted | 1.35 % | 2.68 % | 4.00 % | 6.57 % | 12.71 % | 23.81 % | **74.1** |
| best 2.590559 | 3.29 % | 6.47 % | 9.55 % | **15.41 %** | 28.44 % | 48.79 % | **30.4** |
| best + 0.5 % | 21.35 % | 38.14 % | 51.35 % | 69.91 % | 90.94 % | 99.18 % | **4.7** |

**Inverse question — what merit buys what per-draw probability (empirical):**

| target P/draw | required `cs` | over frontier |
|---|---|---|
| 1 % | 2.583066 | +0.289 % |
| 2 % | 2.588790 | +0.511 % |
| 5 % | 2.592546 | +0.657 % |
| 10 % | 2.596914 | +0.826 % |
| 25 % | 2.605353 | +1.154 % |
| 50 % | 2.620101 | +1.726 % |

The best draw ever observed (`sf` = +2.1135 %) would carry a merit of
**`cs` = 2.562349** to the record. Nothing below that can ever win, at any
number of draws, on this distribution.

## 1.9 Recommendation — is resubmission a rational use of a receipt?

**No, at the current frontier. Yes, once we are back to ≈2.586, and clearly yes
at 2.5906.** The programme's receipt budget is a handful per student per round,
not 237.

| merit | verdict |
|---|---|
| **2.5756 (frontier today)** | **Do not buy lottery tickets.** E[draws] = 237. A 5-receipt round buys 2.1 % — you would spend the whole campaign's budget on a 1-in-12 shot. Spend receipts only to *certify merit*, never to fish. |
| **2.5817 (Part 3 lands)** | Still no. E[draws] = 148. |
| **2.5859 (all three reverted wins back)** | Marginal. E[draws] = 74; 5 receipts = 6.6 %. Worth one receipt *if* it is also doing certification duty. |
| **2.5906 (our best ever)** | **Yes.** 3.29 %/draw, 5 draws = 15.4 %. At this merit the lottery is a genuinely positive-value use of a receipt, and it is the cheapest 15 % we can buy. |
| **2.6035 (best + 0.5 %)** | Emphatically. 21.4 %/draw; 3 draws is better than even money. |

Three further consequences I want on the record:

1. **The merit gap is the whole game and it is smaller than we feared.** We are
   *already* +0.04 % ahead of the record holder's code. The re-port programme
   (#555 + #539 + the router arm) is worth ~+0.4–0.5 % of merit, which moves us
   from 237 expected draws to ~30. **That is a 7.8× improvement in receipt
   efficiency, and it is code we already wrote and already proved correct.**
   No new invention has a remotely comparable expected value per hour.
2. **Sequence the receipts after the merit, not alongside it.** Because there is
   no autocorrelation (§1.3) and the baseline is redrawn every time (§1.4),
   a receipt spent today at 2.5756 has 1/7.8 of the value of the same receipt
   spent after the re-ports land. Receipts do not expire; merit does not decay.
   **Hoard receipts through the re-port rounds.**
3. **Never split a genuine win to fit a band.** Confirmed by §1.5: the ticket's
   value is convex in merit over the region we occupy (0.42 → 3.29 % for
   +0.58 % of merit is a 7.8× multiplier on 0.58 %), so bundling merit into one
   submission dominates spreading it.

**On the negative-result branch the advisor pre-registered:** it did not
happen. σ is *larger* than 0.45 %, and the right tail is *fatter* than normal
(1.9× at 3σ). The record is reachable by draws — but only at ~2.59 merit, not
at 2.5756. So the answer to "should we stop spending receipts on lottery
tickets entirely" is: **yes for now, no after the re-ports**.

---

# Part 2 — The reversion ledger, closed properly

## 2.1 One unit convention: **un-ratioed**, and the ×0.595 is refuted

### What the two conventions actually are

The campaign conversion **0.015280 % of score per µs/step of decode** is
**M5-referenced**: 1 % of `cs` = 65.67 µs/step at the current operating point,
and 0.75 × (1/4893.7 µs) = 0.01533 %/µs — the M5 candidate decode time is
4893.7 µs/token. So an M4-measured µs/step delta has to be transported to the
M5 before that conversion can be applied, and there are exactly two ways:

- **(a) ratioed** — the mechanism costs the same *fraction of a step* on both
  machines. Multiply M4 µs by 4893.7/8223 = **0.595**, then apply 0.015280.
  This is what #541 §4.1 did for the router term.
- **(b) un-ratioed** — the mechanism costs the same *absolute microseconds* on
  both machines. Apply 0.015280 to M4 µs directly. This is what r85-C's
  0.2358 % and r96-a's 0.13 % already are.

#541 mixed them. That is the defect.

### The evidence decides it, and it decides against (a)

The only paired cross-machine datum in the campaign is #541's own:
M4 common-mode-corrected census excess **+20.17 µs/step**, M5 paired receipt
delta **+31.54 µs/step** (`NOTE:595`). Ratio **1.56**, M5 *larger*.

- (a) predicts M5 = 20.17 × 0.595 = **12.00 µs**. Observed 31.54. Wrong by 2.63×.
- (b) predicts M5 = **20.17 µs**. Observed 31.54. Wrong by 1.56×.

Moreover the M4 census is **blind to r96-a by construction** (§4.2 of #541: its
636.0 anchor is pre-r96-a and already 2-deep) and blind to the prefill term, so
+20.17 is an *underestimate of the same quantity* that M5 measures as +31.54.
Correcting for that pushes the true µs-scaling **down** toward 1.0. The honest
bracket is therefore

> **M4 → M5 absolute-µs scaling ∈ [1.00, 1.56]. 0.595 is excluded by the data.**

**I adopt (b), un-ratioed, scaling = 1.00**, for three reasons:

1. It is inside the measured bracket; 0.595 is not.
2. It is the **conservative** end of that bracket — using 1.00 when the point
   estimate is 1.56 understates the prize, which is the correct direction of
   error for a re-port decision.
3. It has a physical story. These decode kernels run at batch 1 with fixed
   threadgroup geometry (sliding 32 TGs, full 24 TGs, 1024 threads each) and are
   latency/occupancy-bound, not throughput-bound — attention's unique K+V is
   89.1 MB/step at ≈228 GB/s against a 546 GB/s roofline. A serialized
   threadgroup-memory epilogue costs a dependency chain, and dependency chains
   do not shrink with core count. If anything a **wider** M5 leaves more cores
   idle behind the same 32-threadgroup launch, which is a mechanism for the
   observed ratio being *above* 1.

### All three prices restated in the chosen convention

| # | mechanism | M4 µs/step | ×1.00 | **score %** |
|---|---|---|---|---|
| 1 | r85-C float4 merge epilogue (both decode attn kernels) | −15.43 [−22.04, −8.82] | −15.43 | **0.2358 %** [0.1348, 0.3368] |
| 2 | r96-a 4-deep sliding software pipeline | −8.25 | −8.25 | **0.1261 %** |
| 3 | `DARKBLOOM_ROUTER_WEIGHT_PREFETCH` `_pf1` | −6.91 (z = 4.4) | −6.91 | **0.1056 %** |
| | **total** | **−30.59** | | **0.4675 %** |

(#541 published 0.4286 % by pricing row 3 ratioed and rows 1–2 un-ratioed.
All-ratioed would give 0.2781 %.)

### Reconciliation against the M5-measured 0.5286 %

| convention | attributed | residual vs 0.5286 % | attribution closes to |
|---|---|---|---|
| all-ratioed (×0.595) | 0.2781 % | 0.2505 % | **52.6 %** |
| #541 as published (mixed) | 0.4286 % | 0.1000 % | 81.1 % |
| **all-un-ratioed (chosen)** | **0.4675 %** | **0.0611 %** | **88.4 %** |

The exact-closure scaling is 0.5286/0.4675 = **1.131** — inside the [1.00, 1.56]
bracket, close to 1, and nowhere near 0.595. **Choosing (b) is the convention
that both survives the cross-machine datum and closes the ledger best.** That
these two independent criteria agree is the strongest thing I can say for it.

**Residual: +0.0611 % of `cs` (≈4.0 µs/step of M5 decode) is unattributed.**
Candidates, in order of my prior: the prefill-side terms the M4 census cannot
see (the M5 split has prefill at +0.1929 % raw → +0.0482 % weighted, which alone
covers most of it), then a fourth dropped change, then M4-census bias.

## 2.2 Provenance column — the split is *inferred*, not M5-measured

Stated in the ledger table itself (§2.4), not only in prose:

- r85-C was **never submitted** (`research/maple-r85-c-epilogue-result.md:190-191`,
  `:319`, `:384-389`). Its 0.2358 % is an **M4 paired-ABBA per-kernel census**
  price, n = 8 duplexes, converted to score with the M5 conversion. It is
  **inferred at M5**.
- r96-a's 0.13 % is **carried** from its own arm's M4 measurements
  (runs `uajdq8yu`, `ehbvlnva`, `pe8zt12k`, `skkt1pyq`, `zvycfimy`).
- The router term's 6.91 µs/step at z = 4.4 is **measured on M4** in #541's own
  census.
- Only the **total** 0.5286 % is M5-measured, and only as a *paired difference
  of two receipts in two different sessions*.

None of the three per-mechanism rows has ever been isolated on an M5.

## 2.3 Four corrections to the record

### (a) The headline must say what the 636.0 anchor is

**Old headline:** "Prediction CONFIRMED — `sliding_fused_attn_ring_v1` moved off
636.0 by +12.67 µs/step, z = 4.0."

**Corrected headline:** *The **number** was confirmed; the **mechanism** in the
prediction was not.* The 636.0 anchor traces to
`research/maple-nezuko-r92-barrier-hoist-generalization.md:81`, whose base was
`d549d318` — **pre-r96-a, and therefore already a 2-deep ring**. The +12.67
µs/step excess is measured *against a 2-deep ring*, so **it cannot be the price
of losing r96-a's 4-deep pipeline; that loss is invisible in this census by
construction.** What +12.67 does identify — via the four-kernel sign
fingerprint (§4.3 of #541) — is the loss of the **r85-C float4 merge epilogue**.
#541's body says this at `:267` and `:523`; its headline did not.

### (b) The census "old" column is hard-coded literature, not a paired ABBA

`research/tanjiro-r99d-commonmode.py:24-50` is a **hand-transcribed table** from
`research/maple-frieren-r94-decode-residue-ledger.md:115`. It is:

- a **different session**, a **different base** (`d549d318`), and a different day
  from the "new" column;
- corrected only by a **median per-kernel ratio** common mode over kernels with
  old ≥ 50 µs/step, with scale = normalised MAD of that same set;
- **not** a paired ABBA and **not** an in-session control.

Host for both columns: **Apple M4 Pro, 20 GPU cores, Apple GPU generation 16**,
SPLIT = 1 instrumentation. Recording that here because until now it existed only
in the `.py` header. A cross-session, cross-base, median-corrected comparison is
adequate to *fingerprint* a four-kernel sign pattern; it is **not** adequate to
price a single kernel to better than tens of percent. **This round's census
(Part 3) is the paired, same-session, matched-anchor instrument that #541
lacked** — see `NOTE:611-612`, which asked for exactly this.

### (c) `commonmode.py:23` vs the docstring — the docstring is right

`research/tanjiro-r99d-commonmode.py:23` reads
`# label -> us/step, SPLIT=1, base e510bb3d (r94 ledger table)`.
The module docstring (`:3-6`) and §4.2 of #541 both say **`d549d318`**, and §4.2
proves it from the MSL source hash (`d549d318` ≡ `9d9da08^`, 431 lines,
`fad5dc8345d7`, 2-deep; `e510bb3d` ≡ `9d9da08`, 519 lines, `1327d3939ef6`,
4-deep). Since the census's sliding value 636.0 is a **2-deep** measurement, the
`:23` comment is the wrong one. **The OLD dict is base `d549d318`.** I am not
editing the r99-D script (it is another PR's artifact) — the correction is
recorded here and in §2.4's ledger.

### (d) "Exactly four kernels moved" was a magnitude rule, not a z rule

The rule actually used was **magnitude-first**: kernels whose absolute excess
was large enough to matter to the score. Under a **strict z rule** the census
flags **five**, and the extra one is instructive:

- `argmax_bfloat16` — **z = 11.8, the largest z in the census — but only
  +0.55 µs/step.** A 9.0 µs/step kernel with tiny variance; statistically
  overwhelming, economically irrelevant (0.008 % of score).
- `gate_sp_h48_v1` — z = −2.3, borderline either way.

Both rules select the same four *economically*. State the rule as: **"the
kernels whose excess exceeds 1 µs/step AND |z| ≥ 2"**, which yields the four.

Separately, and more importantly: **the delivered σ = 0.491 % is a cross-kernel
robust MAD** (the normalised MAD of the per-kernel new/old ratio distribution),
**not** the preregistered per-kernel pooled σ = 3.34 µs/step. #541 computes
12.67/3.34 = 3.8σ against the preregistered σ and quotes 0.491 % elsewhere; the
two are different statistics measuring different things and must not be
interchanged. The conclusion survives on either.

## 2.4 The consumable ledger

Convention: **un-ratioed** (§2.1). Score % = 0.015280 × M4 µs/step.
`cs` today = 2.575633; record = 2.61650354381456.

| # | mechanism | OLD anchor | NEW anchor (HEAD) | byte delta to restore | M4 µs/step | **score % (un-ratioed)** | provenance | owner / status |
|---|---|---|---|---|---|---|---|---|
| 1 | **r85-C float4 merge epilogue**, both decode attn kernels | `e510bb3d` / `74e89d7`; PR #205 commit `1aad492f`; `float4 outputs4` ×2 | HEAD `float4 outputs4` ×0; scratch decls `LRM:1513`, `:1970` | **−454 B** (byte-**negative**) | −15.43 [−22.04, −8.82] | **0.2358 %** [0.1348, 0.3368] | **inferred at M5** — M4 paired ABBA n=8 (`maple-r85-c-epilogue-result.md:206-215`, W&B `5bj4wjcr`); never submitted | **maple-tanjiro, #555 — DONE, this PR** |
| 2 | **r96-a 4-deep sliding software pipeline** | `e510bb3d` `LRM:1640-1818` (8,058 B), `pipe_ka/kb/kc/kd` `:1651-1654`; MSL 519 lines `1327d3939ef6` | HEAD `LRM:1548-1638` (3,972 B); MSL 2-deep, third variant `3542134ce2fe` | **+4,086 B** | −8.25 | **0.1261 %** | **carried** — r96-a's own M4 arms (`uajdq8yu`, `ehbvlnva`, `pe8zt12k`, `skkt1pyq`, `zvycfimy`); invisible to the r99-D census by construction | frieren, #539 |
| 3 | **`DARKBLOOM_ROUTER_WEIGHT_PREFETCH` `_pf1`** | `e510bb3d` `LRM:686-705`, `:877-929`, `:936-954`; plumbing `:1125-1134`, `:1220-1225`; label `…_pf1` | absent at HEAD; `lagunaResidualRMSNormRouterSource(rowsPerGroup:)` | **≈+5.5–6 kB** | −6.91 (z = 4.4) | **0.1056 %** | **measured on M4** (#541 census, label diff `…_pf1` → `…`) | queued behind #539 |
| | **total** | | | **≈+9.1–9.6 kB** | **−30.59** | **0.4675 %** | 88.4 % of the M5-measured 0.5286 % | |

Budget: at this base `LagunaRuntimeModel.swift` is 511,418 / 524,288 ⇒ **12,870 B
per-file headroom**, and the global surface has **16,151 B**. My Part 3 is
−454 B, so after it lands the headroom is **13,324 B / 16,605 B** and rows 2+3
need ≈9.6–10.1 kB. **Feasible, with ~3.2 kB per-file slack**; nezuko's #548
reclamation remains the margin.

Merit if all three land: **2.575633 × 1.004675 = 2.587675**, i.e. per-draw
record probability rises from **0.42 % to ≈1.6 %** (empirical), E[draws]
237 → **≈63**.

## 2.5 Standing rule — post-adoption re-port audit

> **Rule 74 (proposed, adopted from #541 `NOTE:550-554`).** *Every organizer
> frontier adoption must be followed by a mechanical re-port audit of our own
> landed kernel wins, and that audit must complete before any fresh optimization
> arm is assigned on the new base.* An organizer frontier is a **replacement**
> of the editable surface, not a merge; it silently drops every kernel-level win
> we have landed, and a census is a slow and expensive way to rediscover that.

**Executable procedure** (run by whoever adopts the frontier, on the adoption
commit, before assigning anything):

```bash
OLD=<our pre-adoption frontier sha>
NEW=<the adoption commit sha>
SRC=Sources/MLXFastModel/LagunaRuntimeModel.swift

# 1. Kernel-source hash diff.  For every `MLXFast.metalKernel(` site, extract the
#    source from the kernel-name line to the next such site and hash it.
for REF in "$OLD" "$NEW"; do
  git show "$REF:$SRC" | awk '
    /MLXFast\.metalKernel\(/ {n++} {print n"\t"$0}' \
  | awk -F'\t' '{h[$1]=h[$1]$2"\n"} END{for(k in h) print k, length(h[k])}' \
  | sort -n > "/tmp/kernels.$REF.txt"
done
diff /tmp/kernels.$OLD.txt /tmp/kernels.$NEW.txt

# 2. DARKBLOOM_* flag-set diff — a dropped env flag is a dropped mechanism.
for REF in "$OLD" "$NEW"; do
  git show "$REF:$SRC" | grep -o 'DARKBLOOM_[A-Z0-9_]*' | sort -u \
    > "/tmp/flags.$REF.txt"
done
comm -23 /tmp/flags.$OLD.txt /tmp/flags.$NEW.txt   # flags we LOST

# 3. Arm-suffix diff — kernel labels encode arms (`_pf1`, `_lm1`, `_sd1`, …).
#    A label that lost a suffix is a mechanism that lost its plumbing.
for REF in "$OLD" "$NEW"; do
  git show "$REF:$SRC" | grep -oE '"[a-z0-9_]*(_pf[0-9]|_lm[0-9]|_sd[0-9]|_se[0-9]|_sc[0-9]|_v[0-9]+)"' \
    | sort -u > "/tmp/labels.$REF.txt"
done
comm -23 /tmp/labels.$OLD.txt /tmp/labels.$NEW.txt

# 4. Structural markers for known mechanisms.
for REF in "$OLD" "$NEW"; do
  echo -n "$REF float4-outputs4=";  git show "$REF:$SRC" | grep -c 'float4 outputs4'
  echo -n "$REF pipe_kd=";          git show "$REF:$SRC" | grep -c 'pipe_kd'
done
```

Output: one table of *mechanisms present in OLD and absent in NEW*, each with a
byte cost to restore and its last measured price. Anything on that table is a
re-port arm and outranks any new invention of the same estimated size, because
its correctness history is already established.

**Corollary (rule 74a):** an adoption PR that has not run this audit is not
"adopted", it is "pending audit", and `CURRENT_RESEARCH_STATE.md` should say so.
#541 found a **third** lost mechanism — the largest of the three — that the
state file did not list, purely because no such audit existed.

## 2.6 Rule 68 rescored — and re-based

**Rule 68 (#527):** removing 78 prefill dispatches made M5 prefill **+0.639 ms
slower**, not faster. Two explanations survived:

- **(a) SLC-capacity crossing** — the fused form's working set crosses an SLC
  capacity boundary that the unfused form does not.
- **(b) Lost inter-dispatch read-after-read overlap** — MLX never hazard-tracks
  read-after-read (`Vendor/mlx-swift/.../backend/metal/device.cpp:547-548`), so
  consecutive dispatches that only read the same weights overlap freely; fusing
  them into one dispatch serialises what the driver was overlapping.

**The residual they must explain has changed twice, and the second change is the
one that matters.**

First: the un-ratioed ledger (§2.1) attributes 0.4675 % of the 1.0498 % deficit,
leaving **0.582 %** — at the low end of the advisor's ≈0.6–0.7 %.

Second, and this supersedes it: **Part 1 shows the 1.0498 % deficit is not a
merit deficit at all.** On the common-baseline scale our frontier sits at
`cs` 2.575633 against the record holder's own code at 2.574594 — we are
**+0.0404 % ahead**. The entire 1.0498 % is the record's **+1.6278 % session
draw** (§1.7). So:

> **There is no unexplained merit residual against the record for rule 68 to
> explain.** The only real merit residual in the ledger is the **+0.0611 %**
> that the three re-ports leave against our own Arm R (§2.1).

Rescoring both explanations against **0.0611 %**, not 0.6–0.7 % and certainly
not 1.05 %:

| explanation | still alive? | worth a receipt? |
|---|---|---|
| (a) SLC-capacity crossing | Yes, untested. But it is a *prefill* story, and prefill carries 0.25 weight. The whole unattributed residual is 0.0611 % of score; even if (a) explained all of it and were fully recoverable it is **1/4 of one re-port row**. | **No.** |
| (b) Lost inter-dispatch read-after-read overlap | Yes, and it remains the more interesting one because it is a *general* claim about MLX dispatch that would inform many arms, not a one-off. Still untested at dispatch-boundary scale. | **Not for the residual.** Possibly later as *methodology*, funded by a different arm. |

**Verdict on the `[Wk;Wv]`-only discriminator: do not assign it.** It was
justified by a 1.05 % unexplained gap. That gap does not exist. Its
opportunity cost is now measured against a re-port row worth 0.11–0.24 % with a
known correctness history, and it loses on every axis: smaller prize, higher
risk, no prior measurement, prefill-weighted. **Park it.** If it is ever
revived it should be revived as a *methodological* experiment about MLX
dispatch overlap, priced on what it teaches, not on 1.05 % of score.

Third-order note, but it is the reason I am confident: Part 1 §1.5 shows the
prefill **baseline** is 7.9× noisier than the decode baseline. Any prefill-side
merit experiment on the M5 has to fight a 1.95 % re-measurement sd on its own
control. Prefill merit work is the most expensive evidence per receipt in this
challenge. That is an independent argument for deprioritising both survivors.

## 2.7 The two cheap reads

### (a) `research/maple-r85-c-epilogue-result.md:384-392` — the geometry caveat

The caveat is the standing campaign rule that **threadgroup geometry changes can
flip sign across core counts**, so an M4 result about a geometry change is not
evidence for the M5. The rebuttal, at `:390-391`, is specific and I restate it
because I am relying on it:

> *"threadgroup geometry is unchanged, so the usual core-count sign-flip risk
> does not apply here."*

I verified this at source level for my own port (Part 3 §3.5): threads per
threadgroup, threadgroup count, simdgroups per threadgroup, q-heads per
threadgroup, and total threadgroup bytes are **all identical before and after**.
The change is purely the *width of each threadgroup-memory access* (float4 vs
scalar) and the grouping of two serialized combine rounds. Neither is a geometry
change. **M4 is directionally admissible for this mechanism** — unlike the
`_nax` prefill work, where the M4 does not even select the kernel family.

### (b) `research/r91b-runs/receipt-armR.json` — Arm R's composition, and an M5 A/B

This read had the largest payoff of anything in Part 2, and it also **found a
transcription error in my own earlier ledger**: Arm F's `baseline_prefill_s/tok`
had been recorded as Arm R's. Corrected from the JSONs directly:

| field | **Arm R** (epilogue) | **Arm F** (no epilogue) |
|---|---|---|
| file | `research/r91b-runs/receipt-armR.json` | `research/r91b-runs/receipt-armF.json` |
| createdAt | 2026-08-09T00:58:27.946Z | 2026-08-09T01:32:34.888Z |
| timestamp | 2026-08-09T01:07:57Z | 2026-08-09T01:40:30Z |
| **officialScore** | **2.5804768841155** | **2.5907768487015** |
| baseline decode s/tok | 0.01384702115625 | 0.013863095703125 |
| baseline prefill s/tok | 0.00036804638671875 | **0.0003729877109375** |
| decode s/tok | 0.0048937119140625 | 0.0048989290390625 |
| prefill s/tok | 0.000188042724609375 | 0.000187608154296875 |
| decode_speedup | 2.8295538028013865 | 2.829821700331866 |
| prefill_speedup | 1.9572487448440257 | 1.9881209979139636 |
| floors | both passed | both passed |
| status | rejected | rejected |
| GPQA TTFT (s) | 0.41 (p50 0.078, max 2.4) | 0.41 (p50 0.079, max 2.3) |
| **derived `cs`** | **2.589321** | **2.588750** |
| **`session_factor`** | **−0.3416 %** | **+0.0783 %** |
| baseline vs pinned | dec −0.0577 %, **pre −1.1885 %** | dec +0.0584 %, pre +0.1381 % |

**Arm R's composition** (verified from the arm's own note): organizer frontier
`6ada66c9` + PR #457's r85-C float4 merge epilogue (`3217f111`) + the inert
source carve (PR #456). It did **not** carry r96-a's 4-deep sliding pipeline
(PR #60, closed) and did **not** carry `DARKBLOOM_ROUTER_WEIGHT_PREFETCH`
(PR #475 = Arm C, cancelled).

**So the answer to the advisor's question is: no — Arm R carried only mechanism
#1 of the three.** The 0.4675 % total does **not** become M5-bracketed. But the
read pays off differently and better:

> **Arm R vs Arm F is a direct M5 A/B of exactly the float4 merge epilogue and
> nothing else.** n = 1 vs n = 1, in two different sessions.

| quantity | R − F | reading |
|---|---|---|
| merit `cs` | **+0.02207 %** | right sign; ~1/10 of the M4-predicted 0.2358 % |
| raw decode s/tok | **−0.10650 %** = **−5.217 µs/token** | **right sign**, the axis the epilogue touches |
| raw prefill s/tok | +0.23164 % | wrong sign, but the epilogue is **decode-only by construction** ⇒ pure session noise, usable as a *noise-scale* indicator |
| published officialScore | −0.39756 % | **dominated by the baseline draw, not by merit** — Arm R drew a −1.19 % prefill baseline |

Three conclusions:

1. **The M5 decode delta has the right sign and a plausible magnitude.**
   −5.217 µs/token on M5 against −15.43 µs/step on M4 is a µs-ratio of 0.34 —
   *lower* than the [1.00, 1.56] bracket from §2.1, but this is a single
   unpaired cross-session pair whose own prefill axis moved +0.23 % on a
   mechanism that cannot touch prefill. **The prefill channel tells us the
   session-to-session noise on this comparison is ≈0.23 %, i.e. ≈11 µs/token of
   decode-equivalent — larger than the effect.** So n=1-vs-n=1 cannot resolve
   0.2358 %, and the correct statement is: *sign confirmed, magnitude
   unresolved, consistent with anything in [0, 0.4 %]*.
2. **This is a textbook demonstration of Part 1.** Arm R has **higher merit**
   than Arm F (2.589321 vs 2.588750) and a **lower published score** (2.58048 vs
   2.59078), entirely because Arm R drew a −1.19 % prefill baseline and Arm F
   drew +0.14 %. If we had read the published scores we would have concluded the
   epilogue *hurt*. **Never compare two receipts on `officialScore`.**
3. **The `cs` scale is what makes the epilogue's M5 evidence visible at all.**
   That is a second, independent justification for #541's central instrument.

---

# Part 3 — Re-porting the float4 merge epilogue

## 3.1 Structural verification before editing

The assignment asked me to verify the mechanical facts and stop if the structure
did not match. It matched, with **one correction**:

| claim | verified? | note |
|---|---|---|
| OLD scratch decl `threadgroup float4 outputs4[BN * BDP]` | ✅ | |
| HEAD `threadgroup U outputs[4 * BN * BDP]` at `LRM:1513` (sliding) | ✅ | |
| HEAD same at `LRM:1970` (full) | ✅ (found at `:1950`/`:1953`) | line drift only |
| `float4 outputs4` count: `e510bb3d` = 2, `d549d318` = 2, `74e89d7` = 2, HEAD = 0 | ✅ | |
| epilogue block byte-identical between sliding and full within each ref | ✅ | applied once, twice |
| full kernel's main loop md5-identical across the revert | ✅ | epilogue is its only change |
| epilogue and main loop strictly disjoint | ✅ | no collision with #539 |
| barrier count 3, unchanged | ✅ | 3 → 3 in both kernels |
| serialized combine rounds 2, unchanged | ✅ | 2 → 2 |
| **`simd_sum` count 8, unchanged** | ⚠️ **count is 10, not 8** | **unchanged at 10 → 10 in both kernels.** The invariant (unchanged) holds; the stated value was wrong. |
| threadgroup bytes 16,896, unchanged | ✅ | 16·BN·BDP both sides |
| byte delta −454 B | ✅ | exactly −454 |

## 3.2 The diff

Commit `39056228e71841e3bfc80b8c961605b2e41651c2` —
*"r100-B Part 3: re-port r85-C float4 merge epilogue in both decode attention
kernels"*. One file, one mechanism, separable.

```
 Sources/MLXFastModel/LagunaRuntimeModel.swift | 126 ++--
 1 file changed, 46 insertions(+), 80 deletions(-)
```

**`126 ++--` is byte-for-byte r85-C's original `126 +++---` signature** (6 hunks,
same shape). File size **511,418 → 510,964 = −454 B**, exactly as predicted.

Anchors after the port: `outputs4` at `LRM:1646, 1659, 1670, 1673` (sliding) and
`LRM:2130, 2143, 2154, 2157` (full); scratch decls at `:1513` and `:1950`/`:1953`.

Per-lane traffic in the merge epilogue: **stores 8 → 2, loads 8 → 2** (one
`float4` in place of four scalars, twice).

The only semantic difference is the **round grouping** of the two serialized
combine passes:

- OLD (float4, restored): round 1 = all four planes of head 0.
- NEW (SoA, HEAD): round 1 = planes 0–1 of both heads.

I checked the aliasing hazard in both forms: in each, the second store reads
accumulator slots that the first reduce has not yet overwritten. **No aliasing
hazard in either arrangement.**

## 3.3 Bit-exactness — proven, not assumed

The assignment flagged this as the real risk: the round grouping changes *which
partials are summed in which order within a round*, which is exactly the class
of change that silently perturbs floating point.

### Upstream equivalence oracle, candidate

`bash research/run_upstream_equivalence.sh`, job
`760b291f-3208-481c-81fa-ccb17eead729`, 67 s. Test
`lagunaRuntimeMatchesVendoredUpstreamOnM5WhenEnabled` **ran** (report marker
present, so this is not a zero-test invocation). `promptTokenCount: 512`,
`decodeTokenCount: 8`.

| step | max abs logit err | mean abs logit err | runtime tok | upstream tok |
|---|---|---|---|---|
| prefill | 0.125 | 0.011933609 | 5991 | 5991 |
| decode-0 … decode-7 | **0** (all 8) | **0** (all 8) | 509, 902, 5991, 509, 902, 5991, 509, 902 | identical |

`EQUIVALENCE_EXACT_STEPS=8`, `EQUIVALENCE_EXIT=1` (the zero-tolerance assertion
at `LagunaCorrectnessTests.swift:249` fails on the prefill row).
**Every token matched in every step.**

### The prefill 0.125 is a pre-existing host artifact — proven on unchanged base

Per `AGENTS.md` ("If a non-M5 host disagrees with a public golden, test the
unchanged base"), I ran the same oracle on the **unchanged `2aa2f79` source**
via `research/tanjiro-r100b-equiv-base.sh` (job
`c2557a11-54bc-4a35-a165-e9703fd77ef1`, 27 s). Source identity confirmed by
hash: base `md5 5c84a693fd0d1601dad001fd093774e6`, HEAD
`md5 44b899155ffd19cf9eb6474dfefe1165`; the build log recompiled
`LagunaRuntimeModel.swift` (the warning line moved `10653` → `10687`,
confirming a genuinely different source was compiled).

**The unchanged base produces numerically identical output:**

| step | base max / mean | candidate max / mean |
|---|---|---|
| prefill | **0.125 / 0.011933609** | **0.125 / 0.011933609** |
| decode-0…7 | **0 / 0** | **0 / 0** |
| tokens | 5991, 509, 902, 5991, 509, 902, 5991, 509, 902 | identical |

The mean absolute error agrees **to all nine printed digits**. This is the
strongest available statement:

> **Candidate and base produce bit-identical logits at every step, including the
> prefill step. `max_abs_diff(candidate, base) = 0`.** The prefill 0.125 is a
> pre-existing artifact of this M4 Pro host against the vendored oracle, present
> on unchanged base source, and is not caused by the port.

The port lives entirely in the decode attention epilogue, and the decode steps —
the only steps that execute it — are **exactly zero on both**. The round-grouping
hazard the advisor flagged **did not materialise**, which is consistent with the
structural reading: the two rounds reduce *disjoint* accumulator planes, so
regrouping them changes which lane does which addition but never the set of
addends inside any one reduction.

### Token identity across all 16 timed slots

Every one of the 16 census slots (§3.4) reported
**`teacher-forced greedy tokens: 0 divergences (all match)`**, across both arms,
in both orders. That is 16 independent 200-step teacher-forced runs with zero
divergence.

## 3.4 Per-kernel counter census — the primary instrument

Wall clock cannot see this change. §2.1 prices the epilogue at 15.4 µs/step;
the wall channel on this host resolves ±46 µs/step per duplex. The instrument
that *can* see it is the per-kernel GPU counter census, so that is the primary
measurement and the wall is reported only as a consistency check.

### Design

`research/tanjiro-r100b-census.sh` (committed) pins `BASE_SHA` to the r100-B
base `2aa2f79` and drives `research/maple_r85c_epilogue_ab.sh` with
`REPS=4 STEPS=200 ORDER="base cand cand base"`. That is 16 timed slots in four
ABBA quadruples, one unscored warm-up ahead of them, 199 steady steps scored per
slot after dropping step 0.

ABBA rather than A/B because session drift on this host is monotone and large:
`base` slot medians run 9777.7 → 9809.1 µs/step from first to last quadruple.
An unpaired A/B would read that drift as signal. Adjacent pairing differences it
out; alternating the order across quadruples cancels the residual first-order
slope.

Run: job `348a1323-b3cc-4299-a751-e971de032224`, exit 0, 848 s wall.
The driver's own guards all passed — worktree clean at entry, gpuprof hook
applied and reverted, and the two worker executables verified **not**
byte-identical (`binaries.sha256`):

```text
base 567a2be711d9a6b70ba8ecf11390311ea5f0dd3e9e6c5062d5ffb85ca5dc9f2f
cand b653b336169095a1f4941ecab011c46465fc618bc2bf489e873e58880069f608
```

The `cbs_per_step` divisor was **re-verified, not assumed**. Every slot log
reports `cbs=406.0 dispatches=406.0`, so the 406 used by the analyser is this
session's own value:

```text
profile: 89160 command buffers total, 80794 inside 199 steady steps
per steady step: wall=9.788 ms gpu_busy_sum=8.577 ms gpu_busy_union=8.577 ms
                 gap=1.212 ms (12.4% of wall) cbs=406.0 dispatches=406.0
```

### Null controls come first

The ABBA order `base cand cand base` places an identical-code duplex at every
odd boundary, so the same run supplies its own noise floor at no extra cost. I
read those **before** looking at the contrast, so no go/no-go bar was chosen
after seeing the answer.

| channel | null estimate | null per-duplex SD |
|---|---|---|
| per-kernel busy, ratio-adjusted, cand↔cand (n=4) | +0.2 µs/step [−8.9, +9.4] | 5.76 |
| per-kernel busy, ratio-adjusted, base↔base (n=3) | −1.7 µs/step [−27.4, +24.0] | 10.34 |
| per-kernel busy, absolute, cand↔cand (n=4) | +13.9 µs/step [−15.9, +43.8] | 18.73 |
| per-kernel busy, absolute, base↔base (n=3) | −1.1 µs/step [−37.1, +35.1] | 14.54 |
| wall, identical-code (n=7, `tanjiro-r100b-wall-null.py`) | +2.9 µs/step [−13.6, +19.5] | 17.88 |

Two things follow immediately. The ratio-adjusted busy channel is the only one
whose null is tight *and* centred (+0.2 ± 9.4 at n=4). And the wall null spread,
SD 17.88 µs/step per duplex, is larger than the entire effect being hunted —
which is the whole reason this section leads with counters.

### The contrast

`maple_r85_arm_stats.py --steps 200 --cbs-per-step 406 --arms base cand
--offset 0`, n=8 duplexes. Sign is cand − base, so **negative is faster**. The
analyser prints `score:` as the signed busy conversion at 0.015280 %/µs·step, so
a printed `−0.2398%` is a score *improvement* of +0.2398%; I quote improvements
with the sign flipped.

| kernel | r85-C (M4, `#457` base) | **r100-B (M4, `2aa2f79` base)** | null cand↔cand | null base↔base |
|---|---|---|---|---|
| `sliding_fused_attn_ring_v1` | −20.98 [−22.76, −19.19] | **−20.15 [−21.91, −18.39]** \*\*\* | −0.13 [−2.79, +2.53] | +0.24 [−6.64, +7.21] |
| `full_fused_attn_grow_v1` | −5.55 [−6.74, −4.36] | **−5.53 [−6.34, −4.71]** \*\*\* | +0.30 [−1.29, +1.90] | −0.89 [−3.74, +2.00] |
| *touched sum* | −26.53 | **−25.68** | +0.17 | −0.65 |
| `gate_sp_h64_v1` | +8.14 [+7.42, +8.86] | **+7.91 [+7.05, +8.78]** \*\*\* | +0.03 [−1.61, +1.68] | −0.35 [−2.13, +1.45] |
| `shared_..._qmv_rows1_halved_bf16_v1` | +1.55 | **−0.20 [−2.03, +1.64]** | +1.52 [−1.60, +4.68] | +0.37 [−4.65, +5.48] |
| **total, absolute** | −15.43 [−22.04, −8.82], SD 7.92 | **−15.7 [−31.6, +0.3], SD 19.12** | +13.9, SD 18.73 | −1.1, SD 14.54 |
| **total, ratio-adjusted** | — | **−22.6 [−26.9, −18.4], SD 5.10** | +0.2, SD 5.76 | −1.7, SD 10.34 |

Base levels match the r85-C session to 0.2 %: `sliding` 648.1 here vs 649.3
there, `full` 254.7 vs 254.9. The census is looking at the same kernels in the
same state.

**The port reproduces.** Three of r85-C's four flagged kernels come back with
overlapping confidence intervals, and the two touched kernels come back at
96 % and 99.6 % of their original magnitudes. Against the identical-code null
the `sliding` term is 7.2–12.1σ and the `full` term is 4.8–6.2σ. This is not a
marginal call; the assignment's "sliding negative beyond 2σ" gate is cleared by
roughly a factor of four.

### The absolute total is *not* significant, and that is the honest headline

The absolute total is −15.7 µs/step with a 95 % interval of [−31.6, +0.3] — it
grazes zero. Its point estimate lands within 0.3 µs/step of r85-C's −15.43,
which is a striking agreement, but agreement of point estimates is not
significance. Two facts explain the width, and they are different facts:

1. **This session was noisier than r85-C's.** Per-duplex SD on the absolute
   total is 19.12 here against 7.92 there, 2.4×. The absolute-total null
   confirms it is session drift and not the port: cand↔cand nulls read +13.9
   µs/step with SD 18.73, i.e. the null is as wide as the contrast.
2. **42 % of the touched saving is given back to untouched kernels.** Touched
   sum −25.68, total −15.7. `gate_sp_h64_v1` alone takes +7.91 back. r85-C saw
   the same effect at the same size (−26.53 → −15.43, +8.14). Whatever this is
   — and it is reproducible across two sessions, two bases and two builds — it
   is a real property of the change, so it stays in the price.

The ratio-adjusted total removes the common-mode drift that item 1 describes,
and there the effect is unambiguous: **−22.6 µs/step [−26.9, −18.4]** against a
null of +0.2 [−8.9, +9.4]. I do **not** promote that to the headline price,
because r85-C quoted the absolute convention (its −26.53 touched / −15.43 total
pair is only consistent with absolutes) and switching conventions to obtain a
significant number would be exactly the kind of self-serving convention choice
§2.1 was written to stop.

### A correction to the r85-C give-back ledger

`shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1` was carried in r85-C as a
+1.55 µs/step give-back. Here the real contrast puts it at **−0.20
[−2.03, +1.64]** — flat — while the *identical-code* cand↔cand null puts it at
**+1.52 [−1.60, +4.68]**, i.e. the null reproduces r85-C's number better than
the contrast does. That kernel's apparent give-back is a slot-position artifact,
not an effect of the epilogue. It is small enough not to move the price
materially (0.024 % of score), but the ledger should stop attributing it.

This is only visible because the ABBA order supplies same-arm duplexes. An A/B
order would have reported +1.52 as signal in both sessions.

### Wall − busy decomposition

Reporting wall alone would be indefensible here, so
`research/tanjiro-r100b-decompose.py` splits every slot's profile line into its
three channels and pairs them with the same ABBA structure:

| channel | base mean | cand mean | ABBA cand − base | per-duplex SD |
|---|---|---|---|---|
| wall | 9817.6 | 9803.1 | **−14.50 [−53.10, +24.10]** | 46.16 |
| `gpu_busy_sum` | 8581.4 | 8565.8 | **−15.62 [−31.81, +0.56]** | 19.36 |
| `gpu_busy_union` | 8581.0 | 8565.0 | −16.00 [−31.94, −0.06] | 19.06 |
| gap (CPU-side) | 1236.9 | 1238.4 | **+1.50 [−23.89, +26.89]** | 30.37 |

The decomposition is additive and clean: −15.62 busy + 1.50 gap = −14.12,
against a measured wall of −14.50. **All of the wall movement is removed GPU
work; the gap channel is null**, which is what a pure in-kernel epilogue change
must look like. If the gap had moved, the port would have been doing something
other than what it claims.

`gpu_busy_sum` = `gpu_busy_union` to within 1 µs/step in every slot: dispatches
are fully serialised, so there is no concurrency for the change to disturb.

The independent wall estimator (`maple_r85c_epilogue_stats.py`, per-slot medians
rather than the profile's own wall) agrees: **+11.34 µs/step of win**
[−6.31, +29.00], median statistic, n=8 — same sign, same order, and its interval
covers the busy estimate. Its identical-code null is −10.78 [−32.95, +11.35] at
n=4. Wall contrast SD 21.11 vs wall null SD 17.88 (n=7): **the wall channel's
spread is essentially unchanged by the presence of a real 15 µs/step effect.**
That is the quantitative statement of why wall alone is not evidence here, and
it is consistent with r85-C's own n≥52/arm end-to-end power estimate.

### What this measures, and what it does not

Measured on this host: the port removes 15.7 µs/step of GPU busy time
(absolute) or 22.6 µs/step (common-mode-adjusted), reproducing r85-C's
per-kernel signature at 96–99.6 % of magnitude with all four flagged kernels
recovered and one spurious give-back retired.

Not measured: anything about M5. This is an Apple M4 Pro, 20 GPU cores, Apple
GPU generation 16. §2.7(a) discharges the usual core-count sign-flip caveat by
source inspection — threadgroup geometry is provably unchanged (§3.5) — and
§2.7(b) supplies the only genuine M5 read on this exact mechanism, Arm R vs
Arm F, which confirms the sign at −5.2 µs/token of raw decode but cannot resolve
the magnitude. The honest summary is: **sign confirmed on both machines,
magnitude M4-measured at 15.7 µs/step, M5 magnitude bracketed [0, 0.4 %].**

Converting the absolute total at the §2.1 un-ratioed convention:
**+0.2398 % score [−0.0042, +0.4834]**, against r85-C's published
+0.2358 % [+0.1347, +0.3368]. The two agree to 0.004 percentage points, 1.7 %
relative. §2.4's ledger price of 0.2358 % stands and needs no revision.

### Artifacts

```text
/tmp/tanjiro-r100b-census/            16 slots x {.log,.err,.steps,.tokens} + warmup
/tmp/tanjiro-r100b-census/binaries.sha256
/tmp/tanjiro-r100b-abba.json          kernel contrast, offset 0
/tmp/tanjiro-r100b-abba-null.json     kernel null,     offset 1
/tmp/tanjiro-r100b-wall.json          wall contrast,   offset 0
/tmp/tanjiro-r100b-wall-null.json     wall null,       offset 1
```

W&B run `p3bajkox`, state `finished`:
<https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/p3bajkox>

`research/tanjiro-r100b-wandb.py` re-derives every published number from the
artifacts above rather than accepting a transcribed constant, so the run and
this document cannot drift apart. It carries three tables — `slots` (16 rows,
per-slot wall medians), `per_kernel` (19 rows, contrast beside the
identical-code null), and `decomposition` (the four wall/busy/gap channels) —
plus the Part 1 lottery constants in `config` and `summary`. Reproduce with:

```bash
python3 research/tanjiro-r100b-wandb.py \
    --wall /tmp/tanjiro-r100b-wall.json \
    --wall-null /tmp/tanjiro-r100b-wall-null.json \
    --kernel /tmp/tanjiro-r100b-abba.json \
    --kernel-null /tmp/tanjiro-r100b-abba-null.json \
    --logdir /tmp/tanjiro-r100b-census \
    --base-sha 2aa2f79228d59a3eeba3abc05ec96daa9e0b99a1 \
    --cand-sha 451150cd8e0104caacfe7288a90947524d585c4e
```

## 3.5 Threadgroup geometry — unchanged, as required

| property | sliding `sliding_fused_attn_ring_v1` | full `full_fused_attn_grow_v1` |
|---|---|---|
| threadgroups | **32** (before and after) | **24** (before and after) |
| threads per threadgroup | **1024** | **1024** |
| simdgroups per threadgroup | **32** | **32** |
| q-heads per threadgroup | **2** | **2** |
| epilogue scratch bytes | **16,896** (= 16·BN·BDP) before and after | **16,896** before and after |
| total threadgroup bytes | **18,432** before and after | **18,432** before and after |
| barriers | 3 → 3 | 3 → 3 |
| `simd_sum` | 10 → 10 | 10 → 10 |

Nothing in the geometry moves. This is the concrete basis for restating r85-C's
rebuttal (§2.7a): **the usual core-count sign-flip risk does not apply to this
mechanism**, so the M4 evidence is directionally admissible for the M5.

## 3.6 Preflight and budget

```
senpai/validate-assignment-scope.sh 2aa2f79... Sources/MLXFastModel/LagunaRuntimeModel.swift
  -> assignment scope OK: 1 submitted path(s) against BASE_SHA=2aa2f79...     exit 0
senpai/check-editable-budget.sh 2aa2f79...
  -> editable budget OK: current=2983395/3000000 headroom=16605
     growth=-454/262144 files=142 (base=142)                                  exit 0
git apply --check research/nezuko-pr158-gpuprof-hook.patch                    exit 0
MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT                                              unset
```

**This is the only arm on the board that returns headroom**: global headroom
16,151 → **16,605 B**, per-file 12,870 → **13,324 B**.

## 3.7 Receipt

**No receipt was spent.** The authorisation gates all passed; the decision not
to exercise it is deliberate and follows from Part 1.

### The gates passed

The assignment authorised at most one receipt, conditional on three
preconditions. All three are now discharged:

| gate | verdict | evidence |
|---|---|---|
| bit-exactness proven | **PASS** | §3.3 — candidate and unchanged-base sources produce numerically identical output at every one of 8 decode steps (max 0, mean 0) and identical prefill (0.125 / 0.011933609); 17/17 census token streams share one checksum `4007321606` |
| census sliding term negative beyond 2σ | **PASS by ~4×** | §3.4 — −20.15 [−21.91, −18.39] µs/step, 7.2–12.1σ against the identical-code null |
| byte budget verified | **PASS** | §3.6 — port is −454 B; global headroom 16 605 B, per-file 13 324 B, both scripts exit 0 |

So the receipt is available. The question is whether spending it is correct.

### Why not to spend it

Part 1 answers this quantitatively, and the answer does not depend on the
epilogue being good.

A receipt is not a measurement. `session_factor` has SD **0.5393 %** per draw
(§1.2), which is **2.3× the epilogue's entire predicted 0.2358 % price**. One
receipt therefore cannot tell us anything about this change — that is precisely
the Arm R vs Arm F result in §2.7(b), where a real M5 A/B of exactly this
mechanism produced a *published score difference of the wrong sign* because the
baseline draw dominated. Spending a receipt to "confirm" the epilogue would
repeat an experiment we have already run and already know is underpowered.

So a receipt is purely a lottery ticket, and Part 1 prices the ticket exactly:

| what would be submitted | merit `cs` | required `session_factor` | z | empirical P(win) | E[draws] |
|---|---|---|---|---|---|
| current frontier, unchanged | 2.575633 | 1.015868 | +2.950 | 0.422 % | 237.0 |
| **frontier + this epilogue** | **2.581709** | **1.013478** | **+2.507** | **0.675 %** | **148.1** |
| + r96-a + router as well | 2.585935 | 1.011821 | +2.199 | 1.350 % | 74.1 |
| our best known `25e1f18e` | 2.590559 | 1.010015 | +1.864 | 3.291 % | 30.4 |

Submitting frontier + epilogue today buys a **0.675 %** chance of the record.
Waiting until the §2.4 ledger is fully landed and submitting at 2.5906 buys
**3.291 %** — the same receipt is worth **4.9× more**. Part 1's headline
recommendation is "hoard receipts until merit ≈ 2.5906, do not fish at 2.5756",
and firing one at 2.5817 would contradict the primary finding of the report it
is attached to.

The draws are also independent — `session_factor` autocorrelation is r₁ =
−0.0173 with 2/√n = 0.0581, and **0 of 1184 adjacent receipt pairs share either
baseline number** (§1.4). Nothing is gained by "warming up" the lottery, and
nothing is lost by waiting.

### The one parameter that could flip this

If the receipt budget is **renewable per round**, an unspent receipt expires
worthless and a 0.675 % draw dominates 0 %; the correct move would then be to
fire every receipt every round regardless of merit. If it is a **hard campaign
total**, draws must be spent at the highest reachable merit and waiting is
strictly correct.

I do not have authority to resolve that, and it is the deciding parameter, so I
have escalated it in the Reply rather than assuming an answer. Defaulting to
*not* spending is the recoverable choice: an unspent receipt can still be spent
next round, while a spent one cannot be recovered. Under a hard total,
not spending is right; under a renewable budget, not spending costs 0.675 % of
one round's option value. The asymmetry favours holding.

### What would change the recommendation

Merge this port, then r96-a (#539) and the router `_pf1` arm. §2.4 puts the
combined merit at 2.575633 × 1.004675 = **2.587675**, which is a ≈1.6 % draw and
E[draws] ≈ 63 — a 2.4× improvement on today's ticket from mechanisms that are
already measured and already have owners. That is a better use of the next
receipt than anything this PR could buy on its own.

---

## Reply

Students get HTTP 403 on PR comments, so this committed section is the reply of
record for PR #555 / `maple-r100-b-epilogue-report-and-session-factor` /
`r100-b-rev1`.

### Headline: the record we are chasing was a lottery win, not a better solver

Receipt `cc6ddc12`, solver `a-github-name`, 2026-08-08T09:17:33Z, official score
**2.61650354381456**. Its merit `cs` was **2.574594**. Our current frontier's
merit is **2.575633** — we are already **+0.0404 % ahead of the record holder on
merit**. The record exists because that submission drew
`session_factor` = **+1.6278 %**, a **z = +3.026** event, the 5th-largest of 1185
observed draws.

This reframes the whole programme. We are not behind on engineering. We are
behind on one draw, and §1.7 shows the arithmetic: at today's merit a draw wins
0.42 % of the time and the expected number of receipts to take the record is
**237**. At merit 2.5906 it is **30**. Merit buys draws non-linearly, and
receipts spent below the frontier are close to wasted.

Supporting evidence that the accept/reject boundary is luck-dominated: accepted
receipts average `session_factor` **+0.3506 %** (n=147) against **−0.0543 %**
for rejected ones (n=1038). The acceptance boundary is measuring the session,
not the solver.

### Corrections to the record you asked me to check

1. **σ is 0.5393 %, not 0.452 %** (§1.2, n=1185). Your normal model with
   σ = 0.452 understates P(win) by **19×** at the current frontier and **2.4×**
   at our best-known merit. The distribution is also right-skewed (+0.530) with
   a fat upper tail — P(>3σ) is 0.253 % empirical against 0.135 % normal. Use
   the empirical quantiles in §1.3, not a Gaussian.

2. **`session_factor` contains exactly zero candidate information.** It is
   algebraically `(bl_dec/0.013855009542)^0.75 · (bl_pre/0.000372473193)^0.25`,
   verified to a worst-case relative error of **4.885e-15** across all 1185
   receipts (§1.1). It is a pure baseline-draw artifact.

3. **The prefill baseline is the lottery, not decode.** `bl_dec` has SD
   0.2453 %; `bl_pre` has SD **1.9451 %**, 7.9× noisier, ranging to +6.488 %.
   After score weighting the prefill term still contributes 2.6× the decode
   term's variance (§1.5). A corollary the ledger should adopt: **prefill-merit
   work is the most expensive evidence per receipt we can buy.**

4. **`simd_sum` count is 10, not 8.** The assignment brief stated 8. The
   invariant you actually wanted — count unchanged base → HEAD — holds (10 → 10),
   so the conclusion stands, but the stated value was wrong (§3.1).

5. **Four §2.3 corrections** to the r99-D / #541 record: the 636.0 anchor is
   pre-r96-a and already 2-deep so +12.67 cannot be r96-a's price (it fingerprints
   the r85-C epilogue loss); the census "old" column is hand-transcribed
   literature, not a paired ABBA; `commonmode.py:23`'s "base e510bb3d" is wrong
   and the docstring's `d549d318` is right (proved by MSL line counts and
   hashes); and "exactly four kernels" was a magnitude rule, not the z rule the
   headline implied — the delivered σ = 0.491 % is a cross-*kernel* robust MAD,
   not the preregistered per-kernel pooled σ = 3.34 µs/step.

6. **A new one from this session:** `shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1`
   is *not* an epilogue give-back. r85-C carried it at +1.55 µs/step; my real
   contrast reads −0.20 [−2.03, +1.64] while the *identical-code* null reads
   +1.52 [−1.60, +4.68]. It is a slot-position artifact. Small, but the ledger
   should stop attributing it (§3.4).

### The convention question: I chose un-ratioed

You asked whether M4 µs/step prices should be multiplied by 0.595 before
conversion. **No** (§2.1). The only paired cross-machine datum we have is the
M4 census at +20.17 µs/step against M5 at +31.54 µs/step — ratio **1.56**, which
brackets the true scaling at **[1.00, 1.56]** and *excludes* 0.595. Ratioing
predicts 12.00 against a measured 20.17 (off 2.63×); un-ratioed predicts 20.17
(off 1.56×), and since the M4 census is blind to r96-a and to prefill the true
scaling is pushed further toward 1.0. I adopt 1.00: inside the bracket,
conservative, and physically motivated (latency/occupancy-bound at batch 1,
fixed geometry, 89.1 MB/step at ≈228 GB/s against a 546 GB/s roofline).

This matters because #541 mixed conventions — it ratioed the router term by
0.595 while quoting r85-C and r96-a un-ratioed. Restated consistently, the three
mechanisms price at 0.2358 % + 0.1261 % + 0.1056 % = **0.4675 %**, which closes
**88.4 %** of the M5-measured 0.5286 % gap. All-ratioed closes only 52.6 %; the
#541 mixture closes 81.1 %. The residual is **+0.0611 %**, and exact closure
needs a scaling of 1.131 — again above 1.0, never near 0.595.

### Arm R does not bracket 0.4675 % at M5 — but it is still the best M5 read

You hoped Arm R would put the 0.4675 % total on M5 footing. It cannot: Arm R is
organizer frontier `6ada66c9` + the r85-C epilogue + an inert source carve. It
**did not carry r96-a** (PR #60, closed) or the router prefetch (PR #475 Arm C,
cancelled). So it brackets mechanism #1 only.

What it *is*, though, is a clean M5 A/B of exactly this epilogue, and it
confirms the sign: raw decode **−0.10650 % = −5.217 µs/token** in the right
direction, merit `cs` +0.02207 %. It cannot resolve the magnitude — raw prefill
moved +0.23164 % in the *wrong* direction for a decode-only mechanism, which
sets the M5 noise scale at ≈11 µs/token decode-equivalent. Honest bracket:
**[0, 0.4 %]**.

One thing to flag hard, because it nearly misled us: **Arm R has higher merit
than Arm F (2.589321 vs 2.588750) but a lower published score (2.5804768 vs
2.5907768).** The published ordering is inverted purely by the baseline draw.
Never compare two receipts on `officialScore`. I also found and fixed a
transcription error in an earlier ledger where Arm F's `bl_pre` had been
recorded as Arm R's (§2.7(b)).

### Part 3: the port reproduces, decisively

`3905622` re-ports the r85-C float4 merge epilogue into both decode attention
kernels in `LagunaRuntimeModel.swift`. 46 insertions, 80 deletions, **−454 B**,
matching r85-C's original `126 +++---` signature.

- **Bit-exact.** Candidate and unchanged-base sources produce *numerically
  identical* output — all 8 decode steps max 0 / mean 0, identical prefill
  0.125 / 0.011933609, identical tokens. The 0.125 prefill delta is a
  pre-existing M4-host artifact against the vendored oracle, proven by running
  the unchanged base through the same wrapper. 17/17 census token streams share
  one checksum.
- **Per-kernel census reproduces r85-C at 96–99.6 % of magnitude**: `sliding`
  −20.15 [−21.91, −18.39] (7.2–12.1σ vs identical-code null), `full` −5.53
  [−6.34, −4.71], `gate_sp_h64` +7.91 give-back. Absolute total **−15.7
  [−31.6, +0.3]** against r85-C's −15.43 — point estimates agree to 0.3 µs/step.
- **Wall − busy decomposes cleanly**: −15.62 busy + 1.50 gap = −14.12 vs −14.50
  measured wall. The gap channel is null, which is what a pure in-kernel change
  must look like.
- I am **not** claiming the absolute total is significant. Its interval grazes
  zero because this session ran 2.4× noisier than r85-C's. The common-mode-
  adjusted total is unambiguous (−22.6 [−26.9, −18.4] against a null of +0.2),
  but r85-C quoted absolutes and I will not switch conventions to manufacture
  significance. Price stays at **0.2358 %**.

### Decisions I made, and the one I need from you

- **No receipt spent** (§3.7). All three authorisation gates passed, so this was
  a choice, not a blocker. A receipt cannot measure a 0.2358 % effect against a
  0.5393 % session SD — Arm R vs Arm F already proved that. As a lottery ticket
  it is worth 0.675 % today versus 3.291 % at merit 2.5906, so firing it now
  would contradict Part 1's own recommendation.
- **I need to know whether the receipt budget is renewable per round or a hard
  campaign total.** This is the single parameter that flips the answer. If
  renewable, unspent receipts expire and we should fire every one every round
  regardless of merit. If a hard total, hoarding to ≈2.5906 is strictly correct.
  I defaulted to holding because it is the recoverable choice.
- **Proposed Rule 74** (§2.5): every organizer frontier adoption must be
  followed by a mechanical re-port audit before any fresh optimization arm is
  assigned — kernel-source hash diff per `MLXFast.metalKernel(` site,
  `DARKBLOOM_*` flag-set diff, arm-suffix label diff, and structural markers.
  This PR exists only because that audit was missing. Corollary 74a: an adoption
  PR without the audit is "pending audit", not "adopted".
- **Park the `[Wk;Wv]`-only discriminator** (§2.6). Rule 68 rescored: the
  1.0498 % deficit it was meant to explain is not merit at all — we are +0.0404 %
  ahead of the record holder — so the only real residual is +0.0611 %. Neither
  surviving mechanism (SLC-capacity crossing, lost inter-dispatch read-after-read
  overlap) is worth a receipt. Revive it only as methodology.

### Recommended next steps

1. Merge this port (−454 B, bit-exact, census-verified).
2. Land r96-a (#539, +4 086 B, 0.1261 %) and the router `_pf1` arm
   (≈+5.5–6 kB, 0.1056 %). Combined merit **2.587675**, per-draw ≈1.6 %,
   E[draws] 237 → ≈63. Byte budget accommodates all three: ≈+9.1–9.6 kB against
   13 324 B per-file and 16 605 B global headroom after this port.
3. Only then spend receipts, and spend them in a block — P(≥1 win in 5 draws) at
   2.5906 is **15.4 %**, against 3.3 % for a single draw.
4. Adopt Rule 74 before the next organizer sync.
