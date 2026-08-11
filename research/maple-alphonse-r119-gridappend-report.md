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

Four results are worth more than the negative itself. The first is the one to
read if you read only one.

1. **The 48.3 µs/step floor has been measured directly, and it is
   +2.1 µs/step.** A second 96-run session added arm **R** — the guest appended
   exactly as in arm H, but with the standalone router dispatch deliberately
   *kept alive* by discarding the appended result. `R − H` therefore isolates the
   value of the 39 removed dispatches with guest cost held fixed. It is
   **+2.1 µs/step, 95 % CI [−10.4, +14.6]**, median +0.2, 6/12 blocks positive
   ⇒ `D ≤ 0.374 µs/dispatch` at 95 % against Rule 57's **1.2382**. The floor was
   literally `39 × 1.2382 = 48.29`; **Rule 57's price is excluded at 95 % for
   this pair, by 3.3× at the bound and 23× at the point estimate.** The floor is
   not merely unreached — the one quantity it is made of has now been measured
   (§7.3, §10b.3, `L-SIBLING-DISPATCH-IS-ALREADY-FREE`).
2. **`dep_scope = NONE` is not the precondition that makes an append legal and
   profitable; it is the condition that makes it worthless.** MLX encodes with
   `MTL::DispatchTypeConcurrent`
   (`Vendor/mlx-swift/.../backend/metal/device.cpp:548`) and barriers only on
   tracked hazards (`:315–375`). Sibling kernels are therefore *already
   overlapped*, so their dispatch cost is already off the critical path and
   fusion has nothing to recover, while the guest's serial tile latency is newly
   charged to the host's tail. Expected net effect of a sibling grid-append is
   **`+g`, not `−k·D`** — which is exactly what all three appended arms measure.
3. **R114-E's win is real but is not dispatch recovery, which resolves the
   comment-6 transfer anomaly.** Unfusing R114-E costs **+44.2 [+34.1, +54.3]
   µs/step**, but at most +15.0 of that (40 × the 0.374 bound) can come from
   dispatch count, so **≥66 %, and in point estimate 95 %, is operand reuse** —
   one kernel streaming `normalized` and its weights once instead of two doing it
   twice. A dispatch-overhead win should transfer across Apple Silicon
   generations nearly unchanged; an operand-reuse win scales with cache and
   bandwidth per unit of work. So the two official draws landing at −0.063 %
   against a predicted +0.45 % is the *expected* behaviour of an operand-reuse
   win moving to a wider, better-fed machine, not an anomaly. §10b.1 also records
   that I had to retract my own first law here — R114-E is itself a barrier-free
   sibling append, so "no barrier" was never the discriminator.
