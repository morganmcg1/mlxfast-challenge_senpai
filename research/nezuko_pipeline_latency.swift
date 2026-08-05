// Research-only host harness (not part of the submission surface).
//
// Step 2 of the PR #60 sliding-attention load-pipeline experiment. Compiles the
// `laguna_sliding_fused_attn_ring_v1` body out of *two* copies of the scored
// source -- the assignment base and the working tree -- inside one process, one
// Metal device, and one command queue, so the two arms share the thermal state,
// the clock, and the buffer contents. Reports:
//
//   1. compiled pipeline properties for both arms;
//   2. a bit-for-bit output comparison over pseudorandom bfloat16 inputs at
//      several ring write indices (the loop rewrite claims an identical
//      reduction order, which is a bitwise claim, not a tolerance claim);
//   3. an ABBA-interleaved matched latency comparison at the lone-threadgroup
//      point K=1 and at the shipped sliding dispatch K=32;
//   4. a staircase sweep for both arms plus a `t(K) = a + b*ceil(K/W)` refit,
//      so a change in the serial floor `a` is separated from a change in the
//      per-wave slope `b`.
//
// Build and run:
//   xcrun swiftc -O research/nezuko_pipeline_latency.swift -o /tmp/nezlat \
//     && /tmp/nezlat BASE_COPY.swift Sources/MLXFastModel/LagunaRuntimeModel.swift

import Foundation
import Metal

// MARK: - Extraction (same slicing rules as research/nezuko_occupancy_probe.swift)

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

    let closeIndent =
        lines[close].prefix(while: { $0 == " " }).count
    var body: [String] = []
    for l in lines[(open + 1)..<close] {
        body.append(String(l.dropFirst(min(closeIndent, l.prefix(while: { $0 == " " }).count))))
    }
    return (body.joined(separator: "\n").replacingOccurrences(of: "\\\\", with: "\\"), close)
}

struct Extracted {
    let header: String
    let body: String
    let bodyLines: Int
}

func extractSliding(_ path: String) -> Extracted {
    let lines = try! String(contentsOfFile: path, encoding: .utf8)
        .split(separator: "\n", omittingEmptySubsequences: false).map(String.init)
    var decl = -1
    for (i, l) in lines.enumerated()
    where l.contains("name: \"laguna_sliding_fused_attn_ring_v1\"") {
        decl = i
        break
    }
    precondition(decl >= 0, "sliding kernel declaration not found in \(path)")
    let src = extractLiteral(lines, label: "source", from: decl)
    let hdr = extractLiteral(lines, label: "header", from: src.closeIndex)
    return Extracted(
        header: hdr.text, body: src.text,
        bodyLines: src.text.split(separator: "\n", omittingEmptySubsequences: false).count)
}

let signature = """
    [[kernel]] void custom_kernel_sliding(
      const device bfloat16_t* raw_queries [[buffer(0)]],
      const device bfloat16_t* raw_keys [[buffer(1)]],
      const device bfloat16_t* raw_values [[buffer(2)]],
      const device bfloat16_t* query_weight [[buffer(3)]],
      const device bfloat16_t* key_weight [[buffer(4)]],
      const device float* angles [[buffer(5)]],
      const device bfloat16_t* k_cache [[buffer(6)]],
      const device bfloat16_t* v_cache [[buffer(7)]],
      const constant uint32_t* params [[buffer(8)]],
      const constant float* scale_arr [[buffer(9)]],
      device bfloat16_t* attended [[buffer(10)]],
      uint simdgroup_index_in_threadgroup [[simdgroup_index_in_threadgroup]],
      uint thread_index_in_simdgroup [[thread_index_in_simdgroup]],
      uint3 threadgroup_position_in_grid [[threadgroup_position_in_grid]]) {

    """

let preamble = """
    #include <metal_stdlib>
    #include <metal_simdgroup>
    using namespace metal;
    typedef bfloat bfloat16_t;

    """

// MARK: - Device and arms

let device = MTLCreateSystemDefaultDevice()!
let queue = device.makeCommandQueue()!

func gpuCoreCount() -> Int {
    let p = Process()
    p.executableURL = URL(fileURLWithPath: "/usr/sbin/system_profiler")
    p.arguments = ["SPDisplaysDataType"]
    let pipe = Pipe()
    p.standardOutput = pipe
    try? p.run()
    let data = pipe.fileHandleForReading.readDataToEndOfFile()
    p.waitUntilExit()
    let text = String(data: data, encoding: .utf8) ?? ""
    for line in text.split(separator: "\n") where line.contains("Total Number of Cores") {
        let digits = line.filter { $0.isNumber }
        return Int(digits) ?? 0
    }
    return 0
}

