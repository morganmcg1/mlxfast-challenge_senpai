// Research-only host probe (not part of the submission surface).
//
// Paired A/B cost of the routed gate/up NVFP4 SwiGLU QMV kernel
// (`laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2`) against a
// threadgroup-count ladder, for round-99 arm E.
//
// Unlike `research/nezuko_r98_ab_kernel_probe.swift` this probe does not
// extract from Swift: the routed literal carries string interpolation, so
// `research/fern_r99_qmv_variants.py` emits fully resolved `.metal` files and
// this program only compiles and times them.
//
// Mandatory ordering: invoked with one file it runs the NULL control only
// (identical source in both slots).  The dose ladder needs the extra variant
// arguments, so a candidate number cannot be printed before the null spread is.
//
// Build and run:
//   xcrun swiftc -O research/fern_r99_qmv_probe.swift -o /tmp/fernqmv
//   /tmp/fernqmv research/artifacts/fern-r99/depth1_shipped.metal
//   /tmp/fernqmv research/artifacts/fern-r99/depth1_shipped.metal \
//     research/artifacts/fern-r99/tmpl_s1.metal ...

import Foundation
import Metal

let kernelName = "laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2"

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

// MARK: - buffers

/// Deterministic filler so every arm sees the same weight codes, the same
/// `laguna_nvfp4_scale` fast-path branch pattern, and the same router winners.
func filled(_ bytes: Int, seed: UInt64) -> MTLBuffer {
    let buf = device.makeBuffer(length: bytes, options: .storageModeShared)!
    let words = bytes / 8
    let p = buf.contents().bindMemory(to: UInt64.self, capacity: words)
    var s = seed &* 0x9E37_79B9_7F4A_7C15 &+ 1
    for i in 0..<words {
        s ^= s << 13
        s ^= s >> 7
        s ^= s << 17
        p[i] = s
    }
    return buf
}

let inputWidth = 2048
let scalePatchBytes = 128
let packedExpertBytes = 65536
let routedExperts = 8

let dInput = device.makeBuffer(length: inputWidth * 2, options: .storageModeShared)!
do {
    let p = dInput.contents().bindMemory(to: UInt16.self, capacity: inputWidth)
    var s: UInt32 = 0x1234_5678
    for i in 0..<inputWidth {
        s = s &* 1_664_525 &+ 1_013_904_223
        // BF16 magnitudes near 1.0 with mixed signs: representative activations.
        p[i] = UInt16(0x3F00 | (s >> 24)) ^ UInt16((s >> 16) & 0x8000)
    }
}
// 256 experts x 1 MiB, plus a MiB of slack so ladder points above the shipped
// 2048 threadgroups stay in bounds.
let dWeight = filled(257 * 1024 * 1024, seed: 11)
let dScales = filled(scalePatchBytes + 256 * packedExpertBytes + 4096, seed: 23)
let dKeys = filled(256 * 4, seed: 37)
let dActivated = device.makeBuffer(length: routedExperts * 4096 * 2, options: .storageModeShared)!

func bind(_ enc: MTLComputeCommandEncoder) {
    for (i, b) in [dInput, dWeight, dScales, dKeys, dActivated].enumerated() {
        enc.setBuffer(b, offset: 0, index: i)
    }
}

// MARK: - pipelines

let paths = Array(CommandLine.arguments.dropFirst())
precondition(!paths.isEmpty, "usage: fernqmv <reference.metal> [variant.metal ...]")

struct Arm {
    let label: String
    let path: String
    let lines: Int
    let pipe: MTLComputePipelineState
}

func buildArm(_ path: String, label: String) -> Arm {
    let msl = try! String(contentsOfFile: path, encoding: .utf8)
    let lib = try! device.makeLibrary(source: msl, options: nil)
    let fn = lib.makeFunction(name: "custom_kernel_\(kernelName)")!
    let pipe = try! device.makeComputePipelineState(function: fn)
    return Arm(
        label: label, path: path, lines: msl.split(separator: "\n").count, pipe: pipe)
}

func stem(_ path: String) -> String {
    (path as NSString).lastPathComponent.replacingOccurrences(of: ".metal", with: "")
}

let reference = buildArm(paths[0], label: stem(paths[0]))
let variants: [Arm] =
    paths.count == 1
    ? [buildArm(paths[0], label: "NULL(\(stem(paths[0])))")]
    : paths.dropFirst().map { buildArm($0, label: stem($0)) }

print("=== device ===")
print("name                  \(device.name)")
print("architecture          \(device.architecture.name)")
print("gpu cores             \(cores)")
print("kernel                \(kernelName)")
print("mode                  \(paths.count == 1 ? "NULL CONTROL" : "DOSE LADDER")")

