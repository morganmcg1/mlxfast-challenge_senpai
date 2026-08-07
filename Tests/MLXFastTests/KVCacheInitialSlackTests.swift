import MLX
import MLXLMCommon
import Testing

private func kvTensor(tokens: Int, width: Int, offset: Float = 0) -> MLXArray {
    let count = 2 * tokens * width
    return (MLXArray(0..<count).asType(.float32) * 0.001 + offset)
        .reshaped([1, 2, tokens, width])
}

private func expectEqual(_ actual: MLXArray, _ expected: MLXArray) {
    #expect(actual.shape == expected.shape)
    #expect(allClose(actual, expected).item(Bool.self))
}

@Test
func initialSlackExactStepSkipsFusedAppendContiguization() throws {
    let keys = kvTensor(tokens: 512, width: 4)
    let values = kvTensor(tokens: 512, width: 3, offset: 10)
    let cache = KVCacheSimple(initialSlack: true)

    let updated = cache.update(keys: keys, values: values)
    expectEqual(updated.0, keys)
    expectEqual(updated.1, values)
    #expect(cache.offset == 512)

    let initialBacking = cache.innerState()
    #expect(initialBacking.count == 2)
    #expect(initialBacking[0].shape == [1, 2, 768, 4])
    #expect(initialBacking[1].shape == [1, 2, 768, 3])
    #expect(initialBacking[0].asData(access: .noCopy).strides == [6144, 3072, 4, 1])
    #expect(initialBacking[1].asData(access: .noCopy).strides == [4608, 2304, 3, 1])
    expectEqual(cache.state[0], keys)
    expectEqual(cache.state[1], values)

    let firstPrepare = try #require(cache.fusedAppendPrepare())
    #expect(firstPrepare.writeIdx == 512)
    #expect(firstPrepare.keys === initialBacking[0])
    #expect(firstPrepare.values === initialBacking[1])

    let repeatedPrepare = try #require(cache.fusedAppendPrepare())
    #expect(repeatedPrepare.writeIdx == 512)
    #expect(repeatedPrepare.keys === firstPrepare.keys)
    #expect(repeatedPrepare.values === firstPrepare.values)

    let nextKeys = kvTensor(tokens: 1, width: 4, offset: 20)
    let nextValues = kvTensor(tokens: 1, width: 3, offset: 30)
    let firstKeys = firstPrepare.keys
    let firstValues = firstPrepare.values
    firstKeys[.ellipsis, firstPrepare.writeIdx ..< firstPrepare.writeIdx + 1, 0...] = nextKeys
    firstValues[.ellipsis, firstPrepare.writeIdx ..< firstPrepare.writeIdx + 1, 0...] = nextValues
    cache.fusedAppendAdvance()

    #expect(cache.offset == 513)
    expectEqual(cache.state[0], concatenated([keys, nextKeys], axis: 2))
    expectEqual(cache.state[1], concatenated([values, nextValues], axis: 2))

    let secondPrepare = try #require(cache.fusedAppendPrepare())
    #expect(secondPrepare.writeIdx == 513)
    #expect(secondPrepare.keys === firstPrepare.keys)
    #expect(secondPrepare.values === firstPrepare.values)

    let finalKeys = kvTensor(tokens: 1, width: 4, offset: 40)
    let finalValues = kvTensor(tokens: 1, width: 3, offset: 50)
    let secondKeys = secondPrepare.keys
    let secondValues = secondPrepare.values
    secondKeys[.ellipsis, secondPrepare.writeIdx ..< secondPrepare.writeIdx + 1, 0...] = finalKeys
    secondValues[.ellipsis, secondPrepare.writeIdx ..< secondPrepare.writeIdx + 1, 0...] = finalValues
    cache.fusedAppendAdvance()

    #expect(cache.offset == 514)
    #expect(cache.innerState()[0].shape == [1, 2, 768, 4])
    #expect(cache.innerState()[1].shape == [1, 2, 768, 3])
    expectEqual(cache.state[0], concatenated([keys, nextKeys, finalKeys], axis: 2))
    expectEqual(cache.state[1], concatenated([values, nextValues, finalValues], axis: 2))
}

