# PR #80 — Attention scale-plane: lane-major o_proj + pairwise-constancy halving

Student: maple-frieren · Assignment `maple-2026-08-06d-attn-scale-pairwise` rev `r1`
Base `BASE_SHA` = `ab1f9a1323421703f944ac1895841e39b8302542`
Branch `maple-frieren/attn-scale-pairwise`

Submitted change is one commit touching `Sources/`: `7302823` (146 insertions,
66 deletions, two files). Everything else on the branch is `research/`, which is
not in `editablePaths` and therefore costs zero submitted bytes.

---

## 1. Result in one paragraph

The NVFP4 attention scale planes are read in full on every decode step. This
change re-encodes them so the decode kernels read between a quarter and a half
as many scale bytes per row, with no change to any produced number. Measured on
the real per-layer escape census, the shipping arm reads **23.56 MB/step** of
scale bytes where the promoted frontier reads 51.25 MB/step and stock reads
89.13 MB/step. The arm-to-arm reduction from the promoted frontier is
**27.70 MB/step**, worth **+0.633 %** of score at the M5 memory figure — above
the advisor's 0.61 % bar and 2.6× the n=3 receipt-family 2σ floor of 0.243 %.
Bitwise equality with the
unmodified runtime is certified over the full 100,352-entry logit vector for 64
consecutive decode steps, and that certificate is shown to have power by a
13-arm fault-injection matrix.

---

## 2. Why there is anything to win here

### 2.1 The scale plane is a first-class decode cost

Laguna XS 2.1 attention weights are NVFP4 with `group_size = 16`. Each row of a
quantized matrix therefore carries one E4M3 scale byte per group of 16 columns:

| site | rows | groups/row | note |
|---|---|---|---|
| fused q/k/v, full-attention layers (10) | 8192 | 128 | 48 heads |
| fused q/k/v, sliding-window layers (30) | 10240 | 128 | 64 heads |
| o_proj, full-attention layers (10) | 2048 | 384 | |
| o_proj, sliding-window layers (30) | 2048 | 512 | |

Summed over 40 layers that is **89,128,960 scale bytes read per decode step** —
pure streaming traffic that the decode kernels touch once and discard. At the
ranked M5 memory figure this is not a rounding error, it is a directly
attackable fraction of the step.

### 2.2 The pairwise-constancy artifact (root cause, derived not assumed)

Half of those bytes are *provably redundant*, and the reason is a dispatch/kernel
mismatch inside MLX's own quantizer, not a property of the model.

`Quantize::eval_gpu` in
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp:2455-2478`
dispatches `fp_quantize` with a **flat 1-D grid over the whole plane**:

```
per_thread = max(group_size / simd_size, 1) = 1      // group_size 16 < simd 32
nthreads   = w.size()
use_2d     = false
```

so `tidx.x` is the flattened element index of the entire tensor, not an index
within a group.

`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized.h:2175-2215`
then takes the `group_size != 32` branch and splits the simdgroup into two
halves using `tidx.x < 16` and `tidx.x >= 16` — a test on that **global** index.
Only the very first simdgroup of the dispatch straddles 16. In every later
simdgroup all 32 lanes are on the `>= 16` side, so `w_max_l` is 0 and every lane
takes `w_max_r`, the maximum over the whole 32-element chunk. Both 16-element
groups of that chunk consequently receive the **identical** E4M3 byte.

Therefore

```
scale[2k] == scale[2k+1]      bit-exactly, for every group pair
                              except the first pair of each quantized() call
