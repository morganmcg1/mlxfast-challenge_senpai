// Stage 2 of PR #300: price the redundant RMSNorm reduction.
//
// The shipped fused norm+affine QKV kernel (LagunaRuntimeModel.swift:4910-4970,
// dispatched at :5301-5357) runs a 64-thread threadgroup that virtualises the
// native 512-lane reduction tree, then produces 8 QKV output rows. Every
// threadgroup redundantly re-reduces the same 2048-wide hidden row.
//
// Reverting to the native 2-rows-per-threadgroup geometry of the unfused
// projection (LagunaRuntimeModel.swift:4815-4877) would multiply the number of
// redundant reductions by 4x. This harness prices exactly that delta: a
// reduction-only kernel (verbatim prologue, no matmul) dispatched at the real
// current and proposed threadgroup counts.
//
// Build:
//   swiftc -O research/fern_redundant_rmsnorm_cost.swift \
//     -o /tmp/fern_rmsnorm_cost -framework Metal -framework Foundation
// Run:
//   /tmp/fern_rmsnorm_cost [reps] [out.json]
//
// MLX compiles JIT kernels with fast math DISABLED
// (Vendor/mlx-swift/.../backend/metal/device.cpp:631); this harness matches.

import Foundation
import Metal

// MARK: - model geometry (Sources/MLXFastModel/LagunaConfig.swift)

let hiddenSize = 2048
let headDim = 128
let numKeyValueHeads = 8
let kvRows = 2 * numKeyValueHeads * headDim  // 2048
let slidingHeads = 64
let fullHeads = 48
let slidingLayers = 30
let fullLayers = 10

// gating_types is per_head for all 40 layers, so gate rows == head count and
// the fused QKV bank carries them.
let slidingRows = slidingHeads * headDim + kvRows + slidingHeads  // 10304
let fullRows = fullHeads * headDim + kvRows + fullHeads  // 8240

let currentRowsPerTG = 8  // num_simdgroups(2) * results_per_simdgroup(4)
let nativeRowsPerTG = 2  // unfused laguna_decode_nvfp4_qkv_r1: num_simdgroups(2)

// MARK: - kernel source

// Verbatim reduction prologue from lagunaNormAffineQKVBody:4937-4966, with the
// projection body removed and the reduced value written out so it survives DCE.
let kernelSource = """
#include <metal_stdlib>
#include <metal_simdgroup>
using namespace metal;

kernel void redundant_norm_only(
    const device bfloat* residual [[buffer(0)]],
    device float* out [[buffer(1)]],
    uint3 threadgroup_position_in_grid [[threadgroup_position_in_grid]],
    uint3 thread_position_in_threadgroup [[thread_position_in_threadgroup]],
    uint simdgroup_index_in_threadgroup [[simdgroup_index_in_threadgroup]],
    uint thread_index_in_simdgroup [[thread_index_in_simdgroup]])
{
    constexpr uint axis_size = 2048;
    constexpr uint n_reads = 4;
    constexpr uint norm_threads = axis_size / n_reads;
    constexpr uint real_threads = 64;
    constexpr uint virtual_per_thread = norm_threads / real_threads;
    constexpr uint simd_size = 32;
    constexpr float norm_eps = 1.0e-6f;
    constexpr uint num_simdgroups = 2;

    uint tile = threadgroup_position_in_grid.x;
    uint lid = thread_position_in_threadgroup.x;
    uint simd_gid = simdgroup_index_in_threadgroup;
    uint simd_lid = thread_index_in_simdgroup;

    threadgroup float local_inv_mean[1];
    threadgroup float local_sums[simd_size];

    if (lid < simd_size) {
        local_sums[lid] = 0.0f;
    }
    threadgroup_barrier(mem_flags::mem_threadgroup);

    for (uint j = 0; j < virtual_per_thread; ++j) {
        uint base = (lid + j * real_threads) * n_reads;
        float acc = 0.0f;
        for (uint i = 0; i < n_reads; ++i) {
            float xi = float(residual[base + i]);
            acc += xi * xi;
        }
        acc = simd_sum(acc);
        if (simd_lid == 0) {
            local_sums[simd_gid + num_simdgroups * j] = acc;
        }
    }
    threadgroup_barrier(mem_flags::mem_threadgroup);

    if (simd_gid == 0) {
        float total = simd_sum(local_sums[simd_lid]);
        if (simd_lid == 0) {
            local_inv_mean[0] =
                metal::precise::rsqrt(total / float(axis_size) + norm_eps);
        }
    }
    threadgroup_barrier(mem_flags::mem_threadgroup);

    if (lid == 0) {
        out[tile] = local_inv_mean[0];
    }
}

// Launch-and-schedule floor: same grid, same threadgroup width, no reduction.
kernel void empty_tg(
    const device bfloat* residual [[buffer(0)]],
    device float* out [[buffer(1)]],
    uint3 threadgroup_position_in_grid [[threadgroup_position_in_grid]],
    uint3 thread_position_in_threadgroup [[thread_position_in_threadgroup]])
{
    if (thread_position_in_threadgroup.x == 0) {
        out[threadgroup_position_in_grid.x] = float(residual[0]);
    }
}
"""

