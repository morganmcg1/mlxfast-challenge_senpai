# R87-A result — routed gate/up QMV head latency

Assignment `maple-r87-a-routed-qmv-head-latency`, revision `r87-a-rev2`, PR #469.
Branch `maple-tanjiro/r87-routed-qmv-head-latency`, base
`3f430f6f17ac4bfbac5f47767ca78cb89d84a760`. The measurement campaign in §1–§13
was run against the earlier base `3217f111142346e004f41fae611a8bede172a659`;
see §14 for what rev2 changed and why no number moved.

Pre-registration: [`research/tanjiro-r87a-prereg.md`](tanjiro-r87a-prereg.md),
committed at `7e93b50` / amended at `502756c`, **both before any timing run**.
Every prediction in §6 of that file is scored HIT/MISS in §9 below.

## Verdict — **NO-GO on A1. The hypothesis is refuted, not merely unresolved.**

| | |
| --- | --- |
| A1 (submittable input-prefetch ladder) | **HARMFUL.** Best arm +26.47 µs/step kernel-local, worst +105.80. All three arms are regressions at 3–30× the rig floor. |
| Shipped surface | **Zero bytes of `Sources/` change** as of rev2. The three probe knobs are reverted and preserved as `research/tanjiro_r87a_probes.patch`; `git diff` against the base over the submitted surface is empty (§14a). |
| A2 (deliberately incorrect ceiling probe) | **−83.64 ± 2.96 µs/step** kernel-local, quoted at face value per rule 43. The SPLIT=1 census total was −69.71 ± 36.21 µs/step; the two bracket **≈+1.07% to +1.28% score**. No give-back discount is applied. **Confounded** — the probe also cuts ~22% of DRAM bytes, so this is a *loose* upper bound, not a target. See §5a. |
| Correctness | **Clean.** `--local-iterate` at default: `passed=true`, `passed_correctness=true`, `max_abs_diff=0`, 130/130 checked steps, `golden_hash b9509697…` matching this host's known-good value, with `MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT` unset (§7b). Upstream-equivalence oracle byte-identical across candidate-default, candidate-`PF=1`, and a base-`3217f111` control (§7a). |
| Merge recommendation | **Do not merge as a speedup.** With a zero-byte submitted surface, a merge carries only `research/` documentation and costs nothing in editable budget; close instead if the advisor prefers. Decide on the value of the negative result, the barrier-cost scope limit, the A2 bound, and §13a. |

Three things in this PR are worth more than the failed hypothesis:

1. **A `threadgroup_barrier` is not a dispatch boundary.** Measured
   0.0293 µs per barrier per dispatch versus rule 41's 1.3163–1.4964 µs
   per *dispatch* boundary. This is a **scope limit** on rule 41, not a
   correction to it: rule 41 prices a per-dispatch-boundary event and my
   measurement says in-kernel barriers are not that event. Barriers 9–16
   cost nothing marginal. (§3a)
2. **The head-latency ceiling is ≈+1.07% to +1.28% score and it is real** —
   the router kernel absorbed only +0.71 ± 1.59 µs/step, so the recovery is
   latency removed, not work migrated. (§5)
3. **My ceiling data independently fail to support the 42% give-back law.**
   The measured total/touched ratio here is 0.833 ± 0.433 → [0.401, 1.266],
   which contains 1.0 (no give-back) as comfortably as it contains 0.58.
   PR #473 has since shown the give-back was an artefact of
   `DARKBLOOM_GPU_PROFILE_SPLIT=1` itself, and rule 43 now forbids any
   SPLIT=1 total or ratio from entering a standing rule. This section is
   retained as corroborating evidence, not as a new law. (§11)

### Rule 43 compliance

Every decision in this document is carried by **per-kernel attribution under
`DARKBLOOM_GPU_PROFILE_SPLIT=1`**, which rule 43 explicitly preserves. No
SPLIT=1 *total* or ratio is load-bearing:

- The NO-GO on A1 rests on per-kernel deltas of +26.47 to +105.80 µs/step
  against a per-kernel σ of 3.51 — a 7–30× margin. The SPLIT=1 totals for those
  arms are not used.
- The A2 ceiling is quoted at face value on the touched kernel (−83.64 ± 2.96),
  with the SPLIT=1 census total shown only as a bracket and labelled as such.
- No `nat`-regime paired ABBA census was run, and none is claimed. A2 is a
  deliberately incorrect probe that can never be submitted; a real candidate in
  this family owes that census before any merge decision.
- The end-to-end wall numbers here have σ ≈ 116 under SPLIT=1 and are marked
  inadmissible throughout, which is the same failure mode PR #473 diagnosed.

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

**Naming the estimator (rule 40, third form).** σ is a property of the
estimator, not of the rig, so every floor above is labelled:

| estimator used here | σ (µs/step) | where it applies |
| --- | --- | --- |
| cross-process, per-run **per-kernel** busy label, `_r1_bf16_v2` | **3.51** | §3, §4, §5 per-kernel verdicts |
| cross-process, per-run **`busy_sum` TOTAL** under SPLIT=1 | **17.11** (18 control runs) | §5 census total only |

The SPLIT=1 total is ~5× more dispersed than the per-kernel labels measured in
the same runs. That ordering is consistent with PR #473's finding that the
split itself is expensive and noisy, and it is why every decision in this
document rests on the per-kernel column.

## 3. Positive control — the barrier-injection arm

Block `research/r87a-runs/control`, 18 retained runs, n=6 per arm, arms
A0 / B2 / B4 (`DARKBLOOM_PROBE_ROUTED_GATEUP_BARRIERS`, `B` extra
`threadgroup_barrier(mem_flags::mem_none)` per k-loop trip ⇒ `4B` extra barriers
per threadgroup). Rule 33 confirmed from the trace: the dispatched names are
`..._v2` / `..._v2_b2` / `..._v2_b4`.

| arm | touched kernel Δ (µs/step) | untouched sum Δ | TOTAL busy_sum Δ (SPLIT=1) |
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

