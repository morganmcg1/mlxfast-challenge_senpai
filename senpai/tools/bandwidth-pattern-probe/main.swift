import Foundation
import Metal

// Achieved DRAM read bandwidth as a function of ACCESS PATTERN and of BYTES PER
// DISPATCH.
//
// A clean streaming probe reports one number (~260 GB/s on this M4 Pro, 95% of
// the 273 GB/s pin). The decode step does not stream: it reads NVFP4 codes 8 B
// per lane from one buffer and their fp8 scales 1 B per lane from a second
// buffer, gathers 8 scattered expert blocks out of 256, walks a ring-buffer KV
// cache, and does all of it in a few hundred small serialized dispatches. Each
// of those deviations has its own achievable ceiling, and a roofline built on
// one global ceiling silently books the difference as "unexplained residual".
//
// Method notes that matter for believing the numbers:
//
//  * Every timed dispatch reads a region no earlier dispatch in the same
//    command buffer read, from pools far larger than any cache, so no
//    measurement is served out of the SLC.
//  * Both pools get full GPU-side warm passes before timing, so first-touch
//    page-table cost is outside the timed window.
//  * Loads are consumed by XOR into registers and stored only on a value that
//    cannot occur, so nothing is dead-code eliminated and the write stream is
//    ~0 bytes.
//  * Time is the GPU timestamp span of one command buffer holding N serialized
//    dispatches, so per-dispatch ramp-up and drain are charged the way MLX
//    charges them.
//  * `min` over repeats. Only within-process comparisons are meaningful.

let device = MTLCreateSystemDefaultDevice()!
let queue = device.makeCommandQueue()!

var args = Array(CommandLine.arguments.dropFirst())
var tgSize = 256
var tgPerCore = 8
var cores = 20
var repeats = 5
var poolMB = 1024
var scalePoolMB = 192
var mode = "report"
var sizesMB: [Double] = [0.125, 0.25, 0.5, 1, 2, 4, 8, 16, 64, 256]
var runKB: [Double] = [0.03125, 0.0625, 0.25, 1, 4, 16, 64, 256, 1024, 1811.94]
var argIndex = 0
while argIndex < args.count {
    switch args[argIndex] {
    case "--tg-size": tgSize = Int(args[argIndex + 1])!; argIndex += 2
    case "--tg-per-core": tgPerCore = Int(args[argIndex + 1])!; argIndex += 2
    case "--cores": cores = Int(args[argIndex + 1])!; argIndex += 2
    case "--repeats": repeats = Int(args[argIndex + 1])!; argIndex += 2
    case "--pool-mb": poolMB = Int(args[argIndex + 1])!; argIndex += 2
    case "--mode": mode = args[argIndex + 1]; argIndex += 2
    case "--sizes":
        sizesMB = args[argIndex + 1].split(separator: ",").map { Double($0)! }
        argIndex += 2
    case "--runs":
        runKB = args[argIndex + 1].split(separator: ",").map { Double($0)! }
        argIndex += 2
    default:
        FileHandle.standardError.write("unknown argument \(args[argIndex])\n".data(using: .utf8)!)
        exit(2)
    }
}

let poolBytes = poolMB << 20
let scalePoolBytes = scalePoolMB << 20
let vecBytes = 16

// MARK: - Kernels

// Sequential, gathered and strided reads. The index table holds the first
// vector of each contiguous run, so:
//   one run                            -> pure sequential
//   shuffled run starts                -> gather (routed experts)
//   ordered starts with a fixed gap     -> strided (per-head KV walk)
let runsSource = """
#include <metal_stdlib>
using namespace metal;

kernel void probe(
    device const uint4* src [[buffer(0)]],
    device const uint* runStart [[buffer(1)]],
    device uint* out [[buffer(2)]],
    constant uint2& p [[buffer(3)]],
    uint gid [[thread_position_in_grid]],
    uint gsz [[threads_per_grid]])
{
    uint4 acc = uint4(0);
    uint total = p.x * p.y;
    for (uint i = gid; i < total; i += gsz) {
        uint r = i / p.x;
        acc ^= src[runStart[r] + (i - r * p.x)];
    }
    uint v = acc.x ^ acc.y ^ acc.z ^ acc.w;
    if (v == 0xFFFFFFFFu) { out[gid] = v; }
}
"""

