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


#### 4.0.3 The shadow MMA is on the unconditional path, verified in the IR

A static instruction census proves the shadow `mma` was *emitted*. It does not
prove it *executes*. The M2 sink is

```c++
if constexpr (kProbeM2) {
  if (run_skip_pct > 1000) {          // host-clamped to [1,100]
    y[0] = static_cast<T>(Dshadow.frag_at(0, 0)[0]);
  }
}
```

and that guarded store is the shadow accumulator's only consumer. A compiler is
free to sink the whole chain into the guard, in which case the arm would add a
never-taken branch and nothing else, and a null would be an instrument failure
rather than a result. The convergence argument in the source comment is a claim
about what the optimiser *should* do, not evidence about what it *did*.

So I checked the emitted IR before reading any receipt.
`EMIT_IR=1 research/nax_msl_compile_check.sh` was run at probes 0–3 and the
per-function control-flow graph of `..._2048x1024_bk64[_pbN]` inspected
(`/tmp/naxpb{0,1}/unit.ll`):

| what | probe 0 | probe 1 (M2) |
|---|---|---|
| `run_skip_pct > 1000` compare | absent | line 190, function prologue |
| store guarded by it | absent | line 660, block `448` |
| `matmul2d_op_run_cooperative` | line 445, block `304` | lines 468 (`323`) and 594 (`404`) |

Both MMA sites sit in **loop-exit blocks of the accumulate nest**, reached from
loop latches (`br i1 %339, label %323, label %327`) on the ordinary fall-through
path. The guard block `448` is reached only after *both* nests have completed,
and contains only the store. Neither MMA is dominated by the guard, so the
shadow chain runs on every pass. **D1 discharged: the shadow MMA executes.**

The same IR pass re-derives the perturbation table from a second, independent
representation and reproduces §4.0.2 exactly, which is worth more than either
count alone:

| axis | pb0 | pb1 M2 | pb2 S2 | pb3 B2 | ΔM2 | ΔS2 | ΔB2 |
|---|---|---|---|---|---|---|---|
| device loads | 6 | 6 | 8 | 6 | +0 | **+2** | +0 |
| threadgroup loads | 4 | 4 | 4 | 4 | +0 | +0 | +0 |
| threadgroup stores | 5 | 5 | 6 | 5 | +0 | **+1** | +0 |
| `air.wg.barrier` | 7 | 7 | 8 | 9 | +0 | **+1** | **+2** |
| `mma` | 1 | 2 | 1 | 1 | **+1** | +0 | +0 |
| integer ALU | 147 | 176 | 153 | 147 | **+29** | +6 | +0 |
| float ALU | 10 | 11 | 10 | 10 | +1 | +0 | +0 |

The `512x2048` projection gives an identical delta column on every axis
(`dev_load +0/+2/+0`, `barrier +0/+1/+2`, `mma +1/+0/+0`, `int_alu +29/+6/+0`),
so neither GEMM shape is a special case.

Three things follow. **M2 perturbs no memory or barrier axis at all** — its only
companion to the extra MMA is integer ALU. **B2 is exactly `barrier +2` and
nothing else**, `int_alu` included: at this representation it is a perfectly
clean single-axis arm, cleaner than the AIR census could show. **S2 moves four
axes**, which is why its reading is an interval rather than a point.

Two caveats, recorded rather than hidden. First, the integer-ALU deltas are
larger here than the AIR counts in §4.0.2 (`+29` vs `+15` for M2, `+6` vs `+4`
for S2). The two representations count at different lowering stages, so the
magnitudes are not comparable; the sign, the ordering, and the set of
*untouched* axes agree exactly, and that is what the argument rests on. Second,
probe 1's kernel body is 585 IR instructions against probe 0's 457, and the
accumulate region appears as two sequential nests rather than one. The table
shows this is *addressing* growth — the extra `..._get_element_pointer` calls
and index arithmetic a second cooperative destination tensor needs — not a
duplicated load nest, since every memory and barrier axis is unchanged. It is
the one-sided integer-ALU confound §4.0.2 already flagged, seen from the other
side.


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
| 2026-08-07T02:00:09.608Z | m2 | **DISPATCHED** as `d786ad5c` on the watcher's first attempt after the hourly reset, into a slot it had held under observation. Armed window ≈ 9 s; tree restored to probe 0 in the same command. |
| 2026-08-07T02:20:05.683Z | m2 | **RECEIPT** — terminal `rejected` (ranking only), all gates passed. 19 min 56 s in queue against `benchmark_wall_seconds = 53`. Waiter exit 0 after 486.8 s of polling. |
| 2026-08-07T02:23:14Z | s2 | watcher started for arm 2 (deadline 03:18Z). Slot observed busy at 02:23:23Z: `08ddee4 validating`, a submission from another student that entered after M2 cleared. |
| 2026-08-07T02:41:19Z | — | `08ddee4` cleared (`rejected`). Slot free. The watcher had been silent for 18 minutes; that silence was the design (it logs only on status *change*), not a hang. |
| 2026-08-07T02:41:26Z | s2 | **DISPATCHED** as `a3e38005-5510-4529-93c5-da236eff0950`, 7 s after the slot opened, on the watcher's first attempt. Armed window ≈ 7 s; tree restored to probe 0 in the same command. Watcher exit 0 after 1091.8 s. |
| 2026-08-07T03:03:05Z | s2 | **RECEIPT** — terminal `rejected` (ranking only), all gates passed, `max_abs_diff = 0`. 21 min 39 s in queue against `benchmark_wall_seconds = 53`. |
| 2026-08-07T03:03:12Z | b2 | **DISPATCHED** as `f2160f8f-7166-4c64-a92f-5efcc46f576a`, 7 s after S2's slot released — the same first-attempt-into-an-observed-slot tactic, now three for three. |
| 2026-08-07T03:23:54Z | b2 | **RECEIPT** — terminal `rejected` (ranking only), all gates passed, `max_abs_diff = 0`. 20 min 42 s in queue. Waiter exit 0 after 1056.1 s. |
| 2026-08-07T03:26Z | s3 | S3 built, validated and committed (`aa05cee`) while B2 was still in the queue, so the fourth arm was ready to dispatch the moment the slot freed. Dispatcher started against a clean tree. |


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

