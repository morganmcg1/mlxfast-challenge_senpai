# Relocated commentary — `CompiledDecode.swift`

Measurement narrative and design history moved verbatim out of `Vendor/mlx-swift-lm/Libraries/MLXLMCommon/CompiledDecode.swift`
to free bytes on the capped editable submission surface. Line numbers refer to
the file as it stood at base `63ab67c8`. Nothing here is compiled or
submitted, and the code is unchanged (see
`research/frieren_comment_strip_check.sh`).

## `line26`

_relocated from lines 2-26 at base 63ab67c8_


Ported (trimmed) from osaurus-ai/vmlx-swift-lm
(Libraries/MLXLMCommon/BatchEngine/BatchCompile.swift `compileForward`).

This wraps MLX `compile(inputs:outputs:)` so a single decode step — the model
forward plus the per-layer KV-cache write — is captured as one compiled graph,
collapsing hundreds of FFI crossings into a single compiled call. The tracer
captures each cache layer's `innerState()`; subsequent invocations mutate the
captured cache objects in place via `_updateInternal`.

REQUIREMENTS / CONSTRAINTS:
- Every layer must be a ``CompilableKVCache`` or ``CompilableRotatingKVCache``
  (fixed-shape, MLXArray offset). Standard `KVCacheSimple` / `RotatingKVCache`
  change state shape per step and cannot be compile-traced.
- Mixed caches (e.g. Gemma4: KVCacheSimple for full-attention layers,
  RotatingKVCache for sliding-window layers) are supported via per-layer
  promotion in `setupCompiledDecode`.
- The trace specialises on the token-batch shape it first sees (typically
  `[B, 1]`). A changing batch size forces a recompile, so the batched decode
  path needs fixed-size buckets (see the port plan for `GenerationBatch`).

This helper is dependency-free w.r.t. the continuous-batching engine: it can
be exercised in isolation (see CompilableKVCacheTests) and reused by either a
single-stream or a batched decode loop once the cache-promotion + bucketing
plumbing lands.

## `TieredForward`

_relocated from lines 39-43 at base 63ab67c8_


The fast graph attends to a short fixed prefix while the slow graph
exposes the whole backing buffer. Both cache arrays contain wrappers
around the same `MLXArray` objects, so switching graphs requires no KV
copy and no GPU offset readback.

## `eligible`

_relocated from lines 96-97 at base 63ab67c8_

Accepts both single-stream (CompilableKVCache, CompilableRotatingKVCache)
and batched (CompilableBatchKVCache, CompilableBatchRotatingKVCache) types.

## `compileForward`

_relocated from lines 106-124 at base 63ab67c8_


The returned closure accepts `[tokens]` (a single `[B, L]` int token
array wrapped in a one-element array) and returns `[logits]` (a single
`[B, L, V]` array). The captured cache layers are mutated in place.

Supports mixed cache types: single-stream (``CompilableKVCache``,
``CompilableRotatingKVCache``) and batched (``CompilableBatchKVCache``,
``CompilableBatchRotatingKVCache``) all expose `innerState()` returning
MLXArrays tracked by `compile(inputs:outputs:)`.

- Precondition: `cacheRef` is non-empty and every element is a
  compilable cache (see ``eligible(_:)``). Call `eval(cacheRef)`
  before this so no pending tracer ops corrupt state identity.

- Parameters:
  - model: The language model to trace through.
  - cacheRef: Per-layer compilable cache instances. Captured by the
    returned closure; must not be empty.
- Returns: A `@Sendable` closure mapping `[tokens]` -> `[logits]`.

## `setup`

_relocated from lines 161-167 at base 63ab67c8_

- Parameters:
  - model: The language model.
  - cache: Mutable cache array. On success, entries are replaced with
    their compilable equivalents in place.
  - maxCacheLength: Maximum sequence length for the compiled cache buffers
    (applies to CompilableKVCache; RotatingKVCache uses its own maxCacheSize).
- Returns: A compiled forward closure, or `nil` if setup was skipped.

## `initialAttentionLength`

_relocated from lines 251-258 at base 63ab67c8_


Lengths above 1024 stay on MLX's two-pass vector SDPA on large M-series
devices. The first such length is exactly 1025: attention views share
the full backing allocation, so unlike cache storage they do not need
tranche alignment. This preserves the full buffer's block partition
for Laguna's six-way GQA on every MLX architecture category (`s`: 128
blocks, `d`: 128, other: 64) while scanning the shortest possible view.
This is a kernel boundary, not a benchmark prompt/token constant.

## `setupBatchCompiledDecode`

_relocated from lines 290-304 at base 63ab67c8_


Promotes ``BatchKVCache`` layers to ``CompilableBatchKVCache`` and
``BatchRotatingKVCache`` layers to ``CompilableBatchRotatingKVCache``
in place. Layers that are already compilable are kept as-is.

ArraysCache / MambaCache layers are unsupported — if any are present,
setup is skipped and `nil` is returned.

- Parameters:
  - model: The language model.
  - cache: Mutable batched-cache array. On success, entries are replaced
    with their compilable equivalents in place.
  - maxCacheLength: Maximum sequence length for full-attention layers.
    Sliding-window layers use their own maxCacheSize.
- Returns: A compiled forward closure, or `nil` if setup was skipped.
