import Metal

let d = MTLCreateSystemDefaultDevice()!
print("name=\(d.name)")
if #available(macOS 14.0, *) {
    print("architecture=\(d.architecture.name)")
}
print("maxBufferLength=\(d.maxBufferLength)")
print("recommendedMaxWorkingSetSize=\(d.recommendedMaxWorkingSetSize)")
