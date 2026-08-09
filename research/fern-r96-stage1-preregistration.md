# R96-C Stage 1 pre-registration — lossless repack of the layer-0 dense BF16 MLP

Student `maple-fern`, PR #513, assignment `maple-r96-c-bf16-lossless-compaction`,
revision `r96-c-rev1`, base `43036cd39dd3c795b117b099f0fe52767fbedbca`.

**Written and committed BEFORE any weight bit-pattern was read.** No histogram,
span, entropy, or mantissa statistic from `weights/` has been inspected at the
time of this commit. The only data-side facts used below are the safetensors
*headers* (dtype `BF16`, shapes `[8192,2048]`, `[8192,2048]`, `[2048,8192]`,
33,554,432 B each), which are metadata, not weight values.

## 0. Target, and one correction to the assignment

Layer 0 is the single dense MLP (layers 1–39 are sparse MoE). Its decode weight
stream is

```
fused gate+up  2 * 8192 * 2048 * 2 B = 67,108,864 B
down               2048 * 8192 * 2 B = 33,554,432 B
total                                = 100,663,296 B/step = 100.663 MB/step
N                                    = 50,331,648 weights at 16 bits
```

**Correction, verified in this checkout (not from data):** the assignment states
the decode path is "a plain MLX BF16 matmul" and that a compaction arm "must
supply its own decode GEMV kernel". That is false at this base. Two hand-written
decode GEMV kernels already exist and own this traffic:

- `laguna_dense_gate_up_swiglu_bf16_v1` — `Sources/MLXFastModel/LagunaRuntimeModel.swift:8581`
- `laguna_dense_down_residual_bf16_v1` — `Sources/MLXFastModel/LagunaRuntimeModel.swift:8674`
- call site `Sources/MLXFastModel/LagunaRuntimeLayers.swift:286-302`
  (`lagunaFusedDenseGateUpSwiGLUEnabled` / `lagunaFusedDenseDownResidualEnabled`,
  fused bank from `prepareFusedDenseGateUp()` `:122-139`).

Stage 2, if reached, is therefore an *edit* of two shipped kernels' load path,
not a new kernel from scratch. This lowers Stage 2 cost and it does not change
any Stage 1 bar below.

## 1. Admissibility claim (stated before the data, so it cannot be retrofitted)

`TASK.md:92-94` bars *re-quantization* of this MLP. This arm performs no
re-quantization: every scheme below re-encodes the **identical IEEE bf16 bit
pattern** of every weight and reconstructs it exactly, so the value fed to the
existing convert/FMA sequence is bitwise identical and the kernel's arithmetic
order is unchanged. Bit-exactness is a construction property, and D4 below is
its proof obligation. If D4 does not print exactly `0` mismatching weights, the
arm is dead regardless of byte savings.

## 2. The scheme family (fixed-width, no entropy coding, O(1) random access)

Every candidate is one point in a single family: **per-block uint8 exponent base
+ per-weight (sign, exponent delta, kept mantissa bits)**.

Parameters:

- `B` — block length along the reduction axis, `B in {32, 64, 128, row}`, where
  `row` = 2048 for gate/up and 8192 for down.
- `d` — exponent-delta width in bits, `d in {2,3,4,5}`.
- `m` — kept mantissa bits, `m in {7,6,5,4,3}`. `m < 7` is admissible **only if
  the census proves the low `7-m` mantissa bits are identically zero for every
  one of the 50,331,648 weights** — a truncation that drops a set bit is a
  precision change and is out of scope.

Bits per weight `p = 1 + d + m`. Reconstruction is pure ALU, no table, no second
dependent load:

```
w16 = (s << 15) | ((base + delta) << 7) | (mant << (7 - m))
```

with one delta code reserved for exact `+/-0` iff the census finds exact zeros.

Usable exponent span per block:

```
span_max(d) = 2^d - 1 - (1 if the tensor contains exact zeros else 0)
```

A block **escapes** iff `max_exp_nonzero - min_exp_nonzero > span_max(d)`.

