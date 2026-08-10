import Dispatch
import Foundation
import MLX
@testable import MLXFastModel
import Testing

private let prefillInputRMSRPG4Epsilon: Float = 1e-6
private let prefillInputRMSRPG4Width = 2048

private func bf16Array(bits: [UInt16], shape: [Int]) -> MLXArray {
    MLXArray(bits, shape).view(dtype: .bfloat16)
}

private func repeatedBF16Pattern(_ pattern: [UInt16], rows: Int) -> MLXArray {
    let count = rows * prefillInputRMSRPG4Width
    let bits = (0..<count).map { pattern[$0 % pattern.count] }
    return bf16Array(bits: bits, shape: [1, rows, prefillInputRMSRPG4Width])
}

private func stockInputRMS(_ input: MLXArray, weight: MLXArray) -> MLXArray {
    MLXFast.rmsNorm(input, weight: weight, eps: prefillInputRMSRPG4Epsilon)
}

private func exactBytes(_ array: MLXArray) -> Data {
    array.asData(access: .copy).data
}

private func requireExactInputRMSMatch(
    input: MLXArray, weight: MLXArray, label: String
) throws -> Data {
    let candidate = try #require(
        lagunaPrefillInputRMSRPG4(
            input, weight: weight, epsilon: prefillInputRMSRPG4Epsilon
        ),
        "candidate declined supported case \(label)"
    )
    let stock = stockInputRMS(input, weight: weight)
    eval(candidate, stock)

    #expect(candidate.dtype == .bfloat16)
    #expect(candidate.shape == stock.shape)
    let candidateBytes = exactBytes(candidate)
    let stockBytes = exactBytes(stock)
    #expect(candidateBytes == stockBytes, "byte mismatch for \(label)")
    print("prefill_input_rms_rpg4_exact label=\(label) bytes=\(candidateBytes.count)")
    return stockBytes
}

@Test
func prefillInputRMSRPG4MatchesStockBytesWhenRuntimeTestsAreEnabled() throws {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1"
    else { return }
    #expect(
        ProcessInfo.processInfo.environment["DARKBLOOM_PREFILL_INPUT_RMS_RPG4"] == "1"
    )

    let store = try DenseTensorStore(weightsPath: "weights")
    let tensor = try store.materializedTensor(
        named: "model.layers.0.input_layernorm.weight"
    )
    let realWeight = try MLXArrayTensorBridge().makeArray(from: tensor)
    #expect(realWeight.dtype == .bfloat16)
    #expect(realWeight.shape == [prefillInputRMSRPG4Width])

    let finitePattern: [UInt16] = [
        0x0000, 0x8000, 0x0001, 0x8001, 0x007f, 0x807f, 0x0080, 0x8080,
        0x3f80, 0xbf80, 0x3f00, 0xbf00, 0x4000, 0xc000, 0x7f7f, 0xff7f,
    ]
    let nonfinitePattern: [UInt16] = [
        0x0000, 0x8000, 0x3f80, 0xbf80, 0x7f80, 0xff80, 0x7fc1, 0xffc1,
        0x0001, 0x8001, 0x7f7f, 0xff7f, 0x3f00, 0xbf00, 0x4000, 0xc000,
    ]

    var finiteRows4Stock = Data()
    for rows in [4, 8, 512] {
        let finiteInput = repeatedBF16Pattern(finitePattern, rows: rows)
        let stockBytes = try requireExactInputRMSMatch(
            input: finiteInput, weight: realWeight, label: "real_weight_finite_rows_\(rows)"
        )
        if rows == 4 {
            finiteRows4Stock = stockBytes
        }
        _ = try requireExactInputRMSMatch(
            input: repeatedBF16Pattern(nonfinitePattern, rows: rows),
            weight: realWeight,
            label: "real_weight_nonfinite_rows_\(rows)"
        )
    }

    let adversarialWeight = bf16Array(
        bits: (0..<prefillInputRMSRPG4Width).map {
            nonfinitePattern[$0 % nonfinitePattern.count]
        },
        shape: [prefillInputRMSRPG4Width]
    )
    _ = try requireExactInputRMSMatch(
        input: repeatedBF16Pattern(finitePattern, rows: 4),
        weight: adversarialWeight,
        label: "adversarial_weight_rows_4"
    )

    var corrupted = finiteRows4Stock
    corrupted[corrupted.startIndex] ^= 1
    #expect(corrupted != finiteRows4Stock, "positive corruption control was not detected")
    print("prefill_input_rms_rpg4_positive_corruption_detected=true")
}