**A second parsing defect, found before it cost anything.** The dispatcher's
slot detector carried the same bug that had already fabricated one receipt in
the waiter: `mlxfast submissions` colours the status column, so the third field
is `"\x1b[36mvalidating\x1b[39m"` and never compared equal to any member of the
in-flight set. Verified against live state rather than argued — with M2
genuinely `validating`, the old predicate returned `free=True`. In the waiter
that meant a wrong answer; here it would have armed the tree, submitted into an
occupied slot, taken a `conflict`, and retried on the next 12 s poll, roughly
five attempts a minute against an hourly budget that is **account-wide and
shared with three other students**. The failure would have been mine and the
cost would have been theirs.

The predicate was inverted while being fixed. It no longer asks whether a status
is one of the in-flight tokens I thought of; it asks whether every row has
reached a status known to be terminal, and treats anything else — including a
token never seen before — as in flight. The two errors are not symmetric: a
wrong "busy" costs bounded waiting, a wrong "free" costs a shared rate-limit
attempt. Enumerating all 42 historical rows returns `rejected`/`failed`/
`promoted` and nothing else, so the terminal set covers the observed vocabulary
and the slot still frees normally. A `conflict` now also arms a 120 s cooldown.

### 5.2 Receipt M2 — `d786ad5c` (arm 1 of 3)

| field | value |
| --- | --- |
| submission | `d786ad5c-cdd5-4383-b246-d9a7f3775a69` |
| harness commit | `409ba5c83f52bc91ebf23c9b5b44934e9b8b5379` |
| dispatched / receipt | `2026-08-07T02:00:09.608Z` / `2026-08-07T02:20:05.683Z` (~20 min) |
| status | `rejected` — `rejectionReason: score did not improve current best` |
| `officialScore` | `2.56432760787264` (frontier `2.58882784082067`) |
| `passed_correctness` | **`True`**, `max_abs_diff = 0` |
| `passed_prefill_speedup_floor` | **`True`** (`prefill_speedup = 1.965943317395163`) |
| `passed_decode_speedup_floor` | **`True`** (`decode_speedup = 2.8018250473613273`) |
| `gpqa_ttft_passed` / `semantic_gpqa_passed` | `True` / `True` (8 of 9) |
| `prefill_seconds_per_token` | `0.000195197671875` ⇒ **`S = 99.941 ms`** |
| `baseline_prefill_seconds_per_token` | `0.00038374755859375` ⇒ `196.479 ms` |
| `decode_seconds_per_token` | `0.00495820865625` ⇒ `4.95821 ms/step` |
| `baseline_decode_seconds_per_token` | `0.013892033203125` ⇒ `13.89203 ms/step` |
| `benchmark_wall_seconds` / `timed_benchmark_seconds` | `53` / `46` |
| `peak_ram_gb` | `21` |

**`ΔM2 = 99.941 − 97.895 = +2.046 ms`.**

Three validity conditions had to hold before that number means anything, and
all three hold.

1. **Bit-exact.** `max_abs_diff = 0`. The shadow accumulator never reached `y`;
   the sink held on the real device, not just in the IR.
2. **The arm actually ran.** This is the condition most easily overlooked. A
   probe that silently failed to compile in, or a kernel that was never
   selected, reads as *zero* — and zero sits inside the `±1.35 ms` three-sigma
   null band (§4.6). `+2.046 ms` is `4.5σ` outside it. So the M5 really did
   execute a second bit-exact MMA stream, and the measurement is of that stream
   rather than of nothing. The `R0a`-style void reading is excluded on evidence.
3. **Session health.** The paired baseline came in at `196.479 ms` prefill
   against the frontier session's `195.93 ms` (`+0.28%`, well inside the 12.6%
   baseline dispersion of §4.6) and `13.89203 ms/step` decode against a feed
   median of `13.86539` (`+0.19%`). Nothing about this session was unusual.

### 5.3 Receipt S2 — `a3e38005` (arm 2 of 3)

| field | value |
| --- | --- |
| submission | `a3e38005-5510-4529-93c5-da236eff0950` |
| harness commit | `47e8f5ec8095d950c39e7bda399b17d2fd31b48d` |
| dispatched / receipt | `2026-08-07T02:41:26Z` / `2026-08-07T03:03:05Z` (~21.6 min) |
| status | `rejected` — `rejectionReason: score did not improve current best` |
| `officialScore` | `2.40727961939956` |
| `passed_correctness` | **`True`**, `max_abs_diff = 0` |
| `passed_prefill_speedup_floor` | **`True`** (`prefill_speedup = 1.6294238289570744`) |
| `passed_decode_speedup_floor` | **`True`** (`decode_speedup = 2.7417258764555257`) |
| `gpqa_ttft_passed` / `semantic_gpqa_passed` | `True` / `True` |
| `prefill_seconds_per_token` | `0.000222374185546875` ⇒ **`S = 113.856 ms`** |
| `baseline_prefill_seconds_per_token` | `0.000362341796875` ⇒ `185.52 ms` |
| `decode_seconds_per_token` | `0.0050384658203125` ⇒ `5.03847 ms/step` raw |
| `baseline_decode_seconds_per_token` | `0.0138140921171875` ⇒ `13.81409 ms/step` |
| `benchmark_wall_seconds` | `53` |
| `peak_ram_gb` | `21` |

