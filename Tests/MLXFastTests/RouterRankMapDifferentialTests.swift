import Foundation
import MLX
import MLXLMCommon
import Testing
@testable import MLXFastModel

private enum RouterRankMapScenario {
    case random
    case balanced
    case sameEightTie
}

@Test
func routerRankMapDifferentialMatchesStableGatherSortWhenEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_ROUTER_RANK_MAP_TESTS"] == "1" else {
        return
    }

    for rows in [2, 3, 7, 8, 16, 63, 64, 127, 128, 511, 512, 513] {
        verifyRouterRankMap(rows: rows, scenario: .random, normalizing: false)
        verifyRouterRankMap(rows: rows, scenario: .random, normalizing: true)
    }
    for rows in [2, 64, 512, 513] {
        for scenario in [RouterRankMapScenario.balanced, .sameEightTie] {
            verifyRouterRankMap(rows: rows, scenario: scenario, normalizing: false)
            verifyRouterRankMap(rows: rows, scenario: scenario, normalizing: true)
        }
    }
}

private func verifyRouterRankMap(
    rows: Int,
    scenario: RouterRankMapScenario,
    normalizing: Bool
) {
    let inputs = makeRouterInputs(rows: rows, scenario: scenario)
    let logits = MLXArray(inputs.logits, [1, rows, 256])
    let correctionBias = MLXArray(inputs.bias)
    let control = lagunaPrefillRouterTournamentOrdinalForTesting(
        logits: logits,
        correctionBias: correctionBias,
        rows: rows,
        normalizing: normalizing
    )
    let candidate = lagunaPrefillRouterTournamentOrdinalRankMapForTesting(
        logits: logits,
        correctionBias: correctionBias,
        rows: rows,
        normalizing: normalizing
    )
    eval([control.0, control.1, candidate.0, candidate.1, candidate.2])

    let controlIndices = control.0.asArray(UInt32.self)
    let candidateIndices = candidate.0.asArray(UInt32.self)
    #expect(candidateIndices == controlIndices)
    #expect(candidate.1.asArray(Float.self) == control.1.asArray(Float.self))
    #expect(candidate.2.shape == [rows, 256])
    #expect(candidate.2.dtype == .uint8)

    var expectedMap = [UInt8](repeating: 255, count: rows * 256)
    for row in 0 ..< rows {
        let winners = Array(candidateIndices[(row * 8) ..< (row * 8 + 8)])
        #expect(Set(winners).count == 8)
        for (slot, expert) in winners.enumerated() {
            expectedMap[row * 256 + Int(expert)] = UInt8(slot)
        }
    }
    let rankMap = candidate.2.asArray(UInt8.self)
    #expect(rankMap == expectedMap)

    let activationWidth = 4
    let activationValues = (0 ..< rows).flatMap { row in
        (0 ..< activationWidth).map { channel in
            Float(row * 16 + channel) + 0.25
        }
    }
    let activations = MLXArray(
        activationValues,
        [1, rows, 1, 1, activationWidth]
    )
    let generic = gatherSort(x: activations, indices: candidate.0)
    let specialized = lagunaRouterRankMapGatherSortForTesting(
        activations,
        rankMap: candidate.2
    )
    let enumeration = lagunaRouterRankMapEnumerationForTesting(candidate.2)
    eval([
        generic.0, generic.1, generic.2,
        specialized.0, specialized.1, specialized.2,
        enumeration.0, enumeration.1, enumeration.2,
    ])

    #expect(specialized.0.asArray(Float.self) == generic.0.asArray(Float.self))
    #expect(specialized.1.asArray(UInt32.self) == generic.1.asArray(UInt32.self))
    #expect(specialized.2.asArray(UInt32.self) == generic.2.asArray(UInt32.self))

    let expected = expectedEnumeration(rankMap: rankMap, rows: rows)
    #expect(enumeration.0.asArray(UInt32.self) == expected.rows)
    #expect(enumeration.1.asArray(UInt32.self) == expected.experts)
    #expect(enumeration.2.asArray(UInt32.self) == expected.inverse)

    let genericOutput = syntheticRoutedOutput(
        sortedActivations: generic.0.asArray(Float.self),
        sortedExperts: generic.1.asArray(UInt32.self),
        inverseOrder: generic.2.asArray(UInt32.self),
        width: activationWidth
    )
    let specializedOutput = syntheticRoutedOutput(
        sortedActivations: specialized.0.asArray(Float.self),
        sortedExperts: specialized.1.asArray(UInt32.self),
        inverseOrder: specialized.2.asArray(UInt32.self),
        width: activationWidth
    )
    #expect(specializedOutput == genericOutput)
}

private func makeRouterInputs(
    rows: Int,
    scenario: RouterRankMapScenario
) -> (logits: [Float], bias: [Float]) {
    var logits = [Float](repeating: -12, count: rows * 256)
    var bias = [Float](repeating: 0, count: 256)

    switch scenario {
    case .random:
        for expert in 0 ..< 256 {
            bias[expert] = Float((expert * 17) % 23 - 11) / 512
        }
        for row in 0 ..< rows {
            for expert in 0 ..< 256 {
                var state = UInt32(truncatingIfNeeded: row * 65_537 + expert * 257 + 19)
                state = state &* 1_664_525 &+ 1_013_904_223
                logits[row * 256 + expert] = Float(state % 16_381) / 2_048 - 4
            }
        }
    case .balanced:
        for row in 0 ..< rows {
            for slot in 0 ..< 8 {
                let expert = (row * 8 + slot) % 256
                logits[row * 256 + expert] = 6 - Float(slot) / 8
            }
        }
    case .sameEightTie:
        let experts = [0, 1, 2, 3, 252, 253, 254, 255]
        for row in 0 ..< rows {
            for expert in experts {
                logits[row * 256 + expert] = 5
            }
        }
    }
    return (logits, bias)
}

private func expectedEnumeration(
    rankMap: [UInt8],
    rows: Int
) -> (rows: [UInt32], experts: [UInt32], inverse: [UInt32]) {
    var rowOrder: [UInt32] = []
    var sortedExperts: [UInt32] = []
    var inverseOrder = [UInt32](repeating: .max, count: rows * 8)
    rowOrder.reserveCapacity(rows * 8)
    sortedExperts.reserveCapacity(rows * 8)

    for expert in 0 ..< 256 {
        for row in 0 ..< rows {
            let slot = rankMap[row * 256 + expert]
            if slot < 8 {
                let position = UInt32(rowOrder.count)
                rowOrder.append(UInt32(row))
                sortedExperts.append(UInt32(expert))
                inverseOrder[row * 8 + Int(slot)] = position
            }
        }
    }
    return (rowOrder, sortedExperts, inverseOrder)
}

private func syntheticRoutedOutput(
    sortedActivations: [Float],
    sortedExperts: [UInt32],
    inverseOrder: [UInt32],
    width: Int
) -> [Float] {
    var output = [Float](repeating: 0, count: inverseOrder.count * width)
    for original in inverseOrder.indices {
        let sorted = Int(inverseOrder[original])
        let expertScale = Float(sortedExperts[sorted] + 1)
        for channel in 0 ..< width {
            output[original * width + channel] =
                sortedActivations[sorted * width + channel] * expertScale
        }
    }
    return output
}
