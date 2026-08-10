// Research-only host probe (not part of the submission surface).
//
// Round-107 arm F, Stage 1.  Standalone, residency-defeated replica of the
// scored routed+shared NVFP4 down-residual kernel
// `laguna_routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6`, reconstructed
// from the MSL dumped off the live pipeline in Stage 0 and validated against it
// (identical driver triple maxThreads=1024 execWidth=32 tgMem=80).
//
// Question.  The in-situ anchor is 22.07 us/call for 5,030,912 unique DRAM
// bytes = 227.95 GB/s = 87.47 % of this host's measured 260.6 GB/s read
// ceiling.  Two models fit that number:
//
//   (D) DRAM-bound on unique bytes.  Then removing activation *replay* cannot
//       help at all, because replay is served by cache.
//   (I) bound on issued load slots, L1 line-touches or instruction issue.  A0
//       issues 10,027,008 bytes and 1,769,472 loads per call, of which 47.06 %
//       of the bytes are the 512-fold replay of one 9,216 byte activation set,
//       and 72.7 % of the 44 L1 line-touches per simdgroup come from the
//       32-byte-strided 8-byte activation loads.  Then either raising
//       `outputs_per_simd` 4 -> 8 (-16.67 % loads, -23.53 % issued bytes) or
//       widening the activation load to 2 x uint4 (-36.4 % line-touches at
//       identical geometry) buys time at zero change in unique DRAM bytes.
//
// Design (second revision; the first revision measured the wrong regime).
//
//  * Dispatch regime.  In situ the kernel is entered 39 times per decode step,
//    once per layer, as 39 serialised 512-threadgroup dispatches.  A single
//    fused dispatch of 39 * 512 threadgroups amortises 38 launch ramps and
//    drains, and is therefore *not* the scored regime.  Every cell is measured
//    in both `split` (39 serialised dispatches in one serial encoder, the
//    scored shape) and `fused` (one dispatch, height = calls) mode.  The
//    difference prices launch ramp, and only `split` may be compared with the
//    22.07 us/call in-situ anchor.
//  * Interleaving.  All cells are timed once per round inside the same round
//    loop, with the cell order reversed on odd rounds, so a clock ramp or a
//    thermal drift cannot be mistaken for an arm effect.  Every comparison is
//    reported as a round-paired difference against the same-mode, same-residency
//    a0 cell.
//  * Falsifier ladder.  a0_act{2,1,0} vary only how many of the four
//    `vec<bfloat,4>` activation loads each lane issues, at fixed threadgroup
//    count, fixed unique bytes, fixed arithmetic and fixed code/scale loads:
//    d(T)/d(activation loads) predicts A1 before any runtime edit exists.
//    a0_wide is the widened-activation lever itself.  a0_badcoal is a
//    deliberate *degradation* (code loads restrided to 32 bytes, line-touches
//    44 -> 68 per simdgroup) and acts as a positive control: if tripling the
//    line-touches of the dominant load stream is free, then a 36 % reduction
//    cannot pay.  a2 has A1's threadgroup count and A0's load census, so it
//    separates "fewer threadgroups" from "fewer loads".  `_min` arms strip the
//    NVFP4 unpack and dot but keep every load and a cross-lane reduction, so
//    they price arithmetic without letting the compiler sink loads into the
//    `lane == 0` epilogue (the first revision's `_noarith` arms did not keep a
//    cross-lane op and were dead-code eliminated; their numbers were void).
//  * Residency discipline (rule 98.9).  Each of the `calls` replicas selects 9
//    fresh experts out of a 320 MiB bank by a fixed permutation, so unique
//    bytes == issued DRAM bytes and no timed window can be served by the
//    ~24 MiB system level cache.  Every configuration is additionally run with
//    `resident=1`, which points all calls at the same 9 experts (4.5 MiB,
//    cache-resident).  The resident cell is never a headline; it is reported
//    beside its non-resident twin as the explicit upper bound on what any
//    load-side saving could ever be worth.
//
// Build and run:
//   xcrun swiftc -O research/maple_frieren_r107f_t2d_probe.swift -o /tmp/r107f_probe
//   R107F_JSON_OUT=research/artifacts/maple-frieren-r107f/stage1/t2d-probe.json /tmp/r107f_probe

import Foundation
import Metal

// MARK: - environment

func intVal(_ n: String, _ d: Int) -> Int {
    guard let r = ProcessInfo.processInfo.environment[n], let v = Int(r) else { return d }
    return v
}
func intList(_ n: String, _ d: [Int]) -> [Int] {
    guard let r = ProcessInfo.processInfo.environment[n] else { return d }
    let p = r.split(separator: ",").compactMap { Int($0.trimmingCharacters(in: .whitespaces)) }
    precondition(!p.isEmpty, "\(n) set but unparseable: \(r)")
    return p
}

let rounds = intVal("R107F_ROUNDS", 61)
let discard = intVal("R107F_DISCARD", 6)
let focusRounds = intVal("R107F_FOCUS_ROUNDS", 201)
let focusDiscard = intVal("R107F_FOCUS_DISCARD", 10)
let bankExperts = intVal("R107F_EXPERTS", 640)
let scoredCalls = intVal("R107F_SCORED_CALLS", 39)
let callSweep = intList("R107F_CALLS", [1, 4, 16, 39, 64])
let jsonOut =
    ProcessInfo.processInfo.environment["R107F_JSON_OUT"]
    ?? "research/artifacts/maple-frieren-r107f/stage1/t2d-probe.json"

