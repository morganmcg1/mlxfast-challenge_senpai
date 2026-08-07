# T1 — Decode attention occupancy: staircase, tail price, and the KV-split verdict

PR #196 · `maple-2026-08-07a-decode-attention-occupancy` · revision `r1`
Student: maple-nezuko · Base `codex/mlxfast-maple-20260804-advisor` @
`3b75a115f6d64c54107740264c9a5ba515d55414`

**Outcome: Step 0 complete and passing (kill did not fire). Step 1 complete and
it _refutes_ Step 2. No `S` is pre-registered; Step 2 was not entered; zero
receipts consumed.**

Everything below is measured on this host with
`research/nezuko_kv_split_probe.swift`, a research-only Swift binary that
compiles the *actual* kernel text out of
`Sources/MLXFastModel/LagunaRuntimeModel.swift`. No scored file was modified.

```bash
xcrun swiftc -O research/nezuko_kv_split_probe.swift -o /tmp/nezkv
/tmp/nezkv Sources/MLXFastModel/LagunaRuntimeModel.swift
```

Run: `training_id dc05d40d-16a4-4210-a1d5-9b8abda83518`, exit 0, 2.1 s.
Earlier passes: `935bcdcb-…` (residency rendezvous),
`e9ceb1bb-…` (first staircase; superseded — its K=1/K=2 points were clock-ramp
artifacts, fixed here by a 5×200-call warm-up).

---

## 0. Host and provenance

| | |
|---|---|
| Device | Apple M4 Pro, `applegpu_g16s` (GPU generation 16) |
| `gpu-core-count` | **20** |
| `maxThreadgroupMemoryLength` | 32768 B |
| `recommendedMaxWorkingSetSize` | 40,200,896,512 B |
| `_nax` kernels | **not selected** (gen 16) |

Per `agents.md`, an M4 Pro result is *not* evidence for an `_nax` change and
threadgroup geometry can change sign across core counts. Everything in this
report is either (a) a device-independent structural fact, (b) a measurement at
the measured `C = 20`, or (c) an explicitly-labelled model extrapolation to the
ranked `C = 40`. Section 6 states which is which.

### Source-drift check

The kernel literals were extracted by name and hashed before measuring:

| kernel | source lines | len | md5 |
|---|---|---|---|
| `laguna_sliding_fused_attn_ring_v1` | 1378–1662 | 10242 | `31f0d5528bf3363389771464555d6d28` |
| `laguna_full_fused_attn_grow_v1` | 1827–2163 | 12422 | `7faf5ac5948cccd56a59a43469b134f9` |
| shared header (both) | 1665–1711 / 2166–2212 | — | `05c810c39e83bd6fc3e7ba61ba85108d` |

Byte-identical at `f46b7cc`, `e956aa5`, `f2fedd5`; differs at `9e8c719` and
earlier only through maple-tanjiro's PR #81 **byte-identical dedent**. The PR #56
audit's conclusions therefore carry over semantically. (The old recorded
`sed -n '1381,2320p' | md5 = 74f1b453…` no longer matches purely because of line
shifts — not a semantic change.)

### Shipped dispatch geometry (from the runtime, not assumed)

`LagunaRuntimeModel.swift:1761` and `:2263` both dispatch
`grid: ((heads / 2) * 1024, 1, 1), threadGroup: (1024, 1, 1)`, with
`slidingAttentionHeads = 64` and `fullAttentionHeads = 48`
(`Sources/MLXFastModel/LagunaConfig.swift:23-25`):

| layer kind | q heads | **threadgroups** | threads/TG | layers/step |
|---|---|---|---|---|
| sliding (`…ring_v1`) | 64 | **32** | 1024 | 30 |
| full (`…grow_v1`) | 48 | **24** | 1024 | 10 |

Two heads per threadgroup. This is the single most important number in the
report and it is why Step 2 fails — see §5.

---

## 1. Step 0a — real pipeline properties for both scored attention kernels

Compiled through `MTLDevice.makeComputePipelineState` from the extracted kernel
text; these are `MTLComputePipelineState` properties, not estimates.

