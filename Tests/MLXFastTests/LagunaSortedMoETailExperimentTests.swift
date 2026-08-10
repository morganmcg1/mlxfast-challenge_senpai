import Dispatch
import Foundation
import MLX
@testable import MLXFastModel
import Testing

private let sortedTailControlKernel = MLXFast.metalKernel(
    name: "laguna_prefill_sorted_moe_tail_bf16_control_test",
    inputNames: [
        "sorted_expert_outputs", "inverse_order", "router_weights",
        "shared_output", "residual",
    ],
    outputNames: ["output"],
    source: """
constexpr uint hidden = 2048;
constexpr uint experts = 8;
constexpr uint n_cols = 4;

uint row = thread_position_in_grid.y;
uint col = thread_position_in_grid.x * n_cols;
const device float* weight_row = router_weights + row * experts;

bfloat expert_weights[experts];
uint sorted_rows[experts];
for (uint e = 0; e < experts; ++e) {
    expert_weights[e] = bfloat(weight_row[e]);
    sorted_rows[e] = inverse_order[row * experts + e];
}

for (uint i = 0; i < n_cols; ++i) {
    bfloat total = bfloat(0);
    for (uint e = 0; e < experts; ++e) {
        bfloat product = bfloat(
            sorted_expert_outputs[sorted_rows[e] * hidden + col + i] *
            expert_weights[e]);
        total = bfloat(product + total);
    }
    bfloat scaled = bfloat(total * bfloat(2.5f));
    bfloat r2 = bfloat(scaled + shared_output[row * hidden + col + i]);
    output[row * hidden + col + i] =
        bfloat(residual[row * hidden + col + i] + r2);
}
""",
    ensureRowContiguous: true
)

private struct SortedTailFixture {
    let rows: Int
    let sortedExpertOutputs: MLXArray
    let inverseOrder: MLXArray
    let routerWeights: MLXArray
    let sharedOutput: MLXArray
    let residual: MLXArray
    let rmsWeight: MLXArray
}

@Suite(.serialized)
struct LagunaSortedMoETailExperimentTests {
    @Test
    func exactRawBF16DifferentialAndFollowingLayerHandoff() {
        let rowCases = [2, 3, 4, 5, 511, 512, 513]
        for rows in rowCases {
            autoreleasepool {
                let fixture = makeSortedTailFixture(rows: rows)
                let control = controlTail(fixture)
                let candidate = candidateTail(fixture)
                let controlHandoff = MLXFast.rmsNorm(
                    control,
                    weight: fixture.rmsWeight,
                    eps: 1e-5
                )
                let candidateHandoff = MLXFast.rmsNorm(
                    candidate,
                    weight: fixture.rmsWeight,
                    eps: 1e-5
                )
                eval(control, candidate, controlHandoff, candidateHandoff)

                let controlBits = rawBF16Bits(control)
                let candidateBits = rawBF16Bits(candidate)
                let tailMismatch = firstMismatch(controlBits, candidateBits)
                #expect(tailMismatch == nil, "rows=\(rows), tail mismatch=\(String(describing: tailMismatch))")

                let controlHandoffBits = rawBF16Bits(controlHandoff)
                let candidateHandoffBits = rawBF16Bits(candidateHandoff)
                let handoffMismatch = firstMismatch(controlHandoffBits, candidateHandoffBits)
                #expect(
                    handoffMismatch == nil,
                    "rows=\(rows), handoff mismatch=\(String(describing: handoffMismatch))"
                )

                var corrupted = candidateBits
                let corruptionIndex = (rows * 2_047 + 255) % corrupted.count
                corrupted[corruptionIndex] ^= 1
                #expect(firstMismatch(controlBits, corrupted) == corruptionIndex)
                print("SORTED_TAIL_EXACT rows=\(rows) values=\(controlBits.count) corruption_index=\(corruptionIndex) status=pass")
            }
        }
    }

    @Test
    func mirroredABBAAndBAABMicrobenchmark() {
        guard ProcessInfo.processInfo.environment["MLXFAST_RUN_SORTED_TAIL_EXPERIMENT"] == "1" else {
            return
        }

        let fixture = makeSortedTailFixture(rows: 512)
        eval(
            fixture.sortedExpertOutputs,
            fixture.inverseOrder,
            fixture.routerWeights,
            fixture.sharedOutput,
            fixture.residual
        )

        let warmup = (0..<32).flatMap { _ in
            [controlTail(fixture), candidateTail(fixture)]
        }
        eval(warmup)

        for round in 0..<24 {
            measureSequence(
                order: "ABBA",
                round: round,
                variants: ["control", "candidate", "candidate", "control"],
                fixture: fixture
            )
        }
        for round in 0..<24 {
            measureSequence(
                order: "BAAB",
                round: round,
                variants: ["candidate", "control", "control", "candidate"],
                fixture: fixture
            )
        }
    }
}