// MARK: - bf16 helpers

func bf16Bits(_ f: Float) -> UInt16 {
    let bits = f.bitPattern
    let lsb = (bits >> 16) & 1
    let rounded = bits &+ 0x7FFF &+ lsb
    return UInt16(truncatingIfNeeded: rounded >> 16)
}

struct SplitMix64 {
    var state: UInt64
    mutating func next() -> UInt64 {
        state = state &+ 0x9E37_79B9_7F4A_7C15
        var z = state
        z = (z ^ (z >> 30)) &* 0xBF58_476D_1CE4_E5B9
        z = (z ^ (z >> 27)) &* 0x94D0_49BB_1331_11EB
        return z ^ (z >> 31)
    }
    mutating func normal() -> Float {
        let u1 = max(Float(next() >> 11) * 0x1p-53, 1e-9)
        let u2 = Float(next() >> 11) * 0x1p-53
        return sqrtf(-2 * logf(u1)) * cosf(2 * .pi * u2)
    }
}

// MARK: - setup

guard let device = MTLCreateSystemDefaultDevice() else {
    FileHandle.standardError.write("no Metal device\n".data(using: .utf8)!)
    exit(1)
}
let queue = device.makeCommandQueue()!

let options = MTLCompileOptions()
options.fastMathEnabled = false
let library: MTLLibrary
do {
    library = try device.makeLibrary(source: kernelSource, options: options)
} catch {
    FileHandle.standardError.write("compile failed: \(error)\n".data(using: .utf8)!)
    exit(1)
}

let normPipeline = try! device.makeComputePipelineState(
    function: library.makeFunction(name: "redundant_norm_only")!)
let emptyPipeline = try! device.makeComputePipelineState(
    function: library.makeFunction(name: "empty_tg")!)

var rng = SplitMix64(state: 0x5EED_1234_ABCD_0002)
var rowBits = [UInt16](repeating: 0, count: hiddenSize)
for i in 0..<hiddenSize { rowBits[i] = bf16Bits(rng.normal() * 0.35) }
let residualBuffer = device.makeBuffer(
    bytes: rowBits, length: hiddenSize * 2, options: .storageModeShared)!

let maxTGs = 1 << 14
let outBuffer = device.makeBuffer(
    length: maxTGs * MemoryLayout<Float>.size, options: .storageModeShared)!

// MARK: - measurement

struct Config {
    let name: String
    let tgs: Int
    let pipeline: MTLComputePipelineState
}

