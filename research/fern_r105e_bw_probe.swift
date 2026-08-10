// Research-only host probe (not part of the submission surface).
//
// Round-105 arm E, part A3: measure the *pattern-specific* read ceiling of
// this M4 Pro, so that a family's achieved bandwidth can be scored against the
// ceiling its own access shape can actually reach rather than against the pure
// streaming number (266.3 GB/s, rule 80).
//
// A1's ledger divides bytes by a SPLIT=1 label.  Without A3 that ratio can
// only be compared with a streaming ceiling, which would silently charge every
// gather-shaped kernel for a ceiling it was never able to reach.  A3 supplies
// the correct denominator per pattern.
//
// Arms:
//
//   stream        pure grid-stride uint4 read.  Swept over threads per
//                 threadgroup, threadgroups per core, and per-thread loads in
//                 flight (ILP 1/2/4/8).  The ILP sweep is the direct test of
//                 explanation (P): if 64-thread threadgroups with one load in
//                 flight cannot saturate DRAM here, the same shape on a wider
//                 M5 will be further from its own peak for reasons that have
//                 nothing to do with the byte model.
//
//   stream_tg64   the same kernel pinned to 64 threads per threadgroup, the
//                 geometry the routed NVFP4 qmv family actually dispatches.
//
//   nvfp4_qmv     replica of the scored routed-expert qmv read pattern taken
//                 from the dumped MSL (lib_0082, /tmp/r105c/dump/a_base):
//                 64 threads per threadgroup = 2 simdgroups, each simdgroup
//                 owns one gate row and one up row, each lane reads a uint2
//                 of packed codes at (row*1024 + block*256 + lane*8) over four
//                 blocks, plus the per-lane-pair scale bytes, plus its share
//                 of a shared 4096 B bf16 activation row.  Eight expert slabs
//                 per call.  Run with and without the activation reads so the
//                 cache-served replay can be priced separately.
//
//   gather_slab   eight 1 MiB slabs selected out of a large bank and read
//                 contiguously.  Isolates slab-selection cost from the
//                 in-slab access shape used by nvfp4_qmv.
//
// Cold-data discipline: the expert bank is FERN_EXPERTS slabs and one timed
// dispatch consumes a permutation of the whole bank, so a timed window reads
// ~1.1 GB of unique data against a ~24 MiB system level cache.  No timed
// window can be cache-warm.  Writes are one float per simdgroup, disclosed in
// the output as `write_bytes` so the read figure can be corrected if wanted.
//
// Build and run:
//   xcrun swiftc -O research/fern_r105e_bw_probe.swift -o /tmp/fern105e \
//     && FERN_JSON_OUT=research/artifacts/fern-r105e/pattern-bandwidth.json /tmp/fern105e

import Foundation
import Metal

func intVal(_ n: String, _ d: Int) -> Int {
    guard let r = ProcessInfo.processInfo.environment[n], let v = Int(r) else { return d }
    return v
}
func dblVal(_ n: String, _ d: Double) -> Double {
    guard let r = ProcessInfo.processInfo.environment[n], let v = Double(r) else { return d }
    return v
}
func intList(_ n: String, _ d: [Int]) -> [Int] {
    guard let r = ProcessInfo.processInfo.environment[n] else { return d }
    let p = r.split(separator: ",").compactMap { Int($0.trimmingCharacters(in: .whitespaces)) }
    precondition(!p.isEmpty, "\(n) set but unparseable: \(r)")
    return p
}

let rounds = intVal("FERN_ROUNDS", 9)
let coreCount = intVal("FERN_CORES", 20)
/// Rule 80's M4 Pro streaming denominator.  Every pattern is reported both in
/// GB/s and as a fraction of this, so the ledger can use either.
let ref266 = dblVal("FERN_REF_GBS", 266.3)
let slcEstimateMiB = intVal("FERN_SLC_MIB", 24)
let jsonOut = ProcessInfo.processInfo.environment["FERN_JSON_OUT"]
    ?? "research/artifacts/fern-r105e/pattern-bandwidth.json"

// Scored-kernel constants, from the dumped MSL.
let inputWidth = 2048
let routedExperts = 8
let fusedExpertBytes = 1_048_576
let packedExpertBytes = 65_536
let simdgroupsPerCall = 4096
let actRowBytes = inputWidth * 2

