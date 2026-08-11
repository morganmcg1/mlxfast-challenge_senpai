import Foundation
import MLX
@testable import MLXFastModel
import Testing

private let row32Vocab = 100_352
private let row32Hidden = 2_048

private func row32Coarse(_ values: [Int: Float] = [:]) -> MLXArray {
    var coarse = [Float](repeating: 0, count: row32Vocab)
    for (row, value) in values {
        coarse[row] = value
    }
    return MLXArray(coarse, [row32Vocab])
}

private func row32Delta() -> MLXArray {
    MLXArray([UInt16](repeating: 0, count: row32Vocab), [row32Vocab])
        .view(dtype: .bfloat16)
}

private func row32Bits(_ array: MLXArray) -> [UInt16] {
    array.view(dtype: .uint16).asArray(UInt16.self)
}

private func row32Compare(
    name: String,
    coarse: MLXArray,
    delta: MLXArray,
    threshold: Float,
    weight: MLXArray,
    hidden: MLXArray,
    refinement: (codesBit: MLXArray, scales: MLXArray)? = nil
) -> [UInt16] {
    let thresholdArray = MLXArray([threshold])
    let accepted = lagunaLmHeadAssembleForTesting(
        coarse: coarse,
        delta: delta,
        threshold: thresholdArray,
        lmHeadWeight: weight,
        hidden: hidden,
        useRow32: false,
        refinement: refinement
    )
    let row32 = lagunaLmHeadAssembleForTesting(
        coarse: coarse,
        delta: delta,
        threshold: thresholdArray,
        lmHeadWeight: weight,
        hidden: hidden,
        useRow32: true,
        refinement: refinement
    )
    eval(accepted, row32)
    let acceptedBits = row32Bits(accepted)
    let row32OutputBits = row32Bits(row32)
    #expect(acceptedBits == row32OutputBits)
    print("ROW32_FIXTURE \(name) PASS rows=\(row32OutputBits.count)")
    return row32OutputBits
}

@Suite(.serialized)
struct LagunaLmHeadRow32CompositionTests {
    @Test
    func exactTailMatchesAcceptedKernel() {
        guard
            ProcessInfo.processInfo.environment["MLXFAST_RUN_LMHEAD_ROW32_FIXTURES"] == "1"
        else {
            return
        }

        let weight = MLXRandom.normal(
            [row32Vocab, row32Hidden],
            dtype: .bfloat16,
            key: MLXRandom.key(721)
        )
        let randomHidden = MLXRandom.normal(
            [row32Hidden],
            dtype: .bfloat16,
            key: MLXRandom.key(722)
        )
        let delta = row32Delta()
        eval(weight, randomHidden, delta)

        let denseBits = row32Compare(
            name: "dense",
            coarse: row32Coarse(),
            delta: delta,
            threshold: -1,
            weight: weight,
            hidden: randomHidden
        )

        let zeroBits = row32Compare(
            name: "zero-candidate",
            coarse: row32Coarse(),
            delta: delta,
            threshold: 1,
            weight: weight,
            hidden: randomHidden
        )
        #expect(zeroBits.allSatisfy { $0 == 0 })

        let boundaryRows = [0, 3, 4, 31, 32, 255, 256, 100_348, 100_351]
        let sparseBits = row32Compare(
            name: "sparse-boundaries",
            coarse: row32Coarse(Dictionary(uniqueKeysWithValues: boundaryRows.map { ($0, 2) })),
            delta: delta,
            threshold: 1,
            weight: weight,
            hidden: randomHidden
        )
        let boundarySet = Set(boundaryRows)
        for row in 0 ..< row32Vocab {
            #expect(sparseBits[row] == (boundarySet.contains(row) ? denseBits[row] : 0))
        }

        let oneHidden = MLXArray(
            [UInt16](repeating: 0x3F80, count: row32Hidden),
            [row32Hidden]
        ).view(dtype: .bfloat16)
        let codesBit = MLXArray(
            [UInt8](repeating: 0, count: row32Vocab * row32Hidden / 8),
            [row32Vocab, row32Hidden / 8]
        )
        let scales = MLXArray(
            [UInt8](repeating: 127, count: row32Vocab * row32Hidden / 32),
            [row32Vocab, row32Hidden / 32]
        )
        eval(oneHidden, codesBit, scales)

        let exactReference = row32Compare(
            name: "refined-exact-reference",
            coarse: row32Coarse([32: 2]),
            delta: delta,
            threshold: 1,
            weight: weight,
            hidden: oneHidden
        )
        let refinedBits = row32Compare(
            name: "refined-survivor-reject",
            coarse: row32Coarse([31: 1_100, 32: 3_000]),
            delta: delta,
            threshold: 1_000,
            weight: weight,
            hidden: oneHidden,
            refinement: (codesBit, scales)
        )
        for row in 0 ..< row32Vocab {
            let expected: UInt16
            switch row {
            case 31:
                expected = 0x4298
            case 32:
                expected = exactReference[row]
            default:
                expected = 0
            }
            #expect(refinedBits[row] == expected)
        }
    }
}
