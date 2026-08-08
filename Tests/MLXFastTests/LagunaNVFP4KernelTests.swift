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
func qkvr1VectorLoadsExactnessAndIsolatedTimingWhenExperimentIsEnabled() throws {
    guard ProcessInfo.processInfo.environment["MLXFAST_QKVR1_VECTOR_EXPERIMENT"] == "1" else {
        return
    }

    let weightsPath = ProcessInfo.processInfo.environment["MLXFAST_WEIGHTS_PATH"]
        ?? FileManager.default.currentDirectoryPath + "/weights"
    let store = try DenseTensorStore(weightsPath: weightsPath)
    let bridge = MLXArrayTensorBridge()
    for specification in [
        QKVR1Specification(heads: 48, layer: 0, rows: 8_192),
        QKVR1Specification(heads: 64, layer: 1, rows: 10_240),
    ] {
        let checkpoint = try makeQKVR1CheckpointInputs(
            store: store,
            bridge: bridge,
            specification: specification
        )
        verifyQKVR1Exactness(
            label: "checkpoint",
            normalized: checkpoint.normalized,
            weightCodes: checkpoint.weightCodes,
            weightScales: checkpoint.weightScales,
            specification: specification
        )

        let supportedScaleBytes = Array(Set(checkpoint.weightScales.asArray(UInt8.self))).sorted()
        #expect(!supportedScaleBytes.isEmpty)

        var randomGenerator = QKVR1Generator(
            state: UInt64(0x45d9_f3b1) ^ UInt64(specification.heads)
        )
        let randomNormalizedBits = makeRandomBF16Bits(generator: &randomGenerator)
        let randomCodes = (0..<(specification.rows * 256)).map { _ in
            UInt32(truncatingIfNeeded: randomGenerator.next())
        }
        let randomScales = (0..<(specification.rows * 128)).map { _ in
            supportedScaleBytes[Int(randomGenerator.next() % UInt64(supportedScaleBytes.count))]
        }
        verifyQKVR1Exactness(
            label: "random",
            normalized: makeBF16Array(bits: randomNormalizedBits),
            weightCodes: MLXArray(randomCodes, [specification.rows, 256]),
            weightScales: MLXArray(randomScales, [specification.rows, 128]),
            specification: specification
        )

        let adversarialBits = makeAdversarialBF16Bits()
        let codePatterns: [UInt32] = [
            0x0000_0000, 0x8888_8888, 0x7777_7777, 0xffff_ffff,
            0x7654_3210, 0xfedc_ba98, 0x1357_9bdf, 0xeca8_6420,
        ]
        let adversarialCodes = (0..<(specification.rows * 256)).map {
            codePatterns[$0 % codePatterns.count]
        }
        let adversarialScales = (0..<(specification.rows * 128)).map {
            supportedScaleBytes[($0 * 7 + $0 / 128) % supportedScaleBytes.count]
        }
        let adversarialNormalized = makeBF16Array(bits: adversarialBits)
        verifyQKVR1Exactness(
            label: "adversarial",
            normalized: adversarialNormalized,
            weightCodes: MLXArray(adversarialCodes, [specification.rows, 256]),
            weightScales: MLXArray(adversarialScales, [specification.rows, 128]),
            specification: specification
        )

        let alignedProbe = lagunaQKVR1NormalizedAlignmentForTesting(adversarialNormalized)
        let padded = MLXArray([UInt16(0x3f80)] + adversarialBits, [2_049])
            .view(dtype: .bfloat16)
        let misalignedNormalized = padded[1...].reshaped([1, 1, 2_048])
        let misalignedProbe = lagunaQKVR1NormalizedAlignmentForTesting(misalignedNormalized)
        eval([alignedProbe, misalignedProbe])
        #expect(alignedProbe.asArray(UInt32.self) == [1])
        #expect(misalignedProbe.asArray(UInt32.self) == [0])
        verifyQKVR1Exactness(
            label: "misaligned-fallback",
            normalized: misalignedNormalized,
            weightCodes: checkpoint.weightCodes,
            weightScales: checkpoint.weightScales,
            specification: specification
        )

        let timing = measureQKVR1PairedTiming(
            normalized: checkpoint.normalized,
            weightCodes: checkpoint.weightCodes,
            weightScales: checkpoint.weightScales,
            specification: specification
        )
        reportQKVR1Timing(timing, specification: specification)
        let passesTimingGate = timing.combinedSpeedup >= 1.003
            && timing.abSpeedup >= 1.0
            && timing.baSpeedup >= 1.0
            && (timing.bootstrapLower > 1.0
                || log(timing.combinedSpeedup) > 2 * timing.logRatioMAD)
        #expect(
            passesTimingGate,
            Comment(rawValue: "H\(specification.heads) isolated vector-load gate failed")
        )
    }
}

