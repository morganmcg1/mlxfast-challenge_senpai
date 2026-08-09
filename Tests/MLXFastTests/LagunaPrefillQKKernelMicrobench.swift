import Foundation
import MLX
@testable import MLXFastModel
import Testing

private enum QKExperimentError: Error {
    case missingWeightsPath
    case missingAttentionFamily
    case missingRoPEAtlases
    case bitMismatch(String, Int, UInt16, UInt16)
    case invalidLoadOrder(String)
}

private enum QKFamily: String, CaseIterable {
    case sliding
    case full

    var heads: Int {
        switch self {
        case .sliding: LagunaConstants.slidingAttentionHeads
        case .full: LagunaConstants.fullAttentionHeads
        }
    }
}

private final class QKExperimentFixture {
    let runtime: LagunaRuntimeModel
    let slidingQueryWeight: MLXArray
    let slidingKeyWeight: MLXArray
    let fullQueryWeight: MLXArray
    let fullKeyWeight: MLXArray
    let slidingAngles: MLXArray
    let fullAngles: MLXArray

    init() throws {
        guard let weightsPath = ProcessInfo.processInfo.environment[
            "MLXFAST_LAGUNA_EQUIVALENCE_WEIGHTS_PATH"
        ] else {
            throw QKExperimentError.missingWeightsPath
        }
        let config = try LagunaConfig.load(from: weightsPath)
        guard let slidingLayer = config.layerTypes.firstIndex(of: .sliding),
            let fullLayer = config.layerTypes.firstIndex(of: .full)
        else {
            throw QKExperimentError.missingAttentionFamily
        }
        let store = try DenseTensorStore(weightsPath: weightsPath)
        let bridge = MLXArrayTensorBridge()

        slidingQueryWeight = try bridge.makeArray(
            from: store.materializedTensor(
                named: LagunaWeightNames.attention(slidingLayer, "q_norm.weight")
            )
        )
        slidingKeyWeight = try bridge.makeArray(
            from: store.materializedTensor(
                named: LagunaWeightNames.attention(slidingLayer, "k_norm.weight")
            )
        )
        fullQueryWeight = try bridge.makeArray(
            from: store.materializedTensor(
                named: LagunaWeightNames.attention(fullLayer, "q_norm.weight")
            )
        )
        fullKeyWeight = try bridge.makeArray(
            from: store.materializedTensor(
                named: LagunaWeightNames.attention(fullLayer, "k_norm.weight")
            )
        )

        runtime = LagunaRuntimeModel(config)
        let atlases = runtime.model.prepareRoPEAngleAtlases()
        guard atlases.count == 2 else {
            throw QKExperimentError.missingRoPEAtlases
        }
        fullAngles = atlases[0]
        slidingAngles = atlases[1]
        eval([
            slidingQueryWeight, slidingKeyWeight, fullQueryWeight, fullKeyWeight,
            fullAngles, slidingAngles,
        ])
    }

    func invoke(
        family: QKFamily,
        rawQueries: MLXArray,
        rawKeys: MLXArray,
        offset: Int,
        length: Int,
        headsPerGroup: Int
    ) -> (MLXArray, MLXArray) {
        let offsets = MLXArray([Int32(offset)], [1])
        switch family {
        case .sliding:
            return lagunaPrefillSlidingQKNormRoPE(
                rawQueries: rawQueries,
                rawKeys: rawKeys,
                queryWeight: slidingQueryWeight,
                keyWeight: slidingKeyWeight,
                angles: slidingAngles,
                offsets: offsets,
                length: length,
                headsPerGroupOverride: headsPerGroup
            )
        case .full:
            return lagunaPrefillFullQKNormYaRN(
                rawQueries: rawQueries,
                rawKeys: rawKeys,
                queryWeight: fullQueryWeight,
                keyWeight: fullKeyWeight,
                angles: fullAngles,
                offsets: offsets,
                length: length,
                headsPerGroupOverride: headsPerGroup
            )
        }
    }
}

private let qkBitPatterns: [UInt16] = [
    0x0000, 0x8000, 0x0001, 0x8001, 0x0080, 0x8080, 0x3e00, 0xbe00,
    0x3f00, 0xbf00, 0x3f80, 0xbf80, 0x4000, 0xc000, 0x4080, 0xc080,
]

private func qkInput(length: Int, heads: Int, salt: Int) -> MLXArray {
    let width = heads * LagunaConstants.headDim
    let count = length * width
    var bits = [UInt16]()
    bits.reserveCapacity(count)
    for index in 0..<count {
        let mixed = index &* 1_315_423_911 &+ salt &* 2_654_435_761
        bits.append(qkBitPatterns[(mixed ^ (mixed >> 11)) & (qkBitPatterns.count - 1)])
    }
    return MLXArray(bits, [1, length, width]).view(dtype: .bfloat16)
}

