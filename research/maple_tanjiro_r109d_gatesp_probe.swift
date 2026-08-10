// Research-only host probe (not part of the submission surface).
//
// R109-D: threadgroup occupancy of the affine gate/softplus kernel
// `laguna_gate_sp_h{64,48}_v1` (`lagunaGateSoftplusSource` in
// `Sources/MLXFastModel/LagunaRuntimeModel.swift`).
//
// The shipped geometry is R=4 rows per simdgroup and NS=2 simdgroups per
// threadgroup, so a threadgroup retires NS*R = 8 output heads and the dispatch
// uses `heads/8` threadgroups: 8 for the 64-head sliding banks and 6 for the
// 48-head full-attention banks.  Both numbers are far below the 20 GPU cores of
// this host (and the 40 of the ranked M5), so the kernel leaves most of the
// machine idle while every threadgroup streams its own rows from memory.
//
// The dose axis is therefore (R, NS): shrinking either one raises the
// threadgroup count without touching the per-row arithmetic.  A row is still
// accumulated by the same 32 lanes over the same eight k-blocks in the same
// order with the same scale/bias pair and the same 32-lane `simd_sum` tree, so
// every arm must be bitwise identical to the shipped geometry.  The probe
// enforces that with a hard gate before printing any timing.
//
// `input` is only 4 KiB and is re-read per row, so lowering R does not change
// the distinct byte footprint at all: this is a pure parallelism experiment.
//
// Regime matters for the sign of the result.  In situ each dispatch is preceded
// by a whole decoder layer of NVFP4 traffic, so the ~148 KiB working set is
// cold; a naive probe that re-dispatches one resident binding measures a
// cache-served cost instead.  `TANJIRO_DEFEAT_SLOTS` rotates the weight, scale
// and bias binding offsets per dispatch so a round's distinct footprint exceeds
// any plausible system level cache.  Both regimes are reported.
//
// Build and run:
//   xcrun swiftc -O research/maple_tanjiro_r109d_gatesp_probe.swift -o /tmp/tanjirogsp
//   /tmp/tanjirogsp                      # NULL control (shipped geometry twice)
//   TANJIRO_ARMS=4x2,2x2,1x2,1x1 /tmp/tanjirogsp
//
// Env:
//   TANJIRO_ARMS          RxNS list, first entry is the reference (default 4x2)
//   TANJIRO_HEADS         head-count ladder (default 64,48 — the two real banks)
//   TANJIRO_DEFEAT_SLOTS  binding slots rotated per dispatch (default 200)
//   TANJIRO_REPS          dispatches per timed round (default 200)
//   TANJIRO_ROUNDS        alternating paired rounds (default 21)

import Foundation
import Metal

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

func intList(_ name: String, _ fallback: [Int]) -> [Int] {
    guard let raw = ProcessInfo.processInfo.environment[name] else { return fallback }
    let v = raw.split(separator: ",").compactMap { Int($0) }
    return v.isEmpty ? fallback : v
}
func intVal(_ name: String, _ fallback: Int) -> Int {
    Int(ProcessInfo.processInfo.environment[name] ?? "") ?? fallback
}

/// Measured sequential-read peak for this host (rule 55 / PR #498).
let dramPeakGBs = 266.3
/// Published estimate for an M4-Pro-class system level cache; label only.
let slcEstimateBytes = 24 * 1024 * 1024

let hiddenSize = 2048  // LagunaConstants.hiddenSize
let groupSize = 32
let headsLadder = intList("TANJIRO_HEADS", [64, 48])
let maxHeads = headsLadder.max()!
let defeatSlots = max(intVal("TANJIRO_DEFEAT_SLOTS", 200), 1)
let reps = intVal("TANJIRO_REPS", 200)
let rounds = intVal("TANJIRO_ROUNDS", 21)

// MARK: - kernel source
//
// Byte-identical to `lagunaGateSoftplusSource` when R=4 and NS=2; the only
// edits are the two `constexpr` values and the matching length of the `r`
// initializer list.  `heads` never appears in the shipped body (it is encoded
// in the kernel name and the grid), so the arms differ only in geometry.

