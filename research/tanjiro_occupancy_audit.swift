// Step 0 static + empirical occupancy audit for the fused decode attention
// kernels. Research-only: never part of the submitted surface.
//
//   swiftc -O research/tanjiro_occupancy_audit.swift \
//     -o /tmp/tanjiro_occ -framework Metal -framework Foundation
//   /tmp/tanjiro_occ stats research/tanjiro_kernels/*.metal
//   /tmp/tanjiro_occ probe
//
// `stats` compiles a reconstructed MLX kernel library with the same compile
// options MLX uses (Device::get_kernel_, device.cpp:631-632: fast math off,
// language version from get_metal_version()) and prints the pipeline limits
// MLX itself never queries.
//
// `wave` measures *actual* co-residency by timing staircase: every threadgroup
// runs an identical dependent-FMA chain, so GPU time is flat while the whole
// dispatch fits in one resident wave and steps up when it does not. Sweeping
// the dynamic threadgroup allocation moves the step, which names the binding
// occupancy term (threadgroup memory vs simdgroup slots) instead of assuming
// it. An atomic "count live threadgroups" probe was tried first and rejected:
// it reported 320 co-resident 1024-thread groups on a 20-core part, which is
// physically impossible, so it was not measuring residency.
//
// `resident` is the repaired version of that atomic probe. The rejected one
// only incremented, so it counted cumulative arrivals rather than concurrency.
// This one holds the slot while spinning and decrements on exit, so the peak
// reading is the number of threadgroups actually co-resident. The staircase in
// `wave` cannot answer this because an ALU-saturated kernel produces the same
// staircase whether two groups serialise or share the same ALUs.

import Foundation
import Metal

let probeSource = """
#include <metal_stdlib>
using namespace metal;

kernel void wave_probe(
    device float* sink [[buffer(0)]],
    const constant uint& iters [[buffer(1)]],
    threadgroup float* scratch [[threadgroup(0)]],
    uint tid [[thread_index_in_threadgroup]],
    uint tgid [[threadgroup_position_in_grid]],
    uint tgsize [[threads_per_threadgroup]]) {
  scratch[tid % 256u] = float(tid + tgid);
  threadgroup_barrier(mem_flags::mem_threadgroup);
  float acc = scratch[(tid + 1u) % 256u] * 1e-6f;
  for (uint i = 0; i < iters; ++i) {
    acc = fma(acc, 1.0000001f, 1e-7f);
  }
  // Never true; keeps the chain live without a real store.
  if (acc == -1234.5678f) {
    sink[tgid % 64u] = acc + float(tgsize);
  }
}
"""

let residentSource = """
#include <metal_stdlib>
using namespace metal;

kernel void resident_probe(
    device atomic_uint* live [[buffer(0)]],
    device uint* peak [[buffer(1)]],
    const constant uint& budget [[buffer(2)]],
    threadgroup float* scratch [[threadgroup(0)]],
    uint tid [[thread_index_in_threadgroup]],
    uint tgid [[threadgroup_position_in_grid]]) {
  scratch[tid % 256u] = float(tid + tgid);
  threadgroup_barrier(mem_flags::mem_threadgroup);
  if (tid == 0u) {
    // Claim the slot, then hold it for the whole spin. Every co-resident
    // group is therefore counted at the same time.
    atomic_fetch_add_explicit(live, 1u, memory_order_relaxed);
    uint seen = 0u;
    for (uint s = 0; s < budget; ++s) {
      uint now = atomic_load_explicit(live, memory_order_relaxed);
      if (now > seen) { seen = now; }
    }
    peak[tgid] = seen;
    atomic_fetch_sub_explicit(live, 1u, memory_order_relaxed);
  }
  // Keep the other threads alive so the group really occupies its slot.
  threadgroup_barrier(mem_flags::mem_threadgroup);
  if (scratch[tid % 256u] == -1.0f) { peak[tgid] = tid; }
}
"""

