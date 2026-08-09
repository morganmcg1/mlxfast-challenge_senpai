import Dispatch
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
    func zeroOneTopologyIsExhaustiveForLeafAndMerge() {
        for mask in 0..<256 {
            var values = (0..<8).map { (mask >> $0) & 1 }
            sortEightBits(&values)
            #expect(values == values.sorted())
        }

        for leftZeros in 0...8 {
            for rightZeros in 0...8 {
                let left = Array(repeating: 0, count: leftZeros)
                    + Array(repeating: 1, count: 8 - leftZeros)
                let right = Array(repeating: 0, count: rightZeros)
                    + Array(repeating: 1, count: 8 - rightZeros)
                let expected = Array((left + right).sorted().prefix(8))
                #expect(mergeTopEightBits(left, right) == expected)
            }
        }
    }

    @Test
    func hierarchicalMergeMatchesFullSortWithTies() {
        var items: [RankedItem] = []
        items.reserveCapacity(256)
        for index in 0..<256 {
            let key = UInt32((index * 73 + (index / 8) * 19) % 23)
            items.append(RankedItem(key: key, index: UInt32(index)))
        }
        var level = stride(from: 0, to: items.count, by: 8).map {
            Array(items[$0..<($0 + 8)]).sorted(by: rankedBefore)
        }

        while level.count > 1 {
            level = stride(from: 0, to: level.count, by: 2).map {
                mergeTopEight(level[$0], level[$0 + 1])
            }
        }

        let expected = Array(items.sorted(by: rankedBefore).prefix(8))
        let comparatorCount = 32 * 24 + 31 * 20
        #expect(level[0] == expected)
        #expect(comparatorCount == 1_388)
    }

    @Test
    func prunedKernelMatchesAcceptedKernelWhenRuntimeTestsAreEnabled() {
        guard runtimeRouterTestsEnabled else { return }

        var checkedCorruptionControls = false
        for testCase in routerCases() {
            checkCompiledRouterCase(
                testCase,
                includeRecomputedScores: true,
                checkedCorruptionControls: &checkedCorruptionControls
            )
        }
        #expect(checkedCorruptionControls)
    }

    @Test
    func prunedKernelCoversEveryExpertAtEveryRankWhenRuntimeTestsAreEnabled() {
        guard runtimeRouterTestsEnabled else { return }

        var coverage = Array(repeating: Array(repeating: 0, count: 256), count: 8)
        var ignoredCorruptionControls = true
        for shift in 0..<256 {
            var logits = Array(repeating: Float(-8), count: 256)
            for rank in 0..<8 {
                let expert = (shift + rank * 33) % 256
                logits[expert] = 8.0 - Float(rank) * 0.75
                coverage[rank][expert] += 1
            }
            checkCompiledRouterCase(
                RouterCase(
                    name: "cyclic-shift-\(shift)",
                    logits: logits,
                    bias: Array(repeating: 0, count: 256)
                ),
                includeRecomputedScores: false,
                checkedCorruptionControls: &ignoredCorruptionControls
            )
        }
        #expect(coverage.allSatisfy { $0.allSatisfy { $0 == 1 } })
    }

    @Test
    func prunedKernelMatchesAcceptedKernelOnRandomizedRowsWhenRuntimeTestsAreEnabled() {
        guard runtimeRouterTestsEnabled else { return }

        var ignoredCorruptionControls = true
        for testCase in randomizedRouterCases(count: 256) {
            checkCompiledRouterCase(
                testCase,
                includeRecomputedScores: false,
                checkedCorruptionControls: &ignoredCorruptionControls
            )
        }
    }

    @Test
    func isolatedNormalizingScoreTableBenchmarkWhenEnabled() {
        guard ProcessInfo.processInfo.environment["MLXFAST_RUN_ROUTER_BENCHMARK"] == "1"
        else { return }

        let testCase = routerCases()[0]
        let logits = MLXArray(testCase.logits, [1, 1, 256]).asType(.bfloat16)
        let bias = MLXArray(testCase.bias, [256])
        eval(logits, bias)

        let accepted = {
            lagunaDecodeRouterTop8AcceptedForTesting(
                logits: logits, correctionBias: bias, normalizing: true)
        }
        let candidate = {
            lagunaDecodeRouterTop8OrdinalScoreTableForTesting(
                logits: logits, correctionBias: bias, normalizing: true)
        }

        for _ in 0..<8 {
            _ = measureRouterBatch(accepted)
            _ = measureRouterBatch(candidate)
            _ = measureRouterBatch(candidate)
            _ = measureRouterBatch(accepted)
            _ = measureRouterBatch(candidate)
            _ = measureRouterBatch(accepted)
            _ = measureRouterBatch(accepted)
            _ = measureRouterBatch(candidate)
        }

        var abbaSpeedups: [Double] = []
        var baabSpeedups: [Double] = []
        var acceptedNanoseconds: [Double] = []
        var candidateNanoseconds: [Double] = []
        abbaSpeedups.reserveCapacity(61)
        baabSpeedups.reserveCapacity(61)
        for _ in 0..<61 {
            let abba = [
                measureRouterBatch(accepted),
                measureRouterBatch(candidate),
                measureRouterBatch(candidate),
                measureRouterBatch(accepted),
            ]
            acceptedNanoseconds.append(contentsOf: [abba[0], abba[3]])
            candidateNanoseconds.append(contentsOf: [abba[1], abba[2]])
            abbaSpeedups.append(sqrt((abba[0] * abba[3]) / (abba[1] * abba[2])))

            let baab = [
                measureRouterBatch(candidate),
                measureRouterBatch(accepted),
                measureRouterBatch(accepted),
                measureRouterBatch(candidate),
            ]
            acceptedNanoseconds.append(contentsOf: [baab[1], baab[2]])
            candidateNanoseconds.append(contentsOf: [baab[0], baab[3]])
            baabSpeedups.append(sqrt((baab[1] * baab[2]) / (baab[0] * baab[3])))
        }

        let abbaMedian = median(abbaSpeedups)
        let baabMedian = median(baabSpeedups)
        let abbaLogMAD = medianAbsoluteDeviation(abbaSpeedups.map(log))
        let baabLogMAD = medianAbsoluteDeviation(baabSpeedups.map(log))
        print(
            String(
                format:
                    "ROUTER_TOP8_ISOLATED dispatches_per_batch=39 superblocks_per_order=61 accepted_ns_per_dispatch=%.3f candidate_ns_per_dispatch=%.3f abba_speedup=%.6f abba_log_mad=%.6f baab_speedup=%.6f baab_log_mad=%.6f",
                median(acceptedNanoseconds), median(candidateNanoseconds), abbaMedian,
                abbaLogMAD, baabMedian, baabLogMAD
            )
        )

        #expect(abbaMedian >= 1.005)
        #expect(baabMedian >= 1.005)
        #expect(log(abbaMedian) > 2 * abbaLogMAD)
        #expect(log(baabMedian) > 2 * baabLogMAD)
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

private typealias RouterKernel = () -> (MLXArray, MLXArray)

private var runtimeRouterTestsEnabled: Bool {
    ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1"
}

private func checkCompiledRouterCase(
    _ testCase: RouterCase,
    includeRecomputedScores: Bool,
    checkedCorruptionControls: inout Bool
) {
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
            let scoreTable = lagunaDecodeRouterTop8OrdinalScoreTableForTesting(
                logits: logits,
                correctionBias: bias,
                normalizing: normalizing
            )
            let recomputed = includeRecomputedScores
                ? lagunaDecodeRouterTop8OrdinalForTesting(
                    logits: logits,
                    correctionBias: bias,
                    normalizing: normalizing
                ) : nil
            var outputs = [accepted.0, accepted.1, scoreTable.0, scoreTable.1]
            if let recomputed {
                outputs.append(contentsOf: [recomputed.0, recomputed.1])
            }
            eval(outputs)

            let acceptedResult = capture(indices: accepted.0, scores: accepted.1)
            let scoreTableResult = capture(indices: scoreTable.0, scores: scoreTable.1)
            let label = "\(testCase.name), \(dtype), normalizing=\(normalizing)"
            #expect(
                resultsMatch(acceptedResult, scoreTableResult),
                Comment(rawValue: "score-table: \(label)")
            )
            if let recomputed {
                let recomputedResult = capture(indices: recomputed.0, scores: recomputed.1)
                #expect(
                    resultsMatch(acceptedResult, recomputedResult),
                    Comment(rawValue: "recomputed: \(label)")
                )
            }

            if !checkedCorruptionControls {
                var droppedWinner = scoreTableResult
                droppedWinner.indices[0] = droppedWinner.indices[1]
                #expect(!resultsMatch(acceptedResult, droppedWinner))

                var swappedRanks = scoreTableResult
                swappedRanks.indices.swapAt(0, 1)
                swappedRanks.scoreBits.swapAt(0, 1)
                #expect(!resultsMatch(acceptedResult, swappedRanks))

                var corruptedIndex = scoreTableResult
                corruptedIndex.indices[0] ^= 1
                #expect(!resultsMatch(acceptedResult, corruptedIndex))

                var corruptedScore = scoreTableResult
                corruptedScore.scoreBits[0] ^= 1
                #expect(!resultsMatch(acceptedResult, corruptedScore))
                checkedCorruptionControls = true
            }
        }
    }
}

