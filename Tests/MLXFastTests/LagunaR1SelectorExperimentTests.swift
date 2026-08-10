import Foundation
import MLX
@testable import MLXFastModel
import Testing

private enum R1SelectorExperimentError: Error, CustomStringConvertible {
    case missingEnvironment(String)
    case missingPreparedWeights(Int)
    case unexpectedSparseLayerCount(Int)
    case mismatch(String)

    var description: String {
        switch self {
        case .missingEnvironment(let name):
            return "missing required environment variable \(name)"
        case .missingPreparedWeights(let layer):
            return "sparse layer \(layer) lacks prepared routed gate/up weights"
        case .unexpectedSparseLayerCount(let count):
            return "expected 39 sparse layers, found \(count)"
        case .mismatch(let detail):
            return detail
        }
    }
}

private struct R1SelectorCase {
    let name: String
    let keys: [UInt32]
}

private struct R1PreparedBlock {
    let layer: Int
    let block: LagunaRuntimeSparseMoEBlock
    let fusedWeight: MLXArray
    let packedScales: MLXArray
}

private struct R1LoadedModel {
    let cache: LagunaRuntimeWeightCache
    let blocks: [R1PreparedBlock]
}

private struct R1SourceEvidence: Codable {
    let candidateBarrierCount: Int
    let duplicateBarrierCount: Int
    let candidateRoundCallCount: Int
    let duplicateRoundCallCount: Int
    let candidateSharedWinnerCount: Int
    let candidateSIMDGroupZeroGuardCount: Int
    let candidateThreadgroupSize: Int
    let candidateSIMDGroupsPerThreadgroup: Int
}

private struct R1ExactnessCaseEvidence: Codable {
    let name: String
    let expectedWinners: [UInt32]
}

private struct R1ExactnessArtifact: Codable {
    let createdAt: Date
    let architecture: String
    let operatingSystem: String
    let physicalMemoryBytes: UInt64
    let sparseLayerCount: Int
    let selectorCaseCount: Int
    let selectorComparisons: Int
    let activationComparisons: Int
    let activationBitsCompared: Int
    let positiveCorruptionDetected: Bool
    let sourceEvidence: R1SourceEvidence
    let cases: [R1ExactnessCaseEvidence]
}

private struct R1TimingRecord: Codable {
    let order: String
    let cycle: Int
    let position: Int
    let arm: String
    let elapsedNanoseconds: UInt64
}

private struct R1TimingArtifact: Codable {
    let createdAt: Date
    let architecture: String
    let operatingSystem: String
    let physicalMemoryBytes: UInt64
    let sparseLayerCount: Int
    let warmupSamplesPerArm: Int
    let cyclesPerOrder: Int
    let orders: [String]
    let sourceEvidence: R1SourceEvidence
    let records: [R1TimingRecord]
}

