# PR #301 — Closing the two measured gaps between the shared and routed NVFP4 QMV kernels

Student: `maple-frieren`. Assignment `maple-2026-08-07o-shared-qmv-twin-gap` r1.
Base `codex/mlxfast-maple-20260804-advisor` @ `69178729b154cbb648ea0ce6152e92dbfdb17cc6`.
Submitted surface: `Sources/MLXFastModel/LagunaRuntimeModel.swift` only.

Host: `Mac16,11` M4 Pro, 20-core GPU, 48 GiB, macOS 26.5.2, **Apple GPU
generation 16**. `_nax` variants are unreachable here; neither mechanism has an
`mlx-generated` twin, so `nax_twin_check` is not applicable. Prefill numbers
from this host are not M5 evidence (standing rule 10). The low-memory startup
profile is active, which is expected below 64 GiB.

No ranked submission was attempted: the ranked pipeline was down for the whole
round (see the assignment). This is a banked, correctness-verified patch.

W&B run: <https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/ag6xhecn>
(run id `ag6xhecn`, project `wandb-applied-ai-team/mlxfast-maple`). It carries
88 scalars, six result tables (`local_iterate_runs`, `kernel_ab`,
`drift_tripwire_128step`, `correctness_aggregate`, `fault_injection`,
`free_run_trajectory`) and the raw per-arm score rows. Three summary flags are
deliberately not the "clean" value and are explained rather than suppressed:
`correctness/all_passed` is `False` because of the two cool-gate-aborted §5
slots, which produced no tokens at all (`correctness/cool_gate_aborts` is 2,
`correctness/token_mismatches` is 0, and
`correctness/no_mismatch_in_completed_runs` is `True`);
`correctness/fault_injection/all_as_expected` and
`correctness/free_run/faults_all_detected` are `False` because of the two null
fault arms `prefetch_stale` and `plane_byte` (§4.3–§4.4).
`correctness/free_run/guards_bit_exact` is `True`.

---

## 0. Headline

| Mechanism | Flag (opt-in, default OFF) | Verdict |
| --- | --- | --- |
| (a) K-block prefetch in the shared gate/up QMV | `DARKBLOOM_SHARED_QMV_PREFETCH` | **Kernel-level win; argmax-identical, detector power bracketed (§0.1 item 1).** −0.363 µs/call, 95 % CI [−0.495, −0.232], −4.80 %, = **−14.2 µs/step** |
| (b) Pairwise (halved) gate/up scale plane | `DARKBLOOM_SHARED_QMV_PAIRWISE_SCALES` (implies (a)) | **No benefit; regression of at least +1.93 %.** +0.139 µs/call, 95 % CI [+0.057, +0.221], = **+5.4 µs/step**; the invariant control also moved, so the accompanying −1.40 % whole-step delta is *not* attributable to this mechanism |

Mechanism (a) is the part of this patch worth banking. Mechanism (b) makes its
own kernel measurably slower, so I do not claim it.

**One caveat belongs in the headline, not only in §3.5.** In both ABBAs the arm
is perfectly confounded with slot *kind*: `ORDER="off on on off"` puts `on` in
the two middle slots and `off` in the two edge slots, and Stage 2 later
demonstrated that this host does move an *untouched* control kernel by
−0.449 µs (−1.16 %) between edge and middle slots. That demonstrated slot shift
has the same sign as, and is larger than, the −0.363 µs mechanism-(a) effect.
The Stage 1 invariant control (+0.056 µs, CI ±0.62 µs) is too wide to exclude
it: it excludes a *proportional* whole-process rescaling, not an *additive*
per-dispatch one. Perfect 6-versus-6 process separation is no defence, because
every `on` process sits in a middle slot. **The single most valuable missing
measurement is a reversed-`ORDER` Stage 1 separator** (`on off off on`); it was
not run (§7.3). Until it is, mechanism (a)'s −0.363 µs/call should be read as
"mechanism effect plus a slot term of unknown size and the same sign".

Mechanism (b)'s verdict is safer because it survives *a fortiori*: the
session/slot effect in Stage 2 made the untouched control **faster** by 1.16 %,
so the mechanism's own kernel getting 1.93 % slower puts the mechanism cost at
that or more (≈+3.1 % once the common shift is subtracted). What the argument
cannot exclude is an *opposite*-sign slot effect specific to the small kernel,
so the exact claim is "no evidence of benefit; the point estimate is a
regression of at least +1.93 %", not "proved harmful".

Both effects are far below this host's end-to-end resolution. Using one
denominator throughout — the `--local-iterate` decode wall of 12.78 ms/token
(§5), the same axis the ±0.73 % MDE is defined on — −14.2 µs/step is
**0.111 %**, i.e. **≈6.6× below** resolution. (On the split-instrumented probe's
9.825 ms step wall it is 0.145 %, and 0.166 % of that probe's GPU-busy time;
those are different axes and are not comparable with the MDE.) The end-to-end
ABBA in §5 lost half its slots to the 40 C cool gate and finished at **n = 1 per
arm**, so it is reported as three unreplicated point estimates with **no CI**
and is explicitly **not** treated as a refutation.

### 0.1 Framing: bit-exactness plus in-situ per-dispatch cost

The advisor's 2026-08-07T18:19Z nudge on PR #301 offered to accept this
experiment as a bit-exactness plus per-dispatch-cost result rather than an
end-to-end one, because the predicted effect is structurally below the M4 Pro
detection floor. **I take that framing.** The arithmetic is not close:

| Quantity | Value |
| --- | --- |
| Predicted mechanism-(a) benefit (upper bound, see below) | −14.2 µs/step |
| `--local-iterate` decode wall on this host (§5) | 12.78 ms/token |
| Predicted benefit as fraction of that wall | **0.111 %** |
| `--local-iterate` MDE at the reps this host can afford | **±0.73 %** |
| Ratio (matched denominators) | effect is **≈6.6× below** resolution |
| Same benefit on the split-probe step wall (9.825 ms, §1) — *different axis* | 0.145 % |

So the load-bearing evidence in this report is, in order:

1. **Bit-exactness of each mechanism independently**, argued from source
   (§2.2, §3.3) and demonstrated by teacher-forced greedy comparison with a
   **fault-injection power check** (§4.3) plus a compounding self-fed free-run
   trajectory hash (§4.4). Standing rule 16 applies: the equivalence oracle
   never dispatches this kernel (§4.1), so a zero-divergence result only means
   something once the same check is shown to catch a deliberately broken
   variant. The honest verdict from that check is *asymmetric*: mechanism (b)'s
   check has demonstrated power on exactly the branch it needs to cover, while
   mechanism (a)'s power is **bracketed** — the check catches zeroing the
   prefetched scales but not mis-indexing them, so for (a) rule 16's letter is
   met and its spirit only partly. §4.3 and §4.4 state that limitation rather
   than round it away.
2. **In-situ per-dispatch cost** of the kernel with each guard on and off
   (§2.1, §3.2), measured by ABBA with an invariant control.
3. The end-to-end ABBA (§5), which the 40 C cool gate cut to n = 1 per arm and
   which is therefore reported as unreplicated point estimates with no CI, and
   explicitly **not** as a refutation.

**On standing rule 25 (isolated vs in-situ).** The per-dispatch numbers in §2.1
and §3.2 are *not* isolated-proxy timings. They come from
`research/nezuko-pr158-gpuprof-hook.patch` applied to the vendored MLX dispatch
path in the real `mlxfast-runtime-worker`, running the real 512-token seed plus
teacher-forced decode loop, with `DARKBLOOM_GPU_PROFILE_SPLIT=1` so each
dispatch gets its own command buffer. There is therefore no isolated→in-situ
conversion factor to apply to the *delta*: the 7.53 µs/call figure is already an
in-situ per-dispatch cost, and the 39-dispatch/step count is an instrumented
count from the same trace, not an assumption.

The one place rule 25 still bites is the ×39 conversion to µs/step. Splitting
command buffers removes the overlap that the uninstrumented worker gets, so
`39 × delta` is an **upper bound** on the wall-clock benefit per step, not a
prediction of it. The floor of that bound is **~0**, not "a bit less than
−14.2 µs": the prefetch works by hiding scale-load latency inside the current
block's dot products, and in the unsplit regime some or all of that latency may
already be hidden by concurrency between this dispatch and its neighbours. #298
vs #300 puts the overlap discount at roughly half — but that is a *different*
kernel with a different occupancy, so borrowing the factor here gives an
illustration (≈−7 µs/step, ~0.05 % of the 12.78 ms wall), not an estimate.
Sign preservation under overlap is **untested**: this report measured the
regime it could resolve, not the scored regime. Every µs/step number below
should be read with that upper-bound caveat.

