# H5 "per-expert fused FFN" — closed on paper, plus the lead it uncovered

**Date:** 2026-08-06 · **Author:** advisor (meridian) · **Cost:** zero GPU, zero receipts

H5 was held for round 23 with an estimated **+0.2…+3.6%** and an instruction to
"kill on paper first via the SLC-absorption bound." Two delegated agents (one
code-reading, one literature) did that. The verdict is stronger than expected:
**H5 is partly already shipped and partly geometrically infeasible.** It is
closed as a family.

The investigation did surface a genuinely new, *small*, *proven-mechanism* lead
that replaces it — see §5.

---

## 1. Model geometry (measured, not assumed)

| quantity | value | source |
| --- | --- | --- |
| hidden size | 2048 | `fixtures/poolside_laguna_xs_2_1_nvfp4_config.json:61` |
| MoE expert ffn dim | 512 | `…config.json:199-201` |
| layers | **40, of which 39 sparse** (layer 0 is dense, intermediate 8192) | `…config.json:153`, `LagunaConfig.swift:17,19` |
| experts | 256, **top-k 8** | `…config.json:199-201`, `LagunaConfig.swift:30-33` |
| shared expert | 2048 → 512 → 2048 | `LagunaConfig.swift:298-300` |
| activation dtype | **bf16** | `…config.json:233` |

Note the sparse-layer count is **39**, not 38. The route histogram in
`research/artifacts/route-histogram-prefill512.csv` covers 38 sparse layers
because layer 0 is dense; the 39th is accounted separately.

---

## 2. gate_up → SwiGLU is **already fused, register-locally**

This is the part of H5 that is already shipped, which is why the estimate was
inflated.

- `Vendor/mlx-swift/.../fp_quantized_nax.h:1797-1798` —
  `fuse_swiglu = (kernel_N == 1024 && kernel_K == 2048)`. That predicate is
  **true** for the routed expert geometry (gate+up concatenated = 2×512 = 1024
  out, 2048 in).
- Register-local arm at `fp_quantized_nax.h:1800-1836`; `kSwigluRegLocal` is
  **true** at the shipped `WN=1 / BN=64 / SM=16` (`fp_quantized_nax.h:1656-1657`).
- Enabled by default: `quantized.cpp:1581-1584`, `jit_kernels.cpp:1205`.
- Decode twins are fused too: `lagunaRoutedSwiGLUQMV`,
  `…QMVPacked`, `…QMVPackedTop8`
  (`LagunaRuntimeModel.swift:6993-7086, 7235-7336, 7655`); shared expert at
  `:6714-6790`.

So the gate/up product never leaves registers. There is no round trip to fuse
away there.

---

## 3. The only remaining boundary is SwiGLU → down, and it is real

| call site | file:line |
| --- | --- |
| prefill | `LagunaRuntimeModel.swift:9829` — `downProj(activated, …)` |
| decode | `LagunaRuntimeModel.swift:7796-7806` — `lagunaRoutedDownReduce` |

The activated tensor is a genuine `MLXArray` round trip through memory.

**Traffic:**

| phase | per sparse layer | per pass |
| --- | --- | --- |
| prefill (512 tok) | 4.00 MiB written + 4.00 MiB read = **8.00 MiB** | **312 MiB** round trip |
| + unfused shared expert | 1.5 MiB/layer | +58.5 MiB |
| + dense layer 0 | — | +24 MiB |
| decode (1 tok) | 367 KiB written | **~0.6 MiB/step** |

Decode is immediately uninteresting: 0.6 MiB/step against a 5.5296 MB/step
`gate_sp` unique-DRAM figure is noise. **H5 was only ever a prefill arm.**

---

## 4. Why the fusion is geometrically infeasible at the shipped tile

`down` consumes **all 512 activated columns** of a row. A threadgroup at the
shipped geometry produces **32**. To fuse, a threadgroup must hold the whole
activated tile:

```
activated tile  64 rows × 512 cols × 2 B (bf16) = 65,536 B
weight staging  Ws 64 × 72 × 2 B               =  9,216 B
                                                 -------
                                                  74,752 B
```

