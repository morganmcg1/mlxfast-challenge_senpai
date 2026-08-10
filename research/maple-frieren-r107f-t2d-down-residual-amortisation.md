# R107-F — T2d routed+shared down+residual: output-row amortisation

**Student** maple-frieren · **PR** #597 · **revision** `r105-b-rev6` ·
**base** `2454cc01ea3afabac067f0a271e36901fea7d21c` · **host** AWS M4 Pro,
Apple GPU generation 16, 20 cores, measured DRAM ceiling 260.2 GB/s.

Every M5 figure quoted from the state-doc pool table (§B.0.3, lines 1685–1705)
carries its mandatory provenance label verbatim:
**`α = 0.4369, β = 0.5 two-pool map, residual −6.63 %, #561`**.

---

## §0 Outcome

**`PENDING`** — filled at the end of Stage 1 or Stage 2. The permitted vocabulary
is fixed in §2.7 below and may not be extended after the fact.

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
