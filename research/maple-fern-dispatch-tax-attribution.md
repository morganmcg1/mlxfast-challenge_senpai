# Attributing the decode "dispatch tax" (PR #268, maple-fern)

**Status:** DRAFT — numbers below marked `TBD` are filled from the full
battery in `/tmp/fern268`. Smoke-run numbers are labelled as such.

**Host:** Apple M4 Pro, 20 GPU cores, 48 GiB, macOS 26.5.2, Metal 4, Apple GPU
generation 16. **This is not the ranked host.** It never selects the `_nax`
kernel variants the ranked M5 Max uses, and its decode step is ~2x the M5's.
Every microsecond here is directional, not rankable.

**Workload:** the real teacher-forced golden decode — 512-token seed, one-token
steps — driven through the scored runtime, not a microbenchmark.

---

## 0. The question

PR #241 measured, off the critical path, "something like 1.4 µs per dispatch"
in decode. That number is the entire justification for the fusion programme:
if it is real and refundable, removing dispatches is the primary decode
direction; if it is an artefact, the programme is a mirage.

Two hypotheses:

* **H-MECH** — the tax is dominated by exactly one identifiable mechanism.
* **H-REFUND** — removing one dispatch from the live decode chain refunds
  ≥ 1.0 µs of wall-clock step time.

Candidate mechanisms:

| id | mechanism | signature if true |
|----|-----------|-------------------|
| E1 | CPU-side per-op encode starving the GPU | cost appears in the commit→complete **gap**, and tracks CPU work |
| E2 | GPU command-processor fixed launch cost | cost appears in **GPU-busy** time and tracks dispatch count |
| E3 | cache flush/invalidate scaling with dirty footprint | cost scales with **bytes** touched per dispatch |
| E4 | residency/bookkeeping scaling with distinct resources | cost scales with the number of **distinct buffers** live |
| E5 | command-buffer commit overhead | already refuted in PR #241 |

## 1. Instrument

Two patches, applied only to build the research worker and never committed to
`Sources/` or `Vendor/` (see §7):

