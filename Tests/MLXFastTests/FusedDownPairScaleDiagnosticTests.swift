import Dispatch
import Foundation
import MLX
import MLXNN
@testable import MLXFastModel
import Testing

private struct PairScaleDownOperands {
    let layer: Int
    let routedWeight: MLXArray
    let routedScales: MLXArray
    let sharedWeight: MLXArray
    let sharedScales: MLXArray
}

private func pairScalePatternedBF16(
    count: Int,
    salt: Int,
    includeExtrema: Bool = false
) -> MLXArray {
    var values = (0 ..< count).map { index in
        Float((index * 73 + salt * 29) % 257 - 128) / 128
    }
    values[0] = 0
    values[1] = -Float.zero
    if includeExtrema {
        values[2] = 65_504
        values[3] = -65_504
    }
    return MLXArray(values).asType(.bfloat16)
}

private func pairScaleIndices(_ values: [UInt32]) -> MLXArray {
    MLXArray(values, [1, 1, LagunaConstants.numExpertsPerTok])
}

private func pairScaleDown(
    _ operands: PairScaleDownOperands,
    routedActivation: MLXArray,
    sharedActivation: MLXArray,
    indices: MLXArray,
    routerWeights: MLXArray,
    residual: MLXArray,
    broadcast: Bool,
    verbose: Bool = false
) -> MLXArray {
    lagunaRoutedSharedDownResidual(
        routedActivated: routedActivation,
        routedDownWeight: operands.routedWeight,
        routedDownScales: operands.routedScales,
        indices: indices,
        routerWeights: routerWeights,
        sharedActivated: sharedActivation,
        sharedDownWeight: operands.sharedWeight,
        sharedDownScales: operands.sharedScales,
        residual: residual,
        staged: true,
        pairScaleBroadcast: broadcast,
        verbose: verbose
    )
}

private func pairScaleBits(_ array: MLXArray) -> [UInt16] {
    array.view(dtype: .uint16).asArray(UInt16.self)
}

private func pairScaleMeasureChain(
    operands: [PairScaleDownOperands],
    routedActivation: MLXArray,
    sharedActivation: MLXArray,
    indices: MLXArray,
    routerWeights: MLXArray,
    seedResidual: MLXArray,
    repeats: Int,
    broadcast: Bool
) -> Double {
    let start = DispatchTime.now().uptimeNanoseconds
    var residual = seedResidual
    for _ in 0 ..< repeats {
        for layer in operands {
            residual = pairScaleDown(
                layer,
                routedActivation: routedActivation,
                sharedActivation: sharedActivation,
                indices: indices,
                routerWeights: routerWeights,
                residual: residual,
                broadcast: broadcast
            )
        }
    }
    eval(residual)
    return Double(DispatchTime.now().uptimeNanoseconds - start) / 1_000_000_000
}

private func pairScaleMean(_ values: [Double]) -> Double {
    values.reduce(0, +) / Double(values.count)
}

