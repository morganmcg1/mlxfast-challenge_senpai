# PR #103 — Fused decode attention: occupancy rewrite of `sliding_fused_attn_ring_v1`

Student: @maple-tanjiro
Assignment: `maple-2026-08-06i-sliding-attn-occupancy-rewrite` r1
Head branch: `maple-tanjiro/sliding-attn-occupancy-rewrite`
BASE_SHA (assigned): `1d12077a26f3300fa0fa784105d3c6c5b8847d57`

**Verdict: NO-GO on every variant. Recommend closing the sliding-attention
occupancy line. The submitted surface is unchanged — zero bytes of
`Sources/`, `Vendor/`, `Package.swift` or `benchmark.json` were touched.**

---

## 0. Baseline-advance event — resolved without a rebase or a re-measure

The base branch moved from the assigned `1d12077a` to `dec0a83c` during the
experiment. Verbatim:

```console
$ git diff --stat 1d12077a26f3300fa0fa784105d3c6c5b8847d57 dec0a83c075d151ef5dec94f4005bd39ff2c2d69 \
      -- Sources/ Vendor/ Package.swift benchmark.json
                                     <<< empty >>>

$ git diff --name-only 1d12077a26f3300fa0fa784105d3c6c5b8847d57 dec0a83c075d151ef5dec94f4005bd39ff2c2d69
research/CURRENT_RESEARCH_STATE.md
```

The advance is one research-note file. **Zero submitted bytes changed**, so no
rebase and no re-measurement are required, and every timing below remains valid
against the newer baseline. Corroboration — the editable-budget accounting is
byte-identical at both SHAs:

```console
$ ./senpai/check-editable-budget.sh 1d12077a26f3300fa0fa784105d3c6c5b8847d57
editable budget OK: current=2934331/3000000 bytes headroom=65669 growth=0/262144 files=142 (file count is diagnostic only; base=142)

$ ./senpai/check-editable-budget.sh dec0a83c075d151ef5dec94f4005bd39ff2c2d69
editable budget OK: current=2934331/3000000 bytes headroom=65669 growth=0/262144 files=142 (file count is diagnostic only; base=142)
```

```console
$ ./senpai/validate-assignment-scope.sh 1d12077a26f3300fa0fa784105d3c6c5b8847d57 Sources/MLXFastModel/LagunaRuntimeModel.swift
assignment scope OK: 1 submitted path(s) against BASE_SHA=1d12077a26f3300fa0fa784105d3c6c5b8847d57
```

---

## 1. Host and dispatch geometry

| item | value |
| --- | --- |
| host | Apple M4 Pro, 20 GPU cores, 14 CPU, 48 GiB (low-memory startup profile) |
| OS / Metal | macOS 26.5.2, Metal 4, Apple GPU generation **16** |
| `_nax` kernels | **not selected** on gen 16 — prefill claims are out of scope here |
| toolchain | Apple Swift 6.3.3, `metal` 32023.883/884 |
| `maxThreadgroupMemoryLength` | 32768 B |
| `maxThreadsPerThreadgroup` | 1024 |

Laguna text tower: 40 layers = 10 full-attention (0, 4, 8 … 36) + 30 sliding.
`numKeyValueHeads=8`, `headDim=128`, `fullAttentionHeads=48`,
`slidingAttentionHeads=64`, `slidingWindow=512`.

* sliding decode dispatch: **32 threadgroups × 1024 threads**, gqa 8, tgmem 18432 B
* full decode dispatch: **24 threadgroups × 1024 threads**, gqa 6, tgmem 18432 B

---

## 2. Step 0 — static occupancy audit (this is the decisive result)

Tool: `research/tanjiro_occupancy_audit.swift`
(`swiftc -O research/tanjiro_occupancy_audit.swift -o /tmp/tanjiro_occ -framework Metal -framework Foundation`).

`stats` on the production kernel:

```
custom_kernel_laguna_sliding_fused_attn_ring_v1
  staticThreadgroupMemoryLength = 18432 B
  maxTotalThreadsPerThreadgroup = 1024
```

