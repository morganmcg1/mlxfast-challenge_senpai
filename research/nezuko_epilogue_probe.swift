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

func perCallMicros(
    _ pipe: MTLComputePipelineState, k: Int, threads: Int = 1024, reps: Int = 200,
    tries: Int = 5, bind: (MTLComputeCommandEncoder) -> Void
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

/// Anti-DCE tail. Every threadgroup array and every live register the truncated
/// epilogue produced is folded into one value *outside* the `lane == 0` branch,
/// so the compiler can neither drop the threadgroup stores nor sink the loads
/// into the branch. Its cost is a constant shared by every rung, so it cancels
/// in the rung-to-rung deltas.
let sink = """

    U dbsink = pair_o0[0] + pair_o0[1] + pair_o0[2] + pair_o0[3]
        + pair_o1[0] + pair_o1[1] + pair_o1[2] + pair_o1[3]
        + pair_max0 + pair_max1 + pair_sum0 + pair_sum1
        + outputs[lane * BDP + sg] + max_scores[sg] + sum_exp_scores[sg];
    if (lane == 0) {
        attended[head0 * head_dim + sg * v_per_thread] = static_cast<bfloat>(dbsink);
    }
    """

func pad(_ s: String, _ n: Int) -> String {
    s.count >= n ? s : s + String(repeating: " ", count: n - s.count)
}

func prefix(_ m: EpilogueMap, _ cut: Int) -> String {
    let head = m.lines[0..<cut].joined(separator: "\n")
    return cut == m.end ? head : head + "\n" + sink
}

struct Rung {
    let name: String
    let cut: (EpilogueMap) -> Int
    let adds: String
}

let ladder: [Rung] = [
    Rung(name: "L0 pre-epilogue", cut: { $0.e0 }, adds: "KV loop only (baseline)"),
    Rung(name: "L1 +bcast+wr1", cut: { $0.b1 }, adds: "max/sum store + round-1 outputs[] writes"),
    Rung(name: "L2 +barrier1", cut: { $0.b1 + 1 }, adds: "barrier #1 (RAW)"),
    Rung(name: "L3 +scorered", cut: { $0.r1 }, adds: "4 tg reads, 2 simd_max, 2 exp, 2 simd_sum"),
    Rung(name: "L4 +rd1", cut: { $0.b2 }, adds: "round-1: 4 tg reads, 4 simd_sum, 4 div"),
    Rung(name: "L5 +barrier2", cut: { $0.b2 + 1 }, adds: "barrier #2 (WAR)"),
    Rung(name: "L6 +wr2", cut: { $0.b3 }, adds: "round-2: 4 tg writes"),
    Rung(name: "L7 +barrier3", cut: { $0.b3 + 1 }, adds: "barrier #3 (RAW)"),
    Rung(name: "L8 +rd2", cut: { $0.f0 }, adds: "round-2: 4 tg reads, 4 simd_sum, 4 div"),
    Rung(name: "L9 +store", cut: { $0.end }, adds: "final 8-element device store (== shipped)"),
]

func nSub(_ body: String, _ n: Int) -> String {
    body.replacingOccurrences(
        of: "constexpr int N = 512;", with: "constexpr int N = \(n);")
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

// MARK: - P1: the prefix ladder

print("\n=== P1: epilogue prefix ladder (what the constant microseconds buy) ===")
print("Each rung compiles the kernel truncated at that point plus a shared")
print("anti-DCE sink; `delta` is the marginal cost of the stage named in `adds`.")
print("Cost is per call at the shipped threadgroup count, best of 5 x 200 reps.")

var ladderAbs: [String: [Double]] = [:]

for t in targets {
    let m = mapEpilogue(t.k.body)
    print("\n--- \(t.name) (\(t.shippedTGs) threadgroups x 1024 threads) ---")
    print("  epilogue spans body lines \(m.e0 + 1)..\(m.end) of \(m.end)")
    print("  rung               us/call     delta     %of full   adds")
    var prev = 0.0
    var full0 = 0.0
    var col: [Double] = []
    for (i, r) in ladder.enumerated() {
        guard let p = compile(t.k, body: prefix(m, r.cut(m))) else {
            print("  \(r.name)  COMPILE FAILED")
            col.append(Double.nan)
            continue
        }
        let us = perCallMicros(p, k: t.shippedTGs, bind: binder(t.params))
        col.append(us)
        if i == ladder.count - 1 { full0 = us }
        let d = i == 0 ? 0.0 : us - prev
        print("  " + pad(r.name, 17)
            + String(format: "%8.3f  %+8.3f   ", us, d)
            + r.adds)
        prev = us
    }
    ladderAbs[t.name] = col
    if col.count == ladder.count, col[0].isFinite, full0.isFinite {
        let epi = full0 - col[0]
        print(String(format: "  epilogue total  %8.3f us  = %.1f%% of the %.3f us call",
            epi, 100 * epi / full0, full0))
        let bar = (col[2] - col[1]) + (col[5] - col[4]) + (col[7] - col[6])
        let traffic = (col[1] - col[0]) + (col[6] - col[5])
        let reduce = (col[3] - col[2]) + (col[4] - col[3]) + (col[8] - col[7])
        let store = col[9] - col[8]
        print("  --- bucketed ---")
        for (lbl, v) in [
            ("(a) barriers x3", bar), ("(b) threadgroup writes", traffic),
            ("(c) reads + simd reductions + divides", reduce), ("(d) final device store", store),
        ] {
            print("     " + pad(lbl, 39)
                + String(format: "%8.3f us   %5.1f%% of epilogue", v, 100 * v / epi))
        }
    }
}

// MARK: - P2: marginal barrier price

print("\n=== P2: marginal barrier price (duplicate barrier #3 x extra) ===")
print("Duplicating a barrier is a semantic no-op, so this prices barrier")
print("latency with no DCE or correctness confound. A flat row means the")
print("compiler coalesced the adjacent barriers; then P1's L2/L5/L7 deltas")
print("are the only barrier evidence.")
for t in targets {
    let m = mapEpilogue(t.k.body)
    print("  --- \(t.name) ---")
    print("    extra   us/call   delta vs +0   us per extra barrier")
    var base = 0.0
    for extra in [0, 1, 2, 4, 8] {
        var ls = m.lines
        if extra > 0 {
            ls.insert(contentsOf: Array(repeating: kBarrier, count: extra), at: m.b3 + 1)
        }
        guard let p = compile(t.k, body: ls.joined(separator: "\n")) else { continue }
        let us = perCallMicros(p, k: t.shippedTGs, bind: binder(t.params))
        if extra == 0 { base = us }
        print(String(format: "    %5d  %8.3f   %+11.3f   %19.4f",
            extra, us, us - base, extra == 0 ? 0 : (us - base) / Double(extra)))
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
    print("  --- \(t.name) ---")
    print("    BDP   tgmem(B)   us/call   vs BDP=33")
    var base = 0.0
    for bdp in [32, 33, 34, 36, 40] {
        let body = t.k.body.replacingOccurrences(
            of: "constexpr int BDP = BD + 1;", with: "constexpr int BDP = \(bdp);")
        precondition(body != t.k.body, "BDP declaration not found in \(t.name)")
        guard let p = compile(t.k, body: body) else {
            print(String(format: "    %3d   COMPILE/PIPELINE FAILED", bdp))
            continue
        }
        let us = perCallMicros(p, k: t.shippedTGs, bind: binder(t.params))
        if bdp == 33 { base = us }
        print(String(format: "    %3d   %8d  %8.3f   %+8.3f",
            bdp, 4 * 32 * bdp * 4 + 4 * 64 * 4, us, us - base))
    }
    _ = base
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
    let a = perCallMicros(p0, k: t.shippedTGs, bind: binder(t.params))
    let b = perCallMicros(p, k: t.shippedTGs, bind: binder(t.params))
    print("  " + pad(t.name, 9)
        + String(format: "shipped %8.3f   rcp-hoisted %8.3f   saved %+7.3f us", a, b, a - b))
}

// MARK: - P5: KV-length independence of the epilogue

print("\n=== P5: epilogue cost vs KV length (sliding only, N substitutable) ===")
print("Confirms the epilogue really is a constant: it must not move with N.")
let ms = mapEpilogue(sliding.body)
print("     N   full us   L0 us   epilogue us   %of call")
for n in [64, 128, 256, 512] where targets[0].nSubstitutable {
    guard let pf = compile(sliding, body: nSub(sliding.body, n)),
        let p0 = compile(sliding, body: nSub(prefix(ms, ms.e0), n))
    else { continue }
    let a = perCallMicros(pf, k: 32, bind: binder(dParams1))
    let b = perCallMicros(p0, k: 32, bind: binder(dParams1))
    print(String(format: "  %4d  %8.3f  %6.3f   %11.3f   %6.1f%%", n, a, b, a - b, 100 * (a - b) / a))
}
