# R108-K — is one decode dispatch per layer actually removable, and is removal worth the rule-65 price?

- **Student** maple-frieren · **PR** #660 · **assignment** `maple-r108-k-decode-dispatch-merge` · **revision** `r108-k-rev1`
- **Base** `codex/mlxfast-maple-20260804-advisor` at assignment time `d3045bd8`; **reconciled by MERGE** onto the
  live advisor tip **`705484b9`** (rule 97.0 — recording which). The merge brought in tanjiro's R107-G census,
  which the advisor's 15:48Z feedback comment made a Stage-0 input.
- Carried forward on the same branch: two research-only commits orphaned by the closure of #597
  (`cert v2`, `SOP v2`). No `Sources/` change accompanies Stage 0.

---

## Both stages, in one screen

**Stage 1 first, because it changes how Stage 0's headline should be read.** Stage 0 argued M2 was worth
≈ 2 % of `cs` on a *kernel-time* accounting and said so was the reason to distrust it (§2.3.5). Stage 1 went
and measured the one term that accounting cannot separate — the price of a decode dispatch — and it is
**roughly four-fold cheaper than the assignment's assumed 1.890 M4 µs/dispatch**. The dispatch-count half of
the M2 prize is therefore ≈ 0.15 % of score, not 2 %. Whatever remains of the 2 % must come from fusing *work*,
and Stage 1 has no evidence for that.

Every figure in the table below, in §3.3, and in §3.5's ladder is machine-written from the probe sink by
`research/maple-frieren-r108k-insert-results.py`; prose elsewhere is deliberately rounded so it cannot
disagree with them.

<!--HEADLINE:BEGIN-->
| | Stage 1 answer |
|---|---|
| **Reported verdict** | **`P-INDETERMINATE`** — the identified per-dispatch price lands inside comment 6's undecided 0.3–0.8 band. One verdict only; §3.3 discloses that the mechanical §5 estimator prints `P-INDETERMINATE-UNDERPOWERED` and §3.2.1 proves why that estimator is degenerate and must not be believed. |
| **Per-dispatch price** | **`k = 0.451` M4 µs/dispatch, CI95 `[0.399, 0.502]`** from the unchained ladder; `0.465 [0.415, 0.514]` from the chained ladder, *independently*. Two ladders, one number. |
| **Barrier price** | **≈ 0, at both rungs.** `−0.080 [−0.282, +0.123]` µs/barrier at N=160 (B=3); `+0.0019` µs/barrier at N=1200 (n=1). Serialising the injected chain costs nothing measurable — the free-region claim survives, but as a *barrier* claim, not a dispatch claim. |
| **Merge prize, repriced** | 40 dispatches/step × `k` = **18.0 M4 µs/step = 0.20 % decode = 0.15 % score** (interval 0.13–0.17 %). At the assumed `k = 1.890` it would have been 0.63 %. |
| **Pre-registered predictions** | 1 of 3 **refuted** (P1, by 3.2×), 1 discriminated as intended (P2: `k = 0` dead by more than fifteen standard errors), 1 sign-confirmed and size-wrong (P3). §3.3 scores all three and names the root cause: the pre-registration anchored its fit on a rung that turned out to be off the line. |
| **Accidental finding** | the intercept is **negative and large**: `c ≈ −4.2 to −3.8` µs *per layer*, i.e. adding one `asyncEval` commit boundary per layer at zero added dispatches would make decode **≈ 153–168 µs/step (1.7–1.9 %) faster**. That is an order of magnitude more than the merge prize, it contradicts the campaign's ≈ 30–50 µs-*cost*-per-commit folklore, and it is the follow-up I would rank first. It is also an extrapolation to N=0 from rungs at 160 and 1200 with a tape-split confound, so §3.4.1 states it as a lead to test, not a result. |
| **`Sources/` bytes spent** | **zero.** Both stages are measurement and source reading. |
<!--HEADLINE:END-->

---

## Stage 0 verdict, both deliverables, in one screen

| | answer |
|---|---|
| **A — fiction-corrected residue table** | **REFUTED.** `−291.2` is a *headroom*-column value subtracted from a *time* column; the M5 kernel time of rows 5/13 is 318.0 + 114.9 = **432.9**, and rule 100.3's own words say the headroom "does not exist" (§1.3). The replacement result is a **budget**: residue 351.7 M4 / 490.6 M5 µs/step. |
| **A′ — new, unasked** | **the census is not the whole ledger.** ≥ 92 uncensused decode dispatches found and witnessed live ⇒ **`N ≥ 411`**, not 319 (§1.4, table U). Consequence: the per-removal glue ceiling drops to **≤ 1.1937 M5 µs/dispatch, `k_removal ∈ [0, 0.964]`** — so the advisor's "conservative floor" of `k = 1.0` is *above* the ceiling, and **a dispatch removal has no static point price at all** (§1.6). I withdrew my own first-draft instruction to quote `k = 1.0`. |
| **B — ledger** | 7 candidates, all read at source level (§2.2). **Nothing in decode is TG-local.** The brief's taxonomy is missing a class, and the winner is in it: **SIBLING** — two dispatches reading the *same* input, needing **no synchronisation whatsoever** to merge. |
| **Stage-1 pick (early)** | **M2 — merge `lagunaGateSoftplus` (`:4525`) into `lagunaDecodeNVFP4QKVR1` (`:5002`).** 40 dispatches/step (more than any censused family), **105.15 class 1 by source argument**, sibling ⇒ no sync, +3,200 B, passes tanjiro's #48 gate *by construction*. Family E exists only because two weight banks are quantized differently (`foldGateIntoBank`, `:5713`) — a packaging accident, not a data dependency. |
| **Value** | **+1.7 % to +3.1 % of `cs`, point estimate ≈ 2.0 %** — and deliberately *not* a dispatch-count argument, since §1 forbids that. It is 328.2 M4 µs/step of latency-regime kernel time against +20.8 M4 µs/step of added bytes. This is larger than the entire 1.6359 % gap to the record, which is itself the strongest reason to distrust it; §2.3.5 lists all four accountings and three reasons for skepticism. |
| **⚠️ Collision** | `lagunaDecodeNVFP4QKVLaneMajorSource` (`:4922`) is **maple-edward's under #629**. Flagged, not negotiated. Fallback if ruled fatal: **M3** (class 2, ≈¼ the value, touches nothing edward owns). |
| **Not** `N-MERGE-UNREACHABLE` | the kill rule's second clause is satisfied — M2's design is written in full (§2.3.4), five hours before the gate. |

---

## §0 Preregistration (written before any device time — rule from R107-F §2.7)

**Question.** Not "how much is dispatch merging worth" (that is priced) but **"can one dispatch per layer be
removed, and is removal worth what rule 65 says an *addition* costs?"**

**Stage 0 has no device time at all.** It is arithmetic and source reading. The only claims Stage 0 may make
are (a) arithmetic-only re-derivations of published numbers and (b) source-level statements about kernel
geometry with `file:line`.

**Outcome vocabulary, fixed now, not to be extended afterwards:**

| verdict | meaning |
|---|---|
| `N-MERGE-UNREACHABLE` | no pair is TG-local, and no grid-wide pair has a design writable in full by 21:00Z |
| `Y-MERGE-CLASS1` | a TG-local pair exists whose per-output accumulation order is preserved ⇒ bit-exact by source argument |
| `Y-MERGE-CLASS2` | a mergeable pair exists but it reassociates ⇒ needs a margin certificate |
| `N-REMOVAL-ASYMMETRIC` | removal provably recovers less than the draw bar even if the merge is free |

**Stopping rule.** If §1's arithmetic had shown the removal price collapsing below the 0.4 % bar at its
*ceiling*, Stage 0 would have terminated at `N-REMOVAL-ASYMMETRIC` and no ledger scan would have been done.
It did not (§1.6), so the scan proceeded.

---

## §1 Deliverable A — the fiction-corrected residue table is **refuted**, and the residue is a *ceiling*, not a corroboration

### §1.1 What was asked

The brief (§1) offered a new, arithmetic-only corroboration of `k_dispatch = 1.890` and asked me to confirm or
refute it, honestly, flagging mis-attribution of which rows rule 100 calls fiction:

| quantity | advisor's value (M5 µs/step) |
|---|---:|
| rule 58 `T_M5` (decode, ex-prefill) | 4141.5 |
| §B.0.3 M5 column sum as printed | 3650.9 |
| less rule-100 fiction (rows 5, 13) | −291.2 |
| **real kernel time** | **3359.7** |
| **residue available for dispatch glue** | **781.8** |
| 319 dispatches × rule 65's 2.3403 µs | **746.6** |
| slack | +35.2 |

### §1.2 The inputs all reproduce exactly

Re-summed from `research/CURRENT_RESEARCH_STATE.md` §B.0.3 (lines 1693–1709):

| quantity | recomputed | state doc |
|---|---:|---:|
| M4 µs column, 15 rows | **8096.3** | 8096.3 ✓ |
| M5 µs column, 15 rows | **3650.9** | 3650.9 ✓ |
| calls column, 15 rows | **319** | (never summed before — see §1.4) |

`8096.3 / 8448.0 = 95.84 %` ✓ and `3650.9 / 4141.5 = 88.16 %` ✓, matching the state doc's 95.8 % / 88.2 %.
So the arithmetic the corroboration is built on is sound. The corroboration itself is not.

### §1.3 🚫 REFUTED — `291.2` is a value from the **headroom** column, not the kernel-time column

Rows 5 and 13 of §B.0.3:

| row | family | M5 µs (kernel time) | headroom µs |
|---|---|---:|---:|
| 5 | T3a sliding fused attn | **318.0** | ~~215.0~~ **0** |
| 13 | T3a′ full fused attn | **114.9** | ~~76.2~~ **0** |
| | **sum** | **432.9** | **291.2** |

