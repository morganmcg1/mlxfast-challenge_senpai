# Relocated commentary — `CompilableKVCache.swift`

Measurement narrative and design history moved verbatim out of `Vendor/mlx-swift-lm/Libraries/MLXLMCommon/CompilableKVCache.swift`
to free bytes on the capped editable submission surface. Line numbers refer to
the file as it stood at base `63ab67c8`. Nothing here is compiled or
submitted, and the code is unchanged (see
`research/frieren_comment_strip_check.sh`).

## `CompilableKVCache`

_relocated from lines 7-26 at base 63ab67c8_


Standard KVCacheSimple returns keys[..<offset] — a dynamically sized slice that
changes every decode step. This prevents compile() from tracing through the cache
because DynamicSlice requires static slice_size.

CompilableKVCache solves this by:
1. Pre-allocating a fixed-size buffer [B, H, maxLength, D]
2. Writing new keys/values via dynamicSliceUpdate (compile-traceable writes)
3. Returning the FULL buffer from update() — constant shape every step
4. Generating a boolean attention mask in makeMask() that marks active positions

The attention kernel handles the masking, computing only on valid positions.
This trades marginal redundant compute (masked zeros) for enabling compile()
to fuse hundreds of FFI crossings into a single compiled call.

Usage:
  // After prefill with standard cache, convert for compiled decode:
  let compilableCache = standardCache.map { c in
      CompilableKVCache(from: c, maxLength: 2048)
  }

## `CompilableKVCache`

_relocated from lines 38-44 at base 63ab67c8_


Key differences from KVCacheSimple:
- `offsetArray` (MLXArray) tracks position in the computation graph
- Pre-allocated buffer of fixed size (no dynamic growth during decode)
- `update()` returns the FULL buffer — mask handles which positions are valid
- `makeMask()` always returns an array mask covering the full buffer
- `innerState()` returns [keys, values, offsetArray] — all compile-tracked

## `offsetArray`

_relocated from lines 51-51 at base 63ab67c8_

Must be 1D (not scalar) for DynamicSlice start parameter compatibility.

## `attentionLength`

_relocated from lines 58-61 at base 63ab67c8_


This may be shorter than `maxLength` for a compiled fast view. Both
views still update the same full backing arrays; only the returned
attention slice and mask width differ.

## `maskRinds`

_relocated from lines 68-68 at base 63ab67c8_

Avoids re-creating every step.

## `line94`

_relocated from lines 94-94 at base 63ab67c8_

Copies the existing cache state into a fixed-size buffer.

## `line126`

_relocated from lines 126-126 at base 63ab67c8_

This triggers synchronous readback — avoid inside compiled paths.

## `line171`

_relocated from lines 169-171 at base 63ab67c8_

The attention mask from makeMask() handles which positions are valid.
This keeps tensor shapes constant across all decode steps,
enabling compile() to trace the entire forward pass.

## `sharingStorage`

_relocated from lines 183-186 at base 63ab67c8_


`MLXArray` has reference semantics and compiled state is advanced with
`_updateInternal`, so sharing these object identities lets either
compiled graph advance state that the other graph sees without a copy.

## `makeMask`

_relocated from lines 204-216 at base 63ab67c8_


Since update() returns the entire maxLength buffer, we ALWAYS need an array
mask to prevent attention to unwritten positions. The mask is boolean:
True = attend, False = don't attend (gets -inf in attention scores).

For decode (n=1): mask[0, j] = (j <= offset)
For prefill (n>1): mask[i, j] = (j <= offset + i)  (causal)

Note: `offset` here is the PRE-update value. After update, positions
0..<offset+n are valid, matching the mask exactly.

Uses `offsetArray` (MLXArray) for all computation so compile() can trace
the mask through the computation graph.
