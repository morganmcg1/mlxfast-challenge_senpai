// Research-only host probe (not part of the submission surface).
//
// R109-C fork of `research/fern_r99_qmv_probe.swift`.  The only difference is
// the router-key buffer: it now carries eight trailing uint32 words at index
// 256..263 holding the top-8 winners in *goodness* order (ascending
// `(key, expert)`), which is the order the shipping tournament writes into
// `inds` and the order `laguna_router_top8_extract_round` returns slot by slot.
//
// That lets an arm read `router_keys[256u + expert_slot]` instead of running the
// extract-round prologue while touching the *same eight expert regions in the
// same slot order*, so the probe's bitwise output gate is a real equivalence
// check rather than a footprint comparison.  The base arm reads only words
// 0..255 and is therefore unchanged from the r99/r107g base.
//
// Paired A/B cost of the routed gate/up NVFP4 SwiGLU QMV kernel
// (`laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2`) against a
// threadgroup-count ladder, for round-99 arm E.
//
// Unlike `research/nezuko_r98_ab_kernel_probe.swift` this probe does not
// extract from Swift: the routed literal carries string interpolation, so
// `research/fern_r99_qmv_variants.py` emits fully resolved `.metal` files and
// this program only compiles and times them.
//
// Mandatory ordering: invoked with one file it runs the NULL control only
// (identical source in both slots).  The dose ladder needs the extra variant
// arguments, so a candidate number cannot be printed before the null spread is.
//
// Build and run:
//   xcrun swiftc -O research/fern_r99_qmv_probe.swift -o /tmp/fernqmv
//   /tmp/fernqmv research/artifacts/fern-r99/depth1_shipped.metal
//   /tmp/fernqmv research/artifacts/fern-r99/depth1_shipped.metal \
//     research/artifacts/fern-r99/tmpl_s1.metal ...

import Foundation
import Metal

let kernelName = "laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2"

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

// MARK: - regime instrumentation (round-100 P1.1 / P1.2)
//
// The r99 ladder re-dispatched an identical binding `reps` times inside one
// command buffer, so every dispatch after the first re-read the same ~8.5 MiB
// working set.  That fits an M4-Pro-class system level cache, which means the
// number the probe reported was a cache-resident cost, not the DRAM-fed cost the
// kernel pays inside a real decode step.  Defeat mode advances the weight and
// scale binding offsets per dispatch so the round's distinct footprint is large
// enough that the cache cannot hold it.
//
// `FERN_DEFEAT_SLOTS <= 1` reproduces the r99 resident binding exactly.
let defeatSlots = max(intVal("FERN_DEFEAT_SLOTS", 1), 1)

/// Measured sequential-read peak for this host (rule 55 / PR #498:
/// `t = 3.97 us + bytes / 266.3 GB/s`).  Apple's spec sheet says 273 GB/s.
let dramPeakGBs = 266.3
/// Published estimate for an M4-Pro-class system level cache.  Only used to
/// label a regime; every byte count is printed so a reader can re-derive it.
let slcEstimateBytes = 24 * 1024 * 1024

// MARK: - buffers

/// Deterministic filler so every arm sees the same weight codes, the same
/// `laguna_nvfp4_scale` fast-path branch pattern, and the same router winners.
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

let inputWidth = 2048
let scalePatchBytes = 128
let packedExpertBytes = 65536
let routedExperts = 8

let dInput = device.makeBuffer(length: inputWidth * 2, options: .storageModeShared)!
do {
    let p = dInput.contents().bindMemory(to: UInt16.self, capacity: inputWidth)
    var s: UInt32 = 0x1234_5678
    for i in 0..<inputWidth {
        s = s &* 1_664_525 &+ 1_013_904_223
        // BF16 magnitudes near 1.0 with mixed signs: representative activations.
        p[i] = UInt16(0x3F00 | (s >> 24)) ^ UInt16((s >> 16) & 0x8000)
    }
}
let fusedExpertBytes = 1024 * 1024
/// One slot step per buffer.  A slot advances the weight base by exactly one
/// expert stride, so slot `s` of expert `e` occupies the byte range expert
/// `e + s` would have used: the addresses are fresh but the access pattern,
/// alignment, and instruction count are bit-for-bit the resident pattern.
let weightSlotStride = fusedExpertBytes
let scaleSlotStride = packedExpertBytes

