# R87-A result — routed gate/up QMV head latency

Assignment `maple-r87-a-routed-qmv-head-latency`, revision `r87-a-rev1`, PR #469.
Branch `maple-tanjiro/r87-routed-qmv-head-latency`, base
`3217f111142346e004f41fae611a8bede172a659`.

Pre-registration: [`research/tanjiro-r87a-prereg.md`](tanjiro-r87a-prereg.md),
committed at `7e93b50` / amended at `502756c`, **both before any timing run**.
Every prediction in §6 of that file is scored HIT/MISS in §9 below.

<!-- VERDICT -->

---

## 1. Host, reachability, and what that licenses

| property | value |
| --- | --- |
| chip | Apple M4 Pro, 20 GPU cores |
| unified memory | 48 GiB (low-memory startup profile) |
| macOS | 26.5.2 |
| GPU family | `applegpu_g16s` (Apple GPU generation 16) |
| `_nax` selected? | **no** — gen 16 never selects `_nax` |
| decode kernel family reachable? | **yes** — decode is 100% `laguna_*`, and the
  kernel under test is the same `routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2`
  the ranked M5 dispatches |

This host is a legitimate **decode** screen for this kernel and is **not**
evidence for any `_nax` prefill change; this arm touches none. Occupancy-mediated
readings stay directional: the AGX table in advisor comment 5228399317 is a G13
static model and this is G16.

## 2. Rig, and the floor it can actually resolve

MLX dispatch profiler, local-only commit patching
`Vendor/mlx-swift/.../metal/device.{cpp,h}` — **neither file is in
`editablePaths`, and that commit is reverted before submission** (PR #73
precedent, pre-declared in prereg §4). Env `DARKBLOOM_GPU_PROFILE=1`,
`DARKBLOOM_GPU_PROFILE_SPLIT=1` (one dispatch per command buffer ⇒ per-kernel
attribution). Driver `research/decode_probe.py --steps 200 --profile`; step 0
discarded, 199 steady steps retained. `gpu_busy_sum == gpu_busy_union` to within
1 µs/step in every block below ⇒ **zero dispatch concurrency in decode**, so
per-kernel deltas transfer 1:1 to step deltas.

Every arm shares **one binary**: all knobs are read from the environment at
process start, so no arm carries a recompilation confound. Every campaign block
discards its position-0 run as a warm-up and uses a position-balanced palindrome
so arm and thermal position are decorrelated.

**Pre-registered floor.** `floor_95 = 1.96·√2·s/√199 = 0.19648·s` where `s` is
the *per-step* SD of the kernel's busy time, with a usability bar of
`floor_95 ≤ 10 µs/step`.

