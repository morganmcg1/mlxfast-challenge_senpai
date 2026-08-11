import Foundation
import MLX
@testable import MLXFastModel
import MLXNN
import Testing

private struct FusedDownCase {
    let label: String
    let indices: [UInt32]
    let routerWeights: [Float]
}

@Test
func fusedDownSingleSIMDGroupMatchesStagedKernelBitwiseOnRealWeights() throws {
    let environment = ProcessInfo.processInfo.environment
    guard environment["MLXFAST_RUN_FUSED_DOWN_SINGLE_SIMDGROUP_TESTS"] == "1" else {
        return
    }

    let weightsPath = environment["MLXFAST_FUSED_DOWN_TEST_WEIGHTS"] ?? "weights"
    let config = try LagunaConfig.load(from: weightsPath)
    let loader = try LagunaWeightLoader(weightsPath: weightsPath)
    let cache = LagunaRuntimeWeightCache(loader: loader, config: config)
    let runtimeModel = try cache.requireLibraryModel()
    let sparseLayers = runtimeModel.model.layers.compactMap {
        $0.mlp as? LagunaRuntimeSparseMoEBlock
    }
    #expect(sparseLayers.count == 39)

    var routedValues = deterministicFusedDownValues(count: 8 * 512, seed: 11, scale: 1 / 64)
    var sharedValues = deterministicFusedDownValues(count: 512, seed: 23, scale: 1 / 64)
    var residualValues = deterministicFusedDownValues(count: 2_048, seed: 47, scale: 1 / 32)
    routedValues[0] = 0
    routedValues[1] = -0.0
    sharedValues[0] = -0.0
    sharedValues[1] = 0
    residualValues[0] = 0
    residualValues[1] = -0.0

    let routedActivated = MLXArray(routedValues, [1, 1, 8, 1, 512]).asType(.bfloat16)
    let sharedActivated = MLXArray(sharedValues, [1, 1, 512]).asType(.bfloat16)
    let residual = MLXArray(residualValues, [1, 1, 2_048]).asType(.bfloat16)
    let cases = [
        FusedDownCase(
            label: "expert-extremes",
            indices: [0, 255, 1, 254, 2, 253, 3, 252],
            routerWeights: [
                1, -1, 0.5, -0.5, 0, -0.0,
                Float.leastNonzeroMagnitude, -Float.leastNonzeroMagnitude,
            ]
        ),
        FusedDownCase(
            label: "repeated-tied",
            indices: [0, 0, 255, 255, 0, 255, 17, 17],
            routerWeights: Array(repeating: 0.125, count: 8)
        ),
        FusedDownCase(
            label: "permuted",
            indices: [255, 0, 255, 0, 127, 128, 1, 254],
            routerWeights: [0.375, 0.25, 0.125, 0.0625, -0.375, -0.25, 0, -0.0]
        ),
    ]

    var comparisonCount = 0
    var lastCandidateBits: [UInt16] = []
    for (layerOffset, layer) in sparseLayers.enumerated() {
        let routedDownWeight = try #require(layer._routedDownWeight)
        let routedDownScales = try #require(layer._routedDownScales)
        let sharedDown = try #require(layer.sharedExpert.downProj as? QuantizedLinear)
        let sharedHalvedScales = try #require(layer.sharedExpert._sharedDownScalesHalved)
        let scalePlanes = [
            (label: "full", scales: sharedDown.scales),
            (label: "halved", scales: sharedHalvedScales),
        ]

        for scalePlane in scalePlanes {
            for testCase in cases {
                let indices = MLXArray(testCase.indices, [1, 1, 8])
                let routerWeights = MLXArray(testCase.routerWeights, [1, 1, 8])
                let control = lagunaRoutedSharedDownResidual(
                    routedActivated: routedActivated,
                    routedDownWeight: routedDownWeight,
                    routedDownScales: routedDownScales,
                    indices: indices,
                    routerWeights: routerWeights,
                    sharedActivated: sharedActivated,
                    sharedDownWeight: sharedDown.weight,
                    sharedDownScales: scalePlane.scales,
                    residual: residual,
                    staged: true,
                    singleSIMDGroup: false
                )
                let candidate = lagunaRoutedSharedDownResidual(
                    routedActivated: routedActivated,
                    routedDownWeight: routedDownWeight,
                    routedDownScales: routedDownScales,
                    indices: indices,
                    routerWeights: routerWeights,
                    sharedActivated: sharedActivated,
                    sharedDownWeight: sharedDown.weight,
                    sharedDownScales: scalePlane.scales,
                    residual: residual,
                    staged: true,
                    singleSIMDGroup: true
                )
                eval(control, candidate)

                let controlBits = control.view(dtype: .uint16).asArray(UInt16.self)
                let candidateBits = candidate.view(dtype: .uint16).asArray(UInt16.self)
                let label = "layer=\(layerOffset + 1) scales=\(scalePlane.label) case=\(testCase.label)"
                #expect(controlBits.count == 2_048, Comment(rawValue: label))
                #expect(candidateBits.count == 2_048, Comment(rawValue: label))
                #expect(candidateBits == controlBits, Comment(rawValue: label))
                comparisonCount += 1
                lastCandidateBits = candidateBits
            }
        }
    }

    #expect(comparisonCount == 39 * 2 * cases.count)
    var corrupted = lastCandidateBits
    corrupted[0] ^= 1
    #expect(corrupted != lastCandidateBits)
    print("fused_down_single_simdgroup_bitwise_comparisons=\(comparisonCount)")
}

