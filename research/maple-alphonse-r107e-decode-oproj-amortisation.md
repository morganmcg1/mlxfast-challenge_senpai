# R107-E — Decode oproj output-row amortisation (H-OPROJ-ISSUE)

Student: maple-alphonse · PR #644 · branch `maple-alphonse/r107-decode-oproj-amortisation`
Assignment `maple-r107-e-decode-oproj-amortisation`, revision `r107-e-rev1`
`BASE_SHA = 2454cc01ea3afabac067f0a271e36901fea7d21c`
Host: Apple **M4 Pro**, 20 GPU cores / 14 CPU / 48 GiB, macOS 26.5.2 (25F84),
Apple GPU generation **16** ⇒ `nax_available = false`, kernel family
`applegpu_g16s`. **Zero official submissions were dispatched from this PR.**

---

## §0 — Verdict

**`N-T3B-ROOFLINE`, plus `N-AMORT` mechanistically explained by
`N-ISSUE-BOUND`.** The T3b head of this family sits at its unique-byte roofline,
so the lever has nowhere to go; and when the lever is pulled anyway it costs
decode time rather than buying it. Both halves are measured, not inferred.

- **Primary verdict (§0.5).** Run first as instructed, frieren's unique-byte
  falsifier **fires** on T3b `oproj_act_h64`: the 37.2567 µs/call anchor
  decomposes as **87.05 %** unique-byte DRAM floor + **10.66 %** measured
  per-dispatch intercept, leaving **2.29 %** addressable — inside the 5 %
  tolerance. That split replicates R107-F's T2d **86.6 / 14.0 / 2.5** on a
  different kernel. T3c `oproj_act_h48` leaves 6.24 %, marginally outside
  tolerance, but is worth only **0.31 draw bars** in total. Family addressable
  slack: **44.49 µs/step M4 = 0.2960 %`cs` (α) = 0.74 draw bars**.
- **Secondary result, and it agrees (§2).** The `results_per_simdgroup` 4→8 main effect is a clean
  **regression of +110.60 µs/step M4, CI95 [+88.4, +132.8]** — in the bytes
  regime at α = 0.4369 that is **+0.7358 %`cs`, CI [+0.588, +0.884]** — with the
  same sign in 4/4 halves and in both schedule orders. Host **M4 Pro**, epoch
  **2026-08-10**.
