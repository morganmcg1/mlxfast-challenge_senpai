// Research-only host probe (not part of the submission surface).
//
// Step 0 of the queued sliding-attention rewrite brief
// (research/BRIEF_QUEUED_SLIDING_ATTN_REWRITE.md): establish, from a compiled
// MTLComputePipelineState and from the device rather than from arithmetic,
// which resource actually binds threadgroup residency for the two fused decode
// attention kernels.
//
// Phase A reads the two kernel bodies straight out of the scored source
// (`Sources/MLXFastModel/LagunaRuntimeModel.swift`) instead of copying them, so
// the probe cannot drift from the kernel it claims to measure. The [[kernel]]
// signature is a replica of the one MLX's JIT generates in
// `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/common/metal_kernel.cpp`
// `write_signature` (:85-158, attribute table :221-250, constant-vs-device
// threshold `max_constant_array_size = 8` at :19), with the input dtypes and
// element counts taken from the two Swift wrappers (:1758-1803, :2272-2320).
// It prints `staticThreadgroupMemoryLength`, `maxTotalThreadsPerThreadgroup`
// and `threadExecutionWidth` -- the three pipeline properties Metal exposes
// (`Vendor/mlx-swift/Source/Cmlx/metal-cpp/Metal/MTLComputePipeline.hpp`
// :148-167); MLX itself only ever reads the second one
// (`backend/metal/custom_kernel.cpp:104-112`).
//
// Phases B and C measure how many threadgroups are actually co-resident, using
// a cooperative rendezvous rather than a sampled counter or a timing model.
// Dispatch exactly K threadgroups; each threadgroup's leader thread increments
// a device counter once and then spins until the counter reaches K or a bounded
// timeout expires, while every other thread in the threadgroup waits on a
// threadgroup barrier (so no simdgroup can retire early and hand its slot
// back). The rendezvous succeeds for *every* threadgroup if and only if all K
// are resident at the same time: if only R < K fit, the first R leaders time
// out and record a failure, and only later waves can see the counter reach K.
// "All K succeeded" is therefore monotone in K, so a binary search finds the
// exact maximum, and the answer is a pass/fail fact rather than an estimate.
//
// Phase B sweeps a synthetic kernel over *statically* declared threadgroup
// memory and threadgroup width to expose the machine's residency curve. Phase C
// runs the same rendezvous inside the real extracted sliding-attention body, so
// register pressure and threadgroup memory are the shipped kernel's, and
// repeats it with the epilogue plane count halved as a resource counterfactual
// for the brief's R1/R4 variants.
//
// Build and run:
//   xcrun swiftc -O research/nezuko_occupancy_probe.swift -o /tmp/nezocc \
//     && /tmp/nezocc [path-to-LagunaRuntimeModel.swift]

import Foundation
import Metal

// MARK: - Phase A: extract the real kernel bodies from the scored source

/// Slices a Swift multiline string literal introduced by `label: """` out of
/// `lines`, starting the search at `from`. Returns the dedented, unescaped
/// contents and the index of the closing delimiter line.
func extractLiteral(
    _ lines: [String], label: String, from: Int
) -> (text: String, closeIndex: Int) {
    var open = -1
    var i = from
    while i < lines.count {
        if lines[i].trimmingCharacters(in: .whitespaces) == "\(label): \"\"\"" {
            open = i
            break
        }
        i += 1
    }
    precondition(open >= 0, "no `\(label): \"\"\"` after line \(from + 1)")

    var close = -1
    i = open + 1
    while i < lines.count {
        let t = lines[i].trimmingCharacters(in: .whitespaces)
        if t == "\"\"\"," || t == "\"\"\"" {
            close = i
            break
        }
        i += 1
    }
    precondition(close >= 0, "unterminated `\(label)` literal at line \(open + 1)")

    // Swift strips the closing delimiter's indentation from every line.
    let indent = lines[close].prefix(while: { $0 == " " }).count
    let body = lines[(open + 1)..<close].map { line -> String in
        var l = line
        var stripped = 0
        while stripped < indent, l.first == " " {
            l.removeFirst()
            stripped += 1
        }
        // The only escape used in these literals is a doubled backslash for
        // macro line continuations; assert that before undoing it.
        precondition(
            !l.contains("\\(") && !l.replacingOccurrences(of: "\\\\", with: "").contains("\\"),
            "unexpected escape in kernel literal: \(l)")
        return l.replacingOccurrences(of: "\\\\", with: "\\")
    }
    return (body.joined(separator: "\n"), close)
}

