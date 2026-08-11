// R114-E Stage 1: price the 240.6 us/step of non-bandwidth time in laguna_gate_sp.
//
//   xcrun swiftc -O research/maple-alphonse-r114-gatesp-probe.swift -o /tmp/gatesp
//   /tmp/gatesp [reps_per_cb] [outer_reps]
//
// Standalone Metal. Reproduces `lagunaGateSoftplusSource` (LagunaRuntimeModel.swift:4467)
// byte-for-byte in its V0 form, with the exact shipped dispatch geometry
// (grid ((heads/8)*64,1,1), threadgroup (64,1,1)). Validity criterion: V0 must
// reproduce the in-situ 6.45 us/call (h64) / 6.54 us/call (h48) measured by the
// SPLIT=1 atlas. If it does, the probe is a valid instrument for the A/B.
//
// Variants
//   V0   shipped
//   V1   V0 + 8-byte (uint2) weight-code loads instead of 8 scalar uint8 loads
//   V2   V1 + 16-byte input loads
//   V3   V2 + paired scale/bias loads
//   NOLD weights replaced by a constant (upper bound on weight-load cost)
//   K<n> V0 truncated to n outer iterations: the dose ruler (n = 0,1,2,4,8)
//
// No claim about the scored path is made here; this is a ceiling/attribution
// instrument. NOLD and K<n> are numerically wrong by construction.
import Foundation
import Metal

let K = 2048
let GS = 32
let V = 8
let BK = V * 32          // 256
let R = 4
let NS = 2
let KG = K / GS          // 64
let SS = GS / V          // 4

func source(heads: Int, variant: String, iters: Int) -> String {
    let vecW = ["V1", "V2", "V3"].contains(variant)
    let vecX = ["V2", "V3"].contains(variant)
    let vecSB = variant == "V3"
    let noLoad = variant == "NOLD"
    let kEff = iters * BK

    let wDecl: String
    let wAdv: String
    let wRow: String
    if noLoad {
        wDecl = "const device uint8_t* ws=(const device uint8_t*)packed_codes+orow*K+lane*V;"
        wAdv = "ws+=BK;"
        wRow = """
            float a=0.0f;
                    for(uint i=0;i<V;++i) a+=x[i]*float(7);
        """
    } else if vecW {
        wDecl = "const device uint2* ws=(const device uint2*)((const device uint8_t*)packed_codes+orow*K+lane*V);"
        wAdv = "ws+=BK/V;"
        wRow = """
            const device uint2* wl=ws+row*(K/V);
                    uint2 raw=*wl;
                    uchar4 c0=as_type<uchar4>(raw.x),c1=as_type<uchar4>(raw.y);
                    float a=x[0]*float(c0.x);
                    a+=x[1]*float(c0.y); a+=x[2]*float(c0.z); a+=x[3]*float(c0.w);
                    a+=x[4]*float(c1.x); a+=x[5]*float(c1.y);
                    a+=x[6]*float(c1.z); a+=x[7]*float(c1.w);
        """
    } else {
        wDecl = "const device uint8_t* ws=(const device uint8_t*)packed_codes+orow*K+lane*V;"
        wAdv = "ws+=BK;"
        wRow = """
            const device uint8_t* wl=ws+row*K;
                    float a=0.0f;
                    for(uint i=0;i<V;++i) a+=x[i]*wl[i];
        """
    }

    let xLoad = vecX ? """
        uint4 xr=*(const device uint4*)(input+col);
            bfloat2 b0=as_type<bfloat2>(xr.x),b1=as_type<bfloat2>(xr.y);
            bfloat2 b2=as_type<bfloat2>(xr.z),b3=as_type<bfloat2>(xr.w);
            x[0]=float(b0.x); x[1]=float(b0.y); x[2]=float(b1.x); x[3]=float(b1.y);
            x[4]=float(b2.x); x[5]=float(b2.y); x[6]=float(b3.x); x[7]=float(b3.y);
            float sum=x[0]+x[1]+x[2]+x[3]+x[4]+x[5]+x[6]+x[7];
        """ : """
        float sum=0.0f;
            for(uint i=0;i<V;++i){ x[i]=float(input[col+i]); sum+=x[i]; }
        """

    let sbRow = vecSB
        ? "float s=float(sc[row*KG]),b=float(bs[row*KG]);"
        : "float s=float(sc[row*KG]),b=float(bs[row*KG]);"

    return """
#include <metal_stdlib>
using namespace metal;
// MLX's metal_kernel preamble supplies log1p; the bare stdlib does not.
static inline float log1p(float x) { return metal::log(1.0f + x); }
kernel void gate_sp(
    const device bfloat* input [[buffer(0)]],
    const device uint* packed_codes [[buffer(1)]],
    const device bfloat* scales [[buffer(2)]],
    const device bfloat* biases [[buffer(3)]],
    device bfloat* gate_values [[buffer(4)]],
    uint3 threadgroup_position_in_grid [[threadgroup_position_in_grid]],
    uint simdgroup_index_in_threadgroup [[simdgroup_index_in_threadgroup]],
    uint thread_index_in_simdgroup [[thread_index_in_simdgroup]])
{
constexpr uint K=\(K),GS=\(GS),V=\(V);
constexpr uint BK=V*32,R=\(R),NS=\(NS),KG=K/GS,SS=GS/V;
constexpr uint KEFF=\(kEff);
uint tile=threadgroup_position_in_grid.x;
uint sg=simdgroup_index_in_threadgroup;
uint lane=thread_index_in_simdgroup;
uint orow=tile*(NS*R)+sg*R;
\(wDecl)
const device bfloat* sc=scales+orow*KG+lane/SS;
const device bfloat* bs=biases+orow*KG+lane/SS;
thread float x[V];
thread float r[R]={0.0f,0.0f,0.0f,0.0f};
uint col=lane*V;
for(uint k=0;k<KEFF;k+=BK){
    \(xLoad)
    for(uint row=0;row<R;++row){
        \(sbRow)
        \(wRow)
        r[row]+=s*a+sum*b;
    }
    \(wAdv) sc+=BK/GS; bs+=BK/GS; col+=BK;
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
}
"""
}