// The shipped NVFP4 group-16 weight-stream read, arithmetic removed.
// A simdgroup owns `rowsPerSimd` output rows. Per k-block a lane reads `CODE`
// bytes of codes and 1 byte of scale per row, so the 32 lanes cover 32*CODE
// contiguous bytes of each code row and 32 contiguous bytes of each scale row,
// and consecutive k-blocks walk the rows forwards. That is exactly the inner
// loop of LagunaRuntimeModel.swift's laguna_decode_nvfp4_* /
// laguna_routed_nvfp4_* kernels and of MLX fp_qmv_fast_impl, whose lane stride
// is 8 B with a separate `device const uint8_t* scales`.
//
// `rowsPerSimd` is the knob that sets loads in flight per lane, which is what
// decides whether a short-row stream can cover DRAM latency: a 256 B code row
// is one single 8 B load per lane, so with one row per simdgroup the lane has
// nothing else outstanding while it waits.
//   FUSED=0: codes and scales in two buffers, as shipped.
//   FUSED=1: one buffer, each row's scale bytes immediately after its codes.
func qmvSource(codeBytesPerLane: Int, fused: Bool, rowsPerSimd: Int) -> String {
    let loadType = codeBytesPerLane == 16 ? "uint4" : "uint2"
    let scaleLoads = codeBytesPerLane / 8
    let rowStride = fused ? "(g.x + g.y)" : "g.x"
    let issue = (0..<rowsPerSimd).map { j in
        "v[\(j)] = *(const device \(loadType)*)(crow + \(j)u * rowStride + k * codeStep);"
    }.joined(separator: "\n                    ")
    let consume = (0..<rowsPerSimd).map { j in
        "acc[\(j)] ^= v[\(j)];"
            + (0..<scaleLoads).map {
                " sacc ^= uint(srow[\(j)u * scaleRowStride + k * scaleStep + \($0) * 32u]);"
            }.joined()
    }.joined(separator: "\n                    ")
    return """
        #include <metal_stdlib>
        using namespace metal;

        kernel void probe(
            device const uchar* codes [[buffer(0)]],
            device const uchar* scales [[buffer(1)]],
            device uint* out [[buffer(2)]],
            constant uint4& p [[buffer(3)]],
            constant uint4& g [[buffer(4)]],
            uint tid [[thread_position_in_threadgroup]],
            uint tgid [[threadgroup_position_in_grid]],
            uint tgsz [[threads_per_threadgroup]],
            uint ntg [[threadgroups_per_grid]])
        {
            const uint lane = tid & 31u;
            const uint simdsPerTg = tgsz >> 5;
            const uint simdIdx = tgid * simdsPerTg + (tid >> 5);
            const uint nsimds = ntg * simdsPerTg;
            const uint codeStep = 32u * \(codeBytesPerLane)u;
            const uint scaleStep = 32u * \(scaleLoads)u;
            const uint rowStride = \(rowStride);
            const uint scaleRowStride = \(fused ? rowStride : "g.y");
            const uint R = \(rowsPerSimd)u;
            \(loadType) acc[R];
            for (uint j = 0; j < R; ++j) { acc[j] = \(loadType)(0); }
            uint sacc = 0;
            for (uint r = simdIdx * R; r + R <= p.z; r += nsimds * R) {
                const device uchar* crow =
                    codes + p.x + r * rowStride + lane * \(codeBytesPerLane)u;
                const device uchar* srow =
                    \(fused
                        ? "codes + p.x + r * rowStride + g.x"
                        : "scales + p.y + r * scaleRowStride")
                    + lane * \(scaleLoads)u;
                for (uint k = 0; k < p.w; ++k) {
                    \(loadType) v[R];
                    \(issue)
                    \(consume)
                }
            }
            uint value = sacc;
            for (uint j = 0; j < R; ++j) { value ^= acc[j].x ^ acc[j].y; }
            if (value == 0xFFFFFFFFu) { out[tid] = value; }
        }
        """
}

let emptySource = """
#include <metal_stdlib>
using namespace metal;

kernel void probe(
    device uint* out [[buffer(0)]],
    constant uint& p [[buffer(1)]],
    uint gid [[thread_position_in_grid]])
{
    if (p == 0xFFFFFFFFu) { out[gid] = p; }
}
"""

