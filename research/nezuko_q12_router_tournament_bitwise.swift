// Research-only (not part of the submission surface).
//
// PR #441 Stage 2 -- decode router block tournament bit-exactness.
//
// H: the two-phase active-64 block tournament selects exactly the same eight
// expert indices and emits bit-identical scores as the shipped full-256
// bitonic ordinal network, for every one of the four decode arms
// (normalizing x score-table).
//
// Control  A -- verbatim transcription of
//               `lagunaDecodeRouterOrdinalKernelSource` (the shipped default
//               decode arm, LagunaRuntimeModel.swift:8818-8909).
// Candidate B -- verbatim transcription of
//               `lagunaDecodeRouterTournamentOrdinalKernelSource` (this PR,
//               LagunaRuntimeModel.swift:8994-9119).
// Fault Bd -- B with block 7's eighth candidate replaced by the worst ordinal.
//             REQUIRED: proves the comparator can fail (standing rule 16).
// Fault Ba -- B with the alternating Batcher extraction direction forced to
//             ascending for every block. REQUIRED: second live fault.
//
// Both generator functions below are byte-identical copies of the shipped Swift
// generators; `research/nezuko_q12_router_tournament_check.sh` diffs them
// against `Sources/MLXFastModel/LagunaRuntimeModel.swift` so MSL drift cannot
// go unnoticed.
//
// Logits reach the shipped kernels as bf16 or fp32 and are consumed as
// `float(logits[lane])`. bf16 widening to float is exact, so this harness keeps
// one fp32 buffer and, for the bf16 arm, rounds the host values to bf16
// (round-to-nearest-even) before upload. That compares the same program on the
// same values.
//
// MLX JIT-compiles `metalKernel` sources with fast math DISABLED
// (Vendor/mlx-swift/.../backend/metal/device.cpp:631); this harness matches.
//
// Build/run:
//   swiftc -O research/nezuko_q12_router_tournament_bitwise.swift \
//     -o /tmp/nezuko_q12_bitwise -framework Metal -framework Foundation
//   /tmp/nezuko_q12_bitwise [randomRows]

import Foundation
import Metal

// MARK: - Verbatim copy: shipped full-256 decode ordinal arm

private func lagunaDecodeRouterOrdinalKernelSource(
    normalizing: Bool, scoreTable: Bool = false
) -> String {
    let scoreStorage =
        scoreTable
        ? "threadgroup float original_scores[256];"
        : ""
    let scoreStore =
        scoreTable
        ? "original_scores[lane] = score;"
        : ""
    let winnerScore =
        scoreTable
        ? """
    my_score = original_scores[my_index];
"""
        : """
    float winner_x = float(logits[my_index]);
    float winner_y = 1.0f / (1.0f + metal::exp(metal::abs(winner_x)));
    my_score = winner_x < 0.0f ? winner_y : 1.0f - winner_y;
"""
    let epilogue =
        normalizing
        ? """
float my_score = 0.0f;
if (lane < 8) {
\(winnerScore)
}
float total = 0.0f;
for (uint i = 0; i < 8; ++i) {
    total = simd_shuffle(my_score, ushort(i)) + total;
}
if (lane < 8) {
    router_indices[lane] = my_index;
    router_scores[lane] = my_score / total;
}
"""
        : """
if (lane < 8) {
    float my_score = 0.0f;
\(winnerScore)
    router_indices[lane] = my_index;
    router_scores[lane] = my_score;
}
"""
    return """
uint lane = thread_position_in_threadgroup.x;

threadgroup uint xchg_ordinals[256];
threadgroup uint xchg_indices[256];
\(scoreStorage)

float x = float(logits[lane]);
float y = 1.0f / (1.0f + metal::exp(metal::abs(x)));
float score = x < 0.0f ? y : 1.0f - y;
\(scoreStore)
float key = -(score + float(correction_bias[lane]));
uint my_ordinal = laguna_router_key_ordinal(key);
uint my_index = lane;

for (uint sequence = 2; sequence <= 256; sequence <<= 1) {
    for (uint stride = sequence >> 1; stride > 0; stride >>= 1) {
        uint other_ordinal;
        uint other_index;
        if (stride < 32) {
            other_ordinal = simd_shuffle_xor(my_ordinal, ushort(stride));
            other_index = simd_shuffle_xor(my_index, ushort(stride));
        } else {
            xchg_ordinals[lane] = my_ordinal;
            xchg_indices[lane] = my_index;
            threadgroup_barrier(mem_flags::mem_threadgroup);
            uint partner = lane ^ stride;
            other_ordinal = xchg_ordinals[partner];
            other_index = xchg_indices[partner];
            threadgroup_barrier(mem_flags::mem_threadgroup);
        }

        bool is_lower = (lane & stride) == 0;
        bool lower_wants_better = (lane & sequence) == 0;
        bool want_better = lower_wants_better == is_lower;
        bool other_before_my = laguna_router_ordinal_before(
            other_ordinal, other_index, my_ordinal, my_index);
        bool take_other = want_better ? other_before_my : !other_before_my;
        if (take_other) {
            my_ordinal = other_ordinal;
            my_index = other_index;
        }
    }
}

\(epilogue)
"""
}

