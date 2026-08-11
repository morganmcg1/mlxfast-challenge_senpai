# N-NORM-QKV-FUSION-BELOW-BAR

**Assignment** `maple-r110-a-prefill-nax-arm-factory`, revision `r110-a-rev4`, Stage 0.
**Student** maple-tanjiro. **PR** #692. **Host** Mac16,11 M4 Pro, 48 GB, 20 cores, Apple GPU gen 16
(`is_nax_available() == false`, low-memory startup profile active).
**Submitted surface: untouched.** A2 in `matmul.cpp` stays frozen exactly as the advisor left it;
everything below is research-only measurement under `research/maple-tanjiro-r110/`.

---

## 1. Verdict in one paragraph

The fused RMSNorm+QKV path (`lagunaNormAffineQKV`) is **reachable, numerically exact, and slower
than the unfused path** on the only bank where it currently runs. On the group-32 affine INT8 bank
it removes exactly 40 dispatches per decode step (366 -> 326) and eliminates 40 of the 41
`rmsbfloat16` calls, but the fused projection kernel gives back **more time than the norms cost**.
Measured penalty is **+24 to +60 us/step against fusion** in SPLIT-corrected GPU-busy time and,
from the 32-run paired ABBA in the unsplit build whose microseconds are actually priced,
**+17.2 us/step against fusion, 95 % [+9.0, +25.3]** (blocking-free rank test z = +3.05,
p ~ 0.002). The Stage 1 bar was fusion being **at least +35.7 us/step
faster**. Observed sign is the wrong one, and the most fusion-favourable bound in any
estimator is +2.7 us/step, still **13x short of the bar**. **Stage 1 is not
entered.** The full theoretical ceiling of this idea -- eliminating every per-layer input norm for
free -- is only **~77 us/step** on either bank, so even a perfect implementation clears the bar by
about 2x, and this implementation is 100-137 us/step away from perfect.

---

## 2. What was measured, and how the guard was satisfied

`lagunaNormAffineQKV` (`Sources/MLXFastModel/LagunaRuntimeModel.swift:5488`, call site `:5933`) sits
behind a decode-only outer gate (`B == 1, L == 1`, `:5897`) and a six-condition guard (`:5926-5931`)
that requires the Q/K/V bank to be **group-32 affine INT8**. The shipped model quantizes those
projections as NVFP4, so on the default configuration **the fusion never fires** and its cost was
unknown.

The bank is selectable at runtime without touching the submitted surface:
`lagunaNativeAffineNVFP4From` (`:3048-3054`) starts with
`guard env["DARKBLOOM_NATIVE_AFFINE_NVFP4"] != "0" else { return nil }`, and the consumer at `:3101`
falls through to `:3115-3123`, `quantized(source, groupSize: 32, bits: 8, mode: .affine)`.
Group-32 affine INT8 for Q/K/V/O plus per-head `g_proj` is exactly the permitted re-quantization
envelope (`TASK.md:78-94`), so this is a legal configuration to measure, not a hack.

Three arms, one binary, one weight bank load path, same host, same session:

| arm | environment | meaning |
|---|---|---|
| **F** | `DARKBLOOM_NATIVE_AFFINE_NVFP4=0` | int8 bank, **fusion ON** (guard satisfied) |
| **U** | `DARKBLOOM_NATIVE_AFFINE_NVFP4=0` `DARKBLOOM_FUSED_NORM_AFFINE_QKV=0` | int8 bank, **fusion OFF** |
| **N** | (none) | shipped NVFP4 default -- bank-cost reference only |

`F - U` is the fusion effect. `N` exists only to price the bank so the reader can see what does and
does not cancel.

**Correctness.** All three arms ran 200 teacher-forced decode steps against the seeded 512-token
prefix and reported **`0 divergences (all match)`**. The int8 bank has zero test coverage in-tree;
it nonetheless produced bit-identical greedy tokens in every arm. This is not a substitute for
`run_upstream_equivalence.sh` and is not offered as one -- no code on the submitted surface changed,
so no equivalence claim is being made.

---

## 3. Dispatch and kernel accounting (SPLIT=1, 200 steps, 199 steady steps)

Captured with `research/maple-tanjiro-r110/stage0-split1-profile.sh`, which applies
`research/pr91-gpuprof-hook.patch`, builds an instrumented worker, runs each arm under
`DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=1`, and reverts the patch on exit.
Raw per-arm output is committed under `stage0-evidence/{F,U,N}.log`.

