# Merge Shared+Routed Gate/Up QMV Dispatch — Implementation Plan

## Executive Summary

The Laguna XS 2.1 decode path issues two separate gate/up SwiGLU QMV dispatches
per sparse layer per decode step: one for the 8 routed experts and one for the
shared expert. The down+residual kernel (line 7851) already merges 8 routed +
1 shared into a single 9-slot dispatch. This plan extends the same pattern to
the gate/up QMV, eliminating ~40 separate dispatches per decode step (1 per
sparse layer × 40 layers = 40), which is ~14% of the ~280 total decode
dispatches.

**Key constraint**: `sharedExpertIntermediateSize == moeIntermediateSize == 512`
(LagunaConfig.swift:32-33), so the shared expert has identical per-expert weight
geometry to a routed expert. The merge is geometrically straightforward.

**Numerical risk**: **ZERO**. Each expert's gate/up computation is independent;
the merge only changes which threadgroup computes which rows, not the
arithmetic per row. The SwiGLU activation is per-row, and the simd_sum
reduction order is unchanged.

---

## 1. Relevant Code Sections (Exact Line Numbers)

### 1.1 Flag declarations (lines 110-185)

```swift
// Line 114-115: shared SwiGLU QMV flag
let lagunaFusedSharedSwiGLUQMVEnabled =
    ProcessInfo.processInfo.environment["DARKBLOOM_FUSED_SHARED_SWIGLU_QMV"] != "0"

// Line 135-136: routed SwiGLU QMV flag
let lagunaFusedRoutedSwiGLUQMVEnabled =
    ProcessInfo.processInfo.environment["DARKBLOOM_FUSED_ROUTED_SWIGLU_QMV"] != "0"

// Line 128-130: routed+shared down+residual fusion flag (already merged!)
let lagunaFusedRoutedSharedDownResidualEnabled =
    ProcessInfo.processInfo.environment[
        "DARKBLOOM_FUSED_ROUTED_SHARED_DOWN_RESIDUAL"] != "0"

// Line 151-152: packed scales flag
let lagunaPackedScalesEnabled =
    ProcessInfo.processInfo.environment["DARKBLOOM_PACKED_SCALES"] != "0"

// Line 157-158: precomputed router keys flag
private let lagunaRouterPrecomputedKeysEnabled =
    ProcessInfo.processInfo.environment["DARKBLOOM_ROUTER_PRECOMPUTED_KEYS"] != "0"

// Line 7526-7527: R1 gate/up scheduling flag
let lagunaRoutedGateUpR1Enabled =
    ProcessInfo.processInfo.environment["DARKBLOOM_ROUTED_GATEUP_R1"] != "0"
```

### 1.2 Shared expert SwiGLU QMV kernel (lines 6689-6874)

```swift
// Line 6689-6767: lagunaSharedSwiGLUQMVKernel
//   name: "laguna_shared_nvfp4_swiglu_qmv_bf16_v1"
//   inputNames: ["input", "fused_weight", "fused_scales"]
//   Key constants:
//     input_width = 2048, output_width = 512, fused_width = 1024
//     packed_row_bytes = 1024, scale_row_bytes = 128, block_width = 512
//   Row addressing (CONCATENATED layout):
//     gate_row = first_row + row          (0..511)
//     up_row   = gate_row + output_width   (= gate_row + 512)
//   Scale addressing:
//     gate_scale = fused_scales + gate_row * 128 + block/16 + lane
//     up_scale   = fused_scales + up_row   * 128 + block/16 + lane

// Line 6771-6840: lagunaSharedSwiGLUQMVRows1Kernel (R1 variant, same layout)

// Line 6842-6874: lagunaSharedSwiGLUQMV() dispatch function
//   grid: (128 * 64, 1, 1) or (256 * 64, 1, 1) for R1
//   threadGroup: (64, 1, 1)
//   outputShapes: [[1, 1, 512]]
//   Weight shape: [1024, 256] uint32 = [2*512, 2048/8]
//   Scales shape: [1024, 128] uint8 = [2*512, 2048/16]
```

### 1.3 Routed expert SwiGLU QMV kernels

**Non-packed kernel** (lines 6976-7076):
```swift
// Line 6976: lagunaRoutedSwiGLUQMVKernel
//   name: "laguna_routed_nvfp4_swiglu_qmv_bf16_v2"
//   inputNames: ["input", "fused_weight", "fused_scales", "indices"]
//   Key constants:
//     input_width=2048, output_width=512, fused_width=1024
//     packed_row_bytes=1024, scale_row_bytes=128, block_width=512
//     routed_experts=8, tiles_per_expert=128
//   Row addressing (INTERLEAVED layout):
//     gate_row = (logical_row / 32) * 64 + logical_row % 32
//     up_row   = gate_row + 32
//   Scale addressing (PLAIN, scale_row_bytes=128):
//     gate_scale = expert_scales + gate_row * 128 + block/16 + lane
//     up_scale   = expert_scales + up_row   * 128 + block/16 + lane
//   Expert selection: expert = uint(indices[expert_slot])
//   Grid: (8 * 128 * 64, 1, 1), threadGroup: (64, 1, 1)
//   Output: [1, 1, 8, 1, 512]
```

