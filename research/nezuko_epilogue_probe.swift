// Step 0 for the attention merge epilogue assignment: decompose the constant
// ~1.07 us that both decode attention kernels pay after their KV loop.
//
//   xcrun swiftc -O research/nezuko_epilogue_probe.swift -o /tmp/nezep
//   /tmp/nezep [path-to-LagunaRuntimeModel.swift]
//
// Extraction, MLX signature replica, dummy buffers and the serial-encoder
// timing loop are the instrument built for research/nezuko_kv_split_probe.swift
// (PR #196); only the ablations below are new.

import Foundation
import Metal

// MARK: - extraction (identical to nezuko_kv_split_probe.swift)

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
        return l.replacingOccurrences(of: "\\\\", with: "\\")
    }
    return (body.joined(separator: "\n"), close)
}

struct ExtractedKernel {
    let name: String
    let header: String
    let body: String
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
    return ExtractedKernel(name: name, header: hdr.text, body: src.text)
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

let device = MTLCreateSystemDefaultDevice()!
let queue = device.makeCommandQueue()!

let sourcePath =
    CommandLine.arguments.count > 1
    ? CommandLine.arguments[1] : "Sources/MLXFastModel/LagunaRuntimeModel.swift"
let scoredLines = try! String(contentsOfFile: sourcePath, encoding: .utf8)
    .split(separator: "\n", omittingEmptySubsequences: false).map(String.init)

let sliding = extractKernel(scoredLines, name: "laguna_sliding_fused_attn_ring_v1")
let full = extractKernel(scoredLines, name: "laguna_full_fused_attn_grow_v1")

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
    guard let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
        let arr = root["SPDisplaysDataType"] as? [[String: Any]],
        let first = arr.first,
        let cores = first["sppci_cores"] as? String, let n = Int(cores)
    else { return 0 }
    return n
}
let cores = max(gpuCoreCount(), 1)

print("=== device ===")
print("name                    \(device.name)")
print("architecture.name       \(device.architecture.name)")
print("gpu-core-count          \(cores)")
print("scored source           \(sourcePath) (\(scoredLines.count) lines)")

// MARK: - buffers

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