let nExperts = intVal("FERN_EXPERTS", 1024)
/// One dispatch covers the whole bank exactly once: calls * 8 == nExperts.
let nCalls = nExperts / routedExperts

let device = MTLCreateSystemDefaultDevice()!
let queue = device.makeCommandQueue()!

let msl = """
#include <metal_stdlib>
using namespace metal;

kernel void seq_read(
    device const uint4 *src [[buffer(0)]],
    device uint4 *dst [[buffer(1)]],
    constant uint &n [[buffer(2)]],
    constant uint &gsz [[buffer(3)]],
    constant uint &sweeps [[buffer(4)]],
    constant uint &ilp [[buffer(5)]],
    uint gid [[thread_position_in_grid]]
) {
    uint4 acc = uint4(0u);
    for (uint s = 0; s < sweeps; ++s) {
        uint i = gid;
        uint span = gsz * ilp;
        while (i + span - gsz < n) {
            for (uint k = 0; k < ilp; ++k) { acc ^= src[i + k * gsz]; }
            i += span;
        }
        while (i < n) { acc ^= src[i]; i += gsz; }
    }
    dst[gid] = acc;
}

// Replica of the routed NVFP4 qmv read pattern.  `sgPerTG` is a compile-time
// style parameter passed as a constant so the same body can be dispatched at
// 64, 256 and 512 threads per threadgroup while covering an identical byte set.
kernel void nvfp4_qmv(
    device const uchar *codes [[buffer(0)]],
    device const uchar *scales [[buffer(1)]],
    device const uint *sel [[buffer(2)]],
    device const uchar *act [[buffer(3)]],
    device float *dst [[buffer(4)]],
    constant uint &sgPerTG [[buffer(5)]],
    constant uint &readAct [[buffer(6)]],
    uint tgid [[threadgroup_position_in_grid]],
    uint tid [[thread_index_in_threadgroup]]
) {
    const uint SG_PER_CALL = 4096u;
    const uint FUSED_EXPERT_BYTES = 1048576u;
    const uint PACKED_EXPERT_BYTES = 65536u;
    const uint FUSED_ROW_BYTES = 1024u;

    uint tgPerCall = SG_PER_CALL / sgPerTG;
    uint call = tgid / tgPerCall;
    uint localTG = tgid % tgPerCall;
    uint sg = tid / 32u;
    uint lane = tid % 32u;

    // Canonical simdgroup enumeration of the scored kernel: slot = (gs/2)%8,
    // logical_row = (gs/16)*2 + gs%2.  Holding it fixed keeps the byte set
    // identical as sgPerTG changes.
    uint gs = localTG * sgPerTG + sg;
    uint slot = (gs / 2u) % 8u;
    uint logical_row = (gs / 16u) * 2u + (gs % 2u);

    uint gate_row = (logical_row / 32u) * 64u + (logical_row % 32u);
    uint up_row = gate_row + 32u;

    uint e = sel[call * 8u + slot];
    device const uchar *ew = codes + (ulong)e * (ulong)FUSED_EXPERT_BYTES;
    device const uchar *es = scales + (ulong)e * (ulong)PACKED_EXPERT_BYTES
                           + (ulong)logical_row * 128u;
    device const uchar *arow = act + (ulong)call * 4096u;

    uint2 acc = uint2(0u);
    uint sacc = 0u;
    uint4 aacc = uint4(0u);
    for (uint blk = 0; blk < 4u; ++blk) {
        device const uint2 *gp = (device const uint2 *)
            (ew + gate_row * FUSED_ROW_BYTES + blk * 256u + lane * 8u);
        device const uint2 *up = (device const uint2 *)
            (ew + up_row * FUSED_ROW_BYTES + blk * 256u + lane * 8u);
        acc ^= *gp;
        acc ^= *up;
        // Lane pairs share a scale byte: 16 gate + 16 up bytes per block.
        sacc += (uint)es[blk * 32u + (lane >> 1)];
        sacc += (uint)es[blk * 32u + 16u + (lane >> 1)];
        if (readAct != 0u) {
            // 16 bf16 values per lane per block = 32 B = two uint4.
            device const uint4 *ap = (device const uint4 *)
                (arow + blk * 1024u + lane * 32u);
            aacc ^= ap[0];
            aacc ^= ap[1];
        }
    }
    uint v = acc.x ^ acc.y ^ sacc ^ aacc.x ^ aacc.y ^ aacc.z ^ aacc.w;
    if (lane == 0u) { dst[gs + call * SG_PER_CALL] = as_type<float>(v); }
}

// Eight 1 MiB slabs per call, read contiguously by the threadgroups assigned
// to that call.  Same byte volume as nvfp4_qmv codes, trivial access shape.
kernel void gather_slab(
    device const uint4 *codes [[buffer(0)]],
    device const uint *sel [[buffer(1)]],
    device uint4 *dst [[buffer(2)]],
    constant uint &tgPerCall [[buffer(3)]],
    uint tgid [[threadgroup_position_in_grid]],
    uint tid [[thread_index_in_threadgroup]],
    uint tgsz [[threads_per_threadgroup]],
    uint gid [[thread_position_in_grid]]
) {
    const uint U4_PER_SLAB = 65536u;  // 1 MiB / 16
    uint call = tgid / tgPerCall;
    uint localTG = tgid % tgPerCall;
    uint slot = localTG % 8u;
    uint chunk = localTG / 8u;
    uint nchunk = tgPerCall / 8u;
    uint e = sel[call * 8u + slot];
    device const uint4 *slab = codes + (ulong)e * (ulong)U4_PER_SLAB;
    uint4 acc = uint4(0u);
    uint per = U4_PER_SLAB / nchunk;
    for (uint i = chunk * per + tid; i < (chunk + 1u) * per; i += tgsz) { acc ^= slab[i]; }
    if (tid == 0u) { dst[tgid] = acc; }
    (void)gid;
}
"""

