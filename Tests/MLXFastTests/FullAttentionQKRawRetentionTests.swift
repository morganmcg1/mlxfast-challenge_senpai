import Foundation
import MLX
import MLXFast
import Testing

private let qkRetentionLengths = [513, 544, 545, 576, 577, 608, 609, 640]
private let qkRetentionCapacity = 768
private let qkRetentionSamples = 400

@Test
func fullAttentionQKRawRetentionMatchesControlAndMeasuresIsolatedKernelWhenEnabled() throws {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_QK_RETENTION_TESTS"] == "1" else {
        return
    }

    let (control, candidate) = try qkRetentionKernels()
    if ProcessInfo.processInfo.environment["MLXFAST_QK_RETENTION_MODE"] == "timing" {
        try measureQKRetention(control: control, candidate: candidate)
    } else {
        verifyQKRetention(control: control, candidate: candidate)
    }
}

private struct QKRetentionFixture {
    let rawQueries: MLXArray
    let rawKeys: MLXArray
    let rawValues: MLXArray
    let queryWeight: MLXArray
    let keyWeight: MLXArray
    let angles: MLXArray
    let scale: MLXArray
    let controlKeys: MLXArray
    let controlValues: MLXArray
    let candidateKeys: MLXArray
    let candidateValues: MLXArray
}

private struct QKRetentionTimingCase: Codable {
    let length: Int
    let abControlNanoseconds: [UInt64]
    let abCandidateNanoseconds: [UInt64]
    let baCandidateNanoseconds: [UInt64]
    let baControlNanoseconds: [UInt64]
}

private struct QKRetentionTimingReport: Codable {
    let hardware: String
    let controlKernel: String
    let candidateKernel: String
    let capacity: Int
    let samplesPerArmPerOrder: Int
    let cases: [QKRetentionTimingCase]
}

private enum QKRetentionHarnessError: Error {
    case markerNotFound(String)
    case candidateBlockNotFound
}

