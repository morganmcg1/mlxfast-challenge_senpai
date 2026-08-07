import Dispatch
import Foundation
import MLX
@testable import MLXFastModel
import Testing

private struct RouterInputCase {
    let name: String
    let logits: [Float]
    let correctionBias: [Float]
}

private struct RouterTimingPair {
    let controlSeconds: Double
    let candidateSeconds: Double

    var speedup: Double { controlSeconds / candidateSeconds }
}

private struct RouterLCG {
    var state: UInt64

    mutating func nextUInt32() -> UInt32 {
        state = state &* 6_364_136_223_846_793_005 &+ 1_442_695_040_888_963_407
        return UInt32(truncatingIfNeeded: state >> 32)
    }

    mutating func nextFloat(scale: Float) -> Float {
        Float(Int32(bitPattern: nextUInt32())) / Float(Int32.max) * scale
    }
}

private func routerPingPongCases() -> [RouterInputCase] {
    let positiveZero = Float(bitPattern: 0x0000_0000)
    let negativeZero = Float(bitPattern: 0x8000_0000)
    let nanPatterns: [Float] = [
        Float(bitPattern: 0x7fc0_0001),
        Float(bitPattern: 0x7fa1_2345),
        Float(bitPattern: 0xffc0_0002),
        Float(bitPattern: 0xffa5_4321),
    ]
    let infinityPattern: [Float] = [
        .infinity, -.infinity, .greatestFiniteMagnitude, -.greatestFiniteMagnitude,
        1, -1, positiveZero, negativeZero,
    ]
    let extremePattern: [Float] = [
        .greatestFiniteMagnitude, -.greatestFiniteMagnitude,
        .leastNormalMagnitude, -.leastNormalMagnitude,
        .leastNonzeroMagnitude, -.leastNonzeroMagnitude,
        positiveZero, negativeZero,
    ]

    var cases = [
        RouterInputCase(
            name: "all-ties",
            logits: Array(repeating: Float(0), count: 256),
            correctionBias: Array(repeating: Float(0), count: 256)
        ),
        RouterInputCase(
            name: "signed-zero",
            logits: (0..<256).map { $0.isMultiple(of: 2) ? positiveZero : negativeZero },
            correctionBias: (0..<256).map { $0.isMultiple(of: 3) ? negativeZero : positiveZero }
        ),
        RouterInputCase(
            name: "infinities",
            logits: (0..<256).map { infinityPattern[$0 % infinityPattern.count] },
            correctionBias: (0..<256).map {
                infinityPattern[(infinityPattern.count - 1 - $0) % infinityPattern.count]
            }
        ),
        RouterInputCase(
            name: "nan-payloads",
            logits: (0..<256).map { nanPatterns[$0 % nanPatterns.count] },
            correctionBias: (0..<256).map {
                nanPatterns[(nanPatterns.count - 1 - $0) % nanPatterns.count]
            }
        ),
        RouterInputCase(
            name: "nan-finite-mix",
            logits: (0..<256).map {
                let pattern = nanPatterns + [positiveZero, negativeZero, 1, -1]
                return pattern[$0 % pattern.count]
            },
            correctionBias: (0..<256).map {
                let pattern: [Float] = [0.125, -0.125] + nanPatterns
                return pattern[$0 % pattern.count]
            }
        ),
        RouterInputCase(
            name: "extremes",
            logits: (0..<256).map { extremePattern[$0 % extremePattern.count] },
            correctionBias: (0..<256).map {
                extremePattern[(extremePattern.count - 1 - $0) % extremePattern.count]
            }
        ),
    ]

    var generator = RouterLCG(state: 0x9e37_79b9_7f4a_7c15)
    for caseIndex in 0..<32 {
        let logits = (0..<256).map { _ in generator.nextFloat(scale: 12) }
        let correctionBias = (0..<256).map { _ in generator.nextFloat(scale: 0.25) }
        cases.append(
            RouterInputCase(
                name: "random-\(caseIndex)",
                logits: logits,
                correctionBias: correctionBias
            )
        )
    }
    return cases
}

