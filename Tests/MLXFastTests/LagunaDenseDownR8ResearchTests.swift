import Dispatch
import Foundation
import Metal
import MLX
@testable import MLXFastModel
import Testing

private let denseDownR4ControlKernel = MLXFast.metalKernel(
    name: "laguna_dense_down_residual_bf16_r4_research_control",
    inputNames: ["activated", "down_weight", "residual"],
    outputNames: ["output"],
    source: denseDownBody(rowsPerThread: 4),
    ensureRowContiguous: true
)

@Test
func denseDownR8MatchesR4BitwiseWhenResearchTestsAreEnabled() throws {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_DENSE_DOWN_R8_TESTS"] == "1" else {
        return
    }

    let finitePalette: [UInt16] = [
        0x0000, 0x8000, 0x3b80, 0xbb80, 0x3c00, 0xbc00,
        0x3c80, 0xbc80, 0x3d00, 0xbd00,
    ]
    for seed in [UInt32(0x1234_5678), UInt32(0xdead_beef), UInt32(0xa5a5_5a5a)] {
        let inputs = denseDownInputs(seed: seed, palette: finitePalette)
        let control = denseDownR4(inputs)
        let candidate = lagunaDenseDownResidual(
            inputs.activated,
            downWeight: inputs.weight,
            residual: inputs.residual
        )
        eval(control, candidate)
        let controlBits = rawBF16(control)
        let candidateBits = rawBF16(candidate)
        #expect(controlBits == candidateBits)
        #expect(zip(controlBits, candidateBits).allSatisfy { $0 == $1 })
    }

    let edgePalette: [UInt16] = [
        0x0000, 0x8000, 0x0001, 0x8001, 0x0080, 0x8080,
        0x7f7f, 0xff7f, 0x7f80, 0xff80, 0x7fc1, 0xffc1,
    ]
    let edgeInputs = denseDownInputs(seed: 0x1357_9bdf, palette: edgePalette)
    let edgeControl = denseDownR4(edgeInputs)
    let edgeCandidate = lagunaDenseDownResidual(
        edgeInputs.activated,
        downWeight: edgeInputs.weight,
        residual: edgeInputs.residual
    )
    eval(edgeControl, edgeCandidate)
    let edgeControlBits = rawBF16(edgeControl)
    let edgeCandidateBits = rawBF16(edgeCandidate)
    #expect(edgeControlBits == edgeCandidateBits)

    var corrupted = edgeCandidateBits
    corrupted[1_024] ^= 1
    #expect(corrupted != edgeControlBits)
    print("DENSE_DOWN_R8_CORRUPTION_ORACLE detected=true index=1024 xor=1")
}

@Test
func denseDownR8GeometryAndPipelineResourcesWhenResearchTestsAreEnabled() throws {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_DENSE_DOWN_R8_TESTS"] == "1" else {
        return
    }

    let rows = (0..<64).flatMap { tile in
        (0..<4).flatMap { simdGroup in
            (0..<8).map { row in tile * 32 + simdGroup * 8 + row }
        }
    }
    #expect(rows.count == 2_048)
    #expect(Set(rows).count == 2_048)
    #expect(rows.min() == 0)
    #expect(rows.max() == 2_047)
    #expect(rows.sorted() == Array(0..<2_048))

    let device = try #require(MTLCreateSystemDefaultDevice())
    let resources = try [
        pipelineResources(device: device, rowsPerThread: 4),
        pipelineResources(device: device, rowsPerThread: 8),
    ]
    let data = try JSONSerialization.data(withJSONObject: resources, options: [.sortedKeys])
    print("DENSE_DOWN_PIPELINE_RESOURCES \(String(decoding: data, as: UTF8.self))")
    print(
        "DENSE_DOWN_R8_GEOMETRY grid=64x128 threadgroup=128 simdgroups=4 "
            + "rows_per_simdgroup=8 first_row=0 last_row=2047 unique_rows=2048 "
            + "threadgroup_memory=0"
    )
}