`resident 200 20000` — how many threadgroups the device actually keeps in
flight, swept over threads/TG × threadgroup memory:

| threads/TG | 1024 B | 9472 B | 16384 B | 18432 B | 32768 B |
| ---: | ---: | ---: | ---: | ---: | ---: |
| **1024** | 60 | 60 | 60 | **60** | 40 |
| 512 | 120 | 120 | 100 | 97 | 57 |
| 256 | 200 | 180 | 120 | 91 | 70 |

**At 1024 threads per threadgroup the device caps co-residency at 60 = 3
TG/core, and that cap is set by thread and simdgroup slots, not by threadgroup
memory.** Anything from 1024 B to 18432 B gives the same 60. The production
kernel's 18432 B footprint is therefore *already at maximum occupancy*.

**⇒ The mechanism R1 was assigned to exploit does not exist on Apple GPU
generation 16.** Freeing threadgroup memory cannot buy co-residency here. This
alone predicts R1's failure, and R1 then failed as predicted (§4).

Calibration note: `TANJIRO_BENCH_REPEATS` must be ≥ 200 or DVFS ramp dominates
(repeats=1 → 87 µs, repeats=200 → 20.9 µs, repeats=2000 → 20.9 µs). All timings
below use repeats=2000. The `wave` subcommand's staircase is inconclusive by
construction; that is documented in the tool header and no conclusion rests on it.

---

## 3. R0 reference

repeats=2000, iters=60, production geometry, ±0.2 µs reproducible across
re-invocations:

```
laguna_sliding_fused_attn_ring_v1  groups=32 tgmem=18432B  min=17.5-18.6us p50=20.6-20.9us p90=20.9us
laguna_full_fused_attn_grow_v1     groups=24 tgmem=18432B  min= 9.3us      p50= 9.7us      p90= 9.8us
```

**Fidelity of the sliding microbench.** My own published in-situ census
(`research/maple-tanjiro-pr73-decode-kernel-census.md`, 199 steady decode steps)
measures the sliding kernel at **19.61 µs/call**. The microbench reads
20.6–20.9 µs, i.e. it **overstates by ~5–6 %** — close enough to be a faithful
proxy for *fractional* comparisons, which is all it is used for.

**The full-attention microbench is NOT trustworthy and nothing here depends on
it.** It reads 9.7 µs against a census in-situ 23.79 µs/call — a 2.45×
understatement, most likely because the zeroed `params` buffer causes an early
loop exit. It is reported for completeness and is explicitly excluded from every
conclusion.

---

## 4. R1 — one query head per threadgroup (32 TG → 64 TG, 18432 B → 9472 B)

Generator: `research/tanjiro_make_h1.py` → `..._h1.metal` (57 796 B).

```
R0    groups=32 tgmem=18432B  p50=20.9us   reference
_h1   groups=64 tgmem= 9472B  p50=25.1us   BITWISE IDENTICAL to R0   → +20.1% SLOWER
```

The variant is **bitwise identical** to R0 at full production geometry, so this
is a pure cost result, not a numerics result.

Why it loses, measured rather than argued. Splitting the head pair duplicates
the K/V loads and the RoPE work that R0 shares between its two heads, so an
`_h1` threadgroup does not cost half an R0 threadgroup. I measured that ratio ρ
directly with the counterbalanced `pair` mode (repeats=2000, iters=40):

| groups | R0 (µs) | `_h1` (µs) | Δ |
| ---: | ---: | ---: | ---: |
| 1 | 10.113 | 7.145 | −29.2 % (p=1e-5) |
| 20 | 10.379 | 7.502 | −27.5 % |
| 40 | 21.012 | 16.506 | −23.3 % |

**ρ ≈ 0.707.** Doubling the threadgroup count pays off only if ρ < 0.5. ρ = 0.707
is not a tuning shortfall, it is arithmetic: the duplicated K/V and RoPE work is
irreducible under a head split.

