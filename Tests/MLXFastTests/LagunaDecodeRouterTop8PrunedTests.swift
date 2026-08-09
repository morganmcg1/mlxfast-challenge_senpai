import Foundation
import MLX
@testable import MLXFastModel
import Testing

@Suite(.serialized)
struct LagunaDecodeRouterTop8PrunedTests {
    @Test
    func mergeNetworkCoversEveryRelativeOrdering() {
        let ranked = (0..<16).map {
            RankedItem(key: UInt32($0), index: UInt32($0))
        }
        var partitions = 0

        for mask in 0..<(1 << 16) where mask.nonzeroBitCount == 8 {
            let left = ranked.enumerated().compactMap { offset, item in
                mask & (1 << offset) != 0 ? item : nil
            }
            let right = ranked.enumerated().compactMap { offset, item in
                mask & (1 << offset) == 0 ? item : nil
            }
            #expect(mergeTopEight(left, right) == Array(ranked.prefix(8)))
            partitions += 1
        }

        #expect(partitions == 12_870)
    }

    @Test
    func hierarchicalMergeMatchesFullSortWithTies() {
        let items = (0..<256).map {
            RankedItem(
                key: UInt32(($0 * 73 + ($0 / 8) * 19) % 23),
                index: UInt32($0)
            )
        }
        var level = stride(from: 0, to: items.count, by: 8).map {
            Array(items[$0..<($0 + 8)]).sorted(by: rankedBefore)
        }

        while level.count > 1 {
            level = stride(from: 0, to: level.count, by: 2).map {
                mergeTopEight(level[$0], level[$0 + 1])
            }
        }

        #expect(level[0] == Array(items.sorted(by: rankedBefore).prefix(8)))
        #expect(32 * 24 + 16 * 20 + 8 * 20 + (4 + 2 + 1) * 20 == 1_388)
    }

    @Test
    func prunedKernelMatchesAcceptedKernelWhenRuntimeTestsAreEnabled() {
        guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1"
        else { return }

        var checkedCorruptionControls = false
        for testCase in routerCases() {
            for dtype in [DType.float32, .bfloat16] {
                let baseLogits = MLXArray(testCase.logits, [1, 1, 256])
                let logits = dtype == .bfloat16 ? baseLogits.asType(.bfloat16) : baseLogits
                let bias = MLXArray(testCase.bias, [256])

                for normalizing in [false, true] {
                    let accepted = lagunaDecodeRouterTop8AcceptedForTesting(
                        logits: logits,
                        correctionBias: bias,
                        normalizing: normalizing
                    )
                    let candidate = lagunaDecodeRouterTop8OrdinalScoreTableForTesting(
                        logits: logits,
                        correctionBias: bias,
                        normalizing: normalizing
                    )
                    eval(accepted.0, accepted.1, candidate.0, candidate.1)

                    let acceptedResult = capture(indices: accepted.0, scores: accepted.1)
                    let candidateResult = capture(indices: candidate.0, scores: candidate.1)
                    let label = "\(testCase.name), \(dtype), normalizing=\(normalizing)"
                    #expect(
                        resultsMatch(acceptedResult, candidateResult),
                        Comment(rawValue: label)
                    )

                    if !checkedCorruptionControls {
                        var corruptedIndex = candidateResult
                        corruptedIndex.indices[0] ^= 1
                        #expect(!resultsMatch(acceptedResult, corruptedIndex))

                        var corruptedScore = candidateResult
                        corruptedScore.scoreBits[0] ^= 1
                        #expect(!resultsMatch(acceptedResult, corruptedScore))
                        checkedCorruptionControls = true
                    }
                }
            }
        }

        #expect(checkedCorruptionControls)
    }
}

private struct RankedItem: Equatable {
    let key: UInt32
    let index: UInt32
}

private struct RouterCase {
    let name: String
    let logits: [Float]
    let bias: [Float]
}

private struct RouterResult {
    var indices: [UInt32]
    var scoreBits: [UInt32]
}

private func rankedBefore(_ lhs: RankedItem, _ rhs: RankedItem) -> Bool {
    lhs.key < rhs.key || (lhs.key == rhs.key && lhs.index < rhs.index)
}

private func mergeTopEight(_ left: [RankedItem], _ right: [RankedItem]) -> [RankedItem] {
    precondition(left.count == 8 && right.count == 8)
    var winners = (0..<8).map {
        let other = right[7 - $0]
        return rankedBefore(other, left[$0]) ? other : left[$0]
    }

    for stride in [4, 2, 1] {
        let prior = winners
        for lane in 0..<8 {
            let other = prior[lane ^ stride]
            let otherBefore = rankedBefore(other, prior[lane])
            let isLower = lane & stride == 0
            if isLower ? otherBefore : !otherBefore {
                winners[lane] = other
            }
        }
    }
    return winners
}

private func routerCases() -> [RouterCase] {
    let pseudorandom = RouterCase(
        name: "pseudorandom",
        logits: (0..<256).map {
            Float((($0 * 73 + $0 * $0 * 17) % 401) - 200) / 17
        },
        bias: (0..<256).map {
            Float((($0 * 43 + 11) % 97) - 48) / 37
        }
    )
    let tied = RouterCase(
        name: "tie-heavy",
        logits: (0..<256).map { Float(($0 % 7) - 3) / 2 },
        bias: (0..<256).map { Float((($0 / 8) % 5) - 2) / 4 }
    )

    var distributedLogits = (0..<256).map { -8 + Float($0 % 13) / 100 }
    var distributedBias = Array(repeating: Float(-3), count: 256)
    for (rank, index) in [3, 36, 69, 102, 135, 168, 201, 234].enumerated() {
        distributedLogits[index] = 2 - Float(rank) / 10
        distributedBias[index] = 3
    }
    let distributed = RouterCase(
        name: "all-simdgroups",
        logits: distributedLogits,
        bias: distributedBias
    )

    var specialLogits = (0..<256).map { Float(($0 % 19) - 9) / 4 }
    var specialBias = (0..<256).map { Float(($0 % 11) - 5) / 8 }
    specialLogits[0] = .infinity
    specialLogits[1] = -.infinity
    specialLogits[2] = 0
    specialLogits[3] = -0.0
    specialLogits[4] = .nan
    specialLogits[5] = 8
    specialLogits[6] = -8
    specialBias[2] = 10
    specialBias[3] = 10
    specialBias[7] = .nan
    let special = RouterCase(
        name: "nan-infinity-signed-zero",
        logits: specialLogits,
        bias: specialBias
    )

    return [pseudorandom, tied, distributed, special]
}

private func capture(indices: MLXArray, scores: MLXArray) -> RouterResult {
    RouterResult(
        indices: indices.asArray(UInt32.self),
        scoreBits: scores.asArray(Float.self).map { $0.bitPattern }
    )
}

private func resultsMatch(_ lhs: RouterResult, _ rhs: RouterResult) -> Bool {
    lhs.indices == rhs.indices && lhs.scoreBits == rhs.scoreBits
}
