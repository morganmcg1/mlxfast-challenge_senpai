import Foundation
import MLX
@testable import MLXFastModel
import Testing

private let prefillGatedTransposeRuntimeTestsEnabled =
    ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1"
private let prefillGatedTransposeBenchmarkEnabled =
    ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_BENCHMARKS"] == "1"

private enum GatedTransposeArm: String {
    case stock
    case candidate
}

@Suite(.serialized)
struct LagunaPrefillGatedTransposeTests {
    @Test
    func liveStrideKernelMatchesStockBF16BitsForBothHeadCounts() throws {
        guard prefillGatedTransposeRuntimeTestsEnabled else { return }

        try checkExactBits(heads: 48, seed: 0x18c0_ffee)
        try checkExactBits(heads: 64, seed: 0x20c0_ffee)
    }

    @Test
    func unsupportedModesShapesAndDTypesReturnFallback() {
        let attended = zeros([1, 48, 512, 128], dtype: .bfloat16)
        let gate = zeros([1, 512, 48], dtype: .bfloat16)

        #expect(lagunaPrefillGatedTranspose(attended: attended, gate: gate, enabled: false) == nil)
        #expect(
            lagunaPrefillGatedTranspose(
                attended: attended, gate: gate, gateIsActivated: false) == nil)
        #expect(
            lagunaPrefillGatedTranspose(
                attended: attended, gate: gate, gatePerHead: false) == nil)
        #expect(
            lagunaPrefillGatedTranspose(
                attended: zeros([1, 32, 512, 128], dtype: .bfloat16),
                gate: zeros([1, 512, 32], dtype: .bfloat16)) == nil)
        #expect(
            lagunaPrefillGatedTranspose(
                attended: zeros([1, 48, 1, 128], dtype: .bfloat16),
                gate: zeros([1, 1, 48], dtype: .bfloat16)) == nil)
        #expect(
            lagunaPrefillGatedTranspose(
                attended: zeros([1, 48, 512, 64], dtype: .bfloat16),
                gate: gate) == nil)
        #expect(
            lagunaPrefillGatedTranspose(
                attended: zeros([1, 48, 512, 128], dtype: .float32),
                gate: gate) == nil)
        #expect(
            lagunaPrefillGatedTranspose(
                attended: attended,
                gate: zeros([1, 512, 48], dtype: .float32)) == nil)
        #expect(
            lagunaPrefillGatedTranspose(
                attended: attended,
                gate: zeros([1, 511, 48], dtype: .bfloat16)) == nil)
    }

    @Test
    func isolatedLiveStrideTimingWinsInBothOrders() {
        guard prefillGatedTransposeBenchmarkEnabled else { return }

        let orders: [[GatedTransposeArm]] = [
            [.stock, .candidate],
            [.candidate, .stock],
        ]
        for heads in [48, 64] {
            for (orderIndex, order) in orders.enumerated() {
                let seed = UInt32(heads * 1_000 + orderIndex)
                let (attended, gate) = makeTimingInputs(heads: heads, seed: seed)
                var medians: [GatedTransposeArm: Double] = [:]
                for arm in order {
                    medians[arm] = measureTimingArm(
                        arm, attended: attended, gate: gate, heads: heads)
                }

                let stockMilliseconds = medians[.stock]!
                let candidateMilliseconds = medians[.candidate]!
                let ratio = stockMilliseconds / candidateMilliseconds
                let stockText = String(format: "%.6f", stockMilliseconds)
                let candidateText = String(format: "%.6f", candidateMilliseconds)
                let ratioText = String(format: "%.6f", ratio)
                print(
                    "isolated_gated_transpose heads=\(heads) "
                        + "order=\(order[0].rawValue),\(order[1].rawValue) "
                        + "stock_ms=\(stockText) candidate_ms=\(candidateText) "
                        + "ratio=\(ratioText)")
                #expect(ratio >= 1.002)
            }
        }
    }

    private func makeTimingInputs(heads: Int, seed: UInt32) -> (MLXArray, MLXArray) {
        let headDim = 128
        let attended = MLXArray(
            randomFiniteBF16Bits(
                count: 512 * heads * headDim,
                seed: seed),
            [1, 512, heads, headDim]
        )
        .view(dtype: .bfloat16)
        .transposed(0, 2, 1, 3)
        let gate = MLXArray(
            randomFiniteBF16Bits(
                count: 512 * heads,
                seed: seed ^ 0xa5a5_a5a5),
            [1, 512, heads]
        )
        .view(dtype: .bfloat16)
        eval(attended, gate)
        Stream.gpu.synchronize()
        return (attended, gate)
    }

    private func measureTimingArm(
        _ arm: GatedTransposeArm,
        attended: MLXArray,
        gate: MLXArray,
        heads: Int
    ) -> Double {
        for _ in 0..<6 {
            eval(makeTimingOutput(arm, attended: attended, gate: gate, heads: heads))
        }
        Stream.gpu.synchronize()

        let iterations = 12
        var samples = [Double]()
        samples.reserveCapacity(11)
        for _ in 0..<11 {
            Stream.gpu.synchronize()
            let start = ProcessInfo.processInfo.systemUptime
            for _ in 0..<iterations {
                eval(makeTimingOutput(arm, attended: attended, gate: gate, heads: heads))
            }
            Stream.gpu.synchronize()
            let elapsed = ProcessInfo.processInfo.systemUptime - start
            samples.append(elapsed * 1_000 / Double(iterations))
        }
        samples.sort()
        return samples[samples.count / 2]
    }

    private func makeTimingOutput(
        _ arm: GatedTransposeArm,
        attended: MLXArray,
        gate: MLXArray,
        heads: Int
    ) -> MLXArray {
        switch arm {
        case .stock:
            return (attended.transposed(0, 2, 1, 3) * gate[.ellipsis, .newAxis])
                .reshaped(1, 512, heads * 128)
        case .candidate:
            guard let output = lagunaPrefillGatedTranspose(attended: attended, gate: gate) else {
                preconditionFailure("valid timing shape unexpectedly declined")
            }
            return output
        }
    }

    private func checkExactBits(heads: Int, seed: UInt32) throws {
        let headDim = 128
        var attendedBits = randomFiniteBF16Bits(
            count: 512 * heads * headDim,
            seed: seed
        )
        var gateBits = randomFiniteBF16Bits(count: 512 * heads, seed: seed ^ 0xa5a5_a5a5)
        let edges: [UInt16] = [
            0x0000, 0x8000, 0x0001, 0x8001,
            0x7f7f, 0xff7f, 0x3f80, 0xbf80,
        ]
        for (d, bits) in edges.enumerated() {
            attendedBits[d] = bits
        }
        gateBits[0] = 0x3f80
        for (index, bits) in edges.enumerated() {
            let gateIndex = index + 1
            gateBits[gateIndex] = bits
            attendedBits[gateIndex * headDim] = 0x3f80
        }

        let attended = MLXArray(attendedBits, [1, 512, heads, headDim])
            .view(dtype: .bfloat16)
            .transposed(0, 2, 1, 3)
        let gate = MLXArray(gateBits, [1, 512, heads]).view(dtype: .bfloat16)
        let actual = try #require(
            lagunaPrefillGatedTranspose(attended: attended, gate: gate))
        let reference =
            (attended.transposed(0, 2, 1, 3) * gate[.ellipsis, .newAxis])
            .reshaped(1, 512, heads * headDim)

        eval(actual, reference)
        #expect(actual.shape == [1, 512, heads * headDim])
        let actualBits = actual.view(dtype: .uint16).asArray(UInt16.self)
        let referenceBits = reference.view(dtype: .uint16).asArray(UInt16.self)
        #expect(actualBits.count == referenceBits.count)
        #expect(actualBits.elementsEqual(referenceBits))
    }

    private func randomFiniteBF16Bits(count: Int, seed: UInt32) -> [UInt16] {
        var state = seed
        var values = Array(repeating: UInt16(0), count: count)
        for index in values.indices {
            state = state &* 1_664_525 &+ 1_013_904_223
            var bits = UInt16(truncatingIfNeeded: state)
            if bits & 0x7f80 == 0x7f80 {
                bits &= 0x807f
            }
            values[index] = bits
        }
        return values
    }
}
