// Execution-equivalence check for the `_nax` expert gather-QMM kernel.
//
// Selection is not capability: MLX's dispatch heuristics never *select* the
// `_nax` kernels on Apple GPU generation 16 (M4 family), but the kernels
// compile and instantiate there, so this host can still RUN them. That turns
// "bit-exact by construction" from an argument into a measurement.
//
// The tool loads two offline metallibs built by
// `research/nax_msl_compile_check.sh EMIT_LIB=1` (a base one and a candidate
// one), dispatches the matching kernel from each over the SAME deterministic
// input buffers, and compares the two output buffers byte for byte.
//
// Usage:
//   swift research/tanjiro_nax_exec_equiv.swift BASE.metallib CAND.metallib
//
// Env:
//   SHAPES=2048x1024,512x2048   which ranked shapes to exercise
//   ROWS=256                    M (sorted routed rows) fed to the kernel
//   EGROUPS=4                   grid.y, i.e. how many experts to materialize.
//                               The shipped dispatch uses 256; each
//                               threadgroup owns exactly one expert, so a
//                               reduced grid.y runs the identical per-expert
//                               code over a smaller weight slab.
//   SEED=12345                  PRNG seed
//   TRIALS=3                    independent input draws per shape

import Foundation
import Metal

// ---------------------------------------------------------------- rng ------

struct Xoshiro {
    var s: UInt64
    init(_ seed: UInt64) { s = seed &* 0x9E3779B97F4A7C15 &+ 0x1234567 }
    mutating func next() -> UInt64 {
        s ^= s << 13
        s ^= s >> 7
        s ^= s << 17
        return s
    }
    mutating func byte() -> UInt8 { UInt8(truncatingIfNeeded: next() >> 24) }
}

/// bfloat16 bit pattern with a bounded exponent, so the MMA chain sees
/// ordinary finite magnitudes (~2^-4 .. 2^4) instead of denormals or NaN.
func randomBF16(_ r: inout Xoshiro) -> UInt16 {
    let v = r.next()
    let sign = UInt16((v >> 40) & 1)
    let exp = UInt16(123 + (v >> 32) % 9)   // 123..131 -> 2^-4 .. 2^4
    let mant = UInt16((v >> 8) & 0x7F)
    return (sign << 15) | (exp << 7) | mant
}

/// NVFP4 group scale is OCP e4m3. 0x7F/0xFF are NaN, so clamp the exponent
/// nibble away from all-ones and keep the scale magnitude moderate.
func randomE4M3(_ r: inout Xoshiro) -> UInt8 {
    let v = r.next()
    let sign = UInt8((v >> 40) & 1)
    let exp = UInt8(5 + (v >> 32) % 7)      // 5..11, never 15 (NaN)
    let mant = UInt8((v >> 8) & 0x7)
    return (sign << 7) | (exp << 3) | mant
}

// ------------------------------------------------------------- device ------

guard let device = MTLCreateSystemDefaultDevice(),
      let queue = device.makeCommandQueue() else {
    FileHandle.standardError.write(Data("no Metal device\n".utf8))
    exit(1)
}

let args = Array(CommandLine.arguments.dropFirst())
guard args.count == 2 else {
    print("usage: swift research/tanjiro_nax_exec_equiv.swift BASE.metallib CAND.metallib")
    exit(2)
}

let env = ProcessInfo.processInfo.environment
let shapes = (env["SHAPES"] ?? "2048x1024,512x2048").split(separator: ",").map(String.init)
let rows = Int(env["ROWS"] ?? "256")!
let egroups = Int(env["EGROUPS"] ?? "4")!
let seed0 = UInt64(env["SEED"] ?? "12345")!
let trials = Int(env["TRIALS"] ?? "3")!

func loadLib(_ path: String) -> MTLLibrary {
    do {
        return try device.makeLibrary(URL: URL(fileURLWithPath: path))
    } catch {
        FileHandle.standardError.write(Data("cannot load \(path): \(error)\n".utf8))
        exit(1)
    }
}

let libs = [loadLib(args[0]), loadLib(args[1])]
let labels = [
    URL(fileURLWithPath: args[0]).deletingLastPathComponent().lastPathComponent,
    URL(fileURLWithPath: args[1]).deletingLastPathComponent().lastPathComponent,
]

print("device: \(device.name)")
print("A = \(args[0])")
print("B = \(args[1])")
print("rows(M) = \(rows)  grid.y(experts) = \(egroups)  trials = \(trials)")
print("")

/// The offline check metallibs name their kernels
/// `fp_gather_qmm_rhs_expert_nax_check_<K>x<N>_bk<BK>[_sl1]`. Take whichever
/// of the two spellings this library actually exports so the same tool works
/// on a base library (no `_sl1`) and a candidate one.
func findFunction(_ lib: MTLLibrary, shape: String, bk: Int) -> (String, MTLFunction)? {
    let stem = "fp_gather_qmm_rhs_expert_nax_check_\(shape)_bk\(bk)"
    for name in [stem, stem + "_sl1"] where lib.functionNames.contains(name) {
        if let f = lib.makeFunction(name: name) { return (name, f) }
    }
    return nil
}

var failures = 0
var comparisons = 0

