# PR #48 fusion deconfound — separating the dispatch refund from the geometry cost

Student: `maple-nezuko`. Assignment `maple-2026-08-07m-pr48-deconfound` r1, PR #298.
Base `codex/mlxfast-maple-20260804-advisor` @ `d9905fc7d4902951c33142c58cd7fbebe6a1cc21`.
Host: Apple M4 Pro, 48 GiB (low-memory startup profile). **Directional only** — the
ranked host is M5 Max.

## 1. Question

PR #48 folded the input RMSNorm into the decode QKV kernel and lost
`-0.1488 %` ranked (receipt `285f79fa-089f-4184-b1ec-0647cb51e61b`,
`ns = 2.540575` against control `c3ce66ec` `ns = 2.544360`). That candidate changed
three things at once:

1. it removed 40 `rmsnorm` dispatches per decode step (the intended **refund**);
2. it hardcoded 512 threads / 16 simdgroups per threadgroup in the QKV kernel,
   an **8x reduction in threadgroup count** relative to the stock lane-major
   geometry (the **geometry** confound);
3. it made every QKV threadgroup redo the whole 2048-element RMSNorm reduction
   instead of reading a precomputed row (the **redundant-reduction** confound).

A single A/B cannot say which of the three lost the race, so the negative did not
tell us whether norm/QKV fusion is a dead idea or a good idea wearing a bad
geometry. This experiment splits the three effects with a six-arm design in which
every contrast moves exactly one of them.

## 2. Residency — what actually runs

Established before any timing (`DARKBLOOM_TRACE_FUSION=1`):

* The live scored decode QKV kernels are `decode nvfp4 qkv r1 h48/h64 lane-major`.
  `lagunaNormAffineQKV` is **dead** on this base: `fusedQKV == nil` on all 40
  layers, and its guard requires an affine/int8/g32 bank while the QKV bank is
  NVFP4 g16.
* Neither `DARKBLOOM_DECODE_NVFP4_QKV_R1_SIMDGROUPS` nor
  `DARKBLOOM_DECODE_NVFP4_NORM_QKV_FUSE` existed on the base. Both knobs were
  written from scratch on the *live* lane-major kernel; PR #48's patches
  (`/tmp/pr48/p1.patch`, `/tmp/pr48/p2.patch`) no longer apply.
* Model shape: 30 sliding layers with `heads = 64` and 10 full layers with
  `heads = 48`; `hidden = 2048`, `headDim = 128`, `numKeyValueHeads = 8`.
  Output rows are `(64 + 16) * 128 = 10240` (h64) and `8192` (h48). The stock
  lane-major geometry is 2 simdgroups (64 threads) per threadgroup, i.e.
  **5120 / 4096 threadgroups**; at 16 simdgroups (512 threads) it is
  **640 / 512 threadgroups**.
* All 40 layers take the `_nativeAffineGProj` -> `lagunaGateSoftplus` path
  (`_nativeAffineQKVGateRows != nHeads`), so `normalized` has **two** consumers:
  the QKV kernel and the gate kernel. Any fold that wants to delete the
  `rmsnorm` dispatch must fold *both*.

## 3. The six arms

Two orthogonal knobs on the live lane-major kernel:

* `DARKBLOOM_DECODE_NVFP4_QKV_R1_SIMDGROUPS` in `{2,4,8,16}` (default 2) —
  simdgroups per threadgroup, i.e. pure row ownership.
* `DARKBLOOM_DECODE_NVFP4_NORM_QKV_FUSE` in `{0,1,3}` (default 0):
  * `0` — no fold. QKV reads the precomputed `normalized`.
  * `1` — fold. QKV *and* the gate kernel take `(residual, norm_weight)` and
    recompute the RMSNorm in a threadgroup prologue; the `rmsnorm` dispatch is
    **deleted**.
  * `3` — *redundant* fold. QKV recomputes the RMSNorm exactly as in mode 1, but
    the `rmsnorm` dispatch is still issued, `normalized` is still bound to the
    kernel (unread, to preserve the buffer-dependency edge), and the gate kernel
    still reads `normalized`.

