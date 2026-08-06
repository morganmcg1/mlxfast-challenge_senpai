// Research-only (not part of the submission).
//
// PR #72 Step 2 §0.9.21 certificate: does the group-32 scale-plane halving
// reproduce the shipped NVFP4 routed decode outputs BIT-EXACTLY?
//
// The two kernel texts (shipped baseline and halved candidate) are compiled in
// ONE process from `makeLibrary`, run on the same real expert weights, and the
// two output buffers are compared with `memcmp`. `--local-submit` is not an
// admissible certificate for this claim: it neither isolates the kernel nor
// proves the comparison had power to fail.
//
// Power controls: deliberately-incoherent candidate variants MUST each produce
// a non-zero diff. If any control agrees with the baseline, the harness reports
// FAIL because the comparison could not have detected the fault it claims to
// rule out.
//
// Inputs are produced by the two companion tools (run these first):
//   python3 research/nezuko_g32_extract.py --preamble
//   python3 research/nezuko_g32_extract.py --tag baseline  --rev HEAD
//   python3 research/nezuko_g32_extract.py --tag candidate --worktree
//   python3 research/nezuko_g32_dump.py
//
// Build/run:
//   swiftc -O research/nezuko_group32_halving_check.swift \
//     -o /tmp/nezuko_g32/halving_check -framework Metal -framework Foundation \
//     && /tmp/nezuko_g32/halving_check

import Foundation
import Metal

let dir = "/tmp/nezuko_g32"

// MARK: - MLX metal_kernel signature synthesis
//
// Port of `mlx/backend/common/metal_kernel.cpp:write_signature`. MLXFast's
// `metalKernel(name:inputNames:outputNames:source:)` does not hand the runtime
// a whole Metal function; it hands it a header + body and synthesises the
// `[[kernel]]` signature. To compile the exact shipped text here we must
// synthesise the identical signature.

struct Binding {
    let name: String
    let dtype: String
}

// Emitted in this fixed order, each only when the body mentions it.
let attributeTable: [(String, String)] = [
    ("dispatch_quadgroups_per_threadgroup", "uint"),
    ("dispatch_simdgroups_per_threadgroup", "uint"),
    ("dispatch_threads_per_threadgroup", "uint3"),
    ("grid_origin", "uint3"),
    ("grid_size", "uint3"),
    ("quadgroup_index_in_threadgroup", "uint"),
    ("quadgroups_per_threadgroup", "uint"),
    ("simdgroup_index_in_threadgroup", "uint"),
    ("simdgroups_per_threadgroup", "uint"),
    ("thread_execution_width", "uint"),
    ("thread_index_in_quadgroup", "uint"),
    ("thread_index_in_simdgroup", "uint"),
    ("thread_index_in_threadgroup", "uint"),
    ("thread_position_in_grid", "uint3"),
    ("thread_position_in_threadgroup", "uint3"),
    ("threadgroup_position_in_grid", "uint3"),
    ("threadgroups_per_grid", "uint3"),
    ("threads_per_grid", "uint3"),
    ("threads_per_simdgroup", "uint"),
    ("threads_per_threadgroup", "uint3"),
]

func writeSignature(
    name: String, header: String, body: String,
    inputs: [Binding], outputs: [Binding]
) -> String {
    var out = header + "\n[[kernel]] void " + name + "(\n"
    var slot = 0
    for b in inputs {
        // `max_constant_array_size = 8`; every binding here is far larger, so
        // MLX picks the `device` address space for all of them.
        out += "  const device \(b.dtype)* \(b.name) [[buffer(\(slot))]],\n"
        slot += 1
    }
    let attrs = attributeTable.filter { body.contains($0.0) }
    for (i, b) in outputs.enumerated() {
        let last = (i == outputs.count - 1) && attrs.isEmpty
        out += "  device \(b.dtype)* \(b.name) [[buffer(\(slot))]]"
        out += last ? ") {\n" : ",\n"
        slot += 1
    }
    for (i, a) in attrs.enumerated() {
        out += "  \(a.1) \(a.0) [[\(a.0)]]"
        out += (i == attrs.count - 1) ? ") {\n" : ",\n"
    }
    return out + body + "\n}\n"
}

// MARK: - I/O helpers

func readFile(_ path: String) -> [UInt8] {
    guard let d = FileManager.default.contents(atPath: path) else {
        FileHandle.standardError.write("missing input: \(path)\n".data(using: .utf8)!)
        exit(2)
    }
    return [UInt8](d)
}

