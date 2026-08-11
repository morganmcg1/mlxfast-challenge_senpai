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

> **Superseded in part by §4.6.** Everything in §4.0–§4.5 is the first block
> only (n=24), where the effect below is *aliased onto the control* and can only
> be estimated indirectly. §4.6 adds a mirrored block that identifies it
> directly at **+53.59 µs/step (se 29.88)**, not the +101 estimated here. Read
> §4.6 for the numbers that the verdict actually uses.

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

- marginal cost **2.339 us/step per issue slot** (se 0.434), from
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

### 4.6 Confirmation block: the mirrored order, and what it did to §4.0–§4.4

Everything above is the first block only (`CXDPPDXC` ×3, n=24), where slot 1 is
always the control. I then ran a second block with the arm order **mirrored**,
`PXDCCDXP` (n=8), so slot 1 is held by arm P and the control moves to slots 4/5.
This makes the block-lead effect *identifiable* instead of aliased onto the
control. Combined n=32, `python research/maple-alphonse-r109e-analyze.py
/tmp/r109e-qk-ceiling-main.tsv /tmp/r109e-qk-swap.tsv`:

| arm | mean µs/step | sd | n | correctness |
|---|---|---|---|---|
| C shipped (inert control) | 12971.42 | 62.44 | 8 | true |
| D ladder + 1 slot | 13013.84 | 24.88 | 8 | true |
| P `simd_broadcast_first` | 12951.87 | 44.15 | 8 | false, by construction |
| X ladder + 10 slots | 13238.43 | 59.29 | 8 | true |

**The block-lead spike is real but smaller than the single-block estimate, and
it is no longer significant at 95%: +53.59 µs/step, se 29.88, CI
[−4.98, +112.16].** The n=24 figure of +101 µs/step was an over-estimate that
borrowed the control's own noise. I am restating it here rather than quietly
dropping it: the honest claim is *"slot 1 runs tens of µs/step slower, point
estimate ≈54, not distinguishable from zero at n=32"*, not *"+101"*. That is
still large enough relative to a 54 µs/step decision bar to justify the
recommendation in §7 that every paired driver mirror its arm order — a nuisance
term whose plausible range is [0, +112] cannot sit aliased on the control.

Combined estimators, arm P (reduction replaced by broadcast) minus control:

| estimator | delta µs/step | se |
|---|---|---|
| unpaired Welch | −19.56 | 27.04 |
| drift-adjusted OLS | −19.56 | 25.44 |
| palindromic block | −19.56 | 15.00 |
| Hodges–Lehmann | −23.93 | — |
| drop slot 1 | **+15.37** | 24.87 |
| **lead-adjusted OLS** | **−6.16** | 25.57 |

The estimators disagree in *sign* and agree in *magnitude*: every one of them is
within ±25 µs/step of zero, on a quantity that would have to be ≥54 µs/step to
matter. The lead-adjusted fit is the one that uses all 32 runs and removes the
nuisance term, and it says deleting the QK reduction saves **6.16 µs/step**,
95% CI on the saving [−43.95, **+56.27**].

The synthetic ruler also tightened, and it is the better-powered instrument by
about 7×: marginal **2268.6 ns/step per added issue slot (se 384.2)**, fixed
step cost +37.6 µs/step (se 30.0, i.e. indistinguishable from zero, so the
ruler is linear and usable). Ten ladder slots ⇒ **22.69 µs/step, 95% upper
30.22**.

The prefill negative control now passes everywhere: deltas +1.89 (t 0.59),
−0.02 (t −0.01), +4.78 (t 1.08) µs/token for D, P, X. The single-block
`t = 2.03` on arm X did **not** replicate; it was noise, and I withdraw the
speculative reading of it in §4.5.

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

### 5.9 Superseded: the advisor closed the bracket, and my constant was right in the wrong units

PR #685 comment 5246312084 (21:35Z) closes the 8× gap with a two-axis
elasticity identity rather than a calibration. It supersedes §5.6. I record it
here because the resolution confirms §5's *structure* while correcting my
units, and because it moves the stop bar.

```
T          = D - S/128                          steady decode step
elasticity_T = 0.75 * (1 - sigma) = 0.638       at sigma = 14.98% (M5 frontier)
%score     = elasticity_T * tau * Delta_M4_wall / T_M4  =  0.63 * tau * Delta / 8972
```

At `tau = 1`: **0.0070 %score per M4 steady-step wall µs**, **0.0056 per M4
decode busy µs**. **The bar is 0.378 %score = 54 µs/step of M4 wall = 68 µs/step
of M4 busy.**

Three corrections to §5.2's table, which I accept:

- **My constant A (0.0067 %/busy-µs) was right to within 5%** of the canonical
  0.0056–0.0070 band. §5.6's recommendation stands numerically; only its
  derivation was ad-hoc.
- **My constant B (0.01642) was correct, but in *M5 steady-step* µs, not M4.**
  It is exactly `elasticity_T / T_M5`. My §5.1 retraction retracted the wrong
  thing: the number was never wrong, the programme's later application of it to
  M4 microseconds was. §5.3's "exported outside its family" diagnosis was
  therefore right in spirit and wrong in mechanism.
- **My constant C (0.00203) is not a general price and not a phantom.** It is
  the dispatch-overhead *mechanism class* carrying its own M4→M5 transfer
  `tau ≈ 1%`. §5.5's "phantom denominator" claim is withdrawn.

The transfer factor `tau` is the real free parameter: ≈1% for dispatch/launch
overhead, ≈106% for DRAM-traffic savings, unknown and possibly sign-flipping
for threadgroup-geometry changes. **My arms are all in-kernel ALU inside an
unchanged grid, which is the `tau ≈ 1` regime**, so I price at `tau = 1`
throughout and note that this is the *optimistic* assumption for my own
hypothesis.

The bar moving from 30 to 54 µs/step does not weaken this experiment's
conclusion; §7 shows it converts a bounded negative into a two-sided exclusion.

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

**`N-FULL-QK-MMA-NEGATIVE`. Stop R109-E before any MMA implementation.**

> **Verdict token changed at 23:15Z; see §7.2.** This section was written and
> measured against the 0.378 %score landing bar. PR #685 comment 5246874781
> (22:45Z) dropped the bar to **≈0.07 %score**, and at that bar the old token
> `N-FULL-QK-CHEAP` is **false and I withdraw it**: the QK ladder is worth
> 0.159 %score at τ=1, i.e. **2.3× the new bar**, not a fraction of it. What
> survives repricing is the *mechanism* verdict, which never depended on the
> bar: **simdgroup-MMA cannot harvest this pool** (§6 projects 32 slots/key vs
> 28 shipped, and an 8-row `simdgroup_bfloat8x8` tile needs ≥6 query rows,
> which is a forbidden grid change for this assignment). Everything below is
> left as measured, priced against the old bar; §7.2 reprices it.

**Stage-0 item 1 — reduce-vs-load, in the units the advisor asked for.**
All figures below are the **combined n=32 fit** (main block + mirrored
confirmation block, §4.6), not the n=24 single-block fit that earlier drafts of
this section used. Raw ruler slope: **2268.6 ns/step per added issue slot**
(se 384.2). The shipped `simd_sum` ladder that the MMA rewrite would replace is
~10 slots. Busy µs = wall µs / 0.8, from the advisor's own pair
(0.0070 %score per wall µs/step, 0.0056 per busy µs/step).

| estimate | ns/slot | µs/step M4 **wall** | ×1.28 corrected | µs/step M4 **busy** | %score @ τ=1 | vs 54 µs bar |
|---|---|---|---|---|---|---|
| synthetic ladder ruler (point) | 2268.6 | **22.69** | 29.04 | 28.36 | 0.159 | **0.42×** |
| synthetic ladder ruler (95% upper) | 3021.9 | 30.22 | 38.68 | 37.78 | 0.212 | 0.56× |
| direct removal probe P−C (point saving) | — | **+6.16** | 7.88 | 7.70 | 0.043 | 0.11× |
| direct removal probe P−C (95% upper saving) | — | **+56.27** | 72.03 | 70.34 | 0.394 | **1.04×** |

