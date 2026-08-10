// Research-only host probe (not part of the submission surface).
//
// Rule 99.3 reachability facts for R107-F. Replicates MLX's own derivation so
// the answer is measured on this device rather than inferred:
//   * `Device::Device()` parses the architecture gen from the two characters
//     before the trailing family letter (device.cpp:564-572).
//   * `is_nax_available()` requires macOS >= 26.2 AND
//     gen >= (arch.back() == 'p' ? 18 : 17)   (device.cpp:913-931).
//
// Build and run:
//   xcrun swiftc -O research/maple_frieren_r107f_stage0_host.swift \
//     -o /tmp/r107f_stage0_host && /tmp/r107f_stage0_host

import Foundation
import Metal

guard let device = MTLCreateSystemDefaultDevice() else {
    FileHandle.standardError.write("no Metal device\n".data(using: .utf8)!)
    exit(1)
}

let archName = device.architecture.name
let backChar = archName.last.map(String.init) ?? ""

// device.cpp:564-572
var agTens = 0
var agOnes = 0
let chars = Array(archName.utf8)
if chars.count >= 3 {
    let t = Int(chars[chars.count - 3]) - 48
    let o = Int(chars[chars.count - 2]) - 48
    agTens = (t >= 0 && t < 10) ? t : 0
    agOnes = (o >= 0 && o < 10) ? o : 0
}
let archGen = agTens * 10 + agOnes

let osVersion = ProcessInfo.processInfo.operatingSystemVersion
let osString = "\(osVersion.majorVersion).\(osVersion.minorVersion).\(osVersion.patchVersion)"
let osClause = (osVersion.majorVersion, osVersion.minorVersion) >= (26, 2)
let genFloor = backChar == "p" ? 18 : 17
let naxAvailable = osClause && archGen >= genFloor

// device.cpp:573-595 command-buffer commit thresholds
let (maxOps, maxMB): (Int, Int)
switch backChar {
case "p": (maxOps, maxMB) = (20, 40)
case "g": (maxOps, maxMB) = (40, 40)
case "s": (maxOps, maxMB) = (50, 50)
case "d": (maxOps, maxMB) = (50, 50)
default: (maxOps, maxMB) = (40, 40)
}

func jsonEscape(_ s: String) -> String {
    s.replacingOccurrences(of: "\\", with: "\\\\")
        .replacingOccurrences(of: "\"", with: "\\\"")
}

var fields: [String] = []
func emit(_ key: String, _ value: String, quoted: Bool = true) {
    print("\(key)=\(value)")
    fields.append("  \"\(key)\": \(quoted ? "\"\(jsonEscape(value))\"" : value)")
}

emit("device_name", device.name)
emit("architecture_name", archName)
emit("architecture_back_char", backChar)
emit("architecture_gen", "\(archGen)", quoted: false)
emit("os_version", osString)
emit("os_clause_macos_26_2", "\(osClause)", quoted: false)
emit("nax_gen_floor", "\(genFloor)", quoted: false)
emit("nax_available", "\(naxAvailable)", quoted: false)
emit("max_ops_per_buffer", "\(maxOps)", quoted: false)
emit("max_mb_per_buffer", "\(maxMB)", quoted: false)
emit("max_threads_per_threadgroup_x", "\(device.maxThreadsPerThreadgroup.width)", quoted: false)
emit("max_threadgroup_memory_length", "\(device.maxThreadgroupMemoryLength)", quoted: false)
emit("max_buffer_length", "\(device.maxBufferLength)", quoted: false)
emit("recommended_max_working_set_size", "\(device.recommendedMaxWorkingSetSize)", quoted: false)
emit("has_unified_memory", "\(device.hasUnifiedMemory)", quoted: false)
emit("physical_memory_bytes", "\(ProcessInfo.processInfo.physicalMemory)", quoted: false)

if let out = ProcessInfo.processInfo.environment["R107F_JSON_OUT"] {
    let body = "{\n" + fields.joined(separator: ",\n") + "\n}\n"
    try? body.write(toFile: out, atomically: true, encoding: .utf8)
}
