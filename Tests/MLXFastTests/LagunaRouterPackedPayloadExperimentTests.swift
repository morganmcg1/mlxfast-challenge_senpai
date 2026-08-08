import Foundation
import MLX
@testable import MLXFastModel
import Testing

private struct RouterPackedCase {
    let name: String
    let logits: [Float]
    let bias: [Float]
}

private struct RouterPackedStats {
    let median: Double
    let mad: Double

    var normalizedMAD: Double {
        median == 0 ? .infinity : mad / median
    }
}

private func routerPackedMedian(_ values: [Double]) -> Double {
    let sorted = values.sorted()
    let middle = sorted.count / 2
    if sorted.count.isMultiple(of: 2) {
        return (sorted[middle - 1] + sorted[middle]) / 2
    }
    return sorted[middle]
}

private func routerPackedStats(_ values: [Double]) -> RouterPackedStats {
    let median = routerPackedMedian(values)
    return RouterPackedStats(
        median: median,
        mad: routerPackedMedian(values.map { abs($0 - median) })
    )
}

private func routerPackedRandomValues(seed: UInt32) -> [Float] {
    var state = seed
    return (0..<256).map { _ in
        state = state &* 1_664_525 &+ 1_013_904_223
        return (Float(state) / Float(UInt32.max) - 0.5) * 32
    }
}

private func routerPackedCases() -> [RouterPackedCase] {
    let randomLogits = routerPackedRandomValues(seed: 0x1234_5678)
    let randomBias = routerPackedRandomValues(seed: 0x8765_4321).map { $0 * 0.0625 }
    let special: [Float] = [
        0, -0, Float.greatestFiniteMagnitude, -Float.greatestFiniteMagnitude,
        Float.leastNonzeroMagnitude, -Float.leastNonzeroMagnitude,
        .infinity, -.infinity,
        Float(bitPattern: 0x7fc0_0001), Float(bitPattern: 0xffc0_0021),
        1, -1, 88, -88, 0.5, -0.5,
    ]
    let specialLogits = (0..<256).map { special[$0 % special.count] }
    let specialBias = (0..<256).map { special[($0 * 5 + 3) % special.count] }
    let permutedLogits = (0..<256).map { randomLogits[($0 * 73 + 19) % 256] }
    let permutedBias = (0..<256).map { randomBias[($0 * 151 + 7) % 256] }

    return [
        RouterPackedCase(name: "random", logits: randomLogits, bias: randomBias),
        RouterPackedCase(
            name: "ties", logits: Array(repeating: 0.25, count: 256),
            bias: Array(repeating: 0, count: 256)),
        RouterPackedCase(
            name: "signed-zero", logits: (0..<256).map { $0.isMultiple(of: 2) ? 0 : -0 },
            bias: (0..<256).map { $0.isMultiple(of: 3) ? -0 : 0 }),
        RouterPackedCase(
            name: "special-logits", logits: specialLogits,
            bias: Array(repeating: 0, count: 256)),
        RouterPackedCase(
            name: "special-bias", logits: randomLogits, bias: specialBias),
        RouterPackedCase(name: "permuted", logits: permutedLogits, bias: permutedBias),
    ]
}

private func routerPackedOutputs(
    logits: MLXArray,
    bias: MLXArray,
    scoreTable: Bool,
    normalizing: Bool,
    packed: Bool
) -> (MLXArray, MLXArray) {
    if scoreTable {
        if packed {
            return lagunaDecodeRouterTop8OrdinalScoreTablePackedForTesting(
                logits: logits, correctionBias: bias, normalizing: normalizing)
        }
        return lagunaDecodeRouterTop8OrdinalScoreTableForTesting(
            logits: logits, correctionBias: bias, normalizing: normalizing)
    }
    if packed {
        return lagunaDecodeRouterTop8OrdinalPackedForTesting(
            logits: logits, correctionBias: bias, normalizing: normalizing)
    }
    return lagunaDecodeRouterTop8OrdinalForTesting(
        logits: logits, correctionBias: bias, normalizing: normalizing)
}

private func routerPackedRawOutputs(
    _ output: (MLXArray, MLXArray)
) -> ([UInt32], [UInt32]) {
    (
        output.0.asArray(UInt32.self),
        output.1.asArray(Float.self).map(\.bitPattern)
    )
}

