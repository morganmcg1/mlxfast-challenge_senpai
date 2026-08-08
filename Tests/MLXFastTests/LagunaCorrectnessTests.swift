import Foundation
import CryptoKit
import MLX
import MLXFast
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


@Test
func lagunaRouterSigmoidBF16LookupEvidenceWhenEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_ROUTER_SIGMOID_LUT_EVIDENCE"] == "1" else {
        return
    }

    let table = lagunaRouterSigmoidBF16TableForTesting()
    let oracleKernel = MLXFast.metalKernel(
        name: "laguna_router_sigmoid_bf16_lut_oracle_v1",
        inputNames: ["sigmoid_lut"],
        outputNames: ["direct_scores", "lookup_scores"],
        source: """
            uint bits = thread_position_in_grid.x;
            float x = float(as_type<bfloat>(ushort(bits)));
            float y = 1.0f / (1.0f + metal::exp(metal::abs(x)));
            direct_scores[bits] = x < 0.0f ? y : 1.0f - y;
            lookup_scores[bits] = sigmoid_lut[bits];
            """,
        ensureRowContiguous: true
    )
    let oracle = oracleKernel(
        [table],
        grid: (65_536, 1, 1),
        threadGroup: (256, 1, 1),
        outputShapes: [[65_536], [65_536]],
        outputDTypes: [.float32, .float32]
    )
    eval(table, oracle[0], oracle[1])

    let directBits = oracle[0].asArray(Float.self).map { $0.bitPattern }
    let lookupBits = oracle[1].asArray(Float.self).map { $0.bitPattern }
    let mismatches = mismatchIndices(directBits, lookupBits)
    let tableBytes = table.size * MemoryLayout<Float>.stride
    #expect(table.shape == [65_536])
    #expect(table.dtype == .float32)
    #expect(tableBytes == 262_144)
    #expect(mismatches.isEmpty)

    var corruptedBits = lookupBits
    let corruptionIndex = 0x3f80
    corruptedBits[corruptionIndex] ^= 1
    let detectedCorruption = mismatchIndices(lookupBits, corruptedBits)
    #expect(detectedCorruption == [corruptionIndex])
    print(
        "ROUTER_LUT_EXHAUSTIVE patterns=65536 mismatches=\(mismatches.count) "
            + "corruption_index=0x3f80 bytes=\(tableBytes)"
    )

    typealias Inputs = (logits: [Float], bias: [Float])
    let zeros = Array(repeating: Float(0), count: 256)
    var corpus = [Inputs]()
    corpus.append((Array(repeating: 1, count: 256), zeros))
    corpus.append((
        (0..<256).map { (Float($0) - 128) * 0.0625 },
        (0..<256).map { Float(($0 % 7) - 3) * 0.125 }
    ))
    corpus.append((
        (0..<256).map {
            $0.isMultiple(of: 2)
                ? Float.greatestFiniteMagnitude / 4 : -Float.greatestFiniteMagnitude / 4
        },
        zeros
    ))
    corpus.append((
        (0..<256).map {
            $0.isMultiple(of: 2) ? Float(bitPattern: 0) : Float(bitPattern: 0x8000_0000)
        },
        zeros
    ))

    var special = (0..<256).map { Float($0 - 128) }
    let specialBits: [UInt32] = [
        0x7f80_0000, 0xff80_0000, 0x7fc0_0001, 0x7fa0_0001,
        0xffc0_0001, 0xffa0_0001, 0x0000_0000, 0x8000_0000,
    ]
    for (index, bits) in specialBits.enumerated() {
        special[index] = Float(bitPattern: bits)
    }
    corpus.append((special, zeros))

    var state: UInt64 = 0x6a09_e667_f3bc_c909
    func shuffledOrdinals() -> [Float] {
        var values = Array(0..<256)
        for upper in stride(from: 255, through: 1, by: -1) {
            state = state &* 6_364_136_223_846_793_005 &+ 1_442_695_040_888_963_407
            let lower = Int(state % UInt64(upper + 1))
            values.swapAt(upper, lower)
        }
        return values.map { (Float($0) - 128) * 0.0625 }
    }
    for sample in 0..<64 {
        corpus.append((
            shuffledOrdinals(),
            (0..<256).map {
                Float((($0 &* 17 &+ sample &* 13) % 19) - 9) * 0.03125
            }
        ))
    }

    var comparisons = 0
    for (caseIndex, inputs) in corpus.enumerated() {
        let logits = MLXArray(inputs.logits, [1, 1, 256]).asType(.bfloat16)
        let bias = MLXArray(inputs.bias, [1, 1, 256])
        for normalizing in [false, true] {
            let direct = lagunaDecodeRouterTop8OrdinalForTesting(
                logits: logits,
                correctionBias: bias,
                normalizing: normalizing
            )
            let lookup = lagunaDecodeRouterTop8OrdinalScoreTableForTesting(
                logits: logits,
                correctionBias: bias,
                normalizing: normalizing
            )
            eval([direct.0, direct.1, lookup.0, lookup.1])
            let directIndices = direct.0.asArray(UInt32.self)
            let lookupIndices = lookup.0.asArray(UInt32.self)
            let directScores = direct.1.asArray(Float.self).map { $0.bitPattern }
            let lookupScores = lookup.1.asArray(Float.self).map { $0.bitPattern }
            #expect(
                directIndices == lookupIndices,
                Comment(rawValue: "case \(caseIndex) normalized=\(normalizing) indices differ")
            )
            #expect(
                directScores == lookupScores,
                Comment(rawValue: "case \(caseIndex) normalized=\(normalizing) scores differ")
            )
            comparisons += 1
        }
    }
    print("ROUTER_LUT_ADVERSARIAL cases=\(corpus.count) comparisons=\(comparisons) exact=true")
}

