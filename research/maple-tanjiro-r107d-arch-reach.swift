// Host-reachability probe for the R107-D decode fused-attention assignment.
//
// Replicates, on the live Metal device, the exact three quantities that the
// scored MLX runtime uses to choose between a plain kernel and an `_nax`
// twin:
//
//   Vendor/mlx-swift/.../backend/metal/device.cpp:557-572  arch_ / arch_gen_
//   Vendor/mlx-swift/.../backend/metal/device.cpp:913-931  is_nax_available()
//
// `arch_` is `device_->architecture()->name()` unless MLX_METAL_GPU_ARCH is
// set, which is the same string Swift's `MTLDevice.architecture.name` returns.
//
// Build/run:
//   xcrun swiftc -O research/maple-tanjiro-r107d-arch-reach.swift -o /tmp/r107d-reach && /tmp/r107d-reach

import Foundation
import Metal

guard let device = MTLCreateSystemDefaultDevice() else {
    FileHandle.standardError.write("no Metal device\n".data(using: .utf8)!)
    exit(1)
}

let envArch = ProcessInfo.processInfo.environment["MLX_METAL_GPU_ARCH"] ?? ""
let arch = envArch.isEmpty ? device.architecture.name : envArch

// device.cpp:565-572 verbatim: tens/ones are the 3rd- and 2nd-from-last chars.
var agTens = 0
var agOnes = 0
if arch.count >= 3 {
    let chars = Array(arch.utf8)
    agTens = Int(chars[chars.count - 3]) - Int(UInt8(ascii: "0"))
    agOnes = Int(chars[chars.count - 2]) - Int(UInt8(ascii: "0"))
    agTens = (agTens < 10 && agTens >= 0) ? agTens : 0
    agOnes = (agOnes < 10 && agOnes >= 0) ? agOnes : 0
}
let archGen = agTens * 10 + agOnes
let backChar = arch.last.map(String.init) ?? "?"

// device.cpp:918-927 verbatim.
var canUseNax = false
if #available(macOS 26.2, *) { canUseNax = true }
let osAllowsNax = canUseNax
let genThreshold = (backChar == "p") ? 18 : 17
canUseNax = canUseNax && (archGen >= genThreshold)

print("device_name              = \(device.name)")
print("os_version               = \(ProcessInfo.processInfo.operatingSystemVersionString)")
print("MLX_METAL_GPU_ARCH       = \(envArch.isEmpty ? "<unset>" : envArch)")
print("get_architecture()       = \(arch)")
print("get_architecture().back() = \(backChar)")
print("get_architecture_gen()   = \(archGen)")
print("os_allows_nax (>=26.2)   = \(osAllowsNax)")
print("gen_threshold            = \(genThreshold)")
print("nax_available            = \(canUseNax)")
print("max_threads_per_tg       = \(device.maxThreadsPerThreadgroup)")
print("recommended_wset_MB      = \(device.recommendedMaxWorkingSetSize / (1024 * 1024))")
