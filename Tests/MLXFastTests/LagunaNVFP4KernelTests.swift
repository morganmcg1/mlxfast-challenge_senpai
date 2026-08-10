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

private let packedTop8ParentRouterHeader = """
METAL_FUNC uint laguna_router_key_ordinal(float key) {
    uint bits = as_type<uint>(key);
    uint magnitude = bits & 0x7FFFFFFFu;
    if (magnitude > 0x7F800000u) return 0xFFFFFFFFu;
    if (magnitude == 0u) return 0x80000000u;
    return (bits & 0x80000000u) != 0u ? ~bits : (bits ^ 0x80000000u);
}
METAL_FUNC bool laguna_router_ordinal_before(
    uint a, uint a_index, uint b, uint b_index) {
    if (a < b) return true;
    if (b < a) return false;
    return a_index < b_index;
}
METAL_FUNC uint laguna_router_top8_extract_round(
    thread const uint* keys, thread uint& mask, uint lane) {
    uint best_ordinal = 0xFFFFFFFFu;
    uint best_index = 256u;
    for (uint j = 0; j < 8; ++j) {
        if ((mask & (1u << j)) != 0u) continue;
        uint e = lane + 32u * j;
        uint o = keys[j];
        if (laguna_router_ordinal_before(o, e, best_ordinal, best_index)) {
            best_ordinal = o;
            best_index = e;
        }
    }
    uint2 best_pair = uint2(best_ordinal, best_index);
    for (ushort offset = 16; offset > 0; offset >>= 1) {
        const uint2 other_pair = simd_shuffle_xor(best_pair, offset);
        if (laguna_router_ordinal_before(
            other_pair.x, other_pair.y, best_pair.x, best_pair.y)) {
            best_pair = other_pair;
        }
    }
    best_index = best_pair.y;
    if ((best_index & 31u) == lane) {
        mask |= 1u << (best_index >> 5u);
    }
    return best_index;
}
"""