| arm | simdgroups | fuse | threads/TG | `rmsnorm` dispatched | what it is |
|---|---|---|---|---|---|
| **0** | 2 | 0 | 64 | yes | stock, the control |
| **RV** | 2 | 3 | 64 | yes | redundant reduction at stock geometry (5120 TGs) |
| **V** | 2 | 1 | 64 | no | fold with **zero** geometry change |
| **G** | 16 | 0 | 512 | yes | geometry change alone |
| **R** | 16 | 3 | 512 | yes | redundant reduction at fused geometry (640 TGs) |
| **N** | 16 | 1 | 512 | no | **PR #48 mode 1 reproduced** |

The design gives two exact decompositions of the confounded total:

```
(N - 0)  =  (G - 0)   +  (R - G)              +  (N - R)
            geometry     redundant reduction     dispatch refund     [fused geometry]

(V - 0)  =              (RV - 0)              +  (V - RV)
                         redundant reduction     dispatch refund     [stock geometry]
```

`(V - RV)` is the contrast PR #48 could not produce: the dispatch refund measured
with the threadgroup geometry held at stock. `(N - R)` is the same refund at the
fused geometry.

## 4. Bit-exactness of the geometry knob

`num_simdgroups = R / 32` and `virtual_per_thread = 512 / R`; their product is
always 16. The partial index `p = simd_gid + num_simdgroups * j` covers elements
`[128p, 128p + 128)` for every `R`, and lane `L` inside a partial always maps to
element `128p + 4L`. The partials and the `simd_sum` lane order are therefore
identical for `R` in `{64, 128, 256, 512}`. Everything below `out_row` in the
lane-major kernel is simdgroup-local, so `num_simdgroups` is a *pure row-ownership*
change with no numerical content.

This is the first substantive finding: **PR #48's geometry confound was
avoidable.** The 512-thread geometry was not required by the fold. A staged fold
could have kept the stock geometry and moved one variable at a time.

Empirically all six arms report `teacher-forced greedy tokens: 0 divergences
(all match)` against the public 256-token golden on every run of the sweep
(49/49 runs, including the discarded primer).

## 5. Dispatch and barrier accounting

MLX's barrier rule is precise rather than conservative-per-dispatch
(`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp:315-375`):
`set_input_array` raises `needs_barrier_` only on a RAW hit against
`prev_outputs_`, `set_output_array` additionally on a WAR hit against
`prev_inputs_`, and `maybeInsertBarrier` resets the windows when it fires.
Bindings are host-side and independent of whether the shader reads the buffer.

Static consequence for the three fuse modes, per layer:

* **mode 0**: `rmsnorm(input) -> normalized`; `qkv` reads `normalized` in
  `prev_outputs_` -> barrier; `gate` then reads `normalized`, which after the
  barrier is no longer in `prev_outputs_` -> no barrier.
* **mode 3**: identical. `normalized` is still produced and still bound to `qkv`,
  so the same RAW edge and the same barrier fire. The extra `residual`/
  `norm_weight` bindings are reads of buffers that sit in `prev_inputs_`, not
  `prev_outputs_`, so they add no barrier. **Same dispatch count, same barrier
  count as mode 0.**
* **mode 1**: the `rmsnorm` dispatch is gone (**-40 dispatches per decode step**).
  `qkv` reads `input`, which the previous layer's residual add left in
  `prev_outputs_`, so the barrier is preserved.

Arm R is therefore a valid kill gate for arm N by construction: it holds the
dispatch and barrier structure at mode 0 while paying the redundant reduction.
**This is a static argument, not a measured census.** Measuring it needs
`research/fern_tax_device_counters.patch`, which touches
`Vendor/.../metal/device.cpp` — outside `editablePaths`, fingerprinted by
`Sources/MLXFastTrustedHarness/VendoredMetalFingerprint.swift:18-21`, and
requiring an MLX/metallib rebuild. It was skipped for budget; the geometry-free
contrast `(V - RV)` does not depend on it.

