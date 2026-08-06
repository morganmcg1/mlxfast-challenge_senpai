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

> **This section was substantially wrong in its first draft and has been
> rewritten after a dedicated pricing pass. The original claimed that flipping
> two call-site guards would reuse the shipped fused kernel at both sites for
> 58.5 + 24 MiB. Both the mechanism and the byte counts were wrong. What
> follows is the corrected version; the numbers below supersede any earlier
> quotation of "58.5 MiB", "24 MiB", "82.5 MiB", or line `:8503`.**

### 6.1 The shipped fused epilogue is not reachable from either candidate site

The sole `fuse_swiglu` predicate lives **inside the routed-expert gather
kernel** `fp_gather_qmm_rhs_expert_nax`
(`fp_quantized_nax.h:1568-1886`, predicate at `:1797`). Reaching it requires
`lhs_indices`/`rhs_indices` (`quantized.cpp:2197-2198`) via
`GatherQMM::eval_gpu` (`:2213`) ← `gather_qmm_rhs` (`:1943,1961`) ←
`gather_qmm_rhs_nax` (`:1593`), plus the host gate
`M>=64 && bm==64 && wm==4` (`quantized.cpp:1658-1661`). **Neither the shared
expert nor dense layer 0 dispatches through a gather path at all.** There is no
guard to flip.

### 6.2 Dense layer 0 is dead on arrival

Two independent killers:

- The predicate is false regardless: `N = 16384`
  (`_fusedDenseGateUpWeight.dims(2*8192, 2048)`, `LagunaRuntimeModel.swift:8446`,
  built `:8300-8301`).
- **The dense weights are plain bf16 `Linear`** (`:8438-8445`) — no quantized
  kernel is involved, so no NVFP4 epilogue exists to extend. Fusing would
  require a new bf16 steel-GEMM epilogue in `steel_gemm_fused_nax.h`: a
  different kernel family with no bit-exactness argument available.

The `x.dim(1) == 1` guard at `:8423` is **load-bearing correctness**, not
conservatism: it protects the bespoke single-row Metal GEMVs
`lagunaDenseGateUpSwiGLU` (`:8113-8130`) and `lagunaDenseDownResidual`
(`:8188-8207`), both of which carry hard `precondition`s. Feeding them `M=512`
crashes. **Do not touch it.**

### 6.3 The shared expert is worth a slot, but re-scoped

Good news first: **the concatenated NVFP4 `[gate; up]` bank already exists and
is already built.** `prepareFusedSharedGateUp()` (`:8248-8276`) concatenates on
axis 0, is called per sparse layer at `:11028-11029` under
`DARKBLOOM_FUSED_SHARED_GATE_UP` (default on, `:121-122`), and is eval'd at
`:11041-11043`. **No `MLXFastTransform` work is needed.**

The prefill non-use is the `x.dim(1) == 1` guard at **`:8463`** (not `:8503`),
gating the concat-bank `quantizedMM` branch at `:8490-8502`. Prefill falls
through to `:8504`: two separate `quantizedMM` calls plus
`compiledSiluProduct`. Unlike §6.2 this guard **is** conservative scoping
rather than correctness.

But lifting it does **not** get a fused SwiGLU. The host path it reaches is
`fp_qmm_t_nax_static`, which ships `wm=2, wn=2` (`quantized.cpp:494-495`) ⇒
`SN=32` ⇒ `kSwigluRegLocal` (`:1655-1657`) is **false**. A real fusion means
**adding a new epilogue to `fp_qmm_t_nax_static`**, using either the
threadgroup-staged arm (`:1838+`, free via the `Ws` alias) or forcing `wn=1`.
That is a kernel change, not a call-site change.

### 6.4 Corrected numbers

Earlier figures counted **writes only**. Written + read:

| item | corrected | earlier (wrong) |
| --- | --- | --- |
| shared expert, full fusion | **2.000 MiB/layer × 39 = 78.0 MiB** per 512-token prefill, + 78 fewer dispatches | 58.5 MiB |
| dense layer 0 | **32.0 MiB** + 2 dispatches — but unreachable, see §6.2 | ~24 MiB |

The `activated` round trip is **not** removed either way, because `down_proj`
still consumes it.

