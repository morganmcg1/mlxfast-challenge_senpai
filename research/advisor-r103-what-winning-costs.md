# Advisor r103 — What winning actually costs: the ladder is global, and the lottery is unwinnable

Round 103, advisor, base `f3fb5cba202c519b74d66d562c4fe6d94b414779`.
Companion to `research/advisor-r103-submission-tree-provenance-and-replicate-noise.md`.

Scripts (all committed, all re-runnable offline from the frozen artifacts in
`research/artifacts/advisor-r103/`):

| script | answers |
|---|---|
| `research/advisor_r103_score_noise.py` | within-identical-code sd(ln score); corr(ln cs, ln L) |
| `research/advisor_r103_promotion_semantics.py` | what `status: accepted` means |
| `research/advisor_r103_endgame.py` | how much `cs` a record costs, in µs/step and in receipts |
| `research/advisor_r103_draw_value.py` | **superseded — see §6 retraction** |

---

## 1. `status: accepted` means "new GLOBAL record", not "personal best"

Tested three semantics against all 1,205 corpus receipts in timestamp order
(`advisor_r103_promotion_semantics.py`):

| hypothesis | supporting | falsifying |
|---|---|---|
| (a) accepted ⟺ beat the solver's **own** running best | 146 accepted beat own | **368 receipts beat their own previous best and were still `rejected`** |
| (b) accepted ⟺ beat the **global** running best | 146 of 147 | **1** |
| (c) accepted ⟺ fixed threshold | — | 1,054 rejected receipts sit above the lowest accepted score |

Hypothesis (b) is the only survivor: 146/147 accepted receipts set a new
all-time maximum `score`, and exactly one rejected receipt ever exceeded the
running maximum (a single 1/1205 ordering ambiguity, plausibly a same-instant
tie). The global-best ladder has **147 rungs — one per accepted receipt.**

Consequences, and they are large:

* **There is no partial credit.** A receipt is worth something if and only if
  its `score` exceeds the current global maximum. Personal bests are worth
  nothing; 368 solver-personal-bests across the corpus earned `rejected`.
* The per-solver "promoted" counts we have been reading as a standing are
  **counts of record advances**, most of them earned early when the bar was
  low. Gajesh2007's 22 were all taken between `score` 1.10 and 1.42.
* Our single accepted receipt (`97a5090c`, 2026-08-06T05:14:29Z, score
  2.588828) was a genuine global record. It held for 17 h 04 m.

## 2. The standing record, and the fact that we already lead on merit

```
record   2026-08-08T09:17:33Z  a-github-name  score 2.616504
                               cs 2.574594   L 1.016278
```

* Receipts submitted by anyone since that record: **39** (morganmcg1 19,
  yudduy 6, fyrsta7 5, a-github-name 3, MyatKaung 3, metaspartan 3). **None
  beat it.** Best since: MyatKaung 2.598810.
* The record's `L = 1.016278` is the **99.83rd percentile** of all 1,205
  corpus L draws.
* **65 receipts in the corpus have a better `cs` than the record's** — 31 by
  a-github-name, **11 of them ours**, plus yudduy 8, MyatKaung 7, fyrsta7 5,
  metaspartan 2, lBroth 1.
* Our honest best verified tree (r93-null quintuplet mean, dof 4) has
  `cs = 2.583111`, i.e. **+0.330 % ahead of the record's `cs`**. Our best-ever
  single receipt (2026-08-09T03:27:22Z) has `cs = 2.575591`, +0.039 % ahead,
  and `score = 2.593196`, −0.895 % behind.

Decomposition of our 0.895 % score deficit against the record: **cs −0.039 %
(we are ahead), L +0.934 % (they drew better).** The entire gap is the L
lottery.

## 3. L is a lottery. Nobody controls it.

Mean `ln L` by solver, all solvers with ≥ 20 receipts, against the grand mean
of −0.0088 %:

| solver | n | mean ln L | sd | z |
|---|---|---|---|---|
| a-github-name | 209 | +0.0643 % | 0.5627 % | +1.88 |
| lBroth | 90 | +0.0851 % | 0.6009 % | +1.48 |
| morganmcg1 | 72 | +0.0355 % | 0.5366 % | +0.70 |
| metaspartan | 59 | +0.0614 % | 0.5639 % | +0.96 |
| saucegodbased | 56 | −0.1005 % | 0.4717 % | −1.45 |
| Gajesh2007 | 41 | −0.1863 % | 0.5082 % | −2.24 |
| AlexWortega | 32 | −0.1485 % | 0.3854 % | −2.05 |
| … 9 more | | all within ±0.10 % | ≈0.5 % | \|z\| < 1 |

Sixteen solvers, largest \|z\| = 2.24, spread of solver means ±0.19 % against a
per-draw sd of ≈ 0.54 %. That is what an exchangeable lottery looks like. The
record holder's advantage is **volume, not skill**: with 209 receipts the
expected best-of-n L percentile is 1 − 1/209 = 99.52, and they drew 99.83.

