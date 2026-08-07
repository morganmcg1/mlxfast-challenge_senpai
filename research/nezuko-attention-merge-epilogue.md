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

### 5.1 Pre-registered expected magnitude

Written **before** the official receipt returns, so the verdict is read against
a stated prior rather than rationalised afterwards.

Per decode step the model runs 30 sliding and 10 full attention layers, so the
§4 kernel measurements project

```
30 x 0.400 us  +  10 x 0.202 us  =  14.02 us/step   (M4 Pro)
```

against a measured M4 candidate decode step of 8881.5 µs/token (§9.4).

**Elasticity correction (advisor note, 2026-08-07T05:56:39Z).** The *physical*
prediction above — 14.02 µs/step removed from the per-step decode cost `T` — is
the pre-registered quantity and is unchanged. The µs→score conversion I first
used was wrong and is superseded here. The scored decode axis is
`decode_seconds_per_token`, and its timing window **includes a full 512-token
seed prefill** (`LagunaRuntimeBenchmark.swift` `measureWorkerDecode(...)`
`:946`, clock start `:966`, `worker.beginDecode(seedTokens:)` `:968`, and the
progress line `:980-:982` which emits `includes_seed_prefill=true`). So

```
D = decode_seconds_per_token = 4 x prefill_seconds_per_token + T
```

and the correct divisor is `D = 4908.372 µs`, not `T = 4143.569 µs`. Removing
1 µs from `T` removes 1 µs from `D`, i.e. `-1/4908.372 = -0.02037 %` of `D`;
score `∝ decode_speedup^0.75 ∝ D^-0.75`, so

```
0.75 x 0.02037 % = 0.015280 % of officialScore per us removed from T
```

This retires both the assignment brief's `0.01464 %/µs` (4.4 % low) and the
floating `0.0181 %/µs` (18.5 % high). It moves this target's ceiling from
+0.685 % to **+0.715 %** (`40 x 1.17 µs = 46.8 µs/step`). Kill thresholds in
§2.5 are stated in µs and are unaffected.

| quantity | value |
|---|---|
| projected decode saving on `T` | 14.02 µs/step |
| relative gain on the scored window `D = 4928.1 µs` | +0.2846 % |
| implied `decode_speedup` change | **+0.2853 %** |
| implied `officialScore` change (`14.02 x 0.015280`) | **+0.2142 %** |
| fraction of the 46.8 µs/step epilogue ceiling | **30 %** |
| *superseded* first estimate (wrong divisor) | ~~+0.118 %~~ |

Two honest caveats on that arithmetic:

1. It assumes the epilogue saving translates ~1:1 into wall-clock decode, which
   requires the attention kernel to be on the critical path and not hidden
   behind other work. Decode is serial and latency-bound, so this is plausible,
   but it is an assumption the kernel-level probe cannot itself test — and the
   end-to-end ABBA (§7.5) could not resolve an effect this small on this host.
2. It is an **M4 Pro** projection. The M5 is a different core count and a
   different bottleneck regime (instruction-bound rather than bandwidth-bound),
   which is the argument for the sign transferring but explicitly *not* an
   argument for the magnitude transferring.

So the pre-registered expectation is a **small positive**: `+0.2853 %` on
`decode_speedup`, `+0.2142 %` on `officialScore`. §11.2 measures the noise
floor of a single cross-session receipt contrast at `sd = 0.3637 %` on
`decode_speedup`, so one receipt sits at roughly **0.8σ** of the predicted
effect — it can bound the effect but cannot confirm it. The pre-registered
reading rule was therefore: a receipt landing anywhere near the frontier is
"not resolved". §11 shows the receipt in fact landed far enough on the *wrong*
side to reject the prediction outright, which is a stronger outcome than the
prior anticipated.

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

---

## 10. Why this target is chain-link, not side-branch

PR #204 merged a hard negative that is worth restating precisely because it
does **not** apply here, and the difference is structural rather than a matter
of degree.

### 10.1 The #204 result and the taxonomy it forces

fern's router-top-8 arm removed 39 GPU dispatches from the decode step. The
emit kernel's own cost was resolved cleanly — `C-B = +37.3 µs` (sd 12.1,
t = 7.6, p = 0.0006). The 39 removed dispatches were **not**:
`A-C = -0.9 µs` (sd 29.7, t = -0.07, p = 0.94), 95 % CI ≈ `[-32, +30] µs`
against a pre-registered −110 µs. A null that tight is not a failure to
measure; it is a measurement that the dispatches cost nothing.