`291.2 = 215.0 + 76.2` is the **headroom** of those two rows. Their **kernel time** is `318.0 + 114.9 = 432.9`.
Rule 100.3 says so in its own words: *"291.2 µs/step of nominal **headroom** = 4.43 % of score does not
exist"* and *"Strike rows 5 and 13 from every **remaining pot** list."* The fiction is the *compressibility*,
not the *time*. Subtracting 291.2 from a kernel-time column subtracts a headroom number from a time column.

The substantive version of the same objection is stronger. Rule 100's finding is that the fused-attention pool
is **ISSUE-bound at 97.7 % of peak issue**. That is precisely a statement that **the time is real and
incompressible**. Removing it from the kernel-time column asserts that those two kernels execute in zero
time — which contradicts the rule invoked to justify the removal.

And the substitution is not internally consistent even if one grants it: if rows 5 and 13's *time* were
fiction, their `30 + 10 = 40` dispatches would have to leave the dispatch count too, and the price becomes
`279 × 2.3403 = 652.9`, not 746.6. Struck properly (`−432.9`) the table reads: real kernel time 3218.0,
residue **923.5**, price 746.6, slack +176.9 — a "fit" purchased by asserting that 40 of 319 dispatches
execute nothing.

**Verdict on deliverable A: refuted. The row attribution was the error the brief asked me to look for.**

### §1.4 The correct closure — a budget constraint, and the census is **not** the whole ledger

The **calls** column of §B.0.3 sums to **exactly 319**:

```
39 + 30 + 30 + 39 + 30 + 1 + 10 + 39 + 39 + 10 + 30 + 1 + 10 + 1 + 10 = 319
```

I first read that as an independent confirmation that "the census" and "the 319-dispatch count" describe the
same object. **I withdraw that reading, and I want the withdrawal on the record rather than buried.** I could
find no independent origin for `319` anywhere in `CURRENT_RESEARCH_STATE.md` (`grep 319` returns only a router
µs figure, an `LRM:4319` line reference and a byte count). The most likely provenance of the campaign's
"319 dispatches" is *this same column*, so summing it proves nothing. What the sum does establish is weaker
and still worth having: **§B.0.3 is internally consistent with a 40-layer model** (`numHiddenLayers = 40`,
`LagunaConfig.swift:20`), because it decomposes exactly:

```
attention side, all 40 layers   4 × 40 = 160   qkv (30 h64 + 10 h48) · fused attn (30+10) · gate_sp (30+10) · oproj (30+10)
MoE side, layers 1..39          4 × 39 = 156   residual/rms/router · shared gate+up · routed gate+up · down+residual
layer 0 dense                          2       dense gate_up · dense_down
head                                   1       lmhead int5
                                     ─────
                                       319
```

**And then it is incomplete.** I enumerated the live decode dispatch set from source and confirmed it on the
device: one `capture --steps 2` run with `DARKBLOOM_TRACE_FUSION=1` prints one `mlxfast: fusion active:` line
per distinct dispatch site actually taken (`LagunaRuntimeModel.swift:79-92`). Raw witness list:
`research/artifacts/maple-frieren-r108k/fusion-active-decode.txt`. Every one of the 15 census families is
present. So are these, **none of which is in the census**:

| # | uncensused decode dispatch | calls/step | site | evidence it is live |
|---|---|---:|---|---|
| U1 | plain MLX `rmsNorm` — `normalized = fusedQKV ?? inputNorm(input)` | **40** | `:5950` | `decode nvfp4 qkv r1 h64/h48 lane-major` fires, and *no* `norm+affine qkv` witness ⇒ `fusedQKV == nil` ⇒ the `inputNorm` branch is taken in all 40 layers |
| U2 | `laguna_decode_router_top8_*_norm_*` (top-8 select + weights) | **39** | `:10291` (launcher `:9597`) | `decode router top8 (cast sink + norm sink)` |
| U3 | `laguna_full_qk_norm_yarn_bf16_128_v4` | **10** | `:6205` (launcher `:1332`) | `full qk norm+yarn`, decode shape `(1,1,48·128)` — the 10 full-attention layers only; the 30 sliding layers have it fused into `laguna_sliding_fused_attn_ring_v1` |
| U4 | `laguna_decode_embedding_rope_atlas_bf16_2048_v2` | 1 | `:11592` | `decode embedding+rope atlas` |
| U5 | `laguna_residual_rms_bf16_2048_v1` (layer 0, dense, no router) | 1 | `:11197` | `residual+rmsnorm` (distinct from `residual+rmsnorm+router rpg8 pf1`) |
| U6 | final norm + sampling/argmax tail | ≥1 | not enumerated | — |
| | **total uncensused** | **≥ 92** | | |

So the true decode dispatch count is **`N ≥ 411`, not 319** — the census covers about **78 % of the
dispatches** (and, since everything it omits is small, well over 95 % of the kernel *time*). Two of the
omissions are 39–40-call families of tiny kernels, i.e. exactly the shape of thing this assignment is hunting.
They re-enter as candidates in §2.

This does **not** damage the constraint; it tightens it. Write `R` for the residue, `K_unc ≥ 0` for the kernel
time of the uncensused dispatches, `N ≥ 319` for the true count. Then

```
average per-dispatch glue  =  (R − K_unc) / N  ≤  R / 319
```

so `R/319` is an upper bound on the average per-dispatch glue under *either* reading, and `R/411` is the
bound once the source-attested count is used. The residue is therefore still a **budget** — a constraint,
which is a more useful object than a corroboration, because it can be violated:

| host | `T` | Σ census kernel time | residue `R` | `R ÷ 319` | `R ÷ 411` | marginal ADDED price (rules 57/65) | price × 319 | over-run |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| M4 | 8448.0 | 8096.3 | **351.7** | 1.1025 µs | **0.8557 µs** | 1.2382 | 395.0 | **112.3 % of budget** |
| M5 | 4141.5 | 3650.9 | **490.6** | 1.5379 µs | **1.1937 µs** | 2.3403 | 746.6 | **152.2 % of budget** |

**The marginal added-dispatch price over-runs the census residue on both hosts** — by 52 % on M5, and by
12 % on M4, where the census kernel times were actually measured rather than derived. The state doc's own
figure `490.6 / 351.7 = 1.3949` is exactly the *ratio of the two ceilings*, which is why it reads as 1.395
and not as 1.890: it was never a measurement of a per-dispatch price, it was a residue-to-residue ratio.

### §1.5 🔑 What the over-run means — and it is a direct, arithmetic-only answer to caveat 1

There is one reading under which every measurement above is simultaneously true:

> **A resident dispatch's glue is partly overlapped with kernel execution. An *added* empty dispatch's glue is
> not.**

Rules 57 and 65 measure a no-op inserted into the stream. A no-op has nothing to hide behind, so it exposes
the full serial host/driver cost. A dispatch that is *already* in the stream hides part of that cost behind
its neighbour's execution. The census residue measures only the part that was never hidden.

⇒ **Removal symmetry fails — and it fails in the conservative direction.** Removing a resident dispatch
recovers only its *non-overlapped* share, which the residue bounds from above at `R / N`. With the census's
own 319 that is 1.5379 M5 µs/dispatch; with the corrected count `N ≥ 411` from §1.4 it is
**≤ 1.1937 M5 µs/dispatch**, i.e. `k_removal ≤ 1.1937 / 1.2382 = **0.964**`.

This is the answer the brief wanted and it is the opposite sign from the one it hoped for: the hedge in rule
105.13 was **not** wrong, it was **not conservative enough**. `k_dispatch ∈ [1.0, 1.890]` does not describe
removal at all — the admissible interval for removal is `k_removal ∈ [0, 0.964]`, and it does not contain
1.0. The lower end is not rhetorical: nothing in this arithmetic forbids the overlapped share being 100 %,
so **the residue gives a ceiling and no floor.**

### §1.6 The honest ladder — replacing the brief's three-point read

`cs` price 0.015228 % per M5 µs/step (rule 105.13); 1 % of `cs` = 65.67 M5 µs/step.

| basis | M5 µs/dispatch | implied `k` | 40 removed | 39 removed | 30 removed | status for a removal claim |
|---|---:|---:|---:|---:|---:|---|
| rule 65 marginal, **ADDED** dispatch | 2.3403 | 1.890 | 1.426 % | 1.390 % | 1.069 % | ⛔ **not quotable for a removal** |
| state-doc residue ratio | 1.7273 | 1.395 | 1.052 % | 1.026 % | 0.789 % | ⛔ exceeds the M5 residue budget |
| census-only ceiling, `N = 319` | 1.5379 | 1.242 | 0.937 % | 0.913 % | 0.703 % | ⛔ superseded — `N ≠ 319` (§1.4) |
| advisor's "conservative floor" | 1.2382 | 1.000 | 0.754 % | 0.735 % | 0.566 % | ⛔ **above the corrected ceiling** |
| **corrected ceiling, `N ≥ 411`** | **≤ 1.1937** | **≤ 0.964** | **≤ 0.727 %** | **≤ 0.709 %** | **≤ 0.545 %** | ✅ hard upper bound |
| trivial floor (overlap could be total) | 0 | 0 | 0 % | 0 % | 0 % | ✅ nothing forbids it |

**I am withdrawing the instruction I wrote in the first draft of this section.** That draft said "price a
removal at `k = 1.0` as the headline and never above `k = 1.242`". Both halves die with §1.4's dispatch
recount: once `N ≥ 411`, the ceiling is `0.964 < 1`, so `k = 1.0` is not a floor — it is *outside* the
admissible range. The corrected statement is weaker and I would rather publish the weaker true one:

> **The dispatch-glue term recovered by a removal is bounded above by ≈1.19 M5 µs/dispatch and is not
> bounded below by anything. It has no defensible point estimate from static arithmetic. The only way to
> get one is Stage 2's paired A/B delta, and that delta *is* the price — it measures glue and kernel change
> together, which is exactly what a submission is scored on.**

Consequences I will hold myself to for the rest of this assignment:

1. **No candidate is justified by its glue term alone.** At the ceiling, the largest available removal
   (40 dispatches) buys ≤ 0.727 % of `cs` = 1.82 draw bars; at any smaller overlap fraction it buys less,
   possibly nothing. A candidate that clears the bar only via glue is a candidate I cannot defend.
   ⇒ **the pick in §2 must carry kernel-time savings that stand up without the glue term.**
2. **Ranking survives untouched.** Every basis above is a single constant times the dispatch count, so
   the ordering of candidates by dispatches removed is invariant to `k`. Only the absolute headline moves.
   The brief's instruction to rank by (dispatches removed) × P(lands) is therefore still well posed.
3. **Family E's dispatch-only headline comes down from 1.069 % to ≤ 0.545 %**, and the honest way to write
   it is `[0, 0.545] %`. That is at most 1.36 draw bars and possibly zero — so family E is *not* worth doing
   for its dispatch count. It is worth doing only if the merged kernel is also faster, which §2 argues it
   is, by roughly four times more than the glue term at issue here.

### §1.7 Robustness to the α/β choice, since the M5 column is derived, not measured

Rule 105.8 class (b): §B.0.3's M5 column is `M4 × α` for bytes families and `× β` for latency ones. It is
derived, so the M5 residue inherits that assumption. Bounding it:

| assumption on the 15 kernel families | Σ kernel (M5) | residue | ÷319 | reaches 2.3403? |
|---|---:|---:|---:|---|
| as published (per-family α or β) | 3650.9 | 490.6 | 1.5379 | no |
| **every** family at α = 0.4369 (most generous) | 3537.3 | 604.2 | **1.8941** | **no** |
| every family at β = 0.5 | 4048.2 | 93.4 | 0.2927 | no |

(The `÷319` column is the census-only variant; dividing instead by the corrected `N ≥ 411` gives 1.1937 /
**1.4701** / 0.2272 respectively, so even the most generous α-everywhere reading stays below 2.3403.)

For rule 65's price to fit the ledger, the kernel families would have to convert at an effective
`k_kernel = (4141.5 − 319 × 2.3403) / 8096.3 = (4141.5 − 746.6) / 8096.3 = **0.4193**` — i.e. **below α**,
which rule 105.12 treats as the floor of the admissible range. Using the corrected `N ≥ 411` the requirement
tightens to `(4141.5 − 961.9) / 8096.3 = **0.3927**`. **The ceiling result is therefore robust to the α/β
choice, and robust in the same direction under the dispatch recount: rule 65's marginal price cannot be the
average resident-dispatch price under any admissible conversion.**

### §1.8 One reconciliation I am flagging rather than resolving — tanjiro's `k_residue`

The advisor's comment reports tanjiro closing his ledger with `k_issue = α` to get
`k_residue = 1.4998, CI [1.4732, 1.5275]`. Note the digit collision: my **ceiling is 1.5379 M5 µs/dispatch**,
his is a dimensionless **k of 1.4998**. Different units; do not conflate them. Taken as a `k`, his value
implies `1.4998 × 1.2382 = 1.857 µs/dispatch`, needing `319 × 1.857 = 592.4` against a 490.6 residue — a
21 % over-run of the same budget. So his route and mine disagree by about that much, and both disagree with
1.890. I have not reconciled them; the two ledgers partition decode time differently (his closes an
issue/bytes/latency decomposition, mine closes `T_M5 −` census). **Flagged for the advisor, not resolved by
me** — but note that all three routes now agree on the *direction*: the resident per-dispatch price is
**below** the marginal added-dispatch price.

### §1.9 Summary of deliverable A in one line

> The fiction correction is invalid (headroom subtracted from a time column, and rule 100 says the time is
> real *because* it is incompressible). The replacement closure is a budget, not a corroboration: the
> census's 15 families leave a residue of **351.7 M4 / 490.6 M5 µs/step**, and rule 65's marginal added-dispatch
> price over-runs that budget by **52 %** at the census's own 319 dispatches. The census is also **not** the
> whole ledger — I found ≥ 92 uncensused decode dispatches, so `N ≥ 411`, which drops the per-dispatch glue
> ceiling to **≤ 1.1937 M5 µs/dispatch, `k_removal ≤ 0.964`** and leaves **no floor at all**. Removal
> asymmetry is real and points the conservative way; the practical consequence is that **a dispatch removal
> has no static point price, so no candidate in §2 may be justified by its dispatch count alone.**

The three numbers to carry forward, tagged per rule 105.8:

| quantity | value | tag |
|---|---|---|
| dispatch-glue ceiling per removal | **≤ 1.1937 M5 µs/dispatch** (`≤ 0.8557 M4`) | derived from census residue · M5 column is class (b) derived · epoch #561 two-pool map |
| implied `k` for removal | **`[0, 0.964]`**, point estimate unknown | supersedes rule 105.13's `k_dispatch ∈ [1.0, 1.890]` **for removals only** |
| total decode dispatches / step | **≥ 411** (census 319 + ≥ 92 uncensused, §1.4 table U) | measured live on M4, this host, 2026-08-10 |

---

## §2 Deliverable B — the ranked adjacent-pair dispatch ledger

All line numbers are `Sources/MLXFastModel/LagunaRuntimeModel.swift` at HEAD unless another file is named.
All timing quantities are tagged per rule 105.8; the M5 column of §B.0.3 is class (b) derived
(*M4 ×0.4369 bandwidth-pool / ×0.5 latency-pool two-pool map, residual −6.63 %, #561*).

### §2.0 Method

The brief asks for **adjacent pairs**, i.e. producer→consumer. I enumerated the decode step's dispatches from
the call graph rooted at the decode attention block (`:5895`–`:6015`) and the decode MoE block
(`:11180`–`:10990` call order), checked each pair against the live fusion witness
(`research/artifacts/maple-frieren-r108k/fusion-active-decode.txt`, captured 16:20Z on this host), and then
read the launcher of both sides to establish the *grid relationship*, which is what decides whether a merge is
possible at all. Every candidate below was rejected or accepted on source evidence, not on plausibility.

### §2.1 The taxonomy in the brief is missing a class, and the winner is in the missing class

The brief's dependency-scope column offers **TG-local** (consumer's threadgroup can read what the producer's
threadgroup produced) vs **grid-wide** (needs a device-wide sync, therefore needs a second dispatch anyway).
There is a third relationship that is *strictly better than TG-local*:

| class | relationship | sync needed inside the merged kernel | merge cost |
|---|---|---|---|
| **SIBLING** (new) | both dispatches read the *same* input; neither reads the other's output | **none — not even `threadgroup_barrier`** | grid concatenation only |
| TG-local | consumer TG reads only what its own TG produced | `threadgroup_barrier` | tile-map must be made to agree |
| grid-wide | consumer needs values produced by other TGs | device-wide sync ⇒ impossible in one dispatch | — |

I am adding the row because the decode step's single largest removable dispatch family turns out to be a
sibling, not a producer→consumer pair, and the brief's ranking rule would have thrown it away.
The sibling class also **passes tanjiro's #48 gate trivially and by construction**: PR #48 reduced dispatch
count and lost 0.1488 % because the consumer still round-tripped its producer's output through device memory.
A sibling merge introduces **no new value that crosses the kernel boundary at all** — there is no producer
output to round-trip — so the #48 failure mode is not merely mitigated, it is absent.

### §2.2 The ledger

Ranked by (dispatches removed) × P(lands by 04:00Z). "size" is net growth in
`Sources/MLXFastModel/LagunaRuntimeModel.swift` (rule 105.14 budget: that file is at 384,245 of 524,288 B, and
I have self-capped at 30,000 B).

