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

### 0.1 The census row is not a price, and we can prove it from inside the census

The cleanest falsification is already in the programme's own data and needs no
new instrument. In `#204` the GPU census of the decode step attributes
`1.82 us/call` to `rmsbfloat16`. The same PR's dispatch-overhead fit on the
same host gives a fixed per-dispatch cost `a = 1.661 us` and a per-threadgroup
cost `phi = 1.469 us`, so the *floor* for any single-threadgroup dispatch is
`a + phi = 3.130 us`.

`1.82 < 3.13`. A census row reports **less time than the cheapest possible
dispatch can take**. That is only consistent if the census duration for that
kernel is not a serial slice of the step at all: the reported window overlaps
its neighbours. A number that is internally impossible as an exclusive cost
cannot be used as a budget, and every "census says 200 us here" estimate in the
programme inherits that defect.

This report replaces the census with a *measured* price.

### 0.2 Absorption is per-family, not a single step-level budget

The decode step has a *serial spine* that pays for every microsecond of added
work, and a *shadow* around it in which extra GPU work is free. Which one a
kernel family sits in is a measurable property of that family, and the answer
varies by more than three orders of magnitude across families that look similar
in a GPU census.

Measured pass-through of injected duplicate work, per family, on the same host
in the same session (full ledger and run IDs in §5):

| family | calls/step | marginal us/call | **marginal us/step** | share of step | absorbed slack | `E` | verdict |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `T0b_qkv` | 40 | 31.900 | **1276** | 15.6 % | `-0.17` copy-sets | 0.74 | on the spine |
| `T2c_routed_qmv` | 39 | 30.354 | **1184** | 14.4 % | `-0.26` | 0.75 | on the spine |
| `T2d_down_residual` | 39 | 14.228 | **555** | 6.8 % | `0.00` | 0.62 | on the spine |
| `T1c_lmhead` | 1 | 474.22 | **474** | 5.8 % | `-0.60` | 1.11 | on the spine |
| `T1a_residual_rms_router` | 39 | 2.73 (chained) | **106** | 1.3 % | 15.16 copy-sets | 0.35 | partly shadowed |
| `T2a_shared_qmv` | 39 | 1.893 | **74** | 0.9 % | `-0.22` | 0.31 | thin spine |
| `T0a_router_top8` | 39 | 0.00 +/- 0.12 | **0** | 0.0 % | 15.33 copy-sets | 0.00 | fully shadowed |

`E` is the pass-through efficiency: measured marginal us/step divided by the
independently published GPU-census duration of the same family
(`research/maple-tanjiro-pr73-decode-kernel-census.md`,
`research/nezuko-decode-roofline.md`). `E ~ 1` means an added copy costs what
the census says the original costs. `E ~ 0` means the family is free at the
margin no matter what the census says.

`T0b` (the fused NVFP4 QKV projection) and `T2c` (the routed-expert top-8
SwiGLU QMV) both have **zero absorbed slack**: the very first injected
duplicate already costs `+1629.7 +/- 25.3 us` and `+1377.7 +/- 1.1 us`
respectively. `T0a` absorbs 15.3 copy-sets - about 2.85 ms of GPU work - before
it costs anything at all, and `#204`'s independent deletion of that same family
measured `-0.9 +/- 12.1 us`, exactly as this instrument predicts.

The practical consequence re-prices the remaining search space:

> Do not spend effort on the small decode kernels. Router top-8, and the
> norm/router glue, are *proven* to be in the shadow: making them faster, or
> deleting them, is worth ~0. The fused QKV projection, the routed-expert QMV
> path, the down/residual merge and the lm_head are *proven* to be on the spine
> at 62-111 % pass-through - those are the only families measured so far where
> a microsecond saved is close to a microsecond earned.

The four spine families sum to **3489 us/step, 42.6 % of the 8.20 ms host
step**, priced by direct measurement rather than by census attribution.

This gives a quantitative explanation for the programme's long run of
"census says 200 us, deletion measures 0 +/- 12 us" results, and it converts
that pattern from a mystery into a screening test: **inject before you
optimize.** One 110-second duplicate-injection probe tells you whether a family
can pay, before any kernel is written.

