# PR #48 — Fusing the 40 input RMSNorms and 40 per-head gate dispatches into the R1 QKV kernel

`assignment_id` `maple-2026-08-05d-fused-norm-qkv-gate`, `revision_id` `r1`,
student maple-fern. Base accepted
`90bbc33d25dabbb08dc41bad0b96d74a8e57a3eb`.

Base advanced twice while this arm was open (`1849b376` → `d267ebda` →
`90bbc33d`). I ran the intersection myself under the standing rule: **4 files
changed since `1849b376`, all under `research/` (`BRIEF_QUEUED_SLIDING_ATTN_REWRITE.md`,
`CURRENT_RESEARCH_STATE.md`, `GATHER_GEMM_REGIME_DESIGN.md`,
`RESEARCH_IDEAS_2026-08-05_15:35.md`), editable intersection 0** ⇒ accepted
without rebase or re-run. `git merge-base 90bbc33d HEAD` = `1849b376`, so
attribution is clean.

Host for every local number below: **Apple M4 Pro, 20 GPU cores, 48 GiB, macOS
26.5.2, Apple GPU generation 16 (not `_nax`-capable).** No M5 receipt was taken
for this arm; Step 4 was not authorised.

**Evidence contract.** This programme has **no W&B runs**. Every number here is
either a local measurement on the host above, or a citation to a ranked
`mlxfast` receipt ID or a `research/*.md` path.

---

## 0. Headline

Steps 1, 2 and 3 are all complete and bit-exact. The decode dispatch count
drops **406 → 326, exactly −80**, satisfying the assignment's hard stop.

But the arm produced one result I did not expect, and I think it matters more
than the fusion itself. I instrumented MLX's in-encoder barrier logic and
counted, per decode step, how many `memoryBarrier(BarrierScopeBuffers)` calls
the three modes actually emit:

> **80 dispatches were deleted, but only 40 barriers were deleted — and the
> split is grossly asymmetric.** The norm fold accounts for **39 of the 40**
> (243 → 204 barriers for −40 dispatches). The gate fold accounts for **1**
> (204 → 203 barriers for another −40 dispatches).

Barrier counts are host-computed from buffer aliasing in the op stream, so under
the **M4 TRANSFER LAW** they are *counts* and transfer to M5 exactly. The
counts themselves are solid and internally consistent (barrier + no-barrier
totals land on 406/366/326 to the integer, independently reproducing nezuko's
406).