@Test
func fusedDownPairScaleBroadcastDiagnostic() throws {
    let environment = ProcessInfo.processInfo.environment
    guard environment["MLXFAST_PAIR_SCALE_DIAGNOSTIC"] == "1" else { return }
    let weightsPath = try #require(
        environment["MLXFAST_LAGUNA_EQUIVALENCE_WEIGHTS_PATH"])

    let config = try LagunaConfig.load(from: weightsPath)
    let loader = try LagunaWeightLoader(weightsPath: weightsPath)
    try loader.denseStore.validateReadableByteRanges()
    try loader.validateRequiredMetadata(config: config)
    let loadedWeights = try loadRuntimeWeightArrays(denseStore: loader.denseStore)
    let runtime = LagunaRuntimeModel(config)
    try runtime.update(
        parameters: ModuleParameters.unflattened(runtime.sanitize(weights: loadedWeights)),
        verify: [.all]
    )
    eval(runtime)
    runtime.prepareFusedRuntimeWeights()

    let sparseLayers = runtime.model.layers.enumerated().compactMap { index, layer in
        (layer.mlp as? LagunaRuntimeSparseMoEBlock).map { (index, $0) }
    }
    #expect(sparseLayers.count == 39)

    let probe = pairScalePatternedBF16(
        count: LagunaConstants.hiddenSize, salt: 3
    ).reshaped([1, 1, LagunaConstants.hiddenSize])
    let operands = try sparseLayers.map { layer, block in
        let routedWeight = try #require(block._routedDownWeight)
        let routedScales = try #require(block._routedDownScales)
        let shared = try #require(block.sharedExpert.fusedSharedBanks(probe))
        #expect(shared.downScales.ndim == 1)
        return PairScaleDownOperands(
            layer: layer,
            routedWeight: routedWeight,
            routedScales: routedScales,
            sharedWeight: shared.downWeight,
            sharedScales: shared.downScales
        )
    }
    #expect(operands.count == 39)

    let routedActivation = pairScalePatternedBF16(
        count: LagunaConstants.numExpertsPerTok * LagunaConstants.moeIntermediateSize,
        salt: 11,
        includeExtrema: true
    ).reshaped([
        1, 1, LagunaConstants.numExpertsPerTok, 1,
        LagunaConstants.moeIntermediateSize,
    ])
    let sharedActivation = pairScalePatternedBF16(
        count: LagunaConstants.sharedExpertIntermediateSize,
        salt: 17,
        includeExtrema: true
    ).reshaped([1, 1, LagunaConstants.sharedExpertIntermediateSize])
    let residual = pairScalePatternedBF16(
        count: LagunaConstants.hiddenSize,
        salt: 23,
        includeExtrema: true
    ).reshaped([1, 1, LagunaConstants.hiddenSize])
    let routerWeights = MLXArray(
        [Float](repeating: 0.125, count: LagunaConstants.numExpertsPerTok),
        [1, 1, LagunaConstants.numExpertsPerTok]
    )

    var expertSets = stride(from: 0, to: LagunaConstants.numExperts, by: 8).map {
        base in (0 ..< 8).map { UInt32(base + $0) }
    }
    expertSets.append([0, 0, 255, 255, 1, 1, 2, 2])
    expertSets.append([1, 2, 3, 4, 5, 6, 7, 255])
    let indexArrays = expertSets.map(pairScaleIndices)
    eval([routedActivation, sharedActivation, residual, routerWeights] + indexArrays)

    var exactComparisons = 0
    var routedPatchReads = 0
    for operands in operands {
        var pending: [MLXArray] = []
        var pairs: [(stock: MLXArray, candidate: MLXArray, experts: [UInt32])] = []
        for (scenario, indices) in zip(expertSets, indexArrays) {
            let stock = pairScaleDown(
                operands,
                routedActivation: routedActivation,
                sharedActivation: sharedActivation,
                indices: indices,
                routerWeights: routerWeights,
                residual: residual,
                broadcast: false
            )
            let candidate = pairScaleDown(
                operands,
                routedActivation: routedActivation,
                sharedActivation: sharedActivation,
                indices: indices,
                routerWeights: routerWeights,
                residual: residual,
                broadcast: true,
                verbose: exactComparisons == 0
            )
            pending.append(contentsOf: [stock, candidate])
            pairs.append((stock, candidate, scenario))
            routedPatchReads += scenario.filter { $0 == 0 }.count
        }
        eval(pending)
        for pair in pairs {
            #expect(
                pairScaleBits(pair.stock) == pairScaleBits(pair.candidate),
                "pair-scale mismatch at sparse layer \(operands.layer), experts \(pair.experts)"
            )
            exactComparisons += 1
        }
    }

    var corruptedBytes = operands[0].routedScales.asArray(UInt8.self)
    let corruptedOffset = lagunaScalePatchHeaderBytes
    corruptedBytes[corruptedOffset] =
        corruptedBytes[corruptedOffset] == 0x38 ? 0x40 : 0x38
    let corruptedScales = MLXArray(corruptedBytes).reshaped(operands[0].routedScales.shape)
    let corruptedOperands = PairScaleDownOperands(
        layer: operands[0].layer,
        routedWeight: operands[0].routedWeight,
        routedScales: corruptedScales,
        sharedWeight: operands[0].sharedWeight,
        sharedScales: operands[0].sharedScales
    )
    let corruptionIndices = pairScaleIndices([0, 1, 2, 3, 4, 5, 6, 7])
    let uncorrupted = pairScaleDown(
        operands[0],
        routedActivation: routedActivation,
        sharedActivation: sharedActivation,
        indices: corruptionIndices,
        routerWeights: routerWeights,
        residual: residual,
        broadcast: true
    )
    let corrupted = pairScaleDown(
        corruptedOperands,
        routedActivation: routedActivation,
        sharedActivation: sharedActivation,
        indices: corruptionIndices,
        routerWeights: routerWeights,
        residual: residual,
        broadcast: true
    )
    eval(uncorrupted, corrupted)
    #expect(pairScaleBits(uncorrupted) != pairScaleBits(corrupted))

    print("PAIR_SCALE_EXACT layers=\(operands.count) scenarios=\(expertSets.count) comparisons=\(exactComparisons) output_rows=\(LagunaConstants.hiddenSize) experts_covered=\(LagunaConstants.numExperts) repeated_ids=true expert0=true expert255=true no_expert0=true signed_zero=true finite_extrema=true corruption_detected=true")
    print("PAIR_SCALE_PATCH_CENSUS exactness_routed_row0_patch_reads=\(routedPatchReads) exactness_shared_row0_patch_reads=\(operands.count * expertSets.count) production_calls=4992 routed_attempts=5111808 routed_removable_max=2555904 shared_removable_max=314496")

    let timingIndices = corruptionIndices
    let chainRepeats = Int(environment["MLXFAST_PAIR_SCALE_CHAIN_REPEATS"] ?? "16") ?? 16
    _ = pairScaleMeasureChain(
        operands: operands,
        routedActivation: routedActivation,
        sharedActivation: sharedActivation,
        indices: timingIndices,
        routerWeights: routerWeights,
        seedResidual: residual,
        repeats: 2,
        broadcast: false
    )
    _ = pairScaleMeasureChain(
        operands: operands,
        routedActivation: routedActivation,
        sharedActivation: sharedActivation,
        indices: timingIndices,
        routerWeights: routerWeights,
        seedResidual: residual,
        repeats: 2,
        broadcast: true
    )

    let patterns = [
        (name: "ABBA", order: [false, true, true, false]),
        (name: "BAAB", order: [true, false, false, true]),
    ]
    var ratiosByPattern = [String: [Double]]()
    var allRatios: [Double] = []
    var stockTimes: [Double] = []
    var candidateTimes: [Double] = []
    for cycle in 0 ..< 2 {
        for pattern in patterns {
            let times = pattern.order.map { broadcast in
                pairScaleMeasureChain(
                    operands: operands,
                    routedActivation: routedActivation,
                    sharedActivation: sharedActivation,
                    indices: timingIndices,
                    routerWeights: routerWeights,
                    seedResidual: residual,
                    repeats: chainRepeats,
                    broadcast: broadcast
                )
            }
            let ratios = pattern.name == "ABBA"
                ? [times[0] / times[1], times[3] / times[2]]
                : [times[1] / times[0], times[2] / times[3]]
            ratiosByPattern[pattern.name, default: []].append(contentsOf: ratios)
            allRatios.append(contentsOf: ratios)
            for (broadcast, time) in zip(pattern.order, times) {
                if broadcast {
                    candidateTimes.append(time)
                } else {
                    stockTimes.append(time)
                }
            }
            print("PAIR_SCALE_BLOCK cycle=\(cycle) pattern=\(pattern.name) times=\(times) ratios=\(ratios)")
        }
    }

    let mean = pairScaleMean(allRatios)
    let variance = allRatios.reduce(0) { $0 + ($1 - mean) * ($1 - mean) }
        / Double(allRatios.count - 1)
    let lower95 = mean - 2.365 * variance.squareRoot() / Double(allRatios.count).squareRoot()
    let stockPerChain = pairScaleMean(stockTimes) / Double(chainRepeats)
    let candidatePerChain = pairScaleMean(candidateTimes) / Double(chainRepeats)
    let baselineDecode = Double(environment["MLXFAST_PAIR_SCALE_BASELINE_DECODE"] ?? "0.0129265006484375")
        ?? 0.0129265006484375
    let projectedDecode = baselineDecode / (baselineDecode - (stockPerChain - candidatePerChain))
    let abbaMean = pairScaleMean(ratiosByPattern["ABBA"] ?? [])
    let baabMean = pairScaleMean(ratiosByPattern["BAAB"] ?? [])
    let noBadBlock = allRatios.allSatisfy { $0 > 1 }
    print("PAIR_SCALE_TIMING repeats=\(chainRepeats) sparse_layers=\(operands.count) abba_speedup=\(abbaMean) baab_speedup=\(baabMean) mean_speedup=\(mean) lower95=\(lower95) no_bad_block=\(noBadBlock) stock_seconds_per_chain=\(stockPerChain) candidate_seconds_per_chain=\(candidatePerChain) projected_whole_decode_speedup=\(projectedDecode)")
}
