import Dispatch
import Foundation
import MLX
@testable import MLXFastModel
import Testing

private let denseGateUpHiddenSize = 2_048
private let denseGateUpOutputSize = 8_192
private let denseGateUpWeightRows = 2 * denseGateUpOutputSize

private func denseGateUpPatternedCase(adversarial: Bool) -> (MLXArray, MLXArray) {
    let inputValues = (0..<denseGateUpHiddenSize).map { index -> Float in
        if adversarial {
            return index.isMultiple(of: 2) ? 1 : -1
        }
        return Float((index * 17) % 29 - 14) / 32
    }
    let columnValues = (0..<denseGateUpHiddenSize).map { index -> Float in
        if adversarial {
            switch index % 4 {
            case 0: return 1
            case 1: return 1
            case 2: return -1
            default: return -1
            }
        }
        return Float((index * 13) % 31 - 15) / 64
    }
    let rowValues = (0..<denseGateUpWeightRows).map { row -> Float in
        let magnitude = Float((row * 7) % 23 + 1) / (adversarial ? 8 : 128)
        return row.isMultiple(of: 2) ? magnitude : -magnitude
    }

    let input = MLXArray(inputValues, [1, 1, denseGateUpHiddenSize]).asType(.bfloat16)
    let columns = MLXArray(columnValues, [1, denseGateUpHiddenSize])
    let rows = MLXArray(rowValues, [denseGateUpWeightRows, 1])
    let weight = contiguous((rows * columns).asType(.bfloat16))
    eval(input, weight)
    return (input, weight)
}

private func denseGateUpRandomCase() -> (MLXArray, MLXArray) {
    let input = MLXRandom.uniform(
        low: -0.5,
        high: 0.5,
        [1, 1, denseGateUpHiddenSize],
        key: MLXRandom.key(0xC0FFEE)
    ).asType(.bfloat16)
    let weight = contiguous(
        MLXRandom.uniform(
            low: -0.125,
            high: 0.125,
            [denseGateUpWeightRows, denseGateUpHiddenSize],
            key: MLXRandom.key(0xBAD5EED)
        ).asType(.bfloat16)
    )
    eval(input, weight)
    return (input, weight)
}

private func denseGateUpCase(named name: String) -> (MLXArray, MLXArray) {
    switch name {
    case "representative":
        return denseGateUpPatternedCase(adversarial: false)
    case "random":
        return denseGateUpRandomCase()
    case "adversarial":
        return denseGateUpPatternedCase(adversarial: true)
    default:
        fatalError("unknown dense gate/up oracle case: \(name)")
    }
}

@Test
func denseGateUpTwoRowsMatchesFourRowsBitwiseWhenEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_DENSE_GATEUP_ORACLE"] == "1" else {
        return
    }

    var lastCandidateBytes = Data()
    for name in ["representative", "random", "adversarial"] {
        let (input, weight) = denseGateUpCase(named: name)
        let baseline = lagunaDenseGateUpSwiGLU(
            input,
            fusedWeight: weight,
            rowsPerSIMDGroup: 4
        )
        let candidate = lagunaDenseGateUpSwiGLU(
            input,
            fusedWeight: weight,
            rowsPerSIMDGroup: 2
        )
        eval(baseline, candidate)

        let baselineBytes = baseline.asData(access: .copy).data
        let candidateBytes = candidate.asData(access: .copy).data
        #expect(baseline.shape == [1, 1, denseGateUpOutputSize])
        #expect(candidate.shape == baseline.shape)
        #expect(baselineBytes.count == denseGateUpOutputSize * 2)
        #expect(candidateBytes == baselineBytes)
        print(
            "DENSE_GATEUP_ORACLE case=\(name) outputs=\(denseGateUpOutputSize) "
                + "bytes=\(candidateBytes.count) bitwise_equal=\(candidateBytes == baselineBytes)"
        )
        lastCandidateBytes = candidateBytes
    }

    var corrupted = lastCandidateBytes
    let first = corrupted.startIndex
    corrupted[first] = corrupted[first] ^ 1
    #expect(corrupted != lastCandidateBytes)
    print("DENSE_GATEUP_ORACLE positive_corruption_detected=true")
}