---

## 1. Stage 0 — reachability, by instrumented count

Method: the pre-built worker carrying `research/nezuko-pr158-gpuprof-hook.patch`
driven by `research/decode_probe.py --profile` with
`DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=1` (one dispatch per
command buffer). Raw digest: `research/shared-qmv-logs/stage0.probe.log`.

Steady decode step on this host: wall **9.825 ms**, GPU busy **8.552 ms**,
13.0 % gap, 406 command buffers / dispatches per step.

The kernel under test is live and it is the Rows1 variant:

| Kernel | dispatches/step | µs/call | µs/step | share of GPU busy |
| --- | --- | --- | --- | --- |
| `laguna_shared_nvfp4_swiglu_qmv_rows1_bf16_v1` | **39** | 7.53 | 293.7 | 3.43 % |
| `laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_…r1…` (routed twin, invariant control) | 39 | 38.5 | 1502 | 17.6 % |

39 dispatches/step = one per sparse layer, so the shared Rows1 kernel runs on
every sparse layer of every decode step. The 2-row twin at the old `:6719`
never appears in the profile: `DARKBLOOM_SHARED_QMV_R1` defaults ON and the
`_rows1_` suffix in the observed kernel name is the R1 arm. Reachability is
established by count, not by reading the comment.

Dispatch geometry, read from the source and confirmed by the recorded
GPUPSO: `tiles = 256`, 16,384 threads, 2 simdgroups/threadgroup,
1 row/simdgroup across two streams (gate + up), ≈1.0 MiB weights per dispatch,
`maxTotalThreadsPerThreadgroup=1024`, `threadExecutionWidth=32`,
`staticThreadgroupMemoryLength=0`.

For scale, the other large per-step items: `decode_nvfp4_qkv_h64` ≈1352 µs,
`oproj_act_h64` ≈1130 µs, `routed_shared_nvfp4_down_residual…r1_v5` ≈881 µs,
`sliding_fused_attn_ring_v1` ≈637 µs, `lmhead_int5_base_coarse_delta` ≈423 µs.

### 1.1 Correction to the assignment's model of the call site

The assignment describes the shared QMV as dispatched from the shared-expert
MLP's `callAsFunction`. On the scored decode path it is **not**. There are two
call sites of `lagunaSharedSwiGLUQMV`:

- `LagunaRuntimeMLP.callAsFunction` (`LagunaRuntimeModel.swift:8638`), and
- `LagunaRuntimeMLP.fusedSharedDownInputs(_:sharedActivation:)` (`:8490`),
  reached through `fusedSharedBankGuard`.

The live scored path is **`fusedSharedDownInputs`**, which I established the
hard way: the first Stage 2 build trapped at startup, and the crash report in
`/Library/Logs/DiagnosticReports` symbolized a `SIGTRAP` on the
`MLXArray.dims(_:)` precondition inside `lagunaSharedSwiGLUQMV` with
`fusedSharedDownInputs` as the caller. Any change to the arguments of this
kernel must be routed through **both** sites; changing only
`callAsFunction` is a no-op on the scored path. This is worth recording for
future assignments that touch the shared expert.

---

## 2. Stage 1 — the K-block prefetch

### 2.1 What changed

`lagunaSharedSwiGLUQMVRows1Kernel` previously loaded weight codes and scales at
point of use, inside the `laguna_nvfp4_qdot_16(...)` call, leaving one
outstanding load stream per thread. The routed twin has a prefetch prologue, a
next-tile load issued before the current tile's FMAs, and a deferred consume.

The new arm (opt-in, `DARKBLOOM_SHARED_QMV_PREFETCH`) ports that structure:

- prologue loads block 0's `uint2` codes and its two scale bytes into registers
  before the loop;
- inside the loop, the next block's codes and scales are issued **before** the
  current block's `laguna_nvfp4_qdot_codes_16` FMAs;
- the current block's registers are consumed after that issue, and the
  prefetched registers are rotated in.

Flag form, read from the `getenv` expression itself rather than the comment
(`LagunaRuntimeModel.swift:6810-6812`):

```swift
private let lagunaSharedSwiGLUQMVPrefetchEnabled =
    ProcessInfo.processInfo.environment["DARKBLOOM_SHARED_QMV_PREFETCH"] == "1"
    || lagunaSharedSwiGLUQMVPairwiseScalesEnabled
```

`== "1"` is the strict opt-in form: absent ⇒ OFF. No inverted form, no
`atoi` of an unchecked pointer.

### 2.2 Bit-exactness argument

The prefetch changes **when** a value is loaded and never the arithmetic. The
key identity is in the shared qdot header at `:6708-6715`:

```metal
static inline float laguna_nvfp4_qdot_16(
    const device uint8_t* weight, const thread float* input, float scale
) {
    const device uint2* packed = (const device uint2*)weight;
    return laguna_nvfp4_qdot_codes_16(packed[0], input, scale);
}
```

So the baseline arm's `laguna_nvfp4_qdot_16(gate_row_weight + block/2, …)` is
*by definition* `laguna_nvfp4_qdot_codes_16(*(const device uint2*)(gate_row_weight
+ block/2), …)`. The prefetch arm calls `laguna_nvfp4_qdot_codes_16` with the
identical `uint2`, loaded one iteration earlier into a register. Concretely:

- same `laguna_nvfp4_qdot_codes_16` per-block call sequence, same per-lane K
  ordering, same `input_values` block load (untouched, shared by both arms);
- the number of `laguna_nvfp4_scale` sites is unchanged at one per output
  stream (gate, up). `laguna_nvfp4_qdot_codes_16` ends in `return scale * accum`
  (`:6705`), so the scale still multiplies the same group of 16 as the last
  operation of that group's dot product — the `scale_defer` invariant holds;
- the per-row private FP32 accumulators `gate_result` / `up_result` and the
  32-lane `simd_sum` are untouched, so the reduction order is unchanged;
- the `if (next_block < input_width)` guard means the last block's registers are
  consumed but nothing beyond the tensor is read, and no block is consumed twice
  or skipped (`cur_*` snapshots are taken before the next-block issue).

Empirically, all 12 Stage 1 processes (6 OFF, 6 ON) produced **0 teacher-forced
greedy-token divergences** against the public golden, and the recorded launch
geometry (the GPUPSO fields in §1: tiles, threads, simdgroups/threadgroup) is
identical between arms. The kernel *source* is of course not identical, so this
subsection is a source-level argument, and it has a real gap: it shows the
value stream and reduction order are unchanged, but it cannot exclude the
Metal compiler re-associating or re-scheduling FP32 work differently after the
loop is restructured. Only §4.3's demonstrated-power check speaks to that, and
what it can and cannot certify is stated there.

### 2.3 Per-kernel A/B result

Driver: `research/maple_shared_qmv_prefetch_abba.sh`, ABBA order
(`off on on off`), `REPS=3 STEPS=33`, one worker process per arm, 12 processes,
1,248 steady calls per *process* (32 steady steps × 39 dispatches), so 7,488 per
arm. Digest:
`research/shared-qmv-logs/stage1.prefetch-abba.log`.

| Arm | µs/call (mean of 6 processes) | sd across processes |
| --- | --- | --- |
| OFF | 7.573 | 0.120 |
| ON | 7.210 | 0.070 |

Δ = **−0.363 µs/call**, Welch 95 % CI **[−0.495, −0.232]**, −4.80 %, df 8.1,
with perfect 6-versus-6 separation (every ON process is faster than every OFF
process). Per step: 39 calls × −0.363 µs = **−14.2 µs/step**.

Invariant control — the routed twin, which the change cannot touch:
**+0.056 µs/call, CI [−0.563, +0.674]**, i.e. a null, so the effect is not a
whole-process speed shift mislabelled as a kernel effect.

