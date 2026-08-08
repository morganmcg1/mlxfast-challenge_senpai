import Dispatch
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


private let slidingPrefillVLayoutControlH4Kernel = MLXFast.metalKernel(
    name: "laguna_prefill_sliding_qk_norm_rope_bf16_128_v2_test_control",
    inputNames: [
        "raw_queries", "raw_keys", "query_weight", "key_weight", "angles",
        "offsets",
    ],
    outputNames: ["queries", "keys"],
    source: """
        constexpr uint head_dim = 128;
        constexpr uint rotary_pairs = 64;
        constexpr uint query_heads = 64;
        constexpr uint kv_heads = 8;

        uint t = threadgroup_position_in_grid.y;
        uint length = threadgroups_per_grid.y;
        uint head = threadgroup_position_in_grid.x * 4
            + simdgroup_index_in_threadgroup;
        uint lane = thread_index_in_simdgroup;

        const device bfloat* input;
        const device bfloat* weight;
        device bfloat* output;
        if (head < query_heads) {
            input = raw_queries + (t * query_heads + head) * head_dim;
            weight = query_weight;
            output = queries + (head * length + t) * head_dim;
        } else {
            uint khead = head - query_heads;
            input = raw_keys + (t * kv_heads + khead) * head_dim;
            weight = key_weight;
            output = keys + (khead * length + t) * head_dim;
        }

        uint base = lane * 4;
        thread bfloat normalized[4];
        float sum = 0.0f;
        #pragma clang loop unroll(full)
        for (uint i = 0; i < 4; ++i) {
            float value = float(input[base + i]);
            sum += value * value;
        }
        sum = simd_sum(sum);
        float inverse_rms = metal::precise::rsqrt(sum / 128.0f + 1.0e-6f);

        #pragma clang loop unroll(full)
        for (uint i = 0; i < 4; ++i) {
            normalized[i] =
                weight[base + i] *
                bfloat(float(input[base + i]) * inverse_rms);
        }

        thread float paired[4];
        #pragma clang loop unroll(full)
        for (uint i = 0; i < 4; ++i) {
            paired[i] = simd_shuffle(float(normalized[i]), lane ^ 16);
        }

        const device float* angle_row =
            angles + (uint(offsets[0]) + t) * (2 * rotary_pairs);
        if (lane < 16) {
            #pragma clang loop unroll(full)
            for (uint i = 0; i < 4; ++i) {
                uint pair = base + i;
                float first = float(normalized[i]);
                float second = paired[i];
                float cosine = angle_row[pair];
                float sine = angle_row[pair + rotary_pairs];
                output[pair] = bfloat(first * cosine - second * sine);
                output[pair + rotary_pairs] =
                    bfloat(first * sine + second * cosine);
            }
        }
        """,
    ensureRowContiguous: true
)

