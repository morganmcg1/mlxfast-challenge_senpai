// Research-only host harness (not part of the submission surface).
//
// Stage 0 of PR #682 (R109-B decode router hybrid selector). The advisor asked
// for the *occupancy* ceiling, not the barrier count, before any comparator
// network is written. This probe answers three questions in one process, one
// device, one queue:
//
//   1. Occupancy. What co-residency does 2048 B of static threadgroup memory
//      cost at 256 threads/threadgroup on this host, and what would 1536 B or
//      64 B buy back? Measured with the rendezvous test, not inferred.
//   2. Ceiling. What fraction of the router dispatch is stage 2 at all?
//      Arm B deletes stage 2 outright (wrong output, deliberately) so the
//      measured A-B gap is an upper bound no bit-exact rewrite can beat.
//      Arm C is a null kernel with the same buffers: the launch floor.
//   3. Feasibility. Arm D is the actual proposal -- simdgroup 0 alone merges
//      all 64 finalists out of `candidate_*`, so barrier #2 and the two
//      `xchg_*` planes disappear -- checked bit-for-bit against arm A.
//
// All four arms are compiled from the *shipped* source text sliced out of
// LagunaRuntimeModel.swift, so the base arm cannot drift from the scored code.
//
// Build and run:
//   xcrun swiftc -O research/nezuko_r109b_router_probe.swift -o /tmp/nezr109b \
//     && /tmp/nezr109b

import Foundation
import Metal

// MARK: - Extraction

let lrmPath =
    CommandLine.arguments.count > 1
    ? CommandLine.arguments[1] : "Sources/MLXFastModel/LagunaRuntimeModel.swift"
let lrmLines = try! String(contentsOfFile: lrmPath, encoding: .utf8)
    .split(separator: "\n", omittingEmptySubsequences: false).map(String.init)

/// Slices a `"""` block that opens on `openLine` and closes on the next line
/// whose trimmed text is exactly `"""`. Every literal this probe needs is
/// written at column 0 inside the enclosing declaration, so no dedent applies.
func sliceLiteral(openLine: Int) -> (text: String, close: Int) {
    var close = -1
    var i = openLine + 1
    while i < lrmLines.count {
        if lrmLines[i] == "\"\"\"" { close = i; break }
        i += 1
    }
    precondition(close >= 0, "unterminated literal opened at line \(openLine + 1)")
    return (lrmLines[(openLine + 1)..<close].joined(separator: "\n"), close)
}

func findLine(_ needle: String, from: Int = 0) -> Int {
    for i in from..<lrmLines.count where lrmLines[i].contains(needle) { return i }
    preconditionFailure("`\(needle)` not found in \(lrmPath)")
}

let headerText = sliceLiteral(
    openLine: findLine("private let lagunaDecodeRouterOrdinalHeader = \"\"\"")).text
let funcLine = findLine(
    "private func lagunaPrefillRouterTournamentOrdinalKernelSource(normalizing: Bool)")
// `let epilogue = normalizing ? """..."""  : """..."""` -- take the second one,
// the non-normalizing form the scored decode path selects.
let epilogueOpen = findLine(": \"\"\"", from: funcLine)
let epilogueText = sliceLiteral(openLine: epilogueOpen).text
let rawBody = sliceLiteral(openLine: findLine("return \"\"\"", from: epilogueOpen)).text

precondition(
    headerText.contains("laguna_router_ordinal_before")
        && epilogueText.contains("router_indices[row * 8 + lane] = my_index2;")
        && !epilogueText.contains("total")
        && rawBody.contains("\\(epilogue)"),
    "slicing did not recover the expected shipped text")

// MARK: - Arms, built by rewriting the shipped body text

let xchgDecls = """
    threadgroup uint xchg_ordinals[64];
    threadgroup uint xchg_indices[64];

    """
let stage2Open = "uint my_ordinal2 = 0u;"
let stage2Close = "\\(epilogue)"

func region(_ body: String, _ open: String, _ close: String) -> Range<String.Index> {
    precondition(
        body.ranges(of: open).count == 1 && body.ranges(of: close).count == 1,
        "ambiguous or missing stage-2 markers")
    return body.range(of: open)!.lowerBound..<body.range(of: close)!.lowerBound
}

