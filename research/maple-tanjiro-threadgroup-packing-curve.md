# Decode QKV-GEMV threadgroup-packing curve

PR #308 · branch `maple-tanjiro/threadgroup-packing-curve` ·
base `63ab67c888e1892086b7b5b623de4dd0ebe68c90`

Host: Apple **M4 Pro**, 14 CPU, 48 GiB (low-memory startup profile),
macOS 26.5.2, Apple GPU generation **16** (no `_nax` kernels).
Every number below is an **M4 Pro** number. Nothing here is a ranked-M5 claim.

---

## 0. Corrections to the assignment before any measurement

These matter because they change what the experiment *is*.

### 0.1 The knob does not exist in `Sources/`. Stage 0/1 is not a zero-source-edit sweep.

The assignment says to sweep `DARKBLOOM_DECODE_NVFP4_QKV_R1_SIMDGROUPS`, and
describes it as an existing control. It is not:

```
$ grep -rn "SIMDGROUPS" Sources/
(no output)
```

The identifier appears at the assignment base only inside an **unapplied**
research patch, `research/nezuko_pr48_deconfound.patch` (369 lines, 16,815 B),
which PR #298 used and never landed. So the −35.4 µs/step PR #298 result was
measured through a patched worker, and reproducing or extending it *requires*
applying a patch and rebuilding. Any plan that treats this sweep as
"flip an env var against the shipped binary" is wrong.

I did not reuse nezuko's patch. It bundles the packing knob together with the
folded-norm prologue (`DARKBLOOM_DECODE_NVFP4_NORM_QKV_FUSE`), which is exactly
the confound PR #298 spent eight runs per arm untangling, and the fold is also
the thing that would make threadgroup memory scale with `S`. Instead I wrote a
78-line single-axis knob, `research/tanjiro_packing_geometry.patch`, that
changes nothing but the packing geometry.

### 0.2 `S=1` is a real arm here; under nezuko's patch it was a silent no-op.

nezuko's validator accepts only `[2, 4, 8, 16]`, so `S=1` silently falls back to
`2`. The assignment lists `1/2/4/8/16` as the sweep. My knob accepts
`[1, 2, 4, 8, 16, 32]`, and Stage 0 below proves that `S=1` and `S=32` both
reach the kernel with the encoded geometry they claim. Had I inherited
nezuko's patch, the `S=1` arm would have produced a perfect statistical tie
with the default for the uninteresting reason that it *was* the default.

### 0.3 Minor: the fold flag's real name

The assignment writes `DARKBLOOM_DECODE_NVFP4_QKV_R1_NORM_QKV_FUSE`. The actual
variable in nezuko's patch is `DARKBLOOM_DECODE_NVFP4_NORM_QKV_FUSE`. My driver
pins the correct name to `0`.

### 0.4 The assignment's fault injection is a semantic no-op. I had to redesign it.

The assignment asks for "an off-by-one row mapping". I implemented the literal
version first —

```
uint out_row = tile * num_simdgroups + ((simd_gid + 1) % num_simdgroups);
```

— and the public 64-step golden gate **passed** it at both `S=2` and `S=16`
(training `6a499c27-b0bf-43b1-b6a9-70e750b707df`). That is not a broken
tripwire. It is a correct verdict on a patch that does nothing.

In this kernel `out_row` is the *only* row identity. It gates the weight-code
pointer, the scale-nibble read, the scale-base read, the weight-scale read, and
the output store `projected[out_row]` — all five together. So any **bijection**
over `out_row` still computes every row exactly once from that row's own weights
and writes it to that row's own output slot. Rotating `simd_gid` inside a
threadgroup is a bijection. It is literally identity on the output.

The corrected fault (§3) keeps every *read* on the true `out_row` and rotates
only a new `store_row` used at `projected[store_row]`. That desynchronises read
row from write row, which is the row-mapping mistake a repack can actually make,
and it stays in bounds so the gate has to catch a wrong *answer* rather than an
out-of-bounds write. I deliberately deviated from the assignment's bare `+1`
(which would also have been an out-of-bounds store, a weaker test) for that
reason.

The same observation is the positive half of §1.2: it is *why* the sweep is
bit-exact.

