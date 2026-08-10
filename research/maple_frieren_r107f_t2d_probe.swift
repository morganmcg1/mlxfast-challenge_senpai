// Research-only host probe (not part of the submission surface).
//
// Round-107 arm F, Stage 1.  Standalone, residency-defeated replica of the
// scored routed+shared NVFP4 down-residual kernel
// `laguna_routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6`, reconstructed
// from the MSL dumped off the live pipeline in Stage 0 and validated against it
// (identical driver triple maxThreads=1024 execWidth=32 tgMem=80).
//
// Question.  The in-situ anchor is 22.07 us/call, 5,013,504 unique DRAM bytes
// per call = 227.1 GB/s = 87.2 % of this host's measured 260.6 GB/s read
// ceiling.  Two very different models fit that number:
//
//   (D) DRAM-bound on unique bytes.  Then halving the activation *replay*
//       cannot help at all, because replay is served by cache.
//   (I) bound on issued load slots / L1 return bandwidth.  A0 issues
//       10,027,008 bytes and 1,769,472 loads per call, of which 47.06 % of the
//       bytes are the 512-fold replay of one 9,216 byte activation set.  Then
//       raising `outputs_per_simd` from 4 to 8 removes 16.67 % of the loads and
//       23.53 % of the issued bytes at zero change in unique DRAM bytes.
//
// The probe separates them without touching the scored runtime.  Its central
// cell is not the A1 arm but the *activation-load slope*: arms a0_act{4,2,1,0}
// hold threadgroup count, unique DRAM bytes, arithmetic and code/scale loads
// fixed and vary only how many of the four `vec<bfloat,4>` activation loads
// each lane issues.  Aggregate activation loads under A1 equal those of
// a0_act2, so d(T)/d(activation loads) measured at fixed geometry *predicts*
// A1 before any runtime edit exists.  a2 (18 simdgroups, two row subtiles) has
// A1's threadgroup count and A0's load census, so it separates "fewer
// threadgroups" from "fewer activation loads".  The `_noarith` pair prices the
// NVFP4 dot product itself.
//
// Residency discipline (rule 98.9).  One timed dispatch is `calls`
// back-to-back replicas of the scored call, each selecting 9 fresh experts out
// of a 320 MiB bank by a fixed permutation, so unique bytes == issued DRAM
// bytes and no timed window can be served by the ~24 MiB system level cache.
// Every configuration is additionally run with `resident=1`, which points all
// calls at the same 9 experts (4.5 MiB, cache-resident).  The resident cell is
// never a headline; it is reported beside its non-resident twin as the explicit
// upper bound on what any load-side saving could ever be worth.
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

let rounds = intVal("R107F_ROUNDS", 11)
let discard = intVal("R107F_DISCARD", 2)
let bankExperts = intVal("R107F_EXPERTS", 640)
let callSweep = intList("R107F_CALLS", [1, 2, 4, 8, 16, 39, 64])
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
let maxCalls = callSweep.max()!
precondition(maxCalls * slotsPerTile <= bankExperts, "bank too small for \(maxCalls) calls")

let device = MTLCreateSystemDefaultDevice()!
let queue = device.makeCommandQueue()!

// MARK: - kernel template
//
// One template emits every arm, so arms can differ only in the compile-time
// constants named in `Arm`.  `arith == false` strips the NVFP4 dot product and
// the epilogue reduction while keeping every load address identical, which
// prices arithmetic against the same memory traffic.

struct Arm {
    let name: String
    let opsi: Int  // outputs_per_simd
    let subtiles: Int  // row subtiles per threadgroup (1 = shipped)
    let actLoads: Int  // activation vec<bfloat,4> loads per lane (shipped 4)
    let arith: Bool
    var simdgroups: Int { slotsPerTile * subtiles }
    var threadsPerTG: Int { simdgroups * 32 }
    var rowsPerTG: Int { opsi * subtiles }
    var tgPerCall: Int { outputWidth / rowsPerTG }
    var threadsPerCall: Int { tgPerCall * threadsPerTG }
    var bytesPerLane: Int { actLoads * 8 + opsi * 8 + opsi * 1 }
    var loadsPerLane: Int { actLoads + opsi + opsi }
    var tgMemBytes: Int { simdgroups * opsi * 2 }
}

