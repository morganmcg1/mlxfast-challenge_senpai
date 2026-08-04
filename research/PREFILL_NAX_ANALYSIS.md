# M5 prefill under the NAX blind spot: hypotheses, testability, candidates

Scope: why the official 512-token forward (S = 98.153 ms) sits at ~28.8 TFLOP/s
and ~272 GB/s, roughly half of both M5 rooflines; what can be resolved without
executing a `_nax` kernel; and concrete candidate changes. All file:line refs
verified against this tree. Statements marked **[inference]** are derived, not
read from code or receipts.

## Framing: the floor arithmetic that ranks everything

Two corrections to the naive "26.68 GB / 271.8 GB/s" picture:

1. **Real DRAM bytes are ~23.1 GB, not 26.68.** 20.3% of (layer, expert) pairs
   receive zero rows (`research/maple-fern-prefill-roofline.md` §3, raw data
   `research/prefill-512-route-histogram.txt`), and the expert kernel never
   touches those weights (empty run ⇒ the chunk loop at
   `fp_quantized_nax.h:1699-1704` never executes). That removes
   0.203 × 17.666 GB ≈ 3.6 GB. So the true DRAM floor at ~500-550 GB/s is
   **42-46 ms**, and measured S is ~2.15× that floor (≈46% of DRAM peak).
2. **The compute floor is ≤50 ms** (2830.2 GFLOP at ≥57 TFLOP/s simdgroup-MMA
   scaling; NAX units are faster, so likely well under 40 ms) **[inference]**.

Measured S ≈ DRAM floor + MMA floor. That sum-of-floors coincidence is the
signature of kernels that **alternate** memory and compute phases instead of
overlapping them. This is exactly the structure of the quantized NAX kernels
(below), and it is the organizing observation of this analysis.