private let lagunaDecodeRouterOrdinalHeader = """
METAL_FUNC uint laguna_router_key_ordinal(float key) {
    uint bits = as_type<uint>(key);
    uint magnitude = bits & 0x7FFFFFFFu;
    if (magnitude > 0x7F800000u) {
        return 0xFFFFFFFFu;
    }
    if (magnitude == 0u) {
        return 0x80000000u;
    }
    return (bits & 0x80000000u) != 0u ? ~bits : (bits ^ 0x80000000u);
}

METAL_FUNC bool laguna_router_ordinal_before(
    uint a, uint a_index, uint b, uint b_index) {
    if (a < b) {
        return true;
    }
    if (b < a) {
        return false;
    }
    return a_index < b_index;
}
"""

// MARK: - Verbatim copy: candidate tournament arm

private func lagunaDecodeRouterTournamentOrdinalKernelSource(
    normalizing: Bool, scoreTable: Bool = false
) -> String {
    let scoreStorage =
        scoreTable
        ? "threadgroup float original_scores[256];"
        : ""
    let scoreStore =
        scoreTable
        ? "original_scores[lane] = score;"
        : ""
    let winnerScore =
        scoreTable
        ? """
    my_score = original_scores[my_index2];
"""
        : """
    float winner_x = float(logits[my_index2]);
    float winner_y = 1.0f / (1.0f + metal::exp(metal::abs(winner_x)));
    my_score = winner_x < 0.0f ? winner_y : 1.0f - winner_y;
"""
    let epilogue =
        normalizing
        ? """
float my_score = 0.0f;
if (lane < 8) {
\(winnerScore)
}
float total = 0.0f;
for (uint i = 0; i < 8; ++i) {
    total = simd_shuffle(my_score, ushort(i)) + total;
}
if (lane < 8) {
    router_indices[lane] = my_index2;
    router_scores[lane] = my_score / total;
}
"""
        : """
if (lane < 8) {
    float my_score = 0.0f;
\(winnerScore)
    router_indices[lane] = my_index2;
    router_scores[lane] = my_score;
}
"""
    return """
uint lane = thread_position_in_threadgroup.x;

threadgroup uint xchg_ordinals[256];
threadgroup uint xchg_indices[256];
threadgroup uint candidate_ordinals[64];
threadgroup uint candidate_indices[64];
\(scoreStorage)

float x = float(logits[lane]);
float y = 1.0f / (1.0f + metal::exp(metal::abs(x)));
float score = x < 0.0f ? y : 1.0f - y;
\(scoreStore)
float key = -(score + float(correction_bias[lane]));
uint my_ordinal = laguna_router_key_ordinal(key);
uint my_index = lane;

for (uint sequence = 2; sequence <= 32; sequence <<= 1) {
    for (uint stride = sequence >> 1; stride > 0; stride >>= 1) {
        uint other_ordinal = simd_shuffle_xor(my_ordinal, ushort(stride));
        uint other_index = simd_shuffle_xor(my_index, ushort(stride));

        bool is_lower = (lane & stride) == 0;
        bool lower_wants_better = (lane & sequence) == 0;
        bool want_better = lower_wants_better == is_lower;
        bool other_before_my = laguna_router_ordinal_before(
            other_ordinal, other_index, my_ordinal, my_index);
        bool take_other = want_better ? other_before_my : !other_before_my;
        if (take_other) {
            my_ordinal = other_ordinal;
            my_index = other_index;
        }
    }
}

uint block = lane >> 5;
uint within_block = lane & 31;
bool block_ascending = (block & 1) == 0;
uint rank_in_block = block_ascending ? within_block : (31 - within_block);
bool is_local_top8 = block_ascending ? (within_block < 8) : (within_block >= 24);
if (is_local_top8) {
    candidate_ordinals[block * 8 + rank_in_block] = my_ordinal;
    candidate_indices[block * 8 + rank_in_block] = my_index;
}
threadgroup_barrier(mem_flags::mem_threadgroup);

uint my_ordinal2 = candidate_ordinals[lane & 63];
uint my_index2 = candidate_indices[lane & 63];
for (uint sequence = 2; sequence <= 64; sequence <<= 1) {
    for (uint stride = sequence >> 1; stride > 0; stride >>= 1) {
        uint other_ordinal;
        uint other_index;
        if (stride < 32) {
            other_ordinal = simd_shuffle_xor(my_ordinal2, ushort(stride));
            other_index = simd_shuffle_xor(my_index2, ushort(stride));
        } else {
            xchg_ordinals[lane] = my_ordinal2;
            xchg_indices[lane] = my_index2;
            threadgroup_barrier(mem_flags::mem_threadgroup);
            uint partner = lane ^ stride;
            other_ordinal = xchg_ordinals[partner];
            other_index = xchg_indices[partner];
            threadgroup_barrier(mem_flags::mem_threadgroup);
        }

        bool is_lower = (lane & stride) == 0;
        bool lower_wants_better = (lane & sequence) == 0;
        bool want_better = lower_wants_better == is_lower;
        bool other_before_my = laguna_router_ordinal_before(
            other_ordinal, other_index, my_ordinal2, my_index2);
        bool take_other = want_better ? other_before_my : !other_before_my;
        if (take_other) {
            my_ordinal2 = other_ordinal;
            my_index2 = other_index;
        }
    }
}

\(epilogue)
"""
}

