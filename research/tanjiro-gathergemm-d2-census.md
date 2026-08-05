# T2 — Exhaustive threadgroup-memory census of the shipped `fp_gather_qmm_rhs_expert_nax` instantiation

PR #57 (`maple-2026-08-05f-gathergemm-coresidency`), task T2. Research-only note;
zero submitted bytes. No file under `benchmark.json`'s `editablePaths` is
touched by this PR.

Short names used below:

| tag | file |
|---|---|
| `QC` | `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp` |
| `NAXH` | `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized_nax.h` |
| `NAXCPP` | `Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized_nax.cpp` |
| `JIT` | `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/jit_kernels.cpp` |

## 1. Result

**Static threadgroup memory of the shipped instantiation = 9,224 B by source
census, 9,232 B as reported by a real compiled pipeline** (9,224 rounded up to
the next 16-byte boundary). Measured on both shapes the Laguna text tower
actually dispatches:

```
fp_gather_qmm_rhs_expert_nax_check_2048x1024
    staticThreadgroupMemoryLength=9232 B  maxTotalThreadsPerThreadgroup=1024  threadExecutionWidth=32
fp_gather_qmm_rhs_expert_nax_check_512x2048
    staticThreadgroupMemoryLength=9232 B  maxTotalThreadsPerThreadgroup=1024  threadExecutionWidth=32
```

(`research/tanjiro_gathergemm_occupancy_probe.swift` Phase A; the MSL is
extracted from the shipped `mlx-generated` sources by
`research/nax_msl_compile_check.sh`, linked with `xcrun -sdk macosx metallib`,
loaded with `device.makeLibrary(URL:)`, and instantiated with
`makeComputePipelineState`.) Source census and measurement agree, so the census
below is confirmed rather than merely asserted.

## 2. The shipped template arguments

Read off the dispatch site, not guessed:

| parameter | value | source |
|---|---|---|
| `T` | `bfloat16_t` | `QC:1661` |
| `group_size` | `16` | `QC:1661` |
| `bits` | `4` | `QC:1663` |
| `BM` | `64` | `QC:1643` (variant 5, table `QC:1468-1478`) |
| `WM` | `4` | `QC:1643` |
| `WN` | `1` | `QC:1643` |
| `BN` | `64` | `QC:1635` |
| `BK` | `64` | `QC:1635` |
| `transpose` | `true` | `QC:1635` |
| `fixed_K` / `fixed_N` | on | `QC:1888-1889`, gate `QC:1664-1668` |
| `Wtype` | `bfloat` | `QC:1661` |
| `tg_expert_groups` | `256` | `QC:1673` -> `QC:1383` |
| `wide_store` | `true` | `QC:1674` / `QC:1346` |
| `wide_load` | `true` | `QC:1679-1681` / `QC:1361`, certificate `QC:1518-1548` |
| `experts` | `256` | `NAXH:1595` |

The accept gate is verbatim `QC:1659-1662`; `laguna_moe_shape` is
`QC:1650-1651`. Name construction is `QC:1744-1774`, with the expert branch at
`QC:1747-1750` and suffixes `_gs_16_b_4_bm_64_bn_64_bk_64_wm_4_wn_1`,
`_k_<K>_n_<N>`, `_eg_256_ws_1_wl_1`. There are **no Metal function constants**
on the expert-aligned path (`QC:1836`), so the pipeline's static footprint is
fully determined by the template arguments — which is why an offline compile of
the same instantiation reproduces the shipped number.

## 3. The census

Exhaustive walk of every `threadgroup`-qualified declaration reachable in
`NAXH` lines 1568-1886 (the `fp_gather_qmm_rhs_expert_nax` body):

| # | declaration | source | bytes | note |
|---|---|---|---|---|
| 1 | `NAXWsChunk16<bfloat> Ws_storage[576]` | `NAXH:1612-1613` | **9,216** | `kWsElems=4608` (`:1610`) / `kWsPerChunk=8` (`:1611`) = 576 chunks; `alignas(16)`, `sizeof==16` (`NAXH:196-199`) |
| 2 | `Ws` alias over `Ws_storage` | `NAXH:1614` | 0 | reinterpreting pointer, no new storage |
| 3 | `gate_up_stage` | `NAXH:1615-1616` | **0** | explicitly **aliased onto `Ws_storage`**, non-additive |
| 4 | `int bounds[2]` | `NAXH:1618` (hoist) / `NAXH:1620` (fallback) | **8** | see section 4 |
| 5 | `Atile` | `NAXH:1730` | 0 | a **register** array, not threadgroup; activations are read straight from device memory at `NAXH:1737` |
| | **total** | | **9,224** | padded to **9,232** |

Supporting constants: `BK_padded = 72` (`NAXH:1589`), `SM = BM/WM = 16`
(`NAXH:1634`).

`9216 = 576 x 16`, and `576 = 4608/8`. The 16-byte pad to 9,232 is what a real
pipeline reports.

## 4. `DARKBLOOM_BSEARCH_HOIST` is free — there is no ~1 kB `bounds` saving

`DARKBLOOM_BSEARCH_HOIST` **defaults ON** (`JIT:1220`, gate `JIT:1247-1249`,
plumbed from `QC:1587-1591`). Both the hoisted and the fallback path declare
`int bounds[2]` = 8 B (`NAXH:1618` vs `NAXH:1620`), because on this
instantiation `experts / expert_groups = 256 / 256 = 1`. The two variants are
**byte-identical in threadgroup memory**. Any plan that budgets ~1 kB of
threadgroup-memory savings from changing the bounds representation is budgeting
against a quantity that does not exist.

