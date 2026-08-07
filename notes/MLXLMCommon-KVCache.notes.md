# Relocated commentary — `KVCache.swift`

Measurement narrative and design history moved verbatim out of `Vendor/mlx-swift-lm/Libraries/MLXLMCommon/KVCache.swift`
to free bytes on the capped editable submission surface. Line numbers refer to
the file as it stood at base `e1d070f2`. Nothing here is compiled or
submitted, and the code is unchanged (see
`research/frieren_comment_strip_check.sh`).

## `protocol KVCache`

_relocated from lines 7-34 at base e1d070f2_

Implementation of KV cache functionality for MLX Swift


## Quantized Cache Usage

**Standard caches:**
```swift
let cache = KVCacheSimple()
let (keys, values) = cache.update(keys: keys, values: values)
let output = MLXFast.scaledDotProductAttention(queries: q, keys: keys, values: values, ...)
```

**Quantized cache:**
```swift
let quantizedCache = QuantizedKVCache(groupSize: 64, bits: 4)
let (qKeys, qValues) = quantizedCache.updateQuantized(keys: keys, values: values)

let output = quantizedScaledDotProductAttention(
    queries: queries,
    quantizedKeys: qKeys,
    quantizedValues: qValues,
    scale: scale,
    mask: mask,
    groupSize: quantizedCache.groupSize,
    bits: quantizedCache.bits
)
```


## `KVCache.makeMask`

_relocated from lines 62-70 at base e1d070f2_


This method encapsulates cache-specific mask creation logic. Implementations should handle offset capping, window size logic,
and optimization decisions (symbolic vs array masks).

- Parameters:
  - n: The sequence length for the new tokens
  - windowSize: Optional sliding window size
  - returnArray: Force return of array mask instead of symbolic
- Returns: Attention mask mode for scaled dot product attention

## `protocol QuantizedKVCacheProtocol`

_relocated from lines 80-93 at base e1d070f2_


**Usage Example:**
```swift
// Efficient quantized path
if let quantizedCache = cache as? QuantizedKVCacheProtocol {
    let (qKeys, qValues) = quantizedCache.updateQuantized(keys: k, values: v)
    // Use native quantized operations
    let scores = quantizedMM(queries, w: qKeys.0, scales: qKeys.1, biases: qKeys.2, ...)
} else {
    // Regular path
    let (k, v) = cache.update(keys: k, values: v)
    let output = MLXFast.scaledDotProductAttention(queries: q, keys: k, values: v, ...)
}
```

## `QuantizedKVCacheProtocol.updateQuantized`

_relocated from lines 105-109 at base e1d070f2_


- Parameters:
  - keys: New key data to add to cache
  - values: New value data to add to cache
- Returns: Quantized tuples (keys, values) as ((weight, scales, biases), (weight, scales, biases))

## `QuantizedKVCacheProtocol.getQuantizedState`

_relocated from lines 115-117 at base e1d070f2_


Useful for accessing cached data without adding new tokens.
- Returns: Current quantized state, or nil if cache is empty

## `BaseKVCache.makeMask`

_relocated from lines 163-163 at base e1d070f2_

For single token, no mask needed

## `BaseKVCache.makeMask`

_relocated from lines 168-168 at base e1d070f2_

For multi-token sequences

## `createAttentionMask`

_relocated from lines 288-294 at base e1d070f2_


- Parameters:
  - h: The input array (used to determine sequence length)
  - cache: Optional single KV cache
  - windowSize: Optional sliding window size (if provided, creates windowed attention)
  - returnArray: Force return of array mask instead of symbolic "causal"
- Returns: Attention mask mode for scaled dot product attention

## `createAttentionMask`

_relocated from lines 303-303 at base e1d070f2_

Delegate to cache's makeMask if available

## `createAttentionMask`

_relocated from lines 308-308 at base e1d070f2_

Fallback for no cache

## `KVCacheSimple.update`

_relocated from lines 344-350 at base e1d070f2_

When the first update already lands exactly on an allocation-step
boundary, the stock zero allocation has no spare capacity: it
creates arrays with the same sequence length as `keys`/`values`,
then copies the entire inputs into them. Retain the incoming arrays
directly in this no-slack case. Shapes, offsets, returned values,
and the next growth boundary are identical; only the redundant
zero-fill and full-prompt slice updates disappear.

## `KVCacheSimple fused decode append`

_relocated from lines 403-409 at base e1d070f2_


Mirrors the single-token `update` bookkeeping for the fused decode
attention kernel, which performs the slot write itself and attends
over the first `offset + 1` rows with the new row substituted from
registers. Engages only when the backing already has spare capacity
for one more row (i.e. after the first decode step's stock growth
concat), so the growth/reset branches above are provably not taken.

