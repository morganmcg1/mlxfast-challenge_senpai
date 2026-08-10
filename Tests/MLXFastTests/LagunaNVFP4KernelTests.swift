import Foundation
import MLX
import MLXLMCommon
import MLXNN
import Testing
@testable import MLXFastModel

@Test
func nvfp4Group16SplitKMatmulMatchesDequantizedReferenceWhenRuntimeTestsAreEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
        return
    }

    // M=32, N=128, K=64 enters qmm_splitk. With group size 16 the old
    // dispatch selected four K=16 partitions even though the Metal kernel
    // consumes K in 32-wide tiles, over-reading every partition.
    let input = MLXArray(Array(repeating: Float(1), count: 32 * 64), [32, 64])
    let weight = MLXArray(Array(repeating: Float(1), count: 128 * 64), [128, 64])
    let (packedWeight, scales, biases) = quantized(
        weight,
        groupSize: 16,
        bits: 4,
        mode: .nvfp4
    )

    let actual = quantizedMM(
        input,
        packedWeight,
        scales: scales,
        biases: biases,
        transpose: true,
        groupSize: 16,
        bits: 4,
        mode: .nvfp4
    )
    let referenceWeight = dequantized(
        packedWeight,
        scales: scales,
        biases: biases,
        groupSize: 16,
        bits: 4,
        mode: .nvfp4,
        dtype: .float32
    )
    let reference = matmul(input, referenceWeight.T)
    eval(actual, reference)

    let actualValues = actual.asArray(Float.self)
    let referenceValues = reference.asArray(Float.self)
    #expect(actualValues.allSatisfy { $0.isFinite })
    #expect(referenceValues.allSatisfy { $0.isFinite })
    let maximumError = zip(actualValues, referenceValues)
        .map { abs($0 - $1) }
        .max() ?? .infinity
    #expect(maximumError <= 1e-4)
}

@Test
func nvfp4NibbleOrderAndE4M3ScaleBytesMatchMLXContractWhenRuntimeTestsAreEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
        return
    }

    // U32 packs eight FP4 values least-significant nibble first. E2M1 codes
    // 0...7 decode as 0, .5, 1, 1.5, 2, 3, 4, 6 and bit 3 is the sign.
    // E4M3 scale bytes 0x38 and 0x40 decode as 1 and 2 respectively.
    let packed = MLXArray(
        [
            UInt32(0x7654_3210), UInt32(0xfedc_ba98),
            UInt32(0x7654_3210), UInt32(0xfedc_ba98),
        ],
        [2, 2]
    )
    let scales = MLXArray([UInt8(0x38), UInt8(0x40)], [2, 1])
    let unpacked = dequantized(
        packed,
        scales: scales,
        biases: nil,
        groupSize: 16,
        bits: 4,
        mode: .nvfp4,
        dtype: .float32
    )
    eval(unpacked)

    let base: [Float] = [
        0, 0.5, 1, 1.5, 2, 3, 4, 6,
        -0, -0.5, -1, -1.5, -2, -3, -4, -6,
    ]
    #expect(unpacked.shape == [2, 16])
    #expect(unpacked.asArray(Float.self) == base + base.map { $0 * 2 })
}

@Test
func nvfp4ActualSharedExpertQMMShapesCoverDecodeAndSplitKPrefillWhenRuntimeTestsAreEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
        return
    }

    // gate/up: [512, 2048] logical, down: [2048, 512] logical.
    for (label, outputFeatures, inputFeatures) in [
        ("shared-gate-up", 512, 2_048),
        ("shared-down", 2_048, 512),
    ] {
        let weight = MLXArray.full(
            [outputFeatures, inputFeatures],
            values: MLXArray(Float(0.5)),
            dtype: .float32
        )
        let (packedWeight, scales, biases) = quantized(
            weight,
            groupSize: 16,
            bits: 4,
            mode: .nvfp4
        )
        let referenceWeight = dequantized(
            packedWeight,
            scales: scales,
            biases: biases,
            groupSize: 16,
            bits: 4,
            mode: .nvfp4,
            dtype: .float32
        )

        for tokenRows in [1, 32] {
            let input = MLXArray.full(
                [tokenRows, inputFeatures],
                values: MLXArray(Float(1)),
                dtype: .float32
            )
            let actual = quantizedMM(
                input,
                packedWeight,
                scales: scales,
                biases: biases,
                transpose: true,
                groupSize: 16,
                bits: 4,
                mode: .nvfp4
            )
            let reference = matmul(input, referenceWeight.T)
            expectFiniteClose(
                actual,
                reference,
                tolerance: 1e-4,
                label: "\(label)-M\(tokenRows)"
            )
        }
    }
}

