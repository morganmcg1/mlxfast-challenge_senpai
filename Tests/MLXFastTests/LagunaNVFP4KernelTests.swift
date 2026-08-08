import Foundation
import MLX
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

private let oprojActivatedTGOracleEnvironment =
    "MLXFAST_RUN_OPROJ_TG_STAGING_ORACLE"
private let oprojActivatedTGTimingEnvironment =
    "MLXFAST_RUN_OPROJ_TG_STAGING_TIMING"
private let oprojActivatedTGOutputSize = 2_048
private let oprojActivatedTGTimingBatchSize = 64
private let oprojActivatedTGTimingPairs = 8

@Test
func oprojActivatedInputTGStagingSourceProvesSingleWriterLifetime() {
    let expectedWriters = Set(0..<512)
    let writers = (0..<64).flatMap { lid in
        (0..<8).map { lid * 8 + $0 }
    }
    #expect(writers.count == 512)
    #expect(Set(writers).count == 512)
    #expect(Set(writers) == expectedWriters)

    for heads in [48, 64] {
        let control = lagunaGatedAffineOProjNVFP4Source(
            heads: heads,
            preActivatedGate: true,
            stageActivatedInput: false
        )
        let candidate = lagunaGatedAffineOProjNVFP4Source(
            heads: heads,
            preActivatedGate: true,
            stageActivatedInput: true
        )
        let barrier = "threadgroup_barrier(mem_flags::mem_threadgroup);"
        let sections = candidate.components(separatedBy: barrier)

        #expect(!control.contains("threadgroup bfloat activated_input[block_size];"))
        #expect(candidate.contains("threadgroup bfloat activated_input[block_size];"))
        #expect(candidate.components(separatedBy: "activated_input[index] =").count == 2)
        #expect(sections.count == 3)
        #expect(sections[0].contains("activated_input[index] ="))
        #expect(!sections[1].contains("activated_input[index] ="))
        #expect(sections[1].contains("float(activated_input[simd_lid * values_per_thread + i])"))
        #expect(!sections[2].contains("activated_input"))
        #expect(candidate.contains("constexpr uint staging_values_per_thread = 8;"))
        #expect(candidate.contains("thread float x_thread[values_per_thread];"))

        print(
            "OPROJ_ACTIVATED_TG_SOURCE_JSON={\"heads\":\(heads),"
                + "\"threadgroup_bytes\":1024,\"producers\":64,"
                + "\"values_per_producer\":8,\"unique_writes\":512,"
                + "\"barriers\":2,\"private_float_values_per_thread\":16,"
                + "\"explicit_local_memory_bytes\":0}"
        )
    }
}

@Test
func oprojActivatedInputTGStagingBitwiseOracleWhenEnabled() throws {
    guard ProcessInfo.processInfo.environment[oprojActivatedTGOracleEnvironment] == "1" else {
        return
    }

    for (heads, layer) in [(48, 0), (64, 1)] {
        let context = try makeOProjActivatedTGContext(heads: heads, layer: layer)
        let fixtures = [
            context.checkpointFixture,
            makeOProjActivatedTGRandomFixture(context: context),
            makeOProjActivatedTGEdgeFixture(context: context),
        ]
        let control = makeOProjActivatedTGKernel(heads: heads, staged: false)
        let candidate = makeOProjActivatedTGKernel(heads: heads, staged: true)
        let perturbed = makeOProjActivatedTGKernel(
            heads: heads,
            staged: true,
            perturbFirstOutputBit: true
        )

        for fixture in fixtures {
            eval(fixture.inputs)
            let controlOutput = runOProjActivatedTG(control, fixture: fixture)
            let candidateOutput = runOProjActivatedTG(candidate, fixture: fixture)
            let perturbedOutput = runOProjActivatedTG(perturbed, fixture: fixture)
            eval(controlOutput, candidateOutput, perturbedOutput)

            let controlData = controlOutput.asData(access: .copy).data
            let candidateData = candidateOutput.asData(access: .copy).data
            let perturbedData = perturbedOutput.asData(access: .copy).data
            #expect(
                controlData == candidateData,
                Comment(rawValue: "H\(heads) \(fixture.label) staging changed output bits")
            )
            #expect(
                controlData != perturbedData,
                Comment(rawValue: "H\(heads) \(fixture.label) corruption control was not detected")
            )
            print(
                "OPROJ_ACTIVATED_TG_ORACLE_JSON={\"heads\":\(heads),"
                    + "\"fixture\":\"\(fixture.label)\","
                    + "\"bytes\":\(controlData.count),"
                    + "\"candidate_bitwise_equal\":true,"
                    + "\"one_bit_corruption_detected\":true,"
                    + "\"jit_compiled\":true}"
            )
        }
    }
}