A caveat that runs through the whole report: an injected duplicate re-reads
weights the real dispatch just streamed, so it is *cache-warm*. For families
whose working set exceeds cache the measured marginal is therefore a **lower
bound** on the cost of the real, cold dispatch; for small cache-resident
families it is faithful. This makes the instrument *conservative* about
"worth optimizing" and *sound* about "worth nothing". See §4.

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

### A2 (positive control on `T0b_qkv`) - PASS, after the named site was found dead and re-wired

Pre-registered target: `T0b_qkv`, the decode QKV projection, predicted a
chain-link with `E_pred = 1.0`, acceptance `[0.70, 1.30]`.

The first wiring attached that name to `lagunaNormAffineQKV`, and its first two
runs produced clean, tight nulls (`-9.36 +/- 6.54 us`, then `+0.50 +/- 1.09 us`
at K up to 33). **Those nulls were an artefact.** The all-site `DUPCOUNT`
census added afterwards shows that wiring produced **zero** injected copies in
decode *or* prefill: the site never executes.

Cause (confirmed by source audit, all reasons checkpoint-structural, not
env-dependent): the outer decode fast path at `:5822-5840` passes, but the
norm-fusion inner guard at `:5852-5858` declines because
`lagunaNativeAffineNVFP4From` defaults to `0`, so every layer's bank is
`mode == .nvfp4, bits == 4, groupSize == 16` and fails `mode == .affine &&
bits == 8`; NVFP4 also yields no affine biases, and gate folding requires
group-32 INT8 so `_nativeAffineQKVGateRows` stays `0 != nHeads`.
`lagunaNormAffineQKV` is dead code on this checkpoint.

The *live* decode QKV projection is `lagunaDecodeNVFP4QKVR1`. `T0b_qkv` was
re-wired onto it at `:5883-5887`, the census confirmed `T0b_qkv=40` calls per
decode forward with `copies == 40 x (K-1)`, and A2 was re-run **on its
originally named target**:

```
run ab7e4b94, schedule 1,2,3,5,9,9,5,3,2,1 x2, 216 steps/segment, 0 divergences
DUPCOUNT: T0b_qkv=40 calls/decode-forward, 0 in prefill
OLS slope = 1276.01 +/- 11.48 us per copy-set   (t = 111)
census     = 1722.3 us   (nezuko roofline: h64 1358.4 + h48 363.9)
             1789.6 us   (PR73 pairing: 1408.9 + 380.7)
E = 1276.01 / 1722.3 = 0.741      (0.713 against the PR73 pairing)
```

`E = 0.741` is inside the pre-registered acceptance band `[0.70, 1.30]`.
**A2 passes on its pre-registered target.** Absorbed slack is `-0.17`
copy-sets: the very first duplicate already costs `+1629.7 +/- 25.3 us`
(t = 64), so there is no slack at this site at all.

The shortfall from `E = 1` is itself informative rather than a gate failure,
and §4 shows it is the cache-warm discount: QKV is the one decode family
independently measured at **100 % of the host's roofline bandwidth ceiling**
(260.6 GB/s of 260.6), so a warm duplicate is exactly where a discount should
appear. `E = 0.74` puts that discount at ~26 %.

#### Supplementary A2 control: a confirmed chain-link with `E > 1`

`T1c_lmhead` was measured while the QKV wiring was still believed dead, and it
is retained as the reference chain-link because it is the cleanest linear site
in the ledger:

```
run a0357d34, schedule 1,2,3,5,9,9,5,3,2,1 x2, 216 steps/segment, 0 divergences
OLS slope = 474.22 +/- 4.87 us per copy-set   (t = 97)
census     = 427.0 us  (PR73: 420.6 us)
E = 474.22 / 427.0 = 1.111
```

Its linearity is exact: the K1->K2 step costs `499.86 us` and the K2->K5 slope
is `508.44 us/copy-set`, a ratio of `1.02`. A single 1x2048 x 2048x131072
int5 GEMV has no cache reuse to exploit, so unlike QKV it shows **no** warm
discount - `E` sits just above 1. Two independent sites therefore bracket the
chain-link regime from both sides.

