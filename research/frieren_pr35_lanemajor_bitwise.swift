// r5-A: bit-for-bit differential certificate for the lane-major NVFP4 QKV scale
// bank against the wide (byte-plane) kernel.
//
// Both kernel texts are the *exact* strings MLX handed to `makeLibrary` on this
// host, captured from the scored runtime with `verbose: true` and committed
// under research/r5a_kernels/. This harness compiles both in one process with
// the same compile options MLX uses, runs them on identical activations and
// identical weight payloads, and compares the output buffers with memcmp.
//
// Build:
//   swiftc -O research/frieren_pr35_lanemajor_bitwise.swift \
//     -o /tmp/frieren_pr35_bitwise -framework Metal -framework Foundation
// Run:
//   /tmp/frieren_pr35_bitwise --planes /tmp/pr35_r5a --repo .

import Foundation
import Metal

// ---------------------------------------------------------------- infrastructure

func die(_ message: String) -> Never {
    FileHandle.standardError.write(Data(("FATAL: " + message + "\n").utf8))
    exit(2)
}

func say(_ message: String) {
    print(message)
    fflush(stdout)
}

func arg(_ name: String, default def: String) -> String {
    let argv = CommandLine.arguments
    guard let i = argv.firstIndex(of: name), i + 1 < argv.count else { return def }
    return argv[i + 1]
}

struct Rng {
    var state: UInt64
    init(_ seed: UInt64) { state = seed }
    mutating func next() -> UInt64 {
        state = state &+ 0x9E3779B97F4A7C15
        var z = state
        z = (z ^ (z >> 30)) &* 0xBF58476D1CE4E5B9
        z = (z ^ (z >> 27)) &* 0x94D049BB133111EB
        return z ^ (z >> 31)
    }
    mutating func unit() -> Float { Float(next() >> 40) * (1.0 / 16777216.0) }
    mutating func byte() -> UInt8 { UInt8(truncatingIfNeeded: next() >> 33) }
}

// round-to-nearest-even float32 -> bfloat16 bit pattern
func bf16Bits(_ value: Float) -> UInt16 {
    let bits = value.bitPattern
    let lower = bits & 0xFFFF
    var upper = bits >> 16
    if lower > 0x8000 || (lower == 0x8000 && (upper & 1) == 1) { upper &+= 1 }
    return UInt16(truncatingIfNeeded: upper)
}

// monotone integer key so |key(a) - key(b)| is the ULP distance for bfloat16
func bf16Ord(_ bits: UInt16) -> Int32 {
    if bits & 0x8000 != 0 { return -Int32(bits & 0x7FFF) }
    return Int32(bits)
}

// -------------------------------------------------------------- source assembly

func readText(_ path: String) -> String {
    guard let data = FileManager.default.contents(atPath: path),
          let text = String(data: data, encoding: .utf8) else {
        die("cannot read \(path)")
    }
    return text
}

func readBytes(_ path: String) -> [UInt8] {
    guard let data = FileManager.default.contents(atPath: path) else {
        die("cannot read \(path)")
    }
    return [UInt8](data)
}

/// MLX builds every JIT library as `metal::utils()` preamble + generated source
/// (backend/metal/custom_kernel.cpp). `verbose: true` prints only the generated
/// half, so the preamble is recovered from the committed vendor literal.
func loadPreamble(repo: String) -> String {
    let path = repo + "/Vendor/mlx-swift/Source/Cmlx/mlx-generated/utils.cpp"
    let text = readText(path)
    guard let open = text.range(of: "R\"preamble("),
          let close = text.range(of: ")preamble\"", range: open.upperBound..<text.endIndex) else {
        die("preamble markers not found in \(path)")
    }
    return String(text[open.upperBound..<close.lowerBound])
}

