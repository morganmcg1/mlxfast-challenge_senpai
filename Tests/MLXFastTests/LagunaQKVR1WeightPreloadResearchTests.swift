import Foundation
import MLX
import MLXFastCore
@testable import MLXFastModel
import Testing

@Suite(.serialized)
struct LagunaQKVR1WeightPreloadResearchTests {
    @Test
    func preloadIsExactAndFasterForBothHeadCounts() throws {
        guard ProcessInfo.processInfo.environment["MLXFAST_RUN_QKVR1_PRELOAD_RESEARCH"] == "1"
        else { return }

        let store = try DenseTensorStore(weightsPath: MLXFastConstants.defaultReferencePath)
        var exactLabels: [String] = []
        var timingResults: [[String: Any]] = []

        for specification in [(layer: 0, heads: 48), (layer: 1, heads: 64)] {
            let actual = try makeActualInput(
                store: store,
                layer: specification.layer,
                heads: specification.heads
            )
            let random = makeSyntheticInput(
                label: "random-h\(specification.heads)",
                heads: specification.heads,
                seed: UInt64(0x5a17 + specification.heads),
                adversarial: false
            )
            let adversarial = makeSyntheticInput(
                label: "adversarial-h\(specification.heads)",
                heads: specification.heads,
                seed: UInt64(0xa55a + specification.heads),
                adversarial: true
            )

            for input in [actual, random, adversarial] {
                try expectExact(input)
                exactLabels.append(input.label)
            }
            timingResults.append(try measure(actual))
        }

        let report: [String: Any] = [
            "exact_cases": exactLabels,
            "timing": timingResults,
            "host": "M4 Pro",
        ]
        let data = try JSONSerialization.data(withJSONObject: report, options: [.sortedKeys])
        print("QKVR1_PRELOAD_RESULT \(String(decoding: data, as: UTF8.self))")

        for result in timingResults {
            let abSpeedup = try #require(result["ab_geometric_speedup"] as? Double)
            let baSpeedup = try #require(result["ba_geometric_speedup"] as? Double)
            let geometricSpeedup = try #require(result["geometric_speedup"] as? Double)
            let ciLower = try #require(result["ci95_lower"] as? Double)
            let logGain = try #require(result["log_gain"] as? Double)
            let noise = try #require(result["measured_noise"] as? Double)
            #expect(abSpeedup >= 1.0)
            #expect(baSpeedup >= 1.0)
            #expect(geometricSpeedup >= 1.003)
            #expect(ciLower > 1.0 || logGain > 2 * noise)
        }
    }
}

private struct QKVR1ResearchInput {
    let label: String
    let heads: Int
    let normalized: MLXArray
    let packedCodes: MLXArray
    let scales: MLXArray
}

private struct QKVR1LCG {
    var state: UInt64

    mutating func next() -> UInt64 {
        state = state &* 6_364_136_223_846_793_005 &+ 1_442_695_040_888_963_407
        return state
    }
}

private func makeActualInput(
    store: DenseTensorStore,
    layer: Int,
    heads: Int
) throws -> QKVR1ResearchInput {
    let bridge = MLXArrayTensorBridge()
    var banks: [LagunaNativeAffineWeight] = []
    for suffix in ["q_proj.weight", "k_proj.weight", "v_proj.weight"] {
        let tensor = try store.materializedTensor(
            named: LagunaWeightNames.attention(layer, suffix)
        )
        let weight = try bridge.makeArray(from: tensor)
        banks.append(try #require(lagunaNativeAffineWeight(weight, layer: layer)))
    }
    let normalized = makeNormalized(seed: UInt64(0xc001 + heads), adversarial: false)
    return QKVR1ResearchInput(
        label: "checkpoint-layer\(layer)-h\(heads)",
        heads: heads,
        normalized: normalized,
        packedCodes: concatenated(banks.map(\.packedCodes), axis: 0),
        scales: concatenated(banks.map(\.scales), axis: 0)
    )
}

private func makeSyntheticInput(
    label: String,
    heads: Int,
    seed: UInt64,
    adversarial: Bool
) -> QKVR1ResearchInput {
    let rows = (heads + 16) * 128
    let codeCount = rows * 256
    let scaleCount = rows * 128
    let codePatterns: [UInt32] = [
        0x0000_0000, 0xffff_ffff, 0x0123_4567, 0x89ab_cdef,
        0x1111_1111, 0xeeee_eeee, 0x5a5a_a5a5, 0x8000_0001,
    ]
    let scalePatterns: [UInt8] = [0x00, 0x20, 0x38, 0x40, 0x58, 0x77]
    var generator = QKVR1LCG(state: seed)
    var codes = [UInt32]()
    codes.reserveCapacity(codeCount)
    for index in 0..<codeCount {
        codes.append(adversarial ? codePatterns[index % codePatterns.count] : UInt32(truncatingIfNeeded: generator.next()))
    }
    var scales = [UInt8]()
    scales.reserveCapacity(scaleCount)
    for index in 0..<scaleCount {
        let selector = adversarial ? index : Int(generator.next() % UInt64(scalePatterns.count))
        scales.append(scalePatterns[selector % scalePatterns.count])
    }
    return QKVR1ResearchInput(
        label: label,
        heads: heads,
        normalized: makeNormalized(seed: seed ^ 0x9e37_79b9, adversarial: adversarial),
        packedCodes: MLXArray(codes).reshaped([rows, 256]),
        scales: MLXArray(scales).reshaped([rows, 128])
    )
}

private func makeNormalized(seed: UInt64, adversarial: Bool) -> MLXArray {
    let patterns: [Float] = [
        0, -0.0, 1, -1, 0.5, -0.5, 7.9375, -7.9375,
        0.0078125, -0.0078125, 31, -31, 0.125, -0.125, 2, -2,
    ]
    var generator = QKVR1LCG(state: seed)
    var values = [Float]()
    values.reserveCapacity(2_048)
    for index in 0..<2_048 {
        if adversarial {
            values.append(patterns[index % patterns.count])
        } else {
            let centered = Int(generator.next() >> 56) - 128
            values.append(Float(centered) / 32)
        }
    }
    return MLXArray(values).reshaped([1, 1, 2_048]).asType(.bfloat16)
}

private func launch(_ input: QKVR1ResearchInput, candidate: Bool) throws -> MLXArray {
    try #require(lagunaDecodeNVFP4QKVR1Research(
        normalized: input.normalized,
        packedCodes: input.packedCodes,
        scales: input.scales,
        heads: input.heads,
        candidate: candidate
    ))
}