## `KVCacheSimple.fusedAppendContiguized`

_relocated from lines 414-416 at base e1d070f2_

slot writes lost). After the first decode step's growth concat the
backings are concat outputs and already contiguous; `contiguous()`
is then an identity-value op.

## `KVCacheSimple.toQuantized`

_relocated from lines 475-476 at base e1d070f2_


Use `updateQuantized()` and `quantizedScaledDotProductAttention()` for zero-overhead operation.

## `KVCacheSimple.toQuantized`

_relocated from lines 479-479 at base e1d070f2_

Quantize the current keys and values

## `KVCacheSimple.toQuantized`

_relocated from lines 482-484 at base e1d070f2_

Pick a group size whose divisibility matches the head dim instead
of trusting the requested one (avoids a hard crash on models whose
head dim isn't divisible by 64). Upstream 01b8624.

## `KVCacheSimple.toQuantized`

_relocated from lines 502-502 at base e1d070f2_

Set the quantized state

## `RotatingKVCache.updateConcat`

_relocated from lines 592-592 at base e1d070f2_

Put the keys/values in temporal order to preserve context

## `RotatingKVCache.updateInPlace`

_relocated from lines 617-617 at base e1d070f2_

May not have hit the max size yet, so potentially keep growing the cache

## `RotatingKVCache.updateInPlace`

_relocated from lines 643-643 at base e1d070f2_

Trim if needed

## `RotatingKVCache.updateInPlace`

_relocated from lines 651-651 at base e1d070f2_

Rotate if we've hit the end

## `RotatingKVCache.updateInPlace`

_relocated from lines 656-656 at base e1d070f2_

Assign

## `RotatingKVCache.updateInPlace`

_relocated from lines 662-662 at base e1d070f2_

Return the appropriate cache slice

## `RotatingKVCache fused decode ring`

_relocated from lines 684-694 at base e1d070f2_


The fused decode attention kernel performs this cache's single-token
update itself: it writes the new normed+roped K row and raw V row
directly into the ring backing at the slot `updateInPlace` would have
slice-assigned, and attends over the full ring in slot order with the
new row substituted from registers — the same buffers, values, and
slot visit order the stock update + SDPA pair produces. These
accessors expose exactly the state that path needs and mirror
updateInPlace's `tokenCount == 1` bookkeeping. They engage only in
the steady wrapped regime (buffer at capacity, `keep == 0`), where
updateInPlace's growth and trim branches are provably no-ops.

## `RotatingKVCache.makeMask`

_relocated from lines 803-803 at base e1d070f2_

Multi-token case

## `RotatingKVCache.makeMask`

_relocated from lines 807-807 at base e1d070f2_

Decide if we need an array mask

## `RotatingKVCache.makeMask`

_relocated from lines 814-814 at base e1d070f2_

Single token case (n == 1)

## `RotatingKVCache.makeMask`

_relocated from lines 829-829 at base e1d070f2_

Roll the mask to account for rotation

## `RotatingKVCache.toQuantized`

_relocated from lines 853-853 at base e1d070f2_

Note: This is complex due to the rotating nature and temporal ordering

## `RotatingKVCache.toQuantized`

_relocated from lines 855-856 at base e1d070f2_

For now, throw an error like the Python version does
A full implementation would need to handle the temporal ordering correctly

## `RotatingKVCache.toQuantized`

_relocated from lines 861-865 at base e1d070f2_

Future implementation would need to:
1. Put keys/values in temporal order using temporalOrder()
2. Quantize the temporally ordered arrays
3. Store metadata about rotation state
4. Implement corresponding dequantization with rotation restoration

## `QuantizedKVCache.initQuant`

_relocated from lines 943-943 at base e1d070f2_

Create temporary zero arrays and quantize them using native MLX Swift

## `QuantizedKVCache.getQuantizedState`

_relocated from lines 962-962 at base e1d070f2_

- Returns: Tuple of ((keyWeight, keyScales, keyBiases), (valueWeight, valueScales, valueBiases))

## `QuantizedKVCache.updateQuantized`

_relocated from lines 976-980 at base e1d070f2_


- Parameters:
  - keys: New key data to add to cache
  - values: New value data to add to cache
- Returns: Quantized tuples (keys, values) as ((weight, scales, biases), (weight, scales, biases))

## `QuantizedKVCache.updateQuantized`

_relocated from lines 990-993 at base e1d070f2_

Resolve a compatible group size up front; adopt it only while the
cache is still empty so a fresh QuantizedKVCache built with a
mismatched default group size self-corrects instead of crashing.
Upstream 01b8624.

## `QuantizedKVCache.updateQuantized`

_relocated from lines 1013-1013 at base e1d070f2_

Check if we need to expand the cache

## `QuantizedKVCache.updateQuantized`

_relocated from lines 1019-1019 at base e1d070f2_

Trim if needed

## `QuantizedKVCache.updateQuantized`

_relocated from lines 1021-1021 at base e1d070f2_

Use tree_map equivalent to trim both keys and values

## `QuantizedKVCache.updateQuantized`

_relocated from lines 1031-1031 at base e1d070f2_

Expand using tree_map equivalent (Python's tree_map(expand_quant, ...))

## `QuantizedKVCache.updateQuantized`

_relocated from lines 1035-1035 at base e1d070f2_

Initialize new quantized cache

## `QuantizedKVCache.updateQuantized`

_relocated from lines 1046-1046 at base e1d070f2_

Convert named tuples to positional tuples

## `QuantizedKVCache.updateQuantized`

_relocated from lines 1050-1050 at base e1d070f2_

Assign to storage

## `QuantizedKVCache.updateQuantized`

_relocated from lines 1055-1055 at base e1d070f2_

Update each component of the quantized tuples

## `QuantizedKVCache.updateQuantized`

_relocated from lines 1071-1071 at base e1d070f2_

Return quantized tuples

## `QuantizedKVCache.state`

_relocated from lines 1092-1092 at base e1d070f2_

Trim to current offset using tree_map

## `QuantizedKVCache.state`

_relocated from lines 1095-1095 at base e1d070f2_

Flatten tuples to array for serialization

## `QuantizedKVCache.state`

_relocated from lines 1101-1101 at base e1d070f2_

Flatten tuples to array for serialization

## `QuantizedKVCache.toUnquantized`

_relocated from lines 1170-1170 at base e1d070f2_

Dequantize the current state using tree_map approach

## `QuantizedKVCache.toUnquantized`

_relocated from lines 1181-1181 at base e1d070f2_

Set the unquantized state

## `ArraysCache.rollbackState`

_relocated from lines 1293-1293 at base e1d070f2_

Port of omlx commit 696d90a: patches/mlx_lm_mtp/cache_rollback.py ArraysCache.rollback_state

## `CacheList.metaState`

_relocated from lines 1566-1568 at base e1d070f2_


Like Python's CacheList.meta_state which returns [child_class_names, child_meta_states],
but flattened for Swift's [String] format.

## `savePromptCache`

_relocated from lines 1649-1653 at base e1d070f2_


- Parameters:
  - url: The URL to the `.safetensors` file
  - cache: The model cache state
  - metadata: Optional metadata to save along with cache state

## `loadPromptCache`

_relocated from lines 1695-1698 at base e1d070f2_


- Parameters:
  - url: The URL to the `.safetensors` file
- Returns: The prompt cache and the metadata

## `loadPromptCache`

_relocated from lines 1704-1704 at base e1d070f2_

Unflatten arrays using tree_unflatten compatible logic

## `loadPromptCache`

_relocated from lines 1707-1707 at base e1d070f2_

Unflatten metadata using tree_unflatten compatible logic

## `loadPromptCache`

_relocated from lines 1724-1724 at base e1d070f2_

Reconstruct cache instances

## `restoreCacheFromMetaState`

_relocated from lines 1739-1741 at base e1d070f2_


Like Python's `globals()[className].from_state(state, meta_state)`, each cache type
encodes enough info in `metaState` to reconstruct itself.

## `unflattenArrays`

_relocated from lines 1807-1807 at base e1d070f2_

Parse all keys and organize by indices

## `unflattenArrays`

_relocated from lines 1821-1821 at base e1d070f2_

Convert to ordered array structure

## `unflattenMetadata`

_relocated from lines 1855-1855 at base e1d070f2_

Ensure cacheInfo is large enough

## `unflattenMetadata`

_relocated from lines 1859-1859 at base e1d070f2_

Ensure inner array is large enough

## `unflattenMetadata`

_relocated from lines 1872-1872 at base e1d070f2_

Ensure cacheClasses is large enough

## `makePromptCache`

_relocated from lines 1892-1893 at base e1d070f2_

The model already conforms to LanguageModel which has newCache
If it also conforms to KVCacheDimensionProvider, the extension will provide the implementation

## `makePromptCacheWithLayerCount`

_relocated from lines 1907-1909 at base e1d070f2_


This function creates a default cache structure when the number of layers is known.
Use this when `makePromptCache` cannot determine the layer count automatically.

## `compiledQuantizedAttentionSoftmax`

_relocated from lines 1946-1972 at base e1d070f2_

Compiled, shape-agnostic softmax cores for `quantizedScaledDotProductAttention`.

The softmax over the score tensor is the largest cluster of small elementwise
kernels in the quantized-attention path (max, sub, exp, where, sum, div) —
each a separate GPU dispatch. Wrapping it in `compile(shapeless:)` fuses those
launches into a single graph and cuts the per-step launch overhead that
dominates decode latency.

`shapeless: true` is what makes this safe on the decode path. During
single-query decode the query length is 1 but the cached-KV (`kL`) axis grows
by one every token, so the score tensor's *shape* changes every step. A
shapeless graph is NOT recompiled when only shapes change — only a change in
rank (ndim) or dtype forces a recompile. The score tensor is always rank-4
(`[B, nQHeads, L, kL]`, collapsed below before softmax) and keeps a stable
dtype during a run, so the graph compiles once and is reused for every step;
there is no per-shape recompilation churn.

The cores use only `axis: -1` reductions and broadcasts, so they are
independent of batch size, head count, query length and `kL`, and they carry
no quantization parameters (groupSize/bits/mode live in the surrounding
`quantizedMM` calls, which stay outside the compiled core). The matmuls
themselves are intentionally left out: each is a single large kernel whose
launch overhead is marginal, and folding the GQA reshape (which depends on the
batch axis) into a shapeless graph would bake in a stale batch constant.

Numerics are identical to the previous inline version — the same ops in the
same order, just fused into one graph.

## `quantizedScaledDotProductAttention`

_relocated from lines 2016-2016 at base e1d070f2_

Scale queries

## `quantizedScaledDotProductAttention`

_relocated from lines 2019-2019 at base e1d070f2_

Handle GQA (Grouped Query Attention)

## `quantizedScaledDotProductAttention GQA mask broadcast`

_relocated from lines 2047-2049 at base e1d070f2_

standard attention masks are [B, 1, L, kL] / [B, nQHeads, L, kL] / [L, kL]
and cannot broadcast against the 5D GQA score tensor when B > 1 (the 5D
path only "worked" at B == 1 because the leading 1s happened to broadcast).

## `quantizedScaledDotProductAttention`

_relocated from lines 2052-2052 at base e1d070f2_

Apply mask

## `quantizedScaledDotProductAttention absent sink limit`

_relocated from lines 2086-2097 at base e1d070f2_

Attention sink: a learned per-(query)head logit that acts as one extra
"virtual" key in the softmax — it has no value vector, so it only
absorbs softmax mass, making the real-token weights sum to < 1.
(Equivalent to concatenating `sinks` as an extra score column and
dropping it after softmax, but done without concat/slice so the
weights stay contiguous for `quantizedMM`.) A no-sink cache is the
`sink -> -inf` limit, i.e. `sinks == nil` below, NOT a zero sink.

In the canonical 4D layout `sinks` ([nQHeads]) maps directly onto the
head axis. The reshape stays outside the compiled core so the core
never bakes in a head-count constant. The fused, numerically-stable
softmax then folds the sink into the denominator.

## `quantizedScaledDotProductAttention`

_relocated from lines 2101-2105 at base e1d070f2_

Fused, stable no-sink softmax. Unlike the generic softmax, this keeps
fully masked query rows finite by assigning zero probability to every
real key (there is no sink to absorb probability mass). Model code
ignores padded query rows, but keeping them finite avoids NaN
propagation.

## `quantizedScaledDotProductAttention`

_relocated from lines 2116-2116 at base e1d070f2_

Compute output using quantized matmul

## `quantizedScaledDotProductAttention`

_relocated from lines 2123-2123 at base e1d070f2_

Reshape output for GQA

## `maybeQuantizeKVCache`

_relocated from lines 2134-2144 at base e1d070f2_


Converts regular caches to quantized caches when:
- kvBits is specified
- The cache is not already quantized
- The cache offset is greater than quantizedKVStart

- Parameters:
  - cache: Array of KV caches to potentially quantize
  - kvBits: Number of bits for quantization (nil = no quantization)
  - kvGroupSize: Group size for quantization
  - quantizedKVStart: Token count threshold to begin quantizing

## `maybeQuantizeKVCache MambaCache gate`

_relocated from lines 2154-2156 at base e1d070f2_

On hybrid attention+SSM models (Qwen3.5, Qwen3-Next, Nemotron, Falcon-H1)
cache[0] is often a MambaCache, so gating on cache[0] silently no-ops KV
quantization. Scan for the first KVCacheSimple instead. Upstream 88beb40.

## `maybeQuantizeKVCache`

_relocated from lines 2165-2165 at base e1d070f2_

Handle cache types that support quantization

## `maybeQuantizeKVCache`

_relocated from lines 2185-2187 at base e1d070f2_

TODO: RotatingKVCache.toQuantized() is not implemented yet, like in Python.
When implemented, add: else if let rotatingCache = cache[i] as? RotatingKVCache { ... }
MambaCache and CacheList don't use traditional KV quantization
