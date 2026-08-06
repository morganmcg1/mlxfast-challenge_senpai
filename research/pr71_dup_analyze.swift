// PR #71 Step 0 analysis: OLS slope of decode s/tok vs routed-QMV duplication
// count N, converted to achieved routed-gate/up DRAM bandwidth on M4 Pro.
//
// Usage:
//   xcrun swiftc -O research/pr71_dup_analyze.swift -o /tmp/pr71_analyze && \
//     /tmp/pr71_analyze research/pr71-dup/score.dup1.json research/pr71-dup/score.dup3.json ...
//
// Constants are documented in research/CURRENT_RESEARCH_STATE.md and the PR #71
// assignment body.

import Foundation

// Bytes moved by ONE extra routed gate/up QMV pass over the whole 128-step
// decode window, per decode step: 39 MoE layers x 9 MiB per layer.
let routedGateUpBytesPerStep = 39.0 * 9_437_184.0        // 368.0 MB
let m4CeilingGBs = 260.2                                  // research/host_bandwidth_ceiling.swift
let dispatchesPerCopy = 39.0
let dispatchOverheadLoUs = 0.36
let dispatchOverheadHiUs = 2.088

struct Arm {
    let n: Double
    let decode: Double
    let prefill: Double
    let correct: Bool
    let maxAbsDiff: Double
    let goldenHash: String
    let path: String
}

func firstNumber(_ text: String, _ key: String) -> Double? {
    guard let r = text.range(of: "\"\(key)\"") else { return nil }
    let tail = text[r.upperBound...]
    guard let colon = tail.firstIndex(of: ":") else { return nil }
    var s = ""
    for ch in tail[tail.index(after: colon)...] {
        if ch == " " || ch == "\n" || ch == "\t" { if s.isEmpty { continue } else { break } }
        if ch == "," || ch == "}" { break }
        s.append(ch)
    }
    return Double(s)
}

func firstString(_ text: String, _ key: String) -> String? {
    guard let r = text.range(of: "\"\(key)\"") else { return nil }
    let tail = text[r.upperBound...]
    guard let colon = tail.firstIndex(of: ":") else { return nil }
    guard let open = tail[tail.index(after: colon)...].firstIndex(of: "\"") else { return nil }
    let rest = tail[tail.index(after: open)...]
    guard let close = rest.firstIndex(of: "\"") else { return nil }
    return String(rest[rest.startIndex..<close])
}

func firstBool(_ text: String, _ key: String) -> Bool? {
    guard let r = text.range(of: "\"\(key)\"") else { return nil }
    let tail = text[r.upperBound...]
    if let t = tail.range(of: "true"), let f = tail.range(of: "false") {
        return t.lowerBound < f.lowerBound
    }
    return tail.range(of: "true") != nil
}

var arms: [Arm] = []
for path in CommandLine.arguments.dropFirst() {
    guard let text = try? String(contentsOfFile: path, encoding: .utf8) else {
        FileHandle.standardError.write("cannot read \(path)\n".data(using: .utf8)!)
        continue
    }
    // N is encoded in the filename: score.dup<N>.json
    let base = (path as NSString).lastPathComponent
    let digits = base.drop(while: { !$0.isNumber }).prefix(while: { $0.isNumber })
    guard let n = Double(digits) else {
        FileHandle.standardError.write("cannot parse N from \(base)\n".data(using: .utf8)!)
        continue
    }
    guard let decode = firstNumber(text, "decode_seconds_per_token"),
          let prefill = firstNumber(text, "prefill_seconds_per_token") else {
        FileHandle.standardError.write("missing timing keys in \(path)\n".data(using: .utf8)!)
        continue
    }
    arms.append(Arm(n: n, decode: decode, prefill: prefill,
                    correct: firstBool(text, "passed_correctness") ?? false,
                    maxAbsDiff: firstNumber(text, "max_abs_diff") ?? Double.nan,
                    goldenHash: firstString(text, "golden_hash") ?? "?",
                    path: path))
}
arms.sort { $0.n < $1.n }

guard arms.count >= 2 else {
    print("need >= 2 arms")
    exit(1)
}

print("=== arms ===")
for a in arms {
    print(String(format: "N=%.0f decode=%.9f s/tok prefill=%.9f  correct=%@ maxAbsDiff=%g golden=%@",
                 a.n, a.decode, a.prefill, a.correct ? "true" : "FALSE",
                 a.maxAbsDiff, String(a.goldenHash.prefix(12))))
}

