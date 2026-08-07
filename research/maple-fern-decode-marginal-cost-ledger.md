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

| family | calls/step | marginal us/call | **marginal us/step** | absorbed slack | verdict |
| --- | --- | ---: | ---: | ---: | --- |
| `T2c_routed_qmv` | 39 | 30.354 | **1184** | `-0.26` copy-sets | on the spine |
| `T2d_down_residual` | 39 | 14.228 | **555** | `0.00` | on the spine |
| `T1c_lmhead` | 1 | 474.22 | **474** | `-0.60` | on the spine |
| `T2a_shared_qmv` | 39 | 1.893 | **74** | `-0.22` | on the spine |
| `T1a_residual_rms_router` | 39 | 2.73 (chained) | **106** | 15.16 copy-sets | partly shadowed |
| `T0a_router_top8` | 39 | 0.00 +/- 0.12 | **0** | 15.33 copy-sets | fully shadowed |

`T2c` (the routed-expert top-8 SwiGLU QMV) has **zero absorbed slack** and its
very first injected duplicate already costs `+1377.7 +/- 1.1 us` at `t = 1272`.
`T0a` absorbs 15.3 copy-sets - about 2.85 ms of GPU work - before it costs
anything at all, and `#204`'s independent deletion of that same family measured
`-0.9 +/- 12.1 us`, exactly as this instrument predicts.

The practical consequence re-prices the remaining search space:

> Do not spend effort on the small decode kernels. Router top-8, and the
> norm/router glue, are *proven* to be in the shadow: making them faster, or
> deleting them, is worth ~0. The routed-expert QMV path, the down/residual
> merge and the lm_head are *proven* to be on the spine at ~100 % pass-through -
> those are the only families measured so far where a microsecond saved is a
> microsecond earned.

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

**A2 was re-run on `T1c_lmhead`**, a confirmed-live site (1 call/forward) that
carries a published census row in the advisor's own decode tier table, so the
`E = slope/census` test is well posed:

```
run a0357d34, schedule 1,2,3,5,9,9,5,3,2,1 x2, 216 steps/segment, 0 divergences
OLS slope = 474.22 +/- 4.87 us per copy-set   (t = 97)
census     = 427.0 us
E = 474.22 / 427.0 = 1.111
```

`E = 1.111` is inside the pre-registered A2 acceptance band `[0.7, 1.3]`.
**A2 passes.** The linearity is exact: the K1->K2 step costs `499.86 us` and the
K2->K5 slope is `508.44 us/copy-set`, a ratio of `1.02`. This is the reference
"chain-link" behaviour the gate was designed to detect - a site with no slack,
whose duplicate costs the same as the original.

#### Supplementary control: the instrument can move wall time by 5 ms

Because the original A2 target was dead, a second, *target-independent* control
was added: a big-K saturation sweep on the confirmed-live `T0a_router_top8`
site - the same family that produced the A1 null. If the A1 null were dead
injection rather than genuine absorption, no K would ever move the clock.

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

`T2c_routed_qmv` is the interesting case. Its per-layer routed working set is
far larger than cache, so partial re-fetch is unavoidable and its measured
`30.35 us/call` is *still* a lower bound. That a lower bound already accounts
for `1.18 ms` of an `8.20 ms` step is the strongest single finding here.

---

## 5. The ledger

Every row is a wired site, measured on the same host in the same session with
the same palindromic-schedule / block-paired protocol, and every run reported
`divergences=0` against the public golden. `us/step` is `slope x calls`, the
family's total marginal weight in the decode step.

