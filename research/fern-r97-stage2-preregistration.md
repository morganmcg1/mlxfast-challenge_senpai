# R97-A Stage 2 preregistration — layer-0 dense-MLP block-exponent compaction

Assignment `maple-r97-a-dense-mlp-stage2`, revision `r97-a-rev1`, PR #525.
Base SHA `b78e7cdb80b5ae5f1cb1fdd39803322fb283ae5e`.

**This document is committed before any timing datum for this experiment
exists.** It fixes the plane format, the priced instruction budget, the ladder
design, the predictions, and the go/no-go bar. Nothing below may be revised
once a rung has been timed; a deviation is recorded as a deviation in
`research/fern-r97-stage2-result.md`.

Scope is rung **R1** only. R2 (down compacted on the output axis) is explicitly
out of scope and will not be built or timed.

---

## 0. What is being changed

Layer 0 is the only decoder layer whose MLP is plain BF16 (`gate_proj`,
`up_proj`, `down_proj` are never NVFP4). At decode it therefore streams
100,663,296 B of BF16 weight per step through two kernels that are pure
bandwidth:

| kernel | source | shape | bytes/step |
|---|---|---|---|
| `laguna_dense_gate_up_swiglu_bf16_v1` | `LagunaRuntimeModel.swift:8668` | fused `[16384, 2048]` | 67,108,864 |
| `laguna_dense_down_residual_bf16_v1` | `LagunaRuntimeModel.swift:8761` | `[2048, 8192]` | 33,554,432 |

The R96 census (`research/artifacts/fern_r96_dense_census_reduction_axis.json`)
established, for all three tensors: zero zeros, zero subnormals, zero inf/NaN,
and `trailing_zero_mantissa_bits = 0`. The mantissa plane is therefore
**incompressible** — `m = 7` is forced, not chosen. The only compressible field
is the 8-bit exponent, whose per-block span is far below 8 bits.

This experiment replaces the BF16 weight stream with a **lossless
block-exponent representation**: a 1-byte payload per weight (7 mantissa bits +
sign), a `d`-bit per-weight exponent delta, and a 1-byte per-block base
exponent. Reconstruction is bit-exact for every representable pattern, so every
decoded weight is the identical BF16 value the stock kernel loads, every fma
consumes the identical `float`, and no checked token can move.

Two rungs are built and timed:

* **S2a** — `gate_proj`/`up_proj` compacted at `B = 128, d = 4, m = 7`;
  `down_proj` untouched (stock BF16).
* **S2b** — S2a plus `down_proj` compacted at `B = row (8192), d = 6, m = 7`,
  which the census shows is the only escape-free down configuration.

---

## 1. Exact format per plane

### 1.1 Common encoding (the "rotate" formulation)

A BF16 bit pattern is `bits = s<<15 | e<<7 | m` with `s` 1 bit, `e` 8 bits,
`m` 7 bits. Define

```
rot(bits) = (bits << 1) | (bits >> 15)          // 16-bit rotate left by 1
          = e<<8 | m<<1 | s
```

so the **low byte of `rot(bits)`** is exactly `payload = (m<<1) | s` and the
**high byte** is exactly `e`. Encoding stores `payload` and `delta = e - base`;
decoding rebuilds

```
r    = (base + delta)<<8 | payload      // == rot(bits)
bits = (r >> 1) | (r << 15)             // 16-bit rotate right by 1
value = float(as_type<bfloat>(bits))
```

This is a bijection on all 65,536 patterns, including zero, subnormal and
inf/NaN encodings, so exactness does not depend on the census. The census only
determines whether a given `(B, d)` fits without escapes.

`base` is the per-block **minimum** exponent. `base = 0xFF` is the escape
sentinel. Since the census shows no inf/NaN in any of the three tensors,
`e <= 254` for every weight, so a real `base` can never collide with `0xFF`.
The packer asserts this and declines to stock if it is ever violated.

### 1.2 Gate/up planes (rung S2a), `B = 128, d = 4, m = 7`