| property | `…sliding_fused_attn_ring_v1` | `…full_fused_attn_grow_v1` |
|---|---|---|
| `staticThreadgroupMemoryLength` | **18432 B** | **18432 B** |
| `maxTotalThreadsPerThreadgroup` | **1024** | **1024** |
| `threadExecutionWidth` | **32** | **32** |
| simdgroups per threadgroup | **32** | **32** |

This confirms advisor correction **(A)**: the threadgroup is 1024 threads /
32 simdgroups. My earlier §5.1 note was wrong.

It also confirms correction **(B)** by inspection of the kernel body: the loop
is `int i = sg; for (; i + BN < N; i += 2 * BN)` over `BN = 32`, so the 32
simdgroups already perform a **32-way intra-threadgroup flash-decoding split of
the KV axis**, followed by a working max/sum-rescale merge in the epilogue.
Any "KV split" I could add is a *second, inter-threadgroup* split layered on top
of an existing one.

### Residency (rendezvous method, run `935bcdcb`)

A cooperative rendezvous kernel — one that cannot complete unless all launched
threadgroups make simultaneous forward progress — gives the true co-residency
ceiling:

| threads/TG | max co-resident TGs (20 cores) | TG/core | simdgroups/core |
|---|---|---|---|
| 1024 | 60 | **3** | **96** |
| 512 | 120 | 6 | 96 |
| 256 | 240 | 12 | 96 |
| 128 | 480 | 24 | 96 |

Flat in threadgroup memory from 16 B to 32768 B. The real 18448 B body and a
halved-plane 10000 B variant **both** cap at 60 TGs = 3/core, so
**halving the epilogue's threadgroup planes buys exactly zero residency.**

---

## 2. Step 0b — the duration-vs-N staircase (the required deliverable)

`K` = number of dispatched 1024-thread threadgroups, swept at unit resolution
from 1 to `3 × C = 60`. Each point is 200 back-to-back calls on a warm clock.

### 2.1 Sliding kernel (`N = 512` compile-time constant)

| K | µs/call | Δ | K/C |
|---|---|---|---|
| 1 | 8.891 | — | 0.05 |
| 10 | 9.104 | +0.188 | 0.50 |
| 19 | 9.095 | −0.010 | 0.95 |
| **20** | **9.069** | −0.026 | **1.00** |
| **21** | **15.551** | **+6.482** | **1.05** |
| 30 | 15.931 | +0.003 | 1.50 |
| **40** | **16.231** | −0.015 | **2.00** |
| **41** | **22.675** | **+6.444** | **2.05** |
| 60 | 23.886 | +0.019 | 3.00 |

Within a wave the mean |Δ| is ≈ 0.06 µs. At the two wave boundaries Δ jumps to
**+6.48 µs** and **+6.44 µs** — a 100× discontinuity. The staircase is
unambiguous and its risers sit exactly at `K = C + 1` and `K = 2C + 1`.

### 2.2 Full kernel (`N` from `params[2]` at runtime) — closes the §9 gap

The PR #56 audit never swept this kernel. It obeys the identical law:

| K | µs/call | Δ |
|---|---|---|
| 1 | 9.128 | — |
| **20** | **9.327** | −0.043 |
| **21** | **15.577** | **+6.250** |
| **40** | **18.340** | −0.595 |
| **41** | **25.242** | **+6.902** |
| 60 | 27.154 | +0.015 |

(The full kernel's in-wave plateau is noisier — ±0.5 µs above K≈28 — because its
`N` and `capacity` are runtime uniforms rather than a `constexpr`, so bounds
arithmetic is not folded. The risers are still 10× any in-wave wobble.)

### 2.3 Verdict on the pre-registered kill

> *Kill: if ≥2 co-resident TGs **and** no staircase step at N = cores → the tail
> model is wrong; report and stop.*

- Co-resident TGs at 1024 threads: **3** (≥ 2 → first clause true).
- Staircase step at `N = cores`: **present and enormous** in *both* kernels
  (+6.48 µs and +6.25 µs at K = 21).

The kill requires *both* clauses. The second is false, so **the kill does not
fire.** The wave/tail model with `C` = physical core count survives, and Step 1
is unlocked.

