import Foundation
import MLX
import Testing

@testable import MLXFastModel

@Test
func denseDownActivationStagingMatchesControlAndReportsMirroredTiming() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_DENSE_DOWN_STAGING"] == "1" else {
        return
    }
    defer { Memory.clearCache() }

    let activationShape = [1, 1, LagunaConstants.denseIntermediateSize]
    let weightShape = [
        LagunaConstants.hiddenSize, LagunaConstants.denseIntermediateSize,
    ]
    let residualShape = [1, 1, LagunaConstants.hiddenSize]

    let weightA = finiteBF16Tensor(shape: weightShape, seed: 0x1234_5678_9abc_def0)
    let activationA = finiteBF16Tensor(shape: activationShape, seed: 0x3141_5926_5358_9793)
    let residualA = finiteBF16Tensor(shape: residualShape, seed: 0x2718_2818_2845_9045)
    expectDenseDownBitwiseMatch(
        label: "finite-a",
        activation: activationA,
        weight: weightA,
        residual: residualA
    )

    let boundaryBits: [UInt16] = [
        0x0000, 0x8000, 0x0001, 0x8001,
        0x007f, 0x807f, 0x0080, 0x8080,
        0x3f80, 0xbf80, 0x7f7f, 0xff7f,
        0x7f80, 0xff80, 0x7fc1, 0xffc1,
    ]
    let boundaryActivation = patternedBF16Tensor(shape: activationShape, bits: boundaryBits)
    let boundaryResidual = patternedBF16Tensor(
        shape: residualShape,
        bits: boundaryBits.reversed()
    )
    expectDenseDownBitwiseMatch(
        label: "boundary",
        activation: boundaryActivation,
        weight: weightA,
        residual: boundaryResidual
    )

    let weightB = finiteBF16Tensor(shape: weightShape, seed: 0x0fed_cba9_8765_4321)
    let activationB = finiteBF16Tensor(shape: activationShape, seed: 0x1111_2222_3333_4444)
    let residualB = finiteBF16Tensor(shape: residualShape, seed: 0x5555_6666_7777_8888)
    expectDenseDownBitwiseMatch(
        label: "finite-b",
        activation: activationB,
        weight: weightB,
        residual: residualB
    )

    for _ in 0..<6 {
        eval(
            lagunaDenseDownResidualControlForTesting(
                activationA, downWeight: weightA, residual: residualA),
            lagunaDenseDownResidual(
                activationA, downWeight: weightA, residual: residualA)
        )
    }

    let sampleCount = 11
    let dispatchesPerSample = 48
    var abControl = [Double]()
    var abCandidate = [Double]()
    var baCandidate = [Double]()
    var baControl = [Double]()

    for _ in 0..<sampleCount {
        abControl.append(measureDenseDownBatch(
            dispatches: dispatchesPerSample,
            operation: {
                lagunaDenseDownResidualControlForTesting(
                    activationA, downWeight: weightA, residual: residualA)
            }
        ))
        abCandidate.append(measureDenseDownBatch(
            dispatches: dispatchesPerSample,
            operation: {
                lagunaDenseDownResidual(
                    activationA, downWeight: weightA, residual: residualA)
            }
        ))
    }
    for _ in 0..<sampleCount {
        baCandidate.append(measureDenseDownBatch(
            dispatches: dispatchesPerSample,
            operation: {
                lagunaDenseDownResidual(
                    activationA, downWeight: weightA, residual: residualA)
            }
        ))
        baControl.append(measureDenseDownBatch(
            dispatches: dispatchesPerSample,
            operation: {
                lagunaDenseDownResidualControlForTesting(
                    activationA, downWeight: weightA, residual: residualA)
            }
        ))
    }

    let abControlMedian = median(abControl)
    let abCandidateMedian = median(abCandidate)
    let baControlMedian = median(baControl)
    let baCandidateMedian = median(baCandidate)
    let abSpeedup = abControlMedian / abCandidateMedian
    let baSpeedup = baControlMedian / baCandidateMedian
    let stageOnePass = abSpeedup >= 1.003 && baSpeedup >= 1.003

    print("DENSE_DOWN_STAGE1_AB_CONTROL_SECONDS=\(abControl)")
    print("DENSE_DOWN_STAGE1_AB_CANDIDATE_SECONDS=\(abCandidate)")
    print("DENSE_DOWN_STAGE1_BA_CANDIDATE_SECONDS=\(baCandidate)")
    print("DENSE_DOWN_STAGE1_BA_CONTROL_SECONDS=\(baControl)")
    print(String(
        format: "DENSE_DOWN_STAGE1_MEDIANS ab_control=%.9f ab_candidate=%.9f ba_candidate=%.9f ba_control=%.9f",
        abControlMedian,
        abCandidateMedian,
        baCandidateMedian,
        baControlMedian
    ))
    print(String(
        format: "DENSE_DOWN_STAGE1_SPEEDUPS ab=%.6f ba=%.6f pass=%@",
        abSpeedup,
        baSpeedup,
        stageOnePass ? "true" : "false"
    ))
}

private func expectDenseDownBitwiseMatch(
    label: String,
    activation: MLXArray,
    weight: MLXArray,
    residual: MLXArray
) {
    let control = lagunaDenseDownResidualControlForTesting(
        activation, downWeight: weight, residual: residual)
    let candidate = lagunaDenseDownResidual(
        activation, downWeight: weight, residual: residual)
    eval(control, candidate)

    let controlBits = control.view(dtype: .uint16).asArray(UInt16.self)
    let candidateBits = candidate.view(dtype: .uint16).asArray(UInt16.self)
    let mismatches = zip(controlBits, candidateBits).reduce(into: 0) { count, pair in
        if pair.0 != pair.1 {
            count += 1
        }
    }
    print("DENSE_DOWN_ORACLE label=\(label) outputs=\(controlBits.count) mismatches=\(mismatches)")
    #expect(mismatches == 0)
}

private func measureDenseDownBatch(
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

private func median(_ values: [Double]) -> Double {
    let sorted = values.sorted()
    return sorted[sorted.count / 2]
}

private func finiteBF16Tensor(shape: [Int], seed: UInt64) -> MLXArray {
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

private func patternedBF16Tensor<S: Collection>(
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