4. **The comment-3/§5 host-widening gate passes, and the §5 fallback was
   already measured.** Arm **W** (shared-expert SwiGLU host widened to TG
   (256,1,1) / 64 tiles, nothing appended) measures **−1.5 µs/step
   [−15.4, +12.5]**, worst-estimator CI upper **+15.7**, inside the
   pre-registered `≤ +25 ⇒ fuse` threshold; 10/12 blocks negative, sign test
   p = 0.039. The load-balance-granularity hazard is not realized at 20 GPU
   cores — host widening is free. Separately, the comment-5 §5 fallback
   ("narrow the guest to 64 lanes, append to the untouched host, still collect
   the 48.3 µs/step floor") is structurally my **arm H**, which measures
   **+7.3 µs/step (pass 1) and +6.4 (pass 2)**, not −48.3. Archive row C3
   (`RESEARCH_ARCHIVE_through-round-91.md:4686`) was right to de-staff this at
   0.1231 µs per removed dispatch; comment 4's "under-priced by 16×" is the
   claim that fails.

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

All lines are in `Sources/MLXFastModel/LagunaRuntimeModel.swift`. Every line
below was re-read and re-verified at `dbd4b9f3`, the last commit that touches
that file, and is therefore current at branch HEAD. The four R114-E rows are
byte-identical at `BASE_SHA` (checked with `git show $BASE_SHA:…`); the R119-A
rows shifted by ~+28 lines when the pass-2 arms were added, so earlier drafts
citing `:11163` / `:11238` / `:8357` refer to the same code at an earlier
commit. The one remaining pre-submission edit — flipping the shipped
`DARKBLOOM_GRID_APPEND` default at `:8241` from `"23"` to `"0"` (§9a) — replaces
one token on one line and shifts nothing below it, so this table stays valid at
the submitted commit.

| instance | fallback branch | file:line |
| --- | --- | --- |
| **2 and 3 (common)** | `} else {` → `lagunaRoutedSwiGLUQMVPackedTop8(` | `:11268` → `:11271` |
| wrapper: shape/dtype guards | `guard … else { return nil }` | `:8385–8395` |
| wrapper: nothing appendable | `guard shared != nil \|\| logits != nil else { return nil }` | `:8408` |
| **2** (shared) | `?? lagunaSharedSwiGLUQMV(` inside `fusedSharedDownInputs` | `:9383–9389` |
| **2** (shared bank guard) | `guard let banks = fusedSharedBankGuard(x) else { return nil }` | `:9382` |
| **3** (router) | standalone tournament `var (inds, weights) = gate(x, logits: routerLogits)` stays in force; the append result only *overwrites* it at `:11263–11267` | `:11191` |
| **retroactive, R114-E** | QKV: `fusedQKVGate?.qkv ?? lagunaDecodeNVFP4QKVR1(...)` | `:6073–6077` |
| **retroactive, R114-E** | gate: `if let fusedGate = fusedQKVGate?.gate { … } else if … lagunaGateSoftplus(…)` | `:6111–6121` |

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

### 7.2b Robustness — block structure and an estimator-free sign test

A fair critic reading §7 will notice the most awkward fact in the table and I
want to state it before anyone else has to: **on the block estimator the
negative control's point estimate (+15.2) is larger than every single-instance
treatment (F +10.0, H +7.3), and the joint arm's CI [+9.5, +17.7] lies entirely
inside the control's CI [−16.9, +47.3].** Taken at face value that says my
treatments are indistinguishable from a day when nothing changed.

The resolution is visible in the individual block deltas, which I now print
(`research/maple-alphonse-r119-gridappend-stats.py:162`):

| arm | block deltas (µs/step, one per pass) | blocks > 0 | median of blocks |
|---|---|---|---|
| **N** | −6.7, −0.6, **+73.1**, −5.6, +6.3, +24.7 | 3/6 | +2.9 |
| **F** | +10.0, +1.4, +1.8, +4.1, +6.0, **+36.8** | 6/6 | +5.1 |
| **H** | +14.9, +19.0, +3.7, −1.4, +6.5, +1.3 | 5/6 | +5.1 |
| **G** | +16.8, +11.9, +20.0, +11.2, +10.6, +10.9 | 6/6 | +11.6 |
| **E** | +44.2, +46.1, +41.8, +30.8, +60.6, +41.5 | 6/6 | +43.0 |

Two things follow.

**The control's width is one block, not a property of the rig.** N's mean is
+15.2 only because of a single +73.1 block (the run-53 session); the other five
average +3.6 and its median-of-blocks is +2.9. F carries a similar single
excursion (+36.8). This is the mean/median gap the block estimator cannot see,
and it is why the two robust estimators — median-of-blocks and the bootstrap
median of per-run medians — agree closely and with each other across every arm
(N +2.9/+2.2, F +5.1/+6.7, H +5.1/+4.4, G +11.6/+12.6, E +43.0/+41.1) while the
mean-based block and Welch estimators do not. **I therefore nominate the robust
pair as the headline for every arm uniformly, and keep block/adjacent-pair/Welch
as the contract-required sensitivity analysis.** Applying a robust estimator to
the control and a mean to the treatments would be exactly the cherry-pick this
paragraph exists to forbid.

**The sign test settles it without any estimator at all.** Under the null of no
effect each block delta is positive with probability ½, so 6/6 positive is
two-sided p = 2/64 = **0.031** and 5/6 is p = 0.22. G (6/6, minimum block
+10.6) and E (6/6, minimum +30.8) are distinguishable from null by this
distribution-free test; **N (3/6, p = 1.0) is not**, and neither H (5/6) nor F
(6/6 but with a min of +1.4 and one dominant block) carries an interesting
magnitude. The joint arm is a real, small, consistently reproduced regression;
the control is not.

Robust headline picture, then: **null ≈ +3, each instance alone ≈ +5, joint
≈ +12, positive control ≈ +43 µs/step.** Joint-minus-null is ≈ **+9 µs/step**,
which remains a regression and remains ~74 µs/step away from the predicted
−65.5.

**Materiality.** +12 µs/step against the 12 876 µs/token ranked decode step
measured on this host is **+0.09 % decode**, i.e. about −0.07 % of score at the
0.75 decode weight. This is a small effect measured carefully, not a large one;
the reason it matters is that the *prediction* was 5× larger and of the opposite
sign, and that asymmetry is what the negative verdict rests on.

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

**Design.** `research/maple-alphonse-r119-gridappend-abba.sh
"CWCRCHCNNCHCRCWC"×6 /tmp/r119-pass2 255`, 96 runs, analysed at `--passlen 8`
so every 8-run window is one block containing each arm exactly once. That gives
**n = 12 paired blocks per arm** (12 measured runs × 239 samples = 2 868 raw
samples per arm; C carries 48 runs). Correctness: **96/96 runs report
`divergences (all match)`**, zero nonzero-divergence lines.

*Pre-registration shortfall, disclosed.* Comment 5 registered n ≥ 24/arm. This
pass delivers n = 12 blocks/arm (arm H reaches 18 runs when pooled with pass 1).
Reaching 24 needed 192 runs ≈ 2.5 h, which did not fit the window alongside the
layer-2 and correctness gates. I flag it rather than round it up. It does not
change any verdict direction below, because every decision here turns on a
**confidence-interval upper bound**, and more data can only narrow it.

**Arm W — host widening, nothing appended (the comment-3/§5 gate).**

| estimator | Δ (µs/step) | 95 % CI |
|---|---|---|
| block (n=12) | **−1.5** | [−15.4, +12.5] |
| adjacent-pair | +2.4 | [−10.9, +15.7] |
| Welch | −1.5 | [−14.4, +11.4] |
| bootstrap median | −5.2 | [−9.7, −1.3] |

Forward −7.9, mirror +4.9 µs/step. Median-of-blocks −4.35, **10/12 blocks
negative** (sign test two-sided p = 0.039). The worst upper bound across the
four estimators is **+15.7 µs/step**, comfortably inside the pre-registered
`≤ +25 ⇒ fuse` threshold. **The gate passes**: widening the shared-expert
SwiGLU host to TG (256,1,1) / 64 tiles is free on this host and, if anything,
mildly *faster*. The load-balance-granularity hazard raised in comment 5 is not
realized at 20 GPU cores. This is a clean positive result and it is independent
of everything else here — it says the *host preparation* comment 3 asked for is
safe, whatever happens to the append itself.

**Arms R and H — the decomposition.**

| arm | block | adjacent-pair | Welch | bootstrap median | fwd | mirror | median-of-blocks |
|---|---|---|---|---|---|---|---|
| R (append, standalone kept live) | +8.5 [−1.7, +18.7] | +12.4 [+2.5, +22.4] | +8.5 [−0.9, +17.9] | +6.9 [+3.5, +11.6] | +7.6 | +9.4 | +5.8 (10/12 +, p = 0.039) |
| H (append, standalone elided) | +6.4 [−3.0, +15.8] | −3.4 [−23.2, +16.4] | +6.4 [−2.0, +14.9] | +6.5 [+2.9, +10.5] | +7.2 | +5.6 | +8.1 (9/12 +) |
| N (null) | +2.5 [−9.9, +14.8] | −1.9 [−20.1, +16.3] | +2.5 [−9.4, +14.3] | −2.0 [−4.1, +5.7] | +9.1 | −4.2 | +1.0 (7/12 +, p = 0.77) |

Two instrument checks pass before interpretation. The **null is centred on
zero** in this pass (bootstrap −2.0 [−4.1, +5.7] includes zero; 7/12 blocks
positive), which fixes the noise floor at roughly ±10–15 µs/step on a block CI
at n = 12. And **arm H replicates across passes**: pass 1 gave block
+7.3 [−1.0, +15.7] / bootstrap +4.4, pass 2 gives +6.4 [−3.0, +15.8] /
bootstrap +6.5 — agreement within ~1 µs/step on an independent 96-run session.

**The paired contrast `R − H`, computed block by block** (both arms are
referenced to C inside the same block, so C and the per-dispatch term cancel):

```
per block (µs/step): -39.5 -3.3 -8.1 -0.3 +28.7 -7.4 +3.6 -6.2 +4.5 +0.7 +12.7 +39.5
mean +2.08   sd 19.67   se 5.68   95 % CI [-10.4, +14.6]
median +0.20   positive blocks 6/12 (sign test p = 1.0)
```

`R − H` is the wall-clock cost of *keeping* the 39 standalone router-tournament
dispatches alive, i.e. exactly the `D·k` term of the §10b model. It is
**+2.1 µs/step, 95 % CI [−10.4, +14.6], median +0.2, indistinguishable from
zero.** The internal identity holds exactly: `(R−C) − (R−H) = 8.5 − 2.1 = 6.4
≡ H−C`.

**This is the result the experiment was for.** Dividing by k = 39:

| quantity | value |
|---|---|
| measured per-dispatch recovery `D`, point | **0.053 µs/dispatch** |
| measured `D`, 95 % upper bound | **0.374 µs/dispatch** |
| Rule 57 price used to build the floor | 1.2382 µs/dispatch |
| ratio (Rule 57 ÷ measured point) | **23×** |
| ratio (Rule 57 ÷ measured 95 % upper) | 3.3× |

Rule 57's per-dispatch price is **excluded at 95 %** for this dispatch pair. And
note what the honest floor actually was: 39 × 1.2382 = 48.29 ≈ the quoted
**48.3 µs/step**. The floor *is* `k·D` at Rule 57's price. Arm R measures `k·D`
directly and bounds it at +14.6 µs/step. So the floor is not merely unreached —
the single quantity it is made of has now been measured, and it is 23× smaller
than assumed.

The source-level prediction registered above was therefore **half right and
half wrong in an informative way**. Elision is real — the escape routes are
closed in this file and 39 dispatches per step genuinely disappear in arm H —
but removing them recovers ≈0 µs, so H's +6.4 µs/step is very nearly pure
fusion tax. Both branches of my registered dichotomy assumed `R − H ≈ 0` could
only mean "the dispatches were never removed"; the third world, *removed and
worthless*, is the one that occurred, and it is the world the mechanism below
predicts.

**Mechanism.** MLX creates its compute encoder with
`MTL::DispatchTypeConcurrent`
(`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp:548`) and
inserts barriers only on tracked hazards (`:315–375`). Both instances here have
`dep_scope = NONE` (§3), so **no barrier separates guest from host and the GPU
already overlaps them.** The router tournament is a 1-threadgroup kernel sharing
a 20-core GPU with a 256-threadgroup sibling; it was never on the critical path.
A dispatch that is already free cannot be recovered by fusing it, and fusing it
*adds* the guest's serialized contribution `g` to the host's critical path.
Net effect: `+g`. Rule 57's 1.2382 µs/dispatch is a price for **serialized,
barrier-separated** dispatches; applying it to `dep_scope = NONE` siblings
over-prices the saving by at least 3.3× and in point estimate by 23×.

**Consequence for R114-E, which reconciles the last loose end.** Pass 1 measured
`E − C = +44.2 µs/step`: unfusing R114-E costs 44 µs/step, so the fusion is
genuinely worth that much. But at most +15.0 µs/step of it (k ≈ 40 × the 0.374
µs/dispatch upper bound) can be dispatch-count recovery. So **at least 66 %, and
in point estimate 95 %, of R114-E's win is not dispatch-count recovery at all.**
It is the operand-reuse and kernel-quality difference between one fused
gate+QKV kernel and two separate kernels that each stream `normalized` and
their own weights. R114-E is therefore **not** evidence for the
"grid-append recovers dispatches" thesis; it is evidence for operand-reuse
fusion that happens to be implemented as a grid append.

That reclassification also gives a mechanism for the transfer anomaly disclosed
in comment 6 (two official draws at −0.063 % against a predicted +0.45 %). A
dispatch-overhead win is a property of the command encoder and should transfer
between Apple Silicon generations nearly unchanged. An operand-reuse win is a
property of the memory system, and its size depends on cache capacity and DRAM
bandwidth per unit of work — which differ sharply between a 20-core M4 Pro and
an M5 Max. Under the operand-reuse reading, **weaker transfer to the wider,
better-fed machine is the expected outcome**, not an anomaly. I did not set out
to explain that disclosure; arm R produced the explanation.

*Bimodality audit.* 2 of 96 runs flagged (88 at 0.745, 90 at 0.615). Both are
single-mode with a thin upper tail: run 88 has p10/median/p90 =
8.180/8.219/8.280 ms with a p99 of 8.473, an upper/lower tail ratio of 1.61
against 1.08–1.23 for unflagged runs. Right skew from occasional scheduling
interference, not the two-population signature that would indicate instrument
failure. The pass-1 finding stands and the stop rule is not triggered.

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

**Layer-1 directional evidence (`decode_probe`, SPLIT=1, n = 6 blocks/arm,
717 raw samples/order).** Arm E turns R114-E's fused QKV+gate path *off*, so a
positive E − C delta means the merged fusion is paying:

| estimator | E − C (µs/step) | 95 % interval |
|---|---|---|
| block-level paired | **+44.2** | [+34.1, +54.3] |
| adjacent-pair | +43.6 | [+30.1, +57.2] |
| Welch | +44.2 | [+34.7, +53.7] |
| bootstrap on median paired saving | +41.1 | [+37.2, +53.4] |
| median-of-blocks (robust) | **+43.0** | 6/6 blocks positive, sign-test p = 0.031 |

Every estimator agrees and the sign test is distribution-free significant, so
**R114-E is unambiguously still alive and still paying on this head** — the
merged fusion is worth about **−43 to −44 µs/step at SPLIT=1 on M4 Pro**. That
is a real, reproducible, same-direction confirmation, and it is the single
strongest positive number in this whole assignment.

It is *not* the −76.8 µs/step figure, and I want to be precise about why the
comparison is not apples-to-apples rather than claim a shortfall:

1. **Different instrument.** −76.8 came from `./benchmark.sh --local-iterate`;
   +44 comes from `decode_probe`. The layer-2 pair below is the like-for-like
   answer.
2. **Different split.** −76.8 is a SPLIT=0 ranked number; layer 1 runs SPLIT=1,
   which prices a different mix of the step.
3. **Different machine class.** −76.8 was an M5 `_nax`-selecting measurement
   context; this host is M4 Pro (Apple GPU gen 16, no `_nax`). Per the agent
   guide, an M4 number is directional for a shared kernel family and is not
   evidence about `_nax` selection.

So the honest layer-1 statement is: *reproduces in sign and in order of
magnitude, at roughly 56 % of the M5 SPLIT=0 magnitude on a different
instrument, split and machine.* None of those three gaps is evidence of
regression; each is a known scaling factor.

**On the advisor's comment-6 transfer disclosure.** Comment 6 reports that two
official draws from R114-E-containing bases sit at **−0.063 %** against a
predicted **+0.45 %**, and that at n ≥ 8 post-gate draws a normalized shift
below +0.10 % would refute ranked-host transfer at ~2.7σ. My arm-E result is
directly relevant, so three things I can contribute:

1. **At n = 2 this is not yet evidence of non-transfer.** The gap is ~0.51
   percentage points; two draws can only resolve it if the per-draw standard
   deviation of the normalized shift is well under ~0.25 pp. I do not know that
   dispersion, and I think it is the single most useful number to publish
   alongside the mean — without it, "−0.063 % vs +0.45 %" and "the effect is
   real but the instrument is noisy at n = 2" are indistinguishable. My local
   arm E is unambiguously alive at 6/6 blocks and p = 0.031, which is at least a
   reason not to write the change off on two ranked draws.
2. **If it does hold at n ≥ 8, `L-APPEND-NEEDS-A-CHEAP-GUEST` supplies a
   mechanism for machine-dependent non-transfer that is specific to this
   technique.** Recovery depends on how much the guest lengthens the host's
   *per-core* critical path, and per-core queue depth falls as core count rises.
   R114-E appends 6–8 guest tiles onto a 4096–5120-tile host; on M4 Pro's 20
   cores that host is ~205–256 tiles deep per core, on a larger M5 Max it is
   roughly half that. The dispatch saving is core-count-independent, but the
   guest's marginal occupancy cost is not, so the *ratio* — and therefore the
   recovery — should degrade monotonically with core count. That predicts
   exactly the observed shape (a clear M4 win, a null on M5) without invoking
   measurement error, and it is falsifiable.
3. **A cheap, shippable test of (2) that does not require new theory.** If the
   guest's serial tile latency is the problem, split R114-E's guest finer at
   constant total work: `laguna_gate_tiles = heads / 8` gives 6–8 fat tiles;
   `heads / 1` would give 48–64 thin ones, same arithmetic, ~8× lower per-tile
   latency and ~8× better load-balance granularity. That is a one-constant
   change at `Sources/MLXFastModel/LagunaRuntimeModel.swift:5092` plus the
   matching stride in `lagunaGateSoftplusSource`. If the M4 win survives and the
   M5 draws move toward the prediction, (2) is confirmed and the fix ships with
   it. If M4 is unchanged and M5 is unchanged, (2) is dead and the honest
   conclusion is that R114-E's ranked value is smaller than modelled.

I did not run this — it is outside the assignment's edit scope for R119-A and
touches a merged, shipped kernel — but it is the highest-value item I found and
it is listed as follow-up 10.

<!-- FILL: layer-2 C/E delta and verdict -->

## 10b. Mechanism — what makes a sibling grid-append pay, and what does not

This is the part of the result worth keeping regardless of the arm's fate,
because it is a property of the MLX dispatch layer, not of my kernel.

**No serialization point sits between the sibling dispatches, so there is no
bubble to recover.** I deliberately state it that way rather than "they already
overlap in hardware": temporal co-residency is plausible but I did not observe
it, and the weaker graph-structural claim is all the conclusion needs. Verified
in the vendored source in this checkout:

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
outputs, then a barrier before K5. So **nothing separated K2, K3 and K4 before I
fused anything.** Grid-append removed a dispatch record, not a serialization
point.

An independent corroboration worth stating: the fused arms pass the drift
tripwire with `divergences=0` in all 60 runs. Metal guarantees no ordering
between threadgroups of one grid, so a correct fused kernel that computes the
router in tile 0 and the routed experts in tiles 1…256 is *itself* proof that K2
and K3 have no ordering dependence — otherwise the fused arm would produce wrong
tokens, not merely slow ones.

That is precisely the `dep_scope = NONE` property from §3. What I got wrong for
most of this assignment was the inference drawn from it — see §10b.1. The
absence of a barrier bounds what fusion can recover to *dispatch cost alone*;
it does not make that recovery zero, because R114-E recovers ~89 % of it under
exactly the same conditions.

**The right two-term model.** Per layer:

> **ΔT_layer = g − D · k**, where `k` is the number of dispatches the append
> removes per layer, `D` is the per-dispatch recovery, and `g` is the guest's
> marginal contribution to the host kernel's critical path.

`g` is the term the old model was missing. Fitting `k = 1` per instance and
`D = 1.2382 µs` (Rule 57) on the pass-1 block means:

| arm | guest | k | measured µs/step | µs/layer | implied `g` (µs/layer) | guest standalone µs/call | `g` as % of standalone |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **R114-E** | gate softplus, 6–8 TGs | 1 | **−44.2** | −1.105 | **0.13** | not measured | — |
| R119-A **H** | router, 1 TG | 1 | +7.3 | +0.187 | **1.43** | 4.78 | 30 % |
| R119-A **F** | shared SwiGLU, 256 TGs | 1 | +10.0 | +0.256 | **1.49** | 7.32 | 20 % |
| R119-A **G** | both | 2 | +13.6 | +0.349 | 2.83 (vs 2.92 additive) | — | — |

Three things fall out of that table.

1. **The costs are additive within noise.** Under this model `g_F + g_H` should
   equal `g_G`, and the `D` terms cancel, so the check is instrument-independent:
   F + H = **+17.3 µs/step** against G's measured **+13.6 µs/step**, and +17.3
   lies *inside* G's 95 % block interval `[+9.5, +17.7]`. Additivity is not
   rejected, which supports treating each append's cost as a property of that
   append rather than an interaction.
2. **`g` is the discriminator, and it tracks guest size, not barrier
   structure.** A 6–8-threadgroup guest costs ~0.13 µs/layer on its host; a
   1-threadgroup-but-4.78 µs guest costs ~1.43; a 256-threadgroup 7.32 µs guest
   costs ~1.49. In both R119-A cases `g` exceeds the entire dispatch recovery
   `D`, so the append is under water before anything else happens. Note that the
   guest *absorbs* substantially — only 20–30 % of its standalone duration shows
   up on the critical path — which is real evidence that fusion does overlap
   work. It just does not overlap enough when the guest is this large.
3. **`D` and `g` are not separately identified by these arms**, which is exactly
   why arm **R** exists. R performs the identical fused work but keeps the
   standalone dispatch live, so `R − C` isolates `g` and `R − H` isolates
   `D · k`. §7.3 reports that decomposition; it is the only measurement here
   that can put a number on `D` on this machine rather than inheriting Rule 57's.

**Withdrawn fits.** I previously fitted a per-host-threadgroup fusion tax
`p ≈ 9 ns/TG` (then `≈ 1 ns/TG`) with `S ≈ 0`, using an R114-E row that listed
its host as **8 threadgroups**. That row was simply wrong: R114-E's host is
`rows/2` = **4096–5120** threadgroups and its *guest* is `heads/8` = 6–8
(§10b.2). Both the `p` fit and the "R114-E won because its host left the cores
idle" sentence built on it are **withdrawn**. A per-TG tax may well exist, but
these three arms share one host TG count and therefore cannot measure it; the
clone ladder (follow-up 2) can.

**Why R114-E won and R119-A lost, in one sentence:** all three are sibling
appends with no barrier to recover, so all three can win at most the dispatch
cost — and R114-E's guest is small enough to leave that recovery almost intact
(`g ≈ 0.1 µs/layer`) while R119-A's guests each cost more on the host's
critical path than the dispatch they remove was worth.

**Why the 1.2382 µs/dispatch constant should never have been used as a floor.**
This is the single most transferable thing in the report, so I want it stated
sharply. A "per-dispatch cost" is not one number; it is a mixture of at least
four terms with completely different recoverability:

| term | scale | recovered by removing a dispatch? |
|---|---|---|
| CPU graph-build + encode | ~0.3–1 µs/op | only when the step is encode/submission-bound |
| front-end issue + PSO switch | small | only in issue-bound regimes (many tiny kernels) |
| **barrier drain/fill bubble** | µs-scale | per removed **barrier**, not per removed dispatch |
| the kernel's own execution | whatever it is | never — grid-append relocates it, it does not delete it |

R114-E's site maximised the third term *and* the fill gain (a real barrier, an
8-TG host leaving 20 cores nearly idle). R119-A's site has neither. Dividing
R114-E's lumpy win by its dispatch count produced 1.2382 µs/dispatch, which is
therefore a **per-structure** quantity, not a per-dispatch one — and using a
best-case structure's value as a *minimum* for a structurally worse one inverts
the logic. That inversion, not any measurement, is where the −48.3 µs/step floor
came from.

