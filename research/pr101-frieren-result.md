# PR #101 — maple-frieren result: double NO-GO, plus a dispatch-concurrency finding

Assignment `maple-2026-08-06h-gatesp-occupancy-oproj-hoist` r1.
BASE_SHA `1d12077a26f3300fa0fa784105d3c6c5b8847d57`. Host: Apple M4 Pro,
14 CPU / 20 GPU cores, 48 GB, macOS 26.5.2 (25F84), Apple GPU generation 16.

**Verdict: NO-GO on Arm A. NO-GO on Arm B. Zero submitted bytes.**
Both arms are reverted; the submitted surface is byte-identical to BASE_SHA.

The primary deliverable of this ticket is not either arm. It is the mechanism
that explains why both are null, which was measured directly and which narrows
the scope of one programme law.

---

## 0. Preflight, scope and correctness bookkeeping

```
assignment scope OK: 1 submitted path(s) against BASE_SHA=1d12077a26f3300fa0fa784105d3c6c5b8847d57
editable budget OK: current=2934331/3000000 bytes headroom=65669 growth=0/262144 files=142 (file count is diagnostic only; base=142)
```

Submitted-surface diff versus every base SHA this branch has been offered:

```
git diff 1d12077a -- Sources/ Vendor/ Package.swift Package.resolved benchmark.json   -> empty
git diff 0dd2be7  -- Sources/ Vendor/ Package.swift Package.resolved benchmark.json   -> empty
```

`0dd2be7` is the current advisor-branch head. Six commits landed on the base
after my assignment was cut (`dec0a83c`, `bbc9e7bb`, `b60bdd75`, `2f3ed2e2`,
`c5038fb`, `0dd2be7`); I verified each is zero submitted bytes rather than
taking the notices on trust, per §R19.4. No rebase is owed and no pool needs
re-measuring.

Build of the fully reverted tree, including the reverted Cmlx probe:
`swift build -c release --force-resolved-versions --product mlxfast-runtime-worker --scratch-path .build-worker`
— green in 49.30 s, only the pre-existing `mergedSharedActivated` and
`EngineLoopV2` Sendable warnings. `Package.resolved` unchanged.

**`run_upstream_equivalence.sh` was deliberately NOT run, and no
`golden_hash`/`harness_hash` pair is quoted.** The candidate is byte-identical
to the baseline over the entire submitted surface, so an equivalence run would
be comparing the base against itself. Stating that plainly is more honest than
producing a pass that certifies nothing. The same reasoning retires the
`--local-iterate` ABBA requirement for this result. If the advisor wants either
artefact for the record I will run it on request.

**All timing in this report is wall-clock.** `DARKBLOOM_GPU_PROFILE` hooks are
not present anywhere in the current source, so `research/decode_probe.py
--profile` returns `profile: no GPUPROF records`. There is consequently **no
profile-hook revert SHA to report** — there were never any hooks to revert. The
kernel-level attribution the brief asked for came instead from an isolated
Metal microbenchmark (§4) and from the PR #73 census.

---

## 1. Arm A — `gate_sp` R×NS occupancy: NULL

### 1.1 What was built

`lagunaGateSoftplusSource(heads:rows:simdgroups:)` gained `R` and `NS` as
parameters read from `DARKBLOOM_GATESP_R` / `DARKBLOOM_GATESP_NS` (allow-list
`[1,2,4]`, defaults `4` / `2` = stock). The grid divisor was changed from the
hardcoded `heads/8` to `heads/(NS*R)` exactly as the brief required, and the
kernel name gained an `_r{R}n{NS}` suffix so the JIT cache cannot alias two
geometries. The K loop was not touched; K is not split.

Stock `R4NS2` at h64 is 8 threadgroups on this 20-core GPU; `R1NS1` is 64.

**Plumbing was proved live before any timing was trusted.** A temporary stderr
banner was compiled in, two 8-step probes were run, and the banner was
reverted:

```
/tmp/plumb_r1n2.txt:GATESP-PLUMB r=1 ns=2
/tmp/plumb_r4n2.txt:GATESP-PLUMB r=4 ns=2
```

### 1.2 Bit-exactness: a standalone oracle that has a live control

`research/frieren_pr101_gatesp_bitwise.swift` (386 lines) compiles the runtime's
own kernel template out of `LagunaRuntimeModel.swift` and compares payloads
across geometries.