let lib = try! device.makeLibrary(source: msl, options: nil)
let seqPipe = try! device.makeComputePipelineState(function: lib.makeFunction(name: "seq_read")!)
let qmvPipe = try! device.makeComputePipelineState(function: lib.makeFunction(name: "nvfp4_qmv")!)
let slabPipe = try! device.makeComputePipelineState(
    function: lib.makeFunction(name: "gather_slab")!)

// MARK: - buffers

func fill(_ buf: MTLBuffer, seed: UInt64) {
    let n = buf.length / 8
    let p = buf.contents().bindMemory(to: UInt64.self, capacity: n)
    var x = seed
    for i in 0..<n {
        x = x &* 6364136223846793005 &+ 1442695040888963407
        p[i] = x
    }
}

let codesBytes = nExperts * fusedExpertBytes
let scalesBytes = nExperts * packedExpertBytes
let codes = device.makeBuffer(length: codesBytes, options: .storageModeShared)!
let scales = device.makeBuffer(length: scalesBytes, options: .storageModeShared)!
fill(codes, seed: 0x9E37_79B9_7F4A_7C15)
fill(scales, seed: 0xBF58_476D_1CE4_E5B9)

// Expert selection is a deterministic permutation of the whole bank, so the
// dispatch touches every slab exactly once: unique bytes == issued DRAM bytes.
var selection = Array(0..<UInt32(nExperts))
do {
    var state: UInt64 = 0xDEAD_BEEF_CAFE_F00D
    var i = nExperts - 1
    while i > 0 {
        state = state &* 6364136223846793005 &+ 1442695040888963407
        let j = Int((state >> 33) % UInt64(i + 1))
        selection.swapAt(i, j)
        i -= 1
    }
}
let sel = device.makeBuffer(bytes: selection, length: nExperts * 4, options: .storageModeShared)!
let act = device.makeBuffer(length: nCalls * actRowBytes, options: .storageModeShared)!
fill(act, seed: 0x94D0_49BB_1331_11EB)

let dstFloats = nCalls * simdgroupsPerCall
let dst = device.makeBuffer(length: max(dstFloats * 4, 1 << 24), options: .storageModeShared)!

/// Streaming source.  Reuses the codes bank so the host does not hold a third
/// gigabyte-scale allocation.
let streamU4 = codesBytes / 16

func makeConst(_ v: UInt32) -> MTLBuffer {
    let b = device.makeBuffer(length: 4, options: .storageModeShared)!
    b.contents().bindMemory(to: UInt32.self, capacity: 1)[0] = v
    return b
}

// MARK: - timing

func summarise(_ raw: [Double]) -> (med: Double, lo: Double, hi: Double) {
    let s = raw.sorted()
    return (s[s.count / 2], s.first!, s.last!)
}