// MARK: - scored-kernel constants (Stage 0 reachability, LagunaConstants)

let inputWidth = 512  // moeIntermediateSize
let outputWidth = 2048  // hiddenSize
let routedExperts = 8  // numExpertsPerTok
let slotsPerTile = 9  // 8 routed + 1 shared
let packedRowBytes = 256
let scaleRowBytes = 16
let scalePatchBytes = 128
let packedExpertBytes = outputWidth * packedRowBytes  // 524_288
let scaleExpertBytes = outputWidth * scaleRowBytes  // 32_768
let valuesPerLane = 16
let maxCalls = max(callSweep.max()!, scoredCalls)
precondition(maxCalls * slotsPerTile <= bankExperts, "bank too small for \(maxCalls) calls")

let device = MTLCreateSystemDefaultDevice()!
let queue = device.makeCommandQueue()!

// MARK: - kernel template
//
// One template emits every arm, so arms differ only in compile-time constants.

enum ActMode: String {
    case narrow  // shipped: `actLoads` x vec<bfloat,4>, byte stride 32, width 8
    case wide  // WAL: 2 x uint4, byte stride 16, width 16, 32-byte aligned
    case none  // no activation load at all
}

struct Arm {
    let name: String
    let opsi: Int  // outputs_per_simd
    let subtiles: Int  // row subtiles per threadgroup (1 = shipped)
    let actMode: ActMode
    let actLoads: Int  // vec<bfloat,4> loads per lane when actMode == .narrow
    let badCoalCodes: Bool  // restride code loads to 32 bytes (positive control)
    let minArith: Bool  // strip NVFP4 unpack+dot, keep all loads and a simd op
    var simdgroups: Int { slotsPerTile * subtiles }
    var threadsPerTG: Int { simdgroups * 32 }
    var rowsPerTG: Int { opsi * subtiles }
    var tgPerCall: Int { outputWidth / rowsPerTG }
    var threadsPerCall: Int { tgPerCall * threadsPerTG }
    var actLoadsEff: Int {
        switch actMode {
        case .narrow: return actLoads
        case .wide: return 2
        case .none: return 0
        }
    }
    var actBytes: Int {
        switch actMode {
        case .narrow: return actLoads * 8
        case .wide: return 32
        case .none: return 0
        }
    }
    var bytesPerLane: Int { actBytes + opsi * 8 + opsi * 1 }
    var loadsPerLane: Int { actLoadsEff + opsi + opsi }
    var tgMemBytes: Int { simdgroups * opsi * 2 }
    // L1 line-touches per simdgroup per call, 128-byte lines.  A load of width
    // w at lane stride s touches ceil(32 * s / 128) lines when s >= w.
    var lineTouches: Int {
        let act: Int
        switch actMode {
        case .narrow: return actLoads * 8 + opsi * (badCoalCodes ? 8 : 2) + opsi * 1
        case .wide: act = 2 * 8  // width 16 at lane stride 32 spans 1024 bytes = 8 lines
        case .none: act = 0
        }
        return act + opsi * (badCoalCodes ? 8 : 2) + opsi * 1
    }
}

func arm(
    _ name: String, opsi: Int = 4, subtiles: Int = 1, actMode: ActMode = .narrow, actLoads: Int = 4,
    badCoalCodes: Bool = false, minArith: Bool = false
) -> Arm {
    Arm(
        name: name, opsi: opsi, subtiles: subtiles, actMode: actMode, actLoads: actLoads,
        badCoalCodes: badCoalCodes, minArith: minArith)
}

let arms: [Arm] = [
    arm("a0"),
    arm("a0_act2", actLoads: 2),
    arm("a0_act1", actLoads: 1),
    arm("a0_act0", actMode: .none),
    arm("a0_wide", actMode: .wide),
    arm("a0_badcoal", badCoalCodes: true),
    arm("a1", opsi: 8),
    arm("a1_wide", opsi: 8, actMode: .wide),
    arm("a2", subtiles: 2),
    arm("a3", opsi: 16),
    arm("a0_min", minArith: true),
    arm("a0_act0_min", actMode: .none, minArith: true),
]
let focusArms = ["a0", "a0_act0", "a0_wide", "a1", "a2"]

func activationBlock(_ a: Arm) -> String {
    var s = "vec<bfloat, 4> av[4];\n"
    switch a.actMode {
    case .none:
        s += """
        av[0] = vec<bfloat, 4>(bfloat(float(lane) * 0.01f), bfloat(1.0f), bfloat(0.5f), bfloat(0.25f));
        av[1] = av[0]; av[2] = av[0]; av[3] = av[0];
        """
    case .wide:
        s += """
        const device uint4* input_wide =
            (const device uint4*)(expert_input + lane * values_per_lane);
        const uint4 w0 = input_wide[0];
        const uint4 w1 = input_wide[1];
        av[0] = as_type<vec<bfloat, 4>>(uint2(w0.x, w0.y));
        av[1] = as_type<vec<bfloat, 4>>(uint2(w0.z, w0.w));
        av[2] = as_type<vec<bfloat, 4>>(uint2(w1.x, w1.y));
        av[3] = as_type<vec<bfloat, 4>>(uint2(w1.z, w1.w));
        """
    case .narrow:
        for i in 0..<4 {
            if i < a.actLoads {
                s += "av[\(i)] = input_vectors[\(i)];\n"
            } else {
                s += "av[\(i)] = av[\(i % a.actLoads)];\n"
            }
        }
    }
    s += """

    for (uint i = 0; i < 4; ++i) {
        input_values[4 * i] = av[i][0];
        input_values[4 * i + 1] = av[i][1];
        input_values[4 * i + 2] = av[i][2];
        input_values[4 * i + 3] = av[i][3];
    }
    """
    return s
}

