# The attention merge epilogue (PR #205, `maple-2026-08-07c-attention-merge-epilogue`)

Student: maple-nezuko. Base `codex/mlxfast-maple-20260804-advisor` @
**`747d130be532383d3eabd190f54f8b1b2bc6f9fd`** (rebased; the assignment marker's
base was `1fe609eb920dd96a409f2949a0e901d3bb525af6`, and sections 1-7 were
measured there -- see §9 for the rebase and the re-verification). Host: Apple
M4 Pro, 20 GPU cores, `applegpu_g16s`, 48 GiB. Ranked host is M5 Max.

Shipped surface: `Sources/MLXFastModel/LagunaRuntimeModel.swift` only.
Net editable growth **−454 bytes** against `747d130b` (§8), well inside the
advisor's revised +12,000-byte cap.
Research-only: this file, `research/nezuko_epilogue_probe.swift`,
`research/nezuko_epilogue_abba.sh`,
`research/nezuko_pr205_rebase_verify.sh`,
`research/nezuko_pr205_dispatch_receipt.sh` and
`research/nezuko-pr205-submission-note.md`.

---

## 0. What the target is

Both decode attention kernels

- `laguna_sliding_fused_attn_ring_v1` (32 threadgroups x 1024 threads)
- `laguna_full_fused_attn_grow_v1` (24 threadgroups x 1024 threads)

end with a **merge epilogue**: the post-KV-loop block that combines the 32
per-simdgroup partial softmax states into the final `attended` rows. It is a
verbatim mirror between the two kernels. Its structure in the base commit:

| stage | work |
| --- | --- |
| broadcast | `lane == 0` writes 4 scalars to `max_scores` / `sum_exp_scores` |
| round-1 write | 4 threadgroup float stores into `outputs[]` (transposing, `lane*BDP + sg`) |
| barrier #1 | RAW |
| score reduce | 4 tg loads, 2 `simd_max`, 2 `fast::exp`, 2 `simd_sum` |
| round-1 read | 4 tg loads (`sg*BDP + lane`), 4 `simd_sum`, 4 divides |
| barrier #2 | WAR |
| round-2 write | 4 threadgroup float stores |
| barrier #3 | RAW |
| round-2 read | 4 tg loads, 4 `simd_sum`, 4 divides |
| final store | `lane == 0` writes 8 scalar `bfloat` to device |

Thread `(sg = S, lane = L)` holds the partials for output dims `[4S, 4S+4)`
computed from KV chunk `L`. The write/read index pair transposes so that
`simd_sum` inside simdgroup `S` sums over `L = 0..31`.

The advisor's prior measurement priced this block at a roughly constant
1.068 / 1.072 / 1.170 us at N = 64 / 256 / 512, i.e. ~12.9% of a 512-row call,
40 calls/step -> ~46.8 us/step, ceiling +0.685% score at the recorded
elasticity.

---

## 1. Methodology, and the measurement lesson that had to come first

**The first two probe designs were unusable and were deleted.** They used
best-of-N absolute us/call. On this host the *unmodified* sliding kernel read
15.90, 15.98, 17.99, 18.36 and 18.50 us in five different sections of one 10 s
process -- a 16% swing that dwarfs every effect under test. A truncation ladder
was additionally confounded twice over: removing an epilogue stage lets the
compiler dead-code the producer, and it lowers register pressure, which can
change occupancy.

The instrument was rebuilt around **ABBA-interleaved paired differencing**:

- `timeOnce(pipe, ...)` = one command buffer of `kReps = 400` dispatches,
  us/call from `cb.gpuEndTime - cb.gpuStartTime`.
- `paired(a, b)` runs `kRounds = 11` rounds of `A, B, B, A` (the two arms are
  ~15 ms apart), and each round's estimate is `(A1+A2)/2 - (B1+B2)/2`, which
  cancels linear drift. Reported: **median delta** plus the **min..max spread**
  over the 11 rounds.
- Every section carries a **`null` row**: a second, independently compiled
  build of the *same* source, paired the same way. It must straddle zero. It
  bounds what the design can resolve.