What the counts do **not** determine is *which kernel owned each barrier*. I
first read the −39/−1 split as "`gate_sp` was already concurrent, so the gate is
only ≈15 % of the prize". A frontier adjudication of that claim against
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp` showed it is
**one of two models that fit the same six aggregates**, and that the *other*
model is the one favoured by mode 1's dataflow (§4.3). I withdraw the "the gate
is 15 % of the prize" number.

What survives, and is model-free, is the negative half:

> **The brief prices both folds at summed GPU-timeline duration —
> 40 × 0.87 µs + 40 × 5.32 µs — and that pricing is unsupported in either
> direction.** Barrier counts *rebalance* under folding (removing a producer
> rotates its consumer's barrier away rather than deleting it), so a 2:1
> dispatch deletion buying a 39:1 barrier deletion is direct evidence that the
> two folds are **not** interchangeable at `c` µs per dispatch. The true
> marginal cost of the gate dispatch could be near zero (fully shadowed by the
> 640-threadgroup QKV kernel it now rides inside) or could exceed the summed
> duration on a higher-core-count part.

I am not asking you to substitute a number of mine for yours — I no longer have
one. I am asking you to notice that the per-call price in the brief has no
support from the only mechanism-level measurement anyone has taken on this path,
that mode 1 and mode 2 are separable by one character in the source, and that
this makes #48 a *discriminating* receipt rather than a confirmatory one.

---

## 1. What shipped

One submitted file: `Sources/MLXFastModel/LagunaRuntimeModel.swift`.
`senpai/validate-assignment-scope.sh` → scope OK, 1 submitted path.

Two env-gated controls, **both identity by default**:

| control | env | values | default |
|---|---|---|---|
| `lagunaDecodeNVFP4QKVR1SIMDGroups` (`:4615`) | `DARKBLOOM_DECODE_NVFP4_QKV_R1_SIMDGROUPS` | 1,2,4,8,16 | **2** (= stock geometry) |
| `lagunaDecodeNVFP4NormQKVFuseMode` (`:4727`) | `DARKBLOOM_DECODE_NVFP4_NORM_QKV_FUSE` | 0,1,2 | **0** (= no fold) |

Mode 1 folds the input RMSNorm into the QKV kernel and still exports the
device-visible `normalized` row. Mode 2 additionally folds the per-head
`g_proj` + softplus, so `normalized` is never materialised.

**The committed default is a no-op.** Merging this PR ships zero behavioural
change; the mechanism is unpriced until a ranked receipt exists. Step 4 is a
one-character change: the `0` in `lagunaDecodeNVFP4NormQKVFuseMode`'s fallback
at `:4727` becomes `2`.

New/changed symbols: `lagunaDecodeNVFP4QKVR1Body(orow:input:)` `:4628` and
`lagunaGateSoftplusBody(orow:input:)` `:4309` (extracted from the existing
sources so the fused kernel can re-emit the *same* MSL text with a different row
map — the extraction is byte-identical for the standalone kernels);
`lagunaDecodeNVFP4NormQKVSource(heads:foldGate:)` `:4739`;
`lagunaDecodeNVFP4NormQKVKernels` `:4809`;
`lagunaDecodeNVFP4NormQKV(...)` `:4833`; call site `:5759-5810`.

---

## 2. Step 1 — geometry widening alone (M4 admissible)

Only knob: simdgroups per threadgroup in the R1 QKV kernel. `constexpr uint
num_simdgroups` and the grid/threadgroup shape change; the K loop, the
`column = simd_lid * 16` map and the deferred `× 4194304` epilogue are
untouched, so this is bit-exact by construction.

**Threadgroups per layer — the integer the prior negative cares about:**

| layer class | bank rows | TGs at N=2 (stock) | TGs at N=16 |
|---|---:|---:|---:|
| sliding, h64 | (64 + 2·8)·128 = 10240 | 5120 | **640** |
| full, h48 | (48 + 2·8)·128 = 8192 | 4096 | **512** |

An 8× reduction. `:5554-5557`'s recorded cause of the +2.7 % prior negative was
"a naive fold recomputes the 2048-element reduction 5120 times per layer". At
N=16 it recomputes it 640 times, and mode 1/2 amortise it to **once per
threadgroup** — 640 reductions per h64 layer instead of 5120 or 10240.

**Single-pass sweep, 128 steps, 0 divergences at every N** (mean/median ms/step):

| N | 2 | 4 | 8 | 16 |
|---|---|---|---|---|
| mean | 8.558 | 8.541 | 8.530 | 8.555 |
| median | 8.541 | 8.534 | 8.523 | 8.521 |

**12 × 512-step interleaved paired screen, N=16 vs stock** (fresh process per
arm, warm-up discarded, 24 arms, 0 divergences;
`research/maple_fern_pr48_paired.py`, log `/tmp/paired_step1.log`):

| statistic | control | candidate | Δ | Δ% | sd(d) | paired t (n=12) |
|---|---:|---:|---:|---:|---:|---:|
| mean | 8.6103 | 8.5909 | −0.0193 | −0.225 % | 0.0383 | **−1.746** (n.s., t_crit 2.201) |
| median | 8.6016 | 8.5911 | −0.0105 | −0.122 % | 0.0125 | **−2.900** (sig.) |
| min | 8.6085 | 8.6154 | +0.0069 | +0.083 % | — | +0.282 |

Per-pair mean deltas: −0.1190 +0.0160 +0.0360 −0.0080 +0.0020 −0.0220 −0.0020
−0.0230 −0.0140 −0.0360 −0.0160 −0.0460.

**Conclusion.** Widening the geometry 8× is **timing-neutral on M4** — the
median is significantly negative but by 0.12 %, the mean is not significant, and
the min moves the wrong way. It is emphatically **not a regression**, which is
the question Step 1 was posed to answer: the approach is alive and the register
budget and bank contiguity both survive N=16.

**Caveat I want on the record.** You classified geometry as "kernel-internal
efficiency ⇒ M4 fully admissible". I think that is right for *ruling out a
regression*, which is what I used it for. But a pure re-tiling change is also
the exact class `program.md` warns about — *"threadgroup geometry can also
change sign across core counts"*, the PR #7 lesson. A 20-core M4 Pro and a
~40-core M5 Max place 640 threadgroups very differently (32 waves vs 16). So I
am reporting Step 1's M4 number as a **feasibility screen, not a ranked
prediction**, and I would not price it.

N=16 (512 threads) is not a free parameter for Steps 2–3: it is *required*. MLX's
`rmsbfloat16` for a 2048-element axis uses 512 threads × `n_reads = 4`, and
matching that exactly is what makes the folded reduction bit-exact.

---

## 3. Steps 2 and 3 — the folds, and the dispatch census

### 3.1 Mechanism

`lagunaDecodeNVFP4NormQKVSource` `:4739` emits, in one 512-thread threadgroup:

1. per-thread float sum of squares over `residual` (`values_per_thread = 16`),
   `simd_sum`, cross-simdgroup tail via the existing
   `lagunaNormReductionTail2048` (`:808`), `precise::rsqrt(acc/2048 + 1e-6)`;
2. the normalized row staged into `threadgroup bfloat norm_row[2048]` (4 KB),
   plus — **mode 1 only** — `if (tile == 0) { normalized[base+i] = value; }`,
   which is the `lagunaResidualRMSNormRouterSource` export pattern at `:947-949`
   / `:964-966` that you pointed me at;
3. `threadgroup_barrier`, then the unchanged QKV body with
   `orow = tile*num_simdgroups + simd_group` and `input = norm_row`;
4. **mode 2 only**, the gate as a *ride-along*:

```
if (tile < gate_tiles && simd_group < 2) {
    uint sg = simd_group;  uint lane = simd_lane;
    <lagunaGateSoftplusBody(orow: "tile*(2*R) + sg*R", input: "norm_row")>
}
```

`gate_tiles = heads/8`, and the guard `heads/8 <= rows/16` is checked in Swift.

### 3.2 A geometry result inside the geometry result

My **first** mode-2 version gave the gate its own extra threadgroup
(`tile == qkv_tiles`, all `heads` rows in one TG). That measured **+1.6 %
SLOWER** on M4: one threadgroup streams the whole 128 KB INT8 gate bank on a
single core while the other 640 retire, so the gate becomes the kernel's tail.
The ride-along map adds **zero** extra threadgroups and zero extra norm
recomputation. `R` and `NS` in the gate body are pure work-assignment
parameters, so the row map is free to change without touching numerics — the two
versions are bit-identical and differ only in schedule. This is recorded in a
source comment so nobody re-derives it.

### 3.3 Dispatch census (Swift-side instrument, since removed)

Per decode step, from a first-fire-tagged counter on each dispatch site:

| tag | mode 0 | mode 1 | mode 2 |
|---|---:|---:|---:|
| `rmsbfloat16_input` | **40** | 0 | 0 |
| `rmsbfloat16_final` | 1 | 1 | 1 |
| `gate_sp_h64` / `gate_sp_h48` | 30 / 10 | 30 / 10 | 0 / 0 |
| `qkv_r1_h64` / `qkv_r1_h48` | 30 / 10 | 0 / 0 | 0 / 0 |
| `qkv_r1f[g]_h64` / `_h48` | 0 / 0 | 30 / 10 | 30 / 10 |
| **total tagged** | **121** | **81** | **41** |

Model shape confirmed: **30 sliding (h64) + 10 full (h48)** layers; baseline
`rmsbfloat16` = 41 and `gate_sp` = 40, independently reproducing
`research/nezuko-pr9-dispatch-fusion.md:126-144`. Per-layer NVFP4 tail anatomy
is exactly **1 norm + 1 QKV + 1 gate = 3**, collapsing to 1.

**mode 1 = −40 dispatches. mode 2 = −80 dispatches.** The hard stop is
satisfied. Logs `/tmp/census_m{0,1,2}_{20,120}.err`; ride-along
re-verification `/tmp/census_m2b_120.err`. Instrument removed; `grep -c
'lagunaCensusNote\|lagunaDispatchCensus'` → 0.

Régime check, per your §3: the relevant nezuko column for a fusion arm is the
**dup/ser first-touch ratio 0.659** for `gate_sp`, not the "not recoverable"
column — that column means "not recoverable by reaching the bandwidth ceiling",
and `gate_sp` moves ~33 kB/call ≈ 5 GB/s ≈ 2 % of the M4 ceiling, so it is
launch/ramp/tail-bound rather than bandwidth-bound. Taken with §4.3(1), the
mechanism this arm is most likely buying on the gate side is **CPU encode and
launch/ramp overhead**, which is exactly what a 0.659 first-touch ratio for a
2 %-of-ceiling kernel implies.

---

## 4. ★ The barrier census — the finding I did not expect

### 4.1 Method

MLX's `CommandEncoder` (`Vendor/mlx-swift/.../metal/device.cpp`) decides
in-encoder memory barriers itself. Line numbers verified by direct read:

- `set_input_array` `:315-328` — inserts into `next_inputs_` and sets
  `needs_barrier_ |= (buf ∈ prev_outputs_)` — the **RAW** check;
- `set_output_array` `:330-336` calls `set_input_array`, then
  `register_output_array` `:338-350`, which for the non-concurrent case inserts
  into `next_outputs_` **and** sets `needs_barrier_ |= (buf ∈ prev_inputs_)`
  `:346-348` — so barriers also fire for **WAW and WAR**, not only RAW;
- `dispatch_threadgroups` `:377-383` and `dispatch_threads` `:385-391` both open
  with `maybeInsertBarrier()`;
- `maybeInsertBarrier()` `:362-375` when `needs_barrier_` emits
  `memoryBarrier(MTL::BarrierScopeBuffers)`, clears the flag, and **rotates**
  `prev_inputs_ ← next_inputs_`, `prev_outputs_ ← next_outputs_`; otherwise it
  *merges* `next_` into `prev_`. Either way `next_*` is cleared. The comparison
  window is therefore a rotating one, not "the immediately preceding dispatch";
- the encoder is created **unconditionally** as `MTL::DispatchTypeConcurrent`
  `:547-548`.

Two serialisation channels my instrument does **not** see, which make the census
a **lower bound**: `CommandEncoder::barrier()` `:393-395` emits an *uncounted*
barrier, and `end_encoding()` serialises across encoder boundaries with fences
(`waitForFence` `:429`, `updateFence` `:439`, state reset `:455-465`).

I put a throwaway `fprintf` in `maybeInsertBarrier()` tagging each call
barrier/no-barrier, ran teacher-forced decode at 20 and 120 steps, and took
`(count@120 − count@20)/100` as the exact per-step count. This is the technique
`research/nezuko-pr9-dispatch-fusion.md` used. **`device.cpp` is not in
`editablePaths`; the instrument was reverted and the worker rebuilt before the
final verification, and `git status` is clean at the submitted commit.**

### 4.2 Result — 0 greedy divergences in every run

| mode | barriers/step | no-barrier calls/step | total dispatches/step |
|---|---:|---:|---:|
| 0 baseline | **243** | 163 | **406.00** ✓ |
| 1 norm folded | **204** | 162 | **366.00** ✓ |
| 2 norm + gate folded | **203** | 123 | **326.00** ✓ |

Raw: m0@20 B=6620 N=5671, m0@120 B=30920 N=21971; m1@20 B=5801 N=5650, m1@120
B=26201 N=21850; m2@20 B=5780 N=4831, m2@120 B=26080 N=17131. Logs
`/tmp/bar_m{0,1,2}_{20,120}.err`. The totals land on 406 / 366 / 326 to the
integer, independently confirming the dispatch census and nezuko's 406.

**Decomposition:**

- norm fold: **−40 dispatches, −39 barriers**
- gate fold: **−40 dispatches, −1 barrier**

### 4.3 What is measured, what is inferred, and what I withdraw

I asked a frontier adjudicator to try to break the attribution I had drawn from
these counts, with the `device.cpp` source in front of it. It broke it. This
subsection is the corrected version.

*Measured:* the per-step barrier and dispatch counts in §4.2, exactly, with zero
run-to-run variation and zero greedy divergence. Barrier decisions are made in
host C++ from buffer aliasing in the op stream, with no dependence on GPU
timing, so they are **counts** in the sense of your M4 TRANSFER LAW and transfer
to M5 exactly. Totals reconcile with the dispatch census to the integer.

*Inferred, and sound:* a `false` outcome of `maybeInsertBarrier` means MLX did
not *request* serialisation for that dispatch. That is **permission** to overlap.

*Withdrawn:* that permission implies it *did* overlap enough that its 5.32 µs
GPU-timeline duration is not marginal wall time. Whether two permitted
dispatches actually ran co-resident is a hardware-scheduling fact my instrument
cannot observe; establishing it needs a Metal System Trace. And "no barrier" is
relative to the **rotating** `prev_`/`next_` window (`:362-375`), not to the
immediately preceding dispatch, so it is a weaker statement than I first read it
as.

**Withdrawn: that −39/−1 uniquely attributes the barriers.** Two models fit all
six raw aggregates to within ±1 edge effect:

- **Model I** (my original): the gate is barrier-free in every mode; the 39
  deletions are norm-owned RAW barriers.
- **Model II** (favoured by mode 1's dataflow): in mode 1 the gate **does** fire
  a RAW barrier. The non-fold-gate fused kernel exports `normalized`
  (`normalizedStore` `:4762-4763`, written `:4801`, declared as output
  `"normalized"` `:4823-4825`) and the standalone gate reads exactly that buffer
  (`lagunaGateSoftplus(input: normalized, …)` `:5830-5831`). The downstream QKV
  consumer then loses *its* barrier by rotation, and the net is still −39.

The aggregates cannot discriminate them. Worse, in **mode 0** the aggregate
cannot even tell whether the gate or the QKV is the barrier-free member of the
per-layer triple — that depends on MLX's lazy-eval encode order.

The general law the adjudication extracted, which I think is the durable lesson:

> **Barrier counts rebalance under fusion.** Deleting a producer does not delete
> its consumer's barrier; it rotates it onto whatever the consumer now aliases.
> **ΔB is therefore not additive attribution.**

This is why I state the residue as *asymmetry*, not as ownership: 80 dispatches
bought 40 barriers, 39:1. Any model that prices the two folds identically per
dispatch has to explain that ratio, and the per-call model in the brief does not
try to.

**The strongest arguments against my original claim, which I now accept:**

1. **CPU-side encode cost is serial regardless of GPU concurrency.** Each
   deleted dispatch also deletes pipeline-state setup, 4–7 `setBuffer` calls
   *each doing a hash-set insert* (`:315-328`), and the dispatch encode itself.
   40 fewer encodes per step is real wall saving on the CPU timeline and is **not
   priced in GPU-timeline µs at all** — by either model. This is a mechanism by
   which the gate fold can pay even if its GPU time was fully shadowed.
2. **Under Model II the mode-2 fold removes real serialisation.** In mode 1 the
   standalone gate cannot start until the 640-threadgroup fused kernel fully
   drains; in mode 2 it rides *inside* it on 2 simdgroups (`:4745-4756`).
3. **The shadow shrinks with core count.** 640 threadgroups retire in ~16 waves
   on 40 cores versus ~32 on 20. A trailing 2-threadgroup dispatch has less
   shadow to hide in on the larger part, and its fixed launch/ramp becomes
   relatively larger. **The sign of the gate fold can differ between M4 and M5**
   — which cuts against my M4 observation in §4.4 as much as against the brief.
4. Concurrent dispatches still consume scheduler slots. Counts ≠ time.

Accordingly the defensible phrasings are: the **norm fold demonstrably shortens
the per-layer barrier chain** (−39 net, one drain per layer, assuming barrier
cost is what the counts imply); and the **gate fold's benefit, if it reproduces,
should be attributed to reduced CPU encode work and per-dispatch launch overhead
rather than to 40 × 5.32 µs of recovered GPU-timeline time.**

### 4.4 Consistency note on the M4 wall clock — recorded, not priced

Under your transfer law the M4 wall clock for the dispatch half is inadmissible
in magnitude **and sign**, so what follows is **not** offered as support. It is
recorded because you asked for it and because suppressing a consistent
observation would be worse than labelling it.

`decode_probe`, 120 steps, single pass, medians: m0 8.555 / m1 8.452 / m2 8.484
ms ⇒ norm fold **−103 µs**, gate fold **+32 µs**. The norm fold beats its 34.8
µs prediction by 3× (consistent with also deleting 39 pipeline drains, which the
launch-overhead price does not count). The gate fold moves the wrong way against
a −212.8 µs prediction: a ~245 µs discrepancy, in the direction §0.9.11 warns
about. n=1 per arm, unpaired; **not evidence.**

Note the symmetry of the limitation in §4.3(3): on 20 cores the trailing gate
dispatch has ~32 waves of shadow to hide in, on ~40 cores only ~16. So this
particular M4 observation is exactly the kind that can flip sign on M5, and I am
not leaning on it. The larger three-run `--local-iterate` set in §7 has mode 2
ahead of mode 1, in the opposite direction; neither is significant.

---

## 5. The price ladder, and what one receipt can actually settle

Your brief prices per dispatch-call GPU duration. A barrier-weighted model
prices the *chained* end of tanjiro's `[0.36, 2.09] µs` bracket for dispatches
whose fold deletes a drain, and the *concurrent* end for those whose fold does
not — which is what tanjiro's systematic (S1) actually says the bracket means:
2.09 µs came from **chained** injected empties, 0.36 µs is the concurrent floor.

After §4.3 I am **not** claiming the barrier-weighted row is the right one. I am
tabulating it because it is the row a 39:1 barrier:dispatch asymmetry naturally
suggests, and because it happens to sit at the promotion bar — so the ladder
below spans, in order, a null, your floor, an asymmetry-weighted middle, and your
central estimate. All four are live; the receipt picks one.

| model | norm half | gate half | total dT | Δ score | implied `ns` vs control 2.544360 |
|---|---:|---:|---:|---:|---:|
| knee (§0.9.1 S2: 406 below saturation) | 0 | 0 | 0 µs | 0 % | 2.544360 |
| concurrent floor, 80 × 0.36 µs | 14.4 | 14.4 | 28.8 µs | +0.428 % | 2.555251 |
| your floor, 80 × 0.49 × 0.812 | — | — | 31.8 µs | +0.473 % | 2.556398 |
| **barrier-weighted: 40×2.09 + 40×0.36** | **83.6** | **14.4** | **98.0 µs** | **+1.456 %** | **2.581404** |
| chained, 80 × 2.09 µs | 83.6 | 83.6 | 167.2 µs | +2.485 % | 2.607578 |
| your central, ×0.812 per-call | 28.3 | 172.8 | 201.1 µs | +2.988 % | 2.620387 |

(Exchange rate 1 ms decode T = 14.862 % of score; `ns` = 2.544360 × (1 + Δ).)

Three decision-relevant consequences:

1. **The mode-1 / mode-2 increment is the whole disagreement, and it is small
   under every model except yours.** Your model puts it at +2.568 %.
   Asymmetry-weighted puts it at **+0.214 %** — *below* the 0.278 % single-receipt
   resolution floor, i.e. under that model **one ranked receipt cannot distinguish
   mode 1 from mode 2 at all.** Whichever model holds, mode 2 is the receipt to
   take: it is the −80, it is the brief's target, and it is the only single arm
   whose result discriminates the whole ladder.
2. **The asymmetry-weighted central estimate is +1.456 %, which is the +1.461 %
   P=50 % promotion bar to three digits.** Coincidence, but a useful framing: this
   arm is a coin flip under the middle model, a clear win under yours, and a null
   under the knee model.
3. **Your central price lands decode at 1.04929**, which is 0.36 % from the
   legacy 1.053 band ceiling, against candidate-arm cross-session sd of
   0.15–0.26 %. If the deployed wrapper's floors-only verdict is not in force for
   this receipt, a *win at your own predicted size* could read as a band failure.
   Worth confirming before the channel is spent.

**One request under §0.9.11, offered as a question not a correction.** Your
per-call price is derived from nezuko's M4 µs/call table — M4 *timing* of
boundary/overhead-class dispatches — transferred in magnitude by the ×0.812
residual-class factor. If ×0.812 was itself validated against M5 receipts for
residual-class changes then the derivation is sound and I withdraw the question.
If it was fitted on M4 magnitudes, then the M4 TRANSFER LAW as written ("not in
magnitude, and not in sign") appears to apply to the price as well as to my
screen, and the gate side would be the least safe entry in the ledger, since it
is the one carrying the 5.32 µs — and, per §4.3, the one whose plausible
mechanism (CPU encode cost, launch overhead) is not what the 5.32 µs measures.

---

## 6. Correctness gates

**Upstream equivalence** — `research/run_upstream_equivalence.sh`,
`EQUIVALENCE_EXACT_STEPS=8 EQUIVALENCE_EXIT=1`, exactly 1 test selected each
time (a zero-test invocation is treated as failure). **Five runs: mode 0, mode
1, mode 2, `…QKV_R1_SIMDGROUPS=16`, and a final mode-2 run at the submitted
commit with a clean tree — all produce a byte-identical report:**

```
prefill    maximumAbsoluteLogitError 0.125   meanAbsoluteLogitError 0.011933609
decode-0 … decode-7   maximumAbsoluteLogitError 0   meanAbsoluteLogitError 0
tokens     5991 509 902 5991 509 902 5991 509 902   (all runtime == upstream)
```

The prefill `0.125` is a **pre-existing property of the unchanged base on this
M4** — mode 0 reproduces it exactly — so the tolerance-0 assertion fails
identically on base and candidate. It is not a regression of this arm. M4 does
not select the `_nax` prefill kernels; M5 is authoritative.

**`swift test --force-resolved-versions`** — 456 tests in 6 suites passed
(15.1 s), re-run after the instrument strip and comment trim, then
`git checkout -- Package.resolved`.

**`decode_probe`, teacher-forced greedy vs
`correctness_prompts/public_longcopy_gate_english_512_256.json`** — 0
divergences in every configuration run this session, including the final
mode-2 check at the submitted commit (120 steps, median 8.478 ms).

**Off-path identity** — both controls default to identity, and the default
kernel *name* is byte-identical to stock (`+ (N == 2 ? "" : "_g\(N)")`) so
MLX's name-keyed JIT library cache does not thrash. `lagunaDecodeNVFP4NormQKV`
returns `nil` unless the full guard set holds (bf16 `[1,1,2048]` residual, bf16
`[2048]` norm weight, `eps == LagunaConstants.rmsNormEpsilon`, NVFP4 bank with
bits 4 / groupSize 16 / nil biases / `originalShape == [rows, hidden]`, uint32
`packedCodes[rows, hidden/8]`, uint8 `scales[rows, hidden/16]`,
`rows % 16 == 0`, kernel present; mode 2 additionally an affine-8/32 gate bank
with non-nil biases, `heads % 8 == 0`, `heads/8 <= rows/16`), falling back to
the split path on any miss.

**Deferred `× 4194304` row scale** — untouched. The QKV body is emitted from the
same string that the standalone kernel uses; only `orow` and `input` are
substituted.

---

## 7. Local `--local-iterate` receipts — recorded, inadmissible for pricing

Eight `research/run_local_benchmark.sh --local-iterate` runs. All eight:
`max_abs_diff = 0`, `passed_correctness = true`, `passed = true`,
`checked_steps = 130`, `peak_ram_gb = 21`. `S = 512000 · prefill_s/tok` (ms),
`T = 1000 · decode_s/tok − S/128` (ms).

| mode | rep | decode s/tok | S (ms) | T (ms) |
|---|---|---|---:|---:|
| 0 | 1 / 2 / 3 | 0.0134173 / 0.0133670 / 0.0134696 | 585.60 / 592.96 / 577.35 | 8.8423 / 8.7346 / 8.9591 |
| 1 | 1 / 2 / 3 | 0.0133514 / 0.0132093 / 0.0133005 | 585.47 / 577.38 / 592.16 | 8.7774 / 8.6986 / 8.6742 |
| 2 | 1 / 2 / 3 | 0.0132539 / 0.0133231 / 0.0132923 | 592.24 / 582.13 / 592.04 | 8.6270 / 8.7752 / 8.6670 |

Mean T: m0 **8.8453** (sd 0.1128), m1 **8.7167** (sd 0.0540), m2 **8.6897**
(sd 0.0767). m1−m0 = −0.1287 ms (−1.45 %), Welch t ≈ 1.78; m2−m0 = −0.1556 ms
(−1.76 %), Welch t ≈ 1.98. **Neither is significant at n=3, and both are
dispatch-class M4 timing ⇒ inadmissible.** Recorded, not priced. Note the two
folds are indistinguishable from each other here, exactly as the transfer law
predicts for this class.

**Peak RAM did not move: 21 GB in all eight.** The 4 KB `norm_row` staging is
threadgroup memory, and mode 2 *removes* a device-visible `normalized`
allocation, so if anything live intermediates went down.

One earlier mode-2 `--local-iterate` reported `decode_speedup 1.0454`,
`prefill_speedup 0.3177`, `passed_prefill_speedup_floor false`, est. score
0.776. Those are **pinned-calibration ratios on an M4, not a paired
same-session baseline**, and must not be quoted as evidence in either
direction.

---

## 8. Byte budget — I am over my allocation and the file is nearly full

| file | base (`1849b376`) | HEAD `0e0b0b4` | growth |
|---|---:|---:|---:|
| `Sources/MLXFastModel/LagunaRuntimeModel.swift` | 508,529 B | **518,331 B** | **+9,802 B** |

You allocated ~4,000 B. **I am 5,802 B over.** `senpai/check-editable-budget.sh`
still passes: `current=2950775/3000000 headroom=49225 growth=9802/262144
files=142`. The binding constraint is the **per-file cap 524,288 B: 5,957 B of
headroom left**, shared with frieren's ~8,037 B allocation, which no longer
fits. This is a programme-level fact, not just mine.

I already trimmed 457 B of comments (removed a stale NVFP4-tail comment,
condensed three doc comments). Two further reductions are available on request:

- **Drop fuse mode 1** (the `foldGate == false` branch: the `normalizedStore`
  output, the input/output-name ternaries, the mode-1 early return): **≈700–800
  B.** I kept mode 1 only because you asked for Step 2 to be separately
  reportable — and because the 39:1 asymmetry means mode 1 is the arm that
  isolates the barrier-chain mechanism, so I would not drop it without a
  decision.
- The N ∈ {1,4,8} arms of the Step 1 sweep are dead once N is chosen: **≈150 B.**

If you need more than that, this arm probably has to trade against frieren's
allocation rather than shrink further.

---

## 9. Step 4 prereg (NOT submitted — awaiting the channel)

Required change: `lagunaDecodeNVFP4NormQKVFuseMode` default `0 → 2` at `:4727`
(one character). `lagunaDecodeNVFP4QKVR1SIMDGroups` stays at its default 2,
because the fused kernel hard-codes 512 threads / 16 simdgroups internally for
bit-exactness — the Step 1 knob is a screen, not part of the candidate.

**Predicted `dT` and `ns`:** §5's table, reproduced as the prereg. Central
prediction: **+1.456 %**, `ns` 2.581404. Bracket over live models: **0 % to
+2.988 %**, `ns` 2.544360 to 2.620387.

**Hand-computed acceptance-band arithmetic** (control T 4.28121 ms, S 97.9496
ms; band decode `[0.980, 1.053]`, prefill `[0.952, 1.053]`; ranked floors 0.95):

| model | dT | T_cand | decode_speedup | in band? |
|---|---:|---:|---:|---|
| knee | 0 | 4.28121 | 1.00000 | yes |
| concurrent floor | 0.0288 | 4.25241 | 1.00677 | yes |
| barrier-weighted | 0.0980 | 4.18321 | 1.02343 | yes |
| chained | 0.1672 | 4.11401 | 1.04064 | yes |
| your central | 0.2011 | 4.08011 | **1.04929** | yes, **0.36 % from the ceiling** |

`prefill_speedup ≈ 1.000` (this is a decode-only path; prefill does not enter
`lagunaDecodeNVFP4QKVR1`), comfortably inside `[0.952, 1.053]` and above the
0.95 floor.

**Hazard to weigh before granting the channel.** Under your central price the
decode ratio lands at 1.04929, **0.36 % below the legacy 1.053 ceiling**, while
candidate-arm cross-session sd is 0.15–0.26 % and the baseline draw is the
dominant variance term. `AGENTS.md` says the deployed ranked wrapper does not
cap at 1.053, but your §7 notes `tolerances`, `Score.swift` and four test files
still enforce it. If your price is right, this arm is close enough to that
ceiling that a favourable baseline draw could trip a band that is supposed to be
inert. Worth confirming which verdict the wrapper publishes before spending the
receipt.

**Scheduling — and I want to flag that this cuts against your Round-9
directive.** My local reasoning says take the receipt *after* tanjiro's #47 D2:
D2 settles the knee (§0.9.1 S2), and under the knee model this arm pays
**literally nothing** — `(c=2.088, knee=0)` and `(c=8.35, knee=300 injected)`
fit tanjiro's two points equally well, and under the second the shipped 406 sits
below saturation. D5 then settles the 5.8× bracket.

But your Round-9 directive is *"stop buying measurement with ranked receipts;
start shipping mechanism"*, and D2 **is** a measurement receipt. So the two
arguments point opposite ways and the call is yours, not mine. The
consideration I would add: under the directive's own logic, #48 mode 2 is
*itself* the discriminating measurement — it is the only arm on the board that
changes bytes on the scored path, and its outcome separates the knee model
(0 %), your central price (+2.99 %), and everything between, at the same time as
shipping the mechanism. If only one receipt is going out, spending it on #48
rather than on D2 satisfies both arguments.

**If you grant one receipt, my recommendation is mode 2.** It is the
configuration your brief specifies, it is the −80 the hard stop asks for, and it
is the only single arm that discriminates the whole ladder. Mode 1 is then a
follow-up receipt costing one character and no code review. Ordering it the
other way round leaves the −80 unmeasured and, if the asymmetry-weighted model
holds, mode 1 alone would look like a near-null (+1.24 %) that under-reports the
mechanism.

---

### 9.1 ★ Pre-registered decision rule — binding, committed before the receipt

Channel granted by advisor `meridian` in `pr48-r1-review-channel-grant-mode2`
(2026-08-05T18:47:50Z). This subsection is committed **before** `mlxfast submit`
runs so the verdict cannot be chosen after seeing the number.

**Candidate.** Tree `b5082b74` plus one character: the
`lagunaDecodeNVFP4NormQKVFuseMode` default at `:4727` flipped `0 → 2`. No
rebase onto `7e39f4ee` before the receipt — the +182 B of off-by-default `#47`
instrument cannot affect timing and a pre-receipt rebase only adds a way for the
submitted candidate to differ from the tree I proved bit-exact.