private func measureRouterBatch(_ invoke: RouterKernel) -> Double {
    var outputs: [MLXArray] = []
    outputs.reserveCapacity(78)
    for _ in 0..<39 {
        let result = invoke()
        outputs.append(result.0)
        outputs.append(result.1)
    }

    let start = DispatchTime.now().uptimeNanoseconds
    eval(outputs)
    let elapsed = DispatchTime.now().uptimeNanoseconds - start
    return Double(elapsed) / 39.0
}

private func median(_ values: [Double]) -> Double {
    precondition(!values.isEmpty)
    let sorted = values.sorted()
    let middle = sorted.count / 2
    if sorted.count.isMultiple(of: 2) {
        return (sorted[middle - 1] + sorted[middle]) / 2
    }
    return sorted[middle]
}

private func medianAbsoluteDeviation(_ values: [Double]) -> Double {
    let center = median(values)
    return median(values.map { abs($0 - center) })
}

private func sortEightBits(_ values: inout [Int]) {
    for sequence in [2, 4, 8] {
        var stride = sequence / 2
        while stride > 0 {
            let prior = values
            for lane in 0..<8 {
                let other = prior[lane ^ stride]
                let isLower = lane & stride == 0
                let lowerWantsBetter = lane & sequence == 0
                let wantBetter = lowerWantsBetter == isLower
                if wantBetter ? other < prior[lane] : other > prior[lane] {
                    values[lane] = other
                }
            }
            stride /= 2
        }
    }
}

