# r97-c preregistration — two-stage simdgroup-axis split of the two fused decode attention kernels

**Student** maple-nezuko · **PR** #528 · **assignment** `maple-r97-c-attn-two-stage-split`
· **revision** `r97-c-rev1` · **branch** `maple-nezuko/r97-attn-two-stage-split`
· **base** `b78e7cdb80b5ae5f1cb1fdd39803322fb283ae5e` (R93-A / #496 merge)

**Host for all local work** Apple M4 Pro, 48 GiB, `applegpu_g16s` (Apple GPU
generation 16), 20 GPU cores, low-memory startup profile. **Official ranked host
is M5 Max, 40 GPU cores, generation 17.**

**Written and committed before any timing datum for this arm was collected.**
The only measurement that precedes this document is Gate 0 (§1), which the
assignment orders first and which is a *bit-exactness* probe, not a timing
probe. Its numbers are recorded here rather than in the result file so that the
go/no-go bars below can be read against what Gate 0 actually returned.

---

## 0. What the arm claims, in one paragraph

Both fused decode attention kernels launch **one 1024-thread threadgroup per
query-head pair**: 64 sliding heads → **32 threadgroups**, 48 full heads → **24
threadgroups** (`LagunaRuntimeModel.swift:1971–1972` and `:2456–2457`, both
`grid: ((heads/2)*1024,1,1)`, `threadGroup: (1024,1,1)`). The ranked M5 has
**40 GPU cores**. 32 and 24 threadgroups therefore leave 8 and 16 cores idle
for the whole kernel. The arm asks whether splitting the K axis across more,
smaller threadgroups — sliding 32 → 512 TGs at 2 simdgroups, full 24 → 96 TGs
at 8 simdgroups — recovers that idle fraction without changing a single output
bit.

---

## 1. Gate 0 — reduction-order reproducibility

### 1.1 Design

Both kernels reduce with `simd_sum` over 32 lanes, twice per K slot in the main
loop (`LRM:1709–1710`, `:1755–1756`, …) and again in the epilogue. `simd_sum` is
a compiler intrinsic whose *association order* is unspecified. Any restructuring
that replaces or regroups it must land on the same float, because the
correctness gate is every checked greedy token matching and `max_abs_diff = 0`.

Gate 0 is a standalone Metal probe, `research/nezuko_r97_simdsum_order_probe.swift`,
that reduces the same adversarial data six ways and compares **bit patterns**,
not tolerances:

| variant | reduction |
|---|---|
| `ref_simd_sum` | the shipped `simd_sum` (reference) |
| `xor_ascending` | `simd_shuffle_xor` with deltas 1, 2, 4, 8, 16 |
| `xor_descending` | the same five adds, deltas 16, 8, 4, 2, 1 |
| `shuffle_down_tree` | `simd_shuffle_down` 16, 8, 4, 2, 1 + broadcast |
| `prefix_sequential` | strict lane order 0…31 via `simd_shuffle` |
| `two_level` | xor 1, 2 (inside 4-lane groups), then xor 4, 8, 16 (across groups) |

Input is deliberately adversarial to association order: random mantissa in
[−1, 1] scaled by 2^e with e uniform on [−12, 12], so a simdgroup spans ~24
binary orders of magnitude and cancellation is common. 200,000 vectors ×
32 lanes = **6,400,000 reduced values** per variant.

`two_level` is the load-bearing row. It is the question "may a two-stage split
reduce *hierarchically* — inside a group, then across groups — and still be
bit-exact?".

### 1.2 Result — **GATE 0 PASSES**

```
device: Apple M4 Pro
architecture: applegpu_g16s
vectors: 200000  lanes: 32  threads: 6400000
xor_ascending     vs simd_sum: bitexact 6400000/6400000 (100.000%)  max_ulp 0
xor_descending    vs simd_sum: bitexact 2434848/6400000 ( 38.044%)  max_ulp 98304
shuffle_down_tree vs simd_sum: bitexact 2434848/6400000 ( 38.044%)  max_ulp 98304
prefix_sequential vs simd_sum: bitexact 1734912/6400000 ( 27.108%)  max_ulp 66638
two_level         vs simd_sum: bitexact 6400000/6400000 (100.000%)  max_ulp 0
```

Reproduce:

```bash
xcrun swiftc -O research/nezuko_r97_simdsum_order_probe.swift \
  -o /tmp/nezuko_simdsum_probe -framework Metal -framework Foundation
/tmp/nezuko_simdsum_probe
```

Two findings, both new and both reusable:

1. **`simd_sum` over 32 lanes is exactly the ascending XOR butterfly ladder**
   (xor 1, 2, 4, 8, 16). 6,400,000/6,400,000 bit-identical, `max_ulp 0`.
2. **A two-level grouped decomposition of that ladder is also bit-exact**
   (100.000 %, `max_ulp 0`). Grouping is legal *because the ascending butterfly
   is itself already a balanced binary tree*: partitioning it at any power-of-two
   boundary reproduces the identical association.

The three plausible-looking alternatives are all wrong: descending XOR and the
shuffle-down tree each disagree on **62 %** of values with excursions to ~98,000
ULP, and strict lane order disagrees on **73 %**. This is not a rounding
curiosity — it is a reminder that "sum the same numbers" is not a specification.

### 1.3 The caveat I am recording rather than smoothing

This was measured on generation-16 silicon. The ranked M5 is generation 17.
`simd_sum`'s lowering is a **compiler** decision, and a Metal compiler upgrade
shipping with a newer GPU family could in principle re-associate it. Gate 0 is
therefore a **necessary** condition established on M4, not a proof about M5. Any
candidate built on it must still be gated on `max_abs_diff = 0` from the
official M5 receipt, and the M4 result must not be quoted as an M5 guarantee.

---

## 2. The structural finding that reshapes this arm

The assignment's Gate 0 premise is that a split changes *how many values each
`simd_sum` sees*. On inspection that is true only for a **generic** split. Two
sharper facts govern the design:

**(a) A partition-preserving split needs no reduction-order change at all.**
Simdgroup `sg ∈ [0,32)` is a *partition* over K: it handles positions
`sg, sg+32, sg+64, …` (16 positions each). The epilogue transposes through
`threadgroup float4 outputs4[BN*BDP]` so that reader simdgroup `sg` owns output
dims `4sg…4sg+3` and reduces **across the 32 partitions with lane index = partition
index** (`LRM:1820–1870`). If a split keeps exactly 32 partitions and only moves
them between threadgroups, stage 2 re-invokes the *identical* `simd_sum` over
the *identical* 32 values in the *identical* lane order. Gate 0's `xor_ascending`
row is then not even needed.

**(b) Bit-exactness forbids the hierarchical combine that Gate 0 unlocks.**
This is the part that changes the arm's economics, so I state it as a proof
rather than an opinion.

The per-partition state is an *online-softmax* triple `(m_p, s_p, o_p)`, and the
combine is not a sum — it is max-then-rescale-then-sum:

```
M = max_p m_p ,   O = Σ_p o_p · exp(m_p − M) ,   S = Σ_p s_p · exp(m_p − M)
```

A hierarchical combine must first reduce inside a group `g`, where the only max
available is the group max `M_g`, and then rescale the group result by
`exp(M_g − M)`:

```
O_hier = Σ_g ( Σ_{p∈g} o_p · exp(m_p − M_g) ) · exp(M_g − M)
```

In exact arithmetic `exp(m_p − M_g)·exp(M_g − M) = exp(m_p − M)`. **In fp32 it
does not**, for two independent reasons: `exp` is evaluated twice and rounded
twice, and the intermediate product is rounded again. `LAGUNA_RESCALE` does not
rescue this — it is a guarded `exp` of a non-positive argument, not a
power-of-two scale. Nor does a two-pass "materialise all scores, then softmax"
restructure help: it changes the *order* in which the running max is discovered,
and the reference's running `pair_max`/`pair_sum`/`LAGUNA_RESCALE` recurrence is
exactly what the greedy-token gate is pinned to.

**Therefore, for a bit-exact split, each partition's `(m_p, s_p, o_p)` must
cross the threadgroup boundary intact.** No grouping, no pre-reduction, no
compression. Gate 0's `two_level` row is a genuine finding, but it is not usable
*here*, because the operator being decomposed is not associative-in-fp32.

**Consequence.** A bit-exact two-stage split is necessarily
*write-all-partials → separate dispatch → combine*. That is a **hard structural
requirement**, and it is what the cost model in §5 must be built on. The
assignment's working figure of ≈17 MB/step and −0.26 % implicitly assumed a
coarser partitioning that (b) rules out.

---

## 3. Phase-1 restructure decision (registered)

Phase 1 of both kernels computes Q0/Q1 RMSNorm+RoPE on simdgroups 0–2, K
RMSNorm+RoPE, and a V copy on simdgroup 3 (28 of 32 simdgroups idle), then
barriers and writes the KV ring cache. It must happen **exactly once per head
pair per layer**, and its RMSNorm uses `simd_sum` at `LRM:1561`.

Three options, decided in advance:

| option | verdict | reason |
|---|---|---|
| **Hoist phase 1 to its own dispatch** | **rejected** | adds a *third* dispatch per layer: 40 more dispatches/step at the measured M5 price of 2.3403 µs (§5) = +93.6 µs/step, on top of the split's own +93.6. Self-evidently fatal. |
| **Replicate phase 1 in every stage-1 TG** | **rejected as the primary** | at 512 sliding TGs each head pair is covered by 16 TGs ⇒ **16× redundant** RMSNorm+RoPE and 16 writers racing on the same KV ring slot. The ring write would need guarding to one TG, and the redundancy is pure added ALU and added `simd_sum` traffic. |
| **Keep phase 1 in a 4-simdgroup prologue inside stage-1 TG 0 of each head pair, others spin** | **rejected** | Metal gives no forward-progress guarantee across threadgroups; a spin is a deadlock risk, not an optimisation. |

**Registered decision:** if the arm proceeds to implementation, phase 1 is
replicated in every stage-1 threadgroup with the KV ring write guarded to the
threadgroup whose K-block index is 0, and the replication cost is **priced, not
assumed away**. A 4-simdgroup (128-thread) stage-1 threadgroup maps phase 1
perfectly (sg 0,1,2,3 → Q0, Q1, K, V), which is a reason to prefer 4-simdgroup
stage-1 TGs (256 sliding TGs) over the assignment's 2-simdgroup / 512-TG shape.
That preference is registered here so it cannot be read back as a post-hoc
choice; the ladder in §7 measures both.

---

## 4. FMA per K iteration versus the ≈96 free-ALU budget

The assignment asks for this count against the M5 free-ALU budget. Per thread,
per K position, per head pair, the sliding main loop
(`LRM:1690–1760`, four-deep pipeline, one slot shown) executes:

| work | ops |
|---|---|
| QK dot, `qk_per_thread = 4`, × 2 heads | 8 fma |
| `simd_sum` × 2 (ascending butterfly, 5 shuffle + 5 add each) | 10 add + 10 shuffle |
| `metal::max` × 2, `LAGUNA_RESCALE` × 2, `fast::exp` × 2 | 2 max + 4 transcendental |
| `pair_sum = pair_sum·factor + exp` × 2 | 2 fma |
| `pair_o[d] = pair_o[d]·factor + exp·v`, 4 dims × 2 heads | 8 mul + 8 fma |
| **total** | **≈26 fma + 10 add + 8 mul + 10 shuffle + 2 max + 4 transcendental ≈ 54 ALU slots** |

The M5 free-ALU reference is **`n = 24` in #496 §10.5 = 24 × 4 = 96 fma per K
iteration**, which M5 absorbed for an effect it could not distinguish from zero
(`research/r93-runs/RESULTS.md:1595–1600`). **But #496 §10.10 withdrew that as a
general statement**: the response is convex, the first ~24 injected ops are
absorbed at 1.36 µs/op and the next 40 are charged at **8.07 µs/op**
(`:1749`), so the absorption knee lies at `24 < n ≤ 64`, i.e. between 96 and
256 fma per K iteration. Two caveats I will not paper over: that ladder sat in
the **routed gather-GEMM** K loop, not the attention K loop, and the two kernels
differ in occupancy and in memory pressure, so the transfer is an assumption.

**What this means for this arm, stated in advance:** the attention loop's ~26
fma per K iteration sits comfortably inside even the conservative 96-fma
absorbed band, and — decisively — **the two-stage split adds no ALU work in the
K loop at all.** It adds *memory traffic* and *dispatches*. The free-ALU budget
is therefore **not the binding constraint** for this mechanism, and I am
registering that I will not invoke it as an explanation for either outcome. The
ladder in §7 is a pure geometry test.

---

## 5. Pre-registered cost arithmetic — the reason this arm is at high risk of a NO-GO

I am registering the kill arithmetic *before* measuring, because if the ladder
later comes out flat I do not want that to read as a rationalisation.

### 5.1 The cost is fixed and known to three significant figures

A bit-exact split is *necessarily* two dispatches per attention layer (§2b).
That is **30 sliding + 10 full = 40 additional decode dispatches per step**.

The price of one added decode dispatch on the ranked M5 was measured on this
programme's own receipt channel: **2.3403 µs/dispatch, 95 % CI [2.2766, 2.4040]**
(OLS, n = 8, R² > 0.999 — `research/r93-runs/RESULTS.md:328`, `:2160`).

```
M5 added dispatch cost = 40 × 2.3403 = 93.6 µs/step   [91.1, 96.2]
```

On M4 the corresponding saturated glue cost is rule 57's **1.2382 [1.2237,
1.2518] µs/dispatch** ⇒ **49.5 µs/step [49.0, 50.1]**.