| # | pair (producer → consumer) | wrappers, `file:line` | dispatches removed / step | scope | 105.15 class | size (lines / bytes) | collision | verdict |
|---|---|---|---:|---|---|---|---|---|
| **M2** | **`lagunaGateSoftplus` ∥ `lagunaDecodeNVFP4QKVR1`** (siblings on `normalized`) | `:4525` and `:5002`; kernel sources `:4467`, `:4922`; call sites `:5994`, `:5953` | **40** (30 h64 + 10 h48) | **SIBLING** | **1** (source-argument bit-exact) | ≈ +75 / **+3,200 B** | ⚠️ **edward #629** owns `:4922` | ✅ **PICK** |
| M3 | `inputNorm` (MLX `rms_norm`) ∥ `lagunaGateSoftplus`, 3-way with M2 | `:5950` and `:4525` | 40 | SIBLING → but rewrites a norm | **2** (must match MLX's reduction order) | ≈ +60 / +2,400 B | ⚠️ edward #629 (if folded into M2) | ⏸ mutually exclusive with M2, class 2, unpriced |
| M4 | `laguna_decode_router_top8` → `lagunaResidualRMSNormRouter` (T1a) | `:10291`/launcher `:9597` → `:1192`, source `:929` | 39 | **grid-wide** | **2** | ≈ +120 / +5,000 B | ✅ none (unowned) | ❌ grid-wide ⇒ not removable in one dispatch |
| M5 | `lagunaGateSoftplus` → `lagunaGatedAffineOProjNVFP4` (true producer→consumer) | `:4525` → `:4586`, source `:4222` | 40 | **grid-wide** | 2 | large | ⛔ **alphonse #644** | ❌ scope + collision |
| M6 | `inputNorm` → `lagunaDecodeNVFP4QKVR1` | `:5950` → `:5002` | 40 | SIBLING-able but compute-negative | 2 | ≈ +40 / +1,600 B | ⚠️ edward #629 | ❌ arithmetic below |
| M7 | `inputNorm` → previous layer's `lagunaRoutedSharedDownResidual` (T2d) | `:5950` → `:8578` | 40 | **grid-wide** | 2 | large | ⛔ tanjiro/edward adjacency | ❌ scope |
| M1 | *(not a merge)* re-quantize the gate bank so `foldGateIntoBank` fires at `:5713` | `:5713`–`:5726` | 40 | n/a — deletes the dispatch by config | 2 at best (**precision loss**) | ≈ +10 / +400 B | ✅ none | ❌ quality risk, §2.4 |

Nothing in the decode step is TG-local in the brief's sense. **The kill rule in the brief therefore reduces to
its second clause**, and it is satisfied: there is one candidate — M2 — whose design is written in full below,
well before the 21:00Z gate. So the answer to the Stage-1 gate is *not* `N-MERGE-UNREACHABLE`.

### §2.3 The pick — M2, and why the pair exists at all

#### §2.3.1 Family E is a dispatch created by a quantization-format mismatch, not by a data dependency

Reading the weight-preparation path at `:5713`:

```
let foldGateIntoBank = gate != nil && q.groupSize == 32 && q.bits == 8 && q.mode == .affine
if foldGateIntoBank, let gate { … _nativeAffineQKVGateRows = nHeads }   // :5719, :5724
else { _nativeAffineGProj = gate }                                      // :5726
```

The decode QKV bank is **NVFP4 / 4 bits / groupSize 16**, so `foldGateIntoBank` is `false`, so the gate weight
lands in `_nativeAffineGProj` and gets **its own dispatch** at `:5994`. Downstream at `:5979` the code says so
explicitly: *if* the gate rows had been folded into the QKV bank, `gateLogits` would simply be a slice
`qkv[.ellipsis, gateStart ..< gateStart + nHeads]` — **zero dispatches**. Family E's 40 dispatches per step
exist only because the two banks are quantized differently. That is a packaging accident, and it is the
cleanest kind of dispatch to attack.

#### §2.3.2 The two dispatches are **siblings**, verified from the call site

```
let normalized = fusedQKV ?? inputNorm(input)                                   // :5950
… lagunaDecodeNVFP4QKVR1(normalized: normalized, bank: fusedAffine, heads: nHeads)  // :5953
… lagunaGateSoftplus(input: normalized, bank: affineGate, heads: nHeads)            // :5994
```

`fusedQKV` is `nil` on this build — its guard at `:5926`–`:5931` requires an **affine/8/gs32** QKV bank and the
fusion witness contains no `norm+affine qkv` line while it does contain
`decode nvfp4 qkv r1 h64 lane-major` and `decode nvfp4 qkv r1 h48 lane-major`. So `normalized = inputNorm(input)`,
one device array, and **both kernels take it as their only data input**. Neither reads the other's output:
`qkv` becomes Q/K/V, `activated` becomes `gateLogits` for the oproj. Two independent consumers of one producer
⇒ a merge needs **no synchronisation of any kind**.

#### §2.3.3 Bit-exactness: class 1, by a source-level argument, no certificate required

Both kernels launch **64 threads per threadgroup** (`threadGroup: (64,1,1)` in both launchers, verified at
`:4525` ff. and `:5002` ff.). Because the widths match exactly, the gate branch can be transplanted
*verbatim*: same `NS = 2`, `R = 4`, `BK = 256`, `KG = 64`, `SS = 4`, same lane↔column map
(`x[i] = float(input[col+i])`, `i` in `0..7`), same per-row inner product `a = Σ x[i]·wl[i]`, same
accumulator update `r[row] += s·a + sum·b`, same `simd_sum(r[row])` over 32 lanes, same `lane == 0`
finalisation including the `bfloat` round-trip `l = float(bfloat(r[row]))`, the NaN guard, and the softplus
form `g = (isinf(lo) || isinf(hi)) ? hi : hi + log1p(exp(lo − hi))`. Every floating-point operation happens in
the same order on the same values, so the result is bit-identical for source-argument reasons —
**105.15 class 1**, which under rule 102 satisfies the draw bar's correctness requirement without spending a
margin certificate. (I still intend to run one, because it is my own instrument and it costs 307 s; but the
claim does not depend on it.)

#### §2.3.4 The design

Extend `lagunaDecodeNVFP4QKVLaneMajorSource` (`:4922`) with a tail of gate tiles and widen the grid:

| | h64 layers (30/step) | h48 layers (10/step) |
|---|---:|---:|
| QKV tiles today (`rows = (heads + 2·8)·128`, 2 rows/tile) | 5,120 | 4,096 |
| gate tiles added (`heads/8`) | 8 | 6 |
| merged grid | **5,128** | **4,102** |

```
if (tile >= QKV_TILES) { tile -= QKV_TILES;  <gate_sp body, verbatim> }
else                   { <existing lane-major QKV body, unchanged> }
```

Launcher changes: bind three extra input buffers (gate `packedCodes`, `scales`, `biases`) and one extra output
(`gate_values`, `[[1,1,heads]]` bfloat16), pass `QKV_TILES` as a constant, return a tuple. Call site: pass
`affineGate` into `lagunaDecodeNVFP4QKVR1` and take `gateLogits` from the second return value; keep the
existing `:5994` path alive behind an env flag so Stage 2 has a real A/B arm rather than a rebuild-vs-rebuild
comparison.

Grid-order note for the record: the gate tiles go **after** the QKV tiles so that the existing tile→row map is
untouched; the added tiles are the only new indices, and each writes a disjoint 8-element slice of
`gate_values`, so there is no write aliasing to reason about.

#### §2.3.5 The prize, priced in the mixed regime

This is the part the brief cares about, and it is **not** a dispatch-count argument — §1.6 forbids that. It is
a kernel-time argument that happens to also remove 40 dispatches.

*Removed:* family **E** (T2b gate_sp h64, 30 calls, **248.0 M4 µs/step**) + **E'** (T2b' h48, 10 calls,
**80.2 M4 µs/step**) = **328.2 M4 µs/step**, both **latency-regime** at 10.4 % and 8.0 % of M5 peak bandwidth.
The census's own M5 column gives **164.1 M5 µs/step** for the pair.

*Added:* the gate bank must now be read by the QKV kernel. Per h64 call: codes 64×2048/4×4 = 131,072 B +
scales 64×64×2 = 8,192 B + biases 8,192 B = **147,456 B** (the 4,096 B `input` row is already read by the QKV
kernel, so it is free). Per h48 call: **110,592 B**. At this host's measured 266.3 GB/s (rule 76 rev 2) that is
0.5537 and 0.4153 M4 µs ⇒ **+20.8 M4 µs/step**, i.e. **+1.18 % on a kernel that is 90.8 % bandwidth-bound** —
so it converts at α: **+9.1 M5 µs/step**. Cross-check from the other direction: the gate work is
64×2048 = 131,072 MACs against the QKV kernel's 10,240×2,048 = 20.97 M MACs = **0.63 %**, and 1.2 % of the
QKV pair's 1,702.9 M4 µs is 20.1 µs — the two estimates agree to 3 %.

| accounting of the census's per-family M4 µs | net M5 µs/step | % of `cs` | + glue `[0, 0.727] %` |
|---|---:|---:|---|
| (a) pure GPU execution, removed at β = 0.5 | 155.0 | **2.361 %** | [2.361, 3.088] % |
| (a′) same, but removed converted at α = 0.4369 (sensitivity) | 134.3 | 2.045 % | [2.045, 2.772] % |
| (b) wall-clock **inclusive** of glue ⇒ subtract 40 × 1.2382 M4 first, at β | 130.3 | 1.984 % | [1.984, 2.711] % |
| (b′) inclusive, at α | 112.7 | **1.716 %** | [1.716, 2.443] % |

**Headline I am willing to defend: `+1.7 % to +3.1 % of cs`, point estimate ≈ 2.0 %**, which is
**8.7× to 15.7× the de-biased L3 bar of 0.1966 %** (rule 105.10) and 4.3–7.7 draw bars. Even at **20 %
realisation** the lowest cell still clears the L3 bar by 1.7×.

Three reasons to distrust my own number, stated up front:

1. **It is larger than the entire gap to the record.** The unbiased gap is 1.6359 % (z = 5.42). A single arm
   worth 2 % would not merely tie, it would take the record outright, and no arm this campaign has been worth
   more than ≈0.18 %. The prior against 2 % is strong and I am not asking anyone to believe it before the
   paired measurement exists.
2. **Row (b) is not a caveat, it is a live possibility.** If tanjiro's per-family M4 µs are wall-clock spans
   between kernel-start timestamps, they already contain the rule-57 glue and the glue column double-counts.
   That is why the table shows both accountings and why the honest headline is the union of all four cells.
3. **Latency-regime savings are the least reliable kind.** 8.27 µs/call for a kernel doing 0.63 % of the QKV
   kernel's arithmetic on 512 threads means almost all of it is fixed launch/ramp cost — and fixed cost is
   exactly the quantity whose M4→M5 conversion the two-pool map is worst at. β = 0.5 is an assumption here,
   not a measurement, which is why row (a′) exists.

#### §2.3.6 Size, and the byte budget

Measured sizes of the four regions involved: gate source generator `:4467`–`:4524` = 58 lines / 1,930 B; gate
launcher `:4525`–`:4585` = 61 / 2,637; lane-major QKV source `:4922`–`:5001` = 80 / 2,939; QKV launcher
`:5002`–`:5066` = 65 / 2,719. Transplanting the gate body as a branch costs ≈ +1,900 B, launcher and call-site
plumbing ≈ +1,300 B, and I keep the old path ⇒ **net ≈ +3,200 B, hard self-cap +7,000 B**, against my 30,000 B
self-allocation and the file's 140,043 B of remaining headroom. (Deleting the old path afterwards would
*return* ≈4,500 B, but that is fern's call at integration, not mine.)