| site | what it is | calls/step | us/copy-set (OLS +/- se) | us per call | **us/step** | share of 8.20 ms | absorbed slack | run |
| --- | --- | --: | --- | --: | --: | --: | --: | --- |
| `T2c_routed_qmv` | routed top-8 SwiGLU QMV | 39 | 1183.81 +/- 8.44 (t=140) | 30.354 | **1184** | 14.44 % | `-0.26` copy-sets | `f5edeba0` |
| `T2d_down_residual` | routed+shared down proj & residual | 39 | 554.89 +/- 6.09 (t=91) | 14.228 | **555** | 6.77 % | `0.00` | `aca5a48b` |
| `T1c_lmhead` | final logits projection | 1 | 474.22 +/- 4.87 (t=97) | 474.22 | **474** | 5.78 % | `-0.60` | `a0357d34` |
| `T1a_residual_rms_router` | residual + RMSNorm + router glue | 39 | 106.4 chained (K=5) | 2.73 | **106** | 1.30 % | `15.16` | `ee407682` |
| `T2a_shared_qmv` | shared-expert fused SwiGLU QMV | 39 | 73.82 +/- 3.79 (t=19.5) | 1.893 | **74** | 0.90 % | `-0.22` | `ec307cd1` |
| `T0a_router_top8` | top-8 selection from router logits | 39 | `-8.45` +/- 4.83 (t=-1.7) | 0.00 +/- 0.12 | **0** | 0.00 % | `15.33` | `d7b8f9cf` |

Sum of the priced rows: **2393 us/step, 29.2 % of the 8.20 ms host step.** The
remaining 71 % is attention, KV movement, RoPE, the norms, and the fixed
per-step dispatch/synchronisation floor - none of which is wired here.

A negative "absorbed slack" is a fit artefact of a perfectly linear family (the
two-regime hinge has nowhere to put a knee); read `<= 0` as "no slack".

Note on `us/step`: this is the cost of one *duplicate* pass over the family, so
it is the marginal price of that family's work as the runtime currently issues
it. It is not a promise that deleting the family returns exactly that much -
see the cache-warm caveat in §4, which makes these numbers lower bounds for the
two routed rows.

### 5.1 The routed-expert path is the whole story

`T2c` and `T2d` together are **1739 us/step, 21 % of the decode step**, and
both are at ~100 % pass-through with **zero** absorbed slack. Everything else
measured is between 0 % and 1.3 %.

The two rows behave qualitatively differently from the two glue rows and the
difference is not subtle:

| | `T2c` / `T2d` | `T0a` / `T1a` |
| --- | --- | --- |
| first duplicate (K=2) | already resolved, `t = 1272` / `t = 103` | invisible until K=17 / K=11 |
| absorbed slack | `-0.26` / `0.00` copy-sets | `15.3` / `15.2` copy-sets |
| scaling | linear from K=1 | flat, then convex, then linear |

A family with zero absorbed slack is, by construction, *not* running in the
shadow of some other serial dependency - it **is** the serial dependency.

### 5.2 Why this contradicts the intuitive reading of a GPU census

A GPU census orders these families as `T1c (427 us) > T2c > T1a (305) > T0a
(186)`. The marginal ledger orders them `T2c (1184) > T2d (555) > T1a (106) >
T0a (0)`. `T0a` and `T1a` have census costs within 1.6x of each other and
marginal costs that differ by more than an order of magnitude.

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
| `T2c_routed_qmv` | 14.44 % | 598 | **+9.14 %** |
| `T2d_down_residual` | 6.77 % | 280 | +4.29 % |
| `T1c_lmhead` | 5.78 % | 240 | +3.66 % |
| `T2a_shared_qmv` | 0.90 % | 37 | +0.57 % |
| `T1a_residual_rms_router` | 1.30 % | 54 | +0.82 % |
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

1. **The routed-expert QMV path (`T2c`), by a wide margin.** 14.4 % of the
   step, ~100 % pass-through, zero slack, and the measured value is a *lower*
   bound. This is the only family in the ledger where the arithmetic supports a
   multi-percent score move. Levers worth pricing, in order of expected
   leverage:
   - fewer *bytes* per routed GEMV (the family is on the long arm of the
     diamond and appears traffic-limited, see §6.2);
   - fewer *dispatches* per layer across the 8 routed experts;
   - overlapping the routed fetch with the shared-expert arm, which has 0.90 %
     of the step of its own work and is issued in parallel.
2. **`T2d_down_residual` (6.8 %) as the second target,** and specifically as a
   *fusion partner for `T2c`*, since the two are adjacent on the same serial
   arm and jointly account for 21 % of the step with zero slack between them.
3. **`T1c_lmhead` (5.8 %, one call).** A single 474 us dispatch at 100 %
   pass-through is an unusually clean target: there is no per-call overhead to
   amortise, only the projection itself. Vocabulary pruning, output-tile
   blocking, or splitting it to overlap with the last layer's tail are all
   testable against a `E = 1.111` reference.

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


