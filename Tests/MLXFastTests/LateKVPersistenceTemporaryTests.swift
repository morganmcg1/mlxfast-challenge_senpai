import CryptoKit
import Foundation
import MLX
@testable import MLXFastModel
import MLXLMCommon
import Testing

private let lateKVHeadDim = LagunaConstants.headDim
private let lateKVHeads = LagunaConstants.numKeyValueHeads

private func lateKVPattern(_ shape: [Int], salt: Int) -> MLXArray {
    let count = shape.reduce(1, *)
    let values = (0..<count).map { index -> Float in
        let centered = (index &* 17 &+ salt &* 29) % 251 - 125
        return Float(centered) / 64
    }
    return MLXArray(values, shape).asType(.bfloat16)
}

private func lateKVCachePattern(
    capacity: Int,
    target: Int,
    salt: Int,
    poison: Float
) -> MLXArray {
    let shape = [1, lateKVHeads, capacity, lateKVHeadDim]
    let count = shape.reduce(1, *)
    var values = (0..<count).map { index -> Float in
        let centered = (index &* 13 &+ salt &* 31) % 127 - 63
        return Float(centered) / 32
    }
    for head in 0..<lateKVHeads {
        let row = (head * capacity + target) * lateKVHeadDim
        for column in 0..<lateKVHeadDim {
            values[row + column] = poison + Float(head) / 8 + Float(column % 7) / 64
        }
    }
    return MLXArray(values, shape).asType(.bfloat16)
}

private func lateKVIdentityAngles(rotaryPairs: Int) -> MLXArray {
    MLXArray(
        Array(repeating: Float(1), count: rotaryPairs)
            + Array(repeating: Float(0), count: rotaryPairs),
        [1, 1, 1, rotaryPairs * 2]
    )
}

private func lateKVBits(_ array: MLXArray) -> [UInt32] {
    array.asArray(Float.self).map(\.bitPattern)
}

private func lateKVRowBits(_ array: MLXArray, index: Int) -> [UInt32] {
    let row = array[.ellipsis, index ..< (index + 1), 0...]
    eval(row)
    return lateKVBits(row)
}

private func lateKVDigest(_ bitPatterns: [UInt32]) -> String {
    var data = Data(capacity: bitPatterns.count * MemoryLayout<UInt32>.size)
    for bitPattern in bitPatterns {
        var littleEndian = bitPattern.littleEndian
        withUnsafeBytes(of: &littleEndian) { data.append(contentsOf: $0) }
    }
    return SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}

private func lateKVInputs(heads: Int, salt: Int, rotaryPairs: Int) -> (
    queries: MLXArray,
    keys: MLXArray,
    values: MLXArray,
    queryWeight: MLXArray,
    keyWeight: MLXArray,
    angles: MLXArray,
    scale: MLXArray
) {
    (
        lateKVPattern([1, 1, heads * lateKVHeadDim], salt: salt),
        lateKVPattern([1, 1, lateKVHeads * lateKVHeadDim], salt: salt + 1),
        lateKVPattern([1, 1, lateKVHeads * lateKVHeadDim], salt: salt + 2),
        lateKVPattern([lateKVHeadDim], salt: salt + 3),
        lateKVPattern([lateKVHeadDim], salt: salt + 4),
        lateKVIdentityAngles(rotaryPairs: rotaryPairs),
        MLXArray([1 / sqrt(Float(lateKVHeadDim))])
    )
}

private func lateKVExpectedValueBits(_ rawValues: MLXArray) -> [UInt32] {
    let row = rawValues.reshaped([1, lateKVHeads, 1, lateKVHeadDim])
    eval(row)
    return lateKVBits(row)
}