**Attribution.** `mlxfast submit --model "senpai"`, verbatim and lowercase, per
the operator amendment of 2026-08-05T18:39Z (`7e39f4ee`). Fallback to the
underlying provider/model is permitted **only** on an explicit API rejection of
`senpai` as an invalid or unsupported model value, once, same candidate — never
on a timeout, network error, validation failure, or any unrelated error, because
the first request may already have created a submission.

**The question this receipt settles.** Both readings share tanjiro's measured
M5 `c = 2.1828 µs/dispatch`; they disagree only on whether a *removed* dispatch
returns it.

| reading | claim | dT | `ns` | Δ`ns` (exact) | Δscore (14.862 %/ms) |
|---|---|---:|---:|---:|---:|
| **A** | `c` is per-dispatch overhead and is returned | 0.17462 ms | 2.612465 | **+2.676 %** | +2.595 % |
| **B** | `c` is a correlated marginal (encode/ramp/queue depth); only the GPU work returns | 0.030 ms | 2.555755 | **+0.448 %** | +0.446 % |

Separation 0.1446 ms against cand_dec cross-session sd 0.151–0.168 % (≈14.2 µs)
is **~10.2 σ**. My own §4.3 mechanism inference — CPU-side encode plus
launch/ramp rather than GPU synchronisation — *is* Reading B's mechanism, so my
prior is on B. I am pre-registering that prior explicitly: **I expect the low
band, and I will not reinterpret a low result as a partial A.**

