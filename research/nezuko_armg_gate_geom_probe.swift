// Research-only host harness (not part of the submission surface).
//
// Arm G rung 1c of PR #682. Blocks b1 (inline recompute) and b2 (threadgroup
// staging) both lost, and by more than the 260 us/step the removed
// `rmsbfloat16` dispatch is worth:
//
//   b1  candidate 8.6400 ms vs control 8.2953 ms  -> -344.8 us/step (-3.01%)
//   b2  candidate 8.9544 ms vs control 8.2540 ms  -> -700.4 us/step (-5.93%)
//
// Both arms are bit-exact, so the loss is pure cost. The shipped
// `laguna_gate_sp_h64_v1` dispatch is 8 threadgroups of 64 threads. A
// 2048-element RMS reduction spread over 64 threads has 8x less parallelism
// than the AOT `rms_single_row` laguna fast path, which uses 512 threads in one
// threadgroup and costs 3.47 us end to end. The 8 threadgroups run
// concurrently on distinct cores, so replication is nearly free -- what is not
// free is the per-threadgroup *latency* of 32 elements per thread with only two
// simdgroups available to hide memory latency.
//
// The prediction under test: fused cost falls roughly as 1/threads-per-
// threadgroup, so a wider threadgroup makes the fusion profitable. Total rows
// stay `heads`; each threadgroup owns NS*R rows, so (NS, R) trades threadgroup
// count against threadgroup width at constant arithmetic:
//
//   NS=2  R=4   8 TG x  64 thr   (shipped)
//   NS=4  R=2   8 TG x 128 thr
//   NS=4  R=4   4 TG x 128 thr
//   NS=8  R=1   8 TG x 256 thr
//   NS=8  R=2   4 TG x 256 thr
//   NS=16 R=1   4 TG x 512 thr
//   NS=16 R=2   2 TG x 512 thr
//
// Lowering R removes activation reuse inside a simdgroup, so each geometry is
// measured with a stock arm as well as a fused arm; only the fused-minus-stock
// difference at the *same* geometry is a fusion cost, and only the stock-minus-
// shipped difference is a geometry cost.
//
// Build and run:
//   xcrun swiftc -O research/nezuko_armg_gate_geom_probe.swift \
//     -o /tmp/nezgeom && /tmp/nezgeom

import Foundation
import Metal

let hidden = 2048
let heads = 64
let reps = 192

// MLX injects its own `log1p` into every `metalKernel` body (metal_stdlib has
// none), so the probe restates the same shape to keep the softplus epilogue's
// arithmetic and cost comparable with the shipped kernel.
let preamble = """
    #include <metal_stdlib>
    #include <metal_simdgroup>
    using namespace metal;
    using bfloat16_t = bfloat;

    inline float log1p(float x) {
      float xp1 = 1.0f + x;
      if (xp1 == metal::numeric_limits<float>::infinity()) {
        return metal::numeric_limits<float>::infinity();
      }
      if (xp1 == 1.0f) { return x; }
      return x * (metal::precise::log(xp1) / (xp1 - 1.0f));
    }

    """

// MARK: - Reference RMSNorm (AOT `rms_single_row` laguna fast path)

