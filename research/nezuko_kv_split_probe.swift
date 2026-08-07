// Research-only host probe (not part of the submission surface).
//
// PR #196 (maple-2026-08-07a-decode-attention-occupancy) Step 0 + Step 1.
//
// Step 0 asks for the residency question to be settled by a *duration-vs-N*
// staircase rather than by arithmetic, together with the three real
// `MTLComputePipelineState` properties for both fused decode attention
// kernels. `research/nezuko_occupancy_probe.swift` already establishes the
// co-residency fact by cooperative rendezvous (3 threadgroups of 1024 threads
// per core = 96 simdgroups per core) and a coarse K-staircase for the sliding
// kernel. This probe adds the three things that audit is missing and that
// Step 1 needs:
//
//   P1  a *fine* staircase, K = 1 ... 3*C at unit resolution, so the riser
//       positions are read off the data instead of assumed. If duration is
//       flat in K there is no tail to price and the pre-registered kill fires.
//   P2  the same staircase for the *full* attention kernel, whose K-sweep was
//       never run (nezuko_step0_occupancy_audit.md section 9 limitation). Its
//       `params` is a 3-element uint32 buffer and its N is a runtime value,
//       so it needs its own binding.
//   P3  the decisive Step 1 number. A KV split at factor S turns 32
//       threadgroups of 512 KV rows into 32*S threadgroups of 512/S rows. It
//       can only pay if the KV-independent fixed cost of a threadgroup is
//       small compared with the marginal cost of its KV rows. Sweeping the
//       sliding kernel's `constexpr int N` (a pure textual substitution in the
//       extracted body) and fitting t = b + (f + g*L) * ceil(K/C) separates
//       that fixed cost f from the per-iteration cost g.
//   P4  an assumption-free cross-check of P3: directly time the shipped
//       geometry (K=32, N=512) against every split geometry (K=32*S,
//       N=512/S). This is the makespan of the split *without* its merge, so
//       it is a strict upper bound on the achievable gain.
//
// Build and run:
//   xcrun swiftc -O research/nezuko_kv_split_probe.swift -o /tmp/nezkv \
//     && /tmp/nezkv [path-to-LagunaRuntimeModel.swift]

import Foundation
import Metal

