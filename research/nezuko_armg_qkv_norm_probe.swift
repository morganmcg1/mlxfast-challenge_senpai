// Research-only host harness (not part of the submission surface).
//
// Arm G rung 1 of PR #682: fold the attention input RMSNorm into the decode
// NVFP4 QKV projection so the `rmsbfloat16` dispatch (142.3 us/step, 41
// dispatches) disappears.
//
// The scored decode path selects `laguna_decode_nvfp4_qkv_h64_r1_v1_lm1_pw1_se1_sd1`
// (lane-major pairwise), so this probe compiles the *shipped* lane-major source
// text sliced out of LagunaRuntimeModel.swift and answers two questions in one
// process:
//
//   1. Bit-exactness. Arm A is `rms_single_row`'s laguna fast path (replicated
//      from the AOT metal source) followed by the shipped QKV kernel. Arm G is
//      the fused kernel. Every bit of `projected` must match, and arm G's
//      second output `normalized_out` must equal arm A's intermediate.
//   2. Cost. The QKV pool is 1704 us/step at ~241 GB/s against a 263 GB/s
//      measured read ceiling, so it is DRAM bound with ALU slack -- but the
//      fusion roughly doubles inner-loop ALU. If the pool grows more than
//      142 us/step (8.3%) the fusion is a net loss. Measured ABBA over 8
//      independent weight sets so the 10.5 MB code plane cannot sit in cache.
//
// Build and run:
//   xcrun swiftc -O research/nezuko_armg_qkv_norm_probe.swift -o /tmp/nezarmg \
//     && /tmp/nezarmg

import Foundation
import Metal

// MARK: - Shipped-source extraction

let lrmPath =
    CommandLine.arguments.count > 1
    ? CommandLine.arguments[1] : "Sources/MLXFastModel/LagunaRuntimeModel.swift"
let rmsPath = "Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/rms_norm.metal"
let lrmLines = try! String(contentsOfFile: lrmPath, encoding: .utf8)
    .split(separator: "\n", omittingEmptySubsequences: false).map(String.init)

func findLine(_ needle: String, from: Int = 0) -> Int {
    for i in from..<lrmLines.count where lrmLines[i].contains(needle) { return i }
    preconditionFailure("`\(needle)` not found in \(lrmPath)")
}

/// Slices a `"""` block opened on `openLine`, dedenting by the indentation of
/// the closing delimiter exactly as Swift does.
func sliceLiteral(openLine: Int) -> String {
    var close = -1
    var i = openLine + 1
    while i < lrmLines.count {
        if lrmLines[i].trimmingCharacters(in: .whitespaces) == "\"\"\"" { close = i; break }
        i += 1
    }
    precondition(close >= 0, "unterminated literal opened at line \(openLine + 1)")
    let indent = lrmLines[close].prefix(while: { $0 == " " }).count
    return lrmLines[(openLine + 1)..<close]
        .map { String($0.dropFirst(min(indent, $0.prefix(while: { $0 == " " }).count))) }
        .joined(separator: "\n")
}

/// Every gate below defaults to enabled (`env != "0"`), and the kernel name in
/// the M4 dispatch census (`..._lm1_pw1_se1_sd1`) confirms the scored decode
/// selects all four. Resolving the interpolations to that configuration keeps
/// the probe on the shipped text instead of a hand-copied paraphrase.
let interpolations: [(token: String, value: String)] = [
    ("lagunaTailNVFP4ScaleDecodeSource", "    return float(as_type<half>(raw));"),
    ("lagunaTailNVFP4QDotAccumDeclSource", "float accum;"),
    (
        "lagunaTailNVFP4QDotFirstGroupSource",
        """
        if (j == 0) {
                        accum =
                            (x_thread[8 * j] * v04.x +
                             x_thread[8 * j + 1] * v15.x +
                             x_thread[8 * j + 2] * v26.x +
                             x_thread[8 * j + 3] * v37.x);
                    } else {
                        accum +=
                            (x_thread[8 * j] * v04.x +
                             x_thread[8 * j + 1] * v15.x +
                             x_thread[8 * j + 2] * v26.x +
                             x_thread[8 * j + 3] * v37.x);
                    }
        """
    ),
    ("lagunaTailNVFP4QDotReturn", "return scale * accum;"),
    ("lagunaTailNVFP4ScaleFoldEnabled", "ushort raw = ushort(bits) << 7;"),
    ("lagunaTailNVFP4RowScaleSuffixSource", " * 4194304.0f"),
    ("pairwise ? 4 : 2", "4"),
    ("pairwise ? \"(simd_lid >> 1)\"", "(simd_lid >> 1)"),
]

