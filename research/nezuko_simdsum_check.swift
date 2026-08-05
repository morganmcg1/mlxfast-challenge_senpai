// Research-only (not part of the submission).
//
// Question: is `simd_sum(vec<float,N>)` bit-identical to N independent
// `simd_sum(float)` calls on the same 32 lane values?
//
// Two field solvers assert Metal's SIMD reduction "applies componentwise" and
// shipped a packed reduction at max_abs_diff = 0. The Metal spec does not
// state the association order of `simd_sum` on floats, so the packed form is
// only safe if the vector reduction uses the same tree per component.
//
// The scalar and vector reductions live in separate kernels so the compiler
// cannot CSE one into the other and make the comparison vacuous.
//
// Build/run:
//   swiftc -O research/nezuko_simdsum_check.swift -o /tmp/simdsum_check \
//     -framework Metal -framework Foundation && /tmp/simdsum_check

import Foundation
import Metal

let source = """
#include <metal_stdlib>
using namespace metal;

kernel void scalar4(
    device const float4* input [[buffer(0)]],
    device uint4* out [[buffer(1)]],
    uint tg [[threadgroup_position_in_grid]],
    uint lane [[thread_index_in_simdgroup]])
{
    float4 v = input[tg * 32 + lane];
    float s0 = simd_sum(v.x);
    float s1 = simd_sum(v.y);
    float s2 = simd_sum(v.z);
    float s3 = simd_sum(v.w);
    if (lane == 0) {
        out[tg] = uint4(as_type<uint>(s0), as_type<uint>(s1),
                        as_type<uint>(s2), as_type<uint>(s3));
    }
}

kernel void vector4(
    device const float4* input [[buffer(0)]],
    device uint4* out [[buffer(1)]],
    uint tg [[threadgroup_position_in_grid]],
    uint lane [[thread_index_in_simdgroup]])
{
    float4 v = input[tg * 32 + lane];
    float4 p = simd_sum(v);
    if (lane == 0) {
        out[tg] = as_type<uint4>(p);
    }
}

kernel void vector2(
    device const float4* input [[buffer(0)]],
    device uint4* out [[buffer(1)]],
    uint tg [[threadgroup_position_in_grid]],
    uint lane [[thread_index_in_simdgroup]])
{
    float4 v = input[tg * 32 + lane];
    float2 a = simd_sum(v.xy);
    float2 b = simd_sum(v.zw);
    if (lane == 0) {
        out[tg] = uint4(as_type<uint>(a.x), as_type<uint>(a.y),
                        as_type<uint>(b.x), as_type<uint>(b.y));
    }
}

// Power control: an explicit butterfly with the mask order reversed relative
// to the usual 1,2,4,8,16 tree. A test corpus that cannot distinguish this
// from simd_sum could not detect an association-order change either.
kernel void scalar4_reversed(
    device const float4* input [[buffer(0)]],
    device uint4* out [[buffer(1)]],
    uint tg [[threadgroup_position_in_grid]],
    uint lane [[thread_index_in_simdgroup]])
{
    float4 v = input[tg * 32 + lane];
    for (uint mask = 16; mask >= 1; mask >>= 1) {
        v += simd_shuffle_xor(v, mask);
    }
    if (lane == 0) {
        out[tg] = as_type<uint4>(v);
    }
}

// PR #68 Step 1: the ascending hand-rolled butterfly. This is the exact
// replacement a batched cross-lane reduction would have to use, so its
// bitwise agreement with simd_sum(float) is the gate on the whole
// batched-reduction family.
kernel void scalar4_forward(
    device const float4* input [[buffer(0)]],
    device uint4* out [[buffer(1)]],
    uint tg [[threadgroup_position_in_grid]],
    uint lane [[thread_index_in_simdgroup]])
{
    float4 v = input[tg * 32 + lane];
    for (uint mask = 1; mask <= 16; mask <<= 1) {
        v += simd_shuffle_xor(v, mask);
    }
    if (lane == 0) {
        out[tg] = as_type<uint4>(v);
    }
}

// The same ascending butterfly written as four scalar chains rather than a
// float4, in case the vector form is contracted differently.
kernel void scalar4_forward_scalar(
    device const float4* input [[buffer(0)]],
    device uint4* out [[buffer(1)]],
    uint tg [[threadgroup_position_in_grid]],
    uint lane [[thread_index_in_simdgroup]])
{
    float4 v = input[tg * 32 + lane];
    float a = v.x, b = v.y, c = v.z, d = v.w;
    for (uint mask = 1; mask <= 16; mask <<= 1) {
        a += simd_shuffle_xor(a, mask);
        b += simd_shuffle_xor(b, mask);
        c += simd_shuffle_xor(c, mask);
        d += simd_shuffle_xor(d, mask);
    }
    if (lane == 0) {
        out[tg] = uint4(as_type<uint>(a), as_type<uint>(b),
                        as_type<uint>(c), as_type<uint>(d));
    }
}

// simd_shuffle_down tree: the other common lowering, 16,8,4,2,1.
kernel void scalar4_down(
    device const float4* input [[buffer(0)]],
    device uint4* out [[buffer(1)]],
    uint tg [[threadgroup_position_in_grid]],
    uint lane [[thread_index_in_simdgroup]])
{
    float4 v = input[tg * 32 + lane];
    for (uint d = 16; d >= 1; d >>= 1) {
        v += simd_shuffle_down(v, d);
    }
    if (lane == 0) {
        out[tg] = as_type<uint4>(v);
    }
}

// The actual batched mechanism under evaluation: R=4 independent per-lane
// values reduced through one rotation ladder, so all four results land in
// 5 shuffle rounds of a float4 instead of 4 x 5 scalar rounds.
kernel void batched4_rot(
    device const float4* input [[buffer(0)]],
    device uint4* out [[buffer(1)]],
    uint tg [[threadgroup_position_in_grid]],
    uint lane [[thread_index_in_simdgroup]])
{
    float4 v = input[tg * 32 + lane];
    for (uint mask = 1; mask <= 16; mask <<= 1) {
        float4 o;
        o.x = simd_shuffle_xor(v.x, mask);
        o.y = simd_shuffle_xor(v.y, mask);
        o.z = simd_shuffle_xor(v.z, mask);
        o.w = simd_shuffle_xor(v.w, mask);
        v += o;
    }
    if (lane == 0) {
        out[tg] = as_type<uint4>(v);
    }
}
"""