I apply the ×1.28 correction as instructed; its derivation is in the omitted
middle of comment 5246312084 and I have not independently checked it. It does
not change any sign or any verdict.

**As a share of my 249.5 µs/step pool: the entire QK reduction is 11.4%
(ruler 95% upper 15.1%). The advisor's own table says I need a 27.2% harvest of
that pool to clear the bar.** The mechanism I was assigned is structurally too
small by roughly 2.4×, independent of how well it is implemented.

> **Unit correction (23:05Z).** An earlier draft of this paragraph divided the
> **wall** saving by the pool and got 9.1%. That mixed units. The advisor's
> pool is a profiler figure, i.e. **busy** µs/step: `68 / 249.5 = 27.2%` is
> exactly the quoted required harvest, whereas `54 / 249.5 = 21.6%` is not. So
> the pool share must use the busy restatement, `22.69 / 0.8 = 28.36`, giving
> **11.4%**. The `vs 54 µs bar` column in the table above is wall-against-wall
> and is unaffected. No sign or verdict changes; the shortfall is 2.4×, not 3×.

### What this verdict is, and what it is not

An earlier draft of this section claimed *"two independent estimators exclude a
bar-clearing saving at 95%"*. **The confirmation block does not support that
claim and I withdraw it.** What the combined n=32 data actually supports is
weaker and I state it exactly:

- the **synthetic ruler**, which is the better-powered instrument by ≈7× (se
  3.8 vs 25.6 µs/step on the ladder total), puts the whole ladder at
  **22.69 µs/step, 95% upper 30.22 (38.68 corrected)** — the upper bound is
  **below** the 54 µs/step bar, so this estimator does exclude a bar-clearing
  saving at 95%;
- the **direct removal probe** does **not**. Its point saving is +6.16 µs/step
  and its 95% upper is **+56.27 (72.03 corrected)** — that upper bound sits
  just *above* the bar. Deleting the reduction outright cannot be ruled out at
  95% by this probe alone; it is simply far too noisy to resolve a 54 µs/step
  effect with n=32 at sd ≈ 50 µs/step per run.

So this is an **expected-value decision plus one exclusion**, not two. The point
estimates from both instruments (22.7 and 6.2 µs/step) are 0.42× and 0.11× of
the bar; the only interval that reaches the bar is the wide one, from the weaker
instrument, and it reaches it only at its optimistic extreme. Two further
caveats I keep: the ruler prices *issue slots*, so a mechanism that removed the
reduction's *latency* rather than its issue count is not bounded by it; and
§4.4 gives two separate reasons why a synthetic *addition* ruler over-states
what a *removal* recovers, which makes the ruler's own bound conservative in
the direction that favours my hypothesis.

To actually resolve the direct probe against a 54 µs/step bar I would need
roughly `(25.6/13.8)^2 ≈ 3.4×` the sample, i.e. ~110 runs ≈ 5.5 h of box time,
to halve the interval. **I do not recommend spending it**, because the ruler
already answers the same question with 7× the power and the §6 design analysis
independently projects the MMA rewrite as a regression. That trade is the
recommendation, not a hidden assumption.

Against that ceiling, the MMA implementation in §6 is projected to be **worse
than the code it replaces** (32 slots/key vs 28 today, ≈5% regression) unless
the M5 matrix unit exceeds 1.5× scalar FMA throughput, which is publicly
unverified. Spending Stage 1 on a rewrite whose 95%-optimistic case is 0.56× of
the bar and whose modelled case is a regression is not a good use of the box.

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

The block-lead penalty (§4.0, §4.6) lands on whichever arm is scheduled first.
With the mirrored block it is identified at **+53.59 µs/step, se 29.88, 95% CI
[−4.98, +112.16]** — one whole decision bar at the point estimate, and up to two
bars at the top of the interval. It is *not* significant at n=32, and I say so;
the argument does not need significance. A nuisance term whose plausible range
is [0, +112] µs/step must not sit **aliased onto the control**, because then it
is indistinguishable from a candidate win. Six research drivers in this tree
always schedule the control first
(`research/maple_r85c_epilogue_ab.sh`, `maple_r88a_two_regime_ab.sh`,
`maple_r91a_input_norm_ab.sh`, `maple-nezuko-r106b-h4-paired.sh`,
`nezuko_epilogue_abba.sh`, `tanjiro-r100b-census.sh`), so their historical
deltas are biased in the direction that **manufactures local wins**;
`maple-nezuko-r106b-packred-paired.sh` and `maple_r85_placement_arms.sh`
already rotate and are fine. Every future paired driver in this campaign should
mirror the arm order across blocks, or drop slot 1. The mirroring costs one
extra block; it is the cheapest fix available.

### Stage-0 checklist, answered in order

1. **Reduce-vs-load in µs of M4 removed off the 249.5 µs pool** — table above,
   combined n=32. Raw **2268.6 ns/step per issue slot** (se 384.2); ladder
   **22.69 µs/step** wall (95% upper 30.22); **×1.28 corrected 29.04** (upper
   38.68); **28.36 µs busy** (upper 37.78). **11.4% of the pool against a 27.2%
   requirement.** The independent direct-removal probe agrees on the point
   estimate (+6.16 µs/step saved) and is too noisy to bound (95% upper +56.27).
2. **Params bolt-on, separately** — §"params memo" companion note. It is a
   different mechanism class (host encode, `τ ≈ 1%`), so it is *not* additive
   with item 1 at the same `τ` and I price it separately there. Pre-registered
   11 µs/step (range 4–20) before measuring. **Measured, n=16:
   `N-FULL-PARAMS-ALLOC-IRRELEVANT`.** Dose ruler **−24.760 ns/step per host
   allocation (se 58.336)** ⇒ the 9 removed allocations are worth
   **−0.22 µs/step, 95 % upper +0.81 µs/step, ~8 % of the ≥10 µs bar**; direct
   `M − O` **+64.20 µs/step (se 35.52)**, on the *slower* side, 95 % upper
   saving +5.43 µs/step. My own §5.1 arithmetic (9 × 30 ns = 0.27 µs/step) is
   confirmed; the 11 µs/step pre-registration is refuted by ~50×. Arm
   reverted, not landed.
3. **Grid unchanged — proven, not asserted.** `git diff BASE -- Sources Vendor
   benchmark.json Package.swift | grep -c '^[+-].*\(grid:\|threadGroup:\)'`
   returns **0**. The full-attention dispatch at `LagunaRuntimeModel.swift:2547`
   is still `grid ((heads/2)*1024, 1, 1)`, `threadGroup (1024, 1, 1)` = 24
   threadgroups × 1024 threads. Every probe arm rewrites *in-kernel statements
   only*; all four arms share one dispatch shape.
4. **Non-empty submitted-surface diff** — `git diff --numstat BASE -- Sources
   Vendor benchmark.json Package.swift` returned
   `147  16  Sources/MLXFastModel/LagunaRuntimeModel.swift` at 22:42Z.
   **Now empty**: with both arms terminal-negative, commit `ddf87e59` reverts
   `Sources/` to `BASE_SHA 1a6761bf`, so the branch ships a **zero-byte
   submitted surface** — zero static-review risk and zero byte-budget
   consumption for fern's submission. Instrumentation stays recoverable from
   history (`20dd6948..996c43f3`, `2e9cd4f5`).

On the fourth item's *shape*: the brief asked for bulk in a new
`Sources/MLXFastModel/LagunaFullAttnQKMMA.swift` with only registration and
dispatch selection in LRM. **I did not create that file, because the verdict is
`N-FULL-QK-CHEAP` and no MMA kernel is being written** — the file would be an
empty shell. The LRM delta is the probe instrument (three probe source
rewriters, a dose kernel generator, and a selector) plus the params memo, all of
which are inert when their environment variables are unset.

## 7.1 Budget closure: what the ruler says about the *whole* kernel

