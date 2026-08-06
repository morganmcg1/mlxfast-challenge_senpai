// Research-only probe (PR #157, Step 0): does this stack execute two
// hazard-free kernels concurrently on the GPU, and can the programme's
// incumbent `gpu_busy_union` instrument see it if it does?
//
// Build and run:
//   xcrun swiftc -O research/tanjiro_coresidency_probe.swift -o /tmp/tjcores \
//       -framework Metal -framework Foundation
//   /tmp/tjcores [rounds] [targetMs]
//
// Two instruments are computed on the *same* command buffers:
//
//   wall       CPU time across commit() + waitUntilCompleted(). Cannot be
//              blind to overlap: if two 20 ms kernels finish in 21 ms they
//              overlapped. This is the primary instrument.
//   CB-union   an exact reimplementation of research/decode_probe.py:147-192,
//              i.e. sweep-merge of per-command-buffer
//              MTLCommandBuffer.gpuStartTime/gpuEndTime intervals. This is the
//              instrument every "zero concurrency" datum in the campaign was
//              read from. It is computed here so it can be compared, on
//              identical work, against wall.
//
// Encoder semantics replicate MLX exactly, from
// Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp:
//   * compute encoders are created DispatchTypeConcurrent (:548),
//   * memoryBarrier(BarrierScopeBuffers) is emitted only before a dispatch
//     whose input was written by an earlier dispatch in the same encoder
//     (:325-330 set_input_array, :363-375 maybeInsertBarrier).
//
// Arms per (pair, size): a_only, b_only, concurrent_1cb, barrier_1cb,
// raw_1cb (negative control), serialenc_1cb, two_cb.
//
// Discipline carried over from PR #47 D1: GPU clocks are pinned by a sustained
// burn before every measured cell; every cell is sampled once per round in a
// freshly shuffled order; the overlap ratio is formed *within* a round so that
// drift cancels; the spread over rounds is the CI.

import Foundation
import Metal

// MARK: - shaders

let shaderSource = """
#include <metal_stdlib>
using namespace metal;

// Compute-bound. Reads depIn[0] so that a real RAW hazard can be created by
// binding a previous kernel's output as this kernel's depIn.
kernel void k_alu(device float *out [[buffer(0)]],
                  device const float *depIn [[buffer(1)]],
                  constant uint &iters [[buffer(2)]],
                  uint gid [[thread_position_in_grid]]) {
  float a = depIn[0] + float(gid) * 1e-6f;
  float b = a * 1.000001f + 0.5f;
  float c = a * 0.999999f + 0.25f;
  float d = a + 1.0f;
  for (uint i = 0; i < iters; ++i) {
    a = fma(a, 1.0000001f, 1e-7f);
    b = fma(b, 0.9999999f, 2e-7f);
    c = fma(c, 1.0000002f, 3e-7f);
    d = fma(d, 0.9999998f, 4e-7f);
  }
  out[gid] = a + b + c + d;
}

// Bandwidth-bound: streams a large buffer with a grid-stride loop.
kernel void k_mem(device float *out [[buffer(0)]],
                  device const float *depIn [[buffer(1)]],
                  constant uint &iters [[buffer(2)]],
                  device const float4 *src [[buffer(3)]],
                  constant uint &n4 [[buffer(4)]],
                  uint gid [[thread_position_in_grid]],
                  uint gsz [[threads_per_grid]]) {
  float4 acc = float4(depIn[0]);
  for (uint it = 0; it < iters; ++it) {
    for (uint i = gid; i < n4; i += gsz) {
      acc += src[i];
    }
  }
  out[gid] = acc.x + acc.y + acc.z + acc.w;
}

// Straightforward tiled bf16 GEMM. Not fast; it only has to be large, real
// bf16 arithmetic, and independent of its partner.
#define TS 16
kernel void k_gemm(device float *out [[buffer(0)]],
                   device const float *depIn [[buffer(1)]],
                   constant uint3 &dims [[buffer(2)]],
                   device const bfloat *A [[buffer(3)]],
                   device const bfloat *B [[buffer(4)]],
                   uint2 tgid [[threadgroup_position_in_grid]],
                   uint2 tid [[thread_position_in_threadgroup]]) {
  const uint N = dims.y, K = dims.z;
  threadgroup bfloat As[TS][TS];
  threadgroup bfloat Bs[TS][TS];
  const uint row = tgid.y * TS + tid.y;
  const uint col = tgid.x * TS + tid.x;
  float acc = depIn[0];
  for (uint k0 = 0; k0 < K; k0 += TS) {
    As[tid.y][tid.x] = A[row * K + k0 + tid.x];
    Bs[tid.y][tid.x] = B[(k0 + tid.y) * N + col];
    threadgroup_barrier(mem_flags::mem_threadgroup);
    for (uint k = 0; k < TS; ++k) {
      acc += float(As[tid.y][k]) * float(Bs[k][tid.x]);
    }
    threadgroup_barrier(mem_flags::mem_threadgroup);
  }
  out[row * N + col] = acc;
}
"""

