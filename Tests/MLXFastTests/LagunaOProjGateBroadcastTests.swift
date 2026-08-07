import Foundation
import MLX
@testable import MLXFastModel
import Testing

private let oprojGateBroadcastOracleEnvironment =
    "MLXFAST_RUN_OPROJ_GATE_BROADCAST_ORACLE"
private let oprojGateBroadcastTimingEnvironment =
    "MLXFAST_RUN_OPROJ_GATE_BROADCAST_TIMING"
private let oprojOutputSize = 2_048
private let oprojTimingBatchSize = 64
private let oprojTimingCycles = 10

@Test
func oprojActivatedGateSIMDBroadcastSourceCoversH48AndH64() {
    for heads in [48, 64] {
        let control = lagunaGatedAffineOProjNVFP4Source(
            heads: heads,
            preActivatedGate: true,
            simdGateBroadcast: false
        )
        let candidate = lagunaGatedAffineOProjNVFP4Source(
            heads: heads,
            preActivatedGate: true,
            simdGateBroadcast: true
        )
        #expect(control.contains("float g=float(gate_values[column>>head_shift]);"))
        #expect(!control.contains("g=simd_shuffle(g,ushort(simd_lid&~7u));"))
        #expect(candidate.contains("if((simd_lid&7u)==0u)"))
        #expect(candidate.contains("g=simd_shuffle(g,ushort(simd_lid&~7u));"))

        let inputSize = heads * 128
        for blockBase in stride(from: 0, to: inputSize, by: 512) {
            for lane in 0..<32 {
                let gate = (blockBase + lane * 16) >> 7
                #expect(gate == blockBase / 128 + lane / 8)
                #expect(gate < heads)
            }
        }
    }
}

@Test
func oprojActivatedGateSIMDBroadcastBitwiseOracle() {
    guard ProcessInfo.processInfo.environment[oprojGateBroadcastOracleEnvironment] == "1" else {
        return
    }

    for heads in [48, 64] {
        let fixture = makeOProjFixture(heads: heads)
        let control = makeOProjKernel(heads: heads, broadcast: false)
        let candidate = makeOProjKernel(heads: heads, broadcast: true)
        let perturbed = makeOProjKernel(heads: heads, broadcast: true, perturbFirstOutputBit: true)
        eval(fixture.inputs)

        let controlOutput = runOProj(control, fixture: fixture)
        let candidateOutput = runOProj(candidate, fixture: fixture)
        let perturbedOutput = runOProj(perturbed, fixture: fixture)
        eval(controlOutput, candidateOutput, perturbedOutput)

        let controlData = controlOutput.asData(access: .copy).data
        let candidateData = candidateOutput.asData(access: .copy).data
        let perturbedData = perturbedOutput.asData(access: .copy).data
        let firstBits = controlData.withUnsafeBytes { bytes in
            bytes.loadUnaligned(as: UInt16.self)
        }

        #expect(controlData == candidateData)
        #expect(controlData != perturbedData)
        #expect(firstBits != 0)
        #expect(firstBits & 0x8000 == 0)
        print(
            "OPROJ_GATE_ORACLE_JSON={\"heads\":\(heads),"
                + "\"bytes\":\(controlData.count),"
                + "\"candidate_bitwise_equal\":true,"
                + "\"one_bit_positive_control_detected\":true}"
        )
    }
}

@Test
func oprojActivatedGateSIMDBroadcastAlternatingTiming() throws {
    guard ProcessInfo.processInfo.environment[oprojGateBroadcastTimingEnvironment] == "1" else {
        return
    }

    for heads in [48, 64] {
        let fixture = makeOProjFixture(heads: heads)
        let control = makeOProjKernel(heads: heads, broadcast: false)
        let candidate = makeOProjKernel(heads: heads, broadcast: true)
        eval(fixture.inputs)
        eval(
            runOProj(control, fixture: fixture),
            runOProj(candidate, fixture: fixture)
        )
        Stream.gpu.synchronize()

        var controlAB: [Double] = []
        var candidateAB: [Double] = []
        var controlBA: [Double] = []
        var candidateBA: [Double] = []
        for cycle in 0..<oprojTimingCycles {
            if cycle.isMultiple(of: 2) {
                controlAB.append(measureOProj(control, fixture: fixture))
                candidateAB.append(measureOProj(candidate, fixture: fixture))
            } else {
                candidateBA.append(measureOProj(candidate, fixture: fixture))
                controlBA.append(measureOProj(control, fixture: fixture))
            }
        }

        let controlABMedian = median(controlAB)
        let candidateABMedian = median(candidateAB)
        let controlBAMedian = median(controlBA)
        let candidateBAMedian = median(candidateBA)
        let speedupAB = controlABMedian / candidateABMedian
        let speedupBA = controlBAMedian / candidateBAMedian
        let result: [String: Any] = [
            "heads": heads,
            "batch_size": oprojTimingBatchSize,
            "cycles": oprojTimingCycles,
            "seconds_per_dispatch": [
                "control_ab": controlAB,
                "candidate_ab": candidateAB,
                "control_ba": controlBA,
                "candidate_ba": candidateBA,
            ],
            "medians": [
                "control_ab": controlABMedian,
                "candidate_ab": candidateABMedian,
                "control_ba": controlBAMedian,
                "candidate_ba": candidateBAMedian,
            ],
            "speedup": ["ab": speedupAB, "ba": speedupBA],
            "gate": ["minimum": 1.002, "passed": speedupAB >= 1.002 && speedupBA >= 1.002],
        ]
        let data = try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys])
        print("OPROJ_GATE_TIMING_JSON=\(String(decoding: data, as: UTF8.self))")

        #expect(speedupAB >= 1.002)
        #expect(speedupBA >= 1.002)
    }
}

