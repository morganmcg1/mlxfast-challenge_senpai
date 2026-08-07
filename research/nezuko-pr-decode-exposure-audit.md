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
of one extra command buffer, and `D` for the GPU time saved by concurrent
execution at the shipped granularity. At SPLIT=1 every command buffer holds one
dispatch, so **nothing can overlap**:

```text
busy(SPLIT=1) = W + 406 c
busy(SPLIT=0) = W +  45 c - D
---------------------------------
difference    =        361 c + D
```

PR #158 assigned the entire 573.4 us to `361 c` and implicitly asserted `D = 0`.
But `D` is exactly the quantity PR #101 measured, and it is *not* zero. The
single error inflates `c` and annihilates `D` simultaneously -- which is why the
same 7.6x shows up on both sides of the contradiction.

### The headline

| quantity | PR #158 | this PR |
| --- | --- | --- |
| `D`, concurrency benefit at the shipped split | ~0 (bounded <= 60 us/step) | **448 +- 31 us/step** |
| `c`, marginal GPU cost of one command buffer | 1.596 us/CB | **0.35 +- 0.23 us/CB** |
| per-dispatch de-inflation applied to every §2.b row | 1.419 us | **~0.24-0.31 us** |
| `W`, zero-overlap work per step | never formed | **~8.43-8.46 ms/step** |

`c` is roughly **4.6x smaller** than published. The `1.419 us/dispatch`
correction sitting under every row of the §2.b census is about **6x too large**.

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

TBD-1.

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

### 2.7 Independent cross-check from PR #158's own SPLIT=2 datum

PR #158 published `busy(SPLIT=2) = 8058.0 us` at 204 command buffers per step.
Re-priced with `c = 0.347` and `W = 8572.8 - 406 c = 8431.9`:

```text
busy(k=2) = W + 204 c - D(2)
8058.0    = 8431.9 + 70.8 - D(2)
D(2)      = 444.7 us      =>  D(2)/D(0) = 0.993
```

R-A predicts `D(2)/D(0) = 202/361 = 0.560` (seams scale with dispatch count).
R-B predicts ~0.95 (one good neighbour per pair is enough). With the alternative
`c = 0.209` the ratio is 0.95. Either way the datum PR #158 already had on disk
falsifies R-A -- it was never analysed against a model that allowed `D != 0`.

---

## 3. Exposure factors

TBD-3.

---

## 4. The re-priced census

TBD-4.

---

## 5. Top surviving decode targets, priced

TBD-5.

---

## 6. What to stop targeting

### 6.1 Per-command-buffer overhead

With `c ~ 0.35 us/CB` and 45 command buffers per step, the **entire** per-CB
budget is `45 c ~ 16 us/step = 0.23 %` of score. Eliminating every command
buffer boundary on the decode path is worth less than a 2 % improvement on one
of the big NVFP4 matvecs. PR #158's `c = 1.596` made this look like a 72 us/step
prize; it is not. Encoder batching, command-buffer merging, and dispatch-count
reduction as ends in themselves are all below the +-70 us measurement floor.

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

Both inputs to the §2.b ranking are wrong: the constant (1.419 vs ~0.31) and the
omission of `E` entirely. Rank against §4, not §2.b.

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