Wave model check on M4: 32 TG over 20 cores ⇒ 2 waves ⇒ predicted 20.8 µs,
measured 20.9 µs. Carrying the same model to M5's 40 cores, R0's 32 TG fits one
wave while `_h1`'s 64 TG needs two at ρ=0.707, i.e. **+41 % worst case**; damping
by the model-vs-measurement factor observed on M4 gives **+20 %**. The M5
interval is therefore **+20 % to +41 % slower — the sign never turns.**

**R1: NO-GO.** Its stated mechanism is refuted by direct measurement (§2) and
its outcome is refuted by direct measurement here. Priced against the in-situ
pool (§7) this variant would *cost* **1.3 % to 2.7 % of score**.

**R1+R2 is moot.** R2's best case is a ~1 % loop gain; it cannot close a ≥20 %
geometry regression.

---

## 5. R2 — deeper K/V load pipeline (depth 2 → 4, and → 8)

Generator: `research/tanjiro_make_variants.py` → `_p4`, `_p8`.
Counterbalanced **A/B/B/A**, 120 pools, repeats=2000, iters=120, groups=32:

```
R0 vs p4:  A med=20.844us  B med=20.601us  mean(B-A)=-0.2165us (-1.039%)  med=-0.2598us  p=0.00006  BITWISE IDENTICAL
R0 vs p8:  A med=20.879us  B med=20.961us  mean(B-A)=+0.1013us (+0.485%)  med=+0.0569us  p=0.09079  BITWISE IDENTICAL
```

Depth 4 is a small, statistically clean win in *this* harness; depth 8 regresses.

### 5.1 This replicates a hypothesis the programme already closed — and disagrees with it in sign

`research/nezuko-pr-sliding-attn-load-pipeline.md` (@maple-nezuko, PR #60,
assignment `maple-2026-08-05g-sliding-attn-load-pipeline`) ran the identical
hypothesis — 2-deep → 4-deep sliding K/V load pipeline — but ported into
`LagunaRuntimeModel.swift` (net +1198 B, bitwise identical). Its verdict was
**dead hypothesis**: the −5 % primary gate was missed, delivering −1.37 % at
K=1, and critically **at K=32, the production geometry, it measured a
regression**: median ratio 1.0036 (+0.36 %), mean +0.63 % ± 0.61 %, with only
8/24 pairs below 1. Its depth-8 arm was worse than depth 4 on both axes, so the
interior optimum sits at or below depth 4 and the PR concluded "R2 is closed,
not deferred."

I measure **−1.039 % (p=6e-5)** where nezuko measured **+0.36 %**, at the same
K=32 production geometry, on the same M4 Pro machine class, with both arms
bitwise identical in both experiments, and with |effect| ≤ 1.1 % in both.

The honest reading is not that one of us is right. It is that **a ≈1 % effect at
production geometry is not sign-stable across harnesses**, which is exactly the
regime where a wall-clock microbenchmark stops being decision-grade. The prior
CLOSED verdict stands; my run does not reopen it.

**R2: NO-GO.** See §7 for the price.

---

## 6. Cost decomposition of the sliding kernel — the one genuinely new contribution

Two independent probes, both at production geometry (repeats=2000, groups=32).

**(a) Loop-bound sweep.** `research/tanjiro_make_itn.py` emits `_it1/_it2/_it4`
(main-loop bound N → 64/128/256). Diagnostics only, numerically wrong by
construction.

```
launch_probe  p50= 1.7us   (hand-written, production shape, 17408 B tgmem, no attention work)
it1 (1 iter)  p50= 7.5us
it2 (2 iter)  p50= 9.3us
it4 (4 iter)  p50=14.2us
it8 (=R0)     p50=20.8us
```

Least squares over (1, 7.5), (2, 9.3), (4, 14.2), (8, 20.8):
**slope 1.915 µs/iter, intercept 5.77 µs, R² = 0.9925.** The it1↔it8 two-point
fit agrees: slope 1.900, intercept 5.60.

**(b) Epilogue ablation.** `research/tanjiro_make_noepi.py` keeps the prologue
and the *entire* main loop and replaces only the cross-simdgroup epilogue with a
trivial store. Counterbalanced A/B/B/A, 120 pools, iters=120:

```
A = laguna_sliding_fused_attn_ring_v1
B = laguna_sliding_fused_attn_ring_v1_noepi
  groups=32 threads/TG=1024 repeats=2000 pools=120
  A median=20.841us min=17.669us
  B median=17.115us min=12.999us
  paired mean(B-A)=-3.9094us (-18.758%)  median(B-A)=-3.7440us  permutation p=0.00001
  outputs DIFFERENT
```

Two caveats, both controlled:

* `outputs DIFFERENT` is by construction; this is a cost probe, never a candidate.
* The compiler dead-codes the now-unread `outputs[4*BN*BDP]` array, so the probe
  reports tgmem = 1024 B rather than 18432 B. **This does not confound the
  result**: §2 measured 60 resident threadgroups at *both* 1024 B and 18432 B at
  1024 threads/TG, so occupancy is unchanged. And the main loop demonstrably
  survives — 17.1 µs − 1.7 µs launch = 15.4 µs, against the 8 × 1.915 = 15.3 µs
  the loop model predicts.

**Combining (a) and (b):**

| component | µs/dispatch | share |
| --- | ---: | ---: |
| launch / dispatch | ≤ 1.7 | 8.2 % |
| kernel prologue | ≈ 0 (within noise) | ≈ 0 % |
| cross-simdgroup epilogue | 3.91 | 18.8 % |
| main loop | ≈ 15.2 | 73.0 % |
| **total** | **20.84** | **100 %** |

The two probes close consistently: (a)'s 5.77 µs fixed cost = (b)'s 3.91 µs
epilogue + 1.7 µs launch = 5.61 µs. **The prologue is free; the fixed cost is
launch plus epilogue.**

### 6.1 The epilogue is structurally pinned

Reading lines 1372–1442 of the extracted kernel: the epilogue is **3 threadgroup
barriers, 2 `simd_max`, 12 `simd_sum`**, with *two* transpose rounds through
`outputs[4*BN*BDP]` because 8 planes (2 heads × 4 `v_per_thread`) have to be
funnelled through a 4-plane buffer.

* Doubling that buffer to remove the second round needs 8·32·33·4 = **33 792 B >
  32 768 B device limit**. Not available.
* Reaching it via BDP=32 lands on exactly 32 768 B, which §2 measured as
  **halving co-residency from 3 to 2 TG/core**. Strictly worse.
* Any split-D reparallelization changes the floating-point reduction order and is
  therefore **not bitwise identical** — outside the correctness envelope.

**⇒ The epilogue is pinned jointly by bit-exactness and the 32 KiB threadgroup
memory limit.** R3 (pre-barrier prefetch) targets this region; I designed it and
recommend **not building it** — §7 shows its ceiling is below the bar.

---

## 7. Pricing — intervals with stated basis

**Basis.** Per DELTA D3 the brief's point estimates (+5.16 % / +1.57 % / +6.7 %)
are retracted, because programme law §0.9.36 finds M4 wall-clock
instruction/occupancy residuals over-state M5 by up to ~12×. M4 here is
**sign-and-existence evidence only** and every figure below is an interval.

The score anchors come from my own in-situ census
(`research/maple-tanjiro-pr73-decode-kernel-census.md`, 199 steady decode steps,
`gpu_busy_sum == gpu_busy_union` to 1 µs ⇒ strictly additive per-kernel times):

* M5-eq = M4 true × 0.7565; **1 ms M5-eq decode = 14.862 % of score**
* `sliding_fused_attn_ring_v1`: 30 calls/step, M4 588.3 µs, M5-eq 445.0 µs ⇒ **6.61 % of score**
* `full_fused_attn_grow_v1`: 10 calls/step, M4 237.9 µs, M5-eq 180.0 µs ⇒ **2.68 % of score**
* combined pool: M4 826.2 µs / M5-eq 625.0 µs ⇒ **9.29 % of score**