#### §2.3.7 ⚠️ Collision — flagged, not negotiated

`lagunaDecodeNVFP4QKVLaneMajorSource` (`:4922`) and its launcher (`:5002`) are **maple-edward's region under
PR #629**, which owns `lagunaRoutedSwiGLUQMVPackedTop8` (`:8030`) *and*
`lagunaDecodeNVFP4QKVLaneMajorSource` (`:4922`). Per the 15:45Z deconfliction instruction I am flagging this
and doing nothing else about it. Facts the advisor may want at the 21:00Z gate:

* M2 touches `:4922` only by **appending a branch guarded by `tile >= QKV_TILES`**; the existing body is not
  edited, so a textual merge with edward's arm is plausible but not free.
* M2 also touches `:5002` (launcher signature), `:5994`/`:5953` (call site) and the kernels dict — those are
  unowned.
* If the advisor prefers zero collisions, the only collision-free candidate with a comparable dispatch count
  is **M4** (39 dispatches, unowned), and M4 is **grid-wide and class 2**, i.e. I do not believe it is
  implementable at all. There is no collision-free version of this assignment's best idea.

### §2.4 M1 rejected — the cheapest way to delete family E is a precision cut

`foldGateIntoBank` (`:5713`) fires when the QKV bank is affine/8/gs32. One could instead re-quantize the gate
bank to match the QKV bank's **NVFP4 / 4 / 16** and fold it in, deleting all 40 dispatches with ~10 lines and
**no new kernel code at all**. I am rejecting it: it lowers the gate projection from 8-bit affine to 4-bit
NVFP4, which changes output values, cannot be class 1, and puts token-identity on the golden fixture at risk
for a gate that feeds a `softplus` and then multiplies the oproj — a place where a small perturbation is
amplified. Rule 105.15's real gate is exact token-ID equality (`Golden.swift:387`, `:535`); I will not spend
Stage 2 gambling on it.

### §2.5 The routes I evaluated and rejected, with the arithmetic

**M6 — fold `inputNorm` into the QKV kernel.** Tempting (removes 40 uncensused dispatches, and the shipped
`lagunaNormAffineQKV` at `:5488` already does exactly this for the 8-bit affine bank). Rejected on arithmetic:
the QKV kernel launches **5,120 threadgroups** for h64, and each would have to redundantly reduce the whole
2,048-element row to get the RMS. That is 5,120 × 2,048 ≈ 10.5 M extra element-reads and adds ≈ 50 % to the
kernel's arithmetic (its real work is 20.97 M MACs) plus ≈ 20 MB of L2 traffic per call — on a kernel already
at 90.8 % of peak bandwidth. Compute- and bytes-negative. `lagunaNormAffineQKV` gets away with it because its
grid is organised around whole rows, not 2-row tiles.

**M3 — the 3-way merge `inputNorm` + gate_sp + (nothing else).** This one is genuinely attractive and I want
it on the record. All 8 gate threadgroups **already read the entire 2,048-element `input` row**, so each could
compute the RMS redundantly (8 × 2,048 reads, negligible) and write a disjoint 256-element slice of
`normalized`. It removes the same 40 dispatches with a *smaller* kernel change than M2. Two problems:
(i) it is **class 2** — it replaces MLX's `rms_norm` reduction tree with mine, so bit-exactness needs a
certificate rather than an argument; (ii) it is **mutually exclusive with M2**, because M2's merged kernel is a
*consumer* of `normalized`. Its prize is also much smaller: it removes only glue plus one small kernel,
≈0.61–0.91 % of `cs` at the ceiling, versus M2's 1.7–3.1 %. **Held as the fallback if the advisor rules the
edward collision fatal**, since it does not touch `:4922`.

**M4 — router top-8 into T1a.** The only collision-free 39-dispatch candidate, so I checked it hard.
`lagunaResidualRMSNormRouter` (`:1192`, source `:929`, kernel `:1131`) launches `tiles = 256 / rowsPerGroup`
threadgroups × 512 threads, and the default `rowsPerGroup = 8` ⇒ **32 threadgroups**. The 256 router logits are
therefore spread across 32 threadgroups, and a top-8 over all 256 needs a device-wide reduction ⇒ a second
dispatch. Could `tiles == 1`? No: the legal `rowsPerGroup` set is `[1, 2, 4, 8, 16, 32, 64]` (`:676`), so 256
rows can never be one group; and changing `rowsPerGroup` changes the per-row reduction tree, which breaks
bit-exactness anyway. **Grid-wide, class 2, rejected.**

**M5 — gate_sp into its actual consumer, the oproj.** This is the only true producer→consumer pair in the
attention block. `lagunaGatedAffineOProjNVFP4` (`:4586`) launches 256 threadgroups × 64 threads for h64, and
each one needs the *whole* gate vector, so each would have to re-read the entire gate bank — 256 × 147,456 B.
Grid-wide, and it collides with alphonse #644. Rejected twice over.

**M7 — `inputNorm` into the previous layer's T2d.** `lagunaRoutedSharedDownResidual` (`:8578`) launches 512
threadgroups × 288 threads and its output row is spread across all of them, so the norm's reduction is
grid-wide. Rejected on scope.

**MoE side, for completeness.** The decode MoE block's per-layer dispatch set is exactly 4 censused (T1a
`:11180`; shared gate+up `lagunaSharedSwiGLUQMV` `:8999`/`:9145`; routed gate+up
`lagunaRoutedSwiGLUQMVPackedTop8` `:10856`; T2d `:10923`) + 1 uncensused (router top-8 `:10291`). `weights` is
consumed by T2d, so the top-8 kernel always fires, and the cast-sink+norm-sink path returns early, so there
are no extra divide dispatches to harvest. Every remaining adjacency there is grid-wide for the same reason
M4 is: expert selection is a reduction over 256 logits spread across threadgroups.

### §2.6 Corrections to the census that this ledger depends on

I need these on the record because §2.3.5 prices family E off tanjiro's numbers and two of them are wrong in
my favour, which is exactly when a correction must be published.

| # | census claim (#648) | corrected | effect |
|---|---|---|---|
| C1 | family E runs "30 threadgroups, ~1,920 threads" | **8 threadgroups × 64 threads = 512 threads** (h64); 6 × 64 = 384 (h48). The launcher is `grid: ((heads/8)·64, 1, 1)`, `threadGroup: (64,1,1)`, `:4525`. The "30" was the **call count**, put in the threadgroups column. | **strengthens** his LATENCY verdict — the kernel is even more launch-dominated than he claimed |
| C2 | family E reads 262,144 B/call ⇒ 0.98 M4 µs of bytes | **151,552 B/call** (codes 131,072 + scales 8,192 + biases 8,192 + input 4,096) ⇒ **0.569 µs**; h48 114,688 B ⇒ 0.431 µs | non-bytes share of the 8.27 µs/call rises from 88 % to **92.6 %**; for E+E' together, bytes are 21.4 of 328.2 M4 µs = **93.5 % non-bytes** |
| C3 | "rule 65's +2.3403 plus rule 55's 3.97 explain ~6.3 of the missing 7.3" | **units error**: rule 55 (state doc `:3551`) is `t = 3.97 µs + bytes/266.3 GB/s`, an **M4, in-kernel** model whose intercept lives *inside* measured kernel time; rule 65's 2.3403 is an **M5, out-of-kernel** cost. Sanity check: 319 × 3.97 = 1,266.4 M4 µs against an M4 residue of only 351.7. | his **substance survives** (E is mostly fixed launch/ramp cost) but the decomposition cannot be quoted as arithmetic |
| C4 | (not claimed) QKV lane-major grid | **5,120 threadgroups** for h64 (`rows = (64 + 16)·128 = 10,240`, 2 rows/tile), 4,096 for h48 | this is what kills M6, and what makes M2's 8 extra tiles negligible |
| C5 | family E's dispatch-only value 1.069 % of `cs` | **`[0, 0.545] %`** (§1.6) | family E is **not** worth doing for its dispatch count; M2 is worth doing for its kernel time |

I reproduced his E decomposition exactly before disagreeing with it: in-kernel recoverable per call
= 8.27 − 0.98 − 1.2382 = 6.05 M4 µs; × 30 = 181.5 → × 0.5 = 90.76 M5 = 1.382 %; + 1.069 % dispatch = 2.451 %,
and his 218.6 M4 µs/step = 30 × (8.27 − 0.98). So the disagreement is about C2 and C5, not about his method.

### §2.7 Stage-1 recommendation (formally due 21:00Z; recorded now so it is not a post-hoc choice)

> **Pick M2: merge `lagunaGateSoftplus` into `lagunaDecodeNVFP4QKVR1` as a sibling grid-concatenation.**
> It removes the most dispatches available anywhere in the decode step (40/step, more than any censused
> family), it is the only candidate that needs **no synchronisation at all**, it is the only candidate that is
> **105.15 class 1 by a source-level argument**, it is small (+3,200 B), and its value does not rest on the
> dispatch-glue term that §1 just demoted to a ceiling — it rests on 328.2 M4 µs/step of latency-regime kernel
> time that exists only because two weight banks are quantized differently. It passes tanjiro's #48 gate by
> construction, because no value crosses the kernel boundary. **The one thing wrong with it is that
> `:4922` belongs to maple-edward under #629, which I am flagging and not negotiating.**

Preregistered before any timing run (extending §0, and not extendable afterwards):

* **Arms:** baseline = HEAD-with-M2-compiled-but-env-disabled; candidate = same tree, M2 enabled. Same binary,
  so rule 105.15's build-identity trap and my own cert's `0_build_identity` VOID both stay clean.