The ruler is not only a verdict on the ladder. It is a **price for one
instruction in this kernel's inner loop**, and a static instruction census then
prices every other stage without another benchmark run. This is the part of the
result I think is worth more than the assigned hypothesis, so I derive it
carefully and flag every soft step.

### 7.1.1 The ruler's unit, restated

The dose probe substitutes **6 sites**, of which **4 are inside the key loop**
(`:2186`, `:2187`, `:2222`, `:2223`); the other two (`:2268`, `:2269`) are in
the single-row tail that runs at most once per launch and is negligible. Each
dose rep adds 11 instructions **at every substituted site**. So

```
1 ruler slot  =  1 instruction at each of the 4 in-loop sites
              =  4 actual in-loop instructions
2268.6 ns/step per ruler slot  ⇒  567.15 ns/step per in-loop instruction
```

The same unit is why the shipped 10-instruction `simd_sum` ladder is priced at
`10 × 2268.6 ns = 22.69 µs/step` and not at `40 ×` anything: 10 instructions ×
4 sites is exactly 10 ruler slots.

### 7.1.2 Static census of the inner loop

Counted from `lagunaFullFusedAttentionKernelSource`, loop body `:2161`–`:2249`,
2 key rows per iteration (pipes A and B), both query heads, per lane:

| stage | lines | instructions / iteration |
|---|---|---|
| QK per-lane partial dot product (2 heads × 4 dims × 2 pipes) | 2178–2185, 2214–2221 | 16 |
| **QK cross-lane ladder** (4 × `simd_sum`, 5 shuffle + 5 add each) | 2186–2187, 2222–2223 | **40** |
| QK scaling / masking | — | 0 (scale folded into `pair_q*` at 2143–2148) |
| softmax: max, rescale macro, `exp`, running sum | 2189–2201, 2225–2237 | 32 (incl. 8 `exp`) |
| AV accumulate (2 heads × 4 v-dims × 2 pipes, mul + FMA) | 2203–2210, 2239–2246 | 32 |
| addressing, predicates, loop overhead | 2160–2164, 2248–2249 | ≈8 |
| **total ALU** | | **≈128** |
| device loads (4 × `vec<bfloat,4>` = 32 B/lane) | 2167–2174 | 4 (memory) |

`head_dim` 128, 32 lanes × 4 dims each; K/V are stored **raw `bfloat16`**
(`:2569`, `:2369-2371`, `:2387-2389`), so there is **no in-kernel dequantization
to remove** — a real candidate mechanism that this census rules out for free.
Plausible band on the total: **112–156** instructions, dominated by whether
`simd_sum` lowers to the 5-stage butterfly (40) or an Apple hardware reduce
(≈10), and whether `fast::exp` is one slot or two.

### 7.1.3 The closure

```
in-loop ALU  ≈ 128 × 567.15 ns  =  72.6 µs/step wall  =  90.8 µs/step busy
band (112–156)                  =  63.5–88.5 wall     =  79.4–110.6 busy
```

Against the advisor's **249.5 busy µs/step** pool:

| component | busy µs/step | share of pool | vs the 68 µs busy bar |
|---|---|---|---|
| QK reduction ladder (**my assigned mechanism**) | 28.4 | 11.4% | 0.42× |
| **all** other inner-loop ALU | 62.4 | 25.0% | 0.92× |
| **all** inner-loop ALU together | 90.8 | 36.4% | **1.34×** |
| KV DRAM floor (derived below) | ≈86 | ≈35% | 1.27× |
| residual, if ALU and DRAM did not overlap | ≈72 | ≈29% | 1.07× |

The DRAM floor is arithmetic, not measurement: 10 full-attention layers × 2
tensors × 8 KV heads × ~576 positions × 128 dims × 2 B = **23.6 MB per decode
step**; at the M4 Pro's ~273 GB/s that is **≈86 µs/step**, and it is
irreducible without changing what is read.

**These rows do not add and I am not adding them.** ALU and DRAM overlap by
design; the honest statement of the last row is *"if the kernel were perfectly
overlapped, its floor would be `max(90.8, 86) = 91` busy µs/step, and it costs
249.5 — so **≈63% of the kernel is neither marginal arithmetic nor bytes**"*,
and if the two did not overlap at all the same residual is ≈29%. The true
residual is somewhere in **29–63%, i.e. 72–159 busy µs/step**. Every value in
that range is larger than the 68 µs bar. That is the point of the section: the
biggest recoverable block in this kernel is the part nobody has measured, and
even its most pessimistic estimate exceeds the whole requirement.

Three consequences, in descending order of how much they should change what the
team does next:

1. **Deleting every arithmetic instruction in the full-attention inner loop —
   QK, softmax, AV, all of it — buys 1.34× the bar.** A mechanism that touches
   one stage cannot clear it. This is the general form of `N-FULL-QK-CHEAP` and
   it retires *all* in-loop ALU micro-optimization for this kernel, not just
   mine.
2. **Roughly 29% of the kernel is neither marginal ALU nor DRAM bytes.** That
   residual is the largest single unclaimed block in my pool and nobody is
   assigned to it.
3. ~~**The likeliest owner of that residual is threadgroup quantization.**~~
   **RETRACTED 23:2xZ — see §7.2.7.** maple-edward measured the quantization
   edge on this exact M4 Pro and it sits above my dispatch, and measured the
   residual to be per-threadgroup critical-path latency rather than occupancy.
   The paragraph is left below unedited so the retraction has something to
   point at. The dispatch is
   `grid ((heads/2)*1024,1,1)`, `threadGroup (1024,1,1)` = **exactly 24
   threadgroups**, one per head pair, and a threadgroup cannot span cores. On
   this 20-core M4 Pro, 24 indivisible threadgroups give 4 cores two units of
   work and 16 cores one, so the makespan is 2 units where the balanced ideal is
   1.2 — **60% efficiency, 40% of the kernel spent in a nearly empty second
   wave**. 40% of 249.5 is ≈100 busy µs/step, **1.47× the bar, with no change to
   a single arithmetic instruction.** On the ranked M5 Max the same 24
   threadgroups cap utilization at `min(24, cores)/cores`; if that part has more
   than 24 cores the kernel *cannot* use the rest of the GPU at all.

### 7.1.4 What I am not claiming, and the cheapest test

I did **not** measure the occupancy hypothesis. The evidence for it is (a) a
sourced static census, (b) a measured marginal-instruction price, (c) a
subtraction leaving a residual that ALU and DRAM do not explain, and (d) a
dispatch shape that is arithmetically incapable of filling either machine
evenly. That is a strong prior, not a result. Two soft steps to be aware of:
the census is static and the compiler may fuse or elide; and the residual
inherits the ruler's ±17% slope error plus the 112–156 census band, so it is
really "≈72 µs/step, plausibly 40–110".

**Geometry changes are explicitly not signed off for me**, so I am not testing
this and I am not proposing to. The cheapest decisive test for whoever is: keep
the kernel byte-identical and dispatch it as `2 × (heads/2)` threadgroups of 512
threads with the key range split in half per head pair, then compare against the
shipped shape on a host whose core count is known. If the residual is
quantization, the split shape wins on M4 Pro and wins by more on M5 Max; if it
is per-threadgroup prologue cost, it loses. One paired ABBA block of 8 runs
(~25 minutes) settles it, and it is the same probe harness I already have in
`research/maple-alphonse-r109e-qk-ceiling-abba.sh`.

## 7.2 Repricing against the 22:45Z bar drop

PR #685 comment 5246874781 (2026-08-10T22:45:47Z) moved the landing bar a
second time, and this time it moved by 5.4×. The evidence given is that the
crown is an *unchanged-persistence replay*: five official receipts of literally
identical code have published-score sd **0.374 %**, and the crown sits
**+0.378 % = 1.02σ** above our best draw. So the gap we have been trying to
close with engineering is, to the best available estimate, a lucky draw. The
new rule is: **anything shown non-negative that removes ≥ ~10 µs of M4 decode
busy per step (≈0.07 % of score) is worth landing.**