#### Supplementary control: the instrument can move wall time by 5 ms

A second, *target-independent* control: a big-K saturation sweep on the
confirmed-live `T0a_router_top8` site - the same family that produced the A1
null. If the A1 null were dead injection rather than genuine absorption, no K
would ever move the clock.

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

The instrument moves wall time by 5.1 ms when asked to, so the A1 null and the
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

#### 4.1 The warm discount, measured

`T0b_qkv` lets the discount be quantified rather than assumed, because it is
the one decode family with an independent bandwidth measurement.
`research/nezuko-decode-roofline.md:277,281` puts
`decode_nvfp4_qkv_h64_r1_v1` at 11.80 MB/call and **260.6 GB/s**, and
`..._h48` at 9.44 MB/call and **258.9 GB/s**, against a roofline ceiling of
260.6 GB/s measured on this same host. QKV runs at **100 % of the achievable
memory bandwidth** and moves `30 x 11.80 + 10 x 9.44 = 448.4 MB` per decode
step - a quarter of the step's entire 1794 MB.

For a family pinned to the bandwidth ceiling, a warm duplicate is precisely
where a discount must appear, and the ledger measures it directly:

```text
E(T0b) = 1276.01 / 1722.3 = 0.741    =>  warm discount ~= 26 %
E(T1c) = 474.22  /  427.0 = 1.111    =>  no discount (no reuse to exploit)
```

`T1c_lmhead` is the control: one `1x2048 * 2048x131072` int5 GEMV streams a
weight matrix far too large for any cache and is read exactly once by the
original, so its duplicate gets no help and `E` sits just above 1. QKV re-reads
a 11.8 MB bank that the original just pulled in, and keeps 74 % of the cost
anyway. So on this host the cache-warm discount on a 100 %-of-roofline family
is about a quarter, not an order of magnitude - which bounds how much the
ledger's spine rows are understated.

Applying the same reading to the routed rows: `E(T2c) = 1183.81/1569.8 = 0.754`
and `E(T2d) = 554.89/898.8 = 0.617`. All three streaming families land in
`0.62-0.75`, consistent with one shared mechanism rather than three
coincidences.

`T2c_routed_qmv` remains the interesting case. Its per-layer routed working set
is far larger than cache, so partial re-fetch is unavoidable and its measured
`30.35 us/call` is *still* a lower bound. That a lower bound already accounts
for `1.18 ms` of an `8.20 ms` step is one of the two strongest findings here;
`T0b`'s `1.28 ms` is the other.

---

## 5. The ledger

Every row is a wired site, measured on the same host in the same session with
the same palindromic-schedule / block-paired protocol, and every run reported
`divergences=0` against the public golden. `us/step` is `slope x calls`, the
family's total marginal weight in the decode step.

| site | what it is | calls/step | us/copy-set (OLS +/- se) | us per call | **us/step** | share of 8.20 ms | absorbed slack | census us | `E` | run |
| --- | --- | --: | --- | --: | --: | --: | --: | --: | --: | --- |
| `T0b_qkv` | fused NVFP4 QKV projection | 40 | 1276.01 +/- 11.48 (t=111) | 31.900 | **1276** | 15.56 % | `-0.17` copy-sets | 1722.3 | 0.741 | `ab7e4b94` |
| `T2c_routed_qmv` | routed top-8 SwiGLU QMV | 39 | 1183.81 +/- 8.44 (t=140) | 30.354 | **1184** | 14.44 % | `-0.26` | 1569.8 | 0.754 | `f5edeba0` |
| `T2d_down_residual` | routed+shared down proj & residual | 39 | 554.89 +/- 6.09 (t=91) | 14.228 | **555** | 6.77 % | `0.00` | 898.8 | 0.617 | `aca5a48b` |
| `T1c_lmhead` | final logits projection | 1 | 474.22 +/- 4.87 (t=97) | 474.22 | **474** | 5.78 % | `-0.60` | 427.0 | 1.111 | `a0357d34` |
| `T1a_residual_rms_router` | residual + RMSNorm + router glue | 39 | 106.4 chained (K=5) | 2.73 | **106** | 1.30 % | `15.16` | 305.1 | 0.349 | `ee407682` |
| `T2a_shared_qmv` | shared-expert fused SwiGLU QMV | 39 | 73.82 +/- 3.79 (t=19.5) | 1.893 | **74** | 0.90 % | `-0.22` | 237.5 | 0.311 | `ec307cd1` |
| `T0a_router_top8` | top-8 selection from router logits | 39 | `-8.45` +/- 4.83 (t=-1.7) | 0.00 +/- 0.12 | **0** | 0.00 % | `15.33` | 185.7 | -0.045 | `d7b8f9cf` |

