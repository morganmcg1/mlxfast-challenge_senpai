# r96-c Stage 2 — decode kernel design for lossless block-exponent compaction

Written at the end of the Stage-1 session as the assignment's "kernel design
written down" deliverable. Nothing here is measured; every byte number comes
from the round-trip-certified Stage-1 ladder
(`research/artifacts/fern_r96_ladder.json`, W&B run `vr40qzky`).

## 0. Correction the design rests on

The assignment says layer 0's decode MLP is "a plain MLX BF16 matmul" and that
Stage 2 "must supply its own decode GEMV kernel". That is wrong, and the
correction makes Stage 2 *smaller* than assigned.

Layer-0 dense decode is already served by two hand-written Metal kernels:

| kernel | source | dispatch |
|---|---|---|
| `laguna_dense_gate_up_swiglu_bf16_v1` | `Sources/MLXFastModel/LagunaRuntimeModel.swift:8581` | `Sources/MLXFastModel/LagunaRuntimeLayers.swift:266` |
| `laguna_dense_down_residual_bf16_v1` | `Sources/MLXFastModel/LagunaRuntimeModel.swift:8674` | `Sources/MLXFastModel/LagunaRuntimeLayers.swift:286-302` |

`prepareFusedDenseGateUp()` (`LagunaRuntimeLayers.swift:122-139`, called from
`LagunaRuntimeModel.swift:9183`) builds the concatenated `[gate; up]` bank into
`_fusedDenseGateUpWeight` (`LagunaRuntimeLayers.swift:42`). Stage 2 is an
**edit of two shipped kernels plus one packer**, not a new kernel family.

Shipped geometry (do not change it — rule 24):

- gate/up kernel: 128 threadgroups x 16 simdgroups; 4 gate + 4 up output rows
  per simdgroup; each lane owns 4 columns striding 128 across 16 blocks;
  8-byte `vec<bfloat,4>` loads; `simd_shuffle_down` reduction; bf16 SiLU
  epilogue on lane 0.
- down kernel: same pattern over 64 blocks, ~2 output rows per simdgroup,
  residual epilogue.

## 1. Encoding actually implemented by the packer

Per block of `B` consecutive weights along the chosen blocking axis:

- **base plane**: 1 byte, the block's minimum BF16 exponent (`0xFF` = escape).
- **delta plane**: `d` bits per weight, `exp - base`.
- **payload plane**: 8 bits per weight — 1 sign bit + 7 mantissa bits.

`m = 7` is forced, not chosen: the Stage-1 census measured
`trailing_zero_mantissa_bits = 0` on all three tensors, so every mantissa bit is
live. The three planes are stored separately (plane-major within a row) so each
plane is independently aligned; this is what makes the payload plane exactly one
byte per weight and `uchar4`-loadable.

Escaped blocks keep their original BF16 bytes and are read from the
**still-resident original tensor at today's exact address**, so an escape costs
zero extra resident bytes and reuses the shipped NVFP4 escape idiom
(`LagunaRuntimeModel.swift:4869-4876`, builder `LagunaRuntimeWeights.swift:886-940`).

## 2. Staged implementation ladder (priced, certified, in order)

Every row below is round-trip certified: 0 mismatched weights and per-tensor
SHA-256 equality against the original BF16 bytes.

| stage | change | bytes/step | saved | % score | M4 µs/step | escape branch needed |
|---|---|---:|---:|---:|---:|---|
| **S2a** | gate/up only, reduction axis, `B=128 d=4 m=7`; `down` stays stock BF16 | 84,592,384 | 16.071 MB | 0.2446 | 60.3 | per-block, gate/up only |
| **S2b** | S2a + `down` reduction axis, `B=row d=6 m=7` | 80,400,128 | 20.263 MB | 0.3085 | 76.1 | none added (`down` escapes = 0/2048) |
| **S2c** | S2b but `down` on the **output** axis, `B=32 d=4 m=7` | 78,219,008 | 22.444 MB | 0.3417 | 84.3 | per-block in `down` too |

M4 µs uses the #498 DRAM model `t = 3.97 µs + bytes / 266.3 GB/s`; score uses the
PR #110 realised byte price 0.015224 %/MB/step.

**Start at S2a.** It edits exactly one kernel, both of its planes are
byte-aligned, and it is the cheapest possible kill-or-confirm signal. Its
predicted 60.3 µs/step is below the ≈80 µs M4 single-receipt bar but well above
the blocked-ladder floor (SE 1.34 µs/step, rule 56), so it is measurable with
the rig from #497 and must not be measured with a single receipt.

## 3. Exact layout arithmetic (verified against measured bytes)

### gate/up, reduction axis, `B=128 d=4` — shape `[8192, 2048]`, 16 blocks/row

