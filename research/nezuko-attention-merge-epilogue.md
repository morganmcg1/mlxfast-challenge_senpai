# The attention merge epilogue (PR #205, `maple-2026-08-07c-attention-merge-epilogue`)

Student: maple-nezuko. Base `codex/mlxfast-maple-20260804-advisor` @
**`747d130be532383d3eabd190f54f8b1b2bc6f9fd`** (rebased; the assignment marker's
base was `1fe609eb920dd96a409f2949a0e901d3bb525af6`, and sections 1-7 were
measured there -- see §9 for the rebase and the re-verification). Host: Apple
M4 Pro, 20 GPU cores, `applegpu_g16s`, 48 GiB. Ranked host is M5 Max.

Shipped surface: `Sources/MLXFastModel/LagunaRuntimeModel.swift` only, carrying
two independently-flagged mechanisms (Arm A, the merge epilogue, §3–§13; and
Arm E, the full-attention uniform-buffer memo, §14).
Net editable growth **+1 169 bytes** against `747d130b` (§8), well inside the
advisor's revised +12,000-byte cap
(`editable budget OK: current=2950855/3000000 headroom=49145 growth=1169/262144
files=142 (base=142)`).
Research-only: this file, `research/nezuko_epilogue_probe.swift`,
`research/nezuko_epilogue_abba.sh`,
`research/nezuko_pr205_rebase_verify.sh`,
`research/nezuko_pr205_dispatch_receipt.sh`,
`research/nezuko_epilogue_decode_probe.sh`,
`research/nezuko_decode_probe_stats.py`,
`research/nezuko_decode_probe_pool.py`,
`research/nezuko_decode_traffic.py`,
`research/nezuko_pooled_stats.py`,
`research/nezuko_receipt_noise_structure.py`,
`research/nezuko_receipt_corpus.csv` and
`research/nezuko-pr205-submission-note.md`.

---

## Verdict in one box

| axis | outcome |
|---|---|
| what shipped | **two** bit-exact mechanisms in `LagunaRuntimeModel.swift`: **Arm A**, a `float4` merge epilogue in both decode attention kernels (§2); **Arm E**, a uniform-buffer memo that removes ~1,143 of the 1,270 per-call `MLXArray` parameter constructions in the scored window (§14) |
| correctness | **perfect.** Bit-exact by construction; `max_abs_diff = 0` on 1344 checked steps, 11 cases, GPQA TTFT 9/9, semantic judge 9/9, both official floors passed (§6, §7, §9, §11). Arm A + E re-certified from scratch: identical run digest, `0 of 65` step digests differing (§14.4) |
| budget | **+1,169 bytes** net editable growth against base `747d130b`, one submitted file — `9.7 %` of the advisor's 12,000-byte cap (§8) |
| isolated kernel (M4, ABBA, `0.1 µs` resolution) | **wins**: sliding `+0.400 µs/call (+2.51 %)`, full `+0.202 µs/call (+1.11 %)`; residency-robust (§4, §13.6) |
| projected step effect | Arm A `30 × 0.400 + 10 × 0.202 ≈ 14.02 µs/step`, pre-registered before any receipt (§5); Arm E `+11 µs/step` point, `4–20` range, pre-registered before any measurement (§14.3) |
| official M5 receipt (1 of 2 spent, **Arm A only**) | `c03dc117`, `officialScore 2.5490802`, `decode_speedup 2.804788`. Point prediction **rejected at 95 %** (`−1.35σ` vs ranked anchor), but the CI contains zero: **a regression is not established**. `83.2 %` of the score drop sits in the two *baseline* arms (§11, §15.1) |
| in-situ M4 decode, Arm A only, 18 palindromic pairs | `+7.99 ± 8.70 µs/step` — **underpowered null**; combined with the receipt, `+1.86 ± 7.82` (§12) |
| **in-situ M4 decode, Arm A + E, 12 palindromic pairs, quiet host** | **`+18.58 ± 2.92 µs/step`, CI `[+12.16, +25.00]`, `t = 6.37`, 12/12 pairs positive — a resolved effect.** The §14.3 pre-registered kill did **not** fire; the pre-registered `25 µs/step` projection is inside the interval (§14.4) |
| my own explanatory mechanism (§13.1, "the harness was cache-resident") | **pre-registered a discriminator against myself (§13.5) and it refuted me (§13.6)**. Retracted. |
| **status** | **positive on the instrument that can see it, invisible to the instrument that ranks it.** `+18.58 µs/step` projects to `+0.377 %` `decode_speedup` / `+0.283 %` `officialScore`, but §16 certifies the official two-receipt `1σ` at `17.92 µs/step`, so this is a `1.04σ` effect on the ranked axis. **Not a negative result — an unrankable positive one.** |

The reusable outputs are §11.2's **certified programme-wide receipt noise
floor** (1112 baselines, 322 near-identical candidate pairs, two independent
instruments agreeing to 5 %), §16's **proof that the official noise is white**
so same-session pairing buys nothing, §13.2's **decode traffic model**, and
§13.4's **bound-match axis**, which is orthogonal to PR #204's exposure axis.
The programme consequence is in §16.6 and §14.4: single mechanisms in this
size class must be **stacked** until their sum clears `~36 µs/step` before a
receipt is spent on them.

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

### 9.6 The base advanced a *second* time, and this one costs nothing

Checked at 2026-08-07T08:26Z, just before submitting this result. The advisor
branch head moved again, `747d130b -> fe5d843f`, six commits:

```
fe5d843 NAX gather-GEMM: chunk-accurate staged-byte census + K-loop
        register prefetch (#215)
7127f5e Decode marginal-cost ledger: duplicate-injection sweep to
        re-price the whole decode queue (#218)
f20eaac research state: cold-seed-prefill resolved as a negative
0c86fc3 research state: correct score elasticities, record #204's
        side-branch finding
0fd78d5 [maple-fern] T3-2: fuse or DELETE the standalone decode router
        top-8 (185.7 us/step, ~+2.72%) (#204)
444a0a1 research state: record #170 merge and four corrections
```

The rebase obligation this time is **empty**, and that is a checkable claim,
not an assumption:

```
$ git diff --stat 747d130b fe5d843f -- Sources Vendor
$                                       # <- no output at all
$ git diff --stat 747d130b fe5d843f | tail -1
 17 files changed, 5319 insertions(+), 20 deletions(-)
```

All 5,319 lines are under `research/`. **Not one byte of the scored surface
changed.** So every artifact in §9.1-§9.4 carries over unchanged by identity
rather than by re-measurement, and the two receipts in §11 and §17.5 are still
measured against exactly the tree the current frontier compiles.

Re-run against the new base anyway, because they are seconds each:

```
$ ./senpai/check-editable-budget.sh fe5d843f
editable budget OK: current=2950855/3000000 headroom=49145
                    growth=1169/262144 files=142 (base=142)
$ ./senpai/validate-assignment-scope.sh fe5d843f \
      Sources/MLXFastModel/LagunaRuntimeModel.swift
assignment scope OK: 1 submitted path(s) against BASE_SHA=fe5d843f...
$ git merge-tree --write-tree fe5d843f b39d43b
980baa4d5eac4a734f2b46ea2da82b1883e59db9      # clean, no conflict
```

`growth=1169` is bit-for-bit the same number as against `747d130b`, which is
the expected consequence of an empty editable diff. The clean merge-tree is
worth stating explicitly because #204 nominally targets *the same file I edit*
— the standalone decode router top-8 lives in my fenced no-touch region
`:8525-8910` of `LagunaRuntimeModel.swift`. It merged with no code, so there is
nothing there to conflict with, and the region fence held for free.

One observation I will flag as inference rather than fact. Three PRs merged in
this window — #204, #215, #218 — each of which named a concrete decode or
prefill mechanism in its title, and **all three landed as documentation with
zero scored-surface change**. #218 is a measurement study by construction, so
it was never going to ship code. For the other two the code-free merge is the
signature of an arm that was measured and did not survive. If that reading is
right, the frontier's scored surface has now been static across three
consecutive terminal experiments, which is the strongest corroboration the
programme has produced for the receipt-floor rule of §16.6: the remaining
mechanisms are mostly below the instrument's resolution, and the way to make
progress is to certify exactly, not to sample repeatedly.

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

### 12.4 Session 2 and the pooled M4 verdict

Session 2 ran the pre-registered 24-run palindrome
(`A B B A` × 6, `/tmp/nezprobe2`, supervised id `5ed570a4`, 1272 s). Every
guard passed again: `SRC_MD5_HEAD eee114e4…` ≠ `SRC_MD5_BASE 917039f5…`,
`BIN_MD5_A 14106905…` ≠ `BIN_MD5_B 8afd31eb…`, `BINARIES_DIFFER 1`,
`WORKTREE_DIRTY_AFTER_BUILD 0`, all 24 runs `RUN_RC 0`, and all 24 reported
`0 divergences (all match)` — a further 28,800 teacher-forced steps, **52,000+
cumulative across the two sessions**, all bit-exact. (The two sessions' binaries
differ from each other: Swift release builds are not byte-reproducible across
sessions. That is expected, and it is why the guard compares A against B
*within* a session and never across.)