func pipeline(_ source: String) -> MTLComputePipelineState {
    let options = MTLCompileOptions()
    options.fastMathEnabled = false
    let library = try! device.makeLibrary(source: source, options: options)
    return try! device.makeComputePipelineState(function: library.makeFunction(name: "probe")!)
}

let runsPipeline = pipeline(runsSource)
let emptyPipeline = pipeline(emptySource)

var qmvCache = [String: MTLComputePipelineState]()
func qmvPipeline(codeBytesPerLane: Int, fused: Bool, rowsPerSimd: Int)
    -> MTLComputePipelineState
{
    let key = "\(codeBytesPerLane):\(fused):\(rowsPerSimd)"
    if let cached = qmvCache[key] { return cached }
    let built = pipeline(
        qmvSource(codeBytesPerLane: codeBytesPerLane, fused: fused, rowsPerSimd: rowsPerSimd))
    qmvCache[key] = built
    return built
}

// MARK: - Buffers

func makePool(_ bytes: Int) -> MTLBuffer {
    let buffer = device.makeBuffer(length: bytes, options: .storageModeShared)!
    let words = buffer.contents().bindMemory(to: UInt32.self, capacity: bytes / 4)
    var state: UInt64 = 0x243F_6A88_85A3_08D3
    for w in 0..<(bytes / 4) {
        state = state &* 6_364_136_223_846_793_005 &+ 1_442_695_040_888_963_407
        words[w] = UInt32(truncatingIfNeeded: state >> 33)
    }
    return buffer
}

let pool = makePool(poolBytes)
let scalePool = makePool(scalePoolBytes)
let indexCapacity = 1 << 22
let indexBuffer = device.makeBuffer(length: indexCapacity * 4, options: .storageModeShared)!
let outBuffer = device.makeBuffer(
    length: max(cores * tgPerCore * tgSize, 4096) * 4, options: .storageModeShared)!

var rng: UInt64 = 0x9E37_79B9_7F4A_7C15
func nextRandom() -> UInt64 {
    rng ^= rng << 13
    rng ^= rng >> 7
    rng ^= rng << 17
    return rng
}

// MARK: - Timing

var totalThreads: Int { cores * tgPerCore * tgSize }
var tgCount: Int { cores * tgPerCore }

struct Sample {
    let seconds: Double
    let bytes: Int
    let dispatches: Int
    var gbPerSecond: Double { Double(bytes) / seconds / 1e9 }
    var microsecondsPerDispatch: Double { seconds * 1e6 / Double(dispatches) }
}

func timeCommandBuffer(_ encode: (MTLComputeCommandEncoder, Int) -> Void, dispatches: Int)
    -> Double
{
    let buffer = queue.makeCommandBuffer()!
    let encoder = buffer.makeComputeCommandEncoder()!
    for d in 0..<dispatches { encode(encoder, d) }
    encoder.endEncoding()
    buffer.commit()
    buffer.waitUntilCompleted()
    return buffer.gpuEndTime - buffer.gpuStartTime
}

func scalarBuffer<T>(_ value: T) -> MTLBuffer {
    var v = value
    return device.makeBuffer(bytes: &v, length: MemoryLayout<T>.size, options: .storageModeShared)!
}

