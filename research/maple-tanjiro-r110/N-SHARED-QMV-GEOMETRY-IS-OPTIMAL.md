# `N-SHARED-QMV-GEOMETRY-IS-OPTIMAL` — and `L-STANDALONE-METAL-RIG-DOES-NOT-CALIBRATE`

**Author:** maple-tanjiro · **Round 110** · branch `maple-tanjiro/r110-prefill-nax-arm-factory`
**Status:** self-directed side lead, opened and **closed** in the same session. Not an
assignment; no submission; nothing here is a candidate for shipping.
**Evidence:** `research/maple-tanjiro-r110/qmv-geometry-evidence/`

> **The one-line takeaway for whoever reads this next:** the shared-QMV kernel's launch
> geometry is already the best of eight bit-identical alternatives and its source, run
> alone, already lands on the sibling efficient frontier it was supposed to be 30 % short
> of — **and** the standalone Metal rig I built to test all this fails its own calibration
> standard by 3–30×, so *no* standalone-rig result about this kernel family should be
> believed on its own. Measure in situ.

---

## 1. The lead as it stood

Target kernel: `laguna_shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1` (the shared-expert
NVFP4 SwiGLU QMV, 39 dispatches/decode step).

Measured **in situ** (prior session, decode profile):

| quantity | value |
|---|---|
| wall | 288.7 µs/step |
| traffic | 46.0 MB/step |
| per call | 7.4 µs (39 calls/step) |
| achieved BW | **159 GB/s** = 58 % of M4 Pro peak (273 GB/s) |
| sibling QMV kernels | 88–90 % of peak |

Fitting the siblings to `t_call = c + bytes/BW` gives `c = 1.01 µs`, `BW = 251.7 GB/s`.
The shared kernel sits **1.70 µs/call** above that line:

```
1.70 µs/call × 39 calls = 66.4 µs/step (M4)
                        = 29.0 µs/step (M5 equivalent, 30 M5-µs = 68.7 M4-µs)
                        = 0.242 % of score at τ = 1
```

The shipping bar (Rule 105.12) is +30 µs/step M5 = **0.251 % of score**. So even the
*entire* sibling-fit residual, captured perfectly and at full τ, is **just under one bar**.
That framing matters: this was never a fat lead. (The 0.391 % headline number that floated
around earlier is the naive whole-gap-to-peak figure and **must not be quoted** — it double
counts the fixed launch cost `c`.)

Hypothesis under test: the 1.70 µs/call excess is a **launch-geometry** effect —
rows-per-simdgroup, threadgroup shape, or K-split — that a bit-identical re-decomposition
could recover.

## 2. The instrument

I could not test eight kernel geometries in situ cheaply (each needs a rebuild + a paired
ABBA session), so I built a standalone Metal microbenchmark:
`qmv-geometry-evidence/qmv-geometry-bench.swift` (459 lines, no dependencies).

```
swiftc -O qmv-geometry-bench.swift -o bench
./bench <path-to-header.metal> [iters] [poolMB]
# header used: research/maple-tanjiro-r110/nibble-evidence/header_split1.metal
#   sha256 7f0387756fcf7877e04f7578d06a33886858b4cc937e324cf5132b4a9bb7d138
```

Design decisions that were **necessary** to get any signal at all — each of these was
learned the hard way and is worth reusing:

1. **39 dispatches per command buffer**, matching the in-situ per-step dispatch count, so
   the launch overhead is amortised the same way.
2. **GPU timestamps** (`cb.gpuEndTime - cb.gpuStartTime`), not CPU wall.
3. **Configurable weight pool.** Default 43 MB (≈ the real per-step working set, partly
   cache-resident); 1024 MB forces cold DRAM on every read.
4. **A 4 s global DVFS warmup before any arm is timed.** *Apple GPU DVFS needs ~120–140 ms
   of sustained work before clocks settle.* Without a global warmup, whichever variant is
   scheduled first is penalised by **~3×**. This single bug invalidates any naive
   "run A, run B, compare" Metal rig on this machine.
5. **Round-robin interleaved sampling** across arms, so DVFS/thermal drift is shared
   equally rather than aliasing onto arm order.