Sum of the priced rows: **3669 us/step, 44.7 % of the 8.20 ms host step**, of
which the four spine rows are **3489 us, 42.6 %.** The remaining ~55 % is
attention, KV movement, RoPE, the norms, and the fixed per-step
dispatch/synchronisation floor - none of which is wired here.

Every `E` is measured marginal over the independently published census
duration for the same family. Reading down the column, the ledger separates
three regimes cleanly: `E ~ 1` chain-link (`T1c`), `E ~ 0.6-0.75` streaming
chain-link with a cache-warm discount (`T0b`, `T2c`, `T2d`), `E <= 0.35`
shadowed or thin (`T1a`, `T2a`, `T0a`).

A negative "absorbed slack" is a fit artefact of a perfectly linear family (the
two-regime hinge has nowhere to put a knee); read `<= 0` as "no slack".

Note on `us/step`: this is the cost of one *duplicate* pass over the family, so
it is the marginal price of that family's work as the runtime currently issues
it. It is not a promise that deleting the family returns exactly that much -
see the cache-warm caveat in §4, which makes these numbers lower bounds for the
two routed rows.

### 5.1 The big weight-streaming projections are the whole story

`T0b`, `T2c` and `T2d` together are **3015 us/step, 37 % of the decode step**,
all three with **zero** absorbed slack and `E` in `0.62-0.75`. Add the lm_head
and the four spine rows are 42.6 %. Everything else measured is between 0 % and
1.3 %.

The spine rows behave qualitatively differently from the glue rows and the
difference is not subtle:

| | `T0b` / `T2c` / `T2d` | `T0a` / `T1a` |
| --- | --- | --- |
| first duplicate (K=2) | already resolved, `t = 64` / `1272` / `103` | invisible until K=17 / K=11 |
| absorbed slack | `-0.17` / `-0.26` / `0.00` copy-sets | `15.3` / `15.2` copy-sets |
| scaling | linear from K=1 | flat, then convex, then linear |

A family with zero absorbed slack is, by construction, *not* running in the
shadow of some other serial dependency - it **is** the serial dependency.

What the three share is not FLOPs and not dispatch count, it is **bytes**:
each is a quantized weight bank read once per token with no reuse. The lever
they respond to is bytes moved per token, which is also the only lever that
survives the move to the ranked M5 (614 GB/s, ~89 % instruction-bound) with a
predictable sign.

### 5.2 Why this contradicts the intuitive reading of a GPU census

A GPU census orders these families as `T0b (1722) > T2c (1570) > T2d (899) >
T1c (427) > T1a (305) > T0a (186)`. The marginal ledger orders them
`T0b (1276) ~ T2c (1184) > T2d (555) > T1c (474) > T1a (106) > T0a (0)`. The
top of the list survives; the bottom does not. `T0a` and `T1a` have census
costs within 1.6x of each other and marginal costs that differ by more than an
order of magnitude, and `T1a`'s census (305 us) is 1.6x `T0a`'s while both are
worth essentially nothing at the margin.

The census is therefore not useless - it is a good *upper* bound and it ranks
the large streaming families correctly. It fails exactly where the programme
kept getting burned: on the small kernels, where it reports plausible
three-figure microsecond costs for work that is entirely hidden.

Census answers "how many GPU microseconds does this kernel occupy". The decode
step is not asking that question. It is asking "does this kernel sit on the
chain that the next token has to wait for", and only the ledger answers it.