This is before partial traffic. §2b forces 32 partitions × (128 fp32 + `m_p` +
`s_p`) per head:

```
sliding  64 heads × 32 × 130 × 4 B          = 1.065 MB/layer
         × 2 (write + read) × 30 layers     = 63.9 MB/step
full     48 heads × 32 × 130 × 4 B          = 0.799 MB/layer
         × 2 (write + read) × 10 layers     = 16.0 MB/step
                                       total ≈ 79.9 MB/step
```

against a 1794 MB/step decode byte budget, i.e. **+4.5 %**. At the realised byte
price of 0.015224 % score per MB/step that is nominally **−1.22 % of score** —
larger than the entire 1.0498 % deficit to the promoted frontier. I flag one
honest mitigation: this buffer is ~1 MB per layer, produced and consumed across
a single dispatch boundary, so it may live in SLC and never reach DRAM, in which
case the marginal DRAM price badly overprices it. **I therefore do not use the
byte price as the kill; I use the dispatch cost, which has no such escape.**

### 5.2 The gain has a hard ceiling, and it is smaller than the cost

The published M5 costs of the two kernels are **sliding ≈ 290 µs/step** and
**full ≈ 100 µs/step** (`research/CURRENT_RESEARCH_STATE.md:551`). The wave model
fitted on M4 in round 96 is `t(K) = 1.413 + 7.849 · ceil(K / cores)` per call
(`research/maple-nezuko-r96-a-decode-attention-pipeline.md:133`), so the
**wave-dependent fraction is 7.849 / 9.262 = 84.7 %**; the remaining 15.3 % is a
fixed per-call term that a split cannot remove and in fact *duplicates*.