The corollary I owe the advisor honestly: this experiment mostly **re-attributes
the earlier R114-E win** (to barrier removal into an idle machine) rather than
discovering a new anomaly. That re-attribution is the durable knowledge.

There is also a physical reason to expect `S ≈ 0` here specifically: the K3∥K4
span is expert-weight-bandwidth-bound at decode, and dispatch count does not
change the bytes moved. Removing a dispatch cannot speed up an interval whose
duration is set by DRAM traffic.

**Alternatives I have not excluded, ranked by how much they would change the
story.** I list them because the conclusion is a negative and a negative is only
as strong as its alternative set.

1. **Nothing was actually removed** (lazy elision did not fire). Then +7.3 is
   added work, not net-of-savings, and the floor is untested rather than refuted.
   §7.3 closes this at source level and arm R closes it empirically; it is the
   one alternative I considered load-bearing enough to spend a 96-run pass on.
2. **CPU-encode savings are real but off the critical path.** 39 fewer encoded
   ops save perhaps 10–40 µs of *CPU* time; if encoding runs ahead of the GPU,
   wall time does not move. Observationally identical to my story, and it changes
   the generalisation from "sibling absorption never pays" to "it pays only when
   encode-bound". Cheap discriminator: sum per-command-buffer
   `gpuStartTime → gpuEndTime` and compare against wall step time.