| | **F** fused/int8 | **U** unfused/int8 | **N** shipped NVFP4 |
|---|---|---|---|
| dispatches per step | **326.0** | **366.0** | 406.0 |
| gpu_busy_sum per step | 11.630 ms | 11.558 ms | 8.567 ms |
| wall per step (SPLIT=1) | 12.102 ms | 12.016 ms | 9.811 ms |
| inter-dispatch gap | 0.472 ms (3.9 %) | 0.458 ms (3.8 %) | 1.244 ms (12.7 %) |
| decode mean / median (ms) | 12.108 / 12.034 | 12.024 / 11.971 | 9.822 / 9.775 |
| teacher-forced divergences | 0 | 0 | 0 |

The dispatch delta is exactly **-40**, which is exactly the 40 per-layer input norms. The 41st
`rmsbfloat16` (the final norm before the LM head) survives in arm F, as expected.

### Changed-kernel set

**F** -- fused norm+QKV, 40 calls/step across four specializations:

| n/step | us/call | us/step | kernel |
|---|---|---|---|
| 27 | 98.66 | 2663.9 | `norm_affine_qkv_qmv_i8g32_r10304_pf4_idx_v1` |
| 9 | 79.92 | 719.3 | `norm_affine_qkv_qmv_i8g32_r8240_pf4_idx_v1` |
| 3 | 102.50 | 307.5 | `norm_affine_qkv_qmv_i8g32_r10304_pf4_v1` |
| 1 | 84.30 | 84.3 | `norm_affine_qkv_qmv_i8g32_r8240_pf4_v1` |
| **40** | | **3774.9** | fused QKV total |
| 1 | 3.57 | 3.6 | `rmsbfloat16` (final norm only) |
| **41** | | **3778.5** | **changed-set total** |

**U** -- separate norm then projection:

| n/step | us/call | us/step | kernel |
|---|---|---|---|
| 40 | 90.95 | 3638.0 | `affine_qmv_fast` |
| 41 | 3.49 | 143.2 | `rmsbfloat16` |
| **81** | | **3781.2** | **changed-set total** |

Raw changed-set difference is **-2.6 us/step**, which naively reads as a wash. It is not, because
the two arms issue a different number of command buffers.

---

## 4. The SPLIT=1 correction, and a drift control that must be applied with it

Under `DARKBLOOM_GPU_PROFILE_SPLIT=1` every dispatch becomes its own command buffer, and each
command buffer carries a fixed **+1.554 us** of measured busy time that does not exist in the
unsplit build. Arm U issues 81 command buffers in the changed set; arm F issues 41. Comparing raw
totals therefore hands arm U a 62 us handicap that is pure instrumentation.

| | F | U | F - U |
|---|---|---|---|
| changed-set measured | 3778.5 | 3781.2 | -2.6 |
| SPLIT inflation (n x 1.554) | 63.7 (41 cb) | 125.9 (81 cb) | -62.2 |
| **changed-set true busy** | **3714.8** | **3655.3** | **+59.5 (fusion slower)** |

**Drift control.** The two arms are separate worker processes, so a single capture pair can drift.
The 19 kernels that are byte-identical between the arms are dispatched **285 times per step in both
arms** -- identical count, so the SPLIT inflation cancels exactly and their sum is a clean
same-work control:

| | F | U | ratio |
|---|---|---|---|
| unchanged-kernel sum (285 disp/step) | 7851.7 us | 7777.0 us | **1.0096** |

Arm F's capture ran **0.96 % slower on identical work**, i.e. a **+74.7 us/step** systematic offset
that has nothing to do with the fusion. That offset is *larger than the effect being measured*, so
the raw +59.5 us figure must not be quoted alone. Rescaling arm F's changed set by 1/1.0096:

| | value |
|---|---|
| F changed-set, drift-corrected | 3679.4 us |
| U changed-set, true | 3655.3 us |
| **drift-corrected fusion penalty** | **+24.2 us/step (fusion slower)** |

So the honest SPLIT=1 answer is a band: **fusion costs +24 to +60 us/step of GPU busy**, sign
unambiguous, magnitude uncertain by roughly the size of the effect. This is precisely why the wall
ABBA in section 6 was run, and why a single profile capture is not the deliverable.

---

## 5. Where the time actually goes: the prize is real but small, the give-back is larger

Decomposing the drift-corrected numbers into "norms removed" and "projection got more expensive":

| component | true us/step | note |
|---|---|---|
| all 41 `rmsbfloat16` in U | 79.4 | 143.2 measured - 41 x 1.554 |
| **40 per-layer norms eliminated** | **+77.4 saved** | 79.4 x 40/41 |
| U projections (`affine_qmv_fast` x40) | 3575.8 | 3638.0 - 40 x 1.554 |
| F projections, drift-corrected | 3677.4 | |
| **fused projection give-back** | **-101.6 cost** | |
| **net** | **-24.2 (fusion slower)** | |

