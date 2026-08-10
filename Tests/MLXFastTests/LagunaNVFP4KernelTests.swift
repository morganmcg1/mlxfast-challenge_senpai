import Foundation
import MLX
@testable import MLXFastModel
import MLXLMCommon
import MLXNN
import Testing

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
func lagunaRoutedPackedTop8MatchesCanonicalPackedQMVBitwiseWhenRuntimeTestsAreEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
        return
    }

    let expertCount = LagunaConstants.numExperts
    let outputWidth = LagunaConstants.moeIntermediateSize
    let fusedRows = 2 * outputWidth
    let packedWidth = LagunaConstants.hiddenSize / 8
    var markerOffsets = [Int32]()
    markerOffsets.reserveCapacity(2 * expertCount)
    for expert in 0..<expertCount {
        let gateRow = (expert / 32) * 64 + expert % 32
        let expertBase = expert * fusedRows * packedWidth
        markerOffsets.append(Int32(expertBase + gateRow * packedWidth))
        markerOffsets.append(Int32(expertBase + (gateRow + 32) * packedWidth))
    }
    let fusedWeight = MLXArray.zeros(
        [expertCount * fusedRows * packedWidth], dtype: .uint32
    ).at[MLXArray(markerOffsets)].add(UInt32(0x2222_2222)).reshaped(
        [expertCount, fusedRows, packedWidth]
    )
    let packedScales = MLXArray.full(
        [lagunaPackedRoutedGateUpScaleBytes],
        values: MLXArray(UInt8(0x38)),
        dtype: .uint8
    )
    let input = MLXArray.full(
        [1, 1, LagunaConstants.hiddenSize],
        values: MLXArray(Float(1)),
        dtype: .bfloat16
    )

    for (label, scores) in packedTop8DifferentialCases() {
        let expectedIndices = expectedPackedTop8Indices(scores)
        let candidate = lagunaRoutedSwiGLUQMVPackedTop8(
            input,
            fusedWeight: fusedWeight,
            packedScales: packedScales,
            routerKeys: MLXArray(scores.map(packedRouterOrdinal))
        )
        let control = lagunaRoutedSwiGLUQMVPacked(
            input,
            fusedWeight: fusedWeight,
            packedScales: packedScales,
            indices: MLXArray(expectedIndices, [1, 1, LagunaConstants.numExpertsPerTok])
        )
        eval(candidate, control)

        let candidateBits = candidate.view(dtype: .uint16).asArray(UInt16.self)
        let controlBits = control.view(dtype: .uint16).asArray(UInt16.self)
        #expect(candidate.shape == control.shape, Comment(rawValue: label))
        #expect(
            candidateBits == controlBits,
            Comment(rawValue: "\(label): expected exact experts \(expectedIndices)")
        )
        for slot in 0..<LagunaConstants.numExpertsPerTok {
            let start = slot * outputWidth
            let nonzeroRows = controlBits[start..<(start + outputWidth)].enumerated()
                .compactMap { row, bits in bits & 0x7FFF == 0 ? nil : row }
            #expect(
                nonzeroRows == [Int(expectedIndices[slot])],
                Comment(rawValue: "\(label): slot \(slot) did not identify one exact expert")
            )
        }
    }
}

private func packedRouterOrdinal(_ value: Float) -> UInt32 {
    let bits = value.bitPattern
    let magnitude = bits & 0x7FFF_FFFF
    if magnitude > 0x7F80_0000 {
        return .max
    }
    if magnitude == 0 {
        return 0x8000_0000
    }
    return bits & 0x8000_0000 != 0 ? ~bits : bits ^ 0x8000_0000
}

private func expectedPackedTop8Indices(_ scores: [Float]) -> [UInt32] {
    scores.enumerated().sorted { lhs, rhs in
        let lhsOrdinal = packedRouterOrdinal(lhs.element)
        let rhsOrdinal = packedRouterOrdinal(rhs.element)
        return lhsOrdinal == rhsOrdinal ? lhs.offset < rhs.offset : lhsOrdinal < rhsOrdinal
    }.prefix(LagunaConstants.numExpertsPerTok).map { UInt32($0.offset) }
}

private func packedTop8DifferentialCases() -> [(String, [Float])] {
    let randomDistinct = (0..<LagunaConstants.numExperts).map {
        Float(($0 * 73) % 257) - 128
    }
    let allTies = [Float](repeating: 2, count: LagunaConstants.numExperts)

    var signedZeros = [Float](repeating: 1, count: LagunaConstants.numExperts)
    for (position, index) in [5, 31, 32, 63, 64, 95, 96, 127, 128, 159].enumerated() {
        signedZeros[index] = position.isMultiple(of: 2) ? 0 : Float(bitPattern: 0x8000_0000)
    }

    var nanCutoff = (0..<LagunaConstants.numExperts).map {
        Float(bitPattern: 0x7FC0_0000 | UInt32($0 + 1))
    }
    for (score, index) in zip([-6, -5, -4, -3, -2, -1] as [Float], [255, 223, 191, 159, 127, 95]) {
        nanCutoff[index] = score
    }

    var extrema = [Float](repeating: .nan, count: LagunaConstants.numExperts)
    extrema[250] = -Float.infinity
    extrema[3] = -Float.greatestFiniteMagnitude
    extrema[200] = -Float.leastNonzeroMagnitude
    extrema[5] = Float(bitPattern: 0x8000_0000)
    extrema[180] = 0
    extrema[7] = Float.leastNonzeroMagnitude
    extrema[160] = Float.greatestFiniteMagnitude
    extrema[9] = Float.infinity
    extrema[140] = Float(bitPattern: 0x7FC1_2345)

    var oneLaneReverse = [Float](repeating: 100, count: LagunaConstants.numExperts)
    for (rank, index) in [255, 223, 191, 159, 127, 95, 63, 31].enumerated() {
        oneLaneReverse[index] = Float(rank - 8)
    }

    var repeatedCutoff = [Float](repeating: 100, count: LagunaConstants.numExperts)
    for index in [250, 3] { repeatedCutoff[index] = -3 }
    for index in [224, 32, 5] { repeatedCutoff[index] = -2 }
    for index in [255, 33, 6, 128, 160] { repeatedCutoff[index] = -1 }

    return [
        ("random-distinct", randomDistinct),
        ("all-ties", allTies),
        ("signed-zero-cutoff", signedZeros),
        ("nan-cutoff", nanCutoff),
        ("extrema", extrema),
        ("one-lane-reverse", oneLaneReverse),
        ("repeated-cutoff", repeatedCutoff),
    ]
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