**Packed-scales kernel** (lines 7229-7326):
```swift
// Line 7229: lagunaRoutedSwiGLUQMVPackedKernel
//   name: "laguna_routed_nvfp4_swiglu_qmv_packed_bf16_v1"
//   inputNames: ["input", "fused_weight", "packed_scales", "indices"]
//   Key constants:
//     scale_row_bytes=32 (packed walk-order)
//     scale_sub_bytes=8*32=256, scale_kblock_bytes=256, scale_tile_bytes=1024
//     packed_expert_bytes=128*1024=131072
//   Scale addressing (PACKED walk-order):
//     block_scales = tile_scales + (block/block_width) * scale_kblock_bytes
//     gate_scale = block_scales + sub * 2 * 32 + lane
//     up_scale   = gate_scale + 32
//     where sub = simd_group * 2 + row
//   Same interleaved code layout as non-packed.
```

**Packed Top8 precomputed-keys kernel** (lines 7368-7516):
```swift
// Line 7368: lagunaRoutedSwiGLUQMVPackedSelectedSource(prologue:expertExpression:)
//   Generates the kernel body string. The prologue is the top-8 selection code.
//   The expert expression is "top8_winner".
//
// Line 7493-7504: lagunaRouterTop8PrecomputedPrelude
//   Extracts the winner for THIS slot by running expert_slot+1 rounds:
//     for (uint r = 0; r <= expert_slot; ++r) {
//         top8_winner = laguna_router_top8_extract_round(top8_keys, top8_mask, lane);
//     }
//   Each round extracts one winner from the 256 expert keys via simd reduction.
//
// Line 7506: lagunaRoutedSwiGLUQMVPackedTop8Kernel
//   Uses the selected source with top8 prologue and "top8_winner" expert expression.
//   inputNames: ["input", "fused_weight", "packed_scales", "router_keys"]
//   Grid: (8 * 128 * 64, 1, 1), threadGroup: (64, 1, 1)
//   Output: [1, 1, 8, 1, 512]
```

**R1 Packed Top8 kernel** (lines 7529-7646):
```swift
// Line 7529: lagunaRoutedSwiGLUQMVPackedTop8R1Kernel
//   Same as above but one row per simdgroup (256 tiles instead of 128).
//   Includes depth-1 weight staging (lines 7569-7627) for latency hiding.
//   Grid: (8 * 256 * 64, 1, 1), threadGroup: (64, 1, 1)
//   Same row addressing: gate_row = (logical_row/32)*64 + logical_row%32
```

### 1.4 Down+residual kernel — the EXISTING merge pattern (lines 7851-7960)

```swift
// Line 7851: lagunaRoutedSharedDownResidualKernel
//   This kernel ALREADY merges 8 routed + 1 shared in one dispatch.
//   Key pattern (line 7871): shared_slot = 8
//   Line 7885: bool is_shared = slot == shared_slot;
//   Line 7886: uint expert = is_shared ? 0 : uint(indices[slot]);
//   Line 7888-7897: branches on is_shared for input/weight/scale pointers
//   Line 7925-7927: threadgroup shared memory sized (routed_experts + 1) * outputs_per_simd
//   Line 7951-7952: reduction reads shared_slot's down_outputs
//   THIS IS THE PATTERN TO REPLICATE FOR GATE/UP.
```

### 1.5 Shared expert prepare function (lines 8270-8298)

```swift
// Line 8292: let fusedWeight = concatenated([gate.weight, up.weight], axis: 0)
//   → [1024, 256] uint32, CONCATENATED (512 gate rows + 512 up rows)
// Line 8293: let fusedScales = concatenated([gate.scales, up.scales], axis: 0)
//   → [1024, 128] uint8, CONCATENATED
// Line 8296: _fusedGateUpSplit = gate.weight.dim(0)  // = 512
```

### 1.6 Routed expert prepare function (lines 10057-10140)

```swift
// Line 10108-10126: Interleave 32-row gate/up tiles
//   gateWeightTiles = gateWeight.reshaped([experts, split/32, 32, weightDepth])
//   upWeightTiles   = upWeight.reshaped([experts, split/32, 32, weightDepth])
//   fusedWeight = concatenated([gateWeightTiles, upWeightTiles], axis: 2)
//                 .reshaped([experts, 2*split, weightDepth])
//   → [256, 1024, 256] uint32, INTERLEAVED (32 gate, 32 up, 32 gate, 32 up, ...)
//   Same for scales: [256, 1024, 128] uint8
```

### 1.7 Packed routed scales prepare (lines 10151-10190)

```swift
// Line 10166-10186: Walk-order gather
//   rowBlocks = fusedScales.reshaped([experts, rows*4, 32])  // [256, 4096, 32]
//   order: for tile in 0..<(rows/8), for kblock in 0..<4, for sub in 0..<8:
//     logicalRow = tile*4 + sub/2
//     gateRow = (logicalRow/32)*64 + logicalRow%32
//     fusedRow = sub%2 == 0 ? gateRow : gateRow+32
//     order.append(fusedRow * 4 + kblock)
//   packed = contiguous(take(rowBlocks, MLXArray(order), axis: 1))
//   → [256, 4096, 32] uint8, walk-order packed
```

### 1.8 Forward path — gate/up dispatch and `??` fallback (lines 10243-10363)