Two things follow, and the second matters more than the first.

**(a) The ceiling is low.** One `rmsbfloat16` dispatch truly costs **1.94 us**. Forty of them cost
**77.4 us/step**, i.e. 0.79 % of the 9.81 ms NVFP4 step. On the shipped NVFP4 arm the same kernel
measures 41 x 3.47 = 142.1 us -> **76.5 us/step true** for 40 norms, essentially identical. At the
campaign pricing constant of 0.0070 % of score per steady-state M4 wall microsecond, a *free*
elimination of every per-layer input norm is worth about **+0.54 % of score**. That is the absolute
best case for this entire direction, and it assumes the fusion itself is free.

**(b) The fusion is not free, by 1.3x its own ceiling.** The fused kernel costs 101.6 us/step more
than `affine_qmv_fast` doing the same projections. So the mechanism spends 1.31 units to buy 1.00
unit.

**Confound, named honestly.** The +101.6 us has two candidate causes and this experiment does not
separate them:

1. **Redundant reduction.** Every threadgroup in the fused kernel recomputes the RMS over the
   2048-wide input row, so the reduction is paid once per threadgroup instead of once per row.
2. **Kernel quality.** `norm_affine_qkv_qmv_i8g32_*` is a hand-written MLXFast runtime-compiled
   string kernel; `affine_qmv_fast` is MLX's tuned quantized matvec. The fused kernel may simply be
   a worse matvec, independent of the norm.

The knobs to decompose this exist -- `DARKBLOOM_NORM_AFFINE_QKV_PF` (0..4, default 4) and
`DARKBLOOM_NORM_AFFINE_QKV_STAGE=tg` -- and a PF/stage sweep in arm F would attribute the give-back.
It was not run because the attribution does not change the Stage 1 decision: even if the entire
101.6 us were kernel-quality and a perfect fused kernel recovered all of it, the remaining prize is
77 us/step, and the NVFP4 geometry in section 7 says NVFP4 would keep less of it than int8 does.
This is the highest-value follow-up if the advisor wants the direction reopened.

---

## 6. Paired wall-time ABBA (the deliverable interval)

Because the two arms are separate processes and section 4 showed a drift larger than the effect, the
decisive measurement is an interleaved paired design in the **unsplit** build -- the one whose
microseconds are actually priced.

Driver: `research/maple-tanjiro-r110/stage0-norm-qkv-abba.sh`, 32 runs, 200 decode steps each,
order `FUUFUFFUFUUFUFFUFUUFUFFUFUUFUFFU` -- a palindromic block of 8 repeated 4x, with F at slots
{1,4,6,7} and U at {2,3,5,8}, both with mean slot 4.5, so any monotone thermal or hour-of-day trend
cancels to first order within every block.

Analysis: `research/maple-tanjiro-r110/stage0-analyze.py`, reporting both an unpaired interval
and a block-paired interval (`BLOCK_LEN=8`). One label correction: the unpaired interval is printed
as "Welch" but uses `df = min(n_a, n_b) - 1 = 15` rather than the Welch-Satterthwaite df (~27 here).
That is deliberately conservative -- it widens the interval -- but it is not Welch's df, and the
column is read that way below.

**Run.** 32 runs completed, 200 decode steps each, `0` divergent runs (every
teacher-forced token matched in all 32). Raw per-run table is committed at
`stage0-evidence/abba.tsv`; load time was 42-44 s per run and the whole rig took
~26 min. Per-arm summary (per-step wall, us):

| arm | n | mean | sd | median-of-run-medians |
|---|---|---|---|---|
| **F** fused | 16 | **11638.1** | 17.2 | 11627.4 |
| **U** unfused | 16 | **11620.9** | 24.9 | 11608.8 |

**F - U = +17.2 us/step on the mean, +18.6 us/step on the median. Fusion is
slower.** Sign agrees with both SPLIT=1 estimators.

### 6.1 The point estimate is stable; the interval width is not

The contrast is insensitive to the analysis choice, but the *uncertainty* is
not, and reporting only the pre-registered block length would overstate the
precision. All three block lengths, mean column:

| estimator | F - U | 95 % interval | excludes 0? |
|---|---|---|---|
| unpaired, conservative df=15 | +17.2 | [+1.0, +33.3] | yes |
| **blocked, k=4 x 8 (pre-registered)** | **+17.2** | **[+9.0, +25.3]** | **yes** |
| blocked, k=8 x 4 | +17.2 | [-2.7, +37.0] | **no** |
| blocked, k=2 x 16 | +17.2 | [-36.0, +70.4] | no (df=1, uninformative) |

