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

/// The kernel's own output is bfloat, whose 8-bit mantissa hides differences
/// below ~2e-3 relative. A one-ulp float32 reassociation therefore survives to
/// the output with probability ~1e-4 per value, which makes a bfloat-only
/// comparison unable to demonstrate its own sensitivity. `raw` replaces the
/// softplus epilogue with a float32 dump of the pre-rounding accumulator, so
/// the differential test runs at float32 resolution: strictly finer than the
/// property being certified, and fine enough for the control to bite.
func rawVariant(_ body: String) -> String {
    let tail = "for(uint row=0;row<R;++row){\n    r[row]=simd_sum(r[row]);"
    guard let cut = body.range(of: tail) else { die("raw: epilogue anchor not found") }
    return String(body[body.startIndex..<cut.lowerBound]) + """
    for(uint row=0;row<R;++row){
        r[row]=simd_sum(r[row]);
        if(lane==0){ gate_values[orow+row]=r[row]; }
    }
    """
}

/// Minimal stand-in for the signature MLX synthesises for `metalKernel`
/// (inputNames: input, packed_codes, scales, biases; outputNames: gate_values).
/// Only the body differs between geometries, so the wrapper is a shared
/// constant of the differential test.
func wrap(_ name: String, _ body: String, raw: Bool = false) -> String {
    preamble + """
    [[kernel]] void \(name)(
        const device bfloat* input [[buffer(0)]],
        const device uint* packed_codes [[buffer(1)]],
        const device bfloat* scales [[buffer(2)]],
        const device bfloat* biases [[buffer(3)]],
        device \(raw ? "float" : "bfloat")* gate_values [[buffer(4)]],
        uint3 threadgroup_position_in_grid [[threadgroup_position_in_grid]],
        uint simdgroup_index_in_threadgroup [[simdgroup_index_in_threadgroup]],
        uint thread_index_in_simdgroup [[thread_index_in_simdgroup]]) {
    \(body)
    }
    """
}

// ------------------------------------------------------------------ drift guard

let repo = arg("--repo", default: ".")

/// MLX compiles every JIT library as `metal::utils()` preamble + generated
/// source (backend/metal/custom_kernel.cpp), so the differential harness must
/// use the same preamble to see the same `log1p`, `bfloat`, and simd helpers.
let preamble: String = {
    let path = repo + "/Vendor/mlx-swift/Source/Cmlx/mlx-generated/utils.cpp"
    guard let data = FileManager.default.contents(atPath: path),
          let text = String(data: data, encoding: .utf8),
          let open = text.range(of: "R\"preamble("),
          let close = text.range(of: ")preamble\"", range: open.upperBound..<text.endIndex)
    else { die("preamble markers not found in \(path)") }
    return String(text[open.upperBound..<close.lowerBound])
}()

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

func pipeline(_ name: String, _ body: String, raw: Bool = false) -> MTLComputePipelineState {
    let src = wrap(name, raw ? rawVariant(body) : body, raw: raw)
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
    // The INT8 codes are unsigned with mean ~127.5, so the dot product tracks
    // 127.5 * sum(x) over 2048 columns. These ranges keep the pre-softplus
    // logit inside roughly [-8, 8]; larger scales drive softplus to 0 or to the
    // identity branch and the comparison stops discriminating.
    for i in 0..<(heads * KG) {
        let s = bf16Bits(rng.unit() * 2.0e-4 + 1.0e-5)
        let b = bf16Bits((rng.unit() * 2.0 - 1.0) * 5.0e-4)
        scales[2 * i] = UInt8(truncatingIfNeeded: s)
        scales[2 * i + 1] = UInt8(truncatingIfNeeded: s >> 8)
        biases[2 * i] = UInt8(truncatingIfNeeded: b)
        biases[2 * i + 1] = UInt8(truncatingIfNeeded: b >> 8)
    }
    return Payload(heads: heads, input: buffer(inputBytes), codes: buffer(codes),
                   scales: buffer(scales), biases: buffer(biases))
}

func run(_ state: MTLComputePipelineState, _ p: Payload,
         rows: Int, simdgroups: Int, raw: Bool = false) -> [UInt8] {
    let outBytes = p.heads * (raw ? 4 : 2)
    guard let out = device.makeBuffer(length: outBytes, options: .storageModeShared)
    else { die("alloc out") }
    memset(out.contents(), 0xAB, outBytes)
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
    return [UInt8](Data(bytes: out.contents(), count: outBytes))
}

// ------------------------------------------------------------------------ sweep

let headCounts = [64, 48]       // sliding, full
let geometries: [(Int, Int)] = [(4, 2), (4, 4), (4, 1), (2, 2), (2, 4), (2, 1),
                                (1, 2), (1, 4), (1, 1)]
let seeds: [UInt64] = [0x5EED_0001, 0x5EED_0002, 0x5EED_0003, 0x5EED_0004]

var failures = 0
var comparisons = 0