/// The exact shipped cross-simdgroup exchange: two `xchg_*` stores, the second
/// `threadgroup_barrier`, and the sequence-64 first stage. Arm B deletes only
/// this, keeping the local sort and the stride 16..1 merge that arm D also
/// keeps, so arm B is an upper bound on what arm D can win.
let shippedExchange = """
    if (lane < 64) {
        xchg_ordinals[lane] = my_ordinal2;
        xchg_indices[lane] = my_index2;
    }
    threadgroup_barrier(mem_flags::mem_threadgroup);
    if (lane < 64) {
        uint partner = lane ^ 32u;
        uint other_ordinal = xchg_ordinals[partner];
        uint other_index = xchg_indices[partner];
        bool is_lower = (lane & 32u) == 0;
        bool other_before_my = laguna_router_ordinal_before(
            other_ordinal, other_index, my_ordinal2, my_index2);
        bool take_other = is_lower ? other_before_my : !other_before_my;
        if (take_other) {
            my_ordinal2 = other_ordinal;
            my_index2 = other_index;
        }

        for (uint stride = 16; stride > 0; stride >>= 1) {
    """
let excisedExchange = """
    if (lane < 64) {
        uint other_ordinal;
        uint other_index;
        bool is_lower;
        bool other_before_my;
        bool take_other;
        for (uint stride = 16; stride > 0; stride >>= 1) {
    """

/// The bit-exact candidate. Simdgroup 0 holds the original lane-`lane`
/// finalist in (a) and the original lane-`lane|32` finalist in (b), reading
/// both straight out of `candidate_*` after the *first* barrier. Every
/// comparator predicate below is evaluated with the original lane id, so the
/// same pairs are compared in the same order as the shipped network.
///
/// Exactness contract (`laguna_router_ordinal_before` in the header): this is a
/// pure selection network over (ordinal, index) pairs whose ties break toward
/// the smaller expert index. It performs no arithmetic on the payload, so
/// reproducing the comparator pairs and their order reproduces the same eight
/// winners and the same `original_scores[]` lookups bit for bit.
let candidateStage2 = """
uint my_ordinal2 = 0u;
uint my_index2 = 0u;
if (lane < 32) {
    uint a_ordinal = candidate_ordinals[lane];
    uint a_index = candidate_indices[lane];
    uint b_ordinal = candidate_ordinals[lane + 32u];
    uint b_index = candidate_indices[lane + 32u];

    for (uint sequence = 2; sequence <= 32; sequence <<= 1) {
        bool a_lower_wants_better = (lane & sequence) == 0;
        bool b_lower_wants_better = ((lane | 32u) & sequence) == 0;
        for (uint stride = sequence >> 1; stride > 0; stride >>= 1) {
            bool is_lower = (lane & stride) == 0;

            uint other_ordinal = simd_shuffle_xor(a_ordinal, ushort(stride));
            uint other_index = simd_shuffle_xor(a_index, ushort(stride));
            bool other_before_my = laguna_router_ordinal_before(
                other_ordinal, other_index, a_ordinal, a_index);
            bool take_other = (a_lower_wants_better == is_lower)
                ? other_before_my : !other_before_my;
            if (take_other) {
                a_ordinal = other_ordinal;
                a_index = other_index;
            }

            other_ordinal = simd_shuffle_xor(b_ordinal, ushort(stride));
            other_index = simd_shuffle_xor(b_index, ushort(stride));
            other_before_my = laguna_router_ordinal_before(
                other_ordinal, other_index, b_ordinal, b_index);
            take_other = (b_lower_wants_better == is_lower)
                ? other_before_my : !other_before_my;
            if (take_other) {
                b_ordinal = other_ordinal;
                b_index = other_index;
            }
        }
    }

    // Sequence-64 first stage. The shipped kernel gives lanes 0..31
    // `is_lower == true`, so the lower half unconditionally takes the better of
    // the two partners; the discarded upper half never reaches the epilogue.
    if (laguna_router_ordinal_before(b_ordinal, b_index, a_ordinal, a_index)) {
        a_ordinal = b_ordinal;
        a_index = b_index;
    }

    for (uint stride = 16; stride > 0; stride >>= 1) {
        uint other_ordinal = simd_shuffle_xor(a_ordinal, ushort(stride));
        uint other_index = simd_shuffle_xor(a_index, ushort(stride));
        bool is_lower = (lane & stride) == 0;
        bool other_before_my = laguna_router_ordinal_before(
            other_ordinal, other_index, a_ordinal, a_index);
        bool take_other = is_lower ? other_before_my : !other_before_my;
        if (take_other) {
            a_ordinal = other_ordinal;
            a_index = other_index;
        }
    }

    my_ordinal2 = a_ordinal;
    my_index2 = a_index;
}

"""