private let slidingPrefillVLayoutControlH1Kernel = MLXFast.metalKernel(
    name: "laguna_prefill_sliding_qk_norm_rope_bf16_128_h1_v2_test_control",
    inputNames: [
        "raw_queries", "raw_keys", "query_weight", "key_weight", "angles",
        "offsets",
    ],
    outputNames: ["queries", "keys"],
    source: """
        constexpr uint head_dim = 128;
        constexpr uint rotary_pairs = 64;
        constexpr uint query_heads = 64;
        constexpr uint kv_heads = 8;

        uint group = threadgroup_position_in_grid.x;
        bool terminal = threadgroups_per_grid.y == 1 &&
            threadgroups_per_grid.x > query_heads + kv_heads;
        uint length = terminal
            ? (threadgroups_per_grid.x - query_heads) / kv_heads
            : threadgroups_per_grid.y;
        uint t = terminal
            ? (group < query_heads ? length - 1 : (group - query_heads) / kv_heads)
            : threadgroup_position_in_grid.y;
        uint head = terminal && group >= query_heads
            ? query_heads + (group - query_heads) % kv_heads : group;
        uint lane = thread_index_in_simdgroup;

        const device bfloat* input;
        const device bfloat* weight;
        device bfloat* output;
        if (head < query_heads) {
            uint qt = terminal ? 0 : t;
            input = raw_queries + (qt * query_heads + head) * head_dim;
            weight = query_weight;
            output = queries + (head * (terminal ? 1 : length) + qt) * head_dim;
        } else {
            uint khead = head - query_heads;
            input = raw_keys + (t * kv_heads + khead) * head_dim;
            weight = key_weight;
            output = keys + (khead * length + t) * head_dim;
        }

        uint base = lane * 4;
        thread bfloat normalized[4];
        float sum = 0.0f;
        #pragma clang loop unroll(full)
        for (uint i = 0; i < 4; ++i) {
            float value = float(input[base + i]);
            sum += value * value;
        }
        sum = simd_sum(sum);
        float inverse_rms = metal::precise::rsqrt(sum / 128.0f + 1.0e-6f);

        #pragma clang loop unroll(full)
        for (uint i = 0; i < 4; ++i) {
            normalized[i] =
                weight[base + i] *
                bfloat(float(input[base + i]) * inverse_rms);
        }

        thread float paired[4];
        #pragma clang loop unroll(full)
        for (uint i = 0; i < 4; ++i) {
            paired[i] = simd_shuffle(float(normalized[i]), lane ^ 16);
        }

        const device float* angle_row =
            angles + (uint(offsets[0]) + t) * (2 * rotary_pairs);
        if (lane < 16) {
            #pragma clang loop unroll(full)
            for (uint i = 0; i < 4; ++i) {
                uint pair = base + i;
                float first = float(normalized[i]);
                float second = paired[i];
                float cosine = angle_row[pair];
                float sine = angle_row[pair + rotary_pairs];
                output[pair] = bfloat(first * cosine - second * sine);
                output[pair + rotary_pairs] =
                    bfloat(first * sine + second * cosine);
            }
        }
        """,
    ensureRowContiguous: true
)

private struct SlidingPrefillVLayoutFixture {
    let rawQueries: MLXArray
    let rawKeys: MLXArray
    let rawValues: MLXArray
    let queryWeight: MLXArray
    let keyWeight: MLXArray
    let angles: MLXArray
    let offsets: MLXArray
    let length: Int
    let terminal: Bool
}

private func slidingPrefillPattern(
    shape: [Int],
    period: Int,
    scale: Float,
    offset: Float = 0,
    dtype: DType = .bfloat16
) -> MLXArray {
    let count = shape.reduce(1, *)
    let values = (0 ..< count).map { offset + Float($0 % period) * scale }
    return MLXArray(values, shape).asType(dtype)
}

private func makeSlidingPrefillVLayoutFixture(
    length: Int,
    terminal: Bool
) -> SlidingPrefillVLayoutFixture {
    let queryLength = terminal ? 1 : length
    let rawQueries = slidingPrefillPattern(
        shape: [1, queryLength, 64 * 128],
        period: 509,
        scale: 1.0 / 256.0,
        offset: -1
    )
    let rawKeys: MLXArray
    let rawValues: MLXArray
    if terminal {
        let bank = slidingPrefillPattern(
            shape: [1, length, 2 * 8 * 128],
            period: 2039,
            scale: 1.0 / 512.0,
            offset: -2
        )
        rawKeys = bank[.ellipsis, 0 ..< 8 * 128]
        rawValues = bank[.ellipsis, 8 * 128 ..< 2 * 8 * 128]
    } else {
        rawKeys = slidingPrefillPattern(
            shape: [1, length, 8 * 128],
            period: 1021,
            scale: 1.0 / 512.0,
            offset: -1
        )
        rawValues = slidingPrefillPattern(
            shape: [1, length, 8 * 128],
            period: 1019,
            scale: 1.0 / 256.0,
            offset: -2
        )
    }
    let queryWeight = slidingPrefillPattern(
        shape: [128], period: 127, scale: 1.0 / 256.0, offset: 0.75)
    let keyWeight = slidingPrefillPattern(
        shape: [128], period: 125, scale: 1.0 / 256.0, offset: 0.5)
    let angles = slidingPrefillPattern(
        shape: [1, 1, 4096, 128],
        period: 127,
        scale: 1.0 / 4096.0,
        offset: 0.5,
        dtype: .float32
    )
    let offsets = MLXArray(Int32(0))
    eval(rawQueries, rawKeys, rawValues, queryWeight, keyWeight, angles, offsets)
    return SlidingPrefillVLayoutFixture(
        rawQueries: rawQueries,
        rawKeys: rawKeys,
        rawValues: rawValues,
        queryWeight: queryWeight,
        keyWeight: keyWeight,
        angles: angles,
        offsets: offsets,
        length: length,
        terminal: terminal
    )
}