// MARK: - setup

let args = CommandLine.arguments
let rounds = args.count > 1 ? Int(args[1])! : 7
let targetMs = args.count > 2 ? Double(args[2])! : 20.0

guard let device = MTLCreateSystemDefaultDevice(),
      let queue = device.makeCommandQueue(),
      let queue2 = device.makeCommandQueue() else {
  fatalError("no Metal device")
}
let library = try device.makeLibrary(source: shaderSource, options: nil)
func pso(_ name: String) -> MTLComputePipelineState {
  try! device.makeComputePipelineState(function: library.makeFunction(name: name)!)
}
let psoAlu = pso("k_alu")
let psoMem = pso("k_mem")
let psoGemm = pso("k_gemm")

print("# host")
print("device                       \(device.name)")
print("architecture                 \(device.architecture.name)")
print("maxThreadgroupMemoryLength   \(device.maxThreadgroupMemoryLength)")
print("recommendedWorkingSetSize    \(device.recommendedMaxWorkingSetSize)")
print("k_alu maxThreadsPerTG        \(psoAlu.maxTotalThreadsPerThreadgroup)")
print("k_gemm maxThreadsPerTG       \(psoGemm.maxTotalThreadsPerThreadgroup)")
print("counterSampling.stage        \(device.supportsCounterSampling(.atStageBoundary))")
print("counterSampling.dispatch     \(device.supportsCounterSampling(.atDispatchBoundary))")
print("counterSampling.blit         \(device.supportsCounterSampling(.atBlitBoundary))")
print("rounds=\(rounds) targetMs=\(targetMs)")
print("")

// MARK: - jobs

final class Job {
  let pso: MTLComputePipelineState
  let out: MTLBuffer
  var depIn: MTLBuffer
  let buffers: [(Int, MTLBuffer)]
  var scalars: [(Int, UInt32)]
  var vec3: [(Int, SIMD3<UInt32>)]
  let grid: MTLSize
  let tg: MTLSize
  init(pso: MTLComputePipelineState, out: MTLBuffer, depIn: MTLBuffer,
       buffers: [(Int, MTLBuffer)] = [], scalars: [(Int, UInt32)] = [],
       vec3: [(Int, SIMD3<UInt32>)] = [], grid: MTLSize, tg: MTLSize) {
    self.pso = pso; self.out = out; self.depIn = depIn; self.buffers = buffers
    self.scalars = scalars; self.vec3 = vec3; self.grid = grid; self.tg = tg
  }
}

func encode(_ enc: MTLComputeCommandEncoder, _ j: Job) {
  enc.setComputePipelineState(j.pso)
  enc.setBuffer(j.out, offset: 0, index: 0)
  enc.setBuffer(j.depIn, offset: 0, index: 1)
  for (i, b) in j.buffers { enc.setBuffer(b, offset: 0, index: i) }
  for (i, v) in j.scalars { var x = v; enc.setBytes(&x, length: 4, index: i) }
  for (i, v) in j.vec3 { var x = v; enc.setBytes(&x, length: 16, index: i) }
  enc.dispatchThreadgroups(j.grid, threadsPerThreadgroup: j.tg)
}

// MARK: - arms

enum Arm: String, CaseIterable {
  case aOnly = "a_only"
  case bOnly = "b_only"
  case concurrent = "concurrent_1cb"
  case barrier = "barrier_1cb"
  case raw = "raw_1cb"
  case serialenc = "serialenc_1cb"
  case twoCB = "two_cb"
  case twoQueue = "two_queue"
  case twoCBSerial = "two_cb_serial"
}