@Test
func nvfp4ActualRoutedGatherShapesCoverMultipleExpertsAndPrefillWhenRuntimeTestsAreEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
        return
    }

    // gate/up logical [256, 512, 2048], down logical [256, 2048, 512].
    for (label, outputFeatures, inputFeatures) in [
        ("routed-gate-up", 512, 2_048),
        ("routed-down", 2_048, 512),
    ] {
        verifyActualRoutedGather(
            label: label,
            outputFeatures: outputFeatures,
            inputFeatures: inputFeatures,
            tokenCounts: [1, 8]
        )
    }
}

@Test
func quantizedSwitchLinearForwardsNVFP4GatherSemanticsWhenRuntimeTestsAreEnabled() throws {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
        return
    }

    let dense = SwitchLinear(
        inputDims: 64,
        outputDims: 32,
        numExperts: 4,
        bias: false
    )
    let layer = QuantizedSwitchLinear(
        dense,
        groupSize: 16,
        bits: 4,
        mode: .nvfp4
    )
    let input = MLXArray.full(
        [1, 2, 64],
        values: MLXArray(Float(0.25)),
        dtype: .float32
    )
    let expandedInput = expandedDimensions(input, axes: [-2, -3])
    let indices = MLXArray([Int32(0), 3, 2, 1], [1, 2, 2])
    let actual = layer(expandedInput, indices)

    let parameters = Dictionary(uniqueKeysWithValues: layer.parameters().flattened())
    let packedWeight = try #require(parameters["weight"])
    let scales = try #require(parameters["scales"])
    let referenceWeight = dequantized(
        packedWeight,
        scales: scales,
        biases: parameters["biases"],
        groupSize: 16,
        bits: 4,
        mode: .nvfp4,
        dtype: .float32
    )
    let reference = gatherMM(
        expandedInput,
        referenceWeight.swappedAxes(-1, -2),
        rhsIndices: indices
    )
    expectFiniteClose(
        actual,
        reference,
        tolerance: 1e-4,
        label: "QuantizedSwitchLinear"
    )
}

private func verifyActualRoutedGather(
    label: String,
    outputFeatures: Int,
    inputFeatures: Int,
    tokenCounts: [Int]
) {
    let expertCount = 256
    let topK = 8
    let packedWidth = inputFeatures * 4 / 32
    let scaleWidth = inputFeatures / 16

    // Give every expert a distinct constant E2M1 code. Broadcasting then
    // materializing this compact seed avoids a giant Swift-side payload while
    // still proving rhs expert indexing, including expert 255.
    let expertPackedCodes = (0..<expertCount).map { expert -> UInt32 in
        UInt32((expert % 7) + 1) &* UInt32(0x1111_1111)
    }
    let packedSeed = MLXArray(expertPackedCodes, [expertCount, 1, 1])
    let packedWeight = contiguous(
        broadcast(
            packedSeed,
            to: [expertCount, outputFeatures, packedWidth]
        )
    )
    let scales = MLXArray.full(
        [expertCount, outputFeatures, scaleWidth],
        values: MLXArray(UInt8(0x38)),
        dtype: .uint8
    )
    let selectedExpertIDs: [Int32] = [0, 7, 42, 255, 3, 128, 17, 99]
    let uniqueIDs = MLXArray(selectedExpertIDs)
    let selectedPacked = take(packedWeight, uniqueIDs, axis: 0)
    let selectedScales = take(scales, uniqueIDs, axis: 0)
    let selectedReferenceWeight = dequantized(
        selectedPacked,
        scales: selectedScales,
        biases: nil,
        groupSize: 16,
        bits: 4,
        mode: .nvfp4,
        dtype: .float32
    )

    for tokenCount in tokenCounts {
        let input = MLXArray.full(
            [1, tokenCount, inputFeatures],
            values: MLXArray(Float(0.25)),
            dtype: .float32
        )
        let expandedInput = expandedDimensions(input, axes: [-2, -3])
        let flattenedIDs = (0..<tokenCount).flatMap { _ in selectedExpertIDs }
        let rhsIndices = MLXArray(flattenedIDs, [1, tokenCount, topK])
        let actual = gatherQuantizedMM(
            expandedInput,
            packedWeight,
            scales: scales,
            biases: nil,
            rhsIndices: rhsIndices,
            transpose: true,
            groupSize: 16,
            bits: 4,
            mode: .nvfp4
        )
        let localIDs = MLXArray(
            (0..<tokenCount).flatMap { _ in (0..<topK).map(Int32.init) },
            [1, tokenCount, topK]
        )
        let reference = gatherMM(
            expandedInput,
            selectedReferenceWeight.swappedAxes(-1, -2),
            rhsIndices: localIDs
        )
        expectFiniteClose(
            actual,
            reference,
            tolerance: 1e-4,
            label: "\(label)-tokens\(tokenCount)"
        )
    }
}

