// Research-only host probe (not part of the submission surface).
//
// Round-100 arm A, part P2/E1b: which resource quantizes the threadgroup
// cost ladder?
//
// E1 measured t(K) for `laguna_sliding_fused_attn_ring_v1` and found a
// staircase whose risers sit at K = 21, 41, 61 on this 20-core host, i.e.
// exactly one threadgroup resident per core.  That single fact decides the
// whole "one query head per threadgroup" question, because it fixes how many
// scheduling waves each geometry costs.  But it does not say *why* the limit
// is one, and the two candidate causes have opposite consequences:
//
//   * threads   -- if a core admits only 1024 concurrent threads, then any
//                  1024-thread threadgroup is 1/core no matter what else the
//                  kernel does, and no source change can raise occupancy.
//   * tg memory -- if the 18432 B threadgroup allocation is what excludes a
//                  second resident threadgroup, then shrinking that array
//                  below half (or a third) of the per-core budget raises
//                  occupancy, and a threadgroup-doubling variant can hide its
//                  extra waves.
//
// The probe therefore sweeps (threads_per_tg, threadgroup_bytes) over a
// synthetic kernel whose only job is to occupy a core for a fixed, tunable
// time, scans K upward, and reports where the risers land.  Concurrency is
// read directly off the first riser: C = K_riser - 1, and TGs/core = C/cores.
//
// The synthetic kernel is deliberately *not* numerically meaningful.  It is a
// scheduling instrument, and its arithmetic exists only to make one wave last
// long enough that the risers are unambiguous against launch overhead.
//
// Build and run:
//   xcrun swiftc -O research/fern_r100_occupancy_probe.swift -o /tmp/fernocc \
//     && /tmp/fernocc

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

let threadsList = intList("FERN_THREADS_LIST", [1024, 512, 256])
let tgMemList = intList("FERN_TGMEM_LIST", [256, 8192, 10240, 16384, 18432, 24576, 32768])
let kMax = intVal("FERN_K_MAX", 200)
let iters = intVal("FERN_ITERS", 6000)
let rounds = intVal("FERN_ROUNDS", 5)
let reps = intVal("FERN_REPS", 40)
let riserRatio = Double(intVal("FERN_RISER_PCT", 118)) / 100.0

let device = MTLCreateSystemDefaultDevice()!
let queue = device.makeCommandQueue()!
let cores = intVal("FERN_CORES", 20)

func mslSource(tgMemBytes: Int) -> String {
    let floats = max(4, tgMemBytes / 4)
    return """
    #include <metal_stdlib>
    using namespace metal;

    constexpr constant uint SCRATCH_FLOATS = \(floats);

    kernel void occ_probe(
        device float *out [[buffer(0)]],
        constant uint &iters [[buffer(1)]],
        uint tg [[threadgroup_position_in_grid]],
        uint tid [[thread_position_in_threadgroup]],
        uint tgsz [[threads_per_threadgroup]]) {
      threadgroup float scratch[SCRATCH_FLOATS];
      for (uint i = tid; i < SCRATCH_FLOATS; i += tgsz) {
        scratch[i] = float(i + tg);
      }
      threadgroup_barrier(mem_flags::mem_threadgroup);
      float x = scratch[tid % SCRATCH_FLOATS];
      const float a = 1.0000001f;
      const float b = 1.0e-7f;
      for (uint i = 0; i < iters; ++i) {
        x = fma(x, a, b);
      }
      scratch[tid % SCRATCH_FLOATS] = x;
      threadgroup_barrier(mem_flags::mem_threadgroup);
      if (tid == 0) {
        out[tg] = scratch[0];
      }
    }
    """
}

struct Config {
    let threads: Int
    let tgMemBytes: Int
    let pipe: MTLComputePipelineState
}

let outBuf = device.makeBuffer(length: 4 * (kMax + 8), options: .storageModeShared)!
var itersBox = UInt32(iters)