struct ExtractedKernel {
    let name: String
    let header: String
    let body: String
    let sourceLines: Int
}

func extractKernel(_ lines: [String], name: String) -> ExtractedKernel {
    var decl = -1
    for (i, l) in lines.enumerated() where l.contains("name: \"\(name)\"") {
        decl = i
        break
    }
    precondition(decl >= 0, "kernel declaration `\(name)` not found")
    let src = extractLiteral(lines, label: "source", from: decl)
    let hdr = extractLiteral(lines, label: "header", from: src.closeIndex)
    let count = src.text.split(separator: "\n", omittingEmptySubsequences: false).count
    return ExtractedKernel(
        name: name, header: hdr.text, body: src.text, sourceLines: count)
}

/// Replica of the signature MLX's JIT emits for both fused attention kernels.
/// Both take the same ten inputs and one output; `params` (1 or 3 elements) and
/// `scale_arr` (1 element) fall under `max_constant_array_size`, which is why
/// the mangled MTLFunction name carries `..._uint32_tc_floatc_...`.
func mlxSignature(_ name: String, extraBuffers: Bool) -> String {
    var s = "[[kernel]] void custom_kernel_\(name)(\n"
    s += "  const device bfloat16_t* raw_queries [[buffer(0)]],\n"
    s += "  const device bfloat16_t* raw_keys [[buffer(1)]],\n"
    s += "  const device bfloat16_t* raw_values [[buffer(2)]],\n"
    s += "  const device bfloat16_t* query_weight [[buffer(3)]],\n"
    s += "  const device bfloat16_t* key_weight [[buffer(4)]],\n"
    s += "  const device float* angles [[buffer(5)]],\n"
    s += "  const device bfloat16_t* k_cache [[buffer(6)]],\n"
    s += "  const device bfloat16_t* v_cache [[buffer(7)]],\n"
    s += "  const constant uint32_t* params [[buffer(8)]],\n"
    s += "  const constant float* scale_arr [[buffer(9)]],\n"
    s += "  device bfloat16_t* attended [[buffer(10)]],\n"
    if extraBuffers {
        s += "  device atomic_uint* db_counter [[buffer(11)]],\n"
        s += "  device uint* db_ok [[buffer(12)]],\n"
        s += "  const constant uint2* db_cfg [[buffer(13)]],\n"
    }
    // Attribute order follows metal_kernel.cpp's fixed table, not source order.
    s += "  uint simdgroup_index_in_threadgroup [[simdgroup_index_in_threadgroup]],\n"
    s += "  uint thread_index_in_simdgroup [[thread_index_in_simdgroup]],\n"
    if extraBuffers {
        s += "  uint db_tid [[thread_index_in_threadgroup]],\n"
    }
    s += "  uint3 threadgroup_position_in_grid [[threadgroup_position_in_grid]]) {\n"
    return s
}

let preamble = """
    #include <metal_stdlib>
    #include <metal_simdgroup>
    using namespace metal;
    typedef bfloat bfloat16_t;

    """

let device = MTLCreateSystemDefaultDevice()!
let arch = device.architecture.name

print("=== device ===")
print("name                             \(device.name)")
print("architecture.name                \(arch)")
print("maxThreadsPerThreadgroup         \(device.maxThreadsPerThreadgroup)")
print("maxThreadgroupMemoryLength       \(device.maxThreadgroupMemoryLength) B"
    + "  (\(String(format: "%.2f", Double(device.maxThreadgroupMemoryLength) / 1024.0)) KiB)")
print("recommendedMaxWorkingSetSize     \(device.recommendedMaxWorkingSetSize) B")
print("hasUnifiedMemory                 \(device.hasUnifiedMemory)")
for f in [MTLGPUFamily.apple7, .apple8, .apple9, .metal3] {
    print("supportsFamily(\(f))              \(device.supportsFamily(f))")
}

let sourcePath =
    CommandLine.arguments.count > 1
    ? CommandLine.arguments[1] : "Sources/MLXFastModel/LagunaRuntimeModel.swift"
let scoredLines = try! String(contentsOfFile: sourcePath, encoding: .utf8)
    .split(separator: "\n", omittingEmptySubsequences: false).map(String.init)
