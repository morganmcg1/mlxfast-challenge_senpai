// Resident-threadgroup census for the R125-D routed-down BN ladder.
//
// Same instrument as research/maple-alphonse-r107c-occupancy-census.swift,
// re-pointed at the three static footprints this experiment cares about
// (BN=32/64/128 -> 4624 / 9232 / 18448 bytes) with more repetitions so the
// BN=128 point gets a usable interval. Machine-constant measurement of
// scheduler co-residency versus dynamic threadgroup bytes; no Laguna kernel
// timing is measured or claimed.
//
// Usage: /tmp/bin <bytes ...>   (default 4624 9232 18448)
import Foundation
import Metal

let kernelSource = """
#include <metal_stdlib>
using namespace metal;

[[kernel]] void census(
    device atomic_uint* live [[buffer(0)]],
    device atomic_uint* peak [[buffer(1)]],
    device float* sink [[buffer(2)]],
    constant uint& spin [[buffer(3)]],
    threadgroup uchar* scratch [[threadgroup(0)]],
    uint lid [[thread_index_in_threadgroup]],
    uint tgid [[threadgroup_position_in_grid]],
    uint tgsize [[threads_per_threadgroup]]) {
  for (uint i = lid; i < 64; i += tgsize) {
    scratch[i] = uchar(i + tgid);
  }
  threadgroup_barrier(mem_flags::mem_threadgroup);

  if (lid == 0) {
    uint now = atomic_fetch_add_explicit(live, 1u, memory_order_relaxed) + 1u;
    atomic_fetch_max_explicit(peak, now, memory_order_relaxed);
  }
  threadgroup_barrier(mem_flags::mem_threadgroup);

  float acc = float(lid) + float(scratch[lid % 64]);
  for (uint i = 0; i < spin; ++i) {
    acc = fma(acc, 1.0000001f, 1e-7f);
    if (lid == 0 && (i & 255u) == 0u) {
      uint now = atomic_load_explicit(live, memory_order_relaxed);
      atomic_fetch_max_explicit(peak, now, memory_order_relaxed);
    }
  }

  threadgroup_barrier(mem_flags::mem_threadgroup);
  if (lid == 0) {
    sink[tgid] = acc;
    atomic_fetch_sub_explicit(live, 1u, memory_order_relaxed);
  }
}
"""

guard let device = MTLCreateSystemDefaultDevice(),
    let queue = device.makeCommandQueue()
else {
    FileHandle.standardError.write(Data("no Metal device\n".utf8))
    exit(2)
}

let library = try device.makeLibrary(source: kernelSource, options: MTLCompileOptions())
let pipeline = try device.makeComputePipelineState(
    function: library.makeFunction(name: "census")!)

let tgCount = 8192
let live = device.makeBuffer(length: 4, options: .storageModeShared)!
let peak = device.makeBuffer(length: 4, options: .storageModeShared)!
let sink = device.makeBuffer(length: tgCount * 4, options: .storageModePrivate)!
var spin: UInt32 = 120_000
let spinBuf = device.makeBuffer(bytes: &spin, length: 4, options: .storageModeShared)!

print("device: \(device.name)")
print("maxThreadgroupMemoryLength: \(device.maxThreadgroupMemoryLength)")
print("threads_per_tg,tg_bytes,rep,peak_resident_tgs,elapsed_s")

func censusOnce(threads: Int, bytes: Int) -> (UInt32, Double)? {
    live.contents().storeBytes(of: UInt32(0), as: UInt32.self)
    peak.contents().storeBytes(of: UInt32(0), as: UInt32.self)
    let cb = queue.makeCommandBuffer()!
    let enc = cb.makeComputeCommandEncoder()!
    enc.setComputePipelineState(pipeline)
    enc.setBuffer(live, offset: 0, index: 0)
    enc.setBuffer(peak, offset: 0, index: 1)
    enc.setBuffer(sink, offset: 0, index: 2)
    enc.setBuffer(spinBuf, offset: 0, index: 3)
    enc.setThreadgroupMemoryLength(max(bytes, 64), index: 0)
    enc.dispatchThreadgroups(
        MTLSize(width: tgCount, height: 1, depth: 1),
        threadsPerThreadgroup: MTLSize(width: threads, height: 1, depth: 1))
    enc.endEncoding()
    let t0 = Date()
    cb.commit()
    cb.waitUntilCompleted()
    let dt = Date().timeIntervalSince(t0)
    if cb.error != nil { return nil }
    return (peak.contents().load(as: UInt32.self), dt)
}

let args = CommandLine.arguments.dropFirst().compactMap { Int($0) }
let byteSweep = args.isEmpty ? [4624, 9232, 18448] : args
var samples: [Int: [UInt32]] = [:]
_ = censusOnce(threads: 128, bytes: 4624)  // warm the queue
for bytes in byteSweep {
    for rep in 0..<8 {
        guard let (observed, dt) = censusOnce(threads: 128, bytes: bytes) else {
            print("128,\(bytes),\(rep),ERROR,-")
            continue
        }
        print(String(format: "128,%d,%d,%u,%.4f", bytes, rep, observed, dt))
        samples[bytes, default: []].append(observed)
    }
}
print("\ntg_bytes,n,min,mean,max,sd")
for bytes in byteSweep {
    let s = samples[bytes] ?? []
    if s.isEmpty { continue }
    let xs = s.map { Double($0) }
    let mean = xs.reduce(0, +) / Double(xs.count)
    let varr = xs.map { ($0 - mean) * ($0 - mean) }.reduce(0, +) / Double(max(xs.count - 1, 1))
    print(
        String(
            format: "%d,%d,%u,%.1f,%u,%.2f", bytes, s.count, s.min()!, mean, s.max()!,
            varr.squareRoot()))
}
