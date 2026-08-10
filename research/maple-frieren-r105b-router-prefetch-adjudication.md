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
408 dispatches ≈ 27.7 µs/step of estimated displacement. (#571 used 408 here;
the repo's repeatedly measured figure is **406** dispatches/step —
`research/RESEARCH_ARCHIVE_through-round-91.md:4067-4068`, `:4088-4090`, `:69`
and `research/DATASET_ANALYSIS.md:146-147`. 68 ns × 406 ≈ 27.6 µs/step, so the
correction is immaterial to #571's argument; I note it only so the number is not
propagated further.) A "pure relocation"
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
DESIGN=rotate REPS=18 STEPS=250 WARMUP_REPS=2
SNAP=/tmp/maple-r105b-snap OUT=/tmp/maple-r105b/phaseA
ASSERT_DIFFER=' ' ASSERT_SAME=' '
bash research/maple-frieren-r103a-abba.sh
```

Budget note (revised after measuring the #571 rung-2 artefacts): the surviving
`.steps` mtimes give **44.53 s/slot** over 144 slots. 4 arms × 2 slots × 18 reps
= 144 slots = 6,367 s ≈ 106 min, inside the 180 min per-run ceiling. `REPS=18`
with `WARMUP_REPS=2` leaves 16 analysed reps = exactly **four complete rotation
cycles**, so position balance is exact; `REPS=24` would have left a two-rep
partial cycle. n=16 within-rep pairs against σ_pair = 18.44 µs/step gives
SE = 4.6 and hw ≈ 9.8 µs/step, which resolves a +34.58 effect at 7.5σ and still
meets the A0 acceptance ceiling of hw ≤ 12.

`ASSERT_DIFFER`/`ASSERT_SAME`/`NULL_COPIES` are read with `${VAR:-default}`, so
an *empty* string silently restores the default assertion. They must be passed
as a single **space** to disable them.

Why 4 arms at 144 slots rather than #571's 3 arms at 144 slots: it merges the
A0 null, the effect and the A1 placement adjudication into a single session,
removing cross-session variance between the null and the effect it is
calibrating, at identical wall-clock. The price is power — n=16 pairs instead
of #571's 21, hw ≈9.8 instead of 8.45. §5 states what that does and does not
resolve.

Analysis, fixed in advance:

```
python3 research/maple-frieren-r103a-analyze-multi.py    /tmp/maple-r105b/phaseA 4
python3 research/maple-frieren-r103a-position-matched.py /tmp/maple-r105b/phaseA 4
python3 research/maple-frieren-r105b-stepwise.py        /tmp/maple-r105b/phaseA 4
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
the `_pf1c` suffix.

M2 (§3.3, executed — results in §6.2) upgrades this from "a control someone
labelled placement" to an **exactly isolated single-variable control**. The
generated MSL for `_pf1` and `_pf1c` differs in nothing but the *line number* of
one identical 12-line block:

```
 thread vec<bfloat, 4> laguna_pf[4];
 if (simd_group < active_simd_groups) { ... laguna_pf[k] = pf_values[0]; }
```

In `_pf1` it sits at MSL line **75**, *before* the RMSNorm reduction and
therefore before all **5** `threadgroup_barrier` calls. In `_pf1c` the identical
block sits at line **103**, *after* them. Same loads, same registers, same
arithmetic, same consumer loop, byte-identical everywhere else. So the three
arms decompose the dial into two orthogonal halves:

| Contrast | Isolates | Kernel-label value (archive) |
|---|---|---|
| `P5 − P0` | the **local hoist**: 4×`vec<bfloat,4>` batched into registers just before use, same side of the barriers — pure ILP | `+0.05` µs/step (`pf1c−pf0b` = −0.0083, the Rule-79 null) |
| `P1 − P5` | the **cross-barrier hoist**: the same 8 live 32-bit registers carried *across* 5 threadgroup barriers, and a **256 KB** `router_weight` salvo issued *before* the norm's own traffic instead of after [ERRATUM E1] | `−6.38` µs/step (pf1 313.51 vs pf1c 319.89) |
| `P1 − P0` | both together | `−6.39` µs/step |

The kernel label therefore credits **100 % of its −6.39 win to the cross-barrier
hoist and 0 % to the local hoist**. That gives A1 a sharp preregistered
prediction rather than a menu: if the +34.58 end-to-end penalty is the hidden
price of the same structural feature the label rewards, then

> **P1 − P5 ≈ +34.6 µs/step and P5 − P0 ≈ 0.**

| Verdict | Condition | Reading |
|---|---|---|
| **V-PLACEMENT** | `P5 ≈ P0` (inside the A0 band) and `P1 − P5` CI excludes 0 upward | Confirms the prediction. The cross-barrier hoist buys −6.4 µs/step inside the router label and pays ≫ that outside it. #558's decision row is **sign-inverted end to end**, not merely attenuated, and both `5` and `0` are better defaults than `1`. Choosing between `5` and `0` is then a separate question settled in §10.2, **not** by any label win [ERRATUM E2]. |
| **V-PEEL** | `P5 ≈ P1`, both slower than `P0` | The cost tracks the loads themselves, not their placement. Then `0` is the only fix, and the label's Rule-79 null cell (`pf1c−pf0b` ≈ 0) is itself label-blind. |
| **V-MIXED** | both `P5 − P0` and `P1 − P5` CIs exclude 0 upward | Two additive costs; report the split. |
| **V-NEITHER** | all three within the A0 null band | No end-to-end effect of any placement at this power. The +34.58 does not reproduce. |

`P5` is a zero-marginal-cost rider: same binary, and it occupies slots the
rotation needs anyway. **V-PLACEMENT would make the deliverable a one-token
change (`return 1` → `return 5`) that keeps a measured kernel win and drops a
measured end-to-end loss** — which is why P5 earns its arm even at the cost of
5 pairs of power.

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

#### 4.1.1 Independent cross-check of σ_pair from the public receipt list

`σ_pair(T) = 17.08 µs/step` is inherited, so I checked it against the only
independent sample I can read for free. `mlxfast submissions` lists this
account's receipts. Taking the 14 consecutive non-outlier receipts (dropping
the six obviously-worse trees at `cs` 2.04-2.55) gives mean `cs` 2.575792 and
**relative sd 0.3438 %**, i.e. 22.6 µs/step for a *single* receipt and
**31.9 µs/step for a difference of two**.

That is **1.9× the assumed σ_pair**, and the two figures bracket the truth from
opposite sides:

- 0.3438 % is *inflated*, because all 14 receipts are different trees, so it
  mixes genuine tree differences into the noise term. It is an upper bound.
- it is also *deflated* by my having dropped the six low outliers, which is a
  selection on the response. So it is not a clean upper bound either.

Half-widths under the conservative σ_pair = 31.9 µs/step (`z = 1.96`):

| pairs | 95 % half-width, µs/step | resolves +34.58? |
|---|---|---|
| 2 | ±44.2 | no |
| 3 | ±36.1 | no (just) |
| 4 | ±31.3 | yes |
| 6 | ±25.5 | yes |

**Consequence I accept before drawing:** the 2 pairs the stopping rule permits
resolve +34.58 only under the optimistic inherited σ, and not under the
conservative one. Phase B as budgeted is therefore an M5 *sign and transfer*
check, not a Phase-B-alone confirmation, and I will report it that way whatever
comes back. The precise M4 measurement is Phase A; Phase B only asks whether
the ranked architecture agrees in sign.

One further empirical note from the same listing: every receipt on this
account is `rejected`, and the best-of-benchmark implied by the reported
deltas sits near `cs` 2.62. A receipt drawn from this branch is therefore
science, not a plausible promotion, which removes the temptation to read the
absolute number.

## 5. Stopping rule (preregistered)

Stop and write up when the first of these holds:

1. Phase A complete (A0 + A1 + M2) **and** ≥2 M5 pairs drawn; or
2. 6 receipts spent; or
3. **A0 fires N-1** — in which case stop *before* spending any receipt, retract
   the +34.58, and submit. A broken estimator is the finding; buying M5 time to
   chase its artefact would be the same error #571 made in reverse.

## 6. Executed before any new GPU time was spent

Two results below cost **zero** GPU seconds and both changed the design in §3.

### 6.1 The #571 rung-2 raw per-step data survived, and it refutes mechanism B

`/tmp/maple-r103a/rung2` still holds all 144 `.steps` files (250 per-step values
each, in ms), `index.tsv`, `analysis-multi.json`, `position-matched.txt` and
`provenance.txt`. Provenance line 4 confirms the arms:
`A:old B:new:DARKBLOOM_ROUTER_WEIGHT_PREFETCH=0 C:new:DARKBLOOM_ROUTER_WEIGHT_PREFETCH=1`,
host Apple M4 Pro. So `C − B` **is** the pf1-vs-pf0 contrast at fixed code, and
the +34.58 can be re-interrogated at step resolution. I wrote
`research/maple-frieren-r105b-stepwise.py` for this.

**Step-index profile of `C − B`** (µs/step, cross-slot medians, windows
0-1, 1-2, 2-5, 5-10, 10-25, 25-50, 50-100, 100-150, 150-200, 200-250):

```
C-B  +32.23 +26.15 +26.87 +24.67 +24.56 +26.63 +29.35 +32.91 +31.29 +33.63
B-A  -22.92  -5.50  -7.43  -6.64  -7.08  -3.70  -4.15  -7.91  -5.52  -4.77
C-A   +9.31 +20.65 +19.44 +18.04 +17.48 +22.93 +25.21 +25.00 +25.77 +28.87
```

**Mechanism B — a per-slot one-time cost (JIT, pipeline build, shader cache) — is
quantitatively refuted.** The rung-2 primary statistic is a per-slot **median
over 250 steps** (`STATS = ("median","trimmed","mean","mean_first128","step0")`,
median primary), which is structurally blind to a step-0 spike. And all four
sustained statistics agree: median **+34.58**, trimmed **+36.15**, mean
**+35.96**, mean_first128 **+38.74**. `mean − median` = 1.38 µs/step × 250 steps
= 345 µs of total one-time budget, which matches the direct `step0` estimate
**+420.86 [−779.59, +1621.31]** — a CI that covers zero. So the one-time
component is at most ≈1.7 µs/step of the 34.58 (**≈5 %**) and is not
statistically distinguishable from nothing. The gap is *sustained across all 250
steps*.

**Not a position artefact.** Per-(arm, position) mean of slot medians (µs/step):

| arm | pos1 | pos2 | pos3 | pos4 | pos5 | pos6 |
|---|---|---|---|---|---|---|
| A | 8260.9 | 8241.1 | 8240.8 | 8248.4 | 8238.4 | 8243.9 |
| B | 8235.4 | 8216.9 | 8231.9 | 8240.8 | 8238.4 | 8235.4 |
| C | 8284.1 | 8265.2 | 8267.8 | 8263.8 | 8261.9 | 8263.8 |
| **C−B** | **+48.7** | **+48.3** | **+35.9** | **+23.0** | **+23.5** | **+28.4** |

6/6 positions positive for `C−B` and for `C−A`; only 1/6 for `B−A`.

**Not a drift artefact.** Within-rep paired, n=21: `C−B` mean **+34.63**, median
+29.60, sd 18.44, **21/21 positive**; `C−A` +22.20 (19/21); `B−A` −12.43 (4/21).
Slot-median distributions (n=42 each): A [8230.5, 8383.3] sd 23.5; B [8084.0,
8246.8] sd 24.4; C [8249.8, 8341.5] sd 15.7. **C and B are disjoint** —
`min(C) − max(B) = +2.9 µs/step`, zero slots in the overlap.

