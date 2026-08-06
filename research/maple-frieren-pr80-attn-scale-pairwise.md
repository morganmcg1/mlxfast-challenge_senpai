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
**27.70 MB/step**, worth **+0.633 %** of score at the M5 *peak* memory figure and
**+0.756 %** at the *effective* figure. Bitwise equality with the
unmodified runtime is certified over the full 100,352-entry logit vector for 64
consecutive decode steps, and that certificate is shown to have power by a
13-arm fault-injection matrix.

### 1.1 Where this sits against the receipt-resolvability floor

I want to be precise about this rather than pick the flattering denominator.
`CURRENT_RESEARCH_STATE.md:639-644` sets the bar for a ranked byte-trading arm at
**3σ = 42.6 µs/step**. Converting my measured 27.698 MB/step at the two published
memory figures:

| memory figure | predicted saving | vs 3σ = 42.6 µs | score % |
|---|---|---|---|
| 651.8 GB/s (peak, 107 % of nominal) | 42.50 µs/step | **2.99σ** | +0.633 % |
| 546.2 GB/s (effective) | 50.71 µs/step | **3.57σ** | +0.756 % |

So on the pessimistic denominator this arm lands *exactly on* the single-receipt
3σ floor, not comfortably above it; on the effective denominator it clears it by
19 %. The advisor's independent arithmetic (27.73 MB/step, +0.77 %) is the
effective-denominator row and agrees with my census to 0.1 %.

Two things push the true value toward the upper row rather than the lower. First,
the §6 M4 ladder measured an observed/predicted ratio of **1.13** across the whole
B→D stack, i.e. peak-bandwidth division *under*-predicts the real saving, which is
what an effective-bandwidth model predicts. Second, the three rungs are only
resolvable as a union: PW-QKV alone (+0.280 %) sits at the MDE, and PW-O (+0.218 %)
and O-LM (+0.135 %) are individually below it. That is why I ship the union and
make no per-rung ranked claim.

I am *not* claiming the 2.6×-headroom figure that comes from the 0.243 % floor at
`:2445`. That floor is defined for **two n=3 receipt families in one session**; a
single dispatched receipt does not get that averaging, so §0.5.8's 3σ is the bar
that actually applies to me.

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

### 4.1 The pairwise predicate is nearly free — and the residual is exactly the predicted one

Differencing the census arms separates the two predicates that share the escape
path. The lane-major base-range predicate is pre-existing; the pairwise
predicate is what this change adds.

| site | escapes without pairwise | escapes with pairwise | **marginal cost of pairwise** |
|---|---|---|---|
| fused q/k/v | 2454 (arm B) | 2543 (arm C) | **+89 rows** |
| o_proj | 1526 (arm C) | 1563 (arm D) | **+37 rows** |

The root-cause model in §2 predicts this number a priori. Exactly one group pair
per `quantized()` call is a genuine exception — the first simdgroup, the only one
where `tidx.x < 16` actually splits the halves. `q`, `k` and `v` are quantized
separately, so the upper bound is 3 rows/layer × 40 layers = **120** for fused
QKV and 1 × 40 = **40** for o_proj. Observed: 89 and 37. Both sit under the
bound, and the shortfall is accounted for by exception rows that were already
escaping on the base-range predicate and so cost nothing extra.

So the mechanism is not "most rows happen to be pairwise-constant". It is
"**every** row is pairwise-constant except one per quantized tensor, and that one
is a deterministic consequence of the dispatch geometry, not of the data". That
is why the saving is a structural 2× on the accepted plane rather than a
data-dependent average.

**This independently reproduces PR #72.** nezuko found the same artefact on the
routed MoE scale plane: 985,300,992 even-byte pairs, 99.999983 % equal, **exactly
168 exceptions — one per tensor, always at flat pair 0**, across 234 tensors
(`research/maple-nezuko-pr72-group32-scale-census.md`). Two students, two
disjoint weight planes, identical signature. The odd-index control in her census
(23.24 % mismatch) rules out the trivial explanation that these scales are just
smooth. Neither census can be a fixture artefact, and since no `fp_quantize`
override exists in `fp_quantized_nax.{h,metal}`, the property is
architecture-independent and holds on the ranked M5.

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

### 6.1 Design, and why it satisfies programme law §0.9.32

§0.9.32 withdrew fixed pre-registered no-harm bands and requires the bar to come
from a **measured same-session A/A**. The ladder was built to produce that bar as
a by-product rather than as a separate experiment.