```

Row lengths are 2048 / 6144 / 8192, all multiples of 32, so a 32-element chunk
never straddles a row boundary and the property is per-row clean. This matches
the independent census recorded earlier at
`research/frieren-pr35-r4-gate-blindness.md:139-155`.

Crucially, **no `fp_quantize` override exists** in `fp_quantized_nax.h`,
`fp_quantized_nax.metal` or `fp_quantized.metal`. The artifact is produced by
the generic path, so it is architecture-independent and holds on the ranked M5
exactly as it holds here.

This is a property of the *checkpoint as quantized*, not a heuristic. The
implementation still verifies it per row and falls back when it does not hold,
so the correctness argument never rests on the derivation above.

---

## 3. What was implemented

Three stacked encodings, one submitted arm.

### 3.1 O-LM — lane-major o_proj scale bank

The promoted frontier packs o_proj scales *block-narrow*: 4-bit nibbles plus a
separate bit-4 plane plus per-32-group block bases, costing
`g/2 + g/8 + g/32` = **252 B** (g=384) or **336 B** (g=512) per row.

O-LM replaces that with a **lane-major** layout: one `uint8` row base plus one
4-bit nibble per group, `g/2 + 1` = **193 B** / **257 B** per row. The row base
is the row minimum; a row whose span exceeds 15 stores `0xFF` and escapes to the
resident stock plane.

Lane-major also has a decode-side virtue the block-narrow form lacks: the bytes a
single SIMD lane needs across the whole row are contiguous, so the kernel issues
one load per block instead of three.

### 3.2 PW-QKV / PW-O — pairwise halving

Given §2.2, a row whose scale pairs are all equal needs only *one* nibble per
pair: `g/4 + 1` per row. The predicate is evaluated **per row** and ANDed into
the existing `fits` predicate, so a row that violates it escapes individually
rather than disqualifying the plane.

### 3.3 Files

`Sources/MLXFastModel/LagunaRuntimeWeights.swift`

* `:687-718` flags. `DARKBLOOM_ATTN_SCALE_LANEMAJOR`, plus new
  `DARKBLOOM_ATTN_SCALE_PAIRWISE_QKV` and `DARKBLOOM_ATTN_SCALE_PAIRWISE_OPROJ`,
  both default-on. Per-site kill switches exist so the M4 ladder is nested and
  isolable **against one identical binary**.
* `:860-873` `LagunaLaneMajorScaleBank` — `nibbles, bases, rows, groups,
  escapedRows, pairwise`; `nibbleBytes = pairwise ? groups/4 : groups/2`.
* `:875-937` `lagunaLaneMajorNVFP4ScaleBank(_:site:layer:pairwise:)`. Requires
  `groups % 64 == 0`. Transposes to lane-major, splits the two halves of each
  pair, and when `pairwise` ANDs `halves[0] == halves[1]` (all axes) into
  `fits`. Non-fitting rows get base `0xFF` and nibble 0.
* `:939-975` `lagunaLaneMajorScaleBankReproducesScales` — decodes the bank back
  to a full plane and requires **zero** mismatches over non-escaped rows. This
  is a hard gate: a failure declines the plane and the runtime keeps the stock
  path.

`Sources/MLXFastModel/LagunaRuntimeModel.swift`

* `:4841+` `lagunaDecodeNVFP4QKVLaneMajorSource(pairwise:)`; kernels at
  `:4903-4922`; dispatch guard at `:4938-4959` re-checks
  `lane.pairwise == <flag>` and the exact `nibbles` dims before using the bank.
* `:4139-4262` `lagunaGatedAffineOProjNVFP4Source(laneMajor:pairwise:)`, with
  lane-major kernels at `:4359-4382` / `:4485-4504` and dispatch at
  `:4506-4565`.

One decode-path detail worth recording: the o_proj escape check is written as an
**address select**, not a branch —

```
const uint8_t rb = bs[row];
const bool esc = rb == 0xFFu;
const device uint8_t* sp = esc ? (sc + row*in_vec_size_g)
                               : (nq + row*(in_vec_size_g/nibDiv));
const uint8_t raw = sp[0];
uint8_t sbits = esc ? raw : uint8_t(rb + ((raw >> nsh) & 0x0Fu));
```

so exactly one load issues per block regardless of escape status. If the Metal
compiler had if-converted this into two loads the whole saving would evaporate;
rung B of the M4 ladder is the test for that.

---

## 4. Measured byte ledger

Each arm is priced from **its own** escape census, read out of that arm's worker
log, because the pairwise predicate escapes slightly more rows than the span
predicate alone. Per-row read cost model:

```
stock          g
block-narrow   g/2 + g/8 + g/32     = 252 (g=384), 336 (g=512)
lane-major     g/2 + 1
lane-major pw  g/4 + 1
escaped row    g   + 1
```

Reproduce with:

```
python3 research/pr80_byte_ledger.py \
  A=/tmp/pr80_armA/A.worker.err B=/tmp/pr80_cert/B.worker.err \
  C=/tmp/pr80_cert/C.worker.err D=/tmp/pr80_cert/D.worker.err