The design block is 8 (the palindrome `FUUFUFFU`), so `[+9.0, +25.3]` is the
pre-registered answer. But it rests on **k=4 contrasts, df=3**, and a df=3
variance estimate is itself worth roughly +-40 %. The k=8 blocking has a better
conditioned variance estimate and does **not** exclude zero. Per-block contrasts
show why:

```
k=4 blocks of 8:  +20.8  +22.0  +15.0  +11.0        (4/4 positive)
k=8 blocks of 4:   -3.0  +44.5  +24.0  +20.0
                  +20.5   +9.5  +47.0  -25.0        (6/8 positive)
```

The two negative 4-blocks are the two outlier runs, `28 F=11.689` and
`32 U=11.701`; they land in different arms and largely offset in the mean, but
they inflate a variance estimated from only 2 runs per arm per block.

**Blocking-free corroboration.** A Mann-Whitney rank test on the 32 run means
makes no drift, normality, or blocking assumption at all: **U = 209.0, z = +3.05
(p ~ 0.002)**, F ranked slower. The sign is therefore not an artefact of the
block length.

### 6.2 The decision does not hinge on zero

Whether the interval excludes zero is the wrong question here, and it is worth
being explicit because the honest answer to it is "depends on the block length".
The Stage 1 gate is not zero -- it is fusion being **faster by +35.7 us/step**
(+0.25 % at 0.0070 %/wall-us). Against that bar every interval agrees:

| estimator | most fusion-favourable 95 % bound | vs +35.7 bar |
|---|---|---|
| blocked k=4 x 8 | fusion **9.0 us/step slower** | bar excluded |
| blocked k=8 x 4 | fusion 2.7 us/step faster | bar excluded, 13x short |
| unpaired df=15 | fusion 1.0 us/step slower | bar excluded |

The best case for fusion anywhere in this data is **+2.7 us/step**, against a bar
of **+35.7**. The bar sits outside every interval at every block length, and it
is not close in any of them.

### 6.3 What this says about the instrument

The rig resolved this decision, and its resolution is worth recording because it
is the first paired number this branch has produced. The widest credible
half-width above is ~20 us/step on an 11.6 ms step = **+-0.17 % of score for 32
runs / ~26 min**; the pre-registered blocking gives +-8.1 us = **+-0.07 %**. So a
paired M4 ABBA of this size does resolve a 0.25 % effect, on an arm that
actually executes on this host. That is a property of the *rig*, established
here on a live contrast -- not a claim that it can be pointed at an arm the host
never runs.

---

## 7. Why the shipped NVFP4 bank would do worse, not better

Stage 1 would have ported the fusion to NVFP4. The dispatch geometry argues against it directly.

| | rows per threadgroup | grid | threadgroup |
|---|---|---|---|
| fused int8 `lagunaNormAffineQKV` (`:5536-5542`) | **8** | `((rows/8)*64, 1, 1)` | 64 |
| NVFP4 `lagunaDecodeNVFP4QKVR1` (`:5002-5064`) | **2** | `((rows/2)*64, 1, 1)` | 64 |

The NVFP4 QKV kernel runs **4x as many threadgroups** for the same output rows. Folding the RMS
reduction into it therefore replicates that reduction **4x more often** than the int8 fusion does.
The int8 fusion already loses 101.6 us/step against a 77.4 us/step prize; the same construction on
NVFP4 starts from a strictly worse redundancy ratio, against a prize (76.5 us/step) that is the
same size. There is no reading of these numbers under which the NVFP4 port clears a +36 us/step bar.

Making it work would require restructuring `lagunaDecodeNVFP4QKVR1` to 8 rows per threadgroup, or
adding a threadgroup-cooperative single-pass reduction, both of which are new kernels rather than a
port -- a different, larger experiment with its own correctness surface.

---

## 8. The bank cost, stated explicitly because it cancels

Arm N (shipped NVFP4) runs at **9.81 ms/step**; the int8 bank runs at **~12.0 ms/step**. The int8
bank is **~2.2 ms/step, about 22 %, slower**. That is not a finding about fusion. It is entirely a
property of the bank -- `decode_nvfp4_qkv_h64_r1_v1_*` at 44.81 us/call and `oproj_act_h64_v1_*` at
37.22 us/call are far faster than their int8 counterparts at 90.95 and 75.08 us/call.

**This 2.2 ms is common to arms F and U and cancels exactly in the F - U contrast.** It does not
contaminate the fusion measurement in either direction.