`research/pr80_ladder_abba.sh` runs **one binary**. Arms are selected only by
`DARKBLOOM_*` environment, so there is no rebuild between arms and no code-layout
confound. Two positions of the same arm are therefore a genuine A/A: identical
bytes, identical kernels, identical session, identical host state. Each arm is
run four times, so the pooled within-arm standard deviation *is* this session's
measured noise floor.

Ordering is position-balanced — one discarded warm-up arm, then
`B C D | D C B | B C D | D C B`. Every arm's positions sum to 26 and every block
of three contains each arm once, so smooth thermal drift cancels to first order.
The recorded thermals confirm drift was real and was absorbed: CPU rose 37.5 °C →
42.6 °C over the first four arms and then held.

Arms, all on the shipping binary:

| arm | QKV plane | o_proj plane | scale bytes/step |
|---|---|---|---|
| B | lane-major | lane-major | 45.56 MB |
| C | lane-major + pairwise | lane-major | 33.19 MB |
| D | lane-major + pairwise | lane-major + pairwise | 23.56 MB (shipping) |

### 6.2 Result

```
bash research/pr80_ladder_abba.sh                  # 13 arms, 1200 steps each, ~13 min
python3 research/pr80_ladder_analyze.py /tmp/pr80_ladder.log
```

```
arm   n   mean ms   sd us  pos sum  positions
B     4    8.5966     6.8       26  8.6039 8.6008 8.5906 8.5911
C     4    8.5309     4.2       26  8.5356 8.5278 8.5331 8.5270
D     4    8.5010     4.8       26  8.5060 8.5033 8.4997 8.4949

measured same-session A/A floor (pooled within-arm sd): 5.4 us  (dof=9)
2-sigma bar on a single arm-to-arm delta: 10.7 us

delta       observed us  predicted us   ratio  verdict
B->C               65.7          47.5    1.38  resolved (2se=7.6)
C->D               29.9          37.0    0.81  resolved (2se=7.6)
B->D               95.6          84.6    1.13  resolved (2se=7.6)
```

**The measured A/A floor is 5.4 µs.** Every arm's four replicates fall inside a
17 µs band while the arms themselves separate by 30–96 µs. `B->D` is 95.6 µs
against a 3.8 µs standard error on the difference — a 25σ separation, and 11×
the A/A floor. This is the §0.9.32-compliant evidence: the bar was measured in
the same session, not asserted in advance.

For scale, tanjiro's null-change base↔base A/A in PR #81 §6.3 moved decode by
+0.460 % (≈ 39 µs at this step size). That is 7× my measured floor, which is
what §0.9.32 was minted to address — and it is still four times smaller than
this arm's B→D effect, so the conclusion survives even under his noisier
measurement regime.

### 6.3 Reading the observed/predicted ratio honestly

The aggregate ratio is **1.13**: the ladder saves slightly *more* time than
dividing the byte saving by the M4's 260.2 GB/s peak predicts. The two rungs
bracket 1.0 (1.38 and 0.81), so the per-rung ratios should not be
over-interpreted; only the aggregate is well determined.

The most likely explanation is the dull one: dividing by *peak* bandwidth
under-predicts the time a real streaming read costs, because achieved bandwidth
on this access pattern is below peak. If that is right, the same reasoning
applies to the M5 figure, and the score numbers in §4 — which all divide by the
M5 **peak** 651.8 GB/s — are conservative rather than optimistic. I am claiming
the byte-ledger numbers, not the 1.13-scaled ones.

### 6.4 What this screen does and does not cover

Covered: `B→D`, i.e. 22.00 MB/step of the submitted arm's 27.70 MB/step.

**Not covered: the `A→B` rung** (o_proj block-narrow → lane-major, 5.70 MB/step,
+0.130 %). Arm A is the promoted frontier and needs a *different binary*; a
mid-ladder rebuild is exactly the confound the single-binary design exists to
avoid. It is priced from the byte ledger only. It is also below the 0.278 %
receipt MDE on its own, which is why the arm ships as a union.

That gap is bounded rather than ignored. The advisor's standing rule is that an
M4 null is not a refutation but an M4 **regression** is, so what actually matters
is excluding a regression on the o_proj read path — specifically the escape
address-select, the one construct a Metal compiler could plausibly if-convert
into an unconditional double load. `research/pr80_oproj_abba.sh` closes that on
the same binary by substituting a reachable bound:

| arm | o_proj plane | bytes/step |
|---|---|---|
| S | stock (untouched) | 39.32 MB |
| B | lane-major | 20.11 MB |

Arm A's block-narrow plane sits strictly between S and B in bytes (252/336 B per
row against stock 384/512 and lane-major 193/257) and decodes from three planes
instead of two. If `S→B` resolves as a gain near the byte-model rate, the
lane-major o_proj read path is healthy and `A→B` being a regression is not
credible.