func readText(_ path: String) -> String {
    guard let s = try? String(contentsOfFile: path, encoding: .utf8) else {
        FileHandle.standardError.write("missing input: \(path)\n".data(using: .utf8)!)
        exit(2)
    }
    return s
}

/// Splits a rendered `<header>\n// @@SOURCE@@\n<body>` artifact.
func splitRendered(_ path: String) -> (header: String, body: String) {
    let text = readText(path)
    let marker = "\n// @@SOURCE@@\n"
    guard let r = text.range(of: marker) else {
        FileHandle.standardError.write("no @@SOURCE@@ marker in \(path)\n".data(using: .utf8)!)
        exit(2)
    }
    return (String(text[text.startIndex..<r.lowerBound]),
            String(text[r.upperBound...]))
}

// MARK: - The transformation under test
//
// Mirrors `lagunaHalvedGroup32ScalePlane` in Sources/MLXFastModel/
// LagunaRuntimeModel.swift. Output layout is
//   [128-byte patch header] ++ [even byte of every group-32 pair]
// and `header[slot]` carries the odd byte of `allowedFlatPairs[slot]`, the only
// pairs the census found to be unequal.

let patchHeaderBytes = 128

func halve(_ plane: [UInt8], allowedFlatPairs: [Int]) -> (plane: [UInt8], violations: [Int]) {
    let pairs = plane.count / 2
    var out = [UInt8](repeating: 0, count: patchHeaderBytes + pairs)
    var violations: [Int] = []
    let allowed = Set(allowedFlatPairs)
    for p in 0..<pairs {
        let even = plane[2 * p]
        let odd = plane[2 * p + 1]
        out[patchHeaderBytes + p] = even
        if even != odd && !allowed.contains(p) { violations.append(p) }
    }
    for (slot, p) in allowedFlatPairs.enumerated() {
        out[slot] = plane[2 * p + 1]
    }
    return (out, violations)
}

// MARK: - Metal plumbing

guard let device = MTLCreateSystemDefaultDevice(),
      let queue = device.makeCommandQueue() else {
    print("no Metal device"); exit(2)
}

let compileOptions: MTLCompileOptions = {
    let o = MTLCompileOptions()
    // MLX compiles kernels with fast math OFF (device.cpp:630). Leaving it on
    // would let the compiler re-associate the qdot accumulation and make a
    // bit-exactness claim meaningless.
    if #available(macOS 15.0, *) { o.mathMode = .safe } else { o.fastMathEnabled = false }
    return o
}()

let preamble = readText("\(dir)/preamble.metal")

func makePipeline(_ text: String, name: String, label: String) -> MTLComputePipelineState {
    do {
        let lib = try device.makeLibrary(source: preamble + "\n" + text, options: compileOptions)
        guard let fn = lib.makeFunction(name: name) else {
            print("\(label): no function \(name)"); exit(2)
        }
        return try device.makeComputePipelineState(function: fn)
    } catch {
        let dump = "\(dir)/failed_\(label).metal"
        try? (preamble + "\n" + text).write(toFile: dump, atomically: true, encoding: .utf8)
        print("\(label): compile failed -> \(dump)\n\(error)")
        exit(2)
    }
}

func buffer(_ bytes: [UInt8]) -> MTLBuffer {
    bytes.withUnsafeBytes {
        device.makeBuffer(bytes: $0.baseAddress!, length: bytes.count,
                          options: .storageModeShared)!
    }
}

func run(
    _ pipeline: MTLComputePipelineState,
    inputs: [MTLBuffer], outputBytes: Int,
    threads: Int, threadgroup: Int
) -> [UInt8] {
    let out = device.makeBuffer(length: outputBytes, options: .storageModeShared)!
    memset(out.contents(), 0, outputBytes)
    let cb = queue.makeCommandBuffer()!
    let enc = cb.makeComputeCommandEncoder()!
    enc.setComputePipelineState(pipeline)
    for (i, b) in inputs.enumerated() { enc.setBuffer(b, offset: 0, index: i) }
    enc.setBuffer(out, offset: 0, index: inputs.count)
    enc.dispatchThreads(MTLSize(width: threads, height: 1, depth: 1),
                        threadsPerThreadgroup: MTLSize(width: threadgroup, height: 1, depth: 1))
    enc.endEncoding()
    cb.commit()
    cb.waitUntilCompleted()
    if let e = cb.error { print("dispatch failed: \(e)"); exit(2) }
    return [UInt8](UnsafeBufferPointer(
        start: out.contents().assumingMemoryBound(to: UInt8.self), count: outputBytes))
}

