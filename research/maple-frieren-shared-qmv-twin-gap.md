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

---

## 0. Headline

| Mechanism | Flag (opt-in, default OFF) | Verdict |
| --- | --- | --- |
| (a) K-block prefetch in the shared gate/up QMV | `DARKBLOOM_SHARED_QMV_PREFETCH` | **Kernel-level win, bit-exact.** −0.363 µs/call, 95 % CI [−0.495, −0.232], −4.80 %, = **−14.2 µs/step** |
| (b) Pairwise (halved) gate/up scale plane | `DARKBLOOM_SHARED_QMV_PAIRWISE_SCALES` (implies (a)) | **Refuted at kernel level, bit-exact.** +0.140 µs/call, 95 % CI [+0.058, +0.222], +1.94 %, = **+5.5 µs/step**; the invariant control also moved, so the accompanying −1.40 % whole-step delta is *not* attributable to this mechanism |

Mechanism (a) is a clean, reproducible, bit-exact kernel win and is the part of
this patch worth banking. Mechanism (b) makes its own kernel measurably slower
and its ABBA violated the invariant-control precondition, so I do not claim it.

Both effects are far below this host's end-to-end resolution. −14.2 µs/step is
**0.166 % of GPU busy time and 0.145 % of decode wall time**, against a
±0.73 % local-iterate MDE. The end-to-end ABBA in §5 is reported as a point
estimate with a CI and is **not** treated as a refutation.

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
greedy-token divergences** against the public golden, and the recorded GPUPSO is
identical between arms.

### 2.3 Per-kernel A/B result

Driver: `research/maple_shared_qmv_prefetch_abba.sh`, ABBA order
(`off on on off`), `REPS=3 STEPS=33`, one worker process per arm, 12 processes,
1248 steady calls per arm. Digest:
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

`DARKBLOOM_GPU_PROFILE_SPLIT=1` puts one dispatch per command buffer; that is
what makes a 0.36 µs/call effect measurable at all. It also means these
per-call numbers are *not* end-to-end numbers, which §5 covers separately.

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
`lagunaSharedGateUpHalvedScaleBytes =
lagunaScalePatchHeaderBytes + 2 * 2048 * (32768 / 32) = 2 + 65,536 = 65,664` B,
i.e. the 2-byte allow-list header plus one kept byte per pair.

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
ORDER="on pairwise pairwise on"`, 12 worker processes, 1248 steady calls per
arm. Supervised launch `fc455230-07e8-485b-b5d0-f4e1370723b7`, exit 0, 491 s.
Digest: `research/shared-qmv-logs/stage2.pairwise-abba.log`.

`on` here is Stage 1's winning prefetch arm, so this A/B isolates only the
scale-plane density change.

| Kernel | `on` µs/call (sd) | `pairwise` µs/call (sd) | Δ | 95 % CI | Δ % |
| --- | --- | --- | --- | --- | --- |
| `laguna_shared_nvfp4_swiglu_qmv_rows1_bf16_v1` (changed) | 7.210 (0.078) | 7.350 (0.026) | **+0.140** | [+0.058, +0.222] | **+1.94 %** |
| `routed_shared_nvfp4_…_qmv_…` (invariant control) | 38.817 (0.250) | 38.368 (0.075) | **−0.449** | — | **−1.16 %** |

Two facts to read together:

1. **The mechanism failed on its own kernel.** Halving the scale plane made the
   kernel it changes *slower* by +1.94 % (df 6.1, perfect 6-v-6 separation).
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

I can offer two unseparated explanations for (2) and I did not run the
experiment that would separate them:

- *Real bandwidth relief.* The pairwise arm removes 39 × 65,408 B ≈ 2.55 MB of
  scale traffic per decode step, which could free cache/bandwidth for the
  neighbouring decode kernels. But 2.55 MB at this host's achieved decode
  bandwidth accounts for only ~6–7 µs/step, whereas the neighbours together
  gained ~59 µs/step. The magnitudes do not match.
- *Allocation/layout artifact.* The pairwise arm allocates one extra buffer per
  layer and builds a second pipeline-state object, which changes heap layout and
  page placement for everything else.

Verdict: mechanism (b) is **refuted** as a kernel-level optimisation, and its
whole-step delta is **not claimed**, because the stage does not satisfy its own
invariant-control precondition. The honest residue is a *new* observation worth
its own experiment (§7): on this host, reducing decode-phase scale traffic
appears to speed up unrelated decode kernels far more than it speeds up the
kernel whose traffic was reduced.

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

TBD-TRIPWIRE

---

## 5. Stage 3 — end-to-end matched timing

TBD-STAGE3

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
**−14.2 µs/step ≈ −0.145 % of decode wall** on this host. It is not a
demonstrated end-to-end win: the effect is 5× below this host's end-to-end
resolution (§5), exactly as the assignment predicted, so §5 is a point estimate
and not a verdict.

Mechanism (b) is a clean *negative*: halving the scale plane is lossless and
bit-exact, it is certified live, and it makes its own kernel 1.94 % slower. The
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
   cost. If the same −4.8 % held there it would be −75 µs/step, which is inside
   local resolution. The blocked items in this assignment (rows/simdgroup,
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
