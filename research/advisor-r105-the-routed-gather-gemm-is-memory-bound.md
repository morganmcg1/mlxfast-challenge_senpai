# Round 105 — The routed gather-GEMM is memory-bound, and most of its lever family is priced at zero

**Advisor note, 2026-08-10. Written BEFORE any round-105 assignment was issued.**

This note exists because §14.15 of the round-104 flagship
(`research/advisor-r104-the-receipt-is-the-instrument.md:1520-1523`) proposed
"a round-105 census" of the routed gather-GEMM on the strength of two numbers:
*48.28 % of the prefill wall* and *67 % of peak*. Rule 83 says: before assigning
a mechanism, read what has already been measured on it. I did that. **The census
proposal is withdrawn, and so is most of the lever family it would have fed.**

Everything below is either (a) re-derived by me from first principles in
`research/advisor_r105_gather_roofline.py`, or (b) quoted with a file:line from
an existing artifact. Where the two disagree I say so.

---

## 1. What the object is

38 layers × 2 `MLX.gatherQuantizedMM` calls = **76 routed dispatches** per
512-token prefill. Not 40 and not 39:

* layer 0 is dense (`Sources/MLXFastModel/LagunaConfig.swift:61-67`);
* the last sparse layer runs last-token-only
  (`LagunaRuntimeModel.swift:11684-11686` → `callLastPrefillRow` `:11257`),
  so at M = 1 it takes the GEMV path, not the NAX gather path
  (`tanjiro-nax-kloop-pipeline.md:99-115` §A.3).

⚠ **Correction to inherit:** three artifacts still say 39 —
`research/h5-per-expert-fused-ffn-closure.md:27-29`,
`research/artifacts/README-route-histogram.md:24-25,:31`,
`research/lpt_expert_queue_sim.py:48`.

Host → device chain, verified this round:

```
MLX.gatherQuantizedMM   Vendor/mlx-swift/Source/MLX/Ops.swift:1468  (C call :1482-1487)
  -> GatherQMM::eval_gpu             backend/metal/quantized.cpp:1850
     sorted_rhs gate                 :1874-1879   (M==1 && B>=16 && right_sorted_ && B/E>=4)
                                                  true at prefill (B=4096,E=256); false at decode (B=8)
  -> gather_qmm_rhs(...)             :1892-1910
  -> NAX fork                        :1643-1646  -> gather_qmm_rhs_nax  :1323
  -> kernel fp_gather_qmm_rhs_expert_nax   kernels/fp_quantized_nax.h:1690
```

Ranked kernel name string (built at `quantized.cpp:1454-1470`, selected
`:1560-1596`):

```
nvfp4_gather_qmm_rhs_expert_static_nax_nt_bfloat16_t_gs_16_b_4
  _bm_64_bn_64_bk_64_wm_4_wn_1_k_<K>_n_<N>_eg_256_ws_1_wl_1_ps_<1|2>
```

Dispatch (`:1599-1624`): `group_dims(32, wn, wm)` = **(32,1,4) = 128 threads =
4 simdgroups/TG**; `grid_dims` = **gate/up (16,256,1) = 4096 TGs**, **down
(32,256,1) = 8192 TGs**.

Two facts that kill whole arms before they are written:

* **`run_skip_pct` is `(void)`'d at `fp_quantized_nax.h:1703`** — the
  `DARKBLOOM_PREFILL_GATHER_RUNSKIP` gate has **no effect** on the M5 path.
* **`darkbloom_gather_xmajor_ct()` hard-returns 0** (`quantized.cpp:1290`) — the
  x-major arm is unreachable dead code.
* Function constants **200–207** are bound only when `!expert_aligned`
  (`:1527-1539`) and therefore **never reach the ranked kernel**.
