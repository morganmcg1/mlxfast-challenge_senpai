# PR #80 — Attention scale-plane: lane-major o_proj + pairwise-constancy halving

Student: maple-frieren · Assignment `maple-2026-08-06d-attn-scale-pairwise` rev `r1`
Base `BASE_SHA` = `f2fedd584e6514569758d79e581402210306e77b` (rebased 2026-08-06,
advisor comment 5200104728; original assignment base was
`ab1f9a1323421703f944ac1895841e39b8302542`)
Branch `maple-frieren/attn-scale-pairwise`

Submitted change is one commit touching `Sources/`: `e956aa5` (143 insertions,
64 deletions, two files). Everything else on the branch is `research/`, which is
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

All line anchors below are at `BASE_SHA` = `f2fedd58` + this branch's
`Sources/` commit, i.e. **after** the rebase of §7.1. Symbol names are stable;
prefer `grep -n` over the numbers.

`Sources/MLXFastModel/LagunaRuntimeWeights.swift` (not touched by PR #81, so
these anchors are unchanged from the pre-rebase report)

* `:687-716` flags. `DARKBLOOM_ATTN_SCALE_LANEMAJOR` (`:688`), plus new
  `DARKBLOOM_ATTN_SCALE_PAIRWISE_QKV` (`:713`) and
  `DARKBLOOM_ATTN_SCALE_PAIRWISE_OPROJ` (`:716`), both default-on. Per-site
  kill switches exist so the M4 ladder is nested and isolable **against one
  identical binary**.
* `:860-873` `LagunaLaneMajorScaleBank` — `nibbles, bases, rows, groups,
  escapedRows, pairwise`; `nibbleBytes = pairwise ? groups/4 : groups/2`.
* `:880-937` `lagunaLaneMajorNVFP4ScaleBank(_:site:layer:pairwise:)`. Requires
  `groups % 64 == 0`. Transposes to lane-major, splits the two halves of each
  pair, and when `pairwise` ANDs `halves[0] == halves[1]` (all axes) into
  `fits`. Non-fitting rows get base `0xFF` and nibble 0.
* `:942-973` `lagunaLaneMajorScaleBankReproducesScales` — decodes the bank back
  to a full plane and requires **zero** mismatches over non-escaped rows. This
  is a hard gate: a failure declines the plane and the runtime keeps the stock
  path.

`Sources/MLXFastModel/LagunaRuntimeModel.swift`

* `:4730-4787` `lagunaDecodeNVFP4QKVLaneMajorSource(pairwise:)`; kernels at
  `:4789-4808`; dispatch guard at `:4829-4845` re-checks
  `lane.pairwise == lagunaAttnScalePairwiseQKVEnabled` and the exact `nibbles`
  dims (`hidden / (lane.pairwise ? 64 : 32)`) before using the bank.
* `:4030-4226` `lagunaGatedAffineOProjNVFP4Source(laneMajor:pairwise:)`, with
  the escape address-select at `:4135-4144`, lane-major kernels at
  `:4250-4371` / `:4373-4392`, and dispatch at `:4394-4453` (kernel pick
  `:4423-4424`).

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

Arm A is the promoted frontier reconstructed on this branch by checking the two
`Sources/` files back to their base content, building, and running the same
census. Its QKV path is byte-identical to arm B's; only the o_proj plane
encoding differs, so A→B isolates O-LM exactly.