let cores = gpuCoreCount()
print("=== device ===")
print("name                    \(device.name)")
print("architecture            \(device.architecture.name)")
print("gpu cores               \(cores)")

precondition(CommandLine.arguments.count > 2, "usage: nezlat BASE.swift CANDIDATE.swift")
let paths = [CommandLine.arguments[1], CommandLine.arguments[2]]
let names = ["A base", "B cand"]

func build(_ path: String) -> (MTLComputePipelineState, Extracted, Int) {
    let e = extractSliding(path)
    let msl = preamble + e.header + "\n" + signature + e.body + "\n}\n"
    let lib = try! device.makeLibrary(source: msl, options: nil)
    let fn = lib.makeFunction(name: "custom_kernel_sliding")!
    let pipe = try! device.makeComputePipelineState(function: fn)
    return (pipe, e, msl.utf8.count)
}

print("\n=== arms ===")
var pipes: [MTLComputePipelineState] = []
for (n, p) in zip(names, paths) {
    let (pipe, e, bytes) = build(p)
    pipes.append(pipe)
    print("\(n)  \(p)")
    print("  body lines                     \(e.bodyLines)")
    print("  assembled MSL bytes            \(bytes)")
    print("  staticThreadgroupMemoryLength  \(pipe.staticThreadgroupMemoryLength) B")
    print("  maxTotalThreadsPerThreadgroup  \(pipe.maxTotalThreadsPerThreadgroup)")
    print("  threadExecutionWidth           \(pipe.threadExecutionWidth)")
}

// MARK: - Pseudorandom shared inputs

var rngState: UInt64 = 0x9E37_79B9_7F4A_7C15

func nextUnit() -> Float {
    rngState = rngState &+ 0x9E37_79B9_7F4A_7C15
    var z = rngState
    z = (z ^ (z >> 30)) &* 0xBF58_476D_1CE4_E5B9
    z = (z ^ (z >> 27)) &* 0x94D0_49BB_1331_11EB
    z = z ^ (z >> 31)
    return Float(z >> 40) / Float(1 << 24) * 2.0 - 1.0
}

/// Truncating float32 -> bfloat16, which is the same 16 bits both arms read.
func bf16(_ f: Float) -> UInt16 { UInt16(truncatingIfNeeded: f.bitPattern >> 16) }

func randomBF16(_ elements: Int) -> MTLBuffer {
    let buf = device.makeBuffer(length: elements * 2, options: .storageModeShared)!
    let p = buf.contents().bindMemory(to: UInt16.self, capacity: elements)
    for i in 0..<elements { p[i] = bf16(nextUnit()) }
    return buf
}

let cHeads = 512
let cKV = 128
let cDim = 128
let cWindow = 512
let dRawQ = randomBF16(cHeads * cDim)
let dRawK = randomBF16(cKV * cDim)
let dRawV = randomBF16(cKV * cDim)
let dQW = randomBF16(cDim)
let dKW = randomBF16(cDim)
let dKCache = randomBF16(cKV * cWindow * cDim)
let dVCache = randomBF16(cKV * cWindow * cDim)
let dAngles = device.makeBuffer(length: cDim * 4, options: .storageModeShared)!
do {
    let p = dAngles.contents().bindMemory(to: Float.self, capacity: cDim)
    for i in 0..<cDim { p[i] = powf(10_000.0, -2.0 * Float(i % 64) / Float(cDim)) }
}
let dParams = device.makeBuffer(length: 4, options: .storageModeShared)!
let dScale = device.makeBuffer(length: 4, options: .storageModeShared)!
dScale.contents().bindMemory(to: Float.self, capacity: 1)[0] = 0.088_388_35
let outs = [
    device.makeBuffer(length: cHeads * cDim * 2, options: .storageModeShared)!,
    device.makeBuffer(length: cHeads * cDim * 2, options: .storageModeShared)!,
]

func bind(_ enc: MTLComputeCommandEncoder, out: MTLBuffer) {
    for (i, b) in [dRawQ, dRawK, dRawV, dQW, dKW, dAngles, dKCache, dVCache,
        dParams, dScale, out].enumerated()
    {
        enc.setBuffer(b, offset: 0, index: i)
    }
}