**Achieved precision, honestly.** The standard error of the OFF→ON delta is
**0.0567 µs/call** (t ≈ 6.4 on df 8.1). The advisor's nudge asked for the
per-dispatch SE to be under ~5 % of the *predicted* per-call delta. Against the
delta I actually measured (0.363 µs) that target is **0.018 µs and I am 3.1×
short**; the 0.028 µs figure I quoted earlier corresponds to 5 % of a ≈0.56
µs/call prediction, which the measurement did not support. Take the stricter
reading: **3.1× short**. What I have is a delta 6.4 standard errors from zero
with perfect 6-versus-6 process separation, but the ±0.13 µs CI width pins the
*magnitude* only to about ±36 %, and the separation is confounded with slot kind
(§0, §3.5), so it is not independent corroboration.
Reaching 0.018 µs would need roughly 10× the process count on a host whose
40 C idle already costs a cool-gate failure every few runs; even the 4× needed
for 0.028 µs is ≈33 min of instrumented GPU time per arm. I judged more
precision on a confounded contrast to be worth less than the reversed-`ORDER`
separator (§7.3), and I am flagging the shortfall rather than quietly rounding
the CI.

`DARKBLOOM_GPU_PROFILE_SPLIT=1` puts one dispatch per command buffer; that is
what makes a 0.36 µs/call effect measurable at all. It also means these
per-call numbers are *not* end-to-end numbers, which §5 covers separately, and
that the ×39 step conversion above is an upper bound (§0.1, standing rule 25).

---

## 3. Stage 2 — the pairwise (halved) gate/up scale plane

### 3.1 The layout question the assignment asked me to answer

The assignment's fallback was "if the shared expert's scale plane is not laid
out pairwise on disk, stop and describe an offline repack in
`Sources/MLXFastTransform`". **No transform change is needed**, because the
plane is already pairwise-redundant *in value*: the checkpoint's NVFP4 group-16
scales for the shared gate/up tensors are equal within each even/odd pair
almost everywhere. That is not an assumption — the branch installs the halved
plane only after checking it.

The base tree already contains the certifying helper,
`lagunaHalvedGroup32ScalePlane(_:allowedFlatPairs:)`
(`Sources/MLXFastWeights/…/LagunaRuntimeWeights.swift:985`), which the routed
packed bank uses. It walks the plane pair by pair, keeps the even byte, and
returns `nil` unless every discarded odd byte is bitwise equal to its even
partner — except for an explicit allow-list of pair indices whose true odd byte
is stored in a small header. So the halving is **lossless by construction or it
does not install at all**; there is no "mostly equal" path.

On the fused `[gate; up]` shared plane the quantizer leaves exactly two pairs
unequal: the first pair of the gate tensor and the first pair of the up tensor.
Those are the pairs I pass as `allowedFlatPairs`:

```swift
allowedFlatPairs: [0, gate.scales.size / 2]   // = [0, 32768]
```

The helper indexes **pairs**, not bytes. The fused plane is 131,072 bytes =
65,536 pairs; up-row 0 group 0 sits at flat byte 65,536, i.e. pair 32,768. Both
indices are therefore correct, and the resulting plane is
`lagunaSharedGateUpHalvedScaleBytes = lagunaScalePatchHeaderBytes + 131,072 / 2
= 128 + 65,536 = 65,664` B (equivalently 2 streams × 512 rows × 64 B + 128),
i.e. the 128-byte patch header (`LagunaRuntimeWeights.swift:953`) plus one kept
byte per pair. The header is what the kernel prologue re-patches for the two
allow-listed pairs, so its size is load-bearing for the in-bounds argument
below, not incidental.

### 3.2 What changed in the kernel

Row-scale pointer setup (`:6828-6847`) switches to the halved plane and skips
the header, and the per-block index divides by 32 instead of 16:

```metal
// pairwise arm
const device uint8_t* gate_row_scale =
    fused_scales + scale_patch_bytes + row * scale_row_bytes + (lane >> 1);
...
gate_sb = gate_row_scale[next_block / 32];    // was next_block / 16
```

The index algebra: a K-block is 512 weights, so the group a lane needs is
`block / 16 + lane` and the halved-plane byte it lives in is
`block / 32 + (lane >> 1)`. This split is exact because
`block / 16 ∈ {0, 32, 64, 96}` is always even for the four blocks of this
kernel, so the pair index never straddles a lane boundary. The pointer carries
the constant `(lane >> 1)` term and the loop supplies `next_block / 32`.

The two allow-listed pairs are restored in the prefetch prologue
(`:6885-6892`), which is why the pairwise arm implies the prefetch arm:

```metal
bool patch_lane = row == 0 && lane == 1;
uint8_t gate_sb = patch_lane ? fused_scales[0] : gate_row_scale[0];
uint8_t up_sb   = patch_lane ? fused_scales[1] : up_row_scale[0];
```

Only lane 1 of row 0 ever reads an odd pair member that could differ (group 1
of the first pair), and only at block 0, so `patch_lane` covers exactly the two
allowed exceptions and nothing else. Every other lane reads an even member,
which the halved plane stores verbatim.

`scale_row_bytes` drops 128 → 64 and the kernel name becomes
`laguna_shared_nvfp4_swiglu_qmv_rows1_ps_bf16_v1`, so a profile can tell the two
arms apart by name.

### 3.3 Bit-exactness argument

The same scale byte value multiplies the same group of 16 at the same point in
the accumulation. Only the *address* it is fetched from and the *width of the
region* covered by that byte change. The pairwise arm cannot silently degrade:
if any pair outside the allow-list were unequal, `lagunaHalvedGroup32ScalePlane`
returns `nil`, `_fusedGateUpHalvedScales` stays nil, and both QMV call sites
fall through to the existing full-density path rather than being handed a plane
of the wrong density (`:8478-8495`, `:8618-8643`). I made that decline explicit
rather than implicit, and it emits a one-time certificate:

```
mlxfast: packed-scales active: shared gate/up halved scale plane
```

Observed on this host, so the plane certified and installed.

Two limits of that certificate are worth naming. It certifies *pairwise scale
equality*, i.e. that halving loses no information; it does **not** certify that
the kernel then indexes the halved plane correctly — that is exactly what the
`plane_shift` and `plane_byte` fault arms in §4.3 probe. And the allow-list is
`[0, 32768]` (`LagunaRuntimeWeights.swift:8408`), so the certificate is a
statement about the two flat pair offsets this transform actually halves, not
about the tensor as a whole.

### 3.4 Byte accounting

Per dispatch the kernel reads ≈1.0 MiB (1,048,576 B) of NVFP4 weight codes plus
the gate/up scale plane. The scale plane falls from 131,072 B to 65,664 B, so
the per-call byte stream drops from 1,179,648 B to 1,114,240 B: the saving is
65,408 B, i.e. **5.55 % of the 1.18 MB per-call byte stream**, and the
weights-per-scale-byte density rises from 16 to 32 (`scale_row_bytes` 128 → 64).
It removes **no** load instructions — the same
number of scalar byte loads is issued, they just hit half as many cache lines.
Extra resident memory is 65,664 B × 39 layers ≈ **2.6 MB**, on top of the
full-density plane which is kept for the fallback.

### 3.5 Result — the mechanism is refuted, and its whole-step delta is not attributable

Driver: `research/maple_shared_qmv_prefetch_abba.sh`, `REPS=3 STEPS=33
ORDER="on pairwise pairwise on"`, 12 worker processes (6 per arm), 1248 steady
calls per **process** and therefore 7,488 per arm.
Supervised launch `fc455230-07e8-485b-b5d0-f4e1370723b7`, exit 0, 491 s.
Digest: `research/shared-qmv-logs/stage2.pairwise-abba.log`.

`on` here is Stage 1's winning prefetch arm, so this A/B isolates only the
scale-plane density change.

| Kernel | `on` µs/call (sd) | `pairwise` µs/call (sd) | Δ | 95 % CI | Δ % |
| --- | --- | --- | --- | --- | --- |
| `laguna_shared_nvfp4_swiglu_qmv_rows1_bf16_v1` (changed) | 7.210 (0.078) | 7.350 (0.026) | **+0.139** | [+0.057, +0.221] | **+1.93 %** |
| `routed_shared_nvfp4_…_qmv_…` (invariant control) | 38.817 (0.250) | 38.368 (0.075) | **−0.449** | — | **−1.16 %** |