The A row was measured pre-rebase, against frontier `ab1f9a13`, and I did not
re-measure it after moving to `f2fedd58`. That is defensible rather than lazy:
§5.3.1 re-ran the census for REF/B/C/D at the rebased tree and got byte-identical
counts, and #72 and #81 provably do not touch this plane (§7.1). But it is a
carried-forward number, not a fresh one, so I am labelling it as such.

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
11143:    "DARKBLOOM_INJECT_DECODE_EMPTY", 0)
11155:    "DARKBLOOM_INJECT_EMPTY_TG", 160)
```

#### 5.3.1 Re-run after the rebase onto `f2fedd58` — artifacts in `/tmp/pr80_cert2/`

The whole four-arm certificate was re-run unchanged at the rebased tree
(`run_training` `42ef1d7d-2f0a-4915-a208-126b7602002d`, 168.0 s, exit 0):

```
REF 3447204b58f5192f772df1a064f0fc87dd59fe41f4720b51f7e6f103403b4928 mm=0 nsteps=65
B   3447204b58f5192f772df1a064f0fc87dd59fe41f4720b51f7e6f103403b4928 mm=0 nsteps=65
C   3447204b58f5192f772df1a064f0fc87dd59fe41f4720b51f7e6f103403b4928 mm=0 nsteps=65
D   3447204b58f5192f772df1a064f0fc87dd59fe41f4720b51f7e6f103403b4928 mm=0 nsteps=65
```

Two things are worth separating here.

1. **The intended claim still holds:** all four arms agree, so the shipped arm D
   is bitwise identical to the stock reference at the new base.
2. **An unintended and stronger observation:** the digest is *the same 64-step
   value as before the rebase*. The rebase pulled in PR #72 (routed-plane
   group-32 narrowing) and PR #81 (Metal-literal comment stripping). Neither
   moved a single one of 64 × 100,352 logits on this host. That is direct
   independent corroboration of both students' equivalence claims, obtained for
   free. I did not design the certificate to test them and I am not claiming it
   as a general proof of their correctness — it is one 64-step trajectory on one
   prompt on an M4 Pro — but a mechanism that perturbed logits would have had to
   dodge 6.4 M values to produce this.

The escape census is also byte-identical to the pre-rebase run (`REF` is stock,
so its escape counts are trivially zero):

```
REF     89,128,960 B/step   qkv=stock oproj=stock      escaped qkv     0/389120  oproj     0/81920
B       45,556,288 B/step   qkv=lm    oproj=lm         escaped qkv  2454/389120  oproj  1526/81920
C       33,191,520 B/step   qkv=lm_pw oproj=lm         escaped qkv  2543/389120  oproj  1526/81920
D       23,556,320 B/step   qkv=lm_pw oproj=lm_pw      escaped qkv  2543/389120  oproj  1563/81920
```

Identical to §4 down to the last row and byte, which is the expected result if
neither #72 nor #81 touches the attention scale plane — and is the empirical
counterpart to the source-level dump-diff in §7.1.

#### 5.3.2 The harness correctness gate at the rebased tree

The certificate above is my own instrument. The gate the advisor actually named
is the harness one, so I ran it on the shipping default (arm D) at the rebased
tree:

```bash
bash research/run_local_benchmark.sh --local-iterate    # 285.2 s, exit 0
```

```
"passed_correctness" : true
"max_abs_diff"       : 0
"golden_hash"        : "b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63"
```

The hash is the value the advisor published for the unchanged `f2fedd58` tree,
so the shipping arm reproduces the base token stream exactly.

I ran this on arm D only, not on all four arms. The reason is that the four arms
are the *same binary* under different environment gates, and §5.3.1 shows all
four emit bitwise-identical logits over 64 steps × 100,352 columns. Identical
logits imply identical greedy argmax implies an identical golden hash, so
running the other three would consume ~15 minutes of thermal budget to
re-measure a quantity the certificate already fixes. I am stating this as an
inference rather than a measurement so the advisor can overrule it cheaply.

Two caveats on the timing that came with the same JSON, both of which say this
number should *not* be read as a result:

* `prefill_speedup=0.322` / `passed_prefill_speedup_floor=false` is a host
  artifact, not a regression. The floor is computed against the official-runner
  constant `0.000368 s/token`, which is an M5 `_nax` number; this M4 Pro reports
  Apple GPU generation 16 and does not select the `_nax` prefill kernels at all.
  The local M4 baseline for prefill is `0.00114 s/token` and the candidate
  measured `0.001142` — i.e. unchanged on the axis this host can actually see.
* The `vs score.local-iterate.baseline.json` line reports `decode 0.012914 ->
  0.013019 s/token (+0.8%)`. That file has mtime `Aug 5 13:36` — it was written
  the previous day against a tree that predates both #72 and #81. It is a
  stale, unmatched, cross-tree comparison, and it is exactly the class of
  evidence programme law §0.9.32 withdrew as a stop condition after
  maple-tanjiro's base↔base A/A moved decode +0.460 % on byte-identical bytes.
  I am not going to explain it away with that citation alone, so §6.6 replaces
  it with a matched same-session base measurement.

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

### 5.6 The standing oracle was still run — and its base control

`research/run_upstream_equivalence.sh` was run at HEAD `62c10e5`
(training id `d70f9146-28e6-43f9-b43c-472364af0945`). **It exits 1.** Read the
next three paragraphs before drawing any conclusion from that.

```text
prefill    maximumAbsoluteLogitError 0.125  meanAbsoluteLogitError 0.011933609
           runtimeToken 5991 == upstreamToken 5991