func makeOptions() -> MTLCompileOptions {
    let options = MTLCompileOptions()
    options.languageVersion = .version4_0
    if #available(macOS 15.0, *) {
        options.mathMode = .safe
    } else {
        options.fastMathEnabled = false
    }
    return options
}

func die(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(1)
}

guard let device = MTLCreateSystemDefaultDevice() else {
    die("no Metal device")
}

func entryPoint(of text: String) -> String? {
    guard let range = text.range(of: "[[kernel]] void ") else { return nil }
    let rest = text[range.upperBound...]
    guard let paren = rest.firstIndex(of: "(") else { return nil }
    return String(rest[rest.startIndex..<paren])
        .trimmingCharacters(in: .whitespacesAndNewlines)
}

func stats(paths: [String]) {
    print(String(format: "device: %@  registryID=%llu",
                 device.name, device.registryID))
    print("recommendedMaxWorkingSetSize: "
        + "\(device.recommendedMaxWorkingSetSize / (1 << 20)) MiB")
    print("maxThreadgroupMemoryLength:   "
        + "\(device.maxThreadgroupMemoryLength) B")
    print("maxThreadsPerThreadgroup:     "
        + "\(device.maxThreadsPerThreadgroup.width)")
    print("")
    for path in paths {
        guard let text = try? String(contentsOfFile: path, encoding: .utf8)
        else { die("cannot read \(path)") }
        guard let entry = entryPoint(of: text) else {
            die("no [[kernel]] entry point in \(path)")
        }
        let library: MTLLibrary
        do {
            library = try device.makeLibrary(source: text,
                                             options: makeOptions())
        } catch {
            die("compile failed for \(path):\n\(error)")
        }
        guard let function = library.makeFunction(name: entry) else {
            die("no function \(entry) in \(path)")
        }
        let pipeline: MTLComputePipelineState
        do {
            pipeline = try device.makeComputePipelineState(function: function)
        } catch {
            die("pipeline failed for \(entry):\n\(error)")
        }
        let tgMem = pipeline.staticThreadgroupMemoryLength
        let maxThreads = pipeline.maxTotalThreadsPerThreadgroup
        let width = pipeline.threadExecutionWidth
        print("kernel \(entry)")
        print("  file                          \(path)")
        print("  staticThreadgroupMemoryLength \(tgMem) B "
            + String(format: "(%.2f kB)", Double(tgMem) / 1024.0))
        print("  maxTotalThreadsPerThreadgroup \(maxThreads) "
            + "(= \(maxThreads / max(width, 1)) simdgroups)")
        print("  threadExecutionWidth          \(width)")
        if maxThreads < 1024 {
            print("  !! BELOW 1024: the shipped dispatch asks for 1024 "
                + "threads/threadgroup and would fail or be clamped")
        }
        print("")
    }
}

