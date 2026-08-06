// PR #101 arm A: bit-for-bit differential certificate for every gate_sp
// (R, NS) dispatch geometry against the stock R=4, NS=2 geometry.
//
// The kernel bodies are read straight out of the scored runtime source
// (Sources/MLXFastModel/LagunaRuntimeModel.swift) by re-implementing the same
// string template, so the harness cannot drift from what MLX will compile.
// Each geometry is compiled into its own MTLLibrary in one process, run on
// identical random INT8 affine banks and identical bfloat16 activations, and
// the h64/h48 gate_values buffers are compared with memcmp.
//
// A deliberately corrupted control geometry must be flagged; a run in which the
// control passes is reported as a harness failure, not as a certificate.
//
// Build:
//   swiftc -O research/frieren_pr101_gatesp_bitwise.swift \
//     -o /tmp/frieren_pr101_gatesp -framework Metal -framework Foundation
// Run:
//   /tmp/frieren_pr101_gatesp --repo .

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

struct Rng {
    var s: UInt64
    init(_ seed: UInt64) { s = seed }
    mutating func next() -> UInt64 {
        s = s &+ 0x9E3779B97F4A7C15
        var z = s
        z = (z ^ (z >> 30)) &* 0xBF58476D1CE4E5B9
        z = (z ^ (z >> 27)) &* 0x94D049BB133111EB
        return z ^ (z >> 31)
    }
    mutating func unit() -> Float { Float(next() >> 40) * (1.0 / 16777216.0) }
    mutating func byte() -> UInt8 { UInt8(truncatingIfNeeded: next() >> 33) }
}

func bf16Bits(_ v: Float) -> UInt16 {
    let b = v.bitPattern
    let lo = b & 0xFFFF
    var hi = b >> 16
    if lo > 0x8000 || (lo == 0x8000 && (hi & 1) == 1) { hi &+= 1 }
    return UInt16(truncatingIfNeeded: hi)
}

let K = 2048            // LagunaConstants.hiddenSize
let KG = K / 32         // scale / bias groups per row

/// Byte-identical re-implementation of `lagunaGateSoftplusSource`
/// (LagunaRuntimeModel.swift). Kept literally in sync with the runtime; the
/// checker below diffs this template against the committed runtime source.
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