- Semantics-preserving *duplication* replaces truncation, so nothing can be
  dead-coded and no arm can come out cheaper than the reference except through
  noise.

Whole probe: ~16 s. Log:
`state/openhands_state/training/adcedf1f-4699-4dc5-ae92-2e957080198e.log`.

> Transferable lesson for the track: on this host, **absolute us/call from
> different sections of one process are not comparable**. Any kernel
> micro-result stated as "arm X was N us and arm Y was M us" without ABBA
> pairing and a null row should be treated as unproven.

---

## 2. Step 0 -- decomposition of the epilogue (mandatory deliverable)

### 2.1 S1, duplication pricing

Each row inserts **one extra copy** of a single epilogue component and is
ABBA-paired against the reference. An anti-DCE sink (`U dbprobe = pair_max0 *
0.0f;` folded into the final `static_cast<bfloat>`) keeps the duplicated work
live; MLX JIT-compiles these kernels with **fast math off**
(`Vendor/mlx-swift/.../metal/device.cpp:631`,
`options->setFastMathEnabled(false)`), so `* 0.0f` cannot be folded away.

Marginal cost of one extra copy, us/call:

| component | sliding | full |
| --- | ---: | ---: |
| **null** (2nd build of same source) | -0.050 | +0.014 |
| 4 threadgroup float stores | +0.072 | +0.007 |
| 4 tg loads + 4 `simd_sum` | -0.001 | -0.010 |
| 4 `simd_sum` only (register operand) | -0.006 | +0.029 |
| score reduce (4 ld, 2 `simd_max`, 2 `exp`, 2 `simd_sum`) | -0.005 | +0.007 |
| 8 scalar `bfloat` device stores | +0.066 | -0.006 |

**Every marginal cost sits at or below the null floor.** Reconstructed epilogue
total (2 rounds of write/read + 1 score + 1 store, barriers excluded):
sliding **0.202 us = 1.1%** of the 18.446 us call; full **-0.005 us ~ 0%**.

### 2.2 P2, barrier price

Duplicating barrier #3 is a semantic no-op, so this prices barrier latency with
no DCE and no correctness confound. Extra barriers of 0/1/2/4/8:

- sliding: all deltas in [-0.032, +0.028] us, every spread straddling zero.
- full: all deltas in [-0.089, +0.002] us, every spread straddling zero.

**Barriers are not resolvable as a cost at this rep count.**

### 2.3 P3, threadgroup bank-conflict sensitivity (the one large signal)

`BDP = BD + 1 = 33` pads each 32-wide plane so the transposing write
`outputs[lane*BDP + sg]` hits 32 distinct banks. Setting `BDP = 32` turns that
write into a 32-way bank conflict while remaining a bijection, hence still
bit-identical.

| BDP | sliding vs 33 | spread | full vs 33 | spread |
| ---: | ---: | --- | ---: | --- |
| 32 | **+1.966 us** | [+1.753 +2.517] | **+1.820 us** | [+1.641 +1.957] |
| 33 | -0.012 | [-0.140 +0.097] | +0.015 | [-0.158 +0.187] |
| 34 | -0.065 | [-0.967 +1.130] | -0.034 | [-0.163 +0.073] |
| 36 | -0.012 | [-0.178 +0.360] | +0.054 | [-0.010 +0.750] |
| 40 | -0.059 | [-0.176 +0.095] | +0.015 | [-0.190 +0.134] |

The existing `+1` padding is worth ~1.9 us/call on both kernels, and the effect
reproduces with a spread far from zero. **The epilogue is strongly threadgroup
access-pattern sensitive** even though no individual component is expensive.
This is what says the epilogue is addressable: not by removing instructions,
but by changing the *shape* of its threadgroup traffic.

### 2.4 P4, divides

Hoisting the 8 `acc / pair_sum` divides into a reciprocal multiply:
sliding -0.088 us [-0.643 +0.287], full +0.006 us [-0.074 +0.125]. Null.
And with fast math off, `RN(a * RN(1/s)) != RN(a / s)`, so it is not shippable
anyway. **Divides are closed as a lever.**

### 2.5 Formal evaluation of the pre-registered kill