// 256 experts x 1 MiB, plus a MiB of slack so ladder points above the shipped
// 2048 threadgroups stay in bounds, plus one stride per defeat slot.
let dWeight = filled(257 * 1024 * 1024 + (defeatSlots - 1) * weightSlotStride, seed: 11)
let dScales = filled(
    scalePatchBytes + 256 * packedExpertBytes + 4096 + (defeatSlots - 1) * scaleSlotStride,
    seed: 23)
// 256 keys, then 8 trailing words with the winners in goodness order.  The
// first 1024 bytes are bit-identical to `filled(256 * 4, seed: 37)` because the
// generator is sequential, so the base arm sees the r99/r107g key set exactly.
let dKeys = filled(264 * 4, seed: 37)
let goodnessOrderedWinners: [Int] = {
    let keys = dKeys.contents().bindMemory(to: UInt32.self, capacity: 264)
    let order = (0..<256)
        .sorted { keys[$0] == keys[$1] ? $0 < $1 : keys[$0] < keys[$1] }
        .prefix(routedExperts)
    for (slot, expert) in order.enumerated() {
        keys[256 + slot] = UInt32(expert)
    }
    return Array(order)
}()
let dActivated = device.makeBuffer(length: routedExperts * 4096 * 2, options: .storageModeShared)!

func bind(_ enc: MTLComputeCommandEncoder, slot: Int = 0) {
    enc.setBuffer(dInput, offset: 0, index: 0)
    enc.setBuffer(dWeight, offset: slot * weightSlotStride, index: 1)
    enc.setBuffer(dScales, offset: slot * scaleSlotStride, index: 2)
    enc.setBuffer(dKeys, offset: 0, index: 3)
    enc.setBuffer(dActivated, offset: 0, index: 4)
}

// MARK: - pipelines

let paths = Array(CommandLine.arguments.dropFirst())
precondition(!paths.isEmpty, "usage: fernqmv <reference.metal> [variant.metal ...]")

struct Arm {
    let label: String
    let path: String
    let lines: Int
    let pipe: MTLComputePipelineState
}

func buildArm(_ path: String, label: String) -> Arm {
    let msl = try! String(contentsOfFile: path, encoding: .utf8)
    let lib = try! device.makeLibrary(source: msl, options: nil)
    let fn = lib.makeFunction(name: "custom_kernel_\(kernelName)")!
    let pipe = try! device.makeComputePipelineState(function: fn)
    return Arm(
        label: label, path: path, lines: msl.split(separator: "\n").count, pipe: pipe)
}

func stem(_ path: String) -> String {
    (path as NSString).lastPathComponent.replacingOccurrences(of: ".metal", with: "")
}

let reference = buildArm(paths[0], label: stem(paths[0]))
let variants: [Arm] =
    paths.count == 1
    ? [buildArm(paths[0], label: "NULL(\(stem(paths[0])))")]
    : paths.dropFirst().map { buildArm($0, label: stem($0)) }

print("=== device ===")
print("name                  \(device.name)")
print("architecture          \(device.architecture.name)")
print("gpu cores             \(cores)")
print("kernel                \(kernelName)")
print("mode                  \(paths.count == 1 ? "NULL CONTROL" : "DOSE LADDER")")

print("\n=== pipeline reflection (register/occupancy gate) ===")
print("  arm                          lines   tgMemB   maxTotalThreads   execWidth")
for a in [reference] + variants {
    print(
        String(
            format: "  %-26@   %5d   %6d   %15d   %9d",
            a.label as NSString, a.lines, a.pipe.staticThreadgroupMemoryLength,
            a.pipe.maxTotalThreadsPerThreadgroup, a.pipe.threadExecutionWidth))
}

// MARK: - byte model, parsed from the kernel source being timed
//
// Nothing here is hand-typed: every stride comes out of the `constexpr uint`
// declarations of the reference MSL, so if a variant changes a layout constant
// the byte model changes with it (or the parse fails loudly).

func parseConstexprUInts(_ msl: String) -> [String: Int] {
    var table: [String: Int] = [:]
    for rawLine in msl.split(separator: "\n") {
        let line = rawLine.trimmingCharacters(in: .whitespaces)
        guard line.hasPrefix("constexpr uint "), line.hasSuffix(";") else { continue }
        let body = line.dropFirst("constexpr uint ".count).dropLast()
        let halves = body.split(separator: "=", maxSplits: 1)
        guard halves.count == 2 else { continue }
        let name = halves[0].trimmingCharacters(in: .whitespaces)
        var product = 1
        var ok = true
        for term in halves[1].split(separator: "*") {
            let t = term.trimmingCharacters(in: .whitespaces)
            if let n = Int(t) {
                product *= n
            } else if let n = table[t] {
                product *= n
            } else {
                ok = false
            }
        }
        if ok { table[name] = product }
    }
    return table
}