print("\nscored source                    \(sourcePath) (\(scoredLines.count) lines)")

let kernels = [
    extractKernel(scoredLines, name: "laguna_sliding_fused_attn_ring_v1"),
    extractKernel(scoredLines, name: "laguna_full_fused_attn_grow_v1"),
]

print("\n=== Phase A: compiled pipeline properties (real kernel bodies) ===")
for k in kernels {
    let msl = preamble + k.header + "\n" + mlxSignature(k.name, extraBuffers: false)
        + k.body + "\n}\n"
    print("\n\(k.name)")
    print("  extracted source lines         \(k.sourceLines)")
    print("  assembled MSL bytes            \(msl.utf8.count)")
    do {
        let lib = try device.makeLibrary(source: msl, options: nil)
        let fn = lib.makeFunction(name: "custom_kernel_\(k.name)")!
        let pipe = try device.makeComputePipelineState(function: fn)
        print("  staticThreadgroupMemoryLength  \(pipe.staticThreadgroupMemoryLength) B"
            + "  (\(String(format: "%.3f", Double(pipe.staticThreadgroupMemoryLength) / 1024.0)) KiB)")
        print("  maxTotalThreadsPerThreadgroup  \(pipe.maxTotalThreadsPerThreadgroup)"
            + (pipe.maxTotalThreadsPerThreadgroup < 1024
                ? "   *** BELOW THE 1024 THE KERNEL IS DISPATCHED WITH ***" : "   (>= dispatched 1024)"))
        print("  threadExecutionWidth           \(pipe.threadExecutionWidth)")
        let tgmemShare = Double(pipe.staticThreadgroupMemoryLength)
            / Double(device.maxThreadgroupMemoryLength)
        print("  tgmem / device tgmem limit     \(String(format: "%.3f", tgmemShare))"
            + "  -> tgmem alone permits \(Int(1.0 / max(tgmemShare, 1e-9))) TG/core")
        let simdgroups = 1024 / pipe.threadExecutionWidth
        print("  simdgroups in a 1024-thread TG \(simdgroups)")
    } catch {
        print("  COMPILE FAILED: \(error)")
    }
}

// MARK: - Rendezvous residency harness

/// GPU core count, read from the same place the roofline notes read it.
func gpuCoreCount() -> Int {
    let p = Process()
    p.executableURL = URL(fileURLWithPath: "/usr/sbin/system_profiler")
    p.arguments = ["-json", "SPDisplaysDataType"]
    let pipe = Pipe()
    p.standardOutput = pipe
    p.standardError = FileHandle.nullDevice
    try? p.run()
    let data = pipe.fileHandleForReading.readDataToEndOfFile()
    p.waitUntilExit()
    guard let s = String(data: data, encoding: .utf8) else { return 0 }
    for line in s.split(separator: "\n") where line.contains("sppci_cores") {
        return Int(line.filter { $0.isNumber }) ?? 0
    }
    return 0
}

let cores = gpuCoreCount()
let queue = device.makeCommandQueue()!
print("\nGPU cores (system_profiler)      \(cores)")

// A failed rendezvous costs `timeoutSpins` relaxed atomic loads per wave, so
// keep the product of waves and spins far below the GPU watchdog.
let timeoutSpins: UInt32 = 500_000
let okSlots = 1024
let counterBuf = device.makeBuffer(length: 4, options: .storageModeShared)!
let okBuf = device.makeBuffer(length: okSlots * 4, options: .storageModeShared)!
let cfgBuf = device.makeBuffer(length: 8, options: .storageModeShared)!

