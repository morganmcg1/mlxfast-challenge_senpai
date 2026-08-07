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
func lagunaDecodeRouterHierarchicalOrdinalMatchesAcceptedWhenRuntimeTestsAreEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
        return
    }

    var fixtures: [(name: String, logits: [Float], bias: [Float])] = []
    let zeros = Array(repeating: Float(0), count: 256)
    fixtures.append(("all ties", zeros, zeros))
    fixtures.append((
        "signed zeros",
        (0..<256).map { $0.isMultiple(of: 2) ? Float(0) : -Float(0) },
        zeros
    ))

    var crossBlockLogits = Array(repeating: Float(-20), count: 256)
    var crossBlockBias = Array(repeating: Float(-20), count: 256)
    for index in [0, 31, 32, 63, 64, 95, 128, 224, 255] {
        crossBlockLogits[index] = 0
        crossBlockBias[index] = 0
    }
    fixtures.append(("nine-way cross-block tie", crossBlockLogits, crossBlockBias))

    var specialLogits = Array(repeating: Float(-8), count: 256)
    var specialBias = zeros
    for (offset, index) in [0, 31, 32, 63, 64, 95, 128, 159, 224, 255].enumerated() {
        if offset.isMultiple(of: 2) {
            specialLogits[index] = .infinity
        } else {
            specialLogits[index] = -.infinity
            specialBias[index] = 1
        }
    }
    specialLogits[17] = .nan
    specialLogits[99] = Float.greatestFiniteMagnitude
    specialLogits[100] = -Float.greatestFiniteMagnitude
    specialLogits[101] = Float.leastNormalMagnitude
    specialLogits[102] = -Float.leastNormalMagnitude
    fixtures.append(("extremes infinities and NaNs", specialLogits, specialBias))
    fixtures.append(("all NaNs", Array(repeating: Float.nan, count: 256), zeros))

    var state: UInt64 = 0xD1B54A32D192ED03
    func randomSigned() -> Float {
        state = state &* 6_364_136_223_846_793_005 &+ 1_442_695_040_888_963_407
        let bits = UInt32(truncatingIfNeeded: state >> 32)
        return Float(Int32(bitPattern: bits)) / Float(Int32.max)
    }
    for sample in 0..<12 {
        let logits = (0..<256).map { _ in randomSigned() * 16 }
        let bias = (0..<256).map { _ in randomSigned() * 2 }
        fixtures.append(("random-\(sample)", logits, bias))
    }

    for fixture in fixtures {
        for useBF16 in [false, true] {
            let logits32 = MLXArray(fixture.logits)
            let logits = useBF16 ? logits32.asType(.bfloat16) : logits32
            let bias = MLXArray(fixture.bias)
            let dtypeName = useBF16 ? "bf16" : "fp32"
            for normalizing in [false, true] {
                let accepted = lagunaDecodeRouterTop8AcceptedForTesting(
                    logits: logits,
                    correctionBias: bias,
                    normalizing: normalizing
                )
                let hierarchical = lagunaDecodeRouterTop8OrdinalScoreTableForTesting(
                    logits: logits,
                    correctionBias: bias,
                    normalizing: normalizing
                )
                eval(accepted.0, accepted.1, hierarchical.0, hierarchical.1)

                let acceptedIndices = accepted.0.asArray(UInt32.self)
                let hierarchicalIndices = hierarchical.0.asArray(UInt32.self)
                let acceptedScoreBits = accepted.1.asArray(Float.self).map { $0.bitPattern }
                let hierarchicalScoreBits = hierarchical.1.asArray(Float.self).map { $0.bitPattern }
                let caseName = "\(fixture.name), \(dtypeName), normalizing=\(normalizing)"
                #expect(acceptedIndices == hierarchicalIndices, "index mismatch: \(caseName)")
                #expect(acceptedScoreBits == hierarchicalScoreBits, "score mismatch: \(caseName)")
            }
        }
    }
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
