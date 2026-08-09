import MLX
@testable import MLXFastModel
import Testing

private typealias RouterKernel = (MLXArray, MLXArray, Bool) -> (MLXArray, MLXArray)

private func verifySingleBF16RouterNormalization(
    logits: MLXArray,
    correctionBias: MLXArray,
    kernel: RouterKernel
) {
    let (referenceIndices, referenceScores) = kernel(logits, correctionBias, false)
    let expectedWeights = (
        referenceScores / referenceScores.sum(axis: -1, keepDims: true)
    ).asType(.bfloat16)
    let (actualIndices, actualWeights) = kernel(logits, correctionBias, true)
    eval(referenceIndices, expectedWeights, actualIndices, actualWeights)

    #expect(actualWeights.dtype == .bfloat16)
    #expect(actualIndices.asArray(UInt32.self) == referenceIndices.asArray(UInt32.self))
    #expect(
        actualWeights.view(dtype: .uint16).asArray(UInt16.self)
            == expectedWeights.view(dtype: .uint16).asArray(UInt16.self)
    )
}

@Test
func lagunaDecodeRoutersNormalizeInFP32ThenRoundOnceToBF16() {
    let representativeLogits = MLXArray(
        (0..<256).map { index in
            Float((index * 73) % 257 - 128) / 12
        },
        [1, 1, 256]
    ).asType(.bfloat16)
    let representativeBias = MLXArray(
        (0..<256).map { index in
            Float((index * 29) % 31 - 15) / 128
        },
        [256]
    )
    let edgePattern: [Float] = [-80, -20, -1, -0.0, 0.0, 1, 20, 80]
    let edgeLogits = MLXArray(
        (0..<256).map { edgePattern[$0 % edgePattern.count] },
        [1, 1, 256]
    ).asType(.bfloat16)
    let zeroBias = MLXArray(Array(repeating: Float.zero, count: 256), [256])

    let kernels: [RouterKernel] = [
        { lagunaDecodeRouterTop8AcceptedForTesting(
            logits: $0, correctionBias: $1, normalizing: $2) },
        { lagunaDecodeRouterTop8OrdinalForTesting(
            logits: $0, correctionBias: $1, normalizing: $2) },
        { lagunaDecodeRouterTop8OrdinalScoreTableForTesting(
            logits: $0, correctionBias: $1, normalizing: $2) },
    ]
    for kernel in kernels {
        verifySingleBF16RouterNormalization(
            logits: representativeLogits,
            correctionBias: representativeBias,
            kernel: kernel
        )
        verifySingleBF16RouterNormalization(
            logits: edgeLogits,
            correctionBias: zeroBias,
            kernel: kernel
        )
    }
}

@Test
func lagunaPrefillRoutersNormalize512RowsInFP32ThenRoundOnceToBF16() {
    let rows = 512
    let edgePattern: [Float] = [-80, -20, -1, -0.0, 0.0, 1, 20, 80]
    let logits = MLXArray(
        (0..<(rows * 256)).map { index in
            let row = index / 256
            let column = index % 256
            if row == 0 {
                return edgePattern[column % edgePattern.count]
            }
            return Float((row * 17 + column * 73) % 511 - 255) / 24
        },
        [1, rows, 256]
    ).asType(.bfloat16)
    let correctionBias = MLXArray(
        (0..<256).map { index in
            Float((index * 19) % 37 - 18) / 128
        },
        [256]
    )

    let kernels: [RouterKernel] = [
        { lagunaPrefillRouterTournamentAcceptedForTesting(
            logits: $0, correctionBias: $1, rows: rows, normalizing: $2) },
        { lagunaPrefillRouterTournamentOrdinalForTesting(
            logits: $0, correctionBias: $1, rows: rows, normalizing: $2) },
    ]
    for kernel in kernels {
        verifySingleBF16RouterNormalization(
            logits: logits,
            correctionBias: correctionBias,
            kernel: kernel
        )
    }
}
