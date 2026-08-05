// nezuko_phase_decompose.swift
//
// Step 0 of PR #68 (maple-2026-08-05j-attn-marginal-wave-cost).
//
// Decomposes the marginal wave cost of `laguna_sliding_fused_attn_ring_v1`
// into its four phases by building progressively truncated variants of the
// real kernel body and fitting the same staircase model the two-arm
// instrument `research/nezuko_pipeline_latency.swift` uses.
//
// Naming note carried from that instrument: the fit here is
//     t(K) = a + b * ceil(K / W)
// so `b` is the SLOPE, i.e. the quantity the assignment brief calls the
// marginal wave cost `a`, and `a` here is the intercept the brief calls `b`.
// Every derived share below is a share of the SLOPE.
//
// Variants (identical signature, identical threadgroup footprint, identical
// live-out tail; only the amount of real kernel body differs):
//     E   prologue only                       dispatch + tail floor
//     L1  through the Phase 1 barrier         + QK norm/RoPE + V copy
//     L2  through the Phase 2 cache write     + ring row persist
//     L3  through the end of the k-loop       + 16-slot online softmax
//     L4  the whole body                      + epilogue combine
//
// This is a research-only harness. It holds no model, takes no benchmark
// lock, and is legal on a non-M5 host under the assignment's section 0.9.10.
//
// usage: nezdec PATH_TO_LagunaRuntimeModel.swift [reps=3]

import Foundation
import Metal

// MARK: - Extraction (same slicing rules as nezuko_pipeline_latency.swift)

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

    let closeIndent = lines[close].prefix(while: { $0 == " " }).count
    var body: [String] = []
    for l in lines[(open + 1)..<close] {
        body.append(String(l.dropFirst(min(closeIndent, l.prefix(while: { $0 == " " }).count))))
    }
    return (body.joined(separator: "\n").replacingOccurrences(of: "\\\\", with: "\\"), close)
}

func extractSliding(_ path: String) -> (header: String, body: [String]) {
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
    return (
        hdr.text,
        src.text.split(separator: "\n", omittingEmptySubsequences: false).map(String.init)
    )
}

let path = CommandLine.arguments.count > 1
    ? CommandLine.arguments[1]
    : "Sources/MLXFastModel/LagunaRuntimeModel.swift"
let reps = CommandLine.arguments.count > 2 ? Int(CommandLine.arguments[2])! : 3
let (header, body) = extractSliding(path)

// MARK: - Cut points located by anchor text, never by a pinned line number

func anchor(_ needle: String) -> Int {
    var hit = -1
    for (i, l) in body.enumerated() where l.contains(needle) {
        precondition(hit < 0, "anchor `\(needle)` is ambiguous (lines \(hit + 1), \(i + 1))")
        hit = i
    }
    precondition(hit >= 0, "anchor `\(needle)` not found")
    return hit
}

/// Net brace balance of `body[0..<end]`, ignoring `//` comment tails.
func braceDepth(_ end: Int) -> Int {
    var d = 0
    for l in body[0..<end] {
        let code = l.components(separatedBy: "//")[0]
        for c in code {
            if c == "{" { d += 1 }
            if c == "}" { d -= 1 }
        }
    }
    return d
}

let cutPhase1Start = anchor("// Phase 1:")
let cutL1 = anchor("// Phase 2:")
let cutL2 = anchor("// Phase 3:")
let cutL3 = anchor("// Combine:")
let cutL4 = body.count

print("=== cut points (0-based index into the extracted kernel body) ===")
print("   body lines                 \(body.count)")
for (n, c) in [("Phase 1 start", cutPhase1Start), ("L1 end", cutL1),
    ("L2 end", cutL2), ("L3 end", cutL3), ("L4 end", cutL4)]
{
    print(String(format: "   %-15@ %5d   brace depth %d", n as NSString, c, braceDepth(c)))
}
for c in [cutPhase1Start, cutL1, cutL2, cutL3, cutL4] {
    precondition(
        braceDepth(c) == 0,
        "cut at body index \(c) is not at brace depth 0; the base moved and the "
            + "phase boundaries are no longer top-level statements")
}

// MARK: - Uniform scaffolding

let preamble = """
    #include <metal_stdlib>
    #include <metal_simdgroup>
    using namespace metal;
    typedef bfloat bfloat16_t;

    """

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

