// Barrier-cost probe: absolute ns per in-kernel rendezvous vs threadgroup width.
//
// PR #66 (maple-2026-08-05i-barrier-scope-narrowing), Step 1(a).
// Research-only: NOT on benchmark.json's editablePaths, never compiled by a
// scored build.
//
// Build & run:
//   xcrun swiftc -O research/tanjiro_barrier_cost_probe.swift -o /tmp/tjbar \
//       -framework Metal -framework Foundation && /tmp/tjbar
//
// Env knobs:
//   MLXFAST_GPU_CORES=<n>   override detected GPU core count
//   TJ_REPS=<n>             timed reps per config (default 9, median reported)
//   TJ_WAVES=<n>            threadgroups dispatched = n * cores (default 1)
//
// Method
// ------
// Three arms share one kernel body; only the rendezvous flavour differs:
//   none : no barrier
//   sg   : simdgroup_barrier(mem_flags::mem_threadgroup)
//   tg   : threadgroup_barrier(mem_flags::mem_threadgroup)
// The body is a rotate-by-one exchange through threadgroup memory, indexed so
// writer and reader are always in the SAME simdgroup. That keeps every arm
// semantically valid (the `sg` and `none` arms are correct on Apple's lockstep
// simdgroups) so the three are genuinely comparable, and it is exactly the
// traffic pattern that makes a site scope-narrowable in the census.
//
// Cost is extracted as a SLOPE over loop trip count, not as a single absolute
// time. Slope cancels launch overhead, pipeline setup, and the fixed cost of
// the exchange body, leaving ns per loop iteration. Two barriers execute per
// iteration, so
//     ns/threadgroup_barrier = (slope_tg  - slope_none) / 2
//     ns/simdgroup_barrier   = (slope_sg  - slope_none) / 2
//     narrowing saving       = (slope_tg  - slope_sg  ) / 2
// All are per threadgroup per wave, at one resident wave, which is the unit
// that maps onto a real dispatch's wall cost.

import Foundation
import Metal

let stderrHandle = FileHandle.standardError

func log(_ s: String) { print(s); fflush(stdout) }
func die(_ s: String) -> Never {
    stderrHandle.write(("FATAL: " + s + "\n").data(using: .utf8)!); exit(1)
}
func env(_ k: String) -> String? {
    guard let v = ProcessInfo.processInfo.environment[k], !v.isEmpty else { return nil }
    return v
}
func fmt(_ v: Double, _ d: Int = 3) -> String { String(format: "%.\(d)f", v) }
func pad(_ s: String, _ w: Int) -> String {
    s.count >= w ? s : String(repeating: " ", count: w - s.count) + s
}

func run(_ path: String, _ args: [String]) -> (Int32, String) {
    let p = Process()
    p.executableURL = URL(fileURLWithPath: path)
    p.arguments = args
    let pipe = Pipe()
    p.standardOutput = pipe
    p.standardError = pipe
    do { try p.run() } catch { return (-1, "spawn failed: \(error)") }
    let data = pipe.fileHandleForReading.readDataToEndOfFile()
    p.waitUntilExit()
    return (p.terminationStatus, String(data: data, encoding: .utf8) ?? "")
}

func detectCores() -> (Int, String) {
    if let s = env("MLXFAST_GPU_CORES"), let n = Int(s) { return (n, "MLXFAST_GPU_CORES override") }
    let (st, out) = run("/usr/sbin/system_profiler", ["SPDisplaysDataType"])
    if st == 0 {
        for line in out.split(separator: "\n") where line.contains("Total Number of Cores") {
            let digits = line.filter { $0.isNumber }
            if let n = Int(digits) { return (n, "system_profiler SPDisplaysDataType") }
        }
    }
    return (0, "UNDETECTED")
}

func sysctlString(_ name: String) -> String {
    var size = 0
    sysctlbyname(name, nil, &size, nil, 0)
    guard size > 0 else { return "?" }
    var buf = [CChar](repeating: 0, count: size)
    sysctlbyname(name, &buf, &size, nil, 0)
    return String(cString: buf)
}

guard let device = MTLCreateSystemDefaultDevice() else { die("no Metal device") }
guard let queue = device.makeCommandQueue() else { die("no command queue") }
let (cores, coresSource) = detectCores()
guard cores > 0 else { die("GPU core count undetected; set MLXFAST_GPU_CORES") }

let reps = Int(env("TJ_REPS") ?? "") ?? 9
let waves = Int(env("TJ_WAVES") ?? "") ?? 1

log("""
=== tanjiro barrier-cost probe (PR #66 Step 1a) ===
device      : \(device.name)
gpu cores   : \(cores)  [\(coresSource)]
machine     : \(sysctlString("hw.model")) / \(sysctlString("kern.osproductversion"))
reps        : \(reps)   waves: \(waves)  (threadgroups = \(waves * cores))
""")

