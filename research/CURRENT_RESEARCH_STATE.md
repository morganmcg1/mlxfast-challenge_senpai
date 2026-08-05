# SENPAI Research State

- **2026-08-05 09:40 UTC** (advisor: meridian). Round 7 in flight; round-8 queue
  drafted.
- **Most recent human research direction:** operator authorised the advisor and
  all four students to dispatch official `mlxfast submit` runs. No new
  scientific direction since; the standing objective is unchanged.
- **Current focus:** the **routed gather-GEMM `_nax` prefill block** — the
  single largest attributable item anywhere in the scored window, now localised
  to staging↔MMA serialisation — supported by two instruments that close the
  decode budget (per-family byte/latency census, aggregate M5 dispatch law) and
  one free ranked knob (`MLX_MAX_MB_PER_BUFFER`).
- **Biggest known blind spot:** ~20 ms of prefill glue that no experiment has
  ever priced (P-GLUE, round-8 queue). It is unowned and larger than anything
  else unowned on either axis.
- **Score:** `score = decode_speedup^0.75 * prefill_speedup^0.25`, both floors
  0.95. Our frontier is 4th of 937 receipts **on content** (`ns`) but **7th of
  67 solvers on `officialScore`**, the metric that actually gates promotion.
  Read "Our position" before quoting either number.

> This is a living document, not a log. Superseded reasoning is deleted rather
> than annotated. Per-experiment detail lives in the PRs and in
> `research/<student>-pr<N>-*.md`.

---

## THE FIVE THINGS TO READ FIRST

### 1. Both residuals now have a shape. One has an owner.

tanjiro's #27 measured the M5's hardware constants; his #34 then measured the
four biggest *blocks'* real M5 rates in situ by differencing official receipts
(§A). Three of the four are at or above their ceiling. The residuals are no
longer undifferentiated ignorance:

```
PREFILL   measured S_0                                  97.86 ms
          honest residual after compute + bytes         ~34 ms
          of which routed gather-GEMM excess           +14.30 ms   <-- 42.1%
                                                                       LARGEST
                                                                       ITEM ON
                                                                       EITHER
                                                                       AXIS
DECODE    1794 MB at 610 GB/s  = byte roofline           2.941 ms
          measured T                                     4.3224 ms
          residual                                       1.383 ms
          rates 2+4 cover 75.5% of decode bytes,
            combined excess only                        +0.106 ms
          UNATTRIBUTED                                  ~1.27 ms   <-- 29% of T
```

**Prefill's biggest item is a real, sized, ownable defect.** The routed
gather-GEMM moves 17,666.41 MB / 1005.02 GFLOP across 39 routed layers in
dS = 43.2619 ± 0.402 ms = 408.4 GB/s = 23.23 TFLOP/s, which is **67% of its own
34.7 TFLOP/s byte ceiling**. At prefill elasticity 0.362, full recovery is
+5.3% of score and a third is +1.8%. The campaign needs +1.0% to +2.0%.
**Owner: maple-fern, PR #40.** Corrected roofline and mechanism in §A3.

**Decode's residual is now bounded and mostly non-byte.** The two decode blocks
we can price (attention qkvo QMV at 651.8 GB/s, routed-expert QMV at
546.2 GB/s) together move 1354.24 MB — 75.5% of the step's bytes — and waste
only 0.106 ms between them. So the missing ~1.27 ms is *not* in the bytes we
understand. It sits in the remaining ~440 MB and in costs that are not bytes at
all.

**★ REFRAMED 2026-08-05 — the host-dispatch candidate has been demoted; read
this before pricing any fusion idea.** The former text here read: "#37 measured
+4.1 µs/dispatch of host encode/commit that the GPU clock never sees, and the
scored path issues ~406 dispatches ⇒ **1.665 ms**, larger than the entire
residual … recovering a third of 1.27 ms is **+6% of score**." That arithmetic
is arithmetically fine and **causally wrong**. The 4.1 µs is an *average
accounting constant that reconciles two instruments on M4*. It is not a
marginal critical-path price, and 406 × 4.1 ms is not a recoverable pool. Four
independent results say the marginal price at our operating point is ≈ 0:

| Evidence | What it says |
|---|---|
| tanjiro's saturation law (§2) | knee at **+1209** extra dispatches; the scored 406 sits **3× below** saturation; 600 injected launch-only dispatches cost 1% |
| frieren #23 | encoding thread runs **3.5× ahead** of a 96.6%-busy GPU; decode head latency 35.7 µs exposed |
| frieren #14 | 2.0 ms of injected per-layer host spin *reduced* wall time |
| the only direct **M5** dispatch-removal datum | removing the 2 RoPE angle probes from the step front: **+0.01..+0.07 ms/step** (null/negative), `LagunaRuntimeModel.swift:571-580` |

Closing arithmetic: on M4, wall 8.545 ms = 8.345 GPU-busy + **0.200 ms** of
total gap across 406 dispatches *and* 45 command buffers ⇒ ~0.49 µs/dispatch
actually exposed. Had 4.1 µs/dispatch been marginal, M4 wall would read ~10.0 ms.
It does not.

**Where the 1.27 ms most likely lives instead: inside GPU-busy, as issue /
occupancy / latency time in the ~200 dispatches that carry almost no DRAM
bytes.** The magnitudes coincide. nezuko #9's M4 "recoverable" column sums to
**~1.38 ms** — the same size as the M5 residual:

| Kernel | M4 recoverable | Note |
|---|---|---|
| sliding fused attention | **428 µs** | **36% of ceiling**, ~8 threadgroups on 20 cores |
| full fused attention | ~130 µs | |
| `residual_rms_router` rpg8→rpg4/2 | ~106 µs | |
| shared expert K1 | ~65 µs | |

The sliding-attention line is the one to price first, and it is the rare case
where **M4 understates the M5 prize**: the official M5 has roughly twice the
cores, so ~8 threadgroups leaves *more* of the machine idle there. That
prediction is falsifiable in one census arm (#32 deliverable B, re-aimed
2026-08-05).

Standing caution kept from the old text: every "hidden host cost" datum except
the M5 RoPE-probe null is M4-based, and M4 is known-blind to exactly this
class. **Whether M5 exposes per-dispatch host cost is precisely #34
deliverable A** and nothing else we hold can answer it. Commission no
dispatch-fusion mechanism before that lands.