@Test
func r1SelectorSharingMatchesDuplicateSelectorAcrossRealSparseLayers() throws {
    guard ProcessInfo.processInfo.environment["MLXFAST_R1_SELECTOR_MODE"] == "exactness" else {
        return
    }

    let artifactPath = try r1RequiredEnvironment("MLXFAST_R1_SELECTOR_ARTIFACT_PATH")
    let loaded = try r1LoadPreparedModel()
    let input = r1DeterministicInput()
    let cases = r1SelectorCases()
    let sourceEvidence = try r1ValidateSourceEvidence()

    var selectorComparisons = 0
    var activationComparisons = 0
    var activationBitsCompared = 0
    var positiveCorruptionDetected = false
    var caseEvidence: [R1ExactnessCaseEvidence] = []

    for selectorCase in cases {
        let routerKeys = MLXArray(selectorCase.keys, [LagunaConstants.numExperts])
        let expectedWinners = r1ExpectedWinners(selectorCase.keys)
        let expectedPairs = expectedWinners.flatMap { [$0, $0] }
        let duplicateWinners = lagunaR1SelectorExperimentWinners(
            routerKeys, useSharedSelector: false)
        let sharedWinners = lagunaR1SelectorExperimentWinners(
            routerKeys, useSharedSelector: true)
        eval(duplicateWinners, sharedWinners)
        let duplicateValues = duplicateWinners.asArray(UInt32.self)
        let sharedValues = sharedWinners.asArray(UInt32.self)
        try r1RequireEqual(
            duplicateValues, expectedPairs,
            label: "selector duplicate \(selectorCase.name)")
        try r1RequireEqual(
            sharedValues, expectedPairs,
            label: "selector shared \(selectorCase.name)")
        try r1RequireEqual(
            sharedValues, duplicateValues,
            label: "selector A/B \(selectorCase.name)")
        selectorComparisons += 3

        if !positiveCorruptionDetected {
            var corrupted = expectedPairs
            corrupted[0] ^= 1
            positiveCorruptionDetected = corrupted != duplicateValues
        }

        for prepared in loaded.blocks {
            let duplicate = lagunaR1SelectorExperimentGateUp(
                input,
                fusedWeight: prepared.fusedWeight,
                packedScales: prepared.packedScales,
                routerKeys: routerKeys,
                useSharedSelector: false)
            let shared = lagunaR1SelectorExperimentGateUp(
                input,
                fusedWeight: prepared.fusedWeight,
                packedScales: prepared.packedScales,
                routerKeys: routerKeys,
                useSharedSelector: true)
            eval(duplicate, shared)
            let duplicateBits = duplicate.view(dtype: .uint16).asArray(UInt16.self)
            let sharedBits = shared.view(dtype: .uint16).asArray(UInt16.self)
            try r1RequireEqual(
                sharedBits, duplicateBits,
                label: "layer \(prepared.layer) activation \(selectorCase.name)")
            activationComparisons += 1
            activationBitsCompared += sharedBits.count
        }

        caseEvidence.append(
            R1ExactnessCaseEvidence(
                name: selectorCase.name,
                expectedWinners: expectedWinners))
    }

    guard positiveCorruptionDetected else {
        throw R1SelectorExperimentError.mismatch(
            "positive corruption control did not detect a changed winner")
    }

    let artifact = R1ExactnessArtifact(
        createdAt: Date(),
        architecture: GPU.deviceInfo().architecture,
        operatingSystem: ProcessInfo.processInfo.operatingSystemVersionString,
        physicalMemoryBytes: ProcessInfo.processInfo.physicalMemory,
        sparseLayerCount: loaded.blocks.count,
        selectorCaseCount: cases.count,
        selectorComparisons: selectorComparisons,
        activationComparisons: activationComparisons,
        activationBitsCompared: activationBitsCompared,
        positiveCorruptionDetected: positiveCorruptionDetected,
        sourceEvidence: sourceEvidence,
        cases: caseEvidence)
    try r1WriteArtifact(artifact, to: artifactPath)
    print("R1_SELECTOR_EXACTNESS_ARTIFACT=\(artifactPath)")
}

@Test
func r1SelectorSharingMeasuresWarmFullSparseGateUpChain() throws {
    guard ProcessInfo.processInfo.environment["MLXFAST_R1_SELECTOR_MODE"] == "timing" else {
        return
    }

    let artifactPath = try r1RequiredEnvironment("MLXFAST_R1_SELECTOR_ARTIFACT_PATH")
    let loaded = try r1LoadPreparedModel()
    let input = r1DeterministicInput()
    let timingCase = try #require(r1SelectorCases().first { $0.name == "permuted-unique" })
    let routerKeys = MLXArray(timingCase.keys, [LagunaConstants.numExperts])
    let sourceEvidence = try r1ValidateSourceEvidence()
    let warmupSamplesPerArm = 8
    let cyclesPerOrder = 64

    for index in 0..<warmupSamplesPerArm {
        _ = r1MeasureChain(
            loaded.blocks, input: input, routerKeys: routerKeys,
            useSharedSelector: index.isMultiple(of: 2))
        _ = r1MeasureChain(
            loaded.blocks, input: input, routerKeys: routerKeys,
            useSharedSelector: !index.isMultiple(of: 2))
    }

    let orders: [(String, [Bool])] = [
        ("A-B-B-A", [false, true, true, false]),
        ("B-A-A-B", [true, false, false, true]),
    ]
    var records: [R1TimingRecord] = []
    records.reserveCapacity(orders.count * cyclesPerOrder * 4)

    for (orderName, order) in orders {
        for cycle in 0..<cyclesPerOrder {
            for (position, useSharedSelector) in order.enumerated() {
                let elapsed = r1MeasureChain(
                    loaded.blocks,
                    input: input,
                    routerKeys: routerKeys,
                    useSharedSelector: useSharedSelector)
                records.append(
                    R1TimingRecord(
                        order: orderName,
                        cycle: cycle,
                        position: position,
                        arm: useSharedSelector ? "candidate" : "control",
                        elapsedNanoseconds: elapsed))
            }
        }
    }

    let artifact = R1TimingArtifact(
        createdAt: Date(),
        architecture: GPU.deviceInfo().architecture,
        operatingSystem: ProcessInfo.processInfo.operatingSystemVersionString,
        physicalMemoryBytes: ProcessInfo.processInfo.physicalMemory,
        sparseLayerCount: loaded.blocks.count,
        warmupSamplesPerArm: warmupSamplesPerArm,
        cyclesPerOrder: cyclesPerOrder,
        orders: orders.map { $0.0 },
        sourceEvidence: sourceEvidence,
        records: records)
    try r1WriteArtifact(artifact, to: artifactPath)
    print("R1_SELECTOR_TIMING_ARTIFACT=\(artifactPath)")
}

