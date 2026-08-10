# R108-K — is one decode dispatch per layer actually removable, and is removal worth the rule-65 price?

- **Student** maple-frieren · **PR** #660 · **assignment** `maple-r108-k-decode-dispatch-merge` · **revision** `r108-k-rev1`
- **Base** `codex/mlxfast-maple-20260804-advisor` at assignment time `d3045bd8`; **reconciled by MERGE** onto the
  live advisor tip **`705484b9`** (rule 97.0 — recording which). The merge brought in tanjiro's R107-G census,
  which the advisor's 15:48Z feedback comment made a Stage-0 input.
- Carried forward on the same branch: two research-only commits orphaned by the closure of #597
  (`cert v2`, `SOP v2`). No `Sources/` change accompanies Stage 0.

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

### §1.4 The correct closure — and it is a *stronger* result than the one that was hoped for

The **calls** column of §B.0.3 sums to **exactly 319**:

```
39 + 30 + 30 + 39 + 30 + 1 + 10 + 39 + 39 + 10 + 30 + 1 + 10 + 1 + 10 = 319
```

Nobody has summed that column before. It matters, because it means **§B.0.3 is not a "top 15" — it is the
complete decode dispatch ledger.** There is no 16th family, no unlisted small kernel, no residual pool of
un-censused work. (This is the first independent confirmation that the census and the 319-dispatch count
describe the same object.)

Therefore **the residue contains no kernel time at all**. It is dispatch glue, encoder boundaries and gaps,
and nothing else. That converts the residue from a corroboration into a **budget constraint** — and a
constraint is a much more useful thing than a corroboration, because it can be violated.

| host | `T` | Σ census kernel time | residue | residue ÷ 319 | marginal price (rules 57/65) | price × 319 | over-run |
|---|---:|---:|---:|---:|---:|---:|---:|
| M4 | 8448.0 | 8096.3 | **351.7** | **1.1025 µs** | 1.2382 | 395.0 | **112.3 % of budget** |
| M5 | 4141.5 | 3650.9 | **490.6** | **1.5379 µs** | 2.3403 | 746.6 | **152.2 % of budget** |

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
recovers only its *non-overlapped* share, which the census residue bounds from above at
**1.5379 M5 µs/dispatch**, i.e. `k_removal ≤ 1.5379 / 1.2382 = **1.242**`.

This is the answer the brief wanted and it is the opposite sign from the one it hoped for: the hedge in rule
105.13 was **not** wrong, it was **not conservative enough**. `k_dispatch ∈ [1.0, 1.890]` should be, for
*removal*, `k_removal ∈ [1.0, 1.242]`.

### §1.6 The honest ladder — replacing the brief's three-point read

`cs` price 0.015228 % per M5 µs/step (rule 105.13); 1 % of `cs` = 65.67 M5 µs/step.

| basis | M5 µs/dispatch | implied `k` | 39 removed | 30 removed | status for a removal claim |
|---|---:|---:|---:|---:|---|
| rule 65 marginal, **ADDED** dispatch | 2.3403 | 1.890 | 1.390 % | 1.069 % | ⛔ **not quotable for a removal** |
| state-doc residue ratio | 1.7273 | 1.395 | 1.026 % | 0.789 % | ⛔ exceeds the M5 residue budget |
| **census-residue ceiling for REMOVAL** | **1.5379** | **1.242** | **0.913 %** | **0.703 %** | ✅ hard upper bound |
| **conservative headline (advisor's floor)** | **1.2382** | **1.0** | **0.735 %** | **0.566 %** | ✅ **quote this** |

**Instruction to myself and to anyone reading this: price a dispatch *removal* at `k = 1.0` as the headline
and never above `k = 1.242`.** The brief's "even the floor is 1.8× the draw bar" survives intact:

| candidate | k = 1.0 | k = 1.242 (ceiling) | bars at k = 1.0 |
|---|---:|---:|---:|
| 39 dispatches (families D, B) | 0.735 % | 0.913 % | **1.84 bars** |
| 30 dispatches (families A, C, **E**) | 0.566 % | 0.703 % | **1.41 bars** |

So the lever still survives its own worst case, which is the property that made it worth the remaining hours.
It just survives with less margin than the brief assumed, and family **E**'s headline number must come down
from **1.069 % to 0.566 %** (0.703 % at the ceiling). That is 1.41 bars, not 2.67.

### §1.7 Robustness to the α/β choice, since the M5 column is derived, not measured

Rule 105.8 class (b): §B.0.3's M5 column is `M4 × α` for bytes families and `× β` for latency ones. It is
derived, so the M5 residue inherits that assumption. Bounding it:

| assumption on the 15 kernel families | Σ kernel (M5) | residue | ÷319 | reaches 2.3403? |
|---|---:|---:|---:|---|
| as published (per-family α or β) | 3650.9 | 490.6 | 1.5379 | no |
| **every** family at α = 0.4369 (most generous) | 3537.3 | 604.2 | **1.8941** | **no** |
| every family at β = 0.5 | 4048.2 | 93.4 | 0.2927 | no |

For rule 65's price to fit the ledger, the kernel families would have to convert at an effective
`k_kernel = (4141.5 − 746.6) / 8096.3 = **0.4193**` — i.e. **below α**, which rule 105.12 treats as the floor
of the admissible range. **The ceiling result is therefore robust to the α/β choice: rule 65's marginal price
cannot be the average resident-dispatch price under any admissible conversion.**

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
> real *because* it is incompressible). The correct closure is better: §B.0.3's call column sums to exactly
> 319, so the census *is* the whole ledger, the residue is pure glue, and it is a **budget that rule 65's
> price over-runs by 52 %**. That over-run is itself the measurement of removal asymmetry: **removal is worth
> ≤ 1.5379 M5 µs/dispatch, `k_removal ≤ 1.242`, headline `k = 1.0`.**

---

## §2 Deliverable B — the ranked adjacent-pair dispatch ledger

*(in progress — §2 lands with the 18:30Z Stage-0 push)*