per row: payload 2048 B (32 lines) + delta 1024 B (16 lines) + base 16 B
= **3088 B** vs 4096 B BF16 (−24.6 %).
`8192 x 3088 = 25,296,896`; plus escape line bytes 219,648 (gate) / 224,512 (up)
gives the measured 25,516,544 / 25,521,408. No padding anywhere.

Lane access, keeping `values_per_thread = 4`: one `uchar4` payload load, one
`ushort` delta load (4 weights x 4 bits = exactly 2 bytes), one `uchar` base
load per block hoisted into a register. That is 6.5 bytes per 4 weights against
8 bytes today.

### down, reduction axis, `B=row d=6` — shape `[2048, 8192]`, 1 block/row

per row: payload 8192 B (128 lines) + delta 6144 B (96 lines) + base 1 B
= 14337 B vs 16384 B BF16 (−12.5 %). `2048 x 14337 = 29,362,176` = measured.
Zero escapes, so **no escape branch is added to the down kernel at all**.

Friction: `d=6` is sub-byte per weight — 4 weights occupy 3 delta bytes, so a
lane needs a `ushort`+`uchar` pair and two shifts per 4 weights. `d=8` would
make the row 16385 B, i.e. worse than BF16, so `d=6` is the only aligned-plane
option on this axis.

### down, output axis, `B=32 d=4` — 524,288 blocks

per 32-weight block: payload 32 B + delta 16 B + base 1 B = 49 B vs 64 B.
`524288 x 49 = 25,690,112`; plus strided escape line bytes 1,490,944 gives the
measured 27,181,056. Delta is exactly 0.5 B/weight, so the inner loop is
*simpler* than S2b's — but the planes are transposed relative to the shipped
down kernel, so S2c is a work-decomposition change and therefore a separate arm
under rule 24. It buys only 2.181 MB (0.033 %, 8.2 µs) over S2b.

All rungs are 64-byte-line aligned at row granularity; no padding is required
and none was priced.

## 4. Packer

Build in `Sources/MLXFastModel/LagunaRuntimeWeights.swift`, following the
lane-major idiom at `:886-940`:

1. read the BF16 tensor, compute per-block min exponent,
2. mark blocks with `span > (2^d - 1)` as `0xFF` escapes,
3. emit the three planes into one buffer per tensor,
4. **certify in-process**: decode the packed bank and compare all 50,331,648
   weights bit-for-bit against the source; on any mismatch log and decline to
   the stock BF16 path rather than shipping a wrong bank.

Keep the original BF16 tensors resident (they are the escape source and the
decline-to-stock fallback). Resident RAM grows by the packed bank size; the
scored metric is bytes *streamed per decode step*, not resident bytes.

## 5. Correctness and measurement plan

- `research/run_upstream_equivalence.sh` — numerical oracle (rule 51: it is not
  a dispatch oracle).
- public 64-step drift tripwire, plus one token-stream hash across all timed
  slots (rule 45).
- reduction order must not change: **keep `values_per_thread = 4`**. Widening it
  to 8 would reorder the `simd_shuffle_down` tree and is the central trap in
  this design.
- rule 39: grep-prove the packed path is reachable on the default config before
  trusting any timing.
- rule 33: suffix each variant's kernel name (`..._bexp128d4_v1`, etc.).
- rule 56: blocked randomised within-run ladder for ranking; switching-free
  `perrun` pairs for absolute savings. Never average the two designs.
- check the observed µs/step against the table in §2; a large miss is itself a
  finding, because §2 assumes byte removal converts at face value while #498
  measured the trio at 92-93 % of sequential-read peak (250.3/253.3 GB/s), i.e.
  expect ~85-95 % conversion on M4.

## 6. Risks, in the order they are likely to bite

1. **Reduction-order drift** from any change to lane/column mapping. Mitigation:
   freeze `values_per_thread = 4`; run the oracle and the drift tripwire.
2. **Sentinel/overflow bugs** in the packer. Mitigation: the in-process
   50.3 M-weight decode-and-compare certificate with decline-to-stock.
3. **Achieved-GB/s regression** — three plane loads instead of one contiguous
   load can lower achieved bandwidth enough to eat a 24.6 % byte cut.
   Mitigation: per-kernel dispatch A/B (rule 44, name- and residency-matched)
   before any end-to-end claim.
4. **Escape-rate blow-up on a different checkpoint.** Mitigation: the packer
   recomputes the census at load time; if the measured escape fraction exceeds
   the Stage-1 value by more than ~2x, decline to stock.
5. **M5 transfer.** The byte price is inferred from the M4 DRAM model. S2a/S2b
   are below the ≈80 µs single-receipt bar, so an M5 ranked receipt alone will
   not resolve them; they need the paired same-session rig.