/// One command buffer holding `reps` back-to-back dispatches of one config.
/// GPU start/end timestamps exclude CPU encode time.
func timeBuffer(_ config: Config, reps: Int) -> Double {
    let cb = queue.makeCommandBuffer()!
    let enc = cb.makeComputeCommandEncoder()!
    enc.setComputePipelineState(config.pipeline)
    enc.setBuffer(residualBuffer, offset: 0, index: 0)
    enc.setBuffer(outBuffer, offset: 0, index: 1)
    for _ in 0..<reps {
        enc.dispatchThreadgroups(
            MTLSize(width: config.tgs, height: 1, depth: 1),
            threadsPerThreadgroup: MTLSize(width: 64, height: 1, depth: 1))
    }
    enc.endEncoding()
    cb.commit()
    cb.waitUntilCompleted()
    return (cb.gpuEndTime - cb.gpuStartTime) * 1e6 / Double(reps)
}

func mean(_ xs: [Double]) -> Double { xs.reduce(0, +) / Double(xs.count) }
func stderrOf(_ xs: [Double]) -> Double {
    guard xs.count > 1 else { return 0 }
    let m = mean(xs)
    let v = xs.map { ($0 - m) * ($0 - m) }.reduce(0, +) / Double(xs.count - 1)
    return sqrt(v / Double(xs.count))
}

let reps = CommandLine.arguments.count > 1 ? Int(CommandLine.arguments[1])! : 400
let outPath = CommandLine.arguments.count > 2 ? CommandLine.arguments[2] : nil

let configs: [Config] = [
    Config(name: "sliding_current_1288", tgs: slidingRows / currentRowsPerTG, pipeline: normPipeline),
    Config(name: "sliding_native_5152", tgs: slidingRows / nativeRowsPerTG, pipeline: normPipeline),
    Config(name: "full_current_1030", tgs: fullRows / currentRowsPerTG, pipeline: normPipeline),
    Config(name: "full_native_4120", tgs: fullRows / nativeRowsPerTG, pipeline: normPipeline),
    Config(name: "empty_sliding_current_1288", tgs: slidingRows / currentRowsPerTG, pipeline: emptyPipeline),
    Config(name: "empty_sliding_native_5152", tgs: slidingRows / nativeRowsPerTG, pipeline: emptyPipeline),
    Config(name: "empty_full_current_1030", tgs: fullRows / currentRowsPerTG, pipeline: emptyPipeline),
    Config(name: "empty_full_native_4120", tgs: fullRows / nativeRowsPerTG, pipeline: emptyPipeline),
]

print("host reps/buffer=\(reps) fastMath=disabled")
print("rows sliding=\(slidingRows) full=\(fullRows)")
for c in configs where c.pipeline === normPipeline {
    print("  \(c.name): \(c.tgs) threadgroups x 64 threads")
}

// Warm up every pipeline/grid before any recorded sample.
for c in configs { _ = timeBuffer(c, reps: 32) }

// ABBA sweep: forward then reverse order per round cancels monotone drift.
let rounds = 6
var samples: [String: [Double]] = [:]
for round in 0..<rounds {
    let order = round % 2 == 0 ? configs : configs.reversed()
    for c in order {
        samples[c.name, default: []].append(timeBuffer(c, reps: reps))
    }
}

struct Stat { let mean: Double; let se: Double }
var stats: [String: Stat] = [:]
for (k, v) in samples { stats[k] = Stat(mean: mean(v), se: stderrOf(v)) }

print("\n=== per-dispatch GPU microseconds (n=\(rounds) buffers of \(reps) dispatches) ===")
for c in configs {
    let s = stats[c.name]!
    print(String(format: "  %-28s %8.3f us  +/- %.3f", (c.name as NSString).utf8String!, s.mean, s.se))
}

// Reduction-only cost = norm kernel minus the same-grid empty kernel.
func net(_ name: String) -> (Double, Double) {
    let a = stats[name]!
    let b = stats["empty_" + name]!
    return (a.mean - b.mean, sqrt(a.se * a.se + b.se * b.se))
}