func wave(threadCounts: [Int], memBytes: [Int], maxGroups: Int, iters: UInt32) {
    let library: MTLLibrary
    do {
        library = try device.makeLibrary(source: probeSource,
                                         options: makeOptions())
    } catch {
        die("probe compile failed:\n\(error)")
    }
    guard let function = library.makeFunction(name: "wave_probe") else {
        die("no wave_probe")
    }
    let pipeline: MTLComputePipelineState
    do {
        pipeline = try device.makeComputePipelineState(function: function)
    } catch {
        die("probe pipeline failed:\n\(error)")
    }
    guard let queue = device.makeCommandQueue() else { die("no queue") }
    let sink = device.makeBuffer(length: 4 * 64, options: .storageModeShared)!
    let width = pipeline.threadExecutionWidth

    func timeGPU(groups: Int, threads: Int, mem: Int) -> Double {
        var itersValue = iters
        var best = Double.greatestFiniteMagnitude
        for _ in 0..<5 {
            let buffer = queue.makeCommandBuffer()!
            let encoder = buffer.makeComputeCommandEncoder()!
            encoder.setComputePipelineState(pipeline)
            encoder.setBuffer(sink, offset: 0, index: 0)
            encoder.setBytes(&itersValue, length: 4, index: 1)
            encoder.setThreadgroupMemoryLength(mem, index: 0)
            encoder.dispatchThreadgroups(
                MTLSize(width: groups, height: 1, depth: 1),
                threadsPerThreadgroup: MTLSize(width: threads,
                                               height: 1, depth: 1))
            encoder.endEncoding()
            buffer.commit()
            buffer.waitUntilCompleted()
            if let error = buffer.error { die("probe dispatch: \(error)") }
            best = min(best, (buffer.gpuEndTime - buffer.gpuStartTime) * 1e6)
        }
        return best
    }

    print("wave_probe: maxTotalThreadsPerThreadgroup="
        + "\(pipeline.maxTotalThreadsPerThreadgroup) "
        + "threadExecutionWidth=\(width) "
        + "staticThreadgroupMemoryLength="
        + "\(pipeline.staticThreadgroupMemoryLength)")
    print("iters=\(iters); each cell is best-of-5 GPU microseconds")
    print("")
    for threads in threadCounts where
        threads <= pipeline.maxTotalThreadsPerThreadgroup {
        for mem in memBytes where mem <= device.maxThreadgroupMemoryLength {
            _ = timeGPU(groups: 1, threads: threads, mem: mem)
            let unit = timeGPU(groups: 1, threads: threads, mem: mem)
            var row = "threads/TG=\(threads) (\(threads / width) simd) "
                + "tgmem=\(mem)B  one-TG=\(String(format: "%.0f", unit))us | "
            var firstStep = -1
            var groups = 1
            while groups <= maxGroups {
                let t = timeGPU(groups: groups, threads: threads, mem: mem)
                row += "\(groups):\(String(format: "%.0f", t)) "
                if firstStep < 0 && t > unit * 1.6 { firstStep = groups }
                groups += 1
            }
            row += "|| first step at N=\(firstStep) "
                + "=> \(firstStep < 0 ? 0 : firstStep - 1) co-resident TGs"
            print(row)
        }
    }
}

// MARK: - production-shaped microbenchmark + kernel-level bitwise oracle

struct Geometry {
    let heads: Int
    let kvHeads = 8
    let headDim = 128
    let capacity: Int
    let angleCount: Int
    let paramCount: Int
    var groups: Int { heads / 2 }
}

let slidingGeometry = Geometry(heads: 64, capacity: 512,
                               angleCount: 128, paramCount: 1)
let fullGeometry = Geometry(heads: 48, capacity: 513,
                            angleCount: 64, paramCount: 3)

struct Rng {
    var state: UInt64 = 0x2545_F491_4F6C_DD1D
    mutating func next() -> UInt64 {
        state ^= state << 13
        state ^= state >> 7
        state ^= state << 17
        return state
    }
    mutating func unit() -> Float {
        Float(next() >> 40) / Float(1 << 24) * 2.0 - 1.0
    }
}

func bfloatBuffer(_ count: Int, _ rng: inout Rng) -> MTLBuffer {
    let buffer = device.makeBuffer(length: count * 2,
                                   options: .storageModeShared)!
    let raw = buffer.contents().bindMemory(to: UInt16.self, capacity: count)
    for i in 0..<count {
        raw[i] = UInt16(truncatingIfNeeded: rng.unit().bitPattern >> 16)
    }
    return buffer
}

func floatBuffer(_ values: [Float]) -> MTLBuffer {
    let buffer = device.makeBuffer(bytes: values,
                                   length: values.count * 4,
                                   options: .storageModeShared)!
    return buffer
}