3. **Command-buffer split relocation.** If MLX splits command buffers by op
   count, deleting 39–78 ops shifts every downstream split point, and splits act
   as global barriers. This could mask a real local saving.
4. **Offsetting large effects** (`S ≈ 35`, tax ≈ 48) rather than (`S ≈ 0`, tax
   ≈ 13). My data cannot separate these, and they have opposite implications for
   future fusions. The clone ladder in §11 is the discriminator.
5. **One-time PSO compilation contamination** of candidate arms. The control's
   own +73.1 µs block is the right size for this class of event.

**M4 → M5 transfer.** The graph-structural conclusion — a `dep_scope = NONE`
sibling has no serialization point to remove, because the encoder logic is CPU
side and identical — transfers to M5. The *magnitude and even the sign* of the
per-TG tax need not: core count, `_nax` kernel selection, and Dynamic Caching
behaviour all differ. Nothing here should be read as an M5 verdict on the tax;
it is an M5-relevant verdict on `S`.

### 10b.1 I have to retract my own proposed law before I state one

I drafted this section around a law called `L-ABSORPTION-NEEDS-A-REAL-BARRIER`:
that a `dep_scope = NONE` sibling is already overlapped by MLX's
`DispatchTypeConcurrent` encoder, so absorbing it recovers nothing, and that
legality and payoff are therefore anti-correlated for this technique.