## 5. Dispatch geometry

| quantity | value | source |
|---|---|---|
| `group_dims` | `(32, WN=1, WM=4)` = **128 threads = 4 simdgroups** | `QC:1914` |
| `grid_dims` | `(N/64, egroups=256, 1)` | `QC:1920-1923`; `xmajor_ct` pinned off at `QC:1563-1567` |
| dispatch call | `dispatch_threadgroups(grid_dims, group_dims)` | **`QC:1940`** |

`QC:1940` is the decisive line: the grid is expressed in **threadgroups**, not
threads. So the shipped launches are

| projection | K x N | threadgroups |
|---|---|---|
| gate / up | 2048 x 1024 | `(1024/64) x 256` = **4,096** |
| down | 512 x 2048 | `(2048/64) x 256` = **8,192** |

Per core: **205 / 410 TG/core on this 20-core M4 Pro**, and **102 / 205 TG/core
on the ranked 40-core M5 Max**. Both are an order of magnitude past the
24-TG/core figure that the co-residency argument in `research/` is built on.

## 6. Twin-file consistency (`.h` vs `mlx-generated/*.cpp`)

`NAXH` is 1,886 lines / 65,515 B. `NAXCPP` is 2,027 lines / 68,466 B. The
embedded MSL is `NAXCPP:152-2021`, with provenance comment at `NAXCPP:148`, a
`#line 1` at `NAXCPP:151`, and the raw string closing `)preamble";` at
`NAXCPP:2024`.

The two are **not byte-identical**. The delta is 4 pure deletions covering 16
lines, **all comments or `#include` directives**, with zero insertions and zero
substitutions:

| deleted from `.h` | content |
|---|---|
| `NAXH:6-7` | `#include` lines |
| `NAXH:1401-1405` | comment block |
| `NAXH:1455` | comment |
| `NAXH:1761-1768` | comment block |

Because the deletions are interleaved, **the line offset is piecewise and the
"+141 verbatim" claim in `research/` §0.9.9 is wrong on both counts** (it is not
verbatim, and no single offset applies):

| `.h` range | offset to `NAXCPP` |
|---|---|
| 1-5 | +151 |
| 8-1400 | +149 |
| 1406-1454 | +144 |
| 1456-1760 | **+143** |
| 1769-1886 | +135 |

Spot-verified line pairs: `NAXH:1568 -> NAXCPP:1711`, `1589 -> 1732`,
`1610 -> 1753`, `1612 -> 1755`, `1615 -> 1758`, `1618 -> 1761`,
`1620 -> 1763`.

Practical consequence: the embedded twin is behaviourally consistent with the
header (no semantic drift), so editing one without the other would only diverge
if the edit landed in a comment region. But any future note citing a `.cpp`
line derived by adding a constant to a `.h` line is unreliable; use the table
above.

## 7. Three corrections to existing research notes

I am flagging these rather than editing the notes.

1. **`research/CURRENT_RESEARCH_STATE.md:544-547` and
   `research/GATHER_GEMM_REGIME_DESIGN.md:239-241` misread
   `tg_expert_groups`.** It is not an expert-partition count that sizes a
   per-expert `bounds` array; it is the **grid.y threadgroup count, 256**
   (`QC:1673` -> `QC:1383`, consumed at `QC:1920-1923`). `bounds` is therefore
   `int[2]` = **8 B**, not ~1 kB. Every downstream byte-savings estimate keyed
   on that misreading is void.
2. **`Ws_storage` is 9,216 B, not "~8.4 kB".** The "~8.4 kB" figure comes from
   using `BK_padded = 66`; the source value is **72** (`NAXH:1589`).
3. **The "+141 verbatim" twin-offset claim is false**, per section 6.

## 8. What this means for a threadgroup-memory-byte optimisation

The single dominant term is `Ws_storage` at 9,216 B / 9,224 B total = **99.91%**
of the footprint. There is no incidental slack: `gate_up_stage` is already
aliased, `Atile` is already in registers, activations are already read direct
from device memory, and `bounds` is 8 B. Reducing the footprint therefore
requires shrinking the weight staging tile itself — i.e. changing `BK`, `BN`,
`BK_padded`, or the chunk representation — which changes the GEMM blocking and
is not a free byte-accounting win.

Separately, the co-residency motivation for wanting fewer bytes does not survive
measurement on this host: see `research/tanjiro-pr-gathergemm-coresidency.md`
sections 3-5, where 640 threadgroups (32/core) at this exact 9,232 B footprint
are demonstrated co-resident, and where the shipped 4,096/8,192-threadgroup
launch is shown to sit far past the whole occupancy curve.

## 9. Caveats

- Measured on Apple M4 Pro (`Mac16,11`), 20 GPU cores, macOS 26.5.2, Apple GPU
  generation 16. Generation 16 **cannot select** the `_nax` kernels at runtime
  (`Vendor/mlx-swift/.../backend/metal/device.cpp:913-931` requires generation
  >= 17 and macOS >= 26.2), so the pipeline here was created directly from the
  shipped MSL rather than reached through the runtime's selection path.
  Pipeline *creation* and the static footprint it reports are properties of the
  compiled instantiation and the template arguments, both of which are
  identical on M5; the number should transfer. Anything about *runtime
  selection* on M5 is not established by this note.
- The census covers **static** threadgroup memory only. There is no
  `setThreadgroupMemoryLength` call on this path, so dynamic threadgroup memory
  is zero, but that is an absence-of-evidence reading of the dispatch site
  (`QC:1900-1940`) rather than a measured dynamic total.
