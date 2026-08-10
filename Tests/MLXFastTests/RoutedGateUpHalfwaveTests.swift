import Foundation
import MLX
@testable import MLXFastModel
import Testing

private let halfwaveFetchCount = 8 * 512 * 2 * 4 * 32
private let halfwaveDecodeBaselineSeconds = 0.0128366158828125
private let halfwaveRequiredSavingsSeconds = 18e-6
private let halfwaveRequiredDecodeSpeedup = 1.001334

private struct HalfwaveOrderResult {
    let records: [[String: Any]]
    let savings: [Double]
    let meanSavings: Double
    let lower95Savings: Double
}

private func halfwaveLoadSource(
    candidate: Bool,
    target: String,
    address: String
) -> String {
    if candidate {
        return """
        {
            uint4 pair = uint4(0u);
            if (code_owner) {
                pair = *(const device uint4*)(\(address));
            }
            const uint2 peer = simd_shuffle_xor(pair.zw, ushort(1));
            \(target) = code_owner ? pair.xy : peer;
        }
        """
    }
    return "\(target) = *(const device uint2*)(\(address));"
}

private func halfwaveFetchSource(candidate: Bool, corrupt: Bool = false) -> String {
    let load = halfwaveLoadSource(
        candidate: candidate,
        target: "codes",
        address: "expert_weight + row * fused_row_bytes + block * 256 + lane * 8"
    )
    return """
    constexpr uint fused_row_bytes = 1024;
    constexpr uint fused_expert_bytes = 1024 * fused_row_bytes;
    uint gid = thread_position_in_grid.x;
    uint lane = gid % 32;
    uint item = gid / 32;
    uint block = item % 4;
    item /= 4;
    uint projection = item % 2;
    item /= 2;
    uint logical_row = item % 512;
    uint expert_slot = item / 512;
    uint expert = indices[expert_slot];
    uint gate_row = (logical_row / 32) * 64 + logical_row % 32;
    uint row = gate_row + projection * 32;
    const device uint8_t* expert_weight =
        (const device uint8_t*)fused_weight + expert * fused_expert_bytes;
    const bool code_owner = (lane & 1u) == 0u;
    uint2 codes;
    \(load)
    if (\(corrupt ? "gid == 17" : "false")) {
        codes.x ^= 1u;
    }
    fetched[gid * 2] = codes.x;
    fetched[gid * 2 + 1] = codes.y;
    """
}

private func halfwaveSyntheticSource(candidate: Bool) -> String {
    let load = halfwaveLoadSource(
        candidate: candidate,
        target: "codes",
        address: "base + lane * 8"
    )
    return """
    uint lane = thread_position_in_grid.x;
    const device uint8_t* base =
        (const device uint8_t*)packed_codes + offset_bytes[0];
    const bool code_owner = (lane & 1u) == 0u;
    uint2 codes;
    \(load)
    fetched[lane * 2] = codes.x;
    fetched[lane * 2 + 1] = codes.y;
    """
}