private func routerOutputsMatch(
    inputCase: RouterInputCase, dtype: DType, normalizing: Bool, repetition: Int
) -> Bool {
    let logits = MLXArray(inputCase.logits, [256]).asType(dtype)
    let correctionBias = MLXArray(inputCase.correctionBias, [256])
    let control = lagunaDecodeRouterTop8OrdinalScoreTableForTesting(
        logits: logits,
        correctionBias: correctionBias,
        normalizing: normalizing
    )
    let candidate = lagunaDecodeRouterTop8OrdinalScoreTablePingPongForTesting(
        logits: logits,
        correctionBias: correctionBias,
        normalizing: normalizing
    )
    eval([control.0, control.1, candidate.0, candidate.1])
    Stream.gpu.synchronize()

    let controlIndices = control.0.asArray(UInt32.self)
    let candidateIndices = candidate.0.asArray(UInt32.self)
    let controlScoreBits = control.1.asArray(Float.self).map { $0.bitPattern }
    let candidateScoreBits = candidate.1.asArray(Float.self).map { $0.bitPattern }
    let context =
        "case=\(inputCase.name) dtype=\(dtype) normalizing=\(normalizing) repetition=\(repetition)"

    var matches = true
    if controlIndices != candidateIndices {
        Issue.record("router index mismatch: \(context)")
        matches = false
    }
    if controlScoreBits != candidateScoreBits {
        Issue.record("router raw FP32 score mismatch: \(context)")
        matches = false
    }
    return matches
}

private func routerTimingRows() -> [(logits: MLXArray, correctionBias: MLXArray)] {
    var generator = RouterLCG(state: 0xd1b5_4a32_d192_ed03)
    var rows: [(logits: MLXArray, correctionBias: MLXArray)] = []
    rows.reserveCapacity(39)
    for _ in 0..<39 {
        let logits = (0..<256).map { _ in generator.nextFloat(scale: 10) }
        let correctionBias = (0..<256).map { _ in generator.nextFloat(scale: 0.2) }
        rows.append(
            (
                MLXArray(logits, [256]).asType(.bfloat16),
                MLXArray(correctionBias, [256])
            )
        )
    }
    eval(rows.flatMap { [$0.logits, $0.correctionBias] })
    Stream.gpu.synchronize()
    return rows
}

private func measureRouterArm(
    rows: [(logits: MLXArray, correctionBias: MLXArray)], candidate: Bool
) -> Double {
    let start = DispatchTime.now().uptimeNanoseconds
    var outputs: [MLXArray] = []
    outputs.reserveCapacity(rows.count * 2)
    for row in rows {
        let pair: (MLXArray, MLXArray)
        if candidate {
            pair = lagunaDecodeRouterTop8OrdinalScoreTablePingPongForTesting(
                logits: row.logits,
                correctionBias: row.correctionBias
            )
        } else {
            pair = lagunaDecodeRouterTop8OrdinalScoreTableForTesting(
                logits: row.logits,
                correctionBias: row.correctionBias
            )
        }
        outputs.append(pair.0)
        outputs.append(pair.1)
    }
    eval(outputs)
    Stream.gpu.synchronize()
    return Double(DispatchTime.now().uptimeNanoseconds - start) * 1e-9
}

private func median(_ values: [Double]) -> Double {
    let sorted = values.sorted()
    let middle = sorted.count / 2
    if sorted.count.isMultiple(of: 2) {
        return (sorted[middle - 1] + sorted[middle]) / 2
    }
    return sorted[middle]
}

private func pairedLogMedian(_ pairs: [RouterTimingPair]) -> Double {
    exp(median(pairs.map { log($0.speedup) }))
}

private func bootstrapPairedLogMedianCI(
    _ pairs: [RouterTimingPair], seed: UInt64, resamples: Int = 10_000
) -> [Double] {
    let values = pairs.map { log($0.speedup) }
    var generator = RouterLCG(state: seed)
    var medians: [Double] = []
    medians.reserveCapacity(resamples)
    for _ in 0..<resamples {
        var sample: [Double] = []
        sample.reserveCapacity(values.count)
        for _ in values.indices {
            sample.append(values[Int(generator.nextUInt32()) % values.count])
        }
        medians.append(median(sample))
    }
    medians.sort()
    return [
        exp(medians[Int(Double(resamples - 1) * 0.025)]),
        exp(medians[Int(Double(resamples - 1) * 0.975)]),
    ]
}