/// Replaces every `\(...)` with its resolved text, matching the parenthesis
/// depth so nested calls and string literals survive.
func resolveInterpolations(_ text: String) -> String {
    var out = ""
    var chars = Array(text)
    var i = 0
    while i < chars.count {
        if chars[i] == "\\", i + 1 < chars.count, chars[i + 1] == "(" {
            var depth = 0
            var j = i + 1
            var inString = false
            while j < chars.count {
                let c = chars[j]
                if inString {
                    if c == "\\" { j += 2; continue }
                    if c == "\"" { inString = false }
                } else if c == "\"" {
                    inString = true
                } else if c == "(" {
                    depth += 1
                } else if c == ")" {
                    depth -= 1
                    if depth == 0 { break }
                }
                j += 1
            }
            precondition(depth == 0, "unbalanced interpolation in shipped literal")
            let expr = String(chars[(i + 2)..<j])
            guard let rule = interpolations.first(where: { expr.contains($0.token) }) else {
                preconditionFailure("no resolution rule for interpolation `\(expr)`")
            }
            out += rule.value
            i = j + 1
            continue
        }
        out.append(chars[i])
        i += 1
    }
    return out
}

let qdotHeader = resolveInterpolations(
    sliceLiteral(openLine: findLine("private let lagunaTailNVFP4QMVHeader = \"\"\"")))
/// The lane-major body is an implicit-return literal, so anchor on the first
/// bare `"""` after the declaration rather than on a `return` keyword.
func sliceFunctionLiteral(declNeedle: String) -> String {
    var i = findLine(declNeedle) + 1
    while i < lrmLines.count {
        if lrmLines[i].trimmingCharacters(in: .whitespaces) == "\"\"\"" {
            return sliceLiteral(openLine: i)
        }
        i += 1
    }
    preconditionFailure("no literal opens after `\(declNeedle)`")
}

let laneMajorBody = resolveInterpolations(
    sliceFunctionLiteral(
        declNeedle: "private func lagunaDecodeNVFP4QKVLaneMajorSource(pairwise: Bool) -> String"))

precondition(
    qdotHeader.contains("laguna_tail_nvfp4_qdot") && qdotHeader.contains("as_type<half2>(p0)")
        && !qdotHeader.contains("\\("),
    "qdot header did not resolve")
precondition(
    laneMajorBody.contains("x_thread[i] = float(normalized[column + i]);")
        && laneMajorBody.contains("projected[out_row] = bfloat(result);")
        && laneMajorBody.contains("thread uint8_t sb[blocks_per_row];")
        && !laneMajorBody.contains("\\("),
    "lane-major body did not resolve")

// The reference RMS below replicates the AOT laguna fast path. Assert the
// expressions this probe depends on are still the shipped ones.
let rmsText = try! String(contentsOfFile: rmsPath, encoding: .utf8)
for needle in [
    "if (axis_size == 2048 && grid_size == 512 && w_stride == 1) {",
    "constexpr uint laguna_simdgroups = 16;",
    "acc = simd_sum(acc);",
    "if (simd_group_id == 0 && simd_lane_id >= laguna_simdgroups) {",
    "local_inv_mean[0] = metal::precise::rsqrt(acc / axis_size + eps);",
    "row_w[i] * static_cast<T>(xcache[i] * local_inv_mean[0]);",
] {
    precondition(rmsText.contains(needle), "AOT rms fast path drifted: `\(needle)`")
}

// MARK: - Kernel sources

let preamble = """
    #include <metal_stdlib>
    #include <metal_simdgroup>
    using namespace metal;
    typedef bfloat bfloat16_t;
    #ifndef METAL_FUNC
    #define METAL_FUNC inline __attribute__((__always_inline__))
    #endif

    """

