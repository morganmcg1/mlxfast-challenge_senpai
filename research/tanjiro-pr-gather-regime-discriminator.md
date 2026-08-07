# PR #170 — Regime discriminator for the prefill routed gather GEMM

Assignment `maple-2026-08-06o-gather-regime-discriminator`, revision `r1`.
Base `codex/mlxfast-maple-20260804-advisor` @ `f1f7c1b`.

## 0. Question

On the promoted receipt `97a5090` (commit `3e165fa`, `officialScore =
2.58882784082067`, `ns = 2.5982163`) the prefill wall is `S = 97.895 ms` and the
routed gather GEMM `fp_gather_qmm_rhs_expert_nax` costs

```
W = 43.2619 +- 0.402 ms   17,666.41 MB   1005.02 GFLOP     (ledger field dS1)
```

`W` is the sole empirical anchor of this experiment; every threshold below is a
fraction of it.

### 0.1 What the roofline actually says, honestly

The corpus has repeatedly described this kernel as "67% of the compute roofline
and 67% of the bandwidth roofline at the same time". That phrasing overstates
the evidence and this experiment does not rely on it. The kernel's arithmetic
intensity is

```
AI = 1005.02 GFLOP / 17.66641 GB = 56.89 FLOP/B
```

and the ridge point of the assumed machine model is `34.7 TFLOP/s / 610 GB/s =
56.89 FLOP/B`. The two numbers are **equal**, so the kernel sits exactly on the
ridge *by construction of the assumed peaks*, and the two "67%"s are one
measurement projected twice, not two independent facts. Worse, the corpus
sanctions several byte rates for this machine (281.3, 415, 546.2, 610, 651.8
GB/s depending on access pattern); at 546.2 GB/s the implied load stream is
32.34 ms rather than 28.96 ms and the streams are no longer symmetric at all.

So the honest statement of the puzzle is weaker and more useful:

- the kernel does `1005.02 GFLOP` and moves `17.666 GB` in `43.26 ms`;
- **no theoretical peak is known to be attainable in situ**, and the ridge
  coincidence means a roofline chart cannot separate the two axes here;
- therefore the binding axis has to be measured, not inferred.

Rather than guess, this experiment **adds** bit-exact work along one axis at a
time and reads the marginal wall cost. Adding work is a strictly better
instrument than removing it: a removal that does not help is ambiguous (wrong
axis, or right axis but the removal did not bite), whereas an addition that
costs nothing proves the axis has slack. Crucially, a marginal-cost measurement
needs **no** assumption that any peak is attainable — it only needs the measured
wall `W = 43.26 ms` as its own denominator. Theoretical peaks are demoted in
§4 to a one-way sanity cross-check (they can only tell us the instrument is
broken, never that a hypothesis is true).

Four hypotheses were pre-registered:

- **H0** jointly saturated — both streams already overlap as well as possible.
- **H1** MMA-limited — arithmetic is the critical path.
- **H2** load+dequant-limited — weight traffic and dequant are the critical path.
- **H3** schedule-latency-limited — barriers/occupancy, not work, dominate.

## 1. Instrument

One new template parameter on the kernel, `int probe = 0`, selected by a single
named constant in the selector:

| arm | `probe` | added work | intended axis |
|-----|---------|-----------|----------------|
| control | 0 | none — byte-identical to the shipped kernel | — |
| **M2** | 1 | second `tile_matmad_nax` per `kk1` into a shadow accumulator, fed by an already-resident `Atile` fragment and the same staged `Btile` | MMA only |
| **S2** | 2 | second loader stages a neighbouring expert's weights + dequant into the same `Ws`, then the real staging overwrites it | load + dequant (+1 barrier) |
| **B2** | 3 | two extra `threadgroup_barrier(mem_threadgroup)` per k-iteration | schedule only |

Submitted surface (exactly the three paths the assignment authorised):

- `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized_nax.h`
- `Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized_nax.cpp` (JIT twin)
- `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp` (selector)