func kernelSource(_ a: Arm) -> String {
    // Both variants end in a cross-lane reduction, which cannot legally be
    // sunk into the divergent `lane == 0` epilogue, so no arm can have its
    // loads dead-code eliminated.
    let dot =
        a.minArith
        ? """
        result[row] = simd_sum(
            float(row_codes[row].x ^ row_codes[row].y) + float(row_sb[row])
            + input_values[row & 15u]);
        """
        : """
        result[row] = laguna_nvfp4_qdot_codes_16(
            row_codes[row], input_values, laguna_nvfp4_scale(row_sb[row]));
        result[row] = simd_sum(result[row]);
        """
    let codeAddr =
        a.badCoalCodes
        ? "expert_weight + first_row * packed_row_bytes + lane * 32u + row * 8u"
        : "expert_weight + output_row * packed_row_bytes + lane * 8u"
    let inputVectors =
        a.actMode == .narrow
        ? """
        const device vec<bfloat, 4>* input_vectors =
            (const device vec<bfloat, 4>*)(expert_input + lane * values_per_lane);
        """ : ""
    return """
    [[kernel]] void \(a.name)(
      const device bfloat16_t* routed_activated [[buffer(0)]],
      const device uint32_t* routed_down_weight [[buffer(1)]],
      const device uint8_t* routed_down_scales [[buffer(2)]],
      const device uint32_t* indices [[buffer(3)]],
      const device float* router_weights [[buffer(4)]],
      const device bfloat16_t* shared_activated [[buffer(5)]],
      const device uint32_t* shared_down_weight [[buffer(6)]],
      const device uint8_t* shared_down_scales [[buffer(7)]],
      const device bfloat16_t* residual [[buffer(8)]],
      device bfloat16_t* output [[buffer(9)]],
      uint2 tgid [[threadgroup_position_in_grid]],
      uint sg [[simdgroup_index_in_threadgroup]],
      uint lane [[thread_index_in_simdgroup]]) {
    constexpr uint input_width = \(inputWidth);
    constexpr uint output_width = \(outputWidth);
    constexpr uint routed_experts = \(routedExperts);
    constexpr uint shared_slot = \(routedExperts);
    constexpr uint outputs_per_simd = \(a.opsi);
    constexpr uint subtiles = \(a.subtiles);
    constexpr uint values_per_lane = \(valuesPerLane);
    constexpr uint packed_row_bytes = \(packedRowBytes);
    constexpr uint scale_patch_bytes = \(scalePatchBytes);
    constexpr uint scale_row_bytes = \(scaleRowBytes);
    constexpr uint packed_expert_bytes = \(packedExpertBytes);
    constexpr uint scale_expert_bytes = \(scaleExpertBytes);

    uint tile = tgid.x;
    uint call = tgid.y;
    uint slot = sg % \(slotsPerTile)u;
    uint subtile = sg / \(slotsPerTile)u;
    uint first_row = tile * (outputs_per_simd * subtiles) + subtile * outputs_per_simd;
    bool is_shared = slot == shared_slot;
    uint expert = uint(indices[call * \(slotsPerTile)u + slot]);

    const device bfloat* expert_input = is_shared
        ? shared_activated + call * input_width
        : routed_activated + (call * routed_experts + slot) * input_width;
    const device uint8_t* expert_weight = is_shared
        ? (const device uint8_t*)shared_down_weight + expert * packed_expert_bytes
        : (const device uint8_t*)routed_down_weight + expert * packed_expert_bytes;
    const device uint8_t* expert_scales = is_shared
        ? shared_down_scales + scale_patch_bytes + expert * scale_expert_bytes
        : routed_down_scales + scale_patch_bytes + expert * scale_expert_bytes;
    uint scale_lane = (lane >> 1);

    thread float input_values[values_per_lane];
    \(inputVectors)
    \(activationBlock(a))

    thread float result[outputs_per_simd] = {0.0f};
    uint2 row_codes[outputs_per_simd];
    uint8_t row_sb[outputs_per_simd];
    for (uint row = 0; row < outputs_per_simd; ++row) {
        uint output_row = first_row + row;
        row_codes[row] = *(const device uint2*)(\(codeAddr));
        const device uint8_t* scale =
            expert_scales + output_row * scale_row_bytes + scale_lane;
        row_sb[row] = scale[0];
    }
    for (uint row = 0; row < outputs_per_simd; ++row) {
        \(dot)
    }

    threadgroup bfloat down_outputs[(routed_experts + 1) * outputs_per_simd * subtiles];
    if (lane == 0) {
        for (uint row = 0; row < outputs_per_simd; ++row) {
            down_outputs[sg * outputs_per_simd + row] = bfloat(result[row] * 4194304.0f);
        }
    }
    threadgroup_barrier(mem_flags::mem_threadgroup);

    if (slot == 0 && lane < outputs_per_simd) {
        bfloat routed_total = bfloat(0);
        for (uint routed_slot = 0; routed_slot < routed_experts; ++routed_slot) {
            bfloat route_weight = bfloat(router_weights[call * routed_experts + routed_slot]);
            bfloat product = bfloat(
                down_outputs[(subtile * \(slotsPerTile)u + routed_slot) * outputs_per_simd + lane]
                    * route_weight);
            routed_total = bfloat(product + routed_total);
        }
        bfloat routed = bfloat(routed_total * bfloat(2.5f));
        bfloat shared =
            down_outputs[(subtile * \(slotsPerTile)u + shared_slot) * outputs_per_simd + lane];
        bfloat r2 = bfloat(routed + shared);
        uint o = call * output_width + first_row + lane;
        output[o] = bfloat(residual[o] + r2);
    }}
    """
}