private func lateKVRunSliding(writeIdx: Int) {
    let capacity = LagunaConstants.slidingWindow
    let left = (writeIdx + capacity - 1) % capacity
    let right = (writeIdx + 1) % capacity
    let inputs = lateKVInputs(
        heads: LagunaConstants.slidingAttentionHeads,
        salt: 100 + writeIdx,
        rotaryPairs: lateKVHeadDim / 2
    )
    let nextInputs = lateKVInputs(
        heads: LagunaConstants.slidingAttentionHeads,
        salt: 1_100 + writeIdx,
        rotaryPairs: lateKVHeadDim / 2
    )
    let cache = RotatingKVCache(maxSize: capacity, step: capacity)
    let cacheKeys = lateKVCachePattern(
        capacity: capacity, target: writeIdx, salt: 200 + writeIdx, poison: 29)
    let cacheValues = lateKVCachePattern(
        capacity: capacity, target: writeIdx, salt: 300 + writeIdx, poison: -31)
    let logicalBefore = capacity + writeIdx
    let physicalBefore = writeIdx == 0 ? capacity : writeIdx
    cache.state = [cacheKeys, cacheValues]
    cache.metaState = ["0", "\(capacity)", "\(capacity)", "\(logicalBefore)", "\(physicalBefore)"]

    let prepared = cache.fusedRingPrepare()
    #expect(prepared != nil)
    guard let prepared else { return }
    #expect(prepared.writeIdx == writeIdx)

    let poisonK = lateKVRowBits(prepared.keys, index: writeIdx)
    let poisonV = lateKVRowBits(prepared.values, index: writeIdx)
    let leftK = lateKVRowBits(prepared.keys, index: left)
    let leftV = lateKVRowBits(prepared.values, index: left)
    let rightK = lateKVRowBits(prepared.keys, index: right)
    let rightV = lateKVRowBits(prepared.values, index: right)

    let (_, expectedKeys) = lagunaSlidingQKNormRoPE(
        rawQueries: inputs.queries,
        rawKeys: inputs.keys,
        queryWeight: inputs.queryWeight,
        keyWeight: inputs.keyWeight,
        angles: inputs.angles
    )
    eval(expectedKeys)
    let expectedK = lateKVBits(expectedKeys)
    let expectedV = lateKVExpectedValueBits(inputs.values)
    #expect(poisonK != expectedK)
    #expect(poisonV != expectedV)

    let attended = lagunaSlidingFusedAttention(
        rawQueries: inputs.queries,
        rawKeys: inputs.keys,
        rawValues: inputs.values,
        queryWeight: inputs.queryWeight,
        keyWeight: inputs.keyWeight,
        angles: inputs.angles,
        cacheKeys: prepared.keys,
        cacheValues: prepared.values,
        writeIdx: prepared.writeIdx,
        scale: inputs.scale
    )
    eval(attended)
    cache.fusedRingAdvance()

    let actualK = lateKVRowBits(prepared.keys, index: writeIdx)
    let actualV = lateKVRowBits(prepared.values, index: writeIdx)
    #expect(actualK == expectedK)
    #expect(actualV == expectedV)
    #expect(lateKVRowBits(prepared.keys, index: left) == leftK)
    #expect(lateKVRowBits(prepared.values, index: left) == leftV)
    #expect(lateKVRowBits(prepared.keys, index: right) == rightK)
    #expect(lateKVRowBits(prepared.values, index: right) == rightV)
    #expect(cache.offset == logicalBefore + 1)
    #expect(Int(cache.metaState[4]) == writeIdx + 1)

    let next = cache.fusedRingPrepare()
    #expect(next != nil)
    guard let next else { return }
    #expect(next.writeIdx == right)
    let continuation = lagunaSlidingFusedAttention(
        rawQueries: nextInputs.queries,
        rawKeys: nextInputs.keys,
        rawValues: nextInputs.values,
        queryWeight: nextInputs.queryWeight,
        keyWeight: nextInputs.keyWeight,
        angles: nextInputs.angles,
        cacheKeys: next.keys,
        cacheValues: next.values,
        writeIdx: next.writeIdx,
        scale: nextInputs.scale
    )
    eval(continuation)
    cache.fusedRingAdvance()
    #expect(cache.offset == logicalBefore + 2)
    #expect(Int(cache.metaState[4]) == (writeIdx + 2) % capacity)

    print(
        "LATE_KV family=sliding N=512 widx=\(writeIdx) "
            + "attended=\(lateKVDigest(lateKVBits(attended))) "
            + "k=\(lateKVDigest(actualK)) v=\(lateKVDigest(actualV)) "
            + "leftK=\(lateKVDigest(leftK)) leftV=\(lateKVDigest(leftV)) "
            + "rightK=\(lateKVDigest(rightK)) rightV=\(lateKVDigest(rightV)) "
            + "continuation=\(lateKVDigest(lateKVBits(continuation))) "
            + "logical=\(cache.offset) physical=\(cache.metaState[4])"
    )
}

