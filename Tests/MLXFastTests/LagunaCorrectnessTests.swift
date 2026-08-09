import Foundation
import CryptoKit
import MLX
import MLXFastCore
@testable import MLXFastModel
@testable import MLXFastHarness
import Testing

@Test
func lagunaExpertAlignedGatherRequiresNAXHardwareAndOS() {
    #expect(!lagunaNAXAvailable(architecture: "agxg16s", osSupportsNAX: true))
    #expect(lagunaNAXAvailable(architecture: "agxg17s", osSupportsNAX: true))
    #expect(!lagunaNAXAvailable(architecture: "agxg17p", osSupportsNAX: true))
    #expect(lagunaNAXAvailable(architecture: "agxg18p", osSupportsNAX: true))
    #expect(!lagunaNAXAvailable(architecture: "agxg17s", osSupportsNAX: false))
    #expect(!lagunaNAXAvailable(architecture: "unknown", osSupportsNAX: true))
}

private enum H48PacketPattern: UInt32 {
    case random = 1
    case ties
    case extremeFinite
    case nonFiniteQuery
    case nonFiniteKey
    case nonFiniteValue
}

private struct H48PacketSnapshot: Equatable {
    var outputBits: [UInt16]
    var keyBits: [UInt16]
    var valueBits: [UInt16]
    let initialKeyBits: [UInt16]
    let initialValueBits: [UInt16]
    let rawValueBits: [UInt16]
    let capacity: Int
    let backingOffset: Int
    let writeIdx: Int
}

private func h48ModerateBits(count: Int, seed: UInt32) -> [UInt16] {
    var state = seed
    return (0..<count).map { _ in
        state = 1_664_525 &* state &+ 1_013_904_223
        let sign = UInt16((state >> 31) << 15)
        let exponent = UInt16(124 + ((state >> 8) % 7)) << 7
        return sign | exponent | UInt16(state & 0x7f)
    }
}

private func h48PacketInputs(
    pattern: H48PacketPattern, seed: UInt32
) -> (MLXArray, MLXArray, MLXArray, [UInt16], MLXArray, MLXArray, MLXArray, MLXArray) {
    let headDim = LagunaConstants.headDim
    let heads = LagunaConstants.fullAttentionHeads
    let kvHeads = LagunaConstants.numKeyValueHeads
    var queryBits = h48ModerateBits(count: heads * headDim, seed: seed)
    var keyBits = h48ModerateBits(count: kvHeads * headDim, seed: seed &+ 1)
    var valueBits = h48ModerateBits(count: kvHeads * headDim, seed: seed &+ 2)

    switch pattern {
    case .random:
        break
    case .ties:
        queryBits = Array(repeating: 0, count: queryBits.count)
    case .extremeFinite:
        let extremes: [UInt16] = [0x7f7f, 0xff7f, 0x0080, 0x8080, 0x0001, 0x8001, 0, 0x8000]
        for index in queryBits.indices {
            queryBits[index] = extremes[index % extremes.count]
        }
        for index in keyBits.indices {
            keyBits[index] = extremes[(index + 3) % extremes.count]
        }
        for index in valueBits.indices {
            valueBits[index] = extremes[(index + 5) % extremes.count]
        }
    case .nonFiniteQuery:
        queryBits.replaceSubrange(0..<3, with: [0x7f80, 0xff80, 0x7fc1])
    case .nonFiniteKey:
        keyBits.replaceSubrange(0..<3, with: [0x7f80, 0xff80, 0x7fc1])
    case .nonFiniteValue:
        valueBits.replaceSubrange(0..<3, with: [0x7f80, 0xff80, 0x7fc1])
    }

    let rawQueries = MLXArray(queryBits, [1, 1, queryBits.count]).view(dtype: .bfloat16)
    let rawKeys = MLXArray(keyBits, [1, 1, keyBits.count]).view(dtype: .bfloat16)
    let rawValues = MLXArray(valueBits, [1, 1, valueBits.count]).view(dtype: .bfloat16)
    let queryWeight = MLXArray(
        h48ModerateBits(count: headDim, seed: seed &+ 3), [headDim]
    ).view(dtype: .bfloat16)
    let keyWeight = MLXArray(
        h48ModerateBits(count: headDim, seed: seed &+ 4), [headDim]
    ).view(dtype: .bfloat16)
    let angleValues = (0..<(headDim / 4)).map { cos(Float($0 + 1) / 64) }
        + (0..<(headDim / 4)).map { sin(Float($0 + 1) / 64) }
    let angles = MLXArray(angleValues, [1, 1, 1, headDim / 2])
    let scale = MLXArray([pow(Float(headDim), -0.5)])
    return (
        rawQueries, rawKeys, rawValues, valueBits,
        queryWeight, keyWeight, angles, scale
    )
}