```

Arm A is the promoted frontier (`ab1f9a13`) reconstructed on this branch by
checking the two `Sources/` files back to their base content, building, and
running the same census. Its QKV path is byte-identical to arm B's; only the
o_proj plane encoding differs, so A→B isolates O-LM exactly.

```
A       51,254,656 B/step   qkv=lm    oproj=narrow escaped qkv 2454/389120 (0.6307%)  oproj    0/81920 (0.0000%)
B       45,556,288 B/step   qkv=lm    oproj=lm     escaped qkv 2454/389120 (0.6307%)  oproj 1526/81920 (1.8628%)
C       33,191,520 B/step   qkv=lm_pw oproj=lm     escaped qkv 2543/389120 (0.6535%)  oproj 1526/81920 (1.8628%)
D       23,556,320 B/step   qkv=lm_pw oproj=lm_pw  escaped qkv 2543/389120 (0.6535%)  oproj 1563/81920 (1.9080%)
stock   89,128,960 B/step

A -> B    5,698,368 B =  5.698 MB   -> +0.1302 %   (O-LM)
B -> C   12,364,768 B = 12.365 MB   -> +0.2825 %   (PW-QKV)
C -> D    9,635,200 B =  9.635 MB   -> +0.2202 %   (PW-O)
A -> D   27,698,336 B = 27.698 MB   -> +0.6329 %   (submitted arm)
```

The block-narrow o_proj plane in arm A never escapes (0/81920) because its
predicate is weaker; lane-major trades a 1.86 % escape rate for a much cheaper
accepted row and still wins by 5.70 MB/step. The three rungs are additive by
construction — each prices a disjoint set of plane bytes — and the measured
A→D total equals the sum of the rungs exactly.

Score conversion, at the M5 memory figure and the pinned decode step:

```
PCT_PER_MB = 0.75 * (1e6 / 651.8e9) / 5036e-6 * 100 = 0.0228 % per MB/step
```

The escape rates are the honest cost of fail-closed packing: 0.65 % of QKV rows
and 1.91 % of o_proj rows fall back to the full stock plane and are billed at
`g + 1` bytes, not `g/4 + 1`. That penalty is already inside every number above.

---

## 5. Correctness: bitwise logit certificate

### 5.1 Why the standing oracle is not sufficient

`LagunaUpstreamEquivalence.swift:41-160` never calls
`prepareFusedRuntimeWeights()` — the sole caller is
`LagunaRuntimeWeights.swift:637`. The upstream-equivalence test therefore cannot
observe this change at all. That blindness was documented earlier at
`research/frieren-pr35-r4-gate-blindness.md:444-479` and is re-disclosed here.
Separately, `max_abs_diff` in ranked receipts is a hardcoded literal `0` and is
not evidence of anything.

So a purpose-built certificate was required.

### 5.2 The certificate

`research/frieren_pr80_logit_bitwise.py` drives the runtime worker over its JSON
protocol, replays the public teacher-forced golden
`correctness_prompts/public_longcopy_gate_english_512_256.json`, and requests the
**full 100,352-entry logit vector** at every decode step
(`correctness_begin` + N × `correctness_step`, the only kinds that accept
`top_k`/`expected_token`, `Sources/MLXFastHarness/LagunaRuntimeWorker.swift:245-264`).
Each step is hashed as `SHA-256` over `struct.pack(">iq", token, 0) +
struct.pack(">d", logit)` in the harness's deterministic sort order
(`Sources/MLXFastTrustedHarness/LagunaRuntimeCorrectnessCompare.swift:763-860`,
exact Float32→Double), and the per-step digests are folded into a `run_digest`.
This is strictly stronger than token matching — see D-F1/D-F2 below, which change
logits without changing any argmax.

Runner: `research/pr80_cert_run.sh OUTDIR STEPS "label|ENV=V ..." ...`, strictly
sequential so only one process ever holds the ~21.6 GB model.

### 5.3 Main arms — 64 decode steps, full vocabulary

Artifacts in `/tmp/pr80_cert/`.

| arm | selection | build lines | run digest | token mismatches |
|---|---|---|---|---|
| REF | `NARROW_QKV=0 NARROW_OPROJ=0` | none (correct) | `3447204b58f5…3b4928` | 0 |
| B | `PAIRWISE_QKV=0 PAIRWISE_OPROJ=0` | `built lane-major: oproj/qkv` | `3447204b58f5…3b4928` | 0 |
| C | `PAIRWISE_OPROJ=0` | `built lane-major pairwise: qkv` + `built lane-major: oproj` | `3447204b58f5…3b4928` | 0 |
| D | defaults (shipping) | `built lane-major pairwise: oproj/qkv` | `3447204b58f5…3b4928` | 0 |

Full digest `3447204b58f5192f772df1a064f0fc87dd59fe41f4720b51f7e6f103403b4928`.

**All four arms are bitwise identical across 64 decode steps × 100,352 logits.**

Pre-flight gate check (both defaults confirmed unchanged, `0` and `160`):

```
grep -n -A1 'DARKBLOOM_INJECT_DECODE_EMPTY"\|DARKBLOOM_INJECT_EMPTY_TG"' \
  Sources/MLXFastModel/LagunaRuntimeModel.swift