> "If Step 0 shows >70% of the 1.07 us is a single unmovable cross-simdgroup
> reduction latency, stop and write it up."

**Kill NOT triggered.** No single component reaches even 40% of the
reconstructed total, the `simd_sum` reduction rows are *negative* on sliding
and inside the null floor on full, and the one large reproducible signal (P3,
~1.9 us) is a movable access-pattern cost, not a fixed reduction latency.
Section 4.12.8(G) stays an open target.

---

## 3. Arm status

### Arm B -- drop a barrier: **DEAD**

All three barriers are load-bearing, and P2 says they would be free even if
they were not:

- #1 RAW: round-1 reads `outputs[sg*BDP + lane]` written by other simdgroups.
- #2 WAR: round-2 writes overwrite locations round-1 still had to read.
- #3 RAW: same cross-simdgroup dependency as #1.

### Arm C -- keep partials in registers: **structurally impossible**

The merge is a reduction *across* simdgroups. Apple GPUs have no
cross-simdgroup register path; threadgroup memory is the only channel. There is
no register formulation of this step.

### One-round collapse -- **structurally impossible (32 KB wall)**

Doing both heads' four planes in a single round needs `8 * BN * BDP` floats.
Padded that is `8 * 1056 * 4 = 33792 B`, over Apple's 32768 B threadgroup
limit. An XOR-swizzled unpadded layout lands at exactly 32768 B but
`max_scores` + `sum_exp_scores` still need 512 B -> 33280 B. **Two rounds and
three barriers are forced.**

### Arm D -- `simd_shuffle` the within-simdgroup reduction: **not pursued**

`simd_sum` is already a shuffle-reduction on Apple GPUs; S1 prices the
reduction rows at or below the null floor. There is nothing to win.

### Arm A -- collapse the passes over `outputs[]`: **the winner (V1)**

Not by fusing rescale into accumulation (S1 shows the arithmetic is free), but
by changing the *width* of the threadgroup traffic, which P3 shows is what the
epilogue is actually sensitive to.

**V1**: declare `threadgroup float4 outputs4[BN * BDP]` in place of
`threadgroup U outputs[4 * BN * BDP]`. Round 1 stages head0's four planes as a
single `float4` and finalizes head0; round 2 does head1. This turns
**8 threadgroup stores + 8 threadgroup loads into 2 + 2**.

- Footprint unchanged: `BN * BDP` float4 = `4 * BN * BDP` float = 16896 B.
- Max index `31*33 + 31 = 1054 < 1056`.
- Pitch 33 float4 keeps the transposing access conflict-free for 16-byte
  accesses.
- **Bit-identical by construction**: each `simd_sum` consumes exactly the same
  32 scalar products in exactly the same lane order; only the round in which a
  given plane is finalized changes, and rounds are independent.
- All three barriers retained.

Two further ideas were measured as **separate arms** and are **not shipped**:

- **V2**: 8 scalar `bfloat` device stores -> 2 `vec<bfloat,4>` stores
  (8-byte-aligned, verified). Bit-safe, but null-to-negative in timing.
- **V3**: pack `max_scores` + `sum_exp_scores` into one
  `threadgroup float4 stats[BN]`. Bit-safe, but null-to-negative in timing.

---

## 4. S4 -- ABBA-paired arm results

`saved > 0` = variant faster than the shipped kernel it was interleaved with.

### sliding (32 threadgroups)

| arm | us/call | saved | % of call | spread |
| --- | ---: | ---: | ---: | --- |
| null | 16.066 | +0.011 | +0.07% | [-0.074 +0.127] |
| **V1** | 15.533 | **+0.400** | **+2.51%** | **[+0.258 +0.564]** |
| V2 | 18.475 | -0.081 | -0.44% | [-0.333 +0.043] |
| V3 | 18.784 | -0.240 | -1.30% | [-0.575 -0.159] |
| V12 | 18.174 | +0.337 | +1.82% | [+0.172 +0.479] |
| V123 | 18.071 | +0.416 | +2.25% | [+0.292 +0.640] |

### full (24 threadgroups)

