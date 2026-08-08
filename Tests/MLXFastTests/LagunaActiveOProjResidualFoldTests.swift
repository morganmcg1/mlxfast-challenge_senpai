import Foundation
import MLX
import Testing

@testable import MLXFastModel

@Test
func activeOProjResidualFoldMatchesStockChainAndReportsTiming() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_ACTIVE_OPROJ_RESIDUAL_FOLD"] == "1" else {
        return
    }
    defer { Memory.clearCache() }

    for heads in [48, 64] {
        let finite = activeOProjFixture(heads: heads, boundary: false)
        expectActiveOProjChainBitwiseMatch(label: "finite-h\(heads)", fixture: finite)

        let boundary = activeOProjFixture(heads: heads, boundary: true)
        expectActiveOProjChainBitwiseMatch(label: "boundary-h\(heads)", fixture: boundary)

        guard let rawGate = lagunaGatedAffineOProjNVFP4(
            attentionOutput: finite.attention,
            gateLogits: finite.gate,
            codes: finite.codes,
            scales: finite.scales,
            heads: heads,
            gateIsActivated: false
        ) else {
            Issue.record("raw-gate fallback unavailable for H\(heads)")
            continue
        }
        eval(rawGate)
        print("ACTIVE_OPROJ_FALLBACK h=\(heads) outputs=\(rawGate.size) available=true")

        for _ in 0..<6 {
            eval(
                activeOProjControlRouterLogits(finite),
                activeOProjCandidateRouterLogits(finite)
            )
        }

        let samples = 11
        let dispatches = 48
        var abControl = [Double]()
        var abCandidate = [Double]()
        var baCandidate = [Double]()
        var baControl = [Double]()

        for _ in 0..<samples {
            abControl.append(measureActiveOProjBatch(dispatches: dispatches) {
                activeOProjControlRouterLogits(finite)
            })
            abCandidate.append(measureActiveOProjBatch(dispatches: dispatches) {
                activeOProjCandidateRouterLogits(finite)
            })
        }
        for _ in 0..<samples {
            baCandidate.append(measureActiveOProjBatch(dispatches: dispatches) {
                activeOProjCandidateRouterLogits(finite)
            })
            baControl.append(measureActiveOProjBatch(dispatches: dispatches) {
                activeOProjControlRouterLogits(finite)
            })
        }

        let abControlMedian = activeOProjMedian(abControl)
        let abCandidateMedian = activeOProjMedian(abCandidate)
        let baCandidateMedian = activeOProjMedian(baCandidate)
        let baControlMedian = activeOProjMedian(baControl)
        let abSpeedup = abControlMedian / abCandidateMedian
        let baSpeedup = baControlMedian / baCandidateMedian
        let passed = abSpeedup >= 1.003 && baSpeedup >= 1.003

        print("ACTIVE_OPROJ_STAGE2_AB_CONTROL_H\(heads)_SECONDS=\(abControl)")
        print("ACTIVE_OPROJ_STAGE2_AB_CANDIDATE_H\(heads)_SECONDS=\(abCandidate)")
        print("ACTIVE_OPROJ_STAGE2_BA_CANDIDATE_H\(heads)_SECONDS=\(baCandidate)")
        print("ACTIVE_OPROJ_STAGE2_BA_CONTROL_H\(heads)_SECONDS=\(baControl)")
        print(String(
            format: "ACTIVE_OPROJ_STAGE2_MEDIANS h=%d ab_control=%.9f ab_candidate=%.9f ba_candidate=%.9f ba_control=%.9f",
            heads,
            abControlMedian,
            abCandidateMedian,
            baCandidateMedian,
            baControlMedian
        ))
        print(String(
            format: "ACTIVE_OPROJ_STAGE2_SPEEDUPS h=%d ab=%.6f ba=%.6f pass=%@",
            heads,
            abSpeedup,
            baSpeedup,
            passed ? "true" : "false"
        ))
    }
}

private struct ActiveOProjFixture {
    let heads: Int
    let attention: MLXArray
    let gate: MLXArray
    let codes: MLXArray
    let scales: MLXArray
    let residual: MLXArray
    let normWeight: MLXArray
    let routerWeight: MLXArray
}