(Δ is computed from the unrounded per-process means, so it does not equal the
difference of the three-decimal means printed here: 7.350 − 7.210 = 0.140 by
display, +0.139 in full precision. The same applies to Stage 1's −0.363.)

Two facts to read together:

1. **The mechanism failed on its own kernel.** Halving the scale plane made the
   kernel it changes *slower* by +1.93 % (df 6.1, perfect 6-v-6 separation).
   `on`'s mean reproduced Stage 1's `on` mean to three decimals (7.210), so the
   harness was stable across the two stages. The likely cause is that the kernel
   was never scale-fetch-bound: the same number of scalar byte loads is still
   issued (§3.4), the pair-index arithmetic adds work, and the halved plane's
   lower spatial locality per lane costs more than the saved cache lines.
2. **The invariant control moved, so per-kernel attribution is invalid for this
   stage.** The routed twin is untouched by this patch and it got 1.16 % faster
   with perfect separation. Every memory-heavy *decode* kernel moved the same
   way (`down_residual` −2.65 %, routed qmv −1.15 %, `oproj` −0.75 %, `qkv`
   −0.58 %), while the prefill-dominated `nvfp4_gather_qmm` did not
   (−0.03 %). Whole-step wall fell 9.8973 (sd 0.1349) → 9.7587 ms (sd 0.0254),
   −1.40 %; GPU busy 8.5923 → 8.5243 ms, −0.79 %; 406 command buffers in both
   arms.

Candidate explanations for (2), ranked, with what would separate them. None is
established; I did not run the separating experiment.

1. *Arm ↔ slot-within-rep confound.* The rep order is palindromic, so each arm
   has the same **mean** slot (2.5) — but not the same **kind** of slot: `on`
   always occupies the two edge slots and `pairwise` always the two middle
   slots. The variance pattern is consistent with a slot effect in both stages:
   the edge arm has the larger process-level sd in both, by **1.7×** in Stage 1
   (`off` 0.120 vs `on` 0.070) and **3.0×** in Stage 2 (`on` 0.078 vs
   `pairwise` 0.026). Only the Stage 2 ratio is large; treat Stage 1's as
   suggestive at best, since an sd ratio from n=6 vs n=6 has a wide sampling
   distribution and 1.7× is well inside it. It is *not*
   consistent in sign — the edge arm is the slower one in Stage 1 and the
   faster one in Stage 2 — so a monotone edge penalty cannot be the whole
   story, but a slot-linked variance/level effect is not excluded. The driver's
   own comment that a host drift "cannot line up with arm labels" is true for
   mean position and false for edge-vs-middle.
   *Separator (cheap, env-only, ~500 s):* rerun with `ORDER="pairwise on on
   pairwise"`. If the control's −1.16 % follows the *slot* it is an artifact; if
   it follows the *arm* it is real.
2. *Decode-phase cache-capacity relief.* Decode with `pairwise` stops streaming
   the full 5.1 MB gate/up scale planes, which frees system-level cache for the
   routed experts. This is the only candidate that also explains the axis
   asymmetry: prefill takes the QMM path in both arms, and prefill-dominated
   `nvfp4_gather_qmm` moved −0.03 % while every decode neighbour moved
   −0.6…−2.7 % in one direction. The magnitude is still unexplained (≈2.55 MB
   of scale traffic removed per step vs ≈59 µs/step gained across neighbours).
3. *Power/DVFS headroom.* Less DRAM traffic during decode can raise sustained
   clocks, and prefill runs in a different power regime. No clock or power
   telemetry was captured, so this is untested.
4. *Allocation/heap-layout side effect.* The pairwise arm allocates one extra
   buffer per layer, which changes heap layout and page placement for
   everything else. Weakened by the fact that the halved plane also exists
   during prefill, which did not move. *Separator:* an allocate-but-do-not-use
   arm (build the plane, keep the `_ps_` kernel off).
5. *Bandwidth sharing between the two QMV kernels.* Refuted: `SPLIT=1`
   serialises the profiled dispatches, so the two kernels are not concurrently
   contending, and the byte magnitudes differ by ~10×.
6. *Argument-encoding or TLB effects.* Ruled out by inspection: the same three
   buffers are bound, and ~4 fewer pages per layer is negligible.

One earlier draft of this section claimed the pairwise arm "builds a second
pipeline-state object". That is wrong and it is withdrawn. The flag selects a
kernel **name** in a single `MLXFast.metalKernel` construction
(`:6933-6936`), so exactly one pipeline exists per process either way; the only
extra cost is a one-time JIT/library compile for the differently-named variant,
which happens before the steady window the statistics use.

Verdict: mechanism (b) is **refuted** as a kernel-level optimisation, and its
whole-step delta is **not claimed**, because the stage does not satisfy its own
invariant-control precondition. The honest residue is a *new* observation worth
its own experiment (§7): on this host, reducing decode-phase scale traffic
appears to speed up unrelated decode kernels far more than it speeds up the
kernel whose traffic was reduced.

Two further limits on this stage, for the record. The six neighbour-kernel
comparisons quoted above carry **no multiplicity control**; their evidential
weight comes from the uniform direction and the prefill/decode asymmetry, not
from any single one of them. And Stage 1's "the control did not move" precondition
is only asserted to Stage 1's own resolution: its control CI is ±0.62 µs
(±1.6 %), which cannot exclude a shift of the size Stage 2 later observed
(−0.449 µs). Both stages' process-level intervals also treat 6 process means as
i.i.d. despite the fixed order, so they should be read as descriptive rather
than as strict frequentist coverage.

---

## 4. Correctness

### 4.1 What the upstream-equivalence oracle actually exercises: **neither mechanism**

The assignment asked me to state which of the two changes the oracle reaches
and how I know. The answer is that it reaches **neither**, and the reason is
structural.

Both call sites of `lagunaSharedSwiGLUQMV` are guarded on
`_fusedGateUpWeight` / `_fusedGateUpScales` being present
(`LagunaRuntimeModel.swift:8478-8495` and `:8618-8643`). Those are installed
only by `prepareFusedSharedGateUp()` (`:8375`), which is called only from
`LagunaRuntimeModel.prepareFusedRuntimeWeights()` (`:11192`), which in turn has
exactly one caller: `LagunaRuntimeWeights.loadLibraryModel(loader:config:)`
(`LagunaRuntimeWeights.swift:611`).

`LagunaUpstreamEquivalence.swift` does not use `loadLibraryModel`. It builds
`LagunaRuntimeModel(runtimeConfig)` directly, installs arrays with
`update(parameters:verify:)`, and `eval`s
(`LagunaUpstreamEquivalence.swift:66-88`). So `prepareFusedRuntimeWeights()`
never runs, the fused shared gate/up banks stay nil, both guards fail, and the
shared QMV kernel is never dispatched inside the oracle.

That is confirmed by the Stage 1 equivalence pair itself: the prefetch-ON run
and the unchanged-base run produced **byte-for-byte identical** reports —
identical down to `maximumAbsoluteLogitError 0.125` and mean
`0.011933609` on prefill and exact zeros on all 8 decode steps
(`research/shared-qmv-logs/equivalence.prefetch-vs-base.log`). Identical is
what you get from a change the oracle cannot see. I am **not** presenting that
run as positive coverage of the kernel; it is evidence of no collateral damage
to the paths the oracle does cover, and nothing more.

The prefill delta of 0.125 is present on the unchanged base too, so it is
host-intrinsic to this generation-16 machine, not a product of this branch. No
`MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT` override was used anywhere in this round.

### 4.2 What does cover the mechanisms: the scored-path drift tripwire

Because the oracle is blind here, the load-bearing correctness evidence is the
teacher-forced greedy-token comparison run **through the real worker on the
scored decode path**, where the fused banks exist and the kernel demonstrably
dispatches 39×/step (§1).

**Instrument.** `research/decode_probe.py` drives the release worker
`.build-worker/release/mlxfast-runtime-worker` over its line-delimited JSON
protocol using `correctness_prompts/public_longcopy_gate_english_512_256.json`
(512 prompt tokens, 256 expected tokens). It sends one `decode_begin` with the
512-token seed, then N `decode_step` requests. Step *i* is fed `expected[i]`
and its returned argmax is compared against `expected[i+1]`
(`research/decode_probe.py:136-145`). Because the *expected* token is fed
forward rather than the model's own, a divergence cannot propagate and cannot
mask later steps: all N comparisons are independent checks of the same
distribution the harness checks, which is strictly stronger per-step coverage
than a free run of the same length.

**The ≥64-step requirement, at 128 steps, all three arms.** Log:
`research/shared-qmv-logs/drift-tripwire-128step.log` (raw worker stderr in
`/tmp/maple-shared-qmv-drift/`).

| Arm | Steps compared | Divergences | Step mean | Seed forward |
| --- | --- | --- | --- | --- |
| `off` (base) | 128 | **0** (all match) | 8.183 ms | 547.26 ms |
| `on` (prefetch) | 128 | **0** (all match) | 8.211 ms | 547.46 ms |
| `pairwise` (prefetch + halved plane) | 128 | **0** (all match) | 8.179 ms | 547.30 ms |

Reproduce (one arm; must be the only model-holding process on the host):

```bash
DARKBLOOM_SHARED_QMV_PAIRWISE_SCALES=1 \
  python3 research/decode_probe.py --steps 128 \
  --stderr /tmp/maple-shared-qmv-drift/03-rep1-pairwise.err
```

Two properties of this particular run make it the cleanest correctness
evidence in the round:

1. It ran on the **uninstrumented** worker. `./benchmark.sh --local-iterate`
   had rebuilt `.build-worker`, which discards the research GPUPROF hook
   (`research/nezuko-pr158-gpuprof-hook.patch`) that Stages 1 and 2 relied on;
   every arm's log therefore ends `profile: no GPUPROF records`. So these
   tokens came out of exactly the binary the scored path builds, with no
   research patch in the vendored MLX.
2. At 39 dispatches per decode step (§1), 128 steps is **4,992
   `laguna_shared_nvfp4_swiglu_qmv_rows1_bf16_v1` dispatches per arm** with
   every intervening greedy argmax checked. That exercises the prefetch
   `next_block < input_width` tail guard (`:6910`) on every K-block of every
   dispatch, and in the `pairwise` arm the even-index read of the halved
   gate/up scale plane (`:6888-6890`) on every dispatch.

**Aggregate over the whole round.** Every model-holding process launched in
Stages 1, 2, 2b and the tripwire ran the same teacher-forced comparison, so the
divergence count accumulates:

| Source | Processes | Steps each | Comparisons | Divergences |
| --- | --- | --- | --- | --- |
| Stage 1 (`off`×6, `on`×6) | 12 | 33 | 396 | 0 |
| Stage 2 (`on`×6, `pairwise`×6) | 12 | 33 | 396 | 0 |
| Stage 2b, cancelled (`pairwise`×3, `on`×3) | 6 | 33 | 198 | 0 |
| Drift tripwire (`off`, `on`, `pairwise`) | 3 | 128 | 384 | 0 |
| **Total** | **33** | — | **1,374** | **0** |

By arm: 326 comparisons on `off`, 623 on `on`, 425 on `pairwise`.

"Stage 2b" is a first, cancelled attempt at the §3.5 pairwise ABBA: the worker
it launched had been rebuilt without the research GPUPROF hook, so it emitted no
per-kernel records and its **timing is discarded and appears nowhere in this
report**. I did not archive a digest for it, so the only thing it contributes is
the 198 teacher-forced comparisons above, which each process prints
independently of GPUPROF. If you would rather not count an unarchived run at
all, subtract it: the round total becomes 27 processes and **1,176 comparisons,
0 divergences**, and nothing else in the report changes.

Two honest limits on this evidence. First, it is one prompt: the tripwire and
both ABBA stages use the same public golden, so it covers 128 distinct
positions and 4,992 dispatches but only one token distribution. The hidden
512-token teacher-forced cases, hidden anchors, free runs and the semantic GPQA
judge on the official M5 remain the real gate. Second, both mechanisms are
argued bit-exact from the source (§2.2, §3.3) — the tripwire's job is to catch
a mistake in that argument, not to establish tolerance, and a zero here is
consistent with the bit-exactness claim rather than a substitute for it.

Third, and most important: §4.3 measures how much this check can actually see,
and the answer is *less than I assumed*. It catches a zeroed prefetch scale but
**not** a stale one, so these 1,374 zeros give mechanism (a) only coarse
protection against the specific bug class §2.2 has to exclude. Read this section
with §4.3 and §4.4, not on its own.

### 4.3 Fault injection — does that zero have any power?

§4.2's 1,374 comparisons at 0 divergences are worthless on their own. A check
that cannot fail reports zero regardless, and §4.1 has just established that
the one automated oracle in the tree is structurally blind to this kernel. So
standing rule 16 applies: before the zero counts as evidence, the same check
must be shown to catch a deliberately wrong build **of each mechanism
separately**.

**Design.** `research/maple_pr301_fault_injection.py` injects five env-gated
faults into the working tree — never committed to the submitted surface, so
`LagunaRuntimeModel.swift` byte growth is unaffected — and
`research/maple_shared_qmv_fault_injection.sh` builds **one** worker that serves
every mode, runs each arm through the identical 128-step teacher-forced probe
used in §4.2, and then reverts the hooks and rebuilds a clean worker from a
`trap … EXIT` so no faulted binary can survive the run. Each fault mode also
gets its own pipeline-state name (`…_fault_<mode>`), so a stale PSO cannot
silently serve a fault arm.

| Fault mode | Mechanism | What it breaks | Why this fault |
| --- | --- | --- | --- |
| `prefetch_stale` | (a) | The prefetch loads `block / weightsPerScaleByte` instead of `next_block / …`, so K-blocks 1–3 of every row use the previous block's scale byte | This is *the* bug the prefetch rewrite could plausibly contain: issuing the load but forgetting to advance the index. If the tripwire cannot see this, it cannot vouch for §2.2 |
| `plane_byte` | (b) | One data byte of the halved group-32 scale plane is bit-flipped (`faultBytes[1] ^= 1`), corrupting the scale of exactly 16 gate weights of one row | The **smallest possible** "halved plane is wrong" fault — a deliberately hard test of sensitivity, not a softball |
| `plane_shift` | (b) | The plane's whole data region is shifted one byte left, so every lane of every row reads its neighbour's scale | A gross version of the same class, to separate "the check is insensitive" from "this particular fault is subthreshold" |
| `prefetch_zero` | (a) | `gate_sb = 0; up_sb = 0;` is appended at the **same patched line**, so K-blocks 1–3 contribute nothing | Calibration. If this also passes, the check is blind at that site and no (a) result means anything. It is the upper end of a sensitivity bracket around `prefetch_stale` |
| `activation_zero` | whole kernel | `activated[row] = bfloat(silu * up) * bfloat(0);` — the rows-1 kernel writes zeros | Calibration of the probe itself: bounds the tripwire's power from above for the entire shared-expert path |

**Arms.** Two controls and five faults, all on the same faulted binary, so a
control that passes rules out "the injected build is broken everywhere":

```text
on-control                 PREFETCH=1                    FAULT=                 -> expect 0
on-fault-prefetch_stale    PREFETCH=1                    FAULT=prefetch_stale   -> expect >0
on-fault-prefetch_zero     PREFETCH=1                    FAULT=prefetch_zero    -> expect >0
on-fault-activation_zero   PREFETCH=1                    FAULT=activation_zero  -> expect >0
pairwise-control           PAIRWISE_SCALES=1             FAULT=                 -> expect 0
pairwise-fault-plane_byte  PAIRWISE_SCALES=1             FAULT=plane_byte       -> expect >0
pairwise-fault-plane_shift PAIRWISE_SCALES=1             FAULT=plane_shift      -> expect >0
```

**Result.** Battery `a22ac0dc-d18e-435c-bfe4-7d0b70039572`, exit 0, 362 s,
`/tmp/maple-shared-qmv-fault2/summary.txt`:

| Arm | Divergences / 128 | First `(step, expected, got)` | Step mean | Verdict |
| --- | --- | --- | --- | --- |
| `01-on-control` | 0 | — | 8.210 ms | as expected |
| `02-on-fault-prefetch_stale` | **0** | — | 8.236 ms | **fault not detected** |
| `03-on-fault-prefetch_zero` | 95 | (2, 5991, 947) | 8.348 ms | detected |
| `04-on-fault-activation_zero` | 125 | (1, 902, 290) | 8.590 ms | detected |
| `05-pairwise-control` | 0 | — | 8.179 ms | as expected |
| `06-pairwise-fault-plane_byte` | **0** | — | 8.320 ms | **fault not detected** |
| `07-pairwise-fault-plane_shift` | 17 | (12, 509, 81) | 8.215 ms | detected |

Two of five fault arms did not fire, so the W&B
`correctness/fault_injection/all_as_expected` flag is **False**. I am reporting
that rather than dropping the inconvenient arms. What it means, mechanism by
mechanism:

**The hook sites are live — the "structurally blind" hypothesis is dead.**
`prefetch_zero` is injected at *the same patched line* as the shipped prefetch
loads (`Sources/MLXFastModel/LagunaRuntimeModel.swift:6927-6929`) and flipped
95 of 128 tokens starting at step 2. `activation_zero` flipped 125 of 128
starting at step 1. So the fault plumbing compiles, the per-mode PSO name
defeats caching, the kernel is dispatched on the scored decode path, and the
128-step probe *can* see a wrong shared-expert result. That is the letter of
rule 16 for mechanism (a).

**But the realistic-bug arm for (a) is null, and that is a magnitude result,
not a dead hook.** With `prefetch_stale` the emitted Metal is
`gate_sb = gate_row_scale[block / 16]` instead of `… [next_block / 16]`. Since
the scale pointer is already lane-biased and the index advances by 32 bytes per
512-wide K-block, lane *L* in K-block *i* then consumes the group-16 E4M3 scale
of lane *L* in K-block *i−1*: **3 of every 4 K-blocks of every row of both the
gate and up projections use a neighbouring group's scale**, and not one of 128
greedy argmaxes moved. The demonstrated sensitivity of this check at this site
is therefore bracketed: it catches *zeroing* those three K-blocks and does not
catch *mis-scaling* them. Two explanations are consistent with the data and I
cannot separate them here — adjacent group-16 maxima of one row are often the
same E4M3 code, so the effective perturbation may be much smaller than 3/4 of
the rows; and/or the shared expert's contribution to the residual is small
enough relative to the greedy margin to absorb it. Separating them needs a
logits-level diff, which the worker protocol does not expose (`decode_step`
returns only `{"token": …}`) and which I will not get by patching the trusted
harness.

Consequence, stated plainly: **§4.2's 1,374 zeros do not vouch for mechanism
(a) against the specific bug class §2.2 has to exclude.** Rule 16's letter is
met; its spirit is only partly met for (a). Mechanism (a)'s bit-exactness rests
on §2.2's source-level identity argument and on the byte-identical output of the
ON build, with the tripwire providing only coarse protection. §4.4 closes part
of that gap with a more sensitive check.

**Mechanism (b) is fully covered.** `plane_shift` is a demonstrated-power arm
(17 divergences, first at step 12) on exactly the halved-plane byte-editing
branch. `plane_byte`'s null is a magnitude result with the branch *proved live
independently of tokens*: `peak_ram_gb` is 21.93 for `05-pairwise-control` but
**22.845 for both `06-plane_byte` and `07-plane_shift`**, because both modes run
the same extra host-side copy of the plane's data region. A one-LSB E4M3 flip is
one mantissa step (≈12.5 %) on the scale of 16 gate weights of one row out of
512 — the smallest fault in the battery, deliberately so — and it is
subthreshold for a 128-step greedy check. Both controls on the faulted binary
are 0, which rules out "the injected build is broken everywhere".

Reproduce (must be the only model-holding process on the host):

```bash
OUT=/tmp/maple-shared-qmv-fault2 bash research/maple_shared_qmv_fault_injection.sh
python3 research/maple_pr301_fault_injection.py check   # must print clean x6 afterwards
git status --porcelain                                  # must show no Sources/ changes
```

Both post-run checks were run and passed: `clean … x1` for all six hook sites
and no `Sources/` entry in `git status`. The `trap … EXIT` also rebuilt a clean
worker, so no faulted binary survived into any timing arm.

### 4.4 A self-fed trajectory hash, and why it bought less than I expected

**The design.** §4.2's tripwire is teacher-forced: after each step it discards
the model's own argmax and feeds the golden token back, so it compares 128
*independent* single-step argmaxes and never lets a numeric difference
accumulate. A self-fed free run feeds the model its own argmax, so any single
disagreement changes every later step. Two builds sharing a hash of 256 self-fed
tokens is therefore a *measurement* of trajectory identity, where the tripwire's
zero is a conjunction of 128 weak comparisons. I added `--free-run` and
`--dump-tokens` to `research/decode_probe.py` and a `MODE=freerun` arm list to
the fault driver, with the two faults §4.3 already detects included as positive
controls so that an all-arms-match table could not be a silent detector failure.

**What actually happened, and it is worth stating before the table.** The public
long-copy gate's own continuation is the period-3 cycle `509, 902, 5991`
repeating — `expected_tokens` is that cycle for all 256 positions, and the
unperturbed free run reproduces it exactly (`distinct=3`, `cycle=3` over the
last 64 tokens). A self-fed run whose argmax always equals the golden token *is*
the teacher-forced run, step for step. So on this fixture the free-run mode
**does not compound anything** for an arm that never diverges: it is a 256-step
version of the same weak check, not a qualitatively stronger one. The
compounding argument in my own driver header was wrong for this fixture until I
measured the trajectory instead of assuming it; the probe now prints `distinct=`
and `cycle=` so the assumption is always checked.

**Result.** Two batteries, 256 self-fed steps per arm, one shared faulted build
per battery. Run 1 (`run_training` `799e3785-69a2-45d3-8545-15b819751402`,
exit 0, 277 s, `/tmp/maple-shared-qmv-freerun`) covered five arms; run 2
(`2bc2ac36-df13-4a4e-9b57-abda08d5295e`, exit 0, 370 s,
`/tmp/maple-shared-qmv-freerun2`) added the two faults §4.3 detects.

| arm | guards | injected fault | rc | 256-token hash | equals `off`? |
| --- | --- | --- | --- | --- | --- |
| `off` | none | — | 0 | `aed94d1679d31318` | reference |
| `on` | prefetch | — | 0 | `aed94d1679d31318` | yes |
| `pairwise` | prefetch + pairwise | — | 0 | `aed94d1679d31318` | yes |
| `on-fault-prefetch_stale` | prefetch | `prefetch_stale` | 0 | `aed94d1679d31318` | yes — **null** |
| `on-fault-prefetch_zero` | prefetch | `prefetch_zero` | 0 | `b1f82d576695e859` | **no — detected** |
| `pairwise-fault-plane_byte` | prefetch + pairwise | `plane_byte` | 0 | `aed94d1679d31318` | yes — **null** |
| `pairwise-fault-plane_shift` | prefetch + pairwise | `plane_shift` | 0 | `7e9b0d71c132ea48` | **no — detected** |

Both guard arms are bit-identical to `off` over 256 self-fed steps, and the two
positive controls move the hash, so the table is not a silent detector failure.
The divergence structure is informative: `prefetch_zero` leaves the cycle at
step 2 (`509, 902, 947, 290, 86, …`) and `plane_shift` survives eleven steps
before breaking at step 12 (`… 509, 902, 5991, 81, 902, 5991, 81, …`), after
which it reports `distinct=5, cycle=0` — once an argmax moves, the trajectory
really does leave the attractor and never re-enters a short cycle. That is the
compounding property I wanted; it just cannot be exercised by an arm that never
diverges in the first place.

Re-deriving the hashes from the archived `.tokens` files gives a free
cross-check: the first step at which each fault arm departs from `off` is **2**
for `prefetch_zero` and **12** for `plane_shift`, which are exactly the
`first=(2, 5991, 947)` and `first=(12, 509, 81)` steps the independent
teacher-forced tripwire reported in §4.3. Two differently-fed detectors agreeing
on the first divergent step is good evidence that both are reading the same
underlying numeric fault rather than picking up run-to-run noise.

**Trying to escape the attractor, and what that revealed instead.** If the
period-3 cycle is what blunts the free run, the obvious fix is to start outside
it, so I added `--free-run-bootstrap <token>` (feed a chosen token at step 0
instead of `expected[0]`, identically in every arm) and reran the full battery
with `BOOTSTRAP=7020`, the prompt's first token (`run_training`
`f9bee8e7-a374-4cf6-b4ec-da229941a481`, exit 0, 371 s,
`/tmp/maple-shared-qmv-freerun3`, 7/7 arms `rc=0`).