let dParams1 = device.makeBuffer(length: 4, options: .storageModeShared)!
dParams1.contents().bindMemory(to: UInt32.self, capacity: 1)[0] = 0

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
        for (i, b) in [
            dRawQ, dRawK, dRawV, dQW, dKW, dAngles, dKCache, dVCache,
            params, dScale, dAttended,
        ].enumerated() {
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

/// An earlier revision timed each variant once as best-of-15 x 600 reps and
/// compared across sections. That is unusable here: the *unmodified* sliding
/// kernel read 15.90, 15.98, 17.99, 18.36 and 18.50 us in five different
/// sections of one 10 s process, a 16% swing that dwarfs every effect under
/// test. Absolute numbers on this host drift on a timescale of seconds, so
/// every comparison below is instead an ABBA-interleaved paired difference:
/// within one round the two pipelines are measured A, B, B, A about 15 ms
/// apart and the round's estimate is (A1+A2)/2 - (B1+B2)/2, which cancels any
/// drift that is linear over the round. The reported statistic is the median
/// over rounds; `spread` is the min..max of the per-round estimates and is the
/// honest resolution limit. `null` rows pair a pipeline against a second,
/// independently compiled copy of the same source and must straddle zero.
let kReps = 400
let kRounds = 11

func timeOnce(
    _ pipe: MTLComputePipelineState, k: Int, threads: Int, reps: Int,
    bind: (MTLComputeCommandEncoder) -> Void
) -> Double {
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
    return (cb.gpuEndTime - cb.gpuStartTime) * 1e6 / Double(reps)
}

struct Paired {
    let a: Double  // median us/call of A
    let b: Double  // median us/call of B
    let delta: Double  // median of (A - B); > 0 means B is faster
    let lo: Double
    let hi: Double
    var spread: String { String(format: "[%+.3f %+.3f]", lo, hi) }
}

func median(_ xs: [Double]) -> Double {
    let s = xs.sorted()
    return s.count % 2 == 1 ? s[s.count / 2] : 0.5 * (s[s.count / 2 - 1] + s[s.count / 2])
}

func paired(
    _ a: MTLComputePipelineState, _ b: MTLComputePipelineState, k: Int,
    threads: Int = 1024, reps: Int = kReps, rounds: Int = kRounds,
    bind: (MTLComputeCommandEncoder) -> Void
) -> Paired {
    var das: [Double] = []
    var abs_: [Double] = []
    var bbs: [Double] = []
    for _ in 0..<rounds {
        let a1 = timeOnce(a, k: k, threads: threads, reps: reps, bind: bind)
        let b1 = timeOnce(b, k: k, threads: threads, reps: reps, bind: bind)
        let b2 = timeOnce(b, k: k, threads: threads, reps: reps, bind: bind)
        let a2 = timeOnce(a, k: k, threads: threads, reps: reps, bind: bind)
        let am = 0.5 * (a1 + a2)
        let bm = 0.5 * (b1 + b2)
        abs_.append(am)
        bbs.append(bm)
        das.append(am - bm)
    }
    return Paired(
        a: median(abs_), b: median(bbs), delta: median(das),
        lo: das.min()!, hi: das.max()!)
}

// MARK: - epilogue line map

/// Line indices (into the extracted body) of every epilogue landmark, located
/// by trimmed-content match so re-indentation of the literal cannot move them.
struct EpilogueMap {
    let lines: [String]
    let decl: Int  // `constexpr int pair_planes = 2;`
    let e0: Int  // `if (lane == 0) {`  -- max/sum broadcast store
    let b1: Int  // barrier 1
    let s0: Int  // `pair_max0 = max_scores[lane];`
    let r1: Int  // round-1 read/reduce loop head
    let b2: Int  // barrier 2
    let w2: Int  // round-2 write loop head
    let b3: Int  // barrier 3
    let r2: Int  // round-2 read/reduce loop head
    let f0: Int  // `if (lane == 0) {`  -- final device store
    let end: Int
}

let kBarrier = "threadgroup_barrier(mem_flags::mem_threadgroup);"
let kLoopHead = "for (int p = 0; p < pair_planes; ++p) {"

func mapEpilogue(_ body: String) -> EpilogueMap {
    let ls = body.split(separator: "\n", omittingEmptySubsequences: false).map(String.init)
    func find(_ needle: String, _ from: Int) -> Int {
        var i = from
        while i < ls.count {
            if ls[i].trimmingCharacters(in: .whitespaces) == needle { return i }
            i += 1
        }
        preconditionFailure("epilogue anchor not found: `\(needle)` from line \(from)")
    }
    let decl = find("constexpr int pair_planes = 2;", 0)
    let e0 = find("if (lane == 0) {", decl)
    let b1 = find(kBarrier, e0)
    let s0 = find("pair_max0 = max_scores[lane];", b1)
    let r1 = find(kLoopHead, s0)
    let b2 = find(kBarrier, r1)
    let w2 = find(kLoopHead, b2)
    let b3 = find(kBarrier, w2)
    let r2 = find(kLoopHead, b3)
    let f0 = find("if (lane == 0) {", r2)
    return EpilogueMap(
        lines: ls, decl: decl, e0: e0, b1: b1, s0: s0, r1: r1, b2: b2, w2: w2,
        b3: b3, r2: r2, f0: f0, end: ls.count)
}

func pad(_ s: String, _ n: Int) -> String {
    s.count >= n ? s : s + String(repeating: " ", count: n - s.count)
}

struct Kernel {
    let name: String
    let k: ExtractedKernel
    let shippedTGs: Int
    let params: MTLBuffer
    let nSubstitutable: Bool
}

let targets = [
    Kernel(name: "sliding", k: sliding, shippedTGs: 32, params: dParams1, nSubstitutable: true),
    Kernel(name: "full", k: full, shippedTGs: 24, params: makeParams3(n: 512), nSubstitutable: false),
]

// MARK: - S0: warm the GPU, the shader cache and the residency set

if let p = compile(sliding, body: sliding.body) {
    for _ in 0..<16 {
        _ = timeOnce(p, k: 32, threads: 1024, reps: kReps, bind: binder(dParams1))
    }
}

// MARK: - S1: duplication pricing of the merge epilogue

/// Line index of the first line whose trimmed content equals `needle`, at or
/// after `from`.
func at(_ ls: [String], _ needle: String, _ from: Int) -> Int {
    var i = from
    while i < ls.count {
        if ls[i].trimmingCharacters(in: .whitespaces) == needle { return i }
        i += 1
    }
    preconditionFailure("anchor not found: `\(needle)`")
}

/// Every duplication variant, including the reference row, carries the same
/// opaque accumulator so the sink itself cancels in the deltas. `dbprobe` is
/// `pair_max0 * 0` -- MLX compiles kernel sources with fast math OFF
/// (`Device::build_library_` calls `setFastMathEnabled(false)`), so neither the
/// initialiser nor any `* 0.0f` sink can be folded to a constant, and no
/// duplicate can be dead-coded. Numerically the epilogue is unchanged.
let probeDecl = "U dbprobe = pair_max0 * 0.0f;"

/// Rewrites the final device store so `dbprobe` reaches memory.
func withProbeSink(_ ls: [String], _ m: EpilogueMap) -> [String] {
    var out = ls
    out.insert(probeDecl, at: m.decl + 1)
    return out.map {
        $0.replacingOccurrences(
            of: "static_cast<bfloat>(pair_o0[p])",
            with: "static_cast<bfloat>(pair_o0[p] + dbprobe)"
        ).replacingOccurrences(
            of: "static_cast<bfloat>(pair_o1[p])",
            with: "static_cast<bfloat>(pair_o1[p] + dbprobe)")
    }
}

struct DupProbe {
    let name: String
    let prices: String
    /// Returns the body lines with one extra copy of the component inserted.
    let make: ([String], EpilogueMap) -> [String]
}

/// Duplicating a block that writes the same values to the same addresses is
/// bit-identical, not merely semantics-preserving.
let dupStore = DupProbe(
    name: "wr x2", prices: "4 threadgroup float stores (round-1 write loop)"
) { ls, m in
    let w1 = at(ls, kLoopHead, m.e0)
    let b1 = at(ls, kBarrier, w1)
    return Array(ls[0..<b1]) + Array(ls[w1..<b1]) + Array(ls[b1...])
}

let dupDevStore = DupProbe(
    name: "devst x2", prices: "8 scalar bfloat device stores (final block)"
) { ls, m in
    let f0 = at(ls, "if (lane == 0) {", m.r2)
    return ls + Array(ls[f0...])
}

/// Reads the same `outputs[]` the shipped round-2 loop reads, after barrier #3
/// and with no intervening write, so the loads are legal and hit warm lines.
let dupRead = DupProbe(
    name: "rd x2", prices: "4 threadgroup float loads + 4 simd_sum"
) { ls, m in
    let f0 = at(ls, "if (lane == 0) {", m.r2)
    let block = """
        {
            U d_acc = 0;
            for (int p = 0; p < pair_planes; ++p) {
                d_acc += simd_sum(
                    outputs[p * pair_plane_size + sg * BDP + lane] * pair_global_factor0);
                d_acc += simd_sum(
                    outputs[(pair_planes + p) * pair_plane_size + sg * BDP + lane]
                    * pair_global_factor1);
            }
            dbprobe += d_acc * 0.0f;
        }
        """
    var out = ls
    out.insert(contentsOf: block.split(separator: "\n").map(String.init), at: f0)
    return out
}

/// Identical shape to `rd x2` with the threadgroup load replaced by a live
/// register, so `rd x2 - red x2` isolates threadgroup load cost.
let dupReduce = DupProbe(
    name: "red x2", prices: "4 simd_sum only (same shape, register operand)"
) { ls, m in
    let f0 = at(ls, "if (lane == 0) {", m.r2)
    let block = """
        {
            U d_acc = 0;
            for (int p = 0; p < pair_planes; ++p) {
                d_acc += simd_sum(pair_o0[p] * pair_global_factor0);
                d_acc += simd_sum(pair_o1[p] * pair_global_factor1);
            }
            dbprobe += d_acc * 0.0f;
        }
        """
    var out = ls
    out.insert(contentsOf: block.split(separator: "\n").map(String.init), at: f0)
    return out
}

let dupScore = DupProbe(
    name: "score x2", prices: "4 tg loads, 2 simd_max, 2 fast::exp, 2 simd_sum"
) { ls, m in
    let r1 = at(ls, kLoopHead, at(ls, "pair_max0 = max_scores[lane];", m.b1))
    let block = """
        {
            U d_m0 = max_scores[lane];
            U d_m1 = max_scores[BN + lane];
            U d_f0 = metal::fast::exp(d_m0 - simd_max(d_m0));
            U d_f1 = metal::fast::exp(d_m1 - simd_max(d_m1));
            dbprobe += (simd_sum(sum_exp_scores[lane] * d_f0)
                + simd_sum(sum_exp_scores[BN + lane] * d_f1)) * 0.0f;
        }
        """
    var out = ls
    out.insert(contentsOf: block.split(separator: "\n").map(String.init), at: r1)
    return out
}

print("\n=== S1: duplication pricing (semantics-preserving, no truncation) ===")
print("Each row inserts ONE extra copy of a single epilogue component and is")
print("ABBA-paired against the reference. Unlike a truncation ladder this keeps")
print("the KV loop, the register pressure and the occupancy fixed, so no stage")
print("can be dead-coded and no row can come out cheaper than the reference")
print("except through measurement noise, which `spread` bounds.")
print("\(kRounds) ABBA rounds x \(kReps) reps at the shipped threadgroup count.")

let dupProbes = [dupStore, dupRead, dupReduce, dupScore, dupDevStore]
var dupResult: [String: [String: Double]] = [:]

for t in targets {
    let m = mapEpilogue(t.k.body)
    let ref = withProbeSink(m.lines, m)
    let refSrc = ref.joined(separator: "\n")
    print("\n--- \(t.name) (\(t.shippedTGs) threadgroups x 1024 threads) ---")
    print("  epilogue spans body lines \(m.decl + 1)..\(m.end) of \(m.end)")
    guard let pRef = compile(t.k, body: refSrc),
        let pNull = compile(t.k, body: refSrc + "\n")
    else { print("  reference build FAILED"); continue }
    var row: [String: Double] = [:]
    let nul = paired(pNull, pRef, k: t.shippedTGs, bind: binder(t.params))
    print("  " + pad("null", 11)
        + String(format: "%8.3f us  %+8.3f us marginal  %@  ", nul.a, -nul.delta,
            nul.spread as NSString) + "second build of the same source")
    for d in dupProbes {
        guard let p = compile(t.k, body: d.make(ref, m).joined(separator: "\n")) else {
            print("  \(d.name): COMPILE FAILED"); continue
        }
        let r = paired(p, pRef, k: t.shippedTGs, bind: binder(t.params))
        row[d.name] = r.delta
        print("  " + pad(d.name, 11)
            + String(format: "%8.3f us  %+8.3f us marginal  %@  ", r.a, r.delta,
                r.spread as NSString) + d.prices)
    }
    dupResult[t.name] = row
    if let st = row["wr x2"], let rd = row["rd x2"], let red = row["red x2"],
        let sc = row["score x2"], let ds = row["devst x2"] {
        let load = rd - red
        let total = 2 * st + 2 * load + 2 * red + sc + ds
        print("  --- reconstructed epilogue (2 rounds of wr/rd, 1 score, 1 store) ---")
        for (lbl, v) in [
            ("threadgroup stores  (2 rounds)", 2 * st),
            ("threadgroup loads   (2 rounds)", 2 * load),
            ("simd reductions     (2 rounds)", 2 * red),
            ("score reduction     (1x)", sc),
            ("final device store  (1x)", ds),
        ] {
            print("     " + pad(lbl, 34)
                + String(format: "%8.3f us  %5.1f%%", v, 100 * v / total))
        }
        print("     " + pad("TOTAL (excl. barriers)", 34)
            + String(format: "%8.3f us  %5.1f%% of the %.3f us call",
                total, 100 * total / nul.b, nul.b))
    }
}

// MARK: - P2: marginal barrier price

print("\n=== P2: marginal barrier price (duplicate barrier #3 x extra) ===")
print("Duplicating a barrier is a semantic no-op, so this prices barrier")
print("latency with no DCE or correctness confound. A flat or noisy row means")
print("barriers are too cheap to resolve at this rep count.")
for t in targets {
    let m = mapEpilogue(t.k.body)
    guard let pBase = compile(t.k, body: t.k.body) else { continue }
    print("  --- \(t.name) ---")
    print("    extra   us/call   delta vs +0    us/barrier   spread of delta")
    for extra in [0, 1, 2, 4, 8] {
        var ls = m.lines
        ls.insert(contentsOf: Array(repeating: kBarrier, count: max(extra, 1)), at: m.b3 + 1)
        // `extra == 0` re-times a second build of the unmodified source: a null row.
        let src = extra == 0 ? t.k.body + "\n" : ls.joined(separator: "\n")
        guard let p = compile(t.k, body: src) else { continue }
        let r = paired(p, pBase, k: t.shippedTGs, bind: binder(t.params))
        print(String(format: "    %5d  %8.3f   %+11.3f   %10.4f   %@",
            extra, r.a, r.delta, extra == 0 ? 0 : r.delta / Double(extra),
            r.spread as NSString))
    }
}

// MARK: - P3: is the epilogue threadgroup-bandwidth bound?

print("\n=== P3: BDP padding sweep -- bank-conflict sensitivity ===")
print("`BDP = BD + 1 = 33` pads each 32-wide plane so the transposing write")
print("`outputs[lane*BDP + sg]` hits 32 distinct banks. BDP = 32 makes that")
print("write a 32-way bank conflict while staying a bijection, hence still")
print("bit-identical. If BDP=32 costs ~the same, the epilogue is not")
print("threadgroup-throughput bound and traffic reduction cannot pay.")
for t in targets {
    guard let pBase = compile(t.k, body: t.k.body) else { continue }
    print("  --- \(t.name) ---")
    print("    BDP   tgmem(B)   us/call   vs BDP=33   spread of delta")
    for bdp in [32, 33, 34, 36, 40] {
        let body = t.k.body.replacingOccurrences(
            of: "constexpr int BDP = BD + 1;", with: "constexpr int BDP = \(bdp);")
        precondition(body != t.k.body, "BDP declaration not found in \(t.name)")
        guard let p = compile(t.k, body: body) else {
            print(String(format: "    %3d   COMPILE/PIPELINE FAILED", bdp))
            continue
        }
        let r = paired(p, pBase, k: t.shippedTGs, bind: binder(t.params))
        print(String(format: "    %3d   %8d  %8.3f   %+9.3f   %@",
            bdp, 4 * 32 * bdp * 4 + 4 * 64 * 4, r.a, r.delta, r.spread as NSString))
    }
}

// MARK: - P4: how much do the 8 divides cost?

print("\n=== P4: divide cost probe (NOT bit-identical -- timing evidence only) ===")
print("Replaces the 8 `acc / pair_sum` divides with a hoisted reciprocal")
print("multiply. Only prices the divides; `a*(1/b) != a/b` in general so this")
print("variant is not shippable as-is.")
for t in targets {
    let reduced = "pair_sum1 = simd_sum(sum_exp_scores[BN + lane] * pair_global_factor1);"
    var body = t.k.body.replacingOccurrences(
        of: reduced,
        with: reduced + "\n"
            + "U pair_rcp0 = pair_sum0 == 0 ? U(1) : U(1) / pair_sum0;\n"
            + "U pair_rcp1 = pair_sum1 == 0 ? U(1) : U(1) / pair_sum1;")
    body = body.replacingOccurrences(
        of: "pair_sum0 == 0 ? acc0 : (acc0 / pair_sum0)", with: "acc0 * pair_rcp0")
    body = body.replacingOccurrences(
        of: "pair_sum1 == 0 ? acc1 : (acc1 / pair_sum1)", with: "acc1 * pair_rcp1")
    let changed = !body.contains("acc0 / pair_sum0") && body.contains("pair_rcp0")
    guard changed, let p = compile(t.k, body: body), let p0 = compile(t.k, body: t.k.body)
    else {
        print("  \(t.name): rewrite did not apply cleanly (changed=\(changed)); skipped")
        continue
    }
    let r = paired(p0, p, k: t.shippedTGs, bind: binder(t.params))
    print("  " + pad(t.name, 9)
        + String(format: "shipped %8.3f   rcp-hoisted %8.3f   saved %+7.3f us  %@",
            r.a, r.b, r.delta, r.spread as NSString))
}

// MARK: - S4: candidate merge-epilogue rewrites

/// The shipped `outputs[]` transpose one float at a time: each thread does
/// 4 stores and 4 loads per round, 8 + 8 over the two rounds. `float4` carries
/// the whole 4-element per-thread slice in one access, so a round becomes
/// 1 store + 1 load. The pairing changes from
/// (round 1 = planes 0/1 of both heads, round 2 = planes 2/3) to
/// (round 1 = head0, round 2 = head1); every `simd_sum` still consumes exactly
/// the same 32 products in the same lane order, so the result is bit-identical.
/// Footprint is unchanged: BN * BDP float4 == 4 * BN * BDP float == 16896 B.
let v1Epilogue = """
if (lane == 0) {
    max_scores[sg] = pair_max0;
    max_scores[BN + sg] = pair_max1;
    sum_exp_scores[sg] = pair_sum0;
    sum_exp_scores[BN + sg] = pair_sum1;
}
outputs4[lane * BDP + sg] =
    float4(pair_o0[0], pair_o0[1], pair_o0[2], pair_o0[3]);
threadgroup_barrier(mem_flags::mem_threadgroup);

pair_max0 = max_scores[lane];
pair_max1 = max_scores[BN + lane];
U pair_global_max0 = simd_max(pair_max0);
U pair_global_max1 = simd_max(pair_max1);
U pair_global_factor0 = metal::fast::exp(pair_max0 - pair_global_max0);
U pair_global_factor1 = metal::fast::exp(pair_max1 - pair_global_max1);
pair_sum0 = simd_sum(sum_exp_scores[lane] * pair_global_factor0);
pair_sum1 = simd_sum(sum_exp_scores[BN + lane] * pair_global_factor1);

float4 pair_v0 = outputs4[sg * BDP + lane];
U acc00 = simd_sum(pair_v0.x * pair_global_factor0);
U acc01 = simd_sum(pair_v0.y * pair_global_factor0);
U acc02 = simd_sum(pair_v0.z * pair_global_factor0);
U acc03 = simd_sum(pair_v0.w * pair_global_factor0);
pair_o0[0] = pair_sum0 == 0 ? acc00 : (acc00 / pair_sum0);
pair_o0[1] = pair_sum0 == 0 ? acc01 : (acc01 / pair_sum0);
pair_o0[2] = pair_sum0 == 0 ? acc02 : (acc02 / pair_sum0);
pair_o0[3] = pair_sum0 == 0 ? acc03 : (acc03 / pair_sum0);

threadgroup_barrier(mem_flags::mem_threadgroup);
outputs4[lane * BDP + sg] =
    float4(pair_o1[0], pair_o1[1], pair_o1[2], pair_o1[3]);
threadgroup_barrier(mem_flags::mem_threadgroup);
float4 pair_v1 = outputs4[sg * BDP + lane];
U acc10 = simd_sum(pair_v1.x * pair_global_factor1);
U acc11 = simd_sum(pair_v1.y * pair_global_factor1);
U acc12 = simd_sum(pair_v1.z * pair_global_factor1);
U acc13 = simd_sum(pair_v1.w * pair_global_factor1);
pair_o1[0] = pair_sum1 == 0 ? acc10 : (acc10 / pair_sum1);
pair_o1[1] = pair_sum1 == 0 ? acc11 : (acc11 / pair_sum1);
pair_o1[2] = pair_sum1 == 0 ? acc12 : (acc12 / pair_sum1);
pair_o1[3] = pair_sum1 == 0 ? acc13 : (acc13 / pair_sum1);

if (lane == 0) {
    device bfloat* pair_out0 =
        attended + head0 * head_dim + sg * v_per_thread;
    device bfloat* pair_out1 =
        attended + head1 * head_dim + sg * v_per_thread;
    for (int p = 0; p < v_per_thread; ++p) {
        pair_out0[p] = static_cast<bfloat>(pair_o0[p]);
        pair_out1[p] = static_cast<bfloat>(pair_o1[p]);
    }
}
"""

/// Arm A: `outputs[]` as float4.
func variantV1(_ k: ExtractedKernel) -> String? {
    let m = mapEpilogue(k.body)
    let head = Array(m.lines[0..<m.decl]).joined(separator: "\n")
    let body = head + "\n" + v1Epilogue
    let decl = "threadgroup U outputs[4 * BN * BDP];"
    guard body.contains(decl) else { return nil }
    return body.replacingOccurrences(
        of: decl, with: "threadgroup float4 outputs4[BN * BDP];")
}

/// The final block writes 8 separate 2-byte values to two 8-byte contiguous,
/// 8-byte aligned runs (`attended + head * 128 + sg * 4` bfloats == a byte
/// offset of `head * 256 + sg * 8`). One `vec<bfloat, 4>` store per head is the
/// same bytes in the same order.
let v2Store = """
if (lane == 0) {
    device bfloat* pair_out0 =
        attended + head0 * head_dim + sg * v_per_thread;
    device bfloat* pair_out1 =
        attended + head1 * head_dim + sg * v_per_thread;
    *reinterpret_cast<device vec<bfloat, 4>*>(pair_out0) = vec<bfloat, 4>(
        static_cast<bfloat>(pair_o0[0]), static_cast<bfloat>(pair_o0[1]),
        static_cast<bfloat>(pair_o0[2]), static_cast<bfloat>(pair_o0[3]));
    *reinterpret_cast<device vec<bfloat, 4>*>(pair_out1) = vec<bfloat, 4>(
        static_cast<bfloat>(pair_o1[0]), static_cast<bfloat>(pair_o1[1]),
        static_cast<bfloat>(pair_o1[2]), static_cast<bfloat>(pair_o1[3]));
}
"""

/// Arm A': vectorised final device store, applied on top of `base`.
func applyV2(_ base: String) -> String? {
    let ls = base.split(separator: "\n", omittingEmptySubsequences: false).map(String.init)
    var i = ls.count - 1
    while i >= 0, ls[i].trimmingCharacters(in: .whitespaces) != "if (lane == 0) {" { i -= 1 }
    guard i > 0 else { return nil }
    return (Array(ls[0..<i]) + v2Store.split(separator: "\n").map(String.init))
        .joined(separator: "\n")
}

/// Arm A'': `max_scores` and `sum_exp_scores` are two 2 * BN float arrays read
/// with four scalar loads per thread. One `float4` per simdgroup is the same
/// 512 bytes in one load, and the lane-indexed read stays fully coalesced.
func applyV3(_ base: String) -> String? {
    let rewrites = [
        ("threadgroup U max_scores[2 * BN];", "threadgroup float4 pair_stats[BN];"),
        ("threadgroup U sum_exp_scores[2 * BN];", ""),
        ("max_scores[sg] = pair_max0;",
            "pair_stats[sg] = float4(pair_max0, pair_max1, pair_sum0, pair_sum1);"),
        ("max_scores[BN + sg] = pair_max1;", ""),
        ("sum_exp_scores[sg] = pair_sum0;", ""),
        ("sum_exp_scores[BN + sg] = pair_sum1;", ""),
        ("pair_max0 = max_scores[lane];",
            "float4 pair_st = pair_stats[lane];\npair_max0 = pair_st.x;"),
        ("pair_max1 = max_scores[BN + lane];", "pair_max1 = pair_st.y;"),
        ("sum_exp_scores[lane]", "pair_st.z"),
        ("sum_exp_scores[BN + lane]", "pair_st.w"),
    ]
    var b = base
    for (from, to) in rewrites {
        guard b.contains(from) else { return nil }
        b = b.replacingOccurrences(of: from, with: to)
    }
    return b
}

print("\n=== S4: candidate merge-epilogue rewrites (ABBA-paired vs shipped) ===")
print("`saved` > 0 means the variant is faster than the shipped kernel it was")
print("interleaved with. `null` is a second build of the shipped source and")
print("bounds what this design can resolve.")
print("V1  outputs[] as float4     : 8 tg stores + 8 tg loads -> 2 + 2")
print("V2  vec<bfloat,4> dev store : 8 scalar device stores -> 2 vector stores")
print("V3  packed float4 stats     : 4 broadcast st + 4 ld -> 1 + 1")
print("V12/V123 stack the above. Each is reported as a separate arm.")

for t in targets {
    print("\n--- \(t.name) ---")
    guard let pShip = compile(t.k, body: t.k.body) else {
        print("  shipped build FAILED"); continue
    }
    let v1 = variantV1(t.k)
    let cases: [(String, String?)] = [
        ("null", t.k.body + "\n"),
        ("V1", v1),
        ("V2", applyV2(t.k.body)),
        ("V3", applyV3(t.k.body)),
        ("V12", v1.flatMap(applyV2)),
        ("V123", v1.flatMap(applyV2).flatMap(applyV3)),
    ]
    for (name, src) in cases {
        guard let s = src else { print("  " + pad(name, 9) + "rewrite did not apply"); continue }
        guard let p = compile(t.k, body: s) else {
            print("  " + pad(name, 9) + "COMPILE FAILED"); continue
        }
        let r = paired(pShip, p, k: t.shippedTGs, bind: binder(t.params))
        print("  " + pad(name, 9)
            + String(format: "%8.3f us   saved %+7.3f us  (%+5.2f%% of call)  %@",
                r.b, r.delta, 100 * r.delta / r.a, r.spread as NSString))
    }
}
