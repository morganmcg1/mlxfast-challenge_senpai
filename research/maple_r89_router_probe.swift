// R89-A standalone router-kernel probe. Research-only; nothing here ships.
//
// Answers two questions the in-situ decode rig cannot resolve at its 19.5
// us/step within-process sigma:
//
//   1. Occupancy. `maxTotalThreadsPerThreadgroup` per arm. The kernel is
//      dispatched at 512 threads/threadgroup, so any arm below 512 is
//      undispatchable and the register cliff is the answer, not the timing.
//   2. Mechanism. Does AGX keep a `device` load in flight across a
//      `threadgroup_barrier(mem_flags::mem_threadgroup)`? Arm 1 hoists a
//      four-load peel above the four barriers of the RMS reduction tail; arm 5
//      is the character-identical peel left below them. 1 - 5 is the overlap;
//      1 - 0 confounds overlap with peeling.
//   3. Phase durations. Arms 6 and 7 are numerically wrong by construction:
//      6 keeps the reduction and drops the router GEMV, 7 keeps the GEMV and
//      drops the cross-simdgroup reduction. Arm 6's level bounds the window a
//      hoisted load can overlap into, which is the ceiling on mechanism B.
//
// The Metal text is NOT written here. `maple_r89_emit_router_sources.py` runs
// the scored generator and drops `arm{N}.metal` + `header.metal` into a
// directory this probe reads, so probe and runtime cannot diverge.
//
//   xcrun swiftc -O research/maple_r89_router_probe.swift -o /tmp/r89probe
//   /tmp/r89probe /tmp/r89src
//
// Every comparison is an ABBA-interleaved paired difference. Absolute kernel
// times on this host drift ~16% over seconds (see nezuko_epilogue_probe.swift),
// so only paired differences are usable. `null` rows pair a pipeline against an
// independently compiled copy of its own source and must straddle zero.

import Foundation
import Metal

let arms = [0, 1, 2, 3, 4, 5, 6, 7]
let armLabel: [Int: String] = [
    0: "A0 depth0 (shipped)", 1: "A1 depth1 hoisted", 2: "A2 depth2 hoisted",
    3: "A5 depth3 hoisted", 4: "A3 depth4 hoisted (full)",
    5: "A4 depth1 control (below barriers)",
    6: "P-norm  reduction phase only (no router GEMV)",
    7: "P-gemv  router GEMV only (no cross-simd reduction)",
]

let srcDir = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "/tmp/r89src"
let header = try! String(contentsOfFile: srcDir + "/header.metal", encoding: .utf8)

let device = MTLCreateSystemDefaultDevice()!
let queue = device.makeCommandQueue()!

let preamble = """
#include <metal_stdlib>
#include <metal_simdgroup>
using namespace metal;
typedef bfloat bfloat16_t;

"""

func signature(_ name: String) -> String {
    var s = "[[kernel]] void custom_kernel_\(name)(\n"
    s += "  const device bfloat16_t* residual [[buffer(0)]],\n"
    s += "  const device bfloat16_t* branch [[buffer(1)]],\n"
    s += "  const device bfloat16_t* weight [[buffer(2)]],\n"
    s += "  const device bfloat16_t* router_weight [[buffer(3)]],\n"
    s += "  const device float* correction_bias [[buffer(4)]],\n"
    s += "  device bfloat16_t* summed [[buffer(5)]],\n"
    s += "  device bfloat16_t* normalized [[buffer(6)]],\n"
    s += "  device bfloat16_t* router_logits [[buffer(7)]],\n"
    s += "  device uint32_t* router_keys [[buffer(8)]],\n"
    s += "  uint3 thread_position_in_threadgroup [[thread_position_in_threadgroup]],\n"
    s += "  uint thread_index_in_simdgroup [[thread_index_in_simdgroup]],\n"
    s += "  uint simdgroup_index_in_threadgroup [[simdgroup_index_in_threadgroup]],\n"
    s += "  uint3 threadgroup_position_in_grid [[threadgroup_position_in_grid]]) {\n"
    return s
}

func compile(arm: Int, tag: String) -> MTLComputePipelineState {
    let body = try! String(contentsOfFile: srcDir + "/arm\(arm).metal", encoding: .utf8)
    let name = "r89_arm\(arm)\(tag)"
    let msl = preamble + header + "\n" + signature(name) + body + "\n}\n"
    let lib: MTLLibrary
    do { lib = try device.makeLibrary(source: msl, options: nil) } catch {
        fatalError("arm\(arm) compile failed: \(error)")
    }
    let fn = lib.makeFunction(name: "custom_kernel_\(name)")!
    return try! device.makeComputePipelineState(function: fn)
}

// MARK: - buffers

let hidden = 2048
let experts = 256
let weightElems = experts * hidden          // 524,288 bf16 = 1 MiB per copy
let weightCopies = 64                       // 64 MiB, past any SLC residency

