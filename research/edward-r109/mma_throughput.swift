// R109-D stage 0d driver for research/edward-r109/mma_throughput.metal.
//
// Reports peak MAC/s for scalar FMA chains and for chained 8x8x8 simdgroup MMAs
// so the M=2 decode QK tile's 4x MAC padding can be priced against the reduction
// it would remove. Build:
//   xcrun swiftc -O research/edward-r109/mma_throughput.swift -o /tmp/mmathru
import Foundation
import Metal

let metalPath = CommandLine.arguments.count > 1
    ? CommandLine.arguments[1]
    : "research/edward-r109/mma_throughput.metal"
let iterations = CommandLine.arguments.count > 2 ? Int(CommandLine.arguments[2])! : 12

guard let device = MTLCreateSystemDefaultDevice(),
      let queue = device.makeCommandQueue() else { fatalError("no Metal device") }
let source = try String(contentsOfFile: metalPath, encoding: .utf8)
let library = try device.makeLibrary(source: source, options: nil)

let threadgroup = 256
let out = device.makeBuffer(length: 1 << 26, options: .storageModeShared)!
let tripBuf = device.makeBuffer(length: 4, options: .storageModeShared)!

print("device=\(device.name) iterations=\(iterations) threadgroup=\(threadgroup)")
print("arm            threads  loops     gpu_ms      GMAC/s   trips")

func run(_ name: String, threads: Int, loops: UInt32, macsPerLoopPerThread: Double) throws {
    let pipe = try device.makeComputePipelineState(
        function: library.makeFunction(name: name)!)
    var best = Double.greatestFiniteMagnitude
    var trips: UInt32 = 0
    for _ in 0..<iterations {
        tripBuf.contents().bindMemory(to: UInt32.self, capacity: 1)[0] = 0
        let cb = queue.makeCommandBuffer()!
        let enc = cb.makeComputeCommandEncoder()!
        enc.setComputePipelineState(pipe)
        enc.setBuffer(out, offset: 0, index: 0)
        enc.setBuffer(tripBuf, offset: 0, index: 1)
        var n = loops
        enc.setBytes(&n, length: 4, index: 2)
        enc.dispatchThreads(MTLSize(width: threads, height: 1, depth: 1),
                            threadsPerThreadgroup: MTLSize(width: threadgroup, height: 1, depth: 1))
        enc.endEncoding()
        cb.commit()
        cb.waitUntilCompleted()
        best = min(best, cb.gpuEndTime - cb.gpuStartTime)
        trips = tripBuf.contents().bindMemory(to: UInt32.self, capacity: 1)[0]
    }
    let macs = Double(threads) * Double(loops) * macsPerLoopPerThread
    print(String(format: "%-14@ %7d %6d  %9.3f  %10.1f   %u %@",
                 name as NSString, threads, Int(loops), best * 1e3,
                 macs / best / 1e9, trips,
                 (trips == loops ? "ok" : "TRIP-MISMATCH") as NSString))
}

let threadCounts = [1 << 16, 1 << 18, 1 << 20]
for threads in threadCounts {
    for n in [1, 4, 8] {
        try run("fma_f32_x\(n)", threads: threads, loops: 20000,
                macsPerLoopPerThread: Double(n))
    }
    // One 8x8x8 MMA per simdgroup = 512 MACs spread over 32 lanes = 16 per lane.
    for n in [1, 2, 4] {
        try run("mma_bf16_x\(n)", threads: threads, loops: 20000,
                macsPerLoopPerThread: Double(16 * n))
    }
}
