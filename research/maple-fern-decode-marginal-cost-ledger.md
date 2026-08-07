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

The steady one-token decode step **absorbs 2.85 ms of extra independent GPU
kernel work at zero wall-time cost** - 35 % of the 8.20 ms step. Below that
threshold the marginal cost of GPU work is statistically zero; above it, work
passes through at 56 % of its census GPU microseconds.

Every kernel family on the decode path has a census cost of 0.12-0.43 ms/step,
i.e. **5-24x below the absorption threshold**. Therefore:

> Making any single decode kernel family cheaper - or deleting it outright -
> buys approximately nothing. The decode step is not throughput-bound.

This is a quantitative explanation for the programme's long run of
"census says 200 us, deletion measures 0 +/- 12 us" results (#204 among them),
and it re-prices the remaining optimization space: the lever is **dispatch
count and dependency-chain depth**, not arithmetic.

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