func bf16Buffer(_ elements: Int, seed: UInt64) -> MTLBuffer {
    let buf = device.makeBuffer(length: elements * 2, options: .storageModeShared)!
    let p = buf.contents().bindMemory(to: UInt16.self, capacity: elements)
    var s = seed &* 6_364_136_223_846_793_005 &+ 1
    for i in 0..<elements {
        s = s &* 6_364_136_223_846_793_005 &+ 1_442_695_040_888_963_407
        // BF16 near 1.0 with a varying mantissa; magnitudes stay tame.
        p[i] = UInt16(0x3F00 | UInt16(truncatingIfNeeded: s >> 55))
    }
    return buf
}

let dResidual = bf16Buffer(hidden, seed: 1)
let dBranch = bf16Buffer(hidden, seed: 2)
let dWeight = bf16Buffer(hidden, seed: 3)
let dRouterW = bf16Buffer(weightElems * weightCopies, seed: 4)
let dSummed = bf16Buffer(hidden, seed: 5)
let dNormalized = bf16Buffer(hidden, seed: 6)
let dLogits = bf16Buffer(experts, seed: 7)
let dKeys = device.makeBuffer(length: experts * 4, options: .storageModeShared)!
let dBias = device.makeBuffer(length: experts * 4, options: .storageModeShared)!
do {
    let p = dBias.contents().bindMemory(to: Float.self, capacity: experts)
    for i in 0..<experts { p[i] = Float(i % 7) * 0.01 - 0.03 }
}

// MARK: - timing

let tiles = 32          // 256 router rows / rows_per_group 8
let threads = 512
let reps = 256
let rounds = 20         // 10 ABBA + 10 BAAB, see `paired`
let warmupCBs = 60
/// 40 hidden layers, `mlp_only_layers = [0]` -> 39 sparse layers, and the
/// fused kernel is gated on `mlp as? LagunaRuntimeSparseMoEBlock`, so a decode
/// step issues 39 of these dispatches. The second call site is prefill-only.
let callsPerStep = 39.0

/// One command buffer of `reps` serial dispatches. `rotate` advances the
/// `router_weight` binding by one 1 MiB copy per dispatch, so the weight is
/// re-fetched from DRAM instead of being served by the system level cache --
/// which is the regime the real decode step runs in, with 21.6 GB of weights
/// streaming past between two visits to the same router row.
func timeOnce(_ pipe: MTLComputePipelineState, rotate: Bool) -> Double {
    let cb = queue.makeCommandBuffer()!
    let enc = cb.makeComputeCommandEncoder()!
    enc.setComputePipelineState(pipe)
    for (i, b) in [dResidual, dBranch, dWeight, dRouterW, dBias,
                   dSummed, dNormalized, dLogits, dKeys].enumerated() {
        enc.setBuffer(b, offset: 0, index: i)
    }
    enc.setBuffer(dBias, offset: 0, index: 4)
    enc.setBuffer(dKeys, offset: 0, index: 8)
    for r in 0..<reps {
        if rotate {
            enc.setBufferOffset((r % weightCopies) * weightElems * 2, index: 3)
        }
        enc.dispatchThreadgroups(
            MTLSize(width: tiles, height: 1, depth: 1),
            threadsPerThreadgroup: MTLSize(width: threads, height: 1, depth: 1))
    }
    enc.endEncoding()
    cb.commit()
    cb.waitUntilCompleted()
    return (cb.gpuEndTime - cb.gpuStartTime) * 1e6 / Double(reps)
}

struct Stat { let mean: Double; let sd: Double; let ci: Double; let n: Int }

// two-sided t at 95% for df = n-1
let tTable: [Int: Double] = [
    4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
    11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131, 19: 2.093, 29: 2.045,
]

func stat(_ xs: [Double]) -> Stat {
    let n = xs.count
    let m = xs.reduce(0, +) / Double(n)
    let v = xs.map { ($0 - m) * ($0 - m) }.reduce(0, +) / Double(n - 1)
    let sd = v.squareRoot()
    let t = tTable[n - 1] ?? 2.0
    return Stat(mean: m, sd: sd, ci: t * sd / Double(n).squareRoot(), n: n)
}