private func r1RequiredEnvironment(_ name: String) throws -> String {
    guard let value = ProcessInfo.processInfo.environment[name], !value.isEmpty else {
        throw R1SelectorExperimentError.missingEnvironment(name)
    }
    return value
}

private func r1LoadPreparedModel() throws -> R1LoadedModel {
    let weightsPath = try r1RequiredEnvironment("MLXFAST_R1_SELECTOR_WEIGHTS_PATH")
    let config = try LagunaConfig.load(from: weightsPath)
    let loader = try LagunaWeightLoader(weightsPath: weightsPath)
    let cache = LagunaRuntimeWeightCache(loader: loader, config: config)
    let model = try cache.requireLibraryModel()
    var blocks: [R1PreparedBlock] = []

    for (layer, decoderLayer) in model.model.layers.enumerated() {
        guard let block = decoderLayer.mlp as? LagunaRuntimeSparseMoEBlock else {
            continue
        }
        guard let fusedWeight = block._fusedRoutedGateUpWeight,
            let packedScales = block._packedRoutedGateUpBank
        else {
            throw R1SelectorExperimentError.missingPreparedWeights(layer)
        }
        blocks.append(
            R1PreparedBlock(
                layer: layer,
                block: block,
                fusedWeight: fusedWeight,
                packedScales: packedScales))
    }

    guard blocks.count == 39 else {
        throw R1SelectorExperimentError.unexpectedSparseLayerCount(blocks.count)
    }
    return R1LoadedModel(cache: cache, blocks: blocks)
}

private func r1DeterministicInput() -> MLXArray {
    let values = (0..<LagunaConstants.hiddenSize).map {
        Float(Int($0 % 31) - 15) / 32.0
    }
    return MLXArray(values, [1, 1, LagunaConstants.hiddenSize]).asType(.bfloat16)
}

private func r1SelectorCases() -> [R1SelectorCase] {
    let ascending = (0..<LagunaConstants.numExperts).map(UInt32.init)
    let descending = (0..<LagunaConstants.numExperts).map {
        UInt32(LagunaConstants.numExperts - 1 - $0)
    }
    let equal = Array(repeating: UInt32(0x8000_0000), count: LagunaConstants.numExperts)
    let adjacentTies = (0..<LagunaConstants.numExperts).map {
        UInt32(($0 / 2) % 16)
    }
    let permuted = (0..<LagunaConstants.numExperts).map {
        UInt32(($0 * 73 + 19) % LagunaConstants.numExperts)
    }
    let packedBoundaries = (0..<LagunaConstants.numExperts).map { index -> UInt32 in
        switch index % 8 {
        case 0: return 0x0000_0000
        case 1: return 0x0000_0001
        case 2: return 0x7fff_ffff
        case 3: return 0x8000_0000
        case 4: return 0x8000_0001
        case 5: return 0xffff_fffe
        case 6: return 0xffff_ffff
        default: return UInt32(index / 8)
        }
    }
    var adversarial = (0..<LagunaConstants.numExperts).map {
        UInt32(0x9000_0000 + $0)
    }
    for (offset, expert) in [0, 255, 31, 32, 63, 64, 127, 128, 191, 192].enumerated() {
        adversarial[expert] = UInt32(offset / 2)
    }

    return [
        R1SelectorCase(name: "ascending-id-zero", keys: ascending),
        R1SelectorCase(name: "descending-id-255", keys: descending),
        R1SelectorCase(name: "all-equal", keys: equal),
        R1SelectorCase(name: "tie-adjacent", keys: adjacentTies),
        R1SelectorCase(name: "permuted-unique", keys: permuted),
        R1SelectorCase(name: "packed-code-boundaries", keys: packedBoundaries),
        R1SelectorCase(name: "adversarial-lane-boundaries", keys: adversarial),
    ]
}