private func halfwaveActivationSource(candidate: Bool, singleBlock: Int? = nil) -> String {
    let initialGate = halfwaveLoadSource(
        candidate: candidate,
        target: "gate_codes",
        address: "expert_weight + gate_row * fused_row_bytes + lane * 8"
    )
    let initialUp = halfwaveLoadSource(
        candidate: candidate,
        target: "up_codes",
        address: "expert_weight + up_row * fused_row_bytes + lane * 8"
    )
    let nextGate = halfwaveLoadSource(
        candidate: candidate,
        target: "gate_codes",
        address: "expert_weight + gate_row * fused_row_bytes + next_block / 2 + lane * 8"
    )
    let nextUp = halfwaveLoadSource(
        candidate: candidate,
        target: "up_codes",
        address: "expert_weight + up_row * fused_row_bytes + next_block / 2 + lane * 8"
    )
    let blockBody: String
    if let singleBlock {
        let byteOffset = singleBlock * 256
        let blockGate = halfwaveLoadSource(
            candidate: candidate,
            target: "gate_codes",
            address: "expert_weight + gate_row * fused_row_bytes + \(byteOffset) + lane * 8"
        )
        let blockUp = halfwaveLoadSource(
            candidate: candidate,
            target: "up_codes",
            address: "expert_weight + up_row * fused_row_bytes + \(byteOffset) + lane * 8"
        )
        blockBody = """
        const device uint8_t* block_scales =
            row_scales + \(singleBlock) * scale_kblock_bytes
            + sub * 2 * scale_row_bytes + (lane >> 1);
        bool patch_lane = \(singleBlock == 0 ? "expert == 0 && logical_row == 0 && lane == 1" : "false");
        uint8_t gate_sb = patch_lane ? packed_scales[0] : block_scales[0];
        uint8_t up_sb = patch_lane ? packed_scales[1] : block_scales[scale_row_bytes];
        uint2 gate_codes;
        uint2 up_codes;
        \(blockGate)
        \(blockUp)
        const device vec<bfloat, 4>* input_vectors =
            (const device vec<bfloat, 4>*)(input + \(singleBlock * 512) + lane * values_per_lane);
        for (uint i = 0; i < values_per_lane / 4; ++i) {
            const vec<bfloat, 4> values = input_vectors[i];
            input_values[4 * i] = values[0];
            input_values[4 * i + 1] = values[1];
            input_values[4 * i + 2] = values[2];
            input_values[4 * i + 3] = values[3];
        }
        gate_result += laguna_nvfp4_qdot_codes_16(
            gate_codes, input_values, laguna_nvfp4_scale(gate_sb));
        up_result += laguna_nvfp4_qdot_codes_16(
            up_codes, input_values, laguna_nvfp4_scale(up_sb));
        """
    } else {
        blockBody = """
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
            \(initialGate)
            \(initialUp)
        }
        for (uint block = 0; block < input_width; block += block_width) {
            const device vec<bfloat, 4>* input_vectors =
                (const device vec<bfloat, 4>*)(input + block + lane * values_per_lane);
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
                \(nextGate)
                \(nextUp)
            }
            gate_result += laguna_nvfp4_qdot_codes_16(
                cur_gate_codes, input_values, laguna_nvfp4_scale(cur_gate_sb));
            up_result += laguna_nvfp4_qdot_codes_16(
                cur_up_codes, input_values, laguna_nvfp4_scale(cur_up_sb));
        }
        """
    }
    return """
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
    uint expert = indices[expert_slot];
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
    const bool code_owner = (lane & 1u) == 0u;
    \(blockBody)
    gate_result = simd_sum(gate_result);
    up_result = simd_sum(up_result);
    if (lane == 0) {
        bfloat gate = bfloat(gate_result\(lagunaNvfp4RowScaleSuffix));
        bfloat up = bfloat(up_result\(lagunaNvfp4RowScaleSuffix));
        bfloat exp_abs = metal::exp(metal::abs(gate));
        bfloat denominator = bfloat(1) + exp_abs;
        bfloat y = bfloat(1) / denominator;
        bfloat sigmoid = gate < bfloat(0) ? y : bfloat(1) - y;
        bfloat result = bfloat(bfloat(gate * sigmoid) * up);
        if (control[0] == 0xFFFFFFFFu && group == 0u) {
            result += prev[0];
        }
        activated[expert_slot * output_width + logical_row] = result;
    }
    """
}

private let halfwaveFetchStockKernel = MLXFast.metalKernel(
    name: "cedar_halfwave_fetch_stock_v1",
    inputNames: ["fused_weight", "indices"],
    outputNames: ["fetched"],
    source: halfwaveFetchSource(candidate: false),
    ensureRowContiguous: true
)

private let halfwaveFetchCandidateKernel = MLXFast.metalKernel(
    name: "cedar_halfwave_fetch_candidate_v1",
    inputNames: ["fused_weight", "indices"],
    outputNames: ["fetched"],
    source: halfwaveFetchSource(candidate: true),
    ensureRowContiguous: true
)

private let halfwaveFetchCorruptKernel = MLXFast.metalKernel(
    name: "cedar_halfwave_fetch_corrupt_v1",
    inputNames: ["fused_weight", "indices"],
    outputNames: ["fetched"],
    source: halfwaveFetchSource(candidate: true, corrupt: true),
    ensureRowContiguous: true
)