**`ΔS2 = 113.856 − 97.895 = +15.961 ms` — 36.9% of `W`, and `35σ`.**

This is the largest single number the instrument produced, and it is the one
that turned a residual into an identification. M2 had established that at least
72.6% of the critical path was *not* MMA and *not* integer ALU, but a residual
names nothing on its own. S2 fills it directly.

### 5.4 Receipt B2 — `f2160f8f` (arm 3 of 3)

| field | value |
| --- | --- |
| submission | `f2160f8f-7166-4c64-a92f-5efcc46f576a` |
| harness commit | `702c1d8d690c2c082fca2e3603ff45a0a883ae87` |
| dispatched / receipt | `2026-08-07T03:03:12Z` / `2026-08-07T03:23:54Z` (~20.7 min) |
| status | `rejected` — `rejectionReason: score did not improve current best` |
| `officialScore` | `2.55817063147974` |
| `passed_correctness` | **`True`**, `max_abs_diff = 0` |
| `passed_prefill_speedup_floor` | **`True`** (`prefill_speedup = 1.9633684178542896`) |
| `passed_decode_speedup_floor` | **`True`** (`decode_speedup = 2.7940794090795658`) |
| `gpqa_ttft_passed` / `semantic_gpqa_passed` | `True` / `True` |
| `prefill_seconds_per_token` | `0.000192842529296875` ⇒ **`S = 98.735 ms`** |
| `baseline_prefill_seconds_per_token` | `0.000378620931640625` ⇒ `193.854 ms` |
| `decode_seconds_per_token` | `0.004946203125` ⇒ `4.94620 ms/step` raw |
| `baseline_decode_seconds_per_token` | `0.0138200843046875` ⇒ `13.82008 ms/step` |
| `benchmark_wall_seconds` | `53` |
| `peak_ram_gb` | `21` |

**`ΔB2 = 98.735 − 97.895 = +0.841 ms` — 1.9% of `W`, `2.6σ`.**

B2 is the cleanest arm in the tree: the IR census showed it moves `barrier` and
*nothing else*, on both live threadgroup shapes. So `c_bar = ΔB2 / 2 =
0.4203 ms` per barrier is a direct price rather than an interval, and that is
what makes it worth a receipt despite being the smallest effect.

<!-- RECEIPTS -->

## 6. Reading

### 6.1 What M2 settles on its own: H1 is out

The pre-registered boundary is `dM2 > μ = 4.326 ms` for "large" (§4.2).
`ΔM2 = +2.046 ms` is **47.3% of μ**, so this is unambiguously the *small* cell —
and it is small by a wide margin, not by a hair: it would have to nearly double
to reach the boundary, and the boundary is `9.6σ` away from zero while the
measurement sits `4.5σ` above zero and `5.1σ` below `μ`. There is no reading of
the noise model under which this lands in the large cell.

The inference is direct. The M2 arm issues a *complete second MMA stream* over
the same tiles, matched in shape and count to the real one (§2, `mma 1→2` in
both the AIR and LLVM-IR censuses, on both live GEMM shapes, with **no** memory
or barrier axis perturbed — §4.0.3). If MMA issue were the binding constraint,
that work could not be hidden: doubling the bottleneck resource costs
approximately the whole of it. Instead the kernel absorbed it at **less than
half price**, which is only possible if the MMA pipe has slack — i.e. if
something *else* is holding the kernel up.

> **H1 (MMA-issue-bound) is eliminated.**

This is the outcome that retrospectively justifies having spent the first
receipt on M2 against review advice to start elsewhere (§9). M2's confound is
one-sided: a *large* `ΔM2` would have been ambiguous between MMA pressure and an
occupancy step (§9, register pressure is unmeasured), but a *small* `ΔM2` kills
H1 regardless of which mechanism a large value would have indicated. The cheap
outcome was the decisive one, and it is the one that occurred.

### 6.2 What remains, and what S2 has to do

Eliminating H1 collapses the `2×2` of §4.2 to its top row:

| | `dS2p` small | `dS2p` large |
| --- | --- | --- |
| **`dM2` small ✅** | **R5 → H3 latency/sync** | **R3 → H2 load-bound** |
| ~~`dM2` large~~ | ~~R2 → H1 compute~~ | ~~R4 → H0 jointly saturated~~ |

H0 (jointly saturated) goes with H1: R4 requires *both* deltas large, and it
additionally predicts a sum near `2W ≈ 86 ms`, which `ΔM2` alone has already
made unreachable. So S2 is now a **binary** discriminator between H3 and H2,
which is the strongest position two remaining receipts could be in.

### 6.3 B2 is now conditionally droppable, on a knowable condition

This is a budget result worth stating precisely, because it may save the third
receipt. The pure-load cost is bracketed rather than known, because S2 also adds
one barrier (§4.0.3: `dev_load +2`, `tg_store +1`, `barrier +1`):

