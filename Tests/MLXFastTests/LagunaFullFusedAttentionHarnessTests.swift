import Foundation
import MLX
@testable import MLXFastModel
import Testing

@Suite(.serialized)
struct LagunaFullFusedAttentionHarnessTests {
    private let lengths = [513, 544, 545, 576, 577, 608, 609, 640]
    private let capacity = 640

    @Test
    func fullFusedAttentionHarness() throws {
        let environment = ProcessInfo.processInfo.environment
        guard let mode = environment["MLXFAST_FULL_ATTN_HARNESS_MODE"] else { return }

        let root = URL(
            fileURLWithPath: environment["MLXFAST_FULL_ATTN_ARTIFACT_DIR"]
                ?? ".agent_tmp/full-attn-harness",
            isDirectory: true
        )
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)

        switch mode {
        case "record":
            try recordOracle(at: root)
        case "check":
            try checkOracle(at: root)
        case "capture":
            try captureKernel(at: root, environment: environment)
        case "time":
            try timeKernel(at: root, environment: environment)
        default:
            throw HarnessFailure("unknown harness mode: \(mode)")
        }
    }

    private func recordOracle(at root: URL) throws {
        for length in lengths {
            let result = run(length: length)
            try result.output.write(to: artifact(root, length, "output"))
            try result.keys.write(to: artifact(root, length, "keys"))
            try result.values.write(to: artifact(root, length, "values"))
            print(
                "FULL_ATTN_ORACLE_RECORDED N=\(length) owner=\((length - 1) & 31) "
                    + "output_bytes=\(result.output.count) cache_bytes=\(result.keys.count)"
            )
        }
    }

    private func checkOracle(at root: URL) throws {
        var firstOutput: Data?
        for length in lengths {
            let result = run(length: length)
            let expectedOutput = try Data(contentsOf: artifact(root, length, "output"))
            let expectedKeys = try Data(contentsOf: artifact(root, length, "keys"))
            let expectedValues = try Data(contentsOf: artifact(root, length, "values"))
            try require(result.output == expectedOutput, "output mismatch at N=\(length)")
            try require(result.keys == expectedKeys, "key-cache mismatch at N=\(length)")
            try require(result.values == expectedValues, "value-cache mismatch at N=\(length)")

            if length == lengths[0] {
                firstOutput = result.output
                var corrupted = expectedOutput
                corrupted[corrupted.startIndex] ^= 1
                try require(
                    corrupted != result.output,
                    "one-bit corruption positive control was not detected"
                )
                print("FULL_ATTN_POSITIVE_CONTROL one_bit_corruption=detected")
            }
            print(
                "FULL_ATTN_ORACLE_MATCH N=\(length) owner=\((length - 1) & 31) "
                    + "output_bytes=\(result.output.count) cache_bytes=\(result.keys.count)"
            )
        }

        let misrouted = try Data(contentsOf: artifact(root, lengths[1], "output"))
        try require(
            firstOutput != misrouted,
            "cross-length oracle misroute positive control was not detected"
        )
        print("FULL_ATTN_POSITIVE_CONTROL cross_length_misroute=detected")
    }

    private func captureKernel(at root: URL, environment: [String: String]) throws {
        let length = Int(environment["MLXFAST_FULL_ATTN_CAPTURE_LENGTH"] ?? "513") ?? 513
        let label = environment["MLXFAST_FULL_ATTN_CAPTURE_LABEL"] ?? "unknown"
        try require(lengths.contains(length), "unsupported capture length: \(length)")

        let traceURL = root.appendingPathComponent("capture-\(label)-N\(length).gputrace")
        try require(
            !FileManager.default.fileExists(atPath: traceURL.path),
            "capture path already exists: \(traceURL.path)"
        )

        let fixture = makeFixture()
        evaluateInputs(fixture)
        let warmup = invoke(fixture, length: length)
        eval(warmup)
        Stream.gpu.synchronize()

        GPU.startCapture(url: traceURL)
        let output = invoke(fixture, length: length)
        eval(output)
        Stream.gpu.synchronize()
        GPU.stopCapture(url: traceURL)

        try require(output.shape == [1, 48, 1, 128], "unexpected capture output shape")
        print(
            "FULL_ATTN_CAPTURED label=\(label) N=\(length) owner=\((length - 1) & 31) "
                + "path=\(traceURL.path)"
        )
    }

    private func timeKernel(at root: URL, environment: [String: String]) throws {
        let iterations = Int(environment["MLXFAST_FULL_ATTN_ITERATIONS"] ?? "80") ?? 80
        let label = environment["MLXFAST_FULL_ATTN_LABEL"] ?? "unknown"
        var timings: [String: [UInt64]] = [:]

        for length in lengths {
            let fixture = makeFixture()
            evaluateInputs(fixture)
            let warmup = invoke(fixture, length: length)
            eval(warmup)
            Stream.gpu.synchronize()

            var samples: [UInt64] = []
            samples.reserveCapacity(iterations)
            for _ in 0..<iterations {
                let started = DispatchTime.now().uptimeNanoseconds
                let output = invoke(fixture, length: length)
                eval(output)
                Stream.gpu.synchronize()
                samples.append(DispatchTime.now().uptimeNanoseconds - started)
            }
            timings[String(length)] = samples
            let sorted = samples.sorted()
            print(
                "FULL_ATTN_TIMING label=\(label) N=\(length) owner=\((length - 1) & 31) "
                    + "iterations=\(iterations) median_ns=\(sorted[sorted.count / 2])"
            )
        }

        let result = TimingResult(
            label: label,
            iterations: iterations,
            lengths: lengths,
            nanoseconds: timings
        )
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        try encoder.encode(result).write(to: root.appendingPathComponent("timing-\(label).json"))
    }

    private func run(length: Int) -> RawResult {
        let fixture = makeFixture()
        evaluateInputs(fixture)
        let output = invoke(fixture, length: length)
        eval(output)
        Stream.gpu.synchronize()
        return RawResult(
            output: rawBF16(output),
            keys: rawBF16(fixture.cacheKeys),
            values: rawBF16(fixture.cacheValues)
        )
    }

    private func invoke(_ fixture: Fixture, length: Int) -> MLXArray {
        lagunaFullFusedAttention(
            rawQueries: fixture.rawQueries,
            rawKeys: fixture.rawKeys,
            rawValues: fixture.rawValues,
            queryWeight: fixture.queryWeight,
            keyWeight: fixture.keyWeight,
            angles: fixture.angles,
            cacheKeys: fixture.cacheKeys,
            cacheValues: fixture.cacheValues,
            writeIdx: length - 1,
            scale: fixture.scale
        )
    }

    private func makeFixture() -> Fixture {
        let rawQueries = deterministicBF16(count: 48 * 128, multiplier: 17, bias: 11)
            .reshaped([1, 1, 48 * 128])
        let rawKeys = deterministicBF16(count: 8 * 128, multiplier: 29, bias: 7)
            .reshaped([1, 1, 8 * 128])
        let rawValues = deterministicBF16(count: 8 * 128, multiplier: 37, bias: 19)
            .reshaped([1, 1, 8 * 128])
        let queryWeight = deterministicWeight(count: 128, multiplier: 5, bias: 3)
        let keyWeight = deterministicWeight(count: 128, multiplier: 7, bias: 9)
        let angles = quarterTurnAngles().reshaped([1, 1, 1, 64])
        let cacheKeys = deterministicBF16(
            count: 8 * capacity * 128,
            multiplier: 41,
            bias: 23
        ).reshaped([1, 8, capacity, 128])
        let cacheValues = deterministicBF16(
            count: 8 * capacity * 128,
            multiplier: 43,
            bias: 31
        ).reshaped([1, 8, capacity, 128])
        return Fixture(
            rawQueries: rawQueries,
            rawKeys: rawKeys,
            rawValues: rawValues,
            queryWeight: queryWeight,
            keyWeight: keyWeight,
            angles: angles,
            cacheKeys: cacheKeys,
            cacheValues: cacheValues,
            scale: MLXArray([Float(0.08838834764831845)])
        )
    }

    private func deterministicBF16(count: Int, multiplier: Int, bias: Int) -> MLXArray {
        let values = (0..<count).map {
            Float((($0 * multiplier + bias) % 251) - 125) / 64
        }
        return MLXArray(values).asType(.bfloat16)
    }

    private func deterministicWeight(count: Int, multiplier: Int, bias: Int) -> MLXArray {
        let values = (0..<count).map {
            Float(48 + (($0 * multiplier + bias) % 33)) / 64
        }
        return MLXArray(values).asType(.bfloat16)
    }

    private func quarterTurnAngles() -> MLXArray {
        let rotations: [(Float, Float)] = [(1, 0), (0, 1), (-1, 0), (0, -1)]
        let cosine = (0..<32).map { rotations[$0 & 3].0 }
        let sine = (0..<32).map { rotations[$0 & 3].1 }
        return MLXArray(cosine + sine)
    }

    private func evaluateInputs(_ fixture: Fixture) {
        eval([
            fixture.rawQueries, fixture.rawKeys, fixture.rawValues,
            fixture.queryWeight, fixture.keyWeight, fixture.angles,
            fixture.cacheKeys, fixture.cacheValues, fixture.scale,
        ])
        Stream.gpu.synchronize()
    }

    private func rawBF16(_ array: MLXArray) -> Data {
        let bits = array.view(dtype: .uint16).asArray(UInt16.self)
        return bits.withUnsafeBytes { Data($0) }
    }

    private func artifact(_ root: URL, _ length: Int, _ component: String) -> URL {
        root.appendingPathComponent("N\(length)-\(component).bin")
    }

    private func require(_ condition: @autoclosure () -> Bool, _ message: String) throws {
        guard condition() else { throw HarnessFailure(message) }
    }
}

private struct Fixture {
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

private struct RawResult {
    let output: Data
    let keys: Data
    let values: Data
}

private struct TimingResult: Codable {
    let label: String
    let iterations: Int
    let lengths: [Int]
    let nanoseconds: [String: [UInt64]]
}

private struct HarnessFailure: Error, CustomStringConvertible {
    let description: String

    init(_ description: String) {
        self.description = description
    }
}