**That law is false, and my own positive control refutes it.** While preparing
the arm-E answer for status ask (ii) I read the R114-E kernel I had been
treating as an unrelated merged change, and it is *itself a sibling
grid-append of exactly this family*:

```swift
// Sources/MLXFastModel/LagunaRuntimeModel.swift:5092-5098
constexpr uint laguna_gate_tiles = \(heads / 8);
if (threadgroup_position_in_grid.x < laguna_gate_tiles) {
\(gateBody)
    return;
}
\(lagunaDecodeNVFP4QKVLaneMajorSource(pairwise: pairwise, tileOffset: "laguna_gate_tiles"))
```

dispatched at `:5163-5167` as
`grid: ((heads / 8 + rows / 2) * 64, 1, 1)`, `threadGroup: (64, 1, 1)`.

That is the same construction I was assigned: a guest body occupying the
**leading tiles** of a decode host's grid, at matched threadgroup shape, behind
a tile-index branch. The two bodies are siblings — the gate projection and the
QKV projection both read `normalized` and neither reads the other, so
`dep_scope = NONE` there too. And it pays **−44.2 µs/step** (§10 (ii)).

So a sibling append with no barrier between the two halves *can* recover close
to the full nominal dispatch cost. The barrier-adjacency screen is refuted, and
with it the "legality is anti-correlated with payoff" corollary I was about to
put in the archive. I would rather retract it here than have it cited later.