Makespan in wave units, M5 with 40 cores:

| kernel | shipped | ideal | split shape | split | recovered |
|---|---|---|---|---|---|
| sliding | ceil(32/40) = 1.0 | 32/40 = 0.800 | 512 TGs @ 1/16 work | ceil(512/40)/16 = 13/16 = 0.8125 | 18.75 % |
| full | ceil(24/40) = 1.0 | 24/40 = 0.600 | 96 TGs @ 1/4 work | ceil(96/40)/4 = 3/4 = 0.750 | 25.0 % |

```
sliding gain ≤ 0.1875 × 0.847 × 290 = 46.1 µs/step
full    gain ≤ 0.2500 × 0.847 × 100 = 21.2 µs/step
                                total ≤ 67.3 µs/step
```

**Registered prediction: the ceiling of the mechanism (67.3 µs/step) is below
its floor cost (93.6 µs/step). The expected net is ≈ +26 µs/step — a
regression — even if stage 1 is free, the partials are free, phase-1 replication
is free, and 512 tiny threadgroups schedule perfectly.** None of those four is
free.

One geometry note registered in advance so it cannot be mistaken for a rescue:
the assignment's **96-TG full split is a poor choice for a 40-core host**
(96/40 = 2.4 → 3 waves for 4× the TGs = 0.750). **120 TGs** (24 × 5) gives
ceil(120/40)/5 = 3/5 = 0.600 = *perfect* balance and a 40 % recovery, i.e.
33.9 µs/step. Even substituting that best case, the total ceiling is
46.1 + 33.9 = **80.0 µs/step, still below 93.6**.

