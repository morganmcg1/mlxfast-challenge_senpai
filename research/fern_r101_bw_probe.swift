// Research-only host probe (not part of the submission surface).
//
// Round-101 arm A, part P2: *measure* this host's streaming read ceiling
// instead of assuming one.  Four numbers are in live use for the same M4 Pro
// quantity -- 273.0 GB/s (theoretical, r94 census denominator), 266.3 GB/s
// (hardcoded in research/fern_r100_attn_probe.swift:71), 260.6 GB/s
// (roofline fit, maple-fern-decode-marginal-cost-ledger.md:940-946) and
// 237.4 GB/s (the tanjiro pool differential run on M4 Pro).  Several published
// census rows sit above the first of those, which is what round 101 exists to
// resolve, so the denominator itself has to be measured on the same host and
// with a stated dispatch geometry.
//
// Three arms:
//
//   seq       pure grid-stride uint4 streaming read.  Autotuned over
//             (threadgroups-per-core, threads-per-threadgroup, per-thread ILP)
//             at one large working set, then swept across working sets from
//             below the system level cache to far above it.  The asymptote of
//             this sweep is the DRAM read ceiling; the small-working-set end
//             is the cache-served ceiling.  Reporting both is the point: a
//             single "peak" number cannot classify a kernel whose working set
//             is cache resident.
//
//   blk       block-shuffled read.  Each threadgroup walks a pseudo-random
//             permutation of contiguous FERN_BLOCK_KIB blocks.  This is the
//             access shape of a routed-expert gather (contiguous per expert,
//             scattered between experts) and bounds how much of the routed
//             family's gap to `seq` is gather cost rather than byte cost.
//
//   tanjiro   replicates the instrument geometry behind the 610 GB/s M5
//             constant (tanjiro-pr27-interim.md:1044-1105): a fixed 256 MiB
//             pool, timed at S and S+6 grid-stride sweeps, bandwidth taken
//             from the 6-sweep differential.  Running the *same* instrument
//             here is the only way to get a paired M4->M5 instrument ratio
//             rather than a ratio of two different instruments.
//
// Rule 77 (faithful dispatch geometry) is honoured by printing, for every
// timed configuration, the threadgroup count, threads per threadgroup, bytes
// read per timed command buffer and bytes written per timed command buffer.
//
// Rule 71 as amended is honoured by emitting `regime` (classified from
// achieved_GB_s alone) and `slc_fit` (classified from capacity alone) as two
// independent columns, so a residency claim can never be smuggled in through
// a bandwidth observation or vice versa.
//
// Build and run:
//   xcrun swiftc -O research/fern_r101_bw_probe.swift -o /tmp/fernbw && /tmp/fernbw

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

/// Working sets straddle the M4-Pro-class system level cache estimate (24 MiB)
/// and run to 40x it, so the DRAM asymptote is measured, not extrapolated.
let ladderMiB = intList(
    "FERN_LADDER_MIB",
    [2, 4, 8, 12, 16, 20, 24, 32, 48, 64, 96, 128, 192, 256, 384, 512, 768, 1024]
)
let rounds = intVal("FERN_ROUNDS", 15)
let blockKiB = intVal("FERN_BLOCK_KIB", 64)
let tanjiroPoolMiB = intVal("FERN_TANJIRO_POOL_MIB", 256)
let tanjiroBaseSweeps = intVal("FERN_TANJIRO_BASE_SWEEPS", 2)
let tanjiroExtraSweeps = intVal("FERN_TANJIRO_EXTRA_SWEEPS", 6)
/// Minimum timed-window duration.  Short command buffers are dominated by the
/// ~4us launch floor (rule 55), which would bias every small working set down.
let minWindowMs = dblVal("FERN_MIN_WINDOW_MS", 4.0)
/// Printed label only.  Never used to classify `regime`.
let slcEstimateMiB = intVal("FERN_SLC_MIB", 24)

let device = MTLCreateSystemDefaultDevice()!
let queue = device.makeCommandQueue()!
let coreCount = intVal("FERN_CORES", 20)

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