/// Paired rounds of four command buffers about a millisecond apart. Even rounds
/// run A,B,B,A and odd rounds run B,A,A,B; both estimate A - B and both cancel
/// drift that is linear over the round. Alternating the polarity de-confounds
/// the arm from the slot it occupies (rule 36): an effect that is really a
/// first-slot/last-slot artifact flips sign between the two halves and cancels,
/// while a real effect survives in each half separately.
func paired(_ a: MTLComputePipelineState, _ b: MTLComputePipelineState, rotate: Bool)
    -> (abba: [Double], baab: [Double], aAbs: [Double], bAbs: [Double])
{
    var abba: [Double] = []
    var baab: [Double] = []
    var aAbs: [Double] = []
    var bAbs: [Double] = []
    for round in 0..<rounds {
        let outer = round % 2 == 0 ? a : b
        let inner = round % 2 == 0 ? b : a
        let o1 = timeOnce(outer, rotate: rotate)
        let i1 = timeOnce(inner, rotate: rotate)
        let i2 = timeOnce(inner, rotate: rotate)
        let o2 = timeOnce(outer, rotate: rotate)
        let outerMean = (o1 + o2) / 2
        let innerMean = (i1 + i2) / 2
        let aMean = round % 2 == 0 ? outerMean : innerMean
        let bMean = round % 2 == 0 ? innerMean : outerMean
        if round % 2 == 0 { abba.append(aMean - bMean) } else { baab.append(aMean - bMean) }
        aAbs.append(aMean)
        bAbs.append(bMean)
    }
    return (abba, baab, aAbs, bAbs)
}

// MARK: - run

print("=== device ===")
print("name                 \(device.name)")
print("architecture         \(device.architecture.name)")
print("source dir           \(srcDir)")
print("grid                 \(tiles) threadgroups x \(threads) threads")
print("reps/commandbuffer   \(reps)   rounds \(rounds)")
print("router_weight        \(weightCopies) x 1 MiB rotating copies")
print("")

var pipes: [Int: MTLComputePipelineState] = [:]
print("=== occupancy (mandatory gate: maxTotalThreadsPerThreadgroup >= 512) ===")
print("arm  maxTotalThreads  execWidth  staticTGmem  verdict  label")
for arm in arms {
    let p = compile(arm: arm, tag: "")
    pipes[arm] = p
    let ok = p.maxTotalThreadsPerThreadgroup >= threads ? "PASS" : "FAIL"
    print(String(
        format: "%-4d %-16d %-10d %-12d %-8s %@", arm,
        p.maxTotalThreadsPerThreadgroup, p.threadExecutionWidth,
        p.staticThreadgroupMemoryLength, (ok as NSString).utf8String!,
        armLabel[arm]!))
}
print("")

let armCopy = compile(arm: 0, tag: "_copy")

struct Comparison { let label: String; let a: Int; let b: Int }
let comparisons: [Comparison] = [
    Comparison(label: "null  A0 vs A0' (pre)", a: 0, b: -1),
    Comparison(label: "A1 - A0", a: 1, b: 0),
    Comparison(label: "A2 - A0", a: 2, b: 0),
    Comparison(label: "A5 - A0  (depth3)", a: 3, b: 0),
    Comparison(label: "A3 - A0", a: 4, b: 0),
    Comparison(label: "A4 - A0", a: 5, b: 0),
    Comparison(label: "A1 - A4  (overlap)", a: 1, b: 5),
    Comparison(label: "A2 - A4  (overlap)", a: 2, b: 5),
    // Phase split. A0 - P-norm is the router GEMV's marginal cost; P-norm is
    // the window a prefetch issued above the barriers can overlap into.
    Comparison(label: "P-norm - A0  (phase)", a: 6, b: 0),
    Comparison(label: "P-gemv - A0  (phase)", a: 7, b: 0),
    Comparison(label: "null  A0 vs A0' (post)", a: 0, b: -1),
]

for rotate in [true, false] {
    // The first probe run showed the A0 arm settling monotonically from 9.30 to
    // 6.45 us/call over the first two comparisons, so anything measured before
    // the clocks settle is a warm-up transient, not an arm effect.
    for _ in 0..<warmupCBs { _ = timeOnce(pipes[0]!, rotate: rotate) }

    print("=== paired kernel time, \(rotate ? "COLD (rotating 64 MiB weight)" : "HOT (single 1 MiB weight)") ===")
    print("comparison              A us/call  B us/call  diff us/call  95% CI             ABBA half  BAAB half  per-step us (39 calls)")
    for c in comparisons {
        let a = pipes[c.a]!
        let b = c.b < 0 ? armCopy : pipes[c.b]!
        let (abba, baab, aa, bb) = paired(a, b, rotate: rotate)
        let s = stat(abba + baab)
        let sAbba = stat(abba)
        let sBaab = stat(baab)
        let sa = stat(aa)
        let sb = stat(bb)
        print(String(
            format: "%-23s %-10.3f %-10.3f %-13.4f [%+.4f,%+.4f]  %+9.4f  %+9.4f  %+.2f [%+.2f,%+.2f]",
            (c.label as NSString).utf8String!, sa.mean, sb.mean, s.mean,
            s.mean - s.ci, s.mean + s.ci, sAbba.mean, sBaab.mean,
            s.mean * callsPerStep, (s.mean - s.ci) * callsPerStep,
            (s.mean + s.ci) * callsPerStep))
    }
    print("")
}
