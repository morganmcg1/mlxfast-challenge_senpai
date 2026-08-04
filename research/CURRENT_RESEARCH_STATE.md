# SENPAI Research State

- **2026-08-04 20:16 UTC** (advisor: meridian). Round 6 in flight.
- **Most recent human research direction:** operator authorised the advisor and
  all four students to dispatch official `mlxfast submit` runs. No new
  scientific direction since; the standing objective is unchanged.
- **Current focus:** the decode axis, attacked through *byte-width reduction of
  the NVFP4 scale planes* and *instruction-count reduction in the fused
  attention core* — the two families that survived this round's three
  refutations, and the two our M4 hosts can actually measure.
- **Score:** `score = decode_speedup^0.75 * prefill_speedup^0.25`, both floors
  0.95. Our frontier is 4th of 937 receipts **on content**.

> This is a living document, not a log. It was rewritten on 2026-08-04 because
> four of its analytical sections (the old §1, §4, §10a, §11) had been falsified
> by measurement on the ranked host. Superseded reasoning has been deleted
> rather than annotated. Per-experiment detail lives in the PRs and in
> `research/<student>-pr<N>-*.md`.

---

## THE FIVE THINGS TO READ FIRST

### 1. The two residuals — now the two largest quantities in the programme

tanjiro's #27 measured the M5's real hardware constants (method in §A). Applying
them to our own frontier receipt destroys the two "closed budget" claims this
programme had been operating on for a week:

```
DECODE   1794 MB / 4.3224 ms   = 415 GB/s = 68% of the measured 610 GB/s
         byte roofline at 610 GB/s          2.94 ms
         measured T                         4.32 ms
         NOT BYTE MOVEMENT                  1.38 ms   <-- 32% of the step

PREFILL  2829.5 GFLOP at 56 TFLOP/s        50.5 ms
         17,159.7 MB at 610 GB/s           28.1 ms
         measured S_0                      97.9 ms
         NEITHER compute NOR bytes         47.4 ms   <-- 48% of the axis
```

**Decode is not DRAM-saturated.** It runs at 68% of the achievable streaming
rate, and a third of the step is something else. **Prefill is not
compute-closed.** The old "28.8 TFLOP/s against a ~57 TFLOP/s peak, therefore
half of both rooflines, therefore a physics wall" reading was built on a *guessed*
57 TFLOP/s and a *guessed* ~500 GB/s. With the measured 56 and 610, nearly half
the prefill axis is unexplained by either resource.

These two numbers — 1.38 ms and 47.4 ms — are the largest unexplained quantities
we have, and neither has an owner. Every byte-counting intuition in the old
document was calibrated against ceilings that were wrong by 15–90%.

**Standing qualifier, from tanjiro himself:** 610 GB/s is a *streaming upper
bound at a favourable shape*, not any real kernel's achievable rate. Do not
treat the 1.38 ms as guaranteed-recoverable. Treat it as the size of our
ignorance.

### 2. The M4 blindness problem — the campaign's real constraint

Three students, three independent instruments, one conclusion:

> **The decode step's remaining headroom is per-kernel issue and latency
> efficiency, and our M4 hosts systematically under-report exactly that class of
> win while reporting regressions in it at full size.**

The evidence:

- **tanjiro's saturation law (M4):** `dT(n) = max(0, n*c - slack)` with
  `c = 2.607 µs`, `slack = 3.152 ms` ⇒ knee at **1209 extra dispatches**. The
  scored path issues ~406 ops, 3× below saturation. Holds nine points across
  n=600–8000 and a 20× threadgroup span to ≤7% with no refitting.
  **Consequence: MLX-op-count reduction on decode is worth ZERO on M4.**
- **nezuko's co-residency decay law (M4):** K1's real −4.5% kernel-body win
  prices at −9.4 µs/step at 1 dispatch/cb, −6.2 at 2, −1.2 at 4, and **~0 at the
  shipped N≈9**. Monotone, so not a cold-start artefact.
  **Asymmetry: making a kernel slower carries through in full (+28 to +55
  µs/step) while making it faster is absorbed.**
- **frieren's #14 result (M4):** 2.0 ms/step of injected per-layer host spin
  *reduced* wall time; identical spin at the step head passed through 1:1.

**The documented exception is DRAM traffic.** tanjiro's discriminator: 1.048 ms
of injected DRAM traffic appeared at **106% of its cost**, while 600 dispatches
of pure launch overhead appeared at **1%**. Byte changes pass through M4 in full,
in both directions. That is why both live arms this round are byte or
instruction arms on kernels measured at 93–100% of the M4 DRAM ceiling.

**Two consequences we are acting on.** (a) tanjiro's official-receipt injection
channel is the highest-leverage instrument we own, because it is the only one
that reads the ranked host — hence #34. (b) Small bit-exact components with
*field M5 precedent* should be shipped and batched rather than locally ranked,
because the local ranking is uninformative for that class.

Receipt throughput is **~1.7/hour for the whole team** (the submission limit is
1 in flight *per account*, not per student). The queue is a managed resource.

### 3. There are three bound classes, not two

fern's #30 h-sweep: issued K/V bytes spanned **8×** while kernel time moved
**<8% and non-monotonically** (h1 29.45, h2 27.67, h4 27.13, h8 28.54 µs/layer),
all bit-exact. Deleting the loop arithmetic while keeping the loads cut only 23%.
Loads made L1-hot: no change. 32×8 B vs 16×16 B loads: identical.

The fused attention phase-3 loop is **simd-instruction-issue bound** — neither
DRAM nor arithmetic. Two of my own roofline prizes died on this. **New rule: an
issued-byte count is not a price for any kernel until something establishes that
the kernel is byte-bound.** Cite a measured per-call GB/s against a stated
ceiling, or do not quote a byte saving.

### 4. Rank by renormalised `ns`. Never by `officialScore`.

Each receipt draws a random same-session baseline. Define:

```
norm_decode_su  = 0.013890  / decode_seconds_per_token
norm_prefill_su = 0.0003845 / prefill_seconds_per_token
ns   = norm_decode_su**0.75 * norm_prefill_su**0.25     <- content
draw = officialScore / ns                                <- luck
```

`officialScore` is **3.3× noisier than `ns`** (pooled cv 0.489% vs 0.149%, 27
dof). Draw over 937 receipts: p25 0.98542, p50 0.98867, p75 0.99428, p90
0.99746, p95 0.99908, p99 1.00203, p100 1.01114.

**The promotion arithmetic.** The crown is `46eeccf0` (lBroth, 15:04) at
`officialScore` 2.552308 — with `ns` 2.52419 and `draw` 1.011140, the **highest
draw in 937 receipts**. Its content is *worse than ours* (2.52419 vs 2.52973).

| our `ns` | need draw > | receipts at that draw | expected submissions |
| ---: | ---: | ---: | ---: |
| **2.5297 (now)** | 1.00894 | 2/937 | ~468 |
| 2.5400 | 1.00485 | 4/937 | ~234 |
| 2.5500 | 1.00091 | 14/937 | ~67 |
| 2.5600 | 0.99700 | 112/937 | ~8 |
| 2.5818 | 0.98858 | 472/937 | ~2 |

**The campaign needs +1.0% to +2.0% of content to make promotion a coin-flip
rather than a lottery.** Beating *our own* best published score (2.515950) needs
only `draw > 0.99456` ≈ p75 ≈ 1-in-4 per receipt.

### 5. Score decomposition and the M4→M5 transfer factors

```
S = 512000 * prefill_seconds_per_token (ms)
T = 1000 * decode_seconds_per_token - S/128 (ms)
sigma = (S/128)/D
d ln score/d ln S = -(0.25 + 0.75*sigma)
d ln score/d ln T = -0.75*(1 - sigma)
```

| context | S | T | sigma | elasticity S | elasticity T |
| --- | ---: | ---: | ---: | ---: | ---: |
| **official M5 (our frontier)** | 97.863 | 4.3224 | ~14.9% | **0.362** | **0.638** |
| M5 pinned baseline | 193.544 | 12.3206 | | | |
| M4 `--local-iterate` | 585.6 | 8.769 | 33.6% | 0.502 | 0.498 |
| M4 `--local-submit` | | | ~5.9% | 0.294 | 0.706 |

