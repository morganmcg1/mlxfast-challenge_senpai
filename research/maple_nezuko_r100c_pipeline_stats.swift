// R100-C Step 1 (N-C): per-arm pipeline occupancy for the router GEMV.
// `maxTotalThreadsPerThreadgroup` is a direct function of the backend's
// register allocation, so a drop across arms is the codegen tax N-C predicts.
// Creates pipelines only; runs no kernel and takes no timing.
import Foundation
import Metal

let device = MTLCreateSystemDefaultDevice()!
print("device: \(device.name)")

for tag in ["pf0", "pf1", "pf1c"] {
    let path = "research/msl/r100c_rpg8_\(tag).metallib"
    guard let lib = try? device.makeLibrary(URL: URL(fileURLWithPath: path)),
          let name = lib.functionNames.first,
          let fn = lib.makeFunction(name: name),
          let pso = try? device.makeComputePipelineState(function: fn)
    else {
        print("\(tag): FAILED to build pipeline from \(path)")
        continue
    }
    let launchable = pso.maxTotalThreadsPerThreadgroup >= 512 ? "yes" : "NO"
    print("""
        \(tag)  maxTotalThreadsPerThreadgroup=\(pso.maxTotalThreadsPerThreadgroup) \
        threadExecutionWidth=\(pso.threadExecutionWidth) \
        staticThreadgroupMemory=\(pso.staticThreadgroupMemoryLength) \
        launchable@512=\(launchable)
        """)
}