| arm | injected fault | 256-token hash | equals `off`? | first differing step | peak RAM (GB) |
| --- | --- | --- | --- | --- | --- |
| `off` | — | `9e80bb16b4477d8f` | reference | — | 21.925 |
| `on` | — | `9e80bb16b4477d8f` | yes | — | 21.924 |
| `pairwise` | — | `9e80bb16b4477d8f` | yes | — | 21.931 |
| `on-fault-prefetch_stale` | `prefetch_stale` | `9e80bb16b4477d8f` | yes — **null** | — | 21.924 |
| `on-fault-prefetch_zero` | `prefetch_zero` | `77281fa45f474d2e` | **no — detected** | 0 | 21.924 |
| `pairwise-fault-plane_byte` | `plane_byte` | `9e80bb16b4477d8f` | yes — **null** | — | **22.845** |
| `pairwise-fault-plane_shift` | `plane_shift` | `a5bf62a1db92f6d0` | **no — detected** | 0 | **22.847** |

The bootstrap **did not** open the trajectory: the guard arms produced
`509, 902, 7020, 509, 902, 7020, …` — `distinct=3, cycle=3` again, but a
*different* 3-cycle. That is a fact about the fixture, not about the guards. The
public long-copy gate drives the model into "emit `509, 902`, then repeat the
token you were last given", so **every** self-fed trajectory on this gate is a
period-3 attractor whose third element is whatever you seeded. Free-run
compounding is therefore unreachable on this fixture by choice of seed token;
it would need a different prompt, which is outside this assignment's surface.