private func h48PacketSnapshot(
    pattern: H48PacketPattern, length: Int, packetHeads: Int, seed: UInt32
) -> H48PacketSnapshot {
    let headDim = LagunaConstants.headDim
    let kvHeads = LagunaConstants.numKeyValueHeads
    let capacity = length <= 256 ? 256 : (length <= 512 ? 512 : 768)
    let backingOffset = (1 + length % 3) * headDim
    let viewCount = kvHeads * capacity * headDim
    let backingCount = backingOffset + viewCount + 2 * headDim
    var initialKeyBits = h48ModerateBits(count: backingCount, seed: seed &+ 5)
    var initialValueBits = h48ModerateBits(count: backingCount, seed: seed &+ 6)
    let writeIdx = length - 1
    for kvHead in 0..<kvHeads {
        let start = backingOffset + (kvHead * capacity + writeIdx) * headDim
        let sentinel = repeatElement(UInt16(0x2a5a), count: headDim)
        initialKeyBits.replaceSubrange(start..<(start + headDim), with: sentinel)
        initialValueBits.replaceSubrange(start..<(start + headDim), with: sentinel)
    }

    let keyParent = MLXArray(initialKeyBits).view(dtype: .bfloat16)
    let valueParent = MLXArray(initialValueBits).view(dtype: .bfloat16)
    let cacheShape = [1, kvHeads, capacity, headDim]
    let cacheKeys = asStrided(keyParent, cacheShape, offset: backingOffset)
    let cacheValues = asStrided(valueParent, cacheShape, offset: backingOffset)
    let inputs = h48PacketInputs(pattern: pattern, seed: seed)
    eval(keyParent, valueParent)
    let output = lagunaFullFusedAttention(
        rawQueries: inputs.0,
        rawKeys: inputs.1,
        rawValues: inputs.2,
        queryWeight: inputs.4,
        keyWeight: inputs.5,
        angles: inputs.6,
        cacheKeys: cacheKeys,
        cacheValues: cacheValues,
        writeIdx: writeIdx,
        scale: inputs.7,
        packetHeads: packetHeads
    )
    eval(output)

    return H48PacketSnapshot(
        outputBits: output.view(dtype: .uint16).asArray(UInt16.self),
        keyBits: keyParent.view(dtype: .uint16).asArray(UInt16.self),
        valueBits: valueParent.view(dtype: .uint16).asArray(UInt16.self),
        initialKeyBits: initialKeyBits,
        initialValueBits: initialValueBits,
        rawValueBits: inputs.3,
        capacity: capacity,
        backingOffset: backingOffset,
        writeIdx: writeIdx
    )
}

private func h48ValidatePacketMutation(_ snapshot: H48PacketSnapshot) {
    let headDim = LagunaConstants.headDim
    let heads = LagunaConstants.fullAttentionHeads
    let kvHeads = LagunaConstants.numKeyValueHeads
    let viewCount = kvHeads * snapshot.capacity * headDim
    let changedKeys = snapshot.keyBits.indices.filter {
        snapshot.keyBits[$0] != snapshot.initialKeyBits[$0]
    }
    let changedValues = snapshot.valueBits.indices.filter {
        snapshot.valueBits[$0] != snapshot.initialValueBits[$0]
    }
    let isWrittenRow: (Int) -> Bool = { index in
        let local = index - snapshot.backingOffset
        guard local >= 0, local < viewCount else { return false }
        return (local % (snapshot.capacity * headDim)) / headDim == snapshot.writeIdx
    }

    #expect(snapshot.outputBits.count == heads * headDim)
    #expect(changedKeys.count == kvHeads * headDim)
    #expect(changedValues.count == kvHeads * headDim)
    #expect(changedKeys.allSatisfy(isWrittenRow))
    #expect(changedValues.allSatisfy(isWrittenRow))
    #expect((0..<kvHeads).allSatisfy { kvHead in
        let start = snapshot.backingOffset
            + (kvHead * snapshot.capacity + snapshot.writeIdx) * headDim
        return Array(snapshot.valueBits[start..<(start + headDim)])
            == Array(snapshot.rawValueBits[(kvHead * headDim)..<((kvHead + 1) * headDim)])
    })
}