private struct FusedDownTimingLayer {
    let routedDownWeight: MLXArray
    let routedDownScales: MLXArray
    let sharedDownWeight: MLXArray
    let sharedDownScales: MLXArray
}

private struct FusedDownTimingOrderResult {
    let savingsMicroseconds: [Double]
    let controlSeconds: [Double]
    let candidateSeconds: [Double]
}

@Test
func fusedDownSingleSIMDGroupMirroredTimingOnRealWeights() throws {
    let environment = ProcessInfo.processInfo.environment
    guard environment["MLXFAST_RUN_FUSED_DOWN_SINGLE_SIMDGROUP_TIMING"] == "1" else {
        return
    }

    let weightsPath = environment["MLXFAST_FUSED_DOWN_TEST_WEIGHTS"] ?? "weights"
    let config = try LagunaConfig.load(from: weightsPath)
    let loader = try LagunaWeightLoader(weightsPath: weightsPath)
    let cache = LagunaRuntimeWeightCache(loader: loader, config: config)
    let runtimeModel = try cache.requireLibraryModel()
    let sparseLayers = runtimeModel.model.layers.compactMap {
        $0.mlp as? LagunaRuntimeSparseMoEBlock
    }
    #expect(sparseLayers.count == 39)

    let layers = try sparseLayers.map { layer in
        let sharedDown = try #require(layer.sharedExpert.downProj as? QuantizedLinear)
        return FusedDownTimingLayer(
            routedDownWeight: try #require(layer._routedDownWeight),
            routedDownScales: try #require(layer._routedDownScales),
            sharedDownWeight: sharedDown.weight,
            sharedDownScales: try #require(layer.sharedExpert._sharedDownScalesHalved)
        )
    }
    let routedActivated = MLXArray(
        deterministicFusedDownValues(count: 8 * 512, seed: 71, scale: 1 / 64),
        [1, 1, 8, 1, 512]
    ).asType(.bfloat16)
    let sharedActivated = MLXArray(
        deterministicFusedDownValues(count: 512, seed: 89, scale: 1 / 64),
        [1, 1, 512]
    ).asType(.bfloat16)
    let residual = MLXArray(
        deterministicFusedDownValues(count: 2_048, seed: 107, scale: 1 / 32),
        [1, 1, 2_048]
    ).asType(.bfloat16)
    let indices = MLXArray([UInt32](arrayLiteral: 0, 17, 63, 127, 128, 191, 254, 255), [1, 1, 8])
    let routerWeights = MLXArray(
        [Float](arrayLiteral: 0.22, 0.18, 0.15, 0.13, 0.11, 0.09, 0.07, 0.05),
        [1, 1, 8]
    )

    let control = fusedDownChain(
        layers: layers,
        routedActivated: routedActivated,
        indices: indices,
        routerWeights: routerWeights,
        sharedActivated: sharedActivated,
        initialResidual: residual,
        singleSIMDGroup: false
    )
    let candidate = fusedDownChain(
        layers: layers,
        routedActivated: routedActivated,
        indices: indices,
        routerWeights: routerWeights,
        sharedActivated: sharedActivated,
        initialResidual: residual,
        singleSIMDGroup: true
    )
    eval(control, candidate)
    #expect(control.view(dtype: .uint16).asArray(UInt16.self) == candidate.view(dtype: .uint16).asArray(UInt16.self))

    for _ in 0..<4 {
        _ = timeFusedDownChain(
            layers: layers,
            routedActivated: routedActivated,
            indices: indices,
            routerWeights: routerWeights,
            sharedActivated: sharedActivated,
            initialResidual: residual,
            singleSIMDGroup: false
        )
        _ = timeFusedDownChain(
            layers: layers,
            routedActivated: routedActivated,
            indices: indices,
            routerWeights: routerWeights,
            sharedActivated: sharedActivated,
            initialResidual: residual,
            singleSIMDGroup: true
        )
    }

    print("fused_down_single_simdgroup_timing,order,cycle,position,arm,seconds")
    let abba = measureFusedDownOrder(
        label: "ABBA",
        order: [false, true, true, false],
        cycles: 64,
        layers: layers,
        routedActivated: routedActivated,
        indices: indices,
        routerWeights: routerWeights,
        sharedActivated: sharedActivated,
        initialResidual: residual
    )
    let baab = measureFusedDownOrder(
        label: "BAAB",
        order: [true, false, false, true],
        cycles: 64,
        layers: layers,
        routedActivated: routedActivated,
        indices: indices,
        routerWeights: routerWeights,
        sharedActivated: sharedActivated,
        initialResidual: residual
    )

    let abbaMedian = median(abba.savingsMicroseconds)
    let baabMedian = median(baab.savingsMicroseconds)
    let abbaLowerBound = bootstrapMedianLowerBound(
        abba.savingsMicroseconds,
        sampleCount: 20_000,
        seed: 0x4142_4241
    )
    let baabLowerBound = bootstrapMedianLowerBound(
        baab.savingsMicroseconds,
        sampleCount: 20_000,
        seed: 0x4241_4142
    )
    let abbaRegression = median(abba.candidateSeconds) / median(abba.controlSeconds) - 1
    let baabRegression = median(baab.candidateSeconds) / median(baab.controlSeconds) - 1

    print(String(
        format: "fused_down_single_simdgroup_summary order=ABBA cycles=64 median_saving_us=%.6f bootstrap_95_lcb_us=%.6f median_regression=%.9f",
        abbaMedian,
        abbaLowerBound,
        abbaRegression
    ))
    print(String(
        format: "fused_down_single_simdgroup_summary order=BAAB cycles=64 median_saving_us=%.6f bootstrap_95_lcb_us=%.6f median_regression=%.9f",
        baabMedian,
        baabLowerBound,
        baabRegression
    ))

    #expect(abbaMedian >= 30)
    #expect(baabMedian >= 30)
    #expect(abbaLowerBound > 24.543)
    #expect(baabLowerBound > 24.543)
    #expect(abbaRegression < 0.005)
    #expect(baabRegression < 0.005)
}