@Test
func prefillInputRMSRPG4DeclinesUnsupportedCasesWhenRuntimeTestsAreEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1"
    else { return }

    let weight = repeatedBF16Pattern([0x3f80], rows: 1).reshaped([
        prefillInputRMSRPG4Width
    ])
    for rows in [1, 2, 3, 5, 511, 513] {
        let input = repeatedBF16Pattern([0x3f80], rows: rows)
        #expect(
            lagunaPrefillInputRMSRPG4(
                input, weight: weight, epsilon: prefillInputRMSRPG4Epsilon
            ) == nil,
            "candidate accepted unsupported row count \(rows)"
        )
    }

    let supportedInput = repeatedBF16Pattern([0x3f80], rows: 4)
    #expect(
        lagunaPrefillInputRMSRPG4(
            supportedInput.asType(.float32),
            weight: weight,
            epsilon: prefillInputRMSRPG4Epsilon
        ) == nil
    )
    #expect(
        lagunaPrefillInputRMSRPG4(
            supportedInput,
            weight: weight.asType(.float32),
            epsilon: prefillInputRMSRPG4Epsilon
        ) == nil
    )
    #expect(
        lagunaPrefillInputRMSRPG4(
            supportedInput,
            weight: weight,
            epsilon: prefillInputRMSRPG4Epsilon.nextUp
        ) == nil
    )
    print("prefill_input_rms_rpg4_fallback_rows=1,2,3,5,511,513")
}


private struct PrefillInputRMSRPG4TimingBlock {
    let rawNanoseconds: [UInt64]
    let stockNanoseconds: Double
    let candidateNanoseconds: Double

    var logSpeedup: Double {
        log(stockNanoseconds / candidateNanoseconds)
    }

    var savedNanoseconds: Double {
        stockNanoseconds - candidateNanoseconds
    }
}

private struct PrefillInputRMSRPG4RandomNumberGenerator {
    private var state: UInt64

    init(seed: UInt64) {
        state = seed
    }

    mutating func index(upperBound: Int) -> Int {
        state = state &* 6_364_136_223_846_793_005 &+ 1_442_695_040_888_963_407
        return Int((state >> 16) % UInt64(upperBound))
    }
}

private func prefillInputRMSRPG4Median(_ values: [Double]) -> Double {
    precondition(!values.isEmpty)
    let sorted = values.sorted()
    let middle = sorted.count / 2
    if sorted.count.isMultiple(of: 2) {
        return (sorted[middle - 1] + sorted[middle]) / 2
    }
    return sorted[middle]
}

private func prefillInputRMSRPG4MAD(_ values: [Double]) -> Double {
    let center = prefillInputRMSRPG4Median(values)
    return prefillInputRMSRPG4Median(values.map { abs($0 - center) })
}

private func prefillInputRMSRPG4BootstrapSpeedupCI(
    _ logSpeedups: [Double], seed: UInt64
) -> (lower: Double, upper: Double) {
    let sampleCount = 20_000
    var generator = PrefillInputRMSRPG4RandomNumberGenerator(seed: seed)
    var estimates = [Double]()
    estimates.reserveCapacity(sampleCount)
    for _ in 0..<sampleCount {
        var resample = [Double]()
        resample.reserveCapacity(logSpeedups.count)
        for _ in logSpeedups.indices {
            resample.append(logSpeedups[generator.index(upperBound: logSpeedups.count)])
        }
        estimates.append(exp(prefillInputRMSRPG4Median(resample)))
    }
    estimates.sort()
    return (
        estimates[Int(Double(sampleCount - 1) * 0.025)],
        estimates[Int(Double(sampleCount - 1) * 0.975)]
    )
}

private func prefillInputRMSRPG4ThermalState() -> String {
    switch ProcessInfo.processInfo.thermalState {
    case .nominal: return "nominal"
    case .fair: return "fair"
    case .serious: return "serious"
    case .critical: return "critical"
    @unknown default: return "unknown"
    }
}

private func prefillInputRMSRPG4Sequence(
    input: MLXArray, weights: [MLXArray], candidate: Bool
) -> [MLXArray] {
    weights.map { weight in
        if candidate {
            guard let output = lagunaPrefillInputRMSRPG4(
                input, weight: weight, epsilon: prefillInputRMSRPG4Epsilon
            ) else {
                preconditionFailure("candidate declined benchmark input")
            }
            return output
        }
        return stockInputRMS(input, weight: weight)
    }
}

