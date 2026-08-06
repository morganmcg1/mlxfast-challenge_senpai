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

**Confound verdict: all three arms CLEAN.**

- **M2** — `mma 1 -> 2`; barriers, device loads, threadgroup loads and
  threadgroup stores **all unchanged**. CSE and DCE both defeated, and the arm
  adds exactly zero memory traffic.
- **S2** — `dev_ld 6 -> 8`, `tg_st +1`, `barr +1`, `mma` unchanged. Clean, but
  carries one extra barrier *by construction*; §4 subtracts it.
- **B2** — `barr +2`, every other counter unchanged. The compiler did not merge
  or hoist the added barriers.

Every added call site sits inside the same loop nest as the original it
shadows, so the **static ratio equals the dynamic ratio**.

Pipeline reflection is identical across all four arms and both shapes:
`threadgroupMemoryLength = 9232 B`, `maxTotalThreadsPerThreadgroup = 1024`,
`threadExecutionWidth = 32`, giving `floor(32768 / 9232) = 3` threadgroups per
core. **Occupancy is unchanged by every arm.**

*Honest caveat.* `maxTotalThreadsPerThreadgroup` is saturated at 1024 and so
cannot report register pressure; M2 does add 5 allocas. This does not weaken a
*falsification* (a `ΔM2 ≈ 0` would be confound-free), but a *large* `ΔM2` admits
a register-pressure alternative that this instrument cannot exclude. Also,
these are M4 static counts; the M5 compiles the same MSL but its scheduler is
not identical.

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

Taking the weakest (smallest) floor in each row — `651.8 GB/s` for S2 — and
allowing ~12% for receipt noise and any optimism in the pinned peaks:

| gate | condition | meaning |
|------|-----------|---------|
| **R0a** | `ΔM2 < 13.0` or `ΔS2 < 9.5` | **instrument failure** — the arm did not reach the kernel (or a pinned peak is wrong). Verdict void; debug before spending more receipts. |
| **R0b** | `ΔM2 > 33.3` or `ΔS2 > 37.2` | **flag** — delta exceeds the arm's own peak-bound isolated cost (`28.96`, `32.34` @546.2) by >15%; the arm perturbed something beyond its axis (register pressure / occupancy). Report, do not silently accept. |

### 4.2 Decision rules

Registered before any receipt was spent and implemented in
`research/tanjiro-pr170-receipts.py`. Margin `μ = 0.10·W = 4.33 ms`; the rules
are evaluated in order and are exhaustive.

| rule | condition | verdict |
|------|-----------|---------|
| **R1** | `ΔB2 >= 0.25·W  (10.82)` | **H3 wins** — schedule latency is the dominant cost; next mechanism is barrier removal / deeper pipelining / occupancy |
| R1' | `0.10·W <= ΔB2 < 0.25·W` | H3 **material** — real, first-order, but not dominant; reported alongside the R2–R5 verdict |
| R1'' | `ΔB2 < 0.10·W` | H3 minor on the barrier axis |
| **R5** | `ΔM2 + ΔS2p_hi <= W - μ  (38.94)` | **H3 by elimination** — even summing the two axes *serially* falls short of the measured wall, so a third cost (dispatch, occupancy, latency) dominates. Overrides R2–R4. |
| **R2** | `ΔM2 - ΔS2p_hi >= μ` | **H1** — MMA-limited |
| **R3** | `ΔS2p_lo - ΔM2 >= μ` | **H2** — load+dequant-limited |
| **R4** | otherwise | **H0** — jointly balanced; the two axes are within `μ`, so a single-axis reduction is Amdahl-capped by the other |

**Deleted rule.** An earlier draft carried an R5 reading "both deltas high ⇒ the
streams do not overlap; fix overlap, not either axis". It was self-contradictory
and is withdrawn: two fully serial `28.99 ms` streams would give a `57.98 ms`
wall, but the measured wall is `43.26 ms`, so the streams demonstrably *do*
overlap by about half. Worse, the model algebra in §4.0 shows that doubling an
equal stream yields `Δ = min stream` **for every value of `f`**, so
"both deltas high" is exactly what H0 predicts and carries no information about
overlap at all. The replacement R5 above tests something different and
well-posed: whether the two measured axes can account for the wall *at all*.

### 4.3 Floor safety

`S_candidate <= S_baseline / 0.95 ≈ 200 ms` against `S_control = 97.9 ms`
leaves **~102 ms of injection headroom** versus a maximum predicted arm delta
of ~29 ms. No arm can trip the prefill floor, and no arm touches decode.

### 4.4 Arm ordering, and what it buys

Arms are dispatched **M2, then S2, then B2**. This is not arbitrary. M2 and S2
have a hard peak-derived floor (R0a), so a near-zero delta on either is
*proof the instrument did not reach the kernel*, and the campaign stops to
debug rather than spending the remaining arms. `ΔB2 ≈ 0`, by contrast, is a
legitimate scientific outcome (H3 dead) that is **confounded** with "the arm did
not apply" — running it last means the large M2/S2 deltas have already
demonstrated that the identical plumbing (same `expert_aligned` path, same
`_pb_<n>` naming mechanism) reaches the kernel, which disambiguates it.

*Caveat on direct verification.* The dispatch-site trace fires whenever a probe
is requested and prints `active`/`inactive` with the kname handed to the JIT,
but the M5 receipt does not surface stderr, and the kernel cannot run locally
(this host is `applegpu_g16s`, Apple GPU generation 16; `is_nax_available()`
requires >= 17). The ordering argument above is therefore the operative
verification, and it is stated as such rather than dressed up as a direct one.

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

<!-- RECEIPTS -->

## 6. Reading

<!-- READING -->

## 7. Decode control

<!-- DECODE -->

## 8. Next mechanism

<!-- NEXT -->

## 9. Follow-ups

<!-- FOLLOWUPS -->

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