private func fusedDownChain(
    layers: [FusedDownTimingLayer],
    routedActivated: MLXArray,
    indices: MLXArray,
    routerWeights: MLXArray,
    sharedActivated: MLXArray,
    initialResidual: MLXArray,
    singleSIMDGroup: Bool
) -> MLXArray {
    var output = initialResidual
    for layer in layers {
        output = lagunaRoutedSharedDownResidual(
            routedActivated: routedActivated,
            routedDownWeight: layer.routedDownWeight,
            routedDownScales: layer.routedDownScales,
            indices: indices,
            routerWeights: routerWeights,
            sharedActivated: sharedActivated,
            sharedDownWeight: layer.sharedDownWeight,
            sharedDownScales: layer.sharedDownScales,
            residual: output,
            staged: true,
            singleSIMDGroup: singleSIMDGroup
        )
    }
    return output
}

private func timeFusedDownChain(
    layers: [FusedDownTimingLayer],
    routedActivated: MLXArray,
    indices: MLXArray,
    routerWeights: MLXArray,
    sharedActivated: MLXArray,
    initialResidual: MLXArray,
    singleSIMDGroup: Bool
) -> Double {
    autoreleasepool {
        let output = fusedDownChain(
            layers: layers,
            routedActivated: routedActivated,
            indices: indices,
            routerWeights: routerWeights,
            sharedActivated: sharedActivated,
            initialResidual: initialResidual,
            singleSIMDGroup: singleSIMDGroup
        )
        let start = DispatchTime.now().uptimeNanoseconds
        eval(output)
        let end = DispatchTime.now().uptimeNanoseconds
        return Double(end - start) / 1_000_000_000
    }
}

