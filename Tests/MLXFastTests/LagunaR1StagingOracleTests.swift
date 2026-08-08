import Foundation
import MLX
@testable import MLXFastModel
import Testing

@Test
func routedR1StagedActivationMatchesStockBitsWhenRuntimeTestsAreEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
        return
    }

    let expertPatterns: [UInt32] = [
        0x7654_3210, 0xfedc_ba98, 0x1357_9bdf, 0xeca8_6420,
    ]
    var weightValues: [UInt32] = []
    weightValues.reserveCapacity(4 * 1_024 * 256)
    for pattern in expertPatterns {
        weightValues.append(contentsOf: repeatElement(pattern, count: 1_024 * 256))
    }
    let fusedWeight = MLXArray(weightValues, [4, 1_024, 256])
    let packedScales = MLXArray(
        Array(repeating: UInt8(0x38), count: 4 * 128 * 4 * 8 * 32),
        [4, 128, 4, 8, 32]
    )

    var state = UInt32(0x243f_6a88)
    var randomFiniteBits: [UInt16] = []
    randomFiniteBits.reserveCapacity(2_048)
    for _ in 0..<2_048 {
        state = 1_664_525 &* state &+ 1_013_904_223
        var bits = UInt16(truncatingIfNeeded: state >> 16)
        if bits & 0x7f80 == 0x7f80 {
            bits ^= 0x0080
        }
        randomFiniteBits.append(bits)
    }
    let specialBits: [UInt16] = [
        0x0000, 0x8000, 0x0001, 0x8001,
        0x007f, 0x807f, 0x0080, 0x8080,
        0x7f7f, 0xff7f, 0x7f80, 0xff80,
        0x7fc1, 0xffc1, 0x7f81, 0xff81,
    ]
    let inputCases = [
        ("random-finite", randomFiniteBits),
        ("special-values", Array(repeating: specialBits, count: 128).flatMap { $0 }),
    ]
    let permutations: [[UInt32]] = [
        [0, 1, 2, 3, 0, 1, 2, 3],
        [3, 2, 1, 0, 3, 2, 1, 0],
        [1, 2, 3, 0, 1, 2, 3, 0],
        [3, 0, 2, 1, 3, 1, 0, 2],
    ]

    for (inputLabel, inputBits) in inputCases {
        let input = MLXArray(inputBits, [1, 1, 2_048]).view(dtype: .bfloat16)
        for (permutationIndex, permutation) in permutations.enumerated() {
            let indices = MLXArray(permutation, [1, 1, 8])
            let stock = lagunaRoutedSwiGLUQMVPackedTop8StockOracle(
                input,
                fusedWeight: fusedWeight,
                packedScales: packedScales,
                indices: indices
            )
            let staged = lagunaRoutedSwiGLUQMVPackedTop8(
                input,
                fusedWeight: fusedWeight,
                packedScales: packedScales,
                indices: indices
            )
            eval(stock, staged)

            let stockBits = stock.view(dtype: .uint16).asArray(UInt16.self)
            let stagedBits = staged.view(dtype: .uint16).asArray(UInt16.self)
            if stockBits != stagedBits,
               let mismatch = stockBits.indices.first(where: { stockBits[$0] != stagedBits[$0] }) {
                print(
                    "R1 oracle mismatch input=\(inputLabel) permutation=\(permutationIndex) "
                        + "index=\(mismatch) stock=\(stockBits[mismatch]) staged=\(stagedBits[mismatch])"
                )
            }
            #expect(stockBits == stagedBits)
        }
    }
}