/// The three Phase-3 threadgroup arrays dominate `staticThreadgroupMemoryLength`
/// (about 18 KiB against 1 KiB for the Phase-1 arrays alone). A truncated
/// variant that omitted them would sit at a different occupancy and its wave
/// slope would not be comparable, so E/L1/L2 declare them too.
let hoistedTG = """

    threadgroup U hoist_outputs[4 * BN * BDP];
    threadgroup U hoist_max_scores[2 * BN];
    threadgroup U hoist_sum_exp_scores[2 * BN];

    """

/// Identical in every variant. Forces the hoisted threadgroup memory to be
/// allocated, keeps the phase results live so nothing upstream is dead-code
/// eliminated, and ends in one device store.
let liveOutTail = """

    // ---- uniform live-out tail ----
    hoist_outputs[lane * BDP + sg] = lo_v[0];
    hoist_max_scores[sg] = lo_v[1];
    hoist_sum_exp_scores[sg] = lo_v[2];
    threadgroup_barrier(mem_flags::mem_threadgroup);
    U lo_acc = hoist_outputs[sg * BDP + lane]
        + hoist_max_scores[lane % BN]
        + hoist_sum_exp_scores[lane % BN]
        + lo_v[3];
    if (lane == 0) {
      attended[head0 * head_dim + sg] = bfloat(lo_acc);
    }
    """

/// Keeps tg_q0/tg_q1/tg_k/tg_v live across all 128 elements of each array.
let liveFromPhase1 = """

    U lo_v[4];
    for (int j = 0; j < 4; ++j) {
      lo_v[j] = U(tg_q0[lane * 4 + j]) + U(tg_q1[lane * 4 + j])
              + U(tg_k[lane * 4 + j]) + U(tg_v[lane * 4 + j]);
    }
    """

/// Keeps both accumulator planes and both running max/sum pairs live, so no
/// half of the two-deep k-loop pipeline can be eliminated.
let liveFromKLoop = """

    U lo_v[4];
    for (int j = 0; j < 4; ++j) {
      lo_v[j] = pair_o0[j] + pair_o1[j];
    }
    lo_v[0] += pair_max0;
    lo_v[1] += pair_max1;
    lo_v[2] += pair_sum0;
    lo_v[3] += pair_sum1;
    """

/// No phase at all: the dispatch, the hoisted threadgroup memory and the tail.
let liveFromNothing = """

    U lo_v[4];
    for (int j = 0; j < 4; ++j) {
      lo_v[j] = U(lane * 4 + j) + U(widx);
    }
    """

struct Variant {
    let tag: String
    let note: String
    let msl: String
}

func assemble(_ src: [String], upTo cut: Int, hoist: Bool, live: String) -> String {
    let kept = src[0..<cut].joined(separator: "\n")
    return preamble + header + "\n" + signature + kept
        + (hoist ? hoistedTG : "") + live + liveOutTail + "\n}\n"
}

func assemble(upTo cut: Int, hoist: Bool, live: String) -> String {
    assemble(body, upTo: cut, hoist: hoist, live: live)
}

// MARK: - Batched-ladder rewrite of the k-loop

// All four per-iteration dot products read only loop-invariant `pair_q*` and
// the keys loaded at the top of the iteration; none of them reads the online
// softmax state. They can therefore be reduced together, before the pipe-a
// rescale, without moving any softmax update. The reduction itself is the
// ascending xor butterfly that research/nezuko_simdsum_step1.log shows is
// bit-identical to `simd_sum` over 1,048,576 adversarial reductions, so no
// within-sum addition order changes either.

func uniqueIndex(_ src: [String], _ needle: String) -> Int {
    var hit = -1
    for (i, l) in src.enumerated() where l.contains(needle) {
        precondition(hit < 0, "`\(needle)` is ambiguous (lines \(hit + 1), \(i + 1))")
        hit = i
    }
    precondition(hit >= 0, "`\(needle)` not found")
    return hit
}

let ladder = """
            for (uint nz_m = 1; nz_m <= 16; nz_m <<= 1) {
                pair_score0 += simd_shuffle_xor(pair_score0, nz_m);
                pair_score1 += simd_shuffle_xor(pair_score1, nz_m);
                pipeb_score0 += simd_shuffle_xor(pipeb_score0, nz_m);
                pipeb_score1 += simd_shuffle_xor(pipeb_score1, nz_m);
            }
    """