Budget shares (host-independent FLOP/byte budget, `research/prefill_budget.py`;
M4 time shares from the PR#11 profile): routed experts ≈ 45-50% of S, BF16
attention projections ≈ 25-35%, attention core ≈ 5-8%, shared/dense/router
qmm ≈ 4-6%, non-GEMM glue ≈ 8-12% **[inference from M4 shares + M5 floors]**.

## (a) Ranked hypotheses

### H1 (strongest): the expert gather-GEMM serializes staging and MMA, and per-core threadgroup concurrency is too low to overlap them across threadgroups

The shipped routed path is `fp_gather_qmm_rhs_expert_static_nax_nt_..._bm_64_
bn_64_bk_64_wm_4_wn_1_..._eg_256` (variant 5 default at `quantized.cpp:1470-1479`;
static shapes default-on at `quantized.cpp:1684-1691`; egroups=256 at
`quantized.cpp:1380-1390`; grid = (N/64, 256) at `quantized.cpp:1915-1924`).

Kernel structure per (expert, 64-row chunk, k-iteration)
(`fp_quantized_nax.h:1727-1795`): hoisted A-fragment device loads →
`threadgroup_barrier` → all 128 threads cooperatively dequantize a full 64×64
weight tile into 9.2 KB of threadgroup memory (`Ws_storage`,
`fp_quantized_nax.h:1616-1621`; loader `QuantizedBlockLoader::stage()` at
:270-300) → second barrier → active simdgroups run the MMA chain from Ws
(:1774-1791). There is **no double buffering**: the next iteration's staging
waits behind this iteration's MMA (WAR via the next barrier). Within a
threadgroup, DRAM sits idle during MMA and the NAX unit sits idle during
staging. Cross-TG overlap is the only latency hiding, and it is capped by
threadgroup-memory occupancy (9.2 KB/TG) and 128 threads/TG.

Direct evidence this is the binding constraint, from the tree's own receipts:

- `quantized.cpp:1367-1377`: spreading the 256 experts over more threadgroups
  (egroups 64 → 128 → 256), a **pure parallelism change with identical work
  and identical arithmetic**, measured real M5 prefill gains at each step —
  "the hardware scheduler overlaps per-expert staging drains and MMA phases
  instead of serializing expert slots inside one threadgroup".
- `quantized.cpp:1445-1450`: variant 4's win was attributed to "doubles the
  parallelism available to hide staging latency, **which is 39.5% of
  prefill**" — the staging share is on the record.
- The sum-of-floors match above.

Under the measured routing skew the staging:MMA imbalance is worse than any
uniform model: staging work is one full 64×64×K dequant per **non-empty expert**
per column tile (∝ Σ_e 1{r_e>0}), while useful MMA rows per chunk average
27.1 of 64 (`maple-fern-prefill-roofline.md` §3). The median expert (7 rows)
activates 1 of 4 simdgroups (`sg_active`, :1706-1710) for the entire 32-iteration
K loop of gate/up while all 128 threads stage.

### H2: the skew tax itself — 16-row MMA granularity and full-tile staging — is real but mostly a hardware floor

Issued/useful MMA rows = 1.46× at SM=16 (31.3% padding). SM cannot go below 16:
`TM = SM/16` (`fp_quantized_nax.h:1639-1642`), NAX fragments are hard 16×16
(`kFragRows = 16`, `steel/gemm/nax.h:27-28`), and `tile_matmad_nax` has no
branch for TM=0 or odd TN>1 — it silently compiles to zero MMAs
(`steel/gemm/nax.h:994-1031`). The DRAM side of the skew tax is irreducible
anyway: any expert with ≥1 row must have its full weight bank read once — that
is the 14.08 GB. What is addressable is not the bytes but the **overlap** (H1)
and the **20.3% empty threadgroups** (early-exit after one binary search,
:1671-1697); the latter costs <0.1% of S **[inference: ~2.5k empty TGs × sub-µs]**
and is not worth a slot.

### H3: the BF16 attention-projection family is fragmented across dispatch shapes the M5 heuristics were never tuned for

Prefill Q/K/V/O (+ per-head gate and routers) run as BF16 GEMMs — the INT8
banks are decode-only (`B == 1, L == 1` guard, `LagunaRuntimeModel.swift:5498-5516`),
and `DARKBLOOM_FUSED_QKV` ships OFF because of an **M4** measurement
(`LagunaRuntimeModel.swift:108-114`). Consequences on M5, all from
`matmul.cpp` dispatch logic:

- q (512×8192/6144×2048) runs `steel_gemm_fused_nax` with the "Temp routing
  for larger devices" tiles bm=64, bn=128, bk=256, wm=2, wn=4
  (`matmul.cpp:228-238` — the comment itself says "Temp").
- k and v (N=1024) each dispatch only **64 threadgroups** (grid 8×8) — ~1.6
  TGs per core on a 40-core GPU, twice per layer, 80 dispatches total.
- o_proj (K=8192/6144), per-head g_proj (N=48/64) and routers (N=256) all
  fall into the NAX split-K branch (`matmul.cpp:987-991`) and pay a **float32
  round trip**: `C_split` fp32 intermediate (`matmul.cpp:734-737`) plus a
  separate reduce dispatch — ≈672 MB (o) + 41 MB (router) + 10 MB (g_proj)
  ≈ **0.72 GB, ~3% of real traffic**, plus ~120 extra dispatches, plus g_proj's
  grid of **16 threadgroups**.
- The NAX steel GEMM itself streams fragments straight from device memory with
  no threadgroup staging and `mem_none` barriers (`gemm_nax.h:52-119`) — its
  efficiency is cache-behavior-dependent and unmeasurable off-M5, but its
  structure is sound; the fragmentation and fp32 round trips above are the
  concrete, addressable losses.

### H4: non-GEMM glue is a growing Amdahl term and the only locally measurable one

M4 profile: `laguna_*` + elementwise + rms + router + sort/scatter + moe_tail
≈ 18 ms. These kernels are host-generation-independent (the PR#11 finding: only
5.8% of M4 prefill time is, and this is most of it). On M5 they shrink only by
the generic HW factor (~1.5-2×), so ≈ 9-12 ms ≈ **9-12% of S** while the NAX
GEMMs around them got ~5× faster **[inference]**. The team has already harvested
much of this (tournament router replacing full argsort,
`LagunaRuntimeModel.swift:8744-8846`; fused residual+RMS; prefill async ladder),
so remaining headroom is real but bounded.

### H5 (weak / dead): scale-buffer traffic, attention core, cold-start

- Group-16 scale reads look ugly (1-byte loads at 128 B row stride,
  `fp_quantized_nax.h:255-258`) but the tile's scale footprint (8 KB per
  expert-column-tile) is fully consumed across the K loop, so caches absorb
  it; it is a latency nit, not a DRAM cost **[inference]**.
- The NAX attention kernel already has per-simdgroup causal K-block elision,
  register Q-hoist, direct device loads, `mem_none` barriers
  (`steel_attention_nax.h:250-270, 318-338, 587-596`) and is ~5-8% of S; its
  dispatch constants (bq=64, bk=32, wm=4, wn=1) live in
  `scaled_dot_product_attention.cpp:31-36`, which is **not editable**.
