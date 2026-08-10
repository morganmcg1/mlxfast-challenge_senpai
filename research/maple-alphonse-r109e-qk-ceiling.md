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

| C slot | mean us/step | n |
|---|---|---|
| 1 (block lead) | see table in 4.1 | |
| 8 (block tail) | see table in 4.1 | |

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