```
drift guard   : harness body matches runtime template tail (796 bytes)
device        : Apple M4 Pro ; compile opts: mathMode=safe languageVersion=262144
h64/h48 x 8 non-stock geometries: BITWISE EQUAL on 4/4 payloads at bfloat AND at float32
CONTROL: perturbed kernel flagged at float32 (15/64 rows differ)
RESULT: PASS -- 128 payload comparisons bitwise equal across 9 geometries
```

**Three separate controls were vacuous before this one worked, and the
diagnosis is reusable methodology worth more than the certificate:**

1. Seeding `r[0] = 1e-30f` — lost to rounding against an O(1) accumulator.
2. Commuting `s*a + sum*b` to `sum*b + s*a` — **undetectable in principle**;
   IEEE-754 addition is exactly commutative.
3. Reverse-order inner dot `for (uint i = V; i-- > 0;)` — a genuine
   reassociation, but **invisible in the kernel's own bfloat output**. It moves
   the float32 total by ~1 ulp (~1e-7 relative) while bfloat resolves only
   ~2e-3, so it survives rounding with probability ~1e-4 per value, ~1.3 % over
   256 samples.

Control 3 is the important one: **a bitwise oracle that scores the kernel's
native low-precision output can certify a property strictly weaker than the one
it appears to certify.** The fix was a `raw` float32 probe mode that replaces
the softplus epilogue with a dump of the pre-rounding accumulator `r[row]`. The
same control that moves 0/64 rows at bfloat moves 15/64 rows at float32 —
empirical confirmation of the masking, not an argument for it. The certificate
is now strictly finer than the property certified.

The harness also carries a drift guard that extracts the runtime body tail and
dies on mismatch, and a degenerate-payload guard that dies if fewer than 75 % of
rows are normal and distinct.

### 1.3 Nine-geometry sweep, two rounds, forward and reverse order

400-step runs, 8 warm-ups dropped (n = 392), every point refused unless it
reported `0 divergences (all match)`.

| geometry | r1 median | r2 median | avg | vs stock | r1−r2 gap |
|---|---|---|---|---|---|
| `gatesp_r4n2` (**stock**) | 8.283 | 8.287 | 8.285 | 0.00 % | 0.004 |
| `gatesp_r4n4` | 8.282 | 8.276 | 8.279 | −0.07 % | 0.006 |
| `gatesp_r4n1` | 8.293 | 8.173 | 8.233 | −0.63 % | **0.120** |
| `gatesp_r2n2` | 8.316 | 8.310 | 8.313 | +0.34 % | 0.006 |
| `gatesp_r2n4` | 8.321 | 8.305 | 8.313 | +0.34 % | 0.016 |
| `gatesp_r2n1` | 8.303 | 8.380 | 8.341 | +0.68 % | **0.077** |
| `gatesp_r1n2` | 8.279 | 8.286 | 8.282 | −0.03 % | 0.007 |
| `gatesp_r1n4` | 8.281 | 8.264 | 8.273 | −0.15 % | 0.017 |
| `gatesp_r1n1` | 8.277 | 8.274 | 8.275 | −0.11 % | 0.003 |

All nine stable points span 8.273–8.313 ms = **0.48 %**, with stock mid-pack.
The two apparently-best points, `r4n1` and `r2n1`, are precisely the two with
the largest round-to-round gaps (0.120 and 0.077 ms). They are instability, not
effect. Reporting all nine — as the brief demanded — is what makes that visible;
reporting only the winner would have produced a −0.63 % "result".

### 1.4 Round 3: high-power drift-balanced ABBA on the single best candidate

8 runs × 400 steps, order A B B A A B B A, A = stock `R4NS2`, B = `R1NS2`.
All 8 runs `0 divergences (all match)`.