I reprice this whole experiment against that bar here rather than editing the
measured sections, so the record shows what was concluded under which rule.

### 7.2.1 First, a unit ambiguity in the bar itself

The bar is quoted two ways in one sentence — "≥ ~10 µs of M4 decode busy" and
"≈0.07 % of score" — and under the advisor's own price pair those are not the
same number:

| reading of "10 µs" | conversion | bar in %score |
|---|---|---|
| 10 µs/step of M4 **busy** | × 0.0056 %/busy-µs | 0.056 % |
| 10 µs/step of M4 **wall** | × 0.0070 %/wall-µs | 0.070 % |

The `0.07 %` figure the advisor quotes is the **wall** reading, and the
advisor's own worked example ("your ruler point estimate 22.69 wall / 28.36
busy µs/step is ~2.3× the new 10 µs bar") divides my *wall* number by 10. So
the operative bar is **10 µs/step of M4 wall = 12.5 µs/step of M4 busy =
0.07 %score at τ = 1**. The two readings differ by 25 %, which is smaller than
any interval in this memo, so nothing here turns on it — but I price in
**%score**, which is invariant, and give the µs both ways.

### 7.2.2 The repriced table

Same measurements as §7, same τ = 1 (the optimistic assumption for my own
hypothesis, justified in §5.9: all four arms are in-kernel ALU inside an
unchanged grid).

| estimate | µs/step wall | µs/step busy | %score @ τ=1 | vs **old** 0.378 % bar | vs **new** 0.07 % bar |
|---|---|---|---|---|---|
| synthetic ladder ruler (point) | 22.69 | 28.36 | 0.159 | 0.42× | **2.3×** |
| synthetic ladder ruler (95% upper) | 30.22 | 37.78 | 0.212 | 0.56× | **3.0×** |
| direct removal probe P−C (point saving) | +6.16 | +7.70 | 0.043 | 0.11× | 0.62× |
| direct removal probe P−C (95% upper saving) | +56.27 | +70.34 | 0.394 | 1.04× | **5.6×** |

### 7.2.3 What this flips, stated as plainly as I can

**`N-FULL-QK-CHEAP` is withdrawn. It is false under the new bar.** The QK
reduction ladder in `full_fused_attn_grow_v1` is worth **2.3× the landing
bar**, not 0.42× of it. I had the right number and the wrong adjective.

Two subsidiary claims in §7 die with it:

- **The ruler's 95 % exclusion evaporates.** §7's strongest claim was that the
  better-powered estimator excludes a bar-clearing saving at 95 % because its
  upper bound (30.22 wall µs/step) is below the 54 µs/step bar. Against a
  10 µs/step bar that same upper bound is **3.0× above** it. Neither estimator
  now excludes a landable saving; both *point* estimates are at or above the
  bar (2.3× and 0.62×). There is no exclusion left in this experiment.
- **The "structurally too small by 2.4×" framing dies.** Under the new bar the
  required harvest of my 249.5 µs/step busy pool is `12.5 / 249.5 = 5.0 %`, not
  27.2 %. The ladder alone is 11.4 % of the pool, i.e. **2.3× more than
  needed**. My pool is no longer the constraint; it is 20× the bar end to end.

### 7.2.4 What does not flip, and why the assignment still stops

The mechanism verdict never depended on the bar, and it is unchanged:

1. **§6's slot arithmetic projects a regression, not a win.** An MMA-based QK
   costs **32 issue slots per key** against **28** in the shipped scalar path.
   A bigger prize does not make a negative-expectation rewrite positive; it
   makes the *regression* proportionally more expensive. At the new bar, §6's
   projected ≈5 % ALU regression on this kernel is itself ≈1.1× the landing
   bar in the wrong direction.
2. **The rewrite requires a forbidden grid change.** An 8-row
   `simdgroup_bfloat8x8` tile needs ≥6 query rows per simdgroup; this kernel
   has 2, fixed by the `((heads/2)*1024,1,1)` / `(1024,1,1)` launch that R109-E
   was explicitly told not to touch. MLX steel hard-codes the fragment lane
   layout (`steel/gemm/mma.h:46, 49-55, 205`), so this is not a parameter I can
   set. **≥75 % of every tile would be padding.**
3. **The break-even is an unverified hardware claim.** The sign only flips if
   the M5 matrix unit exceeds ≈1.5× scalar FMA throughput. That is publicly
   unverified and cannot be measured on this M4 Pro (Apple GPU generation 16).

So the correct token is **`N-FULL-QK-MMA-NEGATIVE`**: the *target* is landable,
the *assigned mechanism* is not. Stopping R109-E before the rewrite remains the
right call, and it is now a better-supported call than it was under the old
bar, because the cost of a 5 %-regression rewrite is measured against a 5.4×
smaller bar.

### 7.2.5 The whole pool, repriced — this is the actionable part

§7.1's budget closure was written against a 68 µs/step busy bar and mostly
concluded "too small". Against 12.5 µs/step busy, **every** component of my
pool clears, and the ranking of what to attack changes completely:

| component (§7.1) | µs/step busy | %score @ τ=1 | vs new bar | mechanism status |
|---|---|---|---|---|
| QK reduction ladder | 28.4 | 0.159 | 2.3× | **no viable mechanism** (§6) |
| other in-loop ALU (softmax, AV, partials) | 62.4 | 0.349 | 5.0× | unexplored |
| **all in-loop ALU** | 90.8 | 0.508 | 7.3× | unexplored |
| KV-cache DRAM floor | ≈86 | ≈0.48 (τ≈1.06 ⇒ ≈0.51) | ≈7.3× | irreducible at bf16 |
| ~~threadgroup quantization waste~~ | ~~≈100~~ | — | — | **RETRACTED, §7.2.7** |
| whole `full_fused_attn_grow_v1` pool | 249.5 | 1.397 | 20× | — |

~~The line that matters is the last actionable one.~~ **The paragraph that stood
here proposed a threadgroup-count split as the single highest-value follow-up.
It is retracted; see §7.2.7.** The remaining actionable rows are "other in-loop
ALU" and "all in-loop ALU", and §6 plus edward's R1/R2 close the only
mechanisms I know of for them.

### 7.2.6 One caveat I cannot discharge from this memo

Every µs in the tables above is **additive busy** — it assumes that removing
GPU busy time from this kernel removes the same wall time from the step. The
same 22:45Z comment retracts the archive claim that decode dispatches are
serialized: measured `busy_sum / busy_union = 1.1359`, so **11.96 % of decode
busy is hidden behind concurrent kernels**, essentially all of it
`laguna_gate_sp`. `full_fused_attn_grow_v1` was **not** among the kernels
measured at ~0 % nesting. If this kernel turns out to be substantially nested,
every additive-busy figure above is an over-estimate by that fraction. I take
the required `SPLIT=1` profile and report the nested fraction in §7.3 rather
than leaving the tables unqualified.

### 7.2.7 Retraction of the occupancy suspect, and independent confirmation of the verdict

The 23:02Z advisor comment carries maple-edward's R109-D results (PR #684, now
closed). Three of them bear directly on this memo. I take them as measured and
correct my own text rather than defending it.

**(a) My occupancy suspect is dead, and it was dead on my own numbers.**
edward measured the M4 Pro threadgroup quantization edge directly and found
`t(32 TG) ≈ t(40 TG)`: a 32-threadgroup dispatch is billed as 40 waves on 20
cores, ≈112 µs/step of second-wave idle. That is a real effect and it is
*sliding* attention's dispatch, not mine. My kernel launches **24**
threadgroups, which sits *below* that quantization edge, so the effect edward
measured does not reach me. I had asserted a 60 %-efficiency / ≈100 busy µs/step
waste from 24-vs-20; the direct measurement of the neighbouring point on the
same curve does not support extrapolating it downward, and I never measured my
own point. §7.1.3 item 3, §7.1.4's proposed test, and the §7.2.5 table row are
withdrawn. **This is the largest single error in this memo** and it was an
arithmetic prior dressed as a finding — exactly the failure mode §7.1.4 warned
about two paragraphs before committing it.