Also not covered: **prefill**. Decode on this runtime is 100 % custom Laguna MSL,
but the M4 Pro reports Apple GPU generation 16 and does not select the `_nax`
prefill kernels the ranked M5 uses, so no prefill claim is made from this host.
The change reduces bytes read in both phases and adds no work to either, and the
scale banks are built once outside the timed window.

```
S->B  19.215 MB -> 73.8 us/step predicted at 260.2 GB/s
```

### 6.5 The `S→B` o_proj rung: result

`research/pr80_oproj_abba.sh`, 9 arms (one discarded warm-up then `B S S B B S S B`,
positions counterbalanced to sum 18 each), 1200 steps per arm, same binary:

```
arm   n   mean ms   sd us  pos sum  positions
B     4    8.5957     4.1       18  8.5948 8.5975 8.6000 8.5905
S     4    8.6581     2.6       18  8.6569 8.6554 8.6586 8.6615

measured same-session A/A floor (pooled within-arm sd): 3.4 us  (dof=6)
2-sigma bar on a single arm-to-arm delta: 6.8 us

delta       observed us  predicted us   ratio  verdict
S->B               62.4          73.8    0.84  resolved (2se=4.8)
```

**The lane-major o_proj read path is a gain, not a regression.** 62.4 µs against a
2 se bar of 4.8 µs is 26σ. The arms separate completely: the *slowest* B position
(8.6000) is still 55.4 µs faster than the *fastest* S position (8.6554), so the
verdict does not depend on the summary statistic.

**It is not thermal.** CPU temperature was 42.4–42.7 °C for every S arm, and two of
the four B arms sat at 42.5–42.6 °C in the same band. Restricting to arms ≥ 42 °C
gives B = 8.5987 (n=2) vs S = 8.6581 (n=4), a **59.4 µs** contrast — the same
conclusion from a temperature-matched subset. The two extreme-temperature arms
(p01 at 40.2 °C, p08 at 38.1 °C) are both B and both fast, so dropping them makes
the estimate *more* conservative, not less.

**This closes the §6.4 gap.** The concern was never that `A→B` might be a null —
it was that the escape address-select in the o_proj read path could be
if-converted by the Metal compiler into an unconditional double load, turning a
byte saving into a byte *cost*. Arm S exercises the stock plane and arm B the
lane-major plane through that exact construct, and B wins at 84 % of the byte-model
rate. Arm A's block-narrow plane sits strictly between S and B in bytes, so `A→B`
being a regression is not credible.

**Aggregate byte-model validation.** Arm B was measured independently in this run
(8.5957) and in the §6.2 ladder (8.5966) — **0.9 µs apart across two separate
process launches**, well inside both runs' A/A floors. Chaining the two runs on
that basis:

| chain | observed | predicted | ratio |
|---|---|---|---|
| `S→B` (this run) | 62.4 µs | 73.8 µs | 0.84 |
| `B→D` (§6.2) | 95.6 µs | 84.6 µs | 1.13 |
| **`S→D` chained** | **158.0 µs** | **158.4 µs** | **1.00** |

Over the full stock-o_proj-to-shipping-arm span the byte model is accurate to
0.3 %. I read the per-rung ratios as real but partly compensating: both o_proj
rungs land near 0.82–0.84 and the QKV rung at 1.38, which is consistent with the
larger QKV projections (8192/10240 rows) being more purely bandwidth-bound than
o_proj (2048 rows). I do not have evidence to settle that mechanism, and nothing
in the submitted claim depends on it.

**One caution about the 0.9 µs cross-run agreement.** That is a genuine measured
same-campaign A/A datum, and it is ~500× tighter than the ±0.46 % that tanjiro
measured on a null ranked change. The difference is that this probe is a tight
in-process decode loop on a fixed seed, whereas a ranked session includes process
start, harness setup, and cross-session drift. So this number is good evidence
that **my arm-to-arm contrasts are clean**, and it is *not* evidence about ranked
no-harm. Per programme law §0.9.32 the no-harm claim rests on the §5 identity
certificate, not on any timing I have.

---

## 7. Budget

Measured with `git cat-file -s` at `BASE_SHA` and at branch head:

| file | base `ab1f9a13` | head | delta | free to 524,288 cap |
|---|---|---|---|---|
| `Sources/MLXFastModel/LagunaRuntimeModel.swift` | 521,768 | 523,115 | **+1,347** | **1,173** |
| `Sources/MLXFastModel/LagunaRuntimeWeights.swift` | 44,463 | 47,492 | +3,029 | 476,796 |