/// Arm A stage 1: `rms_single_row`'s laguna fast path, one row, 512 threads.
let rmsSource = preamble + """
    [[kernel]] void probe_rms(
      const device bfloat16_t* x [[buffer(0)]],
      const device bfloat16_t* w [[buffer(1)]],
      device bfloat16_t* out [[buffer(2)]],
      uint lid [[thread_position_in_threadgroup]],
      uint simd_lane_id [[thread_index_in_simdgroup]],
      uint simd_group_id [[simdgroup_index_in_threadgroup]]) {
      constexpr uint axis_size = 2048;
      constexpr int N_READS = 4;
      constexpr uint laguna_simdgroups = 16;
      const float eps = 1.0e-6f;
      threadgroup float local_inv_mean[1];
      threadgroup float local_sums[32];

      const device bfloat16_t* row_x = x + lid * N_READS;
      const device bfloat16_t* row_w = w + lid * N_READS;
      device bfloat16_t* row_out = out + lid * N_READS;

      float acc = 0;
      float xcache[N_READS];
      for (int i = 0; i < N_READS; i++) {
        float xi = row_x[i];
        xcache[i] = xi;
        acc += xi * xi;
      }
      acc = simd_sum(acc);
      if (simd_group_id == 0 && simd_lane_id >= laguna_simdgroups) {
        local_sums[simd_lane_id] = 0;
      }
      if (simd_lane_id == 0) {
        local_sums[simd_group_id] = acc;
      }
      threadgroup_barrier(mem_flags::mem_threadgroup);
      if (simd_group_id == 0) {
        acc = simd_sum(local_sums[simd_lane_id]);
        if (simd_lane_id == 0) {
          local_inv_mean[0] = metal::precise::rsqrt(acc / axis_size + eps);
        }
      }
      threadgroup_barrier(mem_flags::mem_threadgroup);
      for (int i = 0; i < N_READS; i++) {
        row_out[i] = row_w[i] * static_cast<bfloat16_t>(xcache[i] * local_inv_mean[0]);
      }
    }
    """

/// The 64-thread / 2-simdgroup restatement of the same reduction. Simdgroup
/// `sg` owns AOT chunks `8*sg .. 8*sg+7`; lane `l` of chunk `g` accumulates the
/// same four contiguous squares in the same order into the same `local_sums[g]`
/// slot, so the 32-lane final `simd_sum` sees an identical operand vector.
let fusedPrologue = """
    threadgroup float laguna_norm_sums[32];
    threadgroup float laguna_norm_inv[1];
    if (simd_gid == 0 && simd_lid >= 16) {
        laguna_norm_sums[simd_lid] = 0;
    }
    for (uint chunk = 0; chunk < 8; ++chunk) {
        const uint g = simd_gid * 8 + chunk;
        const device bfloat16_t* row_x = residual + g * 128 + simd_lid * 4;
        float acc = 0;
        for (int i = 0; i < 4; i++) {
            float xi = row_x[i];
            acc += xi * xi;
        }
        acc = simd_sum(acc);
        if (simd_lid == 0) {
            laguna_norm_sums[g] = acc;
        }
    }
    threadgroup_barrier(mem_flags::mem_threadgroup);
    if (simd_gid == 0) {
        float acc = simd_sum(laguna_norm_sums[simd_lid]);
        if (simd_lid == 0) {
            laguna_norm_inv[0] = metal::precise::rsqrt(acc / float(axis_size) + 1.0e-6f);
        }
    }
    threadgroup_barrier(mem_flags::mem_threadgroup);
    const float laguna_inv_mean = laguna_norm_inv[0];
    const bool laguna_emit_norm = (tile == 0 && simd_gid == 0);

    """

let stockLoad = """
        for (uint i = 0; i < values_per_thread; ++i) {
            x_thread[i] = float(normalized[column + i]);
        }
    """
let declAnchor = "thread float x_thread[values_per_thread];"

precondition(
    laneMajorBody.ranges(of: stockLoad).count == 1
        && laneMajorBody.ranges(of: declAnchor).count == 1,
    "lane-major inner load or declaration anchor not found verbatim")