// MARK: - extraction (shared shape with nezuko_occupancy_probe.swift)

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

    let indent = lines[close].prefix(while: { $0 == " " }).count
    let body = lines[(open + 1)..<close].map { line -> String in
        var l = line
        var stripped = 0
        while stripped < indent, l.first == " " {
            l.removeFirst()
            stripped += 1
        }
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

/// Replica of the signature MLX's JIT emits for both fused attention kernels
/// (`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/common/metal_kernel.cpp`
/// `write_signature`). Attribute order follows that file's fixed table.
func mlxSignature(_ name: String) -> String {
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
    s += "  uint simdgroup_index_in_threadgroup [[simdgroup_index_in_threadgroup]],\n"
    s += "  uint thread_index_in_simdgroup [[thread_index_in_simdgroup]],\n"
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
let queue = device.makeCommandQueue()!

let sourcePath =
    CommandLine.arguments.count > 1
    ? CommandLine.arguments[1] : "Sources/MLXFastModel/LagunaRuntimeModel.swift"
let scoredLines = try! String(contentsOfFile: sourcePath, encoding: .utf8)
    .split(separator: "\n", omittingEmptySubsequences: false).map(String.init)

let sliding = extractKernel(scoredLines, name: "laguna_sliding_fused_attn_ring_v1")
let full = extractKernel(scoredLines, name: "laguna_full_fused_attn_grow_v1")

/// Reports the GPU core count the same way Metal's own tools do, so the
/// staircase riser spacing can be compared against a device fact rather than
/// against a guess.
func gpuCoreCount() -> Int {
    let task = Process()
    task.launchPath = "/usr/sbin/ioreg"
    task.arguments = ["-l", "-w", "0", "-r", "-c", "AGXAccelerator"]
    let pipe = Pipe()
    task.standardOutput = pipe
    task.standardError = FileHandle.nullDevice
    try? task.run()
    let data = pipe.fileHandleForReading.readDataToEndOfFile()
    task.waitUntilExit()
    guard let text = String(data: data, encoding: .utf8) else { return 0 }
    for line in text.split(separator: "\n") where line.contains("gpu-core-count") {
        let digits = line.split(whereSeparator: { !$0.isNumber })
        if let last = digits.last, let v = Int(last) { return v }
    }
    return 0
}

let cores = gpuCoreCount()

print("=== device ===")
print("name                    \(device.name)")
print("architecture.name       \(device.architecture.name)")
print("gpu-core-count          \(cores)")
print("scored source           \(sourcePath) (\(scoredLines.count) lines)")

// MARK: - buffers

/// Dummy buffers wide enough for the largest dispatch any phase issues.
/// `head0 = 2*tg`, `kv_head = head0/gqa`, so 512 threadgroups need 1024 Q heads
/// and (with the full kernel's gqa=6) 171 KV heads. bfloat lanes are 1.0
/// (0x3F80) so the RMSNorm `rsqrt` never sees a zero sum.
func makeBF16(_ elements: Int) -> MTLBuffer {
    let buf = device.makeBuffer(length: elements * 2, options: .storageModeShared)!
    let p = buf.contents().bindMemory(to: UInt16.self, capacity: elements)
    for i in 0..<elements { p[i] = 0x3F80 }
    return buf
}

let cHeads = 1024
let cKV = 256
let cDim = 128
let cCap = 1024
let dRawQ = makeBF16(cHeads * cDim)
let dRawK = makeBF16(cKV * cDim)
let dRawV = makeBF16(cKV * cDim)
let dQW = makeBF16(cDim)
let dKW = makeBF16(cDim)
let dKCache = makeBF16(cKV * cCap * cDim)
let dVCache = makeBF16(cKV * cCap * cDim)
let dAttended = makeBF16(cHeads * cDim)
let dAngles = device.makeBuffer(length: cDim * 4, options: .storageModeShared)!
for i in 0..<cDim {
    dAngles.contents().bindMemory(to: Float.self, capacity: cDim)[i] = 0.5
}
let dScale = device.makeBuffer(length: 4, options: .storageModeShared)!
dScale.contents().bindMemory(to: Float.self, capacity: 1)[0] = 0.088_388_35

/// Sliding kernel: `params[0]` is the ring write index only.
let dParams1 = device.makeBuffer(length: 4, options: .storageModeShared)!
dParams1.contents().bindMemory(to: UInt32.self, capacity: 1)[0] = 0

/// Full kernel: `params = [write_idx, N, capacity]` (wrapper at
/// `lagunaFullFusedAttention`). N is the runtime KV length there.
func makeParams3(n: Int) -> MTLBuffer {
    let b = device.makeBuffer(length: 12, options: .storageModeShared)!
    let p = b.contents().bindMemory(to: UInt32.self, capacity: 3)
    p[0] = UInt32(n - 1)
    p[1] = UInt32(n)
    p[2] = UInt32(cCap)
    return b
}

func binder(_ params: MTLBuffer) -> (MTLComputeCommandEncoder) -> Void {
    return { enc in
        for (i, b) in [dRawQ, dRawK, dRawV, dQW, dKW, dAngles, dKCache, dVCache,
            params, dScale, dAttended].enumerated()
        {
            enc.setBuffer(b, offset: 0, index: i)
        }
    }
}

// MARK: - timing

func compile(_ k: ExtractedKernel, body: String) -> MTLComputePipelineState? {
    let msl = preamble + k.header + "\n" + mlxSignature(k.name) + body + "\n}\n"
    guard let lib = try? device.makeLibrary(source: msl, options: nil),
        let fn = lib.makeFunction(name: "custom_kernel_\(k.name)"),
        let pipe = try? device.makeComputePipelineState(function: fn)
    else { return nil }
    return pipe
}

/// A compute encoder's default `MTLDispatchType.serial` means the `reps`
/// dispatches in one command buffer do not overlap, so GPU busy time over reps
/// is the per-call cost the per-dispatch profile prices. Best of `tries`
/// command buffers to suppress scheduling noise.
func perCallMicros(
    _ pipe: MTLComputePipelineState, k: Int, threads: Int = 1024, reps: Int,
    tries: Int = 3, bind: (MTLComputeCommandEncoder) -> Void
) -> Double {
    var best = Double.greatestFiniteMagnitude
    for _ in 0..<tries {
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

// MARK: - P0: pipeline properties

print("\n=== P0: compiled pipeline properties (both scored attention kernels) ===")
var pipes: [String: MTLComputePipelineState] = [:]
for k in [sliding, full] {
    guard let pipe = compile(k, body: k.body) else {
        print("\(k.name): COMPILE FAILED")
        continue
    }
    pipes[k.name] = pipe
    print("\n\(k.name)  (\(k.sourceLines) source lines)")
    print("  staticThreadgroupMemoryLength  \(pipe.staticThreadgroupMemoryLength) B")
    print("  maxTotalThreadsPerThreadgroup  \(pipe.maxTotalThreadsPerThreadgroup)")
    print("  threadExecutionWidth           \(pipe.threadExecutionWidth)")
    print("  simdgroups per threadgroup     \(1024 / pipe.threadExecutionWidth)"
        + "  (dispatch is 1024 threads)")
}

// MARK: - P1/P2: unit-resolution duration staircase

/// Prints duration vs threadgroup count at unit resolution over 1...3*C, then
/// the first difference, so a riser at a multiple of the core count is visible
/// as a fact rather than inferred from a fit.
func staircase(
    _ label: String, _ pipe: MTLComputePipelineState, upTo: Int, reps: Int,
    bind: (MTLComputeCommandEncoder) -> Void
) -> [Int: Double] {
    print("\n--- \(label): us/call vs K, K = 1 ... \(upTo) ---")
    _ = perCallMicros(pipe, k: 32, reps: 20, bind: bind)
    var out: [Int: Double] = [:]
    var prev = 0.0
    print("     K     us/call     delta   K/cores")
    for k in 1...upTo {
        let us = perCallMicros(pipe, k: k, reps: reps, bind: bind)
        out[k] = us
        print(String(
            format: "  %4d   %9.3f  %+8.3f   %7.3f", k, us, k == 1 ? 0 : us - prev,
            Double(k) / Double(max(cores, 1))))
        prev = us
    }
    return out
}

let staircaseCap = max(3 * cores, 60)
var slidingStair: [Int: Double] = [:]
if let p = pipes[sliding.name] {
    slidingStair = staircase(
        "P1 sliding (N=512 constexpr)", p, upTo: staircaseCap, reps: 200,
        bind: binder(dParams1))
}
if let p = pipes[full.name] {
    _ = staircase(
        "P2 full (N=512 runtime)", p, upTo: staircaseCap, reps: 200,
        bind: binder(makeParams3(n: 512)))
}

// MARK: - P3: KV-length sweep -> fixed vs marginal threadgroup cost

/// Substitutes the sliding kernel's compile-time KV length. Every use of `N` in
/// that body is a loop bound, so this is exactly "the same threadgroup with
/// fewer KV rows" -- which is what one shard of an S-way split does.
func slidingBody(n: Int) -> String {
    let out = sliding.body.replacingOccurrences(
        of: "constexpr int N = 512;", with: "constexpr int N = \(n);")
    precondition(out != sliding.body || n == 512, "N declaration not found")
    return out
}

print("\n=== P3: sliding cost vs KV length N (per-threadgroup work) ===")
print("L = N/64 = main-loop iterations per simdgroup. Rows are the K at which")
print("the measurement is taken; K=1 is one lone threadgroup, K=cores is one")
print("full wave, K=32 is the shipped dispatch.")
let nSweep = [64, 128, 192, 256, 320, 384, 448, 512]
let probeKs = [1, max(cores, 1), 32]
var nCost: [Int: [Int: Double]] = [:]
var header = "     N    L"
for k in probeKs { header += String(format: "   us@K=%-3d", k) }
print(header)
for n in nSweep {
    guard let pipe = compile(sliding, body: slidingBody(n: n)) else {
        print("  N=\(n): COMPILE FAILED")
        continue
    }
    precondition(
        pipe.staticThreadgroupMemoryLength
            == pipes[sliding.name]!.staticThreadgroupMemoryLength,
        "N substitution changed threadgroup memory; the sweep would not be "
            + "comparing the same resource footprint")
    var row = String(format: "  %4d  %3d", n, n / 64)
    var byK: [Int: Double] = [:]
    for k in probeKs {
        let us = perCallMicros(pipe, k: k, reps: 200, bind: binder(dParams1))
        byK[k] = us
        row += String(format: "   %8.3f", us)
    }
    nCost[n] = byK
    print(row)
}

/// Least-squares fit of us = f + g*L at fixed K, reported with the residual so
/// a bad linear model cannot be quoted as a good one.
func fitLinear(_ pts: [(Double, Double)]) -> (f: Double, g: Double, maxAbsResid: Double) {
    let n = Double(pts.count)
    let sx = pts.reduce(0) { $0 + $1.0 }
    let sy = pts.reduce(0) { $0 + $1.1 }
    let sxx = pts.reduce(0) { $0 + $1.0 * $1.0 }
    let sxy = pts.reduce(0) { $0 + $1.0 * $1.1 }
    let g = (n * sxy - sx * sy) / (n * sxx - sx * sx)
    let f = (sy - g * sx) / n
    let resid = pts.map { abs($0.1 - (f + g * $0.0)) }.max() ?? 0
    return (f, g, resid)
}

print("\n--- P3 fit: us(K) = f(K) + g(K) * L ---")
print("  K     f (us)    g (us/iter)   max|resid|   f/g   f as %% of a 512-row TG")
for k in probeKs {
    let pts = nSweep.compactMap { n -> (Double, Double)? in
        guard let v = nCost[n]?[k] else { return nil }
        return (Double(n / 64), v)
    }
    guard pts.count >= 3 else { continue }
    let fit = fitLinear(pts)
    let total = fit.f + fit.g * 8
    print(String(
        format: "  %3d  %8.3f   %10.4f   %10.4f   %6.3f   %8.2f%%",
        k, fit.f, fit.g, fit.maxAbsResid, fit.g == 0 ? .nan : fit.f / fit.g,
        total == 0 ? .nan : 100 * fit.f / total))
}

// MARK: - P4: direct split-geometry emulation

print("\n=== P4: shipped geometry vs S-way KV split, merge cost excluded ===")
print("Shipped is S=1: 32 threadgroups x 512 rows. An S-way split is 32*S")
print("threadgroups x 512/S rows. Only S that divide 512 into a multiple of 64")
print("are exactly representable; the rest are reported at the ceiling length")
print("(the shard that decides the makespan), which favours the split.")
let splitS = [1, 3, 4, 5, 8, 10]
print("    S     TGs   rows/TG   waves@C   us/call   vs S=1   verdict")
var baseUs = 0.0
for s in splitS {
    let rows = max(64, ((512 / s) + 63) / 64 * 64)
    guard let pipe = compile(sliding, body: slidingBody(n: rows)) else { continue }
    let k = 32 * s
    let us = perCallMicros(pipe, k: k, reps: 100, bind: binder(dParams1))
    if s == 1 { baseUs = us }
    let waves = (k + max(cores, 1) - 1) / max(cores, 1)
    let ratio = baseUs > 0 ? us / baseUs : .nan
    print(String(
        format: "  %3d   %5d   %7d   %7d   %8.3f   %6.3f   %@",
        s, k, rows, waves, us, ratio,
        ratio < 0.999 ? "faster" : (ratio > 1.001 ? "SLOWER" : "tie")))
}

// MARK: - P5: projection to the ranked 40-core host

print("\n=== P5: integer-wave efficiency, measured C=\(cores) and ranked C=40 ===")
print("Efficiency is TGs / (waves * C): the fraction of a wave's slots that do")
print("useful work. Sliding dispatches 32 threadgroups, full dispatches 24.")
print("    S   sliding TGs  waves@\(cores)  eff@\(cores)   waves@40  eff@40"
    + "   full TGs  waves@\(cores)  eff@\(cores)   waves@40  eff@40")
for s in 1...10 {
    func line(_ tgs: Int, _ c: Int) -> (Int, Double) {
        let w = (tgs + c - 1) / c
        return (w, Double(tgs) / Double(w * c))
    }
    let (ws, es) = line(32 * s, max(cores, 1))
    let (ws40, es40) = line(32 * s, 40)
    let (wf, ef) = line(24 * s, max(cores, 1))
    let (wf40, ef40) = line(24 * s, 40)
    print(String(
        format: "  %3d   %10d  %7d  %6.1f%%   %8d  %5.1f%%   %8d  %7d  %6.1f%%   %8d  %5.1f%%",
        s, 32 * s, ws, 100 * es, ws40, 100 * es40, 24 * s, wf, 100 * ef, wf40, 100 * ef40))
}

if !slidingStair.isEmpty, let one = slidingStair[1], let shipped = slidingStair[32] {
    let waveCost = (slidingStair[2 * cores] ?? 0) - (slidingStair[cores] ?? 0)
    print("\n--- summary ---")
    print(String(format: "lone threadgroup (K=1)        %8.3f us", one))
    print(String(format: "shipped dispatch (K=32)       %8.3f us", shipped))
    print(String(format: "marginal wave cost (K=%d->%d) %8.3f us",
        cores, 2 * cores, waveCost))
    print(String(format: "wave cost / lone latency      %8.1f%%",
        one > 0 ? 100 * waveCost / one : .nan))
}
