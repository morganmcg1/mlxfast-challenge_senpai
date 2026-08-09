import Foundation
import MLX
import MLXLMCommon
import Testing

@testable import MLXFastModel

private struct QKGeometryKernel: Codable {
    let family: String
    let headsPerGroup: Int
    let queryHeads: Int
    let keyValueHeads: Int
    let threadgroupThreads: Int
    let simdgroups: Int
    let groupsL2: Int
    let groupsL64: Int
    let groupsL512: Int
}

private struct QKGeometrySample: Codable {
    let order: String
    let h1Nanoseconds: UInt64
    let candidateNanoseconds: UInt64
}

private struct QKGeometryCell: Codable {
    let family: String
    let length: Int
    let candidateHeadsPerGroup: Int
    let warmupsPerGeometry: Int
    let samples: [QKGeometrySample]
}

private struct QKGeometryStudy: Codable {
    let hardware: [String: String]
    let standardLayerCounts: [String: Int]
    let standardDispatchCount: Int
    let terminalGeometry: String
    let weightNames: [String]
    let atlasDescription: [String: String]
    let correctnessCases: Int
    let kernels: [QKGeometryKernel]
    let cells: [QKGeometryCell]
}

private struct QKGeometryFamily {
    let name: String
    let sliding: Bool
    let heads: Int
    let queryWeight: MLXArray
    let keyWeight: MLXArray
    let angles: MLXArray
    let rawQueries: MLXArray
    let rawKeys: MLXArray
}

