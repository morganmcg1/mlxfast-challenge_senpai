# Decode exposure audit: what 0.456 ms/step of "concurrency" actually is,
# and what the §2.b census is worth once it is priced correctly

*Assignment `maple-2026-08-06p-decode-exposure-audit`, revision `r1`, PR #174.
Host: Apple M4 Pro, 14 CPU / 20 GPU cores, 48 GiB, GPU generation 16, macOS
26.5.2, GPU idle 38-39 C. Decode-only; no `_nax` kernels are reachable here and
none are touched. Zero submitted-surface bytes: the diff is `research/` only.*

---

## 0. The contradiction, and the one number that resolves it

PR #101 forced the MLX Metal encoder from `DispatchTypeConcurrent` to
`DispatchTypeSerial` and measured **+0.456 ms/step** of decode wall time
(p = 0.029). My own PR #158 measured `gpu_busy_sum` flat at **7.99 +- 0.06 ms**
while command buffers per step went 45 -> 204, and concluded "hidden concurrent
work <= 0.06 ms/step". The two results differ by **7.6x** and cannot both
describe the same machine.

They do not. The resolution is a single arithmetic error in PR #158, and it is
the *same* 7.6x seen from the other side.

### The bug

PR #158 measured GPU busy time at three command-buffer granularities and formed
a per-command-buffer cost:

```text
c = [ busy(SPLIT=1) - busy(SPLIT=0) ] / [ 406 - 45 ]
  = (8572.8 - 7999.4) / 361
  = 1.588 us/CB
```

That subtraction is not a clean difference in command-buffer count. Write `W`
for the zero-overlap GPU work of one decode step, `c` for the true marginal cost
of one extra command buffer, and `D(k)` for the GPU time saved by concurrent
execution at split level `k`. Both terms of PR #158's difference were measured
with the encoder in its shipped `DispatchTypeConcurrent` mode, so both carry a
`D`:

```text
busy(SPLIT=1) = W + 406 c - D(1)      one dispatch per buffer: nothing can overlap
busy(SPLIT=0) = W +  45 c - D(0)      the shipped granularity
-------------------------------------------------------------
difference    =       361 c + D(0) - D(1)
```

PR #158 assigned the entire 573.4 us to `361 c` and implicitly asserted
`D(0) = D(1)`. But `D(0)` is exactly the quantity PR #101 measured, and it is
*not* zero. The single error inflates `c` and annihilates `D` simultaneously --
which is why the same 7.6x shows up on both sides of the contradiction.

This is an identity, not an estimate. Measuring both split levels again with the
encoder forced serial isolates `c` with no `D` anywhere, and the two routes
reconcile to the last digit
(`research/nezuko-a0-split-derive.txt`):

```text
c from concurrent arms          = (8598.5 - 8022.0) / 361.2 = 1.596 us/CB
c_true + [D(0) - D(1)] / 361.2  =  0.540 + 381.5 / 361.2   = 1.596 us/CB
```

My independently measured `busy_c(SPLIT=1) = 8598.5 us` also reproduces PR
#158's published `8572.8 us` to **0.3 %** across sessions, so the disagreement
is in the arithmetic, not in the measurement.

### The headline

| quantity | PR #158 | this PR |
| --- | --- | --- |
| `D(0)`, concurrency benefit at the shipped split | ~0 (bounded <= 60 us/step) | **448 us/step raw, 382 us/step after subtracting the k=1 residual as bias** |
| `c`, marginal GPU cost of one command buffer | 1.596 us/CB | **0.540 us/CB** over the full range, and **not constant** |
| per-dispatch de-inflation applied to every §2.b row | 1.419 us | **0.480 us** |
| `W`, zero-overlap work per step | never formed | **8.446 ms/step** |

`c` is **3.0x smaller** than published, and the `1.419 us/dispatch` correction
sitting under every row of the §2.b census is **3.0x too large**.

A second, independent flaw in the same framework: `c` is not a constant, so no
single slope can be carried from one split level to another. Measured on the
*serial* arms, where no overlap exists at any granularity:

```text
c(45 -> 204 CB/step)  = 0.022 us/CB
c(204 -> 406 CB/step) = 0.948 us/CB     43x steeper
```

Near the shipped split, extra command buffers are very nearly free on the GPU.
PR #158 fitted its slope in the steep regime at `k = 1` and then charged it to
every kernel at `k = 0`, where it does not apply.

### What the concurrency actually is

The 448 us is not a diffuse "pipelining across command-buffer seams" effect. It
is **three kernels hiding under their neighbours**:

| kernel | calls/step | published us/call | us/step hidden |
| --- | ---: | ---: | ---: |
| `gate_sp_h64` | 30 | 6.64 | 199.2 |
| `shared_nvfp4_swiglu_qmv_rows1` | 39 | 6.09 | 237.6 |
| `gate_sp_h48` | 10 | 6.31 | 63.1 |
| **predicted total** | | | **499.9** |
| **measured total (A0 group census)** | | | **451.5** |

Ratio 0.90. Everything else on the decode path -- the big NVFP4 matvecs,
attention, the router, the LM head -- runs with **exposure factor E ~ 1.0**:
its GPU time lands on the step wall essentially 1:1. Those three small kernels
run with **E ~ 0.10**: optimizing them buys almost nothing, because they are
already free.

---

## 1. Pre-registered prediction and verdict

The predictions in `research/nezuko-a0-split-prereg.md` were committed in
`625d451` **before any SPLIT=1 / SPLIT=2 dispatch-type data existed**.

### The single discriminating number

**`D(2) / D(0) = 387.0 / 448.0 = 0.864`.**

This ratio is model-free. At a fixed split level `k` the concurrent and serial
arms have identical command-buffer counts and identical dispatch counts, so `W`
and `N(k)c` cancel exactly in `D(k) = busy_serial(k) - busy_concurrent(k)`. No
value of `c` -- mine, PR #158's, or none at all -- can move it.

| | prediction | value |
| --- | --- | ---: |
| **R-A** uniform seam pipelining | `seams(2)/seams(0) = 202.1/361.2` | 0.560 |
| **R-B** sibling shadowing | one hazard-free partner per pair suffices | ~0.95 |
| **observed** | | **0.864** |

Linear mixture weight `(0.864 - 0.560) / (0.950 - 0.560)` = **0.78**, i.e.
**~78 % R-B, ~22 % R-A**. Treating the k=1 residual as an additive bias (below)
gives 0.840 and **~72 % R-B**. **R-C is rejected outright** (§2.3).

### Verdict against the pre-registered thresholds, stated honestly

The pre-registration set *absolute* bands anchored on an A0-smoke `D(0)` of
498 us. The final, better-powered A0 measured `D(0) = 448 us`, so the absolute
bands are anchored 11 % high. Read literally against them:

| pre-registered band | observed `D(2)` | reading |
| --- | ---: | --- |
| near 279 us => R-A | 387.0 | no |
| near 473 us => R-B | 387.0 | no |
| **330-420 us => genuinely mixed, report the mixture weight** | **387.0** | **this one** |