private func requireExact(
    _ lhs: MLXArray,
    _ rhs: MLXArray,
    label: String
) throws {
    let lhsBits = lhs.view(dtype: .uint16).asArray(UInt16.self)
    let rhsBits = rhs.view(dtype: .uint16).asArray(UInt16.self)
    guard lhsBits.count == rhsBits.count else {
        throw QKExperimentError.bitMismatch(label, -1, 0, 0)
    }
    if let index = lhsBits.indices.first(where: { lhsBits[$0] != rhsBits[$0] }) {
        throw QKExperimentError.bitMismatch(label, index, lhsBits[index], rhsBits[index])
    }
}

private func verifyH4Mapping(heads: Int) throws {
    let totalHeads = heads + LagunaConstants.numKeyValueHeads
    let groups = totalHeads / 4
    let assigned = (0..<groups).flatMap { group in
        (0..<4).map { simdgroup in group * 4 + simdgroup }
    }
    guard assigned == Array(0..<totalHeads) else {
        throw QKExperimentError.bitMismatch("head-assignment", -1, 0, 0)
    }
}

private func printQKJSON(_ prefix: String, _ object: [String: Any]) throws {
    let data = try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
    print("\(prefix) \(String(decoding: data, as: UTF8.self))")
}

@Test
func lagunaPrefillQKH4BitwiseMatrix() throws {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_QK_H4_EXPERIMENT"] == "1" else {
        return
    }

    let fixture = try QKExperimentFixture()
    let lengths = [2, 3, 31, 32, 63, 64, 511, 512]
    var cases = 0

    for family in QKFamily.allCases {
        try verifyH4Mapping(heads: family.heads)
        for length in lengths {
            for offset in [1, lagunaRoPEAngleAtlasLength - length] {
                try autoreleasepool {
                    let rawQueries = qkInput(
                        length: length,
                        heads: family.heads,
                        salt: length &+ offset &+ family.heads
                    )
                    let rawKeys = qkInput(
                        length: length,
                        heads: LagunaConstants.numKeyValueHeads,
                        salt: length &+ offset &+ 97
                    )
                    let h1 = fixture.invoke(
                        family: family,
                        rawQueries: rawQueries,
                        rawKeys: rawKeys,
                        offset: offset,
                        length: length,
                        headsPerGroup: 1
                    )
                    let h4 = fixture.invoke(
                        family: family,
                        rawQueries: rawQueries,
                        rawKeys: rawKeys,
                        offset: offset,
                        length: length,
                        headsPerGroup: 4
                    )
                    eval(h1.0, h1.1, h4.0, h4.1)
                    try requireExact(h1.0, h4.0, label: "\(family.rawValue)-q-L\(length)-O\(offset)")
                    try requireExact(h1.1, h4.1, label: "\(family.rawValue)-k-L\(length)-O\(offset)")
                    cases += 1
                }
            }
        }
    }

    try autoreleasepool {
        let length = 512
        let offset = lagunaRoPEAngleAtlasLength - length
        let rawQueries = qkInput(
            length: 1,
            heads: LagunaConstants.slidingAttentionHeads,
            salt: 401
        )
        let rawKeys = qkInput(
            length: length,
            heads: LagunaConstants.numKeyValueHeads,
            salt: 409
        )
        let h1 = fixture.invoke(
            family: .sliding,
            rawQueries: rawQueries,
            rawKeys: rawKeys,
            offset: offset,
            length: length,
            headsPerGroup: 1
        )
        let h4Override = fixture.invoke(
            family: .sliding,
            rawQueries: rawQueries,
            rawKeys: rawKeys,
            offset: offset,
            length: length,
            headsPerGroup: 4
        )
        eval(h1.0, h1.1, h4Override.0, h4Override.1)
        try requireExact(h1.0, h4Override.0, label: "terminal-q")
        try requireExact(h1.1, h4Override.1, label: "terminal-k")
    }

    let config = try LagunaConfig.load(
        from: ProcessInfo.processInfo.environment["MLXFAST_LAGUNA_EQUIVALENCE_WEIGHTS_PATH"]!
    )
    let standardLayers = Array(config.layerTypes.dropLast())
    let standardFull = standardLayers.filter { $0 == .full }.count
    let standardSliding = standardLayers.filter { $0 == .sliding }.count
    #expect(standardLayers.count == 39)
    #expect(standardFull == 10)
    #expect(standardSliding == 29)

    try printQKJSON("QK_H4_CORRECTNESS", [
        "atlas_length": lagunaRoPEAngleAtlasLength,
        "bitwise_cases": cases,
        "full_h1_groups_l512": (LagunaConstants.fullAttentionHeads + LagunaConstants.numKeyValueHeads) * 512,
        "full_h4_groups_l512": (LagunaConstants.fullAttentionHeads + LagunaConstants.numKeyValueHeads) / 4 * 512,
        "full_h4_kernel": "laguna_prefill_full_qk_norm_yarn_bf16_128_v2",
        "gpu_architecture": "agxg16s",
        "gpu_cores": 20,
        "gpu_generation": 16,
        "hardware": "Mac16,11 Apple M4 Pro",
        "h1_threadgroup_threads": 32,
        "h4_mapping": "head=threadgroup_x*4+simdgroup_index",
        "h4_simdgroups": 4,
        "h4_threadgroup_threads": 128,
        "sliding_h1_groups_l512": (LagunaConstants.slidingAttentionHeads + LagunaConstants.numKeyValueHeads) * 512,
        "sliding_h4_groups_l512": (LagunaConstants.slidingAttentionHeads + LagunaConstants.numKeyValueHeads) / 4 * 512,
        "sliding_h4_kernel": "laguna_prefill_sliding_qk_norm_rope_bf16_128_v2",
        "standard_full_layers_h4": standardFull,
        "standard_sliding_layers_h4": standardSliding,
        "terminal_layer": "specialized H1 unchanged",
        "terminal_verified": true,
        "wandb_run": NSNull(),
    ])
}