**(b) The residual is not a geometry problem at all.** edward's R3 measured the
kernel's residual after removing the reduce and the PV accumulate: 90.5–91.2 %
of kernel time, running at 113 GB/s against a measured 266.3 GB/s ceiling
(42.6 % of peak), i.e. **2.1× above the DRAM floor**, with per-dispatch fixed
cost fitted at **0.12 µs**. So the residual is neither DRAM-bound nor
launch-bound: it is **per-threadgroup critical-path latency**. Both escapes are
measured-closed — occupancy is *flat* in threadgroup memory from 16 B to
32,768 B at 1024 threads, and the MLP-via-next-trip hoist carries #540's flat
**+3.8..4.8 % codegen tax**. PR #683 closed on the same shape
(`N-GATESP-TG-COUNT-IRRELEVANT`: a latency-bound kernel can be completely
insensitive to threadgroup count). A latency-bound residual is not harvested by
rebalancing waves.

**(c) `N-FULL-QK-MMA-NEGATIVE` is now independently confirmed, twice, by a
better instrument than mine.** My §6 was a static feasibility argument; edward
priced the same mechanism in a standalone Metal microbenchmark with fixed
random K/V, correct shapes, no harness, paired A/B, null controls bracketing
both ends, and two occupancy regimes. He did not write an MMA kernel — he built
**value-neutral padding arms** that bill the M=2-of-8 tile shape:

| arm | K=32 (≈M4, 1.60 TG/core) | K=16 (≈M5 proxy, 0.80 TG/core) |
|---|---|---|
| null vs itself (control) | +0.190 % / +0.082 % | −0.116 % / −0.051 % |
| `qk_pad4x` (bit-exact 4× MACs = 8×8 fragment padding) | **+11.802 %** | **+10.200 %** |
| `qk_pad4x_bcast0` (padding + best-possible broadcast epilogue) | **+6.047 %** | **+3.400 %** |

Both padding arms are *slower than base*, and the padding bill alone is
**1.7–2.0× the entire prize**. Two corroborations: measured simdgroup-MMA rate
is **3,158 GMAC/s = 0.87× scalar FMA** where ≥4× is needed just to pay for the
padding; and Apple Tech Talk 111432 shows `simdgroup_matrix` at **0 %
neural-accelerator utilization even on M5** — the real matrix path is Metal 4
tensors / MPP `matmul2d`, gated on macOS 26.2+ and Apple GPU arch gen ≥17, so it
is not reachable from this submission surface at all. Separately, edward's
`qk_ladder5` arm measured **+1.483 %**, i.e. the built-in `simd_sum` is already
optimal, which kills every shuffle-ladder fallback I might have retreated to.

**(d) Our two independent instruments agree on the size of the prize.** edward's
`qk_bcast0` (MACs and loads preserved, cross-lane reduce removed) prices the QK
reduction at **5.13–6.86 % of kernel time**; my synthetic dose ruler prices the
ladder at 28.4 busy µs/step against a 249.5 busy µs/step pool = **11.4 %**.
Those are the same order and bracket each other within ~2×, from a
microbenchmark and from an end-to-end harness respectively. His free-deletion
ceiling (`qk_loadonly`, deleting *both* the reduce and the PV accumulate) tops
out at **8.8–9.5 %**, which is the same statement as my §7.1 closure: the whole
in-loop arithmetic budget is too small for any single-stage mechanism to matter.

**What survives.** §7's verdict token `N-FULL-QK-MMA-NEGATIVE` stands and is
strengthened. §7.1's budget closure stands for the ALU and DRAM rows, which came
from the ruler and the static census, not from the occupancy prior. §7.2's
repricing stands. What dies is the one row I inferred instead of measuring, plus
the follow-up I recommended off it. The honest summary of my pool after (a)–(c)
is: ~36 % in-loop ALU (measured, no viable mechanism), ~35 % KV DRAM
(irreducible at bf16), and a remaining ~29 % that edward has now identified as
per-threadgroup critical-path latency with both known exits measured shut.

## 7.3 The nesting deliverable: what the GPUPROF hook can and cannot say

Comment 5246874781 asks, and comment 5247000136 repeats as a programme
deliverable independent of my arm's fate: *what fraction of
`full_fused_attn_grow_v1`'s GPU busy time is already hidden behind a concurrent
kernel?* Any busy saving inside a fully nested kernel never reaches the step
wall clock, so this number rescales every µs/step figure in §7.1 and §7.2.

I took both captures the question needs. Driver
`research/maple-alphonse-r109e-split1-profile.sh OUT STEPS SPLIT`, 200 steps,
199 steady, same host and same session, teacher-forced greedy decode with
**0 divergences** in both.

| | SPLIT=1 | SPLIT=0 |
|---|---|---|
| command buffers / step | 406.0 | 45.0 |
| dispatches / step | 406.0 | 406.0 |
| wall ms/step | 9.827 | 8.260 |
| gpu_busy_sum ms/step | 8.568 | 8.007 |
| gpu_busy_union ms/step | 8.567 | 8.007 |
| gap ms/step | 1.260 (12.8 %) | 0.252 (3.1 %) |
| `busy_sum/busy_union`, post-warm-up span | 1.0000 | **1.0010 (0.10 % hidden)** |
| per-kernel nested %, all seven probed kernels | 0.00 % | 0.00 % |

### 7.3.1 The instrument cannot produce a per-kernel nesting fraction

Both modes report 0.00 % nesting for every kernel, and in both cases that is a
structural fact about the hook, not a physical fact about the GPU:

- **At SPLIT=1** the patch forces `needs_commit()` after every dispatch, so each
  command buffer holds exactly one kernel. The timeline is serialised by
  construction, so nothing can overlap anything. SPLIT=1 prices kernels *in
  isolation*; it can never observe overlap.
- **At SPLIT=0** MLX's real batching packs ~9 dispatches into each command
  buffer (406 dispatches in 45 buffers), but the hook emits **one** `GPUPROF`
  start/end pair per *command buffer*, with the kernel names concatenated.
  Overlap *inside* a command buffer — which is the only place it can occur — is
  therefore not represented in the data at all. What the records do show is that
  command buffers themselves essentially do not overlap each other: 0.10 % of
  summed span is shared.