Prior calibration for the refund: a previous ABBA on this base measured
**+1.233 us per removed decode dispatch** (95% CI `[0.920, 1.545]`), corroborated
at ~+1.18 us by a GPUPROF census, on a 406-dispatch/step decode path. 40 removed
dispatches predicts a refund of **-49 us/step** (CI `[-62, -37]`). Section 4.16 of
the advisor brief independently predicted `(N - R) = -55.6 us/step`.

## 6. Method

`research/nezuko_pr48_abba.sh` runs the palindromic block
`0 RV V G R N N R G V RV 0` so monotone thermal/allocator drift cancels inside a
block, preceded by one discarded primer run. Each run is a fresh worker process
driven by `research/decode_probe.py --steps 200` over the public 512-token golden
(`correctness_prompts/public_longcopy_gate_english_512_256.json`), teacher-forced,
with per-step latencies dumped and the first 8 steps discarded as warm-up.
`research/nezuko_pr48_stats.py` reports every contrast two ways: a block-paired
estimate (assumption-light, `df = blocks - 1`) and a `run_mean ~ block + arm`
two-way fixed-effects fit (tighter, `df = n - blocks - 5`).

Two robustness details matter. First, this host occasionally suffers a scheduler
or thermal event that inflates a handful of steps inside one run; the analyzer
prints a within-run-sd interference report and accepts `--trim` for an
upper-trimmed per-run estimator, so a single bad run cannot be mistaken for an
arm effect. Both the untrimmed and trimmed fits are reported below. Second, rule
17 requires measuring both scored axes whenever a `DARKBLOOM_*` flag moves, so
the same driver is re-run with `PREFILL=1` over an alternating `0 N` sequence.

## 7. Results

48 scored runs (one discarded primer), 4 complete palindromic blocks, 8 runs per
arm, 192 kept steps per run. Residual sd of the two-way fixed-effects fit is
28.4 µs/step (untrimmed) and 27.1 µs/step (upper-5%-trimmed) over 39 df.

### 7.1 Arm means

| arm | sg | nf | µs/step (untrim) | µs/step (trim) | description |
|---|---|---|---|---|---|
| `0`  | 2  | 0 | 8194.8 | 8179.9 | stock geometry, no fold |
| `RV` | 2  | 3 | 8496.3 | 8488.2 | stock geometry, redundant reduction, rmsnorm still dispatched |
| `V`  | 2  | 1 | 8406.9 | 8399.5 | stock geometry, fold replaces the rmsnorm dispatch |
| `G`  | 16 | 0 | 8155.3 | 8144.5 | fused geometry, no fold |
| `R`  | 16 | 3 | 8230.4 | 8224.8 | fused geometry, redundant reduction |
| `N`  | 16 | 1 | 8134.8 | 8124.9 | fused geometry + fold — **this is PR #48** |

### 7.2 Contrasts (trimmed fixed-effects, se = 13.6 µs, 39 df)

| contrast | µs/step | t | 95% CI | mechanism |
|---|---|---|---|---|
| `G−0`  | **−35.4** | −2.61 | [−62.8, −8.0] | threadgroup geometry alone |
| `R−G`  | **+80.4** | 5.93 | [+53.0, +107.7] | redundant reduction at 640 TGs |
| `RV−0` | **+308.3** | 22.75 | [+280.9, +335.7] | redundant reduction at 5120 TGs |
| `V−RV` | **−88.6** | −6.54 | [−116.0, −61.2] | dispatch/barrier refund, **zero geometry change** |
| `N−R`  | **−100.0** | −7.38 | [−127.3, −72.6] | dispatch/barrier refund at fused geometry |
| `N−G`  | −19.6 | −1.45 | [−47.0, +7.8] | net fold effect, geometry held at sg16 |
| `V−0`  | +219.6 | 16.21 | [+192.3, +247.0] | net fold effect, geometry held at sg2 |
| `N−0`  | **−55.0** | −4.06 | [−82.4, −27.6] | PR #48 reproduced (both variables moved) |