private func timingPairJSON(_ pair: RouterTimingPair) -> [String: Double] {
    [
        "control_seconds": pair.controlSeconds,
        "candidate_seconds": pair.candidateSeconds,
        "speedup": pair.speedup,
    ]
}

@Suite(.serialized)
struct LagunaRouterPingPongTests {
    @Test
    func routerPingPongMatchesControlAndMeasuresBalancedOrdersWhenEnabled() throws {
        guard
            ProcessInfo.processInfo.environment["MLXFAST_RUN_ROUTER_PING_PONG_TESTS"] == "1"
        else {
            return
        }

        let cases = routerPingPongCases()
        var correctnessPassed = true
        for repetition in 0..<4 {
            for inputCase in cases {
                for dtype in [DType.float32, .bfloat16] {
                    for normalizing in [false, true] {
                        correctnessPassed =
                            routerOutputsMatch(
                                inputCase: inputCase,
                                dtype: dtype,
                                normalizing: normalizing,
                                repetition: repetition
                            ) && correctnessPassed
                    }
                }
            }
        }
        guard correctnessPassed else { return }

        let rows = routerTimingRows()
        for _ in 0..<4 {
            _ = measureRouterArm(rows: rows, candidate: false)
            _ = measureRouterArm(rows: rows, candidate: true)
        }

        var orderGenerator = RouterLCG(state: 0xa076_1d64_78bd_642f)
        var abPairs: [RouterTimingPair] = []
        var baPairs: [RouterTimingPair] = []
        abPairs.reserveCapacity(61)
        baPairs.reserveCapacity(61)
        for _ in 0..<61 {
            let useABBA = orderGenerator.nextUInt32().isMultiple(of: 2)
            let order = useABBA ? [false, true, true, false] : [true, false, false, true]
            let durations = order.map { measureRouterArm(rows: rows, candidate: $0) }
            if useABBA {
                abPairs.append(
                    RouterTimingPair(controlSeconds: durations[0], candidateSeconds: durations[1])
                )
                baPairs.append(
                    RouterTimingPair(controlSeconds: durations[3], candidateSeconds: durations[2])
                )
            } else {
                baPairs.append(
                    RouterTimingPair(controlSeconds: durations[1], candidateSeconds: durations[0])
                )
                abPairs.append(
                    RouterTimingPair(controlSeconds: durations[2], candidateSeconds: durations[3])
                )
            }
        }

        let abMedian = pairedLogMedian(abPairs)
        let baMedian = pairedLogMedian(baPairs)
        let threshold = 1.002
        let report: [String: Any] = [
            "event": "router_ping_pong_gate1",
            "architecture": GPU.deviceInfo().architecture,
            "grid": [256, 1, 1],
            "threadgroup": [256, 1, 1],
            "control_threadgroup_memory_bytes": 3_072,
            "candidate_threadgroup_memory_bytes": 5_120,
            "dispatches_per_arm": rows.count,
            "correctness_cases": cases.count,
            "correctness_repetitions": 4,
            "dtypes": ["float32", "bfloat16"],
            "normalizing_modes": [false, true],
            "ab_samples": abPairs.map(timingPairJSON),
            "ba_samples": baPairs.map(timingPairJSON),
            "ab_paired_log_median_speedup": abMedian,
            "ba_paired_log_median_speedup": baMedian,
            "ab_bootstrap_ci95": bootstrapPairedLogMedianCI(
                abPairs, seed: 0xe703_7ed1_a0b4_28db),
            "ba_bootstrap_ci95": bootstrapPairedLogMedianCI(
                baPairs, seed: 0x8ebc_6af0_9c88_c6e3),
            "gate_threshold": threshold,
            "passed_gate": abMedian >= threshold && baMedian >= threshold,
        ]
        let data = try JSONSerialization.data(withJSONObject: report, options: [.sortedKeys])
        print("ROUTER_PING_PONG_GATE1 \(String(decoding: data, as: UTF8.self))")
    }
}