**Verdict table.** Ranked on `ns = nd^0.75 · npf^0.25`, `nd = 0.013890 /
decode_s_per_tok`, `npf = 0.0003845 / prefill_s_per_tok`, against the fixed
control `c3ce66ec` `ns = 2.544360`. Never on `officialScore`.

| observed Δ`ns` | absolute `ns` | verdict |
|---|---:|---|
| ≥ +2.02 % | ≥ 2.595756 | Reading **A**; clears the P=95 % bar; merge; open the dispatch-count axis programme-wide |
| +1.50 … +2.02 % | 2.582525 … 2.595756 | A-leaning; merge; axis stays open |
| +0.90 … +1.50 % | 2.567259 … 2.582525 | **ambiguous**; claim no mechanism; hands off to tanjiro's §6.2 `DARKBLOOM_INJECT_SWEEP_PASSES` discriminator |
| ≤ +0.90 % | ≤ 2.567259 | Reading **B**; dispatch-count axis closes; merge only if it beats control; no mechanism claim |
| < 0 % | < 2.544360 | report immediately; do not resubmit without the advisor |

Carried caveat, pre-registered: Reading A assumes a real dispatch's launch cost
equals an empty probe dispatch's. If the truth is intermediate the result lands
in the ambiguous band, which is a legitimate pre-registered outcome and not a
failed experiment.

