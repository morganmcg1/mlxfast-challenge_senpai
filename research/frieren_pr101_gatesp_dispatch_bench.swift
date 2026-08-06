// PR #101 arm A discriminator: isolate gate_sp per-dispatch cost from the fixed
// Metal launch floor, per (R, NS) geometry, with no model load.
//
// The end-to-end R x NS sweep was flat. Two explanations survive that result:
//   (a) gate_sp wall time is dominated by fixed per-dispatch overhead, so
//       intra-dispatch occupancy cannot move it; or
//   (b) the kernel is memory-latency bound and the sweep holds total
//       memory-level parallelism invariant (concurrent load streams == heads,
//       however rows are distributed over simdgroups), so it is flat by
//       construction.
// The end-to-end sweep cannot tell those apart. This harness can:
//   serial(gate_sp) - serial(empty) = isolated kernel execution time.
// If that difference is near zero, (a) holds. If it is large but constant
// across geometries, (b) holds.
//
// A concurrent-encoder arm is measured alongside the serial arm. MLX encodes
// with MTLDispatchTypeConcurrent plus explicit hazard barriers
// (Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp:548, :324-365),
// so the serial arm models the dependent decode chain and the concurrent arm
// bounds what wave-sharing between independent dispatches could buy.
//
// Every dispatch reads a distinct weight slot so the weights are cold, as they
// are in the real decode step; a naive repeat-the-same-dispatch loop would time
// a cache-resident kernel and understate execution.
//
// Build:
//   swiftc -O research/frieren_pr101_gatesp_dispatch_bench.swift \
//     -o /tmp/frieren_pr101_bench -framework Metal -framework Foundation
// Run:
//   /tmp/frieren_pr101_bench --repo .

import Foundation
import Metal

func die(_ m: String) -> Never {
    FileHandle.standardError.write(Data(("FATAL: " + m + "\n").utf8))
    exit(2)
}
func say(_ m: String) { print(m); fflush(stdout) }
func arg(_ n: String, default d: String) -> String {
    let a = CommandLine.arguments
    guard let i = a.firstIndex(of: n), i + 1 < a.count else { return d }
    return a[i + 1]
}

let K = 2048
let KG = K / 32

