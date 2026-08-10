# R109-E Stage 0 — ceiling of the full-attention QK cross-lane reduction

Student: maple-alphonse · PR #685 · assignment `maple-r109-e-full-attn-qk-mma`
revision `r109-e-rev1` · base `1a6761bf46c282fcabd0577b618f0c1206757e6c`
Host: Apple **M4 Pro**, 20 GPU cores, 48 GiB (low-memory startup profile),
macOS 26.5.2, Apple GPU generation 16.

> **Directional M4 evidence only.** This host reports Apple GPU generation 16,
> never selects `_nax` kernels, and runs decode at ~12,990 µs/step against the
> ledger's 8,448 µs/step M4 reference — i.e. it is a *slower* M4 than the one
> that calibrated the campaign's transfer constants. Nothing here is a ranked
> claim.

## 1. What Stage 0 had to decide

The assignment asks whether re-expressing the QK inner product of
`laguna_full_fused_attn_grow_v1` with `simdgroup_matrix` MMA can be worth
≥0.25 % of normalized score, and gates further work on a Stage 0 ceiling of
≥0.20 %. `grep -c simdgroup_matrix Sources/MLXFastModel/LagunaRuntimeModel.swift`
is 0, so the gap is genuine; the question is only whether it is *worth* closing.

A ceiling probe answers that without writing the MMA kernel: delete (or
inflate) exactly the instructions MMA would replace, keep everything else
identical, and measure. Whatever MMA could win is bounded above by what
deleting the work outright wins.

## 2. Instrument

The scored QK reduction is six statements in the kernel literal — pipe A, pipe
B and the tail, each for the two heads of a head pair:

```
pair_score0 = simd_sum(pair_score0);   pair_score1 = simd_sum(pair_score1);
pipeb_score0 = simd_sum(pipeb_score0); pipeb_score1 = simd_sum(pipeb_score1);
... (tail copy)
```

`LagunaRuntimeModel.swift` now hoists the kernel literal into
`lagunaFullFusedAttentionKernelSource` / `...KernelHeader` (byte-identical
content) and derives three research kernels from it by textual substitution,
selected by `DARKBLOOM_FULL_ATTN_QK_PROBE`:

| arm | env | substitution | slots/site | correctness |
|-----|-----|--------------|-----------|-------------|
| `C` | unset | none — shipped `laguna_full_fused_attn_grow_v1` | 0 | must pass |
| `P` | `bcast` | `simd_sum(x)` → `simd_broadcast_first(x)` | ≈ −10 | must **fail** |
| `D` | `dose1` | `simd_sum`, then ×2^-5 and a 5-stage doubling butterfly | ≈ +11 | must **pass** |
| `X` | `dose10` | the same butterfly ten times over | ≈ +110 | must **pass** |

Four design points matter.

**(a) `bcast`, not delete.** nezuko's R106-B `NOREDUCE` arm on the *sliding*
kernel simply dropped the reduction. That makes the score lane-*non*-uniform,
so the downstream `LAGUNA_RESCALE` test `as_type<uint>(delta) == 0u` starts
diverging inside the simdgroup. That arm therefore measured "reduction removed
**plus** branch divergence added", which plausibly explains its counter-intuitive
`+16.276 µs/step` (probe *slower*, sd 15.883, CI [−0.395, +32.947]) result and
weakens the "family closed" conclusion drawn from it. `simd_broadcast_first`
keeps every lane holding the same value, so the branch stays uniform and the
delta isolates the ladder.

**(b) `dose` is bit-exact, and is the instrument's own control.** After
`simd_sum` every lane holds the same sum `S`. Scaling by `2^-5` is exact for any
non-subnormal `S`, and five `x += simd_shuffle_xor(x, m)` stages over lane-equal
data recompute `32 · (S/32) = S` with no rounding at all. So `D` must keep
`passed_correctness=true` while paying roughly the ladder's cost a second time.
The compiler cannot fold the shuffles away because it cannot prove the lanes are
equal.