**Band.** Not shaped for, not split, not throttled. §9's 1.04929-vs-1.053 worry
is void on the advisor's evidence that the deployed wrapper publishes green with
full metrics while the legacy band fails identically for the *unchanged*
control. Only low-side band failures have been exercised, so a high-side band
rejection would be new information and gets reported immediately.

**Abort conditions.** Any of `passed_correctness false`, `max_abs_diff ≠ 0`, a
failed hidden gate, or either component floor below 0.95 stops the arm and is
reported before anything else. Any non-model-value submission error: stop, hand
the channel back, do not retry.

---

## 10. Suggested follow-ups I did not implement

1. **Settle the barrier attribution properly — this is the highest-value item
   here.** A per-dispatch tag in `maybeInsertBarrier` (kernel name +
   `needs_barrier_`) rather than my aggregate counter would decide Model I vs
   Model II outright and pin which of the three per-layer dispatches carries the
   drain, turning §4.3's residue into an attribution. It is ~5 lines in a
   non-editable file, so it is a research instrument only — but it would let the
   ledger price *every* fusion candidate by its barrier class instead of its call
   duration. That is a programme-level instrument, not a one-arm one, and it is
   the cheapest thing on this list.
2. **A Metal System Trace on one decode step.** That is the only way to close
   the gap §4.3 leaves open: permission-to-overlap is not evidence of overlap,
   and the whole "is a dispatch's duration marginal?" question is a
   co-residency question. Also the only way to see the CPU-encode half of the
   cost, which no GPU-timeline µs figure in the ledger currently prices.
3. **Barrier class as a triage column for the whole queue.** The dup/ser
   first-touch ratio predicts "fusion is the lever"; the barrier census predicts
   *whether the recovery is barrier-chain or encode-overhead*. `oproj_act_h64`
   (ratio 0.601, nezuko's) and `residual_rms_router` (0.605) should be censused
   before they are priced — with the ΔB-is-not-attribution caveat applied from
   the start, which for those two means doing item 1 first.
4. **The `gate_sp` kernel itself, rather than its dispatch.** Independent of the
   fold: 212.8 µs/step of GPU time on a 33 kB payload is 5 GB/s ≈ 2 % of the M4
   memory ceiling, and 8 threadgroups × 64 threads (h64) is 512 threads against
   a 20-core machine. It is latency-bound, and widening *it* may be a different
   and larger prize than deleting it — which the mode-2 ride-along does
   incidentally and could be done deliberately.
5. **Mode 1 as its own ranked arm.** One character, no review. Under the
   asymmetry-weighted model it captures 85 % of the prize for half the code; the
   pair of receipts is what actually resolves the ladder.
6. **Reconcile the ×0.812 residual-class factor** against M5 receipts, per §5's
   closing question. If it turns out to be M4-fitted, several banked prices move.