```
run                 n     mean   median      p10      min       sd
g01_stock_r4n2      392    8.319    8.322    8.252    8.200    0.058
g02_cand_r1n2       392    8.309    8.310    8.250    8.100    0.053
g03_cand_r1n2       392    8.265    8.311    8.115    8.011    0.110
g04_stock_r4n2      392    8.364    8.351    8.260    8.204    0.146
g05_stock_r4n2      392    8.236    8.233    8.045    8.007    0.199
g06_cand_r1n2       392    8.285    8.281    8.146    8.033    0.107
g07_cand_r1n2       392    8.292    8.299    8.222    8.095    0.080
g08_stock_r4n2      392    8.314    8.308    8.264    8.224    0.052

stat        stock     cand    effect              within-stock  within-cand  verdict
mean        8.308    8.288   +0.020 ms (-0.25%)      0.128        0.044      BELOW noise
median      8.303    8.300   +0.003 ms (-0.04%)      0.118        0.030      BELOW noise
p10         8.205    8.183   +0.022 ms (-0.27%)      0.220        0.135      BELOW noise
min         8.159    8.060   +0.099 ms (-1.22%)      0.217        0.088      BELOW noise

permutation over run medians: observed +0.003 ms, p = 62/70 = 0.886
pooled over all rounds: 6 stock, 6 cand run medians
  effect +0.003 ms  95% CI [-0.040, +0.046] ms
  as a step-time change: -0.04%  95% CI [-0.55%, +0.48%]
```

(Analyzer convention `effect = stock − cand`, positive = candidate faster.)

**Arm A price: −0.04 % step time, 95 % CI [−0.55 %, +0.48 %], on M4 wall-clock.**
Interval, not a point estimate, as required. The interval straddles zero.

**An honest note on the noise floor.** The within-stock median spread in this
ABBA is **0.118 ms = 1.4 %** — considerably wider than the ±0.5 % I had assumed
from the earlier sweep. The 8-run round-3 interval alone does *not* exclude the
−0.87 % microbench bracket of §4; only the pooled 12-run interval does. I am
reporting the wider figure because it is the one my own data supports.

### 1.5 Settled: `gate_sp` unique DRAM = 5.5296 MB/step

Counted from the declared shapes, not inferred from a timing delta:
2304 B/row × 2400 rows = **5.5296 MB/step**. This **invalidates PR #73's
7.86 MB/step** (`research/maple-tanjiro-pr73-decode-kernel-census.md:417`,
`:527`). The 7.86 figure is `5.5296 + 2.4576` MB, where the second term is
redundant per-simdgroup re-reads of the *same* input rows — L2 hits, not DRAM
traffic. Other briefs cite 7.86; they should be corrected.

Per §R20.2 and §0.9.39 I am **not** converting this count into a percent.

**Arm A side-effect that must be on the record:** dropping R from 4 to 1
multiplies those redundant input re-reads by 4×, from ~2.46 MB/step to
~9.83 MB/step. They remain L2-resident so they do not add DRAM traffic, but the
candidate is not strictly cheaper in every channel.

---

## 2. Arm B — o_proj lane-major scale-base hoist: NULL

### 2.1 What was built

`lagunaGatedAffineOProjNVFP4Source` gained `hoistBases: Bool`, gated by
`DARKBLOOM_OPROJ_LM_HOIST=1` (default off). Following the two in-file
precedents the brief named (QKV `:4748-4765`, routed `:7743-7757`), the hoist
declares `thread uint8_t rbv[results_per_simdgroup]` and
`thread bool escv[...]` in the lane-major `scaleSetup` block after
`uint nsh = 0;`, fills them unrolled from `bs[row]`, and rewrites `scaleRead` to
consume them. `scaleAdvance` is untouched: the pointer walk still advances
`sc`/`nq`/`nsh` identically. A `_hb1` name suffix was added at **both**
lane-major sites.

**Dependent-load count per lane, before → after:** h64 `4 × 16 = 64 → 4`;
h48 `4 × 12 = 48 → 4`. The `rb` load and the `esc` derivation move from
once-per-(row × K-iteration) to once-per-row.

**Reachability confirmed, not assumed:** `oproj_act_h64_v1_lm1_pw1_sc1_se1` and
`..._h48_...` both appear on the scored decode path in
`research/pr82-r3-logs/*.txt`. Arm B did reach the scored runtime.

### 2.2 Result

Round 1 looked like a win: mean −0.85 %, p10 −1.32 %. It was not. It was drift
plus a single 11.478 ms outlier inside the OFF run. Round 2 re-ran it as a
drift-balanced OFF/ON/ON/OFF ABBA, 400 steps per run, 8 warm-ups dropped, all
runs `0 divergences`:

| run | n | mean | median | p10 | min | sd |
|---|---|---|---|---|---|---|
| `armb_off_a` | 392 | 8.324 | 8.326 | 8.251 | 8.108 | 0.067 |
| `armb_on_b` | 392 | 8.269 | 8.245 | 8.126 | 8.053 | 0.126 |
| `armb_on_c` | 392 | 8.313 | 8.319 | 8.256 | 8.145 | 0.056 |
| `armb_off_d` | 392 | 8.288 | 8.285 | 8.148 | 8.092 | 0.110 |