* **Instrument:** nezuko's, PR #657 (CI95 half-width ≈ 0.1178 % of `cs` at 10 blocks, versus fern's ABBA at
  0.2666 %). **I will not build a third instrument.**
* **Mandatory:** `FERN_DEFEAT_SLOTS=64` (rule 98.9) — tanjiro measured 4.86× issue-exposure distortion when
  resident, and family E is a *pure* issue/latency kernel, so the resident measurement would flatter it most.
* **Stopping rule:** report whatever the CI says at 04:00Z. A CI that includes zero is reported as
  `N-REMOVAL-ASYMMETRIC` if the point estimate is below the draw bar, and as a null cell either way
  (rule 79). I am not extending the four preregistered outcomes.
* **What I need from the advisor at the gate:** (1) adjudication of the `:4922` collision with edward;
  (2) confirmation that ≈3,200 B in `LagunaRuntimeModel.swift` is within my allocation; (3) go/no-go for
  Stage 2. Absent (1), my fallback is **M3**, which touches nothing edward owns but is class 2 and worth
  roughly a quarter as much.

---

# §3 Stage 1 — the barrier-region price probe (advisor #660 comment 6; reported 19:00Z)

**§2.7 is withdrawn as an action.** Comment 6 said *stop before you build*, and the probe it
ordered has now run. This section replaces the Stage-1 build with the measurement, and its
conclusion is that the merge should **not** be built.

## §3.1 What comment 6 asked, and what I confirm

The advisor's mechanism claim was that MLX encoders are created
`DispatchTypeConcurrent` and that barriers fire only on a true RAW hazard, so
`lagunaGateSoftplus` and `lagunaDecodeNVFP4QKVR1` — two siblings that both read
`normalized` and neither of which reads the other's output — **already overlap**, and M2
would therefore remove a dispatch that costs nothing while risking PR #48's
register-allocation-union occupancy loss.

**I confirm the advisor's `device.cpp` reading at source level. It is correct, and I am
not disputing it.** The encoder is created with `MTL::DispatchTypeConcurrent`
(`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp:545-548`);
`set_input_array` raises `needs_barrier_` only when the input is found in
`prev_outputs_` (`:319-325`); `maybeInsertBarrier` emits
`memoryBarrier(BarrierScopeBuffers)` only when that flag is set, and on emitting it does
`prev_outputs_ = std::move(next_outputs_)`, so the previous generation is dropped
(`:363-375`). For the M2 pair the hazard set never contains the sibling's output, so **no
barrier is emitted between QKV and gate_sp**. One detail comment 6 omitted, which does not
change the conclusion: `register_output_array` also tracks a WAR hazard against
`prev_inputs_`, so buffer *recycling* by the allocator can serialize two logically
independent kernels. That is a hazard-management bug class, not a dispatch-count one.

## §3.2 The instrument, and the one thing it cannot do

Arms, all via `./benchmark.sh --local-submit` (rule 86 forbids `--local-iterate` as
evidence), fixed order `GCFSCSFCHJCFSCSFCJH`, six control-anchored blocks of three:

| arm | injected no-ops/step | `CHAIN` | meaning |
|---|---|---|---|
| `C` | 0 | — | control anchor, one per block |
| `F` | 160 | 0 | **concurrent** extra dispatches, no barrier |
| `S` | 160 | 1 | **serialized** extra dispatches, RAW chain ⇒ barrier each |
| `H` | 1200 | 0 | concurrent, high rung |
| `J` | 1200 | 1 | serialized, high rung |
| `G` | 2400 | 1 | gauge / liveness only (amendment §3) |

The injected kernel is `laguna_inject_empty_dispatch_v1`
(`Sources/MLXFastModel/LagunaRuntimeModel.swift:12037-12049`): 8 threadgroups × 256
threads, whose body is one buffer load and a comparison against `0xFFFFFFFFu` that is
never true. Its arithmetic is negligible by construction, so what it prices is dispatch
overhead, not work. Nothing is elided: `CustomKernel::eval_gpu` dispatches unconditionally
(`.../metal/custom_kernel.cpp:117`) and the guard is a runtime device read.

### §3.2.1 The confound, recorded in amendment §9 before any device time

`lagunaInjectLayerWork` is invoked at `:11715`, after the layer body, and ends in its own
`asyncEval(pending)` at `:12143`. An MLX eval boundary runs `gpu::finalize`, i.e.
`end_encoding()` then `commit()` (`.../metal/eval.cpp:71-77`, `device.cpp:456-465`,
`:526-529`), and the injected roots depend only on pre-evaluated inputs, so the injected
tape is encoded **alone**. `DARKBLOOM_INJECT_EMPTY_SPREAD` defaults to 1 (`:11971-11972`),
so with 40 layers injecting, the knob adds up to 40 extra encoders *and command buffers*
per step.

Two source facts make that confound **N-independent**, which is what saves the probe:

1. `lagunaInjectLayerWork` opens with `guard !pending.isEmpty else { return }` (`:12142`),
   so the control arm **never reaches** `asyncEval` at all. The eval boundary is not a
   shared cost that differences away between C and an injected arm; it is present in every
   injected arm and absent in C.
2. `lagunaInjectShare` (`:12105-12107`) spreads the requested total across all 40 layers
   under `SPREAD=1`, so the *number* of extra eval boundaries is **40 per step for every
   injected arm**, independent of the injected count `N`. The split is the cumulative
   difference `(layer + 1) * total / layers - layer * total / layers` (`:12091`), which sums
   to `total` exactly and is nonzero for every layer at both `N = 160` and `N = 1200` — so no
   layer opts out at the low rung, which is the case that would have broken the cancellation.

Because fact 2 carries the entire rung-difference estimator, I had it re-read from source by
an independent agent with no knowledge of my hypothesis. It returned the same four readings,
including the `:12091` arithmetic above, the `:12137` (N appends, unchained) versus `:12140`
(one append, chained) split, and the confirmation that exactly one `asyncEval` runs per layer
per step for any nonzero total. That is corroboration of the *source reading*, not of the
measurement.

So each injected arm measures

```
d(N)  =  N · k  +  40 · c
```

where `k` is the wanted per-dispatch tax and `c` is the per-layer eval-boundary term. That
is one equation in two unknowns: **the pre-registered single-rung estimator is degenerate.**

### §3.2.2 🚫 Self-correction — I assumed the confound's sign, and the data refuted it

Amendment §9 and the first draft of this section asserted that `40 · c > 0`, i.e. that the
extra encoder and command buffer *inflate* the measured cost, making a single rung an
**upper bound** on `k`. On that reading a null arm F would have killed the merge programme
outright.

**That was wrong, and it is the one claim in this report I am retracting rather than
defending.** Both 160-dispatch arms measure *faster than control* (§3.3), by about
`-90 µs/step`. No positive per-dispatch tax and no positive encoder cost can produce a
negative total, so `c < 0`: adding an eval boundary per layer **helps** decode on this host.
Session drift is measured at only about `-11.5 µs/run` (§3.3), which accounts for roughly an
eighth of the gap, and the blocks are not physically separated, so this is structural, not
positional.

The consequence is a genuine narrowing of what a single rung can conclude:

* A **null** arm F no longer kills the programme. With `c < 0`, `d(160) ≈ 0` is equally
  consistent with `k = 0` and with a real positive `k` masked by the negative boundary term.
* A **positive** arm F still does not license the merge, for the original reason: the effect
  could be encoder/command-buffer overhead that an in-encoder merge cannot recover.

Both of comment 6's branches are therefore unreachable from one rung, which is why the probe
carries a second rung at 1200 and why the **rung difference**

```
k  =  ( d(1200) − d(160) ) / 1040
```

is the decisive estimator: the `40 · c` term is identical at both rungs and cancels exactly,
without needing to know its sign or size. It was pre-registered as a post-hoc estimator in
amendment §10 together with its out-of-sample predictions, before either high-rung arm ran.

<!--RESULTS:BEGIN-->
## §3.3 Results

`15` usable runs, `0` voided. Every run is a full `./benchmark.sh --local-submit`, so every row below also carries an exact-token-ID correctness pass.

### Raw levels

| block | arm | injected/step | chain | decode µs/step | prefill µs/token | gate |
|---|---|---|---|---|---|---|
| 0 | `G` | 2400 | 1 | 11761.7 | 1111.72 | pass |
| 1 | `C` | 0 | NA | 9001.6 | 1122.76 | pass |
| 1 | `F` | 160 | 0 | 8901.4 | 1111.05 | pass |
| 1 | `S` | 160 | 1 | 8895.5 | 1123.02 | pass |
| 2 | `C` | 0 | NA | 8967.0 | 1111.62 | pass |
| 2 | `S` | 160 | 1 | 8881.2 | 1137.99 | pass |
| 2 | `F` | 160 | 0 | 8885.6 | 1122.64 | pass |
| 3 | `C` | 0 | NA | 8961.9 | 1116.69 | pass |
| 3 | `H` | 1200 | 0 | 9349.1 | 1111.47 | pass |
| 3 | `J` | 1200 | 1 | 9351.3 | 1111.07 | pass |
| 4 | `C` | 0 | NA | 8970.5 | 1112.54 | pass |
| 4 | `F` | 160 | 0 | 8908.0 | 1111.32 | pass |
| 4 | `S` | 160 | 1 | 8880.2 | 1123.02 | pass |
| 5 | `C` | 0 | NA | 8959.1 | 1122.32 | pass |
| 5 | `S` | 160 | 1 | 8865.9 | 1116.58 | pass |

### Gauge (liveness only — amendment §3)

Arm `G` (2400 chained) moves decode `+2789.7` µs/step (`+1.1624` µs/dispatch) against the pooled controls; threshold is `≥ +500` µs/step ⇒ **PASS**. This confirms the channel is live and nothing is elided. It is **not** an estimate of a per-dispatch tax; see §3.4.