// Load-issue ceiling.  Same load *shapes* as the scored kernel (two 8 byte
// loads and one 1 byte load per unit of work) against a 16 KiB resident
// buffer, so DRAM cannot be the limit and the result is a loads/second
// ceiling for this host under this instruction mix.  `empty_probe` prices a
// bare dispatch of the scored geometry.
let auxSource = """
[[kernel]] void issue_probe(
  const device uint32_t* small [[buffer(0)]],
  const device uint32_t* iters [[buffer(1)]],
  device uint32_t* out [[buffer(2)]],
  uint gid [[thread_position_in_grid]]) {
    const device uint8_t* b = (const device uint8_t*)small;
    uint n = iters[0];
    uint acc = 0u;
    uint base = (gid * 8u) & 0x3FF0u;
    for (uint i = 0; i < n; ++i) {
        uint o0 = (base + i * 64u) & 0x3FF0u;
        uint o1 = (base + i * 64u + 32u) & 0x3FF0u;
        uint2 a = *(const device uint2*)(b + o0);
        uint2 c = *(const device uint2*)(b + o1);
        uint8_t s = b[(base + i * 7u) & 0x3FFFu];
        acc ^= a.x ^ a.y ^ c.x ^ c.y ^ uint(s);
    }
    if (acc == 0xFFFFFFFFu) { out[gid & 0xFFFFu] = acc; }
}

[[kernel]] void stream_read(
  const device uint4* src [[buffer(0)]],
  const device uint32_t* nu4 [[buffer(1)]],
  const device uint32_t* gsz [[buffer(2)]],
  device uint4* out [[buffer(3)]],
  uint gid [[thread_position_in_grid]]) {
    uint n = nu4[0];
    uint g = gsz[0];
    uint4 acc = uint4(0u);
    for (uint i = gid; i < n; i += g) { acc ^= src[i]; }
    if (acc.x == 0xFFFFFFFFu) { out[gid] = acc; }
}

[[kernel]] void empty_probe(
  device uint32_t* out [[buffer(0)]],
  uint gid [[thread_position_in_grid]]) {
    if (gid == 0xFFFFFFFFu) { out[0] = gid; }
}
"""

let preamble = """
#include <metal_stdlib>
using namespace metal;
typedef bfloat bfloat16_t;

static inline float laguna_nvfp4_scale(uint8_t bits) {
    ushort raw = ushort(uint(bits) << 7);
    return float(as_type<half>(raw));
}

static inline float laguna_nvfp4_qdot_codes_16(
    uint2 codes, const thread float* input, float scale) {
    float accum;
    {
        const uint c = codes.x;
        const uint xe = c & 0x0F0F0F0Fu;
        const uint ge = xe | (xe << 3);
        const uint yo = c & 0xF0F0F0F0u;
        const uint go = yo | (yo >> 3);
        const uint p0 = (ge << 9) & 0x8E008E00u;
        const uint p1 = (go << 8) & 0x8E008E00u;
        const uint p2 = (ge << 1) & 0x8E008E00u;
        const uint p3 = go & 0x8E008E00u;
        const float2 v04 = float2(as_type<half2>(p0));
        const float2 v15 = float2(as_type<half2>(p1));
        const float2 v26 = float2(as_type<half2>(p2));
        const float2 v37 = float2(as_type<half2>(p3));
        accum = (input[0] * v04.x + input[1] * v15.x + input[2] * v26.x + input[3] * v37.x);
        accum += (input[4] * v04.y + input[5] * v15.y + input[6] * v26.y + input[7] * v37.y);
    }
    {
        const uint c = codes.y;
        const uint xe = c & 0x0F0F0F0Fu;
        const uint ge = xe | (xe << 3);
        const uint yo = c & 0xF0F0F0F0u;
        const uint go = yo | (yo >> 3);
        const uint p0 = (ge << 9) & 0x8E008E00u;
        const uint p1 = (go << 8) & 0x8E008E00u;
        const uint p2 = (ge << 1) & 0x8E008E00u;
        const uint p3 = go & 0x8E008E00u;
        const float2 v04 = float2(as_type<half2>(p0));
        const float2 v15 = float2(as_type<half2>(p1));
        const float2 v26 = float2(as_type<half2>(p2));
        const float2 v37 = float2(as_type<half2>(p3));
        accum += (input[8] * v04.x + input[9] * v15.x + input[10] * v26.x + input[11] * v37.x);
        accum += (input[12] * v04.y + input[13] * v15.y + input[14] * v26.y + input[15] * v37.y);
    }
    return scale * accum;
}
"""