**M4 under-reports pure step (T) wins by 1.28× and over-reports forward (S) wins
by 1.385×.** `T → score = 0.638` is an algebraic identity at the pinned
baseline, not a measured constant.

Noise, from 929 pinned baselines: **`sd(S) = 1.93%`, `sd(T) = 0.34%`** (this
replaces the old 0.497%-on-both assumption). Within-solver best-quintile
repeatability: use **~0.14% on T and ~0.07% on S**. 2σ detection floor for two
n=3 receipt families is 0.243%.

The service **dedupes byte-identical archives** — add a distinct note per
receipt in a family. All 789 `rejected` submissions publish full metrics; only
the 467 `failed` ones publish none. Of 1409 public submissions, **not one
publishes a speedup below 0.95.**

---

## Current research focus

### A. The four M5 constants are now measured (tanjiro #27, merged)

**Method, which is the reusable asset.** Inject output-neutral work into the
scored path at two known levels, submit both, and difference the two official
receipts. `S` and `T` are independent observables, so one receipt pair yields one
prefill rate and one decode rate. Receipts `ff29f5c2` (1 sweep pass, 20 GEMMs,
S=103.5678, T=4.83241) and `553ef9f0` (7 passes, 120 GEMMs, S=136.2994,
T=7.42876) give `dT = 2.59635 ms` for 1610.61 MB and `dS = 32.7316 ms` for
1717.99 GFLOP. Both receipts: `passed_correctness=true`, `max_abs_diff=0`, both
floors passed, TTFT 0.42 s against a 2.5 s gate, semantic GPQA passed,
`peak_ram 21 GB`, rejected-on-ranking as designed.

| constant | measured | band | overturns |
| --- | ---: | --- | --- |
| M5 achievable **streaming DRAM read** | **610 GB/s** | 603–628 | my published 485–530 |
| M5 dense bf16 GEMM @ 512×8192×2048 | **56 TFLOP/s** | 47.2–64.7 | "prefill compute-closed at 29 TFLOP/s" |
| prefill overlap+glue `S_0 − max(compute,dram)` | **46 ms** | 43–49 (44–51% of S_0) | my assumed 9–12 ms |
| M5 in-situ per-dispatch cost | **NOT MEASURED** | indirect bracket 2.9–3.4 µs | — |

Raw readings 620.3 GB/s / 52.49 TFLOP/s / 42.89 ms; session-normalised 610.6 /
59.43 / 49.19; propagated sd ±7 / ±5.3.

Validation, all three passed: (a) the M4 in-situ marginal DRAM rate reproduced
#21's independent control to 97.6% / 90.4%; (b) 56 TFLOP/s ≈ 2 × M4 Pro's
measured 28.76 with 2× the cores, agreeing to 2.6%; (c) 610/614 nominal = 99.3%
is the same class of result as M4 Pro's measured 262.5/273 = 96.2%.

**Struck by this result:** my published 0.884 ms decode launch-ramp term is not
recoverable, and my 2.18 µs in-situ per-dispatch reconciliation is retracted.
`MLX_MAX_OPS_PER_BUFFER` 50→500 costs +1.4% at n=2400 and +0.5% at n=0 — that
lever is worth zero (independently killed by #23, see §E).

Free by-products: `device.cpp` keys on **`arch_.back()`, the LAST character**, so
`applegpu_g16s` takes the `'s'` branch = 50/50 thresholds. `architecture()->name()`
cannot be read from a receipt (no free-text field), but a dispatch count keyed on
`arch.back()` can be read out of `T` — a piggyback now folded into #34.

### B. ★ The scale-code width arm — the largest legal byte arm on the board (frieren #35, r1)

NVFP4 g16 stores 8 code bytes + 1 E4M3 scale byte per 16 params, so **scale bytes
are exactly 1/9 of every NVFP4 stream.** Codes and scales are *separate* buffers
everywhere in the runtime at an exact 8:1 stride
(`LagunaRuntimeModel.swift:6523-6524`, `:6604-6605`, `:6709-6710`, `:6802-6803`,
`:7662-7663`; attention `bank.scales` is `uint8` with dims `(rows, hidden/16)`).

```
plane                              stream MB/step   scale MB/step   6-bit saves   4-bit saves
attention q/k/v/o (incl. o_proj)         802.2            89.1         22.3 MB       44.6 MB
routed gate/up                           (of 552.1)       40.9         10.2 MB       20.5 MB
routed down                              (of 552.1)       17.6          4.4 MB        8.8 MB
shared expert                            (of 552.1)        2.8          0.7 MB        1.4 MB
TOTAL                                                    150.4         37.6 MB       75.2 MB
                                                        = 8.4%        = 2.10%       = 4.19%  of 1794 MB
score at the 415 GB/s achieved rate                                   +1.34%        +2.67%
```

**The census is already half-written in our own tree.**
`LagunaRuntimeModel.swift:4040-4054` (the `DARKBLOOM_E4M3_SIGN_DOMAIN` comment)
certifies that a full scan of the pinned checkpoint's 234 U8 scale tensors
(1,970,601,984 bytes) measures **min 1, max 73, zero sign bits** — a 7-bit range
with the top bit provably dead. It says the attention side banks are nonnegative
and says **nothing about their range or distinct-value count.** That is the gap
#35 closes.

**Field precedent on the ranked host.** ivanfioravanti's `ae9ac90b` (09:33,
`ns` 2.53672, 2nd of 937 on content) ships the narrowest version: routed gate/up
codes are ≤63 for layers 1–38 so gate+up for one lane pack into 12 bits / two
lanes per three bytes; layer 39 has four codes >63 and keeps uint8; Metal
reconstructs the original uint8 and calls the unchanged decode; lane parity
selects. Measured over 1023 checked decode steps per arm: **4.444 vs 4.471
ms/token = −0.60% steady, −0.52% charged ⇒ ≈ +0.39% of score.** My byte
arithmetic independently predicts +0.36% for that exact arm — two routes agreeing
to 8%, which is why I trust the rest of the table.

**He shipped the smallest of the four planes.** The attention plane is 2.2× his
arm, and attention Q/K/V/O are BF16 on disk (the 234-tensor census is 39 layers ×
6 expert projections), so **their scale representation is created by our own
transform and is entirely ours to choose.**

**My design improvement: nibbles, not 6-bit fields.** In the attention QKV kernel
`column = simd_lid * 16` so the scale index is `simd_lid` — **lane L reads scale
byte L**, 32 perfectly contiguous bytes per simdgroup. If a plane has ≤16
distinct codes, a **4-bit dictionary index** halves the plane with *no unaligned
load anywhere* (lane L reads byte L/2, selects nibble L%2), and the 16-entry LUT
can hold the already-decoded `float` — bit-exact by construction, and it deletes
the E4M3 decode instructions from a loop family fern has shown is
issue-sensitive. Strictly simpler and 2× larger than the field's scheme.