### 0.5 The trusted CLI holds no model code, so the per-arm golden gate is valid

I checked whether `correctness --golden` was actually exercising my rebuilt
kernel, because `.build/release/mlxfast-swift` was stale relative to the worker.
It does not matter: the CLI contains no MLX or Laguna code at all
(`laguna_decode_nvfp4_qkv_r1`, `lagunaDecodeNVFP4`, `mlx::core` are all absent
from its symbol and string tables). It delegates every model execution to
`MLXFAST_RUNTIME_WORKER_EXECUTABLE`. The per-arm gate therefore ran the rebuilt
worker in every arm.

One trap worth recording: Swift stores small string literals (`_sg`, `_fault`,
`_pw1`, `_se1`) as inline register immediates, so they are **invisible to
`strings`**. Only large literals such as the embedded Metal source show up. To
verify which variant a binary contains, grep the Metal source text
(e.g. `num_simdgroups = `), not the Swift-side suffix.

---

## 1. Stage 0 — reachability, guard chain, and encoded geometry

### 1.1 Guard chain down to a default value

All line numbers are at the assignment base,
`Sources/MLXFastModel/LagunaRuntimeModel.swift`.

1. **Decode call site, `:5735-5790`.** The step first tries `fusedQKV`, which
   requires `lagunaFusedNormAffineQKVEnabled` (`:5295`) *and*
   `fusedAffine.mode == .affine, bits == 8, groupSize == 32`. The runtime
   quantizes QKV as `.nvfp4 / 16 / 4` at `:2914` because
   `lagunaNativeAffineNVFP4From` (`:2861-2867`) **defaults to `0`**. So
   `fusedQKV` is unconditionally `nil` on the default configuration and control
   falls through to `lagunaDecodeNVFP4QKVR1(normalized:bank:heads:)` at `:5766`.

2. **`lagunaDecodeNVFP4QKVR1`, `:4815`.** Requires
   `lagunaDecodeNVFP4QKVR1Enabled` (`:4620`), which is
   `environment[...] != "0"` — i.e. **default `true`**. Then shape guards; note
   `normalized.dims == (1, 1, hidden)` at `:4823`, which is why prefill is
   structurally excluded from this kernel (rule-17 note, §4).

3. **Lane-major branch, `:4834`.** Requires `bank.laneMajorScales` non-nil and
   `lane.pairwise == lagunaAttnScalePairwiseQKVEnabled`
   (`Sources/MLXFastModel/LagunaRuntimeWeights.swift:686`). The bank is
   populated at `:5571` under
   `lagunaAttnScaleNarrowQKVEnabled && mode == .nvfp4 && bits == 4 && groupSize == 16`,
   all of which hold by default. **This is the branch that runs.**

4. Fallbacks that must *not* fire: narrow branch `:4852`, plain R1 `:4867`,
   generic `quantizedMM` last. The Stage 0 probe emits a `PACKPROBE FALLBACK`
   line from each of these, so a silent fallback cannot be mistaken for a
   timing null.

### 1.2 Why the repack is bit-exact by construction

Inside `lagunaDecodeNVFP4QKVLaneMajorSource` the only statement that reads
`num_simdgroups` is

```metal
uint out_row = tile * num_simdgroups + simd_gid;
```

Every statement below it is simdgroup-local (`simd_lid`-indexed loads, a
register K-loop, one `simd_sum`, one `projected[out_row]` store). With `grid.x =
rows * 32` and `threadGroup.x = S * 32`, the set of `(out_row)` values covered
is exactly `[0, rows)` for any `S` that divides `rows`, each visited by exactly
one simdgroup, with one row per simdgroup in every arm. Total simdgroups,
arithmetic, and bytes read are therefore invariant; only the packing changes.

The shipped dispatch is `grid: ((rows/2)*64, 1, 1)`, `threadGroup: (64, 1, 1)`.
My parameterized dispatch at `S=2` is `grid: (rows*32, 1, 1)`,
`threadGroup: (2*32, 1, 1)` — **bit-identical**, so the `S=2` arm is the
unpatched stock path and is a legitimate reference.

### 1.3 Divisibility — and why the curve can be pushed to S=32

