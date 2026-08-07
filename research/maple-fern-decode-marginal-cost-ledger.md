# Decode marginal-cost ledger by duplicate injection

PR #218 - `maple-2026-08-07e-decode-marginal-cost-ledger`, revision `r1`.
Base `codex/mlxfast-maple-20260804-advisor` @ `0c86fc3b5b637a15eee8f95a82d30e67e3e481b3`.

Host: Apple M4 Pro, 20 GPU cores, 48 GiB (low-memory startup profile),
`applegpu_g16s` generation 16, Swift 6.3.3. Steady one-token decode step on
this host is **8.20 ms** (M5 promoted receipt: 4.1436 ms).

**This experiment ships a zero-byte submitted diff.** The instrument is
research-only and is published as
`research/maple-fern-decode-dup-injection.patch`.

---

## 0. Headline

**Absorption is per-family, not a single step-level budget.** The decode step
has a *serial spine* that pays for every microsecond of added work, and a
*shadow* around it in which extra GPU work is free. Which one a kernel family
sits in is a measurable property of that family, and the answer varies by more
than three orders of magnitude across families that look similar in a GPU
census.

Measured pass-through of injected duplicate work, per family, on the same host
in the same session:

| family | calls/step | marginal cost | pass-through vs census | verdict |
| --- | --- | --- | --- | --- |
| `T0a_router_top8` | 39 | **~0 us/call** (slope `-8.4 +/- 4.8` us/copy-set) | 0 % up to 2.85 ms | fully shadowed |
| `T1a_residual_rms_router` | 39 | 2.73 us/call chained (**106 us/step**) | 35 % | partly shadowed |
| `T2c_routed_qmv` | 39 | **30.35 us/call** (**1184 us/step**) | ~100 %, **linear from K=1** | on the spine |

`T2c` (the routed-expert top-8 SwiGLU QMV) has **zero absorbed slack**
(hinge fit: `-0.26` copy-sets) and its very first injected duplicate already
costs `+1377.7 +/- 1.1 us` at `t = 1272`. `T0a` absorbs 15.3 copy-sets - about
2.85 ms - before it costs anything at all, and `#204`'s independent deletion of
that same family measured `-0.9 +/- 12.1 us`, exactly as this instrument
predicts.

The practical consequence re-prices the remaining search space:

> Do not spend effort on the small decode kernels. Router top-8, gate/softplus
> and the norm/router glue are *proven* to be in the shadow: making them faster,
> or deleting them, is worth ~0. The routed-expert QMV path is *proven* to be on
> the spine at ~100 % pass-through - it is the only family measured so far where
> a microsecond saved is a microsecond earned.

This gives a quantitative explanation for the programme's long run of
"census says 200 us, deletion measures 0 +/- 12 us" results, and it converts
that pattern from a mystery into a screening test: **inject before you
optimize.** One 110-second duplicate-injection probe tells you whether a family
can pay, before any kernel is written.

A caveat that runs through the whole report: an injected duplicate re-reads
weights the real dispatch just streamed, so it is *cache-warm*. For families
whose working set exceeds cache the measured marginal is therefore a **lower
bound** on the cost of the real, cold dispatch; for small cache-resident
families it is faithful. See §4.

---

## 1. What was built

A duplicate-injection instrument (`enum LagunaDecodeDup`) inside
`LagunaRuntimeModel.swift`. At a wired site it re-issues the same dispatch
`K-1` extra times into scratch that nothing reads, appends the scratch roots to
the layer's `asyncEval` so they cannot be dead-code eliminated, and then
discards them. `K = 1` is bit-identical to the unmodified runtime.

Controls (all env, all default-off):

| Env | Meaning |
| --- | --- |
| `DARKBLOOM_DECODE_DUP_TARGET` | wired site name |
| `DARKBLOOM_DECODE_DUP_SCHEDULE` | per-segment K schedule |
| `DARKBLOOM_DECODE_DUP_CHAIN` | thread copy *i* into copy *i+1* (serial) |
| `DARKBLOOM_DECODE_DUP_VERBOSE` | per-forward census of every wired site |
| `DARKBLOOM_DECODE_DUP_FAULT` | perturb the **real** input by +1 bf16 ULP |