private let packedTop8ParentR1Kernel = MLXFast.metalKernel(
    name: "cedar_fern_packed_top8_parent_r1_bf16_v2",
    inputNames: ["input", "fused_weight", "packed_scales", "router_keys"],
    outputNames: ["activated"],
    source: """
constexpr uint input_width = 2048;
constexpr uint output_width = 512;
constexpr uint block_width = 512;
constexpr uint values_per_lane = 16;
constexpr uint routed_experts = 8;
constexpr uint fused_row_bytes = 1024;
constexpr uint fused_expert_bytes = 1024 * fused_row_bytes;
constexpr uint scale_patch_bytes = \(lagunaScalePatchHeaderBytes);
constexpr uint scale_row_bytes = 16;
constexpr uint scale_sub_bytes = 8 * scale_row_bytes;
constexpr uint scale_kblock_bytes = scale_sub_bytes;
constexpr uint scale_tile_bytes = 4 * scale_kblock_bytes;
constexpr uint packed_expert_bytes = 128 * scale_tile_bytes;

uint group = threadgroup_position_in_grid.x;
uint expert_slot = group % routed_experts;
uint tile = group / routed_experts;
uint simd_group = simdgroup_index_in_threadgroup;
uint lane = thread_index_in_simdgroup;
uint logical_row = tile * 2 + simd_group;
thread uint top8_keys[8];
for (uint j = 0; j < 8; ++j) {
    top8_keys[j] = router_keys[lane + 32u * j];
}
uint top8_mask = 0u;
uint top8_winner = 0u;
for (uint r = 0; r <= expert_slot; ++r) {
    top8_winner = laguna_router_top8_extract_round(
        top8_keys, top8_mask, lane);
}
uint expert = top8_winner;

const device uint8_t* expert_weight =
    (const device uint8_t*)fused_weight + expert * fused_expert_bytes;
const device uint8_t* row_scales =
    packed_scales + scale_patch_bytes + expert * packed_expert_bytes
    + (logical_row / 4) * scale_tile_bytes;
uint sub = logical_row % 4;
uint gate_row = (logical_row / 32) * 64 + logical_row % 32;
uint up_row = gate_row + 32;

thread float gate_result = 0.0f;
thread float up_result = 0.0f;
thread float input_values[values_per_lane];

uint2 gate_codes;
uint2 up_codes;
uint8_t gate_sb;
uint8_t up_sb;
{
    const device uint8_t* first_scales =
        row_scales + sub * 2 * scale_row_bytes + (lane >> 1);
    bool patch_lane = expert == 0 && logical_row == 0 && lane == 1;
    gate_sb = patch_lane ? packed_scales[0] : first_scales[0];
    up_sb = patch_lane ? packed_scales[1] : first_scales[scale_row_bytes];
    gate_codes = *(const device uint2*)(
        expert_weight + gate_row * fused_row_bytes + lane * 8);
    up_codes = *(const device uint2*)(
        expert_weight + up_row * fused_row_bytes + lane * 8);
}

for (uint block = 0; block < input_width; block += block_width) {
    const device vec<bfloat, 4>* input_vectors =
        (const device vec<bfloat, 4>*) (
            input + block + lane * values_per_lane);
    for (uint i = 0; i < values_per_lane / 4; ++i) {
        const vec<bfloat, 4> values = input_vectors[i];
        input_values[4 * i] = values[0];
        input_values[4 * i + 1] = values[1];
        input_values[4 * i + 2] = values[2];
        input_values[4 * i + 3] = values[3];
    }

    const uint2 cur_gate_codes = gate_codes;
    const uint2 cur_up_codes = up_codes;
    const uint8_t cur_gate_sb = gate_sb;
    const uint8_t cur_up_sb = up_sb;
    const uint next_block = block + block_width;
    if (next_block < input_width) {
        const device uint8_t* next_scales =
            row_scales + (next_block / block_width) * scale_kblock_bytes
            + sub * 2 * scale_row_bytes + (lane >> 1);
        gate_sb = next_scales[0];
        up_sb = next_scales[scale_row_bytes];
        gate_codes = *(const device uint2*)(
            expert_weight + gate_row * fused_row_bytes
            + next_block / 2 + lane * 8);
        up_codes = *(const device uint2*)(
            expert_weight + up_row * fused_row_bytes
            + next_block / 2 + lane * 8);
    }

    gate_result += laguna_nvfp4_qdot_codes_16(
        cur_gate_codes, input_values,
        laguna_nvfp4_scale(cur_gate_sb));
    up_result += laguna_nvfp4_qdot_codes_16(
        cur_up_codes, input_values,
        laguna_nvfp4_scale(cur_up_sb));
}

gate_result = simd_sum(gate_result);
up_result = simd_sum(up_result);
if (lane == 0) {
    bfloat gate = bfloat(gate_result\(lagunaNvfp4RowScaleSuffix));
    bfloat up = bfloat(up_result\(lagunaNvfp4RowScaleSuffix));
    bfloat exp_abs = metal::exp(metal::abs(gate));
    bfloat denominator = bfloat(1) + exp_abs;
    bfloat y = bfloat(1) / denominator;
    bfloat sigmoid = gate < bfloat(0) ? y : bfloat(1) - y;
    bfloat silu = bfloat(gate * sigmoid);
    activated[expert_slot * output_width + logical_row] =
        bfloat(silu * up);
}
""",
    header: lagunaSharedSwiGLUQMVHeader + "\n" + packedTop8ParentRouterHeader,
    ensureRowContiguous: true
)

private struct PackedTop8OrderResult {
    let records: [[String: Any]]
    let controlMean: Double
    let candidateMean: Double
    let speedup: Double
}

private func packedTop8ParentR1(
    _ input: MLXArray,
    fusedWeight: MLXArray,
    packedScales: MLXArray,
    routerKeys: MLXArray
) -> MLXArray {
    packedTop8ParentR1Kernel(
        [input, fusedWeight, packedScales, routerKeys],
        grid: (LagunaConstants.numExpertsPerTok * 256 * 64, 1, 1),
        threadGroup: (64, 1, 1),
        outputShapes: [[
            1, 1, LagunaConstants.numExpertsPerTok, 1,
            LagunaConstants.moeIntermediateSize,
        ]],
        outputDTypes: [.bfloat16]
    )[0]
}