@Test
func lagunaRouterPackedPayloadMatchesControlBitExactlyWhenRuntimeTestsAreEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
        return
    }

    var checkedConfigurations = 0
    var corruptionControlChecked = false
    for testCase in routerPackedCases() {
        for dtype in [DType.float32, DType.bfloat16] {
            let logits = MLXArray(testCase.logits, [256]).asType(dtype)
            let bias = MLXArray(testCase.bias, [256])
            for scoreTable in [false, true] {
                for normalizing in [false, true] {
                    let control = routerPackedOutputs(
                        logits: logits,
                        bias: bias,
                        scoreTable: scoreTable,
                        normalizing: normalizing,
                        packed: false
                    )
                    let candidate = routerPackedOutputs(
                        logits: logits,
                        bias: bias,
                        scoreTable: scoreTable,
                        normalizing: normalizing,
                        packed: true
                    )
                    eval(control.0, control.1, candidate.0, candidate.1)
                    let controlRaw = routerPackedRawOutputs(control)
                    let candidateRaw = routerPackedRawOutputs(candidate)
                    #expect(
                        controlRaw.0 == candidateRaw.0,
                        "index mismatch for \(testCase.name), \(dtype), table=\(scoreTable), norm=\(normalizing)"
                    )
                    #expect(
                        controlRaw.1 == candidateRaw.1,
                        "score-bit mismatch for \(testCase.name), \(dtype), table=\(scoreTable), norm=\(normalizing)"
                    )
                    checkedConfigurations += 1

                    if !corruptionControlChecked {
                        var corruptedIndices = candidateRaw.0
                        corruptedIndices[0] = (corruptedIndices[0] + 1) % 256
                        #expect(
                            controlRaw.0 != corruptedIndices || controlRaw.1 != candidateRaw.1,
                            "corruption control failed to detect a deliberately changed index"
                        )
                        corruptionControlChecked = true
                    }
                }
            }
        }
    }

    #expect(checkedConfigurations == 48)
    #expect(corruptionControlChecked)
    print("ROUTER_PACKED_CORRECTNESS configurations=\(checkedConfigurations) corruption_control=true")
}

private func routerPackedTimedBatch(
    logits: MLXArray,
    bias: MLXArray,
    packed: Bool,
    dispatches: Int = 39
) -> Double {
    var outputs: [MLXArray] = []
    outputs.reserveCapacity(dispatches * 2)
    let start = DispatchTime.now().uptimeNanoseconds
    for _ in 0..<dispatches {
        let output = routerPackedOutputs(
            logits: logits,
            bias: bias,
            scoreTable: true,
            normalizing: true,
            packed: packed
        )
        outputs.append(output.0)
        outputs.append(output.1)
    }
    eval(outputs)
    let end = DispatchTime.now().uptimeNanoseconds
    return Double(end - start) / Double(dispatches)
}

@Test
func lagunaRouterPackedPayloadGate1WhenRuntimeTestsAreEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
        return
    }

    let logits = MLXArray(routerPackedRandomValues(seed: 0x3141_5926), [256]).asType(.bfloat16)
    let bias = MLXArray(routerPackedRandomValues(seed: 0x2718_2818).map { $0 * 0.0625 }, [256])

    for _ in 0..<8 {
        _ = routerPackedTimedBatch(logits: logits, bias: bias, packed: false)
        _ = routerPackedTimedBatch(logits: logits, bias: bias, packed: true)
    }

    var abControl: [Double] = []
    var abCandidate: [Double] = []
    var baControl: [Double] = []
    var baCandidate: [Double] = []
    abControl.reserveCapacity(61)
    abCandidate.reserveCapacity(61)
    baControl.reserveCapacity(61)
    baCandidate.reserveCapacity(61)

    for superblock in 0..<122 {
        if superblock.isMultiple(of: 2) {
            let a1 = routerPackedTimedBatch(logits: logits, bias: bias, packed: false)
            let b1 = routerPackedTimedBatch(logits: logits, bias: bias, packed: true)
            let b2 = routerPackedTimedBatch(logits: logits, bias: bias, packed: true)
            let a2 = routerPackedTimedBatch(logits: logits, bias: bias, packed: false)
            abControl.append((a1 + a2) / 2)
            abCandidate.append((b1 + b2) / 2)
        } else {
            let b1 = routerPackedTimedBatch(logits: logits, bias: bias, packed: true)
            let a1 = routerPackedTimedBatch(logits: logits, bias: bias, packed: false)
            let a2 = routerPackedTimedBatch(logits: logits, bias: bias, packed: false)
            let b2 = routerPackedTimedBatch(logits: logits, bias: bias, packed: true)
            baControl.append((a1 + a2) / 2)
            baCandidate.append((b1 + b2) / 2)
        }
    }

    let abControlStats = routerPackedStats(abControl)
    let abCandidateStats = routerPackedStats(abCandidate)
    let baControlStats = routerPackedStats(baControl)
    let baCandidateStats = routerPackedStats(baCandidate)
    let abSpeedup = abControlStats.median / abCandidateStats.median
    let baSpeedup = baControlStats.median / baCandidateStats.median
    let abNoise = max(abControlStats.normalizedMAD, abCandidateStats.normalizedMAD)
    let baNoise = max(baControlStats.normalizedMAD, baCandidateStats.normalizedMAD)
    let passes =
        abSpeedup >= 1.003 && baSpeedup >= 1.003
        && abSpeedup >= 1 && baSpeedup >= 1
        && (abSpeedup - 1) > 2 * abNoise
        && (baSpeedup - 1) > 2 * baNoise

    print(
        String(
            format:
                "ROUTER_PACKED_GATE1 ab_speedup=%.6f ba_speedup=%.6f ab_control_ns=%.1f ab_candidate_ns=%.1f ba_control_ns=%.1f ba_candidate_ns=%.1f ab_nmad=%.6f ba_nmad=%.6f superblocks_per_order=61 dispatches_per_arm_sample=39 passes=%@",
            abSpeedup,
            baSpeedup,
            abControlStats.median,
            abCandidateStats.median,
            baControlStats.median,
            baCandidateStats.median,
            abNoise,
            baNoise,
            passes ? "true" : "false"
        )
    )
}