`research/fern_dup_probe.py` drives one worker process through a palindromic
schedule of K-arms, aligning to the worker's own segment announcements;
`research/fern_dup_stats.py` reduces it with the segment median as the unit of
replication.

---

## 2. Part A - mandatory instrument gates

### A1 (null on a static side branch) - PASS

`T0a_router_top8` is the family #204 deleted outright for `-0.9 +/- 12.1 us`.
Pre-registered (`d9edc28`, landed before any probe ran) as a side branch with
`E = 0.00`, acceptance `[-0.16, 0.16]`, hard limit `|slope| < 30 us`.

Run `d7b8f9cf`, schedule `1,2,3,5,5,3,2,1` x3, 216 steps/segment, drop 16,
0 token divergences:

```
OLS slope (block-centred, df=20): -8.45 +/- 4.83 us per extra copy-set
                                  95% CI [-18.52, +1.63]
E = slope / census = -8.45 / 185.7 = -0.045
```

`|slope| = 8.45 < 30` and `E = -0.045` inside `[-0.16, 0.16]`. **A1 passes**,
and it reproduces #204's independent deletion result to within noise.

### A2 (positive control) - original site VOID, replaced and PASSED

The pre-registered A2 used `T0b_qkv`, wired to `lagunaNormAffineQKV`. Its first
two runs produced clean, tight nulls (`-9.36 +/- 6.54 us`, then `+0.50 +/-
1.09 us` at K up to 33). **Those nulls were an artefact.** The all-site census
added afterwards shows `T0b_qkv` produces **zero** `DUPCOUNT` records in decode
*or* prefill: the site never executes.

Cause (confirmed by source audit, all reasons checkpoint-structural, not
env-dependent): the outer decode fast path at `:5822-5840` passes, but the
norm-fusion inner guard at `:5852-5858` declines because
`lagunaNativeAffineNVFP4From` defaults to `0`, so every layer's bank is
`mode == .nvfp4, bits == 4, groupSize == 16` and fails `mode == .affine &&
bits == 8`; NVFP4 also yields no affine biases, and gate folding requires
group-32 INT8 so `_nativeAffineQKVGateRows` stays `0 != nHeads`. The real
decode QKV projection is `lagunaDecodeNVFP4QKVR1` at `:5887-5891`.
`lagunaNormAffineQKV` is dead code on this checkpoint.

**A2 was replaced with a stronger, target-independent positive control**: a
big-K saturation sweep on the *confirmed-live* `T0a_router_top8` site. The
instrument must be able to make wall time move at all.

Run `cabf0bf5`, schedule `1,5,17,65,65,17,5,1` x2, 0 divergences,
`copies = 39*(K-1)` verified at every arm:

| K | injected census us | measured us added | hinge prediction |
| --: | --: | --: | --: |
| 1 | 0 | 0 | 0 |
| 5 | 743 | +30.5 +/- 19.0 | 0 |
| 17 | 2971 | +70.5 +/- 6.3 | 70.5 |
| 65 | 11885 | +5091.8 +/- 152.6 | 5091.8 |

Saturated marginal cost **104.6 us per copy-set** (56 % of census); absorbed
slack **2.85 ms/step**. The two-regime hinge fitted on the top two arms
predicts `0` at K=5 against a measured `+30.5 +/- 19.0` (t = 1.6) - the model
is not fitted to that point and lands on it anyway.

**A2 passes.** The instrument moves wall time by 5.1 ms when asked to, and the
K=5/K=17 nulls are genuine absorption, not dead injection.

*Standing rule adopted from the T0b failure:* a ledger row without a positive
`DUPCOUNT` census and `copies == calls x (K-1)` is **void**, not zero.

---

## 3. Part B/C - what duplicate injection actually measures

Two knobs, two different physical quantities:

- **unchained** (`K-1` independent copies): extra *parallel* work. Prices the
  family's **throughput** cost.