let msl = ([preamble, auxSource] + arms.map(kernelSource)).joined(separator: "\n")

let opts = MTLCompileOptions()
let lib: MTLLibrary
do {
    lib = try device.makeLibrary(source: msl, options: opts)
} catch {
    FileHandle.standardError.write("MSL compile failed: \(error)\n".data(using: .utf8)!)
    exit(2)
}

struct Pipe {
    let pso: MTLComputePipelineState
    let maxThreads: Int
    let tgMem: Int
}
func makePipe(_ name: String) -> Pipe {
    let fn = lib.makeFunction(name: name)!
    let pso = try! device.makeComputePipelineState(function: fn)
    return Pipe(
        pso: pso, maxThreads: pso.maxTotalThreadsPerThreadgroup,
        tgMem: pso.staticThreadgroupMemoryLength)
}
var pipes: [String: Pipe] = [:]
for a in arms { pipes[a.name] = makePipe(a.name) }
let issuePipe = makePipe("issue_probe")
let streamPipe = makePipe("stream_read")
let emptyPipe = makePipe("empty_probe")

// MARK: - buffers

func fill(_ buf: MTLBuffer, seed: UInt64) {
    let n = buf.length / 8
    let p = buf.contents().bindMemory(to: UInt64.self, capacity: n)
    var x = seed
    for i in 0..<n {
        x = x &* 6_364_136_223_846_793_005 &+ 1_442_695_040_888_963_407
        p[i] = x
    }
}

let codesBytes = bankExperts * packedExpertBytes
let scalesBytes = scalePatchBytes + bankExperts * scaleExpertBytes
let codes = device.makeBuffer(length: codesBytes, options: .storageModeShared)!
let scales = device.makeBuffer(length: scalesBytes, options: .storageModeShared)!
fill(codes, seed: 0x9E37_79B9_7F4A_7C15)
fill(scales, seed: 0xBF58_476D_1CE4_E5B9)

// Fixed permutation of the bank: expert(call, slot) = perm[call * 9 + slot].
// With maxCalls * 9 <= bankExperts every (call, slot) reads a distinct expert,
// so unique bytes == issued DRAM bytes for every value of `calls`.
var perm = Array(0..<UInt32(bankExperts))
do {
    var state: UInt64 = 0xDEAD_BEEF_CAFE_F00D
    var i = bankExperts - 1
    while i > 0 {
        state = state &* 6_364_136_223_846_793_005 &+ 1_442_695_040_888_963_407
        let j = Int((state >> 33) % UInt64(i + 1))
        perm.swapAt(i, j)
        i -= 1
    }
}
// Two index tables, so residency is chosen entirely on the host and the kernel
// keeps exactly one `indices` load per lane, as the scored kernel does.
var coldTable: [UInt32] = []
var residentTable: [UInt32] = []
for call in 0..<maxCalls {
    for slot in 0..<slotsPerTile {
        coldTable.append(perm[call * slotsPerTile + slot])
        residentTable.append(perm[slot])
    }
}
let coldIdx = device.makeBuffer(
    bytes: coldTable, length: coldTable.count * 4, options: .storageModeShared)!
let residentIdx = device.makeBuffer(
    bytes: residentTable, length: residentTable.count * 4, options: .storageModeShared)!

let routedAct = device.makeBuffer(
    length: maxCalls * routedExperts * inputWidth * 2, options: .storageModeShared)!
let sharedAct = device.makeBuffer(
    length: maxCalls * inputWidth * 2, options: .storageModeShared)!
let residual = device.makeBuffer(
    length: maxCalls * outputWidth * 2, options: .storageModeShared)!
let output = device.makeBuffer(
    length: maxCalls * outputWidth * 2, options: .storageModeShared)!
let routerW = device.makeBuffer(
    length: maxCalls * routedExperts * 4, options: .storageModeShared)!
fill(routedAct, seed: 0x94D0_49BB_1331_11EB)
fill(sharedAct, seed: 0x2545_F491_4F6C_DD1D)
fill(residual, seed: 0x1234_5678_9ABC_DEF0)
do {
    let n = maxCalls * routedExperts
    let p = routerW.contents().bindMemory(to: Float.self, capacity: n)
    for i in 0..<n { p[i] = 0.125 + Float(i % 7) * 0.01 }
}
let small = device.makeBuffer(length: 16384, options: .storageModeShared)!
fill(small, seed: 0x0BAD_C0DE_F00D_1234)
let sink = device.makeBuffer(length: 1 << 22, options: .storageModeShared)!

func makeConst(_ v: UInt32) -> MTLBuffer {
    let b = device.makeBuffer(length: 4, options: .storageModeShared)!
    b.contents().bindMemory(to: UInt32.self, capacity: 1)[0] = v
    return b
}

// MARK: - cells

struct Cell {
    let arm: Arm
    let calls: Int
    let resident: Bool
    let split: Bool
    var key: String {
        "\(arm.name)|c\(calls)|\(resident ? "res" : "cold")|\(split ? "split" : "fused")"
    }
}