// MARK: - Fault injection

enum Fault: String {
    case none
    /// Block 7 loses its eighth-best candidate: a value perturbation of one
    /// candidate-window slot, so an element that belongs in the global top 8
    /// can no longer be recovered.
    case dropEighth = "drop8"
    /// Every block extracts as if ascending, so odd blocks publish their eight
    /// worst entries instead of their eight best.
    case flatDirection = "flatdir"
}

func applyFault(_ body: String, _ fault: Fault) -> String {
    switch fault {
    case .none:
        return body
    case .dropEighth:
        return body.replacingOccurrences(
            of: "    candidate_ordinals[block * 8 + rank_in_block] = my_ordinal;",
            with: """
    uint published_ordinal = my_ordinal;
    if (block == 7 && rank_in_block == 7) { published_ordinal = 0xFFFFFFFFu; }
    candidate_ordinals[block * 8 + rank_in_block] = published_ordinal;
""")
    case .flatDirection:
        return body.replacingOccurrences(
            of: "bool block_ascending = (block & 1) == 0;",
            with: "bool block_ascending = true;")
    }
}

// MARK: - Wrapper

func wrap(name: String, body: String) -> String {
    return """
kernel void \(name)(
    device const float* logits_all [[buffer(0)]],
    device const float* bias_all [[buffer(1)]],
    device uint* indices_all [[buffer(2)]],
    device float* scores_all [[buffer(3)]],
    uint3 threadgroup_position_in_grid [[threadgroup_position_in_grid]],
    uint3 thread_position_in_threadgroup [[thread_position_in_threadgroup]])
{
    uint row = threadgroup_position_in_grid.x;
    device const float* logits = logits_all + row * 256;
    device const float* correction_bias = bias_all + row * 256;
    device uint* router_indices = indices_all + row * 8;
    device float* router_scores = scores_all + row * 8;
\(body)
}
"""
}

struct Arm {
    let name: String
    let normalizing: Bool
    let scoreTable: Bool
    let tournament: Bool
    let fault: Fault
}