private let halfwaveSyntheticStockKernel = MLXFast.metalKernel(
    name: "cedar_halfwave_synthetic_stock_v1",
    inputNames: ["packed_codes", "offset_bytes"],
    outputNames: ["fetched"],
    source: halfwaveSyntheticSource(candidate: false),
    ensureRowContiguous: true
)

private let halfwaveSyntheticCandidateKernel = MLXFast.metalKernel(
    name: "cedar_halfwave_synthetic_candidate_v1",
    inputNames: ["packed_codes", "offset_bytes"],
    outputNames: ["fetched"],
    source: halfwaveSyntheticSource(candidate: true),
    ensureRowContiguous: true
)

private let halfwaveActivationStockKernel = MLXFast.metalKernel(
    name: "cedar_halfwave_activation_stock_v1",
    inputNames: ["input", "fused_weight", "packed_scales", "indices", "prev", "control"],
    outputNames: ["activated"],
    source: halfwaveActivationSource(candidate: false),
    header: lagunaSharedSwiGLUQMVHeader,
    ensureRowContiguous: true
)

private let halfwaveActivationCandidateKernel = MLXFast.metalKernel(
    name: "cedar_halfwave_activation_candidate_v1",
    inputNames: ["input", "fused_weight", "packed_scales", "indices", "prev", "control"],
    outputNames: ["activated"],
    source: halfwaveActivationSource(candidate: true),
    header: lagunaSharedSwiGLUQMVHeader,
    ensureRowContiguous: true
)

private let halfwaveBlockStockKernels = Array(0..<4).map { (block: Int) in
    MLXFast.metalKernel(
        name: "cedar_halfwave_block\(block)_stock_v1",
        inputNames: ["input", "fused_weight", "packed_scales", "indices", "prev", "control"],
        outputNames: ["activated"],
        source: halfwaveActivationSource(candidate: false, singleBlock: block),
        header: lagunaSharedSwiGLUQMVHeader,
        ensureRowContiguous: true
    )
}

private let halfwaveBlockCandidateKernels = Array(0..<4).map { (block: Int) in
    MLXFast.metalKernel(
        name: "cedar_halfwave_block\(block)_candidate_v1",
        inputNames: ["input", "fused_weight", "packed_scales", "indices", "prev", "control"],
        outputNames: ["activated"],
        source: halfwaveActivationSource(candidate: true, singleBlock: block),
        header: lagunaSharedSwiGLUQMVHeader,
        ensureRowContiguous: true
    )
}

private func halfwaveFetch(
    _ weight: MLXArray,
    indices: MLXArray,
    candidate: Bool,
    corrupt: Bool = false
) -> MLXArray {
    let kernel = corrupt
        ? halfwaveFetchCorruptKernel
        : (candidate ? halfwaveFetchCandidateKernel : halfwaveFetchStockKernel)
    return kernel(
        [weight, indices],
        grid: (halfwaveFetchCount, 1, 1),
        threadGroup: (32, 1, 1),
        outputShapes: [[halfwaveFetchCount, 2]],
        outputDTypes: [.uint32]
    )[0]
}

private func halfwaveSyntheticFetch(
    _ codes: MLXArray,
    byteOffset: UInt32,
    candidateRequested: Bool
) -> (MLXArray, Bool) {
    let candidateSelected = candidateRequested && byteOffset.isMultiple(of: 16)
    let kernel = candidateSelected ? halfwaveSyntheticCandidateKernel : halfwaveSyntheticStockKernel
    let offset = MLXArray([byteOffset])
    let output = kernel(
        [codes, offset],
        grid: (32, 1, 1),
        threadGroup: (32, 1, 1),
        outputShapes: [[32, 2]],
        outputDTypes: [.uint32]
    )[0]
    return (output, candidateSelected)
}