### 5.3 What would have to be true for the arm to win

Only one thing: **the second dispatch must be eliminated**, by fusing the
combine into an already-scheduled kernel — the O projection is the only
candidate. That is a materially different and much larger mechanism than the one
assigned, and I am **not** substituting it (rule 24, one mechanism per arm). I
record it in §9 as the follow-up.

---

## 6. Registered go/no-go bars

At least as strict as the advisor's, with the additions marked.

| gate | GO requires | NO-GO |
|---|---|---|
| **Gate 0** | golden output byte-identical **and** token-stream hash identical under the explicit ladder | any bit differs ⇒ **arm terminal, report immediately** |
| **Ceiling ladder** (added by me, decided before running) | measured best-case geometric recovery on M4, in M4 dispatch units, **> 49.5 µs/step** — i.e. the mechanism's ceiling must exceed its own floor cost on the host it is measured on | ceiling ≤ 49.5 µs/step ⇒ **stop before implementing**; no runtime edit is made |
| **Sliding split** | ≥ **120 µs/step** improvement on the M4 blocked randomised ladder, CI excluding zero, `max_abs_diff = 0`, identical token hash, ladder shape = predicted plateau-then-step | CI includes zero, or ladder shape contradicts the mechanism |
| **Full split** | ≥ **40 µs/step** further improvement, same conditions | as above |
| **Equivalence** | `research/run_upstream_equivalence.sh` passes with a non-zero test count | any failure or a zero-test invocation |
| **Budget** | submitted growth ≤ **60,000 B** (headroom at base is 100,524 B total, 0/262,144 growth) | growth > 60,000 B |

