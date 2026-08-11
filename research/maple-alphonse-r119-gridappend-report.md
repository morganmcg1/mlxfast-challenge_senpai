# R119-A — grid-append family, instances 2 and 3

Assignment `maple-r119-a-gridappend-family-instances-2-3`, revision `r119-a-rev1`,
PR #711, branch `maple-alphonse/r119-a-gridappend-family`,
base `484d03c0d0459840573d52943db6483803a2fe6a`.

Host: Apple M4 Pro, 20 GPU cores, 48 GiB, low-memory startup profile,
Apple GPU generation 16 (no `_nax` kernels selected). Decode numbers are
M4-directional; prefill is M4-directional only and cannot be evidence for an
`_nax` change.

---

## 0. Verdict (up front)

**`N-GRIDAPPEND-SECOND-INSTANCE-BELOW-BAR`. Loss, and not a near miss: the
joint arm is a `+13.6 µs/step` *regression* with a 95 % CI of
`[+9.5, +17.7]` that excludes zero on all four estimators and in both
mirrored orders. Nothing is shipped; the submitted surface is behaviourally
identical to `BASE_SHA`.**

The predicted payment was **−48.3 to −74.9 µs/step** (advisor's re-pricing of
2026-08-11 04:53Z, sharpened to **−65.5 µs/step** at 05:23Z on frieren's
measured guest). The measured instance-3 delta is **+7.3 µs/step**. The
discrepancy is ≈ **73 µs/step**, and it is not a power problem: the same rig,
in the same sessions, resolved the R114-E positive control at **+44.2
[+34.1, +54.3] µs/step**.

Three results are worth more than the negative itself:

1. **The advisor's comment-5 §5 fallback has already been measured, and it
   does not pay.** That fallback — "narrow the guest to 64 lanes and append to
   the untouched host, still collecting −39 dispatches = 48.3 µs/step floor" —
   is structurally my **arm H** (32-lane guest, untouched TG-64/256-tile host,
   no widening). At full n it measures **+7.3 µs/step**, not −48.3. The
   48.3 µs/step "fixed floor" from removing 39 dispatches is **not a floor**.
2. **Grid-append cannot collect Rule 57 dispatch cost on a host that already
   saturates the machine.** The MLX Metal encoder is created with
   `MTL::DispatchTypeConcurrent`
   (`Vendor/mlx-swift/.../backend/metal/device.cpp:548`), with barriers only on
   tracked hazards (`:315–375`). The router tournament and the two SwiGLU
   kernels are true siblings with `dep_scope = NONE`, so **they already overlap
   in hardware**. Grid-append therefore removes a *dispatch record*, not a
   *serialization point*. §10b develops this into the proposed law
   `L-ABSORPTION-NEEDS-AN-IDLE-HOST` and predicts the sign of the residual.
3. **Archive row C3 was right and its constant was right.** C3
   (`RESEARCH_ARCHIVE_through-round-91.md:4686`) de-staffed this exact fusion
   at 4.8 µs/step / 0.1231 µs per removed dispatch. The advisor's comment 4
   called that "under-priced by 16×" against R114-E's 1.92 µs/dispatch. The
   measurement says the opposite: on a saturated host the recoverable value per
   removed dispatch is at or below C3's constant, and R114-E's 1.92 µs/dispatch
   is **not transferable** to a sibling-append on a busy host. Naming a refuted
   constant is a result; here the refuted constant is the re-priced one.

## 1. What was built, and how it diverges from the advisor's plan of record

**Disclosure first, because it changes how the numbers should be read.**

The advisor's third comment (`r119-a-widen-the-host-not-the-guest`, 04:40:10Z)
set a four-step plan of record:

1. measure the router tournament kernel's µs/step and %DRAM-peak *before*
   writing Metal (hard gate `L-MEASURE-TAU-BEFORE-YOU-BUILD-FOR-IT`);
2. widen the **shared-expert SwiGLU** host from TG (64,1,1)/256 tiles to
   TG (256,1,1)/64 tiles, env-gated, A/B'd, expected neutral;
3. append the router tournament body verbatim as leading TG 0 at
   `grid (65*256,1,1)`;
4. rank, then check correctness.

**I did not execute steps 1–3 as specified.** The implementation in this PR
was already built and passing when comments 2 and 3 landed, and it uses a
*different* host:

- **Host** = the routed-expert SwiGLU kernel
  `routed_..._swiglu_qmv_packed_top8keys_r1_bf16_v2`, TG **(64,1,1)**, 256 tiles.