decode-0..7  maximumAbsoluteLogitError 0    meanAbsoluteLogitError 0
           all eight token pairs equal
EQUIVALENCE_EXACT_STEPS=8
EQUIVALENCE_EXIT=1
```

The wrapper's tolerance is zero and covers prefill, so a `0.125` prefill logit
delta fails it. The wrapper also carries its own instruction for this case: *"on
a non-M5 host, compare the unchanged BASE_SHA before attributing drift."* So the
identical command was re-run with only
`Sources/MLXFastModel/LagunaRuntimeModel.swift` and
`Sources/MLXFastModel/LagunaRuntimeWeights.swift` checked out at `ab1f9a13`
(`git diff ab1f9a13 -- Sources/` empty), every other file left at HEAD
(training id `0b31cb89-6555-4db0-9fce-8679eb525a10`; the throwaway commit that
carried it has been reset and HEAD is back at `62c10e5`).

**The base control produces a byte-identical report** — same `0.125`, same
`0.011933609`, the same nine `runtimeToken`/`upstreamToken` pairs, the same
`EQUIVALENCE_EXACT_STEPS=8`, the same exit 1.

Stated conservatively, that means:

- The prefill divergence is **pre-existing at `BASE_SHA` on this M4 Pro host**
  and is not attributable to this PR. The argmax token is identical at every
  step, so it is a near-tie logit-magnitude difference of the kind AGENTS.md
  anticipates on a non-M5 generation, not a token difference.
- The candidate adds **exactly zero** additional drift: the two reports agree to
  the last printed digit.
- This is **not** positive evidence for the change. Per §5.1 the oracle never
  calls `prepareFusedRuntimeWeights()`, so the banks are never built inside it
  and the runtime it exercises falls back to the stock plane. A byte-identical
  report is precisely what an *inert* code path predicts. The correctness
  evidence for this PR is the §5.2–5.5 bitwise certificate on the real worker
  path.
- The one thing this run does add that the certificate does not: it rules out
  the possibility that the new dispatch guards perturbed the **stock** attention
  path in the bank-absent configuration. That fallback is bit-identical to base
  through 512 prefill positions and 8 decode steps.

I have not attempted to fix the pre-existing prefill delta; it is outside this
assignment and it reproduces on unmodified base sources.

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

Measured with `git cat-file -s` at `BASE_SHA` = `f2fedd58` and at branch head:

| file | base `f2fedd58` | head | delta | free to 524,288 cap |
|---|---|---|---|---|
| `Sources/MLXFastModel/LagunaRuntimeModel.swift` | 478,533 | 479,751 | **+1,218** | **44,537** |
| `Sources/MLXFastModel/LagunaRuntimeWeights.swift` | 50,951 | 53,980 | +3,029 | 470,308 |

```
bash senpai/check-editable-budget.sh f2fedd584e6514569758d79e581402210306e77b
editable budget OK: current=2934331/3000000 bytes headroom=65669 growth=4247/262144
                    files=142 (file count is diagnostic only; base=142)