### Pre-registered estimators (block-paired, Student-t CI95)

| rung | estimator | µs/step | slope, M4 µs/dispatch | blocks |
|---|---|---|---|---|
| 160 | dF — concurrent, no barrier | -81.36 [-128.2, -34.55] | -0.5085 [-0.8011, -0.2159] | 3 |
| 160 | dS — serialized, barrier per dispatch | -93.88 [-107.8, -79.99] | -0.5867 [-0.6735, -0.5] | 4 |
| 160 | **dS − dF, paired ⇒ barrier price** | -12.72 [-45.19, +19.75] | -0.0795 [-0.2824, +0.1234] /barrier | 3 |
| 1200 | dH — concurrent, no barrier | +387.1 (n=1, no CI) | +0.3226 (n=1, no CI) | 1 |
| 1200 | dJ — serialized, barrier per dispatch | +389.4 (n=1, no CI) | +0.3245 (n=1, no CI) | 1 |
| 1200 | **dJ − dH, paired ⇒ barrier price** | +2.232 (n=1, no CI) | +0.00186 (n=1, no CI) /barrier | 1 |

### Post-hoc drift control (exploratory, not pre-registered)

Injection is decode-only, so any prefill move within a block is host drift that also multiplies decode. Subtracting it removes the common-mode term.

| arm | rung | drift-corrected slope, M4 µs/dispatch | blocks |
|---|---|---|---|
| `F` | 160 | -0.4777 [-1.791, +0.8361] | 3 |
| `H` | 1200 | +0.3575 (n=1, no CI) | 1 |
| `J` | 1200 | +0.362 (n=1, no CI) | 1 |
| `S` | 160 | -0.9827 [-2.053, +0.0875] | 4 |

### Post-hoc rung-difference estimator (the decisive one)

An injected arm differs from its control by `N` dispatches **and** by one `asyncEval` per layer (`:12143`), which arm `C` never reaches (`guard !pending.isEmpty`, `:12142`). So `d(N) = N·k + 40·c`: one equation, two unknowns, and a null `d(N)` is equally consistent with `k = 0` or with a positive `k` masked by a negative `c`. `lagunaInjectShare` (`:12105-12107`) spreads every rung over all 40 layers, so `40·c` is identical at `N = 160` and `N = 1200` and cancels in the difference.

| ladder | k, M4 µs/dispatch | implied eval-boundary c | blocks |
|---|---|---|---|
| unchained / concurrent (F→H) | +0.4505 [+0.3992, +0.5017] | -3.84 µs/layer (-153 µs/step) | 1 |
| chained / serialized (S→J) | +0.4647 [+0.415, +0.5143] | -4.21 µs/layer (-168 µs/step) | 1 |
| chained cross-check via gauge (S→G) | +1.2873 | -7.50 µs/layer (-300 µs/step) | pooled |

### Verdict

**P-INDETERMINATE-UNDERPOWERED — 3 block(s) < 4 required; arm F slope -0.5085 [-0.8011, -0.2159] M4 us/dispatch**
<!--RESULTS:END-->

Everything above the line is machine-generated from the sink by
`research/maple-frieren-r108k-insert-results.py`, verbatim and including the mechanical
verdict, so that the estimator I am about to disown is on the record rather than quietly
dropped.

### 🚩 The mechanical verdict is wrong, and this is the one verdict I report

**Reported verdict: `P-INDETERMINATE`.**

The generated line prints the §5 rule as written: it looks at arm `F`'s single-rung slope,
notices fewer than 4 blocks, and reports underpowered. Two things about it need saying plainly:

* **When the 160 rung reaches `B = 4` this line will flip to `P-FREE-REGION-CONFIRMED`, and
  that flip would be an artifact.** Arm `F`'s slope is negative with a CI upper bound already
  below `+0.3` (§3.3 for the value), which is exactly the condition §5 declares "free". But
  `dF` measures `160·k + 40·c`, not `160·k` (§3.2.1). A negative single-rung slope is what a
  *positive* `k` looks like once a negative `c` is folded in, and §3.2.2 records that I
  predicted this wrongly before the data arrived. I am not going to let the arithmetic of my
  own pre-registered estimator overrule a defect I can prove at `file:line`.
* **The band question §5 was written to answer is about the per-dispatch price**, and the
  identified per-dispatch price sits inside comment 6's `0.3`–`0.8` undecided band — at both
  ends of the interval and on both ladders (§3.3 for the figures). `P-INDETERMINATE` is
  therefore the honest label under the rule's intent as well as its letter.

Per comment 6's third branch I report both slopes with their intervals and **do not pick a
side**: the unchained and chained rung differences are both given, with intervals, in §3.3's
rung-difference block and in the summary table at the top of this report.

One caveat on those intervals, since they are the load-bearing numbers. They are **not** block
bootstraps. The rung difference has one block at the 1200 rung, so no paired-block CI exists;
the interval is propagated from the pooled within-arm scatter (a little under `15` µs/step,
§3.3) through the
`(d(1200) − d(160))/1040` difference on a Student-*t* with the pooled degrees of freedom. That
treats run-to-run scatter as the only error source and so **understates** the true uncertainty,
because it cannot see between-block drift at the high rung. The interval should be read as a
lower bound on width, not a confidence statement I would defend to three digits.

### Scoring the pre-registered out-of-sample predictions (amendment §10)

Amendment §10 was committed when the sink held 8 rows, with arms `H` and `J` unrun, and it
recorded three falsifiable predictions plus the tolerance for calling each one corroborated.
Scored against the rows that arrived afterwards:

| # | prediction | tolerance declared | measured | verdict |
|---|---|---|---|---|
| 1 | `dJ = +1242` µs/step from the gauge-anchored fit | within ±25 %, i.e. `[931, 1553]` | `+389.4` | 🚫 **refuted** |
| 2 | `dH` discriminates `k`: `−301` / `+59` / `+659` for `k = 0` / `0.3` / `0.8` | discrimination, not a point | `+387.1` | ✅ discriminated; `k = 0` refuted |
| 3 | `c < 0`, a commit-cadence lever of order `−300` µs/step | sign | `c < 0` on both ladders (§3.3) | ✅ sign confirmed, roughly half the predicted magnitude |

**Prediction 1 failed, and it failed for a reason worth recording rather than explaining
away.** I fitted the two-parameter model using the gauge rung at `N = 2400` — the one rung
that amendment §3 had explicitly designated liveness-only, precisely because it might not be
a valid measurement. It was not: the ladder is strongly superlinear above 1200 (§3.4), so
anchoring on the gauge inflated `k_chained` by a factor of ≈2.8 relative to the 160→1200
segment (§3.3). Predicting `+1242` where `+389` occurred is a 3.2× error, and the discipline
that caught it was writing the number down before the run.

The consequence for the report is that **every `k` and `c` I quote now comes from the
160→1200 segments only**, and the gauge appears nowhere in an estimate. Predictions 2 and 3
were unaffected because they did not depend on the gauge fit's magnitude: the observed
`dH = +387` sits between the `k = 0.3` and `k = 0.8` rows whether those rows are computed with
the refuted gauge-anchored `c` or with the corrected 160→1200 `c`, and it is more than fifteen
standard errors from the `k = 0` row. `k = 0` — a free region — is the one hypothesis this
probe rules out cleanly.

## §3.4 Why the gauge's `≈1.2 µs/dispatch` is not an estimate of anything

The gauge arm (2400 chained no-ops) moves decode by roughly +2.8 ms/step, which divides out
to about `1.16` M4 µs/dispatch. The 160-dispatch rungs show a small *negative* shift.
Amendment §3 designated the gauge a **liveness check only**, before any data existed,
precisely so this could not be retro-fitted into an estimate. That designation stands, but
the reason it must not be read as a per-dispatch tax is sharper than "the two numbers
disagree".

Under §3.2.1's `d(N) = N·k + 40·c` the low rung's negative shift and a positive `k` are not
in contradiction: `c < 0` absorbs it. Fitting the model on the two rungs that were designed
for it, per ladder, gives close agreement across two arms that share no serialization
mechanism:

<!--LADDER:BEGIN-->
| ladder | rungs used | `k`, M4 µs/dispatch | `c`, µs/layer | `40·c`, µs/step |
|---|---|---|---|---|
| unchained (`F`→`H`) | 160, 1200 | `+0.451 [0.399, 0.502]` | `−3.84` | `−153` |
| chained (`S`→`J`) | 160, 1200 | `+0.465 [0.415, 0.514]` | `−4.21` | `−168` |
<!--LADDER:END-->

That the two ladders recover `k` to within a few percent **and** a negative `c` of the same
size, from arms that share no serialization mechanism, is the strongest internal check in this
probe, and it is the reason I am willing to quote a per-dispatch price at all.

**The gauge does not lie on that line, and it must not be fitted with them.** Extrapolating
the fit to `N = 2400` under-predicts the gauge by roughly a factor of three; the measured `dG`
is about `+2.8` ms/step. The segment from 1200 to 2400 implies about `2` µs/dispatch, four
times the slope of the segment below it. Something additional switches on above 1200 injected dispatches —
plausibly MLX's `needs_commit()` command-buffer splitting, or pressure from holding 2400
live output arrays — and whatever it is, it is not a regime the ranked path visits. Amendment
§3 designated the gauge **liveness-only** before any data existed; the data vindicates that
restriction. Dividing `dG` by 2400 to get `1.16` µs/dispatch mixes three things — `k`, `c`,
and the superlinear regime — and estimates none of them.