@Test
func denseDownR8IsolatedMirroredBenchmarkWhenResearchTestsAreEnabled() throws {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_DENSE_DOWN_R8_MICROBENCH"] == "1" else {
        return
    }

    let inputs = denseDownInputs(
        seed: 0xc001_d00d,
        palette: [0x0000, 0x8000, 0x3b80, 0xbb80, 0x3c00, 0xbc00, 0x3c80, 0xbc80]
    )
    eval(inputs.activated, inputs.weight, inputs.residual)

    for _ in 0..<6 {
        _ = timedDenseDown { denseDownR4(inputs) }
        _ = timedDenseDown {
            lagunaDenseDownResidual(
                inputs.activated,
                downWeight: inputs.weight,
                residual: inputs.residual
            )
        }
    }

    var abControl: [Double] = []
    var abCandidate: [Double] = []
    for _ in 0..<24 {
        abControl.append(timedDenseDown { denseDownR4(inputs) })
        abCandidate.append(
            timedDenseDown {
                lagunaDenseDownResidual(
                    inputs.activated,
                    downWeight: inputs.weight,
                    residual: inputs.residual
                )
            })
    }

    var baCandidate: [Double] = []
    var baControl: [Double] = []
    for _ in 0..<24 {
        baCandidate.append(
            timedDenseDown {
                lagunaDenseDownResidual(
                    inputs.activated,
                    downWeight: inputs.weight,
                    residual: inputs.residual
                )
            })
        baControl.append(timedDenseDown { denseDownR4(inputs) })
    }

    let payload: [String: Any] = [
        "warmups_per_arm": 6,
        "samples_per_arm_per_order": 24,
        "ab": timingPayload(control: abControl, candidate: abCandidate),
        "ba": timingPayload(control: baControl, candidate: baCandidate),
    ]
    let data = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
    print("DENSE_DOWN_MICROBENCH_JSON \(String(decoding: data, as: UTF8.self))")
}

private struct DenseDownInputs {
    let activated: MLXArray
    let weight: MLXArray
    let residual: MLXArray
}

private func denseDownInputs(seed: UInt32, palette: [UInt16]) -> DenseDownInputs {
    var state = seed
    func bits(_ count: Int) -> [UInt16] {
        [UInt16](unsafeUninitializedCapacity: count) { buffer, initializedCount in
            for index in 0..<count {
                state = state &* 1_664_525 &+ 1_013_904_223
                buffer[index] = palette[Int(state % UInt32(palette.count))]
            }
            initializedCount = count
        }
    }
    return DenseDownInputs(
        activated: MLXArray(bits(8_192), [1, 1, 8_192]).view(dtype: .bfloat16),
        weight: MLXArray(bits(2_048 * 8_192), [2_048, 8_192]).view(dtype: .bfloat16),
        residual: MLXArray(bits(2_048), [1, 1, 2_048]).view(dtype: .bfloat16)
    )
}

private func denseDownR4(_ inputs: DenseDownInputs) -> MLXArray {
    denseDownR4ControlKernel(
        [inputs.activated, inputs.weight, inputs.residual],
        grid: (128 * 128, 1, 1),
        threadGroup: (128, 1, 1),
        outputShapes: [[1, 1, 2_048]],
        outputDTypes: [.bfloat16]
    )[0]
}

private func rawBF16(_ array: MLXArray) -> [UInt16] {
    array.view(dtype: .uint16).asArray(UInt16.self)
}

private func timedDenseDown(_ operation: () -> MLXArray) -> Double {
    let start = DispatchTime.now().uptimeNanoseconds
    eval(operation())
    return Double(DispatchTime.now().uptimeNanoseconds - start) / 1_000_000_000
}

private func median(_ values: [Double]) -> Double {
    let sorted = values.sorted()
    let middle = sorted.count / 2
    if sorted.count.isMultiple(of: 2) {
        return (sorted[middle - 1] + sorted[middle]) / 2
    }
    return sorted[middle]
}

private func medianAbsoluteDeviation(_ values: [Double]) -> Double {
    let center = median(values)
    return median(values.map { abs($0 - center) })
}