`P` and `D` therefore bracket the same quantity from opposite sides. If the
ladder is expensive we expect `ΔP ≈ −x`, `ΔD ≈ +x`. If **both** land at zero the
kernel is not issue-bound at this site and no QK-reduction rewrite — MMA,
shuffle-ladder shortening, or blocked softmax — can pay. That is a decisive
result either way, and it is the check the single-sided R106-B arm lacked.

**(c) `dose1` vs `dose10` is a dose-response ruler, not just a sanity arm.**
A single `D` arm can only say "adding ~11 slots costs Δ". Because Δ at this
magnitude is comparable to run-to-run noise, one point cannot separate "slots
are cheap" from "the measurement is too noisy to see anything". Two doses on the
same axis can: the *slope*

```
slope [µs/step per issue slot] = (Δ_X − Δ_D) / (110 − 11)
```

is estimated from a 10× lever, so its noise is divided by 99 rather than 11, and
it is immune to any fixed per-arm offset (recompilation, kernel-name length,
pipeline-cache placement) that both dose arms share. Multiplying the slope by
the ~10 slots the ladder actually costs gives a *marginal* price for the QK
reduction that never depends on the failing `P` arm at all. It is a deliberately
conservative ceiling: the butterfly prices issue slots **plus** shuffle latency,
so it over-states what deleting the ladder could return.

**(d) Geometry is untouched.** `grid ((heads/2)*1024,1,1)`, `threadGroup
(1024,1,1)`, `inputNames`, and dispatch are byte-identical across arms; only the
six statements differ. Swift globals are lazy, so with the env var unset the
probe kernels are never even constructed and arm `C` is the shipped path.

## 3. Design

24 `./benchmark.sh --local-iterate` runs, `MLXFAST_LOCAL_FAN_PROMPT=0`, order

```
CXDPPDXC CXDPPDXC CXDPPDXC
```

Each 8-run block is a palindrome, so a linear drift cancels inside the block.
Estimators reported: unpaired Welch, an OLS fit of
`decode ~ 1 + linear-time + dummy(P) + dummy(D) + dummy(X)`, the mean of the
three per-block deltas, and the dose-response slope. Every run re-enters the
40 °C thermal gate.

Driver `research/maple-alphonse-r109e-qk-ceiling-abba.sh`,
analysis `research/maple-alphonse-r109e-analyze.py`.

## 4. Results

### 4.0 Instrument finding first: the palindrome hides a position effect

This has to come before the arm numbers, because it changes them.

A fixed palindromic order gives every arm exactly one mirrored position pair —
in `CXDPPDXC`, C owns slots {1, 8}, X owns {2, 7}, D owns {3, 6}, P owns {4, 5}.
Arm is therefore **perfectly collinear with position-in-block**, and no
regression on these rows, drift-adjusted or not, can separate the two. The
palindrome cancels a *linear* drift within a block; it does nothing about a
per-slot effect.

This host has a large one: the first run of a block is markedly slower than the
rest, and the gap grows across a session. Measured on control C, which is the
only arm holding slot 1:

| arm | slot | mean us/step | sd | n |
|---|---|---|---|---|
| C | 1 (block lead) | **13025.43** | 60.22 | 3 |
| C | 8 (block tail) | **12924.41** | 47.01 | 3 |
| X | 2 | 13252.47 | 54.37 | 3 |
| X | 7 | 13235.20 | 53.09 | 3 |
| D | 3 | 13000.47 | 16.38 | 3 |
| D | 6 | 13024.09 | 37.17 | 3 |
| P | 4 | 12925.39 | 24.48 | 3 |
| P | 5 | 12965.30 | 55.94 | 3 |

The effect is **+101.0 us/step on slot 1 alone**. Every other mirrored pair
agrees within noise (X 17.3, D -23.6, P -39.9, against per-cell sd 16-56). So
this is not a smooth within-block ramp that a palindrome would cancel — it is a
**one-slot step at the head of the block**, which a palindrome cannot cancel and
which lands entirely on whichever arm is scheduled first. For scale, 101 us/step
is 3.4x the advisor's whole 30 us/step decision bar.

The lead penalty also grows across the session (C slot 1: 12956.2, 13054.4,
13065.7 over the three blocks; X slot 2: 13193.8, 13262.4, 13301.2), so it is
not a single cold-start artifact that a longer warmup would remove.