`Sources/MLXFastModel/LagunaRuntimeModel.swift` was **not** touched (frieren
#148 collision). Editable budget after all edits:
`current=2937322/3000000, headroom=62678, growth=10411/262144` — well inside
every fence.

### 1.1 The arm has to be compiled in, not env-selected

The natural design — an env var — **cannot work for a ranked receipt**. The
official runner strips the environment: `benchmark.sh:2084-2086` runs the timed
measure job under `sudo env_reset` + `env -i`. `benchmark.json` contains no
`env` block, the `mlxfast` CLI bundle contains no matching string, and no
`setenv()` exists anywhere in the repo. An env-only knob therefore always
measures its own control on the M5.

So the knob reads `env::get_var("DARKBLOOM_NAX_GATHER_PROBE",
kNaxGatherProbeDefault)`, and **`kNaxGatherProbeDefault` is the arm**. Each
official receipt is a one-token flip of that constant in the working tree,
which `mlxfast submit` packages (it packages the working tree, not `HEAD`). The
committed value is `""` — the shipped kernel. Env remains a local override
only, matching every other `darkbloom_*` knob in the file. This reproduces the
precedent recorded in `research/maple-fern-pr40-result.md`.

### 1.2 Defeating the optimiser and the caches

Three distinct things could silently turn an arm into its own control:

1. **Dead-code elimination.** M2's shadow accumulator has one consumer, a store
   guarded by `run_skip_pct > 1000`. `run_skip_pct` is a constant-buffer scalar
   the compiler cannot fold, and the host clamps it to `[1, 100]`, so the guard
   is unreachable at runtime yet keeps the chain live at compile time.
2. **Common-subexpression elimination.** The shadow MMA's operand pair is
   `(Atile[(kk1/SK + 1) % (BK/SK)], Btile)` — a pair the real chain never
   forms, so it cannot be folded into the real MMA. All `Atile[]` entries are
   fully loaded in a preceding loop, so the operand is real data, not garbage.
3. **The JIT library cache, which is keyed on kernel name alone.** Each
   non-zero arm therefore appends `_pb_<n>` to the kernel name. The suffix is
   omitted at probe 0 so the shipped name stays byte-identical.

All three were then **verified in the emitted machine code**, not assumed —
see §2.

## 2. Step 0 offline census

Full table, legend, and pipeline reflection:
[`research/artifacts/tanjiro_gather_probe_census.md`](artifacts/tanjiro_gather_probe_census.md).
Counts are post-optimisation AIR from
`xcrun -sdk macosx metal-objdump --disassemble`, both live threadgroup shapes.

```
pb  kernel                      mma  barr  dev_ld  tg_ld  tg_st  ir_lines
0   2048x1024_bk64                1     7       6      4      5       537
0   512x2048_bk64                 1     5       6      2      4       583
1   2048x1024_bk64  (M2)          2     7       6      4      5       697
1   512x2048_bk64   (M2)          2     5       6      2      4       743
2   2048x1024_bk64  (S2)          1     8       8      4      6       583
2   512x2048_bk64   (S2)          1     6       8      2      5       629
3   2048x1024_bk64  (B2)          1     9       6      4      5       539
3   512x2048_bk64   (B2)          1     7       6      2      4       585
```

**Confound verdict on the memory and barrier axes: all three arms CLEAN.**

- **M2** — `mma 1 -> 2`; barriers, device loads, threadgroup loads and
  threadgroup stores **all unchanged**. CSE and DCE both defeated, and the arm
  adds exactly zero memory traffic.
- **S2** — `dev_ld 6 -> 8`, `tg_st +1`, `barr +1`, `mma` unchanged. Clean, but
  carries one extra barrier *by construction*; §4 subtracts it.
- **B2** — `barr +2`, every other counter unchanged. The compiler did not merge
  or hoist the added barriers.

> **Superseded in part by §4.0.2.** These counters cover memory traffic, MMA and
> barriers but **not ALU**. Adding an ALU column later showed M2 also carries
> `int_alu +15` (+17%) and S2 `int_alu +4`, so "M2 is a single-axis arm" was too
> strong a claim. B2 survives the stronger test — it moves barriers and nothing
> else at all. §4.0.2 gives the full per-axis table and the consequences for the
> decision rules; it is left here rather than silently rewritten because the
> weaker census is what the arms were originally justified on.

Every added call site sits inside the same loop nest as the original it
shadows, so the **static ratio equals the dynamic ratio**.

Pipeline reflection is identical across all four arms and both shapes:
`threadgroupMemoryLength = 9232 B`, `maxTotalThreadsPerThreadgroup = 1024`,
`threadExecutionWidth = 32`, giving `floor(32768 / 9232) = 3` threadgroups per
core. **Occupancy is unchanged by every arm.**

*Honest caveat — register residency is not measurable offline here, and this is
the one confound I cannot close.* The advisor asked for register/occupancy
stats per arm. Occupancy I can give and did: `tgMem_B = 9232` on a 32768 B
core budget pins **3 threadgroups/core, identical across all four arms and both
shapes**, so *threadgroup-memory* residency is settled and no arm moves it.
Registers I cannot give, and I would rather say so than publish a number that
looks like a measurement.

The only offline handle is `maxTotalThreadsPerThreadgroup`, which inverts to a
register *bound*, not a count. It reads 1024 for every arm — but 1024 is also
the Metal API's hard ceiling for a threadgroup, so the value is **saturated**:
it is consistent with 8 registers/thread and with 32, and it cannot resolve any
of the half-register cliffs the advisor flagged (104/128/160/208/256), where
gen-17 occupancy steps 1024 → 832 → 640 → 512 → 384 threads/core against a
~208 KB/core register file. A saturated bound reports the ceiling, not the
kernel.

`research/tanjiro_metallib_stats.swift` therefore prints this column as
`regs_bound = <=32*` with the asterisk explained in a footer, rather than the
bare `regs_est = 32` an earlier revision printed. That earlier column was
misleading in exactly the direction that matters — it read as a point estimate
of a quantity the instrument never measured.

**What this costs the experiment.** M2 adds 5 allocas. A `ΔM2 ≈ 0` is still
confound-free, so the *falsification* direction is safe. But a *large* `ΔM2`
admits a register-pressure alternative — M2 spilling and paying occupancy
rather than MMA issue — that this host cannot exclude. R0b exists to flag that
case rather than to resolve it, and if R0b fires the honest reading is
"M2 perturbed something beyond its axis", not "H1 confirmed". Closing this gap
needs on-M5 pipeline reflection, which the receipt protocol does not return; it
is recorded in §9 as a follow-up, not silently absorbed.

*Second caveat, on where these numbers come from.* These are M4 static counts
from an `applegpu_g16s` host (Apple GPU generation 16). The ranked M5 compiles
the same MSL, but it is a different generation with a different scheduler, and
it is the only machine on which these kernels can actually execute
(`is_nax_available()` requires generation >= 17). Every count above is therefore
a statement about the *emitted instruction stream*, which is what the arms are
designed to control, and not a prediction of cycles.

### 2.1 Upstream-equivalence control

Run through `research/run_upstream_equivalence.sh` on the committed default
(probe 0), against the unchanged base revision. The two produce a **byte-identical
report**: prefill `maximumAbsoluteLogitError = 0.125`,
`meanAbsoluteLogitError = 0.011933609`, all eight decode steps exactly `0.0`, and
`runtimeToken == upstreamToken` at every checked position.

The non-zero prefill logit error is a **pre-existing near-tie divergence of this
M4 host**, not something the change introduces — which is exactly what "byte
-identical to the unchanged base" establishes. Reporting it as a clean pass
without that comparison would have been the misleading version.

## 3. Bit-exactness

`probe = 0` is the default on every path, so **the committed kernel is
unchanged and the arms are research state only**.

Per arm, at `probe != 0`:

- **M2** — `Dshadow` is a separate accumulator that is never mixed into
  `Dtile`; its only consumer is unreachable. No value the real chain sees
  changes.
- **S2** — the shadow staging pass writes exactly the same destination address
  set as the real pass (loader addressing depends only on `lid` and simd ids,
  and the sets are disjoint across threads); a threadgroup barrier separates
  the two, and no thread reads `Ws` in between. The real staging therefore
  overwrites the tile in full before any consumer reads it.
- **B2** — barriers are pure synchronisation and cannot change a value.

**Mechanically proven inert at `probe = 0`.** Building the base revision and
the head revision to LLVM IR and diffing gives exactly **70 differing lines**,
all of them Itanium mangling of threadgroup globals (`Ws_storage`, `bounds.0`,
`bounds.1`) gaining `Li0E` from the new defaulted template parameter.
Normalising `ELi0EE -> EE` and re-pairing leaves **zero unmatched lines**: the
default-arm machine code is identical, not merely equivalent.
`research/nax_safety_rig.sh` reports checks 1, 3, 4, 5, 6 PASS and check 2 FAIL
— check 2 uses `cmp -s`, which cannot see through mangling. The rig was left
strict on purpose rather than weakened to make the check pass.

*The landing interlock is inert at probe 0 too.* The throw added at
`quantized.cpp:1769-1773` (witness 2 in §4.4.1) is guarded by
`probe_requested != 0`, so on the shipped default it is dead code on a branch
that is never taken and cannot alter dispatch, kernel naming, or any value. It
is host-side C++ and does not appear in the kernel source at all, so it is
outside the IR diff above by construction; it was re-validated separately
(twin check, four-arm MSL compile, safety rig, host C++ syntax) after being
added.

Twin consistency (`python3 research/nax_twin_check.py`):
`TWIN CHECK: generated copy matches the header`, exit 0.

## 4. Pre-registered decomposition and decision rules

Registered **before** any receipt was spent, and implemented in
`research/tanjiro-pr170-receipts.py` so the verdict cannot be fitted afterwards.

Deltas are in ms of prefill wall `S = 512000 x prefill_s_per_tok`; the arms
touch only this kernel, so `ΔS = Δkernel`. Everything below is normalised by the
**measured** control wall `W = 43.2619 ms`, not by a theoretical peak.

### 4.0 What each arm actually measures

Let `m*` be the in-situ cost of the MMA stream and `d*` the in-situ cost of the
weight-load+dequant stream, under any overlap model
`W = max(m*,d*) + (1-f)·min(m*,d*)` with unknown `f ∈ [0,1]`.

- **M2** doubles MMA work. Algebra of the model gives `ΔM2 = m*` when
  `m* >= d*`, and `ΔM2 < m*` otherwise. So **`ΔM2` is a lower bound on `m*`**,
  tight exactly when MMA is the longer stream.
- **S2** doubles only the *weight* traffic and its dequant, not all bytes: it
  stages the **neighbouring** expert's slab (`(expert+1) % experts`), so the
  extra reads land on different cache lines and are real fetches rather than a
  re-read. The fraction of the load stream it doubles is derived exactly in
  §4.0.1 below (`w = 1.000` of the ledger's counted bytes, `≈ 0.915` of real
  DRAM traffic). Taking the conservative direction,
  **`ΔS2p` is a lower bound on `d*`**.
  *(An earlier draft claimed S2 doubles all `17.666 GB` of traffic and derived
  its bracket from the whole-kernel byte count. The bracket needed the factor
  `w`; the derivation below shows `w` happens to be `1.000` against the ledger's
  own byte figure, so the numeric bracket survives — but for a reason the draft
  had not established.)*
- **B2** adds two barriers per k-iteration. They sit at the top
  (`fp_quantized_nax.h` ~:1766) and bottom (~:1879) of the loop body, separated
  across the back-edge only by `xn += BK; loader_w.next()`, so they execute
  essentially back-to-back and **coalesce into roughly one real rendezvous per
  iteration**, not two.

That last point matters, because S2 adds exactly *one* barrier (at ~:1810, after
genuine staging work) and we must subtract it. `ΔB2/2` assumes the two B2
barriers are independent, which they are not, so it **underestimates** the
subtrahend and biases the result toward H2. `ΔB2` is the other extreme. The
pre-registered treatment is therefore an **interval**, and a rule only fires if
it fires across the whole interval:

```
ΔS2p ∈ [ ΔS2 - ΔB2 ,  ΔS2 - ΔB2/2 ]        (width = ΔB2/2)
```

This is provably adequate rather than merely convenient. The decision margin
below is `μ = 0.10·W = 4.33 ms`, so the interval can only change a verdict if
`ΔB2/2 > μ`, i.e. `ΔB2 > 8.65 ms = 0.20·W`. But `ΔB2 >= 0.20·W` already trips
**R1** and makes H3 the headline finding, at which point the H1-vs-H2 margin is
no longer the reported result. Whenever the H1/H2 comparison is the answer, the
interval is narrower than a third of the margin.

#### 4.0.1 What the ledger's two numbers actually count

Both ledger figures reproduce **exactly** from `weights/config.json`, which pins
down `w` instead of guessing it. With `hidden = 2048`,
`moe_intermediate = 512`, `experts = 256`, `top_k = 8`, `layers = 40`,
NVFP4 `bits = 4` / `group_size = 16` (so `4 + 8/16 = 4.5 bit = 0.5625 B` per
weight value), and a 512-token prefill:

```
values per expert   = 2*(2048*512) + 512*2048            =     3,145,728
FLOP  = 512*8 * 3,145,728 * 2 * L_moe                    with L_moe = 39
      = 1,005,022,347,264                                = 1005.022 GFLOP   (ledger: 1005.02)
bytes = 256 * 3,145,728 * 0.5625 * L_moe
      = 17,666,408,448                                   = 17,666.41 MB     (ledger: 17,666.41)
```

Two things fall out, neither of which was previously on the record:

1. `L_moe = 39`, not 40 — one of the 40 blocks is a dense MLP. Using 40 gives
   `1030.8 GFLOP`, and `39/40` is exactly the `0.975` discrepancy. The `39`
   is not fitted; it is the only integer that makes **both** figures exact.
2. The byte figure is **exactly the routed weight bytes** — all 256 experts
   streamed once per MoE layer — and therefore counts **zero** activation,
   scale-broadcast or output traffic. So the ledger's `17.666 GB` is a
   weights-only number, and `w = 1.000` with respect to it.

Against *real* DRAM traffic the fraction is slightly lower: the x-reads,
intermediate and y-writes add `4096*(2048 + 2*512 + 2048)*2 B ≈ 42 MB` per
layer against `453 MB` of weights, i.e. `w ≈ 0.915`. Both readings are used
below in the direction that weakens the claim.

*(Caveat kept explicit: S2's neighbour-slab reads are real fetches at the
instruction level, but expert `e+1` is also being genuinely loaded by some other
threadgroup in the same layer, so an unknown fraction may hit in the system
cache. That can only make `ΔS2` **smaller** than a true DRAM-miss doubling,
which is why `ΔS2p` is used as a *lower* bound on `d*` and never as an
estimate of it.)*

*(The cleaner instrument would have been an S2-sham arm — same barrier and same
threadgroup-store count at S2's exact position, zero device reads, zero dequant
— which makes the subtraction exact by construction. It is not used here: a sham
that writes the staging tile cannot be correctness-tested on this host at all
(the `_nax` kernel needs Apple GPU gen >= 17, this box is gen 16), and a
bit-inexact arm burns an irreplaceable receipt and publishes no metrics. Listed
in §9 as the follow-up if the interval ever turns out to matter.)*

#### 4.0.2 Which resources each arm perturbs, and which it provably does not

A null result is only publishable if it says *what was ruled out*, and that
requires naming the axes the arms actually moved. The table below is measured,
not asserted: it is a per-function static census of the post-optimisation LLVM
IR for both shipped threadgroup shapes, over the same four metallibs used in §2
(`research/nax_msl_compile_check.sh` with `EMIT_IR=1`, then
`research/tanjiro_probe_alu_census.py`). Counts are for the kernel body, so a static delta inside
the k-loop is also the dynamic delta per iteration.

| arm | shape | mma | barrier | dev_load | tg_load | tg_store | int_alu | float_alu |
|---|---|---|---|---|---|---|---|---|
| pb0 control | 2048x1024 | 1 | 7 | 6 | 4 | 5 | 87 | 5 |
| pb0 control | 512x2048 | 1 | 5 | 6 | 2 | 4 | 82 | 0 |
| pb1 M2 | 2048x1024 | 2 | 7 | 6 | 4 | 5 | 102 | 5 |
| pb1 M2 | 512x2048 | 2 | 5 | 6 | 2 | 4 | 97 | 0 |
| pb2 S2 | 2048x1024 | 1 | 8 | 8 | 4 | 6 | 91 | 5 |
| pb2 S2 | 512x2048 | 1 | 6 | 8 | 2 | 5 | 86 | 0 |
| pb3 B2 | 2048x1024 | 1 | 9 | 6 | 4 | 5 | 87 | 5 |
| pb3 B2 | 512x2048 | 1 | 7 | 6 | 2 | 4 | 82 | 0 |

Both shapes agree on every delta, so:

| arm | perturbed | provably unperturbed |
|---|---|---|
| **M2** | `mma +1`, `int_alu +15` | barrier, dev_load, tg_load, tg_store, float_alu |
| **S2** | `dev_load +2`, `tg_store +1`, `barrier +1`, `int_alu +4` | mma, tg_load, float_alu |
| **B2** | `barrier +2` | mma, dev_load, tg_load, tg_store, int_alu, float_alu |

**B2 is a perfectly clean single-axis arm** — barriers move and literally
nothing else does. That is stronger than §2 could show, because §2 never counted
ALU.

**M2 is not as clean as §2 implied, and this is a correction.** It carries
`+15` scalar integer ops against a control body of 87, a **+17%** increase in
integer ALU, from the address arithmetic for `Dshadow` and the extra
cooperative-tensor operand buffers. §2's confound table called M2 "CLEAN" on the
strength of memory and barrier counters alone; with ALU counted, that claim was
too strong. The honest statement is that M2 perturbs *two* axes.

This matters only in one branch of the decision table, and the asymmetry is
favourable. If `ΔM2 ≈ 0`, H1 dies and the integer confound is irrelevant — a
perturbation that cost nothing cannot have hidden a cost. The confound can only
bite if `ΔM2` is **large**, where "the MMA pipe is saturated" and "the scalar
integer pipe is saturated" both explain the result. Note that this is a second,
independent reason the same branch needs care: §2 already flagged that a large
`ΔM2` also admits a register-pressure/occupancy explanation that M4 reflection
cannot exclude.

**This is exactly what A2 discriminates, and it is why A2 is now worth more than
when the advisor proposed it.** A2 (`probe==4`) moves `int_alu` and *only*
`int_alu` — its own census shows mma, barrier, dev_load, tg_load, tg_store and
float_alu all unchanged — at roughly twice M2's integer amplitude. So:

- large `ΔM2` **and** `ΔA2 ≈ 0` ⇒ the integer confound is excluded, and `ΔM2` is
  MMA (or occupancy), not address arithmetic;
- large `ΔM2` **and** large `ΔA2` ⇒ `ΔM2` is not safely attributable to MMA at
  all, and H1 must not be claimed.

A2's pre-registered firing condition in §4.5 was "R5 null or R3 positive". That
condition is **widened here, before any receipt is spent**: A2 also fires if M2
comes back large, because in that branch A2 is no longer an optional extra axis
but the control that makes M2 interpretable. The receipt budget already reserves
a fourth receipt for exactly this.

**Axes no arm perturbs.** Threadgroup memory footprint (9232 B), maximum
threads per threadgroup (1024), threadgroup residency (3 per core), execution
width (32), kernel launch count, grid shape, `tg_load` traffic, floating-point
ALU, and output bytes written are identical across all four arms. A null across
M2/S2/B2 therefore does **not** exclude a constraint living in occupancy,
instruction fetch, threadgroup-memory bank conflicts on the *read* side, or
command-buffer/launch overhead. §9 carries those forward rather than letting the
null overclaim.


### 4.1 Instrument-failure floor (peaks used only as upper bounds)

This is the one place theoretical peaks appear, and only in the direction they
are actually trustworthy: a peak is an **upper bound on achievable rate**, so it
gives a **lower bound on time**. Even with perfect overlap the wall cannot be
below the longest single stream, so

```
                                                  W' - W = Δ floor
M2:  W' >= 2·m_peak       = 2 × 28.96  = 57.93  ->  ΔM2 >= 14.66   @34.7 TFLOP/s
S2:  W' >= (1+w)·d_peak   = 2 × 27.10  = 54.21  ->  ΔS2 >= 10.95   @651.8 GB/s
                          = 2 × 28.96  = 57.92  ->  ΔS2 >= 14.66   @610   GB/s
                          = 2 × 32.34  = 64.69  ->  ΔS2 >= 21.43   @546.2 GB/s
```

**The S2 triple does reconcile to one byte quantity; an earlier objection that
it did not was arithmetic error on my side.** The check is not `Δ × BW`, it is
`((Δ + W) / 2) × BW`, because `Δ` is the *increment* over the measured wall `W`
and the bound is on the *doubled* stream:

```
(10.95 + 43.26)/2 × 651.8 = 17.667 GB
(14.66 + 43.26)/2 × 610   = 17.666 GB
(21.43 + 43.26)/2 × 546.2 = 17.667 GB      <- all one 17.666 GB traffic model
```

So the three S2 rows are one physical claim evaluated at three candidate DRAM
bandwidths, and the honest form of the S2 floor is an **interval**,
`ΔS2 ∈ [10.95, 21.43]`, whose weakest end is what a gate may use.

**The M2 floor does not survive the same scrutiny, and I am withdrawing it.**
The `34.7 TFLOP/s` figure was back-derived to place this kernel's arithmetic
intensity exactly on the roofline ridge (`AI = 56.89 = 34700/610`). That is a
suspiciously tidy coincidence, and it is one: it is an artifact of choosing the
peak to make the ridge story work. Published M5-class NAX measurements (MLX
PR #3211 reports 52–60 TFLOP/s for fp16 GEMM) put the real peak well above it,
and the floor is extremely sensitive to that choice:

```
m_peak = 1005.02 GFLOP / peak            ΔM2 floor = 2·m_peak − 43.26
  @34.7 TFLOP/s ->  28.96 ms   ->  +14.66      (the back-derived figure)
  @52   TFLOP/s ->  19.33 ms   ->   −4.60      (no floor at all)
  @60   TFLOP/s ->  16.75 ms   ->   −9.76      (no floor at all)
```

At any realistic NAX peak the MMA stream is only ~17–19 ms of a 43.26 ms wall,
so **doubling it can hide entirely underneath the memory stream and cost
nothing**. A small `ΔM2` is therefore a *result* — MMA is not the binding
stream — and not evidence that the arm failed to land. Landing is established
structurally instead (§4.4.1), which is what makes it safe to drop this gate.

Note also what the memory side already tells us without any arm: `W = 43.26 ms`
against `d_peak ∈ [27.10, 32.34]` means the unmodified kernel is already
sustaining **63–75% of peak DRAM bandwidth**. That is a high figure, and it is
the strongest prior in this document that H2 rather than H1 is the live
hypothesis.

Applying ~12% for receipt noise and residual optimism in the surviving peak:

| gate | condition | meaning |
|------|-----------|---------|
| **R0a** | `ΔS2 < 9.5` | **instrument failure on the S2 axis only** — 17.7 GB of extra traffic cannot cost less than this at any plausible bandwidth, so a smaller delta means the staging pass did not land. Void the S2 receipt and debug before spending more. **There is deliberately no `ΔM2` half to this gate** (see the withdrawal above); a small `ΔM2` is read as a datum by R2/R6, not as instrument failure. |
| **R0b** | `ΔM2 > 33.3` or `ΔS2 > 37.2` | **flag** — delta exceeds the arm's own peak-bound isolated cost (`28.96`, `32.34` @546.2) by >15%; the arm perturbed something beyond its axis (register pressure / occupancy). Report, do not silently accept. |
| **R0c** | receipt returns `status=failed` with `officialMetrics = null` | **instrument failure, not a datum** — see §4.3. Do not re-fire the same arm; stop and diagnose. |

### 4.2 Decision rules

Registered before any receipt was spent and implemented in
`research/tanjiro-pr170-receipts.py`. Margin `μ = 0.10·W = 4.33 ms`; the rules
are evaluated in order and are exhaustive.

| rule | condition | verdict |
|------|-----------|---------|
| **R6** | `ΔM2 <= -μ  (-4.33)` | **H3 wins, latency variant** — doubling independent MMA work made the kernel *faster*. The only mechanism that does this is instruction-level parallelism filling issue stalls, so the MMA pipe is **latency-bound, not throughput-bound**. Evaluated first; overrides R1–R5. |
| **R1** | `ΔB2 >= 0.25·W  (10.82)` | **H3 wins** — schedule latency is the dominant cost; next mechanism is barrier removal / deeper pipelining / occupancy |
| R1' | `0.10·W <= ΔB2 < 0.25·W` | H3 **material** — real, first-order, but not dominant; reported alongside the R2–R5 verdict |
| R1'' | `ΔB2 < 0.10·W` | H3 minor on the barrier axis |
| **R5** | `ΔM2 < μ` **and** `ΔS2p_hi < μ` | **H3 by elimination** — *neither* axis is paid for, so a third cost (dispatch, occupancy, latency) dominates. Evaluated first among R2–R5 so the boundary is deterministic. |
| **R2** | `ΔM2 >= μ` **and** `ΔS2p_hi < μ` | **H1** — MMA-limited |
| **R3** | `ΔS2p_lo >= μ` **and** `ΔM2 < μ` | **H2** — load+dequant-limited |
| **R4** | `ΔM2 >= μ` **and** `ΔS2p_lo >= μ` | **H0** — jointly balanced; both axes cost real time, so a single-axis reduction is Amdahl-capped by the other |

R2–R5 are one **2×2 on the individual magnitudes**, with "large" meaning
"exceeds `μ`":

|            | `ΔS2p` small | `ΔS2p` large |
|------------|--------------|--------------|
| `ΔM2` small | **R5** — H3, latency | **R3** — H2, load-bound |
| `ΔM2` large | **R2** — H1, compute | **R4** — H0, jointly saturated |

**A rule I had to fix before spending a receipt.** The draft I registered first
made R5 a *sum* test, `ΔM2 + ΔS2p_hi <= W - μ ⇒ H3`. That rule is wrong, and
wrong in a way that would have silently produced a confident false verdict.
Under H1 the delta pair is approximately `(W, 0)`; under H2 it is approximately
`(0, W)`. **Both sum to about `W`**, which is below the `W - μ` threshold only
by the margin itself — so a textbook H1 or H2 result would have been read as
"neither axis accounts for the wall, therefore H3". The sum separates exactly
one thing: H0 (where doubling *either* axis makes that axis the sole bottleneck
at `2×`, so each delta is ≈`W` and the sum is ≈`2W`) from everything else. It
cannot distinguish H1 from H2 from H3, which is the entire question. I verified
the failure concretely: with `(ΔM2, ΔS2p, ΔB2) = (2, 30, 1)` — a load stream
costing 68% of the kernel wall, about as unambiguous an H2 as this instrument
can produce — the old rule returns **R5/H3**. The 2×2 above returns R3/H2.

The sum survives as a **corroboration line only**, never as a verdict: the
script prints whether `ΔM2 + ΔS2p_hi` is consistent with H0 (`>= 2W - μ =
82.20`), with a single saturated stream (`<= W + μ = 47.59`), or with neither
(reported as ambiguous). It is printed after the verdict and cannot change it.

**Why R6 exists, and why it is not a curiosity.** NAX matrix instructions have
long issue-to-result latency — order 256 cycles for a `32x32x32` tile on A19-class
hardware. A pipe with that latency and only one dependent MMA in flight per
accumulator is **latency-bound long before it is throughput-bound**: the
measured cost is dominated by waiting, not by issue slots. The M2 arm adds a
*second, independent* accumulator chain, which is precisely the input a
latency-bound pipe needs to fill its stalls. So the naive reading — "M2 was
flat, therefore MMA is not the constraint, therefore H0/H2" — is wrong in the
one case that matters most, and `ΔM2 < 0` is close to a proof of latency-bound
operation rather than a null result. Without this row the experiment would
systematically misclassify its most informative outcome.

**Scoping the H0 verdict (R4).** If R4 fires I will not write "the kernel is
balanced" without qualification, because that claim is broader than the
instrument. A clean null here means exactly: *along the two axes these arms
perturb* — MMA issue and threadgroup staging traffic — neither is separately
dominant at margin `μ`. It says nothing about axes the arms do not touch:
address generation and bitfield extraction, scalar-ALU dequantisation, the
routing gather itself, occupancy, or command-buffer overhead. It is also worth
stating in advance that the `67%/67%` two-stream signature which R4 would report
is **algebraically forced** whenever the two streams sit near the ridge and
overlap by about half; it is what the model predicts, not independent
confirmation of it. A2 (§4.5) is the arm that would extend the scope.

**R7 — decode negative control (applies to every receipt).** All three probes
are inside `gather_qmm_rhs_nax`, which the decode path does not reach: decode is
`M == 1` and takes the `qmm_rhs` route, and in any case the probe suffix is only
appended on the prefill-shaped dispatch. Decode is therefore a **within-receipt
placebo channel**, and it carries two independent checks.

*Leak check.* The arm's **raw candidate** decode must match the control's:

```
|decode_ms_per_step(arm) − 4.90837| / 4.90837  <  0.02
```

A shift larger than 2% means the probe did *not* stay inside the prefill-shaped
dispatch — the arm leaked into a kernel the decode path reaches — and the
prefill delta is no longer attributable to the axis I named.

*Session-health check.* Separately, that receipt's **own paired baseline**
decode must match the feed-wide median:

```
|baseline_decode_ms_per_step(arm) − 13.86539| / 13.86539  <  0.01
```

The 1% tolerance is not arbitrary: across the audited feed the harness baseline
decode has a coefficient of variation of **0.22%**, so 1% is roughly `4.5σ`.
A receipt whose baseline decode sits outside that band was measured in a session
that does not resemble the rest of the feed (thermal, scheduler, or a
non-comparable baseline), which contaminates its prefill number too.

An earlier draft folded these into one test,
`|decode_spt − baseline_decode_spt| / baseline < 0.03`. That comparison is
nearly meaningless here: candidate and baseline decode differ by a factor of
`2.82` *by design*, so the quantity is always ≈`0.65` and the test can never
fire. Splitting it into a leak check against a known-good candidate value and a
health check against the feed median makes both halves live. A receipt failing
either is **reported as suspect** and is not used to settle H1 vs H2 on its own.
Both checks cost nothing: the numbers are already in every receipt.

**Deleted rule.** An earlier draft carried an R5 reading "both deltas high ⇒ the
streams do not overlap; fix overlap, not either axis". It was self-contradictory
and is withdrawn: two fully serial `28.99 ms` streams would give a `57.98 ms`
wall, but the measured wall is `43.26 ms`, so the streams demonstrably *do*
overlap by about half. Worse, the model algebra in §4.0 shows that doubling an
equal stream yields `Δ = min stream` **for every value of `f`**, so
"both deltas high" is exactly what H0 predicts and carries no information about
overlap at all. That cell is now **R4/H0**, which is the correct reading.

R5 has therefore been through two withdrawals, both caught before any receipt
was spent: the overlap rule above, then the sum rule in §4.2. Both failed the
same way — they were stated in terms of a *composite* of the two deltas (their
sum, or "both high") when the hypotheses are distinguished by the deltas
*individually*. The 2×2 is the honest form of the test, and I record the two
dead ends rather than presenting it as the original design.

### 4.3 Floor safety, and what a below-floor run would actually publish

This section was rewritten at **2026-08-07T00:20Z**, before any receipt was
spent, after auditing the full public submissions feed
(`n = 1583`; `curl -H "Authorization: Bearer $MLXFAST_API_TOKEN"
https://api.mlx.fast/api/benchmarks/eigenlabs%2Fmlxfast-challenge/submissions`).
The audit was prompted by a reviewer challenge that the arms would fall below
the prefill floor and publish nothing. **The challenge was arithmetically
wrong but its underlying worry is real**, and both halves are now on the record.

**The floor is measured against the paired baseline, not against the frontier.**
The reviewer divided arm cost into the *frontier candidate* wall (97.9 ms) and
concluded every arm lands at `prefill_speedup ≈ 0.72–0.89`. The published
metric is `baseline_prefill / candidate_prefill`, and the last 200 metric-bearing
receipts draw a baseline of `186.08 / 191.18 / 201.31 ms`
(min / p50 / max, per 512-token prefill). Our frontier sits at
`97.895 ms`, i.e. `prefill_speedup ≈ 2.0`. Against the **smallest baseline draw
ever seen** in that window the largest admissible candidate is
`186.08 / 0.95 = 195.87 ms`, so the injection headroom is **97.98 ms**. The
largest arm delta the over-cost flag R0b even permits is `33.3 ms`, giving a
worst-case `prefill_speedup = 186.08 / (97.895 + 33.3) = 1.418` and a margin of
**2.94×** on the `0.95` floor. No arm can trip either floor, and no arm touches
decode.

Acting on the challenge as filed would have required shrinking every arm to
`≤ 4.5%` prefill cost — below the `μ = 4.33 ms` decision margin and comparable
to the `± 0.402 ms` control noise — destroying the experiment for no reason.
Verification, not deference, was the correct response.

**But the failure mode the challenge feared is real, and is now measured.**
A run that misses a floor does not publish degraded metrics; it publishes
*none*:

- `0 / 1091` metric-bearing receipts carry `passed_prefill_speedup_floor` or
  `passed_decode_speedup_floor` equal to `false`;
- all `489` `status = failed` records have `officialMetrics = null` — null, not
  partial — and `17` of them failed precisely at the step
  *"Overlay paired timing into final score"*, which `AGENTS.md` names as the
  floor-enforcing step;
- the minimum published `prefill_speedup` over all 1091 is `0.95236`, a hard
  edge sitting on the `0.95` floor.

**The arms' expected outcome class is confirmed to publish full magnitudes.**
Receipt `6447b89c` is a candidate that ran **4.8% slower than its own paired
baseline** (`prefill_speedup = 0.95236`) and still published
`prefill_seconds_per_token = 0.000398266357421875` alongside
`baseline_prefill_seconds_per_token = 0.000379291912109375`, with
`status = rejected`, reason *"score did not improve current best"*. That reason
accounts for **948 of 948** rejections: `rejected` means *passed every gate,
did not beat best*, which is exactly what each arm should return. `rejected` is
**not** the below-floor outcome; `failed` is.

Wall clock is not a constraint either: `benchmark_wall_seconds` runs
p50 = 46 s, p95 = 49 s, max = 54 s across all 1091, and `timed_benchmark_seconds`
p50 = 39 s. A ~33 ms per-prefill-pass increase is invisible against that, and
the 1-hour-timeout failure bucket is unrelated infrastructure failure.

**New abort gate R0c (pre-registered).** If any arm returns `status = failed`
with `officialMetrics = null`, that is an **instrument failure, not a datum**.
It must not be read as a null result, must not be re-fired on the same arm, and
the campaign stops to diagnose. Raw evidence for this subsection is archived at
`research/artifacts/tanjiro-pr170-feed-audit.txt`.

### 4.4 Arm ordering, and what it buys

Arms are dispatched **M2, then S2, then B2**. The ordering is chosen so that
the arm carrying the surviving peak-derived floor (S2, gate R0a) runs before the
arm with no floor at all (B2), and so that M2 — the arm whose result is most
diagnostic under R6 — is not left until the budget is nearly gone.

What the ordering does **not** do any more is establish landing. An earlier
draft argued that a large M2 or S2 delta demonstrates the plumbing works and so
disambiguates a later `ΔB2 ≈ 0`. That argument is now redundant at best and
circular at worst, and §4.4.1 replaces it with three structural witnesses that
hold for every arm independently of effect size.

*Caveat on direct verification.* The dispatch-site trace fires whenever a probe
is requested and prints `active`/`inactive` with the kname handed to the JIT,
but the M5 receipt does not surface stderr, and the kernel cannot run locally
(this host is `applegpu_g16s`, Apple GPU generation 16; `is_nax_available()`
requires >= 17, enforced at
`Vendor/mlx-swift/.../backend/metal/device.cpp:927`).

#### 4.4.1 Landing is witnessed structurally, not inferred from the ordering

Added **2026-08-07T00:22Z**, before any receipt. A reviewer pointed out that
the R0a void gate as originally written — *"`ΔM2 < 13.0` ⇒ the probe did not
land"* — is a logic error: under H2 or H3 a **small `ΔM2` is the informative
outcome**, and a rule that voids it can only ever confirm H1. That is
corrected here, which requires landing to be established by something other
than the size of the effect. Three independent structural witnesses now do
that, and none depends on any delta being large.

1. **The kernel builder cannot silently substitute a non-probe kernel.**
   `get_qmm_nax_kernel` (`.../metal/jit_kernels.cpp:1225-1255`) has no
   `try`/`catch` and ends in a bare `d.get_kernel(kernel_name, lib)`. A JIT
   compile failure, a missing symbol, or a pipeline failure throws at
   `.../metal/device.cpp:641-648`, `:692-699`, `:716-724` respectively; the
   `nojit` path (`nojit_kernels.cpp:417-423`) throws identically. There is no
   edge that falls back to a non-`_nax` or non-`_pb_<n>` kernel. So if the
   arm's `_pb_<n>` kernel had not built, the run would be
   `status = failed` with null metrics (gate R0c), never a healthy null.

2. **The one remaining silent-degradation path has been closed by an
   interlock.** `gather_probe = expert_aligned ? probe_requested : 0` meant
   that if `expert_aligned` were false on the ranked M5, every arm would
   quietly inject nothing and publish a healthy receipt reading `Δ ≈ 0` —
   indistinguishable from a true H3 null, and the single failure mode capable
   of consuming the entire receipt budget without producing a datum.
   `quantized.cpp:1769-1773` now throws instead, in the same idiom as the
   pre-existing kernel-selection assert at `:1736`. Probe 0 — the shipped
   default and the only state the frontier would ever carry — cannot reach it.

3. **Only one dispatch is selectable, and it is the one analysed.** With the
   official runner's stripped environment the defaults are
   `EXPERT_ALIGNED_GATHER` on (`quantized.cpp:1328-1331`), `STAGE_BM128 = 5` ⇒
   `bm=64, wm=4, wn=1` (`:1491-1502`, `:1692-1700`), `egroups = 256`
   (`:1402-1412`), `BK128` off (`:1383`) ⇒ `bk = 64`. The sole reachable name
   is
   `nvfp4_gather_qmm_rhs_expert_static_nax_nt_bfloat16_t_gs_16_b_4_bm_64_bn_64_bk_64_wm_4_wn_1_k_<K>_n_<N>_eg_256_ws_1_wl_{0|1}`
   for both Laguna shapes, which matches the pipeline set the assignment names
   as the stop-and-report criterion — **no stop-and-report trigger**. Escaping
   to the non-expert builder needs an env override or `M < 64`, and `M < 64` is
   impossible: `GatherQMM::eval_gpu` enters only when
   `M==1 && B>=16 && right_sorted_ && B/E>=4` (`:2325`), which with `E=256`
   forces `B >= 1024`. `_wl_` may still flip 0/1 on the runtime `w.offset()`
   certification (`:1757-1759`); both values are the same kernel function.

**Taken together: any arm that returns a receipt with metrics at all has
provably armed.** A null is therefore a real null, which is what makes a clean
H3 reading merge-worthy rather than ambiguous.

*Also confirmed while checking (3):* **no split-K, atomic-accumulate or
partial-reduction variant is reachable** on this path. `gather_qmm_rhs_nax` has
exactly one `dispatch_threadgroups` (`quantized.cpp:2053`); all split-K in the
file belongs to `qvm_split_k` (`:302`) and `qmm_splitk` (`:812`), reached only
from the non-gather `QuantizedMatmul` route. `matmul.cpp:2056 gather_mm_rhs_nax`
is unreachable for us — it is called only from the *unquantized*
`GatherMM::eval_gpu` (`matmul.cpp:2484-2487`), while the runtime calls
`MLX.gatherQuantizedMM` ⇒ `GatherQMM::eval_gpu` (`quantized.cpp:2297`). MLX
issue #3584 (split-K firing wrongly), raised in the assignment as a risk,
therefore cannot touch this measurement.

### 4.5 The spare receipt: A2, pre-registered but conditional

The budget is four receipts for three arms. The fourth is **not** a replicate
and **not** a free choice made after seeing results; committing to it in advance
is the only thing that keeps it from becoming a fishing licence.

**A2 — scalar-integer decode pressure.** Shadow the NVFP4 unpack: recompute the
4-bit field extraction into a second set of registers that no consumer reads,
without adding a device load (the values are already resident) and without
adding an MMA. This isolates the **scalar-integer ALU axis**, the one
first-order resource none of M2, S2 or B2 perturbs — the exact gap the H0
scoping paragraph in §4.2 admits. Two independent lines of criticism converged
here: the advisor proposed it as an optional fourth arm, and a separate review
arrived at the same place from a dequantisation-cost argument.

**A correction to the arm's stated motivation, which I want on the record
because it weakens the case I was handed.** The advisor motivated A2 from the
AGX ISA notes: dynamic `BITEXTRACT`/`BITINSERT` cost 8–12 cycles against ~1 for
the constant-operand form, so NVFP4 unpack should be expensive. I read the
actual decode before building anything. `fp4nv_decode8`
(`fp_quantized_nax.h:165-188`) is
`xe = c & 0x0F0F0F0F; ge = xe | (xe << 3); yo = c & 0xF0F0F0F0; go = yo | (yo >> 3);`
plus four `(shift) & 0x8E008E00` — **13 integer ops, every shift and mask a
compile-time constant**. There is no dynamic-shift bitfield extract anywhere on
this path, so the 8–12-cycle class the argument rests on does not occur. The
per-k-iteration pointer math is one 64-bit and one 32-bit add (`next()`,
`:505-512`), and the alignment predicates (`:378-404`) are loop-invariant and
hoist. So A2's expected effect is smaller than the motivating argument implies,
and I am recording that *before* the receipt rather than discovering it in the
post-mortem.

That does not make the arm worthless — it makes it a cleaner instrument. The
integer decode is real work on a real pipe; it is simply the ~1-cycle form.

**Design chosen: "integer skeleton", not full re-decode.** The obvious
implementation — re-run all of `fp4nv_decode8` — is impure, because it also
doubles the floating-point tail (~24 cvt/fmul lanes per uint32), so a positive
could not separate integer-pipe from FP-scalar-pipe pressure. A purely
synthetic dynamic-BITEXTRACT chain is worse: wrong cost class, uncalibratable
against the real chain, and loop-invariant so LICM hoists it out. The chosen
arm re-runs only the **13-op integer skeleton** on the register-resident code
bytes, XOR-perturbed by a seed derived from the runtime scalar `run_skip_pct`
so CSE cannot prove it equals the real chain, XOR-folded into four independent
accumulators that mirror the real chain's ILP width of 4 (adding *issue*
pressure, not a serial latency chain), and escaping through the same
never-true guarded sink arm M2 uses. Injected/real ≈ **1.38×** of the integer
decode term, and because the injected ops are the same classes on the same
pipe, the cycle ratio tracks the op ratio to roughly ±15% — far tighter than
any synthetic chain could be calibrated.

The injection point is forced: `QuantizedBlockLoader::load_unsafe_wide`
(`:406-479`), the only place the codes are live in registers (`uint8_t
sb[kSrcBytes]`) with no reload. Anywhere in the kernel body would require
re-reading device or threadgroup memory and would pollute the axis.

**A2 also subtracts a term from S2.** S2 bundles bytes + integer decode + FP
decode + stores + one barrier. If S2 comes back as the dominant positive, A2 is
the only instrument in this set that can say how much of that was the integer
term. The firing condition below is widened accordingly.

**Firing condition, registered now.** A2 is dispatched **only** when all three
of the following hold:

```
R5 fires      ΔM2 + ΔS2p_hi <= W − μ   (the measured axes cannot account for W)
R1'' holds    ΔB2 < 0.10·W             (and it is not the barrier axis either)
R6 does not   ΔM2 > −μ                 (and it is not the ILP-latency signature)
```

That conjunction is the one genuinely unresolved state this instrument can
reach: every axis it perturbs came back small, so the constraint provably lies
on an axis it does not touch, and A2 is the cheapest probe of the most likely
candidate. Note this is *not* the same as "R4 fired" — R5 is evaluated before R4
and overrides it, so an R4/H0 verdict means the measured axes **did** account
for the wall. That is a clean, scoped null and the spare is not spent on it.
Equally, if R6, R1 or R2 fires the question is answered and a fourth receipt
buys nothing.

**One widening, registered before any receipt.** A2 also fires on **R3**
(`ΔM2` small, `ΔS2p_hi` large ⇒ H2 load-bound). The reason is attribution, not
curiosity: S2 is the least pure arm in the set, because doubling the staging
bundles *five* things — device bytes, integer decode, FP decode, threadgroup
stores, and one barrier (§4 already subtracts the barrier via B2). If R3 fires,
"load-bound" is still four mechanisms wide, and A2 is the only instrument here
that can remove the integer-decode term from that bundle. An R3 verdict with A2
is a mechanism; an R3 verdict without it is a direction. Since the whole point
of this experiment is to name the *next* thing to optimise, I would rather
spend the spare narrowing a positive than leave it unspent.

So the spare is spent on exactly two reachable states — the R5 null and the R3
positive — and on nothing else.

**Why A2 is built but not queued.** A2 is a materially harder arm to make
bit-exact and confound-free than the other three: the unpack chain feeds the
real accumulator, so a shadow copy has to be provably unread while surviving CSE
against the real chain it duplicates — much more delicate than M2's separate
accumulator or B2's pure barriers. Building and censusing it to the §2 standard
*before* the first receipt would have delayed all three clean arms behind a
harder fourth.

It turned out not to be a trade at all. The binding constraint on this
experiment is not my time, it is the **submission queue**: one in-flight
submission per account, shared with three other students, at roughly one
receipt per hour (§5.1). Each arm therefore leaves ~45–70 minutes of dead time
in which no dispatch is possible. A2 is built in that dead time, *after* M2 is
already queued, so it costs the three-arm campaign nothing.

Two safeguards make that safe rather than merely convenient:

1. **The three submitted paths stay frozen while a dispatch is possible.** A2
   is developed against a `/tmp` copy of `mlx-generated/` using the `GEN_DIR`
   override that `research/nax_msl_compile_check.sh` already supports, so the
   working tree stays byte-identical to the validated state and can be
   dispatched the instant the queue opens. Only `research/` files — which are
   not in `editablePaths` and are not packaged by `mlxfast submit` — are edited
   in the interim.
2. **A2 is merged into the tree only if its firing condition is met.** If M2,
   S2 or B2 answers the question, the patch is reported and discarded, not
   submitted. Arms 1–3 are therefore never carried to the M5 with a fourth
   arm's dead code compiled alongside them.

So the honest statement of the choice the advisor asked for is: **I took the
optional fourth arm, on the condition that it never delays or contaminates the
three that were already clean.**

### 4.6 Instrument noise, measured — and which estimator to use

Every threshold above is stated in milliseconds of prefill wall, so the whole
design rests on a number I had not measured: **how much does the official
prefill wall move between two receipts that should be identical?** Guessing it
would have been the weakest link in the experiment, so I estimated it from the
1583-submission feed.

**The selection has to be non-circular.** I cannot select receipts by their
prefill wall and then measure the spread of the prefill wall. Instead I selected
on a *different* axis: the `n = 16` receipts whose **candidate decode** lies
within 1% of the control's `4.90837 ms/step`. Decode and prefill are separately
timed phases; agreeing on decode does not force agreement on prefill. Those 16
are effectively repeat measurements of a near-identical candidate, so their
prefill spread is instrument noise rather than signal.

| quantity | sample sd | relative |
|---|---|---|
| **candidate prefill wall `S`** | **0.318 ms** | **0.33%** |
| paired *baseline* prefill wall | 3.997 ms | 2.1% |
| paired estimator `188.5 / prefill_speedup` | 2.139 ms | — |

**This changes which number I read off a receipt.** The obvious choice was the
paired `prefill_speedup`, since that is what the harness ranks on and pairing
normally cancels session drift. It is the wrong choice here. The harness
baseline prefill wall is **12.6× noisier** than the candidate's, so dividing by
it *injects* that noise: the paired estimator is **6.7× worse** than simply
reading the raw candidate wall. Pairing helps when the two members share a
noise source; here the baseline is the dominant noise source. So every delta in
§4.2 is computed from **raw candidate prefill seconds/token**, and
`prefill_speedup` is used only for the floor check it exists to serve.

This asymmetry is specific to prefill. Baseline *decode* is stable — coefficient
of variation **0.22%**, feed median `13.86539 ms/step` — which is exactly why R7
can use it as a session-health tripwire at a 1% tolerance while the prefill
baseline cannot be trusted the same way.

**The arms are hugely over-powered, which makes a null informative.** A delta is
a difference of two receipts, so its noise is `σ_Δ = 0.318·√2 = 0.449 ms`. The
decision margin is `μ = 4.326 ms`, which is therefore **9.6σ**. Anything beyond
`±1.35 ms` is already `3σ`. This is the property that lets me report a clean
H0/H3 null as a *result* rather than as a failure to detect: if both axes come
back inside `μ`, the instrument had roughly ten sigma of headroom to see them
and did not, so "neither axis is separately dominant" is a measurement, not an
absence of one. It also means replicating any arm would be a waste of a receipt
— at `9.6σ` a second sample cannot change a verdict — which is why the fourth
receipt is reserved for a *different* axis (A2, §4.5) rather than a repeat.

**Caveat.** `n = 16` gives the sd itself about `±18%` relative uncertainty, and
those 16 receipts are not my arms — they are other candidates that happen to
decode like the control. If an arm's own session is unusually noisy, R7's
baseline-decode health check is the tripwire that should catch it.

## 5. Receipts

### 5.1 Dispatch log

The official submission queue enforces **one in-flight submission per account**
(`morganmcg1`), shared by every student in this campaign. All three arms
therefore serialise behind whatever else the campaign is submitting, and each
dispatch below records its own attempt history.

| UTC | arm | event |
| --- | --- | --- |
| 2026-08-06T23:47:16Z | m2 | client-side reject: note 3251 B < 5120 B minimum. No receipt consumed. |
| 2026-08-06T23:52:34Z | m2 | server reject: `conflict` — account already has 1 submission in flight (limit 1). No receipt consumed. |
| 2026-08-06T23:54:11Z | m2 | server reject: `conflict` — same in-flight submission. No receipt consumed. |
| 2026-08-07T00:22:36Z | — | queue still occupied: submission `99b7125` has been `validating` since 2026-08-06T23:29Z (~53 min, against a p95 benchmark wall of 49 s). Dispatch deferred; window used to land the §4.1/§4.2/§4.5 pre-registration corrections instead. |
| 2026-08-07T00:38:22Z | — | `99b7125` cleared (`rejected`, score `2.55562`) after ~69 min in `validating`, but `4f546a8` entered the queue at 00:29Z. Still occupied. Window used to land §4.6 and the R5/R7 corrections. |
| 2026-08-07T00:41:28Z | m2 | server reject: `conflict` — `4f546a8` still in flight. No receipt consumed. Working tree restored to probe 0 immediately after. |
| 2026-08-07T00:47:11Z | — | queue check: `4f546a8` still `validating`. No dispatch attempted. |
| 2026-08-07T01:00:43Z | — | queue check: `4f546a8` still `validating`. No dispatch attempted. |
| 2026-08-07T01:04:06Z | — | queue check: `4f546a8` still `validating` (~35 min). No dispatch attempted. |
| 2026-08-07T01:06:17Z | — | queue check: `4f546a8` still `validating` (~37 min). Window used to correct the register column in `research/tanjiro_metallib_stats.swift` (advisor §7) and to design arm A2 (advisor §2). |
| 2026-08-07T01:13:50Z | — | `4f546a8` cleared (`rejected`, `2.46709`) after ~44 min — but a different campaign submission `89521f6` had already entered the queue at 01:10Z, ~3 min after the slot opened. Still occupied, no dispatch possible. |
| 2026-08-07T01:17:26Z | m2 | server reject: `conflict` — `89521f6` in flight. No receipt consumed. Tree auto-restored to probe 0 in the same command. |
| 2026-08-07T01:22:55Z | m2 | server reject: `conflict`. No receipt consumed. |
| 2026-08-07T01:25:22Z | m2 | server reject: `conflict`. No receipt consumed. |
| 2026-08-07T01:31:05Z | m2 | server reject: `conflict`. No receipt consumed. |
| 2026-08-07T01:32:23Z | m2 | server reject: `conflict`. Fifth submit attempt inside the 01:00Z hour. |
| 2026-08-07T01:32:28Z | m2 | **rate limit**: `Rate limit reached. Try again in 1651 seconds` (→ 01:59:59Z). Sixth attempt of the hour. No receipt consumed. |
| ~2026-08-07T01:37:00Z | — | `89521f6` cleared (`rejected`, `2.48216`). The slot opened while my own hourly submit budget was exhausted. |
| 2026-08-07T01:37:15Z | m2 | rate limited, 1362 s (→ 01:59:57Z). Retry-after did not move out, so a blocked attempt carries no extra penalty. |
| 2026-08-07T01:38:50Z | m2 | rate limited, 1271 s (→ 02:00:01Z), from the first pass of the new watcher. Slot observed **free** and still free at 01:39:29Z. |

**Two dispatch tactics were tried. The first was wrong, and it cost a cycle.**

From 01:17Z I made every queue check a real dispatch attempt, on the reasoning
that a `conflict` is free and a passive check can never win a three-minute race.
That reasoning was incomplete. The submit endpoint is **rate limited to roughly
five or six attempts per clock hour, resetting on the hour**, and a `conflict`
reply still consumes one. (The exact ceiling is not directly observable because
the counter is shared — see below. What is observable is that six calls reached
the endpoint in the 01:00Z hour before it refused: the `89521f6` submission
another student filed at 01:10Z, plus my five.) I spent the rest of that hour's
budget on five losing attempts between 01:17Z and 01:32Z, hit the limit at
01:32:28Z, and the slot
then opened at ~01:37Z with nothing left to spend. The slot was still free two
minutes later. A correctly paced agent would have taken that receipt.

This is worth stating plainly because the failure mode is general: when a shared
resource is guarded by *both* an occupancy lock and a rate limit, polling the
lock through the rate-limited endpoint converts a queueing problem into a
starvation problem.

**Measured contention model.** The account is `morganmcg1`
(`solverAccountId b6799236-…`), shared by four students, and the benchmark
allows one in-flight submission per account. From this account's own 41-receipt
history, the gap between one receipt completing and the next claim being filed
is 6, 25, 29, 38 and 45 s. Run durations are 20–59 min and highly variable, so
the opening time is not predictable to better than tens of minutes. The
consequence is that the slot must be *watched*, not *checked*: any strategy whose
reaction time exceeds ~30 s loses essentially every cycle.

**The rate limit is account-wide, not per-student.** This was not obvious and it
changes the tactical picture, so it is worth the evidence. The slot opened at
~01:37Z and my watcher then observed it **continuously free from 01:38:50Z to
01:45:13Z and beyond** — more than eight minutes. Against the measured handoff
distribution above (6, 25, 29, 38, 45 s), a slot sitting empty for eight minutes
is not something the three other students would allow if they were each holding
their own submit budget. The parsimonious reading is that the ~5–6 attempts per
clock hour are counted against `solverAccountId b6799236-…`, so when I exhausted
the 01:00Z hour I exhausted it for the whole campaign. Two consequences follow.
First, the cost of my 01:17–01:32Z polling mistake was borne by four students,
not one. Second, at each reset boundary all four students are released
simultaneously into a race for one slot, which is why the watcher is built to
attempt within ~12 s of the reset rather than on a leisurely cadence.

I could not surface this to the other students mid-flight: `push_branch` is an
advisor-owned transition and a student's only publishing route is the terminal
result. It is recorded here instead, prominently, because it is a campaign-level
operational finding rather than a fact about this kernel.

**Corrected tactic (`research/tanjiro-pr170-dispatch.py`).** Poll a free status
source frequently and spend a rate-limited submit attempt only when the slot is
actually free. `mlxfast submissions` is that source — scoped to this account,
independently authenticated, ~9 s per call, and not subject to the submit limit.
Two cheaper alternatives were rejected: the public feed endpoint returns all 1588
submissions as 17.8 MB and rejects `limit`/`status`/`page` with 502, and
`GET /api/submissions/{id}` is only 18 KB but requires knowing the current
in-flight id, which is exactly what is unknown after a lost race. The watcher
verifies the three submitted paths are byte-identical to `HEAD`, arms the probe
constant only for the seconds spanning one `mlxfast submit` call, restores on
every exit path including `finally` and `KeyboardInterrupt`, and stops on the
first non-conflict response so a receipt is never spent twice.

**Observed queue latency.** Two campaign submissions have now been timed end to
end from this account: `99b7125` took ~69 min and the one before it ~53 min,
against a p50 `benchmark_wall_seconds` of 46 s. So `validating` is ~98% queue
and review, not measurement. The practical dispatch cadence for this account is
therefore roughly **one receipt per hour**, shared across four students. Three
arms is a ~3-hour serial campaign in the best case, which is a further reason
not to spend a receipt replicating an arm the noise analysis (§4.6) already
shows is measured at `9.6σ`.

<!-- RECEIPTS -->

## 6. Reading

<!-- READING -->

## 7. Decode control

<!-- DECODE -->

## 8. Next mechanism

<!-- NEXT -->

## 9. Follow-ups

<!-- FOLLOWUPS -->

**Registered before any receipt, so they cannot be mistaken for post-hoc
excuses.**

**Layer multiplexing is not identifiable, and I am not going to attempt it.**
An obvious-looking extension is to arm the probe on only a subset of the 39 MoE
layers and read the dose-response. It does not work: one receipt yields one
number, so arming `k` of 39 layers gives a single equation in two unknowns
(per-layer cost and the number of layers actually armed) and cannot separate
them. Nothing short of one receipt per dose makes it identifiable, and the
budget is four. Recording this so that a future reader does not spend receipts
rediscovering it.

**Dose-response is not 2×, and the arms do not assume it is.** The arms double
one axis, but `Δ` is a *marginal wall* increment against an overlapped
two-stream schedule, so `Δ = min(stream)` rather than `Δ = stream` across most
of the parameter space (the algebra is in §4.0). Any reading that treats
`Δ` as "the cost of that axis" is wrong; the decision rules deliberately compare
`ΔM2` against `ΔS2` rather than against an absolute prediction.

**Two M2-specific caveats worth checking before over-reading `ΔM2`.**
(a) The census shows `mma 1 -> 2` in post-optimisation AIR on M4, but the M5
compiles independently and a sufficiently aggressive scheduler could still sink
or interleave the shadow MMA differently; the count is evidence, not a
guarantee. (b) It is worth confirming whether `tile_matmad_nax`
(`steel/gemm/nax.h`, around `:994-1031`, descriptor at `:503`) takes threadgroup
operands — if it does, the shadow MMA is not purely an issue-slot perturbation
and shares a resource with S2, which would weaken the axis separation that R2
and R3 depend on. Neither affects a `ΔM2 <= 0` reading under R6.

**Whether to keep the arms as a permanent instrument.** The probes are
default-off and provably inert at probe 0 (§3), so merging them costs the
frontier nothing and gives every future kernel change a ready-made way to ask
the same question. Against that: they are ~200 lines of research scaffolding on
a hot path and they consume editable-surface budget, which is at
`61,995 B` headroom. My recommendation is to merge them only if this experiment
returns a usable verdict; if it does not, delete them rather than leave a
half-trusted instrument in the tree.

**Standing follow-up: the S2 sham-barrier arm.** S2 is bit-exact only because
the neighbouring expert's tile is written into `Ws` *before* the real load
overwrites it, which forces one extra `threadgroup_barrier` into the k-loop.
`ΔS2` therefore carries one barrier that `ΔM2` does not, and this note resolves
it on paper (the `[ΔS2 - ΔB2, ΔS2 - ΔB2/2]` interval in §4.0) rather than in
code. A cleaner instrument would add a fourth arm that keeps S2's extra barrier
but drops its extra loads — a "sham" whose only job is to price that one
barrier directly, collapsing the interval to a point. It is **not** implemented
here on purpose: a sham that writes into the staging tile cannot be shown
bit-exact on a gen-16 host, where `is_nax_available()` is false and the edited
kernel never executes, so shipping it would risk an inexact arm that burns an
irreplaceable official receipt and publishes no `officialMetrics` at all. The
adequacy proof in §4.0 shows the interval can only flip a verdict when
`ΔB2 > 0.20·W = 8.65 ms`, which already trips R1 and makes H3 the headline —
i.e. exactly in the regime where the interval no longer matters. Revisit only
if a future run has M5 access for a correctness check before submission.

## 10. Reproduction

```bash
# offline census (both threadgroup shapes, all four arms)
for p in 0 1 2 3; do PROBE=$p research/nax_msl_compile_check.sh; done

# twin consistency + inertness rig
python3 research/nax_twin_check.py
research/nax_safety_rig.sh

# build health at the committed default (probe 0)
./benchmark.sh --local-iterate

# receipts: flip the one constant, submit, then restore
#   Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp
#   constexpr const char* kNaxGatherProbeDefault = "m2";   # or "s2" / "b2"
mlxfast submit --model "senpai" --note-file research/artifacts/tanjiro-pr170-note-m2.md
git checkout -- Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp

# verdict
curl -s -H "Authorization: Bearer $MLXFAST_API_TOKEN" \
  "https://api.mlx.fast/api/benchmarks/eigenlabs%2Fmlxfast-challenge/submissions" \
  -o /tmp/subs.json
python3 research/tanjiro-pr170-receipts.py /tmp/subs.json m2=<id> s2=<id> b2=<id>
```

Local build health at the committed default: `./benchmark.sh --local-iterate`
exit 0 in 354 s, `"passed": true`, score `0.798`, prefill `0.001126` s/tok,
decode `0.012878` s/tok (M4 numbers; the nax kernel does not run on this host,
so these check the build and the probe-0 inertness, not the mechanism).