```swift
// Line 10243: let activated: MLXArray
// Line 10248: var mergedSharedActivated: MLXArray?  // ALREADY DECLARED!
//   "Set when the routed and shared gate/up QMVs were issued as one dispatch
//    below, so the shared half of that same dispatch is handed to the down
//    projection instead of being issued again."

// Line 10272-10277: Top8 packed dispatch (production path)
//   activated = lagunaRoutedSwiGLUQMVPackedTop8(x, fusedWeight:, packedScales:, routerKeys:)

// Line 10280-10286: Non-precomputed packed dispatch
//   activated = lagunaRoutedSwiGLUQMVPacked(x, fusedWeight:, packedScales:, indices:)

// Line 10294-10299: Non-packed dispatch
//   activated = lagunaRoutedSwiGLUQMV(x, fusedWeight:, fusedScales:, indices:)

// Line 10318-10323: Down+residual fusion (consumes mergedSharedActivated)
//   let sharedInputs = sharedExpert.fusedSharedDownInputs(x, sharedActivation: mergedSharedActivated)
//   → If mergedSharedActivated is non-nil, skips re-issuing the shared QMV

// Line 8356-8362: fusedSharedDownInputs `??` fallback
//   let activated = sharedActivation ?? lagunaSharedSwiGLUQMV(x, ...)
//   → If sharedActivation (mergedSharedActivated) is nil, falls back to separate dispatch
```

---

## 2. Weight Bank Layout Differences (Byte-Level)

### 2.1 Per-Expert Geometry (identical)

| Property | Routed (per expert) | Shared |
|---|---|---|
| Gate weight | [512, 256] uint32 | [512, 256] uint32 |
| Up weight | [512, 256] uint32 | [512, 256] uint32 |
| Gate scales | [512, 128] uint8 | [512, 128] uint8 |
| Up scales | [512, 128] uint8 | [512, 128] uint8 |
| Packed row bytes | 1024 (256 uint32) | 1024 (256 uint32) |
| Total code bytes | 1024 × 1024 = 1,048,576 | 1024 × 1024 = 1,048,576 |
| Total scale bytes (unpacked) | 1024 × 128 = 131,072 | 1024 × 128 = 131,072 |

### 2.2 Code Bank Row Layout

**Routed — INTERLEAVED** (32-row tiles):
```
Row 0-31:   gate tile 0
Row 32-63:  up   tile 0
Row 64-95:  gate tile 1
Row 96-127: up   tile 1
...
Row 992-1023: up tile 15
```
Row mapping in kernel: `gate_row = (logical_row / 32) * 64 + logical_row % 32`,
`up_row = gate_row + 32`.

Built by `prepareFusedRoutedGateUp()` (line 10121-10123):
```swift
let fusedWeight = concatenated(
    [gateWeightTiles, upWeightTiles], axis: 2  // interleave 32-row tiles
).reshaped([experts, 2 * split, weightDepth])
```

**Shared — CONCATENATED** (512-row blocks):
```
Row 0-511:   all gate rows
Row 512-1023: all up rows
```
Row mapping in kernel: `gate_row = row`, `up_row = row + 512`.

Built by `prepareFusedSharedGateUp()` (line 8292):
```swift
let fusedWeight = concatenated([gate.weight, up.weight], axis: 0)
```

**Difference**: The kernel's gate_row/up_row addressing formula differs. The
routed formula `(logical/32)*64 + logical%32` cannot be used on the shared
bank without re-layout. Conversely, the shared formula `row` / `row+512`
cannot be used on the routed bank.

### 2.3 Scale Bank Layout

**Routed UNPACKED scales** (used by non-packed kernel, scale_row_bytes=128):
```
Per expert: [1024, 128] uint8
gate_scale = expert_scales + gate_row * 128 + block/16 + lane
up_scale   = expert_scales + up_row   * 128 + block/16 + lane
```
Same as shared's scale layout (128 bytes per row, straightforward row indexing).

**Routed PACKED scales** (used by packed/Top8 kernels, scale_row_bytes=32):
```
Per expert: [4096, 32] uint8 = 131,072 bytes
Layout: [tile 128][k-block 4][sub 8][32 bytes]
  tile  = tile index (0..127), each tile covers 4 output rows
  kblock = K-block index (0..3), each covers 512 input elements (block_width)
  sub   = (simd_group * 2 + row) * 2 + {0=gate, 1=up}
  32 bytes = one scale byte per lane (32 lanes per simdgroup)
packed_expert_bytes = 128 * 4 * 8 * 32 = 131,072
```

The packed layout bakes the routed row remap (`gateRow = (logicalRow/32)*64 +
logicalRow%32`, `up = gateRow+32`) into scale storage order. The code bank is
NOT re-laid-out — only scales are reorganized into walk-order.

**Shared scales**: [1024, 128] uint8, plain row-major, no packing.

### 2.4 Summary: What Must Change

To merge the shared expert into the routed gate/up dispatch, the shared
expert's code and scales must be in the **same format as one routed expert**:
- **Codes**: interleaved 32-gate / 32-up (re-layout from concatenated)
- **Scales**: packed walk-order with scale_row_bytes=32 (re-pack from plain 128)

This is a prepare-time re-layout, NOT an offline transform change. The offline
transform (`Sources/MLXFastTransform/`) passes weights through unchanged.

---

## 3. Implementation Approach: Prepare-Time Re-layout (Recommended)

### 3.1 Why Re-layout Beats Kernel Branching

**Kernel branch approach** (pass shared bank as separate input, branch in
kernel on `expert_slot == 8`):
- Pro: no prepare-time work
- Con: the kernel needs two different row-addressing formulas (interleaved vs
  concatenated) and two different scale layouts (packed 32B vs plain 128B).
  This doubles the address computation complexity in the hot kernel body and
  creates divergent control flow within the dispatch.
