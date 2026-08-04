# PR #7 interim findings — decode roofline and resident footprint

Student `maple-nezuko`. `BASE_SHA=768bb9d4adfc2baac7d74c0008afc92d010329da`.
Host: Apple M4 Pro, 48 GiB (51539607552 B), macOS 26.5.2 (25F84), Swift 6.3.3.

Typed Senpai transitions cannot post a PR comment from a student, so interim
results land here as commits on the assignment branch.

## Interim 1 — measured host streaming ceiling: 260 GB/s read

Standalone Metal probe with no MLX in the path
(`research/host_bandwidth_ceiling.swift`): grid-stride `float4` streaming
kernels over 3 GiB shared buffers, best of 15 iterations, timed with
`MTLCommandBuffer.gpuStartTime/gpuEndTime` and wall clock (they agree within
1.5%).

| pattern | bytes moved | best GPU time | achieved |
| --- | ---: | ---: | ---: |
| read (`float4` load + accumulate) | 3.22 GB | 12.378 ms | **260.2 GB/s** |
| copy (read + write) | 6.44 GB | 28.605 ms | 225.2 GB/s |
| read-modify-write | 6.44 GB | 26.294 ms | 245.0 GB/s |

Read bandwidth rises monotonically with thread count (251.9 / 256.6 / 258.5 /
260.2 GB/s at 2^16 / 2^18 / 2^20 / 2^22 threads), so 260 GB/s is a saturated
ceiling rather than an occupancy artifact. Decode is read-dominated, so
**260 GB/s (95% of the 273 GB/s nameplate) is the correct ceiling for this
host**.

Restating the advisor's prediction against the measured ceiling:

| | at 1.65 GB/token | at 1.9 GB/token |
| --- | ---: | ---: |
| M4 Pro DRAM floor (260 GB/s) | 6.35 ms/token | 7.31 ms/token |
| 55-65% of ceiling | 9.8-11.5 ms/token | 11.2-13.3 ms/token |

### Incidental: this host's GPU working-set recommendation is 37.4 GiB

`MTLDevice.recommendedMaxWorkingSetSize` = 37.4 GiB of 48 GiB physical. The
shape-derived resident estimate for the runtime is 35-38 GB, i.e. at or above
the recommended working set — the regime where Metal begins making residency
decisions for us. That is a concrete mechanism by which a 48 GiB M4 Pro can
distort every arm's timing, independent of the M5 transfer question.

### Incidental: the wired-residency dose never engages on our student hosts

`wireResidentWeightsIfEnabled()`
(`Sources/MLXFastModel/LagunaRuntimeWeights.swift:548-550`) hard-guards on
`ProcessInfo.processInfo.physicalMemory >= 96 GiB`. On any 48 GiB student host
the shipped wired dose is inert, so an M4 footprint measurement is necessarily
the no-wiring regime; the interaction with `capacity = 1.0 x live bytes +
64 MiB` can only be evaluated on the official M5.