The taxonomy that explains it:

- **Chain-link.** The dispatch is the sole occupant of its barrier-bounded
  interval. Deleting it, or shortening it, saves ~its full duration.
- **Side-branch.** The dispatch is issued inside a much larger sibling's
  concurrency interval, and both feed a common consumer. Deleting it saves
  ~zero, because the consumer was always going to wait for the sibling.

Static predicate: *dispatch X is a side-branch iff every consumer of X also
transitively depends on a sibling Y with duration ≫ X, where Y is issued no
later than X.* fern's kernel was the short arm of a diamond
(`lagunaRoutedSharedDownResidual`, `LagunaRuntimeModel.swift:10100-10130`).
**The short arm of a diamond is free.**

### 10.2 Three independent reasons this target is not that

**(1) I am not deleting a dispatch.** The change shortens the *inside* of
`laguna_sliding_fused_attn_ring_v1` and `laguna_full_fused_attn_grow_v1`. The
dispatch count, grid, threadgroup size and barrier count are all unchanged
(§9.2). There is no sibling for the saving to hide behind, because the saving
is not a sibling — it is a reduction in the length of the critical arm itself.
The side-branch predicate is not even well-formed for it.

**(2) The exposure factor was already measured, and it refutes side-branch
directly.** PR #174 §3.6 measured `E ≥ 0.90` for `sliding_fused_attn_ring_v1`
— that kernel's duration shows up in the step almost 1:1. The contrast in the
same table is decisive: the three kernels that *do* hide
(`gate_sp_h64`, `gate_sp_h48`, `shared_nvfp4_swiglu_qmv_rows1`) sit at
`E = 0.10 [0.00, 0.25]`. My target is at the opposite end of that measured
distribution from the side-branch class.

**(3) The epilogue was measured directly, inside the kernel.** PR #196 §7.1
timed it at 1.068 / 1.072 / 1.170 µs for N = 64 / 256 / 512 — essentially
constant in N, and therefore **12.9 % of a 512-row call**. This is not an
inferred residual; it is the thing itself, on a clock.

### 10.3 What §11 does to that argument

All three statements above remain true, and §11 nevertheless reports a null-to-
negative M5 receipt. That combination is the interesting part of this writeup:
**a kernel can be chain-link by every available static and measured criterion
and still fail to convert an internally-measured saving into step time.** The
side-branch predicate is therefore *sufficient* to explain a null but not
*necessary* — §11.5 sets out the three surviving mechanisms.

---

## 11. The official M5 receipt, and what it says

### 11.1 The receipt

Receipt **`c03dc117-5f3d-4e8f-aa74-a806880be49a`** (short `c03dc11`), dispatched
2026-08-07T05:34:59Z via `research/nezuko_pr205_dispatch_receipt.sh`
(Senpai training `aa29d47b-b349-4d82-9c36-47e43271c681`, exit 0, 1499 s),
`--model "senpai"` accepted on the first attempt with **no fallback**, archive
built from HEAD `4a91cfb`, `submissionCommitSha`
`be504bbafe0630ecba892fc060e0bbd2440de0fe`.

**Correctness was perfect on every gate**, which is the primary thing a
bit-exact change has to prove:

| gate | value |
|---|---|
| `error` | `""` |
| `passed_correctness` | **true** |
| `max_abs_diff` | **0** |
| `checked_steps` / `case_count` | 1344 / 11 |
| `gpqa_ttft_passed` | true (9/9, p50 0.072 s, max 2.3 s) |
| `semantic_gpqa_passed` | true (9/9, judge `claude-opus-4-8`) |
| `passed_decode_speedup_floor` | **true** |
| `passed_prefill_speedup_floor` | **true** |
| `partial_result` | false |
| `peak_ram_gb` | 21 |

`status: rejected`, `rejectionReason: "score did not improve current best"` —
a **ranking** verdict only, with both hard floors passed and no correctness or
error condition. Per the campaign guide, that is exactly the case where the
ranking status must be read separately from the gates.

Timing metrics:

| metric | value |
|---|---|
| `officialScore` | 2.5490802468639 |
| `decode_seconds_per_token` | 0.0049281158828125 |
| `baseline_decode_seconds_per_token` | 0.0138223203125 |
| `decode_speedup` | 2.8047880044191524 |
| `prefill_seconds_per_token` | 0.000190876791015625 |
| `baseline_prefill_seconds_per_token` | 0.000365247314453125 |
| `prefill_speedup` | 1.9135239675274414 |
| `golden_hash` | `be7738fc…7fcf71` |
| `harness_hash` | `18d98ccb…3a058d913` |

