import Foundation
import Metal
import MLX
@testable import MLXFastModel
import Testing

private let denseHiddenSize = 2048
private let denseIntermediateSize = 8192

private func denseGateUpBody(rowsPerThread: Int, rowsPerGroup: Int) -> String {
    let zeros = Array(repeating: "0.0f", count: rowsPerThread).joined(separator: ", ")
    return """
        constexpr uint in_vec_size = 2048;
        constexpr uint output_width = 8192;
        constexpr uint rows_per_thread = \(rowsPerThread);
        constexpr uint values_per_thread = 4;
        constexpr uint block_width = 128;
        constexpr uint blocks = in_vec_size / block_width;
        constexpr uint rows_per_group = \(rowsPerGroup);

        uint tile = threadgroup_position_in_grid.x;
        uint simd_group = simdgroup_index_in_threadgroup;
        uint lane = thread_index_in_simdgroup;

        uint row_base = tile * rows_per_group + simd_group * rows_per_thread;

        thread float gate_result[rows_per_thread] = {\(zeros)};
        thread float up_result[rows_per_thread] = {\(zeros)};
        thread float coefficients[values_per_thread];

        uint column = lane * values_per_thread;
        for (uint block = 0; block < blocks; ++block) {
            const vec<bfloat, 4> c4 =
                *((const device vec<bfloat, 4>*)(input + column));
            for (uint i = 0; i < values_per_thread; ++i) {
                coefficients[i] = float(c4[i]);
            }
            for (uint row = 0; row < rows_per_thread; ++row) {
                const device vec<bfloat, 4>* gate_row_values =
                    (const device vec<bfloat, 4>*)(
                        fused_weight + (row_base + row) * in_vec_size + column);
                const vec<bfloat, 4> gw = gate_row_values[0];
                const device vec<bfloat, 4>* up_row_values =
                    (const device vec<bfloat, 4>*)(
                        fused_weight +
                        (output_width + row_base + row) * in_vec_size + column);
                const vec<bfloat, 4> uw = up_row_values[0];
                for (uint i = 0; i < values_per_thread; ++i) {
                    gate_result[row] += float(gw[i]) * coefficients[i];
                    up_result[row] += float(uw[i]) * coefficients[i];
                }
            }
            column += block_width;
        }

        for (uint row = 0; row < rows_per_thread; ++row) {
            for (ushort delta = 16; delta >= 1; delta >>= 1) {
                gate_result[row] +=
                    metal::simd_shuffle_down(gate_result[row], delta);
                up_result[row] +=
                    metal::simd_shuffle_down(up_result[row], delta);
            }
        }
        if (lane == 0) {
            for (uint row = 0; row < rows_per_thread; ++row) {
                bfloat gate = bfloat(gate_result[row]);
                bfloat up = bfloat(up_result[row]);
                bfloat exp_abs = metal::exp(metal::abs(gate));
                bfloat denominator = bfloat(1) + exp_abs;
                bfloat y = bfloat(1) / denominator;
                bfloat sigmoid = gate < bfloat(0) ? y : bfloat(1) - y;
                bfloat silu = bfloat(gate * sigmoid);
                activated[row_base + row] = bfloat(silu * up);
            }
        }
        """
}

private let fourRowControlKernel = MLXFast.metalKernel(
    name: "laguna_dense_gate_up_swiglu_bf16_four_row_control",
    inputNames: ["input", "fused_weight"],
    outputNames: ["activated"],
    source: denseGateUpBody(rowsPerThread: 4, rowsPerGroup: 64),
    ensureRowContiguous: true
)

private func fourRowControl(_ input: MLXArray, fusedWeight: MLXArray) -> MLXArray {
    fourRowControlKernel(
        [input, fusedWeight],
        grid: ((denseIntermediateSize / 64) * 512, 1, 1),
        threadGroup: (512, 1, 1),
        outputShapes: [[1, 1, denseIntermediateSize]],
        outputDTypes: [.bfloat16]
    )[0]
}

private func makeInput(seed: UInt64?) -> MLXArray {
    var state = seed ?? 0
    let values: [Float] = (0..<denseHiddenSize).map { index in
        if index.isMultiple(of: seed == nil ? 17 : 31) {
            return 0
        }
        if seed == nil {
            return Float((index % 29) - 14) / 64
        }
        state = state &* 6_364_136_223_846_793_005 &+ 1_442_695_040_888_963_407
        let unit = Float((state >> 40) & 0xFF_FFFF) / Float(0xFF_FFFF)
        return (2 * unit - 1) * 0.25
    }
    return MLXArray(values).asType(.bfloat16).reshaped([1, 1, denseHiddenSize])
}

private func makeFusedWeight() -> MLXArray {
    let columns = MLXArray(0..<denseHiddenSize).asType(.float32).reshaped([1, denseHiddenSize])
    let rows = MLXArray(0..<(2 * denseIntermediateSize)).asType(.float32)
        .reshaped([2 * denseIntermediateSize, 1])
    return (sin(columns * 0.017 + rows * 0.003) * 0.0625).asType(.bfloat16)
}

private func compareExact(input: MLXArray, fusedWeight: MLXArray) -> (Bool, Float) {
    let control = fourRowControl(input, fusedWeight: fusedWeight)
    let candidate = lagunaDenseGateUpSwiGLU(input, fusedWeight: fusedWeight)
    eval(control, candidate)
    let equalBytes = control.asData().data == candidate.asData().data
    let maxAbsoluteDifference = abs(
        control.asType(.float32) - candidate.asType(.float32)
    ).max().item(Float.self)
    return (equalBytes, maxAbsoluteDifference)
}