private func prefillInputRMSRPG4MeasureSequence(
    input: MLXArray, weights: [MLXArray], candidate: Bool
) -> UInt64 {
    let outputs = prefillInputRMSRPG4Sequence(
        input: input, weights: weights, candidate: candidate
    )
    let start = DispatchTime.now().uptimeNanoseconds
    eval(outputs)
    return DispatchTime.now().uptimeNanoseconds - start
}

private func prefillInputRMSRPG4MeasureBlock(
    input: MLXArray, weights: [MLXArray], order: String
) -> PrefillInputRMSRPG4TimingBlock {
    let raw: [UInt64]
    if order == "ABBA" {
        raw = [
            prefillInputRMSRPG4MeasureSequence(input: input, weights: weights, candidate: false),
            prefillInputRMSRPG4MeasureSequence(input: input, weights: weights, candidate: true),
            prefillInputRMSRPG4MeasureSequence(input: input, weights: weights, candidate: true),
            prefillInputRMSRPG4MeasureSequence(input: input, weights: weights, candidate: false),
        ]
        return PrefillInputRMSRPG4TimingBlock(
            rawNanoseconds: raw,
            stockNanoseconds: Double(raw[0] + raw[3]) / 2,
            candidateNanoseconds: Double(raw[1] + raw[2]) / 2
        )
    }
    precondition(order == "BAAB")
    raw = [
        prefillInputRMSRPG4MeasureSequence(input: input, weights: weights, candidate: true),
        prefillInputRMSRPG4MeasureSequence(input: input, weights: weights, candidate: false),
        prefillInputRMSRPG4MeasureSequence(input: input, weights: weights, candidate: false),
        prefillInputRMSRPG4MeasureSequence(input: input, weights: weights, candidate: true),
    ]
    return PrefillInputRMSRPG4TimingBlock(
        rawNanoseconds: raw,
        stockNanoseconds: Double(raw[1] + raw[2]) / 2,
        candidateNanoseconds: Double(raw[0] + raw[3]) / 2
    )
}

private func prefillInputRMSRPG4Report(
    order: String, blocks: [PrefillInputRMSRPG4TimingBlock], seed: UInt64
) -> (speedup: Double, ci: (lower: Double, upper: Double), regressingBlocks: Int) {
    let stock = blocks.map(\.stockNanoseconds)
    let candidate = blocks.map(\.candidateNanoseconds)
    let logSpeedups = blocks.map(\.logSpeedup)
    let speedup = exp(prefillInputRMSRPG4Median(logSpeedups))
    let ci = prefillInputRMSRPG4BootstrapSpeedupCI(logSpeedups, seed: seed)
    let regressingBlocks = logSpeedups.filter { $0 < 0 }.count
    print(
        "prefill_input_rms_rpg4_timing order=\(order) blocks=\(blocks.count) "
            + "samples_per_arm=\(blocks.count * 2) "
            + "stock_median_us=\(prefillInputRMSRPG4Median(stock) / 1_000) "
            + "stock_mad_us=\(prefillInputRMSRPG4MAD(stock) / 1_000) "
            + "candidate_median_us=\(prefillInputRMSRPG4Median(candidate) / 1_000) "
            + "candidate_mad_us=\(prefillInputRMSRPG4MAD(candidate) / 1_000) "
            + "speedup=\(speedup) ci95=[\(ci.lower),\(ci.upper)] "
            + "regressing_blocks=\(regressingBlocks)"
    )
    return (speedup, ci, regressingBlocks)
}

@Suite(.serialized)
struct PrefillInputRMSRPG4BenchmarkTests {
    @Test
    func prefillInputRMSRPG4ABBAAndBAABBenchmark() throws {
        let environment = ProcessInfo.processInfo.environment
        guard environment["MLXFAST_PREFILL_INPUT_RMS_RPG4_BENCHMARK"] == "1" else {
            return
        }
        #expect(environment["DARKBLOOM_PREFILL_INPUT_RMS_RPG4"] == "1")
        let fullPrefillWallSeconds = try #require(
            Double(environment["MLXFAST_PREFILL_BASELINE_SECONDS"] ?? "")
        )