let hashes = Set(arms.map { $0.goldenHash })
let allCorrect = arms.allSatisfy { $0.correct && $0.maxAbsDiff == 0 }
print("\nvalue preservation: goldenHash unique=\(hashes.count == 1) allCorrect=\(allCorrect)")
if hashes.count != 1 || !allCorrect {
    print("  !! the duplication fold changed observable output; instrument INVALID")
}

// OLS on decode s/tok vs N
let nBar = arms.map { $0.n }.reduce(0, +) / Double(arms.count)
let yBar = arms.map { $0.decode }.reduce(0, +) / Double(arms.count)
var sxy = 0.0, sxx = 0.0
for a in arms { sxy += (a.n - nBar) * (a.decode - yBar); sxx += (a.n - nBar) * (a.n - nBar) }
let slopeS = sxy / sxx
let intercept = yBar - slopeS * nBar
var ssr = 0.0, sst = 0.0
for a in arms {
    let fit = intercept + slopeS * a.n
    ssr += (a.decode - fit) * (a.decode - fit)
    sst += (a.decode - yBar) * (a.decode - yBar)
}
let r2 = sst > 0 ? 1 - ssr / sst : Double.nan
let slopeMs = slopeS * 1000.0

print("\n=== OLS: decode_s_per_tok = a + b*N ===")
print(String(format: "intercept a = %.9f s/tok  (N=1 predicted %.9f)", intercept, intercept + slopeS))
print(String(format: "slope     b = %.9f s/tok/copy = %.4f ms/copy", slopeS, slopeMs))
print(String(format: "R^2         = %.6f   (linearity / no-CSE check)", r2))

// pairwise slopes: linearity detail
print("\npairwise slopes (ms/copy):")
for i in 0..<arms.count {
    for j in (i + 1)..<arms.count {
        let s = (arms[j].decode - arms[i].decode) / (arms[j].n - arms[i].n) * 1000.0
        print(String(format: "  N=%.0f -> N=%.0f : %.4f", arms[i].n, arms[j].n, s))
    }
}

// Admissibility: a genuinely DRAM-served copy cannot be faster than the
// analytic lower bound at the measured host ceiling.
let lowerBoundMs = routedGateUpBytesPerStep / (m4CeilingGBs * 1e9) * 1000.0
print("\n=== admissibility (cache-warm hazard) ===")
print(String(format: "analytic DRAM lower bound per copy = %.4f ms  (%.1f MB / %.1f GB/s)",
             lowerBoundMs, routedGateUpBytesPerStep / 1e6, m4CeilingGBs))
if slopeMs >= lowerBoundMs {
    print("  slope >= lower bound  => duplicates are DRAM-served; instrument ADMISSIBLE")
} else {
    let ratio = slopeMs / lowerBoundMs
    print(String(format: "  slope is %.1f%% of the lower bound => duplicates partly cache-served;", ratio * 100))
    print("  instrument INADMISSIBLE for declaring the >=92% STOP")
}

// Achieved bandwidth, with the dispatch-overhead correction bracket.
let ovLoMs = dispatchesPerCopy * dispatchOverheadLoUs / 1000.0
let ovHiMs = dispatchesPerCopy * dispatchOverheadHiUs / 1000.0
func gbs(_ ms: Double) -> Double { routedGateUpBytesPerStep / (ms / 1000.0) / 1e9 }
let achievedRaw = gbs(slopeMs)
let achievedLo = gbs(max(slopeMs - ovLoMs, 1e-9))   // small overhead removed -> slightly faster
let achievedHi = gbs(max(slopeMs - ovHiMs, 1e-9))   // large overhead removed -> faster still

print("\n=== achieved routed gate/up bandwidth (M4 Pro) ===")
print(String(format: "uncorrected           : %.1f GB/s  = %.1f%% of %.1f GB/s ceiling",
             achievedRaw, achievedRaw / m4CeilingGBs * 100, m4CeilingGBs))
print(String(format: "minus dispatch %.3f ms: %.1f GB/s  = %.1f%%", ovLoMs, achievedLo, achievedLo / m4CeilingGBs * 100))
print(String(format: "minus dispatch %.3f ms: %.1f GB/s  = %.1f%%", ovHiMs, achievedHi, achievedHi / m4CeilingGBs * 100))

let pct = achievedRaw / m4CeilingGBs * 100
print("\n=== Step 0 gate ===")
if pct >= 92 {
    print(String(format: "achieved %.1f%% >= 92%%  => HARD STOP (if instrument admissible)", pct))
} else if pct <= 88 {
    print(String(format: "achieved %.1f%% <= 88%%  => PROCEED to Step 1/2", pct))
} else {
    print(String(format: "achieved %.1f%% in (88,92)%% => PROCEED with widened prior", pct))
}