### 5.3 A naming collision worth fixing

`fern_dup_stats.py` prints a quantity it calls "shadow ratio", meaning *the
smallest K whose block-paired contrast clears 2 sigma* - a **detection**
threshold. The advisor's "shadow ratio" is a different, **static** quantity:
`(duration of the largest covering sibling) / (duration of the target)`, with
`< 3x` flagged as an M5-flip risk.

To avoid confusion, this report renames the script's metric **"resolution K"**
and never uses "shadow ratio" for it. The dynamic analogue of the advisor's
static shadow ratio is the **absorbed slack in microseconds** column: it is the
measured amount of covering work available to hide a duplicate, expressed in
time rather than as a ratio. The mapping is:

| static (advisor) | dynamic (this report) | reading |
| --- | --- | --- |
| shadow ratio `>> 3x` | absorbed slack large (`T0a`: 2.85 ms) | safely shadowed |
| shadow ratio `~ 1x` | absorbed slack `~ 0` (`T2c`, `T2d`, `T1c`) | on the spine |
| shadow ratio near `3x` | slack of the same order as the target | **M5-flip risk** |

The static predicate that generates the shadow, adopted from #204 and verified
structurally here, is:

> `X` is a side branch iff every consumer of `X` also transitively depends on a
> sibling `Y` with duration `>> X`, issued no later than `X`. **The short arm of
> a diamond is free.**

`T0a_router_top8` satisfies it at `LagunaRuntimeModel.swift:10100-10130`:
`lagunaRoutedSharedDownResidual` consumes both `routerWeights` (short arm,
through top-8) and `routedActivated` (long arm, through the routed QMV), and
both depend on `router_keys`. `T2c` sits on the *long* arm of that same
diamond, which is exactly why it prices at ~100 %.

---

## 6. Translating the ledger into score

At the promoted receipt (`97a5090`: `S = 97.895 ms`, `T = 4.1436 ms`,
`officialScore = 2.58883`) the score derivative for the decode axis is
**0.015280 % of score per microsecond removed from the per-step `T`**.

Because the M5 step is `4.1436 ms` against this host's `8.20 ms`, a *share of
step* transfers across hosts more honestly than an absolute microsecond count.
Taking the measured share and re-pricing it on the M5 step gives a directional
upper bound on what a perfect removal of each family could be worth:

| family | share of host step | M5-equivalent us/step | directional score `+%` if fully removed |
| --- | --: | --: | --: |
| `T0b_qkv` | 15.56 % | 645 | **+9.85 %** |
| `T2c_routed_qmv` | 14.44 % | 598 | **+9.14 %** |
| `T2d_down_residual` | 6.77 % | 280 | +4.29 % |
| `T1c_lmhead` | 5.78 % | 240 | +3.66 % |
| `T1a_residual_rms_router` | 1.30 % | 54 | +0.82 % |
| `T2a_shared_qmv` | 0.90 % | 37 | +0.57 % |
| `T0a_router_top8` | 0.00 % | 0 | **+0.00 %** |

These are *ceilings on a fully successful removal*, not forecasts. Nobody
deletes a routed-expert projection. The row that matters operationally is the
last one: a perfect `T0a` optimisation is worth `+0.00 %`, which is what #204
found the hard way after building the kernel.

Two caveats, both stated so the numbers are not over-read:

1. **Cross-host transfer is directional only.** M4 Pro is generation 16 with
   20 cores and 273 GB/s; the ranked M5 Max is generation 17 with 40 cores and
   614 GB/s and is instruction-bound at ~89 % utilisation. A family that is
   bandwidth-shadowed here can be exposed there and vice versa. The share-of-
   step transfer assumes the *ratio* of family cost to step cost is preserved,
   which is an assumption, not a measurement.
2. **The routed rows are lower bounds** (§4), so their true ceilings are higher
   than shown, which only strengthens the ranking.

### 6.1 What to build next, and what is now formally closed

**Closed - do not spend another experiment here:**

