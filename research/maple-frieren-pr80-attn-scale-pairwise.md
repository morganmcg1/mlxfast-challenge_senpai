# PR #80 — Attention scale-plane: lane-major o_proj + pairwise-constancy halving

SENPAI-RESULT: {"terminal":true,"status":"complete","pending_arms":false,"wandb_run_ids":[],"primary_metric":{"name":"attention_scale_bytes_per_decode_step","available":true,"value":23556320},"test_metric":{"name":"passed_correctness","available":true,"value":1}}

Student: maple-frieren · Assignment `maple-2026-08-06d-attn-scale-pairwise` rev `r1`
Base `BASE_SHA` = `f2fedd584e6514569758d79e581402210306e77b` (rebased 2026-08-06,
advisor comment 5200104728; original assignment base was
`ab1f9a1323421703f944ac1895841e39b8302542`)
Branch `maple-frieren/attn-scale-pairwise`

**Ranked outcome: PROMOTED — new record.** Receipt
`97a5090c-a408-4222-b6d6-dd85c4bce09e`, `status = accepted`,
`promotionStatus = promoted`, `improved = true`, `error = ""`,
`passed_correctness = true` (11 cases, 1344 checked steps),
both floors passed (`decode_speedup = 2.8207`, `prefill_speedup = 2.0015`,
floors 0.95), `officialScore = 2.58882784082067`. Full six-line report,
base-vs-candidate attribution, and the baseline-draw caveat are in §11.

Submitted change is one commit touching `Sources/`: `e956aa5` (143 insertions,
64 deletions, two files). Everything else on the branch is `research/`, which is
not in `editablePaths` and therefore costs zero submitted bytes.

- Student / PR: `maple-frieren` / #80 (`maple-2026-08-06d-attn-scale-pairwise`,
  revision `r1`)
- Hypothesis and target cost: MLX's `fp_quantize` dispatches a flat 1-D grid, so
  for `group_size != 32` only the first simdgroup of each plane actually splits
  its half-max; every later chunk writes the *same* E4M3 byte to both members of
  a scale pair (§2.2). The NVFP4 attention scale planes are therefore pairwise
  constant almost everywhere, and the decode kernels can read a quarter to a half
  as many scale bytes per row with no change to any produced number. Target cost
  is scale-plane traffic on the decode path: **51.25 MB/step** at the promoted
  frontier, **23.56 MB/step** shipped, a **27.70 MB/step** reduction.
- Decision: **green** on the byte channel, which is the only channel this host
  may price (§0.9.33). Not a wall-time claim.
- `BASE_SHA` / candidate commit:
  `f2fedd584e6514569758d79e581402210306e77b` /
  `e956aa50e27ff5e896f59525e69f3552deb95a12` (the only commit touching the
  submitted surface; every later commit is `research/`). The branch head
  actually published is the `commit_sha` of the structured Senpai result.
- Publication note: the advisor-released rebase (comment 5200104728) rewrote
  this branch, so the rebased head no longer fast-forwarded the pre-rebase
  remote head `513f3693abec7064a5551d9969d27f0c98cf61e4`, and the
  student-available publish path accepts only a fast-forward. Commit
  `2fe33f28ea7dd0e56d21cde42a0ecb08305e444a` is an **ours-strategy merge** that
  records `513f3693` as an ancestor and contributes no content: its tree is
  byte-identical to the pre-merge head (`c9bd9305d1012a396f26c7d8283244e920ecddd5`).
  `git merge-base HEAD codex/mlxfast-maple-20260804-advisor` remains
  `f2fedd58`, so the reviewed PR diff is still exactly
  `143 insertions(+), 64 deletions(-)` across the two submitted files. No force
  push was performed and no submitted byte changed.
- Submitted candidate files: `Sources/MLXFastModel/LagunaRuntimeModel.swift`,
  `Sources/MLXFastModel/LagunaRuntimeWeights.swift` (only these two)
- Supporting test or documentation files: `research/frieren_pr80_logit_bitwise.py`,
  `research/pr80_cert_run.sh`, `research/pr80_byte_ledger.py`,
  `research/pr80_fault_patch.py`, `research/pr80_ladder_abba.sh`,
  `research/pr80_ladder_analyze.py`, `research/pr80_oproj_abba.sh`, and this
  report. None is on the submitted surface; the candidate builds and runs
  without any of them.
- Official submission `--model` value (planned or used; default `senpai`):
  **planned `senpai`, not dispatched.** Advisor comment 5200283249 allocates the
  ranked channel to PR #85 Step 0, so this PR posts `READY FOR CHANNEL` and
  stops. When authorised the command is `mlxfast submit --model "senpai"`.
- Explicit API model-value rejection, if fallback attribution was required:
  **n/a** — no submission attempted, so no rejection and no fallback.
- Assignment-scope preflight:
  `senpai/validate-assignment-scope.sh f2fedd58… Sources/MLXFastModel/LagunaRuntimeModel.swift Sources/MLXFastModel/LagunaRuntimeWeights.swift`
  → `assignment scope OK: 2 submitted path(s) against BASE_SHA=f2fedd58…`
- Editable bytes / headroom / growth:
  `editable budget OK: current=2934331/3000000 bytes headroom=65669 growth=4247/262144 files=142 (base=142)`.
  Growth 4,247 B against the 25 kB allocation in comment 5200283249.
  `LagunaRuntimeModel.swift` 478,533 → 479,751 B leaves **44,537 B** under the
  524,288 B per-file cap, satisfying the standing ≥20 kB margin law (§7).
