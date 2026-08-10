# R108-L — Adjacent-pair dispatch ledger for the decode step

**Student** maple-tanjiro · **PR** #663 · **assignment** `maple-r108-l-adjacent-pair-dispatch-ledger` ·
**revision** `r108-l-rev1` · **base** `705484b9e120d60a973d660fdbdd1ccc7cdfa124`
**Class** desk exercise — zero receipts, zero scored-surface edits, source reads only.
**Written** 2026-08-10, ledger due 18:00Z.

---

## 0. Terminal verdict — `N-NO-MERGEABLE-PAIR`

Not for the reason the assignment anticipated. **Three adjacent pairs are
structurally clean** — `dep_scope = NONE`, `n_removed ≈ 40`, `byte_delta`
negative, and `r105_15_class = IDENTICAL` reachable by a tile-range branch. The
refusal is a **pricing** refusal, not a structural one:

> The assignment's "conservative floor" of **k = 1.0** is **11.5× above the only
> directly measured removal-direction price in our own record.** PR #483 (fern)
> measured the exact elasticity on the exact cheapest-dispatch family:
> **+80 dispatches/step cost +8.61 µs/step, CI [−17.71, +35.02] ⇒ 0.108
> µs/dispatch, CI [−0.221, +0.438]** — a confidence interval that **spans zero**
> (`research/maple-fern-r91-input-norm-fusion-price.md:14-24,36`, quoted at
> `CURRENT_RESEARCH_STATE.md:222-226`).

At the measured price, `k_measured = 0.108 / 1.2382 = 0.0872`, and:

| pool | n_removed | @ k=1.0 (assignment floor) | @ **k=0.0872 (measured)** | vs 0.4 % bar |
|---|---|---|---|---|
| best single pair | 40 | 0.753 % | **0.0658 %** | 6.1× below |
| best 2 independent pairs | 79 | 1.487 % | **0.1299 %** | 3.1× below |
| **every removable dispatch in the step** | **158** | 2.973 % | **0.2599 %** | **1.5× below** |

**Removing every dispatch that is removable at all does not clear the bar.**
This is not a new result; it is the fourth independent arrival at the same place
(#483 `0.108 µs/dispatch`, #158 `null −0.12 ± 0.22 µs`, #218 router family
`0.00 ± 0.12 µs/call`, 105-D §4 `≥68.4 % overlapped, first ~480 added dispatches
free, production is 408`). Rule 68 already forbids applying rule 65's addition
price in the removal direction; a prior violation overstated by **21.7×**
(`CURRENT_RESEARCH_STATE.md:219-226`).

**The ledger is still worth its cost, and §13 is why.** Its `dep_scope` column
turns out to decide not just fusion legality but whether the boundary's cost
*exists at all*. MLX creates every compute encoder with
`MTL::DispatchTypeConcurrent` and emits a barrier only on a real buffer-aliasing
hazard (`backend/metal/device.cpp:545-548`, `:315-349`, `:363-391`). Hence the
central symmetry: **the per-dispatch intercept is collectible only at dependent
boundaries, which are exactly the ones fusion cannot cross; and the `NONE`
boundaries fusion can cross emit no barrier today, so there is nothing there to
relieve.**

