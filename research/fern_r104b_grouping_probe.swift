// Research-only host probe (not part of the submission surface).
//
// Round-104 arm B.  The wk/wv regroup hypothesis says: the regular-NAX steel
// GEMM for M=512,N=1024,K=2048 launches 64 threadgroups of 8 simdgroups each,
// that 64 does not divide the core count evenly, and splitting the same 512
// output simdgroups into more, smaller threadgroups therefore balances the
// machine better.
//
// That argument silently assumes one threadgroup resident per core at a time.
// If a core can host several of these threadgroups concurrently -- and the
// gemm_nax kernel measures 0 B of threadgroup memory, so nothing obvious
// forbids it -- the quantum is much finer than "one 8-simdgroup TG" and the
// balance argument collapses.  That is preregistered null N-B.
//
// This probe answers both questions on the local host with a synthetic kernel
// whose only job is to occupy simdgroups for a fixed, tunable time:
//
//   Part 1 (ladder)   for each threadgroup width, sweep the dispatched
//                     threadgroup count upward and locate the risers.  The
//                     first riser at K gives the resident concurrency C=K-1,
//                     hence threadgroups per core and simdgroups per core.
//   Part 2 (grouping) hold the total simdgroup count fixed and vary only how
//                     those simdgroups are grouped into threadgroups.  Under
//                     the balance model the wall time should follow
//                     q(g) = g * ceil(T / (C_tg(g) * g)) normalised to its
//                     minimum; under the "occupancy is not the limiter" null
//                     it should be flat.
//
// The kernel is deliberately not numerically meaningful.  It is a scheduling
// instrument, and its arithmetic exists only so that one wave lasts long
// enough to separate the risers from launch overhead.  It allocates no
// threadgroup memory, matching the measured gemm_nax footprint.
//
// Build and run:
//   xcrun swiftc -O research/fern_r104b_grouping_probe.swift -o /tmp/ferngrp \
//     && /tmp/ferngrp

import Foundation
import Metal

func intVal(_ name: String, _ fallback: Int) -> Int {
    guard let raw = ProcessInfo.processInfo.environment[name], let v = Int(raw) else {
        return fallback
    }
    return v
}

func intList(_ name: String, _ fallback: [Int]) -> [Int] {
    guard let raw = ProcessInfo.processInfo.environment[name] else { return fallback }
    let parsed = raw.split(separator: ",").compactMap { Int($0.trimmingCharacters(in: .whitespaces)) }
    precondition(!parsed.isEmpty, "\(name) set but unparseable: \(raw)")
    return parsed
}

let simdWidth = 32
let sgPerTGList = intList("FERN_SG_LIST", [1, 2, 4, 8])
let totalSG = intVal("FERN_TOTAL_SG", 512)
let kMax = intVal("FERN_K_MAX", 260)
let iters = intVal("FERN_ITERS", 20000)
let reps = intVal("FERN_REPS", 25)
let riserRatio = Double(intVal("FERN_RISER_PCT", 115)) / 100.0

let source = """
#include <metal_stdlib>
using namespace metal;

kernel void spin(device float* out [[buffer(0)]],
                 constant uint& iters [[buffer(1)]],
                 uint gid [[thread_position_in_grid]],
                 uint lid [[thread_position_in_threadgroup]]) {
  float acc = float(lid) * 1e-6f;
  float b = 1.0000001f;
  for (uint i = 0; i < iters; ++i) {
    acc = fma(acc, b, 1e-7f);
  }
  out[gid] = acc;
}
"""

let device = MTLCreateSystemDefaultDevice()!
let queue = device.makeCommandQueue()!
let library = try! device.makeLibrary(source: source, options: nil)
let pipeline = try! device.makeComputePipelineState(function: library.makeFunction(name: "spin")!)

print("device: \(device.name)")
print("arch: \(device.architecture.name)")
print("maxThreadsPerThreadgroup: \(pipeline.maxTotalThreadsPerThreadgroup)")
print("threadExecutionWidth: \(pipeline.threadExecutionWidth)")
print("staticThreadgroupMemoryLength: \(pipeline.staticThreadgroupMemoryLength)")
print("iters=\(iters) reps=\(reps) totalSG=\(totalSG)")

let outCapacity = max(kMax, totalSG) * simdWidth * 8
let outBuf = device.makeBuffer(length: outCapacity * MemoryLayout<Float>.size,
                               options: .storageModePrivate)!
var itersU = UInt32(iters)

