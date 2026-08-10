import Foundation
import MLX
@testable import MLXFastModel
import Testing

private struct FusedDownR8Inputs {
    let routedActivated: MLXArray
    let routedDownWeight: MLXArray
    let routedDownScales: MLXArray
    let indices: MLXArray
    let routerWeights: MLXArray
    let sharedActivated: MLXArray
    let sharedDownWeight: MLXArray
    let sharedDownScales: MLXArray
    let residual: MLXArray
}

private func fullScalePlane(_ shape: [Int], patched: Bool) -> MLXArray {
    var bytes = [UInt8](repeating: 0x38, count: shape.reduce(1, *))
    let rowCount = LagunaConstants.hiddenSize
    let scalesPerRow = shape.last!
    for row in 0..<rowCount {
        let scale = UInt8(0x30 + row % 24)
        for column in 0..<scalesPerRow {
            bytes[row * scalesPerRow + column] = scale
        }
    }
    if patched {
        bytes[1] = 0x40
    }
    return MLXArray(bytes, shape)
}

private func fusedDownR8Inputs(
    routedDownScales: MLXArray,
    sharedDownScales: MLXArray
) -> FusedDownR8Inputs {
    let routedActivated = MLXArray.full(
        [
            1, 1, LagunaConstants.numExpertsPerTok, 1,
            LagunaConstants.moeIntermediateSize,
        ],
        values: MLXArray(Float(1)),
        dtype: .bfloat16
    )
    let routedDownWeight = MLXArray.full(
        [
            LagunaConstants.numExperts,
            LagunaConstants.hiddenSize,
            LagunaConstants.moeIntermediateSize / 8,
        ],
        values: MLXArray(UInt32(0x7654_3210)),
        dtype: .uint32
    )
    let indices = MLXArray(
        [UInt32](repeating: 0, count: LagunaConstants.numExpertsPerTok),
        [1, 1, LagunaConstants.numExpertsPerTok]
    )
    let routerWeights = MLXArray(
        [Float(1)] + [Float](repeating: 0, count: LagunaConstants.numExpertsPerTok - 1),
        [1, 1, LagunaConstants.numExpertsPerTok]
    )
    let sharedActivated = MLXArray.full(
        [1, 1, LagunaConstants.sharedExpertIntermediateSize],
        values: MLXArray(Float(1)),
        dtype: .bfloat16
    )
    let sharedDownWeight = MLXArray.full(
        [
            LagunaConstants.hiddenSize,
            LagunaConstants.sharedExpertIntermediateSize / 8,
        ],
        values: MLXArray(UInt32(0x7654_3210)),
        dtype: .uint32
    )
    let residual = MLXArray(
        (0..<LagunaConstants.hiddenSize).map { Float(($0 % 47) - 23) / 64 },
        [1, 1, LagunaConstants.hiddenSize]
    ).asType(.bfloat16)

    eval(
        routedActivated, routedDownWeight, routedDownScales, indices, routerWeights,
        sharedActivated, sharedDownWeight, sharedDownScales, residual
    )
    return FusedDownR8Inputs(
        routedActivated: routedActivated,
        routedDownWeight: routedDownWeight,
        routedDownScales: routedDownScales,
        indices: indices,
        routerWeights: routerWeights,
        sharedActivated: sharedActivated,
        sharedDownWeight: sharedDownWeight,
        sharedDownScales: sharedDownScales,
        residual: residual
    )
}

private func launchFusedDownR8(_ inputs: FusedDownR8Inputs, staged: Bool) -> MLXArray {
    lagunaRoutedSharedDownResidual(
        routedActivated: inputs.routedActivated,
        routedDownWeight: inputs.routedDownWeight,
        routedDownScales: inputs.routedDownScales,
        indices: inputs.indices,
        routerWeights: inputs.routerWeights,
        sharedActivated: inputs.sharedActivated,
        sharedDownWeight: inputs.sharedDownWeight,
        sharedDownScales: inputs.sharedDownScales,
        residual: inputs.residual,
        staged: staged
    )
}

private func fusedDownWords(_ output: MLXArray) -> [UInt16] {
    output.view(dtype: .uint16).asArray(UInt16.self)
}

private func fusedDownChecksum(_ words: [UInt16]) -> UInt64 {
    words.reduce(UInt64(0xcbf2_9ce4_8422_2325)) { hash, word in
        (hash ^ UInt64(word)) &* 0x0000_0100_0000_01b3
    }
}