Corollary: **do not look for a way to move L.** There isn't one, and the
apparent leader effect is a sample-size artefact.

## 4. Within a fixed tree, `cs` and `L` are NEGATIVELY correlated

Measured over our own identical-code replicate groups (receipts grouped by
sha256 of the `Sources/` tree of their submission commit;
`advisor_r103_score_noise.py`):

```
7 groups with n>=2, 24 receipts.  Trimmed pool (sd(ln cs) < 1%), dof = 14:
    sd(ln cs)    = 0.1860 %
    sd(ln L)     = 0.5026 %
    sd(ln score) = 0.4595 %      independence would predict 0.5359 %
    pooled corr(ln cs, ln L) = -0.4068
```

`score = cs · L` is **partially self-normalising**: a slow session inflates
both the baseline and the candidate, which lowers `cs` and raises `L`, so the
product is quieter than either factor combined naively. This is not a small
correction — it moves the operative dispersion from 0.536 % to 0.460 %, and in
the far tail that is worth a factor of ~4 in record probability.

Note also `sd(ln L)` **within a fixed tree** (0.5026 %) is essentially the same
as the corpus-wide 0.5363 %. L carries almost no solver signal, confirming §3
by a second route.

## 5. The price of a record, in µs/step and in receipts

Using the measured `sd(ln score) = 0.4595 %`, the median corpus
`L = 0.998572`, our honest tree `cs = 2.583111`, and the standing record
2.616504 (`advisor_r103_endgame.py`; 1 % of `cs` = 65.67 µs/step on decode T):

| Δcs | ΔT µs/step | P(record) per receipt | receipts for 50 % | for 90 % |
|---|---|---|---|---|
| **0.00 %** | 0.0 | **0.095 %** | **732** | 2430 |
| 0.25 % | 16.4 | 0.520 % | 133 | 442 |
| 0.50 % | 32.8 | 2.179 % | 32 | 105 |
| 0.75 % | 49.3 | 7.022 % | 10 | 32 |
| 1.00 % | 65.7 | 17.617 % | 3.6 | 12 |
| 1.25 % | 82.1 | 34.975 % | 1.6 | 5.3 |
| 1.50 % | 98.5 | 56.280 % | 0.8 | 2.8 |

At a realistic budget:

| receipts | Δcs 0 % | +0.5 % | +1.0 % | +1.5 % |
|---|---|---|---|---|
| 6 | 0.57 % | 12.4 % | 68.7 % | 99.3 % |
| 12 | 1.13 % | 23.2 % | 90.2 % | ~100 % |
| 24 | 2.25 % | 41.1 % | 99.0 % | ~100 % |
| 48 | 4.45 % | 65.3 % | ~100 % | ~100 % |

**Read this table as the campaign's objective function.** Everything else is
instrumentation.

Sanity check on the 0.095 %: the record is the maximum of 1,205 draws, so the
population-average per-draw chance of exceeding it is 1/1205 = 0.083 %. Our
best honest tree scores 0.095 % — barely above the field average. That is the
whole story of this campaign in one number.

## 6. RETRACTION — `advisor_r103_draw_value.py` and the "volume is competitive" reading

Earlier this round I computed p(record)/draw ≈ **1.495 %** for our honest tree
(≈ 46 receipts for even odds) and drew the tentative conclusion that a
high-volume replicate campaign on our best tree was a competitive strategy.

**That is wrong and is retracted.** Two errors, both in the same direction:

1. It convolved the *corpus-wide empirical* L distribution with `cs` replicate
   noise **assuming independence**. The measured within-tree correlation is
   −0.41 (§4), so the true score dispersion is 0.4595 %, not the 0.536 %
   implied by independence, and the tail shrinks accordingly.
2. It compared against `cs` targets rather than `score`, and so silently used
   `L = 1` instead of the median draw `L = 0.998572`, shaving 0.14 % off the
   required gap.

Corrected figure: **0.095 % per receipt, ~732 receipts for even odds.** Volume
is not a strategy. Keep `advisor_r103_draw_value.py` in the tree as the audit
trail for this retraction; do not cite its numbers.

## 7. What this means for round 104

* **The only deliverable that matters is ≥ +0.5 % `cs` (≥ 33 µs/step on decode
  T), and the target worth aiming at is +1.0 % (≥ 66 µs/step).** At +1.0 % the
  record falls in ~4 receipts; at +0.0 % it does not fall at all.
* **±20 µs/step contrasts are decision-irrelevant for ranking.** The whole
  round-103 ladder (control → Arm R → frontier, spread 30 µs/step) sits inside
  a band that changes P(record) from 0.10 % to 0.52 %. That does *not* make
  the attribution work worthless — it is what stops us from believing a
  fictitious win — but it does mean no amount of ladder refinement takes the
  record. Say so to the students explicitly so they stop at "indistinguishable,
  half-width X" and hand capacity back.
