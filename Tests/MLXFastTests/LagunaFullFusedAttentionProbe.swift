import Foundation
import MLX
@testable import MLXFastModel
import Testing

private let fullAttentionProbeLengths = [2, 31, 32, 33, 511, 512, 513, 640]
private let fullAttentionProbeCapacity = 768
private let fullAttentionProbeWarmups = 4
private let fullAttentionProbeSamples = 31

private struct FullAttentionProbeFixture {
    let rawQueries: MLXArray
    let rawKeys: MLXArray
    let rawValues: MLXArray
    let queryWeight: MLXArray
    let keyWeight: MLXArray
    let angles: MLXArray
    let cacheKeysData: Data
    let cacheValuesData: Data
    let scale: MLXArray
}

private struct FullAttentionProbeCapture {
    let elapsedNanoseconds: UInt64
    let output: Data
    let cacheKeys: Data
    let cacheValues: Data
}

@Test
func lagunaFullFusedAttentionProbe() throws {
    let environment = ProcessInfo.processInfo.environment
    guard environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
        return
    }
    let outputPath = try #require(environment["Q3_PROBE_OUTPUT_DIR"])
    let label = try #require(environment["Q3_PROBE_LABEL"])
    let outputDirectory = URL(fileURLWithPath: outputPath, isDirectory: true)
    try FileManager.default.createDirectory(
        at: outputDirectory, withIntermediateDirectories: true)

    let fixture = makeFullAttentionProbeFixture()
    var cases: [[String: Any]] = []

    for length in fullAttentionProbeLengths {
        for _ in 0..<fullAttentionProbeWarmups {
            _ = runFullAttentionProbe(fixture: fixture, length: length, capture: false)
        }

        var samples: [UInt64] = []
        for _ in 0..<fullAttentionProbeSamples {
            samples.append(
                runFullAttentionProbe(fixture: fixture, length: length, capture: false)
                    .elapsedNanoseconds)
        }

        let capture = runFullAttentionProbe(fixture: fixture, length: length, capture: true)
        expectOnlyCacheRowChanged(
            initial: fixture.cacheKeysData,
            final: capture.cacheKeys,
            writeIndex: length - 1)
        expectOnlyCacheRowChanged(
            initial: fixture.cacheValuesData,
            final: capture.cacheValues,
            writeIndex: length - 1)
        try writeFullAttentionProbeCapture(
            capture, prefix: "n-\(length)", to: outputDirectory)

        if length == 512 {
            let repeated = runFullAttentionProbe(
                fixture: fixture, length: length, capture: true)
            #expect(repeated.output == capture.output)
            #expect(repeated.cacheKeys == capture.cacheKeys)
            #expect(repeated.cacheValues == capture.cacheValues)
            try writeFullAttentionProbeCapture(
                repeated, prefix: "n-512-repeat", to: outputDirectory)
        }

        let sorted = samples.sorted()
        cases.append([
            "length": length,
            "writeIndex": length - 1,
            "samplesNanoseconds": samples.map(Int.init),
            "minimumNanoseconds": Int(sorted.first!),
            "p10Nanoseconds": Int(probePercentile(sorted, 0.10)),
            "medianNanoseconds": Int(probePercentile(sorted, 0.50)),
            "p90Nanoseconds": Int(probePercentile(sorted, 0.90)),
            "maximumNanoseconds": Int(sorted.last!),
        ])
    }

    let result: [String: Any] = [
        "label": label,
        "capacity": fullAttentionProbeCapacity,
        "warmupsPerLength": fullAttentionProbeWarmups,
        "samplesPerLength": fullAttentionProbeSamples,
        "cases": cases,
    ]
    let encoded = try JSONSerialization.data(
        withJSONObject: result, options: [.prettyPrinted, .sortedKeys])
    try encoded.write(to: outputDirectory.appendingPathComponent("results.json"))
    print(String(decoding: encoded, as: UTF8.self))
}