print("\n=== pipeline reflection (register/occupancy gate) ===")
print("  arm                          lines   tgMemB   maxTotalThreads   execWidth")
for a in [reference] + variants {
    print(
        String(
            format: "  %-26@   %5d   %6d   %15d   %9d",
            a.label as NSString, a.lines, a.pipe.staticThreadgroupMemoryLength,
            a.pipe.maxTotalThreadsPerThreadgroup, a.pipe.threadExecutionWidth))
}

// MARK: - paired ladder

/// Serial dispatch: the `reps` dispatches in one command buffer do not overlap,
/// so GPU busy time over reps is the per-call cost.
func perCallMicros(_ pipe: MTLComputePipelineState, tg: Int, reps: Int) -> Double {
    let cb = queue.makeCommandBuffer()!
    let enc = cb.makeComputeCommandEncoder()!
    enc.setComputePipelineState(pipe)
    bind(enc)
    for _ in 0..<reps {
        enc.dispatchThreadgroups(
            MTLSize(width: tg, height: 1, depth: 1),
            threadsPerThreadgroup: MTLSize(width: 64, height: 1, depth: 1))
    }
    enc.endEncoding()
    cb.commit()
    cb.waitUntilCompleted()
    return (cb.gpuEndTime - cb.gpuStartTime) * 1e6 / Double(reps)
}

func intList(_ name: String, _ fallback: [Int]) -> [Int] {
    guard let raw = ProcessInfo.processInfo.environment[name] else { return fallback }
    let v = raw.split(separator: ",").compactMap { Int($0) }
    return v.isEmpty ? fallback : v
}
func intVal(_ name: String, _ fallback: Int) -> Int {
    Int(ProcessInfo.processInfo.environment[name] ?? "") ?? fallback
}

// The shipped dispatch is 2048 threadgroups of 64 threads. On the ranked M5 Max
// (40 cores) that is 51.2 TG/core; the occupancy-matched point on a 20-core M4
// Pro is 1024 threadgroups. The ladder brackets it by 8x either way.
let ladder = intList("FERN_LADDER", [128, 256, 512, 1024, 2048])
let rounds = intVal("FERN_ROUNDS", 21)
let reps = intVal("FERN_REPS", 100)

for a in [reference] + variants { _ = perCallMicros(a.pipe, tg: 512, reps: 20) }

print(
    "\n=== paired per-call cost, \(rounds) alternating rounds of \(reps) dispatches ==="
)
print("delta = variant - reference within a round, so drift cancels. neg = faster.")
print("spread = max-min of the per-round deltas.")

for v in variants {
    print("\n--- \(v.label)  vs reference \(reference.label) ---")
    print(
        "    TG  TG/core    ref_min    var_min    d_mean     d_sd    d_min    d_max   spread    d%_ref"
    )
    var perRound: [Int: [Double]] = [:]
    for tg in ladder {
        var refMin = Double.greatestFiniteMagnitude
        var varMin = Double.greatestFiniteMagnitude
        var deltas: [Double] = []
        for r in 0..<rounds {
            let rv: Double
            let vv: Double
            if r % 2 == 0 {
                rv = perCallMicros(reference.pipe, tg: tg, reps: reps)
                vv = perCallMicros(v.pipe, tg: tg, reps: reps)
            } else {
                vv = perCallMicros(v.pipe, tg: tg, reps: reps)
                rv = perCallMicros(reference.pipe, tg: tg, reps: reps)
            }
            refMin = min(refMin, rv)
            varMin = min(varMin, vv)
            deltas.append(vv - rv)
        }
        perRound[tg] = deltas
        let n = Double(deltas.count)
        let mean = deltas.reduce(0, +) / n
        let sd = (deltas.map { ($0 - mean) * ($0 - mean) }.reduce(0, +) / (n - 1))
            .squareRoot()
        let lo = deltas.min()!
        let hi = deltas.max()!
        print(
            String(
                format:
                    "  %4d   %6.2f   %8.2f   %8.2f   %+7.3f   %6.3f   %+6.2f   %+6.2f   %6.2f   %+7.3f",
                tg, Double(tg) / Double(max(cores, 1)), refMin, varMin, mean, sd, lo,
                hi, hi - lo, 100.0 * mean / (refMin > 0 ? refMin : 1)))
    }
    for tg in ladder {
        let s = perRound[tg]!.map { String(format: "%+.2f", $0) }.joined(separator: " ")
        print("  per-round delta TG=\(tg): \(s)")
    }
}