private func denseGateUpTimedLaunch(
    input: MLXArray,
    weight: MLXArray,
    rowsPerSIMDGroup: Int
) -> Double {
    let start = DispatchTime.now().uptimeNanoseconds
    let output = lagunaDenseGateUpSwiGLU(
        input,
        fusedWeight: weight,
        rowsPerSIMDGroup: rowsPerSIMDGroup
    )
    eval(output)
    let end = DispatchTime.now().uptimeNanoseconds
    return Double(end - start) / 1_000_000_000
}

private func denseGateUpMedian(_ values: [Double]) -> Double {
    let sorted = values.sorted()
    return sorted[sorted.count / 2]
}

private func denseGateUpSecondsJSON(_ values: [Double]) -> String {
    values.map { String(format: "%.9f", $0) }.joined(separator: ",")
}

@Test
func denseGateUpTwoRowsIsolatedTimingWhenEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_DENSE_GATEUP_ISOLATED"] == "1" else {
        return
    }
    let order = ProcessInfo.processInfo.environment["MLXFAST_DENSE_GATEUP_TIMING_ORDER"] ?? "AB"
    precondition(order == "AB" || order == "BA")

    let (input, weight) = denseGateUpRandomCase()
    for _ in 0..<6 {
        _ = denseGateUpTimedLaunch(input: input, weight: weight, rowsPerSIMDGroup: 4)
        _ = denseGateUpTimedLaunch(input: input, weight: weight, rowsPerSIMDGroup: 2)
    }

    GPU.resetPeakMemory()
    var baselineSeconds: [Double] = []
    var candidateSeconds: [Double] = []
    baselineSeconds.reserveCapacity(51)
    candidateSeconds.reserveCapacity(51)
    for _ in 0..<51 {
        if order == "AB" {
            baselineSeconds.append(
                denseGateUpTimedLaunch(input: input, weight: weight, rowsPerSIMDGroup: 4)
            )
            candidateSeconds.append(
                denseGateUpTimedLaunch(input: input, weight: weight, rowsPerSIMDGroup: 2)
            )
        } else {
            candidateSeconds.append(
                denseGateUpTimedLaunch(input: input, weight: weight, rowsPerSIMDGroup: 2)
            )
            baselineSeconds.append(
                denseGateUpTimedLaunch(input: input, weight: weight, rowsPerSIMDGroup: 4)
            )
        }
    }

    let baselineMedian = denseGateUpMedian(baselineSeconds)
    let candidateMedian = denseGateUpMedian(candidateSeconds)
    let speedup = baselineMedian / candidateMedian
    print("DENSE_GATEUP_TIMING order=\(order) architecture=\(GPU.deviceInfo().architecture)")
    print("DENSE_GATEUP_TIMING baseline_seconds=[\(denseGateUpSecondsJSON(baselineSeconds))]")
    print("DENSE_GATEUP_TIMING candidate_seconds=[\(denseGateUpSecondsJSON(candidateSeconds))]")
    print(
        String(
            format: "DENSE_GATEUP_TIMING baseline_median=%.9f candidate_median=%.9f speedup=%.6f",
            baselineMedian,
            candidateMedian,
            speedup
        )
    )
    print(
        "DENSE_GATEUP_DIAGNOSTICS threadgroup_threads=512 baseline_threadgroups=128 "
            + "candidate_threadgroups=256 baseline_fp32_accumulators_per_lane=8 "
            + "candidate_fp32_accumulators_per_lane=4 runtime_launches_per_dense_decode_step=1 "
            + "peak_memory_bytes=\(Memory.peakMemory)"
    )
    print(
        "DENSE_GATEUP_DIAGNOSTICS physical_register_occupancy_spill_counters=unavailable_"
            + "from_MLXFast_runtime source_live_accumulator_reduction=8_to_4"
    )
    #expect(baselineSeconds.count == 51)
    #expect(candidateSeconds.count == 51)
}
