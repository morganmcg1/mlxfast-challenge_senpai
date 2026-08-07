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
func routerNormSIMDGroupZeroEvidenceWhenEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_ROUTER_NORM_SIMDGROUP0_EVIDENCE"] == "1" else {
        return
    }

    typealias Inputs = (logits: [Float], bias: [Float])
    let zeros = Array(repeating: Float(0), count: 256)
    var corpus = [Inputs]()
    corpus.append((Array(repeating: 1, count: 256), zeros))
    corpus.append(((0..<256).map { Float($0 / 4) }, (0..<256).map { Float(($0 % 7) - 3) * 0.125 }))
    corpus.append(((0..<256).map { $0.isMultiple(of: 2) ? Float.greatestFiniteMagnitude / 4 : -Float.greatestFiniteMagnitude / 4 }, zeros))
    corpus.append(((0..<256).map { $0.isMultiple(of: 2) ? Float(bitPattern: 0) : Float(bitPattern: 0x8000_0000) }, zeros))

    var special = (0..<256).map { Float($0 - 128) }
    let specialBits: [UInt32] = [
        0x7f80_0000, 0xff80_0000, 0x7fc0_0001, 0x7fa0_0001,
        0xffc0_0001, 0xffa0_0001, 0x0000_0000, 0x8000_0000,
    ]
    for (index, bits) in specialBits.enumerated() {
        special[index] = Float(bitPattern: bits)
    }
    corpus.append((special, zeros))

    var state: UInt64 = 0x6a09_e667_f3bc_c909
    func shuffledOrdinals() -> [Float] {
        var values = Array(0..<256)
        for upper in stride(from: 255, through: 1, by: -1) {
            state = state &* 6_364_136_223_846_793_005 &+ 1_442_695_040_888_963_407
            let lower = Int(state % UInt64(upper + 1))
            values.swapAt(upper, lower)
        }
        return values.map(Float.init)
    }
    for sample in 0..<64 {
        let logits = shuffledOrdinals()
        let bias = (0..<256).map { Float((($0 &* 17 &+ sample &* 13) % 19) - 9) * 0.03125 }
        corpus.append((logits, bias))
    }

    var exact = true
    for (caseIndex, inputs) in corpus.enumerated() {
        let logits = MLXArray(inputs.logits, [1, 1, 256])
        let bias = MLXArray(inputs.bias, [1, 1, 256])
        let control = lagunaDecodeRouterTop8OrdinalScoreTableForTesting(
            logits: logits,
            correctionBias: bias,
            normalizing: true,
            simdGroupZeroNormalizing: false
        )
        let candidate = lagunaDecodeRouterTop8OrdinalScoreTableForTesting(
            logits: logits,
            correctionBias: bias,
            normalizing: true,
            simdGroupZeroNormalizing: true
        )
        eval([control.0, control.1, candidate.0, candidate.1])
        let controlIndices = control.0.asArray(UInt32.self)
        let candidateIndices = candidate.0.asArray(UInt32.self)
        let controlScores = control.1.asArray(Float.self).map { $0.bitPattern }
        let candidateScores = candidate.1.asArray(Float.self).map { $0.bitPattern }
        let indicesMatch = controlIndices == candidateIndices
        let scoresMatch = controlScores == candidateScores
        exact = exact && indicesMatch && scoresMatch
        #expect(indicesMatch, Comment(rawValue: "case \(caseIndex) indices differ"))
        #expect(scoresMatch, Comment(rawValue: "case \(caseIndex) score bits differ"))
    }
    print("ROUTER_EXACTNESS cases=\(corpus.count) passed=\(exact)")

    let timingInputs: [(MLXArray, MLXArray)] = (0..<16).map { sample in
        let logits = shuffledOrdinals().map { $0 * 0.015625 - Float(sample) * 0.0001 }
        let bias = (0..<256).map { Float((($0 &* 29 &+ sample &* 7) % 23) - 11) * 0.015625 }
        return (MLXArray(logits, [1, 1, 256]), MLXArray(bias, [1, 1, 256]))
    }

    func evaluate(candidate: Bool, repetitions: Int) -> UInt64 {
        var outputs = [MLXArray]()
        outputs.reserveCapacity(repetitions * 2)
        for repetition in 0..<repetitions {
            let input = timingInputs[repetition % timingInputs.count]
            let routed = lagunaDecodeRouterTop8OrdinalScoreTableForTesting(
                logits: input.0,
                correctionBias: input.1,
                normalizing: true,
                simdGroupZeroNormalizing: candidate
            )
            outputs.append(routed.0)
            outputs.append(routed.1)
        }
        let start = DispatchTime.now().uptimeNanoseconds
        eval(outputs)
        return DispatchTime.now().uptimeNanoseconds - start
    }

    _ = evaluate(candidate: false, repetitions: 8)
    _ = evaluate(candidate: true, repetitions: 8)

    let pairs = 31
    let repetitions = 1_024
    var abRatios = [Double]()
    var baRatios = [Double]()
    for pair in 0..<pairs {
        let control = evaluate(candidate: false, repetitions: repetitions)
        let candidate = evaluate(candidate: true, repetitions: repetitions)
        let speedup = Double(control) / Double(candidate)
        abRatios.append(speedup)
        print("ROUTER_TIMING order=AB pair=\(pair) control_ns=\(control) candidate_ns=\(candidate) speedup=\(String(format: "%.9f", speedup))")
    }
    for pair in 0..<pairs {
        let candidate = evaluate(candidate: true, repetitions: repetitions)
        let control = evaluate(candidate: false, repetitions: repetitions)
        let speedup = Double(control) / Double(candidate)
        baRatios.append(speedup)
        print("ROUTER_TIMING order=BA pair=\(pair) control_ns=\(control) candidate_ns=\(candidate) speedup=\(String(format: "%.9f", speedup))")
    }

    let abMedian = abRatios.sorted()[pairs / 2]
    let baMedian = baRatios.sorted()[pairs / 2]
    print("ROUTER_SUMMARY order=AB pairs=\(pairs) repetitions=\(repetitions) median_speedup=\(String(format: "%.9f", abMedian))")
    print("ROUTER_SUMMARY order=BA pairs=\(pairs) repetitions=\(repetitions) median_speedup=\(String(format: "%.9f", baMedian))")
}

