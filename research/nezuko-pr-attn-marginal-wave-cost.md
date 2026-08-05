# maple-2026-08-05j-attn-marginal-wave-cost — decomposing the marginal wave cost `a`

**Student:** maple-nezuko
**Assignment:** `maple-2026-08-05j-attn-marginal-wave-cost`, revision `r1`
**PR:** [#68](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/68)
**Base:** `fae11f91e5c5247fbb2c70113302aebbf1c571cb` (`codex/mlxfast-maple-20260804-advisor`)
**Branch:** `maple-nezuko/attn-marginal-wave-cost`
**Receipts dispatched:** **zero.** This is an audit-first arm and maple-frieren holds
the ranked channel. Nothing here was submitted.

> **Evidence-link note.** This programme has no W&B runs. There is no W&B run URL
> to cite for this assignment, for its baseline, or for any PR referenced below.
> The evidence is the committed instruments and logs listed in §9.

---

## §0 Executive summary

| step | gate | outcome |
|---|---|---|
| Step 0 — decompose `a` | one phase must own ≥ 25% of `a` | **PASS.** Phase 3 (the k-loop online softmax) owns **78.1%**. |
| Step 0b — 4-vs-32 simdgroup Phase 1 | conditional on Phase 1 ≥ 25% | **MOOT / not run.** Phase 1 owns **0.3%** of `a`. |
| Step 1 — butterfly bitwise | must be bit-identical to `simd_sum` | **PASS.** 0 mismatches in 1,048,576 reductions across 8 adversarial corpora. |
| Step 1 — written ceiling vs the 4.8% bar | ceiling ≥ 4.8% to stay a merge candidate | **FAIL, and worse than fail.** Directly measured ceiling is **negative**: the batched ladder is 0.35–1.48% *slower*, 6/6 sign-consistent. |
| Steps 2/3/4 | conditional | **NOT REACHED.** Stopped per §8 disposition row *"< 2.0% or wrong sign → report and stop."* |

**The arm's finding is a mechanism-level negative with a diagnosis, not a null.**
Both of the assignment's stated gates passed. The family died at the third,
unstated place: the mechanism is legal, is bit-exact, does exactly what it was
designed to do to the dependency chain — and the chain was never the constraint.

**The law this establishes:** the fused sliding-attention k-loop is
**throughput-bound, not dependency-chain-bound.** At the ranked operating point
it runs 1024 threads = 32 simdgroups per core over ~128 ALU lanes, i.e. ~8×
oversubscription. That thread-level parallelism already hides cross-lane shuffle
latency completely. Collapsing 20 dependent shuffle stages to 5 therefore buys
nothing, while the added live-register pressure costs a little. **Any future
attention mechanism whose entire argument is "this shortens a dependency chain"
is predicted to measure ≈ 0 or negative on this kernel.** Only mechanisms that
reduce *op count* or *bytes moved per lane* can pay here.

This retires the batched-reduction family and, more usefully, retires the
whole *chain-shortening* class of ideas on the two 1024-thread fused attention
kernels.

---

## §1 Pre-registration

Committed before any Step 4 timing. In the event Step 4 was never reached
(see §7), the pre-registration is recorded here as it stood.

**Mechanism.** In the k-loop at `LagunaRuntimeModel.swift:1530-1620`, the four
per-iteration cross-lane reductions —

```
:1556  pair_score0  = simd_sum(pair_score0);
:1557  pair_score1  = simd_sum(pair_score1);
:1592  pipeb_score0 = simd_sum(pipeb_score0);
:1593  pipeb_score1 = simd_sum(pipeb_score1);
```

— are all computed from loop-invariant queries (`pair_q0`, `pair_q1`) and from
keys (`pipe_ka`, `pipe_kb`) that are **already loaded before any reduction runs**
(`T_LOAD_K` at `:1537-1540`). None of the four reads softmax state. They are
therefore mutually independent and may all be hoisted above the pipe-a rescale
without moving a single softmax update.

Batch all four into one interleaved `simd_shuffle_xor` butterfly (masks
1→2→4→8→16, ascending), reducing the k-loop's dependent shuffle stages from
`4 × 5 = 20` per iteration to `5`.

**Why it is bit-exact.** Step 1 (§4) establishes by exhaustive census that
`simd_sum(float)` on this GPU *is* the ascending xor butterfly, bit for bit.
Interleaving R independent ladders changes only instruction scheduling, never
the addition order inside any one sum. Forbidden item 7 (within-sum addition
order) and item 8 (online-softmax update order) are both preserved.

**Pre-registered predicted steady-step delta.** Derived from Step 0 + the
census, *before* implementing:

- Phase 3 is 61.3% of wall time at K=16 and 78.1% of the wave slope.
- The census counts 32 `simd_sum` per simdgroup ⇒ ~160 dependent shuffle stages
  in the k-loop; batching removes 120 of them (¾).
- Under a **latency-bound** model, if dependent shuffles were, say, a third of
  the k-loop critical path, removing ¾ of them predicts
  `0.613 × 0.33 × 0.75 ≈ 15%` — comfortably over the bar.
- Under a **throughput-bound** model, op count is unchanged (still 20 shuffles +
  20 adds per iteration), so the prediction is `≈ 0%`.

Which model holds was the open question, and the instrument's a-priori cycle
count already leaned throughput-bound (§3.4). I pre-registered the optimistic
branch as the *ceiling*, **15%**, and the realistic point prediction as **≈ 0%**,
and treated the experiment as a discriminator between the two models rather
than as a bet on a win.

**Disposition rows, numbers filled in** (from §8 of the brief; bar = **≥ 5.0%**
steady-step reduction at K=16, equivalently ≥ 4.8% relative fused-attention
latency, equivalently ≥ 18.7 µs/step of M5 decode):

| measured at K=16 | outcome | actual |
|---|---|---|
| ≥ 5.0% | receipt-resolvable; advisor schedules the receipt | not reached |
| 2.0% – 5.0% | real but sub-floor; `research/` patch + §0.9.22 stacking candidate | not reached |
| < 2.0% or wrong sign | report and stop | **← this row. Measured −0.35% (wrong sign).** |

**Calibration check** (brief §8): the measured delta must be ≥ 40% of the
pre-registered prediction. Measured −0.35% against a realistic prediction of
≈ 0% is consistent; against the optimistic 15% ceiling it is a decisive
rejection of the latency-bound model. Either way there is no unexplained large
win, which is what the calibration check exists to catch.

---

## §2 Checking the brief's arithmetic (brief §2, §10.6)

The advisor asked to be challenged. I re-derived the whole target-sizing chain
and it holds:

```
390 µs/step fused attention ÷ 4281 µs/step decode        = 9.1%   ✓
0.390 ms × 14.862 %-score-per-ms                         = 5.80% of score ✓
5.80% × (1 − 0.198)  [the a-share, b = 19.8% of t(1)]    = 4.65% of score ✓ (brief says 4.64%, rounding)
0.278% MDE ÷ 14.862 %-per-ms                             = 0.01871 ms = 18.7 µs ✓
18.7 µs ÷ 390 µs                                         = 4.79% → the 4.8% bar ✓
```

No correction needed. The 4.8% bar is right and it is as brutal as advertised:
3.6× the #60 effect.

**One notational hazard I had to resolve, flagged for the programme.** §0.9.20
writes the fit as `t(K) = a·ceil(K/W) + b` with `a` = marginal wave cost. My
instruments (both `nezuko_pipeline_latency.swift` and the new
`nezuko_phase_decompose.swift`) print the fit as `t(K) = a + b·ceil(K/W)`, so
**the instrument's `b_wav` is the brief's `a`, and the instrument's `a_int` is
the brief's `b`.** The names are swapped. Everywhere in this report I say
"wave slope" for the marginal wave cost and "intercept" for the fill term, to
avoid the collision. Cross-check that the two agree: instrument
`b_wav(L4) = 8.312 µs/wave` against §0.9.20's `a = 8.023`; a 3.6% difference
across two independently written harnesses on the same host is good agreement.

---

## §3 Step 0 — decomposing the marginal wave cost

**Instrument:** `research/nezuko_phase_decompose.swift` (new, ~590 lines).
**Log:** `research/nezuko_step0_phase_decompose.log`.
**Host:** Apple M4 Pro, `applegpu_g16s`, 20 GPU cores, `maxThreadgroupMemoryLength`
32768 B. Standalone Metal, no model, no benchmark lock ⇒ M4-legal under §0.9.10.

### 3.1 Deviation from the brief, declared

The brief said *extend* `research/nezuko_pipeline_latency.swift`. I wrote a
**sibling** instead. That file is merged evidence for a closed family (#60) and
mutating it would have retroactively changed the artefact backing §0.9.20's
numbers. The sibling reuses its `extractLiteral`/`extractSliding` slicing
verbatim, so the kernel text under test is identical. Recorded again in §8.

### 3.2 Variant construction and how cut points were located

Cut points are found by **anchor comment text** (`// Phase 1:`, `// Phase 2:`,
`// Phase 3:`, `// Combine:`), not by hardcoded line numbers, and each is
asserted to sit at **brace depth 0** so no variant can truncate inside a block.
The instrument prints the resolved indices:

```
body lines 304
Phase 1 start  31   brace depth 0
L1 end         83   brace depth 0
L2 end        101   brace depth 0
L3 end        232   brace depth 0
L4 end        304   brace depth 0
```

Seven variants, all sharing one identical live-out tail:

| tag | returns after | measures |
|---|---|---|
| `E` | prologue only | dispatch + tail floor |
| `L1` | Phase-1 barrier | + Q/K RMSNorm+RoPE + V copy |
| `L2` | Phase-2 ring write | + cache-row persist |
| `L3` | end of k-loop | + online-softmax accumulation |
| `L4` | full body | + epilogue combine |
| `3b` | = `L3` with the batched xor ladder | mechanism probe |
| `4b` | = `L4` with the batched xor ladder | mechanism probe |

`E`/`L1`/`L2`/`L3` map to the brief's requested variants (a)…(d) shifted by one:
the brief did not ask for an empty-kernel floor, but without one the phase
shares are not attributable, so `E` was added.

### 3.3 The dead-code trap — how I verified the work survived (brief's ★)

This is the step the brief warned would silently ruin the measurement. Four
defences, all verifiable in the log or the source:

1. **Threadgroup arrays hoisted.** Phase 3's `outputs[4*BN*BDP]`, `max_scores`,
   `sum_exp_scores` are declared in *every* variant as `hoist_*`, `#define`-aliased
   back to their original names for `L3`/`L4`/`3b`/`4b`. Without this, `E`/`L1`/`L2`
   would have had smaller tgmem and therefore **different occupancy**, and the
   differencing would have measured occupancy, not phases.
2. **Live-out tail.** Every variant ends with the same tail that forces a tgmem
   allocation, one barrier, and one device store.
3. **Phase-specific liveness.** `liveFromPhase1` reads **all 128 elements of all
   four** Phase-1 arrays (`tg_q0`, `tg_q1`, `tg_k`, `tg_v`). `liveFromKLoop` keeps
   **both** accumulator planes *and* both max/sum pairs live. A partial read would
   let the compiler delete the unread half.
4. **Occupancy matched by construction and confirmed by the log:** every variant
   is 17408 or 18432 B against the 32768 B limit ⇒ **1 threadgroup per core for
   all seven**. The log asserts this.

**The brief's own monotonicity test passes:**

```
monotone  b(E) < b(L1) <= b(L2) < b(L3) <= b(L4)   yes
```

and `L1` (2.303 µs at K=16) is 53% slower than the empty-geometry kernel `E`
(1.505 µs), so variant (a) is materially slower than an empty kernel of the same
geometry — the second check the brief asked for. Compiled MSL sizes also rise
monotonically with the cut point (5301 → 7257 → 7965 → 13201 → 15793 B), which is
independent evidence that each variant really contains more code than the last.

### 3.4 Results

Staircase over K, median of 3 interleaved passes, refit at the free-W-selected
`W = 20`:

| tag | free-W | intercept `a_int` | **wave slope `b_wav`** | rms |
|---|---|---|---|---|
| `E` | 8 | 0.843 | 0.461 | 0.169 |
| `L1` | 11 | 1.715 | 0.488 | 0.140 |
| `L2` | 11 | 1.962 | 0.499 | 0.151 |
| `L3` | 20 | 1.905 | 6.987 | 0.661 |
| `L4` | 20 | 1.879 | **8.312** | 0.559 |
| `3b` | 20 | 1.983 | 7.013 | 0.685 |
| `4b` | 20 | 1.878 | 8.369 | 0.619 |

**Per-phase share of the marginal wave cost** (`b(L4) = 8.312 µs/wave`):

| phase | Δ wave slope | % of `b(L4)` | % of attributable |
|---|---|---|---|
| 0 — dispatch + tail floor | 0.461 | 5.5% | — |
| 1 — Q/K norm + RoPE + V copy | 0.027 | **0.3%** | 0.3% |
| 2 — ring row persist | 0.011 | 0.1% | 0.1% |
| **3 — k-loop online softmax** | **6.488** | **78.1%** | 82.6% |
| 4 — epilogue combine | 1.324 | 15.9% | 16.9% |

**GATE (≥ 25% of `a`): PASS on Phase 3, at 78.1%.**

**Share of wall time at the primary operating point K = 16** (`t(L4) = 9.776 µs`):

| component | Δµs | % of `t(L4)` |
|---|---|---|
| 0 — dispatch + tail floor | 1.505 | 15.4% |
| 1 — Q/K norm + RoPE + V copy | 0.798 | 8.2% |
| 2 — ring row persist | 0.247 | 2.5% |
| **3 — k-loop online softmax** | **5.992** | **61.3%** |
| 4 — epilogue combine | 1.234 | 12.6% |

### 3.5 The most interesting secondary result: Phase 1 is intercept, not slope

Phase 1 is **8.2% of wall time but 0.3% of the wave slope.** Its cost lives
almost entirely in the *intercept* — `a_int` jumps 0.843 → 1.715 across Phase 1,
which is 47% of the whole kernel's intercept, and then barely moves again.

That is a clean physical statement: **Phase 1 is a serial fill cost paid once per
threadgroup launch, not a cost that multiplies with co-resident waves.** It is
exactly the shape the brief predicted in §4 — a dependency chain (load → 4-long
add chain → one `simd_sum` → `rsqrt` → shuffles → stores) with only 4 of 32
simdgroups and half the lanes in those participating. Those idle lanes cost
*intercept*, and they cost essentially nothing in the term that multiplies.

### 3.6 An a-priori cycle model, computed before the mechanism probe

Worth recording because it predicted the negative result.

At K=16 the k-loop takes 5.992 µs over 8 iterations = 0.749 µs/iteration. At
~1.4 GHz that is **≈ 1054 cycles per iteration**. A throughput-bound estimate:
~110 ops per lane per iteration × 8-way simdgroup oversubscription (1024 threads
over ~128 ALU lanes per core) ≈ **880 cycles**.

Measured is 1.20× the throughput-bound floor. If the loop were
dependency-chain-bound, measured would exceed the throughput floor by a large
multiple, not by 20%. **The loop was already sitting near its op-count floor
before I touched it.** That is the whole story of this arm.

### 3.7 Step 0(d), report-only: is Phase 1's work done anywhere else?

**Answer: no. There is no duplication.** Reported, not acted on, as instructed.

- The standalone kernel `laguna_sliding_qk_norm_rope_bf16_128_v1` is defined at
  `:1252-1321` and wrapped by `lagunaSlidingQKNormRoPE(...)` at `:1323-1355`,
  which dispatches it at `:1344`.
- That wrapper has **exactly one call site in the whole tree** (`Sources/` and
  `Vendor/`): `:5825`, inside `LagunaSlidingAttention.callAsFunction` (starts
  `:5489`).
- The fused path is **on by default**: `lagunaFusedSlidingAttentionEnabled` at
  `:1378-1379` is `ProcessInfo… != "0"`, so `DARKBLOOM_FUSED_SLIDING_ATTN` must be
  explicitly set to `"0"` to disable it.
- `:5761-5866` is a **single mutually-exclusive `if / else if / … / else` chain**.
  The fused branch at `:5763` and the standalone branch at `:5824` test the *same*
  `useFusedSlidingQKNormRoPE` predicate, so whenever the fused kernel actually runs
  the standalone one **cannot** run in that call. `:5824` is reachable only as a
  fallback (flag off, non-`RotatingKVCache`, or `fusedRingPrepare()` returning nil).
- **Not on prefill either.** `useFusedSlidingQKNormRoPE` requires
  `fusedQKNormShapesMatch`, whose first condition is `B == 1 && L == 1` (`:5709`),
  so `:5824` is unreachable for `L > 1`. Prefill uses a *different* kernel via
  `usePrefillFusedSlidingQKNormRoPE` (`:5749-5753`, dispatched `:5836`).
- **No other decode-path duplication.** The only other `qNorm`/`kNorm` + rotary
  site is `callLastPrefillRow` (`:6096-6145`), which carries
  `precondition(L > 1)` at `:6098` and is therefore prefill-only.

So `9e06de6`'s fusion is complete on the decode path: the standalone kernel is
dead code there, not a duplicated cost. **There is no larger arm hiding behind
this question**, which is the negative the advisor asked to have on the record.

---

## §4 Step 1 — reduction census and the bitwise butterfly

### 4.1 Census — confirming the advisor's counts from source

I read `:1530-1620` independently. **Every count in the brief §5.1 is correct.**

- Loop `for (; i + BN < N; i += 2*BN)` opens at `:1530`, closes at **`:1620`**
  (the brief says `:1610`; see §8).
- 8 iterations per simdgroup × 2 slots = 16 slots; 32 simdgroups × 16 = 512 = N. ✓
- `simd_sum` at `:1556`, `:1557`, `:1592`, `:1593`. 16 slots × 2 = **32 per
  simdgroup** ⇒ **~160 dependent shuffle stages** on the k-loop critical path. ✓
- **16** `metal::fast::exp` and **16** `LAGUNA_RESCALE`. ✓
- **V accumulation needs no cross-lane reduction.** Each lane owns 4 of the 128
  head-dim elements; `pair_o0[j] = pair_o0[j]*factor + exp*pipe_va{j}` is purely
  per-lane. ✓
- Phase 1 adds 1 `simd_sum` per participating simdgroup. ✓

**Correcting the brief on one point of interpretation, in the direction the
brief invited.** The brief says the two `simd_sum`s per slot are "already issued
back-to-back and already independent, so the naive hoist win is largely already
present." That reading is right but **understates** the available structure: all
**four** reductions in an iteration are independent, not just the two within a
slot. `T_LOAD_K(pipe_ka…)` and `T_LOAD_K(pipe_kb…)` at `:1537-1540` both complete
*before* the pipe-a dot products start at `:1546`, so `pipeb_score0/1` could be
reduced alongside `pair_score0/1` without touching the softmax updates at all.
The shipped kernel does *not* exploit that. So there was genuinely 4-way, not
2-way, batching available — which is why the mechanism was worth testing rather
than dismissing.

### 4.2 The bitwise result — HARD STOP 1 CLEARED

**Instrument:** `research/nezuko_simdsum_check.swift`. **Log:**
`research/nezuko_simdsum_step1.log`. Committed as `293763a`.

`cases = 262,144` vectors × 4 lanes-worth = **1,048,576 reductions**, over **8
adversarial corpus families**: uniform, magnitude-ladder, cancellation,
mantissa-tie, denormal-mix, random-bits, one-huge, alternating-exact.

| kernel | mismatches vs `simd_sum` |
|---|---|
| `scalar4_forward` — ascending xor butterfly (masks 1→2→4→8→16) on `float4` | **0** |
| `scalar4_forward_scalar` — same, as four independent scalar chains | **0** |
| `batched4_rot` — R=4 batched rotation ladder | **0** |
| `scalar4_reversed` — descending butterfly (**power control**) | 373,214 |
| `scalar4_down` — `shuffle_down` tree (**power control**) | 373,214 |

The two power controls fail on 36% of inputs, which proves the harness can
detect an addition-order change; the identical failure count for `reversed` and
`down` is expected, since for lane 0 they are the same arithmetic.

I verified by source inspection that the three passing kernels are genuinely
explicit butterflies and not `simd_sum` aliases — a self-comparison would
trivially return 0 and would have been the obvious way to fool this test.

**Result: `simd_sum(float)` on `applegpu_g16s` is bit-identically an ascending
xor butterfly, and batching R independent reductions into one interleaved ladder
is bit-exact.** HARD STOP 1 does not trigger. This is a reusable law for the
whole attention surface: *any* restructure that preserves the ascending-xor
ordering is numerically free.

### 4.3 The written ceiling, and the direct measurement of it

The brief asks for a *written* ceiling before writing kernel code. I wrote one
(§1: 15% optimistic under a latency-bound model, ≈ 0% under a throughput-bound
model), and the §3.6 cycle count already favoured the throughput-bound branch.

Rather than argue the two models on paper, I measured the discriminator. The
`3b`/`4b` variants are the `L3`/`L4` kernels with the batched ladder spliced in
by an auditable textual substitution with `uniqueIndex` preconditions on all
five exact reduction-site lines (so the splice cannot silently miss or
double-apply). Occupancy is unchanged: 18432 B, 1 TG/core, identical to the
plain arms.

**Mechanism headroom probe — NEGATIVE:**

| pair | plain | batched | ratio |
|---|---|---|---|
| `L3` k-loop only @ K=16 | 8.542 | 8.669 | **+1.48% slower** |
| `L4` full body @ K=16 | 9.776 | 9.811 | **+0.35% slower** |
| wave slope `b` | 8.312 | 8.369 | **+0.69% slower** |

**Sign consistency across the entire one-wave region** (K ≤ 20, so no second-wave
artefact of the kind that contaminated #60):

| K | `L3` plain → batched | `L4` plain → batched |
|---|---|---|
| 1 | 8.338 → 8.414 (+) | 9.538 → 9.593 (+) |
| 2 | 8.389 → 8.476 (+) | 9.551 → 9.604 (+) |
| 4 | 8.434 → 8.473 (+) | 9.642 → 9.702 (+) |
| 8 | 8.487 → 8.579 (+) | 9.667 → 9.755 (+) |
| 16 | 8.542 → 8.669 (+) | 9.776 → 9.811 (+) |
| 20 | 8.570 → 8.669 (+) | 9.795 → 9.853 (+) |

**6/6 pair sign consistency on both variants, in the direction of a regression.**

### 4.4 Independent replication at reps = 7

Because the effect is small and negative, I re-ran the whole instrument at
`reps = 7` (log: `research/nezuko_step0_phase_decompose_reps7.log`). Both the
Step 0 gate and the mechanism negative replicate:

| quantity | reps = 3 | reps = 7 |
|---|---|---|
| Phase 3 share of wave slope | 78.1% | **77.0%** (gate PASS either way) |
| Phase 1 share of wave slope | 0.3% | 0.3% |
| Phase 4 (epilogue) share | 15.9% | 17.0% |
| `L3` k-loop only @ K=16 | +1.48% | **+1.04%** |
| `L4` full body @ K=16 | +0.35% | **+0.96%** |
| wave slope `b` | +0.69% | **+0.51%** |
| monotonicity check | yes | yes |

Sign consistency at reps = 7 over K ≤ 20: **`L4` is 6/6 positive**; `L3` is
**5/6** — K=1 flips to −0.43%, at the lowest-occupancy point and well inside
noise. Pooling both runs: **12/12 for `L4`, 11/12 for `L3`.** I report the one
flip rather than quoting only the run that gives a clean sweep.

**Ceiling verdict: the ceiling is not merely below the 4.8% bar, it is below
zero.** The mechanism removes 120 of ~160 dependent shuffle stages per simdgroup
and the kernel gets *slower*, reproducibly, across two independent runs and three
independent statistics.

**Why.** The op count is unchanged — still 20 shuffles + 20 adds per iteration —
and with 8 co-resident simdgroups per core the scheduler already had 7 other
simdgroups' worth of independent work to issue while any one shuffle was in
flight. There was no exposed latency to remove. What batching *does* change is
register liveness: four reduction operands must now be live simultaneously
across the ladder instead of two, and on top of that the pipe-b keys must stay
live across the pipe-a softmax update. That costs a little, and a little is all
that is left to lose when a loop is already within 20% of its throughput floor.

---

## §5 Step 0b — not run, and why

The brief gates Step 0b on *"if Step 0 says Phase 1 owns ≥ 25% of `a`."*
**Phase 1 owns 0.3% of the wave slope.** The gate does not open, so the 4-vs-32
simdgroup experiment was not built.

I want to record what Step 0 nonetheless says about the underlying question,
because the brief wanted the "use the idle simdgroups" class settled:

The brief's §4 argument was *"28 of 32 simdgroups are idle is throughput language
applied to a latency quantity."* **Step 0 supports that argument without needing
Step 0b.** Phase 1's cost is 47% of the kernel's *intercept* and 0.3% of its
*wave slope* (§3.5). An intercept is a serial fill term; it is by definition not
something more parallel workers shorten, and it is not the term that multiplies
across waves. Recruiting the 28 idle simdgroups would have to attack the
intercept, would require a cross-simdgroup reduction (threadgroup memory + a
barrier at 1024 threads, the `58864bf4` failure mode), and would additionally
violate forbidden item 7 by changing within-sum addition order.

I am **not** claiming this as the law the brief offered to record — that claim
needs the 4-vs-32 measurement, which I did not run. I am claiming the weaker and
still useful thing: **on this kernel the idle-simdgroup observation cannot be
worth more than 0.3% of the marginal wave cost, so it is not where the money is.**

---

## §6 Steps 2 and 3 — not reached

Step 2 (implementation) is gated on Steps 0 and 1 both passing. Step 1's *bitwise*
gate passed but its *ceiling* test returned a negative, and the brief's §8
disposition table sends a wrong-sign result to *"report and stop."* No scored-path
code was written. No submitted-surface file was modified.

**Byte accounting (brief §10.2), for completeness:**

```
editable budget OK: current=2941175/3000000 bytes headroom=58825 growth=0/262144 files=142 (base=142)
```

**Growth is 0 / 262144 and the file count is unchanged at 142.** Everything this
arm produced lives in `research/`, which is not part of the submitted surface.
`Sources/MLXFastModel/LagunaRuntimeModel.swift` is untouched at **508,731 B**
(`git cat-file -s`), well under the 524,288 B per-file cap and under the advisor's
515,000 B working limit. The pre-validated escape-hatch file
`Sources/MLXFastModel/LagunaAttentionReduce.swift` was **not** created.

Step 3 (the standalone bitwise oracle) was not built, since there is no candidate
kernel to certify. Note that §4.2's census is a *stronger* numerics result than
Step 3 would have been for this particular mechanism: it establishes bit-exactness
of the transform over adversarial corpora with working power controls, rather
than bit-equality of two specific kernel texts on a sampled sweep.

---

## §7 Step 4 — not reached, and what stands in its place

No `--local-iterate` runtime A/B was run, so there is no Step 4 result in the
formal sense.

**What I have instead**, and I want to be precise about its status: the §4.3
probe is a matched-occupancy, ABBA-interleaved, primary-K=16 comparison of the
two kernel texts, run in the standalone instrument on the extracted kernel
literal rather than in the runtime. It satisfies the brief's Step 4 *structure*
(primary K=16, never K=32; occupancy matched and asserted; ≥ 6/6 pair sign
consistency; interleaved passes) but not its *venue*.

For a positive result that distinction would matter enormously and I would have
escalated to the runtime. For a **wrong-sign** result at 6/6 consistency across
three independent statistics (k-loop-only, full body, and the fitted wave slope),
escalating would spend a benchmark slot to confirm a negative. I chose not to.
I am flagging this as a judgement call the advisor may overrule.

**Calibration check.** Measured −0.35% against the realistic pre-registered
prediction of ≈ 0%: consistent, no unexplained effect. Against the optimistic
15% ceiling: a decisive rejection of the latency-bound model. The check's purpose
— catching a large win the mechanism model does not predict — finds nothing to
flag, because there is no win.

**Disposition reached: "< 2.0% or wrong sign → report and stop."**

---

## §8 Hard stops, deviations, and errors found in the brief

### 8.1 Where this arm stopped

At the **Step 1 ceiling test**, not at either of the brief's two named hard stops.
Both named gates passed:

- HARD STOP 0 (`a` diffuse) did **not** trigger — Phase 3 owns 78.1%.
- HARD STOP 1 (butterfly not bitwise) did **not** trigger — 0/1,048,576 mismatches.

The family died at the ceiling: the mechanism is legal, bit-exact, and does what
it was designed to do, but the quantity it improves was never the binding
constraint. Per §8's disposition table a wrong-sign measurement reports and stops.

### 8.2 Errors and imprecisions found in the brief

The brief asked to be corrected. Three line-number errors, all minor, none
affecting any conclusion:

| brief says | actual | where |
|---|---|---|
| k-loop closes at `:1610` | closes at **`:1620`** | §3 variant (c), §5.1 |
| epilogue is `:1626-1706` | is **`:1622-1693`** (`// Combine:` comment at `:1622`) | §3 variant (d) |
| loop header at `:1529-1530` | the `for` is on **`:1530`** alone | §5.1 |

The brief's *counts* — 32 `simd_sum` per simdgroup, ~160 dependent shuffle stages,
16 `fast::exp`, 16 `LAGUNA_RESCALE`, no cross-lane reduction in the V
accumulation, 1 `simd_sum` per participating simdgroup in Phase 1 — are **all
correct**. So is the entire §2 target-sizing arithmetic (§2 above).

One substantive amplification rather than a correction: the brief's §5.1 reading
that the naive independent-reduction hoist is "largely already present" is
correct for the 2 reductions within a slot but misses that **all 4** reductions
in an iteration are independent (§4.1). That is why the mechanism was worth a
measurement rather than a dismissal.

### 8.3 Declared deviations from the brief

1. **Sibling instrument, not an extension.** The brief said extend
   `research/nezuko_pipeline_latency.swift`; I wrote
   `research/nezuko_phase_decompose.swift` instead, to avoid mutating the merged
   artefact that backs §0.9.20's published numbers. Kernel-text slicing is reused
   verbatim, so the code under test is identical.
2. **Five variants requested, seven built.** Added `E` (empty-geometry floor,
   required to attribute phase shares at all) and the `3b`/`4b` mechanism arms.
3. **Step 4 measured in the instrument, not the runtime.** §7, flagged as a
   judgement call.
4. **Step 0b not run.** Its gate did not open (§5).

### 8.4 Standing operational checks

**Inject guard (brief §10.1)**, on the exact tree measured:

```
11046:            "DARKBLOOM_INJECT_DECODE_EMPTY", 0)
11058:            "DARKBLOOM_INJECT_EMPTY_TG", 160)
```

**`0` and `160` as required.**

**Base advance (brief §10.5):** base `fae11f91` was current for this arm. No
rebase, merge, or cherry-pick from the advisor branch was performed.

**Ranked channel (brief §10.4):** no receipt was dispatched. maple-frieren holds
the channel and the advisor is the scheduler.

**Ownership separation (brief §9):** only the two fused attention kernels were
read, and neither was modified. No barrier site outside them was touched.

---

## §9 Artefacts

| file | commit | what it is |
|---|---|---|
| `research/nezuko_simdsum_check.swift` | `293763a` | Step 1 bitwise census harness, 5 kernels + 2 power controls |
| `research/nezuko_simdsum_step1.log` | `293763a` | Step 1 results, 1,048,576 reductions × 8 corpora |
| `research/nezuko_phase_decompose.swift` | `4624f2d` | Step 0 phase-decomposition instrument, 7 occupancy-matched variants |
| `research/nezuko_step0_phase_decompose.log` | `4624f2d` | Step 0 results + mechanism headroom probe |
| `research/nezuko-pr-attn-marginal-wave-cost.md` | this file | the report |

Reproduce:

```bash
swiftc -O research/nezuko_phase_decompose.swift -o /tmp/nezdec
/tmp/nezdec Sources/MLXFastModel/LagunaRuntimeModel.swift 3

swiftc -O research/nezuko_simdsum_check.swift -o /tmp/simdsum_check
/tmp/simdsum_check
```

Both are standalone Metal, hold no model, and take no benchmark lock.

---

## §10 What I would do next, and did not do

Offered as suggestions, not implemented, per the boundary on scope.

1. **The throughput-bound diagnosis redirects the whole `a`-side search.** The
   only mechanisms that can pay on this k-loop reduce **op count** or **bytes
   moved per lane**. Chain-shortening is dead here and §4.3 is the evidence.
   Every future attention brief should be checked against this before it is
   written.
2. **The epilogue is the unexamined 15.9%.** Phase 4 owns 15.9% of the wave slope
   and 12.6% of wall time at K=16, and unlike the k-loop it has *never* been
   probed. It is a smaller target but it may hold proportionally more slack. It
   needs its own numerics argument (forbidden item 9) and therefore its own arm.
3. **Occupancy is the untested structural variable.** Everything here is at 1024
   threads / 1 TG per core / ~8× ALU oversubscription. Whether that oversubscription
   is optimal was never measured. A smaller threadgroup with more TGs per core is
   a different point on the throughput curve — but note it likely collides with
   forbidden item 2, so it needs the advisor to rule on scope before anyone spends
   time on it.
4. **Phase 1 is an intercept target, not a slope target.** If anyone ever wants
   Phase 1, they should be attacking `t(1)`-style fill cost, and they should know
   in advance that the ceiling is 47% of an intercept that is itself ~19% of
   lone-TG latency.

---

_This report was written by an AI agent (OpenHands) acting as a research student
on behalf of morganmcg1._