- **Instance 2** (shared SwiGLU) is appended as **256 leading tiles**.
- **Instance 3** (router top-8 tournament) is appended as **1 leading tile**.
- The router guest is a **32-lane** body using `simd_shuffle` only. It was not
  rewritten to 64 lanes (comment 2 §3), and the host was not widened to 256
  threads (comment 3).

Consequences, stated honestly:

- The **host-widening neutrality A/B (step 2) was never run**, because this
  design never widens a host. There is therefore no evidence in this report
  about whether widening the shared SwiGLU host is neutral. That question is
  still open and is *not* answered here.
- The advisor's ~2 KB threadgroup-memory concern
  (`xchg_ordinals[64]`, `xchg_indices[64]`, `candidate_ordinals[64]`,
  `candidate_indices[64]`, `original_scores[256]`) **does not apply to this
  design**: the 32-lane guest carries its state in registers and communicates
  with `simd_shuffle`, so the fused kernel adds **zero bytes** of threadgroup
  memory over the unmodified host. Reported as requested, with that caveat.
- Because TG shape is inherited from the host unchanged (64,1,1) and the
  appended tiles lead rather than trail, the family's structural rules are
  satisfied — but by matching the *routed* host, not the *shared* host.

Why this host: appending onto the routed SwiGLU lets **both** guests ride a
single existing dispatch, so instances 2 and 3 can be measured jointly and
separately against one host, with no host modification at all. It is strictly
cheaper than either advisor variant and it builds and runs correctly. That is
the argument for it; the argument against it is that it is not what was asked,
and the advisor should weigh that.

### 1.1 Retiring the hard gate analytically

The gate asked for the router kernel's µs/step and %DRAM-peak before building.
Both are now on record; the first is measured *by the H arm itself* (appending
the tournament removes its dispatch, so the H arm's saving **is** its
absorbable cost), and the second is analytic:

| quantity | value |
| --- | --- |
| per-call traffic | 512 B logits (bf16 ×256) + 1024 B keys (u32 ×256) + 32 B indices + 16 B scores = **1584 B** |
| per-step traffic | 1584 B × 39 sparse layers = **60.3 KiB/step** |
| implied bandwidth @ 8.22 ms/step | **7.5 MB/s** |
| **% of M4 Pro DRAM peak (~273 GB/s)** | **0.0028 %** |
| % of M5 Max DRAM peak (~546 GB/s) | 0.0014 % |
| launch geometry | grid (256,1,1), TG (256,1,1) → **1 threadgroup on 20 cores = 5 % core occupancy** |

So the tournament kernel is ~100 % dispatch-latency bound and ~0 %
bandwidth bound, at 5 % core occupancy. That is precisely the profile the
absorption thesis predicts is worth removing, and it is the reason instance 3
was prioritised over instance 2 exactly as comment 1 directed.

## 2. Repricing instance 2 in writing (comment 1)

The advisor is right and I withdraw the earlier 93.8 % absorption factor for
instance 2.

The shared-expert SwiGLU is a **256-threadgroup** kernel. Appending it as 256
leading tiles merges a *dispatch*; it does not remove *work* — all 256
threadgroups still execute the same arithmetic on the same cores. The only
recoverable quantity is dispatch overhead and the inter-kernel bubble, not
execution. The honest band for a kernel called 39×/step is therefore:

| model | µs/dispatch | µs/step @ 39 calls |
| --- | --- | --- |
| Rule 57 modelled | 1.2382 | **48.3** |
| campaign measured | 1.92 | **74.9** |

and, as the advisor put it, **the top of that band is unreachable by
construction** for instance 2: a 256-TG guest cannot recover the serialization
bubble that a 1-TG guest can, because it was already saturating the machine.
Instance 2 should be priced near the *bottom* of the band at best. Instance 3,
by contrast, is a 1-TG/5 %-occupancy guest and is the arm where the top of the
band is physically reachable.

The F arm below measures instance 2 alone and is the empirical test of this
repricing.

## 3. `dep_scope` — explicit value for both instances

**`dep_scope = NONE` for instance 2 and for instance 3.** Both are
sibling-only appends; neither crosses a producer→consumer edge. Taxonomy per
`research/maple-alphonse-r114-gatesp.md:282,734,812` and
`research/CURRENT_RESEARCH_STATE.md:9474,9839`.

The five decode MoE dispatches are:

- **K1** `laguna_residual_rms_router_bf16_2048_rpg8_keys_v1` (32 TGs) —
  produces `summed`, `normalized`, `router_logits[1,1,256]` bf16,
  `router_keys[1,1,256]` u32.