6. **A coverage/correctness self-check that gates the whole run:** every arm must write all
   512 output rows and match the shipped arm **bit-exactly**. This caught a real bug — an
   early `v6` grid mistake covered only half the rows and would otherwise have "won".

Arms:

| arm | decomposition |
|---|---|
| `v0_shipped` | shipped: R=1 row/simdgroup, 2 simdgroups/TG, 256 TG × 64 threads |
| `v1_r1_tg256` | same work, 64 TG × 256 threads |
| `v2_r1_tg1024` | same work, 16 TG × 1024 threads |
| `v3_r2_tg64` | 2 rows/simdgroup |
| `v4_r4_tg64` | 4 rows/simdgroup (amortises input re-reads 4×) |
| `v5_ks2_tg128` | K-split 2 |
| `v6_ks4_tg256` | K-split 4 |
| `v7_ks8_tg256` | K-split 8 |
| `c0_wide_known_bad` | **calibration standard** — the `DARKBLOOM_QMV_WIDE_CODES` body verbatim (`uint4` code loads, `laguna_nvfp4_qdot_codes_16`) |
| `s0`–`s3` | pure coalesced streaming reads at the same byte volume — the hardware floor |

`c0` is a **calibration standard, never a candidate**: `DARKBLOOM_QMV_WIDE_CODES` is closed
on evidence (rule 102.2) at **−0.5363 % of score, a +12.2 % regression on its own target
kernel, occupancy-binding** (`CURRENT_RESEARCH_STATE.md:4303`). Its in-situ sign and
magnitude are known, so it is the ideal free negative control for a new rig: a rig that
cannot see +12.2 % cannot be trusted to see anything smaller.

> Note: inside this harness `c0` happens to produce **bit-identical** output to `v0`
> (`maxrel = 0.00e+00`). That is a property of my synthetic inputs and reduction order; it
> is *not* a claim that the shipped `WIDE_CODES` gate is bit-exact. It is not, and it stays
> closed.

## 3. Results

All three runs pass the coverage check (all arms 512 rows written, `zeros=83`,
`maxrel = 0.00e+00` against the shipped arm), so **every geometry below computes exactly
the same thing**.

### 3a. 43 MB pool, 400 iterations (the best-powered run)

`qmv-geometry-evidence/run_pool43_n400.txt`

| arm | µs/call | µs/step | GB/s | µs/call min | spread % |
|---|---|---|---|---|---|
| **`v0_shipped`** | **5.637** | **219.83** | **197.7** | **5.587** | 8.0 |
| `v1_r1_tg256` | 6.170 | 240.62 | 180.6 | 5.904 | 6.1 |
| `v2_r1_tg1024` | 5.766 | 224.87 | 193.2 | 5.591 | 9.6 |
| `v3_r2_tg64` | 5.752 | 224.33 | 193.7 | 5.692 | 10.4 |
| `v4_r4_tg64` | 6.644 | 259.13 | 167.7 | 6.173 | 9.8 |
| `v5_ks2_tg128` | 5.843 | 227.88 | 190.7 | 5.660 | 9.7 |
| `v6_ks4_tg256` | 7.294 | 284.46 | 152.7 | 7.091 | 7.5 |
| `v7_ks8_tg256` | 14.939 | 582.62 | 74.6 | 13.601 | 13.4 |
| `c0_wide_known_bad` | 5.672 | 221.21 | 196.4 | 5.628 | 9.1 |
| `s0_stream_16k_8B` | 4.975 | 194.04 | 223.9 | 4.955 | 5.8 |
| `s1_stream_16k_16B` | 4.929 | 192.25 | 226.0 | 4.906 | 6.3 |
| `s2_stream_64k_16B` | **4.907** | 191.38 | **227.0** | 4.885 | 9.1 |
| `s3_stream_8k_16B` | 4.960 | 193.46 | 224.6 | 4.936 | 6.3 |

The 60-iteration replicate (`run_pool43_n60.txt`) reproduces this ordering exactly.

### 3b. 1024 MB cold-DRAM pool, 60 iterations

`qmv-geometry-evidence/run_pool1024_n60.txt` — `v0` goes 5.637 → 5.692 µs/call
(**+1.0 %**), the ordering is unchanged, the streaming floor moves 4.91 → 5.04 µs.

## 4. Findings

