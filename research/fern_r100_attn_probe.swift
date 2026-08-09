// Research-only host probe (not part of the submission surface).
//
// Round-100 arm A, part P2: threadgroup-count cost ladder for the decode
// attention kernels, instrumented for probe *fidelity* rather than for a
// candidate verdict.
//
// It answers three things that `research/nezuko_r98_ab_kernel_probe.swift`
// cannot, because that probe hardcodes its ladder and always binds one
// resident K/V cache:
//
//   E1  the absolute shape of t(K).  A threadgroup-doubling change such as
//       "one query head per threadgroup" only pays if t(2K) < 2*t(K), so the
//       quantity of interest is phi = t(64)/t(32), and whether t(K) is a
//       smooth curve or a staircase whose risers sit at multiples of this
//       host's core count.  A staircase is an occupancy artifact of *this*
//       machine and does not transfer to the ranked 40-core M5; a smooth
//       curve does.  The ladder therefore straddles 20, 40 and 60.
//
//   P1.1 which side of the roofline each rung lives on.  The probe re-reads
//       the same K/V window `reps` times per round, so its read amplification
//       is `reps`, while a real decode step reads each window once.  The
//       printed unique/requested/achieved columns make that gap explicit
//       instead of leaving it as an assumption.
//
//   P1.2 whether a verdict survives losing cache residency.  FERN_DEFEAT_SLOTS
//       rotates the k_cache/v_cache binding offset per repetition so the
//       working set stops fitting the system level cache.  Both arms of every
//       paired round rotate identically, so the rotation cannot manufacture a
//       difference; it can only remove one that depended on residency.
//
// Passing one source path runs BASE against itself: a NULL control whose true
// difference is exactly zero, which measures the instrument's own bias floor.
//
// Build and run:
//   xcrun swiftc -O research/fern_r100_attn_probe.swift -o /tmp/fernattn \
//     && /tmp/fernattn <base-source.swift> [cand-source.swift]

import Foundation
import Metal

// MARK: - env knobs

func intVal(_ name: String, _ fallback: Int) -> Int {
    guard let raw = ProcessInfo.processInfo.environment[name], let v = Int(raw) else {
        return fallback
    }
    return v
}

func intList(_ name: String, _ fallback: [Int]) -> [Int] {
    guard let raw = ProcessInfo.processInfo.environment[name] else { return fallback }
    let parsed = raw.split(separator: ",").compactMap { Int($0.trimmingCharacters(in: .whitespaces)) }
    precondition(!parsed.isEmpty, "\(name) set but unparseable: \(raw)")
    return parsed
}

func strVal(_ name: String, _ fallback: String) -> String {
    ProcessInfo.processInfo.environment[name] ?? fallback
}

// Risers are expected at multiples of the core count, so the ladder brackets
// 20/40/60 from both sides on a 20-core host.
let ladder = intList("FERN_LADDER", [8, 16, 20, 21, 24, 32, 40, 41, 48, 56, 60, 61, 64, 80, 96])
let rounds = intVal("FERN_ROUNDS", 21)
let reps = intVal("FERN_REPS", 200)
let defeatSlots = max(intVal("FERN_DEFEAT_SLOTS", 1), 1)
let cacheCopies = max(intVal("FERN_CACHE_COPIES", 1), 1)

/// R102-A rung 1. Rewrites the kernel's KV row-loop bound so one threadgroup
/// attends a sub-range of the 512-row window, which is what a split-K
/// threadgroup does. The cache addressing constant `window` is deliberately
/// left at 512 so the address stride per kv-head is identical at every point.
/// The ring is `i = sg; i + 3*BN < N; i += 4*BN` with BN=32 over 32 simdgroups,
/// so N = 128*M runs exactly M iterations and N = 96 runs zero.
let attnRows = intVal("FERN_ROWS", 512)
/// Pins the defeat rotation stride to a fixed kv-head count so a K sweep does
/// not silently change the address spread. 0 keeps the per-K default.
let strideKVOverride = intVal("FERN_STRIDE_KV", 0)
/// Row counts visited in rotating order inside one round. Non-empty selects the
/// interleaved sweep, which is the only block whose across-N differences are
/// free of block-order drift. Repeat a value to get a free within-round null.
let sweepRows = intList("FERN_ROWS_SWEEP", [])
/// In defeat mode the DRAM working set scales with rows, so a raw slot count
/// would compare a 512-row point against a 4x smaller footprint. This holds
/// bytes per round fixed by scaling slots as window/rows.
let matchBytes = intVal("FERN_MATCH_BYTES", 0) != 0