**Live growth signature.** `C − B` rises from +24.6 (steps 10-25) to +33.6 (steps
200-250), **+36 %**, while the common level *falls* 8266 → 8262 over the same
window (the arms' shared level drops as the slot warms). KV grows 512 → 762
(**+49 %**) across the slot. A cost that scales with KV footprint is consistent
with a memory-system / cache-contention mechanism (M4/M5 family) and
inconsistent with a fixed per-step overhead. Time-in-slot and KV length are
confounded here; only a step-count sweep (STEPS=125 vs 500 at fixed KV seed)
separates them, and it is listed as the top follow-up.

**Correction to the assignment brief's reading of the #571 "nulls".**
`nulls()` (`research/maple-frieren-r103a-analyze-multi.py:135`) is a *within-arm,
within-rep, later-minus-earlier position contrast at fixed separation*.
`arm_estimates()` *averages an arm's two occurrences inside a rep, then
differences arms*. These are different estimands, and the second averages over
exactly the drift the first measures. So `null B@sep1 = +8.81 [+0.67, +16.95]`
— which does exclude zero — is **not** a discount against the +34.58, and
**no true A/A null for the contrast estimator has ever been run**. That is
precisely the hole A0 (§3.1) fills. For the record the other cells are
B@sep3 +21.69 [−34.74, +78.13], B@sep5 +0.01, A@sep5 −16.59, C@sep5 −19.97,
pooled@sep1 +4.15, pooled@sep3 +5.23, pooled@sep5 −12.18.

### 6.2 M2 executed — no occupancy change, and the dial is one relocated block

`research/maple-nezuko-r100c-isa.sh` + `research/maple_nezuko_r100c_pipeline_stats.swift`
on this M4 Pro at the shipped geometry:

| variant | AIR | metallib | `maxTotalThreadsPerThreadgroup` | `threadExecutionWidth` | `staticThreadgroupMemory` | launchable@512 | AIR `load` | barriers |
|---|---|---|---|---|---|---|---|---|
| `pf0`  | 7392 | 7561 | 1024 | 32 | 4240 | yes | 10 | 5 |
| `pf1`  | 7680 | 7849 | 1024 | 32 | 4240 | yes | 13 | 5 |
| `pf1c` | 7664 | 7818 | 1024 | 32 | 4240 | yes | 13 | 5 |

**Verdict on `CURRENT_RESEARCH_STATE.md:160-166`: CONFIRMED, not retracted.**
The "identical pipeline stats — 1024 threads, width 32, 4240 B" sentence still
holds at HEAD's 512-thread geometry. Threadgroup memory is byte-identical across
all three, so there is **no static occupancy difference** to explain +34.58, and
the code-size delta is 288 B of AIR (mechanism F is far too small).

The MSL diffs are the load-bearing new fact. `pf0 → pf1` adds exactly one 12-line
block (3 extra AIR loads: 4 × `vec<bfloat,4>` = 32 B/thread of `router_weight`
into `thread vec<bfloat,4> laguna_pf[4]`, i.e. **8 live 32-bit registers**) plus
the peeled first 4 blocks of the dot-product loop. `pf1 → pf1c` moves that same
block from MSL line 75 to line 103 and changes **nothing else** — see §3.2.

This localises the surviving mechanism family precisely: in `pf1` those 8
registers stay live across **5 `threadgroup_barrier` calls**, and the ≈1 MB
`router_weight` read burst is issued *before* the RMSNorm reduction's own traffic
rather than after it. Both the register-liveness reading (frontier mechanism C)
and the traffic-window reading (mechanism A/E) predict a cost that the router
kernel's own label does not pay — the label got **6.39 µs/step faster** while
≈41 µs/step landed somewhere else. §3.2's A1 contrast is the direct test.

### 6.3 Phase A binary is built and pinned

`SNAP=/tmp/maple-r105b-snap`, provenance `/tmp/maple-r105b/phaseA-build.txt`.
Snapshot `head`: worker sha256
`baae191f4907664a2a4b0dfffbd1cd66dd48effec61b48e60ee9054459a78399`
(49,190,344 B), metallib
`8e8b18afaee1ed5a0190403f79a4cc74b9bebcb52b50c4b67d0ed91dc73097ec`.
**PASS(G0.4)** digest round-trip; **PASS(G0.5)** metallib byte-identical.

Note for anyone reusing the harness: `rm -rf .build-worker` destroys
`mlx.metallib` and `build_worker()` does **not** rebuild it, so the next arm
build dies at `cp .build-worker/release/mlx.metallib` with exit 5. Run
`tools/build-mlx-metallib.sh` first (50 s → 158,502,072 B).

### 6.4 What I first concluded about the submission base guard (RETRACTED in §6.4.1)

`senpai/submit-official.sh` (merged into `origin/main` as part of #547,
`e29a760` "Guard official submissions against stale bases") enforces at `:74`:

```
git diff --quiet "${main_sha}" "${base_sha}" -- "${protected_paths[@]}"
  || "official submit: BASE_SHA submitted snapshot differs from current origin/main"
```

Measured on this checkout, `origin/main = 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7`:

| candidate `BASE_SHA` | ancestor of HEAD | editable files differing from `origin/main` | guard |
|---|---|---|---|
| `768bb9d4…` (campaign BASE_SHA) | yes | **9** | **refuses** |
| `ed1ca05f…` (my assignment base = advisor branch tip) | yes | **27** | **refuses** |
| `1bc1c895…` (= `origin/main` itself) | yes | 0 | passes |

The direction matters: `768bb9d4` is an *ancestor* of `origin/main` (stale, the
case the guard was written for), but `ed1ca05f` is a **descendant** — the advisor
integration branch carries 27 editable files that are **not yet promoted to
`main`**. `benchmark.json` at my HEAD does match `main`, so only the `:74` check
fires.

I then concluded that passing `1bc1c895` "would satisfy the guard while defeating
its purpose", declared Phase B blocked, and spent zero receipts.

#### RETRACTED. That conclusion was wrong. See §6.4.1.

### 6.4.1 Retraction: I misread the guard's estimand, and Phase B was never blocked

The advisor corrected this in PR #597 fb1 and recorded **Rule 87**. I reproduced
the correction from the script itself and I accept it. The error was mine, and it
is worth naming precisely because it is the same class of error as the §11.5
retraction: **I inferred the estimand from the failure message instead of reading
what the comparison actually compares.**

Line 2 of the wrapper states its own purpose:

```
# Refuse an official submission unless its recorded base includes current fork main.
```

So the `:74` diff is an assertion about the **base**, not about the candidate:

| line | check | question it asks |
|---|---|---|
| `:9-10` | `base_input="$1"; shift` | — |
| `:109` | `exec mlxfast submit --model senpai "$@"` | `BASE_SHA` is **never forwarded**; it is a wrapper-side assertion only |
| `:51` | `git merge-base --is-ancestor "$base_sha" HEAD` | is current fork `main` *in my history*? |
| `:74` | `git diff --quiet "$main_sha" "$base_sha" -- protected` | has `main` *moved* since the base was recorded? |

What is uploaded is my **`HEAD` worktree restricted to the 97 `editablePaths`**.
A candidate is *by definition* a modification of that surface, so no candidate
commit can ever satisfy `:74` against itself. Passing my own head SHA
**guaranteed** the refusal I observed. Both the advisor and Tanjiro (#592 §4.1)
made the identical substitution; that it was a shared error does not make it less
of one.

Verified on this checkout:

| check | result |
|---|---|
| `1bc1c895…` is an ancestor of my `HEAD` | **yes** |
| `git rev-parse origin/main` | `1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7` |
| editable paths in `main:benchmark.json` | 97 |
| `:74` diff for `BASE_SHA = 1bc1c895…` | 0 files ⇒ **passes trivially** |

So passing `1bc1c895…` does **not** defeat the guard. The guard detects a *stale
base*; my base is not stale, because `origin/main` is in my ancestry and has not
moved. Passing it is the canonical correct usage, not a bypass.

**Rule 87, as I will follow it:** `BASE_SHA` names the integration base. The
recorded value is `1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7`, passed verbatim as
argument 1. I will not pass a candidate/PR-head/advisor-head SHA, and I will not
search for a SHA that makes the guard pass — the advisor has made SHA-hunting an
explicit hard negative, which is the right call given that I just demonstrated
how easy it is to rationalise one.

#### One residual I am flagging rather than silently accepting

`:74` constrains the **base**, and nothing constrains how far `HEAD` has moved
beyond `main` on the submitted surface. My `HEAD` differs from `main` on **27**
editable files, and only **one** of those is mine to change
(`Sources/MLXFastModel/LagunaRuntimeModel.swift`); the other 26 are advisor-branch
content not yet promoted. Verified: my own commits touch only `research/`, which
is off the submitted surface entirely.

The consequence is narrow but real, and it shapes how Phase B must be read:

- An **absolute** `cs` from my branch is **not** comparable to a receipt taken on
  a `main`-based tree, because 26 files of unpromoted work sit underneath it.
- A **difference between two of my own receipts** *is* valid, because both arms
  carry the identical 26 files and differ only in the knob. This is exactly what
  Phase B is — a paired P1/P0 contrast — so the design is unaffected.

I am recording this so nobody later reads a Phase B `cs` as a frontier number.

#### Consequence for the §11.3 replicate commits (advisor addendum, accepted)

The archive contains only the 97 `editablePaths`, and the service dedupes
byte-identical archives. `BASE_SHA` is identical across replicates and cannot
distinguish them, and neither can a `research/` file or a commit message. So each
replicate needs a distinguishing byte **inside a submitted file**.

This composes for free with the §9.3 deliverable: the doc blocks I owe are
comments in `LagunaRuntimeModel.swift`, which is both editable and submitted. A
one-line replicate tag in that file is therefore sufficient, and costs no
behavioural change.


### 6.5 Disclosed interim look, and the bit-exactness gate it delivered

Mid-flight, with 91 of 144 slots written, I copied the output directory and ran
`analyze-multi.py` on the partial data. The stated purpose was pipeline
validation: the analyzer sorts arm names and builds contrasts by
`itertools.combinations`, and I wanted a crash on the new `P0/P1/P1B/P5` labels
to surface while there was still time to fix it rather than after the timed
window closed. It did not crash.

I am recording the look because an interim inspection of accumulating data is a
multiplicity problem and hiding it would be dishonest. Two mitigations apply,
and neither is retrospective:

1. **Every decision rule was committed before any Phase A datum existed.** The
   A0 trigger (CI excludes 0, or `|mean| >= 8` us/step), the A0 precision gate
   (`hw <= 12`), and the four-cell A1 table are in commit `d8a5af7`; the Phase A
   job launched afterwards. The §10.2 fallback-dominance argument, which names
   `0` rather than `5`, was committed in `dda278a` — also before the look. So
   the look cannot have selected a rule, an estimator, a statistic, or a
   fallback.
2. **No stopping decision was taken on it.** The stopping rule in §5 is
   completion-based, the job ran to its full 18 repetitions, and the verdicts in
   §10 are computed from the complete 16-repetition analysis set. The interim
   numbers appear nowhere in §10.

What the interim look did deliver, and what does not depend on any timing
statistic at all, is the **correctness gate for the whole knob family**. Every
one of the 91 slots written at that point emitted a byte-identical decode token
stream:

| quantity | value |
|---|---|
| `.tokens` files compared | 91 |
| distinct sha256 over those files | **1** |
| common digest | `aaf1cccc923270801a1e16da07012bc822d9f85eb33ce6e2039fb38f407e51d8` |
| bytes per file | 1,083 |

The four arms span `DARKBLOOM_ROUTER_WEIGHT_PREFETCH` in `{0, 1, 5}`, so this is
a direct demonstration that **`prefetch=0` and `prefetch=5` are both bit-exact
drop-in replacements for the shipped `prefetch=1`** on the scored decode axis, at
this seed and step count. That matters for §10.2: the fallback I recommend is not
merely believed to be output-neutral by reading the kernel source, it is measured
to be output-neutral 91 times over. It does not substitute for
`run_upstream_equivalence.sh` or the hidden gates, which cover cases this
fixture does not, but it removes any doubt that the three settings are the same
computation.


## 7. Scope fence I am holding

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

## 8. Verdicts owed at the end (placeholders, filled in §9)

1. `research/CURRENT_RESEARCH_STATE.md:193-200` — the "free rider / Bank it"
   doctrine for #558.
2. **Rule 82** — whether "elsewhere hoisting is decided by a static read"
   survives, and replacement text if it does not.
3. The blank documentation blocks at LRM `:685-696` and `:705-711`, which
   currently carry no prefetch semantics at all.

---

## 9. Verdicts — delivered

### 9.1 `CURRENT_RESEARCH_STATE.md:193-200`, the "free rider / Bank it" doctrine

The bullet reads: *"#558 ships as a free rider and must never draw its own
receipt … E = 0.349, so the −6.3917 µs/step census win is worth 2.2307 µs/step
chained ⇒ +0.016 % decode ⇒ +0.012 % of score — about 36× below the 0.5393 %
session σ. It is free (bit-exact, 4,186 B, no risk) and therefore worth
carrying."*

**Verdict: the arithmetic is right and the inference is unsafe. Amend, do not
delete.** Two defects, the second of which is unconditional.

**(a) The magnitude claim is inverted when the measured end-to-end number is
substituted for the modelled one.** The doctrine prices the dial at
`census win × E` = 6.3917 × 0.349 = 2.2307 µs/step. #571's uninstrumented
paired design measures the same dial at **+34.58 µs/step in the opposite
direction** — **15.5×** the doctrine's own chained figure. At the decode price
of 0.015228 %/µs-step that is **0.527 % of `cs`**, i.e. **≈1.0× the 0.5393 %
session σ the doctrine used to dismiss it, not 1/36 of it.** The doctrine's own
yardstick, applied to a measurement of the quantity the doctrine is about,
reverses the doctrine's conclusion. (Conditional on A0 clearing — §3.1.)

**(b) The pricing model has no term that could ever detect this, so the
conclusion was unearned even if (a) turns out false.** `E` is a *shadowing
factor*: it discounts a per-kernel saving down to its chained contribution.
It is a one-sided operator on gains. There is no symmetric term for a
kernel-local change whose cost lands *outside its own label* — and that is
exactly the shape of what was measured (label −6.39, whole step ≈+41 elsewhere).
A model that can only shrink gains cannot represent an out-of-label loss, so
"E × win is tiny ⇒ risk-free" is not a valid inference at any value of E.

The words carrying the unearned weight are **"no risk"**. Bit-exactness and
4,186 B bound the *correctness* and *budget* risk. They say nothing about
*timing* risk, and the bullet silently promotes the first two into the third.

**Proposed amendment** (replacing "It is free (bit-exact, 4,186 B, no risk) and
therefore worth carrying"):

> It is bit-exact and 4,186 B, so its correctness and budget risk are zero.
> Its **timing** risk is *unpriced*: `E` discounts gains and has no term for a
> cost that lands outside the changed kernel's own label, which is precisely
> the failure mode R105-B measures. A change may be banked as a free rider only
> when (i) it is bit-exact **and** (ii) its end-to-end effect has been measured
> or bounded in an **uninstrumented paired** design at a precision finer than
> the claimed chained gain. Until (ii) exists the change is not a free rider;
> it is an **unpriced position**, and carrying it is a bet, not a saving.

### 9.2 Rule 82 — the static read is a veto, not an authorisation

Rule 82 (`:3051`): *"Everywhere else it is decided by a **static compile read**
(AIR/ISA, registers, spills, threadgroup memory) before any GPU time is spent —
#558 did exactly that in the router GEMV, found zero occupancy change, and
banked −6.39 µs/step. Make the static read step 1 of any codegen-restructuring
arm."*

**Verdict: the procedure survives and the factual finding survives; the word
"decided" does not.** Three findings.

1. **#558's static read replicates exactly.** My M2 (§6.2) redid it at HEAD's
   shipped 512-thread geometry — the read #558 took in the 1024-thread era —
   and every number matches: `maxTotalThreadsPerThreadgroup` 1024,
   `threadExecutionWidth` 32, `staticThreadgroupMemoryLength` **4240 B**,
   identical across `pf0`/`pf1`/`pf1c`. Rule 82's evidence is not stale and
   `CURRENT_RESEARCH_STATE.md:160-166` needs no retraction.
2. **A clean static read is nevertheless compatible with a +34.58 µs/step
   end-to-end penalty.** Same binary, same metallib, same threadgroup memory,
   same thread limits, 288 B of AIR apart, and 21/21 paired slots slower. So
   the static read cannot *authorise* a hoist. It can only *veto* one.
3. **"Zero occupancy change" is over-claimed even as a static statement.**
   `maxTotalThreadsPerThreadgroup` reports the largest threadgroup the register
   allocation permits. This kernel launches **512**, well under the reported
   1024, so the metric is *not binding* on either arm and cannot distinguish
   them. What Metal does **not** expose is the quantity that matters here: how
   many 512-thread threadgroups stay co-resident per core. `pf1` holds 8 extra
   live 32-bit registers per thread across 5 barriers = **16 KB of extra
   register file per resident threadgroup at 512 threads**. That can halve
   co-residency with no change whatsoever in any statistic #558 read. The
   correct static conclusion is the weaker *"no threadgroup-level occupancy
   limit change"*.

**Proposed replacement for the second sentence of Rule 82:**

> Everywhere else a **static compile read** (AIR/ISA, registers, spills,
> threadgroup memory) is **step 1 and a veto, not an authorisation**. A read
> that shows growth in spills or threadgroup memory, or a drop in
> `maxTotalThreadsPerThreadgroup` below the launched width, kills the arm for
> free. A read that shows none of that has established only that there is **no
> threadgroup-level occupancy limit change** — it has *not* established
> per-core threadgroup co-residency, which Metal does not expose, and it has
> *not* established anything about cost landing outside the changed kernel's
> own label. Promoting a hoist therefore still requires an **uninstrumented
> paired end-to-end** measurement. #558's read was executed correctly and its
> numbers replicate at the shipped geometry (R105-B §6.2); what did not follow
> was the promotion.

The banned/allowed split (fused attention vs elsewhere) is untouched: #540's
attention cliff is a *static* veto, exactly what clause 1 keeps.

### 9.3 The blank documentation blocks at LRM `:685-696` and `:705-711`

Both blocks are empty at HEAD, so the shipped default `return 1` carries no
recorded semantics at all. Text applied to source after the Phase-A timed window
closes (editing `Sources/` during the run would trip the harness's own
`digest_before`/`digest_after` Rule-75 check). Content: the allowed set
`[0, 1, 5]`; the mapping through `lagunaRouterPrefetchGroups`
(`rowsPerThread != 1` ⇒ 0; `5` ⇒ 1 group with the block placed *after* the
reduction; otherwise `groups = prefetch`); the variant key
`rowsPerGroup*8 + prefetch` and the `_pf1c` / `_pf<groups>` suffix rule; and the
one fact a future reader most needs — that `1` and `5` emit **identical
instructions** and differ only in placement relative to the 5 threadgroup
barriers, so they are a matched pair for attributing any cost to placement
rather than to the loads.

## 10. Phase A results and the preregistered verdicts

### 10.1 A0 — the A/A null for the contrast estimator

Phase A finished 18 repetitions × 8 slots = 144 timed slots, 16 analysed after
the preregistered 2-repetition warm-up (exactly 4 complete rotation cycles).
All four gates cleared before any number was read:

| gate | requirement | result |
| --- | --- | --- |
| G1 slot count | 144 | 144 |
| G2 Rule-75 tree digest | `digest_after == digest_before` | `d93a6d14…` both sides, `PASS(rule 75)` |
| G3 token identity | one distinct `sha256` over all slots | 1 distinct: `aaf1cccc…e51d8`, 1,083 B × 144 |
| G4 arm balance | 36 slots per arm | 36 / 36 / 36 / 36 |

G3 is the correctness result of the round and it is stronger than the timing
one. `DARKBLOOM_ROUTER_WEIGHT_PREFETCH ∈ {0, 1, 5}` produced **byte-identical
greedy token streams in all 144 slots**, so `0` and `5` are bit-exact drop-in
replacements for the shipped `1` on this host and this checkpoint.

**A0 verdict: `A0-INCONCLUSIVE`.**

| estimator | mean | 95 % hw | CI | signs | K |
| --- | --- | --- | --- | --- | --- |
| cycle-blocked (**primary**, preregistered) | **+4.04** | 13.77 | [−9.73, +17.81] | 2/2 | 4 |
| per-repetition (secondary) | +4.04 | 7.71 | [−3.67, +11.74] | 8/8 | 16 |

The preregistered table in §3.1 keys A0 off the primary estimator, and the
primary estimator misses the 12 µs/step precision requirement (13.77 > 12), so
the honest reading is `A0-INCONCLUSIVE`: the A/A null covers zero, but partly
because the interval is wide. Under the secondary per-repetition estimator the
same point estimate would have delivered `A0-CLEARS` (hw 7.71 ≤ 12). I record
the branch selected by the rule I wrote down first, not the one I would prefer.

What matters for the round is that **A0 did not fire `A0-FIRES-N1`**: the mean
is +4.04 with |+4.04| < 8, and the interval covers zero on both estimators. The
preregistered kill switch — retract the +34.58 and spend no receipt — is
therefore **not** triggered, and Phase B is authorised.

**The replicate delivered something better than a tight null.** `P1` and `P1B`
are the same environment value and therefore the same machine code. Each was
independently contrasted against `P0`:

| contrast | cycle-blocked | per-repetition | signs |
| --- | --- | --- | --- |
| `P0->P1` | +25.90 [+17.33, +34.47] | +25.97 [+19.88, +32.06] | 4/0 and 16/0 |
| `P0->P1B` | +29.94 [+20.47, +39.41] | +30.02 [+24.13, +35.91] | 4/0 and 16/0 |

Two independent estimates of one quantity, both excluding zero with every
repetition and every cycle on the same side. An A/A null whose interval is wide
is a statement about the noise floor of a single 4-cycle contrast; two
replicates that separately reject zero and land 4 µs apart is a statement about
the effect. The second is the evidence the round needed.

Pooling the two replicates — legitimate because they are byte-identical code —
gives the headline of Phase A:

| pooled `mean(P1, P1B) − P0` | mean | 95 % hw | CI | signs | K |
| --- | --- | --- | --- | --- | --- |
| cycle-blocked (primary) | **+28.00** | **5.77** | [+22.23, +33.77] | 4/0 | 4 |
| per-repetition | +28.00 | 4.58 | [+23.42, +32.58] | 16/0 | 16 |

The pooled primary half-width is 5.77 µs/step, which **clears the 8 µs/step
precision target** that the single `P1->P1B` cell missed. Reproduced with
`research/maple-frieren-r105b-pooled.py`.

Two caveats I will not bury. First, the analyser's own `precision` field reports
`worst_half_width_m4 = 13.77`, `pass = false`, because it reports the worst of
all six pairwise contrasts and the worst one is the A/A cell. That field is
accurate and I am not overriding it; I am pointing out that the contrast the
round is about is measured four times more precisely than the cell that sets the
worst case. Second, the pooled estimator was **not** preregistered — §3.1
preregistered `P1->P1B` as the null and `P0->P1` as the effect. Pooling is a
post-hoc precision gain, so it is reported alongside the preregistered cells and
never in place of them; every preregistered branch above is decided on the
preregistered cell.

The blanket noise gates both cleared this time, which they did not for #571:
`n2_fires = False` (no within-arm drift cell rivals a contrast) and
`n5_fires = False`. The pooled within-arm nulls are quiet at every separation:
`sep1 +8.44 [−3.16, +20.05]`, `sep3 +6.58 [−4.82, +17.99]`,
`sep5 −3.96 [−10.00, +2.08]`, `sep7 −10.04 [−22.18, +2.10]`.

### 10.2 Which fallback, `prefetch = 0` or `prefetch = 5`?

This subsection is placed **before** the A1 verdict on purpose: the answer does
not depend on which A1 branch fires, and I want that on the record before I see
the numbers. §3.2's V-PLACEMENT row originally implied `5` was the natural
fallback because it "keeps the label's ILP win". That was wrong ([ERRATUM E2]),
and once it is removed there is no argument left for `5` over `0`.

**The label win does not exist for `5`.** From
`research/CURRENT_RESEARCH_STATE.md:158-170`, the four-cell router-label census
reads pf0 319.8417, pf0b 319.9000, pf1 313.5083, pf1c 319.8917 µs/step. The
`_pf1c` variant is what `prefetch = 5` selects. Its contrast against the
replicate baseline is the Rule-79 null cell itself:
`pf1c − pf0b = −0.0083 µs/step [−0.9698, +0.9531]`, and against the first
baseline `pf1c − pf0 = +0.0500`. Both sit inside a ±1 µs/step A/A noise floor.
So the −6.4 µs/step that #558's decision row was bought with is credited
**100 % to the cross-barrier hoist and 0 % to the prefetch block**. `5` puts the
block back where it does nothing measurable, in either direction.

**`0` dominates `5` across the whole A1 decision table.** This is the argument I
actually rely on, because it does not require Phase A to land on any particular
branch:

| A1 branch (§3.2) | Fallbacks that remove the cost | Recommended |
|---|---|---|
| **V-PLACEMENT** (`P5 ≈ P0`, `P1 − P5 > 0`) | `0` and `5` both do | `0` — same fix, less machinery, no unmeasured bet |
| **V-PEEL** (`P5 ≈ P1`, `P1 − P0 > 0`) | only `0` | `0` |
| **V-MIXED** (`P5` strictly between `P0` and `P1`) | `0` fully, `5` partly | `0` |
| **V-NEITHER** (`P1 ≈ P0`) | none — this is N-1 territory | none; retract §1.1 |

There is no cell in which `5` is the recommendation. Four supporting reasons,
in descending weight:

1. **Less live machinery.** `prefetch = 0` drives
   `lagunaRouterPrefetchGroups` to `0`, which makes the variant suffix empty and
   selects the plain kernel: no `laguna_pf[4]` declaration, no four
   `vec<bfloat,4>` loads, no 4-block peel. `prefetch = 5` selects `_pf1c`, a
   third distinct router kernel that has to be compiled, cached, and — because
   this family has an `mlx-generated/*.cpp` twin — kept byte-consistent with its
   embedded source forever. Paying that maintenance surface for a contrast whose
   CI straddles zero is a bad trade.
2. **`5` is a bet on an unmeasured upside; `0` is not a bet.** There exists a
   measured M4 Pro reading that `5 ≈ 0` in the label. There exists **no**
   measured reading, on any host, in which `5 > 0`. The case for `5` is
   therefore entirely a conjecture that the peel helps somewhere we have not
   looked — plausibly on M5, whose memory system is ~2.3× wider (610 GB/s
   measured vs 266.3) and whose `_nax` kernel selection differs. §11.9 puts
   10-20 % on pf1c actually being *worse* than pf0 on M5. `0` has no comparable
   tail because it is the absence of the mechanism under suspicion.
3. **The static read is a veto, not an authorisation** (§9.2, Rule 82). M2
   established that `_pf1c` costs nothing in occupancy terms: identical
   `staticThreadgroupMemory` 4240 B, identical `maxTotalThreadsPerTG` 1024,
   launchable at the 512-thread geometry the runtime actually uses, same 5
   barriers, +3 AIR `load` instructions. That means the static read does not
   *forbid* `5`. It cannot license `5` over `0`, and I will not let it.
4. **Attribution.** Shipping `0` removes the mechanism; any subsequent reading is
   unambiguous. Shipping `5` leaves a moved-but-present block, so a future win or
   loss cannot be cleanly assigned. `0` is also the state that #558 replaced, so
   it carries the longest measured history on this codebase.

**What would overturn this.** One thing only: a paired official M5 A/B/A over
{`0`, `1`, `5`} in which `5` beats `0` outside the paired noise band. That is
exactly the Phase B measurement. I first believed the submit guard forbade it;
that was my error and is retracted in §6.4.1, so the measurement *is* available.
It remains undrawn only because Phase B budget goes to the P1/P0 contrast that
adjudicates the shipped default, which is the assignment's question; a three-way
{`0`,`1`,`5`} arbitration is a follow-up, not a substitute. Until it is drawn the
recommendation is `0`, and I am explicit that this is a *recommendation about a
default*, not a measured M5 result.

### 10.3 A1 — placement versus peel

**A1 verdict: `V-PLACEMENT`.** All three preregistered conditions hold on the
primary cycle-blocked estimator:

| preregistered condition | required | measured | holds |
| --- | --- | --- | --- |
| `P0->P1` lo > 0 | the shipped default costs end to end | +25.90, lo **+17.33** | yes |
| `P0->P5` covers 0 | the same loads below the barriers cost nothing | +6.53, [**−4.65**, **+17.71**] | yes |
| `P1->P5` hi < 0 | moving them down recovers the loss | −19.37, hi **−10.83** | yes |

Arm levels, µs/step, mean of slot medians over the 16 analysed repetitions:

| arm | env | level | vs `P0` |
| --- | --- | --- | --- |
| `P0` | `…PREFETCH=0` | 8244.52 | — |
| `P1` | `…PREFETCH=1` (shipped) | 8270.42 | +25.90 |
| `P1B` | `…PREFETCH=1` (replicate) | 8274.46 | +29.94 |
| `P5` | `…PREFETCH=5` (placement control) | 8251.05 | +6.53 |

The ordering is `P0 ≲ P5 ≪ P1 ≈ P1B`. `P1` and `P1B` issue the same four
`vec<bfloat, 4>` loads as `P5`; the only difference between them and `P5` is
whether those loads sit above or below the RMSNorm reduction and its five
threadgroup barriers. So the cost is not the loads. **It is the hoist.**

Three cross-checks, none of which is the decision variable:

1. **Position-matched.** Each of the four rotation-phase slot pairs gives an
   independent `P0->P1`: +28.22, +22.70, +25.04, +27.63 — spread 5.52, all four
   positive; and `P0->P1B`: +32.79, +27.66, +25.97, +33.53 — spread 7.56, all
   four positive. `P0->P5` is the one contrast that does *not* keep its sign
   across positions (+12.96, +8.98, +4.89, −0.31), which is what a genuine null
   looks like.
2. **Step-index profile.** `P1−P0` is +22 to +34 µs/step in every window from
   step 1 to step 250, i.e. a *sustained* per-step cost, not a per-slot constant
   (a constant `C` would appear in the mean and vanish from the median profile).
   `P5−P1` is −15 to −32 across the same windows. The step-0 contrasts are all
   noise (`P0->P1` −538 µs, CI [−2433, +1357]).
3. **Slot-median distributions.** `P1` and `P0` overlap here (min(P1) − max(P0)
   = −53.1), unlike #571 rung 2 where `C` and `B` were disjoint. That is honest
   evidence that the between-slot variance on this host is larger than the
   effect and that the *pairing* is doing the work — which is exactly why the
   design pairs within repetitions.

**Magnitude versus the #571 prediction.** §1.1 predicted +34.58 µs/step with CI
[+26.39, +42.77]. Phase A measures +28.00 pooled, CI [+22.23, +33.77]. The
intervals overlap on [+26.39, +33.77]; the point estimate reproduces at
**0.81×**. The sign, the ordering, and the mechanism all reproduce; the
magnitude reproduces at the low edge of the prior interval. I therefore restate
§1.1's headline as **+28.00 µs/step = +0.426 % of the composite score = 0.79
nominal session σ** and treat the +34.58 figure as superseded by the larger,
better-controlled measurement rather than as confirmed.

**Where that leaves the §1 contradiction.** The per-kernel `SPLIT=1` census
measured the shipped hoist at **−6.39 µs/step (faster)** with 12/12 negative
signs and a ±0.43 floor. Phase A measures the same hoist end to end at **+28.00
µs/step (slower)** with 16/16 positive signs. Both measurements are sound
measurements of different things, and §11.10 gives the mechanism that makes the
sign flip predictable rather than paradoxical: `SPLIT=1` gives every one of the
406 dispatches its own command buffer, so the census times the salvo arriving on
an idle memory fabric, while the shipped 45-command-buffer regime lands the same
salvo in the drain tail of the preceding dispatch, where queueing delay is
convex in arrival rate. The instrument is not wrong; it is blind to the only
regime that is scored.

### 10.4 What Phase A settles and what it does not

**Settled.**

1. `DARKBLOOM_ROUTER_WEIGHT_PREFETCH ∈ {0, 1, 5}` is **bit-exact** across all
   144 timed slots — one `sha256` for every checked greedy token stream. `0` is a
   drop-in for the shipped `1` with no correctness risk on this host and
   checkpoint. This holds independently of every timing number in this document.
2. On M4 Pro the shipped default is an **end-to-end decode regression** of
   +28.00 µs/step, CI [+22.23, +33.77], 16/16 repetitions and 4/4 rotation
   cycles on the same side, with two independent replicates of the same code each
   excluding zero on their own.
3. The cost is attributable to the **cross-barrier hoist**, not to the four
   loads and not to the four-block peel: the same loads emitted below the five
   threadgroup barriers (`prefetch = 5`) are indistinguishable from not emitting
   them at all (+6.53, CI [−4.65, +17.71]), and moving them down from the hoisted
   position recovers −19.37, CI [−27.92, −10.83].
4. The §1 contradiction is **resolved in favour of the end-to-end measurement**,
   with a mechanism (§11.10) that explains why the `SPLIT=1` per-kernel census
   reports the opposite sign rather than merely failing to see the cost.
5. The recommended fallback is **`0`, not `5`** (§10.2, committed before any data
   was read). Phase A adds one unpreregistered reason: `P0->P5` has a positive
   point estimate (+6.53) with 4/4 positive cycles, so if `5` differs from `0` at
   all, the available evidence leans to `5` being the *worse* of the two.

**Not settled.**

1. **Transfer to M5.** Everything above is M4 Pro. M4 Pro reports Apple GPU
   generation 16, has fewer cores, and a different memory-system arrival-rate
   regime — and the mechanism in §11.10 is *specifically* an arrival-rate
   mechanism, which is the class most likely to change magnitude, and possibly
   sign, with core count and fabric width. This is not an `_nax` kernel, so the
   kernel family does reach the ranked M5; the regime does not necessarily.
2. **The magnitude that would be scored.** §11.5 records that the
   KV-proportional reading is underpowered, not refuted. Phase A's own
   per-repetition and bootstrap slope intervals for `P1−P0`
   (+0.0787 ± 0.0805 and +0.0602 [+0.0070, +0.1129] µs per KV token) disagree
   about whether zero is excluded — section 6 covers zero, section 7 excludes it
   — and the report's own rule is that a haircut needs **both**. So the scored
   128-step-window haircut is still not licensed and +28.00 is quoted unhaircut.
3. **Which of the two leading mechanisms it is.** §11.7 ranks burst arrival into
   the preceding dispatch's drain tail above self-delay of the kernel's own
   residual loads, but Phase A separates neither; both predict exactly the
   observed `P1` ≫ `P5` ≈ `P0` ordering.
4. **Whether the −6.39 label win is real in the shipped regime.** Conceded in
   §11.10: the census that produced it also ran on an idle fabric, so its sign
   under 45 command buffers per step is unknown.
5. **Whether `1` is beaten by `0` on the frontier tree.** My branch differs from
   `origin/main` on 27 editable files, 26 of them unpromoted advisor-branch
   content (§6.4.1 residual). An absolute `cs` from this branch is therefore not
   frontier-comparable; only the *difference* between two of my own receipts is
   valid, which is what Phase B draws. Some of those 26 files touch MoE and
   attention and could in principle interact with the router prefetch, so even
   the paired difference is a difference measured on my tree, not on the
   frontier's.
6. **Statistical strength of Phase B as budgeted.** §4.1.1 established, from 14
   consecutive receipts on this account, a paired receipt-to-receipt σ of
   ≈31.9 µs/step — 1.9× the inherited σ_pair. Against a +28.00 effect, two
   pairs give ±44.2 µs/step. Phase B is a **sign-and-transfer check, not a
   confirmation**, and that was accepted in writing before the first receipt was
   drawn.

## 11. Adversarial review of §§0-5, and the four corrections it forced

While the Phase-A window was open I ran an independent review pass over §§0-5
with no access to my own reasoning chain, specifically asked to attack the
framing rather than agree with it. It found four defects. I verified all four
myself from source and from the surviving data, and all four are recorded here
rather than silently patched, because §§0-5 are preregistration text. **No
preregistered trigger condition in §3.1 or §3.2 is changed by any of them.**

### 11.1 E1 — the prefetch salvo is 256 KB per invocation, not ~1 MB

My §3.2 said pf1 issues "a ~1 MB `router_weight` burst". That is 4x too high.
From `research/msl/r100c_rpg8_pf1.metal`, which §6.2 committed:

| quantity | value | source |
|---|---|---|
| `axis_size` | 2048 | kernel constant |
| `block_width` | 128 | kernel constant |
| `router_blocks` | 2048 / 128 = 16 | derived |
| `rows_per_group`, `rows_per_thread` | 8, 1 | shipped geometry |
| prefetch block | `:75-86`, 4 x `vec<bfloat,4>` per thread | read |
| consumer peel | `column += 4 * block_width` | first **4 of 16** blocks = 1/4 row |

Per threadgroup the peel covers 8 rows x 4 blocks x 128 cols x 2 B = 8 KB.
Threadgroups = 256 rows / 8 = 32, so **262,144 B = 256 KiB per invocation**,
exactly one quarter of the 1 MiB router weight (256 x 2048 x 2 B = 1,048,576).

Two independent confirmations of the invocation count fell out of this:
`LagunaConfig.swift:542` requires `mlp_layer_types` to be "dense at layer 0 and
sparse at layers 1-39", so there are **39 routed layers**, and 39 x 1 MiB =
40.89 MB/step — exactly the router-GEMV traffic figure in
`CURRENT_RESEARCH_STATE.md:158-170`. So 39 router invocations per decode step.

The load-bearing consequence is one I had missed entirely: **pf1 does not move
more bytes than pf0.** The prefetch and the peel read precisely the bytes the
unpeeled loop would have read. Every mechanism of the form "pf1 costs more
because it transfers more" is therefore unavailable a priori. Only *when* the
256 KiB is requested differs.

Applied inline as `[ERRATUM E1]` at §3.2.

### 11.2 Per-invocation accounting

At 39 invocations/step:

| quantity | per step | per invocation |
|---|---|---|
| end-to-end penalty (#571 primary) | +34.58 us | **+0.887 us** |
| kernel-label credit (`SPLIT=1`) | -6.39 us | **-0.164 us** |
| implied cost outside the measured kernel | +40.97 us | **+1.051 us** |
| time to stream 256 KiB at M4 Pro's 266.3 GB/s | — | 0.984 us |

The implied out-of-kernel cost is 1.07x the time the salvo would take to drain
at nominal peak bandwidth with nothing else running. I am deliberately not
calling that identification: 266.3 GB/s is nominal rather than achieved, the
arithmetic assumes all 39 invocations pay equally, and a ratio near 1 is
suggestive at best. What it does establish is a **scale check**: the residual is
the right order of magnitude for "the salvo is effectively serialised against
the rest of the step", and it is two to three orders of magnitude too large for
a register-pressure or occupancy story — which §6.2's static read had already
ruled out independently.

### 11.3 E2 — `prefetch = 5` does not retain the kernel-label win

My §3.2 claimed pf1c "keeps the label's ILP win". It does not. Label values from
nezuko-r100c via `CURRENT_RESEARCH_STATE.md:158-167`:

| variant | label us/step | vs pf0 | Rule-79 same-arm null |
|---|---|---|---|
| pf0 | 319.8417 | — | pf1c - pf0b = -0.0083 [-0.9698, +0.9531] |
| pf0b | 319.9000 | +0.058 | (the null cell itself) |
| pf1 | 313.5083 | **-6.333** | |
| pf1c | 319.8917 | +0.050 | inside the null |

pf1c is label-neutral. Since §6.2 established that pf1 and pf1c emit the
**identical** 12-line load block and differ only in its position relative to the
five `threadgroup_barrier`s, the label credits **100 % of its -6.39 win to the
cross-barrier hoist and 0 % to the block itself**. Applied inline as
`[ERRATUM E2]`. This does not touch the A1 prediction table; it changes which
question §10.2 has to answer, and it is why §10.2 exists.

### 11.4 E3 — the "+41 us elsewhere" claim locates nothing

The arithmetic is right (34.58 + 6.39 = 40.97 us/step; 36.81 with the
doctrinal deflator). The *location* claim — that the residual lands in
identifiable other kernels — rested on a `SPLIT=1` per-kernel census. That
census serialises the command stream in order to attribute time per kernel,
which destroys precisely the overlap any arbitration or scheduling mechanism
lives in. **A serialised census cannot locate a cost that only exists when
kernels overlap.** I am downgrading +40.97 us/step to an accounting residual
with no attributed location, and the mechanism ranking in §11.7 stands without
it.

### 11.5 E4 — my "growth" claim was overstated, and testing it properly refuted it

The review flagged an internal inconsistency in my growth statistics. It was
real, and the correct treatment is worse for me than the criticism was.

First the honest description. The step-window medians of `C-B` are +32.23
(window 0-1), then a dip to +24.56 at 10-25, then a rise to +33.63 at 200-250.
That is **not monotone**. And the window-profile mean (+28.45) is not the
primary contrast (+34.58) because the primary is a difference of per-slot
medians, not a mean of per-step medians.

Rather than defend "growth", I tested the model that would explain it. Because
step index *is* KV length here, a gap proportional to KV length is a sharp
hypothesis, and it has a strong mechanistic implication: the router GEMV never
touches KV, so a KV-proportional cost could only be produced by *interaction*
with the attention stream. Sections 5-7 of
`research/maple-frieren-r105b-stepwise.py` now test it three ways.

**Section 5 — fit the pooled window profile.** This looks excellent:

| contrast | dial flipped? | mean us | prop R^2 | affine R^2 | us/KV-tok | elasticity |
|---|---|---|---|---|---|---|
| `B-A` (rebuild only, pf0 both sides) | no | -5.85 | **-0.546** | +0.051 | +0.00406 | -0.41 |
| `C-A` (rebuild + pf0->pf1) | yes | +22.60 | **+0.804** | +0.811 | +0.04265 | +1.11 |
| `C-B` (pf0->pf1) | yes | +28.45 | **+0.793** | +0.848 | +0.03859 | +0.79 |

Reference model is a constant gap (R^2 = 0 by construction). Both contrasts that
flip the dial are well described by proportionality through the origin, the
contrast that does not flip the dial is described *worse than by its own mean*,
and the elasticities straddle 1. It even has an apparent specificity control.

**Sections 6 and 7 — give that fit an interval, and it dies.** Section 6 fits
one slope per repetition and takes a paired t interval; section 7 bootstraps
repetitions (2,000 draws) and refits the pooled median profile, so section 5's
own estimator finally gets an interval:

| contrast | per-rep slope (S6) | bootstrap pooled slope (S7) | bootstrap haircut 128/250 |
|---|---|---|---|
| `B-A` | +0.00433 +- 0.04221 | +0.00504 [-0.02931, +0.03475] | +1.0365 [+0.7170, +1.2257] |
| `C-A` | +0.01680 +- 0.04529 | +0.02547 [-0.00831, +0.06165] | +0.9378 [+0.8165, +1.0187] |
| `C-B` | +0.01247 +- 0.03979 | +0.02099 [-0.00963, +0.05789] | +0.9616 [+0.8932, +1.0172] |

**Every slope interval covers zero.** The section-5 point estimate (+0.0386) is
inside the bootstrap interval, but so is 0. The R^2 = 0.79 was the classic
artefact of fitting nine highly correlated aggregates: averaging away the
rep-to-rep variance before fitting produces a tight-looking line whose slope is
not actually resolved. The "specificity control" is equally unresolved, since
`B-A`'s slope interval also covers zero and overlaps `C-B`'s.

So I am retracting the KV-proportionality inference. It is the single most
attractive new idea I had this session — it would have promoted one mechanism
above all others and given the effect a physical story — and the correct
estimator does not support it. **Status: underpowered, not refuted.** The point
estimates lean positive and the effect may well be real; this dataset cannot
resolve a slope of ~0.02 us/KV-token against zero. §12.1 is the design that can.

### 11.6 Consequence: the headline number is quoted unhaircut, and that is not a free pass

I had derived a scored-window haircut of 576/637 = 0.9042 from the section-5
fit, which would have moved the claim to +31.27 us/step and 0.88 sigma. The
bootstrap haircut for `C-B` is **+0.9616 [+0.8932, +1.0172]**, which covers 1.0,
and the paired estimator puts the gap at +35.95 +- 6.88 at KV 636 versus
+35.19 +- 7.71 at KV 575 — a 2 % difference, not 10 %. **The haircut is not
licensed, so §1.1's +34.58 us/step and 0.527 % of `cs` stand as written.**

I am recording this the honest way round: the headline survived because the
correction could not be established, not because I checked and it was absent.
The interval admits a haircut as large as 0.89, i.e. a true scored-window
effect as small as ~+30.8 us/step. That is inside the band §4.1 already
described as underpowered.

### 11.7 Mechanism ranking after all of the above

This table was rewritten once more after §11.10, which withdrew one of the two
original co-leaders on a code fact I should have checked earlier.

| rank | mechanism | status |
|---|---|---|
| 1 | **burst arrival into the preceding dispatch's drain tail** (§11.10) | best-supported. Consistent with every fact I hold — no extra bytes, pf1c label-neutral, kernel faster in isolation, step slower together, §11.2's 1.05 vs 0.96 µs scale check — and it *explains* the census/e2e disagreement rather than shrugging at it. Unmeasured. |
| 2 | **self-delay of the kernel's own residual loads behind the salvo** | the same queueing physics applied inside the kernel instead of across the dispatch boundary; the five barriers amplify any such delay. Predicts the same sign. **Not separated from rank 1** by anything I hold. |
| 3 | DVFS / power-arbitration response to salvo burstiness | untested; predicts a frequency signature that `powermetrics` per arm would show cheaply (§12.2). Demoted from 1= because it must also explain why a ≈1 µs burst occurring 39× inside an 8.25 ms step moves the clock at all. |
| — | ~~bandwidth / arbitration against the concurrent attention KV read stream~~ | **withdrawn in §11.10.** MLX barrier-separates *dependent* dispatches (`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp:362-375`) and the router kernel consumes the attention output, so there is no concurrent attention stream for it to arbitrate against. This was a co-leader in the previous version of this table and it should not have been. |
| 5 | occupancy / register pressure | argued down by §6.2's static read: identical `maxTotalThreadsPerThreadgroup` (1024), execution width (32) and static threadgroup memory (4240 B) across pf0/pf1/pf1c, and the launch geometry is 512 threads, so the 8 extra live registers are non-binding (§9.2). |
| 6 | SLC pollution | argued down on magnitude: 256 KiB per invocation against a last-level cache in the tens of MB, and the same kernel reads those bytes moments later regardless. |

Ranks 1 and 2 are not separated by any evidence I hold. I am not going to pretend
otherwise. §12.2 is the cheapest thing that would separate them.

### 11.8 Artefact ranking, with the falsifier for each

| artefact | falsifier | status |
|---|---|---|
| A1 arm side effects / arm-label mismatch | A0 (`P1` vs `P1B`), plus the `P5` arms | Phase A |
| A2 residual misattributed to specific kernels | — | conceded in §11.4 |
| A3 drift aliasing | disjoint slot-median supports and the 6/6 position table (§6.1); A0 retests on the fresh tree | already strong |
| A4 tree specificity | Phase A rebuilds the tree (§2). If `P0->P1` does not reproduce ~+30, the #571 effect was specific to the stale tree | Phase A |

### 11.9 M5 transfer

Sign is likely preserved but attenuated if DVFS contributes, since the M5 Max
has more power and bandwidth headroom. Nothing compiler-dependent transfers
reliably at all: the review put the risk that pf1c is *worse* than pf0 on M5 at
10-20 %, via a backend that hoists the loads anyway and then pays the same
placement cost. That is decisive for §10.2 and is why the recommended fallback
is `0` rather than `5`. The M5 pair that would settle it is drawable (§6.4.1
retracts my earlier claim that it was not); it is simply not this assignment's
question, so it is listed as a follow-up in §12.

### 11.10 A second review pass: the dispatch topology, and what it costs me

Still inside the Phase-A window I checked one thing I had been assuming rather
than verifying — **what actually runs next to the router kernel** — and ran a
second independent consultation on the paradox itself. Both changed §11.7.

**The dispatch topology, from code.** All of this is verified in this checkout:

| fact | evidence |
|---|---|
| The fused residual+RMSNorm+router kernel is encoded into the **same command buffer** as the same layer's attention kernels and as adjacent layers' kernels; there is no eval, sync or encoder boundary in the layer body | `Sources/MLXFastModel/LagunaRuntimeModel.swift:11153` (layer body), `:11165` (`selfAttn`), `:11180` (fused router), `:11219` (MoE) |
| MLX closes a command buffer when `(buffer_ops_ > max_ops) \|\| ((buffer_sizes_ >> 20) > max_mb)` | `Vendor/mlx-swift/.../backend/metal/device.cpp:484-487`; split executed at `.../metal/eval.cpp:59-67` |
| Effective caps on a ≥64 GiB host are **200 MB / 200 ops** (the low-memory 128 MB/64 ops branch and the 320 MB/128 ops constants are mutually exclusive alternatives that do not apply) | `Sources/MLXFastModel/LagunaRuntimeWeights.swift:358-398`, esp. `:385-388` |
| Explicit boundaries per decode step: 1 layer-0 attention `asyncEval` + 7 stage fire points (`DARKBLOOM_DECODE_ASYNC_STAGE` default `at:0,1,7,15,23,31,39`) = **8**; the other ~37 of the measured 45 CBs/step are `needs_commit()` byte-cap commits | `:6010-6018`, `:744-770`, `:11444`, `:11695`/`:11707` |
| Exactly **one blocking CPU sync per decode step**, at the very end | `Sources/MLXFastHarness/LagunaCorrectness.swift:108` (`argMax().item()`) |
| **406** dispatches/step and 45 command buffers/step; `SPLIT=1` turns those 45 into 406 | `research/RESEARCH_ARCHIVE_through-round-91.md:4067-4068`, `:4088-4090`, `:69` |
| The router kernel is **39 dispatches/step at 312.8 µs/step** — a third independent confirmation of §11.1's 39 routed layers, and it matches the pf1 census cell 313.5 | `research/advisor-r94-idea-slate.md:134-136` |

**What this costs me: one co-leader is withdrawn.** MLX uses a concurrent
compute encoder and inserts memory barriers only between *dependent* dispatches
(`device.cpp:362-375`). The router kernel consumes the attention output (it is a
residual add plus RMSNorm over `h`) and its outputs feed the MoE, so it is
barrier-separated on both sides. **There is therefore no concurrent attention KV
read stream for the salvo to arbitrate against.** My previous §11.7 rank-1=
"bandwidth / arbitration interaction with the attention KV stream" is, as
literally written, wrong. I should have checked the encoder's barrier rule before
ranking a mechanism that depends on overlap.

**What replaces it is sharper, not vaguer: a barrier drains the dependency, not
the memory system.** `memoryBarrierWithScope` guarantees that the producer's
results are *visible*. It does not guarantee that the fabric, SLC and DRAM
controller queues are *empty*. At the instant the router kernel's first
threadgroups launch, the preceding dependent dispatch's write-back and the
residual reads are still in flight. A hoisted salvo issues 256 KiB of demand
loads — 32 threadgroups × 8 KiB, arriving as roughly 256 strided 1 KiB runs — in
the kernel's first cycles, i.e. directly into that drain tail. The late variant
issues the identical requests after the RMSNorm reduction, hundreds of
nanoseconds later, by which time the tail has cleared. Queueing delay is convex
in arrival rate, and a row-hit-first memory scheduler will let a dense burst
capture the controller ahead of latency-sensitive traffic, so the *same bytes*
cost more when they arrive as a burst on a busy fabric than staggered on a quiet
one. Under the "no extra bytes" constraint of §11.1 that arrival pattern is the
only degree of freedom left, so this is where the effect has to live.

**This dissolves E3's regime objection into a mechanism.** §11.4 conceded that a
serialised census cannot locate the cost, but left it at that. The topology says
why: `SPLIT=1` puts every dispatch in its **own command buffer** — 406 instead of
45, priced by the archive at 1.317 µs/dispatch. A command-buffer boundary is a
far longer quiet gap than a barrier, so under the census the fabric *is* idle
when the router kernel starts, and the hoist shows only its latency-hiding
benefit (−6.4 µs/step). In the shipped 45-CB regime the same hoist lands in a
busy queue. Identical instructions, opposite sign, no contradiction.

**Status: hypothesis.** It is consistent with every fact I hold and it has the
right magnitude (§11.2: implied +1.05 µs/invocation against a 0.96 µs salvo drain
at 266.3 GB/s). But nothing I hold *discriminates* it from the consultation's
second candidate — the salvo delaying the kernel's *own* residual loads into the
RMSNorm reduction, which is the same queueing physics applied inside the kernel
rather than across the boundary, amplified by the five barriers. Both predict the
observed sign and roughly the observed magnitude. Neither is measured.

**Convergence worth recording.** The consultation's top recommendation was "run
the existing end-to-end harness on pf1c — apparently never done." That is exactly
Phase A's `P5` arm, already in flight when the advice arrived. Under the boundary
story `P5` should recover most of the 34.6 µs/step; under a purely in-kernel
story it should not. An independent reviewer and the preregistration picked the
same next measurement, which is mild evidence that §3.2 was designed around the
right question.

**Two things I now have to own.**

1. The −6.4 µs/step label win was itself only ever measured on an idle fabric. I
   had been treating it as a real benefit that is merely outweighed. The honest
   reading is that **its sign in the shipped regime is unknown**, and that is a
   stronger statement against `prefetch = 1` than the one §1.1 makes.
2. **AIR-identical is not ISA-identical.** §6.2 compared MSL, AIR and metallib
   bytes, not final AGX machine code. Every claim in this report that pf1 and
   pf1c "emit identical instructions" is a claim about the MSL and the AIR. Final
   register allocation and wait-counter placement could differ, and an
   `applegpu`-style disassembly or the Xcode shader profiler's register report
   would be the cheap way to check.

**One tension I am flagging rather than resolving,** because it is the advisor's
call and it affects anyone reasoning about command-buffer structure on the decode
path: standing rule 52 attributes the 45 CBs/step to the `asyncEval` stage points
"not the op/MB caps", but the default stage mask yields only 8 explicit
boundaries, and the observed decode command buffers reference 766-911 MB — far
above the 200 MB cap — so roughly 37 of the 45 must be byte-cap commits. Rule 52's
attribution looks at least partly wrong.

## 12. Follow-ups I did not implement

### 12.1 Seed-length x arm sweep — the experiment that resolves §11.5

Varying the **step count** is degenerate for this question: it moves
time-in-slot and mean KV length together, so a thermal or DVFS drift term and a
KV term are not separable. Vary the **seed** instead, holding step count fixed
at the scored 128, so every slot has identical duration and identical step
count while mean KV length moves by an order of magnitude.

| design | k range | sd(k) | lever vs #571 | slope CI half-width | resolution of a 0.021 slope |
|---|---|---|---|---|---|
| #571 as run (seed 512, 250 steps) | 513-761 | 71.9 | 1.00x | 0.0338 | 0.6 sigma |
| seeds {512, 1024} x 128 | 513-1151 | 258.6 | 3.60x | 0.0094 | 2.2 sigma |
| **seeds {128, 512, 1024, 2048} x 128** | 129-2175 | 721.5 | **10.0x** | **0.0034** | **6.2 sigma** |
| seeds {128, 512, 1024, 2048, 3072} x 128 | 129-3199 | 1073.4 | 14.9x | 0.0023 | 9.3 sigma |

Cost for the recommended row: 2 arms x 4 seeds = 8 cells, rotate palindrome
gives 16 slots per repetition, ~44.8 s per slot, so 9 repetitions is ~1.8 h —
one session, the same budget Phase A is spending now. The power comes from the
lever, not from more repetitions, which is why this is worth doing and why
adding repetitions to the current design is not.

The design is also **discriminating**, not merely powerful. The 1-full:3-sliding
schedule (`LagunaConfig.swift:539`) pins 30 of 40 layers' KV at 512 positions,
so total KV traffic and unbounded position index diverge past seed 512:

- cost tracks **total KV traffic** => visible knee at seed 512, slope falls to
  roughly a quarter beyond it;
- cost tracks the **unbounded position index** (i.e. the 10 full-attention
  layers) => straight line throughout;
- cost is a **fixed per-step constant** => slope zero, and §11.5's lean is noise.

Caveat to design in: changing the seed changes prefill work, so the prefill
phase of each slot changes length. The decode measurement is separate, but slot
duration is not constant across cells, so the rotation must be balanced over
seeds as well as arms.

### 12.2 Frequency and trace instrumentation — the cheapest mechanism separator

Ranks 1= in §11.7 are unseparated. Two additions would separate them for
approximately no GPU time:

- `powermetrics` GPU frequency and power sampled per slot, logged alongside the
  per-step dump. A DVFS mechanism predicts a measurable frequency or residency
  difference between `P0` and `P1`; a pure arbitration mechanism predicts none.
- one Instruments Metal System Trace per arm, which shows command-buffer and
  kernel overlap directly, and would reveal a serialisation that the `SPLIT=1`
  census destroys by construction (§11.4).

Neither is a timing run, so neither competes with the receipt budget. I did not
add them because instrumenting the slot loop during an open preregistered
window would have changed the measured configuration.

### 12.3 What I am explicitly not proposing

- No further `SPLIT=1` census as *evidence for location*. §11.4 explains why the
  instrument cannot answer the question; running it again would produce another
  regime-invalid number.
- No re-opening of rpg retiling (§7).
- No step-count sweep (§12.1's first paragraph).

### 12.4 Run the flip off `origin/main`, not off this branch (needs advisor authorisation)

This is the recommendation I most want acted on, and it is not mine to execute
because it requires changing my assignment's base.

The submitted artifact is `HEAD` intersected with the 97 `editablePaths`
(§6.4.1). My `HEAD` differs from `origin/main` on **27** of those files. Exactly
one, `Sources/MLXFastModel/LagunaRuntimeModel.swift`, is mine; the other 26 are
unpromoted advisor-branch content (vendored `Laguna.swift`, 15 `MLXLMCommon/*`
helpers, 11 `Vendor/mlx-swift` Metal and C++ sources). Three consequences
follow, and they compound:

1. **The absolute `cs` of my receipts is not frontier-comparable.** It prices my
   one-token flip *plus* 26 files of somebody else's unmeasured work. Only the
   difference between two of my own same-tree receipts is a valid measurement,
   which is why Phase B is a pair rather than a single draw.
2. **The pair costs twice as many receipts as it needs to.** If the flip were
   applied to a tree that is otherwise `origin/main`, the control arm would
   already exist: `origin/main`'s own snapshot has receipts on the board. One
   new receipt would then buy one paired difference instead of two receipts
   buying one difference.
3. **The candidate would be rankable.** A one-token, bit-exact flip on top of
   the promoted frontier is exactly the shape of a promotable submission. On
   this branch it cannot be promoted no matter what it measures, because the
   tree it sits in is not the frontier.

Concretely: branch from `1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7`, apply the
single `return 1` -> `return 0` at `LagunaRuntimeModel.swift:701`, and submit.
The cost is one receipt. I did not do it because it means abandoning the
assigned base, and §7's scope fence plus the assignment's branch contract put
that decision with the advisor.

The honest counter-argument: if `origin/main`'s existing receipts were drawn in
a different thermal session, using one of them as the control re-imports the
cross-session component of sigma that §4.1.1 measures at 0.34 % relative, and a
fresh same-session pair is cleaner. My answer is that §4.1.1 already shows one
pair is a sign check either way, so the cheaper draw dominates: spend the saved
receipt on a second pair instead of on a control that already exists.

## 13. Phase B execution log, and the submission-channel facts I had to discover

### 13.1 Three undocumented constraints on the official channel

`senpai/submit-official.sh` and `mlxfast submit` are documented in `AGENTS.md`
and in fb1 (§6.4.1). Three further constraints are enforced by the service and
are documented nowhere I could find; each one cost me an attempt, so I record
them for whoever submits next.

**(a) The submission note has a minimum length of 5,120 bytes.** My first
attempt carried a 1,299-byte note and was rejected outright with a demand for
"a complete, reproducible reasoning narrative: initial context and goal,
environment and setup, prior work or baseline, hypotheses, approach selection
and tradeoffs, implementation and files or logic changed, exact commands,
experiments, failures and course corrections, measured results, caveats,
learning, and next steps." This is a *content* requirement enforced by a
*length* floor, so a terse but complete note fails. The notes I ultimately used
are 9,312 B (T1) and 13,054 B (T0), organised under exactly those headings.

**(b) One submission may be in flight per account at a time.**

```
{"error":{"code":"conflict","message":"account already has 1 submission(s)
 in flight for this benchmark (limit 1)"}}
```

**(c) There is a shared per-account rate limit**, reported as
`Rate limit reached. Try again in <n> seconds.` with `n` observed between 759
and 973.

Both (b) and (c) are **account-wide and shared with every other campaign role**.
While I was submitting, another role was drawing receipts on a roughly 23-minute
cadence (`69fb349` at 03:42Z, `c793040` at 04:06Z, `d5f2b4c` at 04:29Z), so the
single in-flight slot was usually occupied. A paired design therefore cannot be
submitted back to back on demand: the two halves are separated by however long
the queue takes to drain, which is one more reason §4.1.1 treats a single pair
as a sign check rather than a measurement.

The consequence for automation is that a submission must be run under a retry
loop that (i) parses the rate-limit delay and waits it out, (ii) treats the
in-flight conflict as retryable, and (iii) confirms success **positively**,
never by an exit code. Getting (iii) right took me two tries, and both failures
are instructive:

- **False positive 1 — trusting the exit status.** The first wrapper reported
  `ACCEPTED` on an attempt that had actually been rate-limited. No submission
  existed. `senpai/submit-official.sh` `exec`s the CLI, and a throttled CLI call
  is not distinguishable from a successful one by exit code alone at that layer.
- **False positive 2 — trusting "the newest id changed".** The second wrapper
  recorded the newest id before attempting and declared success when the tail of
  `mlxfast submissions` changed. It duly reported `ACCEPTED: new submission
  288c702` — but `mlxfast submission-note 288c702` prints
  `# r105-A ladder receipt A2-1`. That receipt belongs to **another campaign
  role**. The submission account is shared, so "the newest id changed" is
  satisfied by *anyone's* submission and is an unsound predicate on this
  channel.

The only sound predicate I found is **content identification**: put a unique
marker string in the note, then after each attempt scan the recent ids from
`mlxfast submissions` and require `mlxfast submission-note <id>` to contain that
marker. My markers were `R105-B Phase B, arm T1` and `R105-B Phase B, arm T0`.
Scanning several recent ids rather than only the newest matters for the same
reason: another role's receipt can land between my submission and my check.

This also means the wrapper is idempotent and safe to re-run: it checks for the
marker *before* the first attempt and exits without submitting if the receipt
already exists. That property is worth more than it sounds, because a
half-confirmed submission is otherwise indistinguishable from a missing one, and
guessing wrong in either direction costs a scarce receipt.

**Also worth recording: do not pass `--model`.** `senpai/submit-official.sh`
lines 18-23 refuse any `--model` argument, because line 109 already execs
`mlxfast submit --model senpai "$@"`. The working invocation is

```bash
export PATH="${HOME}/.local/bin:${PATH}"
bash senpai/submit-official.sh 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7 \
     --note-file /tmp/r105b-note-t1.md
```

### 13.2 Ordering hazard the design has to respect

The wrapper archives the **`HEAD` worktree at the moment of invocation**,
restricted to the 97 `editablePaths`. Because my retry loop sleeps out the rate
limit inside the same process, the arm that is eventually uploaded is whatever
`HEAD` says when the *retry* fires, not when the job was launched. Applying the
T0 flip while the T1 job was sleeping would therefore have silently submitted
T0 twice and produced no control — a failure mode that leaves two receipts and
no contrast, and that no error message would reveal. The protocol I followed is
to hold the flip until the T1 receipt is *confirmed by marker*, and only then
apply it. Any future paired submission must serialise the same way, or snapshot
each arm into a private worktree before invoking the wrapper.

### 13.3 Phase B was not drawn, and the reason is measurable

Job `6e24bcdf-109a-4bd3-9d6d-275b9ad89d73` launched the T1 control submission at
05:07:49Z with a 4,200 s deadline and was terminated by that deadline at 06:17Z
(exit -15). It made **14 submit attempts and landed nothing.** The marker
`R105-B Phase B, arm T1` never appeared in any note, so by the §13.1 predicate
the receipt count for this experiment is **zero**.

Thirteen attempts returned
`{"code":"conflict","message":"account already has 1 submission(s) in flight for this benchmark (limit 1)"}`.
Attempt 8, at 05:28:20Z, returned `Rate limit reached. Try again in 1897 seconds.`

During the same 70 minutes the shared account landed three receipts, none of
them mine:

| id | opened | outcome | cs | commit |
|---|---|---|---|---|
| `288c702` | 05:00 | rejected | 2.55214102802847 | `b4c9b4e` |
| `d4a86ff` | 05:23 | rejected | 2.57182973424995 | `24ad1d2` |
| `0b9ae91` | 06:00 | validating at 06:16 | n/a | n/a |

**The diagnosis, which is the genuinely new finding here: the two channel
constraints compose adversarially, and a polling retry loop is anti-correlated
with success.** A failed *conflict* attempt still consumes per-account
rate-limit budget. So the loop spends its budget on attempts that were
guaranteed to fail, and the resulting lock-out lands on the moment the slot
frees. My own timeline shows exactly that: seven conflicts in the 21 minutes
from 05:07 to 05:25 bought a 1,897 s lock-out running 05:28→06:01, and
`d4a86ff` finished and `0b9ae91` claimed the slot at 06:00 — inside my
lock-out. The rate-limit windows I had recorded earlier were 759 s and 973 s;
1,897 s is 2-2.5× those, which is consistent with the penalty growing in the
number of recent attempts. I built the loop to be robust and it was precisely
the wrong shape.

The corrected design, which I am recording rather than shipping: **gate on
reads, not on submits.** `mlxfast submissions` is a read and does not appear to
consume the submit limiter. Poll *that* until no row reads `validating`, and
only then spend one `submit`. Every wasted submit becomes a free read, and the
process contends only when the slot is actually open. I have not exercised this
variant, so it is a recommendation and not a result, and §13.4 explains why I am
not spending receipts to test it.

One externality deserves stating plainly, because it is not visible from inside
my own experiment: the limiter is **per account**, and the account is shared
with the other campaign roles. My 14 attempts consumed shared budget and can
only have slowed the three roles that were submitting successfully around me.
That is a reason to prefer sparse, well-timed single attempts over loops even
when a loop would help me.

### 13.4 Why I stopped rather than pushing harder

> **[ERRATUM — rev2, written after the base relationship was resolved.]**
> Reason 2 below is **wrong** and I am retracting it. It asserts that HEAD's
> 27-file divergence from `origin/main` makes absolute `cs` "not
> frontier-comparable". I never checked the *direction* of that divergence.
> `origin/main` is `1bc1c895`, and `git merge-base --is-ancestor 1bc1c895
> 0954002c` succeeds: the promoted frontier is a **strict ancestor** of this
> assignment base. The 27 files are comment-stripping in `Vendor/` plus already
> merged 105-C/D/E work. The branch is therefore strictly *ahead* of the
> frontier, absolute `cs` **is** frontier-comparable, and a win here is
> promotion-eligible. The §12.4 "better experiment off `origin/main`" is not
> better; it is the same experiment run from further back. Reasons 1, 3 and 4
> stand as written and remain the honest account of the rev1 stop. rev2
> directed the draws to proceed on this base and §16 reports them.

Four reasons, heaviest first.

1. **The pair cannot settle what it was for, and I said so before drawing.**
   §4.1.1 put σ_pair at 31.9 µs/step from 14 consecutive receipts, so a single
   pair gives ±44 µs against an expected +28 µs, i.e. P(correct sign) ≈ 81 %.
   Two contested receipts buy an underpowered sign check. That was accepted on
   the record before any receipt was requested, so declining to draw it now is
   consistency rather than retreat.
2. **This is the known-inferior design.** §12.4 shows HEAD differs from
   `origin/main` on 27 editable files, 26 of them unpromoted advisor content.
   Off this base the pair costs two receipts *and* yields an absolute `cs` that
   is not frontier-comparable. The better experiment is one receipt: apply the
   one-token flip on top of `origin/main`, where existing `origin/main` receipts
   already serve as the control. Spending two contested receipts to run the
   worse version of an experiment whose better version I have already specified
   is not defensible.
3. **A lone control is worth almost nothing.** Had only T1 landed I would hold
   one receipt on a tree comparable to nothing. This axis is all-or-nothing;
   partial progress does not exist on it.
4. **Continuing costs teammates.** See the externality in §13.3.

What the advisor is therefore being asked to decide is whether to authorise the
§12.4 single-receipt design off `origin/main`. That is a base change plus a
receipt-budget call, so it is not mine to make. The direction matters for that
decision: **P0 is faster than the shipped P1** by +28.00 µs/step = +0.426 % of
composite score, and the flip is bit-exact (144/144 slots, one token digest).
The open question is not academic — it is whether a possibly promotable,
one-token, bit-exact win transfers to M5.

What is *not* blocked is every Phase-A deliverable. A0 and A1 both carry
verdicts under their preregistered rules, the correctness result is the
strongest single outcome of the round, and the four dispositions in §9-§10 (the
free-rider retraction, the Rule 82 qualification, and my own two retractions)
rest on M4 and static evidence that cost no receipts at all.

## 14. Characterisation of the submission limiter (campaign asset)

The advisor asked for this as a standalone section rather than as an excuse
folded into a results narrative, and that is the right call: the limiter is a
shared resource whose behaviour every future maple student will hit, and the
cost of rediscovering it is measured in wasted receipts. What follows is what I
established, how I established it, and what I got wrong on the way.

### 14.1 The mechanism, in one paragraph

`mlxfast submit` runs against a **single API account shared by the whole
campaign**. The account permits **one submission in flight at a time** and
enforces an **account-wide rate limit** on top of that. A submission occupies
the channel from acceptance until its M5 run finishes and its verdict is
published — observed at **20-37 minutes**, median 23. Any attempt made while a
row is `validating` returns a `conflict` error, and — this is the expensive
part — **a conflict attempt still consumes rate-limit budget**. The rate-limit
refusal states its own wait, observed between 759 and 1897 seconds.

### 14.2 What that implies operationally

Four rules follow, and I violated three of them before I derived them.

1. **Never retry on conflict.** A retry loop converts one blocked attempt into
   a rate-limit lockout that blocks the attempt that would have succeeded. The
   correct pattern is read-only polling of `mlxfast submissions` and exactly
   one wrapper invocation once no `validating`/`queued` row is observed.
2. **Never confirm by exit code.** The wrapper's exit status reflects the
   local archive-and-POST, not whether *your* receipt is the one now in the
   channel.
3. **Never confirm by "the newest id changed".** On a shared account the
   newest id changes constantly. I twice believed a receipt was mine when it
   was not; `288c702` turned out to be r105-A's ladder receipt A2-1. The only
   sound confirmation is a **unique marker string embedded in the note body**,
   retrieved with `mlxfast submission-note <id>`. Both my drawer script and
   both Phase B notes are built around that marker.
4. **Never mutate `HEAD` while a submit job can fire.** The wrapper archives
   the *worktree at invocation time* restricted to `editablePaths`. If a
   background drawer fires while you are staging the next arm, it submits a
   tree that corresponds to no commit you can name. Serialise the arms, or
   snapshot each arm into a private worktree first. This is why the P1 control
   commit in this round was not created until P0 had confirmed.

### 14.3 Who is actually contending, and the correction I owe

My first pass at this concluded that the contending traffic was **other Senpai
campaigns** sharing the account. The evidence looked strong: `mlxfast
submissions --all` returns 1,216 sha-bearing rows, only 60 of which are commits
that exist in this repository, and none of the recent ~22-minute-cadence
receipts resolved locally.

**That conclusion was wrong, and I am retracting it.** The inference "the SHA
does not exist in my checkout, therefore the receipt is not ours" is invalid,
because sibling students submit from branches I have never fetched. Resolving
the notes by marker instead of by SHA settles it immediately:

| receipt | time (8/10) | owner |
|---|---|---|
| `d5f2b4c` | 04:29 | r104-A stage 2, leg 01/08 |
| `288c702` | 05:00 | r105-A ladder receipt A2-1 |
| `d4a86ff` | 05:23 | r105-A ladder receipt A0-3 |
| `0b9ae91` | 06:00 | r105-A ladder receipt A1-1 |
| `a8a8040` | 06:20 | r104-A stage 2, leg 02/08 |
| `c52994d` | 06:42 | r105-A ladder receipt A1-2 |
| `795badf` | 07:04 | r104-A stage 2, leg 03/08 |
| `8a09a94` | 07:27 | r104-A stage 2, leg 04/08 |

Every one of the eight is a **maple sibling arm**. The channel is saturated by
exactly two studies: r104-A's eight-leg sliding-attention k-loop unroll ladder
and r105-A's prefetch ladder. Interarrival times were 24, 23, 31, 23, 37, 20,
22, 22, 23 minutes — mean 25, median 23, and essentially back-to-back, meaning
utilisation is at capacity rather than merely high.

The general lesson is worth more than the specific correction: **absence from
the local object database is not evidence of foreign origin**, and I should
have reached for the note bodies — which I already knew how to read — before
publishing an attribution.

### 14.4 The consequence the advisor should weigh

The instruction that "the channel is yours" for this round cannot be enforced
from inside my process, and it was not true in fact: at the time I was told it,
r104-A had four of eight legs still to draw and r105-A was mid-ladder. With a
median 23-minute occupancy and two arms queueing, my expected wait per receipt
is not 23 minutes but 23 minutes times the number of competitors who poll the
same gap, and the race is won by whoever polls with the shortest period. That
is a bad equilibrium: it rewards aggressive polling, which is exactly the
behaviour rule 1 above tells everyone not to exhibit.

This is a scheduling problem, not a research problem, and it has a cheap
scheduling fix. My recommendation is that the campaign adopt an explicit
**receipt-token allocation** — an ordered queue published in one place, with
each arm told its slot — rather than letting parallel arms discover the
contention by colliding. Failing that, a convention that each drawer polls on a
randomised interval with a published mean would at least remove the incentive
to poll fastest. I have not implemented either; both are campaign-level
decisions.

## 15. The two verdicts rev2 asked for, explicitly

rev2 required a plain verdict on two standing claims rather than a discussion
that leaves the reader to infer one. Both are given below in the form
*uphold / qualify / retract*, with the evidence that decides them and the
caveats that limit them.

### 15.0 New static evidence: live ranges across the barrier

Phase A established **V-PLACEMENT** — the prefetch salvo's cost is where the
loads sit relative to the threadgroup barrier, not the loads themselves — but
the *mechanism* behind that was hypothesis, not measurement. §10 offered
register pressure as the likely carrier and said plainly that it was unproven.
I can now do better without spending GPU time, because the mechanism has a
static signature.

The `.air.ll` dumps in `research/msl/` already told us the loads are identical:

| variant | AIR lines | barriers | loads |
|---|---|---|---|
| `pf0` (no salvo) | 369 | 5 | 10 |
| `pf1` (salvo hoisted **above** barrier) | 438 | 5 | 13 |
| `pf1c` (same salvo issued **below** barrier) | 426 | 5 | 13 |

`pf1` and `pf1c` issue the *same 13 loads*. Anything that separates them is
placement by construction. `research/maple-frieren-r105b-liverange.py` counts,
for each threadgroup barrier, the SSA values defined before it and still used
after it — the direct static proxy for the live ranges a hoist stretches across
the barrier:

| variant | SSA defs | live-across-barrier, per barrier | max |
|---|---|---|---|
| `pf0` | 136 | 8, 8, 7, 8 | 8 |
| `pf1` | 178 | 11, 11, 10, 11 | **11** |
| `pf1c` | 172 | 9, 9, 8, 9 | 9 |

Deltas against `pf0`: `pf1` **+3 at every barrier** (+12 total); `pf1c` **+1 at
every barrier** (+4 total). The placement-only contrast `pf1 − pf1c` is
**+2 at every one of the four barriers, +8 total**.

This is the first evidence in the round that is both mechanistic and free. It
matters because the ordering it produces is the *same* ordering the M4 timing
produced, on an axis the timing never saw:

| variant | live-across-barrier (static) | Phase A timing |
|---|---|---|
| `pf0` = P0 | 8 (lowest) | fastest |
| `pf1c` ≈ P5 | 9 | `P0 → P5` CI covers zero |
| `pf1` = P1 | 11 (highest) | **+28.00 µs/step slower than P0** |

Two independent measurements, one static and one dynamic, rank the three
variants identically, and the variant that is *only* a placement change carries
the whole gap. I state the limits precisely: this is a monotone agreement, not
a calibration. +3/barrier costs 28 µs while +1/barrier costs an amount whose
interval covers zero, which is not linear, and I have no occupancy counter to
confirm that the extra live values actually force a spill or an occupancy step
rather than merely widening a live range the allocator absorbs. So the claim I
am willing to sign is the weaker one: **the placement effect has a static
signature that tracks it, and register live-range extension across the barrier
is now a supported mechanism rather than a bare hypothesis.**

### 15.1 Verdict on `research/CURRENT_RESEARCH_STATE.md:193-200`

**UPHOLD the arithmetic and the headline; QUALIFY one clause.**

Upheld without reservation: the step traffic of 1,671,402,432 B, the 2740.00 µs
DRAM floor against Rule 80's 610 GB/s, the 66.16 % share of the 4141.5 µs
ranked step, and the conclusion that **decode is memory-bound at the same knee
as prefill**. Nothing in this round touches those numbers, and my results are
consistent with them: a zero-byte change cannot move the roofline, and it did
not.

The clause I qualify is *"The 1401.50 µs remainder is a **subtraction residual,
not a pool**."* As a warning against *budgeting* the residual — treating
1401.50 µs as a fund that optimisations may draw down — it is correct and
should stay. But it is being read more strongly than that, as though the
residual were inert and work inside it not worth attacking. This round
falsifies the strong reading. The prefetch salvo moves **zero bytes**: `pf1`
and `pf1c` issue byte-identical loads, DRAM traffic is unchanged, and the
roofline term is untouched. It nonetheless moves **28.00 µs/step**, which is
**2.0 % of the 1401.50 µs residual** and **+0.426 % of composite score** — a
figure that would rank, from a change of *where four loads sit*.

So the residual is not inert. It is not a pool you may budget against, and it
is also not a region where placement-sensitive work should be dismissed
a priori. My proposed amendment is one sentence appended to the clause:

> *The residual is a subtraction residual and may not be budgeted as a pool;
> but it is not inert — zero-byte placement effects inside it have been
> measured at 2.0 % of its size, so a change that moves no bytes may still be
> worth ranking-scale time.*

Caveat: 28.00 µs/step is M4 Pro. The M5 transfer is exactly what §16's receipts
were drawn to test, and until they resolve, the *magnitude* is directional even
though the existence of a zero-byte placement effect is established.

### 15.2 Verdict on Rule 82

Rule 82 has an empirical half and a procedural half, and they do not share a
fate.

**RETRACT the empirical half.** Rule 82's factual base is a per-kernel label
measurement: the router GEMV prefetch showed **−6.39 µs/step**, i.e. hoisting
the salvo *won*. That is now falsified end to end, twice and in the same
direction. #571 measured **+34.58 µs/step** against the hoisted arm; this round
measured **+28.00 µs/step [+22.23, +33.77]**, 16 of 16 slots positive. The two
intervals overlap each other and exclude the labelled win. A label that reports
a −6.39 µs gain on a change that costs +28 µs end to end is not noisy, it is
measuring the wrong thing: it sees the loads retire earlier and does not see
the live ranges the hoist stretched across the barrier (§15.0). The rule's
number should be struck rather than widened.

**UPHOLD the procedural half, and promote its corollaries.** Rule 82's
requirement that a codegen arm begin with a static compile read is vindicated —
it is precisely the static read that produced §15.0 and, at zero GPU cost,
supplied the mechanism the timing could not. §9.2's refinement stands and
should be promoted from a qualification buried in this document to freestanding
rules:

- **82a** — *the static read is a **veto**, not an authorisation.* An unchanged
  static profile does not license a hoist; it only fails to forbid one.
  `pf0`/`pf1`/`pf1c` are indistinguishable on the occupancy read that Rule 82
  actually consults, and they differ by 28 µs/step.
- **82b** — *a per-kernel label is not an end-to-end result.* Where the two
  disagree, the end-to-end paired measurement wins, and the label's disagreement
  is a fact about the label.

#540's sliding-attention prohibition is untouched by all of this and stands.

**REPLACE the mechanism** with what the evidence now supports. Proposed:

> **Rule 82′.** The cost of a prefetch is carried by its **placement**, not by
> its loads. Hoisting a load above a threadgroup barrier is charged end to end
> even when the per-kernel label shows a win and static occupancy is unchanged,
> because the hoist extends register live ranges across the barrier. Measured
> M4 Pro: identical 13-load salvos differing only in barrier side rank
> identically by static live-across-barrier count (+2/barrier for the hoisted
> form) and by end-to-end time (+28.00 µs/step, 16/16 slots).

Caveats I attach to 82′ and will not paper over. (i) All timing evidence is
**M4 Pro**; the M5 receipts in §16 are the transfer test, and per `AGENTS.md`
threadgroup-geometry effects can change sign across core counts. (ii) The
live-range mechanism is **supported by a static proxy, not by an occupancy or
spill counter** — the agreement in §15.0 is monotone, not calibrated. (iii) The
rule is stated for threadgroup barriers in this kernel family and should not be
generalised to other barrier types without a fresh read.

## 16. rev2 Phase B — the receipts

### 16.1 What is being measured, and on which statistic

Two arms, one editable byte apart, both on assignment base `0954002c`:

- **P0** — `DARKBLOOM_ROUTER_WEIGHT_PREFETCH` compiled-in default flipped
  `1 → 0`, i.e. the salvo is gone. Commit `ea0e4da`.
- **P1** — the shipped default `1` restored, plus an arm-identifying comment
  block inside the same editable file so the two arms are distinct commits with
  the distinguishing byte on the **submitted** surface. Commit `9214e6b`.

The contrast is read on **`T = D − 4P`**, not on `officialScore`. `T` is the
true steady-state per-step time and follows exactly from two published fields
by the rule-58 identity `D = 4P + T`; `officialScore` additionally carries the
paired baseline of whichever session the receipt happened to land in. I report
`L = officialScore / cs` alongside precisely so that session drift is visible
rather than silently folded into the contrast. If `L` moves materially between
the two draws, the score-level difference is contaminated and only the
`T`-level difference is interpretable.

### 16.2 The power of this pair, stated before it lands

This must be said plainly, because it is the honest limit of the round.
`σ_pair(T) = 17.08 µs/step` from the 14-receipt consecutive-draw corpus, so
**one pair carries a 95 % interval of ±33.5 µs/step** and two pairs ±23.7.
The M4 effect is +28.00 µs/step; the M4→M5 attenuation observed elsewhere in
this campaign is ×0.436, so the *expected* M5 effect is ≈ −12.2 µs/step on
`ΔT = T(P0) − T(P1)`.

An expected −12.2 against a ±33.5 interval is **a sign check with roughly 76 %
power, not a resolution**. Two pairs would take that to ≈84 %. Neither
resolves the transfer coefficient, and no number of receipts inside a
4-receipt ceiling would. I preregistered this in §4.1.1 before drawing and
restate it here so that no reader mistakes a one-pair result for a measurement
of the transfer.

### 16.3 Pair-2 decision rule (preregistered before P1 resolved)

A preregistration that lives only in a file I control is worth very little, so
this one is **embedded in the P1 submission note itself** and therefore carries
the official channel's own server-side timestamp. It was written while
`6fc8abf` (P0) was still `validating` with no published metrics and before P1
had fired, so it is verifiable from the outside — `mlxfast submission-note`
on the P1 receipt shows the rule and the receipt shows when it was accepted —
rather than resting on my assertion about when I typed it.

(It is deliberately *not* committed before the draw. Committing would move
`HEAD` under a live drawer job, and §14.2 rule 4 says not to do that: the
wrapper archives the worktree at fire time, so the receipt would then record a
commit sha that is not the arm I named. The note body is the honest place for
a timestamp anyway.)

Sign convention: M4 says the hoisted arm is slower, i.e. the prediction is
**ΔT < 0**.

| observed `ΔT = T(P0) − T(P1)` | reading | action |
|---|---|---|
| `ΔT ≤ −17.08` (≥1σ, predicted sign) | M4 finding transfers with margin | **stop at 2 receipts**, V-BANKED |
| `−17.08 < ΔT < +17.08` | inside 1σ of zero; ambiguous | **draw pair 2** if the channel permits — this is the only region where doubling *n* changes the verdict |
| `ΔT ≥ +17.08` (≥1σ, reversed) | contradicts 16/16 M4 slots | **draw pair 2** — a reversal is a first-class transfer-menu finding and must not rest on one contested receipt |

The ceiling stays at 4 receipts either way. If pair 2 is indicated but the
channel is saturated by sibling arms, the documented limiter block (§14)
applies and the round terminates at 2 with the ambiguity reported as the
result, not papered over.

### 16.4 Results

*(filled from `research/maple-frieren-r105b-phaseb-receipts.py`, which resolves
each arm by its unique note marker rather than by id ordering, since the
account is shared and the newest id is usually a sibling's.)*

---

*(Nothing in §§0-5 is edited after the first Phase-A launch except to fix a
typo or to carry an explicitly marked `[ERRATUM]`, and every such edit is called
out in the commit message and restated in §11. §6 was written before launch from
zero-GPU-cost evidence and says so. §9 verdicts 9.1/9.2 are argued from evidence
already in hand and are marked where they depend on A0. §§11-12 were written
during the open Phase-A window from the surviving #571 data and from source
reads only, and touched no file under `Sources/` or `Vendor/`.)*