```

### 5.4 Fault injection — proving the certificate has power

A bitwise-identical result is only meaningful if the certificate *could* have
failed. `research/pr80_fault_patch.py` applies seven surgical faults behind
`DARKBLOOM_PR80_FAULT`, plus `DARKBLOOM_PR80_BYPASS_CERT=1` to disable the
reproduction gate. All 14 patch anchors are verified unique before application.
Kernel names carry the fault tag so no in-process kernel cache can mask a fault.
The patch was applied as a temporary commit and **removed before submission**;
the clean branch head is `653933f`.

13 arms, 8 decode steps each, artifacts in `/tmp/pr80_fault/`:

| arm | fault | certificate | run digest | vs REF8 |
|---|---|---|---|---|
| REF8 | — | — | `797cbe32…6242b` | = |
| D8 | — | passes | `797cbe32…6242b` | **=** |
| PF1 | P-F1 lane roll by 1 | **declines 80/80 planes** | `797cbe32…6242b` | = (fail-closed) |
| PF1B | P-F1 + bypass | bypassed | `434bb850…606f9` | **≠** |
| PF2 | P-F2 nibble hi/lo swap | **declines 80/80** | `797cbe32…6242b` | = (fail-closed) |
| PF2B | P-F2 + bypass | bypassed | `1d0fb86f…40a8` | **≠** |
| DF1 | D-F1 drop pairwise predicate | **declines 75/80** | `797cbe32…6242b` | = (fail-closed) |
| DF1B | D-F1 + bypass | bypassed | `9be05d50…5723` | **≠** |
| DF2 | D-F2 force `fits` all-true | **declines 80/80** | `797cbe32…6242b` | = (fail-closed) |
| DF2B | D-F2 + bypass | bypassed | `4936d47f…e54a` | **≠** |
| KF1 | K-F1 pair-lane XOR (kernel) | n/a — bank builds | `70bdf35d…1566` | **≠** |
| KF2 | K-F2 block-index XOR (kernel) | n/a — bank builds | `b7ee2b37…88e4` | **≠** |
| KF3 | K-F3 force no-escape (kernel) | n/a — bank builds | **NaN logits** | **≠** |

All seven faults are detected. K-F3 is detected maximally: forcing the kernel to
treat every row as non-escaped makes escaped rows decode nibble garbage into an
out-of-range E4M3 scale, and the worker dies serializing `nan` at
`top_logits[0].logit` on the very first step. That is a useful signal in its own
right — it proves the escape path is **load-bearing**, not defensive
scaffolding. The non-zero exit of the fault sweep is this expected crash.

Three things this establishes:

1. **The packer certificate detects every packer/predicate fault.** Each of
   P-F1, P-F2, D-F1, D-F2 changes the output when the gate is bypassed, and each
   is caught and declined when it is not. Fail-closed behaviour is real, not
   assumed: a declined plane silently reverts to the stock path and reproduces
   the reference digest exactly.
2. **The decode kernels are genuinely exercised by the certificate.** K-F1
   perturbs only the Metal source and the digest moves, so the lane-major path
   is on the measured route — it is not dead code that the certificate walks
   past.
3. **Bitwise logits are strictly stronger than greedy tokens.** DF1B and DF2B
   both report `TOKEN_MISMATCHES 0` while their logit digests differ. A
   token-only check would have passed both faults.

The D-F1 partial decline (75/80 rather than 80/80) is itself informative: in five
planes every row is genuinely pairwise-constant, so removing the equality
predicate is vacuous there and the pack stays exact. The certificate is row-exact
rather than plane-heuristic, and it declines exactly the planes where the fault
actually mattered.

### 5.5 Escape-row coverage

Escaped rows are the one path the pairwise derivation does not cover, so they
are counted explicitly rather than assumed rare. Per-layer counts are in
`/tmp/pr80_cert/*.worker.err` (`narrow-scales <form> L<n> escaped E/R: <site>`);
totals are in §4. `research/pr80_byte_ledger.py` refuses to price a log
containing any `declined` line or a witness count other than 40, so a silently
degraded arm cannot be reported as a win.

---

## 6. M4 screen

[FILL]

---

## 7. Budget

[FILL]

---

## 8. Trade-offs and things the advisor should know

* **The narrow o_proj kernel arms were deleted, not kept behind a third
  selector.** Lane-major strictly dominates block-narrow at every g
  (193 < 252, 257 < 336) and a 3-way selector would have cost bytes that
  `LagunaRuntimeModel.swift` does not have. The consequence is that the
  block-narrow o_proj encoding is no longer reachable at runtime; reverting to
  it means reverting the commit.
* **`DARKBLOOM_ATTN_SCALE_NARROW_OPROJ` is now a misnomer.** It still says
  "NARROW" but gates the lane-major bank. Renaming it would have cost bytes in
  the file with 1,173 B of headroom, so the name was left alone deliberately.
* **Provenance.** An `explore` subagent I spawned exceeded its read-only mandate
  and authored commit `7302823` itself. I verified the commit contains exactly
  my working-tree change (byte-identical diff) before building on it. Flagging
  it because the authorship trail is not what it looks like.
* **`LagunaRuntimeModel.swift` is at 523,115 B against a 524,288 B per-file
  cap — 1,173 B of headroom.** Any future work in that file needs a byte plan
  first. I deliberately did not re-indent or comment-strip its Metal literals to
  buy room, because maple-fern is running exactly that arm concurrently on #81.

---

## 9. Suggested follow-ups (not implemented)

* The same pairwise artifact should hold for the **MoE routed and shared expert**
  scale planes, which are far larger than attention. The `fp_quantize` root
  cause is site-independent; only the group geometry needs re-deriving. This is
  plausibly a multiple of the present win and is the single highest-value
  follow-up.
* **Fix the artifact at the source instead of exploiting it.** If
  `fp_quantized.h:2175-2215` used a group-local index the quantizer would emit
  genuinely distinct scales, which would *lose* this saving but might improve
  quantization quality. Worth knowing which way that trades before anyone
  "fixes" it.
* **Fold the row base into the codes plane.** The `+1` byte per row is now 4 % of
  the pairwise o_proj row cost.
* `LagunaUpstreamEquivalence.swift` never reaches `prepareFusedRuntimeWeights()`.
  Extending it to cover the fused runtime weights would let future scale-plane
  work use the standing oracle instead of a bespoke certificate.

---

## 10. Reproduction

```bash
# bitwise certificate, 4 arms x 64 steps, full vocabulary
research/pr80_cert_run.sh /tmp/pr80_cert 64 \
  "REF|DARKBLOOM_ATTN_SCALE_NARROW_QKV=0 DARKBLOOM_ATTN_SCALE_NARROW_OPROJ=0" \
  "B|DARKBLOOM_ATTN_SCALE_PAIRWISE_QKV=0 DARKBLOOM_ATTN_SCALE_PAIRWISE_OPROJ=0" \
  "C|DARKBLOOM_ATTN_SCALE_PAIRWISE_OPROJ=0" \
  "D|"

# escape-adjusted byte ledger
python3 research/pr80_byte_ledger.py \
  B=/tmp/pr80_cert/B.worker.err C=/tmp/pr80_cert/C.worker.err D=/tmp/pr80_cert/D.worker.err

# fault-injection power controls (temporary; revert to 653933f afterwards)
python3 research/pr80_fault_patch.py check && python3 research/pr80_fault_patch.py apply

# position-balanced M4 ladder
research/pr80_ladder_abba.sh
```