for shape in shapes {
    let parts = shape.split(separator: "x").map { Int($0)! }
    let K = parts[0], N = parts[1]

    let bk = 64
    var pipes: [(String, MTLComputePipelineState)] = []
    var missing = false
    for lib in libs {
        guard let (name, fn) = findFunction(lib, shape: shape, bk: bk) else {
            missing = true
            break
        }
        guard let pso = try? device.makeComputePipelineState(function: fn) else {
            FileHandle.standardError.write(Data("cannot build PSO for \(name)\n".utf8))
            exit(1)
        }
        pipes.append((name, pso))
    }
    if missing || pipes.count != 2 {
        print("shape \(shape): kernel absent from one library -- skipped")
        continue
    }

    // Layout constants mirrored from fp_gather_qmm_rhs_expert_nax.
    let groupSize = 16
    let K_w = K / 2                 // bytes_per_pack=1, pack_factor=2
    let K_g = K / groupSize
    let strideW = N * K_w
    let strideS = N * K_g
    let yCols = (N == 1024 && K == 2048) ? N / 2 : N   // fused swiglu halves N

    print("shape \(shape) K=\(K) N=\(N)  w=\(strideW * egroups) B  scales=\(strideS * egroups) B")
    print("  A kernel: \(pipes[0].0)   tgMem=\(pipes[0].1.staticThreadgroupMemoryLength)")
    print("  B kernel: \(pipes[1].0)   tgMem=\(pipes[1].1.staticThreadgroupMemoryLength)")

    // Uneven routed runs so both the full-tile (sgp_sm == SM) and the
    // partial-row (store_slice) arms execute.
    var counts: [Int] = []
    var left = rows
    for e in 0..<egroups {
        let c = (e == egroups - 1) ? left : max(0, min(left, 70 - 12 * e))
        counts.append(c)
        left -= c
    }
    var indices = [UInt32]()
    for (e, c) in counts.enumerated() { indices.append(contentsOf: repeatElement(UInt32(e), count: c)) }
    precondition(indices.count == rows, "index run lengths must sum to M")

    for trial in 0..<trials {
        var r = Xoshiro(seed0 &+ UInt64(trial) &* 7919 &+ UInt64(K))

        var x = [UInt16](repeating: 0, count: rows * K)
        for i in 0..<x.count { x[i] = randomBF16(&r) }
        var w = [UInt8](repeating: 0, count: strideW * egroups)
        for i in 0..<w.count { w[i] = r.byte() }        // every nibble is a valid e2m1 code
        var scales = [UInt8](repeating: 0, count: strideS * egroups)
        for i in 0..<scales.count { scales[i] = randomE4M3(&r) }

        let opt: MTLResourceOptions = .storageModeShared
        let bx = device.makeBuffer(bytes: &x, length: x.count * 2, options: opt)!
        let bw = device.makeBuffer(bytes: &w, length: w.count, options: opt)!
        let bs = device.makeBuffer(bytes: &scales, length: scales.count, options: opt)!
        let bi = device.makeBuffer(bytes: &indices, length: indices.count * 4, options: opt)!
        precondition(bs.contents() == bs.contents(), "")

        let yBytes = rows * yCols * 2
        var outs: [[UInt8]] = []
        for (_, pso) in pipes {
            let by = device.makeBuffer(length: yBytes, options: opt)!
            memset(by.contents(), 0xA5, yBytes)         // sentinel: untouched rows must match too
            let cb = queue.makeCommandBuffer()!
            let enc = cb.makeComputeCommandEncoder()!
            enc.setComputePipelineState(pso)
            enc.setBuffer(bx, offset: 0, index: 0)
            enc.setBuffer(bw, offset: 0, index: 1)
            enc.setBuffer(bs, offset: 0, index: 2)
            enc.setBuffer(bi, offset: 0, index: 3)
            enc.setBuffer(by, offset: 0, index: 4)
            var M32 = Int32(rows), N32 = Int32(N), K32 = Int32(K), skip = Int32(100)
            enc.setBytes(&M32, length: 4, index: 5)
            enc.setBytes(&N32, length: 4, index: 6)
            enc.setBytes(&K32, length: 4, index: 7)
            enc.setBytes(&skip, length: 4, index: 8)
            enc.dispatchThreadgroups(
                MTLSize(width: (N + 63) / 64, height: egroups, depth: 1),
                threadsPerThreadgroup: MTLSize(width: 32, height: 1, depth: 4))
            enc.endEncoding()
            cb.commit()
            cb.waitUntilCompleted()
            if let e = cb.error {
                FileHandle.standardError.write(Data("dispatch failed: \(e)\n".utf8))
                exit(1)
            }
            outs.append([UInt8](UnsafeBufferPointer(
                start: by.contents().assumingMemoryBound(to: UInt8.self), count: yBytes)))
        }

        comparisons += 1
        let touched = outs[0].withUnsafeBufferPointer { p -> Int in
            var n = 0
            var i = 0
            while i + 1 < p.count {
                if !(p[i] == 0xA5 && p[i + 1] == 0xA5) { n += 1 }
                i += 2
            }
            return n
        }
        if outs[0] == outs[1] {
            print("  trial \(trial): IDENTICAL  (\(yBytes) B, \(touched)/\(rows * yCols) elems written)")
        } else {
            failures += 1
            var first = -1
            var diff = 0
            for i in 0..<yBytes where outs[0][i] != outs[1][i] {
                if first < 0 { first = i }
                diff += 1
            }
            print("  trial \(trial): MISMATCH  \(diff)/\(yBytes) bytes differ, first at \(first)")
        }
    }
    print("")
}

print("comparisons=\(comparisons) failures=\(failures)")
if comparisons == 0 {
    print("EXEC-EQUIV: NO COMPARISON RAN")
    exit(1)
}
print(failures == 0 ? "EXEC-EQUIV: PASS" : "EXEC-EQUIV: FAIL")
exit(failures == 0 ? 0 : 1)