// 262144 cases x 4 components = 1,048,576 independent 32-lane reductions,
// which is the >= 1e6 corpus PR #68 Step 1 asks for.
let cases = 262_144
let lanesPerCase = 32

func makeInputs() -> ([Float], [String]) {
    var values = [Float](repeating: 0, count: cases * lanesPerCase * 4)
    var labels = [String](repeating: "", count: cases)
    var rng = SystemRandomNumberGenerator()

    func uniform() -> Float { Float.random(in: -1...1, using: &rng) }

    for c in 0..<cases {
        let family = c % 8
        labels[c] = ["uniform", "magnitude-ladder", "cancellation",
                     "mantissa-tie", "denormal-mix", "random-bits",
                     "one-huge", "alternating-exact"][family]
        for lane in 0..<lanesPerCase {
            for comp in 0..<4 {
                let i = (c * lanesPerCase + lane) * 4 + comp
                switch family {
                case 0:
                    values[i] = uniform()
                case 1:
                    // magnitudes spanning 2^20 within one reduction
                    let e = Int(Float(lane) / 32.0 * 20.0) - 10
                    values[i] = uniform() * exp2(Float(e))
                case 2:
                    // catastrophic cancellation: large opposite pairs plus dust
                    values[i] = lane < 2
                        ? (lane == 0 ? 1.0e18 : -1.0e18)
                        : uniform() * exp2(-10)
                case 3:
                    // ties at the last mantissa bit: 1 + k * 2^-24
                    values[i] = lane == 0 ? 1.0 : Float(bitPattern: 0x3380_0000)
                case 4:
                    values[i] = lane % 3 == 0
                        ? Float(bitPattern: UInt32.random(in: 1...0x007F_FFFF, using: &rng))
                        : uniform()
                case 5:
                    var bits = UInt32.random(in: 0...UInt32.max, using: &rng)
                    // keep finite: clamp exponent away from 0xFF
                    if (bits >> 23) & 0xFF == 0xFF { bits &= 0xFF7F_FFFF }
                    values[i] = Float(bitPattern: bits)
                case 6:
                    values[i] = lane == UInt32(comp) % 32 ? 1.0e30 : uniform()
                default:
                    // exact powers of two with alternating sign: any change in
                    // association order changes the intermediate rounding
                    values[i] = (lane % 2 == 0 ? 1 : -1)
                        * exp2(Float(Int(lane) % 24 - 12))
                        * (comp % 2 == 0 ? 1.0 : 3.0)
                }
            }
        }
    }
    return (values, labels)
}