/// The kernel writes bit 1 unconditionally and bit 0 on a successful
/// rendezvous, so a slot that was never written is a failure, not a pass.
func rendezvous(
    _ pipe: MTLComputePipelineState, k: Int, threads: Int,
    bind: (MTLComputeCommandEncoder) -> Void
) -> (pass: Bool, passing: Int, ms: Double) {
    counterBuf.contents().bindMemory(to: UInt32.self, capacity: 1)[0] = 0
    let ok = okBuf.contents().bindMemory(to: UInt32.self, capacity: okSlots)
    for i in 0..<okSlots { ok[i] = 0 }
    let cfg = cfgBuf.contents().bindMemory(to: UInt32.self, capacity: 2)
    cfg[0] = UInt32(k)
    cfg[1] = timeoutSpins

    let cb = queue.makeCommandBuffer()!
    let enc = cb.makeComputeCommandEncoder()!
    enc.setComputePipelineState(pipe)
    bind(enc)
    enc.dispatchThreadgroups(
        MTLSize(width: k, height: 1, depth: 1),
        threadsPerThreadgroup: MTLSize(width: threads, height: 1, depth: 1))
    enc.endEncoding()
    let t0 = Date()
    cb.commit()
    cb.waitUntilCompleted()
    let ms = Date().timeIntervalSince(t0) * 1000.0
    if let e = cb.error { print("  command buffer error: \(e)") }
    var passing = 0
    for i in 0..<k where ok[i] & 3 == 3 { passing += 1 }
    return (passing == k, passing, ms)
}

/// Binary search for the largest K whose rendezvous succeeds. `capped` means the
/// search hit `kCap`, i.e. the true residency is at least that large.
func maxResident(
    _ pipe: MTLComputePipelineState, threads: Int, kCap: Int,
    bind: (MTLComputeCommandEncoder) -> Void
) -> (k: Int, capped: Bool, maxMs: Double) {
    var maxMs = 0.0
    func passes(_ k: Int) -> Bool {
        let r = rendezvous(pipe, k: k, threads: threads, bind: bind)
        maxMs = max(maxMs, r.ms)
        return r.pass
    }
    guard passes(1) else { return (0, false, maxMs) }
    if passes(kCap) { return (kCap, true, maxMs) }
    var lo = 1
    var hi = kCap  // invariant: lo passes, hi fails
    while hi - lo > 1 {
        let mid = (lo + hi) / 2
        if passes(mid) { lo = mid } else { hi = mid }
    }
    return (lo, false, maxMs)
}

/// Enough headroom above the 96-simdgroups-per-core hypothesis to detect a
/// higher limit, while keeping the cost of a failing dispatch bounded.
func searchCap(threads: Int) -> Int {
    min(okSlots, max(4 * max(cores, 1) * (1024 / threads), 64))
}

func residencyLine(_ label: String, k: Int, capped: Bool, threads: Int, ms: Double)
    -> String
{
    let perCore = cores > 0 ? Double(k) / Double(cores) : 0
    let sgPerCore = perCore * Double(threads / 32)
    let name = label.padding(toLength: max(30, label.count), withPad: " ", startingAt: 0)
    return "  " + name + String(
        format: " %4d%@   %6.2f   %7.1f   %7.1f", k, capped ? "+" : " ", perCore,
        sgPerCore, ms)
}

let residencyHeader =
    "  variant                       maxK   TG/core   sg/core   maxMs"

/// Independent, single-dispatch capacity estimate. With `k` far above the true
/// residency every wave times out except the one that finally pushes the counter
/// to `k`, so the number of slots reporting success approximates how many
/// threadgroups were co-resident at that moment.
func oversubscribed(
    _ pipe: MTLComputePipelineState, threads: Int, k: Int,
    bind: (MTLComputeCommandEncoder) -> Void
) -> String {
    let r = rendezvous(pipe, k: k, threads: threads, bind: bind)
    let perCore = cores > 0 ? Double(r.passing) / Double(cores) : 0
    return String(
        format: " %5d   %5d   %6.2f   %7.1f   %7.1f", k, r.passing, perCore,
        perCore * Double(threads / 32), r.ms)
}

let oversubHeader =
    "  variant                           K   passed   TG/core   sg/core      ms"

func padLabel(_ s: String) -> String {
    "  " + s.padding(toLength: max(30, s.count), withPad: " ", startingAt: 0)
}

// MARK: - Phase B: synthetic residency curve over static threadgroup memory