var arms: [Arm] = []
for normalizing in [false, true] {
    for scoreTable in [false, true] {
        let suffix = "\(normalizing ? "norm" : "plain")_\(scoreTable ? "table" : "recompute")"
        arms.append(
            Arm(
                name: "full256_\(suffix)", normalizing: normalizing, scoreTable: scoreTable,
                tournament: false, fault: .none))
        arms.append(
            Arm(
                name: "tourn_\(suffix)", normalizing: normalizing, scoreTable: scoreTable,
                tournament: true, fault: .none))
    }
}
// Fault arms sit on the production default (normalizing + score table).
arms.append(
    Arm(
        name: "tourn_fault_drop8", normalizing: true, scoreTable: true, tournament: true,
        fault: .dropEighth))
arms.append(
    Arm(
        name: "tourn_fault_flatdir", normalizing: true, scoreTable: true, tournament: true,
        fault: .flatDirection))

var metalSource = """
#include <metal_stdlib>
using namespace metal;
#define METAL_FUNC inline

\(lagunaDecodeRouterOrdinalHeader)

"""
for arm in arms {
    let body =
        arm.tournament
        ? lagunaDecodeRouterTournamentOrdinalKernelSource(
            normalizing: arm.normalizing, scoreTable: arm.scoreTable)
        : lagunaDecodeRouterOrdinalKernelSource(
            normalizing: arm.normalizing, scoreTable: arm.scoreTable)
    let faulted = applyFault(body, arm.fault)
    if arm.fault != .none && faulted == body {
        print("FATAL: fault \(arm.fault.rawValue) did not apply to \(arm.name)")
        exit(2)
    }
    metalSource += wrap(name: arm.name, body: faulted) + "\n\n"
}

// MARK: - Row construction

func bf16Round(_ v: Float) -> Float {
    let bits = v.bitPattern
    if (bits & 0x7F80_0000) == 0x7F80_0000 { return v }  // inf/nan pass through
    let lsb = (bits >> 16) & 1
    let rounded = (bits + 0x7FFF + lsb) & 0xFFFF_0000
    return Float(bitPattern: rounded)
}

struct RowClass {
    let name: String
    var logits: [Float] = []
    var bias: [Float] = []
    var rows: Int = 0

    mutating func add(_ l: [Float], _ b: [Float]) {
        precondition(l.count == 256 && b.count == 256)
        logits += l
        bias += b
        rows += 1
    }
}

var seed: UInt64 = 0x9E37_79B9_7F4A_7C15
func nextUniform(_ lo: Float, _ hi: Float) -> Float {
    seed = seed &* 6_364_136_223_846_793_005 &+ 1_442_695_040_888_963_407
    let x = Float(Double(seed >> 11) / Double(1 << 53))
    return lo + (hi - lo) * x
}

let randomRows = CommandLine.arguments.count > 1 ? Int(CommandLine.arguments[1]) ?? 4096 : 4096
var classes: [RowClass] = []

// 1. Smooth random rows.
do {
    var c = RowClass(name: "random_smooth")
    for _ in 0..<randomRows {
        c.add(
            (0..<256).map { _ in nextUniform(-8, 8) },
            (0..<256).map { _ in nextUniform(-0.15, 0.15) })
    }
    classes.append(c)
}

// 2. All-equal rows: every key ties, so the index tie break alone decides.
do {
    var c = RowClass(name: "all_equal")
    for v in [Float(0.0), 1.5, -3.25, 12.0] {
        c.add([Float](repeating: v, count: 256), [Float](repeating: 0.125, count: 256))
    }
    classes.append(c)
}

// 3. Few distinct values: heavy exact ties across distinct indices.
do {
    var c = RowClass(name: "heavy_ties")
    for distinct in [2, 3, 4, 8] {
        let pool = (0..<distinct).map { Float($0) * 0.5 - 1.0 }
        var l = [Float](repeating: 0, count: 256)
        for i in 0..<256 { l[i] = pool[Int(nextUniform(0, Float(distinct))) % distinct] }
        c.add(l, [Float](repeating: 0.0, count: 256))
    }
    // Deliberate near-tie: the top nine keys differ only in the last mantissa bit.
    var l = [Float](repeating: -20.0, count: 256)
    var b = [Float](repeating: 0.0, count: 256)
    for i in 0..<9 {
        l[(i * 29) % 256] = 1.0
        b[(i * 29) % 256] = Float(bitPattern: Float(0.25).bitPattern + UInt32(i % 2))
    }
    c.add(l, b)
    classes.append(c)
}

