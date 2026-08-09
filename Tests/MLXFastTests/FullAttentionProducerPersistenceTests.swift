import Foundation
import MLX
import Testing

private let fullAttentionBaseRevision = "420fc6280e8adabdcaa47e2586115ce50bf88217"
private let fullAttentionKernelPath = "Sources/MLXFastModel/LagunaRuntimeModel.swift"
private let fullAttentionInputNames = [
    "raw_queries", "raw_keys", "raw_values",
    "query_weight", "key_weight", "angles",
    "k_cache", "v_cache", "params", "scale_arr",
]

private enum FullAttentionGateError: Error {
    case missingRepositoryRoot
    case commandFailed(String)
    case malformedKernelSource(String)
    case unsupportedMode(String)
}

private struct FullAttentionKernelText {
    let source: String
    let header: String
}

private struct FullAttentionFixture {
    let rawQueries: MLXArray
    let rawKeys: MLXArray
    let rawValues: MLXArray
    let queryWeight: MLXArray
    let keyWeight: MLXArray
    let angles: MLXArray
    let cacheKeys: MLXArray
    let cacheValues: MLXArray
    let writeIdx: Int
    let scale: MLXArray
}

private struct FullAttentionFixturePair {
    let baseline: FullAttentionFixture
    let candidate: FullAttentionFixture
    let expectedNeighborKeys: [Float]
    let expectedNeighborValues: [Float]
}

private func fullAttentionRepositoryRoot() throws -> String {
    guard let root = ProcessInfo.processInfo.environment["MLXFAST_REPO_ROOT"] else {
        throw FullAttentionGateError.missingRepositoryRoot
    }
    return root
}

private func fullAttentionFile(at revision: String?) throws -> String {
    let root = try fullAttentionRepositoryRoot()
    if let revision {
        let process = Process()
        let pipe = Pipe()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/git")
        process.arguments = ["-C", root, "show", "\(revision):\(fullAttentionKernelPath)"]
        process.standardOutput = pipe
        process.standardError = pipe
        try process.run()
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        guard process.terminationStatus == 0 else {
            throw FullAttentionGateError.commandFailed(
                String(data: data, encoding: .utf8) ?? "git show failed")
        }
        return String(decoding: data, as: UTF8.self)
    }
    return try String(
        contentsOfFile: "\(root)/\(fullAttentionKernelPath)",
        encoding: .utf8)
}

private func fullAttentionKernelText(at revision: String?) throws -> FullAttentionKernelText {
    let file = try fullAttentionFile(at: revision)
    let declaration = "private let lagunaFullFusedAttentionKernel"
    let sourceMarker = "    source: \"\"\"\n"
    let headerMarker = "\n\"\"\",\n    header: \"\"\"\n"
    let endMarker = "\n\"\"\",\n    ensureRowContiguous: true"
    guard
        let declarationRange = file.range(of: declaration),
        let sourceMarkerRange = file.range(
            of: sourceMarker,
            range: declarationRange.lowerBound..<file.endIndex),
        let headerMarkerRange = file.range(
            of: headerMarker,
            range: sourceMarkerRange.upperBound..<file.endIndex),
        let endMarkerRange = file.range(
            of: endMarker,
            range: headerMarkerRange.upperBound..<file.endIndex)
    else {
        throw FullAttentionGateError.malformedKernelSource(revision ?? "worktree")
    }
    return FullAttentionKernelText(
        source: String(file[sourceMarkerRange.upperBound..<headerMarkerRange.lowerBound]),
        header: String(file[headerMarkerRange.upperBound..<endMarkerRange.lowerBound]))
}

private func makeFullAttentionKernel(
    name: String,
    text: FullAttentionKernelText
) -> MLXFast.MLXFastKernel {
    MLXFast.metalKernel(
        name: name,
        inputNames: fullAttentionInputNames,
        outputNames: ["attended"],
        source: text.source,
        header: text.header,
        ensureRowContiguous: true)
}

private func patternedValues(count: Int, multiplier: Int, modulus: Int) -> [Float] {
    (0..<count).map { index in
        Float((index * multiplier) % modulus - modulus / 2) / Float(modulus)
    }
}

private func fullAttentionRows(
    _ values: [Float],
    position: Int,
    capacity: Int
) -> [Float] {
    var result: [Float] = []
    result.reserveCapacity(8 * 128)
    for kvHead in 0..<8 {
        let start = (kvHead * capacity + position) * 128
        result.append(contentsOf: values[start..<(start + 128)])
    }
    return result
}

private func poisonFullAttentionRow(
    _ values: inout [Float],
    position: Int,
    capacity: Int,
    poison: Float
) {
    for kvHead in 0..<8 {
        let start = (kvHead * capacity + position) * 128
        for index in start..<(start + 128) {
            values[index] = poison
        }
    }
}