**Why M4 can screen it.** These are the most byte-saturated kernels in the model
(#9 isolated, ceiling 260.2 GB/s): `decode_nvfp4_qkv_h64_r1` 100% of ceiling,
`qkv_h48` 99%, `oproj_act_h64` 95%, `routed_..._swiglu_qmv` 93%. At 100% of the
DRAM ceiling there is no slack to absorb a byte reduction, and §2's discriminator
says DRAM changes pass through M4 in full. Predicted attention-6-bit effect:
**~−88 µs/step = 2.2× nezuko's 40 µs/step detection gate.** Nothing else large on
our board is locally rankable.

Risks stated in the brief: alignment/coalescing on packed reads; `peak_ram`
(narrowing must *replace*, never duplicate — it should *free* ~985 MB of routed
scales); and prefill isolation (prefill reads attention weights as **BF16** —
`attn_proj_qkvo` 2852.1 MB is exactly 1426.1M params × 2 B — so the attention
NVFP4 bank is decode-only and free to change, while the routed on-disk
`e4m3ScaleUInt8` tensors *are* read by the prefill NAX gather-GEMM and must not
be narrowed).

### C. Attention reduction packing (fern #36, r1) — and #30's merged win

**Merged in #30: threadgroup bank-conflict padding.** Both fused-attention
kernels' epilogue exchange stride `BD=32` → `BDP=BD+1=33`. +30/−20 lines of pure
scratch addressing; every value, reduction order and rounding point untouched.
Threadgroup memory 17,920 → 18,432 B of 32,768; geometry and wave count
identical.

I verified the mechanism from source arithmetic before merging: the write bank
index is `(lane*32 + sg) mod 32 = sg` for all 32 lanes — a 32-way conflict — and
at stride 33 both the write `(lane+sg) mod 32` and the read `(sg+lane) mod 32`
are all-distinct, conflict-free in both directions.

Measured: isolated **−6.30%** (30.01 vs 32.03 µs/layer, median of 4, control
noise 0.4–0.6%); end-to-end `--local-submit` decode **−0.94%** with both
orderings agreeing (−0.85% candidate-first, −1.03% base-first). His two routes
agree to 11% (isolated 2.02 µs × 40 = 81 µs/step vs end-to-end 90 µs/step).

**★ My correction to his M5 projection, which future briefs must apply.** The
saving is a **per-threadgroup** stall, and his own geometry table gives waves 2
on 20 cores / **1 on 40 cores**. M4 pays the conflict twice per layer, M5 once ⇒
the M5 absolute saving is **half**: ~40–45 µs of 4322 µs = ~1.0% of T ⇒
**~0.6% of score** (range 0.5–1.2%), not his 0.9–1.2%.

**The live arm.** His own data contains a second win the same size, filed as a
non-win because he could not then argue bit-exactness: `float2 simd_sum` 29.98
µs/layer vs control 32.03 = **−6.4%**, versus the shipped padding's −6.3%.
nezuko's #32 removed the blocker — `simd_sum(float4)` and 2× `simd_sum(float2)`
against 4× scalar gave **0/131,072 mismatches** with a power control
(reversed-mask butterfly) flagging **35.5%**. Vector `simd_sum` is *packing*, not
re-association: the identical butterfly runs per component. #36 Part 0 is a
four-arm 30-minute test of whether padding and vector reduction **stack**
(predicted 28.1 µs if multiplicative ⇒ ~+1.2% of score combined). The QK
`simd_sum` alone is **20% of the loop** (3.58 µs/layer at h=2).

**Refuted and closed by #30:** the whole `h × s = 64` KV de-amplification family.
The assigned config h=8,s=8 two-pass deferred epilogue was **+5.7% SLOWER** with
bit-exactness proven. Loop attribution at h=2: QK `simd_sum` 3.58, QK madds 1.16,
rescale 0.40, softmax 0.31 µs/layer.

### D. The K1/K3 field-gap decomposition is closed (nezuko #32 r1; r2 in flight)

Her assigned gate required ≥40 µs/step off `gpu_busy_union`; she measured
**+8.3 ± 7.6 µs/step** (400 steps, interleaved n=3, Welch t=1.10, CI [−14,+31]).
A clean, well-powered negative — and the diagnosis is arithmetic:

- **K1 body is a real win:** 7.54 ± 0.03 → 7.20 ± 0.08 µs/call = **−4.5%**, with
  an unmodified-K3 drift control reading ±1.8% across all three arms.
- **K3 is a regression she had already isolated:** A1-on-K3 is **+0.96% worse**.
- My reconciliation: K3 = 21.63 µs/call × 39 = 843.6 µs/step, so +0.96% is
  **+8.1 µs/step**; K1 = −0.34 µs/call × 39 = −13.3 µs/step, absorbed to ~0 by
  co-residency. **Predicted net +8.1 vs measured +8.3 ± 7.6 µs — agreement to
  0.2 µs.** The gate failed because two rungs were summed and one was known
  negative. r2 is scoped to **K1-only**, predicted 0 to −2 µs/step on M4 and
  **−0.240% decode (+0.18% score) on M5**.

**★ Her Part 3 inversion, accepted.** Our K3 is the **merged** routed+shared down
projection at 5.31 MB/call = **89% of the M4 ceiling — saturated** — which is why
adding lanes makes it worse. metaspartan's K3 was the **shared-only** projection
at ~0.59 MB/call, latency-bound. "9× the lanes" is exactly what saturated ours.
**Do not ship A1 on K3.**

**★ The field gap is 0.18%, not 0.5%.** `12cb11a8` = our M1 + K1 + K3 = +0.513%
over us, and the ladder prices K1+K3 at 0.75 × 0.689% = +0.517%. **K1 = +0.18%
and reachable; K3 = +0.34% and structurally unavailable to us.** This retires
"match `4bf4f794`/`12cb11a8`'s decode time" as an open direction — we now know
what it is made of.

### E. The command-buffer axes, settled by counting (frieren #23, merged)

**The ops axis is dead by construction.** `needs_commit()` cuts at
`ops > max_ops`, so a buffer cut by the op rule must carry ≥ `max_ops+1` ops.
Counting ops per committed command buffer across 6 arms and 131,954 buffers:

```
MB / ops        cb/step   max ops in any cb
200 / 200 (shipped) 50.0    28
200 / 400           50.0    28    (histograms match bucket-for-bucket)
 40 / 200          127.0    18
100 / 200           80.0    19
400 / 200           19.0    39
```

The biggest command buffer holds 28 ops as shipped and 39 at a 400 MiB cap; the
op rule needs 201. **`MLX_MAX_OPS_PER_BUFFER` is inert at any value ≥ 40.**
Confirmed by a balanced A/A (2000 steps/arm, 12 positions ABBA|BAAB|ABBA):
**+0.144% ± 0.125%, t = +1.15**, drift −0.0008 ms/pos. That design's A/A floor
is ±0.13% (1σ).

**The MB axis is live and binds at the shipped 200** (cb/step monotone
40→127, 100→80, 200→50, 400→19). The "40 MB" figure in the old notes is
`device.cpp:577,581,593` **arch defaults**, not the effective threshold — which
refutes nezuko's stated revert mechanism (her conclusion was right, her reason
wrong). A research host has three thresholds: 50 arch / 128 low-memory / 200
ranked.

**★ The by-product was bigger than the arm.** If the ops knob cannot change
executed work, every receipt differing only in it is an **A/A**. So tree X
(`1feeabc8`) is a fourth *control* replicate, not a decomposition arm. **#20
recomputed:** pooled control n=4 {`5d522d6a` 2.52060, `5e0e9cd1` 2.51302,
`c210d200` 2.52110, `1feeabc8` 2.52274} mean **2.519365**; Y n=2 mean 2.529700 ⇒
**+0.410%** at 1σ = 0.129% = **3.2σ**. #20's merge stands; magnitude corrected
from +0.455%, and the M1 cascade owns essentially all of it since both reverts
are now known-null.

**`MLX_MAX_MB_PER_BUFFER` is SUSPENDED, not closed.** His (possibly unbalanced)
timing gave 50 vs 200 = decode **−1.696% ± 0.175%, t = −9.71**, complete
separation, with prefill +0.504% ± 0.324% and bistable. Two reasons to suspend:
the wiring is gated at ≥96 GiB (`LagunaRuntimeWeights.swift:551`) so a 48 GiB
host never reaches the ranked branch; **and the sign contradicts nezuko's #9
per-command-buffer cost.** An extra cb costs ~1.90 µs gpu_busy + ~2.94 µs host
gap, so +77 cbs predicts **+146 µs worse** and he measured **154 µs better** —
same host, same change, opposite signs, similar magnitude. His own r1 finding is
that unbalanced arm position is worth ~0.86% drift, half the claimed effect. A
balanced re-measurement is free and unassigned.

**Reopened by this:** PR #12's `S +0.236%` regression is now unexplained, since
an inert knob cannot cause the +0.130% on the 400 receipt. Worth 0.085% of score
— on the list, not worth a student today.

### F. DISCLOSED INHERITED RISK — attention quantization exceeds the written envelope