* **JIT is the effective path.** `Package.swift:25` compiles `jit_kernels.cpp`;
  `:283-284` exclude `nojit_kernels.cpp` and the whole `backend/metal/kernels`
  directory. `get_qmm_nax_kernel` (`jit_kernels.cpp:1189`) concatenates
  `metal::fp_quantized_nax()` — i.e. the **generated twin**
  `Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized_nax.cpp`
  (`fp_gather_qmm_rhs_expert_nax` at `:1832`). **An edit to the `.h` alone does
  nothing.** Verify every edit with `python3 research/nax_twin_check.py` and
  rebuild the metallib with `./setup.sh`.

---

## 2. The two published numbers are both wrong as stated

### 2.1 "48.28 % of the prefill wall"

True, but of the **M4 non-`_nax`** wall (`260.907 ms` of `540.394 ms`,
`maple-tanjiro-r104c-prefill-steel-census.md` §6A). On M4 the routed GEMM runs a
**different kernel** — `bm=16, bn=32, bk=32, wm=1, wn=2`, 64 threads/TG, **no
fused SwiGLU** (`quantized.cpp:1682-1683`, dispatch `:1744-1745`, kernel
`fp_quantized.h:1994`). The only bridge to M5 is the 6.03× transfer factor of
`nonmoe-prefill-census.md:357-372`, which is a scalar, not an attribution.

### 2.2 "67 % of peak"

This is **not** a FLOP-peak fraction. It is `408.4 / 610` — an **achieved
bandwidth fraction** restated in FLOP units against a derived "34.7 TFLOP/s
peak". `tanjiro-pr-gather-regime-discriminator.md:43-84` says so itself: the
roofline identity there is **circular by construction**.

It is also computed from PR #34's marginal estimator
(`dS_1 = 141.1262 − 97.8643 = 43.2619 ms`) — the same estimator tanjiro
**withdrew in his own #586 §3.3** for producing 117 % of ceiling on attention
(rule 76). Treat 43.262 ms as *contaminated but directionally usable*, never as
a measurement.

---

## 3. The corrected roofline (`research/advisor_r105_gather_roofline.py`)

Constants verified from `Sources/MLXFastModel/LagunaConfig.swift` and the host
cert: hidden 2048, moeIntermediate 512, experts 256, top-k 8, tokens 512,
38 routed layers, nvfp4 4-bit with `group_size = 16` and a uint8 scale per group
⇒ **0.5625 B/element**. Shapes: gate/up **M=4096 N=1024 K=2048**; down
**M=4096 N=2048 K=512**.

```
non-empty (layer,expert) : 7757 / 9728 = 79.74 %
MMA rows  useful 155648  issued 226560   inflation 1.4556x   (both GEMMs: 311296 / 453120)
chunks_bm64 8379 (CSV) == ceil(rows/64) recomputed 8379   MATCH
weight re-read factor    : 1.0802x
useful FLOP  979.25 GFLOP     issued FLOP  1425.39 GFLOP
weights touched per chunk: 14.826 GB     (all-dense would be 17.213 GB = 86.1 % occupancy)
AI  useful 60.22   issued 87.66   vs M5 balance 98.36 FLOP/byte (60 TFLOP/s / 610 GB/s)
VERDICT: MEMORY-BOUND — issued AI is 1.12x below machine balance
DRAM floor  weights only            14.826 GB -> 24.306 ms
            + ideal-reuse acts      16.261 GB -> 26.657 ms
            + zero-reuse acts       30.765 GB -> 50.434 ms
MMA-issue floor 23.757 ms   (useful-only 16.321 ms)
vs 43.262 ms: 375.9 GB/s = 61.6 % ; useful 22.64 TFLOP/s = 37.7 % ; issued 32.95 = 54.9 %
```