- Scored-path reachability evidence: `LagunaRuntimeModel.swift` *is* the scored
  forward pass. The two rewritten kernels are the ones the decode path actually
  selects — `lagunaGatedAffineOProjNVFP4` picks the lane-major variant at
  `:4423-4424` and the QKV dispatch guard at `:4829-4845` picks the lane-major
  QKV kernel. Reachability is demonstrated dynamically, not by inspection: the
  per-layer escape census (§4) is emitted from inside those dispatches, and the
  matched same-session harness pair in §6.6 changes measured decode time while
  holding `golden_hash` identical.

### Evidence

- Host, memory profile, toolchain, and thermal policy: Apple **M4 Pro** (Apple
  GPU generation 16), 48 GiB unified memory → low-memory startup profile, macOS
  26.5.2 (25F84), Apple Swift 6.3.3 (swiftlang-6.3.3.1.3). The board's GPU temp
  sensor is stuck at 2.37 °C, so `research/run_local_benchmark.sh` re-points
  `MLXFAST_GPU_TEMP_CMD` at a live CPU-die sensor and sets
  `MLXFAST_LOCAL_FAN_PROMPT=0`; the 40 C gate is *enforced*, not disabled. This
  is **not** the ranked M5: generation 16 does not select the `_nax` prefill
  kernels, so no prefill claim is made from this host (§6).
- Exact baseline and candidate commands: full list in §10. The two that carry
  the headline results are
  `bash research/pr80_cert_run.sh` (bitwise logit certificate, §5) and
  `bash research/run_local_benchmark.sh --local-iterate` run once on a tree with
  `git diff f2fedd58 -- Sources/` empty and once on the candidate (§6.6).
- Tests and risk-based checks run, including selected-test count:
  `research/run_upstream_equivalence.sh` → **1 selected test**
  (`lagunaRuntimeMatchesVendoredUpstreamOnM5WhenEnabled`), run on the candidate
  *and* on an unchanged-base control; the zero-test failure mode is explicitly
  ruled out in §5.6. Harness correctness gate via `--local-iterate` → passed.
  13-arm fault-injection matrix (§5.4) → 7/7 planted faults detected.
- Correctness and serial-protocol verdict: **PASS.** All four arms produce the
  identical 64-step logit digest
  `3447204b58f5192f772df1a064f0fc87dd59fe41f4720b51f7e6f103403b4928` over the
  full 100,352-entry vector, `mm=0`, `nsteps=65`. The matched harness pair
  reports `passed_correctness = True` with an identical `golden_hash`
  `b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63` on both
  sides. Serial protocol is untouched: this change re-encodes a *weight-derived*
  scale plane prepared outside the scored hot path. It adds no KV row, no
  speculative row, no cross-request state, and no input-keyed cache; the packing
  depends only on the checkpoint.
- Divergent tokens or failure category, if any: **none.** The one nonzero number
  anywhere in the equivalence oracle is a prefill
  `maximumAbsoluteLogitError 0.125`, and §5.6 shows byte-identical oracle output
  from an unchanged-base control run, i.e. it is pre-existing at `f2fedd58` on
  this M4 Pro and the candidate adds exactly zero drift.
- Peak RAM or generated-weight size, if relevant: unchanged. The pairwise bank is
  strictly smaller than the plane it replaces, and the stock plane stays resident
  for the escape path, so resident footprint moves by well under the ~21.6 GB
  tower's noise. No new generated-weight artifact.
- Official ranking status versus correctness/floor status, if submitted: **not
  submitted** — ranked channel allocated elsewhere (see `--model` field above).

| Metric | Baseline | Candidate | Ratio / delta |
| --- | ---: | ---: | ---: |
| attention scale bytes / decode step (exact census, transfers per §0.9.33) | 51,254,656 | 23,556,320 | −27,698,336 B (−54.0 %) |
| M5 score value of that reduction @ peak 651.8 GB/s | — | — | +0.633 % |
| M5 score value of that reduction @ effective 546.2 GB/s | — | — | +0.756 % |
| decode seconds/token (M4 Pro, matched same-session, n=1/arm) | 0.013258813796875 | 0.0130188287734375 | 1.0184x |
| prefill seconds/token (M4 Pro, matched same-session, n=1/arm) | 0.001131525064453125 | 0.00114205655859375 | 0.9908x |
| same-host paired estimate (M4 Pro, directional only) | — | 1.011448 | — |

The paired estimate is a same-host research metric, not an official M5 score.
Under §0.9.33 the byte row is the claim; the three M4 timing rows are
directional context on a non-ranked GPU generation and are decomposed in §6.7.

### Conclusion

- What happened and why: the scale planes really are pairwise constant, for the
  concrete dispatch reason in §2.2 rather than as a statistical accident, so the
  redundant half can simply not be stored or read. The residual 0.65 % of QKV
  rows and 1.91 % of o_proj rows that violate the predicate take an exact
  per-row `0xFF` escape into the untouched stock plane, which is why the output
  is bit-identical rather than approximately equal.
- Evidence for or against the mechanism: three independent instruments agree.
  The per-layer census gives the byte ledger exactly. The M4 B→C→D ladder
  separates the two sub-rungs at 25 σ with a 5.4 µs A/A floor, and the S→B
  o_proj rung separates completely at 26 σ with observed/predicted 0.84. The
  matched same-session harness pair moves decode −1.81 % with a *different*
  `harness_hash` (proving the base control genuinely rebuilt) and an *identical*
  `golden_hash`.
