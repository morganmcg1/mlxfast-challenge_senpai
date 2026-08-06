# Dense-layer BF16 lossless re-representation — research & design brief

2026-08-06 02:40 UTC. Advisor-side research only; no source edits. Scope: the
single dense (non-MoE) decoder-layer MLP, its two decode kernels
`laguna_dense_gate_up_swiglu_bf16_v1` and `laguna_dense_down_residual_bf16_v1`,
and whether a **bit-exact lossless repack** of their BF16 weights can cut DRAM
bytes/step.

**Correction to the brief:** the dense layer is **layer index 0**, not 40.
`docs/laguna-weight-contract.md:104-108` ("Layer 0 dense MLP:
`mlp.gate_proj.weight`, `up_proj.weight`: BF16 `[8192, 2048]`;
`mlp.down_proj.weight`: BF16 `[2048, 8192]`") and the kernel comment
`Sources/MLXFastModel/LagunaRuntimeModel.swift:8118` ("Layer 0's gate/up/down
projections are plain BF16"). R12.13's "layer 40/40" phrasing means "1 of 40
layers". Census targets `model.layers.0.mlp.*`.

## 1. Code-anchored facts (MEASURED in code, this checkout)

- **Disk → array path.** The runtime loads the *transformed* tree
  (`weights/model.safetensors.index.json` + shards) via `DenseTensorStore`
  (`Sources/MLXFastModel/DenseTensorStore.swift:169-177`), materialized
  one tensor at a time and **copied into MLX-owned storage**
  (`Sources/MLXFastModel/RuntimeWeightLoading.swift:11-24`), then
  `sanitize → update → eval` (`Sources/MLXFastModel/LagunaRuntimeWeights.swift:627-632`).
- **Kernel-visible layout.** Decode gate/up reads a fused row-major BF16
  `[16384, 2048]` bank (`gate` rows then `up` rows), built **once at load**
  by `prepareFusedDenseGateUp()`
  (`LagunaRuntimeModel.swift:8382-8399`, called from
  `prepareFusedRuntimeWeights()` at `LagunaRuntimeModel.swift:11234-11240`).
  Each simdgroup owns 4 consecutive rows and streams the full 2048-wide row as
  `vec<bfloat,4>` loads (`LagunaRuntimeModel.swift:8143-8180`). The down kernel
  reads `downProj.weight` `[2048, 8192]` directly, same 4-rows-per-simdgroup
  pattern (`LagunaRuntimeModel.swift:8239-8266`, call at 8552-8553).
- **Decode-only.** Both fused kernels are gated on `x.dim(1) == 1`
  (`LagunaRuntimeModel.swift:8519`); prefill layer 0 uses stock `Linear` GEMM.
  Original BF16 arrays must therefore stay resident regardless.
- **Load-time repack hook exists and is the established pattern.** Same-file
  precedents built at untimed init: fused QKV / shared gate-up / dense gate-up
  (`LagunaRuntimeModel.swift:11211-11241`), lm_head coarse copy
  (`11245-11257`), and — decisive precedent — the **byte-exact narrow NVFP4
  scale planes** with census + reconstruction certificate and no-escape
  fixed-width design (`LagunaRuntimeWeights.swift:653-680`). Ranked precedent
  for "lossless re-representation + certificate" is already on the board
  (frieren PR35, `research/frieren-pr35-r5a-certificate.md`).
- **Transform stage.** For Laguna it is a validated **byte-for-byte
  pass-through** and the weight contract *forbids derived metadata sidecars*
  (`Sources/MLXFastTransform/Transform.swift:69-84`). TASK.md:71-75 does allow
  representation changes "through the editable transform and runtime
  together", but a load-time pack (milliseconds, untimed) avoids touching the
  transform contract at all. **Recommendation: pack at load, not transform.**
- **Admissibility.** Re-quantization of this MLP is explicitly barred
  (`TASK.md:92-94`). A lossless repack changes no value: the kernel decodes the
  **identical 16-bit pattern**, converts and FMA-accumulates in the identical
  order, so outputs are bitwise unchanged by construction; the certificate is a
  full 50,331,648-weight decode-and-compare at init/test time.
- **Byte-budget landmine.** `LagunaRuntimeModel.swift` is **521,768 B** against
  the 524,288 B per-file cap — only **2,520 B headroom**. The new kernels and
  packer must live in a **new file** under `Sources/MLXFastModel/` (the
  editable surface is directory-level: `benchmark.json` `editablePaths` lists
  `Sources/MLXFastModel`, `Sources/MLXFastTransform` + 95 vendor entries); only
  the ~10-line call-site guards go into the big file.

## 2. Weights are NOT on this host — distribution is UNMEASURED

`weights/` and `reference_weights/` here contain only `.gitkeep` (advisor
workspace). No bit-pattern census could be run; every distributional claim
below is INFERRED and must be settled by the step-0 census (§4) on a student
host (`setup.sh:54` puts the reference tree at
`reference_weights/laguna-xs-2.1-nvfp4-mlx`; the transformed `weights/` tree is
byte-identical for these tensors per §1, and is what the kernel reads).

## 3. Scheme design space

BF16 = `[s:1][e:8][m:7]`. Per-weight information actually present (INFERRED for
a trained tensor): sign ≈ 1.0 bit, mantissa ≈ 7.0 bits (near-uniform),
exponent ≈ 2–3 bits (weights concentrate in ~8–16 binades) → entropy floor
≈ 10–11 bits/weight. So **the only compressible plane is the exponent**, unless
the checkpoint was ever round-tripped through a lower-precision format (then
trailing mantissa bits are identically zero — the jackpot).

All viable schemes are one family: **fixed-width `sign + exponent-delta +
mantissa` with a per-row uint8 exponent base**, widths chosen by census.
Reconstruction (pure ALU, ~6 int ops/weight, no table, no second dependent
load):

```metal
// c: packed code; base: per-row uint8 (16,384 B gate/up + 2,048 B down total)
ushort s = c >> (k+m); ushort d = (c >> m) & ((1<<k)-1); ushort mt = c & ((1<<m)-1);
ushort w = (d == (1<<k)-1) ? (s << 15)                        // reserved ±0 code
                           : ((s << 15) | ((base + d) << 7) | (mt << (7-m)));
out = as_type<bfloat>(w);
```

| id | layout (per weight) | bits | MB/step read | MB saved | decode cost | verdict |
|---|---|---:|---:|---:|---|---|
| **P8** | `s1+d4+m3` single u8 stream | 8 | 50.33 | 50.33 | pure ALU | **jackpot; needs census: ≥4 trailing mantissa bits zero AND per-row exp span ≤14** |
| **P12** | `s1+d4+m7`, 8 weights → 12 B (3×u32) | 12 | 75.50 | 25.17 | pure ALU | **base case; needs per-row exp span ≤14** |
| P13 | `s1+d5+m7` two-plane (u8 s+m; 5-bit d) | 13 | 81.79 | 18.87 | ALU + 2nd coalesced stream | fallback if span ≤30 |
| T8 | u8 index → global ≤256-entry table | 8+ε | 50.40 | 50.26 | 512 B threadgroup table; bank conflicts | only if ≤256 distinct patterns but unstructured |
| T12/tile | u8 index + 256-entry table per 4096-tile | 9 | 56.62 | 44.04 | per-tile table stream | **reject** (see below) |

Rejections, explicitly:

- **Per-tile 256-entry codebook (T12/tile):** a 4096-weight tile needs ≤256
  distinct 16-bit patterns. One binade × both signs already spans 256 patterns
  (7-bit mantissa); a Gaussian tile spanning ≥2 binades exceeds it almost
  surely. Only a low-precision round-trip could rescue it — and then P8 decodes
  the same bytes with pure ALU instead of a table. Dominated; reject.
- **XOR/delta along the reduction axis:** mantissa bits are near-uniform, so
  XOR of neighbours preserves ~7 bits of entropy; only exponent bits compress,
  which the base+delta already captures without the serial prefix dependency
  that breaks 4-rows-per-simdgroup random access. Reject.
- **Huffman/rANS:** floor is only ~10–11 bits (≈ P12's 12) but costs
  variable-length, divergent, offset-table-indirected decode inside a kernel at
  96–97 % of DRAM ceiling. Reject.
- **Second DRAM stream caveat:** P13's two planes are both sequential and
  coalesced (the NVFP4 QMVs already stream weight+scales pairs); acceptable
  but strictly worse than P12 unless span forces it.

Kernel-cost audit: at 50 % bytes, DRAM supplies ~4 B/ns (M4), i.e. ~2
weights/ns needing ~12 int-ops/ns — three orders of magnitude under GPU int
throughput. Decode adds no dependent DRAM access in P8/P12; unpack latency is
hidden by widening `values_per_thread` to 8 (aligned 12 B/8 B loads) and the
unchanged simdgroup row loop. The FP path (float convert → FMA order →
`simd_shuffle_down` reduction → epilogue, `LagunaRuntimeModel.swift:8174-8201,
8261-8279`) is kept verbatim ⇒ bit-exact outputs given bit-exact weights.

Handling specials: reserved code covers ±0 exactly. Subnormals/Inf/NaN would
blow the row span (exp field 0 or 255) — census gate requires zero of them, or
≤0.1 % of rows escaping to a stock-row read (base sentinel `0xFF`, the shipped
lane-major pattern, `LagunaRuntimeWeights.swift:672-680`).

## 4. Step-0 census — the one falsifiable gate (≤1 h, no kernel work)

Run on any host with the weights; reads 100.66 MB, runs in ~2 min:

```python
# research/dense_census.py; run: python3 research/dense_census.py weights
import json, struct, sys; import numpy as np; from pathlib import Path
W = Path(sys.argv[1]); idx = json.loads((W/"model.safetensors.index.json").read_text())["weight_map"]
names = sorted(n for n in idx if ".layers.0.mlp." in n and n.endswith("proj.weight")); assert len(names)==3
for name in names:
    f = open(W/idx[name], "rb"); hlen = struct.unpack("<Q", f.read(8))[0]
    h = json.loads(f.read(hlen)); t = h[name]; assert t["dtype"]=="BF16"
    f.seek(8+hlen+t["data_offsets"][0])
    u = np.fromfile(f, "<u2", (t["data_offsets"][1]-t["data_offsets"][0])//2).reshape(t["shape"])
    e = ((u>>7)&0xFF).astype(np.int16); m = (u&0x7F); s = (u>>15); nz = e!=0
    cnt = np.bincount(u.ravel(), minlength=65536); p = cnt[cnt>0]/u.size
    orm = int(np.bitwise_or.reduce(m[nz])); tz = 7 if orm==0 else (orm&-orm).bit_length()-1
    rows = u.shape[0]; er = np.where(nz, e, 512)
    rmin = er.min(1); rmax = np.where(nz, e, -1).max(1); rspan = np.maximum(rmax-rmin, 0)
    g = e.reshape(rows//4, -1); gnz = nz.reshape(rows//4, -1)
    gspan = np.maximum(np.where(gnz, g, -1).max(1) - np.where(gnz, g, 512).min(1), 0)
    tiles = u.reshape(-1, 4096); dtile = max(len(np.unique(t_)) for t_ in tiles)
    print(name, dict(distinct16=int((cnt>0).sum()), H=round(float(-(p*np.log2(p)).sum()),3),
      zeros=int(((u&0x7FFF)==0).sum()), subnormal=int(((e==0)&(m!=0)).sum()), infnan=int((e==255).sum()),
      exp_distinct=int(len(np.unique(e[nz]))), exp_span_global=int(e[nz].max()-e[nz].min()),
      row_span_max=int(rspan.max()), row_span_p100_le14=float((rspan<=14).mean()),
      grp4_span_max=int(gspan.max()), trailing_zero_mantissa_bits=tz,
      max_distinct_per_4096tile=int(dtile),
      mantissa_top8=np.bincount(m[nz].ravel(),minlength=128).argsort()[-8:][::-1].tolist()))
```

**Decision table (preregister; all three tensors must pass the chosen row):**

| gate | condition (every tensor) | assign | MB saved | % score @546.2 / @610 |
|---|---|---|---:|---|
| SANITY | `infnan==0` and `subnormal==0` (else ≤0.1 % rows → escape variant; else STOP) | — | — | — |
| **GO-8** | `trailing_zero_mantissa_bits ≥ 4` AND `row_span_max ≤ 14`, or `distinct16 ≤ 256` | P8 (or T8) | 50.33 | **1.37 / 1.23 %** |
| **GO-12** | `row_span_max ≤ 14` | P12 | 25.17 | **0.68 / 0.61 %** |
| GO-13 | `row_span_max ≤ 30` | P13 | 18.87 | 0.51 / 0.46 % |
| **STOP** | otherwise | close arm, record numbers | ≤12.58 | ≤0.34 % ≈ MDE — not worth a kernel rewrite |

Span bar is 14, not 15: 2^4 codes minus one reserved ±0 code = 15 usable deltas
⇒ `span+1 ≤ 15`. The STOP branch is honourable: it costs one hour, produces the
first bit-level census of the only unquantized matmul in decode, and
permanently closes a 4.51 %-of-score question.

## 5. Pricing (arithmetic inline)

Base: 3 × 8192·2048·2 B = 100,663,296 B = 100.663 MB/step = 5.61 % of 1794
MB/step decode traffic.

- **P8:** Δ = 100.663·(1−8/16) = 50.331 MB. t = 50.331e6/546.2e9 = **92.1 µs**
  → 0.0921 ms × 14.862 %/ms = **1.370 %**; at 610 GB/s: 82.5 µs → **1.226 %**.
  MDE ratio 4.4–4.9×.
- **P12:** Δ = 25.166 MB → 46.1 µs → **0.685 %**; at 610: 41.3 µs → **0.613 %**.
  MDE ratio 2.2–2.5×.
- **P13:** Δ = 18.874 MB → 34.6 µs → 0.514 %; at 610: 30.9 µs → 0.460 %.
- Overheads: per-row bases 18,432 B resident, ~18 KB/step extra traffic =
  0.03 µs; T8 table traffic 128 tg × 512 B × 2 kernels ≈ 0.13 MB/step ≈ 0.24 µs.
  Negligible; already netted in the table above to 3 s.f.
- **Upper bound:** R12.13 prices this block at 303.3 µs M5-eq (M4 × 0.7565,
  `research/maple-tanjiro-pr73-decode-kernel-census.md:520`) = 4.51 % of score,
  implying only ~332 GB/s effective on M5; pure byte pricing at 546.2 GB/s says
  184.3 µs = 2.74 %. If the calibrated figure is right, P8 ≈ **2.25 %** and
  P12 ≈ **1.13 %** — my table quotes the conservative byte-priced numbers.
- M4 local check: P12 should cut the pair from ~401 → ~301 µs/step; P8 → ~201
  µs/step — far above local timing noise.

## 6. Ranked recommendation

1. **ASSIGN: bit-plane repack, width chosen by the §4 census** (P8 if GO-8,
   else P12; P13 only after explicit repricing). One new file
   (`LagunaDensePacked.swift`: packer + 2 kernels + init certificate), tiny
   guarded call-site edits at `LagunaRuntimeModel.swift:8538-8556` and
   `11234-11240`, new `DARKBLOOM_DENSE_PACKED*` flags with stock fallback,
   originals stay resident for prefill (skip building the 67.1 MB
   `_fusedDenseGateUpWeight` copy when packed is active ⇒ net RAM delta ≈
   +8 MB for P12, −17 MB for P8).
2. T8 global codebook — only if census shows ≤256 distinct patterns *without*
   base+delta structure.
3. Per-tile codebook, XOR/delta, entropy coding — rejected (§3).

Gate everything on the census. MEASURED here: all code facts (§1), byte
counts, cap headroom. INFERRED: exponent concentration, entropy floor, M5
rates between 332–610 GB/s. ASSUMED: none load-bearing — the census replaces
assumption with measurement before any kernel is written. The arm is dead only
if per-row exponent span >30 in any tensor **and** no mantissa truncation
**and** >4096 distinct patterns — a distribution no trained, non-degenerate
BF16 tensor I know of exhibits, but the checkpoint gets the final word.
