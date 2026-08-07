# Relocated commentary — `BatchKVCache.swift`

Measurement narrative and design history moved verbatim out of `Vendor/mlx-swift-lm/Libraries/MLXLMCommon/BatchKVCache.swift`
to free bytes on the capped editable submission surface. Line numbers refer to
the file as it stood at base `63ab67c8`. Nothing here is compiled or
submitted, and the code is unchanged (see
`research/frieren_comment_strip_check.sh`).

## `line2`

_relocated from lines 2-2 at base 63ab67c8_

https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/models/cache.py

## `BatchKVCache`

_relocated from lines 32-38 at base 63ab67c8_


Storage is right-justified along axis=2: for each row `b`, real keys
live at `[..., leftPadding[b]..._idx, :]` and the leading `leftPadding[b]`
slots are zero. Per-row position offsets are exposed via `batchOffset`
for RoPE dispatch through `BatchPositionedKVCache`.

Not thread-safe; the `BatchGenerator` mutates this from a single task.

## `line119`

_relocated from lines 106-119 at base 63ab67c8_


The cache expects inputs to be left-padded. For these prompts:
```
[1, 3, 5]
[7]
[2, 6, 8, 9]
```
the effective batched input is right-aligned to:
```
[0, 1, 3, 5]
[0, 0, 0, 7]
[2, 6, 8, 9]
```
and `leftPadding = [1, 3, 0]`.

## `line187`

_relocated from lines 184-187 at base 63ab67c8_

gemma-4 shares one RoPE `perRowOffset` from the first cache
(Gemma4.swift:1264), so other caches never consume their own
`batchOffset` and leak a tiny scalar buffer/step (COUNT leak, flat
bytes). `asyncEval` detaches it, no GPU sync. Prefill untouched.

## `extend`

_relocated from lines 265-266 at base 63ab67c8_

Both caches are padded to be right-justified and same time-axis size,
then concatenated along the batch axis.

## `makeMask`

_relocated from lines 409-416 at base 63ab67c8_


For single-token decode steps with no left padding we return `.none` so
the fast attention kernel can take its unmasked path. MLX issue #3384:
on 4-bit quantized Gemma 4, passing an explicit boolean mask (even an
all-`true` one) routes `scaled_dot_product_attention` through a divergent
evaluation branch whose numerical drift flips top-1 logprobs and traps
continuous-batched generation in repetition loops. The unmasked path is
safe here because every stored key position is a real token.

## `BatchRotatingKVCache`

_relocated from lines 494-497 at base 63ab67c8_


This cache preserves the per-row position and left-padding semantics of
`BatchKVCache`, while trimming stored keys/values to `maxSize` for sliding
attention layers.

## `_base`

_relocated from lines 513-515 at base 63ab67c8_

(legacy / freshly normalized layout) `_base == 0` and the buffers are
exactly `_idx` long along axis 2 — byte-for-byte the legacy layout, so
every existing reader is unchanged on that path.

## `useFastDecodePath`

_relocated from lines 532-532 at base 63ab67c8_

without touching global state.

## `windowKeys`

_relocated from lines 536-537 at base 63ab67c8_

Collapses to the stored buffer itself in the normalized layout so the
legacy path returns exactly what it did before.

## `normalizeToWindow`

_relocated from lines 552-552 at base 63ab67c8_

keep reading `keys`/`values` directly.

## `line637`

_relocated from lines 629-637 at base 63ab67c8_

(so at most one slot slides off the front). The legacy path on every
such step allocates and fully copies the window TWICE — once for the
`concatenated` append and again for the front `trim`. Here we instead
write the one new token in place into an over-allocated buffer and
advance a host-side base pointer, compacting only every
`allocationStep` steps. The returned window contents, `_idx`,
`batchOffset`, and `leftPadding` are identical to the legacy path
(see the `Parity` tests), so `makeMask` (which depends only on `_idx`
and `leftPadding`) and RoPE (which reads `batchOffset`) are unchanged.

## `trimSize`

_relocated from lines 666-666 at base 63ab67c8_

newly returned prefill block.

## `line697`

_relocated from lines 694-697 at base 63ab67c8_

others leak ~2 tiny scalar buffers/step until `numResources` hits the
iogpu ceiling and aborts (COUNT leak, flat bytes). keys/values don't
leak (attention consumes them each step). `asyncEval` detaches the
chains, no GPU sync. Prefill untouched.

## `fastDecodeUpdate`

_relocated from lines 708-714 at base 63ab67c8_

frontier, advances `_idx`, and — once the window is full — slides `_base`
forward by one (dropping the oldest token without copying). When the
frontier reaches the end of the physical buffer we compact: a fresh
over-allocated buffer with the current window re-based to the front. The
in-place slice write donates the buffer (refcount 1 between steps, like
`RotatingKVCache.updateInPlace`), so steady-state decode performs no
full-window copy.

## `line724`

_relocated from lines 724-724 at base 63ab67c8_

periodic compaction once `_base` has walked to the buffer end.

## `fromSingleRow`

_relocated from lines 918-930 at base 63ab67c8_

both `state` ([keys, values]) and `metaState` ([keep, maxSize, step,
offset, idx]) — exactly what `extract` emits and `KVCacheSerializer`
round-trips. `keep != 0` is unsupported (the batched cache has no
keep region) and a recurrent/ unsupported window returns an empty B=1
cache (caller should not have routed it here).

Left padding is 0 (single row), so the stored arrays are already in
the batched layout `[1, H, S, D]`. `batchOffset` is the source's
absolute offset and `_idx` its physical length — both read from the
source so a subsequent decode step continues from the right position
and the sliding mask aligns. This is the restore-side mirror of
`extract`; the pair is covered by an extract→fromSingleRow→resume
equivalence test.

## `line976`

_relocated from lines 957-976 at base 63ab67c8_

fits inside the requested window. When `windowSize < maxCacheSize` the
buffer can hold keys older than the active window; returning `.none`
there would let the query attend past it, so keep the windowed mask.
For Gemma (and any caller where window == cache size) `_idx` is capped
at `maxCacheSize == actualWindowSize`, so this is always taken.
`<= 0`, not `== 0`: a rotating cache that has generated past its window
trims slots and subtracts from `leftPadding`, so unpadded rows go
NEGATIVE once past `maxCacheSize`. Accepting only `== 0` would send
every long (> window) Gemma 4 decode back through the explicit-mask path
(the mlx#3384 slow/divergent path) on every sliding layer.

Boundary: makeMask runs BEFORE `update`, which appends `n` keys and then
trims to `maxCacheSize` (NOT to the window). So the post-update retained
length is `min(_idx + n, maxCacheSize)`; `.none` is correct only if THAT
fits the window. For Gemma (window == maxCacheSize) this is always true,
so the fast path is unchanged; it only tightens `windowSize <
maxCacheSize`, where the old `_idx <= actualWindowSize` let the query
attend one token past the window. (Plain `_idx + n <= actualWindowSize`
would wrongly drop Gemma's fast path at the full-cache boundary, where
the trim keeps everything in-window.)

## `zeroTailPerRow`

_relocated from lines 1104-1106 at base 63ab67c8_


This is used by batched speculative decoding when rows accept different
numbers of tokens within the same verify block.