// 4. NaN, inf, signed zero.
do {
    var c = RowClass(name: "nan_inf_zero")
    var l = (0..<256).map { _ in nextUniform(-4, 4) }
    var b = [Float](repeating: 0.0, count: 256)
    for i in stride(from: 0, to: 256, by: 17) { l[i] = Float.nan }
    c.add(l, b)

    l = (0..<256).map { _ in nextUniform(-4, 4) }
    for i in stride(from: 3, to: 256, by: 23) { l[i] = .infinity }
    for i in stride(from: 11, to: 256, by: 29) { l[i] = -.infinity }
    c.add(l, b)

    // Bias NaN also poisons the key.
    l = (0..<256).map { _ in nextUniform(-4, 4) }
    b = [Float](repeating: 0.0, count: 256)
    for i in stride(from: 5, to: 256, by: 31) { b[i] = Float.nan }
    c.add(l, b)

    // Keys that canonicalize to zero: sigmoid underflows to +0 and the bias is
    // signed zero, so `laguna_router_key_ordinal` takes its magnitude == 0 path.
    l = [Float](repeating: -200.0, count: 256)
    b = [Float](repeating: 0.0, count: 256)
    for i in 0..<256 where i % 2 == 0 { b[i] = -0.0 }
    c.add(l, b)

    // Half the row saturates to +0 keys, half carries real keys.
    l = (0..<256).map { i in i % 2 == 0 ? Float(-200.0) : nextUniform(-2, 2) }
    c.add(l, b)
    classes.append(c)
}

// 5. Top-8 concentrated inside a single 32-lane block, and spread one per block.
do {
    var c = RowClass(name: "block_skew")
    for blockIndex in 0..<8 {
        var l = [Float](repeating: -6.0, count: 256)
        for k in 0..<9 { l[blockIndex * 32 + k] = 6.0 - Float(k) * 0.01 }
        c.add(l, [Float](repeating: 0.0, count: 256))
    }
    // Exactly the ninth-best also inside block 0: the block must still publish
    // eight and the global winner set must be unchanged.
    var l = [Float](repeating: -6.0, count: 256)
    for k in 0..<20 { l[k] = 6.0 - Float(k) * 0.001 }
    c.add(l, [Float](repeating: 0.0, count: 256))
    // One strong expert per block.
    l = [Float](repeating: -6.0, count: 256)
    for blockIndex in 0..<8 { l[blockIndex * 32 + blockIndex] = 5.0 + Float(blockIndex) * 0.01 }
    c.add(l, [Float](repeating: 0.0, count: 256))
    classes.append(c)
}

// MARK: - Run

guard let device = MTLCreateSystemDefaultDevice() else {
    print("FATAL: no Metal device")
    exit(1)
}
let options = MTLCompileOptions()
options.fastMathEnabled = false  // matches MLX device.cpp:631
let library: MTLLibrary
do {
    library = try device.makeLibrary(source: metalSource, options: options)
} catch {
    print("FATAL: compile failed: \(error)")
    exit(1)
}
let queue = device.makeCommandQueue()!
var pipelines: [String: MTLComputePipelineState] = [:]
for arm in arms {
    pipelines[arm.name] = try! device.makeComputePipelineState(
        function: library.makeFunction(name: arm.name)!)
}

struct Result {
    var indices: [UInt32]
    var scores: [Float]
}

func run(_ armName: String, logits: [Float], bias: [Float], rows: Int) -> Result {
    let lBuf = device.makeBuffer(
        bytes: logits, length: logits.count * 4, options: .storageModeShared)!
    let bBuf = device.makeBuffer(bytes: bias, length: bias.count * 4, options: .storageModeShared)!
    let iBuf = device.makeBuffer(length: rows * 8 * 4, options: .storageModeShared)!
    let sBuf = device.makeBuffer(length: rows * 8 * 4, options: .storageModeShared)!
    memset(iBuf.contents(), 0xCD, rows * 8 * 4)
    memset(sBuf.contents(), 0xCD, rows * 8 * 4)
    let cb = queue.makeCommandBuffer()!
    let enc = cb.makeComputeCommandEncoder()!
    enc.setComputePipelineState(pipelines[armName]!)
    enc.setBuffer(lBuf, offset: 0, index: 0)
    enc.setBuffer(bBuf, offset: 0, index: 1)
    enc.setBuffer(iBuf, offset: 0, index: 2)
    enc.setBuffer(sBuf, offset: 0, index: 3)
    enc.dispatchThreadgroups(
        MTLSize(width: rows, height: 1, depth: 1),
        threadsPerThreadgroup: MTLSize(width: 256, height: 1, depth: 1))
    enc.endEncoding()
    cb.commit()
    cb.waitUntilCompleted()
    let ip = iBuf.contents().bindMemory(to: UInt32.self, capacity: rows * 8)
    let sp = sBuf.contents().bindMemory(to: Float.self, capacity: rows * 8)
    return Result(
        indices: Array(UnsafeBufferPointer(start: ip, count: rows * 8)),
        scores: Array(UnsafeBufferPointer(start: sp, count: rows * 8)))
}