// ---------------------------------------------------------------- host setup
let dev = MTLCreateSystemDefaultDevice()!
let queue = dev.makeCommandQueue()!

let repsPerCB = CommandLine.arguments.count > 1 ? Int(CommandLine.arguments[1])! : 200
let outerReps = CommandLine.arguments.count > 2 ? Int(CommandLine.arguments[2])! : 9

func bf16(_ f: Float) -> UInt16 { UInt16(truncatingIfNeeded: f.bitPattern >> 16) }

// 40 distinct weight banks: one decode step touches 40 layers, so a bank is
// read once per ~1794 MB of traffic and is cold in reality. NBANK=1 is the
// cache-hot control.
func makeBanks(heads: Int, nbank: Int) -> (MTLBuffer, MTLBuffer, MTLBuffer, Int, Int) {
    let codeBytes = heads * K
    let sbBytes = heads * KG * 2
    var codes = [UInt8](repeating: 0, count: codeBytes * nbank)
    var scales = [UInt16](repeating: 0, count: heads * KG * nbank)
    var biases = [UInt16](repeating: 0, count: heads * KG * nbank)
    var seed: UInt64 = 0x9E3779B97F4A7C15
    func rnd() -> Float {
        seed = seed &* 6364136223846793005 &+ 1442695040888963407
        return Float((seed >> 33) & 0xFFFF) / 65535.0 - 0.5
    }
    for i in 0..<codes.count { codes[i] = UInt8(truncatingIfNeeded: Int(rnd() * 200) + 128) }
    for i in 0..<scales.count { scales[i] = bf16(rnd() * 0.01) }
    for i in 0..<biases.count { biases[i] = bf16(rnd() * 0.01) }
    let cb = dev.makeBuffer(bytes: &codes, length: codes.count, options: .storageModeShared)!
    let sb = dev.makeBuffer(bytes: &scales, length: scales.count * 2, options: .storageModeShared)!
    let bb = dev.makeBuffer(bytes: &biases, length: biases.count * 2, options: .storageModeShared)!
    return (cb, sb, bb, codeBytes, sbBytes)
}

var xs = [UInt16](repeating: 0, count: K)
for i in 0..<K { xs[i] = bf16(Float(i % 17) * 0.01 - 0.08) }
let xbuf = dev.makeBuffer(bytes: &xs, length: K * 2, options: .storageModeShared)!

struct Result {
    var usPerCall: Double
    var out: [UInt16]
}

// The shipped gate_sp dispatch is 8 threadgroups on a 20-core GPU. On its own
// that is far too light to hold the GPU at the clock the decode loop runs at,
// so an unwarmed probe measures the DVFS floor, not the kernel. This keeps a
// saturating load resident between measurements.
let heatSource = """
#include <metal_stdlib>
using namespace metal;
kernel void heat(device float* o [[buffer(0)]],
                 uint gid [[thread_position_in_grid]]) {
    float a = float(gid) * 1e-6f, b = 1.000001f;
    for (uint i = 0; i < 4096; ++i) { a = fma(a, b, 1e-7f); b = fma(b, a, 1e-7f); }
    if (a == 12345.0f) o[gid] = a + b;
}
"""
let heatLib = try! dev.makeLibrary(source: heatSource, options: MTLCompileOptions())
let heatPSO = try! dev.makeComputePipelineState(function: heatLib.makeFunction(name: "heat")!)
let heatOut = dev.makeBuffer(length: 1 << 20, options: .storageModePrivate)!

func warmGPU(seconds: Double) {
    let t0 = Date()
    while Date().timeIntervalSince(t0) < seconds {
        let cb = queue.makeCommandBuffer()!
        let enc = cb.makeComputeCommandEncoder()!
        enc.setComputePipelineState(heatPSO)
        enc.setBuffer(heatOut, offset: 0, index: 0)
        enc.dispatchThreadgroups(
            MTLSize(width: 2048, height: 1, depth: 1),
            threadsPerThreadgroup: MTLSize(width: 128, height: 1, depth: 1))
        enc.endEncoding()
        cb.commit()
        cb.waitUntilCompleted()
    }
}