private func r1ExpectedWinners(_ keys: [UInt32]) -> [UInt32] {
    keys.indices.sorted {
        if keys[$0] != keys[$1] {
            return keys[$0] < keys[$1]
        }
        return $0 < $1
    }.prefix(LagunaConstants.numExpertsPerTok).map(UInt32.init)
}

private func r1ValidateSourceEvidence() throws -> R1SourceEvidence {
    let evidence = R1SourceEvidence(
        candidateBarrierCount: r1Count("threadgroup_barrier", in: lagunaRoutedGateUpR1CandidateSource),
        duplicateBarrierCount: r1Count("threadgroup_barrier", in: lagunaRoutedGateUpR1DuplicateSource),
        candidateRoundCallCount: r1Count(
            "laguna_router_top8_extract_round(", in: lagunaRoutedGateUpR1CandidateSource),
        duplicateRoundCallCount: r1Count(
            "laguna_router_top8_extract_round(", in: lagunaRoutedGateUpR1DuplicateSource),
        candidateSharedWinnerCount: r1Count(
            "threadgroup uint shared_top8_winner[1]", in: lagunaRoutedGateUpR1CandidateSource),
        candidateSIMDGroupZeroGuardCount: r1Count(
            "if (simd_group == 0u)", in: lagunaRoutedGateUpR1CandidateSource),
        candidateThreadgroupSize: 64,
        candidateSIMDGroupsPerThreadgroup: 2)

    guard evidence.candidateBarrierCount == 1,
        evidence.duplicateBarrierCount == 0,
        evidence.candidateRoundCallCount == 1,
        evidence.duplicateRoundCallCount == 1,
        evidence.candidateSharedWinnerCount == 1,
        evidence.candidateSIMDGroupZeroGuardCount == 1
    else {
        throw R1SelectorExperimentError.mismatch(
            "unexpected selector source structure: \(evidence)")
    }
    return evidence
}

private func r1Count(_ needle: String, in haystack: String) -> Int {
    haystack.components(separatedBy: needle).count - 1
}

private func r1RequireEqual<T: Equatable>(
    _ actual: [T],
    _ expected: [T],
    label: String
) throws {
    guard actual == expected else {
        let mismatch = zip(actual, expected).enumerated().first {
            $0.element.0 != $0.element.1
        }?.offset
        throw R1SelectorExperimentError.mismatch(
            "\(label) mismatch at \(mismatch.map(String.init) ?? "length"); actual \(actual.count), expected \(expected.count)")
    }
}

private func r1MeasureChain(
    _ blocks: [R1PreparedBlock],
    input: MLXArray,
    routerKeys: MLXArray,
    useSharedSelector: Bool
) -> UInt64 {
    let start = DispatchTime.now().uptimeNanoseconds
    let outputs = blocks.map {
        lagunaR1SelectorExperimentGateUp(
            input,
            fusedWeight: $0.fusedWeight,
            packedScales: $0.packedScales,
            routerKeys: routerKeys,
            useSharedSelector: useSharedSelector)
    }
    eval(outputs)
    return DispatchTime.now().uptimeNanoseconds - start
}

private func r1WriteArtifact<T: Encodable>(_ artifact: T, to path: String) throws {
    let encoder = JSONEncoder()
    encoder.dateEncodingStrategy = .iso8601
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    try encoder.encode(artifact).write(
        to: URL(fileURLWithPath: path),
        options: .atomic)
}
