// r97-c CEILING LADDER: how much time can a K-axis threadgroup split of the two
// fused decode attention kernels recover, IGNORING everything it would cost?
//
// Two ladders, one per pre-registered state. Rung N = headPairs * t, where t is
// threadgroups per head pair and each threadgroup keeps 32/t simdgroups:
//
//   sliding  N in {32, 64, 128, 256, 512}   (N=32  is the shipped geometry)
//   full     N in {24, 48,  96, 192, 384}   (N=24  is the shipped geometry)
//
// Every rung runs the SAME per-simdgroup body over the SAME 16 K positions and
// finishes with the SAME in-threadgroup epilogue over its own simdgroups. The
// split rungs are deliberately given their cross-threadgroup combine FOR FREE:
// no partial buffer is written, no second dispatch is issued. What this
// measures is therefore a strict UPPER BOUND on the mechanism.
//
// The reported statistic is the recovery FRACTION, because that is what
// transfers across core counts. For both rung sets the wave model predicts the
// same fraction on 20 cores (M4 Pro) and 40 cores (M5 Max):
//   sliding  ceil(32t/cores)/t vs ceil(32/cores)  -> 0.8125 at t=16 on both
//   full     ceil(24t/cores)/t vs ceil(24/cores)  -> 0.625  at t=16 on both
//
// Design is #497's blocked randomised ladder (rule 56): B blocks, all rungs
// visited in a fresh random order inside each block, per-rung medians across
// blocks, bootstrap CI on the paired ratio against the shipped rung.
//
// Build/run:
//   xcrun swiftc -O research/nezuko_r97_split_ceiling_ladder.swift \
//     -o /tmp/nezuko_r97_ladder -framework Metal -framework Foundation
//   /tmp/nezuko_r97_ladder

import Foundation
import Metal

let headDim = 128
let window = 512
let partitions = 32         // K partitions per head pair (fixed by the algorithm)
let posPerPartition = window / partitions   // 16

// Two ladders, one per pre-registered state. Both walk t = threadgroups per
// head pair; rung N = headPairs * t.
//   sliding: 32 head pairs (64 heads), 30 calls/step, t in {1,2,4,8,16}
//   full   : 24 head pairs (48 heads), 10 calls/step, t in {1,2,4,8,16}
let slidingRungs = [32, 64, 128, 256, 512]
let fullRungs = [24, 48, 96, 192, 384]
let blocks = 40
let itersPerMeasure = 200

// Kernel body is structurally the shipped one: qk_per_thread = 4 dims/lane,
// two query heads per head pair, simd_sum over 32 lanes, online softmax with a
// running max/sum rescale, 4 output dims per lane.
let source = """
#include <metal_stdlib>
using namespace metal;

#define HEAD_DIM 128
#define POS_PER_PART 16
#define QK_PER_THREAD 4

kernel void attn_stage1(
    device const half *keys      [[buffer(0)]],
    device const half *values    [[buffer(1)]],
    device const float *queries  [[buffer(2)]],
    device float *out            [[buffer(3)]],
    constant uint &sgPerTG       [[buffer(4)]],
    constant uint &iters         [[buffer(5)]],
    threadgroup float *scratch   [[threadgroup(0)]],
    uint  tgid [[threadgroup_position_in_grid]],
    uint  lane [[thread_index_in_simdgroup]],
    uint  sg   [[simdgroup_index_in_threadgroup]],
    uint  tid  [[thread_index_in_threadgroup]])
{
    // tgsPerPair threadgroups cooperate on one head pair; this threadgroup owns
    // partitions [blk*sgPerTG, (blk+1)*sgPerTG).
    uint tgsPerPair = 32u / sgPerTG;
    uint pair = tgid / tgsPerPair;
    uint blk  = tgid % tgsPerPair;
    uint part = blk * sgPerTG + sg;

    float q0[QK_PER_THREAD];
    float q1[QK_PER_THREAD];
    for (uint d = 0; d < QK_PER_THREAD; ++d) {
        q0[d] = queries[(pair * 2u + 0u) * HEAD_DIM + lane * QK_PER_THREAD + d];
        q1[d] = queries[(pair * 2u + 1u) * HEAD_DIM + lane * QK_PER_THREAD + d];
    }

    // gqa = 8: four consecutive head pairs share one kv head, exactly as shipped.
    uint kvHead = pair / 4u;
    device const half *kbase = keys   + kvHead * 512u * HEAD_DIM;
    device const half *vbase = values + kvHead * 512u * HEAD_DIM;

    float m0 = -INFINITY, m1 = -INFINITY;
    float s0 = 0.0f, s1 = 0.0f;
    float o0[QK_PER_THREAD] = {0,0,0,0};
    float o1[QK_PER_THREAD] = {0,0,0,0};

    for (uint it = 0; it < iters; ++it) {
        for (uint j = 0; j < POS_PER_PART; ++j) {
            uint pos = part + j * 32u;
            device const half *kp = kbase + pos * HEAD_DIM + lane * QK_PER_THREAD;
            device const half *vp = vbase + pos * HEAD_DIM + lane * QK_PER_THREAD;

            float kv[QK_PER_THREAD];
            float vv[QK_PER_THREAD];
            for (uint d = 0; d < QK_PER_THREAD; ++d) {
                kv[d] = float(kp[d]);
                vv[d] = float(vp[d]);
            }

            float sc0 = 0.0f, sc1 = 0.0f;
            for (uint d = 0; d < QK_PER_THREAD; ++d) {
                sc0 += q0[d] * kv[d];
                sc1 += q1[d] * kv[d];
            }
            sc0 = simd_sum(sc0);
            sc1 = simd_sum(sc1);

            float nm0 = max(m0, sc0);
            float nm1 = max(m1, sc1);
            float f0 = metal::fast::exp(m0 - nm0);
            float f1 = metal::fast::exp(m1 - nm1);
            float e0 = metal::fast::exp(sc0 - nm0);
            float e1 = metal::fast::exp(sc1 - nm1);
            m0 = nm0; m1 = nm1;
            s0 = s0 * f0 + e0;
            s1 = s1 * f1 + e1;
            for (uint d = 0; d < QK_PER_THREAD; ++d) {
                o0[d] = o0[d] * f0 + e0 * vv[d];
                o1[d] = o1[d] * f1 + e1 * vv[d];
            }
        }
    }

    // In-threadgroup epilogue over this threadgroup's own simdgroups. The split
    // rungs get their cross-threadgroup combine for free: nothing is spilled.
    threadgroup float *maxes = scratch;
    threadgroup float *sums  = scratch + 64;
    threadgroup float *accum = scratch + 128;
    if (lane == 0) {
        maxes[sg] = m0;
        sums[sg]  = s0;
    }
    for (uint d = 0; d < QK_PER_THREAD; ++d) {
        accum[sg * 128u + lane * QK_PER_THREAD + d] = o0[d] + o1[d];
    }
    threadgroup_barrier(mem_flags::mem_threadgroup);

    if (sg == 0) {
        float gm = -INFINITY;
        for (uint p = 0; p < sgPerTG; ++p) gm = max(gm, maxes[p]);
        float gs = 0.0f, acc = 0.0f;
        for (uint p = 0; p < sgPerTG; ++p) {
            float w = metal::fast::exp(maxes[p] - gm);
            gs += sums[p] * w;
            acc += accum[p * 128u + lane] * w;
        }
        gs = simd_sum(gs);
        if (lane == 0) {
            out[tgid] = acc + gs + m1 + s1;
        }
    }
}
"""