let refMSL = try! String(contentsOfFile: paths[0], encoding: .utf8)
let K = parseConstexprUInts(refMSL)
func need(_ name: String) -> Int {
    guard let v = K[name] else {
        fatalError("byte model: could not parse `constexpr uint \(name)` from \(paths[0])")
    }
    return v
}
let kInputWidth = need("input_width")
let kOutputWidth = need("output_width")
let kRoutedExperts = need("routed_experts")
let kFusedRowBytes = need("fused_row_bytes")
let kFusedExpertBytes = need("fused_expert_bytes")
let kScalePatchBytes = need("scale_patch_bytes")
let kScaleTileBytes = need("scale_tile_bytes")
let kPackedExpertBytes = need("packed_expert_bytes")
precondition(
    kInputWidth == inputWidth && kRoutedExperts == routedExperts
        && kPackedExpertBytes == packedExpertBytes && kScalePatchBytes == scalePatchBytes
        && kFusedExpertBytes == fusedExpertBytes,
    "byte model: parsed kernel constants disagree with the host buffer layout")

/// Replicates the kernel's top-8 extraction on the host so the byte model names
/// the exact eight expert regions the GPU will touch.
///
/// Lane `L` holds candidate `e = L + 32*j` with ordinal `router_keys[e]`, and the
/// per-lane mask bit that a round sets is only set by the lane that owns the
/// winner.  Masking group `j` for that one lane therefore removes exactly the one
/// expert just chosen, so the eight rounds return the global eight smallest
/// experts under `(router_keys[e], e)`.
func routedWinners() -> [Int] {
    let keys = dKeys.contents().bindMemory(to: UInt32.self, capacity: 256)
    return (0..<256)
        .sorted { keys[$0] == keys[$1] ? $0 < $1 : keys[$0] < keys[$1] }
        .prefix(routedExperts)
        .sorted()
}

/// Distinct logical output rows a `tg`-threadgroup dispatch covers.
func rowsCovered(_ tg: Int) -> Int {
    precondition(tg % routedExperts == 0, "ladder points must be multiples of routed_experts")
    return (tg / routedExperts) * 2
}

struct Interval { var lo: Int; var hi: Int }
func unionBytes(_ raw: [Interval]) -> Int {
    let sorted = raw.sorted { $0.lo < $1.lo }
    var total = 0
    var cur: Interval? = nil
    for iv in sorted {
        if var c = cur, iv.lo <= c.hi {
            c.hi = max(c.hi, iv.hi)
            cur = c
        } else {
            if let c = cur { total += c.hi - c.lo }
            cur = iv
        }
    }
    if let c = cur { total += c.hi - c.lo }
    return total
}

let winners = routedWinners()

/// Bytes a single dispatch asks the memory system for.
func requestedBytesPerDispatch(_ tg: Int) -> Int {
    let rows = rowsCovered(tg)
    let weight = routedExperts * rows * 2 * kFusedRowBytes
    let scales = routedExperts * ((rows + 3) / 4) * kScaleTileBytes + kScalePatchBytes
    let writes = routedExperts * rows * 2
    return weight + scales + inputWidth * 2 + 256 * 4 + writes
}

/// Distinct bytes a whole round of `reps` dispatches touches, honouring the
/// defeat-mode slot rotation and any overlap it creates.
func uniqueBytesPerRound(_ tg: Int, reps: Int) -> Int {
    let rows = rowsCovered(tg)
    let slots = min(defeatSlots, reps)
    var wIvs: [Interval] = []
    var sIvs: [Interval] = []
    for s in 0..<slots {
        for e in winners {
            let wBase = s * weightSlotStride + e * kFusedExpertBytes
            wIvs.append(Interval(lo: wBase, hi: wBase + rows * 2 * kFusedRowBytes))
            let sBase = s * scaleSlotStride + kScalePatchBytes + e * kPackedExpertBytes
            sIvs.append(Interval(lo: sBase, hi: sBase + ((rows + 3) / 4) * kScaleTileBytes))
        }
    }
    let small = inputWidth * 2 + 256 * 4 + routedExperts * rows * 2 + kScalePatchBytes
    return unionBytes(wIvs) + unionBytes(sIvs) + small
}