func batchedBody() -> [String] {
    let a0 = uniqueIndex(body, "pair_score0 = simd_sum(pair_score0);")
    let a1 = uniqueIndex(body, "pair_score1 = simd_sum(pair_score1);")
    let bDecl = uniqueIndex(body, "U pipeb_score0 = 0;")
    let b0 = uniqueIndex(body, "pipeb_score0 = simd_sum(pipeb_score0);")
    let b1 = uniqueIndex(body, "pipeb_score1 = simd_sum(pipeb_score1);")
    precondition(a1 == a0 + 1 && b1 == b0 + 1 && a1 < bDecl && bDecl < b0,
        "k-loop reduction sites are not in the expected order; the base moved")

    var out: [String] = []
    out += body[0..<a0]                 // loads + pipe-a dot product
    out += body[bDecl..<b0]             // pipe-b dot product, hoisted
    out += ladder.split(separator: "\n", omittingEmptySubsequences: false).map(String.init)
    out += body[(a1 + 1)..<bDecl]       // pipe-a rescale + accumulate, unmoved
    out += body[(b1 + 1)...]            // pipe-b rescale + accumulate, unmoved
    return out
}

let bodyB = batchedBody()
let cutL3b = uniqueIndex(bodyB, "// Combine:")

let variants: [Variant] = [
    Variant(
        tag: "E ", note: "prologue only (dispatch + tail floor)",
        msl: assemble(upTo: cutPhase1Start, hoist: true, live: liveFromNothing)),
    Variant(
        tag: "L1", note: "through the Phase 1 barrier",
        msl: assemble(upTo: cutL1, hoist: true, live: liveFromPhase1)),
    Variant(
        tag: "L2", note: "through the Phase 2 ring write",
        msl: assemble(upTo: cutL2, hoist: true, live: liveFromPhase1)),
    Variant(
        tag: "L3", note: "through the end of the k-loop",
        msl: assemble(upTo: cutL3, hoist: false, live: liveFromKLoop)),
    Variant(
        tag: "L4", note: "whole body incl. epilogue combine",
        msl: assemble(upTo: cutL4, hoist: false, live: liveFromKLoop)),
    Variant(
        tag: "3b", note: "L3 with the batched xor ladder",
        msl: assemble(bodyB, upTo: cutL3b, hoist: false, live: liveFromKLoop)),
    Variant(
        tag: "4b", note: "L4 with the batched xor ladder",
        msl: assemble(bodyB, upTo: bodyB.count, hoist: false, live: liveFromKLoop)),
]

// L3/L4 keep the kernel's own Phase-3 arrays; alias the hoisted names onto
// them so the single shared tail text compiles unchanged in every variant.
let aliasForKept = """

    #define hoist_outputs outputs
    #define hoist_max_scores max_scores
    #define hoist_sum_exp_scores sum_exp_scores

    """

// MARK: - Device

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
        return Int(line.filter { $0.isNumber }) ?? 0
    }
    return 0
}

print("\n=== device ===")
print("   name           \(device.name)")
print("   architecture   \(device.architecture.name)")
print("   gpu cores      \(gpuCoreCount())")

let tgLimit = device.maxThreadgroupMemoryLength
print("\n=== variants ===")
print("   maxThreadgroupMemoryLength \(tgLimit) B")
print("   tag   tgmem B   TG/core   maxTPTG   msl B   description")
var pipes: [MTLComputePipelineState] = []
var residency: [Int] = []
for v in variants {
    let keepsOwnArrays = ["L3", "L4", "3b", "4b"].contains(v.tag)
    let src = keepsOwnArrays
        ? v.msl.replacingOccurrences(
            of: "[[kernel]] void custom_kernel_sliding(",
            with: aliasForKept + "[[kernel]] void custom_kernel_sliding(")
        : v.msl
    let lib: MTLLibrary
    do {
        lib = try device.makeLibrary(source: src, options: nil)
    } catch {
        try! src.write(toFile: "/tmp/nezdec_fail_\(v.tag.trimmingCharacters(in: .whitespaces)).metal",
            atomically: true, encoding: .utf8)
        fatalError("variant \(v.tag) failed to compile: \(error)")
    }
    let pipe = try! device.makeComputePipelineState(function: lib.makeFunction(name: "custom_kernel_sliding")!)
    pipes.append(pipe)
    let tg = pipe.staticThreadgroupMemoryLength
    // Threadgroup memory, not byte count, is what sets residency, so variants
    // land in the same occupancy bucket whenever this quotient matches.
    residency.append(max(1, tgLimit / max(tg, 1)))
    print(String(
        format: "   %@   %7d   %7d   %7d   %5d   %@",
        v.tag as NSString, tg, residency.last!,
        pipe.maxTotalThreadsPerThreadgroup, src.utf8.count, v.note as NSString))
}
if Set(residency).count != 1 {
    print("   WARNING: residency differs across variants; occupancy is not matched")
} else {
    print("   occupancy matched: every variant is limited to \(residency[0]) threadgroup(s) per core")
}