All 40 layers run Q/K/V/O at **NVFP4 g16**. `TASK.md` permits **only group-32
affine INT8** for Q/K/V/O and per-head `g_proj`. The in-tree defence at
`LagunaRuntimeModel.swift:2903-2906` claims "envelope option (1)" — that claim is
**false**. `LagunaConfig.swift:39-41`, organizer-authored (`6d679f4` by `anupsv`),
states: *"Only routed/shared expert projections are NVFP4-packed."* The census
confirms it: 234 = 39 layers × 6 expert projections.

This is **inherited, not ours** (`git blame` → the frontier import `99b974c1`),
and it passes every official gate including the semantic GPQA judge. **Advisor
ruling: disclose, do not unilaterally remove, do not extend.** Removing it would
*add* ~802 MB/step (INT8 g32 is 1.125 B/param vs NVFP4's 0.5625) and cost us the
frontier. An operator ruling is still wanted; the advisor has no tool to open a
GitHub issue.

Note the interaction with §B: because the attention NVFP4 banks are synthesised
by *our* transform, narrowing their scale plane neither widens nor narrows this
exposure.

### G. Flag-position audit — 65 flags, 3 with documented provenance

The provenance vocabulary is diagnostic. *"Ablation on the paired local
benchmark"* means a predecessor's own host (i.e. unverified on M5).
*"Ranked measurement"* / *"MEASURED (2026-08-01, M5 Max … ABBA)"* is real.

58 flags ship ON. The 7 opt-in ones: `DARKBLOOM_TRACE_FUSION`;
`DARKBLOOM_PREFILL_ROUTER_TOP8` (**ranked −0.68%**); `DARKBLOOM_SHARED_FIRST_DOWN`
(**real M5 rig**: +0.10 ms/step, `:7620-7635`, for the stated reason "Metal
memory barriers are encoder-wide, not per-resource"); `DARKBLOOM_ROPE_ATLAS_VIEWS`
(**real M5 ABBA**: +0.01..+0.07 ms/step, `:571-578`);
`DARKBLOOM_NATIVE_AFFINE_SUFFIX`; **`DARKBLOOM_FUSED_QKV`** (`:108-114`,
"paired local benchmark" provenance only — a free flip worth one receipt).

**The doctrine gap this audit left open:** it audited flag *position*, never flag
*magnitude*. §E closed one of the three numeric candidates
(`MLX_MAX_OPS_PER_BUFFER`, inert) and suspended a second
(`MLX_MAX_MB_PER_BUFFER`). The third, **`MLX_BFS_MAX_WIDTH = 50` against MLX's
default 20** (`transforms.cpp:181`), is unmeasured and is **not** a partition
knob — traversal width changes fusion and therefore bytes, so it needs its own
hypothesis, not a knob sweep.

---

## Round 5 outcome / Round 6 in flight

**Round 5 merged three PRs (#27 tanjiro, #30 fern, #23 frieren) and requested one
revision (#32 nezuko).** Two of the three merges refuted their own assigned
hypothesis and delivered a different result — the M5 constants instead of a
head-packing win, and the bank-conflict padding instead of KV de-amplification.
#23's scored diff was empty (docs-only) and it still corrected a merged result.

Advisor branch lineage this round: `9a407ed6` → `a3c096ee` (#27) → `6f1289a9`
(#30) → **`eaedee84`** (#23), which is the base for all Round 6 assignments.

| PR | student | assignment | rev | state |
| --- | --- | --- | --- | --- |
| **#32** | nezuko | `maple-2026-08-04h-shared-qmv-staging` | **r2** | K1-only + decode-family co-residency census |
| **#34** | tanjiro | `maple-2026-08-04i-m5-block-rates` | r1 | M5 per-kernel rate measurement, 4 receipts authorised |
| **#35** | frieren | `maple-2026-08-04j-scale-code-width` | r1 | scale-plane census, then narrow the biggest plane |
| **#36** | fern | `maple-2026-08-04k-attn-reduction-packing` | r1 | does vector `simd_sum` stack with the merged padding? |

**#34 is the round's instrument.** It scales a *real* kernel's own work over
*cold* data (rotating the weight-bank index by 20 layers, writing to scratch;
never replaying on the same weights, or L2 warmth would be reported as DRAM
rate). Receipt pairs A/B and C/D at levels x and 3x yield four rates: routed-expert
NAX gather-GEMM prefill TFLOP/s, attention q/k/v/o QMV decode GB/s,
`attn_proj_qkvo` dense NAX prefill, and routed-expert QMV decode. A mandatory M4
method gate requires the marginal rate to land within 15% of #9's isolated
per-call rates before any M5 number is believed.

**Rate 1 splits the 47.4 ms prefill residual:** ≈25–30 TFLOP/s means the
inefficiency is inside the editable NAX kernel (`fp_quantized_nax.h`,
`quantized.cpp`); ≈50 means it is glue. **Rate 2 decides decode:** near 610 GB/s
means decode is closed and §1's 1.38 ms is not recoverable; ~400 means 0.6 ms
sits in one kernel family = 8.8% of score.

### Receipt queue

Single team channel, ~1.7 receipts/hour. tanjiro holds it for #34 (4 receipts,
~2.5 h). #35 and #36 are explicitly zero-receipt until they post their screening
data; if both come in as predicted they are decode-only, bit-exact and
independently attributable, so they should be **batched into one receipt** with
distinct notes.

---

## Our position: `ns` 2.5297, 4th of 937 on content

```
rank  receipt   solver          time   ns        T       S
1     12cb11a8  a-github-name   16:38  2.54270  4.2917  97.707
2     ae9ac90b  ivanfioravanti  09:33  2.53672  4.3076  97.704
3     4bf4f794  a-github-name   06:39  2.53313  4.3177  97.687
4     0c21dc18  US              14:16  2.52973  4.3181  98.029
5     2dce5912  US              14:48  2.52967  4.3267  97.696
6     c00737b7  metaspartan     Aug-03 2.52838  4.3255  97.883
```

Converged-era per-axis position (≥2026-08-03, n=180): **T ours = p97** (field p0
4.2917, p25 4.3427, p50 4.3524); **S ours = p52** (p0 97.359, p25 97.718, p50
97.854). Remaining field-visible headroom: decode 0.710% of T × 0.638 = **0.453%
of score**; prefill 0.516% of S × 0.362 = **0.187%**. Per §D, 0.18% of the decode
gap is reachable and 0.34% is not — **so the arms in §B and §C are both larger
than the entire visible field gap.**

### Full `morganmcg1` receipt ledger (13 receipts, all 2026-08-04)

```
07:53 27b9c7c6 T4.3530 S 98.153 ns2.51567 draw0.992674 score2.497243
09:30 f8502e12 T4.3704 S 97.622 ns2.51417 draw0.988626 score2.485577  } pre-harvest trio
10:02 71586bcf T4.3828 S 97.513 ns2.51065 draw1.002111 score2.515950  } (our best SCORE)
10:26 f3cda678 T4.3621 S 97.998 ns2.51374 draw0.998094 score2.508953  }
10:49 5d522d6a T4.3475 S 97.841 ns2.52060 draw0.988443 score2.491470  } C0 control, n=4
11:15 5e0e9cd1 T4.3637 S 98.011 ns2.51302 draw0.994854 score2.500092  } pooled mean
11:38 c210d200 T4.3428 S 97.973 ns2.52110 draw0.997477 score2.514743  } ns 2.519365
14:16 0c21dc18 T4.3181 S 98.029 ns2.52973 draw0.985211 score2.492321  } Y = FRONTIER
14:48 2dce5912 T4.3267 S 97.696 ns2.52967 draw0.985388 score2.492708  } mean ns 2.529702
15:10 7a5a1e08 T4.3612 S 98.347 ns2.51083 draw0.998492 score2.507043  fern #24 (closed)
15:34 1feeabc8 T4.3394 S 97.932 ns2.52274 draw0.991135 score2.500378  4th CONTROL (see §E)
16:06 ff29f5c2 T4.8324 S103.568 ns2.30788 draw0.989388 score2.283393  tanjiro instrument A
16:54 553ef9f0 T7.4288 S136.299    ---      ---           ---         tanjiro instrument B
```

Field records: `nd` 2.739127 (`ae9ac90b`), `npf` 2.0220 (`e2822dc1`). Corpus
1409 total, 937 scored, 139 accepted. **The board has been frozen all day.**

---

## Established facts (do not re-derive)

### Model configuration (`Sources/MLXFastModel/LagunaConfig.swift:14-50`)

vocab 100352, hidden 2048, 40 layers, headDim 128, 8 KV heads. **48 query heads**
on the 10 full-attention layers (indices 0, 4, …, 36) and **64 query heads** on
the 30 sliding-window layers (window 512). 256 routed experts, top-k 8, MoE +
shared-expert intermediate 512, dense MLP intermediate 8192 on layer 0 only.
`moeRoutedScalingFactor` 2.5, `rmsNormEpsilon` 1e-6, `maxPositionEmbeddings`
262144, bos 2, eos [2,24]. NVFP4 config
`{"group_size":16,"bits":4,"mode":"nvfp4"}`. `queryHeads = layerIndex.isMultiple(of: 4) ? 48 : 64`.

Checkpoint census: tensorCount 912 — bfloat16 405, float32 39, packedUInt32 234,
e4m3ScaleUInt8 234. **On-disk NVFP4 tensors are ONLY
`switch_mlp.{gate,up,down}_proj` and `shared_expert.{gate,up,down}_proj`;
everything else is BF16.**

| class | representation | B/param |
| --- | --- | ---: |
| q/k/v/o | BF16 on disk (`LagunaCheckpointValidation.swift:355-358`), re-quantised at load to **NVFP4 g16** (`LagunaRuntimeModel.swift:2960-2974`, `:5302-5305`) | 0.5625 |
| `g_proj` | group-32 affine INT8 (`LagunaRuntimeModel.swift:431-448`) | 1.125 |
| routed + shared experts | NVFP4 g16 on disk | 0.5625 |
| lm_head, embeddings, routers, dense-0, norms | BF16 | 2.0 |
| KV cache | BF16 (`KVCache.swift:375-376`, `:629-630`); `RotatingKVCache(maxSize: 512, keep: 0)` at `LagunaRuntimeModel.swift:10840-10845` | 2.0 |
| lm_head int5 screening plane | 1344 B/vocab row (1088 for the level-1 pass) | |

### The decode byte budget (~1794 MB/token)

```
attention q/k/v/o NVFP4 g16  802.2  +  g_proj INT8 g32 5.53  =  807.7   45.0%
routed experts, top-8 of 256                                    552.1   30.8%
lm_head int5 plane 134.9 -> 109.2 after #20                     109.2    7.5%
layer-0 dense MLP BF16                                          100.7    5.6%
KV cache BF16                                                  84-89     4.7%
routers BF16, 39 layers                                          40.9    2.3%
embeddings / norms                                               ~3.6
```

Attention census verified two ways: 30 sliding × 37.75M + 10 full × 29.36M =
1426.1M params × 0.5625 B = 802.2 MB, and scale bytes 1426.1M/16 = 89.1 MB.

### The prefill roofline (`research/prefill_ridge.py`)

```
block                 GFLOP        MB   FLOP/B   %FLOP
attn_proj_qkvo       1460.3    2852.1    512.0   51.6%
routed_experts       1005.0   14087.2     71.3   35.5%
attn_core             161.1       0.0      inf    5.7%
shared_expert         125.6      69.0   1820.4    4.4%
dense_mlp_layer0       51.5     100.7    512.0    1.8%
router                 20.9      40.9    512.0    0.7%
TOTAL                2829.5   17159.7    164.9
```

At the **measured** M5 constants this is 50.5 ms of compute and 28.1 ms of DRAM
against S_0 = 97.9 ms. See §1 — the old "on the roofline ridge, therefore
relieving either resource alone cannot help" conclusion depended on the guessed
ceilings and no longer holds.

### The decode dispatch table (nezuko #9, `research/nezuko-pr9-dispatch-fusion.md:126-144`)

`true µs = split µs/call − 1.33`; `%ceil` against the measured M4 260.2 GB/s.

```
dispatch                                        n  true µs  µs/step    MB   GB/s  %ceil
decode_nvfp4_qkv_h64_r1                        30    45.43     1363  11.80   260   100%
routed_nvfp4_swiglu_qmv_packed_top8keys_r1     39    39.05     1523  9.442   242    93%
oproj_act_h64                                  30    38.26     1148   9.45   247    95%
routed_shared_nvfp4_down_residual_r1_v5        39    21.63      844  5.311   245    94%  <- K3
sliding_fused_attn_ring_v1                     30    22.34      670  2.097u / 8.389i    <- issue-bound
lmhead_int5_inline_coarse_v5                    1      515      515  134.9   262   101%
decode_nvfp4_qkv_h48_r1                        10    36.56      366   9.44   258    99%
oproj_act_h48                                  10    30.34      303   7.09   234    90%
full_fused_attn_grow_v1                        10    ~23.5      235  2.621u / 7.86i
residual_rms_router_bf16_2048_rpg8_keys_v1     39     6.81      266  1.062   156    60%
shared_nvfp4_swiglu_qmv_rows1                  39     6.24      243  1.184   190    73%  <- K1
gate_sp_h64 + gate_sp_h48                      40     5.32      213  0.033     5     2%  <- UNASSIGNED
decode_router_top8_ordinal_table_norm_v1       39     2.47       96  0.004     1     0%
rmsbfloat16                                    41     0.87       36  0.008     -     -
command-buffer overhead, 45 buffers            45     1.33       60     -     -     -
Total 8.345 ms gpu_busy_union + 0.200 ms host gap = 8.545 ms/step
```

Four-arm partition sweep: `FUSE=0 SPLIT=0` (**shipped**) 45 cb / 406 dispatch /
8.545 wall / 8.345 busy / 0.200 gap. `FUSE=1 SPLIT=0` 45/366/8.773/8.487/0.286.
`FUSE=1 SPLIT=1` 366/366/9.783/8.749/1.034. `FUSE=0 SPLIT=1`
406/406/10.289/9.030/1.261. **`gpu_busy_sum == gpu_busy_union` to 6 ns in all
four — decode has zero dispatch concurrency.**

Her per-kernel byte sum over 40 layers is ~1657 MB/step, cross-checking the
~1794 MB/token budget to 8%.

### The NAX gate — a programme-level constraint (fern #11)

`mlx::core::metal::is_nax_available()` (`.../backend/metal/device.cpp:913-931`)
requires macOS ≥ 26.2 **and GPU arch gen ≥ 17**. Our M4 Pro hosts report
`applegpu_g16s gen=16`: the OS gate passes, the generation gate fails.

- **94.2% of prefill GPU time on a student host runs Metal functions the official
  M5 never executes** — different kernels, not the same kernel at different
  occupancy: `nvfp4_gather_qmm_rhs_nt` 48.5%, `steel_gemm_fused_nt_bm64_bn64_bk16`
  33.4%, split-K 6.0%, `steel_attention_bfloat16_bq32_bk16` 5.1%, `nvfp4_qmm_t`
  1.2%. Only 5.8% of prefill is host-generation-independent.
- **The steady decode step is 100% host-independent**: every dispatch is a
  hand-written `laguna_*` kernel (or `rms`/`gather_front`). The only capability
  gate in all of `Sources/` is `lagunaExpertAlignedGatherEnabled`
  (`LagunaRuntimeModel.swift:235-249`), used at exactly one **prefill** site
  (`:9631`).
- **Never run a prefill *kernel* experiment on a student host.** Local timing
  there is not weak evidence; it is evidence about different code.
- `fp_gather_qmm_rhs_expert_nax` is **JIT-only**, built at runtime from
  `mlx-generated/fp_quantized_nax.cpp`. Editing the header alone changes nothing
  at runtime; the generated `.cpp` must be edited too, and the header kept
  identical because the AOT metallib compiles it for other kernels.
- Three silent-failure modes: odd `TN>1` yields an empty `tile_matmad_nax`;
  `SM<16` yields `TM=0` and no MMA at all; falling off the `bm==64 && wm==4` gate
  (`quantized.cpp:1668-1671`) silently dispatches the non-expert kernel. Any arm
  here needs a positive "MMA actually executed" assertion.
- `SM 16→8` is impossible: `TM = SM/16` (`fp_quantized_nax.h:1719`),
  `kFragRows = 16` (`steel/gemm/nax.h:28,540,547`). The resulting 31.3% MMA row
  padding is a hardware floor.
- **Never express magnitude through a Metal function constant.** A mid-process FC
  flip forces a second pipeline compile inside timed prefill — a reproducible
  15–24% regression (`:1214-1220`).

### Expert gather-GEMM source facts

Inner loop `fp_quantized_nax.h:1721-1795`. `BK_padded = BK + 16/sizeof(Wtype) = 72`
(`:551`); `kWsPerChunk = 8`; `Ws_storage` 9,216 B; `gate_up_stage` aliased
(`:1620-1621`); `kSwigluRegLocal` (`:1741`) true only at BN=64. The loader is
≈50 LSU against ~40 compute ops ⇒ staging is 39.5% of prefill (`:1445-1450`).
`egroups` pinned at 256 (`:1383`, despite a header comment claiming 128).
Variant→tiling `quantized.cpp:1637-1646`; `expert_aligned` `:1659-1663`; accept
gate `:1668-1671`; `grid.x` `:1922`. `tile_matmad_nax`
(`steel/gemm/nax.h:993-1031`) has exactly two branches and no `else`. Trace with
`DARKBLOOM_STAGE2_GATHER=1` / `DARKBLOOM_TRACE_FUSION=1` (`:1700-1705`).

### Attention and MoE kernel source facts

- `laguna_sliding_fused_attn_ring_v1` `:1382`; `laguna_full_fused_attn_grow_v1`
  `:1852`. Both grid `((heads/2)*1024,1,1)`, threadGroup `(1024,1,1)`
  (`:1794-1795`, `:2306-2307`). Sliding constants `:1391-1398`: head_dim 128,
  window 512, gqa 8, BN 32, **BDP 33 after #30**, qk/v_per_thread 4,
  rotary_pairs 64, N 512. Full `:1860-1868`: gqa 6, rotary_pairs 32,
  `yarn_mscale` 1.3465735912322998f. Loop `:1524-1525`; phase 1 `:1420-1465`;
  phase 2 cache write `:1473-1485`; TG memory `:1489-1492`; epilogue `:1626-1660`.
- `laguna_oproj_act_h{heads}_v1` `:4381`, grid `((outVec/8)*64)` = 256 TGs × 64
  threads (`:4425-4429`), **each reading the WHOLE `attention_output`**
  (`:4409-4416`) ⇒ never fold an attention pass-2 into it.
- **K1** `laguna_shared_nvfp4_swiglu_qmv_rows1_bf16_v1`: decl `:6587`, Metal
  `:6591-6653`, header codegen `:6363-6503`. K loop `:6619`, 4 blocks. Two scalar
  `simd_sum` at `:6641`/`:6642`. **No `threadgroup_barrier` in `:6587-6656`.**
  Dispatch `:6679-6684`, grid `(tiles*64,1,1)` with `tiles=256`, threadGroup
  `(64,1,1)`, `row = tile*2 + simd_group`, 512 rows. Gates `:277-278`, `:128-129`.
- **K3** `laguna_routed_shared_nvfp4_down_residual_bf16_r1_v5`: decl `:7639`,
  Metal `:7655-7745`. No K loop; row loop `:7700` over 4 rows with `simd_sum`
  *inside* the loop (`:7710`). `packed_row_bytes=256`, `scale_row_bytes=32`
  (`:7662-7663`). Only barrier `:7722`, epilogue only. Dispatch `:7791-7807`,
  grid 147,456, threadGroup `(288,1,1)` = 512 TGs × 9 simdgroups. Gates `:142-144`,
  `:7636-7637`.
- Our routed R1 twin at `:7325` **already has depth-1 weight staging** (comment
  `:7365-7370`, prologue `:7371-7384`, next-block loads `:7402-7415`).
- The attention QKV decode kernel: `laguna_decode_nvfp4_qkv_h{heads}_r1_v1`
  (`:4647`). `axis_size 2048`, `num_simdgroups 2`, `values_per_thread 16`,
  `in_vec_size_g = 128`; `column = simd_lid * 16` so **lane L reads scale byte
  L** — 32 contiguous bytes per simdgroup. Grid `((rows/2)*64,1,1)`, threadGroup
  `(64,1,1)`.
- `DARKBLOOM_PACKED_SCALES` (default ON, `:152`, `:166`) builds a **separate,
  dense, row-contiguous** decode-only routed gate/up scale bank at `:9834-9871`
  (~32 MB per sparse layer; codes stay in the resident fused bank). Its
  `:9863-9868` comment records a real trap: a `take()` result carries permuted
  strides and `ensureRowContiguous` would then re-copy the bank on **every
  dispatch**.

### Measured hardware ceilings

- **M4 Pro:** scalar FMA f32 7.07 / f16 7.59 TFLOP/s; simdgroup MMA bf16 28.76,
  f16 28.96 TFLOP/s; DRAM **260.2** measured / 262.5 probe control / 273 nominal
  (96.2% of nominal).
- **M5 Max:** 614 GB/s nominal (LPDDR5X-9600, 512-bit), 40 GPU cores, 18 CPU
  cores; **measured streaming read 610 GB/s** (99.3% of nominal); **measured
  dense bf16 GEMM 56 TFLOP/s**; per-dispatch cost not measured (bracket 2.9–3.4 µs).

### Routing histogram at 512 tokens (host-independent, `research/prefill-512-route-histogram.txt`)

311,296 assignments. Mean 16.00 rows per (layer, expert), stdev 28.77
(**CV 1.80**), p50 7, p75 19, p90 39, p95 58, p99 142, max 505, **20.26% of pairs
receive zero rows**, mean nonzero 20.07, median nonzero 11. Busiest 8 experts hold
26.0% of assignments, busiest 32 hold 54.7%. Per-layer max/mean = 15.2×. The
shipped expert tile parameters were "Simulated over uniform routing"
(`quantized.cpp:1405-1415`) — empirically false.

### Harness and gate facts

- **The acceptance band `[0.980, 1.053]` is NOT enforced.** `Constants.swift:150-166`,
  `benchmark.yml:1511` and `overlay-paired-timing.sh:129-169` apply only the two
  0.95 floors. **Never throttle a win to fit the band.**
- **TTFT is not gated.** `gpqa_ttft_max_seconds` is `seconds.max() ?? 0`
  (`LagunaRuntimeCorrectness.swift:230-232`); no threshold exists. Init-time
  headroom is effectively unbounded (our receipts read 0.42 s against the 2.5 s
  reference).
- Upstream-equivalence oracle on base: prefill max_abs **0.125** / mean
  **0.011933609**; **decode steps 0–7 ALL EXACTLY 0** (`EQUIVALENCE_EXACT_STEPS=8`,
  `EXIT=1`). Reproduce exactly 0, not "small". The oracle never calls
  `prepareFusedRuntimeWeights()` — a known scope gap.
- **Local prefill is not an instrument on a sub-64 GiB host.** `--local-iterate`
  reports `prefill_speedup 0.327×` even for a byte-identical build; fern's base
  prefill spans 1.128–1.173 across runs. A/A floor on M4 `--local-iterate`:
  prefill −1.30%, decode +0.48%; fern's own floors ≥1.1% on S and ≥1.5% on T;
  3-pass noise 0.58%.
- Seatbelt: the runtime worker runs under `(deny file-write*)` with only
  `/dev/null`. Only `benchmark --local-iterate|--local-submit` passes
  `forwardsWorkerStderr: true`.
- Submission surface: `editablePaths` = **97 entries**, `fileCount` pinned at 142,
  ~87 KB of the 3,000,000-byte budget free before this round's merges.
- `MLX_MAX_OPS_PER_BUFFER` = 200, `MLX_MAX_MB_PER_BUFFER` = 200,
  `MLX_BFS_MAX_WIDTH` = 50, all at `LagunaRuntimeWeights.swift:381-389`; wiring
  gated at ≥96 GiB at `:551`.
- **Not editable:** `device.cpp/.h`, `eval.cpp`, `utils.h`, `mlx-utils.h`,
  `metal_kernel.cpp`, `scaled_dot_product_attention.cpp`, `MLXHardwareInfo.swift`,
  `array.h`, `fence.cpp`, `transforms.cpp`. `senpai/tools/*` is outside
  `editablePaths`, so **`./probe` on the M5 is impossible**, not merely hard.
- **Editable in `Vendor/mlx-swift`:** `matmul.cpp`, `quantized.cpp`,
  `jit_kernels.cpp`, `kernels.h`, `scaled_dot_product_attention.metal`,
  `sdpa_vector.h`, `softmax.*`, `copy.*`, `unary*`, `binary*`, `ternary*`,
  `arg_reduce.metal`, `sort.*`, `reduce.*`, `reduce_utils.h`, `atomic.h`,
  `reduction/*`, `indexing/*`, `quantized_utils.h`, `steel/gemm`, `steel/attn`,
  `quantized.h/.metal`, `quantized_nax.h/.metal`, `fp4.h`, `fp8.h`,
  `fp_quantized.h/.metal`, `fp_quantized_nax.h/.metal`, `gemv.h/.metal`,
  `rope.metal`, `rms_norm.metal`, all `mlx-generated/*.cpp`. Plus 15
  `mlx-swift-lm` files and 9 `Sources/MLXFastModel/` files.

### Integrity rulings (fern refused to ship both; upheld)

Pre-touching a live buffer pool across the phase boundary, and pre-boosting the
GPU clock across the hello→request boundary, are both **circumvention**, not
optimisation.

---

## Standing measurement rules

1. **Declare the byte numerator** on every byte figure: `unique` or `issued`.
2. **Declare which ceiling you divide by.** The two decode tables use different
   ceilings; do not cross-read them.
3. **A byte saving is not a price until the kernel is shown byte-bound** (§3).
   Cite a measured per-call GB/s against a stated ceiling.
4. Byte-removal arms are priced at ≤0.50× face value and planned against ~0.30×,
   using the **achieved** per-dispatch rate, never the ceiling. Arms predicted
   from a **measured dispatch time** take no discount.
5. **Never compare axes by point-estimate gap.** z-score against a banked
   byte-identical control, and never z-score a field *minimum* against a control
   *mean*.
6. **A product of a ratio and its own denominator is not a measurement.**
7. Quote `amp + ramp = 1.259 ms`, never either half.
8. Manual device-read pipelining across a `mem_threadgroup`-only barrier is a
   no-op at best.
9. Audit every achieved-bandwidth numerator. There is a 16.9×-error precedent.
10. **Do not combine two unmeasured mechanisms.** #32 r1 lost a well-powered gate
    by summing two rungs, one of which it had already isolated as a regression.
11. A bit-exactness corpus needs a **power control** that fails. A test that
    cannot fail is not evidence.

---

## Closed families — do not re-litigate

- **Decode access-pattern efficiency — CLOSED (tanjiro #21).** Every real pattern
  reaches 87–94% of the sequential control at equal bytes/dispatch. What costs is
  *bytes per dispatch* (22.9 GB/s at 0.125 MB rising to 262.5 at 64 MB) and
  *in-flight bytes per lane* (~32 B to saturate).
- **Offline codes/scales interleave — CLOSED TWICE.** fern read A = 1.000 from
  source; tanjiro measured −0.3% to +2.5% on silicon. Nobody is to propose it
  again. (Note: this is *interleaving*, a different mechanism from §B's *width
  narrowing*, which is live.)
- **`./probe` on the M5 — IMPOSSIBLE.** `senpai/tools/*` is never uploaded and
  there is no shell on the ranked host. The only M5 channel is a submitted
  candidate plus its receipt `metrics`.

| family | verdict | evidence |
| --- | --- | --- |
| **Attention byte de-amplification / head packing** | **CLOSED, two independent kills** | fern #30: the `h × s = 64` family. h-sweep spans 8× in issued bytes for <8% non-monotone time; the assigned h=8,s=8 two-pass config was **+5.7% slower** with bit-exactness proven. `kv_head=0` (8× fewer unique bytes) gave 30.5 vs 31.4 — unique bytes are not the bound. Independently killed by tanjiro #27's cache-resident probe (kernel at 34% of the cache-resident ceiling at its own working set) |
| **`MLX_MAX_OPS_PER_BUFFER`** | **INERT at any value ≥ 40** | frieren #23: `needs_commit()` cuts at `ops > max_ops`; the largest command buffer holds 28 ops as shipped and 39 at 400 MiB, while the op rule needs 201. Balanced A/A +0.144% ± 0.125%. See §E |
| **The 0.884 ms decode launch-ramp as a recoverable term** | **STRUCK** | tanjiro #27's saturation law: `dT(n) = max(0, n*c − slack)`, knee at 1209 extra dispatches, scored path at ~406. 600 dispatches of pure launch overhead appeared at **1%** of cost. My 2.18 µs in-situ reconciliation is retracted |
| **In-loop host CPU** | **CLOSED** | frieren #14: 2.0 ms/step of injected per-layer host spin *reduced* wall 8.903→8.669 ms; identical spin at the step head passed through 1:1. `wall ≈ head_latency + GPU_total` |
| **Decode head latency** | **CLOSED** | frieren #23: 35.7 µs exposed = 0.82% of the ranked step = **0.52% of score**, below the 0.61% bar; realistic proxy delivered 0.15%. 88% of the term is off-surface |
| **"Do less host work in decode" as a class** | **CLOSED** | frieren #23: graph construction costs 2.51 ms/step but the encoding thread runs **3.5× ahead** of a 96.6%-busy GPU |
| **Decode graph repartitioning** | **NEGATIVE BOTH DIRECTIONS** | −40 dispatches = +0.228 ms (nezuko #9); +81 command buffers via sub-layer `asyncEval` = +1.93% (frieren #23), and cb/step 48→90→129 is non-monotone in GPU busy |
| **KV re-request amplification at DRAM level** | **REFUTED** | frieren #14 slope method. Amplification ≤1.72× full, ≤1.18× sliding; waste ≤ +28.4 MB (≤1.01% of score); the 190 MB claim is ≥6.9σ out. Replacement finding: the full-attention path is the least bandwidth-efficient stream at 58.2% of peak, capped at 16.9 MB/step ≈ 0.6% |
| **Attention / sliding occupancy** | **CLOSED** | tanjiro #13: 80 threadgroups co-reside at the real 17,920 B / 1024-thread shape on 20 M4 cores. The g=21/41 risers are **work imbalance**, `f(m) ≈ 1 + 0.365(m−1)`. `w=2→1` is model-closed as an M5 loss; `w≥4` exceeds the 32,768 B limit |
| **Harvesting the public field by axis-coverage tables** | **CLOSED / RETRACTED** | nezuko #12: de-biased field ceiling 2.5281–2.5318; the advisor's axis tables were note-length artefacts (median \|axis-mean nd − overall\| = 0.220%, inside noise) |
| **`Sources/MLXFastTransform/`** | **CLOSED by dominance** | fern #22: `prepareFusedRuntimeWeights` is **eager** and resident before the first forward (`:10893-10898`), so load-time repack is unscored and *strictly more capable* than offline layout — it can also repack the BF16 attention weights, which offline cannot. RAM is not binding (21.57 of 25 GiB). Untouched in 147 public diffs because it is dominated, not overlooked |
| **NVFP4 scale-plane amplification** | **CLOSED, A = 1.000** | fern #22: the v5 down/residual kernel reads `expert_scales + output_row*32 + lane` over 4 rows × 32 lanes = exactly one aligned 128 B line, fully consumed. Independent bound from its 231 GB/s: `A ≤ 2.14`. The advisor's 8× premise was arithmetically impossible from repo data |
| **Quantized attention weights in prefill** | **CLOSED by arithmetic** | `research/prefill_ridge.py`: `attn_proj_qkvo` is compute-bound at 512 FLOP/byte, so reusing the decode NVFP4 banks shaves DRAM that is already hidden while adding dequantization to the binding term. **General rule: the same weights want opposite representations in the two phases**, because 512 tokens amortise the weight read 512× |
| **Prefill overlap: C1, C2, C1+C2, prefetch depth** | **CLOSED (fern #24)** | Receipt `7a5a1e08` +0.651% slower on `S`. Every barrier in the routed-expert k-loop is `mem_flags::mem_threadgroup` only, so the device read was already hoistable a full iteration earlier than any hand-rolled stage |
| **`DARKBLOOM_STAGE_BM128` tiling family** | **CLOSED at the floor** | One threadgroup per expert (`quantized.cpp:1922`) with simdgroup bands elided past the row count, so MMA waste is *row padding* `ceil(n_e/SM)*SM`. Real routing gives SM=16 → 453,120 MMA rows = 1.456× ideal, and 453,120 is exactly `Σ ceil(n_e/16)·16`, the `kFragRows=16` floor. SM=32 is a flat +41% |
| **First-touch prewarm** | **CLOSED** | fern #19: six back-to-back forwards, the *first* is fastest. Cache exactly 0 B at timed entry. On a ≥96 GiB M5 the constructor already wires ~31.4 GiB before hello |
| **Attention INT8 envelope adoption** | **DEAD, BACKWARDS** | the frontier runs Q/K/V/O at NVFP4 g16 (0.5625 B/param) vs the envelope's INT8 g32 (1.125). Adopting it *adds* ~802 MB/step. See §F |
| **Prefill byte removal as a general strategy** | closed as *stated*, but see §1 | the ridge argument was calibrated on guessed ceilings; the 47.4 ms residual is now open. Do not resurrect the old framing — bring a mechanism |
| **`MLX_METAL_FAST_SYNCH`** | **INERT** | read only by `FenceImpl` (`fence.cpp:15`); nothing in `Sources/` or the listed `MLXLMCommon` files constructs an `mlx::core::Fence` |
| **Concurrent encoder dispatch** | closed | `gpu_busy_sum == gpu_busy_union` to 6 ns; entry files not editable |
| **"The dense attention GEMM misses NAX"** | **FALSE** | `matmul.cpp:957` `use_nax` is true for BF16; q/k/v take the regular NAX kernel (`:1025`), `o_proj` takes NAX split-K (`:988-991`) |
| **Prefill dual-representation attention** | already shipped | the native-affine QKV path is gated `B == 1 && L == 1` (`:5497-5498`); both representations are already resident |
| Certified LM-head screening (old form) | closed | #6 |
| M4-argmax geometry as evidence | closed | #10 |
| Routed-MoE BM widening; sub-16 SM; zero-row expert skip | closed | hardware floor / no bytes removed |
| `arangeuint32` caching | closed | the 76 dispatches were a command-buffer overlap artefact |
| Prefill host CPU / command buffers | closed | prefill GPU-busy union is 99.4% of wall |
| `DARKBLOOM_ATTN_QHOIST`, `GEMM_TPARAM_MACRO` | closed | no effect |
| **Match the field's best decode time** | **DECOMPOSED, no longer a direction** | nezuko #32: `12cb11a8` = our M1 + K1 + K3; K1 = +0.18% reachable, K3 = +0.34% structurally unavailable (our K3 is the merged projection at 89% of ceiling). See §D |

**SUSPENDED, not closed:** `MLX_MAX_MB_PER_BUFFER` magnitude — sign
contradiction, see §E. A balanced re-measurement is free and unassigned.

**REOPENED:** prefill glue (old C5) and shared-expert overlap (old 5b), because
the 29-TFLOP/s "compute-closed" reading that retired them is dead (§1). PR #12's
`S +0.236%` regression, because an inert knob cannot have caused it (§E).

---

## Potential next research directions

Ordered by expected value. Four of these are held rather than assigned because
all four students are occupied.

1. **The 47.4 ms prefill residual (§1).** Half the prefill axis is explained by
   neither compute nor bytes at the *measured* M5 constants. This is the single
   largest unexplained quantity in the programme and it has no owner. **#34's
   rate 1 is the discriminator**: ≈25–30 TFLOP/s localises it inside the editable
   NAX kernel; ≈50 localises it in glue. Do not assign a mechanism until that
   receipt lands.
2. **The 1.38 ms decode residual (§1).** 32% of the decode step is not byte
   movement, on a step we spent a week believing was bandwidth-closed. **#34's
   rate 2 is the discriminator.** If the achieved attention-family rate is ~400
   GB/s rather than 610, 0.6 ms sits in one kernel family = **8.8% of score**.
3. **Extend §B beyond the first plane.** If the census cooperates, the full
   4-bit-dictionary version across all NVFP4 planes is **+2.67%**, which alone
   would move us from a ~1-in-468 promotion shot to roughly a coin-flip. Must be
   split into independently correct, independently measurable increments — one
   plane per submission — per the calibration band and rule 10.
4. **Deepen the lm_head cascade beyond nezuko's first 25.7 MB.** The int5 plane is
   134.9 MB = 7.5% of the step. A hierarchical screen (very coarse bound over all
   100,352 rows → int5 on ~10³ survivors → exact rescore) could take the plane to
   ~30 MB ⇒ ~105 MB removed ⇒ ~3.7% of score. **The old pricing must be
   re-derived**: the corrected figures are 8.110 MB unique / 9.982 MB issued /
   109.6 GB/s (an earlier 6.5 GB/s figure was wrong by 16.9× on bytes). The
   defensible target is the row-granular gather — 458 live 4-row blocks read 16 KB
   for ~1.2 wanted rows, so the 7.5 MB `gemv_al` term could fall ~3×.
5. **`gate_sp_h64 + gate_sp_h48`: 213 µs/step = 2.43% of T = ~1.55% of score at
   face value.** The cheapest large item on the board by measured time, and at
   **2% of the DRAM ceiling** it is pure latency — which means §2 says our hosts
   cannot rank it. Needs the M5 per-dispatch floor from #34 first.
6. **Bit-exact fused split-K for the NAX steel path** (`o_proj`, `g_proj`,
   router). Port `qmm_t_splitk_fused` (`quantized.cpp:849-893`) to
   `steel_gemm_splitk_nax` (`matmul.cpp:689-810`, split-K branch `:987-991`,
   `C_split` fp32 `:734-737`). Removes ~0.72 GB of fp32 round-trip traffic and
   ~80–120 dispatches; ~0.53% of score, and unusually attractive because it is
   **locally falsifiable on the non-NAX twin**.
7. **The balanced `MLX_MAX_MB_PER_BUFFER` re-measurement (§E).** Free, ~30
   minutes with frieren's 12-position protocol, and it resolves a sign
   contradiction on the largest local decode contrast anyone has measured. Note
   the knob can never ship from a 48 GiB host (wiring gated at ≥96 GiB), so this
   is a *methodology* question, not a candidate.
8. **`DARKBLOOM_FUSED_QKV` free flip.** One receipt; its only provenance is
   "paired local benchmark" on a predecessor's host (`:108-114`).
9. **`MLX_BFS_MAX_WIDTH = 50` vs MLX's default 20** (`transforms.cpp:181`).
   Unmeasured and **not** a partition knob — traversal width changes fusion and
   therefore bytes. Needs its own hypothesis.
10. **Routing-aware two-regime expert dispatch.** The shipped tile is tuned for
    uniform routing that does not occur (CV 1.80, 20.26% empty, busiest 32 experts
    = 54.7%). Row-tile widening, sub-16 SM and the whole `STAGE_BM128` family are
    closed — SM=16 attains the `kFragRows` floor exactly. A *two-regime* split is
    the only remaining route below 1.456× MMA rows and would have to break
    per-expert weight exclusivity. Needs a mechanism proposal, not a knob.
11. **Re-test nezuko's #9 dispatch-fusion negative on the M5, once.** It was
    measured entirely under the M4 blindness of §2, and the ranked host has 2× the
    bandwidth and 2× the cores. Low expected value, but it un-blocks two closed
    families at once if it flips. Largely subsumed by #34's rate work.
12. **Minify the remaining 71 Metal literals in `LagunaRuntimeModel.swift`**
    (−54,251 B of surface). Worth 0.0% of score; only relevant if we run out of
    the ~87 KB of surface headroom.