func measureRuns(
    runBytes: Int, runsPerDispatch: Int, dispatches: Int, shuffle: Bool, gapBytes: Int? = nil,
    rounds: Int? = nil
) -> Sample {
    let runVecs = max(1, runBytes / vecBytes)
    let indices = indexBuffer.contents().bindMemory(to: UInt32.self, capacity: indexCapacity)
    let poolVecs = poolBytes / vecBytes
    let slots = poolVecs / runVecs
    let actualDispatches = max(
        1, min(dispatches, indexCapacity / max(1, runsPerDispatch)))
    let totalRuns = actualDispatches * runsPerDispatch
    if let gap = gapBytes {
        let strideVecs = max(runVecs, gap / vecBytes)
        let span = poolVecs - runVecs
        for r in 0..<totalRuns { indices[r] = UInt32((r * strideVecs) % span) }
    } else if !shuffle {
        for r in 0..<totalRuns { indices[r] = UInt32((r % slots) * runVecs) }
    } else if slots <= 1 << 16 {
        // Few enough slots to permute, so no dispatch re-reads a warm region.
        var order = Array(0..<slots)
        for k in stride(from: slots - 1, to: 0, by: -1) {
            order.swapAt(k, Int(nextRandom() % UInt64(k + 1)))
        }
        for r in 0..<totalRuns { indices[r] = UInt32(order[r % slots] * runVecs) }
    } else {
        // Sampling with replacement; at these slot counts collisions are rare
        // enough not to warm the measurement.
        for r in 0..<totalRuns {
            indices[r] = UInt32(Int(nextRandom() % UInt64(slots)) * runVecs)
        }
    }
    let paramsBuffer = scalarBuffer(SIMD2<UInt32>(UInt32(runVecs), UInt32(runsPerDispatch)))
    let encode: (MTLComputeCommandEncoder, Int) -> Void = { encoder, d in
        encoder.setComputePipelineState(runsPipeline)
        encoder.setBuffer(pool, offset: 0, index: 0)
        encoder.setBuffer(indexBuffer, offset: d * runsPerDispatch * 4, index: 1)
        encoder.setBuffer(outBuffer, offset: 0, index: 2)
        encoder.setBuffer(paramsBuffer, offset: 0, index: 3)
        encoder.dispatchThreadgroups(
            MTLSize(width: tgCount, height: 1, depth: 1),
            threadsPerThreadgroup: MTLSize(width: tgSize, height: 1, depth: 1))
    }
    var best = Double.greatestFiniteMagnitude
    for _ in 0..<(rounds ?? repeats) {
        best = min(best, timeCommandBuffer(encode, dispatches: actualDispatches))
    }
    return Sample(
        seconds: best, bytes: runVecs * vecBytes * runsPerDispatch * actualDispatches,
        dispatches: actualDispatches)
}

// One dispatch reads `rows` rows of `rowCodeBytes` codes plus `rowCodeBytes/8`
// scale bytes, in the shipped lane pattern.
func measureQmv(
    rows: Int, rowCodeBytes: Int, codeBytesPerLane: Int, fused: Bool, dispatches: Int,
    rowsPerSimd: Int = 1, threadsPerGroup: Int = 64, rounds: Int? = nil
) -> Sample {
    let rowScaleBytes = rowCodeBytes / 8
    let kBlocks = rowCodeBytes / (32 * codeBytesPerLane)
    precondition(kBlocks >= 1, "row too short for this lane width")
    let pipe = qmvPipeline(
        codeBytesPerLane: codeBytesPerLane, fused: fused, rowsPerSimd: rowsPerSimd)
    let codeStride = rows * (fused ? rowCodeBytes + rowScaleBytes : rowCodeBytes)
    let scaleStride = rows * rowScaleBytes
    let codeSpan = fused ? poolBytes - codeStride : poolBytes - codeStride
    let scaleSpan = scalePoolBytes - scaleStride
    var paramBuffers = [MTLBuffer]()
    for d in 0..<dispatches {
        paramBuffers.append(
            scalarBuffer(
                SIMD4<UInt32>(
                    UInt32(((d * codeStride) % max(1, codeSpan)) / 16 * 16),
                    UInt32(((d * scaleStride) % max(1, scaleSpan)) / 16 * 16),
                    UInt32(rows), UInt32(kBlocks))))
    }
    let geometry = scalarBuffer(
        SIMD4<UInt32>(UInt32(rowCodeBytes), UInt32(rowScaleBytes), 0, 0))
    let groups = max(1, rows / ((threadsPerGroup / 32) * rowsPerSimd))
    let encode: (MTLComputeCommandEncoder, Int) -> Void = { encoder, d in
        encoder.setComputePipelineState(pipe)
        encoder.setBuffer(pool, offset: 0, index: 0)
        encoder.setBuffer(fused ? pool : scalePool, offset: 0, index: 1)
        encoder.setBuffer(outBuffer, offset: 0, index: 2)
        encoder.setBuffer(paramBuffers[d], offset: 0, index: 3)
        encoder.setBuffer(geometry, offset: 0, index: 4)
        encoder.dispatchThreadgroups(
            MTLSize(width: groups, height: 1, depth: 1),
            threadsPerThreadgroup: MTLSize(width: threadsPerGroup, height: 1, depth: 1))
    }
    var best = Double.greatestFiniteMagnitude
    for _ in 0..<(rounds ?? repeats) {
        best = min(best, timeCommandBuffer(encode, dispatches: dispatches))
    }
    return Sample(
        seconds: best, bytes: rows * (rowCodeBytes + rowScaleBytes) * dispatches,
        dispatches: dispatches)
}