/// Minimal stand-in for the signature MLX synthesises for `metalKernel`
/// (inputNames: input, packed_codes, scales, biases; outputNames: gate_values).
/// Only the body differs between geometries, so the wrapper is a shared
/// constant of the differential test.
func wrap(_ name: String, _ body: String) -> String {
    """
    #include <metal_stdlib>
    using namespace metal;
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

// ------------------------------------------------------------------ drift guard

let repo = arg("--repo", default: ".")
let runtimePath = repo + "/Sources/MLXFastModel/LagunaRuntimeModel.swift"
guard let runtimeData = FileManager.default.contents(atPath: runtimePath),
      let runtimeText = String(data: runtimeData, encoding: .utf8) else {
    die("cannot read \(runtimePath)")
}
// The runtime template is parameterised; the R=4,NS=2 expansion differs from it
// only in the interpolated constants, so compare the invariant tail.
let anchor = "for(uint k=0;k<K;k+=BK){"
guard let a0 = runtimeText.range(of: anchor),
      let a1 = runtimeText.range(of: "\"\"\"", range: a0.upperBound..<runtimeText.endIndex) else {
    die("gate_sp body not found in runtime source")
}
let runtimeTail = String(runtimeText[a0.lowerBound..<a1.lowerBound])
    .trimmingCharacters(in: .whitespacesAndNewlines)
let localTail = String(gateSoftplusBody(rows: 4, simdgroups: 2)[
    gateSoftplusBody(rows: 4, simdgroups: 2).range(of: anchor)!.lowerBound...])
    .trimmingCharacters(in: .whitespacesAndNewlines)
if runtimeTail != localTail {
    die("harness body drifted from \(runtimePath); refusing to certify")
}
say("drift guard   : harness body matches runtime template tail (\(localTail.utf8.count) bytes)")

// ------------------------------------------------------------------- device set

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
} else {
    options.languageVersion = .version3_1
}
say("compile opts  : mathMode=safe languageVersion=\(options.languageVersion.rawValue)")

func pipeline(_ name: String, _ body: String) -> MTLComputePipelineState {
    let src = wrap(name, body)
    let lib: MTLLibrary
    do { lib = try device.makeLibrary(source: src, options: options) }
    catch { die("compile \(name): \(error)") }
    guard let fn = lib.makeFunction(name: name) else { die("no function \(name)") }
    do { return try device.makeComputePipelineState(function: fn) }
    catch { die("pipeline \(name): \(error)") }
}

// ---------------------------------------------------------------------- payload

func buffer(_ bytes: [UInt8]) -> MTLBuffer {
    guard let b = device.makeBuffer(bytes: bytes, length: bytes.count,
                                    options: .storageModeShared) else { die("alloc") }
    return b
}

/// Activations, INT8 codes, per-group scales and biases for one head count.
struct Payload {
    let heads: Int
    let input: MTLBuffer
    let codes: MTLBuffer
    let scales: MTLBuffer
    let biases: MTLBuffer
}

func makePayload(heads: Int, seed: UInt64) -> Payload {
    var rng = Rng(seed)
    var inputBytes = [UInt8](repeating: 0, count: K * 2)
    for i in 0..<K {
        // activations spanning both signs with a wide exponent range
        let v = (rng.unit() * 2.0 - 1.0) * powf(2.0, Float(Int(rng.next() % 9)) - 4.0)
        let b = bf16Bits(v)
        inputBytes[2 * i] = UInt8(truncatingIfNeeded: b)
        inputBytes[2 * i + 1] = UInt8(truncatingIfNeeded: b >> 8)
    }
    var codes = [UInt8](repeating: 0, count: heads * K)
    for i in 0..<codes.count { codes[i] = rng.byte() }
    var scales = [UInt8](repeating: 0, count: heads * KG * 2)
    var biases = [UInt8](repeating: 0, count: heads * KG * 2)
    for i in 0..<(heads * KG) {
        let s = bf16Bits((rng.unit() * 0.02 + 0.001))
        let b = bf16Bits((rng.unit() * 2.0 - 1.0) * 0.05)
        scales[2 * i] = UInt8(truncatingIfNeeded: s)
        scales[2 * i + 1] = UInt8(truncatingIfNeeded: s >> 8)
        biases[2 * i] = UInt8(truncatingIfNeeded: b)
        biases[2 * i + 1] = UInt8(truncatingIfNeeded: b >> 8)
    }
    return Payload(heads: heads, input: buffer(inputBytes), codes: buffer(codes),
                   scales: buffer(scales), biases: buffer(biases))
}

func run(_ state: MTLComputePipelineState, _ p: Payload,
         rows: Int, simdgroups: Int) -> [UInt8] {
    guard let out = device.makeBuffer(length: p.heads * 2, options: .storageModeShared)
    else { die("alloc out") }
    memset(out.contents(), 0xAB, p.heads * 2)
    guard let cb = queue.makeCommandBuffer(), let enc = cb.makeComputeCommandEncoder()
    else { die("encoder") }
    enc.setComputePipelineState(state)
    enc.setBuffer(p.input, offset: 0, index: 0)
    enc.setBuffer(p.codes, offset: 0, index: 1)
    enc.setBuffer(p.scales, offset: 0, index: 2)
    enc.setBuffer(p.biases, offset: 0, index: 3)
    enc.setBuffer(out, offset: 0, index: 4)
    let width = simdgroups * 32
    let tiles = p.heads / (simdgroups * rows)
    enc.dispatchThreads(MTLSize(width: tiles * width, height: 1, depth: 1),
                        threadsPerThreadgroup: MTLSize(width: width, height: 1, depth: 1))
    enc.endEncoding()
    cb.commit()
    cb.waitUntilCompleted()
    if let e = cb.error { die("gpu error: \(e)") }
    return [UInt8](Data(bytes: out.contents(), count: p.heads * 2))
}

// ------------------------------------------------------------------------ sweep

let headCounts = [64, 48]       // sliding, full
let geometries: [(Int, Int)] = [(4, 2), (4, 4), (4, 1), (2, 2), (2, 4), (2, 1),
                                (1, 2), (1, 4), (1, 1)]
let seeds: [UInt64] = [0x5EED_0001, 0x5EED_0002, 0x5EED_0003, 0x5EED_0004]

var failures = 0
var comparisons = 0

for heads in headCounts {
    let payloads = seeds.map { makePayload(heads: heads, seed: $0 &+ UInt64(heads)) }
    var reference: [[UInt8]] = []
    for (gi, g) in geometries.enumerated() {
        let (rows, ns) = g
        if heads % (rows * ns) != 0 { die("h\(heads) not divisible by R\(rows)*NS\(ns)") }
        let st = pipeline("gate_sp_h\(heads)_r\(rows)n\(ns)", gateSoftplusBody(rows: rows, simdgroups: ns))
        let outs = payloads.map { run(st, $0, rows: rows, simdgroups: ns) }
        if gi == 0 {
            reference = outs
            let nz = outs[0].enumerated().filter { $0.offset % 2 == 1 && $0.element != 0 }.count
            say("h\(heads) R\(rows) NS\(ns): reference, \(nz)/\(heads) non-zero high bytes")
            continue
        }
        var bad = 0
        for (i, o) in outs.enumerated() where o != reference[i] { bad += 1 }
        comparisons += outs.count
        if bad == 0 {
            say("h\(heads) R\(rows) NS\(ns): BITWISE EQUAL on \(outs.count)/\(outs.count) payloads "
                + "(tiles=\(heads / (rows * ns)) tgWidth=\(ns * 32))")
        } else {
            failures += 1
            say("h\(heads) R\(rows) NS\(ns): MISMATCH on \(bad)/\(outs.count) payloads")
        }
    }
}

// ------------------------------------------------------------- must-flag control

// Same R=4,NS=2 geometry but with the accumulator seeded to a non-zero value.
// The harness is only a certificate if this is detected.
var controlBody = gateSoftplusBody(rows: 4, simdgroups: 2)
controlBody = controlBody.replacingOccurrences(
    of: "thread float r[R]={0.0f,0.0f,0.0f,0.0f};",
    with: "thread float r[R]={1e-30f,0.0f,0.0f,0.0f};")
if controlBody == gateSoftplusBody(rows: 4, simdgroups: 2) { die("control perturbation did not apply") }
let controlPayload = makePayload(heads: 64, seed: 0x5EED_0001 &+ 64)
let refState = pipeline("gate_sp_ctl_ref", gateSoftplusBody(rows: 4, simdgroups: 2))
let ctlState = pipeline("gate_sp_ctl_bad", controlBody)
let refOut = run(refState, controlPayload, rows: 4, simdgroups: 2)
let ctlOut = run(ctlState, controlPayload, rows: 4, simdgroups: 2)
if refOut == ctlOut {
    say("CONTROL: perturbed kernel NOT flagged -- harness is blind, no certificate")
    failures += 1
} else {
    say("CONTROL: perturbed kernel flagged (expected)")
}

say("")
say(failures == 0
    ? "RESULT: PASS -- \(comparisons) payload comparisons bitwise equal across \(geometries.count) geometries"
    : "RESULT: FAIL -- \(failures) failing checks")
exit(failures == 0 ? 0 : 1)