func gateSoftplusBody(rows: Int, simdgroups: Int) -> String {
    let seed = Array(repeating: "0.0f", count: rows).joined(separator: ",")
    return """
constexpr uint K=\(K),GS=32,V=8;
constexpr uint BK=V*32,R=\(rows),NS=\(simdgroups),KG=K/GS,SS=GS/V;
uint tile=threadgroup_position_in_grid.x;
uint sg=simdgroup_index_in_threadgroup;
uint lane=thread_index_in_simdgroup;
uint orow=tile*(NS*R)+sg*R;
const device uint8_t* ws=(const device uint8_t*)packed_codes+orow*K+lane*V;
const device bfloat* sc=scales+orow*KG+lane/SS;
const device bfloat* bs=biases+orow*KG+lane/SS;
thread float x[V];
thread float r[R]={\(seed)};
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

let repo = arg("--repo", default: ".")

let preamble: String = {
    let path = repo + "/Vendor/mlx-swift/Source/Cmlx/mlx-generated/utils.cpp"
    guard let data = FileManager.default.contents(atPath: path),
          let text = String(data: data, encoding: .utf8),
          let open = text.range(of: "R\"preamble("),
          let close = text.range(of: ")preamble\"", range: open.upperBound..<text.endIndex)
    else { die("preamble markers not found in \(path)") }
    return String(text[open.upperBound..<close.lowerBound])
}()

// Same drift guard as research/frieren_pr101_gatesp_bitwise.swift: a benchmark of
// a body that no longer matches the runtime measures nothing.
let runtimePath = repo + "/Sources/MLXFastModel/LagunaRuntimeModel.swift"
guard let runtimeData = FileManager.default.contents(atPath: runtimePath),
      let runtimeText = String(data: runtimeData, encoding: .utf8) else {
    die("cannot read \(runtimePath)")
}
let anchor = "for(uint k=0;k<K;k+=BK){"
guard let a0 = runtimeText.range(of: anchor),
      let a1 = runtimeText.range(of: "\"\"\"", range: a0.upperBound..<runtimeText.endIndex) else {
    die("gate_sp body not found in runtime source")
}
let runtimeTail = String(runtimeText[a0.lowerBound..<a1.lowerBound])
    .trimmingCharacters(in: .whitespacesAndNewlines)
let ref = gateSoftplusBody(rows: 4, simdgroups: 2)
let localTail = String(ref[ref.range(of: anchor)!.lowerBound...])
    .trimmingCharacters(in: .whitespacesAndNewlines)
if runtimeTail != localTail { die("harness body drifted from \(runtimePath)") }
say("drift guard   : harness body matches runtime template tail (\(localTail.utf8.count) bytes)")

guard let device = MTLCreateSystemDefaultDevice() else { die("no Metal device") }
guard let queue = device.makeCommandQueue() else { die("no command queue") }
say("host          : \(ProcessInfo.processInfo.operatingSystemVersionString)")
say("device        : \(device.name)")

let options = MTLCompileOptions()
options.mathMode = .safe
if #available(macOS 26.0, *) {
    options.languageVersion = .version4_0
} else if #available(macOS 15.0, *) {
    options.languageVersion = .version3_2
}

func wrap(_ name: String, _ body: String) -> String {
    preamble + """
    [[kernel]] void \(name)(
        const device bfloat* input [[buffer(0)]],
        const device uint* packed_codes [[buffer(1)]],
        const device bfloat* scales [[buffer(2)]],
        const device bfloat* biases [[buffer(3)]],
        device bfloat* gate_values [[buffer(4)]],
        uint3 threadgroup_position_in_grid [[threadgroup_position_in_grid]],
        uint simdgroup_index_in_threadgroup [[simdgroup_index_in_threadgroup]],
        uint thread_index_in_simdgroup [[thread_index_in_simdgroup]]) {
    \(body)
    }
    """
}

func pipeline(_ name: String, _ body: String) -> MTLComputePipelineState {
    let lib: MTLLibrary
    do { lib = try device.makeLibrary(source: wrap(name, body), options: options) }
    catch { die("compile \(name): \(error)") }
    guard let fn = lib.makeFunction(name: name) else { die("no function \(name)") }
    do { return try device.makeComputePipelineState(function: fn) }
    catch { die("pipeline \(name): \(error)") }
}

// ------------------------------------------------------------------- payload

/// Number of dispatches per command buffer. Also the number of distinct weight
/// slots, so no dispatch in a command buffer re-reads another's weights.
let N = Int(arg("--dispatches", default: "400"))!
let REPS = Int(arg("--reps", default: "12"))!
let WARM = 3

struct Bank {
    let heads: Int
    let input: MTLBuffer
    let codes: MTLBuffer      // N slots of heads*K bytes
    let scales: MTLBuffer     // N slots of heads*KG*2 bytes
    let biases: MTLBuffer
    let out: MTLBuffer
    let codeSlot: Int
    let scaleSlot: Int
}

func makeBank(heads: Int) -> Bank {
    let codeSlot = heads * K
    let scaleSlot = heads * KG * 2
    func alloc(_ n: Int) -> MTLBuffer {
        guard let b = device.makeBuffer(length: n, options: .storageModePrivate)
        else { die("alloc \(n)") }
        return b
    }
    guard let input = device.makeBuffer(length: K * 2, options: .storageModePrivate)
    else { die("alloc input") }
    guard let out = device.makeBuffer(length: heads * 2, options: .storageModePrivate)
    else { die("alloc out") }
    return Bank(heads: heads, input: input,
                codes: alloc(codeSlot * N), scales: alloc(scaleSlot * N),
                biases: alloc(scaleSlot * N), out: out,
                codeSlot: codeSlot, scaleSlot: scaleSlot)
}

let banks = [64: makeBank(heads: 64), 48: makeBank(heads: 48)]
say("payload       : \(N) cold weight slots/CB = "
    + String(format: "%.1f MB (h64), %.1f MB (h48)",
             Double(64 * K * N) / 1e6, Double(48 * K * N) / 1e6))

// --------------------------------------------------------------------- timing

/// Median GPU wall time per dispatch, in microseconds.
func measure(_ state: MTLComputePipelineState, _ bank: Bank,
             rows: Int, simdgroups: Int, concurrent: Bool) -> Double {
    let width = simdgroups * 32
    let tiles = bank.heads / (simdgroups * rows)
    let grid = MTLSize(width: tiles * width, height: 1, depth: 1)
    let tg = MTLSize(width: width, height: 1, depth: 1)
    var samples: [Double] = []
    for rep in 0..<REPS {
        guard let cb = queue.makeCommandBuffer(),
              let enc = cb.makeComputeCommandEncoder(
                dispatchType: concurrent ? .concurrent : .serial)
        else { die("encoder") }
        enc.setComputePipelineState(state)
        enc.setBuffer(bank.input, offset: 0, index: 0)
        enc.setBuffer(bank.out, offset: 0, index: 4)
        for i in 0..<N {
            enc.setBuffer(bank.codes, offset: i * bank.codeSlot, index: 1)
            enc.setBuffer(bank.scales, offset: i * bank.scaleSlot, index: 2)
            enc.setBuffer(bank.biases, offset: i * bank.scaleSlot, index: 3)
            enc.dispatchThreads(grid, threadsPerThreadgroup: tg)
        }
        enc.endEncoding()
        cb.commit()
        cb.waitUntilCompleted()
        if let e = cb.error { die("gpu error: \(e)") }
        if rep >= WARM {
            samples.append((cb.gpuEndTime - cb.gpuStartTime) * 1e6 / Double(N))
        }
    }
    samples.sort()
    return samples[samples.count / 2]
}

// ----------------------------------------------------------------------- run

let geometries: [(Int, Int)] = [(4, 2), (4, 4), (4, 1), (2, 2), (2, 4), (2, 1),
                                (1, 2), (1, 4), (1, 1)]

say("")
say("per-dispatch GPU time, microseconds (median of \(REPS - WARM) command buffers"
    + " of \(N) dispatches)")
say("")
say("heads geom     ser_gate ser_empty  ser_exec   con_gate con_empty  con_exec"
    + "   ser/con")

var rows: [(Int, String, Double, Double, Double, Double)] = []
for heads in [64, 48] {
    let bank = banks[heads]!
    for (r, ns) in geometries {
        let tag = "R\(r)NS\(ns)"
        let gate = pipeline("gate_h\(heads)_r\(r)n\(ns)", gateSoftplusBody(rows: r, simdgroups: ns))
        let empty = pipeline("empty_h\(heads)_r\(r)n\(ns)", ";")
        let sg = measure(gate, bank, rows: r, simdgroups: ns, concurrent: false)
        let se = measure(empty, bank, rows: r, simdgroups: ns, concurrent: false)
        let cg = measure(gate, bank, rows: r, simdgroups: ns, concurrent: true)
        let ce = measure(empty, bank, rows: r, simdgroups: ns, concurrent: true)
        say(String(format: "  %3d %-8s %8.3f %9.3f %9.3f  %9.3f %9.3f %9.3f %9.2fx",
                   heads, (tag as NSString).utf8String!, sg, se, sg - se, cg, ce, cg - ce,
                   cg > 0 ? sg / cg : 0))
        rows.append((heads, tag, sg, se, cg, ce))
    }
}

say("")
let stock64 = rows.first { $0.0 == 64 && $0.1 == "R4NS2" }!
let stock48 = rows.first { $0.0 == 48 && $0.1 == "R4NS2" }!
// Real decode step issues 30 h64 + 10 h48 gate_sp dispatches.
let stepUs = 30.0 * stock64.2 + 10.0 * stock48.2
say(String(format: "stock serial gate_sp per step : 30 x %.3f + 10 x %.3f = %.1f us",
           stock64.2, stock48.2, stepUs))
let floorUs = 30.0 * stock64.3 + 10.0 * stock48.3
say(String(format: "fixed launch floor per step   : 30 x %.3f + 10 x %.3f = %.1f us (%.0f%%)",
           stock64.3, stock48.3, floorUs, 100.0 * floorUs / stepUs))
for heads in [64, 48] {
    let fam = rows.filter { $0.0 == heads }
    let execs = fam.map { $0.2 - $0.3 }
    let lo = execs.min()!, hi = execs.max()!
    let st = fam.first { $0.1 == "R4NS2" }!
    say(String(format: "h%-3d isolated exec across geometries: %.3f..%.3f us (stock %.3f, spread %.1f%%)",
               heads, lo, hi, st.2 - st.3, lo > 0 ? 100.0 * (hi - lo) / lo : 0))
}
