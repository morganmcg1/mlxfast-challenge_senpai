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

    for useBFloat16 in [false, true] {
        for rows in [2, 3, 7, 8, 16, 63, 64, 127, 128, 511, 512, 513] {
            verifyRouterRankMap(
                rows: rows, scenario: .random, normalizing: false,
                useBFloat16: useBFloat16)
            verifyRouterRankMap(
                rows: rows, scenario: .random, normalizing: true,
                useBFloat16: useBFloat16)
        }
        for rows in [2, 64, 512, 513] {
            for scenario in [RouterRankMapScenario.balanced, .sameEightTie] {
                verifyRouterRankMap(
                    rows: rows, scenario: scenario, normalizing: false,
                    useBFloat16: useBFloat16)
                verifyRouterRankMap(
                    rows: rows, scenario: scenario, normalizing: true,
                    useBFloat16: useBFloat16)
            }
        }
    }
}

@Test
func routerRankMapIsolatedBenchmark() throws {
    let environment = ProcessInfo.processInfo.environment
    guard environment["MLXFAST_RUN_ROUTER_RANK_MAP_BENCHMARK"] == "1" else {
        return
    }

    let order = environment["MLXFAST_ROUTER_RANK_MAP_ORDER"] ?? "AB"
    precondition(order == "AB" || order == "BA")
    let rows = 512
    let width = 2_048
    let warmupPairs = 8
    let timedPairs = 40
    let inputs = makeRouterInputs(rows: rows, scenario: .random)
    let logits = MLXArray(inputs.logits, [1, rows, 256]).asType(.bfloat16)
    let correctionBias = MLXArray(inputs.bias)
    let activationValues = (0 ..< rows * width).map {
        Float(($0 &* 37) % 4_096) / 1_024 - 2
    }
    let activations = MLXArray(
        activationValues, [1, rows, 1, 1, width]
    ).asType(.bfloat16)
    eval([logits, correctionBias, activations])

    func evaluateControl() {
        let router = lagunaPrefillRouterTournamentOrdinalForTesting(
            logits: logits,
            correctionBias: correctionBias,
            rows: rows,
            normalizing: true
        )
        let sorted = gatherSort(x: activations, indices: router.0)
        eval([router.0, router.1, sorted.0, sorted.1, sorted.2])
    }

    func evaluateCandidate() {
        let router = lagunaPrefillRouterTournamentOrdinalRankMapForTesting(
            logits: logits,
            correctionBias: correctionBias,
            rows: rows,
            normalizing: true
        )
        let sorted = lagunaRouterRankMapGatherSortForTesting(
            activations, rankMap: router.2
        )
        eval([
            router.0, router.1, router.2,
            sorted.0, sorted.1, sorted.2,
        ])
    }

    func measure(_ body: () -> Void) -> Double {
        let start = DispatchTime.now().uptimeNanoseconds
        body()
        return Double(DispatchTime.now().uptimeNanoseconds - start) / 1_000_000_000
    }

    for _ in 0 ..< warmupPairs {
        if order == "AB" {
            evaluateControl()
            evaluateCandidate()
        } else {
            evaluateCandidate()
            evaluateControl()
        }
    }

    var controlSamples: [Double] = []
    var candidateSamples: [Double] = []
    controlSamples.reserveCapacity(timedPairs)
    candidateSamples.reserveCapacity(timedPairs)
    for _ in 0 ..< timedPairs {
        if order == "AB" {
            controlSamples.append(measure(evaluateControl))
            candidateSamples.append(measure(evaluateCandidate))
        } else {
            candidateSamples.append(measure(evaluateCandidate))
            controlSamples.append(measure(evaluateControl))
        }
    }

    let controlMedian = routerRankMapMedian(controlSamples)
    let candidateMedian = routerRankMapMedian(candidateSamples)
    let controlMAD = routerRankMapMedian(
        controlSamples.map { abs($0 - controlMedian) }
    )
    let candidateMAD = routerRankMapMedian(
        candidateSamples.map { abs($0 - candidateMedian) }
    )
    let pooledNormalizedMAD = sqrt(
        pow(controlMAD / controlMedian, 2)
            + pow(candidateMAD / candidateMedian, 2)
    )
    let report: [String: Any] = [
        "schema_version": 1,
        "order": order,
        "rows": rows,
        "hidden_width": width,
        "dtype": "bfloat16",
        "normalizing": true,
        "warmup_pairs": warmupPairs,
        "timed_pairs": timedPairs,
        "control_seconds": controlSamples,
        "candidate_seconds": candidateSamples,
        "control_median_seconds": controlMedian,
        "candidate_median_seconds": candidateMedian,
        "control_mad_seconds": controlMAD,
        "candidate_mad_seconds": candidateMAD,
        "speedup": controlMedian / candidateMedian,
        "favorable_delta_fraction": 1 - candidateMedian / controlMedian,
        "pooled_normalized_mad": pooledNormalizedMAD,
        "delta_exceeds_2x_pooled_normalized_mad":
            1 - candidateMedian / controlMedian > 2 * pooledNormalizedMAD,
        "control_generic_enumerator_calls": warmupPairs + timedPairs,
        "candidate_specialized_enumerator_calls": warmupPairs + timedPairs,
        "candidate_generic_enumerator_calls": 0,
        "materialized_outputs": [
            "router_indices", "router_weights", "rank_map_candidate_only",
            "reordered_activations", "row_order", "sorted_indices", "inverse_order",
        ],
    ]
    let data = try JSONSerialization.data(withJSONObject: report, options: [.sortedKeys])
    print("ROUTER_RANK_MAP_BENCHMARK_JSON=" + String(decoding: data, as: UTF8.self))
}