func resident(threadCounts: [Int], memBytes: [Int], groups: Int, budget: UInt32) {
    guard let queue = device.makeCommandQueue() else { die("no queue") }
    let library: MTLLibrary
    do {
        library = try device.makeLibrary(source: residentSource,
                                         options: makeOptions())
    } catch { die("resident probe compile failed:\n\(error)") }
    guard let function = library.makeFunction(name: "resident_probe") else {
        die("no resident_probe")
    }
    let pipeline: MTLComputePipelineState
    do {
        pipeline = try device.makeComputePipelineState(function: function)
    } catch { die("resident pipeline failed:\n\(error)") }

    let live = device.makeBuffer(length: 4, options: .storageModeShared)!
    let peak = device.makeBuffer(length: groups * 4,
                                 options: .storageModeShared)!
    print("resident probe: groups=\(groups) budget=\(budget) "
          + "maxTotalThreadsPerThreadgroup=\(pipeline.maxTotalThreadsPerThreadgroup)")
    for threads in threadCounts {
        if threads > pipeline.maxTotalThreadsPerThreadgroup { continue }
        for bytes in memBytes {
            if bytes > device.maxThreadgroupMemoryLength { continue }
            var best = 0
            for _ in 0..<5 {
                live.contents().storeBytes(of: UInt32(0), as: UInt32.self)
                memset(peak.contents(), 0, groups * 4)
                var budgetValue = budget
                let commands = queue.makeCommandBuffer()!
                let encoder = commands.makeComputeCommandEncoder()!
                encoder.setComputePipelineState(pipeline)
                encoder.setBuffer(live, offset: 0, index: 0)
                encoder.setBuffer(peak, offset: 0, index: 1)
                encoder.setBytes(&budgetValue, length: 4, index: 2)
                encoder.setThreadgroupMemoryLength(max(bytes, 1024), index: 0)
                encoder.dispatchThreadgroups(
                    MTLSize(width: groups, height: 1, depth: 1),
                    threadsPerThreadgroup: MTLSize(width: threads,
                                                   height: 1, depth: 1))
                encoder.endEncoding()
                commands.commit()
                commands.waitUntilCompleted()
                if let error = commands.error { die("resident: \(error)") }
                let raw = peak.contents().bindMemory(to: UInt32.self,
                                                     capacity: groups)
                for g in 0..<groups { best = max(best, Int(raw[g])) }
            }
            print(String(format: "  threads/TG=%4d tgmem=%6dB  peak co-resident TGs=%3d",
                         threads, bytes, best))
        }
    }
}

