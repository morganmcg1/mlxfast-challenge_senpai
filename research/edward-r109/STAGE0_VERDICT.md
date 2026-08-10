# R109-D Stage 0 verdict — simdgroup-MMA for the QK reduction in the sliding fused attention decode kernel

- Assignment: `maple-r109-d-sliding-attn-qk-mma` / `r109-d-rev1`, PR #684
- Base: `codex/mlxfast-maple-20260804-advisor` @ `1a6761bf46c282fcabd0577b618f0c1206757e6c`
- Owned span: `Sources/MLXFastModel/LagunaRuntimeModel.swift` lines 1507–1975 (`laguna_sliding_fused_attn_ring_v1`)
- Measurement host: Apple **M4 Pro**, `applegpu_g16s` (gen 16), 20 GPU cores, 48 GiB. All timing is directional; kernel-internal ratios only, never a ranked score.
- All probe artifacts, arm generators and raw tables are committed under `research/edward-r109/`.

## TL;DR

**The assigned mechanism is refuted, the preregistered stop rule fires, and the
retarget the stop rule pointed at is refuted too. I did not write the MMA
kernel.** The whole above-floor pool in this kernel is closed on M4-screenable
evidence.

### The three preregistered numbers (advisor comment 3)

Paired A/B, residency-defeated (`FERN_DEFEAT_SLOTS=64`), 101 alternating rounds
of 200 dispatches, null brackets on both ends of every sweep.

| arm | K=32 (M4 scored, 1.60 TG/core) | K=16 (**M5 ratio**, 0.80 TG/core) |
|---|---|---|
| (a) current, vs itself | +0.19% / +0.08% | −0.12% / −0.05% |
| (b) dummy-reduce `simd_shuffle(x,0)` | **−6.86%** (t=−39.7) | **−5.13%** (t=−121.9) |
| (c) load-only, no reduce, no PV | **−9.54%** (t=−83.2) | **−8.82%** (t=−276.5) |

**(b) − (a) = 5.13–6.86%, below the preregistered ≥8% bar.** Per the advisor's
own rule the cross-lane reduction is not the binding constraint, MMA cannot pay,
and the verdict is `N-ISSUE-BOUND` for the reduction. Two independent reasons
make it stronger than a rule technicality:

1. The reduce ceiling priced in the advisor's units is **32–43 µs/step of decode
   busy** (5.13–6.86% of the 627.3 µs/step sliding-attention budget; 26–34
   µs/step of wall at the advisor's 0.8 busy→wall transfer). That straddles the
   ~30 µs/step `N-QK-REDUCTION-CHEAP` floor and clears only alphonse's most
   optimistic 0.01642 %score/µs constant, not the 0.00669 additive-busy
   constant (needs 57) and nowhere near tanjiro's 0.00203 (needs 186).
2. **Directly measured, bit-exact: an MMA-shaped QK tile is slower in both
   occupancy regimes.** At M=2 useful rows of an 8×8 fragment the tile must
   issue 4× the QK MACs; held bit-exact that padding costs **+10.2% (K=16) /
   +11.8% (K=32)**, about 2× the entire reduce prize. Net for `MMA + broadcast
   epilogue` is **+3.40% (K=16) / +6.05% (K=32)** — slower than base.

### Why the numbers transfer to the ranked machine

The 1024-thread threadgroup admits one resident TG per core (the thread count,
not the 18.4 kB of TG memory, is the binding limit — see §4f), so **TG/core is
also waves/dispatch**. The scored 32-TG sliding dispatch is
two waves on a 20-core M4 Pro but **one under-filled wave on a ~40-core M5 Max**.
Every earlier arm in this round was priced only at K=32, the two-wave regime the
ranked machine never enters, and `AGENTS.md` warns that threadgroup geometry can
change sign across core counts. So I re-priced the decision arms at K=16 = 0.80
TG/core, the M5 ratio (the same proxy @nezuko uses). **No sign flip**: the
padding still costs 2× the prize, and K=16 is the quieter regime (paired sd
0.029–0.045 vs 0.215–0.287, |t| up to 276).

### Why the load-geometry retarget is also refuted

The stop rule said to retarget to load geometry and use arm (c) minus the DRAM
floor to test whether `pipe_ka` staging leaves latency on the table. It does not:

- Arm (c) leaves **91.2%** of kernel time in loads + QK MACs + loop + epilogue.
- That residual is **not bandwidth**: 113 GB/s achieved against a measured
  266.3 GB/s ceiling = 42.6% of peak, `regime=PARTIAL`.
- It is **not launch overhead**: fitting the absolute ladder `t(20)=9.66`,
  `t(40)=19.20` gives a per-dispatch fixed cost of **0.12 µs**, not rule 55's
  3.97 µs microbenchmark intercept.
- It **is per-threadgroup critical-path latency at one TG per core**: `t(K)` is
  flat at 8.84→9.66 µs from K=4 to K=20, so 5× the threadgroups costs +9%. One
  threadgroup's dependent chain *is* the whole wave, and at 1 TG/core there is
  nothing co-resident to hide it behind.

The only two mechanisms that shorten that chain are both already closed, and I
did not spend budget rediscovering them: raising occupancy by shrinking
threadgroup memory is refuted (occupancy measured **flat in TG memory from 16 B
to 32,768 B at 1024 threads** — the 1024-thread TG is the binding limit, not the
18.4 kB), and restoring memory-level parallelism by hoisting the next trip's
loads is **#540's family-specific +4–5% flat-dose codegen tax on this exact
kernel**, still unqualified after rule 82 was qualified. On M5 there are only 32
TGs for ~40 cores, so extra occupancy capacity cannot help even in principle
without a geometry change, and geometry is frozen.

### Supporting evidence

- `simd_sum` is **already the cheapest correct 32-wide all-lane reduction on
  AGX**: an explicit 5-stage shuffle butterfly — the shape any MMA
  fragment-reduction tail would need — is **+1.5% slower**, not faster. There is
  no reduction tail that beats the built-in, so no MMA variant escapes via a
  cheaper epilogue.
- `simdgroup_multiply_accumulate` MAC rate measures **≈0.87× scalar FMA** on
  this host (matches published AGX Matrix-FFMA16 ratios). Funding 4× padding
  needs ≥4×.
- Apple's own profiler shows `simdgroup_matrix` at **0% Neural Accelerator
  utilization even on M5**. The real matrix path is Metal 4 tensors / MPP
  `matmul2d`, gated on arch gen ≥17 and macOS 26.2+, with no bf16 on gen-1 NA,
  and it helps prefill far more than decode (MLX M5-vs-M4: 3.33–4.06× TTFT but
  only 1.19–1.27× generation).
- **Methodological warning for everyone touching this kernel** (esp. @alphonse
  on the full-attention twin): `LAGUNA_RESCALE` contains a *value-dependent
  branch*. Any probe arm that perturbs score values mis-prices instructions. My
  first 4×-MAC arms appeared **faster** for exactly this reason. The fix is a
  runtime-zero multiply (`pad_ * zero_`, `zero_ = U(widx > 0x3fffffffu)`).
- Calibrated against a known-count arm, a `simd_sum` costs **≈7× an independent
  scalar FMA** at the margin even though the static byte census prices it at one
  instruction. In rule 100.4/100.8's currency the 8 reduce sites are worth ≈14
  independent-FMA-equivalent slots per pipeline stage — just above the ≈12
  bar — so this *was* on-rule work to probe, and the uniform-instruction issue
  model underprices cross-lane ops (§7).

Recommendation: **close R109-D as a negative** on the MMA mechanism
(`N-QK-MMA-PADDING-BOUND`) *and* on the reduction as a target
(`N-ISSUE-BOUND`), with the load-geometry retarget pre-refuted above. §9 leaves
exactly one live item (the W=4 `quad_sum` re-tile at ≈17–22 µs/step, itself
below the ~30 µs/step floor) and closes six; treat the K=16/0.80-TG-core
re-pricing as the default protocol for any future arm on this kernel family.

---

## 1. What the kernel actually does

`laguna_sliding_fused_attn_ring_v1` is declared at LRM:1504–1507; the Metal
source literal spans LRM **1508–2026**. Constants: `head_dim=128`,
`window=512`, `gqa=8`, `BN=BD=32`, `BDP=33`, `qk_per_thread=v_per_thread=4`,
`N=512`. Dispatch (LRM:1963–1972) is 32 threadgroups × 32 simdgroups, with
frozen geometry `threadGroup (1024,1,1)`, `grid ((heads/2)*1024,1,1)`.

Main loop is `for (uint i = sg; i + 3*BN < N; i += 4*BN)` — 4 iterations × 4
pipeline stages (A/B/C/D) = 16 key rows per simdgroup. Two heads per lane
(`pair_score0`, `pair_score1`), so **8 QK reduce sites**, at LRM
1681/1682, 1717/1718, 1753/1754, 1789/1790, each a bare `X = simd_sum(X);`.
The preceding FMA blocks (1673–1680, 1709–1716, 1745–1752, 1781–1788) have
shape `<prefix>_score<h> += pair_q<h>[d] * pipe_k<x>[d];` — 4 products per
head per row, i.e. each lane owns 4 of the 128 head dims.

Downstream, the score feeds `max` → `LAGUNA_RESCALE` → `fast::exp` → V
accumulation, and each lane owns 4 of the 128 *output* dims (`pair_o0[0..3]`).
**Every row score must therefore reach all 32 lanes** — the reduction is a
genuine all-reduce, not a reduce-to-lane-0.

Share of the scored window: 40 layers, `layer % 4 == 0` is full attention, so
**30 sliding layers per decode step**. Measured on this host: 30 calls/step,
588–638 µs/step, per-call min 17.5–18.6 µs / p50 20.6–20.9 µs. M5-equivalent
share of decode time from the previous round's instrumentation: **0.342 ms
(5.08% of score) to 0.445 ms (6.61%)**, i.e. ≈**6.9–9.0% of M5 decode time**.

## 2. Static instruction census

`research/edward-r109/census_qk_reduction.py` compiles every arm for both
`applegpu_g16s` and `applegpu_g17s` and diffs compute-pipeline bytes.
Base = **7936 B** (g16s) / 8048 B (g17s); ÷8 B per instruction ⇒ base ≈ **992
instructions**. Arms are generated by `make_qk_arms.py` (single source of
truth for the arm table), which rewrites *only* the sliding-kernel span — the
full-attention kernel reuses the same `pair_score0/1` identifiers, so every
textual edit is span-bounded.

| arm | g16s B | Δ g16s | Δ g17s | Δ instr (g16s) | per reduce site |
|---|---|---|---|---|---|
| `qk_free` (delete the reduce) | 7888 | −48 | −80 | −6 | −0.75 |
| `qk_ladder2` (2-stage shuffle + simd_sum W=8) | 8096 | +160 | +144 | +20 | +2.50 |
| `qk_quad` (`quad_sum`, W=4) | 7936 | 0 | 0 | 0 | 0 |
| `qk_quad_bcast` (`quad_sum` + broadcast) | 8016 | +80 | +80 | +10 | +1.25 |
| `qk_ladder5` (full 5-stage shuffle butterfly) | 8432 | +496 | +480 | +62 | +7.75 |
| `qk_bcast0` (`simd_broadcast(x,0)` only) | 7952 | +16 | 0 | +2 | +0.25 |
| `qk_fma4x` (4× MACs, **score-changing**) | 8896 | +960 | +960 | +120 | +15.00 |
| `qk_fma4x_bcast0` (**score-changing**) | 8912 | +976 | +960 | +122 | +15.25 |
| `qk_pad4x` (4× MACs, **bit-exact**) | 8976 | +1040 | +1040 | +130 | +16.25 |
| `qk_pad4x_bcast0` (**bit-exact**) | 8992 | +1056 | +1040 | +132 | +16.50 |

Reading: the 32 static QK FMAs are ≈**3.2%** of the kernel's instruction
count; quadrupling them adds ≈**+10–13%** of static instructions. `simd_sum`
itself compiles to a *single* instruction per site on both architectures
(`qk_free` is only −6 instructions across 8 sites), so its cost is
microarchitectural (cross-lane latency / shuffle-network occupancy), not issue
count. That is precisely why a static-count argument for MMA is not
decision-grade and why paired timing was required.

## 3. Is `simdgroup_multiply_accumulate` even cheap to issue?

`research/edward-r109/mma_price.metal` counts native instructions for x
back-to-back MMAs:

| arch | 0 MMAs | 16 MMAs | B per MMA |
|---|---|---|---|
| `applegpu_g16s` | 1664 | 1920 | **≈12.8** |
| `applegpu_g17s` | 1680 | 1968 | **≈14.9** |

For calibration, a `FMA + simd_sum + add` round costs ≈16 B (g16s) / 18.1 B
(g17s). So `simdgroup_multiply_accumulate` is a **native ~1–2 instruction op on
both gen 16 and gen 17** — it is *not* expanded into a shuffle cascade. Issue
cost is not the problem with MMA here. The problem is what you must feed it.

## 4. Paired timing — the decisive measurements

Harness: `research/fern_r100_attn_probe.swift` (built with
`xcrun swiftc -O`), driven by `research/edward-r109/run_probe.sh` and
`run_stage0d.sh`. Configuration `FERN_LADDER=32` (**K=32 is the scored
geometry**), `FERN_REPS=200` dispatches per round, `FERN_CACHE_COPIES=6`,
101 alternating A/B rounds, `FERN_DEFEAT_SLOTS ∈ {64, 1}` to test both
residency regimes. `delta = arm − base` within a round; **negative = faster**.
Base per-call 17–19 µs. Every sweep is bracketed by `null` arms (byte-identical
copies) which came in at **≤ ±0.05 µs** — the harness discriminates well below
the effects below.

### 4a. The ceiling (how much is the reduce worth?)

| arm | slots=64 | t | slots=1 |
|---|---|---|---|
| `qk_free` (no reduce at all) | **−6.849%** | −50.6 | −7.050% (and −12.445% in an earlier sweep) |
| `qk_bcast0` (reduce → `simd_broadcast(x,0)`) | **−6.719%** | −33.2 | **−7.631%** (t −51.2) |
| `qk_ladder2` (W=8 tail) | −4.577% | | −4.677% |
| `qk_quad_bcast` (W=4 tail) | −3.540% | −20.2 | −3.937% |
| `qk_ladder5` (explicit 5-stage butterfly) | **+1.483%** | +12.9 | **+1.489%** |

Two structural conclusions:

- `qk_bcast0` recovers **~91% of `qk_free`**. Replacing `simd_sum` with a
  broadcast keeps the identical *data dependency* (all 32 lanes still wait for
  a cross-lane value derived from lane 0) and keeps the score lane-uniform, so
  the downstream `LAGUNA_RESCALE`/`exp` behaviour is unchanged. What it removes
  is only the **reduce semantics** — the log2(32)=5 shuffle-and-add passes. So
  the ceiling is in the reduction tree, not in "having a cross-lane
  dependency", and not in the issue slot.
- The cost ladder tracks **log2(W) pass counts exactly**: W=32 needs 5 passes
  (≈160 lane-passes over 8 sites), W=8 needs 3, W=4 needs 2 (≈96), W=1 needs 0
  (32 sites' worth of nothing). Timing order `free ≈ bcast0 < ladder2 <
  quad_bcast < base < ladder5` is monotone in that count with one exception:
  the **hand-written full butterfly is slower than the built-in**. `simd_sum`
  is already the optimal correct 32-wide all-reduce on AGX; the compiler/HW
  path beats an explicit `simd_shuffle_xor` ladder. **Any MMA design whose
  fragment-reduction tail is a shuffle ladder is strictly worse than what we
  already have.**

These are the earlier K=32 sweeps; `qk_bcast0` reproduced at −6.719% here and
−6.857% in the later decision sweep (§4d), which is the run-to-run spread on
this arm. §4d prices the ceiling properly, in µs/step of decode busy, and
supersedes the earlier `Δscore% ≈ 0.75 × share × saving` conversion I used
before the advisor published per-kernel budgets.

### 4b. The padding bill (does an MMA tile pay for itself?)

An MMA-shaped QK tile with `simdgroup_matrix<T,8,8>` gives 8 rows per fragment
but the pipeline only has **2 useful score rows per stage** (two heads), so
M=2-of-8 ⇒ **4× the QK MACs**. To price that honestly I built
`qk_pad4x` / `qk_pad4x_bcast0`: they emit the *other 12 products* of the full
4×4 outer product into a block-scoped accumulator and fold it in as
`{v} += pad_ * zero_;` with `const U zero_ = U(widx > 0x3fffffffu);` where
`widx` is a runtime kernel scalar. The compiler cannot fold it, the work is
provably emitted (see the +130/+132 instruction census above), and the **score
is bit-identical**.

Job `441a04a7-22e3-4ded-9717-5264ba8feae2`:

| arm | slots=64 | t | slots=1 | t |
|---|---|---|---|---|
| `null` (bracket) | −0.043% | | −0.290% | |
| **`qk_pad4x_bcast0`** (4× MACs + MMA-style broadcast epilogue) | **+6.047%** | +24.4 | **+3.239%** | +19.8 |
| **`qk_pad4x`** (4× MACs, reduce kept) | **+11.802%** | +119.5 | **+11.801%** | +88.2 |
| `qk_bcast0` (ceiling reference) | −6.719% | −33.2 | −7.631% | −51.2 |
| `null` (bracket) | +0.019% | | +0.076% | |

The `qk_pad4x` figure is **+11.80% in both residency regimes** with t up to
+119 — one of the tightest numbers I have measured on this kernel. So:

> **padding bill (+11.8%) ≈ 1.6–1.8× the entire reduce-elimination ceiling
> (−6.7 to −7.6%).**

And the combined arm — 4× MACs plus the best possible epilogue — is net
**+6.0% / +3.2% slower than base**. An M=2 MMA QK tile loses at MAC-rate
parity, before any fragment load/store, layout, or register-pressure cost.

### 4c. The invalidated arms, and why (read this before probing this kernel)

My first 4×-MAC arms `qk_fma4x` (−5.322%, spread 2.38, min disagreeing with
mean) and `qk_fma4x_bcast0` (−7.883%, t −72.1) appeared to say **4× the work
is faster**. That is not a real effect.

`LAGUNA_RESCALE` (defined LRM:1874) is

```
if (as_type<uint>(delta) == 0u) dst = 1.0f; else dst = fast::exp(delta);
```

— a **value-dependent branch**. `qk_fma4x` changes score values, so it changes
how often `fast::exp` actually executes, and the measured delta is dominated by
that, not by the added MACs. (The same mechanism means `qk_free` makes the
score lane-*varying*, turning that branch divergent — a penalty — so `qk_free`
is a conservative *lower* bound on the reduce cost, which is consistent with
`qk_bcast0` sometimes beating it.)

`qk_pad4x*` exists precisely to remove this confound, and it flips the sign of
the conclusion from −7.9% to +6.0%. **Rule for this kernel: an arm that
perturbs score values cannot price instructions.**

### 4d. The preregistered three-arm probe (a)/(b)/(c) — the operative numbers

Advisor comment 3 (2026-08-10T21:14Z) preregistered a decision probe and a
rule. Design, verbatim in intent:

- **(a)** current kernel (measured as `null` vs itself — a byte-identical copy,
  so this is the harness noise floor for the exact comparison being made);
- **(b)** `qk_bcast0` — reduction replaced by `simd_shuffle(x, 0)`-class
  broadcast, **MACs and loads still alive**;
- **(c)** `qk_loadonly` — loads and MACs alive, reduction **and** the PV
  accumulate removed.

Arm (c) is generated by `make_qk_arms.py`'s `PV_STRIP` path: for each of the 4
pipeline stages the softmax/PV block is replaced by 2 `metal::max` that consume
the (unreduced) score and 4 `pair_o0[k] += U(pipe_{s}k)` that consume V, so the
compiler cannot dead-code the loads or the MACs, but no `simd_sum`, no
`LAGUNA_RESCALE`, no `fast::exp` and no 8-wide `pair_o` rescale-accumulate
remain. `pair_sum*` stays 0 and the existing epilogue absorbs it.

Both occupancy points, `FERN_DEFEAT_SLOTS=64` (residency-defeated),
`FERN_ROUNDS=101`, `FERN_REPS=200`, `null` brackets at both ends:

| arm | K=32 (M4 scored, 1.60 TG/core) | K=16 (M5 ratio, 0.80 TG/core) |
|---|---|---|
| **(a)** `null` vs itself | +0.190% / +0.082% | −0.116% / −0.051% |
| **(b)** `qk_bcast0` | **−6.857%** (t −39.7, sd 0.287) | **−5.134%** (t −121.9, sd 0.040) |
| **(c)** `qk_loadonly` | **−9.544%** (t −83.2, sd 0.215) | **−8.817%** (t −276.5, sd 0.030) |
| `qk_pad4x` (bit-exact 4× MACs) | **+11.802%** | **+10.200%** (t +258.6) |
| `qk_pad4x_bcast0` (MMA-shaped net) | **+6.047%** | **+3.400%** (t +90.7) |

Jobs: `8055e34d-bade-4d15-af82-e0aab87116df` (arm (c), K=32),
`cc71b9f1-3783-4001-9b43-4c26b3e8d781` (K=16 re-pricing),
`441a04a7-22e3-4ded-9717-5264ba8feae2` (the earlier decisive K=32 sweep).
`slots=1` (cache-served, diagnostic only, noisier): (b) −10.878%,
(c) −21.075%.

**(b) − (a) = 5.13% (K=16) to 6.86% (K=32), i.e. below the preregistered 8%
bar in both regimes. The advisor's rule fires: do not write the MMA kernel.**
I did not write it; the submitted surface is byte-for-byte unchanged from
`BASE_SHA`.

In the advisor's own currency, with `sliding_fused_attn_ring_v1` = 627.3 µs/step:

| | busy µs/step | wall µs/step @0.8 transfer |
|---|---|---|
| reduce ceiling, K=32 | 43.0 | 34.4 |
| reduce ceiling, K=16 (M5 ratio) | 32.2 | 25.8 |

Against the three published %score-per-µs constants: 0.00669 (additive-busy)
needs 57 µs/step for the 0.378% gap, alphonse #644's 0.01642 needs 23,
tanjiro #663's 0.00203 needs 186. **32–43 µs/step clears only the most
favourable constant.** It straddles the advisor's own
`N-QK-REDUCTION-CHEAP` floor of ~30 µs/step and is nowhere near the
~190 µs/step that would clear under every constant. And this is the *ceiling* —
the price of deleting the reduction outright, which no correct kernel can do.

### 4e. Why K=16 is the M5-relevant number, and the absolute ladder

M4 Pro has 20 GPU cores; the ranked M5 Max has ~40. The dispatch is frozen at
32 threadgroups (one per head pair), so this kernel runs at **1.60 TG/core on
this host and ~0.80 TG/core on the ranked machine**. `FERN_LADDER=K` sets the
threadgroup count directly, so K=16 on M4 reproduces the ranked
threadgroups-per-core ratio. `research/CURRENT_RESEARCH_STATE.md:2828` records
@nezuko already using K=16/0.8 TG-core as the M5 proxy, so this is existing
practice, not a new convention.

The ratio matters here because the *absolute* ladder is not linear.
`run_stage0e.sh`, base kernel only, slots=64, 31 rounds × 200 reps
(job `e8022231-8a19-4aba-8d52-544ed938cfa8`):

| K | TG/core | base µs | µs/K | φ = t(2K)/t(K) |
|---|---|---|---|---|
| 4 | 0.20 | 8.84 | 2.2097 | 1.0506 |
| 8 | 0.40 | 9.29 | 1.1608 | 1.0168 |
| 16 | 0.80 | 9.44 | 0.5901 | 1.9706 |
| 20 | 1.00 | 9.66 | 0.4832 | 1.9867 |
| 32 | 1.60 | 18.61 | 0.5815 | 1.8403 |
| 40 | 2.00 | 19.20 | 0.4800 | — |
| 64 | 3.20 | 34.24 | 0.5350 | — |

Three readings:

1. **`t(K)` is flat from K=4 to K=20**: 8.84 → 9.66 µs for a 5× increase in
   threadgroups. One threadgroup's dependent chain *is* the whole wave. Every
   instruction-level result on this kernel is therefore a latency result, not a
   throughput result.
2. `t(32) ≈ t(40)` — 32 TGs are billed as two full waves of 20, so ~20% of the
   second wave's capacity is idle. That is worth ≈112 µs/step on M4 but it is
   an **M4-only artifact**: at ~40 cores the M5 runs 32 TGs in a single
   partial wave. Do not chase it.
3. Fitting the two clean full-wave points t(20)=9.66 and t(40)=19.20 gives a
   per-dispatch fixed cost of **0.12 µs**, not the 3.97 µs intercept rule 55
   assumes. Launch overhead is not on this kernel's critical path.

### 4f. The load-geometry retarget is refuted, not merely banned

The advisor's fallback was: if (b) misses the bar, retarget to load geometry,
using "(c) minus the DRAM floor" to test whether the 4-deep pipeline's `pipe_ka`
staging leaves latency on the table. Running that test closes it:

- **(c) leaves 90.5% (K=32) / 91.2% (K=16) of kernel time.** Loads+MACs are
  essentially the whole kernel, so there is a lot of nominal headroom.
- **It is not bandwidth.** The probe reports the base kernel at 113 GB/s
  achieved against a measured `dramPeakGBs = 266.3`, i.e. **42.6% of peak,
  `regime=PARTIAL`**. Byte accounting checks out:
  `requestedBytesPerDispatch = 2.04 MiB` at K=32 = 2×512×8×128×2 B of K+V for
  8 KV heads plus Q/O, confirming fp16, 64 q heads, 8 KV heads. A perfectly
  bandwidth-bound kernel would finish in 42.6% of base time; (c) sits at 90.5%,
  i.e. **2.1× above the DRAM floor**.
- **It is not launch overhead** (0.12 µs/dispatch, §4e).
- What is left is **per-threadgroup critical-path latency at ~1 TG/core**, and
  the two ways to attack it are both already closed:
  - *Raise occupancy so another TG hides the latency.*
    `research/CURRENT_RESEARCH_STATE.md` lines 2186 / 2292 / 3607 record
    occupancy **flat in threadgroup memory from 16 B to 32,768 B at 1024
    threads** — the 1024-thread threadgroup is the binding limit, not the
    18.4 kB of TG memory. `research/BRIEF_QUEUED_SLIDING_ATTN_REWRITE.md` §2
    assumes the opposite; the measurement wins. And on M5 there are only 32 TGs
    for ~40 cores, so extra residency capacity has nothing to fill it with
    absent a geometry change, which is frozen.
  - *Restore memory-level parallelism by hoisting next-trip loads.* That is
    exactly #540, whose flat-dose codegen tax on **this** kernel family measured
    +4.23 / +4.28 / +3.80 / +4.79% (`CURRENT_RESEARCH_STATE.md:2885–2913,
    3955`); line 799 states "the sliding-attention prohibition from #540 …
    still stands unqualified". The compiler cannot hoist it either, because
    `k_cache`/`v_cache` are written in phase 2 (LRM:1486–1487) so provable
    non-aliasing fails.

So the retarget's own diagnostic says the remaining 91% is latency the frozen
geometry cannot expose, by two mechanisms that are independently refuted (not
merely banned).

## 5. MMA MAC rate on this silicon

`research/edward-r109/mma_throughput.metal` + `mma_throughput.swift`
(driver usage: `/tmp/mmathru research/edward-r109/mma_throughput.metal 12`).
Two earlier iterations were invalid — identical accumulator seeds let the
compiler CSE the chain (this also invalidates the MMA numbers in the
pre-existing `research/host_flop_ceiling.swift`). The third iteration refills
the A operand per iteration from a scalar recurrence. Even then the x≥2 arms
stayed flat (5.72→5.79 ms at 64K; 104.48→104.48 ms at 1M), so **x≥2 arms are
still invalid** and I report only what survives:

- Scalar FMA arms scale correctly; **scalar FMA peak 3,470–3,612 GMAC/s**,
  which is 86–89% of the 20 cores × 128 FMA × 1.578 GHz = 4,040 GMAC/s
  theoretical — a credible peak.
- `mma_bf16_x1` (serial dependent chain) reaches **3,158 GMAC/s** =
  **0.87× the measured scalar peak**, and ≈98% of the 0.80× ratio predicted by
  published AGX matrix throughput (102.5 Matrix FFMA16 vs 128 scalar FMA per
  core-cycle).

So the matrix pipe is a **0.8–0.9× MAC-rate path**, not a multiplier. To fund
4× padding it would need to be ≥4×. It is off by roughly 5×.

## 6. Literature: is there a matrix path that *would* pay, on M5?

Delegated a research pass (summarised here, sources checked):

- **`simdgroup_matrix` does not reach the M5 Neural Accelerators.** Apple Tech
  Talk 111432 profiles a `simdgroup_matrix` 4K matmul at **0% NA
  utilization**, and explicitly directs custom-kernel authors to TensorOps.
  Their demo: simdgroup ≈2.0 s → TensorOps ≈0.5 s → +Morton order ≈0.33 s.
- Pre-M5, the matrix path was never a FLOP win: 102.5 Matrix FFMA16 / 101.7
  FFMA32 vs 128 scalar FMA per core-cycle ≈ **0.8×**
  (philipturner/metal-benchmarks). llama.cpp PR #16634 finds the new tensor API
  at parity with `simdgroup_matrix` pre-M5.
- The real matrix path is Metal 4 tensors (`MTLTensor` / `metal::tensor`) plus
  **Metal Performance Primitives** `mpp::tensor_ops::matmul2d`, gated on
  **macOS 26.2+ and Apple GPU arch gen ≥ 17** — exactly MLX's
  `is_nax_available()` gate, i.e. this repo's `_nax` kernel family. This host is
  gen 16 and cannot reach it at all.
- **First-generation NA has no bfloat16.** This kernel is bf16 throughout.
- Even where NA does apply it helps **prefill, not decode**: MLX's M5-vs-M4
  numbers are 3.33–4.06× TTFT but only **1.19–1.27× generation**. The headline
  matrix ratios (A19/M5 FP16 matrix 7500 vs SIMD FP32 1880 GFLOPS ≈ 4.0×;
  INT8 13500 GOPS ≈ 7.2×) are prefill-shaped.

Unverified and left open: whether MPP supports NVFP4 (MLX PR #3551 "Reject
tensor-scale nvfp4 in qqmm" hints at a limit), and there is no public direct
measurement of legacy `simdgroup_matrix` throughput on M5 silicon. Neither gap
can rescue an M=2 tile that has to win by 1.6–1.8× just to break even.

## 7. The reduce *is* the round-107 surviving axis — and the static census undercounts it

`research/CURRENT_RESEARCH_STATE.md:3292–3308` closes the whole decode
fused-attention above-floor pool as `N-ISSUE-BOUND` at 97.7% of theoretical
peak instruction issue, and states:

> The **only** surviving axis is a raw instruction census that removes ≈12 issue
> slots from **each** of the 16 pipeline stages (rule 100.4/100.8).

The two censuses plus a *calibrated* marginal cost locate that axis. The
calibration matters: an earlier draft of this section divided percent by static
byte count and got ≈8.4 slots per `simd_sum`. That is wrong, because the loop
is **not** unrolled (`qk_free` removes 8 textual sites but only −48 B = −6
instructions), so static sites ≠ dynamic executions. The correct currency is
dynamic marginal cost measured against a *known* dynamic instruction dose:

- `qk_pad4x` adds 12 neutral products at each of 8 sites = 96 static, and the
  4-trip loop makes that **384 dynamic independent FMAs**, for **+11.802%** ⇒
  **0.0307% per dynamic FMA**.
- `qk_bcast0` removes 8 static reduce sites = **32 dynamic `simd_sum`**, for
  **−6.857%** ⇒ **0.214% per dynamic `simd_sum`**.

⇒ **one `simd_sum` costs ≈7.0× one independent scalar FMA** on this kernel's
critical path. That ratio is the finding, and it is measured, not back-solved.

Converting to rule 100.4/100.8 currency: 6.857 / 0.0307 = **223
FMA-equivalents** of critical path, spread over the 16 pipeline
stage-executions (4 trips × 4 stages) = **≈14 slots per pipeline stage** —
just above the ≈12-per-stage bar that axis sets.

Two consequences the advisor should weigh:

1. This work is **on-rule, not a banned re-open**. It is a raw instruction-census
   item on the one axis left open, and it is (barely) above the size bar.
2. The 97.7%-of-peak-issue figure appears to be computed from a
   uniform-instruction issue model. If so it **underprices cross-lane ops by
   ~7×**, and every other `simd_*` reduction in the fused attention kernels is
   similarly mispriced in that model. Worth re-checking before that closure is
   used to reject a future proposal — but note §4d: even correctly priced, the
   whole reduce is only 32–43 µs/step, so fixing the model does not by itself
   create a winning item here.

## 8. Decision against the stop rule

The operative rule is the one preregistered in advisor comment 3:

> If (b) does not beat (a) by ≥8% of kernel time … do **not** write the MMA
> kernel. Instead post `N-ISSUE-BOUND` for the reduction specifically, and
> retarget the remaining time to load geometry.

**(b) − (a) = 6.86% at K=32 and 5.13% at the M5 threadgroups-per-core ratio.
Both are below 8%, so the rule fires.** No MMA kernel was written; the
submitted surface is unchanged from `BASE_SHA` (`git diff 1a6761bf -- Sources
Vendor` is empty).

Three separate results converge on the same close:

1. **The rule as written.** (b) misses the 8% bar in both occupancy regimes,
   with null brackets at ±0.19% and t = −39.7 / −121.9.
2. **The mechanism is independently dead, by a wider margin at the ranked
   occupancy ratio.** The bit-exact MMA-shaped arm `qk_pad4x_bcast0` — 4× MACs
   for M=2-of-8 plus the best possible broadcast epilogue — is **+6.047%
   (K=32) / +3.400% (K=16, t +90.7) slower than base**. The padding bill alone
   (+11.8% / +10.2%) is **1.7–2.0× the entire prize**. Supported by measured
   MMA MAC rate (0.87× scalar, needs ≥4×) and Apple's own NA profiling (0%
   utilization for `simdgroup_matrix` even on M5). `qk_ladder5` (+1.5%)
   independently kills every shuffle-ladder fragment-reduction tail.
3. **The retarget is refuted too** (§4f): arm (c) leaves 91% of kernel time,
   but that time is 2.1× above the DRAM floor and 0.12 µs from any launch
   cost, so it is per-threadgroup latency at ~1 TG/core — and both ways to
   expose it (occupancy via TG memory; MLP via next-trip hoist) are already
   measured-refuted, not merely banned.

Also worth recording: the ceiling in the advisor's units is **32–43 µs/step
busy (26–34 µs/step wall at 0.8 transfer)**, which straddles the ~30 µs/step
`N-QK-REDUCTION-CHEAP` floor and clears only alphonse #644's most favourable
%score-per-µs constant. So even the unreachable ceiling is a marginal item.

Proposed labels, in order of what the evidence supports:

- **`N-ISSUE-BOUND` (reduction)** — the rule's named outcome. The QK reduce is
  real (≈14 slots/stage, ≈7× a scalar FMA) but 5–7% of kernel time = 32–43
  µs/step is not enough to cross the gap, and there is no cheaper correct way
  to land it.
- **`N-QK-MMA-PADDING-BOUND`** — the assigned mechanism specifically: an M=2
  simdgroup-MMA tile loses at MAC-rate parity before any fragment
  load/store, layout or register-pressure cost.
- **Load-geometry retarget: closed on this host's evidence**, not deferred.

## 9. What I would carry forward (not implemented)

**Still live (one item).**

1. **W=4 `quad_sum` re-tile** is the only surviving sub-ceiling candidate:
   measured **−3.540% / −3.937%** ⇒ ≈**17–22 µs/step busy**, ≈14–18 µs/step
   wall at 0.8 transfer, at a cost of ≈+56 floats/lane of register pressure.
   That is **below** the advisor's ~30 µs/step `N-QK-REDUCTION-CHEAP` floor, so
   on the pricing in §4d it should stay shut unless the additive-busy constant
   is revised upward. I did not start it. If it is ever revived it needs a
   distinctly named pipeline, unchanged geometry, a margin certificate, and
   ≥8-pair contemporaneous ABBA `--local-iterate`.

**Closed by this round's evidence (do not re-open without new physics).**

2. **The reduce-elimination ceiling itself** is now priced at 32–43 µs/step
   busy, not "the largest unclaimed decode-attention item". It is real but
   sub-threshold, and no correct kernel can collect all of it.
3. **d-major re-tile** (each lane owning 32 dims of 1 row instead of 4 dims of
   8 rows) would make the reduce W=1 for free, but changes V-accumulation
   ownership and therefore the whole pipeline — and its whole prize is the
   sub-threshold 32–43 µs/step. A full rewrite for a marginal item.
4. **Half-width lane split.** Giving lanes 0–15 eight dims of head0 and lanes
   16–31 eight dims of head1 would produce both scores in 5 passes instead of
   10 at identical register count. Prize ≈ half the ceiling ≈ 16–22 µs/step,
   below the floor, *and* an 8-dims-per-lane layout is a wider per-lane load,
   which is on round 107's banned-re-open list (rule 102.5, PR #642). Both
   reasons now point the same way; I am closing it rather than asking for
   clearance.
5. **Raising occupancy via threadgroup-memory reduction** — refuted:
   occupancy is flat in TG memory from 16 B to 32,768 B at 1024 threads
   (`CURRENT_RESEARCH_STATE.md:2186, 2292, 3607`). The 1024-thread TG is the
   binding limit. `BRIEF_QUEUED_SLIDING_ATTN_REWRITE.md` §2's premise that
   18.4 kB is what limits residency is not supported by the measurement.
6. **Restoring MLP by hoisting next-trip loads** — refuted for this kernel
   family by #540's flat-dose codegen tax (+3.80…+4.79%), and the prohibition
   at `CURRENT_RESEARCH_STATE.md:799` stands.
7. If anyone revisits matrix hardware, the only viable target is
   `mpp::tensor_ops::matmul2d` in the `_nax` family on gen ≥ 17, and prefill is
   the place to look, not decode. Gen-1 NA's lack of bf16 must be resolved
   first.

**Method carry-forward, useful to every kernel student.**

8. **Price arms at the ranked threadgroups-per-core ratio, not just at K=32.**
   On this kernel every effect shrank at K=16 (reduce ceiling 6.86 → 5.13%,
   MMA-shaped penalty 6.05 → 3.40%). Reporting only the M4-native geometry
   overstates instruction-level effects by ~1.3–1.8×.
9. **`t(K)` is flat to ~1 TG/core** on this kernel (§4e), and the fitted
   per-dispatch fixed cost is 0.12 µs, not rule 55's 3.97 µs. Any argument on
   this kernel that leans on launch overhead needs re-deriving.
10. **A cross-lane `simd_sum` costs ≈7× an independent scalar FMA** here (§7).
    Static byte/instruction censuses underprice it by that factor.

## 10. Note to @alphonse (full-attention twin, LRM 2027+)

Everything above transfers, and these items save you a full stage:

- **`simd_sum` is already optimal.** An explicit 5-stage shuffle butterfly is
  +1.5% *slower* than the built-in. Do not build a shuffle-ladder MMA epilogue.
- **MMA issue cost is fine** (~12.8 B g16s / ~14.9 B g17s ⇒ native 1–2
  instructions). The killer is the M-padding: 4× MACs = **+11.8% (K=32) /
  +10.2% (K=16)** bit-exact, vs a **−6.9% / −5.1%** total prize; net MMA-shaped
  arm is **+6.0% / +3.4% slower than base**. Check your kernel's
  useful-rows-per-8 before anything else; if you also sit at M=2 the arithmetic
  is identical and you can close on my numbers without spending a stage.
- **`simdgroup_matrix` gets 0% NA utilization even on M5** (Apple Tech Talk
  111432). There is no hidden matrix throughput to unlock via this intrinsic on
  any current Apple GPU. Measured MMA MAC rate is 0.87× scalar FMA; you need
  ≥4× for M=2.
- **Beware `LAGUNA_RESCALE`** (LRM:1874, and its twin in your span): the
  `as_type<uint>(delta)==0u` branch is value-dependent, so any arm that changes
  score values mis-prices instructions — mine reported −7.9% for arms that are
  really +6.0%. Use a runtime-zero multiply
  (`const U zero_ = U(widx > 0x3fffffffu); acc += pad_ * zero_;`) to emit work
  while holding the score bit-identical.
- **Price at the M5 threadgroups-per-core ratio.** `full_fused_attn_grow_v1`
  dispatches `(fullAttentionHeads / 2) = 48/2 = 24` threadgroups
  (`LagunaConfig.swift:24`, dispatch at LRM ~2455–2457), so you are at
  **1.20 TG/core on a 20-core M4 Pro and ~0.60 TG/core on the ~40-core ranked
  M5**. Set `FERN_LADDER=12` and re-price: on my kernel every effect shrank by
  1.3–1.8× when I halved K, and the MMA penalty shrank most. If you only
  measure at native K you overstate both the prize and the penalty.
- **The absolute ladder is flat to ~1 TG/core** (8.84 → 9.66 µs for K=4→20 on
  mine, §4e). If yours behaves the same, one threadgroup's dependent chain is
  the whole wave, your 24 TGs leave ~40% of M5 cores idle, and every
  instruction-level number you measure is a latency number. Worth running
  `run_stage0e.sh`-style `FERN_LADDER=4,8,16,20,32,40,64` on your kernel before
  interpreting anything else — it took one job.
- **My arm generator is reusable.** `research/edward-r109/make_qk_arms.py` is
  span-bounded (it only rewrites LRM 1507–1975, precisely so it does not touch
  your span — note both kernels reuse the `pair_score0/1` names, so any textual
  edit *must* be span-bounded). Swap `sliding_span()` for a full-attention span
  and the `PV_STRIP` / `PAD4X_NEUTRAL` arms come along.

## 11. Reproduction

```bash
# static census (all arms, both architectures)
python3 research/edward-r109/census_qk_reduction.py /tmp/qkcensus

# generate candidate LRM copies for every arm
python3 research/edward-r109/make_qk_arms.py

# MMA native-instruction price
xcrun -sdk macosx metal -c research/edward-r109/mma_price.metal ...   # see script header

# paired timing at the scored geometry (K=32), slots 64 then 1
research/edward-r109/run_stage0d.sh null qk_pad4x_bcast0 qk_pad4x qk_bcast0 null

# the preregistered three arms (a)/(b)/(c) at K=32
research/edward-r109/run_stage0d.sh null qk_bcast0 qk_loadonly null

# absolute threadgroup ladder, base kernel only (§4e)
research/edward-r109/run_stage0e.sh

# re-price every arm at the M5 threadgroups-per-core ratio (§4d, §4e)
research/edward-r109/run_stage0f.sh 16 null qk_bcast0 qk_loadonly qk_pad4x qk_pad4x_bcast0 null

# MMA MAC rate
xcrun swiftc -O research/edward-r109/mma_throughput.swift -o /tmp/mmathru
/tmp/mmathru research/edward-r109/mma_throughput.metal 12
```

Raw tables: `research/edward-r109/probe_*.txt`.
