# Next-Wave Experiment: Merge Shared QMV into Routed QMV Dispatch

## Status: READY TO ASSIGN (when a student becomes available)

## Causal Question

Does eliminating the shared expert SwiGLU QMV dispatch (dispatch 7 of 8 per MoE layer)
by computing it inside the routed R1 kernel's grid produce a measurable decode speedup?

## Mechanism

Currently per MoE layer decode (39 layers):
1. Residual+RMSNorm+Router GEMV (1 dispatch)
2. Router Top-8 selection (1 dispatch)
3. Routed gate/up QMV: `lagunaRoutedSwiGLUQMVPackedTop8R1Kernel` (1 dispatch, grid=131,072 TG)
4. Shared gate/up QMV: `lagunaSharedSwiGLUQMVRows1Kernel` (1 dispatch, grid=16,384 TG)
5. Routed+shared down+residual (1 dispatch)
= 5 MoE dispatches per layer

Merge eliminates dispatch 4. The shared expert QMV is computed by additional
threadgroups in the routed R1 kernel's grid.

## Scaffold Evidence

The code already has `mergedSharedActivated: MLXArray?` (line 9882) explicitly
designed for this: "Set when the routed and shared gate/up QMVs were issued as
one dispatch below, so the shared half of that same dispatch is handed to the
down projection instead of being issued again."

Currently `mergedSharedActivated` is always nil. Setting it non-nil causes
`fusedSharedDownInputs` (line 8087) to skip the shared QMV dispatch.

## Implementation

### New Kernel: `lagunaRoutedSharedSwiGLUQMVPackedTop8R1Kernel`

Extends the routed R1 kernel:
- **Inputs**: Add `shared_weight` (uint32, [2×512, 256]), `shared_scales` (uint8, [2×512, 128])
- **Outputs**: Add `shared_activated` (bfloat16, [1, 1, 512])
- **Grid**: `8*256*64 + 256*64 = 147,456` threadgroups (was 131,072)
- **ThreadGroup**: 64 threads (1 SIMD group, unchanged)

### Kernel Branching

```metal
uint group = threadgroup_position_in_grid.x;
constexpr uint routed_groups = 8 * 256 * 64;  // 131,072

if (group < routed_groups) {
    // EXISTING routed R1 logic (interleaved gate/up, expert-indexed weight bank)
    // Write to activated[expert_slot * 512 + logical_row]
} else {
    // NEW shared expert logic (sequential gate/up, flat weight bank)
    uint shared_group = group - routed_groups;
    uint shared_tile = shared_group / 64;
    uint shared_row = shared_tile * 2 + simd_group;
    
    // Shared weight: flat bank (NOT expert-indexed)
    const device uint8_t* gate_weight = shared_weight + shared_row * 1024 + lane * 8;
    const device uint8_t* up_weight = shared_weight + (shared_row + 512) * 1024 + lane * 8;
    const device uint8_t* gate_scale = shared_scales + shared_row * 128 + lane;
    const device uint8_t* up_scale = shared_scales + (shared_row + 512) * 128 + lane;
    
    // Same QMV + SwiGLU, same laguna_nvfp4_qdot_codes_16, same lagunaNvfp4RowScaleSuffix
    // Write to shared_activated[shared_row]
}
```

### Call Site Change

```swift
// Before:
activated = lagunaRoutedSwiGLUQMVPackedTop8(x, fusedWeight:, packedScales:, indices:)
// mergedSharedActivated = nil  (dispatch 4 still runs)

// After:
let (routedActivated, sharedActivated) = lagunaRoutedSharedSwiGLUQMVPackedTop8(
    x, routedWeight:, packedScales:, indices:, sharedWeight:, sharedScales:)
activated = routedActivated
mergedSharedActivated = sharedActivated  // dispatch 4 skipped
```

## Bit-Exactness

- Same `laguna_nvfp4_qdot_codes_16` function for both paths
- Same `lagunaNvfp4RowScaleSuffix` applied to both
- Same SwiGLU formula: `gate * sigmoid(gate) * up`
- Same accumulation order per row
- Only difference: where weight codes/scales are read from (device address)
- Result: **Bit-exact** — same codes, same scale bytes, same arithmetic

## Expected Impact

- Eliminates 39 dispatches per decode step (1 per MoE layer × 39 layers)
- The shared QMV kernel itself (16,384 TG × 64 threads) is ~12.5% the size of the
  routed R1 kernel (131,072 TG). Its dispatch overhead (~2-5 µs) × 39 = ~78-195 µs
- Plus the kernel execution time itself, which is now overlapped with routed compute
- Total estimated gain: 0.3-1.0% decode

## Risk

- **LOW numerical risk**: Bit-exact by construction
- **MEDIUM complexity**: Extending grid with branching logic
- **LOW protocol risk**: No change to serial non-speculative rule

## Submitted Paths

- `Sources/MLXFastModel/LagunaRuntimeModel.swift`

## Key Source References

- `lagunaRoutedSwiGLUQMVPackedTop8R1Kernel` (line 7288): Base kernel to extend
- `lagunaSharedSwiGLUQMVRows1Kernel` (line 6601): Shared logic to merge
- `lagunaSharedSwiGLUQMVRows1Enabled` (line 277): Default ON — Rows1 is active
- `mergedSharedActivated` (line 9882): Scaffold variable (currently always nil)
- `fusedSharedDownInputs` (line 8087): Receives mergedSharedActivated, skips dispatch if non-nil
- `lagunaRoutedSwiGLUQMVPackedTop8` (line 7410): Call site to modify
- `lagunaRoutedSwiGLUQMVPackedTop8R1Kernel` grid: 8*256*64 = 131,072
- `lagunaSharedSwiGLUQMVRows1Kernel` grid: 256*64 = 16,384

## Conflict Note

This experiment eliminates the shared QMV kernel that Thorfinn's PR #96 modifies.
Assign AFTER Thorfinn finishes, or note that Thorfinn's prefetch findings inform
whether prefetch should be added to the shared path within the merged kernel.
