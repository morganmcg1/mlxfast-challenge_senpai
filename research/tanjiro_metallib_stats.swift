// Pipeline-stat reader for offline-built metallibs.
//
// Part of the `_nax` safety rig. `research/nax_msl_compile_check.sh EMIT_LIB=1`
// produces a metallib containing real instantiations of the expert gather-QMM
// kernel; this tool turns each function in that library into an
// MTLComputePipelineState and reports the two numbers that decide whether a
// tile-geometry change is affordable:
//
//   staticThreadgroupMemoryLength  - threadgroup bytes the compiler reserved
//   maxTotalThreadsPerThreadgroup  - register-pressure proxy. The driver caps
//                                    this at 32768/registers_per_thread, so a
//                                    drop from 1024 is direct evidence that a
//                                    change raised per-thread register demand.
//
// It also disassembles nothing and runs nothing, so it is safe on any host:
// M4 never *selects* `_nax`, but it can still compile and introspect it.
//
// Usage: swift research/tanjiro_metallib_stats.swift LIB.metallib [LIB2 ...]
//        FILTER=<substring>  only report functions whose name contains this

import Foundation
import Metal

struct Row {
    let lib: String
    let fn: String
    let tgMem: Int
    let maxThreads: Int
    let width: Int
}

guard let device = MTLCreateSystemDefaultDevice() else {
    FileHandle.standardError.write(Data("no Metal device\n".utf8))
    exit(1)
}

let filter = ProcessInfo.processInfo.environment["FILTER"] ?? ""
let paths = Array(CommandLine.arguments.dropFirst())
guard !paths.isEmpty else {
    print("usage: swift research/tanjiro_metallib_stats.swift LIB.metallib ...")
    exit(2)
}

print("device: \(device.name)")
print("  maxThreadgroupMemoryLength = \(device.maxThreadgroupMemoryLength) B")
print("")

var rows: [Row] = []
var failed = 0

for path in paths {
    let url = URL(fileURLWithPath: path)
    let lib: MTLLibrary
    do {
        lib = try device.makeLibrary(URL: url)
    } catch {
        print("FAIL  \(path): makeLibrary: \(error)")
        failed += 1
        continue
    }
    for name in lib.functionNames.sorted() {
        if !filter.isEmpty && !name.contains(filter) { continue }
        guard let fn = lib.makeFunction(name: name) else {
            print("FAIL  \(path)  \(name): makeFunction returned nil")
            failed += 1
            continue
        }
        do {
            let pso = try device.makeComputePipelineState(function: fn)
            rows.append(Row(lib: url.lastPathComponent,
                            fn: name,
                            tgMem: pso.staticThreadgroupMemoryLength,
                            maxThreads: pso.maxTotalThreadsPerThreadgroup,
                            width: pso.threadExecutionWidth))
        } catch {
            print("FAIL  \(path)  \(name): makeComputePipelineState: \(error)")
            failed += 1
        }
    }
}

if rows.isEmpty {
    print("no pipelines built (filter=\"\(filter)\")")
    exit(failed == 0 ? 3 : 1)
}

let w = rows.map { $0.fn.count }.max() ?? 8
print(String(format: "%-\(w)@  %9@  %11@  %5@  %9@",
             "function" as NSString, "tgMem_B" as NSString,
             "maxThreads" as NSString, "width" as NSString,
             "regs_bound" as NSString))
var anySaturated = false
for r in rows.sorted(by: { $0.fn < $1.fn }) {
    // maxTotalThreadsPerThreadgroup is floor(register_file / regs_per_thread)
    // rounded to the execution width, so it inverts to an UPPER BOUND on the
    // per-thread register count -- never a point estimate. At the 1024-thread
    // Metal API ceiling the inversion saturates and proves only "<= 32".
    let saturated = r.maxThreads >= 1024
    anySaturated = anySaturated || saturated
    let bound = r.maxThreads > 0 ? 32768 / r.maxThreads : 0
    print(String(format: "%-\(w)@  %9d  %11d  %5d  %9@",
                 r.fn as NSString, r.tgMem, r.maxThreads, r.width,
                 ("<=\(bound)" + (saturated ? "*" : "")) as NSString))
}
if anySaturated {
    print("")
    print("* maxThreads is at the 1024 Metal API ceiling, so the register "
          + "bound is saturated:")
    print("  it cannot distinguish 8 from 32 registers/thread and cannot "
          + "resolve the 104/128/160")
    print("  half-register occupancy cliffs. Threadgroup-memory residency IS "
          + "settled by tgMem_B.")
    print("  Register-driven residency on the ranked GPU generation is NOT "
          + "establishable from this")
    print("  host's offline pipeline build; treat it as an open confound.")
}

exit(failed == 0 ? 0 : 1)
