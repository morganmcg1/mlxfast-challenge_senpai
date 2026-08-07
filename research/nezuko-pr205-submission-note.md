# Decode attention merge epilogue: stage the cross-simdgroup transpose as `float4`

Single mechanism, one file (`Sources/MLXFastModel/LagunaRuntimeModel.swift`),
**net −454 bytes**, and **bit-identical by construction**.

## Provenance and environment

- **Harness / coding agent**: OpenHands, driven autonomously under the Senpai
  advisor–student research loop. Model attribution is recorded as `senpai` per
  that campaign's attribution policy.
- **Development host**: Apple **M4 Pro**, 20 GPU cores, `applegpu_g16s`, 48 GiB
  unified memory. This is *not* the ranked M5, which matters throughout: M4 Pro
  reports Apple GPU generation 16 and does not select the `_nax` prefill
  kernels. All timing below is therefore directional, and I say explicitly
  where it can and cannot carry a sign.
- **Base checkout**: the promoted frontier, local base
  **`747d130be532383d3eabd190f54f8b1b2bc6f9fd`**, i.e. this stacks on the
  current best rather than on a stale tree. The first seven sections of the
  research writeup were measured on the immediately preceding frontier
  `1fe609eb`; the base then advanced (an NVFP4 quantized-matmul change landing
  in three `Vendor/mlx-swift` files that my one-file diff does not touch), so
  the branch was rebased and every claim that could move was re-taken on
  `747d130b`: the bitwise logit certificate, the full `--local-submit` harness
  pass, and the byte budget. The rebased diffstat is byte-identical to the
  pre-rebase one (46 insertions / 80 deletions in a single file), so the edit
  transplanted exactly.
- **Setup / build / measurement commands**:
  ```bash
  ./setup.sh
  ./benchmark.sh --local-iterate     # matched research timing
  ./benchmark.sh --local-submit      # pre-submission correctness
  research/run_upstream_equivalence.sh
  swift build -c release --force-resolved-versions \
      --scratch-path .build-worker --product mlxfast-runtime-worker
  ```

## Goal and how the target was chosen

The scored objective is `decode_speedup^0.75 * prefill_speedup^0.25`, so decode
carries 75 % of the weight. A previous experiment of mine profiled the decode
attention kernels and found that, after the main softmax loop, a
**non-trivial tail of each kernel is the two-head merge epilogue** — pure
threadgroup-memory shuffling with no math worth the name. That tail was the
declared target here.

Before optimizing anything I priced it, rather than assuming it was worth
attacking (section "Failures and course corrections" explains why that ordering
mattered).

## What changed

Both decode attention kernels (sliding-window and full) process two heads per
threadgroup and finish with a cross-simdgroup merge: each simdgroup holds a
partial softmax result for its own KV block, and the epilogue transposes those
partials through threadgroup memory so a single `simd_sum` per output component
can combine them.

That epilogue used to declare `threadgroup U outputs[4 * BN * BDP]` and stage
**eight scalar planes** through it — 4 output components × 2 heads — with eight
threadgroup stores followed by eight threadgroup loads, all in one round.

It now declares `threadgroup float4 outputs4[BN * BDP]` and runs two rounds:
round 1 stores head 0's four components as a **single `float4`**, barriers,
reads one `float4` back, reduces and finalises head 0; round 2 reuses the same
buffer for head 1. **8 stores + 8 loads → 2 stores + 2 loads.**

Threadgroup footprint is unchanged (`float4[1056]` = `float[4224]` = 16 896 B,
total static threadgroup memory 18 432 B), grid and threadgroup size are
unchanged, and all barriers are retained — including the new round-1-read →
round-2-write WAR barrier that buffer reuse requires.

## Why it cannot change a bit

`U` is `typedef float`, so the `float4` staging is a pure repack of the same
32-bit values. The writer→reader transpose is the same bijection as before
(`lane*BDP+sg` written, `sg*BDP+lane` read), so **every `simd_sum` consumes the
same 32 scalar products from the same lanes in the same order**. Only the
grouping of independent reductions changed, which cannot perturb a result.

## Correctness evidence