let (sCur, sCurSE) = net("sliding_current_1288")
let (sNat, sNatSE) = net("sliding_native_5152")
let (fCur, fCurSE) = net("full_current_1030")
let (fNat, fNatSE) = net("full_native_4120")

print("\n=== reduction-only cost (norm kernel - empty kernel at same grid) ===")
print(String(format: "  sliding current (1288 tg): %7.3f us +/- %.3f", sCur, sCurSE))
print(String(format: "  sliding native  (5152 tg): %7.3f us +/- %.3f", sNat, sNatSE))
print(String(format: "  full    current (1030 tg): %7.3f us +/- %.3f", fCur, fCurSE))
print(String(format: "  full    native  (4120 tg): %7.3f us +/- %.3f", fNat, fNatSE))

let slidingDelta = sNat - sCur
let fullDelta = fNat - fCur
let slidingDeltaSE = sqrt(sNatSE * sNatSE + sCurSE * sCurSE)
let fullDeltaSE = sqrt(fNatSE * fNatSE + fCurSE * fCurSE)

// One decode step runs the fused QKV once per layer.
let perStep = Double(slidingLayers) * slidingDelta + Double(fullLayers) * fullDelta
let perStepSE = sqrt(
    pow(Double(slidingLayers) * slidingDeltaSE, 2) + pow(Double(fullLayers) * fullDeltaSE, 2))

// Total redundant-reduction cost already paid at the current geometry.
let perStepCurrent = Double(slidingLayers) * sCur + Double(fullLayers) * fCur
let perStepCurrentSE = sqrt(
    pow(Double(slidingLayers) * sCurSE, 2) + pow(Double(fullLayers) * fCurSE, 2))

print("\n=== per decode step (30 sliding + 10 full fused QKV dispatches) ===")
print(String(format: "  redundant reduction already paid today: %8.3f us +/- %.3f",
             perStepCurrent, perStepCurrentSE))
print(String(format: "  EXTRA cost of 2-rows/TG native geometry: %8.3f us +/- %.3f",
             perStep, perStepSE))

let threshold = 25.0
let verdict = perStep < threshold ? "PURSUE" : "KILL"
print(String(format: "\nDECISION (< %.1f us/step => pursue): %@ (%.3f us/step)",
             threshold, verdict, perStep))

if let outPath {
    var json: [String: Any] = [
        "reps_per_buffer": reps,
        "rounds": rounds,
        "sliding_rows": slidingRows,
        "full_rows": fullRows,
        "sliding_tg_current": slidingRows / currentRowsPerTG,
        "sliding_tg_native": slidingRows / nativeRowsPerTG,
        "full_tg_current": fullRows / currentRowsPerTG,
        "full_tg_native": fullRows / nativeRowsPerTG,
        "reduction_us_sliding_current": sCur,
        "reduction_us_sliding_current_se": sCurSE,
        "reduction_us_sliding_native": sNat,
        "reduction_us_sliding_native_se": sNatSE,
        "reduction_us_full_current": fCur,
        "reduction_us_full_current_se": fCurSE,
        "reduction_us_full_native": fNat,
        "reduction_us_full_native_se": fNatSE,
        "per_step_current_us": perStepCurrent,
        "per_step_current_us_se": perStepCurrentSE,
        "per_step_extra_us": perStep,
        "per_step_extra_us_se": perStepSE,
        "decision_threshold_us": threshold,
        "decision": verdict,
    ]
    for c in configs {
        json["raw_us_" + c.name] = stats[c.name]!.mean
        json["raw_se_" + c.name] = stats[c.name]!.se
        json["samples_" + c.name] = samples[c.name]!
    }
    let data = try! JSONSerialization.data(
        withJSONObject: json, options: [.prettyPrinted, .sortedKeys])
    try! data.write(to: URL(fileURLWithPath: outPath))
    print("wrote \(outPath)")
}