@Test
func lagunaPrefillQKGeometryStudy() throws {
    let environment = ProcessInfo.processInfo.environment
    guard environment["MLXFAST_RUN_PREFILL_QK_GEOMETRY_TESTS"] == "1" else {
        return
    }
    let weightsPath = try #require(environment["MLXFAST_WEIGHTS_PATH"])
    let store = try DenseTensorStore(weightsPath: weightsPath)
    let bridge = MLXArrayTensorBridge()
    let weightNames = [
        "model.layers.0.self_attn.q_norm.weight",
        "model.layers.0.self_attn.k_norm.weight",
        "model.layers.1.self_attn.q_norm.weight",
        "model.layers.1.self_attn.k_norm.weight",
    ]
    let weights = try weightNames.map {
        try bridge.makeArray(from: store.materializedTensor(named: $0))
    }
    let atlases = makeQKGeometryAtlases()
    let keyInputs = adversarialBF16Input(length: 512, width: 8 * 128)
    let families = [
        QKGeometryFamily(
            name: "sliding",
            sliding: true,
            heads: 64,
            queryWeight: weights[2],
            keyWeight: weights[3],
            angles: atlases.sliding,
            rawQueries: adversarialBF16Input(length: 512, width: 64 * 128),
            rawKeys: keyInputs
        ),
        QKGeometryFamily(
            name: "full",
            sliding: false,
            heads: 48,
            queryWeight: weights[0],
            keyWeight: weights[1],
            angles: atlases.full,
            rawQueries: adversarialBF16Input(length: 512, width: 48 * 128),
            rawKeys: keyInputs
        ),
    ]
    eval(
        weights[0], weights[1], weights[2], weights[3],
        atlases.full, atlases.sliding, keyInputs,
        families[0].rawQueries, families[1].rawQueries
    )

    var correctnessCases = 0
    for family in families {
        for length in [2, 3, 31, 32, 63, 64, 511, 512] {
            let rawQueries = family.rawQueries[0..., 0..<length, 0...]
            let rawKeys = family.rawKeys[0..., 0..<length, 0...]
            let offsets = Array(Set([0, 1, 31, 32, 63, 64, 4096 - length])).sorted()
            for offset in offsets {
                let offsetArray = MLXArray([Int32(offset)])
                let h1 = lagunaPrefillQKGeometryProbe(
                    sliding: family.sliding,
                    headsPerGroup: 1,
                    rawQueries: rawQueries,
                    rawKeys: rawKeys,
                    queryWeight: family.queryWeight,
                    keyWeight: family.keyWeight,
                    angles: family.angles,
                    offsets: offsetArray,
                    length: length
                )
                let h2 = lagunaPrefillQKGeometryProbe(
                    sliding: family.sliding,
                    headsPerGroup: 2,
                    rawQueries: rawQueries,
                    rawKeys: rawKeys,
                    queryWeight: family.queryWeight,
                    keyWeight: family.keyWeight,
                    angles: family.angles,
                    offsets: offsetArray,
                    length: length
                )
                let h4 = lagunaPrefillQKGeometryProbe(
                    sliding: family.sliding,
                    headsPerGroup: 4,
                    rawQueries: rawQueries,
                    rawKeys: rawKeys,
                    queryWeight: family.queryWeight,
                    keyWeight: family.keyWeight,
                    angles: family.angles,
                    offsets: offsetArray,
                    length: length
                )
                eval(h1.0, h1.1, h2.0, h2.1, h4.0, h4.1)
                let context = Comment(
                    rawValue: "family=\(family.name) length=\(length) offset=\(offset)")
                #expect(
                    h1.0.view(dtype: .uint16).asArray(UInt16.self)
                        == h2.0.view(dtype: .uint16).asArray(UInt16.self),
                    context
                )
                #expect(
                    h1.1.view(dtype: .uint16).asArray(UInt16.self)
                        == h2.1.view(dtype: .uint16).asArray(UInt16.self),
                    context
                )
                #expect(
                    h1.0.view(dtype: .uint16).asArray(UInt16.self)
                        == h4.0.view(dtype: .uint16).asArray(UInt16.self),
                    context
                )
                #expect(
                    h1.1.view(dtype: .uint16).asArray(UInt16.self)
                        == h4.1.view(dtype: .uint16).asArray(UInt16.self),
                    context
                )
                correctnessCases += 1
            }
        }
    }

    var cells: [QKGeometryCell] = []
    for family in families {
        for length in [2, 64, 512] {
            let rawQueries = family.rawQueries[0..., 0..<length, 0...]
            let rawKeys = family.rawKeys[0..., 0..<length, 0...]
            let offsets = MLXArray([Int32(64)])
            for headsPerGroup in [2, 4] {
                for geometry in [1, headsPerGroup] {
                    for _ in 0..<10 {
                        _ = timeQKGeometry(
                            family: family,
                            headsPerGroup: geometry,
                            rawQueries: rawQueries,
                            rawKeys: rawKeys,
                            offsets: offsets,
                            length: length
                        )
                    }
                }
                var samples: [QKGeometrySample] = []
                samples.reserveCapacity(202)
                for sampleIndex in 0..<202 {
                    if sampleIndex.isMultiple(of: 2) {
                        let h1 = timeQKGeometry(
                            family: family,
                            headsPerGroup: 1,
                            rawQueries: rawQueries,
                            rawKeys: rawKeys,
                            offsets: offsets,
                            length: length
                        )
                        let candidate = timeQKGeometry(
                            family: family,
                            headsPerGroup: headsPerGroup,
                            rawQueries: rawQueries,
                            rawKeys: rawKeys,
                            offsets: offsets,
                            length: length
                        )
                        samples.append(
                            QKGeometrySample(
                                order: "AB",
                                h1Nanoseconds: h1,
                                candidateNanoseconds: candidate
                            ))
                    } else {
                        let candidate = timeQKGeometry(
                            family: family,
                            headsPerGroup: headsPerGroup,
                            rawQueries: rawQueries,
                            rawKeys: rawKeys,
                            offsets: offsets,
                            length: length
                        )
                        let h1 = timeQKGeometry(
                            family: family,
                            headsPerGroup: 1,
                            rawQueries: rawQueries,
                            rawKeys: rawKeys,
                            offsets: offsets,
                            length: length
                        )
                        samples.append(
                            QKGeometrySample(
                                order: "BA",
                                h1Nanoseconds: h1,
                                candidateNanoseconds: candidate
                            ))
                    }
                }
                cells.append(
                    QKGeometryCell(
                        family: family.name,
                        length: length,
                        candidateHeadsPerGroup: headsPerGroup,
                        warmupsPerGeometry: 10,
                        samples: samples
                    ))
            }
        }
    }

    let kernels = families.flatMap { family in
        [1, 2, 4].map { headsPerGroup in
            let groupsPerToken = (family.heads + 8) / headsPerGroup
            return QKGeometryKernel(
                family: family.name,
                headsPerGroup: headsPerGroup,
                queryHeads: family.heads,
                keyValueHeads: 8,
                threadgroupThreads: headsPerGroup * 32,
                simdgroups: headsPerGroup,
                groupsL2: groupsPerToken * 2,
                groupsL64: groupsPerToken * 64,
                groupsL512: groupsPerToken * 512
            )
        }
    }
    let study = QKGeometryStudy(
        hardware: [
            "chip": "Apple M4 Pro",
            "gpu_generation": "16",
            "gpu_cores": "20",
            "cpu": "14 cores (10 performance, 4 efficiency)",
            "metal": "Metal 4",
        ],
        standardLayerCounts: ["sliding": 29, "full": 10],
        standardDispatchCount: 39,
        terminalGeometry: "sliding terminal wrapper remains H1/TG32",
        weightNames: weightNames,
        atlasDescription: [
            "sliding": "stock default RoPE, base 10000, dims 128, 4096 positions",
            "full": "stock YaRN RoPE, base 500000, factor 32, original 8192, dims 64, 4096 positions",
        ],
        correctnessCases: correctnessCases,
        kernels: kernels,
        cells: cells
    )
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    try encoder.encode(study).write(
        to: URL(fileURLWithPath: "score.local-qk-h2-microbench.json"))
    print("QK_GEOMETRY_CORRECTNESS_CASES=\(correctnessCases)")
    print("QK_GEOMETRY_CELLS=\(cells.count)")
}