```
dS2p ∈ [dS2 − dB2, dS2 − dB2/2]
```

Barriers cannot cost negative time, so `dB2 ≥ 0` and therefore `dS2p ≤ dS2`
unconditionally. Hence:

- **If `dS2 ≤ μ`**, then `dS2p ≤ μ` whatever `dB2` turns out to be. R5 fires,
  **H3 is the answer, and B2 need not be dispatched at all** — the third receipt
  is returned unspent.
- **If `dS2 > μ`**, the excess could be genuine load cost (→ H2) or the barrier
  impurity (→ still H3). Only then is B2 required, and §4.0.3 shows B2 is the
  clean instrument for exactly that correction: `barrier +2` and *nothing else*,
  integer ALU included.

So the decision to spend receipt 3 is deferred to a threshold test on receipt 2,
rather than taken now on taste.

§6.4 then revises the *reason* for that decision, and §6.5 revises the decision
itself. I am leaving §6.3 standing as written because it was the plan of record
when M2 landed, and the honest way to show a plan changing is to show the plan.

### 6.4 One receipt also puts a ceiling on every axis it perturbed

`ΔM2` is worth more than the sign test it was designed for. One arm gives one
equation in the unknown per-op costs `c_r ≥ 0`:

```
Σ_r  add_r · c_r  =  ΔM2  =  2.046 ms
```

That is underdetermined — I cannot say how the 2.046 ms splits between the extra
MMA stream and the 15 extra integer ops. But every `c_r` is individually
bounded by it, so the **whole-body** cost of each resource is bounded too.
Maximising `Σ_r body_r · c_r` subject to that single equation is a one-variable
LP: the optimum dumps all of `ΔM2` onto whichever perturbed axis has the largest
`body/add` leverage. The result is a ceiling that holds however the cost actually
splits. Body counts are AIR statics at the dominant `2048x1024_bk64` shape
(§4.0.2), and since both body and delta are static counts in the same inner
body, the loop trip count cancels in every ratio.

| axis | body | M2 adds | leverage | ceiling | share of `W` |
| --- | --- | --- | --- | --- | --- |
| `int_alu` | 87 | +15 | 5.80 | ≤ 11.87 ms | **≤ 27.4%** |
| `mma` | 1 | +1 | 1.00 | ≤ 2.05 ms | **≤ 4.7%** |

The denominator is `W = 43.26 ms`, the roofline time for this GEMM. The kernel's
true wall time `G` is unknown, but `G ≥ W`, so dividing by `W` *overstates* every
share. These are conservative in the direction that matters: a small ceiling
really is small.

Two things fall out, and the second is the one I did not expect.

**H1 dies quantitatively, not just directionally.** MMA issue owns at most 4.7%
of the critical path. The NAX units are idle for at least 95% of this kernel.

**H1b is capped before it is ever tested.** Follow-up 3 in §9 raised scalar/dequant
ALU boundness as a hypothesis that would masquerade as H3, and reserved arm A2 to
catch it. It no longer needs catching at that price: integer ALU owns at most
27.4% of the path. And the two ceilings are not additive — they trade off against
the same 2.046 ms, so the *joint* ceiling is also 27.4%, attained by putting
everything on ALU and nothing on MMA. Therefore:

```
≥ 72.6% of the gather GEMM's critical path is neither MMA issue nor integer ALU.
```

A2 could at best explain a quarter of the runtime, so it cannot be the headline
under any outcome. **A2 is withdrawn from the receipt plan**, not merely held.
The patch and its notes stay on disk as documented, unspent work.

The residual has to be memory or latency/sync — exactly the H2/H3 split that S2
and B2 were built to resolve. The hypothesis space did not just shrink; it
shrank onto the arms I still have.

### 6.5 What B2 is now for — a different job than it was built for

Applying the same reading to S2 in advance: if `dS2 ≤ μ`, then from `dev_load`
leverage `6/2 = 3`, off-chip staging owns at most `3 × 4.326 = 12.98 ms`, i.e.
≤ 30% of `W`. Stacked against §6.4 that is at most 57.4% accounted, leaving
**≥ 42.6% that is none of MMA, integer ALU, or off-chip staging**. That is a
positive result for H3 by quantified residual rather than by hand-waving.

But "H3 by residual" and "H3 demonstrated" are different claims, and §9's close
criterion is that a clean null is merge-worthy while an ambiguous one is not.
So B2 earns its receipt in *both* branches, for two different reasons:

- **`dS2 > μ`** — the original job. Resolve `[dS2 − dB2, dS2 − dB2/2]` against
  `μ` to split H2 from H3.
- **`dS2 ≤ μ`** — a job I did not design it for. B2 is the only arm in the tree
  with `int_alu +0` (§4.0.3: `barrier +2` and literally nothing else). A pure-ALU
  story predicts `dB2 ≈ 0`; H3 predicts `dB2 > 0`. It converts the residual
  argument into a direct positive measurement of the synchronisation axis, and
  simultaneously closes out the ALU story that §6.4 only bounded.

So the honest revision of §6.3 is: **B2 is no longer conditionally droppable.**
The condition I wrote there is still correct arithmetic, and it still tells me
*which question* B2 answers — but there is now a worthwhile question in both
branches. The receipt I expected to hand back has found a better use than being
handed back.

One gap I am naming rather than hiding: S2 leaves `tg_load` at `+0`, so nothing
in this tree bounds threadgroup-load cost. It sits inside the residual. I am
counting it as on-chip latency and therefore part of H3, which is defensible but
is a classification choice, not a measurement.