private func slidingPrefillVLayoutControl(
    _ fixture: SlidingPrefillVLayoutFixture
) -> (MLXArray, MLXArray, MLXArray) {
    let headsPerGroup = lagunaPrefillQKHeadsPerGroup == 1 ? 1 : 4
    let terminal = fixture.terminal
    precondition(!terminal || headsPerGroup == 1)
    let threadGroupSize = headsPerGroup * 32
    let groups = terminal
        ? 64 + 8 * fixture.length
        : (64 + 8) / headsPerGroup
    let kernel = headsPerGroup == 1
        ? slidingPrefillVLayoutControlH1Kernel
        : slidingPrefillVLayoutControlH4Kernel
    let outputs = kernel(
        [
            fixture.rawQueries, fixture.rawKeys, fixture.queryWeight,
            fixture.keyWeight, fixture.angles, fixture.offsets,
        ],
        grid: (groups * threadGroupSize, terminal ? 1 : fixture.length, 1),
        threadGroup: (threadGroupSize, 1, 1),
        outputShapes: [
            [1, 64, terminal ? 1 : fixture.length, 128],
            [1, 8, fixture.length, 128],
        ],
        outputDTypes: [.bfloat16, .bfloat16]
    )
    let values = fixture.rawValues
        .reshaped(1, fixture.length, 8, 128)
        .transposed(0, 2, 1, 3)
    return (outputs[0], outputs[1], values)
}

private func slidingPrefillVLayoutCandidate(
    _ fixture: SlidingPrefillVLayoutFixture
) -> (MLXArray, MLXArray, MLXArray) {
    lagunaPrefillSlidingQKNormRoPE(
        rawQueries: fixture.rawQueries,
        rawKeys: fixture.rawKeys,
        rawValues: fixture.rawValues,
        queryWeight: fixture.queryWeight,
        keyWeight: fixture.keyWeight,
        angles: fixture.angles,
        offsets: fixture.offsets,
        length: fixture.length
    )
}

private func expectSlidingPrefillVLayoutExact(
    _ control: MLXArray,
    _ candidate: MLXArray,
    label: String
) {
    eval(control, candidate)
    let controlValues = control.asArray(Float.self)
    let candidateValues = candidate.asArray(Float.self)
    let mismatches = zip(controlValues, candidateValues).reduce(into: 0) {
        if $1.0 != $1.1 { $0 += 1 }
    }
    let maximumError = zip(controlValues, candidateValues)
        .map { abs($0 - $1) }
        .max() ?? .infinity
    print(
        "MLXFAST_VLAYOUT_EXACT label=\(label) mismatches=\(mismatches) " +
            "max_abs=\(maximumError) count=\(controlValues.count)"
    )
    #expect(control.shape == candidate.shape, Comment(rawValue: label))
    #expect(mismatches == 0, Comment(rawValue: label))
    #expect(maximumError == 0, Comment(rawValue: label))
}

