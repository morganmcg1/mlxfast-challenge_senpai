// Research-only, offline, CPU-only checkpoint slab census.
//
// Answers PR #143 Step 0: are any routed-expert weight slabs or scale planes in
// the 21.6 GB NVFP4 checkpoint byte-identical to each other?
//
// Build:
//   swiftc -O research/nezuko_slab_census.swift -o /tmp/slab_census
// Run:
//   /tmp/slab_census --weights weights --mode probe        # sound upper bound
//   /tmp/slab_census --weights weights --mode full         # exact classes
//   /tmp/slab_census --weights weights --mode rows         # sub-slab census
//   /tmp/slab_census --weights weights --mode entropy      # lossless floor
//
// The `probe` mode is a *sound falsifier*: byte-identical slabs necessarily
// share every prefix, so the prefix-collision rate is an upper bound on the
// true byte-duplicate rate. It reads ~1% of the checkpoint.

import Foundation
import CryptoKit

// MARK: - safetensors header

struct TensorInfo {
    let name: String
    let dtype: String
    let shape: [Int]
    let start: Int   // absolute file offset
    let end: Int
    let shard: Int
}

func itemSize(_ dtype: String) -> Int {
    switch dtype {
    case "BF16", "F16", "I16", "U16": return 2
    case "F32", "I32", "U32": return 4
    case "U8", "I8", "BOOL": return 1
    case "F64", "I64", "U64": return 8
    default: fatalError("unknown dtype \(dtype)")
    }
}

func readHeader(_ url: URL, shard: Int) -> [TensorInfo] {
    let fh = try! FileHandle(forReadingFrom: url)
    defer { try? fh.close() }
    let lenData = try! fh.read(upToCount: 8)!
    let headerLen = lenData.withUnsafeBytes { $0.load(as: UInt64.self) }
    let hdrData = try! fh.read(upToCount: Int(headerLen))!
    let obj = try! JSONSerialization.jsonObject(with: hdrData) as! [String: Any]
    let dataStart = 8 + Int(headerLen)
    var out: [TensorInfo] = []
    for (name, v) in obj {
        if name == "__metadata__" { continue }
        let d = v as! [String: Any]
        let offs = d["data_offsets"] as! [Int]
        out.append(TensorInfo(name: name,
                              dtype: d["dtype"] as! String,
                              shape: (d["shape"] as! [Int]),
                              start: dataStart + offs[0],
                              end: dataStart + offs[1],
                              shard: shard))
    }
    return out
}

// MARK: - slab model

struct Slab {
    let role: String     // canonical family, e.g. "routed.gate_proj.weight"
    let tensor: String
    let layer: Int       // -1 when absent
    let expert: Int      // -1 when not a stacked expert slab
    let shard: Int
    let offset: Int
    let length: Int
    let rowBytes: Int    // bytes per logical row inside the slab
    let rows: Int
}