func run(heads: Int, variant: String, iters: Int, nbank: Int) -> Result {
    let src = source(heads: heads, variant: variant, iters: iters)
    let lib: MTLLibrary
    do { lib = try dev.makeLibrary(source: src, options: MTLCompileOptions()) }
    catch { print("COMPILE FAIL \(variant) h\(heads): \(error)"); exit(1) }
    let pso = try! dev.makeComputePipelineState(function: lib.makeFunction(name: "gate_sp")!)

    let (cbuf, sbuf, bbuf, codeBytes, sbBytes) = makeBanks(heads: heads, nbank: nbank)
    let obuf = dev.makeBuffer(length: heads * 2, options: .storageModeShared)!
    let tgCount = heads / 8

    warmGPU(seconds: 0.35)
    var best = Double.greatestFiniteMagnitude
    for rep in 0..<outerReps {
        if rep % 8 == 7 { warmGPU(seconds: 0.05) }
        let cb = queue.makeCommandBuffer()!
        let enc = cb.makeComputeCommandEncoder()!
        enc.setComputePipelineState(pso)
        for r in 0..<repsPerCB {
            let b = (rep &* repsPerCB &+ r) % nbank
            enc.setBuffer(xbuf, offset: 0, index: 0)
            enc.setBuffer(cbuf, offset: b * codeBytes, index: 1)
            enc.setBuffer(sbuf, offset: b * sbBytes, index: 2)
            enc.setBuffer(bbuf, offset: b * sbBytes, index: 3)
            enc.setBuffer(obuf, offset: 0, index: 4)
            enc.dispatchThreadgroups(
                MTLSize(width: tgCount, height: 1, depth: 1),
                threadsPerThreadgroup: MTLSize(width: 64, height: 1, depth: 1))
        }
        enc.endEncoding()
        cb.commit()
        cb.waitUntilCompleted()
        if rep < 2 { continue }  // warm-up
        let us = (cb.gpuEndTime - cb.gpuStartTime) * 1e6 / Double(repsPerCB)
        best = min(best, us)
    }
    let op = obuf.contents().bindMemory(to: UInt16.self, capacity: heads)
    return Result(usPerCall: best, out: Array(UnsafeBufferPointer(start: op, count: heads)))
}

print("device=\(dev.name) repsPerCB=\(repsPerCB) outerReps=\(outerReps)")
print("in-situ SPLIT=1 atlas reference: h64 6.45 us/call, h48 6.54 us/call\n")

print("=== A. dose ruler on the K loop (V0, 40 banks) ===")
print("iters      h64_us     h48_us")
var ruler64: [(Double, Double)] = []
for it in [0, 1, 2, 4, 8] {
    let a = run(heads: 64, variant: "V0", iters: it, nbank: 40)
    let b = run(heads: 48, variant: "V0", iters: it, nbank: 40)
    ruler64.append((Double(it), a.usPerCall))
    print(String(format: "%-6d %10.3f %10.3f", it, a.usPerCall, b.usPerCall))
}
let n: Double = Double(ruler64.count)
var mx: Double = 0
var my: Double = 0
for p in ruler64 { mx += p.0; my += p.1 }
mx /= n
my /= n
var sxy: Double = 0
var sxx: Double = 0
for p in ruler64 {
    let dx: Double = p.0 - mx
    sxy += dx * (p.1 - my)
    sxx += dx * dx
}
let slope: Double = sxy / sxx
let fixed: Double = my - slope * mx
print(String(format: "h64 OLS: fixed=%.3f us  per-iter=%.3f us  (8 iters => %.3f us of work)",
             fixed, slope, slope * 8))

print("\n=== B. variant A/B (full 8 iters) ===")
print("var    banks     h64_us     h48_us   h64_step   h48_step")
var ref64: [UInt16] = []
var ref48: [UInt16] = []
for nb in [1024, 40, 1] {
    for v in ["V0", "V1", "V2", "V3", "NOLD"] {
        let a = run(heads: 64, variant: v, iters: 8, nbank: nb)
        let b = run(heads: 48, variant: v, iters: 8, nbank: nb)
        if v == "V0" && nb == 40 { ref64 = a.out; ref48 = b.out }
        var mark = ""
        if nb == 40 && v != "NOLD" {
            mark = (a.out == ref64 && b.out == ref48) ? "  bit-exact" : "  *** DIFFERS ***"
        }
        let row = String(format: "%6d %10.3f %10.3f %10.1f %10.1f",
                         nb, a.usPerCall, b.usPerCall,
                         a.usPerCall * 30.30, b.usPerCall * 10.10)
        print(v.padding(toLength: 6, withPad: " ", startingAt: 0) + row + mark)
    }
}