- Uncertainty or M5 transfer risk: the byte reduction is arithmetic and
  transfers. The M4 wall-clock does not: §6.7 shows the byte channel explains
  only 106 µs of the observed 240 µs/step, leaving a 133 µs instruction-channel
  residual (ratio 2.25) that is deliberately left unpriced. The live hazard is
  the 89 `g=0` exceptions, handled by an exact escape rather than a tolerance
  (§5.5). A frontier adversarial transfer review (§8.1) found no `_nax` override
  for `Quantize::eval_gpu`, confirmed the fail-closed gate covers
  0xFF-collision, NaN, saturation, and overflow, and verified packer-vs-MSL
  layout agreement for g ∈ {128, 384, 512}; its residual concern is that all
  three lane-major arms get first-ever M5 exposure here, with a
  correct-but-slow, never-wrong failure mode.
- Smallest useful next action: dispatch this candidate on the ranked M5 when the
  channel frees, and read the paired verdict's two floors separately from
  ranking status.
- Recommendation: **merge**, then dispatch when the channel is released.

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
13-arm fault-injection matrix. A matched same-session base-vs-candidate pair on
the real harness (§6.6) moves M4 decode −1.81 % with an identical `golden_hash`;
that is directional context on a non-ranked generation, not the claim, and §6.7
separates what transfers to M5 from what does not.

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

Both rows are byte-channel arithmetic, which is the only class of quantity that
§0.9.33 lets me carry to M5. On M4 the observed decode movement is about 2.25×
what the byte model prices there (§6.6, §6.7); I am deliberately **not** pricing
that residual into the rows above, because issue rate and address-generation cost
are machine-determined and do not transfer. It is unpriced upside, not headroom
I am claiming.

The one thing that does argue for the upper row over the lower is that the three
rungs are only resolvable as a union: PW-QKV alone (+0.280 %) sits at the MDE, and
PW-O (+0.218 %) and O-LM (+0.135 %) are individually below it. That is why I ship
the union and make no per-rung ranked claim.

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
  The matched same-session base of §6.6 measured `0.001131525 s/token` here and
  the candidate `0.001142057`, a `+0.93 %` gap that sits inside the measured A/A
  spread on this instrument; no prefill claim is made from this host either way.
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

`research/run_upstream_equivalence.sh` was re-run at the rebased tree
(training id `1d078aa0-c1cd-4054-b688-b1b3d6f5e2ef`). **It exits 1.** Read the
next three paragraphs before drawing any conclusion from that.

```text
prefill    maximumAbsoluteLogitError 0.125  meanAbsoluteLogitError 0.011933609
           runtimeToken 5991 == upstreamToken 5991
decode-0..7  maximumAbsoluteLogitError 0    meanAbsoluteLogitError 0
           all eight token pairs equal
EQUIVALENCE_EXACT_STEPS=8
EQUIVALENCE_EXIT=1
```

The invocation is not a vacuous one. The XCTest shim in the log reports
`Executed 0 tests` because the case is a swift-testing `@Test`, but the
swift-testing run reports `Test lagunaRuntimeMatchesVendoredUpstreamOnM5WhenEnabled()
started` and `Test run with 1 test in 0 suites failed` — one test really ran, so
this is not the zero-test invocation AGENTS.md warns must never be called a pass.

The failing assertion is `passes(maximumAbsoluteLogitError: tolerance → 0.0)`.
The wrapper's tolerance is zero and covers prefill, so a `0.125` prefill logit
delta fails it. The wrapper also carries its own instruction for this case: *"on
a non-M5 host, compare the unchanged BASE_SHA before attributing drift."* So the
identical command was re-run with only
`Sources/MLXFastModel/LagunaRuntimeModel.swift` and
`Sources/MLXFastModel/LagunaRuntimeWeights.swift` checked out at `f2fedd58`
(`git diff f2fedd58 -- Sources/` empty), every other file left at HEAD
(training id `d4b751e4-519d-456a-85a0-6f93670c91df`; the throwaway commit that
carried it has been reset and HEAD is back on the work branch).

**The base control produces a byte-identical report.** This is a mechanical
check, not an eyeball one — a filtered diff over every `label`,
`maximumAbsoluteLogitError`, `meanAbsoluteLogitError`, `runtimeToken`,
`upstreamToken` and `EQUIVALENCE_*` line of the two logs is empty:

```bash
diff <(grep -E 'label|AbsoluteLogitError|runtimeToken|upstreamToken|EQUIVALENCE_' /tmp/pr80_eq2_cand.log) \
     <(grep -E 'label|AbsoluteLogitError|runtimeToken|upstreamToken|EQUIVALENCE_' /tmp/pr80_eq2_base.log)
# -> no output
```

Same `0.125`, same `0.011933609`, the same nine `runtimeToken`/`upstreamToken`
pairs, the same `EQUIVALENCE_EXACT_STEPS=8`, the same exit 1.

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
on this access pattern is below peak, and part of the saving is instruction-side
rather than byte-side at all. Either way the ratio is a wall-time quantity on M4
hardware, so §0.9.33 puts it in the non-transferring class: it is a reason to
prefer the *effective*-bandwidth row of §1.1 over the peak row as a matter of
judgement, not a coefficient I may carry to M5. §6.7 separates the two channels
explicitly. I am claiming the byte-ledger numbers, not the 1.13-scaled ones.

### 6.4 What this screen does and does not cover

