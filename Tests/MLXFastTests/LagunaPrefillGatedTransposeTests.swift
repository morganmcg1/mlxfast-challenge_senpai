import Foundation
import MLX
@testable import MLXFastModel
import Testing

@Suite(.serialized)
struct LagunaPrefillGatedTransposeTests {
    @Test
    func exactBF16BytesMatchStockGraphForLiveSDPAStrides() throws {
        guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
            return
        }

        for heads in [48, 64] {
            let inputs = makeInputs(heads: heads)
            let fused = try #require(
                lagunaPrefillGatedTranspose(
                    attentionOutput: inputs.attention,
                    gateValues: inputs.gate,
                    heads: heads
                )
            )
            let reference = stockGraph(
                attention: inputs.attention,
                gate: inputs.gate,
                heads: heads
            )
            eval(fused, reference)

            #expect(fused.shape == [1, 512, heads * 128])
            #expect(fused.dtype == .bfloat16)
            #expect(
                fused.asData(access: .copy).data == reference.asData(access: .copy).data,
                "raw BF16 output differed for H=\(heads)"
            )
        }
    }

    @Test
    func unsupportedShapesAndDTypesUseFallback() {
        guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
            return
        }

        let supported = makeInputs(heads: 48)
        #expect(
            lagunaPrefillGatedTranspose(
                attentionOutput: supported.attention,
                gateValues: supported.gate,
                heads: 48
            ) != nil
        )
        #expect(
            lagunaPrefillGatedTranspose(
                attentionOutput: MLXArray.zeros([1, 48, 1, 128], dtype: .bfloat16),
                gateValues: MLXArray.zeros([1, 1, 48], dtype: .bfloat16),
                heads: 48
            ) == nil
        )
        #expect(
            lagunaPrefillGatedTranspose(
                attentionOutput: MLXArray.zeros([1, 48, 512, 128], dtype: .float32),
                gateValues: MLXArray.zeros([1, 512, 48], dtype: .float32),
                heads: 48
            ) == nil
        )
        #expect(
            lagunaPrefillGatedTranspose(
                attentionOutput: MLXArray.zeros([1, 32, 512, 128], dtype: .bfloat16),
                gateValues: MLXArray.zeros([1, 512, 32], dtype: .bfloat16),
                heads: 32
            ) == nil
        )
    }

    private func makeInputs(heads: Int) -> (attention: MLXArray, gate: MLXArray) {
        var attentionWords = finiteBF16Words(count: 512 * heads * 128, seed: UInt32(heads))
        var gateWords = finiteBF16Words(count: 512 * heads, seed: UInt32(heads * 17))
        let specialPairs: [(UInt16, UInt16)] = [
            (0x0000, 0x3f80),
            (0x8000, 0x3f80),
            (0x0001, 0x3f80),
            (0x8001, 0x3f80),
            (0x7f7f, 0x0080),
            (0xff7f, 0x0080),
        ]
        for (token, pair) in specialPairs.enumerated() {
            attentionWords[token * heads * 128] = pair.0
            gateWords[token * heads] = pair.1
        }

        let physicalSDPAOutput = MLXArray(
            data(attentionWords), [1, 512, heads, 128], dtype: .bfloat16)
        return (
            physicalSDPAOutput.transposed(0, 2, 1, 3),
            MLXArray(data(gateWords), [1, 512, heads], dtype: .bfloat16)
        )
    }

    private func finiteBF16Words(count: Int, seed: UInt32) -> [UInt16] {
        var state = seed
        return (0..<count).map { _ in
            state = state &* 1_664_525 &+ 1_013_904_223
            let sign = UInt16(truncatingIfNeeded: state >> 16) & 0x8000
            let exponent = UInt16(96 + (state >> 24) % 63) << 7
            let fraction = UInt16(truncatingIfNeeded: state) & 0x007f
            return sign | exponent | fraction
        }
    }

    private func data(_ words: [UInt16]) -> Data {
        words.withUnsafeBufferPointer { Data(buffer: $0) }
    }

    private func stockGraph(attention: MLXArray, gate: MLXArray, heads: Int) -> MLXArray {
        let transposed = attention
            .transposed(0, 2, 1, 3)
            .reshaped(1, 512, heads, 128)
        return (transposed * gate[.ellipsis, .newAxis])
            .reshaped(1, 512, heads * 128)
    }
}
