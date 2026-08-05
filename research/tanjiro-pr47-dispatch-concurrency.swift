// Research-only probe (PR #47, D1): isolated per-dispatch cost of a Metal
// compute dispatch in the two regimes MLX can produce, so the 5.8x
// chained/unchained bracket on the M5 dispatch law can be collapsed.
//
// Build and run:
//   xcrun swiftc -O research/tanjiro-pr47-dispatch-concurrency.swift -o /tmp/dispconc
//   /tmp/dispconc [rounds] [opsPerCB] [tg] [fitFrom]
//
// It replicates MLX's encoder semantics exactly, from
// Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp:
//   * every compute encoder is created with DispatchTypeConcurrent (:548),
//   * a memoryBarrier(BarrierScopeBuffers) is emitted before a dispatch whose
//     input buffer was written by an earlier dispatch in the same encoder
//     (:325-330 set_input_array, :363-375 maybeInsertBarrier, :380 dispatch),
//   * each encoder updates its own fence and the next encoder waits on that
//     fence when it reads a buffer an earlier encoder wrote (:396-450),
//   * a command buffer is committed once buffer_ops_ exceeds
//     max_ops_per_buffer (:484-487, :574-595; 50 on an `*s` arch).
//
// Arms, all with identical buffer bindings, dispatch count and grid:
//   chained    - dispatch i reads sink[i-1]; barrier before each dispatch;
//                cross-command-buffer fence wait. This is the regime the real
//                decode step runs in (dependent dispatch stream).
//   unchained  - dispatch i reads a host-written control buffer; distinct
//                sinks; no barrier and no fence. The encoder is free to run
//                every dispatch concurrently.
//   serialenc  - DispatchTypeSerial encoder, no barriers, distinct sinks. A
//                second serialisation mechanism, to separate the cost of the
//                barrier instruction from the cost of serialisation itself.
//   barrieronly- concurrent encoder, distinct sinks and no real data
//                dependency, but the same memoryBarrier before each dispatch.
//                Prices the barrier instruction alone.
//   fenceonly  - concurrent encoder, distinct sinks, no barrier, but the same
//                per-command-buffer fence update/wait. Prices the cross
//                command-buffer fence alone.
//   bindchurn  - the chained arm's bindings, so dispatch i still reads the
//                buffer dispatch i-1 wrote, but with no barrier and no fence,
//                so the hazard is never resolved. Together with barrieronly
//                this separates "a barrier instruction", "a rebound input
//                buffer per dispatch" and "a barrier that has a real
//                read-after-write hazard to drain".
//
// Measurement design. Both slope and offset are fitted independently per arm,
// as PR47 D1 requires, and:
//   * GPU clocks are pinned high by a sustained ALU burn before every round.
//     Without it the sub-millisecond points sit in a low DVFS state and total
//     time can *fall* as n rises, which corrupts any slope.
//   * every (arm, n) cell is sampled once per round in a freshly shuffled
//     order, so clock and thermal drift is orthogonal to both arm and n.
//   * one OLS fit per (arm, round) over n >= fitFrom yields independent slope
//     and intercept replicates; the ratio is formed within a round so
//     round-level drift cancels, and its spread over rounds is the CI.

import Foundation
import Metal

let shaderSource = """
#include <metal_stdlib>
using namespace metal;

// Byte-identical in behaviour to laguna_inject_empty_dispatch_v1 in
// Sources/MLXFastModel/LagunaRuntimeModel.swift: the sink write is
// sentinel-gated so it never fires, and `prev` exists only to create the
// read-after-write edge that makes MLX serialise.
kernel void empty_dispatch(device const uint *control [[buffer(0)]],
                           device const uint *prev [[buffer(1)]],
                           device uint *sink [[buffer(2)]],
                           uint gid [[thread_position_in_grid]]) {
    if (control[0] == 0xFFFFFFFFu) {
        sink[gid & 255u] = gid + prev[0];
    }
}

// Sustained ALU load, used only to pin the GPU DVFS state before timing.
kernel void burn(device const uint *control [[buffer(0)]],
                 device float *out [[buffer(1)]],
                 uint gid [[thread_position_in_grid]]) {
    float acc = float(gid) * 1e-6f;
    uint iters = control[1];
    for (uint i = 0; i < iters; ++i) {
        acc = fma(acc, 1.0000001f, 1e-7f);
    }
    out[gid] = acc;
}
"""

enum Arm: String, CaseIterable {
    case chained
    case unchained
    case serialenc
    case barrieronly
    case fenceonly
    case bindchurn

    /// dispatch i reads the sink dispatch i-1 wrote, so the edge is a real RAW.
    var dataDependent: Bool { self == .chained || self == .bindchurn }
    var usesBarrier: Bool { self == .chained || self == .barrieronly }
    var usesFence: Bool { self == .chained || self == .fenceonly }
}