guard let device = MTLCreateSystemDefaultDevice(),
      let queue = device.makeCommandQueue() else { fatalError("no Metal device") }

print("device: \(device.name)")
if #available(macOS 14.0, *) { print("architecture: \(device.architecture.name)") }
print("blocks: \(blocks)  iters/measure: \(itersPerMeasure)")

let library = try device.makeLibrary(source: source, options: nil)
let fn = library.makeFunction(name: "attn_stage1")!
let pso = try device.makeComputePipelineState(function: fn)
print("maxTotalThreadsPerThreadgroup: \(pso.maxTotalThreadsPerThreadgroup)")

// 8 kv heads (gqa=8 over 64 heads), 512 positions, 128 dims, half.
let kvElems = 8 * 512 * headDim
let keysBuf = device.makeBuffer(length: kvElems * 2, options: .storageModePrivate)!
let valsBuf = device.makeBuffer(length: kvElems * 2, options: .storageModePrivate)!
var qHost = [Float](repeating: 0, count: 32 * 2 * headDim)
for i in 0..<qHost.count { qHost[i] = Float((i % 17)) * 0.01 - 0.08 }
let qBuf = device.makeBuffer(bytes: &qHost,
                             length: qHost.count * 4, options: .storageModeShared)!
let outBuf = device.makeBuffer(length: 512 * 4, options: .storageModeShared)!

// One measurement: N threadgroups, 32/tgsPerPair simdgroups each, `iters`
// repetitions of the 16-position body inside the kernel. Returns µs per call.
func measure(_ n: Int, _ headPairs: Int) -> Double {
    let tgsPerPair = n / headPairs
    let sgPerTG = partitions / tgsPerPair
    let threads = sgPerTG * 32
    var sgU = UInt32(sgPerTG)
    var itU = UInt32(itersPerMeasure)
    let scratchBytes = (128 + sgPerTG * 128) * 4

    let cb = queue.makeCommandBuffer()!
    let enc = cb.makeComputeCommandEncoder()!
    enc.setComputePipelineState(pso)
    enc.setBuffer(keysBuf, offset: 0, index: 0)
    enc.setBuffer(valsBuf, offset: 0, index: 1)
    enc.setBuffer(qBuf, offset: 0, index: 2)
    enc.setBuffer(outBuf, offset: 0, index: 3)
    enc.setBytes(&sgU, length: 4, index: 4)
    enc.setBytes(&itU, length: 4, index: 5)
    enc.setThreadgroupMemoryLength(scratchBytes, index: 0)
    enc.dispatchThreadgroups(MTLSize(width: n, height: 1, depth: 1),
                             threadsPerThreadgroup: MTLSize(width: threads, height: 1, depth: 1))
    enc.endEncoding()
    cb.commit()
    cb.waitUntilCompleted()
    let gpu = cb.gpuEndTime - cb.gpuStartTime
    return gpu * 1e6 / Double(itersPerMeasure)
}