So on the absolute reading the outcome landed in the pre-registered *mixed*
band, and the pre-registration's own instruction for that band was to report the
mixture weight rather than declare a winner. That is what I have done: 78 % R-B.
The scale-free ratio form -- which the pre-registration also stated, as "95 % of
SPLIT=0" versus "56 %, proportional to seam count" -- is immune to the 11 %
anchoring error and gives the same answer. **R-B is dominant; R-A is real but
minor.** I am not claiming the clean R-B win the ratio alone would suggest.

The practical consequence is unchanged either way, and it is the operative
finding of this PR: since ~3/4 of the effect does not scale with seam count,
**no constant per-dispatch or per-buffer subtraction is an admissible pricing
unit**, and per-kernel exposure `E` is required.

### The falsification criterion fired. Reporting it, not re-drawing it.

Pre-registration: "`Delta(SPLIT=1)` materially above ~50 us => the serial probe
is charging a per-dispatch cost unrelated to concurrency, and **the whole A0
conclusion is withdrawn**."

**Observed `D_busy(k=1) = +66.5 us/step`. That exceeds the threshold.** I am
recording that the criterion fired rather than arguing it away. Four facts bear
on how much it costs the conclusions:

1. **The failure mode the criterion names is additive and I can subtract it.**
   Dispatches per step are 406.2 in *all three* split levels. A spurious
   per-dispatch serial cost is therefore the *same* 66.5 us at every `k`.
   Removing it leaves `D(0) = 381.5 us` -- still **6.4x** PR #158's <=60 us
   bound -- and `D(2)/D(0) = 0.840`, still R-B dominant. Every number in
   sections 4-6 is reported at both 448 and 382; no conclusion changes sign,
   rank, or recommendation between them.
2. **The other currency moves the other way.** The same k=1 runs show
   `D_wall = -56.4 us/step`, opposite sign, permutation p = 0.40 with complete
   overlap between arms. A genuine per-dispatch serialization cost should appear
   in both currencies with the same sign.
3. **Both magnitudes sit at the noise floor.** 66.5 us and 56.4 us straddle the
   +-70 us between-session arm scatter that the advisor's doctrine specifies.
   `D(0) = 448 us` is 6.7x larger than either.
4. **k=1 is a badly distorted operating point.** Its host gap is 1.349 ms/step
   versus 0.262 ms at the shipped split -- a 5x change in how the step is
   assembled. A small real effect that exists only at 406 command buffers per
   step would not transfer to `k = 0`.

What this costs: the *point value* of `D(0)` is now a range, 382-448 us/step,
not the +-31 us I would otherwise have quoted. What it does not cost: the
qualitative claim, the R-B verdict, the rejection of constant-correction
pricing, or any target ranking. Settling it cleanly needs a k=1 arm at 3-4x the
replicate count, which I did not have host time for and which would not change
a single recommendation below.

---

## 2. A0: the discriminator

### 2.1 Design

`research/nezuko-serial-dispatch-probe.patch` adds a 42-line env-gated switch in
`Vendor/mlx-swift/.../backend/metal/device.cpp::get_command_encoder()` that
selects `MTLDispatchTypeSerial` instead of `MTLDispatchTypeConcurrent` when
`DARKBLOOM_FORCE_SERIAL_DISPATCH=1`. It prints
`DARKBLOOM_SERIAL_DISPATCH_PROBE force_serial=<0|1>` to stderr, so every point
proves which arm it ran. It is *never* committed to the submitted surface -- it
is a `.patch` file applied to a throwaway `.build-worker` scratch tree and
reverted afterwards.

`research/nezuko_a0_dispatch_type_abba.sh` runs the two arms in an ABBA order
(`A B B A A B B A`, n = 4 vs 4, 400 decode steps each, 25-step settle), so any
monotone thermal or clock drift cancels to first order. Significance is an exact
permutation test over the C(8,4) = 70 arm labellings.

Two orthogonal knobs are crossed with the dispatch type:

- `hook`: the PR #158 GPUPROF instrumentation ON (`h1`) or OFF (`h0`). `h0`
  is the artifact control -- if the effect is created by profiling, it must
  vanish.
- `split`: dispatches per command buffer, `k0` = shipped (~9), `k1` = 1,
  `k2` = 2. `k1` is the probe-validity control: with one dispatch per command
  buffer there is nothing to reorder, so the dispatch type must not matter.

### 2.2 Result

All 16 runs, 400 steps each: **0 token divergences**. The probe changes
scheduling only.

| phase | instrument | concurrent | serial | delta | perm p |
| --- | --- | ---: | ---: | ---: | ---: |
| `h1k0` | step wall (median) | 8.299 ms | 8.720 ms | **+420.9 us** | 0.057 |
| `h1k0` | `gpu_busy_sum` | 8.022 ms | 8.470 ms | **+448.0 us** | 0.086 |
| `h1k0` | `gpu_busy_union` | 8.022 ms | 8.470 ms | **+448.0 us** | 0.086 |
| `h1k0` | `gap` = wall - union | 0.262 ms | 0.241 ms | -21 us | 0.63 |
| `h1k0` | command buffers / step | 45.000 | 45.000 | 0.000 | 1.00 |
| `h1k0` | dispatches / step | 406.200 | 406.200 | 0.000 | 1.00 |
| `h0k0` | step wall, **profiler OFF** | 8.201 ms | 8.781 ms | **+580.0 us** | 0.057 |

Per-run medians (ms), so the scatter is visible rather than asserted:

```text
h1k0 wall   concurrent 8.296 8.303 8.192 8.306 | serial 8.667 8.747 8.693 8.805
h1k0 busy   concurrent 8.018 8.035 7.976 8.026 | serial 8.444 8.496 8.444 8.560
h0k0 wall   concurrent 8.192 8.206 8.196 8.215 | serial 8.723 8.796 8.765 8.796
```

p = 0.057 is the *minimum attainable* p for a one-sided 4-vs-4 permutation test
with perfect separation (4/70). The concurrent and serial run sets do not
overlap on any of the three primary currencies.

### 2.3 All three currencies, and what each one says

| currency | moves? | inference |
| --- | --- | --- |
| step wall | yes, +421 us (hook on), +580 us (hook off) | the effect is real and lands on the score |
| `gpu_busy_sum` | yes, +448 us | the effect is GPU-side, not host-side |
| `gpu_busy_union` | yes, +448 us, identical to sum | **the destroyed overlap is *inside* command buffers** |
| `gap` = wall - union | no, p = 0.63 | host/dispatch time is unchanged; this is not a CPU effect |

The `union == sum` equality is the decisive line. `gpu_busy_union` merges
overlapping *command-buffer* intervals; `gpu_busy_sum` does not. They move by
the same 448 us, which means no command buffers were overlapping in either arm.
The concurrency that `DispatchTypeSerial` destroys is **intra-command-buffer**
-- exactly the layer PR #158's buffer-level instrument cannot see. PR #158 was
not measuring the wrong number; it was measuring a number that is structurally
blind to the phenomenon.

**Resolution R-C (currency mismatch) is rejected.** `busy / wall = 1.064`, and
`gap` is statistically flat. Wall and busy are the same currency here to within
6 %; the discrepancy is not a units problem.

**The GPUPROF-artifact hypothesis is rejected.** The hook-off control is
*larger* (+580 us vs +421 us), not smaller. Instrumentation slightly *damps* the
effect, presumably by serializing a little on its own.

