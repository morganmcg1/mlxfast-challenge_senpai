import Foundation
import CryptoKit
import MLX
import MLXFastCore
@testable import MLXFastModel
@testable import MLXFastHarness
import MLXLMCommon
import Testing

@Test
func lagunaSlidingInterleavedKVMatchesCanonical() throws {
    let window = LagunaConstants.slidingWindow
    let headDim = LagunaConstants.headDim
    let kvHeads = LagunaConstants.numKeyValueHeads
    let heads = LagunaConstants.slidingAttentionHeads

    let candidateSeed = lagunaSlidingKVSeed(length: window, phase: 0.0)
    let referenceSeed = lagunaSlidingKVSeed(length: window, phase: 0.0)
    eval(candidateSeed.keys, candidateSeed.values, referenceSeed.keys, referenceSeed.values)

    let candidate = lagunaSlidingRing(
        keys: candidateSeed.keys, values: candidateSeed.values)
    let reference = lagunaSlidingRing(
        keys: referenceSeed.keys, values: referenceSeed.values)

    let candidateInitial = try #require(candidate.fusedRingPrepare())
    let referenceInitial = try #require(reference.fusedRingPrepare())
    #expect(candidateInitial.writeIdx == 0)
    #expect(referenceInitial.writeIdx == 0)
    #expect(candidateInitial.interleavedKV.shape == [1, kvHeads, window, headDim / 4, 8])
    lagunaExpectInterleavedKVMatchesCanonical(
        candidateInitial.interleavedKV,
        keys: candidateInitial.keys,
        values: candidateInitial.values)
    lagunaExpectInterleavedKVMatchesCanonical(
        referenceInitial.interleavedKV,
        keys: referenceInitial.keys,
        values: referenceInitial.values)

    let queryAxis = MLXArray(0..<(heads * headDim))
        .asType(.float32).reshaped([1, 1, heads * headDim])
    let keyValueAxis = MLXArray(0..<(kvHeads * headDim))
        .asType(.float32).reshaped([1, 1, kvHeads * headDim])
    let weightAxis = MLXArray(0..<headDim).asType(.float32)
    let queryWeight = (cos(weightAxis * 0.007) * 0.125 + 1.0).asType(.bfloat16)
    let keyWeight = (sin(weightAxis * 0.011) * 0.125 + 1.0).asType(.bfloat16)
    let halfAxis = MLXArray(0..<(headDim / 2)).asType(.float32)
    let angles = concatenated(
        [cos(halfAxis * 0.019), sin(halfAxis * 0.019)]
    ).reshaped([1, 1, 1, headDim])
    let scale = MLXArray(Float(1.0 / sqrt(Float(headDim))))
    eval(queryWeight, keyWeight, angles, scale)

    var observedWriteIndices: Set<Int> = []
    for step in 0..<640 {
        let candidateRing = try #require(candidate.fusedRingPrepare())
        let referenceRing = try #require(reference.fusedRingPrepare())
        let expectedWriteIdx = step % window
        #expect(candidateRing.writeIdx == expectedWriteIdx)
        #expect(referenceRing.writeIdx == expectedWriteIdx)
        observedWriteIndices.insert(candidateRing.writeIdx)

        let phase = Float(step) * 0.017
        let rawQueries = (sin(queryAxis * 0.013 + phase) * 0.25).asType(.bfloat16)
        let rawKeys = (cos(keyValueAxis * 0.023 + phase * 0.5) * 0.25)
            .asType(.bfloat16)
        let rawValues = (sin(keyValueAxis * 0.029 + phase * 1.5) * 0.5)
            .asType(.bfloat16)

        let candidateOutput = lagunaSlidingFusedAttention(
            rawQueries: rawQueries,
            rawKeys: rawKeys,
            rawValues: rawValues,
            queryWeight: queryWeight,
            keyWeight: keyWeight,
            angles: angles,
            cacheKeys: candidateRing.keys,
            cacheValues: candidateRing.values,
            cacheInterleavedKV: candidateRing.interleavedKV,
            writeIdx: candidateRing.writeIdx,
            scale: scale,
            interleavedKV: true)
        let referenceOutput = lagunaSlidingFusedAttention(
            rawQueries: rawQueries,
            rawKeys: rawKeys,
            rawValues: rawValues,
            queryWeight: queryWeight,
            keyWeight: keyWeight,
            angles: angles,
            cacheKeys: referenceRing.keys,
            cacheValues: referenceRing.values,
            cacheInterleavedKV: referenceRing.interleavedKV,
            writeIdx: referenceRing.writeIdx,
            scale: scale,
            interleavedKV: false)
        eval(candidateOutput, referenceOutput)

        #expect(lagunaBitwiseEqual(candidateOutput, referenceOutput))
        #expect(lagunaBitwiseEqual(candidateRing.keys, referenceRing.keys))
        #expect(lagunaBitwiseEqual(candidateRing.values, referenceRing.values))
        lagunaExpectInterleavedKVMatchesCanonical(
            candidateRing.interleavedKV,
            keys: candidateRing.keys,
            values: candidateRing.values)
        lagunaExpectInterleavedKVMatchesCanonical(
            referenceRing.interleavedKV,
            keys: referenceRing.keys,
            values: referenceRing.values)

        candidate.fusedRingAdvance()
        reference.fusedRingAdvance()
        let expectedOffset = window + step + 1
        let wrappedIdx = (step + 1) % window
        let expectedIdx = wrappedIdx == 0 ? window : wrappedIdx
        #expect(candidate.metaState[3] == String(expectedOffset))
        #expect(candidate.metaState[4] == String(expectedIdx))
        #expect(candidate.metaState == reference.metaState)
    }

    #expect(observedWriteIndices.isSuperset(of: [0, 1, 31, 32, 511]))

    let replacementSeed = lagunaSlidingKVSeed(length: window, phase: 1.75)
    candidate.state = [replacementSeed.keys, replacementSeed.values]
    candidate.metaState = ["0", String(window), "256", String(window), String(window)]
    let stateReplaced = try #require(candidate.fusedRingPrepare())
    lagunaExpectInterleavedKVMatchesCanonical(
        stateReplaced.interleavedKV,
        keys: stateReplaced.keys,
        values: stateReplaced.values)

    candidate.metaState = candidate.metaState
    let metaReplaced = try #require(candidate.fusedRingPrepare())
    lagunaExpectInterleavedKVMatchesCanonical(
        metaReplaced.interleavedKV,
        keys: metaReplaced.keys,
        values: metaReplaced.values)

    let copied = try #require(candidate.copy() as? RotatingKVCache)
    let copiedRing = try #require(copied.fusedRingPrepare())
    lagunaExpectInterleavedKVMatchesCanonical(
        copiedRing.interleavedKV,
        keys: copiedRing.keys,
        values: copiedRing.values)

    #expect(candidate.trim(1) == 1)
    #expect(candidate.fusedRingPrepare() == nil)

    let ordinarySeed = lagunaSlidingKVSeed(length: window, phase: 0.25)
    let ordinary = lagunaSlidingRing(keys: ordinarySeed.keys, values: ordinarySeed.values)
    _ = try #require(ordinary.fusedRingPrepare())
    let one = lagunaSlidingKVSeed(length: 1, phase: 2.5)
    _ = ordinary.update(keys: one.keys, values: one.values)
    let ordinaryRing = try #require(ordinary.fusedRingPrepare())
    #expect(ordinaryRing.writeIdx == 1)
    lagunaExpectInterleavedKVMatchesCanonical(
        ordinaryRing.interleavedKV,
        keys: ordinaryRing.keys,
        values: ordinaryRing.values)

    let reorderedSeed = lagunaSlidingKVSeed(length: window, phase: 0.5)
    let reordered = lagunaSlidingRing(keys: reorderedSeed.keys, values: reorderedSeed.values)
    _ = try #require(reordered.fusedRingPrepare())
    let two = lagunaSlidingKVSeed(length: 2, phase: 3.0)
    let reorderedState = reordered.update(keys: two.keys, values: two.values)
    #expect(reorderedState.0.dim(2) == window + 1)
    #expect(reordered.fusedRingPrepare() == nil)

    let shortSeed = lagunaSlidingKVSeed(length: window - 1, phase: 0.0)
    let short = lagunaSlidingRing(keys: shortSeed.keys, values: shortSeed.values)
    #expect(short.fusedRingPrepare() == nil)

    let floatSeed = lagunaSlidingKVSeed(length: window, phase: 0.0)
    let floatRing = lagunaSlidingRing(
        keys: floatSeed.keys.asType(.float32),
        values: floatSeed.values.asType(.float32))
    #expect(floatRing.fusedRingPrepare() == nil)

    let keptSeed = lagunaSlidingKVSeed(length: window, phase: 0.0)
    let kept = lagunaSlidingRing(keys: keptSeed.keys, values: keptSeed.values, keep: 1)
    #expect(kept.fusedRingPrepare() == nil)

    let full = KVCacheSimple()
    let fullSeed = lagunaSlidingKVSeed(length: window, phase: 0.75)
    _ = full.update(keys: fullSeed.keys, values: fullSeed.values)
    let fullNext = lagunaSlidingKVSeed(length: 1, phase: 4.0)
    let fullState = full.update(keys: fullNext.keys, values: fullNext.values)
    #expect(full.offset == window + 1)
    #expect(fullState.0.dim(2) == window + 1)
    #expect(fullState.1.dim(2) == window + 1)
}