**Cheap sub-lead (lift the `:8463` guard only, no new epilogue): saves ZERO
bytes.** It writes `[1, 512, 1024]` = 1.0 MiB and reads 1.0 MiB straight back
through strided slices. Its entire value is **39 fewer QMM dispatches** plus
newly enabling `qmm_t_nax_static` (predicate `(K==2048 && N==1024) ||
(K==512 && N==2048)`, `quantized.cpp:510-514`). At the M5 barrier-serialized
dispatch price of 1.980 µs that is at most ~77 µs of prefill = **+0.028%** —
below MDE on its own, so it is only worth doing as a stepping stone to the
epilogue, or if the `qmm_t_nax_static` template flip turns out to matter.

### 6.5 Decode is already fused at both sites

`lagunaSharedSwiGLUQMV` (`:8473-8480`), `fusedSharedDownResidual`
(`:8380-8403`, batched at `:10104`), `lagunaDenseGateUpSwiGLU` (`:8449`) and
`lagunaDenseDownResidual` (`:8456`), called at `:10426` and `:10496`.
**This is a prefill-only gap. It cannot help the 75%-weight axis.**

### 6.6 Budget is a non-issue

A fused epilogue costs **zero** extra threadgroup memory and **zero** extra
tile registers. `gate_up_stage` is a cast alias of `Ws_storage`
(`:1613-1614`); the register-local arm reads `Dtile.frag_at` in place
(`:1822-1825`). Threadgroup usage is exactly **9,224 B of 32,768**
(`kWsElems = 64×72 = 4608` bf16 = 9216 B at `:1590, 1608-1612`, plus `bounds`
8 B at `:1617`). Per-thread MMA state ≈80–112 GPR against a ~128 ceiling
(`Dtile NAXTile<float,1,4>` `:1703` = 32 GPR; `Atile[2]` `:1730` = 16;
`Btile NAXTile<bfloat,4,2>` `:1771` = 32, doubled if both unrolled steps are
live).

### 6.7 Bit-exactness risks, ranked

1. **Largest.** The fused epilogue computes a bf16 sigmoid `1/(1+exp(|g|))`
   under `#pragma clang fp contract(off)` (`:1817-1826`), whereas the unfused
   path is `MLXNN.silu(gate) * up` under `compile(shapeless: true)`
   (`Vendor/mlx-swift-lm/Libraries/MLXLMCommon/SwitchLayers.swift:19-27`). The
   routed path passing greedy-token gates proves **token equality, not
   bit-exactness.** Verify by direct tensor comparison before anything else.
2. Flipping the kernel template N 512→1024 switches `fp_qmm_t_nax` →
   `_static`. Mitigated: the shared `down_proj` (K=512, N=2048) already
   satisfies the `_static` predicate.
3. The strided slices `gateUp[..., 0..<512]` / `[512...]` (`:8500-8501`) are
   non-contiguous; MLX may insert a copy, which can make the cheap §6.4
   variant **net negative**.
4. The generated twin `mlx-generated/fp_quantized_nax.cpp:1932-1934` must stay
   in lockstep.
5. Dense layer 0's epilogue family (§6.2) is entirely uncovered by any existing
   exactness argument.

### 6.8 Verdict

**Round-23 candidate, prefill-only, re-scoped to: add a SwiGLU epilogue to
`fp_qmm_t_nax_static` and lift the `:8463` guard.** 78.0 MiB written+read plus
78 dispatches. Dense layer 0 is closed. The `MLXFastTransform` half of the
original idea is unnecessary — the bank already exists.

---

## 7. Smallest next read

1. The body of `fp_qmm_t_nax_static` (`fp_quantized_nax.h:952-1001`) — where
   the epilogue would be inserted, and whether `wn=1` is admissible there.
2. One bit-exactness probe of the routed fused epilogue against
   `compiledSiluProduct` (risk §6.7.1).

Note for anyone re-running the §4 register arithmetic: the correct header is
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/steel/gemm/nax.h`
(`BaseNAXFrag:27`, `NAXTile:638`) — **not** `kernels/nax.h`.

---

## 8. Process note

Two **leaf** agents (one `explore`, one `search`) returned clean, collectable
results. Earlier in the campaign, `general-purpose` children that spawned their
own helpers died with "uncollected descendants". **Prefer leaf agents for
delegated research** unless the task genuinely needs a second level.