@Test
func oprojActivatedInputTGStagingAlternatingTimingWhenEnabled() throws {
    guard ProcessInfo.processInfo.environment[oprojActivatedTGTimingEnvironment] == "1" else {
        return
    }

    for (heads, layer) in [(48, 0), (64, 1)] {
        let context = try makeOProjActivatedTGContext(heads: heads, layer: layer)
        let fixture = context.checkpointFixture
        let control = makeOProjActivatedTGKernel(heads: heads, staged: false)
        let candidate = makeOProjActivatedTGKernel(heads: heads, staged: true)
        eval(fixture.inputs)
        eval(
            runOProjActivatedTG(control, fixture: fixture),
            runOProjActivatedTG(candidate, fixture: fixture)
        )
        Stream.gpu.synchronize()

        var controlAB: [Double] = []
        var candidateAB: [Double] = []
        var controlBA: [Double] = []
        var candidateBA: [Double] = []
        for _ in 0..<oprojActivatedTGTimingPairs {
            controlAB.append(measureOProjActivatedTG(control, fixture: fixture))
            candidateAB.append(measureOProjActivatedTG(candidate, fixture: fixture))
            candidateBA.append(measureOProjActivatedTG(candidate, fixture: fixture))
            controlBA.append(measureOProjActivatedTG(control, fixture: fixture))
        }

        let controlABMedian = oprojActivatedTGMedian(controlAB)
        let candidateABMedian = oprojActivatedTGMedian(candidateAB)
        let controlBAMedian = oprojActivatedTGMedian(controlBA)
        let candidateBAMedian = oprojActivatedTGMedian(candidateBA)
        let speedupAB = controlABMedian / candidateABMedian
        let speedupBA = controlBAMedian / candidateBAMedian
        let relativeNoise = [controlAB, candidateAB, controlBA, candidateBA]
            .map(oprojActivatedTGRelativeMAD)
            .max() ?? .infinity
        let minimumMargin = min(speedupAB - 1, speedupBA - 1)
        let result: [String: Any] = [
            "heads": heads,
            "hardware": "M4 Pro Mac16,11 GPU generation 16",
            "batch_size": oprojActivatedTGTimingBatchSize,
            "matched_pairs_per_order": oprojActivatedTGTimingPairs,
            "seconds_per_dispatch": [
                "control_ab": controlAB,
                "candidate_ab": candidateAB,
                "control_ba": controlBA,
                "candidate_ba": candidateBA,
            ],
            "medians": [
                "control_ab": controlABMedian,
                "candidate_ab": candidateABMedian,
                "control_ba": controlBAMedian,
                "candidate_ba": candidateBAMedian,
            ],
            "speedup": ["ab": speedupAB, "ba": speedupBA],
            "relative_mad_noise": relativeNoise,
            "minimum_speedup_margin": minimumMargin,
            "gate": [
                "minimum_speedup": 1.005,
                "noise_multiple": 2.0,
                "passed": speedupAB >= 1.005 && speedupBA >= 1.005
                    && minimumMargin > 2 * relativeNoise,
            ],
        ]
        let data = try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys])
        print("OPROJ_ACTIVATED_TG_TIMING_JSON=\(String(decoding: data, as: UTF8.self))")

        #expect(
            speedupAB >= 1.005,
            Comment(rawValue: "H\(heads) AB speedup \(speedupAB) missed 1.005")
        )
        #expect(
            speedupBA >= 1.005,
            Comment(rawValue: "H\(heads) BA speedup \(speedupBA) missed 1.005")
        )
        #expect(
            minimumMargin > 2 * relativeNoise,
            Comment(
                rawValue: "H\(heads) margin \(minimumMargin) was not >2x noise \(relativeNoise)"
            )
        )
    }
}