func bind(_ enc: MTLComputeCommandEncoder, _ c: Cell, callOffset k: Int) {
    enc.setBuffer(routedAct, offset: k * routedExperts * inputWidth * 2, index: 0)
    enc.setBuffer(codes, offset: 0, index: 1)
    enc.setBuffer(scales, offset: 0, index: 2)
    enc.setBuffer(c.resident ? residentIdx : coldIdx, offset: k * slotsPerTile * 4, index: 3)
    enc.setBuffer(routerW, offset: k * routedExperts * 4, index: 4)
    enc.setBuffer(sharedAct, offset: k * inputWidth * 2, index: 5)
    enc.setBuffer(codes, offset: 0, index: 6)
    enc.setBuffer(scales, offset: 0, index: 7)
    enc.setBuffer(residual, offset: k * outputWidth * 2, index: 8)
    enc.setBuffer(output, offset: k * outputWidth * 2, index: 9)
}

/// One timed command buffer for a cell.  `split` encodes `calls` serialised
/// dispatches, matching the 39 per-layer entries the scored kernel pays; `fused`
/// encodes one dispatch whose height is `calls`.
func timeCell(_ c: Cell) -> Double {
    let a = c.arm
    let cb = queue.makeCommandBuffer()!
    let enc = cb.makeComputeCommandEncoder()!
    enc.setComputePipelineState(pipes[a.name]!.pso)
    let tpt = MTLSize(width: a.threadsPerTG, height: 1, depth: 1)
    if c.split {
        for k in 0..<c.calls {
            bind(enc, c, callOffset: k)
            enc.dispatchThreadgroups(
                MTLSize(width: a.tgPerCall, height: 1, depth: 1), threadsPerThreadgroup: tpt)
        }
    } else {
        bind(enc, c, callOffset: 0)
        enc.dispatchThreadgroups(
            MTLSize(width: a.tgPerCall, height: c.calls, depth: 1), threadsPerThreadgroup: tpt)
    }
    enc.endEncoding()
    cb.commit()
    cb.waitUntilCompleted()
    return (cb.gpuEndTime - cb.gpuStartTime) * 1e6
}

var cells: [Cell] = []
for a in arms {
    for resident in [false, true] {
        for split in [true, false] {
            cells.append(Cell(arm: a, calls: scoredCalls, resident: resident, split: split))
        }
    }
}
for a in arms where a.name == "a0" || a.name == "a1" {
    for calls in callSweep where calls != scoredCalls {
        for split in [true, false] {
            cells.append(Cell(arm: a, calls: calls, resident: false, split: split))
        }
    }
}
for c in cells {
    precondition(
        pipes[c.arm.name]!.maxThreads >= c.arm.threadsPerTG,
        "arm \(c.arm.name) requests \(c.arm.threadsPerTG) threads, driver caps at "
            + "\(pipes[c.arm.name]!.maxThreads)")
}

/// Times every cell once per round, reversing cell order on odd rounds, so a
/// monotone drift in host state cannot be absorbed into an arm effect.
func runInterleaved(_ cs: [Cell], rounds: Int, discard: Int) -> [String: [Double]] {
    var out: [String: [Double]] = [:]
    for c in cs { out[c.key] = [] }
    for r in 0..<(rounds + discard) {
        let order = r % 2 == 0 ? cs : cs.reversed().map { $0 }
        for c in order {
            let us = timeCell(c)
            if r >= discard { out[c.key]!.append(us) }
        }
    }
    return out
}

// MARK: - statistics

struct Stat {
    let n: Int
    let med: Double
    let mad: Double
    let p05: Double
    let p95: Double
    let mean: Double
    let sd: Double
    let ciLo: Double
    let ciHi: Double
}

func pct(_ s: [Double], _ q: Double) -> Double {
    let i = Int((Double(s.count - 1) * q).rounded())
    return s[max(0, min(s.count - 1, i))]
}

/// Median with the notched-boxplot 95 % interval, med +/- 1.58 * IQR / sqrt(n).
func stat(_ raw: [Double]) -> Stat {
    let s = raw.sorted()
    let n = s.count
    let med = n % 2 == 1 ? s[n / 2] : 0.5 * (s[n / 2 - 1] + s[n / 2])
    let mad = s.map { abs($0 - med) }.sorted()[n / 2]
    let mean = raw.reduce(0, +) / Double(n)
    let varr = raw.reduce(0.0) { $0 + ($1 - mean) * ($1 - mean) } / Double(max(n - 1, 1))
    let iqr = pct(s, 0.75) - pct(s, 0.25)
    let half = 1.58 * iqr / Double(n).squareRoot()
    return Stat(
        n: n, med: med, mad: mad, p05: pct(s, 0.05), p95: pct(s, 0.95), mean: mean,
        sd: varr.squareRoot(), ciLo: med - half, ciHi: med + half)
}

// MARK: - run

func jstr(_ s: String) -> String { "\"\(s)\"" }
func jnum(_ d: Double) -> String { String(format: "%.6f", d) }
var recs: [String] = []

let uniqueBytesPerCall =
    slotsPerTile * (packedExpertBytes + scaleExpertBytes) + slotsPerTile * inputWidth * 2
    + outputWidth * 2 * 2
precondition(
    slotsPerTile * (packedExpertBytes + scaleExpertBytes) == 5_013_504,
    "weight byte model drifted")
precondition(uniqueBytesPerCall == 5_030_912, "unique byte model drifted: \(uniqueBytesPerCall)")

let grid = runInterleaved(cells, rounds: rounds, discard: discard)
let focusCells = cells.filter {
    $0.calls == scoredCalls && !$0.resident && $0.split && focusArms.contains($0.arm.name)
}
let focus = runInterleaved(focusCells, rounds: focusRounds, discard: focusDiscard)