**Conclusion to carry forward — a scope limit, not a refutation. Rule 41's
1.3–1.5 µs slope is a correctly calibrated price for a *dispatch boundary*;
this measurement only establishes that an in-kernel barrier is not one.**
Rule 41 stands as written. An intra-kernel `threadgroup_barrier` on this kernel
costs ~0.03 µs per threadgroup-pass and saturates after ~8. I predicted
+120 µs/step and measured +8.5; my own prior was wrong by more than an order of
magnitude, and what belongs in the shared rule set is the boundary of rule 41's
applicability, not a change to its slope.

## 4. A1 ladder — the submittable arm

Block `research/r87a-runs/ladder` → `research/r87a-runs/ladder.json`, 25 runs,
position 0 discarded as warm-up, 24 retained, **n=6 per arm**, interleaved
A0/PF1/PF2/PF3 with a mirrored order inside each group of eight so that any
monotone thermal drift cancels. `DARKBLOOM_ROUTED_GATEUP_INPUT_PF` is a
2-bit knob: bit0 = steady-state staging of the next iteration's activation
tile into registers inside the K loop, bit1 = preamble hoist of the first
tile above the routing prelude.

Rule 33 was verified on every run: the dispatched kernel name carried
`_pfin1` / `_pfin2` / `_pfin3` exactly as the arm demanded, so each arm
provably executed a *different* compiled kernel and not the stock one.

| arm | bits | touched kernel Δ (µs/step) | untouched Δ | TOTAL busy_sum Δ |
| --- | --- | --- | --- | --- |
| PF1 steady | `1` | **+98.62 ± 3.33** | +7.25 | **+108.50 ± 36.09** |
| PF2 preamble | `2` | **+26.47 ± 4.02** | +12.88 | **+40.17 ± 16.69** |
| PF3 both | `3` | **+105.80 ± 2.85** | −0.95 | **+107.33 ± 22.82** |

Reference: A0 touched kernel 1499.6 µs/step, 17.53% of decode busy time.
Arm busy_sum means: A0 8555.7 ± 9.8, PF1 8664.2 ± 35.9, PF2 8595.8 ± 15.4,
PF3 8663.0 ± 22.1 µs/step.

**Every A1 variant is a regression, and by a margin 3–30× the rig floor
(±9.73 at n=1, ±3.97 at n=6).** This is not a null result that a bigger n
could rescue; the sign is unambiguous and the smallest effect (PF2, +26.47)
is 6.7 floor-widths from zero. Recommended default for the shipped knob is
therefore **`0` (off)**, which is what it is set to.

### Why input prefetch hurts here

The pre-registration assumed the routed gate/up QMV kernel had spare issue
slots at the head of each K iteration that a staged activation load could
fill. The measurement says the opposite: this kernel is already running a
software pipeline over the **weight** stream at roughly 80% of DRAM peak, and
inserting a second outstanding load stream for the activation tile competes
with it. The in-loop variant (PF1, +98.62) is **3.7× worse** than the
preamble-only variant (PF2, +26.47), exactly the ordering you expect if the
damage is per-iteration interference with the weight prefetch rather than a
one-off setup cost.

Two independent observations support power/clock redistribution rather than
displaced work as the source of the untouched-kernel movement:

- PF3 (+105.80) is **not** PF1 + PF2 (+125.09). The deficit, 19.3 µs/step, is
  ~5 floor-widths, so the two mechanisms are not additive — they contend for
  the same resource.
- `gate_sp_h64_v1`, an untouched kernel, moved **−7.83 (PF1) / −6.98 (PF3)**.
  That is the *inverse sign* of the +8.14 the same kernel showed in PR #457,
  which is what a shared power/clock budget predicts and what displaced work
  does not.

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
| untouched sum, opposite sign | **+14.13** |
| TOTAL busy_sum (SPLIT=1) | **−69.71 ± 36.21** |
| TOTAL busy_union (SPLIT=1) | −69.57 ± 35.38 |
| wall | −64.71 ± 116.43 (inflated by profiler `fputs`; not admissible) |

**Quoted at face value, per rule 43 and the advisor's explicit instruction not
to discount.** At 0.015280 % score per µs/step of decode:

| basis | Δ µs/step | score |
| --- | --- | --- |
| touched kernel only (per-kernel attribution, σ=3.51) | −83.64 | **+1.278%** |
| SPLIT=1 census total (σ=17.11, attribution-only under rule 43) | −69.71 | +1.065% |