private func median(_ values: [Double]) -> Double {
    let sorted = values.sorted()
    let middle = sorted.count / 2
    if sorted.count.isMultiple(of: 2) {
        return (sorted[middle - 1] + sorted[middle]) / 2
    }
    return sorted[middle]
}

private func mad(_ values: [Double]) -> Double {
    let center = median(values)
    return median(values.map { abs($0 - center) })
}

private func mean(_ values: [Double]) -> Double {
    values.reduce(0, +) / Double(values.count)
}

private func sampleStandardDeviation(_ values: [Double]) -> Double {
    let center = mean(values)
    let squared = values.reduce(0) { $0 + ($1 - center) * ($1 - center) }
    return sqrt(squared / Double(values.count - 1))
}

private func bootstrapMeanCI(_ values: [Double], seed: UInt64) -> [Double] {
    var state = seed
    var estimates = [Double]()
    estimates.reserveCapacity(10_000)
    for _ in 0..<10_000 {
        var sum = 0.0
        for _ in values.indices {
            state = state &* 6_364_136_223_846_793_005 &+ 1_442_695_040_888_963_407
            sum += values[Int(state % UInt64(values.count))]
        }
        estimates.append(sum / Double(values.count))
    }
    estimates.sort()
    return [estimates[249], estimates[9_749]]
}

private func timedInvocation(
    fixture: QKExperimentFixture,
    family: QKFamily,
    rawQueries: MLXArray,
    rawKeys: MLXArray,
    headsPerGroup: Int
) -> UInt64 {
    let outputs = fixture.invoke(
        family: family,
        rawQueries: rawQueries,
        rawKeys: rawKeys,
        offset: 257,
        length: 512,
        headsPerGroup: headsPerGroup
    )
    let start = DispatchTime.now().uptimeNanoseconds
    eval(outputs.0, outputs.1)
    return DispatchTime.now().uptimeNanoseconds - start
}

private func measurePair(
    fixture: QKExperimentFixture,
    family: QKFamily,
    rawQueries: MLXArray,
    rawKeys: MLXArray,
    h1First: Bool
) -> (h1: UInt64, h4: UInt64) {
    if h1First {
        let h1 = timedInvocation(
            fixture: fixture,
            family: family,
            rawQueries: rawQueries,
            rawKeys: rawKeys,
            headsPerGroup: 1
        )
        let h4 = timedInvocation(
            fixture: fixture,
            family: family,
            rawQueries: rawQueries,
            rawKeys: rawKeys,
            headsPerGroup: 4
        )
        return (h1, h4)
    }
    let h4 = timedInvocation(
        fixture: fixture,
        family: family,
        rawQueries: rawQueries,
        rawKeys: rawKeys,
        headsPerGroup: 4
    )
    let h1 = timedInvocation(
        fixture: fixture,
        family: family,
        rawQueries: rawQueries,
        rawKeys: rawKeys,
        headsPerGroup: 1
    )
    return (h1, h4)
}

