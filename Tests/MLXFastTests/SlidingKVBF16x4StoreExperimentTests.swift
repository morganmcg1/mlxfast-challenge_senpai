import Foundation
import MLX
import Testing

@testable import MLXFastModel

@Test
func slidingKVBF16x4StoreExperiment() throws {
    guard let mode = ProcessInfo.processInfo.environment[
        "DARKBLOOM_SLIDING_KV_EXPERIMENT_MODE"
    ] else {
        return
    }

    switch mode {
    case "source":
        let fixture = makeSlidingFixture(pattern: .checkpointLike)
        eval(runSlidingKernel(fixture, writeIdx: 0, verbose: true))
    case "differential":
        let path = try #require(
            ProcessInfo.processInfo.environment["DARKBLOOM_SLIDING_KV_ARTIFACT"])
        try writeDifferentialArtifact(to: path)
    case "benchmark":
        let path = try #require(
            ProcessInfo.processInfo.environment["DARKBLOOM_SLIDING_KV_ARTIFACT"])
        try writeBenchmarkArtifact(to: path)
    default:
        Issue.record("unknown experiment mode: \(mode)")
    }
}

private enum SlidingPattern: UInt16, CaseIterable {
    case checkpointLike = 0
    case random = 1
    case adversarial = 2
}

private struct SlidingFixture {
    let rawQueries: MLXArray
    let rawKeys: MLXArray
    let rawValues: MLXArray
    let queryWeight: MLXArray
    let keyWeight: MLXArray
    let angles: MLXArray
    let cacheKeys: MLXArray
    let cacheValues: MLXArray
    let scale: MLXArray
}

private func makeSlidingFixture(pattern: SlidingPattern) -> SlidingFixture {
    let heads = 64
    let kvHeads = 8
    let headDim = 128
    let window = 512
    let rawQueries = makeBF16(
        count: heads * headDim,
        shape: [1, 1, heads * headDim],
        pattern: pattern,
        salt: 0x1234_5678)
    let rawKeys = makeBF16(
        count: kvHeads * headDim,
        shape: [1, 1, kvHeads * headDim],
        pattern: pattern,
        salt: 0x2345_6789)
    let rawValues = makeBF16(
        count: kvHeads * headDim,
        shape: [1, 1, kvHeads * headDim],
        pattern: pattern,
        salt: 0x3456_789a)
    let queryWeight = makeBF16(
        count: headDim,
        shape: [headDim],
        pattern: .checkpointLike,
        salt: 0x4567_89ab,
        offset: 1)
    let keyWeight = makeBF16(
        count: headDim,
        shape: [headDim],
        pattern: .checkpointLike,
        salt: 0x5678_9abc,
        offset: 1)
    let cacheKeys = makeBF16(
        count: kvHeads * window * headDim,
        shape: [1, kvHeads, window, headDim],
        pattern: pattern,
        salt: 0x6789_abcd)
    let cacheValues = makeBF16(
        count: kvHeads * window * headDim,
        shape: [1, kvHeads, window, headDim],
        pattern: pattern,
        salt: 0x789a_bcde)

    var angleValues = [Float](repeating: 0, count: headDim)
    for pair in 0..<(headDim / 2) {
        let theta = Double(pair + 1) * 0.000_976_562_5
        angleValues[pair] = Float(cos(theta))
        angleValues[pair + headDim / 2] = Float(sin(theta))
    }

    return SlidingFixture(
        rawQueries: rawQueries,
        rawKeys: rawKeys,
        rawValues: rawValues,
        queryWeight: queryWeight,
        keyWeight: keyWeight,
        angles: MLXArray(angleValues, [1, 1, 1, headDim]),
        cacheKeys: cacheKeys,
        cacheValues: cacheValues,
        scale: MLXArray([Float(1 / sqrt(128.0))])
    )
}

private func makeBF16(
    count: Int,
    shape: [Int],
    pattern: SlidingPattern,
    salt: UInt64,
    offset: Float = 0
) -> MLXArray {
    switch pattern {
    case .checkpointLike:
        let values = (0..<count).map { index in
            let x = Double((index &* 73 &+ Int(salt & 0xffff)) % 4093)
            return offset + Float(sin(x * 0.013_671_875) * 0.1875)
        }
        return MLXArray(values, shape).asType(.bfloat16)
    case .random:
        var state = salt
        let values = (0..<count).map { _ -> Float in
            state = state &* 6_364_136_223_846_793_005 &+ 1_442_695_040_888_963_407
            let unit = Float((state >> 40) & 0x00ff_ffff) / 8_388_607.5
            return offset + (unit - 1) * 0.75
        }
        return MLXArray(values, shape).asType(.bfloat16)
    case .adversarial:
        let bits: [UInt16] = [
            0x0000, 0x8000, 0x0001, 0x8001,
            0x007f, 0x807f, 0x0080, 0x8080,
            0x3f00, 0xbf00, 0x3f80, 0xbf80,
            0x4040, 0xc040, 0x4180, 0xc180,
        ]
        let values = (0..<count).map { bits[($0 &+ Int(salt & 15)) & 15] }
        return MLXArray(values, shape).view(dtype: .bfloat16)
    }
}