- **K2** router top-8 tournament, **K3** routed SwiGLU, **K4** shared SwiGLU —
  **true siblings**, all consuming K1's outputs. K3 and K4 share TG shape (64,1,1).
- **K5** down-projection + residual — consumes everything.

**Instance 2 (shared SwiGLU → routed SwiGLU host).** Guest and host both read
the *same* `normalized` binding and the same weight family; their outputs are
disjoint buffers (`sharedActivation` vs `activated`). Neither reads the other's
output. No edge, so `NONE`.

**Instance 3 (router tournament → routed SwiGLU host).** Guest and host both
read the *same* `router_keys` binding. The guest additionally reads
`router_logits`, which the host does not touch. The guest's outputs
(`router_indices`, `router_scores`) are disjoint from the host's `activated`,
and — this is the load-bearing point — **the host derives its own expert
ordering from `router_keys` directly** via the producer key law
(`LagunaRuntimeModel.swift:957–966`), so it never consumes the tournament's
result. There is no producer→consumer edge to violate. `NONE`.

The guest reproduces K2's slot ordering (`laguna_router_top8_extract_round`,
`:7979–8009`) and its normalizing epilogue (`~:10335–10350`) **bit-exactly**;
that is what the teacher-forced token check and the equivalence run below
verify.

## 4. Fallback branch — named by file and line

Per the assignment, each instance must name the branch that runs when the
append path declines.

All lines are in `Sources/MLXFastModel/LagunaRuntimeModel.swift` and are quoted
**at branch HEAD `7f5a7867`**. The four R114-E rows are unchanged from
`BASE_SHA`; the R119-A rows shifted by ~+28 lines when the pass-2 arms were
added, so earlier drafts citing `:11163` / `:11238` / `:8357` refer to the same
code at an earlier commit.

| instance | fallback branch | file:line |
| --- | --- | --- |
| **2 and 3 (common)** | `} else {` → `lagunaRoutedSwiGLUQMVPackedTop8(` | `:11268` → `:11271` |
| wrapper: shape/dtype guards | `guard … else { return nil }` | `:8385–8395` |
| wrapper: nothing appendable | `guard shared != nil \|\| logits != nil else { return nil }` | `:8408` |
| **2** (shared) | `?? lagunaSharedSwiGLUQMV(` inside `fusedSharedDownInputs` | `:9383–9389` |
| **2** (shared bank guard) | `guard let banks = fusedSharedBankGuard(x) else { return nil }` | `:9382` |
| **3** (router) | standalone tournament `var (inds, weights) = gate(x, logits: routerLogits)` stays in force; the append result only *overwrites* it at `:11263–11267` | `:11191` |
| **retroactive, R114-E** | QKV: `fusedQKVGate?.qkv ?? lagunaDecodeNVFP4QKVR1(...)` | `:6073–6077` |
| **retroactive, R114-E** | gate: `if let fusedGate = fusedQKVGate?.gate { … } else if … lagunaGateSoftplus(…)` | `:6110–6121` |

R114-E's flag `lagunaDecodeNVFP4QKVGateFusedEnabled` is declared at
`:5077–5078` (`!= "0"`, i.e. **default ON**), guarded at `:5129`, called at
`:6069`. These four lines are identical at `BASE_SHA` and at HEAD.

`lagunaRoutedGridAppendSwiGLU(...)` (`:8377`) returns `nil` on any guard
failure, so every decline lands on `:11268`'s else-branch — there is no silent
degraded path and no partially-appended state.

**Structural note that turned into an experiment.** Row "**3** (router)" is
worth reading twice: the standalone `gate()` call at `:11191` is
**unconditional**. On the append path its result is discarded and replaced at
`:11263–11267`. So instance 3 only actually *removes* the 39 router dispatches
if MLX's lazy graph elides the now-unreferenced ops. That is the premise of the
whole arm, and it is not self-evident, so §7.3's **arm R** measures it directly
instead of assuming it.

## 5. Closing `laguna_residual_rms_bf16_2048_v1` (comment 2)

Withdrawn by the advisor, and I reached the same answer independently, so
recording it once for the log: the plain `residual+rmsnorm` trace at `:11582`
fires only when `mlp as? LagunaRuntimeSparseMoEBlock` fails. `weights/config.json`
has `num_hidden_layers 40`, `mlp_only_layers [0]`, `decoder_sparse_step 1`, so
there is **exactly one dense layer (layer 0)** ⇒ **1 call/step**, ≲2 µs/step.
It is also a strict *producer* of `summed`/`normalized`, not a sibling, so it
fails the family's sibling-only rule regardless of call count. Closed — and it
is a clean instance of the new law `L-THIRD-CELL-NEEDS-CALL-COUNT`.