func entryPoint(of source: String) -> String {
    guard let kw = source.range(of: "[[kernel]] void ") else { die("no [[kernel]] in source") }
    let tail = source[kw.upperBound...]
    guard let paren = tail.firstIndex(of: "(") else { die("malformed kernel signature") }
    return String(tail[tail.startIndex..<paren]).trimmingCharacters(in: .whitespacesAndNewlines)
}

// ----------------------------------------------------------------- lane-major bank

/// Hand port of `lagunaLaneMajorNVFP4ScaleBank` (LagunaRuntimeWeights.swift:847).
/// Verified against the runtime's own dumped bank for all 40 layers (plane P0).
struct Bank {
    var nibbles: [UInt8]
    var bases: [UInt8]
    var escapedRows: Int
}

func buildBank(plane: [UInt8], rows: Int, groups: Int) -> Bank {
    precondition(groups == 128)
    let blocks = groups / 32
    var nibbles = [UInt8](repeating: 0, count: rows * groups / 2)
    var bases = [UInt8](repeating: 0, count: rows)
    var escaped = 0
    for r in 0..<rows {
        let row = r * groups
        var mn = UInt8(255)
        var mx = UInt8(0)
        for g in 0..<groups {
            let v = plane[row + g]
            if v < mn { mn = v }
            if v > mx { mx = v }
        }
        let fits = Int(mx) - Int(mn) <= 15
        bases[r] = fits ? mn : 0xFF
        if !fits { escaped += 1; continue }
        for l in 0..<32 {
            for b in 0..<blocks {
                let flat = l * blocks + b
                let k = flat / 2
                let idx = UInt8(Int(plane[row + b * 32 + l]) - Int(mn)) & 0x0F
                if flat % 2 == 0 {
                    nibbles[r * (groups / 2) + k] |= idx
                } else {
                    nibbles[r * (groups / 2) + k] |= idx << 4
                }
            }
        }
    }
    return Bank(nibbles: nibbles, bases: bases, escapedRows: escaped)
}

// ------------------------------------------------------------------- plane specs

// Every synthetic scale byte stays inside [8, 247]: `laguna_tail_nvfp4_scale`
// builds a half from `bits << 7`, so bits >= 248 decode to inf and bits < 8 to a
// denormal. Real codes observed on this checkpoint top out at 41.
func synthBase(_ r: Int) -> Int { 8 + (r % 190) }

enum Perturb { case none, rotateNibbles, flipBaseBit, singleNibble }

struct PlaneSpec {
    let name: String
    let mustFlag: Bool
    let perturb: Perturb
    let make: (Int) -> [UInt8]   // rows -> plane bytes
}

func planeP1(_ rows: Int) -> [UInt8] {
    var p = [UInt8](repeating: 0, count: rows * 128)
    for r in 0..<rows {
        let base = synthBase(r)
        for g in 0..<128 {
            let l = g % 32, b = g / 32
            p[r * 128 + g] = UInt8(base + ((b + l) % 16))
        }
    }
    return p
}

func planeP1H(_ rows: Int) -> [UInt8] {
    var p = [UInt8](repeating: 0, count: rows * 128)
    for r in 0..<rows {
        let base = synthBase(r)
        let hotL = r % 32, hotB = (r / 32) % 4
        for g in 0..<128 {
            let l = g % 32, b = g / 32
            p[r * 128 + g] = UInt8(base + ((l == hotL && b == hotB) ? 15 : 0))
        }
    }
    return p
}

func planeP2(_ rows: Int) -> [UInt8] {
    var p = [UInt8](repeating: 0, count: rows * 128)
    for r in 0..<rows {
        let base = synthBase(r)
        for g in 0..<128 {
            let l = g % 32, b = g / 32
            p[r * 128 + g] = UInt8(base + ((12 * l + 7 * b) % 16))
        }
    }
    return p
}

func planeP3(_ rows: Int) -> [UInt8] {
    var p = planeP1(rows)
    for r in stride(from: 3, to: rows, by: 7) {
        for g in 0..<128 { p[r * 128 + g] = UInt8(8 + ((7 * g) % 239)) }
    }
    return p
}