// MARK: - Fixture

let input = readFile("\(dir)/input.bin")                  // bf16 [2048]
let fusedWeight = readFile("\(dir)/fused_weight.bin")     // u32  [8,1024,256]
let packedScales = readFile("\(dir)/packed_scales.bin")   // u8   [8,4096,32]
let routerKeys = readFile("\(dir)/router_keys.bin")       // u32  [256]
let downWeight = readFile("\(dir)/down_weight.bin")       // u32  [8,2048,64]
let downScales = readFile("\(dir)/down_scales.bin")       // u8   [8,2048,32]
let indices = readFile("\(dir)/indices.bin")              // u32  [8]
let routerWeights = readFile("\(dir)/router_weights.bin") // f32  [8]
let sharedActivated = readFile("\(dir)/shared_activated.bin")     // bf16 [512]
let sharedDownWeight = readFile("\(dir)/shared_down_weight.bin")  // u32  [2048,64]
let sharedDownScales = readFile("\(dir)/shared_down_scales.bin")  // u8   [2048,32]
let residual = readFile("\(dir)/residual.bin")                    // bf16 [2048]

let r1OutBytes = 4096 * 2   // bf16 [1,1,8,1,512]
let downOutBytes = 2048 * 2 // bf16 [1,1,2048]

let r1Name = "laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2"
let downName = "laguna_routed_nvfp4_down_reduce_bf16_v2"
let sdrName = "laguna_routed_shared_nvfp4_down_residual_bf16_r1_v5"

let r1Inputs = [
    Binding(name: "input", dtype: "bfloat16_t"),
    Binding(name: "fused_weight", dtype: "uint32_t"),
    Binding(name: "packed_scales", dtype: "uint8_t"),
    Binding(name: "router_keys", dtype: "uint32_t"),
]
let r1Outputs = [Binding(name: "activated", dtype: "bfloat16_t")]

let downInputs = [
    Binding(name: "activated", dtype: "bfloat16_t"),
    Binding(name: "down_weight", dtype: "uint32_t"),
    Binding(name: "down_scales", dtype: "uint8_t"),
    Binding(name: "indices", dtype: "uint32_t"),
    Binding(name: "router_weights", dtype: "float"),
]
let downOutputs = [Binding(name: "routed", dtype: "bfloat16_t")]

// Input order matches the shipped (routed-first) arm; `DARKBLOOM_SHARED_FIRST_DOWN`
// is off by default and only permutes these bindings.
let sdrInputs = [
    Binding(name: "routed_activated", dtype: "bfloat16_t"),
    Binding(name: "routed_down_weight", dtype: "uint32_t"),
    Binding(name: "routed_down_scales", dtype: "uint8_t"),
    Binding(name: "indices", dtype: "uint32_t"),
    Binding(name: "router_weights", dtype: "float"),
    Binding(name: "shared_activated", dtype: "bfloat16_t"),
    Binding(name: "shared_down_weight", dtype: "uint32_t"),
    Binding(name: "shared_down_scales", dtype: "uint8_t"),
    Binding(name: "residual", dtype: "bfloat16_t"),
]
let sdrOutputs = [Binding(name: "output", dtype: "bfloat16_t")]

// The 8-expert layer-1 slice reproduces the full-checkpoint census: the only
// unequal group-32 pairs are packed pairs 0 and 16, and down pair 0.
let packedAllowed = [0, 16]
let downAllowed = [0]

let (halvedPacked, packedViolations) = halve(packedScales, allowedFlatPairs: packedAllowed)
let (halvedDown, downViolations) = halve(downScales, allowedFlatPairs: downAllowed)

// MARK: - Pipelines

let baseR1 = splitRendered("\(dir)/baseline_r1.metaltext")
let candR1 = splitRendered("\(dir)/candidate_r1.metaltext")
let baseDown = splitRendered("\(dir)/baseline_down.metaltext")
let candDown = splitRendered("\(dir)/candidate_down.metaltext")

let pBaseR1 = makePipeline(
    writeSignature(name: r1Name, header: baseR1.header, body: baseR1.body,
                   inputs: r1Inputs, outputs: r1Outputs),
    name: r1Name, label: "baseline_r1")
