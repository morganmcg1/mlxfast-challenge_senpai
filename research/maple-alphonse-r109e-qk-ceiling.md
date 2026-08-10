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
content) and derives two research kernels from it by textual substitution,
selected by `DARKBLOOM_FULL_ATTN_QK_PROBE`:

| arm | env | substitution | slots/site | correctness |
|-----|-----|--------------|-----------|-------------|
| `C` | unset | none — shipped `laguna_full_fused_attn_grow_v1` | 0 | must pass |
| `P` | `bcast` | `simd_sum(x)` → `simd_broadcast_first(x)` | ≈ −10 | must **fail** |
| `D` | `dose` | `simd_sum(x)*2^-5` then a 5-stage doubling butterfly | ≈ +11 | must **pass** |

Three design points matter.

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

**(c) Geometry is untouched.** `grid ((heads/2)*1024,1,1)`, `threadGroup
(1024,1,1)`, `inputNames`, and dispatch are byte-identical across arms; only the
six statements differ. Swift globals are lazy, so with the env var unset the
probe kernels are never even constructed and arm `C` is the shipped path.

## 3. Design

24 `./benchmark.sh --local-iterate` runs, `MLXFAST_LOCAL_FAN_PROMPT=0`, order

```
DCPPCD DCPPCD DCPPCD DCPPCD
```

Each 6-run block is a palindrome, so a linear drift cancels inside the block.
Estimators reported: unpaired Welch, an OLS fit of
`decode ~ 1 + linear-time + dummy(P) + dummy(D)`, and the mean of the four
per-block deltas. Every run re-enters the 40 °C thermal gate.

Driver `research/maple-alphonse-r109e-qk-ceiling-abba.sh`,
analysis `research/maple-alphonse-r109e-analyze.py`.

## 4. Results

<!--RESULTS-->

## 5. Pricing, and a correction the advisor needs

The brief prices the ceiling with `0.01642 %cs per M4 µs/step`, a decode
denominator of `8972 µs/step`, and a `18.222` figure. **None of
`0.01642`, `8972`, or `18.222` occurs anywhere under `research/`.** A full-text
search of the research tree returns the following, which is what I used instead:

* `research/CURRENT_RESEARCH_STATE.md:2441` (and `:1295-1296`, `:6449-6455`)
  fixes the campaign price at **`0.015228 %cs per M5 µs/step`**, derived as
  `0.75 / 4925.255 × 100`. It is an **M5** constant.
* **Rule 105** (`:6441`, `:6459-6463`) states explicitly that applying the M5
  constant directly to an M4 measurement over-credits by **2.0–2.6×**.
* **Rule 105.2** (`:6505-6514`) gives the transfer
  `Δ%cs = Δ_M4[µs/step] × k × 0.015228`, with `k = 0.4369` (α) →
  `0.006653`, `k = 0.389` → `0.005924`, `k = 0.5` (β) → `0.007614`; and
  (`:6520-6521`) instructs that for an **ISSUE-bound** family one should
  "use β = 0.5 as an upper bound and say that you did". I do.
* The decode-family census bounds `k_issue ∈ [0.267, 0.654]`
  (`research/maple-tanjiro-r107g-decode-family-regime-census.md:742-743,
  762-763`), i.e. `0.00407–0.00996 %cs per M4 µs/step`.

The brief's `0.01642` is **~2.2× the most permissive sourced constant** and
~1.08× the raw M5 constant — precisely the over-credit Rule 105 warns about. Any
gate expressed in it is ~2.2× too easy to pass.

This host needs one further adjustment. Its control decode is ~12,990 µs/step,
not the ledger's 8,448 (steady) / 8,984.5 (local-submit) M4 reference, so a
`k` calibrated on that faster M4 is not directly transferable. A relative
transfer that assumes decode fraction is preserved gives the host-matched price
`0.75 × 100 / 12,990 = 0.005774 %cs per local µs/step`.

Thresholds for the Stage 0 gate of 0.20 %cs, from most to least conservative:

| constant | %cs per µs/step | µs/step needed for 0.20 %cs |
|---|---|---|
| host-matched (this box) | 0.005774 | **≥ 34.6** |
| Rule 105.2 β = 0.5 upper bound | 0.007614 | ≥ 26.3 |
| `k_issue` census upper 0.654 | 0.009959 | ≥ 20.1 |
| brief's unsourced 0.01642 | 0.01642 | ≥ 12.2 |

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
2. Add the bit-exact `dose` arm. It is the only cheap way to tell "the ladder is
   free" from "my instrument is broken", and it keeps `passed_correctness=true`
   so a failed correctness check is a real signal.
3. Fragment layout for MMA is *not* specified by Apple; MLX steel hard-codes it
   (`steel/gemm/mma.h:46, 49-55, 205`). Mixed bf16×bf16→fp32 8×8×8 does lower to
   a native AIR intrinsic, so precision is not the obstacle — tile occupancy is.
4. Sliding attention has the same 2-query-rows-per-simdgroup limit, so the same
   ≤ 2/8 tile-utilization argument applies unless its geometry differs.