### 6.6 Two amendments to my own pre-registered rules, made before `dS2` existed

§6.5 leans on the branch `dS2 ≤ μ`. Before relying on it I ran the decision
function on synthetic triples covering every branch, and two of the rules I
pre-registered turned out to be wrong. Amending a pre-registered rule is only
legitimate at one moment — before the data that the rule adjudicates exists —
and that is where this is. The S2 arm was still queued behind another student's
submission when both edits were made and committed; the receipt cannot have
influenced them. Both amendments make the script report **less**, not more.

**Amendment 1 — R0a demoted from a void gate to a diagnostic.** R0a voided the
whole arm when `dS2 < 9.5 ms`. Its arithmetic is fine: `dev_load +2` on a body
of `6` moves an extra 33% of the 17.67 GB weight stream = 5.89 GB, which even at
the fastest peak I could justify (651.8 GB/s) is ≥ 9.0 ms of bus occupancy. The
*inference* was wrong. Bus occupancy becomes wall time only if the bus is on the
critical path. Peak-rate stream cost for the whole GEMM is 29.0 ms against
`W = 43.26 ms` and a true `G ≥ W`, so a latency-bound kernel has idle bus for
the extra stream to hide inside. That is precisely H3 — one of my two surviving
hypotheses. As written, R0a would have taken the strongest available H3
signature and filed it as instrument failure. Note the direction of the error:
the gate was not too weak, it was too strong, and it was aimed at the answer.

The three failure modes R0a named are all excluded by evidence I already hold,
none of it timing:

| stated failure mode | already excluded by |
| --- | --- |
| dead-code elimination | AIR/IR census counts `dev_load 6→8` for pb2 at both shapes (§4.0.2, §4.0.3); an elided load is not in the AIR |
| wrong probe compiled in | same census — pb2's delta signature is unique across the four probes |
| kernel not selected | M2 moved the wall clock 4.5σ through identical selector plumbing (§5.2) |

So a low `dS2` is not evidence the arm failed; it is a measurement that the bus
had slack. R0a now prints `R0a ABSORPTION (not void)`, reports how much
occupancy was absorbed, and **does not return early** — the cell rules still run
and the reading is positive evidence for H3 over H2.

One consequence I have to disclose rather than quietly fix: the S2 submission
note was written and dispatched under the *old* R0a and still states the 9.5 ms
floor as a void condition. It is a stale sentence in a dispatched artefact, not
a live gate — the gate lives in `research/tanjiro-pr170-receipts.py`, which is
what actually reads the receipt.

**Amendment 2 — the R4 catch-all asserted a falsehood.** R4 was the final `else`
of the cell ladder, so it claimed joint saturation for *anything* the earlier
rules declined. Fed `dM2 = 2.046, dS2 = 14, dB2 = 12` it printed "R4 H0 JOINTLY
SATURATED: dM2=+2.046 … both exceed mu=4.33", which its own numbers contradict.
That is exactly the M2 value I already have, so the bug was live, not
hypothetical. R4 is now guarded by its actual precondition (`m_big and lo > MU`)
and the new terminal `else` prints `AMBIGUOUS CELL` with both gaps, and points
at the cause: a wide `dS2p` bracket means `dB2` is large relative to `dS2`, so
it is the barrier impurity in S2 — not the load — that blocks the reading, and
the register-sink S2 redesign in §9 is the fix.

The general lesson I am taking from both: a decision ladder whose last rung is
an unguarded `else` will always produce a verdict, including for the cases the
designer never enumerated. The catch-all should be the one that refuses.

### 6.7 Pre-registering the joint reading, before `dS2` and `dB2` exist

§6.4 read one arm as one equation. Three arms are three equations over the same
five unknown marginal per-op costs `c_r ≥ 0`:

```
  M2:  1·c_mma + 15·c_alu                                    = dM2
  S2:  4·c_alu + 2·c_dev + 1·c_tgs + 1·c_bar                 = dS2
  B2:  2·c_bar                                               = dB2
```

Maximising the whole-body cost `Σ_r body_r · c_r` over that system is again an
LP. With every coefficient and every `delta` nonnegative the feasible set is a
bounded polytope, so the optimum sits at a vertex and enumerating all
`C(5,3) = 10` bases is exact — no solver, no tolerance to tune. That is
`joint_ceiling()` in `research/tanjiro-pr170-receipts.py`. It reproduces §6.4's
27.4% exactly when fed M2 alone, which is the check that the two derivations
agree.

Because B2 pins `c_bar = dB2/2` outright and M2 caps `c_alu ≤ dM2/15`, the
three-arm optimum has a closed form (when `dM2/15` is the binding ratio, which
it is for any `dS2 ≳ 0.8 ms`):

```
ceiling  =  dM2  +  5·dS2  +  dB2  +  (52/15)·dM2
```

The `5·dS2` term is `tg_store` leverage: S2 adds one threadgroup store against a
body of five, so a single millisecond of `dS2` can be charged five milliseconds
of whole-body cost. Three consequences I want on the record before the numbers
land.

**The bound is informative on a knowable condition.** A residual statement needs
`ceiling < W = 43.26 ms`. With `dM2 = 2.046` that is `5·dS2 + dB2 < 34.1 ms`,
i.e. roughly **`dS2 < 6.8 ms`**. Above that, `joint_ceiling()` prints
`NO RESIDUAL BOUND` rather than a negative residual — the same class of defect
as §6.6's R4, caught the same way and guarded before use.

