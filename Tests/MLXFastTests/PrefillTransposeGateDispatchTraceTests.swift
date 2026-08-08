import Foundation
import MLX
@testable import MLXFastModel
import Testing

private func stockPrefillTransposeGate(
    _ attended: MLXArray, gate: MLXArray, heads: Int
) -> MLXArray {
    let flattened = attended.transposed(0, 2, 1, 3).reshaped(1, 512, heads * 128)
    return (
        flattened.reshaped(1, 512, heads, 128) * gate[.ellipsis, .newAxis]
    ).reshaped(1, 512, heads * 128)
}

private func expectPrefillTransposeGateBitwiseMatch(
    _ attended: MLXArray, gate: MLXArray, heads: Int
) {
    let expected = stockPrefillTransposeGate(attended, gate: gate, heads: heads)
    let candidate = lagunaPrefillTransposeGateMaterialized(
        attentionOutput: attended, gateValues: gate, heads: heads)
    #expect(candidate != nil)
    guard let candidate else { return }

    eval(candidate, expected)
    let candidateBits = candidate.view(dtype: .uint16).asArray(UInt16.self)
    let expectedBits = expected.view(dtype: .uint16).asArray(UInt16.self)
    #expect(candidateBits == expectedBits)
}

@Test
func prefillTransposeGateMaterializerMatchesStockWhenRuntimeTestsAreEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
        return
    }

    for heads in [48, 64] {
        MLXRandom.seed(UInt64(4280 + heads))
        let attended = MLXRandom.uniform(
            low: -4, high: 4, [1, heads, 512, 128]
        ).asType(.bfloat16)
        let gate = MLXRandom.uniform(
            low: 0, high: 8, [1, 512, heads]
        ).asType(.bfloat16)
        expectPrefillTransposeGateBitwiseMatch(attended, gate: gate, heads: heads)

        let attendedSeed = MLXArray(
            [
                UInt16(0x0000), 0x8000, 0x0001, 0x8001,
                0x0080, 0x8080, 0x3e80, 0xbe80,
                0x3f00, 0xbf00, 0x3f80, 0xbf80,
                0x4000, 0xc000, 0x7f7f, 0xff7f,
            ]
        ).view(dtype: .bfloat16).reshaped(1, 1, 1, 16)
        let gateSeed = MLXArray(
            [
                UInt16(0x0000), 0x0001, 0x0080, 0x3d80,
                0x3e00, 0x3e80, 0x3f00, 0x3f40,
                0x3f80, 0x4000, 0x4040, 0x4080,
                0x4100, 0x4180, 0x7f7f, 0x7f80,
            ]
        ).view(dtype: .bfloat16).reshaped(1, 1, 16)
        let specialAttended = tiled(
            attendedSeed, repetitions: [1, heads, 512, 8])
        let specialGate = tiled(
            gateSeed, repetitions: [1, 512, heads / 16])
        expectPrefillTransposeGateBitwiseMatch(
            specialAttended, gate: specialGate, heads: heads)
    }
}

@Test
func prefillTransposeGateMaterializerDeclinesUnguardedShapes() {
    for heads in [48, 64] {
        for length in [1, 2, 511, 513] {
            let attended = MLXArray.zeros([1, heads, length, 128], dtype: .bfloat16)
            let gate = MLXArray.zeros([1, length, heads], dtype: .bfloat16)
            #expect(
                lagunaPrefillTransposeGateMaterialized(
                    attentionOutput: attended, gateValues: gate, heads: heads) == nil)
        }
    }

    let attended = MLXArray.zeros([1, 32, 512, 128], dtype: .bfloat16)
    let gate = MLXArray.zeros([1, 512, 32], dtype: .bfloat16)
    #expect(
        lagunaPrefillTransposeGateMaterialized(
            attentionOutput: attended, gateValues: gate, heads: 32) == nil)
}