private func expectExact(_ input: QKVR1ResearchInput) throws {
    let baseline = try launch(input, candidate: false)
    let candidate = try launch(input, candidate: true)
    let baselineData = baseline.asData(access: .copy)
    let candidateData = candidate.asData(access: .copy)
    #expect(baseline.dtype == .bfloat16)
    #expect(candidate.dtype == .bfloat16)
    #expect(baseline.shape == candidate.shape)
    #expect(baselineData.data == candidateData.data)
}

private func measure(_ input: QKVR1ResearchInput) throws -> [String: Any] {
    let launchesPerSample = 64
    eval(input.normalized, input.packedCodes, input.scales)
    Stream.gpu.synchronize()

    for _ in 0..<3 {
        _ = try measureBlock(input, candidate: false, launches: launchesPerSample)
        _ = try measureBlock(input, candidate: true, launches: launchesPerSample)
    }

    var abBaseline: [Double] = []
    var abCandidate: [Double] = []
    var baBaseline: [Double] = []
    var baCandidate: [Double] = []
    for _ in 0..<20 {
        abBaseline.append(try measureBlock(input, candidate: false, launches: launchesPerSample))
        abCandidate.append(try measureBlock(input, candidate: true, launches: launchesPerSample))
    }
    for _ in 0..<20 {
        baCandidate.append(try measureBlock(input, candidate: true, launches: launchesPerSample))
        baBaseline.append(try measureBlock(input, candidate: false, launches: launchesPerSample))
    }

    let abRatios = zip(abBaseline, abCandidate).map { $0.0 / $0.1 }
    let baRatios = zip(baBaseline, baCandidate).map { $0.0 / $0.1 }
    let logRatios = (abRatios + baRatios).map(log)
    let logGain = mean(logRatios)
    let standardDeviation = sampleStandardDeviation(logRatios, mean: logGain)
    let measuredNoise = standardDeviation / sqrt(Double(logRatios.count))
    let ci95Lower = exp(logGain - 2.023 * measuredNoise)

    return [
        "heads": input.heads,
        "rows": (input.heads + 16) * 128,
        "warmup_blocks_per_arm": 3,
        "paired_samples_per_order": 20,
        "launches_per_sample": launchesPerSample,
        "ab_baseline_seconds": abBaseline,
        "ab_candidate_seconds": abCandidate,
        "ba_baseline_seconds": baBaseline,
        "ba_candidate_seconds": baCandidate,
        "ab_geometric_speedup": geometricMean(abRatios),
        "ba_geometric_speedup": geometricMean(baRatios),
        "geometric_speedup": exp(logGain),
        "ci95_lower": ci95Lower,
        "log_gain": logGain,
        "measured_noise": measuredNoise,
    ]
}

private func measureBlock(
    _ input: QKVR1ResearchInput,
    candidate: Bool,
    launches: Int
) throws -> Double {
    let start = Date.timeIntervalSinceReferenceDate
    var outputs: [MLXArray] = []
    outputs.reserveCapacity(launches)
    for _ in 0..<launches {
        outputs.append(try launch(input, candidate: candidate))
    }
    eval(outputs)
    Stream.gpu.synchronize()
    return Date.timeIntervalSinceReferenceDate - start
}

private func mean(_ values: [Double]) -> Double {
    values.reduce(0, +) / Double(values.count)
}

private func geometricMean(_ values: [Double]) -> Double {
    exp(mean(values.map(log)))
}

private func sampleStandardDeviation(_ values: [Double], mean: Double) -> Double {
    let squared = values.reduce(0) { $0 + ($1 - mean) * ($1 - mean) }
    return sqrt(squared / Double(values.count - 1))
}
