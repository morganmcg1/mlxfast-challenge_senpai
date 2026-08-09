// Research-only host probe (not part of the submission surface).
//
// Paired A/B cost of one extracted decode-attention kernel body against a
// threadgroup-count ladder, for round-98 arm B (#540, pre-barrier phase-2 K/V
// prefetch).
//
// Why a separate probe from `research/nezuko_occupancy_probe.swift`: that one
// answers "does this body still fit N threadgroups per core" (Phase A/C) and
// prints an *unpaired* cost curve (Phase E). Rule 60 says a latency-hiding arm
// is structurally invisible once threadgroups per core is high enough to hide
// the latency anyway, so the observable here is not a single number but the
// *shape* of the A-minus-B difference across K. On this M4 Pro (20 cores) the
// ranked M5 Max operating point of 32 threadgroups on 40 cores is 0.8 TG/core,
// which is K=16 here; K=40 and K=60 are the 2 and 3 TG/core points where the
// machine hides the latency on its own and a real ILP win must shrink.
//
// Both bodies are extracted from a scored source file by kernel name, compiled
// in this one process, and measured alternately within each round, so thermal
// and clock drift enter both arms of every paired difference.
//
// Build and run:
//   xcrun swiftc -O research/nezuko_r98_ab_kernel_probe.swift -o /tmp/nezab \
//     && /tmp/nezab <base-source.swift> <candidate-source.swift> [kernel-name]

import Foundation
import Metal

// MARK: - source extraction (same contract as nezuko_occupancy_probe.swift)

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
            !l.contains("\\(")
                && !l.replacingOccurrences(of: "\\\\", with: "").contains("\\"),
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

func extractKernel(_ path: String, name: String) -> ExtractedKernel {
    let lines = try! String(contentsOfFile: path, encoding: .utf8)
        .split(separator: "\n", omittingEmptySubsequences: false).map(String.init)
    var decl = -1
    for (i, l) in lines.enumerated() where l.contains("name: \"\(name)\"") {
        decl = i
        break
    }
    precondition(decl >= 0, "kernel declaration `\(name)` not found in \(path)")
    let src = extractLiteral(lines, label: "source", from: decl)
    let hdr = extractLiteral(lines, label: "header", from: src.closeIndex)
    let count = src.text.split(separator: "\n", omittingEmptySubsequences: false).count
    return ExtractedKernel(
        name: name, header: hdr.text, body: src.text, sourceLines: count)
}

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

// MARK: - device, buffers

let device = MTLCreateSystemDefaultDevice()!
let queue = device.makeCommandQueue()!

func gpuCoreCount() -> Int {
    let p = Process()
    p.executableURL = URL(fileURLWithPath: "/usr/sbin/system_profiler")
    p.arguments = ["SPDisplaysDataType", "-json"]
    let pipe = Pipe()
    p.standardOutput = pipe
    p.standardError = FileHandle.nullDevice
    try? p.run()
    let data = pipe.fileHandleForReading.readDataToEndOfFile()
    p.waitUntilExit()
    guard
        let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
        let arr = root["SPDisplaysDataType"] as? [[String: Any]]
    else { return 0 }
    for e in arr {
        if let c = e["sppci_cores"] as? String, let n = Int(c) { return n }
    }
    return 0
}
let cores = gpuCoreCount()

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
// `params` carries three words so the same binding serves the full-attention
// kernel (write index, sequence length, capacity) as well as the sliding one.
let dParams = device.makeBuffer(length: 12, options: .storageModeShared)!
do {
    let p = dParams.contents().bindMemory(to: UInt32.self, capacity: 3)
    p[0] = 7
    p[1] = 512
    p[2] = UInt32(cWindow)
}
let dScale = device.makeBuffer(length: 4, options: .storageModeShared)!
dScale.contents().bindMemory(to: Float.self, capacity: 1)[0] = 0.088_388_35

func bindReal(_ enc: MTLComputeCommandEncoder) {
    for (i, b) in [dRawQ, dRawK, dRawV, dQW, dKW, dAngles, dKCache, dVCache,
        dParams, dScale, dAttended].enumerated()
    {
        enc.setBuffer(b, offset: 0, index: i)
    }
}

// MARK: - build both pipelines

let baseArg = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : ""
let candArg = CommandLine.arguments.count > 2 ? CommandLine.arguments[2] : ""
precondition(!baseArg.isEmpty && !candArg.isEmpty, "usage: nezab <base> <cand> [kernel]")
let kernelName =
    CommandLine.arguments.count > 3
    ? CommandLine.arguments[3] : "laguna_sliding_fused_attn_ring_v1"