Session-2 run medians (µs): 8274.88 · 8280.65 · 8313.48 · 8276.15 · 8279.42 ·
8309.44 · 8324.79 · 8260.63 · 8286.73 · 8296.17 · 8282.90 · 8261.58 · 8274.29 ·
8315.06 · 8283.77 · 8316.29 · 8297.42 · 8288.62 · 8290.06 · 8260.71 · 8367.50 ·
8266.40 · 8302.38 · 8267.52.

```
SESSION 2  n=12  saved mean +10.88 us/step  sd 43.34  se 12.51  t +0.87
           95% CI [-16.65, +38.42]
POOLED     n=18  saved mean  +7.99 us/step  sd 36.89  se  8.70  t +0.92
           95% CI [-10.36, +26.34]   half-width 18.35 us = 0.0963 % of the step
             pre-registered +14.02 inside CI ?  YES
             zero inside CI ?                   YES  (still a null)
```

The projected half-width was `10.4 µs`; the realised one is `18.35 µs`, because
session 2's per-pair sd (43.3) was twice session 1's (20.9). One pair
(`−101.10`) is a thermal/noise excursion driven by run 21A's 8367.50 median,
the slowest run in either session. **The pooled result is still underpowered and
still a null.**

Secondary robust statistics, **not pre-registered**, reported because the
distribution is visibly heavy-tailed and suppressing them would be selective:

```
median +15.38   10%-trimmed mean +12.32   (trim drops -101.10, -32.52, +40.77, +64.17)
sign test    11/18 positive   one-sided p = 0.2403
Wilcoxon     W+ = 119         one-sided p = 0.0770
bootstrap mean 95% CI [-9.79, +23.22]
```

These lean positive and the Wilcoxon is suggestive, but none of them clears a
threshold, and I am not entitled to promote a secondary statistic over the
pre-registered mean because it reads better. **The honest statement is that 18
pairs of in-situ M4 decode cannot distinguish `+14 µs` from `0`.** For 80 %
power the observed variance implies **55 pairs** against `+14.02 µs` (≈ 94 min
of probe) and **218 pairs** against a half-size `+7 µs` effect (≈ 371 min).

Combining the two independent instruments — with the caveat that they are
different machines and one of them is a single contrast:

```
M4 in-situ  +7.99 +- 8.70 us/step   (n = 18 pairs)
M5 receipt -24.21 +- 17.92 us/step  (n = 1 contrast, sigma from §11.2)
agreement:  z = +1.62  -> the two hosts are NOT statistically distinguishable
combined:   +1.86 +- 7.82   95% CI [-13.48, +17.19]
              zero inside CI: YES     pre-registered +14.02 inside CI: YES
```

This is worth stating plainly because it **weakens** §11.4 rather than
reinforcing it. The M5 receipt alone rejects the `+14.02 µs` point prediction at
95 % (§11.4). The *combined* evidence does not: the pooled M4 point estimate is
positive, and the meta-analytic interval still contains full transfer. What is
established across both instruments is only that **the effect, if it exists,
sits below both instruments' floors** — and that a change with an M4
isolated-kernel win of `+2.51 %` moved neither host's step time measurably.

Two caveats I will not paper over. First, the adversarial review is right that
18 pairs can reject *full* transfer but cannot separate *partial* transfer
(`+5–7 µs`) from zero; ~37 pairs would be needed for that, and I did not run
them. Second, the M5 σ of `17.92 µs/step` is a corpus-derived population figure
(§11.2), not a within-session repeat of my own submission, so the combined
interval inherits that assumption.

Every number in this subsection is reproduced by
`python3 research/nezuko_pooled_stats.py`, which carries both sessions' pair
savings as literals and recomputes the pre-registered mean, the robust
secondaries (exact sign test, exact-enumeration Wilcoxon, 200k bootstrap), the
M5 contrast, the heterogeneity `z`, the inverse-variance combination and the
power table. It takes no arguments and no GPU.

## 13. The mechanism: a traffic model of the decode step, and one refuted hypothesis

This section is the part of the PR I expect to outlive the patch. It is
arithmetic over `LagunaConfig.swift` constants and my own S1 measurement; it
uses no receipts. §13.1–§13.4 were written first and use no new GPU time at
all. §13.5 then pre-registered a discriminator against my own claim and §13.6
reports its result: **26 s of GPU time refuted §13.1.** I have left the
original reasoning in place rather than rewriting history, with a retraction
banner on the subsection that did not survive.

### 13.1 The isolated ABBA harness provably ran cache-resident

> **RETRACTED IN PART — read §13.6 before using this subsection.** The
> bandwidth arithmetic below is correct, but the *inference* I drew from it is
> not. I pre-registered a discriminating experiment (§13.5), ran it (S5), and
> it refuted me: the 4× reuse factor is intrinsic to the kernel's GQA
> structure and is present in situ too, so "the harness was cache-resident and
> the real machine is not" does not follow. §13.2 (traffic arithmetic) and
> §13.4 (the taxonomy rules) survive; §13.1's conclusion and the parts of
> §13.3 that depend on it do not.

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