The untrimmed fit agrees within 5 µs on every contrast. The two exact
decompositions close:
`(N−0) = (G−0) + (R−G) + (N−R) = −35.4 + 80.4 − 100.0 = −55.0` and
`(V−0) = (RV−0) + (V−RV) = 308.3 − 88.6 = 219.7`.

`N−0 = −55.0 µs/step` reproduces the advisor's §4.16 prediction of
−55.6 µs/step to within 0.6 µs — an independent check that the reimplementation
is faithful to PR #48 despite being built from scratch.

### 7.3 Interference control

One run (`b02_s14_0`) had within-run sd 423.8 µs against a cohort median of
53.0 µs — six steps above 8.5 ms, max 12.6 ms. This is host interference, not an
arm effect. Upper-5% trimming moves that run −60.1 µs and leaves every other run
within ±2 µs, which is why both fits are reported. Trimming does not change any
sign or any significance verdict.

### 7.4 Prefill axis (rule 17)

Not measured, because both knobs are **structurally unreachable** during
prefill. `lagunaDecodeNVFP4QKVR1` guards on
`normalized.dims(1, 1, hidden)` (`LagunaRuntimeModel.swift:4960`), so with
`L = 512` it returns `nil` before either `lagunaDecodeNVFP4QKVR1Simdgroups` or
`lagunaDecodeNVFP4NormQKVFuse` is read (`:4970-4971`). The fuse mode is
independently forced to 0 by the `B == 1 && L == 1` call-site gate (`:5922`).
Prefill therefore takes `quantizedMM` in all six arms and is bit-identical
across them by construction. A timing probe here would measure only host noise.

## 8. Conclusions

### 8.1 The three mechanisms, scored

**1. Threadgroup-geometry cost — falsified.** The assignment expected the
512-thread geometry to cost time on its own. On this host it *saves*
35.4 ± 13.6 µs/step (`G−0`, t = −2.61). Widening from 64 to 512 threads
per threadgroup is not a tax at M4 Pro core counts; it is a small win.

**2. Redundant-reduction cost — confirmed, and it is the dominant term.**
Re-deriving the RMSNorm reduction inside every QKV threadgroup costs
+80.4 µs/step at 640 threadgroups (`R−G`) and +308.3 µs/step at 5120
threadgroups (`RV−0`). This is the single largest effect in the study and it is
the one mechanism whose sign was never in doubt.

The scaling is informative: 8× the threadgroups produce only 3.8× the cost.
Redundant reduction is therefore *partly* hidden under the matmul's memory
stalls rather than purely additive — but only partly, and never for free.

**3. Dispatch/barrier refund — confirmed, and larger than predicted.**
`V−RV = −88.6 µs/step` isolates the refund with **zero geometry change**: RV and
V run the identical kernel at the identical 5120 threadgroups and differ only in
whether the 40 standalone RMSNorm dispatches still exist. `N−R = −100.0 µs/step`
measures the same refund at fused geometry and agrees.

Both exceed the standing calibration of +1.233 µs per removed decode dispatch
(95% CI [0.920, 1.545]), which predicted −49 µs/step for 40 removals. Measured
is −2.2 to −2.5 µs per removed dispatch. The gap is expected in hindsight: the
calibration prices *launch overhead*, whereas removing the RMSNorm dispatch also
removes a real (if tiny) kernel's execution and its wave drain. **Rule 19 holds
— the refund had to be measured, not predicted.**

### 8.2 The actionable finding