### 11.2 A certified noise floor, built from the public corpus rather than from a second receipt

The advisor's instruction was *"take the second receipt to certify rather than
to re-roll"*. Certification is what was needed; a second receipt turned out not
to be the cheapest way to get it, because the ranked leaderboard already
contains **1604 submissions, 1112 of them scored**, and that corpus contains
the null distribution directly. Two independent instruments, `/tmp/nez_noise.py`:

**Instrument A — the baseline arm.** Every session re-times the *same pinned
baseline*. It is identical content by construction, so its cross-session
scatter is a direct measurement of session-draw noise on a fixed workload.
Over all 1112 scored sessions:

```
baseline decode s/tok : mean 0.013855199  sd 0.000033958  cv 0.2451 %
baseline prefill s/tok: mean 0.000372421  sd 0.000007214  cv 1.9370 %
```

A contrast between two independent receipts therefore carries
`0.2451 % x sqrt(2) = 0.3466 %`.

**Instrument B — near-identical candidate pairs.** Among the 503 frontier-class
receipts (`decode_speedup > 2.5`), 322 adjacent pairs agree on
`decode_seconds_per_token` to better than 0.05 % and on
`prefill_seconds_per_token` to better than 0.5 % — i.e. they are the same
scored behaviour re-timed in a different session. Their paired
`decode_speedup` differences have

```
sd 0.3637 %    mean +0.0084 %    n = 322
```

The mean sits on zero, which certifies the instrument; and **0.3637 % agrees
with Instrument A's 0.3466 % to within 5 %**, from completely different data.
The paired `officialScore` null is wider, `sd 0.7846 %`, because it also
carries the prefill baseline draw.

**Consequences for the whole programme, not just this PR:**

| quantity | 1σ on a 2-receipt contrast |
|---|---|
| `decode_speedup` | **0.3637 %** |
| `officialScore` | **0.7846 %** |
| µs/step removed from `T` | **17.92 µs/step** |

The percentage figures are primitive; the µs figure is derived. The conversion
must use the **same divisor as the advisor's corrected elasticity**, namely
`D = decode_seconds_per_token = 4928.12 µs` for this receipt, *not* the decode
window `T = 4164.6 µs`. Removing `X` µs from `T` removes the same `X` µs from
`D`, so `dlog(D) = -X/D`; the `T` divisor would understate σ by 18 %. Hence
`0.3637 % x 4928.12 µs = 17.92 µs/step`.

So **a single ranked receipt cannot resolve anything below ~36 µs/step at 2σ.**
This target's *entire* ceiling is 46.8 µs/step — only 1.3× the two-sigma
resolution of the instrument used to judge it, and *below* the 3σ figure of
53.8 µs/step that a submission would need to clear to be confirmable rather
than merely favourable. Any campaign target in the sub-50 µs class is being
measured with a ruler coarser than the object.

This retires my own earlier "15.15 µs/step / ~30 µs at 2σ" phrasing, which
divided by `T` while converting the prediction with `D`. The %-space verdict in
§11.4 was computed entirely in %-space and is unaffected: `+0.2853 %` predicted
vs `-0.4912 %` observed at `sd 0.3637 %` is a `-2.13σ` residual either way.

Sanity check on the floor: the promoted frontier `97a5090c` and the ranked
anchor `08ddee45` differ by `-0.0727 %` on `decode_speedup` = **−0.20σ**. Two
different sessions of near-identical frontier content land where the null says
they should.

### 11.3 Decomposition of the receipt (mandatory deliverable)

`ns` below is the score renormalised onto pinned calibration
`BD = 0.013890`, `BP = 0.0003845`, i.e. `ns = (BD/d)^0.75 x (BP/p)^0.25`; it
removes the session baseline draw. `S = 512 x 1000 x p` (ms) is the prefill
window and `T = 1e6 x d - 1e3 x S/128` (µs) is the decode step net of the seed
prefill.

