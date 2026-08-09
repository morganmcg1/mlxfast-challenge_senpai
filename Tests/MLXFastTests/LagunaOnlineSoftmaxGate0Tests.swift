import Dispatch
import Foundation
import MLX
import Testing
@testable import MLXFastModel

private enum Gate0AttentionFamily: String, CaseIterable {
    case sliding
    case full

    var heads: Int {
        switch self {
        case .sliding: LagunaConstants.slidingAttentionHeads
        case .full: LagunaConstants.fullAttentionHeads
        }
    }

    var capacity: Int {
        switch self {
        case .sliding: LagunaConstants.slidingWindow
        case .full: 640
        }
    }

    func writeIndex(for length: Int) -> Int {
        switch self {
        case .sliding: (length - 1) % LagunaConstants.slidingWindow
        case .full: length - 1
        }
    }

    var angleWidth: Int {
        switch self {
        case .sliding: LagunaConstants.headDim
        case .full: LagunaConstants.headDim / 2
        }
    }
}

private enum Gate0ScorePattern: String, CaseIterable {
    case increasing
    case decreasing
    case equal
    case random
}

private struct Gate0Fixture {
    let rawQueries: MLXArray
    let rawKeys: MLXArray
    let rawValues: MLXArray
    let queryWeight: MLXArray
    let keyWeight: MLXArray
    let angles: MLXArray
    let cacheKeys: MLXArray
    let cacheValues: MLXArray
    let writeIndex: Int
    let scale: MLXArray
}

private struct Gate0TimingTotals {
    var baseline: UInt64 = 0
    var candidate: UInt64 = 0

    var speedup: Double {
        Double(baseline) / Double(candidate)
    }
}

@Test
func onlineSoftmaxIdentityRescaleGate0() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
        return
    }

    let lengths = [513, 544, 640]
    let orders: [(String, [Bool])] = [
        ("ABBA", [false, true, true, false]),
        ("BAAB", [true, false, false, true]),
    ]
    var aggregateSpeedups: [String: [Double]] = [:]
    var unchangedBranches: UInt64 = 0
    var growthBranches: UInt64 = 0

    for family in Gate0AttentionFamily.allCases {
        for length in lengths {
            for pattern in Gate0ScorePattern.allCases {
                let label = "\(family.rawValue)-L\(length)-\(pattern.rawValue)"
                let baseline = makeGate0Fixture(family: family, length: length, pattern: pattern)
                let candidate = makeGate0Fixture(family: family, length: length, pattern: pattern)
                let baselineOutputs = invokeGate0(
                    family: family,
                    fixture: baseline,
                    skipIdentity: false,
                    countBranches: true
                )
                let candidateOutputs = invokeGate0(
                    family: family,
                    fixture: candidate,
                    skipIdentity: true,
                    countBranches: true
                )
                eval([
                    baselineOutputs[0], baselineOutputs[1], baseline.cacheKeys,
                    baseline.cacheValues, candidateOutputs[0], candidateOutputs[1],
                    candidate.cacheKeys, candidate.cacheValues,
                ])

                expectExactBF16(baselineOutputs[0], candidateOutputs[0], label: "\(label)-output")
                expectExactBF16(baseline.cacheKeys, candidate.cacheKeys, label: "\(label)-keys")
                expectExactBF16(baseline.cacheValues, candidate.cacheValues, label: "\(label)-values")
                let baselineCounts = baselineOutputs[1].asArray(UInt32.self)
                let candidateCounts = candidateOutputs[1].asArray(UInt32.self)
                #expect(baselineCounts == candidateCounts)
                unchangedBranches += baselineCounts.enumerated().reduce(into: UInt64(0)) {
                    if $1.offset.isMultiple(of: 2) { $0 += UInt64($1.element) }
                }
                growthBranches += baselineCounts.enumerated().reduce(into: UInt64(0)) {
                    if !$1.offset.isMultiple(of: 2) { $0 += UInt64($1.element) }
                }

                let timingBaseline = makeGate0Fixture(
                    family: family, length: length, pattern: pattern)
                let timingCandidate = makeGate0Fixture(
                    family: family, length: length, pattern: pattern)
                for skipIdentity in [false, true, false, true] {
                    let fixture = skipIdentity ? timingCandidate : timingBaseline
                    let outputs = invokeGate0(
                        family: family,
                        fixture: fixture,
                        skipIdentity: skipIdentity,
                        countBranches: false
                    )
                    eval(outputs[0])
                }

                for (orderName, order) in orders {
                    var totals = Gate0TimingTotals()
                    for _ in 0..<20 {
                        for skipIdentity in order {
                            let fixture = skipIdentity ? timingCandidate : timingBaseline
                            let start = DispatchTime.now().uptimeNanoseconds
                            let outputs = invokeGate0(
                                family: family,
                                fixture: fixture,
                                skipIdentity: skipIdentity,
                                countBranches: false
                            )
                            eval(outputs[0])
                            let elapsed = DispatchTime.now().uptimeNanoseconds - start
                            if skipIdentity {
                                totals.candidate += elapsed
                            } else {
                                totals.baseline += elapsed
                            }
                        }
                    }
                    let key = "\(family.rawValue)-\(orderName)"
                    aggregateSpeedups[key, default: []].append(totals.speedup)
                    print(
                        "GATE0 case=\(label) order=\(orderName) "
                            + "baseline_ns=\(totals.baseline) candidate_ns=\(totals.candidate) "
                            + "speedup=\(String(format: \"%.6f\", totals.speedup))"
                    )
                }
            }
        }
    }

    print("GATE0 branches unchanged=\(unchangedBranches) growth=\(growthBranches)")
    #expect(unchangedBranches > 0)
    #expect(growthBranches > 0)
    for family in Gate0AttentionFamily.allCases {
        for orderName in orders.map(\.0) {
            let key = "\(family.rawValue)-\(orderName)"
            let values = aggregateSpeedups[key] ?? []
            let geometricMean = exp(values.map(log).reduce(0, +) / Double(values.count))
            print(
                "GATE0 aggregate=\(key) cases=\(values.count) "
                    + "geomean_speedup=\(String(format: \"%.6f\", geometricMean))"
            )
            #expect(values.count == lengths.count * Gate0ScorePattern.allCases.count)
            #expect(geometricMean >= 1.01)
        }
    }
}

