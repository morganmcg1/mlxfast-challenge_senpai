// R107-F Stage 1 probe P0: per-arm pipeline occupancy for the routed/shared
// NVFP4 down-residual kernel at outputs_per_simd in {4, 8, 16}.
//
// `maxTotalThreadsPerThreadgroup` is a direct function of the backend's
// register allocation for this exact function, reported by the live driver.
// It is the only occupancy observable available on this platform (object
// metadata carries no register counts, and there is no AGX disassembler).
//
// Arm N requests 9 * 32 = 288 threads per threadgroup. If maxThreads for an
// arm falls below 288 the arm is not dispatchable at that geometry and the
// H-T2D-AMORT' lever is dead before any timing run.
//
// Creates pipelines only; runs no kernel and takes no timing.
import Foundation
import Metal

let device = MTLCreateSystemDefaultDevice()!
print("device: \(device.name)")

let requestedThreads = 288
let args = Array(CommandLine.arguments.dropFirst())
guard !args.isEmpty else {
    FileHandle.standardError.write(
        Data("usage: opsi_pipeline_stats LABEL=PATH.metallib ...\n".utf8))
    exit(2)
}

var rows: [[String: Any]] = []
for arg in args {
    let parts = arg.split(separator: "=", maxSplits: 1)
    guard parts.count == 2 else {
        print("SKIP malformed arg \(arg)")
        continue
    }
    let label = String(parts[0])
    let path = String(parts[1])
    guard let lib = try? device.makeLibrary(URL: URL(fileURLWithPath: path)),
        let name = lib.functionNames.first,
        let fn = lib.makeFunction(name: name)
    else {
        print("\(label): FAILED to load library/function from \(path)")
        continue
    }
    let descriptor = MTLComputePipelineDescriptor()
    descriptor.computeFunction = fn
    var reflection: MTLComputePipelineReflection?
    guard
        let pso = try? device.makeComputePipelineState(
            descriptor: descriptor,
            options: [.bindingInfo],
            reflection: &reflection)
    else {
        print("\(label): FAILED to build pipeline")
        continue
    }
    let maxThreads = pso.maxTotalThreadsPerThreadgroup
    print("""
        \(label) fn=\(name) \
        maxTotalThreadsPerThreadgroup=\(maxThreads) \
        threadExecutionWidth=\(pso.threadExecutionWidth) \
        staticThreadgroupMemory=\(pso.staticThreadgroupMemoryLength) \
        dispatchable@\(requestedThreads)=\(maxThreads >= requestedThreads ? "yes" : "NO")
        """)
    rows.append([
        "label": label,
        "function": name,
        "max_total_threads_per_threadgroup": maxThreads,
        "thread_execution_width": pso.threadExecutionWidth,
        "static_threadgroup_memory_length": pso.staticThreadgroupMemoryLength,
        "requested_threads": requestedThreads,
        "dispatchable": maxThreads >= requestedThreads,
        "bindings": reflection?.bindings.count ?? -1,
    ])
}

if let out = ProcessInfo.processInfo.environment["R107F_JSON_OUT"] {
    let payload: [String: Any] = ["device": device.name, "arms": rows]
    let data = try JSONSerialization.data(
        withJSONObject: payload, options: [.prettyPrinted, .sortedKeys])
    try data.write(to: URL(fileURLWithPath: out))
    print("wrote \(out)")
}