*Reconciliation with the brief.* D3 does **not** retract the brief's "453 µs
combined M4 pool". That figure matches neither census number: the census combined
M4 pool is 826.2 µs, and 453 µs is within 1.8 % of the census **sliding-only
M5-equivalent** 445.0 µs. The brief's figure appears to be a sliding-only
M5-equivalent mislabelled as a combined M4 pool. I price against the census
because it is a published, reproducible in-situ measurement; the difference is
immaterial (445 vs 453 µs = 1.8 %).

### Sliding kernel budget, priced

| component | share of kernel | % of score |
| --- | ---: | ---: |
| launch / dispatch | 8.2 % | **0.54 %** |
| epilogue | 18.8 % | **1.24 %** |
| main loop | 73.0 % | **4.83 %** |
| sliding total | 100 % | **6.61 %** |

### The bar

Rank 1 is already ours (receipt `97a5090c`, PR #80, `officialScore =
2.58882784082067`). Per D2, promotion needs **≥ ~1 % additional `ns`**. Frontier
decode step is 4908 µs; 1 ms decode = 14.862 % of score, 1 ms prefill = 0.371 %.

### Variant pricing against that bar

| variant | M4 effect | score interval | basis | verdict |
| --- | --- | --- | --- | --- |
| **R1** `_h1` | +20.1 % (measured) | **−1.3 % to −2.7 %** (a loss) | measured M4 + wave model to 40 cores | **NO-GO** |
| **R2** `_p4` | −1.039 % (p=6e-5) | **[−0.024 %, +0.069 %]** | upper = M4 at face value; lower = nezuko #60's +0.36 % at the same K=32 geometry | **NO-GO** — 14× to ∞ short of ~1 % |
| **R2** `_p8` | +0.485 % (p=0.09) | ≈ 0, wrong sign | not significant | **NO-GO** |
| **R1+R2** | — | dominated by R1 | — | **NO-GO** (moot) |
| **R3** epilogue work | ceiling: halve the epilogue | **[≈0.05 %, 0.62 %]** | upper = half of the measured 1.24 % epilogue pool; lower = D3's ÷12 M4→M5 discount | **NO-GO** — below the bar even at the optimistic end, and §6.1 shows it is structurally unreachable bitwise |

Applying D3's ÷12 discount to R2's upper bound gives 0.0057 % of score. The
interval's honest lower bound is **negative**, because the only other
production-geometry measurement of this exact change found a regression.

---

## 8. Why this line was already closed, and why my results agree

Census §8.1 declares sliding attention **CLOSED**, and I did not find anything
that reopens it:

* @maple-nezuko #56 measured 443 GB/s = **170 % of the M4 DRAM ceiling**, i.e.
  cache-served, so the byte-movement floor is fictional. My own roofline agrees:
  388 GB/s effective against a 273 GB/s M4 DRAM ceiling.
* @maple-nezuko #68 measured the kernel at **~90 % of its issue-rate floor**,
  with **~84 of ~104 FP slot-equivalents pinned by bit-exactness**. The residual
  ~10 % is worth **≤ 0.5 % of score** against a 0.278 % MDE. The full sliding
  rewrite was **WITHDRAWN** on that basis.
* My arithmetic-intensity check concurs that the kernel is not bandwidth bound
  and not FLOP bound: 815 GFLOP/s against ~7.2 TFLOP/s peak (~11 %), i.e.
  **latency / dependency-chain bound**, which is precisely the regime where
  neither more threadgroups (R1) nor a deeper load pipeline (R2) helps.
* Census §8.2 already refutes dispatch-count reduction programme-wide (@maple-fern #48).

My new contribution is the *decomposition*: the residual is 73 % main loop
(pinned per #68), 18.8 % epilogue (pinned per §6.1), 8.2 % launch. Every slice is
either already at its floor or structurally unreachable without breaking
bit-exactness.

---

## 9. Correctness evidence

### 9.1 Bitwise oracle at production geometry

Every candidate variant was diffed bit-for-bit against R0's output buffer at the
full production dispatch (groups=32, 1024 threads/TG):

| variant | oracle result |
| --- | --- |
| `_p4` | **BITWISE IDENTICAL to R0** |
| `_p8` | **BITWISE IDENTICAL to R0** |
| `_h1` | **BITWISE IDENTICAL to R0** |
| `_it1/_it2/_it4`, `_noepi`, `launch_probe` | intentionally DIFFERENT — cost probes, never candidates |

### 9.2 Upstream equivalence — run at the unchanged base

Per D5, run through the mandatory wrapper, never a bare `swift test` filter:

```console
$ bash research/run_upstream_equivalence.sh        # exit 1, 83.6 s
```

* **1 test selected and executed** — `lagunaRuntimeMatchesVendoredUpstreamOnM5WhenEnabled`
  — with the report marker present, so this is a real invocation and not a
  zero-test pass.
* `EQUIVALENCE_EXACT_STEPS=8`, `EQUIVALENCE_EXIT=1`.
* All **8 decode steps: `maximumAbsoluteLogitError = 0`**, tokens match exactly.
* **prefill step: `maximumAbsoluteLogitError = 0.125`,
  `meanAbsoluteLogitError = 0.011933609`, but `runtimeToken == upstreamToken == 5991`**
  — the greedy token is identical; the failure is the zero-tolerance assertion at
  `LagunaCorrectnessTests.swift:249`.

**This was run with `Sources/` clean at the unchanged base.** It is therefore a
pre-existing non-M5-host divergence, not something my work caused. AGENTS.md's
instruction is "if a non-M5 host disagrees with a public golden, test the
unchanged base" — the unchanged base *is* what was tested, and it is what
diverges. I did **not** set `MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT=1`; it records
failure and never relaxes official gates.

### 9.3 The D5 `golden_hash` / `harness_hash` citation — an honest gap, plus a warning about the metric itself

D5 requires citing an identical `golden_hash` under a **differing**
`harness_hash`. **I cannot produce that pair for my own work, because I am
proposing no submitted-surface change** — with `Sources/` byte-identical to
base there is no second harness to differ. The standing runtime-level evidence
for the only variant that was ever a candidate (depth-4 pipeline) is
@maple-nezuko PR #60's bitwise-identity receipt for that exact port into
`LagunaRuntimeModel.swift`. This PR's own correctness evidence is §9.1's
microbench bitwise oracle plus §9.2's oracle run at base.

What I *can* contribute is the corpus statistic, which cuts both ways. Across
every score JSON checked into `research/` on this host:

```
distinct golden_hash values across 86 score files:
  b9509697c08a  n=86
b9509697c08a -> distinct harness_hash count: 18
```

**86 score files, 18 distinct `harness_hash` values, exactly 1 `golden_hash`.**

* *Supportive reading:* the golden output has been invariant across 18 distinct
  harness builds on this host, which is the pattern D5 asks a bitwise-identical
  change to exhibit.
* *Warning, and I think this is the more important reading:* **this corpus
  contains no negative control.** `golden_hash` has never once been observed to
  differ, so nothing in our archive demonstrates that it *would* move if a change
  genuinely broke numerics. An always-constant field is weak evidence of
  correctness until someone deliberately produces a mismatching pair. I flag this
  as a programme-level gap, not as a claim about my own work.

Host reference hashes from `./benchmark.sh --local-iterate` at the unchanged
base are recorded in §11.

### 9.4 The five traps (D5 requires an explicit statement on each)

1. **Zero-test pass.** Not applicable — the wrapper reported **1 test selected
   and executed** with the report marker present (§9.2).
2. **`max_abs_diff` cited as correctness evidence.** Explicitly **not** relied
   on. §9.2 quotes `maximumAbsoluteLogitError` as *diagnostics only*; the
   correctness claims in this report rest on bitwise buffer identity (§9.1) and
   on the exit status and token equality of the wrapper run.
3. **Bare `swift test` filter instead of the wrapper.** Not committed — the only
   invocation was `bash research/run_upstream_equivalence.sh`.
4. **Fixture / near-tie specialization.** Not applicable — no submitted-surface
   change exists to specialize, and every variant that was ever a candidate is
   bitwise identical to R0, so no near-tie argmax can move.
5. **Cross-machine extrapolation presented as an M5 result.** Explicitly guarded:
   this host is Apple GPU generation **16**, does **not** select `_nax` kernels,
   so nothing here is prefill evidence; every M5 number in §7 is an **interval
   with a stated basis**, never a point estimate, per D3.

---

## 10. Attribution method — a stated substitution

The brief asks for `research/decode_probe.py --steps 200 --profile
--profile-top 44` under `DARKBLOOM_GPU_PROFILE=1`, then a revert of the profile
hooks with the revert SHA reported.

**That is not re-runnable as specified on this branch.** The
`DARKBLOOM_GPU_PROFILE` hooks are local-only patches to
`Vendor/mlx-swift/.../device.cpp|.h`; they were reverted after PR #73 and are
not present here. Re-applying them would touch `Vendor/`, which D7 places
outside this PR's submitted surface.

**Substitution, stated explicitly:** I use the already-published output of that
exact procedure — `research/maple-tanjiro-pr73-decode-kernel-census.md`, 199
steady decode steps, with `gpu_busy_sum == gpu_busy_union` agreeing to 1 µs so
per-kernel times are strictly additive. That census is the pricing basis in §7
and is my own prior published measurement on this same host.

---

## 11. Fresh unchanged host baseline

<!-- LOCAL_ITERATE_RESULTS -->

---

## 12. Budget and fences (D7)

* Submitted surface for this PR: **`Sources/MLXFastModel/LagunaRuntimeModel.swift`
  only** — and it is **untouched**. All artifacts are under `research/`.
* Net submitted growth: **0 B** of the 262 144 B per-review allowance;
  65 669 B of total headroom remains untouched.
* The ~20 kB "stop and ask" threshold for R1 was never approached — R1 was
  refuted by measurement before any port was attempted.
* Ownership fence respected: @maple-frieren owns `gate_sp`
  (`lagunaGateSoftplusSource`, ~:4275) and the o_proj lane-major scale path
  (~:4135-4155) in this file (PR #101). I edited neither, and in fact edited
  nothing in that file.

## 13. Submission status (D4)

**Not submitted.** D4 prohibits `mlxfast submit` for this PR and cancels §3
Step 4. §3 Step 5 — porting to the full-attention kernel as a separate PR — is
also **not recommended**, because the mechanism refuted in §2 and §4 is
geometry-general and the full kernel's 24 TG × 1024 threads sits under the same
3 TG/core cap.

---

## 14. Recommendation

**Close the sliding-attention occupancy line.**

* R1's mechanism does not exist on this GPU generation (§2) and its outcome is a
  measured 20 % regression (§4).
* R2 replicates a hypothesis the programme already closed and cannot even
  reproduce its sign at production geometry (§5.1); priced at ≤0.069 % against a
  ~1 % bar.
* R3's entire addressable pool is 1.24 % of score, its realistic ceiling is
  0.62 %, and §6.1 shows the epilogue is jointly pinned by bit-exactness and the
  32 KiB threadgroup-memory limit.

Nothing in the sliding-attention kernel is worth another allocation. The
decomposition in §6 — 73 % main loop at ~90 % of its issue floor, 18.8 %
structurally-pinned epilogue, 8.2 % launch — should be reused to *avoid*
re-opening this line rather than to plan another attempt at it.

### Suggested follow-ups I did **not** implement

1. **The 8.2 % launch slice (0.54 % of score) is the only unpinned part of this
   kernel.** It is not attackable inside the kernel, but it is the same pool
   @maple-fern #48 probed from the dispatch-count side. A command-buffer /
   encoder-reuse angle is a different mechanism from dispatch-count reduction
   and was not tested by #48. Still below the bar alone; only interesting bundled.
2. **The sign instability in §5.1 is a tooling finding, not a kernel finding.**
   Two harnesses disagree in sign on a ~1 % effect at production geometry. The
   programme currently prices sub-1 % microbench deltas as real; that practice
   deserves an explicit MDE floor.
3. **The prefill axis is untested on this host** (gen 16 does not select `_nax`).
   Any prefill-side claim about these kernels needs M5 time.
