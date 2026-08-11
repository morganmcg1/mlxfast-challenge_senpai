// Research-only (PR #693, R110-B rev4 Stage-0): measured streaming-read
// ceiling for this host's GPU.
//
// Stage-0 asks whether the decode QMV family is bandwidth bound. That question
// needs an honest denominator: not the marketing DRAM figure, but the GB/s a
// pure streaming-read kernel actually achieves on this device with a working
// set far larger than the system level cache.
//
//   xcrun swiftc -O research/edward_r110b_bw_bench.swift -o /tmp/edbw && /tmp/edbw
//
// Env knobs: ED_MB (working set per stream, MiB, default 512), ED_REPS.

import Foundation
import Metal

func die(_ m: String) -> Never {
    FileHandle.standardError.write(("ERROR: " + m + "\n").data(using: .utf8)!)
    exit(1)
}

func log(_ m: String) {
    print(m)
    fflush(stdout)
}

func env(_ k: String) -> String? { ProcessInfo.processInfo.environment[k] }
func envInt(_ k: String, _ d: Int) -> Int { env(k).flatMap { Int($0) } ?? d }

let source = """
#include <metal_stdlib>
using namespace metal;

// Contiguous 16-byte loads, grid-strided so every thread walks the buffer
// with a fully coalesced 64-byte-per-simd-quad footprint.
kernel void stream_u4(device const uint4 *src [[buffer(0)]],
                      device uint4 *dst [[buffer(1)]],
                      constant uint &n4 [[buffer(2)]],
                      uint tid [[thread_position_in_grid]],
                      uint nthreads [[threads_per_grid]]) {
    uint4 acc = uint4(0);
    for (uint i = tid; i < n4; i += nthreads) { acc += src[i]; }
    // Value-dependent, never true: keeps the loads live without adding a store.
    if (acc.x == 0xFFFFFFFFu && acc.y == 0xFFFFFFFFu) { dst[tid] = acc; }
}

// Windowed variant for the short-dispatch ceiling. `off4` rotates the window
// across a working set far larger than the SLC, so a 5-11 MB dispatch never
// re-reads what the previous dispatch left cached -- the same situation a
// decode QMV faces, where consecutive dispatches touch different experts and
// different layers.
kernel void stream_win(device const uint4 *src [[buffer(0)]],
                       device uint4 *dst [[buffer(1)]],
                       constant uint &n4 [[buffer(2)]],
                       constant uint &off4 [[buffer(3)]],
                       uint tid [[thread_position_in_grid]],
                       uint nthreads [[threads_per_grid]]) {
    uint4 acc = uint4(0);
    for (uint i = tid; i < n4; i += nthreads) { acc += src[off4 + i]; }
    if (acc.x == 0xFFFFFFFFu && acc.y == 0xFFFFFFFFu) { dst[tid] = acc; }
}

// Same traffic, four independent accumulators: separates a bandwidth floor
// from a load-issue/latency floor.
kernel void stream_u4x4(device const uint4 *src [[buffer(0)]],
                        device uint4 *dst [[buffer(1)]],
                        constant uint &n4 [[buffer(2)]],
                        uint tid [[thread_position_in_grid]],
                        uint nthreads [[threads_per_grid]]) {
    uint4 a0 = uint4(0), a1 = uint4(0), a2 = uint4(0), a3 = uint4(0);
    uint stride = nthreads * 4;
    for (uint i = tid; i + stride <= n4; i += stride) {
        a0 += src[i];
        a1 += src[i + nthreads];
        a2 += src[i + 2 * nthreads];
        a3 += src[i + 3 * nthreads];
    }
    uint4 acc = a0 + a1 + a2 + a3;
    if (acc.x == 0xFFFFFFFFu && acc.y == 0xFFFFFFFFu) { dst[tid] = acc; }
}

// 4-byte loads: the granularity an NVFP4 weight walk uses when it consumes one
// packed uint32 (8 values) at a time.
kernel void stream_u1(device const uint *src [[buffer(0)]],
                      device uint *dst [[buffer(1)]],
                      constant uint &n1 [[buffer(2)]],
                      uint tid [[thread_position_in_grid]],
                      uint nthreads [[threads_per_grid]]) {
    uint acc = 0;
    for (uint i = tid; i < n1; i += nthreads) { acc += src[i]; }
    if (acc == 0xFFFFFFFFu) { dst[tid] = acc; }
}

// Two streams in the NVFP4 ratio: 32 weight bytes per 2 scale bytes, i.e. the
// dual-stream footprint of a real quantized mat-vec. `w` is uint4 (16 B),
// `s` is uchar; one scale byte per 16 values = per 8 weight bytes.
kernel void stream_nvfp4(device const uint4 *w [[buffer(0)]],
                         device const uchar2 *s [[buffer(1)]],
                         device uint4 *dst [[buffer(2)]],
                         constant uint &n4 [[buffer(3)]],
                         uint tid [[thread_position_in_grid]],
                         uint nthreads [[threads_per_grid]]) {
    uint4 acc = uint4(0);
    uint sacc = 0;
    for (uint i = tid; i < n4; i += nthreads) {
        acc += w[i];
        uchar2 sv = s[i];
        sacc += uint(sv.x) + uint(sv.y);
    }
    if (acc.x == 0xFFFFFFFFu && sacc == 0xFFFFFFFFu) { dst[tid] = acc; }
}
"""