/// Measured M4-Pro DRAM read ceiling (rule 55): t = 3.97us + bytes/266.3GB/s.
let dramPeakGBs = 266.3
/// M4-Pro-class system level cache estimate. Used only as a printed label.
let slcEstimateBytes = 24 * 1024 * 1024

// MARK: - source extraction (same contract as nezuko_r98_ab_kernel_probe.swift)

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

func extractKernel(_ path: String, name: String, rows: Int) -> ExtractedKernel {
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
    let body = rewriteRowBound(src.text, rows: rows)
    let count = body.split(separator: "\n", omittingEmptySubsequences: false).count
    return ExtractedKernel(
        name: name, header: hdr.text, body: body, sourceLines: count)
}

/// Substitutes the KV row-loop bound and nothing else. Fails loudly rather than
/// silently timing an unmodified kernel if the declaration ever moves.
func rewriteRowBound(_ body: String, rows: Int) -> String {
    guard rows != 512 else { return body }
    let needle = "constexpr int N = 512;"
    let hits = body.components(separatedBy: needle).count - 1
    precondition(hits == 1, "expected exactly one `\(needle)`, found \(hits)")
    return body.replacingOccurrences(
        of: needle, with: "constexpr int N = \(rows);")
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

// MARK: - device

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
let cGQA = 8

let dRawQ = makeBF16(cHeads * cDim)
let dRawK = makeBF16(cKV * cDim)
let dRawV = makeBF16(cKV * cDim)
let dQW = makeBF16(cDim)
let dKW = makeBF16(cDim)
let dAttended = makeBF16(cHeads * cDim)
// One logical cache is cKV * cWindow * cDim elements (16 MiB at bf16).
// `cacheCopies` extends it so the defeat rotation has somewhere to go.
let dKCache = makeBF16(cKV * cWindow * cDim * cacheCopies)
let dVCache = makeBF16(cKV * cWindow * cDim * cacheCopies)
let dAngles = device.makeBuffer(length: cDim * 4, options: .storageModeShared)!
for i in 0..<cDim {
    dAngles.contents().bindMemory(to: Float.self, capacity: cDim)[i] = 0.5
}
let dParams = device.makeBuffer(length: 12, options: .storageModeShared)!
do {
    let p = dParams.contents().bindMemory(to: UInt32.self, capacity: 3)
    p[0] = 7
    p[1] = 512
    p[2] = UInt32(cWindow)
}
let dScale = device.makeBuffer(length: 4, options: .storageModeShared)!
dScale.contents().bindMemory(to: Float.self, capacity: 1)[0] = 0.088_388_35

/// Bytes of one kv-head's contiguous K (or V) window. Addressing stride is
/// always the full window; only `kvHeadReadBytes` follows `attnRows`.
let kvHeadBytes = cWindow * cDim * 2
/// Bytes of one kv-head the row loop actually reads at this row count.
func kvHeadReadBytes(_ rows: Int) -> Int { min(rows, cWindow) * cDim * 2 }

/// `kv_head = head0 / gqa` and `head0 = 2 * tgpig.x`, so a K-threadgroup
/// dispatch touches kv-heads `0 ..< ceil(2K/gqa)`.
func distinctKVHeads(_ k: Int) -> Int {
    min((2 * k + cGQA - 1) / cGQA, cKV)
}

/// Rotation stride is the whole K/V footprint of one dispatch, so consecutive
/// slots share no cache line. `FERN_STRIDE_KV` pins it across a K sweep.
func cacheSlotStride(_ k: Int) -> Int {
    max(strideKVOverride, distinctKVHeads(k)) * kvHeadBytes
}

/// Slots that actually fit the allocated cache buffer at this K. With
/// `FERN_MATCH_BYTES` the request scales as window/rows so a short-row point
/// streams the same distinct bytes per round as the full-window point.
func effectiveSlots(_ k: Int, _ rows: Int) -> Int {
    let stride = cacheSlotStride(k)
    guard stride > 0 else { return 1 }
    let room = (dKCache.length - stride) / stride + 1
    let want = matchBytes ? defeatSlots * cWindow / max(min(rows, cWindow), 1) : defeatSlots
    return max(1, min(want, room))
}

func bind(_ enc: MTLComputeCommandEncoder, k: Int, slot: Int) {
    let off = slot * cacheSlotStride(k)
    for (i, b) in [dRawQ, dRawK, dRawV, dQW, dKW, dAngles].enumerated() {
        enc.setBuffer(b, offset: 0, index: i)
    }
    enc.setBuffer(dKCache, offset: off, index: 6)
    enc.setBuffer(dVCache, offset: off, index: 7)
    enc.setBuffer(dParams, offset: 0, index: 8)
    enc.setBuffer(dScale, offset: 0, index: 9)
    enc.setBuffer(dAttended, offset: 0, index: 10)
}

/// Device bytes one dispatch of `k` threadgroups asks for.
func requestedBytesPerDispatch(_ k: Int, _ rows: Int) -> Int {
    let kv = distinctKVHeads(k)
    let cacheReads = 2 * kv * kvHeadReadBytes(rows)
    let rawQ = 2 * k * cDim * 2
    let rawKV = 2 * kv * cDim * 2
    let weights = 2 * cDim * 2
    let angles = cDim * 4
    let writes = 2 * k * cDim * 2 + 2 * kv * cDim * 2
    return cacheReads + rawQ + rawKV + weights + angles + writes
}

/// Distinct bytes one round of `reps` dispatches touches, honouring rotation.
func uniqueBytesPerRound(_ k: Int, reps: Int, _ rows: Int) -> Int {
    let slots = min(effectiveSlots(k, rows), reps)
    let perSlot = 2 * distinctKVHeads(k) * kvHeadReadBytes(rows)
    // Rotation only moves the two caches; every other binding is fixed.
    let fixed = requestedBytesPerDispatch(k, rows) - perSlot
    return slots * perSlot + fixed
}

// MARK: - pipelines

let baseArg = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : ""
precondition(!baseArg.isEmpty, "usage: fernattn <base-source> [cand-source]")
let candArg = CommandLine.arguments.count > 2 ? CommandLine.arguments[2] : baseArg
let isNull = CommandLine.arguments.count <= 2
let kernelName = strVal("FERN_KERNEL", "laguna_sliding_fused_attn_ring_v1")

func buildPipeline(_ k: ExtractedKernel) -> MTLComputePipelineState {
    let msl = preamble + k.header + "\n" + mlxSignature(k.name) + k.body + "\n}\n"
    let lib = try! device.makeLibrary(source: msl, options: nil)
    let fn = lib.makeFunction(name: "custom_kernel_\(k.name)")!
    return try! device.makeComputePipelineState(function: fn)
}

let arms = [("BASE", baseArg), (isNull ? "NULL(BASE)" : "CAND", candArg)]
    .map { label, path -> (String, String, ExtractedKernel, MTLComputePipelineState) in
        let k = extractKernel(path, name: kernelName, rows: attnRows)
        return (label, path, k, buildPipeline(k))
    }

/// One pipeline per entry of `FERN_ROWS_SWEEP`, all built from the base source
/// before any timing so compilation never lands inside a measured round.
let sweepPipes: [(rows: Int, pipe: MTLComputePipelineState)] = sweepRows.map {
    ($0, buildPipeline(extractKernel(baseArg, name: kernelName, rows: $0)))
}

print("=== device ===")
print("name                  \(device.name)")
print("architecture          \(device.architecture.name)")
print("gpu cores             \(cores)")
print("kernel                \(kernelName)")
print("attn rows N           \(attnRows)  (ring iters M = \(attnRows / 128))")
print("stride kvheads        \(strideKVOverride == 0 ? "auto" : String(strideKVOverride))")
print("rows sweep            \(sweepRows.isEmpty ? "off" : sweepRows.map(String.init).joined(separator: ","))")
print("match bytes           \(matchBytes ? "on (slots scale as 512/N)" : "off")")
print("mode                  \(isNull ? "NULL CONTROL (base vs itself)" : "A/B")")

print("\n=== pipeline properties (register/occupancy gate) ===")
print("  arm            srcLines   tgMemB   maxTotalThreads   execWidth   source")
for (label, path, k, pipe) in arms {
    print(
        String(
            format: "  %-12@   %7d   %6d   %15d   %9d   %@",
            label as NSString, k.sourceLines, pipe.staticThreadgroupMemoryLength,
            pipe.maxTotalThreadsPerThreadgroup, pipe.threadExecutionWidth,
            path as NSString))
}

// MARK: - timing

/// Serial dispatch type means the `reps` dispatches in one command buffer do
/// not overlap, so GPU busy time over reps is the per-call cost.
func perCallMicros(
    _ pipe: MTLComputePipelineState, k: Int, reps: Int, rows: Int = attnRows
) -> Double {
    let slots = effectiveSlots(k, rows)
    let cb = queue.makeCommandBuffer()!
    let enc = cb.makeComputeCommandEncoder()!
    enc.setComputePipelineState(pipe)
    if slots == 1 { bind(enc, k: k, slot: 0) }
    for i in 0..<reps {
        if slots > 1 { bind(enc, k: k, slot: i % slots) }
        enc.dispatchThreadgroups(
            MTLSize(width: k, height: 1, depth: 1),
            threadsPerThreadgroup: MTLSize(width: 1024, height: 1, depth: 1))
    }
    enc.endEncoding()
    cb.commit()
    cb.waitUntilCompleted()
    return (cb.gpuEndTime - cb.gpuStartTime) * 1e6 / Double(reps)
}

for (_, _, _, pipe) in arms { _ = perCallMicros(pipe, k: 32, reps: 40) }
for k in ladder { _ = perCallMicros(arms[0].3, k: k, reps: reps) }

// MARK: - regime block (P1.1 / P1.2)

print("\n=== memory regime (P1.1) ===")
print("  defeat slots          \(defeatSlots)\(defeatSlots == 1 ? "  (r98 resident binding)" : "")")
print("  cache copies          \(cacheCopies)")
print("  k_cache buffer        \(dKCache.length) B")
print("  dram_peak_GB_s        \(dramPeakGBs)  (measured, rule 55)")
print("  slc_estimate_B        \(slcEstimateBytes)  (M4-Pro-class, label only)")
print(
    "     K  TG/core   kvheads   slots   uniq_MiB   req_MiB/round   amplif   base_us   achieved_GB_s   pct_peak   slc_fit   regime"
)
for k in ladder {
    let uniq = uniqueBytesPerRound(k, reps: reps, attnRows)
    let req = requestedBytesPerDispatch(k, attnRows) * reps
    var t = Double.greatestFiniteMagnitude
    for _ in 0..<3 { t = min(t, perCallMicros(arms[0].3, k: k, reps: reps)) }
    let roundSeconds = t * Double(reps) * 1e-6
    let achieved = Double(req) / roundSeconds / 1e9
    let pctPeak = 100.0 * achieved / dramPeakGBs
    let regime: String
    if achieved > dramPeakGBs {
        regime = "CACHE_SERVED"
    } else if pctPeak >= 80.0 {
        regime = "SATURATED"
    } else if pctPeak >= 40.0 {
        regime = "PARTIAL"
    } else {
        regime = "UNSATURATED"
    }
    print(
        String(
            format:
                "  %4d   %6.2f   %7d   %5d   %8.2f   %13.2f   %6.1f   %7.2f   %13.1f   %8.1f   %7@   %@",
            k, Double(k) / Double(max(cores, 1)), distinctKVHeads(k),
            effectiveSlots(k, attnRows),
            Double(uniq) / 1048576.0, Double(req) / 1048576.0,
            Double(req) / Double(uniq), t, achieved, pctPeak,
            (uniq <= slcEstimateBytes ? "yes" : "no") as NSString, regime as NSString))
}

// MARK: - absolute cost ladder and the doubling ratio (E1)

print("\n=== absolute cost ladder, best of \(rounds) rounds of \(reps) dispatches (E1) ===")
print("phi(K) = t(2K)/t(K).  A threadgroup-doubling change pays only if phi < 2.")
print("t/K is the per-threadgroup cost: flat means work-limited, falling means")
print("the added threadgroups are absorbed by idle cores.")
print("     K  TG/core   base_us     t/K_us   phi(K)=t(2K)/t(K)")
var absolute: [Int: Double] = [:]
for k in ladder {
    var best = Double.greatestFiniteMagnitude
    for _ in 0..<rounds { best = min(best, perCallMicros(arms[0].3, k: k, reps: reps)) }
    absolute[k] = best
}
for k in ladder {
    let t = absolute[k]!
    let phi = absolute[2 * k].map { String(format: "%.4f", $0 / t) } ?? "-"
    print(
        String(
            format: "  %4d   %6.2f   %7.2f   %8.4f   %@",
            k, Double(k) / Double(max(cores, 1)), t, t / Double(k), phi as NSString))
}

// MARK: - paired A/B ladder

print("\n=== paired per-call cost, \(rounds) alternating rounds of \(reps) dispatches ===")
print("delta = second arm - base within a round, so drift cancels. neg = faster.")
print("     K  TG/core   base_min   cand_min    d_mean    d_sd   spread   t_paired        %")
for k in ladder {
    var baseMin = Double.greatestFiniteMagnitude
    var candMin = Double.greatestFiniteMagnitude
    var deltas: [Double] = []
    for r in 0..<rounds {
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
    print(
        String(
            format:
                "  %4d   %6.2f   %8.2f   %8.2f   %+7.3f   %5.3f   %6.2f   %+8.2f   %+7.3f",
            k, Double(k) / Double(max(cores, 1)), baseMin, candMin, mean, sd,
            deltas.max()! - deltas.min()!, t,
            100.0 * mean / (baseMin > 0 ? baseMin : 1)))
}

// MARK: - interleaved row sweep (R102-A rung 1)

/// Separate blocks drift against each other by up to ~14% on this host, which
/// is fatal for an intercept fit across N. Visiting every row point inside one
/// round in rotating order puts each N at every phase of the drift, so the
/// across-N differences the fit consumes are drift-free.
if !sweepPipes.isEmpty {
    for e in sweepPipes { _ = perCallMicros(e.pipe, k: 32, reps: 40, rows: e.rows) }
    print(
        "\n=== interleaved row sweep, \(rounds) rounds x \(sweepPipes.count) row points, "
            + "\(reps) dispatches ===")
    print("Round r visits point (j + r) mod n, so no N owns a fixed slot in the round.")
    print("Repeat an N in FERN_ROWS_SWEEP to get a within-round null on that N.")
    print("     K    idx      N    M   slots   min_us   med_us   mean_us   sd_us   spread")
    var machine: [String] = []
    for k in ladder {
        var samples = [[Double]](repeating: [], count: sweepPipes.count)
        for r in 0..<rounds {
            for j in 0..<sweepPipes.count {
                let idx = (j + r) % sweepPipes.count
                let e = sweepPipes[idx]
                samples[idx].append(perCallMicros(e.pipe, k: k, reps: reps, rows: e.rows))
            }
        }
        for (idx, e) in sweepPipes.enumerated() {
            let s = samples[idx].sorted()
            let n = Double(s.count)
            let mean = s.reduce(0, +) / n
            let sd =
                n > 1 ? (s.map { ($0 - mean) * ($0 - mean) }.reduce(0, +) / (n - 1)).squareRoot() : 0
            let med = s[s.count / 2]
            let slots = effectiveSlots(k, e.rows)
            print(
                String(
                    format: "  %4d   %4d   %5d   %2d   %5d   %7.3f   %7.3f   %8.3f   %6.3f   %6.3f",
                    k, idx, e.rows, e.rows / 128, slots, s[0], med, mean, sd, s[s.count - 1] - s[0]))
            machine.append(
                String(
                    format:
                        "SWEEP k=%d idx=%d N=%d M=%d slots=%d n=%d min=%.4f med=%.4f mean=%.4f sd=%.4f",
                    k, idx, e.rows, e.rows / 128, slots, s.count, s[0], med, mean, sd))
        }
    }
    print("\n=== machine-readable sweep ===")
    for line in machine { print(line) }
}