let planeSpecs: [PlaneSpec] = [
    PlaneSpec(name: "P1-injective", mustFlag: false, perturb: .none, make: planeP1),
    PlaneSpec(name: "P1H-onehot", mustFlag: false, perturb: .none, make: planeP1H),
    PlaneSpec(name: "P2-stride", mustFlag: false, perturb: .none, make: planeP2),
    PlaneSpec(name: "P3-mixed-escape", mustFlag: false, perturb: .none, make: planeP3),
    PlaneSpec(name: "P4a-rotate-nibbles", mustFlag: true, perturb: .rotateNibbles, make: planeP1),
    PlaneSpec(name: "P4b-flip-base-bit", mustFlag: true, perturb: .flipBaseBit, make: planeP1),
    PlaneSpec(name: "P4c-single-nibble", mustFlag: true, perturb: .singleNibble, make: planeP1),
]

func applyPerturb(_ kind: Perturb, bank: inout Bank, rows: Int) -> String {
    switch kind {
    case .none:
        return "-"
    case .rotateNibbles:
        for r in 0..<rows {
            if bank.bases[r] == 0xFF { continue }
            for l in 0..<32 {
                let lo = Int(bank.nibbles[r * 64 + 2 * l])
                let hi = Int(bank.nibbles[r * 64 + 2 * l + 1])
                let packed = lo | (hi << 8)
                let rot = ((packed >> 4) | (packed << 12)) & 0xFFFF
                bank.nibbles[r * 64 + 2 * l] = UInt8(rot & 0xFF)
                bank.nibbles[r * 64 + 2 * l + 1] = UInt8((rot >> 8) & 0xFF)
            }
        }
        return "every lane ushort rotated by one nibble"
    case .flipBaseBit:
        for r in [0, rows / 2] where bank.bases[r] != 0xFF {
            bank.bases[r] ^= 1
        }
        return "bases[0] and bases[\(rows / 2)] xor 1"
    case .singleNibble:
        bank.nibbles[3 * 64 + 2 * 7] ^= 1
        return "row 3 lane 7 block 0 nibble xor 1"
    }
}

// ------------------------------------------------------------------------- setup

let repo = arg("--repo", default: ".")
let planeDir = arg("--planes", default: "/tmp/pr35_r5a")
let kernelDir = repo + "/research/r5a_kernels"

guard let device = MTLCreateSystemDefaultDevice() else { die("no Metal device") }
guard let queue = device.makeCommandQueue() else { die("no command queue") }

say("host          : \(ProcessInfo.processInfo.operatingSystemVersionString)")
say("device        : \(device.name)")
say("plane dir     : \(planeDir)")
say("kernel dir    : \(kernelDir)")

let options = MTLCompileOptions()
// MLX compiles JIT libraries with fastMath disabled (backend/metal/device.cpp:622).
// `mathMode = .safe` is the non-deprecated spelling of `fastMathEnabled = false`.
options.mathMode = .safe
// get_metal_version() selects 4.0 on macOS 26, 3.2 on macOS 15, else 3.1.
if #available(macOS 26.0, *) {
    options.languageVersion = .version4_0
} else if #available(macOS 15.0, *) {
    options.languageVersion = .version3_2
} else {
    options.languageVersion = .version3_1
}
say("compile opts  : mathMode=safe languageVersion=\(options.languageVersion.rawValue)")

let preamble = loadPreamble(repo: repo)
say("preamble      : \(preamble.utf8.count) bytes from Vendor/mlx-swift/.../mlx-generated/utils.cpp")

struct Pipe {
    let name: String
    let state: MTLComputePipelineState
}

