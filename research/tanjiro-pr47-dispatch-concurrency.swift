// Research-only probe (PR #47, D1): isolated per-dispatch cost of a Metal
// compute dispatch in the two regimes MLX can produce, so the 5.8x
// chained/unchained bracket on the M5 dispatch law can be collapsed.
//
// Build and run:
//   xcrun swiftc -O research/tanjiro-pr47-dispatch-concurrency.swift -o /tmp/dispconc
//   /tmp/dispconc [reps] [opsPerCB] [tg]
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
"""

enum Arm: String, CaseIterable {
    case chained
    case unchained
    case serialenc
}

let reps = CommandLine.arguments.count > 1 ? Int(CommandLine.arguments[1])! : 15
let opsPerCB = CommandLine.arguments.count > 2 ? Int(CommandLine.arguments[2])! : 50
let threadgroups = CommandLine.arguments.count > 3 ? Int(CommandLine.arguments[3])! : 8
let counts = [50, 100, 200, 400, 800, 1600, 3200]
let warmups = 3

guard let device = MTLCreateSystemDefaultDevice(),
    let queue = device.makeCommandQueue()
else { fatalError("no Metal device") }

let library = try! device.makeLibrary(source: shaderSource, options: nil)
let pso = try! device.makeComputePipelineState(function: library.makeFunction(name: "empty_dispatch")!)

let maxN = counts.max()!
let control = device.makeBuffer(length: 1024, options: .storageModeShared)!
control.contents().bindMemory(to: UInt32.self, capacity: 256).pointee = 1
let sinks = (0...maxN).map { _ in device.makeBuffer(length: 1024, options: .storageModeShared)! }
let tgSize = MTLSize(width: 256, height: 1, depth: 1)
let gridSize = MTLSize(width: threadgroups, height: 1, depth: 1)

struct Sample {
    let wall: Double
    let gpuBusy: Double
    let gpuUnion: Double
    let commandBuffers: Int
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
        if arm == .chained, let f = fence { enc.waitForFence(f) }
        for k in 0..<chunk {
            let idx = i + k
            enc.setBuffer(control, offset: 0, index: 0)
            enc.setBuffer(arm == .chained ? sinks[idx] : control, offset: 0, index: 1)
            enc.setBuffer(sinks[idx + 1], offset: 0, index: 2)
            if arm == .chained, idx > i { enc.memoryBarrier(scope: .buffers) }
            enc.dispatchThreadgroups(gridSize, threadsPerThreadgroup: tgSize)
        }
        if arm == .chained {
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

func median(_ xs: [Double]) -> Double {
    let s = xs.sorted()
    return s.count % 2 == 1 ? s[s.count / 2] : 0.5 * (s[s.count / 2 - 1] + s[s.count / 2])
}

/// Ordinary least squares of y on x, returning (slope, intercept, r2).
func ols(_ x: [Double], _ y: [Double]) -> (Double, Double, Double) {
    let n = Double(x.count)
    let mx = x.reduce(0, +) / n
    let my = y.reduce(0, +) / n
    var sxy = 0.0
    var sxx = 0.0
    var syy = 0.0
    for i in 0..<x.count {
        sxy += (x[i] - mx) * (y[i] - my)
        sxx += (x[i] - mx) * (x[i] - mx)
        syy += (y[i] - my) * (y[i] - my)
    }
    let slope = sxy / sxx
    return (slope, my - slope * mx, (sxy * sxy) / (sxx * syy))
}

print("device=\(device.name) arch_note=see host_device_arch.swift")
print("reps=\(reps) opsPerCB=\(opsPerCB) threadgroups=\(threadgroups) threads=\(threadgroups * 256)")
print("")
print("arm        n     cb  wall_us/disp  union_us/disp  busy_us/disp   wall_ms  union_ms")

var wallByArm: [Arm: [Double]] = [:]
var unionByArm: [Arm: [Double]] = [:]
var busyByArm: [Arm: [Double]] = [:]

// Interleave arms inside each n so any thermal or clock drift is shared.
for n in counts {
    for arm in Arm.allCases {
        for _ in 0..<warmups { _ = runOnce(arm: arm, n: n) }
        var walls: [Double] = []
        var unions: [Double] = []
        var busies: [Double] = []
        var cbs = 0
        for _ in 0..<reps {
            let s = runOnce(arm: arm, n: n)
            walls.append(s.wall)
            unions.append(s.gpuUnion)
            busies.append(s.gpuBusy)
            cbs = s.commandBuffers
        }
        let w = median(walls)
        let u = median(unions)
        let b = median(busies)
        wallByArm[arm, default: []].append(w)
        unionByArm[arm, default: []].append(u)
        busyByArm[arm, default: []].append(b)
        print(
            String(
                format: "%-9s %5d %6d %13.4f %14.4f %13.4f %9.3f %9.3f",
                (arm.rawValue as NSString).utf8String!, n, cbs,
                w * 1e6 / Double(n), u * 1e6 / Double(n), b * 1e6 / Double(n),
                w * 1e3, u * 1e3))
    }
}

print("")
print("OLS over n = \(counts)  (slope = marginal us per dispatch, intercept = us fixed)")
print("arm        wall_slope_us  wall_icpt_us   wall_r2  union_slope_us  union_icpt_us  union_r2")
let xs = counts.map(Double.init)
for arm in Arm.allCases {
    let (ws, wi, wr) = ols(xs, wallByArm[arm]!.map { $0 * 1e6 })
    let (us, ui, ur) = ols(xs, unionByArm[arm]!.map { $0 * 1e6 })
    print(
        String(
            format: "%-9s %14.4f %13.2f %9.5f %15.4f %14.2f %9.5f",
            (arm.rawValue as NSString).utf8String!, ws, wi, wr, us, ui, ur))
}

let (wc, _, _) = ols(xs, wallByArm[.chained]!.map { $0 * 1e6 })
let (wu, _, _) = ols(xs, wallByArm[.unchained]!.map { $0 * 1e6 })
let (uc, _, _) = ols(xs, unionByArm[.chained]!.map { $0 * 1e6 })
let (uu, _, _) = ols(xs, unionByArm[.unchained]!.map { $0 * 1e6 })
print("")
print(String(format: "wall  chained/unchained slope ratio = %.4f", wc / wu))
print(String(format: "union chained/unchained slope ratio = %.4f", uc / uu))