/// The fused arms decompose the fusion into its three separable costs so a
/// regression can be attributed instead of guessed:
///
/// - `prologueOnly` pays only the RMS reduction plus one extra streaming pass
///   over the 4 KB activation row. Its `projected` is deliberately wrong (the
///   inner loop reads the un-normalized residual), so it is timing-only.
/// - `noEmit` additionally pays the `norm_weight` read and the per-element
///   normalize ALU. This is the ceiling for the variant where `normalized` is
///   never materialized because `gate_sp` also folds the norm.
/// - `hoistedEmit` writes the 2048-word `normalized` from tile 0 in a pre-pass,
///   keeping the main loop free of stores.
/// - `inLoopEmit` writes it from inside the main loop under `tile == 0`, where
///   the store may alias the activation loads.
enum FusedArm: String, CaseIterable {
    case prologueOnly = "P prologue"
    case noEmit = "N no-emit"
    case hoistedEmit = "H hoist-emit"
    case inLoopEmit = "L loop-emit"

    var correct: Bool { self != .prologueOnly }
    var emitsNormalized: Bool { self == .hoistedEmit || self == .inLoopEmit }
}

let normalizeExpr =
    "bfloat16_t(norm_weight[j] * bfloat16_t(float(residual[j]) * laguna_inv_mean))"

func fusedBody(_ arm: FusedArm) -> String {
    let load: String
    switch arm {
    case .prologueOnly:
        load = """
                for (uint i = 0; i < values_per_thread; ++i) {
                    x_thread[i] = float(residual[column + i]);
                }
            """
    case .noEmit, .hoistedEmit:
        load = """
                for (uint i = 0; i < values_per_thread; ++i) {
                    const uint j = column + i;
                    x_thread[i] = float(\(normalizeExpr));
                }
            """
    case .inLoopEmit:
        load = """
                for (uint i = 0; i < values_per_thread; ++i) {
                    const uint j = column + i;
                    const bfloat16_t nv = \(normalizeExpr);
                    x_thread[i] = float(nv);
                    if (laguna_emit_norm) {
                        normalized_out[j] = nv;
                    }
                }
            """
    }
    let prePass =
        arm == .hoistedEmit
        ? """
            if (laguna_emit_norm) {
                for (uint j = simd_lid; j < axis_size; j += 32) {
                    normalized_out[j] = \(normalizeExpr);
                }
            }

            """
        : ""
    return laneMajorBody
        .replacingOccurrences(of: stockLoad, with: load)
        .replacingOccurrences(of: declAnchor, with: fusedPrologue + prePass + declAnchor)
}

let stockSource = preamble + qdotHeader + """

    [[kernel]] void probe_qkv(
      const device bfloat16_t* normalized [[buffer(0)]],
      const device uint32_t* weight_codes [[buffer(1)]],
      const device uint8_t* scale_nibbles [[buffer(2)]],
      const device uint8_t* scale_bases [[buffer(3)]],
      const device uint8_t* weight_scales [[buffer(4)]],
      device bfloat16_t* projected [[buffer(5)]],
      uint3 threadgroup_position_in_grid [[threadgroup_position_in_grid]],
      uint simdgroup_index_in_threadgroup [[simdgroup_index_in_threadgroup]],
      uint thread_index_in_simdgroup [[thread_index_in_simdgroup]]) {
    \(laneMajorBody)
    }
    """

func fusedSource(_ arm: FusedArm) -> String {
    preamble + qdotHeader + """

        [[kernel]] void probe_qkv(
          const device bfloat16_t* residual [[buffer(0)]],
          const device uint32_t* weight_codes [[buffer(1)]],
          const device uint8_t* scale_nibbles [[buffer(2)]],
          const device uint8_t* scale_bases [[buffer(3)]],
          const device uint8_t* weight_scales [[buffer(4)]],
          device bfloat16_t* projected [[buffer(5)]],
          const device bfloat16_t* norm_weight [[buffer(6)]],
          device bfloat16_t* normalized_out [[buffer(7)]],
          uint3 threadgroup_position_in_grid [[threadgroup_position_in_grid]],
          uint simdgroup_index_in_threadgroup [[simdgroup_index_in_threadgroup]],
          uint thread_index_in_simdgroup [[thread_index_in_simdgroup]]) {
        \(fusedBody(arm))
        }
        """
}

// MARK: - Device

let device = MTLCreateSystemDefaultDevice()!
let queue = device.makeCommandQueue()!

print("=== device ===")
print("name                          \(device.name)")
print("architecture                  \(device.architecture.name)")
print("maxThreadgroupMemoryLength    \(device.maxThreadgroupMemoryLength) B")
print("lrm source                    \(lrmPath)")