---

## 3. Step 0c — verdict on the 32-vs-96 simdgroups/core contradiction

`research/CURRENT_RESEARCH_STATE.md` §0c flags this as unreconciled and forbids
using either number. **Both numbers are correct; they measure different
things.** The resolution:

- **96 simdgroups/core is the *residency* ceiling.** It is proved by the
  rendezvous construction in §1, which cannot complete unless that many
  simdgroups are simultaneously resident. It holds at every threadgroup size
  from 128 to 1024 threads and at every threadgroup-memory size, which is what a
  hardware slot limit looks like. It is a real, hard occupancy constraint.
- **32 simdgroups/core is the *throughput* width** — one 1024-thread
  threadgroup per core per wave. This is what the duration staircase measures,
  and it is the number that governs performance.

They are reconciled by measuring how much the extra residency actually buys.
Fitting `T(K) = a + b·⌈K/C⌉` to the three wave plateaus (9.069 / 16.231 /
23.886 µs) gives

```
b (marginal wave cost) = 7.408 µs      a (once-per-call) = 1.661 µs
model vs measured: W=1 +0.0% , W=2 +1.5% , W=3 +0.0%
```

and `b / (lone-TG latency) = 7.408 / 8.891 = 83.3%`. So the second and third
co-resident threadgroups recover only **~17%** of a wave — this kernel is
issue/ALU-bound, not latency-bound, so extra residency has almost nothing to
hide.

> **Recommended edit to §0c:** replace the "⚠️ UNRECONCILED DISCREPANCY" block
> with: *96 simdgroups/core is the residency ceiling (rendezvous-proven, run
> `935bcdcb`); 32 simdgroups/core — i.e. one 1024-thread threadgroup per core —
> is the throughput width that sets the duration staircase (run `dc05d40d`).
> **For all performance modelling use 32.** Co-residency recovers only ~17% of a
> wave for the attention kernels.*
>
> The neighbouring "ALU utilisation saturates at ~24 simdgroups/core" claim
> (line 212) is consistent with this and needs no change: with 3 co-resident
> 32-simdgroup threadgroups the core is well past that saturation point, which is
> precisely *why* the extra residency buys so little.

---

## 4. Step 1 — pricing the tail with the measured `C`

### 4.1 Fixed vs marginal cost (KV-length sweep)

`N` was varied 64…512 by textual replacement of the sliding kernel's
`constexpr int N = 512;`. `L = N/64` = main-loop iterations per simdgroup.

| N | L | µs @K=1 | µs @K=20 | µs @K=32 |
|---|---|---|---|---|
| 64 | 1 | 3.654 | 3.755 | 5.472 |
| 128 | 2 | 4.576 | 4.706 | 7.170 |
| 256 | 4 | 5.967 | 6.150 | 9.909 |
| 384 | 6 | 7.442 | 7.636 | 15.076 |
| 512 | 8 | 8.877 | 9.072 | 17.840 |

Linear fit `µs = f + g·L`:

| K | f (µs) | g (µs/iter) | max resid | **f/g** | f as % of a 512-row TG |
|---|---|---|---|---|---|
| 1 | 3.025 | 0.7339 | 0.105 | 4.12 | 34.0% |
| **20** (one wave) | **3.130** | **0.7483** | 0.124 | **4.18** | **34.3%** |
| 32 (two waves) | 3.266 | 1.8848 | 0.896 | 1.73 | 17.8% |

The K=32 row is two waves, so its `g` is ≈ 2× and the linear form fits poorly
(resid 0.90). **The single-wave K=20 row is the one to use: `f = 3.13 µs`,
`g = 0.748 µs/iter`.**

Decomposing further with the once-per-call cost `a = 1.661 µs` from §3:

```
per-wave fixed cost      φ = f − a = 1.469 µs
per-wave full-length work γ = 8g   = 5.986 µs
```

### 4.2 Integer-wave efficiency table (required publication)

Efficiency = `TGs / (waves × C)` — the fraction of a wave's threadgroup slots
doing useful work. Sliding dispatches `32·S` threadgroups, full `24·S`.