Contrast ON − OFF: mean −0.18 %, median −0.28 %, p10 −0.11 %, min −0.02 % —
**every statistic below the within-condition run-to-run gap.**

**Arm B price: null; no statistic separates from the within-condition gap.**

The mechanism is plausible and the instruction count really does drop by ~16×.
It does not show up. The most likely reason is that the hoisted loads were
already L1/register-resident and fully hidden behind the dependent `sp[0]` chain
and the qmv's memory traffic, so removing them removes issue slots that were not
on the critical path.

---

## 3. Why both arms are null — the mechanism, measured

### 3.1 The code path

Three facts, all verified in source on the reverted tree:

- `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp:548` — MLX
  opens **every** compute encoder with `MTL::DispatchTypeConcurrent`.
- `device.cpp:318-375` — `needs_barrier_` is set **only** on a real hazard.
  `set_input_array` ORs in `prev_outputs_.find(r_buf) != prev_outputs_.end()`
  (RAW); `register_output_array` ORs in `prev_inputs_.find(buf)` (WAR) and only
  when not in a concurrent context. `maybeInsertBarrier()` emits
  `memoryBarrier(MTL::BarrierScopeBuffers)` from `dispatch_threadgroups`.
- `Sources/MLXFastModel/LagunaRuntimeModel.swift:5758` —
  `let normalized = fusedQKV ?? inputNorm(input)`; `:5761-5762` feeds
  `normalized` to `lagunaDecodeNVFP4QKVR1`; `:5802-5803` feeds **the same
  `normalized`** to `lagunaGateSoftplus`.

`gate_sp` consumes QKV's *input*, not QKV's *output*. There is no RAW or WAR
hazard between them, therefore MLX inserts **no barrier** between them,
therefore under a concurrent encoder they are in the same barrier group and may
execute **simultaneously**.

An ~5 µs, 8-threadgroup kernel running in the shadow of a multi-MB QKV qmv has
near-zero marginal cost. That predicts exactly what §1.3 found: nine geometries
that are markedly faster *and* markedly slower in isolation all compressing into
a 0.48 % band with stock mid-pack.

### 3.2 The measurement

I tested the mechanism directly rather than leaving it as a story. A research
probe (env-gated, in `device.cpp`, **now reverted** — `device.cpp` is not in
`editablePaths` so it could never ship) switches the encoder between
`MTL::DispatchTypeConcurrent` and `MTL::DispatchTypeSerial`. Command-buffer
count and kernel code are unchanged; only encoder dispatch type varies.

8 runs × 400 steps, ABBA-ABBA, A = concurrent (shipped), B = serial:

```
run                 n     mean   median      p10      min       sd
s01_concurrent      392    8.284    8.317    8.116    8.074    0.100
s02_serial          392    8.803    8.804    8.746    8.689    0.057
s03_serial          392    8.750    8.727    8.592    8.527    0.136
s04_concurrent      392    8.265    8.254    8.204    8.143    0.064
s05_concurrent      392    8.314    8.318    8.252    8.119    0.059
s06_serial          392    8.752    8.746    8.643    8.553    0.105
s07_serial          392    8.762    8.787    8.607    8.544    0.132
s08_concurrent      392    8.351    8.351    8.281    8.134    0.079

median: concurrent 8.310, serial 8.766 -> -0.456 ms  (+5.49% cost to serialise)
pooled 95% CI [-0.522, -0.390] ms  ==  [+4.70%, +6.28%]
permutation over run medians: p = 2/70 = 0.029  (the exact minimum for 4-vs-4)
complete separation: every concurrent median < every serial median
```

Validity: the plumbing banner confirmed the ABBA order live in each worker
(`s01=0, s02=1, s03=1, s04=0, s05=0, s06=1, s07=1, s08=0`); all 8 runs report
`0 divergences (all match)` — serial dispatch is strictly more conservative than
concurrent-plus-barriers, so bit-identity is expected, and it is confirmed
rather than assumed.

**There is 0.456 ms/step — 5.5 % of the decode step — of real dispatch-level
concurrency in this workload.**

### 3.3 Scope correction to §R20.5

§R20.5 rests on the #73 census:

> "`gpu_busy_sum == gpu_busy_union` to 1 µs in every run ⇒ there is zero
> dispatch concurrency in decode ⇒ per-kernel times are strictly additive. This
> is the licence for every arithmetic operation in this report and it is
> measured, not assumed."
> — `research/maple-tanjiro-pr73-decode-kernel-census.md:178-180`

That measurement is correct at the grain at which it was taken, and the census
deserves credit for making the two-point SPLIT=0/SPLIT=1 measurement that made
this finding possible at all. The correction is one of **scope, not accuracy**:

Each command buffer contributes exactly one `[gpuStartTime, gpuEndTime]`
interval. `union == sum` therefore proves only that **at most one command buffer
is GPU-resident at a time**. Dispatch-level overlap *inside* a command buffer
shortens that interval and is invisible by construction. And the census's
zero-concurrency reading was taken under SPLIT=1 — the configuration in which
CB grain and dispatch grain coincide, which is **the configuration that removes
the concurrency it reports as absent.** This is an observer effect in the
instrument's design, not a mis-measurement.

The advisor's r1 guidance — *"If you find yourself explaining a win as 'the
shorter dispatch let something else start earlier', that explanation is refuted
before you write it"* — follows validly from §R20.5 as stated. The probe shows
the premise holds only at command-buffer grain, and I am flagging that because
it is the single most load-bearing correction in this report. It did not change
my verdict: both arms are still NO-GO. It changes what the null *means*.

### 3.4 Decomposing the census's per-CB constant

```
census.md:316   (8.883 - 8.276) ms / (406 - 45) cbs = 0.607 ms / 361 = 1.681 us/cb
                -- the whole 0.607 ms/step attributed to command-buffer cost

this probe (CB count fixed at the shipped 45; only encoder dispatch type varied):
    de-overlap, measured               = 0.456 ms/step  [0.390, 0.522]
    census gap, CB count varied        = 0.607 ms/step
    de-overlap share of the census gap = 75 %           [64 %, 86 %]
    residual attributable to CB count  = 0.151 ms / 361 = 0.42 us/cb  [0.24, 0.60]
```

Normalised: 0.456 ms / 406 dispatches = **1.12 µs per dispatch of average
serialisation penalty** — a different quantity from the per-dispatch *launch*
floor, which is paid in both conditions.

Two caveats, and both widen the conclusion rather than narrowing it:
(a) `DispatchTypeSerial` in one encoder is not the same as one dispatch per
command buffer — SPLIT=1 additionally loses cross-encoder pipelining and pays
encoder creation, so **75 % is a lower bound** on the de-overlap share;
(b) the census gap is a `gpu_busy_sum` delta while this probe is a wall-clock
delta. Shipped wall − busy is only 0.254 ms (3.0 %), so the two are comparable
at this magnitude, but they are not the same estimator.

### 3.5 The corollary that matters beyond this ticket

The census corrects each kernel family by subtracting a **constant** per command
buffer. De-overlap is not constant per dispatch:

- a small hazard-free kernel that ran entirely in a larger sibling's shadow
  bears **~100 %** of its own isolated time as de-overlap;
- a large kernel on the barrier group's critical path bears **~0**.

A constant-per-CB correction therefore **systematically over-attributes marginal
cost to exactly the small, hazard-free kernels that look like the most
attractive optimisation targets.**

`gate_sp` is the canonical case. Its census attribution of 259.0 µs/step
(h64 191.7 µs / 30 dispatches + h48 67.3 µs / 10 dispatches), ~3.1 % of an
8.3 ms step, is an **upper bound on its marginal cost**. Arm A — 43 % off its
isolated serial execution time buying −0.04 % [−0.55 %, +0.48 %] end to end — is
what that bound being loose looks like in practice.

---

## 4. Isolated-dispatch microbenchmark, and the two brackets it produces

`research/frieren_pr101_gatesp_dispatch_bench.swift` encodes 400 cold weight
slots per command buffer (52.4 MB h64 / 39.3 MB h48, `storageModePrivate`),
median of 9 CBs after 3 warm-ups, GPU time from
`cb.gpuEndTime − cb.gpuStartTime`, with the same drift guard as the oracle. It
runs each geometry under a **serial** encoder and a **concurrent** encoder, plus
an empty-kernel arm that isolates the launch floor.

Selected rows (µs per dispatch; `exec` = measured − empty):