func gateSoftplusBody(R: Int, NS: Int) -> String {
    let zeros = Array(repeating: "0.0f", count: R).joined(separator: ",")
    return """
constexpr uint K=\(hiddenSize),GS=32,V=8;
constexpr uint BK=V*32,R=\(R),NS=\(NS),KG=K/GS,SS=GS/V;
uint tile=threadgroup_position_in_grid.x;
uint sg=simdgroup_index_in_threadgroup;
uint lane=thread_index_in_simdgroup;
uint orow=tile*(NS*R)+sg*R;
const device uint8_t* ws=(const device uint8_t*)packed_codes+orow*K+lane*V;
const device bfloat* sc=scales+orow*KG+lane/SS;
const device bfloat* bs=biases+orow*KG+lane/SS;
thread float x[V];
thread float r[R]={\(zeros)};
uint col=lane*V;
for(uint k=0;k<K;k+=BK){
    float sum=0.0f;
    for(uint i=0;i<V;++i){
        x[i]=float(input[col+i]);
        sum+=x[i];
    }
    for(uint row=0;row<R;++row){
        const device uint8_t* wl=ws+row*K;
        float s=float(sc[row*KG]),b=float(bs[row*KG]),a=0.0f;
        for(uint i=0;i<V;++i) a+=x[i]*wl[i];
        r[row]+=s*a+sum*b;
    }
    ws+=BK; sc+=BK/GS; bs+=BK/GS; col+=BK;
}
for(uint row=0;row<R;++row){
    r[row]=simd_sum(r[row]);
    if(lane==0){
        float l=float(bfloat(r[row]));
        float g;
        if(metal::isnan(l)) g=NAN;
        else {
            float hi=metal::max(l,0.0f);
            float lo=metal::min(l,0.0f);
            g=(metal::isinf(lo)||metal::isinf(hi))?hi:hi+log1p(metal::exp(lo-hi));
        }
        gate_values[orow+row]=bfloat(g);
    }
}
"""
}

/// The wrapper MLX generates around a `metalKernel` body: typed buffers in
/// input-then-output order plus the thread-position attributes the body reads.
let kernelName = "laguna_gate_sp_probe_v1"
func wrappedSource(R: Int, NS: Int) -> String {
    """
    #include <metal_stdlib>
    #include <metal_simdgroup>
    using namespace metal;
    typedef bfloat bfloat16_t;

    [[kernel]] void custom_kernel_\(kernelName)(
      const device bfloat16_t* input [[buffer(0)]],
      const device uint32_t* packed_codes [[buffer(1)]],
      const device bfloat16_t* scales [[buffer(2)]],
      const device bfloat16_t* biases [[buffer(3)]],
      device bfloat16_t* gate_values [[buffer(4)]],
      uint simdgroup_index_in_threadgroup [[simdgroup_index_in_threadgroup]],
      uint thread_index_in_simdgroup [[thread_index_in_simdgroup]],
      uint3 threadgroup_position_in_grid [[threadgroup_position_in_grid]]) {
    \(gateSoftplusBody(R: R, NS: NS))
    }
    """
}

// MARK: - buffers
//
// One slot holds a complete gate bank for the widest head count on the ladder,
// so rotating slots keeps the access pattern, alignment and instruction count
// bit-for-bit identical while moving every address.

func filled(_ bytes: Int, seed: UInt64) -> MTLBuffer {
    let buf = device.makeBuffer(length: bytes, options: .storageModeShared)!
    let words = bytes / 8
    let p = buf.contents().bindMemory(to: UInt64.self, capacity: words)
    var s = seed &* 0x9E37_79B9_7F4A_7C15 &+ 1
    for i in 0..<words {
        s ^= s << 13
        s ^= s >> 7
        s ^= s << 17
        p[i] = s
    }
    return buf
}

let codeSlotBytes = maxHeads * hiddenSize
let scaleSlotBytes = maxHeads * (hiddenSize / groupSize) * 2

let dInput = device.makeBuffer(length: hiddenSize * 2, options: .storageModeShared)!
do {
    let p = dInput.contents().bindMemory(to: UInt16.self, capacity: hiddenSize)
    var s: UInt32 = 0x1234_5678
    for i in 0..<hiddenSize {
        s = s &* 1_664_525 &+ 1_013_904_223
        // BF16 magnitudes near 1.0 with mixed signs: representative activations.
        p[i] = UInt16(0x3F00 | (s >> 24)) ^ UInt16((s >> 16) & 0x8000)
    }
}
let dCodes = filled(defeatSlots * codeSlotBytes, seed: 11)
// bf16 scales/biases in a benign exponent range: random 16-bit patterns would
// be dominated by Inf/NaN and would exercise the softplus fallback only.
func filledBF16(_ slots: Int, _ perSlot: Int, seed: UInt32, bias: UInt16) -> MTLBuffer {
    let count = slots * perSlot
    let buf = device.makeBuffer(length: count * 2, options: .storageModeShared)!
    let p = buf.contents().bindMemory(to: UInt16.self, capacity: count)
    var s = seed
    for i in 0..<count {
        s = s &* 1_664_525 &+ 1_013_904_223
        p[i] = (bias | UInt16((s >> 24) & 0x3F)) ^ UInt16((s >> 16) & 0x8000)
    }
    return buf
}
let scalesPerSlot = maxHeads * (hiddenSize / groupSize)
let dScales = filledBF16(defeatSlots, scalesPerSlot, seed: 0x2345_6789, bias: 0x3B00)
let dBiases = filledBF16(defeatSlots, scalesPerSlot, seed: 0x3456_789A, bias: 0x3A00)
let dGate = device.makeBuffer(length: maxHeads * 2, options: .storageModeShared)!