let pCandR1 = makePipeline(
    writeSignature(name: r1Name, header: candR1.header, body: candR1.body,
                   inputs: r1Inputs, outputs: r1Outputs),
    name: r1Name, label: "candidate_r1")
let pBaseDown = makePipeline(
    writeSignature(name: downName, header: baseDown.header, body: baseDown.body,
                   inputs: downInputs, outputs: downOutputs),
    name: downName, label: "baseline_down")
let pCandDown = makePipeline(
    writeSignature(name: downName, header: candDown.header, body: candDown.body,
                   inputs: downInputs, outputs: downOutputs),
    name: downName, label: "candidate_down")

let baseSdr = splitRendered("\(dir)/baseline_sdr.metaltext")
let candSdr = splitRendered("\(dir)/candidate_sdr.metaltext")
let pBaseSdr = makePipeline(
    writeSignature(name: sdrName, header: baseSdr.header, body: baseSdr.body,
                   inputs: sdrInputs, outputs: sdrOutputs),
    name: sdrName, label: "baseline_sdr")
let pCandSdr = makePipeline(
    writeSignature(name: sdrName, header: candSdr.header, body: candSdr.body,
                   inputs: sdrInputs, outputs: sdrOutputs),
    name: sdrName, label: "candidate_sdr")

// MARK: - Arms

let bInput = buffer(input)
let bFused = buffer(fusedWeight)
let bRouterKeys = buffer(routerKeys)
let bIndices = buffer(indices)
let bRouterWeights = buffer(routerWeights)
let bSharedActivated = buffer(sharedActivated)
let bSharedDownWeight = buffer(sharedDownWeight)
let bSharedDownScales = buffer(sharedDownScales)
let bResidual = buffer(residual)

func runR1(_ p: MTLComputePipelineState, scales: [UInt8]) -> [UInt8] {
    run(p, inputs: [bInput, bFused, buffer(scales), bRouterKeys],
        outputBytes: r1OutBytes, threads: 8 * 256 * 64, threadgroup: 64)
}

func runDown(
    _ p: MTLComputePipelineState, activated: [UInt8], weight: [UInt8], scales: [UInt8]
) -> [UInt8] {
    run(p, inputs: [buffer(activated), buffer(weight), buffer(scales), bIndices, bRouterWeights],
        outputBytes: downOutBytes, threads: (2048 / 4) * 256, threadgroup: 256)
}

func runSdr(
    _ p: MTLComputePipelineState, activated: [UInt8], weight: [UInt8], scales: [UInt8]
) -> [UInt8] {
    run(p,
        inputs: [buffer(activated), buffer(weight), buffer(scales), bIndices, bRouterWeights,
                 bSharedActivated, bSharedDownWeight, bSharedDownScales, bResidual],
        outputBytes: downOutBytes, threads: (2048 / 4) * 288, threadgroup: 288)
}

func diffCount(_ a: [UInt8], _ b: [UInt8]) -> Int {
    zip(a, b).reduce(0) { $0 + ($1.0 == $1.1 ? 0 : 1) }
}

var failures: [String] = []

print("=== fixture ===")
print("packed_scales    \(packedScales.count) B -> halved \(halvedPacked.count) B "
      + "(allowed pairs \(packedAllowed), violations \(packedViolations.count))")
print("down_scales      \(downScales.count) B -> halved \(halvedDown.count) B "
      + "(allowed pairs \(downAllowed), violations \(downViolations.count))")
if !packedViolations.isEmpty || !downViolations.isEmpty {
    failures.append("halving found unequal pairs outside the allowed set: "
                    + "packed \(packedViolations.prefix(8)) down \(downViolations.prefix(8))")
}

print("\n=== equivalence ===")
let baseActivated = runR1(pBaseR1, scales: packedScales)
let candActivated = runR1(pCandR1, scales: halvedPacked)
let r1Diff = diffCount(baseActivated, candActivated)
print("r1 activated      \(r1OutBytes) B, differing bytes = \(r1Diff)")
if r1Diff != 0 { failures.append("r1 activated differs in \(r1Diff) bytes") }

let baseRouted = runDown(pBaseDown, activated: baseActivated,
                         weight: downWeight, scales: downScales)
let candRouted = runDown(pCandDown, activated: candActivated,
                         weight: downWeight, scales: halvedDown)
let downDiff = diffCount(baseRouted, candRouted)
print("down routed       \(downOutBytes) B, differing bytes = \(downDiff)")
if downDiff != 0 { failures.append("down routed differs in \(downDiff) bytes") }