// MARK: - Inputs (shared by every variant, so no arm sees different data)

var rngState: UInt64 = 0x9E37_79B9_7F4A_7C15
func nextUnit() -> Float {
    rngState = rngState &+ 0x9E37_79B9_7F4A_7C15
    var z = rngState
    z = (z ^ (z >> 30)) &* 0xBF58_476D_1CE4_E5B9
    z = (z ^ (z >> 27)) &* 0x94D0_49BB_1331_11EB
    z = z ^ (z >> 31)
    return Float(z >> 40) / Float(1 << 24) * 2.0 - 1.0
}
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
dParams.contents().bindMemory(to: UInt32.self, capacity: 1)[0] = 0
let dScale = device.makeBuffer(length: 4, options: .storageModeShared)!
dScale.contents().bindMemory(to: Float.self, capacity: 1)[0] = 0.088_388_35
let dOut = device.makeBuffer(length: cHeads * cDim * 2, options: .storageModeShared)!

func perCallMicros(_ pipe: MTLComputePipelineState, k: Int, reps: Int, tries: Int = 3) -> Double {
    var best = Double.greatestFiniteMagnitude
    for _ in 0..<tries {
        let cb = queue.makeCommandBuffer()!
        let enc = cb.makeComputeCommandEncoder()!
        enc.setComputePipelineState(pipe)
        for (i, b) in [dRawQ, dRawK, dRawV, dQW, dKW, dAngles, dKCache, dVCache,
            dParams, dScale, dOut].enumerated()
        {
            enc.setBuffer(b, offset: 0, index: i)
        }
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

// MARK: - Sweep

let sweep = [1, 2, 4, 8, 16, 20, 24, 32, 40, 48, 56, 60, 64, 72, 96, 120, 128, 240]
for p in pipes { _ = perCallMicros(p, k: 32, reps: 20) }

print("\n=== staircase sweep (us/call, median of \(reps) interleaved passes) ===")
var samples = [[[Double]]](
    repeating: [[Double]](repeating: [], count: sweep.count), count: pipes.count)
for _ in 0..<reps {
    for (ki, k) in sweep.enumerated() {
        for (pi, p) in pipes.enumerated() {
            samples[pi][ki].append(perCallMicros(p, k: k, reps: 200))
        }
    }
}
var curves = samples.map { $0.map(median) }

print("        K" + variants.map { String(format: "%9@", $0.tag as NSString) }.joined())
for (ki, k) in sweep.enumerated() {
    print(String(format: "     %4d", k)
        + curves.map { String(format: "  %7.3f", $0[ki]) }.joined())
}

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

// Refit every variant on the wave width the full kernel selects, so the
// slopes are all measured against the same staircase and remain comparable.
let wFull = refit(curves[4]).w
func refitFixedW(_ t: [Double], _ w: Int) -> (a: Double, b: Double, rms: Double) {
    let x = sweep.map { Double(($0 + w - 1) / w) }
    let n = Double(x.count)
    let sx = x.reduce(0, +)
    let sy = t.reduce(0, +)
    let sxx = zip(x, x).map(*).reduce(0, +)
    let sxy = zip(x, t).map(*).reduce(0, +)
    let den = n * sxx - sx * sx
    let b = (n * sxy - sx * sy) / den
    let a = (sy - b * sx) / n
    var ss = 0.0
    for (xi, ti) in zip(x, t) { ss += (a + b * xi - ti) * (a + b * xi - ti) }
    return (a, b, (ss / n).squareRoot())
}

print("\n=== staircase refit  t(K) = a + b*ceil(K/W)  (b is the marginal wave cost) ===")
print("   free-W fit selects W=\(wFull) on the full kernel; all rows refit at that W")
print("    tag   freeW    a_int    b_wav      rms")
var slope: [Double] = []
for (i, v) in variants.enumerated() {
    let free = refit(curves[i])
    let f = refitFixedW(curves[i], wFull)
    slope.append(f.b)
    print(String(
        format: "     %@   %5d   %6.3f   %6.3f   %6.4f", v.tag as NSString, free.w, f.a, f.b, f.rms))
}

print("\n=== per-phase share of the marginal wave cost ===")
let bE = slope[0], bL1 = slope[1], bL2 = slope[2], bL3 = slope[3], bL4 = slope[4]
let mono = bE < bL1 && bL1 <= bL2 && bL2 < bL3 && bL3 <= bL4
print("   monotone  b(E) < b(L1) <= b(L2) < b(L3) <= b(L4)   \(mono ? "yes" : "NO -- suspect")")
print(String(format: "   full-kernel marginal wave cost b(L4)   %6.3f us/wave", bL4))
print(String(format: "   dispatch+tail floor          b(E)      %6.3f us/wave (%5.1f%% of b(L4))",
    bE, 100 * bE / bL4))
print("\n   phase                         delta_b   %of b(L4)   %of attributable")
let attributable = bL4 - bE
let rows: [(String, Double)] = [
    ("1  QK norm + RoPE + V copy", bL1 - bE),
    ("2  ring row persist", bL2 - bL1),
    ("3  k-loop online softmax", bL3 - bL2),
    ("4  epilogue combine", bL4 - bL3),
]
for (n, d) in rows {
    print(String(format: "   %-28@ %8.3f   %8.1f%%   %14.1f%%",
        n as NSString, d, 100 * d / bL4, 100 * d / attributable))
}
let top = rows.max(by: { $0.1 < $1.1 })!
print(String(format: "\n   largest phase: %@ at %.1f%% of b(L4)", top.0 as NSString, 100 * top.1 / bL4))
print("   GATE (>=25%% of b(L4)): \(100 * top.1 / bL4 >= 25 ? "PASS" : "HARD STOP 0")")

// The wave slope is the brief's gate, but the scored dispatch runs at a single
// operating point, so the same split is also reported as a share of wall time
// at the assignment's primary K.
let primaryK = 16
let ki16 = sweep.firstIndex(of: primaryK)!
let t16 = curves.map { $0[ki16] }
print("\n=== share of total wall time at the primary operating point K=\(primaryK) ===")
print(String(format: "   full kernel t(L4)   %6.3f us", t16[4]))
print("   component                       delta_us   %of t(L4)")
let rows16: [(String, Double)] = [
    ("0  dispatch + tail floor", t16[0]),
    ("1  QK norm + RoPE + V copy", t16[1] - t16[0]),
    ("2  ring row persist", t16[2] - t16[1]),
    ("3  k-loop online softmax", t16[3] - t16[2]),
    ("4  epilogue combine", t16[4] - t16[3]),
]
for (n, d) in rows16 {
    print(String(format: "   %-28@ %9.3f   %8.1f%%", n as NSString, d, 100 * d / t16[4]))
}

print("\n=== mechanism headroom probe: batched xor ladder in the k-loop ===")
print("   Isolated on the truncated variants, so this sets the pre-registered")
print("   prediction; the full-kernel two-arm ABBA is the separate Step 4 test.")
print("        pair            plain   batched      ratio")
print(String(format: "   L3  k-loop only   %7.3f   %7.3f   %8.4f  (%+.2f%%)",
    t16[3], t16[5], t16[5] / t16[3], 100 * (t16[5] / t16[3] - 1)))
print(String(format: "   L4  full body     %7.3f   %7.3f   %8.4f  (%+.2f%%)",
    t16[4], t16[6], t16[6] / t16[4], 100 * (t16[6] / t16[4] - 1)))
print(String(format: "   wave slope b      %7.3f   %7.3f   %8.4f  (%+.2f%%)",
    slope[4], slope[6], slope[6] / slope[4], 100 * (slope[6] / slope[4] - 1)))
