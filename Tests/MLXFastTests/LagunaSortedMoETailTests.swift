import Foundation
import MLX
@testable import MLXFastModel
import Testing

private struct SortedMoETailInputs {
    let sortedExpertOutputs: MLXArray
    let inverseOrder: MLXArray
    let routerWeights: MLXArray
    let sharedOutput: MLXArray
    let residual: MLXArray
}

private func makeSortedMoETailInputs(rows: Int) -> SortedMoETailInputs {
    let hidden = 2048
    let experts = 8
    let sortedRows = rows * experts
    let columnAxis = MLXArray(0..<hidden).asType(.float32).reshaped([1, hidden])
    let sortedRowAxis = MLXArray(0..<sortedRows).asType(.float32).reshaped([sortedRows, 1])
    let rowAxis = MLXArray(0..<rows).asType(.float32).reshaped([rows, 1])
    let expertAxis = MLXArray(0..<experts).asType(.float32).reshaped([1, 1, experts])

    let sortedExpertOutputs = (
        sin(sortedRowAxis * 0.013 + columnAxis * 0.007) * 0.125
    ).asType(.bfloat16)
    let inverseOrder = MLXArray(
        (0..<sortedRows).map { UInt32(($0 * 17) % sortedRows) }, [sortedRows]
    )
    let routerWeights = (
        cos(expertAxis * 0.19 + rowAxis.reshaped([1, rows, 1]) * 0.011) * 0.0625
            + 0.125
    ).asType(.float32)
    let sharedOutput = (
        sin(rowAxis * 0.017 + columnAxis * 0.003) * 0.25
    ).asType(.bfloat16).reshaped([1, rows, hidden])
    let residual = (
        cos(rowAxis * 0.023 + columnAxis * 0.005) * 0.5
    ).asType(.bfloat16).reshaped([1, rows, hidden])
    eval(sortedExpertOutputs, inverseOrder, routerWeights, sharedOutput, residual)

    return SortedMoETailInputs(
        sortedExpertOutputs: sortedExpertOutputs,
        inverseOrder: inverseOrder,
        routerWeights: routerWeights,
        sharedOutput: sharedOutput,
        residual: residual
    )
}

private func runSortedMoETail(
    _ inputs: SortedMoETailInputs,
    threadGroupWidth: Int
) -> MLXArray {
    lagunaPrefillSortedMoETail(
        sortedExpertOutputs: inputs.sortedExpertOutputs,
        inverseOrder: inputs.inverseOrder,
        routerWeights: inputs.routerWeights,
        sharedOutput: inputs.sharedOutput,
        residual: inputs.residual,
        threadGroupWidth: threadGroupWidth
    )
}

@Test
func lagunaSortedMoETailTG512MatchesTG256WhenEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_SORTED_MOE_TAIL_TESTS"] == "1"
    else {
        return
    }

    for rows in [2, 3, 4, 5, 511, 512, 513] {
        let inputs = makeSortedMoETailInputs(rows: rows)
        let control = runSortedMoETail(inputs, threadGroupWidth: 256)
        let candidate = runSortedMoETail(inputs, threadGroupWidth: 512)
        eval(control, candidate)
        let maxAbsoluteDifference = abs(
            control.asType(.float32) - candidate.asType(.float32)
        ).max().item(Float.self)
        print("sorted_moe_tail_correctness rows=\(rows) max_abs_diff=\(maxAbsoluteDifference)")
        #expect(control.shape == [1, rows, 2048])
        #expect(candidate.shape == control.shape)
        #expect(maxAbsoluteDifference == 0, "TG512 changed the BF16 tail output at rows=\(rows)")
    }
}

private func measureSortedMoETail(
    _ inputs: SortedMoETailInputs,
    threadGroupWidth: Int,
    repetitions: Int
) -> Double {
    let start = DispatchTime.now().uptimeNanoseconds
    let outputs = (0..<repetitions).map { _ in
        runSortedMoETail(inputs, threadGroupWidth: threadGroupWidth)
    }
    eval(outputs)
    return Double(DispatchTime.now().uptimeNanoseconds - start)
        / Double(repetitions)
}

private func mean(_ values: [Double]) -> Double {
    values.reduce(0, +) / Double(values.count)
}

private func jsonArray(_ values: [Double]) -> String {
    "[" + values.map { String(format: "%.3f", $0) }.joined(separator: ",") + "]"
}

@Test
func lagunaSortedMoETailTG512IsolatedTimingWhenEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_SORTED_MOE_TAIL_TIMING"] == "1"
    else {
        return
    }

    let inputs = makeSortedMoETailInputs(rows: 512)
    let repetitions = 32
    let rounds = 24
    eval(runSortedMoETail(inputs, threadGroupWidth: 256))
    eval(runSortedMoETail(inputs, threadGroupWidth: 512))

    var abbaControl: [Double] = []
    var abbaCandidate: [Double] = []
    for _ in 0..<rounds {
        let a1 = measureSortedMoETail(inputs, threadGroupWidth: 256, repetitions: repetitions)
        let b1 = measureSortedMoETail(inputs, threadGroupWidth: 512, repetitions: repetitions)
        let b2 = measureSortedMoETail(inputs, threadGroupWidth: 512, repetitions: repetitions)
        let a2 = measureSortedMoETail(inputs, threadGroupWidth: 256, repetitions: repetitions)
        abbaControl.append((a1 + a2) / 2)
        abbaCandidate.append((b1 + b2) / 2)
    }

    var baabControl: [Double] = []
    var baabCandidate: [Double] = []
    for _ in 0..<rounds {
        let b1 = measureSortedMoETail(inputs, threadGroupWidth: 512, repetitions: repetitions)
        let a1 = measureSortedMoETail(inputs, threadGroupWidth: 256, repetitions: repetitions)
        let a2 = measureSortedMoETail(inputs, threadGroupWidth: 256, repetitions: repetitions)
        let b2 = measureSortedMoETail(inputs, threadGroupWidth: 512, repetitions: repetitions)
        baabControl.append((a1 + a2) / 2)
        baabCandidate.append((b1 + b2) / 2)
    }

    print(
        "sorted_moe_tail_timing={\"unit\":\"ns_per_kernel\",\"rows\":512,"
            + "\"repetitions_per_arm\":\(repetitions),\"rounds\":\(rounds),"
            + "\"abba_control\":\(jsonArray(abbaControl)),"
            + "\"abba_candidate\":\(jsonArray(abbaCandidate)),"
            + "\"baab_control\":\(jsonArray(baabControl)),"
            + "\"baab_candidate\":\(jsonArray(baabCandidate))}"
    )
    print(
        "sorted_moe_tail_speedup abba=\(mean(abbaControl) / mean(abbaCandidate)) "
            + "baab=\(mean(baabControl) / mean(baabCandidate))"
    )
    #expect(abbaControl.allSatisfy { $0 > 0 })
    #expect(abbaCandidate.allSatisfy { $0 > 0 })
    #expect(baabControl.allSatisfy { $0 > 0 })
    #expect(baabCandidate.allSatisfy { $0 > 0 })
}