/// Wall time in seconds for one dispatch of `tgCount` threadgroups of
/// `sgPerTG` simdgroups.  Reports the minimum over `reps` to suppress
/// scheduler and thermal noise.
func time(tgCount: Int, sgPerTG: Int) -> Double {
    let threads = MTLSize(width: simdWidth * sgPerTG, height: 1, depth: 1)
    let grid = MTLSize(width: tgCount, height: 1, depth: 1)
    var best = Double.infinity
    for r in 0..<reps {
        let cb = queue.makeCommandBuffer()!
        let enc = cb.makeComputeCommandEncoder()!
        enc.setComputePipelineState(pipeline)
        enc.setBuffer(outBuf, offset: 0, index: 0)
        enc.setBytes(&itersU, length: 4, index: 1)
        enc.dispatchThreadgroups(grid, threadsPerThreadgroup: threads)
        enc.endEncoding()
        cb.commit()
        cb.waitUntilCompleted()
        let t = cb.gpuEndTime - cb.gpuStartTime
        if r > 0 { best = min(best, t) }  // discard the first leg (rule 77)
    }
    return best
}

// ---------------------------------------------------------------- warm up
_ = time(tgCount: 8, sgPerTG: 1)

// ------------------------------------------------------- Part 1: ladder
// Sweep the dispatched threadgroup count and find where the wall time steps.
// The first riser sits at K = C + 1 where C is the resident concurrency.
print("")
print("== part 1: concurrency ladder ==")
var concurrency: [Int: Int] = [:]
for sg in sgPerTGList {
    if simdWidth * sg > pipeline.maxTotalThreadsPerThreadgroup { continue }
    var t = [Double](repeating: 0, count: kMax + 1)
    for k in 1...kMax { t[k] = time(tgCount: k, sgPerTG: sg) }
    var risers: [Int] = []
    for k in 2...kMax where t[k] > t[k - 1] * riserRatio { risers.append(k) }
    let c = risers.first.map { $0 - 1 } ?? kMax
    concurrency[sg] = c
    let head = risers.prefix(6).map(String.init).joined(separator: ",")
    print(String(format: "sg/tg=%d threads=%4d  t(1)=%8.1fus t(C)=%8.1fus  risers=[%@]  C=%d  sg_resident=%d",
                 sg, simdWidth * sg, t[1] * 1e6, t[max(c, 1)] * 1e6, head, c, c * sg))
}

// ----------------------------------------------------- Part 2: grouping
// Same total simdgroup count, different grouping.  This is the direct
// analogue of the matmul.cpp arms: the per-simdgroup work is identical and
// only the threadgroup partition changes.
print("")
print("== part 2: fixed total simdgroups, varying grouping ==")
print("g  tgs   threads  wall_us   rel     waves  wave_rel")
var results: [(sg: Int, wall: Double, waves: Double)] = []
for sg in sgPerTGList {
    if simdWidth * sg > pipeline.maxTotalThreadsPerThreadgroup { continue }
    guard totalSG % sg == 0 else { continue }
    let tgs = totalSG / sg
    let c = concurrency[sg] ?? 1
    let waves = (Double(tgs) / Double(c)).rounded(.up)
    results.append((sg, time(tgCount: tgs, sgPerTG: sg), waves))
}
let bestWall = results.map(\.wall).min() ?? 1
let bestWaves = results.map(\.waves).min() ?? 1
for r in results {
    print(String(format: "%d  %4d  %5d  %9.1f  %6.4f  %6.0f  %6.4f",
                 r.sg, totalSG / r.sg, simdWidth * r.sg, r.wall * 1e6,
                 r.wall / bestWall, r.waves, r.waves / bestWaves))
}

// -------------------------------------------------- Part 4: tail control
// Part 2 confounds two explanations: wide threadgroups may quantize the tail
// badly, or they may simply run slower per unit work.  Sweeping the total
// simdgroup count separates them.  If the mechanism is tail quantization then
// each grouping's throughput is a sawtooth that peaks whenever the dispatch
// fills its last wave, and the wide grouping matches the narrow one at its
// peaks.  If wide threadgroups are intrinsically slower the gap is flat.
print("")
print("== part 4: throughput vs total simdgroups ==")
let sweep = intList("FERN_SWEEP", [336, 384, 448, 504, 512, 640, 672, 1008, 1024])
var header = "totalSG"
for sg in sgPerTGList where simdWidth * sg <= pipeline.maxTotalThreadsPerThreadgroup {
    header += String(format: "   g=%d_sg/us", sg)
}
print(header)
for total in sweep {
    var line = String(format: "%7d", total)
    for sg in sgPerTGList where simdWidth * sg <= pipeline.maxTotalThreadsPerThreadgroup {
        guard total % sg == 0 else { line += "        -"; continue }
        let wall = time(tgCount: total / sg, sgPerTG: sg)
        line += String(format: "  %10.4f", Double(total) / (wall * 1e6))
    }
    print(line)
}

// ------------------------------------------- Part 3: core-count inference
// If a core admits `R` resident threadgroups of this width, then C = R * P.
// Print the divisor structure so the report can state what P is consistent
// with, rather than assuming it.
print("")
print("== part 3: divisors of measured concurrency ==")
for sg in sgPerTGList.sorted() {
    guard let c = concurrency[sg] else { continue }
    let divs = (1...c).filter { c % $0 == 0 }
    print("sg/tg=\(sg) C=\(c) sg_resident=\(c * sg) divisors=\(divs)")
}
