# R105-B — Adjudicating the router-weight-prefetch default

Student: `maple-frieren` · PR #597 · assignment
`maple-r105-b-router-prefetch-adjudication` rev `r105-b-rev1`
Branch `maple-frieren/r105-router-prefetch-adjudication`, head
`982b57ebd8e22c3a96b8cabccf071eed79f06d4b`, base
`codex/mlxfast-maple-20260804-advisor` @ `ed1ca05fa48307c45780b31c5d88218480aa9441`.
Campaign `BASE_SHA=768bb9d4adfc2baac7d74c0008afc92d010329da`.

**This section (§0–§5) is a preregistration. It was committed before any
timing arm of R105-B was launched.** Every acceptance rule, null cell and
verdict word below is fixed here; §6+ report outcomes against it.

---

## 0. One-paragraph statement

`DARKBLOOM_ROUTER_WEIGHT_PREFETCH` currently defaults to `1`
(`Sources/MLXFastModel/LagunaRuntimeModel.swift:696-704`). Two instruments
that both claim to measure that dial disagree in **sign**: the per-kernel
`SPLIT=1` census says pf1 is **−6.39 µs/step faster**, and the R103-A rung-2
end-to-end estimator says pf1 is **+34.58 µs/step slower**. If the end-to-end
number is real, flipping one token (`return 1` → `return 0`) is worth
+0.23…+0.53 % of `cs` — larger than anything else currently on the maple
frontier — and is bit-exact by construction, because pf0 and pf1 are two
compile-time placements of the same arithmetic. If the census number is real,
the R103-A rung-2 estimator is contaminated and **every** number it has
produced is suspect. R105-B decides which, and it must do so with an A/A null
run through the *same* estimator, because no such null exists.

## 1. The contradiction, with my own readings of the sources

I re-read each source rather than trusting the brief. Line pointers are at
this branch's HEAD.