It does, however, forbid the reverse extrapolation, and this is the single most important caveat in
this document: **the int8-bank result is not the NVFP4 prize.** What was measured is bounded, and
that bound is stated -- on the int8 bank the fusion loses by 24-60 us/step of busy and ~32 us/step
of wall. What was *not* measured is what an NVFP4 fusion would cost, and section 7 is a structural
argument, not a measurement. No number in this document should be carried across the bank boundary
as a prediction. The correct summary is: **the cheapest available instrument says the mechanism is
underwater on the bank where it runs, and the geometry says the other bank is harder, so the
expensive experiment is not worth buying.**

---

## 9. Decision

**Stage 1 is not entered.** The Stage 0 gate was "fusion faster by more than ~36 us/step
(+0.25 % at 0.0070 %/wall-us)". Every estimator produced here has fusion **slower**:

| estimator | fusion effect | vs +36 us/step bar |
|---|---|---|
| SPLIT=1 changed-set, raw | -59.5 us/step | miss by 95.5 |
| SPLIT=1 changed-set, drift-corrected | -24.2 us/step | miss by 60.2 |
| unsplit wall, single pair | -32 us/step | miss by 68 |
| **unsplit wall, 32-run paired ABBA** | **-17.2 us/step [-25.3, -9.0]** | **miss by 52.9** |
| same, widest blocking (k=8) | -17.2 us/step [-37.0, +2.7] | miss by 33.0 at best |
| same, Mann-Whitney rank test | fusion slower, z=+3.05, p~0.002 | -- |

Recorded as **`N-NORM-QKV-FUSION-BELOW-BAR`**. This is a full-value negative: the mechanism is
reachable and exact, its ceiling is now known to be ~77 us/step on either bank, its current
implementation is 1.3x underwater against that ceiling, and the shipped bank's geometry makes the
port strictly harder rather than easier.

**Cost to reach this verdict:** three ~50 s profile runs plus one 32-run / ~26 min paired ABBA on
an M4, and zero bytes of submitted-surface change.

---

## 10. Follow-ups not implemented

1. **PF/stage sweep in arm F** (`DARKBLOOM_NORM_AFFINE_QKV_PF=0..4`,
   `DARKBLOOM_NORM_AFFINE_QKV_STAGE=tg`) to split the 101.6 us give-back into "redundant reduction"
   versus "hand-written kernel is a worse matvec". If it is mostly the latter, the direction is
   worth reopening with a better fused kernel; if mostly the former, it is closed.
   **The driver is written and committed** at
   `research/maple-tanjiro-r110/stage0-fusion-tuning-sweep.sh` (~20 min, one binary, six arms);
   I did not run it because it cannot change the Stage 1 verdict, only the reopen recommendation,
   and follow-up 2 below is a better shape of the idea regardless.
2. **Cheaper norm elimination.** The 77 us/step prize does not require fusion into the projection.
   Fusing the input norm into the *previous* layer's residual-add epilogue -- the pattern
   `residual_rms_router_bf16_2048_rpg8_keys_v1_pf1` already uses at 8.29 us/call for 39 calls --
   would harvest the same 40 dispatches without touching the QKV matvec at all, and without any
   redundant-reduction exposure. That looks like the strictly better shape of this idea.
3. **The int8 bank is untested.** `DARKBLOOM_NATIVE_AFFINE_NVFP4=0` selects a legal, in-envelope
   quantization with no test coverage, yet passed 200 teacher-forced steps with zero divergences in
   two independent configurations. Whether that path is intended to remain live is an advisor call,
   not mine.

---

## 11. Reproduction

```bash
# SPLIT=1 kernel table (three arms, ~3 min total)
bash research/maple-tanjiro-r110/stage0-split1-profile.sh /tmp/r110a-split1 200

# paired wall ABBA (32 runs, ~20 min)
bash research/maple-tanjiro-r110/stage0-norm-qkv-abba.sh \
  FUUFUFFUFUUFUFFUFUUFUFFUFUUFUFFU /tmp/r110a-stage0 200
python3 research/maple-tanjiro-r110/stage0-analyze.py /tmp/r110a-stage0/abba.tsv    # k=4 x 8
python3 research/maple-tanjiro-r110/stage0-analyze.py /tmp/r110a-stage0/abba.tsv 4  # k=8 x 4
```

The committed `stage0-evidence/abba.tsv` reproduces every number in section 6 without rerunning the
rig: `python3 research/maple-tanjiro-r110/stage0-analyze.py \
research/maple-tanjiro-r110/stage0-evidence/abba.tsv`.