func runTimed(_ body: (MTLComputeCommandEncoder) -> Void) -> (med: Double, lo: Double, hi: Double) {
    var out: [Double] = []
    for r in 0..<(rounds + 1) {
        let cb = queue.makeCommandBuffer()!
        let enc = cb.makeComputeCommandEncoder()!
        body(enc)
        enc.endEncoding()
        cb.commit()
        cb.waitUntilCompleted()
        if r > 0 { out.append((cb.gpuEndTime - cb.gpuStartTime) * 1e6) }
    }
    return summarise(out)
}

func timeSeq(tg: Int, tptg: Int, ilp: Int, u4: Int, sweeps: Int) -> (
    med: Double, lo: Double, hi: Double
) {
    let gsz = tg * tptg
    precondition(gsz * 16 <= dst.length, "grid \(gsz) exceeds dst capacity")
    let cN = makeConst(UInt32(u4))
    let cG = makeConst(UInt32(gsz))
    let cS = makeConst(UInt32(sweeps))
    let cI = makeConst(UInt32(ilp))
    return runTimed { enc in
        enc.setComputePipelineState(seqPipe)
        enc.setBuffer(codes, offset: 0, index: 0)
        enc.setBuffer(dst, offset: 0, index: 1)
        enc.setBuffer(cN, offset: 0, index: 2)
        enc.setBuffer(cG, offset: 0, index: 3)
        enc.setBuffer(cS, offset: 0, index: 4)
        enc.setBuffer(cI, offset: 0, index: 5)
        enc.dispatchThreadgroups(
            MTLSize(width: tg, height: 1, depth: 1),
            threadsPerThreadgroup: MTLSize(width: tptg, height: 1, depth: 1))
    }
}

func timeQmv(sgPerTG: Int, readAct: Bool) -> (med: Double, lo: Double, hi: Double) {
    let tgPerCall = simdgroupsPerCall / sgPerTG
    let tg = nCalls * tgPerCall
    let tptg = sgPerTG * 32
    let cS = makeConst(UInt32(sgPerTG))
    let cA = makeConst(readAct ? 1 : 0)
    return runTimed { enc in
        enc.setComputePipelineState(qmvPipe)
        enc.setBuffer(codes, offset: 0, index: 0)
        enc.setBuffer(scales, offset: 0, index: 1)
        enc.setBuffer(sel, offset: 0, index: 2)
        enc.setBuffer(act, offset: 0, index: 3)
        enc.setBuffer(dst, offset: 0, index: 4)
        enc.setBuffer(cS, offset: 0, index: 5)
        enc.setBuffer(cA, offset: 0, index: 6)
        enc.dispatchThreadgroups(
            MTLSize(width: tg, height: 1, depth: 1),
            threadsPerThreadgroup: MTLSize(width: tptg, height: 1, depth: 1))
    }
}

func timeSlab(tgPerCall: Int, tptg: Int) -> (med: Double, lo: Double, hi: Double) {
    let tg = nCalls * tgPerCall
    precondition(tg * 16 <= dst.length, "tg count exceeds dst capacity")
    let cT = makeConst(UInt32(tgPerCall))
    return runTimed { enc in
        enc.setComputePipelineState(slabPipe)
        enc.setBuffer(codes, offset: 0, index: 0)
        enc.setBuffer(sel, offset: 0, index: 1)
        enc.setBuffer(dst, offset: 0, index: 2)
        enc.setBuffer(cT, offset: 0, index: 3)
        enc.dispatchThreadgroups(
            MTLSize(width: tg, height: 1, depth: 1),
            threadsPerThreadgroup: MTLSize(width: tptg, height: 1, depth: 1))
    }
}

func gbps(_ bytes: Double, _ us: Double) -> Double { bytes / (us * 1e-6) / 1e9 }
func f(_ v: Double, _ d: Int = 2) -> String { String(format: "%.\(d)f", v) }

// MARK: - JSON accumulation

var patterns: [String] = []
func emit(
    _ name: String, _ fields: [(String, String)]
) {
    let body = fields.map { "\"\($0.0)\": \($0.1)" }.joined(separator: ", ")
    patterns.append("    {\"pattern\": \"\(name)\", \(body)}")
}
func num(_ v: Double, _ d: Int = 4) -> String { String(format: "%.\(d)f", v) }