- **Bitwise logit digest**, 64 decode steps, `top_k = 100352` (full vocabulary):
  base and candidate produce the **identical** whole-run digest
  `3447204b…4928`; **0 of 65 per-step digests differ**.
- **The control fires.** A 1-ULP bfloat XOR injected into the final store of
  both edited kernels — the smallest perturbation this change could have
  introduced — flips **64 of 65** per-step digests (the one it misses is the
  prefill step, correctly, since only the decode kernels were faulted). The
  greedy-token comparison stayed at 0 mismatches even under that fault, so the
  digest, not the token stream, is the instrument that is actually load-bearing
  here.
- **Upstream-equivalence oracle**: all 8 decode steps exactly
  `maximumAbsoluteLogitError = 0`, `EQUIVALENCE_EXACT_STEPS=8`, exactly one test
  selected. The prefill row (`0.125` / `0.011933609`, token `5991`) is the
  pre-existing M4 Pro artifact of the batched NVFP4 prefill path against the
  BF16 reference, reproduced byte-for-byte on the unmodified base in six prior
  sibling writeups; this change touches no prefill code.
- **`./benchmark.sh --local-submit`**: `passed_correctness true`,
  `max_abs_diff 0` over 1025 checked tokens / 1023 decode steps.
- An independent adversarial review of the diff returned **SAFE** on barrier
  sufficiency, FP equivalence, register liveness, indexing bounds, stale
  symbols, barrier divergence, and sliding-vs-full symmetry (the two new
  epilogues are byte-identical to each other).
- **Re-certified on the advanced base.** After the rebase onto `747d130b` the
  digest run was taken again from scratch — a real `git checkout 747d130b --`
  of the source plus a full rebuild for the reference arm, then restore and
  rebuild for the candidate. Identical whole-run digest, **0 of 65 per-step
  digests differing**, 0 token mismatches on both arms, and the two worker
  binaries hash differently (`0cb47228…` vs `d1e62269…`), so this is a genuine
  two-build comparison rather than a binary compared against itself. The
  `--local-submit` harness pass above was likewise re-run on the rebased tree
  (`passed: true`, `max_abs_diff: 0`, unchanged `golden_hash` and
  `harness_hash`). Incidentally the new-base digest equals the old-base digest,
  so the intervening frontier commit is itself bit-exact on this prompt and
  this change is bit-exact on top of it.

## Timing evidence

Measured on Apple M4 Pro (20 GPU cores, `applegpu_g16s`), so it is directional
for the ranked M5 rather than decisive.

Kernel-level ABBA-interleaved paired differencing (400 reps × 11 rounds of
A,B,B,A; every section carries a null arm — a second independent build of the
*same* source — that must straddle zero):

| kernel | null arm | this change |
|---|---|---|
| sliding (32 TGs) | +0.011 µs [−0.074 +0.127] | **+0.400 µs (+2.51 %) [+0.258 +0.564]** |
| full (24 TGs) | −0.011 µs [−0.261 +0.404] | **+0.202 µs (+1.11 %) [+0.073 +0.443]** |

This was the only candidate rewrite of five with a **strictly positive spread on
both kernels**; the others (deferred divides, reciprocal hoist, and two
combinations) were at or below the null floor and were not shipped. Per decode
step the model runs 30 sliding and 10 full attention layers, projecting
**≈ 14 µs/step** on this host.

A matched end-to-end check (8 arms interleaved cand/base/base/cand/cand/base/
base/cand at the canonical worker path, both binaries really built from source,
no arm rebuilding) came back at **+0.61 µs/step, 95 % CI [−50.4, +51.6]**, with
all 8 arms `passed_correctness` / `max_abs_diff 0`. That interval is 3.6× the
≈14 µs/step the kernel measurement projects, so this host cannot resolve the
effect end to end — it is reported as a no-regression check only, not as
confirmation. The kernel-level measurement above is the load-bearing timing
evidence.

The mechanism is entirely intra-threadgroup — threadgroup-memory access width
and count, with essentially zero incremental DRAM traffic — and it is
unconditional rather than a heuristic that could select differently on another
architecture. A companion sweep showed the epilogue is strongly sensitive to
this exact access pattern (dropping the `BDP` pad from 33 to 32 costs
**+1.97 µs** sliding and **+1.82 µs** full), which is what carries the sign of
the result across to the M5.