private func halfwaveActivation(
    input: MLXArray,
    weight: MLXArray,
    scales: MLXArray,
    indices: MLXArray,
    previous: MLXArray,
    control: MLXArray,
    candidate: Bool,
    singleBlock: Int? = nil
) -> MLXArray {
    let inputs = [input, weight, scales, indices, previous, control]
    let outputs: [MLXArray]
    if let singleBlock {
        let kernel = candidate
            ? halfwaveBlockCandidateKernels[singleBlock]
            : halfwaveBlockStockKernels[singleBlock]
        outputs = kernel(
            inputs,
            grid: (8 * 256 * 64, 1, 1),
            threadGroup: (64, 1, 1),
            outputShapes: [[1, 1, 8, 1, 512]],
            outputDTypes: [.bfloat16]
        )
    } else if candidate {
        outputs = halfwaveActivationCandidateKernel(
            inputs,
            grid: (8 * 256 * 64, 1, 1),
            threadGroup: (64, 1, 1),
            outputShapes: [[1, 1, 8, 1, 512]],
            outputDTypes: [.bfloat16]
        )
    } else {
        outputs = halfwaveActivationStockKernel(
            inputs,
            grid: (8 * 256 * 64, 1, 1),
            threadGroup: (64, 1, 1),
            outputShapes: [[1, 1, 8, 1, 512]],
            outputDTypes: [.bfloat16]
        )
    }
    return outputs[0]
}

private func halfwaveMismatchCount<T: Equatable>(_ lhs: [T], _ rhs: [T]) -> Int {
    guard lhs.count == rhs.count else { return max(lhs.count, rhs.count) }
    var mismatches = 0
    for index in lhs.indices where lhs[index] != rhs[index] {
        mismatches += 1
    }
    return mismatches
}

private func halfwaveMean(_ values: [Double]) -> Double {
    values.reduce(0, +) / Double(values.count)
}

private func halfwaveBootstrapLower95(_ samples: [Double], seed: UInt64) -> Double {
    var state = seed
    var means = [Double]()
    means.reserveCapacity(20_000)
    for _ in 0..<20_000 {
        var sum = 0.0
        for _ in samples.indices {
            state ^= state << 13
            state ^= state >> 7
            state ^= state << 17
            sum += samples[Int(state % UInt64(samples.count))]
        }
        means.append(sum / Double(samples.count))
    }
    means.sort()
    return means[Int(Double(means.count - 1) * 0.025)]
}

private func halfwaveRunChain(
    layers: [(MLXArray, MLXArray)],
    input: MLXArray,
    indices: MLXArray,
    control: MLXArray,
    candidate: Bool,
    singleBlock: Int? = nil
) -> MLXArray {
    var previous = MLXArray.zeros([1, 1, 8, 1, 512], dtype: .bfloat16)
    for (weight, scales) in layers {
        previous = halfwaveActivation(
            input: input,
            weight: weight,
            scales: scales,
            indices: indices,
            previous: previous,
            control: control,
            candidate: candidate,
            singleBlock: singleBlock
        )
    }
    return previous
}

private func halfwaveMeasureChain(
    layers: [(MLXArray, MLXArray)],
    input: MLXArray,
    indices: MLXArray,
    control: MLXArray,
    candidate: Bool,
    singleBlock: Int? = nil
) -> Double {
    let start = Date.timeIntervalSinceReferenceDate
    let tail = halfwaveRunChain(
        layers: layers,
        input: input,
        indices: indices,
        control: control,
        candidate: candidate,
        singleBlock: singleBlock
    )
    eval(tail)
    return Date.timeIntervalSinceReferenceDate - start
}

private func halfwaveMeasureOrder(
    name: String,
    candidates: [Bool],
    cycles: Int,
    layers: [(MLXArray, MLXArray)],
    input: MLXArray,
    indices: MLXArray,
    control: MLXArray
) -> HalfwaveOrderResult {
    var records = [[String: Any]]()
    var savings = [Double]()
    for cycle in 0..<cycles {
        var stock = [Double]()
        var candidate = [Double]()
        var segments = [[String: Any]]()
        for (position, isCandidate) in candidates.enumerated() {
            let duration = halfwaveMeasureChain(
                layers: layers,
                input: input,
                indices: indices,
                control: control,
                candidate: isCandidate
            )
            if isCandidate {
                candidate.append(duration)
            } else {
                stock.append(duration)
            }
            segments.append([
                "position": position,
                "variant": isCandidate ? "candidate" : "stock",
                "seconds": duration,
            ])
        }
        let saving = halfwaveMean(stock) - halfwaveMean(candidate)
        savings.append(saving)
        records.append([
            "cycle": cycle,
            "order": name,
            "segments": segments,
            "saving_seconds": saving,
        ])
    }
    return HalfwaveOrderResult(
        records: records,
        savings: savings,
        meanSavings: halfwaveMean(savings),
        lower95Savings: halfwaveBootstrapLower95(savings, seed: name == "ABBA" ? 0xCE_DA_12 : 0xFE_42_91)
    )
}