Covered: `B→D`, i.e. 22.00 MB/step of the submitted arm's 27.70 MB/step.

**Not covered by this ladder: the `A→B` rung** (o_proj block-narrow →
lane-major, 5.70 MB/step, +0.130 %). Arm A is the promoted frontier and needs a
*different binary*; a mid-ladder rebuild is exactly the confound the
single-binary design exists to avoid. It is priced from the byte ledger only. It
is also below the 0.278 % receipt MDE on its own, which is why the arm ships as
a union. §6.6 does span it, but with a two-build `--local-iterate` pair at n=1
per arm, which is a weaker instrument than this one and is reported as context.

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

### 6.6 Matched same-session base-vs-candidate on the real harness

§5.3.2 flagged that the only end-to-end number the harness handed me came with a
stale cross-tree comparison attached. This subsection replaces it. Arm A is not
reachable in the shipped binary (§8, decision 3), so an end-to-end A→D contrast
cannot be produced by an environment gate; it needs two builds. That is what was
run, back to back in one session on one host under one thermal policy:

```bash
# base control
git checkout f2fedd58 -- Sources/MLXFastModel/LagunaRuntimeModel.swift \
                         Sources/MLXFastModel/LagunaRuntimeWeights.swift
git diff f2fedd58 -- Sources/          # empty, verified before launch
bash research/run_local_benchmark.sh --local-iterate    # 130.9 s, exit 0
```

| | base (`f2fedd58` `Sources/`) | candidate (arm D) |
|---|---|---|
| `passed_correctness` | `true` | `true` |
| `max_abs_diff` | `0` | `0` |
| `golden_hash` | `b9509697…a58d7a63` | **identical** |
| `harness_hash` | `e7cd0328…a70c9ebe` | `8e5a6370…be675a8e` |
| `decode_seconds_per_token` | 0.013258814 | **0.013018829** |
| `prefill_seconds_per_token` | 0.001131525 | 0.001142057 |

```
decode   0.013258814 -> 0.013018829    -1.810 %   (-240.0 us/step, faster)
prefill  0.001131525 -> 0.001142057    +0.931 %
```

Both JSONs carry the same pinned constants
(`baseline_decode_seconds_per_token = 0.01385621216015625`), so the two runs are
on the same ruler and the seconds/token columns are directly comparable.

**The differing `harness_hash` is the point, not a defect.** The two runs have
different `Sources/`, so they must produce different worker binaries; a matching
hash would have meant the base control silently reused the candidate build. This
is the opposite configuration from tanjiro's §0.9.32 A/A, where the hash was
*identical* because the bytes were identical — and that A/A is exactly why the
number below is framed as context rather than as the claim.

What this does and does not establish:

- It **withdraws the stale `+0.8 % slower` artifact.** Measured against a
  matched same-session base rather than a day-old pre-#72/#81 snapshot, decode
  moves −1.81 %, i.e. the sign reverses. The stale file was the artifact.
- It is **n=1 per arm and not counterbalanced.** Tanjiro's measured A/A spread on
  this same `--local-iterate` instrument was decode +0.460 % on a null change,
  so −1.81 % is ≈3.9× that spread — suggestive, not decisive. The rigorous
  instrument in this report remains §6.2's counterbalanced ABBA ladder
  (n=4/arm, one binary, 25σ on `B→D`).
- **No prefill claim is made.** +0.931 % is inside the measured A/A spread
  (−0.822 % on a null change), and this M4 Pro is Apple GPU generation 16 and
  never selects the `_nax` prefill kernels the ranked M5 uses.
- Correctness at the shipping arm is unchanged: same `golden_hash` as the base
  control and as the value the advisor published for `f2fedd58`.

### 6.7 Channel separation under programme law §0.9.33

§0.9.33 says a census quantity crosses Apple Silicon generations if and only if
the algorithm determines it, not the machine. This change produces evidence in
both classes and they must not be added together, so here they are separated.

**Byte channel — transfers to M5 exactly.** The 27,698,336 B/step of §4 is a
count derived from the model geometry, the per-row cost model, and the measured
escape census. It contains no rate, no wall time, and no occupancy term. It is
the same number on M4 and on M5. Only the *rate* used to price it is the target
machine's own:

| basis | rate | priced saving | vs §0.5.8 3σ = 42.6 µs | score |
|---|---|---|---|---|
| M5 peak | 651.8 GB/s | **42.50 µs/step** | 2.99σ | **+0.633 %** |
| M5 effective | 546.2 GB/s | **50.71 µs/step** | 3.57σ | **+0.756 %** |
| M4 (this host) | 260.2 GB/s | 106.45 µs/step | — | — |

**This is the submitted claim.** It is receipt-resolvable at 2.3× the MDE on
either basis.

**Instruction channel — does NOT transfer.** The matched §6.6 pair moved decode
by 240.0 µs/step on M4 against a byte model that prices only 106.45 µs/step
there, leaving a 133.5 µs/step residual (observed/byte-model ratio 2.25). That
residual is real and is the expected sign: block-narrow o_proj issues 12 strided
byte loads per row at `h=64`, where lane-major issues one two-byte load plus one
base byte, and the brief's own independent estimate for that rung alone was
−70…−90 µs/step. But issue rate, address-generation cost, and scheduler
behaviour are machine-determined quantities in §0.9.33's non-transferring class.

Accordingly:

- I do **not** convert 133.5 µs/step to an M5 figure. The M4→M5 byte-arm factor
  0.399 is a bandwidth-ratio conversion and applying it to an instruction-channel
  residual would be a category error under §0.9.33.
- I do **not** fold the residual into the predicted score. The +0.633 %/+0.756 %
  above is byte-channel only.
- The residual is therefore **unpriced upside**, not headroom I am claiming. If
  it survives on M5 the receipt beats the prediction; if it does not, the
  prediction stands on its own.

The same rule retires the magnitudes of §6.2 and §6.5 from the transfer
argument. Those ladders are wall-clock measurements on M4 hardware. What they
contribute is not their microsecond values but two algorithm-class facts: the
mechanism is **live** on the scored path (complete arm separation, 25σ and 26σ),
and it is **monotone and additive** in the direction the byte census predicts
(`S→D` chained observed/predicted 1.00). Those facts transfer; the microseconds
do not.

---

### 6.8 The prefill question, closed: static proof plus a counterbalanced ABBA

§6.6 reported prefill **+0.931 %** on the candidate at n=1/arm. The advisor
priced that against the ranked window at **−0.338 % of score**, enough to eat
half the byte claim, so it had to be resolved rather than waved away. Two
independent lines now close it, and they agree.

**Line 1 — static reachability. Neither mechanism in this PR is reachable at
L = 512.** Verified at the current tree and, independently, at the `f2fedd58`
base via `git show f2fedd58:Sources/MLXFastModel/LagunaRuntimeModel.swift`:

| consumer | call sites | enclosing guard | verdict |
|---|---|---|---|
| o_proj `lagunaGatedAffineOProjNVFP4` (current) | `:6186`, `:6202` | `if` opens `:6139`; guard `:6140` = `gatePerHead, B == 1, L == 1, wo.bias == nil` | decode-only |
| o_proj at base `f2fedd58` | `:6160`, `:6176` — the `narrowScales:` argument lines are exactly `:6165` / `:6181` | `if` opens `:6112`; guard `:6114` = `gatePerHead, B == 1, L == 1` | decode-only |
| QKV `lagunaDecodeNVFP4QKVR1` (declared `:4810`) | exactly one caller, `:5761` | nested in `B == 1, L == 1` at `:5704-5705` (base `:5679`) | decode-only |

The advisor's anchors `6165`/`6181` are real, but they sit *inside* the
`L == 1` block; they are decode call sites, not prefill ones. Base and
candidate therefore issue **identical kernels with identical arguments for all
512 prefill rows**. The predicted prefill compute effect is exactly zero, and
the −0.338 % has no mechanism to act through.

**The one channel the static argument does not close** is residency, not
compute. `DARKBLOOM_ATTN_SCALE_NARROW_OPROJ` gates bank *construction* at
`LagunaRuntimeModel.swift:5483-5488`, so the shipped default leaves ~23.5 MB of
extra arrays resident, which could in principle perturb prefill through
allocator or page pressure.

**Line 2 — counterbalanced prefill ABBA measuring exactly that channel.**
`research/pr80_prefill_abba.sh`, one binary, arms selected by env:
`D` = shipped default (bank built), `S` = `..._NARROW_OPROJ=0` (bank not
built). Nine visits, `p00-discard D` then `D S S D D S S D`; each arm's
positions sum to 18, so any linear drift in position cancels. Per visit:
4 warm-up + **20 measured** whole-prompt `prefill` requests at L = 512, each
repetition using a **different** prompt so no identical-forward memo can serve
one repetition from another.

| pos | arm | mean (ms) | within-visit sd | median | min |
|---|---|---|---|---|---|
| p01 | D | 527.440 | 1.304 | 527.409 | 525.126 |
| p02 | S | 527.370 | 1.207 | 527.323 | 525.659 |
| p03 | S | 527.269 | 1.402 | 527.434 | 524.420 |
| p04 | D | 527.512 | 1.261 | 527.681 | 525.167 |
| p05 | D | 527.442 | 1.073 | 527.563 | 525.642 |
| p06 | S | 527.412 | 1.060 | 527.396 | 525.661 |
| p07 | S | 527.300 | 1.043 | 527.387 | 525.199 |
| p08 | D | 527.411 | 1.325 | 527.676 | 525.259 |

Arm D 527.451 ms (between-visit sd 0.037), arm S 527.338 ms (0.056).

```
D - S = +0.114 ms  = +0.022 % of S
pooled between-visit SE = 0.039 ms,  |t| = 2.91 on 3 dof  (t_crit = 3.18)
2*SE interval = [+0.035, +0.192] ms  =  [+0.007 %, +0.036 %]
```

**Reading.** The residency channel is at most marginal — |t| = 2.91 does not
clear the 3.18 two-tailed critical value at 3 degrees of freedom — and even its
95 %-style upper limit is **+0.036 % of prefill**. Prefill carries weight 0.25,
so the worst case is `0.25 × 0.036 % = −0.009 % of score`; the point estimate
is **−0.0054 %**. That is **37× smaller** than the advisor's priced −0.338 %
and **70× smaller** than the +0.633 % byte claim.

§6.6's +0.931 % is therefore **noise**, exactly as the static proof predicts:
on this scale +0.931 % would be +4.91 ms, and the ABBA excludes anything above
+0.192 ms with four counterbalanced visits per arm. Note the instrument is
sharp enough to say so: within-visit sd is ~1.2 ms (0.25 %), but the
between-visit sd of the 20-sample mean is only 0.04–0.06 ms, so the ABBA's
resolution is ~25× finer than the effect it is refuting.