let rmsSource =
    preamble + """
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

// MARK: - Gate-softplus source generator

enum Mode: String {
    /// Shipped body: reads the already-normalized activation.
    case stock
    /// Fused: prologue, chunked stage into threadgroup memory, matvec reads it.
    case staged
    /// Fused: prologue, no staging, the normalize expression is re-evaluated at
    /// every `x[i]` load (block b1).
    case inline
    /// Timing-only decomposition: prologue and `normalized` emit are kept but
    /// the matvec still reads the separately supplied normalized activation, so
    /// the arm isolates prologue+emit from the staged-read cost.
    case emitOnly
    /// Fused, staged, plus two independent savings: the reduction keeps the
    /// residual elements it already loaded in registers so the stage pass does
    /// not reread them, and the `normalized` device store is split into one
    /// contiguous slice per threadgroup instead of being serialized in tile 0.
    case stagedFast
}

/// `sg` owns AOT chunks `CPS*sg .. CPS*sg+CPS-1`; lane `l` of chunk `g`
/// accumulates the same four contiguous squares in the same order into the same
/// `local_sums[g]` slot, so the 32-lane final `simd_sum` sees an identical
/// operand vector and the result is bit-identical to `rms_single_row`.
func prologue(_ ns: Int, keepRegisters: Bool = false) -> String {
    """
    threadgroup float laguna_norm_sums[32];
    threadgroup float laguna_norm_inv[1];
    constexpr uint CPS = 16 / NS;
    \(keepRegisters ? "thread float laguna_xr[CPS * 4];" : "")
    if (sg == 0 && lane >= 16) { laguna_norm_sums[lane] = 0; }
    for (uint chunk = 0; chunk < CPS; ++chunk) {
        const uint g = sg * CPS + chunk;
        const device bfloat* row_x = residual + g * 128 + lane * 4;
        float acc = 0;
        for (uint i = 0; i < 4; ++i) {
            float xi = float(row_x[i]);
            \(keepRegisters ? "laguna_xr[chunk * 4 + i] = xi;" : "")
            acc += xi * xi;
        }
        acc = simd_sum(acc);
        if (lane == 0) { laguna_norm_sums[g] = acc; }
    }
    threadgroup_barrier(mem_flags::mem_threadgroup);
    if (sg == 0) {
        float acc = simd_sum(laguna_norm_sums[lane]);
        if (lane == 0) {
            laguna_norm_inv[0] = metal::precise::rsqrt(acc / float(K) + 1.0e-6f);
        }
    }
    threadgroup_barrier(mem_flags::mem_threadgroup);
    const float laguna_inv_mean = laguna_norm_inv[0];

    """
}

/// Chunked emit: every thread writes the four contiguous elements it already
/// squared, so the store pattern matches the AOT epilogue.
func emit(_ staged: Bool) -> String {
    (staged ? "threadgroup bfloat laguna_norm_x[K];\n" : "")
        + """
        {
            const bool laguna_emit = (tile == 0);
            for (uint chunk = 0; chunk < CPS; ++chunk) {
                const uint base = (sg * CPS + chunk) * 128 + lane * 4;
                for (uint i = 0; i < 4; ++i) {
                    const bfloat v = bfloat(
                        norm_weight[base + i] * bfloat(float(residual[base + i]) * laguna_inv_mean));
        """
        + (staged ? "            laguna_norm_x[base + i] = v;\n" : "")
        + """
                    if (laguna_emit) { normalized[base + i] = v; }
                }
            }
        }
        threadgroup_barrier(mem_flags::mem_threadgroup);

        """
}

/// Register-sourced stage plus a contiguous per-threadgroup slice of the
/// `normalized` device store. Every threadgroup still stages the whole row, so
/// slicing the device store only removes duplicated traffic and the tile-0
/// straggler; it is not a cross-threadgroup dependency.
func emitFast() -> String {
    """
    threadgroup bfloat laguna_norm_x[K];
    for (uint chunk = 0; chunk < CPS; ++chunk) {
        const uint base = (sg * CPS + chunk) * 128 + lane * 4;
        for (uint i = 0; i < 4; ++i) {
            laguna_norm_x[base + i] = bfloat(
                norm_weight[base + i] * bfloat(laguna_xr[chunk * 4 + i] * laguna_inv_mean));
        }
    }
    threadgroup_barrier(mem_flags::mem_threadgroup);
    {
        constexpr uint TILES = \(heads) / (NS * R);
        constexpr uint GROUPS = K / 4;
        constexpr uint PER = (GROUPS + TILES - 1) / TILES;
        const uint lid = sg * 32 + lane;
        const uint g1 = metal::min(tile * PER + PER, GROUPS);
        for (uint g4 = tile * PER + lid; g4 < g1; g4 += NS * 32) {
            const uint base = g4 * 4;
            for (uint i = 0; i < 4; ++i) { normalized[base + i] = laguna_norm_x[base + i]; }
        }
    }

    """
}

func gateSource(_ mode: Mode, ns: Int, r: Int) -> String {
    let load: String
    switch mode {
    case .stock, .emitOnly: load = "x[i]=float(input[col+i]);"
    case .staged, .stagedFast: load = "x[i]=float(laguna_norm_x[col+i]);"
    case .inline:
        load =
            "x[i]=float(bfloat(norm_weight[col+i]*bfloat(float(residual[col+i])*laguna_inv_mean)));"
    }
    var body = """
        constexpr uint K=\(hidden),GS=32,V=8;
        constexpr uint BK=V*32,R=\(r),NS=\(ns),KG=K/GS,SS=GS/V;
        uint tile=threadgroup_position_in_grid.x;
        uint sg=simdgroup_index_in_threadgroup;
        uint lane=thread_index_in_simdgroup;

        """
    if mode == .stagedFast {
        body += prologue(ns, keepRegisters: true)
        body += emitFast()
    } else if mode != .stock {
        body += prologue(ns)
        body += emit(mode == .staged)
    }
    body += """
        uint orow=tile*(NS*R)+sg*R;
        const device uint8_t* ws=(const device uint8_t*)packed_codes+orow*K+lane*V;
        const device bfloat* sc=scales+orow*KG+lane/SS;
        const device bfloat* bs=biases+orow*KG+lane/SS;
        thread float x[V];
        thread float r[R];
        for(uint row=0;row<R;++row) r[row]=0.0f;
        uint col=lane*V;
        for(uint k=0;k<K;k+=BK){
            float sum=0.0f;
            for(uint i=0;i<V;++i){
                \(load)
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
    return preamble + """
        [[kernel]] void probe_gate(
          const device bfloat* input [[buffer(0)]],
          const device uint* packed_codes [[buffer(1)]],
          const device bfloat* scales [[buffer(2)]],
          const device bfloat* biases [[buffer(3)]],
          device bfloat* gate_values [[buffer(4)]],
          const device bfloat* residual [[buffer(5)]],
          const device bfloat* norm_weight [[buffer(6)]],
          device bfloat* normalized [[buffer(7)]],
          uint3 threadgroup_position_in_grid [[threadgroup_position_in_grid]],
          uint simdgroup_index_in_threadgroup [[simdgroup_index_in_threadgroup]],
          uint thread_index_in_simdgroup [[thread_index_in_simdgroup]]) {
        \(body)
        }
        """
}

// MARK: - Device

let device = MTLCreateSystemDefaultDevice()!
let queue = device.makeCommandQueue()!
print("=== device ===")
print("name                       \(device.name)")
print("architecture               \(device.architecture.name)")
print("maxThreadgroupMemoryLength \(device.maxThreadgroupMemoryLength) B")

func pipeline(_ source: String, _ entry: String, label: String) -> MTLComputePipelineState {
    let lib: MTLLibrary
    do { lib = try device.makeLibrary(source: source, options: nil) } catch {
        print("--- compile failed for \(label) ---")
        print(source)
        fatalError("\(error)")
    }
    return try! device.makeComputePipelineState(function: lib.makeFunction(name: entry)!)
}

// MARK: - Arms

struct Arm {
    let label: String
    let mode: Mode
    let ns: Int
    let r: Int
    var tiles: Int { heads / (ns * r) }
    var threads: Int { ns * 32 }
    let pipe: MTLComputePipelineState
    let gate: MTLBuffer
    let norm: MTLBuffer
}

let geometries: [(Int, Int)] = [(2, 4), (4, 2), (4, 4), (8, 1), (8, 2), (16, 1), (16, 2)]
var armSpecs: [(String, Mode, Int, Int)] = []
for (ns, r) in geometries {
    let tag = "ns\(ns)r\(r)"
    armSpecs.append(("S \(tag)", .stock, ns, r))
    armSpecs.append(("F \(tag)", .staged, ns, r))
}
armSpecs.append(("I ns2r4", .inline, 2, 4))
armSpecs.append(("I ns8r1", .inline, 8, 1))
armSpecs.append(("E ns2r4", .emitOnly, 2, 4))
armSpecs.append(("E ns8r1", .emitOnly, 8, 1))
for (ns, r) in [(4, 2), (8, 1), (8, 2), (16, 1)] {
    armSpecs.append(("G ns\(ns)r\(r)", .stagedFast, ns, r))
}

func buffer(_ bytes: Int) -> MTLBuffer {
    device.makeBuffer(length: bytes, options: .storageModeShared)!
}

let arms: [Arm] = armSpecs.map { label, mode, ns, r in
    Arm(
        label: label, mode: mode, ns: ns, r: r,
        pipe: pipeline(gateSource(mode, ns: ns, r: r), "probe_gate", label: label),
        gate: buffer(heads * 2), norm: buffer(hidden * 2))
}

print("\n=== pipelines ===")
for a in arms {
    print(
        "\(a.label.padding(toLength: 9, withPad: " ", startingAt: 0))"
            + "\(a.tiles) TG x \(a.threads) thr   tgmem \(a.pipe.staticThreadgroupMemoryLength) B"
            + "   maxTPTG \(a.pipe.maxTotalThreadsPerThreadgroup)")
    precondition(
        a.threads <= a.pipe.maxTotalThreadsPerThreadgroup,
        "\(a.label) needs \(a.threads) threads")
}

// MARK: - Fixtures

func bf16(_ f: Float) -> UInt16 {
    let b = f.bitPattern
    return UInt16(truncatingIfNeeded: (b &+ 0x7FFF &+ ((b >> 16) & 1)) >> 16)
}

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
func fill<T>(_ b: MTLBuffer, _ values: [T]) {
    values.withUnsafeBytes { b.contents().copyMemory(from: $0.baseAddress!, byteCount: $0.count) }
}

let residualBuf = buffer(hidden * 2)
let normWeightBuf = buffer(hidden * 2)
let normalizedRefBuf = buffer(hidden * 2)
let gateRefBuf = buffer(heads * 2)
fill(residualBuf, (0..<hidden).map { _ in bf16(0.9 * normal()) })
fill(normWeightBuf, (0..<hidden).map { _ in bf16(1.0 + 0.1 * normal()) })

// Eight independent gate banks so the 128 KB code plane cannot stay resident,
// matching the 30 sliding layers each touching their own bank once per step.
struct Bank {
    let codes: MTLBuffer
    let scales: MTLBuffer
    let biases: MTLBuffer
}
let banks: [Bank] = (0..<8).map { _ in
    let codes = buffer(heads * hidden)
    let cp = codes.contents().bindMemory(to: UInt32.self, capacity: heads * hidden / 4)
    for i in 0..<(heads * hidden / 4) { cp[i] = UInt32(truncatingIfNeeded: nextRand()) }
    let groups = heads * hidden / 32
    let scales = buffer(groups * 2)
    let biases = buffer(groups * 2)
    fill(scales, (0..<groups).map { _ in bf16(0.01 + 0.002 * uniform()) })
    fill(biases, (0..<groups).map { _ in bf16(-1.2 + 0.1 * normal()) })
    return Bank(codes: codes, scales: scales, biases: biases)
}

// MARK: - Dispatch

func run(_ pipe: MTLComputePipelineState, _ binds: [(Int, MTLBuffer)], _ tg: Int, _ thr: Int)
    -> Double
{
    let cb = queue.makeCommandBuffer()!
    let enc = cb.makeComputeCommandEncoder()!
    enc.setComputePipelineState(pipe)
    for (idx, buf) in binds { enc.setBuffer(buf, offset: 0, index: idx) }
    enc.dispatchThreadgroups(
        MTLSize(width: tg, height: 1, depth: 1),
        threadsPerThreadgroup: MTLSize(width: thr, height: 1, depth: 1))
    enc.endEncoding()
    cb.commit()
    cb.waitUntilCompleted()
    return (cb.gpuEndTime - cb.gpuStartTime) * 1e6
}

let rmsPipe = pipeline(rmsSource, "probe_rms", label: "rms")
func runRms() -> Double {
    run(rmsPipe, [(0, residualBuf), (1, normWeightBuf), (2, normalizedRefBuf)], 1, 512)
}

func runArm(_ a: Arm, _ b: Bank) -> Double {
    run(
        a.pipe,
        [
            (0, normalizedRefBuf), (1, b.codes), (2, b.scales), (3, b.biases), (4, a.gate),
            (5, residualBuf), (6, normWeightBuf), (7, a.norm),
        ], a.tiles, a.threads)
}

func words(_ b: MTLBuffer, _ n: Int) -> [UInt16] {
    let p = b.contents().bindMemory(to: UInt16.self, capacity: n)
    return Array(UnsafeBufferPointer(start: p, count: n))
}

// MARK: - Correctness

_ = runRms()
let normRef = words(normalizedRefBuf, hidden)
_ = runArm(arms[0], banks[0])
fill(gateRefBuf, words(arms[0].gate, heads))
let gateRef = words(gateRefBuf, heads)

print("\n=== correctness (vs AOT rms + shipped ns2r4 gate) ===")
var allExact = true
for a in arms {
    _ = runArm(a, banks[0])
    let g = words(a.gate, heads)
    let gateBad = zip(g, gateRef).filter { $0 != $1 }.count
    var normBad = -1
    if a.mode != .stock {
        normBad = zip(words(a.norm, hidden), normRef).filter { $0 != $1 }.count
    }
    let exact = gateBad == 0 && normBad <= 0
    allExact = allExact && exact
    print(
        "\(a.label.padding(toLength: 9, withPad: " ", startingAt: 0))"
            + "gate mismatches \(gateBad)/\(heads)"
            + (normBad >= 0 ? "   normalized mismatches \(normBad)/\(hidden)" : "")
            + "   \(exact ? "EXACT" : "DIVERGES")")
}
print("all arms bit-exact: \(allExact)")

// MARK: - Timing

var samples = [String: [Double]]()
var rmsSamples = [Double]()
for _ in 0..<24 {
    for a in arms { _ = runArm(a, banks[0]) }
    _ = runRms()
}
for rep in 0..<reps {
    let b = banks[rep % banks.count]
    rmsSamples.append(runRms())
    for a in arms.shuffled() { samples[a.label, default: []].append(runArm(a, b)) }
}

func median(_ v: [Double]) -> Double {
    let s = v.sorted()
    return s.count % 2 == 1 ? s[s.count / 2] : 0.5 * (s[s.count / 2 - 1] + s[s.count / 2])
}
func pct(_ v: [Double], _ q: Double) -> Double { v.sorted()[Int(Double(v.count - 1) * q)] }

let rmsMed = median(rmsSamples)
print("\n=== cost (us per dispatch, \(reps) samples, one command buffer each) ===")
print("AOT rms_single_row 1 TG x 512 thr   median \(String(format: "%7.3f", rmsMed))")
print("")
print("arm      geometry        median     p10     p90   vs stock ns2r4   vs same-geom stock")
let stockMed = Dictionary(
    uniqueKeysWithValues: geometries.map { ns, r in
        ("ns\(ns)r\(r)", median(samples["S ns\(ns)r\(r)"]!))
    })
let base = stockMed["ns2r4"]!
for a in arms {
    let v = samples[a.label]!
    let m = median(v)
    let same = stockMed["ns\(a.ns)r\(a.r)"]!
    print(
        "\(a.label.padding(toLength: 9, withPad: " ", startingAt: 0))"
            + "\("\(a.tiles)TGx\(a.threads)".padding(toLength: 12, withPad: " ", startingAt: 0))"
            + String(format: "%8.3f %7.3f %7.3f", m, pct(v, 0.1), pct(v, 0.9))
            + String(format: "   %+8.3f us", m - base)
            + String(format: "     %+8.3f us", m - same))
}

// MARK: - Score model

// 30 sliding layers dispatch `gate_sp_h64_v1`; removing the attention pre-norm
// removes 40 `rmsbfloat16` dispatches worth 138.8 us of busy time plus
// 40 x 3.03 us of inter-dispatch gap, and the M4 decode step is 8972 us with
// 75% of the score weight on decode.
let savedPerStep = 138.8 + 40.0 * 3.03
print("\n=== net score model (h64 arms scaled to 30 sliding layers) ===")
print(String(format: "removed pre-norm dispatches: %+8.1f us/step", savedPerStep))
print("arm      added us/layer   added us/step(x30)   net us/step   net score %")
for a in arms where a.mode != .stock {
    let added = median(samples[a.label]!) - stockMed["ns\(a.ns)r\(a.r)"]!
    let geom = stockMed["ns\(a.ns)r\(a.r)"]! - base
    let net = savedPerStep - (added + geom) * 30.0
    print(
        "\(a.label.padding(toLength: 9, withPad: " ", startingAt: 0))"
            + String(format: "%12.3f  %18.1f  %12.1f  %+11.3f", added, (added + geom) * 30.0, net,
                (pow(8972.0 / (8972.0 - net), 0.75) - 1.0) * 100.0))
}