func makePipe(_ file: String) -> Pipe {
    let generated = readText(kernelDir + "/" + file)
    let name = entryPoint(of: generated)
    let library: MTLLibrary
    do {
        library = try device.makeLibrary(source: preamble + generated, options: options)
    } catch {
        die("compile \(file): \(error)")
    }
    guard let fn = library.makeFunction(name: name) else { die("no function \(name) in \(file)") }
    do {
        let state = try device.makeComputePipelineState(function: fn)
        return Pipe(name: name, state: state)
    } catch {
        die("pipeline \(file): \(error)")
    }
}

// ------------------------------------------------- real call-site geometry check

let runtimePath = repo + "/Sources/MLXFastModel/LagunaRuntimeModel.swift"
let runtimeText = readText(runtimePath)
let requiredLiterals = ["grid: ((rows / 2) * 64, 1, 1)", "threadGroup: (64, 1, 1)"]
for literal in requiredLiterals {
    let count = runtimeText.components(separatedBy: literal).count - 1
    if count == 0 { die("call-site literal not found in LagunaRuntimeModel.swift: \(literal)") }
    say("call-site geom: \(count) occurrence(s) of `\(literal)`")
}
say("harness geom  : dispatchThreads(width: rows/2*64) tg(64,1,1)  [matches call site]")

// --------------------------------------------------------------------- activations

// Lane `l` of a simdgroup touches columns l*16..l*16+15 and the +512/+1024/+1536
// repeats of that run, so a lane-isolated activation exercises exactly one lane's
// four scale blocks and nothing else.
let axis = 2048
let passCount = 33
var activations: [[UInt16]] = []
var passLabels: [String] = []
do {
    var rng = Rng(0xA5A5_0001)
    var dense = [UInt16](repeating: 0, count: axis)
    for i in 0..<axis { dense[i] = bf16Bits(rng.unit() * 4.0 - 2.0) }
    activations.append(dense)
    passLabels.append("dense")
    for lane in 0..<32 {
        var v = [UInt16](repeating: 0, count: axis)
        for b in 0..<4 {
            for i in 0..<16 {
                v[b * 512 + lane * 16 + i] = bf16Bits(rng.unit() * 4.0 - 2.0)
            }
        }
        activations.append(v)
        passLabels.append("lane\(lane)")
    }
}

// ------------------------------------------------------------------ comparison run

struct Geom {
    let heads: Int
    let rows: Int
    let layers: [Int]
}

let geoms = [
    Geom(heads: 48, rows: 8192, layers: [0, 4, 8, 12, 16, 20, 24, 28, 32, 36]),
    Geom(heads: 64, rows: 10240, layers: Array(0..<40).filter { $0 % 4 != 0 }),
]

var failures: [String] = []
var missingFlags: [String] = []
var globalMaxUlp: Int32 = 0
var totalPairs = 0
var totalUncovered = 0

func buf(_ length: Int) -> MTLBuffer {
    guard let b = device.makeBuffer(length: max(length, 4), options: .storageModeShared) else {
        die("makeBuffer(\(length)) failed")
    }
    return b
}

func upload(_ b: MTLBuffer, _ bytes: [UInt8]) {
    bytes.withUnsafeBytes { src in b.contents().copyMemory(from: src.baseAddress!, byteCount: src.count) }
}

func upload16(_ b: MTLBuffer, _ words: [UInt16]) {
    words.withUnsafeBytes { src in b.contents().copyMemory(from: src.baseAddress!, byteCount: src.count) }
}

