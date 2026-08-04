import Foundation
import Metal

// Measures how many threadgroups of a given shape are CONCURRENTLY RESIDENT on
// this GPU, as a function of threads per threadgroup and threadgroup memory.
//
// Why a synthetic kernel: on a real kernel a second co-resident threadgroup and
// a second serialised wave look the same, because the work is throughput bound
// either way. Here the timed work is one long dependent device-memory pointer
// chase executed by lane 0 only. That is latency bound and costs almost no
// bandwidth or ALU, so co-resident threadgroups overlap for free and the elapsed
// time stays flat until the hardware refuses to admit another threadgroup. The
// threadgroup still declares its full thread count and threadgroup memory, so
// both of those resources are reserved exactly as the real kernel reserves them.
//
// Read the result off the plateau: the largest group count g whose single
// dispatch still costs one chase is the number of resident threadgroups on the
// whole device. Divide by the core count for threadgroups per core.

func metalSource(scratchFloats: Int) -> String {
    let scratchDecl = scratchFloats > 0
        ? """
              threadgroup float scratch[\(scratchFloats)];
              scratch[tid % \(scratchFloats)] = float(tid) + float(seed);
              threadgroup_barrier(mem_flags::mem_threadgroup);
              float guard = scratch[seed % \(scratchFloats)];
          """
        : "    float guard = float(seed);"
    return """
        #include <metal_stdlib>
        using namespace metal;

        kernel void probe(
            device const uint* chase [[buffer(0)]],
            device uint* out [[buffer(1)]],
            constant uint& steps [[buffer(2)]],
            constant uint& mask [[buffer(3)]],
            uint tid [[thread_position_in_threadgroup]],
            uint gid [[threadgroup_position_in_grid]])
        {
            uint seed = chase[(gid * 2654435761u) & mask];
        \(scratchDecl)
            if (tid == 0) {
                uint idx = seed & mask;
                for (uint i = 0; i < steps; ++i) {
                    idx = chase[idx];
                }
                out[gid] = idx + uint(guard);
            }
        }
        """
}

struct Shape {
    let threads: Int
    let scratchBytes: Int
    let pipeline: MTLComputePipelineState
    var label: String { "\(threads)thr/\(scratchBytes)B" }
}

let device = MTLCreateSystemDefaultDevice()!
let queue = device.makeCommandQueue()!

// Pointer-chase ring large enough that every hop misses the caches.
let chaseCount = 1 << 22  // 4 Mi entries = 16 MB
let mask = UInt32(chaseCount - 1)
var chase = [UInt32](repeating: 0, count: chaseCount)
var rng: UInt64 = 0x9E37_79B9_7F4A_7C15
func next() -> UInt64 {
    rng ^= rng << 13
    rng ^= rng >> 7
    rng ^= rng << 17
    return rng
}
// A single random cycle over all entries, so no hop is predictable.
var order = Array(0..<chaseCount)
for i in stride(from: chaseCount - 1, to: 0, by: -1) {
    let j = Int(next() % UInt64(i + 1))
    order.swapAt(i, j)
}
for i in 0..<chaseCount {
    chase[order[i]] = UInt32(order[(i + 1) % chaseCount])
}
let chaseBuffer = device.makeBuffer(
    bytes: &chase, length: chaseCount * 4, options: .storageModeShared)!

var args = Array(CommandLine.arguments.dropFirst())
var steps = 512
var maxGroups = 96
var cores = 20
var specs: [String] = []
var argIndex = 0
while argIndex < args.count {
    switch args[argIndex] {
    case "--steps": steps = Int(args[argIndex + 1])!; argIndex += 2
    case "--max-groups": maxGroups = Int(args[argIndex + 1])!; argIndex += 2
    case "--cores": cores = Int(args[argIndex + 1])!; argIndex += 2
    default: specs.append(args[argIndex]); argIndex += 1
    }
}
if specs.isEmpty {
    // Default sweep: the shapes our decode kernels actually use, plus the shapes
    // that would be needed to double residency.
    specs = [
        "1024:17920", "1024:16384", "1024:16640", "1024:9728", "1024:0",
        "512:4228", "512:0", "256:0",
    ]
}