private func routerRankMapMedian(_ values: [Double]) -> Double {
    precondition(!values.isEmpty)
    let sorted = values.sorted()
    let middle = sorted.count / 2
    if sorted.count % 2 == 0 {
        return (sorted[middle - 1] + sorted[middle]) / 2
    }
    return sorted[middle]
}

private func verifyRouterRankMap(
    rows: Int,
    scenario: RouterRankMapScenario,
    normalizing: Bool,
    useBFloat16: Bool
) {
    let inputs = makeRouterInputs(rows: rows, scenario: scenario)
    let floatLogits = MLXArray(inputs.logits, [1, rows, 256])
    let logits = useBFloat16 ? floatLogits.asType(.bfloat16) : floatLogits
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
    let floatActivations = MLXArray(
        activationValues,
        [1, rows, 1, 1, activationWidth]
    )
    let activations = useBFloat16
        ? floatActivations.asType(.bfloat16)
        : floatActivations
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

    let genericActivations = generic.0.asType(.float32).asArray(Float.self)
    let specializedActivations = specialized.0.asType(.float32).asArray(Float.self)
    #expect(generic.0.dtype == activations.dtype)
    #expect(specialized.0.dtype == activations.dtype)
    #expect(specializedActivations == genericActivations)
    #expect(specialized.1.asArray(UInt32.self) == generic.1.asArray(UInt32.self))
    #expect(specialized.2.asArray(UInt32.self) == generic.2.asArray(UInt32.self))

    let expected = expectedEnumeration(rankMap: rankMap, rows: rows)
    #expect(enumeration.0.asArray(UInt32.self) == expected.rows)
    #expect(enumeration.1.asArray(UInt32.self) == expected.experts)
    #expect(enumeration.2.asArray(UInt32.self) == expected.inverse)

    let genericOutput = syntheticRoutedOutput(
        sortedActivations: genericActivations,
        sortedExperts: generic.1.asArray(UInt32.self),
        inverseOrder: generic.2.asArray(UInt32.self),
        width: activationWidth
    )
    let specializedOutput = syntheticRoutedOutput(
        sortedActivations: specializedActivations,
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