Two things are nevertheless bought. First, both positive controls now diverge at
**step 0** rather than at steps 2 and 12, so the detector demonstrably has power
on the very first forward pass under this input, not only after several steps of
accumulation. Second, `plane_byte` ran to `rc=0` here (it was the arm lost to my
mid-run edit in run 2) with the 22.845 GB peak-RAM signature that proves the
halved-plane byte-editing branch executed, so its null is confirmed by direct
measurement in a complete battery rather than inherited from run 1.

So §4.4's honest contribution is narrow. It upgrades the two guards from "128
independent single-step argmaxes match" to "the entire 256-step self-fed
trajectory is byte-identical under two different seeds", which is a stronger
*statement* but, on this fixture, rests on much the same evidence. It does
**not** un-bracket `prefetch_stale`: that fault survives 128 teacher-forced
steps and 2 × 256 self-fed steps of trajectories it never perturbs, while the
two controls that share its build and its input diverge immediately. The most
defensible reading is that `prefetch_stale`'s null is a **magnitude** result —
mis-indexing the E4M3 group scale on 3 of every 4 K-blocks genuinely fails to
move any argmax on this fixture — and not a dead hook. That is weaker than
"rule 16 satisfied for mechanism (a)", and I am not claiming more.

**One operational error worth recording.** In run 2 I edited
`research/decode_probe.py` while the battery was still executing it. Arm 6
started between two writes and died with `NameError: name '_cycle_len' is not
defined` (`rc=1`), which is why its hash above is taken from run 1; arms 1–5 ran
the pre-edit code and arm 7 the post-edit code, visible as the missing
`distinct=`/`cycle=` fields in the early logs. No scored source was involved and
the `trap … EXIT` still reverted every hook, but a supervised run owns the
scripts it reads: edit them before launch or after it terminates, never during.