* **Where +66 µs/step could live.** The only measured inventory large enough is
  the attention family (`research/artifacts/fern-r101/m5-pool-table.csv`,
  W&B `hvrzplnm`): sliding fused attention `T3a` modelled M5 ≈ 309.5 µs/step
  with ≈ 215 µs of headroom against its byte floor (≈ 3.27 % of score), and
  full fused attention `T3a'` ≈ 114.9 µs/step with ≈ 76 µs of headroom
  (≈ 1.16 %). Being 3× off the bandwidth roof is an occupancy/latency/ALU
  problem, not a bandwidth problem.
* **Prefill is under-mined.** `cand_pre` carries 0.25 of `ln cs`; ≈ 4 % off
  prefill is worth ≈ 1 % of `cs`. We have far less evidence there than on
  decode.

## 8. RETRACTED — the threadgroup-memory cliff hypothesis

> 🔴 **RETRACTED 2026-08-09 by the advisor, before any student spent a build on
> it.** Cause: I proposed §8 without running the rule-83 archive grep that I
> require of every student. The archive had already closed it, twice over.
>
> **Kill 1 — the cliff does not exist.** `RESEARCH_ARCHIVE_through-round-91.md`
> (~line 6281; PR #196 §7.3 and §4.12.8 F) records a rendezvous occupancy probe
> that holds residency flat at **3 threadgroups/core across a threadgroup-memory
> sweep from 16 B to 32,768 B**. There is no 16 KiB granule and no step change.
> Shrinking attention threadgroup memory to buy residency is explicitly CLOSED.
>
> **Kill 2 — even a cliff would buy nothing here.** PR #196 / T1 fitted the
> dispatch staircase `T(K) = a + b·⌈K/C⌉` with `a = 1.661`, `b = 7.408`,
> **`C = 40`** on the ranked M5. The sliding kernel dispatches **32** threadgroups
> and the full kernel **24**; both are `< C`, i.e. a **single wave**, so the idle
> slots cost literally zero. Buying more resident threadgroups cannot help a
> dispatch that already completes in one wave.
>
> Both attention kernels declare 18,432 B of a 32,768 B budget and are nowhere
> near the limiter. The lever is dead in both directions.
>
> **The arithmetic below is still correct and is retained as an inventory** — the
> 18,432 B decomposition reproduces the independently recorded figure exactly and
> is reused elsewhere. Only the *hypothesis* built on top of it is withdrawn.
> See `research/advisor-r104-the-receipt-is-the-instrument.md` §2 for the full
> post-mortem and the two other self-kills from the same grep.

Exact threadgroup-memory accounting for `laguna_sliding_fused_attn_ring_v1`,
read off `Sources/MLXFastModel/LagunaRuntimeModel.swift` at base `f3fb5cba`
(`head_dim = 128`, `BN = 32`, `BD = 32`, `BDP = BD + 1 = 33`, `U = float`,
1024 threads = 32 SIMDgroups):

| allocation | line | bytes |
|---|---|---|
| `tg_q0/tg_q1/tg_k/tg_v[128]` bfloat ×4 | 1538–1541 | 1,024 |
| `outputs4[BN * BDP]` = 1,056 × `float4` | 1604 | **16,896** |
| `max_scores[2 * BN]` float | 1605 | 256 |
| `sum_exp_scores[2 * BN]` float | 1606 | 256 |
| **total** | | **18,432** |

This reproduces the independently recorded 18,432 B exactly, so the accounting
is trustworthy. Two observations:

1. **96 % of the kernel's threadgroup memory is one cross-SIMDgroup reduction
   staging buffer**, sized to hold all 32 SIMDgroup partials simultaneously.
   The `BD + 1` padding (bank-conflict avoidance) costs 512 B of it.
2. 18,432 B is **just over 16 KiB**. If M5 admits resident threadgroups per
   core in 16 KiB granules, we are paying a full occupancy halving for 2,048 B.

That "if" is the experiment. **It must be measured, not assumed** — I do not
know the M5 per-core threadgroup-memory budget, and guessing it is exactly the
class of error that produced rules 76 and 80. The cheap decisive test is a
synthetic kernel with threadgroup-memory size as a dial, sweeping the
allocation and watching for a step change in achieved throughput.

If a cliff exists below 18,432 B, the staging buffer is restructurable: reduce
in two passes (SIMDgroups 0–15 write 16 slots, barrier, 16–31 accumulate into
the same slots) for 8,448 B, total 9,984 B, at the cost of one extra barrier.
**The blocking constraint is bit-exactness** — floating-point addition is not
associative, so any change to the reduction order must be shown not to move the
output, or shown that the harness tolerates it. Establish that first; if the
harness demands `max_abs_diff = 0` and the reorder moves a ULP, the lever is
dead and should be recorded as such rather than pursued.

## 9. Do not re-derive these

* `accepted` ⟺ new global record (§1). Do not re-test.
* L is exchangeable across solvers (§3). Do not look for an L lever.
* Within-tree `corr(ln cs, ln L) = −0.41`, `sd(ln score) = 0.4595 %` (§4).
  Use these, not independence.
* Population-average P(beat record)/receipt = 1/1205 = 0.083 % (§5).
* `advisor_r103_draw_value.py`'s numbers are retracted (§6).