private func measureFusedDownOrder(
    label: String,
    order: [Bool],
    cycles: Int,
    layers: [FusedDownTimingLayer],
    routedActivated: MLXArray,
    indices: MLXArray,
    routerWeights: MLXArray,
    sharedActivated: MLXArray,
    initialResidual: MLXArray
) -> FusedDownTimingOrderResult {
    var savingsMicroseconds: [Double] = []
    var controlSeconds: [Double] = []
    var candidateSeconds: [Double] = []
    savingsMicroseconds.reserveCapacity(cycles)
    controlSeconds.reserveCapacity(cycles * 2)
    candidateSeconds.reserveCapacity(cycles * 2)

    for cycle in 0..<cycles {
        var cycleControl: [Double] = []
        var cycleCandidate: [Double] = []
        for (position, singleSIMDGroup) in order.enumerated() {
            let seconds = timeFusedDownChain(
                layers: layers,
                routedActivated: routedActivated,
                indices: indices,
                routerWeights: routerWeights,
                sharedActivated: sharedActivated,
                initialResidual: initialResidual,
                singleSIMDGroup: singleSIMDGroup
            )
            let arm = singleSIMDGroup ? "candidate" : "control"
            print(String(
                format: "fused_down_single_simdgroup_timing,%@,%d,%d,%@,%.9f",
                label,
                cycle,
                position,
                arm,
                seconds
            ))
            if singleSIMDGroup {
                cycleCandidate.append(seconds)
                candidateSeconds.append(seconds)
            } else {
                cycleControl.append(seconds)
                controlSeconds.append(seconds)
            }
        }
        let controlMean = cycleControl.reduce(0, +) / Double(cycleControl.count)
        let candidateMean = cycleCandidate.reduce(0, +) / Double(cycleCandidate.count)
        savingsMicroseconds.append((controlMean - candidateMean) * 1_000_000)
    }

    return FusedDownTimingOrderResult(
        savingsMicroseconds: savingsMicroseconds,
        controlSeconds: controlSeconds,
        candidateSeconds: candidateSeconds
    )
}

private func median(_ values: [Double]) -> Double {
    let sorted = values.sorted()
    let midpoint = sorted.count / 2
    if sorted.count.isMultiple(of: 2) {
        return (sorted[midpoint - 1] + sorted[midpoint]) / 2
    }
    return sorted[midpoint]
}

private struct FusedDownTimingGenerator {
    var state: UInt64

    mutating func next(upperBound: Int) -> Int {
        state = state &* 6_364_136_223_846_793_005 &+ 1_442_695_040_888_963_407
        return Int((state >> 32) % UInt64(upperBound))
    }
}

private func bootstrapMedianLowerBound(
    _ values: [Double],
    sampleCount: Int,
    seed: UInt64
) -> Double {
    var generator = FusedDownTimingGenerator(state: seed)
    var bootstrapMedians: [Double] = []
    bootstrapMedians.reserveCapacity(sampleCount)
    for _ in 0..<sampleCount {
        var sample: [Double] = []
        sample.reserveCapacity(values.count)
        for _ in values {
            sample.append(values[generator.next(upperBound: values.count)])
        }
        bootstrapMedians.append(median(sample))
    }
    bootstrapMedians.sort()
    return bootstrapMedians[Int(Double(sampleCount) * 0.025)]
}


private func deterministicFusedDownValues(
    count: Int,
    seed: Int,
    scale: Float
) -> [Float] {
    (0..<count).map { index in
        let centered = (index &* 37 &+ seed &* 101) % 257 - 128
        return Float(centered) * scale
    }
}