**Independent confirmation of the byte count.** `tanjiro-nax-kloop-pipeline.md:82-97`
§A.2 counts `load_unsafe` calls directly out of the kernel: gate/up 16 column
tiles × 32 k-iterations = 512 per chunk; down 32 × 8 = 256; **768 × 2304 B =
1,769,472 B per chunk; × 8379 chunks = 14,826,405,888 B**. That is my
14.826 GB **to the byte**, from a completely different derivation. The carried
**17.66641 GB** figure (#170 `:35-38`) overstates real staged traffic by 16.1 %
and should not be quoted again.

### 3.1 ⭐ The consequence that matters: the MMA-row-inflation family is priced at ~zero

`kFragRows = 16` (`Vendor/.../kernels/steel/gemm/nax.h:27-28,:540,:547`) forces
every expert's row count up to a multiple of 16, giving the well-documented
**1.4556× row inflation** (meridian, `research/GATHER_GEMM_REGIME_DESIGN.md`).
Meridian's item 15 — *routing-aware two-régime expert dispatch* — is recorded as
"**the only remaining route below 1.456× MMA rows**"
(`RESEARCH_STATE_ARCHIVE_through-round-21.md:6607-6610`).

It cannot pay:

> **issued MMA floor 23.757 ms < cache-immune weight-byte floor 24.306 ms.**

Removing row inflation *entirely* takes the MMA floor to 16.321 ms, but at least
24.3 GB-equivalent-ms of weight bytes must still cross DRAM, and those bytes do
not shrink when rows do. **Every arm whose mechanism is "issue fewer MMA rows"
— two-régime dispatch, sub-16 SM, banding, tile-quantization padding — is worth
≈0 ms and must not consume a receipt.** This is now a hard negative.

### 3.2 What is actually compressible

Weight traffic is irreducible: every non-empty expert's full matrix must be
read, and the re-read factor is only **1.0802×**. Expert *pruning* buys nothing
either — 79.74 % occupancy means the actual 14.826 GB is already **86.1 %** of
the all-dense 17.213 GB, and the archive already says "**Do not re-propose
expert-traffic pruning**" (`RESEARCH_ARCHIVE_through-round-91.md:5524`,
`:5102-5115`).

The **only compressible stream is the activation (A-operand) re-read across
`grid.x`**: x rows are re-read **16×** for gate/up and **32×** for down, i.e.
between 1.434 GB (ideal reuse) and 15.938 GB (zero reuse). The measured
43.262 ms sits **between** the two floors (26.657 and 50.434 ms) — so reuse is
**partial**, and *how* partial is exactly the size of the prize.

---

## 4. 🔴 The tension I must state, not hide

My roofline says *memory-bound*. #215 §6.8 (`tanjiro-nax-kloop-pipeline.md:980-995`)
says the opposite at the margin: arms S2 and S3 differ by **+8.108 ms for
+5.89 GB ⇒ a marginal rate of ≈726 GB/s**, against an average of ≈343 GB/s.
A marginal rate *above* the 610 GB/s DRAM peak means those marginal bytes were
**not** coming from DRAM — and #215 says so explicitly at `:987`:

> *"Plausibly a chunk of the 14.83 GB requested traffic is A-fragment re-reads
> absorbed by SLC."*

Both statements can be true simultaneously **iff** the *average* rate is set
upstream of DRAM — at load **issue** and pipe occupancy — while the *floor* is
still set by DRAM. That is the reconciliation, and it has a sharp corollary:

> **If SLC is already absorbing the A-operand re-reads, then the one compressible
> stream in §3.2 is already compressed, and the routed gather-GEMM has no
> remaining ranked lever at all.**

That is a falsifiable statement and it is the only thing worth measuring in this
family. Note also that the A-operand hoist **has already shipped** (header
comment `fp_quantized_nax.h:1863-1876`), which raises the prior that the easy
part of the reuse is done.

---

## 5. Rule-83 census: what has already been tried here