private struct QKVR1Specification {
    let heads: Int
    let layer: Int
    let rows: Int
}

private struct QKVR1Inputs {
    let normalized: MLXArray
    let weightCodes: MLXArray
    let weightScales: MLXArray
}

private func makeQKVR1CheckpointInputs(
    store: DenseTensorStore,
    bridge: MLXArrayTensorBridge,
    specification: QKVR1Specification
) throws -> QKVR1Inputs {
    func load(_ projection: String) throws -> MLXArray {
        try bridge.makeArray(
            from: store.materializedTensor(
                named: "model.layers.\(specification.layer).self_attn.\(projection)_proj.weight"
            )
        )
    }

    let query = try load("q")
    let key = try load("k")
    let value = try load("v")
    let fused = concatenated([query, key, value], axis: 0)
    let (weightCodes, weightScales, _) = quantized(
        fused,
        groupSize: 16,
        bits: 4,
        mode: .nvfp4
    )
    let normalized = query[0].reshaped([1, 1, 2_048])
    eval([normalized, weightCodes, weightScales])
    #expect(weightCodes.shape == [specification.rows, 256])
    #expect(weightScales.shape == [specification.rows, 128])
    return QKVR1Inputs(
        normalized: normalized,
        weightCodes: weightCodes,
        weightScales: weightScales
    )
}

private func verifyQKVR1Exactness(
    label: String,
    normalized: MLXArray,
    weightCodes: MLXArray,
    weightScales: MLXArray,
    specification: QKVR1Specification
) {
    let scalar = lagunaDecodeNVFP4QKVR1ForTesting(
        normalized: normalized,
        weightCodes: weightCodes,
        weightScales: weightScales,
        heads: specification.heads,
        vectorLoads: false
    )
    let vector = lagunaDecodeNVFP4QKVR1ForTesting(
        normalized: normalized,
        weightCodes: weightCodes,
        weightScales: weightScales,
        heads: specification.heads,
        vectorLoads: true
    )
    eval([scalar, vector])
    let scalarBits = scalar.view(dtype: .uint16).asArray(UInt16.self)
    let vectorBits = vector.view(dtype: .uint16).asArray(UInt16.self)
    #expect(scalarBits.count == specification.rows)
    #expect(
        scalarBits == vectorBits,
        Comment(rawValue: "H\(specification.heads) \(label) raw BF16 mismatch")
    )

    var corruptedBits = vectorBits
    corruptedBits[corruptedBits.count / 2] ^= 1
    let detectedDifferences = zip(scalarBits, corruptedBits).filter { $0.0 != $0.1 }.count
    #expect(
        detectedDifferences == 1,
        Comment(rawValue: "H\(specification.heads) \(label) corruption control failed")
    )
    print(
        "QKVR1_EXACT heads=\(specification.heads) case=\(label) "
            + "rows=\(scalarBits.count) raw_bf16_equal=true corruption_detected=true"
    )
}

private func makeBF16Array(bits: [UInt16]) -> MLXArray {
    MLXArray(bits, [1, 1, 2_048]).view(dtype: .bfloat16)
}

private func makeRandomBF16Bits(generator: inout QKVR1Generator) -> [UInt16] {
    (0..<2_048).map { _ in
        var bits = UInt16(truncatingIfNeeded: generator.next())
        if bits & 0x7f80 == 0x7f80 {
            bits ^= 0x0080
        }
        return bits
    }
}