private func benchmarkFamily(
    fixture: QKExperimentFixture,
    family: QKFamily,
    loadOrder: String
) throws -> [String: Any] {
    let loadH1First: Bool
    switch loadOrder {
    case "h1-first": loadH1First = true
    case "h4-first": loadH1First = false
    default: throw QKExperimentError.invalidLoadOrder(loadOrder)
    }

    let rawQueries = qkInput(length: 512, heads: family.heads, salt: 701 + family.heads)
    let rawKeys = qkInput(
        length: 512,
        heads: LagunaConstants.numKeyValueHeads,
        salt: 709 + family.heads
    )
    eval(rawQueries, rawKeys)

    let loadProbe = measurePair(
        fixture: fixture,
        family: family,
        rawQueries: rawQueries,
        rawKeys: rawKeys,
        h1First: loadH1First
    )
    for index in 0..<10 {
        _ = measurePair(
            fixture: fixture,
            family: family,
            rawQueries: rawQueries,
            rawKeys: rawKeys,
            h1First: index.isMultiple(of: 2) == loadH1First
        )
    }

    var h1Nanoseconds = [UInt64]()
    var h4Nanoseconds = [UInt64]()
    h1Nanoseconds.reserveCapacity(101)
    h4Nanoseconds.reserveCapacity(101)
    for index in 0..<101 {
        let pair = measurePair(
            fixture: fixture,
            family: family,
            rawQueries: rawQueries,
            rawKeys: rawKeys,
            h1First: index.isMultiple(of: 2) == loadH1First
        )
        h1Nanoseconds.append(pair.h1)
        h4Nanoseconds.append(pair.h4)
    }

    let h1 = h1Nanoseconds.map(Double.init)
    let h4 = h4Nanoseconds.map(Double.init)
    let pairedDelta = zip(h1, h4).map { $0.0 - $0.1 }
    let pairedImprovementPercent = zip(pairedDelta, h1).map { $0.0 / $0.1 * 100 }
    let h1Median = median(h1)
    let h4Median = median(h4)
    let medianImprovementPercent = (h1Median - h4Median) / h1Median * 100
    let mdePercent = 1.96 * sampleStandardDeviation(pairedImprovementPercent)
        / sqrt(Double(pairedImprovementPercent.count))
    let ci = bootstrapMeanCI(
        pairedImprovementPercent,
        seed: family == .sliding ? 0x51_1D_1A : 0xF0_11_A7
    )
    let thresholdPercent = max(5.0, 2 * mdePercent)

    return [
        "bootstrap_mean_improvement_ci95_percent": ci,
        "family": family.rawValue,
        "h1_mad_ns": mad(h1),
        "h1_median_ns": h1Median,
        "h1_ns": h1Nanoseconds.map(Int.init),
        "h4_mad_ns": mad(h4),
        "h4_median_ns": h4Median,
        "h4_ns": h4Nanoseconds.map(Int.init),
        "isolated_gate_pass": medianImprovementPercent >= thresholdPercent && ci[0] > 0,
        "load_probe_h1_ns": Int(loadProbe.h1),
        "load_probe_h4_ns": Int(loadProbe.h4),
        "mad_paired_delta_ns": mad(pairedDelta),
        "mean_paired_improvement_percent": mean(pairedImprovementPercent),
        "median_improvement_percent": medianImprovementPercent,
        "median_paired_delta_ns": median(pairedDelta),
        "mde_definition": "1.96*sample_sd(paired_improvement_percent)/sqrt(101)",
        "mde_percent": mdePercent,
        "paired_delta_ns": pairedDelta.map(Int.init),
        "paired_improvement_percent": pairedImprovementPercent,
        "sample_count": 101,
        "threshold_percent": thresholdPercent,
        "warmup_pairs": 10,
    ]
}

@Test
func lagunaPrefillQKH4Microbenchmark() throws {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_QK_H4_EXPERIMENT"] == "1" else {
        return
    }
    let loadOrder = ProcessInfo.processInfo.environment["QK_LOAD_ORDER"] ?? ""
    let fixture = try QKExperimentFixture()
    let results = try QKFamily.allCases.map {
        try benchmarkFamily(fixture: fixture, family: $0, loadOrder: loadOrder)
    }
    try printQKJSON("QK_H4_MICROBENCH", [
        "blocking_operation": "eval(q, k)",
        "commit": "research-control",
        "length": 512,
        "load_order": loadOrder,
        "results": results,
        "sample_pair_order": "alternating",
        "wandb_run": NSNull(),
    ])
}