```
heads geom     ser_gate ser_empty  ser_exec   con_gate con_empty  con_exec   ser/con
   64 R4NS2       5.561     0.557     5.004      1.163     0.173     0.990      4.78x
   64 R1NS2       3.466     0.601     2.865      0.751     0.261     0.490      4.62x
   48 R4NS2       4.958     0.531     4.427      0.417     0.171     0.246     11.88x
   48 R1NS2       4.013     0.607     3.406      0.680     0.157     0.523      5.90x

stock serial gate_sp per step : 30 x 5.561 + 10 x 4.958 = 216.4 us
fixed launch floor per step   : 30 x 0.557 + 10 x 0.531 =  22.0 us (10 %)
h64 isolated exec range: 2.783..5.027 us (stock 5.004, spread 80.6 %)
h48 isolated exec range: 2.236..4.846 us (stock 4.427, spread 116.7 %)
```

The geometry effect in isolation is large and real: 80–117 % spread, and the
ranking broadly matches the a-priori occupancy argument. It simply does not
survive into the step.

**Two brackets fall out of my own harness, and I report both:**

| bracket | construction | value | verdict against measured |
|---|---|---|---|
| serial-encoder | `30×(5.561−3.466) + 10×(4.958−4.013)` | 72.3 µs = **−0.87 %** | **EXCLUDED** by the pooled interval |
| concurrent-encoder | `30×(1.163−0.751) + 10×(0.417−0.680)` | 9.73 µs = **−0.12 %** | **CONSISTENT** with −0.04 % [−0.55 %, +0.48 %] |

The shipped runtime uses a concurrent encoder. **The regime-appropriate arm of
my own microbenchmark predicts the null I measured.** The −0.87 % figure is not
a prediction that failed; it is an **upper bound derived under a
serial-critical-path model that the shipped encoder violates**, and I should
have labelled it that way from the start.

### 4.1 Scoping the launch-floor number properly

The empty-kernel arm gives **0.53–0.90 µs** per dispatch. That number is only
meaningful with its scope attached: *same-PSO dispatches inside an already-open
encoder on this M4 Pro*. Metal "dispatch overhead" is at least five distinct
costs:

1. **CPU encode cost** — does not appear in GPU timestamps at all.
2. **Command-buffer lifecycle** — commit, pickup, kickoff, flush, completion
   interrupt. Paid ~45×/step here, not 406×.
3. **GPU-side per-dispatch launch inside an open encoder** — what my
   empty-kernel arm isolates.
4. **PSO switch cost** — excluded by my same-PSO harness, so genuine in-situ
   per-dispatch overhead sits somewhat **above** my floor.
5. **Hazard-barrier drain under load** — not in the floor either.

A 5–7 µs "dispatch overhead" prior is legitimately reachable for
one-CB-per-kernel or `waitUntilCompleted` round trips, or imported from CUDA
lore. The correct statement is that such a prior **mis-attributes** — it
conflates CB/sync round-trip cost with encoder-internal dispatch cost, and on
this host those differ by about an order of magnitude. It is not that the prior
mis-measures, and I am not claiming it is refuted in general.

**One retraction I owe on my own working.** I had intended to cite the census's
1.681 µs/CB delta as independent corroboration of the 0.53–0.90 µs floor. That
is **circular**: 1.681 µs/CB is a per-*CB* figure derived under the assumption
of zero intra-CB overlap, which is the very assumption the probe in §3.2
falsifies. It should not be cited that way. The probe supplies a non-circular
replacement: residual command-buffer cost ≈ **0.42 µs/CB [0.24, 0.60]**. The
in-repo 1.42 µs and 1.33 µs figures need the same provenance check before
anyone cites them.

---

## 5. Pricing, and what does not transfer

Per the r1 comment on §0.9.36's second channel: both arms are
**occupancy/instruction** arms, so an M4 wall-clock residual for this class does
not transfer to M5 and may be over-stated by up to ~12×. Both arms are null on
M4, so there is nothing to over-state, but the direction of the caveat matters
for the *dispatch-concurrency* finding, which is the thing worth carrying
forward. I am therefore reporting +0.456 ms/step (+5.49 %) as an
**M4-only, directional** magnitude and making **no M5 extrapolation and no score
prediction from it**. This host reports Apple GPU generation 16 and does not
select the `_nax` prefill kernels, so nothing here is evidence about prefill.

Per §0.9.39, I have named the kernel and the source line for every count I quote
and have not converted the settled 5.5296 MB/step into a percent. Per §R20.2 I
have widened rather than narrowed every interval, including revising my own
noise-floor estimate upward from ±0.5 % to the 1.4 % my ABBA data actually shows.

