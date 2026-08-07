# Decode attention: `float4` merge epilogue, plus a uniform-buffer memo

Two independently-flagged mechanisms, one file
(`Sources/MLXFastModel/LagunaRuntimeModel.swift`), **net +1 169 bytes**, and
**bit-identical by construction** on both.

This is the second and last official receipt from this experiment. The first,
`c03dc117-5f3d-4e8f-aa74-a806880be49a`, carried mechanism A alone and returned
perfect correctness (`max_abs_diff 0`, 1 344 checked steps, 11 cases, GPQA TTFT
9/9, semantic judge 9/9, both floors passed) with `officialScore 2.5490802468639`.
It is referenced throughout.

## Provenance and environment

- **Submitter**: student `maple-nezuko`, PR #205, assignment
  `maple-2026-08-07c-attention-merge-epilogue`, revision `r1`, on the Senpai
  campaign branch `codex/mlxfast-maple-20260804-advisor`.
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

Two mechanisms, each behind its own ablation flag so they can be reverted
independently.

### Mechanism A — `float4` merge epilogue (`DARKBLOOM_*`, §3–§13 of the writeup)

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

### Mechanism E — full-attention uniform-buffer memo (`DARKBLOOM_FULL_PARAMS_MEMO`)

`lagunaFullFusedAttention` built its 3-word uniform buffer fresh on **every
call**:

```swift
MLXArray([UInt32(writeIdx), UInt32(writeIdx + 1), UInt32(capacity)])
```

Ten full-attention layers × 127 decode steps is roughly **1 270 host-side array
constructions and graph nodes inside the scored window**, purely to restate two
integers that almost never change. The sliding-window twin already avoids this
with a precomputed `lagunaRingIdxAtlas`.

The obvious fix is the same atlas, and it does not work here: the full-attention
cache has **no fixed modulus**. `capacity` is `cacheKeys.dim(2)`, chosen by the
growth policy, so a capacity-keyed atlas can only be built lazily — and lazily
means *inside the scored window*, because the decode timing window opens at the
512-token seed prefill. That pays back most of what it saves.

Instead: a **single-entry memo keyed on `(writeIdx, capacity)`**. All ten
full-attention layers share one cache clock
(`KVCacheSimple.fusedAppendPrepare()`), so within a step they all ask for the
same pair; the first builds, the other nine hit. That removes **1 143 of the
1 270 constructions (90 %)** with zero build cost and no assumption about
`capacity` at all. A capacity change simply misses and rebuilds.

## Why neither can change a bit

**Mechanism A.** `U` is `typedef float`, so the `float4` staging is a pure
repack of the same 32-bit values. The writer→reader transpose is the same
bijection as before (`lane*BDP+sg` written, `sg*BDP+lane` read), so **every
`simd_sum` consumes the same 32 scalar products from the same lanes in the same
order**. Only the grouping of independent reductions changed, which cannot
perturb a result.

**Mechanism E.** A hit returns an array whose three words were computed from
the *same* `(writeIdx, capacity)` the fresh construction would have used, so the
bytes are identical. The key is cache geometry only — never a token value,
never a prompt, never a request identity — so this is an
input-independent-state cache of exactly the kind the track rules permit, not a
memo on the benchmark repeating itself. Worker decode is single-threaded, which
is why the `nonisolated(unsafe)` storage is sound.

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
- **Certified by the official M5 once already.** Mechanism A alone was submitted
  as receipt `c03dc117-5f3d-4e8f-aa74-a806880be49a`, which returned
  `passed_correctness: true`, `max_abs_diff: 0`, `checked_steps: 1344` across
  11 cases, `gpqa_ttft_passed` 9/9, `semantic_gpqa_passed` 9/9, `error: ""`,
  `partial_result: false`, and both speedup floors true. Its `rejected` status
  was ranking-only (`rejectionReason: "score did not improve current best"`).
- **Mechanism E re-certified from scratch on the same instrument.** With both
  mechanisms applied, the two-build digest run was repeated: identical whole-run
  digest `3447204b…4928`, **0 of 65 per-step digests differing**, 0 token
  mismatches on both arms, and `./benchmark.sh --local-submit` clean
  (`passed: true`, `max_abs_diff: 0`, 1025 checked tokens). The memo is the only
  stateful object in this diff, so it was audited specifically for the one
  failure mode that matters — a **stale hit** — and the key includes `capacity`
  (`cacheKeys.dim(2)`) as well as `writeIdx`, so cache growth misses and
  rebuilds rather than returning a stale buffer.

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

Mechanism E is not measurable at kernel level — it removes host-side graph work,
not GPU work — so it is estimated structurally: 1 270 per-call
`MLXArray([UInt32, UInt32, UInt32])` constructions per scored decode window
(10 full-attention layers × 127 steps), of which the memo eliminates 1 143
(90 %). At an honest 10–30 ns per small-array construction-plus-graph-node this
is a few µs/step; I pre-registered a point estimate of **11 µs/step** with a
4–20 µs range before measuring anything.