The **ceiling ladder** bar is the one I have added, and it is the strictest one
here: it can fail the arm *before* any runtime code is written, using a
falsifiable measurement rather than §5's arithmetic alone. It is registered at
49.5 µs/step because that is the M4-side floor cost (40 × rule 57's 1.2382
µs/dispatch) and the ladder is an M4 measurement; comparing an M4 ceiling to an
M5 cost would be exactly the cross-machine error §8 warns about.

Interpretation registered in advance: a ceiling *below* the floor cost is a
**decisive negative for the mechanism as specified**, not a null result and not
"needs more n". A ceiling *above* it re-opens implementation and I proceed to
the three-state plan.

---

## 7. Falsifier — blocked randomised ladder

Design per rule 56: **blocked randomised ladder for ranking rungs**,
switching-free `perrun` pairs for any absolute saving quoted. #497's design; SE
1.34 µs/step at n = 1742 blocks / 22 min, against a design-offset floor of 9.70
[7.05, 12.42] µs/step that no n removes.

Rungs — sliding **N ∈ {32, 64, 128, 256, 512}** threadgroups, full
**N ∈ {24, 48, 96}**, total K work held constant, executed in randomised
blocked order.

**Registered prediction of the named mechanism:** a **flat plateau at 32, 64 and
128**, then a **step down at 256 and 512**. The plateau exists because on 20 M4
cores `ceil(32/20) = ceil(64/20)·(32/64)`… concretely, makespan in wave units is
1.000 (N=32), 1.000 (N=64: ceil(64/20)/2 = 4/2 → 2.0, worse), so on M4 the
predicted shape differs from M5's and I register the M4 shape explicitly:

| N | ceil(N/20) | work/TG | makespan (wave units) |
|---|---|---|---|
| 32 | 2 | 1 | 2.000 |
| 64 | 4 | 1/2 | 2.000 |
| 128 | 7 | 1/4 | 1.750 |
| 256 | 13 | 1/8 | 1.625 |
| 512 | 26 | 1/16 | 1.625 |

**Falsifiers.** Smooth monotone improvement across all rungs falsifies the named
mechanism (it would indicate a per-TG-size effect, not core quantisation).
Improvement already at N = 64 falsifies it (64 is predicted *exactly* flat
against 32 on 20 cores). Improvement continuing past N = 256 beyond the
predicted 1.625 floor falsifies it. Any of these means the effect measured is
not "core-count quantisation" and the arm's stated mechanism is wrong even if
the number is favourable.

---

## 8. Cross-machine reading — the three precedents I am required to answer

### 8.1 #48 geometry neutrality (receipt `285f79fa`, −0.1488 %)

The precedent: an **8× threadgroup collapse** produced a ranked M5 receipt of
**−0.1488 %** — geometrically neutral. This is the strongest single piece of
evidence against this arm, and I am not discounting it. Two things must be said,
and both are said before measuring:

1. **It is the same axis.** #48 moved threadgroup count by 8× and M5 did not
   care. This arm moves it by 16× (sliding) and 4× (full) in the *other*
   direction. A prior that says "M5 is indifferent to threadgroup count on this
   workload" is directly supported by a real ranked receipt, and my §5 ceiling
   arithmetic — which predicts a *loss* — is consistent with it.
