# Relocated commentary — `CompilableRotatingKVCache.swift`

Measurement narrative and design history moved verbatim out of `Vendor/mlx-swift-lm/Libraries/MLXLMCommon/CompilableRotatingKVCache.swift`
to free bytes on the capped editable submission surface. Line numbers refer to
the file as it stood at base `63ab67c8`. Nothing here is compiled or
submitted, and the code is unchanged (see
`research/frieren_comment_strip_check.sh`).

## `CompilableRotatingKVCache`

_relocated from lines 5-22 at base 63ab67c8_


Standard RotatingKVCache breaks compile() in two ways:
  1. Buffer growth via concat rebinds the keys property — the trace
     captures the original object and rebinding loses it.
  2. Ring-buffer wrap via Swift Int reset doesn't match the trace's
     assumed linear layout.

This subclass fixes both by:
  - Pre-allocating the unified buffer to maxCacheSize at promotion time.
    No concat-growth during decode.
  - Tracking the write index as idxArray (MLXArray [1] int32). Wrap
    arithmetic uses MLXArray ops (where_ + modulo) so the compile tracer
    can follow.
  - Returning the FULL [B, H, maxCacheSize, D] buffer from update().
    The attention mask restricts valid positions.

Initialise via init(from:) on an existing RotatingKVCache populated by
prefill, or via the static promote(from:maxLength:) helper.

## `CompilableRotatingKVCache`

_relocated from lines 29-43 at base 63ab67c8_


Compared to the parent:

- `keys` and `values` are eagerly allocated at `[B, H, maxCacheSize, D]`
  at promotion time. No growth-via-concat during decode.
- `idxArray: MLXArray[1] int32` replaces Swift-Int `idx`. All wrap
  arithmetic happens in MLXArray ops so the compile tracer can follow.
- `offsetArray: MLXArray[1] int32` mirrors `offset`. Used by `makeMask`
  for the causal upper bound; tracked as an MLXArray so the tracer
  follows per-step advances.
- `update(keys:values:)` writes new tokens at `idxArray` via
  `dynamicSliceUpdate`, then advances `idxArray` with wrap semantics
  entirely in MLXArray space.
- `makeMask` always returns `.array(mask)` — the full-buffer return
  means attention must be told which positions are valid.

## `idxArray`

_relocated from lines 47-48 at base 63ab67c8_

In the linear segment (before wrap), this equals `offsetArray`.
After wrap, this rotates through `[keep, maxCacheSize)`.

## `offsetArray`

_relocated from lines 54-54 at base 63ab67c8_

`maxCacheSize` positions in the buffer are valid (ring full).

## `canElideFullWindowDecodeMask`

_relocated from lines 64-64 at base 63ab67c8_

window equals the ring size, a mask is therefore exactly redundant.

## `line82`

_relocated from lines 79-82 at base 63ab67c8_

is smaller (the parent grows lazily in `step`-sized chunks).

- Parameter rotating: Source cache. Typically the result of a
  prefill that has populated keys/values.

## `srcK`

_relocated from lines 97-98 at base 63ab67c8_

This prevents the compile-breaking concat-growth path from ever
firing during decode.

## `update`

_relocated from lines 139-141 at base 63ab67c8_


Returns the FULL `[B, H, maxCacheSize, D]` buffer. `makeMask`
restricts attention to valid positions.

## `line188`

_relocated from lines 187-188 at base 63ab67c8_

view should read the MLXArray counters and materialize
OUTSIDE the compiled trace.

## `makeMask`

_relocated from lines 197-204 at base 63ab67c8_


Mask semantics:
 - **Linear phase** (offsetArray < maxCacheSize): valid positions
   are `[0, offsetArray)`. Causal mask is `linds >= rinds`.
 - **Post-wrap phase** (offsetArray >= maxCacheSize): all
   `maxCacheSize` positions are valid (the ring is full). The
   ring layout means positions are NOT in logical order — but for
   single-query decode with `n=1`, every position is attendable.

## `tokenInds`

_relocated from lines 236-238 at base 63ab67c8_

tokenInds maps each physical position to its distance from the
write cursor: idxArray → 0 (oldest/next-write), idxArray-1 →
maxCacheSize-1 (most recent). Keep the RECENT end of the ring.