**End-to-end, in situ, on the real worker.** A matched ABBA driver builds both
workers once from source (candidate from `HEAD`, base from
`git show 747d130b:Sources/…`), asserts the two binaries hash differently, then
runs a palindromic A/B/B/A schedule of 1 200-step teacher-forced decodes,
swapping *binaries as files* so no arm rebuilds. The run median in µs is the
unit of replication and adjacent (A,B) pairs are differenced.

| session | pairs | mean µs/step saved | sd | 95 % CI |
|---|---|---|---|---|
| mechanism A, session 1 | 6 | +2.20 | 20.86 | [−19.7, +24.1] |
| mechanism A, session 2 | 12 | +10.88 | 43.34 | [−16.7, +38.4] |
| **mechanism A pooled** | **18** | **+7.99** | 36.89 | **[−10.4, +26.3]** |

Median +15.38, 10 %-trimmed +12.32, sign test 11/18 (p = 0.240), Wilcoxon
W⁺ = 119 (p = 0.077). Positive-leaning and consistent with the +14 µs/step
kernel projection, but not significant: the standard error is 8.7 µs/step and
80 % power against +14 µs/step would need **55 pairs** (~94 min of paired GPU
time), against +7 µs/step **218 pairs**.

**The official M5 receipt.** Mechanism A was submitted once
(`c03dc117-5f3d-4e8f-aa74-a806880be49a`): `officialScore 2.5490802468639`,
`decode_speedup 2.8047880044191524`, `prefill_speedup 1.9135239675274414`. I
had pre-registered **+0.2853 %** on `decode_speedup` against the ranked anchor
`08ddee45` (2.818633); the observed value is **−0.4912 %**, so the point
prediction is rejected at 95 %. But the 1σ resolution of a two-receipt contrast
on this axis is 0.364 % (see *Learning*), so the observation is **−1.35σ** with
a 95 % CI of [−1.204 %, +0.222 %] that contains zero: this is a failure to
confirm, not a demonstrated regression. Decomposing the score drop against the
promoted frontier, **83 % of it sits in the two baseline arms** of that session
(`baseline_prefill` alone accounts for 75 %), i.e. in the part of the receipt
my code cannot touch.

Combining the M4 in-situ estimate (+7.99 ± 8.70) with the M5 receipt implied
(−24.2 ± 17.9) gives an agreement z of +1.62 (they do not conflict) and a
fixed-effect combination of **+1.86 ± 7.82 µs/step, CI [−13.5, +17.2]**.

**The combined candidate, A + E, on a quiet host — a resolved effect.** The
same in-situ probe was then run on the shipped `A + E` candidate against the
unchanged base, 24 runs of 1200 decode steps in a 12-pair palindrome
(`A B B A ...`), every run reporting `0 divergences (all match)`. Provenance
emitted by the script: `SRC_MD5_HEAD 192a0d29`, `SRC_MD5_BASE 917039f5`,
`BIN_MD5_A 1cddf80e`, `BIN_MD5_B 1e8f9699`, `BINARIES_DIFFER 1`,
`WORKTREE_DIRTY_AFTER_BUILD 0`.

```text
arm A (candidate) n=12 median-of-medians 8278.57 us  sd 12.32
arm B (base)      n=12 median-of-medians 8296.31 us  sd 12.61
pairs: +24.23 +22.79 +16.38 +43.98 +1.23 +9.60 +15.65 +22.42 +16.67 +17.63 +14.90 +17.50
PAIRED n=12  saved mean +18.58 us/step  sd 10.11  se 2.92  t +6.37
PAIRED 95% CI [+12.16, +25.00] us/step  (+0.147 % .. +0.301 % of the step)
```

Twelve of twelve pairs are positive (sign test p = 0.000244); t = 6.37 on
11 df gives p ≈ 5e-5. The per-run scatter (sd 10.11) is four times tighter
than the earlier session's 43.34, so the host was quiet — that is why this
session resolves what eighteen earlier pairs could not. The median-of-medians
difference (17.74 µs) agrees with the paired mean, so no single run carries
the result. The pre-registered projection for the combined mechanism was
14.02 (A) + 11 (E) = **25 µs/step**, which lies inside the observed interval;
the pre-registered kill condition (negative estimate with an upper bound below
+5 µs/step) did **not** fire.

Projected to the ranked axis with the elasticity used above,
`18.58 / 4928.12 = +0.377 %` on `decode_speedup` and **+0.283 %** on
`officialScore` — right at the honest ceiling I derived for this target.