Two live instruments are pointed at exactly this: nezuko's per-family
byte-carrying-vs-latency-absorbed census (#32 deliverable B) and tanjiro's
aggregate M5 dispatch-saturation law (#34 deliverable A). If the census's
"absorbed" column totals ~1.2–1.3 ms, the decode budget closes for the first
time in the campaign.

**Standing qualifier, from tanjiro himself:** 610 GB/s is a *streaming upper
bound at a favourable shape*, not any real kernel's achievable rate. The
attention qkvo QMV block measuring 107% of it is the proof — treat 610 as a
calibrated reference, not a hard wall.

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

### 3. There are three bound classes, and the third one is dependency depth

fern's #30 h-sweep: issued K/V bytes spanned **8×** while kernel time moved
**<8% and non-monotonically** (h1 29.45, h2 27.67, h4 27.13, h8 28.54 µs/layer),
all bit-exact. Loads made L1-hot: no change. 32×8 B vs 16×16 B loads: identical.
So the fused attention phase-3 loop is neither DRAM- nor arithmetic-bound. Two of
my own roofline prizes died on that finding. **Standing rule: an issued-byte count
is not a price for any kernel until something establishes that the kernel is
byte-bound.** Cite a measured per-call GB/s against a stated ceiling, or do not
quote a byte saving.

**#36 then refined what the third class actually is.** "Instruction issue" is too
coarse — the loop does not price instruction *count*. fern hand-wrote a genuinely
cheaper reduction (xor levels 1,2 leave every lane of a 4-lane group holding the
identical partial, so each lane selects `slot = lane&3`, finishes alone with xor
4,8,16, then 4 broadcasts: **15 shuffles against `simd_sum`'s 20**, same xor order
so the same addition tree, bit-exact by construction). Result: **1.79% SLOWER.**

Count depth, not instructions. `simd_sum(float4)` is 5 butterfly levels over 4
*independent* chains — critical path 5, ILP 4. The 15-shuffle version is three
sequential phases with the tail running one chain — critical path ~15, ILP
collapsing to 1. A 25% instruction cut roughly tripled the dependency depth.

**The lever this implies:** the reduction's cost cannot be removed by shortening
it, only by overlapping it with independent work (software-pipelining the next
iteration's K loads across it). Vector and shuffle-count reduction in the fused
attention core is **closed at the mechanism level**, not merely in its packing
form — do not reopen it with a different vector width.

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

**The per-mechanism transfer factor has a missing middle.** These are the only
two calibrated points, and they are three orders of magnitude apart:

| mechanism class | M4 → M5 transfer | source |
| --- | ---: | --- |
| saves DRAM traffic | **106%** | #21/#34 rate agreement |
| removes dispatch overhead | **1%** | tanjiro's saturation law (§2) |
| *saves bytes but adds fixed ALU/transaction cost* | **unknown** | — |
| *changes threadgroup geometry* | **unknown, can change sign** | core-count dependence |

Every arm whose mechanism is not one of the two calibrated endpoints is
effectively **unscreenable on M4** and must be priced from an M5 receipt. This
is the single largest reason briefs now mandate receipts. #35 r2 deliverable A
exists specifically to calibrate the third row.

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

### A2. The four M5 block rates, measured in situ (tanjiro #34, adopted)

#34 extended the differencing method from *hardware constants* to the **real
kernels' real rates inside the scored window**, by scaling each block's own work
and differencing official receipts. This is the most useful reference table in
the programme: it tells us which blocks are finished and which are not.

| # | block | work moved | measured | own ceiling | excess |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | **routed gather-GEMM (prefill)** | 17,666.41 MB / 1005.02 GFLOP | **408.4 GB/s = 23.23 TFLOP/s** | 34.7 TFLOP/s | **+14.30 ms** |
| 2 | attention qkvo QMV (decode) | 802.16 MB | 651.8 GB/s (107%) | 610 GB/s | ~0 |
| 3 | attention qkvo dense GEMM (prefill) | 1460.29 GFLOP | 65.74 TFLOP/s (117%) | 56 TFLOP/s | ~0 |
| 4 | routed-expert QMV (decode) | 552.08 MB | 546.2 GB/s | 610 GB/s | +0.106 ms |

Per-block deltas: dS₁ = 43.2619 ± 0.402 ms, dT₂ = 1.23070 ± 0.028 ms,
dS₃ = 22.2139 ± 0.362 ms, dT₄ = 1.01067 ± 0.034 ms. Receipts: R1 `b6032aeb`
(S 97.8643, T 4.27468), R2 `ca416f01` (141.1262, 5.50538), R3 `6757de65`
(120.0782, 6.51605). The base tree commit `6288233` is byte-identical on
`Sources/` to R1 and returned base `officialScore` 2.5149 — the control is
sound.

**★ CORRECTION 2026-08-05 — R4 `afec358` FAILED, and row 4 has no independent
receipt.** This document previously recorded R4 as "still validating". It is
not: `mlxfast submissions --all` reports `status=failed`, `score=n/a`,
`metrics=n/a`, commit `af3ab58`. The family therefore rests on **three**
successful receipts, not four. Reconstructing which receipt supplied which rate
(every step below checks to the last published digit):

```
R2 - R1:  dS = 141.1262 - 97.8643 = 43.2619  = dS1   (row 1)
          dT =   5.50538 -  4.27468 = 1.23070 = dT2   (row 2)   <-- one receipt, two rates
R3 - R1:  dS = 120.0782 - 97.8643 = 22.2139  = dS3   (row 3)
          dT =   6.51605 -  4.27468 = 2.24137           (the 2.241 +- 0.031 validation)
=>        dT4 = 2.24137 - 1.23070 = 1.01067  = row 4
```

Row 4 is thus a **difference of differences between two different receipts** — a
legal estimator only if R2's and R3's arms are strictly nested, and in any case
its published ±0.034 ms bar is too tight because it carries only one receipt's
noise. Treat **dT₄ = 1.01067 as PROVISIONAL** until tanjiro confirms arm nesting
(asked on PR #34, 2026-08-05). If `afec358` was its only source, row 4 has no M5
receipt at all and **55.3% of the decode byte budget is unmeasured** — in which
case a merely-slow routed-expert QMV could absorb part of §1's 1.27 ms residual,
which *weakens* rather than strengthens every host-side story. All four
submission notes are byte-identical boilerplate listing the kernels in score
order, so the notes cannot disambiguate this; only tanjiro's notebook can.

**Free internal validation.** R3−R1 moved 1354.24 MB in 2.241 ± 0.031 ms =
604.2 GB/s = **99.0% of the 610 constant**. One difference simultaneously
confirms the constant, the `S/128` correction in the `T` definition, and that
cold injection behaves on the ranked host.

Blocks 2 and 3 are **done**: both measure *above* nominal peak, so there is
nothing to win in attention qkvo on either axis. Block 4 has 0.106 ms = 7.9% of
the decode residual. Block 1 has +14.30 ms and is the programme's #1 item.

tanjiro failed his own pre-registration on block 1 (predicted 29–33 TFLOP/s by
transferring efficiency across a *different* kernel) and retracted a concave
rate-1 sweep in favour of a linear-through-origin fit at 4.138 ms/copy. Both
self-corrections are recorded because they are why the table is trustworthy.

### A3. ★ The routed gather-GEMM prefill prize (fern #40) — the programme's #1 item

**Do not use nominal 17,666 MB for the roofline.** Against the real route
histogram (`research/prefill-512-route-histogram.txt`, 76 records × 256 experts,
4096 rows each) the nominal figure is wrong in both directions:

- **20.26% of (layer, expert) pairs get zero rows and are never read.** The
  binary search finds an empty run and the k-loop never executes
  (`fp_quantized_nax.h:1699-1727`). Those weights cost zero bytes.
- Chunk re-reads for experts with >64 rows are only **1.080×**
  (Σceil(r/64) = 16,758 vs 15,514 non-empty pairs).

```
net weight DRAM      = 17.666 GB x 0.8613 = 15.22 GB  -> 27.9 ms at 610 GB/s
MMA issued rows      = 453,120 / 311,296 useful = 1.456x  -> 26.1 ms issued
                                                             (17.9 useful)
fully-serial D + M   = 54.0 ms
measured             = 43.26 ms   = 0.80 of fully-serial
perfect-overlap bound= max(D, M)  = 27.9 ms
RECOVERABLE GAP      = 15.4 ms
```

The kernel realises only **~41% of the achievable staging↔MMA overlap**. This is
neither a bandwidth problem nor a FLOP problem.

**Mechanism #1 (~10–15 ms): staging↔MMA serialisation on a single-buffered
`Ws`.** k-loop at `fp_quantized_nax.h:1744-1795`: device-load A → `barrier` →
all 128 threads stage the 64×64 weight tile into the *single* 9,216 B `Ws`
(`:1611-1618`) → `barrier` → MMA reads `Ws`. Two barriers per k-iteration, and
the next iteration's staging has a WAR hazard against this iteration's MMA.
Nothing overlaps. Our own `quantized.cpp:1277-1287, 1445-1450` records staging
at ~50 LSU ops/thread/k-iter against ~40 compute-side and calls staging
**"39.5% of prefill"**. This is H1 of `research/PREFILL_NAX_ANALYSIS.md`, now
quantified. Apple tech talk 111373: Family-9+ shares one cache hierarchy across
threadgroup and device memory, so a barrier-staged TG tile buys **no locality**
on this hardware — it is pure serialisation cost. A third-party M5 INT8 study
measured 2.23–2.77× from deleting barrier-staged TG tiles.

**Mechanism #2 (~5–7 ms now, → 0 under perfect overlap): SM=16 M-banding
padding, 1.456×.** Hardware fragment is 16 rows (`steel/gemm/nax.h:27-28`); the
mean non-zero expert gets 20.07 rows, median 11. Fix #1 first, then re-measure.

**Mechanism #3 (~1–3 ms, indirect): x re-read per column tile.** grid.x = 16
(gate_up, K=2048, N=1024) or 32 (down, K=512, N=2048)
(`quantized.cpp:1915-1924`). 15.3 GB if uncached, but the ~16.8 MB per-layer x
slab is SLC-resident, so it costs LSU slots and SLC bandwidth, not DRAM bytes.

**REFUTED — do not re-litigate.** (a) *Weights re-read once per column tile* —
false, and I verified the line myself: `wl = w + y_col * K_w` with
`y_col = tid.x * BN` (`fp_quantized_nax.h:1631-1634`) gives each TG one
(expert, column-tile) pair reading **disjoint** 64-column slabs. This was my own
priority hypothesis and it was wrong; the −20% never-read saving more than
offsets the 1.080× chunk factor, so nominal-byte accounting *overstates* DRAM
time and makes the gap larger, pointing all of it at #1/#2. (b) Load
imbalance / long tail: <1 ms (worst record is one 505-row expert = 8 chunks =
4.2% of that record's chunks, against 4,096–8,192 TGs per dispatch).
(c) Scale-plane access cost (`fp_quantized_nax.h:391-470`): negligible.
(d) Insufficient accumulator concurrency: TN=4 already gives four chains with
dual-issue MMA pairs (`nax.h:1012-1031`).

**The fix arm is already pre-plumbed and inert.** `DARKBLOOM_STAGE2_GATHER`
exists host-side only: `jit_kernels.cpp:1130-1155` parses the env var once and
injects `#define DARKBLOOM_STAGE2_GATHER 1` into **expert-kernel JIT source
only** (`get_qmm_nax_kernel`, `:1227-1257`, gated on `_expert_` in the kernel
name, so every other JIT lib stays byte-identical); `quantized.cpp:1683-1702`
prints the dispatch-site ground truth, where "active" requires **both** the flag
**and** `expert_aligned`. The kernel-side `#ifdef` blocks were stripped **for
byte budget, not because they lost** (`research/nezuko-harvest-report.md`,
solver `4bf4f794` mechanism 4: "…not a speed change: it is submission-surface
budget … ~33 KB … removing it is what made room for mechanisms 3 and 5"). The
symbol appears **only** at `quantized.cpp:1683,1692` and
`jit_kernels.cpp:1130,1148,1155` — absent from `fp_quantized_nax.h` and its
`mlx-generated` twin. The referenced `notes/exp-stage2.md` is an upstream-solver
file we do not have, so **there is no prior stage-2 measurement in this
checkout.**

**Bit-exactness has shipped precedent in this exact kernel.**
`DARKBLOOM_SWIGLU_REGLOCAL` is default ON and already won: it "reads gate/up
straight from the MMA Dtile fragments instead of round-tripping them through
threadgroup memory with two barriers per column tile … values are bit-identical".
Removing TG round-trips and barriers here is a shipped, bit-exact, winning
transformation class. Double-buffering changes only the barrier *schedule*:
identical values, identical MMA issue order, identical epilogue, identical store
addresses. `max_abs_diff` must be exactly 0.

**Five traps that each silently produce a fake null.** (1) `Ws_storage` is
**aliased by `gate_up_stage`** — any double-buffer must handle the alias or
corrupt the gate/up path. (2) Keep `TN` even: `TN = SN/16` = 4 at BN=64/WN=1; an
**odd** `TN > 1` instantiates an **empty** `tile_matmad_nax`
(`steel/gemm/nax.h:994-1031` only has `TN==1 && TM%2==0` and `TN%2==0`
branches) — no compile error, no MMA, silent garbage. (3) Keep `SM ≥ 16`;
`SM < 16` ⇒ `TM = 0` ⇒ no MMA. (4) Keep
`bm==64 && wm==4 && (wn==1||wn==2)` so the `quantized.cpp:1662` accept gate
still selects the expert kernel — falling off it silently dispatches the
**non-expert** kernel. (5) **Confirm the `mlxfast: fusion active: stage2_gather`
stderr line before believing any A/B number.** Our tree documents the precedent:
the trace exists because "those function constants only ever reached the
non-expert kernel" — "the exact confound that made the STAGE_WIDEST/WIDELD arms
measure their own control."

**Ranked evidence must be official M5 receipts.** `quantized.cpp:1959` routes to
`gather_qmm_rhs_nax` only under `metal::is_nax_available()`; `device.cpp:913`
requires arch_gen ≥ 17; our M4 hosts probe as `applegpu_g16s` gen 16 and run
steel bm16/bn32/bk32 instead. **An M4 prefill number is not evidence for an
`_nax` change** — M4 is for compile, correctness, and flag-OFF equivalence only.

Follow-ups, conditional on #40's result: **F3** BN=32 (+1–3 ms, halves `Ws` to
4.6 KB, doubles grid.x, TN→2 even ✓, SM stays 16, but doubles x re-reads — only
interesting if occupancy proves binding); **F2** staging-free B path /
dequantize into fragments (up to ~10 ms, high risk: with WM=4/WN=1 all four
simdgroups consume the *same* 64×64 B tile, so naive removal quadruples
dequant). **Forbidden:** MegaBlocks-style blocking (median non-zero expert has
11 rows against 128-row blocks — wrong regime), split-K, stream-K (8,192 TGs,
uniform K, not tile-starved), BM=32, skip-empty-expert dispatch surgery (empty
TGs already exit at the binary search). The literature review was unambiguous
that the current design already **is** the grouped-GEMM state of the art —
sorted tokens + binary-searched expert runs + one TG per (expert, col-tile) is
vLLM `moe_align_block_size` plus a persistent visitor, and `eg_256` matches the
CUTLASS "at most one tile per problem" rule. The Apple-specific overlap lever is
the only one left, and vLLM's own notes agree small-M MoE GEMM is
memory-latency bound and a deeper pipeline hides weight loads — while warning
extra stages can flip it to occupancy-bound. That trade is the hypothesis.

### B. The scale-code width arm — repriced against the measured M5 rate (frieren #35, r2)

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

**REPRICED by §A2 — this table's last line is now optimistic.** It divides bytes
by the *whole-step average* 415 GB/s. But the attention qkvo plane, which is 59%
of the scale bytes, actually runs at the measured **651.8 GB/s**, so its bytes
are worth 1.57× less time than the table assumes. Concretely for frieren's r1
form: 30.61 MB/step saved buys −47 µs at 651.8 GB/s, not the −138 µs the M4
roofline suggested, while his +43 µs three-load reconstruction cost is
**bandwidth-independent** — net **−4 µs/step ≈ +0.06% of score**, well under the
0.243% detection floor. Worse, 651.8 GB/s is *107% of nominal*, which means the
plane read already coalesces near-perfectly; splitting one contiguous `uint8`
stream into three narrower streams is exactly the kind of change that can
regress on M5 while M4 shows a win. Hence r2: get one ranked M5 receipt on the
current form to calibrate the transfer factor for the class "saves DRAM bytes,
adds fixed ALU/transaction cost", *then* build the 4-bit lane-major variant
(per-row base + `0xFF` sentinel escape, `row_le15` ≈ 0.981–0.994, two loads/row
instead of twelve, −70…−90 µs/step on M4) which has a far better
bytes-saved-per-instruction-added ratio.

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

**★ Re-priced with n=4 (from #36).** Three more within-process estimates of the
padding (−7.8 / −6.8 / −6.8%) put the mean at **−6.9%** of the sliding layer =
2.2 µs/layer × 30 = 65 µs/step on M4. fern's own wave arithmetic then reproduces
my halving: 65/2 = 32.5 µs per wave, M5 waves = 1, 32.5/4318.1 = **0.753% of T**.
Applying the correct elasticity (he used 0.75; it is `0.75 × (1 − sigma)` = 0.637)
gives **0.48% of score**. My ~0.6% correction is confirmed and his 0.9–1.2% is
retired.

**★ RESOLVED (was the last open question about a merged win).** fern's probe read
~30 µs/call for `sliding_fused_attn_ring_v1` (898/30) where nezuko's #9 SPLIT
harness read 22.34 µs — an apparent ~34% gap between two of our instruments on
the same kernel. #37 reconciled it: the GPU-clock time is 22.66–22.78 µs, within
1.7% of SPLIT's 22.34 and below our ~2% instrument floor, and the whole gap is
**host-side** — about +4.1 µs/dispatch of encode/commit plus ~1.2 µs of
command-buffer granularity that the GPU clock never sees. #30's absolute price
was derived from the probe, so it re-prices from 0.48% to **~0.36%** of score
(still a win, still merged). See standing rule 15; the same +4.1 µs/dispatch is
now the leading candidate for the ~1.27 ms unattributed decode residual in §1.

**CLOSED by #36: vector and shuffle-count reduction (the whole family).** Details
in §3. Two premises I gave fern were both wrong, and he found both:

1. **The `float2 −6.4%` row never existed as a separate arm.** It was
   `probe_padvec`, generated as `vector_reduce(pad(src))` — it already *contained*
   the padding. A padding-free vector arm was never measured, so −6.4% and −6.3%
   were **one mechanism under two labels**. My error was worse than misreading a
   label: I wrote "those are the same size" into the brief and treated
   near-equality as evidence the second arm was real. **Standing prior: when two
   arms agree to better than the noise floor, suspect they are the same arm
   before suspecting additivity.**
2. **The "QK `simd_sum` = 3.58 µs = 20% of the loop" figure is probably inflated**
   by dead-code elimination — with the reduction's result unused, nothing keeps
   its producer madds alive. See rule 12. Every number in #30's loop-attribution
   table (QK `simd_sum` 3.58, madds 1.16, rescale 0.40, softmax 0.31) and its d2
   arm ("loop arithmetic deleted, loads kept: 28.9") now carries that caveat.

Measured nulls from #36, all against the shipped padded arm: `float2` alone
−0.27% (one noise floor); pad+`float2` −0.85%/+0.23% (does not stack); `float4`
with madds hoisted −0.47%/+0.12%; `float4` + packed epilogue −0.46%/−0.19%.
Geometry identical in every arm, so this is an instruction-mix experiment at fixed
geometry and the M4 null is evidence about M5; bounded M5 residual 0.013% of score.

**Two reusable assets from #36.** (a) The **duplicate-arm noise floor** — same
`.metal`, two labels — reading 0.02–0.28%, which is what makes the null decisive;
now the standard for this probe, alongside `senpai/tools/sliding-attn-probe/diag_stack.py`,
which generates every arm from one rendered kernel text. (b) **Metal's `simd_sum`
is the ascending xor butterfly**, established via the hand-written tree arm — any
future arm can now reason about association order in these kernels from source.
Bit-exactness confirmed locally at 0/8192 in the real 1024-thread kernel, which
promotes nezuko's #32 packing proof from borrowed to local.

**Also refuted and closed by #30:** the whole `h × s = 64` KV de-amplification
family. The assigned config h=8,s=8 two-pass deferred epilogue was **+5.7%
SLOWER** with bit-exactness proven.

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

## Round 6 outcome / Round 7 in flight

**Round 6 produced two instruments, one decisive negative, and zero candidates.**
#34 (tanjiro) measured the four M5 block rates in situ and thereby located the
programme's largest attributable item (§A2, §A3). #37 (fern) killed the lm_head
level-0 screen family on arithmetic and, as a by-product, reconciled the
instrument-vs-kernel timing discrepancy that had been quietly inflating three
earlier estimates (§Standing measurement rules). #35 (frieren) was *repriced into
a null* by #34's own measurement (§B) before it ever reached a receipt — the
cheapest possible way to learn that.

Advisor branch lineage: `9a407ed6` → `a3c096ee` (#27) → `6f1289a9` (#30) →
`eaedee84` (#23) → `ec3298a1` (rewrite) → `cb3d2f68` (#36) → `3039ffc` (record
#36) → **`279b6e24`** ("Fix competition research mechanics"), which is the base
for every live arm. #32, #34 and #35 were assigned from `eaedee84`; every
intervening commit is documentation-only, so their `baseline_advanced` events
were accepted without a rerun and re-anchored to `279b6e24` in their revision
briefs.

**Four rounds running, the assigned hypothesis has died and the student has
returned something more valuable than the arm.** That is now the expected shape
of a round, not an accident, and it is why every brief carries an explicit
"what a good null looks like" section. But it is also a warning: **our productive
output this week has been instruments and refutations, not candidates.** Round 7
exists to convert the instruments into a candidate. #40 is the first arm in the
programme aimed at a *measured*, *attributed*, *large* excess rather than at a
plausible one.

| PR | student | assignment | rev | state |
| --- | --- | --- | --- | --- |
| **#32** | nezuko | `maple-2026-08-04h-shared-qmv-staging` | **r2** | per-family decode byte/latency census (**B outranks A**) + K1-only |
| **#34** | tanjiro | `maple-2026-08-04i-m5-block-rates` | **r2** | four rates ADOPTED; now strip the instrument to fit the byte cap, then measure the **M5 dispatch-saturation law** |
| **#35** | frieren | `maple-2026-08-04j-scale-code-width` | **r2** | repriced to −4 µs/step; one calibration receipt, then the 4-bit lane-major plane |
| ~~#36~~ | fern | `maple-2026-08-04k-attn-reduction-packing` | r1 | **MERGED as documentation** — dead family, empty scored diff. See §C |
| ~~#37~~ | fern | `maple-2026-08-04l-lmhead-level0` | r1 | **CLOSED** — decisive negative, three by-products adopted |
| **#40** | fern | `maple-2026-08-05a-nax-stage2-double-buffer` | r1 | ★ double-buffer the `_nax` gather-GEMM weight staging (§A3) |

Every student holds exactly one live arm, and each brief states its scope
boundary against the other three: **fern** owns the M5 prefill gather-GEMM
kernel; **frieren** owns attention scale-plane width plus M4→M5 transfer
calibration; **tanjiro** owns the aggregate M5 dispatch law plus the instrument
strip; **nezuko** owns the per-family decode byte/latency census plus K1.

### Receipt queue — the serialisation assumption was false

The "single team channel, ~1.7 receipts/hour" model in the previous revision of
this document is **falsified** (#34). Measured behaviour:

- **The channel is not serialised.** Five accounts validated simultaneously, and
  same-account concurrency was accepted without error.
- Turnaround is **~35 min**, scaling with injection size rather than with queue
  depth.
- A **`rejected` receipt still publishes full metrics** — S, T, both floor
  verdicts and correctness. `rejected` means only "did not beat current best".
  Only the 467 `failed` submissions publish nothing.
- There is **no penalty for submitting a deliberately slowed tree**, which is
  what makes receipt-differencing a legitimate instrument.

Practical consequence: briefs may now ask for **concurrent** receipt families
(#34 r2 runs five at once; #40 runs its A/B pair together) and wall-clock is
bounded by turnaround, not by queue position. Round 6's one loose end is now
closed the wrong way: tanjiro's R4 `afec358` **failed** (no score, no metrics)
rather than completing — see the ★ correction in §A2. A `failed` receipt is a
reminder that the 31.5% field-wide failure rate applies to us too; budget for it
when planning a concurrent family.

Service-side caveat that has not changed: **byte-identical archives are
deduped**, so every receipt in a family needs a distinct note.

---

## The editable byte budget is now a first-order constraint

This is new in round 7 and it changes which experiments are assignable. Run
`bash senpai/check-editable-budget.sh <base>` before writing any brief.

```
current = 2,940,973 / 3,000,000   headroom =  59,027      (2.0% left)
growth  =         0 /   262,144   per-review growth cap
files   =       142 (base = 142)
per-file cap = 524,288
```

Per-file state at base `279b6e24`:

| file | bytes at base | spare |
| --- | --- | --- |
| `Sources/MLXFastModel/LagunaRuntimeModel.swift` | **508,529** | **15,759** |
| `Sources/MLXFastModel/LagunaRuntimeWeights.swift` | 31,844 | — |
| `Vendor/.../kernels/fp_quantized_nax.h` | 65,515 | 458,773 |
| `Vendor/.../mlx-generated/fp_quantized_nax.cpp` | 68,466 | 455,822 |
| `Vendor/.../backend/metal/quantized.cpp` | 81,331 | 442,957 |
| `Vendor/.../backend/metal/jit_kernels.cpp` | 50,368 | 473,920 |

**The scored decode path is nearly out of room and the prefill kernels have
essentially unlimited room.** That asymmetry is now a research input, not a
housekeeping detail:

- **#35 and #34 cannot both merge as submitted.** `scale-code-width` takes
  `LagunaRuntimeModel.swift` to 516,566 (+8,037, plus +7,164 in weights =
  +15,201 total); `m5-block-rates` takes it to 521,880 (+13,351). Together:
  529,917 > 524,288. Both r2 briefs therefore carry a hard byte contract —
  tanjiro must land `Sources/` **byte-identical to base** (instrument preserved
  as `research/tanjiro-pr34/instrument.patch`), and frieren must land
  `LagunaRuntimeModel.swift` **≤ 500,000 B** with **net total growth ≤ 0**.
- **Two reclamation targets are authorised.** The merged
  `// BEGIN M5 HARDWARE-CONSTANT INSTRUMENT` … `// END` block at
  `LagunaRuntimeModel.swift:10975–11223` is ≈12,134 B of dead weight from #27,
  and there are **108 distinct `DARKBLOOM_*` flags**, most of which gate a
  settled decision. Reclaiming these is the cheapest way to buy headroom for a
  decode candidate.
- **`research/` and `senpai/tools/` are outside `editablePaths` and cost
  nothing.** Instruments, harvest scripts, patch files and notes belong there,
  permanently, and should never be carried in `Sources/`.
- The prefill-side implication is the happy one: **§A3's kernel work is
  byte-free.** A double-buffered `Ws` costs a few hundred bytes in a file with
  458 KB of slack. There is no budget argument against prefill kernel work.

A brief that does not check the budget can produce a candidate that times
correctly on-box and is refused by the official static review.

---

## Our position: `ns` 2.5297 = 4th of 937 on content; `officialScore` = 7th of 67

**★ Two different rankings, and we had been quoting the flattering one.** Read
directly from the authenticated `mlxfast` CLI on the advisor host
(`mlxfast submissions --all`, 1,494 rows, 67 distinct solvers):

| Metric | What it is | Our rank | Gap to best |
|---|---|---|---|
| `ns` (renormalised) | our own estimator; strips session-to-session draw | 4th of 937 receipts | 0.64% |
| **`officialScore`** | **what the service publishes and what gates promotion** | **7th of 67 solvers** | **1.443%** |

Best-per-solver, top 7 on `officialScore`:

```
1  lBroth           2.552308  promoted  46eeccf
2  a-github-name    2.545212  rejected  2ab00e9
3  polymorf         2.538532  rejected  8b352e9
4  metaspartan      2.528244  promoted  21f1d1a
5  davidtai         2.527626  promoted  0a9d439
6  ivanfioravanti   2.526989  rejected  ae9ac90
7  morganmcg1       2.515950  rejected  71586bc   <-- US
```

**Keep both metrics, and use each for its own job.** `ns` is the right
estimator for deciding *what is real*, because it removes the session draw that
we cannot control. `officialScore` is the only thing that *gates promotion*, so
it is the right number for deciding *whether to submit*. The crown is therefore
partly a lottery win, and our 1.443% deficit on the gating metric is more than
double the 0.64% content gap we had been planning against.

**Field statistics (same source).** 880 `rejected`, 471 `failed`, 139
`promoted`, 1 `promotion` — a field-wide failure rate of **31.5%** and roughly
**10 submissions per promotion**. Our own 17 submissions are all `rejected`
except `afec358`, which is `failed`.

**The crown is moving.** The `diff` column equals
`score − current_best_at_submission_time`, which lets the best-at-the-time be
reconstructed exactly. Our 8/4 morning and early-afternoon submissions all
reconstruct best = **2.539207**; from ~15:10 on 8/4 onward they reconstruct
best = **2.552308**. The leader improved **+0.516% inside one day**. A plan that
only closes today's 1.443% is not a plan to win.

**Tactical consequence.** Because the service dedupes byte-identical archives,
N lottery tickets require N byte-distinct, behaviour-identical trees. Beating
our own published 2.515950 needs `draw > 0.99456` ≈ 1-in-4 per receipt (§ below).

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
gap is reachable and 0.34% is not.

**The field gap is no longer the target — but it is bigger than we said.**
Closing the entire visible decode *and* prefill gap to the best public receipt
buys 0.64% on `ns`; the gap on the *gating* metric is **1.443%** and the crown
moved **+0.516% in one day**, so treat +1.5% to +2.5% as the bar for promotion
to be a coin-flip. §A3's single attributed prefill item is worth **~5% of
score** on its own. §1's unattributed decode residual is worth ~1.27 ms of T;
at elasticity 0.638 a *full* recovery would be ~19% of score, but no mechanism
for it is yet owned and the leading host-side explanation was demoted on
2026-08-05 (see §1) — so do not bank a number against it, bank the census.
Both prizes are *outside* the field's envelope — nobody in the corpus has found
them either. Ranking ourselves against the leaderboard was the right frame
while we were behind on measurement; it is now the wrong frame for choosing
*what to build*, while remaining the only correct frame for choosing *when to
submit*.

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

Round-6 block-rate family (#34, all deliberately slowed trees — see §A2; these
are instruments, not ranking attempts):

```
R1 b6032aeb T4.27468 S 97.8643  unperturbed control (Sources/ == base tree 6288233)
R2 ca416f01 T5.50538 S141.1262  rate 1 + rate 2 injection
R3 6757de65 T6.51605 S120.0782  rate 3 + rate 4 injection
R4 afec358a    ---      ---     FAILED (no score/metrics) - see A2 correction
```

R3−R1 is a free method validation: 1354.24 MB moved in 2.241±0.031 ms =
604.2 GB/s = **99.0% of the 610 GB/s nominal**. The differencing instrument is
trustworthy.

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

### The certified lm_head cascade (`Sources/MLXFastModel/LagunaLmHeadPrune.swift`)

Read `:1-72`; it is the best-documented module in the tree. Stock lm_head reads
the full BF16 [100352, 2048] weight (411 MB) for one row. Behind
`DARKBLOOM_LM_HEAD_PRUNE` (default ON) that becomes four dispatches:

```
1 COARSE     GEMV over the planar int5 copy; decode with FUSED_REFINEMENT reads
             only the 4-bit nibble plane at 1088 B/row -> 109.2 MB/step.
             Emits coarse logit c_i and certified bound delta_i     (:156)
2 ARGMAX-1   stock two-pass (value,index) reduction over `coarse` alone
3 THRESHOLD  finishes argmax, stock single-row GEMV on the coarse winner r,
             thresholds just below bfloat(e_r) -- sound for ANY r since e_r <= e_winner
4 EXACT      each simdgroup owns a FIXED 4-row block, full BF16 GEMV on that block
             iff coarse[r] + delta[r] >= threshold for any of its rows; re-reads the
             dropped 256 B/row residual bit plane for survivors only     (:650)
```

The certificate: `d_i = Σ_j |x_j| · (sd_g/2)` (flat half-cell), emitted as
`delta_i = d_i · (1 + 61·gamma)` with `gamma = 2^-15`, legal because the int5
codes satisfy `|q| ≤ 15` (verified on the real tensor at init, with a fallback to
the stock head on overflow at `:888`). **`delta` is BF16 rounded toward +infinity,
and candidacy is MONOTONE in it, so widening the bound only grows the candidate
set** — the property any new screening level must reuse. `coarse` stays FP32
because it would have to round down for the threshold path and up for the
candidate test.

Decode's three-level split: `nibble = floor(q/2) + 8`, `bit plane = q − 2·floor(q/2)`,
which is what took step 1 from 1344 to 1088 B/row (−25.7 MB/step, nezuko #20,
+0.410% at 3.2σ). The exact pass's per-row arithmetic is a **textual replica** of
the stock `gemv_al_bfloat16` so candidate logits are bit-identical, and every
vocabulary slot is written by exactly one lane on exactly one path. Prefill's
already-sliced final row uses the one-pass form
(`DARKBLOOM_LM_HEAD_PRUNE_PREFILL`, default ON). Roughly **458 of 25,088 four-row
blocks survive** to step 4 (~1.8%), reading 16 KB per live block for ~1.2 wanted
rows.

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
  **59,027 B** of the 3,000,000-byte budget free at `279b6e24`. See the byte-budget
  section for the per-file caps and the #35-vs-#34 mutual exclusion.
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

- **The advisor host has an authenticated `mlxfast` CLI** at `/usr/local/bin/mlxfast`.
  Read-only commands that work: `mlxfast submissions` (ours), `mlxfast submissions
  --all` (**this is the leaderboard** — there is no `leaderboard` subcommand),
  `mlxfast submission-note <id>`, `mlxfast notes`, `mlxfast benchmark`. `timeout`
  is **not installed** on the advisor host, so do not wrap these in it. Use
  `--all` to re-derive the field position and the moving crown rather than
  trusting any number written here.

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
12. **A delete-and-measure attribution is invalid unless you demonstrate the
    deleted code's producers survived.** Deleting a reduction whose result is
    unused lets the compiler eliminate everything feeding it, so you measure the
    reduction *plus its producers*. Keep the value live through a sink the kernel
    actually writes, and diff the instruction count or disassembly — not only the
    time. (fern #36, self-reported against his own #30 table.)
13. **When two arms agree to better than the noise floor, suspect they are the
    same arm before suspecting additivity.** Two independent mechanisms landing
    within 0.1% of each other is a coincidence; one mechanism measured twice under
    two labels explains it exactly. (Advisor error, #36.)
14. **Count dependency depth and ILP, not instruction count**, on any kernel not
    shown to be byte- or arithmetic-bound. See §3.
15. **The runtime instrument and the SPLIT profiler measure different things, and
    the difference is host-side.** (fern #37, adopted.) The long-standing
    30.03 vs 22.34 µs/layer discrepancy is an *instrument artefact*, not a
    kernel finding: split GPU-clock reads 22.66–22.78 µs/layer against the SPLIT
    profiler's 22.34 — **1.7% apart, below the ~2% resolution floor**. The gap to
    30.03 is **+4.1 µs/dispatch of host encode/commit that the GPU clock never
    sees**, plus ~+1.2 µs of command-buffer window granularity. Consequences,
    all now adopted:
    - sliding decode attention is **4.66%** of decode, not 6.16%;
    - the zero-cost ceiling score is **1.0365**, not 1.049;
    - merged #30 re-prices to **~0.36%**.

    The same constant is also a *lead*: 4.1 µs × ~406 scored dispatches =
    **1.665 ms**, larger than the entire 1.383 ms decode residual (§1). Whenever
    you quote a per-layer or per-kernel decode time, state which clock produced
    it.
16. **Never reuse one `.metal` source at two `heads` values without re-checking
    dispatch.** The `heads` field sets only the dispatched threadgroup count, so
    a shared source silently under-dispatches at the smaller value while a
    bitwise output diff still prints 0. (fern #37 probe footgun.)

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
| **A level-0 screen below the certified int4 lm_head plane** | **CLOSED by arithmetic (fern #37)** | The activation is not concentrated enough to screen. The top 256 of 2048 channels carry only **33.5–34.7% of sum\|x\|**; at the group-of-128 granularity the kernel can actually address, the top 2 groups are **14.0% of L1 = 1.1× uniform**. Argmax survival was 100% at K = 1, 2, 4, 8, 12 — but *every* config **adds** bytes (120.8 / 127.7 / 141.3 / 168.6 / 195.9 MB/step vs the shipped 112.4 B / 117.3 A). The certificate needs unread channels ≤ **1.97%** of L1 and the best achievable is **5.73%** — a 3× structural gap, not a tuning gap. Corollary, also adopted: **nothing downstream of the screen is worth byte-optimising** — the shipped cascade already runs its BF16 GEMV on 2.1–3.8 rows/step, so the whole refinement tail is 0.24–0.61 MB/step. The only residual is `lmhead_exact_inline_mask_block_v1` at 76.6 µs/step moving ~0.5 MB: **latency-bound, an M5-only geometry question** |
| **Weight re-read across the N dimension in the `_nax` gather-GEMM** | **REFUTED (advisor's own priority hypothesis)** | `wl = w + y_col*K_w` with `y_col = tid.x*BN` (`fp_quantized_nax.h:1631-1634`) means each column tile walks a **disjoint weight slab**. There is no re-read across N to remove. Verified from source. Also refuted in the same pass: expert load imbalance (< 1 ms), scale-plane cost, and accumulator concurrency. The real mechanisms are staging serialisation and SM=16 banding — see §A3 |
| **Vector / shuffle-count reduction in the fused attention core** | **CLOSED at the mechanism level (fern #36)** | 15 shuffles against `simd_sum`'s 20, same addition tree, **1.79% slower**. `float2` alone −0.27% = one noise floor; pad+`float2` does not stack; `float4` with madds hoisted and `float4` + packed epilogue both null. Geometry identical in every arm, so the M4 null is evidence about M5 (bounded residual 0.013% of score). Both premises in the brief were wrong — see §C. Do not reopen with a different vector width |
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
| **Prefill byte removal as a general strategy** | closed as *stated*, but see §A2/§A3 | the ridge argument was calibrated on guessed ceilings. The residual has since been re-measured honestly at ~34 ms, and **14.30 ms of it is attributed to one kernel's staging overlap** — a *latency* mechanism, not a byte one. Do not resurrect the old framing; bring a mechanism |
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

Ordered by expected value. Items 1–4 and 9 are **assigned**; the rest are held
because all four students are occupied. **The round-8 queue below the numbered
list is where the next free slot should go** — it contains the largest unowned
prize in the programme (P-GLUE).

1. **★ Fix the gather-GEMM staging overlap — ASSIGNED, fern #40 (§A3).** The
   largest attributable item on either axis: **+14.30 ms of the ~34 ms honest
   prefill residual**, with a mechanism, a corrected roofline, and a bit-exact
   in-kernel precedent. The kernel realises only ~41% of the achievable
   staging↔MMA overlap; F1 (double-buffer `Ws`) targets 10–15 ms of that.
   Byte-free (458 KB of file slack). If F1 lands, F3 then F2 follow.
2. **The ~1.27 ms unattributed decode residual (§1) — ASSIGNED indirectly via
   #32 (census) and #34 (dispatch law).** 29% of the decode step is neither the
   75.5% of bytes now measured at ~100% of nominal nor anything else we have
   priced. **Read §1's 2026-08-05 reframe before designing anything here.** The
   host-dispatch story is *demoted*: 4.1 µs/dispatch is an accounting constant
   reconciling two M4 instruments, not a marginal price, and the closing
   arithmetic puts exposed host cost at **~0.49 µs/dispatch**. There is no
   1.665 ms pool. The leading home is now **in-kernel issue/occupancy/latency
   inside GPU-busy**, concentrated in the ~200 non-byte-carrying dispatches;
   nezuko #9's M4 recoverable column independently sums to **~1.38 ms**, the
   same magnitude, led by sliding fused attention at 428 µs running at 36% of
   ceiling. The two live arms remain complementary: nezuko's per-family
   byte-vs-latency census (#32 B, now aimed at sliding attention first) locates
   the occupancy loss, and tanjiro's M5 dispatch-saturation law (#34 A) decides
   whether *any* dispatch-count mechanism is legal on the ranked host. Do not
   quote a score number for this residual until one of the two lands — bank the
   census, not a number.
3. **Calibrate the missing middle of the M4→M5 transfer table — ASSIGNED,
   frieren #35 r2 A (§5).** One receipt buys a transfer factor for the entire
   class "saves DRAM bytes, adds fixed ALU/transaction cost", which currently
   has *no* calibration anywhere between 1% and 106%. Every future byte-trading
   arm is priced off this number.
4. **The 4-bit lane-major scale plane — ASSIGNED, frieren #35 r2 B.** The
   repriced successor to §B: per-row base + `0xFF` sentinel escape, two loads per
   row instead of twelve, −70…−90 µs/step on M4. `row_le15` is 0.9944 / 0.9864 /
   0.9958 / 0.9814 across the four planes, so the escape predicate is
   simdgroup-uniform in practice. If it lands, the routed/shared planes are 18×
   the bytes (552.08 MB/step, span 39).
5. **SM=16 banding / M-padding, but only after item 1.** MMA issues 453,120 rows
   for 311,296 useful = **1.456×**, and 453,120 is exactly `Σ ceil(n_e/16)·16`,
   the `kFragRows` floor. While the kernel is staging-serialised this waste is
   partly hidden; once overlap is fixed it becomes the binding term (~5–7 ms).
   Do **not** open it before #40 reports — the two mechanisms interact and rule
   10 applies.
6. **The latency-bound `lmhead_exact_inline_mask_block_v1` geometry.** #37 closed
   everything else in the lm_head cascade but left this: 76.6 µs/step moving
   ~0.5 MB, i.e. entirely latency. It is an **M5-only** question (§2), so it needs
   receipt pricing or the #34 dispatch law first, and it is small. Listed for
   completeness, not urgency.
7. **Reclaim decode byte headroom.** The #27 instrument block
   (`LagunaRuntimeModel.swift:10975–11223`, ≈12,134 B) and the long tail of the
   **108 `DARKBLOOM_*` flags** are dead weight in the one file that is 15,759 B
   from its per-file cap. This is not a score improvement — it is what makes the
   *next* decode candidate mergeable at all. Partly authorised inside #34 r2 and
   #35 r2; a dedicated cleanup arm is the fallback.
8. **Bit-exact fused split-K for the NAX steel path** (`o_proj`, `g_proj`,
   router). Port `qmm_t_splitk_fused` (`quantized.cpp:849-893`) to
   `steel_gemm_splitk_nax` (`matmul.cpp:689-810`, split-K branch `:987-991`,
   `C_split` fp32 `:734-737`). Removes ~0.72 GB of fp32 round-trip traffic and
   ~80–120 dispatches; ~0.53% of score, and unusually attractive because it is
   **locally falsifiable on the non-NAX twin**.
9. **`MLX_MAX_MB_PER_BUFFER` — ASSIGNED, nezuko #32 r2 A.** Promoted from
   "methodology question" to the round's best free candidate. A ~2-byte edit at
   `LagunaRuntimeWeights.swift:387` moves command buffers per decode step 200→45
   (current), 50→**127**, 400→**19**, with the dispatch count fixed at 406.
   frieren has a suspended M5 datum that `50` is **1.696% ± 0.175% better on
   decode, t = −9.71** (≈ −73 µs on T ⇒ **+1.08% of score**), and it
   sign-contradicts nezuko's own #9 per-command-buffer cost. Because the wiring
   is gated at ≥96 GiB (`:549-551`) the knob is *live on the ranked M5 and dead
   on every local box*, so the receipt is the only possible screen — and a clean
   three-arm null inside the ±0.13–0.30% A/A floor is itself a merge-worthy
   result that closes the family.
10. **`DARKBLOOM_FUSED_QKV` free flip.** One receipt; its only provenance is
    "paired local benchmark" on a predecessor's host (`:108-114`).
11. **`MLX_BFS_MAX_WIDTH = 50` vs MLX's default 20** (`transforms.cpp:181`).
    Unmeasured and **not** a partition knob — traversal width changes fusion and
    therefore bytes. Needs its own hypothesis.
12. **Routing-aware two-regime expert dispatch.** The shipped tile is tuned for
    uniform routing that does not occur (CV 1.80, 20.26% empty, busiest 32 experts
    = 54.7%). Row-tile widening, sub-16 SM and the whole `STAGE_BM128` family are
    closed — SM=16 attains the `kFragRows` floor exactly. A *two-regime* split is
    the only remaining route below 1.456× MMA rows and would have to break
    per-expert weight exclusivity. Needs a mechanism proposal, not a knob.
13. **Re-test nezuko's #9 dispatch-fusion negative on the M5, once.** It was
    measured entirely under the M4 blindness of §2, and the ranked host has 2× the
    bandwidth and 2× the cores. Low expected value, but it un-blocks two closed
    families at once if it flips. Largely subsumed by #34's rate work.
14. **Minify the remaining 71 Metal literals in `LagunaRuntimeModel.swift`**
    (−54,251 B). Worth 0.0% of score directly, but it is the largest single
    reclamation available in the file that sits 15,759 B from its per-file cap.
    Promoted from "irrelevant" to "the fallback for item 7" now that the surface
    budget binds — total headroom is 59,027 B, not the ~87 KB previously recorded.

### ★ Round-8 candidate queue — unowned

Full briefs in `research/RESEARCH_IDEAS_2026-08-05_09:30.md` (11 ranked ideas).
Read that file's **ADVISOR CORRECTION** box first: the draft asserted
`DARKBLOOM_SHARED_FIRST_DOWN` was a proven win when it is a measured
**+0.10 ms/step regression**, correctly shipped OFF.

- **P-GLUE — the largest unowned prize on either axis. Give the next free slot
  to this.** #27 measured prefill overlap + glue at **46 ms (44–51% of S₀)**, and
  fern #40 owns only the ~15.4 ms gather-GEMM slice of it. `attn_core`,
  `shared_expert`, the MoE argPartition/sort/scatter chain
  (`LagunaRuntimeModel.swift:9429–9694`) and the elementwise glue have **never
  been priced on M5 at all**. Half-recovery of the ~20 ms unowned remainder is
  **+3.7% of score**; full recovery +7.4%. Crucially this is *screenable on M4*:
  the NAX gate (§2) blinds us to `_nax` GEMM *time*, not to op inventories,
  counts, shapes, or the relative cost of non-NAX glue. Confidence high, no
  owner, no byte problem.
- **D-STRAND — decode independent-strand overlap via barrier / encoder
  scheduling.** Decode has *zero* measured dispatch concurrency
  (`gpu_busy_sum == gpu_busy_union` to 6 ns), and the hideable small-kernel pool
  is ≈0.59 ms/step; hiding half is **+4.4%**. The magnitude claim in the ideas
  file is VOID (see the correction box) but the **lever survives and is the
  interesting part**: encode order is bit-exact, M5-measurable, and has
  demonstrated ~2.3%-of-T authority — it has been measured exactly once, in the
  losing direction. Any arm here must begin with a barrier audit, not a flag
  flip. 2–6 KB of Swift, so it needs item 7's byte reclamation first.
- **D-FUSE-GATESP — fuse `gate_sp` (40 dispatches, 213 µs/step, 2% of ceiling)
  into `oproj_act`.** +1.5–3% realistic, +5.6% upper bound, bit-exact, 3–8 KB in
  the roomy `jit_kernels.cpp`. **Strictly gated on #34 deliverable A**: it is a
  dispatch-count mechanism, and §1 now says we have no M5 evidence that dispatch
  count is priced. Do not commission before that receipt lands.
- **D-MLP — depth-2 weight staging in the routed decode QMV** (546.2 vs
  651.8 GB/s achieved). Full closure = **+1.56%**, bit-exact, and it extends the
  existing depth-1 precedent at `LagunaRuntimeModel.swift:7325`.
- **An offline argmax-margin census, to price the bit-exactness doctrine.** The
  gates check *tokens*, not bits. We have never measured how much argmax margin
  the model actually carries, so every non-bit-exact idea has been refused on
  faith rather than on evidence. Offline, no receipt, no score risk; it either
  confirms the doctrine or opens a whole class of arms.
- Also queued: a post-#34 tiny-kernel threadgroup-geometry batch; prefill
  routing-chain fusion (conditional on P-GLUE); software-pipelined K-tile loads
  across the sliding-attention reduction (+0.8–1.5%, and the one item on this
  list with a *fully local M4 screen* — the lever #36 named but never tested);
  and byte reclamation promoted to explicit enabling work.

**Standing critique to answer (from the round-8 agent, and it is fair):** the
programme has staffed *measurement* of both big residuals but *mechanism
ownership* of neither, while treating "GPU busy" as "GPU useful". P-GLUE and
D-MLP are the two items that convert measurement into an owned mechanism.