private func packedTop8FullBodyBatch(
    layers: [(MLXArray, MLXArray)],
    input: MLXArray,
    routerKeys: MLXArray,
    candidate: Bool
) -> MLXArray {
    let outputs = layers.map { weight, scales in
        if candidate {
            lagunaRoutedSwiGLUQMVPackedTop8(
                input,
                fusedWeight: weight,
                packedScales: scales,
                routerKeys: routerKeys
            )
        } else {
            packedTop8ParentR1(
                input,
                fusedWeight: weight,
                packedScales: scales,
                routerKeys: routerKeys
            )
        }
    }
    return concatenated(outputs, axis: 0)
}

private func packedTop8MeasureFullBodyBatch(
    layers: [(MLXArray, MLXArray)],
    input: MLXArray,
    routerKeys: MLXArray,
    candidate: Bool
) -> Double {
    let start = Date.timeIntervalSinceReferenceDate
    eval(packedTop8FullBodyBatch(
        layers: layers,
        input: input,
        routerKeys: routerKeys,
        candidate: candidate
    ))
    return Date.timeIntervalSinceReferenceDate - start
}

private func packedTop8Mean(_ values: [Double]) -> Double {
    values.reduce(0, +) / Double(values.count)
}

private func packedTop8MeasureOrder(
    name: String,
    candidates: [Bool],
    cycles: Int,
    layers: [(MLXArray, MLXArray)],
    input: MLXArray,
    routerKeys: MLXArray
) -> PackedTop8OrderResult {
    var controlDurations = [Double]()
    var candidateDurations = [Double]()
    var records = [[String: Any]]()
    for cycle in 0..<cycles {
        var segments = [[String: Any]]()
        for (position, isCandidate) in candidates.enumerated() {
            let duration = packedTop8MeasureFullBodyBatch(
                layers: layers,
                input: input,
                routerKeys: routerKeys,
                candidate: isCandidate
            )
            if isCandidate {
                candidateDurations.append(duration)
            } else {
                controlDurations.append(duration)
            }
            segments.append([
                "position": position,
                "variant": isCandidate ? "candidate" : "control",
                "seconds": duration,
            ])
        }
        records.append([
            "cycle": cycle,
            "order": name,
            "segments": segments,
        ])
    }
    let controlMean = packedTop8Mean(controlDurations)
    let candidateMean = packedTop8Mean(candidateDurations)
    return PackedTop8OrderResult(
        records: records,
        controlMean: controlMean,
        candidateMean: candidateMean,
        speedup: controlMean / candidateMean
    )
}

private func writePackedTop8Artifact(_ artifact: [String: Any]) throws {
    let path = ProcessInfo.processInfo.environment["MLXFAST_PACKED_TOP8_ARTIFACT_PATH"]
        ?? "/tmp/cedar-fern-packed-top8-full-body.json"
    let data = try JSONSerialization.data(
        withJSONObject: artifact,
        options: [.prettyPrinted, .sortedKeys]
    )
    try data.write(to: URL(fileURLWithPath: path), options: .atomic)
    print("PACKED_TOP8_ARTIFACT=\(path)")
}