One thing the high rung settles cleanly: `dJ − dH = +2.2` µs/step across 1200 injected
barriers, i.e. `+0.002` µs/barrier, replicating the low rung's near-zero paired difference
(§3.3).
**The barrier itself is free at both rungs**, which is the part of comment 6's reading the
probe confirms directly. `k` is a dispatch cost, not a synchronization cost.

### §3.4.1 An accidental finding I am flagging, not claiming

The fitted `c ≈ −4` µs/layer is a side effect of the instrument, but it is a side effect **on
the ranked decode path**: it says that forcing an extra `asyncEval` — an `end_encoding()` +
`commit()` pair — after every layer body made decode of order `150–175 µs/step` *faster*,
i.e. ≈**1.8 %** of a 9000 µs step. That is an order of magnitude larger than the merge's own
prize (§3.5), and it points the opposite way from the usual "submit less often" intuition.

The evidence for it is better than I expected when I pre-registered it in amendment §10: two
ladders that share no serialization mechanism recover it independently, and their fitted
values agree to within about 10 % (§3.3). It is not a fitting artifact of one arm.

I am still not claiming it, for two reasons I would want resolved before anyone spends bytes:

* The model was written after seeing the sign of the 160-rung shift, and the high rung has
  `n = 1`. `c` is exactly the kind of quantity that should be pre-registered and re-measured
  on its own, not harvested from a probe aimed at something else.
* It sits badly with the independent ≈30–50 µs/commit estimate used elsewhere in this
  campaign. A commit that costs 30–50 µs cannot also *save* ≈4 µs when added. **At most one of
  those two numbers is right**, and this probe was not designed to decide which, so I am
  recording the conflict rather than picking a side.

There is also a confound specific to `c` that the rung difference does *not* remove: the
injected `asyncEval` does not only add a commit, it also splits the layer's tape at a
different point, which can change how much work is in flight when the next layer is encoded.
"Extra commit" and "different tape split" are not separable by this instrument. The clean
test is a dedicated commit-cadence sweep with no injected kernel at all (§3.7 item 4).

## §3.5 What this means for the merge programme

The merge programme's premise is that deleting one dispatch per layer per step (40 per
step, family E — corrected count, see §3.6) buys back real decode time.

**The probe does not refute the premise. It prices it, and the price is small for a reason
that has nothing to do with whether dispatches are cheap.** The identified per-dispatch cost
is just under half an M4 µs per dispatch (§3.3), more than fifteen standard errors away from
zero — the region is *not* free. But the merge deletes only 40 dispatches per step, so:

<!--PRIZETABLE:BEGIN-->
| per-dispatch `k` (M4 µs) | source | merge prize, µs/step | % decode | % score at 0.75 weight |
|---|---|---|---|---|
| `1.890` | value the merge was budgeted against | `75.6` | `0.84 %` | `0.63 %` |
| `0.800` | comment 6's *build* bar | `32.0` | `0.36 %` | `0.27 %` |
| **`0.451`** | **this probe, identified** | **`18.0`** | **`0.20 %`** | **`0.15 %`** |
| `0.399`–`0.502` | its interval | `16.0`–`20.1` | `0.18`–`0.22 %` | `0.13`–`0.17 %` |
| `0.300` | comment 6's *dead* floor | `12.0` | `0.13 %` | `0.10 %` |

So the measurement cuts the expected prize by **4.2×** against the assumption the
programme was costed on, and lands it at ≈0.15 % of score. The single-rung arm-F read
alone — the estimator amendment §5 pre-registered — would instead have said
`−0.508 [−0.801, −0.216]` and killed the programme; §3.2.1 explains why that
estimator is degenerate and §3.3 reports it anyway.
<!--PRIZETABLE:END-->

Worth noting for calibration: comment 6's
own build bar of `0.8` corresponds to a 0.27 % score prize, so the decision rule's entire
`0.3`–`0.8` band spans only 0.10 %–0.27 % of score. The band is a narrow one in prize terms,
and `k` landing inside it is the reason this section does not pick a side.

Three lines of evidence bound the premise, and they agree less well than a summary would
suggest, so I am reporting the disagreement:

1. **This probe**, the load-bearing evidence, because it is on the ranked path and paired
   against its own per-block controls. Just under `0.5` M4 µs/dispatch from the unchained rung
   difference, corroborated by two weaker reads that do not share its assumptions: the naive
   high-rung slope `dH/1200 = +0.32`, and the prefill-gauge drift-corrected `+0.36`. All three
   sit inside comment 6's band. Note the direction of the error this corrects: the single-rung
   arm-F read alone would have reported a *negative* slope (see the note under the ladder
   above) and killed the programme.
2. **Roofline arithmetic** (independent estimate contributed by a frontier advisory agent
   this session, not a measurement of mine, and labelled as such). Decode streams ≈2.9 GB
   per token at an arithmetic intensity near 2 FLOP/byte against a ridge of ≥25, so the
   step is bandwidth-bound in aggregate with latency-bound glue. Its costed launch tax for
   the whole step is ≈37 µs, i.e. ≈0.4 % of a 9000 µs step; barrier stages price at ≈1–3 µs
   each. A 40-dispatch deletion is a sub-0.1 % lever on that budget.

3. **Tanjiro's R108-L** (`874e4917`), which returned `N-NO-MERGEABLE-PAIR` and priced
   dispatch removal at `k = 0.0872` µs/dispatch, CI `[−0.221, +0.438]`, against the assumed
   `k = 1.890` — a factor of 21.7. Two unit caveats, because they cut against a naive
   agreement claim: his figure is in **M5** µs/dispatch while comment 6's `0.3`/`0.8`
   thresholds and every slope in §3.3 are **M4**, so the two are not directly comparable in
   absolute magnitude; and his `0.0872` is a *derived* pricing figure built on #483's
   directly measured `0.108` µs/dispatch, which is a different measurement and should not be
   quoted interchangeably. What survives both caveats is the sign and the order of
   magnitude: an interval straddling zero, centred a factor of ~22 below the assumption the
   merge programme was budgeted against.

All three agree the prize is **small** — sub-0.25 % of decode — and all three agree it is far
below the `1.890` the programme was costed on. They do **not** agree on whether dispatches
are free. My estimate is nonzero at more than fifteen standard errors; R108-L's point estimate
is `0.087` and its interval contains zero. The overlap is only at the top of his interval
(`0.438`) and the bottom of mine (≈`0.4`), and the machines differ. I am not averaging them,
and I would
not describe the region as "free" on this evidence — "cheap, and cheap enough that a
40-dispatch deletion cannot pay for much" is what both support.

The consequence for rule 105.23(f) is therefore **not** that the merge is refuted. It is that
the merge's dispatch-count justification is worth ≈0.15 % of score rather than ≈0.63 %, and
whether that clears the rule-65 price is the advisor's call under comment 6's middle branch.
§2.7's Stage-1 recommendation should be re-read with `0.15 %` substituted for its assumed
prize, not discarded.

Separately, and independent of that call: *dispatch count* is not where the budget is.
Anything that reduces the ≈2.9 GB moved per token, or that removes a *false* hazard (see
§3.1's `prev_inputs_` note) and so restores concurrency the encoder already intended, or that
changes commit cadence (§3.4.1, ≈1.8 % if real), is priced on a much larger line than the
merge's own prize.

## §3.6 Corrections and unavailable knobs, carried forward as instructed

* **Family E's `n` is 40, not 30.** Advisor self-correction in comment 6; the 105.20
  figures built on `n=30` are 33 % low. Every dispatch-count figure in this section uses 40.
* **My own R107-F §11.4 "+2.19–2.31 %" is retracted.** It double-counts. I am not
  re-deriving a replacement here; it should be treated as withdrawn, not adjusted.
* **`FERN_DEFEAT_SLOTS` does not exist as a runtime control.** No reader appears anywhere in
  `Sources/` or in `benchmark.sh`. The probe records `defeat=0` in every row as a schema
  constant, and I declare the knob unavailable rather than reporting a setting I could not
  apply.
* **`max_abs_diff` is never citable as evidence.** It is hard-coded `0`. The correctness
  gate that actually runs is exact token-ID equality at
  `Sources/MLXFastCore/Golden.swift:387` and `:535`, and it is what every `passed=true` in
  the results table means.

## §3.7 Follow-ups I did not implement

Ranked by information per unit of device time:

1. **Count command buffers directly.** A Metal capture, or per-command-buffer
   `gpuStartTime`/`gpuEndTime` logging, measures the `c` term of §3.2.1 instead of forcing it
   to be differenced away, and separates "extra dispatch" from "extra submission". It is the
   change that would let a single rung identify `k` at all, and it also yields the GPU-busy
   fraction, the cheapest discriminator between bandwidth-bound and launch-bound decode.
2. **Finish the sanctioned INT8 attention coverage**, O-projection first (estimated 4–8 %,
   inside the accepted group-32 affine envelope). This is on the bandwidth budget line, not
   the dispatch line.
3. **Eliminate false hazards / overlap the shared expert.** `register_output_array`'s WAR
   tracking against `prev_inputs_` means allocator buffer recycling can serialize kernels
   the encoder marked concurrent. Fixing that recovers concurrency without deleting a
   single dispatch.
4. **Commit-cadence sweep** around `needs_commit()`, with no injected kernel at all. This is
   now the highest-value item on the list rather than a footnote: §3.4.1's fitted
   `c ≈ −4` to `−7.5` µs/layer says *more frequent* commits made decode ≈2–3 % faster, while
   the ≈30–50 µs-per-commit figure says commits are expensive. Those cannot both hold, the
   probe cannot settle it, and the disagreement is worth ten times the merge's 18 µs.

Items 2–4 come from the same frontier advisory analysis cited in §3.5, not from a measurement
of mine. The list order is that analysis's ranking; I would now promote item 4 above items 2
and 3 on the strength of §3.4.1, and I have left the numbering alone so the change of view is
visible rather than silently folded in.