`LagunaConfig.swift`: `hiddenSize=2048`, `numKeyValueHeads=8`, `headDim=128`,
`fullAttentionHeads=48`, `slidingAttentionHeads=64`. Fused QKV row counts:

| layer type | heads | rows | factorization |
|---|---|---|---|
| full attention | 48 | `(48+16)*128 = 8192` | `2^13` |
| sliding window | 64 | `(64+16)*128 = 10240` | `2^11 · 5` |

`8192` caps the usable powers of two, so the sweep is
`S ∈ {1, 2, 4, 8, 16, 32}`. `S=32` is `1024` threads/threadgroup, the Metal
maximum. **Because the fold is pinned off, the prologue is empty and no
threadgroup memory scales with `S`** — the >32 KB pipeline-build failure the
assignment warns about cannot occur in this sweep, which is what lets me
extend the curve two points past PR #298's `S=16` and answer "does it keep
improving?".

### 1.4 Encoded geometry actually observed

`research/tanjiro_packing_probe.patch` (unapplied at the PR tip) adds a
`PACKPROBE` line per distinct `(heads, S)` tuple, printed from the dispatch site
*after* the guard chain, plus `PACKPROBE FALLBACK` from all three fallbacks.
Raw logs: `research/packing-curve-logs/stage0/`.

Driver `research/tanjiro_packing_stage0.sh`, training
`418d95ae-ee1b-45cd-ad50-3e75ee1ea2c0` (exit 0, 229.7 s), raw logs in
`research/packing-curve-logs/stage0/`. The instrumentation is landed
**unapplied** as `research/tanjiro_packing_probe.patch` (standing rule 11), and
prints one deduplicated line per distinct dispatch shape:

```
PACKPROBE lane-major heads=48 rows=8192 sg_per_tg=16 threadgroups=512 \
  rows_per_sg=1 threads_per_tg=512 grid_threads=262144 total_sg=8192
```

All six arms reached the lane-major kernel. **There is no `PACKPROBE FALLBACK`
line anywhere in the six logs**, i.e. the narrow (`:4852`), plain-R1 (`:4867`),
and generic `quantizedMM` fallbacks never fired, so every arm is the same kernel
family with a different packing.

| `S` | full attn `heads=48`, `rows=8192` | sliding `heads=64`, `rows=10240` | threads/TG | grid_threads | total_sg | rows/sg |
|---|---|---|---|---|---|---|
| 1 | 8192 TGs | 10240 TGs | 32 | 262144 / 327680 | 8192 / 10240 | 1 |
| **2** (default) | **4096 TGs** | **5120 TGs** | **64** | 262144 / 327680 | 8192 / 10240 | 1 |
| 4 | 2048 TGs | 2560 TGs | 128 | 262144 / 327680 | 8192 / 10240 | 1 |
| 8 | 1024 TGs | 1280 TGs | 256 | 262144 / 327680 | 8192 / 10240 | 1 |
| 16 | 512 TGs | 640 TGs | 512 | 262144 / 327680 | 8192 / 10240 | 1 |
| 32 | 256 TGs | 320 TGs | 1024 | 262144 / 327680 | 8192 / 10240 | 1 |

The invariants the experiment depends on all hold across arms:
`grid_threads` constant, `total_sg` constant, `rows_per_sg = 1` everywhere.
Only `threadgroups` and `threads_per_tg` move, and they move as exact
reciprocals. `S=32` reaches 1024 threads/TG, the Metal maximum, and builds
because with `NORM_QKV_FUSE=0` no threadgroup memory scales with `S`.

Every arm also reported `teacher-forced greedy tokens: 0 divergences (all
match)` on the probe's own short check, and the full public 64-step golden gate
passed at all six arms (training `177c27d5-e2cc-45e7-ac02-63f20c34fe42`, archived
in `research/packing-curve-logs/stage0-gate/`):

| `S` | `passed` | `checked_steps` | `first_failing_step` | `golden_hash` |
|---|---|---|---|---|
| 1 | `True` | 64 | `None` | `b9509697c08a2cf3…` |
| 2 | `True` | 64 | `None` | `b9509697c08a2cf3…` |
| 4 | `True` | 64 | `None` | `b9509697c08a2cf3…` |
| 8 | `True` | 64 | `None` | `b9509697c08a2cf3…` |
| 16 | `True` | 64 | `None` | `b9509697c08a2cf3…` |
| 32 | `True` | 64 | `None` | `b9509697c08a2cf3…` |