/// `flag` is written by the leader and read by a *different* thread after the
/// barrier, so neither the barrier nor the threadgroup allocation can be
/// elided, and the device store is performed by a non-leader thread -- proof
/// that thread is still resident while the leader was spinning.
func synthSource(bytes: Int, threads: Int) -> String {
    let scratch = max(bytes - 4, 4)
    return """
        #include <metal_stdlib>
        using namespace metal;
        kernel void rendez(device atomic_uint* counter [[buffer(0)]],
                           device uint* ok [[buffer(1)]],
                           const constant uint2* cfg [[buffer(2)]],
                           uint tid [[thread_index_in_threadgroup]],
                           uint3 tgpig [[threadgroup_position_in_grid]]) {
            threadgroup uchar scratch[\(scratch)];
            threadgroup uint flag[1];
            const uint K = cfg[0].x;
            const uint timeout = cfg[0].y;
            for (uint j = tid; j < \(scratch)u; j += \(threads)u) {
                scratch[j] = uchar(j + timeout);
            }
            threadgroup_barrier(mem_flags::mem_threadgroup);
            if (tid == 0u) {
                uint mine = atomic_fetch_add_explicit(counter, 1u, memory_order_relaxed) + 1u;
                bool reached = mine >= K;
                for (uint s = 0u; !reached && s < timeout; ++s) {
                    reached = atomic_load_explicit(counter, memory_order_relaxed) >= K;
                }
                flag[0] = (reached ? 1u : 0u) | 2u | (uint(scratch[\(scratch)u - 1u]) << 8);
            }
            threadgroup_barrier(mem_flags::mem_threadgroup);
            if (tid == \(threads)u - 1u) { ok[tgpig.x] = flag[0]; }
        }
        """
}

print("\n=== Phase B: synthetic residency vs static threadgroup memory ===")
print("timeout \(timeoutSpins) spins; a trailing `+` means residency >= the search cap.")
print(residencyHeader)
// 9984 B is the sliding kernel's footprint with two epilogue planes instead of
// four; 18432 B is what Phase A measures for both shipped kernels; 32768 B is
// the device's per-threadgroup API maximum.
for threads in [1024, 512, 256, 128] {
    for bytes in [16, 9984, 18432, 32768]
    where bytes <= device.maxThreadgroupMemoryLength {
        let src = synthSource(bytes: bytes, threads: threads)
        guard let lib = try? device.makeLibrary(source: src, options: nil),
            let fn = lib.makeFunction(name: "rendez"),
            let pipe = try? device.makeComputePipelineState(function: fn)
        else {
            print("  \(threads)t \(bytes)B  COMPILE/PIPELINE FAILED")
            continue
        }
        guard pipe.maxTotalThreadsPerThreadgroup >= threads else {
            print("  \(threads)t \(bytes)B  maxTotalThreadsPerThreadgroup "
                + "\(pipe.maxTotalThreadsPerThreadgroup) < \(threads), skipped")
            continue
        }
        let r = maxResident(pipe, threads: threads, kCap: searchCap(threads: threads)) { enc in
            enc.setBuffer(counterBuf, offset: 0, index: 0)
            enc.setBuffer(okBuf, offset: 0, index: 1)
            enc.setBuffer(cfgBuf, offset: 0, index: 2)
        }
        let label = "\(threads)t static \(pipe.staticThreadgroupMemoryLength)B"
        print(residencyLine(label, k: r.k, capped: r.capped, threads: threads, ms: r.maxMs))
    }
}

// MARK: - Phase C: residency of the real sliding-attention body

/// Rendezvous prologue injected ahead of the real kernel body. It adds one
/// 4-byte threadgroup word and no threadgroup array, so the shipped kernel's
/// register pressure and 18432 B of threadgroup memory are what gets measured.
let realPrologue = """
    threadgroup uint db_flag[1];
    const uint db_K = db_cfg[0].x;
    const uint db_timeout = db_cfg[0].y;
    if (db_tid == 0u) {
        uint db_mine = atomic_fetch_add_explicit(db_counter, 1u, memory_order_relaxed) + 1u;
        bool db_reached = db_mine >= db_K;
        for (uint db_s = 0u; !db_reached && db_s < db_timeout; ++db_s) {
            db_reached = atomic_load_explicit(db_counter, memory_order_relaxed) >= db_K;
        }
        db_flag[0] = (db_reached ? 1u : 0u) | 2u;
    }
    threadgroup_barrier(mem_flags::mem_threadgroup);
    if (db_tid == 1u) { db_ok[threadgroup_position_in_grid.x] = db_flag[0]; }
    threadgroup_barrier(mem_flags::mem_threadgroup);

    """

