# Relocated commentary — `LagunaRuntimeWeights.swift`

Measurement narrative and design history moved verbatim out of `Sources/MLXFastModel/LagunaRuntimeWeights.swift`
to free bytes on the capped editable submission surface. Line numbers refer to
the file as it stood at base `e1d070f2`. Nothing here is compiled or
submitted, and the code is unchanged (see
`research/frieren_comment_strip_check.sh`).

## `wired residency measurement history`

_relocated from lines 420-431 at base e1d070f2_

Zero-headroom wired residency (notes/47 §4e follow-up, session
H6): the vendored MLX Device attaches a `MTLResidencySet` to every
command queue, but `ResidencySet::capacity_` defaults to 0, so the
set stays empty and the driver re-establishes residency for the
whole ~21.6 GB RAM-resident text tower on every command buffer
(notes/47 §4d-4e: driver-busy tracks the prefill span, 9-15 ms
kernelStart gaps). notes/47 §6-§7 measured the naive fix -- a
32 GiB wired limit -- removing that driver work (167.1 -> 9.9 ms)
but regressing under the scored seatbelt, because ~10 GiB of spare
capacity made `ResidencySet::insert`/`erase` issue a Metal
`commit()` for every scored-window allocation and eviction
(resident.cpp:28-50).

## `wired residency host headroom`

_relocated from lines 451-459 at base e1d070f2_

(fraction of live bytes + flat slack; the slack also covers the
MTLBuffer allocatedSize page-rounding inflation over
`Memory.activeMemory` at full wire). A >=96 GiB physical-memory
guard keeps sub-128GB machines on stock behavior. Target machine
(local and ranked) is an M5 Max with 128 GB unified memory:
recommendedMaxWorkingSetSize ~= 115 GB, so even a full ~31 GB
wire is far from the OS cap that `metal::set_wired_limit`
fail-closes on (allocator.cpp:305-312). See the dose table on
`wireResidentWeightsIfEnabled`.

## `greedy argmax PSO miss trace`

_relocated from lines 503-507 at base e1d070f2_

INSIDE the measured window: a timestamped PSO-miss log showed the
compile firing ~0.23 s into the scored prefill request and again in
the decode seed, matching a recurring ~17 ms MTLCompilerService
interval inside both timed phases in Metal System Trace. Replicating
the same ops here moves that one-time compile to untimed init.

## `wired residency dose curve`

_relocated from lines 526-537 at base e1d070f2_

discipline. Measured loaded-local (cool-gated Latin squares, all vs
unwired control, correctness green every sample):
  42 MiB -> -4.2% prefill | 350 MiB -> -8.2% | 0.10x -> -11.2%
  0.20x -> -17.2% | 0.35x -> -20.8% | 1.0x -> -28.3% prefill,
  -4.2% decode composite (seed-prefill share; steady step null).
Chunk 1 (42 MiB) ranked +1.24% score (promoted 1.38531), validating
the ~1:1 loaded-local -> ranked transfer. This configuration ships
the WHOLE curve in one submission per operator instruction; the
documented acceptance band (prefill speedup vs calibration in
[0.952, 1.053]) is expected to reject gains this large in one step
-- if the ranked run fails with acceptance_band_failed, revert to
band-sized dose increments (the curve above is the roadmap).

## `group16 scale pair census`

_relocated from lines 1001-1004 at base e1d070f2_

same byte. Census over all 39 sparse layers (234 tensors, 985,300,992
pairs): 985,300,824 pairs are byte-identical and all 168 exceptions are the
very first pair of a tensor, the one span the quantizer's first simdgroup
writes twice.