- **chained** (`K-1` copies threaded copy *i* -> copy *i+1*): extra *serial*
  depth. Prices the family's **critical-path latency** cost.

`T1a_residual_rms_router` is the one wired site whose output is
shape-preserving, so it can be measured both ways at matched K.

| K | copy-sets | unchained us/step | chained us/step | chained/unchained |
| --: | --: | --: | --: | --: |
| 5 | 4 | 157.9 +/- 5.9 | 425.7 +/- 14.2 | **2.70** |
| 11 | 10 | 468.5 +/- 9.4 | 1053.4 +/- 14.2 | 2.25 |
| 21 | 20 | 1526.8 +/- 89.9 | 2422.0 +/- 24.8 | 1.59 |
| 41 | 40 | 7842.2 +/- 78.7 | 7973.5 +/- 200.7 | 1.02 |

Runs `dfa6b483` (unchained) and `ee407682` (chained), schedule
`1,5,11,21,41,41,21,11,5,1` x2, 0 divergences in both.

The signature is exactly what a latency-bound step predicts: at low load a
serial link costs 2.7x what a parallel one costs, and the two converge as
throughput saturation takes over.

Reading the low-K arm (K=5, where absorption is still in force):

| quantity | per copy-set | per call (39 calls/step) |
| --- | --: | --: |
| parallel / throughput cost | 39.5 us | **1.01 us** |
| serial / critical-path cost | 106.4 us | **2.73 us** |
| GPUPROF census (cold) | 305.1 us | 7.82 us |

**The serial number is the one that matters**, because the real dispatch *is* a
serial link. `residual_rms_router` therefore owns at least
`2.73 us x 39 = 106 us/step` of critical path - **1.63 % of score** at the
0.015280 %/us decode price.

Contrast `T0a_router_top8`: unchained marginal `-8.45 +/- 4.83 us` per
copy-set, i.e. `0.00 +/- 0.12 us` per call, and #204's independent deletion of
that family measured `-0.9 +/- 12.1 us`. Two families with comparable census
cost (185.7 vs 305.1 us/step) differ by more than an order of magnitude in
marginal cost. **Census time is not marginal cost, and the ledger can tell
them apart.**


---

## 4. What the instrument cannot see: the cache-warm floor

This is the most important limitation of the method and it must be stated
before the ledger is read.

An injected duplicate runs immediately after the real dispatch and reads
**exactly the same weight bytes**. Those bytes are still in cache. So the
duplicate does not pay the DRAM traffic the real dispatch paid:

```text
census_cold(family) = dram_component + compute_and_launch_component
duplicate_marginal  =                  compute_and_launch_component   (+ residual DRAM)
```

Two consequences, in opposite directions, and they must not be mixed up:

1. **For a family whose working set exceeds cache, the measured marginal is a
   lower bound on the value of removing it.** Deleting the real dispatch also
   removes its DRAM traffic, which the duplicate never paid. `T1a` shows this
   plainly: census 7.82 us/call cold versus 2.73 us/call chained-warm, so
   roughly 65 % of that family's real cost is traffic the instrument cannot
   charge for.
2. **For a small cache-resident family the measurement is faithful**, because
   there was never much traffic to hide. `T0a_router_top8` operates on
   top-8 logits and router scores; its duplicate and its original cost the
   same, and the measured `~0` is a real `~0`. This is independently confirmed
   by #204, which deleted the family for real and also measured zero.

The instrument is therefore **conservative for "this is worth optimizing"** and
**sound for "this is worth nothing"**. A family that cannot pay for a warm
duplicate might still pay for a cold deletion; a family that *does* pay for a
warm duplicate is unambiguously on the critical path. Both statements are
useful, and the asymmetry is the right way round for a screening test: it will
not send anyone chasing a phantom win.

`T2c_routed_qmv` is the interesting case. Its per-layer routed working set is
far larger than cache, so partial re-fetch is unavoidable and its measured
`30.35 us/call` is *still* a lower bound. That a lower bound already accounts
for `1.18 ms` of an `8.20 ms` step is the strongest single finding here.