for raw in [false, true] {
  let tag = raw ? "f32" : "bf16"
  say("")
  say("--- resolution: \(raw ? "float32 pre-rounding accumulator" : "bfloat kernel output")")
  for heads in headCounts {
    let payloads = seeds.map { makePayload(heads: heads, seed: $0 &+ UInt64(heads)) }
    var reference: [[UInt8]] = []
    for (gi, g) in geometries.enumerated() {
        let (rows, ns) = g
        if heads % (rows * ns) != 0 { die("h\(heads) not divisible by R\(rows)*NS\(ns)") }
        let st = pipeline("gate_sp_\(tag)_h\(heads)_r\(rows)n\(ns)",
                          gateSoftplusBody(rows: rows, simdgroups: ns), raw: raw)
        let outs = payloads.map { run(st, $0, rows: rows, simdgroups: ns, raw: raw) }
        if gi == 0 {
            reference = outs
            if raw {
                say("h\(heads) R\(rows) NS\(ns) [\(tag)]: reference")
                continue
            }
            // Guard against a degenerate payload: if the logits underflow,
            // every gate value collapses to zero and equality is vacuous.
            var live = 0
            var distinct = Set<UInt16>()
            for r in 0..<heads {
                let v = UInt16(outs[0][2 * r]) | (UInt16(outs[0][2 * r + 1]) << 8)
                if v & 0x7F80 != 0 { live += 1 }
                distinct.insert(v)
            }
            say("h\(heads) R\(rows) NS\(ns): reference, \(live)/\(heads) normal gate values, "
                + "\(distinct.count) distinct")
            if live * 4 < heads * 3 || distinct.count * 4 < heads * 3 {
                die("degenerate payload for h\(heads): comparison would be vacuous")
            }
            continue
        }
        var bad = 0
        for (i, o) in outs.enumerated() where o != reference[i] { bad += 1 }
        comparisons += outs.count
        if bad == 0 {
            say("h\(heads) R\(rows) NS\(ns) [\(tag)]: BITWISE EQUAL on \(outs.count)/\(outs.count) "
                + "payloads (tiles=\(heads / (rows * ns)) tgWidth=\(ns * 32))")
        } else {
            failures += 1
            say("h\(heads) R\(rows) NS\(ns) [\(tag)]: MISMATCH on \(bad)/\(outs.count) payloads")
        }
    }
  }
}

// ------------------------------------------------------------- must-flag control

// Same R=4,NS=2 geometry, but the eight-term inner dot product accumulates in
// reverse index order. That is a pure reassociation: algebraically identical,
// bit-wise different, and exactly the class of drift a bit-exactness claim has
// to detect. If the harness cannot see it, the equalities above prove nothing.
//
// Two earlier controls were rejected as vacuous, and both failures are
// informative:
//   * seeding `r[0]=1e-30f` is lost to rounding against an O(1) accumulator;
//   * commuting `s*a+sum*b` to `sum*b+s*a` cannot be detected at all, because
//     IEEE-754 addition is exactly commutative.
// Reverse-order accumulation is a genuine reassociation, but it is still
// invisible in the kernel's own bfloat output: it moves the float32 total by
// ~1 ulp (~1e-7 relative) and bfloat only resolves ~2e-3, so the perturbation
// survives rounding with probability ~1e-4 per value. The control is therefore
// scored at float32 resolution, where the harness must see it.
var controlBody = gateSoftplusBody(rows: 4, simdgroups: 2)
controlBody = controlBody.replacingOccurrences(
    of: "for(uint i=0;i<V;++i) a+=x[i]*wl[i];",
    with: "for(uint i=V;i-->0;) a+=x[i]*wl[i];")
if controlBody == gateSoftplusBody(rows: 4, simdgroups: 2) { die("control perturbation did not apply") }
let controlPayload = makePayload(heads: 64, seed: 0x5EED_0001 &+ 64)
let refState = pipeline("gate_sp_ctl_ref", gateSoftplusBody(rows: 4, simdgroups: 2), raw: true)
let ctlState = pipeline("gate_sp_ctl_bad", controlBody, raw: true)
let refOut = run(refState, controlPayload, rows: 4, simdgroups: 2, raw: true)
let ctlOut = run(ctlState, controlPayload, rows: 4, simdgroups: 2, raw: true)
if refOut == ctlOut {
    say("CONTROL: perturbed kernel NOT flagged -- harness is blind, no certificate")
    failures += 1
} else {
    var moved = 0
    for r in 0..<64 where Array(refOut[4 * r..<4 * r + 4]) != Array(ctlOut[4 * r..<4 * r + 4]) {
        moved += 1
    }
    say("CONTROL: perturbed kernel flagged at float32 (\(moved)/64 rows differ)")
}

say("")
say(failures == 0
    ? "RESULT: PASS -- \(comparisons) payload comparisons bitwise equal across \(geometries.count) geometries"
    : "RESULT: FAIL -- \(failures) failing checks")
exit(failures == 0 ? 0 : 1)