private func activeOProjFixture(heads: Int, boundary: Bool) -> ActiveOProjFixture {
    let hidden = LagunaConstants.hiddenSize
    let inVec = heads * LagunaConstants.headDim
    let specialBits: [UInt16] = [
        0x0000, 0x8000, 0x0001, 0x8001,
        0x007f, 0x807f, 0x0080, 0x8080,
        0x3f80, 0xbf80, 0x7f7f, 0xff7f,
        0x7f80, 0xff80, 0x7fc1, 0xffc1,
    ]

    let attention = boundary
        ? activeOProjPatternedBF16(shape: [1, 1, inVec], bits: specialBits)
        : activeOProjFiniteBF16(shape: [1, 1, inVec], seed: UInt64(heads) << 48 | 0x1234)
    let gate = boundary
        ? activeOProjPatternedBF16(shape: [1, 1, heads], bits: specialBits.reversed())
        : activeOProjFiniteBF16(shape: [1, 1, heads], seed: UInt64(heads) << 40 | 0x5678)
    let residual = boundary
        ? activeOProjPatternedBF16(shape: [1, 1, hidden], bits: specialBits)
        : activeOProjFiniteBF16(shape: [1, 1, hidden], seed: UInt64(heads) << 32 | 0x9abc)

    return ActiveOProjFixture(
        heads: heads,
        attention: attention,
        gate: gate,
        codes: activeOProjCodes(shape: [hidden, inVec / 8], seed: UInt64(heads) << 56 | 0xdef0),
        scales: activeOProjScales(shape: [hidden, inVec / 16]),
        residual: residual,
        normWeight: activeOProjFiniteBF16(shape: [hidden], seed: UInt64(heads) << 24 | 0x2468),
        routerWeight: activeOProjFiniteBF16(
            shape: [LagunaConstants.numExperts, hidden],
            seed: UInt64(heads) << 16 | 0x1357
        )
    )
}

private func expectActiveOProjChainBitwiseMatch(
    label: String,
    fixture: ActiveOProjFixture
) {
    guard let branch = lagunaGatedAffineOProjNVFP4(
        attentionOutput: fixture.attention,
        gateLogits: fixture.gate,
        codes: fixture.codes,
        scales: fixture.scales,
        heads: fixture.heads,
        gateIsActivated: true
    ), let folded = lagunaGatedAffineOProjNVFP4Residual(
        attentionOutput: fixture.attention,
        gateValues: fixture.gate,
        codes: fixture.codes,
        scales: fixture.scales,
        residual: fixture.residual,
        heads: fixture.heads
    ) else {
        Issue.record("active OProj kernels unavailable for \(label)")
        return
    }

    let control = lagunaResidualRMSNormRouter(
        residual: fixture.residual,
        branch: branch,
        weight: fixture.normWeight,
        routerWeight: fixture.routerWeight
    )
    let candidate = lagunaPresummedRMSNormRouter(
        summed: folded,
        weight: fixture.normWeight,
        routerWeight: fixture.routerWeight
    )
    eval(
        control.summed,
        folded,
        control.normalized,
        candidate.normalized,
        control.routerLogits,
        candidate.routerLogits
    )

    expectActiveOProjBitwiseMatch(label: "\(label)-summed", control.summed, folded)
    expectActiveOProjBitwiseMatch(
        label: "\(label)-normalized", control.normalized, candidate.normalized)
    expectActiveOProjBitwiseMatch(
        label: "\(label)-router", control.routerLogits, candidate.routerLogits)
}

private func expectActiveOProjBitwiseMatch(
    label: String,
    _ control: MLXArray,
    _ candidate: MLXArray
) {
    let controlBits = control.view(dtype: .uint16).asArray(UInt16.self)
    let candidateBits = candidate.view(dtype: .uint16).asArray(UInt16.self)
    let mismatches = zip(controlBits, candidateBits).reduce(into: 0) { count, pair in
        if pair.0 != pair.1 {
            count += 1
        }
    }
    print("ACTIVE_OPROJ_ORACLE label=\(label) outputs=\(controlBits.count) mismatches=\(mismatches)")
    #expect(mismatches == 0)
}