| arm | us/call | saved | % of call | spread |
| --- | ---: | ---: | ---: | --- |
| null | 18.271 | -0.011 | -0.06% | [-0.261 +0.404] |
| **V1** | 18.146 | **+0.202** | **+1.11%** | **[+0.073 +0.443]** |
| V2 | 18.277 | +0.060 | +0.33% | [-0.101 +0.164] |
| V3 | 18.414 | +0.019 | +0.10% | [-0.098 +0.169] |
| V12 | 18.182 | +0.183 | +1.00% | [+0.023 +0.332] |
| V123 | 15.671 | -0.007 | -0.05% | [-0.664 +0.645] |

**V1 is the only arm whose 11-round spread is strictly positive on both
kernels.** V2 and V3 are individually null-to-negative; V12 does not beat V1;
V123 is positive on sliding but null on full with a spread nearly 10x its
point estimate. Stacking was therefore *not* done -- V1 alone ships.

Kernel-level projection: `30 * 0.400 + 10 * 0.202 = ~14.0 us/step` on M4 Pro.
The pre-registered abort threshold was "worse than -15 us/step"; +14 us/step of
saving clears it comfortably in the right direction.

---

## 5. Transfer argument to the ranked M5

The mechanism is **entirely intra-threadgroup**: threadgroup-memory access
width and count, with essentially zero incremental DRAM traffic. Under
section 4.11.1, M5 decode is instruction/latency-bound at ~89% utilisation
while M4 is bandwidth-bound; section 4.11.3 makes an instruction-mechanism M4
win presumptively transferable. Because nothing here crosses a threadgroup
boundary, the inter-threadgroup hazards that killed T1 do not apply. The
change is also unconditional -- it is not a heuristic that could select
differently on another architecture -- and the threadgroup footprint, grid,
threadgroup size, barrier count and numerical sequence are all unchanged.

The residual M5 risk is the usual one: 20 GPU cores vs the ranked part's core
count changes occupancy, so the *magnitude* may differ. The *sign* is carried
by the P3 result, which shows the threadgroup access pattern is the dominant
epilogue cost on this family.

---

## 6. Correctness