2. **The doctrine line in `CURRENT_RESEARCH_STATE.md` is "geometry neutrality is
   absolute (#48 receipt `285f79fa` = −0.1488 %)".** I am treating that as the
   prior this arm must overturn, not as a nuisance. Overturning it would require
   the ceiling ladder (§6) to show a *large* recovery; §5 predicts it will not.

### 8.2 Rule 66 — the M4→M5 transfer factor

The correct quotation is **`|T| < 0.5`** (`research/r93-runs/RESULTS.md:699`;
`research/r93-runs/pr137-transfer-factor.md:82`). The older point estimate
**−0.40 ± 0.24 is retired and I will not use it anywhere in this arm.** It
rested on a single receipt (#137, +24.6 µs ≈ 1.7σ). Practically: an M4 result
here bounds M5 only weakly, and an M4 *win* would not be evidence of an M5 win.
An M4 *ceiling failure*, by contrast, is informative in the direction I am
using it, because the ceiling is an arithmetic property of core counts and work
partitioning that both machines share — and M4, with 20 cores against 32
threadgroups, has *more* quantisation waste to recover than M5 does, so it is
the **friendlier** host for this mechanism. A ceiling that fails on M4 is
therefore a conservative kill.

### 8.3 #496 §10.10 — what was withdrawn, and what was not

This distinction matters and is easy to get wrong, so I state it explicitly.

**What §10.10 withdrew** was the *anomaly* flagged in §10.5 — the apparent
finding that a throughput-limited addition cost the same wall time on 40 cores
as on 20, which "is not what a core-count model predicts". §10.10 showed this
was a **slope-segment mismatch**: M4 had been measured over the 0 → 24 rungs and
M5 over 24 → 64, the response is convex, and on **matched** segments the M4/M5
ratio is **1.80×**, close to the 2× core ratio (`RESULTS.md:1796–1812`). The
verbatim resolution is *"Withdrawn (10.10): there was no anomaly."* §10.5's
separate headline "M5 absorbs free ALU" also did not survive as a general
statement (`:1786`).

**What was not withdrawn, and is not in question,** is the raw geometry fact
this arm rests on: the sliding kernel launches **32 threadgroups** and the full
kernel **24 threadgroups** onto a **40-core** M5. That is read directly from
`LRM:1971–1972` and `:2456–2457` and from the official hardware description; it
is not a slope, not a fit, and not a cross-machine extrapolation. §10.10 in fact
*strengthens* the arm's premise, because "M5 behaves like a 2× machine above the
knee" is exactly the core-count model that makes 8 and 16 idle cores a real
cost.

The arm's problem is therefore **not** that its premise was withdrawn. Its
premise is sound. Its problem is that the *bit-exact* realisation of the premise
costs 40 dispatches (§2b, §5.1), and 40 × 2.3403 µs exceeds what the premise can
return.

---

## 9. Plan, stopping rule, and receipt policy

1. **Gate 0** — done, §1, **PASS**.
2. **Ceiling ladder** — standalone Metal probe on M4, real kernel body, stage-1
   only (no partial write, no second dispatch), rungs per §7 in blocked
   randomised order. This measures the mechanism's *unrealisable upper bound*.
   Bar: > 49.5 µs/step (§6).
3. If the ceiling clears its bar, implement the three states (baseline / sliding
   split / full split, one mechanism per state, rule 24), each with a unique
   kernel-name suffix (rule 33), verify `max_abs_diff = 0` and identical token
   hash, run `research/run_upstream_equivalence.sh` (mandatory for this arm),
   and re-check the editable budget.
4. **Stop and submit** when Gate 0 fails, **or** the ceiling ladder fails its
   bar, **or** three timed states with ladders exist, **or** more than two full
   ladder campaigns have been spent with no CI-excluding-zero state.

**Receipt policy: zero official M5 receipts for this arm.** The assignment
directs it and §5 makes it correct — spending a ranked submission on a mechanism
whose ceiling is below its floor would waste a draw worth ~4.5 % promotion
probability.

**W&B contract:** `attn_us_per_step_sliding`, `attn_us_per_step_full`, and a
`gate0_bitexact` boolean, in project `wandb-applied-ai-team/mlxfast-maple`.
Where a quantity is not measured it is logged with an explicit
`*_measured=False` companion rather than NaN-filled.

**Rule 39 verification (states are reached on the default config).** Both fused
paths are ON by default: `lagunaFusedSlidingAttentionEnabled` is
`environment["DARKBLOOM_FUSED_SLIDING_ATTN"] != "0"` (`LRM:1505–1506`) and
`lagunaFusedFullAttentionEnabled` is `environment["DARKBLOOM_FUSED_FULL_ATTN"]
!= "0"` (`LRM:2011–2012`). Both wrappers launch at
`grid: ((heads/2)*1024,1,1)`, `threadGroup: (1024,1,1)` (`:1971–1972`,
`:2456–2457`). Verified at base `b78e7cd`.