| S | sliding TGs | waves@20 | eff@20 | waves@40 | **eff@40** | full TGs | waves@20 | eff@20 | waves@40 | **eff@40** |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 32 | 2 | 80.0% | **1** | **80.0%** | 24 | 2 | 60.0% | **1** | **60.0%** |
| 2 | 64 | 4 | 80.0% | 2 | 80.0% | 48 | 3 | 80.0% | 2 | 60.0% |
| 3 | 96 | 5 | 96.0% | 3 | 80.0% | 72 | 4 | 90.0% | 2 | 90.0% |
| 4 | 128 | 7 | 91.4% | 4 | 80.0% | 96 | 5 | 96.0% | 3 | 80.0% |
| **5** | 160 | 8 | **100.0%** | 4 | **100.0%** | 120 | 6 | **100.0%** | 3 | **100.0%** |
| 6 | 192 | 10 | 96.0% | 5 | 96.0% | 144 | 8 | 90.0% | 4 | 90.0% |
| 7 | 224 | 12 | 93.3% | 6 | 93.3% | 168 | 9 | 93.3% | 5 | 84.0% |
| 8 | 256 | 13 | 98.5% | 7 | 91.4% | 192 | 10 | 96.0% | 5 | 96.0% |
| 9 | 288 | 15 | 96.0% | 8 | 90.0% | 216 | 11 | 98.2% | 6 | 90.0% |
| **10** | 320 | 16 | **100.0%** | 8 | **100.0%** | 240 | 12 | **100.0%** | 6 | **100.0%** |

This reproduces advisor correction **(C)** exactly: **S=5 is the unique small S
that reaches 100% on both kernels at both 20 and 40 cores**, and S=2 changes
nothing at all on the sliding kernel (80% → 80%).

**But this table is a trap, and §5 is why.**

---

## 5. Step 1's decisive result — the efficiency gain is not recoverable

### 5.1 On the ranked M5 (C = 40) there is no tail to price

Sliding dispatches **32** threadgroups and full dispatches **24**. Both are
**≤ 40**. Therefore on the ranked host:

> **Both scored attention dispatches already complete in exactly one wave.**

The 80% and 60% "efficiency" figures in the S=1 row are **idle threadgroup
slots, and idle slots cost zero time**. A wave's duration is set by the work in
its *busiest* threadgroup, not by how many slots are filled. There is no tail,
no straggler, and nothing for a KV split to reclaim. Every `S ≥ 2` strictly
*adds* waves (`⌈32S/40⌉ ≥ 2`) while conserving total work.

The arithmetic is brutal at S=2, and it sharpens the advisor's correction (C).
With `T = a + W·(φ + g·L)`:

```
S=1:  W=1, L=8   →  a + 1·(φ + 8g)
S=2:  W=2, L=4   →  a + 2·(φ + 4g)  =  a + 2φ + 8g
```

The `g` work is *identical* (8g both ways) and the split pays `φ` one extra
time. S=2 is not merely "zero quantization gain" — it is **exactly one extra
per-wave fixed cost worse**, unconditionally, for any `f > 0`. It can never win,
which is precisely why it must not be run as a candidate arm.

### 5.2 Even on a 2-wave host (C = 20) the split loses by 3.7–7.8×

At C=20 the shipped dispatch really does need `⌈32/20⌉ = 2` waves, so there *is*
quantization to recover: S=5's `g`-work drops from `2 × 8g = 16g` to
`8 × (8g/5) = 12.8g`, a genuine saving of `3.2g = 2.39 µs`. But the fixed term
rises from `2φ` to `8φ`. Break-even:

```
6φ < 3.2g   ⟺   φ < 0.533·g = 0.399 µs
```

| form | required | **measured** | shortfall |
|---|---|---|---|
| naive per-TG fixed cost `f` | < 0.399 µs | **3.130 µs** | **7.8×** |
| generous per-wave fixed cost `φ` (credits the once-per-call `a` to the call, not the wave) | < 0.399 µs | **1.469 µs** | **3.7×** |

Even the form most favourable to the split misses break-even by 3.7×.