The decision-grade number is the first row: rule 43 permits per-kernel
attribution under SPLIT=1 and forbids a SPLIT=1 *total* from carrying a rule or
a merge. The second row is shown only to bracket the first. A `nat`-regime
paired ABBA census (rule 43's required instrument) was **not** run for this
arm, because A2 is a deliberately incorrect probe that is never submitted; a
real candidate in this family would need one.

Either way this is an **upper bound on the whole head-latency family**,
obtained by breaking correctness.

**Ratio check against the withdrawn give-back law.** `total/touched =
69.71/83.64 = 0.833 ± 0.433 → [0.401, 1.266]`. The interval contains 1.0, so
these data do **not** support a 0.58 give-back factor; they are also too wide
to reject it on their own. PR #473's `c = 1.247 [0.90, 1.59]` settles it, and
rule 43 supersedes the law. Recorded here as an independent, same-signed
observation, not as a competing estimate.

### 5a. The A2 number is confounded — read it as a loose upper bound, not a target

Hardcoding `expert = 0` for the block-0 addresses does not only remove the
`router_keys → tournament → expert → address` dependency. It also makes the
block-0 weight/scale loads **identical across all 8 expert slots**, so the
probe silently deduplicates DRAM traffic:

```
block 0 is 1 of 4 k-blocks  ⇒  25% of weight bytes
those bytes collapse 8-way  ⇒  0.75 + 0.25/8 = 0.781
                            ⇒  ~22% fewer DRAM bytes per dispatch
```

So the −83.64 is the **sum** of (i) the removed address dependency and
(ii) ~22% less DRAM traffic. A correct mechanism that removes only (i) must
land below it. I did not separate the two, and I should have designed the
probe to hold bytes constant (e.g. by hardcoding a *different* expert per
slot, which preserves the 8-way distinctness while still cutting the
dependency). **This is a design flaw in my own ceiling probe and it weakens
the headline number.**

Two things partly rescue the reading. First, ~22% fewer bytes bought only
5.6%, which is far less than a bandwidth-bound kernel would give back — so
bytes were *not* the binding constraint here, and most of the gain is
plausibly latency. Second, §5's attribution check still holds: the router
kernel absorbed only +0.71 ± 1.59 µs/step, so nothing migrated. But the
honest statement is: **the dependency-only ceiling is somewhere below
−83.64 µs/step kernel-local, and I have not bounded it from below.** Treat the
≈+1.28% score as optimistic — the confound, not a give-back discount, is the
reason to hold it loosely.

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
| PF1 | `_pfin1` | 1024 | 32 | 0 |
| PF2 | `_pfin2` | 1024 | 32 | 0 |
| PF3 | `_pfin3` | 1024 | 32 | 0 |

Read against the comment-5228399317 AGX table (52→1024, 56→896, 64→832,
68→768, 72→704, 80→640, 92→576, 104→512, 116→448, 128→384; ALU saturates at
768): **every variant sits in the top tier** and no variant drops a tier. The
packed `vec<bfloat,4> pf_in[4]` staging (8 GPRs) did not cost an occupancy
tier, and neither did the barrier or ceiling probes.

**Explicit limitation — this metric is ceiling-truncated.** The top tier
covers everything from 1 to 52 registers per thread, so `maxThreads=1024`
proves only that no variant crossed 52 registers. It cannot distinguish, say,
32 registers from 52, and Apple's dispatch may still schedule fewer resident
simdgroups for the higher-pressure variant for reasons the pipeline object
does not expose. So this is evidence that **no occupancy *tier* change**
explains the ladder — it is **not** proof that no occupancy-mediated effect
exists at all. Ruling that out would need a register-count readout the Metal
API does not provide on this host. The remaining latency/MLP reading of §4 is
the most likely explanation, not a proven-by-elimination one.

## 7. Correctness

### 7a. Upstream-equivalence oracle — three arms, one identical report

Run through `research/run_upstream_equivalence.sh`, which uses the bare filter
`lagunaRuntimeMatchesVendoredUpstreamOnM5WhenEnabled`, repairs the debug
metallib from the worker build, and refuses to call a zero-test invocation a
pass. **Every invocation below executed exactly 1 test** (`Test run with 1 test
in 0 suites`), so none of these is a vacuous pass.

| arm | `Sources/` state | `EQUIVALENCE_EXACT_STEPS` | report SHA-256 (first 16) | log |
| --- | --- | --- | --- | --- |
| candidate, knob unset (**what ships**) | branch | 8 / 9 | `ac16b3a2c8c60a37` | `research/r87a-runs/equivalence/candidate-default.log` |
| candidate, `DARKBLOOM_ROUTED_GATEUP_INPUT_PF=1` | branch | 8 / 9 | `ac16b3a2c8c60a37` | `.../candidate-pf1.log` |
| **base control**, `3217f111` | base file restored | 8 / 9 | `ac16b3a2c8c60a37` | `.../base-3217f111.log` |

The base control was produced by checking out
`3217f111:Sources/MLXFastModel/LagunaRuntimeModel.swift` into the worktree, so
`git diff 3217f111 HEAD -- Sources/ Vendor/` was empty for that run, then
restoring the candidate. This is a control against the *current* base, not
against a historically recorded artefact from an older base.

**All three reports are byte-identical.** The single non-exact step is the
known M4 / Apple-GPU-generation-16 **prefill-only** artefact:

```
prefill    maximumAbsoluteLogitError 0.125   meanAbsoluteLogitError 0.011933609
           runtimeToken 5991 == upstreamToken 5991
decode-0..7  maximumAbsoluteLogitError 0     meanAbsoluteLogitError 0    (all 8 exact)
```

`EQUIVALENCE_EXIT=1` on all three arms, including the unchanged base. The
oracle's tolerance is a hard `0.0` and this host cannot meet it in prefill even
with zero edits, which is exactly the situation §1 describes: gen-16 does not
select the `_nax` prefill kernels the M5 uses. **The exit code is a property of
the host, not of this change** — proven by the base control sharing it
digit-for-digit.

**Prereg C4 (A1 arms bit-exact): HIT.** The PF=1 report is identical to base.
The stronger evidence is on the scored path: all 25 ladder runs reported
`0 divergences (all match)` from `research/decode_probe.py`, which checks
teacher-forced greedy argmax equality against a fixed golden sequence over
200 decode steps, and rule 33 confirmed each run dispatched the intended
`_pfin*` kernel. Caveat: the oracle run at PF=1 was not independently
name-verified, so the ladder probes — not the oracle — carry that claim.

**Prereg C5 (M4 prefill artefact digit-identical to base): HIT.**

### 7b. Full harness gate — `./benchmark.sh --local-iterate`

Run at the **default knob setting** (`DARKBLOOM_ROUTED_GATEUP_INPUT_PF` unset,
i.e. mode `0`), with `MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT` **explicitly unset** via
`env -u`. No local override of any kind was in effect: this is the unrelaxed
gate.

```
env -u MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT ./benchmark.sh --local-iterate
# job dd077977-8094-4aad-a6a5-3a19ba3804ef, exit 0, 257.5 s wall
```

| field | value |
| --- | --- |
| `passed` | **true** |
| `passed_correctness` | **true** |
| `max_abs_diff` | **0** |
| `checked_steps` | **130** of 130 (`checked_tokens=130 decode_steps=128 repeats=1`) |
| `first_failing_case` / `_layer` / `_step` | `null` / `null` / `null` |
| `error` | `""` (empty) |
| `golden_hash` | `b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63` |
| `weights_hash` | `aff994300573c5e8589563fc9ff57cdcfb1ef9b49e14898be290a75a6b294b3d` |
| `harness_hash` | `a1fc0e0274710a8f24fc49d1c3a41d778a8965606c67719acd69929a9294bf6d` |
| `num_layers` | 40 |
| `peak_ram_gb` | 21 |
| `score` (local estimate only) | 0.8004893781120298 |
| `decode_seconds_per_token` | 0.012886406578125 |
| `prefill_seconds_per_token` | 0.00111274601171875 |
| `commit` | `098e6f3` |
| `timestamp` | 2026-08-08T23:40:48Z |

That `golden_hash` is character-for-character the value this host family has
produced on every prior unmodified run I have receipts for
(`research/pr270-logs/f1-iterate.{on,off}.json`,
`research/maple-tanjiro-pr81-metal-byte-reclaim.md` §4.1). The tripwire is
therefore matching a *known* golden, not merely self-consistent.

**Do not read the `score`, `decode_speedup`, or `prefill_speedup` fields as
evidence for anything.** `--local-iterate` divides by pinned M5 calibration
constants, so on this M4 Pro the reported `prefill_speedup 0.33x` and the
consequent `passed_prefill_speedup_floor: false` are host artefacts of the
denominator. `research/pr270-logs/f1-iterate.off.json` — an unrelated,
unmodified run on this same host family — records
`prefill_speedup 0.3227638986245973`, `passed_prefill_speedup_floor: false`,
and `passed: true`, i.e. exactly the same artefact with no candidate change
present at all. It is not a candidate regression. The only rows I am claiming
from this run are the correctness rows.

Against the pinned local baseline file the harness prints
`decode 0.013134 -> 0.012886 s/token (-1.9%)`. That comparison is **stale and
not evidence**: the baseline file predates this base, and the run is a single
unpaired sample against a cross-session reference, which the campaign rules and
my own rig work (§2, cross-process σ ≈ 48 µs/step) both forbid treating as a
measurement. The A1 verdict rests on the paired ladder in §4, not on this line.

## 8. Byte accounting

**As shipped in rev2 the submitted spend is zero** — see §14a. The table below
records what the rev1 measurement build cost, because that is the number a
follow-up needs when it re-applies `research/tanjiro_r87a_probes.patch`.

`Sources/MLXFastModel/LagunaRuntimeModel.swift`, the only submitted file changed
in rev1:

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

Every row below was written down in `research/tanjiro-r87a-prereg.md` and
committed at `7e93b50` / `502756c`, **before the first timing run**. Nothing
here was chosen after seeing data.

| # | pre-registered prediction | interval | measured | verdict |
| --- | --- | --- | --- | --- |
| 1 | A1 steady, end-to-end | −6 [+8, −30] | **+108.50** | **MISS** |
| 2 | A1 preamble, end-to-end | −4 [+5, −20] | **+40.17** | **MISS** |
| 3 | A1 both, end-to-end | −9 [+8, −38] | **+107.33** | **MISS** |
| 4 | A2 ceiling, kernel-local (advisor prior) | −60 [−15, −180] | **−83.64** | **HIT** |
| 5 | A2 ceiling, kernel-local (my prior) | −45 [−5, −150] | **−83.64** | **HIT** |
| 6 | Control B0→B4, kernel-local | +120 [+30, +400] | **+8.52** | **MISS** |
| C1 | \|steady\| ≥ \|preamble\| | — | 98.62 vs 26.47 | **HIT** on magnitude, sign wrong |
| C2 | both ≈ steady + preamble within floor_95 | ±4 | 105.80 vs 125.09 (Δ 19.3) | **MISS** |
| C3 | `maxThreads` unchanged across all variants (75% conf.) | — | 1024 everywhere | **HIT** (see §6 truncation caveat) |
| C4 | A1 arms bit-exact, `max_abs_diff = 0` | — | all 25 ladder runs `0 divergences`; decode-0..7 exactly 0 (§7a) | **HIT** |
| C5 | M4 prefill artefact digit-identical to base | — | `max 0.125 / mean 0.011933609 / token 5991==5991`, identical to base control (§7a) | **HIT** |
| C6 | A2 recovery ≥ 4× the best A1 recovery | — | no A1 arm produced *any* recovery | **HIT** (unbounded) |

Rows 1–3 were pre-registered in end-to-end terms, so the "measured" column
quotes the SPLIT=1 totals for comparability with what was written down. Under
rule 43 those totals cannot carry a decision, and they do not: the same three
arms are regressions of +26.47 to +105.80 µs/step on the touched kernel alone
(§4), against a per-kernel σ of 3.51. The MISS verdicts hold on the per-kernel
column by themselves.

All twelve rows are now scored: **five MISS (1, 2, 3, 6, C2), six HIT
(4, 5, C3, C4, C5, C6), one partial (C1)** — and the three
headline predictions are all MISSes with the wrong sign. That is the honest
shape of this result. The two prior-elicitation questions the advisor asked
are answered as follows:

- **Was the direction of the A1 effect predictable?** No. Both the advisor's
  and my priors put the steady-state variant at a modest *gain*; it is the
  single largest regression in the block. The prior rested on an assumption
  about spare issue slots that the measurement refutes.
- **Was the magnitude of the control predictable?** No, and the reason
  generalises. Prediction #6 was 14× the measured value because I applied rule
  41's dispatch-boundary cost to a `threadgroup_barrier`. Rule 41 is fine; my
  use of it was outside its scope. See §3a.

## 10. Reproduction

The arm knobs no longer exist on this branch (§14a). Re-create them first:

```bash
git checkout -b r87a-replay 3217f111142346e004f41fae611a8bede172a659
git checkout maple-tanjiro/r87-routed-qmv-head-latency -- research/
git apply research/tanjiro_r87a_probes.patch
```

Then:

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

# correctness: upstream-equivalence oracle (three arms, see 7a)
bash research/run_upstream_equivalence.sh

# correctness: full harness gate, no drift override (see 7b)
env -u MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT ./benchmark.sh --local-iterate

# W&B
python3 research/tanjiro_r87a_wandb_log.py \
  --block control=research/r87a-runs/control.json \
  --block ladder=research/r87a-runs/ladder.json \
  --block ceiling=research/r87a-runs/ceiling.json \
  --gate research/r87a-runs/gate/score.local-iterate.json \
  --verdict "..."
```

Blocks actually run:

```
control: A0 | A0 B2 B4 B4 B2 A0 A0 B2 B4 B4 B2 A0 A0 B2 B4 B4 B2 A0
ceiling: A0 | A0 E0 E0 A0 A0 E0 E0 A0 A0 E0 E0 A0 A0 E0
ladder : A0 | A0 PF1 PF2 PF3 PF3 PF2 PF1 A0 A0 PF1 PF2 PF3 PF3 PF2 PF1 A0 A0 PF1 PF2 PF3 PF3 PF2 PF1 A0
```

(the run left of the `|` is the discarded position-0 warm-up)

**W&B record.** Canonical run `5fmnrvvy` —
<https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/5fmnrvvy>
(entity `wandb-applied-ai-team`, project `mlxfast-maple`). It carries the arm
tables, per-kernel delta tables, and score conversion for all three blocks,
plus the `gate/*` correctness summary keys from §7b
(`gate/passed_correctness`, `gate/max_abs_diff`, `gate/checked_steps`,
`gate/golden_hash`, `gate/golden_drift_override = "unset"`).

An earlier run `d0ufnmht` logged the same three blocks before the correctness
evidence existed; it is superseded by `5fmnrvvy` and is retained only for
provenance.

## 11. Suggested follow-ups (not implemented)

1. **Record the scope boundary of rule 41 in the shared rule set.** §3a measures
   0.0293 µs per in-kernel `threadgroup_barrier` per dispatch on this kernel,
   saturating after ~8 barriers. Rule 41's 1.3163–1.4964 µs slope remains
   correct for what it prices — a *dispatch boundary* — but it is ~48× too
   expensive as a proxy for in-kernel synchronisation. Any future arm whose cost
   model is "add a barrier" or "remove a barrier" should be re-priced against
   0.03 µs, which will kill some ideas and revive others. Nothing here asks for
   rule 41's slope to change.

2. **The A2 ceiling is the real prize and it is not yet claimable.** −83.6 µs/step
   kernel-local at face value (≈+1.28% score; SPLIT=1 census total −69.7
   ⇒ +1.07%; and see §5a: loose) sits
   behind the router→weight-address dependency. Note §5's attribution check:
   the router kernel absorbed only +0.71 µs/step, so what was recovered was
   recovered, not migrated. Ranked correct mechanisms, cheapest first:

   a. **Reuse the top-8 ids the selector kernel already computes.** A selector
      already runs every layer for the down path
      (`LagunaRuntimeModel.swift:10743`, `:9313` ff.). Passing its indices into
      the gate/up QMV as a buffer removes the tournament from the QMV entirely
      and makes block-0 addresses loadable at instruction 0. This is a ~5-line,
      bit-exact experiment whose only new cost is the dispatch ordering between
      the two kernels — and §3a says in-kernel synchronisation is nearly free.
      **This should be the next assignment; it prices the whole design fork for
      almost nothing.**
   b. **Flatten the in-kernel tournament** (lane-local presort, heads-only
      rounds, `uint4` key loads) — order 30–55 µs, bit-exact provided the
      comparator stays a strict total order, and it needs no cross-kernel
      change at all. Good fallback if (a) is blocked.
   c. **Slot-major multi-slot threadgroups**, amortising one prelude over
      several expert slots. Highest ceiling, but it changes threadgroup
      geometry, which §1 says can flip sign between M4 and M5 core counts — so
      it needs an M5 receipt, not an M4 result.

   Two things to *stop* considering. **Guessing an expert to warm the memory
   system is negative-EV**: at 80% of DRAM peak a wasted 8.39 MB fetch costs
   more than the stall it hides, and there is no in-invocation predictor better
   than 1/32. **Merging the routed and shared dispatches is already known
   exact-but-negative** (`LagunaRuntimeModel.swift:9436–9440`).

   One correction to the framing this PR started from: 83.6 µs/step over 39
   dispatches is 2.14 µs/dispatch, which is 3–4× what a single prelude latency
   per dispatch can explain. The stall therefore recurs at every threadgroup
   turnover — it is a memory-level-parallelism loss across the dispatch, not a
   one-time wave-ramp. Mechanisms that only fix the *first* wave will
   underdeliver.

3. **A2 corroborates PR #473's retraction of the give-back law — no new study
   needed.** My ratio `total/touched = 0.833 [0.401, 1.266]` contains 1.0, so
   these data never supported a 0.58 factor either. PR #473 has since shown the
   effect was an artefact of `DARKBLOOM_GPU_PROFILE_SPLIT=1`, and rule 43
   replaces the discount with a `nat`-regime paired ABBA census. I withdraw the
   "kernel-specific give-back" study I would otherwise have proposed here: it
   would have been chasing profiler overhead. The residual open question is the
   narrower and cheaper one in follow-up 2 — whether a *correct* head-latency
   mechanism reproduces any part of −83.6 under a `nat`-regime census.

4. **Port the winning A1 variant to the `:7566` `_v1` generator** only if A1 is
   promoted (prereg §7). `DARKBLOOM_ROUTED_GATEUP_R1` is default ON, so `:7566`
   is a dead fallback and duplicating a mechanism into it spends per-file
   headroom on unmeasurable code.

## 12. Reply to the power analysis in advisor feedback fb3

fb3 argued this experiment was underpowered and predicted I would come back
with an uninformative null. That prediction did not come true, and it is worth
being precise about why, because the disagreement is entirely about **which
estimator the effect was measured against** — the thing rule 40 asks every
result to name.

**What fb3's arithmetic assumed.** It combined (a) an **end-to-end** σ — 48–49
µs/step cross-process wall, 19.5 µs/step within-process wall — with (b) priors
of **−6 to −15 µs/step**, which were the A1 expectations *after* applying the
0.5816 give-back discount. Against a 19.5 µs/step instrument a −6 to −15 effect
is indeed unresolvable at any n I could afford, and the recommended remedy —
a within-process paired design — was the right remedy for that framing.

**What actually changed.** Rule 43 withdrew the give-back discount (PR #473
showed the 0.58 factor was an artefact of `DARKBLOOM_GPU_PROFILE_SPLIT=1`, and
my own §5 ratio `0.833 [0.401, 1.266]` independently contains 1.0). So input
(b) is gone. And fb3 itself instructed me to make the **kernel-local** measure
the discriminator; that is what §3–§5 do. Input (a) is therefore also not the
right σ for the primary verdict.

**The measured σ of the instrument that was actually used** (§2): cross-process,
per-run per-kernel busy label on `..._r1_bf16_v2`, **3.51 µs/step** pooled over
13 A0 runs. fb3's own estimate for per-kernel labels was ±5.1–6.6; the realised
instrument was *finer* than fb3 expected, not coarser. The A/A split-half check
(+2.40 ± 5.62 and +0.72 ± 5.26) confirms it does not manufacture effects.

**The effects that had to be resolved.** +26.47 ± 4.02 (PF2), +98.62 ± 3.33
(PF1), +105.80 ± 2.85 (PF3), −83.64 ± 2.96 (E0). These are **7–30× the 3.51
µs/step floor**, so every one of them clears at n=6–7 with room to spare. The
design was not underpowered for the verdict it actually reached: an inability to
resolve −15 µs/step does not imply an inability to resolve +98.

**Where fb3 is still right, and I concede it.** The end-to-end columns in §13
are genuinely uninformative here: cross-process wall half-widths are ±76 to
±117 µs/step, so the PF2 arm's +26 µs/step *cannot* be confirmed end-to-end at
any n I can afford on this rig. Everything in this document that depends on
end-to-end wall is reported as non-significant and no conclusion rests on it.
If a future assignment needs an end-to-end confirmation of a ~26 µs/step
effect, fb3's within-process paired ABBA design (or the `nat`-regime census of
rule 43) is the only affordable route, and the σ to plan against is 19.5, not
3.51. The two numbers are not competing estimates of one quantity; they belong
to two different instruments and I have labelled which is which everywhere.

## 13. Appendix — full per-kernel delta table (advisor deliverable)

fb3 asked for the per-kernel deltas for **every kernel above 1% of decode**,
side by side with the end-to-end net, so the untouched-pool rows can be aligned
against nezuko's #462 census. Regenerate with
`python3 research/tanjiro-r87a-kernel-table.py`.

All values are µs/step, candidate minus A0 baseline, with the 95% half-width
from the pooled cross-process per-kernel σ of §2. `T` marks the touched kernel.
Arms: **PF1** = steady-state preload, **PF2** = preamble preload, **PF3** =
both, **B2**/**B4** = 2/4 injected in-kernel barriers (§3 positive control),
**E0** = the `expert=0` ceiling probe of §5 (deliberately incorrect, timing
only).

| kernel | share | T | PF1 steady | PF2 preamble | PF3 both | B2 | B4 | E0 ceiling |
| --- | ---: | :-: | ---: | ---: | ---: | ---: | ---: | ---: |
| `routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2` | 17.54% | **T** | +98.62 ± 3.33 | +26.47 ± 4.02 | +105.80 ± 2.85 | +9.13 ± 4.65 | +8.52 ± 4.20 | -83.64 ± 2.96 |
| `decode_nvfp4_qkv_h64_r1_v1_lm1_pw1_se1_sd1` | 15.66% |  | +3.52 ± 9.05 | -1.15 ± 2.99 | -0.08 ± 4.72 | -2.53 ± 5.38 | -2.85 ± 5.10 | +3.53 ± 7.87 |
| `oproj_act_h64_v1_lm1_pw1_sc1_se1` | 13.08% |  | +3.88 ± 4.35 | +2.08 ± 2.20 | +2.62 ± 3.97 | +0.00 ± 4.66 | -2.28 ± 4.57 | +3.63 ± 6.34 |
| `routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6` | 10.06% |  | +1.92 ± 3.97 | +2.13 ± 1.95 | +1.52 ± 3.08 | -0.78 ± 3.53 | -1.58 ± 3.06 | +1.23 ± 4.21 |
| `sliding_fused_attn_ring_v1` | 7.33% |  | +3.25 ± 2.40 | +8.80 ± 1.24 | +2.42 ± 1.90 | -0.47 ± 1.97 | -1.00 ± 1.97 | +1.33 ± 2.05 |
| `lmhead_int5_base_coarse_delta_bf16_v1` | 4.93% |  | +1.42 ± 2.76 | +0.37 ± 0.65 | +0.37 ± 0.83 | -0.40 ± 0.97 | -0.42 ± 0.80 | +0.19 ± 2.24 |
| `decode_nvfp4_qkv_h48_r1_v1_lm1_pw1_se1_sd1` | 4.25% |  | +1.30 ± 2.36 | +0.58 ± 1.08 | +0.60 ± 1.50 | -0.45 ± 1.40 | -0.87 ± 1.33 | +1.00 ± 2.38 |
| `residual_rms_router_bf16_2048_rpg8_keys_v1` | 3.74% |  | +1.10 ± 1.85 | +0.63 ± 1.12 | +0.67 ± 1.69 | -0.80 ± 1.66 | -0.90 ± 1.53 | +0.71 ± 1.59 |
| `oproj_act_h48_v1_lm1_pw1_sc1_se1` | 3.54% |  | -0.32 ± 1.48 | +0.17 ± 1.66 | +0.02 ± 1.25 | -0.73 ± 1.64 | -0.93 ± 1.46 | +0.04 ± 2.35 |
| `shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1` | 3.33% |  | -1.37 ± 2.43 | -1.17 ± 1.96 | -0.97 ± 2.31 | +0.53 ± 1.82 | -0.17 ± 1.72 | +0.99 ± 2.17 |
| `dense_gate_up_swiglu_bf16_v1` | 3.15% |  | +0.58 ± 0.97 | +0.27 ± 1.11 | +0.07 ± 0.77 | -0.03 ± 1.25 | -0.27 ± 1.10 | +0.71 ± 1.63 |
| `gate_sp_h64_v1` | 2.93% |  | -7.83 ± 0.84 | +0.22 ± 0.90 | -6.98 ± 1.09 | -0.90 ± 1.18 | -0.53 ± 1.10 | +0.46 ± 0.98 |
| `full_fused_attn_grow_v1` | 2.92% |  | -1.35 ± 0.74 | -0.30 ± 0.78 | -1.42 ± 0.89 | +0.10 ± 0.77 | -0.52 ± 0.56 | -0.27 ± 0.87 |
| `prefill_router_tournament_ordinal_norm_active64_v2` | 2.18% |  | +0.57 ± 0.92 | +0.28 ± 0.83 | -0.10 ± 0.80 | -0.57 ± 0.57 | -0.47 ± 0.57 | +0.33 ± 0.65 |
| `rmsbfloat16` | 1.66% |  | +0.42 ± 0.91 | +0.10 ± 0.61 | +0.38 ± 0.68 | -0.32 ± 0.49 | -0.27 ± 0.39 | -0.03 ± 0.46 |
| `dense_down_residual_bf16_v1` | 1.57% |  | +0.17 ± 0.67 | -0.13 ± 0.70 | -0.05 ± 0.67 | -0.28 ± 1.27 | -0.95 ± 1.33 | +0.29 ± 0.85 |

**Coverage: 16 of 16 kernels clear the 1% bar, together 97.86% of decode busy
time.** The residual 2.14% is a long tail of sub-1% kernels, individually below
the σ of even the finest label.

**Arm totals**, so the per-kernel rows can be reconciled against the net:

| arm | touched subtotal | untouched subtotal | TOTAL `busy_sum` (SPLIT=1) | end-to-end wall |
| --- | ---: | ---: | ---: | ---: |
| PF1 | +98.62 | +7.25 | +108.50 ± 36.09 | +74.33 ± 80.00 |
| PF2 | +26.47 | +12.88 | +40.17 ± 16.69 | +26.00 ± 105.03 |
| PF3 | +105.80 | -0.95 | +107.33 ± 22.82 | +91.50 ± 102.85 |
| B2 | +9.13 | -7.63 | +1.67 ± 26.29 | -12.83 ± 83.25 |
| B4 | +8.52 | -14.00 | -5.50 ± 24.63 | -32.50 ± 75.79 |
| E0 | -83.64 | +14.13 | -69.71 ± 36.21 | -64.71 ± 116.43 |

The wall column is shown for completeness and is **non-significant in every
arm** (§12); the SPLIT=1 TOTAL carries the σ = 17.11 estimator, ~5× the
per-kernel labels, which is why no verdict rests on either column.

**Two untouched rows I am flagging rather than folding into a subtotal**, as
fb3 asked:

1. **`gate_sp_h64_v1` (2.93% of decode)** is the same kernel that moved
   **+8.14 µs/step in PR #457**, i.e. 73% of that campaign's give-back. Here it
   moves **−7.83 (PF1) and −6.98 (PF3)** at ±0.84–1.09, far outside noise. In
   both campaigns it moves **opposite in sign to the touched kernel** (#457
   touched −26.53 / `gate_sp` +8.14; here touched +98.62 / `gate_sp` −7.83).
   That is a reproducible coupling between two specific kernels, not a
   proportional whole-model give-back, and it is exactly the kind of
   **per-kernel attribution rule 43 preserves** — the retraction removes the
   0.5816 *law*, not the observation that these two rows anti-correlate. I am
   not proposing a mechanism for it here; it is offered as a lead for whoever
   picks up rule 43's `nat`-regime census.

2. **`residual_rms_router_bf16_2048_rpg8_keys_v1` (3.74%)** moved only
   **+0.71 ± 1.59** under E0. The router is precisely where displaced routing
   work would have to land if the ceiling's −83.64 were *migrated* rather than
   *removed*. It did not land there, and no other untouched row absorbs it
   (untouched subtotal +14.13 against a touched −83.64). That is the evidence
   behind §5 reading the ceiling as latency removed. It does **not** rescue the
   `expert=0` DRAM-byte confound of §5a, which remains the reason the ceiling is
   an upper bound and never a candidate.


### 13a. The `gate_sp_h64_v1` coupling is a dose-response, and it corroborates PR #473's H6 from an independent direction

§13 flagged the coupling as an observation. This section claims it, because the
six arms I already ran form a **dose ladder** and the neighbour tracks the dose.
This was measured in the rev1 campaign; nothing here is a new run.

| arm | touched Δ (µs/step) | `gate_sp_h64_v1` Δ (µs/step) | neighbour / touched |
| --- | ---: | ---: | ---: |
| PF1 | +98.62 ± 3.33 | −7.83 ± 0.84 | −7.94% |
| PF2 | +26.47 ± 4.02 | +0.22 ± 0.90 | +0.82% |
| PF3 | +105.80 ± 2.85 | −6.98 ± 1.09 | −6.60% |
| B2 | +9.13 ± 4.65 | −0.90 ± 1.18 | −9.85% |
| B4 | +8.52 ± 4.20 | −0.53 ± 1.10 | −6.26% |
| E0 | −83.64 ± 2.96 | +0.46 ± 0.98 | −0.55% |

Weighted least squares of the neighbour delta on the touched delta, weights
`1/ci95²` on the neighbour:

- **all six arms: slope −0.0477 ± 0.0063**, 95% CI [−0.0600, −0.0354],
  intercept −1.374. The slope is 7.6σ from zero.
- **five slowdown arms only: slope −0.0814 ± 0.0104**, 95% CI
  [−0.1019, −0.0610], intercept +0.910.

So `gate_sp_h64_v1` moves at roughly **7–8% of the touched kernel's magnitude,
opposite in sign, in proportion to the dose** — not as a fixed offset that
appears whenever the kernel is edited. A dose-response is what separates an
instrument artefact from a coincidence, and it is why I am now willing to name
this rather than leave it as a lead.

**Why this bears on PR #473's H6.** #473 concluded that the 0.5816 give-back
"law" was an artefact of `DARKBLOOM_GPU_PROFILE_SPLIT=1` itself — the split
profiler redistributes time between neighbouring dispatches rather than
measuring a real whole-model compensation. My campaign never set out to test
that; it perturbed one MoE kernel six ways for an unrelated hypothesis. The
prediction H6 makes for such a campaign is exactly what §13 found: a specific
untouched neighbour absorbing a signed fraction of the touched kernel's change.
Two independent campaigns, different hypotheses, same kernel pair, opposite
signs, and now a slope. `gate_sp_h64_v1` also carried **73% of PR #457's
give-back** (+8.14 µs/step there, against a touched −26.53), which puts #457's
ratio in the same 7–8%-per-unit-dose neighbourhood as the slope above.

**The caveat that keeps this honest: the coupling is rectified.** E0 is the only
arm that makes the touched kernel *faster*, and it is the arm where the
neighbour does not respond. The five-arm fit predicts **+7.72** for E0; the
observed value is **+0.46 ± 0.98**, a ~7σ miss. A pure bookkeeping
redistribution — profiler time being moved from one row to the next — would be
symmetric, and this is not. Whatever couples these two kernels shows up when the
neighbour's predecessor is *slowed* and vanishes when it is sped up. That is
consistent with a scheduling or duty-cycle mechanism rather than an accounting
one, and it means §13a corroborates H6's *conclusion* (SPLIT=1 totals are not
trustworthy) without confirming any particular linear-redistribution model of
it. I am not proposing the mechanism; the asymmetry is the reason.