## 3. D2 arithmetic, fixed in advance

Let `E_blk` = escaped blocks, `E_row` = rows containing at least one escaped
block, `n_blk = N / B`, `n_row` = 8192 + 8192 + 2048 = 18,432 rows.

**(a) block-granular escape, reserved-slot (primary; O(1) addressing, no index):**

```
net = N*p/8  +  n_blk*1  +  E_blk*B*2
```

**(b) row-granular escape, reserved-slot (the shipped NVFP4 sentinel idiom,
`LagunaRuntimeWeights.swift:886-940`, `const bool esc = rb == 0xFFu`):**

```
net = N*p/8  +  n_blk*1  +  E_row*rowlen*2
```

**(c) block-granular escape, compacted side plane + 4 B per-block offset
(reported for completeness only; adds an index the hot loop must read):**

```
net = N*p/8  +  n_blk*1  +  n_blk*4  +  E_blk*B*2  -  E_blk*B*p/8
```

Then, for every `(B,d,m)`:

```
saved_B   = 100,663,296 - net
saved_MB  = saved_B / 1e6
score_pct = saved_MB * 0.015224            # realised byte price, PR #110 ledger
us_M4     = saved_B / 266.3e9 * 1e6        # #498 DRAM model, marginal term
```

Padding: none of (a)/(b) needs any. All planes are separate and byte-aligned
(§5), so no `45 B`-style ragged block ever exists and there is no misalignment
term to add. If the chosen variant somehow needs padding, D2 is recomputed with
it before the bar is applied.

**Variant choice rule:** among variants that satisfy the GO bar, take the one
maximising `saved_B`; break ties toward (i) fewer planes, (ii) `1+m == 8` so the
sign+mantissa plane is exactly 1 B/weight, (iii) larger `B`, (iv) escape
design (a) or zero escapes over (b) over (c).

## 4. GO / NO-GO bar — final, pre-data

The best admissible variant must satisfy **all four**:

- **(a) Magnitude.** `saved_B >= 21,300,000 B/step` (>= 21.16 % of the family;
  >= 0.324 % score).
  *Why this number and not the suggested 25 %:* it is the measurability bar, not
  a wish. At the #498 M4 DRAM model, 21.3 MB = **79.98 µs/step**, which is the
  rule-40 M4 single-receipt detection bar (~80 µs/step). A saving we cannot
  attribute in one receipt on our own host must not be turned into a kernel.
  The bar has teeth. Worked example on the assignment's own headline format,
  `B=32, d=3, m=7` (`p = 11`): zero-escape net is
  `50,331,648*11/8 + 1,572,864 = 70,779,264` B, saving 29.88 MB; under escape
  design (a) an escaped block keeps its 45 B reserved slot and adds `32*2 = 64`
  raw bytes, so the bar `saved >= 21.3 MB` is lost once escaped blocks exceed
  `(29,884,032 - 21,300,000)/64 = 134,125` of the 1,572,864 blocks — an escape
  rate of **8.53 %**. Under design (b) an escaped 2048-wide gate/up row adds
  4096 B, so the bar is lost past ~2095 escaped rows of 18,432, and if escapes
  are *scattered* rather than clustered almost every row escapes and design (b)
  goes net-negative. Both thresholds are inside the plausible range for a
  trained Gaussian-like tensor, so this bar can and may fail.
- **(b) Addressing.** Zero escapes, or an escape structure served by design (a)
  or (b) above — i.e. a fixed-stride slot plus a two-way pointer select, no
  offset index and no variable-length block in the hot loop. Design (c) may only
  be selected if it *alone* clears (a) and its index traffic is included in
  `net`.
- **(c) Specials.** No Inf/NaN in any of the three tensors. Exact zeros and
  subnormals must be exactly representable by the chosen scheme (reserved
  delta code for `+/-0`; a subnormal forces its block to escape).
- **(d) Round-trip.** D4 prints exactly `0` mismatching weights over all
  50,331,648, and the SHA-256 of the reconstructed little-endian `uint16` buffer
  equals that of the original, per tensor.

