// Research-only host probe (not part of the submission surface).
//
// R107-G stage 0 calibration: measure this host's *actual* sustained fp32 fma
// issue ceiling, instead of quoting a spec-sheet product.
//
// The R107-G charge quotes 2560 lanes x 1.578 GHz = 4.04e12 fma/s as the
// theoretical peak issue rate and asks for it to be re-derived.  The dose
// ladders in this round produce marginal fma rates *above* that number, which
// means either the doses are not being issued (ruled out: the AIR still carries
// 8 `air.fma.f32` calls in a rolled loop) or the quoted ceiling is wrong.  This
// probe settles it with a kernel that is pure ALU: no device loads inside the
// timed loop, 8 independent accumulators for ILP, and a trip count large enough
// that launch overhead is < 1 %.
//
// Build and run:
//   xcrun swiftc -O research/maple-tanjiro-r107g-alu-ceiling.swift -o /tmp/aluceil
//   /tmp/aluceil
//
// Env: TANJIRO_TGS (threadgroups, default 2048), TANJIRO_TPT (threads/TG,
// default 64 -- the shipped decode-QMV geometry), TANJIRO_ROUNDS, TANJIRO_REPS.

import Foundation
import Metal

let device = MTLCreateSystemDefaultDevice()!
let queue = device.makeCommandQueue()!

func intVal(_ n: String, _ d: Int) -> Int { Int(ProcessInfo.processInfo.environment[n] ?? "") ?? d }
let tgs = intVal("TANJIRO_TGS", 2048)
let tpt = intVal("TANJIRO_TPT", 64)
let rounds = intVal("TANJIRO_ROUNDS", 15)
let reps = intVal("TANJIRO_REPS", 50)

// Trip counts on the same rolled-loop shape the dose harness injects: 8
// independent `fma` per trip, seeded from a value the compiler cannot fold.
let trips = [256, 512, 1024, 2048]

let source = """
#include <metal_stdlib>
using namespace metal;

[[kernel]] void alu_ceiling(
    const device float* seed [[buffer(0)]],
    device float* out [[buffer(1)]],
    constant uint& trips [[buffer(2)]],
    uint gid [[thread_position_in_grid]]) {
  float s = seed[gid & 63];
  float a0 = s, a1 = s + 1.0f, a2 = s + 2.0f, a3 = s + 3.0f;
  float a4 = s + 4.0f, a5 = s + 5.0f, a6 = s + 6.0f, a7 = s + 7.0f;
  for (uint t = 0; t < trips; ++t) {
    a0 = metal::fma(a0, 1.0000001f, 1e-6f);
    a1 = metal::fma(a1, 1.0000001f, 1e-6f);
    a2 = metal::fma(a2, 1.0000001f, 1e-6f);
    a3 = metal::fma(a3, 1.0000001f, 1e-6f);
    a4 = metal::fma(a4, 1.0000001f, 1e-6f);
    a5 = metal::fma(a5, 1.0000001f, 1e-6f);
    a6 = metal::fma(a6, 1.0000001f, 1e-6f);
    a7 = metal::fma(a7, 1.0000001f, 1e-6f);
  }
  float r = ((a0 + a1) + (a2 + a3)) + ((a4 + a5) + (a6 + a7));
  if (r == 1e37f) { out[gid] = r; }
}
"""

let lib = try! device.makeLibrary(source: source, options: nil)
let pipe = try! device.makeComputePipelineState(function: lib.makeFunction(name: "alu_ceiling")!)

let seed = device.makeBuffer(length: 64 * 4, options: .storageModeShared)!
do {
    let p = seed.contents().bindMemory(to: Float.self, capacity: 64)
    for i in 0..<64 { p[i] = Float(i) * 0.125 + 1.0 }
}
let out = device.makeBuffer(length: tgs * tpt * 4, options: .storageModeShared)!

print("=== device ===")
print("name                  \(device.name)")
print("architecture          \(device.architecture.name)")
print("threadgroups           \(tgs)")
print("threads/threadgroup    \(tpt)")
print("threads total          \(tgs * tpt)")
print("maxTotalThreadsPerTG   \(pipe.maxTotalThreadsPerThreadgroup)")
print("threadExecutionWidth   \(pipe.threadExecutionWidth)")
print("staticTGMemory         \(pipe.staticThreadgroupMemoryLength)")

func timeTrips(_ t: Int) -> Double {
    var tv = UInt32(t)
    let tb = device.makeBuffer(bytes: &tv, length: 4, options: .storageModeShared)!
    var best = Double.greatestFiniteMagnitude
    for _ in 0..<rounds {
        let cb = queue.makeCommandBuffer()!
        let enc = cb.makeComputeCommandEncoder()!
        enc.setComputePipelineState(pipe)
        enc.setBuffer(seed, offset: 0, index: 0)
        enc.setBuffer(out, offset: 0, index: 1)
        enc.setBuffer(tb, offset: 0, index: 2)
        for _ in 0..<reps {
            enc.dispatchThreadgroups(
                MTLSize(width: tgs, height: 1, depth: 1),
                threadsPerThreadgroup: MTLSize(width: tpt, height: 1, depth: 1))
        }
        enc.endEncoding()
        let t0 = DispatchTime.now().uptimeNanoseconds
        cb.commit()
        cb.waitUntilCompleted()
        let t1 = DispatchTime.now().uptimeNanoseconds
        best = min(best, Double(t1 - t0) / 1e3 / Double(reps))
    }
    return best
}

// Warm up so the first ladder point is not paying pipeline creation.
_ = timeTrips(trips[0])

print("\n=== sustained fp32 fma issue ceiling (best-of-\(rounds) rounds x \(reps) dispatches) ===")
print("  trips   fma/thread        us      fma_per_dispatch        fma_per_s   fma/thread/us")
var rows: [(Int, Double)] = []
for t in trips {
    let us = timeTrips(t)
    let fmaPerThread = t * 8
    let total = Double(fmaPerThread) * Double(tgs * tpt)
    rows.append((fmaPerThread, us))
    print(
        String(
            format: "  %5d   %10d   %7.3f   %18.0f   %12.4e   %13.5f",
            t, fmaPerThread, us, total, total / (us * 1e-6), Double(fmaPerThread) / us))
}

// Marginal rate from the top two ladder points: cancels the launch/epilogue
// intercept exactly, so it is the number to quote as the ceiling.
let (f1, u1) = rows[rows.count - 2]
let (f2, u2) = rows[rows.count - 1]
let marginalPerThreadUs = (u2 - u1) / Double(f2 - f1)
let marginalRate = Double(tgs * tpt) / (marginalPerThreadUs * 1e-6)
print("")
print(String(format: "marginal us per fma-per-thread   %.9f", marginalPerThreadUs))
print(String(format: "==> MEASURED fma issue ceiling   %.4e fma/s   (%.3f TFLOP/s fp32)",
             marginalRate, marginalRate * 2 / 1e12))
print(String(format: "advisor quoted ceiling           4.0400e+12 fma/s  -> measured/quoted = %.3f",
             marginalRate / 4.04e12))
let lanes = 20.0 * 128.0
print(String(format: "implied clock at 20x128 lanes    %.3f GHz", marginalRate / lanes / 1e9))