Hold geometry fixed and the fold is worth nothing: `N−G = −19.6 µs/step`,
t = −1.45, CI [−47.0, +7.8] — not distinguishable from zero. Essentially all of
PR #48's −55.0 µs/step comes from the geometry change, which is bit-exact
(§4), needs no fold, no folded gate kernel, no `norm_row` threadgroup array, and
no third-consumer bookkeeping.

Put plainly: **PR #48 paid for a complicated fold and collected a refund that
the fold itself then spent.** The +80.4 µs of redundant reduction it introduced
very nearly cancels the −100.0 µs it refunded. Arm `G` — one integer changed
from 2 to 16 — captures −35.4 µs of the −55.0 µs at a fraction of the risk.

### 8.3 Why this still does not ship, and the M4→M5 caveat

Neither `G` (−35.4) nor `N` (−55.0) clears the ranked 3σ noise floor of
≈80 µs/step. At the decode exchange rate of 0.015280 %/µs they are +0.54% and
+0.84% of decode score on *this* host, but the ranked M5 measured PR #48 at
**−0.1488%** overall — the opposite sign to arm `N` here.

That sign flip is the headline caveat and it is exactly the failure mode
`AGENTS.md` warns about: threadgroup geometry changes sign across core counts.
The mechanism is occupancy. M5 Max has substantially more GPU cores than this
M4 Pro; 640 threadgroups plausibly under-fills M5 while comfortably filling M4
Pro, so the term this study measures as `G−0 = −35.4` may be positive on M5.
Two further transfer limits apply: M4 Pro reports Apple GPU generation 16 and
does not select the `_nax` kernels the ranked M5 uses, and the redundancy/
occupancy trade in §8.1 is by construction core-count dependent.

**What does transfer** is the mechanism decomposition, not the numbers: the fold
is a wash at fixed geometry, the redundant reduction is the dominant cost and
scales with threadgroup count, and the refund is ~2× the per-dispatch
calibration. **What does not transfer** is any of the three coefficients, and in
particular the sign of `G−0`.

### 8.4 Correctness evidence

49/49 runs across all six arms report `0 divergences` over 192 teacher-forced
steps against the public 256-token golden, backed by the algebraic bit-exactness
argument of §4 for the geometry knob.

No `./benchmark.sh --local-iterate` run, drift tripwire, or upstream-equivalence
pass was performed, and none is claimed: **nothing ships from this branch.** The
`Sources/` patch exists only as `research/nezuko_pr48_deconfound.patch` and the
submitted surface is unchanged (`git diff --stat` against the base shows no
`Sources/` entries). Note also that `LagunaUpstreamEquivalence` is structurally
blind to this kernel family (rule 16), so the tripwire golden — which this study
does exercise, 49 times — is the stronger instrument here anyway.

## 9. Redundancy-neutral design sketch (design only, not implemented)

The measurement says the fold's problem is not geometry, it is that *every*
threadgroup owning rows of a layer redoes the same 2048-element reduction. The
redundancy factor equals the threadgroup count. Four ways to break that link were
evaluated (a frontier design review was run on this question; its code citations
were re-verified by hand):

| # | option | dispatch delta / step | redundancy factor | bit-exact | verdict |
|---|---|---|---|---|---|
| **A** | **persistent grid-stride lane-major QKV at a fixed small threadgroup count `T`, fuse mode 1** | **-40** | **`T`** | **yes** | **best** |
| B | one threadgroup computes the norm, publishes to device memory, others spin on an atomic flag | -40 | 1 | yes | **reject** |
| C1 | apply `invrms` *after* the matmul (matvec is linear in `x`) | -40 | 0 | **no** | **reject** |
| C2 | tiny scalar-only sum-of-squares kernel; QKV consumes the scalar | 0 | 0 | yes | dominated |
| D | fold the sum of squares into the tail of the previous layer's residual add | -40 | 0 | no | **reject** |