private struct OProjActivatedTGFixture {
    let label: String
    let inputs: [MLXArray]
}

private struct OProjActivatedTGContext {
    let heads: Int
    let weightInputs: [MLXArray]
    let checkpointFixture: OProjActivatedTGFixture
}

private func makeOProjActivatedTGContext(
    heads: Int,
    layer: Int
) throws -> OProjActivatedTGContext {
    let weightsPath = try #require(
        ProcessInfo.processInfo.environment["MLXFAST_LAGUNA_EQUIVALENCE_WEIGHTS_PATH"]
    )
    let store = try DenseTensorStore(weightsPath: weightsPath)
    let tensor = try store.materializedTensor(
        named: LagunaWeightNames.attention(layer, "o_proj.weight")
    )
    let weight = try MLXArrayTensorBridge().makeArray(from: tensor)
    let bank = try #require(lagunaNativeAffineWeight(weight, layer: layer))
    let inputSize = heads * 128

    #expect(weight.shape == [oprojActivatedTGOutputSize, inputSize])
    #expect(bank.originalShape == [oprojActivatedTGOutputSize, inputSize])
    #expect(bank.groupSize == 16)
    #expect(bank.bits == 4)
    #expect(bank.biases == nil)
    #expect(bank.mode == .nvfp4)

    let attention = weight[0..<1, 0..<inputSize]
        .reshaped([1, 1, inputSize])
        .asType(.bfloat16)
    let gates = weight[1..<2, 0..<heads]
        .reshaped([1, 1, heads])
        .asType(.bfloat16)
    let weightInputs = [bank.packedCodes, bank.scales]
    let checkpointFixture = OProjActivatedTGFixture(
        label: "checkpoint_derived",
        inputs: [attention, gates] + weightInputs
    )
    eval([weight] + checkpointFixture.inputs)
    return OProjActivatedTGContext(
        heads: heads,
        weightInputs: weightInputs,
        checkpointFixture: checkpointFixture
    )
}

private func makeOProjActivatedTGRandomFixture(
    context: OProjActivatedTGContext
) -> OProjActivatedTGFixture {
    let inputSize = context.heads * 128
    let attention = makeOProjActivatedTGFiniteBF16(
        count: inputSize,
        shape: [1, 1, inputSize],
        seed: UInt64(context.heads) * 0x9E37_79B9
    )
    let gates = makeOProjActivatedTGFiniteBF16(
        count: context.heads,
        shape: [1, 1, context.heads],
        seed: UInt64(context.heads) * 0xC2B2_AE35
    )
    return OProjActivatedTGFixture(
        label: "random_finite_bf16",
        inputs: [attention, gates] + context.weightInputs
    )
}

private func makeOProjActivatedTGEdgeFixture(
    context: OProjActivatedTGContext
) -> OProjActivatedTGFixture {
    let inputSize = context.heads * 128
    let attention = makeOProjActivatedTGRepeatedBF16(
        pattern: [
            0x0000, 0x8000, 0x0001, 0x8001, 0x007F, 0x807F, 0x0080,
            0x8080, 0x3F80, 0xBF80, 0x3F00, 0xBF00, 0x7F7F, 0xFF7F,
        ],
        count: inputSize,
        shape: [1, 1, inputSize]
    )
    let gates = makeOProjActivatedTGRepeatedBF16(
        pattern: [0x3F80, 0xBF80, 0x0000, 0x8000],
        count: context.heads,
        shape: [1, 1, context.heads]
    )
    return OProjActivatedTGFixture(
        label: "signed_zero_subnormal_extrema_bf16",
        inputs: [attention, gates] + context.weightInputs
    )
}