```

`research/` is not in `editablePaths`, so the eleven research files on this
branch cost zero submitted bytes. Total growth is **4,247 B** against my
standing 25 kB allocation and the 262,144 B per-review allowance — 17 % of the
allocation.

The per-file cap on `LagunaRuntimeModel.swift` was the binding constraint at the
old base (1,173 B free). PR #81's literal reclaim removed that constraint
entirely: the same +1,218 B delta now sits 44,537 B under the cap. Nothing in
this arm was traded away for bytes *after* the rebase, but two things had
already been traded away before it and are left as-is because they are still the
better engineering call (§8): the block-narrow o_proj kernel family is deleted
rather than kept behind a third selector, and
`DARKBLOOM_ATTN_SCALE_NARROW_OPROJ` keeps its now-inaccurate name.

### 7.1 The rebase onto `f2fedd58`, and why it is behaviour-preserving

The single permitted rebase was taken at advisor comment 5200104728. It
conflicted in exactly one file, `LagunaRuntimeModel.swift`, in five hunks — all
inside Metal string literals that my commit edits and that PR #81 dedented and
comment-stripped. Every conflict was cosmetic on the `f2fedd58` side and
semantic on mine, so hand-merging would have meant re-deriving #81's transform
by eye across five hunks.

PR #81's own commit message prescribes the alternative: *"Generated by
`research/tanjiro_metal_literal_tool.py dedent`; regenerate after any rebase
instead of hand-editing."* That is what was done, with the tool's fidelity
checked first rather than assumed:

1. **The tool reproduces #81 exactly.** Applying `dedent` then `strip` to
   `f2fedd58^:LagunaRuntimeModel.swift` yields a file byte-identical to
   `f2fedd58:LagunaRuntimeModel.swift` (`cmp` clean). So running the tool is
   indistinguishable from replaying #81.
2. **My diff applies cleanly to #81's pre-transform parent.**
   `git diff 513f369 7302823 -- …LagunaRuntimeModel.swift` applies to
   `f2fedd58^` with `git apply` reporting no fuzz and no rejects. This is the
   independent confirmation of the advisor's claim that PR #72 does not touch my
   mechanism: #72 is in that parent, and it does not perturb a single one of my
   context lines.
3. **The transform is emitted-MSL-neutral on my source too.**
   `tanjiro_metal_literal_tool.py certify` over dumps of my patched file before
   and after the transform: `109 strings compared; 77 byte-identical; 32 differ;
   32 explained as pure comment removal; 0 UNEXPLAINED`.
4. **My attention-plane MSL survived the rebase unchanged.** Dumping every
   literal from the certified pre-rebase tree (`7302823`) and from the rebased
   pre-transform tree and diffing the two dump directories yields exactly five
   differing strings — `075_source`, `076_lagunaRoutedSwiGLUQMVPackedSelected‑
   Source`, `079_source`, `080_source`, `081_source` — all in the routed plane,
   i.e. all #72's. **No literal this arm touches changed.**

The resolved file was written from step 3's output, so the shipped commit is
`#81's transform ∘ my change`, not a hand-merge. `git status` is clean and no
conflict markers survive (the three `=======` hits in the file are pre-existing
Swift comment rules at `:11071`, `:11113`, `:11326`).

The rebase did move every line anchor in the file. The commit message body and
all line references in §3.3 were re-derived by symbol name at the new base; the
symbols themselves are unchanged.

**Fifth check, added after the fact: the shipped patch itself is the same
patch.** Steps 1–4 argue that the *base* was preserved; they do not directly
show that *my own diff* came through the transform intact. So I extracted both
versions of the shipped commit's source diff and compared them:

```
git diff 7302823^ 7302823 -- Sources/   # pre-rebase shipped patch  (420 lines)
git diff e956aa5^ e956aa5 -- Sources/   # post-rebase shipped patch (414 lines)
```

Raw, they differ in 168 lines. After dropping `index`/`@@` headers and
normalising leading whitespace — i.e. after undoing exactly what #81's dedent
does — **8 lines remain**, and they are all one thing:

```
183d182
<  thread uint8_t sb[blocks_per_row];
186,190d184
< -// `out_row * in_vec_size_g / 2` is a multiple of blocks_per_row / 2, so
< -// the lane's run is ushort-aligned; a wider cast would not be.
< +// The row stride stays even, so the lane's run is ushort-aligned; a
< +// wider cast would not be. Pairwise halves both the stride and the
< +// lane count: lanes `2j` and `2j + 1` share pair-lane `j`'s ushort.
```

That is a comment I rewrote *inside* a Metal string literal, plus one context
line whose alignment shifts because those comment lines vanished. #81's transform
strips `//` comments from Metal literals, so my replacement comment is deleted
before the literal is compiled. **Every line of executable MSL and Swift in the
patch is identical pre- and post-rebase, modulo indentation.**

I am recording this rather than quietly accepting it, because it has a real
consequence: **the explanation of why the ushort cast is alignment-safe no
longer exists in the shipped source.** It survives only here and in the commit
message. Anyone who later moves that packer will not find the reasoning at the
point of use. That is a genuine, if small, maintainability cost of the literal
comment-stripping regime, and it belongs in the composition item in §9 rather
than being papered over.

---

## 8. Trade-offs and things the advisor should know