/// Buffers sized for the largest threadgroup index the search can dispatch:
/// `head0 = 2 * tg` and `kv_head = head0 / 8`, so 256 threadgroups need 512 Q
/// heads and 64 KV heads. bfloat lanes are filled with 1.0 (0x3F80) so the
/// RMSNorm `rsqrt` never sees a zero sum.
func makeBF16(_ elements: Int) -> MTLBuffer {
    let buf = device.makeBuffer(length: elements * 2, options: .storageModeShared)!
    let p = buf.contents().bindMemory(to: UInt16.self, capacity: elements)
    for i in 0..<elements { p[i] = 0x3F80 }
    return buf
}

let cHeads = 512
let cKV = 128
let cDim = 128
let cWindow = 512
let dRawQ = makeBF16(cHeads * cDim)
let dRawK = makeBF16(cKV * cDim)
let dRawV = makeBF16(cKV * cDim)
let dQW = makeBF16(cDim)
let dKW = makeBF16(cDim)
let dKCache = makeBF16(cKV * cWindow * cDim)
let dVCache = makeBF16(cKV * cWindow * cDim)
let dAttended = makeBF16(cHeads * cDim)
let dAngles = device.makeBuffer(length: cDim * 4, options: .storageModeShared)!
for i in 0..<cDim {
    dAngles.contents().bindMemory(to: Float.self, capacity: cDim)[i] = 0.5
}
let dParams = device.makeBuffer(length: 4, options: .storageModeShared)!
dParams.contents().bindMemory(to: UInt32.self, capacity: 1)[0] = 0
let dScale = device.makeBuffer(length: 4, options: .storageModeShared)!
dScale.contents().bindMemory(to: Float.self, capacity: 1)[0] = 0.088_388_35

func bindReal(_ enc: MTLComputeCommandEncoder) {
    for (i, b) in [dRawQ, dRawK, dRawV, dQW, dKW, dAngles, dKCache, dVCache,
        dParams, dScale, dAttended].enumerated()
    {
        enc.setBuffer(b, offset: 0, index: i)
    }
    enc.setBuffer(counterBuf, offset: 0, index: 11)
    enc.setBuffer(okBuf, offset: 0, index: 12)
    enc.setBuffer(cfgBuf, offset: 0, index: 13)
}

print("\n=== Phase C: residency of the real sliding-attention body ===")
print("`planes/2` halves the epilogue threadgroup buffer only as a *resource*")
print("counterfactual; it is deliberately not a functionally correct variant.")
print(residencyHeader)

let sliding = kernels[0]
let planesHalved = sliding.body.replacingOccurrences(
    of: "threadgroup U outputs[4 * BN * BDP];",
    with: "threadgroup U outputs[2 * BN * BDP];")
precondition(planesHalved != sliding.body, "epilogue plane declaration not found")

var realPipelines: [(String, MTLComputePipelineState)] = []
for (label, body) in [("real 4 planes", sliding.body), ("real 2 planes", planesHalved)] {
    let msl = preamble + sliding.header + "\n"
        + mlxSignature(sliding.name, extraBuffers: true) + realPrologue + body + "\n}\n"
    do {
        let lib = try device.makeLibrary(source: msl, options: nil)
        let fn = lib.makeFunction(name: "custom_kernel_\(sliding.name)")!
        let pipe = try device.makeComputePipelineState(function: fn)
        realPipelines.append(("\(label) \(pipe.staticThreadgroupMemoryLength)B", pipe))
        let r = maxResident(
            pipe, threads: 1024, kCap: searchCap(threads: 1024), bind: bindReal)
        print(residencyLine(
            "\(label) \(pipe.staticThreadgroupMemoryLength)B", k: r.k, capped: r.capped,
            threads: 1024, ms: r.maxMs))
        print("    maxTotalThreadsPerThreadgroup \(pipe.maxTotalThreadsPerThreadgroup)")
    } catch {
        print("  \(label): COMPILE FAILED: \(error)")
    }
}


// MARK: - Phase D: oversubscribed single-dispatch cross-check