func pipeline(_ source: String, _ name: String) -> MTLComputePipelineState {
    let lib: MTLLibrary
    do { lib = try device.makeLibrary(source: source, options: nil) } catch {
        print("--- compile failed for \(name) ---")
        print(source)
        fatalError("\(error)")
    }
    return try! device.makeComputePipelineState(function: lib.makeFunction(name: name)!)
}

let rmsPipe = pipeline(rmsSource, "probe_rms")
let stockPipe = pipeline(stockSource, "probe_qkv")
let fusedPipes = FusedArm.allCases.map { pipeline(fusedSource($0), "probe_qkv") }

print("\n=== pipelines ===")
for (n, p) in [("A stock qkv", stockPipe), ("rms ref", rmsPipe)]
    + zip(FusedArm.allCases.map(\.rawValue), fusedPipes)
{
    print(
        "\(n.padding(toLength: 14, withPad: " ", startingAt: 0))"
            + "tgmem \(p.staticThreadgroupMemoryLength) B  "
            + "maxTPTG \(p.maxTotalThreadsPerThreadgroup)  "
            + "width \(p.threadExecutionWidth)")
}

// MARK: - Fixtures

let hidden = 2048
let heads = 64
let rows = (heads + 2 * 8) * 128  // 10240 for the h64 sliding site
let sets = 8

func bf16(_ f: Float) -> UInt16 {
    let b = f.bitPattern
    return UInt16(truncatingIfNeeded: (b &+ 0x7FFF &+ ((b >> 16) & 1)) >> 16)
}
func unbf16(_ h: UInt16) -> Float { Float(bitPattern: UInt32(h) << 16) }

var rngState: UInt64 = 0x9E37_79B9_7F4A_7C15
func nextRand() -> UInt64 {
    rngState ^= rngState << 13
    rngState ^= rngState >> 7
    rngState ^= rngState << 17
    return rngState
}
func uniform() -> Float { Float(nextRand() >> 40) / Float(1 << 24) }
func normal() -> Float {
    let u = max(uniform(), 1e-7)
    return sqrt(-2 * log(u)) * cos(2 * .pi * uniform())
}

func buffer(_ bytes: Int) -> MTLBuffer {
    device.makeBuffer(length: bytes, options: .storageModeShared)!
}
func fill<T>(_ b: MTLBuffer, _ values: [T]) {
    values.withUnsafeBytes { b.contents().copyMemory(from: $0.baseAddress!, byteCount: $0.count) }
}

let residualBuf = buffer(hidden * 2)
let normWeightBuf = buffer(hidden * 2)
let normalizedRefBuf = buffer(hidden * 2)
let normalizedOutBuf = buffer(hidden * 2)
let weightScalesBuf = buffer(rows * (hidden / 16))

fill(normWeightBuf, (0..<hidden).map { _ in bf16(1.0 + 0.1 * normal()) })

struct WeightSet {
    let codes: MTLBuffer
    let nibbles: MTLBuffer
    let bases: MTLBuffer
    let projA: MTLBuffer
    let projG: [MTLBuffer]
}

// `scale_bases[row] != 0xFF` keeps every row on the lane-major nibble path, the
// one the census shows the scored decode takes; `weight_scales` stays bound but
// unread, exactly as in the shipped dispatch.
let weightSets: [WeightSet] = (0..<sets).map { _ in
    let codes = buffer(rows * (hidden / 8) * 4)
    let cp = codes.contents().bindMemory(to: UInt32.self, capacity: rows * hidden / 8)
    for i in 0..<(rows * hidden / 8) { cp[i] = UInt32(truncatingIfNeeded: nextRand()) }
    let nibbles = buffer(rows * (hidden / 64))
    let np = nibbles.contents().bindMemory(to: UInt8.self, capacity: rows * hidden / 64)
    for i in 0..<(rows * hidden / 64) { np[i] = UInt8(truncatingIfNeeded: nextRand()) }
    let bases = buffer(rows)
    let bp = bases.contents().bindMemory(to: UInt8.self, capacity: rows)
    for i in 0..<rows { bp[i] = UInt8(20 + (nextRand() % 12)) }
    return WeightSet(
        codes: codes, nibbles: nibbles, bases: bases,
        projA: buffer(rows * 2), projG: FusedArm.allCases.map { _ in buffer(rows * 2) })
}

