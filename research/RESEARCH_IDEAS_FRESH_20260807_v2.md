# Fresh Optimization Ideas v2 — 2026-08-07 (Subagent Investigation)

Ranked list of fresh, untried optimization directions found by deep
codebase analysis of the scored decode/prefill paths, vendor kernel
dispatch, MoE memory access patterns, scale halving correctness, and the
M5 submission failure root cause.

## CRITICAL FINDING: O-proj Scale Halving Has a Latent M5 Correctness Bug

**The O-proj NVFP4 scale halving (PR #192, commit c414eb5) omits the escape
byte handling that its own design document prescribes.** It was only
validated on M4, and M4 does not catch k=0 escape bugs (PR #198 also
passed M4 and failed M5). The current frontier (2f5d630) includes this
potentially buggy change.

### Evidence

1. **Design doc requires escape**: `research/SCALE_PLANE_HALVING_DESIGN.md`
   lines 118-136 explicitly prescribe an escape byte for the O-proj kernel:
   ```
   // Escape: (out_row + row == 0 && simd_lid == 1 && k == 0)
   if (out_row + row == 0 && simd_lid == 1 && k == 0) {
       sbits = escape_byte;
   }
   ```

2. **Implementation has NO escape**: `LagunaRuntimeModel.swift:5422-5430`
   just does `contiguous(preparedWO.scales[0..., .stride(from: 0, by: 2)])`
   — taking even-indexed bytes only, with no escape tensor. The halved
   kernels (`lagunaGatedAffineOProjNVFP4HalvedKernels` at L4340, and the
   activated twin at L4470) take only 4 inputs — no escape input.

3. **MoE kernels ALL use escape**: Every MoE halved kernel implements
   the k=0 escape:
   - Shared SwiGLU QMV: L6641,6656-6657,6691-6692 and L6736,6761-6762
   - Routed packed R1: L7465,7494-7495,7520-7521
   - Down residual: L6849,6880,6894 and L7791-7801

4. **M4 cannot catch this bug**: PR #198 (prefill MoE halving) had the same
   class of k=0 escape bug. It passed M4 correctness but failed M5.
   `CURRENT_RESEARCH_STATE.md` documents this explicitly.

5. **M5 submission 215e45f included BOTH PR #192 and PR #198**: The failure
   was attributed only to PR #198, but PR #192 may also be buggy. After
   reverting PR #198, the O-proj halving remains — if it's also buggy, the
   next M5 submission (2f5d630) would also fail.

6. **No M5 validation record exists for O-proj halving**: The commit
   message for PR #192 (commit 57804d3) claims "Correctness: PASSED
   (bit-exact, pairwise constancy verified)" but the body says this was
   M4-only. The upstream equivalence test
   (`Sources/MLXFastModel/LagunaUpstreamEquivalence.swift`) has no
   O-proj-specific checks; it's a generic end-to-end comparison that was
   never recorded as passing on M5 with the halving ON.

### Impact

If `scale[0] != scale[1]` for any O-proj weight row (which the NVFP4
quantizer's known bug in `fp_quantized.h` L2184-2195 can produce), the
halved kernel reads `scale[0]` for group 1 elements that should use
`scale[1]`. This is a numerical error that affects row 0 of every O-proj
output. On M5 with hidden 512-token teacher-forced cases, this could
cause a greedy token mismatch.

### Fix

Add escape byte handling to the O-proj kernel and prepare the escape
tensor at init time. See Idea 1 below for the implementation plan.

---

## Budget Reality (current frontier at 2f5d630)

| Constraint | Current | Limit | Headroom |
|---|---|---|---|
| LagunaRuntimeModel.swift | 521,648 B | 524,288 B | **2,640 B** |
| LagunaLmHeadPrune.swift | 43,506 B | 524,288 B | **480,782 B** |
| fp_quantized_nax.h (vendor) | 76,817 B | 524,288 B | **447,471 B** |
| quantized.cpp (vendor) | 82,721 B | 524,288 B | **441,567 B** |

**LRM is the binding constraint at 2,640 B headroom.** Kernel source string
changes in LRM must be very compact. Vendor kernel files and
LagunaLmHeadPrune.swift have ample headroom.

## Decode Bandwidth Breakdown

| Component | Per Step | % of Step |
|---|---|---|
| Attention weights (INT8 QKV+O-proj) | 684.7 MiB | 42.9% |
| MoE (NVFP4, 9 experts) | 526.5 MiB | 33.0% |
| LM head | 104.1 MiB | 6.5% |
| Router | 39 MiB | 2.4% |
| KV cache | 80 MiB | 5.0% |
| Dense MLP (layer 0, BF16) | 96 MiB | 6.0% |
| **Total** | ~1,597 MiB | 100% |

QKV NVFP4 scales: 47.5 MiB (NOT halved) — largest unhalved scale component.
O-proj NVFP4 scales: 18.75 MiB (already halved but missing escape).
MoE decode scales: ~6.5 MiB (already halved with escape).

---

## Idea 1: Fix O-proj Escape Byte Bug ★★★ CRITICAL (correctness)

**Priority**: 1 (MUST FIX before next M5 submission)
**Component**: Decode correctness — all 40 attention layers
**Mechanism**: The O-proj NVFP4 scale halving (PR #192) takes every other
scale byte (`scales[0..., .stride(from: 0, by: 2)]`) and reads
`scale[simd_lid / 2]` in the kernel. This is only bit-exact if
`scale[2k] == scale[2k+1]` for ALL k including k=0. The NVFP4 quantizer's
pairwise constancy guarantees this for k>=1, but k=0 can have
`scale[0] != scale[1]`. Every MoE halved kernel handles this with an
escape byte; the O-proj does not.

**Fix**: Two parts:

1. **Kernel**: Add an escape input and conditional:
```metal
// In lagunaGatedAffineOProjNVFP4Source, halved branch:
uint8_t sbits = sc[row * (\(scaleStride))];
if (out_row + row == 0 && simd_lid == 1 && k == 0) {
    sbits = oproj_escape[0];
}
```
The escape check `(out_row + row == 0 && simd_lid == 1)` is
loop-invariant for the k-block loop (only the first iteration needs it).
The kernel already has a k-block loop; peeling the first iteration or
adding the k==0 check inline are both viable.

2. **Init**: Add escape tensor preparation in `prepareNativeAffineOProjWeight`:
```swift
if preparedWO.mode == .nvfp4, preparedWO.bits == 4,
    preparedWO.groupSize == 16,
    lagunaOProjScaleHalvingEnabled
{
    let halved = contiguous(preparedWO.scales[0..., .stride(from: 0, by: 2)])
    preparedWO.scales = halved
    // Escape: row 0, byte 1 (the one k=0 exception)
    preparedWO.oProjEscape = contiguous(preparedWO.scales[0, 1].reshaped([1]))
}
```
And pass the escape as a 5th kernel input.

**Target code**:
- `LagunaRuntimeModel.swift:4146-4300` (kernel source — add escape conditional)
- `LagunaRuntimeModel.swift:4340-4360` (halved kernel — add escape input)
- `LagunaRuntimeModel.swift:4470-4490` (activated halved kernel — same)
- `LagunaRuntimeModel.swift:4497-4530` (dispatch — pass escape)
- `LagunaRuntimeModel.swift:5406-5432` (init — prepare escape tensor)

**Expected M5 signal**: Not a speed optimization — a correctness fix. If
the O-proj halving is currently buggy on M5, this fix makes it correct,
allowing the next M5 submission to pass correctness gates.

**Bit-exact risk**: The fix makes the halving MORE correct. The non-halved
path is unaffected. If `scale[0] == scale[1]` for all O-proj rows (lucky
case), the escape byte is never used and the fix is a no-op. If
`scale[0] != scale[1]` for any row, the fix corrects a latent bug.

**Budget impact**: ~200-300 B in LRM for the kernel escape conditional +
~100-200 B for init-time escape prep and dispatch changes. **Within the
2,640 B headroom but tight.** The escape conditional is ~3 lines of Metal
source; the init prep is ~5 lines of Swift; the dispatch change is ~3 lines.

**M4 testability**: YES — but M4 may not catch the bug (PR #198 passed M4
with a similar bug). The fix is verifiable by confirming `scale[0] !=
scale[1]` exists in the O-proj weight at runtime, then checking the halved
output matches the non-halved output for row 0.

**Why it's fresh**: Nobody has identified this latent bug. The O-proj
halving has been on the frontier since PR #192 (commit c414eb5) without
escape handling. This is the same class of bug that caused the M5 failure
of PR #198.

---

## Idea 2: QKV NVFP4 Scale Halving ★★☆ HIGH (decode bandwidth)

**Priority**: 2
**Component**: Decode (75% of score) — 47.5 MiB QKV scales unhalved
**Mechanism**: All 40 attention layers use NVFP4 (group-16) for QKV. The
fused QKV bank has scales `[totalRows, 128]` uint8 per layer. The design
doc (`SCALE_PLANE_HALVING_DESIGN.md` lines 84-112) prescribes halving with
escape but it was never implemented.

QKV scale bytes per layer:
- Full attention (48 heads, 10 layers): 8192 rows × 128 B = 1.0 MiB
- Sliding attention (64 heads, 30 layers): 10240 rows × 128 B = 1.25 MiB
- Total: 10×1.0 + 30×1.25 = 47.5 MiB

Halving saves 23.75 MiB per decode step = 1.49% of total decode bandwidth.
Score impact: 1.49% × 0.75 (decode weight) = **1.12% score improvement**.

**Fix**: The QKV bank is a concatenation of Q, K, V weights (each quantized
separately). Each sub-matrix has its own k=0 exception, so 3 escape bytes
are needed:
- Q row 0: `scales[0, 1]` (escape at fused row 0)
- K row 0: `scales[nHeads*headDim, 1]` (escape at fused row Q_rows)
- V row 0: `scales[nHeads*headDim + nKVHeads*headDim, 1]` (escape at fused row Q_rows+K_rows)

The kernel (`lagunaDecodeNVFP4QKVR1Source`, L4697) is compact (~40 lines).
Changes needed:
```metal
// BEFORE:
const device uint8_t* sc = weight_scales +
    out_row * in_vec_size_g + simd_lid;
// ...
sc += block_size / 16;  // advance by 32

// AFTER (halved):
constexpr uint packed_stride = in_vec_size_g / 2;  // 64
const device uint8_t* sc = packed_scales +
    out_row * packed_stride + (simd_lid / 2);
// ...
uint8_t sbits = sc[0];
if (out_row == 0 && simd_lid == 1) sbits = qkv_escape[0];
else if (out_row == q_rows && simd_lid == 1) sbits = qkv_escape[1];
else if (out_row == q_rows + kv_rows && simd_lid == 1) sbits = qkv_escape[2];
sc += block_size / 32;  // advance by 16 (half)
```

**Target code**:
- `LagunaRuntimeModel.swift:4697-4735` (kernel source — add halved variant)
- `LagunaRuntimeModel.swift:4736-4750` (kernel registration — add halved kernels)
- `LagunaRuntimeModel.swift:5435-5510` (init — prepare halved scales + escape)
- `LagunaRuntimeModel.swift:4752-4790` (dispatch — use halved path)

**Expected M5 signal**: 23.75 MiB / 1597 MiB = 1.49% decode bandwidth
reduction. At ~5.4 ms/step and 614 GB/s: saves ~0.039 ms = **~0.72% decode
speedup**. Score: 0.72% × 0.75 = **~0.54% score**. Combined with the
correct O-proj escape fix (Idea 1), total scale halving family is complete.

**Bit-exact risk**: LOW with escape bytes. The NVFP4 pairwise constancy
guarantees `scale[2k] == scale[2k+1]` for k>=1. The 3 escape bytes handle
the k=0 exception for each sub-matrix. Same pattern as the MoE kernels
which are already proven correct.

**Budget impact**: ~300-400 B in LRM for the kernel source (halved variant
with escape) + ~200 B for init-time escape prep. Total ~500-600 B. **Within
the 2,640 B headroom.** This is the largest bandwidth saving that fits in
the LRM budget.

**M4 testability**: YES. The QKV kernel runs on M4. Verify via
`--local-iterate` (max_abs_diff = 0) and upstream equivalence.

**Why it's fresh**: The design doc has the exact implementation plan but no
PR was ever created. QKV scales are the largest unhalved scale component
(47.5 MiB). This is the last major NVFP4 scale halving opportunity.

---

## Idea 3: Fixed Prefill MoE Scale Halving (Correct Escape for Tile-Interleaved Layout) ★★☆ MEDIUM (prefill bandwidth)

**Priority**: 3 (already assigned as PR #220 — this analysis provides the
correct fix)
**Component**: Prefill (25% of score) — prefill MoE gate/up scales
**Mechanism**: PR #198 attempted to halve the prefill MoE gate/up scales
(47.25 MiB prefill) but had a correctness bug in the escape indexing for
the tile-interleaved layout. The fused gate/up bank is constructed as:
```
[gate row 0-31, up row 0-31, gate row 32-63, up row 32-63, ...]
```
(via `concatenated([gateWeightTiles, upWeightTiles], axis: 2)` at L10024).

PR #198 sourced the up-row-0 escape from fused row 512 (the
non-interleaved position), but in the tile-interleaved layout, up row 0
is at **fused row 32** (tile 0, position 32-63).

**Fix**: The correct escape positions are:
- Gate row 0 byte 1: `fusedScales[expert, 0, 1]` (fused row 0)
- Up row 0 byte 1: `fusedScales[expert, 32, 1]` (fused row 32, NOT 512)

This is confirmed by the decode path's packed bank escape at
`preparePackedRoutedGateUpBank` (L10119-10125):
```swift
let gateEscape = packed[0..., 0, 1]      // walk-order index 0 → gate row 0
let upEscape = packed[0..., 128, 1]     // walk-order index 128 → up row 0
```
The walk-order indices 0 and 128 map to fused rows 0 and 32 respectively
(see the `logicalRow` / `gateRow` / `fusedRow` computation at L10088-10093).

**Target code**:
- `LagunaRuntimeModel.swift:10070-10130` (escape preparation — correct
  fused row indices)
- `fp_quantized_nax.h` (kernel — escape read logic, already in PR #198)
- `quantized.cpp` (dispatch — pass halved scales + escape)

**Expected M5 signal**: Prefill MoE gate/up scales: 256 experts × 1024
fused rows × 128 B = 31.25 MiB. Halving saves 15.6 MiB. Prefill MoE total
is 432 MiB, so 15.6/432 = 3.6% of prefill MoE bandwidth. Score: 3.6% × 0.25
= **~0.9% score**. Modest but real, and it's a pure prefill improvement.

**Bit-exact risk**: LOW with the correct escape indexing. The halving
math is identical to the decode MoE halving (PR #180, proven correct).
The only issue was the wrong escape row index.

**Budget impact**: ~0 B net change from PR #198 (which was already
written). The fix changes 2 lines of escape indexing. The vendor kernel
changes from PR #198 are already in the reverted commit and can be
re-applied with the fix.

**M4 testability**: NO — _nax kernels only compile on M5 (GPU gen 17+).
The escape indexing can be verified by code review against the decode
path's proven escape pattern.

**Why it's fresh**: This analysis provides the exact root cause and fix
for the PR #198 failure. The previous research noted the bug was in
"up-row-0 escape indexing" but did not identify the correct position
(fused row 32, not 512). This is critical for PR #220's implementation.

---

## Idea 4: Prefill Down Projection Scale Halving ★☆☆ MEDIUM (prefill bandwidth)

**Priority**: 4
**Component**: Prefill (25% of score) — prefill MoE down scales
**Mechanism**: The decode path already halves the routed down scales
(L10038-10049 in `prepareFusedRoutedGateUp`). The prefill path uses the
stock `downProj` (a `QuantizedSwitchLinear`) with non-halved scales via
`MLX.gatherQuantizedMM` (L9897).

Prefill down scales: 256 experts × 2048 rows × 32 B (group-16) = 16 MiB.
Halving saves 8 MiB. Prefill MoE total is 432 MiB, so 8/432 = 1.85% of
prefill MoE bandwidth. Score: 1.85% × 0.25 = **~0.46% score**.

**Fix**: This requires the same _nax kernel modification as PR #198 (the
down projection also uses `MLX.gatherQuantizedMM` with the expert-aligned
path). The down weight is `[experts, 2048, 256]` uint8 (NVFP4 packed) with
scales `[experts, 2048, 128]` uint8. Halving:
```swift
let downReshaped = downScales.reshaped([experts, 2048, 64, 2])
let halvedDown = contiguous(take(downReshaped, MLXArray([0]), axis: 3).squeezed(axis: 3))
let downEscape = contiguous(downScales[0..., 0, 1].reshaped([experts, 1]))
```
This is identical to the decode path's down halving (L10038-10049), just
applied to the prefill path's down projection.

**Target code**:
- `LagunaRuntimeModel.swift:9959-10070` (init — prepare halved down scales
  for prefill path, alongside the existing decode halving)
- `quantized.cpp` (dispatch — detect halved down scales and pass escape)
- `fp_quantized_nax.h` (kernel — the down projection also goes through
  `fp_gather_qmm_rhs_expert_nax`, which already has the halving support
  from PR #198)

**Expected M5 signal**: 8 MiB / 432 MiB = 1.85% prefill MoE bandwidth.
Score: ~0.46%. Modest but combines naturally with Idea 3 (same _nax kernel
modifications).

**Bit-exact risk**: LOW. Same NVFP4 pairwise constancy invariant. The down
projection's escape is at down row 0, byte 1 — one escape byte per expert.
The decode path already proves this pattern works (L10044-10049).

**Budget impact**: ~100-200 B in LRM (reuse the existing down halving
code, just apply to the prefill path) + ~50-100 B in quantized.cpp (detect
halved down scales). Within vendor file headroom.

**M4 testability**: NO — _nax kernel path, M5 only.

**Why it's fresh**: The decode down halving was done (PR #216), but the
prefill down halving was never attempted. It uses the same _nax kernel
infrastructure as Idea 3, so they should be implemented together.

---

## Idea 5: DARKBLOOM_EXPERT_GATHER_GROUPS=256 Sweep (Prefill, 0-byte) ★☆☆ LOW

**Priority**: 5 (free — combine with any M5 submission)
**Component**: Prefill (25% of score)
**Mechanism**: The prefill MoE gather-QMM kernel
(`fp_gather_qmm_rhs_expert_nax`) spreads 256 experts over `egroups`
threadgroups. The default is 256 (one expert per threadgroup), changed
from the previous 128. The env var `DARKBLOOM_EXPERT_GATHER_GROUPS`
controls this (quantized.cpp:1379-1392).

The comment at L1365-1378 says 256 "measures closer to the acceptance
ceiling in the single-shot harness regime." But 256 was only measured
against 64 and 128 — the sweep has not been formally submitted to M5.

**Fix**: Pure env var — already defaults to 256. Just include in the next
M5 submission and measure. If 256 is already the shipped default, this is
a no-op. If it was reverted, set `DARKBLOOM_EXPERT_GATHER_GROUPS=256`.

**Expected M5 signal**: ~0-2% prefill kernel gain. The trend (64→128→256)
suggests more threadgroups is better for L2 reuse.

**Bit-exact risk**: LOW. Same computation, different threadgroup tiling.

**Budget impact**: 0 bytes.

**M4 testability**: NO.

**Why it's fresh**: Only 64 and 128 were formally tested. 256 is the
current default but was never submitted as a standalone measurement.

---

## Summary: Priority Ranking

| # | Idea | Component | M5 Signal | Bit-Exact | Budget (LRM) | M4? | Priority |
|---|---|---|---|---|---|---|---|
| 1 | O-proj escape byte fix | Decode correctness | Safety fix | N/A | ~300-500 B | YES* | **1 — MUST FIX** |
| 2 | QKV NVFP4 scale halving | Decode 47.5 MiB | ~0.72% | LOW | ~500-600 B | YES | **2** |
| 3 | Fixed prefill MoE halving | Prefill 15.6 MiB | ~0.9% | LOW | ~0 B (re-apply) | NO | **3** (PR #220) |
| 4 | Prefill down scale halving | Prefill 8 MiB | ~0.46% | LOW | ~200 B | NO | **4** |
| 5 | EXPERT_GATHER_GROUPS sweep | Prefill | ~0-2% | LOW | 0 B | NO | **5** (free) |

*M4 testability for Idea 1: YES, but M4 may not catch the bug (same as
PR #198). Verify by checking `scale[0] != scale[1]` at runtime.

**Key recommendations**:

1. **Fix the O-proj escape byte (Idea 1) BEFORE the next M5 submission.**
   The current frontier (2f5d630) includes the O-proj halving without
   escape. If `scale[0] != scale[1]` for any O-proj row, the next M5
   submission will fail correctness gates — the same failure mode as
   PR #198. This is a blocking correctness issue, not an optimization.

2. **QKV scale halving (Idea 2) is the highest-impact bandwidth optimization
   that fits in the LRM budget.** 23.75 MiB savings (1.49% of decode
   bandwidth) with ~500-600 B of code. The design doc has the exact
   implementation plan.

3. **Ideas 3 and 4 should be implemented together** — they both modify the
   same _nax kernel infrastructure. The prefill gate/up halving (Idea 3,
   PR #220) and prefill down halving (Idea 4) share the same escape
   mechanism and can be submitted as one coherent change.

4. **Idea 5 is free** — include in any M5 submission at 0-byte cost.

---

## What Was Ruled Out (and why)

- **Attention scale halving (INT8)**: Attention QKV uses NVFP4 (halvable)
  but the gate-softplus and g_proj use INT8 group-32 — no pairwise
  constancy. PR #193 confirmed this (-2.7% regression). Dead.

- **GQA KV consolidation**: M5 Max has 48 MB SLC. KV cache per layer (2 MiB)
  fits in SLC, so 4x redundant GQA reads are served from on-chip cache, not
  DRAM. GQA consolidation yields minimal DRAM savings.

- **RMSNorm fusion into LM head**: DEAD — compute-bound, 4.9% regression.

- **Attention epilogue 1-pass**: DEAD — 32 KB threadgroup memory limit.

- **KV cache quantization**: NOT bit-exact, outside accepted envelope.

- **ops-800/QHOIST scheduling**: TOXIC on M5, reverted.

- **Transform-time layout changes**: The transform is contractually a
  byte-identical pass-through. All bandwidth-reducing layout optimizations
  happen at runtime load time in `prepareFusedRuntimeWeights()`.

- **Expert weight L2 reuse across threadgroups**: Each threadgroup reads
  unique weight rows (no data sharing). L2 caching doesn't help.

- **Scale load vectorization**: Scale bytes are already coalesced (32
  contiguous bytes per row). Scale traffic is 1/8 of weight traffic and
  already halved where applicable.

- **Non-expert prefill kernel**: The non-expert `fp_gather_qmm_rhs_nax`
  path is not used on M5 (expert-aligned path is default).

- **RUNSKIP pct**: Already at P=100 (full elision). No further gain.

- **Dense MLP re-quantization to NVFP4**: NOT bit-exact — NVFP4 introduces
  rounding error. The dense MLP must stay BF16.

- **Router weight quantization**: Changes top-8 selection, NOT bit-exact.