private func makeOProjActivatedTGFiniteBF16(
    count: Int,
    shape: [Int],
    seed: UInt64
) -> MLXArray {
    var state = seed
    let values = (0..<count).map { _ -> Float in
        state = state &* 6_364_136_223_846_793_005 &+ 1_442_695_040_888_963_407
        let unit = Float((state >> 40) & 0xFF_FFFF) / Float(0xFF_FFFF)
        return (2 * unit - 1) * 4
    }
    return MLXArray(values, shape).asType(.bfloat16)
}

private func makeOProjActivatedTGRepeatedBF16(
    pattern: [UInt16],
    count: Int,
    shape: [Int]
) -> MLXArray {
    let values = (0..<count).map { pattern[$0 % pattern.count] }
    let data = values.withUnsafeBytes { Data($0) }
    return MLXArray(data, shape, dtype: .bfloat16)
}

private func makeOProjActivatedTGKernel(
    heads: Int,
    staged: Bool,
    perturbFirstOutputBit: Bool = false
) -> MLXFast.MLXFastKernel {
    var source = lagunaGatedAffineOProjNVFP4Source(
        heads: heads,
        preActivatedGate: true,
        stageActivatedInput: staged
    )
    if perturbFirstOutputBit {
        let original = "projected[out_row + row] = bfloat(result[row]);"
        let replacement = """
        bfloat value = bfloat(result[row]);
        ushort bits = as_type<ushort>(value);
        if (out_row + row == 0) bits ^= ushort(1);
        projected[out_row + row] = as_type<bfloat>(bits);
        """
        precondition(source.contains(original))
        source = source.replacingOccurrences(of: original, with: replacement)
    }
    return MLXFast.metalKernel(
        name: "laguna_oproj_activated_tg_test_h\(heads)_s\(staged ? 1 : 0)"
            + (perturbFirstOutputBit ? "_p1" : ""),
        inputNames: ["attention_output", "gate_values", "weight_codes", "weight_scales"],
        outputNames: ["projected"],
        source: source,
        ensureRowContiguous: true
    )
}

private func runOProjActivatedTG(
    _ kernel: MLXFast.MLXFastKernel,
    fixture: OProjActivatedTGFixture
) -> MLXArray {
    kernel(
        fixture.inputs,
        grid: ((oprojActivatedTGOutputSize / 8) * 64, 1, 1),
        threadGroup: (64, 1, 1),
        outputShapes: [[1, 1, oprojActivatedTGOutputSize]],
        outputDTypes: [.bfloat16]
    )[0]
}

private func measureOProjActivatedTG(
    _ kernel: MLXFast.MLXFastKernel,
    fixture: OProjActivatedTGFixture
) -> Double {
    let outputs = (0..<oprojActivatedTGTimingBatchSize).map { _ in
        runOProjActivatedTG(kernel, fixture: fixture)
    }
    Stream.gpu.synchronize()
    let start = DispatchTime.now().uptimeNanoseconds
    eval(outputs)
    Stream.gpu.synchronize()
    return Double(DispatchTime.now().uptimeNanoseconds - start)
        / 1_000_000_000
        / Double(oprojActivatedTGTimingBatchSize)
}

private func oprojActivatedTGMedian(_ values: [Double]) -> Double {
    let sorted = values.sorted()
    let middle = sorted.count / 2
    if sorted.count.isMultiple(of: 2) {
        return (sorted[middle - 1] + sorted[middle]) / 2
    }
    return sorted[middle]
}

private func oprojActivatedTGRelativeMAD(_ values: [Double]) -> Double {
    let center = oprojActivatedTGMedian(values)
    return oprojActivatedTGMedian(values.map { abs($0 - center) }) / center
}