The honest summary of the timing axis is therefore: **the mechanism is real
and now resolved end to end on the instrument that can see it, and it is
below the resolution of the instrument that ranks it.** A two-receipt official
contrast has a 1σ of ~18 µs/step (see *Learning*), so +18.58 µs/step is a
1.04σ effect on the official axis — unrankable in isolation, which is exactly
what the single spent receipt showed. This is reported as **an unrankable
positive, not a win on the leaderboard and not a regression**.

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
- The **official** end-to-end check is underpowered, not negative: a two-receipt
  contrast has a 1σ of ~18 µs/step, and the one receipt spent on mechanism A
  gave an interval containing both zero and the predicted effect. The M4 in-situ
  probe *does* resolve the combined `A + E` mechanism (+18.58 ± 2.92 µs/step,
  12/12 pairs positive) — but that is M4 evidence for an M5 ranking, and its
  projected +0.283 % on `officialScore` is still only ~1σ of the official
  instrument. Nothing here should be read as a predicted leaderboard move.
- Mechanism A is unconditional, with no heuristic or threshold that could select
  differently on another architecture — which is the main reason I expect the
  sign to transfer even though the magnitude may not.
- Mechanism E is the only stateful object here. It is keyed purely on cache
  *geometry* (`writeIdx`, `capacity`), never on token, prompt, or request
  identity, so it is an input-independent cache of the kind the track rules
  permit — not a memo whose only possible hit is the harness repeating work. It
  advances no KV position and holds no cross-request state. The
  `nonisolated(unsafe)` statics are sound because worker decode is
  single-threaded; if that ever stops being true this needs revisiting first.
- **The two mechanisms are not separately attributable in this submission.**
  They are shipped together because neither is individually resolvable by the
  available instruments (11 µs/step is 0.61σ on the receipt axis). If the
  combination is ever shown to regress, mechanism A is the one to revert first,
  since E only removes work.

## Learning

The generalisable finding is that **this epilogue is strongly sensitive to
threadgroup access pattern, not to instruction count**. The `BDP` padding sweep
is the cleanest demonstration: dropping the pad from 33 to 32 — which changes
*no* arithmetic whatsoever, only the bank-conflict behaviour — costs +1.97 µs
sliding and +1.82 µs full, roughly 5× the size of the win being chased here.
Anything touching this region should be evaluated as a memory-access change
first and an arithmetic change second.

A second, more portable finding came out of trying to interpret my own first
receipt. I pulled the full public submission corpus (1 115 receipts with
official metrics) and treated the **baseline arm** — the unmodified baseline
binary, re-timed inside every single receipt — as a pure noise series carrying
zero candidate signal. Its marginal cv is **0.245 %** on
`baseline_decode_seconds_per_token` and **1.936 %** on the prefill twin. The
interesting part is the autocorrelation: a variogram binned by time gap
(`<15 min`, `15–60 min`, `1–4 h`, `4–24 h`, `1–7 d`, `>7 d`) is **flat at
95–102 % of the marginal variance in every bin**, and over 1 114 adjacent pairs
(median gap 10 min) the paired difference sd is `0.9818×` the i.i.d.
prediction `√2·σ` for decode and `1.0055×` for prefill, with lag-1
autocorrelation `+0.037 ± 0.030` and `−0.011 ± 0.030`.

So the official measurement noise is **white from 15 minutes out to two weeks**:
there is no slow thermal or fleet drift to difference away, and submitting two
candidates back to back buys nothing over submitting them a week apart. That
also fixes the achievable resolution of a two-receipt contrast: 1σ is
**0.364 %** on `decode_speedup` and **0.785 %** on `officialScore`, which on
this benchmark's decode axis is **≈ 18 µs per decode step**. Any single
mechanism worth less than ~36 µs/step is simply not resolvable by receipts, and
should be argued on kernel-level evidence or not at all. I found this out by
predicting +14 µs/step and getting an uninterpretable answer, which is the
expensive way to learn it.

## Next step

The epilogue is now down to 2 stores + 2 loads per kernel and is close to
exhausted as a target. The measured floor suggests the remaining headroom is in
the *main* softmax loop's threadgroup traffic rather than its tail, and the BDP
sensitivity above is the concrete lead: a padding/swizzle study of the main-loop
staging buffers, evaluated with the same null-arm ABBA discipline, is the
follow-up I would run next.

The more important next step is methodological. Given the ~18 µs/step receipt
resolution established above, the right way to spend a receipt on this class of
target is **not** to submit one mechanism at a time and hope. It is to stack
several independently bit-exact, independently kernel-certified mechanisms until
their sum clears ~36 µs/step, and submit the stack once — accepting up front
that the receipt certifies *correctness* of the stack and only bounds its
timing. Mechanism E was folded into this submission on exactly that reasoning.
Conversely, receipts remain the only instrument that exercises the 1 344-step,
11-case, GPQA and semantic-judge correctness surface, which is what a stateful
change like mechanism E most needs and what a single local 64-step case is
nearly blind to.

_Prepared by an AI agent (OpenHands) on behalf of the Senpai campaign._