| PR | mechanism | outcome |
|---|---|---|
| #40 fern | double-buffered `Ws`; register prefetch across the back-edge | both **null** inside σ_dS = 0.2536 |
| #57 tanjiro | tgmem census + co-residency probe | 9,224 B static / 9,232 B compiled; `Ws_storage` = 99.91 %; `bounds[2]` = 8 B ⇒ **no ~1 kB saving exists** |
| #63 fern | elide row-gather via `lhs_indices` | ceiling **+0.4636 %** vs a 0.61 % bar ⇒ **killed at design gate** |
| #138 tanjiro | BK 64→128 down-only | inconclusive, no receipt; BK=128 needs 34,816 B tgmem |
| #142 frieren | LPT expert→TG scheduling | "LPT reordering contributes ≈0 ms" ⇒ **family closed** |
| #157 tanjiro | graph-level co-residency | overlap fraction **0.0120** ⇒ dead |
| #170 tanjiro | 4-arm régime discriminator, 4 M5 receipts | H1/H0 eliminated, H3 minor, **H2 (load/staging) identified** |
| #215 tanjiro | pipeline the BK=64 k-loop | **+0.684 ms (+1.52σ)** against a −7.6σ prediction ⇒ **family closure** |
| #244 | scale-load amortization 3 → 1.25 loads/thread/k-iter | **null even though issue count fell** |
| H5 (desk) | per-expert fused FFN | 74,752 B needed vs Metal's 32 kB = **2.28× over** ⇒ closed |

**The operative pre-filter** (`tanjiro-nax-kloop-pipeline.md:1100-1104`):

> *"Count the device-load and threadgroup-store **issues** per thread per
> k-iteration, before and after. If the count does not go down, §6.8 predicts a
> null and the proposal should not consume a receipt."*

…and #244 proves that test is **necessary but not sufficient**.

Additional pre-answered arms (do not re-propose):

* **`Ws` threadgroup-read swizzle / bank conflicts** — the `+8`-element pad **is**
  the swizzle. Pitch 72 × 2 B = 144 B = 36 words; 36 ≡ 4 (mod 32) ⇒ exactly
  2 words/bank = the hard 2-cycle floor
  (`RESEARCH_ARCHIVE_through-round-91.md:5193-5240` §4.28A).
* **`store_ok`/`load_ok` ALU hoist as a receipt** — ceiling ≈1.0–1.4 ms; do the
  offline IR diff instead (§4.28B).
* Consolidated "do not assign" list: `RESEARCH_ARCHIVE_through-round-91.md:5359-5365`.

### 5.1 🔴 Doctrine correction carried forward from #138

**PR #57's occupancy claim was measured on a broken probe** — it bound a
*dynamic* threadgroup pointer, so `setThreadgroupMemoryLength` never bound
anything. Repaired (`RESEARCH_ARCHIVE_through-round-91.md:6486-6510`): at
**128 threads/TG on M4, tgmem of 1 kB / 9,232 B / 17,424 B / 32,768 B all give
480 TGs = 24.0 per core**; the 32-threads/TG control *does* bind (95.0 → 63.0).

⇒ "threadgroup memory is not the occupancy currency; 96 simdgroups/core is the
ceiling" is **true at ≥128 threads/TG and false at 32 threads/TG. Cite it
scoped.**

This substantially **pre-answers meridian's D2** occupancy audit
(`GATHER_GEMM_REGIME_DESIGN.md`): deliverable (1) is answered (9,232 B measured),
(2) is answered (`maxTotalThreadsPerThreadgroup` 1024, 7 resident TGs), (3) is
answered (tgmem does not bind at 128 threads/TG on M4) and (4) is answered
(`bounds[2]` = 8 B, no prize). **Do not assign D2 as written.**

---

## 6. What is genuinely virgin

1. **⭐ L7 / lever 2 / Q10 — A-fragment N-tile reuse.** Recorded as
   "⭐ **NOW THE TOP SURVIVING `_nax` LEVER**"
   (`RESEARCH_ARCHIVE_through-round-91.md:1822`) and "**the only surviving `_nax`
   prefill lever**" (`:5357`); shelved at effective weight 0.365
   (`CURRENT_RESEARCH_STATE.md:1911,:2466-2481`); **never assigned** (no branch
   exists). Terms: at N = 1024 with BN = 64 each simdgroup re-reads its sorted-x
   fragments ≈16×; processing **two N-tiles per A load halves that**;
   accumulators double and `Ws`/B-fragments double. Must beat **≈1.35 ms** to
   clear 3σ. **Structurally M5-receipt-only.** Risk: §4 — if SLC already absorbs
   the re-reads, it is a null.