private func expectFiniteClose(
    _ actual: MLXArray,
    _ reference: MLXArray,
    tolerance: Float,
    label: String
) {
    eval(actual, reference)
    let actualValues = actual.asArray(Float.self)
    let referenceValues = reference.asArray(Float.self)
    #expect(actual.shape == reference.shape, Comment(rawValue: label))
    #expect(
        actualValues.allSatisfy { $0.isFinite },
        Comment(rawValue: "\(label) produced non-finite NVFP4 output")
    )
    #expect(
        referenceValues.allSatisfy { $0.isFinite },
        Comment(rawValue: "\(label) produced non-finite reference output")
    )
    let maximumError = zip(actualValues, referenceValues)
        .map { abs($0 - $1) }
        .max() ?? .infinity
    #expect(
        maximumError <= tolerance,
        Comment(rawValue: "\(label) max error \(maximumError) > \(tolerance)")
    )
}

@Test
func terminalPrefillSlidingQKNormRoPEMatchesStockPipelineWhenRuntimeTestsAreEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
        return
    }

    for length in [2, 511, 512, 513] {
        let fixture = TerminalPrefillQKFixture(length: length)
        for offset in [0, 17] {
            let actual = fixture.fused(offset: offset)
            let reference = fixture.stock(offset: offset)
            eval(actual.queries, actual.keys, reference.queries, reference.keys)
            let queryMaximumError = abs(
                actual.queries.asType(.float32) - reference.queries.asType(.float32)
            ).max().item(Float.self)
            let keyMaximumError = abs(
                actual.keys.asType(.float32) - reference.keys.asType(.float32)
            ).max().item(Float.self)
            print(
                "TERMINAL_PREFILL_QK_EXACT length=\(length) offset=\(offset) "
                    + "query_max_abs=\(queryMaximumError) key_max_abs=\(keyMaximumError)"
            )
            #expect(
                queryMaximumError == 0,
                Comment(rawValue: "query mismatch at length=\(length), offset=\(offset)")
            )
            #expect(
                keyMaximumError == 0,
                Comment(rawValue: "key mismatch at length=\(length), offset=\(offset)")
            )
        }
    }
}

@Test
func terminalPrefillSlidingQKNormRoPEIsolatedTimingWhenEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_TERMINAL_PREFILL_QK_TIMING"] == "1" else {
        return
    }

    let fixture = TerminalPrefillQKFixture(length: 512)
    for _ in 0..<16 {
        let stock = fixture.stock(offset: 17)
        eval(stock.queries, stock.keys)
        let fused = fixture.fused(offset: 17)
        eval(fused.queries, fused.keys)
    }

    let abba = measureTerminalPrefillQK(
        fixture: fixture,
        ordering: [.stock, .fused, .fused, .stock],
        cycles: 128
    )
    let baab = measureTerminalPrefillQK(
        fixture: fixture,
        ordering: [.fused, .stock, .stock, .fused],
        cycles: 128
    )

    for (label, result) in [("A-B-B-A", abba), ("B-A-A-B", baab)] {
        let stock = summarizeTerminalPrefillQKSamples(result.stockSamples)
        let fused = summarizeTerminalPrefillQKSamples(result.fusedSamples)
        let speedup = stock.mean / fused.mean
        let medianSpeedup = stock.median / fused.median
        let geometricSpeedup = stock.geometricMean / fused.geometricMean
        let sign = speedup > 1 ? "positive" : "negative"
        print(
            "TERMINAL_PREFILL_QK_TIMING ordering=\(label) repetitions=\(result.repetitions) "
                + "synchronization=eval "
                + "stock_functions=rmsNorm*2+RoPE*2 "
                + "fused_function=laguna_terminal_prefill_sliding_qk_norm_rope_bf16_128_h1_v1 "
                + "stock_total_ns=\(stock.total) fused_total_ns=\(fused.total) "
                + "stock_mean_ns_per_call=\(stock.mean) fused_mean_ns_per_call=\(fused.mean) "
                + "stock_median_ns_per_call=\(stock.median) fused_median_ns_per_call=\(fused.median) "
                + "stock_geomean_ns_per_call=\(stock.geometricMean) "
                + "fused_geomean_ns_per_call=\(fused.geometricMean) "
                + "stock_range_ns=\(stock.minimum)-\(stock.maximum) "
                + "fused_range_ns=\(fused.minimum)-\(fused.maximum) "
                + "speedup=\(speedup) median_speedup=\(medianSpeedup) "
                + "geometric_speedup=\(geometricSpeedup) sign=\(sign)"
        )
        #expect(
            result.repetitions >= 256,
            Comment(rawValue: "\(label) collected too few repetitions")
        )
        #expect(
            speedup >= 1.05,
            Comment(rawValue: "\(label) isolated speedup \(speedup) is below 1.05")
        )
    }
}

