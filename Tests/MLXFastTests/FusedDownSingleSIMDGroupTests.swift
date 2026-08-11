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