        let store = try DenseTensorStore(weightsPath: "weights")
        let bridge = MLXArrayTensorBridge()
        let weights = try (0..<40).map { layer in
            try bridge.makeArray(
                from: store.materializedTensor(
                    named: "model.layers.\(layer).input_layernorm.weight"
                )
            )
        }
        #expect(weights.allSatisfy { $0.dtype == .bfloat16 && $0.shape == [2048] })

        let input = repeatedBF16Pattern(
            [
                0x0000, 0x8000, 0x3f80, 0xbf80, 0x3f00, 0xbf00, 0x4000, 0xc000,
                0x3e80, 0xbe80, 0x4040, 0xc040, 0x3d00, 0xbd00, 0x3fc0, 0xbfc0,
            ],
            rows: 512
        )
        eval([input] + weights)
        for (layer, weight) in weights.enumerated() {
            _ = try requireExactInputRMSMatch(
                input: input, weight: weight, label: "timing_layer_\(layer)"
            )
        }

        _ = prefillInputRMSRPG4MeasureSequence(
            input: input, weights: weights, candidate: false
        )
        _ = prefillInputRMSRPG4MeasureSequence(
            input: input, weights: weights, candidate: true
        )
        for _ in 0..<8 {
            _ = prefillInputRMSRPG4MeasureBlock(input: input, weights: weights, order: "ABBA")
            _ = prefillInputRMSRPG4MeasureBlock(input: input, weights: weights, order: "BAAB")
        }

        print(
            "prefill_input_rms_rpg4_timing thermal_start="
                + prefillInputRMSRPG4ThermalState()
        )
        var abba = [PrefillInputRMSRPG4TimingBlock]()
        var baab = [PrefillInputRMSRPG4TimingBlock]()
        abba.reserveCapacity(257)
        baab.reserveCapacity(257)
        for index in 0..<257 {
            let abbaBlock = prefillInputRMSRPG4MeasureBlock(
                input: input, weights: weights, order: "ABBA"
            )
            let baabBlock = prefillInputRMSRPG4MeasureBlock(
                input: input, weights: weights, order: "BAAB"
            )
            abba.append(abbaBlock)
            baab.append(baabBlock)
            print(
                "prefill_input_rms_rpg4_raw order=ABBA block=\(index) nanoseconds="
                    + abbaBlock.rawNanoseconds.map { String($0) }.joined(separator: ",")
            )
            print(
                "prefill_input_rms_rpg4_raw order=BAAB block=\(index) nanoseconds="
                    + baabBlock.rawNanoseconds.map { String($0) }.joined(separator: ",")
            )
        }
        print(
            "prefill_input_rms_rpg4_timing thermal_end="
                + prefillInputRMSRPG4ThermalState()
        )

        let abbaReport = prefillInputRMSRPG4Report(
            order: "ABBA", blocks: abba, seed: 0x4142_4241
        )
        let baabReport = prefillInputRMSRPG4Report(
            order: "BAAB", blocks: baab, seed: 0x4241_4142
        )
        let pooledBlocks = abba + baab
        let pooledLogSpeedups = pooledBlocks.map(\.logSpeedup)
        let pooledSpeedup = exp(prefillInputRMSRPG4Median(pooledLogSpeedups))
        let pooledCI = prefillInputRMSRPG4BootstrapSpeedupCI(
            pooledLogSpeedups, seed: 0x5250_4734
        )
        let savedMicroseconds = prefillInputRMSRPG4Median(
            pooledBlocks.map(\.savedNanoseconds)
        ) / 1_000
        let projectedPrefillSpeedup = fullPrefillWallSeconds
            / (fullPrefillWallSeconds - savedMicroseconds / 1_000_000)
        print(
            "prefill_input_rms_rpg4_timing pooled_speedup=\(pooledSpeedup) "
                + "pooled_ci95=[\(pooledCI.lower),\(pooledCI.upper)] "
                + "saved_us_per_40_calls=\(savedMicroseconds) "
                + "full_prefill_wall_s=\(fullPrefillWallSeconds) "
                + "projected_prefill_speedup=\(projectedPrefillSpeedup)"
        )

        #expect(abbaReport.speedup >= 1.005)
        #expect(baabReport.speedup >= 1.005)
        #expect(abbaReport.regressingBlocks == 0)
        #expect(baabReport.regressingBlocks == 0)
        #expect(pooledCI.lower > 1.0)
        #expect(projectedPrefillSpeedup >= 1.001)
    }
}