* `research/fern_tax_device_counters.patch` →
  `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp`.
  Counts `maybeInsertBarrier`, `dispatch_threadgroups`, `dispatch_threads`,
  `end_encoding`, `commit`, and accumulates per-command-buffer
  `GPUStartTime→GPUEndTime` (**gpu_ns**, GPU busy),
  `kernelStartTime→kernelEndTime` (**kernel_ns**, the CPU driver's own work)
  and `commit→completion` (**span_ns**). Exposed as one `extern "C"` read.
* `research/fern_tax_inject.patch` → `Sources/MLXFastModel/LagunaRuntimeModel.swift`.
  Adds `enum LagunaTaxProbe`, driven entirely by environment variables and
  defaulting to `mode=none`, which injects K extra dispatches per decoder layer
  at a live site, in several *shapes*.

The shapes are the experiment:

| mode | what it injects at each of the 40 layers | dispatches | barriers |
|------|------------------------------------------|-----------|----------|
| `chain40` | K dependent scalar multiplies, anchored in front of a live consumer | +K·40 | +K·40 |
| `fat40`   | K dependent adds, each re-reading one buffer of `--bytes` | +K·40·1.5 | same as dispatches |
| `dist40`  | as `fat40` but each add reads a **different** buffer from a pool of `--pool` | same as `fat40` | same |
| `fan40`   | K **mutually independent** slices of a live tensor, joined by one concat | same as `fat40` | **half** |
| `spin40`  | pure CPU busy-spin at the same 40 positions, no GPU work | 0 | 0 |
| `chain`/`indep`/`distinct`/`diamond1` | the same dispatch counts issued **off** the live chain | matched | varies |

`anchor=1` splices the injected value back into the live tensor as `x + (t - t)`,
so it is a true data dependency; `anchor=0` issues the identical dispatches with
no live dependency. That switch is the cleanest single contrast in the battery.

**Numerics.** The splice is exactly zero-preserving for finite inputs, and every
arm reported here ran the full golden teacher-forced decode with a per-step token
check: **0 divergences in every arm**. (Caveat: `a - a` would produce NaN on a
non-finite `a`, and `x + 0` flips `-0` to `+0`. Neither fired.)

## 2. Estimator

One reducer, `research/fern_tax_stats.py`, used for every number in this
document and for everything logged to W&B (`research/fern_tax_wandb.py` calls
its `fit()` rather than re-deriving points — PR #241 shipped two reducers that
disagreed by ~6% because they centred contrasts differently).

* unit of replication = one **segment median** (first `--drop` steps discarded)
* the K schedule is **palindromic** (`0,1,2,4,4,2,1,0`) and repeated `--blocks`
  times, so a monotone thermal/clock drift inside a block cancels
* both x and y are centred on their **block mean** before the slope is formed,
  so no arm acts as a privileged reference
* CI = classical OLS t interval on df = n_segments − n_blocks − 1
* passing several TSVs pools them with a **(file, block)** fixed effect, and
  prints each arm's own slope beside the pooled line — an arm off the pooled
  line falsifies that regressor

## 3. Baseline decode step on this host

| quantity | value |
|---|---|
| wall / step | 8.18 ms |
| dispatches / step | 406 |
| barriers / step | 247 |
| commits (command buffers) / step | 67–68 |
| encoders / step | 75–76 |
| GPU busy / step (`GPUEndTime−GPUStartTime`, summed) | 7.95 ms |
| GPU span / step (`min start → max end`) | 8.03 ms |
| CPU driver / step (`kernelEndTime−kernelStartTime`, summed) | 0.60 ms |
| GPU-busy fraction of wall | 0.971 |

Per layer that is 406/40 ≈ **10.2 dispatches** and 247/40 ≈ **6.2 barriers**.
The command-buffer partition (67–68 commits, 75–76 encoders) is stable to
±1 across every arm and every K in the battery, so no arm's slope is
contaminated by MLX re-partitioning the step into a different number of
command buffers.

Two facts frame everything below:

- The GPU is busy 97.1% of the wall clock. Only 0.24 ms/step of the 8.18 ms
  is *not* inside a command buffer's GPU execution window.
- The CPU driver spends 0.60 ms/step in `kernelStart→kernelEnd`, i.e.
  1.48 µs of *host driver* time per dispatch. That number is numerically
  close to the ~1.4 µs tax and is the single most seductive false lead in
  this experiment; §4 A2/A3 kill it.

## 4. Results

### 4.1 A2 — pure-CPU spin at the same encode position (direct E1 test)

`spin40` injects `K × 1400 ns` of real busy-wait (a `DispatchTime.now()`
deadline loop, not elidable) at each of the 40 in-chain sites, and issues
**zero** extra GPU work. Dispatch/barrier/commit counters are identical at
every K, confirming the arm is purely a CPU perturbation.

| K | injected CPU µs/step | wall ms | Δwall vs K=0 | dispatch | barrier |
|---|---|---|---|---|---|
| 0 | 0 | 8.1778 | — | 406 | 247 |
| 1 | 56 | 8.1971 | +19.3 µs | 406 | 247 |
| 2 | 112 | 8.1867 | +8.9 µs | 406 | 247 |
| 4 | 224 | 8.1940 | +16.3 µs | 406 | 247 |

**FE-OLS: +0.0497 ± 0.0293 µs of wall per injected CPU µs, 95% CI
[−0.009, +0.108], t=1.7, n=48.**

A CPU-paced step (E1) predicts slope ≈ 1.0. The measured slope is
**0.05**, and 1.0 is 32 standard errors away. 224 µs/step of extra host
work — 2.7% of the whole step — is absorbed almost completely. Whatever
paces this decode step, it is not host time spent in the layer loop.

*(Caveat, carried from the pre-registered critique: MLX is lazy, so this
spin delays the graph-building thread rather than MLX's encoding thread.
It bounds host slack on the call path, not encode-thread slack. The
decomposition in §4.2 is the stronger E1 test and agrees.)*

### 4.2 A3 — where does the added time land? (E1 vs E2, per barrier)

Same arms, same fit, but the response is swapped for the GPU-side
timestamps from the command-buffer completion handler. `gap_ms` is
`span − busy`: everything between the first command buffer starting and
the last one finishing that is *not* GPU execution, i.e. exactly the place
CPU starvation would show up.

| arm | y = wall | y = GPU busy | y = gap (span−busy) | y = CPU driver |
|---|---|---|---|---|
| `chain40` | **+1.3778 ± 0.0535** | +1.3696 ± 0.0450 | +0.0067 ± 0.0177 | +0.0236 ± 0.0479 |
| `dist40_8k` | **+1.4871 ± 0.0488** | +1.4898 ± 0.0444 | −0.0237 ± 0.0131 | +0.2141 ± 0.0346 |

(µs/step per added barrier, ± standard error, n=48 each.)

- **99.4%** (chain40) and **100.2%** (dist40) of the wall-clock tax
  reappears inside GPU busy time.
- The gap slope is **statistically zero** in both arms (|t| ≤ 1.8) and its
  CI excludes anything above 0.05 µs. The GPU is never left waiting.
- CPU driver time per added dispatch is 0.02–0.21 µs, **7–60× smaller**
  than the wall cost. The 1.48 µs/dispatch of baseline host driver time
  noted in §3 is real but is fully hidden behind GPU execution — it is a
  coincidence of magnitude, not the mechanism.

**E1 is refuted.** The tax is spent by the GPU, inside command buffers.

### 4.3 A1 — the tax is a *barrier* cost, not a *dispatch* cost

This is the central result and it changes what the number means.

Four in-chain arms add K units of work at the same 40 anchored sites, but
with different dependency structure, so they add barriers and dispatches in
different ratios:

| arm | what each unit is | Δdispatch @K=1/2/4 | Δbarrier @K=1/2/4 |
|---|---|---|---|
| `chain40` | `y = y * one`, K times, strictly serial | +40 / +80 / +160 | +40 / +80 / +160 |
| `fat40_8k` | K serial 8 KiB reductions off one buffer | +120 / +160 / +240 | +120 / +160 / +240 |
| `dist40_8k` | same, over a 256-buffer pool | +120 / +160 / +240 | +120 / +160 / +240 |
| `fan40` | K **mutually independent** anchored slices | +80 / +160 / +240 | +80 / +120 / **+120** |

Three of the four arms add barriers and dispatches in exactly 1:1, so they
cannot separate the two. `fan40` can: its added kernels are mutually
independent, so MLX only needs a barrier in front of the group, and between
K=2 and K=4 its barrier count stops growing while its dispatch count keeps
going.

Per-arm single-regressor fits, y = wall (µs/step):

| arm | per **dispatch** | per **barrier** |
|---|---|---|
| `chain40` | +1.3778 ± 0.0535 | +1.3778 ± 0.0535 |
| `fat40_8k` | +1.3469 ± 0.0593 | +1.3469 ± 0.0593 |
| `dist40_8k` | +1.4871 ± 0.0488 | +1.4871 ± 0.0488 |
| `fan40` | **+0.8020 ± 0.0581** | **+1.5582 ± 0.0658** |

Pooling all four with a (file, block) fixed effect and asking whether *one*
slope explains every arm:

| regressor | pooled slope | arms off the line |
|---|---|---|
| **barrier** | **+1.4266 ± 0.0282** (t=50.6, n=192) | **none** |
| dispatch | +1.2261 ± 0.0352 (t=34.9, n=192) | `dist40_8k`, `fan40` |

Read as a *dispatch* cost the arms disagree by 1.9× (0.80 → 1.49) and two of
four fall off the pooled line. Read as a *barrier* cost they agree within
15% (1.35 → 1.56) and all four sit on it.

The cleanest single piece of evidence is a within-arm contrast in `fan40`
that needs no pooling and no modelling at all:

| `fan40` K | dispatch | barrier | wall ms |
|---|---|---|---|
| 2 | 566 | 367 | 8.3631 |
| 4 | **646** (+80) | **367** (+0)| 8.3804 (+17.3 µs) |

**80 extra GPU dispatches, anchored to the live tensor, at the same encode
position, adding no barrier, cost 17.3 µs — 0.216 µs each.** The same 80
dispatches in `chain40` (where each one adds a barrier) cost 110 µs.

Pricing both regressors in one fixed-effects fit (`--joint`), pooled over
the four arms:

| regressor | µs/step | 95% CI | t |
|---|---|---|---|
| **dispatch** (barrier-free) | **+0.173** ± 0.085 | [+0.007, +0.339] | 2.0 |
| **barrier** | **+1.241** ± 0.095 | [+1.054, +1.427] | 13.0 |

`fan40` alone identifies the same split independently (dispatch
+0.137 ± 0.087, barrier +1.330 ± 0.158, n=48), because its
barrier-per-dispatch ratio collapses between K=2 and K=4.

**So the ~1.4 µs "per dispatch" is really 1.24 µs of barrier plus 0.17 µs
of launch.** The tax has been misnamed: 88% of it is the cost of a
*dependency edge*, not the cost of a *dispatch*.

### 4.4 Anchoring control — the barrier is charged even off the critical path

`fat40_8k_free` is `fat40_8k` with `DARKBLOOM_TAX_ANCHOR=0`: identical work at
identical encode positions, but the injected chain never feeds back into the
residual stream, so none of it is on the data-dependency path from this token's
input to this token's logits. MLX still emits the kernels, and — because they
alias the same scratch buffer — still emits barriers, but the barrier count no
longer tracks K:

| `fat40_8k_free` K | dispatch | barrier | wall ms | Δ vs K=0 |
|---|---|---|---|---|
| 0 | 406 | 247 | 8.1754 | — |
| 1 | 446 (+40) | 287 (+40) | 8.2486 | +73.2 µs |
| 2 | 486 (+80) | 287 (**+40**) | 8.2456 | +70.2 µs |
| 4 | 566 (+160) | 301 (+54) | 8.2664 | +91.0 µs |

The K=1→K=2 step is a second model-free contrast, in a different arm and a
different dependency regime from `fan40`, and it says the same thing:
**40 additional GPU dispatches that add no barrier cost −3.0 µs, i.e.
nothing.** The K=2→K=4 step adds 80 dispatches and 14 barriers for +20.8 µs,
or 1.49 µs per barrier with dispatches free.

Single-regressor fits: +0.478 ± 0.075 µs per dispatch (arms disagree),
+1.719 ± 0.155 µs per barrier. The joint fit on this arm alone gives
dispatch **−0.074 ± 0.101** (indistinguishable from zero) and barrier
**+1.903 ± 0.296**.

Two things follow. First, the per-barrier price does **not** fall when the
injected work leaves the critical path — if anything it is higher here than
in-chain (1.90 vs 1.24 µs). A barrier is an intra-encoder
`memoryBarrier(BarrierScopeBuffers)`; it serializes *everything already
encoded in that command encoder*, so it is charged against the whole step
regardless of whether the tensor that caused it is live. Second, adding
`fat40_8k_free` to the pooled joint fit sharpens rather than moves it:

| joint fit, 5 arms (n=240, blocks=30, df=208) | µs/step | 95% CI | t |
|---|---|---|---|
| dispatch (barrier-free) | **+0.120** ± 0.061 | [+0.001, +0.240] | 2.0 |
| barrier | **+1.299** ± 0.073 | [+1.157, +1.442] | 17.9 |

## 5. Verdict on E1–E4

TBD

## 6. Decision rule

**H-REFUND holds, for the fusion of *dependent* kernels.** Fusing two kernels
that are joined by a data dependency removes one dispatch *and* one barrier,
so it refunds

```
0.120 (dispatch) + 1.299 (barrier) = 1.42 us/step  [conservative pooled joint fit]
0.173 (dispatch) + 1.241 (barrier) = 1.41 us/step  [4-arm in-chain joint fit]
```

on this host, comfortably above the 1.0 µs bar the assignment set. But the
refund is *not* proportional to dispatches removed. Three different fusions
that all remove "one dispatch per layer" refund three very different amounts:

| what the fusion removes per layer | refund µs/step (×40 layers, this host) |
|---|---|
| 1 dependent pair → 1 dispatch **and** 1 barrier | **56.8** |
| 1 barrier only (make two siblings concurrent, keep both dispatches) | **52.0** |
| 1 barrier-free dispatch (fuse two already-co-encoded siblings) | **4.8** |

Projecting the barrier term to the ranked M5, using the 1.000× (fixed
overhead) to 0.506× (scales with step time) transfer band and
0.015280 % of score per µs of decode step:

| barriers removed per step | µs/step on M5 | % score | σ (15.34 µs) |
|---|---|---|---|
| 1 per layer (×40) | 28.9 .. 57.1 | 0.441 .. 0.872 | 1.9 .. 3.7 |
| 3 per layer (×40) | 86.6 .. 171.2 | 1.323 .. 2.616 | 5.6 .. 11.2 |
| 10 per layer (×40) | 288.6 .. 570.7 | 4.410 .. 8.720 | 18.8 .. 37.2 |

So the operational rule for the decode programme is:

1. **Count barriers, not dispatches.** MLX inserts one intra-encoder
   `memoryBarrier` when the next op RAW/WAR-conflicts with anything encoded
   since the last barrier, and inserting it *resets* that conflict set
   (`device.cpp:323-375`). Barriers therefore count **waves** of
   mutually-non-conflicting work, not dependency edges. The decode step runs
   406 dispatches in 247 waves; per layer that is 10.2 dispatches in 6.2
   waves. **A fusion that does not reduce the wave count buys ≈ 0.12 µs and is
   not worth its risk.**
2. **The unit of profit is a *dependent* pair.** Fusing sibling kernels that
   already co-encode into the same wave (e.g. router top-8 into the router
   GEMV, or the shared expert into the routed gate/up) removes zero barriers
   and is worth ~0.1 µs per site. Fusing a producer into its consumer removes
   a wave and is worth ~1.4 µs per site.
3. **Prefer fused kernels over dispatch-side tricks.** Indirect command
   buffers, CPU/GPU encode overlap, and command-buffer batching all attack the
   0.12 µs launch term and the 0.60 ms CPU driver time that already hides
   under a 0.971 GPU-busy fraction (§3, §5/E1). They cannot touch the 1.3 µs
   barrier term, which is inside GPU-busy time.
4. **Ceiling check before building.** The per-layer wave budget is roughly
   `{input norm} {QKV, router-gate} {fused attention} {o_proj}
   {residual+post-norm+router} {top-8, routed gate/up, shared gate/up}
   {down+combine+residual}` = 7 waves, matching the 6.2 measured. The
   realistically fusable dependent pairs are the input RMSNorm into the QKV
   GEMV, and attention output into `o_proj`. At 1 wave per layer each that is
   0.44–0.87 % of score apiece on M5, and the RMSNorm→QKV fusion is the one
   with an existing kernel precedent (the INT8 g32 bank already has the fused
   form; the NVFP4 path declines it at
   `Sources/MLXFastModel/LagunaRuntimeModel.swift:5738-5745`). **A realistic
   near-term ceiling for this direction is ~0.9 % of decode, not the ~4 %
   implied by "406 dispatches × 1.4 µs".**
5. **`start_concurrent()` is out of reach.** The obvious way to delete a
   barrier without deleting a kernel is MLX's concurrent-encoding escape hatch
   (`device.h:33-46`, `device.cpp:343-345`), which today has exactly one user
   (`concat_gpu`, `slicing.cpp:35`). `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp`
   is **not** in `benchmark.json`'s `editablePaths`, so the barrier machinery
   itself cannot be changed by a submission. Only the kernel sources,
   `matmul.cpp`, `jit_kernels.cpp`, `kernels.h`, `quantized.cpp` and their
   `mlx-generated/*.cpp` twins are editable. This is why the answer is
   **(A) fuse dependent kernels**, not (B) restructure dispatch.

## 7. Scope

No submitted paths. Everything in this experiment is research-only:

* `research/maple-fern-dispatch-tax-attribution.md` (this file)
* `research/fern_tax_probe.py`, `research/fern_tax_stats.py`,
  `research/fern_tax_wandb.py`, `research/fern_tax_campaign.sh`
* `research/fern_tax_inject.patch`, `research/fern_tax_device_counters.patch`

`git diff <base>..HEAD -- Sources Vendor benchmark.json` is empty. The
instrumented worker is built by applying the patches, building
`mlxfast-runtime-worker` into `.build-worker`, and then reverting the tree, so
the instruments exist only in a binary and never in the submitted surface.
Note that editing anything under `Vendor/mlx-swift/Source/Cmlx/{mlx,mlx-generated}`
changes the tree hash that `Sources/MLXFastTrustedHarness/VendoredMetalFingerprint.swift`
computes, so the trusted harness must not be run against a patched tree without
first re-running `tools/build-mlx-metallib.sh`.

## 8. Caveats

Ordered by how much they could change the verdict.

1. **The 1.4 µs has never been measured on the ranked M5.** Every number here
   is M4 Pro, Apple GPU generation 16, which never selects the `_nax` kernel
   variants. The transfer band (§6) brackets the two extreme assumptions
   rather than resolving them. The *sign* and the *decomposition* should carry
   — they are about how MLX partitions an encoder, which is architecture
   independent — but the magnitude is directional only.
2. **`spin40` bounds host slack on the graph-build thread, not MLX's encode
   thread.** MLX is lazy: the Swift call that `spin40` delays is graph
   construction, and the actual Metal encoding happens later inside `eval`.
   So §4.1 shows that the *call path* has ≥ 224 µs/step of slack, which is not
   quite the same statement as "the encode thread has slack". §4.2 is the
   stronger E1 test and it agrees: 99–100 % of the added wall time lands in
   GPU-busy, and the commit→complete gap slope is statistically zero. Note
   also the seductive coincidence that killed a day: baseline CPU driver time
   / dispatches = 0.60 ms / 406 = 1.48 µs, almost exactly the tax. It is a
   coincidence; the CPU time is not on the critical path.
3. **Barriers count waves, not edges, so "remove a barrier" is a claim about
   MLX's encoder partition, not about the model graph.** Inserting a barrier
   resets `prev_outputs_`/`prev_inputs_` (`device.cpp:363-375`), so a fusion
   that deletes a dependency edge only saves a barrier if that edge was the
   *first* conflict in its wave. §6's per-layer wave budget is my reading of
   the trace, not a proof; a fusion candidate should be re-counted with the
   `TAXCTR` instrument before it is built.
4. **Injected-work realism.** The injected units are cheap elementwise or
   small-reduction kernels. A real fused kernel replaces two *large* kernels,
   and the wave it deletes may have been partly hidden behind other work. The
   1.4 µs is therefore an upper bound on what one real fusion refunds, and the
   §6 ceiling should be read as optimistic.
5. **Splice numerics.** The anchor is `x + (t − t)`, which is bit-exact for
   finite `t` but maps −0 → +0 and would produce NaN for non-finite `t`. All
   17 arms ran the teacher-forced golden with **0 divergences** at every K, so
   this did not bite, but it means the arms are not literally identity
   transformations of the graph.
6. **The off-critical-path comparators understate cost.** `chain`, `indep`,
   `distinct` and `diamond1` inject at a batch boundary rather than inside a
   layer, where the injected work can overlap with real work. Their slopes are
   reported for completeness but the in-chain site arms are the ones the
   verdict rests on.
7. **Thermal drift and command-buffer partition.** Both are controlled rather
   than assumed: the K schedule is palindromic (`0,1,2,4,4,2,1,0`) inside each
   of 6 blocks and the estimator carries a per-block fixed effect, and commit
   and encoder counts were recorded for every arm at every K (67–68 commits,
   75–76 encoders, stable ±1 everywhere). No arm repartitions the stream, so
   E5 stays refuted.
8. **No prior art to calibrate against.** I could find no published
   per-dispatch or per-barrier microsecond figure for Apple M-series Metal.
   The nearest reference points are MLX PR #1773 (MTLFence 15–20 µs vs
   MTLSharedEvent 150–200 µs for *inter-encoder* sync — two orders of
   magnitude above the intra-encoder barrier measured here), wgpu#7712's
   ~48 µs empty-command-buffer floor, and the anukari devlog's ~50 µs
   per-encode figure. All of those are command-buffer-scale costs, consistent
   with this step's 67 commits being the expensive part of the *fixed*
   overhead and the barrier being the marginal one.
