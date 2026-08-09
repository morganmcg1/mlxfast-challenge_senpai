import Foundation
import MLX
import Testing

@testable import MLXFastModel

private let layer0GateUpBaselineKernel = MLXFast.metalKernel(
    name: "laguna_dense_gate_up_swiglu_bf16_baseline_tg512_diagnostic",
    inputNames: ["input", "fused_weight"],
    outputNames: ["activated"],
    source: """
constexpr uint in_vec_size = 2048;
constexpr uint output_width = 8192;
constexpr uint rows_per_thread = 4;
constexpr uint values_per_thread = 4;
constexpr uint block_width = 128;
constexpr uint blocks = in_vec_size / block_width;
constexpr uint rows_per_group = 64;

uint tile = threadgroup_position_in_grid.x;
uint simd_group = simdgroup_index_in_threadgroup;
uint lane = thread_index_in_simdgroup;

uint row_base = tile * rows_per_group + simd_group * rows_per_thread;

thread float gate_result[rows_per_thread] = {0.0f, 0.0f, 0.0f, 0.0f};
thread float up_result[rows_per_thread] = {0.0f, 0.0f, 0.0f, 0.0f};
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
            (const device vec<bfloat, 4>*) (
                fused_weight + (row_base + row) * in_vec_size + column);
        const vec<bfloat, 4> gw = gate_row_values[0];
        const device vec<bfloat, 4>* up_row_values =
            (const device vec<bfloat, 4>*) (
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
""",
    ensureRowContiguous: true
)

private func layer0GateUpBaseline(_ input: MLXArray, fusedWeight: MLXArray) -> MLXArray {
    layer0GateUpBaselineKernel(
        [input, fusedWeight],
        grid: ((8192 / 64) * 512, 1, 1),
        threadGroup: (512, 1, 1),
        outputShapes: [[1, 1, 8192]],
        outputDTypes: [.bfloat16]
    )[0]
}

private func gateUpRowHits(rowsPerGroup: Int, threadGroup: Int) -> [Int] {
    var hits = Array(repeating: 0, count: 8192)
    let simdGroups = threadGroup / 32
    for tile in 0..<(8192 / rowsPerGroup) {
        for simdGroup in 0..<simdGroups {
            let rowBase = tile * rowsPerGroup + simdGroup * 4
            for row in 0..<4 {
                hits[rowBase + row] += 1
            }
        }
    }
    return hits
}

private func durationSeconds(_ duration: Duration) -> Double {
    let components = duration.components
    return Double(components.seconds)
        + Double(components.attoseconds) / 1_000_000_000_000_000_000
}

private func measureGateUp(
    iterations: Int,
    operation: () -> MLXArray
) -> Double {
    let clock = ContinuousClock()
    let start = clock.now
    for _ in 0..<iterations {
        eval(operation())
    }
    return durationSeconds(start.duration(to: clock.now)) / Double(iterations)
}

@Suite
struct Layer0GateUpRetileDiagnosticTests {
    @Test
    func rowMappingCoversEveryOutputExactlyOnce() {
        #expect(gateUpRowHits(rowsPerGroup: 64, threadGroup: 512).allSatisfy { $0 == 1 })
        #expect(gateUpRowHits(rowsPerGroup: 32, threadGroup: 256).allSatisfy { $0 == 1 })
    }

    @Test
    func candidateMatchesBaselineBitwiseAndReportsTiming() {
        guard ProcessInfo.processInfo.environment["MLXFAST_RUN_MLX_RUNTIME_TESTS"] == "1"
        else {
            return
        }

        let columns = MLXArray(0..<2048).asType(.float32).reshaped([1, 1, 2048])
        let weightColumns = MLXArray(0..<2048).asType(.float32).reshaped([1, 2048])
        let weightRows = MLXArray(0..<16384).asType(.float32).reshaped([16384, 1])
        let input = (
            sin(columns * 0.017) * 0.125
                + cos(columns * 0.003) * 0.03125
        ).asType(.bfloat16)
        let fusedWeight = (
            sin(weightRows * 0.011 + weightColumns * 0.007) * 0.0625
                + cos(weightRows * 0.003 - weightColumns * 0.005) * 0.03125
        ).asType(.bfloat16)
        eval(input, fusedWeight)

        let baseline = layer0GateUpBaseline(input, fusedWeight: fusedWeight)
        let candidate = lagunaDenseGateUpSwiGLU(input, fusedWeight: fusedWeight)
        eval(baseline, candidate)
        #expect(isFinite(baseline).all().item(Bool.self))
        #expect(isFinite(candidate).all().item(Bool.self))
        #expect(candidate.dtype == .bfloat16)
        #expect(candidate.shape == [1, 1, 8192])
        #expect(candidate.asArray(Float.self) == baseline.asArray(Float.self))

        let signedInput = (
            cos(columns * 0.029) * 0.25
                - sin(columns * 0.013) * 0.1875
        ).asType(.bfloat16)
        let signedWeight = (-fusedWeight).asType(.bfloat16)
        eval(signedInput, signedWeight)
        let signedBaseline = layer0GateUpBaseline(signedInput, fusedWeight: signedWeight)
        let signedCandidate = lagunaDenseGateUpSwiGLU(signedInput, fusedWeight: signedWeight)
        eval(signedBaseline, signedCandidate)
        #expect(isFinite(signedBaseline).all().item(Bool.self))
        #expect(isFinite(signedCandidate).all().item(Bool.self))
        #expect(signedCandidate.asArray(Float.self) == signedBaseline.asArray(Float.self))

        for _ in 0..<5 {
            eval(layer0GateUpBaseline(input, fusedWeight: fusedWeight))
            eval(lagunaDenseGateUpSwiGLU(input, fusedWeight: fusedWeight))
        }

        let iterations = 60
        let baselineAB = measureGateUp(iterations: iterations) {
            layer0GateUpBaseline(input, fusedWeight: fusedWeight)
        }
        let candidateAB = measureGateUp(iterations: iterations) {
            lagunaDenseGateUpSwiGLU(input, fusedWeight: fusedWeight)
        }
        let candidateBA = measureGateUp(iterations: iterations) {
            lagunaDenseGateUpSwiGLU(input, fusedWeight: fusedWeight)
        }
        let baselineBA = measureGateUp(iterations: iterations) {
            layer0GateUpBaseline(input, fusedWeight: fusedWeight)
        }
        let baselineMean = (baselineAB + baselineBA) / 2
        let candidateMean = (candidateAB + candidateBA) / 2
        print(
            "layer0_gateup_timing iterations=\(iterations) "
                + "baseline_ab_us=\(baselineAB * 1_000_000) "
                + "candidate_ab_us=\(candidateAB * 1_000_000) "
                + "speedup_ab=\(baselineAB / candidateAB) "
                + "candidate_ba_us=\(candidateBA * 1_000_000) "
                + "baseline_ba_us=\(baselineBA * 1_000_000) "
                + "speedup_ba=\(baselineBA / candidateBA) "
                + "baseline_mean_us=\(baselineMean * 1_000_000) "
                + "candidate_mean_us=\(candidateMean * 1_000_000) "
                + "speedup_mean=\(baselineMean / candidateMean)"
        )
    }
}