| receipt | label | cand dec | base dec | dec speedup | cand pf | base pf | pf speedup | score | `ns` | `T` µs | `S` ms |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `c03dc117` | **PR205 (this)** | 0.004928116 | 0.013822320 | 2.804788 | 0.000190877 | 0.000365247 | 1.913524 | 2.5490802 | **2.591504** | **4164.6** | 97.729 |
| `97a5090c` | promoted frontier | 0.004908372 | 0.013844966 | 2.820684 | 0.000191201 | 0.000382683 | 2.001471 | 2.5888278 | 2.598216 | 4143.6 | 97.895 |
| `08ddee45` | ranked anchor r3 | 0.004916428 | 0.013857607 | 2.818633 | 0.000191382 | 0.000375640 | 1.962778 | 2.5748189 | 2.594408 | 4150.9 | 97.988 |

**vs the promoted frontier `97a5090c`:**

| axis | delta |
|---|---|
| `officialScore` | **−1.5354 %** |
| `ns` (baseline draw removed) | −0.2584 % |
| candidate decode | +0.4022 % (+19.74 µs/step) |
| baseline decode | −0.1636 % *(session draw)* |
| `decode_speedup` | **−0.5636 %** |
| candidate prefill | −0.1694 % |
| baseline prefill | **−4.5561 %** *(session draw)* |
| `prefill_speedup` | −4.3941 % |
| `T` | **+21.0 µs** |

Score decomposition: `0.75 x dlog(decode) = −0.4239 %`,
`0.25 x dlog(prefill) = −1.1234 %`, sum `−1.5473 %` ✓.

**vs the ranked anchor `08ddee45`:**

| axis | delta |
|---|---|
| `officialScore` | −0.9996 % |
| `ns` | −0.1120 % |
| candidate decode | +0.2377 % (+11.69 µs/step) |
| baseline decode | −0.2546 % *(session draw)* |
| `decode_speedup` | **−0.4912 %** |
| candidate prefill | −0.2639 % |
| baseline prefill | −2.7667 % *(session draw)* |
| `prefill_speedup` | −2.5094 % |
| `T` | **+13.7 µs** |

Decomposition: decode −0.3693 %, prefill −0.6354 %.

**Reading, axis by axis:**

1. **73 % of the −1.535 % score drop is the prefill *baseline* draw.** My
   session's baseline prefill ran 4.556 % faster than the promoted session's,
   which mechanically depresses `prefill_speedup` by the same amount. My
   *candidate* prefill was 0.17 % **faster** than the promoted candidate's, and
   I touched no prefill code at all. Against a `1.9370 %` baseline-prefill cv
   (§11.2) a 4.556 % draw is 2.35σ — an unlucky but unremarkable session. This
   is the §4.11.4 phenomenon and it is why `ns` exists.
2. **The decode axis is the real signal, and it is on the wrong side of zero.**
   `decode_speedup` −0.4912 % (anchor) / −0.5636 % (promoted); `T` +13.7 /
   +21.0 µs.

### 11.4 The pre-registered prediction is rejected at 95 %

Against the certified null of §11.2 (`sd = 0.3637 %`):

| | vs anchor `08ddee45` | vs promoted `97a5090c` |
|---|---|---|
| observed `decode_speedup` | −0.4912 % | −0.5636 % |
| in σ | **−1.35σ** | **−1.55σ** |
| 95 % CI on the true effect | **[−1.204 %, +0.222 %]** | [−1.276 %, +0.149 %] |
| pre-registered prediction | +0.2853 % | +0.2853 % |
| prediction inside the CI? | **NO — REJECTED** | **NO — REJECTED** |
| residual vs prediction | **−2.14σ** | **−2.33σ** |
| `officialScore` in σ (null sd 0.7846 %) | −1.27σ | −1.96σ |

Three statements, in decreasing strength:

- **The M4-projected +14.02 µs/step win does not transfer to the ranked M5.**
  The predicted `+0.2853 %` on `decode_speedup` lies outside the 95 % interval
  of the observed effect on *both* reference receipts. This is a resolved
  negative, not a failure to measure.
- **A regression is not established.** The point estimate is −1.35σ and the
  interval still contains zero (just barely, at +0.222 %). Honest reading:
  null-to-mildly-negative.
- **The change is free on every other axis.** Bit-exact (`max_abs_diff: 0`,
  1344 checked steps), both hard floors passed, −454 bytes of budget, no
  dispatch/grid/barrier change. It costs nothing to carry and nothing to drop.

### 11.5 Confound clearance, and why the residual is interesting