---

## 6. Verdict and recommendation

| arm | price (M4 wall-clock, interval) | verdict |
|---|---|---|
| A — `gate_sp` R×NS occupancy | −0.04 %, 95 % CI [−0.55 %, +0.48 %] | **NO-GO** |
| B — o_proj lane-major hoist | null; no statistic clears the within-condition gap | **NO-GO** |

**Neither arm belongs in the next bundled ranked submission.** Both are
reverted. This branch adds **zero submitted bytes** and consumes none of the
44,537 B of per-file headroom on `LagunaRuntimeModel.swift`, which remains the
scarcest resource in the programme.

`mlxfast submit` was **not** run, per §R18.9.

The reframed headline, which is what I would actually like carried into the
research state: **own-CB and isolated-serial attributions are upper bounds that
can overstate a shadow-executed kernel's marginal cost by an order of magnitude,
and this workload's `gate_sp` is structurally shadow-executed.**

---

## 7. Suggested follow-ups (not implemented)

1. **Calibrated-injection slope test at the `gate_sp` site.** Encode a
   hazard-free spin kernel of known duration X ∈ {2, 5, 10, 20, 40} µs next to
   `gate_sp` and measure dStep/dX. A slope near zero up to a knee at roughly the
   QKV branch duration would both prove shadow execution and *measure its
   depth*. This converts §3 from "concurrency exists, 0.456 ms/step total" into
   a per-site budget.
2. **Barrier-group-grain in-situ census.** Split encoders at MLX's own hazard
   barrier boundaries so each barrier *group* gets GPU timestamps within a single
   command buffer. Re-run the #73 census at that grain, stock vs `R1NS2`. This is
   the measurement that would let the programme attribute marginal cost
   correctly instead of subtracting a constant per CB.
3. **Programme-level re-audit of every banked "µs/step saved" claim** against the
   isolated-vs-marginal gap now that it is quantified. The prior systematically
   favours small hazard-free kernels; several of them have been assigned as
   tickets.
4. **Stub/remove ablation on `gate_sp`** to size the prize directly (incorrect
   output, timing only) before anyone spends another ticket optimising it.
5. **Wave-sharing via issue-order placement**, and **sibling grid-concatenation
   fusion of `gate_sp` into the same-input QKV matvec** — both exploit the
   hazard-free relationship established in §3.1 rather than fighting it.
6. **PSO unification for h48/h64** to remove a switch class from the step.

**Named dead ends, so nobody re-runs them:** further R×NS geometry search on
`gate_sp` (nine points, 0.48 % band, exhausted); shaving `gate_sp` arithmetic;
cross-layer batching; ICB / encoder surgery; re-fusing `gate_sp` into its
producer (D-FUSE-GATESP rung 2 was built and re-measured at **+2.7 %** — defusion
is the promoted state, `LagunaRuntimeModel.swift:5749-5752` pre-revert
numbering; permanently closed).

---

## 8. Artefacts

| path | contents |
|---|---|
| `research/pr101-serial-dispatch-analysis.txt` | full 122-line dispatch-concurrency write-up |
| `research/pr101-serial-dispatch/` | 24 raw files, 8 runs × {`.txt`, `.steps.txt`, `.worker.err`} |
| `research/pr101-gatesp-abba-analysis.txt` | Arm A round-3 ABBA + pooled 12-run interval |
| `research/pr101-gatesp-dispatch-bench.txt` | isolated microbenchmark, 18 geometry × encoder rows |
| `research/pr101-gatesp-bitwise.txt` | bitwise oracle output with live control |
| `research/pr101-sweep/`, `research/pr101-sweep-r2/` | rounds 1 and 2 raw sweep data |
| `research/frieren_pr101_gatesp_bitwise.swift` | 386-line oracle, drift + degeneracy guards, float32 raw mode |
| `research/frieren_pr101_gatesp_dispatch_bench.swift` | isolated-dispatch microbenchmark |
| `research/frieren_pr101_serial_dispatch_abba.sh` | dispatch-type probe driver |
| `research/frieren_pr101_gatesp_abba.sh` | Arm A round-3 driver |
| `research/frieren_pr101_abba_analyze.py` | generalised two-condition ABBA analyzer |
| `research/frieren_pr101_analyze.py` | rounds 1+2 analyzer |

_This report was written by an AI research-student agent (OpenHands) operating in
the Senpai programme._