struct Sample {
  var wallMs: Double
  var busySumMs: Double
  var busyUnionMs: Double
  var cbs: Int
  /// Per-command-buffer [start,end] in ms relative to the earliest start, so
  /// the actual interval layout is evidence rather than inference.
  var layout: [(Double, Double)]
}

/// Sweep-merge of [start,end] intervals, byte-for-byte the algorithm in
/// research/decode_probe.py:177-186.
func mergedSpan(_ intervals: [(Double, Double)]) -> Double {
  guard !intervals.isEmpty else { return 0 }
  let s = intervals.sorted { $0.0 < $1.0 }
  var total = 0.0
  var (cs, ce) = s[0]
  for (a, b) in s.dropFirst() {
    if a > ce { total += ce - cs; cs = a; ce = b } else { ce = max(ce, b) }
  }
  total += ce - cs
  return total
}

func runArm(_ arm: Arm, a: Job, b: Job, rawDep: MTLBuffer) -> Sample {
  var cbs: [MTLCommandBuffer] = []
  let savedDep = b.depIn
  if arm == .raw { b.depIn = rawDep }
  defer { b.depIn = savedDep }

  switch arm {
  case .aOnly, .bOnly:
    let cb = queue.makeCommandBuffer()!
    let enc = cb.makeComputeCommandEncoder(dispatchType: .concurrent)!
    encode(enc, arm == .aOnly ? a : b)
    enc.endEncoding()
    cbs = [cb]
  case .concurrent:
    let cb = queue.makeCommandBuffer()!
    let enc = cb.makeComputeCommandEncoder(dispatchType: .concurrent)!
    encode(enc, a); encode(enc, b)
    enc.endEncoding()
    cbs = [cb]
  case .barrier, .raw:
    let cb = queue.makeCommandBuffer()!
    let enc = cb.makeComputeCommandEncoder(dispatchType: .concurrent)!
    encode(enc, a)
    enc.memoryBarrier(scope: .buffers)
    encode(enc, b)
    enc.endEncoding()
    cbs = [cb]
  case .serialenc:
    let cb = queue.makeCommandBuffer()!
    let enc = cb.makeComputeCommandEncoder(dispatchType: .serial)!
    encode(enc, a); encode(enc, b)
    enc.endEncoding()
    cbs = [cb]
  case .twoCB, .twoCBSerial:
    for j in [a, b] {
      let cb = queue.makeCommandBuffer()!
      let enc = cb.makeComputeCommandEncoder(dispatchType: .concurrent)!
      encode(enc, j)
      enc.endEncoding()
      cbs.append(cb)
    }
  case .twoQueue:
    for (j, q) in zip([a, b], [queue, queue2]) {
      let cb = q.makeCommandBuffer()!
      let enc = cb.makeComputeCommandEncoder(dispatchType: .concurrent)!
      encode(enc, j)
      enc.endEncoding()
      cbs.append(cb)
    }
  }

  let t0 = DispatchTime.now().uptimeNanoseconds
  if arm == .twoCBSerial {
    // Proper two-command-buffer NEGATIVE control: the second buffer is not
    // even enqueued until the first has fully retired, so no honest
    // instrument may report union < sum here.
    for cb in cbs { cb.commit(); cb.waitUntilCompleted() }
  } else {
    for cb in cbs { cb.commit() }
    for cb in cbs { cb.waitUntilCompleted() }
  }
  let t1 = DispatchTime.now().uptimeNanoseconds

  let iv = cbs.map { ($0.gpuStartTime, $0.gpuEndTime) }
  let sum = iv.reduce(0.0) { $0 + ($1.1 - $1.0) }
  let origin = iv.map { $0.0 }.min() ?? 0
  return Sample(wallMs: Double(t1 - t0) / 1e6,
                busySumMs: sum * 1e3,
                busyUnionMs: mergedSpan(iv) * 1e3,
                cbs: cbs.count,
                layout: iv.map { (($0.0 - origin) * 1e3, ($0.1 - origin) * 1e3) })
}

// MARK: - clock pinning