// MARK: - output equivalence gate
//
// A restructured kernel that skips work would look fast, so timing means nothing
// until every arm is shown to write byte-identical results from identical inputs.
// The output buffer is poisoned before each run so regions the grid never touches
// compare equal by construction rather than by leftover state.

func runOnce(_ pipe: MTLComputePipelineState, tg: Int) -> [UInt8] {
    memset(dActivated.contents(), 0xA5, dActivated.length)
    let cb = queue.makeCommandBuffer()!
    let enc = cb.makeComputeCommandEncoder()!
    enc.setComputePipelineState(pipe)
    bind(enc)
    enc.dispatchThreadgroups(
        MTLSize(width: tg, height: 1, depth: 1),
        threadsPerThreadgroup: MTLSize(width: 64, height: 1, depth: 1))
    enc.endEncoding()
    cb.commit()
    cb.waitUntilCompleted()
    let p = dActivated.contents().bindMemory(to: UInt8.self, capacity: dActivated.length)
    return Array(UnsafeBufferPointer(start: p, count: dActivated.length))
}

func differingBytes(_ a: [UInt8], _ b: [UInt8]) -> Int {
    zip(a, b).reduce(0) { $0 + ($1.0 == $1.1 ? 0 : 1) }
}

print("\n=== output equivalence gate (bitwise, vs reference) ===")
var equivalenceFailed = false
for tg in [1024, 2048] {
    let ref = runOnce(reference.pipe, tg: tg)
    let written = ref.reduce(0) { $0 + ($1 == 0xA5 ? 0 : 1) }
    let selfDiff = differingBytes(ref, runOnce(reference.pipe, tg: tg))
    if selfDiff != 0 { equivalenceFailed = true }
    print(
        String(
            format: "  TG=%4d  %-26@  diff %6d / %6d bytes   (reference wrote %6d)",
            tg, "reference re-run" as NSString, selfDiff, ref.count, written))
    for a in variants {
        let diff = differingBytes(ref, runOnce(a.pipe, tg: tg))
        if diff != 0 { equivalenceFailed = true }
        print(
            String(
                format: "  TG=%4d  %-26@  diff %6d / %6d bytes",
                tg, a.label as NSString, diff, ref.count))
    }
}
print(
    equivalenceFailed
        ? "  VERDICT: MISMATCH — timing below is not a like-for-like comparison."
        : "  VERDICT: all arms bitwise identical to the reference.")


// MARK: - paired ladder

/// Serial dispatch: the `reps` dispatches in one command buffer do not overlap,
/// so GPU busy time over reps is the per-call cost.
func perCallMicros(_ pipe: MTLComputePipelineState, tg: Int, reps: Int) -> Double {
    let cb = queue.makeCommandBuffer()!
    let enc = cb.makeComputeCommandEncoder()!
    enc.setComputePipelineState(pipe)
    if defeatSlots == 1 { bind(enc) }
    for i in 0..<reps {
        if defeatSlots > 1 { bind(enc, slot: i % defeatSlots) }
        enc.dispatchThreadgroups(
            MTLSize(width: tg, height: 1, depth: 1),
            threadsPerThreadgroup: MTLSize(width: 64, height: 1, depth: 1))
    }
    enc.endEncoding()
    cb.commit()
    cb.waitUntilCompleted()
    return (cb.gpuEndTime - cb.gpuStartTime) * 1e6 / Double(reps)
}

// The shipped dispatch is 2048 threadgroups of 64 threads. On the ranked M5 Max
// (40 cores) that is 51.2 TG/core; the occupancy-matched point on a 20-core M4
// Pro is 1024 threadgroups. The ladder brackets it by 8x either way.
let ladder = intList("FERN_LADDER", [128, 256, 512, 1024, 2048])
let rounds = intVal("FERN_ROUNDS", 21)
let reps = intVal("FERN_REPS", 100)

// MARK: - regime block
//
// Printed before any A/B number so a reader can see which side of the roofline
// the measurement lives on before being shown a delta.  `achieved_GB_s` above
// `dram_peak_GB_s` is direct proof that the round was served from cache.
//
// `slc_fit` (capacity) and `regime` (bandwidth saturation) are deliberately
// separate columns: a working set can fit the SLC and still be served at DRAM
// rate, and the two facts license different conclusions.