// MARK: - kernel

enum Arm: String, CaseIterable {
    case none, sg, tg

    var barrier: String {
        switch self {
        case .none: return ""
        case .sg: return "simdgroup_barrier(mem_flags::mem_threadgroup);"
        case .tg: return "threadgroup_barrier(mem_flags::mem_threadgroup);"
        }
    }
}

func source(width: Int, arm: Arm) -> String {
    """
    #include <metal_stdlib>
    using namespace metal;

    kernel void bar_probe(
        device const float* inbuf [[buffer(0)]],
        device float*       out   [[buffer(1)]],
        constant uint&      iters [[buffer(2)]],
        uint tid [[thread_position_in_threadgroup]],
        uint gid [[threadgroup_position_in_grid]])
    {
        threadgroup float tg[\(width)];
        const uint lane    = tid & 31u;
        const uint sgbase  = tid & ~31u;
        const uint partner = sgbase + ((lane + 1u) & 31u);
        float acc = inbuf[tid] + float(gid) * 1e-7f;
        for (uint i = 0; i < iters; ++i) {
            tg[tid] = acc;
            \(arm.barrier)
            float v = tg[partner];
            \(arm.barrier)
            acc = fma(v, 1.0000001f, 1e-9f);
        }
        out[gid * \(width) + tid] = acc;
    }
    """
}

let heaterSource = """
#include <metal_stdlib>
using namespace metal;
kernel void heater(device float* out [[buffer(0)]], uint t [[thread_position_in_grid]]) {
    float a = float(t) * 1e-6f;
    for (uint i = 0; i < 4096u; ++i) { a = fma(a, 1.0000001f, 1e-7f); }
    if (a == 12345.678f) out[0] = a;
}
"""

let iterList = [256, 1024, 4096]
let widths = [32, 64, 128, 256, 512, 1024]

let maxWidth = widths.max()!
let tgCount = waves * cores
guard let inBuf = device.makeBuffer(length: maxWidth * 4, options: .storageModeShared),
      let outBuf = device.makeBuffer(length: tgCount * maxWidth * 4, options: .storageModeShared)
else { die("buffer alloc failed") }
do {
    let p = inBuf.contents().bindMemory(to: Float.self, capacity: maxWidth)
    for i in 0..<maxWidth { p[i] = Float(i) * 0.5 + 1.0 }
}

// The GPU ramps clocks over milliseconds, and `makeLibrary` is a long CPU-only
// stall that lets it drop back down. Compiling every pipeline up front and
// running a heater dispatch immediately before each timed one removes an order
// effect that otherwise reads as a 2.7x width effect at the head of the sweep.
let heaterPipe: MTLComputePipelineState = {
    guard let lib = try? device.makeLibrary(source: heaterSource, options: nil),
          let fn = lib.makeFunction(name: "heater"),
          let p = try? device.makeComputePipelineState(function: fn)
    else { die("heater pipeline failed") }
    return p
}()

func heat(milliseconds: Int) {
    let deadline = Date().addingTimeInterval(Double(milliseconds) / 1000.0)
    repeat {
        guard let cb = queue.makeCommandBuffer(), let enc = cb.makeComputeCommandEncoder() else { return }
        enc.setComputePipelineState(heaterPipe)
        enc.setBuffer(outBuf, offset: 0, index: 0)
        enc.dispatchThreads(MTLSize(width: cores * 4096, height: 1, depth: 1),
                            threadsPerThreadgroup: MTLSize(width: 256, height: 1, depth: 1))
        enc.endEncoding()
        cb.commit()
        cb.waitUntilCompleted()
    } while Date() < deadline
}

/// Median GPU-side seconds for one dispatch of `pipe` at `iters` trip count.
func timeOne(_ pipe: MTLComputePipelineState, width: Int, iters: Int) -> Double {
    var itersVal = UInt32(iters)
    var samples: [Double] = []
    for r in 0..<(reps + 2) {  // 2 warmups
        heat(milliseconds: 12)
        guard let cb = queue.makeCommandBuffer(), let enc = cb.makeComputeCommandEncoder() else {
            die("encoder failed")
        }
        enc.setComputePipelineState(pipe)
        enc.setBuffer(inBuf, offset: 0, index: 0)
        enc.setBuffer(outBuf, offset: 0, index: 1)
        enc.setBytes(&itersVal, length: 4, index: 2)
        enc.dispatchThreadgroups(MTLSize(width: tgCount, height: 1, depth: 1),
                                 threadsPerThreadgroup: MTLSize(width: width, height: 1, depth: 1))
        enc.endEncoding()
        cb.commit()
        cb.waitUntilCompleted()
        if let e = cb.error { die("cb error: \(e)") }
        if r >= 2 { samples.append(cb.gpuEndTime - cb.gpuStartTime) }
    }
    samples.sort()
    return samples[samples.count / 2]
}

