import MLX
import MLXLMCommon
@testable import MLXFastModel
import Testing

private final class DerivedKVCacheSimple: KVCacheSimple {}

private func ordinaryCacheTensor(length: Int, phase: Float = 0) -> MLXArray {
    let values = (0 ..< (2 * length * 4)).map { Float($0) * 0.01 + phase }
    return MLXArray(values).reshaped(1, 2, length, 4)
}

private func expectOrdinaryCacheArraysClose(_ actual: MLXArray, _ expected: MLXArray) {
    #expect(actual.shape == expected.shape)
    #expect(allClose(actual, expected).item(Bool.self))
}

private func expectOrdinaryCacheStateClose(_ actual: KVCache, _ expected: KVCache) {
    #expect(actual.offset == expected.offset)
    #expect(actual.state.count == expected.state.count)
    for (lhs, rhs) in zip(actual.state, expected.state) {
        expectOrdinaryCacheArraysClose(lhs, rhs)
    }
}

@Test
func lagunaOrdinaryCachePrefillRequiresExactMultiTokenCache() {
    #expect(lagunaUsesOrdinaryCachePrefill(sequenceLength: 2, cache: KVCacheSimple()))
    #expect(
        lagunaUsesOrdinaryCachePrefill(
            sequenceLength: 2,
            cache: RotatingKVCache(maxSize: 4)
        )
    )
    #expect(!lagunaUsesOrdinaryCachePrefill(sequenceLength: 1, cache: KVCacheSimple()))
    #expect(!lagunaUsesOrdinaryCachePrefill(sequenceLength: 2, cache: nil))
    #expect(!lagunaUsesOrdinaryCachePrefill(sequenceLength: 2, cache: DerivedKVCacheSimple()))
    #expect(!lagunaUsesOrdinaryCachePrefill(sequenceLength: 2, cache: QuantizedKVCache()))
}

@Test
func lagunaOrdinarySimpleCachePrefillMatchesGenericPathAcrossUpdates() {
    let directCache = KVCacheSimple()
    let referenceCache = KVCacheSimple()

    let firstDirect = lagunaAttentionWithOrdinaryCachePrefill(
        queries: ordinaryCacheTensor(length: 3, phase: 0.2),
        keys: ordinaryCacheTensor(length: 3, phase: 0.4),
        values: ordinaryCacheTensor(length: 3, phase: 0.6),
        cache: directCache,
        scale: 0.5,
        mask: .causal
    )
    let firstReference = attentionWithCacheUpdate(
        queries: ordinaryCacheTensor(length: 3, phase: 0.2),
        keys: ordinaryCacheTensor(length: 3, phase: 0.4),
        values: ordinaryCacheTensor(length: 3, phase: 0.6),
        cache: referenceCache,
        scale: 0.5,
        mask: .causal
    )
    expectOrdinaryCacheArraysClose(firstDirect, firstReference)
    expectOrdinaryCacheStateClose(directCache, referenceCache)

    let secondDirect = lagunaAttentionWithOrdinaryCachePrefill(
        queries: ordinaryCacheTensor(length: 2, phase: 1.2),
        keys: ordinaryCacheTensor(length: 2, phase: 1.4),
        values: ordinaryCacheTensor(length: 2, phase: 1.6),
        cache: directCache,
        scale: 0.5,
        mask: .causal
    )
    let secondReference = attentionWithCacheUpdate(
        queries: ordinaryCacheTensor(length: 2, phase: 1.2),
        keys: ordinaryCacheTensor(length: 2, phase: 1.4),
        values: ordinaryCacheTensor(length: 2, phase: 1.6),
        cache: referenceCache,
        scale: 0.5,
        mask: .causal
    )
    expectOrdinaryCacheArraysClose(secondDirect, secondReference)
    expectOrdinaryCacheStateClose(directCache, referenceCache)
}

@Test
func lagunaOrdinaryRotatingCachePrefillMatchesGenericPathAfterTruncation() {
    let directCache = RotatingKVCache(maxSize: 4, step: 4)
    let referenceCache = RotatingKVCache(maxSize: 4, step: 4)
    let initialKeys = ordinaryCacheTensor(length: 3, phase: 0.3)
    let initialValues = ordinaryCacheTensor(length: 3, phase: 0.5)
    _ = directCache.update(keys: initialKeys, values: initialValues)
    _ = referenceCache.update(keys: initialKeys, values: initialValues)

    let direct = lagunaAttentionWithOrdinaryCachePrefill(
        queries: ordinaryCacheTensor(length: 3, phase: 0.7),
        keys: ordinaryCacheTensor(length: 3, phase: 0.9),
        values: ordinaryCacheTensor(length: 3, phase: 1.1),
        cache: directCache,
        scale: 0.5,
        mask: .causal
    )
    let reference = attentionWithCacheUpdate(
        queries: ordinaryCacheTensor(length: 3, phase: 0.7),
        keys: ordinaryCacheTensor(length: 3, phase: 0.9),
        values: ordinaryCacheTensor(length: 3, phase: 1.1),
        cache: referenceCache,
        scale: 0.5,
        mask: .causal
    )

    expectOrdinaryCacheArraysClose(direct, reference)
    expectOrdinaryCacheStateClose(directCache, referenceCache)
}

@Test
func lagunaOrdinaryCachePrefillUsesKeyLengthForTerminalQuery() {
    let directCache = KVCacheSimple()
    let referenceCache = KVCacheSimple()
    let queries = ordinaryCacheTensor(length: 1, phase: 0.2)
    let keys = ordinaryCacheTensor(length: 4, phase: 0.4)
    let values = ordinaryCacheTensor(length: 4, phase: 0.6)

    let direct = lagunaAttentionWithOrdinaryCachePrefill(
        queries: queries,
        keys: keys,
        values: values,
        cache: directCache,
        scale: 0.5,
        mask: .causal
    )
    let reference = attentionWithCacheUpdate(
        queries: queries,
        keys: keys,
        values: values,
        cache: referenceCache,
        scale: 0.5,
        mask: .causal
    )

    expectOrdinaryCacheArraysClose(direct, reference)
    expectOrdinaryCacheStateClose(directCache, referenceCache)
    #expect(directCache.offset == 4)
}