func bench(paths: [String], iterations: Int) {
    guard let queue = device.makeCommandQueue() else { die("no queue") }
    var rng = Rng()
    // Keyed per kernel family: a sliding variant is only ever compared with
    // other sliding variants.
    var references: [String: [UInt8]] = [:]
    for path in paths {
        guard let text = try? String(contentsOfFile: path, encoding: .utf8),
              let entry = entryPoint(of: text) else { die("cannot read \(path)") }
        let family = entry.contains("sliding") ? "sliding" : "full"
        let geometry = family == "sliding" ? slidingGeometry : fullGeometry
        // Same seed for every variant: the kernel-level bitwise oracle.
        rng = Rng()
        let queries = bfloatBuffer(geometry.heads * geometry.headDim, &rng)
        let keys = bfloatBuffer(geometry.kvHeads * geometry.headDim, &rng)
        let values = bfloatBuffer(geometry.kvHeads * geometry.headDim, &rng)
        let qWeight = bfloatBuffer(geometry.headDim, &rng)
        let kWeight = bfloatBuffer(geometry.headDim, &rng)
        var angleValues = [Float]()
        for i in 0..<geometry.angleCount {
            angleValues.append(Float(i) * 0.013 - 0.4)
        }
        let angles = floatBuffer(angleValues)
        let cacheCount = geometry.kvHeads * geometry.capacity * geometry.headDim
        let kCache = bfloatBuffer(cacheCount, &rng)
        let vCache = bfloatBuffer(cacheCount, &rng)
        var paramValues = [UInt32](repeating: 0, count: geometry.paramCount)
        paramValues[0] = 137
        if geometry.paramCount > 1 {
            paramValues[1] = 138
            paramValues[2] = UInt32(geometry.capacity)
        }
        let params = device.makeBuffer(bytes: paramValues,
                                       length: paramValues.count * 4,
                                       options: .storageModeShared)!
        let scale = floatBuffer([0.088388347])
        let outCount = geometry.heads * geometry.headDim
        let attended = device.makeBuffer(length: outCount * 2,
                                         options: .storageModeShared)!

        let library: MTLLibrary
        do {
            library = try device.makeLibrary(source: text,
                                             options: makeOptions())
        } catch { die("compile failed for \(path):\n\(error)") }
        guard let function = library.makeFunction(name: entry) else {
            die("no function \(entry)")
        }
        let pipeline: MTLComputePipelineState
        do {
            pipeline = try device.makeComputePipelineState(function: function)
        } catch { die("pipeline failed for \(entry):\n\(error)") }

        let buffers: [MTLBuffer] = [queries, keys, values, qWeight, kWeight,
                                    angles, kCache, vCache, params, scale,
                                    attended]
        let threads = pipeline.maxTotalThreadsPerThreadgroup >= 1024
            ? 1024 : pipeline.maxTotalThreadsPerThreadgroup
        // A serial compute encoder inserts an implicit barrier between
        // dispatches, so `repeats` back-to-back launches measure the kernel
        // the way production serializes attention layers while amortising the
        // fixed per-command-buffer GPU cost.
        let repeats = Int(ProcessInfo.processInfo
            .environment["TANJIRO_BENCH_REPEATS"] ?? "") ?? 50
        // Overriding the group count isolates per-threadgroup cost from
        // scheduling granularity: at one group per GPU core there is no
        // inter-group contention, so the ratio between two variants is their
        // true per-threadgroup work ratio.
        let groups = Int(ProcessInfo.processInfo
            .environment["TANJIRO_BENCH_GROUPS"] ?? "")
            ?? (entry.hasSuffix("_h1") ? geometry.heads : geometry.groups)
        var samples = [Double]()
        for iteration in 0..<(iterations + 1) {
            let commands = queue.makeCommandBuffer()!
            let encoder = commands.makeComputeCommandEncoder()!
            encoder.setComputePipelineState(pipeline)
            for (i, buffer) in buffers.enumerated() {
                encoder.setBuffer(buffer, offset: 0, index: i)
            }
            for _ in 0..<repeats {
                encoder.dispatchThreadgroups(
                    MTLSize(width: groups, height: 1, depth: 1),
                    threadsPerThreadgroup: MTLSize(width: threads,
                                                   height: 1, depth: 1))
            }
            encoder.endEncoding()
            commands.commit()
            commands.waitUntilCompleted()
            if let error = commands.error { die("dispatch: \(error)") }
            if iteration == 0 { continue }  // discard warmup
            samples.append((commands.gpuEndTime - commands.gpuStartTime)
                * 1e6 / Double(repeats))
        }
        samples.sort()
        let bytes = Array(UnsafeRawBufferPointer(
            start: attended.contents(), count: outCount * 2))
        let verdict: String
        if let reference = references[family] {
            verdict = reference == bytes
                ? "bitwise IDENTICAL to first \(family) variant"
                : "BITWISE DIFFERENT from first \(family) variant"
        } else {
            references[family] = bytes
            verdict = "reference \(family) variant"
        }
        print("\(entry)  [\(path)]")
        print(String(format: "  groups=%d threads/TG=%d tgmem=%dB  "
                     + "min=%.1fus p50=%.1fus p90=%.1fus  n=%d",
                     groups, threads,
                     pipeline.staticThreadgroupMemoryLength,
                     samples[0], samples[samples.count / 2],
                     samples[(samples.count * 9) / 10], samples.count))
        print("  \(verdict)")
    }
}

struct Variant {
    let entry: String
    let path: String
    let pipeline: MTLComputePipelineState
    let buffers: [MTLBuffer]
    let attended: MTLBuffer
    let outBytes: Int
    let groups: Int
    let threads: Int
}