- Con: the R1 kernel (lines 7529-7646) has depth-1 weight staging that
  pre-loads `gate_codes`/`up_codes` before the block loop. A branch would
  require duplicated staging code for the shared layout.

**Prepare-time re-layout approach** (re-layout shared codes to interleaved,
re-pack shared scales to walk-order, then the kernel treats slot 8 identically
to slots 0-7):
- Pro: the kernel body is unchanged for all slots. Only the bank-pointer
  selection branches (same as the down+residual kernel at line 7885-7897).
- Pro: the re-layout is bit-exact (just row reordering, no recomputation).
- Pro: the R1 depth-1 staging works identically for slot 8.
- Con: ~1,048,576 bytes additional resident memory per sparse layer for the
  re-laid-out shared code bank (the original concatenated bank stays for the
  fallback path). ~40 layers × 1 MB = ~40 MB additional. Acceptable on 128 GB.
  The packed scales are ~131 KB per layer × 40 = ~5.2 MB additional.
- Con: ~40-50 lines of Swift prepare code.

**Decision**: Prepare-time re-layout. The kernel stays simple; the cost is
one-time memory and a small prepare function. This mirrors how the routed
bank itself is built (interleave at prepare time, not in-kernel).

### 3.2 New Prepare Function

```swift
/// Re-layouts the shared expert's gate/up codes from concatenated
/// (512 gate + 512 up) to the routed-compatible interleaved layout
/// (32 gate, 32 up, ...) and packs scales into walk-order, matching
/// one routed expert's fused bank geometry exactly.
func prepareMergedSharedGateUp() -> [MLXArray] {
    guard _mergedSharedGateUpWeight == nil,
        let gate = gateProj as? QuantizedLinear,
        let up = upProj as? QuantizedLinear,
        // ... same guards as prepareFusedSharedGateUp (lines 8272-8291) ...
    else { return [] }

    let split = gate.weight.dim(0)           // 512
    let pairRows = 32
    let weightDepth = gate.weight.dim(1)     // 256
    let scaleDepth = gate.scales.dim(1)      // 128

    // Interleave 32-row gate/up tiles (same as prepareFusedRoutedGateUp)
    let gateWeightTiles = gate.weight.reshaped([split / pairRows, pairRows, weightDepth])
    let upWeightTiles = up.weight.reshaped([split / pairRows, pairRows, weightDepth])
    let fusedWeight = concatenated(
        [gateWeightTiles, upWeightTiles], axis: 1  // [16, 64, 256]
    ).reshaped([2 * split, weightDepth])           // [1024, 256]

    let gateScaleTiles = gate.scales.reshaped([split / pairRows, pairRows, scaleDepth])
    let upScaleTiles = up.scales.reshaped([split / pairRows, pairRows, scaleDepth])
    let fusedScales = concatenated(
        [gateScaleTiles, upScaleTiles], axis: 1  // [16, 64, 128]
    ).reshaped([2 * split, scaleDepth])           // [1024, 128]

    _mergedSharedGateUpWeight = fusedWeight

    // Pack scales into walk-order (same as preparePackedRoutedGateUpBank
    // but for a single expert — no experts dimension, so take axis is 0)
    let rows = 2 * split  // 1024
    let rowBlocks = fusedScales.reshaped([rows * 4, 32])  // [4096, 32]
    var order = [Int32]()
    order.reserveCapacity(rows * 4)
    for tile in 0..<(rows / 8) {
        for kblock in 0..<4 {
            for sub in 0..<8 {
                let logicalRow = tile * 4 + sub / 2
                let gateRow = (logicalRow / 32) * 64 + logicalRow % 32
                let fusedRow = sub % 2 == 0 ? gateRow : gateRow + 32
                order.append(Int32(fusedRow * 4 + kblock))
            }
        }
    }
    // NOTE: axis is 0 here (no experts dim); routed version uses axis: 1
    // because its rowBlocks shape is [experts, rows*4, 32].
    let packedScales = contiguous(take(rowBlocks, MLXArray(order), axis: 0))
    _mergedSharedPackedScales = packedScales

    return [fusedWeight, packedScales]
}
```

### 3.3 New Retained Properties

Add alongside the existing `_fusedGateUpWeight` (shared) and
`_fusedRoutedGateUpWeight` (routed):

```swift
@UseState private var _mergedSharedGateUpWeight: MLXArray?
@UseState private var _mergedSharedPackedScales: MLXArray?
```

### 3.4 Merged Kernel

Extend `lagunaRoutedSwiGLUQMVPackedSelectedSource` (line 7368) with a
`hasShared: Bool` parameter. When true, add two extra inputs and a branch:

```swift
func lagunaRoutedSwiGLUQMVPackedSelectedSource(
    prologue: String, expertExpression: String, hasShared: Bool = false
) -> String {
    """
        constexpr uint input_width = 2048;
        constexpr uint output_width = 512;
        constexpr uint block_width = 512;
        constexpr uint values_per_lane = 16;
        constexpr uint routed_experts = 8;
        constexpr uint total_slots = \(hasShared ? "9" : "8");
        constexpr uint shared_slot = 8;
        constexpr uint fused_row_bytes = 1024;
        constexpr uint fused_expert_bytes = 1024 * fused_row_bytes;
        constexpr uint scale_row_bytes = 32;
        constexpr uint scale_sub_bytes = 8 * scale_row_bytes;
        constexpr uint scale_kblock_bytes = scale_sub_bytes;
        constexpr uint scale_tile_bytes = 4 * scale_kblock_bytes;
        constexpr uint packed_expert_bytes = 128 * scale_tile_bytes;

        uint group = threadgroup_position_in_grid.x;
        uint expert_slot = group % total_slots;
        uint tile = group / total_slots;
        uint simd_group = simdgroup_index_in_threadgroup;
        uint lane = thread_index_in_simdgroup;
        uint first_row = tile * 4 + simd_group * 2;
        uint expert;
        const device uint8_t* expert_weight;
        const device uint8_t* tile_scales;
        if (expert_slot < routed_experts) {
            \(prologue)
            expert = \(expertExpression);
            expert_weight = (const device uint8_t*)fused_weight
                + expert * fused_expert_bytes;
            tile_scales = packed_scales + expert * packed_expert_bytes
                + tile * scale_tile_bytes;
        } else {
            expert_weight = (const device uint8_t*)shared_weight;
            tile_scales = shared_packed_scales + tile * scale_tile_bytes;
        }

        // ... rest of the kernel body is IDENTICAL (same row addressing,
        // same qdot, same simd_sum, same SwiGLU) ...
        // Only the output write changes: expert_slot ranges 0..8
        // activated[expert_slot * output_width + first_row + row] = ...
    """
}
```

The kernel body after the expert/bank selection is textually identical because
the shared bank is now in the same interleaved+packed format as the routed
bank.

### 3.5 New Dispatch Function

```swift
func lagunaMergedRoutedSharedSwiGLUQMVPackedTop8(
    _ input: MLXArray,
    fusedWeight: MLXArray,
    packedScales: MLXArray,
    routerKeys: MLXArray,
    sharedWeight: MLXArray,
    sharedPackedScales: MLXArray
) -> MLXArray {
    let tiles = lagunaRoutedGateUpR1Enabled ? 256 : 128
    let totalSlots = LagunaConstants.numExpertsPerTok + 1  // 9
    let kernel = lagunaRoutedGateUpR1Enabled
        ? lagunaMergedRoutedSharedSwiGLUQMVPackedTop8R1Kernel
        : lagunaMergedRoutedSharedSwiGLUQMVPackedTop8Kernel
    return kernel(
        [input, fusedWeight, packedScales, routerKeys, sharedWeight, sharedPackedScales],
        grid: (totalSlots * tiles * 64, 1, 1),
        threadGroup: (64, 1, 1),
        outputShapes: [[1, 1, totalSlots, 1, LagunaConstants.moeIntermediateSize]],
        outputDTypes: [.bfloat16]
    )[0]
}
```

### 3.6 Forward Path Changes (lines 10243-10323)

In the `if lagunaFusedRoutedSwiGLUQMVEnabled` block (line 10249), add the
merged path BEFORE the existing routed-only dispatch:

```swift
if lagunaMergeSharedRoutedGateUpEnabled,     // NEW FLAG
    let sharedWeight = sharedExpert._mergedSharedGateUpWeight,
    let sharedPackedScales = sharedExpert._mergedSharedPackedScales,
    // ... all existing guards from lines 10250-10256 ...
    // ... plus shared bank shape guards ...
{
    lagunaTrace("merged routed+shared gate/up QMV + SwiGLU (packed, top8)")
    let merged = lagunaMergedRoutedSharedSwiGLUQMVPackedTop8(
        x,
        fusedWeight: fusedWeight,
        packedScales: packedBank,
        routerKeys: routerKeys,
        sharedWeight: sharedWeight,
        sharedPackedScales: sharedPackedScales
    )
    // Slots 0-7 are routed; slot 8 is shared
    activated = merged[0..<1, 0..<1, 0..<8, 0..<1, 0..<512]
    mergedSharedActivated = merged[0..<1, 0..<1, 8..<9, 0..<1, 0..<512]
        .reshaped([1, 1, LagunaConstants.sharedExpertIntermediateSize])
} else if lagunaPackedScalesEnabled, ... {
    // existing routed-only dispatch (lines 10258-10300)
}
```

The existing `mergedSharedActivated` variable (line 10248) is already plumbed
to `fusedSharedDownInputs(x, sharedActivation: mergedSharedActivated)` at
line 10323. When it is non-nil, the `??` fallback at line 8356-8358 skips the
separate shared SwiGLU dispatch. **No changes needed to the down path.**

### 3.7 R1 Variant

The R1 kernel (line 7529) also needs a merged variant. The same
`hasShared: Bool` parameter applies. The depth-1 staging code (lines 7569-7627)
works identically for the shared slot because the shared bank is in the same
interleaved+packed format.

---

## 4. DARKBLOOM Flag and A/B Test Approach

### 4.1 Flag Name

```swift
let lagunaMergeSharedRoutedGateUpEnabled =
    ProcessInfo.processInfo.environment[
        "DARKBLOOM_MERGE_SHARED_ROUTED_GATEUP"] != "0"
```

Default ON (consistent with all other DARKBLOOM fusion flags). Set `"0"` to
ablate and restore the separate shared + routed dispatches.

### 4.2 A/B Test

**A (flag ON)**: Single 9-slot merged dispatch per sparse layer per decode step.
Shared expert's gate/up is computed in slot 8 of the same dispatch.

**B (flag OFF)**: Two separate dispatches:
1. 8-slot routed gate/up dispatch (existing `lagunaRoutedSwiGLUQMVPackedTop8`)
2. Separate shared gate/up dispatch (`lagunaSharedSwiGLUQMV`)