private func invokeGate0(
    family: Gate0AttentionFamily,
    fixture: Gate0Fixture,
    skipIdentity: Bool,
    countBranches: Bool
) -> [MLXArray] {
    switch family {
    case .sliding:
        lagunaSlidingFusedAttentionGate0(
            rawQueries: fixture.rawQueries,
            rawKeys: fixture.rawKeys,
            rawValues: fixture.rawValues,
            queryWeight: fixture.queryWeight,
            keyWeight: fixture.keyWeight,
            angles: fixture.angles,
            cacheKeys: fixture.cacheKeys,
            cacheValues: fixture.cacheValues,
            writeIdx: fixture.writeIndex,
            scale: fixture.scale,
            skipIdentity: skipIdentity,
            countBranches: countBranches
        )
    case .full:
        lagunaFullFusedAttentionGate0(
            rawQueries: fixture.rawQueries,
            rawKeys: fixture.rawKeys,
            rawValues: fixture.rawValues,
            queryWeight: fixture.queryWeight,
            keyWeight: fixture.keyWeight,
            angles: fixture.angles,
            cacheKeys: fixture.cacheKeys,
            cacheValues: fixture.cacheValues,
            writeIdx: fixture.writeIndex,
            scale: fixture.scale,
            skipIdentity: skipIdentity,
            countBranches: countBranches
        )
    }
}

private func makeGate0Fixture(
    family: Gate0AttentionFamily,
    length: Int,
    pattern: Gate0ScorePattern
) -> Gate0Fixture {
    let headDim = LagunaConstants.headDim
    let kvHeads = LagunaConstants.numKeyValueHeads
    let rawQueries = MLXArray(
        Array(repeating: Float(1), count: family.heads * headDim),
        [1, 1, family.heads * headDim]
    ).asType(.bfloat16)
    let rawKeys = MLXArray(
        Array(repeating: Float(1), count: kvHeads * headDim),
        [1, 1, kvHeads * headDim]
    ).asType(.bfloat16)
    let rawValues = MLXArray(
        (0..<(kvHeads * headDim)).map { Float(($0 * 7) % 29 - 14) / 16 },
        [1, 1, kvHeads * headDim]
    ).asType(.bfloat16)
    let queryWeight = MLXArray(Array(repeating: Float(1), count: headDim), [headDim])
        .asType(.bfloat16)
    let keyWeight = MLXArray(Array(repeating: Float(1), count: headDim), [headDim])
        .asType(.bfloat16)
    let halfAngles = family.angleWidth / 2
    let angleValues = Array(repeating: Float(1), count: halfAngles)
        + Array(repeating: Float(0), count: halfAngles)
    let angles = MLXArray(angleValues, [1, 1, 1, family.angleWidth])
    let scores = gate0Scores(pattern: pattern, count: family.capacity)
    var keyValues = Array(
        repeating: Float(0),
        count: kvHeads * family.capacity * headDim
    )
    var valueValues = keyValues
    for kvHead in 0..<kvHeads {
        for position in 0..<family.capacity {
            for component in 0..<headDim {
                let offset = (kvHead * family.capacity + position) * headDim + component
                keyValues[offset] = scores[position]
                let centered = (position * 13 + component * 5 + kvHead * 11) % 61 - 30
                valueValues[offset] = Float(centered) / 32
            }
        }
    }
    let cacheShape = [1, kvHeads, family.capacity, headDim]
    return Gate0Fixture(
        rawQueries: rawQueries,
        rawKeys: rawKeys,
        rawValues: rawValues,
        queryWeight: queryWeight,
        keyWeight: keyWeight,
        angles: angles,
        cacheKeys: MLXArray(keyValues, cacheShape).asType(.bfloat16),
        cacheValues: MLXArray(valueValues, cacheShape).asType(.bfloat16),
        writeIndex: family.writeIndex(for: length),
        scale: MLXArray([1 / sqrt(Float(headDim))])
    )
}

private func gate0Scores(pattern: Gate0ScorePattern, count: Int) -> [Float] {
    switch pattern {
    case .increasing:
        return (0..<count).map { -0.75 + 1.5 * Float($0) / Float(count - 1) }
    case .decreasing:
        return (0..<count).map { 0.75 - 1.5 * Float($0) / Float(count - 1) }
    case .equal:
        return Array(repeating: Float(0.25), count: count)
    case .random:
        var state = UInt32(0x1234_5678)
        return (0..<count).map { _ in
            state = 1_664_525 &* state &+ 1_013_904_223
            return Float(state & 0xffff) / Float(UInt16.max) * 1.5 - 0.75
        }
    }
}

private func expectExactBF16(_ lhs: MLXArray, _ rhs: MLXArray, label: String) {
    let lhsBits = lhs.view(dtype: .uint16).asArray(UInt16.self)
    let rhsBits = rhs.view(dtype: .uint16).asArray(UInt16.self)
    if lhsBits != rhsBits {
        print("GATE0 exact mismatch label=\(label)")
    }
    #expect(lhsBits == rhsBits)
}