let scratchDep = device.makeBuffer(length: 4096, options: .storageModeShared)!
let burnOut = device.makeBuffer(length: 4 * 1024 * 1024, options: .storageModePrivate)!
let burnJob = Job(pso: psoAlu, out: burnOut, depIn: scratchDep,
                  scalars: [(2, 4000)],
                  grid: MTLSize(width: 512, height: 1, depth: 1),
                  tg: MTLSize(width: 256, height: 1, depth: 1))

func pinClocks(ms: Double = 25) {
  let deadline = Date().addingTimeInterval(ms / 1000.0)
  repeat {
    let cb = queue.makeCommandBuffer()!
    let enc = cb.makeComputeCommandEncoder(dispatchType: .concurrent)!
    encode(enc, burnJob)
    enc.endEncoding()
    cb.commit(); cb.waitUntilCompleted()
  } while Date() < deadline
}

// MARK: - statistics

func median(_ xs: [Double]) -> Double {
  let s = xs.sorted()
  let n = s.count
  return n % 2 == 1 ? s[n / 2] : 0.5 * (s[n / 2 - 1] + s[n / 2])
}

func bootstrapCI(_ xs: [Double], reps: Int = 4000) -> (Double, Double) {
  guard xs.count > 1 else { return (Double.nan, Double.nan) }
  var gen = SystemRandomNumberGenerator()
  var meds = [Double]()
  meds.reserveCapacity(reps)
  for _ in 0..<reps {
    var s = [Double]()
    s.reserveCapacity(xs.count)
    for _ in 0..<xs.count { s.append(xs[Int.random(in: 0..<xs.count, using: &gen)]) }
    meds.append(median(s))
  }
  meds.sort()
  return (meds[Int(0.025 * Double(reps))], meds[Int(0.975 * Double(reps))])
}

func fmt(_ x: Double, _ d: Int = 3) -> String { String(format: "%.\(d)f", x) }

// MARK: - pair construction

struct Pair {
  let name: String
  let sizeLabel: String
  let a: Job
  let b: Job
  let rawDep: MTLBuffer   // A's output, bound as B's depIn in the raw arm
  let tgCount: Int
  let threadsPerTG: Int
}

let threadsPerTG = 256
let streamBytes = 256 * 1024 * 1024
let streamBuf = device.makeBuffer(length: streamBytes, options: .storageModePrivate)!
let n4 = UInt32(streamBytes / 16)

func aluJob(tgs: Int, iters: UInt32, out: MTLBuffer, dep: MTLBuffer) -> Job {
  Job(pso: psoAlu, out: out, depIn: dep, scalars: [(2, iters)],
      grid: MTLSize(width: tgs, height: 1, depth: 1),
      tg: MTLSize(width: threadsPerTG, height: 1, depth: 1))
}

func memJob(tgs: Int, iters: UInt32, out: MTLBuffer, dep: MTLBuffer) -> Job {
  Job(pso: psoMem, out: out, depIn: dep,
      buffers: [(3, streamBuf)], scalars: [(2, iters), (4, n4)],
      grid: MTLSize(width: tgs, height: 1, depth: 1),
      tg: MTLSize(width: threadsPerTG, height: 1, depth: 1))
}

/// Calibrate `iters` so one isolated dispatch of `make(iters)` lands near
/// targetMs. Two refinement steps; duration is linear in iters.
func calibrate(_ make: (UInt32) -> Job, start: UInt32) -> UInt32 {
  var iters = start
  for _ in 0..<2 {
    let j = make(iters)
    pinClocks(ms: 15)
    var best = Double.infinity
    for _ in 0..<3 {
      let s = runArm(.aOnly, a: j, b: j, rawDep: scratchDep)
      best = min(best, s.wallMs)
    }
    let scale = targetMs / max(best, 0.05)
    let next = Double(iters) * scale
    iters = UInt32(max(1.0, min(next, 4_000_000.0)))
  }
  return iters
}

func newOut(_ elems: Int) -> MTLBuffer {
  device.makeBuffer(length: max(4096, elems * 4), options: .storageModePrivate)!
}

var pairs: [Pair] = []

let aluSizes = [2, 5, 10, 20, 40, 240, 1000]
let mixSizes = [2, 10, 20, 240]