- **Router top-8 selection / fusion of anything into it.** Measured marginal
  `0.00 +/- 0.12 us/call`, 15.3 copy-sets (2.85 ms) of absorbed slack, and an
  independent real deletion in #204 that measured `-0.9 +/- 12.1 us`. Two
  independent methods, same answer. Any future proposal that prices this family
  from a census row should be rejected on sight.
- **Residual/RMSNorm/router glue (`T1a`) as a throughput target.** Unchained
  marginal at K=5 is `1.01 us/call`; the family absorbs 15.2 copy-sets. Only its
  *serial depth* (2.73 us/call chained) is even visible, and it is 1.3 % of the
  step. A fusion that removes a dispatch from this chain is worth at most
  `+0.8 %` and realistically far less.
- **Shared-expert QMV (`T2a`) as a standalone target.** On the spine, but
  0.90 % of the step: `+0.57 %` ceiling for perfect removal. Only worth touching
  as a free rider on a `T2c` change.

**Open and now justified by measurement:**

1. **The fused NVFP4 QKV projection (`T0b`), the largest single family.**
   15.6 % of the step, `E = 0.74`, zero slack, 40 calls, and independently
   measured at **100 % of this host's roofline bandwidth** while moving
   448.4 MB/step. Being pinned to the bandwidth ceiling is the strongest
   possible statement about which lever works: only *fewer bytes* can help,
   because tiling, occupancy and dispatch count have nothing left to recover
   on this host. Concretely - a narrower KV representation, or fusing the
   `h64`/`h48` variants so the bank is read once instead of per-head-group.
   Note the M5 caveat: it is ~89 % instruction-bound at 614 GB/s, so a
   byte-reduction that is a pure win here may be neutral there, and the sign
   of any *occupancy* change is not transferable at all.
2. **The routed-expert QMV path (`T2c`), essentially tied with `T0b`.** 14.4 %
   of the step, `E = 0.75`, zero slack, and the measured value is a *lower*
   bound. Levers worth pricing, in order of expected leverage:
   - fewer *bytes* per routed GEMV (the family is on the long arm of the
     diamond and, like `T0b`, is traffic-limited - see §6.2);
   - fewer *dispatches* per layer across the 8 routed experts;
   - overlapping the routed fetch with the shared-expert arm, which has 0.90 %
     of the step of its own work and is issued in parallel.

   `T0b` and `T2c` differ by `92 +/- 14 us/step`, but they were measured in
   different worker sessions where arm-level scatter is `+/- 70 us`. Treat them
   as **comparable, both ~1.2 ms**, not as a strict ordering.
3. **`T2d_down_residual` (6.8 %) as the third target,** and specifically as a
   *fusion partner for `T2c`*, since the two are adjacent on the same serial
   arm and jointly account for 21 % of the step with zero slack between them.
4. **`T1c_lmhead` (5.8 %, one call).** A single 474 us dispatch at 111 %
   pass-through is an unusually clean target: there is no per-call overhead to
   amortise, only the projection itself. Vocabulary pruning, output-tile
   blocking, or splitting it to overlap with the last layer's tail are all
   testable against a `E = 1.111` reference.

**Not yet priced, and the obvious next probe:** attention and o-proj
(`sliding_fused_attn_ring_v1`, `full_fused_attn_grow_v1`, `oproj_act_h64/h48`)
carry ~27 % of the census between them and are deliberately unwired here
because their kernels mutate KV in place and advance the cache clock, so a
duplicate is not side-effect-free. Pricing them needs a
copy-on-write KV scratch buffer for the duplicate - a real but bounded piece of
instrument work, and the single highest-value extension of this ledger.

**Method recommendation for the programme:** make a duplicate-injection probe
the *first* step of any decode optimisation proposal. It costs one 110-second
run, it needs no kernel to be written, and it would have pre-empted at least
three of the last several negatives.

### 6.2 One unresolved arithmetic puzzle

`T2c`'s marginal is `1184 us` per duplicate pass over 39 layers. If the routed
top-8 weights read per decode step were ~552 MB, the implied rate would be
`552 MB / 1.184 ms = 466 GB/s`, which **exceeds this host's 273 GB/s peak**.
The measurement is internally consistent and highly significant (`t = 140`), so
one of the following must hold:

1. the 552 MB routed-weight figure is wrong for this checkpoint's decode path;
2. the duplicate enjoys real cache reuse and therefore moves substantially
   fewer bytes than the original (which would make the `1184 us` an even
   *stronger* lower bound on the original's cost);
3. the marginal is not bandwidth-bound at all but launch/occupancy-bound, in
   which case the lever is dispatch count and tile shape rather than bytes.

This is flagged rather than resolved. It matters for §6.1's ordering of levers
within `T2c`, not for the ledger itself, and it does not affect any pass/fail
verdict in this report. Resolving it needs a byte-counting probe (GPUPROF
`bytes_read` per dispatch family), which is a separate experiment.

---

## 7. Pre-registration scorecard

The predictions were landed in `research/maple-fern-decode-ledger-prereg.md`
at commit `d9edc28`, **before any probe was run**. Every row below compares that
frozen prediction with the measurement.

| # | site | pre-reg verdict | `E_pred` | `E_range` | census us/step | measured slope us/copy-set | measured `E` | outcome |
| --- | --- | --- | --: | --- | --: | --- | --: | --- |
| T0a | `router_top8` | side-branch | 0.00 | [-0.16, 0.16] | 185.7 | `-8.45 +/- 4.83` | `-0.045` | **confirmed** |
| T0b | fused QKV | chain-link | 1.00 | [0.70, 1.30] | n/a | `1276.01 +/- 11.48` | n/a | **qualitatively confirmed** (zero slack, linear from K=1); no census row to divide by |
| T1a | `residual_rms_router` | chain-link | 1.00 | [0.70, 1.30] | 305.1 | `106.4` chained / `39.5` unchained | `0.349` / `0.129` | **refuted** |
| T1c | `lmhead` | chain-link | 1.00 | [0.70, 1.30] | 427.0 | `474.22 +/- 4.87` | `1.111` | **confirmed** |
| T2a | `shared_qmv` | side-branch | 0.10 | [-0.10, 0.35] | 237.5 | `73.82 +/- 3.79` | `0.311` | **confirmed** |
| T2c | routed QMV | chain-link | 1.00 | [0.70, 1.30] | n/a | `1183.81 +/- 8.44` | n/a | **qualitatively confirmed** (zero slack) |
| T2d | down + residual | chain-link | 1.00 | [0.70, 1.30] | n/a | `554.89 +/- 6.09` | n/a | **qualitatively confirmed** (zero slack) |
| T1b | `rmsbfloat16` | chain-link, `E_pred = 1.70` | 1.70 | [1.00, 2.20] | 124.6 | not wired | - | **not measured** |
| T2b | `gate_sp` | side-branch | 0.10 | [-0.10, 0.35] | 262.3 | wired, live (40 calls), not timed | - | **not measured** |
| T3a/b/c | attention, o-proj | chain-link | 0.95 | [0.70, 1.30] | n/a | not wired | - | **not measured** |

Four of five computable predictions landed inside their pre-registered bands.

**The one refutation is `T1a`, and it is the informative one.** It was
pre-registered as a chain-link because `lagunaResidualRMSNormRouter` sits
structurally between the residual stream and the router, and every downstream
consumer needs it. That is true, and it is still shadowed: measured `E = 0.349`
chained and `E = 0.129` unchained, both far below the `[0.70, 1.30]` band, with
15.16 copy-sets of absorbed slack. Being *topologically* on the path is not the
same as being *temporally* on the critical path - the routed-expert arm issued
alongside it is long enough to hide almost all of it. This is precisely the
failure mode that a static dependency analysis cannot catch and that this
instrument exists to catch.

`T2a` is the mirror image and worth stating explicitly: pre-registered as a
side branch at `E_pred = 0.10`, measured `E = 0.311` - inside the band, but at
its top edge, and with **zero absorbed slack**. It is a *small* chain-link, not
a side branch. The `E` band accepted it for the wrong reason; the slack column
is the diagnostic that separates them.