private func timingPayload(control: [Double], candidate: [Double]) -> [String: Any] {
    let controlMedian = median(control)
    let candidateMedian = median(candidate)
    return [
        "control_seconds": control,
        "candidate_seconds": candidate,
        "control_median_seconds": controlMedian,
        "candidate_median_seconds": candidateMedian,
        "control_mad_seconds": medianAbsoluteDeviation(control),
        "candidate_mad_seconds": medianAbsoluteDeviation(candidate),
        "speedup": controlMedian / candidateMedian,
    ]
}

private func pipelineResources(device: MTLDevice, rowsPerThread: Int) throws -> [String: Any] {
    let library = try device.makeLibrary(source: denseDownMetalSource(rowsPerThread: rowsPerThread), options: nil)
    let function = try #require(library.makeFunction(name: "dense_down"))
    let pipeline = try device.makeComputePipelineState(function: function)
    return [
        "rows_per_thread": rowsPerThread,
        "thread_execution_width": pipeline.threadExecutionWidth,
        "max_total_threads_per_threadgroup": pipeline.maxTotalThreadsPerThreadgroup,
        "static_threadgroup_memory_length": pipeline.staticThreadgroupMemoryLength,
        "dynamic_threadgroup_memory_length": 0,
        "register_count": "unavailable from public Metal API",
        "occupancy": "unavailable from public Metal API",
        "spill_bytes": "unavailable from public Metal API",
    ]
}

private func denseDownMetalSource(rowsPerThread: Int) -> String {
    """
    #include <metal_stdlib>
    using namespace metal;
    kernel void dense_down(
        device const bfloat* activated [[buffer(0)]],
        device const bfloat* down_weight [[buffer(1)]],
        device const bfloat* residual [[buffer(2)]],
        device bfloat* output [[buffer(3)]],
        uint3 threadgroup_position_in_grid [[threadgroup_position_in_grid]],
        uint simdgroup_index_in_threadgroup [[simdgroup_index_in_threadgroup]],
        uint thread_index_in_simdgroup [[thread_index_in_simdgroup]]) {
    \(denseDownBody(rowsPerThread: rowsPerThread))
    }
    """
}

private func denseDownBody(rowsPerThread: Int) -> String {
    let zeroes = Array(repeating: "0.0f", count: rowsPerThread).joined(separator: ", ")
    return """
    constexpr uint in_vec_size = 8192;
    constexpr uint rows_per_thread = \(rowsPerThread);
    constexpr uint values_per_thread = 4;
    constexpr uint block_width = 128;
    constexpr uint blocks = in_vec_size / block_width;
    constexpr uint rows_per_group = \(rowsPerThread * 4);

    uint tile = threadgroup_position_in_grid.x;
    uint simd_group = simdgroup_index_in_threadgroup;
    uint lane = thread_index_in_simdgroup;
    uint row_base = tile * rows_per_group + simd_group * rows_per_thread;

    thread float result[rows_per_thread] = {\(zeroes)};
    thread float coefficients[values_per_thread];
    uint column = lane * values_per_thread;
    for (uint block = 0; block < blocks; ++block) {
        const vec<bfloat, 4> c4 =
            *((const device vec<bfloat, 4>*)(activated + column));
        for (uint i = 0; i < values_per_thread; ++i) {
            coefficients[i] = float(c4[i]);
        }
        for (uint row = 0; row < rows_per_thread; ++row) {
            const device vec<bfloat, 4>* row_values =
                (const device vec<bfloat, 4>*)(
                    down_weight + (row_base + row) * in_vec_size + column);
            const vec<bfloat, 4> w = row_values[0];
            for (uint i = 0; i < values_per_thread; ++i) {
                result[row] += float(w[i]) * coefficients[i];
            }
        }
        column += block_width;
    }

    for (uint row = 0; row < rows_per_thread; ++row) {
        for (ushort delta = 16; delta >= 1; delta >>= 1) {
            result[row] += metal::simd_shuffle_down(result[row], delta);
        }
    }
    if (lane == 0) {
        for (uint row = 0; row < rows_per_thread; ++row) {
            bfloat down = bfloat(result[row]);
            output[row_base + row] = bfloat(residual[row_base + row] + down);
        }
    }
    """
}