See section 7 for the executed evidence. Protocol (fern's #137):

1. Bitwise logit digest, `top_k = 100352`, 64 steps, base vs candidate,
   requiring 0/65 step digests to differ.
2. **A control shown to fire**: a 1-ULP fault injected into the epilogue must
   flip the digest. A gate that has never been seen to fail is not a gate.
3. `research/run_upstream_equivalence.sh`.
4. `./benchmark.sh --local-submit`.

## 7. Executed evidence

Every number below came from a supervised run on this host (Apple M4 Pro, 20 GPU
cores, `applegpu_g16s`, 48 GiB). Training IDs are the Senpai supervised-run IDs;
their logs are the primary record.

### 7.1 Bitwise logit certificate (the instrument that actually resolves this)

Instrument: `research/frieren_pr80_logit_bitwise.py` against
`.build-worker/release/mlxfast-runtime-worker`, golden
`correctness_prompts/public_longcopy_gate_english_512_256.json`, 64 decode steps,
`top_k = 100352` (the full vocabulary -- no truncation that could hide a
reordering), SHA-256 over each step's logit block plus one whole-run digest.

| arm | worker source | training id | RUN_DIGEST | token mismatches |
|---|---|---|---|---|
| `ref-base` | `1fe609e` `LagunaRuntimeModel.swift` | `cc21ce01-9593-4d9e-8740-3bc35c3f72cb` | `3447204b58f5192f772df1a064f0fc87dd59fe41f4720b51f7e6f103403b4928` | 0 |
| `cand-v1` | this branch | `82cba330-3fa1-4b5f-a296-5d5bb2df4740` | `3447204b58f5192f772df1a064f0fc87dd59fe41f4720b51f7e6f103403b4928` | 0 |
| `fault-1ulp` | candidate + injected fault | `06e8e5eb-ba8c-43f3-ab97-e545ec321c26` | `630e406f351583156e7fdd5da62449f88f75168f157a056a745b37a9dc5d8ec1` | 0 |

**Base and candidate digests are equal. Per-step digests differing: 0 of 65.**
Raw outputs kept at `/tmp/nez_epi_cert/{ref,cand,fault}.json`.

**The control fires.** The fault arm XORs one bfloat ULP into `pair_out0[0]` in
the *final store of both edited kernels* -- the smallest perturbation the change
could possibly have introduced. It flipped **64 of 65** per-step digests. The one
step it did not flip is step 0, the prefill "begin" step, which is correct: only
the two decode kernels were faulted. So the digest is demonstrably sensitive to a
single-ULP change in exactly the code V1 rewrites, and its agreement between base
and candidate is real evidence rather than an untested gate.

Note also that `TOKEN_MISMATCHES` stayed 0 in the *fault* arm. The greedy-token
comparison is blind to a perturbation this size; only the logit digest sees it.
That is why the digest, not the token stream, is the correctness instrument here.

### 7.2 Vendored-upstream equivalence oracle

`research/run_upstream_equivalence.sh`, training `eff0a7d5-03f0-4f8f-bae5-1d9df0ab5067`.

| step | `maximumAbsoluteLogitError` | `meanAbsoluteLogitError` | runtime tok | upstream tok |
|---|---|---|---|---|
| prefill | 0.125 | 0.011933609 | 5991 | 5991 |
| decode-0 .. decode-7 | **0** (all 8) | 0 | 509 / 902 / 5991 ... | equal |

`EQUIVALENCE_EXACT_STEPS=8`, `EQUIVALENCE_EXIT=1`, exactly one test selected
(`"promptTokenCount" : 512` present, so this is not a zero-test false pass).

**All eight decode steps are exactly zero -- decode is the only thing this change
touches.** The non-zero exit comes entirely from the prefill row, and that row is
a pre-existing, independently documented M4 Pro artifact of the batched NVFP4
prefill path against the BF16 upstream reference. It reproduces byte-for-byte on
the unmodified base in at least six sibling writeups, with the identical constants
0.125 / 0.011933609 and the identical token 5991:
`research/frieren-host-cpu-budget.md:471`,
`research/maple-fern-pr40-result.md:381`,
`research/frieren-pr23-r2-cap.md:311`,
`research/frieren-pr35-r3-b-verification.md:106`,
`research/maple-fern-pr137-lmhead-cascade.md:266`,
`research/RESEARCH_STATE_ARCHIVE_through-round-21.md:6085`.
I therefore did not spend a separate base oracle run reproducing a constant six
prior runs already pinned.

### 7.3 `./benchmark.sh --local-submit`

Training `6d92dd0f-969a-4820-b442-567239d5dfcb`, exit 0, 227 s.

```
passed                       : true
passed_correctness           : true
max_abs_diff                 : 0
checked_tokens               : 1025    decode_steps : 1023
first_failing_case/layer/step: null / null / null
golden_hash  f49e4c2cbc0d3ceee90195a3a12e1ff082636f8c031587485a9a2c10702b03d2
harness_hash 51c1773772ae8007dcb822042b9a62cb418778fbb7e2dfb1cb4c96e6a4bcffa8
peak_ram_gb 21   num_layers 40
```

`max_abs_diff = 0` over 1023 checked decode steps, on top of the 64-step digest.
`passed_prefill_speedup_floor : false` is the ordinary M4 Pro reading -- the
harness scores local prefill against the M5 official-runner constant
`0.000368 s/token`, and this host cannot reach it on any build; the floor that
matters is the same-session paired one on the ranked M5.

### 7.4 Independent adversarial review of the diff

A frontier reviewer with no prior context was given the diff cold and asked for
hazards, not confirmation. Verdict **SAFE** on all seven classes it was asked to
break:

1. the read-1 -> store-2 **WAR barrier is present and correctly placed**
   (`LagunaRuntimeModel.swift:1622` sliding, `:2106` full) -- the buffer is now
   reused across rounds, so this was the real risk and it is covered;
2. `typedef float U`, so `float4` staging is a pure repack; the writer -> reader
   transpose (`lane*BDP+sg` -> `sg*BDP+lane`) delivers each `simd_sum` the
   identical per-lane operand as before; reordering independent reductions cannot
   change a bit;
3. `pair_global_factor1` / `pair_sum1` are live and unmodified into round 2;
4. footprint identical at 16 896 B (`float4[1056]` == `float[4224]`), max index
   `31*33+31 = 1054 < 1056`, total static threadgroup memory 18 432 B;
5. **zero** remaining references to the old `outputs`/`pair_planes` symbols, and
   **no** `setThreadgroupMemoryLength` / `staticThreadgroupMemoryLength` anywhere
   in `Sources/MLXFastModel/` -- these are body-declared statics in an
   `MLXFast.metalKernel` JIT kernel, so there is no host-side length to update
   and no `mlx-generated/*.cpp` twin;
6. all four barriers per kernel are at kernel-body top level, none inside
   `if (lane == 0)`, no early `return`, so all 1024 threads reach them uniformly;
7. the two new epilogues are **byte-identical** to each other (`diff` empty), so
   the sliding and full kernels cannot drift apart.

### 7.5 End-to-end matched timing

`research/nezuko_epilogue_abba.sh`, training `a61d8241-7fa5-470d-8026-f8d8421ffb83`.

Both workers are built from real source in the same script -- the base arm is
`git checkout 1fe609eb -- Sources/MLXFastModel/LagunaRuntimeModel.swift` followed
by a real `swift build`, not a runtime override -- then interleaved
**cand/base/base/cand/cand/base/base/cand** at the canonical worker path so the
sandbox, the freshness gate and the 40 C thermal gate behave exactly as in a
normal run. Only the worker binary differs between arms.

`WRAPPER_EXIT=0`, all 8 arms `rc=0`, `passed_corr=True`, `max_abs_diff=0`.
`PROVENANCE cand=47e8dbd80cec27dd1961c273239a3b14 base=4f5770829edb426cd6beb4014a126bbe`
-- genuinely distinct binaries, and the `cand` hash equals the `--local-submit`
build of section 7.3, so the compile is deterministic. `worktree_clean=1`, and
the base arm really is `git checkout 1fe609eb -- <src>` plus a real `swift build`
(diff stat: 1 file, 80 insertions, 46 deletions). Grepping all eight per-arm logs
for `building`/`Compiling`/`swift build` returns **0**: every arm ran a pre-built
binary, so this is binary-vs-binary and not build-vs-build.

| idx | arm | decode s/tok | idx | arm | decode s/tok |
|---|---|---|---|---|---|
| 1 | cand | 0.012925288 | 5 | cand | 0.012916851 |
| 2 | base | 0.012883427 | 6 | base | 0.012910434 |
| 3 | base | 0.012923467 | 7 | base | 0.012883693 |
| 4 | cand | 0.012897529 | 8 | cand | 0.012858930 |

| | n | mean s/tok | sd |
|---|---|---|---|
| candidate | 4 | 0.012899649 | 0.000025572 |
| base | 4 | 0.012900255 | 0.000017320 |

Paired by ABBA position, µs/step saved (positive = candidate faster):
**−41.86, +25.94, −6.42, +24.76**; mean **+0.61 µs/step (+0.005 %)**,
median +9.17, sd 32.03, and a 95 % CI of **[−50.4, +51.6] µs/step**.

**This is a no-regression check, and that is all it can be.** I pre-registered
the arithmetic before running it: the kernel-level result projects to
30 x 0.400 + 10 x 0.202 = **≈14 µs/step**, against a 12 900 µs step. That is a
0.11 % effect, and the CI half-width here is 51 µs -- **3.6x the size of the
effect being looked for**. An instrument that cannot resolve the hypothesis
cannot confirm it, and it equally cannot refute it. The honest reading of
+0.61 ± 51 µs/step is *"consistent with the predicted +14, and consistent with
zero, and consistent with −14"*.

So this run discharges exactly two obligations and no others:

1. the pre-registered M4 kill threshold ("worse than −15 µs/step") is **not**
   triggered -- the point estimate is positive and the lower bound is far short
   of a real regression at this sample size; and
2. correctness holds end to end under the real harness on both binaries, in
   four independent interleaved pairs.

It is **not** evidence that the mechanism works. That claim rests entirely on
the kernel-level ABBA of section 4, where the effect is 3-5x its own interval on
both kernels and every section carries a null arm that straddles zero. Reporting
the +0.005 % end-to-end number as a win would be reading a noise draw; reporting
the arm-1-vs-arm-2 slice (which, taken alone, showed the candidate 42 µs
*slower*) as a loss would be the same mistake with the opposite sign. Both are
why the design interleaved four pairs instead of running one A/B.

Prefill moved +5.45 µs/step (+0.487 %) toward the candidate. V1 touches no
prefill code, so this is a pure noise reading and a useful scale check on what
this host's drift looks like over a 20-minute window.

## 8. Budget

Against the **advanced** base `747d130be532383d3eabd190f54f8b1b2bc6f9fd`
(the advisor's revised requirement, reported here as asked):

```
$ ./senpai/check-editable-budget.sh 747d130be532383d3eabd190f54f8b1b2bc6f9fd
editable budget OK: current=2949232/3000000 bytes headroom=50768
                    growth=-454/262144 files=142 (base=142)
```

**Net growth = −454 bytes.** The revised hard cap for this PR is +12,000 bytes
of net growth, shared against a 50,314-byte pool with PRs #204, #148 and #215.
This change does not draw from that pool at all -- it *returns* 454 bytes to it,
because collapsing eight staged stores/loads into two removes more source than
the `float4` repack adds. Under the older 22 KB framing the figure was the same
(`growth=-454` against base `1fe609eb`, where `headroom` read 65,318); only the
absolute `current`/`headroom` numbers move with the base, since PR #170 added
bytes elsewhere in the surface.

No new file is created, no new kernel-variant string is introduced, and no new
specialization is added to any dispatch table. The advisor's warning about
variant strings does not apply: Arm A is a pure in-place rewrite of two existing
kernel bodies.

Region fence honoured: the diff touches only lines inside the two attention
kernel bodies (`~1466`, `~1593-1662`, `~1923`, `~2094-2163` in the base
numbering). Nothing in `600-1100`, `8525-8910`, `9461-9575` or `10003-10130`.

## 9. Rebase onto the advanced base `747d130b`, and re-verification

### 9.1 Why

All of sections 1-7 were measured against the assignment marker's base
`1fe609eb920dd96a409f2949a0e901d3bb525af6`. While the official receipt was being
dispatched, the advisor advanced the base to
`747d130be532383d3eabd190f54f8b1b2bc6f9fd` (PR #170 merged) and tightened the
byte cap. The in-flight dispatcher was **cancelled before it invoked `submit`**
(`submitted=0`; zero official receipts consumed), the branch was rebased, and
every claim that could move was re-taken on the new base. This section records
that re-verification; it is not a summary of the old one.

### 9.2 The rebase is clean by inspection, not by assertion

PR #170 (`1fe609eb` → `747d130b`, 295 insertions / 4 deletions) touches exactly
three files:

```
Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized_nax.cpp
Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized_nax.h
Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp
```

My change touches exactly one file,
`Sources/MLXFastModel/LagunaRuntimeModel.swift`. The intersection is empty, so
the rebase had no conflict to resolve and no semantic interaction to reason
about: #170 is an NVFP4 quantized-matmul kernel change, mine is a threadgroup
staging change in the decode attention epilogue.

The transplant is verified numerically rather than trusted:

```
$ git diff --stat 747d130b HEAD -- Sources Vendor
 Sources/MLXFastModel/LagunaRuntimeModel.swift | 126 +++++++-------------
 1 file changed, 46 insertions(+), 80 deletions(-)
```

46/80 is **byte-identical** to the pre-rebase diffstat against `1fe609eb`, and
`grep -c outputs4` still returns 10 (two declarations, four stores, four loads).
The edit survived the rebase exactly.

### 9.3 Bitwise logit certificate re-taken on `747d130b`

Driver `research/nezuko_pr205_rebase_verify.sh` (committed). It does a real
`git checkout 747d130b -- <src>` + full rebuild for the reference arm, then
restores and rebuilds the candidate, and hashes the per-step top-k logit
digests. Supervised training `17f7d0f3-2c5b-414a-86db-abc200111684`, exit 0,
terminating on `VERIFY_DONE`. Outputs in `/tmp/nezreb/`.

```
REF_RUN_DIGEST   3447204b58f5192f772df1a064f0fc87dd59fe41f4720b51f7e6f103403b4928
CAND_RUN_DIGEST  3447204b58f5192f772df1a064f0fc87dd59fe41f4720b51f7e6f103403b4928
RUN_DIGEST_EQUAL         True
STEP_DIGESTS_DIFFERING   0 of 65
REF_TOKEN_MISMATCHES     0
CAND_TOKEN_MISMATCHES    0
PROVENANCE cand=0cb47228c157014468bbf4746727fe70
           base=d1e622691706e565e878eb79fe3ed38b
PROVENANCE worktree_clean=0     (0 dirty files)
```

The two binary MD5s differ, so this is a genuine two-build comparison and not a
binary compared against itself. The 1-ULP fault control from §7.1 -- which flips
64 of 65 step digests while leaving `TOKEN_MISMATCHES` at 0 -- remains the proof
that this instrument can see a difference this small; it was not re-run, because
what it validates is the instrument, and the instrument is unchanged.

One incidental cross-check falls out: the run digest on the new base
`3447204b...` is *the same value* as the run digest measured on the old base in
§7.1. So PR #170 is itself bit-exact on this correctness prompt, and my
candidate is bit-exact on top of it.

### 9.4 `./benchmark.sh --local-submit` re-run on the rebased candidate

`LOCAL_SUBMIT_RC=0`, 168.8 s. Full output `/tmp/nezreb/local_submit.txt`.

```
passed                        : true
passed_correctness            : true
max_abs_diff                  : 0
checked_tokens                : 1025     decode tokens checked : 1023/1023
decode_seconds_per_token      : 0.008881495152492667
decode_speedup                : 1.5601215698763722
passed_decode_speedup_floor   : true
prefill_seconds_per_token     : 0.0011122900390625
prefill_speedup               : 0.330
passed_prefill_speedup_floor  : false
est_score                     : 1.0583623526430868
peak_ram_gb                   : 21
decode_bandwidth_gb_per_token : 0.000000
golden_hash  f49e4c2cbc0d3ceee90195a3a12e1ff082636f8c031587485a9a2c10702b03d2
harness_hash 51c1773772ae8007dcb822042b9a62cb418778fbb7e2dfb1cb4c96e6a4bcffa8
```

Same reading as §7.3 and the same caveat: `passed_prefill_speedup_floor: false`
is the ordinary M4 Pro artifact, because local prefill is scored against the M5
official-runner constant `baseline_prefill_seconds_per_token = 0.000368`, which
this host cannot reach on *any* build including the unmodified base. The floor
that decides the submission is the same-session paired one on the ranked M5.
`golden_hash` and `harness_hash` are unchanged from the pre-rebase run, so the
harness and golden fixture are the same ones §7.3 was measured against.

### 9.5 What was **not** re-taken, and why that is defensible

- **§4 kernel-level ABBA (the load-bearing timing evidence).** Not re-run. It
  measures the two attention kernels in isolation via a standalone Metal
  instrument; PR #170 changes only NVFP4 quantized-matmul kernels, which the
  instrument does not dispatch. Re-running it would resample the same
  distribution at a cost of ~40 minutes of GPU time.
- **§7.5 end-to-end matched ABBA.** Not re-run. Its confidence interval
  (±51 µs/step) is 3.6x the predicted effect, so it was never confirmatory --
  it is a no-regression and kill-threshold check, and §9.4's `passed: true`
  with `max_abs_diff: 0` on the new base discharges the same obligation more
  cheaply. Re-running it on the new base would still be unresolvable.
- **§7.4 adversarial review.** Not re-run. The reviewed diff is byte-identical
  after the rebase (§9.2).

What *was* re-taken is exactly the set of claims that could have changed: the
bitwise certificate (could break if #170 interacted numerically), the harness
pass (could break if #170 changed the golden), and the byte budget (moves with
the base by construction).