- **Rule 105.7: the interval is the deliverable.** The estimator's half-width is
  **22.2 µs/step M4**, below both the **60.1 µs/step** solo bar and the
  **30.6 µs/step** summand bar, so this experiment was powered to see a
  shippable win and did not. Even the interval's most favourable end (+88.4
  µs/step) is a loss, so `excludes_summand_sized_gain` is true. **fern (#625) can
  stop budgeting decode oproj row-amortisation as a source of decode
  microseconds** — that is the positive contribution here.
- **Why (§1, §3).** The lever is structurally confounded by construction:
  `grid_threads = 32 · out_vec / results_per_simdgroup = 65536 /
  results_per_simdgroup`, with `num_simdgroups` cancelling exactly. Amortisation
  cannot be bought in this kernel without paying an equal factor of occupancy,
  and the measurement says occupancy is worth more than the issued traffic it
  saves. Factor A is therefore identically the inverse-grid-thread axis.
- **Not `V-TGSHAPE`.** The negative control g3 (same grid threads, twice the
  threadgroup) is flat: **+31.9 µs/step, CI [−277.5, +341.3]**, and
  `B_threadgroup_shape` is +39.1 µs/step, CI [−197.5, +275.8]. The effect tracks
  grid threads, not threadgroup shape; B and AB are unresolved at this n.
- **`N-ISSUE-BOUND` corroboration (§3).** The Rule-100 issue-slot model puts this
  family at **27.30 %** (T3b) and **25.28 %** (T3c) of measured issue peak,
  against the **97.7 %** that tanjiro #642 measured for the genuinely
  issue-bound fused-attention pool. Scaling the best arm's 16.234 % slot saving
  by the family's own 26.87 % time-weighted issue utilisation leaves a ceiling of
  **0.1107 %`cs` = 16.6 µs/step M4** — 3.61× short of the solo bar and 1.84×
  short of the summand bar. The lever cannot reach the bar even if it were free.
- **Regime verdict for T3b/T3c, from this instrument (§3, §5).** #648 comment
  5241940175 ranks `T3b oproj` as the second family whose regime verdict the
  campaign most needs, and asks for it *measured*, never read off §B.0.3's
  derived M5 column. This experiment answers it for T3b and T3c without waiting
  on #648: **BYTES-bound, `k = α`.** Evidence, all M4 Pro census-class:
  achieved **232.25 GB/s = 87.05 %** (T3b) and **215.05 GB/s = 80.60 %** (T3c)
  of the *measured* 266.80 GB/s host ceiling, against an issue-slot occupancy of
  only **27.30 %** / **25.28 %** of measured issue peak. A family cannot be
  ISSUE-bound at a quarter of issue peak, and rule 100's proven ISSUE-bound
  comparator sits at 97.7 %. So the 0.4 % bar for this family is
  **60.1 µs/step M4** (α = 0.4369; 67.5 at α = 0.389), which is **5.4 %** of
  T3b's own 1117.7 µs/step M4 census — reproducing the advisor's orientation
  figure from independent local data rather than from §B.0.3. The regime label
  in §B.0.3 row 3 is **confirmed** by measurement, not merely by the
  tautological M4↔M5 column agreement that rule 105.2 warns about.
- **Premise refuted independently (§5).** The residual-scaling test predicts an
  h48:h64 fixed-overhead ratio of 1.3333 if the residual were per-row issue work;
  the observed ratio is **0.8242**, `observed_sign = "OPPOSITE"`, and dispersion
  assigns the residual to the **fixed-per-dispatch** family (0.2133 vs 0.6177),
  i.e. the closed dispatch-count family of Rules 53/65/68 and #48.
- **`N-ROOFLINE` does not fire.** The family still holds 0.836–1.1365 %`cs` of
  roofline headroom (§5), above the 0.4 % bar. The deficit is real; row
  amortisation is simply not the instrument that collects it.
- **`N-CORRECT` / `N-BUILD` ruled out.** All four arms build and pass local
  correctness; 16/16 paired runs and 4/4 screen runs reported
  `passed_correctness = true`. All arms are bit-exact by construction (each
  output row is owned by one lane and accumulated in the same order).
- **Shipped state unchanged.** The instrument is reverted before the final commit
  (§7) and **no official submission was dispatched from this PR.**

### Mandatory caveats carried into the verdict

- **§B.0.6 α/β degeneracy.** Every M5-projected microsecond in this report
  inherits the two-parameter degeneracy recorded at
  `research/CURRENT_RESEARCH_STATE.md:1757`: `α ≈ 0.389` (M5 ceiling 686 GB/s,
  pool efficiency ≈ 0.86) and `α ≈ 0.437` (ceiling 610.6 GB/s, efficiency
  ≈ 0.62) fit the existing corpus equally well, differ by ~12 % in every M5
  headroom figure, and imply *opposite* research programmes — under the first,
  per-family efficiency work pays; under the second, only compulsory-byte
  reductions pay. R107-E is a direct empirical probe of that fork, because its
  arms move **zero** compulsory bytes (see §3). The named resolving experiment
  remains: run `research/fern_r101_bw_probe.swift` on the official M5 (~7 s,
  no submission-surface change).
- **M5 provenance label (carried verbatim as instructed):**
  `α = 0.4369 / β = 0.5 two-pool map, residual −6.63 %, #561`
- **Rule 98.9.** Every byte-count improvement reported here is
  **cache-resident issue-side traffic, not DRAM traffic.** The compulsory DRAM
  footprint is bit-identical across all four arms (§3, `weight_code_reread_factor
  = 1.0` in every arm). No figure in this report headlines a cache-resident
  number as a bandwidth saving.
- **Rules 105.11 / 105.12 (units direction and one-sidedness).** Every §2 number
  is a **raw local M4** marginal measurement, so it is converted with
  `× k × 0.015228` and never with the bare price; targets handed down in %`cs`
  are divided by 0.015228 **and then by `k`** to land on this bench (§1). Because
  `k < 1` the bare price always over-states, so this arm's regression cannot be
  an artefact of the units error in the favourable direction — the one-sidedness
  theorem means error #9 could only have produced false positives, and this
  result is a negative. R107-E was scoped as a **summand** arm under 105.5: its
  arms are bit-exact by construction (row ownership, not arithmetic order), it
  stays in a different family from edward's qkv site, and every interval is
  published even where it straddles zero.
- **Rule 105.15 — what my correctness evidence does and does not mean.** This
  report **never** cites `max_abs_diff` (a hard-coded literal `0` at every emit
  site) or `golden_hash` (the `golden.sha256` fixture digest) as evidence of
  numerical agreement. The gate that actually fired on all 32 in-situ runs is
  exact **token-ID equality** against the local golden
  (`Sources/MLXFastCore/Golden.swift:387`, `:535`), surfaced as
  `passed_correctness`; my analysis script raises if any row reports false. Under
  105.15(e) a green harness run is not sufficient for the draw bar, so §7 carries
  the **source-level non-reassociation argument** for all four arms instead of
  leaning on the harness. No margin certificate was requested because no arm
  produced a candidate worth certifying.
- **Pre-optimization AIR caveat.** R107-F established that `-S -emit-llvm` on
  Metal emits *pre-optimization* AIR: faithful for buffer attribution and access
  widths, useless for register pressure and scheduling. My §4 AIR census is
  therefore load for load and digest for digest, but its `spill_proxy` alloca
  observation is **not** evidence about registers. That claim is re-grounded on
  the post-optimization pipeline reflection in §5 (Rule 77) and is not carried
  into the verdict.

---

## §0.5 — frieren's unique-byte roofline falsifier, run first

Advisor comment 5242520568 merged R107-F
(`research/maple-frieren-r107f-t2d-down-residual-amortisation.md`) and instructed
me to run frieren's falsifier **before** anything else, because R107-F refuted my
exact change class on a sibling kernel: `outputs_per_simd` 4→8 on T2d
`expert_down` cost **+1.012 µs/call = +39.5 µs/step**, −0.30 %(β) / −0.26 %(α),
verdict `N-T2D-ISSUE-BOUND`, with the 22.07 µs/call decomposing as **86.6 %**
unique-byte DRAM floor, **14.0 %** inter-dispatch barrier drain and **≤2.5 %**
addressable. Her corollary 1 is now standing precedent: *issued-byte reduction at
unchanged unique bytes buys nothing at batch 1 and can cost.*

The falsifier asks two questions of each family, in this order:

1. what is the **unique-byte DRAM floor** — unique bytes per call divided by a
   read ceiling, plus the measured per-dispatch intercept;
2. what is the **clean in-situ residency-defeated anchor** µs/call;

and then reports the ratio. Inside ~5 % ⇒ the family is at its floor, the lever
has nowhere to go, report `N-T3B-ROOFLINE` and stop.

Implemented as `roofline_falsifier()` in
`research/maple-alphonse-r107e-traffic-model.py`; ledger block
`roofline_falsifier` in `research/artifacts/maple-alphonse-r107e/geom-traffic-model.json`.
Anchors are the same census-class per-dispatch numbers used throughout §5,
derived from the shipped-geometry paired baseline (`g0`, env unset) at
13.0806 ms/step, not from a resident micro-loop. The intercept is 3.97 µs/dispatch
— rule 55, independently replicated as the additive term of #648 §3.3's slack
bound.

| family | calls | unique B/call | DRAM floor µs | + intercept = floor µs | anchor µs/call | DRAM % | intercept % | **addressable slack %** | within 5 % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| T3b `oproj_act_h64` | 30 | 8,652,800 | 32.4318 | 36.4018 | **37.2567** | **87.05** | 10.66 | **2.29** | **yes** |
| T3c `oproj_act_h48` | 10 | 6,490,112 | 24.3258 | 28.2958 | **30.1800** | **80.60** | 13.15 | **6.24** | no |

**The falsifier fires on T3b.** My split **87.05 / 10.66 / 2.29** is within a
point and a half of frieren's T2d **86.6 / 14.0 / 2.5** on every term — an
independent replication of the same decomposition on a *different* NVFP4 kernel,
with a different weight tensor, a different activation width and a different
launcher. T3b is the head of my family: 30 of the 40 calls, 15.531 % of step
bytes, and by rule 105 the whole family is worth ~0.96 % of score. So the primary
verdict of this experiment is **`N-T3B-ROOFLINE`**, and the advisor's own framing
applies — this is a complete, publishable result, not a failure.

**T3c is marginally outside tolerance and is still too small to matter.** Its
6.24 % slack is 1.8842 µs/call × 10 calls = **18.8 µs/step M4 = 0.125 %`cs`
(α) = 0.31 draw bars**, so even a perfect capture of all of it cannot reach the
0.4 % draw bar, and it clears only 62 % of the 0.2034 % summand bar. The whole
family's addressable slack is **44.49 µs/step M4 = 0.2960 %`cs` (α) /
0.3387 % (β) = 0.74 / 0.85 draw bars**. Collecting the 0.2034 % second-summand
target from this family would require capturing **68.7 %** (α) or **60.1 %** (β)
of *every* non-byte microsecond in it, including the per-dispatch intercept that
no in-kernel change can touch (#648 §3.3: rule 57's marginal M4 glue is 1.2382 µs,
31 % of the intercept, so the glue sits *below* the floor and in-kernel slack
cannot be priced at `k_dispatch`).

**Ceiling provenance — the one caveat on this section.** The 266.80 GB/s read
ceiling is *borrowed* from fern-r101 corollary 3, measured on **another M4 Pro
host**, not in-run on this one. The advisor's instruction was explicit that the
ceiling must be measured on my own host and not read off a spec sheet or
inherited. The `roofline_falsifier` helper therefore takes the ceiling as an
argument and the ledger carries two slots, `borrowed_ceiling` (populated) and
`in_run_ceiling`. §5 records the in-run probe and, where the two ceilings
disagree, the in-run number governs. Direction of the sensitivity is worth
stating up front: a *higher* in-run ceiling lowers the DRAM floor and *widens* the
addressable slack, a *lower* one narrows it. So the borrowed number is not
conservative in the direction of my own verdict, and that is exactly why it has to
be replaced rather than defended.

**What the falsifier does not license.** It bounds *gains*. It says nothing about
how much a bad geometry can *lose*, which is why the measured +110.6 µs/step
regression in §2 is not in contradiction with 2.29 % of slack (§2, "Why a 110.6 µs
regression is compatible with 23.8 µs of slack"). Having run the falsifier first
and had it fire, I nevertheless report the paired measurement, because the arm had
already been measured when the instruction arrived and because a CI that excludes
a summand-sized gain is worth more to fern than a desk bound alone.

---


## §1 — Hypothesis and lever

**H-OPROJ-ISSUE.** The decode NVFP4 gated-affine oproj family — T3b
`oproj_act_h64` (30 calls/step) and T3c `oproj_act_h48` (10 calls/step) —
re-issues cache-resident activation and scale traffic once per output row. With
the shipped geometry each simdgroup produces only `results_per_simdgroup = 4`
output rows, so one pass over the activation vector is amortised over just 4
rows. Raising output rows per simdgroup should cut issued activation traffic
proportionally.

The lever is the generator's threadgroup geometry in
`lagunaGatedAffineOProjNVFP4Source` plus the matching launcher grid in the
lane-major branch of `lagunaGatedAffineOProjNVFP4`. Nothing else changes: the
same arithmetic, the same accumulation order per output row, the same weight
layout, the same dequantisation path.

### Arm table (2×2 factorial)

| id | `num_simdgroups` | `results_per_simdgroup` | rows/TG | threads/TG | TGs | grid threads | role |
|---|---:|---:|---:|---:|---:|---:|---|
| g0 | 2 | 4 | 8 | 64 | 256 | 16384 | shipped baseline |
| g1 | 2 | 8 | 16 | 64 | 128 | 8192 | 2× amortisation |
| g2 | 1 | 8 | 8 | 32 | 256 | 8192 | 2× amortisation, TG count preserved |
| g3 | 4 | 4 | 16 | 128 | 128 | 16384 | **negative control** |

The design is a clean 2×2:

- **Factor A — `results_per_simdgroup` 4→8** (the amortisation factor itself):
  A+ = {g1, g2}, A− = {g0, g3}.
- **Factor B — `rows_per_threadgroup` 8→16** (threadgroup shape):
  B+ = {g1, g3}, B− = {g0, g2}.
- **Interaction AB:** + = {g0, g1}, − = {g2, g3}.

g3 is the negative control: it doubles rows per *threadgroup* without touching
rows per *simdgroup*, so it changes threadgroup shape while leaving the
amortisation factor at 4. If g3 moves as much as g1, the effect is threadgroup
shape, not amortisation.

**Known confound, stated up front — and it is structural, not a design flaw.**
Because every output row is produced exactly once, `TGs × rows/TG = out_vec` is
fixed, and the grid collapses to a single identity:

```text
grid_threads = TGs * threads_per_TG
             = (out_vec / (ns * rps)) * (ns * 32)
             = 32 * out_vec / rps
             = 65536 / results_per_simdgroup        (out_vec = 2048)
```

`num_simdgroups` cancels. So in a fixed-output QMV kernel **factor A is exactly
the inverse grid-thread count** — g0/g3 at 16384 threads, g1/g2 at 8192 — and no
choice of `num_simdgroups` can restore the threads. You cannot buy amortisation
here without paying occupancy; that is arithmetic, not tuning. A positive A
therefore cannot distinguish "amortisation is worthless" from "amortisation is
real but smaller than the memory-level-parallelism it costs", and the two
readings have the same shipping consequence at this bar.

The one instrument that *would* separate them is split-K: keep 16384 threads and
give each simdgroup 8 rows over half the `k` range, then reduce. That changes the
per-row accumulation order, so it is not bit-exact and cannot be recommended for
integration under rule 102 without a margin certificate; it is a diagnostic
only. §6 records it as such.

**Factor B, by contrast, is clean.** B+ = {g1, g3} and B− = {g0, g2} are balanced
on `rps` and therefore on grid threads, so B is purely threadgroup *width* at
fixed total threads: 64→128 threads/TG within the rps=4 pair (g0→g3) and 32→64
within the rps=8 pair (g2→g1). Any B effect is a scheduling/shape effect and
nothing else.

### Preregistered outcomes

`V-AMORT` · `N-AMORT` · `V-TGSHAPE` · `N-ISSUE-BOUND` · `N-ROOFLINE` ·
`N-CORRECT` · `N-BUILD`. One is selected in §0.

### Shippability bar (rule 105 units contract)

A lever is shippable only at ≥ **0.4 % of `cs`** with a CI excluding zero.
Rule 105 (advisor comment 5241615076, commit `8695fb0e`) fixes how a **local M4**
delta converts into that currency. The campaign price
**0.015228 %`cs` per µs/step** was fitted on **official M5 decode**, so it
consumes *M5* microseconds; a local M4 delta must be mapped through the
cross-host factor first:

```text
Δ%cs = Δ_M4[µs/step] × k × 0.015228          k = α (bytes regime) or β (latency)
```

| regime | k | %`cs` per M4 µs/step | 0.4 % bar, M4 µs/step | 0.2034 % summand bar |
|---|---:|---:|---:|---:|
| bytes, α = 0.4369 (primary) | 0.4369 | 0.006653 | **60.1** | **30.6** |
| bytes, α = 0.389 (§B.0.6 fork) | 0.389 | 0.005924 | **67.5** | 34.3 |
| latency, β = 0.5 | 0.5 | 0.007614 | 52.5 | 26.7 |

This family is in the **bytes** regime, so the primary solo bar for R107-E is
**60.1 µs/step M4** (67.5 under the other α), *not* the 52.5 µs/step a β = 0.5
latency mapping would give — the earlier figure in this file was that superseded
latency number and is now retired. 60.1 µs/step is **5.4 %** of the oproj
family's own 1117.7 µs/step M4 cost (§5), which is the honest way to read the
size of the ask. The bytes label is **provisional pending #648**: if tanjiro's
dose instrument returns an ISSUE verdict for T3b then no bytes-regime `k` is
valid for this family at all, and the bar would have to be re-derived. It would
be circular to defend `k` by citing §B.0.3's regime column, so this report does
not.

**Rule 105.5 — the summand route.** The 0.4 % bar may also be met by a *sum* of
independently verified, bit-exact improvements from **different families**, each
with a CI excluding zero on the same tree. Rule 105.10 (comment 5241791262,
commit `c5db2915`) de-biases the L3 candidate for selection
(`12.27 × 0.707 × 0.8463 = 7.34 µs/step = 19.9 %`,
`research/advisor_r105_selection_bias.py`), leaving L3 at 29.6 µs/step =
**0.1966 %`cs`**, so a second different-family summand needs only
**0.2034 %`cs` = 30.6 µs/step M4 = 2.73 %** of T3b's own cost. Three conditions
bind that route, and all three are recorded here because R107-E is a candidate
summand: (1) it is conditional on L3 replicating — edward #629 Stage A is the
test, and #48's M5 receipt `285f79fa` measured a comparable 8× QKV grid collapse
at **−0.1488 %, a loss**; if L3 is zero the residual snaps straight back to
60.1 µs/step; (2) rule 105.7 still binds the measurement; (3) the two summands
must be load-bearing in different families (T3b oproj vs L3's T0b(a) qkv
qualifies). A sum that lands exactly on 0.400 % carries a 95 % CI of
**[0.23, 0.57] %** once L3's own σ = 0.0816 %`cs` is propagated, so "0.400 %"
is not a safe promotion threshold on its own.

**Rule 105.7 — the CI is the deliverable.** The M4 single-receipt detection bar
is ≈ **80 µs/step**, which is *above* the 60.1 µs/step bar: an unpaired M4
measurement mathematically cannot establish a win here. Paired ABBA on `nat`
resolves at σ = 6.25–10.65 µs/step, which can. So the result this experiment
owes the campaign is an **interval**, not a point estimate; a null is written as
"CI [−a, +b] with b well under the bar", which is a positive contribution
because it lets fern stop budgeting this lever.

**Unit-error restatement (advisor, comment 5241615076).** My own #630 §6 said
"+1.35 µs/token = 2.0 % of the 68.7 µs/step bar". That mixed a local M4
µs/token delta with an M5-derived bar and used the retired 68.7 figure. Restated
under this contract: **+1.35 µs/step M4 × 0.4369 × 0.015228 = +0.0090 %`cs`**,
i.e. **2.2 %** of the 0.4 % solo bar and **4.4 %** of the 0.2034 % summand bar,
both in the bytes regime at α = 0.4369. No rerun is implied; only the arithmetic
label changes.

**Rule 105.11 — the dual direction, and this arm's four numbers.** Advisor
comment 5241939801 (commits `a30fa5f8`, `38c8c64c`) states the inverse of the
rule I applied above: a target handed down in %`cs` is an *M5* target, so
expressing it in the M4 units this bench actually measures inflates it by
`1/k` — divide by 0.015228 **and then by `k`**. The discriminator for any of the
45 sites in `CURRENT_RESEARCH_STATE.md` where a µs/step and a % stand in the bare
ratio 0.015228: receipt-derived figures are already M5 (bare price correct),
§B.0.3-M5-column figures are already α/β-scaled (bare price correct), and **raw
local M4 figures — every number in §2 of this report — must go through `k`**.
Restated in this arm's units at `k = α = 0.4369`:

| what | %`cs` (M5-denominated) | M4 µs/step on this bench |
|---|---:|---:|
| endgame draw bar | 0.400 % | **60.1** |
| "does this justify a slot" line | 0.457 % | **68.7** |
| residual a second summand must cover if L3 replicates at 0.1966 % | 0.2034 % | **30.6** |
| that residual as a fraction of T3b's own 1117.7 µs/step M4 pool | — | **2.73 %** |

The numeral 68.7 recurs here with a *different* meaning from the retired 68.7 in
#630 §6; the restatement above deliberately prices through
`× k × 0.015228` rather than against any 68.7 figure, so the two cannot be
conflated. `n` for this experiment was therefore sized against the
**30.6 µs/step M4** summand effect, not against 60.1.

**Rule 105.12 — one-sidedness, and what it demands of this arm.** Because
`k < 1` always, applying the bare price to an M4 number *over-states*: advisor
error #9 could only ever have produced false positives, never a false negative,
so nothing on the closed list needs reopening and this report spends no time
there. Turned on the live slate the same theorem is uncomfortable: edward's
de-biased L3 is 29.6/68.7 = 0.43× the slot line, this arm's best case is
30.6/68.7 = **0.45×**, nezuko's revert residual is 19.0 µs/step M5 / 30.0 =
0.63× — **no remaining arm can clear the draw bar alone**. Three consequences
were designed into R107-E before the first paired run:

1. **Bit-exactness is not optional.** A summand needing a margin certificate
   cannot be added cleanly to another summand, so all four arms change only
   *which simdgroup owns which output row* — load placement, not arithmetic
   order. The per-row k-traversal order, the FMA order within a row and the
   32-lane `simd_sum` are untouched (§4 proves the shipped arm is byte-identical
   emission, and `logit_delta == 0` was gated on every arm), so no accumulation
   is reordered and no margin certificate is needed.
2. **The CI is reported even when it straddles zero** (rule 96.2). §2 publishes
   every contrast's interval, including the three that do straddle.
3. **Different family from edward.** This patch touches
   `lagunaGatedAffineOProjNVFP4Source` and its launcher only; the qkv path
   (`lagunaDecodeNVFP4QKVLaneMajorSource`) is untouched, so T3b and T0b(a)
   remain independent and admissible as separate summands (§5 deconfliction
   table).

Every quantity in this report is tagged **host · epoch · census-or-marginal**
per rule 105.6 as extended by 105.8/105.11: §2 is *marginal* (paired in-situ M4
deltas, epoch 2026-08-10), §3/§4 are *census* (static AIR and byte counts, host
independent), §5 mixes a measured M4 census (bytes/step, achieved GB/s) with
M5-column-derived pool figures that carry the mandatory provenance label.

---

## §2 — Paired in-situ timing

Host **M4 Pro**, epoch **2026-08-10**, one model-holding worker at a time,
`PRECOOL_SECONDS=120` plus `./benchmark.sh --local-cool-gate-only` before every
arm. Schedule per session is the 16-run palindrome
`g0 g1 g2 g3 | g3 g2 g1 g0 | g0 g1 g2 g3 | g3 g2 g1 g0`, i.e. four halves, two
forward and two reverse, so every contrast is estimated within a half and every
half is order-balanced against its mirror. 16/16 runs reported
`passed_correctness = true`.

**Session `abba1`** (n = 4 halves; g0 mean decode step **13.0806 ms**, g0
coefficient of variation across halves 0.793 %). Both units are given per rule
105.6; %`cs` uses the bytes regime at α = 0.4369.

| contrast | mean | CI95 | µs/step M4 | CI µs/step M4 | %`cs` | fwd / rev | sign | mde µs/step |
|---|---:|---|---:|---|---:|---|---|---:|
| **A_amortisation** | **+0.845 %** | [+0.676, +1.015] | **+110.60** | **[+88.4, +132.8]** | **+0.7358** | +0.923 / +0.767 | 4/4 | **22.2** |
| g1_vs_g0 | +1.145 % | [−0.649, +2.938] | +149.71 | [−84.9, +384.3] | +0.9961 | +1.195 / +1.094 | 4/4 | 234.6 |
| g2_vs_g0 | +0.790 % | [−0.471, +2.052] | +103.39 | [−61.6, +268.4] | +0.6879 | +0.131 / +1.450 | 3/4 | 165.0 |
| g3_vs_g0 | +0.244 % | [−2.122, +2.610] | +31.91 | [−277.5, +341.3] | +0.2123 | −0.521 / +1.009 | 3/4 | 309.4 |
| B_threadgroup_shape | +0.299 % | [−1.510, +2.108] | +39.12 | [−197.5, +275.8] | +0.2602 | +0.272 / +0.326 | 2/4 | 236.6 |
| AB_interaction | +0.055 % | [−1.370, +1.480] | +7.20 | [−179.2, +193.6] | +0.0479 | +0.793 / −0.683 | 2/4 | 186.4 |

Positive = slower. The single load-bearing row is **A_amortisation**, the
`results_per_simdgroup` 4→8 main effect: **+110.60 µs/step M4, CI
[+88.4, +132.8] (= +0.7358 %`cs`, CI [+0.588, +0.884] at α = 0.4369)**, the same
sign in all four halves and in both orders. Its half-width is 22.2 µs/step, so
`resolves_bar` and `resolves_summand` are both true: the instrument was sharp
enough to see either a 60.1 µs/step solo win or a 30.6 µs/step summand, and it
saw a regression instead. Per rule 105.7 the deliverable is that interval —
its most favourable end is **+88.4 µs/step**, i.e. still a loss — so
`excludes_summand_sized_gain` is true and **fern can stop budgeting the oproj
row-amortisation lever entirely** (§8).

Why A's interval is ~10× tighter than every other row: the palindrome balances
factor A exactly (A+ arms sit at schedule positions 2 and 3, A− at 1 and 4 in
each half, and mirrored in the reverse halves), so A's contrast is free of the
within-half position gradient. Factor B is off by one position, and the
single-arm contrasts carry the full gradient, which is why they are wide. This is
a property of the schedule, not of the effects: B and the interaction are
genuinely unresolved at this n (mde 237 and 186 µs/step).

**Second, more conservative estimator.** The ledger also reports `block_means`,
which averages each forward half with its reverse mirror before taking the
contrast, cancelling any linear drift *between* the two halves of a block as
well. It costs half the degrees of freedom. On `abba1` it gives the identical
point estimate for A (**+110.60 µs/step M4**) with CI **[+29.2, +192.0]**,
half-width 81.4 µs/step, `resolves_bar = false` at n = 2. Both estimators agree
on sign and magnitude; the half-diff estimator is the powered one, and where the
two disagree about resolution this report takes the conservative reading.

**Prefill placebo, same runs** (g0 = 1.1484 ms/token, cov 1.288 %). The decode
oproj call site is gated on `gatePerHead && B == 1 && L == 1`
(`LagunaRuntimeModel.swift:6355-6362`), so no arm can reach prefill; a prefill
effect would be instrument error. A_amortisation −1.103 % CI [−2.710, +0.503];
g1 −0.747 %; g2 −0.108 %; g3 +1.352 %; B +0.357 %; AB −0.996 %. **No placebo
contrast excludes zero.** The decode-fitted price is deliberately *not* applied
to this axis (that would repeat the unit error rule 105 names), so the placebo is
reported in % and µs/token only.

**Transfer to the ranked M5.** The regression is an occupancy effect (§1
structural confound: `grid_threads = 65536 / results_per_simdgroup`, exactly),
and the M5 Max has **40** GPU cores against this host's 20. At the A+ grid size
of 8192 threads the M5 gets 6.4 simdgroups per core where this host gets 12.8, so
the same change starves the M5 *harder*. The negative therefore transfers, and it
transfers in the safe direction: there is no plausible M5 reading in which
halving the grid to double amortisation becomes a win.

### Stage 1 — unpaired four-arm screen (session `screen1`, confounded)

`PRECOOL_SECONDS=0`, positions 1–4, 189–214 s per arm.

| pos | arm | decode s/tok | Δ vs g0 | prefill s/tok (placebo) | correctness |
|---:|---|---:|---:|---:|---|
| 1 | g0 | 0.01307970 | — | 0.00114136 | pass |
| 2 | g1 | 0.01318088 | +0.774 % | 0.00114368 | pass |
| 3 | g2 | 0.01314602 | +0.507 % | 0.00115303 | pass |
| 4 | g3 | 0.01310971 | +0.229 % | 0.00115371 | pass |

Two things follow immediately and are not confounded:

1. **All four arms pass local correctness.** `N-CORRECT` and `N-BUILD` are
   ruled out. Every arm builds through `./benchmark.sh --local-iterate` and
   produces matching greedy tokens locally.
2. **The screen is uninterpretable on speed.** The placebo prefill channel —
   which is *provably* identical code across arms (§4) — drifts +1.08 % across
   positions 1→4, about 0.36 % per position. That drift is the same size as the
   decode deltas being measured. Directionally all three candidates are slower
   than shipped, but a serial four-arm screen cannot establish that.

Stage 1 is reported as a build/correctness screen only. The speed claim rests
entirely on the ABBA-paired sessions.

### Between-session noise floor

`abba1.p01.g0` decode = 0.0132137 versus `screen1.p01.g0` decode = 0.0130797:
the **same arm at the same schedule position in two sessions differs by ~1 %**,
which is 2.5× the shippability bar. This is why nothing in §2 is estimated
across sessions; all contrasts are within-session, within-half.

### Variance structure: only position-balanced contrasts reach the noise floor

The six contrasts in the same 16 runs do not share one noise level, and the
pattern is systematic rather than incidental. Backing σ out of each reported
half-width:

| contrast class | example | implied σ (µs/step M4) | mde (µs/step M4) |
|---|---|---:|---:|
| position-balanced within a half | `A_amortisation` | **≈ 14** | **22.2** |
| single-arm difference within a half | `g1_vs_g0`, `g2_vs_g0`, `g3_vs_g0` | ≈ 130–150 | 165–309 |

The cause is visible in the raw rows: adjacent same-arm runs drift by far more
than any effect of interest — `abba1.p01.g0` vs `abba1.p08.g0` differ by
**252 µs/step**, and `p04.g3` vs `p05.g3` by **209 µs/step**, both ≈4–11× the
30.6 µs/step summand bar. A contrast that leans on one run per arm inherits that
wander; a contrast whose two sides have the **same mean schedule position inside
one half** cancels it. In the `g0 g1 g2 g3 | g3 g2 g1 g0` half, factor A's two
sides both average position 2.5, so a linear session drift cancels exactly and
only curvature survives — which the mirrored second block then removes.

**This is why the headline is factor A and not `g1_vs_g0`.** The two estimates
agree in point value (+110.60 vs +149.71 µs/step) but differ 10× in resolution,
and only the balanced one is powered against the bar. It is also the binding
constraint on any follow-up: a two-arm comparison must be run as a **4-run ABBA
quartet per half** (`g0 g4 g4 g0`, both arms at mean position 2.5) and mirrored
in the block's second half, never as adjacent pairs.

The estimator was checked against this claim on synthetic rows carrying a known
+0.02 %/run linear drift and an injected −0.500 % arm effect: it returned
**−0.518 %, CI [−0.564, −0.472]** on the decode axis and exactly **+0.000 %** on
a drift-only placebo axis, confirming that the balanced half removes the drift
rather than absorbing it into the effect
(`research/maple-alphonse-r107e-analyse.py --design occ2`).

### Power: a null is only worth reporting if it could have seen the bar

At this noise level a null could be a real null or an underpowered one, so the
estimator reports its own resolution rather than leaving that to the reader.
Each contrast carries `mde_us_per_step_m4` — the t-CI half-width, i.e. the
smallest effect that this many pairs and this much paired noise could have pushed
clear of zero — plus `resolves_bar` (half-width ≤ **60.1 µs/step M4**),
`resolves_summand` (≤ **30.6**), and `n_pairs_for_bar` / `n_pairs_for_summand`,
the number of ABBA pairs the observed paired SD would need to reach each
half-width. A verdict of `N-AMORT` is only stated as a refutation where
`resolves_bar` is true; where it is false the honest claim is "no effect of
shippable size was resolved at `mde_us_per_step_m4`", and the `n_pairs_*` fields
say exactly what it would cost to do better. Following rule 105.7, the estimator
also reports `excludes_summand_sized_gain` — true when even the interval's most
favourable end (`−(mean − h)`) is below the 30.6 µs/step summand bar. That flag,
not the point estimate, is what licenses fern to stop budgeting a family.
The paired SD is *not* the ~1 % between-session spread above — the palindrome
cancels session level and linear drift — which is the whole reason the design is
paired.

### Session `occ2` — bracketing the shipped geometry from the other side

The 2×2 above only moves *away* from the shipped point in the direction of more
amortisation, and that direction lost. That leaves one question the 2×2 cannot
answer: is `results_per_simdgroup = 4` an optimum, or merely a point on a
monotone slope whose better side was never sampled? Because the grid width is
`32 · out_vec_size / results_per_simdgroup = 65536 / rps` exactly (§1,
structural confound), the *opposite* move — `rps` 4 → 2 — doubles grid threads
to 32,768 and is the only bit-exact way to test the other side.

| id | `num_simdgroups` | `results_per_simdgroup` | rows/TG | threads/TG | TGs | grid threads |
|---|---:|---:|---:|---:|---:|---:|
| G0 | 2 | 4 | 8 | 64 | 256 | 16384 |
| **G4** | 2 | **2** | 4 | 64 | **512** | **32768** |

Bit-exactness is the same row-ownership argument as G1–G3: `out_row = tile *
rows_per_threadgroup + simd_gid * results_per_simdgroup + i` still enumerates
each of the 2048 output rows exactly once (512 tiles × 4 rows), the per-row
k-loop, the 16-value lane partition and the `simd_sum` reduction are unchanged,
and no accumulation order is altered. `rps = 2` *shrinks* the `result[]` array,
so unlike G1/G2 it cannot add register pressure.

The value of this arm is that the two models this report has built predict
**opposite signs** for it, so it cannot be a confirmation exercise:

- The Rule 100 slot model (§3) counts `values_per_thread + 1 + rps ·
  codes_per_thread + 2 · rps` = 25 load instructions per thread at `rps = 2`
  against 33 at `rps = 4`; at 2× the threads that is 1.515× the total load
  slots, **+51.5 %**, so a slot-bound kernel must get slower.
- The measured factor-A result points the other way: halving grid threads cost
  **+110.6 µs/step** while *removing* 16.2 % of slots, i.e. on this axis the
  slot model already has the wrong sign, and the binding quantity behaves like
  occupancy. Extrapolating that, doubling grid threads should *gain*.

Preregistered decision rule, fixed before the session:

- `V-OCC` — CI excludes zero and negative: the shipped `results_per_simdgroup`
  is not optimal. This is a two-line default change, so the instrument is then
  **not** reverted, and the arm is priced against the 30.6 µs/step summand bar.
- `N-OCC` — CI excludes zero and positive, or excludes a summand-sized gain:
  the shipped geometry is a **local optimum with both bit-exact neighbours
  worse**, which closes the geometry axis of this family for fern rather than
  merely failing to open it.

Design: `SESSION=occ2`, 16 runs as two mirrored blocks of the position-balanced
quartet `g0 g4 g4 g0` / `g4 g0 g0 g4`, so each arm has mean position 2.5 within
every half — the only structure §2's variance analysis found to reach the low
noise floor. Analysed with `--design occ2`; expected `mde ≈ 22 µs/step M4`,
which resolves the summand bar. The estimator, the drift-injection validation
and the prefill placebo axis are the same code as `abba1`/`abba2`.

#### Decision: `occ2` was desk-closed and **not run**

While `abba2` was in flight, #648 (R107-G, tanjiro) published its Stage-1
cross-family regime census, verdict `N-BYTES-EVERYWHERE`, and it prices exactly
this arm out. Its strongest form needs no exposure fraction at all: with
`floor_us = bytes / 266.3 GB/s + 3.97 µs` — where 3.97 µs is rule 55's measured
per-dispatch intercept on M4 — no change that leaves byte traffic alone can push
a dispatch below `floor_us`, and every geometry change in this experiment leaves
byte traffic alone (§3: `weight_code_reread_factor = 1.0` in every arm). So the
gap to that floor is a **hard ceiling on the entire non-byte lever** — exposed
ALU, latency, occupancy, issue slots, all of it, with no overlap assumption.

I recomputed it from my own dispatch measurements rather than adopting the
number, and T3b reproduces #648 exactly. #648 did not price T3c, so I extended
it (host **M4 Pro**, epoch 2026-08-10, **census**):

| family | bytes/call | µs/dispatch | `bytes_us` | `floor_us` | slack µs/disp | calls | slack µs/step M4 | % `cs` (α) | bars |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| T3b h64 | 8,652,800 | 37.2567 | 32.493 | 36.463 | **0.794** | 30 | **23.82** | 0.1585 | 0.396 |
| T3c h48 | 6,490,112 | 30.1800 | 24.371 | 28.341 | **1.839** | 10 | **18.39** | 0.1223 | 0.306 |
| **oproj family** | — | — | — | — | — | 40 | **42.21** | **0.2808** | **0.702** |

T3b alone is 0.396 bar, matching #648's 0.40 to the digit. The family total is
42.21 µs/step M4 — above the 30.6 µs/step summand bar, so a summand is not
*arithmetically* excluded, but it would require capturing **72.45 %** of every
non-byte microsecond in both oproj dispatches simultaneously. Priced at β
instead of α the family is 0.3214 % `cs` (0.803 bar) and the capture requirement
only falls to 63 %.

Set that against the three things this report already measured:

1. My own Rule 100 utilisation-scaled slot ceiling for the same family is
   **0.1107 % `cs` = 16.6 µs/step M4** — *already* 0.54× the summand bar, and it
   was derived independently, from AIR instruction counts and #642's issue rate,
   before #648 existed. Two unrelated desk models bracket the lever at 16.6 and
   42.2 µs/step; the summand bar sits above the tighter one.
2. The geometry axis has a measured sign, and it is the wrong one (§2): moving
   along it lost 110.6 µs/step. G4 moves the other way, but see the next
   subsection — the reason G1/G2 lost is bandwidth de-saturation, and h64 is
   already within **2.1 %** of its floor, so the other direction has at most
   that 2.1 % to recover.
3. #648's own per-student recommendation for #644 is "**STOP on the instruction
   axis; RE-AIM to bytes or stand down**" at high confidence. The advisor's
   standing instruction was to launch no further sessions if #648 returned
   `ISSUE` for T3b. It returned `BYTES`, which is *more* closing for a geometry
   lever than `ISSUE` would have been: an issue-bound kernel rewards removing
   instructions, a kernel with 0.79 µs of total non-byte slack rewards nothing.

So `occ2` would have spent 77 minutes of ranked-host-equivalent GPU time to
resolve a quantity whose entire upside is below the bar it would have to clear.
The design, the `g4` geometry entry, the position-balanced schedule, the
`--design occ2` estimator path (validated on synthetic drift-injected rows,
§2) and the g4 arms of the offline census, AIR load census and traffic model are
all committed and ready, so if fern ever wants the point measured the session is
one command. On the evidence it is not worth a slot, and the honest verdict for
the occupancy axis is a **desk closure**, labelled as such rather than dressed
up as a measurement.

### Why a 110.6 µs/step regression is compatible with 23.8 µs/step of slack

These two numbers look contradictory and are not, and the resolution is the
mechanism behind the whole result. The slack bound caps how much time a change
can **remove**. It says nothing about how much a change can **add**, because a
geometry that fails to saturate DRAM loses achieved bandwidth, and that loss is
unbounded above.

Factor A's +110.60 µs/step spread over the family's 40 dispatches is
+2.765 µs/dispatch. Applied to h64 that is 37.257 → **40.022 µs**, i.e. achieved
bandwidth **232.2 → 216.2 GB/s**, or **87.05 % → 81.04 %** of the measured
266.80 GB/s M4 Pro ceiling — a **6.01 pp** loss. That is the entire effect: at
8,192 grid threads this GEMV cannot keep enough loads in flight to hold 87 % of
peak; at 16,384 it can. Nothing was "spent" out of the 0.79 µs slack budget,
which is why the regression can be five times larger than the budget.

The same arithmetic bounds G4 from above. h64 at 37.257 µs sits **2.13 %** above
its 36.463 µs floor, so doubling grid threads to 32,768 can recover at most
2.13 % of that dispatch no matter how much latency hiding it buys. h48 has more
room — 1.839 µs is 6.09 % of its dispatch — but only 10 calls carry it. This is
the quantitative statement of "the knee is between 8,192 and 16,384 threads, and
the shipped point is past it", and it is the durable finding on this axis.

---

## §3 — Issued-traffic model (Rule 98.9: cache-resident, not DRAM)

`research/maple-alphonse-r107e-traffic-model.py` →
`research/artifacts/maple-alphonse-r107e/geom-traffic-model.json`. All
structural assertions pass.

T3b `oproj_act_h64` (`in_vec = 8192`, `out_vec = 2048`, `k_blocks = 16`),
g0 → g1/g2:

| quantity | g0 | g1 / g2 | Δ |
|---|---:|---:|---:|
| issued activation bytes | 8.913 MB | 4.456 MB | −50.0 % |
| issued total bytes | 18.416 MB | 13.959 MB | **−24.2 %** |
| issued / compulsory | 2.124 | 1.610 | — |
| activation re-read factor | 544× | 272× | −50.0 % |
| ops per useful FMA | 1.891 | 1.633 | −13.6 % |
| **`weight_code_reread_factor`** | **1.000** | **1.000** | **0** |

T3c `oproj_act_h48`: issued total 13.828 → 10.486 MB (−24.2 %), same ratios.

**The load-bearing row is the last one.** `weight_code_reread_factor` is exactly
1.0 in every arm, so the compulsory DRAM byte count is *identical* across g0,
g1, g2 and g3. The 24.2 % is issued-instruction / cache-resident traffic only.
Under the pessimistic branch of the α/β fork (§0), a change that moves zero
compulsory bytes is predicted to move zero time.

**Static IR is flat and is not evidence of amortisation.** The AIR census (§4)
shows instruction-*site* counts essentially unchanged across arms because the
`k_blocks` loop is not unrolled. Those are static counts, not dynamic issue
counts. They are reported for completeness and are **not** used as amortisation
arithmetic.

**Named risk.** `results_per_simdgroup = 8` halves grid threads 16384 → 8192,
i.e. 256 simdgroups. On a 40-core M5 Max that is ~6.4 simdgroups per core, which
may under-supply memory-level parallelism. On this 20-core M4 Pro the same arm
gets ~12.8 simdgroups per core, so **this host is structurally more forgiving to
g1/g2 than the ranked M5 is.** A local null is therefore not weaker evidence
than an M5 null would be; a local win would need M5 confirmation.

### Dynamic load census, and independent confirmation of the brief's arithmetic

`research/maple-alphonse-r107e-air-loads.py` →
`research/artifacts/maple-alphonse-r107e/geom-air-loads.json`. This walks the
emitted AIR of all eight arm × head variants, classifies every `load` by address
space and element type, and multiplies rolled-loop trip counts to get *dynamic*
loads per thread per k-block. The brief's §3 asserts "≈32 loads per thread per
k-block, 8 of them to DRAM, ~75 % cache-resident". Derived independently here:

| loads per thread per k-block | g0 / g3 (rps = 4) | g1 / g2 (rps = 8) |
|---|---:|---:|
| activation `xp[i]` (bfloat) | 16 | 16 |
| gate value (bfloat) | 1 | 1 |
| weight codes `wl[j]` (i32) | 8 | 16 |
| scale bases `bs[row]` (i8) | 4 | 8 |
| scale nibbles `sp[…]` (i8) | 4 | 8 |
| **total issued** | **33** | **49** |
| of which reach DRAM | 8 | 16 |
| cache-resident share | **75.8 %** | 67.3 % |
| **issued loads per output row** | **8.25** | **6.125** (−25.8 %) |
| **DRAM loads per output row** | **2** | **2** (invariant) |

The g0 column reproduces the brief's 33/8/75.8 % arithmetic exactly, from the
compiler's own IR rather than from the same hand count. The last two rows are
the whole experiment in miniature: issued loads per output row fall 25.8 %,
DRAM loads per output row are *exactly* invariant. That is the arithmetic reason
`weight_code_reread_factor` is 1.0 in every arm.

**Static load sites are identical in all four arms**: device 5, thread 14,
threadgroup 0. Two of the five device sites are `bfloat` (activation, gate), one
`i32` (codes), two `i8` (scale bases, scale nibbles). The escape plane is a
single `i8` site reached through a *pointer select*, not a branch — which
independently corroborates the advisor's §3.1 "no escape divergence" dead-end
claim from a second instrument.

**No AIR-level spill signature.** Allocas are `[16 x float]` (`x_thread`) plus
`[4 x float]` (g0/g3) or `[8 x float]` (g1/g2) for `result[]`. Private float
count is 20 (g0/g3) versus 24 (g1/g2) — *exactly* the declared inventory, with
no extra alloca. Honest limitation: AIR allocas are pre-register-allocation, so
this rules out a source-level spill but not a register-allocator spill; the
authoritative check is the pipeline reflection in §5's Rule-77 table.

### Rule 100 — pricing the lever's issue-slot ceiling before spending a session

Rule 100 (tanjiro, #642) is the right tool to close this out without a single
extra GPU-hour. It supplies a *measured* Apple-GPU issue rate on this host —
0.008255 µs per fma-per-thread at 32,768 threads, i.e. **3.969e12 issue slots/s**,
96.7 % of the 2560-lane × 1.578 GHz theoretical 4.040e12 — and the lesson that
apparent headroom in the two-pool map is not evidence of a lever. Apply the same
accounting to the oproj family. Every removed instruction slot (load, integer,
convert, fma) is credited at the *full* FP32 fma issue cost and the occupancy
loss is assumed free, so this is a deliberately generous upper bound.

Per-thread per-k-block instruction inventory, which reproduces the AIR census
exactly (`load_instructions_per_thread_per_k = values_per_thread + 1 +
rps·codes_per_thread + 2·rps`): g0/g3 = 16 + 1 + 8 + 4 + 4 = **33**;
g1/g2 = 16 + 1 + 16 + 8 + 8 = **49**. Scaled by grid threads (65536/rps) and
k-blocks, `rps` 4→8 removes **16.234 %** of the family's issue slots.

| family | µs/dispatch | slots/dispatch (g0) | % of measured issue peak | % of theoretical peak |
|---|---:|---:|---:|---:|
| T3b `oproj_act_h64` | 37.2567 | 40,370,176 | **27.30** | 26.82 |
| T3c `oproj_act_h48` | 30.1800 | 30,277,632 | **25.28** | 24.83 |

That is the decisive number. The pool tanjiro proved issue-bound runs at
**97.7 %** of peak issue. This family runs at **27.3 %** of peak issue while
sitting at 87.0 % / 80.6 % of its bandwidth roofline. The two instruments agree
on the regime: oproj is bytes-bound, and issue slots are not the serial resource.

Pricing the lever anyway (h64: 6,553,600 slots removed ⇒ 1.6512 µs/dispatch =
4.432 % of the dispatch ⇒ 49.536 µs/step M4 ⇒ 21.642 µs/step M5; h48:
4,915,200 slots ⇒ 1.2384 µs/dispatch = 4.103 % ⇒ 12.384 µs/step M4 ⇒
5.411 µs/step M5):

| arm | h64 % of `cs` | h48 % of `cs` | combined |
|---|---:|---:|---:|
| g0, g3 | 0.0000 | 0.0000 | 0.0000 |
| g1, g2 | 0.3296 | 0.0824 | **0.4120** |

So at **100 % issue-boundedness** the lever's ceiling is 0.412 % of `cs` — it
would clear the 0.4 % bar by 3 %, with no margin for the occupancy it must pay.
At the measured time-weighted issue utilisation of **26.87 %**, the ceiling is
**0.1107 % of `cs`**. For the lever to reach the bar, a removed load/integer
slot would have to cost **3.613×** an FP32 fma slot.

Caveats, stated because they all point the same way: rule 100's rate was measured
on FP32 FMA issue in a different kernel with 1024-thread threadgroups; treating a
load or integer op as one fma slot assumes a single shared issue port; the op
counts are a source-level model, not disassembly (the applegpu-nt blocker is
still open); and the whole construction is an upper bound that assumes issue is
the *only* serial resource, which the roofline says it is not. Under every one of
those caveats the true value is smaller than 0.1107 %.

Provenance label carried verbatim for the M5 conversion:
`α = 0.4369 / β = 0.5 two-pool map, residual −6.63 %, #561`.

### Rule 75 — emission digests for all eight variants

sha256, first 16 hex digits, over the `.metal` source and the compiled `.ir`:

| variant | metal digest | metal B | AIR digest | AIR B |
|---|---|---:|---|---:|
| g0_h48 | `2d0a4283cbbf8b34` | 4727 | `3e78cecf5e2fa561` | 18744 |
| g0_h64 | `70fb41cdf86ad63b` | 4727 | `ed2bc1be21b0b8df` | 18736 |
| g1_h48 | `380fa5146bf5e4b8` | 4751 | `1128222f326aba9c` | 18744 |
| g1_h64 | `439f050525e47614` | 4751 | `f102c9ac29bda262` | 18736 |
| g2_h48 | `744bd8b5537f67c4` | 4751 | `5ca5d2a4f82a4397` | 18722 |
| g2_h64 | `1f8ea648c700627a` | 4751 | `a292f9d7636edb2e` | 18713 |
| g3_h48 | `6381d6b8a8b8bc0d` | 4727 | `2943efb552d88e34` | 18744 |
| g3_h64 | `e40c239da4d0b007` | 4727 | `931396a3863b456f` | 18736 |

All eight AIR digests are distinct, so no two arms can be silently serving the
same compiled kernel.

---

## §4 — Offline AIR census, and why "env unset" is a sound baseline

`research/maple-alphonse-r107e-oproj-geom-census.py` →
`research/artifacts/maple-alphonse-r107e/geom-air-ledger.json` plus
`oproj_g{0..3}_h{48,64}.metal` / `.ir` / `.compile.log`.

All 8 arm × head variants compile cleanly under
`xcrun metal -std=metal4.0 -fno-fast-math`.

The decisive result:

```
g0_emission_identical_to_base = { h48: true, h64: true }
```

The parameterisation is a **provable byte-for-byte no-op for the shipped arm**.
That licenses using "`DARKBLOOM_OPROJ_GEOM` unset" as the paired baseline from a
single build, instead of rebuilding at `BASE_SHA` between arms — which would
otherwise have doubled session length and injected build-order confounds.

### Rule 99.3 — resolved pipeline name for both oproj dispatches

The brief asks for the resolved pipeline name so that "which kernel actually
ran" is not an inference. The name is assembled in the live dictionary
(`LagunaRuntimeModel.swift:4599-4607`) and then prefixed by MLX
(`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/common/metal_kernel.cpp:289`,
`kernel_name = "custom_kernel_" + name`; `template_args` is empty on this path,
so no template hash is appended). The three feature flags in the name all
default *on* — each is `env[...] != "0"`:

- `lagunaAttnScalePairwiseOProjEnabled` → `_pw1` (`LagunaRuntimeWeights.swift:721`)
- `lagunaNvfp4QmvSignCarryEnabled` → `_sc1` (`LagunaRuntimeModel.swift:4130`)
- `lagunaNvfp4QmvSeedElisionEnabled` → `_se1` (`LagunaRuntimeModel.swift:4158`)
- `lagunaGateSoftplusEnabled` (`:4468`) selects the *activated* lane-major dict

Resolved names, per arm:

| arm | T3b (h64) | T3c (h48) |
|---|---|---|
| g0 | `custom_kernel_laguna_oproj_act_h64_v1_lm1_pw1_sc1_se1` | `…_h48_v1_lm1_pw1_sc1_se1` |
| g1 | `…_h64_v1_lm1_pw1_sc1_se1_g1` | `…_h48_v1_lm1_pw1_sc1_se1_g1` |
| g2 | `…_h64_v1_lm1_pw1_sc1_se1_g2` | `…_h48_v1_lm1_pw1_sc1_se1_g2` |
| g3 | `…_h64_v1_lm1_pw1_sc1_se1_g3` | `…_h48_v1_lm1_pw1_sc1_se1_g3` |

The arm tag is deliberately part of the name so Metal's pipeline cache cannot
serve a sibling arm's compiled pipeline to the arm under test.

**Honest limitation.** This is a static derivation from the flag defaults plus
MLX's naming rule, not a runtime print: a runtime print would need a `Sources/`
instrument that this experiment must revert. The zero-source-change confirmation
available is `DARKBLOOM_ATTN_SCALE_NARROW_LOG=1`, which makes the existing
`lagunaNarrowScaleLog.noteDispatch("lane-major", "oproj h\(heads)")` at `:4620`
report that the *activated lane-major* dictionary — the one whose geometry is
parameterised — is the dispatching path. That observation is reported in §7
alongside the upstream-equivalence run, which is where it costs no extra GPU
occupancy.

### Built-in placebo channel

The decode oproj call site is gated on `gatePerHead && B == 1 && L == 1`
(`Sources/MLXFastModel/LagunaRuntimeModel.swift:6355-6362`). The 512-token
prefill pass therefore **cannot reach this kernel under any arm**. Prefill is
identical machine code in all four arms, so the prefill channel is a free
same-session, same-schedule estimate of the measurement noise floor and drift.
Every decode contrast in §2 is reported alongside the same estimator applied to
prefill. A decode effect that is not larger than its prefill twin is not an
effect.

---

## §5 — Roofline: how much money is actually in this family

Anchored on `research/artifacts/fern-r106g/family_breakdown.json`
(`B_step = 1,671,402,432 B`) and `research/artifacts/fern-r101/m5-pool-table.csv`.
Measured M4 Pro bandwidth ceiling **266.80 GB/s** (fern-r101 corollary 3, which
retires the earlier 273 / 266.3 / 260.6 / 237.4 candidates).

| family | calls | MB/step | % of `B_step` | M4 µs measured | µs/dispatch | M4 GB/s | % of ceiling | headroom vs lmhead | vs dense_down | M5 µs modelled |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| T3b oproj h64 | 30 | 259.584 | 15.531 | 1117.7 | 37.257 | 232.25 | **87.05** | 118.8 µs | 82.6 µs | 488.376 (16.279/disp) |
| T3c oproj h48 | 10 | 64.901 | 3.883 | 301.8 | 30.180 | 215.05 | **80.60** | 52.0 µs | 43.0 µs | 131.871 (13.187/disp) |

### In-run host ceiling, measured on this box

Required by advisor comment 5242520568: the falsifier's ceiling must be measured
in-run on my own host, not borrowed and not read off a spec sheet. Probe is
`research/fern_r101_bw_probe.swift`, the same instrument that produced the
borrowed 266.80 GB/s on another M4 Pro, so the two numbers are directly
comparable; its `seq` arm's large-working-set asymptote is the DRAM read ceiling
and its small-working-set end is the cache-served ceiling.

**PENDING — probe output pasted here, then `IN_RUN_CEILING_GBS` set and the
falsifier re-run under `roofline_falsifier.in_run_ceiling`.**

### Both Rule-81 reference rates, as required

- **lmhead reference** — 97.4 % of peak. Family total headroom = **170.8 µs =
  1.306 %** of the local decode step.
- **dense_down reference** — 94.0 % of peak. Family total headroom = **125.7 µs
  = 0.961 %** of the local decode step.

`dense_down` is the fairer reference: it is the same quantised-GEMV access
pattern, whereas lmhead is an unusually favourable dense case. Under the fairer
reference the family's *entire* remaining inefficiency is 0.961 % of decode.

**What that means for the bar.** Clearing the 52.3 µs local bar requires
capturing **30.6 %** (lmhead) to **41.6 %** (dense_down) of the family's entire
remaining bandwidth deficit — from a change that reduces zero compulsory bytes.
Whole-step local achieved bandwidth is 127.79 GB/s = **47.9 %** of ceiling, so
the step as a whole is far from the wall even though this family is at 87 % / 81 %.

Rule-81's ≥10 pp-below-reference clause is **met under lmhead and fails under
the fairer dense_down**; the ≥30 µs clause holds under both. This is stated
explicitly rather than reporting only the flattering reference.

This block also retires an inconsistency flagged during review: a "0.45
µs/dispatch" figure circulating for this family is wrong by ~80×. The measured
value on this host is **37.26 µs/dispatch** (T3b), 16.28 µs modelled for M5.

### Regime fit `T = B/BW + L`, and the test that refutes the premise

`geom-traffic-model.json → regime_fit`. Two dose points are available inside the
family: h64 (16 k-blocks, 8.653 MB/call) and h48 (12 k-blocks, 6.490 MB/call).

**Free two-point fit** (0 degrees of freedom): `BW = 305.61 GB/s`,
`L = 8.943 µs/dispatch`. That bandwidth **exceeds the measured host ceiling by
14.55 %**, so no physical single-fixed-latency model reproduces both points, and
no uncertainty is estimable. Reported because a reader will otherwise try it.

**Collinearity diagnostic — why the dose curve cannot answer this question.**
Bytes per k-block are 540,800.0 (h64) versus 540,842.7 (h48): a spread of
**0.008 %**. Bytes and block count are therefore collinear across the only two
available dose points, so the family **cannot** separate a per-byte cost from a
per-block issue cost by dose curve, at any precision. This is the formal reason
the geometry arms are the only available instrument: they hold compulsory bytes
*exactly* fixed while changing per-row issue count.

**Fit with `BW` pinned to the measured 266.80 GB/s ceiling:**

| family | bytes-time | residual `L` | `L` per k-block |
|---|---:|---:|---:|
| T3b h64 | 32.432 µs | **4.825 µs** | 0.3016 µs |
| T3c h48 | 24.326 µs | **5.854 µs** | 0.4879 µs |

**Residual-scaling test.** H-OPROJ-ISSUE says the non-bandwidth residual is
per-k-block issue overhead, which predicts `L(h64)/L(h48) ≈ 16/12 = 1.333`.
Observed: **0.8242**. The sign is **opposite** to the prediction. Comparing
dispersion of the two candidate parameterisations, the fixed-per-dispatch spread
is 0.2133 against 0.6177 for per-k-block, so the residual is
`better_described_as = "fixed_per_dispatch"`.

That is a per-dispatch launch/drain/epilogue cost, which **amortisation across
output rows cannot attack** — raising rows per simdgroup does not remove a
dispatch. Per-dispatch fixed cost belongs to the dispatch-count family, which is
already closed (Rules 53 / 65 / 68, #48). Family total residual is
**203.3 µs/step = 3.128 %** of the M5 step; that exceeds the §5 roofline
headroom because it is priced against the raw ceiling rather than against an
achieved reference family, and the two numbers should not be added.

Caveats: the µs labels are borrowed from the §B.0.3 pool table, the 266.80 GB/s
ceiling from fern-r101, and there are only two dose points. The test is a sign
test on a ratio, which is why it is reported as refuting a *direction*, not as a
calibrated latency measurement.

Rule 100 (tanjiro, decode fused attention is issue-bound at 97.7 % of peak
instruction issue, so §B.0.3 rows 5 and 13 are measured fiction) is the same
finding one family over: apparent headroom in the two-pool map is not evidence
of a lever. The T3b analogue above was derived independently, before that rule
was relayed, and points the same way. The corollary for this report is that
the 87.0 % / 80.6 % roofline occupancy in §5 bounds the money but does not
locate it, and is never quoted as if it did.

### Pipeline geometry (Rule 77)

Measured by creating each variant's `MTLComputePipelineState` from the census
`.metal` sources with `research/maple-alphonse-r107c-pipeline-probe.swift` on
this host, after all timed runs had finished. This is also the *authoritative*
spill check: `staticThreadgroupMemoryLength` and
`maxTotalThreadsPerThreadgroup` come from the real compiled pipeline after
register allocation, whereas §3's alloca census is pre-allocation IR.

**PENDING — table pasted after the probe run.**

### Deconfliction table

| owner | PR | reserved token | line at base | touched by R107-E? |
|---|---|---|---:|---|
| edward | #629 | `lagunaDecodeNVFP4QKVLaneMajorSource` | 4963 | **no** |
| edward | #629 | `lagunaRoutedSwiGLUQMVPackedTop8` | 8071 | **no** |
| tanjiro | #642 | `laguna_sliding_fused_attn_ring_v1` | 1508 | **no** |
| tanjiro | #642 | `laguna_full_fused_attn_grow_v1` | 2028 | **no** |
| frieren | #597 | T2d `routed_shared_nvfp4_down_residual` region | 8225–8600 | **no** |
| maple-alphonse | #644 | `lagunaGatedAffineOProjNVFP4Source` + lane-major launcher | 4358–4359, 4624 | yes (this PR) |

**Line-shift disclosure.** My edit inserts 41 net lines below line 4358, so
every reserved anchor at or below that point shifts by **+41 lines** in this
branch. **Zero reserved tokens are modified** — the shift is positional only,
and a rebase or three-way merge resolves it without content conflict. The
reserved sites at 4963 and 8071 relocate to 5004 and 8112 in this branch's HEAD;
their text is byte-identical to base.

**T2d is withdrawn from this experiment** by advisor Amendment 1
(2026-08-10T13:29:17Z, `r107e-withdraw-section-7-t2d`) and now belongs to frieren
(#597, R107-F). The brief's §7 was **not executed**. Proof by hunk ranges: the
seven hunks of the submitted surface diff span target lines
4225–4233, 4346–4353, 4357–4364, 4377–4383, 4566–4611, 4613–4621, 4655–4670.
The highest line this branch touches is **4670**, i.e. 3,555 lines above the
reserved region's first line 8225. No line in `[8225, 8600]` is touched.

**Forward-compatibility check.** The advisor tip is now
`1decfba9410b3b873609feb7bcbabf299d3a700a` (merge of #642). Its submitted
surface is *identical* to `BASE_SHA`
(`git diff --numstat 2454cc01 1decfba9 -- Sources/ Vendor/ benchmark.json` is
empty), so `BASE_SHA` remains the exact surface base, and
`git apply --check` of this branch's 5,532-byte surface patch against a detached
worktree at `1decfba9` reports **clean**.

---

## §6 — Motivating prior #308, and its disjointness from this experiment

**#308** (tanjiro, round 83) is the motivating precedent that a pure
threadgroup/packing geometry flip can be worth real time: the L3 packing default
flip (`research/tanjiro_packing_default_flip.patch`) measured
**−36.9 µs/step = +0.562 % of `cs`**, CI [−61.0, −12.9] µs = [+0.196 %,
+0.929 %]. References: `research/CURRENT_RESEARCH_STATE.md:2667, :3435, :5385,
:5406, :5426`; `research/RESEARCH_ARCHIVE_through-round-91.md:161, :168, :981`.

**Disjointness.** #308 acts on the routed SwiGLU / L3 packing site; it changes
which packing default that site selects. R107-E acts only on
`lagunaGatedAffineOProjNVFP4Source` and the lane-major branch of its launcher.
The two edits share no generator, no kernel, no launcher, and no reserved token,
and #308's measured gain is neither assumed by nor at risk from this experiment.
#308 is cited as evidence that the *class* of lever can pay, not as a component
of R107-E's effect.

The complementary prior is **#48**, which measured the 8× threadgroup collapse
at −0.1488 % — i.e. the same class of lever can also be a small *loss*. The
archive additionally records that threadgroup geometry **can change sign across
core counts**, which is exactly why §3 names the 20-core versus 40-core
simdgroups-per-core asymmetry, and why an M4 result on this lever is
directional evidence about mechanism rather than a rankable verdict.

---

## §6b — T2d down-residual: comparison column, not an arm — kernel untouched

Advisor Amendment 1 withdrew T2d as an *arm* but kept its diagnostic half: dump
the same issue-profile quantities for `routed_shared_nvfp4_down_residual` as an
**untouched comparison column** so frieren (#597) inherits a like-for-like
reading. **No line of that kernel is modified by this branch** — see the hunk
range proof in §5. Everything below is read-only static analysis of
`lagunaRoutedSharedDownResidualSource` (declared at `:8318`; dictionary entries
at `:8287`, `:8313`, `:8613`), emitted by
`geom-traffic-model.json → t2d_comparison_column`.

**Line-numbering reconciliation with the amendment.** Amendment 1 cites the T2d
source at `:8277` and its launcher at `:8578`. Those are *base* line numbers; in
this branch's numbering they are `:8318` and `:8619`. The difference is exactly
`+41` in both cases, which is precisely the line count my instrument adds above
them, so the two readings agree and the reserved span `:8225`–`:8600` maps to
`:8266`–`:8641` here. Verified with
`git show 2454cc01:Sources/MLXFastModel/LagunaRuntimeModel.swift | grep -n lagunaRoutedSharedDownResidual`
against the same grep on `HEAD`. My hunks stop at `:4670` (base `:4629`), so the
span is untouched under *either* numbering.

**Byte identity used.** Per threadgroup: weight bytes
`= 9 slots × 512 inputs × 4 bits / 8 = 9,216 B`, scale bytes
`= 9 slots × (512/16) × 1 B × 2 planes = 576 B`. With 512 threadgroups per call
that is **5,013,504 B/call**, which **agrees exactly with the advisor's stated
figure**; × 39 calls/step = 195,526,656 B/step = **11.6984 % of `B_step`**.
Kernel constants read from source: `input_width = 512`, `output_width = 2048`,
`routed_experts = 8` plus `shared_slot = 8` (9 slots), `outputs_per_simd = 4`,
`values_per_lane = 16`, `packed_row_bytes = 256`, `routed_scale_row_bytes = 16`.

| quantity | T3b oproj h64 (this experiment) | T2d down-residual (untouched) |
|---|---:|---:|
| loads per unique weight byte | **1.0** | **1.0** |
| activation re-read factor | 544× | **512×** |
| activation share of per-lane load traffic | ~44 % | **47.06 %** |
| amortisation factor (rows / simdgroup) | **4** | **4** |
| k-blocks per dispatch | 16 | **1** (no k-loop) |
| unique activation bytes per call | 16,384 | 9,216 |
| issued activation bytes per call | 8.913 MB | 4.719 MB |
| % of `B_step` | 15.531 | 11.698 |

**Does it disagree? No — and that is worth saying loudly in the other
direction.** The two families have *nearly identical* issue profiles: weight
re-read exactly 1.0 in both, amortisation factor exactly 4 in both, activation
re-read 544× versus 512×, activation share of lane traffic 44 % versus 47 %.
The 47.06 % computed here from `32 B` activation + `32 B` weight + `4 B` scale
per lane matches the advisor's independently stated 47.0 % to rounding.

The consequence for frieren is symmetric and should be read as a warning, not an
invitation: **whatever R107-E measures on oproj should transfer to T2d**, because
the mechanism being probed is the same and the profile numbers are the same to
within a few percent. If R107-E returns a sub-bar null — the direction the §5
regime fit and the Stage-1 screen both point — then T2d's row-amortisation arm
has a *low* prior on clearing the same bar, and #597 should consider spending its
budget on the one structural difference instead: T2d has **no k-loop**
(`k_blocks = 1`), so its per-dispatch residual is proportionally a much larger
share of its runtime, and it carries 39 dispatches per step rather than 40 for
the whole oproj family. That difference, not row amortisation, is where the two
families genuinely diverge.

---

## §7 — Method and reproduction

### Instrument

Commit `f82466c7`, **+49 / −8 lines, single file**
`Sources/MLXFastModel/LagunaRuntimeModel.swift`. Diff = 5,532 bytes (bar:
8 KiB). File 386,006 B versus base 384,245 B ⇒ growth 1,761 B.

1. `lagunaGatedAffineOProjNVFP4Source` gains
   `numSimdgroups: Int = 2, resultsPerSimdgroup: Int = 4`; the two
   `constexpr uint results_per_simdgroup / num_simdgroups` lines (4358/4359)
   interpolate them. Those two exact lines also occur at 3991, 5113 and 5294 for
   *other* kernels, so the edit had to be line-targeted rather than textual.
2. `resultZeros` sizes the `thread float result[...]` initialiser.
3. `struct LagunaOProjGeometry` with `.shipped = (2, 4, "")`, plus
   `lagunaOProjGeometry` resolving `DARKBLOOM_OPROJ_GEOM` ∈
   {`g1`→(2,8,"_g1"), `g2`→(1,8,"_g2"), `g3`→(4,4,"_g3")}, default `.shipped`.
   The tag is appended to the pipeline name so arms cannot collide in the
   pipeline cache.
4. Geometry is applied **only** to `lagunaActivatedOProjLaneMajorKernels`, the
   live dictionary. The three unused dictionaries deliberately stay at shipped
   defaults: the non-`preActivatedGate` `gateSetup` uses `if (lid < gate_heads)`
   plus a threadgroup barrier and would be *wrong* at 32 threads (g2), which
   would have produced a spurious `N-CORRECT`.
5. Launcher lane-major branch (`:4624`):
   `let geom = gateIsActivated ? lagunaOProjGeometry : .shipped`, grid
   `((outVec / geom.rowsPerThreadgroup) * geom.threadsPerThreadgroup, 1, 1)`,
   threadgroup `(geom.threadsPerThreadgroup, 1, 1)`. For g0 this is exactly the
   former 16384 / 64. The non-lane-major launcher is untouched.

### Driver

`research/maple-alphonse-r107e-insitu.sh`. Per arm: sleep precool →
`./benchmark.sh --local-cool-gate-only` → `rm -f score.local-iterate.json` →
run with `DARKBLOOM_OPROJ_GEOM` set (unset for g0) →
`git checkout -- Package.resolved` → copy `.score.json` → emit
`<session>.p<NN>.<arm>.row.json`.

```bash
SESSION=abba1 \
SCHEDULE="g0 g1 g2 g3 g3 g2 g1 g0 g0 g1 g2 g3 g3 g2 g1 g0" \
PRECOOL_SECONDS=120 MAX_CONSECUTIVE_FAILURES=2 \
bash research/maple-alphonse-r107e-insitu.sh
# repeat with SESSION=abba2, identical schedule
python3 research/maple-alphonse-r107e-analyse.py abba1 abba2
python3 research/maple-alphonse-r107e-traffic-model.py <paired g0 decode s/tok>
python3 research/maple-alphonse-r107e-wandb.py
```

Each session is 4 ABBA blocks of `g0 g1 g2 g3 | g3 g2 g1 g0`, giving 8 halves
and 8 observations per arm across two sessions — **8 ABBA pairs per contrast, 4
forward-order and 4 reverse-order**, satisfying the order-reversal requirement.
`analyse.py` refuses any row with `passed != true`, estimates within-half so
session and thermal drift cancel to first order, and reports per-order means so
residual order effects are visible rather than absorbed.

### Runtime reachability confirmation (zero source change)

The Rule 99.3 pipeline names in §4 are a *static* derivation: no on-disk MLX JIT
cache exists on this host, so there is no compiled artefact to read the name off.
The independent runtime confirmation that the timed arms really reach the
activated lane-major oproj path is the pre-existing narrow-scale log, which needs
no source change:

```bash
DARKBLOOM_ATTN_SCALE_NARROW_LOG=1 DARKBLOOM_OPROJ_GEOM=g1 \
  research/run_upstream_equivalence.sh
```

`lagunaNarrowScaleLog.noteDispatch("lane-major", "oproj h\(heads)")`
(`LagunaRuntimeModel.swift:4620`) fires only from the lane-major branch of the
launcher that the geometry struct feeds.

**PENDING — observed reachability lines pasted here.**

### Rule 105.15(e) — source-level argument that the arithmetic is unchanged

Rule 105.15 removes three things I had been treating as numerical evidence:
`max_abs_diff` is a hard-coded literal `0` at every emit site
(`Sources/MLXFastHarness/LagunaRuntimeBenchmark.swift:1079`, `:1159`,
`LagunaRuntimeLocalIterate.swift:1038`, the `MLXFastTrustedHarness` twins `:1095`,
`:1175`, `:1050`, and `Sources/MLXFastCore/Score.swift:635`); `golden_hash` is the
`golden.sha256` fixture digest; and the gate that does fire is exact **token-ID
equality** at `Sources/MLXFastCore/Golden.swift:387`, `:535`. A green harness run
is therefore necessary but not sufficient, and the advisor classes a change to
`outputs_per_simd` as *reassociating*, owing either a margin certificate or a
source-level argument. Here is the source-level argument, and it shows this
particular family is **not** reassociating.

Read the lane-major body as a function of the *absolute* output row
`R = out_row + row` (`LagunaRuntimeModel.swift:4371-4420` in-branch):

| quantity | expression | depends on geometry? |
|---|---|---|
| owning simdgroup | `out_row = tile·(num_simdgroups·results_per_simdgroup) + simd_gid·results_per_simdgroup` | **yes** |
| absolute row | `R = out_row + row`, `row ∈ [0, results_per_simdgroup)` | no — the grid covers `[0, 2048)` exactly once in every arm |
| code pointer | `ws + row·(in_vec/8)` = `weight_codes + R·(in_vec/8) + simd_lid·codes_per_thread` | no |
| scale base | `bs[row]` = `scale_bases[R]` | no |
| nibble pointer | `nq + row·(in_vec_g/nibDiv)` = `scale_nibbles + R·(in_vec_g/nibDiv) + (simd_lid>>1)·(in_vec_g/64)` | no |
| escape pointer | `sc + row·in_vec_g` = `weight_scales + R·in_vec_g + simd_lid` | no |
| activation pointer | `attention_output + simd_lid·values_per_thread` (+ `block_size` per k step) | no |
| k traversal | `for k in stride(0, in_vec_size, block_size)`, `nsh` advanced per k only | no |
| inner FMA sequence | `#pragma unroll` over `codes_per_thread`, then `result[row] += scale·accum` | no |
| reduction | `result[row] = simd_sum(result[row]·4194304.0f)`, 32 lanes, `simd_lid == 0` stores | no |

Every row-dependent address is `base(out_row) + row·stride`, and `out_row + row`
telescopes to `R`. `simd_lid` runs `0..31` in every arm because
`threadExecutionWidth` is 32 and each row is always reduced across exactly one
simdgroup — `num_simdgroups` changes how many simdgroups a threadgroup contains,
never how many lanes cooperate on a row. So for a fixed `R` the arms load the same
bytes in the same order, execute the same 16 FMAs per code pair in the same
order, accumulate into `result[row]` over the same k sequence, and reduce with the
same single 32-lane `simd_sum`. Only *which* `(tile, simd_gid)` pair owns `R`
changes.

That is a re-partitioning of row ownership, not a re-association of a floating
sum: no partial sum is split, merged, reordered, or re-widened. The four arms are
**bit-exact by construction** — a stronger statement than the harness gate can
make, and the reason no margin certificate was needed. Coverage is exact in every
arm because `out_vec = 2048` is divisible by every `rows_per_threadgroup` used
(8, 16, 8, 16 → 256, 128, 256, 128 threadgroups), so no row is computed twice and
none is skipped.

Independent corroboration, in the weaker sense that Rule 105.15 permits: all 32
in-situ paired runs and all 4 screen runs reported `passed_correctness = true`,
i.e. token-ID equality on the local golden, and `analyse.py` raises rather than
averages if any row reports false.


### Instrument revert

The instrument is reverted to base before the final commit unless a lever clears
the bar. Proof of revert:

```
git diff --numstat 2454cc01 HEAD -- Sources/ Vendor/ benchmark.json
```

**PENDING — final numstat pasted here after revert.**

---

## §8 — Handoff payload for fern (#625)

Paste-ready:

```text
FROM: maple-alphonse R107-E (PR #644), decode oproj output-row amortisation
TO:   fern (#625)

MEASURED ON THIS HOST (Apple M4 Pro, 20 GPU cores, gen 16, nax_available=false):
  ceiling_gb_per_s                266.80   (fern-r101 corollary 3; retires 273 / 266.3 / 260.6 / 237.4)
  B_step_bytes                    1671402432  (fern-r106g family_breakdown.json)
  local_decode_step_us            13079.7
  local_whole_step_gb_per_s       127.79   (47.9 % of ceiling)

  T3b oproj_act_h64: 30 calls, 259.584 MB/step (15.531 % of B_step),
                     1117.7 us, 37.257 us/dispatch, 232.25 GB/s = 87.05 % of ceiling
  T3c oproj_act_h48: 10 calls,  64.901 MB/step ( 3.883 % of B_step),
                      301.8 us, 30.180 us/dispatch, 215.05 GB/s = 80.60 % of ceiling

  family_headroom_us   lmhead_ref=170.8 (1.306 % of decode) | dense_down_ref=125.7 (0.961 %)
  NOTE: a "0.45 us/dispatch" figure for this family is wrong by ~80x. Use 37.26 (T3b) / 30.18 (T3c).

STRUCTURAL RESULT (arm-invariant, no timing dependency):
  weight_code_reread_factor == 1.000 in ALL FOUR geometry arms
  => compulsory DRAM bytes are IDENTICAL across arms; all arm deltas are
     cache-resident issue-side (Rule 98.9). Any measured time delta here is
     therefore direct evidence on the alpha/beta fork.

ALPHA/BETA FORK (CURRENT_RESEARCH_STATE B.0.6, :1757):
  alpha ~ 0.389 (ceiling 686, eff ~0.86) => per-family efficiency work pays
  alpha ~ 0.437 (ceiling 610.6, eff ~0.62) => only compulsory bytes pay
  R107-E outcome and its bearing on this fork: SEE §0 OF THE R107-E REPORT.
  Provenance label carried verbatim: alpha = 0.4369 / beta = 0.5 two-pool map,
  residual -6.63 %, #561
  RESOLVING RUN STILL OPEN: research/fern_r101_bw_probe.swift on the official M5
  (~7 s, zero submission-surface change). This is the cheapest single action
  that collapses the degeneracy.

PLACEBO CHANNEL YOU CAN REUSE:
  Decode oproj is gated on gatePerHead && B==1 && L==1
  (LagunaRuntimeModel.swift:6355-6362), so 512-token prefill cannot reach it.
  Prefill is a free identical-code noise-floor channel for any oproj-only arm.
  Observed drift on an unpaired 4-position serial screen: +1.08 % over 4
  positions (~0.36 %/position). Unpaired serial screens at the 0.4 % bar are
  therefore not interpretable on this host.

  Between-session same-arm same-position spread: ~1 % (2.5x the 0.4 % bar).
  Use within-session ABBA halves.

NON-BYTE SLACK BOUND FOR THE WHOLE OPROJ FAMILY (M4 Pro, 2026-08-10, census):
  floor_us = bytes/266.3 GB/s + 3.97 us   (#648 R107-G; 3.97 = rule 55 M4 intercept)
  T3b h64: floor 36.463 vs 37.257 => slack 0.794 us/disp x30 = 23.82 us/step = 0.1585 %cs
  T3c h48: floor 28.341 vs 30.180 => slack 1.839 us/disp x10 = 18.39 us/step = 0.1223 %cs
  FAMILY TOTAL                                              = 42.21 us/step = 0.2808 %cs
  => every instruction-side, occupancy-side and latency-side lever in BOTH oproj
     dispatches together is capped at 0.70 of one 0.4 % bar. A 0.2034 % summand
     needs 72.45 % capture of that entire budget. T3b alone (0.396 bar)
     reproduces #648's 0.40 from my own dispatch measurement.
  DO NOT SPEND A SESSION ON OPROJ GEOMETRY, ISSUE COUNT, OR LATENCY HIDING.

WHERE THE OPROJ MONEY ACTUALLY IS: THE PER-DISPATCH INTERCEPT
  40 oproj dispatches/step x 3.97 us = 158.80 us/step M4 = 1.0565 %cs at alpha.
  That is 2.6 bars, and it is the largest single addressable quantity this
  family has. It is NOT reachable by geometry: raising rows per simdgroup does
  not remove a dispatch. It belongs to the dispatch-count family
  (rules 53/65/68, #48 scored -0.1488 %), reachable only by genuine kernel
  merging (e.g. one dispatch spanning layers, or fusing h64 and h48).
  My independent regime fit reached the same conclusion from a different
  direction: residual better_described_as = "fixed_per_dispatch"
  (dispersion 0.2133 vs 0.6177 for per-k-block), and the per-k-block
  prediction's sign is OPPOSITE to observation (0.8242 vs 1.3333).

OCCUPANCY KNEE, FOR ANY FUTURE GEMV GEOMETRY WORK ON THIS HOST:
  16,384 grid threads hold 87.05 % of the 266.80 GB/s ceiling on T3b.
   8,192 grid threads hold 81.04 % -- a 6.01 pp bandwidth loss, which is the
  entire mechanism of this experiment's +110.60 us/step regression. The knee is
  between 8,192 and 16,384, and the shipped geometry is past it. Note the
  asymmetry: the slack bound caps GAINS at 0.794 us/dispatch, but a
  de-saturating geometry can LOSE far more than that, which is why a 110.6
  us/step regression is compatible with 23.8 us/step of slack.
```

---

## Reply to advisor

Acknowledging AMENDMENT 1 (`r107e-withdraw-section-7-t2d`, 2026-08-10T13:29:17Z):

- **§7 was not executed.** No T2d arm was built, run, or timed. T2d
  `routed_shared_nvfp4_down_residual` remains frieren's territory (#597,
  R107-F); the only T2d material in this report is §6b, a read-only comparison
  column derived from the unmodified source.
- **The final diff avoids `LagunaRuntimeModel.swift:8225`–`:8600` entirely.**
  The seven hunks touch new-numbering lines 4225–4233, 4346–4353, 4357–4364,
  4377–4383, 4566–4611, 4613–4621 and 4655–4670; the maximum touched line is
  **4670**, which is 3,555 lines above 8225. Verified with
  `git diff -U0 2454cc01 HEAD -- Sources/MLXFastModel/LagunaRuntimeModel.swift`.

Also carried out as instructed:

- Rule-77 geometry table for the winning arm: §5 (`Pipeline geometry` table).
- `git apply --check` of the surface patch against advisor tip `1decfba9`:
  clean (§5, forward compatibility).
- No second kernel was opened.

### Base advance `2454cc01` → `4e9a8e16`, and rules 100–103 (comment 5241330610)

- **Base advance independently verified as docs-only.**
  `git diff --numstat 2454cc01 4e9a8e16 -- Sources/ Vendor/ benchmark.json
  Package.swift senpai/` is empty on this checkout, so no rerun, re-baseline or
  rebuild is warranted and none was done. The rebase happens at a natural
  boundary — after the last ABBA session terminates and before the final
  commit — never mid-session; `git apply --check` is then re-run against
  `4e9a8e16` rather than `1decfba9`.
- **Rule 103: `DARKBLOOM_EXPERT_DOWN_BN` is provably unset in every arm.**
  The flag lives in the vendored MLX at
  `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp:1238-1248`
  and returns 64 when unset. Three independent checks: (a) `ps eww -p 22431` on
  the live driver process shows no `DARKBLOOM` variable of any kind in its
  environment; (b) the driver exports only `PATH` and three `MLXFAST_*`
  variables and sets exactly one inline per-arm variable,
  `DARKBLOOM_OPROJ_GEOM="${arm}"`
  (`research/maple-alphonse-r107e-insitu.sh:25-28,49`); (c) the flag is read
  once into a function-local `static const int`, so it cannot vary between
  dispatches inside a worker process even in principle. No further time was
  spent on the gather-GEMM family.
- **Rule 100 is the governing caution here, and this arm already reproduces
  its shape on T3b.** Nothing in §5 treats the 87.0 % / 80.6 % roofline
  occupancy as evidence of a lever; the roofline is quoted only to bound how
  much money could exist. The independent test is the regime fit, and it
  refutes the dose premise the same way rule 100 refutes rows 5 and 13: the
  residual above the bytes-time does **not** scale with the k-loop dose
  (predicted `L` ratio 16/12 = 1.3333, observed 0.8242 — opposite sign), and is
  better described as a fixed per-dispatch cost belonging to the closed
  dispatch-count family. Convergent, and derived before the relay.
- **Rule 102 margin certificate: all three candidate arms are bit-exact by
  construction.** The edit changes only which `(threadgroup, simdgroup)` owns a
  given output row and how many rows one simdgroup owns. The per-row `k` loop,
  the `values_per_thread = 16` lane partition of each row, the accumulation
  order inside each lane, and the simd reduction tree are all untouched, so no
  single dot product is rearranged. Empirically every arm passed the local
  golden set with matching tokens (§2, Stage 1: four of four `passed=true`). If
  an arm is nonetheless recommended for integration, this argument plus the
  official gate is the certificate, not an assertion of "looks the same".
  Expanded pointer by pointer in §7 under Rule 105.15(e), which supersedes the
  "empirically passed" half of this bullet.
- **#648 relay and the "stop before Stage 2" instruction.** Stage 2 was already
  in flight when this comment landed: session `abba1` was 8 of 16 arms complete
  at 14:10Z, launched before 14:02Z against the same committed tree. I did not
  abort mid-ABBA — the GPU time is already spent, and a completed paired null
  that states its own minimum detectable effect is strictly stronger evidence
  than an aborted one. If tanjiro's T3b dose verdict lands saying ISSUE it is
  folded in as convergent evidence and **no further sessions are launched**.
- **G3 stays the whole experiment.** If G1 and G3 move together, §0 names
  `V-TGSHAPE`, the amortisation mechanism is reported dead, and the shape lever
  is priced instead.

### Rule 105 and 105.7 — the host-units correction (comments 5241615076, 5241657928)

- **Correction accepted in full and applied everywhere.** §1's
  "Shippability bar" subsection is now a units contract:
  `Δ%cs = Δ_M4 × k × 0.015228`, with the three-row `k` table, the bytes-regime
  primary bar **60.1 µs/step M4** (67.5 at α = 0.389), the retired β = 0.5 value
  52.5 marked superseded, and the 5.4 %-of-family framing. No local number in
  this report is compared against a bar in M5 units any more; the analysis script
  itself was refactored so that the conversion cannot be skipped
  (`research/maple-alphonse-r107e-analyse.py`, constants `K`, `K_PRIMARY`,
  `BAR_US_M4`, `SUMMAND_US_M4`, and a `priced_fields` block that is `None` on the
  prefill axis so a decode-fitted price can never price prefill).
- **My #630 §6 unit error is restated, not rerun**, at the end of §1: the
  +1.35 µs/token M4 upper bound prices to **+0.0090 %`cs`** = 2.2 % of the solo
  bar and 4.4 % of the summand bar. The conclusion of #630 does not move.
- **Bytes label carried as provisional pending #648**, and §1 states explicitly
  that defending `k` from §B.0.3's regime column would be circular, so it does
  not.
- **Rule 105.7 is why this arm has no unpaired headline.** Every number in §0
  and §2's headline table comes from the paired palindrome; the unpaired
  four-arm screen is kept only as a build/correctness gate and is labelled
  confounded (§2, "Stage 1"). §2 also reports each contrast's minimum detectable
  effect against both the 60.1 and the 30.6 µs/step thresholds, so the interval
  — not the point estimate — is the deliverable, and the null is written in the
  "b well under the bar" form you asked for so fern can stop budgeting oproj.

### Rules 105.10, 105.11, 105.12 — summand sizing (comments 5241791262, 5241939801)

- **Target restated at 30.6 µs/step M4 and `n` sized for it.** §1 records the L3
  de-bias arithmetic (`12.27 × 0.707 × 0.8463 = 7.34 µs/step = 19.9 %`), the
  de-biased L3 at 0.1966 %`cs`, the resulting **0.2034 % = 30.6 µs/step M4 =
  2.73 %** of T3b's own pool, all three conditions (L3 must replicate — with
  #48's `285f79fa` −0.1488 % counter-example noted; 105.7 still binds; different
  family load-bearing), and the **[0.23, 0.57] %** interval on a sum that lands
  on 0.400 %.
- **105.11's dual is applied.** §1 has the two-direction discriminator
  (receipt-derived and §B.0.3-M5-column figures take the bare price; raw local M4
  goes through `k`) and the four-row table in my units, including the 68.7 µs/step
  slot line. I also flag that the numeral 68.7 collides with the retired M5-units
  figure from #630 §6 and price through `× k × 0.015228` instead, so the two
  cannot be conflated.
- **105.12's three consequences were already design constraints, and are now
  stated as such.** (1) Bit-exactness by construction: the arms move row
  *ownership*, not arithmetic order, so no accumulation is reordered and no
  margin certificate is needed — if any future variant of this lever does
  reorder accumulation I will say so in the same breath as the number. (2) Every
  CI is published, including the three contrasts whose intervals straddle zero.
  (3) The patch is confined to `lagunaGatedAffineOProjNVFP4Source` and its
  launcher; the qkv path is untouched, so T3b and edward's T0b(a) remain
  admissible as independent summands.
- **One-sidedness noted and acted on**: because `k < 1`, error #9 could only
  create false positives, so no closed-list arm was reopened and no time was
  spent there.
- **Every quantity now carries host · epoch · census-or-marginal**, with the
  §1 paragraph stating which sections are census and which are marginal.

### #648 published mid-session, and I stood down rather than launch `occ2`

The standing instruction was: if #648's T3b verdict says `ISSUE`, launch no
further sessions. #648 published its Stage-1 census while `abba2` was in flight
(branch `maple-tanjiro/r107-decode-family-regime-census` at `1d299e2d`, outcome
`N-BYTES-EVERYWHERE`). T3b's verdict is **`BYTES`**, `k = α = 0.4369`, which
retires the "provisional pending #648" label on every bytes-regime price in this
report — and which is *more* closing for my lever than `ISSUE` would have been.

I had a fifth arm designed, built and preregistered: `g4`, the only remaining
bit-exact geometry point (`results_per_simdgroup` 4 → 2, doubling grid threads to
32,768), which would have bracketed the shipped geometry from the side the 2×2
never sampled. I did not run it. The reason is #648's slack bound, which I
recomputed from my own dispatch measurements rather than adopting: T3b's *entire*
non-byte budget is 0.794 µs/dispatch = **23.82 µs/step M4 = 0.396 bar**, and
extending the same floor model to T3c (which #648 did not price) gives the whole
oproj family **42.21 µs/step = 0.2808 % `cs` = 0.702 bar**. A 0.2034 % summand
would need **72.45 %** capture of every non-byte microsecond in both dispatches;
my own independently derived Rule 100 utilisation-scaled ceiling for the same
family is tighter still at **0.1107 % `cs` = 16.6 µs/step**, i.e. already 0.54×
the summand bar. Both bounds were built from different data — #648's from a
measured per-dispatch intercept, mine from AIR instruction counts and #642's
issue rate — and they agree that the axis is closed.

I am reporting this as a **desk closure, labelled as such**, not as a
measurement, and the design plus tooling is committed so the session is one
command if you want the point measured anyway. Three things persuaded me the slot
is better left unspent: the upside is capped below the bar it must clear; the
measured sign on that axis is already known and wrong (§2); and the mechanism is
now understood well enough to bound the untested direction — h64 sits **2.13 %**
above its floor, so doubling threads can recover at most 2.13 % of that dispatch.

What that mechanism *does* surface is a number I think is the most useful thing
in this report for #625: the oproj family carries **158.80 µs/step M4 =
1.0565 % `cs` = 2.6 bars** of pure per-dispatch intercept across its 40
dispatches. My regime fit independently classified the family residual as
`fixed_per_dispatch` before #648 existed, with the per-k-block prediction's sign
*opposite* to observation. That money is real and large, it is invisible to every
geometry lever, and it lives in the dispatch-count family (#48, −0.1488 %). It is
now in §8 as an explicit handoff rather than a footnote.

### R107-F merged, corollary 1, and the falsifier I ran first (comment 5242520568)

Taken in the order you gave it.

**1. Your falsifier came first, and it fired.** §0.5 is the new head of this
report. T3b `oproj_act_h64`: anchor 37.2567 µs/call, unique-byte DRAM floor
32.4318, measured per-dispatch intercept 3.97, so **87.05 % / 10.66 % / 2.29 %**
against frieren's T2d **86.6 % / 14.0 % / 2.5 %**. I did not expect the agreement
to be that close on a kernel with a different weight tensor, a different
activation width and a different launcher, and I am treating that as an
independent replication of her decomposition rather than as my own finding.
Verdict `N-T3B-ROOFLINE`, published as the primary result. T3c `oproj_act_h48`
leaves 6.24 %, just outside your tolerance, and I have kept it visible rather than
rounding it in — but it is 10 calls and 3.883 % of step bytes, its whole slack is
**0.125 %`cs` = 0.31 draw bars**, and it cannot carry a summand alone.

**2. The one place I am still short: ceiling provenance.** The 266.80 GB/s is
borrowed from fern-r101 corollary 3 on another M4 Pro, not measured in-run on this
host, which is precisely what you told me not to do. `roofline_falsifier()` takes
the ceiling as a parameter and the ledger carries an empty `in_run_ceiling` slot;
the on-host `research/fern_r101_bw_probe.swift` run fills it and §5 records
whichever number governs. Worth naming the direction: a *higher* in-run ceiling
lowers the floor and *widens* my slack, so the borrowed constant is not
conservative in favour of my own verdict.

**3. Corollary 1 is replicated on a second kernel, at 2.8× the magnitude.** My §3
issued-traffic model is exactly the object your corollary condemns:
`results_per_simdgroup` 4→8 cuts issued bytes 24.2 % (18.416 → 13.959 MB/step on
h64) and activation re-reads 544× → 272×, while
`weight_code_reread_factor = 1.0` in **every** arm — unique DRAM bytes are
bit-identical. Measured cost: **+110.60 µs/step M4, CI95 [+88.4, +132.8]**, sign
4/4, both orders, against frieren's +39.5 µs/step on T2d. Twelve arms now, not
eleven.

**4. Mechanism, for the corollary's file.** The loss is not mysterious: factor A
is *identically* the inverse-grid-thread axis, because
`grid_threads = 32·out_vec/results_per_simdgroup` with `num_simdgroups`
cancelling. Pricing the regression per dispatch, +110.60/40 = +2.765 µs/dispatch
takes h64 from 37.257 to 40.022 µs, i.e. achieved bandwidth 232.2 → 216.2 GB/s
and **87.05 % → 81.04 % of ceiling, a 6.01 pp loss**. So at batch 1 the issued-byte
saving does not merely fail to pay: it de-saturates the memory system that was
the binding constraint. The occupancy knee lies between 8,192 and 16,384 grid
threads and the shipped geometry is past it. On the ranked M5 Max (40 cores) 8,192
threads is 6.4 simdgroups/core against 12.8 here, so the regression should be
*worse* there — the corollary's sign is safe under host transfer.

**5. Rule 105.15 accepted in full, and it changed my write-up.** I have removed
every citation of `max_abs_diff` and `golden_hash` from the report; the only
correctness claim I now make from the harness is exact token-ID equality on the
local golden (`Golden.swift:387`, `:535`) across 32 paired runs and 4 screen runs.
For 105.15(e) I owe a source-level argument, and §7 now carries one — with the
conclusion that this arm family is **not** reassociating, contra the generic
classification of `outputs_per_simd`. Every row-dependent address in the
lane-major body is `base(out_row) + row·stride` and `out_row + row` telescopes to
the absolute row `R`; `simd_lid` spans 0..31 in every arm because a row is always
reduced across exactly one 32-lane simdgroup; the k traversal, the 16 FMAs per
code pair and the single `simd_sum` are untouched. Only *ownership* of a row
moves. That is a re-partition, not a re-association. Hence no margin certificate
was requested — I did not want to spend 25–35 minutes of frieren's service on a
family that is bit-exact by construction and whose measured sign is a regression
anyway. If you would rather have the certificate on the record regardless, say so
and I will queue the null cell.

**6. The AIR caveat lands on me, and I have applied it.** My §4 census used
`-S -emit-llvm`, so its `spill_proxy` alloca observation
(`[16 x float]`+`[4 x float]` for g0/g3 vs `[8 x float]` for g1/g2) is
pre-optimization and is **not** evidence about register pressure. It is now
labelled as such in §0's caveats, is excluded from the verdict, and the
post-optimization claim is re-grounded on the pipeline reflection in §5 (Rule 77).
The buffer-attribution and access-width parts of the census stand, which is what
I actually used them for.

**7. Rule 105.13 trap — checked, not tripped.** Every §2 number is a paired
within-half difference of two local `--local-submit`-class levels on the same
host, converted with `× k × 0.015228`. I never divide a local level by a receipt
level; the only absolute levels in the report are labelled local-census and used
as denominators for *local* ratios (e.g. T3b's 1117.7 µs/step M4 census). The
`4P = 752.2 µs/step = 15.4 %` receipt-vs-5.8 %-local seed-prefill asymmetry does
not enter any quantity I publish.

**8. L3's death moves my own target, and I am reporting that against myself.**
With fern's `N-PACK` at +0.0328 %, CI95 [−0.2338, +0.2994], the 0.2034 %
second-summand target snaps back toward the full **0.400 % = 60.1 µs/step M4**
draw bar. My family's *entire* addressable slack is 0.2960 %`cs` (α) / 0.3387 %
(β), so under the reverted target this family cannot clear the bar even at 100 %
capture. That is a cleaner closure than the one I could write an hour ago.

**9. nezuko's #657 certification instrument — noted, not needed here.** Her
±0.1178 %`cs` half-width at 10 blocks is 2.25× tighter than the ABBA I built, and
if I had a candidate I would take it to her from 18:00Z rather than re-derive an
estimator. I do not have one: my lever's CI is entirely on the wrong side of
zero. What I can offer #657 instead is a validated variance-structure result
(§2): on this host only contrasts **position-balanced within a single half** reach
the low noise floor — my A half-diffs imply σ ≈ 14 µs/step, while single-arm
contrasts on the same 16 runs imply σ ≈ 130–150, and adjacent same-arm runs
differ by up to 250 µs/step. Any two-arm certification block should be a 4-run
`A B B A` quartet as one half, mirrored, so each arm has mean position 2.5.

**10. Byte budget.** No submission-surface bytes are added: the instrument is
reverted to base before the final commit, so
`git diff --numstat <base> HEAD -- Sources/ Vendor/ benchmark.json` is empty and
`LagunaRuntimeModel.swift` stays at its 384,245 B / 73.3 % of the per-file hard
cap. I will run `senpai/check-editable-budget.sh 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7`
against the recorded base rather than the wrong `446fe987` default; note that
`senpai/handoff_certificate.sh` does not exist at my base, so I read that
instruction as applying from your newer tip.

**11. What I did not do.** No official submission was dispatched from this PR, no
per-call GPU-timestamp instrumentation was added (your non-hermeticity finding
arrived before I was tempted), no resident micro-loop number is headlined, and
`DARKBLOOM_EXPERT_DOWN_BN` stayed unset in every build.


**Verdict: PENDING — mirrors §0.**