for a in [reference] + variants { _ = perCallMicros(a.pipe, tg: 512, reps: 20) }
for tg in ladder { _ = perCallMicros(reference.pipe, tg: tg, reps: reps) }

print("\n=== memory regime (P1.1) ===")
print("  defeat slots          \(defeatSlots)\(defeatSlots == 1 ? "  (r99 resident binding)" : "")")
print("  weight buffer         \(dWeight.length) B")
print("  scale buffer          \(dScales.length) B")
print("  routed winners        \(winners)")
print("  winners (slot order)  \(goodnessOrderedWinners)")
print("  output_width          \(kOutputWidth)")
print("  dram_peak_GB_s        \(dramPeakGBs)  (measured, rule 55)")
print("  slc_estimate_B        \(slcEstimateBytes)  (M4-Pro-class, label only)")
print(
    "    TG   rows   uniq_MiB   req_MiB/round   amplif   ref_us   achieved_GB_s   pct_peak   unique_GB_s   slc_fit   regime"
)
for tg in ladder {
    let uniq = uniqueBytesPerRound(tg, reps: reps)
    let req = requestedBytesPerDispatch(tg) * reps
    var t = Double.greatestFiniteMagnitude
    for _ in 0..<3 { t = min(t, perCallMicros(reference.pipe, tg: tg, reps: reps)) }
    let roundSeconds = t * Double(reps) * 1e-6
    let achieved = Double(req) / roundSeconds / 1e9
    let unique = Double(uniq) / roundSeconds / 1e9
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
                "  %4d   %4d   %8.2f   %13.2f   %6.1f   %6.2f   %13.1f   %8.1f   %11.1f   %7@   %@",
            tg, rowsCovered(tg), Double(uniq) / 1048576.0, Double(req) / 1048576.0,
            Double(req) / Double(uniq), t, achieved, pctPeak, unique,
            (uniq <= slcEstimateBytes ? "yes" : "no") as NSString, regime as NSString))
}

print(
    "\n=== paired per-call cost, \(rounds) alternating rounds of \(reps) dispatches ==="
)
print("delta = variant - reference within a round, so drift cancels. neg = faster.")
print("spread = max-min of the per-round deltas.")

for v in variants {
    print("\n--- \(v.label)  vs reference \(reference.label) ---")
    print(
        "    TG  TG/core    ref_min    var_min    d_mean     d_sd    d_min    d_max   spread    d%_ref    t_paired"
    )
    var perRound: [Int: [Double]] = [:]
    for tg in ladder {
        var refMin = Double.greatestFiniteMagnitude
        var varMin = Double.greatestFiniteMagnitude
        var deltas: [Double] = []
        for r in 0..<rounds {
            let rv: Double
            let vv: Double
            if r % 2 == 0 {
                rv = perCallMicros(reference.pipe, tg: tg, reps: reps)
                vv = perCallMicros(v.pipe, tg: tg, reps: reps)
            } else {
                vv = perCallMicros(v.pipe, tg: tg, reps: reps)
                rv = perCallMicros(reference.pipe, tg: tg, reps: reps)
            }
            refMin = min(refMin, rv)
            varMin = min(varMin, vv)
            deltas.append(vv - rv)
        }
        perRound[tg] = deltas
        let n = Double(deltas.count)
        let mean = deltas.reduce(0, +) / n
        let sd = (deltas.map { ($0 - mean) * ($0 - mean) }.reduce(0, +) / (n - 1))
            .squareRoot()
        let lo = deltas.min()!
        let hi = deltas.max()!
        let tPaired = sd > 0 ? mean / (sd / n.squareRoot()) : 0
        print(
            String(
                format:
                    "  %4d   %6.2f   %8.2f   %8.2f   %+7.3f   %6.3f   %+6.2f   %+6.2f   %6.2f   %+7.3f   %+9.2f",
                tg, Double(tg) / Double(max(cores, 1)), refMin, varMin, mean, sd, lo,
                hi, hi - lo, 100.0 * mean / (refMin > 0 ? refMin : 1), tPaired))
    }
    for tg in ladder {
        let s = perRound[tg]!.map { String(format: "%+.2f", $0) }.joined(separator: " ")
        print("  per-round delta TG=\(tg): \(s)")
    }
}