func emit(_ cs: [Cell], _ data: [String: [Double]], block: String) {
    print("")
    print(
        "== \(block)  n=\(data[cs[0].key]!.count) ==============================================")
    print(
        "arm          mode   res  calls   us_med   us/call   d_vs_a0  ci_lo   ci_hi   GB/s  "
            + "lines/sg")
    for c in cs {
        let a = c.arm
        let st = stat(data[c.key]!)
        let perCall = st.med / Double(c.calls)
        let uniq = c.resident ? uniqueBytesPerCall : uniqueBytesPerCall * c.calls
        let dramGBs = Double(uniq) / (st.med * 1e-6) / 1e9
        let baseKey =
            Cell(arm: arms[0], calls: c.calls, resident: c.resident, split: c.split).key
        var pairJSON = ""
        var dTxt = "      -"
        var loTxt = "      -"
        var hiTxt = "      -"
        if let base = data[baseKey], a.name != "a0", base.count == st.n {
            let mine = data[c.key]!
            let diff = (0..<st.n).map { (mine[$0] - base[$0]) / Double(c.calls) }
            let ds = stat(diff)
            pairJSON =
                ",\"paired_vs_a0_us_per_call\":\(jnum(ds.med)),"
                + "\"paired_ci_lo\":\(jnum(ds.ciLo)),\"paired_ci_hi\":\(jnum(ds.ciHi)),"
                + "\"paired_mad\":\(jnum(ds.mad))"
            dTxt = String(format: "%7.3f", ds.med)
            loTxt = String(format: "%7.3f", ds.ciLo)
            hiTxt = String(format: "%7.3f", ds.ciHi)
        }
        let p = pipes[a.name]!
        recs.append(
            """
            {"kind":"arm","block":\(jstr(block)),"arm":\(jstr(a.name)),"opsi":\(a.opsi),\
            "subtiles":\(a.subtiles),"act_mode":\(jstr(a.actMode.rawValue)),\
            "act_loads":\(a.actLoadsEff),"bad_coal_codes":\(a.badCoalCodes),\
            "min_arith":\(a.minArith),"calls":\(c.calls),"resident":\(c.resident),\
            "split":\(c.split),"threads_per_tg":\(a.threadsPerTG),"tg_per_call":\(a.tgPerCall),\
            "threads_per_call":\(a.threadsPerCall),"bytes_per_lane":\(a.bytesPerLane),\
            "loads_per_lane":\(a.loadsPerLane),"line_touches_per_sg":\(a.lineTouches),\
            "issued_bytes_per_call":\(a.threadsPerCall * a.bytesPerLane),\
            "loads_per_call":\(a.threadsPerCall * a.loadsPerLane),\
            "unique_bytes_per_call":\(uniqueBytesPerCall),"pso_max_threads":\(p.maxThreads),\
            "pso_tg_mem":\(p.tgMem),"predicted_tg_mem":\(a.tgMemBytes),"n":\(st.n),\
            "us_med":\(jnum(st.med)),"us_mad":\(jnum(st.mad)),"us_p05":\(jnum(st.p05)),\
            "us_p95":\(jnum(st.p95)),"us_mean":\(jnum(st.mean)),"us_sd":\(jnum(st.sd)),\
            "us_ci_lo":\(jnum(st.ciLo)),"us_ci_hi":\(jnum(st.ciHi)),\
            "us_per_call":\(jnum(perCall)),"dram_gb_s":\(jnum(dramGBs))\(pairJSON),\
            "samples":[\(data[c.key]!.map(jnum).joined(separator: ","))]}
            """)
        print(
            String(
                format: "%-12s %-6s %-4s %5d %8.2f %9.3f %@ %@ %@ %6.1f %6d",
                (a.name as NSString).utf8String!,
                ((c.split ? "split" : "fused") as NSString).utf8String!,
                ((c.resident ? "res" : "cold") as NSString).utf8String!, c.calls, st.med, perCall,
                dTxt, loTxt, hiTxt, dramGBs, a.lineTouches))
    }
}

for split in [true, false] {
    for resident in [false, true] {
        emit(
            cells.filter {
                $0.calls == scoredCalls && $0.resident == resident && $0.split == split
            }, grid, block: "grid calls=\(scoredCalls) \(split ? "split" : "fused") "
                + (resident ? "resident" : "cold"))
    }
}
emit(
    cells.filter { $0.calls != scoredCalls }, grid,
    block: "call sweep cold")
emit(focusCells, focus, block: "focus split cold calls=\(scoredCalls)")

// Per-dispatch launch cost at the scored geometry: N serialised empty
// dispatches of `tg` threadgroups x 288 threads in one serial encoder.
func timeEmpty(dispatches: Int, tg: Int) -> Double {
    let cb = queue.makeCommandBuffer()!
    let enc = cb.makeComputeCommandEncoder()!
    enc.setComputePipelineState(emptyPipe.pso)
    enc.setBuffer(sink, offset: 0, index: 0)
    for _ in 0..<dispatches {
        enc.dispatchThreadgroups(
            MTLSize(width: tg, height: 1, depth: 1),
            threadsPerThreadgroup: MTLSize(width: 288, height: 1, depth: 1))
    }
    enc.endEncoding()
    cb.commit()
    cb.waitUntilCompleted()
    return (cb.gpuEndTime - cb.gpuStartTime) * 1e6
}