The stock kernel's `block` loop iterates `blocks = in_vec_size / block_width =
2048 / 128 = 16` times; iteration `b` covers columns `[128b, 128b+128)` of one
row, and thread `lane` reads the 4 contiguous columns `128b + 4*lane .. +3`.
**The census block `B = 128` is therefore exactly one K-iteration of one row**,
which is why the base value is simdgroup-uniform and can be hoisted.

Let `R in [0, 16384)` be the fused row index (gate rows `0..8191`, up rows
`8192..16383`) and `c in [0, 2048)` the column.

| plane | dtype | elements | index of weight `(R, c)` | bytes |
|---|---|---|---|---|
| `bexpPayload` | `uint8` | `16384 * 2048` | `R*2048 + c` | 33,554,432 |
| `bexpDelta` | `uint8` | `16384 * 1024` | byte `R*1024 + c/2`, nibble `c&1` at bits `4*(c&1)` | 16,777,216 |
| `bexpBase` | `uint8` | `16 * 16384` | `(c/128)*16384 + R` (**block-major**) | 262,144 |
| `bexpEscape` | `bfloat16` | `nEsc * 128` | `slot*128 + (c&127)` | 2·128·`nEsc` |

Totals per tensor (`nEsc` from the census: gate 858, up 877 of 131,072 blocks):

```
gate: 16,777,216 + 8,388,608 + 131,072 + 219,648 = 25,516,544 B
up  : 16,777,216 + 8,388,608 + 131,072 + 224,512 = 25,521,408 B
```

Both reproduce the census `net` figures exactly.

Design notes that are part of the preregistered format:

* **Block-major base plane.** A thread handles 4 consecutive rows. With a
  row-major base plane those 4 bytes are 16 B apart; block-major makes them
  contiguous, so one `uchar4` load per plane per K-iteration replaces four
  scalar loads. A whole threadgroup's 64 rows for one block occupy one 64 B
  cache line.
* **Delta load width.** A thread's 4 columns are 4 consecutive nibbles = one
  naturally aligned `ushort` at byte `R*1024 + 64b + 2*lane`.
* **Payload load width.** One naturally aligned `uchar4` at `R*2048 + 128b +
  4*lane`.
* **Escape channel with zero extra bytes.** When a block escapes, `base ==
  0xFF` and the block's 128 delta nibbles (64 B) are unused. The packer
  **replicates the 16-bit escape slot index into all 32 `ushort`s of that
  block's delta region**, so the `ushort` the thread already loaded *is* the
  slot index. The escape read is then one `vec<bfloat,4>` from `bexpEscape` —
  the same load width as stock. No index plane, no extra load, no extra byte.
  A 16-bit slot supports 65,536 escaped blocks; the packer declines to stock if
  `nEsc >= 65535`.
* **Branch uniformity.** `base` depends on `(R, b)` only, and every lane of a
  simdgroup shares `R` and `b`. The escape branch is therefore
  simdgroup-uniform: no divergence, only a rare taken branch (0.65 % / 0.67 %
  of `(row, block)` pairs).
* **`values_per_thread` stays 4.** Widening it would reorder the
  `simd_shuffle_down` reduction tree and change the float accumulation order,
  which is a correctness change, not an optimisation.

### 1.3 Down planes (rung S2b), `B = row (8192), d = 6, m = 7`

The census is unambiguous that `down_proj` cannot use a small block: at
`B = 128, d = 5` it escapes on 76 % of blocks. The only escape-free
configuration is one base per row with a 6-bit delta. A 6-bit field is packed
as a 4-bit plane plus a 2-bit plane so both loads stay naturally aligned;
packing 4 weights into 3 bytes would be unaligned and padding to 8 bits would
erase the entire saving.

Let `R in [0, 2048)`, `c in [0, 8192)`. The stock kernel has `blocks = 64`,
thread `lane` reads columns `128b + 4*lane .. +3`.

| plane | dtype | elements | index of weight `(R, c)` | bytes |
|---|---|---|---|---|
| `bexpPayload` | `uint8` | `2048 * 8192` | `R*8192 + c` | 16,777,216 |
| `bexpDeltaLo` | `uint8` | `2048 * 4096` | byte `R*4096 + c/2`, nibble `c&1`, holds `delta & 0xF` | 8,388,608 |
| `bexpDeltaHi` | `uint8` | `2048 * 2048` | byte `R*2048 + c/4`, field `c&3` at bits `2*(c&3)`, holds `delta >> 4` | 4,194,304 |
| `bexpBase` | `uint8` | `2048` | `R` | 2,048 |

Total `29,362,176 B`, reproducing the census figure exactly.

* Per-thread loads per K-iteration per row: one `uchar4` (payload, 4 B
  aligned), one `ushort` (lo, 2 B aligned), one `uchar` (hi).
* `base` is per row, so it is hoisted **entirely out of the 64-iteration block
  loop** — 4 scalar loads per thread for the whole kernel.
* **No escape branch exists in the down kernel.** The packer requires
  `nEsc == 0`; if any row escapes it logs and declines to stock BF16 for
  `down_proj`, which degrades S2b to S2a rather than to an incorrect result.

### 1.4 Byte totals

| state | gate | up | down | total bytes/step |
|---|---|---|---|---|
| base | 33,554,432 | 33,554,432 | 33,554,432 | 100,663,296 |
| S2a | 25,516,544 | 25,521,408 | 33,554,432 | 84,592,384 |
| S2b | 25,516,544 | 25,521,408 | 29,362,176 | 80,400,128 |

### 1.5 Build-time certificate (preregistered, not optional)

The packer runs entirely in MLX array ops (no Swift scalar loop over 33.5 M
weights) and, before the compact planes are retained, **decodes every plane
back and compares to the source tensor**. Retention happens only if:

1. `max(abs(decoded - source)) == 0` and the bit patterns are identical;
2. the measured escape counts are within 2× of the census
   (gate 858, up 877, down 0);
3. `base != 0xFF` for every non-escaped block;
4. down escapes `== 0`.

Any failure logs through the existing `lagunaNarrowScaleLog.note(...)` channel
and **declines to stock** for that tensor. This mirrors the shipped
`lagunaLaneMajorNVFP4ScaleBank` idiom in
`LagunaRuntimeWeights.swift:~866-945`.

---

## 2. Added instruction count per K-iteration per thread

### 2.1 The budget being spent against

The only measured ALU-headroom curve this campaign owns is PR #496
(`research/r93-runs/RESULTS.md` §10.8–10.10, §11.2). It was measured on **one
kernel** — the routed gather-GEMM
`laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2`
(`LagunaRuntimeModel.swift:7916`) — in units of **4 fma per K-iteration per
thread**, and it found a hinge, not a line:

| host | below-knee slope | above-knee slope | convexity | knee |
|---|---|---|---|---|
| M5 | 1.1657 µs/unit (t = +1.37, n.s.) | 8.0696 µs/unit (t = +15.8) | 6.92× | in (24, 64] units |
| M4 Pro | 7.2662 µs/unit (t = +41.5) | 14.5471 µs/unit | 2.00× | in (24, 64] units |

The knee interval `(24, 64]` units is **`(96, 256]` added fma-equivalents per
K-iteration per thread**. "≈96" is the *conservative lower edge* of that
interval, not a measured threshold.

That report states plainly that reusing this curve on a different kernel is
unlicensed extrapolation, and that block-exponent schemes must be *quoted with
their added instruction count per K-iteration so this can be checked*. The
numbers below are that quote. They are a disclosure, not a pass certificate.

### 2.2 Gate/up (S2a) — 32 weights per K-iteration per thread

Stock per K-iteration per thread: 4 rows × 2 planes × 4 values = **32 weights,
32 fma**, from 8 `vec<bfloat,4>` loads.

Compact inner sequence, per weight (`bs = ushort(base) << 8`, hoisted per
row-plane; `dn` the 4-nibble `ushort`; `p4` the payload `uchar4`):

```
r    = bs + ((dn << k) & 0x0F00) + ushort(p4[i]);   // shift, and, add, add
bits = (r >> 1) | (r << 15);                        // shr, shl, or
```

| item | ops |
|---|---|
| nibble align (shift + mask) | 2 |
| add base, add payload | 2 |
| rotate right by 1 | 3 |
| **per weight** | **7** |
| × 32 weights | 224 |
| `bs` hoist (8 shifts) | 8 |
| escape compare/branch (8 uniform tests) | 8 |
| **added integer ops per K-iteration per thread** | **≈240** |

Load count per K-iteration per thread changes from 8 × 8 B to 8 × 4 B
(payload) + 8 × 2 B (delta) + 2 × 4 B (base) = 18 loads of 56 B, versus 8 loads
of 64 B. Instruction issue for loads therefore also rises, by 10.

**≈240 added ops sits at the top of the `(96, 256]` knee interval.** On the
below-knee M5 slope this would be free; on the above-knee M5 slope
(8.07 µs/unit, 60 units) it would cost far more than the 60.3 µs the byte
saving is worth. This is the single largest risk in the experiment and is the
reason the go/no-go bar below is written in terms of *conversion efficiency*
rather than a bare sign test: the experiment is designed to be informative
whichever side of the knee the kernel lands on.

A same-side sanity check: 240 ops × 32 threads/simd × ... expressed
end-to-end, the gate/up kernel issues 8192 rows/64 × 512 threads × 16
K-iterations ≈ 1.07 M thread-K-iterations, so ≈257 M added integer ops per
step. At an M4-class integer issue rate the added ALU is of the order of tens
of µs against ≈192 µs of post-compaction memory time for this kernel — hideable
in principle, but only if the kernel is genuinely memory-bound and the added
ops overlap. That "in principle" is exactly what the ladder measures.

### 2.3 Down (S2b) — 16 weights per K-iteration per thread

Stock per K-iteration per thread: 4 rows × 4 values = **16 weights, 16 fma**,
from 4 `vec<bfloat,4>` loads.

```
r    = bs + ((dlo << k) & 0x0F00) + ((ushort(dhi) << j) & 0x3000) + p4[i];
bits = (r >> 1) | (r << 15);
```

| item | ops |
|---|---|
| lo nibble align (shift + mask) | 2 |
| hi 2-bit align (shift + mask) | 2 |
| three adds | 3 |
| rotate right by 1 | 3 |
| **per weight** | **10** |
| × 16 weights | 160 |
| `bs` hoist | 0 (outside the block loop; `base` is per row) |
| **added integer ops per K-iteration per thread** | **≈160** |

Loads change from 4 × 8 B to 4 × 4 B + 4 × 2 B + 4 × 1 B = 12 loads of 28 B
versus 4 loads of 32 B.

≈160 added ops is inside the `(96, 256]` knee interval but below the gate/up
figure, and the down kernel has no escape branch, so S2b's incremental rung is
the cheaper of the two per byte saved.

### 2.4 Rungs, restated against the budget

| rung | weights / K-iter / thread | added ops / K-iter / thread | vs conservative 96 | vs upper knee 256 |
|---|---|---|---|---|
| S2a gate/up | 32 | ≈240 | 2.5× over | 0.94× under |
| S2b down | 16 | ≈160 | 1.7× over | 0.63× under |

---

## 3. Ladder design

**Name: three-state blocked randomised within-run ladder with a switching-free
`perrun` companion.** This is the R93-B Stage 3 rig
(`research/fern_r93_nested_probe.py`, `research/fern_r93_nested_session.sh`,
`research/fern_r93_ladder.py`, `research/fern_r93_perrun.py`) re-pointed from a
glue-depth knob to a rung knob.

### 3.1 Why not `--local-iterate`

Rule 56 and the R93-B power result: the rig's reported SE is ≈1.34 µs/step at
22 min with n ≈ 1742 blocks, while a single `--local-iterate` receipt on M4
resolves ≈80 µs/step at best. S2a's predicted effect is **60.3 µs/step**, below
that single-receipt bar. `--local-iterate` medians are therefore **not** an
admissible ranking instrument for this experiment and will not be quoted as
one. `--local-iterate` is used only to produce the scored worker build.

### 3.2 Instrument

A research-only patch `research/fern-r97-rung-ladder.patch` adds a live rung
control in the exact R93-B shape: `DARKBLOOM_R97_RUNG_MAP` names a 4-byte file
mmap'd once, whose little-endian `Int32` is read on every single-token decode
forward and selects the layer-0 dense MLP rung:

```
0 -> stock BF16 gate/up + stock BF16 down          (base)
1 -> compact gate/up    + stock BF16 down          (S2a)
2 -> compact gate/up    + compact down             (S2b)
```

`DARKBLOOM_R97_RUNG` is the static fallback used when the map is unset. Both
the compact and the stock planes are resident for the whole session so that
switching costs nothing but a branch; **resident bytes are therefore not the
metric — bytes *read per step* is**, and that is what the census figures in
§1.4 count.

The patch header carries the base SHA, the exact re-apply line, the knob
documentation, and a relocation warning, per the standing instrument contract.
The shipped (submitted) code selects the rung from two ordinary env flags in
the existing `ProcessInfo...["NAME"] != "0"` idiom and contains no mmap.

### 3.3 Blocked randomised ladder (the RANKING estimator)

| parameter | value |
|---|---|
| schedule | `rand:0,1,2` |
| block length | 6 steps (each rung twice per block, freshly permuted) |
| processes `P` | 12 |
| runs per process `R` | 9 |
| steps per run `S` | 248 |
| warmup runs | 1 (discarded) |
| dropped steps per run | 24 |
| placebo every | 8 |
| thermal gate | `GATE_C=40` before every process |
| seed | 97 |
| analyser | `research/fern_r93_ladder.py --block 6 --drop-steps 24 --mad-mult 8 --bootstrap 4000 --seed 97` |

Estimator: block-paired mean difference of each rung against rung 0. SE from
the 3-level nested bootstrap (process → run → block). Block-level censoring at
median + 8 · MAD · 1.4826. Hodges–Lehmann, origin slope, quadratic, hinge and
carryover diagnostics are reported alongside but the **preregistered primary
statistic is the block-paired mean difference with its 95 % bootstrap CI**.

The placebo arm (blocks whose rungs are all 0) must be consistent with zero;
a placebo whose CI excludes 0 invalidates the session and it is rerun.

### 3.4 Switching-free companion (the ABSOLUTE estimator)

`SCHEDULE=perrun:0,1,2` holds the rung constant for a whole `decode_begin` run
and alternates only between runs, so it shares no per-step switching artefact
with the ladder. Analysed with `research/fern_r93_perrun.py --label-contains
perrun` as two adjacent-run pairings, `--lo 0 --hi 1` and `--lo 0 --hi 2`. If
the analyser rejects a 3-level `perrun` file, two separate two-level sessions
(`perrun:0,1` and `perrun:0,2`) are run instead; that substitution is a
mechanical accommodation of the tool and is recorded, not a design change.

Session parameters: `P=8 R=8 S=248 WARMUP_RUNS=1 GATE_C=40 SEED=97`.

**Rule 56 is honoured literally: the blocked ladder number is quoted for
RANKING, the `perrun` number is quoted for the ABSOLUTE saving. The two designs
are never averaged.** If they disagree in sign, or if the ladder estimate lies
outside the `perrun` CI, the result is reported as inconclusive with both
numbers shown.

### 3.5 Reported quantities

For each of S2a and S2b: block-paired mean difference vs base (µs/step) with
95 % CI; `perrun` paired difference with 95 % CI; census bytes/step; conversion
efficiency = (measured µs saved) / (predicted µs saved).

---

## 4. Predictions

The µs predictions are the census's M4 bandwidth model, which prices a byte
saved at the measured achieved dense-stream bandwidth (≈266 GB/s); the score
percentages are that model's decode-weighted conversion.

| quantity | S2a | S2b |
|---|---|---|
| bytes/step | 84,592,384 | 80,400,128 |
| bytes removed/step | 16,070,912 | 20,263,168 |
| MB removed/step | 16.071 | 20.263 |
| predicted score gain | 0.2446 % | 0.3085 % |
| predicted µs/step saved | 60.3 | 76.1 |

These are **pure-bandwidth predictions with zero ALU cost assumed**. §2 shows
the added ALU is not obviously zero, so the honest prior is that measured
savings land *below* these numbers. Conversion efficiency is the statistic that
carries the finding.

Escape rates predicted from the census and to be confirmed at load time:

| tensor | config | escaped blocks | of |
|---|---|---|---|
| `gate_proj` | B=128, d=4 | 858 | 131,072 |
| `up_proj` | B=128, d=4 | 877 | 131,072 |
| `down_proj` | B=row, d=6 | 0 | 2,048 |

---

## 5. Go / no-go bar

The assignment's suggested bar is adopted **unchanged and not loosened**.

### GO (all must hold)

1. **Bytes.** S2b removes ≥ 19.0 MB/step, verified by the census arithmetic in
   §1.4 *and* by the packer's measured plane sizes and escape counts at load
   time.
2. **Effect.** The blocked ladder shows S2b faster than base by ≥ 55 µs/step
   with a 95 % CI that excludes 0.
3. **Conversion efficiency.** measured µs saved / 76.1 µs ≥ 0.72 for S2b.
4. **Correctness.** `max_abs_diff = 0` on the 64-step drift tripwire;
   `research/run_upstream_equivalence.sh` green with a verified nonzero test
   count; identical single token-stream hash for base, S2a and S2b.
5. **Budget.** Editable-surface growth ≤ 60,000 B against
   `b78e7cdb80b5ae5f1cb1fdd39803322fb283ae5e`, with
   `senpai/check-editable-budget.sh` output reported before and after.

### NO-GO

* The 95 % CI on the S2b ladder difference cannot exclude 0, **or**
* conversion efficiency < 0.5.

Efficiency below 0.5 is **not** a null result. It is a publishable measurement
that the layer-0 dense stream is not purely bandwidth-limited at decode, i.e.
that this kernel sits above the ALU knee, and it retires the whole family of
"trade ALU for bytes" schemes on this block. It is reported as a finding with
the §2 instruction counts attached, not as a failed attempt.

### Stopping rule

Stop when **both** S2a and S2b have a ladder number with a CI, **or** when a
correctness gate fails and the failure is localised to a named plane or kernel.

**Early stop:** if S2a alone converts at efficiency < 0.5, stop there. Do not
build S2b. Report the negative with the bandwidth diagnosis, because a gate/up
rung that cannot convert 16 MB/step makes a 4 MB/step down rung uninformative.

### Explicitly out of scope

* R2 (down compacted on the output axis, `B=32, d=4`, 742 escapes).
* Any change to `values_per_thread`, the reduction tree, the epilogue, or the
  accumulation order.
* Any precision change. This scheme is lossless by construction; the accepted
  attention quantization envelope is not touched.