guard let device = MTLCreateSystemDefaultDevice(),
      let queue = device.makeCommandQueue()
else { fatalError("no Metal device") }

let library = try device.makeLibrary(source: source, options: nil)
let (inputs, labels) = makeInputs()

let inputBytes = inputs.count * MemoryLayout<Float>.size
let inputBuffer = device.makeBuffer(bytes: inputs, length: inputBytes,
                                    options: .storageModeShared)!
let outBytes = cases * 4 * MemoryLayout<UInt32>.size

func run(_ name: String) -> [UInt32] {
    let pipeline = try! device.makeComputePipelineState(
        function: library.makeFunction(name: name)!)
    let out = device.makeBuffer(length: outBytes, options: .storageModeShared)!
    memset(out.contents(), 0xCD, outBytes)
    let cb = queue.makeCommandBuffer()!
    let enc = cb.makeComputeCommandEncoder()!
    enc.setComputePipelineState(pipeline)
    enc.setBuffer(inputBuffer, offset: 0, index: 0)
    enc.setBuffer(out, offset: 0, index: 1)
    enc.dispatchThreadgroups(MTLSize(width: cases, height: 1, depth: 1),
                             threadsPerThreadgroup: MTLSize(width: 32, height: 1, depth: 1))
    enc.endEncoding()
    cb.commit()
    cb.waitUntilCompleted()
    print("\(name): maxTotalThreadsPerThreadgroup=\(pipeline.maxTotalThreadsPerThreadgroup)"
          + " threadExecutionWidth=\(pipeline.threadExecutionWidth)")
    let p = out.contents().bindMemory(to: UInt32.self, capacity: cases * 4)
    return Array(UnsafeBufferPointer(start: p, count: cases * 4))
}

let scalarBits = run("scalar4")
let vector4Bits = run("vector4")
let vector2Bits = run("vector2")

func compare(_ label: String, _ candidate: [UInt32]) {
    var mismatches = 0
    var byFamily: [String: Int] = [:]
    var firstReport = ""
    for c in 0..<cases {
        for comp in 0..<4 {
            let i = c * 4 + comp
            if scalarBits[i] != candidate[i] {
                mismatches += 1
                byFamily[labels[c], default: 0] += 1
                if firstReport.isEmpty {
                    let a = Float(bitPattern: scalarBits[i])
                    let b = Float(bitPattern: candidate[i])
                    firstReport = "case \(c) family=\(labels[c]) comp=\(comp) "
                        + "scalar=\(a) (0x\(String(scalarBits[i], radix: 16))) "
                        + "packed=\(b) (0x\(String(candidate[i], radix: 16)))"
                }
            }
        }
    }
    print("\n\(label): \(mismatches) bit-pattern mismatches out of \(cases * 4) reductions")
    if mismatches > 0 {
        print("  first: \(firstReport)")
        for (family, count) in byFamily.sorted(by: { $0.value > $1.value }) {
            print("  \(family): \(count)")
        }
    }
}

let reversedBits = run("scalar4_reversed")
let forwardBits = run("scalar4_forward")
let forwardScalarBits = run("scalar4_forward_scalar")
let downBits = run("scalar4_down")
let batchedBits = run("batched4_rot")

compare("simd_sum(float4) vs 4x simd_sum(float)", vector4Bits)
compare("2x simd_sum(float2) vs 4x simd_sum(float)", vector2Bits)
compare("POWER CONTROL: reversed butterfly vs 4x simd_sum(float)", reversedBits)
compare("STEP 1: ascending xor butterfly (float4) vs 4x simd_sum(float)", forwardBits)
compare("STEP 1: ascending xor butterfly (scalar) vs 4x simd_sum(float)", forwardScalarBits)
compare("STEP 1: shuffle_down tree vs 4x simd_sum(float)", downBits)
compare("STEP 1: batched R=4 rotation ladder vs 4x simd_sum(float)", batchedBits)