for tgs in aluSizes {
  let outA = newOut(tgs * threadsPerTG), outB = newOut(tgs * threadsPerTG)
  let iters = calibrate({ aluJob(tgs: tgs, iters: $0, out: outA, dep: scratchDep) },
                        start: 200_000)
  pairs.append(Pair(name: "alu/alu", sizeLabel: "tg=\(tgs) iters=\(iters)",
                    a: aluJob(tgs: tgs, iters: iters, out: outA, dep: scratchDep),
                    b: aluJob(tgs: tgs, iters: iters, out: outB, dep: scratchDep),
                    rawDep: outA, tgCount: tgs, threadsPerTG: threadsPerTG))
}

for tgs in mixSizes {
  let outA = newOut(tgs * threadsPerTG), outB = newOut(tgs * threadsPerTG)
  let iters = calibrate({ memJob(tgs: tgs, iters: $0, out: outA, dep: scratchDep) },
                        start: 2)
  pairs.append(Pair(name: "mem/mem", sizeLabel: "tg=\(tgs) iters=\(iters)",
                    a: memJob(tgs: tgs, iters: iters, out: outA, dep: scratchDep),
                    b: memJob(tgs: tgs, iters: iters, out: outB, dep: scratchDep),
                    rawDep: outA, tgCount: tgs, threadsPerTG: threadsPerTG))
}

for tgs in mixSizes {
  let outA = newOut(tgs * threadsPerTG), outB = newOut(tgs * threadsPerTG)
  let aIters = calibrate({ aluJob(tgs: tgs, iters: $0, out: outA, dep: scratchDep) },
                         start: 200_000)
  let bIters = calibrate({ memJob(tgs: tgs, iters: $0, out: outB, dep: scratchDep) },
                         start: 2)
  pairs.append(Pair(name: "alu/mem", sizeLabel: "tg=\(tgs) alu=\(aIters) mem=\(bIters)",
                    a: aluJob(tgs: tgs, iters: aIters, out: outA, dep: scratchDep),
                    b: memJob(tgs: tgs, iters: bIters, out: outB, dep: scratchDep),
                    rawDep: outA, tgCount: tgs, threadsPerTG: threadsPerTG))
}

// bf16 GEMMs. TS=16 tiles, so threadgroups = (N/16) * (M/16).
// small / half / fill relative to the 20-core device.
// K is calibrated per shape so every GEMM cell lands near targetMs; otherwise
// the occupancy sweep would confound threadgroup count with kernel duration.
let gemmShapes: [(String, Int, Int, Int)] = [
  ("small", 64, 64, 65536),    //   16 TGs
  ("half",  128, 160, 65536),  //   80 TGs
  ("fill",  512, 1024, 8192),  // 2048 TGs
]
for (label, m, n, probeK) in gemmShapes {
  let tgs = (m / 16) * (n / 16)
  func makeGemm(_ k: Int, _ aBuf: MTLBuffer, _ bBuf: MTLBuffer, _ out: MTLBuffer) -> Job {
    Job(pso: psoGemm, out: out, depIn: scratchDep,
        buffers: [(3, aBuf), (4, bBuf)],
        vec3: [(2, SIMD3<UInt32>(UInt32(m), UInt32(n), UInt32(k)))],
        grid: MTLSize(width: n / 16, height: m / 16, depth: 1),
        tg: MTLSize(width: 16, height: 16, depth: 1))
  }
  let pA = device.makeBuffer(length: m * probeK * 2, options: .storageModePrivate)!
  let pB = device.makeBuffer(length: probeK * n * 2, options: .storageModePrivate)!
  let pC = newOut(m * n)
  pinClocks(ms: 15)
  var probeMs = Double.infinity
  for _ in 0..<3 {
    let j = makeGemm(probeK, pA, pB, pC)
    probeMs = min(probeMs, runArm(.aOnly, a: j, b: j, rawDep: scratchDep).wallMs)
  }
  let k = max(1024, Int((Double(probeK) * targetMs / max(probeMs, 0.05)) / 16.0) * 16)
  let aBuf = device.makeBuffer(length: m * k * 2, options: .storageModePrivate)!
  let bBuf = device.makeBuffer(length: k * n * 2, options: .storageModePrivate)!
  let cA = newOut(m * n), cB = newOut(m * n)
  pairs.append(Pair(name: "gemm/gemm",
                    sizeLabel: "\(label) M=\(m) N=\(n) K=\(k) tg=\(tgs)",
                    a: makeGemm(k, aBuf, bBuf, cA), b: makeGemm(k, aBuf, bBuf, cB),
                    rawDep: cA, tgCount: tgs, threadsPerTG: 256))
}