- Cold first-touch inside the timed window is a dead hypothesis: the ≥96 GiB
  M5 wires ~31.4 GiB before hello, and back-to-back forwards show the first
  is fastest (`research/maple-fern-pr19-first-touch.md`).

## (b) What can be tested or bounded without executing a `_nax` kernel

1. **Histogram arithmetic (free, exact).** Routing is host-independent. It
   already killed BM=128 and priced SM=16 vs 8. It equally prices: BN=32
   (unchanged DRAM bytes, 2× resident TGs, 2× staging instances of half size),
   zero-row cost (<0.1%), and chunk re-staging (Σceil(r/64) = 1.08× — small).
2. **Static analysis of the generated JIT source.** The M5-only kernels are
   assembled from `mlx-generated/fp_quantized_nax.cpp` + header; any candidate
   must keep the twin consistent (`AGENTS.md`). `xcrun metal` can compile the
   assembled MSL offline to catch template breakage — including the silent
   no-MMA modes: adding `static_assert((TN == 1 && TM % 2 == 0) || (TN % 2 == 0))`
   inside `tile_matmad_nax` (`nax.h:994-1031`) converts silent-zero kernels
   into compile errors for free (all current instantiations pass: TN=4 TM=1
   expert; TN=2 TM=2 qmm; TN=1 paths). Register-pressure/occupancy cannot be
   read statically with confidence — say so rather than guess.
3. **M4 structural analogue.** The non-NAX twin `fp_quantized.h` gather kernel
   shares the loader class, the stage→barrier→MMA phase structure, and the
   same skewed routing. A mechanism like k-loop double buffering can be
   implemented in both twins and ABBA'd on M4 for the non-NAX kernel. This
   validates correctness machinery and the imbalance model, but per AGENTS.md
   the magnitude does not transfer; treat as go/no-go on mechanism sanity only.
4. **Bit-exactness by construction, verified locally where executable.** The
   winning pattern in this tree is changes that are provably
   arithmetic-neutral ("regroup rows/columns across simdgroups/threadgroups",
   `quantized.cpp:1422-1438`) or that emulate multi-pass rounding exactly
   (`qmm_t_splitk_fused`, `quantized.cpp:849-861`). Local 1025-step gates and
   upstream equivalence cover the Swift side and non-NAX twins; the NAX kernel
   itself gets numeric coverage only from the official gates, so every NAX
   change should carry a process-constant env kill-switch (the
   `DARKBLOOM_STAGE_BM128=4` precedent).
5. **Differential official receipts.** Candidate-absolute S has σ ≈ 0.50%
   (three compile-identical receipts,
   `research/tanjiro-m5-instrument-calibration.md`), and the team already
   resolved a mechanism family this way (204.90 → 201.64 → 201.42 → 198.00
   µs/token, `quantized.cpp:1470-1479`). A 3-receipt family resolves ~1.5%;
   every candidate below predicts ≥1.5% or is locally falsifiable. Mind the
   calibration band (prefill ≤1.053 per accepted run, `TASK.md:43-44`): a >5%
   winner must be split into independently-correct chunks — the static-shape
   split (separate (K=2048,N=1024) and (K=512,N=2048) instantiations,
   `quantized.cpp:1686-1691`) provides a natural two-chunk path.

## (c) Candidate changes

**C1. Double-buffered weight staging (k-loop software pipeline) in
`fp_gather_qmm_rhs_expert_nax`.**
Mechanism: 2× `Ws` (9.2→18.4 KB), stage tile k+1 while MMA consumes tile k; one
barrier per iteration instead of two; MMA chain, operand values, and
accumulation order untouched.
Files: `fp_quantized_nax.h:1616-1621, 1727-1795` + the `mlx-generated/
fp_quantized_nax.cpp` twin (JIT assembly in `jit_kernels.cpp`).
Predicted: staging is on record at 39.5% of prefill; hiding half of the
expert-kernel staging behind MMA ⇒ **2-6% of S** (expect ~3%).
Risk: numerics none (same values, same order). Perf risk: doubling TG memory
may halve resident TGs/core and *reduce* cross-TG overlap — the exact opposite
effect; unknowable off-M5 (dynamic caching).
Falsify: static compile check + M4 twin analogue, then one receipt
(kill-switch env for the A arm). Ship gate/up and down instantiations as
separate chunks if the win is large.

