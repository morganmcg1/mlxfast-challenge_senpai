import Foundation
import Dispatch
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
func lagunaPrefillRouterOrdinalFourRowMatchesCurrent() {
    let rowCounts = [1, 2, 3, 4, 5, 8, 511, 512, 513]
    for rows in rowCounts {
        let expected = rows > 1 && rows.isMultiple(of: 4) ? 4 : 1
        #expect(lagunaPrefillRouterOrdinalRowsPerThreadgroupForTesting(rows: rows) == expected)
    }

    let adversarial: [Float] = [
        0, -0.0, 1, -1, 0.5, 0.5,
        Float(bitPattern: 0x7f7f_0000), -Float(bitPattern: 0x7f7f_0000),
        Float(bitPattern: 0x0001_0000), -Float(bitPattern: 0x0001_0000),
        .infinity, -.infinity,
        Float(bitPattern: 0x7fc1_0000), Float(bitPattern: 0xffc2_0000),
        16, -16,
    ]
    let correctionBias = MLXArray(
        (0..<256).map { Float(($0 * 17) % 23 - 11) / 128 },
        [256]
    )
    var exercisedCorruptionControl = false

    for rows in rowCounts {
        let logitsValues = (0..<(rows * 256)).map { offset -> Float in
            let row = offset / 256
            let column = offset % 256
            return adversarial[(column + row * 13) % adversarial.count]
        }
        let logits = MLXArray(logitsValues, [rows, 256]).asType(.bfloat16)
        for normalizing in [false, true] {
            let reference = lagunaPrefillRouterTournamentOrdinalForTesting(
                logits: logits,
                correctionBias: correctionBias,
                rows: rows,
                normalizing: normalizing,
                useRows4: false
            )
            let candidate = lagunaPrefillRouterTournamentOrdinalForTesting(
                logits: logits,
                correctionBias: correctionBias,
                rows: rows,
                normalizing: normalizing
            )
            eval(reference.0, reference.1, candidate.0, candidate.1)

            let referenceIndices = reference.0.asArray(UInt32.self)
            let candidateIndices = candidate.0.asArray(UInt32.self)
            let referenceScores = reference.1.asArray(Float.self).map(\.bitPattern)
            let candidateScores = candidate.1.asArray(Float.self).map(\.bitPattern)
            #expect(candidateIndices == referenceIndices)
            #expect(candidateScores == referenceScores)

            if !exercisedCorruptionControl {
                var corrupted = referenceIndices
                corrupted[0] ^= 1
                #expect(corrupted != referenceIndices)
                exercisedCorruptionControl = true
            }
        }
    }
    #expect(exercisedCorruptionControl)
}

@Test
func lagunaPrefillRouterOrdinalFourRowTiming() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_PREFILL_ROUTER_TIMING"] == "1" else {
        return
    }

    let rows = 512
    let callCount = LagunaConstants.numHiddenLayers - 2
    let controlThreadgroups = callCount * rows
    let candidateThreadgroups = callCount * rows / 4
    let removedThreadgroups = controlThreadgroups - candidateThreadgroups
    let decodeCandidateCalls =
        lagunaPrefillRouterOrdinalRowsPerThreadgroupForTesting(rows: 1) == 4 ? callCount : 0
    #expect(callCount == 38)
    #expect(controlThreadgroups == 19_456)
    #expect(candidateThreadgroups == 4_864)
    #expect(removedThreadgroups == 14_592)
    #expect(decodeCandidateCalls == 0)
    print(
        "PREFILL_ROUTER_CENSUS {\"candidate_calls\":\(callCount),"
            + "\"control_threadgroups\":\(controlThreadgroups),"
            + "\"candidate_threadgroups\":\(candidateThreadgroups),"
            + "\"removed_threadgroups\":\(removedThreadgroups),"
            + "\"threads_per_threadgroup\":256,"
            + "\"decode_candidate_calls\":\(decodeCandidateCalls)}"
    )

    let logitsByLayer = (0..<callCount).map { layer in
        let values = (0..<(rows * 256)).map { offset -> Float in
            Float(((offset * 37 + layer * 101) % 4_093) - 2_046) / 256
        }
        return MLXArray(values, [1, rows, 256]).asType(.bfloat16)
    }
    let correctionBiasByLayer = (0..<callCount).map { layer in
        MLXArray(
            (0..<256).map { expert -> Float in
                Float(((expert * 17 + layer * 13) % 97) - 48) / 256
            },
            [256]
        )
    }
    eval(logitsByLayer + correctionBiasByLayer)

    func runSequence(useRows4: Bool) -> UInt64 {
        let start = DispatchTime.now().uptimeNanoseconds
        var outputs: [MLXArray] = []
        outputs.reserveCapacity(callCount * 2)
        for layer in 0..<callCount {
            let result = lagunaPrefillRouterTournamentOrdinalForTesting(
                logits: logitsByLayer[layer],
                correctionBias: correctionBiasByLayer[layer],
                rows: rows,
                normalizing: true,
                useRows4: useRows4
            )
            outputs.append(result.0)
            outputs.append(result.1)
        }
        eval(outputs)
        return DispatchTime.now().uptimeNanoseconds - start
    }

    for _ in 0..<4 {
        _ = runSequence(useRows4: false)
        _ = runSequence(useRows4: true)
    }

    let orders: [(name: String, arms: [Bool])] = [
        ("ABBA", [false, true, true, false]),
        ("BAAB", [true, false, false, true]),
    ]
    for order in orders {
        for cycle in 0..<12 {
            for (position, useRows4) in order.arms.enumerated() {
                let nanoseconds = runSequence(useRows4: useRows4)
                let arm = useRows4 ? "candidate" : "control"
                print(
                    "PREFILL_ROUTER_TIMING {\"order\":\"\(order.name)\","
                        + "\"cycle\":\(cycle),\"position\":\(position),"
                        + "\"arm\":\"\(arm)\",\"nanoseconds\":\(nanoseconds)}"
                )
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