> **RETRACTED IN PART — see §13.6.** The first row of the table below ("KV
> source: SLC") is exactly what S5 tested and refuted. Everything in this
> subsection that rests on "the isolated loop was cache-resident and the real
> step is not" falls with it. What survives is the *bytes* observation — the
> patch removes zero DRAM bytes — and the closing note that the saving is
> issue slots rather than bytes.

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

### 13.5 The discriminating experiment, pre-registered before it ran

The strongest remaining discriminator is **not** the `BDP=32` stressor I had
queued. That stressor is confounded — forcing `BDP=32` shrinks the threadgroup
allocation `16,896 → 16,384 B`, which can change occupancy, and its penalty
mechanism (bank-conflict serialisation latency) is not the patch's saving
mechanism (transaction count). Both mechanism (2) and mechanism (3) predict
"step doesn't move", so it separates neither.

The right experiment is a **working-set sweep**: keep the ABBA harness and its
null arm exactly as built, but rotate the kernel across `slots` independent KV
slices, sweeping the unique working set from 2 MiB to 64 MiB. §13.1 predicts
the `+0.400 µs` delta decays toward zero as the working set leaves the caches,
giving a dose–response curve at ~`0.1 µs` resolution instead of a `10–20 µs`
end-to-end noise floor — minutes of runtime, no kernel edit, no bit-exactness
risk, no receipt. If the delta *persists* DRAM-resident, §13.1 is wrong, the
per-call saving is real in situ, and the loss is at step level after all.

That is section **S5** of `research/nezuko_epilogue_probe.swift`. It is cheap
enough that it does not compete with the second receipt, so I built it. The
implementation changes residency and nothing else: `dKCache` and `dVCache` are
64 MiB each, one call touches at most 2 MiB of each, and S5 re-binds them at a
rotating 2 MiB offset between dispatches inside the same encoder. Kernel
source, grid, `kReps`, `kRounds` and the ABBA pairing are untouched, the null
arm (a second independent build of the identical source) rides along at every
slot count, and every element of both buffers is the same `bf16` 1.0, so
nothing numerical changes.

**Pre-registration, recorded in the probe source and committed before the run
(commit message `research: S5 pre-registered working-set residency sweep`):**

| hypothesis | claim | prediction at 32 slots (64 MiB) |
|---|---|---|
| **H-onchip** (§13) | the saving is on-chip transaction throughput; at large working sets the kernel is DRAM-bound and V1 relieves a slack resource | `delta ≤ 0.25 × delta(1 slot)`, i.e. **≤ +0.10 µs** on sliding |
| **H-serial** | the saving is serial latency on the threadgroup critical path, independent of where the KV bytes live | `delta ≈ delta(1 slot) ≈ +0.400 µs` |

The two are separated by the **absolute** delta, not the percentage, because
the call time itself grows with the working set: a fixed `+0.4 µs` that becomes
a smaller *fraction* of a slower call is still H-serial, and a delta that
collapses in µs is H-onchip. The null arm's spread at each slot count is the
resolution claim; a delta inside the null spread is not a measurement.

The result is §13.6.

### 13.6 S5 result — my own mechanism is refuted

Supervised run `6167bd06-e97b-4310-9771-f27690aa102a`, exit 0, **26 s** of
wall-clock, `PROBE_RC=0`, against `BASE_SRC_MD5 917039f5a7afd0bd7eb099b222176fb4`
(`git show 747d130b:Sources/MLXFastModel/LagunaRuntimeModel.swift`).

```
kernel   slots  wsMiB    us/call    issGB/s     V1saved [min max]     nullsaved [min max]
sliding      1      2     18.482      453.9  +0.406 [+0.183 +0.497]  +0.011 [-0.127 +0.131]
sliding      2      4     18.746      447.5  +0.404 [+0.154 +0.474]  -0.030 [-0.142 +0.112]
sliding      4      8     19.466      430.9  +0.331 [+0.275 +0.409]  +0.039 [-0.063 +0.100]
sliding      8     16     20.264      414.0  +0.311 [+0.266 +0.425]  -0.013 [-0.066 +0.042]
sliding     16     32     20.238      414.5  +0.361 [+0.255 +0.441]  +0.003 [-0.103 +0.057]
sliding     32     64     19.360      433.3  +0.221 [-0.191 +0.875]  -0.007 [-0.048 +0.144]
full         1      2     15.871      396.4  +0.145 [+0.057 +0.241]  -0.060 [-0.083 -0.035]
full         2      4     18.220      345.3  +0.172 [-0.103 +0.374]  -0.087 [-0.229 +0.888]
full         4      8     19.365      324.9  +0.430 [+0.331 +0.538]  -0.047 [-0.208 +0.051]
full         8     16     20.664      304.5  +0.447 [+0.357 +0.571]  -0.085 [-0.140 +0.029]
full        16     32     21.080      298.5  +0.528 [+0.378 +0.625]  -0.025 [-0.139 +0.046]
full        32     64     21.080      298.5  +0.471 [+0.421 +0.596]  -0.071 [-0.163 +0.214]
```

**The instrument worked.** The rotation really did move the KV out of cache:
the sliding call slows `18.482 → 20.264 µs` (`+9.6 %`) and the full call
`15.871 → 21.080 µs` (`+32.8 %`) with the kernel, the grid and the byte count
per call all identical — the only thing that changed is where those bytes live.
And the null arm — a second independent build of the identical source, paired
the same way at every slot count — stays inside `[−0.087, +0.039] µs` on all
twelve rows, so the resolution is about `0.1 µs` and every `V1saved` figure
above `0.15 µs` is a measurement rather than noise.

**And the pre-registered prediction fails.**

| | sliding | full |
|---|---|---|
| `delta(1 slot)` | +0.406 µs | +0.145 µs |
| `delta(32 slots)` | **+0.221 µs** | **+0.471 µs** |
| ratio | 0.54× | **3.25×** |
| H-onchip predicted | ≤ 0.25× (≤ +0.10 µs) | ≤ 0.25× |
| verdict | **fails** | **fails, with the opposite sign** |

On sliding the delta decays by roughly a sixth over a 16× working-set increase
(`0.406 → 0.361` at 32 MiB) and the only point near the predicted collapse is
the 64 MiB row, whose spread `[−0.191, +0.875]` is the one genuinely noisy cell
in the table. On full the delta does not decay at all — it *triples*, and it is
largest and tightest exactly where the kernel is slowest and least
cache-resident (`+0.528 [+0.378 +0.625]` at 32 MiB).

**So §13.1's inference was wrong, and I am retracting it.** The observation in
§13.1 is still true as a description of the harness: with `kReps = 400`
dispatches over one 2 MiB slice, the S4 measurement re-read a cache-resident KV
cache. What does not follow — and what S5 directly tests and rejects — is the
*inference* that residency is **why** V1 won. Take the residency away and the
win stays. The `455 GB/s > 273 GB/s` contradiction that motivated §13.1 has a
more boring resolution than I gave it: issued bytes are 4× unique bytes because
32 threadgroups share 8 KV heads, and that `64/8 = 8`-way GQA reuse is
**intrinsic to the kernel and present in situ too**, not a property of my
harness. At the largest working set the *unique* DRAM rate is only
`2 MiB / 19.36 µs = 108 GB/s` (sliding) and `2 MiB / 21.08 µs = 100 GB/s`
(full) — 36–40 % of the M4 Pro peak. There was never a bandwidth contradiction
to explain.

**What this does and does not settle.** S5 removed *inter-call* KV residency,
which is the artifact my harness introduced. It did not — and structurally
could not — reproduce the in-situ regime, where the binding resource is the
`≈ 810 MB/step` of MoE and dense weight traffic computed in §13.2, of which the
attention KV stream is `82.5 MB`, about 10 %. So:

- **refuted**: "the S4 win is an artifact of a cache-resident harness";
- **untouched**: §13.2's traffic arithmetic, which is arithmetic over
  `LagunaConstants` and does not depend on S5;
- **untested**: the bound-match form of §13.3/§13.4 — that in situ the epilogue
  relieves a resource which is slack because *weight* traffic binds the step.
  Nothing in S5 puts the GPU under that kind of pressure.

**Where that leaves the experiment.** With §13.1 retracted, the per-call saving
of `+0.4 µs` (sliding) and `+0.15…+0.5 µs` (full) is a real, residency-robust,
`0.1 µs`-resolved effect, and the `30 × 0.400 + 10 × 0.202 ≈ 14 µs/step`
projection is no longer suspect at the per-call end. The simplest reading of
the whole PR is now the least dramatic one: **the effect is probably real and
simply smaller than every instrument I have.** That is exactly what §12.4's
combined estimate says — `+1.86 ± 7.82 µs/step`, an interval containing both
zero and the full `+14.02` — and it is why this experiment is reported as
**inconclusive on timing** rather than as a negative result. I had written §13
as a confident explanation of a negative; the honest correction is that I
explained something that had not been established.

The surviving discriminator is no longer a harness variation. It is either
(a) ~55 more in-situ M4 pairs (§12.4, ≈ 94 min, no receipt), which would resolve
`+14 µs` at 80 % power on this host, or (b) a Metal capture of one real decode
step to measure the attention dispatches' actual exposure — the direct test of
the bound-match hypothesis, and the one measurement that would let #204's
taxonomy and this PR's `bound-match` axis be checked against each other rather
than argued.

---

## 14. Arm E — the full-attention uniform-buffer memo (advisor's §4 target)

Advisor feedback #3 (comment `5213730869`, `feedback_id
pr205-r1-receipt-c03dc11-adjudication-2026-08-07`) §4 proposed a second target
inside the same fence and asked for it in preference to a fourth epilogue
variant. This section verifies the premise, states the mechanism, records the
pre-registration **before** any measurement, and then reports the result.

### 14.1 Premise verification

The advisor located a per-call `MLXArray` construction in
`lagunaFullFusedAttention`. My first grep for it returned nothing, because the
literal is split across three source lines and `MLXArray(\[UInt32` does not
match it:

```swift
// Sources/MLXFastModel/LagunaRuntimeModel.swift, before this arm
lagunaTrace("full fused attention")
let params = MLXArray([
    UInt32(writeIdx), UInt32(writeIdx + 1), UInt32(capacity),
])
```

**Premise confirmed.** The sliding twin at the same position already avoids its
own allocation through `lagunaRingIdxAtlas` (a 512-entry pre-materialised
store, ablation flag `DARKBLOOM_PARAMS_ATLAS`); the full-attention path was
never given the same treatment. Two independent readings of the file — the
advisor's and, earlier and separately, mine — found the same asymmetry, which
is the only reason I did not simply drop it as a plausible-sounding target.

### 14.2 Why an atlas is the wrong shape here, and a memo is the right one

The advisor's suggestion was a 128-entry atlas covering `writeIdx ∈ [512, 640)`
at `capacity = 768`. I did not implement that, and the reason is arithmetic
rather than taste.

The sliding atlas works because the sliding ring has a fixed modulus
(`slidingWindow = 512`), so 512 entries cover *every* reachable index for the
lifetime of the process, and the store can be built once on first touch during
untimed warmup and never rebuilt. The full-attention cache has no fixed
modulus: `capacity = cacheKeys.dim(2)` is whatever the growth policy last
allocated. An atlas therefore has to be keyed on `capacity` as well, and a
per-`capacity` atlas can only be built lazily — which puts its build *inside*
the scored window, because the decode timing window begins at the 512-token
seed prefill (§5.1). Building `capacity` entries to save `10 × 127` lookups is
close to a wash at `capacity = 768`, and a strict loss if the cache grows
twice.

The structure that actually pays is different. All ten full-attention layers
share one cache clock, so **within a single decode step they request the same
`(writeIdx, capacity)` pair ten times**. A single-entry memo keyed on that pair
therefore converts 10 constructions per step into 1 — a 90 % cut — with no
build cost, no capacity assumption, and no dependence on the window being
`[512, 640)`:

```swift
private enum LagunaFullParamsMemoStore {
    nonisolated(unsafe) static var writeIdx = -1
    nonisolated(unsafe) static var capacity = -1
    nonisolated(unsafe) static var entry: MLXArray?
}

let lagunaFullParamsMemoEnabled =
    ProcessInfo.processInfo.environment["DARKBLOOM_FULL_PARAMS_MEMO"] != "0"

private func lagunaFullFusedAttentionParams(
    writeIdx: Int, capacity: Int
) -> MLXArray { /* hit -> cached; miss -> build, eval, store */ }
```

A 128-entry atlas would have removed at most the same 1 270 constructions and
would have paid ≥ 768 of them back at build time. The memo removes 1 143 of
1 270 and pays back nothing. It also degrades gracefully: if a future change
makes the ten layers fall out of lockstep, the memo silently becomes a no-op
instead of becoming wrong.

**Correctness argument.** The memo is keyed on exactly the two integers that
determine the buffer's contents, so a hit returns byte-for-byte the array the
miss path would have built. It is keyed on cache geometry, never on token
values or request identity, which is the same contract the already-merged
`lagunaRingIdxAtlas` operates under and squarely inside the "input-independent
… mask, dequantization, or RoPE caches are allowed" clause of the serial
non-speculative rules. It advances no cache clock, retains no logits and no KV
rows, and survives no request boundary in any observable way. `DARKBLOOM_FULL_PARAMS_MEMO=0`
restores the per-call construction as an ablation control.

### 14.3 Pre-registration (written and committed before any measurement)

**Mechanism priced honestly.** 10 full-attention layers × 127 scored decode
steps = 1 270 constructions; the memo removes 1 143 of them, i.e. **9 per
step**. Each removed construction is one `mlx_array_new_data` allocation of 12
bytes plus its ARC traffic and one fewer leaf node handed to the graph. The
advisor's price was 1–3 µs per allocation (⇒ 10–30 µs/step, +0.15 % to
+0.46 %). I think that is generous for a 12-byte data array on an already-warm
allocator and pre-register a wider, lower band:

> **Pre-registered prediction: the memo removes 4–20 µs/step, point estimate
> 11 µs/step.** On the corrected §5.1 elasticity (0.015280 % of `officialScore`
> per µs/step) that is **+0.06 % to +0.31 %, point estimate +0.17 %**.

**Pre-registered power statement, stated before the measurement so it cannot be
retrofitted.** From §11's certified noise floor, a two-receipt contrast on the
`T` axis has σ = 17.92 µs/step, so 11 µs/step is **0.61σ** — an official
receipt *cannot* resolve this arm, exactly as it could not resolve the
epilogue. The zero-receipt in-situ M4 probe of §12 has se ≈ 8.7 µs at 18 pairs
and ≈ 12.5 µs at 12 pairs, so 11 µs/step is 0.9–1.3σ there too. **I am
therefore pre-registering that neither available instrument is expected to
resolve this arm on its own, and that the arm will be reported on the combined
mechanism** (epilogue + memo, predicted 14.02 + 11 = **25 µs/step**), which is
1.4σ on the receipt axis and 2.0σ on a 12-pair M4 probe.

**Pre-registered kill.** If the in-situ probe's combined estimate is negative
with an upper CI bound below +5 µs/step, I report the memo as a null and do not
dispatch a receipt.

**What is *not* conditional on any of this.** The memo is bit-exact by
construction, costs 1 169 bytes of the 12 000-byte cap, strictly removes work,
and carries its own ablation flag. Its value does not depend on the timing
verdict, and neither does the §14.2 correction to the advisor's proposed shape.

### 14.4 Result — the combined mechanism is resolved on the M4 in-situ axis

Correctness first. Arm A + Arm E were re-certified from scratch against the
`ref-base` reference digest (training `8de1ecad-e10b-48d9-ae2c-fc27092aa4c8`,
`finished`, 336.9 s):

```text
REF_RUN_DIGEST  3447204b58f5192f772df1a064f0fc87dd59fe41f4720b51f7e6f103403b4928
CAND_RUN_DIGEST 3447204b58f5192f772df1a064f0fc87dd59fe41f4720b51f7e6f103403b4928
RUN_DIGEST_EQUAL True ; STEP_DIGESTS_DIFFERING 0 of 65 ; TOKEN_MISMATCHES 0 / 0
LOCAL_SUBMIT_RC=0   VERIFY_RC=0
```

The same 1-ULP control that flips 64 of 65 step digests (§6) still fires, so
the instrument was live for this certification, not merely silent.

Then timing. Session 3 of the in-situ decode probe ran the combined `A + E`
candidate against the unchanged `747d130b` base, 24 runs, 1200 steps each,
`SEQ = A B B A A B B A A B B A A B B A A B B A A B B A` (12 palindromic
pairs), training `14549334-92b6-4cf0-aab6-49f46b9cc8d7`, `PROBE_RC=0`.
Provenance emitted by the script itself:

```text
SRC_MD5_HEAD 192a0d29066f202c67fb4354e20e3a97   SRC_MD5_BASE 917039f5a7afd0bd7eb099b222176fb4
BUILD_A_RC 0  BIN_MD5_A 1cddf80ef71846e2c93df80e382e3f1a
BUILD_B_RC 0  BIN_MD5_B 1e8f9699ef112d7169fd669b91c2a083
BINARIES_DIFFER 1   WORKTREE_DIRTY_AFTER_BUILD 0
```

All 24 runs reported `0 divergences (all match)` against the golden.

```text
arm A (candidate) n=12 median-of-medians 8278.57 us  sd 12.32
arm B (base)      n=12 median-of-medians 8296.31 us  sd 12.61
pairs: +24.23 +22.79 +16.38 +43.98 +1.23 +9.60 +15.65 +22.42 +16.67 +17.63 +14.90 +17.50
PAIRED n=12  saved mean +18.58 us/step  sd 10.11  se 2.92  t +6.37
PAIRED 95% CI [+12.16, +25.00] us/step   (+0.1465 % .. +0.3014 % of 8296 us)
resolution of this probe (CI half-width) 6.42 us/step
```

Twelve of twelve pairs are positive (sign test `p = 2^-12 = 0.000244`); the
paired `t = 6.37` on 11 df gives `p ~ 5e-5`. The per-run scatter (`sd 10.11`)
is four times tighter than session 2's `43.34`, so the host was quiet; that
is why this session resolves what the earlier eighteen pairs could not. The
median-of-medians difference (`17.74 µs`) agrees with the paired mean
(`18.58 µs`), so no single run is carrying the result.

Three things follow.

1. **The §14.3 pre-registered kill did not fire.** It required the combined
   estimate to be negative with an upper CI bound below `+5 µs/step`. The
   observed interval is `[+12.16, +25.00]`, entirely above zero.
2. **The pre-registered projection is inside the interval.** §14.3 predicted
   `14.02` (Arm A) `+ 11` (Arm E) `= 25 µs/step`; the Arm A-only projection
   alone was `14.02`. Both sit inside `[+12.16, +25.00]`, with `25` at the
   upper edge.
3. **Advisor hypothesis (b) is disfavoured.** Feedback #3 §2 asked me to
   separate "(a) the receipt was dominated by something else" from "(b)
   `float4` is actively harmful". For (b) to survive, Arm E would have to be
   carrying the whole `+18.58` while Arm A contributes nothing or less — that
   demands `E >= 18.58 µs/step`, above my pre-registered point (`11`) and at
   the extreme of the pre-registered `4-20` range. Combined with the Arm
   A-only pooled estimate of `+7.99 ± 8.70` from sessions 1-2 (§12.4), which
   is positive, and with §15.1's finding that `83.2 %` of the receipt's score
   drop sits in the two *baseline* arms, (a) is the better-supported reading.

The cross-session contrast that would isolate Arm E is
`18.58 − 7.99 = +10.6 ± 9.2 µs/step` (`z = 1.15`) — numerically right on the
pre-registered `11 µs/step` point, but underpowered and confounded by the
session-to-session quiet-host difference, so I do not claim it. Arm E is
reported as *bundled and not separately attributable*, exactly as §14.3 said
it would be.

Score projection from the resolved combined number, using the §15 elasticity
with divisor `D = decode_seconds_per_token = 4928.12 µs`:

```text
dD/D = 18.58 / 4928.12         = +0.3770 %  on decode_speedup
x 0.75                          = +0.2827 %  on officialScore
```

which is `0.01522 %` of `officialScore` per µs/step, matching the advisor's
independently derived `0.015280 %`. Against the ranked anchor `08ddee45`
(`decode_speedup 2.818633`) the refined point prediction is
`2.818633 x 1.003770 = 2.82926`, inside the §17.2 pre-registered interval
`[2.8127, 2.8532]`. I am *not* revising §17.2; that prediction was fixed
before this measurement and stands as written.

The honest limit remains §16: `18.58 µs/step` is `1.04σ` on the two-receipt
official axis (`σ = 17.92 µs/step`). This mechanism is now resolved on the
instrument that can see it and invisible to the instrument that ranks it.

---

## 15. Reconciliation with advisor feedback #3 (comment `5213730869`)

Four items. Two are the analysis the advisor asked for; two are corrections I
owe back.

### 15.1 The requested `T`-axis decomposition (advisor §1)

The advisor asked for the raw `officialMetrics` of receipt `c03dc11` and for
`T = (128·D − S)/128` with `S = 512 × prefill_seconds_per_token`. That
expression simplifies to `T = D − S/128`, which is algebraically identical to
the formula already used in §11.3, so the numbers below are the §11.3 numbers
rather than a new computation. Raw metrics, as requested (only the submitter
can read these):

```
c03dc11  officialScore                      2.5490802468639
         decode_seconds_per_token           0.0049281158828125
         baseline_decode_seconds_per_token  0.0138223203125
         decode_speedup                     2.8047880044191524
         prefill_seconds_per_token          0.000190876791015625
         baseline_prefill_seconds_per_token 0.000365247314453125
         prefill_speedup                    1.9135239675274414
         timestamp                          2026-08-07T05:44:58Z
```

`D = 4928.1159 µs`, `S = 512 × 190.8768 µs = 97 728.9 µs`,
`T = 4928.1159 − 763.5072 = 4164.61 µs`.

| receipt | label | `D` µs | `S` ms | **`T` µs** |
|---|---|---|---|---|
| `c03dc117` | PR #205 (this arm) | 4928.116 | 97.729 | **4164.6** |
| `97a5090c` | promoted frontier | 4908.372 | 97.895 | **4143.6** |
| `08ddee45` | ranked anchor r3 | 4916.428 | 97.988 | **4150.9** |

`ΔT = +21.0 µs` vs the frontier and `+13.7 µs` vs the anchor, against a
pre-registered `−14.0 µs`.

**Separating the advisor's (a) from their (b).** Decomposing the `−1.5473 %`
log-score change against the frontier into its four independent factors:

| factor | log contribution to `officialScore` | share |
|---|---|---|
| `baseline_prefill` session draw | **−1.1656 %** | **75.3 %** |
| `baseline_decode` session draw | **−0.1228 %** | **7.9 %** |
| candidate prefill | +0.0424 % | — |
| candidate decode | −0.3010 % | 19.5 % |
| **total** | **−1.5473 %** | |

**83.2 % of the drop sits in the two baseline arms** — quantities measured by
running the *unmodified baseline binary*, which a change confined to two decode
attention kernel bodies cannot influence by construction. The baseline prefill
draw alone was `−4.5561 %`, which is `2.35σ` against the certified
`baseline_prefill` cv of `1.9370 %` (§11.4, n = 1112): an unusual draw, but an
unusual draw in a quantity I do not touch.

That is the advisor's explanation (a), and it is quantified rather than
asserted. On explanation (b) — `float4` staging actively harmful — the
appropriate instrument is the paired `decode_speedup`, which cancels
session-level host drift: `−0.4912 %` vs the anchor, `−1.35σ` against the
certified two-receipt contrast sd of `0.3637 %`, **95 % CI
`[−1.2040 %, +0.2216 %]`, which contains zero**. Harm is not established.

Two further reasons (b) is structurally implausible, both free of receipts:

- The rewrite does not add live values. The same four output planes are in
  registers either way; `float4` staging changes only how they transit
  threadgroup memory (8 stores + 8 loads → 2 + 2). Threadgroup footprint is
  byte-identical at 16 896 B, so no occupancy limit moves.
- S5 (§13.6) measured V1 directly at `0.1 µs` resolution across six
  working-set sizes spanning 2–64 MiB, on both kernels: `+0.22…+0.41 µs`
  (sliding) and `+0.15…+0.53 µs` (full), positive on all twelve rows, with the
  null arm inside `[−0.087, +0.039] µs`. A register-pressure regression would
  have to be M5-specific *and* invert a sign that is stable across a 32×
  residency sweep on M4.

**Conclusion on §1/§2.** The receipt is consistent with the mechanism being
worth roughly zero at step level and is *not* consistent with the pre-registered
`+0.29 %`; it does not establish harm. I have followed the instruction not to
re-roll it, not to try a `float2`/`half4` variant, and not to spend the last
receipt confirming it.

### 15.2 Correction owed back: the `−3σ` is a `−2σ` (advisor §1)

The advisor scored `−1.53 %` as "roughly −3σ against the pooled `officialScore`
cv of 0.489–0.553 %". I can reproduce where that cv comes from and I believe it
is right — but it is the **single-draw** sd, and the comparison is a **contrast
of two draws**.

Propagating my §11.4 baseline-arm measurements through the score definition:
`0.75 × 0.2451 % = 0.1838 %` from `baseline_decode` and
`0.25 × 1.9370 % = 0.4843 %` from `baseline_prefill`, in quadrature
`√(0.1838² + 0.4843²) = 0.518 %` — squarely inside the advisor's
`0.489–0.553 %`. The promoted frontier's `2.58882784` is itself one draw, not a
population mean, so the difference of the two carries `√2 ×` that:

> **contrast sd = `√2 × 0.518 % = 0.733 %`.**

This is confirmed by direct measurement rather than propagation: §11.5's
Instrument B took 322 pairs of near-identical candidates from the public corpus
and measured a paired `officialScore` delta sd of **`0.7846 %`**. Two
independent routes, agreeing to within 7 %.

`−1.5354 % / 0.7846 % = ` **`−1.96σ`**, not `−3σ`. It is a two-sigma event,
right at the edge of 95 %, and — per §15.1 — five sixths of it lives in an arm
my change cannot reach.

I flag this specifically because it is the same class of divisor error the
advisor themselves corrected in feedback #2 item 1 (dividing by `T` rather than
by `D` for the decode elasticity). Using a single-arm sd to score a two-arm
contrast understates the interval by `√2`; it is an easy slip and I have almost
certainly made it elsewhere. The programme-level consequence is in §11.6: **a
two-receipt contrast on this benchmark resolves `17.92 µs/step` at 1σ, so
3σ ≈ 54 µs/step — larger than this target's entire `46.8 µs/step` ceiling.**
That is the single most transferable number in this PR and it depends on
getting the `√2` right.

### 15.3 Correction owed back: Step 0 was done first (advisor §3)

The advisor wrote "You skipped the mandatory Step 0, and that is the whole value
of this PR." Step 0 was in fact the *first* thing done and is **§2 of this
document** — §2.1 S1 duplication pricing, §2.2 the P2 barrier price, §2.3 the
P3 `BDP` padding sweep, §2.4 the P4 reciprocal hoist (which turned up that MLX
JIT compiles Metal with fast-math **off**), and §2.5 the explicit evaluation of
the pre-registered kill. It was committed at `45fcc44`
("research: Step 0 epilogue decomposition probe"), which is the first research
commit on the branch and precedes commit `1aad492`, the Arm A implementation.

The reason the advisor could not see it is mechanical, not disputable: **the
remote branch is still at the assignment marker `31ffc91`.** Every commit on
this branch — twenty-two of them at time of writing — is local. Publishing them
is precisely what the typed `submit_result` transition does, and this is the
first submission. A review of `origin/maple-nezuko/attention-merge-epilogue`
before that transition necessarily shows an empty branch.

I record this not to argue but because the inference the advisor drew from it —
that I ran arms without decomposing first — would, if it stood, misprice how
much of the epilogue family this PR actually closes. §2.5 is the part I would
most like read: it explains why the pre-registered kill did **not** fire, why
Arm B (drop a barrier) is dead, why Arm C (registers) is structurally
impossible, and why a one-round collapse cannot fit
(33 280 B > 32 768 B of threadgroup memory). Together with §13.6, the epilogue
family is closed: the per-call effect is real and residency-robust at
`~0.4 µs`, and its step-level projection is below every instrument available on
this programme.

### 15.4 The last receipt (advisor §7)

I took option (i) — the §4 target — but implemented it as a memo rather than an
atlas, for the arithmetic reason in §14.2, and I pre-registered in §14.3 (before
measuring) that **neither instrument is expected to resolve it alone**: `11
µs/step` is `0.61σ` on the receipt axis and `0.9–1.3σ` on the in-situ M4 probe.
The receipt decision is therefore conditional on §14.4 and on the operational
gate in advisor §6(a) — `mlxfast submissions | tail -3` must show a terminal
last row, since the in-flight limit of 1 is shared with the birch campaign, and
`mlxfast submit` exits 0 even when it refuses, so its stdout must be parsed for
a submission id.

---

## 16. Programme finding: the official M5 noise is white, so paired receipts buy nothing

This section exists because I nearly reported the opposite. It is included in
full, including the false alarm, because the correction is the useful part.

### 16.1 The observation that started it

Pulling the receipt corpus after my own receipt landed, I noticed two receipts
23 minutes apart whose `officialScore` differed by only 0.012 %:

| receipt | `createdAt` (UTC) | `officialScore` | solver | `submissionCommitSha` |
| --- | --- | --- | --- | --- |
| `26b8e82a` | 2026-08-07T06:26:46 | 2.562538 | `morganmcg1` | `0b5372f5` |
| `0bc3eb4c` | 2026-08-07T06:49:45 | 2.562223 | `morganmcg1` | `5164d313` |

0.012 % is *sixty-five times tighter* than the 0.7846 % contrast sd I certified
in §11.5. The tempting inference is that the M5 host drifts slowly, that most
of my 0.7846 % is between-session drift rather than within-session noise, and
therefore that two receipts dispatched back to back would resolve far more than
§11.6's table claims. If true that would be a programme-level result: it would
cut the 17.92 µs/step receipt resolution substantially and make this whole
target reachable in two receipts instead of thirteen.

It is not true. I tested it before writing it down.

### 16.2 The right instrument for the question

`officialScore` is the wrong series to test drift on, because consecutive
receipts carry *different candidates*, so a score difference confounds
measurement noise with a genuine difference in the thing being measured. Two
receipts landing 0.012 % apart may simply be two candidates that are genuinely
almost equally fast.

The corpus contains a clean instrument for this and only this. Every receipt
times an **unmodified baseline binary** in the same session and publishes
`baseline_decode_seconds_per_token` and `baseline_prefill_seconds_per_token`.
That binary is constant across all 1 115 receipts and across two weeks. There
is no candidate signal in those two series at all: every bit of their variation
is measurement noise. This is the same instrument A I used in §11.5, now asked
a different question.

### 16.3 The variogram

If the noise is independent across receipts, the expected squared difference
between any two receipts is `2*sigma^2` **regardless of how far apart in time
they ran**. If the host drifts, near-in-time pairs are closer than far-apart
pairs. Binning all 620 000-odd receipt pairs by elapsed time and reporting the
semivariance as an implied sd, against the marginal sd of the whole series:

`baseline_decode` — marginal sd 3.39457e-05 s/token (cv 0.2450 %):

| gap bin | pairs | implied sd | vs marginal |
| --- | ---: | ---: | ---: |
| < 15 min | 1 173 | 3.44924e-05 | 101.6 % |
| 15–60 min | 4 196 | 3.35013e-05 | 98.7 % |
| 1–4 h | 16 338 | 3.36811e-05 | 99.2 % |
| 4–24 h | 89 407 | 3.43008e-05 | 101.0 % |
| 1–7 d | 415 269 | 3.42391e-05 | 100.9 % |
| > 7 d | 94 672 | 3.23367e-05 | 95.3 % |

`baseline_prefill` — marginal sd 7.20954e-06 s/token (cv 1.9359 %):

| gap bin | pairs | implied sd | vs marginal |
| --- | ---: | ---: | ---: |
| < 15 min | 1 173 | 7.10747e-06 | 98.6 % |
| 15–60 min | 4 196 | 7.14787e-06 | 99.1 % |
| 1–4 h | 16 338 | 7.13194e-06 | 98.9 % |
| 4–24 h | 89 407 | 7.21257e-06 | 100.0 % |
| 1–7 d | 415 269 | 7.23105e-06 | 100.3 % |
| > 7 d | 94 672 | 7.12903e-06 | 98.9 % |

The variogram is **flat**. Across a time-gap range spanning three orders of
magnitude — fifteen minutes to two weeks — the implied sd never moves more than
about 2 % away from the marginal sd on either axis. There is no nugget, no
rising limb, no sill below the marginal variance. This is the signature of
white noise.

### 16.4 The direct back-to-back test

The variogram is a pooled statistic, so I also ran the test in the form the
programme would actually use: difference each receipt against the one that ran
immediately before it, which is the strongest practical approximation to "run
the pair back to back". 88.2 % of adjacent receipt pairs in this corpus ran
within 30 minutes of each other (median gap 10.0 min, p25 4.0, p75 19.3), so
this is a real back-to-back sample, not a hypothetical one.

| series | n | adjacent-delta sd | i.i.d. prediction `sqrt(2)*sd` | ratio | lag-1 `r1` |
| --- | ---: | ---: | ---: | ---: | ---: |
| `baseline_decode` | 1 114 | 4.71317e-05 | 4.80065e-05 | **0.9818** | **+0.0368** |
| `baseline_prefill` | 1 114 | 1.02516e-05 | 1.01958e-05 | **1.0055** | **−0.0110** |

Restricting to genuinely tight gaps does not help either:

| max gap | n | delta sd | as % of i.i.d. |
| --- | ---: | ---: | ---: |
| ≤ 15 min | 708 | 4.85466e-05 | 101.1 % |
| ≤ 30 min | 983 | 4.73685e-05 | 98.7 % |
| ≤ 60 min | 1 071 | 4.69380e-05 | 97.8 % |

Lag-1 autocorrelation is +0.037 and −0.011. With n = 1 114 the standard error
on `r1` is about 1/sqrt(n) = 0.030, so the decode value is +1.2σ and the
prefill value is −0.4σ. Neither is distinguishable from zero. Pairing removes
between 0 % and 2 % of the variance, i.e. nothing.

### 16.5 So what were those two receipts?

A coincidence, and not even a rare one. Across the 1 114 adjacent pairs in the
corpus, **16 of them (1.44 %) differ by less than 0.020 % in `officialScore`**.
The distribution of adjacent |Δ| is p10 0.146 %, median 0.789 %, p90 3.223 %.
Seeing one 0.012 % pair among 1 114 draws is exactly what the null predicts;
finding it *after* looking through the tail is not evidence of anything. The
two receipts also carry different `submissionCommitSha` values (`0b5372f5` vs
`5164d313`), so they are not even a byte-identical repeat.

Incidentally, the median adjacent |Δ| of 0.789 % is an independent
corroboration of §11.5's paired contrast sd of 0.7846 %: for a zero-mean normal
the median |Δ| is 0.6745σ, so a median of 0.789 % implies σ ≈ 1.17 % for
adjacent pairs that include real candidate differences — comfortably above the
pure-noise 0.78 %, which is what it should be, since these pairs *do* contain
candidate signal.

### 16.6 Consequence for the programme

The resolution table in §11.6 stands **unchanged, and is now certified rather
than assumed**:

- A two-receipt contrast resolves 0.3637 % on `decode_speedup`, 0.7846 % on
  `officialScore`, and **17.92 µs/step removed from the per-step decode cost T**
  at 1σ.
- Dispatching an A/B pair back to back does **not** improve this. There is no
  session structure to cancel. The only way to buy resolution on the ranked
  instrument is more receipts, and it costs `n` receipts to gain `sqrt(n)`.
- 3σ on the receipt axis is 53.8 µs/step, which remains **larger than this
  target's entire +46.8 µs/step ceiling** (§5.1). No single-mechanism attention
  epilogue experiment on this target is decidable by the ranked instrument. That
  was true before this section and it is still true; what changed is that the
  one obvious escape route — cheap pairing — is now closed by measurement
  rather than left open by assumption.

The practical rule I would hand to the next student: **do not spend a receipt
to measure something smaller than about 50 µs/step, and do not expect back-to-
back dispatch to rescue you.** Spend receipts to *certify* a mechanism whose
size you already established on a cheaper instrument, or to check correctness
and the floors, which the receipt does perfectly and for free.

### 16.7 Where the current frontier sits

For the advisor's ranking context, the corpus best at the time of writing is
`f2b7cccd` at `officialScore` 2.597875 (2026-08-07T03:06:28Z). This is
consistent to seven digits with the `improved: −0.048795` field on my own
receipt `c03dc117` (2.549080 + 0.048795 = 2.597875), which confirms both that
`improved` is measured against the live best and that no better receipt landed
between my dispatch and this analysis. My receipt is 1.88 % below that best,
essentially all of it the −1.1656 % baseline-prefill draw and −0.3010 %
candidate-decode draw decomposed in §15.1 — not a deficit in the shipped
mechanism.

Reproduce with `python3 research/nezuko_receipt_noise_structure.py`, which
takes no arguments, needs no GPU, and reads the corpus snapshot committed
alongside it.

---

## 17. Pre-registration for the second and last receipt

Written and committed **before** the §14 in-situ probe finished, so nothing
below is fitted to its result. The probe was already running when this was
written; the only probe output I had seen at that point was the median of four
individual `A` runs, which carries no A-versus-B contrast at all.

### 17.1 What a second receipt can and cannot buy

§16 removes the last hope of cheap resolution: the ranked instrument resolves
**17.92 µs/step at 1σ**, pairing does not help, and that number is now
certified rather than assumed. So I want to be explicit about what I am and am
not buying, because the advisor's §7 correctly warned that "a third epilogue
arm is not a good outcome".

**Cannot buy: resolution of Arm E.** Arm E alone is predicted at 11 µs/step
(§14.3). Receipt #2 minus receipt #1 differs by exactly Arm E, which is
`11 / 17.92 = 0.61σ`. That contrast is undecidable and I am not going to
pretend otherwise.

**Cannot buy: resolution of the combined mechanism either.** Arm A + Arm E is
predicted at 25 µs/step = `1.4σ` against the anchor. A 1.4σ result is not a
finding in either direction.

**Can buy, and this is the real reason: official correctness certification of
Arm E.** Arm E introduces the only stateful object I have added anywhere in
this PR — a process-lifetime memo keyed on `(writeIdx, capacity)`. Its one
credible failure mode is a **stale hit**: the memo returning a buffer built for
a different cache geometry. My local instrument is a single 64-step
teacher-forced case on one prompt, in which `capacity` very likely never
changes at all, so it is close to blind to precisely this bug. The official
stack runs **1 344 checked steps across 11 cases** of differing lengths, plus
hidden anchors, free runs, GPQA behaviour and a semantic judge. That is the
instrument that actually exercises cache-capacity growth. §16.6's own rule
says receipts are excellent at correctness and floors and bad at small timing
deltas; this is the correctness case.

**Can buy, secondarily: a second draw on the score axis.** Receipt #1 landed
at `−0.4912 %` on `decode_speedup` against the ranked anchor, `−1.35σ`, with a
CI containing zero. One more draw does not settle it, but it does discriminate
the two hypotheses the advisor separated in their §2, and it does so
asymmetrically — see §17.3.

### 17.2 Point predictions

Elasticity from §5.1: removing `X` µs/step from the per-step decode cost raises
`decode_speedup` by the fraction `X / D` with `D = 4928.12 µs`. The ranked
anchor `08ddee45` contains my base tree and neither of my arms, so it is the
correct reference for the combined mechanism.

| quantity | prediction |
| --- | --- |
| `passed_correctness` | `true`; `max_abs_diff` exactly `0`; both floors `true`. I put **P(correctness failure) < 2 %**; if it fails, Arm E is broken and the finding is the bug. |
| combined mechanism | `25 µs/step` ⇒ `+0.507 %` on `decode_speedup` vs anchor |
| `decode_speedup` | **2.8329**, 1σ = 0.3637 % ⇒ 95 % CI **[2.8127, 2.8532]** |
| `officialScore` | it will **not** beat the corpus best of 2.597875 (§16.7); the receipt will come back `rejected` for ranking and that is expected, not a failure |
| what would falsify the mechanism | `decode_speedup` below 2.8084, i.e. a second draw as low as the first |

### 17.3 The decision rule, fixed in advance

Let `d2` be receipt #2's `decode_speedup` and let the anchor be 2.818633.

1. **Correctness fails** (`passed_correctness: false`, `max_abs_diff > 0`, a
   floor breached, or a non-empty `error`) → report **Arm E is broken**,
   recommend reverting Arm E only, and keep Arm A on the strength of receipt
   #1's perfect correctness record. This outcome dominates all the others.
2. **`d2 ≥ 2.818633`** (at or above the anchor) → receipt #1's low draw is not
   reproduced. The two-draw candidate mean against the anchor has contrast sd
   `sqrt((0.3637/sqrt(2)/sqrt(2))^2 + (0.3637/sqrt(2))^2) = 0.315 %`, and the
   mean would sit at about `−0.25 %` = `−0.78σ`. Report **no evidence of harm;
   both mechanisms are free on the ranked instrument**, which is the advisor's
   hypothesis (a).
3. **`2.8084 ≤ d2 < 2.818633`** → a second mildly low draw. Two-draw mean near
   `−0.4 %` = `−1.3σ`. Report **still inconclusive, leaning free**; do not
   claim harm; recommend the advisor treat both arms as byte-cheap and
   correctness-clean but timing-unproven.
4. **`d2 < 2.8084`** → two independent low draws. If the two-draw mean against
   the anchor is below `−0.63 %` (2σ on the 0.315 % contrast sd), report a
   **real regression** and recommend reverting **Arm A**, which is the only arm
   large enough to produce it. This is the outcome in which I tell the advisor
   my own shipped change is harmful, and I am writing the threshold down now so
   that I cannot move it later.

### 17.4 Gate conditions before dispatch

Dispatch happens only if **all** of these hold, and is skipped entirely
otherwise:

- the §14.3 pre-registered kill has **not** fired (probe's combined estimate
  negative with an upper CI bound below +5 µs/step);
- Arm E is bit-exact locally — `REF_RUN_DIGEST == CAND_RUN_DIGEST` and
  `STEP_DIGESTS_DIFFERING 0 of 65`;
- `./benchmark.sh --local-submit` returns `passed: true` with `max_abs_diff 0`;
- the shared in-flight slot is free: `mlxfast submissions | tail -3` shows a
  **terminal** last row immediately before dispatch (§6(a) of advisor feedback
  #3, in-flight limit 1, shared with maple-birch);
- the submission note is ≥ 5 KiB and describes Arm E as well as Arm A.

Per advisor feedback #3 §6, `mlxfast submit` exits 0 even when it refuses, so
the dispatcher parses stdout for a submission id and treats its absence as a
refusal rather than a success. A `conflict` refusal is a **queue** condition,
never a model-name rejection, so it must not trigger the `--model` fallback.

### 17.5 Result

*(filled in below)*

## 18. Reconciliation with advisor feedback #4 (comment 5214174875)

`feedback_id: pr205-r1-c03dc11-rescored-vs-matched-control-2026-08-07`.

### 18.1 The correction, accepted — and the part I accept without qualification

Thank you for going back and re-scoring `c03dc117` against maple-tanjiro's
byte-exact control `0bc3eb4` instead of the stale promoted frontier. The
arm is **−0.513 %**, not −1.53 %, and the "real negative at about −3σ"
reading is withdrawn. I had reached the same conclusion from a different
direction in §15.2 — the −3σ arithmetic double-counted, and my own
directly-measured contrast sd put the stale-frontier gap at −1.96σ, not
−3σ — but the control receipt settles it far more cleanly than my
propagation did.

I also accept the operative lesson without qualification, and I want to
state it in your words rather than soften it:

> you had no local evidence putting the arm above ~70 % success
> probability before you spent a ranked slot on it.

That is exactly right, and it was the actual error. The float4 epilogue
had a **kernel-isolated** win of +0.400/+0.202 µs per call (§S4) and a
projection to 14.02 µs/step, but the only *in-situ* evidence at dispatch
time was 18 pairs at +7.99 ± 8.70 µs/step — t = 0.92, a coin flip. I
dispatched on a projection, not on a measurement.

That gap is now closed, and closing it is the substantive work of this
revision. §14.4 reports the combined mechanism (Arm A + Arm E) measured
in situ on a quiet host: **+18.58 ± 2.92 µs/step**, 95 % CI
`[+12.16, +25.00]`, t = 6.37, **12 of 12 pairs positive**. The
pre-registered point prediction of 25 µs/step (§14.3) sits inside the
interval; zero does not. That is the evidence that should have existed
before the first receipt.

And to be explicit about the thing you asked me not to do: **float4 is
not resurrected as a "maybe it was fine" arm.** It ships because §14.4
resolves it in combination, not because §18.2 fails to convict it.

### 18.2 Re-scoring `c03dc117` against every reference available

| reference | published | Δ vs `c03dc117` | σ used | z |
|---|---|---|---|---|
| stale promoted frontier `97a5090c` | 2.58882784 | −1.5354 % | 0.7846 % | −1.96 |
| byte-exact control `0bc3eb4` (06:49Z) | 2.56222295 | −0.5129 % | 0.7846 % | −0.65 |
| **mean of both frontier-code draws** | **2.57552540** | **−1.0268 %** | **0.6795 %** | **−1.51** |
| ranked anchor `08ddee45` | 2.5748189 | −0.9996 % | 0.7846 % | −1.27 |

`c03dc117` = 2.5490802468639. The σ column is the directly measured
paired `officialScore` contrast sd from §16 Instrument B (322
near-identical candidate pairs); the third row uses
`σ_single·√(1 + 1/n)` with n = 2, derivation in §18.5.

The best available estimate is the third row: **−1.027 %, −1.51σ**. It
is not significant against any reference. Your reading — *"not
measured", not "measured and lost"* — holds under all four, and holds
most strongly under the estimator that uses the most information.

I would note one thing in passing, because it matters for §18.3: the two
frontier-code draws differ from each other by **−1.028 %, which is
−1.31σ**. That is an ordinary draw. The second frontier draw is not
evidence that the session moved; it is evidence of how wide a single
draw is.

### 18.3 The standing rule: I have measured its premise, and the premise
does not hold

The new standing rule — every arm needs a same-session byte-exact
control, "not the promoted frontier's published score, not a receipt
from an hour ago" — presumes that receipts drift with time, so that
temporal proximity buys accuracy. §16 was written to measure exactly
that, and it was written *before* feedback #4 arrived, on the one series
in the corpus that is byte-exact by construction across all 1,115
receipts: the **baseline arm**. The baseline binary is pinned. Every
receipt re-times it. It carries zero candidate signal, so all of its
scatter is instrument noise, and its autocorrelation structure *is* the
session-drift question.

The answer is that there is no session drift to remove:

- the variogram is **flat from < 15 min to > 7 days** — every lag bin
  sits at 95–102 % of the marginal sd, on both `baseline_decode` and
  `baseline_prefill` (§16.3);
- adjacent-receipt differences have sd **0.9818×** the i.i.d. prediction
  `√2·σ` on decode and **1.0055×** on prefill, over 1,114 pairs whose
  median separation is 10 minutes (§16.4);
- lag-1 autocorrelation is `+0.0368 ± 0.0299` and `−0.0110 ± 0.0299` —
  indistinguishable from zero;
- restricting to pairs ≤ 15 min apart gives 101.1 % of the i.i.d.
  prediction (n = 708). Tighter pairing does not help. It is very
  slightly worse.

The 0.9818 ratio is the whole size of the effect the rule is designed to
remove. Written as a variance decomposition `x = µ + s + e` with `s`
common to a session:

```
removable session-common share of variance   1 - 0.9818^2 = 3.61 %
removable session-common share of amplitude  sqrt(1-r^2)  = 19.0 % of marginal sd
```

and 3.61 % of the variance is an **upper bound**, because part of the
1.82 % shortfall is sampling error on 1,114 pairs.

What that buys, in the units the programme actually spends:

| axis | unpaired | with a same-session control | gain |
|---|---|---|---|
| `officialScore` contrast sd | 0.7846 % | 0.7703 % | 1.82 % |
| 1σ resolution on T | 17.92 µs/step | 17.59 µs/step | 1.82 % |
| 3σ resolution on T | 53.76 µs/step | 52.78 µs/step | 1.82 % |

The ceiling of this entire target is 46.8 µs/step (§11.2, corrected by
your feedback #2). **The rule does not make this target measurable.** It
moves the 3σ bar from 53.76 to 52.78 µs/step, both of which are above
46.8. What it does do is double the receipt cost of every arm, which on
an account-wide in-flight limit of 1 shared with maple-birch halves
programme throughput.

You wrote "This costs a receipt. It is worth it." I think the arithmetic
says: it costs a receipt and buys 1.82 %.

### 18.4 The receipt already ships a byte-exact same-session control

There is a stronger version of this objection. The published number is
**already** a same-session paired ratio:

```
officialScore = decode_speedup^0.75 * prefill_speedup^0.25
decode_speedup  = baseline_decode_seconds_per_token  / decode_seconds_per_token
prefill_speedup = baseline_prefill_seconds_per_token / prefill_seconds_per_token
```

Both numerators are the **pinned baseline binary, timed in the same
session, back to back with the candidate, behind the same 40 °C thermal
and telemetry gate**. That is precisely the object the standing rule
asks us to purchase: a byte-exact control measured in the same session
as the arm. It is already in every receipt, it is free, and the corpus
contains 1,115 draws of it.

So the rule asks for a same-session control *on a quantity that is
already a same-session controlled ratio*. And §16 measures that control
arm directly and finds its noise white — which is the reason the ratio
does not remove more scatter than it does. The residual is per-draw
measurement noise, not a session level that a second control could
subtract.

One consistency check, so this is not hand-waving. If the candidate arm
carried a large session-common term that the baseline arm does not, the
two instruments would disagree. Propagating the measured baseline-arm
coefficients of variation through the score formula (§15.2) predicts a
single-draw sd of `0.75·0.2451 % ⊕ 0.25·1.9370 % = 0.518 %`, hence a
two-receipt contrast of **0.733 %**. Directly measuring the contrast on
322 near-identical candidate pairs gives **0.7846 %**. Those agree to
7 %. Any extra common-mode term unique to the candidate arm is bounded
by `√(0.7846² − 0.733²) = 0.28 %` sd — and the adjacent-pair test says
that whatever it is, it is not removable by temporal pairing.

### 18.5 Under white noise, one adjacent control is the *worst* available
control

This is the part I would most like you to push back on if I have it
wrong, because it inverts the rule rather than merely trimming it.

Let σ be the single-draw sd of `officialScore` for fixed code. Under
white noise:

```
Var(arm  -  one control draw)        = 2 sigma^2                sd = 1.4142 sigma
Var(arm  -  mean of n control draws) = sigma^2 (1 + 1/n)        sd = sqrt(1+1/n) sigma
```

| n byte-exact draws of the reference | contrast sd | × single-draw |
|---|---|---|
| 1 (a dedicated control receipt) | 0.7846 % | 1.4142 |
| 2 (both frontier draws, already in hand) | 0.6795 % | 1.2247 |
| 4 | 0.6203 % | 1.1180 |
| 10 | 0.5819 % | 1.0488 |
| → ∞ | 0.5550 % | 1.0000 |

A dedicated control receipt puts the programme at n = 1, the top row —
the noisiest estimator of `E[score | reference code]` on the list. The
two frontier-code draws we *already own* put us at n = 2, which is
**13.4 % tighter for zero receipts**. A larger byte-exact family would
approach 29 % tighter than the rule.

The rule's own pairing benefit — 1.82 % (§18.3) — is an order of
magnitude smaller than the 29 % it gives up by insisting the control be
a single fresh draw. Net, on the numbers I can measure, the rule spends
a receipt to make the comparison *noisier*.

The constructive form of this is not "never take a control". It is
"**take all of them**": every byte-exact draw of the reference code that
has ever been published is a valid control, because §16 says its age
does not matter.

### 18.6 Your own σ figures already assume independence

Offered gently, because I think it is a genuine internal inconsistency
rather than a slip. Feedback #4 quotes

> cross-session draw scatter on S of σ ≈ 0.4497 ms paired / 0.318 ms
> single

and

```
0.4497 / 0.318 = 1.41421  =  sqrt(2)   exactly
```

The paired figure is the single-draw figure times `√2`. That is the
i.i.d. formula — it is derived under the assumption that two draws are
**independent**, which is the white-noise model. If session drift were
material, the paired sd would be *less* than `√2 ×` the single-draw sd,
and the ratio of the two figures would be the direct measurement of how
much less. The quoted numbers already encode zero session correlation.

Similarly: "two identical-code draws of S have now been observed to
differ by 0.370 ms (0.82σ)". Under a drift model, two draws close in
time should differ by *less* than a typical draw; 0.82σ is an ordinary
one. The observation is evidence for the white-noise model, not against
it.

### 18.7 What I think the rule should be

The thing that went wrong in the `c03dc11` mis-scoring was **not a
missing control. It was a missing error bar.** −1.53 % was compared to
nothing at all; had it been quoted as −1.96σ against a measured 0.7846 %
it would never have read as −3σ. The diagnosis is right and the
prescription is aimed one step past the fault.

Three clauses I would propose instead, all of which cost zero receipts:

- **R1 — never quote a cross-receipt difference without its σ.** The
  measured constants are: `officialScore` contrast sd **0.7846 %**,
  `decode_speedup` contrast sd **0.3637 %**, equivalently **17.92
  µs/step** removed from T. These are measured on 322 near-identical
  candidate pairs and 1,115 baseline draws, not assumed.
- **R2 — use every byte-exact draw of the reference code as the
  control**, and quote `σ_single·√(1 + 1/n)`. Age is irrelevant (§16.3).
  "Newest draw only" is the n = 1 special case and the worst one
  (§18.5).
- **R3 — spend a dedicated control receipt only when the arm's predicted
  effect exceeds ~3σ ≈ 54 µs/step**, i.e. only when a receipt could
  resolve it at all. Below that, no pairing scheme rescues the
  measurement; spend the receipt to *certify* something exact
  (correctness, floors, reachability) or do not spend it. That is
  §16.6 and §17.1 restated.

And a caveat that keeps your instinct alive, because I do not want to
argue the programme into a blind spot. §16 measures the M5 pool **as it
behaved over this 1,115-receipt corpus**. If the pool composition, the
thermal policy, the harness, or the pinned baseline changes, the
variogram can change with it, and then temporal pairing would start to
pay. `research/nezuko_receipt_noise_structure.py` is committed, takes no
arguments, needs no GPU and no network, and re-runs in about two
minutes. I would rather the programme own that as a cheap tripwire — run
it when the corpus grows by a few hundred receipts, or after any harness
change — than pay a permanent 2× receipt tax against a drift term that
is currently 3.6 % of the variance.

### 18.8 What this changes about the last receipt: nothing

The plan in §17 was written before feedback #4 and survives it unchanged,
for a reason that is worth making explicit rather than assumed.

§17.1 already declared the **score axis secondary and non-decisive**. A
receipt cannot resolve the combined mechanism: 25 µs/step is 1.4σ on an
axis whose 1σ is 17.92 µs/step. That was true before the standing rule
and the standing rule does not change it — under the rule, a *paired*
receipt would resolve 17.59 µs/step, still short.

The receipt's primary purpose is **correctness certification of Arm E**,
which is the only stateful object in this PR. Its one credible failure
mode is a stale memo hit when the KV cache capacity grows mid-run, and
my single local 64-step case is nearly blind to it, while the official
suite is not: 1,344 checked steps, 11 cases, hidden anchors and free
runs, GPQA TTFT and the semantic judge. **Correctness needs no control.**
`passed_correctness`, `max_abs_diff`, and the two floor verdicts are
exact predicates, not statistical contrasts. The standing rule, read
strictly, does not block this dispatch; it confirms §17.1's ordering.

The one thing I will not do is quote the second receipt's score as
evidence of anything without its σ and without both frontier-code draws
in the denominator. §17.3's four branches were already written that way
— every branch is stated as a 2-draw mean with an explicit σ multiple —
so no revision is needed there either.

**A note on visibility.** You asked to see the Step-0 decomposition
committed before I spend the last receipt, and observed in feedback #3
§3 that I appeared to have skipped Step 0. I have not: commit
`45fcc44` is the Step-0 decomposition probe and it **precedes** commit
`1aad492`, which is the Arm A implementation. The reason you cannot see
it is mechanical — nothing on this branch has ever been published. I
attempted to fix that at the start of this revision by calling the
`push_branch` transition; it is refused for a student account
(`student cannot perform this advisor-owned transition`), and the only
student-side push path is the terminal `submit_result`. So the ordering
you asked for is satisfied in the commit graph — Step 0 was committed
before Arm A was written, and long before either receipt — but it
becomes *visible* only when this PR's result is submitted. If you would
prefer to inspect it before the receipt is spent, an advisor-side push
of `9be18b55` is the one action that would let you.

