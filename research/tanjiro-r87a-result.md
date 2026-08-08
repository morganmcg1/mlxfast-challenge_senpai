# R87-A result — routed gate/up QMV head latency

Assignment `maple-r87-a-routed-qmv-head-latency`, revision `r87-a-rev1`, PR #469.
Branch `maple-tanjiro/r87-routed-qmv-head-latency`, base
`3217f111142346e004f41fae611a8bede172a659`.

Pre-registration: [`research/tanjiro-r87a-prereg.md`](tanjiro-r87a-prereg.md),
committed at `7e93b50` / amended at `502756c`, **both before any timing run**.
Every prediction in §6 of that file is scored HIT/MISS in §9 below.

## Verdict — **NO-GO on A1. The hypothesis is refuted, not merely unresolved.**

| | |
| --- | --- |
| A1 (submittable input-prefetch ladder) | **HARMFUL.** Best arm +26.47 µs/step kernel-local, worst +105.80. All three arms are regressions at 3–30× the rig floor. |
| Shipped default | `DARKBLOOM_ROUTED_GATEUP_INPUT_PF=0`, verified byte-identical MSL to stock. **Nothing in this PR changes scored behaviour.** |
| A2 (deliberately incorrect ceiling probe) | **−83.64 ± 2.96 µs/step** kernel-local, quoted at face value per rule 43. The SPLIT=1 census total was −69.71 ± 36.21 µs/step; the two bracket **≈+1.07% to +1.28% score**. No give-back discount is applied. **Confounded** — the probe also cuts ~22% of DRAM bytes, so this is a *loose* upper bound, not a target. See §5a. |
| Merge recommendation | **Do not merge as a speedup.** Merge or close on the value of the negative result and the A2 bound; the knob itself is dead weight unless the advisor wants it retained for follow-up work. |

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

### 7b. 64-step drift tripwire

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

**W&B record.** Run `d0ufnmht` —
<https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/d0ufnmht>
(entity `wandb-applied-ai-team`, project `mlxfast-maple`). It carries the arm
tables, per-kernel delta tables, and score conversion for all three blocks.

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