func buildPipeline(_ k: ExtractedKernel) -> MTLComputePipelineState {
    let msl = preamble + k.header + "\n" + mlxSignature(k.name) + k.body + "\n}\n"
    let lib = try! device.makeLibrary(source: msl, options: nil)
    let fn = lib.makeFunction(name: "custom_kernel_\(k.name)")!
    return try! device.makeComputePipelineState(function: fn)
}

let arms = [("BASE", baseArg), ("CAND", candArg)].map { label, path -> (String, String, ExtractedKernel, MTLComputePipelineState) in
    let k = extractKernel(path, name: kernelName)
    return (label, path, k, buildPipeline(k))
}

print("=== device ===")
print("name                  \(device.name)")
print("architecture          \(device.architecture.name)")
print("gpu cores             \(cores)")
print("kernel                \(kernelName)")

print("\n=== pipeline properties (register/occupancy gate) ===")
print("  arm    srcLines   tgMemB   maxTotalThreads   execWidth   source")
for (label, path, k, pipe) in arms {
    print(String(
        format: "  %-5@   %7d   %6d   %15d   %9d   %@",
        label as NSString, k.sourceLines, pipe.staticThreadgroupMemoryLength,
        pipe.maxTotalThreadsPerThreadgroup, pipe.threadExecutionWidth,
        path as NSString))
}

// MARK: - paired cost ladder

/// Serial dispatch type means the `reps` dispatches in one command buffer do
/// not overlap, so GPU busy time over reps is the per-call cost.
func perCallMicros(_ pipe: MTLComputePipelineState, k: Int, reps: Int) -> Double {
    let cb = queue.makeCommandBuffer()!
    let enc = cb.makeComputeCommandEncoder()!
    enc.setComputePipelineState(pipe)
    bindReal(enc)
    for _ in 0..<reps {
        enc.dispatchThreadgroups(
            MTLSize(width: k, height: 1, depth: 1),
            threadsPerThreadgroup: MTLSize(width: 1024, height: 1, depth: 1))
    }
    enc.endEncoding()
    cb.commit()
    cb.waitUntilCompleted()
    return (cb.gpuEndTime - cb.gpuStartTime) * 1e6 / Double(reps)
}

let ladder = [8, 16, 20, 24, 32, 40, 60]
let rounds = 15
let reps = 200

// Warm both pipelines before any measured round.
for (_, _, _, pipe) in arms { _ = perCallMicros(pipe, k: 32, reps: 40) }

print("\n=== paired per-call cost, \(rounds) alternating rounds of \(reps) dispatches ===")
print("min is the per-K best over rounds; delta uses the per-round paired")
print("difference, so drift within a round cancels. neg delta = candidate faster.")
print("     K  TG/core   base_min   cand_min   d_min    d_mean    d_sd   t(paired)   %")
for k in ladder {
    var baseMin = Double.greatestFiniteMagnitude
    var candMin = Double.greatestFiniteMagnitude
    var deltas: [Double] = []
    for r in 0..<rounds {
        // Alternate which arm leads so any first-mover effect averages out.
        let b: Double
        let c: Double
        if r % 2 == 0 {
            b = perCallMicros(arms[0].3, k: k, reps: reps)
            c = perCallMicros(arms[1].3, k: k, reps: reps)
        } else {
            c = perCallMicros(arms[1].3, k: k, reps: reps)
            b = perCallMicros(arms[0].3, k: k, reps: reps)
        }
        baseMin = min(baseMin, b)
        candMin = min(candMin, c)
        deltas.append(c - b)
    }
    let n = Double(deltas.count)
    let mean = deltas.reduce(0, +) / n
    let sd = (deltas.map { ($0 - mean) * ($0 - mean) }.reduce(0, +) / (n - 1)).squareRoot()
    let t = sd > 0 ? mean / (sd / n.squareRoot()) : 0
    print(String(
        format: "  %4d   %6.2f   %8.2f   %8.2f   %+6.2f   %+6.2f   %5.2f   %+8.2f   %+6.2f",
        k, Double(k) / Double(max(cores, 1)), baseMin, candMin,
        candMin - baseMin, mean, sd, t, 100.0 * mean / (baseMin > 0 ? baseMin : 1)))
}