func assemble(_ body: String) -> String {
    let full = body.replacingOccurrences(of: stage2Close, with: epilogueText)
    precondition(!full.contains("\\("), "unsubstituted interpolation left in body")
    return """
        #include <metal_stdlib>
        #include <metal_simdgroup>
        using namespace metal;
        typedef bfloat bfloat16_t;
        #ifndef METAL_FUNC
        #define METAL_FUNC inline __attribute__((__always_inline__))
        #endif

        \(headerText)

        [[kernel]] void custom_kernel_router(
          const device bfloat16_t* logits [[buffer(0)]],
          const device float* correction_bias [[buffer(1)]],
          device uint* router_indices [[buffer(2)]],
          device float* router_scores [[buffer(3)]],
          uint3 thread_position_in_threadgroup [[thread_position_in_threadgroup]],
          uint3 threadgroup_position_in_grid [[threadgroup_position_in_grid]]) {
        \(full)
        }
        """
}

precondition(
    rawBody.ranges(of: shippedExchange).count == 1
        && rawBody.ranges(of: xchgDecls).count == 1,
    "shipped exchange or xchg declarations not found verbatim")

var bodyB = rawBody.replacingOccurrences(of: shippedExchange, with: excisedExchange)
bodyB = bodyB.replacingOccurrences(of: xchgDecls, with: "")

var bodyD = rawBody
bodyD.replaceSubrange(region(bodyD, stage2Open, stage2Close), with: candidateStage2)
bodyD = bodyD.replacingOccurrences(of: xchgDecls, with: "")