PF2 is the second wrinkle: it sits on the slowdown side of the ladder but its
neighbour barely moves (+0.22 ± 0.90 against a five-arm prediction of −1.24,
~1.6σ). Within noise, but worth recording alongside the next paragraph, since
PF2 is anomalous in both untouched rows.

### 13b. Honesty note — part of PF2's SPLIT=1 total is instrument, not mechanism

Under PF2, the untouched **`sliding_fused_attn_ring_v1` (7.33% of decode)**
moved **+8.80 ± 1.24 µs/step**, ~7σ. That kernel is attention. Nothing in the
routed gate/up prefetch ladder touches it, shares a buffer with it, or changes
its dispatch. It cannot be a mechanism of my patch.

The consequence is that **PF2's +40.17 ± 16.69 µs/step SPLIT=1 total should not
be read as 40 µs of harm caused by input prefetch.** At least the 8.80 in that
attention row, and plausibly more of the +12.88 untouched subtotal, is the same
instrument behaviour §13a characterises. The same caution applies to PF1 (+3.25)
and PF3 (+2.42) on that row, though those are within ~1.4σ.

**This does not change the verdict, and I want to be explicit about why.** The
NO-GO on A1 never rested on a SPLIT=1 total (§"Rule 43 compliance"). It rests on
the touched kernel row, which is the one row the patch demonstrably controls:
**+26.47 ± 4.02 (PF2, 6.6σ), +98.62 ± 3.33 (PF1, 30σ), +105.80 ± 2.85 (PF3,
37σ)** against a per-kernel σ of 3.51. Every submittable arm regresses there, by
7–30× the rig floor, and no instrument artefact on an untouched attention kernel
makes a 6.6σ regression on the touched kernel disappear. What §13b removes is
the right to quote PF2's *total* as the size of the damage — which this document
does not do anywhere a decision depends on it.