func median(_ a: [Double]) -> Double {
    let s = a.sorted()
    return s.count % 2 == 1 ? s[s.count / 2]
                            : 0.5 * (s[s.count / 2 - 1] + s[s.count / 2])
}

var rng = SystemRandomNumberGenerator()

// Returns the best recovery FRACTION (1 - t_N/t_base) and its bootstrap CI.
// The fraction, not the absolute microseconds, is what transfers to another
// core count: it is set purely by ceil(N/cores)/t relative to ceil(N0/cores).
@discardableResult
func runLadder(_ name: String, headPairs: Int, rungs: [Int],
               callsPerStep: Int) -> (n: Int, frac: Double, lo: Double, hi: Double) {
    print("")
    print("=== \(name) ladder: \(headPairs) head pairs, \(callsPerStep) calls/step ===")
    print("requested K+V per call, every rung: "
          + "\(headPairs * window * headDim * 2 * 2 / 1024 / 1024) MB")

    for n in rungs { _ = measure(n, headPairs) }

    var samples: [Int: [Double]] = [:]
    for n in rungs { samples[n] = [] }
    for _ in 0..<blocks {
        for n in rungs.shuffled(using: &rng) {
            samples[n]!.append(measure(n, headPairs))
        }
    }

    let base = median(samples[rungs[0]]!)
    print("rung  t  sg/TG  thr/TG   median us/call   us/step   recovery vs shipped")
    var best = (n: rungs[0], frac: 0.0, lo: 0.0, hi: 0.0)
    for n in rungs {
        let t = n / headPairs
        let sg = partitions / t
        let m = median(samples[n]!)

        let a = samples[rungs[0]]!, b = samples[n]!
        var boot: [Double] = []
        boot.reserveCapacity(4000)
        for _ in 0..<4000 {
            var num = 0.0, den = 0.0
            for _ in 0..<blocks {
                let i = Int.random(in: 0..<blocks, using: &rng)
                num += a[i] - b[i]
                den += a[i]
            }
            boot.append(num / den)
        }
        boot.sort()
        let lo = boot[Int(0.025 * Double(boot.count))]
        let hi = boot[Int(0.975 * Double(boot.count))]
        let frac = (base - m) / base
        if frac > best.frac { best = (n, frac, lo, hi) }
        print(String(format: "%4d %2d  %5d  %6d   %13.3f   %7.1f   %+6.2f%% [%+.2f%%, %+.2f%%]",
                     n, t, sg, sg * 32, m, m * Double(callsPerStep),
                     frac * 100, lo * 100, hi * 100))
    }
    return (best.n, best.frac, best.lo, best.hi)
}

let slid = runLadder("SLIDING", headPairs: 32, rungs: slidingRungs, callsPerStep: 30)
let full = runLadder("FULL", headPairs: 24, rungs: fullRungs, callsPerStep: 10)

// Pre-registered read-out. The M4 bar compares the measured ceiling with rule
// 57's M4 dispatch cost; the M5 projection applies the measured fraction to the
// programme's M5 attention costs and rule-quoted M5 dispatch cost.
print("")
print("--- pre-registered read-out ---")
let m4Dispatch = 1.2382, m5Dispatch = 2.3403
let m5Sliding = 290.0, m5Full = 100.0
let m4Sliding = 636.0        // CURRENT_RESEARCH_STATE.md:550
let waveDepShare = 0.847     // t(K) = 1.413 + 7.849*ceil(K/cores)

let m4Gain = slid.frac * m4Sliding * waveDepShare
let m4Cost = 30.0 * m4Dispatch
print(String(format: "M4 sliding: ceiling %+.1f us/step (%.2f%% of %.0f) vs 2nd-dispatch cost %.1f",
             m4Gain, slid.frac * 100, m4Sliding, m4Cost))
print(m4Gain > m4Cost ? "  M4 CEILING BAR: PASS" : "  M4 CEILING BAR: FAIL")
print(String(format: "M4/M5 favourability for a kernel-time-for-dispatch trade: %.2fx",
             (m4Gain / m4Cost) / (slid.frac * m5Sliding * waveDepShare / (30.0 * m5Dispatch))))

for waveDep in [0.847, 1.0] {
    let gS = slid.frac * m5Sliding * waveDep
    let gF = full.frac * m5Full * waveDep
    let cS = 30.0 * m5Dispatch, cF = 10.0 * m5Dispatch
    print(String(format: "M5 @ wave-dep %.3f: sliding %+.1f vs cost %.1f (bar 120) | "
                 + "full %+.1f vs cost %.1f (bar 40) | net %+.1f us/step",
                 waveDep, gS, cS, gF, cF, gS + gF - cS - cF))
}