private func mergeTopEightBits(_ left: [Int], _ right: [Int]) -> [Int] {
    var winners = (0..<8).map { min(left[$0], right[7 - $0]) }
    for stride in [4, 2, 1] {
        let prior = winners
        for lane in 0..<8 {
            let other = prior[lane ^ stride]
            let isLower = lane & stride == 0
            if isLower ? other < prior[lane] : other > prior[lane] {
                winners[lane] = other
            }
        }
    }
    return winners
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
    var pseudorandomLogits: [Float] = []
    var pseudorandomBias: [Float] = []
    var tiedLogits: [Float] = []
    var tiedBias: [Float] = []
    var distributedLogits: [Float] = []
    var specialLogits: [Float] = []
    var specialBias: [Float] = []
    for index in 0..<256 {
        let randomLogit = ((index * 73 + index * index * 17) % 401) - 200
        let randomBias = ((index * 43 + 11) % 97) - 48
        pseudorandomLogits.append(Float(randomLogit) / 17.0)
        pseudorandomBias.append(Float(randomBias) / 37.0)
        tiedLogits.append(Float((index % 7) - 3) / 2.0)
        tiedBias.append(Float(((index / 8) % 5) - 2) / 4.0)
        distributedLogits.append(-8.0 + Float(index % 13) / 100.0)
        specialLogits.append(Float((index % 19) - 9) / 4.0)
        specialBias.append(Float((index % 11) - 5) / 8.0)
    }

    let pseudorandom = RouterCase(
        name: "pseudorandom",
        logits: pseudorandomLogits,
        bias: pseudorandomBias
    )
    let tied = RouterCase(name: "tie-heavy", logits: tiedLogits, bias: tiedBias)

    var distributedBias = Array(repeating: Float(-3), count: 256)
    for (rank, index) in [3, 36, 69, 102, 135, 168, 201, 234].enumerated() {
        distributedLogits[index] = 2.0 - Float(rank) / 10.0
        distributedBias[index] = 3.0
    }
    let distributed = RouterCase(
        name: "all-simdgroups",
        logits: distributedLogits,
        bias: distributedBias
    )

    specialLogits[0] = .infinity
    specialLogits[1] = -.infinity
    specialLogits[2] = 0.0
    specialLogits[3] = -0.0
    specialLogits[4] = Float(bitPattern: 0x7FC0_0001)
    specialLogits[5] = Float(bitPattern: 0xFFC1_2345)
    specialLogits[6] = 8.0
    specialLogits[7] = -8.0
    specialBias[2] = 10.0
    specialBias[3] = 10.0
    specialBias[8] = Float(bitPattern: 0x7FC0_1111)
    specialBias[9] = Float(bitPattern: 0xFFC0_2222)
    let special = RouterCase(
        name: "nan-payload-infinity-signed-zero",
        logits: specialLogits,
        bias: specialBias
    )

    return [pseudorandom, tied, distributed, special]
}

private struct SplitMix64 {
    var state: UInt64

    mutating func next() -> UInt64 {
        state &+= 0x9E37_79B9_7F4A_7C15
        var value = state
        value = (value ^ (value >> 30)) &* 0xBF58_476D_1CE4_E5B9
        value = (value ^ (value >> 27)) &* 0x94D0_49BB_1331_11EB
        return value ^ (value >> 31)
    }
}

private func randomizedRouterCases(count: Int) -> [RouterCase] {
    var random = SplitMix64(state: 0xA11C_E5E5_CAFE_BEEF)
    return (0..<count).map { caseIndex in
        var logits: [Float] = []
        var bias: [Float] = []
        logits.reserveCapacity(256)
        bias.reserveCapacity(256)
        for _ in 0..<256 {
            if caseIndex.isMultiple(of: 4) {
                logits.append(Float(Int(random.next() % 33) - 16) / 4.0)
            } else {
                logits.append(Float(Int(random.next() % 4097) - 2048) / 128.0)
            }
            bias.append(Float(Int(random.next() % 1025) - 512) / 256.0)
        }
        return RouterCase(name: "random-\(caseIndex)", logits: logits, bias: bias)
    }
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