/// Raw-bit comparison. `mismatchWords` counts differing uint32 words across
/// both outputs; `maxAbsDiff` is a readability aid only.
func compare(_ a: Result, _ b: Result) -> (words: Int, rows: Int, maxAbsDiff: Float) {
    var words = 0
    var badRows = Set<Int>()
    var maxAbs: Float = 0
    for i in 0..<a.indices.count {
        if a.indices[i] != b.indices[i] {
            words += 1
            badRows.insert(i / 8)
        }
        if a.scores[i].bitPattern != b.scores[i].bitPattern {
            words += 1
            badRows.insert(i / 8)
        }
        let d = abs(a.scores[i] - b.scores[i])
        if d.isFinite && d > maxAbs { maxAbs = d }
    }
    return (words, badRows.count, maxAbs)
}

var totalWords = 0
var totalRows = 0
var faultWords: [String: Int] = [:]
var onControlWords = 0

print("metal device: \(device.name)")
print("kernels: \(arms.count), classes: \(classes.count)")

for precision in ["bf16", "fp32"] {
    print("\n=== logits precision: \(precision) ===")
    for c in classes {
        let logits = precision == "bf16" ? c.logits.map(bf16Round) : c.logits
        let bias = c.bias
        for normalizing in [false, true] {
            for scoreTable in [false, true] {
                let suffix =
                    "\(normalizing ? "norm" : "plain")_\(scoreTable ? "table" : "recompute")"
                let ctrl = run("full256_\(suffix)", logits: logits, bias: bias, rows: c.rows)
                let cand = run("tourn_\(suffix)", logits: logits, bias: bias, rows: c.rows)
                let cmp = compare(ctrl, cand)
                totalWords += cmp.words
                totalRows += cmp.rows
                print(
                    "  \(c.name) rows=\(c.rows) arm=\(suffix) "
                        + "mismatch_words=\(cmp.words) mismatch_rows=\(cmp.rows) "
                        + "max_abs_diff=\(cmp.maxAbsDiff)")
            }
        }
        // On-control: the shipped arm against itself must report zero.
        let a = run("full256_norm_table", logits: logits, bias: bias, rows: c.rows)
        let b = run("full256_norm_table", logits: logits, bias: bias, rows: c.rows)
        onControlWords += compare(a, b).words
        // Fault arms must be detected.
        for fault in ["tourn_fault_drop8", "tourn_fault_flatdir"] {
            let f = run(fault, logits: logits, bias: bias, rows: c.rows)
            let w = compare(a, f).words
            faultWords[fault, default: 0] += w
            print("  \(c.name) \(fault) mismatch_words=\(w)")
        }
    }
}

print("\n--- verdict ---")
print("on-control (shipped arm vs itself) mismatch_words: \(onControlWords)")
for (k, v) in faultWords.sorted(by: { $0.key < $1.key }) {
    print("fault \(k) mismatch_words: \(v) (must be > 0)")
}
print("candidate total mismatch_words: \(totalWords), mismatch_rows: \(totalRows)")

let faultsLive = faultWords.values.allSatisfy { $0 > 0 }
if onControlWords != 0 {
    print("RESULT: INVALID -- on-control arm disagreed with itself.")
    exit(1)
}
if !faultsLive {
    print("RESULT: INVALID -- an injected fault was not detected.")
    exit(1)
}
if totalWords == 0 {
    print("RESULT: SUPPORTED -- tournament is bit-identical on every row and arm.")
    exit(0)
}
print("RESULT: REFUTED -- \(totalWords) mismatching words.")
exit(1)