@Test
func lagunaFullAttentionTriplePacketMatchesPairPacketBitExactlyWhenRuntimeTestsAreEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
        return
    }

    let requestedLengths = [1, 31, 32, 33, 511, 512, 513, 514, 576, 640]
    var positiveControlSnapshot: H48PacketSnapshot?
    for length in requestedLengths {
        let seed = UInt32(10_000 + length)
        let pair = h48PacketSnapshot(
            pattern: .random, length: length, packetHeads: 2, seed: seed)
        let triple = h48PacketSnapshot(
            pattern: .random, length: length, packetHeads: 3, seed: seed)
        h48ValidatePacketMutation(pair)
        h48ValidatePacketMutation(triple)
        #expect(pair == triple)
        positiveControlSnapshot = positiveControlSnapshot ?? triple
    }

    for (pattern, lengths) in [
        (H48PacketPattern.ties, [32, 33, 512, 513]),
        (.extremeFinite, [33, 513, 640]),
    ] {
        for length in lengths {
            let seed = pattern.rawValue &* 100_000 &+ UInt32(length)
            let pair = h48PacketSnapshot(
                pattern: pattern, length: length, packetHeads: 2, seed: seed)
            let triple = h48PacketSnapshot(
                pattern: pattern, length: length, packetHeads: 3, seed: seed)
            h48ValidatePacketMutation(pair)
            h48ValidatePacketMutation(triple)
            #expect(pair == triple)
        }
    }

    for (pattern, length) in [
        (H48PacketPattern.nonFiniteQuery, 33),
        (.nonFiniteKey, 513),
        (.nonFiniteValue, 640),
    ] {
        let seed = pattern.rawValue &* 100_000 &+ UInt32(length)
        let pairA = h48PacketSnapshot(
            pattern: pattern, length: length, packetHeads: 2, seed: seed)
        let pairB = h48PacketSnapshot(
            pattern: pattern, length: length, packetHeads: 2, seed: seed)
        let triple = h48PacketSnapshot(
            pattern: pattern, length: length, packetHeads: 3, seed: seed)
        #expect(pairA == pairB)
        #expect(pairA == triple)
    }

    let clean = positiveControlSnapshot!
    var corruptedOutput = clean
    corruptedOutput.outputBits[clean.outputBits.count / 2] ^= 1
    #expect(clean != corruptedOutput)
    var corruptedKeyGuard = clean
    corruptedKeyGuard.keyBits[0] ^= 1
    #expect(clean != corruptedKeyGuard)
    var corruptedValueRow = clean
    let valueRowIndex = clean.backingOffset + clean.writeIdx * LagunaConstants.headDim
    corruptedValueRow.valueBits[valueRowIndex] ^= 1
    #expect(clean != corruptedValueRow)
}

@Test
func lagunaExpertAlignedGatherRequiresPackedStageVariant() {
    #expect(lagunaExpertAlignedStageEnabled(nil))
    #expect(lagunaExpertAlignedStageEnabled(""))
    #expect(lagunaExpertAlignedStageEnabled("4"))
    #expect(lagunaExpertAlignedStageEnabled("5"))
    #expect(!lagunaExpertAlignedStageEnabled("0"))
    #expect(!lagunaExpertAlignedStageEnabled("invalid"))
}