## 5. D5 memory layout, fixed in advance

Three separate, independently coalesced planes per tensor (no ragged blocks, no
cross-cacheline block straddling, no padding):

| plane | size | alignment |
|---|---|---|
| `P` sign+mantissa, `1+m` bits/weight | `N*(1+m)/8` B | 1 B/weight when `m == 7`; else `(1+m)` bit-packed at 8-weight granularity so 8 weights occupy an exact byte count |
| `D` exponent deltas, `d` bits/weight | `N*d/8` B | `d in {2,4}` gives exact nibble/2-bit packing; 8 weights occupy `d` bytes |
| `H` per-block exponent base, 8 bits | `n_blk` B | 1 B/block, base sentinel `0xFF` marks escape |

A thread that owns 8 consecutive reduction-axis weights therefore issues one
aligned 8 B load from `P` (when `m == 7`), one aligned 4 B load from `D` (when
`d == 4`), and one broadcast byte from `H`. All three streams are sequential and
coalesced across the simdgroup, matching the existing 4-rows-per-simdgroup
`vec<bfloat,4>` pattern (`LagunaRuntimeModel.swift:8143-8180`, `:8239-8266`)
with `values_per_thread` widened to 8. For `p == 8` exactly (`d=4, m=3`) the
`P`/`D` planes collapse into a single 1 B/weight plane.

## 6. What I do for each outcome

- **PASS (all of 4a–4d):** log the D1–D5 deliverables and Stage-1 W&B metrics,
  write the chosen `(B,d,m)` and the packer/kernel design into the PR, then
  start Stage 2 (load-time packer in `LagunaRuntimeWeights.swift`, unpack in the
  two existing kernels, `DARKBLOOM_DENSE_PACKED_<variant>` env A/B, rule-39
  default-reachability grep, rule-33 kernel name suffix). If Stage 2 cannot
  finish inside the stopping rule, Stage 1 plus the written design is the
  terminal result.
- **FAIL on (a):** STOP at Stage 1. Submit the census as a terminal negative
  that prices and closes the family. No kernel.
- **FAIL on (b) only, (a) satisfied by design (c) alone:** report the index cost
  explicitly and STOP unless design (c) still clears (a) by >= 2x the 21.3 MB
  bar, in which case Stage 2 proceeds with (c) and the extra index stream named
  as a known risk.
- **FAIL on (c):** if Inf/NaN exist, STOP (the scheme cannot represent them
  without a wider escape). If only subnormals exist, treat their blocks as
  escapes and re-apply (a).
- **FAIL on (d):** hard stop, arm dead, bug reported.

## 7. Deliverables and W&B keys (fixed in advance)

D1 span histogram per tensor and pooled, for each `B`; D2 net-bytes table for
the full `(B,d,m)` grid under designs (a)/(b)/(c); D3 per-row escaped-block
count distribution p50/p90/p99/max; D4 round-trip identity + SHA-256; D5 the
layout note above, re-costed if padding is needed.

W&B project `wandb-applied-ai-team/mlxfast-maple`, primary metric
`dense_mlp_bytes_per_step` (start 100,663,296, lower better), plus
`stage1_escape_block_fraction`, `stage1_net_bytes_saved`,
`stage1_net_score_pct`, `roundtrip_mismatched_weights` (must be 0).

## 8. Rules I am binding myself to

Rule 24 one mechanism (the compaction; no geometry retune, no SwiGLU fusion, no
dispatch-shape change in this arm) · rule 33 per-variant kernel name suffix ·
rule 39 prove default reachability · rule 40 state the resolvable floor with
arithmetic and name the design · rule 43/44 `nat` ABBA for magnitude, SPLIT=1 is
attribution-only · rule 45 one token-stream hash across all timed slots · rule
51 run the numerical oracle but do not trust it for dispatch · rule 56 blocked
randomised ladder for ranking, `perrun` for absolute savings.