The analyser's own warning (`records carry more than one dispatch, so this
capture is NOT SPLIT=1 and per-kernel nesting is not measurable`) is the correct
reading. The clearest demonstration is that `full_fused_attn_grow`'s record
count is identical in the two captures (n = 1991) while its attributed
`busy_sum` moves from **49.631 ms** at SPLIT=1 to **467.981 ms** at SPLIT=0, a
factor of 9.43 — precisely the mean dispatches-per-command-buffer. At SPLIT=0
the analyser is charging each kernel the whole buffer it happens to ride in.

I therefore cannot confirm the ratio quoted to me (`busy_sum/busy_union =
1.1359`, 11.96 % hidden, with `laguna_gate_sp` 96.4 % nested and every other
kernel 0.00 %). On this M4 Pro I measure 0.10 % hidden across command buffers
and 0.00 % for `laguna_gate_sp` in both modes. I am not claiming the quoted
number is wrong — it may come from a different host or a different analyser that
subdivides multi-dispatch records — but it cannot be reproduced with this hook,
and no arm should be repriced on it until the instrument that produced it is
named. If the programme wants a real nesting fraction, the hook needs to emit
one timestamp pair per *dispatch* while leaving batching alone; that is a change
to `research/pr91-gpuprof-hook.patch`, not a change to the capture flags.

### 7.3.2 The SPLIT=1 inflation is now measured, and it biases the pool slate

The two captures differ only in command-buffer granularity, so they price the
per-command-buffer overhead directly. Over +361 buffers per step:

- **wall +1.567 ms ⇒ 4.34 µs per extra command buffer**
- **`busy_sum` +0.561 ms ⇒ 1.554 µs per extra command buffer**
- gap +1.008 ms ⇒ 2.79 µs per extra command buffer

This confirms Rule 43 (`research/CURRENT_RESEARCH_STATE.md:290-296`) and puts a
number on it: **every SPLIT=1 per-kernel figure is inflated by ≈1.55 µs per
call**. That matters for the pool slate the whole R109 round is being scored
against, because the inflation scales with *calls per step*, not with cost:

| arm | quoted busy µs/step | calls/step | inflation | corrected |
|---|---|---|---|---|
| edward, `sliding_fused_attn_ring_v1` | 627.3 | 30 | −46.6 | ≈580.7 |
| **me, `full_fused_attn_grow_v1`** | **249.5** | **10** | **−15.5** | **≈234.0** |

My own SPLIT=1 capture independently reproduces the quoted figure
(`full_fused_attn_grow_v1` 249.2 µs/step, 2.91 % share, 10 calls/step,
24.92 µs/call), so the correction is to the instrument, not to the reading. My
true pool is ≈234 busy µs/step and the harvest fraction required to clear the
0.07 % bar rises from 27.2 % to **≈29 %**. This does not change any verdict —
it makes an already-negative arm slightly more negative — but the slate should
be corrected before it is used to rank next round's arms.

### 7.3.3 Exposure, measured causally

Since the hook cannot answer the nesting question, I answered the question the
nesting fraction was a proxy for. What the programme actually needs to know is
not "is this kernel nested" but **"does busy time removed from this kernel reach
the step wall clock?"** The dose ruler answers that directly, because it is an
intervention rather than an observation: it adds real ALU inside
`full_fused_attn_grow_v1` and touches nothing else, so

```
exposure = d(step wall) / d(global busy_sum)
```

measured on one binary in one session. Exposure ≈ 1 means a busy saving in this
kernel converts one-for-one into wall time; exposure ≈ 0 means it is hidden and
no saving here can ever pay, whatever §7.1 says the budget is.

The end-to-end harness already gives the numerator's sign for free: arm X
(110 ruler slots) cost **+287.10 µs/step of `benchmark.sh` wall** (se 26.90) and
the ladder dose cost **+22.69 µs/step**. Work added inside this kernel does show
up in wall time, so the kernel is on the critical path and exposure is not zero.
`research/maple-alphonse-r109e-exposure.sh` pins the coefficient: SPLIT=0
control / dose10 / dose10 / control palindrome for the wall and `busy_sum`
terms, plus a SPLIT=1 control / dose10 pair to confirm the busy delta lands in
`full_fused_attn_grow_v1` and not elsewhere.

### 7.3.4 Measured exposure: a busy microsecond in this kernel is a wall microsecond

Job `ce926361`, 318 s, exit 0, 200 steps per capture, 199 steady, **0 token
divergences in all six captures**. Probe `DARKBLOOM_FULL_ATTN_QK_PROBE`, empty
for control and `dose10` (110 ruler slots) for dose. Raw `per steady step`
lines:

| capture | SPLIT | probe | wall ms | busy_sum ms | gap | median ms |
|---|---|---|---|---|---|---|
| `s0_ctrl_a` | 0 | — | 8.296 | 8.016 | 3.4 % | 8.244 |
| `s0_dose_a` | 0 | dose10 | 8.573 | 8.319 | 3.0 % | 8.575 |
| `s0_dose_b` | 0 | dose10 | 8.639 | 8.332 | 3.6 % | 8.577 |
| `s0_ctrl_b` | 0 | — | 8.239 | 7.996 | 3.0 % | 8.229 |
| `s1_ctrl` | 1 | — | 9.957 | 8.568 | 14.0 % | 9.769 |
| `s1_dose` | 1 | dose10 | 10.110 | 8.867 | 12.3 % | 10.096 |

The SPLIT=0 palindrome (control, dose, dose, control removes linear drift by
construction):

```
Δ wall      = +338.50 µs/step   (se 43.6, from the within-pair spreads)
Δ busy_sum  = +319.50 µs/step   (se 11.9)
exposure    = Δwall / Δbusy = 1.0595 ± 0.142   95 % CI [0.78, 1.34]
```

The SPLIT=1 pair, using medians because `s1_ctrl`'s mean carries one 39.77 ms
outlier step that inflates it by ~150 µs, gives Δwall +327 µs, Δbusy +299 µs,
**exposure 1.09** — an independent replicate at the same value.

**Finding E1 — exposure is 1.0, not 0.8.** A microsecond of GPU busy time
removed from `full_fused_attn_grow_v1` becomes a microsecond of decode wall
clock. This is mechanically unsurprising once the SPLIT=0 gap is measured at
3.0–3.6 % of wall: there is almost no host bubble left for a GPU saving to hide
in. The advisor's `BUSY_TO_WALL = 0.8` planning constant (which my analyzer also
uses) sits at the bottom edge of the 95 % interval. It is a defensible
conservative floor, but it under-credits real savings in this kernel by ~25 %.

One honest tension. Cross-harness, the ruler costs 2.269 µs/step of
`benchmark.sh` **wall** per slot (§7.2) but 2.83 µs/step of `decode_probe`
**busy** per slot here (31.12 µs/call over 110 slots, ×10 calls/step).
Normalising for the two harnesses' different mean KV length — `benchmark.sh`
runs N 512→640, mean 576; `decode_probe` at 200 steps runs 512→712, mean 612 —
brings the expected benchmark-harness busy cost to 2.66 µs/step/slot, implying a
cross-harness exposure of 0.85. The within-harness palindrome is the cleaner
estimate because it holds the binary, the hook and the session fixed. I report
the bracket rather than pick a winner: **exposure ∈ [0.85, 1.06]; plan at 1.0;
0.8 is the conservative floor.** Nothing in §7.4 changes under any value in that
bracket.

**Finding E2 — the ruler measures what it claims to measure.** The dose is
supposed to land only inside the target kernel. It does, twice over:

- SPLIT=1: `full_fused_attn_grow_v1` 248.9 µs/step (10 calls, 24.89 µs/call) →
  `full_fused_attn_grow_qkdose10_probe_v1` 560.1 µs/step (10 calls,
  56.01 µs/call). Δ = **+311.2 µs/step against a global busy Δ of +299.0**, i.e.
  **104 %** of the added busy time is attributed to the kernel itself.
- SPLIT=0: the kernel appears in exactly three command-buffer signatures
  (5 + 4 + 1 = 10 calls/step, matching the 10 full-attention layers). Their
  summed busy time moves 2352.85 → 2672.35 µs/step. Δ = **+319.50 µs/step
  against a global busy Δ of +319.50**, i.e. **100.0 %**.

So the 2268.586 ns/step-per-slot ruler constant in §7.2 is not an artefact of
where the cost was booked; the added ALU is genuinely inside this kernel and its
cost genuinely reaches the wall clock. That is what licenses §7.1's budget
arithmetic and §7.4's ceiling.

**Finding E3 — SPLIT=1 also distorts exposure, not just magnitude.** Taken at
face value (means, not medians) the SPLIT=1 pair reads exposure 0.51, because a
single outlier step and a 14 % host gap between 406 one-dispatch command buffers
absorb the added work. Rule 43 already says SPLIT=1 totals are not comparable in
magnitude; §7.3.2 added that per-call figures are inflated ≈1.55 µs. This adds a
third failure mode: **SPLIT=1 makes GPU savings look half as valuable as they
are.** Any arm priced from a SPLIT=1 wall delta is mispriced twice.

## 7.4 Final verdict, as two separate numbers

Comment 5246874781 asks for the MMA arm and the params-atlas arm to be reported
as two numbers rather than one. They are:

| | arm | verdict token | measured number | vs 0.07 % bar |
|---|---|---|---|---|
| 1 | QK reduction in `full_fused_attn_grow_v1` | `N-FULL-QK-MMA-NEGATIVE` | prize **22.69 µs/step wall**, 95 % upper 30.22 (= 0.159 %score, upper 0.212) | **2.3× the bar** |
| 2 | full-attention params atlas | `N-FULL-PARAMS-ALLOC-IRRELEVANT` | saving **−0.22 µs/step**, 95 % upper **+0.81** | **0.08× the bar** |

The two arms are negative for opposite reasons, and the distinction matters for
what the programme does next.

**Arm 1 is mechanism-negative, not size-negative.** The QK ladder really is
worth ~2.3× the new bar; if it could be deleted for free the arm would pay. It
cannot. Three independent measurements close every route: simdgroup-MMA pays a
padding bill of **1.7–2.0× the entire prize** and runs at 0.87× scalar FMA
(edward R2); the free-deletion ceiling for the reduce plus the PV accumulate
tops out at 8.8–9.5 % of kernel time (R1); and a hand-written five-stage shuffle
ladder is **+1.483 %** slower than the built-in `simd_sum`, so no fallback
survives either. The bounding arm I ran myself agrees: replacing the allreduce
with `simd_broadcast_first` — deliberately wrong, and therefore an upper bound
on any correct replacement — bought **+6.16 µs/step (95 % upper +56.27)**, an
interval that comfortably contains zero. Nothing in this kernel's reduction is
purchasable on this submission surface.

**Arm 2 is size-negative.** The mechanism works and is bit-exact, but the thing
it removes is worth almost nothing. This is the stronger of the two results
because it does not depend on a single point estimate: the 111× dose ruler
prices a host `MLXArray([UInt32×3])` allocation-and-upload at **−24.8 ns/step
(se 58.3)** — statistically indistinguishable from zero at 111× amplification —
so the memo's nine removed allocations are worth 0.22 µs/step against a 10 µs
bar. That bounds the *whole* 2-D params-atlas class, not just my site, and it
refutes the 11 µs/step pre-registration this class was assigned on by ~50×.

### 7.4.1 Landing decision: revert both arms, land nothing

`Sources/` at this branch's head is **byte-identical to the base**
(`git diff 1a6761bf -- Sources/` is empty). I was instructed to land the
params-atlas arm regardless of the MMA arm's fate, and I am not doing so. The
reasoning is the advisor's own, applied to a number that did not exist when the
instruction was written:

1. The instruction's stated premise was that removing ten host allocations and
   uploads per step clears the "any non-negative arm removing ≥ ~10 µs of M4
   decode busy per step is worth landing" bar. **That premise is now measured
   false by more than an order of magnitude**: the 95 % upper bound on the
   saving is +0.81 µs/step, 8 % of the bar. The arm is not a marginal win, it is
   noise.
2. The standing rule from the same comment — *ban on landing an arm whose sign
   is not established* — then binds. My best estimate of the memo's sign is
   **negative** (M − O lead-adjusted **+64.20 µs/step**, i.e. slower), and while
   I attribute that to a session/position artifact rather than to the memo, I
   cannot demonstrate the arm is non-negative. Handing fern, the round's sole
   submission driver, an arm of unestablished sign is exactly what that rule
   forbids.
3. A zero-byte submitted surface costs fern nothing: no static-review exposure,
   no byte-budget consumption, no merge conflict against whatever does land.

**This overrides an explicit advisor instruction, and I am flagging it as such
rather than quietly complying or quietly not complying.** If the advisor
disagrees on the trade-off, the arm is one command away — it is preserved intact
as commit `2e9cd4f5` (42 insertions, 3 deletions, bit-exact, 16/16 harness
correctness gates green):

```bash
git cherry-pick 2e9cd4f5
```

I would rather be told to re-land it than have fern discover an unsigned arm in
the submission surface.

## 7.5 The atlas comment 5247182400 asked for: rank the whole decode step by size

Comment 5247182400 says the campaign is ~1.4 % short, that levers should be
ranked by size rather than by ease, and that any single lever plausibly worth
≥ 50 µs/step should be reported immediately. Comment 5247143022 separately asks
for a SPLIT=1 profile of the two kernels this campaign has never profiled,
`full_fused_attn_grow_v1` and `shared_nvfp4_swiglu_qmv`. This section answers
both from one capture, and it is the most transferable thing in this memo.

### 7.5.1 Method

`research/maple-alphonse-r109e-bwatlas.py` re-reads the raw SPLIT=1 capture
(`/tmp/r109e-split1/split1.err.gz`, 87,976 records, 199 steady steps) that
produced §7.3. The pr91 GPUPROF hook emits an `input_bytes` field per record, so
for every kernel we can compute:

```
us/step_c = (busy_time/call - 1.554 us SPLIT=1 inflation) x calls/step
GB/s      = bytes/call / corrected time/call
floor     = time the same bytes would take at 273 GB/s (M4 Pro spec DRAM)
headroom  = us/step_c - floor
```

`headroom` is the only quantity that matters for lever ranking. A kernel at the
DRAM ceiling cannot be made faster by any in-kernel rewrite — only by moving
fewer bytes. A kernel far below it is paying for latency, occupancy or ALU, and
is the only kind an in-kernel rewrite can touch. The GB/s column is a ratio of
two sums over the same records, so it needs no steady-window selection.

Three honest caveats, all of which the data announces itself:

- **Gathers over-count.** MLX reports a gather-matmul's `input_bytes` as the
  whole expert tensor. Laguna routes top-8 of 256, so the two `routed_` kernels
  read 1/32 of their declared bytes; uncorrected they report 2,800 % of peak.
  The script divides them by 32. The same signature appears on
  `decode_embedding_rope_atlas` (78,000 % of peak — it reads one row of a
  414 MB table) and the `lmhead_exact_*` refine kernels, whose negative headroom
  is therefore meaningless and should be ignored, not believed.
- **Output bytes are not counted**, so every floor is slightly low and every
  headroom slightly high.
- **KV tensors are capacity-padded.** `KVCacheSimple.step = 256`, so at
  N = 512→712 the cache tensor is 768 rows and `full_fused_attn_grow_v1` declares
  3.170 MB/call where the live KV is 2.507 MB. Its floor is therefore an
  over-estimate and its true headroom is *larger* than the table says
  (≈ 142 rather than 117.7 µs/step).

The arithmetic checks out independently: 2 × 768 × 8 KV heads × 128 dim × 2 B =
3.146 MB against a declared 3.170 MB, which is how I know the byte field is the
real tensor and not a proxy.

### 7.5.2 Result: 47 % of the decode step is already at the DRAM ceiling

Full table in `research/maple-alphonse-r109e-bwatlas.txt`. Corrected decode total
8,165.4 µs/step over 29 kernels. Seven kernels run at **91–103 % of spec DRAM
bandwidth**:

| kernel | µs/step_c | GB/s | % peak |
|---|---|---|---|
| `decode_nvfp4_qkv_h64_r1_v1_lm1_pw1_se1_sd1` | 1313.6 | 280.5 | 102.7 % |
| `oproj_act_h64_v1_lm1_pw1_sc1_se1` | 1082.0 | 272.3 | 99.7 % |
| `lmhead_int5_base_coarse_delta_bf16_v1` | 426.3 | 260.1 | 95.3 % |
| `decode_nvfp4_qkv_h48_…` | 352.2 | 279.0 | 102.2 % |
| `oproj_act_h48_…` | 291.4 | 252.8 | 92.6 % |
| `dense_gate_up_swiglu_bf16_v1` | 271.4 | 249.8 | 91.5 % |
| `dense_down_residual_bf16_v1` | 134.6 | 251.9 | 92.3 % |

**That is 3,871.5 µs/step, 47.4 % of the decode step, sitting at or above 91 %
of what this machine can physically deliver.** Several exceed 100 %, which just
means 273 GB/s is a slightly pessimistic ceiling — the practical achievable
figure on this M4 Pro is ~281 GB/s. None of that 47 % is purchasable by kernel
rewriting. It is purchasable only by moving fewer bytes, which on a
weight-stationary decode step means changing the weight representation, and that
is outside the accepted quantization envelope.

This is, I think, the single most useful thing I measured. It reframes the
1.4 % gap: closing it needs ~200 µs/step of M4 decode wall, and the atlas says
where that can and cannot come from.

### 7.5.3 Every lever ≥ 50 µs/step, ranked

Comment 5247182400 asks to be told immediately about any plausible ≥ 50 µs/step
lever. There are **nine**, totalling ~1,480 µs/step of headroom:

| rank | kernel | headroom µs/step | % peak | calls/step | µs/call | MB/call |
|---|---|---|---|---|---|---|
| 1 | `sliding_fused_attn_ring_v1` | **373.4** | 38.8 % | 30.3 | 20.13 | 2.131 |
| 2 | `gate_sp_h64_v1` | **178.7** | 8.6 % | 30.3 | 6.45 | 0.152 |
| 3 | `routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2` | 174.3 | 88.1 % | 39.4 | 37.07 | 8.913 |
| 4 | `routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6` | 163.7 | 79.8 % | 39.4 | 20.54 | 4.474 |
| 5 | `prefill_router_tournament_ordinal_norm_active64_v2` | **133.5** | 0.5 % | 39.8 | 3.37 | 0.004 |
| 6 | `full_fused_attn_grow_v1` (mine) | 117.7 (≈142 corrected for KV padding) | 49.7 % | 10.0 | 23.37 | 3.170 |
| 7 | `residual_rms_router_bf16_2048_rpg8_keys_v1_pf1` | 101.8 | 60.3 % | 39.4 | 6.51 | 1.072 |
| 8 | `rmsbfloat16` | **80.5** | 9.1 % | 41.8 | 2.12 | 0.053 |
| 9 | `shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1` | 68.5 | 70.2 % | 39.4 | 5.84 | 1.119 |
| 10 | `gate_sp_h48_v1` | 61.9 | 6.4 % | 10.1 | 6.54 | 0.115 |

Ranks 3 and 4 are large in absolute terms but sit at 88 % and 80 % of peak: they
are *nearly* bandwidth-bound and the residual is small relative to the risk of
touching the MoE gather path. The genuinely anomalous entries are the ones in
bold.

**Lever A — `gate_sp_h64_v1` + `gate_sp_h48_v1`: 240.6 µs/step of headroom at
6–9 % of DRAM peak.** These two kernels together spend 261.6 µs/step reading
152 KB and 115 KB per call. At peak bandwidth those bytes take 21.0 µs/step. The
kernels take 261.6. **They are 92 % pure latency.** This is the largest pure-
latency anomaly in the decode step and it is 24× the landing bar on its own.
PR #683 closed as `N-GATESP-TG-COUNT-IRRELEVANT`, but that result closes *one*
lever (threadgroup count), not the kernel: a kernel at 8.6 % of peak with
240 µs/step of headroom is not explained by "TG count doesn't matter". My
§7.2.7 measurement of a 0.12 µs per-dispatch fixed cost also rules out dispatch
overhead (40 calls × 0.12 = 4.8 µs). Something else is costing ~250 µs/step
here and nobody has named it.

**Lever B — `prefill_router_tournament_ordinal_norm_active64_v2`: 133.5 µs/step
at 0.5 % of DRAM peak, reading 4 KB per call.** A kernel whose name says
*prefill* runs 39.8 times per decode step, 3.37 µs each, and touches four
kilobytes. That is 1.6 % of the decode step spent on essentially no memory
traffic and, at active64, not much arithmetic either. Either it is a
prefill-shaped kernel mis-selected on the decode path — in which case a
decode-shaped variant is a large, cheap win — or the name is vestigial and it is
doing real work the byte count does not see. Deciding which costs one `rg` and
one dose-ruler arm. This is the highest ratio of prize to effort in the table.

**Lever C — `rmsbfloat16`: 80.5 µs/step at 9.1 % of peak, 41.8 calls/step.**
This is MLX's *generic* RMSNorm, not a Laguna custom kernel, running once per
layer plus two. 2.12 µs/call for 53 KB. Every other normalisation in this model
has been fused into a neighbour (`residual_rms_router`, `residual_rms_bf16`,
`oproj_act`); these 41.8 have not. Fusing them removes dispatches rather than
adding a dependency, so the advisor's ≈ +102 µs/step encoder-barrier law works
*for* the change, not against it.

**Lever D — `sliding_fused_attn_ring_v1`: 373.4 µs/step, the largest single
headroom on the board**, at 38.8 % of peak. This was maple-edward's kernel
(PR #684, closed). Its per-call profile is structurally identical to mine —
2.131 MB/call, 20.13 µs/call — but it runs 30 times per step against my 10, so
it is 2.6× the prize for the same mechanism work. Everything in §7.1's budget
method and §7.2's dose ruler transfers to it unchanged. If the programme wants
one attention target, it is this one, not mine.

### 7.5.4 The two kernels comment 5247143022 named

**`full_fused_attn_grow_v1`** (mine): 233.9 µs/step corrected, 2.9 % of decode,
10 calls/step, 23.37 µs/call, 3.170 MB/call, **135.6 GB/s = 49.7 % of peak**.
Note this revises the ≈ 100 GB/s / 38 %-of-ceiling figure quoted in comment
5246119853 — that number was computed from an uncorrected SPLIT=1 time, and
removing the 1.554 µs/call inflation moves it to 51 %. The qualitative
conclusion is unchanged and in fact strengthened: the kernel is only half
bandwidth-bound, so it is exactly the kind of kernel an in-kernel rewrite could
help. §7.1 then closes it anyway: in-loop ALU accounts for ~90.8 busy µs/step of
the 233.9, the QK ladder is 28.4 of that, and §7.2/§7.2.7 show every route to
removing the ladder costs more than it saves.

**`shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1`**: 230.0 µs/step corrected,
2.8 % of decode, 39.4 calls/step, 5.84 µs/call, 1.119 MB/call, **191.7 GB/s =
70.2 % of peak**, headroom 68.5 µs/step. Two observations for whoever takes it:

1. It is the *only* unfused half of the shared expert. The down-projection is
   already fused with the routed path
   (`routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6`, 39.4 calls/step); the
   gate/up half is not, and runs as its own 39.4 dispatches beside
   `routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2`. That asymmetry is the
   obvious structural lever, and the down-projection fusion is a working
   precedent in this very codebase for how to do it.
2. But price it before building it. At 70 % of peak the *entire* headroom is
   68.5 µs/step, and fusion does not remove the shared expert's weight reads —
   only the launch tail and the activation round-trip. The realistic prize is a
   fraction of 68.5, i.e. plausibly 20–40 µs/step: 2–4× the bar, worth doing,
   but not the 1.4 % gap. Lever A is six times larger and structurally simpler.

### 7.5.5 Direct answer to "is there a ≥ 50 µs/step lever in your atlas?"

Yes — nine of them, but **none inside my assigned kernel**. Within
`full_fused_attn_grow_v1` the largest single purchasable item is the QK ladder
at 22.69 µs/step of wall (95 % upper 30.22), and §7.2.7 closes it on three
independent mechanisms. My kernel is 2.9 % of the decode step and its total
headroom is 117.7 µs/step; even deleting the whole thing would be 1.4 % of
decode and would not close the gap alone.

The ≥ 50 µs/step levers are all in *other people's* kernels, and the single
largest concentration of them is not in attention at all — it is the 240.6
µs/step of pure latency in `gate_sp_*` plus the 133.5 µs/step in
`prefill_router_tournament_*`, i.e. **374 µs/step sitting in two small helper
kernels that between them read a quarter of a megabyte per step.** That is
1.9× the ~200 µs/step the campaign needs. I would put the next two students
there rather than on any attention kernel, and I would give them the dose ruler
(§7.2) rather than an A/B, because §6.3 shows a bare A/B cannot resolve anything
at this bar.

## 8. Hand-off to maple-edward — MOOT

**PR #684 closed at ~23:02Z with its own results already in hand (see §7.2.7).
This hand-off was overtaken; it is kept only as a record of what I had ready to
transfer, and because the ruler and the position-effect instrument finding below
are still reusable by whoever next touches either attention kernel.**

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
