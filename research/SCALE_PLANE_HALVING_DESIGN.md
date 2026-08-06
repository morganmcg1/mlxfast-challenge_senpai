# Scale Plane Halving via Quantizer Invariant — Design Document

## Mechanism

MLX's NVFP4 quantizer (group_size=16) has a verified pairwise-constancy invariant:
`scale[2k] == scale[2k+1]` for all `k >= 1` within each flattened weight matrix.
Only `k=0` (the first 32 elements = first 2 groups of row 0) can have
`scale[0] != scale[1]`.

This is caused by a bug in `fp_quantized.h` L2184-2195: the `group_size != 32`
branch uses `tidx.x` (global thread index) for the left/right split predicate
(`tidx.x < 16`), but `tidx.x` is the global index in a 1-D dispatch, so only
the first SIMD group (threads 0-31) has the correct split. All subsequent
SIMD groups have all threads with `tidx.x >= 16`, making the left half-maximum
always 0, so both halves get the same right half-maximum.

## Applicability

Our attention weights use NVFP4 (group_size=16):
- `DARKBLOOM_NATIVE_AFFINE_NVFP4` defaults ON → ALL attention layers use NVFP4
- `lagunaNativeAffineNVFP4From` defaults to "0" → ALL layers from layer 0

Kernels affected:
- `lagunaDecodeNVFP4QKVR1Source` (QKV decode, L4583): uint8 scales, 128 B/row
- `lagunaGatedAffineOProjNVFP4Source` (O-proj decode, L4099): uint8 scales,
  384 B/row (full) / 512 B/row (sliding)

NOT affected:
- Gate-softplus (group_size=32, bfloat scales): no pairwise constancy
- g_proj (group_size=32, affine INT8): no pairwise constancy
- MoE kernels (DARKBLOOM_PACKED_SCALES is a separate reordering, not this)

## Scale Traffic Per Step

| Path | Layers | Rows/layer | Bytes/row | Total |
|------|--------|------------|-----------|-------|
| QKV sliding | 16 | 10240 | 128 | 20 MiB |
| QKV full | 24 | 8192 | 128 | 24 MiB |
| O-proj sliding | 16 | 2048 | 512 | 16 MiB |
| O-proj full | 24 | 2048 | 384 | 18 MiB |
| **Total** | | | | **78 MiB** |

Halving via packing: **39 MiB saved per decode step**.
At M5 651.8 GB/s: ~60 us saved per 5376 us step = **~1.1% decode improvement**.

## Implementation Design

### Transform-Time Packing (LagunaRuntimeWeights.swift or LagunaRuntimeModel.swift)

After `quantized(weight, groupSize: 16, bits: 4, mode: .nvfp4)` produces
`scales` as uint8 [rows, hidden/16]:

1. Create `packedScales` as uint8 [rows, hidden/32] (half the columns)
2. For each row r:
   - For each pair k = 0, 1, 2, ..., hidden/32 - 1:
     - If r == 0 and k == 0:
       - Store scale[0,0] in packedScales[0,0]
       - Store scale[0,1] in escapeByte (one byte per weight matrix)
     - Else:
       - Assert scale[r, 2k] == scale[r, 2k+1] (crash if violated)
       - Store scale[r, 2k] in packedScales[r, k]
3. Pass `packedScales` + `escapeByte` to the kernel instead of `scales`

### Kernel Changes (LagunaRuntimeModel.swift)

#### QKV Kernel (L4583-4620)

BEFORE:
```metal
const device uint8_t* sc = weight_scales +
    out_row * in_vec_size_g + simd_lid;
// ...
for (uint k = 0; k < axis_size; k += block_size) {
    result += laguna_tail_nvfp4_qdot(
        ws, x_thread, laguna_tail_nvfp4_scale(sc[0]));
    ws += block_size / 2;
    sc += block_size / 16;  // advance by 32
    column += block_size;
}
```

AFTER:
```metal
constexpr uint packed_stride = in_vec_size_g / 2;  // 64
const device uint8_t* sc = packed_scales +
    out_row * packed_stride + (simd_lid / 2);
// ...
// Peel first iteration for escape handling
{
    uint8_t sbits = sc[0];
    if (out_row == 0 && simd_lid == 1) {
        sbits = escape_byte;  // the one exception per matrix
    }
    result += laguna_tail_nvfp4_qdot(
        ws, x_thread, laguna_tail_nvfp4_scale(sbits));
    ws += block_size / 2;
    sc += block_size / 32;  // advance by 16 (half of 32)
    column += block_size;
}
// Remaining iterations (no escape needed)
for (uint k = block_size; k < axis_size; k += block_size) {
    result += laguna_tail_nvfp4_qdot(
        ws, x_thread, laguna_tail_nvfp4_scale(sc[0]));
    ws += block_size / 2;
    sc += block_size / 32;
    column += block_size;
}
```

Note: `simd_lid / 2` maps lanes 0,1 → packed[0], lanes 2,3 → packed[1], etc.
This is correct because scale[2k] == scale[2k+1] for k >= 1.
The escape handles the sole exception at (row 0, lane 1, block 0).

#### O-proj Kernel (L4099-4252)

The O-proj kernel has a more complex scale access pattern:
```metal
uint8_t sbits = sc[row * in_vec_size_g];
```
where `sc = weight_scales + out_row * in_vec_size_g + simd_lid`.

With packing:
```metal
const device uint8_t* sc = packed_scales +
    out_row * (in_vec_size_g / 2) + (simd_lid / 2);
// ...
uint8_t sbits = sc[row * (in_vec_size_g / 2)];
// Escape: (out_row + row == 0 && simd_lid == 1 && k == 0)
if (out_row + row == 0 && simd_lid == 1 && k == 0) {
    sbits = escape_byte;
}
```

The escape check can be hoisted: `(out_row + row == 0 && simd_lid == 1)`
is loop-invariant for the k-block loop (since k starts at 0, only the first
iteration needs the escape). Peel the first k-block iteration.

### Bit-Exactness

This change is bit-exact:
- The packed scale values are the SAME as the original scale values
- No precision or rounding change
- The escape ensures the one exception pair is handled correctly
- The quantizer invariant is verified at pack time (assert)

### Budget

- Transform code: ~200-300 bytes (packing function + escape)
- Kernel code: ~200-300 bytes (modified scale access + escape handling)
- Total: ~500-600 bytes, well within the 32K headroom

### Verification

1. `--local-iterate` for correctness (64-step drift tripwire)
2. `research/run_upstream_equivalence.sh` (expect bit-exact)
3. Same-host seconds/token comparison
4. Assert the pairwise constancy at pack time (crash if violated)

### Risk

- If the quantizer invariant does NOT hold for some weight matrices, the
  assert at pack time will crash. This is a correctness guarantee, not a risk.
- The M4 (bandwidth-bound) may show a larger gain than the M5 (instruction-bound)
  because the optimization saves bandwidth. But the instruction savings from
  fewer scale loads should also help on M5.
- The escape handling adds a small number of instructions (one conditional
  per kernel invocation, hoisted out of the inner loop).