private func lateKVRunFull(length: Int, writeIdx: Int) {
    #expect(length == writeIdx + 1)
    let capacity = length + 1
    let left = writeIdx - 1
    let right = writeIdx + 1
    let inputs = lateKVInputs(
        heads: LagunaConstants.fullAttentionHeads,
        salt: 2_000 + writeIdx,
        rotaryPairs: lateKVHeadDim / 4
    )
    let nextInputs = lateKVInputs(
        heads: LagunaConstants.fullAttentionHeads,
        salt: 3_000 + writeIdx,
        rotaryPairs: lateKVHeadDim / 4
    )
    let cache = KVCacheSimple()
    cache.step = capacity
    let cacheKeys = lateKVCachePattern(
        capacity: capacity, target: writeIdx, salt: 4_000 + writeIdx, poison: 29)
    let cacheValues = lateKVCachePattern(
        capacity: capacity, target: writeIdx, salt: 5_000 + writeIdx, poison: -31)
    cache.state = [cacheKeys, cacheValues]
    cache.offset = writeIdx

    let prepared = cache.fusedAppendPrepare()
    #expect(prepared != nil)
    guard let prepared else { return }
    #expect(prepared.writeIdx == writeIdx)

    let poisonK = lateKVRowBits(prepared.keys, index: writeIdx)
    let poisonV = lateKVRowBits(prepared.values, index: writeIdx)
    let leftK = lateKVRowBits(prepared.keys, index: left)
    let leftV = lateKVRowBits(prepared.values, index: left)
    let rightK = lateKVRowBits(prepared.keys, index: right)
    let rightV = lateKVRowBits(prepared.values, index: right)

    let (_, expectedKeys) = lagunaFullQKNormYaRN(
        rawQueries: inputs.queries,
        rawKeys: inputs.keys,
        queryWeight: inputs.queryWeight,
        keyWeight: inputs.keyWeight,
        angles: inputs.angles
    )
    eval(expectedKeys)
    let expectedK = lateKVBits(expectedKeys)
    let expectedV = lateKVExpectedValueBits(inputs.values)
    #expect(poisonK != expectedK)
    #expect(poisonV != expectedV)

    let attended = lagunaFullFusedAttention(
        rawQueries: inputs.queries,
        rawKeys: inputs.keys,
        rawValues: inputs.values,
        queryWeight: inputs.queryWeight,
        keyWeight: inputs.keyWeight,
        angles: inputs.angles,
        cacheKeys: prepared.keys,
        cacheValues: prepared.values,
        writeIdx: prepared.writeIdx,
        scale: inputs.scale
    )
    eval(attended)
    cache.fusedAppendAdvance()

    let actualK = lateKVRowBits(prepared.keys, index: writeIdx)
    let actualV = lateKVRowBits(prepared.values, index: writeIdx)
    #expect(actualK == expectedK)
    #expect(actualV == expectedV)
    #expect(lateKVRowBits(prepared.keys, index: left) == leftK)
    #expect(lateKVRowBits(prepared.values, index: left) == leftV)
    #expect(lateKVRowBits(prepared.keys, index: right) == rightK)
    #expect(lateKVRowBits(prepared.values, index: right) == rightV)
    #expect(cache.offset == length)

    let next = cache.fusedAppendPrepare()
    #expect(next != nil)
    guard let next else { return }
    #expect(next.writeIdx == right)
    let continuation = lagunaFullFusedAttention(
        rawQueries: nextInputs.queries,
        rawKeys: nextInputs.keys,
        rawValues: nextInputs.values,
        queryWeight: nextInputs.queryWeight,
        keyWeight: nextInputs.keyWeight,
        angles: nextInputs.angles,
        cacheKeys: next.keys,
        cacheValues: next.values,
        writeIdx: next.writeIdx,
        scale: nextInputs.scale
    )
    eval(continuation)
    cache.fusedAppendAdvance()
    #expect(cache.offset == length + 1)

    print(
        "LATE_KV family=full N=\(length) widx=\(writeIdx) "
            + "attended=\(lateKVDigest(lateKVBits(attended))) "
            + "k=\(lateKVDigest(actualK)) v=\(lateKVDigest(actualV)) "
            + "leftK=\(lateKVDigest(leftK)) leftV=\(lateKVDigest(leftV)) "
            + "rightK=\(lateKVDigest(rightK)) rightV=\(lateKVDigest(rightV)) "
            + "continuation=\(lateKVDigest(lateKVBits(continuation))) "
            + "logical=\(cache.offset) physical=\(cache.offset)"
    )
}