// MARK: - Dispatch

let tgSize = MTLSize(width: 64, height: 1, depth: 1)
let tgCount = MTLSize(width: rows / 2, height: 1, depth: 1)

/// One command buffer per dispatch, matching the scored decode (the M4 census
/// reports `cbs == dispatches == 406`), and returns GPU busy microseconds.
func run(
    _ pipe: MTLComputePipelineState, _ binds: [(Int, MTLBuffer)],
    threadgroups: MTLSize, threads: MTLSize
) -> Double {
    let cb = queue.makeCommandBuffer()!
    let enc = cb.makeComputeCommandEncoder()!
    enc.setComputePipelineState(pipe)
    for (idx, buf) in binds { enc.setBuffer(buf, offset: 0, index: idx) }
    enc.dispatchThreadgroups(threadgroups, threadsPerThreadgroup: threads)
    enc.endEncoding()
    cb.commit()
    cb.waitUntilCompleted()
    return (cb.gpuEndTime - cb.gpuStartTime) * 1e6
}

func runRms() {
    _ = run(
        rmsPipe, [(0, residualBuf), (1, normWeightBuf), (2, normalizedRefBuf)],
        threadgroups: MTLSize(width: 1, height: 1, depth: 1),
        threads: MTLSize(width: 512, height: 1, depth: 1))
}

func runStock(_ s: WeightSet) -> Double {
    run(
        stockPipe,
        [
            (0, normalizedRefBuf), (1, s.codes), (2, s.nibbles), (3, s.bases),
            (4, weightScalesBuf), (5, s.projA),
        ], threadgroups: tgCount, threads: tgSize)
}

func runFused(_ arm: Int, _ s: WeightSet) -> Double {
    run(
        fusedPipes[arm],
        [
            (0, residualBuf), (1, s.codes), (2, s.nibbles), (3, s.bases),
            (4, weightScalesBuf), (5, s.projG[arm]), (6, normWeightBuf), (7, normalizedOutBuf),
        ], threadgroups: tgCount, threads: tgSize)
}

func words(_ b: MTLBuffer, _ n: Int) -> [UInt16] {
    let p = b.contents().bindMemory(to: UInt16.self, capacity: n)
    return Array(UnsafeBufferPointer(start: p, count: n))
}

// MARK: - 1. Bit-exactness

print("\n=== bit-exactness (all \(rows) projected rows + 2048 normalized) ===")
print(
    "case / arm".padding(toLength: 36, withPad: " ", startingAt: 0)
        + "proj mismatches  norm mismatches  max |proj| abs delta")
let cases: [(String, () -> Float)] = [
    ("standard N(0,1)", { normal() }),
    ("wide N(0,8)", { 8 * normal() }),
    ("tiny N(0,1e-3)", { 1e-3 * normal() }),
    ("near-zero N(0,1e-6)", { 1e-6 * normal() }),
    ("heavy tail", { normal() * (uniform() < 0.02 ? 60 : 1) }),
]
var exact = true
for (name, draw) in cases {
    fill(residualBuf, (0..<hidden).map { _ in bf16(draw()) })
    runRms()
    let s = weightSets[0]
    _ = runStock(s)
    let a = words(s.projA, rows)
    let nRef = words(normalizedRefBuf, hidden)
    for (i, arm) in FusedArm.allCases.enumerated() where arm.correct {
        fill(normalizedOutBuf, [UInt16](repeating: 0, count: hidden))
        _ = runFused(i, s)
        let g = words(s.projG[i], rows)
        let projBad = zip(a, g).filter { $0 != $1 }.count
        let normBad =
            arm.emitsNormalized
            ? zip(nRef, words(normalizedOutBuf, hidden)).filter { $0 != $1 }.count : -1
        let maxDelta = zip(a, g).map { abs(unbf16($0) - unbf16($1)) }.max() ?? 0
        if projBad != 0 || normBad > 0 { exact = false }
        print(
            "\(name) / \(arm.rawValue)".padding(toLength: 36, withPad: " ", startingAt: 0)
                + String(projBad).padding(toLength: 17, withPad: " ", startingAt: 0)
                + (normBad < 0 ? "n/a" : String(normBad))
                    .padding(toLength: 17, withPad: " ", startingAt: 0)
                + "\(maxDelta)")
    }
}
print(exact ? "VERDICT bit-exact" : "VERDICT NOT bit-exact")