print("# host: \(device.name), \(coreCount) GPU cores, rounds=\(rounds), ref=\(ref266) GB/s")
print("# expert bank: \(nExperts) slabs, \(nCalls) calls per dispatch")
print(
    "# unique bytes per qmv dispatch: "
        + "\(nExperts * (fusedExpertBytes + packedExpertBytes)) "
        + "(\(f(Double(nExperts * (fusedExpertBytes + packedExpertBytes)) / 1e9, 3)) GB) "
        + "vs SLC estimate \(slcEstimateMiB) MiB")

// MARK: - A. streaming geometry x loads-in-flight sweep

print("")
print("# arm=stream  working set = whole \(codesBytes / 1024 / 1024) MiB bank")
print("tptg\ttgPerCore\ttg\tgrid\tilp\tsweeps\tus_med\tGB_s\tpct_266_3")
var bestStream = (g: 0.0, tptg: 0, tgpc: 0, ilp: 0)
var tg64Best = (g: 0.0, tgpc: 0, ilp: 0)
let streamTPTG = intList("FERN_TPTG", [64, 128, 256, 512, 1024])
let streamTGPC = intList("FERN_TGPC", [1, 2, 4, 8])
let streamILP = intList("FERN_ILP", [1, 2, 4, 8])
let sweeps = 1
for tptg in streamTPTG {
    for tgpc in streamTGPC {
        let tg = coreCount * tgpc
        if tg * tptg * 16 > dst.length { continue }
        for ilp in streamILP {
            let t = timeSeq(tg: tg, tptg: tptg, ilp: ilp, u4: streamU4, sweeps: sweeps)
            let bytes = Double(codesBytes) * Double(sweeps)
            let g = gbps(bytes, t.med)
            print(
                "\(tptg)\t\(tgpc)\t\(tg)\t\(tg * tptg)\t\(ilp)\t\(sweeps)\t"
                    + "\(f(t.med))\t\(f(g))\t\(f(g / ref266 * 100, 1))")
            emit(
                "stream", [
                    ("threads_per_tg", "\(tptg)"), ("tg_per_core", "\(tgpc)"),
                    ("threadgroups", "\(tg)"), ("grid_threads", "\(tg * tptg)"),
                    ("loads_in_flight", "\(ilp)"), ("bytes_read", "\(codesBytes * sweeps)"),
                    ("write_bytes", "\(tg * tptg * 16)"), ("us_med", num(t.med)),
                    ("us_min", num(t.lo)), ("us_max", num(t.hi)), ("achieved_gbs", num(g)),
                    ("pct_of_266_3", num(g / ref266 * 100)),
                ])
            if g > bestStream.g { bestStream = (g, tptg, tgpc, ilp) }
            if tptg == 64 && g > tg64Best.g { tg64Best = (g, tgpc, ilp) }
        }
    }
}
let streamPeak = bestStream.g
print(
    "# stream peak = \(f(streamPeak)) GB/s at tptg=\(bestStream.tptg) tgPerCore=\(bestStream.tgpc) "
        + "ilp=\(bestStream.ilp)  (\(f(streamPeak / ref266 * 100, 1))% of \(ref266))")
print(
    "# stream_tg64 peak = \(f(tg64Best.g)) GB/s at tgPerCore=\(tg64Best.tgpc) ilp=\(tg64Best.ilp)  "
        + "(\(f(tg64Best.g / streamPeak * 100, 1))% of stream peak)")

// MARK: - B. NVFP4 qmv replica