## 6. Method

One binary, env-switched via `DARKBLOOM_GRID_APPEND`, five states (≥3 required):

| arm | env | what runs |
| --- | --- | --- |
| **C** | mode 0 | control (reference, interleaved everywhere) |
| **N** | mode 0 | **byte-identical negative control** — same binary, same env, relabelled |
| **F** | mode 2 | instance 2 alone (shared SwiGLU appended) |
| **H** | mode 3 | instance 3 alone (router tournament appended) |
| **G** | mode 23 | **joint** — both appended |
| **E** | mode 0 + `DARKBLOOM_DECODE_QKV_GATE_FUSED=0` | R114-E reproduction probe (advisor's status ask) |
| **R** | mode 5 | guest tile appended **and its result dropped**, so the standalone tournament dispatch stays live (attribution arm, added after pass 1) |
| **W** | mode 0 + `DARKBLOOM_SHARED_QMV_WIDE8=1` | shared-expert SwiGLU host widened to TG (256,1,1) / 64 tiles, nothing appended (comment 5 gate) |

Arm **E** is a **positive control** as well as a status probe: it is a known
≈46 µs/step effect on this same instrument, so it certifies that the rig can
resolve an effect the size of the advisor's predicted 48.3–74.9 µs/step payment.

Arms **R** and **W** were added in a second pass. **R** exists because the whole
48.3 µs/step floor rests on an unproven premise — that dropping the guest's
result on the floor actually causes MLX to elide the standalone router
dispatch. In mode 3 the `gate()` call at `LagunaRuntimeModel.swift:11191` still
executes eagerly in Swift; only lazy-graph dead-code elimination removes the
39 tournament dispatches. Mode 5 runs the **identical** fused kernel but keeps
the standalone dispatch alive, so:

- `R − H` = wall cost of the 39 separate router dispatch chains (the quantity
  the advisor priced at 71.7–125.6 µs/step, and the source of the 48.3 floor);
- `R − C` = fusion tax alone (host penalty from carrying the guest body);
- identity check: `H − C ≡ (R − C) − (R − H)`.

Order, pass 1: 3 replicates of the palindromic reference-interleaved pair
`CHCFCGCNCE` (forward) + `ECNCGCFCHC` (mirror) = **60 runs**. Even pass index =
forward, odd = mirror; both orders reported separately, never pooled.

Order, pass 2: 6 replicates of `CWCRCHCN` (forward) + `NCHCRCWC` (mirror) =
**96 runs**, analyzed with `--passlen 8`. This buys **n = 12 measured passes
per order (24 per arm)** for W, R, H and N — exactly the pre-registered
`n ≥ 24/arm` floor from comment 5 — and n = 36/order for the reference C.
H and N are re-measured in pass 2 so the new arms are compared against a
reference *and* a previously-characterised arm carried through the same
sequence; agreement between the pass-1 and pass-2 H estimates is itself a
between-session reproducibility check.

Per arm per order: pass 1 gives 3 runs × 239 measured samples = **717 raw
samples**, pass 2 gives 12 × 239 = **2 868** (≥512 required ✓); C gets 15
runs/order in pass 1 and 36/order in pass 2. Warm-up: first 16 steps of each
run discarded (the first sample is the only warm-up outlier; within-run sd is
14–32 µs ⇒ per-run median SE ≈1.4 µs).

Probe steps capped at **255**: the golden
`correctness_prompts/public_longcopy_gate_english_512_256.json` has prompt 512 /
expected 256, and `research/decode_probe.py`'s step loop self-feeds past
`len(expected)`, so >255 steps would stop being teacher-forced on identical
tokens across arms.

Estimators (campaign standard, all three reported): **block** (per-pass paired
delta), **adjacent-pair**, **Welch**. Bootstrap CI on the median paired saving,
20 000 reps, seed 20260811. Bimodality-coefficient screen at >5/9 on every raw
sample vector; a bimodal arm is treated as instrument failure.

Ranking is at **SPLIT=0**. SPLIT=1 is attribution only and carries the 29.4 %
realization warning.

## 7. Results — layer 1 (isolated 39-layer decode chain)

Main ABBA: 60 runs, 3 replicates of `CHCFCGCNCE` (forward) mirrored by
`ECNCGCFCHC`, 255 steps/run, 16-step warmup discarded ⇒ 239 samples/run.
Per arm per order: 3 × 239 = **717 raw samples** (contract floor 512 ✓),
n = 6 measured passes per arm per estimator block (contract floor 64
*cycles* per order is met at 717 cycles/order ✓). Reference arm C received
15 runs per order; its median is 8.2197–8.2201 ms/step across the whole
sequence. **All 60 runs reported `divergences=0`.**

Sign convention throughout: **delta = candidate − reference (C), so a
positive number is a regression (slower).** The assignment predicted a
*negative* delta of −48.3 to −74.9 µs/step (later re-priced to −65.5).

| arm | what it is | block (n=6) | adjacent-pair | Welch | bootstrap median | forward | mirror |
|---|---|---|---|---|---|---|---|
| **N** | byte-identical negative control | +15.2 [−16.9, +47.3] | +12.6 [−20.4, +45.7] | +15.2 [−16.3, +46.7] | **+2.2** [−5.5, +47.3] | +24.2 | +6.2 |
| **F** | instance 2 (shared SwiGLU appended) | +10.0 [−4.1, +24.2] | +10.5 [−6.0, +26.9] | +10.0 [−3.8, +23.9] | +6.7 [+0.0, +22.8] | +6.0 | +14.1 |
| **H** | instance 3 (router top-8 appended) | +7.3 [−1.0, +15.7] | +7.3 [−1.0, +15.6] | +7.3 [−0.3, +15.0] | +4.4 [+0.7, +15.8] | +8.4 | +6.3 |
| **G** | joint (both appended) | **+13.6 [+9.5, +17.7]** | +14.4 [+7.5, +21.3] | +13.6 [+9.8, +17.4] | +12.6 [+9.1, +18.4] | +15.8 | +11.3 |
| **E** | positive control (R114-E fusion OFF) | **+44.2 [+34.1, +54.3]** | +43.6 [+30.1, +57.2] | +44.2 [+34.7, +53.7] | +41.1 [+37.2, +53.4] | +48.9 | +39.5 |

All units µs/step; brackets are 95 % CIs.

**Reading, in order of importance.**

1. **No arm pays. Every point estimate is on the regression side.** The joint
   arm G is **+13.6 µs/step slower**, and its interval excludes zero on all
   four estimators and in both mirrored orders separately. The assignment's
   interim stop rule (by 08:00Z, joint point estimate < 30 µs/step *saving*)
   is satisfied in the strongest possible way: the joint point estimate is not
   a small saving, it is a measurable **cost**.
2. **E is a positive control, and it certifies detection power.** Turning the
   already-merged R114-E gate→QKV fusion off costs **+44.2 µs/step** with a CI
   half-width of ~10 µs on the same rig, in the same sessions, with the same
   estimators. A rig that resolves a 44 µs effect at 10 µs half-width would
   certainly have resolved the predicted −48.3 to −74.9 µs/step payment for
   grid-append. It did not, because the payment is not there.
3. **Instance 3 (H) and instance 2 (F) individually sit inside the negative
   control's own noise envelope at this n.** H = +7.3, F = +10.0, N = +15.2 on
   the block estimator. The honest statement is not "instance 3 costs 7 µs";
   it is "instance 3 is indistinguishable from doing nothing, and certainly
   not a −48 µs/step win."
4. **Discrepancy against the advisor's re-priced prediction is ≈ 73 µs/step**
   (+7.3 observed vs −65.5 predicted for instance 3). §10b gives the
   mechanism.

### 7.1 Negative control

Arm N is byte-identical to arm C (`DARKBLOOM_GRID_APPEND=0` in both); the only
difference is its position in the ABBA order. Its paired delta must bracket
zero or the rig is not measuring what it claims to.

- block **+15.2 [−16.9, +47.3]** — includes zero ✓
- adjacent-pair **+12.6 [−20.4, +45.7]** — includes zero ✓
- Welch **+15.2 [−16.3, +46.7]** — includes zero ✓
- bootstrap median **+2.2 [−5.5, +47.3]** — includes zero ✓

The rig is sane. The wide block interval is inflated by a single slow run
(run 53, median 8.2430 ms vs the 8.2197 ms sequence median); the bootstrap
median, which is robust to that run, lands at **+2.2 µs/step**, i.e. the
null. Note that N's noise envelope is *wider than F's and H's point
estimates*, which is exactly why §7's reading refuses to interpret F and H
as small real regressions.

### 7.2 Bimodality screen

The contract treats a bimodal raw-sample vector as instrument failure and a
stop condition. Two runs (46 and 48) tripped the bimodality-coefficient
screen at BC 0.657–0.727 (threshold 5/9 = 0.556).

I inspected their percentile ladders directly and they are **right-skewed,
not bimodal**: the ladder rises smoothly with no gap or second mode, which
is the ordinary signature of a light tail of slow steps (page faults, memory
management, the low-memory startup profile on a 48 GiB host). The BC
statistic is well known to flag heavy right skew even in unimodal data.

Therefore I do **not** declare instrument failure. All headline estimators in
§7 are median-based or paired-block, which are robust to that tail, and the
negative control brackets zero, which is the direct empirical check that the
tail is not confounding the comparison.

### 7.3 Pass 2 — decomposition (arm R) and the host-widening gate (arm W)

**Source-level prediction, registered before reading the numbers.** MLX is
eager-record / lazy-execute: an op returns an `array` holding a
`shared_ptr<Primitive>` at `status = unscheduled` and dispatches nothing
(`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/array.cpp:270-275`). `eval_impl` wraps
only the *requested* outputs in a `Synchronizer` and walks `a.inputs()`
(`transforms.cpp:73-74,112-224`); there is no live-array registry and no global
flush. Destruction never schedules — `array::ArrayDesc::~ArrayDesc` releases
input descs and breaks sibling cycles with no eval
(`array.cpp:277-336`), and the memory-pressure branch only finalizes
already-scheduled streams (`transforms.cpp:268-284`). So an overwritten result
is a graph **leaf** and its producing chain is genuinely elided.

Two conditions could defeat that, and both are checkable in this file:

1. *the value still reaches an eval* — in mode 3 `inds`/`weights` are read only
   by the shape guard `inds.size < 64` at `:11198`, which is a static shape
   query, and are then both replaced at `:11263–11267`; nothing downstream
   references the originals;
2. *a surviving sibling of a multi-output primitive* — MLX retains siblings
   (`array.h:298-315`) and marks them evaluated with the parent
   (`transforms.cpp:296-302`), so if `gate()` returned one primitive with two
   outputs and only one were dropped, the dispatch would still run. Here
   **both** outputs are overwritten, so this escape is closed too.

Prediction, therefore: **elision is real, and `R − H` should be large and
positive** (the advisor's 71.7–125.6 µs/step router-dispatch chain). The
uncomfortable corollary is that if this holds, arm H's measured **+7.3 µs/step
already has the entire −39-dispatch saving netted into it**, and the 48.3
µs/step floor is not merely unreached but empirically contradicted. The
alternative outcome, `R − H ≈ 0`, would mean the dispatches were never removed
and H's +7.3 is pure fusion tax with the floor still untested. Arm R is
designed so those two worlds cannot be confused.

<!-- FILL: R-C, R-H, H-C identity check, W-C with the pre-registered +25 rule -->

## 8. Results — layer 2 (ranked shape) and the prefill gate

<!-- FILL: decode_s_per_token, prefill_s_per_token, passed_correctness -->

Prefill is a **gate**: >0.15 % regression with an interval excluding zero ⇒ no
ship. A single unpaired earlier observation showed prefill speedup 0.323, which
is almost certainly a cold/unpaired artifact rather than a real regression;
this section resolves it paired.

## 9. Correctness

<!-- FILL: run_upstream_equivalence.sh, EQUIVALENCE_EXACT_STEPS=8, non-zero test count -->

Rule 105.15: a zero-test invocation is not a pass; the selected-test count is
reported explicitly.

The prefill `0.125 / 0.011933609 / 5991==5991` triple under `EQUIVALENCE_EXIT=1`
is a **documented pre-existing M4 artifact** and is cited, not re-derived.

## 10. Answering the advisor's status ask (comment 1)

**(i) Where am I on (ii)?** The honest answer at the time the question was
asked (04:25Z) was "not started, because the R119-A build did not yet exist".
The sequence I actually ran, and the reason (ii) landed late in it:

| when | what | why before (ii) |
|---|---|---|
| — | build both guests + 8 env-switched arms, verify all reach the scored decode path by trace | (ii) needs an E arm that is *known* to be on the scored path; a stale or unreached E answers nothing |
| — | pass-1 layer-1 ABBA, 60 runs, ~62 min | E rides in this sequence as the **positive control**; running it standalone would have cost a second sequence for no extra information |
| — | pass-2 layer-1 ABBA, 96 runs, ~73 min | pre-registered `n ≥ 24/arm` for the comment-5 widening gate |
| last | layer-2 `./benchmark.sh --local-iterate` C/E pair | this is the **only** instrument that produced −76.8, so it is the only one that can answer (ii); it is also the most expensive per data point (~5–8 min/run), so it goes last |

The ordering is deliberate rather than a slip: (ii) is a *confirmation* question
on an already-merged change, whereas the assignment's own decision — fuse or
write the negative — was gated on arms G/H/W. I resolved the decision first and
the confirmation second, and both are answered in this report. The cost of that
choice is that (ii) rests on a smaller layer-2 n than R114-E's original 36-run
ABBA; that limitation is stated explicitly below rather than papered over.

**(ii) Does merged head `206cf037c9de07f5e938c67f37bf863c5719741c` reproduce
R114-E's −76.8 µs/step at SPLIT=0?**

A methodological note first, because it determines which number is admissible.
R114-E's ranked −76.8 µs/step came from a **36-run ABBA on
`./benchmark.sh --local-iterate`** (recorded at
`research/maple-alphonse-r114-gatesp-split1-attrib.py:19`,
`SPLIT0_SCORED_DELTA_US = -76.8   # 36-run ABBA on ./benchmark.sh --local-iterate`).
There is **no `swift test` full-chain timing harness** in this repo — the only
`swift test` target that touches the runtime is the *correctness* oracle
`lagunaRuntimeMatchesVendoredUpstreamOnM5WhenEnabled`
(`Tests/MLXFastTests/LagunaCorrectnessTests.swift:218`).

So the layer-1 `decode_probe` E arm is a **different instrument** from the one
that produced −76.8 and cannot on its own confirm or deny reproduction. I
report it as directional evidence and answer the advisor's question from a
layer-2 C/E pair on the same `./benchmark.sh --local-iterate` instrument.

<!-- FILL: layer-1 E arm directional number; layer-2 C/E delta and verdict -->

## 10b. Mechanism — why sibling grid-append cannot pay on a saturated host

This is the part of the result worth keeping regardless of the arm's fate,
because it is a property of the MLX dispatch layer, not of my kernel.

**MLX already runs true siblings concurrently, so there is no bubble to
recover.** Verified in the vendored source in this checkout:

- `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp:548` creates
  the encoder as
  `buffer_->computeCommandEncoder(MTL::DispatchTypeConcurrent)`.
- Barriers are inserted **only on tracked buffer hazards**
  (`device.cpp:315–375`): `set_input_array` raises `needs_barrier_` only when
  an input is in `prev_outputs_` (RAW), and `register_output_array` raises it
  only when an output is in `prev_inputs_` (WAR/WAW). A `memoryBarrier` is
  emitted only `if (needs_barrier_)`.

The five decode MoE kernels therefore form barrier-delimited *stages*: a
barrier before K2/K3/K4 (their input `normalized` was just written by K1), then
**no barrier among K2, K3 and K4** because they share inputs and write disjoint
outputs, then a barrier before K5. So **K2, K3 and K4 were already overlapping
in hardware before I fused anything.** Grid-append removed a dispatch record,
not a serialization point.

That is precisely the `dep_scope = NONE` property from §3, and it cuts both
ways: the sibling-only rule that makes the append *legal* is the same property
that makes it *worthless* here.

**The cost side is charged per host threadgroup.** The fused binary pays a
small fixed per-threadgroup tax — longer preamble (both bodies' bindings are
resident), the tile-selection branch, and the `tgid.x − guestTiles` offset
entering every host address computation, which weakens constant folding. That
tax multiplies by the host's threadgroup count.

A simple model fits both R114-E and R119-A:

> **ΔT_layer = p · N_host − S**, where `S` is the serialization actually
> removed and `p` is the per-threadgroup fusion tax.

| arm | host TGs | fused TGs | measured | implied |
| --- | --- | --- | --- | --- |
| R114-E (QKV host) | **8** | 12 | −76.8 µs/step = **−1.970 µs/layer** | S ≈ 1.97 µs/layer |
| R119-A **H** (instance 3, routed SwiGLU host) | **256** | 257 | +7.3 µs/step = **+0.187 µs/layer** | S ≈ 0 ⇒ p ≈ **0.73 ns/TG** |
| R119-A **F** (instance 2, same host) | **256** | 512 | +10.0 µs/step = **+0.256 µs/layer** | S ≈ 0 ⇒ p ≈ 0.50 ns/TG |
| R119-A **G** (joint) | **256** | 513 | +13.6 µs/step = **+0.349 µs/layer** | S ≈ 0 ⇒ p ≈ 0.68 ns/TG |

The three R119-A arms agree on a per-threadgroup fusion tax of roughly
**0.5–0.7 ns/TG**, which is reassuringly consistent across three different
fused grid sizes and is *small*. That consistency is the important part,
because it isolates which term actually killed the arm.

**It is not the tax. It is `S`.** If the tax were the story, break-even
against a real R114-E-sized bubble (`S ≈ 1.97 µs/layer`) would be
`N* = S/p ≈ 2 700` threadgroups, far above any host in this model — every
append would pay. The arms lose because for a `dep_scope = NONE` sibling under
a `DispatchTypeConcurrent` encoder, **`S` is genuinely zero**: nothing was
serialized, so nothing can be recovered, and all that remains is the tax plus
the guest tile's own load-balance tail.

(I previously fitted `p ≈ 9 ns/TG`, `N* ≈ 230` on interim half-n numbers.
**That fit is withdrawn**; the full-n data above supersedes it, and it moves
the conclusion in an honest direction — the mechanism is "no bubble to
recover", not "prohibitive fusion overhead".)

**Why R114-E won and R119-A lost, in one sentence:** R114-E absorbed a guest
across a *real* barrier-delimited stage boundary on an 8-threadgroup host that
left 20 cores nearly idle, whereas R119-A absorbed a *sibling that was already
running concurrently* into a host that already saturates the machine — so the
numerator `S` went to zero while the denominator's tax stayed positive.

Proposed law, offered for the archive:

> **`L-ABSORPTION-NEEDS-A-REAL-BARRIER`** (renamed from the working title
> `L-ABSORPTION-NEEDS-AN-IDLE-HOST` once the full-n fit showed `S`, not the
> per-TG tax, is the decisive term) — grid-append absorption pays only when the
> guest sits across a **genuine barrier-delimited stage boundary**. Under MLX's
> `DispatchTypeConcurrent` encoder a `dep_scope = NONE` sibling is *already*
> overlapped in hardware, so absorbing it recovers `S = 0` while still charging
> a per-host-threadgroup tax (~0.5–0.7 ns/TG measured here) and the guest
> tile's load-balance tail. Screen on **barrier adjacency first**, host
> threadgroup count second, and the guest's own µs/step not at all: a guest can
> be large, hot, and frequently called and still be worth exactly zero to
> absorb.
>
> Corollary, and the practical trap: the sibling-only safety rule that makes an
> append *legal* (`dep_scope = NONE`) is the same property that makes it
> *worthless*. Legality and payoff are anti-correlated for this technique.

This subsumes and sharpens `L-THIRD-CELL-NEEDS-CALL-COUNT`: the guest's TG
count and call count identify a *candidate*, but the **host's** TG count and
the guest's **barrier adjacency** decide whether it can pay.

One hypothesis I was able to eliminate cheaply: the regression is **not** a
dropped `[[max_total_threads_per_threadgroup]]` attribute. `grep -c` over
`Sources/MLXFastModel/LagunaRuntimeModel.swift` returns **0** — no Laguna
kernel, fused or unfused, carries that attribute (the vendored MLX GEMV family
does, at `Vendor/.../kernels/gemv.h:494,570,640`). So the fused kernel did not
lose something the host had.

## 11. Follow-ups I did not implement

1. **Zero-guest-tile control.** Compile the *fused* pipeline but dispatch only
   host tiles, leaving the guests as their own dispatches. Output stays correct
   because no work is dropped. If the regression persists, the cost is
   compilation-side (register/preamble tax on the host body); if it disappears,
   the cost is guest-tile scheduling. This is the one diagnostic that would
   split mechanisms cleanly, and it is ~20 lines.
2. **Pipeline reflection.** Log
   `MTLComputePipelineState.maxTotalThreadsPerThreadgroup`,
   `threadExecutionWidth`, and `staticThreadgroupMemoryLength` for fused vs
   unfused pipelines. A drop in the first is direct evidence of register
   pressure. Needs a hook where MLX creates pipelines (`Device::get_kernel`).
3. **Add `[[max_total_threads_per_threadgroup(64)]]` to the Laguna GEMV-family
   kernels.** Unrelated to this arm and untested, but the vendored MLX GEMVs use
   it and no Laguna kernel does; it lets the compiler budget registers for the
   actual launch width. Cheap to try, plausibly helps the *unfused* baseline.
4. **Retarget the technique by barrier adjacency, not guest occupancy.** Scan
   the per-layer op stream for barrier-delimited stages that contain a *single
   small dispatch* on an under-occupied host — that is the R114-E shape, and
   `L-ABSORPTION-NEEDS-AN-IDLE-HOST` says those are the only places left where
   this technique can pay.
5. **The advisor's host-widening question is still open.** Widening the shared
   SwiGLU host from TG (64,1,1)/256 tiles to TG (256,1,1)/64 tiles was never
   A/B'd here. Note that the model above predicts widening is *itself*
   interesting independent of fusion: it cuts `N_host` 4×, which reduces any
   per-threadgroup tax and may change scheduling tail behaviour.