private func activeOProjControlRouterLogits(_ fixture: ActiveOProjFixture) -> MLXArray {
    let branch = lagunaGatedAffineOProjNVFP4(
        attentionOutput: fixture.attention,
        gateLogits: fixture.gate,
        codes: fixture.codes,
        scales: fixture.scales,
        heads: fixture.heads,
        gateIsActivated: true
    )!
    return lagunaResidualRMSNormRouter(
        residual: fixture.residual,
        branch: branch,
        weight: fixture.normWeight,
        routerWeight: fixture.routerWeight
    ).routerLogits
}

private func activeOProjCandidateRouterLogits(_ fixture: ActiveOProjFixture) -> MLXArray {
    let folded = lagunaGatedAffineOProjNVFP4Residual(
        attentionOutput: fixture.attention,
        gateValues: fixture.gate,
        codes: fixture.codes,
        scales: fixture.scales,
        residual: fixture.residual,
        heads: fixture.heads
    )!
    return lagunaPresummedRMSNormRouter(
        summed: folded,
        weight: fixture.normWeight,
        routerWeight: fixture.routerWeight
    ).routerLogits
}

private func measureActiveOProjBatch(
    dispatches: Int,
    operation: () -> MLXArray
) -> Double {
    let outputs = (0..<dispatches).map { _ in operation() }
    let merged = stacked(outputs)
    let start = DispatchTime.now().uptimeNanoseconds
    eval(merged)
    let elapsed = DispatchTime.now().uptimeNanoseconds - start
    return Double(elapsed) / 1_000_000_000 / Double(dispatches)
}

private func activeOProjMedian(_ values: [Double]) -> Double {
    let sorted = values.sorted()
    return sorted[sorted.count / 2]
}

private func activeOProjFiniteBF16(shape: [Int], seed: UInt64) -> MLXArray {
    let count = shape.reduce(1, *)
    var state = seed
    let bits = Array<UInt16>(unsafeUninitializedCapacity: count) { buffer, initializedCount in
        for index in buffer.indices {
            state ^= state << 13
            state ^= state >> 7
            state ^= state << 17
            let sign = UInt16((state >> 63) << 15)
            let exponent = UInt16(120 + ((state >> 8) & 7)) << 7
            let mantissa = UInt16(state & 0x7f)
            buffer[index] = sign | exponent | mantissa
        }
        initializedCount = count
    }
    return MLXArray(bits, shape).view(dtype: .bfloat16)
}

private func activeOProjPatternedBF16<S: Collection>(
    shape: [Int],
    bits pattern: S
) -> MLXArray where S.Element == UInt16 {
    let pattern = Array(pattern)
    let count = shape.reduce(1, *)
    let bits = Array<UInt16>(unsafeUninitializedCapacity: count) { buffer, initializedCount in
        for index in buffer.indices {
            buffer[index] = pattern[index % pattern.count]
        }
        initializedCount = count
    }
    return MLXArray(bits, shape).view(dtype: .bfloat16)
}

private func activeOProjCodes(shape: [Int], seed: UInt64) -> MLXArray {
    let count = shape.reduce(1, *)
    var state = seed
    let values = Array<UInt32>(unsafeUninitializedCapacity: count) { buffer, initializedCount in
        for index in buffer.indices {
            state ^= state << 13
            state ^= state >> 7
            state ^= state << 17
            buffer[index] = UInt32(truncatingIfNeeded: state)
        }
        initializedCount = count
    }
    return MLXArray(values, shape)
}

private func activeOProjScales(shape: [Int]) -> MLXArray {
    let pattern: [UInt8] = [0x30, 0x34, 0x38, 0x3c]
    let count = shape.reduce(1, *)
    let values = Array<UInt8>(unsafeUninitializedCapacity: count) { buffer, initializedCount in
        for index in buffer.indices {
            buffer[index] = pattern[index % pattern.count]
        }
        initializedCount = count
    }
    return MLXArray(values, shape)
}