## Alternatives considered and rejected

Five rewrites of the epilogue were measured, not one:

| variant | mechanism | outcome |
|---|---|---|
| **V1** | `float4` staging of the transpose (shipped) | only arm positive on **both** kernels |
| V2 | defer the per-head divides past the merge | −0.081 sliding / +0.060 full — at the null floor |
| V3 | hoist a reciprocal out of the merge | −0.240 sliding / +0.019 full, **and not bit-exact** |
| V12 | V1 + V2 | +0.337 / +0.183 — no better than V1 alone |
| V123 | V1 + V2 + V3 | +0.416 / −0.007, interval straddles zero on full |

Three structural alternatives were ruled out before measurement:

- **Drop a barrier.** Audited all four barriers per kernel; every one is
  load-bearing. Dead.
- **Keep the partials in registers** and avoid threadgroup memory entirely.
  Structurally impossible: the reduction is *across* simdgroups, which have no
  register-level path to each other.
- **Collapse both heads into one round** (a single `float4` buffer sized for
  both). Would need 33 280 B of threadgroup memory against Apple's 32 768 B
  limit. Impossible, and this is exactly why the shipped version uses two
  rounds with a WAR barrier rather than one wider round.

V3 is worth a specific warning for future solvers: **MLX's JIT compiles Metal
with fast-math OFF** (`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp`),
so an algebraically-equivalent reciprocal hoist is *not* bit-equivalent. It also
happened to be slower, but it would have been disqualifying regardless.

## Failures and course corrections

**The measurement methodology had to be rebuilt mid-experiment.** My first
instrument reported absolute best-of-N µs/call. It showed a large, clean-looking
win — and it was an artifact: absolute best-of-N drifts **16 %** across sections
of a single process on this host, which is an order of magnitude larger than
anything being measured. Any ranking read off it would have been noise.

The instrument was rebuilt around **ABBA-interleaved paired differencing**
(400 reps × 11 rounds of A,B,B,A), and — the part that actually made it
trustworthy — **every section carries a null arm**: a second independent build
of the *same* source, which must straddle zero. Sections whose null arm did not
straddle zero were discarded rather than interpreted. This is what turned V1
from "looks fast" into a defensible result, and what demoted V2/V3 from
"apparent wins" to floor noise.

A second correction: the end-to-end driver's `restore_src` used
`git checkout -- <path>`, but `git checkout <sha> -- <path>` writes the *index*
too, so restores were silently reading back from a poisoned index. Fixed to
restore from `HEAD`.

## Caveats

- **All timing here is M4 Pro, not the ranked M5.** The kernel-level result is
  the load-bearing evidence and it is a same-host, same-kernel-family, matched
  comparison — but generation-16 vs the ranked M5 is a real gap, and
  threadgroup geometry can change sign across core counts.
- The end-to-end check is a **no-regression check only**; it cannot resolve a
  0.11 % effect on this host and is not offered as confirmation.
- The change is unconditional, with no heuristic or threshold that could select
  differently on another architecture — which is the main reason I expect the
  sign to transfer even though the magnitude may not.

## Learning

The generalisable finding is that **this epilogue is strongly sensitive to
threadgroup access pattern, not to instruction count**. The `BDP` padding sweep
is the cleanest demonstration: dropping the pad from 33 to 32 — which changes
*no* arithmetic whatsoever, only the bank-conflict behaviour — costs +1.97 µs
sliding and +1.82 µs full, roughly 5× the size of the win being chased here.
Anything touching this region should be evaluated as a memory-access change
first and an arithmetic change second.

## Next step

The epilogue is now down to 2 stores + 2 loads per kernel and is close to
exhausted as a target. The measured floor suggests the remaining headroom is in
the *main* softmax loop's threadgroup traffic rather than its tail, and the BDP
sensitivity above is the concrete lead: a padding/swizzle study of the main-loop
staging buffers, evaluated with the same null-arm ABBA discipline, is the
follow-up I would run next.

_Prepared by an AI agent (OpenHands) on behalf of the Senpai campaign._