| # | Source | Instrument | Reading | Sign for pf1 |
|---|---|---|---|---|
| 1 | `research/maple_r89_a_report.md:370`, summary `:694` | per-kernel `SPLIT=1` label, base `3f430f6f` (declared at `:217`, **not** `:222` as the brief says) | **−6.850 µs/step**, 95 % CI [−9.760, −3.940], 8/8 slots negative (`:375-377`); summary quotes −6.80 vs A0 / −6.85 vs A4 at σ = 3.34 | **faster** |
| 2 | `research/maple_r89_a_report.md:696` (§12 "nat" census) | whole-decode busy / wall / median | **+10.87 µs/step busy** [−1.13, +22.88] (σ ±13.26), **+8.38 wall** (σ ±10.19), **+18.50 median** [+10.44, +26.56] (σ ±5.23); the report itself labels this row **"not adjudicated"** | **slower** |
| 3 | `research/maple-nezuko-r100c-*.md:289-296` | pilot per-kernel | pf0 319.40 → pf1 313.55, **−5.85 µs/step**; `:38` defines prefetch value `5` as the **"Placement control"** | **faster** |
| 4 | `research/CURRENT_RESEARCH_STATE.md:160-166` (#558, the merge that shipped the default) | in-situ per-kernel census, REPS=12, STEPS=300 | pf0 319.8417, pf0b 319.9000, pf1 313.5083, pf1c 319.8917; paired `pf1 − pf0b` = **−6.3917** [−7.0157, −5.7677], 12/12 negative, 14.7× the ±0.43 floor; Rule-79 null `pf1c − pf0b` = −0.0083 [−0.9698, +0.9531] | **faster** |
| 5 | PR #571 `research/maple-frieren-r103a-missing-microseconds.md`, rung-2 | cross-process end-to-end median s/token, 24 reps × 6 slots, `DESIGN=rotate`, `STEPS=250`, K=21 reps / 7 cycles | `B→C` (`PREFETCH=0` → `PREFETCH=1`, **same binary**) = **+34.58 µs/step** [+26.39, +42.77], hw 8.19, **7/7 cycles**, **21/21 reps**; position-matched +34.59, 7/0 at every separation | **slower** |

Row 2 is the forgotten one. It is the *only* pre-#571 whole-decode reading of
this dial, it points the same way as row 5, its median channel is 3.5 σ from
zero, and #558 shipped over it because the row was marked "not adjudicated".
Two independent whole-decode instruments now agree that pf1 is slower.

### 1.1 Size of the hole

The doctrine at `research/CURRENT_RESEARCH_STATE.md:193-200` does not claim the
census −6.39 lands whole. It applies a router shadowing factor **E = 0.349**:

> "the −6.3917 µs/step census win is worth 6.3917 × 0.349 = **2.2307 µs/step
> chained** ⇒ +0.016 % decode ⇒ +0.012 % of score — about **36× below** the
> 0.5393 % session σ. It is free (bit-exact, 4,186 B, no risk) and therefore
> worth carrying, but a receipt spent to measure it would be pure noise. **Bank
> it** and let the next receipt-worthy arm carry it."

So the two predictions for the end-to-end effect of turning pf1 on are:

| Predictor | End-to-end Δ µs/step, pf1 − pf0 | Gap vs measured +34.58 |
|---|---|---|
| census, naive chain (E = 1) | −6.39 | **40.97** |
| census, doctrinal chain (E = 0.349) | −2.23 | **36.81** |
| R103-A rung-2, measured | **+34.58** | — |

At the decode price of this campaign (1 % of `cs` = 65.67 µs/step ⇒ 0.015228 %
of `cs` per µs/step), +34.58 µs/step is **0.527 % of `cs`**. The doctrinal
prediction is 0.034 %. The two differ by **15×** *and* by sign. That is not a
calibration disagreement, it is one of the two instruments being wrong.

### 1.2 Why this has to be settled now, not banked

- The dial is **on by default in the shipped tree**. There is no "wait for the
  next arm" option; every submission from this base already pays whatever pf1
  costs.
- `research/CURRENT_RESEARCH_STATE.md:388-392`: *"our last receipt is
  `e08d759f` at 18:36:41Z … #558 (R3, router weight prefetch) merged at
  20:47:04Z … **So no receipt has ever measured a tree containing R3.**"* The
  default has never been priced on M5 at all.
- Rule 82 is *stated* as a general law of hoisting but was *derived* from the
  same #558 static read that also produced the −6.39. If the −6.39 does not
  chain, Rule 82's evidentiary base is a per-kernel label, not an end-to-end
  win, and the rule needs rewording. §7 delivers that verdict.

## 2. Correction to the assignment's premise (must be read before §3)

The brief states that `Sources/` is unchanged since `0f6862d0` and that the
PR #571 snapshots can therefore be reused. **As written that is false.**

```
$ git diff --numstat 0f6862d0 HEAD -- Sources
2059    2059    Sources/MLXFastModel/LagunaRuntimeModel.swift
```

2,059 lines changed on each side. What *is* true — and what the brief was
reaching for — is that the change is **semantically empty**: the multiset of
non-comment, whitespace-normalised code lines is identical (sorted-line diff =
0 lines). The delta is a pure relocation of code and comment blocks inside
LRM.

That distinction is exactly what R105-B is about, because §5.4 of #571 blamed
the missing microseconds on **binary layout**: `__text` +64,320 B, `laguna`
symbols at an identical address in only **0.03 %** of cases, and 68 ns ×
408 dispatches ≈ 27.7 µs/step of estimated displacement. A "pure relocation"
of 2,059 lines of LRM is precisely the kind of change that moves every
`laguna` symbol without changing a single instruction's semantics.

Operational consequence: the #571 snapshots are **stale and unusable**. Tree
digest is now
`d93a6d14a9322bb741c7da64b08aca947ba4850854c80b8a656a0eb7dca1d09c`
against `c3fafd30b4fdba6d3058746e79a715a53a072c5d5c77b0716a3a73dbd385f492`
at the #571 build. R105-B builds fresh at HEAD.

## 3. Preregistered Phase A — one 4-arm same-binary session

Everything in Phase A runs from **one** worker binary built at HEAD. Arms are
selected by environment variable only, so no arm can differ from another by a
single byte of code, symbol address, or metallib content. This is the
structural fix for #571 §5.4: layout is held exactly constant by construction
rather than measured and corrected.

```
ARMS="P0:head:DARKBLOOM_ROUTER_WEIGHT_PREFETCH=0 \
      P1:head:DARKBLOOM_ROUTER_WEIGHT_PREFETCH=1 \
      P5:head:DARKBLOOM_ROUTER_WEIGHT_PREFETCH=5 \
      P1B:head:DARKBLOOM_ROUTER_WEIGHT_PREFETCH=1"
DESIGN=rotate REPS=24 STEPS=250 WARMUP_REPS=4
SNAP=/tmp/maple-r105b-snap OUT=/tmp/maple-r105b/phaseA
ASSERT_DIFFER="" ASSERT_SAME=""
bash research/maple-frieren-r103a-abba.sh
```

4 arms × 2 slots = 8 slots/rep; rotation cycle = 4 reps = 32 slots; 24 reps =
**192 slots**; 20 analysed reps = **5 cycles**. At the #571 measured slot cost
of ≈44.2 s (§6.8: of which ≈42.5 s is model load — 96 % startup) this is
≈8,600 s ≈ 143 min, inside the 180-min per-run limit.

Why 192 slots rather than #571's 144: it merges the A0 null and the A1
placement adjudication into a single session, removing cross-session variance
between the null and the effect it is calibrating, and it costs less
wall-clock than two separate 144-slot sessions. The price is statistical
power: at K=5 cycles instead of 7, the expected CI half-width per contrast is
≈11 µs/step rather than 8.19. §5 states what that does and does not resolve.

Analysis, fixed in advance:

```
python3 research/maple-frieren-r103a-analyze-multi.py /tmp/maple-r105b/phaseA 4
python3 research/maple-frieren-r103a-position-matched.py /tmp/maple-r105b/phaseA 4
```

`analyze-multi.py` takes `itertools.combinations(arms, 2)`, so all **six**
contrasts below come out of one invocation with one set of cycle blocks, one
QC pass and one rejection rule.

### 3.1 A0 — the A/A null the estimator has never had (P1 vs P1B)

`P1` and `P1B` are the same binary with the same environment. Their contrast is
identically zero by construction. It is the Rule-79 null cell for the
+34.58 — the one #571 never ran and the reason the +34.58 was never safe to
publish as a lever.

| Verdict | Condition | Meaning |
|---|---|---|
| **N-1 fires** | `\|P1B − P1\|` CI excludes 0, or median offset ≥ 8 µs/step | The rung-2 estimator manufactures a ≥8 µs/step effect from nothing. **The +34.58 is retracted**, R103-A rung-2 is retired, and no receipt is spent. |
| **N-1 clears** | CI covers 0 **and** half-width ≤ 12 µs/step | The estimator is calibrated at this precision. `P0 → P1` and `P0 → P1B` are then two independent replicas of the #571 `B→C` contrast, and I compare them to +34.58 [+26.39, +42.77]. |
| **N-1 inconclusive** | CI covers 0 but half-width > 12 µs/step | Underpowered. Reported as such; no retraction, no receipt on the strength of Phase A alone. |

`P0 → P1` and `P0 → P1B` are also a second, *internal* consistency check: two
estimates of the same physical quantity from arms at different rotation
offsets. If they disagree by more than their pooled CI, position dependence is
still present after rotation and A0 is not sufficient.

### 3.2 A1 — placement vs peel (P5 vs P0, P5 vs P1)

`prefetch = 5` is the preregistered **placement control** of #558
(`maple-nezuko-r100c:38`): via `lagunaRouterPrefetchGroups` (LRM `:876-879`)
it maps to `groups = 1`, and the variant dictionary (LRM `:1115-1150`) selects
the `_pf1c` suffix — the peel without the cross-barrier hoist. #558's decision
row 1 fired on `pf1 < pf1c ≈ pf0` *at the kernel label*. A1 asks whether that
still holds end to end.

| Verdict | Condition | Reading |
|---|---|---|
| **V-PLACEMENT** | `P5 ≈ P0` and `P1` slower than both | The end-to-end cost tracks the cross-barrier hoist, i.e. the same structural feature the census credited with the win. #558's decision row is *sign-inverted* end to end, not merely attenuated. |
| **V-PEEL** | `P5 ≈ P1`, both slower than `P0` | The cost tracks the peel, not the hoist. #558 mis-attributed the mechanism and the census label is measuring something other than the dial's real cost. |
| **V-NEITHER** | all three within the A0 null band | No end-to-end effect of any placement at this power. The +34.58 does not reproduce. |

`P5` is a zero-marginal-cost rider: it is the same binary and it occupies slots
the rotation needs anyway.

### 3.3 M2 — static compile read at the shipped geometry (no GPU time)

Rule 82 makes a static read step 1 of any codegen arm, and #558's read is the
load-bearing evidence for "zero occupancy change". That read was taken in the
**1024-thread** era; HEAD ships **512** threads. A static read at the wrong
geometry cannot support an occupancy claim, so I redo it:

```
research/maple-nezuko-r100c-dump-msl.sh     # RPG=8 → research/msl/r100c_rpg8_{BASE,pf0,pf1,pf1c}.body.metal
research/maple-nezuko-r100c-isa.sh          # → .air, .metallib, .air.ll  (metal3.1 -O3)
swift research/maple_nezuko_r100c_pipeline_stats.swift
```

Preregistered reading: I report `maxTotalThreadsPerThreadgroup`,
`threadExecutionWidth`, `staticThreadgroupMemoryLength` and `launchable@512`
for pf0 / pf1 / pf1c, plus the AIR load/barrier line ordering. **M2 cannot
explain a 41 µs/step end-to-end gap either way** — the whole router GEMV is
≈320 µs/step and an occupancy change would show in the census, which is the
instrument that says pf1 is *faster*. M2's job is narrower: to confirm or
retract the specific "identical pipeline stats" sentence at
`CURRENT_RESEARCH_STATE.md:160-166`, which is quoted at the *old* geometry.

### 3.4 Mechanism list, with what would confirm each

Fixed in advance so that no post-hoc mechanism can be fitted to the data.

| ID | Mechanism for a sign-inverting ≈37–41 µs/step gap | Confirming observable | Available in R105-B? |
|---|---|---|---|
| **M1** | Estimator artefact: rung-2 attributes slot-position or process-order structure to the dial | A0 fires N-1 | **yes** (§3.1) |
| **M2** | Occupancy / spill tax invisible to the census label | pipeline stats differ pf0 vs pf1 at 512 threads | **yes** (§3.3) |
| **M3** | Displacement: pf1's extra code moves *other* kernels' instruction cache footprint | same-binary design removes it; if a same-binary P0→P1 still shows +34, M3 is refuted as the *sole* cause | **yes**, as a refutation only |
| **M4** | Cross-kernel interference: prefetched router weights evict lines other kernels need, so the cost lands outside the router label | census total ≪ end-to-end total, and the *deficit* sits in non-router labels | partial — needs a `SPLIT=1` session, not run here |
| **M5** | Dispatch/command-buffer cost of the extra variant (different kernel object, different pipeline-state switch pattern) | per-dispatch count or encoder-switch count differs | not instrumented; noted as open |
| **M6** | The census label itself is biased: the `SPLIT=1` boundary excludes the part of the router path that pf1 slows | census null (Rule 79, −0.0083) is clean, so a *bias* rather than *noise*; only a differently-bounded label settles it | no; declared out of scope |

A verdict of "M1 confirmed" is reported as *the estimator is broken*, not as
*pf1 is fine*. Those are different claims and the second one still needs an
M5 receipt, which is why Phase B exists even if A0 fires.

## 4. Preregistered Phase B — official M5 receipts

Phase B alternates two commits that differ **only** in the one-token default:

- **T1** = current tree, `return 1` (this is also the deferred frontier
  receipt that `CURRENT_RESEARCH_STATE.md:388-392` says has never been drawn).
- **T0** = one-line flip to `return 0` at LRM `:696-704`.

Both are bit-exact against each other by construction: pf0 and pf1 are two
placements of identical arithmetic, and #558 recorded `max_abs_diff 0` on all
four e2e ABBA legs plus a byte-identical equivalence oracle. I re-verify with
`research/run_upstream_equivalence.sh` on both arms before submitting either.

Receipt budget: **up to 6, minimum 4**, alternating T1/T0 so that session
drift cannot be confused with the flip. Each receipt needs its own commit;
where two receipts must carry byte-identical `Sources/`, I verify with an
empty `git diff --numstat <a> <b> -- Sources` and confine the SHA difference
to files outside `Sources/`. Attribution is by `submissionCommitSha`.

Submission is via `senpai/submit-official.sh "$BASE_SHA"` (which forces
`--model "senpai"`), watched with
`python3 senpai/watch-submission.py --submission <id>` under `run_job`
(`read_only`).

### 4.1 Honest power statement (this is a limitation, not a footnote)

The receipt channel's paired σ is **σ_pair(T) = 17.08 µs/step**. Half-widths:

| pairs | 95 % half-width, µs/step | as % of `cs` |
|---|---|---|
| 3 | ±19.3 | ±0.294 |
| 4 | ±16.7 | ±0.254 |
| 6 | ±13.7 | ±0.209 |

So:

- If the true end-to-end effect is the full **+34.58 µs/step**, 3 pairs
  resolve it (34.58 > 19.3) and 6 pairs resolve it comfortably.
- If the effect transfers at the doctrinal **E = 0.349** shadowing factor,
  the true effect is ≈ **+12.1 µs/step**, which is **below the half-width at
  every budget I can afford**. A ×0.436 (or smaller) transfer is **not
  resolvable at 3 pairs and not resolvable at 6**.

I state this before drawing anything: **a null result in Phase B is
compatible with a real +12 µs/step regression** and must not be reported as
"the flip does nothing". The receipt channel can confirm the large effect; it
cannot exclude the small one.

## 5. Stopping rule (preregistered)

Stop and write up when the first of these holds:

1. Phase A complete (A0 + A1 + M2) **and** ≥2 M5 pairs drawn; or
2. 6 receipts spent; or
3. **A0 fires N-1** — in which case stop *before* spending any receipt, retract
   the +34.58, and submit. A broken estimator is the finding; buying M5 time to
   chase its artefact would be the same error #571 made in reverse.

## 6. Scope fence I am holding

- **rpg retiling is a CLOSED family.** It may ride along only as a
  zero-marginal-cost same-binary arm and is **never** the thesis and **never**
  a receipt. Phase A carries no rpg arm.
- Sliding-attention and every sibling dial stay at shipped defaults.
- Rule 86: no `--local-iterate` delta appears anywhere in this report as
  evidence for or against the lever.
- Rule 79: every effect cell in §6+ is published beside its null cell.
- `research/r103b/artifacts/ab_router_prefetch_cancelled_summary.tsv` stays
  cancelled and is not resurrected.
- Commits are kept distinct from `maple-nezuko`'s, which is concurrently
  spending M5 receipts on #584.

## 7. Verdicts owed at the end (placeholders, filled in §9)

1. `research/CURRENT_RESEARCH_STATE.md:193-200` — the "free rider / Bank it"
   doctrine for #558.
2. **Rule 82** — whether "elsewhere hoisting is decided by a static read"
   survives, and replacement text if it does not.
3. The blank documentation blocks at LRM `:685-696` and `:705-711`, which
   currently carry no prefetch semantics at all.

---

*(Sections 8+ are written after the runs and report outcomes against the
above. Nothing above this line is edited after the first Phase-A launch except
to fix a typo, and any such edit is called out in the commit message.)*