**That condition is not a limitation, it is the right shape.** If `dS2` lands in
the 35–45 ms range the brief predicts for H2, the residual argument is not
needed: the arm has named the constraint directly. The residual argument is
required exactly when every arm comes back null, and it is informative exactly
then. The two regimes do not overlap and neither is left uncovered.

**Precision.** Propagating the instrument's `σ_Δ = 0.45 ms` (§4.6) through the
coefficients `(1 + 52/15, 5, 1) = (4.47, 5, 1)` gives `σ(ceiling) ≈ 3.0 ms`,
about 7% of `W`. So a residual claim is worth stating to the nearest ~10% of
`W` and no finer, and — worth knowing before I read anything — the bound is
**five times more sensitive to S2's measurement than to M2's**. If any arm
deserved a replication receipt it would be S2, not M2.

Two caveats that belong to the method, not to the data.

*Marginal is not share.* Every `c_r` is measured by **adding** work, so
`body_r · c_r` is the local sensitivity of wall time to resource `r` — how much
a proportional reduction of `r` could save — not `r`'s share of some serial
execution. Local sensitivity is the quantity an optimisation programme actually
wants, so this is the useful reading, but it is not the intuitive one and I do
not want it read as "resource `r` occupies X% of the runtime". The model also
assumes each `c_r` is constant across the perturbation range; a port that is
already saturated can charge more for added work than it would refund for
removed work.

*A negative delta falsifies the model, it does not just look odd.* With
nonnegative op counts and `c_r ≥ 0`, no cost vector can produce a negative
delta. If any arm returns one, occupancy or scheduling changed rather than work
being added, and every ceiling derived from that arm is void. `joint_ceiling()`
refuses to compute in that case rather than returning a number.

### 6.8 The reading, on three receipts

All three arms returned bit-exact (`max_abs_diff = 0`), passed both speedup
floors, passed GPQA TTFT and the semantic judge, and were `rejected` on ranking
only — which is the designed outcome, since every arm deliberately adds work.

| arm | axis perturbed | receipt | `S` (ms) | `Δ` (ms) | `Δ/W` | in σ |
| --- | --- | --- | --- | --- | --- | --- |
| control `97a5090` | — | — | `97.895` | — | — | — |
| **M2** | `mma +1`, `int_alu +15` | `d786ad5c` | `99.941` | `+2.046` | `4.7%` | `4.5σ` |
| **S2** | `dev_load +2`, `tg_store +1`, `barrier +1`, `int_alu +4` | `a3e38005` | `113.856` | **`+15.961`** | `36.9%` | `35σ` |
| **B2** | `barrier +2` | `f2160f8f` | `98.735` | `+0.841` | `1.9%` | `1.9σ` |

Against `μ = 4.326 ms` (`9.6σ`), the pre-registered rules fire cleanly:

- **R1″ → H3 MINOR.** `ΔB2 = +0.841 ms` for a **`+29%`** increase in barrier
  count. Synchronisation is not the constraint.
- **R3 → H2 WINS.** `dS2p ∈ [+15.120, +15.541] ms` exceeds `ΔM2 = +2.046 ms` by
  more than `μ`, in the *small-`dM2` / large-`dS2p`* cell.
- **SUM CHECK consistent.** `ΔM2 + dS2p_hi = 17.59 ms ≤ W + μ = 47.59 ms`, so
  no arm is double-counting the same stall.

> **The prefill routed gather GEMM `fp_gather_qmm_rhs_expert_nax` is
> load/staging-limited. H1 (MMA) and H0 (jointly saturated) are eliminated; H3
> (synchronisation) is real but minor; H2 is positively identified.**

This is a *positive identification*, not a residual argument, and that
distinction is what makes it worth the receipts. §6.4's residual bound from M2
alone said only "≥ 72.6% of the critical path is none of the axes I perturbed" —
true, but it names nothing. S2 names it directly.

**B2 prices the barrier axis outright.** B2 is the one arm whose IR moves a
single axis and nothing else (`barrier 7→9`, everything else byte-identical), so
it yields a *price* rather than a ceiling:

```
c_bar = ΔB2 / 2 = 0.4203 ms per barrier
```

That price is what converts S2 from a bundle into a measurement. S2's own extra
barrier costs `0.420 ms`, M2 caps `c_alu ≤ ΔM2/15 = 0.1364 ms/op` so S2's `+4`
integer ops cost at most `0.546 ms`, and subtracting both leaves

> **≥ 14.995 ms — 34.7% of the entire gather GEMM — attributable to two extra
> device loads and one extra threadgroup store.**

**On the staging axis the marginal price is not below the body average but
above it, which is what turns the linear model from an assumption into a
measurement.** The body carries 11 staging instructions (`dev_load 6` +
`tg_store 5`); S2 adds 3, a `+27.3%` increase, and the wall moves `+36.9%`.
Marginal cost per staging instruction is `4.998 ms` against `3.933 ms` if
staging owned the whole body — a ratio of **`1.27`**. If marginal equalled
average, staging would account for `54.98 ms`, i.e. **`127%` of `W`**.
The overshoot is itself informative: it says
staging does not merely dominate the kernel, it is being charged at a *higher*
marginal rate than the body average, which is the signature of a resource at or
past saturation.

**Where the honest limits are.** Three, stated plainly:

1. *Marginal is not share.* Each `c_r` is measured by **adding** work, so
   `body_r · c_r` is local sensitivity — what a proportional reduction could
   save — not a share of serial execution. A pipelined unit can slot added,
   dataflow-independent work into idle issue slots while body ops sit on serial
   dependence chains, in which case the marginal price reads *spare* capacity.
   This is exactly why the `1.27` ratio matters: on the staging axis the
   marginal price is not cheap-because-idle, it is dearer than average, so the
   linear model is empirically validated *on the axis that carries the result*.
   The `≥ 72.6%` residual from M2 survives only in the weaker form "the kernel
   is not MMA-**issue-throughput**-bound".
2. *The joint LP is vacuous here, as pre-registered.* Solving all three arms
   against five axes gives a ceiling of `89.79 ms = 207.5%` of `W`, so it
   bounds nothing. §6.7 registered that outcome in advance, and it is the
   correct one: an LP that maximises a ceiling cannot tighten when one arm has
   already named the constraint directly.
3. *`tg_load` is unpriced.* No arm in this tree perturbs threadgroup **reads**
   (body count 4). Staging is identified as the constraint, but the split
   between *filling* threadgroup memory and *reading* it back — including
   possible bank conflicts on the read side — is not resolved here. §8 says what
   would resolve it.

**What S3 adds.** S2 conflates two things that call for opposite optimisations:
the *instructions* that stage a tile, and the *bytes* those instructions move.
S2's shadow loader reads the neighbour expert's slab, which is `5.89 GB` of
genuinely new DRAM traffic, so its `+15.961 ms` could be a pipeline cost, a
bandwidth cost, or any mixture. The fourth and final receipt separates them.

<!-- READING -->

## 7. Decode control

The decode axis is a **negative control**, not a target. Every arm perturbs only
the prefill-selected `_nax` gather GEMM; at decode the routed path takes a
different kernel entirely (`M==1` fails the `B/E>=4` prefill gate, §2), so a
correctly-scoped arm must leave decode alone. A decode movement tracking the
prefill movement would mean the probe had escaped its intended scope and would
invalidate the prefill reading.

### 7.1 The control must be applied to `T`, not to the raw decode column

The raw `decode_seconds_per_token` cannot be used as the negative control, and
this is a property of the harness rather than a convenience. The harness's
decode pass is a **512-token seed prefill followed by 128 one-token steps**, and
it divides the *whole pass* by 128. Every arm's own prefill delta therefore
lands in the raw decode column at `dS/128`, by construction, under exactly zero
leakage.

S2 is the case that makes this unmissable: its raw decode reads `+2.65%`, which
would breach the `2%` tolerance and void the strongest result in the tree — and
`+2.54%` of that `+2.65%` is arithmetically just its own `+15.961 ms` of honest
prefill spread over 128 steps. The residual actual decode movement is `+0.13%`.
Testing the raw column would fail any arm *for succeeding at its job*.

`T_ms` subtracts the seed term:

```
T = (128 · decode_s_per_tok − 512 · prefill_s_per_tok) / 128
```

This is a wiring repair, not a post-hoc rescue: `T_ms` has been the R7 estimator
since `9ddd94f` (2026-08-06T23:15:47Z), **three hours before the first receipt
existed**. The raw column is still printed as a diagnostic, and the table below
shows both so the correction can be audited rather than trusted.

### 7.2 Results

| arm | seed-corrected `T` | vs control `4.14357` | raw decode | of which is own prefill | paired baseline decode | vs feed median `13.86539` | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M2 | `4.17742` | `+0.82%` | `4.95821` (`+1.02%`) | `+0.33%` | `13.89203` | `+0.19%` | **OK** |
| S2 | `4.14897` | `+0.13%` | `5.03847` (`+2.65%`) | `+2.54%` | `13.81409` | `−0.37%` | **OK** |
| B2 | `4.17483` | `+0.75%` | `4.94620` (`+0.77%`) | `+0.13%` | `13.82008` | `−0.33%` | **OK** |

Tolerance `2%`; session-health band on the paired baseline `1%`.

**All three arms pass, and they pass in the informative direction.** The
strongest test is not that each `|ΔT|` is small — it is that `ΔT` is
**uncorrelated with `ΔS`**. If a probe had escaped into the decode path, decode
movement would track prefill movement. Instead S2, which moved prefill nearly
**eight times** further than M2 (`+15.961` vs `+2.046 ms`), moved corrected
decode the *least* of the three (`+0.13%` vs `+0.82%`). That inversion is
exactly what §2's static argument predicts: at decode `M==1` fails the
`B/E>=4` prefill gate, so the probed kernel is **not dispatchable at all**, and
the small residual scatter is session noise rather than leakage.

Session health is clean on every arm: all three paired baselines sit within
`0.4%` of the n=16 feed median, well inside the `1%` band, so no receipt in this
tree is reading a degraded session.

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
(a) The census shows `mma 1 -> 2` in post-optimisation AIR on M4, and §4.0.3
goes further by showing in the LLVM IR that neither MMA is dominated by the
runtime-false guard, so on *this* toolchain the shadow chain provably executes.
What that does not cover is the M5, which compiles independently: a different
scheduler could still sink or interleave the shadow MMA. The residue is now
narrow — it is a claim about one specific compiler on unavailable hardware
rather than about the source — but it is evidence, not a guarantee.
(b) It is worth confirming whether `tile_matmad_nax`
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