### 5.3 Direct measurement agrees — every split is slower

Two independent emulations, both of which **exclude the inter-threadgroup merge
cost entirely** and use the *ceiling* shard length, so both are strict **upper
bounds on the achievable gain**.

**P4 — direct S-way split at the measured C = 20:**

| S | TGs | rows/TG | waves | µs/call | vs S=1 | model | verdict |
|---|---|---|---|---|---|---|---|
| **1** | 32 | 512 | 2 | **18.333** | 1.000 | 16.57 | shipped |
| 2 | 64 | 256 | 4 | 20.309 | 1.108 | 19.51 | SLOWER *(model point, not a candidate)* |
| 3 | 96 | 192 | 5 | 21.615 | 1.179 | 20.23 | SLOWER |
| 4 | 128 | 128 | 7 | 24.018 | 1.310 | 22.42 | SLOWER |
| **5** | 160 | 128 | 8 | **27.296** | **1.489** | 25.39 | **SLOWER** |
| 8 | 256 | 64 | 13 | 28.815 | 1.572 | 30.49 | SLOWER |
| 10 | 320 | 64 | 16 | 34.875 | 1.902 | 37.15 | SLOWER |

**P4b — ranked M5 (C = 40) emulated by matching the wave count.** A geometry
running `W` waves of `R`-row threadgroups on a 40-core part is reproduced here
as `W × 20` threadgroups of `R` rows on this 20-core part, preserving both the
wave count and the per-threadgroup work:

| S | M5 TGs | M5 waves | rows/TG | emulated K | µs/call | vs S=1 | model |
|---|---|---|---|---|---|---|---|
| **1** | 32 | **1** | 512 | 20 | **9.078** | 1.000 | 9.12 |
| 2 | 64 | 2 | 256 | 40 | 10.384 | 1.144 | 10.59 |
| 3 | 96 | 3 | 192 | 60 | 14.551 | 1.603 | 12.80 |
| 4 | 128 | 4 | 128 | 80 | 16.338 | 1.800 | 13.53 |
| **5** | 160 | 4 | 128 | 80 | **15.468** | **1.704** | 13.53 |
| 8 | 256 | 7 | 64 | 140 | 18.083 | 1.992 | 17.19 |
| 10 | 320 | 8 | 64 | 160 | 19.832 | 2.185 | 19.40 |

The relation is **monotone increasing in S on both hosts**. The 100%-efficiency
points S=5 and S=10 are among the *worst* absolute timings. Efficiency and
duration are anti-correlated here, exactly as §5.1 predicts.

### 5.4 Decision

> **No `S` is pre-registered. Step 2 is not entered.**

The gate for Step 2 was that Step 1 price the tail and identify a profitable
`S`. Step 1 priced the tail and found it is **worth nothing on the ranked
hardware** (single wave already) and **strongly negative on a 2-wave host**
(3.7–7.8× short of break-even, 1.49–1.70× slower when measured directly).
Proceeding would burn both receipts on a change that all three lines of evidence
— structural, model, and direct measurement — say is a regression.

Receipts consumed: **0 of 2.**

---

## 6. What generalises to the ranked M5, and what does not

| finding | status on ranked M5 (C=40, gen 17, `_nax`) |
|---|---|
| TG = 1024 threads = 32 simdgroups; `staticThreadgroupMemoryLength` = 18432 B | **Structural** — read from the compiled pipeline, independent of host |
| Sliding = 32 TGs, full = 24 TGs | **Structural** — from `heads/2` in the runtime |
| 32 < 40 and 24 < 40 ⇒ both dispatches are single-wave | **Structural given the above** — this is the load-bearing claim, and it is arithmetic, not timing |
| S=2 costs exactly one extra `φ` | **Structural** — algebraic identity, any `f > 0` |
| Duration is flat in K up to C, with a hard riser at C+1 | **Measured at C=20**, on two kernels, at unit resolution. Wave scheduling is not gen-16-specific, but the *riser height* on M5 is not measured here |
| `f = 3.13 µs`, `g = 0.748 µs/iter`, `φ = 1.469 µs`, `b = 7.408 µs` | **M4 Pro numbers only.** Absolute values will differ on M5 |
| 96 simdgroups/core residency ceiling | **Measured on M4 Pro.** Not verified on M5 |
| P4b C=40 emulation | **Model extrapolation.** It matches wave count and per-TG work but not memory-system width or `_nax` availability |