Both A and B produce identical `activated` and `sharedActivated` values
(bit-exact). The difference is purely dispatch count and scheduling.

### 4.3 Verification

1. **Correctness**: Run `research/run_upstream_equivalence.sh` with the flag ON
   and OFF. Both must pass the 64-step drift tripwire.
2. **Timing**: `./benchmark.sh --local-iterate` with flag ON vs OFF, same host,
   same thermal gate. Compare decode seconds/token.
3. **Prefill**: The merged path is decode-only (guarded by `x.dim(1) == 1`).
   Prefill must use the stock path unchanged.

---

## 5. Files to Edit

All edits are in files listed in `benchmark.json`'s `editablePaths`:

| File | Edit | In editablePaths? |
|---|---|---|
| `Sources/MLXFastModel/LagunaRuntimeModel.swift` | Flag, prepare function, merged kernel, dispatch function, forward path | Yes (`Sources/MLXFastModel/`) |
| `Sources/MLXFastTransform/*.swift` | **No changes** — re-layout is runtime, not offline | N/A |

**No other files need editing.** The Metal kernels are embedded as string
literals in `LagunaRuntimeModel.swift`, so no `.metal` files change. The
vendored MLX kernel headers (`lagunaSharedSwiGLUQMVHeader`, etc.) are reused
as-is.

---

## 6. Estimated Code Growth

| Component | Estimated bytes |
|---|---|
| Flag declaration (1 line) | ~120 |
| `_mergedSharedGateUpWeight` + `_mergedSharedPackedScales` properties | ~120 |
| `prepareMergedSharedGateUp()` function (~45 lines) | ~2,000 |
| `hasShared` parameter + branch in source generator (~20 lines Metal) | ~600 |
| 2 new kernel definitions (Top8 + R1 Top8, wrappers only) | ~800 |
| `lagunaMergedRoutedSharedSwiGLUQMVPackedTop8()` dispatch function | ~500 |
| Forward path branch + extraction (~15 lines) | ~700 |
| Comments / whitespace | ~500 |
| **Total estimated growth** | **~5,300 bytes** |

**Budgets**:
- Per-file: `LagunaRuntimeModel.swift` is 512,331 bytes; limit is 524,288.
  Headroom: 11,957 bytes. **5,300 < 11,957 ✓**
- Per-submission growth: limit 262,144 bytes. **5,300 < 262,144 ✓**
- Total surface: current 2,996,505 bytes; limit 3,000,000.
  Headroom: **3,495 bytes**. **5,300 > 3,495 ❌ FAILS**

### ⚠️ CRITICAL: Total Surface Budget Is the Binding Constraint

The total editable surface has only **3,495 bytes** of headroom against the
3,000,000 byte cap. The naive implementation (~5,300 bytes) exceeds this by
~1,800 bytes. The student MUST either:

**Strategy 1 — Minimize new code to ≤3,400 bytes:**
- Do NOT create a separate `prepareMergedSharedGateUp()` function. Instead,
  extend the existing `prepareFusedSharedGateUp()` (line 8270) to ALSO produce
  the interleaved + packed bank as additional retained properties. This reuses
  the existing guard chain and eval path, saving ~800 bytes of duplicate guards.
- Use a single kernel variant (non-R1) for the initial experiment. The R1
  merged kernel can be added in a follow-up submission after dead code removal
  creates more headroom. This saves ~800 bytes.
- Minimize comments to essential-only. Every byte counts.
- Inline the dispatch function into the forward path (no separate
  `lagunaMergedRoutedSharedSwiGLUQMVPackedTop8` wrapper). Saves ~300 bytes.

**Strategy 2 — Remove dead code first to create ≥6,000 bytes headroom:**
- Search for unused DARKBLOOM flags, stale comments, or dead kernel variants
  that can be safely removed. Each removed flag + its dead code path frees
  bytes.
- Candidates: any ablation flag that has been permanently ON and whose OFF
  path is never exercised. Check `git log` for flags that were promoted and
  never ablated again.
- The `lagunaRoutedSwiGLUQMVRows1Kernel` (line 7081) and its non-R1 sibling
  may have a dead variant if R1 is always selected.
- Removing ~2,500 bytes of dead code + the minimal ~3,400 byte implementation
  = ~5,900 bytes net growth, fitting in the 3,495 + 2,500 = 5,995 byte budget.

**Strategy 3 — Two-submission approach:**
- Submission 1: Remove dead code (net negative growth, creates headroom).
- Submission 2: Add the merge (uses the created headroom).
This is the safest approach if dead code identification is uncertain.

### Revised Minimal Implementation (~3,400 bytes)

| Component | Estimated bytes |
|---|---|
| Flag declaration (1 line) | ~120 |
| 2 retained properties (2 lines) | ~120 |
| Extended `prepareFusedSharedGateUp` (+~25 lines for interleave + pack) | ~1,100 |
| `hasShared` branch in source generator (~15 lines Metal) | ~500 |
| 1 new kernel definition (non-R1 Top8 only) | ~450 |
| Forward path branch + inline dispatch + extraction (~12 lines) | ~600 |
| Minimal comments | ~300 |
| **Total** | **~3,190 bytes** |

---

## 7. Numerical Risk Assessment

### 7.1 Per-Row Computation: Unchanged