print("\n=== Phase D: oversubscribed dispatch cross-check ===")
print("Independent of the Phase B/C binary search: one dispatch of K far above")
print("capacity, where the count of successful slots estimates co-residency.")
print(oversubHeader)
for threads in [1024, 512, 256, 128] {
    for bytes in [16, 18432, 32768] where bytes <= device.maxThreadgroupMemoryLength {
        let src = synthSource(bytes: bytes, threads: threads)
        guard let lib = try? device.makeLibrary(source: src, options: nil),
            let fn = lib.makeFunction(name: "rendez"),
            let pipe = try? device.makeComputePipelineState(function: fn)
        else { continue }
        let k = min(okSlots, 4 * 96 * 32 * max(cores, 1) / threads)
        print(padLabel("\(threads)t static \(pipe.staticThreadgroupMemoryLength)B")
            + oversubscribed(pipe, threads: threads, k: k) { enc in
                enc.setBuffer(counterBuf, offset: 0, index: 0)
                enc.setBuffer(okBuf, offset: 0, index: 1)
                enc.setBuffer(cfgBuf, offset: 0, index: 2)
            })
    }
}
// The real body indexes dummy buffers sized for at most 256 threadgroups.
for (label, pipe) in realPipelines {
    print(padLabel(label)
        + oversubscribed(pipe, threads: 1024, k: 240, bind: bindReal))
}

// MARK: - Phase E: per-dispatch cost of the real body vs threadgroup count

func bindRealPlain(_ enc: MTLComputeCommandEncoder) {
    for (i, b) in [dRawQ, dRawK, dRawV, dQW, dKW, dAngles, dKCache, dVCache,
        dParams, dScale, dAttended].enumerated()
    {
        enc.setBuffer(b, offset: 0, index: i)
    }
}

/// A compute encoder's default `MTLDispatchType.serial` means the `reps`
/// dispatches in one command buffer do not overlap, so GPU busy time over reps
/// is the per-call cost the per-dispatch profile prices. Reported as the best of
/// three command buffers to suppress scheduling noise.
func perCallMicros(
    _ pipe: MTLComputePipelineState, k: Int, threads: Int, reps: Int,
    bind: (MTLComputeCommandEncoder) -> Void
) -> Double {
    var best = Double.greatestFiniteMagnitude
    for _ in 0..<3 {
        let cb = queue.makeCommandBuffer()!
        let enc = cb.makeComputeCommandEncoder()!
        enc.setComputePipelineState(pipe)
        bind(enc)
        for _ in 0..<reps {
            enc.dispatchThreadgroups(
                MTLSize(width: k, height: 1, depth: 1),
                threadsPerThreadgroup: MTLSize(width: threads, height: 1, depth: 1))
        }
        enc.endEncoding()
        cb.commit()
        cb.waitUntilCompleted()
        best = min(best, (cb.gpuEndTime - cb.gpuStartTime) * 1e6 / Double(reps))
    }
    return best
}

print("\n=== Phase E: real-body cost vs threadgroup count (dummy buffers) ===")
print("Each threadgroup reads 512x128 K and V rows = 262144 B, and 4 consecutive")
print("threadgroups share one KV head, so `req` counts issued bytes and `uniq`")
print("counts distinct bytes. Shipped sliding dispatch is K=32; R1 would be K=64.")
print("     K   TGs/core     us/call   us/TG    req GB/s   uniq GB/s   vs K=32")
do {
    let msl = preamble + sliding.header + "\n"
        + mlxSignature(sliding.name, extraBuffers: false) + sliding.body + "\n}\n"
    let lib = try device.makeLibrary(source: msl, options: nil)
    let fn = lib.makeFunction(name: "custom_kernel_\(sliding.name)")!
    let pipe = try device.makeComputePipelineState(function: fn)
    precondition(pipe.staticThreadgroupMemoryLength == 18432)
    _ = perCallMicros(pipe, k: 32, threads: 1024, reps: 20, bind: bindRealPlain)
    var base = 0.0
    for k in [1, 2, 4, 8, 16, 20, 24, 32, 40, 48, 56, 60, 64, 72, 96, 120, 128, 240] {
        let us = perCallMicros(pipe, k: k, threads: 1024, reps: 200, bind: bindRealPlain)
        if k == 32 { base = us }
        let bytes = Double(k) * 262_144.0
        let uniq = Double((k + 3) / 4) * 262_144.0
        print(String(
            format: "  %4d   %8.2f   %9.2f   %5.2f   %9.1f   %9.1f   %6.3f",
            k, Double(k) / Double(max(cores, 1)), us, us / Double(k),
            bytes / us * 1e-3, uniq / us * 1e-3, base > 0 ? us / base : 0))
    }
} catch {
    print("  plain real pipeline: COMPILE FAILED: \(error)")
}