Stage 0 therefore answers the assignment's gating question: **the knob does
change encoded geometry**, so Stage 1 is a real timing experiment rather than a
null one.

The tiny-`n` medians from the 6-step probe runs already hinted at the shape that
Stage 1 measures properly — `S=1` clearly slow, everything else close with
`S=16` lowest:

| `S` | 1 | 2 | 4 | 8 | 16 | 32 |
|---|---|---|---|---|---|---|
| 6-step median (ms/step) | 8.411 | 8.224 | 8.224 | 8.190 | **8.173** | 8.188 |

`n=6` with no ABBA structure, so this is a sanity check on direction, not
evidence.

---

## 2. Stage 1 — the packing curve

<!-- STAGE1 -->

---

## 3. Fault injection — is the tripwire load-bearing?

The assignment makes this mandatory: if an injected row-mapping defect cannot
make the tripwire fail, Stage 1 is `INVALID`. It took two attempts, and the
first attempt is the more instructive one.

### 3.1 Attempt 1 — the assignment's literal fault is identity (INVALID by design)

Patch: `out_row = tile * num_simdgroups + ((simd_gid + 1) % num_simdgroups)`.
Training `6a499c27-b0bf-43b1-b6a9-70e750b707df`.

| `S` | `passed` | `checked_steps` | verdict |
|---|---|---|---|
| 2 | `True` | 64 | gate passed an injected "fault" |
| 16 | `True` | 64 | gate passed an injected "fault" |

My gate script correctly refused this (`exit 2`). But the conclusion is **not**
"the tripwire is weak" — it is that the patch is a no-op, for the reason in
§0.4: `out_row` gates all four weight/scale reads *and* the store together, so
any bijection over rows recomputes the same set of rows into the same set of
slots. See §1.2: this is exactly the argument that makes the whole sweep
bit-exact, so it had to be true.

### 3.2 Attempt 2 — desynchronise the store row from the read row (VALID)

`research/tanjiro_packing_fault.patch` (37 lines). Reads stay on the true
`out_row`; a new `store_row = tile * num_simdgroups + ((simd_gid + 1) %
num_simdgroups)` is used only at `projected[store_row]`. Still in bounds, and the
kernel name gains a `_fault` suffix so no cached compiled kernel can mask it.

Training `0010f873-b274-4dca-b4ca-a96fa7dddccc`, archived in
`research/packing-curve-logs/fault/`:

| `S` | `passed` | `checked_steps` | `first_failing_step` | `error` |
|---|---|---|---|---|
| 2 | **`False`** | 2 | 1 | `teacher-forced token mismatch` |
| 16 | **`False`** | 2 | 1 | `teacher-forced token mismatch` |
| 1 | `True` | 64 | `None` | `''` (negative control, see below) |

The public 64-step tripwire catches the defect **on the very first decode step**
at both the default packing and the PR #298 winner packing. The tripwire is
load-bearing, so the Stage 1 per-arm passes in §1.4 are meaningful and Stage 1 is
**VALID**.

`S=1` passing is not a hole — it is the control that makes the result
interpretable. At `S=1` the rotation is `(0 + 1) % 1 == 0`, i.e. the fault patch
compiles to identity. So the same rebuilt, `_fault`-suffixed binary passes at
`S=1` and fails at `S ∈ {2, 16}`. That rules out "the rebuild broke something"
and "the gate fails any patched worker": the verdict tracks the injected defect
and only the injected defect. My driver's global `EXPECT=fail` flagged `S=1` as
unexpected and exited 2; that is the script being rigid, and the three raw JSONs
are the evidence.

---

## 4. Rule 17 — the prefill axis

Rule 17 requires measuring both axes when a `DARKBLOOM_*` flag moves, because
prefill carries 25 % of the score and has its own hard `0.95` floor.

Here the answer is **structural before it is empirical**. The guard at
`LagunaRuntimeModel.swift:4823` is