func layerIndex(_ name: String) -> Int {
    guard let r = name.range(of: #"layers\.(\d+)\."#, options: .regularExpression) else { return -1 }
    let s = name[r].dropFirst("layers.".count).dropLast()
    return Int(s) ?? -1
}

/// Canonical family name, layer index stripped.
func roleName(_ name: String) -> String {
    var n = name.replacingOccurrences(of: #"^model\.layers\.\d+\."#,
                                      with: "", options: .regularExpression)
    n = n.replacingOccurrences(of: "mlp.switch_mlp.", with: "routed.")
    n = n.replacingOccurrences(of: "mlp.shared_expert.", with: "shared.")
    n = n.replacingOccurrences(of: "self_attn.", with: "attn.")
    n = n.replacingOccurrences(of: "mlp.gate.", with: "router.")
    n = n.replacingOccurrences(of: "mlp.", with: "dense.")
    return n
}

func buildSlabs(_ tensors: [TensorInfo]) -> [Slab] {
    var slabs: [Slab] = []
    for t in tensors {
        let isz = itemSize(t.dtype)
        let role = roleName(t.name)
        let layer = layerIndex(t.name)
        let total = t.end - t.start
        if t.name.contains("switch_mlp") {
            // stacked [E, R, C] -> one slab per expert
            precondition(t.shape.count == 3, "unexpected stacked shape \(t.shape)")
            let e = t.shape[0], r = t.shape[1], c = t.shape[2]
            let per = r * c * isz
            precondition(per * e == total, "stacked size mismatch \(t.name)")
            for i in 0..<e {
                slabs.append(Slab(role: role, tensor: t.name, layer: layer, expert: i,
                                  shard: t.shard, offset: t.start + i * per,
                                  length: per, rowBytes: c * isz, rows: r))
            }
        } else {
            let rowBytes = (t.shape.last ?? 1) * isz
            slabs.append(Slab(role: role, tensor: t.name, layer: layer, expert: -1,
                              shard: t.shard, offset: t.start, length: total,
                              rowBytes: rowBytes, rows: rowBytes > 0 ? total / rowBytes : 1))
        }
    }
    return slabs
}

// MARK: - hashing

/// 128-bit digest prefix, ample for ~6e4..6e8 items (collision p < 1e-20).
struct Key: Hashable {
    let a: UInt64
    let b: UInt64
}

@inline(__always)
func key(_ p: UnsafeRawPointer, _ n: Int) -> Key {
    var h = SHA256()
    h.update(bufferPointer: UnsafeRawBufferPointer(start: p, count: n))
    var a: UInt64 = 0, b: UInt64 = 0
    h.finalize().withUnsafeBytes { raw in
        a = raw.load(fromByteOffset: 0, as: UInt64.self)
        b = raw.load(fromByteOffset: 8, as: UInt64.self)
    }
    return Key(a: a, b: b)
}

// MARK: - mmap

final class Mapped {
    let base: UnsafeRawPointer
    let size: Int
    private let fd: Int32
    init(_ path: String) {
        fd = open(path, O_RDONLY)
        precondition(fd >= 0, "open failed \(path)")
        var st = stat()
        fstat(fd, &st)
        size = Int(st.st_size)
        let m = mmap(nil, size, PROT_READ, MAP_PRIVATE, fd, 0)!
        precondition(m != UnsafeMutableRawPointer(bitPattern: -1))
        base = UnsafeRawPointer(m)
    }
    deinit { munmap(UnsafeMutableRawPointer(mutating: base), size); close(fd) }
}

// MARK: - reporting helpers

func fmtBytes(_ n: Int) -> String {
    let d = Double(n)
    if n >= 1 << 30 { return String(format: "%.2f GiB", d / Double(1 << 30)) }
    if n >= 1 << 20 { return String(format: "%.2f MiB", d / Double(1 << 20)) }
    if n >= 1 << 10 { return String(format: "%.2f KiB", d / Double(1 << 10)) }
    return "\(n) B"
}

func pct(_ a: Int, _ b: Int) -> String {
    b == 0 ? "n/a" : String(format: "%.4f%%", 100.0 * Double(a) / Double(b))
}

// MARK: - main

var weightsDir = "weights"
var mode = "probe"
var probeBytes = 4096
var args = Array(CommandLine.arguments.dropFirst())
var i = 0
while i < args.count {
    switch args[i] {
    case "--weights": weightsDir = args[i + 1]; i += 2
    case "--mode": mode = args[i + 1]; i += 2
    case "--probe-bytes": probeBytes = Int(args[i + 1])!; i += 2
    default: fatalError("unknown arg \(args[i])")
    }
}

let dir = URL(fileURLWithPath: weightsDir)
var tensors: [TensorInfo] = []
var maps: [Int: Mapped] = [:]
for s in 1...5 {
    let p = dir.appendingPathComponent(String(format: "model-%05d-of-00005.safetensors", s))
    tensors += readHeader(p, shard: s)
    maps[s] = Mapped(p.path)
}
tensors.sort { ($0.shard, $0.start) < ($1.shard, $1.start) }
let slabs = buildSlabs(tensors).sorted { ($0.shard, $0.offset) < ($1.shard, $1.offset) }

print("# checkpoint slab census")
print("dir: \(weightsDir)")
print("tensors: \(tensors.count)   slabs: \(slabs.count)")
let totalBytes = slabs.reduce(0) { $0 + $1.length }
print("slab bytes: \(fmtBytes(totalBytes))  (\(totalBytes))")
print("mode: \(mode)")
print("")

// ---- enumerator self-check --------------------------------------------
// Every slab must occupy a distinct (shard, offset) region and must lie
// inside its shard. A repeated site would let the tool "discover" a
// duplicate that is really the same bytes hashed twice.
do {
    var sites = Set<String>()
    var repeated = 0, overlapping = 0, outOfRange = 0
    var prevShard = -1, prevEnd = 0
    for s in slabs {
        if !sites.insert("\(s.shard):\(s.offset)").inserted { repeated += 1 }
        if s.shard == prevShard && s.offset < prevEnd { overlapping += 1 }
        if s.offset < 0 || s.offset + s.length > maps[s.shard]!.size { outOfRange += 1 }
        prevShard = s.shard; prevEnd = s.offset + s.length
    }
    print("## enumerator self-check")
    print("")
    print("- distinct (shard, offset) sites: \(sites.count) of \(slabs.count) slabs")
    print("- repeated sites: \(repeated)   overlapping slabs: \(overlapping)"
          + "   out-of-range slabs: \(outOfRange)")
    print("- verdict: \(repeated == 0 && overlapping == 0 && outOfRange == 0 ? "PASS" : "FAIL")")
    print("")
}

// ---- inventory by role -------------------------------------------------
print("## inventory by role")
print("")
print("| role | slabs | bytes each | total bytes | share |")
print("|---|---|---|---|---|")
var byRole: [String: [Slab]] = [:]
for s in slabs { byRole[s.role, default: []].append(s) }
for (role, ss) in byRole.sorted(by: { $0.value.reduce(0) { $0 + $1.length } > $1.value.reduce(0) { $0 + $1.length } }) {
    let tb = ss.reduce(0) { $0 + $1.length }
    let each = Set(ss.map(\.length)).count == 1 ? "\(ss[0].length)" : "mixed"
    print("| `\(role)` | \(ss.count) | \(each) | \(tb) | \(pct(tb, totalBytes)) |")
}
print("")

// ---- hash pass ---------------------------------------------------------
// probe: hash min(probeBytes, len) leading bytes -> sound upper bound.
// full:  hash the whole slab -> exact equivalence classes.
let n = slabs.count
var keys = [Key](repeating: Key(a: 0, b: 0), count: n)
var zeroFlags = [Bool](repeating: false, count: n)
var constFlags = [Bool](repeating: false, count: n)

let t0 = Date()
if mode == "probe" || mode == "full" {
    let lock = NSLock()
    var hashedBytes = 0
    DispatchQueue.concurrentPerform(iterations: n) { idx in
        let s = slabs[idx]
        let p = maps[s.shard]!.base.advanced(by: s.offset)
        let take = mode == "probe" ? min(probeBytes, s.length) : s.length
        keys[idx] = key(p, take)
        if mode == "full" {
            // zero / constant-byte detection over the full slab
            let bytes = UnsafeRawBufferPointer(start: p, count: s.length)
            let first = bytes[0]
            var allSame = true
            for b in bytes where b != first { allSame = false; break }
            constFlags[idx] = allSame
            zeroFlags[idx] = allSame && first == 0
        }
        lock.lock(); hashedBytes += take; lock.unlock()
    }
    let dt = Date().timeIntervalSince(t0)
    print("## hash pass")
    print("")
    print("- bytes hashed: \(fmtBytes(hashedBytes)) (\(hashedBytes))")
    print("- wall: \(String(format: "%.2f", dt)) s")
    print("- fraction of checkpoint read: \(pct(hashedBytes, totalBytes))")
    print("")

    // ---- equivalence classes -----------------------------------------
    // Slabs of different length can never be byte-identical; include length
    // in the class identity so a truncated probe cannot merge them.
    struct ClassKey: Hashable { let k: Key; let len: Int }
    var classes: [ClassKey: [Int]] = [:]
    for idx in 0..<n { classes[ClassKey(k: keys[idx], len: slabs[idx].length), default: []].append(idx) }

    let dupClasses = classes.filter { $0.value.count > 1 }
    var dupSlabs = 0, dupBytes = 0, redundantSlabs = 0, redundantBytes = 0
    for (_, v) in dupClasses {
        dupSlabs += v.count
        dupBytes += v.count * slabs[v[0]].length
        redundantSlabs += v.count - 1                    // removable copies
        redundantBytes += (v.count - 1) * slabs[v[0]].length
    }

    let label = mode == "probe" ? "UPPER BOUND (prefix screen)" : "EXACT"
    print("## duplicate verdict — \(label)")
    print("")
    print("- distinct classes: \(classes.count) of \(n) slabs")
    print("- classes with >1 member: \(dupClasses.count)")
    print("- slabs in a duplicate class: \(dupSlabs) / \(n) = \(pct(dupSlabs, n))")
    print("- **removable (redundant) slabs: \(redundantSlabs) / \(n) = \(pct(redundantSlabs, n))**")
    print("- **removable bytes: \(fmtBytes(redundantBytes)) / \(fmtBytes(totalBytes)) = \(pct(redundantBytes, totalBytes))**")
    print("")

    // routed-expert-only view: the arm's actual target
    let routedIdx = (0..<n).filter { slabs[$0].role.hasPrefix("routed.") }
    var rClasses: [ClassKey: [Int]] = [:]
    for idx in routedIdx { rClasses[ClassKey(k: keys[idx], len: slabs[idx].length), default: []].append(idx) }
    let rRedundant = rClasses.values.reduce(0) { $0 + ($1.count - 1) }
    let rRedundantBytes = rClasses.values.reduce(0) { $0 + ($1.count - 1) * slabs[$1[0]].length }
    let rBytes = routedIdx.reduce(0) { $0 + slabs[$1].length }
    print("### routed experts only (the arm's target)")
    print("")
    print("- routed slabs: \(routedIdx.count), bytes \(fmtBytes(rBytes))")
    print("- removable slabs: \(rRedundant) = \(pct(rRedundant, routedIdx.count))")
    print("- **removable bytes: \(fmtBytes(rRedundantBytes)) = \(pct(rRedundantBytes, rBytes))**")
    print("")

    // per-role breakdown of duplicates
    if !dupClasses.isEmpty {
        print("### duplicate classes by role")
        print("")
        print("| role | classes | members | removable slabs | removable bytes |")
        print("|---|---|---|---|---|")
        var agg: [String: (Int, Int, Int, Int)] = [:]
        for (_, v) in dupClasses {
            let r = slabs[v[0]].role
            var a = agg[r] ?? (0, 0, 0, 0)
            a.0 += 1; a.1 += v.count; a.2 += v.count - 1
            a.3 += (v.count - 1) * slabs[v[0]].length
            agg[r] = a
        }
        for (r, a) in agg.sorted(by: { $0.value.3 > $1.value.3 }) {
            print("| `\(r)` | \(a.0) | \(a.1) | \(a.2) | \(a.3) |")
        }
        print("")

        // class-size histogram
        var sizeHist: [Int: Int] = [:]
        for (_, v) in dupClasses { sizeHist[v.count, default: 0] += 1 }
        print("### duplicate class-size histogram")
        print("")
        print("| members per class | classes |")
        print("|---|---|")
        for (k, v) in sizeHist.sorted(by: { $0.key < $1.key }) { print("| \(k) | \(v) |") }
        print("")

        // clustering + memcmp verification of every class (capped listing)
        print("### duplicate classes (verified by memcmp)")
        print("")
        var verified = 0, failed = 0, listed = 0
        var aliasedClasses = 0
        for (_, v) in dupClasses.sorted(by: { $0.value.count > $1.value.count }) {
            let a = slabs[v[0]]
            let pa = maps[a.shard]!.base.advanced(by: a.offset)
            var allEqual = true
            for j in v.dropFirst() {
                let b = slabs[j]
                let pb = maps[b.shard]!.base.advanced(by: b.offset)
                // in probe mode only the probed prefix is claimed identical
                let cmpLen = mode == "probe" ? min(probeBytes, min(a.length, b.length)) : a.length
                if a.length != b.length || memcmp(pa, pb, cmpLen) != 0 { allEqual = false }
            }
            // a duplicate is only real if every member occupies a distinct
            // (shard, offset) region; identical (shard, offset) would mean the
            // enumerator hashed the same bytes twice.
            let sites = Set(v.map { "\(slabs[$0].shard):\(slabs[$0].offset)" })
            let distinctSites = sites.count == v.count
            if !distinctSites { aliasedClasses += 1 }
            if allEqual { verified += 1 } else { failed += 1 }
            if listed < 40 {
                let members = v.map {
                    "L\(slabs[$0].layer)/e\(slabs[$0].expert)@s\(slabs[$0].shard)+\(slabs[$0].offset)"
                }.joined(separator: " ")
                print("- `\(a.role)` len=\(a.length) memcmp=\(allEqual ? "OK" : "MISMATCH")"
                      + " distinct-offsets=\(distinctSites ? "YES" : "NO/ALIASED") : \(members)")
                listed += 1
            }
        }
        if dupClasses.count > 40 { print("- … \(dupClasses.count - 40) more classes not listed") }
        print("")
        print("- memcmp verified classes: \(verified), mismatched: \(failed)")
        print("- classes whose members alias the same (shard, offset): \(aliasedClasses)")
        print("")
    } else {
        print("### no duplicate classes found at all")
        print("")
    }

    if mode == "full" {
        let zeros = (0..<n).filter { zeroFlags[$0] }
        let consts = (0..<n).filter { constFlags[$0] && !zeroFlags[$0] }
        print("### degenerate slabs")
        print("")
        print("- all-zero slabs: \(zeros.count) (\(fmtBytes(zeros.reduce(0) { $0 + slabs[$1].length })))")
        print("- constant-byte non-zero slabs: \(consts.count)")
        for idx in consts.prefix(20) { print("  - `\(slabs[idx].role)` L\(slabs[idx].layer)/e\(slabs[idx].expert)") }
        print("")

        // ---- near-duplicate line item --------------------------------
        // "identical mantissa, different scale plane" is directly observable:
        // weight and scales are separate tensors joined by (layer, role, expert).
        print("### near-duplicate line item: identical mantissa, differing scales")
        print("")
        var mantissaClasses: [ClassKey: [Int]] = [:]
        for idx in 0..<n where slabs[idx].role.hasSuffix(".weight") && slabs[idx].role.hasPrefix("routed.") {
            mantissaClasses[ClassKey(k: keys[idx], len: slabs[idx].length), default: []].append(idx)
        }
        let mDup = mantissaClasses.filter { $0.value.count > 1 }
        print("- routed mantissa slabs sharing bytes with another mantissa slab: \(mDup.values.reduce(0) { $0 + $1.count - 1 })")
        print("- (a mantissa-only match is NOT bit-exactly exploitable unless the paired scale plane also matches)")
        print("")
    }
}

// ---- sub-slab row census ----------------------------------------------
if mode == "rows" {
    print("## sub-slab row census")
    print("")
    print("Row-level duplicate structure inside each role. A row is the innermost")
    print("contiguous dimension of a slab. This is NOT part of the Step 0 gate: a")
    print("row-level dedup needs a per-row indirection whose own bytes must be paid.")
    print("")
    print("| role | rows | row bytes | distinct rows | removable rows | removable bytes | index cost @ 4B/row | net bytes |")
    print("|---|---|---|---|---|---|---|---|")
    for (role, ss) in byRole.sorted(by: { $0.key < $1.key }) {
        guard ss[0].rowBytes > 0, ss[0].rows > 1 else { continue }
        // sample every role fully but bound total work on the huge routed families
        let stride = role.hasPrefix("routed.") ? 8 : 1   // 1/8 of experts, uniform
        let picked = ss.enumerated().filter { $0.offset % stride == 0 }.map(\.element)
        var seen = Set<Key>()
        var rowCount = 0
        for s in picked {
            let p = maps[s.shard]!.base.advanced(by: s.offset)
            for r in 0..<s.rows {
                seen.insert(key(p.advanced(by: r * s.rowBytes), s.rowBytes))
                rowCount += 1
            }
        }
        let removable = rowCount - seen.count
        let rowBytes = ss[0].rowBytes
        let removableBytes = removable * rowBytes
        let indexCost = seen.count == rowCount ? 0 : rowCount * 4
        let net = removableBytes - indexCost
        let note = stride > 1 ? " (1/\(stride) sample)" : ""
        print("| `\(role)`\(note) | \(rowCount) | \(rowBytes) | \(seen.count) | \(removable) (\(pct(removable, rowCount))) | \(removableBytes) | \(indexCost) | \(net) |")
    }
    print("")
}

// ---- information-theoretic floor --------------------------------------
// Dedup is one member of the "spend fewer DRAM bytes on the same weights"
// family. Zeroth-order entropy over the actual plane bytes bounds EVERY
// memoryless lossless scheme (dedup, RLE, Huffman, dictionary) from below:
// no such scheme can emit fewer than H bits per symbol on average.
// NVFP4 mantissa symbols are 4-bit, so the nibble measure is the meaningful
// one for the weight planes; scales are U8, so the byte measure applies.
if mode == "entropy" {
    print("## information-theoretic floor per role")
    print("")
    print("A memoryless lossless recode cannot beat zeroth-order entropy.")
    print("`nibble H` is the relevant column for NVFP4 mantissa planes (4-bit")
    print("symbols); `byte H` is the relevant one for U8 scale planes.")
    print("")
    print("| role | bytes measured | byte H (bits/8b) | nibble H (bits/4b) | distinct byte codes | fixed-width LUT bits | LUT saving | best lossless size | max saving |")
    print("|---|---|---|---|---|---|---|---|---|")

    var roleOrder: [String] = []
    var seenRole = Set<String>()
    for s in slabs where !seenRole.contains(s.role) { seenRole.insert(s.role); roleOrder.append(s.role) }

    var floorTotal = 0.0, measuredTotal = 0
    for role in roleOrder.sorted() {
        let ss = byRole[role]!
        // Entropy of a mantissa plane is estimated from a strided sample of
        // whole slabs (unbiased for the symbol distribution). Scale planes are
        // scanned exhaustively: a distinct-code alphabet claim must be sound,
        // and a sample can only miss rare codes.
        let sampleOK = !role.hasSuffix(".scales")
        let stride = (sampleOK && ss.count > 512) ? ss.count / 512 : 1
        let picked = stride > 1 ? (0..<ss.count).filter { $0 % stride == 0 }.map { ss[$0] } : ss

        var byteHist = [Int](repeating: 0, count: 256)
        var nibHist = [Int](repeating: 0, count: 16)
        let lock = NSLock()
        DispatchQueue.concurrentPerform(iterations: picked.count) { k in
            let s = picked[k]
            let p = maps[s.shard]!.base.advanced(by: s.offset)
                                    .assumingMemoryBound(to: UInt8.self)
            var lb = [Int](repeating: 0, count: 256)
            var ln = [Int](repeating: 0, count: 16)
            for o in 0..<s.length {
                let b = p[o]
                lb[Int(b)] += 1
                ln[Int(b & 0x0F)] += 1
                ln[Int(b >> 4)] += 1
            }
            lock.lock()
            for j in 0..<256 { byteHist[j] += lb[j] }
            for j in 0..<16 { nibHist[j] += ln[j] }
            lock.unlock()
        }

        let measured = picked.reduce(0) { $0 + $1.length }
        func entropy(_ h: [Int]) -> Double {
            let tot = Double(h.reduce(0, +))
            guard tot > 0 else { return 0 }
            var e = 0.0
            for c in h where c > 0 { let p = Double(c) / tot; e -= p * log2(p) }
            return e
        }
        let hB = entropy(byteHist), hN = entropy(nibHist)
        // charge each plane at its natural symbol width
        let bitsPerByte = role.hasSuffix(".scales") ? hB : hN * 2
        let roleTotal = ss.reduce(0) { $0 + $1.length }
        let floor = Double(roleTotal) * bitsPerByte / 8.0
        floorTotal += floor
        measuredTotal += measured
        let saving = 1.0 - bitsPerByte / 8.0
        // Entropy coding is not randomly accessible, so it cannot serve a
        // kernel that gathers an arbitrary expert's row. A *fixed-width*
        // recode over the observed alphabet is randomly accessible and
        // bit-exact (the LUT returns the original byte), so the distinct-code
        // count is the actionable statistic for the scale planes.
        let distinct = byteHist.filter { $0 > 0 }.count
        let lutBits = distinct <= 1 ? 0 : Int(ceil(log2(Double(distinct))))
        let lutSaving = 1.0 - Double(lutBits) / 8.0
        let note = stride > 1 ? " (1/\(stride) sample)" : ""
        print("| `\(role)`\(note) | \(fmtBytes(measured)) | "
              + String(format: "%.4f", hB) + " | " + String(format: "%.4f", hN)
              + " | \(distinct) | \(lutBits) | "
              + String(format: "%+.2f%%", lutSaving * 100)
              + " | \(fmtBytes(Int(floor))) | "
              + String(format: "%+.2f%%", saving * 100) + " |")
    }
    print("")
    print("- bytes actually measured: \(fmtBytes(measuredTotal))")
    print("- checkpoint size: \(fmtBytes(totalBytes))")
    print("- best-case memoryless lossless size: \(fmtBytes(Int(floorTotal)))")
    let maxSave = 1.0 - floorTotal / Double(totalBytes)
    print("- **maximum achievable saving from ANY memoryless lossless scheme: "
          + String(format: "%+.2f%%", maxSave * 100) + "**")
    print("")

    let routedTotal = roleOrder.filter { $0.hasPrefix("routed.") }
        .reduce(0) { $0 + byRole[$1]!.reduce(0) { $0 + $1.length } }
    print("- routed plane bytes: \(fmtBytes(routedTotal)) "
          + "(\(pct(routedTotal, totalBytes)) of checkpoint)")
    print("")

    // ---- per-slab scale alphabet --------------------------------------
    // A whole-plane alphabet forces one global LUT. A *per-slab* LUT is far
    // cheaper to exploit: its table is amortised over the slab and, if the
    // per-slab alphabet fits 16 codes, the recode is a byte-aligned nibble
    // pack identical in shape to the existing FP4 mantissa packing.
    print("## per-slab scale alphabet (exhaustive)")
    print("")
    print("| role | slabs | max codes in any slab | p50 | p99 | slabs >16 codes | LUT bits | scale-plane saving |")
    print("|---|---|---|---|---|---|---|---|")
    for role in roleOrder.sorted() where role.hasSuffix(".scales") {
        let ss = byRole[role]!
        var counts = [Int](repeating: 0, count: ss.count)
        DispatchQueue.concurrentPerform(iterations: ss.count) { k in
            let s = ss[k]
            let p = maps[s.shard]!.base.advanced(by: s.offset)
                                    .assumingMemoryBound(to: UInt8.self)
            var seen = [Bool](repeating: false, count: 256)
            var c = 0
            for o in 0..<s.length where !seen[Int(p[o])] { seen[Int(p[o])] = true; c += 1 }
            counts[k] = c
        }
        let sorted = counts.sorted()
        let maxC = sorted.last ?? 0
        let p50 = sorted[sorted.count / 2]
        let p99 = sorted[min(sorted.count - 1, (sorted.count * 99) / 100)]
        let over16 = counts.filter { $0 > 16 }.count
        let bits = maxC <= 1 ? 0 : Int(ceil(log2(Double(maxC))))
        print("| `\(role)` | \(ss.count) | \(maxC) | \(p50) | \(p99) | \(over16) | \(bits) | "
              + String(format: "%+.2f%%", (1.0 - Double(bits) / 8.0) * 100) + " |")
    }
    print("")
}

print("wall total: \(String(format: "%.2f", Date().timeIntervalSince(t0))) s")