/// Least-squares slope (seconds per loop iteration) of time vs trip count.
func slope(_ pts: [(Int, Double)]) -> Double {
    let n = Double(pts.count)
    let sx = pts.reduce(0.0) { $0 + Double($1.0) }
    let sy = pts.reduce(0.0) { $0 + $1.1 }
    let sxx = pts.reduce(0.0) { $0 + Double($1.0) * Double($1.0) }
    let sxy = pts.reduce(0.0) { $0 + Double($1.0) * $1.1 }
    return (n * sxy - sx * sy) / (n * sxx - sx * sx)
}

// Compile every pipeline before any timing so no CPU-side compile stall lands
// inside the sweep.
var pipes: [Int: [Arm: MTLComputePipelineState]] = [:]
for width in widths {
    var byArm: [Arm: MTLComputePipelineState] = [:]
    for arm in Arm.allCases {
        let lib: MTLLibrary
        do { lib = try device.makeLibrary(source: source(width: width, arm: arm), options: nil) }
        catch { die("compile w=\(width) arm=\(arm.rawValue): \(error)") }
        guard let fn = lib.makeFunction(name: "bar_probe") else { die("no bar_probe") }
        let pipe: MTLComputePipelineState
        do { pipe = try device.makeComputePipelineState(function: fn) }
        catch { die("pipeline w=\(width) arm=\(arm.rawValue): \(error)") }
        guard pipe.maxTotalThreadsPerThreadgroup >= width else {
            log("width \(width) arm \(arm.rawValue): SKIP (maxTotalThreadsPerThreadgroup=\(pipe.maxTotalThreadsPerThreadgroup))")
            continue
        }
        byArm[arm] = pipe
    }
    pipes[width] = byArm
}
log("compiled \(pipes.values.reduce(0) { $0 + $1.count }) pipelines; heating GPU 800 ms")
heat(milliseconds: 800)

/// One full sweep. `order` lets a reverse pass falsify any residual order effect.
func sweep(order: [Int], label: String) -> [Int: (tg: Double, sg: Double, narrow: Double)] {
    log("")
    log("--- pass \(label): raw GPU times (us) per dispatch, \(tgCount) threadgroups ---")
    log("width  arm   " + iterList.map { pad("it=\($0)", 12) }.joined() + pad("ns/iter", 12))
    var out: [Int: (tg: Double, sg: Double, narrow: Double)] = [:]
    for width in order {
        var slopes: [Arm: Double] = [:]
        for arm in Arm.allCases {
            guard let pipe = pipes[width]?[arm] else { continue }
            var pts: [(Int, Double)] = []
            for it in iterList { pts.append((it, timeOne(pipe, width: width, iters: it))) }
            let s = slope(pts)
            slopes[arm] = s
            log(pad("\(width)", 5) + "  " + pad(arm.rawValue, 4) + "  "
                + pts.map { pad(fmt($0.1 * 1e6, 2), 12) }.joined()
                + pad(fmt(s * 1e9, 4), 12))
        }
        if let sn = slopes[.none], let ss = slopes[.sg], let st = slopes[.tg] {
            out[width] = ((st - sn) / 2 * 1e9, (ss - sn) / 2 * 1e9, (st - ss) / 2 * 1e9)
        }
    }
    return out
}

let fwd = sweep(order: widths, label: "A (ascending width)")
let rev = sweep(order: widths.reversed(), label: "B (descending width)")

log("")
log("--- ns per barrier per threadgroup (\(waves) wave(s), \(tgCount) TGs) ---")
log("width  simdgroups   ns/tg_barrier(A,B)     ns/sg_barrier(A,B)     ns saved by narrowing(A,B)")
for width in widths {
    guard let a = fwd[width], let b = rev[width] else { continue }
    log(pad("\(width)", 5) + pad("\(width / 32)", 12)
        + pad(fmt(a.tg, 2) + ", " + fmt(b.tg, 2), 22)
        + pad(fmt(a.sg, 2) + ", " + fmt(b.sg, 2), 23)
        + pad(fmt(a.narrow, 2) + ", " + fmt(b.narrow, 2), 28))
}

log("")
log("Interpretation notes:")
log(" * ns/tg_barrier is the ELIMINATION saving upper bound for one barrier at that width.")
log(" * ns saved by narrowing is the threadgroup_barrier -> simdgroup_barrier saving.")
log(" * Multiply by (eligible sites) x (dispatches/decode step) x ceil(TGs/cores) waves")
log("   to get us/step; 1 ms decode = 14.862% of score, so 0.15% needs >= 10.09 us/step.")