@Test
func lagunaCorrectnessComparesExpectedTokenSequences() {
    let pass = LagunaCorrectness.compareTokens(
        expected: [4, 5, 6],
        actual: [4, 5, 6],
        steps: 3
    )
    #expect(pass.passed)
    #expect(pass.checkedSteps == 3)
    #expect(pass.firstFailingStep == nil)

    let fail = LagunaCorrectness.compareTokens(
        expected: [4, 5, 6],
        actual: [4, 9, 6],
        steps: 3
    )
    #expect(!fail.passed)
    #expect(fail.checkedSteps == 2)
    #expect(fail.firstFailingStep == 1)
    #expect(fail.expectedToken == 5)
    #expect(fail.actualToken == 9)

    let short = LagunaCorrectness.compareTokens(
        expected: [4, 5, 6],
        actual: [4],
        steps: 3
    )
    #expect(!short.passed)
    #expect(short.checkedSteps == 2)
    #expect(short.firstFailingStep == 1)
    #expect(short.expectedToken == 5)
    #expect(short.actualToken == nil)

    let expectedShort = LagunaCorrectness.compareTokens(
        expected: [4],
        actual: [4, 5],
        steps: 2
    )
    #expect(!expectedShort.passed)
    #expect(expectedShort.checkedSteps == 2)
    #expect(expectedShort.firstFailingStep == 1)
    #expect(expectedShort.expectedToken == nil)
    #expect(expectedShort.actualToken == 5)

    let bothShort = LagunaCorrectness.compareTokens(
        expected: [4],
        actual: [4],
        steps: 2
    )
    #expect(!bothShort.passed)
    #expect(bothShort.checkedSteps == 2)
    #expect(bothShort.firstFailingStep == 1)
    #expect(bothShort.expectedToken == nil)
    #expect(bothShort.actualToken == nil)
}

@Test
func lagunaCorrectnessGeneratesGreedyTokensWithGrowingContext() throws {
    var contexts: [[Int]] = []
    let generated = try LagunaCorrectness.generateGreedyNoCache(
        promptTokens: [10, 11],
        steps: 3
    ) { context in
        contexts.append(context)
        return context.count
    }

    #expect(generated == [2, 3, 4])
    #expect(contexts == [[10, 11], [10, 11, 2], [10, 11, 2, 3]])
}

@Test
func lagunaCorrectnessTeacherForcedUsesGoldenPrefix() throws {
    var contexts: [[Int]] = []
    let expected = [20, 21, 22]
    let comparison = try LagunaCorrectness.compareTeacherForcedNoCache(
        promptTokens: [10, 11],
        expectedTokens: expected,
        steps: expected.count
    ) { context in
        contexts.append(context)
        return expected[context.count - 2]
    }

    #expect(comparison.passed)
    #expect(comparison.checkedSteps == 3)
    #expect(contexts == [[10, 11], [10, 11, 20], [10, 11, 20, 21]])
}

@Test
func correctnessReportEncodesStableFailureFields() throws {
    let report = CorrectnessReport(
        passed: true,
        checkedSteps: MLXFastConstants.correctnessSteps,
        caseCount: 1,
        expertCacheHits: 4,
        expertCacheMisses: 6,
        expertCacheEvictions: 2,
        expertBytesRead: 2048,
        expertReadSeconds: 0.5,
        expertPeakCachedTensors: 8,
        expertHitRate: 0.4,
        firstFailingCase: nil,
        firstFailingStep: nil,
        expectedToken: nil,
        actualToken: nil,
        goldenHash: "abc123",
        error: ""
    )
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    let data = try encoder.encode(report)
    let raw = String(decoding: data, as: UTF8.self)

    #expect(raw.contains("\"first_failing_case\" : null"))
    #expect(raw.contains("\"first_failing_step\" : null"))
    #expect(raw.contains("\"expected_token\" : null"))
    #expect(raw.contains("\"actual_token\" : null"))
    #expect(raw.contains("\"checked_steps\" : \(MLXFastConstants.correctnessSteps)"))
    #expect(raw.contains("\"case_count\" : 1"))
    #expect(raw.contains("\"expert_cache_hits\" : 4"))
    #expect(raw.contains("\"expert_cache_misses\" : 6"))
    #expect(raw.contains("\"expert_cache_evictions\" : 2"))
    #expect(raw.contains("\"expert_bytes_read\" : 2048"))
    #expect(raw.contains("\"expert_read_seconds\" : 0.5"))
    #expect(raw.contains("\"expert_peak_cached_tensors\" : 8"))
    #expect(raw.contains("\"expert_hit_rate\" : 0.4"))
    #expect(raw.contains("\"golden_hash\" : \"abc123\""))
    #expect(report.expertStreamingStats.cacheHits == 4)
    #expect(report.expertStreamingStats.cacheMisses == 6)
    #expect(report.expertStreamingStats.hitRate == 0.4)
}