```swift
normalized.dims(1, 1, hidden)
```

so `lagunaDecodeNVFP4QKVR1` can only fire for a single-token input. Prefill
passes `seq = 512` and never reaches this kernel at all — it goes through the
quantized-matmul path. `DARKBLOOM_DECODE_NVFP4_QKV_R1_SIMDGROUPS` therefore
cannot influence prefill by construction, not merely by measurement.

<!-- PREFILL_MEASURED -->

---

## 5. M4 → M5 transfer

This is the section that should decide what, if anything, ships. The repo's own
history is blunt about the failure mode: PR #48 arm `N` measured **−55.0 µs/step
on M4** and **+10.0 µs/step on ranked M5**, and PR #7 was **+7.32 % on M4 and
≈0.0 % on M5**. Both were core-count quantisation. A threadgroup-packing sweep is
*precisely* a core-count-quantisation experiment, so the prior for naive transfer
should be low.

### 5.1 The kernel is DRAM-stream-bound, so the effect is small by construction

Each row streams ≈1.15 KB (1024 B of NVFP4 codes + scale nibbles + bases +
row scale). Per kernel that is ≈9.4 MB at `rows=8192` and ≈11.8 MB at
`rows=10240`. At M4 Pro's ≈273 GB/s that is a **34–43 µs bandwidth floor per
kernel**, and the measured kernel time is close to it. Spread PR #298's 35 µs/step
across the ≈28 QKV GEMVs in a step and the per-kernel gain is **≈1.25 µs, i.e.
3–4 %**. So this is not a compute or arithmetic win at all; it is an *edges and
residency* win — ramp, drain, and how many simdgroups are resident — layered on
top of a stream-bound kernel. That framing matters because ramp/drain and
residency scale with **core count**, which is the axis that differs between this
host and the ranked machine.

### 5.2 Candidate mechanisms, and which of them transfer

| # | Mechanism | Direction | Transfers to M5? |
|---|---|---|---|
| 1 | Resident-simdgroup shortfall at small `S` (per-core TG-slot granularity, plus TG issue/retire rate — at `S=2` the distributor must place one TG every ≈8.5 ns machine-wide) | penalises **small** `S` | yes, roughly in TGs-per-core units |
| 2 | Per-TG ramp/drain at kernel boundaries (≈2.5–5 µs at `S=2` vs ≈0.3–0.6 µs at `S=16`) | penalises **small** `S` | yes, and *grows* with core count |
| 3 | Wave/tail quantisation | penalises **large** `S` | **sign can flip** — this is the documented cause of this project's M4→M5 reversals |
| 4 | DRAM page locality | weakly favours large `S` | weak either way |
| 5–7 | Input-vector reuse, i-cache pressure, intra-TG coalescing | ≈nil (the input vector is 4 KB and already L2/L1-resident; loads are already fully coalesced within a simdgroup) | n/a |

Composite prediction from 1+2 fighting 3: **a shallow U with a wide flat bottom
around `S ≈ 8–16`, a steep left wall at `S = 1–2`, and a machine-dependent right
wall.** Stage 1 (§2) is the test of that prediction.

The `S=32` right wall has a concrete cause even with zero threadgroup memory: a
1024-thread TG must be resident **atomically on one core**, needing ≈160–256 KB
of register file, which fragments internally and strands registers at retire
granularity; and 256 TGs over ≈40 M5 cores is only 6.4 TGs/core, which is too
coarse to balance.

### 5.3 The transfer argument, in TGs-per-core

The right invariant is not `S` but **threadgroups per GPU core**, because that is
what sets both residency headroom and tail quantisation. This host has **20**
GPU cores; the ranked M5 Max has **≈40**.

| `S` | TGs (full attn) | TGs/core on M4 Pro (20) | TGs/core on M5 Max (40) |
|---|---|---|---|
| 2 | 4096 | 204.8 | 102.4 |
| 4 | 2048 | 102.4 | 51.2 |
| 8 | 1024 | 51.2 | **25.6** |
| 16 | 512 | **25.6** | 12.8 |
| 32 | 256 | 12.8 | 6.4 |

