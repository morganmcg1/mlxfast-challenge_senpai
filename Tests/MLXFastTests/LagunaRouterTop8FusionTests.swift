import Foundation
import MLX
@testable import MLXFastModel
import Testing

@Test
func fusedResidualRMSNormRouterTop8MatchesSeparateExactPath() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
        return
    }

    let hidden = 2_048
    let experts = 256
    let residual = MLXArray(
        (0..<hidden).map { Float(($0 * 17) % 97 - 48) / 64 },
        [1, 1, hidden]
    ).asType(.bfloat16)
    let branch = MLXArray(
        (0..<hidden).map { Float(($0 * 29) % 89 - 44) / 128 },
        [1, 1, hidden]
    ).asType(.bfloat16)
    let weight = MLXArray(
        (0..<hidden).map { 0.75 + Float($0 % 31) / 128 },
        [hidden]
    ).asType(.bfloat16)
    let routerWeight = MLXArray(
        (0..<(experts * hidden)).map {
            let row = $0 / hidden
            let column = $0 % hidden
            return Float((row * 13 + column * 7) % 67 - 33) / 256
        },
        [experts, hidden]
    ).asType(.bfloat16)
    let correctionBias = MLXArray(
        (0..<experts).map { Float(($0 * 19) % 37 - 18) / 1_024 },
        [experts]
    )

    let separate = lagunaResidualRMSNormRouter(
        residual: residual,
        branch: branch,
        weight: weight,
        routerWeight: routerWeight
    )
    let expectedTop8 = lagunaDecodeRouterTop8OrdinalScoreTableForTesting(
        logits: separate.routerLogits,
        correctionBias: correctionBias,
        normalizing: true
    )
    let fused = lagunaResidualRMSNormRouterTop8(
        residual: residual,
        branch: branch,
        weight: weight,
        routerWeight: routerWeight,
        correctionBias: correctionBias
    )
    eval(
        separate.summed,
        separate.normalized,
        expectedTop8.0,
        expectedTop8.1,
        fused.summed,
        fused.normalized,
        fused.routerIndices,
        fused.routerScores
    )

    #expect(fused.summed.asArray(Float.self) == separate.summed.asArray(Float.self))
    #expect(fused.normalized.asArray(Float.self) == separate.normalized.asArray(Float.self))
    #expect(fused.routerIndices.asArray(UInt32.self) == expectedTop8.0.asArray(UInt32.self))
    #expect(fused.routerScores.asArray(Float.self) == expectedTop8.1.asArray(Float.self))
}