private func makeFullAttentionFixturePair(writeIdx: Int) -> FullAttentionFixturePair {
    let capacity = 640
    let cacheCount = 8 * capacity * 128
    let rawQueries = MLXArray(
        patternedValues(count: 48 * 128, multiplier: 17, modulus: 509),
        [1, 1, 48 * 128]).asType(.bfloat16)
    let rawKeys = MLXArray(
        patternedValues(count: 8 * 128, multiplier: 29, modulus: 503),
        [1, 1, 8 * 128]).asType(.bfloat16)
    let rawValues = MLXArray(
        patternedValues(count: 8 * 128, multiplier: 37, modulus: 499),
        [1, 1, 8 * 128]).asType(.bfloat16)
    let queryWeight = MLXArray(
        (0..<128).map { 0.75 + Float($0 % 17) / 64.0 },
        [128]).asType(.bfloat16)
    let keyWeight = MLXArray(
        (0..<128).map { 0.625 + Float($0 % 23) / 64.0 },
        [128]).asType(.bfloat16)
    let angleValues = (0..<32).map { cos(Float($0) * 0.03125) }
        + (0..<32).map { sin(Float($0) * 0.03125) }
    let angles = MLXArray(angleValues, [1, 1, 1, 64])
    let scale = MLXArray([Float(1.0 / sqrt(128.0))])

    let historicalKeys = patternedValues(
        count: cacheCount, multiplier: 41, modulus: 487)
    let historicalValues = patternedValues(
        count: cacheCount, multiplier: 43, modulus: 479)
    var baselineKeys = historicalKeys
    var candidateKeys = historicalKeys
    var baselineValues = historicalValues
    var candidateValues = historicalValues
    poisonFullAttentionRow(
        &baselineKeys, position: writeIdx, capacity: capacity, poison: 12)
    poisonFullAttentionRow(
        &candidateKeys, position: writeIdx, capacity: capacity, poison: -13)
    poisonFullAttentionRow(
        &baselineValues, position: writeIdx, capacity: capacity, poison: 14)
    poisonFullAttentionRow(
        &candidateValues, position: writeIdx, capacity: capacity, poison: -15)

    let baselineCacheKeys = MLXArray(
        baselineKeys, [1, 8, capacity, 128]).asType(.bfloat16)
    let candidateCacheKeys = MLXArray(
        candidateKeys, [1, 8, capacity, 128]).asType(.bfloat16)
    let baselineCacheValues = MLXArray(
        baselineValues, [1, 8, capacity, 128]).asType(.bfloat16)
    let candidateCacheValues = MLXArray(
        candidateValues, [1, 8, capacity, 128]).asType(.bfloat16)
    let expectedNeighborKeys = MLXArray(
        fullAttentionRows(historicalKeys, position: writeIdx + 1, capacity: capacity),
        [8 * 128]).asType(.bfloat16)
    let expectedNeighborValues = MLXArray(
        fullAttentionRows(historicalValues, position: writeIdx + 1, capacity: capacity),
        [8 * 128]).asType(.bfloat16)

    eval([
        rawQueries, rawKeys, rawValues, queryWeight, keyWeight, angles, scale,
        baselineCacheKeys, candidateCacheKeys,
        baselineCacheValues, candidateCacheValues,
        expectedNeighborKeys, expectedNeighborValues,
    ])

    func fixture(keys: MLXArray, values: MLXArray) -> FullAttentionFixture {
        FullAttentionFixture(
            rawQueries: rawQueries,
            rawKeys: rawKeys,
            rawValues: rawValues,
            queryWeight: queryWeight,
            keyWeight: keyWeight,
            angles: angles,
            cacheKeys: keys,
            cacheValues: values,
            writeIdx: writeIdx,
            scale: scale)
    }

    return FullAttentionFixturePair(
        baseline: fixture(keys: baselineCacheKeys, values: baselineCacheValues),
        candidate: fixture(keys: candidateCacheKeys, values: candidateCacheValues),
        expectedNeighborKeys: expectedNeighborKeys.asArray(Float.self),
        expectedNeighborValues: expectedNeighborValues.asArray(Float.self))
}

private func runFullAttentionKernel(
    _ kernel: MLXFast.MLXFastKernel,
    fixture: FullAttentionFixture
) -> MLXArray {
    let params = MLXArray([
        UInt32(fixture.writeIdx),
        UInt32(fixture.writeIdx + 1),
        UInt32(fixture.cacheKeys.dim(2)),
    ])
    return kernel(
        [
            fixture.rawQueries, fixture.rawKeys, fixture.rawValues,
            fixture.queryWeight, fixture.keyWeight, fixture.angles,
            fixture.cacheKeys, fixture.cacheValues, params, fixture.scale,
        ],
        grid: (24 * 1024, 1, 1),
        threadGroup: (1024, 1, 1),
        outputShapes: [[1, 48, 1, 128]],
        outputDTypes: [.bfloat16]
    )[0]
}