func prepare(path: String) -> Variant {
    guard let text = try? String(contentsOfFile: path, encoding: .utf8),
          let entry = entryPoint(of: text) else { die("cannot read \(path)") }
    let geometry = entry.contains("sliding") ? slidingGeometry : fullGeometry
    var rng = Rng()
    let queries = bfloatBuffer(geometry.heads * geometry.headDim, &rng)
    let keys = bfloatBuffer(geometry.kvHeads * geometry.headDim, &rng)
    let values = bfloatBuffer(geometry.kvHeads * geometry.headDim, &rng)
    let qWeight = bfloatBuffer(geometry.headDim, &rng)
    let kWeight = bfloatBuffer(geometry.headDim, &rng)
    var angleValues = [Float]()
    for i in 0..<geometry.angleCount {
        angleValues.append(Float(i) * 0.013 - 0.4)
    }
    let angles = floatBuffer(angleValues)
    let cacheCount = geometry.kvHeads * geometry.capacity * geometry.headDim
    let kCache = bfloatBuffer(cacheCount, &rng)
    let vCache = bfloatBuffer(cacheCount, &rng)
    var paramValues = [UInt32](repeating: 0, count: geometry.paramCount)
    paramValues[0] = 137
    if geometry.paramCount > 1 {
        paramValues[1] = 138
        paramValues[2] = UInt32(geometry.capacity)
    }
    let params = device.makeBuffer(bytes: paramValues,
                                   length: paramValues.count * 4,
                                   options: .storageModeShared)!
    let scale = floatBuffer([0.088388347])
    let outCount = geometry.heads * geometry.headDim
    let attended = device.makeBuffer(length: outCount * 2,
                                     options: .storageModeShared)!
    let library: MTLLibrary
    do {
        library = try device.makeLibrary(source: text, options: makeOptions())
    } catch { die("compile failed for \(path):\n\(error)") }
    guard let function = library.makeFunction(name: entry) else {
        die("no function \(entry)")
    }
    let pipeline: MTLComputePipelineState
    do {
        pipeline = try device.makeComputePipelineState(function: function)
    } catch { die("pipeline failed for \(entry):\n\(error)") }
    let threads = pipeline.maxTotalThreadsPerThreadgroup >= 1024
        ? 1024 : pipeline.maxTotalThreadsPerThreadgroup
    let groups = Int(ProcessInfo.processInfo
        .environment["TANJIRO_BENCH_GROUPS"] ?? "")
        ?? (entry.hasSuffix("_h1") ? geometry.heads : geometry.groups)
    return Variant(entry: entry, path: path, pipeline: pipeline,
                   buffers: [queries, keys, values, qWeight, kWeight, angles,
                             kCache, vCache, params, scale, attended],
                   attended: attended, outBytes: outCount * 2,
                   groups: groups, threads: threads)
}

// One command buffer holding `repeats` back-to-back dispatches, returning
// microseconds per dispatch.
func timeOnce(_ v: Variant, queue: MTLCommandQueue, repeats: Int) -> Double {
    let commands = queue.makeCommandBuffer()!
    let encoder = commands.makeComputeCommandEncoder()!
    encoder.setComputePipelineState(v.pipeline)
    for (i, buffer) in v.buffers.enumerated() {
        encoder.setBuffer(buffer, offset: 0, index: i)
    }
    for _ in 0..<repeats {
        encoder.dispatchThreadgroups(
            MTLSize(width: v.groups, height: 1, depth: 1),
            threadsPerThreadgroup: MTLSize(width: v.threads,
                                           height: 1, depth: 1))
    }
    encoder.endEncoding()
    commands.commit()
    commands.waitUntilCompleted()
    if let error = commands.error { die("dispatch: \(error)") }
    return (commands.gpuEndTime - commands.gpuStartTime) * 1e6 / Double(repeats)
}

func median(_ xs: [Double]) -> Double {
    let s = xs.sorted()
    return s.isEmpty ? .nan : s[s.count / 2]
}