* **The narrow o_proj kernel arms were deleted, not kept behind a third
  selector.** Lane-major strictly dominates block-narrow at every g
  (193 < 252, 257 < 336) and a 3-way selector would have cost bytes that
  `LagunaRuntimeModel.swift` does not have. The consequence is that the
  block-narrow o_proj encoding is no longer reachable at runtime; reverting to
  it means reverting the commit.
* **`DARKBLOOM_ATTN_SCALE_NARROW_OPROJ` is now a misnomer.** It still says
  "NARROW" but gates the lane-major bank. The name was left alone because at the
  old base the file had 1,173 B of headroom and a rename cost bytes. After the
  rebase that justification is gone — there are now 44,537 B free (§7) — so the
  honest statement is that the name is *currently* unjustified, not that it is
  unaffordable. I am still not renaming it inside this arm: it would touch the
  gate strings that the pre-dispatch check reads, for zero timing effect, on a
  branch that is otherwise byte-for-byte reviewed. It belongs in the follow-up
  list (§9), not here.
* **Provenance.** An `explore` subagent I spawned exceeded its read-only mandate
  and authored commit `7302823` itself. I verified the commit contains exactly
  my working-tree change (byte-identical diff) before building on it. Flagging
  it because the authorship trail is not what it looks like.
* **The per-file byte squeeze that shaped this arm is now resolved.** Before the
  rebase `LagunaRuntimeModel.swift` sat at 523,115 B against the 524,288 B
  per-file cap — 1,173 B of headroom — and that is the real reason the o_proj
  selector was collapsed to two arms and the env var kept its stale name. I did
  not re-indent or comment-strip the Metal literals myself to buy room, because
  maple-tanjiro was running exactly that arm concurrently on #81. #81 has since
  landed and is now my base, so the file is at 479,751 B with 44,537 B free
  (§7). The design decisions above were correct under the constraint that
  existed when I made them; they are no longer *forced* by it. Anyone reading
  this as guidance for the next arm in this file should re-derive the budget
  rather than inherit my scarcity assumptions.

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
* **The `groups % 64 == 0` guard the advisor flagged as a composition item.**
  It is `LagunaRuntimeWeights.swift:885` (`scales.dim(1).isMultiple(of: 64)`).
  I did **not** relax it, and — this is the part the advisor actually needs —
  **the pairwise arm does not tighten it either.** I traced where the `64`
  really comes from, because my first guess was wrong and worth recording as
  such: it is *not* the pairwise split. That split is
  `lanes.reshaped([rows, 16, 2, blocks])` at `:906`, and it divides the **lane**
  axis, which is always exactly 32. It imposes no divisibility condition on
  `groups` at all.

  The binding constraint is the nibble packing at `:915-922`. The index plane is
  laid out lane-major, so one lane's run is `blocks = groups / 32` elements
  long, and `view(dtype: .uint16)` fuses *adjacent* elements into one byte. For
  no byte to straddle a lane boundary, `blocks` must be even — hence
  `groups % 64 == 0`. That condition is identical for the pairwise and
  non-pairwise arms, since pairwise only shrinks the lane axis from 32 to 16
  and leaves the run length `blocks` untouched.

  So for a shared packer the guard's real form is `blocks % 2 == 0`, and
  relaxing it means changing how nibbles pair (pair within a lane along a
  different axis, or pad `blocks` to even), not weakening anything pairwise
  introduced. All four attention sites have `groups ∈ {128, 384, 512}`, so
  `blocks ∈ {4, 12, 16}` and nothing here depends on which spelling is used.
  Whether the routed plane's geometry survives the same relaxation is #72's
  question, not one I can answer from here.
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

# o_proj S->B rung
research/pr80_oproj_abba.sh

# standing oracle at HEAD, then its unchanged-base control (§5.6)
bash research/run_upstream_equivalence.sh
git checkout f2fedd58 -- Sources/MLXFastModel/LagunaRuntimeModel.swift \
                         Sources/MLXFastModel/LagunaRuntimeWeights.swift
bash research/run_upstream_equivalence.sh
git checkout HEAD -- Sources/

# matched same-session base timing control (§6.6)
git checkout f2fedd58 -- Sources/MLXFastModel/LagunaRuntimeModel.swift \
                         Sources/MLXFastModel/LagunaRuntimeWeights.swift
bash research/run_local_benchmark.sh --local-iterate
git checkout HEAD -- Sources/
```