Read that table across the diagonal. **M5 at `S=8` sits in numerically the same
TGs-per-core regime (25.6) as the M4 point I actually measured as good
(`S=16`).** M5 at `S=16` corresponds instead to M4 at `S=32` — a point on the
right wall that was never validated as good on any machine.

So the honest recommendation is:

- If exactly one value must ship **without an M5 measurement**, ship **`S=8`**,
  not `S=16`. It is the conservative transfer of the M4 optimum, and on M4 it is
  inside the flat bottom (§2), so the M4 cost of choosing it is small.
- `S=16` is defensible **only** with a paired M5 measurement. Shipping the raw M4
  argmax is exactly what PR #48 arm `N` did.

### 5.4 Rule of thumb for the Stage 2 sites

Falling out of §5.1–5.3: an `S`-repack pays only when **both** hold —

1. the TG count *after* the repack is still ≫ the ranked machine's core count
   (≳400 TGs on a 40-core M5), so tail quantisation cannot eat the gain; and
2. the kernel currently uses **≤64-thread TGs**, so there is a residency and
   ramp/drain deficit to recover in the first place.

§6 applies this to every candidate site, and it is what kills three of the four.

### 5.5 Stated uncertainties

Apple does not publish per-core threadgroup-slot counts or the distributor's TG
issue rate, so mechanisms 1 and 2 are inferred, not measured. Published M1/M2-era
occupancy numbers may not carry to M4/M5 under Dynamic Caching (M3+). And the M4
evidence that motivated this whole assignment was a single two-point A/B whose
effect size has roughly ±2× uncertainty. Stage 1 fixes the two-point problem on
M4; it cannot fix the cross-generation problem.

The cheapest measurement that would *discriminate* mechanism 1 from mechanism 2 —
and therefore settle transfer without an M5 — is an isolated dependency-chained
QKV-GEMV microbenchmark at `S=2` vs `S=16` (the pattern already exists at
`research/frieren_pr101_gatesp_dispatch_bench.swift`), recording
`GPUStartTime`/`GPUEndTime` and converting to achieved GB/s. If `S=2` shows
*lower achieved bandwidth*, it is mechanism 1, which transfers and predicts
`S=8 ≈ S=16` on M5. If both arms achieve the same GB/s and the gap is a constant
≈1 µs per launch, it is mechanism 2, whose gain scales with TG count *and* core
count — which would make the routed-MoE site in §6 the next real win. I did not
run this; it is the top follow-up.

---

## 6. Stage 2 — generalizing the repack

The assignment asks for the repack to be generalized behind
`DARKBLOOM_<KERNEL>_SIMDGROUPS` with the recipe

```
global_sg  = tgid.x * S + simd_index
old_group  = global_sg / OLD_SG
old_simd   = global_sg % OLD_SG
```

and an encode-time `total_sg % S == 0` assertion. I audited every decode GEMV
site that packs more than one simdgroup per threadgroup before writing any code,
because the audit changes the answer: **only one of the four sites is both safe
and plausibly profitable, and two are safe-but-provably-unprofitable.**

### 6.1 Site audit

All line numbers are in `Sources/MLXFastModel/LagunaRuntimeModel.swift` at base
`63ab67c8`.

| # | Site | current sg/TG | row index | rows/simd | TG mem | barrier | TGs now | Safe? |
|---|---|---|---|---|---|---|---|---|
| 1 | routed MoE gate/up packed top-8 R1 (`laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2`, decl 7564-7677) | hardcoded `* 2` @ **7588** | 7588 `logical_row = tile * 2 + simd_group` | 1 | none | none | 2048 (64-thread) | **SAFE** |
| 2 | o_proj gated affine NVFP4 (`lagunaGatedAffineOProjNVFP4Source`, 4035-4231) | `num_simdgroups = 2` @ **4170** | 4180-4181, already parametric | 4 | `gt[gate_heads]` @ 4091 | **4103** | 256 | SAFE for `S ≥ 2` |
| 3 | shared-expert gate/up rows1 (`laguna_shared_nvfp4_swiglu_qmv_rows1_bf16_v1`, 6820-6889) | hardcoded `* 2` @ **6835** | 6835 `row = tile * 2 + simd_group` | 1 | none | none | 256 | **SAFE** |
| 4 | fused down+residual `_r1_v5` (7870-7989) | 9, from `threadGroup: (288,…)` @ **8043** | 7905 `first_row = tile * outputs_per_simd` | 4 | 7954-7956 | **7963** | 512 (288-thread) | **UNSAFE** |