// The fused routed+shared down/residual kernel is the PRIMARY decode down path
// (`lagunaFusedRoutedSharedDownResidualEnabled` defaults on and `residual` is
// always supplied); `lagunaRoutedDownReduce` above is its fallback. It is also
// the only kernel where the routed and shared scale planes now carry different
// row strides, so it is the riskiest arm of this change.
let baseFused = runSdr(pBaseSdr, activated: baseActivated,
                       weight: downWeight, scales: downScales)
let candFused = runSdr(pCandSdr, activated: candActivated,
                       weight: downWeight, scales: halvedDown)
let sdrDiff = diffCount(baseFused, candFused)
print("sdr output        \(downOutBytes) B, differing bytes = \(sdrDiff)")
if sdrDiff != 0 { failures.append("sdr output differs in \(sdrDiff) bytes") }

// A degenerate all-zero output would make any memcmp trivially pass.
let nonZero = baseActivated.contains { $0 != 0 }
    && baseRouted.contains { $0 != 0 }
    && baseFused.contains { $0 != 0 }
print("baseline outputs non-degenerate: \(nonZero)")
if !nonZero { failures.append("baseline output is all zero; comparison is vacuous") }

// MARK: - Power controls
//
// Each control breaks the candidate in a way the halving could plausibly break
// it for real. A control that does NOT change the output proves the harness is
// blind to that fault class, so it is a harness failure, not a pass.

print("\n=== power controls (each MUST flag) ===")

func control(_ label: String, _ diff: Int) {
    print("\(label): differing bytes = \(diff) -> \(diff != 0 ? "FLAGGED" : "BLIND")")
    if diff == 0 { failures.append("power control '\(label)' did not flag") }
}

// 1. Incoherent fault: drop the exception restore, i.e. let the patch header
//    carry the even byte so the odd group-32 member silently inherits it.
//    This is exactly the bug the whole design exists to avoid.
var incoherentPacked = halvedPacked
for (slot, p) in packedAllowed.enumerated() { incoherentPacked[slot] = packedScales[2 * p] }
control("1a. packed patch header dropped (even byte substituted)",
        diffCount(baseActivated, runR1(pCandR1, scales: incoherentPacked)))

var incoherentDown = halvedDown
for (slot, p) in downAllowed.enumerated() { incoherentDown[slot] = downScales[2 * p] }
control("1b. down patch header dropped (even byte substituted)",
        diffCount(baseRouted, runDown(pCandDown, activated: baseActivated,
                                      weight: downWeight, scales: incoherentDown)))

// 2. Ordinary halved scale byte perturbed by one bit.
var bitflipPacked = halvedPacked
bitflipPacked[patchHeaderBytes + 1000] ^= 0x01
control("2a. ordinary halved packed scale byte bit-flipped",
        diffCount(baseActivated, runR1(pCandR1, scales: bitflipPacked)))

var bitflipDown = halvedDown
bitflipDown[patchHeaderBytes + 1000] ^= 0x01
control("2b. ordinary halved down scale byte bit-flipped",
        diffCount(baseRouted, runDown(pCandDown, activated: baseActivated,
                                      weight: downWeight, scales: bitflipDown)))

control("1c. sdr patch header dropped (even byte substituted)",
        diffCount(baseFused, runSdr(pCandSdr, activated: baseActivated,
                                    weight: downWeight, scales: incoherentDown)))
control("2c. ordinary halved sdr scale byte bit-flipped",
        diffCount(baseFused, runSdr(pCandSdr, activated: baseActivated,
                                    weight: downWeight, scales: bitflipDown)))

// 3. Weight byte corrupted: confirms the harness sees the weight plane at all
//    and is not accidentally reading a cached or constant-folded result.
var corruptDownWeight = downWeight
corruptDownWeight[4096] ^= 0xFF
control("3a. down weight byte corrupted",
        diffCount(baseRouted, runDown(pCandDown, activated: baseActivated,
                                      weight: corruptDownWeight, scales: halvedDown)))
control("3b. sdr weight byte corrupted",
        diffCount(baseFused, runSdr(pCandSdr, activated: baseActivated,
                                    weight: corruptDownWeight, scales: halvedDown)))

print("\n=== verdict ===")
if failures.isEmpty {
    print("PASS: halved scale planes reproduce the shipped routed decode outputs "
          + "bit-exactly, and all power controls flagged.")
} else {
    for f in failures { print("FAIL: \(f)") }
    exit(1)
}