private struct OProjFixture {
    let heads: Int
    let inputs: [MLXArray]
}

private func makeOProjFixture(heads: Int) -> OProjFixture {
    let inputSize = heads * 128
    let attentionValues = (0..<inputSize).map { index in
        Float((index % 127) + 1) / 128
    }
    let gateValues = (0..<heads).map { head in
        Float(head + 1) / Float(heads)
    }
    let attention = MLXArray(attentionValues, [1, 1, inputSize]).asType(.bfloat16)
    let gates = MLXArray(gateValues, [1, 1, heads]).asType(.bfloat16)
    let codes = MLXArray.full(
        [oprojOutputSize, inputSize / 8],
        values: MLXArray(UInt32(0x7654_3210)),
        dtype: .uint32
    )
    let scales = MLXArray.full(
        [oprojOutputSize, inputSize / 16],
        values: MLXArray(UInt8(0x38)),
        dtype: .uint8
    )
    return OProjFixture(heads: heads, inputs: [attention, gates, codes, scales])
}

private func makeOProjKernel(
    heads: Int,
    broadcast: Bool,
    perturbFirstOutputBit: Bool = false
) -> MLXFast.MLXFastKernel {
    var source = lagunaGatedAffineOProjNVFP4Source(
        heads: heads,
        preActivatedGate: true,
        simdGateBroadcast: broadcast
    )
    if perturbFirstOutputBit {
        let original = "projected[out_row + row] = bfloat(result[row]);"
        let replacement = """
        bfloat value = bfloat(result[row]);
        ushort bits = as_type<ushort>(value);
        if (out_row + row == 0) bits ^= ushort(1);
        projected[out_row + row] = as_type<bfloat>(bits);
        """
        precondition(source.contains(original))
        source = source.replacingOccurrences(of: original, with: replacement)
    }
    return MLXFast.metalKernel(
        name: "laguna_oproj_gate_broadcast_test_h\(heads)_b\(broadcast ? 1 : 0)"
            + (perturbFirstOutputBit ? "_p1" : ""),
        inputNames: ["attention_output", "gate_values", "weight_codes", "weight_scales"],
        outputNames: ["projected"],
        source: source,
        ensureRowContiguous: true
    )
}

private func runOProj(
    _ kernel: MLXFast.MLXFastKernel,
    fixture: OProjFixture
) -> MLXArray {
    kernel(
        fixture.inputs,
        grid: ((oprojOutputSize / 8) * 64, 1, 1),
        threadGroup: (64, 1, 1),
        outputShapes: [[1, 1, oprojOutputSize]],
        outputDTypes: [.bfloat16]
    )[0]
}

private func measureOProj(
    _ kernel: MLXFast.MLXFastKernel,
    fixture: OProjFixture
) -> Double {
    let outputs = (0..<oprojTimingBatchSize).map { _ in
        runOProj(kernel, fixture: fixture)
    }
    Stream.gpu.synchronize()
    let start = DispatchTime.now().uptimeNanoseconds
    eval(outputs)
    Stream.gpu.synchronize()
    return Double(DispatchTime.now().uptimeNanoseconds - start)
        / 1_000_000_000
        / Double(oprojTimingBatchSize)
}

private func median(_ values: [Double]) -> Double {
    let sorted = values.sorted()
    let middle = sorted.count / 2
    if sorted.count.isMultiple(of: 2) {
        return (sorted[middle - 1] + sorted[middle]) / 2
    }
    return sorted[middle]
}