private struct TerminalPrefillQKFixture {
    let length: Int
    let rawQueries: MLXArray
    let rawKeys: MLXArray
    let queryWeight: MLXArray
    let keyWeight: MLXArray
    let angles: MLXArray
    let rope: RoPE

    init(length: Int) {
        self.length = length
        self.rawQueries = patternedBF16(count: 64 * 128, period: 251, divisor: 64)
            .reshaped(1, 1, 64 * 128)
        self.rawKeys = patternedBF16(count: length * 8 * 128, period: 241, divisor: 72)
            .reshaped(1, length, 8 * 128)
        self.queryWeight = patternedBF16(count: 128, period: 17, divisor: 128, bias: 1)
        self.keyWeight = patternedBF16(count: 128, period: 19, divisor: 144, bias: 1)
        self.rope = RoPE(dimensions: 128, traditional: false, base: 10_000, scale: 1)
        let seed = MLXArray(
            Array(repeating: Float(1), count: 64) + Array(repeating: Float(0), count: 64),
            [1, 1, 1, 128]
        )
        self.angles = rope(broadcast(seed, to: [1, 1, 4096, 128]), offset: 0)
        eval(rawQueries, rawKeys, queryWeight, keyWeight, angles)
    }

    func stock(offset: Int) -> (queries: MLXArray, keys: MLXArray) {
        let queries = MLXFast.rmsNorm(
            rawQueries.reshaped(1, 1, 64, 128),
            weight: queryWeight,
            eps: 1e-6
        ).transposed(0, 2, 1, 3)
        let keys = MLXFast.rmsNorm(
            rawKeys.reshaped(1, length, 8, 128),
            weight: keyWeight,
            eps: 1e-6
        ).transposed(0, 2, 1, 3)
        return (
            rope(queries, offset: offset + length - 1),
            rope(keys, offset: offset)
        )
    }

    func fused(offset: Int) -> (queries: MLXArray, keys: MLXArray) {
        lagunaTerminalPrefillSlidingQKNormRoPE(
            rawQueries: rawQueries,
            rawKeys: rawKeys,
            queryWeight: queryWeight,
            keyWeight: keyWeight,
            angles: angles,
            offsets: MLXArray([Int32(offset)]),
            length: length
        )
    }
}

private enum TerminalPrefillQKArm {
    case stock
    case fused
}

private struct TerminalPrefillQKTimingResult {
    let stockSamples: [UInt64]
    let fusedSamples: [UInt64]

    var repetitions: Int { stockSamples.count }
}

private struct TerminalPrefillQKTimingSummary {
    let total: UInt64
    let mean: Double
    let median: Double
    let geometricMean: Double
    let minimum: UInt64
    let maximum: UInt64
}

private func measureTerminalPrefillQK(
    fixture: TerminalPrefillQKFixture,
    ordering: [TerminalPrefillQKArm],
    cycles: Int
) -> TerminalPrefillQKTimingResult {
    var stockSamples: [UInt64] = []
    var fusedSamples: [UInt64] = []

    for _ in 0..<cycles {
        for arm in ordering {
            let start = DispatchTime.now().uptimeNanoseconds
            let output = switch arm {
            case .stock: fixture.stock(offset: 17)
            case .fused: fixture.fused(offset: 17)
            }
            eval(output.queries, output.keys)
            let elapsed = DispatchTime.now().uptimeNanoseconds - start
            switch arm {
            case .stock: stockSamples.append(elapsed)
            case .fused: fusedSamples.append(elapsed)
            }
        }
    }

    #expect(stockSamples.count == fusedSamples.count)
    return TerminalPrefillQKTimingResult(
        stockSamples: stockSamples,
        fusedSamples: fusedSamples
    )
}

private func summarizeTerminalPrefillQKSamples(
    _ samples: [UInt64]
) -> TerminalPrefillQKTimingSummary {
    let sorted = samples.sorted()
    let total = samples.reduce(UInt64(0), +)
    let mean = Double(total) / Double(samples.count)
    let middle = samples.count / 2
    let median = samples.count.isMultiple(of: 2)
        ? (Double(sorted[middle - 1]) + Double(sorted[middle])) / 2
        : Double(sorted[middle])
    let geometricMean = Foundation.exp(
        samples.reduce(0.0) { $0 + Foundation.log(Double($1)) }
            / Double(samples.count)
    )
    return TerminalPrefillQKTimingSummary(
        total: total,
        mean: mean,
        median: median,
        geometricMean: geometricMean,
        minimum: sorted[0],
        maximum: sorted[sorted.count - 1]
    )
}

private func patternedBF16(
    count: Int,
    period: Int,
    divisor: Float,
    bias: Float = 0
) -> MLXArray {
    let midpoint = period / 2
    let values = (0..<count).map { bias + Float($0 % period - midpoint) / divisor }
    return MLXArray(values).asType(.bfloat16)
}