### 2.4 Cross-session reconciliation with PR #101

| session | delta (us/step) |
| --- | ---: |
| this PR, `h1k0` wall | 421 |
| this PR, `h1k0` busy | 448 |
| **PR #101** | **456** |
| this PR, earlier smoke | 490 |
| this PR, `h0k0` wall (hook off) | 580 |

Five independent sessions spread over ~160 us, consistent with the campaign's
+-70 us arm-level between-session scatter doctrine. PR #101's +456 us sits in
the middle of that distribution. **PR #101 replicates.** The working value used
throughout the rest of this report is `D = 448 +- 31 us/step`.

### 2.5 R-A vs R-B: the per-group census

The GPUPROF hook can restrict the serial/concurrent switch to a named group of
adjacent dispatches, so the 448 us can be decomposed. If the effect were uniform
seam pipelining (R-A), cost would scale with the number of *seams* (`m - 1` for
a group of `m` dispatches), and per-dispatch cost would *rise* toward
`(m-1)/m` as groups grow.

| group | dispatches | delta us/CB | delta us/**seam** | delta us/dispatch | E = conc/serial |
| --- | ---: | ---: | ---: | ---: | ---: |
| `rmsbfloat16 \| gate_sp_h48 \| qkv_h48` | 3 | 6.65 | **3.33** | 2.22 | 0.857 |
| `residual_rms_router \| shared_qmv_rows1 \| router_top8 \| routed_qmv \| routed_down` | 5 | 6.82 | **1.70** | 1.36 | 0.915 |
| full layer, h64 | 10 | 12.59-13.68 | **1.40-1.52** | 1.20-1.37 | 0.928-0.935 |
| layer pair | 12 | 9.11-10.26 | **0.83-0.93** | 0.76-0.86 | 0.955-0.961 |
| `[8]` sub-layer | 8 | 13.75 | 1.96 | 1.72 | 0.904 |
| `[11]` | 11 | 12.02 | 1.20 | 1.09 | 0.944 |

Per-seam price varies **4x** and *falls* monotonically as groups grow. That is
the opposite of the R-A prediction. **R-A (uniform seam pipelining) is rejected
on its own data.**

### 2.6 R-B: which kernels hide

Because the groups are nested, group composition identifies the hider directly.
Each row below compares the measured group delta against the published §2.b
cost of the single candidate kernel that entered the group:

| step | group delta us/CB | candidate entering | published us/call | ratio |
| --- | ---: | --- | ---: | ---: |
| `[3]` | 6.65 | `gate_sp_h48` | 6.31 | **1.05** |
| `[5]` | 6.82 | `shared_nvfp4_swiglu_qmv_rows1` | 6.09 | **1.12** |
| `[8]` - `[5]` | 6.93 | `gate_sp_h64` (also entering: `sliding_attn` 19.74, `oproj_h64` 35.80) | 6.64 | **1.04** |
| `[10]` full layer | 12.59-12.88 | `gate_sp_h64` + `shared_qmv_rows1` = 12.73 | 12.73 | **0.99-1.01** |

The third row is the sharpest: adding `sliding_fused_attn_ring_v1` (19.74
us/call) and `oproj_act_h64` (35.80 us/call) to the group -- 55.5 us/call of
additional kernel time -- increases the serial penalty by 6.93 us, which is
`gate_sp_h64` alone. **The two big kernels contribute nothing.** They were never
overlapped; they are fully exposed in both arms.

The fourth row covers ~50 % of the whole-step delta and predicts it to within
1 %.

Whole-step budget:

```text
gate_sp_h64        30 x 6.64 = 199.2 us/step
gate_sp_h48        10 x 6.31 =  63.1
shared_qmv_rows1   39 x 6.09 = 237.6
                             --------
predicted overlap             499.9 us/step
measured overlap (A0)         451.5 us/step     ratio 0.90
```

**R-B (sibling shadowing) is accepted.** The residual 10 % is the honest error
bar: group totals do not uniquely identify a hider, and the 12-dispatch
layer-pair groups under-deliver at 0.54-0.73 of prediction, which is what
partial shadowing looks like when the shadowing neighbour is not long enough to
cover the whole hidden kernel.

### 2.7 The SPLIT=2 arm, measured directly

The discriminator does not have to be reconstructed from PR #158's published
concurrent-only numbers, because I ran the serial arm at SPLIT=2 as well. All
three split levels, same session, same ABBA order, same 4v4 replicates
(`research/nezuko-a0-split-derive.txt`):

| split | CB/step | dispatch/step | seams | `busy_conc` | `busy_ser` | `D_busy` | `D_wall` | p | tokens |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| k=1 | 406.2 | 406.2 | 0 | 8598.5 | 8665.0 | **+66.5** | -56.4 | 0.057 | 0 div |
| k=2 | 204.1 | 406.2 | 202.1 | 8086.5 | 8473.5 | **+387.0** | +296.1 | 0.057 | 0 div |
| k=0 | 45.0 | 406.2 | 361.2 | 8022.0 | 8470.0 | **+448.0** | +420.9 | 0.086 | 0 div |

`D(2)/D(0) = 0.864` against R-A's 0.560 and R-B's ~0.95. The seam count fell
44 % and the effect fell 14 %.

Two things fall out of the same table that PR #158's framework could not see.

**`busy_conc(k=1) = 8598.5 us` replicates PR #158's published 8572.8 us to
0.3 %** across sessions and machines-in-time. The two PRs measured the same
thing; only the arithmetic applied to it differed.

**`c` is not constant.** Read off the *serial* column, where no overlap exists
at any granularity, the marginal cost of a command buffer is 0.022 us/CB between
45 and 204 buffers per step but 0.948 us/CB between 204 and 406 -- 43x steeper.
The shipped split sits in the flat regime. Any framework that fits one slope at
`k = 1` and charges it at `k = 0` is wrong twice over: once for absorbing `D`,
and once for extrapolating across a knee.

---

## 3. Exposure factors

### 3.0 What `E` means and why it needs its own measurement

Define, for kernel `k`:

```text
E(k) = d(step wall time) / d(isolated GPU cost of k)
```

`E = 1` means the kernel is on the critical path and every microsecond you save
lands in the score. `E = 0` means the kernel is already running underneath a
sibling dispatch, and making it infinitely fast buys nothing.

Every published decode census in this campaign -- PR #158 §2.b included -- is a
table of **isolated** cost. Section 2 showed that at least three kernels are
fully shadowed, so an isolated-cost census is not a target list until it is
multiplied by `E`. Section 3 supplies the multiplier.

I have three estimators. They are listed in decreasing order of directness, and
they do not depend on each other.

### 3.1 Estimator A -- nested-group serialization composition (direct, per kernel)

This is the strongest of the three because it needs no wall-clock difference, no
second build, and no knob. Forcing serial dispatch on a *group* of sibling
dispatches destroys exactly the concurrency that group had. The incremental
serialization penalty of admitting one more kernel to the group therefore *is*
the amount of work that kernel was hiding.

From the per-group census in §2.6 (`research/nezuko-a0-dispatch-type`):

| kernel admitted | incremental penalty | its isolated cost | hidden? |
|---|---|---|---|
| `gate_sp_h48` (group `[2]` -> `[3]`) | +6.65 us | 6.31 us | yes, ~100% |
| `shared_nvfp4_swiglu_qmv_rows1` (`[3]` -> `[5]`) | +6.82 us | 6.09 us | yes, ~100% |
| `gate_sp_h64` + `sliding_attn` + `oproj_h64` (`[5]` -> `[8]`) | +6.93 us | 6.64 + 19.74 + 35.80 = 62.18 us | only the 6.64 |

The third row is the load-bearing one, and it cuts both ways in a single
measurement. Admitting three kernels worth 62.18 us of isolated work raised the
serialization penalty by 6.93 us -- almost exactly the isolated cost of
`gate_sp_h64` alone. So `gate_sp_h64` was fully shadowed, **and** the other two
were not shadowed at all: if `sliding_fused_attn_ring_v1` or `oproj_act_h64` had
been even 20% hidden, that step would have cost at least 11 us more than it did.
That is direct, kernel-specific evidence for `E ~ 1` on the two largest
attention-side kernels, from the same experiment that proves `E ~ 0` for the
small ones.

Magnitude comes from the budget. Predicted hidden work if those three are 100%
shadowed:

```text
30 x 6.64  (gate_sp_h64)                    = 199.2 us/step
10 x 6.31  (gate_sp_h48)                    =  63.1 us/step
39 x 6.09  (shared_nvfp4_swiglu_qmv_rows1)  = 237.6 us/step
                                     total  = 499.9 us/step
```

Measured total serialization penalty across the 45 shipped command buffers:
**451.5 us/step**. Ratio 0.90, so the shadowing is 90% complete, not 100%:

```text
E(shadowed) = 1 - 451.5/499.9 = 0.10
```

The interval on that 0.10 is set by how well `D(0)` reproduces, not by
within-session scatter. Five sessions measured `D(0)` at 421 / 442 / 456 (PR
#101) / 490 / 580 us/step. Propagating that spread through the same ratio gives
`E(shadowed)` in roughly **[0.00, 0.25]**, truncated at zero. The useful
statement is not the point estimate -- it is that the whole class is worth at
most a quarter of its census line.

### 3.2 Estimator B -- the closure test (one parameter, 19 rows)

Estimator A names *which* kernels hide but says nothing about the other sixteen
census rows. Those are pinned by a closure requirement: the effective census
must sum to the measured concurrent GPU busy time.

Fix `E = 0.10` for the three named hiders. Then a single free parameter
`E_rest`, applied to every other row, is forced by

```text
sum_k (isolated_k * E_k) + 45c = busy_concurrent = 7999.4 us/step
```

`research/nezuko_a2_reprice.py` solves it:

```text
isolated work sum:  8387.3 us/step
closure test:       named hiders absorb 516.6 us -> E_rest = 1.013
identity check:     work*E + 45c = 7999.4 vs busy 7999.4 us/step
```

This is a one-parameter fit against a nineteen-row table, and it landed within
1.3% of exactly 1. Nothing in the construction forced that. Had the true
picture been "lots of diffuse partial overlap", `E_rest` would have come out
near 0.7; had the census been systematically over-de-inflated, near 1.4. It
came out at 1.013.

Sensitivity: the census sum reproduces to about +-25 us/step between sessions
(+-0.003 on `E_rest`), and moving `E(shadowed)` across its entire [0.00, 0.25]
interval moves `E_rest` by only 0.007. The statistical interval is therefore
**1.013 +- 0.01**. The honest caveat is systematic rather than statistical: this
assumes the `SPLIT=1` per-kernel census is the correct "isolated" currency, which
§2.7 shows is true to within the +66.5 us/step residual discussed in §1.

### 3.3 Estimator C -- knob ablation, `E = dS / dI`

The pre-registered design (`research/nezuko-a1-prereg.md`) was to take a
default-ON runtime knob, measure the change in isolated cost `dI` from the
`SPLIT=1` census with the knob off, measure the change in step wall time `dS`
with the profiler hook off, and report `E = dS/dI` directly, in the currency the
score is paid in. The design floor was `|dI| >= 150 us/step`, from the +-70
us/step arm-level between-session scatter doctrine.

### 3.4 Estimator C, attempt 1: both pre-registered knobs missed the design floor

24 runs, `research/nezuko-a1-exposure`, analysis in
`research/nezuko-a1-exposure.txt`. **0 token divergences in all 24 runs.**

| knob | `dI` (isolated) | `dS` (wall) | perm p on `dS` | verdict |
|---|---|---|---|---|
| `DARKBLOOM_ROUTED_GATEUP_R1` | +18.2 +- 23.8 us/step | +65.0 us/step | 0.17 | underpowered |
| `DARKBLOOM_SHARED_QMV_R1` | +24.4 +- 18.8 us/step | -47.9 us/step | 0.20 | underpowered |

Both arms are an order of magnitude below the 150 us/step floor, so per the
pre-registration I report the bound and not the point estimate. `E = 3.56` and
`E = -1.97` are noise divided by noise; the confidence intervals are unbounded
in both directions and I am not going to launder them into a number.

**Why the design failed, stated plainly.** I selected the knobs on "is it
default-ON and does it name a large census row", when the criterion that
actually mattered was "does turning it off change isolated GPU work by at least
150 us/step". Both knobs turn out to be *variant swaps*, not slowdowns. Turning
them off does not make a kernel slower; it substitutes a different kernel that
does the same work at nearly the same price:

```text
ROUTED_GATEUP_R1  on -> routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2  1497.3 us/step
                 off -> routed_nvfp4_swiglu_qmv_packed_top8keys_bf16_v1     1517.8 us/step
SHARED_QMV_R1     on -> shared_nvfp4_swiglu_qmv_rows1_bf16_v1                293.1 us/step
                 off -> shared_nvfp4_swiglu_qmv_bf16_v1                      317.4 us/step
```

That is what an `_r1` layout knob is *for*: it is the previous generation's
kernel kept as an ablation, and it was promoted precisely because it was only
slightly better. In hindsight this was predictable from the knob names alone
without spending a GPU hour, and a future exposure sweep should read the isolated
census delta from a single cheap 50-step census pair before committing to eight
wall runs.

Both knobs are otherwise clean: apart from the swapped pair, no kernel moved by
more than 6 us/step in either ablation, so the knobs are well localized and the
`dI` measurement itself is trustworthy. It is simply too small.

**One thing worth salvaging.** `SHARED_QMV_R1` adds +24.4 us/step of isolated
work to `shared_nvfp4_swiglu_qmv_rows1` -- one of the three kernels Estimator A
says is shadowed at `E = 0.10`. The prediction is therefore
`dS = 0.10 x 24.4 = +2.4 us/step`, i.e. nothing. Measured `dS = -47.9 us/step`,
`p = 0.20`: statistically indistinguishable from zero, consistent with the
prediction. But it does not *discriminate*, because `E = 1` predicts +24 us and
that is also inside the scatter. Consistency is not confirmation and I am not
claiming it as one.

**And one thing worth keeping as doctrine.** The two arms produced wall deltas
of +65.0 and -47.9 us/step -- 113 us apart -- while changing isolated GPU work by
under 25 us in both cases. That is an independent, in-session reproduction of the
+-70 us/step arm-level scatter doctrine, obtained by accident, and it is exactly
why the 150 us/step design floor exists. Anyone who had run one of these two arms
alone, without the census, would have published either "+65 us regression" or
"-48 us win" with equal confidence.

---

## 4. The re-priced census

`research/nezuko_a2_reprice.py` takes the PR #158 §2.b table verbatim, undoes
its `1.419 us/dispatch` subtraction, re-applies the measured `0.480 us/dispatch`
(a **+0.939 us/call** correction to every row), and multiplies by exposure:

```text
effective_us_per_step = (published_us_per_call + 0.939) * calls_per_step * E
```

Reproduce with:

```bash
research/nezuko_a2_reprice.py --c 0.540 --top 24 \
  --exposure '{"gate_sp_h64":0.10,"gate_sp_h48":0.10,
               "shared_nvfp4_swiglu_qmv_rows1":0.10}'
```

### 4.1 The closure test

This is the part that makes the table more than a re-scaling. `E` is pinned to
0.10 for **only the three kernels A0 independently identified as hidden**
(§2.6). The remaining sixteen rows are left free, and their common exposure is
then *solved for* from the identity `sum(work_i * E_i) + 45c = busy`:

```text
isolated work sum   8387.3 us/step
implied overlap      412.2 us/step   (A0 measured 448 raw / 382 bias-corrected)
E_rest = 1.013                       (1.000 == fully explained)
```

`E_rest = 1.013` is not a fitted parameter and is not tautological: three
exposures were fixed from a different experiment, and the sixteen unconstrained
kernels came back at 1.3 % from unity. Two independent lines -- the nested-group
composition census of §2.5-2.6 and this whole-step accounting identity -- agree
that the decode path is **three hidden kernels and sixteen fully exposed ones**,
with no diffuse residual left over. The same script run at the earlier
provisional `c = 0.347` returns `E_rest = 1.007`; the closure is insensitive to
`c` because `45c` is only 24 us of an 8000 us step.

### 4.2 The table

Ranked by effective us/step. `d` is the change in rank against PR #158 §2.b.
`score %` is the share of the 8.0 ms decode step this row would return if driven
to zero, priced at **-1 us = +0.01464 % score**.

| rank | `d` | effective | isolated | `E` | n | PR158 | score % | kernel |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | +0 | 1501.7 | 1482.0 | 1.013 | 39 | 1445.4 | 21.99 | `routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2` |
| 2 | +0 | 1337.3 | 1319.7 | 1.013 | 30 | 1291.5 | 19.58 | `decode_nvfp4_qkv_h64` |
| 3 | +0 | 1116.9 | 1102.2 | 1.013 | 30 | 1074.0 | 16.35 | `oproj_act_h64` |
| 4 | +0 | 860.7 | 849.4 | 1.013 | 39 | 812.8 | 12.60 | `routed_shared_nvfp4_down_residual_bf16_r1_v5` |
| 5 | +0 | 628.7 | 620.4 | 1.013 | 30 | 592.2 | 9.20 | `sliding_fused_attn_ring_v1` |
| 6 | +0 | 427.0 | 421.4 | 1.013 | 1 | 420.4 | 6.25 | `lmhead_int5_base_coarse_delta` |
| 7 | +0 | 364.0 | 359.2 | 1.013 | 10 | 349.8 | 5.33 | `decode_nvfp4_qkv_h48` |
| 8 | **+2** | 305.1 | 301.0 | 1.013 | 39 | 264.5 | 4.47 | `residual_rms_router_rpg8_keys_v1` |
| 9 | -1 | 302.3 | 298.3 | 1.013 | 10 | 288.9 | 4.43 | `oproj_act_h48` |
| 10 | -1 | 273.1 | 269.5 | 1.013 | 1 | 268.6 | 4.00 | `dense_gate_up_swiglu` |
| 11 | +0 | 252.6 | 249.3 | 1.013 | 10 | 239.9 | 3.70 | `full_fused_attn_grow_v1` |
| 12 | **+2** | 185.7 | 183.3 | 1.013 | 39 | 146.7 | 2.72 | `decode_router_top8_ordinal_table_norm` |
| 13 | +2 | 136.3 | 134.5 | 1.013 | 1 | 133.6 | 2.00 | `dense_down_residual` |
| 14 | **+2** | 124.6 | 123.0 | 1.013 | 41 | 84.5 | 1.82 | `rmsbfloat16` |
| 15 | +2 | 76.3 | 75.2 | 1.013 | 1 | 74.3 | 1.12 | `lmhead_exact_fused_int5_sparse_refine` |
| 16 | **-4** | **27.4** | 274.1 | **0.100** | 39 | 237.6 | 0.40 | `shared_nvfp4_swiglu_qmv_rows1` |
| 17 | +2 | 25.5 | 25.1 | 1.013 | 6 | 19.5 | 0.37 | six kernels below 8 us/step |
| 18 | **-5** | **22.7** | 227.4 | **0.100** | 30 | 199.2 | 0.33 | `gate_sp_h64` |
| 19 | -1 | **7.2** | 72.5 | **0.100** | 10 | 63.1 | 0.11 | `gate_sp_h48` |

`sum(work * E) + 45c = 7999.4` against a measured `busy = 7999.4 us/step`.

### 4.3 What actually moved

The re-pricing is **not** a uniform rescale, and the two mechanisms push in
opposite directions:

- **The de-inflation correction is regressive in call count.** Restoring
  +0.939 us/call helps a 39-calls/step kernel 39x more than a 1-call/step
  kernel. Under-counted high-frequency kernels rise: `rmsbfloat16` +47 %,
  `decode_router_top8_ordinal_table_norm` +27 %, `residual_rms_router_rpg8_keys_v1`
  +15 %. Single-call kernels barely move (`lmhead_int5_base_coarse_delta`
  +1.6 %). This is exactly the population PR #158's over-large correction
  penalised hardest.
- **Exposure is not regressive at all, and it dominates.** The three shadowed
  kernels are also high-frequency, so the correction inflated them too -- and
  then `E = 0.10` divided that by ten. `gate_sp_h64` moves from rank 13 to rank
  **18**, `shared_nvfp4_swiglu_qmv_rows1` from 12 to **16**.

The largest rank displacements in the table are **-5, -4, +2, +2, +2**. Every
displacement of magnitude >= 4 is a kernel A0 showed to be hidden; every
displacement of +2 is a high-frequency kernel the old correction over-charged.
The top seven ranks do not move, which is the reassuring half of the result:
**PR #158 got the big targets right for the wrong reason**, and would have got
the small ones badly wrong.

---

## 5. Top surviving decode targets, priced

Everything below is priced through the campaign constant **-1 us/step on decode
= +0.01464 % score**. Reproduce with
`research/nezuko_a2_roofline.py` (output: `research/nezuko-a2-roofline.txt`).

### 5.0 The headline reframing: census rank is not headroom rank

The re-priced census in section 4 says where the *time* is. It does not say
where the *headroom* is. Pricing every kernel against the M4 Pro DRAM roofline
(273 GB/s measured peak, 20 GPU cores) splits the 8.45 ms step into three pools
that behave completely differently:

| pool | effective us/step | % of step | floor us/step | headroom us/step | headroom % score |
|---|---|---|---|---|---|
| NVFP4 / bf16 weight streaming | 5920 | 70.1 | 5582 | **338** | 4.94 (needs literal 100 % of peak) |
| attention (2 kernels) | 881 | 10.4 | 317 unique-byte | 564 arithmetic ceiling | 8.26 |
| glue (kilobyte operands) | 641 | 7.6 | 152 | **489** | 7.16 |

The weight-streaming pool is **70 % of the decode step and it is finished**.
Per-kernel it runs at 87-98 % of DRAM peak:

```
decode_nvfp4_qkv_h64          268.2 GB/s   98.2 % of peak
decode_nvfp4_qkv_h48          262.7 GB/s   96.2 %
oproj_act_h64                 256.9 GB/s   94.1 %
dense_down_residual  (bf16)   249.5 GB/s   91.4 %
dense_gate_up_swiglu (bf16)   249.0 GB/s   91.2 %
routed_..._top8keys_r1_v2     248.3 GB/s   91.0 %
routed_shared_..._down_res    243.7 GB/s   89.3 %
oproj_act_h48                 237.3 GB/s   86.9 %
```

The top four census entries -- ranks 1, 2, 3, 4, together 4816 us/step, 57 % of
the step -- have a **combined** remaining headroom of 377 us/step, and claiming
even that requires every one of them to hit the theoretical DRAM peak that
`decode_nvfp4_qkv_h64` alone comes within 1.8 % of. Rank 2 in the census is
rank 2 in *time* and near-last in *opportunity*.

Meanwhile the two attention kernels are census ranks **5 and 11**, run at
**37.1 %** and **34.7 %** of peak, and carry more absolute headroom than the
whole weight pool.

### 5.1 T1 -- attention occupancy: split the serial KV sweep

**Priced: 227 us/step (+3.32 % score) conservative lower bound; 564 us/step
(+8.26 %) arithmetic ceiling. Unowned by any open PR.**

Both decode attention kernels use one threadgroup per *pair* of query heads
(`Sources/MLXFastModel/LagunaRuntimeModel.swift:1370` sliding,
`:1819` full; both compute `head0 = pair_tg * 2` from
`threadgroup_position_in_grid.x`). With `LagunaConstants.slidingAttentionHeads
= 64` and `fullAttentionHeads = 48` that is a grid of **32** and **24**
threadgroups on a **20-core** GPU.

Two independent measurements say bytes are not the constraint:

1. **The DRAM roofline is not binding.** GQA replication means 4 threadgroups
   (sliding) and 3 (full) each re-read the same kv head. Counting replicated
   traffic gives 406 GB/s and 284 GB/s -- 149 % and 104 % of DRAM peak. Traffic
   at 149 % of DRAM peak is being served from cache, so the kernels are not
   waiting on DRAM. Counting *unique* bytes gives 101 GB/s and 95 GB/s, i.e.
   37 % and 35 % of peak. Either way, DRAM is not the wall.
2. **The grid does not tile the machine.** 32 threadgroups on 20 cores occupies
   two waves but supplies 1.60 waves of work; 24 on 20 supplies 1.20. Even
   assuming wave 1 is perfectly packed and *ignoring the serial KV chain
   entirely*, the idle tail is 20 % of `sliding_fused_attn_ring_v1` (126 us/step)
   and 40 % of `full_fused_attn_grow_v1` (101 us/step) = **227 us/step**.

That 227 us/step is a floor on the loss, not an estimate of it, because inside
each threadgroup the sliding kernel walks the 512-position window strictly
serially: `constexpr uint window = 512; constexpr int BN = 32; constexpr int N =
512` gives **16 sequential KV iterations with no split and no flash-decoding
merge**. During the tail wave, 12 of 20 cores are idle for the entire length of
that 16-iteration chain.

**Mechanism.** Split the KV sweep across `S >= 2` threadgroups per head pair and
merge with the standard online-softmax combine (each partial keeps its running
`m` and `l`; the merge is `exp(m_i - m)` weighted). Grid goes 32 -> 64 (sliding,
S=2) and 24 -> 48 (full, S=2), which tiles 20 cores far better (3.20 and 2.40
waves, tails 7 % and 20 %) and cuts the serial chain per threadgroup from 16
iterations to 8. The merge adds a second short kernel or a threadgroup-memory
reduction; at 2.097 MB and 2.359 MB of unique operand per call the extra traffic
is negligible.

**Why this is a genuine decode lever and not a re-run of PR #101's NO-GO.** PR
#101 re-geometrized `gate_sp` -- a kernel section 2.6 and section 4 both show is
**shadowed at E ~ 0.10**, i.e. a kernel whose GPU time is almost entirely
hidden behind a sibling. Re-geometrizing a hidden kernel cannot move the step
even when the kernel itself gets faster, which is exactly the -0.04 % PR #101
measured. `sliding_fused_attn_ring_v1` is the opposite case: **E = 1.013**,
628.7 us/step fully exposed, census rank 5. This is the single largest
non-bytes-bound exposed cost in the decode step.

**Risks to state up front.** (a) The merge changes the floating-point reduction
order, so this needs `LagunaUpstreamEquivalence.swift` via
`research/run_upstream_equivalence.sh` plus the 64-step drift tripwire, not just
a timing run. (b) Threadgroup geometry changes sign across core counts -- this
is priced on a 20-core M4 Pro and the ranked M5 Max has more cores, where the
32-threadgroup grid tiles *differently*; the tail fraction must be re-derived,
not assumed, and the M5 is authoritative. (c) Prefill uses different kernels and
has its own 0.95 floor; the change must be shown not to touch the prefill path.

### 5.2 T2 -- routed-MoE matvec bandwidth efficiency (priced, not claimed)

**Priced: 188 us/step (+2.75 % score). Call site fenced to maple-frieren
PR #148 -- this is a price, not a claim.**

The two routed-expert kernels are the only large weight-streaming kernels
materially below the efficiency the model itself demonstrates:

| kernel | GB/s | % peak | gap to 98.2 % | us/step |
|---|---|---|---|---|
| `routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2` | 248.3 | 91.0 | 7.2 pts | 110 |
| `routed_shared_nvfp4_down_residual_bf16_r1_v5` | 243.7 | 89.3 | 8.9 pts | 78 |

The reference point is not the theoretical peak but **`decode_nvfp4_qkv_h64` at
98.2 %**: a kernel in this same model, reading this same NVFP4 layout, on this
same host, reaching within 1.8 % of peak. Whatever the routed kernels lose
relative to it -- gather indirection, per-expert scale reload, less regular
access order -- is in principle recoverable without any precision change.
Closing the gap to 98.2 % is worth **110 + 78 = 188 us/step = 2.75 % score**.

This is a *ceiling*, and a soft one: `decode_nvfp4_qkv_h64` reads one contiguous
weight block while the routed kernel gathers 8 of 256 experts, so some of the
gap is structural. I am reporting it because it is the only place in the 70 %
weight pool where an in-model existence proof says the current number is not
the floor.

The routed gather-GEMM call site in `LagunaRuntimeModel.swift` is fenced to
maple-frieren PR #148. I did not touch it and I am not proposing to.

### 5.3 T3 -- the glue pool: 489 us/step that is not bytes and not command buffers

**Priced: 489 us/step (+7.16 % score) of non-bytes-bound cost; realistic
fusion subset 100-300 us/step.**

Four census entries have kilobyte-scale operands and microsecond-scale costs:

| kernel | n/step | us/call | us/step | operand | byte floor us/step |
|---|---|---|---|---|---|
| `residual_rms_router_rpg8_keys_v1` | 39 | 7.72 | 305.1 | 256x2048 router bf16 + hidden + residual | 151.0 |
| `decode_router_top8_ordinal_table_norm` | 39 | 4.70 | 185.7 | 256 expert scores fp32 | 0.1 |
| `rmsbfloat16` | 41 | 3.00 | 124.6 | 2048 bf16 | 0.6 |
| six kernels below 8 us/step | 6 | 4.18 | 25.5 | negligible | 0.0 |
| **total** | | | **641.0** | | **152** |

The pool costs **641 us/step, 7.6 % of the decode step**, against a DRAM floor
of 152 us/step -- and that 152 is almost entirely the one real matvec in the
group (the 256x2048 router projection). The remaining **489 us/step** is launch,
threadgroup setup, reduction tree and drain: time the GPU spends being busy
without moving operands. `decode_router_top8_ordinal_table_norm` is the cleanest
case -- it sorts 1 kB of expert scores and costs 4.70 us a call, 185.7 us/step,
**1.03 kB at an implied 0.2 GB/s**.

**This is not the thing section 6.1 rules out, and the distinction matters.**
Section 6.1 rules out `c = 0.540 us/CB` of *host* encode cost between command
buffers, total 24 us/step. The 489 us/step here is *counter-measured GPU-busy
kernel time* inside the command buffers. The two quantities are disjoint and
measured by different instruments; conflating them is precisely the error that
made PR #158 chase per-dispatch overhead.

**Mechanism.** Fusion across the barriered seams, which is also where the
frontier review independently landed. The natural candidates, in order of how
mechanical they are:

1. `rmsbfloat16` (41 calls, 124.6 us/step) into its consumer matvec's prologue.
   A 2048-element bf16 norm is a threadgroup reduction the consumer can do
   itself before its first weight tile lands.
2. `decode_router_top8_ordinal_table_norm` (39 calls, 185.7 us/step) into
   `residual_rms_router_rpg8_keys_v1`. The router projection already produces
   the 256 scores; the top-8 selection and normalisation is a reduction over
   data that is already in registers when the producing kernel ends. This one
   pair is worth **~186 us/step = 2.72 % score** on its own and reads no new
   bytes.
3. The residual epilogues into their producing matvecs.

I am pricing 100-300 us/step as the realistic recoverable subset, not the full
489, because each fusion consumes threadgroup memory and registers in a kernel
that is already at 91-98 % of roofline, and an occupancy regression in the
weight pool would cost more than the glue saves. That trade has to be measured
per fusion, and it is why this is three separate small experiments rather than
one.

### 5.4 Explicitly not on this list

- **The dense-layer bf16 MLP.** `dense_gate_up_swiglu` and
  `dense_down_residual` are `laguna_dense_*_bf16_v1`
  (`LagunaRuntimeModel.swift:8040`, `:8133`) and load `vec<bfloat,4>` -- this is
  the one un-quantized MLP in the model, 101 MB/step, 409 us/step, 4.8 % of the
  step. At NVFP4 it would read 28 MB and cost ~104 us/step: a **306 us/step,
  4.48 % score** prize. It is **ruled out** -- the accepted envelope permits
  only group-32 affine INT8 for Q/K/V/O and per-head `g_proj`. Priced here so
  that the next person to notice a 249 GB/s kernel reading 67 MB does not spend
  a session re-deriving it.
- **`lmhead_int5_base_coarse_delta`** (427.0 us/step, 6.25 %, census rank 6).
  Pruned/sparse, so its byte count is not modellable from config shapes, and it
  is fenced to maple-fern PR #137.

---

## 6. What to stop targeting

### 6.1 Per-command-buffer overhead

With `c = 0.540 us/CB` and 45 command buffers per step, the **entire** per-CB
budget is `45 c = 24 us/step = 0.36 %` of score, and that is the ceiling
reachable only by driving the decode step to a single command buffer. PR #158's
`c = 1.596` made this look like a 72 us/step prize; it is not.

The local slope is far worse than even that ceiling suggests. Between 45 and 204
buffers per step the measured marginal cost is **0.022 us/CB** (§2.7), so
removing ten command buffers from the shipped step is worth roughly **0.2 us**
-- two orders of magnitude below the +-70 us measurement floor. Encoder
batching, command-buffer merging, and dispatch-count reduction as ends in
themselves are unmeasurable here, not merely small.

### 6.2 The three shadowed kernels

`gate_sp_h64`, `gate_sp_h48` and `shared_nvfp4_swiglu_qmv_rows1` carry ~500
us/step of GPU work at `E ~ 0.10`, so only ~50 us/step of it reaches the step
wall. Making `gate_sp` twice as fast buys roughly `199.2 / 2 x 0.10 = 10 us/step`
(0.15 % score), not the 100 us/step the raw census implies.

This retro-explains an existing NO-GO rather than proposing anything new: PR
#101's `gate_sp` R x NS occupancy re-geometrization returned **-0.04 %**. It was
optimizing a kernel that is already free. The exposure model predicts exactly
that outcome, which is a useful post-hoc validation of the model.

### 6.3 Further overlap, granularity, or dispatch-type engineering

The shipped configuration already captures the available overlap: `E ~ 1.0` for
everything except three small kernels, and those are ~90 % hidden. There is at
most ~50 us/step of un-captured shadowing left, and capturing it requires giving
a shadowed kernel a *longer* hazard-free neighbour -- which the big matvecs
already are. The 12-dispatch layer-pair groups under-delivering at 0.54-0.73 of
prediction is the signature of that ceiling.

### 6.4 Census-ranked targeting with a constant per-dispatch correction

Both inputs to the §2.b ranking are wrong: the constant (1.419 us/dispatch vs
the measured 0.480) and the omission of `E` entirely. Rank against §4, not §2.b.

### 6.5 The wall-minus-busy gap, and re-splitting to reclaim it

The gap between step wall time and `gpu_busy_union` is **262 us/step = 3.83 % of
score** at the shipped 45-command-buffer split. That is a real, visible number
and it is the obvious thing to go after next. **It is measured dead.**

The SPLIT sweep in §2.7 measures the gap at three granularities, in both
dispatch-type arms:

| split | CBs/step | dispatches/step | gap, concurrent | gap, serial |
|---|---|---|---|---|
| `k=1` (one dispatch per CB) | 406.2 | 406.2 | 1.349 ms | 1.191 ms |
| `k=2` | 204.1 | 406.2 | 0.365 ms | 0.255 ms |
| `k=0` (**shipped**) | 45.0 | 406.2 | **0.262 ms** | 0.241 ms |

The shipped split is at or adjacent to the minimum of that curve. Doubling the
command-buffer count costs **+103 us/step**; going to one dispatch per buffer
costs **+1087 us/step**. There is no evidence of a granularity on the other side
of the minimum, and the direction of every measured move is worse. Re-splitting
the decode step is not a lever; it is a way to lose 100-1000 us/step.

### 6.6 Two instrument traps that manufacture phantom headroom

Both of these cost me time in this session, and both would make a kernel look
badly inefficient when it is not. Recording them so nobody re-derives them.

- **`weights/config.json` says `num_attention_heads: 48`. The runtime does not
  use that number for most layers.**
  `Sources/MLXFastModel/LagunaConfig.swift` sets
  `slidingAttentionHeads = 64` (`:26`) and `fullAttentionHeads = 48` (`:24`).
  Laguna XS 2.1 is a **hybrid**: 30 sliding-window layers run **64** query
  heads, 10 full-attention layers run 48. Pricing the h64 kernels at 48 heads
  under-counts their operand by 1/3 and manufactures a phantom ~22 %
  inefficiency in exactly the kernels (`decode_nvfp4_qkv_h64`, `oproj_act_h64`)
  that section 5.0 shows are already at 94-98 % of roofline. Read
  `LagunaConfig.swift`, not `config.json`.
- **The dense layer is bf16, not NVFP4.** `laguna_dense_gate_up_swiglu_bf16_v1`
  (`LagunaRuntimeModel.swift:8040`) and `laguna_dense_down_residual_bf16_v1`
  (`:8133`) load `vec<bfloat,4>`. Assuming the model-wide NVFP4 layout here
  under-counts their operand by 3.56x and makes two kernels running at 91 % of
  peak look like they are running at 26 %. Every other large matvec in the step
  really is NVFP4 -- this single MLP is the exception, and it is the exception
  that looks most like a bug.

The general form of both traps: **a kernel's efficiency number is only as good
as its assumed operand size, and the operand size lives in Swift source, not in
the checkpoint metadata.** Verify the representation and the head count from
`LagunaRuntimeModel.swift` and `LagunaConfig.swift` before pricing anything.

---

## 7. Does `gpu_busy_sum` survive as an instrument?

**Partly. Its positive uses survive; its one negative claim must be withdrawn.**

| use | verdict |
| --- | --- |
| total GPU work per step at the shipped split | **survives**. `busy/wall = 1.064`, `gap` is stable across a large scheduling perturbation (p = 0.63). |
| per-kernel isolated cost, measured at SPLIT=1 | **survives**. At one dispatch per command buffer nothing overlaps, so the per-kernel census is a genuine isolated-work measurement. This is what makes the §2.b kernel times reusable at all. |
| detecting command-buffer-level concurrency | **survives, and correctly reported zero.** `gpu_busy_union` equals `gpu_busy_sum` in both arms, so no command buffers overlap. That is a true fact about this runtime. |
| detecting *intra*-command-buffer concurrency | **does not survive.** Both `sum` and `union` are built from command-buffer start/end timestamps. Concurrency between two dispatches inside one buffer is invisible: it shows up as a buffer that finished sooner, i.e. as *work that is not there*, never as overlap. |
| PR #158's claim "hidden concurrent work <= 0.06 ms/step" | **withdrawn.** The instrument is structurally incapable of supporting it. The true value is 448 +- 31 us/step. |

Two concrete rules for future use:

1. **Never form a per-command-buffer cost by differencing two SPLIT levels
   without a `D` term.** The correct identity is
   `busy(k) = W + N(k) c - D(k)`, with `D(1) = 0` by construction. `c` must be
   derived from two levels that both have `D = 0`, or from a level pair where
   `D` is independently known.
2. **`gpu_busy_sum` at the shipped split is not the sum of isolated kernel
   costs.** It is `W + 45 c - D`. Anyone summing the §2.b column and comparing
   it to 7999.4 us is comparing two different quantities and will conclude the
   census "over-accounts" by ~500 us. That gap is `D`, not census error.

The GPUPROF window correlation itself is sound and was verified in both
directions: a run under `CLOCK_UPTIME_RAW` produces a non-empty window, and a
deliberately broken clock control (`research/nezuko_clockfix_control.py`,
substituting a process-relative `perf_counter` for `mach_absolute_time`) fires
`WINDOW CORRELATION FAILED` rather than silently reporting plausible garbage.

---

## 8. Reproduction

All timings on the M4 Pro host described in the header, single model-holding
process, 40 C thermal gate, GPU idle 38-39 C at every launch.

```bash
# 1. Build the instrumented worker. Neither patch is ever committed to the
#    submitted surface; both are applied to a throwaway scratch tree.
git apply research/nezuko-serial-dispatch-probe.patch
git apply research/nezuko-pr158-gpuprof-hook.patch
CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions \
  --scratch-path .build-worker --product mlxfast-runtime-worker
git checkout -- \
  Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp \
  Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.h

# 2. A0 discriminator: shipped split, GPUPROF hook on (h1) and off (h0).
PHASES='1:0 0:0' OUT=research/nezuko-a0-dispatch-type \
  bash research/nezuko_a0_dispatch_type_abba.sh
python research/nezuko_a0_analyze.py research/nezuko-a0-dispatch-type --top 30

# 3. A0 SPLIT localization: 2 and 1 dispatches per command buffer.
#    k=1 is the probe-validity control; k=2 separates R-A from R-B.
PHASES='1:2 1:1' OUT=research/nezuko-a0-split \
  bash research/nezuko_a0_dispatch_type_abba.sh
python research/nezuko_a0_split_derive.py

# 4. A1 exposure factors E = dS/dI for the default-ON fusion knobs.
bash research/nezuko_a1_exposure.sh
python research/nezuko_a1_analyze.py research/nezuko-a1-exposure

# 5. A2 re-priced census.
python research/nezuko_a2_reprice.py --top 25 \
  --exposure '{"gate_sp_h64":0.10,"gate_sp_h48":0.10,"shared_nvfp4_swiglu_qmv_rows1":0.10}'

# 6. Clock-correlation negative control (must print WINDOW CORRELATION FAILED).
DARKBLOOM_GPU_PROFILE=1 /usr/bin/python3 research/nezuko_clockfix_control.py \
  --steps 40 --profile
```

Every ABBA driver writes one `*.txt` summary per point plus a large
`*.worker.err` GPUPROF dump. Only the `.txt` summaries are committed; the raw
dumps are 19 MB/point at SPLIT=0 and considerably larger at SPLIT=1, and are
excluded via `.git/info/exclude`.

**Scope.** `git diff --stat` against the assignment base
`268fb087980cc6ee9a60479f74f37d1ed258ec8f` touches `research/` only. No file
under `Sources/`, `Vendor/`, or `benchmark.json` is modified, so this PR
consumes **zero submitted-surface bytes** and zero of the 262,144-byte
per-review growth budget. Region fences respected: no edits to
`LagunaRuntimeModel.swift` (maple-frieren #148), `LagunaLmHeadPrune.swift`
(maple-fern #137), or `fp_quantized_nax.h` / `mlx-generated/fp_quantized_nax.cpp`
/ `quantized.cpp` (maple-tanjiro #170). No `mlxfast submit` was issued.

*This report was written by an AI agent (OpenHands) on behalf of the Senpai
research campaign.*