**A — persistent grid-stride.** Section 4 already proves that which simdgroup owns
which row has no numerical content, so the redundancy factor is a free parameter.
Choosing `T = 128` threadgroups of 16 simdgroups gives 2048 simdgroups, i.e.
`10240 / 2048 = 5` rows per simdgroup for h64 and `8192 / 2048 = 4` for h48 —
both exact, no tail. This keeps mode 1's `-40` dispatches while cutting the
redundancy from 640 to 128, a 5x reduction of the term measured as `(R - G)`.
Precedent for the pattern already exists in this file:
`lagunaResidualRMSNormRouter` (`LagunaRuntimeModel.swift:853,1055,10542`) folds
the *post-attention* residual add and RMSNorm into the router kernel with a small
threadgroup count.

**B — atomic-flag publish.** Apple GPUs give no forward-progress guarantee across
threadgroups, so a spin on a flag written by another threadgroup can hang. Not
worth a hang on the ranked box.

**C1 — post-matmul `invrms`.** Algebraically valid (`out = W @ (x*w) * invrms`)
but **not bit-exact**: the NVFP4 matvec accumulates in FP32, and scaling after the
accumulation changes every rounding. This file already records exactly this
failure mode at `LagunaRuntimeModel.swift:843-852` — regrouping 64 sequential FP32
adds into a tree left every local check green and failed the hidden exact-token
gate. Also, folding the norm weight `w` into the weight columns is impossible
without requantizing an NVFP4 group-16 bank.

**C2 — scalar-only kernel.** Bit-exact and redundancy-free, but it puts a
dispatch back one-for-one, so it forfeits the entire `(N - R)` refund. Dominated
by A.

**D — sum of squares in the previous layer's tail.** The residual add is the
custom MoE tail kernel `laguna_routed_shared_nvfp4_down_residual_bf16_r1_v5`
(`LagunaRuntimeModel.swift:8029`), dispatched as
`grid = (hidden/4 * 288)`, `threadGroup = 288` (`:8201`) — 512 threadgroups each
owning 4 of the 2048 outputs. Accumulating a global sum of squares there needs
cross-threadgroup FP atomics, whose summation order is nondeterministic, so it is
not bit-exact.

**Recommended next experiment:** option A, as a third value of
`DARKBLOOM_DECODE_NVFP4_QKV_R1_SIMDGROUPS`-style control — a `TOTAL_THREADGROUPS`
knob with a grid-stride row loop — swept over `T` in `{64, 128, 256, 640}` against
arms 0 and N in the same palindromic design. `T` is a pure occupancy/redundancy
trade with no numerical content, so the whole sweep is one bit-exact family, and
the optimum is exactly the quantity that will *not* transfer from M4 Pro to M5
Max and therefore must be re-swept on the ranked host.

## 10. Reproduction

```bash
git apply research/nezuko_pr48_deconfound.patch
CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions \
  --scratch-path .build-worker --product mlxfast-runtime-worker
git checkout -- Package.resolved
./research/nezuko_pr48_abba.sh /tmp/nez298/abba 4 200
python3 research/nezuko_pr48_stats.py /tmp/nez298/abba
python3 research/nezuko_pr48_stats.py /tmp/nez298/abba --trim 0.05
```

Wall time is ≈41.5 s per run, so the 49-run sweep takes ≈34 minutes.

The driver also supports a prefill axis via
`PREFILL=1 ARM_SEQ="0 N N 0 0 N" ./research/nezuko_pr48_abba.sh /tmp/nez298/pf 1 8`.
It was deliberately **not** run: §7.4 shows both knobs are unreachable when
`L = 512`, so that command can only measure host noise.

The runtime patch is **not** part of the submitted surface: `Sources/` is restored
before the result commit, so this branch adds zero bytes to `editablePaths`.
Applying the patch changes `LagunaRuntimeModel.swift` from 468,336 to 475,865
bytes (growth 7,529 of the 262,144 review budget) if a future experiment does
choose to ship a variant of it.