@Test
func lagunaRuntimeCorrectnessReportsMissingArtifacts() throws {
    let directory = try temporaryDirectory()
    defer { try? FileManager.default.removeItem(at: directory) }

    let report = try LagunaRuntime.runCorrectness(
        CorrectnessOptions(
            weightsPath: directory.appendingPathComponent("missing-weights").path,
            goldenPath: directory.appendingPathComponent("missing-golden.json").path
        )
    )

    #expect(!report.passed)
    #expect(report.checkedSteps == 0)
    #expect(report.firstFailingCase == nil)
    #expect(report.error.contains("correctness golden file"))
}

@Test
func lagunaRuntimeCorrectnessReportsGoldenMetadataWhenWeightsAreMissing() throws {
    let directory = try temporaryDirectory()
    defer { try? FileManager.default.removeItem(at: directory) }

    let goldenPath = directory.appendingPathComponent("golden.json")
    let expected = Array(repeating: 7, count: MLXFastConstants.correctnessSteps)
    let json = """
    {
      "version": 1,
      "cases": [
        {
          "name": "valid-golden",
          "prompt_tokens": \(arrayJSON(Array(repeating: 1, count: MLXFastConstants.correctnessPromptTokens))),
          "expected_tokens": \(expected)
        }
      ]
    }
    """
    try json.write(to: goldenPath, atomically: true, encoding: .utf8)

    let report = try LagunaRuntime.runCorrectness(
        CorrectnessOptions(
            weightsPath: directory.appendingPathComponent("missing-weights").path,
            goldenPath: goldenPath.path
        )
    )

    let digest = SHA256.hash(data: try Data(contentsOf: goldenPath))
    let expectedHash = digest.map { String(format: "%02x", $0) }.joined()
    #expect(!report.passed)
    #expect(report.checkedSteps == 0)
    #expect(report.caseCount == 1)
    #expect(report.goldenHash == expectedHash)
    #expect(report.firstFailingCase == nil)
}

@Test
func lagunaRuntimeMatchesVendoredUpstreamOnM5WhenEnabled() throws {
    let environment = ProcessInfo.processInfo.environment
    guard environment["MLXFAST_RUN_LAGUNA_UPSTREAM_EQUIVALENCE"] == "1" else {
        return
    }
    let weightsPath = try #require(
        environment["MLXFAST_LAGUNA_EQUIVALENCE_WEIGHTS_PATH"]
    )
    let goldenPath =
        environment["MLXFAST_LAGUNA_EQUIVALENCE_GOLDEN_PATH"]
        ?? MLXFastConstants.defaultPublicCorrectnessGoldenPath
    let sourceCase = try #require(
        loadGoldenCases(
            from: goldenPath,
            requiredSteps: 8,
            requiredPromptTokens: MLXFastConstants.correctnessPromptTokens
        ).first
    )
    let tolerance = Float(
        environment["MLXFAST_LAGUNA_EQUIVALENCE_MAX_ABS_ERROR"] ?? "0"
    ) ?? 0

    let report = try LagunaUpstreamEquivalence.compare(
        weightsPath: weightsPath,
        promptTokens: sourceCase.promptTokens,
        decodeTokens: Array(sourceCase.expectedTokens.prefix(8))
    )
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    let encoded = try encoder.encode(report)
    print(String(decoding: encoded, as: UTF8.self))
    #expect(report.passes(maximumAbsoluteLogitError: tolerance))
}

private func temporaryDirectory() throws -> URL {
    let url = FileManager.default.temporaryDirectory.appendingPathComponent(
        UUID().uuidString,
        isDirectory: true
    )
    try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
    return url
}

private func arrayJSON(_ values: [Int]) -> String {
    "[\(values.map(String.init).joined(separator: ","))]"
}