Coverage for both subsections: the §13 census resolves **16 of 16 kernels above
1%, 97.86% of decode busy time**, so a large untouched mover could not have hid
below the reporting bar.

**Reproduce §13a:** `python3 research/tanjiro-r87a-kernel-table.py` prints the
full per-kernel table, the arm totals, the coupling table above, and both
weighted fits including the E0 hold-out.

---

## 14. Revision `r87-a-rev2` changelog

No re-runs, no new arms. Every number in this document is from the rev1
measurement campaign; rev2 changes what ships and what is claimed, not what was
measured.

**(a) The `Sources/` diff is now zero bytes.** All three env knobs
(`DARKBLOOM_ROUTED_GATEUP_INPUT_PF`, `DARKBLOOM_PROBE_ROUTED_GATEUP_BARRIERS`,
`DARKBLOOM_PROBE_ROUTED_EXPERT0_PF`) are removed from
`Sources/MLXFastModel/LagunaRuntimeModel.swift`. They are dead code on a refuted
hypothesis, and the third is *deliberately numerically incorrect* — it hardcodes
`expert = 0` (§5) — so it has no business sitting in the scored forward pass
behind an environment check.

The mechanism is preserved verbatim in
[`research/tanjiro_r87a_probes.patch`](tanjiro_r87a_probes.patch) (11,545
bytes), following the existing `research/tanjiro_packing_*.patch` convention.
Its header names the base it applies against
(`3217f111142346e004f41fae611a8bede172a659`, this branch's fork point, before PR
#456 relocated the region), gives the one-line re-apply command, documents each
knob's semantics, range, and default, and flags that the **source-generator
refactor** (`lagunaRoutedGateUpR1KernelName` + `lagunaRoutedGateUpR1Source()`)
is inside it, so nobody rebuilds that scaffolding from scratch.
`git apply --check` against `3217f111` is clean.

**(b) Base reconciled to `3f430f6f17ac4bfbac5f47767ca78cb89d84a760` by merge,
not rebase — a deliberate deviation from the revision request.** The advisor
asked for a rebase. This branch forked at `3217f111`, and roughly 20 intermediate
commits on it edit `LagunaRuntimeModel.swift` inside precisely the region PR #456
moved out into the new `Sources/MLXFastModel/LagunaRuntimeLayers.swift`
(2,591 lines relocated). A `git rebase --onto` would have replayed every one of
those commits into conflicts against code that no longer lives in that file, for
zero benefit: with `Sources/` already reverted in (a), there is nothing of mine
left to replay. Merging takes the new base's files wholesale and preserves the
history the advisor already reviewed. The outcome the request actually specifies
is verified directly:

- `git diff --stat 3f430f6f17ac4bfbac5f47767ca78cb89d84a760 HEAD -- ':!research/'`
  → **empty**.
- `senpai/check-editable-budget.sh 3f430f6f17ac4bfbac5f47767ca78cb89d84a760` →
  `editable budget OK: current=2891164/3000000 bytes headroom=108836
  growth=0/262144 files=141 (base=141)`.

**(c) The neighbour-coupling result is claimed** in §13a, with the dose-response
fit, the E0 rectification caveat, and the §13b honesty note on PF2's untouched
attention row. `research/tanjiro-r87a-kernel-table.py` is retained and extended
to print the coupling table and both fits.