for geom in geoms {
    let rows = geom.rows
    say("")
    say("================ geometry h\(geom.heads): rows=\(rows) layers=\(geom.layers.count)")

    let lm = makePipe("lanemajor_h\(geom.heads).metal")
    let wide = makePipe("wide_h\(geom.heads).metal")
    for p in [lm, wide] {
        say("pipeline \(p.name)")
        say("   staticThreadgroupMemoryLength=\(p.state.staticThreadgroupMemoryLength)"
            + " maxTotalThreadsPerThreadgroup=\(p.state.maxTotalThreadsPerThreadgroup)"
            + " threadExecutionWidth=\(p.state.threadExecutionWidth)")
    }

    // Deterministic weight codes, held fixed for every plane in this geometry.
    var codes = [UInt8](repeating: 0, count: rows * 1024)
    do {
        var rng = Rng(UInt64(geom.heads) &* 0x1000193 &+ 7)
        for i in 0..<codes.count { codes[i] = rng.byte() }
    }
    let codesBuf = buf(codes.count)
    upload(codesBuf, codes)

    let actBufs = activations.map { a -> MTLBuffer in
        let b = buf(axis * 2)
        upload16(b, a)
        return b
    }
    let outWide = (0..<passCount).map { _ in buf(rows * 2) }
    let outLm = (0..<passCount).map { _ in buf(rows * 2) }
    let outWideB = (0..<passCount).map { _ in buf(rows * 2) }
    let outLmB = (0..<passCount).map { _ in buf(rows * 2) }

    let scalesBuf = buf(rows * 128)
    let nibBuf = buf(rows * 64)
    let baseBuf = buf(rows)

    func encodeAll(_ pipe: Pipe, _ bindings: [MTLBuffer], _ outs: [MTLBuffer], fill: Int32) {
        guard let cb = queue.makeCommandBuffer() else { die("no command buffer") }
        for p in 0..<outs.count {
            memset(outs[p].contents(), fill, rows * 2)
            guard let enc = cb.makeComputeCommandEncoder() else { die("no encoder") }
            enc.setComputePipelineState(pipe.state)
            enc.setBuffer(actBufs[p], offset: 0, index: 0)
            for (i, b) in bindings.enumerated() { enc.setBuffer(b, offset: 0, index: i + 1) }
            enc.setBuffer(outs[p], offset: 0, index: bindings.count + 1)
            enc.dispatchThreads(MTLSize(width: (rows / 2) * 64, height: 1, depth: 1),
                                threadsPerThreadgroup: MTLSize(width: 64, height: 1, depth: 1))
            enc.endEncoding()
        }
        cb.commit()
        cb.waitUntilCompleted()
        if let e = cb.error { die("dispatch \(pipe.name): \(e)") }
    }

    func words(_ b: MTLBuffer) -> [UInt16] {
        let p = b.contents().bindMemory(to: UInt16.self, capacity: rows)
        return Array(UnsafeBufferPointer(start: p, count: rows))
    }

    var planeJobs: [(String, [UInt8], Perturb, Bool, Int)] = []
    for layer in geom.layers {
        let tag = String(format: "L%02d", layer)
        let file = "\(planeDir)/plane_r\(rows)_g128_\(tag).bin"
        let plane = readBytes(file)
        if plane.count != rows * 128 { die("\(file): \(plane.count) bytes, expected \(rows * 128)") }
        planeJobs.append(("P0-real-\(tag)", plane, .none, false, layer))
    }
    for spec in planeSpecs {
        planeJobs.append((spec.name, spec.make(rows), spec.perturb, spec.mustFlag, -1))
    }

    for (planeName, plane, perturb, mustFlag, layer) in planeJobs {
        var bank = buildBank(plane: plane, rows: rows, groups: 128)

        if layer >= 0 {
            // P0 doubles as a check that this harness's bank builder is the same
            // function the runtime ran: compare against the runtime's own dump.
            let tag = String(format: "L%02d", layer)
            let refNib = readBytes("\(planeDir)/nibbles_r\(rows)_g128_\(tag).bin")
            let refBase = readBytes("\(planeDir)/bases_r\(rows)_g128_\(tag).bin")
            if refNib != bank.nibbles { failures.append("\(planeName): builder nibbles != runtime dump") }
            if refBase != bank.bases { failures.append("\(planeName): builder bases != runtime dump") }
        }

        let note = applyPerturb(perturb, bank: &bank, rows: rows)
        upload(scalesBuf, plane)
        upload(nibBuf, bank.nibbles)
        upload(baseBuf, bank.bases)

        // Each kernel runs twice over two *different* pre-fills. A row left
        // unwritten keeps its fill byte and therefore cannot agree across the
        // pair, so agreement proves full row coverage; it is also a per-pass
        // run-to-run determinism check. A fill-pattern collision with a
        // legitimate output value cannot mask this because the fills differ.
        encodeAll(wide, [codesBuf, scalesBuf], outWide, fill: 0xCD)
        encodeAll(wide, [codesBuf, scalesBuf], outWideB, fill: 0x37)
        encodeAll(lm, [codesBuf, nibBuf, baseBuf, scalesBuf], outLm, fill: 0xCD)
        encodeAll(lm, [codesBuf, nibBuf, baseBuf, scalesBuf], outLmB, fill: 0x37)

        var mismatchPasses = 0
        var mismatchRows = 0
        var maxUlp: Int32 = 0
        var uncovered = 0
        var vacuous = 0
        for p in 0..<passCount {
            let a = words(outWide[p])
            let b = words(outLm[p])
            let a2 = words(outWideB[p])
            let b2 = words(outLmB[p])
            totalPairs += 1
            var nonzero = 0
            var rowDiff = 0
            for r in 0..<rows {
                if a[r] != 0 { nonzero += 1 }
                if a[r] != a2[r] || b[r] != b2[r] { uncovered += 1 }
                if a[r] != b[r] {
                    rowDiff += 1
                    let d = abs(bf16Ord(a[r]) - bf16Ord(b[r]))
                    if d > maxUlp { maxUlp = d }
                }
            }
            if nonzero == 0 { vacuous += 1 }
            if rowDiff != 0 { mismatchPasses += 1; mismatchRows += rowDiff }
        }
        if !mustFlag && maxUlp > globalMaxUlp { globalMaxUlp = maxUlp }

        let verdict: String
        if mustFlag {
            if mismatchPasses == 0 {
                verdict = "SILENT (harness defect)"
                missingFlags.append("h\(geom.heads) \(planeName)")
            } else {
                verdict = "FLAGGED"
            }
        } else if mismatchPasses == 0 {
            verdict = "bit-identical"
        } else {
            verdict = "MISMATCH"
            failures.append("h\(geom.heads) \(planeName): \(mismatchPasses)/\(passCount) passes,"
                + " \(mismatchRows) rows, maxUlp=\(maxUlp)")
        }
        totalUncovered += uncovered
        if uncovered != 0 {
            failures.append("h\(geom.heads) \(planeName): \(uncovered) unwritten/nondeterministic rows")
        }
        if vacuous != 0 { failures.append("h\(geom.heads) \(planeName): \(vacuous) all-zero passes") }

        func pad(_ s: String, _ n: Int) -> String {
            s.count >= n ? s : s + String(repeating: " ", count: n - s.count)
        }
        say("  " + pad(planeName, 22)
            + " esc=" + pad(String(bank.escapedRows), 6)
            + " diffPasses=" + pad("\(mismatchPasses)/\(passCount)", 6)
            + " diffRows=" + pad(String(mismatchRows), 9)
            + " maxUlp=" + pad(String(maxUlp), 7)
            + pad(verdict, 24) + note)
    }
}

// ------------------------------------------------------------------------ verdict

say("")
say("pairs compared        : \(totalPairs)")
say("max ULP diff (P0-P3)  : \(globalMaxUlp)")
say("uncovered rows        : \(totalUncovered)  (two-fill coverage + determinism check)")
say("mismatch failures     : \(failures.count)")
for f in failures { say("   FAIL \(f)") }
say("silent power controls : \(missingFlags.count)")
for f in missingFlags { say("   SILENT \(f)") }

if failures.isEmpty && missingFlags.isEmpty {
    say("")
    say("R5A_VERDICT: PASS  (P0-P3 bit-identical on every geometry, plane and lane;"
        + " every P4 power control flagged)")
    exit(0)
}
say("")
say("R5A_VERDICT: FAIL")
exit(1)