**Known limitation: register pressure per arm is unmeasured.** The pipeline
reports `staticThreadgroupMemoryLength = 9232 B`,
`maxTotalThreadsPerThreadgroup = 1024` and `threadExecutionWidth = 32`,
byte-identical across all four probes and both shapes, which is what lets §7 of
each note claim occupancy is unperturbed *on the threadgroup-memory axis*. It
does not settle the register axis. The census tool prints a `regs_est` column,
but that value is a hardcoded `32` rather than a real estimate — I checked, and
I am flagging it here because a reader could easily mistake it for a
measurement. With a ~208 KB/core register file, an arm that pushed register
demand over an occupancy step would change resident threadgroups per core and
confound its own reading. M2 is the plausible offender: it adds a second
accumulator tile. Nothing in the evidence rules this out, so a large `ΔM2`
must be read as "MMA-axis pressure *or* an occupancy step", not as pure issue
cost. Resolving it needs either a real register count from an M5 toolchain or
the occupancy probe below.

**The cleanest unbuilt instrument is an explicit occupancy probe.** Rather than
inferring occupancy effects, pad `Ws_storage` by enough bytes to drop the
kernel from 3 resident threadgroups per core to 2, changing nothing else. That
is a single-axis occupancy arm, it is trivially bit-exact (the padding is never
read), and it prices the occupancy step directly — which both calibrates the
register caveat above and tests H3 from a different direction than B2 does. If
I had a fifth receipt this is what I would spend it on.

**Unprobed hypothesis H1b: scalar/dequant ALU boundness.** The three arms
partition the resource space into MMA, staging and barriers, and treat "none of
the above" as H3 (latency). That is too coarse. On a generation where the NAX
unit co-issues with the FP and integer pipes, a kernel bottlenecked on the
NVFP4 dequant chain — `fp4nv_decode8` alone is 13 integer ops, and the routed
gather does that per 8 values — would show `ΔM2 ≈ ΔS2 ≈ ΔB2 ≈ 0` and be filed
as H3, because no arm perturbs the scalar integer pipe as its *primary* axis.
The A2 arm built for this PR (`research/artifacts/tanjiro-pr170-a2-probe4.patch`,
`int_alu 606 → 635`, every other axis unchanged) is exactly that instrument and
is held out of tree pending a firing condition. Registered before any receipt:
A2 fires if the reading is a flat null, if S2 reads positive, or if `ΔM2` is
large. A flat null across M2/S2/B2 should be reported as "H3 *or* H1b", not as
H3, unless A2 has been run.

**Two redesigns for a second-generation S2.** (i) The current S2 stages through
threadgroup memory and therefore drags a barrier along, which is the whole
reason its reading is an interval. A register-sink variant — load
device → registers and OR-accumulate into one dead vector register — perturbs
the load axis with no extra barrier and no extra threadgroup store, collapsing
the interval to a point and retiring the B2 correction entirely. (ii) It would
also drop S2's `int_alu +6` confound. This is strictly better than what shipped
and is the first thing to build if this line continues.

**Get a generation-17 device and most of this becomes local.** Every hard
constraint in this experiment — four receipts, no bit-exactness check for
staging arms, no register numbers, M5-only compilation — traces to
`is_nax_available()` being false on the gen-16 host, so the kernel under study
never executes here. A single gen-17 machine converts the entire programme from
receipt-metered to iterative. Short of that, adding an offline `metal` compile
targeting apple-17 to the preflight rig would at least catch JIT errors that
currently can only surface as a wasted official run.

**Why M2 went first, against review advice.** The frontier review argued for
S2 → M2 and for demoting B2, on the grounds that S2 has the strongest prior
(feeding one core's NAX needs ~93 GB/s/core). I kept M2 → S2 → B2 for two
reasons and record them so the ordering can be judged rather than assumed.
First, the ALU census makes the M2 confound **one-sided**: the arm adds MMA
*and* integer ALU, so a large `ΔM2` is ambiguous but a small `ΔM2` kills H1
outright regardless of the confound. Ordering a test so that its cheap outcome
is its decisive one is worth more than ordering by prior probability. Second,
M2's dispatch path was already structurally witnessed end to end when the slot
opened, and re-verifying a different arm would have cost a queue cycle against
a hard four-receipt budget. If the reading comes back ambiguous, the review's
ordering was the better one and I will say so.

**The strategic ceiling here is modest, and worth stating plainly.** Perfectly
fixing whichever axis this experiment names is worth at most `43.26 → ~29 ms`
of the routed gather, about 14.6% of prefill and — at 25% score weight — a
low-single-digit score move. This experiment's value is that it tells the next
person *which* axis to attack, not that it wins on its own. A related honest
limit: a `(large, large)` reading on both stream arms cannot distinguish a
perfectly overlapped co-bound kernel from two serially exposed phases, since
the observed `43.26 ms` sits between the `~29 ms` perfect-overlap and `~58 ms`
fully-serial predictions. A latency probe, not another throughput arm, is the
discriminator for that fork.

## 10. Reproduction

```bash
# offline census (both threadgroup shapes, all four arms)
for p in 0 1 2 3; do PROBE=$p research/nax_msl_compile_check.sh; done

# §4.0.3: LLVM IR control-flow check that the shadow MMA is not sunk into the
# runtime-false guard, plus the independent op-class delta table
for p in 0 1 2 3; do
  PROBE=$p BK=64 EMIT_IR=1 OUT_DIR=/tmp/naxpb$p research/nax_msl_compile_check.sh
done
python3 research/tanjiro_ir_cfg_check.py /tmp/naxpb0 /tmp/naxpb1 /tmp/naxpb2 /tmp/naxpb3

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
