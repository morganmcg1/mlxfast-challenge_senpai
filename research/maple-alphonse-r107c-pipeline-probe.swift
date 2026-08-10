// Occupancy probe for the R107-C expert gather-GEMM BN ledger.
//
// Compiles one reconstructed `fp_gather_qmm_rhs_expert_nax` JIT source per BN
// and reports the pipeline facts Metal exposes without launching the kernel:
// `maxTotalThreadsPerThreadgroup` (a register-pressure ceiling on Apple GPUs)
// and `staticThreadgroupMemoryLength`. No timing is measured or claimed.
import Foundation
import Metal

guard let device = MTLCreateSystemDefaultDevice() else {
    FileHandle.standardError.write(Data("no Metal device\n".utf8))
    exit(2)
}
print("device: \(device.name)")
print("maxThreadgroupMemoryLength: \(device.maxThreadgroupMemoryLength)")
print("maxThreadsPerThreadgroup: \(device.maxThreadsPerThreadgroup)")

let options = MTLCompileOptions()
options.mathMode = .safe
options.languageVersion = .version4_0

var failures = 0
for path in CommandLine.arguments.dropFirst() {
    let name = (path as NSString).lastPathComponent
    guard let source = try? String(contentsOfFile: path, encoding: .utf8) else {
        print("\(name): unreadable")
        failures += 1
        continue
    }
    do {
        let library = try device.makeLibrary(source: source, options: options)
        for fnName in library.functionNames {
            guard let fn = library.makeFunction(name: fnName) else { continue }
            let pipeline = try device.makeComputePipelineState(function: fn)
            print(
                "\(name): fn=\(fnName) "
                    + "maxTotalThreadsPerThreadgroup=\(pipeline.maxTotalThreadsPerThreadgroup) "
                    + "staticThreadgroupMemoryLength=\(pipeline.staticThreadgroupMemoryLength) "
                    + "threadExecutionWidth=\(pipeline.threadExecutionWidth)")
        }
    } catch {
        print("\(name): FAILED \(error)")
        failures += 1
    }
}
exit(failures == 0 ? 0 : 1)