**Caveat, stated plainly.** This is an M4 Pro measurement of an M4 Pro prefill
(527 ms here versus ~98 ms for the M5 candidate). Under programme law §0.9.33
the *microseconds* do not transfer. What transfers is the reachability fact —
which is source-level, machine-independent, and verified at both trees — plus
the algorithm-class conclusion that the only surviving channel is resident
bytes rather than issued work. If the ranked prefill nevertheless disagrees,
**the receipt wins** and the residency channel becomes the first place to look.

Analyzer: `research/pr80_prefill_analyze.py`. Log: supervised run
`784e8c2f-4735-4f01-8d4d-4487d3a9511e` (exit 0), thermal gate healthy
throughout (GPU 40.0 °C at start).

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

`research/` is not in `editablePaths`, so the eight research files on this
branch cost zero submitted bytes. Total growth is **4,247 B** against the 25 kB
allocation the advisor confirmed for this PR in comment 5200283249 (#80 = 25 kB,
#82 = 15 kB, #85 = 25 kB, 5 kB reserve) and the 262,144 B per-review allowance —
17 % of the allocation.

The same comment set a standing law that `LagunaRuntimeModel.swift` must retain
at least **20 kB** of per-file margin. This head leaves **44,537 B**, so it is
compliant with 24.5 kB to spare, and it would remain compliant even if the whole
25 kB allocation landed in that one file.

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

### 7.2 The second `baseline_advanced` (`f2fedd58` → `6a19fd74`) was not taken

A `baseline_advanced` event moved the advisor branch to `6a19fd74` after this
work was already rebased. I did **not** rebase again, and the advisor confirmed
that in comment 5200283249. The reason is checkable in one command:

```bash
git diff --name-only f2fedd58 6a19fd74
research/CURRENT_RESEARCH_STATE.md
```

One file, and it is not in `editablePaths`, so the intersection between that
advance and my submission surface is empty. Rebasing would have moved every line
anchor in §3.3 and invalidated the §7.1 verification chain in exchange for
nothing. `BASE_SHA` for this PR therefore stays `f2fedd58`, and the single
permitted rebase has been consumed exactly once.

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

---

## 11. Dispatch, ranked receipt, and channel release

Head is now `fc6c13d` (research files only). The **ranked commit is `2b030838`**, tag
`pr80-publish-head`; nothing under `editablePaths` has changed since the advisor
review, and the two commits above it touch `research/` only.

### 11.1 Dispatch disclosure — one conflict, no model fallback

| | |
|---|---|
| attempt 1 | `2026-08-06T05:00:26Z` — **conflict**: `account already has 1 submission(s) in flight for this benchmark (limit 1)`. No submission was created. |
| attempt 2 | `2026-08-06T05:04:15Z` — **OK**, submission `97a5090c-a408-4222-b6d6-dd85c4bce09e`, status `validating`, model `senpai`. |

Both attempts ran the **verbatim identical command**,
`mlxfast submit --model "senpai" --note-file /tmp/pr80_note.md`. Attempt 1 failed on
**channel occupancy**, which is not an explicit rejection of the model value, so the
campaign fallback rule was **not** triggered and **no model other than `senpai` was
ever used**. Recorded in `/tmp/pr80_dispatch.txt`.

One durable CLI fact worth having: **in-flight submissions are not listed by
`mlxfast submissions` at all** until they reach a terminal state. That is why no
`pending` row was visible during the conflict, and why `--all` (paginated,
stale-tailed) is useless for finding recent entries. The occupying submission was
`58e28b8` (04:42Z), which cleared on its own about 22 minutes after its own dispatch.

### 11.2 Ranked receipt — **PROMOTED, new record**

The six lines the advisor asked for, in the requested order. Nothing here is inferred;
every value is a field of the receipt's `officialMetrics`.

1. **Receipt ID** — `97a5090c-a408-4222-b6d6-dd85c4bce09e` (dispatched
   `2026-08-06T05:04:23.273Z`, measured `05:14:29Z`, terminal `05:26:43.321Z`).
2. **Correctness** — `passed_correctness = true`. `case_count = 11`,
   `checked_steps = 1344`,
   `first_failing_case / first_failing_step / first_failing_layer = null`,
   `partial_result = false`. `semantic_gpqa_passed = true` (9/9, judge
   `claude-opus-4-8`), `gpqa_ttft_passed = true` (9/9, measured 0.41 s, p50 0.071 s,
   cap 2.4 s).
3. **Error** — `error = ""` (empty). `rejectionReason = null`.
4. **Decode floor** — `decode_speedup = 2.82068398043601` against
   `decode_speedup_floor = 0.95` → `passed_decode_speedup_floor = true`. **PASS**,
   2.97× the floor.
5. **Prefill floor** — `prefill_speedup = 2.0014713863613727` against
   `prefill_speedup_floor = 0.95` → `passed_prefill_speedup_floor = true`. **PASS**,
   2.11× the floor.
6. **Ranking status** — `status = "accepted"`, `improved = true`,
   `promotionStatus = "promoted"`, `promotionReason = null`. **Promoted.** This is the
   first promoted receipt on the account.

**Normalised score.** `decode_spt = 0.0049083720703125`,
`prefill_spt = 0.00019120068359375`, so

```
norm_decode_su  = 0.013890  / 0.0049083720703125 = 2.829858821
norm_prefill_su = 0.0003845 / 0.00019120068359375 = 2.010976074
ns = 2.829858821^0.75 * 2.010976074^0.25         = 2.598216
S = 512000 * prefill_spt      =  97.8948 ms
T = 1000 * decode_spt - S/128 =   4.1436 ms
```

| ns | receipt | who |
|---|---|---|
| **2.598216** | **`97a5090` (this one)** | **us — promoted** |
| 2.575430 | `58e28b8` | us, 04:42Z |
| 2.556326 | `0d12366` | us, previous best of ours |
| 2.526002 | `21f1d1a` | metaspartan |
| 2.524190 | `46eeccf` | lBroth — the record this displaced |
| 2.516663 | `8415f63` | a-github-name |

`officialScore` 2.588827841 vs the previous best 2.552308140491 (`46eeccf`, lBroth,
promoted 2026-08-04T15:04:14Z) = **+0.036520, or +1.431 %**. The CLI table renders that
delta as `+0.03652 (+3.64%)`; I could not reproduce the `3.64 %` figure from any pair
of receipt fields, so treat the percentage in the CLI as a display artefact and use the
arithmetic above.

#### 11.2.1 The previous receipt is our exact base — so this is a real increment

`58e28b8`'s own submission note opens ``# Laguna XS 2.1 NVFP4 — candidate `f2fedd58` ``
and lists only the routed-expert scale planes (#72) and the Metal-literal reclamation
(#81). **`f2fedd58` is precisely this PR's base commit.** So the official M5 measured
`f2fedd58` at 04:49:44Z and `f2fedd58 + PR #80` at 05:14:29Z — 25 minutes apart,
differing by exactly the two-file diff under review. That is much better attribution
than I expected to be able to offer.

| | `58e28b8` = base | `97a5090` = base + #80 | change |
|---|---|---|---|
| `decode_seconds_per_token` | 0.00496813671875 | 0.00490837207031 | **−1.2176 %** |
| `prefill_seconds_per_token` | 0.000190995605469 | 0.000191200683594 | +0.1074 % (slower) |
| `decode_speedup` | 2.78882521978 | 2.82068398044 | +1.1424 % |
| `golden_hash` | `be7738fc…cf71` | `be7738fc…cf71` | **byte-identical** |
| `harness_hash` | `35fe8b02…` | `c037fea1…` | differs (binaries really differ) |
| `weights_hash` | `aff99430…` | `aff99430…` | identical |
| `checked_steps` | 1344 | 1344 | — |

Two independent readings of the decode increment:

- **raw** `decode_spt` ratio → **+1.2176 % decode → +0.913 % of score**;
- **drift-cancelled** (each receipt's speedup divided by its own same-session pinned
  baseline) → +1.1424 % decode → **+0.857 % of score**.

They agree to within 0.06 % of score because `baseline_decode_seconds_per_token` is a
stable normaliser: across the last 40 scored sessions its relative sd is **0.236 %**
(peak-to-peak 1.03 %). Call the decode increment **+0.86 % to +0.91 % of score**.

#### 11.2.2 Reconciliation with the submitted claim — the claim was conservative

| channel | µs/token | % of score |
|---|---|---|
| **submitted claim** (bytes @ M5 peak 651.8 GB/s, assuming a 5036 µs step) | 42.50 | **+0.633 %** |
| same bytes, corrected to the real 4908.4 µs `decode_spt` | 42.50 | +0.649 % |
| same bytes @ M5 *effective* 546.2 GB/s | 50.71 | +0.775 % |
| **observed** (raw, base → candidate) | **59.76** | **+0.913 %** |

The whole of the submitted claim's conservatism is one stale assumption: I priced
27,698,336 B/step against a 5036 µs decode step, and the actual frontier step is
4908 µs, so the same byte saving is worth 1.22× more of the score than I claimed.
Observed / effective-bandwidth = **1.18×**; the residual **+0.09…+0.14 % of score** is
the instruction channel I flagged as unpriced.

**The M4 instruction residual did not transfer, exactly as §0.9.33 says it must not.**
On M4 the residual was 133.5 µs against a 106.45 µs byte share — a ratio of **2.25×**.
On M5 it is 9.05 µs against a 50.71 µs byte share — a ratio of **0.18×**. The byte
census transferred to within 18 %; the M4 wall-clock residual over-stated the
instruction channel by more than an order of magnitude. I would not have known this
without the receipt, and it is the single most useful calibration fact I got out of
this run.

#### 11.2.3 Prefill on the ranked machine, and a caveat I have to raise myself

Raw prefill wall time rose **+0.107 %** — i.e. the candidate is a hair *slower* — from
97.7897 ms to 97.8948 ms. The receipt-level prefill instrument has a relative sd of
**1.99 %** across the last 40 sessions, so that shift is **0.05 σ**: no detectable
change, in either direction.

Do **not** read the drift-cancelled prefill number. It says `prefill_speedup` rose
+3.94 %, but that is an artefact: `baseline_prefill_seconds_per_token` is **8.4×
noisier** than the decode baseline (relative sd 1.99 % vs 0.236 %, peak-to-peak 6.7 %),
and my session drew `0.000382682697265625` — the **highest of the last twelve sessions,
+1.32 σ above the 40-session mean**. My headline `prefill_speedup = 2.0015` is
flattered by a slow baseline draw.

Since that inflates the reported `officialScore`, here is the correction, unprompted:

```
as measured                           officialScore = 2.588827841
both baselines set to 40-session mean officialScore = 2.573889892
previous best (46eeccf)                             = 2.552308140
  margin as measured         = +0.036520  (+1.431 %)
  margin baseline-normalised = +0.021582  (+0.846 %)
```

The promotion survives the correction with room to spare, but **+1.43 % overstates the
true margin; +0.85 % is the honest figure.**

#### 11.2.4 Correctness, confirmed on the ranked machine

`golden_hash` is **byte-identical** between the base receipt and this one —
`be7738fccd6a28807ae7d18c038cbbc9e1b05dab26b99b2f247358fdc67fcf71` in both — across
1344 checked steps and 11 cases, while `harness_hash` differs. That is direct M5
confirmation of the bit-identical claim that §5 had verified only locally (four-arm
bitwise certificate, digest `3447204b…`, M4). Note that I am **not** citing
`max_abs_diff = 0`: that field is a hardcoded literal in the receipt and is not
evidence of anything.

Other fields worth recording: `peak_ram_gb = 21`,
`process_resident_memory_gb = 0.11`, `bandwidth_gb_per_token = 0` and every `expert_*`
counter zero (expected — RAM-resident model, no expert cache),
`benchmark_wall_seconds = 52`, `timed_benchmark_seconds = 46`,
`correctness_seconds = 39`, `preflight_seconds = 0.00013`, `num_layers = 40`,
`weights_byte_count = 21568891382` across 9 files.

#### 11.2.5 What I am not claiming

- Not claiming the +1.431 % headline margin; §11.2.3 corrects it to +0.85 %.
- Not claiming the two receipts are a *harness-paired* A/B. Each has its own
  same-session baseline; the base-vs-candidate comparison is across sessions, and I
  lean on it only because `baseline_decode_spt` is demonstrably stable at 0.236 % and
  the two readings agree.
- Not claiming the instruction-channel residual is resolved. +0.09…+0.14 % of score is
  one measurement, comfortably inside the prefill-term noise of `ns`.
- Not claiming any of this generalises to a different frontier. It is one receipt on
  one base.

#### 11.2.6 How to get these fields

The CLI truncates `metrics` and has no `--json`. The full record is at
`GET https://api.mlx.fast/api/benchmarks/eigenlabs%2Fmlxfast-challenge/submissions`
with `Authorization: Bearer $MLXFAST_API_TOKEN`. One gotcha that cost me a cycle: the
secret is injected **only when the literal string `MLXFAST_API_TOKEN` appears in the
shell command text**, so a bare `python3 fetch.py` receives nothing — it has to be
written `MLXFAST_API_TOKEN="${MLXFAST_API_TOKEN:-}" python3 fetch.py`. The response is
~17 MB and every record carries its full note, so filter before printing. Everything in
this section is reproduced by `research/pr80_receipt_analyze.py`.

### 11.3 The advisor's §4 prefill premise, closed

Full treatment is in §6.8; the verdict in one place:

- **Static.** The advisor priced a possible prefill regression at **−0.338 % of score**
  on the premise that the o_proj narrow scale bank is read by prefill (anchors 6165 /
  6181 at `f2fedd58`). The anchors are real but sit **inside an `L == 1` block**, and
  the QKV lane-major kernel's single caller is likewise `B == 1, L == 1` gated. Base
  and candidate issue identical kernels with identical arguments for all 512 prefill
  rows, so the priced risk has no mechanism to act through. The only surviving channel
  is *residency*, not *issued work*.
- **Measured (M4, counterbalanced ABBA `784e8c2f`).** `D − S = +0.114 ms = +0.022 %`
  of prefill, `|t| = 2.91` on 3 dof (below `t_crit = 3.18`), 2·SE upper limit
  **+0.036 % of prefill** ⇒ worst case **−0.009 % of score**, 37× below the priced
  risk. §6.6's +0.931 % was noise.
- **Measured (M5, this receipt).** +0.107 % of prefill wall time = **0.05 σ** of the
  receipt instrument. The priced −0.338 % of score would have been −1.322 ms on a
  97.8 ms prefill — 12.6× larger than what was observed. Not present.

Three independent lines agree, and the ranked machine is the one that counts.

### 11.4 Channel released

The submission channel is **released to the advisor**. I am not merging and not
rebasing, per the review's §6 order of operations.

The five review findings (a)–(h) are recorded in the review thread and **not** actioned
in this PR, as instructed. For the queued `gate_sp` occupancy brief, ★(a) — the o_proj
register hoist — is the natural companion: `rb = bs[row]`
(`LagunaRuntimeModel.swift:4138`) and `sp[0]` (`:4143`) re-execute *inside* the K loop
for all 4 rows, where QKV correctly hoists `scale_bases[out_row]` plus one 2-byte
nibble load into `sb[]` before the loop (`:4749-4758`). Given §11.2.2 — the M5
instruction residual is 0.18× the byte share, not the 2.25× M4 suggested — I would now
price a pure instruction-side change conservatively until it has its own receipt.

One correction to my own §9 follow-up while it is fresh: the real binding constraint
behind the `groups % 64 == 0` guard is the **nibble packing** at
`LagunaRuntimeWeights.swift:915-922` — `blocks = groups / 32` with a
`view(dtype: .uint16)` that fuses adjacent blocks, so `blocks` must be **even** — and
*not* the pairwise split at `:906`. The correct general form is `blocks % 2 == 0`,
which should unblock the queued #72 × #35 composition.

_This section was written by an AI agent (OpenHands) acting as the Senpai research
student `maple-frieren`, on behalf of @morganmcg1._
