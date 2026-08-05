// Gather-GEMM threadgroup co-residency / occupancy probe.
//
// PR #57 (maple-2026-08-05f-gathergemm-coresidency), task T1.
// Research-only: this file is NOT on benchmark.json's editablePaths and is
// never compiled by a scored build.
//
// Build & run:
//   xcrun swiftc -O research/tanjiro_gathergemm_occupancy_probe.swift \
//       -o /tmp/tjocc && /tmp/tjocc
//
// Env knobs (all optional):
//   MLXFAST_GPU_CORES=<n>     override detected GPU core count
//   TJ_SKIP_PHASE_A=1         skip the real-kernel metallib pipeline probe
//   TJ_SKIP_PHASE_D=1         skip the spin-rendezvous residency check
//   TJ_TARGET_US=<float>      lone-threadgroup calibration target (default 10)
//
// Design notes (why the probe looks like this)
// --------------------------------------------
// * Phase A never hand-copies kernel source. It shells out to
//   research/nax_msl_compile_check.sh, which extracts the JIT preamble bodies
//   straight out of Vendor/mlx-swift/Source/Cmlx/mlx-generated/*.cpp and emits
//   the shipped template instantiation. That is the no-drift analogue of
//   nezuko's label-slicing trick in research/nezuko_occupancy_probe.swift.
// * The synthetic kernel in Phases B/C/D is *footprint matched* to the shipped
//   expert kernel as censused in research/tanjiro-gathergemm-d2-census.md:
//   9,216 B of 16-B-aligned staging chunks + an 8-B bounds pair = 9,224 B of
//   static threadgroup memory, and 128 threads (4 simdgroups) per threadgroup.
// * Device reads come from a 256 KiB buffer so they stay cache resident. That
//   is deliberate: nezuko's PR #56 §4.3 showed the real sliding-window kernel
//   issues ~443 GB/s at K=32, i.e. 170% of the 260.2 GB/s M4 DRAM ceiling, so
//   the regime under test is cache-served and latency bound, not DRAM bound.
//   A DRAM-bound synthetic would measure a different machine.
// * Phase C holds PER-THREAD work exactly constant while threads/threadgroup
//   varies over {128, 256, 512, 1024}. That is the unconfounded discriminator:
//   "1 threadgroup per core" means 4 warps/core at 128 threads but 32
//   warps/core at 1024 threads, so a large 128-thread gain is expected from
//   warp under-occupancy alone and does not by itself show that the
//   *threadgroup* is the scheduling unit.

import Foundation
import Metal

// MARK: - small helpers

let stderrHandle = FileHandle.standardError

func log(_ s: String) {
    print(s)
    fflush(stdout)
}

func die(_ s: String) -> Never {
    stderrHandle.write(("FATAL: " + s + "\n").data(using: .utf8)!)
    exit(1)
}

func env(_ k: String) -> String? {
    guard let v = ProcessInfo.processInfo.environment[k], !v.isEmpty else { return nil }
    return v
}

func run(_ launchPath: String, _ args: [String], cwd: String? = nil) -> (Int32, String) {
    let p = Process()
    p.executableURL = URL(fileURLWithPath: launchPath)
    p.arguments = args
    if let cwd { p.currentDirectoryURL = URL(fileURLWithPath: cwd) }
    let pipe = Pipe()
    p.standardOutput = pipe
    p.standardError = pipe
    do { try p.run() } catch { return (-1, "spawn failed: \(error)") }
    let data = pipe.fileHandleForReading.readDataToEndOfFile()
    p.waitUntilExit()
    return (p.terminationStatus, String(data: data, encoding: .utf8) ?? "")
}

func fmt(_ v: Double, _ digits: Int = 3) -> String {
    String(format: "%.\(digits)f", v)
}

func pad(_ s: String, _ width: Int) -> String {
    s.count >= width ? s : String(repeating: " ", count: width - s.count) + s
}

// MARK: - host facts