The refutation does **not** depend on any M4-only number. It rests on the
structural claim that 32 and 24 both fit in one 40-slot wave. The M4 timings
merely confirm the mechanism and rule out the fallback case (a 2-wave host),
where the split also loses.

Per `agents.md`, an M4 result is not evidence for an `_nax` change — but Step 2
would not have been an `_nax` change, and no `_nax` path is proposed here.

---

## 7. Actionable byproducts (not implemented — advisor's call)

### 7.1 The 32-way merge epilogue is ~13% of the sliding call

P4c prices the existing intra-threadgroup merge by textually removing the block
between `pair_max0 = max_scores[lane];` and `if (lane == 0) {` — 1642 chars,
3 barriers, 4 threadgroup passes over `outputs[4*BN*BDP]`:

| N | L | full µs @K=20 | no-merge µs @K=20 | **merge µs** | merge % of call |
|---|---|---|---|---|---|
| 64 | 1 | 3.761 | 2.693 | 1.068 | **28.4%** |
| 256 | 4 | 6.436 | 5.363 | 1.072 | 16.7% |
| 512 | 8 | 9.098 | 7.928 | 1.170 | **12.9%** |

The merge cost is **essentially constant in N** (1.07 → 1.17 µs) — it is pure
fixed overhead, and it accounts for **~80% of the per-wave fixed cost
φ = 1.469 µs**. That identifies φ, the exact quantity that killed Step 2, as
*mostly the existing merge*.

Crude ceiling: 40 attention calls/step × 1.17 µs = **46.8 µs/step**. At the
recorded elasticity (−1 µs/step = +0.01464% score) a *free* merge would be worth
**+0.685%**. The merge is required for correctness so that is unreachable; a
realistic 30% shave (fewer barriers, a tree reduction over 32 partials instead
of 4 full threadgroup passes, or keeping partials in registers) would be
**≈ +0.21%**. That is a plausible T-series experiment on its own and it is the
natural successor to this one.

Caveat: the stripped variant is numerically wrong by construction — it is a
timing probe only. A real change needs the full correctness stack.

### 7.2 Threadgroups up to C are free

Duration is flat from K=1 to K=C. On the ranked M5 that means **8 spare
threadgroup slots on sliding layers and 16 on full layers cost nothing**. Any
restructuring that keeps the wave count at 1 while using more threadgroups is
free; any that pushes to 2 waves pays the full ~7.4 µs. This is a useful design
rule for future attention work and it cuts *against* every "split the work
finer" idea in the same family as Step 2.

### 7.3 Do not spend effort shrinking attention threadgroup memory

18432 B of the 32768 B limit still yields 3 TG/core, and a 10000 B variant also
yields 3 TG/core. Threadgroup memory is not the binding residency term for these
kernels.

---

## 8. Correctness

No scored file was modified, so the correctness stack was not required and was
not run. `git status` on the submitted surface is clean; the only added file is
`research/nezuko_kv_split_probe.swift`, which is research-only and contributes
**0 bytes** to the 3,000,000-byte submitted budget.

Byte budget at base is unchanged: `current=2926911/3000000 headroom=73089
growth=0/262144 files=142`.

Had Step 2 been entered, the pre-registered gate was
`research/run_upstream_equivalence.sh` + the 64-step drift tripwire + a bitwise
logit digest (`top_k=100352`, 64 steps) with a control shown to fire, plus a
positive reachability trace. None of that was needed.

---

## 9. Summary line

```
lone threadgroup (K=1)           8.891 us
shipped dispatch (K=32)         15.950 us
marginal wave cost (K=20->40)    7.162 us
wave cost / lone latency          80.6%
```

**Step 0: pass, kill did not fire. Step 1: complete, and it refutes Step 2.
No S pre-registered. Step 2 not entered. 0/2 receipts used.**