print("")
print("# arm=nvfp4_qmv  \(nCalls) calls, 8 experts/call, permutation of the bank")
print("sgPerTG\ttptg\ttg\tread_act\tdram_B\tissued_B\tus_med\tdram_GB_s\tissued_GB_s\tpct_266_3")
let qmvDramBytes = Double(nExperts * (fusedExpertBytes + packedExpertBytes))
var qmvRef = 0.0
for sgPerTG in intList("FERN_QMV_SGPTG", [2, 8, 16]) {
    for readAct in [true, false] {
        let t = timeQmv(sgPerTG: sgPerTG, readAct: readAct)
        let tgPerCall = simdgroupsPerCall / sgPerTG
        let actIssued =
            readAct ? Double(nCalls * simdgroupsPerCall * actRowBytes) : 0.0
        let issued = qmvDramBytes + actIssued
        let gd = gbps(qmvDramBytes, t.med)
        let gi = gbps(issued, t.med)
        print(
            "\(sgPerTG)\t\(sgPerTG * 32)\t\(nCalls * tgPerCall)\t\(readAct ? 1 : 0)\t"
                + "\(f(qmvDramBytes / 1e6, 1))\t\(f(issued / 1e6, 1))\t"
                + "\(f(t.med))\t\(f(gd))\t\(f(gi))\t\(f(gd / ref266 * 100, 1))")
        emit(
            "nvfp4_qmv", [
                ("simdgroups_per_tg", "\(sgPerTG)"), ("threads_per_tg", "\(sgPerTG * 32)"),
                ("threadgroups", "\(nCalls * tgPerCall)"),
                ("reads_activation", readAct ? "true" : "false"),
                ("bytes_dram_unique", num(qmvDramBytes, 0)), ("bytes_issued", num(issued, 0)),
                ("write_bytes", "\(dstFloats * 4)"), ("us_med", num(t.med)),
                ("us_min", num(t.lo)), ("us_max", num(t.hi)),
                ("achieved_gbs", num(gd)), ("issued_gbs", num(gi)),
                ("pct_of_266_3", num(gd / ref266 * 100)),
                ("pct_of_stream_peak", num(gd / streamPeak * 100)),
            ])
        if sgPerTG == 2 && readAct { qmvRef = gd }
    }
}
print(
    "# faithful geometry (64 threads/TG, activation read) = \(f(qmvRef)) GB/s  "
        + "(\(f(qmvRef / ref266 * 100, 1))% of \(ref266), \(f(qmvRef / streamPeak * 100, 1))% of "
        + "stream peak)")

// MARK: - C. slab gather

print("")
print("# arm=gather_slab  8 x 1 MiB slabs per call")
print("tgPerCall\ttptg\ttg\tbytes\tus_med\tGB_s\tpct_266_3")
for tgPerCall in intList("FERN_SLAB_TGPC", [8, 32, 128]) {
    for tptg in intList("FERN_SLAB_TPTG", [64, 256]) {
        let tg = nCalls * tgPerCall
        let t = timeSlab(tgPerCall: tgPerCall, tptg: tptg)
        let bytes = Double(nExperts * fusedExpertBytes)
        let g = gbps(bytes, t.med)
        print(
            "\(tgPerCall)\t\(tptg)\t\(tg)\t\(f(bytes / 1e6, 1))\t\(f(t.med))\t\(f(g))\t"
                + "\(f(g / ref266 * 100, 1))")
        emit(
            "gather_slab", [
                ("tg_per_call", "\(tgPerCall)"), ("threads_per_tg", "\(tptg)"),
                ("threadgroups", "\(tg)"), ("bytes_dram_unique", num(bytes, 0)),
                ("write_bytes", "\(tg * 16)"), ("us_med", num(t.med)),
                ("us_min", num(t.lo)), ("us_max", num(t.hi)), ("achieved_gbs", num(g)),
                ("pct_of_266_3", num(g / ref266 * 100)),
                ("pct_of_stream_peak", num(g / streamPeak * 100)),
            ])
    }
}

// MARK: - JSON

do {
    let path = jsonOut
    let header = """
        {
          "probe": "fern_r105e_bw_probe.swift",
          "host": "\(device.name)",
          "gpu_cores": \(coreCount),
          "rounds": \(rounds),
          "reference_stream_gbs_rule80": \(ref266),
          "slc_estimate_mib": \(slcEstimateMiB),
          "expert_bank_slabs": \(nExperts),
          "calls_per_dispatch": \(nCalls),
          "unique_bytes_per_qmv_dispatch": \(nExperts * (fusedExpertBytes + packedExpertBytes)),
          "stream_peak_gbs": \(num(streamPeak)),
          "stream_peak_geometry": {"threads_per_tg": \(bestStream.tptg), \
        "tg_per_core": \(bestStream.tgpc), "loads_in_flight": \(bestStream.ilp)},
          "stream_tg64_peak_gbs": \(num(tg64Best.g)),
          "nvfp4_qmv_faithful_gbs": \(num(qmvRef)),
          "measurements": [
        """
    let text = header + "\n" + patterns.joined(separator: ",\n") + "\n  ]\n}\n"
    try! text.write(toFile: path, atomically: true, encoding: .utf8)
    print("")
    print("# wrote \(path)")
}
print("# done")