**C2. BN=64→32 expert-kernel variant (new `DARKBLOOM_STAGE_BM128`-style
variant, bm=64, bn=32, wm=4, wn=1).**
Mechanism: halves Ws to 4.6 KB and doubles grid.x (32/64 column tiles), so
~2× threadgroups fit per core — more resident staging streams to overlap MMA
phases, the same lever the egroups 64→128→256 receipts already proved pays on
M5. DRAM bytes unchanged (column split; K chain per output element identical ⇒
bit-exact, same class as the proven WN move).
Files: `quantized.cpp:1637-1663` (tile switch + `expert_aligned` gate + grid),
kernel template already generic in BN; Swift gate at
`LagunaRuntimeModel.swift:231-233` unaffected when the C++ default changes.
Predicted: **1.5-4% of S**. Risk: more per-expert binary searches and
scale-line touches (cache-absorbed); TN drops 4→2, shortening the MMA chain
per k-step (scheduling, not arithmetic).
Falsify: one receipt. Composes oppositely to C1 on TG memory — measure
separately, never bundled.

**C3. Prefill row-concat QKV (q+k+v only, BF16).**
Mechanism: one `[Wq;Wk;Wv]` bank per layer for multi-token forwards ⇒ one
640-TG `steel_gemm_fused_nax` dispatch replaces one 512-TG + two 64-TG
dispatches; row-concatenation of same-dtype projections over the same input is
the tree's documented bit-exact class (`LagunaRuntimeModel.swift:101-106`)
because each output row keeps its own K loop in the same kernel/tiling
(N=10240 and 8192 both keep align_N true at bn=128). Exclude g_proj (its rows
currently take the split-K path; folding them would change accumulation
grouping).
Files: `LagunaRuntimeModel.swift` attention prefill path (~:5476 onward, bank
construction mirroring the decode `_fusedQKVWeight`).
Predicted: k/v are 6.1% of forward FLOPs at ~1.6 TGs/core fill; **1-3% of S**.
Risk: numerics none; perf risk that output slicing forces an extra
contiguous copy (~8.4 MB/layer) — implement so the head-reshape consumes the
strided slice. Note the OFF default was justified by an M4 measurement on
non-NAX kernels; that evidence does not transfer.
Falsify: one receipt; local M4 run only to confirm token-exactness.

**C4. Bit-exact fused split-K for the NAX steel path (o_proj, g_proj,
router).**
Mechanism: single dispatch walks both K partitions with separate fp32
accumulators and sums them in the reduce's exact order before the single bf16
store — the `qmm_t_splitk_fused` recipe (`quantized.cpp:849-893`) ported to
`steel_gemm_splitk_nax`. Removes ~0.72 GB of fp32 intermediate traffic (~3% of
real bytes) and ~80 dispatches.
Files: `matmul.cpp:689-810` + `steel_gemm_splitk_nax.h` + generated twin.
Predicted: **1.5-3% of S**. Risk: numerics none *by construction* (order
emulated exactly); moderate implementation complexity; register pressure from
dual accumulators (bm64/bn64/wm2/wn2 ⇒ 2×32 floats/lane) needs the static
compile check.
Falsify: implement the same emulation for the non-NAX `steel_gemm_splitk` and
bit-compare + time on M4 (that twin IS executable locally), then one receipt.

**C5. Glue-pass reduction, measured entirely on M4.**
Mechanism: per-dispatch profile (`research/prefill_probe.py`) of the
host-independent ~18 ms M4 glue (sort/scatter chain, moe_tail, residual/norm
elementwise, router tail), then cut the top item — e.g. replacing the generic
merge-sort of 4096 8-bit expert ids with a counting-sort custom kernel, or
fusing scatter+moe_tail.
Predicted: 30% of glue ⇒ ~3 ms M4, scaling to ~1-2% of M5 S **[inference]**.
Risk: low; these kernels run identically on both hosts, so local ABBA is a
valid instrument end-to-end — the only candidate family with full local
falsifiability.

**Ordering.** C1 and C2 attack H1, the largest block, and are cheap to build;
C2 is the safer first receipt (bit-exact, no occupancy downside), C1 second
(mechanism confirmed by egroups receipts but TG-mem direction uncertain). C3
and C4 attack H3 and are independent of the expert kernel. C5 runs in parallel
locally at zero receipt cost. Static-only validation before any receipt: C2,
C3 (plus local token-exactness), C4-twin; C1 needs one receipt to resolve its
occupancy ambiguity.