// Exactly two kernels, measured A/B/B/A inside every iteration so that a
// monotone clock or thermal drift cancels within the pair. Reports a paired
// two-sided sign-flip permutation test on the per-iteration differences.
func pair(paths: [String], iterations: Int) {
    guard paths.count == 2 else { die("pair needs exactly two kernels") }
    guard let queue = device.makeCommandQueue() else { die("no queue") }
    let repeats = Int(ProcessInfo.processInfo
        .environment["TANJIRO_BENCH_REPEATS"] ?? "") ?? 500
    let a = prepare(path: paths[0])
    let b = prepare(path: paths[1])
    var aSamples = [Double]()
    var bSamples = [Double]()
    var diffs = [Double]()
    for iteration in 0..<(iterations + 1) {
        let a0 = timeOnce(a, queue: queue, repeats: repeats)
        let b0 = timeOnce(b, queue: queue, repeats: repeats)
        let b1 = timeOnce(b, queue: queue, repeats: repeats)
        let a1 = timeOnce(a, queue: queue, repeats: repeats)
        if iteration == 0 { continue }
        let ta = (a0 + a1) / 2
        let tb = (b0 + b1) / 2
        aSamples.append(ta)
        bSamples.append(tb)
        diffs.append(tb - ta)
    }
    let aBytes = Array(UnsafeRawBufferPointer(start: a.attended.contents(),
                                              count: a.outBytes))
    let bBytes = Array(UnsafeRawBufferPointer(start: b.attended.contents(),
                                              count: b.outBytes))
    let observed = diffs.reduce(0, +) / Double(diffs.count)
    var rng = Rng()
    var extreme = 0
    let trials = 100_000
    for _ in 0..<trials {
        var total = 0.0
        for d in diffs { total += (rng.next() & 1) == 0 ? d : -d }
        if abs(total / Double(diffs.count)) >= abs(observed) { extreme += 1 }
    }
    let p = Double(extreme + 1) / Double(trials + 1)
    print("A = \(a.entry)  [\(a.path)]")
    print("B = \(b.entry)  [\(b.path)]")
    print(String(format: "  groups=%d threads/TG=%d repeats=%d pools=%d",
                 a.groups, a.threads, repeats, diffs.count))
    print(String(format: "  A median=%.3fus min=%.3fus", median(aSamples),
                 aSamples.min() ?? .nan))
    print(String(format: "  B median=%.3fus min=%.3fus", median(bSamples),
                 bSamples.min() ?? .nan))
    print(String(format: "  paired mean(B-A)=%+.4fus (%+.3f%%)  "
                 + "median(B-A)=%+.4fus  permutation p=%.5f",
                 observed, 100 * observed / (median(aSamples)),
                 median(diffs), p))
    print("  outputs \(aBytes == bBytes ? "bitwise IDENTICAL" : "DIFFERENT")")
}

let args = Array(CommandLine.arguments.dropFirst())
switch args.first {
case "stats":
    stats(paths: Array(args.dropFirst()))
case "wave":
    let maxGroups = args.count > 1 ? Int(args[1]) ?? 96 : 96
    let iters = args.count > 2 ? UInt32(args[2]) ?? 400_000 : 400_000
    wave(threadCounts: [1024, 512],
         memBytes: [1024, 8192, 9472, 11264, 16384, 18432, 32768],
         maxGroups: maxGroups, iters: iters)
case "resident":
    let groups = args.count > 1 ? Int(args[1]) ?? 128 : 128
    let budget = args.count > 2 ? UInt32(args[2]) ?? 30_000 : 30_000
    resident(threadCounts: [1024, 512, 256],
             memBytes: [1024, 9472, 16384, 18432, 32768],
             groups: groups, budget: budget)
case "bench":
    let rest = Array(args.dropFirst())
    let iterations = Int(ProcessInfo.processInfo
        .environment["TANJIRO_BENCH_ITERS"] ?? "") ?? 400
    bench(paths: rest, iterations: iterations)
case "pair":
    let rest = Array(args.dropFirst())
    let iterations = Int(ProcessInfo.processInfo
        .environment["TANJIRO_BENCH_ITERS"] ?? "") ?? 40
    pair(paths: rest, iterations: iterations)
default:
    die("usage: tanjiro_occ stats FILE.metal... | wave [maxGroups] [iters]"
        + " | resident [groups] [budget] | bench FILE.metal..."
        + " | pair A.metal B.metal")
}