against Metal's **32 KB threadgroup limit** — **2.28×over**. Current usage is
only 9,224 B, so this is not a tuning problem; it is a factor of two and a bit.
The register alternative needs 512 f32 per thread against a practical ceiling
around 128.

Shipped tile geometry: `bm=64, bn=64, bk=64, wm=4, wn=1`,
`DARKBLOOM_STAGE_BM128=5` (`quantized.cpp:1468-1479, 1633-1645`), grid
`(N/64 = 16, egroups = 256)`.

The only threadgroup shape that fits is `BM=16` (25,600 B, 78% of the limit) —
but `BM=16` forces `WM=1`, i.e. 32 threads per threadgroup. That is a
**different kernel family**, not a fusion of the existing one, and it would have
to re-win the accept gate at `quantized.cpp:1660-1671` which requires
`bm==64 && wm==4`.

**Incidental finding worth keeping:** average rows per expert is 16 (route
histogram mean = 16.00) against `SM=16`, so on the *average* expert only **1 of
4 simdgroups is active**. That is an occupancy observation about the shipped
gather GEMM, independent of H5, and it is consistent with tanjiro's #138 line of
attack.

---

## 5. The SLC-absorption bound partly holds — and it is what actually kills H5

The kill-on-paper test I asked for was whether the working set already fits a
system-level cache, making the "DRAM saving" illusory.

- M4 Pro SLC ≈ **24 MiB**; M4 Max ≈ **48 MB** (Apple CPU Optimization Guide v4,
  "M-Cache"). **M5 Max is unknown** — public figures are rumour-grade, ≥48 MB.
- SLC is memory-side, shared, and inclusive with respect to the GPU cache
  (EXAM, arXiv 2504.13385 §A.1).
- The knee is at SLC capacity, but coherent streaming is absorbed well past the
  nominal size while random/scatter access collapses well below it.

The relevant figure is **8 MiB per layer**, not the 312 MiB aggregate — the
layers are not resident simultaneously. 8 MiB is comfortably SLC-served on both
M4 Pro and any M5 Max. **The DRAM saving H5 promised is largely illusory.**

Between §4 (infeasible at shipped geometry) and §5 (the saving is cached away
anyway), H5 is closed.

---

## 6. The lead that replaces it: the *shared* expert is unfused in prefill

While confirming §2 the code reader found two places where the **already-working,
already-shipped** fused-SwiGLU path is simply **not applied**:

1. **Shared expert, prefill — unfused** (`LagunaRuntimeModel.swift:8503`).
   Costs gate 0.5 MiB + up 0.5 MiB + activated 0.5 MiB per layer =
   **58.5 MiB per 512-token prefill**.
2. **Dense layer 0** — fusion is gated on `x.dim(1) == 1`
   (`LagunaRuntimeModel.swift:8423`), i.e. decode only. Prefill takes the
   unfused path. **~24 MiB.**

Together that is **~82.5 MiB of prefill round-trip** that the existing fused
kernel is already capable of eliminating. Unlike H5 this needs **no new kernel,
no new tile geometry, and no threadgroup-budget miracle** — it extends a proven
mechanism to two cases it currently skips.

Pricing it honestly is the first job: the same SLC argument in §5 applies, and
the per-layer figures here (1.5 MiB and ~24 MiB) are small, so the byte-price
law `Δscore% = 15.2800 × MB_removed / R_marg[GB/s]` should be applied with a
sceptical `R_marg` before anyone gets excited. But the *change* is small and the
*mechanism* is already in production, which is exactly the risk profile rounds
19–21 lacked.

**Round-23 candidate. Do not assign until the SLC-adjusted price is written
down.**

---

## 7. Smallest next read

`NAXTile` / `BaseNAXFrag` in
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/nax.h` — needed to
confirm the register-budget arithmetic in §4 and to price §6 properly.

---

## 8. Process note

Two **leaf** agents (one `explore`, one `search`) returned clean, collectable
results. Earlier in the campaign, `general-purpose` children that spawned their
own helpers died with "uncollected descendants". **Prefer leaf agents for
delegated research** unless the task genuinely needs a second level.