func measureEmpty(dispatches: Int) -> Double {
    let paramsBuffer = scalarBuffer(UInt32(0))
    let encode: (MTLComputeCommandEncoder, Int) -> Void = { encoder, _ in
        encoder.setComputePipelineState(emptyPipeline)
        encoder.setBuffer(outBuffer, offset: 0, index: 0)
        encoder.setBuffer(paramsBuffer, offset: 0, index: 1)
        encoder.dispatchThreadgroups(
            MTLSize(width: tgCount, height: 1, depth: 1),
            threadsPerThreadgroup: MTLSize(width: tgSize, height: 1, depth: 1))
    }
    var best = Double.greatestFiniteMagnitude
    for _ in 0..<repeats { best = min(best, timeCommandBuffer(encode, dispatches: dispatches)) }
    return best / Double(dispatches)
}

// First touch of both pools, then a sustained load so the GPU is at its steady
// clock before anything is timed. Without the sustained part the first timed
// configuration reads 35% low and the whole table is ordered by warm-up.
func warmPools() {
    _ = measureRuns(
        runBytes: poolBytes / 8, runsPerDispatch: 1, dispatches: 8, shuffle: false, rounds: 1)
    _ = measureQmv(
        rows: 16384, rowCodeBytes: 1024, codeBytesPerLane: 8, fused: false, dispatches: 8,
        rounds: 1)
    let start = Date()
    while Date().timeIntervalSince(start) < 0.5 {
        _ = measureRuns(
            runBytes: 32 << 20, runsPerDispatch: 1, dispatches: 8, shuffle: false, rounds: 1)
    }
}

func dispatchesFor(bytesPerDispatch: Int, budget: Int = 512 << 20) -> Int {
    max(2, min(512, budget / max(1, bytesPerDispatch)))
}

func report(_ label: String, _ sample: Sample, control: Double?) {
    let frac = control.map { String(format: "   %5.1f%% of control", 100 * sample.gbPerSecond / $0) }
        ?? ""
    print(
        String(
            format: "  %-40@ %7.1f GB/s  %8.2f us/dispatch%@", label as NSString,
            sample.gbPerSecond, sample.microsecondsPerDispatch, frac as NSString))
}

print("device: \(device.name), assumed cores \(cores)")
print(
    "runs/sizes grid: \(tgCount) x \(tgSize) = \(totalThreads) threads; "
        + "qmv grid: shipped 64-thread groups, one row per simdgroup")
print("pools: \(poolMB) MB codes + \(scalePoolMB) MB scales, repeats \(repeats), min statistic\n")
warmPools()
warmPools()