private func makeFullAttentionProbeFixture() -> FullAttentionProbeFixture {
    let rawQueries = probeBF16Array(
        count: 48 * 128, shape: [1, 1, 48 * 128],
        frequency: 0.013, phase: 0.17, amplitude: 0.125)
    let rawKeys = probeBF16Array(
        count: 8 * 128, shape: [1, 1, 8 * 128],
        frequency: 0.019, phase: 0.29, amplitude: 0.125)
    let rawValues = probeBF16Array(
        count: 8 * 128, shape: [1, 1, 8 * 128],
        frequency: 0.023, phase: 0.41, amplitude: 0.25)
    let queryWeight = probeBF16Array(
        count: 128, shape: [128],
        frequency: 0.031, phase: 0.07, amplitude: 0.5, offset: 1.0)
    let keyWeight = probeBF16Array(
        count: 128, shape: [128],
        frequency: 0.037, phase: 0.11, amplitude: 0.5, offset: 1.0)

    let angleAxis = MLXArray(0..<32).asType(.float32)
    let theta = angleAxis * 0.017 + 0.03
    let angles = concatenated([cos(theta), sin(theta)], axis: 0)
        .reshaped([1, 1, 1, 64])
    let cacheShape = [1, 8, fullAttentionProbeCapacity, 128]
    let cacheKeys = probeBF16Array(
        count: 8 * fullAttentionProbeCapacity * 128, shape: cacheShape,
        frequency: 0.00071, phase: 0.53, amplitude: 0.0625)
    let cacheValues = probeBF16Array(
        count: 8 * fullAttentionProbeCapacity * 128, shape: cacheShape,
        frequency: 0.00083, phase: 0.67, amplitude: 0.0625)
    let scale = MLXArray([pow(Float(128), -0.5)])
    eval(
        rawQueries, rawKeys, rawValues, queryWeight, keyWeight, angles,
        cacheKeys, cacheValues, scale)

    return FullAttentionProbeFixture(
        rawQueries: rawQueries,
        rawKeys: rawKeys,
        rawValues: rawValues,
        queryWeight: queryWeight,
        keyWeight: keyWeight,
        angles: angles,
        cacheKeysData: cacheKeys.asData(access: .copy).data,
        cacheValuesData: cacheValues.asData(access: .copy).data,
        scale: scale)
}

private func probeBF16Array(
    count: Int,
    shape: [Int],
    frequency: Float,
    phase: Float,
    amplitude: Float,
    offset: Float = 0
) -> MLXArray {
    let axis = MLXArray(0..<count).asType(.float32)
    return (sin(axis * frequency + phase) * amplitude + offset)
        .asType(.bfloat16)
        .reshaped(shape)
}

private func runFullAttentionProbe(
    fixture: FullAttentionProbeFixture,
    length: Int,
    capture: Bool
) -> FullAttentionProbeCapture {
    let cacheShape = [1, 8, fullAttentionProbeCapacity, 128]
    let cacheKeys = MLXArray(fixture.cacheKeysData, cacheShape, dtype: .bfloat16)
    let cacheValues = MLXArray(fixture.cacheValuesData, cacheShape, dtype: .bfloat16)
    eval(cacheKeys, cacheValues)

    let start = DispatchTime.now().uptimeNanoseconds
    let output = lagunaFullFusedAttention(
        rawQueries: fixture.rawQueries,
        rawKeys: fixture.rawKeys,
        rawValues: fixture.rawValues,
        queryWeight: fixture.queryWeight,
        keyWeight: fixture.keyWeight,
        angles: fixture.angles,
        cacheKeys: cacheKeys,
        cacheValues: cacheValues,
        writeIdx: length - 1,
        scale: fixture.scale)
    eval(output)
    let elapsed = DispatchTime.now().uptimeNanoseconds - start

    guard capture else {
        return FullAttentionProbeCapture(
            elapsedNanoseconds: elapsed,
            output: Data(),
            cacheKeys: Data(),
            cacheValues: Data())
    }
    return FullAttentionProbeCapture(
        elapsedNanoseconds: elapsed,
        output: output.asData(access: .copy).data,
        cacheKeys: cacheKeys.asData(access: .copy).data,
        cacheValues: cacheValues.asData(access: .copy).data)
}

private func expectOnlyCacheRowChanged(
    initial: Data,
    final: Data,
    writeIndex: Int
) {
    let rowBytes = 128 * MemoryLayout<UInt16>.size
    var expected = initial
    for head in 0..<8 {
        let start = (head * fullAttentionProbeCapacity + writeIndex) * rowBytes
        let end = start + rowBytes
        #expect(initial[start..<end] != final[start..<end])
        expected.replaceSubrange(start..<end, with: final[start..<end])
    }
    #expect(expected == final)
}

private func writeFullAttentionProbeCapture(
    _ capture: FullAttentionProbeCapture,
    prefix: String,
    to directory: URL
) throws {
    try capture.output.write(to: directory.appendingPathComponent("\(prefix)-output.bf16"))
    try capture.cacheKeys.write(to: directory.appendingPathComponent("\(prefix)-keys.bf16"))
    try capture.cacheValues.write(to: directory.appendingPathComponent("\(prefix)-values.bf16"))
}

private func probePercentile(_ sorted: [UInt64], _ percentile: Double) -> UInt64 {
    let index = Int((Double(sorted.count - 1) * percentile).rounded())
    return sorted[index]
}