The consequence for the whole campaign is direct. Six research drivers in this
tree default to an order that always hands the lead slot to the control arm —
`research/maple_r85c_epilogue_ab.sh`, `research/maple_r88a_two_regime_ab.sh`,
`research/maple_r91a_input_norm_ab.sh`, `research/maple-nezuko-r106b-h4-paired.sh`,
`research/nezuko_epilogue_abba.sh`, `research/tanjiro-r100b-census.sh`
(`base cand cand base`, `CHCHCH`, `base skipr skipc base base skipc skipr base`).
Under a lead penalty of size `d` those designs inflate the control by `d/2` for
a four-slot block, which biases **candidates fast** by tens of us/step — the
direction that manufactures local wins that do not reproduce on M5.
`research/maple-nezuko-r106b-packred-paired.sh` and
`research/maple_r85_placement_arms.sh` already rotate their arm order and are
not affected.

Everything below therefore reports, alongside the conventional estimators, a
`no block-lead run (pos>1)` delta that simply drops slot 1 of each block. That
is the estimate I trust.

### 4.1 Arm means

`CXDPPDXC` x 3, n = 6 per arm, one `./benchmark.sh --local-iterate` per row,
same binary throughout (arms are selected at runtime by
`DARKBLOOM_FULL_ATTN_QK_PROBE`, so no rebuild separates them).

| arm | probe | mean us/step | sd | n | correctness |
|---|---|---|---|---|---|
| C | shipped kernel (inert control) | 12974.92 | 73.46 | 6 | pass |
| P | `simd_broadcast_first` (reduction deleted) | 12945.34 | 44.38 | 6 | **fail, by construction** |
| D | ladder + 1 synthetic slot | 13012.28 | 28.76 | 6 | pass |
| X | ladder + 10 synthetic slots | 13243.83 | 48.98 | 6 | pass |

### 4.2 Arm P fails the token check, and that is the design

All six P rows report `local-iterate teacher-forced token mismatch`. That is
expected and is not a defect: P replaces the per-lane cross-lane sum with
`simd_broadcast_first`, so the QK scores are wrong on purpose. P is a *removal
probe* that prices the reduction's cost; it was never a shippable candidate.

The timing is still valid and still comparable, because the decode loop is
teacher-forced and does not branch on the mismatch. In
`Sources/MLXFastTrustedHarness/LagunaRuntimeLocalIterate.swift:613` the next
input is `expectedDecodeTokens[decodedStep - 1]`, never the produced token, and
`:622-628` only *records* `failureStep` — there is no `break`. Every arm runs the
same 512-token seed plus 128 one-token steps at identical shapes. What differs
between C and P is the kernel body, which is the thing being priced.

### 4.3 The removal probe: after position correction, deleting the reduction saves nothing

| estimator | P - C, us/step | se | 95% CI |
|---|---|---|---|
| unpaired Welch | -29.58 | 35.04 | [-98.25, +39.09] |
| drift-adjusted OLS | -29.58 | 30.36 | [-89.08, +29.92] |
| palindromic block | -29.58 | 15.79 | [-60.52, +1.36] |
| Hodges-Lehmann + bootstrap | -30.54 | — | [-110.72, +43.15] |
| **drop block-lead run (pos > 1)** | **+20.93** | **32.63** | **[-43.02, +84.89]** |

Every estimator that uses slot 1 says the removal probe is about 30 us/step
*faster* than control, which would have put it right on the advisor's bar. That
number is an artifact: it is the +101 us/step lead penalty charged to C and
divided across the block. Drop the lead run and the sign flips — the arm with
the reduction deleted is if anything **slower** than the arm that keeps it, and
the interval spans zero in both directions.

Read literally: the best estimate of what deleting the entire cross-lane QK
reduction buys is **0 us/step**, and the data cannot distinguish it from the
30 us/step bar in either direction.

### 4.4 The synthetic ruler: the ladder is linear and worth ~23 us/step

D and X sit at slots {3, 6} and {2, 7}. Both are mid-block, so the D-X contrast
is free of the slot-1 artifact and does not touch C at all.

- marginal cost **2.339 ns/step per issue slot** (se 0.434), from
  `(13243.83 - 13012.28) / (110 - 11)`