```bash
OUT=/tmp/maple-shared-qmv-freerun2 MODE=freerun STEPS=256 \
  bash research/maple_shared_qmv_fault_injection.sh
cat /tmp/maple-shared-qmv-freerun2/summary.txt
```


---

## 5. Stage 3 — end-to-end matched timing (partial: n = 1 per arm)

**Design.** `research/maple_shared_qmv_local_iterate_abba.sh` runs
`./benchmark.sh --local-iterate` once per slot with the cool gate **enabled and
untouched**, copies each `score.local-iterate.json` to
`${OUT}/<idx>-rep<N>-<arm>.score.json`, and soaks between slots.

```bash
REPS=1 PRECOOL_SECONDS=210 ORDER="off on pairwise pairwise on off" \
  OUT=/tmp/maple-shared-qmv-stage3-r2 \
  bash research/maple_shared_qmv_local_iterate_abba.sh
python3 research/maple_shared_qmv_stage3_stats.py /tmp/maple-shared-qmv-stage3-r2
```

**What actually happened.** The driver completed slots 01–03 and then lost slots
04 and 05 to the trusted cool-down gate, which is its
`MAX_CONSECUTIVE_FAILURES=2` bail condition, so it exited 3 with the ABBA
half-finished (supervised launch `16347d55-bd91-45e7-b872-a5951dc1b51a`,
~2,900 s). An earlier attempt (`1e2efe4f-…`) died the same way.

```text
01-rep1-off      rc=0 seconds=242
02-rep1-on       rc=0 seconds=451
03-rep1-pairwise rc=0 seconds=293
04-rep1-pairwise rc=1 seconds=351   error="local GPU cool-down gate failed for prefill with status 1"
05-rep1-on       rc=1 seconds=492   error="local GPU cool-down gate failed for decode with status 1"
aborting: 2 consecutive failed runs
```

This is a host property, not a code fault. This Mac16,11 **idles at
39.9–40.1 C**, and `benchmark.sh`'s gate is a `readonly COOL_GATE_TEMP_C=40`
with `MAX_WAIT=900`; `tools/fan-control.sh` cannot help because there is no
`smc` CLI here. Once the machine has absorbed the heat of three consecutive
512+128 benchmark passes, a 900 s wait for <40 C is a coin flip. I did not lower
`PRECOOL_SECONDS` below 210 and did not touch the gate: a comparable-timing rule
is worth more than a completed table.

**Correctness.** All three completed slots report
`passed_correctness=true, checked_steps=130, error=""`. The two failed slots
never ran a timed phase; their score files carry zeroed timings and are excluded
from every arm mean by `arm_values()` in the stats script.

**Result — three single observations, both axes.**

| Slot | Arm | prefill s/tok | decode s/tok | tok/s (decode) | correct |
| --- | --- | --- | --- | --- | --- |
| 01 | `off` | 0.001125312 | 0.012781521 | 78.24 | yes |
| 02 | `on` (prefetch) | 0.001117158 | 0.012850674 | 77.82 | yes |
| 03 | `pairwise` | 0.001138764 | 0.012881249 | 77.63 | yes |
| 04 | `pairwise` | — | — | — | cool gate |
| 05 | `on` | — | — | — | cool gate |

| Contrast | prefill Δ | decode Δ |
| --- | --- | --- |
| `off` → `on` | −0.725 % | **+0.541 %** |
| `off` → `pairwise` | +1.195 % | +0.780 % |
| `on` → `pairwise` | +1.934 % | +0.238 % |

**Achieved precision, stated honestly.** n = 1 per arm. There is no within-arm
variance estimate, so **no SE and no confidence interval exist** for any of
these contrasts and the achieved MDE is undefined — strictly worse than the
±0.73 % this host reaches at 5 reps per arm. The stats script prints
`95% CI undefined: n=1 vs 1, replication insufficient - point estimate only`
rather than a fabricated interval.

**This is not a refutation of mechanism (a), and it cannot be one.** Three
independent reasons, in decreasing order of force:

1. **The predicted effect is smaller than the tool's resolution even at full
   reps.** §0.1: −14.2 µs/step is **0.111 %** of this table's own 12.78 ms
   decode step, and that 14.2 is itself an upper bound (standing rule 25). The
   ±0.73 % MDE is **≈6.6×** larger.
2. **At n = 1 the observation is consistent with pure noise.** Back-solving the
   established ±0.73 % MDE at n=5 (`MDE ≈ 2.8·sd·√(2/n)`) implies a per-run sd
   of ≈0.41 %, so a single `off`/`on` pair has sd ≈ 0.58 %. The observed
   +0.541 % is ≈0.9 sd from zero. A coin-flip-magnitude deviation is not
   evidence in either direction.

   *Provenance and assumptions for that back-solve, since it does real work
   here.* The ±0.73 % figure is **not** measured in this round: it is the
   advisor-supplied MDE for `--local-iterate` on this host class at 5 reps per
   arm, and I use it only as an order-of-magnitude yardstick. The constant 2.8 is
   the usual two-sided 80 %-power, α = 0.05 approximation (`z_{0.975} +
   z_{0.80} ≈ 1.96 + 0.84`); a stricter reading that treats ±0.73 % as a bare
   95 % half-width (constant 1.96) gives sd ≈ 0.59 % per run and 0.83 % per pair,
   which makes +0.541 % only **0.65 sd** — i.e. every plausible convention lands
   in "indistinguishable from noise", so the conclusion does not depend on the
   choice. The load-bearing assumption is **variance stationarity across
   sessions**: that the run-to-run sd behind the advisor's 5-rep MDE also
   describes this Stage 3 session, which ran a longer pre-cool (210 s) and then
   failed its cool gate twice. If this session was in fact noisier than the
   reference session — which the two cool-gate failures make more likely than
   less — the true per-pair sd is *larger*, +0.541 % is *fewer* sd from zero, and
   the "consistent with noise" reading only strengthens. I checked the direction
   of that sensitivity precisely because it could have cut the other way.
