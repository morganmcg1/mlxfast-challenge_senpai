# A2 — fused-NAX `bn` 128 → 64 **and** `wn` 4 → 2 for prefill `N <= 1024`

Status (rev3): **live on the branch head and first in the firing order.**
Magnitude-capped, and still requires the Rule-83 disclosure in §6 before an M5
slot is spent.

Live on this branch as
`17 0 Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/matmul.cpp`; the patch
file `research/maple-tanjiro-r110/A2-fused-nax-bn64-n1024.patch` is retained for
provenance and is byte-equivalent to the head hunk.

**Direct answer to the `TN == 1` concern raised at rev3:** the shipped arm keeps
`TN = 2`, identical to the incumbent, because `bn` and `wn` are halved together
so `SN = bn/wn` is invariant at 32. The `TN == 1` risk belongs to the
**discarded** `bn`-only version. Full geometry in §2.

This document was rewritten after the first version of the arm was found to be
wrong in a way the local gate could not see. Read §2 before §5.

---

## 1. What the arm does

`steel_matmul_regular_axpby_nax()` picks the fused-NAX tile at
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/matmul.cpp:213-231`. On an
M5 (`devc == 's'`) the incumbent selection is

```
bk = (K >= 8192 && K > (M + N)) ? 64 : 256;
bm = 64;
wm = 2;
// bn and wn keep their generic values: bn = 128, wn = 4
```

A2 adds one guarded override:

```cpp
if (darkbloom_fused_nax_narrow_bn() && M >= 64 && N <= 1024) {
  bn = 64;
  wn = 2;
}
```

`DARKBLOOM_FUSED_NAX_NARROW_BN=0` restores the incumbent exactly, so fern can
run a paired A/B from one binary.

## 2. Why `wn` moves with `bn` — the correction that matters

The first version of this arm set `bn = 64` **only**, leaving `wn = 4`. That is
wrong, and the M4 gate cannot detect it because `is_nax_available()` is false
here. The geometry:

| | incumbent | `bn=64` only (**discarded**) | A2 as shipped |
|---|---|---|---|
| `bm, bn, bk` | 64, 128, 256 | 64, **64**, 256 | 64, **64**, 256 |
| `wm, wn` | 2, 4 | 2, 4 | 2, **2** |
| simdgroups / TG | 8 | 8 | **4** |
| `SM = bm/wm` | 32 | 32 | 32 |
| `SN = bn/wn` | 32 | **16** | 32 |
| per-simdgroup A+B operand rows | 32+32 | 32+16 → **+50 % traffic per output** | 32+32 |
| TGs for `N=1024` | 8 | 16 | 16 |
| total simdgroups | 512 | 1024 | **512** |
| emitted tuple | `(64,128,256,2,4)` | `(64,64,256,2,4)` | `(64,64,256,2,2)` |
| AOT-instantiated? | **yes** | **no → JIT** | **yes** |
| `tile_matmad_nax` branch | `TN % 2 == 0` | `TN == 1` | `TN % 2 == 0` |

Evidence for the AOT rows:
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/steel/gemm/kernels/steel_gemm_fused_nax.metal:23-29`
lists exactly six instantiated `(bm,bn,bk,wm,wn)` tuples. `(64,64,256,2,2)` is
the first entry; `(64,128,256,2,4)` is the third. `(64,64,256,2,4)` is absent.