let outBuffer = device.makeBuffer(
    length: max(maxGroups, 1) * 4, options: .storageModeShared)!
var stepsValue = UInt32(steps)
var maskValue = mask
let stepsBuffer = device.makeBuffer(
    bytes: &stepsValue, length: 4, options: .storageModeShared)!
let maskBuffer = device.makeBuffer(
    bytes: &maskValue, length: 4, options: .storageModeShared)!

func makeShape(_ spec: String) -> Shape {
    let parts = spec.split(separator: ":").map { Int($0)! }
    let threads = parts[0]
    let bytes = parts[1]
    let options = MTLCompileOptions()
    options.fastMathEnabled = false
    let library = try! device.makeLibrary(
        source: metalSource(scratchFloats: bytes / 4), options: options)
    let function = library.makeFunction(name: "probe")!
    let pipeline = try! device.makeComputePipelineState(function: function)
    return Shape(threads: threads, scratchBytes: bytes, pipeline: pipeline)
}

// GPU-side elapsed time of one isolated dispatch, minimum over `repeats`.
func time(_ shape: Shape, groups: Int, repeats: Int) -> Double {
    var best = Double.greatestFiniteMagnitude
    for _ in 0..<repeats {
        let buffer = queue.makeCommandBuffer()!
        let encoder = buffer.makeComputeCommandEncoder()!
        encoder.setComputePipelineState(shape.pipeline)
        encoder.setBuffer(chaseBuffer, offset: 0, index: 0)
        encoder.setBuffer(outBuffer, offset: 0, index: 1)
        encoder.setBuffer(stepsBuffer, offset: 0, index: 2)
        encoder.setBuffer(maskBuffer, offset: 0, index: 3)
        encoder.dispatchThreadgroups(
            MTLSize(width: groups, height: 1, depth: 1),
            threadsPerThreadgroup: MTLSize(width: shape.threads, height: 1, depth: 1))
        encoder.endEncoding()
        buffer.commit()
        buffer.waitUntilCompleted()
        best = min(best, buffer.gpuEndTime - buffer.gpuStartTime)
    }
    return best
}

print("device: \(device.name)")
print(
    "threadgroup memory limit \(device.maxThreadgroupMemoryLength) B, "
        + "max threads/tg \(device.maxThreadsPerThreadgroup.width), "
        + "assumed cores \(cores)")
print(
    "chase: \(chaseCount) entries (\(chaseCount * 4 / 1_000_000) MB), "
        + "\(steps) dependent hops")
print("")

for spec in specs {
    let shape = makeShape(spec)
    guard shape.threads <= shape.pipeline.maxTotalThreadsPerThreadgroup else {
        print(
            "\(shape.label): SKIPPED, pipeline caps at "
                + "\(shape.pipeline.maxTotalThreadsPerThreadgroup) threads")
        continue
    }
    _ = time(shape, groups: 1, repeats: 3)
    var seconds = [Int: Double]()
    // Alternate direction so monotone host drift cannot fake a step.
    for round in 0..<3 {
        let order = round % 2 == 0
            ? Array(1...maxGroups) : Array((1...maxGroups).reversed())
        for g in order {
            let value = time(shape, groups: g, repeats: 2)
            seconds[g] = min(seconds[g] ?? .greatestFiniteMagnitude, value)
        }
    }
    let unit = seconds[1]!
    // Plateau = largest g still within 25% of the single-threadgroup cost.
    var plateau = 1
    for g in 1...maxGroups where seconds[g]! < unit * 1.25 { plateau = g }
    print(
        "\(shape.label): static tg memory "
            + "\(shape.pipeline.staticThreadgroupMemoryLength) B, "
            + String(format: "1 TG = %.2f us", unit * 1e6))
    var line = ""
    for g in 1...maxGroups {
        line += String(format: "  %d:%.2f", g, seconds[g]! * 1e6)
        if g % 8 == 0 { print(line); line = "" }
    }
    if !line.isEmpty { print(line) }
    print(String(
        format: "  => resident threadgroups %d, per core %.2f, threads/core %.0f\n",
        plateau, Double(plateau) / Double(cores),
        Double(plateau * shape.threads) / Double(cores)))
}