- two-parameter fit: fixed step cost **+11.63 us/step** (se 33.90), i.e. **not
  distinguishable from zero** — the ruler is **linear within noise**
- the real reduction is a 10-slot ladder (`simd_shuffle_xor` masks 1,2,4,8,16
  over two pipes), so deleting it is worth
  **23.39 us/step, 95% upper 31.89 us/step**

This retires the "concave / slack" story from the earlier n=2 look. There is no
measurable free issue slack in this kernel: added work costs a constant rate,
and the first slot costs the same as the hundredth.

Two reasons this 23.4 is an **over**-estimate of a real removal:

1. A synthetic *addition* is unconstrained work appended to a live dependency
   chain; a real *removal* returns issue slots that the surrounding code may not
   be able to use. Addition prices the slot; removal recovers at most the slot.
2. X's decode load leaks into the prefill negative control (below), so part of
   X's +269 us/step is a thermal side-channel rather than issue cost, which
   inflates the D-X slope.

Both point the same way, and both are consistent with the direct removal probe
in 4.3 measuring zero.

### 4.5 Prefill negative control

`lagunaFullFusedAttention` is the single-token grow kernel, so no probe should
move prefill. Per token:

| arm | mean us/token | sd | delta vs C | se | t |
|---|---|---|---|---|---|
| C | 1116.11 | 6.08 | — | — | — |
| D | 1118.62 | 7.33 | +2.51 | 3.89 | +0.65 |
| P | 1117.94 | 11.21 | +1.83 | 5.20 | +0.35 |
| X | 1126.15 | 10.45 | +10.04 | 4.94 | **+2.03** |

D and P are clean, which rules out a global thermal or DVFS confound that would
have made the whole comparison worthless. X is marginal, and there is a
mechanism: `LagunaRuntimeLocalIterate.swift:559` charges prefill before
`:583` starts decode *within* a repeat, but with `timingRepeats > 1` the second
repeat's prefill follows the first repeat's decode. Only X's decode is heavy
enough (+269 us/step over 128 steps) to heat the die into the next prefill. This
is a caveat on X, not on the comparison, and it makes 4.4 conservative.

<!--RESULTS-->

## 5. Pricing: reconciling the 8× gap between the three campaign constants

Per the advisor's revised instruction (PR #685 comment 5246119853) the headline
number in §4 and §7 is **µs/step of GPU busy time removed on this M4 host**,
against the stated stop bar of **~30 µs/step**. No conversion is applied to the
verdict. This section exists only to close the pricing question the advisor
flagged as "worth as much to the programme as your main arm", and to retract an
error in an earlier draft of this memo.

### 5.1 Retraction

An earlier draft of this section asserted that `0.01642` "occurs nowhere under
`research/`". **That is wrong.** The constant is sourced, to my own prior work:

> `research/maple-alphonse-r108p-dispatch-removal-symmetry.md:81`

It is invisible from this worktree because that memo lives on branch
`maple-alphonse/r107-decode-oproj-amortisation` (commits `f4784a1e` …
`bee426df`) and was never merged into this base. A `grep` of the checked-out
tree is therefore not evidence of absence for any cross-branch constant, and I
should not have treated it as such.

### 5.2 The three constants are the same rule at three different `k`

All three numbers in circulation are Rule 105.2,
`Δ%score = Δ_M4[µs/step] × k × 0.015228`
(`research/CURRENT_RESEARCH_STATE.md:6505-6514`; the M5 base constant
`0.015228 = 0.75 / 4925.255 × 100` at `:2441`, `:1295-1296`, `:6449-6463`),
evaluated with a `k` drawn from a **different physical family**:

| | value (%score per µs/step) | what the µs/step must be | implied `k` | family it is valid for |
|---|---|---|---|---|
| **A** | **0.0066875** | M4 **GPU busy** µs/step | **0.4392** ( = α) | in-kernel work: bytes moved or latency removed |
| **B** | 0.016423 | M4 µs/step of removed **chained host-encode / dispatch** | 1.0785 | the dispatch axis only |
| **C** | 0.0020325 | M4 **nominal** dispatch µs | 0.1335 | nothing (see 5.4) |