func bind(_ enc: MTLComputeCommandEncoder, slot: Int) {
    enc.setBuffer(dInput, offset: 0, index: 0)
    enc.setBuffer(dCodes, offset: slot * codeSlotBytes, index: 1)
    enc.setBuffer(dScales, offset: slot * scaleSlotBytes, index: 2)
    enc.setBuffer(dBiases, offset: slot * scaleSlotBytes, index: 3)
    enc.setBuffer(dGate, offset: 0, index: 4)
}

// MARK: - arms

struct Arm {
    let label: String
    let R: Int
    let NS: Int
    let pipe: MTLComputePipelineState
    var rowsPerTG: Int { NS * R }
    var threadsPerTG: Int { 32 * NS }
    func threadgroups(heads: Int) -> Int { heads / rowsPerTG }
}

func buildArm(_ spec: String) -> Arm {
    let parts = spec.lowercased().split(separator: "x").compactMap { Int($0) }
    precondition(parts.count == 2, "arm spec must be RxNS, got \(spec)")
    let (R, NS) = (parts[0], parts[1])
    let src = wrappedSource(R: R, NS: NS)
    let lib: MTLLibrary
    do {
        lib = try device.makeLibrary(source: src, options: nil)
    } catch {
        FileHandle.standardError.write("MSL compile failed for \(spec): \(error)\n".data(using: .utf8)!)
        exit(1)
    }
    let fn = lib.makeFunction(name: "custom_kernel_\(kernelName)")!
    let pipe = try! device.makeComputePipelineState(function: fn)
    precondition(
        pipe.maxTotalThreadsPerThreadgroup >= 32 * NS,
        "arm \(spec) wants \(32 * NS) threads but the pipeline caps at \(pipe.maxTotalThreadsPerThreadgroup)")
    return Arm(label: "R\(R)xNS\(NS)", R: R, NS: NS, pipe: pipe)
}

let armSpecs: [String] = {
    let raw = ProcessInfo.processInfo.environment["TANJIRO_ARMS"] ?? "4x2"
    return raw.split(separator: ",").map(String.init)
}()
let reference = buildArm(armSpecs[0])
let variants: [Arm] =
    armSpecs.count == 1
    ? [buildArm(armSpecs[0])].map { Arm(label: "NULL(\($0.label))", R: $0.R, NS: $0.NS, pipe: $0.pipe) }
    : armSpecs.dropFirst().map(buildArm)

for h in headsLadder {
    for a in [reference] + variants {
        precondition(
            h % a.rowsPerTG == 0,
            "heads=\(h) is not a multiple of \(a.rowsPerTG) rows/threadgroup for \(a.label)")
    }
}

print("=== device ===")
print("name                  \(device.name)")
print("architecture          \(device.architecture.name)")
print("gpu cores             \(cores)")
print("kernel                laguna_gate_sp (affine gate + softplus)")
print("mode                  \(armSpecs.count == 1 ? "NULL CONTROL" : "GEOMETRY LADDER")")
print("shipped geometry      R=4 NS=2  ->  8 rows/TG")

print("\n=== geometry and pipeline reflection ===")
print("  arm            rows/TG  thr/TG   TG@h64  TG@h48   tgMemB   maxThreads   execWidth")
for a in [reference] + variants {
    print(
        String(
            format: "  %-12@   %6d  %6d   %6d  %6d   %6d   %10d   %9d",
            a.label as NSString, a.rowsPerTG, a.threadsPerTG,
            a.threadgroups(heads: 64), a.threadgroups(heads: 48),
            a.pipe.staticThreadgroupMemoryLength, a.pipe.maxTotalThreadsPerThreadgroup,
            a.pipe.threadExecutionWidth))
}

// MARK: - dispatch

func dispatch(_ enc: MTLComputeCommandEncoder, _ a: Arm, heads: Int) {
    enc.dispatchThreadgroups(
        MTLSize(width: a.threadgroups(heads: heads), height: 1, depth: 1),
        threadsPerThreadgroup: MTLSize(width: a.threadsPerTG, height: 1, depth: 1))
}