Each output row's computation is:
1. Load 16 BF16 input values (from the same `x` vector)
2. Load gate code word (uint2) + scale byte (uint8)
3. `laguna_nvfp4_qdot_16` → float dot product (16 elements)
4. `laguna_nvfp4_scale` → E4M3 scale dequantization
5. Accumulate across 4 K-blocks (block 0..3)
6. `simd_sum` across 32 lanes
7. Cast to BF16 with `lagunaNvfp4RowScaleSuffix` (×2^22)
8. SwiGLU: `silu(gate) * up`

This sequence is **identical** regardless of whether the row is computed by
the routed kernel or the shared kernel, because:
- The re-laid-out shared bank has the same bytes at each (gate_row, block)
  address as the concatenated bank had at the corresponding address.
- The packed shared scales have the same scale bytes at each (tile, kblock,
  sub, lane) address as the plain scales had at the corresponding address.
- The `laguna_nvfp4_qdot_16` and `laguna_nvfp4_scale` functions are the same.
- The `simd_sum` reduction order across 32 lanes is the same.
- The BF16 cast and SwiGLU are the same.

### 7.2 Accumulation Order: Unchanged

The K-block accumulation order (block 0 → 1 → 2 → 3) is the same. The
`simd_sum` tree reduction order is the same. The R1 depth-1 staging loads the
same bytes in the same order (it just prefetches block b+1 while computing
block b, which doesn't change results).

### 7.3 Cross-Expert Independence: Preserved

The gate/up kernel performs **no cross-expert reduction**. Each expert slot
writes to a separate output region (`activated[expert_slot * 512 + ...]`).
The only cross-expert reduction happens in the down+residual kernel, which is
unchanged.

### 7.4 Input Vector: Same `x`

All 9 slots read the same `x` vector. In the current code, the routed kernel
and shared kernel both read the same `x`. The merge does not change this.

### 7.5 Re-layout Correctness

The interleaved re-layout is a pure row permutation:
- Concatenated: gate rows [0..511], up rows [512..1023]
- Interleaved: for tile t (0..15): gate rows [t*32..(t+1)*32-1] at positions
  [t*64..t*64+31], up rows at positions [t*64+32..t*64+63]

The row mapping `(logical/32)*64 + logical%32` for gate and `+32` for up
exactly reverses this permutation, so the kernel reads the same physical
bytes as the concatenated kernel would for the same logical row.

The packed scale re-layout is the same walk-order gather already proven
correct for the routed bank (`preparePackedRoutedGateUpBank`, line 10151).
The only difference is no `experts` dimension.

### 7.6 Conclusion

**The merge is bit-exact (class A).** No accumulation order changes, no
precision changes, no new operations. The only change is which threadgroup
computes which rows, and the shared expert's bank is re-laid-out to match
the routed format.

---

## 8. Dispatch Count Analysis

### Current (flag OFF):
Per sparse layer per decode step:
- 1 × routed gate/up QMV dispatch (Top8, packed)
- 1 × shared gate/up QMV dispatch
- 1 × merged routed+shared down+residual dispatch
- = 3 dispatches

### Merged (flag ON):
Per sparse layer per decode step:
- 1 × merged routed+shared gate/up QMV dispatch (9 slots)
- 1 × merged routed+shared down+residual dispatch (9 slots)
- = 2 dispatches

### Savings:
- 1 dispatch × 40 layers = **40 dispatches eliminated per decode step**
- Total decode dispatches: ~280 → ~240 (14.3% reduction)

Each eliminated dispatch saves:
- Command buffer encoding overhead (~5-15 µs)
- Grid setup and threadgroup launch overhead
- One output buffer allocation/teardown

---

## 9. Complete Experiment Brief (Ready for Student Assignment)

### Title
Merge shared and routed expert gate/up QMV dispatches into a single 9-slot dispatch

### Hypothesis
The shared expert's gate/up QMV can be merged into the routed Top8 packed
QMV dispatch by re-laying-out the shared expert's weight bank from
concatenated (512 gate + 512 up) to interleaved (32 gate, 32 up, ...) format
at prepare time, and packing its scales into the same walk-order format as
the routed packed scales. This eliminates 40 dispatches per decode step (14%
of total), improving decode latency with zero numerical risk.

### Background
- The down+residual kernel (line 7851) already merges 8 routed + 1 shared in
  a single 9-slot dispatch. This experiment applies the same pattern to the
  upstream gate/up QMV.
- `sharedExpertIntermediateSize == moeIntermediateSize == 512`, so the shared
  expert has identical per-expert geometry to a routed expert.
- The `mergedSharedActivated` variable (line 10248) and the `??` fallback in
  `fusedSharedDownInputs` (line 8356) are already plumbed for this merge —
  they were designed to accept a pre-computed shared activation from a merged
  dispatch.

### Instructions to Student

1. **Read this plan thoroughly.** All line numbers refer to
   `Sources/MLXFastModel/LagunaRuntimeModel.swift` at the current frontier.

2. **Check byte budget first.** Run `senpai/check-editable-budget.sh "$BASE_SHA"`
   to confirm headroom. The total editable surface is near the 3,000,000 byte
   cap. If headroom is < 6,000 bytes, identify dead code or stale comments to
   remove before adding new code.

3. **Add the flag** (near line 136):
   ```swift
   let lagunaMergeSharedRoutedGateUpEnabled =
       ProcessInfo.processInfo.environment[
           "DARKBLOOM_MERGE_SHARED_ROUTED_GATEUP"] != "0"
   ```

4. **Add retained properties** alongside existing `_fusedGateUpWeight`:
   ```swift
   @UseState private var _mergedSharedGateUpWeight: MLXArray?
   @UseState private var _mergedSharedPackedScales: MLXArray?
   ```

5. **Implement `prepareMergedSharedGateUp()`** — see Section 3.2 above. This
   function re-layouts the shared expert's gate/up codes from concatenated to
   interleaved (same as `prepareFusedRoutedGateUp` does for routed experts,
   but without the experts dimension) and packs scales into walk-order (same
   as `preparePackedRoutedGateUpBank`, but for a single expert). Call it
   from the same prepare path that calls `prepareFusedSharedGateUp()`.

6. **Extend `lagunaRoutedSwiGLUQMVPackedSelectedSource`** (line 7368) with a
   `hasShared: Bool = false` parameter. When true:
   - Change `routed_experts = 8` to `total_slots = 9` and add `shared_slot = 8`.
   - Add `shared_weight` and `shared_packed_scales` to the input names.
   - Add the bank-selection branch (see Section 3.4) before the kernel body.
   - The rest of the body is unchanged.

7. **Create merged kernel definitions** for both non-R1 and R1 variants:
   ```swift
   private let lagunaMergedRoutedSharedSwiGLUQMVPackedTop8Kernel = MLXFast.metalKernel(
       name: "laguna_merged_routed_shared_nvfp4_swiglu_qmv_packed_top8keys_bf16_v1",
       inputNames: ["input", "fused_weight", "packed_scales", "router_keys",
                    "shared_weight", "shared_packed_scales"],
       outputNames: ["activated"],
       source: lagunaRoutedSwiGLUQMVPackedSelectedSource(
           prologue: lagunaRouterTop8PrecomputedPrelude,
           expertExpression: "top8_winner",
           hasShared: true),
       header: lagunaSharedSwiGLUQMVHeader + "\n" + lagunaDecodeRouterOrdinalHeader
           + "\n" + lagunaRouterTop8PrologueHeader,
       ensureRowContiguous: true
   )
   ```
   Do the same for the R1 variant (line 7529 pattern).

8. **Implement `lagunaMergedRoutedSharedSwiGLUQMVPackedTop8()`** — see
   Section 3.5. Grid: `(9 * tiles * 64, 1, 1)`. Output: `[1, 1, 9, 1, 512]`.

9. **Modify the forward path** (lines 10249-10300). Add the merged branch
   BEFORE the existing routed-only dispatch. When the flag is ON and all
   guards pass (including shared bank availability), issue the merged dispatch
   and split the output:
   - `activated = merged[..., 0:8, ...]` (routed, same shape as before)
   - `mergedSharedActivated = merged[..., 8:9, ...].reshaped([1, 1, 512])`
   The existing `fusedSharedDownInputs(x, sharedActivation: mergedSharedActivated)`
   at line 10323 will use `mergedSharedActivated` instead of falling back to
   the separate `lagunaSharedSwiGLUQMV` dispatch.

10. **Verify correctness**:
    - `swift build -c release --force-resolved-versions` must succeed.
    - `research/run_upstream_equivalence.sh` must pass with flag ON.
    - `research/run_upstream_equivalence.sh` must pass with flag OFF.
    - Both must produce identical greedy tokens.

11. **Measure timing**:
    - `./benchmark.sh --local-iterate` with flag ON.
    - `./benchmark.sh --local-iterate` with flag OFF (`DARKBLOOM_MERGE_SHARED_ROUTED_GATEUP=0`).
    - Compare decode seconds/token on the same host under the same thermal gate.
    - Record prefill seconds/token (should be unchanged — decode-only path).

12. **Report**: Submit structured results with:
    - W&B run links for both A (ON) and B (OFF).
    - Decode speedup ratio (A/B).
    - Prefill speedup ratio (A/B, expected ~1.0).
    - Upstream equivalence pass/fail for both.
    - `mlxfast: packed-scales` log output confirming the merged dispatch was taken.
    - Exact byte growth measured by `senpai/check-editable-budget.sh`.

### Expected Outcome
- Decode: 1-3% speedup from eliminating 40 dispatches (~14% of total).
  Each dispatch saves ~5-15 µs of command buffer overhead; 40 × ~10 µs = ~400 µs
  per decode step. At ~280 dispatches × ~10 µs = ~2.8 ms baseline, saving 400 µs
  is ~14% of overhead, but dispatch overhead is only part of decode latency
  (bandwidth-bound compute dominates), so net decode speedup is likely 1-3%.
- Prefill: unchanged (decode-only path).
- Correctness: bit-exact (class A — no accumulation order change).

### Risk
- **Low**: The merge follows the proven down+residual 9-slot pattern. The
  re-layout is bit-exact. The `mergedSharedActivated` plumbing already exists.
- **Byte budget**: Total surface is near the 3M cap. May require dead code
  removal first.
- **M4 vs M5**: The M5 selects `_nax` prefill kernels, but this is a decode-only
  change, so M4 timing is directional evidence. The threadgroup count increases
  from 8×128×64=65,536 to 9×128×64=73,728, which may interact with GPU core
  scheduling. Test on the M5 for the official verdict.

### Stopping Condition
- If decode speedup > 1.0 and upstream equivalence passes → submit for promotion.
- If decode speedup ≤ 1.0 → report negative result; the dispatch overhead
  savings may be masked by the additional grid size or scheduling effects.
- If upstream equivalence fails → debug the re-layout; the packed scales
  walk-order may have an off-by-one in the tile/sub mapping.