private func pairOutput(_ values: [Float], pair: Int) -> ArraySlice<Float> {
    let start = pair * 2 * 128
    return values[start..<(start + 2 * 128)]
}

private func checksum(_ values: ArraySlice<Float>) -> Double {
    values.reduce(0) { $0 + Double($1) }
}

private func verifyFullAttentionCorrectness(
    baselineKernel: MLXFast.MLXFastKernel,
    candidateKernel: MLXFast.MLXFastKernel
) throws {
    for writeIdx in [512, 638] {
        let fixtures = makeFullAttentionFixturePair(writeIdx: writeIdx)
        let baselineOutput = runFullAttentionKernel(
            baselineKernel, fixture: fixtures.baseline)
        let candidateOutput = runFullAttentionKernel(
            candidateKernel, fixture: fixtures.candidate)
        eval(baselineOutput, candidateOutput)

        let baselineOutputValues = baselineOutput.asArray(Float.self)
        let candidateOutputValues = candidateOutput.asArray(Float.self)
        let baselineKeys = fixtures.baseline.cacheKeys.asArray(Float.self)
        let candidateKeys = fixtures.candidate.cacheKeys.asArray(Float.self)
        let baselineValues = fixtures.baseline.cacheValues.asArray(Float.self)
        let candidateValues = fixtures.candidate.cacheValues.asArray(Float.self)
        let capacity = fixtures.baseline.cacheKeys.dim(2)
        let currentKeys = fullAttentionRows(
            candidateKeys, position: writeIdx, capacity: capacity)
        let currentValues = fullAttentionRows(
            candidateValues, position: writeIdx, capacity: capacity)
        let neighborKeys = fullAttentionRows(
            candidateKeys, position: writeIdx + 1, capacity: capacity)
        let neighborValues = fullAttentionRows(
            candidateValues, position: writeIdx + 1, capacity: capacity)

        try #require(baselineOutputValues == candidateOutputValues)
        try #require(baselineKeys == candidateKeys)
        try #require(baselineValues == candidateValues)
        try #require(currentKeys.allSatisfy { $0 != -13 && $0 != 12 })
        try #require(currentValues.allSatisfy { $0 != -15 && $0 != 14 })
        try #require(neighborKeys == fixtures.expectedNeighborKeys)
        try #require(neighborValues == fixtures.expectedNeighborValues)
        try #require(
            pairOutput(baselineOutputValues, pair: 0)
                == pairOutput(candidateOutputValues, pair: 0))
        try #require(
            pairOutput(baselineOutputValues, pair: 1)
                == pairOutput(candidateOutputValues, pair: 1))

        print(
            "FULL_ATTN_CORRECTNESS position=\(writeIdx + 1) "
                + "output_exact=true cache_exact=true poison_overwritten=true "
                + "neighbor_unchanged=true current_row_tgm=true "
                + "owner_pair_checksum=\(checksum(pairOutput(candidateOutputValues, pair: 0))) "
                + "nonowner_pair_checksum=\(checksum(pairOutput(candidateOutputValues, pair: 1)))")
    }
}

private func median(_ values: [Double]) -> Double {
    let sorted = values.sorted()
    let middle = sorted.count / 2
    if sorted.count.isMultiple(of: 2) {
        return (sorted[middle - 1] + sorted[middle]) / 2
    }
    return sorted[middle]
}

private func timeFullAttentionBatch(
    kernel: MLXFast.MLXFastKernel,
    fixture: FullAttentionFixture,
    batchSize: Int
) -> Double {
    var outputs: [MLXArray] = []
    outputs.reserveCapacity(batchSize)
    for _ in 0..<batchSize {
        outputs.append(runFullAttentionKernel(kernel, fixture: fixture))
    }
    let start = DispatchTime.now().uptimeNanoseconds
    eval(outputs)
    let elapsed = DispatchTime.now().uptimeNanoseconds - start
    return Double(elapsed) / Double(batchSize)
}

private struct FullAttentionTimingResult {
    let baselineMedian: Double
    let candidateMedian: Double
    let baselineMAD: Double
    let candidateMAD: Double
    let normalizedMAD: Double
    let speedup: Double
    let passed: Bool
}