let arms: [Arm] = [
    Arm(name: "a0", opsi: 4, subtiles: 1, actLoads: 4, arith: true),
    Arm(name: "a0_act2", opsi: 4, subtiles: 1, actLoads: 2, arith: true),
    Arm(name: "a0_act1", opsi: 4, subtiles: 1, actLoads: 1, arith: true),
    Arm(name: "a0_act0", opsi: 4, subtiles: 1, actLoads: 0, arith: true),
    Arm(name: "a1", opsi: 8, subtiles: 1, actLoads: 4, arith: true),
    Arm(name: "a2", opsi: 4, subtiles: 2, actLoads: 4, arith: true),
    Arm(name: "a3", opsi: 16, subtiles: 1, actLoads: 4, arith: true),
    Arm(name: "a0_noarith", opsi: 4, subtiles: 1, actLoads: 4, arith: false),
    Arm(name: "a1_noarith", opsi: 8, subtiles: 1, actLoads: 4, arith: false),
]

func activationBlock(_ a: Arm) -> String {
    var s = "vec<bfloat, 4> av[4];\n"
    if a.actLoads == 0 {
        s += """
        av[0] = vec<bfloat, 4>(bfloat(float(lane) * 0.01f), bfloat(1.0f), bfloat(0.5f), bfloat(0.25f));
        av[1] = av[0]; av[2] = av[0]; av[3] = av[0];
        """
    } else {
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
    let dot =
        a.arith
        ? """
        result[row] = laguna_nvfp4_qdot_codes_16(
            row_codes[row], input_values, laguna_nvfp4_scale(row_sb[row]));
        result[row] = simd_sum(result[row]);
        """
        : """
        result[row] = float(row_codes[row].x ^ row_codes[row].y) + float(row_sb[row]);
        """
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
    const device vec<bfloat, 4>* input_vectors =
        (const device vec<bfloat, 4>*)(expert_input + lane * values_per_lane);
    \(activationBlock(a))

    thread float result[outputs_per_simd] = {0.0f};
    uint2 row_codes[outputs_per_simd];
    uint8_t row_sb[outputs_per_simd];
    for (uint row = 0; row < outputs_per_simd; ++row) {
        uint output_row = first_row + row;
        row_codes[row] = *(const device uint2*)(
            expert_weight + output_row * packed_row_bytes + lane * 8);
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
// ceiling for this host under this instruction mix.
let issueSource = """
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

let msl = ([preamble, issueSource] + arms.map(kernelSource)).joined(separator: "\n")

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


// MARK: - timing

func stats(_ raw: [Double]) -> (med: Double, lo: Double, hi: Double, mean: Double, sd: Double) {
    let s = raw.sorted()
    let mean = raw.reduce(0, +) / Double(raw.count)
    let varr = raw.reduce(0.0) { $0 + ($1 - mean) * ($1 - mean) } / Double(max(raw.count - 1, 1))
    return (s[s.count / 2], s.first!, s.last!, mean, varr.squareRoot())
}

func runTimed(_ body: (MTLComputeCommandEncoder) -> Void) -> [Double] {
    var out: [Double] = []
    for r in 0..<(rounds + discard) {
        let cb = queue.makeCommandBuffer()!
        let enc = cb.makeComputeCommandEncoder()!
        body(enc)
        enc.endEncoding()
        cb.commit()
        cb.waitUntilCompleted()
        if r >= discard { out.append((cb.gpuEndTime - cb.gpuStartTime) * 1e6) }
    }
    return out
}

func timeArm(_ a: Arm, calls: Int, resident: Bool) -> [Double] {
    let p = pipes[a.name]!
    precondition(
        p.maxThreads >= a.threadsPerTG,
        "arm \(a.name) requests \(a.threadsPerTG) threads but driver caps at \(p.maxThreads)")
    return runTimed { enc in
        enc.setComputePipelineState(p.pso)
        enc.setBuffer(routedAct, offset: 0, index: 0)
        enc.setBuffer(codes, offset: 0, index: 1)
        enc.setBuffer(scales, offset: 0, index: 2)
        enc.setBuffer(resident ? residentIdx : coldIdx, offset: 0, index: 3)
        enc.setBuffer(routerW, offset: 0, index: 4)
        enc.setBuffer(sharedAct, offset: 0, index: 5)
        enc.setBuffer(codes, offset: 0, index: 6)
        enc.setBuffer(scales, offset: 0, index: 7)
        enc.setBuffer(residual, offset: 0, index: 8)
        enc.setBuffer(output, offset: 0, index: 9)
        enc.dispatchThreadgroups(
            MTLSize(width: a.tgPerCall, height: calls, depth: 1),
            threadsPerThreadgroup: MTLSize(width: a.threadsPerTG, height: 1, depth: 1))
    }
}

func timeIssue(threads: Int, iters: Int) -> [Double] {
    let cI = makeConst(UInt32(iters))
    return runTimed { enc in
        enc.setComputePipelineState(issuePipe.pso)
        enc.setBuffer(small, offset: 0, index: 0)
        enc.setBuffer(cI, offset: 0, index: 1)
        enc.setBuffer(sink, offset: 0, index: 2)
        enc.dispatchThreadgroups(
            MTLSize(width: threads / 288, height: 1, depth: 1),
            threadsPerThreadgroup: MTLSize(width: 288, height: 1, depth: 1))
    }
}

func timeStream(bytes: Int, threads: Int) -> [Double] {
    let nu4 = bytes / 16
    let cN = makeConst(UInt32(nu4))
    let cG = makeConst(UInt32(threads))
    return runTimed { enc in
        enc.setComputePipelineState(streamPipe.pso)
        enc.setBuffer(codes, offset: 0, index: 0)
        enc.setBuffer(cN, offset: 0, index: 1)
        enc.setBuffer(cG, offset: 0, index: 2)
        enc.setBuffer(sink, offset: 0, index: 3)
        enc.dispatchThreadgroups(
            MTLSize(width: threads / 256, height: 1, depth: 1),
            threadsPerThreadgroup: MTLSize(width: 256, height: 1, depth: 1))
    }
}

// MARK: - run

func jstr(_ s: String) -> String { "\"\(s)\"" }
func jnum(_ d: Double) -> String { String(format: "%.6f", d) }
var recs: [String] = []

let uniqueBytesPerCall = slotsPerTile * (packedExpertBytes + scaleExpertBytes)
precondition(uniqueBytesPerCall == 5_013_504, "unique byte model drifted: \(uniqueBytesPerCall)")

for a in arms {
    let p = pipes[a.name]!
    let issuedPerCall = a.threadsPerCall * a.bytesPerLane
    let loadsPerCall = a.threadsPerCall * a.loadsPerLane
    for calls in callSweep {
        for resident in [false, true] {
            let raw = timeArm(a, calls: calls, resident: resident)
            let st = stats(raw)
            let perCall = st.med / Double(calls)
            let uniq = resident ? uniqueBytesPerCall : uniqueBytesPerCall * calls
            let dramGBs = Double(uniq) / (st.med * 1e-6) / 1e9
            let issuedGBs = Double(issuedPerCall * calls) / (st.med * 1e-6) / 1e9
            let loadsPerSec = Double(loadsPerCall * calls) / (st.med * 1e-6)
            recs.append(
                """
                {"kind":"arm","arm":\(jstr(a.name)),"opsi":\(a.opsi),"subtiles":\(a.subtiles),\
                "act_loads":\(a.actLoads),"arith":\(a.arith),"calls":\(calls),\
                "resident":\(resident),"threads_per_tg":\(a.threadsPerTG),\
                "tg_per_call":\(a.tgPerCall),"threads_per_call":\(a.threadsPerCall),\
                "bytes_per_lane":\(a.bytesPerLane),"loads_per_lane":\(a.loadsPerLane),\
                "issued_bytes_per_call":\(issuedPerCall),"loads_per_call":\(loadsPerCall),\
                "unique_bytes_per_call":\(uniqueBytesPerCall),\
                "pso_max_threads":\(p.maxThreads),"pso_tg_mem":\(p.tgMem),\
                "predicted_tg_mem":\(a.tgMemBytes),\
                "us_med":\(jnum(st.med)),"us_lo":\(jnum(st.lo)),"us_hi":\(jnum(st.hi)),\
                "us_mean":\(jnum(st.mean)),"us_sd":\(jnum(st.sd)),\
                "us_per_call":\(jnum(perCall)),"dram_gb_s":\(jnum(dramGBs)),\
                "issued_gb_s":\(jnum(issuedGBs)),"loads_per_s":\(jnum(loadsPerSec)),\
                "samples":[\(raw.map(jnum).joined(separator: ","))]}
                """)
            let tag = resident ? "resident" : "cold"
            print(
                String(
                    format: "%-11s calls=%-3d %-8s  %9.2f us  %8.3f us/call  %7.1f GB/s(dram) "
                        + "%7.1f GB/s(issued)  %6.2f Gload/s",
                    (a.name as NSString).utf8String!, calls, (tag as NSString).utf8String!,
                    st.med, perCall, dramGBs, issuedGBs, loadsPerSec / 1e9))
        }
    }
}

for threads in [36864, 73728, 147456, 294912, 589824] {
    for iters in [4, 16, 64] {
        let raw = timeIssue(threads: threads, iters: iters)
        let st = stats(raw)
        let loads = Double(threads * iters * 3)
        let lps = loads / (st.med * 1e-6)
        recs.append(
            """
            {"kind":"issue","threads":\(threads),"iters":\(iters),"loads":\(jnum(loads)),\
            "us_med":\(jnum(st.med)),"us_lo":\(jnum(st.lo)),"us_hi":\(jnum(st.hi)),\
            "loads_per_s":\(jnum(lps)),"samples":[\(raw.map(jnum).joined(separator: ","))]}
            """)
        print(
            String(
                format: "issue      thr=%-7d it=%-3d  %9.2f us  %6.2f Gload/s", threads, iters,
                st.med, lps / 1e9))
    }
}

for bytes in [1 << 26, 1 << 28] {
    for threads in [147456, 294912] {
        let raw = timeStream(bytes: bytes, threads: threads)
        let st = stats(raw)
        let gbs = Double(bytes) / (st.med * 1e-6) / 1e9
        recs.append(
            """
            {"kind":"stream","bytes":\(bytes),"threads":\(threads),"us_med":\(jnum(st.med)),\
            "gb_s":\(jnum(gbs)),"samples":[\(raw.map(jnum).joined(separator: ","))]}
            """)
        print(
            String(
                format: "stream     MiB=%-5d thr=%-7d %9.2f us  %7.1f GB/s", bytes >> 20, threads,
                st.med, gbs))
    }
}

let header = """
{"probe":"maple-frieren-r107f-stage1-t2d",\
"device":\(jstr(device.name)),"rounds":\(rounds),"discard":\(discard),\
"bank_experts":\(bankExperts),"bank_code_bytes":\(codesBytes),"bank_scale_bytes":\(scalesBytes),\
"call_sweep":[\(callSweep.map(String.init).joined(separator: ","))],\
"records":[\(recs.joined(separator: ",\n"))]}
"""
try? FileManager.default.createDirectory(
    atPath: (jsonOut as NSString).deletingLastPathComponent, withIntermediateDirectories: true)
try! header.write(toFile: jsonOut, atomically: true, encoding: .utf8)
print("wrote \(jsonOut)")
