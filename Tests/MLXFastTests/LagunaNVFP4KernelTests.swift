import Foundation
import MLX
import MLXFast
import MLXLMCommon
import MLXNN
@testable import MLXFastModel
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

@Test
func routedSharedDownRouterWeightBroadcastMatchesBaselineBitsWhenRuntimeTestsAreEnabled() throws {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
        return
    }

    let candidateEpilogue = """
        if (slot == 0) {
            bfloat routed_total = bfloat(0);
            for (uint routed_slot = 0;
                 routed_slot < routed_experts;
                 ++routed_slot) {
                ushort route_weight_bits = lane == 0
                    ? as_type<ushort>(bfloat(router_weights[routed_slot]))
                    : ushort(0);
                route_weight_bits =
                    simd_broadcast(route_weight_bits, ushort(0));
                if (lane < outputs_per_simd) {
                    bfloat route_weight =
                        as_type<bfloat>(route_weight_bits);
                    bfloat product = bfloat(
                        down_outputs[
                            routed_slot * outputs_per_simd + lane
                        ] * route_weight);
                    routed_total = bfloat(product + routed_total);
                }
            }
            if (lane < outputs_per_simd) {
                bfloat routed = bfloat(
                    routed_total * bfloat(2.5f));
                bfloat shared =
                    down_outputs[shared_slot * outputs_per_simd + lane];
                bfloat r2 = bfloat(routed + shared);
                output[first_row + lane] =
                    bfloat(residual[first_row + lane] + r2);
            }
        }
        """
    let baselineEpilogue = """
        if (slot == 0 && lane < outputs_per_simd) {
            bfloat routed_total = bfloat(0);
            for (uint routed_slot = 0;
                 routed_slot < routed_experts;
                 ++routed_slot) {
                bfloat route_weight =
                    bfloat(router_weights[routed_slot]);
                bfloat product = bfloat(
                    down_outputs[
                        routed_slot * outputs_per_simd + lane
                    ] * route_weight);
                routed_total = bfloat(product + routed_total);
            }
            bfloat routed = bfloat(
                routed_total * bfloat(2.5f));
            bfloat shared =
                down_outputs[shared_slot * outputs_per_simd + lane];
            bfloat r2 = bfloat(routed + shared);
            output[first_row + lane] =
                bfloat(residual[first_row + lane] + r2);
        }
        """
    let candidateSource = lagunaRoutedSharedDownResidualSource(
        sharedHalved: true,
        staged: true
    )
    try #require(candidateSource.components(separatedBy: candidateEpilogue).count == 2)
    let baselineSource = candidateSource.replacingOccurrences(
        of: candidateEpilogue,
        with: baselineEpilogue
    )

    let inputNames = [
        "routed_activated", "routed_down_weight", "routed_down_scales",
        "indices", "router_weights", "shared_activated",
        "shared_down_weight", "shared_down_scales", "residual",
    ]
    let candidateKernel = MLXFast.metalKernel(
        name: "test_laguna_routed_shared_down_router_broadcast",
        inputNames: inputNames,
        outputNames: ["output"],
        source: candidateSource,
        header: lagunaSharedSwiGLUQMVHeader,
        ensureRowContiguous: true
    )
    let baselineKernel = MLXFast.metalKernel(
        name: "test_laguna_routed_shared_down_router_per_lane",
        inputNames: inputNames,
        outputNames: ["output"],
        source: baselineSource,
        header: lagunaSharedSwiGLUQMVHeader,
        ensureRowContiguous: true
    )

    let routedValues = (0..<(8 * 512)).map { index in
        Float((index % 31) - 15) / 32
    }
    let routedActivated = MLXArray(
        routedValues,
        [1, 1, 8, 1, 512]
    ).asType(.bfloat16)
    let routedPackedSeed = MLXArray(
        (0..<256).map { expert in
            UInt32((expert % 7) + 1) &* UInt32(0x1111_1111)
        },
        [256, 1, 1]
    )
    let routedDownWeight = contiguous(
        broadcast(routedPackedSeed, to: [256, 2_048, 64])
    )
    let routedDownScales = MLXArray.full(
        [128 + 256 * 2_048 * 16],
        values: MLXArray(UInt8(0x38)),
        dtype: .uint8
    )
    let indices = MLXArray(
        [UInt32(0), 7, 42, 255, 3, 128, 17, 99],
        [1, 1, 8]
    )
    let routerWeights = MLXArray(
        [
            UInt32(0x3f80_7fff), 0x3f80_8000,
            0x3f80_8001, 0x3f81_7fff,
            0xbf80_7fff, 0xbf80_8000,
            0xbf80_8001, 0xbf81_8001,
        ].map(Float.init(bitPattern:)),
        [1, 1, 8]
    )
    let sharedValues = (0..<512).map { index in
        Float((index % 23) - 11) / 32
    }
    let sharedActivated = MLXArray(
        sharedValues,
        [1, 1, 512]
    ).asType(.bfloat16)
    let sharedDownWeight = contiguous(
        broadcast(MLXArray(UInt32(0x2222_2222)), to: [2_048, 64])
    )
    let sharedDownScales = MLXArray.full(
        [128 + 2_048 * 16],
        values: MLXArray(UInt8(0x38)),
        dtype: .uint8
    )
    let residual = MLXArray(
        (0..<2_048).map { index in Float((index % 19) - 9) / 16 },
        [1, 1, 2_048]
    ).asType(.bfloat16)
    let inputs = [
        routedActivated, routedDownWeight, routedDownScales,
        indices, routerWeights, sharedActivated,
        sharedDownWeight, sharedDownScales, residual,
    ]

    func run(_ kernel: MLXFast.MLXFastKernel) -> MLXArray {
        kernel(
            inputs,
            grid: (2_048 / 4 * 288, 1, 1),
            threadGroup: (288, 1, 1),
            outputShapes: [[1, 1, 2_048]],
            outputDTypes: [.bfloat16]
        )[0]
    }

    let candidate = run(candidateKernel)
    let baseline = run(baselineKernel)
    eval(candidate, baseline)
    let candidateBits = candidate.view(dtype: .uint16).asArray(UInt16.self)
    let baselineBits = baseline.view(dtype: .uint16).asArray(UInt16.self)
    #expect(candidateBits == baselineBits)
    #expect(Array(candidateBits[2_044..<2_048]) == Array(baselineBits[2_044..<2_048]))
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