private func analyzeFullAttentionTiming(
    baseline: [Double],
    candidate: [Double]
) -> FullAttentionTimingResult {
    let baselineMedian = median(baseline)
    let candidateMedian = median(candidate)
    let baselineMAD = median(baseline.map { abs($0 - baselineMedian) })
    let candidateMAD = median(candidate.map { abs($0 - candidateMedian) })
    let normalizedMAD = Foundation.sqrt(
        pow(baselineMAD / baselineMedian, 2)
            + pow(candidateMAD / candidateMedian, 2))
    let speedup = baselineMedian / candidateMedian
    return FullAttentionTimingResult(
        baselineMedian: baselineMedian,
        candidateMedian: candidateMedian,
        baselineMAD: baselineMAD,
        candidateMAD: candidateMAD,
        normalizedMAD: normalizedMAD,
        speedup: speedup,
        passed: speedup >= 1.003 && (speedup - 1) > 2 * normalizedMAD)
}

private func printFullAttentionTiming(
    order: String,
    baseline: [Double],
    candidate: [Double],
    result: FullAttentionTimingResult
) {
    print("FULL_ATTN_RAW_\(order)_BASE_NS \(baseline)")
    print("FULL_ATTN_RAW_\(order)_CANDIDATE_NS \(candidate)")
    print(
        "FULL_ATTN_TIMING order=\(order) "
            + "baseline_median_ns=\(result.baselineMedian) "
            + "candidate_median_ns=\(result.candidateMedian) "
            + "baseline_mad_ns=\(result.baselineMAD) "
            + "candidate_mad_ns=\(result.candidateMAD) "
            + "normalized_mad=\(result.normalizedMAD) "
            + "speedup=\(result.speedup) pass=\(result.passed)")
}

private func verifyFullAttentionTiming(
    baselineKernel: MLXFast.MLXFastKernel,
    candidateKernel: MLXFast.MLXFastKernel
) throws {
    let fixtures = makeFullAttentionFixturePair(writeIdx: 638)
    for _ in 0..<7 {
        eval(runFullAttentionKernel(baselineKernel, fixture: fixtures.baseline))
        eval(runFullAttentionKernel(candidateKernel, fixture: fixtures.candidate))
    }

    let sampleCount = 31
    let batchSize = 8
    var abBaseline: [Double] = []
    var abCandidate: [Double] = []
    var baBaseline: [Double] = []
    var baCandidate: [Double] = []
    for _ in 0..<sampleCount {
        abBaseline.append(timeFullAttentionBatch(
            kernel: baselineKernel, fixture: fixtures.baseline, batchSize: batchSize))
        abCandidate.append(timeFullAttentionBatch(
            kernel: candidateKernel, fixture: fixtures.candidate, batchSize: batchSize))
    }
    for _ in 0..<sampleCount {
        baCandidate.append(timeFullAttentionBatch(
            kernel: candidateKernel, fixture: fixtures.candidate, batchSize: batchSize))
        baBaseline.append(timeFullAttentionBatch(
            kernel: baselineKernel, fixture: fixtures.baseline, batchSize: batchSize))
    }

    let ab = analyzeFullAttentionTiming(baseline: abBaseline, candidate: abCandidate)
    let ba = analyzeFullAttentionTiming(baseline: baBaseline, candidate: baCandidate)
    printFullAttentionTiming(
        order: "AB", baseline: abBaseline, candidate: abCandidate, result: ab)
    printFullAttentionTiming(
        order: "BA", baseline: baBaseline, candidate: baCandidate, result: ba)
    try #require(ab.passed)
    try #require(ba.passed)
}

@Test
func fullAttentionProducerPersistenceGate() throws {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_FULL_ATTN_PRODUCER_GATE"] == "1" else {
        return
    }

    let baselineText = try fullAttentionKernelText(at: fullAttentionBaseRevision)
    let candidateText = try fullAttentionKernelText(at: nil)
    try #require(baselineText.header.contains("dst[0] = tg_k"))
    try #require(baselineText.header.contains("d0 = tg_v"))
    try #require(candidateText.header.contains("dst[0] = tg_k"))
    try #require(candidateText.header.contains("d0 = tg_v"))
    try #require(candidateText.source.contains("const bool sub_a = uint(i) == widx"))
    try #require(candidateText.source.contains("const bool sub_b = uint(i + BN) == widx"))
    print("FULL_ATTN_TGM_SOURCE_PROOF baseline=true candidate=true")

    let baselineKernel = makeFullAttentionKernel(
        name: "laguna_full_fused_attn_grow_v1_baseline",
        text: baselineText)
    let candidateKernel = makeFullAttentionKernel(
        name: "laguna_full_fused_attn_grow_v1",
        text: candidateText)
    let mode = ProcessInfo.processInfo.environment["MLXFAST_FULL_ATTN_GATE_MODE"]
        ?? "correctness"
    switch mode {
    case "correctness":
        try verifyFullAttentionCorrectness(
            baselineKernel: baselineKernel,
            candidateKernel: candidateKernel)
    case "timing":
        try verifyFullAttentionTiming(
            baselineKernel: baselineKernel,
            candidateKernel: candidateKernel)
    default:
        throw FullAttentionGateError.unsupportedMode(mode)
    }
}