func detectCores() -> (Int, String) {
    if let s = env("MLXFAST_GPU_CORES"), let n = Int(s) { return (n, "MLXFAST_GPU_CORES override") }
    let (st, out) = run("/usr/sbin/system_profiler", ["SPDisplaysDataType"])
    if st == 0 {
        for line in out.split(separator: "\n") {
            if line.contains("Total Number of Cores") {
                let digits = line.filter { $0.isNumber }
                if let n = Int(digits) { return (n, "system_profiler SPDisplaysDataType") }
            }
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

func sysctlUInt64(_ name: String) -> UInt64 {
    var v: UInt64 = 0
    var size = MemoryLayout<UInt64>.size
    sysctlbyname(name, &v, &size, nil, 0)
    return v
}

// MARK: - repo location

let repoRoot: String = {
    // The probe lives at <repo>/research/, but may be compiled anywhere.
    // Walk up from the source file location recorded at compile time.
    let here = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    return here.deletingLastPathComponent().path
}()

// MARK: - Metal setup

guard let device = MTLCreateSystemDefaultDevice() else { die("no Metal device") }
guard let queue = device.makeCommandQueue() else { die("no command queue") }

let (cores, coresSource) = detectCores()

log("""
=== tanjiro gather-GEMM occupancy probe (PR #57 T1) ===
device                        : \(device.name)
gpu cores                     : \(cores == 0 ? "UNDETECTED" : String(cores))  [\(coresSource)]
machine                       : \(sysctlString("hw.model")) / \(sysctlString("kern.osproductversion"))
hw.memsize                    : \(sysctlUInt64("hw.memsize")) B
maxThreadgroupMemoryLength    : \(device.maxThreadgroupMemoryLength) B
maxThreadsPerThreadgroup      : \(device.maxThreadsPerThreadgroup.width)x\(device.maxThreadsPerThreadgroup.height)x\(device.maxThreadsPerThreadgroup.depth)
hasUnifiedMemory              : \(device.hasUnifiedMemory)
recommendedMaxWorkingSetSize  : \(device.recommendedMaxWorkingSetSize) B
""")
if cores == 0 { die("GPU core count undetected; set MLXFAST_GPU_CORES") }

// =====================================================================
// Phase A: real shipped _nax expert kernel -> MTLComputePipelineState
// =====================================================================
//
// Purpose: read staticThreadgroupMemoryLength off the *actual* compiled
// pipeline instead of trusting a source census. Predicted 9,224 B.

struct PhaseAResult {
    var attempted = false
    var libraryLoaded = false
    var rows: [(String, String)] = []
    var notes: [String] = []
    var tgMem: Int? = nil
}

var phaseA = PhaseAResult()

func phaseARun() -> PhaseAResult {
    var r = PhaseAResult()
    r.attempted = true
    let script = repoRoot + "/research/nax_msl_compile_check.sh"
    guard FileManager.default.fileExists(atPath: script) else {
        r.notes.append("nax_msl_compile_check.sh not found at \(script)")
        return r
    }
    let out = "/tmp/tj_nax_pipeline"
    var e = ProcessInfo.processInfo.environment
    e["OUT_DIR"] = out
    let p = Process()
    p.executableURL = URL(fileURLWithPath: "/bin/bash")
    p.arguments = [script]
    p.environment = e
    p.currentDirectoryURL = URL(fileURLWithPath: repoRoot)
    let pipe = Pipe()
    p.standardOutput = pipe
    p.standardError = pipe
    do { try p.run() } catch {
        r.notes.append("compile-check spawn failed: \(error)")
        return r
    }
    let data = pipe.fileHandleForReading.readDataToEndOfFile()
    p.waitUntilExit()
    let text = String(data: data, encoding: .utf8) ?? ""
    guard p.terminationStatus == 0 else {
        r.notes.append("compile-check FAILED (status \(p.terminationStatus)):\n" + text)
        return r
    }
    r.notes.append("compile-check: " + text.split(separator: "\n").joined(separator: " | "))

    let (mst, mout) = run("/usr/bin/xcrun",
                          ["-sdk", "macosx", "metallib", out + "/unit.air", "-o", out + "/unit.metallib"])
    guard mst == 0 else {
        r.notes.append("metallib link FAILED: " + mout)
        return r
    }
    let url = URL(fileURLWithPath: out + "/unit.metallib")
    let lib: MTLLibrary
    do { lib = try device.makeLibrary(URL: url) } catch {
        r.notes.append("makeLibrary(URL:) FAILED: \(error)")
        return r
    }
    r.libraryLoaded = true
    r.notes.append("makeLibrary OK; functionNames=\(lib.functionNames.sorted())")

    for name in lib.functionNames.sorted() {
        guard let fn = lib.makeFunction(name: name) else {
            r.rows.append((name, "makeFunction returned nil"))
            continue
        }
        do {
            let pso = try device.makeComputePipelineState(function: fn)
            r.tgMem = pso.staticThreadgroupMemoryLength
            r.rows.append((name,
                           "staticThreadgroupMemoryLength=\(pso.staticThreadgroupMemoryLength) B"
                           + "  maxTotalThreadsPerThreadgroup=\(pso.maxTotalThreadsPerThreadgroup)"
                           + "  threadExecutionWidth=\(pso.threadExecutionWidth)"))
        } catch {
            r.rows.append((name, "makeComputePipelineState FAILED: \(error)"))
        }
    }
    return r
}

if env("TJ_SKIP_PHASE_A") == nil {
    log("\n--- Phase A: shipped _nax expert kernel pipeline properties ---")
    phaseA = phaseARun()
    for n in phaseA.notes { log("  note: " + n) }
    for (k, v) in phaseA.rows { log("  \(k)\n      \(v)") }
    if phaseA.rows.isEmpty { log("  (no pipelines created)") }
} else {
    log("\n--- Phase A: SKIPPED (TJ_SKIP_PHASE_A) ---")
}

// =====================================================================
// Synthetic footprint-matched kernel
// =====================================================================
//
// Static threadgroup memory:
//   ws[576] of 16 B  = 9,216 B   (mirrors NAXWsChunk16<bfloat> Ws_storage[576])
//   bounds[2] of 4 B =     8 B   (mirrors the hoisted bsearch bounds pair)
//   ------------------------------
//   total            = 9,224 B, which the driver pads to 9,232 B — exactly what
//   Phase A reads off the real shipped pipeline. The cross-simdgroup reduction
//   epilogue reuses ws rather than allocating its own staging array, so the
//   footprint stays matched.
//
// Per-iteration structure mirrors the shipped k-loop dependency chain:
//   device float4 load (every DEV_EVERY-th iteration)
//     -> threadgroup staged store
//     -> barrier
//     -> 4 threadgroup loads feeding a serial 2-deep FMA chain
//     -> barrier
// Work per THREAD is independent of threads/threadgroup, which is what makes
// the Phase C geometry sweep interpretable.

let msl = """
#include <metal_stdlib>
using namespace metal;

struct alignas(16) Chunk16 { float4 v; };

constant constexpr uint kWsChunks = 576u;      // 9,216 B
constant constexpr uint kDevEvery = 4u;        // device load cadence

// scope: 0 = threadgroup_barrier, 1 = simdgroup_barrier
template <uint SCOPE>
inline void probe_barrier() {
    if (SCOPE == 0u) {
        threadgroup_barrier(mem_flags::mem_threadgroup);
    } else {
        simdgroup_barrier(mem_flags::mem_threadgroup);
    }
}

template <uint SCOPE>
inline void probe_body(
    device const float4* src,
    device float* out,
    uint reps,
    uint srcMask,
    uint tid,
    uint ntg,
    uint gid,
    uint lane,
    uint sgid,
    threadgroup Chunk16* ws,
    threadgroup int* bounds)
{
    // Prologue: zero the staging array so every later read is well defined
    // even in the SCOPE==1 variant, where cross-simdgroup ordering is relaxed.
    for (uint i = tid; i < kWsChunks; i += ntg) {
        ws[i].v = float4(0.5f);
    }
    if (tid == 0) { bounds[0] = 0; bounds[1] = 1; }
    threadgroup_barrier(mem_flags::mem_threadgroup);

    float4 acc = float4(0.5f);
    uint cur = (gid * 1013u + tid * 4u) & srcMask;
    float4 v = float4(0.5f);

    for (uint r = 0; r < reps; ++r) {
        if ((r & (kDevEvery - 1u)) == 0u) {
            v = src[cur];
            cur = (cur + 64u) & srcMask;
        }
        uint slot = (tid + r * 37u) % kWsChunks;
        ws[slot].v = v + acc * 1e-6f;   // staged store depends on the chain
        probe_barrier<SCOPE>();

        uint base = (r * 13u) % kWsChunks;
        float4 a0 = ws[base].v;
        float4 a1 = ws[(base + 64u) % kWsChunks].v;
        float4 a2 = ws[(base + 128u) % kWsChunks].v;
        float4 a3 = ws[(base + 192u) % kWsChunks].v;
        acc = fma(a0, acc, a1);
        acc = fma(a2, acc, a3);
        probe_barrier<SCOPE>();
    }

    // Reduce to one float per threadgroup: keeps the loop alive for the
    // optimiser without adding a per-thread device write stream. The staging
    // slots are carved out of ws so the static footprint stays at 9,224 B.
    float s = acc.x + acc.y + acc.z + acc.w + float(bounds[1]);
    s = simd_sum(s);
    threadgroup_barrier(mem_flags::mem_threadgroup);   // ws reuse hazard
    if (lane == 0) { ws[sgid].v.x = s; }
    threadgroup_barrier(mem_flags::mem_threadgroup);
    if (tid == 0) {
        float t = 0.0f;
        uint nsg = (ntg + 31u) / 32u;
        for (uint i = 0; i < nsg; ++i) { t += ws[i].v.x; }
        out[gid] = t;
    }
}

#define PROBE_KERNEL(NAME, SCOPE)                                            \\
kernel void NAME(                                                            \\
    device const float4* src      [[buffer(0)]],                             \\
    device float* out             [[buffer(1)]],                             \\
    constant uint& reps           [[buffer(2)]],                             \\
    constant uint& srcMask        [[buffer(3)]],                             \\
    uint tid  [[thread_position_in_threadgroup]],                            \\
    uint ntg  [[threads_per_threadgroup]],                                   \\
    uint gid  [[threadgroup_position_in_grid]],                              \\
    uint lane [[thread_index_in_simdgroup]],                                 \\
    uint sgid [[simdgroup_index_in_threadgroup]])                            \\
{                                                                            \\
    threadgroup Chunk16 ws[kWsChunks];                                       \\
    threadgroup int bounds[2];                                               \\
    probe_body<SCOPE>(src, out, reps, srcMask, tid, ntg, gid, lane, sgid,    \\
                      ws, bounds);                                          \\
}

PROBE_KERNEL(probe_tgbar, 0u)
PROBE_KERNEL(probe_sgbar, 1u)

// Spin rendezvous: measures how many threadgroups of a given geometry and
// threadgroup-memory footprint are simultaneously resident. Same static
// threadgroup allocation as the probe kernels so the residency limit under
// test is the one that matters.
// The threadgroup arrays must be fed from device memory and drained back to
// device memory, otherwise the compiler removes them and the pipeline reports a
// 0 B static footprint - which would measure residency at the wrong footprint.
kernel void rendezvous(
    device atomic_uint* ctr    [[buffer(0)]],
    device atomic_uint* fails  [[buffer(1)]],
    constant uint& target      [[buffer(2)]],
    constant uint& spinLimit   [[buffer(3)]],
    device const float4* src   [[buffer(4)]],
    device float* out          [[buffer(5)]],
    uint tid [[thread_position_in_threadgroup]],
    uint ntg [[threads_per_threadgroup]],
    uint gid [[threadgroup_position_in_grid]])
{
    threadgroup Chunk16 ws[kWsChunks];
    threadgroup int bounds[2];
    for (uint i = tid; i < kWsChunks; i += ntg) { ws[i].v = src[i]; }
    if (tid == 0) { bounds[0] = 0; bounds[1] = int(ntg); }
    threadgroup_barrier(mem_flags::mem_threadgroup);
    if (tid != 0) { return; }
    atomic_fetch_add_explicit(ctr, 1u, memory_order_relaxed);
    bool ok = false;
    for (uint s = 0; s < spinLimit; ++s) {
        if (atomic_load_explicit(ctr, memory_order_relaxed) >= target) { ok = true; break; }
    }
    if (!ok) { atomic_fetch_add_explicit(fails, 1u, memory_order_relaxed); }
    float t = float(bounds[1]);
    for (uint i = 0; i < kWsChunks; i += 37u) { t += ws[i].v.x; }
    out[gid] = t;
}
"""

let opts = MTLCompileOptions()
if #available(macOS 15.0, *) { opts.mathMode = .safe } else { opts.fastMathEnabled = false }

let synthLib: MTLLibrary
do { synthLib = try device.makeLibrary(source: msl, options: opts) } catch {
    die("synthetic kernel compile failed: \(error)")
}

func pso(_ name: String) -> MTLComputePipelineState {
    guard let fn = synthLib.makeFunction(name: name) else { die("missing function \(name)") }
    do { return try device.makeComputePipelineState(function: fn) } catch {
        die("pipeline \(name) failed: \(error)")
    }
}

let psoTG = pso("probe_tgbar")
let psoSG = pso("probe_sgbar")
let psoRV = pso("rendezvous")

log("""

--- synthetic footprint-matched kernel ---
probe_tgbar  staticThreadgroupMemoryLength=\(psoTG.staticThreadgroupMemoryLength) B \
maxTotalThreadsPerThreadgroup=\(psoTG.maxTotalThreadsPerThreadgroup) \
threadExecutionWidth=\(psoTG.threadExecutionWidth)
probe_sgbar  staticThreadgroupMemoryLength=\(psoSG.staticThreadgroupMemoryLength) B \
maxTotalThreadsPerThreadgroup=\(psoSG.maxTotalThreadsPerThreadgroup)
rendezvous   staticThreadgroupMemoryLength=\(psoRV.staticThreadgroupMemoryLength) B \
maxTotalThreadsPerThreadgroup=\(psoRV.maxTotalThreadsPerThreadgroup)
census prediction (research/tanjiro-gathergemm-d2-census.md): 9224 B, padded 9232 B
""")

// 9232 = 9224 census total padded to the driver's 16 B granularity; used when
// Phase A is skipped so the check still has a reference.
let realTGMem = phaseA.tgMem ?? 9232

for (name, p) in [("probe_tgbar", psoTG), ("probe_sgbar", psoSG), ("rendezvous", psoRV)] {
    let got = p.staticThreadgroupMemoryLength
    if got != realTGMem {
        log("  FOOTPRINT MISMATCH: \(name)=\(got) B vs real shipped pipeline \(realTGMem) B"
            + " - geometry sweeps are NOT footprint-matched")
    }
}

// MARK: - buffers

let srcChunks = 16384                       // 256 KiB of float4 -> cache resident
let srcMask = UInt32(srcChunks - 1)
guard let srcBuf = device.makeBuffer(length: srcChunks * 16, options: .storageModeShared) else {
    die("src buffer alloc failed")
}
do {
    let p = srcBuf.contents().bindMemory(to: Float.self, capacity: srcChunks * 4)
    for i in 0..<(srcChunks * 4) { p[i] = 0.5 + Float(i % 7) * 1e-3 }
}
let maxTGs = 4096
guard let outBuf = device.makeBuffer(length: maxTGs * 4, options: .storageModeShared) else {
    die("out buffer alloc failed")
}

// MARK: - timing core

let dispatchesPerCB = 200

/// Returns GPU-busy seconds per dispatch, best of `bestOf` command buffers.
func timeDispatch(_ pipeline: MTLComputePipelineState,
                  threadgroups: Int,
                  threadsPerTG: Int,
                  reps: UInt32,
                  dispatches: Int = dispatchesPerCB,
                  bestOf: Int = 3) -> Double {
    var repsV = reps
    var maskV = srcMask
    var best = Double.greatestFiniteMagnitude
    for _ in 0..<bestOf {
        guard let cb = queue.makeCommandBuffer(), let enc = cb.makeComputeCommandEncoder() else {
            die("encoder failed")
        }
        enc.setComputePipelineState(pipeline)
        enc.setBuffer(srcBuf, offset: 0, index: 0)
        enc.setBuffer(outBuf, offset: 0, index: 1)
        enc.setBytes(&repsV, length: 4, index: 2)
        enc.setBytes(&maskV, length: 4, index: 3)
        for _ in 0..<dispatches {
            enc.dispatchThreadgroups(MTLSize(width: threadgroups, height: 1, depth: 1),
                                     threadsPerThreadgroup: MTLSize(width: threadsPerTG, height: 1, depth: 1))
        }
        enc.endEncoding()
        cb.commit()
        cb.waitUntilCompleted()
        if cb.status != .completed { die("command buffer status \(cb.status.rawValue): \(String(describing: cb.error))") }
        let t = (cb.gpuEndTime - cb.gpuStartTime) / Double(dispatches)
        best = min(best, t)
    }
    return best
}

// MARK: - calibration

let targetUS = Double(env("TJ_TARGET_US") ?? "") ?? 10.0
var reps: UInt32 = 64
do {
    // Warm up compilation / clocks, then scale reps so a lone 128-thread
    // threadgroup lands near targetUS.
    _ = timeDispatch(psoTG, threadgroups: 1, threadsPerTG: 128, reps: 64, dispatches: 50, bestOf: 2)
    let t = timeDispatch(psoTG, threadgroups: 1, threadsPerTG: 128, reps: 64) * 1e6
    let scaled = 64.0 * targetUS / max(t, 1e-6)
    reps = UInt32(max(16.0, min(4096.0, scaled.rounded())))
    log("\n--- calibration ---")
    log("  t(K=1, 128t, reps=64)   = \(fmt(t, 3)) us")
    log("  chosen reps             = \(reps)  (target \(fmt(targetUS, 1)) us)")
}

// MARK: - DCE guard

do {
    log("\n--- DCE guard (loop must be real work) ---")
    let t1 = timeDispatch(psoTG, threadgroups: 20, threadsPerTG: 128, reps: reps) * 1e6
    let t2 = timeDispatch(psoTG, threadgroups: 20, threadsPerTG: 128, reps: reps * 2) * 1e6
    let t4 = timeDispatch(psoTG, threadgroups: 20, threadsPerTG: 128, reps: reps * 4) * 1e6
    log("  reps=\(reps)    t=\(fmt(t1)) us")
    log("  reps=\(reps * 2)   t=\(fmt(t2)) us   ratio vs 1x = \(fmt(t2 / t1))  (want ~2.0)")
    log("  reps=\(reps * 4)   t=\(fmt(t4)) us   ratio vs 1x = \(fmt(t4 / t1))  (want ~4.0)")
    let ok = abs(t2 / t1 - 2.0) < 0.35 && abs(t4 / t1 - 4.0) < 0.7
    log("  verdict: \(ok ? "PASS - loop work scales linearly" : "SUSPECT - inspect before trusting timings")")
}

// MARK: - Phase B: 128-thread threadgroup-count sweep (primary metric)

struct Row {
    let k: Int
    let us: Double
    var usPerTG: Double { us / Double(k) }
    var tgPerSec: Double { Double(k) / (us * 1e-6) }
}

func sweep(_ pipeline: MTLComputePipelineState,
           threadsPerTG: Int,
           ks: [Int],
           label: String) -> [Row] {
    log("\n  \(label)  (threads/TG=\(threadsPerTG), reps=\(reps), tgmem=\(pipeline.staticThreadgroupMemoryLength) B)")
    log("    K      TG/core   warps/core   t(K) us     us/TG      TG/s (M)   norm-thru")
    var rows: [Row] = []
    var base: Double? = nil
    for k in ks {
        if k > maxTGs { continue }
        let us = timeDispatch(pipeline, threadgroups: k, threadsPerTG: threadsPerTG, reps: reps) * 1e6
        let r = Row(k: k, us: us)
        rows.append(r)
        let tgPerCore = Double(k) / Double(cores)
        let warpsPerCore = tgPerCore * Double(threadsPerTG) / 32.0
        if base == nil { base = r.tgPerSec }
        log("    \(String(format: "%-6d", k)) \(String(format: "%8.2f", tgPerCore)) \(String(format: "%12.2f", warpsPerCore)) \(String(format: "%10.3f", us)) \(String(format: "%10.4f", r.usPerTG)) \(String(format: "%11.3f", r.tgPerSec / 1e6)) \(String(format: "%10.3f", r.tgPerSec / base!))")
    }
    return rows
}

/// Least-squares fit of t(K) = a*ceil(K/W) + b over candidate wave widths W.
func fitStaircase(_ rows: [Row], candidates: [Int]) -> (w: Int, a: Double, b: Double, rmsRel: Double) {
    var best: (Int, Double, Double, Double) = (0, 0, 0, .greatestFiniteMagnitude)
    for w in candidates {
        let xs = rows.map { Double(($0.k + w - 1) / w) }
        let ys = rows.map { $0.us }
        let n = Double(xs.count)
        let sx = xs.reduce(0, +), sy = ys.reduce(0, +)
        let sxx = zip(xs, xs).map(*).reduce(0, +)
        let sxy = zip(xs, ys).map(*).reduce(0, +)
        let den = n * sxx - sx * sx
        guard abs(den) > 1e-12 else { continue }
        let a = (n * sxy - sx * sy) / den
        let b = (sy - a * sx) / n
        var acc = 0.0
        for (x, y) in zip(xs, ys) {
            let pred = a * x + b
            acc += ((pred - y) / y) * ((pred - y) / y)
        }
        let rms = (acc / n).squareRoot()
        if rms < best.3 { best = (w, a, b, rms) }
    }
    return best
}

log("\n--- Phase B: threadgroup-count sweep at the shipped geometry ---")
log("  shipped expert dispatch: 128 threads/TG (32,1,4), 4096 TGs (gate/up) / 8192 TGs (down)")

// Residency predicted by nezuko PR #56: 3072 threads/core -> 24 TGs/core at 128t.
let ksBase128 = [1, 4, 10, 20, 24, 40, 48, 80, 120, 160, 161, 168, 240, 320, 480, 481, 520, 640, 960, 1920]
let rows128 = sweep(psoTG, threadsPerTG: 128, ks: ksBase128, label: "Phase B / 128t / threadgroup_barrier")

func metric(_ rows: [Row], threadsPerTG: Int, hiTGPerCore: Int) -> (percore: Double, lone: Double, khi: Int)? {
    let khi = hiTGPerCore * cores
    guard let hi = rows.first(where: { $0.k == khi }),
          let one = rows.first(where: { $0.k == cores }),
          let lone = rows.first(where: { $0.k == 1 }) else { return nil }
    return (hi.tgPerSec / one.tgPerSec, hi.tgPerSec / lone.tgPerSec, khi)
}

if let m = metric(rows128, threadsPerTG: 128, hiTGPerCore: 24) {
    log("""

  PRIMARY METRIC (coresidency_throughput_gain_128t_1_to_24x), K_hi=\(m.khi)
    per-core form  (K_hi/t(K_hi)) / (cores/t(cores))  = \(fmt(m.percore, 4))
    lone-TG form   (K_hi/t(K_hi)) / (1/t(1))          = \(fmt(m.lone, 4))
""")
}

let fit128 = fitStaircase(rows128, candidates: Array(1...64).map { $0 * cores } + [cores * 96, cores * 128])
if let t1 = rows128.first(where: { $0.k == 1 })?.us {
    log("""
  staircase fit t(K) ~ a*ceil(K/W) + b over the 128t sweep
    W (wave width, TGs)  = \(fit128.w)   -> \(fmt(Double(fit128.w) / Double(cores), 2)) TG/core
    a (us per wave)      = \(fmt(fit128.a, 4))
    b (us fixed)         = \(fmt(fit128.b, 4))
    rms relative resid   = \(fmt(fit128.rmsRel * 100, 2))%
    a / t(1)             = \(fmt(fit128.a / t1, 4))   (nezuko 1024t reference: 0.884)
""")
}

// MARK: - Phase C: geometry sweep at matched warps-in-flight per core
//
// Every geometry is sampled at the SAME warps-in-flight-per-core levels, so a
// row-by-row comparison is apples to apples. K = w * 32 * cores / g, chosen so
// K is always a multiple of `cores` (no ragged partial wave). Both barrier
// scopes are swept: threadgroup_barrier cost grows with simdgroups per
// threadgroup, which on its own can make the threadgroup look like the
// scheduling unit.

let geometries = [128, 256, 512, 1024]
let warpLevels = [32, 64, 96, 192, 384]

func ksFor(_ g: Int) -> [Int] {
    var out: [Int] = [1, cores]
    for w in warpLevels {
        let k = w * 32 * cores / g
        if k >= 1 { out.append(k) }
    }
    var uniq: [Int] = []
    for k in out.sorted() where !uniq.contains(k) { uniq.append(k) }
    return uniq
}

/// Thread-iterations per microsecond: the only work unit comparable across
/// geometries, since per-thread work is held constant at `reps`.
func rate(_ r: Row, _ g: Int) -> Double { Double(r.k) * Double(g) * Double(reps) / r.us }

/// Marginal cost of one more threadgroup over the top two sampled K values.
/// Converted to thread-iterations/us it is the saturated throughput.
func asymptote(_ rows: [Row], _ g: Int) -> (usPerTG: Double, rate: Double)? {
    let s = rows.sorted { $0.k < $1.k }
    guard s.count >= 2 else { return nil }
    let a = s[s.count - 2], b = s[s.count - 1]
    guard b.k > a.k else { return nil }
    let slope = (b.us - a.us) / Double(b.k - a.k)
    guard slope > 0 else { return nil }
    return (slope, Double(g) * Double(reps) / slope)
}

struct GeomSweep {
    let scope: String
    let g: Int
    let rows: [Row]
}
var sweeps: [GeomSweep] = []

for (scope, pso) in [("threadgroup_barrier", psoTG), ("simdgroup_barrier", psoSG)] {
    log("""

--- Phase C (\(scope)): matched warps/core across threads/TG ---
  warps/core levels: \(warpLevels.map(String.init).joined(separator: ", "))
""")
    for g in geometries {
        guard pso.maxTotalThreadsPerThreadgroup >= g else {
            log("  threads/TG=\(g) exceeds maxTotalThreadsPerThreadgroup=\(pso.maxTotalThreadsPerThreadgroup); skipped")
            continue
        }
        let rows = sweep(pso, threadsPerTG: g, ks: ksFor(g), label: "\(scope) / \(g)t")
        sweeps.append(GeomSweep(scope: scope, g: g, rows: rows))
    }
}

// MARK: - collapse test
//
// Ruling input for prereg Table B. At each matched warps/core level, compare
// thread-iteration rate across geometries. Spread near 0 => warps in flight per
// core is the whole story (SIMD group is the scheduling unit). Large spread
// with small threadgroups faster => threadgroup count matters independently.

func collapseReport(_ scope: String) -> Double {
    let mine = sweeps.filter { $0.scope == scope }
    guard let ref = mine.first(where: { $0.g == geometries[0] }) else { return .nan }
    log("""

  collapse table (\(scope)): thread-iterations/us at matched warps/core,
  normalised to the \(geometries[0])t row of the same level.
    warps/core \(geometries.map { pad("\($0)t", 12) }.joined())   spread
""")
    var worst = 0.0
    for w in warpLevels {
        var cells: [Double] = []
        var line = String(format: "    %10d", w)
        for g in geometries {
            guard let s = mine.first(where: { $0.g == g }),
                  let row = s.rows.first(where: { $0.k == w * 32 * cores / g }),
                  let refRow = ref.rows.first(where: { $0.k == w * 32 * cores / ref.g }) else {
                line += pad("-", 12)
                continue
            }
            let n = rate(row, g) / rate(refRow, ref.g)
            cells.append(n)
            line += String(format: "%12.3f", n)
        }
        if let lo = cells.min(), let hi = cells.max() {
            line += String(format: "%9.3f", hi - lo)
            worst = max(worst, hi - lo)
        }
        log(line)
    }

    log("""

  saturated throughput (\(scope)): marginal us per extra threadgroup at the top
  of each sweep, converted to thread-iterations/us.
    thr/TG   us/TG (marginal)   Gthread-iter/s   rel. to \(geometries[0])t
""")
    let refAsym = mine.first(where: { $0.g == geometries[0] }).flatMap { asymptote($0.rows, $0.g) }
    for g in geometries {
        guard let s = mine.first(where: { $0.g == g }), let a = asymptote(s.rows, g) else { continue }
        let rel = refAsym.map { a.rate / $0.rate } ?? Double.nan
        log("    \(String(format: "%6d", g)) \(String(format: "%18.4f", a.usPerTG)) \(String(format: "%16.3f", a.rate / 1e3)) \(String(format: "%17.3f", rel))")
    }

    log("""

  per-geometry staircase fit t(K) ~ a*ceil(K/W) + b   (\(scope))
    thr/TG    W (TGs)   W/core     a us      b us    rms resid   a/t(1)
""")
    for g in geometries {
        guard let s = mine.first(where: { $0.g == g }), s.rows.count >= 3 else { continue }
        let f = fitStaircase(s.rows, candidates: Array(1...64).map { $0 * cores } + [cores * 96, cores * 128])
        let t1 = s.rows.first(where: { $0.k == 1 })?.us ?? Double.nan
        log("    \(String(format: "%6d", g)) \(String(format: "%10d", f.w)) \(String(format: "%8.2f", Double(f.w) / Double(cores))) \(String(format: "%9.4f", f.a)) \(String(format: "%9.4f", f.b)) \(String(format: "%11.2f", f.rmsRel * 100))% \(String(format: "%8.4f", f.a / t1))")
    }
    return worst
}

let spreadTG = collapseReport("threadgroup_barrier")
let spreadSG = collapseReport("simdgroup_barrier")

log("""

  PREREG TABLE B INPUT
    max spread, threadgroup_barrier = \(fmt(spreadTG, 3))
    max spread, simdgroup_barrier   = \(fmt(spreadSG, 3))
    Table B thresholds: <=0.15 no independent effect; 0.15-0.40 partial;
    >=0.40 with small TGs faster => threadgroup is an independent unit.
    The simdgroup_barrier column is the confound-free reading.
""")

// MARK: - Phase D: residency rendezvous

if env("TJ_SKIP_PHASE_D") == nil {
    log("""

--- Phase D: spin-rendezvous residency at 9,224 B threadgroup memory ---
  A threadgroup that cannot see all `target` arrivals within spinLimit is not
  co-resident with the rest. fails==0 => all K threadgroups co-resident.
""")
    guard let ctrBuf = device.makeBuffer(length: 4, options: .storageModeShared),
          let failBuf = device.makeBuffer(length: 4, options: .storageModeShared) else {
        die("rendezvous buffer alloc failed")
    }
    func rendezvous(_ k: Int, threadsPerTG: Int, spinLimit: UInt32 = 2_000_000) -> (fails: UInt32, ms: Double) {
        ctrBuf.contents().bindMemory(to: UInt32.self, capacity: 1)[0] = 0
        failBuf.contents().bindMemory(to: UInt32.self, capacity: 1)[0] = 0
        var target = UInt32(k)
        var spin = spinLimit
        guard let cb = queue.makeCommandBuffer(), let enc = cb.makeComputeCommandEncoder() else {
            die("rendezvous encoder failed")
        }
        enc.setComputePipelineState(psoRV)
        enc.setBuffer(ctrBuf, offset: 0, index: 0)
        enc.setBuffer(failBuf, offset: 0, index: 1)
        enc.setBytes(&target, length: 4, index: 2)
        enc.setBytes(&spin, length: 4, index: 3)
        enc.setBuffer(srcBuf, offset: 0, index: 4)
        enc.setBuffer(outBuf, offset: 0, index: 5)
        enc.dispatchThreadgroups(MTLSize(width: k, height: 1, depth: 1),
                                 threadsPerThreadgroup: MTLSize(width: threadsPerTG, height: 1, depth: 1))
        enc.endEncoding()
        cb.commit()
        cb.waitUntilCompleted()
        let f = failBuf.contents().bindMemory(to: UInt32.self, capacity: 1)[0]
        return (f, (cb.gpuEndTime - cb.gpuStartTime) * 1e3)
    }
    log("    thr/TG      K   fails   wall ms   co-resident?")
    for (g, ks) in [(128, [cores * 12, cores * 24, cores * 24 + 1, cores * 26, cores * 32]),
                    (1024, [cores * 2, cores * 3, cores * 3 + 1, cores * 4])] {
        for k in ks where k <= maxTGs {
            let r = rendezvous(k, threadsPerTG: g)
            log("    \(String(format: "%6d", g)) \(String(format: "%6d", k)) \(String(format: "%7d", r.fails)) \(String(format: "%9.2f", r.ms))   \(r.fails == 0 ? "YES" : "no")")
        }
    }
} else {
    log("\n--- Phase D: SKIPPED (TJ_SKIP_PHASE_D) ---")
}

log("\n=== probe complete ===")
