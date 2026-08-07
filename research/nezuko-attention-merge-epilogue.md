# The attention merge epilogue (PR #205, `maple-2026-08-07c-attention-merge-epilogue`)

Student: maple-nezuko. Base `codex/mlxfast-maple-20260804-advisor` @
`1fe609eb920dd96a409f2949a0e901d3bb525af6`. Host: Apple M4 Pro, 20 GPU cores,
`applegpu_g16s`, 48 GiB. Ranked host is M5 Max.

Shipped surface: `Sources/MLXFastModel/LagunaRuntimeModel.swift` only.
Research-only: this file and `research/nezuko_epilogue_probe.swift`.

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

<!-- ABBA_RESULTS -->

## 8. Budget

`./senpai/check-editable-budget.sh 1fe609eb920dd96a409f2949a0e901d3bb525af6`
after the change: `current=2934682 headroom=65318 growth=-454/262144 files=142`.
The change is a net **reduction** of 454 bytes, so it takes nothing from the
shared 65 KB pool that maple-fern also draws on.

Region fence honoured: the diff touches only lines inside the two attention
kernel bodies (`~1466`, `~1593-1662`, `~1923`, `~2094-2163` in the base
numbering). Nothing in `600-1100`, `8525-8910`, `9461-9575` or `10003-10130`.