guard let device = MTLCreateSystemDefaultDevice() else { die("no Metal device") }
guard let queue = device.makeCommandQueue() else { die("no command queue") }
log("device: \(device.name)")
log("recommendedMaxWorkingSetSize: \(device.recommendedMaxWorkingSetSize / (1 << 20)) MiB")

let opts = MTLCompileOptions()
opts.fastMathEnabled = false
let lib: MTLLibrary
do { lib = try device.makeLibrary(source: source, options: opts) }
catch { die("compile failed: \(error)") }

let mib = envInt("ED_MB", 512)
let reps = envInt("ED_REPS", 12)
let bytes = mib << 20
let n4 = bytes / 16
let n1 = bytes / 4
let scaleBytes = bytes / 8 // one fp8 scale per 16 nvfp4 values == per 8 bytes

guard let src = device.makeBuffer(length: bytes, options: .storageModePrivate),
      let scales = device.makeBuffer(length: scaleBytes, options: .storageModePrivate),
      let dst = device.makeBuffer(length: 1 << 22, options: .storageModePrivate)
else { die("buffer allocation failed (\(mib) MiB)") }

struct Case {
    let name: String
    let fn: String
    let elems: Int
    let bytesMoved: Int
    let dual: Bool
}

let cases = [
    Case(name: "stream_u4", fn: "stream_u4", elems: n4, bytesMoved: bytes, dual: false),
    Case(name: "stream_u4x4", fn: "stream_u4x4", elems: n4, bytesMoved: bytes, dual: false),
    Case(name: "stream_u1", fn: "stream_u1", elems: n1, bytesMoved: bytes, dual: false),
    Case(name: "stream_nvfp4", fn: "stream_nvfp4", elems: n4,
         bytesMoved: bytes + scaleBytes, dual: true),
]

// Enough threads to saturate every core with several waves in flight, but few
// enough that each one still walks a long contiguous-ish run.
let tgSize = 256
let totalThreads = 256 * 1024
let tgCount = totalThreads / tgSize

log("working set: \(mib) MiB   threads: \(totalThreads)   tg: \(tgSize)   reps: \(reps)")
log("")