switch mode {
case "sizes":
    print("== sequential read: bandwidth vs bytes per dispatch (serialized in one command buffer) ==")
    var best = 0.0
    for mb in sizesMB {
        let bytes = Int(mb * 1_048_576) / vecBytes * vecBytes
        let n = dispatchesFor(bytesPerDispatch: bytes)
        let s = measureRuns(runBytes: bytes, runsPerDispatch: 1, dispatches: n, shuffle: true)
        best = max(best, s.gbPerSecond)
        print(
            String(
                format: "  %9.3f MB/dispatch x%3d   %7.1f GB/s  %8.2f us/dispatch", mb,
                s.dispatches, s.gbPerSecond, s.microsecondsPerDispatch))
    }
    print(String(format: "\n  best %.1f GB/s", best))

case "runs":
    print("== random-order contiguous runs: bandwidth vs run length ==")
    for kb in runKB {
        let runBytes = max(vecBytes, Int(kb * 1024) / vecBytes * vecBytes)
        let runsPerDispatch = max(1, (8 << 20) / runBytes)
        let n = dispatchesFor(bytesPerDispatch: runBytes * runsPerDispatch)
        let s = measureRuns(
            runBytes: runBytes, runsPerDispatch: runsPerDispatch, dispatches: n, shuffle: true)
        print(
            String(
                format: "  run %9.3f KB x%6d runs x%3d   %7.1f GB/s", kb, runsPerDispatch,
                s.dispatches, s.gbPerSecond))
    }

case "empty":
    for n in [1, 2, 4, 8, 16, 32, 64, 128, 256] {
        print(String(format: "  %4d serialized empty dispatches: %8.3f us each", n, measureEmpty(dispatches: n) * 1e6))
    }

case "downshape":
    // laguna_routed_shared_nvfp4_down_residual: 288-thread groups (9
    // simdgroups: 8 routed expert slots plus the shared expert), 4 output rows
    // per simdgroup, 256 B code rows, one 512-value k-block, 512 groups,
    // 5.311 MB per dispatch. Measured on the scored path at 109.5 GB/s = 42% of
    // the streaming ceiling. This strips the kernel to its reads alone and then
    // varies one structural parameter at a time.
    print("== routed-down dispatch shape: reads only, one parameter at a time ==")
    for (label, threads, rowsPerSimd, groups) in [
        ("shipped: 288 thr, 4 rows/simd, 512 groups", 288, 4, 512),
        ("288 thr, 4 rows/simd, 1024 groups", 288, 4, 1024),
        ("288 thr, 4 rows/simd, 2048 groups", 288, 4, 2048),
        ("288 thr, 1 row /simd, 512 groups", 288, 1, 512),
        ("288 thr, 8 rows/simd, 512 groups", 288, 8, 512),
        ("288 thr, 16 rows/simd, 512 groups", 288, 16, 512),
        ("1024 thr, 4 rows/simd, 512 groups", 1024, 4, 512),
        ("64 thr, 4 rows/simd, 512 groups", 64, 4, 512),
    ] {
        let rows = groups * (threads / 32) * rowsPerSimd
        let bytes = rows * 288
        let n = dispatchesFor(bytesPerDispatch: bytes)
        let s = measureQmv(
            rows: rows, rowCodeBytes: 256, codeBytesPerLane: 8, fused: false, dispatches: n,
            rowsPerSimd: rowsPerSimd, threadsPerGroup: threads)
        print(
            String(
                format: "  %-42@ %6.2f MB  %7.1f GB/s  %8.2f us", label as NSString,
                Double(bytes) / 1_048_576, s.gbPerSecond, s.microsecondsPerDispatch))
    }

case "downsize":
    // Same 18432 rows of 256 B codes + 32 B scales = 5.06 MB, the routed-down
    // dispatch's real byte count, under every threads/rows-per-simdgroup shape.
    // This is the achievable read ceiling for that stream at its real size.
    print("== routed-down bytes fixed at 5.06 MB, shape swept ==")
    let downRows = 18432
    let n = dispatchesFor(bytesPerDispatch: downRows * 288)
    for threads in [64, 128, 256, 288, 512, 1024] {
        var lineText = String(format: "  %4d thr:", threads)
        for r in [1, 2, 4, 8, 16] {
            let simds = threads / 32
            guard downRows % (simds * r) == 0 else { continue }
            let groups = downRows / (simds * r)
            let s = measureQmv(
                rows: downRows, rowCodeBytes: 256, codeBytesPerLane: 8, fused: false,
                dispatches: n, rowsPerSimd: r, threadsPerGroup: threads)
            lineText += String(format: "  R%-2d %5.0fg %6.1f", r, Double(groups), s.gbPerSecond)
        }
        print(lineText)
    }

case "tune":
    print("== control tuning: threadgroup size x groups per core, 64 MB/dispatch ==")
    for size in [64, 128, 256, 512, 1024] {
        for perCore in [1, 2, 4, 8, 16] {
            tgSize = size
            tgPerCore = perCore
            let s = measureRuns(
                runBytes: 64 << 20, runsPerDispatch: 1, dispatches: 8, shuffle: true, rounds: 3)
            print(String(format: "  %4d threads x %2d/core   %7.1f GB/s", size, perCore, s.gbPerSecond))
        }
    }

default:
    let control = measureRuns(
        runBytes: 128 << 20, runsPerDispatch: 1, dispatches: 8, shuffle: true)
    print("== control ==")
    report("sequential, 128 MB/dispatch", control, control: nil)
    let ceiling = control.gbPerSecond

    print("\n== NVFP4 g16 weight stream, shipped lane pattern ==")
    // routed gate/up: 1024 B code rows, 128 B scale rows (1 MiB + 128 KiB per
    // expert); routed down: 256 B code rows; attention: 2048 B code rows.
    for (name, rowCodeBytes, rows, shippedR) in [
        ("routed gate/up 1024 B rows", 1024, 8192, 1),
        ("routed down 256 B rows", 256, 32768, 4),
        ("attention 2048 B rows", 2048, 4096, 1),
    ] {
        let bytes = rows * (rowCodeBytes + rowCodeBytes / 8)
        let n = dispatchesFor(bytesPerDispatch: bytes)
        print(String(format: "  %@, %.2f MB/dispatch x%d", name, Double(bytes) / 1_048_576, n))
        for r in [1, 2, 4, 8, 16] where rows % (2 * r) == 0 {
            let split = measureQmv(
                rows: rows, rowCodeBytes: rowCodeBytes, codeBytesPerLane: 8, fused: false,
                dispatches: n, rowsPerSimd: r)
            report(
                "    \(r) row\(r == 1 ? " " : "s")/simdgroup, split"
                    + (r == shippedR ? " (shipped)" : ""), split, control: ceiling)
        }
        let fused = measureQmv(
            rows: rows, rowCodeBytes: rowCodeBytes, codeBytesPerLane: 8, fused: true,
            dispatches: n, rowsPerSimd: shippedR)
        let shipped = measureQmv(
            rows: rows, rowCodeBytes: rowCodeBytes, codeBytesPerLane: 8, fused: false,
            dispatches: n, rowsPerSimd: shippedR)
        report("    scales fused into code rows", fused, control: ceiling)
        if rowCodeBytes >= 512 {
            let wide = measureQmv(
                rows: rows, rowCodeBytes: rowCodeBytes, codeBytesPerLane: 16, fused: false,
                dispatches: n, rowsPerSimd: shippedR)
            report("    16 B per lane per k-block", wide, control: ceiling)
        }
        print(
            String(
                format: "    fusing scales: %+.2f%% of this stream's time",
                100 * (fused.seconds - shipped.seconds) / shipped.seconds))
    }

    // Scattered-block reads at a fixed ~9 MB per dispatch, so run length is the
    // only variable and the small-dispatch penalty cannot masquerade as a
    // gather penalty.
    print("\n== scattered blocks at fixed 9 MB per dispatch ==")
    for kb in [1811.94, 1024.0, 512.0, 256.0, 64.0, 16.0] {
        let runBytes = Int(kb * 1024) / vecBytes * vecBytes
        let runsPerDispatch = max(8, (9 << 20) / runBytes)
        let n = dispatchesFor(bytesPerDispatch: runBytes * runsPerDispatch)
        let s = measureRuns(
            runBytes: runBytes, runsPerDispatch: runsPerDispatch, dispatches: n, shuffle: true)
        report(
            String(format: "%d x %.0f KB scattered", runsPerDispatch, kb), s, control: ceiling)
    }

    print("\n== KV walk: 256 B per position per head ==")
    for (runs, label) in [(8192, "2 MB/dispatch, shipped size"), (32768, "8 MB/dispatch")] {
        for strideBytes in [256, 2048, 8192] {
            let n = dispatchesFor(bytesPerDispatch: 256 * runs)
            let s = measureRuns(
                runBytes: 256, runsPerDispatch: runs, dispatches: n, shuffle: false,
                gapBytes: strideBytes)
            report("256 B every \(strideBytes) B, \(label)", s, control: ceiling)
        }
    }

    print("\n== serialized dispatch floor ==")
    let us = measureEmpty(dispatches: 128)
    print(String(format: "  empty dispatch, 128 back to back: %.3f us each", us * 1e6))
    print(String(format: "  324 decode dispatches at that floor: %.3f ms", 324 * us * 1000))
}