print("")
print("== dispatch launch cost (empty kernel, 288 threads/tg) ==")
for tg in [128, 256, 512] {
    for n in [1, 39, 156] {
        var raw: [Double] = []
        for r in 0..<(rounds + discard) {
            let us = timeEmpty(dispatches: n, tg: tg)
            if r >= discard { raw.append(us) }
        }
        let st = stat(raw)
        recs.append(
            """
            {"kind":"empty","tg":\(tg),"dispatches":\(n),"n":\(st.n),\
            "us_med":\(jnum(st.med)),"us_mad":\(jnum(st.mad)),"us_ci_lo":\(jnum(st.ciLo)),\
            "us_ci_hi":\(jnum(st.ciHi)),"us_per_dispatch":\(jnum(st.med / Double(n))),\
            "samples":[\(raw.map(jnum).joined(separator: ","))]}
            """)
        print(
            String(
                format: "empty     tg=%-4d n=%-4d %8.2f us  %7.3f us/dispatch", tg, n, st.med,
                st.med / Double(n)))
    }
}

print("")
print("== load-issue ceiling and stream ceiling ==")
for threads in [147456, 589824] {
    for iters in [16, 64] {
        let cI = makeConst(UInt32(iters))
        var raw: [Double] = []
        for r in 0..<(rounds + discard) {
            let cb = queue.makeCommandBuffer()!
            let enc = cb.makeComputeCommandEncoder()!
            enc.setComputePipelineState(issuePipe.pso)
            enc.setBuffer(small, offset: 0, index: 0)
            enc.setBuffer(cI, offset: 0, index: 1)
            enc.setBuffer(sink, offset: 0, index: 2)
            enc.dispatchThreadgroups(
                MTLSize(width: threads / 288, height: 1, depth: 1),
                threadsPerThreadgroup: MTLSize(width: 288, height: 1, depth: 1))
            enc.endEncoding()
            cb.commit()
            cb.waitUntilCompleted()
            if r >= discard { raw.append((cb.gpuEndTime - cb.gpuStartTime) * 1e6) }
        }
        let st = stat(raw)
        let lps = Double(threads * iters * 3) / (st.med * 1e-6)
        recs.append(
            """
            {"kind":"issue","threads":\(threads),"iters":\(iters),"n":\(st.n),\
            "us_med":\(jnum(st.med)),"us_mad":\(jnum(st.mad)),"loads_per_s":\(jnum(lps)),\
            "samples":[\(raw.map(jnum).joined(separator: ","))]}
            """)
        print(
            String(
                format: "issue     thr=%-7d it=%-3d %8.2f us  %6.2f Gload/s", threads, iters,
                st.med, lps / 1e9))
    }
}
for bytes in [1 << 26, 1 << 28] {
    let nu4 = makeConst(UInt32(bytes / 16))
    let threads = 294912
    let gsz = makeConst(UInt32(threads))
    var raw: [Double] = []
    for r in 0..<(rounds + discard) {
        let cb = queue.makeCommandBuffer()!
        let enc = cb.makeComputeCommandEncoder()!
        enc.setComputePipelineState(streamPipe.pso)
        enc.setBuffer(codes, offset: 0, index: 0)
        enc.setBuffer(nu4, offset: 0, index: 1)
        enc.setBuffer(gsz, offset: 0, index: 2)
        enc.setBuffer(sink, offset: 0, index: 3)
        enc.dispatchThreadgroups(
            MTLSize(width: threads / 256, height: 1, depth: 1),
            threadsPerThreadgroup: MTLSize(width: 256, height: 1, depth: 1))
        enc.endEncoding()
        cb.commit()
        cb.waitUntilCompleted()
        if r >= discard { raw.append((cb.gpuEndTime - cb.gpuStartTime) * 1e6) }
    }
    let st = stat(raw)
    let gbs = Double(bytes) / (st.med * 1e-6) / 1e9
    recs.append(
        """
        {"kind":"stream","bytes":\(bytes),"threads":\(threads),"n":\(st.n),\
        "us_med":\(jnum(st.med)),"us_mad":\(jnum(st.mad)),"gb_s":\(jnum(gbs)),\
        "samples":[\(raw.map(jnum).joined(separator: ","))]}
        """)
    print(
        String(
            format: "stream    MiB=%-5d thr=%-7d %8.2f us  %7.1f GB/s", bytes >> 20, threads,
            st.med, gbs))
}

let header = """
{"probe":"maple-frieren-r107f-stage1-t2d","revision":2,\
"device":\(jstr(device.name)),"rounds":\(rounds),"discard":\(discard),\
"focus_rounds":\(focusRounds),"focus_discard":\(focusDiscard),\
"scored_calls":\(scoredCalls),"bank_experts":\(bankExperts),"bank_code_bytes":\(codesBytes),\
"bank_scale_bytes":\(scalesBytes),"unique_bytes_per_call":\(uniqueBytesPerCall),\
"call_sweep":[\(callSweep.map(String.init).joined(separator: ","))],\
"records":[\(recs.joined(separator: ",\n"))]}
"""
try? FileManager.default.createDirectory(
    atPath: (jsonOut as NSString).deletingLastPathComponent, withIntermediateDirectories: true)
try! header.write(toFile: jsonOut, atomically: true, encoding: .utf8)
print("wrote \(jsonOut)")