func run(_ pipe: MTLComputePipelineState, k: Int, out: MTLBuffer) {
    let cb = queue.makeCommandBuffer()!
    let enc = cb.makeComputeCommandEncoder()!
    enc.setComputePipelineState(pipe)
    bind(enc, out: out)
    enc.dispatchThreadgroups(
        MTLSize(width: k, height: 1, depth: 1),
        threadsPerThreadgroup: MTLSize(width: 1024, height: 1, depth: 1))
    enc.endEncoding()
    cb.commit()
    cb.waitUntilCompleted()
}

// MARK: - Bitwise output comparison

print("\n=== bitwise output comparison (pseudorandom bfloat16 inputs) ===")
print("Every checked lane must match bit-for-bit: the rewrite claims the same")
print("slot order and the same statement order, not a tolerance.")
print("   widx      K   lanes   bitwise-equal   maxUlpDiff   maxAbsDiff")
var allBitwiseEqual = true
for widx in [0, 1, 15, 31, 32, 33, 255, 288, 480, 511] {
    for k in [1, 32] {
        dParams.contents().bindMemory(to: UInt32.self, capacity: 1)[0] = UInt32(widx)
        for (idx, pipe) in pipes.enumerated() {
            memset(outs[idx].contents(), 0, cHeads * cDim * 2)
            run(pipe, k: k, out: outs[idx])
        }
        let lanes = k * 2 * cDim
        let a = outs[0].contents().bindMemory(to: UInt16.self, capacity: lanes)
        let b = outs[1].contents().bindMemory(to: UInt16.self, capacity: lanes)
        var equal = 0
        var maxUlp = 0
        var maxAbs = Float(0)
        for i in 0..<lanes {
            if a[i] == b[i] {
                equal += 1
            } else {
                maxUlp = max(maxUlp, abs(Int(a[i]) - Int(b[i])))
                let fa = Float(bitPattern: UInt32(a[i]) << 16)
                let fb = Float(bitPattern: UInt32(b[i]) << 16)
                maxAbs = max(maxAbs, abs(fa - fb))
            }
        }
        if equal != lanes { allBitwiseEqual = false }
        print(String(
            format: "   %4d   %4d   %5d   %13@   %10d   %10.3e",
            widx, k, lanes, (equal == lanes ? "yes" : "NO") as NSString, maxUlp, maxAbs))
    }
}
print(allBitwiseEqual
    ? "verdict: every checked lane is bit-identical across the two arms"
    : "verdict: BITWISE MISMATCH -- the reduction order changed")

// MARK: - Timing

/// One compute encoder's default serial dispatch type means the `reps`
/// dispatches do not overlap, so GPU busy time over reps is the per-call cost.
/// Best of `tries` command buffers suppresses scheduling noise.
func perCallMicros(
    _ pipe: MTLComputePipelineState, k: Int, reps: Int, tries: Int = 3
) -> Double {
    var best = Double.greatestFiniteMagnitude
    for _ in 0..<tries {
        let cb = queue.makeCommandBuffer()!
        let enc = cb.makeComputeCommandEncoder()!
        enc.setComputePipelineState(pipe)
        bind(enc, out: outs[0])
        for _ in 0..<reps {
            enc.dispatchThreadgroups(
                MTLSize(width: k, height: 1, depth: 1),
                threadsPerThreadgroup: MTLSize(width: 1024, height: 1, depth: 1))
        }
        enc.endEncoding()
        cb.commit()
        cb.waitUntilCompleted()
        best = min(best, (cb.gpuEndTime - cb.gpuStartTime) * 1e6 / Double(reps))
    }
    return best
}

func median(_ v: [Double]) -> Double {
    let s = v.sorted()
    return s.count % 2 == 1 ? s[s.count / 2] : (s[s.count / 2 - 1] + s[s.count / 2]) / 2
}

dParams.contents().bindMemory(to: UInt32.self, capacity: 1)[0] = 0
for p in pipes { _ = perCallMicros(p, k: 32, reps: 20) }

print("\n=== ABBA matched latency (us/call, best-of-3 command buffers) ===")
print("Each pair runs A,B,B,A; the arm value is the mean of its two slots, so a")
print("monotone drift over the pair cancels to first order.")
let pairs = CommandLine.arguments.count > 3 ? Int(CommandLine.arguments[3])! : 6
let skipSweep = CommandLine.arguments.contains("nosweep")
// abbaK=1,20,32 overrides the matched-latency operating points. The default pair
// is the assignment's primary K=1 and the shipped sliding dispatch K=32; other
// values matter because the throughput wave width equals the GPU core count, so
// the same K sits in a different wave on a different machine.
let abbaK: [Int] = CommandLine.arguments
    .first(where: { $0.hasPrefix("abbaK=") })
    .map { $0.dropFirst(6).split(separator: ",").map { Int($0)! } } ?? [1, 32]
