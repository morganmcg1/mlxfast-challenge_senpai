import Foundation
import MLX
import MLXFast
@testable import MLXFastModel
import Testing

@Suite(.serialized)
struct ActivatedOProjTileStagingExperimentTests {
    @Test
    func activatedOProjTileStagingExperiment() throws {
        guard let mode = ProcessInfo.processInfo.environment["MLXFAST_OPROJ_EXPERIMENT"] else {
            return
        }
        switch mode {
        case "exact":
            try runExactness()
        case "timing":
            try runTiming()
        default:
            Issue.record("unknown MLXFAST_OPROJ_EXPERIMENT mode: \(mode)")
        }
    }
}

private struct OProjExperimentCase {
    let heads: Int
    let laneMajor: Bool
    let pairwise: Bool
    let inputs: [MLXArray]
    let baseline: MLXFast.MLXFastKernel
    let staged: MLXFast.MLXFastKernel

    var label: String { "H\(heads)-\(laneMajor ? "lane" : "normal")" }

    func call(_ kernel: MLXFast.MLXFastKernel) -> MLXArray {
        kernel(
            inputs,
            grid: ((4_096 / 8) * 64, 1, 1),
            threadGroup: (64, 1, 1),
            outputShapes: [[1, 1, 4_096]],
            outputDTypes: [.bfloat16]
        )[0]
    }
}

private func runExactness() throws {
    for heads in [48, 64] {
        for laneMajor in [false, true] {
            let experiment = makeExperimentCase(heads: heads, laneMajor: laneMajor)
            let baseline = experiment.call(experiment.baseline)
            let staged = experiment.call(experiment.staged)
            eval(baseline, staged)

            let baselineBits = baseline.asType(.float32).asArray(Float.self).map(\.bitPattern)
            let stagedBits = staged.asType(.float32).asArray(Float.self).map(\.bitPattern)
            #expect(baselineBits == stagedBits, "old/new mismatch for \(experiment.label)")
            #expect(baselineBits.contains { ($0 & 0x7fff_ffff) != 0 })
            print("OPROJ_EXACT label=\(experiment.label) values=\(baselineBits.count) match=true")
        }
    }

    let raw = lagunaGatedAffineOProjNVFP4Source(heads: 48)
    let activated = lagunaGatedAffineOProjNVFP4Source(heads: 48, preActivatedGate: true)
    #expect(raw.components(separatedBy: "threadgroup_barrier").count - 1 == 1)
    #expect(!raw.contains("x_tile"))
    #expect(activated.components(separatedBy: "threadgroup_barrier").count - 1 == 2)
    #expect(activated.components(separatedBy: "threadgroup bfloat x_tile[block_size]").count - 1 == 1)
    print("OPROJ_SOURCE raw_barriers=1 activated_barriers=2 tile_bytes=1024 threads=64")
}

private func runTiming() throws {
    let environment = ProcessInfo.processInfo.environment
    guard let headsText = environment["MLXFAST_OPROJ_HEADS"],
        let heads = Int(headsText), [48, 64].contains(heads)
    else {
        Issue.record("MLXFAST_OPROJ_HEADS must be 48 or 64")
        return
    }
    let laneMajor = environment["MLXFAST_OPROJ_LAYOUT"] == "lane"
    let order = environment["MLXFAST_OPROJ_ORDER"] ?? "AB"
    guard ["AB", "BA"].contains(order) else {
        Issue.record("MLXFAST_OPROJ_ORDER must be AB or BA")
        return
    }

    let experiment = makeExperimentCase(heads: heads, laneMajor: laneMajor)
    for _ in 0..<8 {
        eval(experiment.call(experiment.baseline), experiment.call(experiment.staged))
    }

    var baselineSamples: [Double] = []
    var stagedSamples: [Double] = []
    for _ in 0..<101 {
        if order == "AB" {
            baselineSamples.append(measure(experiment.baseline, experiment: experiment))
            stagedSamples.append(measure(experiment.staged, experiment: experiment))
        } else {
            stagedSamples.append(measure(experiment.staged, experiment: experiment))
            baselineSamples.append(measure(experiment.baseline, experiment: experiment))
        }
    }

    let baselineMedian = median(baselineSamples)
    let stagedMedian = median(stagedSamples)
    let payload: [String: Any] = [
        "label": experiment.label,
        "order": order,
        "samples": 101,
        "dispatches_per_sample": 5,
        "baseline_median_seconds": baselineMedian,
        "staged_median_seconds": stagedMedian,
        "speedup": baselineMedian / stagedMedian,
        "baseline_mad_seconds": median(baselineSamples.map { abs($0 - baselineMedian) }),
        "staged_mad_seconds": median(stagedSamples.map { abs($0 - stagedMedian) }),
        "baseline_samples_seconds": baselineSamples,
        "staged_samples_seconds": stagedSamples,
    ]
    let data = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
    print("OPROJ_TIMING_JSON \(String(decoding: data, as: UTF8.self))")
}