```
bash senpai/check-editable-budget.sh ab1f9a1323421703f944ac1895841e39b8302542
editable budget OK: current=2971207/3000000 bytes headroom=28793 growth=4376/262144
                    files=142 (base=142)
```

`research/` is not in `editablePaths`, so the ten research files on this branch
cost zero submitted bytes. Total growth is 4,376 B against a 262,144 B
per-review allowance.

**The per-file cap on `LagunaRuntimeModel.swift` is the binding constraint, and
it is met with 1,173 B to spare.** It is also met against the newer frontier the
advisor flagged: at `9e8c719f` that file is 521,506 B, so 2,782 B free versus my
+1,347 B delta. This arm therefore does not depend on PR #81's literal reclaim
landing first — #81 turns a tight fit into a comfortable one, but the arm fits
either way.

Two consequences were accepted deliberately to stay inside that cap: the
block-narrow o_proj kernel family was deleted rather than kept behind a third
selector (§8), and no MSL literal in `LagunaRuntimeModel.swift` was re-indented
or comment-stripped, because PR #81 is running exactly that transformation
concurrently and a textual collision would be expensive for both branches.

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

### 8.1 Independent adversarial review of the M5 transfer risk

Because every timing number I have is from an M4 Pro and the ranked host is an
M5 Max, I commissioned a separate context-free frontier review of commit
`7302823` charged with finding reasons it would behave differently on M5. Its
verdict was **safe to dispatch, moderate-high confidence**, on the grounds that
the design is self-validating per host: the plane is quantized on-device at load,
the packer derives pairwise equality from the bytes actually produced *on that
host*, the certificate byte-checks the inverse decode on that same host, and any
row or bank that fails escapes to the resident stock plane. Nothing in the design
assumes the M4 result transfers.

It confirmed three things I had asserted and one I had not checked:

* `Quantize::eval_gpu` (`quantized.cpp:2396-2478`) has **no** `is_nax_available()`
  branch — nax gates only `qmm`/`gather_qmm` — and the runtime-compiled JIT twin
  `mlx-generated/fp_quantized.cpp:2334-2360` embeds the identical `w_max_l`/
  `w_max_r` source. The artifact is architecture-independent, as §2.2 claims.
* The fail-closed gate is sound: 0xFF-sentinel collision, NaN/Inf E4M3 bytes,
  nibble saturation and overflow are all closed by construction.
* Packer and MSL layouts agree at both sites for g ∈ {128, 384, 512}. A latent
  `g % 64 ≠ 0` / odd-block hazard exists but the packer guard makes it
  unreachable for this model's geometry. Worth a comment if the encoding is ever
  reused at another site.

**The finding I had not made myself, and the one the advisor should weigh:**
`CURRENT_RESEARCH_STATE.md:639-645` records that deliverable A (~2.6 MB/step) and
deliverable B alone (12.4 MB/step) were both held *off* the ranked path for being
below the resolvability floor. The consequence is that **all three lane-major
arms get their first ever M5 exposure in this dispatch** — no part of this read
path has ever run on the ranked host. That is a real, if low-likelihood,
gen-17-codegen risk, and it is high-cost because it burns the channel.

Two cheap mitigations, neither of which I can run from this host:

1. Run the M5 drift tripwire / upstream-equivalence pass before the timed phase.
2. One-off M5 escape census via `DARKBLOOM_ATTN_SCALE_NARROW_LOG=1`. If the
   pairwise artifact were somehow absent on M5 the arm degrades to mass escapes —
   still bit-exact, just slower — and the census would say so immediately.

Residual risk that the artifact is absent on M5 is rated moderate-low, and its
failure mode is *correct but slow*, never wrong.

---

## 9. Suggested follow-ups (not implemented)

* ~~The same pairwise artifact should hold for the **MoE routed and shared
  expert** scale planes.~~ **Already done — this is PR #72 (nezuko), merged
  02:48Z at `9e8c719f`.** She took the identical `fp_quantize` constancy property
  (`fp_quantized.h:2186-2205`, predicate `:2192-2194`) onto the routed plane with
  a `[128-B patch header][even-byte halved plane]` layout and an
  `allowedFlatPairs` gate. Her census independently reproduces my root cause from
  the other side: 985,300,992 even-byte pairs, 99.999983 % equal, **exactly 168
  exceptions across 234 tensors — one per tensor, always at flat pair 0**, with an
  odd-index control at 23.24 % mismatch. That "one exception per tensor at pair 0"
  is precisely what a first-simdgroup-only split predicts, and it is the strongest
  external confirmation the mechanism has. Her hunks (`:7330-8101`, `:10021-10340`)
  do not intersect my four sites, so the two changes compose.
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