@Test
func exactStepWithoutInitialSlackKeepsFusedAppendFallback() throws {
    let keys = kvTensor(tokens: 512, width: 4)
    let values = kvTensor(tokens: 512, width: 3, offset: 10)
    let cache = KVCacheSimple(initialSlack: false)

    _ = cache.update(keys: keys, values: values)
    #expect(cache.fusedAppendPrepare() == nil)
    #expect(cache.offset == 512)
    expectEqual(cache.state[0], keys)
    expectEqual(cache.state[1], values)

    #expect(cache.trim(1) == 1)
    let originalBacking = cache.innerState()
    let prepared = try #require(cache.fusedAppendPrepare())
    #expect(prepared.writeIdx == 511)
    #expect(prepared.keys !== originalBacking[0])
    #expect(prepared.values !== originalBacking[1])
    #expect(prepared.keys.asData(access: .noCopy).strides == [4096, 2048, 4, 1])
    #expect(prepared.values.asData(access: .noCopy).strides == [3072, 1536, 3, 1])
    expectEqual(cache.state[0], keys[.ellipsis, ..<511, 0...])
    expectEqual(cache.state[1], values[.ellipsis, ..<511, 0...])
}

@Test
func nonMultipleInitialUpdateKeepsFusedAppendFallback() throws {
    let keys = kvTensor(tokens: 511, width: 4)
    let values = kvTensor(tokens: 511, width: 3, offset: 10)
    let cache = KVCacheSimple(initialSlack: true)

    _ = cache.update(keys: keys, values: values)
    let originalBacking = cache.innerState()
    #expect(originalBacking[0].shape == [1, 2, 512, 4])
    #expect(originalBacking[1].shape == [1, 2, 512, 3])

    let prepared = try #require(cache.fusedAppendPrepare())
    #expect(prepared.writeIdx == 511)
    #expect(prepared.keys !== originalBacking[0])
    #expect(prepared.values !== originalBacking[1])
    #expect(prepared.keys.asData(access: .noCopy).strides == [4096, 2048, 4, 1])
    #expect(prepared.values.asData(access: .noCopy).strides == [3072, 1536, 3, 1])
    #expect(cache.offset == 511)
    expectEqual(cache.state[0], keys)
    expectEqual(cache.state[1], values)
}

@Test
func replacingStateInvalidatesFusedAppendPreparation() throws {
    let keys = kvTensor(tokens: 512, width: 4)
    let values = kvTensor(tokens: 512, width: 3, offset: 10)
    let cache = KVCacheSimple(initialSlack: true)

    _ = cache.update(keys: keys, values: values)
    _ = try #require(cache.fusedAppendPrepare())

    let replacementState = cache.state
    #expect(replacementState[0].shape == [1, 2, 512, 4])
    #expect(replacementState[1].shape == [1, 2, 512, 3])
    cache.state = replacementState
    #expect(cache.offset == 512)

    #expect(cache.trim(1) == 1)
    let restoredBacking = cache.innerState()
    #expect(restoredBacking[0] === replacementState[0])
    #expect(restoredBacking[1] === replacementState[1])

    let prepared = try #require(cache.fusedAppendPrepare())
    #expect(prepared.writeIdx == 511)
    #expect(prepared.keys !== restoredBacking[0])
    #expect(prepared.values !== restoredBacking[1])
    #expect(prepared.keys.asData(access: .noCopy).strides == [4096, 2048, 4, 1])
    #expect(prepared.values.asData(access: .noCopy).strides == [3072, 1536, 3, 1])
    expectEqual(cache.state[0], keys[.ellipsis, ..<511, 0...])
    expectEqual(cache.state[1], values[.ellipsis, ..<511, 0...])
}