private func makeExperimentCase(heads: Int, laneMajor: Bool) -> OProjExperimentCase {
    let pairwise = true
    let stagedSource = lagunaGatedAffineOProjNVFP4Source(
        heads: heads,
        preActivatedGate: true,
        laneMajor: laneMajor,
        pairwise: pairwise
    )
    let baselineSource = unstagedActivatedSource(stagedSource)
    let suffix = "h\(heads)_\(laneMajor ? "lane" : "normal")"
    let inputNames = laneMajor
        ? ["attention_output", "gate_values", "weight_codes", "scale_nibbles", "scale_bases", "weight_scales"]
        : ["attention_output", "gate_values", "weight_codes", "weight_scales"]
    let baseline = MLXFast.metalKernel(
        name: "oproj_experiment_baseline_\(suffix)",
        inputNames: inputNames,
        outputNames: ["projected"],
        source: baselineSource,
        ensureRowContiguous: true
    )
    let staged = MLXFast.metalKernel(
        name: "oproj_experiment_staged_\(suffix)",
        inputNames: inputNames,
        outputNames: ["projected"],
        source: stagedSource,
        ensureRowContiguous: true
    )
    return OProjExperimentCase(
        heads: heads,
        laneMajor: laneMajor,
        pairwise: pairwise,
        inputs: makeInputs(heads: heads, laneMajor: laneMajor, pairwise: pairwise),
        baseline: baseline,
        staged: staged
    )
}

private func makeInputs(heads: Int, laneMajor: Bool, pairwise: Bool) -> [MLXArray] {
    let inVec = heads * 128
    let attentionSeed: [Float] = [
        0, -0.0, Float(bitPattern: 0x0001_0000), -Float(bitPattern: 0x0001_0000),
        0.0078125, -0.015625, 0.125, -0.25, 0.5, -0.75, 1, -1,
    ]
    let gateSeed: [Float] = [
        0, -0.0, Float(bitPattern: 0x0001_0000), -Float(bitPattern: 0x0001_0000),
        0.03125, -0.0625, 0.25, -0.5, 0.75, -1, 1.5, -2,
    ]
    let attention = MLXArray(
        (0..<inVec).map { i in
            let base = attentionSeed[i % attentionSeed.count]
            return base + Float((i * 17) % 11 - 5) / 256
        },
        [1, 1, inVec]
    ).asType(.bfloat16)
    let gates = MLXArray(
        (0..<heads).map { gateSeed[$0 % gateSeed.count] },
        [1, 1, heads]
    ).asType(.bfloat16)
    let codeWords = (0..<(4_096 * inVec / 8)).map { i -> UInt32 in
        switch i & 3 {
        case 0: return 0x7654_3210
        case 1: return 0xfedc_ba98
        case 2: return 0x1234_5670
        default: return 0x9abc_def8
        }
    }
    let codes = MLXArray(codeWords, [4_096, inVec / 8])
    let scales = MLXArray(
        Array(repeating: UInt8(0x38), count: 4_096 * inVec / 16),
        [4_096, inVec / 16]
    )
    if !laneMajor {
        return [attention, gates, codes, scales]
    }

    let nibbleDivisor = pairwise ? 4 : 2
    let nibbles = MLXArray(
        Array(repeating: UInt8(0), count: 4_096 * inVec / 16 / nibbleDivisor),
        [4_096, inVec / 16 / nibbleDivisor]
    )
    let bases = MLXArray(Array(repeating: UInt8(0x38), count: 4_096), [4_096])
    return [attention, gates, codes, nibbles, bases, scales]
}

private func unstagedActivatedSource(_ source: String) -> String {
    let stagedLoad = """
if (simd_gid == 0) {
    float g=float(gate_values[column>>head_shift]);
    for(uint i=0;i<values_per_thread;++i)
        x_tile[simd_lid*values_per_thread+i]=bfloat(float(xp[i])*g);
}
threadgroup_barrier(mem_flags::mem_threadgroup);
for(uint i=0;i<values_per_thread;++i)
    x_thread[i]=float(x_tile[simd_lid*values_per_thread+i]);
"""
    let baselineLoad = """
float g=float(gate_values[column>>head_shift]);
for(uint i=0;i<values_per_thread;++i)
    x_thread[i]=float(bfloat(float(xp[i])*g));
"""
    var result = source.replacingOccurrences(
        of: "threadgroup bfloat x_tile[block_size];\n",
        with: ""
    )
    result = result.replacingOccurrences(of: stagedLoad, with: baselineLoad)
    result = result.replacingOccurrences(
        of: "\n    threadgroup_barrier(mem_flags::mem_threadgroup);\n    ws += block_size / 8;",
        with: "\n    ws += block_size / 8;"
    )
    precondition(!result.contains("x_tile"))
    precondition(!result.contains("threadgroup_barrier"))
    return result
}

private func measure(
    _ kernel: MLXFast.MLXFastKernel,
    experiment: OProjExperimentCase
) -> Double {
    var outputs: [MLXArray] = []
    outputs.reserveCapacity(5)
    let start = Date.timeIntervalSinceReferenceDate
    for _ in 0..<5 {
        outputs.append(experiment.call(kernel))
    }
    eval(outputs)
    return (Date.timeIntervalSinceReferenceDate - start) / 5
}

private func median(_ values: [Double]) -> Double {
    let sorted = values.sorted()
    return sorted[sorted.count / 2]
}