**The intervening-merge confound is cleared.** The anchor `08ddee45` measured
tree `ee91466` (post-#137, row-major default OFF). My base is `747d130b`. The
only scored-surface difference is **PR #170**, which touches only
`Vendor/mlx-swift/.../fp_quantized_nax.cpp`, `fp_quantized_nax.h` and
`quantized.cpp` (+295/−4), and whose merged default is
`constexpr const char* kNaxGatherProbeDefault = "";` → probe 0 → in #170's own
words *"leaves both the template argument list and the kernel name
byte-identical to the promoted frontier."* It is a compiled-in no-op on the
shipped default and it is prefill-gather-GEMM scoped in any case. PR #204
(fern's router top-8) is **not** in my base. The decode delta is unconfounded.
Independent empirical support: §9.3 found the `747d130b` logit digest
**identical** to the `1fe609e` digest (`3447204b…4928`), so #170 is bit-exact
on this path too.

That leaves a real residual to explain: the kernel-level ABBA (§4) resolved
V1 at **+0.400 µs** on sliding (95 % CI `[+0.258, +0.564]`) and **+0.202 µs**
on full (`[+0.073, +0.443]`), against a null arm straddling zero on both — and
that saving did not appear in the step. Three surviving mechanisms, in the
order I would test them:

1. **Architecture inversion.** M5 threadgroup memory may not price a `float4`
   store the way M4 does. §2.3's P3 result shows this epilogue is *strongly*
   sensitive to threadgroup access pattern (BDP=32 costs +1.966/+1.820 µs vs
   BDP=33 — an order of magnitude larger than the effect I chased). A subsystem
   that sensitive is exactly the kind that can change sign across generations.
   The campaign already has a precedent for a measured M4→M5 sign inversion.
2. **The saving is real but not on the step's critical path.** `E ≥ 0.90` was
   measured for *the kernel*, not for its epilogue: if the epilogue's last
   round overlaps the next dispatch's setup, shortening it moves nothing.
   This would be a genuinely new taxonomy case — chain-link kernel, side-branch
   *interval within* the kernel — and it is the reason §10.3 says the #204
   predicate is sufficient but not necessary.
3. **The M4 kernel-level ABBA overstates the effect.** It is an isolated-kernel
   harness; occupancy, cache state and clock behaviour differ from the live
   decode step. §12 tests exactly this, on this host, at zero receipt cost.

### 11.6 On the second receipt

The 2-receipt cap was not exhausted; **one receipt was spent**. The remaining
one was deliberately not spent, and the reasoning is part of the deliverable:

- A second receipt of identical content would shrink the contrast σ by `√2`
  (0.3637 % → 0.2572 %), moving the point estimate from −1.35σ to ≈ −1.9σ. That
  would upgrade *"the predicted gain is rejected"* to *"probably a mild
  regression"*. It would not change the disposition of the arm, and it would
  not explain the residual.
- Certification — the thing the advisor actually asked for — was obtained more
  cheaply and with far more power from the public corpus: **n = 322 measured
  null pairs instead of n = 1 replicate**, cross-validated against n = 1112
  baseline-arm sessions.
- The receipt slot is account-wide (one in-flight per benchmark) and costs
  ≈ 44 minutes dispatch-to-verdict. Spending a shared slot for a 0.5σ
  sharpening of an already-answered question is poor stewardship when the
  *unanswered* question (mechanism 3 above) can be attacked on this host for
  zero receipts.

§12 is that zero-receipt attack.

## 12. The zero-receipt end-to-end probe on M4 Pro

### 12.1 Why `--local-iterate` could not answer this

The effect to resolve is `14.02 µs` on a `~8290 µs` M4 decode step — **0.169 %**.
`./benchmark.sh --local-iterate` times only **128** decode steps per ~216 s run,
and §7.4's matched ABBA over 8 full runs returned a 95 % CI of
`[−50.4, +51.6] µs/step`: a half-width **3.6× the effect**. No affordable number
of `--local-iterate` runs closes that gap, because most of its variance is
*between-run* session state, not between-step noise.

The advisor's PR #204 note prescribed the instrument that does work, and I
adopted it verbatim:

- `research/decode_probe.py`, **1200** decode steps per run, per-step spans from
  `time.clock_gettime(CLOCK_UPTIME_RAW)`, first **16** steps dropped as warmup;
- the **run median** is the unit of replication, not the step — this is the key
  choice, because per-step times are heavy-tailed (one run showed a `33.4 ms`
  outlier against an `8.30 ms` median) and the mean is not robust to it;
- **palindromic** arm ordering, so any monotone drift in host state cancels in
  adjacent-pair differences;
- **both binaries built once up front and swapped as files**, so no timed run
  carries a rebuild and the source tree is clean throughout.

Driver: `research/nezuko_epilogue_decode_probe.sh`. Statistics:
`research/nezuko_decode_probe_stats.py` (single session) and
`research/nezuko_decode_probe_pool.py` (pooled across sessions).

### 12.2 Arm-validity certification

The advisor's second methodological requirement was to *certify arm validity*
rather than assume it. Three independent guards, all emitted into the run log:

| guard | session 1 result |
|---|---|
| `SRC_MD5_HEAD` vs `SRC_MD5_BASE` | `eee114e4…` ≠ `917039f5…` — the two arms are genuinely different source |
| `BINARIES_DIFFER` | `1` — and `BIN_MD5_A ba6c5f71…` ≠ `BIN_MD5_B 424f1bd7…`, so the compiler did not fold the difference away |
| `WORKTREE_DIRTY_AFTER_BUILD` | `0` — `Sources/` restored to HEAD before the first timed run |

The script **fails fast** if either the sources or the binaries compare equal,
so an inert arm cannot masquerade as a null result. This is the same failure
mode the advisor flagged in #204, handled statically here.

Independently, §6/§7 already certified arm validity by **fault injection**: a
1-ULP bfloat perturbation of `pair_out0[0]` flips **64 of 65** per-step logit
digests. The edited region is demonstrably live on the scored decode path.

Every one of the 12 timed runs returned `RUN_RC 0` and **0 teacher-forced greedy
divergences**, which is also a 14,400-step bit-exactness check on top of §9.3.

### 12.3 Session 1 — a null, but an *underpowered* null

Sequence `A B B A A B B A A B B A` (A = candidate, B = base), 1200 steps/run,
1184 steps after warmup, `/tmp/nezprobe`.

| run | arm | median µs | run | arm | median µs |
|---|---|---|---|---|---|
| 1 | A | 8282.98 | 7 | B | 8285.98 |
| 2 | B | 8273.81 | 8 | A | 8292.19 |
| 3 | B | 8286.71 | 9 | A | 8267.52 |
| 4 | A | 8256.88 | 10 | B | 8294.02 |
| 5 | A | 8322.77 | 11 | B | 8300.85 |
| 6 | B | 8301.67 | 12 | A | 8307.48 |

Adjacent-pair savings (positive = candidate faster): `−9.17, +29.83, −21.10,
−6.21, +26.50, −6.63 µs/step`.

```
PAIRED n=6  saved mean +2.20 us/step  sd 20.86  se 8.51  t +0.26
PAIRED 95% CI [-19.69, +24.10] us/step   (-0.2375 % .. +0.2907 %)
  pre-registered +14.02 us/step inside CI ?  YES
  zero inside CI ?                           YES (null)
```

This is precisely the outcome the advisor warned about: **the CI contains both
zero and the prediction**, so on its own it discriminates nothing. Resolution
(half-width) is `21.89 µs`, about `1.6×` too coarse. Reporting it as "the M4
end-to-end result is null" would have been the uncertified null that *"is worth
nothing"*.

The fix is cheap and costs no receipts: variance is known (`sd 20.86`), so the
pair count needed for a `< 14 µs` half-width is `n ≈ 6 × (21.89/14)² ≈ 15`.
Session 2 runs a 24-run palindrome (12 further pairs) for **18 pooled pairs**,
projected half-width `≈ 10.4 µs`. Pairing is strictly *within* session and
*between adjacent runs*, so a between-session level shift cannot bias the pooled
mean.

## 13. The mechanism: the isolated harness measured a different machine

This section is the part of the PR I expect to outlive the patch. It is
arithmetic over `LagunaConfig.swift` constants and my own S1 measurement; it
uses no new GPU time and no receipts.

### 13.1 The isolated ABBA harness provably ran cache-resident

Take the sliding kernel exactly as §2.1 measured it: `18.446 µs` per call,
32 threadgroups. Each threadgroup streams the whole 512-position window for its
KV head: `512 x 128 x 2 (K and V) x 2 B (bfloat) = 256 KiB`. Issued reads per
call are therefore `32 x 256 KiB = 8.0 MiB`, of which only
`8 KV heads x 256 KiB = 2.0 MiB` are unique — a 4× cross-threadgroup reuse
factor that follows directly from `slidingAttentionHeads / numKeyValueHeads
= 64 / 8`.

```
8.0 MiB / 18.446 us  =  455 GB/s   effective read bandwidth
M4 Pro peak DRAM bandwidth          273 GB/s
```

**The isolated kernel sustained 1.67× the machine's DRAM peak.** That is not an
interpretation, it is a contradiction: those bytes cannot have come from DRAM.
In a 400-rep ABBA loop the 2.0 MiB working set is SLC-resident after the first
rep, so every subsequent rep is served on-chip. The harness that produced my
`+0.400 µs (+2.51 %)` S4 result was, by its own numbers, benchmarking an
on-chip-throughput-bound kernel.

That single line reframes everything below it.

### 13.2 In situ, the decode step is memory-traffic-dominated

Per decode step at batch 1, from `LagunaConstants` (script `research/nezuko_decode_traffic.py`;
NVFP4 = 4 bits + one E4M3 scale per 16 values = `0.5625 B/param`):

| component | MB/step |
|---|---|
| routed top-8 (39 layers) + shared expert | 592.3 |
| KV cache read (30 sliding + 10 full) | 82.5 |
| dense MLP layer 0 + routers | 135.0 |
| **hard floor, charging attention and `lm_head` nothing at all** | **809.8** |
| attention q/k/v/o at INT8 g32 | 1700.0 |
| attention q/k/v/o at BF16 | 2720.0 |
| `lm_head` at BF16 | 392.0 |

The same accounting reproduces the resident model: `16.45 GB` routed experts +
`2.66 GB` attention + `0.80 GB` head/embed/routers + `0.16 GB` dense and
shared = **20.07 GB** against the ~21.6 GB the brief states, which validates
the parameter model.

Now bound it. The M4 Pro moves at most `273 GB/s x 8290 µs = 2158 MB` in one
measured step. So:

```
hard floor  809.8 MB / 2158 MB  =  37.5 % of peak DRAM bandwidth
```

and *any* configuration that charges attention weights even at INT8 exceeds
100 % of peak — which is impossible, so the true frontier configuration lies
between those bounds. **Per-step DRAM traffic is therefore between 38 % and
100 % of everything the memory system can deliver, and the weight inventory
forces it toward the top of that range.** Decode is memory-traffic-dominated,
and it is dominated by weight streaming, not by arithmetic.

I flag the honest weakness: I did not audit which of the ~200 merged frontier
optimizations reduced attention or head traffic, so I cannot name the exact
fraction. I do not need to. The floor alone — computed while charging the
entire attention stack and the whole vocabulary head *zero* — is already 37.5 %
of peak, and the floor is not reachable.

The corroborating cross-machine ratio is `8290 / 4165 = 1.990`, implying
`543 GB/s` on the ranked M5 Max if both machines are bandwidth-bound. That is
exactly the Max-tier bandwidth class. I deliberately do **not** claim this as
evidence: a 20→40 GPU-core ratio is also ≈2, so the step ratio cannot
discriminate bandwidth-bound from compute-bound. §13.1 does that work alone.

### 13.3 Why this predicts a zero step-level effect, on both machines

The patch removes **zero DRAM bytes**. It removes six threadgroup stores and
six threadgroup loads per thread, i.e. on-chip transactions and
instruction-issue slots. Line up the two regimes:

| | isolated ABBA loop | in-situ decode step |
|---|---|---|
| KV source | SLC (proved: 455 GB/s > 273 peak) | DRAM |
| binding resource | on-chip transaction throughput | DRAM bytes |
| does the patch relieve it? | **yes** | **no** |
| predicted effect | `+0.400 µs/call` ✓ observed | **≈ 0** |

On Apple family-9 GPUs threadgroup memory and the L1/data path are carved from
the same on-chip storage and share ports. Cache-resident, KV loads and my
epilogue's threadgroup traffic contend for that port, so deleting 12 of 16
accesses per thread relieves the binding resource — the measured `+2.51 %`.
DRAM-resident, those ports idle while simdgroups wait on memory, so the same
deletion relieves a resource with slack.

Note also what the patch does *not* save: a `float4` threadgroup access is
512 B per simdgroup-instruction. If the port moves ~128 B/cycle it costs the
same four beats as four scalar accesses. The saving is issue slots, address
generation and bank-conflict windows — never bytes. That is precisely the class
of saving that is worth something when the port is busy and nothing when it is
idle, and it is why the naive "16→4 instructions ≈ 50 ns" estimate
under-predicted the isolated delta by 8×.

**This single mechanism explains all three evidence lines at once** — the
isolated `+2.51 %` win (§4), the M5 receipt's failure to move (§11), and the M4
end-to-end null (§12) — without invoking any M4→M5 architectural difference.
It is also strictly more parsimonious than the "M4→M5 inversion" hypothesis I
carried into §11.5, because it predicts the *same-host* null that §12 measures,
which an architecture-inversion hypothesis cannot.

### 13.4 Consequences for the taxonomy, and for the campaign

§10 asked whether this target is chain-link or side-branch and answered
chain-link on three independent grounds, all of which still hold: the kernel is
not being deleted, `E ≥ 0.90` for the enclosing kernel (PR #174 §3.6), and the
epilogue is 12.9 % of a 512-row call (PR #196 §7.1). Every one of those
statements is true. **They were also insufficient**, and that is the finding.

The #204 taxonomy classifies *dispatches* by concurrency exposure. It has no
term for the case where a dispatch is fully exposed but the resource the change
relieves is not the resource that binds. So the taxonomy needs a second,
orthogonal axis:

> **Exposure** answers *"is this dispatch on the critical path?"*
> **Bound-match** answers *"does this change relieve the resource that binds
> this dispatch, in the regime where it actually runs?"*
>
> A saving reaches the step only if **both** are yes. `E ≥ 0.90` with
> bound-match ≈ 0 is worth exactly as much as a side-branch: nothing.

fern's #204 kernel was `E ≈ 0`, bound-match irrelevant. Mine is `E ≥ 0.90`,
bound-match ≈ 0. Both produce a null; they are different failure modes and they
need different pre-registration checks.

Three rules I would apply to any future decode-kernel assignment:

1. **Residency rule.** If per-step traffic ÷ last-level-cache capacity ≫ 1
   (here `~2 GB / ~35 MB ≈ 60`), a microbenchmark that loops one kernel over a
   fixed buffer characterises a *different machine*. Either sweep the working
   set across `R` independent KV buffer sets until the effect stops depending
   on `R`, or discount the result entirely. The cheap tell costs no runtime:
   divide issued bytes by measured time and compare with DRAM peak. Mine failed
   that check by 1.67× and I did not run it.
2. **Bound-match rule.** Isolated deltas in on-chip-contention resources
   (threadgroup transactions, bank conflicts, L1 port pressure) measured
   cache-resident are *upper bounds* with a prior transfer coefficient near
   zero. Only serial-dependency-latency deltas transfer at roughly `E`. Classify
   the resource before pre-registering a step-level number.
3. **Receipt-floor rule.** §11.2 puts the ranked instrument at
   `17.92 µs/step` (1σ). A submission is confirmable only at about `3σ ≈ 54
   µs/step` — which is **larger than this target's entire `46.8 µs/step`
   ceiling**. This target was unconfirmable by a single ranked receipt *even if
   the mechanism had been perfect*. My `+14.02 µs` prediction was `0.78σ`;
   reaching 80 % power would have taken ~13 receipts. That is a
   go/no-go arithmetic check that costs nothing and should gate every future
   assignment in the sub-50 µs class.

### 13.5 The cheap experiment I would run next, and did not

The strongest remaining discriminator is **not** the `BDP=32` stressor I had
queued. That stressor is confounded — forcing `BDP=32` shrinks the threadgroup
allocation `16,896 → 16,384 B`, which can change occupancy, and its penalty
mechanism (bank-conflict serialisation latency) is not the patch's saving
mechanism (transaction count). Both mechanism (2) and mechanism (3) predict
"step doesn't move", so it separates neither.

The right experiment is a **working-set sweep**: keep the ABBA harness and its
null arm exactly as built, but rotate the kernel across `R` independent KV
buffer sets, sweeping `R x 2.0 MiB` from 4 MB to 512 MB. §13.1 predicts the
`+0.400 µs` delta decays toward zero as the working set crosses the SLC, giving
a dose–response curve at ~`0.1 µs` resolution instead of a `10–20 µs`
end-to-end noise floor — minutes of runtime, no kernel edit, no bit-exactness
risk, no receipt. If the delta *persists* DRAM-resident, §13.1 is wrong, the
per-call saving is real in situ, and the loss is at step level after all.

I am reporting this rather than running it because it is a new instrument
rather than a variation of the assigned arms, and the assignment's remaining
budget is better spent certifying the result I have.