**Site 4 is unsafe for a general `S` sweep and the reason is structural, not
incidental.** At 7903 `uint slot = simdgroup_index_in_threadgroup;` and at 7906
`bool is_shared = slot == shared_slot;` — the nine simdgroups **are** the eight
routed experts plus the shared expert. Simdgroup index is *expert identity*, not
a row group. There is a real `threadgroup_barrier` at 7963 and a `slot == 0`
cross-simdgroup reduction at 7965-7985 over `threadgroup bfloat down_outputs[…]`
(7954-7956). The assignment's `global_sg / OLD_SG` recipe would silently
reassign experts. The only legal variant here is a multiple-of-9 packing
(`9·M`, `M ≤ 3` before hitting the thread cap), which is a different experiment.

**Site 2 is unsafe specifically at `S=1`** for the raw-logit arm: the
`threadgroup float gt[gate_heads]` at 4090-4103 is filled by `if (lid <
gate_heads)`, which requires `32·S ≥ gate_heads` (48 or 64 depending on layer).
The pre-activated twins (4364, 4382) have no gate block and are safe at all `S`.
Threadgroup memory is ≤256 B and constant in `S`, so it never limits occupancy.

### 6.2 Applying the §5.4 rule of thumb — three of four sites are dead

This is the useful result of the audit, and it is a *negative* one. Criterion 1
is "TG count after the repack must still be ≫ 40".

| # | Site | total sg | TGs at `S=16` | TGs/core on 40-core M5 | Verdict |
|---|---|---|---|---|---|
| 1 | routed MoE gate/up | 4096 | 256 (`S=8` → **512**) | 6.4 (`S=8` → **12.8**) | **PURSUE**, at `S=8` |
| 2 | o_proj gated affine | 512 | **32** | **0.8** | **KILL** |
| 3 | shared-expert gate/up | 512 | **32** | **0.8** | **KILL** |
| 4 | fused down+residual | 4608 | n/a (already 288-thread TGs) | 12.8 today | **KILL** |

- **Sites 2 and 3 collapse below the core count.** 512 total simdgroups repacked
  at `S=16` gives 32 threadgroups on a 40-core machine — **at least 8 cores get
  no work at all.** The repack would convert a mild residency deficit into a
  guaranteed idle-core deficit. For these two kernels the correct direction is the
  *opposite* one: more parallelism (split-K), not more packing. Site 2 is doubly
  immune because its 4 rows/simdgroup already make each simdgroup ~4× longer-lived,
  which is the same ramp/drain amortisation the repack is trying to buy.
- **Site 4 already has 288-thread threadgroups**, so criterion 2 fails: there is
  no ≤64-thread residency deficit left to recover. Expected gain ≈0 even ignoring
  the safety problem.
- **Site 1 is the only site that passes both criteria**: 4096 simdgroups in
  64-thread threadgroups, no threadgroup memory, no barrier, 1 row/simdgroup, and
  512 rows per expert slot so every `S ∈ {1,…,32}` divides cleanly. Note that here
  too §5.3 argues for `S=8` (512 TGs, 12.8/core) over `S=16` (256 TGs, 6.4/core).

Implementation note for site 1 if it is picked up: its kernel name is a static
literal at 7565, so it needs an `_sgN` suffix exactly like §1's knob, otherwise
the compiled-kernel cache will serve the `S=2` variant to every arm and the sweep
will silently measure nothing. This is the single easiest way to fake a null
result on this axis, and worth stating explicitly.

### 6.3 What I did not build

I did not land a generalized `DARKBLOOM_<KERNEL>_SIMDGROUPS` mechanism. Building
a shared abstraction across four sites when the audit says three of them are
provably unprofitable would add editable-surface bytes for no measurable path.
The audit table plus the `_sgN` note above is the deliverable that makes the one
live site a one-session experiment for whoever picks it up.

---

## 7. Verdicts

<!-- VERDICTS -->