3. **The two axes disagree in sign** (`off`→`on` is −0.725 % on prefill and
   +0.541 % on decode) with no mechanism that predicts a prefill-only benefit —
   the shared gate/up QMV rows-1 kernel is a *decode* kernel and prefill takes
   the QMM path entirely. Two axes moving oppositely by comparable amounts is
   the signature of between-run drift, not of the guard.

The load-bearing evidence for mechanism (a) therefore remains §2.1's in-situ
per-dispatch ABBA (−0.363 µs/call, CI [−0.495, −0.232], invariant control null)
plus the bit-exactness chain in §2.2/§4.3, exactly as §0.1 sets out. Confirming
or refuting a 0.145 % end-to-end effect needs the ranked M5 with its paired
same-session baseline; it is not obtainable on this host at any rep count I can
afford.

**W&B.** Stage 3 timings, the Stage 1/2 kernel A/B, the 128-step tripwire, the
round-wide correctness aggregate, the fault-injection table and the free-run
trajectory table are logged to one run by
`research/maple_shared_qmv_wandb.py`:
<https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/ag6xhecn>
(run id `ag6xhecn`). §0 lists the three summary flags that are intentionally not
the clean value and why.

```
WANDB_DIR=/tmp/maple-wandb python3 research/maple_shared_qmv_wandb.py \
  /tmp/maple-shared-qmv-stage3-r2
```

Only the `-r2` directory is logged. `/tmp/maple-shared-qmv-stage3-r1` is an
earlier aborted attempt holding a single `01-rep1-off` score; mixing it in would
have put two `off` observations from different sessions into the same arm mean,
which is exactly the session confound §3.5 is about.

---

## 6. Byte budget

Checked against the recorded base with the trusted scripts, before any edit and
again at the end of the round.

```
# before (BASE_SHA, clean worktree)
assignment scope OK: 1 submitted path(s) against BASE_SHA=69178729b154cbb648ea0ce6152e92dbfdb17cc6
editable budget OK: current=2866420/3000000 bytes headroom=133580 growth=0/262144

# after
assignment scope OK: 1 submitted path(s) against BASE_SHA=69178729b154cbb648ea0ce6152e92dbfdb17cc6
editable budget OK: current=2873731/3000000 bytes headroom=126269 growth=7311/262144 files=140 (file count is diagnostic only; base=140)
```

| Limit | Value | Used | Headroom |
| --- | --- | --- | --- |
| Total submitted surface | 3,000,000 B | 2,873,731 B | 126,269 B |
| Growth per submission review | 262,144 B | **7,311 B** | 254,833 B |
| Assignment's own growth cap | 12,000 B | **7,311 B** | 4,689 B |
| Per file (`LagunaRuntimeModel.swift`) | 524,288 B | 475,647 B (base 468,336 B) | 48,641 B |

Only `Sources/MLXFastModel/LagunaRuntimeModel.swift` changed; the file count is
unchanged at 140. All research artifacts (`research/…`) are outside the
submitted surface.

---

## 7. Honest assessment and follow-ups

### 7.1 What this patch is, and what it is not

It is one bit-exact kernel improvement (mechanism (a)) with a clean per-call A/B,
a passing invariant control, and 39 dispatches per decode step of leverage, worth
**−14.2 µs/step** on this host — **−0.111 %** of the 12.78 ms `--local-iterate`
decode step, or −0.145 % of the 9.825 ms split-instrumented probe step. Both are
upper bounds (§0.1).
It is not a demonstrated end-to-end win: on matched denominators the effect is
**≈6.6× below** this host's end-to-end resolution even at full reps (§0.1),
exactly as the assignment predicted,
and the cool gate left §5 at n = 1 per arm — so §5 is three unreplicated point
estimates, not a verdict in either direction.

Mechanism (b) is a clean *negative*: halving the scale plane is lossless and
bit-exact, it is certified live, and it makes its own kernel 1.93 % slower. The
useful conclusion is that this kernel is not scale-fetch-bound, which also
predicts that widening the scale read further would not help.

### 7.2 Promotion requires one deliberate line change

Both mechanisms are strict opt-ins (`== "1"`), which is what the assignment
asked for so that a single binary could serve every ABBA arm. The ranked
workflow sets **no** `DARKBLOOM_*` variable, so as committed this patch is inert
in an official run. `DARKBLOOM_` *is* on the worker environment allowlist
(`sanitizedRuntimeWorkerEnvironment`,
`Sources/MLXFastTrustedHarness/LagunaRuntimeWorker.swift:1936-2025`), which is
why the local ABBA works at all.

Promoting mechanism (a) is exactly one comparison at
`Sources/MLXFastModel/LagunaRuntimeModel.swift:6810-6812`:

```swift
// research form (as committed): inert unless explicitly enabled
private let lagunaSharedSwiGLUQMVPrefetchEnabled =
    ProcessInfo.processInfo.environment["DARKBLOOM_SHARED_QMV_PREFETCH"] == "1"
    || lagunaSharedSwiGLUQMVPairwiseScalesEnabled

// promotion form: on by default, with a kill switch
private let lagunaSharedSwiGLUQMVPrefetchEnabled =
    ProcessInfo.processInfo.environment["DARKBLOOM_SHARED_QMV_PREFETCH"] != "0"
```

I did not make that flip myself: it changes what a ranked run executes, and the
whole point of the opt-in was that the measured evidence and the shipped default
are separable decisions for the advisor. Mechanism (b)'s flag should stay
opt-in — or be deleted — because it is a measured regression.

### 7.3 Follow-ups I did not implement

1. **The decode-neighbour effect is the biggest lead here, and it is not this
   experiment.** In Stage 2, removing 2.55 MB/step of scale traffic left the
   changed kernel slower but made every memory-heavy decode neighbour faster,
   for a −1.40 % whole-step delta that is ~10× larger than the traffic
   removed can explain (§3.5). That deserves its own assignment with the
   invariant control chosen so it *cannot* move: e.g. hold the kernel binary
   fixed and vary only allocation order/padding, to separate "decode is
   globally scale-traffic-sensitive" from "heap layout artifact". If the former
   is real, it is a much larger prize than either mechanism here.
2. **Apply the same lossless halving to the shared *down* plane**, and to the
   `routed_shared_nvfp4_down_residual…r1_v5` kernel, which Stage 0 measured at
   ~881–915 µs/step — 3× the shared gate/up kernel's whole budget.
   `lagunaHalvedGroup32ScalePlane` already exists and already declines when the
   halving would be lossy, so the risk is bounded; but Stage 2 says to expect a
   per-kernel regression, so it is only worth doing as part of follow-up 1.
3. **Prefetch the routed twin.** The prefetch idea is not specific to the shared
   expert; the routed QMV runs 39×/step at 38.5 µs/call, 5× the shared kernel's
   cost. If the same −4.8 % held there it would be 38.5 × 0.048 × 39 =
   **−72 µs/step**, i.e. −0.56 % of the 12.78 ms `--local-iterate` decode step
   against a ±0.73 % MDE. That is *not* comfortably inside local resolution: it
   is a knife-edge case even before standing rule 25 discounts the isolated →
   in-situ conversion, and a rule-25 halving (~−36 µs, −0.28 %) puts it clearly
   below. So the honest claim is that the routed twin is the only place on this
   host where a −4.8 % kernel win could plausibly *approach* end-to-end
   detectability — it would still want either more reps or a quieter host, or an
   M5. The blocked items in this assignment (rows/simdgroup,
   `uint4` widening, split-K) do not apply to the prefetch change.
4. **Re-measure mechanism (a) on the M5**, where `_nax` kernels are selected and
   the memory system differs. This host cannot rank it.

### 7.4 Facts worth carrying forward

- The live shared-QMV call site on the scored path is `fusedSharedDownInputs`
  (`LagunaRuntimeModel.swift:8490`), **not** `callAsFunction` (`:8638`). A
  change routed only through the latter is unmeasurable, which is a trap I hit
  in Stage 2 and had to fix in commit `a15af48`.
- `LagunaUpstreamEquivalence.swift` **cannot see any fused shared-expert
  kernel**, because it builds the model directly and never calls
  `LagunaRuntimeWeights.loadLibraryModel`, which is the only installer of the
  fused banks (§4.1). Any future shared-expert fusion work must get its
  correctness evidence from the scored worker path, and a byte-identical
  equivalence report is *expected* rather than reassuring.