**Do not build a merged kernel, and do not build a concurrent encoder either.**
My own §9 estimate of ≈1.83 % for the latter is **retracted in §13.4**: the
encoder is already concurrent, and `device.cpp` is not in `editablePaths`. Both
halves of this axis price at ≈0.1 %, matching every removal-direction receipt
(#48: −0.1488 %; #483: 0.108 M4 µs, CI [−0.221, +0.438]).

---

## 1. Scope, host, epoch, and tagging convention

Per rule 105.8 every quantity below carries three tags.

| tag | meaning |
|---|---|
| **[M4]** | measured on my host: AWS **M4 Pro**, `applegpu_g16s`, Apple GPU gen **16**, 20 GPU cores, 48 GiB, macOS 26.5.2. Raw µs. |
| **[M5]** | ranked-machine quantity, receipt-derived. |
| **[census]** | steady-state per-step accounting of the unmodified base (R107-G census, this base's parent lineage). |
| **[marginal]** | a differential price measured by perturbing the base. |
| **[conjecture]** | model output or belief with no receipt behind it. |
| **INFERRED** | derived from source reading and arithmetic, **not measured in this assignment.** |

**Every row of the ledger in §5 is INFERRED.** This assignment ran zero
benchmark receipts by design. The only measured inputs are cited constants from
prior rounds, each tagged at its point of use.

Epoch: all census quantities are from my **R107-G** census
(`research/maple-tanjiro-r107g-decode-family-regime-census.md`, artifacts under
`research/artifacts/maple-tanjiro-r107g/`, W&B run `jhuxsg3h`), taken on the
`705484b9` lineage. Constants from other students are tagged with their PR.

---

## 2. Topology correction: the step has ~404 dispatches, not 319

The assignment says "the decode step's 319 dispatches". **319 is my own census
number and it is the count of dispatches my census *timed*, not the count the
step *issues*.** A full source-level walk of the decode path finds:

| block | dispatches/step | in R107-G census? |
|---|---|---|
| embedding + RoPE atlas (`LRM:11412`) | 1 | ✗ |
| **standalone input RMSNorm** (`LRM:5949`, `fusedQKV ?? inputNorm`) | **40** | ✗ |
| QKV NVFP4 GEMV (`LRM:5027`) | 40 | ✓ T0b(a)/(b) |
| gate softplus (`LRM:4539`) | 40 | ✓ T2b/T2b′ |
| fused attention, sliding 30 + full 10 (`LRM:1964`/`:2450`) | 40 | ✓ T3a/T3a′ |
| activated O-proj (`LRM:4620`) | 40 | ✓ T3b/T3c |
| residual+RMS+router, layers 1-39 (`LRM:1225`) | 39 | ✓ T1a |
| layer-0 residual+RMS (`LRM:1236`) | 1 | ✗ |
| **router top-8 tournament** (`LRM:10180`) | **39** | ✗ |
| routed SwiGLU gate+up (`LRM:8045`) | 39 | ✓ T2c |
| shared SwiGLU gate+up (`LRM:7221`) | 39 | ✓ T2a |
| routed+shared down+residual (`LRM:8636`) | 39 | ✓ T2d |
| layer-0 dense gate+up, dense down+residual | 2 | ✓ |
| final RMSNorm (`LRM:11775`) | 1 | ✗ |
| lm-head chain: base-coarse, argmax stage-1, exact-winner, refined-exact (`LagunaLmHeadPrune.swift:941,957,964,973`) | **4** | ✓ as **1** |
| **total** | **404** | 319 censused |

`createAttentionMask` returns `nil` at `L=1` (`LRM:11666-11668`) — no dispatch.
The `qkv → queries/keys/values` slices (`LRM:6022-6027`) are strided views; I did
**not** confirm no contiguity copy is forced (UNKNOWN, low risk).

**404 corroborates 105-D §4's independently reported "production is 408"**
(`CURRENT_RESEARCH_STATE.md:271`) to within 1 %. That is a useful cross-check
of both walks, and it matters: 105-D's free-absorption region extends to ~480
added dispatches, so the production step sits **inside** the region where added
dispatches are free — which is the same statement as #483's 0.108 µs.

The 85 uncensused dispatches are the **cheapest** in the step: an input RMSNorm
moves 12,288 B, a router tournament ~2 KB. My R107-G one-parameter model
(`dispatch_us = unique_bytes / 266.3 GB/s + 3.97 µs`, R² = 0.9810 [M4, census])
predicts **4.02 µs** for the input RMSNorm; the independently recorded
measurement is **3.46 µs/call** [M4] (`RESEARCH_IDEAS_2026-08-09_13:45.md:121`).
A 14 % error on a family the model was never fitted to is a genuine
out-of-sample validation of the byte model, and it is *why* these 85 dispatches
are worthless to remove: they are all pinned at the ~3.97 µs overhead floor,
which 105-D §4 shows is ≥68.4 % overlapped.

---

## 3. Pricing constants, and two arithmetic problems with the EV formula

### 3.1 Constants

| constant | value | tags | source |
|---|---|---|---|
| `P` — score price of step time | **0.015228 % of `cs` per µs/step** | [M5, marginal] | receipt `59bd72a3`, `cand_dec = 4925.255 µs`, w = 0.75; `6580.8 = cand_dec/0.75` so `µs/6580.8` already carries the decode weight |
| rule 65 — **added** dispatch | **+2.3403 µs**, CI [2.2766, 2.4040] | [M5, marginal, **ADDITION-ONLY**] | rule 65 |
| #497 saturated per-dispatch | 1.2382 µs | [M4, marginal, addition] | `CURRENT_RESEARCH_STATE.md:3245` |
| `k_dispatch` transfer | 2.3403 / 1.2382 = **1.890** | [derived] | research state 6975-6976 |
| **#483 — removed/added dispatch, measured on the input-norm family** | **0.108 µs**, CI **[−0.221, +0.438]** | **[M4, marginal, both directions]** | `maple-fern-r91-input-norm-fusion-price.md:14-24,36` |
| `k_measured` | 0.108 / 1.2382 = **0.0872** | [derived] | — |
| byte price | 0.4 % per **15.10 MiB/step** ⇒ 0.026490 %/MiB ⇒ **2.5272e-8 %/B** | [M4-census bytes → M5 %cs] | R107-G; consistent with ~600 GB/s M5 effective (15.10 MiB / 600 GB/s = 26.5 µs × `P` = 0.404 %) |
| frieren barrier-drain | **0.799–0.915 % per ~39.5-boundary family** ⇒ 0.02023–0.02316 %/boundary | [M5, **conjecture**] | matches `RESEARCH_IDEAS…13:45.md:123` "≈91 µs … 60–91 µs" × `P` |
| rule 41 — serialisation share of a 4 KiB boundary | **76.3 %** (vs `c_fixed` 22.4 %, bytes 1.3 %) | [M5, marginal] | `CURRENT_RESEARCH_STATE.md:571-573` |
| bar | **0.4 %** (advisor) / 0.5 % = 32.8 µs/step (fern's ranked ledger) | — | — |

Per-dispatch score gain, `p(k) = 0.03556 % × k / 1.890`:

| k | `p(k)` | provenance of `k` |
|---|---|---|
| **0.0872** | **0.0016446 %** | **measured (#483)** |
| 1.0 | 0.018815 % | assignment "conservative floor" — **no measurement supports it** |
| 1.395 | 0.026248 % | assignment midpoint |
| 1.890 | 0.035560 % | full rule-65 addition price applied in reverse — **forbidden by rule 68** |

Sanity check against the advisor's own arithmetic: at n = 30 this yields 0.565 %
(k=1.0), 0.787 % (k=1.395), 1.067 % (k=1.890), reproducing the advisor's
0.565/1.069 exactly. The advisor's quoted **0.803 %** at k=1.395 does not
reproduce; **0.787 %** does. Minor, but flagged.

### 3.2 Problem 1 — `dispatch_gain_pct + drain_gain_pct` double-counts

The EV formula sums a dispatch term and a drain term. **They are the same money.**
Rule 65's 2.3403 µs was priced with *dependent* addition probes — "the receipts
that priced it added *dependent* dataflow (e.g. the +40 softmax-partial
dispatches, rule 67 corollary), **so launch and drain are confounded**"
(`RESEARCH_IDEAS_2026-08-09_13:45.md:52`). H_B is not an *additional* component
on top of rule 65; it is the *hypothesised decomposition of* rule 65. Summing
them would count the drain once inside `dispatch_gain_pct` and again in
`drain_gain_pct`.

Consistency check: frieren's per-boundary drain (0.0202–0.0232 %) and rule 65's
per-dispatch price at k=1.0 (0.0188 %) are the **same number to 10 %** — as they
must be, if one is a decomposition of the other.

I therefore report `drain_gain_pct` in the ledger as the assignment requires, but
**exclude it from the headline EV** and give the literal sum only as a labelled
upper envelope.

### 3.3 Problem 2 — the direction is measured, and it is not symmetric

`dispatch_gain_pct` at any k ≥ 1 assumes removal refunds what addition costs.
Three results in our record say it does not:

1. **#483**, on the exact family: 0.108 µs/dispatch, CI spanning zero, family
   declared "terminal — the family is dead".
2. **#48**: an 8× threadgroup collapse that *reduced* dispatch count scored
   **−0.1488 %** (receipt `285f79fa`). Removing boundaries made the score worse.
   The surviving law is fern's §0.9.16: **a boundary costs what it SERIALISES,
   not what it drains and not what it launches.**
3. **105-D §4**: ≥68.4 % overlapped; production's 408 dispatches sit inside a
   free-absorption region extending to ~480.

alphonse is measuring the removal-symmetry ratio (due 20:00Z). **That ratio is
the gate on every row of §5.** My prior, from the above, is that it lands at
`k ≤ 0.2`, and #483's CI already includes zero.

---

## 4. `dep_scope` taxonomy — and why it alone predicts the sign of `byte_delta`

Four categories, ranked as the assignment directs (`NONE` above `TG-LOCAL` above
the rest), plus one sub-class I had to add:

| `dep_scope` | definition | fusion mechanism | `byte_delta` sign |
|---|---|---|---|
| **NONE** | no array crosses; the two dispatches share only an *input* | tile-range branch, no recompute | **DOWN** (shared input read once) |
| **TG-LOCAL** | crossing element produced by the same threadgroup that consumes it | epilogue absorption | **DOWN** (intermediate never round-trips) |
| **REDUCTION-RECOMPUTABLE** *(new sub-class)* | crossing is a reduction **over an array the consumer already reads in full** | consumer recomputes the reduction from data already in registers | **DOWN** |
| **REDUCTION** | consumer needs the producer's whole array reduced, and does not already read it | atomics or a second pass | ~0, or blocked |
| **GRID-WIDE** | each consumer threadgroup reads a broad/whole slice of the producer output | recompute per consumer TG | **UP by ≥ the consumer's TG count** |

**The byte-sign law.** For a GRID-WIDE crossing, fusion by recompute multiplies
the *producer's weight traffic* by the consumer's threadgroup count. Every
GRID-WIDE pair in this step has a consumer TG count ≥ 32, so `byte_delta` is
always UP by ≥32×, which is fatal at 2.5272e-8 %/B. For NONE and TG-LOCAL pairs
no recompute is needed at all, so `byte_delta` is always mildly negative.

This makes the assignment's category ranking a **theorem rather than a
heuristic**, and it is the same one-parameter structure I found in R107-G: once
you know `dep_scope`, the byte column carries no extra information.

**REDUCTION-RECOMPUTABLE is why I had to add a category beyond the assignment's
four.** The (input-RMSNorm → QKV) pair looks GRID-WIDE+REDUCTION — every one of
the QKV output rows needs the full normalised 2048-vector — but each QKV
threadgroup *already reads all 2048 inputs* for its GEMV, so it can compute the
RMS from data it has already loaded. Zero recompute, bytes down. The
affine-8 kernel family already implements exactly this
(`lagunaNormAffineQKVBody(… normalize:)`, `LRM:5097`).

---

## 5. The ranked ledger

`n_removed` = dispatches removed **per decode step**. `intermediate_bytes` =
per-step traffic of the crossing array that fusion eliminates (write + read).
`byte_delta` = per-step change in unique bytes; negative is a saving.
`EV` = `dispatch_gain_pct − byte_penalty`, **excluding the double-counted drain
term** (§3.2). All rows **INFERRED**.

### 5.1 Headline — at the measured price `k = 0.0872`

| # | pair (producer → consumer) | n_removed | dep_scope | intermediate_bytes | byte_delta | **EV @ k=0.0872 (measured)** | `r105_15_class` | collision |
|---|---|---|---|---|---|---|---|---|
| **1** | routed gate+up `LRM:8045` → shared gate+up `LRM:7221` | **39** | **NONE** | 0 | **−159,744** | **+0.0682 %** | **IDENTICAL** (tile branch) | **none known** |
| **2** | QKV `LRM:5027` → gate_sp `LRM:4539` | **40** | **NONE** | 0 | **−163,840** | **+0.0699 %** | **IDENTICAL** (tile branch) / REASSOCIATED (row-fold) | `99b974c1` re-measured the norm+QKV+gate fusion at **+2.7 %** (worse); its defusion is the promoted state |
| **3** | input RMSNorm `LRM:5949` → QKV `LRM:5027` | **40** | **REDUCTION-RECOMPUTABLE** | 327,680 | **−327,680** | **+0.0741 %** | **REASSOCIATED** | **#483 CLOSED, ≤0.533 %, ≈0.13 % after transfer**; PR #483 fused this exact pair |
| **4** | gate_sp `LRM:4539` → fused attention `LRM:1964`/`:2450` | **40** | **NONE** | 0 | 0 | **+0.0658 %** | IDENTICAL (INFERRED; TG 64→1024) | **active PR #642** owns the attention kernels |
| 5 | O-proj `LRM:4620` → residual+RMS+router `LRM:1225` | 40 nominal / **0 effective** | TG-LOCAL | 327,680 | −327,680 | **0** | IDENTICAL for the residual add only | — |
| 6 | down+residual `LRM:8636` → next input RMSNorm | 40 nominal / **0 effective** | GRID-WIDE + REDUCTION | 327,680 | −327,680 | **0** | — | Arm C producer-side folding |
| 7 | residual+RMS+router `LRM:1225` → router top-8 `LRM:10180` | 39 | REDUCTION | 119,808 | −119,808 | +0.0672 %, **blocked** | **REORDERED** (tie-break) | **#218 bounds family at 0.00 ± 0.12 µs/call; #204 deleted it for −0.9 ± 12.1 µs**; #483 built a router mega-kernel, closed |
| 8 | router top-8 `LRM:10180` → routed gate+up `LRM:8045` | 39 | REDUCTION-carried | 4,992 | −4,992 | +0.0642 %, **blocked** | — | as row 7 |
| 9 | dense gate+up → dense down+residual (layer 0) | 1 | GRID-WIDE | 32,768 | −32,768 | +0.0025 % | — | — |
| 10 | lm-head base-coarse → argmax stage-1 | 1 | REDUCTION | 401,408 | −401,408 | +0.0118 % | REORDERED (argmax ties) | — |
| 11 | final RMSNorm → lm-head base-coarse | 1 | GRID-WIDE | 8,192 | −8,192 | +0.0018 % | — | — |
| 12 | embedding+RoPE → layer-0 input RMSNorm | 1 | GRID-WIDE + REDUCTION | 8,192 | −8,192 | +0.0018 % | — | — |
| 13 | argmax stage-1 → exact-winner | 1 | REDUCTION | 2,048 | −2,048 | +0.0017 % | — | — |
| 14 | exact-winner → refined-exact | 1 | GRID-WIDE (scalar) | 8 | −8 | +0.0016 % | — | — |
| **15** | **routed gate+up → down+residual `LRM:8636`** | 39 | **GRID-WIDE** | 319,488 | **+177.4 GB** | **−4,484 %** | — | **PR #48 repeat** |
| **16** | **shared gate+up → down+residual** | 39 | **GRID-WIDE** | 39,936 | **+22.2 GB** | **−561 %** | — | **PR #48 repeat** |
| **17** | **QKV → fused attention** | 40 | **GRID-WIDE** | 737,280 | **+10.4 GB** | **−263 %** | — | **PR #48 repeat** |
| **18** | **fused attention → O-proj** | 40 | **GRID-WIDE** | 604,160 | **+15.3 GB** | **−387 %** | — | **PR #48 repeat** |

### 5.2 The same ledger at the assignment's k-grid

Only the four live rows; `drain_gain_pct` shown for completeness and **excluded**
from EV per §3.2.

| # | pair | n | `dispatch_gain_pct` @ k=1.0 / 1.395 / 1.890 | `drain_gain_pct` (conjecture) | byte penalty | **EV @ k=1.0** | envelope EV (literal sum, k=1.890) |
|---|---|---|---|---|---|---|---|
| 1 | routed ∥ shared gate+up | 39 | 0.7338 / 1.0237 / 1.3868 | 0.789–0.903 | −0.0040 | **0.7378 %** | 2.294 % |
| 2 | QKV ∥ gate_sp | 40 | 0.7526 / 1.0499 / 1.4224 | 0.809–0.926 | −0.0041 | **0.7567 %** | 2.353 % |
| 3 | input RMSNorm → QKV | 40 | 0.7526 / 1.0499 / 1.4224 | 0.809–0.926 | −0.0083 | **0.7609 %** | 2.357 % |
| 4 | gate_sp ∥ attention | 40 | 0.7526 / 1.0499 / 1.4224 | 0.809–0.926 | 0 | **0.7526 %** | 2.349 % |

The advisor priced (QKV, gate_sp) at **n = 30** because family E is `T2b gate_sp
h64` (30 h64 layers). **The correct `n` is 40**: `T2b′ gate_sp h48` adds 10 more
layers of the identical kernel family, and the fold applies to both. That raises
the advisor's headline from 0.565 % to 0.753 % at k=1.0 — and it does not change
the verdict, because at the measured k it is 0.0699 %.

### 5.3 Maximum independent removal

Rows 2 and 4 both consume the same 40 gate_sp dispatches; rows 3 and 6 both
consume the same 40 input RMSNorms. The largest mutually compatible set is:

| removed | n | @ k=0.0872 |
|---|---|---|
| gate_sp (row 2 **or** 4) | 40 | 0.0658 % |
| input RMSNorm (row 3) | 40 | 0.0658 % |
| shared gate+up (row 1) | 39 | 0.0641 % |
| router top-8 (row 7, if the REORDERED cert lands) | 39 | 0.0642 % |
| **total** | **158** | **0.2599 %** |

**The entire removable pool is 1.5× below the 0.4 % bar and 1.9× below fern's
0.5 % bar.** At k=1.0 it would be 2.973 %; the gap between those two numbers is
the whole content of alphonse's 20:00Z measurement.

### 5.4 Byte-column arithmetic, shown

- `normalized` is 2048 bf16 = **4,096 B**. Deduplicating one read of it across a
  merged NONE pair saves 4,096 B × n.
  Row 1: 4,096 × 39 = 159,744 B. Row 2: 4,096 × 40 = 163,840 B.
- Row 3 eliminates the standalone norm's input read **and** its output write:
  8,192 B × 40 = 327,680 B.
- Row 15 (the worst): the down-projection grid is `(2048/4)·288` = 147,456
  threads = **512 threadgroups**. Fusing the gate+up producer into it by
  recompute makes every one of those 512 TGs read the full 8.913 MB routed
  gate/up bank [M4, census] ⇒ 512 × 8.913 MB = 4.56 GB per layer ⇒ +177.4 GB/step
  over 39 layers. At 2.5272e-8 %/B that is −4,484 % of `cs`. Dead by ~10⁴.
- Row 17: attention runs 32 TGs (h64, `(heads/2)·1024`); 32 × 10.824 MB
  [M4, census] = 346 MB/layer ⇒ +10.4 GB/step.

At the **measured** price the byte term is no longer negligible: for row 3 it is
**11 %** of the dispatch term (0.0083 / 0.0741). At k=1.0 it was 1 %. Worth
noting because it inverts the usual campaign intuition.

---

## 6. The four named questions

### Q1 — is family E (`T2b gate_sp`) → consumer TG-LOCAL or GRID-WIDE?

**Neither. The advisor's revised belief of `NONE` is confirmed for both adjacent
neighbours; the true data consumer is GRID-WIDE and is not adjacent.**

- **Producer side, (QKV → gate_sp): `NONE`.** Both dispatches read the *same
  Swift local* `normalized` (`LRM:5950`), not each other's output. QKV consumes
  it at `LRM:5951-5955`; gate_sp at `LRM:5994-5995`. Outputs are disjoint —
  `projected[rows]` vs `gate_values[heads]` (`LRM:4540-4545`, output shape
  `[1,1,heads]`).
- **Consumer side, (gate_sp → fused attention): `NONE`.** Attention reads
  `rawQueries/Keys/Values` — slices of the *QKV* output — and never touches
  `gateLogits`.
- **The actual consumer of `gateLogits` is the activated O-proj**
  (`laguna_oproj_act_h{48,64}_v1`, `LRM:4620`), **two dispatches downstream**,
  and that crossing **is GRID-WIDE**: every one of the 2048 O-proj output rows
  applies the per-head gate, so the 64-element (or 48-element) vector is
  broadcast to all 256 threadgroups.

So family E is a **floating independent dispatch** whose only true dependency
edge is non-adjacent and grid-wide. That is precisely the shape that makes it
worthless to *merge* and valuable to *co-schedule* (§9): 0.262 MB/dispatch,
8.27 µs, **3.313 µs of slack — 1.89 bars, the only family in the non-attention
pool that clears one bar** [M4, census, R107-G].

### Q2 — is any pair both TG-LOCAL and ≥30 dispatches?

**Exactly one candidate among adjacent pairs, and it is not exploitable.**

Row 5, **(O-proj → residual+RMS+router)**, n = 40: the crossing array is
`r`[2048] bf16, added element-wise at matching positions — genuinely TG-LOCAL.
But the merge removes **zero** dispatches, because the consumer's *first stage
after* the residual add is a **grid-wide RMS reduction over the crossing array**.
O-proj runs 256 TGs of 64 threads (`(2048/8)·64`); the router GEMV needs the
fully normalised vector. Absorbing only the residual add into the O-proj
epilogue leaves `rms + router` still needing its own dispatch. **n_effective = 0.**

Three further TG-LOCAL crossings exist (`LRM` #7→#11 `h` residual, n=39; #8→#11
`weights[8]`, n=39; lm-head #13→#16 `coarse`/`delta`, n=1) but **none is an
adjacent pair** — other dispatches sit between them — and #11 already reads `h`
directly, so they are already fused.

**Answer: one TG-LOCAL adjacent pair at n ≥ 30; zero exploitable.** The general
obstruction is worth stating as a rule: *a TG-LOCAL crossing is only fusable if
the consumer's first stage is also TG-LOCAL.*

### Q3 — which pairs are `r105_15_class = IDENTICAL` (skipping frieren's certificate)?

Two, both by the same construction, and both **INFERRED**:

**Row 2, (QKV ∥ gate_sp) — IDENTICAL if and only if built as a tile-range
branch.** I read both kernel tails:

| | QKV (`lagunaDecodeNVFP4QKVR1Source`, `LRM:4841-4877`) | gate_sp (`LRM:4469-4506`) |
|---|---|---|
| rows/simdgroup | 1 | R = 4 |
| values/thread | 16 | V = 8 |
| block K | 512 | BK = 256 |
| K-chunks | 4 | 8 |
| reduction | `simd_sum` over 32 lanes (`:4873`) | `simd_sum` over 32 lanes (`:4496`) |
| accumulator | `float` (`:4859`) | `float` |
| epilogue | `projected[out_row] = bfloat(result)` | **extra `float l = float(bfloat(r[row]))` round-trip** (`:4498`) then softplus |
| weight format | nvfp4 / 4-bit / group-16 | INT8 affine / group-32 (+ biases) |
| threadgroup | 64 (2 simdgroups) | 64 (2 simdgroups) |

Both reduce with a single `simd_sum` (no `simd_shuffle_down` loop) and both
accumulate in `float`, so a merged grid `(rows/2 + heads/8)·64` with a
tile-range branch that keeps each side's `V`/`BK`/`simd_sum`/`float(bfloat(·))`
**verbatim** is bit-identical. **Folding the gate rows into the nvfp4 row loop is
NOT** — it changes `V` 8→16, `BK` 256→512, the dequant path, and applies the
deferred row scale `* 4194304.0f` (`LRM:4745-4747`): **REASSOCIATED**. It is also
**inadmissible** independently, because it would move `g_proj` off INT8/group-32
affine, and `AGENTS.md`'s accepted envelope permits *only* group-32 affine INT8
for Q/K/V/O and per-head `g_proj`.

**Row 1, (routed gate+up ∥ shared gate+up) — IDENTICAL by the same tile-branch
construction, and this is the cleanest row in the ledger.** Both are nvfp4
g16/b4 SwiGLU QMVs over the same `normalized`, both 64-thread threadgroups, with
disjoint outputs (`routedActivated[8,512]` vs `sharedActivated[512]`) and no
shared reduction. Merged grid `(8·256 + 256)·64`. **INFERRED** — I read the
dispatch sites (`LRM:8045-8054`, `LRM:7221-7227`) and the format guards
(`LRM:10673-10683`, `LRM:8889-8901`) but did **not** line-by-line diff the two
kernel bodies' reduction order. That diff is the one cheap read that would
promote this row from INFERRED to source-confirmed.

**Row 4** (gate_sp ∥ attention) is plausibly IDENTICAL — `simd_sum` is
per-simdgroup over 32 lanes and so is invariant to the host TG size, meaning a
64-thread-equivalent gate branch inside attention's 1024-thread TG preserves the
reduction exactly — but it wastes 14 of 16 simdgroups and collides with active
PR #642. **INFERRED.**

Everything else needs a margin certificate: **row 3 REASSOCIATED** (MLX's AOT
`rms_norm` uses a 1024-lane row reduction; recomputing it inside a 64-thread QMV
TG is a different order), **rows 7 and 10 REORDERED** (router tie-break;
argmax ties).

### Q4 — any pair where merged unique bytes go UP (a PR #48 repeat)?

**Yes — four, and they are the four largest crossings in the step.** Rows 15-18.
All four are GRID-WIDE, and by the byte-sign law of §4 fusion by recompute
multiplies producer weight traffic by the consumer's threadgroup count:

| pair | consumer TGs | producer bytes/dispatch [M4, census] | `byte_delta`/step | EV |
|---|---|---|---|---|
| routed gate+up → down+residual | 512 | 8.913 MB | **+177.4 GB** | −4,484 % |
| fused attention → O-proj | 256 | 8.653 MB (h64) | **+15.3 GB** | −387 % |
| QKV → fused attention | 32 | 10.824 MB | **+10.4 GB** | −263 % |
| shared gate+up → down+residual | 512 | 1.114 MB | **+22.2 GB** | −561 % |

For scale: the campaign's entire byte budget moves the score 0.4 % per 15.10
MiB/step. Row 15 proposes adding **12,000× that** in one change.

PR #48's own mechanism is the cautionary precedent in the other direction: it
*reduced* dispatch count via an 8× threadgroup collapse and still scored
**−0.1488 %** (receipt `285f79fa`). Rows 15-18 are that failure mode amplified
by four orders of magnitude, and they are the reason `dep_scope` must be
established **before** any `n_removed` is priced.

---

## 7. The advisor's four unverified facts — all four adjudicated

Read against `Sources/MLXFastModel/LagunaRuntimeModel.swift` at `705484b9`
(12,147 lines, unmodified).

**F1 — CONFIRMED.** `lagunaGateSoftplusSource` at **:4467**; kernel
`laguna_gate_sp_h{heads}_v1` registered `:4513-4521` with `inputNames:
["input","packed_codes","scales","biases"]`, `outputNames: ["gate_values"]`. It
reads only the RMSNorm vector plus its own `g_proj` bank. Both it and QKV are fed
the same Swift local `normalized` (`:5950`), so **dep_scope = NONE**. In the
gate_sp branch `fusedQKV` is provably `nil` (the fused norm+QKV kernel at
`:5928-5931` requires `_nativeAffineQKVGateRows == nHeads`, mutually exclusive
with `_nativeAffineGProj != nil` — see F2), so `normalized == inputNorm(input)`,
one identical `MLXArray`.

**F2 — CONFIRMED, predicate exact, and the refused branch is the live one.**
`:5713-5714`:
```swift
let foldGateIntoBank =
    gate != nil && q.groupSize == 32 && q.bits == 8 && q.mode == .affine
```
Fold branch `:5719-5725` appends the gate `packedCodes/scales/biases` to the
Q/K/V blocks, `totalRows += nHeads`, `_nativeAffineQKVGateRows = nHeads`.
Refused branch `:5726-5727`: `} else if let gate { _nativeAffineGProj = gate }`.
Slice extraction at `:5979-5983`, `gateStart` as the advisor described.

**Why it refuses:** Q/K/V are re-quantised to **nvfp4 / 4-bit / group-16 for all
40 layers** by `lagunaNativeAffineWeight` (`:3092-3125`; `NVFP4_FROM` defaults to
`"0"`, `:3048-3054`), while `g_proj` goes through a *separate* quantizer
`lagunaNativeAffineGProjWeight` (`:478-497`) **hardwired** to `groupSize: 32,
bits: 8, mode: .affine`. So the predicate is false, `_nativeAffineGProj` is set,
decode takes `:5984-5997`, and `lagunaGateSoftplus` fires once per layer × 40.
The blocker is structural: `concatenated([q.packedCodes, …, gate.packedCodes])`
would be a **mixed-format concat**.

*Correction:* the advisor's cited line ranges 2960-2974 / 5302-5305 are unrelated
code (an indexed-metadata struct; a group-32 INT8 qmv source). The real
requantisation site is **`:3092-3125`**.

**F3 — PARTIAL.** Declaration CONFIRMED at `:3520-3536`,
`laguna_fused_norm_qkv_projection_bf16_h{heads}_v3`, `outputNames:
["queries","keys","values","gate_values"]`. The early-tile gate branch is
CONFIRMED at `:3433-3500` (`if (tile >= qkv_tiles) { … return; }`).

But **"character-identical softplus" is REFUTED** — semantically identical,
textually different. The fused bf16 kernel (`:3485-3496`) uses `bfloat
rounded_logit = bfloat(total); float logit = float(rounded_logit); …` while
gate_sp (`:4498-4506`) uses `float l=float(bfloat(r[row])); …`. Same op sequence,
same `isinf`/`isnan` guards, same `bfloat` round-trip before softplus; only
identifiers and whitespace differ.

More important: **it is not reachable on today's decode path.** Its only call
site (`:6042-6050`) is the `else` of `if lagunaUseNativeAffineQKV(layer:), let
fusedAffine = _nativeAffineQKV` (`:5916-5917`), and native-affine QKV is on for
all 40 layers. It also requires bf16 `wq/wk/wv/gProj` Linear weights
(`:5904-5914`). Its reduction uses `simd_shuffle_down` + a threadgroup split-K
(`:3463-3468`), a **different order** from the live nvfp4 kernel's `simd_sum` —
so it is not a drop-in bit-exact template either.

**F4 — CONFIRMED, with provenance.** `:5947` `let fusedTailGateLogits: MLXArray?
= nil`, consumed at `:5974-5978` — statically dead. `git log -S
fusedTailGateLogits` returns a single commit, **`99b974c1 "Sync promoted frontier
afcb832"`** (Mon 3 Aug 2026): it **arrived already stubbed**. The introducing
diff carries the decisive comment, now stripped from the working tree
(`:5936-5949` are blank):

> "The fused tail norm+QKV+gate kernel was removed after the r=1-regime
> re-sweep **re-measured it +2.7 %** (its defusion is the promoted state); the
> placeholder keeps the downstream defer/eager gate-activation plumbing
> unchanged."

**This is the single most important collision in the ledger.** The closest prior
art to row 2 was not merely untried — it was measured **2.7 % worse** and
deliberately defused, and that defusion is what is promoted today. Row 2 differs
(nvfp4 QKV + a NONE-scope tile branch, versus a three-stage bf16 norm+QKV+gate
fusion), but any brief that proposes row 2 must open by explaining why the
difference matters.

---

## 8. Stranded-fold sweep — the generalisation of F2

The advisor's highest-value extra ask: are other decode segments stranded by a
quantisation-format predicate? I swept `groupSize ==`, `bits ==`, `mode ==
.affine`, `fold…`, `_native…Rows` across `Sources/MLXFastModel`,
`Sources/MLXFastTransform`, and the editable vendor files.

**All format-stranded fusions on the scored decode path are in attention, and
they share one root cause:** `lagunaNativeAffineWeight` (`:3092-3125`)
re-quantises Q/K/V/O to nvfp4/4/16 for all 40 layers, while every fusion kernel
written for those banks is guarded on affine/8/32.

| # | site | predicate | live | stranded dispatches/step |
|---|---|---|---|---|
| 1 | `:5926-5931` fused **RMSNorm+QKV+gate** | `… mode == .affine, bits == 8, groupSize == 32, _nativeAffineQKVGateRows == nHeads` | **FALSE** | **~40** (standalone RMSNorm = ledger row 3) |
| 2 | `:5713-5714` `foldGateIntoBank` | `gate != nil && groupSize == 32 && bits == 8 && mode == .affine` | **FALSE** | **~40** (standalone gate_sp = ledger row 2) |
| 3 | `:5947` `fusedTailGateLogits = nil` | not a format gate — hard-nil consumer for the nvfp4 tail-fold | **dead** | same 40 as #2, alternative route |
| 4 | `:5669-5673`, `:5746-5750` indexed-LUT metadata | `mode == .affine, bits == 8, groupSize == 32, let biases` | **FALSE** | 0 dispatches (memory format only); renders `lagunaNormAffineQKVIndexedKernels` `:5447-5470` unreachable |
| 5 | `:6344-6347` fused gated O-proj (affine8) | `mode == .affine, bits == 8, groupSize == 32` | **FALSE** but **covered** by the nvfp4 twins `:6373-6402` | **0** |
| 6 | `:4529-4531` `lagunaGateSoftplus` | `bank.mode == .affine, bits == 8, groupSize == 32` | **TRUE** | 0 — this is the *cost* of #2, not a stranding |

**Negative results (checked, nothing stranded).** MoE `prepareFusedRoutedGateUp`
(`:10673-10683`) and `prepareFusedSharedGateUp` (`:8889-8901`) require
nvfp4/g16/b4 ⇒ **TRUE**, fusions active. Layer-0 dense MLP fusions
(`:9113-9127`) are guarded on `.bfloat16`, matching BF16 storage ⇒ **TRUE**.
Router/residual fusions (`:11172-11216`) are dtype-only. Editable vendor files
carry no scored format predicate (`SwitchLayers.swift:515`,
`KVCache.swift:698,1646` are only default parameters of unused quantised-cache
constructors).

**Bonus dead code found.** `Sources/MLXFastTransform/AffineMetadataCoding.swift`
writes `mlxfast-projection-metadata.safetensors` (`:24`, `:167`) from
`.self_attn.*` stems, invoked at `Transform.swift:242` — and I found **no runtime
reader** in `RuntimeWeightLoading.swift` or `LagunaRuntimeWeights.swift`; the
runtime rebuilds LUTs in-process at `:2974`. The offline sidecar appears **doubly
dead** on this checkpoint (affine8-only *and* unread). Not a timing lever; a
byte-budget and clarity note. UNKNOWN: whether a reader exists outside those two
files.

**Net:** the stranded pool is **80 dispatches/step** (rows 2 and 3 of the
ledger), which is exactly the 80 dispatches #483 priced at 0.108 µs each. The
sweep found no *new* stranded segment outside attention.

---

## 9. What I would do instead — the concurrency reframing

> **RETRACTED by §13.4.** The premise of this section — that the decode command
> encoder might be serialising the `NONE` boundaries — is **false in source**.
> MLX creates *every* compute encoder with `MTL::DispatchTypeConcurrent`
> (`Vendor/mlx-swift/…/backend/metal/device.cpp:545-548`) and emits a barrier
> only on a real buffer-aliasing hazard (`:315-349`, `:363-391`). The ≈1.8 %
> estimate below is **not available**: there is no unnecessary serialisation to
> remove. `device.cpp` is also not in `editablePaths`. I am leaving the section
> standing rather than deleting it, because the retraction is the most valuable
> single result in this report — see §13.4.

The ledger's `dep_scope` column has a second use, and it is worth ~14× more than
its first.

Rule 41 [M5, marginal]: **serialisation is 76.3 % of a 4,096 B dispatch
boundary**, against `c_fixed` 22.4 % and bytes 1.3 %. fern's §0.9.16 law from
PR #48: *a boundary costs what it SERIALISES, not what it drains and not what it
launches.* #617's open handle is precisely "whether the Metal compute encoder is
`MTLDispatchTypeSerial` where the dependency DAG does not require it", and
`backend/metal/**` **is** in `editablePaths` (`CURRENT_RESEARCH_STATE.md:571-573`).

**This ledger's `NONE` rows are the enumeration of the boundaries where the DAG
provably does not require serialisation:**

| independent pair | n/step | slack [M4, census, R107-G] |
|---|---|---|
| QKV ∥ gate_sp | 40 | gate_sp: 3.313 µs (h64), 3.310 µs (h48) — **1.89 bars, the only non-attention family clearing one bar** |
| routed gate+up ∥ shared gate+up | 39 | shared: −0.792 µs (byte-bound); routed: +0.963 µs |
| gate_sp ∥ attention | 40 | as above |

Order-of-magnitude, and I want to be explicit that this is **[conjecture]** built
on one measured constant: 79 unnecessarily-serialised 4 KiB-class boundaries × a
~3.99 µs boundary [M4, from my one-parameter model] × 76.3 % serialisation share
= **240.5 µs/step [M4]**. My R107-G census independently totals **241.9 µs/step
of positive slack = 1.842 % of `cs`** across all 13 families. Those two numbers
agreeing to 0.6 % is either a real result or a coincidence, and it is cheap to
find out.

Compare: **0.13 % for merging the same pairs, versus ≈1.8 % for stopping their
serialisation.** Same structural analysis; two orders of magnitude between the
two levers.

Two honest caveats. (i) My R107-G rule 100 finding is that `T3a`/`T3a′` fused
attention is **ISSUE-bound at 97.7 % of peak issue**, so there may be no spare
issue capacity to overlap *into* during attention — which is exactly why the
gate_sp ∥ attention row is the weakest of the three and the two MoE/QKV rows are
the strongest. (ii) This converges on an already-identified idea (Arm C's
"reorder emission so independent work — gate softplus, shared expert — fills
dependent gaps", `RESEARCH_IDEAS_2026-08-09_13:45.md:198`); my contribution is
not the idea but the **verified `NONE`-scope adjacency set** it needs as input,
plus the finding that `dep_scope` is decidable by source reading alone.

---

## 10. Caveats

1. **Every ledger row is INFERRED.** Zero receipts, by assignment design.
2. **Direction asymmetry is the gate.** All `dispatch_gain_pct` values at k ≥ 1
   assume removal refunds what addition costs. #483 measures 0.108 µs/dispatch
   with a CI spanning zero; rule 68 forbids the k=1.890 column outright.
   alphonse's 20:00Z removal-symmetry ratio decides whether §5.2 or §5.1 is the
   real table. **If that ratio comes back near 1.0 it contradicts #483 on #483's
   own family, and that contradiction must be resolved before anything is built.**
3. **The EV formula double-counts** (§3.2); my headline EV excludes the drain term.
4. **Host.** All census bytes and µs are **M4 Pro, gen 16, 20 cores**. Per
   `AGENTS.md`, threadgroup geometry can change sign across core counts, and the
   M5's 40-core issue capacity changes the concurrency argument in §9 in an
   unknown direction. None of these kernels has an `_nax` twin, so the kernel
   family is M4-reachable, but the *occupancy* conclusions are not transferable.
5. **404 vs 319.** I corrected the assignment's dispatch count. If the advisor's
   319 came from a different source than my census, the 85-dispatch delta needs
   reconciling before §5.3's 158 is trusted.
6. **Row 1 is INFERRED at the reduction-order level** — the one read that would
   firm it up is a line-by-line diff of `lagunaRoutedSwiGLUQMVPackedTop8R1Kernel`
   (`LRM:7915`) against `lagunaSharedSwiGLUQMVRows1[Halved]Kernel` (`LRM:7185`).
7. `qkv → queries/keys/values` slicing (`:6022-6027`) is assumed copy-free.
8. **rule 105.15 respected:** no `max_abs_diff` is cited anywhere in this
   document. The correctness gate is exact token-ID equality at
   `Sources/MLXFastCore/Golden.swift:387` and `:535`.
9. **Byte budget:** this file lives in `research/`, outside `editablePaths`, so
   it consumes none of the 318,794 B of remaining headroom (rule 105.14).

---

## 11. Suggested follow-ups (not implemented)

1. ~~**Highest value — reprice the axis, don't merge it.** Turn §9 into a real
   assignment: does the decode command encoder use `MTLDispatchTypeSerial` where
   the DAG (this ledger) says it need not?~~ **WITHDRAWN — answered in §13.4 for
   the cost of one source read, and the answer is no.** The encoder is already
   `MTL::DispatchTypeConcurrent` and barriers track real buffer hazards, so the
   ≈1.8 % does not exist; `device.cpp` is also not in `editablePaths`. Do not
   spend an assignment on it. The replacement follow-up is to look for a lever
   that shortens the **critical path** through the dependency DAG, since §13.4
   establishes that is what decode wall time is made of — removing off-path
   occupancy, however large in attribution, buys ≈0.
2. **Cheapest confirmatory read (≈15 min).** Diff the routed and shared SwiGLU
   QMV kernel bodies to promote ledger row 1 from INFERRED to source-confirmed
   IDENTICAL. It is the only structurally clean, collision-free, bit-exact,
   n=39 merge in the step — the one thing to build *if* alphonse's ratio
   surprises us.
3. **Resolve the #483 / alphonse contradiction explicitly.** If the 20:00Z ratio
   is ≫0.0872, the two results are measuring different things (one dependent,
   one independent dataflow?) and that distinction is worth more than either
   number.
4. **Reconcile the 85 uncensused dispatches** into the family census so future
   ledgers do not have to rederive the topology. My one-parameter byte model
   already predicts them to 14 % out of sample.
5. **Delete the dead surface** (advisor's call, byte-budget positive): `:5947`
   `fusedTailGateLogits` and its `:5974-5978` consumer, the unreachable
   `lagunaNormAffineQKVIndexedKernels` (`:5447-5470`), and — if no reader is
   found — the `mlxfast-projection-metadata` writer. `LagunaRuntimeModel.swift`
   is at 384,245 B of a 524,288 B per-file hard cap.
6. **Do not open rows 15-18** under any framing. They are PR #48 amplified 10⁴×.

---

## 12. Provenance

| item | value |
|---|---|
| base | `705484b9e120d60a973d660fdbdd1ccc7cdfa124` |
| scored-surface diff vs base | **empty** (`Sources`, `Vendor`, `benchmark.json`, `Package.swift`, `senpai` — verified `git diff --numstat`) |
| receipts | **none** (desk exercise) |
| host for all [M4] quantities | AWS M4 Pro, `applegpu_g16s`, gen 16, 20 GPU cores, 48 GiB, macOS 26.5.2 |
| census epoch | R107-G, `research/maple-tanjiro-r107g-decode-family-regime-census.md`, W&B `jhuxsg3h` |
| primary source read | `Sources/MLXFastModel/LagunaRuntimeModel.swift` @ 12,147 lines, unmodified |
| secondary sources | `research/maple-fern-r91-input-norm-fusion-price.md:14-24,36`; `research/CURRENT_RESEARCH_STATE.md:219-226,270-280,465-480,560-575,1470-1482,3245`; `research/RESEARCH_IDEAS_2026-08-09_13:45.md:52,121-127,190-200`; `research/RESEARCH_ARCHIVE_through-round-91.md:312,1423,4242` |
| terminal verdict | **`N-NO-MERGEABLE-PAIR`** — pricing refusal; three structurally clean `NONE` pairs named for contingency |

---

## 13. Route reconciliation (answers rule 105.23 and comments 5242807697, 5242969214)

Reproduction: `python3 research/maple-tanjiro-r108l-route-reconciliation.py`.
Every constant in that script is copied unchanged from the committed census
`research/maple-tanjiro-r107g-slack.py:22-31`. Nothing new was measured; this
section is arithmetic plus one source read.

### 13.1 The exact arithmetic, inputs, `k` and basis behind "1.89 bars"

The number is mine, from `maple-tanjiro-r107g-slack.py`, family
**E `T2b gate_sp h64`**. Inputs: `calls=30`, occupancy `248.0` M4 µs/step,
`262,000` unique B/dispatch, `k=0.5`, `PEAK=266.3e9` B/s,
`INTERCEPT=3.97` M4 µs, `PRICE=0.015228` %cs per M5 µs/step, `BAR=0.4` %cs.

```text
disp  = 248.0 / 30                      =  8.2667  M4 µs/dispatch
byte  = 262000 / 266.3e9 × 1e6          =  0.9839  M4 µs
floor = byte + INTERCEPT                =  4.9539  M4 µs
slack = disp − floor                    =  3.3128  M4 µs
      × calls (30)                      = 99.38    M4 µs/step
      × k (0.5) × PRICE (0.015228)      =  0.7567  %cs
      ÷ BAR (0.4)                       =  1.892   bars
```

`k=0.5` for family E specifically (β, the generic M4→M5 transfer); the other
four families carry the directly-probed `k=0.4369`. That asymmetry is in the
committed census, not introduced here.

**The basis is the part that matters.** `slack` is occupancy *above a floor that
already concedes the per-dispatch intercept*. It was commissioned to bound the
**fixed-dispatch-count / instruction-side** lever — the R107-G question. It was
**never** a ceiling on *removing* the dispatch. Quoting 1.89 bars against a
fusion proposal compares a fusion prize to a non-fusion bound.

### 13.2 Routes B and C are addends, not rivals — residual identically zero

| family | n | C (slack) % | intercept % | C+int % | B (advisor prize) % | residual | A (rule 65) % |
|---|---|---|---|---|---|---|---|
| D `T2c` routed gate+up | 39 | 0.2500 | 1.0301 | 1.2801 | 1.2801 | **0.0000** | 1.3899 |
| A `T3b` oproj h64 | 30 | 0.1586 | 0.7924 | 0.9510 | 0.9510 | **0.0000** | 1.0691 |
| C `T0b(a)` qkv h64 | 30 | 0.0110 | 0.7924 | 0.8034 | 0.8034 | **0.0000** | 1.0691 |
| B `T2d` down+residual | 39 | −0.2008 | 1.0301 | 0.8293 | 0.8293 | **0.0000** | 1.3899 |
| E `T2b` gate_sp h64 | 30 | 0.7567 | 0.9068 | 1.6635 | 1.6635 | **0.0000** | 1.0691 |
| **sum** | **168** | **0.9756** | **4.5518** | **5.5274** | **5.5274** | **0.0000** | **5.9872** |

Route B *is* route C plus the conceded intercept, exactly, for every family. My
R107-G run already printed route B for family E directly —
`(3.3128 + 3.97) × 30 = 218.5` M4 µs/step `= 1.664 % = 4.16 bars` — reproducing
the advisor's route B (1.69–1.78 %) to 2–7 %.

Over the whole population, **route A and route B agree to 1.083× (8 %)**:
5.987 % vs 5.527 %. Three routes, two independent instruments, one number.

### 13.3 The claimed 4.86× disagreement — same byte floor? Plain answer

The advisor asked whether 105.16's per-family slack uses the same byte floor as
my census, side by side. Here is the plain paragraph.

The five families' `calls` sum to **exactly 168**, so 105.16 and 105.17 are
priced over the *same* dispatch population; the 4.86× is not a population
effect. **105.16 does use my census byte floor, unchanged** — `PEAK = 2.663e11`
B/s, subtracted per dispatch as `uniqueB/PEAK`, equivalently `2.5272e-08` %cs
per byte; its numbers were derived *from* that census, so it could not have used
a different floor. **105.17 uses no byte floor at all** — it is dispatch count
times rule 65's marginal price, and bandwidth never enters the calculation. So
the two are not two estimates of one quantity under two different floors. They
are **two different terms of one decomposition**: 105.16 = 0.976 % prices what
sits *above* the floor, 105.17 = 5.987 % prices *the floor's dispatch term
itself*. The conceded intercept between them is 4.552 %, and
`0.976 + 4.552 = 5.527`, which agrees with 105.17's 5.987 % to 1.083×. The
"4.86×" is `5.987 / 1.232`, i.e. a total divided by one of its own two addends.
There is no disagreement to resolve, only a decomposition to name.

Independent cross-check on the per-dispatch overhead, the one quantity both
rules do estimate:

| instrument | M5 µs/dispatch | ratio to rule 65 |
|---|---|---|
| rule 55 intercept @ `k=0.4369` | 1.7345 | 1.349× |
| rule 55 intercept @ `k=0.5` (β) | 1.9850 | 1.179× |
| rule 65 marginal (M5-native) | 2.3403 | — |

Two instruments built from different experiments agree on the same physical
quantity to 18–35 %. Note also the **erratum** already carried in §3.1: my
R107-G script's printed line "rule 65's … 2.3403 µs × 30 = 70.2 µs/step =
0.535 % of cs" wrongly applies `k` to a rule-65 (already-M5) number. The correct
value is **1.069 %**; the reconciliation script omits `k` for route A throughout.

### 13.4 Answer to the three options: **option 3 — something not yet considered**

Not option 1 (`k` wrong): `k = 0.5 = β` is what the census uses for family E and
is the conservative generic transfer. Not option 2 (route B wrong): route B
reproduces from my own numbers to four decimal places and agrees with rule 65 to
8 %. The routes are not in conflict **with each other**.

The conflict is between *all three* of them and the **removal direction**. All
of A, B and C are **attributed per-kernel occupancy**. None is a measurement of
what happens when a dispatch is actually removed. The only marginal
removal-direction measurement on this axis is PR #483 on the input-norm family:
**0.108 M4 µs, CI [−0.221, +0.438]** — against family E's recoverable occupancy
of `disp − byte = 7.283` M4 µs/dispatch. A **67.4× gap**, with zero inside the
confidence interval. PR #48 (−0.1488 %) already falsified dispatch count as a
removal-direction proxy.

**The mechanism, from source, and it is decisive for the Stage-1 gate.** MLX
creates *every* compute encoder concurrent, and inserts barriers only on real
data hazards:

- `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp:545-548` —
  `buffer_->computeCommandEncoder(MTL::DispatchTypeConcurrent)`, unconditionally.
- `:315-328` — `set_input_array` raises `needs_barrier_` only if a bound buffer
  is in `prev_outputs_` (RAW).
- `:339-349` — `register_output_array` raises it only if the buffer is in
  `prev_inputs_` (WAR); `:330-336` routes outputs through `set_input_array` so
  WAW is covered too.
- `:363-391` — `maybeInsertBarrier` runs on every `dispatch_threadgroups` /
  `dispatch_threads`, but emits `memoryBarrier(MTL::BarrierScopeBuffers)` **only
  when that flag is set**.

So **adjacent independent dispatches are already free to overlap.** This yields
the ledger's central symmetry, and it is the cleanest statement of the terminal
verdict:

> A boundary's intercept is collectible **only where a barrier is actually
> emitted** — i.e. at dependent boundaries, `dep_scope ≠ NONE` — which are
> exactly the boundaries fusion cannot legally or profitably cross. And the
> boundaries fusion **can** cross, `dep_scope = NONE` (ledger rows 1, 2, 4),
> emit no barrier today, so there is no serialisation there to relieve.

This also reconciles rule 65 with #483 under fern's §0.9.16 law — *a boundary
costs what it serialises*. Rule 65's probes **added dependent dataflow** (rule 67
corollary), so each probe forced a whole-encoder `BarrierScopeBuffers` flush and
measured a genuine serialisation cost. #483 **removed** dispatches without
removing anything from the serialised critical path, and measured ≈0. Both are
correct measurements of different quantities.

Concurrency does not by itself close the 67× gap: rule 41's 76.3 % serialisation
share bounds the overlap correction at `1/0.763 = 1.311×`. The residue is the
§0.9.16 law itself — **decode wall time is set by the critical path through the
dependency DAG, and attributed occupancy above that path is free.** Removing
free work buys nothing. That is why every removal-direction receipt on this axis
has returned ≈0 while every attribution-direction estimate returns 1–6 %.

### 13.5 Canonical bars from my own census — correcting 105.23(e)

| family | mine | advisor 105.23(e) |
|---|---|---|
| D `T2c` routed gate+up | **0.62** | 0.71 |
| A `T3b` oproj h64 | **0.40** | 0.45 |
| C `T0b(a)` qkv h64 | **0.03** | *(left blank)* |
| B `T2d` down+residual | **−0.50** | 0.00 |
| E `T2b` gate_sp h64 | 1.89 | 1.89 |
| **sum** | **2.44 bars = 0.976 %** | 3.08 bars = 1.232 % |

The quoted 3.08 bars is **26 % high** against the signed sum and 5 % high
against a B-floored sum (2.94 bars = 1.176 %). Family C is 0.03 bars, not blank.
Family B is **−0.50** bars, not 0.00: it already runs at or below the modelled
DRAM floor, which is a **flag on the byte audit** (~3 % tension, §10) and not a
recoverable zero — flooring it to 0.00 discards a diagnostic.

### 13.6 Consequence for the Stage-1 go/no-go

If the merge is pitched at route B (≈1.66 % for the QKV ∥ gate_sp pair), the
source reading above says the intercept share of that number — 0.907 of the
1.664 %, i.e. **55 %** — is not on the table, because that boundary emits no
barrier. What remains is route C, **0.7567 % for family E and 0.0110 % for
family C**, and route C is a *ceiling* on instruction-side work, reachable only
by a kernel that does strictly less arithmetic — not by fusion, which changes no
arithmetic. Set against #483's directly measured 0.108 M4 µs and #48's
−0.1488 %, the expected value of building the merge is **≈0.1 %, not ≈1.7 %**.

**Verdict unchanged: `N-NO-MERGEABLE-PAIR`.** It now rests on a mechanical cause
in vendored source rather than on pricing arithmetic alone, which makes it
cheaper to refute than it was at submission: any counter-claim now has to show a
barrier being emitted at a `dep_scope = NONE` boundary.

**And the retraction is the actionable half.** §9 proposed spending Stage-1 on a
concurrent encoder at ≈1.8 %. That prize does not exist — the encoder is already
concurrent, the surviving barriers are all genuine data hazards, and
`device.cpp` is not in `editablePaths` in any case (the only editable
metal-backend files are `matmul.cpp`, `jit_kernels.cpp`, `kernels.h`,
`quantized.cpp`, plus the `kernels/` subtree). Spending the 21:00Z gate on
either the merge or the concurrent encoder is spending it on a priced-at-zero
axis. If Stage-1 needs a dispatch-side idea, it needs a *different* one.