@Test
func lateKVPersistencePoisonedRowsMatchReferenceWhenEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_LATE_KV_TESTS"] == "1" else {
        return
    }

    for writeIdx in [0, 31, 32, 511] {
        lateKVRunSliding(writeIdx: writeIdx)
    }
    for (length, writeIdx) in [(2, 1), (32, 31), (513, 512), (640, 639)] {
        lateKVRunFull(length: length, writeIdx: writeIdx)
    }
}

private struct LateKVTimingInputs {
    let queries: MLXArray
    let keys: MLXArray
    let values: MLXArray
    let queryWeight: MLXArray
    let keyWeight: MLXArray
    let angles: MLXArray
    let cacheKeys: MLXArray
    let cacheValues: MLXArray
    let scale: MLXArray
}

private func lateKVTimingInputs(
    heads: Int,
    capacity: Int,
    salt: Int,
    rotaryPairs: Int
) -> LateKVTimingInputs {
    let inputs = lateKVInputs(heads: heads, salt: salt, rotaryPairs: rotaryPairs)
    let timing = LateKVTimingInputs(
        queries: inputs.queries,
        keys: inputs.keys,
        values: inputs.values,
        queryWeight: inputs.queryWeight,
        keyWeight: inputs.keyWeight,
        angles: inputs.angles,
        cacheKeys: lateKVPattern(
            [1, lateKVHeads, capacity, lateKVHeadDim], salt: salt + 5),
        cacheValues: lateKVPattern(
            [1, lateKVHeads, capacity, lateKVHeadDim], salt: salt + 6),
        scale: inputs.scale
    )
    eval([
        timing.queries, timing.keys, timing.values,
        timing.queryWeight, timing.keyWeight, timing.angles,
        timing.cacheKeys, timing.cacheValues, timing.scale,
    ])
    Stream.gpu.synchronize()
    return timing
}

private func lateKVTimedBatch(
    family: String,
    length: Int,
    writeIdx: Int,
    makeOutput: () -> MLXArray
) {
    let batchSize = 128
    for _ in 0..<2 {
        let outputs = (0..<batchSize).map { _ in makeOutput() }
        eval(outputs)
        Stream.gpu.synchronize()
    }

    let outputs = (0..<batchSize).map { _ in makeOutput() }
    let start = DispatchTime.now().uptimeNanoseconds
    eval(outputs)
    Stream.gpu.synchronize()
    let elapsed = DispatchTime.now().uptimeNanoseconds - start
    print(
        "LATE_KV_TIMING,family=\(family),N=\(length),widx=\(writeIdx),kernels=\(batchSize),ns=\(elapsed),ns_per_kernel=\(Double(elapsed) / Double(batchSize))"
    )
}

@Test
func lateKVIsolatedTiming() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_LATE_KV_TIMING"] == "1" else {
        return
    }

    let slidingWriteIdx = LagunaConstants.slidingWindow - 1
    let sliding = lateKVTimingInputs(
        heads: LagunaConstants.slidingAttentionHeads,
        capacity: LagunaConstants.slidingWindow,
        salt: 2_000,
        rotaryPairs: lateKVHeadDim / 2
    )
    lateKVTimedBatch(
        family: "sliding",
        length: LagunaConstants.slidingWindow,
        writeIdx: slidingWriteIdx
    ) {
        lagunaSlidingFusedAttention(
            rawQueries: sliding.queries,
            rawKeys: sliding.keys,
            rawValues: sliding.values,
            queryWeight: sliding.queryWeight,
            keyWeight: sliding.keyWeight,
            angles: sliding.angles,
            cacheKeys: sliding.cacheKeys,
            cacheValues: sliding.cacheValues,
            writeIdx: slidingWriteIdx,
            scale: sliding.scale
        )
    }

    let fullWriteIdx = 639
    let full = lateKVTimingInputs(
        heads: LagunaConstants.fullAttentionHeads,
        capacity: 768,
        salt: 3_000,
        rotaryPairs: lateKVHeadDim / 4
    )
    lateKVTimedBatch(
        family: "full",
        length: fullWriteIdx + 1,
        writeIdx: fullWriteIdx
    ) {
        lagunaFullFusedAttention(
            rawQueries: full.queries,
            rawKeys: full.keys,
            rawValues: full.values,
            queryWeight: full.queryWeight,
            keyWeight: full.keyWeight,
            angles: full.angles,
            cacheKeys: full.cacheKeys,
            cacheValues: full.cacheValues,
            writeIdx: fullWriteIdx,
            scale: full.scale
        )
    }
}