private func makeSortedTailFixture(rows: Int) -> SortedTailFixture {
    let hidden = 2_048
    let experts = 8
    let expertPattern = [0, 255, 17, 17, 64, 3, 255, 1]
    let bf16Palette: [UInt16] = [
        0x0000, 0x8000, 0x0001, 0x8001, 0x0080, 0x8080,
        0x3c00, 0xbc00, 0x3d00, 0xbd00, 0x3e80, 0xbe80,
        0x3f00, 0xbf00, 0x3f80, 0xbf80, 0x4000, 0xc000,
        0x4040, 0xc040,
    ]
    let routerPalette: [Float] = [
        Float(bitPattern: 0x0000_0000),
        Float(bitPattern: 0x8000_0000),
        0.5, 0.5, -0.5, 1, -1, 0.25,
    ]

    var sortedBits = Array(repeating: UInt16(0), count: rows * experts * hidden)
    var inverseOrder = Array(repeating: UInt32(0), count: rows * experts)
    var routerWeights = Array(repeating: Float(0), count: rows * experts)
    var sharedBits = Array(repeating: UInt16(0), count: rows * hidden)
    var residualBits = Array(repeating: UInt16(0), count: rows * hidden)

    for row in 0..<rows {
        let expertIDs = (0..<experts).map { expertPattern[($0 + row) % experts] }
        let sortedSlots = (0..<experts).sorted {
            expertIDs[$0] == expertIDs[$1] ? $0 < $1 : expertIDs[$0] < expertIDs[$1]
        }
        for (sortedRank, slot) in sortedSlots.enumerated() {
            inverseOrder[row * experts + slot] = UInt32(row * experts + sortedRank)
            let sortedBase = (row * experts + sortedRank) * hidden
            for col in 0..<hidden {
                let paletteIndex =
                    (row * 31 + slot * 7 + expertIDs[slot] + col * 13 + col / 32)
                    % bf16Palette.count
                sortedBits[sortedBase + col] = bf16Palette[paletteIndex]
            }
        }
        for slot in 0..<experts {
            routerWeights[row * experts + slot] = routerPalette[(row + slot) % routerPalette.count]
        }
        let rowBase = row * hidden
        for col in 0..<hidden {
            sharedBits[rowBase + col] = bf16Palette[(row * 11 + col * 3 + 5) % bf16Palette.count]
            residualBits[rowBase + col] = bf16Palette[(row * 17 + col * 5 + 9) % bf16Palette.count]
        }
    }

    let rmsBits = (0..<hidden).map { index -> UInt16 in
        switch index % 4 {
        case 0: 0x3f80
        case 1: 0x3f00
        case 2: 0x3fc0
        default: 0xbf80
        }
    }

    return SortedTailFixture(
        rows: rows,
        sortedExpertOutputs: bf16Array(sortedBits, shape: [rows * experts, hidden]),
        inverseOrder: MLXArray(inverseOrder, [rows * experts]),
        routerWeights: MLXArray(routerWeights, [1, rows, experts]),
        sharedOutput: bf16Array(sharedBits, shape: [1, rows, hidden]),
        residual: bf16Array(residualBits, shape: [1, rows, hidden]),
        rmsWeight: bf16Array(rmsBits, shape: [hidden])
    )
}

private func bf16Array(_ bits: [UInt16], shape: [Int]) -> MLXArray {
    MLXArray(bits, shape).view(dtype: .bfloat16)
}

private func controlTail(_ fixture: SortedTailFixture) -> MLXArray {
    sortedTailControlKernel(
        [
            fixture.sortedExpertOutputs,
            fixture.inverseOrder,
            fixture.routerWeights,
            fixture.sharedOutput,
            fixture.residual,
        ],
        grid: (2_048 / 4, fixture.rows, 1),
        threadGroup: (256, 1, 1),
        outputShapes: [[1, fixture.rows, 2_048]],
        outputDTypes: [.bfloat16]
    )[0]
}

private func candidateTail(_ fixture: SortedTailFixture) -> MLXArray {
    lagunaPrefillSortedMoETail(
        sortedExpertOutputs: fixture.sortedExpertOutputs,
        inverseOrder: fixture.inverseOrder,
        routerWeights: fixture.routerWeights,
        sharedOutput: fixture.sharedOutput,
        residual: fixture.residual
    )
}

private func rawBF16Bits(_ array: MLXArray) -> [UInt16] {
    array.view(dtype: .uint16).asArray(UInt16.self)
}

private func firstMismatch(_ lhs: [UInt16], _ rhs: [UInt16]) -> Int? {
    guard lhs.count == rhs.count else { return min(lhs.count, rhs.count) }
    return lhs.indices.first { lhs[$0] != rhs[$0] }
}

private func measureSequence(
    order: String,
    round: Int,
    variants: [String],
    fixture: SortedTailFixture
) {
    let repetitions = 32
    for (position, variant) in variants.enumerated() {
        let outputs = (0..<repetitions).map { _ in
            variant == "candidate" ? candidateTail(fixture) : controlTail(fixture)
        }
        let start = DispatchTime.now().uptimeNanoseconds
        eval(outputs)
        let elapsed = DispatchTime.now().uptimeNanoseconds - start
        let perCall = Double(elapsed) / Double(repetitions)
        print(
            "TAIL_SAMPLE {\"order\":\"\(order)\",\"round\":\(round),\"position\":\(position),\"variant\":\"\(variant)\",\"repetitions\":\(repetitions),\"total_ns\":\(elapsed),\"ns_per_call\":\(perCall)}"
        )
    }
}