// MARK: - output equivalence gate (hard)

func runOnce(_ a: Arm, heads: Int, slot: Int) -> [UInt8] {
    memset(dGate.contents(), 0xA5, dGate.length)
    let cb = queue.makeCommandBuffer()!
    let enc = cb.makeComputeCommandEncoder()!
    enc.setComputePipelineState(a.pipe)
    bind(enc, slot: slot)
    dispatch(enc, a, heads: heads)
    enc.endEncoding()
    cb.commit()
    cb.waitUntilCompleted()
    let p = dGate.contents().bindMemory(to: UInt8.self, capacity: heads * 2)
    return Array(UnsafeBufferPointer(start: p, count: heads * 2))
}

func differingBytes(_ a: [UInt8], _ b: [UInt8]) -> Int {
    zip(a, b).reduce(0) { $0 + ($1.0 == $1.1 ? 0 : 1) }
}

print("\n=== output equivalence gate (bitwise, vs shipped geometry) ===")
var equivalenceFailed = false
// Several slots so the gate covers many distinct weight/scale/bias patterns,
// not one lucky draw.
let gateSlots = [0, 1, min(7, defeatSlots - 1), defeatSlots - 1].reduce(into: [Int]()) {
    if !$0.contains($1) { $0.append($1) }
}
for heads in headsLadder {
    for slot in gateSlots {
        let ref = runOnce(reference, heads: heads, slot: slot)
        let nonPoison = ref.reduce(0) { $0 + ($1 == 0xA5 ? 0 : 1) }
        if nonPoison != heads * 2 {
            equivalenceFailed = true
            print("  heads=\(heads) slot=\(slot)  reference left \(heads * 2 - nonPoison) poison bytes")
        }
        let selfDiff = differingBytes(ref, runOnce(reference, heads: heads, slot: slot))
        if selfDiff != 0 { equivalenceFailed = true }
        for v in variants {
            let diff = differingBytes(ref, runOnce(v, heads: heads, slot: slot))
            if diff != 0 { equivalenceFailed = true }
            print(
                String(
                    format: "  heads=%3d slot=%4d  %-14@  diff %4d / %4d bytes   (ref self-diff %d)",
                    heads, slot, v.label as NSString, diff, heads * 2, selfDiff))
        }
        if variants.isEmpty {
            print("  heads=\(heads) slot=\(slot)  reference self-diff \(selfDiff)")
        }
    }
}
if equivalenceFailed {
    print("  VERDICT: MISMATCH — a geometry arm is not bitwise equivalent; refusing to time it.")
    exit(2)
}
print("  VERDICT: all geometry arms bitwise identical to the shipped R=4 NS=2 dispatch.")

// MARK: - byte model

/// Distinct bytes one dispatch touches: the whole gate bank (codes, scales,
/// biases), the shared input row, and the gate output.  Identical for every arm
/// — lowering R only re-reads the 4 KiB input row more times, which changes no
/// distinct byte.
func uniqueBytesPerDispatch(heads: Int) -> Int {
    heads * hiddenSize + 2 * heads * (hiddenSize / groupSize) * 2 + hiddenSize * 2 + heads * 2
}

// MARK: - paired timing

func perCallMicros(_ a: Arm, heads: Int, reps: Int) -> Double {
    let cb = queue.makeCommandBuffer()!
    let enc = cb.makeComputeCommandEncoder()!
    enc.setComputePipelineState(a.pipe)
    if defeatSlots == 1 { bind(enc, slot: 0) }
    for i in 0..<reps {
        if defeatSlots > 1 { bind(enc, slot: i % defeatSlots) }
        dispatch(enc, a, heads: heads)
    }
    enc.endEncoding()
    cb.commit()
    cb.waitUntilCompleted()
    return (cb.gpuEndTime - cb.gpuStartTime) * 1e6 / Double(reps)
}

for a in [reference] + variants { _ = perCallMicros(a, heads: headsLadder[0], reps: 20) }