private func makeAdversarialBF16Bits() -> [UInt16] {
    let patterns: [UInt16] = [
        0x0000, 0x8000, 0x0001, 0x8001,
        0x007f, 0x807f, 0x0080, 0x8080,
        0x3f80, 0xbf80, 0x7f7f, 0xff7f,
        0x3eaa, 0xbeaa, 0x4000, 0xc000,
    ]
    var bits = (0..<2_048).map { patterns[($0 * 11 + $0 / 17) % patterns.count] }
    let laneOffsets = [0, 1, 2, 3, 12, 13, 14, 15, 496, 497, 498, 499, 508, 509, 510, 511]
    for block in 0..<4 {
        for (index, offset) in laneOffsets.enumerated() {
            bits[block * 512 + offset] = patterns[(block * laneOffsets.count + index) % patterns.count]
        }
    }
    return bits
}

private struct QKVR1Generator {
    var state: UInt64

    mutating func next() -> UInt64 {
        state ^= state << 13
        state ^= state >> 7
        state ^= state << 17
        return state
    }
}

private struct QKVR1Timing {
    let repetitions: Int
    let abScalar: [Double]
    let abVector: [Double]
    let baScalar: [Double]
    let baVector: [Double]
    let abSpeedup: Double
    let baSpeedup: Double
    let combinedSpeedup: Double
    let logRatioMAD: Double
    let bootstrapLower: Double
    let bootstrapUpper: Double
}

private func measureQKVR1PairedTiming(
    normalized: MLXArray,
    weightCodes: MLXArray,
    weightScales: MLXArray,
    specification: QKVR1Specification
) -> QKVR1Timing {
    for _ in 0..<8 {
        eval(lagunaDecodeNVFP4QKVR1ForTesting(
            normalized: normalized,
            weightCodes: weightCodes,
            weightScales: weightScales,
            heads: specification.heads,
            vectorLoads: false
        ))
        eval(lagunaDecodeNVFP4QKVR1ForTesting(
            normalized: normalized,
            weightCodes: weightCodes,
            weightScales: weightScales,
            heads: specification.heads,
            vectorLoads: true
        ))
    }

    let repetitions = 32
    var abScalar: [Double] = []
    var abVector: [Double] = []
    var baScalar: [Double] = []
    var baVector: [Double] = []
    for _ in 0..<30 {
        abScalar.append(measureQKVR1Batch(
            normalized: normalized,
            weightCodes: weightCodes,
            weightScales: weightScales,
            heads: specification.heads,
            vectorLoads: false,
            repetitions: repetitions
        ))
        abVector.append(measureQKVR1Batch(
            normalized: normalized,
            weightCodes: weightCodes,
            weightScales: weightScales,
            heads: specification.heads,
            vectorLoads: true,
            repetitions: repetitions
        ))
        baVector.append(measureQKVR1Batch(
            normalized: normalized,
            weightCodes: weightCodes,
            weightScales: weightScales,
            heads: specification.heads,
            vectorLoads: true,
            repetitions: repetitions
        ))
        baScalar.append(measureQKVR1Batch(
            normalized: normalized,
            weightCodes: weightCodes,
            weightScales: weightScales,
            heads: specification.heads,
            vectorLoads: false,
            repetitions: repetitions
        ))
    }

    let abRatios = zip(abScalar, abVector).map { $0.0 / $0.1 }
    let baRatios = zip(baScalar, baVector).map { $0.0 / $0.1 }
    let ratios = abRatios + baRatios
    let logRatios = ratios.map { log($0) }
    let medianLogRatio = qkvr1Median(logRatios)
    let logRatioMAD = qkvr1Median(logRatios.map { abs($0 - medianLogRatio) })
    let bootstrap = qkvr1BootstrapInterval(logRatios)
    return QKVR1Timing(
        repetitions: repetitions,
        abScalar: abScalar,
        abVector: abVector,
        baScalar: baScalar,
        baVector: baVector,
        abSpeedup: qkvr1GeometricMean(abRatios),
        baSpeedup: qkvr1GeometricMean(baRatios),
        combinedSpeedup: qkvr1GeometricMean(ratios),
        logRatioMAD: logRatioMAD,
        bootstrapLower: bootstrap.lower,
        bootstrapUpper: bootstrap.upper
    )
}