@Test
func packedTop8FullBodyBenchmark() throws {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_PACKED_TOP8_BENCHMARK"] == "1" else {
        return
    }
    #expect(lagunaRoutedGateUpR1Enabled)
    guard lagunaRoutedGateUpR1Enabled else { return }

    let weightsPath = ProcessInfo.processInfo.environment["MLXFAST_WEIGHTS_PATH"]
        ?? URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            .appendingPathComponent("weights").path
    let config = try LagunaConfig.load(from: weightsPath)
    let loader = try LagunaWeightLoader(weightsPath: weightsPath)
    let cache = LagunaRuntimeWeightCache(loader: loader, config: config)
    let model = try cache.requireLibraryModel()
    let sparseLayers = model.model.layers.compactMap { $0.mlp as? LagunaRuntimeSparseMoEBlock }
    var layers = [(MLXArray, MLXArray)]()
    for sparse in sparseLayers {
        guard let weight = sparse._fusedRoutedGateUpWeight,
              let packedScales = sparse._packedRoutedGateUpBank
        else {
            continue
        }
        layers.append((weight, packedScales))
    }
    #expect(layers.count == 39)
    guard layers.count == 39 else { return }

    let inputValues = (0..<LagunaConstants.hiddenSize).map {
        Float(($0 % 37) - 18) / 32.0
    }
    let input = MLXArray(inputValues, [1, 1, LagunaConstants.hiddenSize]).asType(.bfloat16)
    var scores = [Float](repeating: 100, count: LagunaConstants.numExperts)
    for (rank, index) in [255, 223, 191, 159, 127, 95, 63, 31].enumerated() {
        scores[index] = Float(rank - 8)
    }
    let routerKeys = MLXArray(scores.map(packedRouterOrdinal))
    let expectedExperts = expectedPackedTop8Indices(scores)

    let control = packedTop8FullBodyBatch(
        layers: layers,
        input: input,
        routerKeys: routerKeys,
        candidate: false
    )
    let candidate = packedTop8FullBodyBatch(
        layers: layers,
        input: input,
        routerKeys: routerKeys,
        candidate: true
    )
    eval(control, candidate)
    let controlBits = control.view(dtype: .uint16).asArray(UInt16.self)
    let candidateBits = candidate.view(dtype: .uint16).asArray(UInt16.self)
    let mismatches = zip(controlBits, candidateBits).reduce(into: 0) {
        if $1.0 != $1.1 { $0 += 1 }
    }
    #expect(control.shape == candidate.shape)
    #expect(mismatches == 0)
    guard mismatches == 0 else { return }

    for isCandidate in [false, true] {
        for _ in 0..<2 {
            eval(packedTop8FullBodyBatch(
                layers: layers,
                input: input,
                routerKeys: routerKeys,
                candidate: isCandidate
            ))
        }
    }

    let started = Date.timeIntervalSinceReferenceDate
    let abba = packedTop8MeasureOrder(
        name: "ABBA",
        candidates: [false, true, true, false],
        cycles: 64,
        layers: layers,
        input: input,
        routerKeys: routerKeys
    )
    let baab = packedTop8MeasureOrder(
        name: "BAAB",
        candidates: [true, false, false, true],
        cycles: 64,
        layers: layers,
        input: input,
        routerKeys: routerKeys
    )
    let elapsed = Date.timeIntervalSinceReferenceDate - started
    let artifact: [String: Any] = [
        "architecture": String(describing: GPU.deviceInfo().architecture),
        "base_sha": "005f1a77cc6e3d5eece775603c7694e2717bd196",
        "candidate_sha": ProcessInfo.processInfo.environment["MLXFAST_EXPERIMENT_COMMIT"]
            ?? "unknown",
        "candidate_kernel": "laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v3",
        "control_kernel": "cedar_fern_packed_top8_parent_r1_bf16_v2",
        "cycles_per_order": 64,
        "elapsed_seconds": elapsed,
        "expected_experts": expectedExperts,
        "grid": [LagunaConstants.numExpertsPerTok * 256 * 64, 1, 1],
        "layer_count": layers.count,
        "output_shape": control.shape,
        "peak_memory_bytes": Int(Memory.peakMemory),
        "resource_measurement": "Metal runtime exposes no trustworthy per-kernel register, spill, or occupancy counters on this M4 host",
        "r1_enabled": lagunaRoutedGateUpR1Enabled,
        "selector_mismatches": mismatches,
        "threadgroup": [64, 1, 1],
        "weights_path": weightsPath,
        "ABBA": [
            "candidate_mean_seconds": abba.candidateMean,
            "control_mean_seconds": abba.controlMean,
            "records": abba.records,
            "speedup": abba.speedup,
        ],
        "BAAB": [
            "candidate_mean_seconds": baab.candidateMean,
            "control_mean_seconds": baab.controlMean,
            "records": baab.records,
            "speedup": baab.speedup,
        ],
    ]
    try writePackedTop8Artifact(artifact)
    print("PACKED_TOP8_ABBA_SPEEDUP=\(abba.speedup)")
    print("PACKED_TOP8_BAAB_SPEEDUP=\(baab.speedup)")
    #expect(abba.speedup >= 1.015)
    #expect(baab.speedup >= 1.015)
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
