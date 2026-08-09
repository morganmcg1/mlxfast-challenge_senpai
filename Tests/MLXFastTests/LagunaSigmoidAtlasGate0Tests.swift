import Foundation
import MLX
import MLXFast
import Testing

private let gate0AtlasKernel = MLXFast.metalKernel(
    name: "laguna_gate0_bf16_sigmoid_atlas",
    inputNames: [],
    outputNames: ["atlas"],
    source: """
        uint raw = thread_position_in_grid.x;
        bfloat gate = as_type<bfloat>(ushort(raw));
        bfloat exp_abs = metal::exp(metal::abs(gate));
        bfloat denominator = bfloat(1) + exp_abs;
        bfloat y = bfloat(1) / denominator;
        atlas[raw] = gate < bfloat(0) ? y : bfloat(1) - y;
        """
)

private let gate0SharedInlineKernel = MLXFast.metalKernel(
    name: "laguna_gate0_shared_inline",
    inputNames: ["seed"],
    outputNames: ["output"],
    source: """
        uint row = threadgroup_position_in_grid.x * 2
            + simdgroup_index_in_threadgroup;
        uint lane = thread_index_in_simdgroup;
        if (lane == 0) {
            ushort raw = ushort((row * 131 + seed * 997) & 0xffff);
            bfloat gate = as_type<bfloat>(raw);
            bfloat exp_abs = metal::exp(metal::abs(gate));
            bfloat denominator = bfloat(1) + exp_abs;
            bfloat y = bfloat(1) / denominator;
            output[row] = gate < bfloat(0) ? y : bfloat(1) - y;
        }
        """
)

private let gate0SharedAtlasKernel = MLXFast.metalKernel(
    name: "laguna_gate0_shared_atlas",
    inputNames: ["atlas", "seed"],
    outputNames: ["output"],
    source: """
        uint row = threadgroup_position_in_grid.x * 2
            + simdgroup_index_in_threadgroup;
        uint lane = thread_index_in_simdgroup;
        if (lane == 0) {
            ushort raw = ushort((row * 131 + seed * 997) & 0xffff);
            bfloat gate = as_type<bfloat>(raw);
            output[row] = atlas[uint(as_type<ushort>(gate))];
        }
        """
)

private let gate0RoutedInlineKernel = MLXFast.metalKernel(
    name: "laguna_gate0_routed_inline",
    inputNames: ["seed"],
    outputNames: ["output"],
    source: """
        constexpr uint routed_experts = 8;
        constexpr uint output_width = 512;
        uint group = threadgroup_position_in_grid.x;
        uint expert_slot = group % routed_experts;
        uint tile = group / routed_experts;
        uint logical_row = tile * 2 + simdgroup_index_in_threadgroup;
        uint lane = thread_index_in_simdgroup;
        if (lane == 0) {
            uint row = expert_slot * output_width + logical_row;
            ushort raw = ushort((row * 131 + seed * 997) & 0xffff);
            bfloat gate = as_type<bfloat>(raw);
            bfloat exp_abs = metal::exp(metal::abs(gate));
            bfloat denominator = bfloat(1) + exp_abs;
            bfloat y = bfloat(1) / denominator;
            output[row] = gate < bfloat(0) ? y : bfloat(1) - y;
        }
        """
)

private let gate0RoutedAtlasKernel = MLXFast.metalKernel(
    name: "laguna_gate0_routed_atlas",
    inputNames: ["atlas", "seed"],
    outputNames: ["output"],
    source: """
        constexpr uint routed_experts = 8;
        constexpr uint output_width = 512;
        uint group = threadgroup_position_in_grid.x;
        uint expert_slot = group % routed_experts;
        uint tile = group / routed_experts;
        uint logical_row = tile * 2 + simdgroup_index_in_threadgroup;
        uint lane = thread_index_in_simdgroup;
        if (lane == 0) {
            uint row = expert_slot * output_width + logical_row;
            ushort raw = ushort((row * 131 + seed * 997) & 0xffff);
            bfloat gate = as_type<bfloat>(raw);
            output[row] = atlas[uint(as_type<ushort>(gate))];
        }
        """
)

@Test
func bf16SigmoidAtlasGate0BoundWhenRuntimeTestsAreEnabled() {
    guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1" else {
        return
    }

    let atlas = gate0AtlasKernel(
        [],
        grid: (65_536, 1, 1),
        threadGroup: (256, 1, 1),
        outputShapes: [[65_536]],
        outputDTypes: [.bfloat16]
    )[0]
    eval(atlas)

    func outputs(useAtlas: Bool) -> [MLXArray] {
        var result = [MLXArray]()
        result.reserveCapacity(78)
        for layer in 0..<39 {
            let seed = MLXArray(UInt32(layer))
            if useAtlas {
                result.append(
                    gate0SharedAtlasKernel(
                        [atlas, seed],
                        grid: (256 * 64, 1, 1),
                        threadGroup: (64, 1, 1),
                        outputShapes: [[512]],
                        outputDTypes: [.bfloat16]
                    )[0])
                result.append(
                    gate0RoutedAtlasKernel(
                        [atlas, seed],
                        grid: (8 * 256 * 64, 1, 1),
                        threadGroup: (64, 1, 1),
                        outputShapes: [[8 * 512]],
                        outputDTypes: [.bfloat16]
                    )[0])
            } else {
                result.append(
                    gate0SharedInlineKernel(
                        [seed],
                        grid: (256 * 64, 1, 1),
                        threadGroup: (64, 1, 1),
                        outputShapes: [[512]],
                        outputDTypes: [.bfloat16]
                    )[0])
                result.append(
                    gate0RoutedInlineKernel(
                        [seed],
                        grid: (8 * 256 * 64, 1, 1),
                        threadGroup: (64, 1, 1),
                        outputShapes: [[8 * 512]],
                        outputDTypes: [.bfloat16]
                    )[0])
            }
        }
        return result
    }

    func measure(useAtlas: Bool) -> Double {
        let pending = outputs(useAtlas: useAtlas)
        let start = ProcessInfo.processInfo.systemUptime
        eval(pending)
        return (ProcessInfo.processInfo.systemUptime - start) * 1_000_000
    }

    _ = measure(useAtlas: false)
    _ = measure(useAtlas: true)

    var inlineSamples = [Double]()
    var atlasSamples = [Double]()
    for trial in 0..<12 {
        if trial.isMultiple(of: 2) {
            inlineSamples.append(measure(useAtlas: false))
            atlasSamples.append(measure(useAtlas: true))
        } else {
            atlasSamples.append(measure(useAtlas: true))
            inlineSamples.append(measure(useAtlas: false))
        }
    }
    inlineSamples.sort()
    atlasSamples.sort()
    let inlineMedian = (inlineSamples[5] + inlineSamples[6]) / 2
    let atlasMedian = (atlasSamples[5] + atlasSamples[6]) / 2
    let savings = inlineMedian - atlasMedian
    print(
        String(
            format: "GATE0_SIGMOID_ATLAS inline_us=%.3f atlas_us=%.3f savings_us=%.3f",
            inlineMedian, atlasMedian, savings))
    #expect(savings >= 20)
}