private func elapsedMilliseconds(
    iterations: Int,
    operation: () -> MLXArray
) -> Double {
    Stream.gpu.synchronize()
    let start = DispatchTime.now().uptimeNanoseconds
    var outputs = [MLXArray]()
    outputs.reserveCapacity(iterations)
    for _ in 0..<iterations {
        outputs.append(operation())
    }
    eval(outputs)
    Stream.gpu.synchronize()
    let elapsed = DispatchTime.now().uptimeNanoseconds - start
    return Double(elapsed) / 1_000_000 / Double(iterations)
}

private func median(_ values: [Double]) -> Double {
    let sorted = values.sorted()
    return sorted[sorted.count / 2]
}

private func pipelineState(
    device: MTLDevice,
    name: String,
    rowsPerThread: Int,
    rowsPerGroup: Int
) throws -> MTLComputePipelineState {
    let body = denseGateUpBody(rowsPerThread: rowsPerThread, rowsPerGroup: rowsPerGroup)
        .replacingOccurrences(
            of: "bfloat exp_abs = metal::exp(metal::abs(gate));",
            with: "bfloat exp_abs = bfloat(metal::exp(metal::abs(float(gate))));"
        )
    let source = """
        #include <metal_stdlib>
        using namespace metal;
        kernel void \(name)(
            device const bfloat* input [[buffer(0)]],
            device const bfloat* fused_weight [[buffer(1)]],
            device bfloat* activated [[buffer(2)]],
            uint3 threadgroup_position_in_grid [[threadgroup_position_in_grid]],
            uint simdgroup_index_in_threadgroup [[simdgroup_index_in_threadgroup]],
            uint thread_index_in_simdgroup [[thread_index_in_simdgroup]]) {
        \(body)
        }
        """
    let library = try device.makeLibrary(source: source, options: nil)
    let function = try #require(library.makeFunction(name: name))
    return try device.makeComputePipelineState(function: function)
}

private func printPipelineEvidence() throws {
    let device = try #require(MTLCreateSystemDefaultDevice())
    for (label, rowsPerThread, rowsPerGroup) in [
        ("four_row", 4, 64),
        ("two_row", 2, 32),
    ] {
        let pipeline = try pipelineState(
            device: device,
            name: "dense_gate_up_\(label)_evidence",
            rowsPerThread: rowsPerThread,
            rowsPerGroup: rowsPerGroup
        )
        print(
            "dense_gate_up_pipeline label=\(label) "
                + "thread_execution_width=\(pipeline.threadExecutionWidth) "
                + "max_threads_per_threadgroup=\(pipeline.maxTotalThreadsPerThreadgroup) "
                + "static_threadgroup_memory=\(pipeline.staticThreadgroupMemoryLength)"
        )
    }
}

@Test
func layer0DenseTwoRowExactnessAndIsolatedTiming() throws {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_DENSE_GATE_UP_EXPERIMENT"] == "1"
    else {
        return
    }

    try printPipelineEvidence()
    let fusedWeight = makeFusedWeight()
    eval(fusedWeight)

    for (label, input) in [
        ("deterministic", makeInput(seed: nil)),
        ("random_seed_0x5eed", makeInput(seed: 0x5EED)),
    ] {
        let (equalBytes, maxAbsoluteDifference) = compareExact(
            input: input,
            fusedWeight: fusedWeight
        )
        print(
            "dense_gate_up_exact label=\(label) equal_bf16_bytes=\(equalBytes) "
                + "max_abs_diff=\(maxAbsoluteDifference)"
        )
        #expect(equalBytes, "two-row output changed BF16 bytes for \(label)")
        #expect(maxAbsoluteDifference == 0, "two-row output changed values for \(label)")
    }

    let timingInput = makeInput(seed: 0xC0FFEE)
    for _ in 0..<4 {
        eval(
            fourRowControl(timingInput, fusedWeight: fusedWeight),
            lagunaDenseGateUpSwiGLU(timingInput, fusedWeight: fusedWeight)
        )
    }
    Stream.gpu.synchronize()

    let iterations = 80
    let samples = 7
    var abSpeedups = [Double]()
    var baSpeedups = [Double]()
    for sample in 0..<samples {
        let baseline = elapsedMilliseconds(iterations: iterations) {
            fourRowControl(timingInput, fusedWeight: fusedWeight)
        }
        let candidate = elapsedMilliseconds(iterations: iterations) {
            lagunaDenseGateUpSwiGLU(timingInput, fusedWeight: fusedWeight)
        }
        let speedup = baseline / candidate
        abSpeedups.append(speedup)
        print(
            "dense_gate_up_timing order=A/B sample=\(sample) baseline_ms=\(baseline) "
                + "candidate_ms=\(candidate) speedup=\(speedup)"
        )
    }
    for sample in 0..<samples {
        let candidate = elapsedMilliseconds(iterations: iterations) {
            lagunaDenseGateUpSwiGLU(timingInput, fusedWeight: fusedWeight)
        }
        let baseline = elapsedMilliseconds(iterations: iterations) {
            fourRowControl(timingInput, fusedWeight: fusedWeight)
        }
        let speedup = baseline / candidate
        baSpeedups.append(speedup)
        print(
            "dense_gate_up_timing order=B/A sample=\(sample) baseline_ms=\(baseline) "
                + "candidate_ms=\(candidate) speedup=\(speedup)"
        )
    }

    let abMedian = median(abSpeedups)
    let baMedian = median(baSpeedups)
    let passed = abMedian >= 1.002 && baMedian >= 1.002
    print(
        "dense_gate_up_decision ab_median_speedup=\(abMedian) "
            + "ba_median_speedup=\(baMedian) threshold=1.002 passed=\(passed)"
    )
}
