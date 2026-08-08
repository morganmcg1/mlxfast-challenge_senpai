import Foundation
import MLX
import Testing

@Test
func prefillTransposeGateBaselineDispatchTraceWhenEnabled() {
    guard
        let headsText = ProcessInfo.processInfo.environment[
            "MLXFAST_PREFILL_TAIL_DISPATCH_TRACE_HEADS"],
        let heads = Int(headsText),
        heads == 48 || heads == 64
    else {
        return
    }

    let length = 512
    let headDimension = 128
    let attended = MLXArray.zeros(
        [1, heads, length, headDimension], dtype: .bfloat16)
    let gate = MLXArray.ones([1, length, heads], dtype: .bfloat16)
    let weight = MLXArray.zeros(
        [2048, heads * headDimension], dtype: .bfloat16)
    eval(attended, gate, weight)

    let flattened = attended.transposed(0, 2, 1, 3).reshaped(
        1, length, heads * headDimension)
    let gated = (
        flattened.reshaped(1, length, heads, headDimension)
            * gate[.ellipsis, .newAxis]
    ).reshaped(1, length, heads * headDimension)
    let projected = matmul(gated, weight.T)

    let start = Date().timeIntervalSince1970
    let message =
        "prefill_tail_dispatch_begin heads=\(heads) time=\(start) "
        + "attended_shape=\(attended.shape) attended_dtype=\(attended.dtype) "
        + "gate_shape=\(gate.shape) gate_dtype=\(gate.dtype) "
        + "flatten_shape=\(flattened.shape) flatten_dtype=\(flattened.dtype) "
        + "gated_shape=\(gated.shape) gated_dtype=\(gated.dtype) "
        + "projected_shape=\(projected.shape)\n"
    FileHandle.standardError.write(Data(message.utf8))
    eval(projected)
    let end = Date().timeIntervalSince1970
    FileHandle.standardError.write(
        Data("prefill_tail_dispatch_end heads=\(heads) time=\(end)\n".utf8))

    #expect(projected.shape == [1, length, 2048])
    #expect(projected.dtype == .bfloat16)
}