let nullBody = """
uint lane = thread_position_in_threadgroup.x;
uint row = threadgroup_position_in_grid.y;
float score = float(logits[row * 256 + lane]) + correction_bias[lane];
if (lane < 8) {
    router_indices[row * 8 + lane] = lane;
    router_scores[row * 8 + lane] = score;
}
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

let cores = gpuCoreCount()
print("=== device ===")
print("name                          \(device.name)")
print("architecture                  \(device.architecture.name)")
print("gpu cores                     \(cores)")
print("maxThreadgroupMemoryLength    \(device.maxThreadgroupMemoryLength) B")
print("source                        \(lrmPath)")

let armNames = [
    "A shipped (base)", "B stage2 excised (ceiling)", "C null (launch floor)",
    "D single-simdgroup merge",
]
let armBodies = [rawBody, bodyB, nullBody, bodyD]
var pipes: [MTLComputePipelineState] = []

print("\n=== arms ===")
for (name, body) in zip(armNames, armBodies) {
    let msl = assemble(body)
    let lib = try! device.makeLibrary(source: msl, options: nil)
    let pipe = try! device.makeComputePipelineState(
        function: lib.makeFunction(name: "custom_kernel_router")!)
    pipes.append(pipe)
    print(name)
    print("  body lines                     "
        + "\(body.split(separator: "\n", omittingEmptySubsequences: false).count)")
    print("  staticThreadgroupMemoryLength  \(pipe.staticThreadgroupMemoryLength) B")
    print("  maxTotalThreadsPerThreadgroup  \(pipe.maxTotalThreadsPerThreadgroup)")
    print("  threadExecutionWidth           \(pipe.threadExecutionWidth)")
}

// MARK: - Buffers

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

let maxRows = 512
let dLogits = device.makeBuffer(length: maxRows * 256 * 2, options: .storageModeShared)!
let dBias = device.makeBuffer(length: 256 * 4, options: .storageModeShared)!
let outIdx = (0..<4).map { _ in
    device.makeBuffer(length: maxRows * 8 * 4, options: .storageModeShared)!
}
let outScore = (0..<4).map { _ in
    device.makeBuffer(length: maxRows * 8 * 4, options: .storageModeShared)!
}

/// `tieEvery > 0` forces exact ordinal ties between neighbouring experts, which
/// is the only place the `laguna_router_ordinal_before` index tie-break can be
/// observed. A rewrite that reorders comparators fails here and nowhere else.
func fillLogits(tieEvery: Int) {
    let p = dLogits.contents().bindMemory(to: UInt16.self, capacity: maxRows * 256)
    for r in 0..<maxRows {
        for e in 0..<256 {
            let v: Float = tieEvery > 0
                ? Float(((e / tieEvery) + r) % 7) * 0.25 - 0.75 : nextUnit()
            p[r * 256 + e] = bf16(v)
        }
    }
    let b = dBias.contents().bindMemory(to: Float.self, capacity: 256)
    for e in 0..<256 { b[e] = tieEvery > 0 ? 0.0 : nextUnit() * 0.05 }
}

func bind(_ enc: MTLComputeCommandEncoder, arm: Int) {
    enc.setBuffer(dLogits, offset: 0, index: 0)
    enc.setBuffer(dBias, offset: 0, index: 1)
    enc.setBuffer(outIdx[arm], offset: 0, index: 2)
    enc.setBuffer(outScore[arm], offset: 0, index: 3)
}

func run(_ arm: Int, rows: Int) {
    let cb = queue.makeCommandBuffer()!
    let enc = cb.makeComputeCommandEncoder()!
    enc.setComputePipelineState(pipes[arm])
    bind(enc, arm: arm)
    enc.dispatchThreadgroups(
        MTLSize(width: 1, height: rows, depth: 1),
        threadsPerThreadgroup: MTLSize(width: 256, height: 1, depth: 1))
    enc.endEncoding()
    cb.commit()
    cb.waitUntilCompleted()
}

// MARK: - Bit-exactness of arm D against arm A

print("\n=== bit-exactness: arm D vs arm A (all 8 slots, indices and score bits) ===")
print("  ties      rows   slots   index-equal   score-bit-equal")
var dExact = true
for (ties, rows) in [(0, 1), (0, 512), (2, 512), (4, 512), (8, 512), (64, 512)] {
    fillLogits(tieEvery: ties)
    for arm in [0, 3] {
        memset(outIdx[arm].contents(), 0xFF, maxRows * 8 * 4)
        memset(outScore[arm].contents(), 0xFF, maxRows * 8 * 4)
        run(arm, rows: rows)
    }
    let slots = rows * 8
    let ai = outIdx[0].contents().bindMemory(to: UInt32.self, capacity: slots)
    let di = outIdx[3].contents().bindMemory(to: UInt32.self, capacity: slots)
    let asv = outScore[0].contents().bindMemory(to: UInt32.self, capacity: slots)
    let dsv = outScore[3].contents().bindMemory(to: UInt32.self, capacity: slots)
    var idxEq = 0
    var scoreEq = 0
    for i in 0..<slots {
        if ai[i] == di[i] { idxEq += 1 }
        if asv[i] == dsv[i] { scoreEq += 1 }
    }
    if idxEq != slots || scoreEq != slots { dExact = false }
    print(String(
        format: "  %4d   %7d   %5d   %11@   %15@", ties, rows, slots,
        (idxEq == slots ? "yes" : "NO \(idxEq)") as NSString,
        (scoreEq == slots ? "yes" : "NO \(scoreEq)") as NSString))
}
print(dExact
    ? "verdict: arm D reproduces every checked index and score bit of arm A"
    : "verdict: arm D IS NOT BIT-EXACT -- not a candidate")

// MARK: - Timing

/// One compute encoder's default serial dispatch type means the `reps`
/// dispatches do not overlap, so GPU busy time over reps is the per-call cost.
func perCallMicros(_ arm: Int, rows: Int, reps: Int, tries: Int = 3) -> Double {
    var best = Double.greatestFiniteMagnitude
    for _ in 0..<tries {
        let cb = queue.makeCommandBuffer()!
        let enc = cb.makeComputeCommandEncoder()!
        enc.setComputePipelineState(pipes[arm])
        bind(enc, arm: arm)
        for _ in 0..<reps {
            enc.dispatchThreadgroups(
                MTLSize(width: 1, height: rows, depth: 1),
                threadsPerThreadgroup: MTLSize(width: 256, height: 1, depth: 1))
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

fillLogits(tieEvery: 0)
for a in 0..<4 { _ = perCallMicros(a, rows: 1, reps: 50) }

let pairs = CommandLine.arguments
    .first(where: { $0.hasPrefix("pairs=") }).map { Int($0.dropFirst(6))! } ?? 8

// Decode is `rows: 1` (LagunaRuntimeModel.swift:9606) -- one 256-thread
// threadgroup per layer per step. rows=512 is the prefill dispatch.
print("\n=== ABBA matched latency (us/call, best-of-3 command buffers) ===")
var perCall: [Int: [Int: Double]] = [:]
for rows in [1, 512] {
    print("  rows=\(rows)")
    print("     pair      A       B       C       D    B/A     D/A")
    var acc: [Int: [Double]] = [0: [], 1: [], 2: [], 3: []]
    for p in 0..<pairs {
        var slot: [Int: [Double]] = [0: [], 1: [], 2: [], 3: []]
        for arm in [0, 1, 2, 3, 3, 2, 1, 0] {
            slot[arm]!.append(perCallMicros(arm, rows: rows, reps: rows == 1 ? 200 : 40))
        }
        for a in 0..<4 { acc[a]!.append(slot[a]!.reduce(0, +) / 2) }
        let v = (0..<4).map { acc[$0]!.last! }
        print(String(
            format: "     %4d %6.3f  %6.3f  %6.3f  %6.3f  %5.3f   %5.3f", p + 1,
            v[0], v[1], v[2], v[3], v[1] / v[0], v[3] / v[0]))
    }
    let m = (0..<4).map { median(acc[$0]!) }
    perCall[rows] = [0: m[0], 1: m[1], 2: m[2], 3: m[3]]
    print(String(
        format: "   median %6.3f  %6.3f  %6.3f  %6.3f  %5.3f   %5.3f",
        m[0], m[1], m[2], m[3], m[1] / m[0], m[3] / m[0]))
    let rat = zip(acc[3]!, acc[0]!).map { $0 / $1 }
    let mean = rat.reduce(0, +) / Double(rat.count)
    let sd = (rat.map { ($0 - mean) * ($0 - mean) }.reduce(0, +)
        / Double(max(rat.count - 1, 1))).squareRoot()
    print(String(
        format: "   D/A mean %.4f +- %.4f sem  -> %+.2f%%", mean,
        sd / Double(rat.count).squareRoot(), (mean - 1) * 100))
}

// MARK: - Score arithmetic

// Steady-step elasticity from the campaign's own paired receipts: a decode-step
// saving of dT on a step of T seconds moves the weighted score by
// 0.75 * (1 - sigma) * dT / T, where sigma is the non-steady share of the timed
// window (about 15% on the ranked M5, 33.6% on an M4 --local-iterate).
let stepUs = 13_890.0
let layers = 40.0
print("\n=== stage-2 ceiling in score terms ===")
print("decode step (paired baseline) \(stepUs) us over \(Int(layers)) layers")
for (label, arm) in [("B stage2 excised", 1), ("D bit-exact candidate", 3)] {
    let d = perCall[1]![0]! - perCall[1]![arm]!
    let perStep = d * layers
    let frac = perStep / stepUs
    print(String(
        format: "  %-22@ %+.4f us/call  %+.3f us/step  %+.4f%% of step"
            + "  -> %+.4f%% score (M5 sigma=0.15)",
        label as NSString, d, perStep, frac * 100, frac * 0.75 * 0.85 * 100))
}
print(String(
    format: "  whole router dispatch  %.4f us/call (A) vs %.4f us/call (C null)"
        + "  -> router is %.4f%% of the step",
    perCall[1]![0]!, perCall[1]![2]!,
    (perCall[1]![0]! - perCall[1]![2]!) * layers / stepUs * 100))

// MARK: - Occupancy: rendezvous residency vs static threadgroup memory

let timeoutSpins: UInt32 = 500_000
let okSlots = 1024
let counterBuf = device.makeBuffer(length: 4, options: .storageModeShared)!
let okBuf = device.makeBuffer(length: okSlots * 4, options: .storageModeShared)!
let cfgBuf = device.makeBuffer(length: 8, options: .storageModeShared)!

func rendezvous(_ pipe: MTLComputePipelineState, k: Int, threads: Int)
    -> (pass: Bool, passing: Int, ms: Double)
{
    counterBuf.contents().bindMemory(to: UInt32.self, capacity: 1)[0] = 0
    let ok = okBuf.contents().bindMemory(to: UInt32.self, capacity: okSlots)
    for i in 0..<okSlots { ok[i] = 0 }
    let cfg = cfgBuf.contents().bindMemory(to: UInt32.self, capacity: 2)
    cfg[0] = UInt32(k)
    cfg[1] = timeoutSpins
    let cb = queue.makeCommandBuffer()!
    let enc = cb.makeComputeCommandEncoder()!
    enc.setComputePipelineState(pipe)
    enc.setBuffer(counterBuf, offset: 0, index: 0)
    enc.setBuffer(okBuf, offset: 0, index: 1)
    enc.setBuffer(cfgBuf, offset: 0, index: 2)
    enc.dispatchThreadgroups(
        MTLSize(width: k, height: 1, depth: 1),
        threadsPerThreadgroup: MTLSize(width: threads, height: 1, depth: 1))
    enc.endEncoding()
    let t0 = Date()
    cb.commit()
    cb.waitUntilCompleted()
    let ms = Date().timeIntervalSince(t0) * 1000.0
    var passing = 0
    for i in 0..<k where ok[i] & 3 == 3 { passing += 1 }
    return (passing == k, passing, ms)
}

func maxResident(_ pipe: MTLComputePipelineState, threads: Int, kCap: Int)
    -> (k: Int, capped: Bool)
{
    func passes(_ k: Int) -> Bool { rendezvous(pipe, k: k, threads: threads).pass }
    guard passes(1) else { return (0, false) }
    if passes(kCap) { return (kCap, true) }
    var lo = 1
    var hi = kCap
    while hi - lo > 1 {
        let mid = (lo + hi) / 2
        if passes(mid) { lo = mid } else { hi = mid }
    }
    return (lo, false)
}

/// `flag` is written by the leader and read by a *different* thread after the
/// barrier, so neither the barrier nor the threadgroup allocation can be
/// elided, and the device store is issued by a non-leader thread -- proof that
/// thread was still resident while the leader spun.
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

print("\n=== occupancy: co-resident threadgroups vs static threadgroup memory ===")
print("256 threads/threadgroup, the shipped router geometry. A trailing `+`")
print("means residency is at least the search cap.")
print("  bytes    maxK   TG/core   sg/core")
let kCap = min(okSlots, max(4 * max(cores, 1) * 4, 64))
// 2048 B is the shipped router footprint; 1536 B is arm D (the two xchg planes
// gone); 512 B and 64 B are what a hypothetical scratch-free rewrite would buy.
for bytes in [2048, 1536, 512, 64, 16] {
    let src = synthSource(bytes: bytes, threads: 256)
    let lib = try! device.makeLibrary(source: src, options: nil)
    let pipe = try! device.makeComputePipelineState(
        function: lib.makeFunction(name: "rendez")!)
    let r = maxResident(pipe, threads: 256, kCap: kCap)
    let perCore = cores > 0 ? Double(r.k) / Double(cores) : 0
    print(String(
        format: "  %5d   %4d%@   %7.2f   %7.1f", bytes, r.k, r.capped ? "+" : " ",
        perCore, perCore * 8))
}
print("Decode dispatches rows=1, i.e. K=1: one threadgroup per layer per step,")
print("so co-residency cannot be the binding term on the scored decode path.")

exit(dExact ? 0 : 1)