for k in abbaK {
    print("  K=\(k)")
    print("     pair    A base    B cand    B/A")
    var ratios: [Double] = []
    var aAll: [Double] = []
    var bAll: [Double] = []
    for p in 0..<pairs {
        let a1 = perCallMicros(pipes[0], k: k, reps: 200)
        let b1 = perCallMicros(pipes[1], k: k, reps: 200)
        let b2 = perCallMicros(pipes[1], k: k, reps: 200)
        let a2 = perCallMicros(pipes[0], k: k, reps: 200)
        let a = (a1 + a2) / 2
        let b = (b1 + b2) / 2
        ratios.append(b / a)
        aAll.append(a)
        bAll.append(b)
        print(String(format: "     %4d   %7.3f   %7.3f   %6.4f", p + 1, a, b, b / a))
    }
    let mean = ratios.reduce(0, +) / Double(ratios.count)
    let sd = ratios.count > 1
        ? (ratios.map { ($0 - mean) * ($0 - mean) }.reduce(0, +)
            / Double(ratios.count - 1)).squareRoot()
        : 0
    let sem = sd / Double(ratios.count).squareRoot()
    print(String(
        format: "   median   %7.3f   %7.3f   %6.4f   (candidate %+.2f%%)",
        median(aAll), median(bAll), median(ratios), (median(ratios) - 1) * 100))
    print(String(
        format: "     mean   %7.3f   %7.3f   %6.4f   +- %.4f sem  -> %+.2f%% +- %.2f%%",
        aAll.reduce(0, +) / Double(pairs), bAll.reduce(0, +) / Double(pairs),
        mean, sem, (mean - 1) * 100, sem * 100))
}

// MARK: - Staircase sweep and refit

let sweep = [1, 2, 4, 8, 16, 20, 24, 32, 40, 48, 56, 60, 64, 72, 96, 120, 128, 240]
if skipSweep { exit(allBitwiseEqual ? 0 : 1) }
print("\n=== staircase sweep (us/call) ===")
print("        K    A base    B cand      B/A")
var curves: [[Double]] = [[], []]
for k in sweep {
    let a = perCallMicros(pipes[0], k: k, reps: 200)
    let b = perCallMicros(pipes[1], k: k, reps: 200)
    curves[0].append(a)
    curves[1].append(b)
    print(String(format: "     %4d   %7.3f   %7.3f   %6.4f", k, a, b, b / a))
}

/// Least-squares fit of `t(K) = a + b*ceil(K/W)` with W chosen by grid search.
/// `a` is the serial floor the lone-threadgroup point exposes; `b` is the
/// marginal cost of one more resident wave.
func refit(_ t: [Double]) -> (w: Int, a: Double, b: Double, rms: Double) {
    var best = (w: 0, a: 0.0, b: 0.0, rms: Double.greatestFiniteMagnitude)
    for w in 8...48 {
        let x = sweep.map { Double(($0 + w - 1) / w) }
        let n = Double(x.count)
        let sx = x.reduce(0, +)
        let sy = t.reduce(0, +)
        let sxx = zip(x, x).map(*).reduce(0, +)
        let sxy = zip(x, t).map(*).reduce(0, +)
        let den = n * sxx - sx * sx
        if abs(den) < 1e-12 { continue }
        let b = (n * sxy - sx * sy) / den
        let a = (sy - b * sx) / n
        var ss = 0.0
        for (xi, ti) in zip(x, t) { ss += (a + b * xi - ti) * (a + b * xi - ti) }
        let rms = (ss / n).squareRoot()
        if rms < best.rms { best = (w, a, b, rms) }
    }
    return best
}

print("\n=== staircase refit  t(K) = a + b*ceil(K/W) ===")
print("      arm     W        a        b      rms   a/t(1)")
for (i, n) in names.enumerated() {
    let f = refit(curves[i])
    print(String(
        format: "   %6@   %3d   %6.3f   %6.3f   %6.3f   %6.3f",
        n as NSString, f.w, f.a, f.b, f.rms, f.a / curves[i][0]))
}
