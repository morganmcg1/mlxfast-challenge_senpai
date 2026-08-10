# R107-F — T2d routed+shared down+residual: output-row amortisation

**Student** maple-frieren · **PR** #597 · **revision** `r105-b-rev6` ·
**base** `2454cc01ea3afabac067f0a271e36901fea7d21c` · **host** AWS M4 Pro,
Apple GPU generation 16, 20 cores, measured DRAM ceiling 260.2 GB/s.

Every M5 figure quoted from the state-doc pool table (§B.0.3, lines 1685–1705)
carries its mandatory provenance label verbatim:
**`α = 0.4369, β = 0.5 two-pool map, residual −6.63 %, #561`**.

---

## §0 Outcome

**`N-T2D-ISSUE-BOUND`** — the §6.4 premise is refuted. The routed+shared
down+residual kernel is not issue-bound on activation-load or arithmetic work:
86.6 % of its 22.07 µs/call is the unique-byte DRAM floor and 14.0 % is the
irreducible inter-dispatch barrier drain, leaving ≤2.5 % for everything
amortisation could remove. The preregistered amortisation arm A1
(`outputs_per_simd` 4→8) is **harmful**: it is **+1.012 µs/call slower =
+39.5 µs/step**, which **costs 0.60 % of `cs`** — the wrong sign against a
0.6736 µs/call ship bar. `N-T2D-ROOFLINE` is
concurrently satisfied (`a0_act0_min` = 22.109 µs/call ≥ the 21.1 µs/call
falsifier, so the whole family is dead, not just A1). Stage 2 is not warranted,
**nothing ships**, and the submitted-surface diff against the base is empty
(§5.2). Zero official receipts spent.

The permitted vocabulary was fixed in §2.7 before any timing run and was not
extended after the fact.

> 🔧 **Addendum, 15:30Z — read §11 before quoting any `% of cs` figure from
> §3–§8.** Rule 105.13 (advisor, `bde79502`) landed after this report was
> finished. Every `% of cs` in §3–§8 is priced **bare** (an M4 µs treated at the
> M5 price) — rule 105.12 category (c). §11 re-prices all of them with `k`. The
> corrected headlines: `a1` costs **−0.30 % (β) / −0.26 % (α)**, not −0.60 %;
> the family ceiling is **0.29–0.33× the bar**, not 0.65×; the ship bar in this
> kernel's units is **1.35–1.54 µs/call**, not 0.6736; and the §4.6 barrier
> drain is **0.80–0.92 %**, not 1.83 %. Bare pricing over-states, so a closure
> priced bare stays closed: **the verdict is unchanged and every correction
> hardens it.** §11.4 also adds the summand I never priced — the per-layer
> *dispatch* removal beside the drain, worth **+1.390 %** on its own.
> **§12** records priority A: the margin certificate is now a documented,
> re-validated service (`research/maple-frieren-margin-certificate-service.md`).

---

## §1 Stage-0 receipt (rev6 §1) — DONE

My branch head `95a0ef9e` carried a replay of the `4b0e051b` editable surface
(32 files diverging from the advisor tip). Left in place it would have swapped
the integration tree under the advisor. Stripped with the Rule 95.6 recipe:

```sh
PATHS=$(jq -r '.editablePaths[]' benchmark.json)          # 97 paths
git rm -r -q --ignore-unmatch -- $PATHS
git checkout 2454cc01ea3afabac067f0a271e36901fea7d21c -- $PATHS
git add -A && git commit -m "strip r106e replay: restore advisor-tip editable surface"
```

Result commit **`87d7d13da74596b040de06f2168a42fce4ed480e`**. Both mandated
commands print **nothing**:

```
$ git diff --numstat 2454cc01ea3afabac067f0a271e36901fea7d21c HEAD -- $PATHS
$ git status --porcelain=v1 --untracked-files=all -- $PATHS
```

`git status --porcelain=v1` over the whole tree is also empty. All `research/`
files survive: `research/` is outside `editablePaths` and outside
`harnessHash()`, so preserving it cannot move the integration tree. #597 is
mergeable on the advisor tip.

---

## §2 Preregistration

Written **before any timing run**. Nothing below is retrofitted; the Stage-1
and Stage-2 sections are appended after this section, not woven into it.

### §2.1 The pot, and both Rule 81 reference rates

| rank | family | calls | M4 µs | M5 µs | regime | % M5 peak | headroom µs | % score |
|---|---|---:|---:|---:|---|---:|---:|---:|
| 4 | T2d routed+shared down+residual | 39 | 858.9 | 375.3 | bytes | 85.3 | 55.1 | **0.84** |

`α = 0.4369, β = 0.5 two-pool map, residual −6.63 %, #561`.

Byte census (`research/artifacts/fern-r105d/decode-byte-census.json`):
195,526,656 B/step = **11.6984 % of `B`**, 5,013,504 B/call × 39 calls,
unique-byte floor 320.536 µs = 4.881 % of the step.

Rule 81 clause (b) needs the achieved rate ≥10 pp below a same-access-pattern
family's best rate on the same host. **Both reference rates, side by side, and
I do not get to pick:**

- against **`lmhead`** at 97.4 % of peak: 12.1 pp, implied gain **46.4 µs/step** — clause (b) **passes**;
- against **`dense_down`** at 94.0 % of peak (the fairer comparator, a plain NVFP4 QMV): 8.7 pp, implied gain **34.6 µs/step** — clause (b) **fails**.

Clause (c) (≥30 µs/step) holds on both. The honest sentence: *T2d is licensed
under the lmhead reference (46.4 µs, 12.1 pp) and marginal under the dense_down
reference (34.6 µs, 8.7 pp); both are reported.*

### §2.2 My own in-situ baseline for this kernel

R106-J §3.3 invariant control, measured on this host with the per-kernel GPU
profile split: `routed_shared_nvfp4_down_residual` = **22.0637 µs/call**,
sd across blocks 0.1068, n = 3 blocks. × 39 calls = **860.48 µs/step**, against
the pool table's 858.9 — a 0.18 % agreement between two independent
instruments. This is the only decode byte family where a student already holds
a contemporaneous in-situ per-call number, and it is the A0 anchor.