for c in cases {
    guard let fn = lib.makeFunction(name: c.fn) else { die("no function \(c.fn)") }
    let pso: MTLComputePipelineState
    do { pso = try device.makeComputePipelineState(function: fn) }
    catch { die("pipeline \(c.fn): \(error)") }

    var n = UInt32(c.elems)
    var samples: [Double] = []
    for r in 0..<(reps + 2) {
        guard let cb = queue.makeCommandBuffer(),
              let enc = cb.makeComputeCommandEncoder() else { die("encoder") }
        enc.setComputePipelineState(pso)
        if c.dual {
            enc.setBuffer(src, offset: 0, index: 0)
            enc.setBuffer(scales, offset: 0, index: 1)
            enc.setBuffer(dst, offset: 0, index: 2)
            enc.setBytes(&n, length: 4, index: 3)
        } else {
            enc.setBuffer(src, offset: 0, index: 0)
            enc.setBuffer(dst, offset: 0, index: 1)
            enc.setBytes(&n, length: 4, index: 2)
        }
        enc.dispatchThreadgroups(MTLSize(width: tgCount, height: 1, depth: 1),
                                 threadsPerThreadgroup: MTLSize(width: tgSize, height: 1, depth: 1))
        enc.endEncoding()
        cb.commit()
        cb.waitUntilCompleted()
        if let e = cb.error { die("\(c.fn) failed: \(e)") }
        if r >= 2 { samples.append(cb.gpuEndTime - cb.gpuStartTime) }
    }
    samples.sort()
    let best = samples.first!
    let med = samples[samples.count / 2]
    let gbBest = Double(c.bytesMoved) / best / 1e9
    let gbMed = Double(c.bytesMoved) / med / 1e9
    log(String(format: "%-14s  best %7.3f ms -> %7.1f GB/s   median %7.3f ms -> %7.1f GB/s",
               (c.name as NSString).utf8String!, best * 1e3, gbBest, med * 1e3, gbMed))
}

// MARK: - short-dispatch ceiling at the real decode geometries
//
// A 5-11 MB dispatch is not a 512 MiB stream: wave launch and the tail drain
// are a much larger fraction of it. The fair comparator for a decode QMV is a
// pure read of the same byte count with the same grid, not the asymptotic
// stream above.

struct Geom {
    let name: String
    let bytes: Int
    let threads: Int
    let tg: Int
}

let geoms = [
    Geom(name: "K1 routed_gate_up", bytes: 8_918_016, threads: 131_072, tg: 64),
    Geom(name: "K2 qkv_h64", bytes: 10_827_776, threads: 327_680, tg: 64),
    Geom(name: "K3 oproj_h64", bytes: 8_669_312, threads: 16_384, tg: 64),
    Geom(name: "K4 down_residual", bytes: 5_026_880, threads: 147_456, tg: 288),
    Geom(name: "K3' oproj @128k", bytes: 8_669_312, threads: 131_072, tg: 64),
]

guard let winFn = lib.makeFunction(name: "stream_win") else { die("no stream_win") }
let winPso: MTLComputePipelineState
do { winPso = try device.makeComputePipelineState(function: winFn) }
catch { die("pipeline stream_win: \(error)") }

log("")
log("short-dispatch read ceiling (window rotates over the \(mib) MiB set):")
for g in geoms {
    let n = UInt32(g.bytes / 16)
    let windows = max(1, n4 / Int(n))
    var samples: [Double] = []
    for r in 0..<(reps + 2) {
        var nn = n
        var off = UInt32((r % windows) * Int(n))
        guard let cb = queue.makeCommandBuffer(),
              let enc = cb.makeComputeCommandEncoder() else { die("encoder") }
        enc.setComputePipelineState(winPso)
        enc.setBuffer(src, offset: 0, index: 0)
        enc.setBuffer(dst, offset: 0, index: 1)
        enc.setBytes(&nn, length: 4, index: 2)
        enc.setBytes(&off, length: 4, index: 3)
        enc.dispatchThreadgroups(MTLSize(width: g.threads / g.tg, height: 1, depth: 1),
                                 threadsPerThreadgroup: MTLSize(width: g.tg, height: 1, depth: 1))
        enc.endEncoding()
        cb.commit()
        cb.waitUntilCompleted()
        if let e = cb.error { die("stream_win failed: \(e)") }
        if r >= 2 { samples.append(cb.gpuEndTime - cb.gpuStartTime) }
    }
    samples.sort()
    let best = samples.first!
    let med = samples[samples.count / 2]
    log(String(format: "%-18s %9d B  %7d thr tg=%3d   best %7.2f us -> %6.1f GB/s   median %7.2f us -> %6.1f GB/s",
               (g.name as NSString).utf8String!, g.bytes, g.threads, g.tg,
               best * 1e6, Double(g.bytes) / best / 1e9,
               med * 1e6, Double(g.bytes) / med / 1e9))
}
