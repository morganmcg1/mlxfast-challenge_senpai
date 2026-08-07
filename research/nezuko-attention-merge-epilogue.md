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

<!-- filled in below -->

## 8. Budget

`./senpai/check-editable-budget.sh 1fe609eb920dd96a409f2949a0e901d3bb525af6`
after the change: `current=2934682 headroom=65318 growth=-454/262144 files=142`.
The change is a net **reduction** of 454 bytes, so it takes nothing from the
shared 65 KB pool that maple-fern also draws on.

Region fence honoured: the diff touches only lines inside the two attention
kernel bodies (`~1466`, `~1593-1662`, `~1923`, `~2094-2163` in the base
numbering). Nothing in `600-1100`, `8525-8910`, `9461-9575` or `10003-10130`.