// MARK: - 2. Cost

fill(residualBuf, (0..<hidden).map { _ in bf16(normal()) })
runRms()

let warmup = 3
let pairs = 12
for _ in 0..<warmup {
    for s in weightSets {
        _ = runStock(s)
        for i in FusedArm.allCases.indices { _ = runFused(i, s) }
    }
}

// Each arm is paired against its own freshly interleaved stock samples, ABBA
// within a pair index so monotone drift cancels.
var aTimes = [[Double]](repeating: [], count: FusedArm.allCases.count)
var gTimes = [[Double]](repeating: [], count: FusedArm.allCases.count)
for p in 0..<pairs {
    for s in weightSets {
        for i in FusedArm.allCases.indices {
            if p % 2 == 0 {
                aTimes[i].append(runStock(s))
                gTimes[i].append(runFused(i, s))
                gTimes[i].append(runFused(i, s))
                aTimes[i].append(runStock(s))
            } else {
                gTimes[i].append(runFused(i, s))
                aTimes[i].append(runStock(s))
                aTimes[i].append(runStock(s))
                gTimes[i].append(runFused(i, s))
            }
        }
    }
}

func median(_ v: [Double]) -> Double {
    let s = v.sorted()
    return s.count % 2 == 1 ? s[s.count / 2] : 0.5 * (s[s.count / 2 - 1] + s[s.count / 2])
}
func pct(_ v: [Double], _ q: Double) -> Double { v.sorted()[Int(Double(v.count - 1) * q)] }

let codeBytes = Double(rows * hidden / 2)
let allA = aTimes.flatMap { $0 }
let aMed = median(allA)

print("\n=== cost, h\(heads) site: rows=\(rows), \(rows / 2) threadgroups x 64 threads ===")
print("samples per arm               \(gTimes[0].count) (stock: \(allA.count) total)")
func line(_ name: String, _ v: [Double]) {
    let m = median(v)
    print(
        name.padding(toLength: 14, withPad: " ", startingAt: 0)
            + "median \(String(format: "%8.2f", m)) us"
            + "  p10 \(String(format: "%8.2f", pct(v, 0.1)))"
            + "  p90 \(String(format: "%8.2f", pct(v, 0.9)))"
            + "  ratio \(String(format: "%6.3f", m / aMed))")
}
line("A stock", allA)
for (i, arm) in FusedArm.allCases.enumerated() { line(arm.rawValue, gTimes[i]) }
print(
    "A effective code bandwidth    "
        + "\(String(format: "%.1f", codeBytes / aMed / 1000)) GB/s"
        + "  (live scored h64 dispatch: 44.7 us -> 235 GB/s)")

// Scored-path accounting. 30 h64 dispatches + 10 h48 dispatches per decode step
// carry 1340.7 + 363.5 = 1704.2 us of busy time; the fusion removes the whole
// 142.3 us `rmsbfloat16` pool. Growth is charged against the h64 measurement
// because the h48 site runs the identical kernel at 0.8x the rows.
let qkvPool = 1704.2
let rmsPool = 142.3
print("\n=== scored-path projection (M4 decode census) ===")
print("arm            qkv growth us   net busy us   net score %")
for (i, arm) in FusedArm.allCases.enumerated() {
    let growth = qkvPool * (median(gTimes[i]) / aMed - 1.0)
    let net = growth - rmsPool
    print(
        arm.rawValue.padding(toLength: 15, withPad: " ", startingAt: 0)
            + String(format: "%+13.1f", growth)
            + String(format: "%+14.1f", net)
            + String(format: "%+14.4f", -net / 8972.0 * 0.8 * 0.75 * 100))
}
print("break-even qkv growth         \(String(format: "%.1f", rmsPool)) us/step"
    + " = ratio \(String(format: "%.4f", 1 + rmsPool / qkvPool))")
print("(advisor conversion 0.00669 %/us; P is timing-only, N assumes gate_sp also folds the norm)")
print(
    "\nplus 41 fewer command buffers at ~3.03 us of measured gap each: "
        + "\(String(format: "%.0f", 41 * 3.03)) us/step of non-busy wall not counted above")