@Test
func slidingPrefillVLayoutExactOracleWhenEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_VLAYOUT_EXACT"] == "1" else {
        return
    }
    let headsPerGroup = lagunaPrefillQKHeadsPerGroup
    let scenarios: [(Int, Bool)] = headsPerGroup == 1
        ? [(512, false), (37, false), (512, true), (37, true)]
        : [(512, false), (37, false)]
    for (length, terminal) in scenarios {
        let fixture = makeSlidingPrefillVLayoutFixture(length: length, terminal: terminal)
        let control = slidingPrefillVLayoutControl(fixture)
        let candidate = slidingPrefillVLayoutCandidate(fixture)
        let scenario = terminal ? "terminal" : "ordinary"
        let prefix = "\(scenario)_h\(headsPerGroup)_l\(length)"
        expectSlidingPrefillVLayoutExact(control.0, candidate.0, label: "\(prefix)_q")
        expectSlidingPrefillVLayoutExact(control.1, candidate.1, label: "\(prefix)_k")
        expectSlidingPrefillVLayoutExact(control.2, candidate.2, label: "\(prefix)_v")
    }
}

private func measureSlidingPrefillVLayout(
    fixture: SlidingPrefillVLayoutFixture,
    candidate: Bool
) -> Double {
    let start = DispatchTime.now().uptimeNanoseconds
    let outputs = candidate
        ? slidingPrefillVLayoutCandidate(fixture)
        : slidingPrefillVLayoutControl(fixture)
    eval(outputs.0, outputs.1, outputs.2)
    return Double(DispatchTime.now().uptimeNanoseconds - start) / 1_000_000_000
}

private func printSlidingPrefillVLayoutSample(
    scenario: String,
    order: String,
    pair: Int,
    variant: String,
    seconds: Double
) {
    print(
        "MLXFAST_VLAYOUT_SAMPLE scenario=\(scenario) order=\(order) pair=\(pair) " +
            "variant=\(variant) seconds=\(seconds)"
    )
}

@Test
func slidingPrefillVLayoutTimingWhenEnabled() {
    guard let mode = ProcessInfo.processInfo.environment["MLXFAST_RUN_VLAYOUT_TIMING"] else {
        return
    }
    let terminal = mode == "terminal"
    let headsPerGroup = lagunaPrefillQKHeadsPerGroup
    precondition(mode == "ordinary" || terminal)
    precondition(!terminal || headsPerGroup == 1)
    let scenario = terminal ? "terminal_h1_banked" : "ordinary_h\(headsPerGroup)_contiguous"
    let fixture = makeSlidingPrefillVLayoutFixture(length: 512, terminal: terminal)

    for iteration in 0 ..< 10 {
        _ = measureSlidingPrefillVLayout(
            fixture: fixture, candidate: iteration.isMultiple(of: 2))
        _ = measureSlidingPrefillVLayout(
            fixture: fixture, candidate: !iteration.isMultiple(of: 2))
    }

    for pair in 0 ..< 30 {
        let control = measureSlidingPrefillVLayout(fixture: fixture, candidate: false)
        let candidate = measureSlidingPrefillVLayout(fixture: fixture, candidate: true)
        printSlidingPrefillVLayoutSample(
            scenario: scenario, order: "AB", pair: pair, variant: "A", seconds: control)
        printSlidingPrefillVLayoutSample(
            scenario: scenario, order: "AB", pair: pair, variant: "B", seconds: candidate)
    }
    for pair in 0 ..< 30 {
        let candidate = measureSlidingPrefillVLayout(fixture: fixture, candidate: true)
        let control = measureSlidingPrefillVLayout(fixture: fixture, candidate: false)
        printSlidingPrefillVLayoutSample(
            scenario: scenario, order: "BA", pair: pair, variant: "B", seconds: candidate)
        printSlidingPrefillVLayoutSample(
            scenario: scenario, order: "BA", pair: pair, variant: "A", seconds: control)
    }
}