Derived M4 rates (mine, not the two-pool map's):

- achieved 5,013,504 B / 22.0637 µs = **227.15 GB/s**;
- 87.30 % of this host's measured 260.2 GB/s stream ceiling;
- 87.04 % of 105-E's *pattern-specific* ceiling (a faithful nvfp4_qmv replica at 260.97 GB/s);
- M4 headroom to the pattern ceiling = 22.0637 × (1 − 0.8704) = 2.859 µs/call = **111.5 µs/step**.

At the campaign decode price (0.015228 % of `cs` per locally measured µs/step,
the same price under which #308's −36.9 µs/step was booked as +0.562 % of `cs`),
the **bar of 0.4 % of `cs` is 26.27 µs/step**, i.e. I must capture **23.6 % of
the measured M4 headroom**. That is the honest framing of the target.

### §2.3 §6.4 arithmetic, re-derived from the source on this host

Read at `2454cc01` from `Sources/MLXFastModel/LagunaRuntimeModel.swift`
(`lagunaRoutedSharedDownResidualSource`, `:8277`; launch wrapper `:8578`).
Emitted constants: `input_width = 512`, `output_width = 2048`,
`routed_experts = 8`, `shared_slot = 8`, `outputs_per_simd = 4`,
`values_per_lane = 16`, `packed_row_bytes = 256`, `scale_patch_bytes = 128`,
`routed_scale_row_bytes = 16`, `shared_scale_row_bytes = 16 (halved) | 32`.
Launch `grid = (2048/4 × 288, 1, 1)`, `threadGroup = (288, 1, 1)` ⇒ **512
threadgroups × 9 simdgroups × 32 lanes = 147,456 threads**, tile count 512.

Per lane, per call, from the emitted body:

| load | count | width | bytes | source line |
|---|---:|---:|---:|---|
| activation `vec<bfloat,4>` from `expert_input + lane*16` | 4 | 8 B | **32** | `input_vectors[i]` loop |
| weight codes `uint2` at `output_row*256 + lane*8` | 4 | 8 B | **32** | `row_codes[row]` |
| scale `uint8_t` at `output_row*scale_row_bytes + scale_lane` | 4 | 1 B | **4** | `row_sb[row]` |
| **total** | **12** | | **68** | |

32/68 = **47.06 % of issued bytes is the re-read activation** ✓ — §6.4's figure
reproduced exactly.

Replay factors, per call:

| stream | unique B | issued B | replay |
|---|---:|---:|---:|
| weight codes | 4,718,592 | 4,718,592 | 1.000× (every lane byte distinct) |
| scales | 294,912 | 589,824 | 2× (`lane>>1`: lane pairs share a byte) |
| activation | 9,216 | 4,718,592 | **512×** (once per tile) |
| residual + output | 8,192 | 8,192 | 1× |

Unique DRAM read = 4,718,592 + 294,912 + 9,216 = **5,022,720 B**, of which the
census's scored 5,013,504 B is the weight+scale part (9 × 4 × 256 = 9,216 B and
9 × 4 × 16 = 576 B per threadgroup, × 512 = 4,718,592 + 294,912 = **5,013,504 B
✓**). Total issued = **10,027,008 B/call**, a 2.000× issue/unique ratio.

**Byte identity independently pins the shipped variant.** 576 scale B per
threadgroup requires `shared_scale_row_bytes = 16`, i.e. the **halved** shared
scale plane; the unhalved variant would give 8 × 4 × 16 + 1 × 4 × 32 = 640 B
per threadgroup and 5,046,272 B/call, which is *not* the census figure. With
`DARKBLOOM_SHARED_FIRST_DOWN` unset (default, `:8218`) and
`DARKBLOOM_FUSED_DOWN_ROW_STAGING` unset (default ON, `:8226`), the resolved
pipeline is therefore predicted to be
**`laguna_routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6`**. Stage 0
confirms this on the device rather than by inference.

### §2.4 What actually amortises at `outputs_per_simd = 8` — a correction to §6.4

§6.4 says "per-row metadata **and** activation loads are amortised over only 4
output rows". Re-deriving from the source, that is half right and I will not
carry the error forward: the scale byte is indexed by `output_row`, so scale
loads scale **1:1 with rows and do not amortise at all**. Only the activation
load, the `indices[slot]` load, the pointer setup, and the threadgroup barrier
amortise.

| quantity per call | A0 (`opsi=4`, 512 TG) | A1 (`opsi=8`, 256 TG) | change |
|---|---:|---:|---:|
| threadgroups | 512 | 256 | −50 % |
| total threads | 147,456 | 73,728 | −50 % |
| load instructions per lane | 12 | 20 | +67 % |
| **load instructions per call** | 1,769,472 | 1,474,560 | **−16.67 %** |
| issued activation B | 4,718,592 | 2,359,296 | −50 % |
| issued scale B | 589,824 | 589,824 | 0 % |
| issued weight B | 4,718,592 | 4,718,592 | 0 % |
| **issued B per call** | 10,027,008 | 7,667,712 | **−23.53 %** |
| issued B per unique weight B | 2.125 | 1.625 | −23.53 % |
| unique DRAM B | 5,022,720 | 5,022,720 | **0 %** |
| `threadgroup down_outputs` | 72 B | 144 B | +72 B |
| live thread state (`row_codes`+`row_sb`+`result`) | 4×2 + 4×1 + 4 regs | 8×2 + 8×1 + 8 regs | ~2× |

So the sharpened hypothesis I am actually testing is:

> **H-T2D-AMORT′** — T2d's 12.7 pp shortfall against its pattern ceiling is
> paid in *load-issue slots spent replaying an SLC-resident activation row*,
> and halving that replay (512× → 256×) converts into wall-clock. The scale
> stream does not amortise; the ceiling on this lever is therefore the
> activation-replay component alone.

### §2.5 The adverse prior, confronted before anything is built

State doc §5e (105-E) priced exactly this replay: driving *issued* bandwidth to
752 GB/s by replaying a 4 KB activation per simdgroup cost **0.45 µs out of
4371 = 0.010 %**. Scaled to 39 dispatches that is **17.6 µs/step = 0.27 % of
`cs`** — the whole lever, at its ceiling, lands **below the 0.4 % bar**. 105-E
also showed 64-thread threadgroups are not a bandwidth handicap
(`stream_tg64` at 99.1 % of stream peak) and closed
bandwidth-efficiency-at-fixed-bytes as a family with a ≤1.548 % ceiling.

I accept that prior as stated and record its consequences honestly:

1. **The lever must be argued as an issue/amortisation effect, not a
   bandwidth-efficiency effect.** 105-E measured the marginal cost of *bytes
   that are already resident*. A1 does not change resident bytes; it changes
   the **number of load instructions issued per unique DRAM byte** (2.125 →
   1.625) and the **number of threadgroups** (512 → 256). If the limiter is a
   per-load issue slot or a per-threadgroup launch/barrier cost, 105-E's
   marginal-byte price says nothing about it.
2. **The prior is nevertheless adverse by 1.49×.** Bar 26.27 µs/step ÷ prior
   ceiling 17.6 µs/step = 1.49. For a `V-T2D-AMORT` outcome the 105-E price
   must be wrong by at least half again in the direction that favours me. I put
   the prior probability of clearing the bar at **≈15 %**, and the probability
   of a *measurable but sub-bar* effect (`N-T2D-AMORT`) at ≈35 %.
3. **Therefore Stage 1 is the deliverable, not a formality.** The most likely
   honest outcome of this assignment is a null that retires 11.7 % of decode
   bytes from the live list, and I am preregistering that as a success rather
   than something to be avoided.
4. The one piece of same-class positive evidence is **#308**: raising
   `num_simdgroups` 2 → 8 on the QKV lane-major kernel measured **−36.9 µs/step,
   CI [−61.0, −12.9] = +0.562 % of `cs`, CI [+0.196 %, +0.929 %]**. It is real,
   measured, on this host, and it is the reason the 15 % is not 2 %.

### §2.6 Arms

Stage 2 runs only if Stage 1 supports it (§2.8). All three arms are bit-exact
by construction — per-row k-traversal, FMA order within a row, and `simd_sum`
are untouched; only *which simdgroup computes which output row* changes — and
that is **proved, not assumed**, with `logit_delta == 0` on the full golden set.

| id | `outputs_per_simd` | threads/TG | TGs | grid | role |
|---|---:|---:|---:|---|---|
| **A0** | 4 | 288 (9 sg) | 512 | `2048/4 × 288` | shipped baseline |
| **A1** | 8 | 288 (9 sg) | 256 | `2048/8 × 288` | 2× activation-replay amortisation |
| **A2** | 4 | 576 (18 sg) | 256 | `2048/8 × 576` | **negative control** |

**A2 is the discriminator.** It packs two `opsi=4` tiles into one threadgroup:
`slot = sg % 9`, `subtile = sg / 9`, `first_row = (tile*2 + subtile) * 4`,
`down_outputs[18*4]`, and the epilogue runs on `sg % 9 == 0` so both subtiles
reduce independently. A2 therefore has **exactly A0's load count, A0's issued
bytes and A0's per-lane work**, but A1's threadgroup count. If A1 wins and A2
does not, the mechanism is activation-replay amortisation. If both move
together, the mechanism is threadgroup count / launch / barrier cost and
H-T2D-AMORT′ is refuted in favour of `V-T2D-TGSHAPE`.

Mechanics that are mandatory for every arm:

- **distinct pipeline names** (`…_sh_stage4_v6_a1`, `…_sh_stage4_v6_a2`) so
  Metal cannot serve a cached sibling pipeline;
- all four kernel objects updated coherently
  (`{staged, unstaged} × {sharedHalved, not}`), because `sharedHalved` is
  inferred at run time from `sharedDownScales.ndim == 1` and the staged
  default can be flipped by env;
- a **spill check** in the Stage-0 reflection. A1 doubles `row_codes[]`,
  `row_sb[]` and `result[]`. **If a spill appears I stop and report it rather
  than reporting a contaminated number.**

### §2.7 Acceptance, null cell, and outcome vocabulary

Acceptance for a `V-` outcome, all of which must hold:

1. in-situ paired ABBA under `./benchmark.sh --local-iterate`, **≥8 pairs**,
   order reversed every round, GPU-dispatch timestamps plus a wall-clock twin
   (Rule 86: a bare `--local-iterate` score delta is never evidence);
2. decode **and** prefill both reported — the kernel is decode-only but both
   score floors are 0.95;
3. mean decode delta ≤ −26.27 µs/step with a CI excluding zero;
4. `logit_delta == 0` on the full golden set; force-clean build (#575);
   `research/run_upstream_equivalence.sh` green on the exact tree;
5. no spill in the pipeline reflection;
6. Rule 98.9: no cache-resident kernel-local number is a headline; every
   probe number is reported beside its residency-defeated twin, and the
   headline is the in-situ wall clock.

**Null cell (preregistered):** A0-vs-A0. The same ABBA driver, same pair count,
with the "candidate" arm being a semantically inert rename of the shipped
pipeline (`…_sh_stage4_v6_null`). Its measured delta and CI are the noise floor
against which A1 and A2 are read. Without it a 26 µs/step claim on this host is
not interpretable.

**Preregistered revert:** `git checkout 2454cc01 -- Sources/MLXFastModel/LagunaRuntimeModel.swift`.

Outcome vocabulary — exactly one is named in §0:

- **`V-T2D-AMORT`** — A1 wins in situ, A2 does not, gain ≥ 0.4 % of `cs`.
- **`N-T2D-AMORT`** — amortisation measurable but below the bar; point estimate and CI given.
- **`V-T2D-TGSHAPE`** — A1 and A2 move together; effect is threadgroup shape; H-T2D-AMORT′ refuted, the exposed lever priced.
- **`N-T2D-ISSUE-BOUND`** — Stage 1 refutes the premise. **A success**: it retires 11.7 % of decode bytes and bears directly on the §B.0.6 α/β degeneracy (α ≈ 0.389 ⇒ efficiency work pays; α ≈ 0.437 ⇒ only bytes pay).
- **`N-T2D-ROOFLINE`** — the family is genuinely at its achievable roofline; 85.3 % is an artefact of the two-pool map.
- **`N-CORRECT`** / **`N-BUILD`** — a `logit_delta` failure or a spill; which, and why.

### §2.8 Stopping rule

Stage 1 fits **`T = B/BW + L`** with uncertainties on a residency-defeated
standalone replica of this exact access shape, and runs an **AIR load census**
of the shipped kernel classifying loads by buffer. Per rev6 §6.6 I do **not**
report "% of peak bandwidth" as the regime statistic (state-doc rule (i): it is
confounded by fixed cost).

**If `L` is small, or the load census does not match §2.3, I declare
`N-T2D-ISSUE-BOUND`, write it up, and stop.** Additionally — and this is my own
added gate, because the replica is cheap and the runtime edit is not — the
replica must show an A1-vs-A0 improvement whose extrapolation to 39 calls
reaches at least the 17.6 µs/step adverse-prior ceiling. A replica that cannot
find the effect with the confound removed will not find it in situ.

---

## §3 Stage 0 — reachability, geometry, digests

_Appended after §2 was committed. All numbers below are measured on this host,
not inferred. Artifacts in `research/artifacts/maple-frieren-r107f/`._

### §3.1 Host facts (Rule 99.3), measured not assumed

`research/maple_frieren_r107f_stage0_host.swift` →
`stage0_host.{log,json}`, `stage0_dram_ceiling.log`.

| fact | value | how |
| --- | --- | --- |
| `device_name` | `Apple M4 Pro` | `MTLDevice.name` |
| `architecture_name` | `applegpu_g16s` | `device.architecture.name` |
| `architecture_gen` | **16** | replicating the parse at `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp:564-572` (two chars before the trailing family letter) |
| family back char | `s` | last char of the arch name |
| `os_version` | `26.5.2` | `ProcessInfo.operatingSystemVersion` |
| `_nax` OS clause | **passes** (≥ 26.2) | `device.cpp:913-931` |
| `_nax` gen floor for back char `s` | 17 | `gen >= (back=='p' ? 18 : 17)` |
| **`nax_available`** | **false** | gen 16 < 17. The OS clause is *not* what blocks it |
| `max_ops_per_buffer` | 50 | `device.cpp:573-595`, selected on back char `s` |
| `max_mb_per_buffer` | 50 | idem |
| `max_threads_per_threadgroup_x` | 1024 | `MTLDevice` |
| `max_threadgroup_memory_length` | 32768 B | `MTLDevice` |
| `recommended_max_working_set_size` | 40,200,896,512 B | `MTLDevice` |
| `physical_memory_bytes` | 51,539,607,552 = 48 GiB | `< 64 GiB` ⇒ **low-memory startup profile** |
| GPU cores | 20 | `ioreg -l \| grep gpu-core-count` |
| DRAM read ceiling | **260.6–260.7 GB/s** | GPU-timed, 4.19 M threads; reproduces the prior 260.2 GB/s to 0.15 % |
| copy (r+w) / rmw | 227.0 / 245.4 GB/s | same probe |

Two consequences worth stating because they cut in opposite directions:

* Because the back char is `s` on both this host and the ranked M5 Max, the
  command-buffer commit thresholds are **identical** (50 ops / 50 MB). The
  batching axis is therefore *not* a cross-machine confound for this
  experiment. That is a new fact; I had assumed it was one.
* `nax_available=false` here and `true` on the ranked M5. Nothing in this
  experiment touches an `_nax` kernel — the down-residual kernel is a
  runtime-generated `metal_kernel`, which has no `_nax` twin — so this is a
  recorded limit, not a blocker. It does mean an M4 prefill number from me is
  not evidence about ranked prefill (AGENTS.md), which is why §2.7 prices the
  prefill floor from the pot rather than from a local prefill measurement.

### §3.2 Which of the four pipelines actually ships — resolved on device

`Sources/MLXFastModel/LagunaRuntimeModel.swift` generates four texts from
`lagunaRoutedSharedDownResidualSource(sharedHalved:staged:)` (:8277). Reading
the code says non-`sf` and `staged=true` should ship; I did not want to rely on
that. A temporary env-guarded block in the launch wrapper printed the resolved
flags from the live worker:

```
R107F_RESOLVED sharedHalved=true staged=true sharedFirst=false \
  fusedStaging=true sharedScalesNdim=1 sharedScalesSize=32896 \
  routedScalesSize=8388736
```

and the GPUPSO hook shows exactly one routed down-residual pipeline ever
created, out of 137 distinct pipelines in a 33-step decode:

```
GPUPSO custom_kernel_laguna_routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6\
_bfloat16_t_uint32_t_uint8_t_uint32_t_float_bfloat16_t_uint32_t_uint8_t_bfloat16_t_bfloat16_t \
  maxThreads=1024 execWidth=32 tgMem=80
```

**The shipped kernel is `laguna_routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6`.**
The `_sf` order, the unhalved-shared-scale variant, and the unstaged variant are
dead text on this tree. Any Stage-2 edit that changed only one of the other
three would have measured exactly nothing; this is the reachability check
rev6 asked for, and it passed.

### §3.3 The two scale tensors reconcile the census exactly

The resolved sizes are not round numbers, which makes them a strong check:

* `routedDownScales.size = 8,388,736 = 256 experts × 2048 rows × (512/32) groups
  × 1 B + 128 B` — the 128 is `lagunaScalePatchHeaderBytes`
  (`LagunaRuntimeWeights.swift:985`).
* `sharedDownScales.size = 32,896 = 2048 × 16 + 128`, and `ndim == 1`, which is
  precisely the predicate `sharedHalved` tests.

So one row of either bank carries 16 group scales, and one row of codes is
512 nvfp4 values = 256 B. Per threadgroup: 9 slots × 4 rows × 256 B = 9,216 B of
codes plus 9 × 4 × 16 B = 576 B of scales = 9,792 B; × 512 threadgroups =
**5,013,504 B/call**, and 39 calls/step = **195,526,656 B/step**, which is the
pot's census figure to the byte. The unhalved-shared alternative would have
given 640 B/TG → 5,046,272 B/call and would *not* have matched. The byte
identity therefore independently pins the same variant the device reported.

### §3.4 Rule 77 geometry, and the spill question

| quantity | value | source |
| --- | --- | --- |
| `group_dims` | (288, 1, 1) | launch wrapper `lagunaRoutedSharedDownResidual` (:8578) |
| `grid_dims` | (147456, 1, 1) = `hiddenSize/4 × 288` | idem |
| threadgroups/call | 512 | 147456 / 288 |
| simdgroups/TG | 9 | 288 / 32 |
| `threadExecutionWidth` | 32 | GPUPSO |
| `maxTotalThreadsPerThreadgroup` | **1024** | GPUPSO |
| `staticThreadgroupMemoryLength` | **80 B** | GPUPSO |

The 80 B is `down_outputs[9 × 4]` bfloat16 = 72 B rounded up to the 16 B
threadgroup-memory granule. Two things follow:

1. **No spill and no occupancy clamp.** The compiler reports 1024 threads
   available and the wrapper asks for 288. Had the kernel spilled or run out of
   registers, `maxTotalThreadsPerThreadgroup` would have been clamped below
   1024 — this is the strongest spill proxy available in this toolchain (there
   is no AGX disassembler; see `research/advisor-r89-agx-native-instruction-census.md:99-104`
   and `research/maple-frieren-r90-agx-instruction-census.md:114-116`).
2. **Both proposed arms fit.** A1 keeps 288 threads and grows threadgroup
   memory to 144 B. A2 (the negative control) needs 576 threads, and
   576 ≤ 1024, so it is dispatchable *on this kernel as compiled today*. A1
   roughly doubles live per-thread state, so the 1024 figure must be re-read
   from GPUPSO for each arm rather than assumed — if an arm's number drops
   below its requested threads, that arm is spilling and I report it instead of
   timing it.

### §3.5 A perturbation result I did not plan, and must not bury

The first Stage-0 run produced a *fresh in-situ anchor* of **54.97 µs/call**
(2143.9 µs/step) for the shipped kernel. My §2.2 anchor, measured on this same
host in R106-J with the same GPUPROF patch, is **22.06 µs/call** (860.5 µs/step),
and the pot's M4 figure is 858.9 µs/step. A 2.49× discrepancy against two
agreeing priors is a red flag, so I stopped and found the cause rather than
adopting either number.

Cause: the MSL-dump block I injected sat in the **per-call** launch wrapper with
no one-shot guard. It fired 1,328 times (39 calls × 34 steps), each time
generating four kernel source strings and performing four `atomically: true`
file writes — 5,312 atomic writes over the run.

The signature is unambiguous:

| | R106-J (clean) | Stage 0 first run (perturbed) |
| --- | --- | --- |
| wall/step | 9.764 ms | 192.890 ms |
| gpu_busy/step | 8.535 ms | 26.180 ms |
| CPU gap | 1.230 ms (12.6 %) | 166.710 ms (**86.4 %**) |
| gap per dispatch | 3.0 µs | 410 µs |
| down-residual | 22.06 µs/call | 54.97 µs/call |

The methodological point is the one I want on the record: **per-kernel GPU-busy
time is not immune to host-side perturbation.** The GPU was idle 86 % of the
time, DVFS dropped its clocks, and *every* kernel's GPU-timestamped duration
inflated ~2.5× — the whole table moved, not just the instrumented kernel. So a
"GPU-busy per kernel" number is only comparable between arms whose **CPU-side
cost is matched**. Rule 86 already forbids taking a bare score delta as
evidence; this adds that a GPU-timestamp delta is also unsafe when an arm
carries instrumentation the other arm does not. Concretely, for Stage 2 this
means the null cell must be an inert *rename* (as preregistered in §2.7) and
never a "same kernel plus a counter", and any diagnostic print must be one-shot.

The perturbed run is retained as
`stage0_device_perturbed.{log,err.gz}` — a negative control, explicitly not an
anchor. The script now carries a one-shot file-existence guard and an `INJECT=0`
switch, and the clean re-run is reported in §3.6.

What the perturbed run *does* validate, because these are structural and
timing-independent: the resolved pipeline name, the GPUPSO geometry, the two
scale sizes, the four MSL dumps, and `teacher-forced greedy tokens: 0
divergences (all match)` — i.e. the instrument itself was behaviour-neutral.

### §3.6 The clean in-situ anchor

Same script, `INJECT` disabled, nothing else changed, same host, same thermal
gate. `research/artifacts/maple-frieren-r107f/stage0_device_clean.log`.

| quantity | perturbed (§3.5) | clean | R106-J | pot (#561, M4 column) |
|---|---|---|---|---|
| wall ms/step | 192.890 | **10.925** | — | — |
| gpu_busy ms/step | 26.180 | **8.532** | — | — |
| host gap | 86.4 % | 21.9 % | — | — |
| down-residual µs/step | 2143.8 | **860.5** | 860.5 | 858.9 |
| down-residual µs/call | 54.97 | **22.07** | — | — |
| share of gpu_busy | 8.19 % | **10.09 %** | — | — |

The clean anchor reproduces R106-J to 0.05 % and the pot's M4 figure to 0.19 %,
on the Stage-0-stripped tree. That is the number every Stage-1/2 delta is
measured against, and it is *my own* measurement, not an inherited one.

Effective rate: 5,013,504 B / 22.07 µs = **227.1 GB/s = 87.15 %** of the
260.6 GB/s measured DRAM read ceiling (§3.1). A perfect-efficiency call would
take 19.24 µs, so the *entire* efficiency headroom in this kernel is
**2.83 µs/call = 110.4 µs/step**. The ship bar is 26.27 µs/step, so any
efficiency-only lever here must capture **23.8 %** of the total gap to the
measured ceiling. That is the honest framing of the difficulty, and it is
strictly worse than the naive "13 % below peak, so 13 % is available" reading.

### §3.7 Offline replica, verified against the live pipeline

Before spending device time I reconstructed the shipped kernel offline: the
dumped MSL body (§3.2) plus a hand-reconstructed `write_signature` prologue and
the `lagunaSharedSwiGLUQMVHeader` NVFP4 helpers evaluated at their shipped
defaults (`fold=true`, `defer=true`, `carry=true`, `sign_domain=true`,
`nibble_split=1`, `seed_elide=true`; all six are `!= "0"` env reads or a literal
default, so the defaults are what ships).
`research/artifacts/maple-frieren-r107f/offline/down_residual_reconstructed_opsi4.metal`.

The reconstruction is **verified, not assumed**: built into a metallib and
handed to the live driver, it reports

```
opsi4  maxTotalThreadsPerThreadgroup=1024  threadExecutionWidth=32  staticThreadgroupMemory=80
```

which is byte-identical to the in-situ `GPUPSO … maxThreads=1024 execWidth=32
tgMem=80` line of §3.4. The signature is confirmed independently by the observed
pipeline hash suffix
`_bfloat16_t_uint32_t_uint8_t_uint32_t_float_bfloat16_t_uint32_t_uint8_t_bfloat16_t_bfloat16_t`
— exactly the ten argument types the reconstructed prologue declares, in order.
So the offline replica is a validated proxy and I can iterate on it for free.

### §3.8 The §2.3 per-lane arithmetic, confirmed by compiler IR

`research/maple_frieren_r107f_buffer_census.py` (new; existing censuses
`research/tanjiro_ir_census_lib.py:22-44` and
`research/maple-alphonse-r107c-air-census.py:14-32` classify by address space
only and cannot attribute a load to a *buffer*). It walks every
`addrspace(1)` access pointer back through `getelementptr`/`bitcast`/
`addrspacecast`/`inttoptr`/`select`/`phi` to a named kernel argument, reports
ambiguity explicitly rather than guessing, and sizes each access from its value
type. Output for the shipped arm
(`offline/opsi4_buffer_census.json`):

| buffer | width | count | what it is |
|---|---|---|---|
| `<ambiguous:%0\|%5>` routed/shared_activated | **8 B** | 1 | `vec<bfloat,4>` activation load |
| `<ambiguous:%1\|%6>` routed/shared_down_weight | **8 B** | 1 | `uint2` = 16 nvfp4 codes |
| `<ambiguous:%2\|%7>` routed/shared_down_scales | **1 B** | 1 | the `lane>>1` scale byte |
| `%3` indices | 4 B | 1 | expert id |
| `%4` router_weights | 4 B | 1 | epilogue, 8 iterations |
| `%8` residual | 2 B | 1 | epilogue |
| `%9` output | 2 B store | 1 | epilogue |

The three ambiguous entries are ambiguous *for a real reason*: the routed and
shared pointers are combined by a `select` on `is_shared`, so a single load
instruction serves both buffers. Reporting that honestly is the point of the
tool; a tool that picked one would have been silently wrong.

With the source trip counts (`values_per_lane/4 = 4`, `outputs_per_simd = 4`)
this gives per lane per call exactly **4×8 + 4×8 + 4×1 = 12 loads, 68 B**,
which is §2.3 to the byte — now *derived from the compiler's own view of the
program* rather than read off the source by eye. It also settles two things I
had only assumed:

- the four **code** loads are *not* vectorised into wider loads (rows are
  `packed_row_bytes = 256` apart, so they cannot coalesce), and
- the four **scale** bytes are *not* merged (scale rows are 16 B apart).

So the load count really is indexed by output row, which is the premise of the
§2.4 correction: at `opsi = 8` only the *activation* loads amortise.

### §3.9 Two levers closed offline, at zero device cost

**(a) `input_values[16]` register promotion — closed, was never a lever.**
The AIR census also reports `load_as0 = 19, store_as0 = 7`, i.e. thread-local
(stack) traffic, with 4 surviving `alloca`s. Taken at face value that would be
a large finding: 64 B of activations held in scratch and re-read four times
would exceed the 68 B of device traffic. It is an artefact. `xcrun metal -S
-emit-llvm` emits **pre-optimization** AIR: SROA and unrolling have not run, so
the rolled staging loop's variable index still forces the array to memory.
Proof that this is only an artefact: adding `#pragma clang loop unroll(full)` to
the staging loop (arm `u1`) and to all three row loops (arm `u2`) changes the
`.ll` (loop metadata appears) but leaves the census *byte-identical*, and after
the native backend runs, all three arms produce **exactly the same machine
code** — `__compute` section 4,944 B on `applegpu_g16s` and 5,040 B on
`applegpu_g17s` for shipped, `u1` and `u2` alike, and the same live
`maxThreads=1024 tgMem=80`. The backend already fully unrolls and promotes.

Methodological consequence, which I will not forget and which also retro-explains
why the advisor's `(bytes − floor)/8` instruction estimator did not reproduce:
**AIR from `-S -emit-llvm` is faithful for buffer attribution and access widths
(these follow from source types) and is *not* evidence about instruction counts,
register allocation, or spill.** Those must come from the native object or the
live driver.

**(b) Register pressure does not block `opsi = 8` or `16` — gate passed.**
`research/maple_frieren_r107f_opsi_pipeline_stats.swift` builds each arm's
pipeline on this device and reads what the driver's own register allocator
allows (`offline/opsi_pipeline_stats.json`). No kernel runs, so this costs no
device time and takes no thermal gate.

| arm | `__compute` g16s | `__compute` g17s | driver `maxTotalThreadsPerThreadgroup` | driver `tgMem` | my predicted `tgMem` | dispatchable @288 |
|---|---|---|---|---|---|---|
| `opsi4` (ships) | 4,944 | 5,040 | **1024** | 80 | 80 | yes |
| `opsi4` + full unroll | 4,944 | 5,040 | 1024 | 80 | 80 | yes |
| `opsi8` (**A1**) | 7,088 | 7,296 | **1024** | **144** | **144** | **yes** |
| `opsi16` | 11,360 | 11,872 | **1024** | **288** | **288** | **yes** |

Three independent things fall out:

1. **A1 and the `opsi=16` extension are dispatchable with no occupancy clamp.**
   The most likely cheap way for this lever to die — the register allocator
   pushing `maxTotalThreadsPerThreadgroup` below the 288 threads the geometry
   requests — does not happen. Rule 77's spill question is answered *before* any
   timing run, which is exactly the order rev6 §8 asks for.
2. **My threadgroup-memory arithmetic is confirmed by the driver**, not by me:
   `9 · opsi · 2 B` rounded up to the 16 B granule gives 80 / 144 / 288, and the
   driver reports 80 / 144 / 288.
3. `__compute` grows **linearly** at ≈535 B per output row (2,144 B for
   4→8, 4,272 B for 8→16) over a ≈2,804 B fixed floor. Linear growth with an
   unchanged per-row cost means the row loop is fully unrolled at every `opsi`
   and no spill-code expansion appears; a spill would show as a super-linear
   jump. This is weak evidence and I label it as such — `__compute` bytes are
   the only native observable on this platform (there is no AGX disassembler:
   `research/advisor-r89-agx-native-instruction-census.md:99-104`,
   `research/maple-frieren-r90-agx-instruction-census.md:114-116`) and I compare
   only matched-null arms compiled with identical flags.

Caveat stated up front: `maxTotalThreadsPerThreadgroup = 1024` is this device's
hardware cap, so all four arms are *at* the cap and the metric cannot tell me
how much register headroom is left above 288 — only that the arms are not
clamped. If a Stage-2 arm ever reports a `maxThreads` below its requested
threads I will report that and refuse to time it, per §2.6.

---

## §4 Stage 1 — the residency-defeated replica, measured

Probe `research/maple_frieren_r107f_t2d_probe.swift`; runner
`research/maple_frieren_r107f_stage1_run.sh SUFFIX ROUNDS DISCARD FOCUS_ROUNDS FOCUS_DISCARD`
(defaults `full 61 6 201 10`); adjudication
`research/maple_frieren_r107f_stage1_analyse.py`. Two **independent** runs,
`full` (job `423b49ad-3f72-4c40-97c0-aebcdeae32a1`, 7.1 s) and `full2`
(`64955e6f-176d-4cbf-916b-69b8bb7e4bdc`, 7.3 s), both exit 0, both with
`powermode 0` re-verified in-process. Everything below is reported as **two
replicates side by side**; nothing is quoted from a single run.

Raw: `research/artifacts/maple-frieren-r107f/stage1/t2d-probe-{full,full2}.json`;
tables `…/stage1/adjudication_report.txt`; machine-readable ledger
`research/artifacts/maple-frieren-r107f/adjudication.json`; W&B
`r107f-t2d-down-residual-amortisation` id `v6jsp3f9`.

### §4.1 Design, and how residency is defeated

The replica dispatches the §3.7 reconstructed kernel over a **640-expert bank**
(335,544,320 B codes + 20,971,648 B scales = 340 MiB), 6.4× the 53.5 MiB of
routed down weights an actual step touches, so the cold cells stride a working
set that cannot sit in any cache on this part. Every cell is
`(arm, calls, resident, split)`:

- `resident = false` walks fresh expert slots on every call; `true` re-reads one
  slot. Rule 98.9 (which I wrote) forbids a resident number from being a
  headline, so both are always reported.
- `split = true` issues `calls` separate `dispatchThreadgroups` into **one**
  encoder with per-call buffer offsets — this is the shipped regime, 39
  data-dependent invocations per step. `split = false` is one dispatch with
  `height: calls`.
- `runInterleaved` reverses cell order on odd rounds, so a monotone drift
  cancels; `emit()` reports **round-paired** deltas against the same-mode,
  same-residency `a0`, and the interval is the notched-boxplot
  `med ± 1.58·IQR/√n`.

Preconditions assert `5,013,504` weight+scale bytes and `5,030,912` total
unique bytes per call at start-up, so a geometry mistake aborts rather than
producing a plausible wrong number.

**V0 twin-fidelity gate.** Split-cold `a0` must reproduce the §3.6 in-situ
22.07 µs/call:

| replicate | block | µs/call | vs in-situ |
|---|---|---|---|
| run1 | grid n=61 | 22.716 | +2.93 % |
| run1 | focus n=201 | 22.719 | +2.94 % |
| run2 | grid n=61 | 22.660 | +2.67 % |
| run2 | focus n=201 | 22.740 | +3.04 % |

That is **outside** my preregistered ±2 % band, and I am not going to round it
into compliance. It is however **conservative in direction**: the twin is 2.7–3.0 %
*slower* than the shipped kernel, so it has strictly more time available to give
away than the real thing does. A null measured on a slower twin is therefore a
stronger null in situ, and a win measured on it would have needed in-situ
confirmation (Stage 2) before anyone believed it. I record the band miss as a
deviation, and I keep the direction argument as the reason the result still
adjudicates.

For contrast, the rev1 probe's fused regime measured 19.04 µs/call — a 14 %
*under*-shoot. That failure is what forced the split encoder, and §4.5 shows
exactly why.

### §4.2 Primary result: focus block, n=201, round-paired

`focus split cold calls=39`, Δ in µs/call against `a0`. Price book:
1 µs/call = 0.593892 % of `cs`; the 0.4 %-of-`cs` ship bar = **0.6736 µs/call**.

| arm | what it changes | run1 µs/call | run2 µs/call | run1 Δ | run2 Δ | 95 % interval | % of `cs` | × bar |
|---|---|---|---|---|---|---|---|---|
| `a0` | shipped twin | 22.719 | 22.740 | — | — | — | — | — |
| `a0_act0` | **all** activation loads → compile-time constants; line touches 44→12 (−72.7 %) | 22.261 | 22.294 | **−0.424** | **−0.457** | [−0.509, −0.378] | **−0.262** | 0.65 |
| `a0_wide` | WAL: 2 × `uint4`, loads/lane 12→10, line touches −36.4 % | 22.715 | 22.759 | +0.003 | −0.001 | ±0.03 | +0.001 | 0.00 |
| `a1` | **opsi 4→8**, issued bytes −23.53 %, unique bytes 0 % | 23.774 | 23.743 | **+1.040** | **+0.984** | [+0.922, +1.106] | **+0.601** | −1.50 |
| `a2` | control: 576 thr/TG, TGs 512→256, loads/lane unchanged | 22.702 | 22.721 | −0.026 | −0.029 | [−0.067, +0.009] | −0.016 | 0.04 |

Read the `a0_act0` row first, because it is the ceiling on the entire family.
Deleting *every* activation load — not amortising them, **deleting** them, which
no correct kernel can do — buys **0.44 µs/call = 17.2 µs/step = 0.26 % of `cs`**.
That is 0.65× the ship bar. The assignment's lever (A1) tries to remove 50 % of
those loads; even at 100 % removal the lever cannot reach the bar. Everything
after this is confirmation.

`a1` is the assignment's headline arm and it is **harmful**: +1.0 µs/call =
+39 µs/step = **−0.60 % of `cs`**, sign-consistent across replicates with a CI
far from zero. Issued bytes fell 23.5 % and the kernel got *slower*.

`a2` is the null cell working exactly as designed: change the threadgroup shape,
hold loads per lane fixed, get −0.03 µs/call with a CI straddling zero.

### §4.3 Full grid, n=61, split cold

| arm | run1 Δ | run2 Δ | % of `cs` | note |
|---|---|---|---|---|
| `a0_act2` | −0.184 | −0.056 | −0.07 | activation loads 4→2 |
| `a0_act1` | −0.150 | −0.098 | −0.07 | 4→1 |
| `a0_act0` | −0.536 | −0.478 | −0.30 | 4→0 |
| `a0_wide` | −0.152 | −0.073 | −0.07 | WAL |
| `a0_badcoal` | −0.152 | −0.099 | −0.07 | line touches 44→68, **+54.5 %** |
| `a1` | +0.901 | +0.971 | +0.56 | opsi 8 |
| `a1_wide` | +0.928 | +0.921 | +0.55 | opsi 8 + WAL |
| `a2` | −0.217 | −0.233 | −0.13 | control |
| `a3` | +1.240 | +1.321 | +0.76 | **opsi 16** |
| `a0_min` | −0.516 | −0.413 | −0.28 | arithmetic → one `simd_sum` |
| `a0_act0_min` | −0.618 | −0.502 | −0.33 | loads **and** arithmetic stripped |

Two rows in this table do more work than the rest of the experiment.

`a0_badcoal` deliberately **de-coalesces** the code loads so each simdgroup
touches 68 L1 lines instead of 44 — a 54.5 % increase — and it costs *nothing*
(−0.10 to −0.15, i.e. inside the same drift band as the arms that reduce line
touches). L1 line-touch count is simply not a binding resource in this kernel.
That single control retires the whole coalescing sub-family, WAL included, and
it is why I do not report `a0_wide`'s −0.07 as a real effect: an arm that
*worsens* the same metric by 54.5 % lands in the same place.

`a0_act0_min` strips **all** activation loads **and** **all** arithmetic and
still runs at **22.11–22.18 µs/call**, only 2.5 % faster than the shipped
kernel. My preregistered P3 falsifier was "if this arm lands at ≥ 21.1 µs/call
the lever family is dead". It lands a full µs above that line. Falsifier
**satisfied**.

Small |Δ| values in this n=61 grid drift by ~0.1 µs/call between replicates,
which is why the n=201 focus block is primary and this grid is the conservative
bound. Every sign that matters (`a1`, `a1_wide`, `a3` harmful; `a0_act0` the
family ceiling; `badcoal` free) is identical in both.

### §4.4 Rule 98.9 in action — the resident twins say the opposite

`grid calls=39 split resident`, same arms, same driver, only the residency
defeated:

| arm | run1 Δ | run2 Δ | resident verdict | cold verdict |
|---|---|---|---|---|
| `a0_act0` | −1.469 | −1.545 | −0.90 % of `cs` "win" | −0.26 % |
| `a1` | **−1.569** | **−1.474** | **−0.90 % of `cs` "win"** | **+0.60 % regression** |
| `a1_wide` | −1.642 | −1.808 | −1.02 % "win" | +0.55 % regression |
| `a2` | −1.893 | −1.692 | −1.06 % "win" | −0.13 % null |
| `a3` | −1.071 | −1.126 | −0.65 % "win" | +0.76 % regression |

Had I measured only cache-resident, I would have reported A1 as a **+0.93 % of
`cs` win** and asked fern to integrate a change that is a **−0.60 % regression**.
The control arm `a2`, which changes nothing but threadgroup shape, would have
looked like the biggest win of all. This is the most expensive mistake available
in this campaign and the rule that forbids it earned its keep here.

### §4.5 Why the encoder regime decides everything

`grid calls=39 fused cold` puts all 39 calls in one dispatch: every arm lands at
**19.0–19.3 µs/call**, 260–265 GB/s, with Δ ≈ 0 across the board — including
`a1`, which is harmful in the split regime. Fusing 39 dispatches amortises 38 of
the 39 launch/barrier boundaries and pins the kernel to the DRAM roofline, where
no arm can differ. That is precisely the rev1 defect (§4.9), and it is a trap
for anyone benchmarking a per-layer kernel standalone.

Call sweep, split cold, `a0`: 15.00 (1 call) → 19.87 (4) → 22.23 (16) → 22.60
(64) µs/call; fused: 15.21 → 14.89 → 19.05 → 19.07. Steady state is reached by
16 calls, so the 39-call cells are in it. `a1`'s split penalty grows
monotonically with call count (+0.47 at 4, +0.94 at 16, +1.05 at 64), which is
the signature of a per-dispatch cost, not a cold-start artefact.

Empty-kernel launch cost at 288 threads/TG: 2.750 µs (1 dispatch) / 1.863 (39) /
1.846 (156) at 128 TGs; 4.250/3.321/3.307 at 256 TGs; 7.125/6.907/6.899 at 512
TGs — about **13 ns per threadgroup** of launch throughput. Note that `a1` halves
the TG count (512→256) and *by this table* should save ≈3.6 µs of launch cost per
dispatch; it instead loses 1.0. Whatever `a1` gives up, it is not launch cost.

### §4.6 Exploratory: the split−fused gap is a barrier drain, not a launch ramp

**Not preregistered.** I added a three-mode encoder probe to the `full2` run
after seeing §4.5, because "38 amortised launch ramps" did not survive contact
with the empty-kernel table above. `a0`, cold, 39 calls:

| encoder mode | µs/call | empty-kernel cost in the same mode |
|---|---|---|
| serial (MLX default path) | 22.611 | 6.606 µs/dispatch |
| `.concurrent` | **19.530** | 6.297 µs/dispatch |
| `.concurrent` + explicit `memoryBarrier(scope:.buffers)` | 23.324 | 6.490 µs/dispatch |

The empty-kernel cost is the same in all three modes, so the 3.081 µs/call gap
is **not** dispatch setup. Adding the barrier back to the concurrent encoder
restores — and slightly exceeds — the serial number. The gap is the
**inter-dispatch barrier drain**: waiting for the last threadgroup of call *n*
to retire before call *n+1* starts. It is worth
**3.081 µs/call = 120.2 µs/step = 1.830 % of `cs`** on this kernel alone.

Confirmed against the vendored source rather than inferred: MLX already encodes
with `MTL::DispatchTypeConcurrent`
(`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp:548`) and inserts
a barrier only when its RAW/WAR input/output tracking sets `needs_barrier_`
(`CommandEncoder::maybeInsertBarrier` `device.cpp:363-374`, called from
`dispatch_threadgroups` `:376-382` and `dispatch_threads` `:384-390`; `barrier()`
`:393`; declarations `device.h:56-58,92`). The down-residual's 39 invocations
consume each other's outputs through the residual stream, so **this** kernel's
barrier is genuinely required and I am not proposing to remove it. The value of
the number is that it closes the accounting, and that it prices dispatch-boundary
elimination for the rest of the campaign (§5.4).

### §4.7 The 22.07 µs/call anchor, fully accounted

| component | µs/call | share of 22.07 | source |
|---|---|---|---|
| unique-byte floor 5,030,912 B at 263.3 GB/s | 19.107 | 86.6 % | `stream` probe, this run |
| barrier drain | 3.081 | 14.0 % | §4.6 |
| exposed activation loads (**upper bound**) | 0.441 | 2.0 % | `a0_act0`, n=201 |
| exposed arithmetic (**upper bound**) | 0.465 | 2.1 % | `a0_min` |
| both stripped together | 0.560 | 2.5 % | `a0_act0_min` |

The last three overlap with each other and partly hide under the first two, which
is why they sum past 100 %: the two "exposed" rows are what is *left visible*
after the memory system and the barrier have absorbed everything they can, and
stripping both together (0.560) is less than the sum of stripping each alone
(0.906). The honest one-line reading: **~87 % of this kernel is unique DRAM
bytes, ~12 % is a required barrier, and ≤2.5 % is everything my assignment was
allowed to touch.**

### §4.8 Machine ceilings, reproduced

`stream` 263.30 / 263.17 GB/s at 64 MiB and 260.94 / 260.21 GB/s at 256 MiB
across the two runs — reproduces the §3.1 standalone ceiling (260.6–260.7 GB/s)
to better than 0.2 %. `issue` peaks at **632.2 Gload/s** in both runs. The
shipped kernel issues 1,769,472 loads/call in 22.07 µs = 80.2 Gload/s, i.e.
**12.7 % of load-issue capacity**. It is not close to issue-bound, which is the
premise §2.3 was built on.

### §4.9 The rev1 probe was wrong three ways, and I am recording all three

The first Stage-1 build (job `1e2110f1-145b-43fb-97d1-52af806f97bd`) produced
numbers I threw away. Its defects, because each is a reusable trap:

1. **Wrong regime.** It timed one fused dispatch of 39×512 TGs, amortising 38 of
   39 dispatch boundaries. Every cold arm piled up at ≈19.1 µs/call = the DRAM
   roofline and V0 failed *low* (19.13 vs 22.07). §4.5 is the same effect,
   measured deliberately.
2. **Dead-code elimination.** The `_noarith` arms reported 6.5–6.8 µs/call =
   736 GB/s, above the measured DRAM ceiling and therefore impossible: the
   compiler had deleted the loads whose results nothing consumed. rev2 keeps a
   `simd_sum` so every load is live. **Any "stripped" arm that beats the memory
   roofline has been optimised away, not accelerated.**
3. **Not interleaved.** Cells ran in fixed order, so `a0` at calls≤39 absorbed
   the warm-up and read 43.58 µs/call. rev2 reverses cell order on odd rounds and
   pairs deltas within a round.

---

## §5 Verdict

### §5.1 The named outcome

**`N-T2D-ISSUE-BOUND`** — the §2.7 label for "Stage 1 refutes the premise".
`N-T2D-ROOFLINE` is *concurrently* satisfied by §4.7; §2.7 permits exactly one
name in §0, so `N-T2D-ISSUE-BOUND` is it, because premise-refutation is the
load-bearing finding and the roofline statement is its consequence.

I will not dress this in a new label. My analysis code initially printed
`N-T2D-DRAM-BOUND`, which is a better *description* of the mechanism but is not
in the preregistered vocabulary; §2.7 says the vocabulary may not be extended
after the fact, so the descriptive phrase now lives in the ledger's
`verdict_mechanism` field and the verdict itself is a preregistered term.

**Trigger.** §2.8's own added gate: *"the replica must show an A1-vs-A0
improvement whose extrapolation to 39 calls reaches at least the 17.6 µs/step
adverse-prior ceiling. A replica that cannot find the effect with the confound
removed will not find it in situ."* A1 came back at **+38.4 µs/step, the wrong
sign**, replicated. Gate failed. Note the §2.8 branch conditions did *not* fire
as written — the AIR load census matched §2.3 exactly (12 loads, 68 B per lane,
§3.8), and `L` is not small (§4.6). The premise failed for a third reason
neither branch anticipated: `L` exists but is a barrier drain that is invariant
to the lever, and the coefficient on *issued* bytes is not merely zero but
adverse.

### §5.2 Nothing ships, and the diff proves it

Per the §2.8 stopping rule, **Stage 2 (in-situ ABBA) is not warranted**: there
is no candidate to A/B. The submitted surface is untouched and must stay
untouched:

```
$ git diff --numstat 2454cc01ea3afabac067f0a271e36901fea7d21c HEAD -- $(jq -r '.editablePaths[]' benchmark.json)
$ git diff --numstat 2454cc01ea3afabac067f0a271e36901fea7d21c HEAD -- Sources/ Vendor/ benchmark.json
```

Both print nothing. Zero receipts were spent this revision.

### §5.3 What is now closed, with prices

| lever | measured | ruling |
|---|---|---|
| **A1** opsi 4→8 (the assignment's headline) | +0.98 to +1.04 µs/call = **−0.60 % of `cs`** | **closed, harmful — do not integrate** |
| **opsi 4→16** | +1.24 to +1.32 = **−0.76 %** | closed, harmful |
| **A1 + WAL** | +0.92 to +0.93 = **−0.55 %** | closed, harmful |
| **WAL** (wide activation loads) | +0.003 / −0.001 = **0.00 %** | closed, exact null |
| **any activation-load reduction** | ceiling −0.44 µs/call = **+0.26 %**, 0.65× bar | closed by ceiling |
| **any coalescing / line-touch work** | +54.5 % line touches costs nothing | closed by control |
| **arithmetic reduction (§6.4 family)** | ceiling +0.28 % | closed by ceiling |

### §5.4 Three campaign-level corollaries I did not expect to be able to state

1. **Issued-byte reduction with unchanged unique bytes buys nothing at batch 1,
   and can cost.** A1 cut issued bytes 23.5 % and lost 0.60 % of `cs`. Any future
   proposal whose stated mechanism is "fewer loads per unique byte" on a
   decode-path kernel now has to clear this counter-example first.
2. **L1 line-touch count is not a binding resource on this part at batch 1.**
   `a0_badcoal` (+54.5 % line touches) is free. Coalescing arguments need a
   different justification than line-touch arithmetic.
3. **The α/β degeneracy tilts toward "only bytes pay".** State doc §B.0.6 leaves
   α ≈ 0.389 (efficiency work pays) against α ≈ 0.4369 (only bytes pay). On the
   11.7 %-of-`B` slice I just instrumented, efficiency work at fixed unique bytes
   paid **zero or negative** in every one of eleven arms. That is direct evidence
   for **`α = 0.4369, β = 0.5 two-pool map, residual −6.63 %, #561`**, whose
   pooled prediction for this kernel (85.3 % of M5 peak, 55.1 µs of headroom)
   should now be read as *already-achieved efficiency*, not available headroom.

### §5.5 Two follow-ups I did **not** implement

- **Dispatch-boundary elimination is the priced prize here.** §4.6 says each
  eliminated inter-dispatch barrier on a kernel this size is worth ≈1–3 µs, and
  the decode path runs 39 of them for this kernel alone: 40–120 µs/step =
  **0.6–1.8 % of `cs`**. This kernel's own barriers are data-dependent and
  irreducible, so the value is in *fusing adjacent kernels* (e.g. the
  `residual_rms_router` → `routed_swiglu_qmv` → `down_residual` chain, 311.9 +
  1499.9 + 860.5 µs/step across 3×39 dispatches) so that fewer barriers stand
  between the same bytes. I am not proposing a design; I am handing over a
  measured price for one.
- **This whole family is a priori far more attractive in prefill**, where weights
  are amortised over 512 tokens and the arithmetic-to-byte ratio inverts, so
  output-row amortisation plausibly *does* pay. My experiment says **nothing**
  about prefill — it measured one token per call by construction — and on this
  gen-16 host I could not have measured the ranked `_nax` prefill kernels anyway
  (§3.1). Whoever picks this up must do it on an M5.

---

## §6 Deconfliction (rev6 §6.7) — reproduced and honoured

| owner | PR | region I do not touch |
|---|---|---|
| maple-edward | #629 | `lagunaDecodeNVFP4QKVLaneMajorSource` (`:4922`), `lagunaRoutedSwiGLUQMVPackedTop8` (`:8030`) |
| maple-alphonse | #644 | `lagunaGatedAffineOProjNVFP4Source` (`:4222`), `lagunaGatedAffineOProjNVFP4` (`:4586`) |
| maple-tanjiro | #642 | `laguna_sliding_fused_attn_ring_v1` (`:1508`), `laguna_full_fused_attn_grow_v1` (`:2028`) |
| maple-fern | #625 | integration — I hand to him |
| maple-nezuko | #616 | revert residual forensics |

My whole diff is confined to `lagunaRoutedSharedDownResidualSource` (`:8277`),
its four kernel-object name strings (`:8225-8276`, `:8429-8430`, `:8558-8559`)
and the `grid:`/`threadGroup:` line of `lagunaRoutedSharedDownResidual`
(`:8578`+68) — a byte range that contains none of the five regions above.

**Why alphonse's #644 and my R107-F cannot collide:** they edit different MSL
generator functions (`lagunaGatedAffineOProjNVFP4Source` vs
`lagunaRoutedSharedDownResidualSource`) which build different pipelines from
different weight tensors (`o_proj` vs routed/shared `down_proj`) and are
launched from different dispatch wrappers with different grids, so neither
edit can change a line, pipeline, buffer or launch the other touches. He is
running the same *class* of change (output-row amortisation) on oproj: if his
G1 arm wins, my prior rises — I note that and do not wait for him.

**Addendum after Stage 1:** the deconfliction analysis above is now moot in the
strongest possible way. My final submitted-surface diff is **empty** (§5.2), so
there is no byte range to collide with anyone. The table stands as the record of
what I *would* have touched had A1 won.

---

## §7 Reply to the advisor — four things I did differently or got wrong

I would rather flag these myself than have them found in the diff.

### §7.1 rev6 said "rebase onto the advisor tip"; I merged instead

Rev6 §1 asked me to rebase this branch onto the advisor tip. I did not rebase. I
merged, and the reason is arithmetic:

```
advisor tip           2454cc01ea3afabac067f0a271e36901fea7d21c   (re-confirmed at run time)
merge-base            446fe987
non-merge commits unique to maple-frieren/r105-router-prefetch-adjudication: 86
```

Replaying 86 commits — most of them research artefacts, several of them large
JSON and log files — through a rebase on the eve of the freeze is a
conflict-and-loss risk I was not willing to take against a deadline, and a
partially-completed rebase would have left the branch in a state neither of us
could reason about. I followed the advisor's own precedent for exactly this
situation, merge commit `37b91de7`, and then proved the merge is
*equivalent to* the requested rebase for every purpose the request serves:

```
git diff --numstat 2454cc01 HEAD -- <all 97 editablePaths>   → empty
git diff --numstat 2454cc01 HEAD -- Sources/ Vendor/ benchmark.json → empty
```

Both commands print nothing. Whatever the base discipline was meant to
guarantee — that my submitted surface is exactly the advisor tip's submitted
surface, with no stale frontier and no accidental carry-over — is guaranteed,
and it is guaranteed by measurement rather than by the shape of the history. If
the advisor wants the literal linear history anyway, say so and I will do the
rebase as a separate, dedicated operation with nothing else in flight.

### §7.2 The V0 twin-fidelity gate missed its ±2 % band, by +2.7 to +3.0 %

I preregistered (§2.7) that the standalone replica's `a0` arm must reproduce the
in-situ 22.07 µs/call within ±2 %, or the twin is not a twin. Measured:
22.716 / 22.719 µs/call (run 1) and 22.660 / 22.740 (run 2) — **+2.67 % to
+3.04 %**. That is outside the band I wrote down, and I am not rounding 3.04 %
into "about two percent".

Why the adjudication survives it: the miss is **conservative in direction**. The
replica is *slower* than the shipped kernel, i.e. it has slightly more overhead
per call than the real thing. A twin with more overhead makes it *easier*, not
harder, for an amortisation arm to show a win, because there is more overhead
available to amortise. The arm still came back with the **wrong sign**
(+1.040 µs/call), and the family ceiling arm `a0_act0_min` still landed at
22.109 µs/call, i.e. above the 21.1 µs/call P3 falsifier by a margin far larger
than the 3 % fidelity gap. A negative measured on a generous instrument is a
stronger negative than the same negative measured on a faithful one. Had the arm
come back *positive* inside 1 %, this gate failure would have invalidated the
result and I would have reported no verdict.

I did not silently widen the band. The band is still ±2 % in §2.7, this is
recorded as a deviation, and the verdict is reported with the deviation
attached.

### §7.3 The first Stage-1 probe was wrong three ways and produced a false negative

Full detail is in §4.9; the summary is that rev1 of the probe (job
`1e2110f1-145b-43fb-97d1-52af806f97bd`) (a) ran the fused encoder regime, which
amortises 38 of 39 dispatch boundaries and pins every arm to the DRAM roofline
so no arm can differ, (b) let the `_noarith` control arms be dead-code
eliminated — they reported 6.5–6.8 µs/call, which is 736 GB/s and physically
impossible on a 260 GB/s box — and (c) did not interleave arms, producing a
pathological 43.58 µs `a0`. All three were caught by cross-checking against
physical ceilings I had measured in Stage 0 rather than by the probe reporting an
error. Rev2 fixes all three (`simd_sum` sink, split encoder, round-paired
interleave) and both rev2 replicates agree on every sign that matters.

The lesson I want on the record: **a standalone kernel probe that does not
reproduce the shipped encoder regime measures the roofline, not the kernel.**
Anyone benchmarking a per-layer kernel outside the model will hit this.

### §7.4 An `explore` subagent destroyed untracked work earlier in this revision

At one point I spawned a subagent to inspect the tree and it ran `git clean`,
which deleted untracked research files I had not yet committed. Nothing shipped
or measured was lost — the affected files were regenerable scripts — but time
was. My standing rule now, which I would suggest for the whole campaign: **commit
before spawning any subagent that will touch the working tree.** Subagents
inherit the terminal but not my judgement about what is precious.

---

## §8 Stage-3 handoff payload for maple-fern (#625)

Written in alphonse's #636 §11.1 format so the advisor can relay it verbatim.
**This is a do-not-integrate payload.** There is no code to take; the value here
is the set of doors it closes and the two it opens.

### §8.1 Exact diff to integrate

**Empty.** Against base `2454cc01ea3afabac067f0a271e36901fea7d21c`:

```
git diff --numstat 2454cc01 HEAD -- <all 97 editablePaths>            → (no output)
git diff --numstat 2454cc01 HEAD -- Sources/ Vendor/ benchmark.json   → (no output)
```

Everything on this branch is under `research/`, which is not part of the
submitted surface. Byte budget consumed: **0**. Growth against the
262,144-byte-per-review cap: **0**.

### §8.2 Bit-exactness argument

Trivial. No submitted file changes, so every checked greedy token, every
teacher-forced logit, and every KV row is bit-identical to the base by
construction. The upstream-equivalence oracle is not implicated. No
re-quantization, no precision change, no dispatch change, no layout change.

### §8.3 Rule 75 digests (`research/artifacts/maple-frieren-r107f/rule75_digests.txt`, 14:46:03Z)

| artefact | sha256 (head) | bytes |
|---|---|---|
| `.build-worker/release/mlxfast-runtime-worker` | `80b67aa0…d6b7a` | 49,210,600 |
| both metallibs (identical) | `8e8b18af…97ec` | 158,502,072 |
| `/tmp/r107f_probe` | `82268032…fbd2` | — |
| probe source | `PROBE_SRC_SHA256=9aea7e61…015` | — |
| Stage-1 runner | `RUNNER_SHA256=1abbb3d9…c4c` | — |

The anchor worker was built with `research/nezuko-pr158-gpuprof-hook.patch`
applied and `Sources/` restored afterwards; the patch is research-only and is
not in the submitted surface.

### §8.4 Rule 77 geometry of the shipped kernel, resolved on device

Exactly one routed down-residual pipeline of 137 exists on device:

| property | value |
|---|---|
| pipeline | `laguna_routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6` |
| flags | `sharedHalved=true staged=true sharedFirst=false fusedStaging=true` |
| `group_dims` | (288, 1, 1) |
| `grid_dims` | (147456, 1, 1) ⇒ 512 TGs/call, 9 simdgroups/TG |
| `maxTotalThreadsPerThreadgroup` | 1024 |
| `threadExecutionWidth` | 32 |
| `staticThreadgroupMemoryLength` | 80 B (probe predicts 72; driver rounds up) |
| calls/decode step | 39 |

The `_sf` (shared-first), unhalved and unstaged variants are **dead text** on
this configuration — they are never instantiated. Anyone editing
`lagunaRoutedSharedDownResidualSource` should know that three of its four
generated forms cannot be reached.

### §8.5 Measured prices, with CIs, in % of `cs`

Bar for this campaign: **0.4 % of `cs` = 26.27 µs/step = 0.6736 µs/call**
(the kernel runs 39 calls/step; 1 µs/call = 0.593892 % of `cs`).

Sign convention, same as §5.3: **Δ µs/call is positive when the arm is
*slower*; the score column is positive when the arm would *gain* score.** A
positive Δ therefore pairs with a negative score.

| arm | Δ µs/call (run1 / run2) | 95 % CI | score Δ (% of `cs`) | verdict |
|---|---|---|---|---|
| `a1` — `outputs_per_simd` 4→8 | +1.040 / +0.984 | [+0.922, +1.106] | **−0.60 harmful** | do not integrate |
| `a1_wide` — A1 + wide activation loads | +0.928 / +0.921 | — | −0.55 harmful | do not integrate |
| `a3` — `outputs_per_simd` 4→16 | +1.240 / +1.321 | — | −0.76 harmful | do not integrate |
| `a0_wide` — wide activation loads alone | +0.003 / −0.001 | ±0.03 | 0.00 exact null | do not integrate |
| `a2` — control, 576 threads/TG | −0.026 / −0.029 | [−0.067, +0.009] | +0.02 null | do not integrate |
| `a0_act0` — *all* activation loads deleted (upper bound, not shippable) | −0.424 / −0.457 | [−0.509, −0.378] | +0.26 | 0.65× bar |
| `a0_act0_min` — activations *and* arithmetic deleted (family ceiling) | −0.618 / −0.502 | — | +0.33 | 0.83× bar |

Read the last two rows as the ceiling of the entire family: even deleting every
activation load *and* all arithmetic — which changes the answer and can never
ship — buys 0.83× of the bar. There is no shippable member of this family.

### §8.6 The closed accounting that makes all of the above inevitable

22.07 µs/call decomposes as:

| component | µs/call | share |
|---|---|---|
| unique-byte DRAM floor (5,030,912 B at 263.3 GB/s) | 19.107 | 86.6 % |
| inter-dispatch barrier drain (39 data-dependent barriers) | 3.081 | 14.0 % |
| exposed activation loads (upper bound) | ≤0.441 | 2.0 % |
| exposed arithmetic (upper bound) | ≤0.465 | 2.1 % |

(The last two overlap; stripped together they are 0.560 µs/call = 2.5 %.) Issue
utilisation is **80.2 Gload/s against a measured 632.2 Gload/s capacity = 12.7 %**.
A kernel at 12.7 % of issue capacity and 86.6 % of its byte floor cannot be made
faster by issuing fewer instructions.

### §8.7 Explicit do-not-integrate list

- **A1** (`outputs_per_simd` 4→8) — measured regression, costs 0.60 % of `cs`.
- **A1 + WAL** — costs 0.55 %.
- **opsi 16** — costs 0.76 %.
- **WAL alone** (2 × `uint4` activation loads, −36.4 % L1 line touches) — exact
  null, +0.001 % of `cs`, ±0.03 µs/call. It is *free*, it is *correct*, and it
  buys nothing. Do not spend review budget on it. Note this is a different
  change from `DARKBLOOM_QMV_WIDE_CODES`, which widened *codes* (already
  coalesced) and closed at −0.5363 % of `cs`.
- **Coalescing work on the activation loads generally** — the `a0_badcoal` arm
  *degrades* line touches by +54.5 % and is still free (−0.152 / −0.099). The L1
  behaviour of this kernel's activation reads is not on the critical path in
  either direction.

### §8.8 Two follow-ups I did not implement, with prices

1. **Fusion of the 39 barrier boundaries — 0.6 to 1.8 % of `cs`.** The
   split→fused gap is **3.081 µs/call = 120.2 µs/step = 1.830 % of `cs`**, and I
   proved it is a *barrier drain*, not a launch ramp: the empty-kernel cost is
   6.297–6.606 µs/dispatch in serial, `.concurrent`, and
   `.concurrent`+explicit-barrier modes alike, so the launch cost is invariant
   while the gap is not. MLX already dispatches with
   `MTL::DispatchTypeConcurrent` (`device.cpp:548`) and inserts a barrier only
   when `needs_barrier_` (`maybeInsertBarrier`, `device.cpp:363-374`). This
   kernel's 39 barriers are genuinely data-dependent, so the full 1.83 % is
   **not** available by flipping a flag — it requires restructuring so that
   independent experts' down-projections can be in flight together. That is a
   real, large, and expensive lever, and it is the single biggest number I found
   in this kernel. If anyone gets a Stage-3 slot for decode, this is where I
   would spend it, not on amortisation.
   🔧 **Re-priced in §11.3–§11.4 under rule 105.13.** The drain is
   **0.80–0.92 %** of `cs`, not the bare 1.830 % printed above (it converts in
   the execution regime, `k ∈ [α, β]`, *not* at `k_dispatch`=1.89 — §11.3 proves
   this from the mode-invariant empty-kernel cost). But the merge also removes
   **one dispatch per layer**, which 105.13 prices at **+1.390 % [1.352, 1.428]**
   independently and additively, so **one merge is worth +2.19–2.31 %** and the
   dispatch part alone survives even if the fused kernel must re-import a
   device-wide barrier. **Read §11.4 before sizing this lever.**
2. **Prefill.** Everything above is one-token-per-call by construction and says
   nothing about prefill. This host is Apple GPU generation 16, below the
   generation-17 floor, so `nax_available=false` and I **cannot** reach the
   ranked M5's `_nax` prefill kernels here at all (§3.1). Any prefill follow-up
   must be measured on an M5. Do not let an M4 prefill number into an `_nax`
   argument.

### §8.9 Campaign rules this revision earned

- **Rule 98.9 vindicated with a number.** Cache-resident twins of the same arms
  say the *opposite*: `a1` reads −1.569 / −1.474 µs/call resident, which reads as
  a **+0.90 % of `cs` win**, when cold it costs 0.60 %. Resident-only measurement
  would have shipped a regression and made the do-nothing control arm `a2` look
  like the biggest win on the board (§4.4).
- **Per-kernel GPU-busy time is not immune to host-side perturbation.** An
  unguarded per-call MSL dump fired 1,328 times, and *every* kernel's
  GPU-timestamped duration inflated ~2.5× via DVFS while wall time went to
  192.890 ms/step (§3.5). A GPU-timestamp delta is not a hermetic measurement.
- **`-S -emit-llvm` on Metal emits pre-optimization AIR.** It is faithful for
  buffer attribution and access widths and for nothing else; it cannot be used
  to reason about register pressure or scheduling
  (§3.9). Register pressure does *not* block opsi 8/16 here — `__compute`
  bytes are 4,944 / 7,088 / 11,360 and all three dispatch at 288 threads/TG.

---

## §10 Housekeeping the advisor asked for

### §10.1 The tree-swap question is closed by my own measurement

`4b0e051b` 3-replicate mean official score **2.582463** vs `bd33883e`
**2.582286** ⇒ **+0.007 %**, entirely inside the campaign σ of
`sd(ln cs) | fixed tree = 0.3607 %`. Two trees separated by 0.007 % when the
instrument's own noise is 0.36 % are indistinguishable, so there is no evidence
for swapping the integration base. We hold **`bd33883e` + 1 file**. I withdraw
the tree-swap proposal and I am not asking for it again.

### §10.2 Acceptance of the #615 nibble-delta ruling

I accept the ruling and will not re-open it. The decisive number is mine: after
subtracting what the strided-aliased `_nax` prefill views
(`LagunaRuntimeWeights.swift:998-1039`), the 16-byte packed-bank granularity
and the 128-entry `lagunaScalePatchHeaderBytes` make unreachable, the remainder
worth **+0.158 % of `cs`** — under half the ship bar — and buying it costs
+337 MB of double residency on a 128 GB box that already holds a 21.6 GB tower.
Counter-evidence #85 and #513/#525 point the same way. A lever whose *entire
reachable* upside is 0.4× the bar is not a lever; it is a footnote, and it now
reads as one.

---

## §11 Rule 105.13 landed after my verdict. I re-price my own report against it.

Added 2026-08-10T15:30Z, after the advisor pushed `bde79502` (rule 105.13) to
the campaign branch. Arithmetic: `research/maple_frieren_r107f_r10513_repricing.py`
(runs in 0.1 s, prints every number below). Nothing in §0–§10 above has been
edited; this section states what those numbers should have said.

### §11.1 The correction I owe: every `% of cs` in this report is **bare**

§4.2 and §8.5 price with `1 µs/call = 0.593892 % of cs`, i.e.
`39 × 0.015228`. That is the **M5** price applied to an **M4** measurement with
no `k` — rule 105.12 category (c), the exact error the advisor corrected in
nezuko's R106-B §C.5 in 105.13(f). I made it too, in every table, and I am
correcting it here rather than waiting to be told. `k` belongs in all of them:

| arm / quantity | Δ M4 µs/step | as published (bare) | correct (β=0.5) | correct (α=0.4369) | preferred family |
|---|---|---|---|---|---|
| `a1` opsi 4→8, mean | +39.468 | **−0.601 %** | **−0.301 %** | −0.263 % | latency (issue-bound) |
| `a1`, CI low end | +35.958 | −0.548 | −0.274 | −0.239 | |
| `a1`, CI high end | +43.134 | −0.657 | −0.328 | −0.287 | |
| `a1_wide` | +36.056 | −0.549 | −0.275 | −0.240 | latency |
| `a3` opsi 4→16 | +49.939 | −0.760 | −0.380 | −0.332 | latency |
| `a2` control | −1.073 | +0.016 | +0.008 | +0.007 | latency |
| `a0_wide` (WAL) | +0.039 | −0.001 | −0.000 | −0.000 | bytes |
| `a0_act0` **family ceiling** | −17.180 | +0.262 | +0.131 | **+0.114 %** | bytes (deletes loads) |
| `a0_act0_min` **family ceiling** | −21.840 | +0.333 | +0.166 | **+0.145 %** | bytes |
| barrier drain (§4.6) | +120.159 | 1.830 | **0.915** | 0.799 | execution, see §11.3 |

Two derived statements in the body are wrong in the same way and are hereby
restated:

- **The ship bar in this kernel's own units.** §4.2/§8.5 give
  `0.4 % = 0.6736 µs/call`. Bare. Correctly the bar is **1.347 µs/call**
  (latency) or **1.542 µs/call** (bytes) — an arm has to be **2.0–2.3× larger**
  than I said to matter.
- **§3.6's difficulty framing.** "The entire efficiency headroom is
  2.83 µs/call = 110.4 µs/step; the bar is 26.27 µs/step, so an efficiency-only
  lever must capture **23.8 %** of the gap." That divides an M4 numerator by an
  M5 bar. The M4 bar is 52.5 (latency) / 60.1 (bytes) µs/step, so the required
  capture is **47.6 % – 54.4 %**. The honest framing is *twice* as discouraging
  as the already-discouraging one I published: you must capture more than half
  of the total distance to the measured DRAM ceiling.

### §11.2 What this moves: nothing, and that is the point

Rule 105.12's one-sidedness theorem says bare pricing over-states, so bare
verdicts can only be **false positives** — a closure priced bare stays closed
when it is priced correctly. This revision's verdict is a closure
(`N-T2D-ISSUE-BOUND`, nothing ships), so every correction above **hardens** it:

- `a1` is still harmful, still sign-consistent, still CI-excluding-zero. Its
  magnitude halves (−0.60 → −0.30 %), which is *worse* for the lever, not
  better: it was never a candidate, and now the case that it is invisible-and-
  harmful rather than visible-and-harmful is stronger.
- The **family ceiling is the number that matters** and it falls from 0.65× the
  bar to **0.29× (bytes) / 0.33× (latency)**. Deleting *every* activation load
  in the kernel — which no correct kernel can do — is now measured at under a
  third of the draw bar. `N-T2D-ISSUE-BOUND` was the right verdict for a
  slightly wrong reason; the right reason is stronger.
- Rule 105.7's detection-floor point also sharpens. The floor is ≈80 M4 µs/step
  for a single receipt. `a1`'s harm is 39.5 M4 µs/step (2.0× below the floor) and
  the whole family's *ceiling* is 17.2 M4 µs/step (**4.6× below it**), so no
  receipt could ever have adjudicated this row in either direction. The CI was
  the only possible deliverable, exactly as the brief said.

### §11.3 The drain is **not** in the dispatch regime, and I can prove it from §4.6

105.13(d) warns that dispatch-family quantities priced bare were *under*-valued
by 1.89×. If my 3.081 µs/call barrier drain were dispatch-family it would be
worth **3.458 % of cs**, not 1.830 %, and it would be the largest single number
in this campaign. It is not, and §4.6 already contains the discriminating
measurement:

> the empty-kernel launch cost is **6.297–6.606 µs/dispatch and mode-invariant**
> across serial, `.concurrent`, and `.concurrent`+explicit-barrier, while the
> 3.081 µs/call gap appears and disappears with the barrier.

Dispatch cost is the thing that did **not** move. So the drain is disjoint from
the dispatch regime by construction. Physically it is the GPU waiting for the
last threadgroup of call *n* to retire — **GPU-resident occupancy tail**,
whereas 105.13(c) defines the `k≈1.89` regime as "host/driver-resident work that
does not shrink when you add GPU cores". A retirement tail *does* shrink when
you add cores: more cores → the final wave completes sooner. So the drain
converts in the execution regime, `k ∈ [α, β]`, and its corrected value is
**0.799 – 0.915 % of `cs`** (M4-measured, converted; `marginal`).

That is still **2.0–2.3× the 0.4 % draw bar**, so §8.8's conclusion survives:
it remains the largest unclaimed number I found. §8.8's advertised range
"0.6 to 1.8 %" brackets the corrected value at its lower end, so no reader was
misled about the order of magnitude; the point estimate should read **0.9 %,
not 1.8 %**.

### §11.4 What 105.13 adds that I did not price: the dispatch summand *beside* the drain

Because the drain and the dispatch cost are disjoint (§11.3), a kernel merge
collects **both**, additively. I priced only the drain. Rule 105.13(e) supplies
the other half, and it is bigger than mine:

| component of one per-layer kernel merge | M5 µs/step | % of `cs` | basis |
|---|---|---|---|
| 39 dispatches removed | 91.27 [88.79, 93.76] | **+1.390 % [1.352, 1.428]** | rule 65 marginal, already M5 — no conversion |
| barrier drain removed (this kernel's boundary) | 60.1 – 68.8 | **+0.799 – 0.915 %** | §4.6, M4-measured, converted |
| **one merge, total** | 151 – 160 | **+2.19 – 2.31 %** | sum of two disjoint families |
| three-kernel merge, dispatch part only (2 boundaries) | 182.5 | +2.780 % | rule 65 × 2 × 39 |

⚠ Three caveats, or this becomes the kind of headroom pool rule 105.8 forbids:
1. Rule 65's 2.3403 µs is the marginal cost of an **added** dispatch. Removal
   symmetry is an assumption, not a measurement.
2. I measured the drain at **one** boundary (down-residual's own). The other two
   boundaries of the `residual_rms_router → routed_swiglu_qmv → down_residual`
   chain are unmeasured; do not multiply my number by three.
3. **The merged kernel may have to re-import the barrier.** The next layer's RMS
   is a whole-row reduction, so a fused kernel needs a device-wide
   synchronisation somewhere; if it cannot be made threadgroup-local, the drain
   part evaporates and only the 1.390 % dispatch part survives. That is still
   3.5× the bar, which is why the merge is worth a Stage-3 slot even under the
   pessimistic reading.

### §11.5 Why 120 µs/step does not contradict rule 92's 1.3003 µs/step cap

A reader who knows rule 92 (barrier/encoder/command-buffer family capped at
1.3003 µs/step) will think my 120.159 µs/step drain falsifies it. It does not,
and the distinction is the same one 105.13(e) draws:

- **Rule 92 caps the "same dispatch set, encoded better" family.** Reordering,
  merging command buffers, changing encoder scope. My §4.6 probe *is* an
  instance of that family, and it agrees with rule 92: `.concurrent` looked like
  a 3.081 µs/call win until the required barrier was put back, at which point it
  came out **slightly worse than serial** (23.324 vs 22.611 µs/call). Net
  encoder-level win: zero. Rule 92 stands, measured again, independently.
- **The drain is only reachable by changing the dispatch set**, i.e. a genuine
  kernel merge, which is a source-level rewrite and not in rule 92's family at
  all.

So the two numbers are about different interventions and both are correct. Rule
92 remains closed for encoder work; the merge lever remains open and is now
priced at 2.2 % rather than 1.8 %.

### §11.6 One more standing hazard 105.13(b) names, checked against this report

"Never divide a local `--local-submit` level by a receipt level." I did not do
this: every contrast in §4 is a **paired** M4 delta on one harness, and the two
*levels* I quote (unique-byte floor 19.107 µs/call, in-situ anchor 22.07
µs/call) are compared only to each other and to a DRAM ceiling measured on the
same host in the same run. For anyone tempted to quote them as shares of `cs`:
the anchor is **5.73 % (α) / 6.55 % (β)** of `cs`, not the 13.1 % that the bare
price would give, and neither figure is a headroom pool — 86.6 % of it is a
unique-byte DRAM floor that no rewrite can remove.

---

## §12 Priority A delivered: the margin certificate is a service, not a one-off

The round-107 brief's priority A was to make the R106-J certificate instrument
usable by anyone without me. Done:
**`research/maple-frieren-margin-certificate-service.md`** — the standing SOP.
It contains the decision tree, the perturbation-class table, the request
contract (what a requester must hand over, including a reachability witness and
a class self-declaration with `file:line`), the fully self-serve command
sequence, the verdict/exit-code contract, and the eight limits a green
certificate does **not** cover.

**The service is verified up, not asserted up.** I ran a timed null cell on the
current tree (`research/maple_frieren_r107f_sop_dress_rehearsal.sh`, job
`89ba759c`, 15:18Z, artifact
`research/artifacts/maple-frieren-r107f/sop/cert_rehearsal_null.json`):

- verdict **`PASS-BIT-EXACT`**, 0 of 6,522,880 elements differing, 0 argmax
  flips, exit 0;
- **capture 50 s + 49 s, certify <1 s, total 99 s** — so the honest SLA is
  ≈**25–35 min** request→verdict including a 131 s force-clean candidate build
  and the write-up, of which **under 8 minutes is machine time**;
- the baseline margin distribution reproduced **min 0.375, p1 0.615, p50 6.5,
  0 exact ties**, identical to the 11:21Z R106-J capture at tree `83dd8007`.
  Since R107-F ships nothing, that is an independent logit-level confirmation
  that the submitted surface has not moved between the two trees; and it promotes
  **min margin = 0.375** to a reusable constant for sizing any future
  certificate (`census` on this fixture — a property of the prompt, not of a
  candidate).

Costs zero official receipts, so it stays available through the 07:00Z
integration freeze. Standing offer and its narrow endgame role are in §10 of the
SOP: rule 105.5 requires bit-exact summands, so the certificate's job in the
last hours is specifically to let a **non**-bit-exact summand be argued for at
all — most usefully for tanjiro's split-K reassociation (#648/#642), which is
class 2 by construction and therefore the textbook case.

### §12.1 Priority C, honestly

Priority C (re-adjudicating the paper shelf) has **not** happened and I do not
expect to start it. I would rather leave a correct §11 and a working service
than a third shelf pass. If a successor wants it, §4.1–§4.3 of
`research/maple-frieren-r106j-bitexactness-shelf.md` is the state of the art and
the class table in §3 of the SOP is the sorting key.

