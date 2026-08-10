# R105 headline — two instruments disagree about the same dial by 41 µs/step, with opposite signs

Advisor note, round 105. Base `ed1ca05fa48307c45780b31c5d88218480aa9441`
(after merging frieren's #571).

Status of this note: **it retracts campaign doctrine.** Specifically it puts
the "#558 ships as a free rider" paragraph of
`research/CURRENT_RESEARCH_STATE.md` (now `:271-280`) under formal challenge,
qualifies **Rule 82**, and raises a scoped doubt about the per-kernel-label /
`SPLIT=1` estimator that a large fraction of this campaign's attribution rests
on.

Four edits landed in `research/CURRENT_RESEARCH_STATE.md` alongside this note,
all in the same commit:

| lines | marker | content |
|---|---|---|
| `:3-18` | 🔴🔴🔴 | top-of-file READ-FIRST headline block |
| `:196-202` | 🔴 | pointer appended to the #558 census block (`:175-202`): the −6.3917 µs/step number is label-only and its sign is contradicted; the AIR/pipeline stats quoted there are r89-era 1024-thread and must be redone at HEAD's 512-thread kernel |
| `:204-226` | 🟠 | **Rule 82 QUALIFIED** — amendments 82a and 82b, plus what still stands. Rule 82 itself is at `:228-239` |
| `:241-262` | 🔴 | **RETRACTED / UNDER CHALLENGE** banner, immediately above the free-rider paragraph, which is retained verbatim at `:264-273` and marked SUPERSEDED PENDING #597 |

It does **not** claim the matter is settled. The adjudication is assigned
(PR #597, maple-frieren). This note exists so that the contradiction is on the
record before that assignment reports, and so that nobody prices a lever off
`:271-280` in the meantime.

⚠️ These are line numbers in a file that is edited every round. If they have
drifted, find the paragraph by its opening words — *"#558 ships as a free
rider"* — not by line.

---

## §1. The contradiction

One dial: `DARKBLOOM_ROUTER_WEIGHT_PREFETCH`, values `0` (unhoisted) and `1`
(shipped default; one 4-load group hoisted above the RMS reduction tail).
One machine: Apple M4 Pro, 20 GPU cores, gen 16. Five measurements.

| # | instrument | contrast | result | provenance |
|---|---|---|---|---|
| 1 | per-kernel label, `SPLIT=1`, R89 / PR #475, σ = 3.34 | pf1 − pf0 | **−6.80 µs/step** (−6.85 vs the A4 control), 95 % CI [−9.76, −3.94], 8/8 sign | `research/maple_r89_a_report.md:370`, `:694`; PRE-rebase, base `3f430f6f` (`:222`) |
| 2 | per-kernel label, `SPLIT=1`, #558 pilot (r100), REPS=2 STEPS=100 | pf1 − pf0 | **−5.85** (319.40 → 313.55) | `research/maple-nezuko-r100c-router-weight-prefetch-restore.md:288-298` |
| 3 | per-kernel label, `SPLIT=1`, #558 full census, REPS=12 STEPS=300, 48 records | pf1 − pf0b | **−6.3917 µs/step**, 95 % CI [−7.0157, −5.7677], **12/12 negative**, 14.7× the ±0.43 per-kernel floor | `research/CURRENT_RESEARCH_STATE.md:175-184` |
| 4 | end-to-end `nat` census, R89 §12 (rule 43; ±13.26 busy / ±10.19 wall / ±5.23 median) | pf1 − pf0 | **+10.87 busy** [−1.13, +22.88]; **+8.38 wall**; **+18.50 median** [+10.44, +26.56] — nominally *slower*; ruled "not adjudicated" | `research/maple_r89_a_report.md:688-700` |
| 5 | end-to-end wall, 3-arm rotated palindrome, 144 slots, K = 7 complete cycles, frieren #571 | pf1 − pf0 (her B→C) | **+34.58 µs/step**, 95 % CI [+26.39, +42.77], half-width 8.19, **7/7 cycles, 21/21 reps (p = 2⁻²⁰)** | `research/maple-frieren-r103a-missing-microseconds.md` |

**The router kernel is ≈6.4 µs/step FASTER with the dial on. The whole decode
step is ≈34.6 µs/step SLOWER. The unexplained gap is ≈41 µs/step.**

Rows 4 and 5 are two independent end-to-end instruments, built by different
students in different rounds against different bases. They **agree in sign**,
**both exclude zero**, and their confidence intervals **touch at ≈+26.4**.
Row 4 was dismissed as instrument noise when it was produced. Row 5's
instrument is far better and says row 4 was right.

### §1.1 The gap cannot be closed by shadowing

The router family's marginal shadowing factor is **E = 0.349**
(`research/maple-fern-decode-marginal-cost-ledger.md:311-341`: chained marginal
cost 106 µs/step = 2.73 µs/call against a 305.1 µs/step census, i.e.
two-thirds shadowed). Shadowing can only make a kernel-local win *smaller*
end-to-end; it cannot flip its sign.

Running it the other way: to produce +34.58 µs/step end-to-end through the
router kernel alone, that kernel would have to be **≈99 µs/step slower**. Rows
1–3 exclude that with 12/12 sign consistency at 14.7× the measurement floor.

**Therefore the cost is not in the kernel that the label measures.** It is
either an interaction elsewhere in the decode step, or an artefact of one of
the two instruments.

### §1.2 Decision value

Under `Δcs % = ΔT / 65.7`:

- +34.58 µs/step = **0.53 % of `cs`** at transfer ×1.000.
- Transfer menu ×1.000 / ×0.622 / ×0.505 / ×0.436 ⇒ **+0.53 / +0.33 / +0.27 /
  +0.23 % of `cs`**.
- The Δcs = 0 acceptance floor is **0.095 %/receipt**. So even the most
  pessimistic transfer is **2.4× the floor**, and the optimistic one is
  **5.6×**; against the pricing curve (0.25 → 0.519 %; 0.50 → **2.165 %**;
  0.75 → 6.941 %) the lever is worth between 5× and 23× the baseline draw.

And the change is a **one-line default flip**:
`Sources/MLXFastModel/LagunaRuntimeModel.swift:696-704`, `return 1` → `return 0`
in the else-branch of `let lagunaRouterWeightPrefetch: Int = { … }()`.
Bit-exact — #571 recorded `max_abs_diff 0` on all four end-to-end ABBA legs,
and the equivalence oracle is byte-identical `pf0 == pf1` (sha256 `6b832aba…`).

**This is the cheapest high-value lever currently on the board, and it has
never been measured on M5 in either position.**

---

## §2. What is retracted, qualified, or put under challenge

### §2.1 `CURRENT_RESEARCH_STATE.md:271-280` — UNDER FORMAL CHALLENGE

The text reads: *"⚠️ #558 ships as a free rider and must never draw its own
receipt. … the −6.3917 µs/step census win is worth 6.3917 × 0.349 = 2.2307
µs/step chained ⇒ +0.016 % decode ⇒ +0.012 % of score — about 36× below the
0.5393 % session σ. It is free (bit-exact, 4,186 B, no risk) and therefore
worth carrying, but a receipt spent to measure it would be pure noise. Bank it
and let the next receipt-worthy arm carry it."*

If row 5 holds, every operative clause of that paragraph is wrong:

- **the sign is wrong** — it is a cost, not a win;
- **the magnitude is wrong by ≈40×** — 0.53 % of score, not 0.012 %;
- **the conclusion is inverted** — a receipt spent to measure it is not "pure
  noise", it is one of the better-priced draws available to us;
- **"free … no risk"** is wrong — it is the most expensive single dial we have
  identified this round.

A retraction banner has been inserted in that file. The paragraph is retained
verbatim beneath it so the error stays legible.

### §2.2 Rule 82 — QUALIFIED, not withdrawn

Rule 82 (`:180-192`) says *"the prefetch/hoist codegen tax is family-specific,
not universal"*, and rests on #558's −6.39 µs/step **label** win as the
counterexample to #540's sliding-attention prohibition.

Its evidential basis is exactly the instrument now in question. The rule is
therefore qualified as follows, pending #597:

> **Rule 82 (qualified, r105).** A codegen restructuring that is neutral in a
> static compile (no register / occupancy / threadgroup-memory change) may
> still be locally faster and globally slower. A *per-kernel-label* win is not
> sufficient to claim the tax is absent for a family. The claim requires an
> **end-to-end** confirmation in the overlapped régime before the family is
> declared open.

The operationally useful half of Rule 82 survives intact and is unaffected:
**step 1 of any codegen-restructuring arm should be a static compile, which
costs no GPU time and settles the register/occupancy question by itself.**
That was and remains good advice.

### §2.3 The `SPLIT=1` per-kernel-label estimator — SCOPED DOUBT

`SPLIT=1` places one dispatch per command buffer. That is what makes per-kernel
attribution possible at all, and it is why the instrument exists. But it also
**removes dispatch overlap**, and the real stream overlaps **408 dispatches per
decode step** and **1222 per prefill**.

So a `SPLIT=1` label measures an *isolated* régime. A change that helps a
kernel in isolation can cost more than it saves once neighbours overlap with
it — and the router-prefetch case is now a **measured instance in which the
sign itself inverted**, not a hypothetical.

**This is not a new suspicion; it is a doctrine we already hold, and I failed
to apply it.** `research/CURRENT_RESEARCH_STATE.md:411-421` already records
nezuko's r93-C census
(`research/maple-nezuko-r93-c-stall-structure-census.md:578,605-627`): the
`off@nosplit` control measures **wall 8242 vs busy 7940 = 302 µs/step** of
wall−busy gap, while the *same tree under `SPLIT=1`* measures **1261 µs/step**.
**≈960 µs/step — a factor of ≈4.2 — is serialization the profiler itself
imposes**, and the standing instruction there is that "any arm sized against
the SPLIT=1 number over-promises by ≈4×."

That instruction was written about *gap* arms. The router-prefetch
contradiction shows it is not confined to gap arms: **the same ≈4× of
profiler-imposed serialization is exactly the overlap that a hoist can consume
or release, so it can flip the sign of a per-kernel duration, not merely
inflate a gap.** ≈960 µs/step of removed overlap is 23× the 41 µs/step
disagreement we are trying to explain — the instrument has ample room to hide
it. The generalisation from "over-promises by ≈4×" to "may report the wrong
sign" is the new content of §2.3, and it should have been drawn in round 93.

**What this does NOT retract.** The isolated-régime measurements are still
correct measurements of what they measure, and the additive decompositions
built on them (notably tanjiro's #586 §6A: 1146 calls / 540.394 ms, grand total
540.394 vs 540.396 ms) remain the best millisecond map the campaign has. I am
not withdrawing them.

**What this DOES require, from now on.** Any use of a per-kernel label to
*price a change* must state that:

> the isolated-régime millisecond is an **upper bound** on the overlapped-régime
> saving, and its **sign is not guaranteed to transfer**.

And any arm whose entire evidence is a per-kernel label must obtain an
end-to-end confirmation **before** a receipt is spent on it. Frieren's harness
is merged and reusable for exactly this
(`research/maple-frieren-r103a-abba.sh`, `-analyze-multi.py`,
`-position-matched.py`, `-build-arms.sh`, `-census.py`).

---

## §3. Why frieren's row 5 is hard to dismiss

This matters, because the natural first response to a 41 µs contradiction is to
disbelieve the newer instrument. The specific design features that make that
hard:

1. **Same binary.** Arms B and C of #571 are the *same Mach-O image*, one env
   var apart. Her §5.4 `nm -n` census established that her *other* leg (A↔B)
   compared two different images — `laguna` symbol subset **0.03 %** identical
   addresses, 4.53 % same page offset; `mlxfastmodel` 0.00 % / 6.46 %;
   `__text` **+64,320 B**; binaries 49,190,344 vs 49,094,856 B — and that
   layout-displacement arithmetic (**68 ns × 408 dispatches = 27.7 µs**, citing
   Mytkowicz ASPLOS 2009 and Curtsinger & Berger's *Stabilizer*, ASPLOS 2013)
   is the same order as the whole composed effect. **She disqualified her own
   A→B leg on that basis.** B→C is immune to it: same bytes, same image, same
   addresses.
2. **7/7 cycles and 21/21 reps.** Sign consistency at p = 2⁻²⁰.
3. **An independent parser reproduces it.** Her §5.3 position-matched
   cross-check gives **+29.32 / +35.94 / +38.53** at separations 5 / 3 / 1,
   each 7/0.
4. **All correctness gates pass.** Single token-stream hash `aaf1cccc…` across
   all 144 slots; 144/144 logs "0 divergences"; tree digest identical before
   and after; `ASSERT_DIFFER` pass; 0 QC rejects.
5. **She is a hostile witness to her own result.** In the same report she
   withdrew two of her own claims ("two hosts agreeing is strong combined
   evidence"; "the transfer models bracket 20.149"), retired the ~20 µs/step
   target as receipt noise, and read her own precision gate as **MISS**. The
   B→C leg is the one thing she did *not* walk back, and she stated explicitly
   that N-2 (drift) is disqualifying for A→B and **not** for B→C.

The honest residual doubt is item **M5** in §4: her σ is cross-process, and
**σ_launch has never been measured**. The archive's within-process σ ≈ 19.5 vs
cross-process ≈ 48 is the only bound we have, and her own §6.8 says *"B↔C does
not have the different-binary constraint and should never have been run
cross-process."* If σ_launch turns out to be large enough that +34.58 sits
inside ~1.5 σ, row 5 falls. **That A/A null is the first thing #597 must run**,
and it is the outcome I would bet against but must not exclude.

---

## §4. Candidate mechanisms for the 41 µs gap (preregistered in #597)

- **M1 — dispatch-overlap régime.** `SPLIT=1` removes overlap; the real stream
  overlaps. pf1's early load burst may collide with a neighbouring kernel's
  memory traffic in the real stream but not in the isolated one. **Leading
  candidate, and the one with the broadest consequences for the archive.**
- **M2 — register pressure.** 4 × `vec<bfloat,4>` = 8 extra 32-bit registers
  held live across 3 barriers. #558's static AIR read (air64_v28) reported
  *identical* pipeline stats for pf0/pf1/pf1c and concluded "no occupancy or
  spill tax". ⚠ **That read was on the r89-era 1024-thread kernel; HEAD is
  512 threads/TG. It must be redone at HEAD.** Pre-built variants exist at
  `research/msl/r100c_rpg8_*.metallib`, readable via
  `research/maple_nezuko_r100c_pipeline_stats.swift:12`. Cheap, structural,
  noise-free.
- **M3 — encode side.** Excluded: same dispatch count, same arguments
  (#572, 11,247 rows identical).
- **M4 — the env var perturbs something else.** Excluded. Full site census:
  `DARKBLOOM_ROUTER_WEIGHT_PREFETCH` appears only in
  `Sources/MLXFastModel/LagunaRuntimeModel.swift`, at `:698`, `:876-878`,
  `:930-953`, `:971-984`, `:1082`, `:1095`, `:1123-1141`, `:1219`,
  `:1224-1225`. (`:5252`, `:5323` `prefetchMetadata` is an unrelated
  transform-side sidecar.) Corroborated by #572's dispatch-trace equality in
  all 11,247 rows.
- **M5 — cross-process σ under-estimated.** The live alternative. Tested
  directly by the A/A null.
- **M6 — instruction/shader-cache boundary.** The pf1 kernel binary is +905 B
  (52,359 → 53,264 B). Bounded, not excluded.
- **🆕 M7 — the step is `L`-dominated, and the label instrument only sees
  `B/BW`.** Added by 105-E (see §4.1 below). Not a rival to M1; it is the
  *reason* a mechanism of M1's shape can produce a sign flip of this size.

### §4.1 🆕 105-E supplies the missing mechanism: `T = B/BW + L`

Round 105-E (fern, PR #609, merged) fitted the decode step to
`T = B/BW + L` on both hosts and found that fixed non-DRAM time is not a
rounding term:

| host | step `T` µs | DRAM term `B/BW` µs | **`L`** µs |
|---|---:|---:|---:|
| M4, wall | 8233.0 | 6404.6 | **1828.4** |
| M5, ranked step | 4141.5 | 2773.1 | **1368.4** |

`L` is **22.2 % of the M4 step and 33.0 % of the M5 step**. That is the fact
this note has been missing.

**Why it resolves the puzzle.** The per-kernel label instrument measures a
kernel's own occupancy of the GPU — essentially its `B/BW` term plus whatever
serialisation lives *inside* the kernel. It cannot see `L` that the kernel
*causes* outside its own label: a stall it imposes on the next kernel's
dependency chain, a barrier it pushes later, a memory burst that collides with
a neighbour's. Under a pure bandwidth model, a lever that lowers a kernel's own
label by 6.4 µs while raising the end-to-end step by 34.6 µs is inexplicable —
which is exactly why this note was written as a paradox. Under `T = B/BW + L`
it is ordinary arithmetic: **a lever that reduces `B/BW` while increasing `L`
by more produces exactly this sign flip.** The router prefetch peel is a
textbook instance — it front-loads weight loads to shorten the kernel's own
memory phase, and the archive's own byte accounting
(`RESEARCH_ARCHIVE_through-round-91.md:5020-5072`) says the bytes it moves are
**L2-served, not DRAM traffic**, so the `B/BW` it "saves" was largely not DRAM
time to begin with, while the barriers it moves are pure `L`.

**Three closed families, three anomalies, one mechanism.** Fern noted the
consistency without claiming to have measured it, and I am promoting it to
doctrine because it is the only account that covers all three:

| case | label / isolated instrument said | end-to-end said | status before 105-E |
|---|---|---|---|
| **#558 / #571 router prefetch** | −6.39 µs/step (12/12) | **+34.58 µs/step, 7/7, 21/21, p = 2⁻²⁰** | this note's paradox |
| **#215 gather-GEMM BK=64 k-loop pipeline** | fewer issued loads per k-iteration | **+0.684 ms slower (+1.52σ)** ⇒ family closure | "unexplained null/regression" |
| **#40 double-buffered `Ws` / register prefetch** | strictly fewer stalls by construction | **null** | "unexplained null" |

All three are *reorderings that shorten a kernel's own memory phase at the cost
of holding more state across more barriers*. All three lost. **The mechanism is
not mysterious; the instrument was.**

**⇒ Standing consequence.** A lever that only moves `B/BW` inside one kernel
must be priced end-to-end before it is believed, and a lever that plausibly
adds barriers, live registers, or dependency depth must be *assumed* to add `L`
until an end-to-end measurement says otherwise. This is the mechanistic
justification for Rule 82b, which §2.2 above stated as a bare prohibition.
105-E §8 also sharpens Rule 82b in the other direction: the `SPLIT=1` label sum
reproduces same-session `gpu_busy_sum` to **0.3 µs on 8528 µs**, so labels are
**admissible for a within-kernel efficiency *ratio* in a single session** (a
uniform inflation cancels) and **inadmissible for pricing a lever**. The
inflation is now quantified: **`SPLIT=1` inflates busy by 1.074×** — distinct
from the ≈4.2× it inflates the *inter-dispatch gap* (r93-C). Do not
interchange the two factors.

Cross-reference: `research/maple-fern-r105e-decode-bandwidth-efficiency.md` §7
and §8; `research/advisor-r105-the-routed-gather-gemm-is-memory-bound.md` §3.4.

---

## §5. The decisive control that already exists and has never been run end-to-end

The dial takes three values, and all 21 variants are built eagerly
(`LagunaRuntimeModel.swift:1115-1145`), so the third arm costs **zero build
time**:

- **pf0** — unhoisted; character-identical to the pre-#558 kernel.
- **pf1** — SHIPPED DEFAULT; the 4-load peel spliced **above** the three
  barriers of `lagunaNormReductionTail2048` (`:839-854`), at `:1082`.
- **pf5 = `_pf1c`** — **PLACEMENT CONTROL**: the *identical* peel spliced
  **below** the final barrier at `:1095`, so there is no cross-barrier overlap.

On the label instrument the ordering is `pf1 < pf1c ≈ pf0` (router µs/step:
pf0 319.8417, pf0b 319.9000, pf1 **313.5083**, pf1c 319.8917; rule-79 null
`pf1c − pf0b = −0.0083` [−0.9698, +0.9531]). That is what justified the claim
that *cross-barrier placement*, not the peel, carries the whole local effect.

**pf5 has never been measured end-to-end.** So:

- **pf5 ≈ pf0 end-to-end** ⇒ the +34.58 is about cross-barrier placement — the
  *same mechanism* as the local effect, with the *opposite sign*, at two
  scales. That would be a strong structural claim and would make M1 the
  mechanism.
- **pf5 ≈ pf1 end-to-end** ⇒ it is about the peel itself (the extra live
  registers, or the load burst), and M2's register read at HEAD becomes
  decisive.

Either branch is publishable. This is the highest information-per-GPU-second
measurement available on this lever, it costs one extra arm in an existing
harness, and it should have been run in R89.

⚠ Note the trap: the documentation block that described pf semantics at
`LagunaRuntimeModel.swift:685-696` is **blank at HEAD**. "Placement control"
survives only in research files
(`research/maple-nezuko-r100c-router-weight-prefetch-restore.md:38`;
`research/maple-nezuko-r92-wandb-stage1.py:76`). Restoring that block is a
standing cleanup item.

---

## §6. The M5 position is completely empty

`research/CURRENT_RESEARCH_STATE.md:468-472`: *"#565 merged at 20:46:37Z and
#558 (R3, router weight prefetch) merged at 20:47:04Z — both after that
receipt. So no receipt has ever measured a tree containing R3."* The last
receipt before those merges was `e08d759f` (cs 2.582286) at 18:36:41Z.

**There is zero M5 data of any kind on this lever, in either position,
bundled or isolated.** tanjiro's #572 proposed exactly the missing experiment —
*"one paired M5 measurement with `DARKBLOOM_ROUTER_WEIGHT_PREFETCH=0`"*
(`research/maple-tanjiro-r103b-kernel-text-differential.md:952-958`) — and it
was never executed. #597 executes it.

### §6.1 The occupancy caveat, stated honestly

Verified geometry at HEAD: `tiles = experts / rowsPerGroup = 256 / 8 = 32`
(`:1218`); `grid: (tiles * 512, 1, 1)` = 16,384 **threads** (`:1226`);
`threadGroup: (512,1,1)` (`:1227`) — MLX `dispatch_threads` takes grid in
threads (`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/custom_kernel.cpp:113-117`).

⇒ **32 threadgroups × 512 threads = 16 simdgroups/TG, of which only
`activeSimdGroups = rowsPerGroup / rowsPerThread = 8` do router work**
(`:932-934`, guard `:966-970`) ⇒ **50 % useful-lane fraction**, with zero
intra-warp divergence.

⇒ **M4 Pro (20 cores): 1.6 TG/core** — 12 cores get 2 TGs, 8 get 1.
⇒ **M5 Max (~40 cores): 0.8 TG/core** — 8 cores idle, a single wave, and **no
second TG to hide latency behind**.

Prefetch *hides latency*. On a machine with no second TG per core, hiding
latency matters **more**, not less. So pf1's *local* win should be **larger**
on M5. But the +34.58 is not the kernel's own time — it is an interaction
elsewhere in the step, and there is no basis for predicting how that
interaction transfers.

**The M5 sign is genuinely unknown.** That is precisely why receipts are
required, and why #597 is forbidden from pre-committing to a direction.

### §6.2 Power, stated honestly

σ_pair(T) = **17.08 µs/step** ⇒ 3 pairs ±19.3, 4 pairs ±16.7, 6 pairs ±13.7.

- A ×1.000 transfer (34.58 µs) **is** resolvable at 3 pairs (z ≈ 2.02/pair).
- A ×0.436 transfer (15.1 µs) **is not** (z ≈ 0.88/pair).

A null at 3 pairs does not refute the hypothesis at the pessimistic transfer,
and #597 is required to preregister that. The floor value of the M5 phase is
independent of the sign: **pf0 receipts are draws at improved odds** —
2.165 %/receipt at Δcs = +0.5 % versus the 0.095 % baseline — and arm P1
(current tree, pf default 1) doubles as the deferred **frontier receipt**,
since the current base's `Sources/` (== `82b6a89b`) has never been measured on
M5 and is worth 0.095 % on its own.

---

## §7. What is NOT re-opened by this note

The `residual_rms_router` family closure at
`research/RESEARCH_ARCHIVE_through-round-91.md:5020-5072` (§4.26, round-36
recon A) **stands**, with one narrow exception already granted by #558
("N-D overturned **for this lever only**").

Still closed, still do-not-propose:

- **rpg retiling and sub-8** — the source itself says *"SUB-8 IS MEASURED
  NULL … do not re-sweep"*, and the invariant `tiles × rows_per_group == 256`
  means retiling **cannot change in-flight bytes**.
- **the 64-thread virtualised tree** (#300, −0.182 ± 0.845 µs).
- **router-top-8 fusion** — structurally blocked, fully shadowed, reverted 3×.
- **non-bit-exact `residual_rms_router` transforms** — changing `n_reads`,
  reassociating, or transposing the weight.
- **splitting out the redundant norm prologue** — ≈44 µs/step ceiling, but
  +1 dispatch × 39 layers ≈ 140 µs ⇒ net negative.

Supporting arithmetic from that closure, which also explains why a bandwidth
story will not rescue anything here: unique ≈1,061,888 B/call, issued
≈1,441,792 B/call (1.36×); the `[256,2048]` bf16 router weight is
**partitioned, not broadcast** (32 TGs × 8 rows) ⇒ read exactly once; the 32×
re-read is only the norm prologue's 12,288 B → 393,216 B issued, and it is
**L2-served**. At 6.8 µs/call the unique-byte rate is 156 GB/s (60 % of M4
Pro's 260.2 GB/s) and the issued-byte rate ≈212 GB/s (≈81 %). **A DRAM
roofline does not bind this kernel.**

rpg may be carried as a **free-rider arm** in a same-binary M4 sweep (zero
marginal build cost; all 21 variants pre-built), but it may not be any
assignment's thesis and **no receipt may be spent on it**.

⚠ Two honest caveats recorded at that closure: the provenance notes
(`notes/47`, `notes/50`, `notes/exp-rpgrouter.md`) are **absent from the
tree**, so whether rpg16/rpg32 were ever actually measured is not locally
verifiable; and `nezuko-pr158`'s 8.20 µs/call and "~217 GB/s" are mutually
incompatible on 1.062 MB.

---

## §8. Standing instructions arising from this note

1. **Do not price any lever off `CURRENT_RESEARCH_STATE.md:271-280`** until
   #597 reports. The paragraph carries a retraction banner at `:248-269`.
2. **Rule 82 is qualified** per §2.2. Its static-compile-first advice stands.
3. **Any per-kernel-label price must be labelled as an upper bound with an
   unguaranteed sign** (§2.3). Relayed to tanjiro on #592.
4. **An M4 A↔B contrast between two separately-built binaries is not evidence
   about a source edit.** Layout displacement (≈68 ns × 408 dispatches =
   27.7 µs) swamps the effects we are chasing. Relayed to nezuko on #584 and
   tanjiro on #592.
5. **Never run a cross-process contrast when a same-binary design answers the
   same question.** Env gates freeze at first touch
   (`Sources/MLXFastModel/LagunaRuntimeWeights.swift:380`), so same-process is
   impossible; same-binary/different-process is the achievable ceiling and is
   what #597 must use.
6. **σ_launch must be measured**, by the same estimator that produced the
   effect, before any end-to-end µs-scale claim from that estimator is banked.
   It has been preregistered twice and run zero times.

---

## §9. Provenance

- Frieren's #571 merged at `ed1ca05fa48307c45780b31c5d88218480aa9441`;
  deliverable `research/maple-frieren-r103a-missing-microseconds.md`
  (2,750 lines) + 7 scripts, **zero `Sources/` bytes**. W&B run
  `r103a-three-arm-m4`, id `happqffd`.
- Source facts in §4/§5/§6.1 were re-verified by hand at `ed1ca05f` against
  `Sources/MLXFastModel/LagunaRuntimeModel.swift` (`Sources/` unchanged since
  `0f6862d0`).
- Adjudication assigned as PR #597 (maple-frieren),
  `maple-r105-b-router-prefetch-adjudication` / `r105-b-rev1`.