@Test
func lagunaRouterSigmoidBF16LookupBenchmarkWhenEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_ROUTER_SIGMOID_LUT_BENCHMARK"] == "1" else {
        return
    }

    var state: UInt64 = 0xbb67_ae85_84ca_a73b
    func shuffledOrdinals() -> [Float] {
        var values = Array(0..<256)
        for upper in stride(from: 255, through: 1, by: -1) {
            state = state &* 2_862_933_555_777_941_757 &+ 3_037_000_493
            let lower = Int(state % UInt64(upper + 1))
            values.swapAt(upper, lower)
        }
        return values.map(Float.init)
    }
    let timingInputs: [(logits: MLXArray, bias: MLXArray)] = (0..<16).map { sample in
        let logits = shuffledOrdinals().map {
            ($0 - 128) * 0.0625 - Float(sample) * 0.0001
        }
        let bias = (0..<256).map {
            Float((($0 &* 29 &+ sample &* 7) % 23) - 11) * 0.015625
        }
        return (
            MLXArray(logits, [1, 1, 256]).asType(.bfloat16),
            MLXArray(bias, [1, 1, 256])
        )
    }

    func route(candidate: Bool, input: (logits: MLXArray, bias: MLXArray))
        -> (MLXArray, MLXArray)
    {
        if candidate {
            return lagunaDecodeRouterTop8OrdinalScoreTableForTesting(
                logits: input.logits,
                correctionBias: input.bias,
                normalizing: true
            )
        }
        return lagunaDecodeRouterTop8OrdinalForTesting(
            logits: input.logits,
            correctionBias: input.bias,
            normalizing: true
        )
    }

    func evaluateQueued(candidate: Bool, repetitions: Int) -> UInt64 {
        var outputs = [MLXArray]()
        outputs.reserveCapacity(repetitions * 2)
        for repetition in 0..<repetitions {
            let routed = route(
                candidate: candidate,
                input: timingInputs[repetition % timingInputs.count]
            )
            outputs.append(routed.0)
            outputs.append(routed.1)
        }
        let start = DispatchTime.now().uptimeNanoseconds
        eval(outputs)
        return DispatchTime.now().uptimeNanoseconds - start
    }

    func evaluateSingle(candidate: Bool, sample: Int) -> UInt64 {
        let routed = route(
            candidate: candidate,
            input: timingInputs[sample % timingInputs.count]
        )
        let start = DispatchTime.now().uptimeNanoseconds
        eval(routed.0, routed.1)
        return DispatchTime.now().uptimeNanoseconds - start
    }

    func median(_ values: [Double]) -> Double {
        values.sorted()[values.count / 2]
    }

    _ = evaluateQueued(candidate: false, repetitions: 16)
    _ = evaluateQueued(candidate: true, repetitions: 16)

    let queuedPairs = 31
    let queuedRepetitions = 1_024
    var queuedAB = [Double]()
    var queuedBA = [Double]()
    for _ in 0..<queuedPairs {
        let direct = evaluateQueued(candidate: false, repetitions: queuedRepetitions)
        let lookup = evaluateQueued(candidate: true, repetitions: queuedRepetitions)
        queuedAB.append(Double(direct) / Double(lookup))
    }
    for _ in 0..<queuedPairs {
        let lookup = evaluateQueued(candidate: true, repetitions: queuedRepetitions)
        let direct = evaluateQueued(candidate: false, repetitions: queuedRepetitions)
        queuedBA.append(Double(direct) / Double(lookup))
    }

    let singlePairs = 129
    var singleAB = [Double]()
    var singleBA = [Double]()
    for sample in 0..<singlePairs {
        let direct = evaluateSingle(candidate: false, sample: sample)
        let lookup = evaluateSingle(candidate: true, sample: sample)
        singleAB.append(Double(direct) / Double(lookup))
    }
    for sample in 0..<singlePairs {
        let lookup = evaluateSingle(candidate: true, sample: sample)
        let direct = evaluateSingle(candidate: false, sample: sample)
        singleBA.append(Double(direct) / Double(lookup))
    }

    print(
        "ROUTER_LUT_QUEUED pairs=\(queuedPairs) repetitions=\(queuedRepetitions) "
            + "ab_median=\(String(format: "%.9f", median(queuedAB))) "
            + "ba_median=\(String(format: "%.9f", median(queuedBA)))"
    )
    print(
        "ROUTER_LUT_SINGLE pairs=\(singlePairs) "
            + "ab_median=\(String(format: "%.9f", median(singleAB))) "
            + "ba_median=\(String(format: "%.9f", median(singleBA)))"
    )
}

private func mismatchIndices(_ lhs: [UInt32], _ rhs: [UInt32]) -> [Int] {
    precondition(lhs.count == rhs.count)
    var mismatches = [Int]()
    for index in lhs.indices where lhs[index] != rhs[index] {
        mismatches.append(index)
    }
    return mismatches
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