private func qkRetentionKernels() throws -> (
    control: MLXFast.MLXFastKernel, candidate: MLXFast.MLXFastKernel
) {
    let testURL = URL(fileURLWithPath: #filePath)
    let repositoryURL = testURL
        .deletingLastPathComponent()
        .deletingLastPathComponent()
        .deletingLastPathComponent()
    let runtimeURL = repositoryURL
        .appendingPathComponent("Sources")
        .appendingPathComponent("MLXFastModel")
        .appendingPathComponent("LagunaRuntimeModel.swift")
    let runtime = try String(contentsOf: runtimeURL, encoding: .utf8)
    let kernelMarker = "private let lagunaFullFusedAttentionKernel = MLXFast.metalKernel("
    guard let kernelStart = runtime.range(of: kernelMarker) else {
        throw QKRetentionHarnessError.markerNotFound(kernelMarker)
    }
    let tail = String(runtime[kernelStart.lowerBound...])
    let candidateSource = stripSwiftMultilineIndent(try extractSwiftMultilineString(
        from: tail,
        startMarker: "    source: \"\"\"\n",
        endMarker: "        \"\"\",\n    header: \"\"\"\n"
    ))
    var header = stripSwiftMultilineIndent(try extractSwiftMultilineString(
        from: tail,
        startMarker: "    header: \"\"\"\n",
        endMarker: "        \"\"\",\n    ensureRowContiguous: true"
    ))
    header = header.replacingOccurrences(of: "\\\\", with: "\\")

    let retainedBlock = """
        uint base = lane * 4;
        thread float raw[4];
        thread bfloat normalized[4];
        float sum = 0.0f;
        for (uint i = 0; i < 4; ++i) {
            raw[i] = float(input[base + i]);
            sum += raw[i] * raw[i];
        }
        sum = simd_sum(sum);
        float inverse_rms = metal::precise::rsqrt(sum / 128.0f + 1.0e-6f);
        for (uint i = 0; i < 4; ++i) {
            normalized[i] =
                weight[base + i] * bfloat(raw[i] * inverse_rms);
        }
    """
    let baselineBlock = """
        uint base = lane * 4;
        thread bfloat normalized[4];
        float sum = 0.0f;
        for (uint i = 0; i < 4; ++i) {
            float value = float(input[base + i]);
            sum += value * value;
        }
        sum = simd_sum(sum);
        float inverse_rms = metal::precise::rsqrt(sum / 128.0f + 1.0e-6f);
        for (uint i = 0; i < 4; ++i) {
            normalized[i] =
                weight[base + i] *
                bfloat(float(input[base + i]) * inverse_rms);
        }
    """
    guard candidateSource.components(separatedBy: retainedBlock).count == 2 else {
        throw QKRetentionHarnessError.candidateBlockNotFound
    }
    let controlSource = candidateSource.replacingOccurrences(
        of: retainedBlock, with: baselineBlock)
    let inputNames = [
        "raw_queries", "raw_keys", "raw_values",
        "query_weight", "key_weight", "angles",
        "k_cache", "v_cache", "params", "scale_arr",
    ]
    let control = MLXFast.metalKernel(
        name: "laguna_full_fused_attn_qk_retention_control_v1",
        inputNames: inputNames,
        outputNames: ["attended"],
        source: controlSource,
        header: header,
        ensureRowContiguous: true
    )
    let candidate = MLXFast.metalKernel(
        name: "laguna_full_fused_attn_qk_retention_candidate_v2",
        inputNames: inputNames,
        outputNames: ["attended"],
        source: candidateSource,
        header: header,
        ensureRowContiguous: true
    )
    return (control, candidate)
}

private func extractSwiftMultilineString(
    from text: String, startMarker: String, endMarker: String
) throws -> String {
    guard let start = text.range(of: startMarker) else {
        throw QKRetentionHarnessError.markerNotFound(startMarker)
    }
    guard let end = text.range(
        of: endMarker, range: start.upperBound..<text.endIndex)
    else {
        throw QKRetentionHarnessError.markerNotFound(endMarker)
    }
    return String(text[start.upperBound..<end.lowerBound])
}

private func stripSwiftMultilineIndent(_ text: String) -> String {
    text.split(separator: "\n", omittingEmptySubsequences: false)
        .map { line in line.isEmpty ? "" : String(line.dropFirst(8)) }
        .joined(separator: "\n")
}

private func qkRetentionFixture(length: Int) -> QKRetentionFixture {
    let headDimension = 128
    let queryHeads = 48
    let keyValueHeads = 8
    let rawQueries = patternedBF16(
        shape: [1, 1, queryHeads * headDimension], phase: 0.17, magnitude: 0.75)
    let rawKeys = patternedBF16(
        shape: [1, 1, keyValueHeads * headDimension], phase: 0.31, magnitude: 0.625)
    let rawValues = patternedBF16(
        shape: [1, 1, keyValueHeads * headDimension], phase: 0.47, magnitude: 0.5)
    let queryWeight = patternedBF16(
        shape: [headDimension], phase: 0.11, magnitude: 0.125, offset: 1)
    let keyWeight = patternedBF16(
        shape: [headDimension], phase: 0.23, magnitude: 0.125, offset: 1)
    var angleValues = [Float]()
    angleValues.reserveCapacity(64)
    for pair in 0..<32 {
        angleValues.append(cos(Float(pair + length) * 0.0017))
    }
    for pair in 0..<32 {
        angleValues.append(sin(Float(pair + length) * 0.0017))
    }
    let angles = MLXArray(angleValues, [1, 1, 1, 64])
    let scale = MLXArray([pow(Float(headDimension), -0.5)])
    let cacheShape = [1, keyValueHeads, qkRetentionCapacity, headDimension]
    let baseKeys = patternedBF16(
        shape: cacheShape, phase: Float(length) * 0.003, magnitude: 0.25)
    let baseValues = patternedBF16(
        shape: cacheShape, phase: Float(length) * 0.005, magnitude: 0.375)
    let zero = MLXArray(Float(0)).asType(.bfloat16)
    let one = MLXArray(Float(1)).asType(.bfloat16)
    let controlKeys = baseKeys + zero
    let candidateKeys = baseKeys * one
    let controlValues = baseValues + zero
    let candidateValues = baseValues * one
    eval(
        rawQueries, rawKeys, rawValues, queryWeight, keyWeight, angles, scale,
        controlKeys, candidateKeys, controlValues, candidateValues)
    return QKRetentionFixture(
        rawQueries: rawQueries,
        rawKeys: rawKeys,
        rawValues: rawValues,
        queryWeight: queryWeight,
        keyWeight: keyWeight,
        angles: angles,
        scale: scale,
        controlKeys: controlKeys,
        controlValues: controlValues,
        candidateKeys: candidateKeys,
        candidateValues: candidateValues
    )
}

private func patternedBF16(
    shape: [Int], phase: Float, magnitude: Float, offset: Float = 0
) -> MLXArray {
    let count = shape.reduce(1, *)
    let axis = MLXArray(0..<count).asType(.float32)
    return (
        sin(axis * Float(0.013) + phase) * magnitude
            + cos(axis * Float(0.007) - phase) * (magnitude * Float(0.25))
            + offset
    ).asType(.bfloat16).reshaped(shape)
}

private func runQKRetentionKernel(
    _ kernel: MLXFast.MLXFastKernel,
    fixture: QKRetentionFixture,
    keys: MLXArray,
    values: MLXArray,
    length: Int,
    verbose: Bool = false
) -> MLXArray {
    let params = MLXArray([
        UInt32(length - 1), UInt32(length), UInt32(qkRetentionCapacity),
    ])
    return kernel(
        [
            fixture.rawQueries, fixture.rawKeys, fixture.rawValues,
            fixture.queryWeight, fixture.keyWeight, fixture.angles,
            keys, values, params, fixture.scale,
        ],
        grid: (24 * 1024, 1, 1),
        threadGroup: (1024, 1, 1),
        outputShapes: [[1, 48, 1, 128]],
        outputDTypes: [.bfloat16],
        verbose: verbose
    )[0]
}

private func verifyQKRetention(
    control: MLXFast.MLXFastKernel,
    candidate: MLXFast.MLXFastKernel
) {
    for length in qkRetentionLengths {
        let fixture = qkRetentionFixture(length: length)
        for _ in 0..<4 {
            eval(runQKRetentionKernel(
                control, fixture: fixture, keys: fixture.controlKeys,
                values: fixture.controlValues, length: length))
            eval(runQKRetentionKernel(
                candidate, fixture: fixture, keys: fixture.candidateKeys,
                values: fixture.candidateValues, length: length))
        }
        let controlOutput = runQKRetentionKernel(
            control, fixture: fixture, keys: fixture.controlKeys,
            values: fixture.controlValues, length: length, verbose: length == 513)
        let candidateOutput = runQKRetentionKernel(
            candidate, fixture: fixture, keys: fixture.candidateKeys,
            values: fixture.candidateValues, length: length, verbose: length == 513)
        eval(
            controlOutput, candidateOutput,
            fixture.controlKeys, fixture.candidateKeys,
            fixture.controlValues, fixture.candidateValues)

        let outputEqual = bf16Bits(controlOutput) == bf16Bits(candidateOutput)
        let keysEqual = bf16Bits(fixture.controlKeys) == bf16Bits(fixture.candidateKeys)
        let valuesEqual = bf16Bits(fixture.controlValues) == bf16Bits(fixture.candidateValues)
        print(
            "qk_retention_correctness length=\(length) output_equal=\(outputEqual) "
                + "entire_k_cache_equal=\(keysEqual) entire_v_cache_equal=\(valuesEqual)"
        )
        #expect(outputEqual, "raw BF16 output mismatch at length \(length)")
        #expect(keysEqual, "entire K cache mismatch at length \(length)")
        #expect(valuesEqual, "entire V cache mismatch at length \(length)")
    }

    let fixture = qkRetentionFixture(length: 513)
    var corruption = [Float](repeating: 0, count: 8 * 128)
    corruption[0] = 0.5
    let corruptedRawKeys = (
        fixture.rawKeys.asType(.float32) + MLXArray(corruption, [1, 1, 8 * 128])
    ).asType(.bfloat16)
    let corruptFixture = QKRetentionFixture(
        rawQueries: fixture.rawQueries,
        rawKeys: corruptedRawKeys,
        rawValues: fixture.rawValues,
        queryWeight: fixture.queryWeight,
        keyWeight: fixture.keyWeight,
        angles: fixture.angles,
        scale: fixture.scale,
        controlKeys: fixture.controlKeys,
        controlValues: fixture.controlValues,
        candidateKeys: fixture.controlKeys + MLXArray(Float(0)).asType(.bfloat16),
        candidateValues: fixture.controlValues + MLXArray(Float(0)).asType(.bfloat16)
    )
    eval(corruptFixture.candidateKeys, corruptFixture.candidateValues)
    let reference = runQKRetentionKernel(
        candidate, fixture: fixture, keys: fixture.candidateKeys,
        values: fixture.candidateValues, length: 513)
    let corrupted = runQKRetentionKernel(
        candidate, fixture: corruptFixture, keys: corruptFixture.candidateKeys,
        values: corruptFixture.candidateValues, length: 513)
    eval(reference, corrupted, fixture.candidateKeys, corruptFixture.candidateKeys)
    let positiveControlDetected =
        bf16Bits(reference) != bf16Bits(corrupted)
        || bf16Bits(fixture.candidateKeys) != bf16Bits(corruptFixture.candidateKeys)
    print("qk_retention_positive_control_detected=\(positiveControlDetected)")
    #expect(positiveControlDetected, "deliberate raw-key corruption was not detected")
}

private func measureQKRetention(
    control: MLXFast.MLXFastKernel,
    candidate: MLXFast.MLXFastKernel
) throws {
    var cases = [QKRetentionTimingCase]()
    for length in qkRetentionLengths {
        let fixture = qkRetentionFixture(length: length)
        for _ in 0..<20 {
            eval(runQKRetentionKernel(
                control, fixture: fixture, keys: fixture.controlKeys,
                values: fixture.controlValues, length: length))
            eval(runQKRetentionKernel(
                candidate, fixture: fixture, keys: fixture.candidateKeys,
                values: fixture.candidateValues, length: length))
        }

        var abControl = [UInt64]()
        var abCandidate = [UInt64]()
        var baCandidate = [UInt64]()
        var baControl = [UInt64]()
        abControl.reserveCapacity(qkRetentionSamples)
        abCandidate.reserveCapacity(qkRetentionSamples)
        baCandidate.reserveCapacity(qkRetentionSamples)
        baControl.reserveCapacity(qkRetentionSamples)
        for _ in 0..<qkRetentionSamples {
            abControl.append(measureNanoseconds {
                runQKRetentionKernel(
                    control, fixture: fixture, keys: fixture.controlKeys,
                    values: fixture.controlValues, length: length)
            })
            abCandidate.append(measureNanoseconds {
                runQKRetentionKernel(
                    candidate, fixture: fixture, keys: fixture.candidateKeys,
                    values: fixture.candidateValues, length: length)
            })
        }
        for _ in 0..<qkRetentionSamples {
            baCandidate.append(measureNanoseconds {
                runQKRetentionKernel(
                    candidate, fixture: fixture, keys: fixture.candidateKeys,
                    values: fixture.candidateValues, length: length)
            })
            baControl.append(measureNanoseconds {
                runQKRetentionKernel(
                    control, fixture: fixture, keys: fixture.controlKeys,
                    values: fixture.controlValues, length: length)
            })
        }
        let abSpeedup = median(abControl) / median(abCandidate)
        let baSpeedup = median(baControl) / median(baCandidate)
        print(
            "qk_retention_timing length=\(length) samples=\(qkRetentionSamples) "
                + "ab_control_median_ns=\(median(abControl)) "
                + "ab_candidate_median_ns=\(median(abCandidate)) "
                + "ab_speedup=\(abSpeedup) "
                + "ba_control_median_ns=\(median(baControl)) "
                + "ba_candidate_median_ns=\(median(baCandidate)) "
                + "ba_speedup=\(baSpeedup)"
        )
        cases.append(QKRetentionTimingCase(
            length: length,
            abControlNanoseconds: abControl,
            abCandidateNanoseconds: abCandidate,
            baCandidateNanoseconds: baCandidate,
            baControlNanoseconds: baControl
        ))
    }
    let report = QKRetentionTimingReport(
        hardware: ProcessInfo.processInfo.environment["MLXFAST_QK_RETENTION_HARDWARE"]
            ?? ProcessInfo.processInfo.hostName,
        controlKernel: "laguna_full_fused_attn_qk_retention_control_v1",
        candidateKernel: "laguna_full_fused_attn_qk_retention_candidate_v2",
        capacity: qkRetentionCapacity,
        samplesPerArmPerOrder: qkRetentionSamples,
        cases: cases
    )
    let outputPath = ProcessInfo.processInfo.environment["MLXFAST_QK_RETENTION_OUTPUT"]
        ?? "/tmp/mlxfast-qk-retention-isolated-results.json"
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    try encoder.encode(report).write(to: URL(fileURLWithPath: outputPath))
    print("qk_retention_timing_report=\(outputPath)")
}

private func measureNanoseconds(_ operation: () -> MLXArray) -> UInt64 {
    let start = DispatchTime.now().uptimeNanoseconds
    eval(operation())
    return DispatchTime.now().uptimeNanoseconds - start
}

private func median(_ values: [UInt64]) -> Double {
    let sorted = values.sorted()
    let middle = sorted.count / 2
    if sorted.count.isMultiple(of: 2) {
        return (Double(sorted[middle - 1]) + Double(sorted[middle])) / 2
    }
    return Double(sorted[middle])
}

private func bf16Bits(_ array: MLXArray) -> [UInt16] {
    precondition(array.dtype == .bfloat16)
    return array.view(dtype: .uint16).asArray(UInt16.self)
}