private func runSlidingKernel(
    _ fixture: SlidingFixture,
    writeIdx: Int,
    verbose: Bool = false
) -> MLXArray {
    lagunaSlidingFusedAttentionKernel(
        [
            fixture.rawQueries, fixture.rawKeys, fixture.rawValues,
            fixture.queryWeight, fixture.keyWeight, fixture.angles,
            fixture.cacheKeys, fixture.cacheValues,
            MLXArray([UInt32(writeIdx)]), fixture.scale,
        ],
        grid: (64 / 2 * 1024, 1, 1),
        threadGroup: (1024, 1, 1),
        outputShapes: [[1, 64, 1, 128]],
        outputDTypes: [.bfloat16],
        verbose: verbose
    )[0]
}

private func writeDifferentialArtifact(to path: String) throws {
    let writeIndices = [0, 1, 31, 255, 511]
    var artifact = Data()
    artifact.appendUInt16(0x4b56)
    artifact.appendUInt16(1)

    for pattern in SlidingPattern.allCases {
        let fixture = makeSlidingFixture(pattern: pattern)
        for writeIdx in writeIndices {
            let output = runSlidingKernel(fixture, writeIdx: writeIdx)
            eval(output)

            artifact.appendUInt16(pattern.rawValue)
            artifact.appendUInt16(UInt16(writeIdx))
            let keyBits = fixture.cacheKeys.view(dtype: .uint16).asArray(UInt16.self)
            let valueBits = fixture.cacheValues.view(dtype: .uint16).asArray(UInt16.self)
            let outputBits = output.view(dtype: .uint16).asArray(UInt16.self)
            for head in 0..<8 {
                let rowStart = (head * 512 + writeIdx) * 128
                artifact.appendUInt16s(keyBits[rowStart..<(rowStart + 128)])
                artifact.appendUInt16s(valueBits[rowStart..<(rowStart + 128)])
            }
            artifact.appendUInt16s(outputBits)
        }
    }

    try artifact.write(to: URL(fileURLWithPath: path), options: .atomic)
}

private struct SlidingBenchmarkArtifact: Codable {
    let kernel: String
    let vectorStoreEnabled: Bool
    let sequenceLength: Int
    let warmupSamples: Int
    let measuredSamples: Int
    let dispatchesPerSample: Int
    let millisecondsPerDispatch: [Double]
}

private func writeBenchmarkArtifact(to path: String) throws {
    let fixture = makeSlidingFixture(pattern: .checkpointLike)
    let warmupSamples = 16
    let measuredSamples = 80
    let dispatchesPerSample = 4

    for sample in 0..<warmupSamples {
        let outputs = (0..<dispatchesPerSample).map {
            runSlidingKernel(
                fixture,
                writeIdx: (sample * dispatchesPerSample + $0) & 511)
        }
        eval(outputs)
    }

    var samples = [Double]()
    samples.reserveCapacity(measuredSamples)
    for sample in 0..<measuredSamples {
        let start = DispatchTime.now().uptimeNanoseconds
        let outputs = (0..<dispatchesPerSample).map {
            runSlidingKernel(
                fixture,
                writeIdx: ((sample + warmupSamples) * dispatchesPerSample + $0) & 511)
        }
        eval(outputs)
        let end = DispatchTime.now().uptimeNanoseconds
        samples.append(
            Double(end - start) / 1_000_000 / Double(dispatchesPerSample))
    }

    let artifact = SlidingBenchmarkArtifact(
        kernel: "laguna_sliding_fused_attn_ring_v1",
        vectorStoreEnabled: lagunaSlidingKVBF16x4StoreEnabled,
        sequenceLength: 512,
        warmupSamples: warmupSamples,
        measuredSamples: measuredSamples,
        dispatchesPerSample: dispatchesPerSample,
        millisecondsPerDispatch: samples
    )
    let data = try JSONEncoder().encode(artifact)
    try data.write(to: URL(fileURLWithPath: path), options: .atomic)
}

extension Data {
    fileprivate mutating func appendUInt16(_ value: UInt16) {
        var littleEndian = value.littleEndian
        Swift.withUnsafeBytes(of: &littleEndian) { append(contentsOf: $0) }
    }

    fileprivate mutating func appendUInt16s<S: Sequence>(_ values: S)
    where S.Element == UInt16 {
        for value in values {
            appendUInt16(value)
        }
    }
}
