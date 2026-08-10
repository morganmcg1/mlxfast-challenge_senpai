// Resident-threadgroup census for the R107-C expert gather-GEMM BN ledger.
//
// Measures how many threadgroups of a given size co-reside on this GPU as a
// function of dynamic threadgroup-memory bytes. This calibrates the occupancy
// column of the static ledger: it is a machine-constant measurement, not a
// timing claim about any Laguna kernel.
//
// Method: every threadgroup bumps a device `live` counter on entry, repeatedly
// publishes `atomic_max(peak, live)` while it spins a bounded dependent-FMA
// loop, then decrements. The peak is the co-residency the scheduler achieved.
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
  // Touch the dynamic allocation so it cannot be elided.
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
let spinBuf = device.makeBuffer(
    bytes: &spin, length: 4, options: .storageModeShared)!

print("device: \(device.name)")
print("maxThreadgroupMemoryLength: \(device.maxThreadgroupMemoryLength)")
print("pipeline.maxTotalThreadsPerThreadgroup: \(pipeline.maxTotalThreadsPerThreadgroup)")
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

// 4624 / 9232 are the measured static allocations of the BN=32 / BN=64
// `fp_gather_qmm_rhs_expert_nax` pipelines.
let byteSweep = [0, 1024, 2048, 4096, 4624, 6144, 8192, 9232, 12288, 16384, 24576, 32768]
var best: [Int: UInt32] = [:]
for threads in [128] {
    _ = censusOnce(threads: threads, bytes: 4624)  // warm the queue
    for bytes in byteSweep {
        for rep in 0..<5 {
            guard let (observed, dt) = censusOnce(threads: threads, bytes: bytes) else {
                print("\(threads),\(bytes),\(rep),ERROR,-")
                continue
            }
            print(String(format: "%d,%d,%d,%u,%.4f", threads, bytes, rep, observed, dt))
            best[bytes] = max(best[bytes] ?? 0, observed)
        }
    }
}
print("\ntg_bytes,max_over_reps")
for bytes in byteSweep {
    print("\(bytes),\(best[bytes] ?? 0)")
}