private func halfwaveWriteArtifact(_ artifact: [String: Any]) throws {
    let path = ProcessInfo.processInfo.environment["MLXFAST_HALFWAVE_ARTIFACT_PATH"]
        ?? "/tmp/cedar-fern-halfwave-gates.json"
    let data = try JSONSerialization.data(
        withJSONObject: artifact,
        options: [.prettyPrinted, .sortedKeys]
    )
    try data.write(to: URL(fileURLWithPath: path), options: .atomic)
    print("HALFWAVE_ARTIFACT=\(path)")
}

@Test
func routedGateUpHalfwaveGate1AndGate2() throws {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_HALFWAVE_GATES"] == "1" else {
        return
    }

    let weightsPath = ProcessInfo.processInfo.environment["MLXFAST_WEIGHTS_PATH"]
        ?? URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            .appendingPathComponent("weights").path
    let config = try LagunaConfig.load(from: weightsPath)
    let loader = try LagunaWeightLoader(weightsPath: weightsPath)
    let cache = LagunaRuntimeWeightCache(loader: loader, config: config)
    let model = try cache.requireLibraryModel()
    let sparseLayers = model.model.layers.compactMap { $0.mlp as? LagunaRuntimeSparseMoEBlock }
    let indices = MLXArray([UInt32(0), 255, 0, 255, 0, 255, 0, 255])
    let inputValues = (0..<2048).map { index in
        Float((index % 37) - 18) / 32.0
    }
    let input = MLXArray(inputValues, [1, 1, 2048]).asType(.bfloat16)
    let control = MLXArray([UInt32(0)])
    var layerBanks = [(MLXArray, MLXArray)]()
    var fetchLayerResults = [[String: Any]]()
    var activationLayerResults = [[String: Any]]()
    var retainedScaleCount = 0
    var gate1Pass = sparseLayers.count == 39

    for (layerIndex, sparse) in sparseLayers.enumerated() {
        guard let weight = sparse._fusedRoutedGateUpWeight,
              let packedScales = sparse._packedRoutedGateUpBank
        else {
            gate1Pass = false
            continue
        }
        if sparse._fusedRoutedGateUpScales != nil {
            retainedScaleCount += 1
        } else {
            gate1Pass = false
        }
        layerBanks.append((weight, packedScales))

        let stockFetch = halfwaveFetch(weight, indices: indices, candidate: false)
        let candidateFetch = halfwaveFetch(weight, indices: indices, candidate: true)
        eval(stockFetch, candidateFetch)
        let fetchMismatches = halfwaveMismatchCount(
            stockFetch.asArray(UInt32.self),
            candidateFetch.asArray(UInt32.self)
        )
        fetchLayerResults.append([
            "layer": layerIndex + 1,
            "addresses": halfwaveFetchCount,
            "uint32_values": halfwaveFetchCount * 2,
            "mismatches": fetchMismatches,
        ])
        gate1Pass = gate1Pass && fetchMismatches == 0

        let seed = MLXArray.zeros([1, 1, 8, 1, 512], dtype: .bfloat16)
        let stockActivation = halfwaveActivation(
            input: input,
            weight: weight,
            scales: packedScales,
            indices: indices,
            previous: seed,
            control: control,
            candidate: false
        )
        let candidateActivation = halfwaveActivation(
            input: input,
            weight: weight,
            scales: packedScales,
            indices: indices,
            previous: seed,
            control: control,
            candidate: true
        )
        eval(stockActivation, candidateActivation)
        let activationMismatches = halfwaveMismatchCount(
            stockActivation.view(dtype: .uint16).asArray(UInt16.self),
            candidateActivation.view(dtype: .uint16).asArray(UInt16.self)
        )
        activationLayerResults.append([
            "layer": layerIndex + 1,
            "bf16_values": 8 * 512,
            "mismatches": activationMismatches,
        ])
        gate1Pass = gate1Pass && activationMismatches == 0
    }

    var adversarialWords = [UInt32]()
    let adversarialPattern: [UInt32] = [
        0x0000_0000, 0xFFFF_FFFF, 0xAAAA_AAAA, 0x5555_5555,
        0x0123_4567, 0x89AB_CDEF, 0x7654_3210, 0xFEDC_BA98,
    ]
    while adversarialWords.count < 68 {
        adversarialWords.append(contentsOf: adversarialPattern)
    }
    adversarialWords.removeLast(adversarialWords.count - 68)
    let adversarialCodes = MLXArray(adversarialWords)
    let (syntheticStock, _) = halfwaveSyntheticFetch(
        adversarialCodes,
        byteOffset: 0,
        candidateRequested: false
    )
    let (syntheticCandidate, syntheticCandidateSelected) = halfwaveSyntheticFetch(
        adversarialCodes,
        byteOffset: 0,
        candidateRequested: true
    )
    let (fallbackStock, fallbackCandidateSelected) = halfwaveSyntheticFetch(
        adversarialCodes,
        byteOffset: 8,
        candidateRequested: true
    )
    let (fallbackReference, _) = halfwaveSyntheticFetch(
        adversarialCodes,
        byteOffset: 8,
        candidateRequested: false
    )
    eval(syntheticStock, syntheticCandidate, fallbackStock, fallbackReference)
    let syntheticMismatches = halfwaveMismatchCount(
        syntheticStock.asArray(UInt32.self),
        syntheticCandidate.asArray(UInt32.self)
    )
    let fallbackMismatches = halfwaveMismatchCount(
        fallbackStock.asArray(UInt32.self),
        fallbackReference.asArray(UInt32.self)
    )
    gate1Pass = gate1Pass
        && syntheticMismatches == 0
        && fallbackMismatches == 0
        && syntheticCandidateSelected
        && !fallbackCandidateSelected

    var corruptionMismatches = 0
    if let firstWeight = layerBanks.first?.0 {
        let reference = halfwaveFetch(firstWeight, indices: indices, candidate: false)
        let corrupt = halfwaveFetch(
            firstWeight,
            indices: indices,
            candidate: true,
            corrupt: true
        )
        eval(reference, corrupt)
        corruptionMismatches = halfwaveMismatchCount(
            reference.asArray(UInt32.self),
            corrupt.asArray(UInt32.self)
        )
    }
    gate1Pass = gate1Pass && corruptionMismatches > 0

    var artifact: [String: Any] = [
        "architecture": String(describing: GPU.deviceInfo().architecture),
        "peak_memory_bytes": Int(Memory.peakMemory),
        "weights_path": weightsPath,
        "sparse_layer_count": sparseLayers.count,
        "retained_full_scale_layer_count": retainedScaleCount,
        "expert_ids": [0, 255, 0, 255, 0, 255, 0, 255],
        "fetch_layers": fetchLayerResults,
        "activation_layers": activationLayerResults,
        "synthetic_adversarial_mismatches": syntheticMismatches,
        "aligned_candidate_selected": syntheticCandidateSelected,
        "fallback_offset_bytes": 8,
        "fallback_selected_stock": !fallbackCandidateSelected,
        "fallback_mismatches": fallbackMismatches,
        "positive_corruption_mismatches": corruptionMismatches,
        "gate1_pass": gate1Pass,
    ]

    guard gate1Pass else {
        artifact["gate2_skipped"] = true
        try halfwaveWriteArtifact(artifact)
        #expect(gate1Pass)
        return
    }

    for candidate in [false, true] {
        for _ in 0..<2 {
            let tail = halfwaveRunChain(
                layers: layerBanks,
                input: input,
                indices: indices,
                control: control,
                candidate: candidate
            )
            eval(tail)
        }
    }

    let abba = halfwaveMeasureOrder(
        name: "ABBA",
        candidates: [false, true, true, false],
        cycles: 64,
        layers: layerBanks,
        input: input,
        indices: indices,
        control: control
    )
    let baab = halfwaveMeasureOrder(
        name: "BAAB",
        candidates: [true, false, false, true],
        cycles: 64,
        layers: layerBanks,
        input: input,
        indices: indices,
        control: control
    )

    var blockResults = [[String: Any]]()
    var blockFamiliesPass = true
    for block in 0..<4 {
        for candidate in [false, true] {
            let tail = halfwaveRunChain(
                layers: layerBanks,
                input: input,
                indices: indices,
                control: control,
                candidate: candidate,
                singleBlock: block
            )
            eval(tail)
        }
        var savings = [Double]()
        var records = [[String: Any]]()
        for cycle in 0..<16 {
            let order = cycle.isMultiple(of: 2) ? [false, true] : [true, false]
            var stock = 0.0
            var candidate = 0.0
            var segments = [[String: Any]]()
            for isCandidate in order {
                let duration = halfwaveMeasureChain(
                    layers: layerBanks,
                    input: input,
                    indices: indices,
                    control: control,
                    candidate: isCandidate,
                    singleBlock: block
                )
                if isCandidate { candidate = duration } else { stock = duration }
                segments.append([
                    "variant": isCandidate ? "candidate" : "stock",
                    "seconds": duration,
                ])
            }
            let saving = stock - candidate
            savings.append(saving)
            records.append([
                "cycle": cycle,
                "segments": segments,
                "saving_seconds": saving,
            ])
        }
        let meanSaving = halfwaveMean(savings)
        let blockPass = meanSaving >= -5e-6
        blockFamiliesPass = blockFamiliesPass && blockPass
        blockResults.append([
            "block": block,
            "records": records,
            "mean_saving_seconds": meanSaving,
            "material_regression_bound_seconds": -5e-6,
            "pass": blockPass,
        ])
    }

    let combinedSavings = (abba.meanSavings + baab.meanSavings) / 2
    let projectedCandidateSeconds = halfwaveDecodeBaselineSeconds - combinedSavings
    let projectedDecodeSpeedup = halfwaveDecodeBaselineSeconds / projectedCandidateSeconds
    let gate2Pass = abba.meanSavings >= halfwaveRequiredSavingsSeconds
        && baab.meanSavings >= halfwaveRequiredSavingsSeconds
        && abba.lower95Savings > 0
        && baab.lower95Savings > 0
        && blockFamiliesPass
        && projectedDecodeSpeedup >= halfwaveRequiredDecodeSpeedup

    artifact["peak_memory_bytes"] = Int(Memory.peakMemory)
    artifact["gate2"] = [
        "required_order_saving_seconds": halfwaveRequiredSavingsSeconds,
        "required_decode_speedup": halfwaveRequiredDecodeSpeedup,
        "baseline_decode_seconds": halfwaveDecodeBaselineSeconds,
        "ABBA": [
            "records": abba.records,
            "mean_saving_seconds": abba.meanSavings,
            "bootstrap_lower95_saving_seconds": abba.lower95Savings,
        ],
        "BAAB": [
            "records": baab.records,
            "mean_saving_seconds": baab.meanSavings,
            "bootstrap_lower95_saving_seconds": baab.lower95Savings,
        ],
        "combined_mean_saving_seconds": combinedSavings,
        "projected_candidate_decode_seconds": projectedCandidateSeconds,
        "projected_decode_speedup": projectedDecodeSpeedup,
        "block_families": blockResults,
        "block_families_pass": blockFamiliesPass,
        "pass": gate2Pass,
    ]
    artifact["gate2_pass"] = gate2Pass
    try halfwaveWriteArtifact(artifact)

    #expect(fetchLayerResults.allSatisfy { ($0["mismatches"] as? Int) == 0 })
    #expect(activationLayerResults.allSatisfy { ($0["mismatches"] as? Int) == 0 })
    #expect(corruptionMismatches > 0)
}