**Deviation, declared.** The profiler emits per-run aggregates over the 199
steady steps, not the per-step series, so `s` is not directly observable. I
substituted the **run-to-run** SD of the run means, which is *strictly more
conservative*: it contains the process-level offset that the per-step formula
omits. Prereg §4 anticipated exactly this ("the A/A also exposes run-to-run
offset that the formula does not capture"), so this is the quantity it wanted
reported, measured directly instead of derived.

**Measured on the touched kernel `..._r1_bf16_v2`, pooled over the 13 A0 runs
of the control and ceiling blocks:**

```
mean = 1501.88 us/step,  run-to-run SD = 3.51 us/step   (0.23% of the kernel total)

95% half-width of a two-arm difference:
  n=1/arm  +-9.73 us/step     <- pre-registered bar was <= 10; met even at n=1
  n=6/arm  +-3.97 us/step
  n=7/arm  +-3.68 us/step
```

**A/A false-positive check** (same binary, same knobs, different launches;
split-half of the A0 runs within each block):

| block | mean A (µs/step) | mean B | A/A difference | 95% half-width | verdict |
| --- | --- | --- | --- | --- | --- |
| control | 1503.60 (n=3) | 1501.20 (n=3) | **+2.40** | ±5.62 | inside — no false positive |
| ceiling | 1501.75 (n=4) | 1501.03 (n=3) | **+0.72** | ±5.26 | inside — no false positive |

The rig therefore does **not** manufacture an effect where none exists, and the
observed per-arm half-widths reported below (±2.96 to ±4.65) agree with the
±3.68 to ±3.97 predicted from the pooled A0 SD. All verdicts below are quoted
at n=6 or n=7 per arm.

## 3. Positive control — the barrier-injection arm

Block `research/r87a-runs/control`, 18 retained runs, n=6 per arm, arms
A0 / B2 / B4 (`DARKBLOOM_PROBE_ROUTED_GATEUP_BARRIERS`, `B` extra
`threadgroup_barrier(mem_flags::mem_none)` per k-loop trip ⇒ `4B` extra barriers
per threadgroup). Rule 33 confirmed from the trace: the dispatched names are
`..._v2` / `..._v2_b2` / `..._v2_b4`.

| arm | touched kernel Δ (µs/step) | untouched give-back | TOTAL busy_sum Δ |
| --- | --- | --- | --- |
| B2 vs A0 | **+9.13 ± 4.65** | −7.63 | +1.67 ± 26.29 |
| B4 vs A0 | **+8.52 ± 4.20** | −14.00 | −5.50 ± 24.63 |

**Rig verdict: the rig resolves what it needs to resolve.** The sign is correct,
the effect lands on exactly the kernel that was modified, and its 95% interval
excludes zero in both arms. The demonstrated resolution on the touched kernel is
**≈±4.2 µs/step at n=6**, which is smaller than every A1 effect the advisor's
prior contemplates.

**But the §5 gate as I wrote it FAILS, and I am reporting that rather than
quietly re-scoring it.** The gate required the `B=0→B=4` step to be positive
**and ≥3× floor_95** with **B=2 falling between**. Measured: 8.52 / 4.20 =
**2.03×**, not ≥3×; and B2 ≳ B4, i.e. the curve **saturates rather than
increasing monotonically**. The gate failed because my *prediction of barrier
cost was ~14× too large* (+120 µs/step predicted, +8.5 measured), not because
the instrument is blind. Those are different failures and only the second would
void A1.

### 3a. Why the control failed: a `threadgroup_barrier` is not a dispatch boundary

This block settles the inconsistency the advisor flagged in comment fb4 §2(b),
and it settles it against my own prereg arithmetic.

```
B=2  ⇒ 8 extra barriers per threadgroup
     ⇒ +9.13 µs/step spread over 39 R1 gate/up dispatches per step
     ⇒ 0.2341 µs per dispatch
     ⇒ 0.0293 µs per barrier per dispatch
```

Rule 41's calibrated dispatch-boundary slope is **1.3163–1.4964 µs per
dispatch-boundary**. The measured barrier cost is therefore **≈48× cheaper**
than a dispatch boundary. Moreover barriers **9 through 16** (the B2→B4 step)
cost **zero marginal time within the resolution of this rig** — the kernel is
bandwidth-bound at ~80% of peak (prereg §2 roofline) and has ample stall time to
absorb them.

**Conclusion to carry forward: rule 41's 1.3–1.5 µs slope is a property of the
no-op-*dispatch* variant and must not be applied to in-kernel synchronisation.**
An intra-kernel `threadgroup_barrier` on this kernel costs ~0.03 µs per
threadgroup-pass and saturates after ~8. I predicted +120 µs/step and measured
+8.5; the prior was wrong by more than an order of magnitude and the correction
belongs in the shared rule set, not just in this PR.

## 4. A1 ladder — the submittable arm

<!-- LADDER -->

## 5. A2 ceiling probe — deliberately incorrect, timing only, never a candidate

Block `research/r87a-runs/ceiling`, 14 retained runs, n=7 per arm, arms A0 / E0
(`DARKBLOOM_PROBE_ROUTED_EXPERT0_PF=1`: block-0 weight/scale address computation
and loads hoisted above the routing prelude with `expert` hardcoded to 0).
Rule 33 confirmed: dispatched name is `..._v2_e0`. No correctness gate was run
against this arm, no golden hash is reported from it, and it is **never
submitted**.

| quantity | value (µs/step) |
| --- | --- |
| touched kernel `..._v2_e0` | **−83.64 ± 2.96** (ref 1501.44, 17.54% of decode) |
| untouched give-back | **+14.13** |
| give-back fraction | **16.9%** — well under the 42% of PR #457 |
| TOTAL busy_sum | **−69.71 ± 36.21** |
| TOTAL busy_union | −69.57 ± 35.38 |
| wall | −64.71 ± 116.43 (inflated by profiler `fputs`; not admissible) |

Discounted per the 42% give-back law (×0.60): **≈−50 µs/step end-to-end
≈ +0.77% score**. That is an **upper bound on the whole head-latency family**,
obtained by breaking correctness; it is what a hypothetical mechanism that
removed the router→weight-address dependency entirely could be worth.

**Prereg scoring: HIT for both priors.** Advisor prior −60 kernel-local
[−15, −180] ⇒ HIT. My prediction −45 kernel-local ⇒ HIT (measured −83.64 is
inside my [−5, −150] interval).

**Attribution caveat (PR #475).** The router kernel
`residual_rms_router_bf16_2048_rpg8_keys_v1` moved only **+0.71 ± 1.59
µs/step** — i.e. removing the router→address dependency did *not* shift cost
into the router kernel. The −83.64 is genuinely latency recovered inside the
QMV kernel, not work migrated to a neighbour. The two largest untouched movers
are `decode_nvfp4_qkv_h64...` (+3.53 ± 7.87) and `oproj_act_h64...`
(+3.63 ± 6.34), both with intervals spanning zero, consistent with the
power/clock-redistribution explanation rather than displaced work.

## 6. Occupancy — `maxTotalThreadsPerThreadgroup` for every variant

Read directly from `MTLComputePipelineState` at pipeline creation (the profiler
patch prints `GPUPSO <name> maxThreads= execWidth= tgMem=`).

| arm | dispatched kernel name suffix | maxThreads | execWidth | tgMem |
| --- | --- | --- | --- | --- |
| A0 | *(none)* | 1024 | 32 | 0 |
| B2 | `_b2` | 1024 | 32 | 0 |
| B4 | `_b4` | 1024 | 32 | 0 |
| E0 | `_e0` | 1024 | 32 | 0 |
<!-- OCCUPANCY_PF -->

Read against the comment-5228399317 AGX table (52→1024, 56→896, 64→832,
68→768, 72→704, 80→640, 92→576, 104→512, 116→448, 128→384; ALU saturates at
768): **every variant sits in the top tier**, i.e. ≤52 registers per thread, and
no variant drops a tier. The packed `vec<bfloat,4> pf_in[4]` staging (8 GPRs)
did not cost an occupancy tier, and neither did the barrier or ceiling probes.
There is therefore **no occupancy-mediated explanation available** for any
result in this PR — the ladder must be read as pure latency/MLP, which is what
the pre-registration wanted the measurement to isolate.

## 7. Correctness

<!-- CORRECTNESS -->

## 8. Byte accounting

`Sources/MLXFastModel/LagunaRuntimeModel.swift`, the only submitted file
changed:

| | bytes |
| --- | --- |
| base `3217f111` | 510,964 |
| branch head | 515,667 |
| growth | **+4,703** |
| per-file cap | 524,288 |
| **remaining per-file headroom** | **8,621** |

`senpai/check-editable-budget.sh 3217f111142346e004f41fae611a8bede172a659` on the
branch head:

```
editable budget OK: current=2895592/3000000 bytes headroom=104408 growth=4703/262144 files=140 (base=140)
```

Repo budget **GREEN**, per-submission growth **GREEN** (4,703 of 262,144), file
count unchanged at 140. Prereg §9 budgeted ≈2.3 KB and the actual spend is
4.7 KB; the overrun is the generator-conversion boilerplate plus the MSL
verification anchors, and it still leaves 8.6 KB of per-file headroom.

## 9. Pre-registration scorecard

<!-- SCORECARD -->

## 10. Reproduction

```bash
# one campaign block (position 0 is a discarded warm-up)
bash research/tanjiro-r87a-campaign.sh <block> <arm>...      # arms: A0 PF1 PF2 PF3 B2 B4 E0

# aggregate
python3 research/tanjiro-r87a-stats.py research/r87a-runs/<block> \
  --ref A0 --drop-warmup --min-share 1.0 \
  --touched routed_nvfp4_swiglu_qmv_packed_top8keys \
  --json research/r87a-runs/<block>.json

# MSL equivalence of the default path against stock
bash research/tanjiro-r87a-verify-msl.sh

# W&B
python3 research/tanjiro_r87a_wandb_log.py \
  --block control=research/r87a-runs/control.json \
  --block ladder=research/r87a-runs/ladder.json \
  --block ceiling=research/r87a-runs/ceiling.json \
  --verdict "..."
```

Blocks actually run:

```
control: A0 | A0 B2 B4 B4 B2 A0 A0 B2 B4 B4 B2 A0 A0 B2 B4 B4 B2 A0
ceiling: A0 | A0 E0 E0 A0 A0 E0 E0 A0 A0 E0 E0 A0 A0 E0
ladder : A0 | A0 PF1 PF2 PF3 PF3 PF2 PF1 A0 A0 PF1 PF2 PF3 PF3 PF2 PF1 A0 A0 PF1 PF2 PF3 PF3 PF2 PF1 A0
```

(the run left of the `|` is the discarded position-0 warm-up)

## 11. Suggested follow-ups (not implemented)

1. **Retire the barrier-cost prior in the shared rule set.** §3a measures
   0.0293 µs per in-kernel `threadgroup_barrier` per dispatch on this kernel,
   saturating after ~8 barriers. Rule 41's 1.3163–1.4964 µs slope is a
   *dispatch-boundary* cost and applying it to in-kernel synchronisation
   overestimates by ~48×. Any future arm whose cost model is "add a barrier" or
   "remove a barrier" should be re-priced against 0.03 µs, which will kill some
   ideas and revive others.

2. **The A2 ceiling is the real prize and it is not yet claimable.** −83.6 µs/step
   kernel-local (≈−50 end-to-end, ≈+0.77% score) sits behind the
   router→weight-address dependency. A *correct* mechanism would need the
   top-8 expert ids available before the QMV dispatch — e.g. computing routing
   in the preceding `residual_rms_router_*` dispatch and passing expert ids as a
   buffer, so the QMV kernel's block-0 weight addresses are loadable at
   instruction 0. That is the un-fusion idea gated on #462, and this measurement
   *raises* its expected value rather than lowering it. Note §5's attribution
   check: the router kernel absorbed only +0.71 µs/step, so the saving is real
   recovery, not migration.

3. **A2 leaves the give-back law looking kernel-specific.** PR #457 gave back
   42%; this arm gave back 16.9% on a larger absolute saving. A give-back
   fraction that varies 2.5× between arms is not a constant to multiply by. It
   would be worth one dedicated study of whether give-back scales with the
   *number of distinct kernels* a diff perturbs rather than with the size of the
   saving.

4. **Port the winning A1 variant to the `:7566` `_v1` generator** only if A1 is
   promoted (prereg §7). `DARKBLOOM_ROUTED_GATEUP_R1` is default ON, so `:7566`
   is a dead fallback and duplicating a mechanism into it spends per-file
   headroom on unmeasurable code.
