import Foundation
import MLX
@testable import MLXFastModel
import Testing

@Test
func routedSharedDownWorkerExperimentMatchesSavedReference() throws {
    let environment = ProcessInfo.processInfo.environment
    guard environment["MLXFAST_RUN_ROUTED_DOWN_WORKER_EXPERIMENT"] == "1" else {
        return
    }

    var coveredSlots: [Int] = []
    for worker in 0..<5 {
        if worker == 4 {
            coveredSlots.append(8)
        } else {
            coveredSlots.append(worker * 2)
            coveredSlots.append(worker * 2 + 1)
        }
    }
    #expect(coveredSlots == Array(0...8))
    #expect(Set(coveredSlots).count == 9)

    let routedValues = (0..<(8 * LagunaConstants.moeIntermediateSize)).map { index -> Float in
        let slot = index / LagunaConstants.moeIntermediateSize
        return Float(((index * 13 + slot * 7) % 29) - 14) / 16
    }
    let routedActivated = MLXArray(
        routedValues,
        [1, 1, 8, 1, LagunaConstants.moeIntermediateSize]
    ).asType(.bfloat16)

    let expertPackedCodes = (0..<LagunaConstants.numExperts).map { expert -> UInt32 in
        UInt32((expert % 7) + 1) &* UInt32(0x1111_1111)
    }
    let routedDownWeight = contiguous(broadcast(
        MLXArray(expertPackedCodes, [LagunaConstants.numExperts, 1, 1]),
        to: [
            LagunaConstants.numExperts,
            LagunaConstants.hiddenSize,
            LagunaConstants.moeIntermediateSize / 8,
        ]
    ))
    let routedDownScales = MLXArray.full(
        [
            LagunaConstants.numExperts,
            LagunaConstants.hiddenSize,
            LagunaConstants.moeIntermediateSize / 16,
        ],
        values: MLXArray(UInt8(0x38)),
        dtype: .uint8
    )
    let indices = MLXArray(
        [UInt32(0), 0, 7, 7, 255, 255, 3, 3],
        [1, 1, LagunaConstants.numExpertsPerTok]
    )
    let routerWeights = MLXArray(
        [Float(0.125), -0.25, 0.375, -0.5, 0.625, -0.75, 1, -1.25],
        [1, 1, LagunaConstants.numExpertsPerTok]
    )

    let sharedValues = (0..<LagunaConstants.sharedExpertIntermediateSize).map { index -> Float in
        Float(((index * 11) % 23) - 11) / 16
    }
    let sharedActivated = MLXArray(
        sharedValues,
        [1, 1, LagunaConstants.sharedExpertIntermediateSize]
    ).asType(.bfloat16)
    let sharedDownWeight = MLXArray.full(
        [
            LagunaConstants.hiddenSize,
            LagunaConstants.sharedExpertIntermediateSize / 8,
        ],
        values: MLXArray(UInt32(0x5432_1765)),
        dtype: .uint32
    )
    let sharedDownScales = MLXArray.full(
        [
            LagunaConstants.hiddenSize,
            LagunaConstants.sharedExpertIntermediateSize / 16,
        ],
        values: MLXArray(UInt8(0x38)),
        dtype: .uint8
    )
    let residualValues = (0..<LagunaConstants.hiddenSize).map { index -> Float in
        Float((index % 31) - 15) / 32
    }
    let residual = MLXArray(
        residualValues,
        [1, 1, LagunaConstants.hiddenSize]
    ).asType(.bfloat16)

    let output = lagunaRoutedSharedDownResidual(
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
    eval(output)

    let words = output.view(dtype: .uint16).asArray(UInt16.self)
    let outputData = words.withUnsafeBytes { Data($0) }
    let referencePath = try #require(environment["MLXFAST_ROUTED_DOWN_REFERENCE_PATH"])
    switch environment["MLXFAST_ROUTED_DOWN_REFERENCE_MODE"] {
    case "write":
        try outputData.write(to: URL(fileURLWithPath: referencePath))
        print("MLXFAST_ROUTED_DOWN_REFERENCE wrote_bytes=\(outputData.count)")
    case "check":
        let referenceData = try Data(contentsOf: URL(fileURLWithPath: referencePath))
        #expect(outputData == referenceData)
        print("MLXFAST_ROUTED_DOWN_REFERENCE exact_match bytes=\(outputData.count)")
    default:
        Issue.record("MLXFAST_ROUTED_DOWN_REFERENCE_MODE must be write or check")
    }
}