Evidence for the matmad rows:
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/steel/gemm/nax.h:972-1029`
has a `TN == 1 && TM % 2 == 0` arm and a `TN % 2 == 0` arm and **no else**.
`SN = 16` gives `TN = 1`, which is a live but far less travelled branch.

So the shipped form is a **pure packing change**: identical per-simdgroup
operand traffic, identical total simdgroup count (512), identical `gemm_loop`
template, identical matmad branch, identical AOT-vs-JIT status. Only the
mapping of simdgroups onto threadgroups changes: 64 TG × 8 sg → 128 TG × 4 sg.

## 3. Bit-exactness

The accumulation order inside a simdgroup tile is unchanged, `bk` is unchanged,
and there is no split-K reduction on this path (`steel_matmul_regular_*` writes
each output element from exactly one simdgroup). Two GEMMs that differ only in
how output columns are partitioned across threadgroups produce bit-identical
results. A2 is **bit-exact by construction**, not merely "expected to be close".

This is a real distinction: it is precisely why A4 (see `READY.md` §6) was
killed.

## 4. What the arm actually reaches

Prefill dense-GEMM census, per forward pass, `M = 512` throughout (full table in
`READY.md` §4):

| count | shape | entry point | TGs (incumbent) |
|---|---|---|---|
| **78** | wk/wv `N=1024 K=2048` | `steel_gemm_fused_nax` (regular) | **64 → 1.60/core** |
| 31 | wq `N=8192 K=2048` | regular nax | 512 |
| 10 | wq `N=6144 K=2048` | regular nax | 384 |
| 1 | layer-39 `[K;V] N=2048 K=2048` | regular nax | 128 |
| 38 | router `N=256 K=2048` | **splitk** nax | 64 |
| 29 | g_proj `N=64 K=2048` | **splitk** nax | 16 |
| 10 | g_proj `N=48 K=2048` | **splitk** nax | 16 |
| 30 | wo `N=2048 K=8192` | **splitk** nax | 512 |
| 10 | wo `N=2048 K=6144` | **splitk** nax | 512 |

`N <= 1024` in `steel_matmul_regular_axpby_nax` reaches **only the 78 wk/wv
dispatches.** Router and g_proj are `N <= 1024` too, but they never enter this
function — they are routed to `steel_gemm_splitk_axpby_nax`, whose tile block is
a separate piece of code at `matmul.cpp:665-684`. Anyone reading "N ≤ 1024" and
mentally adding the 77 router/g_proj dispatches will overestimate this arm's
coverage by ~2×. Coverage is **78 dispatches, not 155.**

## 5. Honest ceiling — this arm cannot win the round

The wk/wv slice is 167.5 GFLOP, **11.1 % of the ~1.5 TFLOP prefill dense-GEMM
total.** The `steel_gemm_bf16` family already runs at **1502.8 GFLOP / 28.6 ms
= ~52.5 TFLOP/s, 87.5 % of a 60 TFLOP/s reference**
(`research/maple-tanjiro-r104c-prefill-steel-census.md:217`, restated at
`research/advisor-r104-the-receipt-is-the-instrument.md:1375` and
`research/fern-r104b-wkwv-tile-regroup.md:1026`), so the headroom inside that
slice is small by construction.

*Scope warning:* that 87.5 % is a **dense-steel-family efficiency**, not a
whole-prefill number. Do not conflate it with the 27.88 ms unattributed block
quoted in §4 of `READY.md`, which comes from a different census at a different
granularity.

* absolute ceiling if wk/wv went to 100 % efficiency: **≈ 0.93 ms ≈ +0.35 % score**
* realistic packing-only gain: **≈ 0.29 ms ≈ +0.11 % score**

Maple's deficit to the crown is ~1.4 % of real speed, ≈ 3.8 ms of prefill at
0.37 %/ms. **A2 at its theoretical ceiling covers a quarter of that; at its
realistic value, under a tenth.** It is a tidy, cheap, bit-exact probe. It is
not a round-winner and must not be described as one.

### 5.1 Hard upper bound from the M5 attribution artifact

The bound above is derived from a GFLOP share. There is a stricter and more
direct one. `research/artifacts/tanjiro-r104c/steel_ms_attribution_m4.json`,
bucket `K=2048, N=1024, n=78`, records `m5_proj_b_ms = 3.922`,
`gflop = 167.505`, `m5_tg_per_core = 1.6`.

**3.922 ms is the entire cost of every dispatch A2 can touch.** At 0.37 %/ms
that is **1.45 % of score if the family vanished completely**. Any price quoted
for A2 above 1.45 % is therefore impossible, and any price above ~0.46 % — the
31.6 % packing-probe ceiling, `1 − 1/1.4613` of 3.922 ms = 1.24 ms — requires a
mechanism stronger than the only one measured.

Reconciling the two ceilings: the packing bound (1.24 ms) is larger than the
family-efficiency bound (0.93 ms) because 87.5 % is an *average over buckets*,
and this bucket's 1.6 TG/core occupancy waste is invisible in that average. Read
the ceiling as **0.9–1.24 ms ≈ 0.35–0.46 % of score**, and the realistic value
as **0.3–0.8 ms ≈ 0.11–0.30 %**.

The 0.94 %–2.52 % band quoted for this arm in review is not reachable: 2.52 %
exceeds the family's total cost by 74 %, and 0.94 % would require capturing 65 %
of the whole family from a change that only repacks simdgroups onto
threadgroups.

## 6. Rule-83 disclosure — this is the *third* visit to this site

Anyone scheduling A2 must be told this up front.

1. **PR #293 — `DARKBLOOM_STEEL_REGULAR_SKINNY_TILE`.** Same site, same
   `bn=64, wn=2`. Introduced by `c2812d1c` (2026-08-07 14:29), merged **inert
   (default-OFF)** as PR #293 via `31f64154` (2026-08-07 18:34), and removed by
   `6ada66c9` "Adopt organizer promoted frontier c5b0a13c as research base"
   (2026-08-08 20:37). **Zero M5 receipts were ever taken.** Its status is
   *queued and never run*, not *refuted*.
2. **PR #585 / fern R104-B — `DARKBLOOM_NAX_SKINNY_TILE`.** Same site.
   Self-retracted with "failed — hypothesis refuted a priori", i.e. also
   without an M5 measurement of this geometry.
3. **A2 (this arm).** Same site again.

Against it: the campaign **replacement rule**
(`research/CURRENT_RESEARCH_STATE.md:4120-4130`) rejects narrow-`_nax`-tile
briefs, citing the measured **+0.639 ms M5 regression from PR #527 (Rule 68)**
and citing magnitude. A2 is squarely inside the class that rule names. I am not
arguing the rule is wrong; I am recording that the rule's evidence base for
*this specific geometry* is one adjacent regression and two never-measured
queue entries.

For it — and this is the only reason A2 survived at all: **fern's own M4 probe
(`research/fern-r104b-wkwv-tile-regroup.md` §7.1, job
`0c4e2817-f311-4933-ba80-b6487d6eb9dd` at `:566`) measured that at a fixed
total of 512 simdgroups, 8 sg/TG costs 1.4613× what 4 sg/TG costs** — `:575`
reads `| 8 | 64 | 256 | 762.2 | 1.4613 |` against 521.6 µs for 4 sg/TG. Fern's
§7.2 causal control shows this is a pure packing/occupancy-quantization effect,
and that 512 total simdgroups sits in **the worst band fern observed**. A2 moves
exactly that variable — 8 sg/TG → 4 sg/TG at fixed total 512 — on a dispatch
family sitting at 64 TG = 1.60 TG/core, i.e. deep in the quantization-sensitive
regime.

**Fern explicitly refuses to extrapolate the band location from M4 to M5, and I
am not extrapolating it either.** M4 Pro reports GPU generation 16 and never
selects `_nax`, so fern §7.1 measures the *mechanism*, not this kernel. The
correct reading is: a real, measured, causally-isolated packing effect of the
right sign and a large magnitude — on the wrong machine and the wrong kernel
family.

**Recommendation to fern: do not spend a standalone M5 slot on A2.** If a
wk/wv-family slot is ever scheduled for another reason, A2 is the cheapest
rider available — one env var, one binary, bit-exact, AOT-instantiated.

## 7. Correction to this document's earlier `M >= 64` justification

The previous version justified the `M >= 64` guard by claiming decode wk/wv runs
at `M = 8` through the same regular fused-NAX entry, so an unguarded arm would
retile a decode GEMM carrying 75 % of the score.

**That justification is wrong.** `Matmul::eval_gpu` short-circuits at
`matmul.cpp:1269-1270`:

```cpp
if (std::min(M, N) == 1) {
  return gemv(...);
}
```

Teacher-forced decode is 128 **one-token** steps, so `M = 1` and every dense
projection leaves through `gemv` before any steel tile is chosen. Decode reaches
**zero** dense steel GEMMs, which also matches fern's independent finding.

The guard is therefore **free rather than load-bearing**. I kept it: it costs
nothing, it mirrors the existing prefill gate at `quantized.cpp:1393-1397`, and
it keeps the arm honest if the decode path is ever batched. It must not be
presented as the thing that makes the arm safe.

## 8. Local gate

See `GATES.md` §A2. The gate is green and proves compilation, link, harness and
golden health, and non-perturbation of the non-NAX path. `is_nax_available()` is
false on this host, so **it proves nothing about `_nax` numerics or timing.**
The discarded `bn=64`-only form gated green here too — that is the clearest
statement of what this gate is worth for this arm.

## 9. Reproduce

A2 is the branch head at rev3, so there is nothing to apply — checking out the
branch is the whole procedure:

```bash
git --no-pager diff --numstat 30904ecbf180aa05d7ddf5cc957e83155fbfc6f4 HEAD \
    -- Sources Vendor benchmark.json Package.swift
#   expect exactly: 17  0  Vendor/.../metal/matmul.cpp
```

Paired A/B from one binary: `DARKBLOOM_FUSED_NAX_NARROW_BN=1` (default) vs `=0`.