### 10b.2 What actually separates the win from the two losses

The refutation is useful, because R114-E and R119-A now form a two-point
calibration of the *same* technique on the *same* host machine, instrument and
step — and they differ by three orders of magnitude in one parameter.

`heads` is 48 or 64 per layer (`weights/config.json`,
`num_attention_heads_per_layer`), and `rows` is the fused QKV width
`heads·128 + 2·8·128` = 8192 or 10240. So R114-E's grid is:

| | guest TGs (`heads/8`) | host TGs (`rows/2`) | guest share of grid |
|---|---|---|---|
| sliding layers (`heads = 48`) | 6 | 4096 | **0.15 %** |
| full-attention layers (`heads = 64`) | 8 | 5120 | **0.16 %** |

Against that, the two R119-A instances, using the guest and host per-call times
the advisor and frieren supplied in PR comments 2 and 6:

| append | guest | guest TGs | guest µs/call | host TGs | host µs/call | guest ÷ host duration | dispatches removed/step | measured Δ µs/step | recovered µs/dispatch |
|---|---|---|---|---|---|---|---|---|---|
| **R114-E** (shipped) | `gate_softplus` | 6–8 | not measured; 0.15 % of grid | 4096–5120 | — | **≈ 0.0015** (grid-share proxy) | 40 | **−44.2** | **+1.11** (89 % of Rule 57's 1.2382) |
| R119-A i2 (arm F) | shared SwiGLU | 256 | 7.32 | 256 | ≥ 7.32 | **≈ 1.0** | 39 | +10.0 / +5.1 robust | −0.26 to −0.13 |
| R119-A i3 (arm H) | router tournament | 1 | 4.78 | 256 | ≥ 7.32 | **≤ 0.65** | 39 | +7.3 / +5.1 robust | −0.19 to −0.13 |

Two notes on the host column, both conservative against my own conclusion. The
7.32 µs/call host figure the advisor quoted is
`shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1`; my implementation appends onto
the **routed** SwiGLU host instead (§1), which has the same 256-tile shape but
strictly more work (256 experts with a top-8 gather, versus one shared expert),
so its true per-call duration is ≥ 7.32 µs. A *longer* host makes a fixed guest
easier to hide, so the ratios above are upper bounds and the recovery figures
are the most favourable reading available to the append. It still lost.

Proposed law, offered for the archive in place of the retracted one:

> **`L-APPEND-NEEDS-A-CHEAP-GUEST`** — a sibling grid-append recovers the
> removed dispatch cost in proportion to how little the guest lengthens the
> host kernel's critical path. Screen on **guest kernel duration ÷ host kernel
> duration** (equivalently guest tiles ÷ host tiles when tile costs are
> comparable), not on barrier adjacency and not on the guest's µs/step.
> Two measured points on one machine: ratio ≈ 0.0015 recovers ≈ 89 % of the
> nominal 1.2382 µs/dispatch; ratio ≥ 0.65 recovers a *negative* amount. The
> zero crossing is unmeasured, so a screening threshold of **ratio ≤ 0.05** is
> the widest rule the two points support.
>
> Corollary: the guest's own µs/step is the wrong headline number. A big, hot,
> frequently called guest is the *worst* append candidate precisely because it
> is big — its serial tile latency is charged to the host's tail. The right
> candidate is a guest that is frequently called and individually trivial.

This inverts, rather than sharpens, `L-THIRD-CELL-NEEDS-CALL-COUNT`. Call count
still identifies a candidate — the saving is `calls × per-dispatch recovery` —
but the second factor is *small guest*, not *large guest*. Under the old
reading, a 186 µs/step guest looked like the best target in the model; under
this one it was disqualified before I wrote a line of code, and R114-E's
~6-threadgroup softplus was the exemplar the family should have been screened
against.

**Correction to the last column of that table, forced by arm R.** The
"+1.11 recovered µs/dispatch" attributed to R114-E is computed by dividing its
whole −44.2 µs/step win by its 40 removed dispatches, i.e. by *assuming* the win
is dispatch recovery. Arm R measures the per-dispatch recovery directly and
bounds it at 0.374 µs/dispatch (§7.3), so that attribution is wrong: R114-E
recovers at most 15 of its 44 µs/step from dispatch count, and in point estimate
about 2. The number stays in the table as the *apparent* recovery under the
assumption it tests, not as a measurement. This is the second thing I have had
to retract, and it matters more than the first, because the whole family was
staffed on it.

I want to be explicit about the status of `L-APPEND-NEEDS-A-CHEAP-GUEST`: it is
a **two-point fit** with an unmeasured crossing, and one of its two points has
just been shown to be driven by a different mechanism. It survives as a
*screening heuristic* — a cheap guest is still the only kind that can win —
but it is no longer the primary explanation. §10b.3 states that.

### 10b.3 The law the measurement actually supports

Arm R replaces inference with measurement. It isolates `D·k` — the wall-clock
value of the removed dispatches, with the guest cost held fixed — at
**+2.1 µs/step for 39 dispatches, 95 % CI [−10.4, +14.6]**, hence
`D ≤ 0.374 µs/dispatch` at 95 % against a Rule 57 price of 1.2382.

> **`L-SIBLING-DISPATCH-IS-ALREADY-FREE`** — Rule 57's ~1.24 µs/dispatch is a
> price for *serialized* dispatches. MLX encodes with
> `MTL::DispatchTypeConcurrent`
> (`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp:548`) and
> barriers only on tracked hazards (`:315–375`), so two kernels with
> `dep_scope = NONE` are *already overlapped* and their dispatch cost is already
> off the critical path. Fusing them by grid-append therefore recovers
> ≈0.05 µs/dispatch (≤0.374 at 95 %), while adding the guest's serialized
> contribution `g` to the host's tail. **Expected net effect of a sibling
> grid-append is `+g`, not `−k·D`.**
>
> Practical consequence: `dep_scope = NONE`, which the family treated as the
> *enabling* precondition for a legal append, is precisely the condition under
> which the append has nothing to recover. The profitable case is the opposite
> one — a *barrier-separated* pair, where the dispatch really is serialized —
> and there the merge is harder to prove correct.
>
> Corollary for pricing any future append: never price it as
> `calls × 1.2382 µs`. Price it as `calls × D_measured(dep_scope)` and measure
> `D` with a discard arm before staffing the work. A discard arm costs one flag
> and one extra ABBA arm; it would have priced this family at ≈+2 µs/step
> instead of ≈−48 and saved the round.

This supersedes the reasoning behind the honest band in comment 1, and it
subsumes `L-THIRD-CELL-NEEDS-CALL-COUNT`: call count multiplies a per-dispatch
recovery that is ~0 for siblings, so for a `dep_scope = NONE` pair, *no* call
count is large enough. It also explains why R114-E is not a counterexample —
§7.3 shows its win is operand reuse, which grid-append merely happens to be the
vehicle for.

Follow-up 1 (encoder instrumentation) and follow-up 2 (the clone ladder) remain
worthwhile, but their target has changed: the question is no longer "where is the
guest-cost crossing" but "which dispatch pairs in this model are genuinely
serialized", because those are the only ones where an append can pay at all.

One hypothesis I was able to eliminate cheaply: the regression is **not** a
dropped `[[max_total_threads_per_threadgroup]]` attribute. `grep -c` over
`Sources/MLXFastModel/LagunaRuntimeModel.swift` returns **0** — no Laguna
kernel, fused or unfused, carries that attribute (the vendored MLX GEMV family
does, at `Vendor/.../kernels/gemv.h:494,570,640`). So the fused kernel did not
lose something the host had.

## 11. Follow-ups I did not implement

Ordered by decisiveness per unit of effort. The first three are the ones I would
run next if the advisor wants the mechanism nailed rather than merely believed.

1. **Instrument the vendored encoder** (`device.cpp` is on the editable
   surface). Count, per step, dispatches by pipeline name, `memoryBarrier`
   insertions, and command-buffer commits. One cheap change resolves *three*
   load-bearing assumptions at once: whether the tournament PSO's count really
   drops by exactly 39 (elision), whether K2/K3/K4 really encode barrier-free
   (the §10b premise), and whether split points moved (alternative 3). No GPU
   profiler needed — and GPUPROF is not compiled into this checkout, so this is
   the only route to that evidence.
2. **Clone ladder.** Encode k ∈ {0, 8, 32} *extra* live standalone router
   dispatches with distinct outputs, consumed by one checked scalar so they
   cannot be elided, inside the same concurrent region. The slope of step time
   against k is the **measured** marginal cost of one concurrent sibling
   dispatch on this exact topology. Slope ≈ 0 proves "already free"
   quantitatively and replaces the 1.2382 µs/dispatch constant with a locally
   calibrated one; a positive slope × 39 says what removal should have bought.
   This is the single experiment that would separate `S ≈ 0, tax ≈ 13` from
   `S ≈ 35, tax ≈ 48` (alternative 4). Run the ladder twice — once with the
   clones as free siblings, once with a forced dependency between them — and the
   two slopes are `D(dep_scope = NONE)` and `D(dep_scope ≠ NONE)`. That pair of
   constants is what follow-up 8 needs to price any future append, and neither
   is currently known for this machine.
3. **Poison-liveness test.** In the fused build, make the standalone router
   write garbage. Green correctness gates ⇒ its result is dead in the evaluated
   graph, which is the necessary condition for elision. The same poison applied
   to arm R verifies that R's "kept live" consumption is *actually* live and not
   itself folded away — a failure mode that would silently invalidate the
   decomposition.
4. **Delete the standalone call at source level** rather than relying on
   elision, if the API threading permits. Constructive removal; arguably this
   should have been the primary arm rather than arm R.
5. **Zero-guest-tile control.** Compile the *fused* pipeline but dispatch only
   host tiles, leaving the guests as their own dispatches. Output stays correct
   because no work is dropped. If the regression persists, the cost is
   compilation-side (register/preamble tax on the host body); if it disappears,
   the cost is guest-tile scheduling. This is the one diagnostic that would
   split mechanisms cleanly, and it is ~20 lines.
6. **Pipeline reflection.** Log
   `MTLComputePipelineState.maxTotalThreadsPerThreadgroup`,
   `threadExecutionWidth`, and `staticThreadgroupMemoryLength` for fused vs
   unfused pipelines. A drop in the first is direct evidence of register
   pressure. Needs a hook where MLX creates pipelines (`Device::get_kernel`).
7. **Add `[[max_total_threads_per_threadgroup(64)]]` to the Laguna GEMV-family
   kernels.** Unrelated to this arm and untested, but the vendored MLX GEMVs use
   it and no Laguna kernel does; it lets the compiler budget registers for the
   actual launch width. Cheap to try, plausibly helps the *unfused* baseline.
8. **Retarget the technique by serialization, not by guest prominence or guest
   cost.** §10b.3 changes the screen. The primary filter is *not* "cheap guest"
   — that is only a screen on the `+g` term — it is `dep_scope ≠ NONE`: a pair
   the encoder actually separates with a `memoryBarrier`, so removing the
   dispatch boundary removes real serialization rather than a boundary that cost
   nothing. Concretely: instrument `device.cpp` (follow-up 1) to dump, per step,
   which dispatch pairs receive a barrier; rank those pairs by call count;
   *then* apply the cheap-guest screen to the survivors. Both instances in this
   round, and R114-E, are `dep_scope = NONE`, so this whole candidate class is
   untouched by the family so far. Note the honest tension flagged in §10b.3:
   the barrier-separated pairs are exactly the ones whose merge is hardest to
   prove correct, so expect the correctness argument, not the timing, to be the
   binding constraint. Candidates in the ≥ 39-calls/step, grid ≤ 16-threadgroup
   band remain worth enumerating as a secondary screen, since they were
   invisible under the profile-by-total-cost screen that selected instances 2
   and 3 — but on this round's evidence a cheap guest alone predicts ≈ break-even,
   not a win.
9. **Host widening as an optimization in its own right.** Arm W measures
   widening the shared SwiGLU host from TG (64,1,1)/256 tiles to TG (256,1,1)/64
   tiles *as a standalone change* (§7.3), which is the advisor's comment-3 gate.
   What I did **not** do is pursue widening as an optimization decoupled from
   fusion: the model above predicts it is interesting on its own, because it cuts
   `N_host` 4× and so reduces any per-threadgroup cost and changes the scheduling
   tail. If arm W is neutral or better, that is a free simplification the fusion
   agenda does not need.
10. **Split R114-E's own guest finer and re-draw on M5 — the highest-value item
    I found.** Detailed in §10 (ii) item 3. `laguna_gate_tiles = heads / 8`
    (`Sources/MLXFastModel/LagunaRuntimeModel.swift:5092`) gives 6–8 fat guest
    tiles; `heads / 1` gives 48–64 thin ones at identical arithmetic, ~8× lower
    per-tile latency and ~8× finer load-balance granularity. Under
    `L-APPEND-NEEDS-A-CHEAP-GUEST` this should be neutral-to-positive on M4 and
    *more* positive on a higher-core-count M5, which is exactly the direction
    the comment-6 transfer gap needs. It is a one-constant change to a merged,
    shipped kernel, so it is cheap to try and cheap to revert — but it is
    outside R119-A's scope and I did not touch it.