private func measureQKVR1Batch(
    normalized: MLXArray,
    weightCodes: MLXArray,
    weightScales: MLXArray,
    heads: Int,
    vectorLoads: Bool,
    repetitions: Int
) -> Double {
    let outputs = (0..<repetitions).map { _ in
        lagunaDecodeNVFP4QKVR1ForTesting(
            normalized: normalized,
            weightCodes: weightCodes,
            weightScales: weightScales,
            heads: heads,
            vectorLoads: vectorLoads
        )
    }
    let start = DispatchTime.now().uptimeNanoseconds
    eval(outputs)
    let elapsed = DispatchTime.now().uptimeNanoseconds - start
    return Double(elapsed) / Double(repetitions)
}

private func reportQKVR1Timing(
    _ timing: QKVR1Timing,
    specification: QKVR1Specification
) {
    let abRatios = zip(timing.abScalar, timing.abVector).map { $0.0 / $0.1 }
    let baRatios = zip(timing.baScalar, timing.baVector).map { $0.0 / $0.1 }
    print(
        "QKVR1_TIMING heads=\(specification.heads) samples_per_order=30 "
            + "repetitions=\(timing.repetitions) "
            + "ab_scalar_sum_ns=\(timing.abScalar.reduce(0, +)) "
            + "ab_vector_sum_ns=\(timing.abVector.reduce(0, +)) "
            + "ba_scalar_sum_ns=\(timing.baScalar.reduce(0, +)) "
            + "ba_vector_sum_ns=\(timing.baVector.reduce(0, +)) "
            + "ab_scalar_median_ns=\(qkvr1Median(timing.abScalar)) "
            + "ab_vector_median_ns=\(qkvr1Median(timing.abVector)) "
            + "ba_scalar_median_ns=\(qkvr1Median(timing.baScalar)) "
            + "ba_vector_median_ns=\(qkvr1Median(timing.baVector)) "
            + "ab_ratio_nmad=\(qkvr1NormalizedMAD(abRatios)) "
            + "ba_ratio_nmad=\(qkvr1NormalizedMAD(baRatios)) "
            + "ab_speedup=\(timing.abSpeedup) ba_speedup=\(timing.baSpeedup) "
            + "combined_speedup=\(timing.combinedSpeedup) "
            + "log_ratio_mad=\(timing.logRatioMAD) "
            + "bootstrap95=[\(timing.bootstrapLower),\(timing.bootstrapUpper)]"
    )
    print("QKVR1_AB_SCALAR_NS heads=\(specification.heads) \(timing.abScalar)")
    print("QKVR1_AB_VECTOR_NS heads=\(specification.heads) \(timing.abVector)")
    print("QKVR1_AB_SPEEDUPS heads=\(specification.heads) \(abRatios)")
    print("QKVR1_BA_VECTOR_NS heads=\(specification.heads) \(timing.baVector)")
    print("QKVR1_BA_SCALAR_NS heads=\(specification.heads) \(timing.baScalar)")
    print("QKVR1_BA_SPEEDUPS heads=\(specification.heads) \(baRatios)")
}

private func qkvr1Median(_ values: [Double]) -> Double {
    let sorted = values.sorted()
    let middle = sorted.count / 2
    if sorted.count.isMultiple(of: 2) {
        return (sorted[middle - 1] + sorted[middle]) / 2
    }
    return sorted[middle]
}

private func qkvr1GeometricMean(_ values: [Double]) -> Double {
    exp(values.map { log($0) }.reduce(0, +) / Double(values.count))
}

private func qkvr1NormalizedMAD(_ values: [Double]) -> Double {
    let sampleMedian = qkvr1Median(values)
    return qkvr1Median(values.map { abs($0 - sampleMedian) }) / sampleMedian
}

private func qkvr1BootstrapInterval(_ logRatios: [Double]) -> (lower: Double, upper: Double) {
    var generator = QKVR1Generator(state: 0x9e37_79b9_7f4a_7c15)
    var means: [Double] = []
    means.reserveCapacity(10_000)
    for _ in 0..<10_000 {
        var sum = 0.0
        for _ in logRatios.indices {
            let index = Int(generator.next() % UInt64(logRatios.count))
            sum += logRatios[index]
        }
        means.append(sum / Double(logRatios.count))
    }
    means.sort()
    return (exp(means[250]), exp(means[9_749]))
}