private func lagunaSlidingKVSeed(
    length: Int, phase: Float
) -> (keys: MLXArray, values: MLXArray) {
    let size = LagunaConstants.numKeyValueHeads * length * LagunaConstants.headDim
    let axis = MLXArray(0..<size).asType(.float32)
    let shape = [
        1, LagunaConstants.numKeyValueHeads, length, LagunaConstants.headDim,
    ]
    return (
        (sin(axis * 0.003 + phase) * 0.5).asType(.bfloat16).reshaped(shape),
        (cos(axis * 0.005 + phase * 0.75) * 0.5).asType(.bfloat16).reshaped(shape)
    )
}

private func lagunaSlidingRing(
    keys: MLXArray, values: MLXArray, keep: Int = 0
) -> RotatingKVCache {
    let cache = RotatingKVCache(maxSize: LagunaConstants.slidingWindow, keep: keep)
    _ = cache.update(keys: keys, values: values)
    return cache
}

private func lagunaExpectInterleavedKVMatchesCanonical(
    _ interleavedKV: MLXArray, keys: MLXArray, values: MLXArray
) {
    let canonicalShape = [
        interleavedKV.dim(0), interleavedKV.dim(1), interleavedKV.dim(2),
        interleavedKV.dim(3) * 4,
    ]
    let sideKeys = interleavedKV[.ellipsis, 0..<4].reshaped(canonicalShape)
    let sideValues = interleavedKV[.ellipsis, 4..<8].reshaped(canonicalShape)
    #expect(lagunaBitwiseEqual(sideKeys, keys))
    #expect(lagunaBitwiseEqual(sideValues, values))
}

private func lagunaBitwiseEqual(_ lhs: MLXArray, _ rhs: MLXArray) -> Bool {
    guard lhs.shape == rhs.shape, lhs.dtype == rhs.dtype else { return false }
    return arrayEqual(
        lhs.view(dtype: .uint16), rhs.view(dtype: .uint16)
    ).item(Bool.self)
}

@Test
func lagunaExpertAlignedGatherRequiresNAXHardwareAndOS() {
    #expect(!lagunaNAXAvailable(architecture: "agxg16s", osSupportsNAX: true))
    #expect(lagunaNAXAvailable(architecture: "agxg17s", osSupportsNAX: true))
    #expect(!lagunaNAXAvailable(architecture: "agxg17p", osSupportsNAX: true))
    #expect(lagunaNAXAvailable(architecture: "agxg18p", osSupportsNAX: true))
    #expect(!lagunaNAXAvailable(architecture: "agxg17s", osSupportsNAX: false))
    #expect(!lagunaNAXAvailable(architecture: "unknown", osSupportsNAX: true))
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