// MARK: - measure

print("# arms")
print("pair,size,arm,wall_ms,busy_sum_ms,busy_union_ms,cbs,cbunion_overlap,cb_layout_ms")
var samples: [String: [Arm: [Sample]]] = [:]

for round in 0..<rounds {
  var cells: [(Int, Arm)] = []
  for (pi, _) in pairs.enumerated() { for arm in Arm.allCases { cells.append((pi, arm)) } }
  cells.shuffle()
  for (pi, arm) in cells {
    let p = pairs[pi]
    pinClocks(ms: 12)
    let s = runArm(arm, a: p.a, b: p.b, rawDep: p.rawDep)
    let key = "\(p.name)|\(p.sizeLabel)"
    samples[key, default: [:]][arm, default: []].append(s)
    if round == 0 {
      let ov = s.busySumMs > 0 ? 1 - s.busyUnionMs / s.busySumMs : 0
      let lay = s.layout.map { "[\(fmt($0.0, 3))-\(fmt($0.1, 3))]" }.joined(separator: " ")
      print("\(p.name),\(p.sizeLabel),\(arm.rawValue),\(fmt(s.wallMs)),\(fmt(s.busySumMs))," +
            "\(fmt(s.busyUnionMs)),\(s.cbs),\(fmt(ov, 6)),\(lay)")
    }
  }
}

print("")
// overlap     = 1 - wall(arm) / (wall_a + wall_b). Headline figure named by the
//               assignment. Its ceiling is 0.5 only when A and B cost the same.
// overlap_eff = (sum - wall) / (sum - max(a,b)). Fraction of the *achievable*
//               saving that was realised, so unequal pairs stay interpretable.
//               1.0 = the shorter kernel was fully hidden, 0.0 = pure serial.
print("# summary: within-round ratios; overlap = 1 - wall(arm)/(wall_a+wall_b);")
print("# overlap_eff = (iso_sum - wall)/(iso_sum - max(wall_a,wall_b))")
print("pair,size,arm,wall_ms_med,iso_sum_ms_med,iso_max_ms_med,overlap_med,overlap_lo," +
      "overlap_hi,overlap_eff_med,cb_busy_sum_med,cb_busy_union_med,cb_overlap_med")

for p in pairs {
  let key = "\(p.name)|\(p.sizeLabel)"
  guard let byArm = samples[key] else { continue }
  let aW = byArm[.aOnly]!.map { $0.wallMs }
  let bW = byArm[.bOnly]!.map { $0.wallMs }
  for arm in Arm.allCases {
    let ss = byArm[arm]!
    let ratios = (0..<ss.count).map { 1 - ss[$0].wallMs / (aW[$0] + bW[$0]) }
    let effs = (0..<ss.count).map { i -> Double in
      let sum = aW[i] + bW[i], mx = max(aW[i], bW[i])
      return sum - mx > 1e-9 ? (sum - ss[i].wallMs) / (sum - mx) : Double.nan
    }
    let (lo, hi) = bootstrapCI(ratios)
    let cbSum = median(ss.map { $0.busySumMs })
    let cbUni = median(ss.map { $0.busyUnionMs })
    let cbOv = cbSum > 0 ? 1 - cbUni / cbSum : 0
    print("\(p.name),\(p.sizeLabel),\(arm.rawValue),\(fmt(median(ss.map { $0.wallMs })))," +
          "\(fmt(median((0..<ss.count).map { aW[$0] + bW[$0] })))," +
          "\(fmt(median((0..<ss.count).map { max(aW[$0], bW[$0]) })))," +
          "\(fmt(median(ratios), 4)),\(fmt(lo, 4)),\(fmt(hi, 4)),\(fmt(median(effs), 4))," +
          "\(fmt(cbSum)),\(fmt(cbUni)),\(fmt(cbOv, 6))")
  }
}