**F1 (measured). The shipped decomposition wins.** `v0_shipped` is the fastest of the
eight bit-identical arms in every run. Every threadgroup reshape, every rows-per-simdgroup
increase, and every K-split is equal or slower. The closest challengers (`v3`, `v2`) are
+2.0 % and +2.3 %; the best K-split (`v5`) is +3.7 %. There is no geometry win here.

**F2 (measured). The real ceiling is 224–227 GB/s, not 251.7 GB/s.** Four pure coalesced
streaming kernels reading the same byte volume with no arithmetic at all top out at
4.91–4.98 µs. The shipped QMV is **+14.9 %** over that floor. So the sibling-fit slope of
251.7 GB/s — the number that generated the whole 1.70 µs/call "excess" — is **not
achievable for a dispatch of this size**; a large part of the modelled gap is the small-
dispatch bandwidth ceiling, which no source change can recover.

**F3 (measured). Input re-reads are not the limiter.** `v4_r4_tg64` amortises the input
vector re-read 4× and is **18 % slower**, not faster. Fewer, fatter threads lose more to
reduced memory-level parallelism than they gain by re-reading less.

**F4 (measured). Cache residency does not explain the in-situ number.** A 24× larger,
guaranteed-cold weight pool moves the shipped arm by **+1.0 %**. The in-situ kernel runs at
7.4 µs/call while this rig runs the identical source at 5.6–5.7 µs/call; cold-DRAM
pressure accounts for essentially none of that ~1.7 µs difference.

**F5 (measured, and decisive). The rig fails its own calibration.** The `c0` arm, known
in situ at **+12.2 %** kernel time, measures:

| run | `c0` vs `v0`, mean | `c0` vs `v0`, min | fraction of the known +12.2 % |
|---|---|---|---|
| 43 MB, n = 400 | **+0.62 %** | +0.73 % | **5–6 %** |
| 43 MB, n = 60 | +0.37 % | +0.66 % | 3–5 % |
| 1024 MB, n = 60 | +4.01 % | +1.78 % | 15–33 % |

Even the single most generous reading (+4.0 %, from the noisiest run) is **3× below** the
known in-situ regression; the best-powered reading is **20× below**. The rig is therefore
compressing real effects on this kernel family by at least 3× and probably ~20×.

**F5b (measured, and the sharpest number in this report). Run alone, the shipped kernel
sits *on* the sibling efficient frontier.** The whole lead was built on a sibling fit
`t_call = 1.01 µs + bytes/251.7 GB/s`. Evaluate that fit at the shared kernel's own byte
count and compare:

| | µs/call | vs sibling frontier |
|---|---|---|
| sibling-frontier prediction @ 1.179 MB/call | 5.696 | — |
| **this rig, identical source, 1 GB cold pool** | **5.692** | **−0.04 %** |
| this rig, 43 MB pool, n = 400 | 5.637 | −1.00 % |
| **in situ** | **7.400** | **+29.96 %** |

Byte-count caveat: the in-situ accounting is 1.179 MB/call (46.0 MB / 39) while the rig
touches 1.114 MB of weights+scales; using the rig's own byte count instead moves the
frontier to 5.436 µs and the rig lands at +3.7 % rather than −0.0 %. Either way the
conclusion is the same and it is not subtle: **the shipped source, executed alone, is
within 0–4 % of the frontier the lead said it was 30 % away from.**

**Read F5b against F6, not on its own.** F5 says the rig compresses *deltas*; F6 guesses
the reason is that the rig runs at a more favourable operating point. If F6 is right, then
part of F5b's agreement with the frontier is the rig flattering itself, and the honest
claim shrinks to: *there is no source-level property of this kernel that stops it reaching
the sibling frontier under favourable conditions.* That is still enough, because it removes
every source-level explanation for the 1.70 µs/call — the geometry (F1), the input re-reads
(F3), and cache residency (F4) are each independently excluded, and F5b closes the
remaining "maybe the code is just bad" hypothesis. What is left is the operating point
inside the decode loop, which is not something an edit to this kernel can reach.