let rounds = CommandLine.arguments.count > 1 ? Int(CommandLine.arguments[1])! : 24
let opsPerCB = CommandLine.arguments.count > 2 ? Int(CommandLine.arguments[2])! : 50
let threadgroups = CommandLine.arguments.count > 3 ? Int(CommandLine.arguments[3])! : 8
let fitFrom = CommandLine.arguments.count > 4 ? Int(CommandLine.arguments[4])! : 800
let counts = [50, 100, 200, 400, 800, 1600, 3200, 6400]

guard let device = MTLCreateSystemDefaultDevice(),
    let queue = device.makeCommandQueue()
else { fatalError("no Metal device") }

let library = try! device.makeLibrary(source: shaderSource, options: nil)
let pso = try! device.makeComputePipelineState(
    function: library.makeFunction(name: "empty_dispatch")!)
let burnPSO = try! device.makeComputePipelineState(function: library.makeFunction(name: "burn")!)

let maxN = counts.max()!
let control = device.makeBuffer(length: 1024, options: .storageModeShared)!
let controlWords = control.contents().bindMemory(to: UInt32.self, capacity: 256)
controlWords[0] = 1  // never the 0xFFFFFFFF sentinel, so the sink write is dead
controlWords[1] = 2048  // burn iterations
let sinks = (0...maxN).map { _ in device.makeBuffer(length: 1024, options: .storageModeShared)! }
let burnOut = device.makeBuffer(length: 1 << 20, options: .storageModePrivate)!
let tgSize = MTLSize(width: 256, height: 1, depth: 1)
let gridSize = MTLSize(width: threadgroups, height: 1, depth: 1)
let burnGrid = MTLSize(width: 512, height: 1, depth: 1)

struct Sample {
    let wall: Double
    let gpuBusy: Double
    let gpuUnion: Double
    let commandBuffers: Int
}

/// Sustained ALU load, to hold the GPU at a high clock state while timing.
func rampGPU(seconds: Double) {
    let t0 = Date()
    while Date().timeIntervalSince(t0) < seconds {
        let cb = queue.makeCommandBuffer()!
        let enc = cb.makeComputeCommandEncoder()!
        enc.setComputePipelineState(burnPSO)
        enc.setBuffer(control, offset: 0, index: 0)
        enc.setBuffer(burnOut, offset: 0, index: 1)
        for _ in 0..<32 { enc.dispatchThreadgroups(burnGrid, threadsPerThreadgroup: tgSize) }
        enc.endEncoding()
        cb.commit()
        cb.waitUntilCompleted()
    }
}

/// One full submission of `n` empty dispatches in `arm`'s regime.
func runOnce(arm: Arm, n: Int) -> Sample {
    var buffers: [MTLCommandBuffer] = []
    buffers.reserveCapacity(n / max(1, opsPerCB) + 2)
    var fence: MTLFence? = nil
    let t0 = Date()

    var i = 0
    while i < n {
        let chunk = min(opsPerCB, n - i)
        let cb = queue.makeCommandBuffer()!
        let enc = cb.makeComputeCommandEncoder(
            dispatchType: arm == .serialenc ? .serial : .concurrent)!
        enc.setComputePipelineState(pso)
        if arm.usesFence, let f = fence { enc.waitForFence(f) }
        for k in 0..<chunk {
            let idx = i + k
            enc.setBuffer(control, offset: 0, index: 0)
            enc.setBuffer(arm.dataDependent ? sinks[idx] : control, offset: 0, index: 1)
            enc.setBuffer(sinks[idx + 1], offset: 0, index: 2)
            if arm.usesBarrier, idx > i { enc.memoryBarrier(scope: .buffers) }
            enc.dispatchThreadgroups(gridSize, threadsPerThreadgroup: tgSize)
        }
        if arm.usesFence {
            let f = device.makeFence()!
            enc.updateFence(f)
            fence = f
        }
        enc.endEncoding()
        cb.commit()
        buffers.append(cb)
        i += chunk
    }
    buffers.last!.waitUntilCompleted()
    let wall = Date().timeIntervalSince(t0)
    let busy = buffers.reduce(0.0) { $0 + ($1.gpuEndTime - $1.gpuStartTime) }
    let union = buffers.map { $0.gpuEndTime }.max()! - buffers.map { $0.gpuStartTime }.min()!
    return Sample(wall: wall, gpuBusy: busy, gpuUnion: union, commandBuffers: buffers.count)
}

func mean(_ xs: [Double]) -> Double { xs.reduce(0, +) / Double(xs.count) }

func median(_ xs: [Double]) -> Double {
    let s = xs.sorted()
    return s.count % 2 == 1 ? s[s.count / 2] : 0.5 * (s[s.count / 2 - 1] + s[s.count / 2])
}

