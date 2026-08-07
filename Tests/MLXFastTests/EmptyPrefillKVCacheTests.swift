import MLX
import MLXLMCommon
import Testing

@Suite(.serialized)
struct EmptyPrefillKVCacheTests {
    @Test
    func simpleCacheMatchesStockPrefillAndFirstContinuation() {
        verifyEmptyPrefill(
            control: KVCacheSimple(initialSlack: true),
            candidate: KVCacheSimple(initialSlack: true)
        )
    }

    @Test
    func rotatingCacheMatchesStockPrefillAndFirstContinuation() {
        verifyEmptyPrefill(
            control: RotatingKVCache(maxSize: 512),
            candidate: RotatingKVCache(maxSize: 512)
        )
    }
}

private func verifyEmptyPrefill(
    control: any EmptyPrefillKVCache,
    candidate: any EmptyPrefillKVCache
) {
    let controlKeys = testTensor(tokens: 512, seed: 3)
    let controlValues = testTensor(tokens: 512, seed: 11)
    let candidateKeys = testTensor(tokens: 512, seed: 3)
    let candidateValues = testTensor(tokens: 512, seed: 11)
    let prefillQuery = testTensor(tokens: 1, seed: 19)

    let (cachedKeys, cachedValues) = control.update(keys: controlKeys, values: controlValues)
    let controlPrefill = MLXFast.scaledDotProductAttention(
        queries: prefillQuery,
        keys: cachedKeys,
        values: cachedValues,
        scale: 0.5,
        mask: .none
    )
    let candidatePrefill = attentionWithCacheUpdate(
        queries: prefillQuery,
        keys: candidateKeys,
        values: candidateValues,
        cache: candidate,
        scale: 0.5,
        mask: .none
    )

    expectEqual(cachedKeys, controlKeys)
    expectEqual(cachedValues, controlValues)
    expectEqual(controlPrefill, candidatePrefill)
    expectEquivalentState(control, candidate)
    #expect(control.offset == 512)
    #expect(candidate.offset == 512)

    let controlNextKeys = testTensor(tokens: 1, seed: 23)
    let controlNextValues = testTensor(tokens: 1, seed: 29)
    let candidateNextKeys = testTensor(tokens: 1, seed: 23)
    let candidateNextValues = testTensor(tokens: 1, seed: 29)
    let continuationQuery = testTensor(tokens: 1, seed: 31)

    let (continuedKeys, continuedValues) = control.update(
        keys: controlNextKeys,
        values: controlNextValues
    )
    let controlContinuation = MLXFast.scaledDotProductAttention(
        queries: continuationQuery,
        keys: continuedKeys,
        values: continuedValues,
        scale: 0.5,
        mask: .none
    )
    let candidateContinuation = attentionWithCacheUpdate(
        queries: continuationQuery,
        keys: candidateNextKeys,
        values: candidateNextValues,
        cache: candidate,
        scale: 0.5,
        mask: .none
    )

    expectEqual(controlContinuation, candidateContinuation)
    expectEquivalentState(control, candidate)
    #expect(control.offset == 513)
    #expect(candidate.offset == 513)
}

private func testTensor(tokens: Int, seed: Int) -> MLXArray {
    let values = (0 ..< (2 * tokens * 4)).map {
        Float((($0 + seed) % 37) - 18) / 16
    }
    return MLXArray(values, [1, 2, tokens, 4])
}

private func expectEquivalentState(_ lhs: any KVCache, _ rhs: any KVCache) {
    let lhsState = lhs.state
    let rhsState = rhs.state
    #expect(lhsState.count == rhsState.count)
    #expect(lhs.metaState == rhs.metaState)
    for (lhsArray, rhsArray) in zip(lhsState, rhsState) {
        expectEqual(lhsArray, rhsArray)
        #expect(
            lhsArray.asData(access: .noCopy).strides
                == rhsArray.asData(access: .noCopy).strides
        )
    }
}

private func expectEqual(_ lhs: MLXArray, _ rhs: MLXArray) {
    eval(lhs, rhs)
    #expect(lhs.shape == rhs.shape)
    #expect(lhs.dtype == rhs.dtype)
    #expect(lhs.asArray(Float.self) == rhs.asArray(Float.self))
}