Derivations, so each is checkable:

* **A** `0.75 × 100 × 0.8 / 8972 = 0.0066875`, i.e. Rule 105.2 at `k = α`.
  `α = 0.4369` is `CURRENT_RESEARCH_STATE.md:6512`, cross-checked at
  `research/maple-alphonse-r108p-dispatch-removal-symmetry.md:460`. The `0.8`
  is the planning busy→wall transfer.
* **B** `0.015228 × 1.0785 = 0.0164234`. `k_dispatch = 2.3403 / 2.17 = 1.0785`
  is `r108p:81` and `:457`, CI `[0.9917, 1.1820]`. R108-P itself flags this
  constant as **unvalidated** at `:85-88` and says it could move to ≈2.2.
* **C** `0.1439 / 70.8 = 0.0020325` — a chain-discounted %score numerator
  divided by a *nominal* dispatch-µs denominator.

Ratios: **`B / C = 8.08×`** — this is the 8× gap. **`B / A = 2.469×`**, which is
exactly `1.0785 / 0.4369`, i.e. entirely the `k` difference and nothing else.

### 5.3 Error 1 — B was exported outside its family

`k_dispatch = 1.0785` was fitted on **chained host-side dispatch removal**
(R108-P's removal ladder, `r108p:29`), where each removed encode also removes a
serialization stall. Applied to **in-kernel** busy µs it over-credits by
`1.0785 / 0.4369 = 2.47×`. Rule 105 (`CURRENT_RESEARCH_STATE.md:6441`,
`:6459-6463`) already warns that the raw M5 constant over-credits an M4
measurement by 2.0–2.6×; B is that same over-credit re-derived by a different
route. `β = 0.5` (`r108p:461`) is the sanctioned **upper** bound for
issue-bound work, not 1.0785.

### 5.4 Error 2 — C mixes two models in one fraction

`70.8 µs / 158 dispatches = 0.448 µs/dispatch` is a **mixture**, not a rate.
R108-P measures a *chained* slope of `2.1379 µs/dispatch`
(CI `[1.6213, 2.6546]`) and a *free-region* slope of `0.0686 µs/dispatch`
(`r108p:293-295`); rule 105.24 finds ≥ 68.4 % of decode dispatch is overlapped
(`research/advisor-rule-105-24-*.md:108`). C divides a numerator that has
already been chain-discounted by a denominator that has not been, so it is a
ratio of two incompatible models. It should not be used for anything.

Crucially, **C cannot apply to in-kernel busy at all**. Decode kernels on this
family do not overlap — the advisor's own budget has `busy_sum` 8489.7 ≈
`busy_union` 8489.1 µs/step over 406 dispatches with sd 0 — so any busy µs
actually removed from a decode kernel is on the critical path *by construction*,
and needs no overlap discount.

### 5.5 Error 3 — a phantom denominator

The chain `0.75 × 100 / 4568 = 0.016419` that appears to justify B is
coincidence. `4925.255 / 1.0785 = 4566.8`, so "4568" is just the M5 denominator
divided by `k_dispatch`. **No `4568 µs/step` decode denominator exists anywhere
in the repo.**

### 5.6 Recommendation

For **in-kernel busy µs on decode**, use

> **≈ 0.0067 %score per M4 busy µs/step** (constant **A**, Rule 105.2 at
> `k = α = 0.4369`)

with an honest band:

| band | %score per M4 busy µs/step | basis |
|---|---|---|
| α/β bracket | 0.0059 – 0.0076 | `CURRENT_RESEARCH_STATE.md:6512-6514` |
| ISSUE-bound widening | 0.0041 – 0.0100 | `k_issue ∈ [0.267, 0.654]`, `maple-tanjiro-r107g-decode-family-regime-census.md:762-763`; `0.00996` is a hard upper bound |

Busy→wall is `0.8` for planning; the one measured estimate is `0.93` with a CI
spanning zero (`research/r87a-runs/ceiling.json`, arms A0/E0, `:105`, `:118`),
so `0.8` is the conservative choice and should be stated whenever used.

**Do not use `0.01642` for in-kernel work. Do not use `0.00203` for anything.**

### 5.7 Still unclosed

Two inputs to A and C have **no in-repo source** and I could not close them:

* the decode denominator **`8972 µs/step`** — the repo's M4 controls are
  `8448` (`CURRENT_RESEARCH_STATE.md:6943`) and `8984.5`
  (`research/maple-nezuko-r106b-handoff-to-fern.md:42`); `8972` is close to the
  latter but is not it;
* the pair **`(70.8 µs, 0.1439 %)`** feeding C. The `158` in `70.8 / 158` is my
  own removal ladder (`r108p:29`); the other two numbers are not in the tree.

If the advisor holds the provenance of `8972`, A should be re-derived on the
sourced denominator; the effect is ≤ 6 % either way and does not change the
Stage 0 verdict.

### 5.8 What this means for this host

This box's control decode is ~12,990 µs/step, not 8,448 / 8,972 / 8,984.5, so
even A is not directly transferable. A relative transfer that assumes the decode
fraction is preserved gives `0.75 × 100 × 0.8 / 12,990 = 0.004619 %score per
local busy µs/step`. That is why §4 and §7 report **µs/step**, and why the
advisor — who holds the M5 denominator — should do the conversion.

## 6. Independent MMA feasibility analysis

A frontier design review of the `simdgroup_matrix` rewrite at the mandated fixed
geometry, run in parallel with the measurement, reached **expected loss** on
instruction accounting alone. Verified on this toolchain:

* `simdgroup_bfloat8x8` exists; a mixed `bf16 × bf16 → fp32` 8×8×8 multiply
  compiles to the native AIR intrinsic
  `air.simdgroup_matrix_8x8_multiply_accumulate.v64f32.v64bf16.v64bf16.v64f32`
  with no `fpext`, so the datatype path is real.
* `simdgroup_load` supports device and threadgroup address spaces, stride,
  origin and transpose.
* MLX's own steel GEMM avoids the mixed path and hard-codes the officially
  unspecified fragment lane layout (`steel/gemm/mma.h:46, 49-55, 205`), so any
  layout assumption is undocumented behaviour we would be adopting.

The blocking problem is occupancy of the 8×8 tile. The kernel's threadgroup owns
one head **pair**, so only 2 query rows exist per simdgroup; every valid mapping
leaves the tile ≤ 2/8 utilized.

* Mapping "head_dim chunks into M" is *semantically invalid*: all M rows of an
  MMA share one B fragment and one k-slice.
* Mapping "keys × keys" is vacuous.
* Best valid mapping (M = 8 keys, N = 2-of-8 query columns, natural-layout K
  loads, `Qᵀ` staged once) needs 16 MMAs per 8-key block = **32 slots/key**,
  replacing today's **28** (8 FMA + 20 reduction) — about **+5 %** on the inner
  loop, and ~+15 % against a blocked-softmax scalar baseline.
* The only mapping that fills the tile needs ≥ 6 query rows per tile, which
  requires exactly the grid change the assignment forbids.

MMA therefore only breaks even if the M5 retires MMA at ≥ 1.5× the scalar FMA
MAC rate or co-issues MMA with the scalar pipe. That is publicly unverified for
Apple silicon; all M1–M4 evidence points at parity. The cheapest way to settle it
is a standalone ~40-line M5 microbenchmark of MMA-vs-FMA throughput (fp32 MMA,
bf16→fp32 MMA, interleaved co-issue): a ratio ≤ 1.1 kills the idea outright,
≥ 1.5 would justify prototyping the mapping above.

The same review noted one geometry-preserving, non-MMA alternative worth roughly
25 % of the inner loop: keeping the two heads in opposite lane halves so the
reduction becomes a 4-step shuffle (~10–11 slots instead of 20), combined with
8-key blocked softmax. **The `P` arm measured here is the ceiling for that idea
too** — it deletes strictly more work than the shortened ladder saves.

## 7. Verdict

**`N-FULL-QK-CHEAP`. Stop R109-E before any MMA implementation.**

The number the advisor asked for, in the units the advisor asked for:

| estimate | µs/step of GPU busy time removable | vs 30 µs/step bar |
|---|---|---|
| direct removal probe (P − C, lead-corrected) | **0** (point +20.9 the *wrong* way, se 32.6) | below |
| synthetic ladder ruler (D−X slope × 10 slots) | **23.4** (95% upper 31.9) | below |

I am deliberately **not** converting these to %score; §5 supplies the constant
and its family if the advisor wants to.

### What this verdict is, and what it is not

It is a **bounded negative and an expected-value decision**, not a proven null.
The honest statement of the strongest datum is that P − C is +20.9 ± 32.6
µs/step, whose 95% interval [−43.0, +84.9] does **not** exclude a 30 µs/step
saving. What the data do establish is that the *point* estimate of the removal
is zero or negative, that the independent synthetic ruler puts the whole ladder
at 23.4 µs/step with a 95% upper bound of 31.9, and that two separate arguments
(§4.4) say the ruler over-states what a removal recovers. Every line of evidence
lands at or under the bar, none above it. Against that, the MMA implementation
in §6 is projected to be **worse than the code it replaces** (32 slots/key vs 28
today, ≈5% regression) unless the M5 matrix unit exceeds 1.5× scalar FMA
throughput, which is publicly unverified.

Spending the remaining Stage 1 allocation on a rewrite whose best case is a
sub-bar saving and whose modelled case is a regression is not a good use of the
box. Cancelling is the right call even though the null is not proven.

### Three things that would change the verdict

1. **An M5 MMA-vs-FMA microbenchmark** (~40 lines, §6). If the M5 simdgroup
   matrix unit is ≥1.5× scalar FMA rate, the slot arithmetic flips sign and this
   verdict should be revisited on M5 rather than here.
2. **A geometry change.** The ≤2-query-rows-per-simdgroup limit that wastes
   ≥75% of an 8×8 tile is a consequence of the frozen
   `((heads/2)*1024, 1, 1)` / `(1024, 1, 1)` launch, which R109-E was forbidden
   to touch. The two carve-outs granted to other arms (`gate_sp_h64`,
   `residual_rms_router`) suggest the campaign is willing to grant these; a
   full-attention carve-out is the precondition for any MMA work here.
3. **Occupancy, not arithmetic.** This kernel launches 24 threadgroups — one per
   head pair. That is above the 20 GPU cores of this M4 Pro but far below an
   M5 Max, so on the ranked machine most of the GPU is idle for the whole
   duration of this kernel. A split-K or head-splitting launch is a much larger
   lever than anything inside the inner loop, and it is measurable before it is
   implemented: a one-step GPU counter capture on M5 would settle it. **I
   recommend this over any further QK-inner-loop work.**

### Instrument finding, which outlives the verdict

The +101 µs/step block-lead penalty (§4.0) is 3.4× the entire decision bar and
lands on whichever arm is scheduled first. Six research drivers in this tree
always schedule the control first, so their historical deltas are biased in the
direction that **manufactures local wins**. Every future paired driver in this
campaign should mirror the arm order across blocks, or drop slot 1.

<!--VERDICT-->

## 8. Hand-off to maple-edward

Reusable for the sliding-window kernel (`LagunaRuntimeModel.swift` 1507–1975,
same six-statement structure at 1681/1717/…):

1. Use `simd_broadcast_first`, not deletion, for a reduction ceiling probe;
   deletion adds `LAGUNA_RESCALE` branch divergence and confounds the delta.
2. Add **two** bit-exact `dose` arms (`dose1` and `dose10`), not one. A single
   dose only tells "the ladder is free" from "my instrument is broken"; two
   doses on the same axis give a slope with a 10× lever, cancel any fixed
   per-arm offset, and price the ladder without relying on the failing `bcast`
   arm. Both keep `passed_correctness=true`, so a correctness failure there is a
   real signal, not an expected one.
3. Fragment layout for MMA is *not* specified by Apple; MLX steel hard-codes it
   (`steel/gemm/mma.h:46, 49-55, 205`). Mixed bf16×bf16→fp32 8×8×8 does lower to
   a native AIR intrinsic, so precision is not the obstacle — tile occupancy is.
4. Sliding attention has the same 2-query-rows-per-simdgroup limit, so the same
   ≤ 2/8 tile-utilization argument applies unless its geometry differs.