print("\n=== memory regime ===")
print("  defeat slots          \(defeatSlots)\(defeatSlots == 1 ? "  (resident binding)" : "")")
print("  code buffer           \(dCodes.length) B")
print("  scale buffer          \(dScales.length) B each (scales, biases)")
print("  dram_peak_GB_s        \(dramPeakGBs)  (measured, rule 55)")
print("  slc_estimate_B        \(slcEstimateBytes)  (M4-Pro-class, label only)")
print("  heads   uniq_KiB/disp   uniq_MiB/round   ref_us   unique_GB_s   pct_peak   slc_fit   regime")
for heads in headsLadder {
    let uniqDisp = uniqueBytesPerDispatch(heads: heads)
    let uniqRound = uniqDisp * min(defeatSlots, reps)
    var t = Double.greatestFiniteMagnitude
    for _ in 0..<3 { t = min(t, perCallMicros(reference, heads: heads, reps: reps)) }
    let gbs = Double(uniqDisp) / (t * 1e-6) / 1e9
    let pct = 100.0 * gbs / dramPeakGBs
    let regime = gbs > dramPeakGBs
        ? "CACHE_SERVED" : (pct >= 80 ? "SATURATED" : (pct >= 40 ? "PARTIAL" : "UNSATURATED"))
    print(
        String(
            format: "  %5d   %12.2f   %14.2f   %6.2f   %11.1f   %8.1f   %7@   %@",
            heads, Double(uniqDisp) / 1024.0, Double(uniqRound) / 1048576.0, t, gbs, pct,
            (uniqRound <= slcEstimateBytes ? "yes" : "no") as NSString, regime as NSString))
}

print("\n=== paired per-call cost, \(rounds) alternating rounds of \(reps) dispatches ===")
print("delta = variant - reference within a round, so drift cancels. neg = faster.")
for v in variants {
    print("\n--- \(v.label)  vs reference \(reference.label) ---")
    print(
        "  heads    TG  TG/core    ref_min    var_min    d_mean     d_sd    d_min    d_max   spread    d%_ref    t_paired"
    )
    var perRound: [Int: [Double]] = [:]
    for heads in headsLadder {
        var refMin = Double.greatestFiniteMagnitude
        var varMin = Double.greatestFiniteMagnitude
        var deltas: [Double] = []
        for r in 0..<rounds {
            let rv: Double
            let vv: Double
            if r % 2 == 0 {
                rv = perCallMicros(reference, heads: heads, reps: reps)
                vv = perCallMicros(v, heads: heads, reps: reps)
            } else {
                vv = perCallMicros(v, heads: heads, reps: reps)
                rv = perCallMicros(reference, heads: heads, reps: reps)
            }
            refMin = min(refMin, rv)
            varMin = min(varMin, vv)
            deltas.append(vv - rv)
        }
        perRound[heads] = deltas
        let n = Double(deltas.count)
        let mean = deltas.reduce(0, +) / n
        let sd = (deltas.map { ($0 - mean) * ($0 - mean) }.reduce(0, +) / (n - 1)).squareRoot()
        let lo = deltas.min()!
        let hi = deltas.max()!
        let tPaired = sd > 0 ? mean / (sd / n.squareRoot()) : 0
        print(
            String(
                format:
                    "  %5d  %4d   %6.2f   %8.2f   %8.2f   %+7.3f   %6.3f   %+6.2f   %+6.2f   %6.2f   %+7.3f   %+9.2f",
                heads, v.threadgroups(heads: heads),
                Double(v.threadgroups(heads: heads)) / Double(max(cores, 1)),
                refMin, varMin, mean, sd, lo, hi, hi - lo,
                100.0 * mean / (refMin > 0 ? refMin : 1), tPaired))
    }
    for heads in headsLadder {
        let s = perRound[heads]!.map { String(format: "%+.2f", $0) }.joined(separator: " ")
        print("  per-round delta heads=\(heads): \(s)")
    }
}

// MARK: - decode-step projection
//
// Laguna has 30 sliding (64-head) and 10 full (48-head) attention layers, and
// the gate/softplus kernel runs once per layer per decode step.

print("\n=== decode-step projection (30 sliding h64 + 10 full h48) ===")
print("  arm            us/step   d_us/step_vs_ref")
func stepMicros(_ a: Arm) -> Double {
    var total = 0.0
    for (heads, layers) in [(64, 30), (48, 10)] {
        guard headsLadder.contains(heads) else { continue }
        var t = Double.greatestFiniteMagnitude
        for _ in 0..<5 { t = min(t, perCallMicros(a, heads: heads, reps: reps)) }
        total += t * Double(layers)
    }
    return total
}
let refStep = stepMicros(reference)
print(String(format: "  %-12@   %7.1f   %+16.1f", reference.label as NSString, refStep, 0.0))
for v in variants {
    let s = stepMicros(v)
    print(String(format: "  %-12@   %7.1f   %+16.1f", v.label as NSString, s, s - refStep))
}
print("  NOTE: min-of-5 per-dispatch cost x layer count. The in-situ kernel is")
print("  preceded by a full layer of NVFP4 traffic, so treat this as a bound and")
print("  confirm end to end with a paired ABBA decode run.")