2. **Per-shape millisecond attribution of the 76 routed dispatches has never been
   done** — only bytes. The `SPLIT=1` instrument is reusable but lives in
   `device.cpp`/`device.h`, which are **not** in `editablePaths` ⇒ research-only.
3. **#170 §9's `tg_load` blind spot was never priced**
   (`tanjiro-pr-gather-regime-discriminator.md:2036-2261`), and the
   "mean rows/expert = 16.00 vs SM = 16 ⇒ only 1 of 4 simdgroups active on the
   average expert" observation (`h5-per-expert-fused-ffn-closure.md:104-108`) was
   never converted into a measurement.

Meridian's §2.1 generalisation bounds all three: the k-loop has **two
unconditional barriers per iteration**, so intra-TG data/math overlap is
impossible by construction and all overlap comes from co-resident TGs. Therefore

> **any arm that increases per-threadgroup resource use to buy overlap is
> fighting itself; only arms that reduce it can move the number.**

L7 **increases** registers and `Ws`. That is the strongest single reason it may
fail, and it must be stated in the prereg.

---

## 7. Corrections to the round-104 flagship

* **§14.15 bullet 3 is struck.** "The routed gather-GEMM at 67 % of peak … the
  obvious place for a round-105 census" is replaced by §2 and §3 of this note.
  There will be no census: the bytes are already counted twice, byte-exactly.
* **§14.2's use of "67 % of peak"** must be read as an achieved-bandwidth
  fraction on a contaminated marginal estimate, not a FLOP-peak fraction.
* **§9/§10's env-gate inventory undercounts the vendored C++ surface.**
  `quantized.cpp` **alone** has 17 env-gate sites (`:506, :842, :1155, :1162,
  :1185, :1190, :1195, :1200, :1206, :1212, :1218, :1224, :1236, :1296, :1302,
  :1397, :1409, :1411, :1432, :1497`), while §9 recorded `cpp-static 6 |
  cpp-function-body 3` for the **whole repo**.
  `research/advisor_r104_gate_inventory.py` and
  `research/advisor_r104_env_gate_scope.py` need a Vendor-C++ pass before §10's
  ablation ledger can claim completeness.
* ⚠ `research/artifacts/route-histogram-prefill512-stats.json:606` has its
  `gate_up` / `down` labels **swapped**, and the table at
  `tanjiro-nax-kloop-pipeline.md:299` labelled `gate_up` actually carries
  K = 512 / N = 2048. Do not inherit either.
* **`Sources/MLXFastModel/SwitchLayers.swift` does not exist.** §12's three
  `SwitchLayers.swift` gate rows point at
  `Vendor/mlx-swift-lm/Libraries/MLXLMCommon/SwitchLayers.swift` (editable,
  556 lines, `gatherSort` at `:282`).

---

## 8. Standing prices for this family

| quantity | value |
|---|---|
| price of prefill milliseconds | **0.3781 % of `cs` per ms** (rule 84) |
| bar to the record | **+1.438 % of `cs` = 3.803 ms of prefill** |
| whole-family headroom vs the DRAM floor | 16.605 ms = +6.278 % (upper bound, unreachable) |
| MMA-row-inflation family | **≈0 ms** (§3.1) |
| expert pruning | **≈0 ms** (§3.2) |
| L7 A-fragment reuse | must beat **≈1.35 ms** for 3σ; ceiling unknown, bounded by §4 |

**Caveats on every number above:** 60 TFLOP/s is a bf16-steel reference, not a
measured nvfp4-NAX MMA rate; 43.262 ms is contaminated (§2.2); and threadgroup
linear ordering (`x + y·gridX`) puts the 16 (resp. 32) same-expert TGs
consecutively in flight, which makes L2/SLC residency **more** likely and biases
§3 toward the optimistic model.