**F6 (inferred, not measured).** The likely mechanism: the rig's post-warmup clocks run
hotter and its memory system runs cleaner than the in-situ decode loop (197 GB/s vs
159 GB/s for identical source). That makes the rig *more* memory-bound and *less*
occupancy-/issue-bound than reality — and `WIDE_CODES` is documented as
**occupancy-binding**, precisely the axis the rig suppresses. I did not test this; it is a
hypothesis, and it predicts the rig will systematically under-report any
occupancy/register-pressure effect while roughly preserving pure-bandwidth effects.

## 5. Verdict

**`N-SHARED-QMV-GEOMETRY-IS-OPTIMAL`.** The shared-QMV launch geometry lead is **closed as
unfundable**. Four independent reasons, any one of which is sufficient:

1. The whole modelled residual is 0.242 % of score — **below the 0.251 % bar** — before any
   τ discount, so a perfect fix is a non-ship.
2. Of that residual, F2 shows a large fraction is the small-dispatch bandwidth ceiling,
   which is not addressable in source.
3. Of what remains, F1 shows the shipped geometry already beats all eight alternatives.
4. F5b shows the shipped source, run alone, **already lands on the sibling frontier** — the
   deficit does not live in the kernel text at all, so there is nothing in this file to fix.

**`L-STANDALONE-METAL-RIG-DOES-NOT-CALIBRATE` (the more valuable result).** A standalone
Metal microbenchmark of the NVFP4 QMV family reproduces only **3–30 % of a known in-situ
kernel delta**, even when it is byte-identical in source, dispatch count, traffic, and
output. Consequences for the campaign:

- A **negative** from such a rig (like F1) is weak-but-directional evidence: the rig would
  have had to compress a *huge* real win to hide it, and the arms it ranked worst lose by
  far more than its compression factor.
- A **positive** from such a rig is **worthless** — a rig that shrinks a +12.2 % effect to
  +0.6 % has no calibrated map from its own µs to in-situ µs, in either direction.
- Therefore: **do not build a standalone rig to rank kernel variants for shipping.** The
  only admissible instrument for this family remains an in-situ paired ABBA session
  (SPLIT=0 for ranking, SPLIT=1 for attribution, ≥ 6 reps/arm).
- If anyone does build one anyway, **carry a closed, sign-known gate as a calibration arm**
  and publish the calibration ratio next to every result. That cost me ~40 lines and turned
  a plausible-looking sweep into an honest null.

## 6. What would reopen this

Nothing about this kernel's **text**. F1 and F5b between them exhaust the source-level
hypotheses, so "rewrite the shared QMV" is closed regardless of what the rig's calibration
factor turns out to be.

The one live question this work *creates* rather than closes: identical source runs at
7.4 µs/call in situ and 5.6–5.7 µs/call alone. That ~1.7 µs/call is worth ~66 µs/step M4,
and F4 rules out cache residency, so it is an **operating-point** effect — co-residency,
cadence, or clock state inside the decode loop. Two cautions before anyone chases it:

- It is a **whole-decode-loop** question, not a shared-QMV question. If the decode loop
  really does run its kernels at a worse operating point than they can achieve alone, that
  is a campaign-level finding worth far more than 66 µs/step — and it should be opened as
  one, on an instrument that can see it, not as a patch to this kernel.
- By the τ table, cadence/dispatch-class effects price at τ ≈ 0.01, which would turn
  0.242 % into 0.002 %. I am **not** claiming a τ value here: I did not measure one, and
  nobody should quote one from this document in either direction.

## 7. Reproduction

```bash
mkdir -p /tmp/qmvbench && cd /tmp/qmvbench
cp <repo>/research/maple-tanjiro-r110/qmv-geometry-evidence/qmv-geometry-bench.swift bench.swift
swiftc -O bench.swift -o bench
./bench <repo>/research/maple-tanjiro-r110/nibble-evidence/header_split1.metal 400 43
./bench <repo>/research/maple-tanjiro-r110/nibble-evidence/header_split1.metal 60 1024
```

Runs in ~6 s each, holds no model, touches no gate, and is safe to run alongside nothing
else. It writes the generated Metal to `/tmp/qmvbench/generated.metal` for inspection.

Known gotchas if you edit it: `String(format:"%s")` with Swift `String`s segfaults; and
`metal::abs(bfloat)` is ambiguous under `languageVersion = .version3_1`, so the epilogue
must go through `float`.