private func makeQKGeometryAtlases() -> (full: MLXArray, sliding: MLXArray) {
    let fullRope = initializeRope(
        dims: 64,
        base: 500_000,
        traditional: false,
        scalingConfig: [
            "rope_type": .string("yarn"),
            "factor": .float(32),
            "original_max_position_embeddings": .int(8192),
            "beta_fast": .float(64),
            "beta_slow": .float(1),
        ],
        maxPositionEmbeddings: 262_144
    )
    let slidingRope = initializeRope(
        dims: 128,
        base: 10_000,
        traditional: false,
        scalingConfig: ["rope_type": .string("default")],
        maxPositionEmbeddings: 262_144
    )
    let fullSeed = MLXArray(
        Array(repeating: Float(0.7426255941390991), count: 32)
            + Array(repeating: Float(0), count: 32),
        [1, 1, 1, 64]
    )
    let slidingSeed = MLXArray(
        Array(repeating: Float(1), count: 64)
            + Array(repeating: Float(0), count: 64),
        [1, 1, 1, 128]
    )
    return (
        fullRope(broadcast(fullSeed, to: [1, 1, 4096, 64]), offset: 0),
        slidingRope(broadcast(slidingSeed, to: [1, 1, 4096, 128]), offset: 0)
    )
}

private func adversarialBF16Input(length: Int, width: Int) -> MLXArray {
    let pattern: [Float] = [
        0, -0, 1e-38, -1e-38, 1e-10, -1e-10, 0.5, -0.5,
        1, -1, 3.5, -3.5, 64, -64, 1_000, -1_000,
        Float.pi, -Float.pi, 0.333251953125, -0.333251953125,
    ]
    let values = (0..<(length * width)).map { pattern[$0 % pattern.count] }
    return MLXArray(values, [1, length, width]).asType(.bfloat16)
}

private func timeQKGeometry(
    family: QKGeometryFamily,
    headsPerGroup: Int,
    rawQueries: MLXArray,
    rawKeys: MLXArray,
    offsets: MLXArray,
    length: Int
) -> UInt64 {
    let start = DispatchTime.now().uptimeNanoseconds
    let outputs = lagunaPrefillQKGeometryProbe(
        sliding: family.sliding,
        headsPerGroup: headsPerGroup,
        rawQueries: rawQueries,
        rawKeys: rawKeys,
        queryWeight: family.queryWeight,
        keyWeight: family.keyWeight,
        angles: family.angles,
        offsets: offsets,
        length: length
    )
    eval(outputs.0, outputs.1)
    return DispatchTime.now().uptimeNanoseconds - start
}