@Suite(.serialized)
struct FusedDownR8Stage4x2OracleTests {
    @Test
    func realKernelsMatchBothLayoutsAndConsumePatchHeaders() throws {
        guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1"
        else { return }

        let routedShape = [
            LagunaConstants.numExperts,
            LagunaConstants.hiddenSize,
            LagunaConstants.moeIntermediateSize / 16,
        ]
        let sharedShape = [
            LagunaConstants.hiddenSize,
            LagunaConstants.sharedExpertIntermediateSize / 16,
        ]
        let routedFull = fullScalePlane(routedShape, patched: true)
        let routedFullNoPatch = fullScalePlane(routedShape, patched: false)
        let sharedFull = fullScalePlane(sharedShape, patched: true)
        let sharedFullNoPatch = fullScalePlane(sharedShape, patched: false)
        let routedHalved = try #require(
            lagunaHalvedGroup32ScalePlane(routedFull, allowedFlatPairs: [0]))
        let routedHalvedNoPatch = try #require(
            lagunaHalvedGroup32ScalePlane(routedFullNoPatch, allowedFlatPairs: [0]))
        let sharedHalved = try #require(
            lagunaHalvedGroup32ScalePlane(sharedFull, allowedFlatPairs: [0]))
        let sharedHalvedNoPatch = try #require(
            lagunaHalvedGroup32ScalePlane(sharedFullNoPatch, allowedFlatPairs: [0]))

        #expect(routedHalved[0].item(UInt8.self) == 0x40)
        #expect(routedHalved[128].item(UInt8.self) == 0x30)
        #expect(sharedHalved[0].item(UInt8.self) == 0x40)
        #expect(sharedHalved[128].item(UInt8.self) == 0x30)

        let fullInputs = fusedDownR8Inputs(
            routedDownScales: routedHalved, sharedDownScales: sharedFull)
        let halvedInputs = fusedDownR8Inputs(
            routedDownScales: routedHalved, sharedDownScales: sharedHalved)
        let noRoutedPatchInputs = fusedDownR8Inputs(
            routedDownScales: routedHalvedNoPatch, sharedDownScales: sharedHalved)
        let noSharedPatchInputs = fusedDownR8Inputs(
            routedDownScales: routedHalved, sharedDownScales: sharedHalvedNoPatch)

        let r4Full = launchFusedDownR8(fullInputs, staged: false)
        let r8Full = launchFusedDownR8(fullInputs, staged: true)
        let r4Halved = launchFusedDownR8(halvedInputs, staged: false)
        let r8Halved = launchFusedDownR8(halvedInputs, staged: true)
        let noRoutedPatch = launchFusedDownR8(noRoutedPatchInputs, staged: false)
        let noSharedPatch = launchFusedDownR8(noSharedPatchInputs, staged: false)
        eval(r4Full, r8Full, r4Halved, r8Halved, noRoutedPatch, noSharedPatch)

        let r4FullWords = fusedDownWords(r4Full)
        let r8FullWords = fusedDownWords(r8Full)
        let r4HalvedWords = fusedDownWords(r4Halved)
        let r8HalvedWords = fusedDownWords(r8Halved)
        let noRoutedPatchWords = fusedDownWords(noRoutedPatch)
        let noSharedPatchWords = fusedDownWords(noSharedPatch)

        #expect(r4FullWords == r8FullWords)
        #expect(r4HalvedWords == r8HalvedWords)
        #expect(r4FullWords == r4HalvedWords)
        #expect(r4FullWords.count == LagunaConstants.hiddenSize)
        #expect(r4HalvedWords[0] != noRoutedPatchWords[0])
        #expect(Array(r4HalvedWords.dropFirst()) == Array(noRoutedPatchWords.dropFirst()))
        #expect(r4HalvedWords[0] != noSharedPatchWords[0])
        #expect(Array(r4HalvedWords.dropFirst()) == Array(noSharedPatchWords.dropFirst()))

        print(
            "FUSED_DOWN_R8_ORACLE control_r4_groups=512 candidate_r8_groups=256 "
                + "threads=288 scratch_bytes=144 layouts=full,halved "
                + "routed_patch=consumed shared_patch=consumed "
                + "words=\(r4FullWords.count) "
                + "checksum=\(String(fusedDownChecksum(r4FullWords), radix: 16))"
        )
    }
}
