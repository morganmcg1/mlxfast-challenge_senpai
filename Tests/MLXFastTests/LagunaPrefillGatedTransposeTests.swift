import Dispatch
import Foundation
import MLX
@testable import MLXFastModel
import Testing

@Suite(.serialized)
struct LagunaPrefillGatedTransposeTests {
    @Test
    func exactBF16BytesMatchStockGraphWhenRuntimeTestsAreEnabled() throws {
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
    func unsupportedShapesAndDTypesUseFallbackWhenRuntimeTestsAreEnabled() {
        guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
            return
        }

        let supportedAttention = MLXArray.zeros([1, 48, 512, 128], dtype: .bfloat16)
        let supportedGate = MLXArray.zeros([1, 512, 48], dtype: .bfloat16)
        #expect(
            lagunaPrefillGatedTranspose(
                attentionOutput: supportedAttention,
                gateValues: supportedGate,
                heads: 48
            ) != nil
        )
        #expect(
            lagunaPrefillGatedTranspose(
                attentionOutput: MLXArray.zeros([1, 32, 512, 128], dtype: .bfloat16),
                gateValues: MLXArray.zeros([1, 512, 32], dtype: .bfloat16),
                heads: 32
            ) == nil
        )
        #expect(
            lagunaPrefillGatedTranspose(
                attentionOutput: MLXArray.zeros([1, 48, 511, 128], dtype: .bfloat16),
                gateValues: MLXArray.zeros([1, 511, 48], dtype: .bfloat16),
                heads: 48
            ) == nil
        )
        #expect(
            lagunaPrefillGatedTranspose(
                attentionOutput: MLXArray.zeros([1, 48, 512, 64], dtype: .bfloat16),
                gateValues: supportedGate,
                heads: 48
            ) == nil
        )
        #expect(
            lagunaPrefillGatedTranspose(
                attentionOutput: MLXArray.zeros([2, 48, 512, 128], dtype: .bfloat16),
                gateValues: MLXArray.zeros([2, 512, 48], dtype: .bfloat16),
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
                attentionOutput: MLXArray.zeros([1, 48, 1, 128], dtype: .bfloat16),
                gateValues: MLXArray.zeros([1, 1, 48], dtype: .bfloat16),
                heads: 48
            ) == nil
        )
    }

    @Test
    func pairedMaterializerTimingWhenBenchmarkIsEnabled() throws {
        guard ProcessInfo.processInfo.environment[
            "MLXFAST_RUN_PREFILL_GATED_TRANSPOSE_BENCHMARK"
        ] == "1" else {
            return
        }

        for heads in [48, 64] {
            let inputs = makeInputs(heads: heads)
            eval(inputs.attention, inputs.gate)

            let stock = {
                stockGraph(attention: inputs.attention, gate: inputs.gate, heads: heads)
            }
            let fused = {
                try #require(
                    lagunaPrefillGatedTranspose(
                        attentionOutput: inputs.attention,
                        gateValues: inputs.gate,
                        heads: heads
                    )
                )
            }

            for _ in 0..<8 {
                eval(stock(), try fused())
            }

            for stockFirst in [true, false] {
                var stockSamples: [Double] = []
                var fusedSamples: [Double] = []
                for _ in 0..<51 {
                    if stockFirst {
                        stockSamples.append(measure(stock))
                        fusedSamples.append(try measure(fused))
                    } else {
                        fusedSamples.append(try measure(fused))
                        stockSamples.append(measure(stock))
                    }
                }

                let stockMedian = median(stockSamples)
                let fusedMedian = median(fusedSamples)
                let order = stockFirst ? "stock-first" : "fused-first"
                print(
                    "materializer H\(heads) order=\(order) "
                        + "stock_ms=\(stockMedian) fused_ms=\(fusedMedian) "
                        + "speedup=\(stockMedian / fusedMedian)"
                )
            }
        }
    }

    private func makeInputs(heads: Int) -> (attention: MLXArray, gate: MLXArray) {
        var attentionWords = finiteBF16Words(count: heads * 512 * 128, seed: UInt32(heads))
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
            attentionWords[token * 128] = pair.0
            gateWords[token * heads] = pair.1
        }

        return (
            MLXArray(data(attentionWords), [1, heads, 512, 128], dtype: .bfloat16),
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

    private func measure(_ makeOutput: () throws -> MLXArray) rethrows -> Double {
        let start = DispatchTime.now().uptimeNanoseconds
        eval(try makeOutput())
        let end = DispatchTime.now().uptimeNanoseconds
        return Double(end - start) / 1_000_000
    }

    private func median(_ samples: [Double]) -> Double {
        samples.sorted()[samples.count / 2]
    }
}