func percentile(_ xs: [Double], _ p: Double) -> Double {
    let s = xs.sorted()
    let r = p * Double(s.count - 1)
    let lo = Int(r.rounded(.down))
    let hi = min(lo + 1, s.count - 1)
    return s[lo] + (r - Double(lo)) * (s[hi] - s[lo])
}

func sd(_ xs: [Double]) -> Double {
    guard xs.count > 1 else { return .nan }
    let m = mean(xs)
    return (xs.reduce(0.0) { $0 + ($1 - m) * ($1 - m) } / Double(xs.count - 1)).squareRoot()
}

/// Ordinary least squares of y on x, returning (slope, intercept).
func ols(_ x: [Double], _ y: [Double]) -> (Double, Double) {
    let mx = mean(x)
    let my = mean(y)
    var sxy = 0.0
    var sxx = 0.0
    for i in 0..<x.count {
        sxy += (x[i] - mx) * (y[i] - my)
        sxx += (x[i] - mx) * (x[i] - mx)
    }
    let slope = sxy / sxx
    return (slope, my - slope * mx)
}

print("device=\(device.name)")
print(
    "rounds=\(rounds) opsPerCB=\(opsPerCB) threadgroups=\(threadgroups) "
        + "threads=\(threadgroups * 256) fitFrom=\(fitFrom)")

var wallCell: [Arm: [Int: [Double]]] = [:]
var unionCell: [Arm: [Int: [Double]]] = [:]
var cbCount: [Int: Int] = [:]

rampGPU(seconds: 2.0)
for arm in Arm.allCases { for n in counts { _ = runOnce(arm: arm, n: n) } }

var rng = SystemRandomNumberGenerator()
for _ in 0..<rounds {
    rampGPU(seconds: 0.35)
    var cells: [(Arm, Int)] = []
    for arm in Arm.allCases { for n in counts { cells.append((arm, n)) } }
    cells.shuffle(using: &rng)
    for (arm, n) in cells {
        let s = runOnce(arm: arm, n: n)
        wallCell[arm, default: [:]][n, default: []].append(s.wall * 1e6)
        unionCell[arm, default: [:]][n, default: []].append(s.gpuUnion * 1e6)
        cbCount[n] = s.commandBuffers
    }
}

print("")
print("per-cell medians (us per dispatch), n_rounds=\(rounds)")
print("arm        n      cb  wall_us/disp  union_us/disp   wall_ms  wall_cv%")
for arm in Arm.allCases {
    for n in counts {
        let w = wallCell[arm]![n]!
        let u = unionCell[arm]![n]!
        print(
            String(
                format: "%-9s %5d %6d %13.4f %14.4f %9.3f %9.2f",
                (arm.rawValue as NSString).utf8String!, n, cbCount[n]!,
                median(w) / Double(n), median(u) / Double(n), median(w) / 1e3,
                100.0 * sd(w) / mean(w)))
    }
}

let fitCounts = counts.filter { $0 >= fitFrom }
let xs = fitCounts.map(Double.init)
var slopes: [Arm: [Double]] = [:]
var icpts: [Arm: [Double]] = [:]
for arm in Arm.allCases {
    for r in 0..<rounds {
        let (s, b) = ols(xs, fitCounts.map { wallCell[arm]![$0]![r] })
        slopes[arm, default: []].append(s)
        icpts[arm, default: []].append(b)
    }
}

print("")
print("per-round independent OLS on wall time over n = \(fitCounts)")
print("arm        slope_us/disp   slope_sd      slope_95CI       icpt_us         icpt_95CI")
for arm in Arm.allCases {
    let s = slopes[arm]!
    let b = icpts[arm]!
    print(
        String(
            format: "%-9s %13.4f %10.4f [%6.4f, %6.4f] %11.1f [%8.1f, %8.1f]",
            (arm.rawValue as NSString).utf8String!, median(s), sd(s),
            percentile(s, 0.025), percentile(s, 0.975), median(b),
            percentile(b, 0.025), percentile(b, 0.975)))
}

// The ratio is formed inside a round, so any round-level clock or thermal
// drift divides out before the distribution is taken.
print("")
print("slope ratio vs the unchained arm, paired within each round")
print("arm            ratio_median   ratio_mean   ratio_sd        ratio_95CI")
for arm in Arm.allCases where arm != .unchained {
    let rs = (0..<rounds).map { slopes[arm]![$0] / slopes[.unchained]![$0] }
    print(
        String(
            format: "%-13s %12.4f %12.4f %10.4f [%6.4f, %6.4f]",
            (arm.rawValue as NSString).utf8String!, median(rs), mean(rs), sd(rs),
            percentile(rs, 0.025), percentile(rs, 0.975)))
}