func timeMicros(_ pipe: MTLComputePipelineState, threads: Int, k: Int) -> Double {
    var best = Double.infinity
    for _ in 0..<rounds {
        let cb = queue.makeCommandBuffer()!
        let enc = cb.makeComputeCommandEncoder()!
        enc.setComputePipelineState(pipe)
        enc.setBuffer(outBuf, offset: 0, index: 0)
        enc.setBytes(&itersBox, length: 4, index: 1)
        for _ in 0..<reps {
            enc.dispatchThreadgroups(
                MTLSize(width: k, height: 1, depth: 1),
                threadsPerThreadgroup: MTLSize(width: threads, height: 1, depth: 1))
        }
        enc.endEncoding()
        let t0 = DispatchTime.now().uptimeNanoseconds
        cb.commit()
        cb.waitUntilCompleted()
        let t1 = DispatchTime.now().uptimeNanoseconds
        best = min(best, Double(t1 - t0) / 1000.0 / Double(reps))
    }
    return best
}

print("=== device ===")
print("name                  \(device.name)")
print("architecture          \(device.architecture.name)")
print("gpu cores (assumed)   \(cores)")
print("max tg memory / core  \(device.maxThreadgroupMemoryLength) B")
print("iters per thread      \(iters)")
print("K scan                1..\(kMax), best of \(rounds) rounds of \(reps) dispatches")
print("riser threshold       t(K)/t(K-1) > \(String(format: "%.2f", riserRatio))")
print("")

print("=== pipeline admission ===")
print("  threads   tgmem_req_B   tgmem_static_B   maxTotalThreads   execWidth   admitted")
var configs: [Config] = []
for tgMem in tgMemList {
    let pipe: MTLComputePipelineState
    do {
        let lib = try device.makeLibrary(source: mslSource(tgMemBytes: tgMem), options: nil)
        pipe = try device.makeComputePipelineState(function: lib.makeFunction(name: "occ_probe")!)
    } catch {
        print("        -   \(tgMem)   compile-failed: \(error)")
        continue
    }
    for threads in threadsList {
        let ok = threads <= pipe.maxTotalThreadsPerThreadgroup
        let head = String(
            format: "  %7d   %11d   %14d   %15d   %9d   ",
            threads, tgMem, pipe.staticThreadgroupMemoryLength,
            pipe.maxTotalThreadsPerThreadgroup, pipe.threadExecutionWidth)
        print(head + (ok ? "yes" : "NO (tg mem too large for this thread count)"))
        if ok {
            configs.append(Config(threads: threads, tgMemBytes: tgMem, pipe: pipe))
        }
    }
}
print("")

print("=== occupancy ladder ===")
print("C = first riser K - 1 = threadgroups resident concurrently across the device.")
print("tg/core = C / \(cores).  tgmem/core implied by tg/core * tgmem_static.")
print("")
print("  threads   tgmem_B   t(1)_us   risers(K)                         C   tg/core   implied_tgmem/core_B   limiter")

for cfg in configs {
    var times: [Double] = [0]
    for k in 1...kMax {
        times.append(timeMicros(cfg.pipe, threads: cfg.threads, k: k))
    }
    var risers: [Int] = []
    for k in 2...kMax where times[k] > times[k - 1] * riserRatio {
        risers.append(k)
    }
    let c = risers.first.map { $0 - 1 } ?? kMax
    let tgPerCore = Double(c) / Double(cores)
    let impliedTgMem = Int((tgPerCore * Double(cfg.pipe.staticThreadgroupMemoryLength)).rounded())
    let limiter: String
    if cfg.threads * Int(tgPerCore.rounded()) >= 1024 && tgPerCore >= 1.0 {
        limiter = (impliedTgMem * 2 > device.maxThreadgroupMemoryLength) ? "tgmem-or-threads" : "threads"
    } else {
        limiter = "tgmem"
    }
    var riserText = risers.prefix(5).map(String.init).joined(separator: ",")
    if riserText.isEmpty { riserText = "none<=\(kMax)" }
    riserText = riserText.padding(toLength: max(30, riserText.count), withPad: " ", startingAt: 0)
    let head = String(
        format: "  %7d   %7d   %7.2f   ",
        cfg.threads, cfg.pipe.staticThreadgroupMemoryLength, times[1])
    let tail = String(format: "   %5d   %7.2f   %20d   ", c, tgPerCore, impliedTgMem)
    print(head + riserText + tail + limiter)
}
print("")
print("Read: if the 1024-thread rows report tg/core = 1.00 at every tgmem")
print("setting including the smallest, then the concurrent-thread budget is the")
print("binding constraint and no threadgroup-memory reduction can raise")
print("occupancy.  If tg/core rises as tgmem falls, threadgroup memory is the")
print("binding constraint and a smaller threadgroup allocation buys occupancy.")
