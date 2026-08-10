# R109-B Stage 0 — the decode router's stage-2 exchange is already cheap

Host: Apple M4 Pro, 20 GPU cores, `applegpu_g16s` (gen 16, no `_nax`), 48 GiB.
Base: `1a6761bf46c282fcabd0577b618f0c1206757e6c`.
Probe: `research/nezuko_r109b_router_probe.swift` (research-only, not on the
submitted surface). It slices the *shipped* header / body / epilogue string
literals straight out of `Sources/MLXFastModel/LagunaRuntimeModel.swift`, so the
baseline arm cannot drift from what the runtime actually compiles.

Reproduce:

```bash
xcrun swiftc -O research/nezuko_r109b_router_probe.swift -o /tmp/nezr109b
/tmp/nezr109b Sources/MLXFastModel/LagunaRuntimeModel.swift pairs=8
```

## Verdict: `N-ROUTER-STAGE2-CHEAP`

The advisor asked for occupancy first, before writing any comparator network.
Two independent measurements say the hypothesised mechanism cannot pay.

### 1. Co-residency is flat in threadgroup memory at this geometry

Rendezvous probe, 256 threads/threadgroup (the shipped router geometry),
binary search on the number of threadgroups that can make joint forward
progress:

| static threadgroup bytes | max co-resident TGs | TG/core | simdgroups/core |
| --- | --- | --- | --- |
| 2048 (shipped) | 240 | 12.00 | 96.0 |
| 1536 (stage-2 scratch removed) | 240 | 12.00 | 96.0 |
| 512 | 240 | 12.00 | 96.0 |
| 64 | 240 | 12.00 | 96.0 |
| 16 | 240 | 12.00 | 96.0 |

The binding occupancy term is 96 simdgroups / 3072 threads per core, not
threadgroup memory. Dropping the two `xchg_*` planes (2048 B -> 1536 B) buys
exactly zero residency. Note also that 64 B is not reachable anyway: the
epilogue reads `original_scores[256]` (1024 B), so the floor for this kernel is
1536 B, not 64 B.

### 2. Decode dispatches `rows = 1`, so K = 1

`LagunaRuntimeModel.swift:9606` dispatches the decode selector with `rows: 1`.
Grid `(256, 1, 1)` / threadGroup `(256, 1, 1)` is **one** threadgroup per layer
per step. A single threadgroup cannot contend for residency with itself, so
even a real occupancy cliff would not be on the scored decode path.

### 3. The whole stage-2 region is worth +0.016% of score

Arm B is a ceiling arm: it surgically deletes only the `xchg_*` stores, the
second `threadgroup_barrier`, and the `partner = lane ^ 32` sequence-64 compare
(the local sort and the strides-16..1 loop stay live through a declarations
shim). It is deliberately *wrong* — it just measures how much time that region
costs at all.

ABBA, 8 pairs, `A/B/C/D/D/C/B/A`, one encoder, serial dispatch,
`gpuEndTime - gpuStartTime` / reps, best-of-3 command buffers:

| rows | A shipped | B stage-2 excised | C null kernel | D bit-exact merge |
| --- | --- | --- | --- | --- |
| 1 (decode) | 2.931 us | 2.843 us | 1.426 us | 3.378 us |
| 512 (prefill) | 16.005 us | 15.571 us | 1.754 us | 14.536 us |

(medians; `rows=1` D/A mean over 8 pairs 1.063 +- 0.070 sem, `rows=512` D/A
mean 0.931 +- 0.016 sem.)

Converting the decode ceiling on the paired baseline (13,890 us/step, 40
layers, M5 sigma 0.15 haircut):

* removing the entire stage-2 exchange: **+0.088 us/call -> +3.5 us/step ->
  +0.0253% of step -> +0.0161% of score**
* the *whole* router dispatch, shipped vs. a null kernel with the same launch
  shape: 2.931 us vs 1.426 us, i.e. the router is **0.4336% of the decode
  step** and just over half of that is bare launch overhead

+0.0161% is an order of magnitude under the assignment's 0.15% go/no-go and
well under the 0.243% two-family n=3 detection floor on `ns`. There is no
version of this hypothesis that reaches the bar, because the ceiling arm that
*breaks correctness* still only finds 0.016%.

## Arm D: the bit-exact merge works, and is still not worth shipping

I built the real thing anyway, because it is the only way to be sure the
ceiling is not an artefact of the excision.

Design (bit-exact, no comparator changes): after barrier #1 the finalists live
in `candidate_*[64]`. Lanes 32-63's post-cross values are never consumed --
only `lane < 8` writes output, and strides <= 16 never leave simdgroup 0. So
simdgroup 0 alone reads `candidate_*[lane]` and `candidate_*[lane + 32]` into
two register pairs, runs the sequence-2..32 bitonic sort on both (predicates
keyed on the *original* lane ids `lane` and `lane | 32`, which is the only
place the two copies differ), performs the sequence-64 compare in registers,
then runs strides 16..1 as before. This removes the second
`threadgroup_barrier` and both `xchg_*` planes (2048 B -> 1536 B) while
executing the identical comparator pairs in the identical order.

Bit-exactness, arm D vs arm A, all 8 slots, both the `uint32` indices and the
raw `float` score bits:

| tieEvery | rows | slots checked | index-equal | score-bit-equal |
| --- | --- | --- | --- | --- |
| 0 (random) | 1 | 8 | yes | yes |
| 0 (random) | 512 | 4096 | yes | yes |
| 2 | 512 | 4096 | yes | yes |
| 4 | 512 | 4096 | yes | yes |
| 8 | 512 | 4096 | yes | yes |
| 64 | 512 | 4096 | yes | yes |

`tieEvery = k` forces logits onto a 4-value lattice (`((e/k)+r) % 7 * 0.25 -
0.75`, zero correction bias) so that hundreds of experts share an ordinal and
the `laguna_router_ordinal_before` "smaller index wins" tie-break is the only
thing that can order them. `tieEvery = 2` puts ~128 experts at each of 4
ordinals; arm D still matches every bit.

But the measured effect has the wrong sign where the score weight is:

* `rows = 1` (decode, 75% weight): D is **slower**, -0.447 us/call ->
  -17.9 us/step -> **-0.082% of score**. With K = 1 there is no residency to
  win, and folding the merge into one simdgroup leaves the other seven idle
  while lengthening the critical path.
* `rows = 512` (prefill, 25% weight): D is **faster**, 14.536 vs 16.005 us
  (-9.2%). Here many threadgroups are in flight, so less work and one fewer
  barrier per threadgroup does help. Sized: 1.47 us/call x 40 layers = 58.8 us
  against a 196,864 us prefill (512 tokens x 384.5 ns) = 0.0299% of prefill ->
  **+0.0075% of score** at the 0.25 exponent.

Net -0.075%. Arm D is a correct, bit-exact, *net-negative* change. I am not
proposing it.

## What this rules out, for the record

Six r109 predecessors submitted empty diffs on this family. This is the
mechanism-level reason: the decode router is 0.43% of the step, half of that is
launch overhead that no in-kernel restructuring can touch, threadgroup-memory
occupancy is flat from 2048 B all the way down to 16 B at 256 threads/TG, and
decode runs one threadgroup so residency is irrelevant. Any future router
work on this track should target the *dispatch* (fusing it away), not the
kernel body.

Per the pre-authorized pivot in the assignment thread, I am moving to Arm G
(fold RMSNorm into the NVFP4 QKV kernel) without waiting.