kernel void blk_read(
    device const uint4 *src [[buffer(0)]],
    device uint4 *dst [[buffer(1)]],
    device const uint *perm [[buffer(2)]],
    constant uint &nblocks [[buffer(3)]],
    constant uint &u4PerBlock [[buffer(4)]],
    constant uint &ntg [[buffer(5)]],
    constant uint &sweeps [[buffer(6)]],
    uint tid [[thread_index_in_threadgroup]],
    uint tgid [[threadgroup_position_in_grid]],
    uint tgsz [[threads_per_threadgroup]],
    uint gid [[thread_position_in_grid]]
) {
    uint4 acc = uint4(0u);
    for (uint s = 0; s < sweeps; ++s) {
        for (uint b = tgid; b < nblocks; b += ntg) {
            uint base = perm[b] * u4PerBlock;
            for (uint i = tid; i < u4PerBlock; i += tgsz) { acc ^= src[base + i]; }
        }
    }
    dst[gid] = acc;
}
"""

let lib = try! device.makeLibrary(source: msl, options: nil)
let seqPipe = try! device.makeComputePipelineState(function: lib.makeFunction(name: "seq_read")!)
let blkPipe = try! device.makeComputePipelineState(function: lib.makeFunction(name: "blk_read")!)

// MARK: - buffers

let maxMiB = max(ladderMiB.max()!, tanjiroPoolMiB)
let srcBytes = maxMiB * 1024 * 1024
let src = device.makeBuffer(length: srcBytes, options: .storageModeShared)!
// Fault every page in and give it non-trivial content, so no timed window pays
// a first-touch fault and no XOR chain can be folded to a constant.
do {
    let p = src.contents().bindMemory(to: UInt64.self, capacity: srcBytes / 8)
    var x: UInt64 = 0x9E3779B97F4A7C15
    for i in 0..<(srcBytes / 8) {
        x = x &* 6364136223846793005 &+ 1442695040888963407
        p[i] = x
    }
}
let dstCapThreads = 1 << 20
let dst = device.makeBuffer(length: dstCapThreads * 16, options: .storageModeShared)!

func makeConst(_ v: UInt32) -> MTLBuffer {
    let b = device.makeBuffer(length: 4, options: .storageModeShared)!
    b.contents().bindMemory(to: UInt32.self, capacity: 1)[0] = v
    return b
}

// MARK: - timing

struct Timed {
    let usMedian: Double
    let usMin: Double
    let usMax: Double
}

func summarise(_ raw: [Double]) -> Timed {
    let s = raw.sorted()
    return Timed(usMedian: s[s.count / 2], usMin: s.first!, usMax: s.last!)
}

func timeSeq(threadgroups: Int, threadsPerTG: Int, ilp: Int, u4Count: Int, sweeps: Int) -> Timed {
    let gsz = threadgroups * threadsPerTG
    precondition(gsz <= dstCapThreads, "grid \(gsz) exceeds dst capacity")
    let cN = makeConst(UInt32(u4Count))
    let cG = makeConst(UInt32(gsz))
    let cS = makeConst(UInt32(sweeps))
    let cI = makeConst(UInt32(ilp))
    var out: [Double] = []
    for r in 0..<(rounds + 1) {
        let cb = queue.makeCommandBuffer()!
        let enc = cb.makeComputeCommandEncoder()!
        enc.setComputePipelineState(seqPipe)
        enc.setBuffer(src, offset: 0, index: 0)
        enc.setBuffer(dst, offset: 0, index: 1)
        enc.setBuffer(cN, offset: 0, index: 2)
        enc.setBuffer(cG, offset: 0, index: 3)
        enc.setBuffer(cS, offset: 0, index: 4)
        enc.setBuffer(cI, offset: 0, index: 5)
        enc.dispatchThreadgroups(
            MTLSize(width: threadgroups, height: 1, depth: 1),
            threadsPerThreadgroup: MTLSize(width: threadsPerTG, height: 1, depth: 1))
        enc.endEncoding()
        cb.commit()
        cb.waitUntilCompleted()
        if r > 0 { out.append((cb.gpuEndTime - cb.gpuStartTime) * 1e6) }
    }
    return summarise(out)
}

func timeBlk(
    threadgroups: Int, threadsPerTG: Int, u4Count: Int, sweeps: Int, perm: MTLBuffer, nblocks: Int,
    u4PerBlock: Int
) -> Timed {
    let gsz = threadgroups * threadsPerTG
    precondition(gsz <= dstCapThreads, "grid \(gsz) exceeds dst capacity")
    let cB = makeConst(UInt32(nblocks))
    let cP = makeConst(UInt32(u4PerBlock))
    let cT = makeConst(UInt32(threadgroups))
    let cS = makeConst(UInt32(sweeps))
    var out: [Double] = []
    for r in 0..<(rounds + 1) {
        let cb = queue.makeCommandBuffer()!
        let enc = cb.makeComputeCommandEncoder()!
        enc.setComputePipelineState(blkPipe)
        enc.setBuffer(src, offset: 0, index: 0)
        enc.setBuffer(dst, offset: 0, index: 1)
        enc.setBuffer(perm, offset: 0, index: 2)
        enc.setBuffer(cB, offset: 0, index: 3)
        enc.setBuffer(cP, offset: 0, index: 4)
        enc.setBuffer(cT, offset: 0, index: 5)
        enc.setBuffer(cS, offset: 0, index: 6)
        enc.dispatchThreadgroups(
            MTLSize(width: threadgroups, height: 1, depth: 1),
            threadsPerThreadgroup: MTLSize(width: threadsPerTG, height: 1, depth: 1))
        enc.endEncoding()
        cb.commit()
        cb.waitUntilCompleted()
        if r > 0 { out.append((cb.gpuEndTime - cb.gpuStartTime) * 1e6) }
    }
    _ = u4Count
    return summarise(out)
}

/// Sweeps needed so the timed window clears the launch floor by a wide margin.
func sweepsFor(_ miB: Int, at gbps: Double) -> Int {
    let bytes = Double(miB) * 1024 * 1024
    let oneSweepMs = bytes / (gbps * 1e9) * 1e3
    return max(1, Int((minWindowMs / oneSweepMs).rounded(.up)))
}

func gbps(bytes: Double, us: Double) -> Double { bytes / (us * 1e-6) / 1e9 }

// MARK: - A. autotune the sequential arm

print("# host: \(device.name), \(coreCount) GPU cores, rounds=\(rounds) (median of \(rounds))")
print("# arm=autotune  working_set=512MiB  metric=achieved_GB_s")
print("tgPerCore\tthreadsPerTG\tilp\ttg\tgrid\tsweeps\tus_med\tGB_s")

let tuneMiB = 512
let tuneU4 = tuneMiB * 1024 * 1024 / 16
var best = (gbps: 0.0, tgPerCore: 0, threadsPerTG: 0, ilp: 0)
for tgPerCore in intList("FERN_TUNE_TGPC", [2, 4, 8, 16]) {
    for threadsPerTG in intList("FERN_TUNE_TPTG", [128, 256, 512]) {
        for ilp in intList("FERN_TUNE_ILP", [1, 2, 4, 8]) {
            let tg = coreCount * tgPerCore
            if tg * threadsPerTG > dstCapThreads { continue }
            let sw = sweepsFor(tuneMiB, at: 250)
            let t = timeSeq(
                threadgroups: tg, threadsPerTG: threadsPerTG, ilp: ilp, u4Count: tuneU4, sweeps: sw)
            let bytes = Double(tuneMiB) * 1024 * 1024 * Double(sw)
            let g = gbps(bytes: bytes, us: t.usMedian)
            print(
                "\(tgPerCore)\t\(threadsPerTG)\t\(ilp)\t\(tg)\t\(tg * threadsPerTG)\t\(sw)\t"
                    + String(format: "%.2f\t%.2f", t.usMedian, g))
            if g > best.gbps { best = (g, tgPerCore, threadsPerTG, ilp) }
        }
    }
}
let bTG = coreCount * best.tgPerCore
let bTPTG = best.threadsPerTG
let bILP = best.ilp
print(
    "# autotune winner: tgPerCore=\(best.tgPerCore) threadsPerTG=\(bTPTG) ilp=\(bILP) "
        + String(format: "-> %.2f GB/s", best.gbps))

// MARK: - B. sequential working-set ladder

print("")
print("# arm=seq  geometry: tg=\(bTG) threadsPerTG=\(bTPTG) grid=\(bTG * bTPTG) ilp=\(bILP)")
print("# bytes_written_per_cb = \(bTG * bTPTG * 16) (one uint4 per thread, once per dispatch)")
print(
    "uniq_MiB\tsweeps\treq_MB\tus_med\tus_min\tus_max\tGB_s\tGB_s_lo\tGB_s_hi\tslc_fit")
var seqRows: [(miB: Int, g: Double, lo: Double, hi: Double)] = []
for miB in ladderMiB {
    let u4 = miB * 1024 * 1024 / 16
    let sw = sweepsFor(miB, at: 250)
    let t = timeSeq(threadgroups: bTG, threadsPerTG: bTPTG, ilp: bILP, u4Count: u4, sweeps: sw)
    let bytes = Double(miB) * 1024 * 1024 * Double(sw)
    let g = gbps(bytes: bytes, us: t.usMedian)
    let lo = gbps(bytes: bytes, us: t.usMax)
    let hi = gbps(bytes: bytes, us: t.usMin)
    let fit = miB * 2 <= slcEstimateMiB ? "fits" : (miB <= slcEstimateMiB * 2 ? "marginal" : "spills")
    print(
        "\(miB)\t\(sw)\t" + String(format: "%.1f\t%.2f\t%.2f\t%.2f\t%.2f\t%.2f\t%.2f\t", bytes / 1e6,
            t.usMedian, t.usMin, t.usMax, g, lo, hi) + fit)
    seqRows.append((miB, g, lo, hi))
}

// The DRAM asymptote is the median of the rows at >= 8x the SLC estimate.
let asymRows = seqRows.filter { $0.miB >= slcEstimateMiB * 8 }.map { $0.g }.sorted()
let dramPeak = asymRows[asymRows.count / 2]
let cachePeak = seqRows.map { $0.g }.max()!
print(
    "# MEASURED dram_read_ceiling = " + String(format: "%.2f", dramPeak)
        + " GB/s (median of \(asymRows.count) rows >= \(slcEstimateMiB * 8) MiB, range "
        + String(format: "%.2f..%.2f", asymRows.first!, asymRows.last!) + ")")
print("# MEASURED cache_served_ceiling = " + String(format: "%.2f", cachePeak) + " GB/s")

// Rule 71 as amended: `regime` from achieved_GB_s only, independent of capacity.
print("")
print("# arm=seq  rule-71 two-column classification")
print("uniq_MiB\tGB_s\tpct_dram_ceiling\tregime\tslc_fit")
for r in seqRows {
    let pct = r.g / dramPeak * 100
    let regime = pct <= 115 ? "dram" : (pct <= 160 ? "mixed" : "cache")
    let fit =
        r.miB * 2 <= slcEstimateMiB ? "fits" : (r.miB <= slcEstimateMiB * 2 ? "marginal" : "spills")
    print("\(r.miB)\t" + String(format: "%.2f\t%.1f\t", r.g, pct) + regime + "\t" + fit)
}

// MARK: - C. block-shuffled arm

print("")
print("# arm=blk  block=\(blockKiB)KiB  geometry: tg=\(bTG) threadsPerTG=\(bTPTG)")
print("uniq_MiB\tnblocks\tsweeps\treq_MB\tus_med\tGB_s\tpct_seq\tslc_fit")
let u4PerBlock = blockKiB * 1024 / 16
for miB in ladderMiB where miB * 1024 >= blockKiB {
    let nblocks = miB * 1024 / blockKiB
    var order = Array(0..<UInt32(nblocks))
    // Deterministic Fisher-Yates so the permutation is reproducible run to run.
    var state: UInt64 = 0xDEADBEEFCAFEF00D
    var i = nblocks - 1
    while i > 0 {
        state = state &* 6364136223846793005 &+ 1442695040888963407
        let j = Int((state >> 33) % UInt64(i + 1))
        order.swapAt(i, j)
        i -= 1
    }
    let perm = device.makeBuffer(
        bytes: order, length: nblocks * 4, options: .storageModeShared)!
    let sw = sweepsFor(miB, at: 250)
    let t = timeBlk(
        threadgroups: bTG, threadsPerTG: bTPTG, u4Count: miB * 1024 * 1024 / 16, sweeps: sw,
        perm: perm, nblocks: nblocks, u4PerBlock: u4PerBlock)
    let bytes = Double(miB) * 1024 * 1024 * Double(sw)
    let g = gbps(bytes: bytes, us: t.usMedian)
    let ref = seqRows.first { $0.miB == miB }!.g
    let fit = miB * 2 <= slcEstimateMiB ? "fits" : (miB <= slcEstimateMiB * 2 ? "marginal" : "spills")
    print(
        "\(miB)\t\(nblocks)\t\(sw)\t"
            + String(format: "%.1f\t%.2f\t%.2f\t%.1f\t", bytes / 1e6, t.usMedian, g, g / ref * 100)
            + fit)
}

// MARK: - D. tanjiro pool-differential instrument

print("")
print("# arm=tanjiro  pool=\(tanjiroPoolMiB)MiB  base=\(tanjiroBaseSweeps) extra=\(tanjiroExtraSweeps)")
print("# replicates tanjiro-pr27-interim.md:1044-1105 geometry on this host")
let poolU4 = tanjiroPoolMiB * 1024 * 1024 / 16
let tA = timeSeq(
    threadgroups: bTG, threadsPerTG: bTPTG, ilp: bILP, u4Count: poolU4, sweeps: tanjiroBaseSweeps)
let tB = timeSeq(
    threadgroups: bTG, threadsPerTG: bTPTG, ilp: bILP, u4Count: poolU4,
    sweeps: tanjiroBaseSweeps + tanjiroExtraSweeps)
let dBytes = Double(tanjiroExtraSweeps) * Double(tanjiroPoolMiB) * 1024 * 1024
let dUs = tB.usMedian - tA.usMedian
print("sweeps\tus_med\tus_min\tus_max")
print(String(format: "\(tanjiroBaseSweeps)\t%.2f\t%.2f\t%.2f", tA.usMedian, tA.usMin, tA.usMax))
print(
    String(
        format: "\(tanjiroBaseSweeps + tanjiroExtraSweeps)\t%.2f\t%.2f\t%.2f", tB.usMedian, tB.usMin,
        tB.usMax))
print(
    "# delta_bytes = " + String(format: "%.2f MB  delta_us = %.2f  -> %.2f GB/s", dBytes / 1e6, dUs,
        gbps(bytes: dBytes, us: dUs)))
print(
    "# tanjiro_instrument_pct_of_measured_dram_ceiling = "
        + String(format: "%.1f%%", gbps(bytes: dBytes, us: dUs) / dramPeak * 100))

// MARK: - E. published-denominator comparison

print("")
print("# published M4-Pro denominators vs this measurement")
print("source\tvalue_GB_s\tpct_of_measured_dram_ceiling")
for (name, v) in [
    ("theoretical_273_r94_census", 273.0),
    ("hardcoded_266.3_fern_r100_probe:71", 266.3),
    ("roofline_260.6_fern_ledger:940", 260.6),
    ("tanjiro_pool_diff_237.4_published", 237.4),
] {
    print(name + String(format: "\t%.1f\t%.1f", v, v / dramPeak * 100))
}
print("# done")
