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

**`N-FULL-QK-CHEAP`. Stop R109-E before any MMA implementation.**

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
   11 µs/step (range 4–20) before measuring; measurement in flight.
3. **Grid unchanged — proven, not asserted.** `git diff BASE -- Sources Vendor
   benchmark.json Package.swift | grep -c '^[+-].*\(grid:\|threadGroup:\)'`
   returns **0**. The full-attention dispatch at `LagunaRuntimeModel.swift:2547`
   is still `grid ((heads/2)*1024, 1, 1)`, `threadGroup (1024, 1, 1)` = 24
   threadgroups × 1024 threads. Every probe arm rewrites *in-kernel statements
   only*; all four arms share one dispatch shape.
4. **Non-empty submitted-surface diff** — `git diff --numstat BASE -- Sources
   Vendor benchmark.json Package.swift` returns
   `147  16  Sources/MLXFastModel/LagunaRuntimeModel.swift`.

On the fourth item's *shape*: the brief asked for bulk in a new
`Sources/MLXFastModel/LagunaFullAttnQKMMA.swift` with only registration and
dispatch selection in LRM. **I did not create that file, because the verdict is
`N-FULL-QK-CHEAP` and no MMA kernel is being written** — the file would be an
empty shell. The LRM delta is the probe instrument (three probe source
rewriters, a dose kernel generator, and a selector) plus the params memo, all of
which are inert when their environment variables are unset.

<!--VERDICT-->

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
3. **The likeliest owner of that residual is threadgroup quantization, and it is
   arithmetic anyone can check without a benchmark.** The dispatch is
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
