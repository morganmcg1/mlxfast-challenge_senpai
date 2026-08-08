# R85-C — the placement lever behind PR #443's +13.5 µs/step give-back

## 0. Read this first: two items the advisor must action

1. **PR #460 needs the calibrated noise number and I have no channel to post
   it.** `gh pr comment` is refused by the harness policy
   (`Action rejected: Use a typed Senpai GitHub tool for 'gh pr' mutations`) and
   `respond_to_human_issue` refuses a pull request (`human messages must use an
   issue, not a pull request`). The number tanjiro is waiting for is in §5 and
   durably committed at `research/maple-r85-noise-floor.md`, which ends with a
   ready-to-paste comment. **Please relay it.** Headline correction: the usable
   resolution is **±5.1 µs/step at n=8** with the ratio-adjusted paired
   estimator, not ±13.5 — but only if the estimator is ratio-adjusted. Raw wall
   clock on this host is **±133 µs/step** one-vs-one, 26× worse. #460's SNR
   warning also misattributes the ±13.5 to allocation count; §3 shows allocation
   count contributes nothing.
2. **The research base moved twice mid-arm and the second move is not cosmetic.**
   `f64456d → 6ada66c` adopted organizer promoted frontier `c5b0a13c`, which
   rewrote 1,435 lines of `Sources/MLXFastModel/LagunaRuntimeModel.swift`, 117
   of `LagunaRuntimeWeights.swift`, and the `_nax` quantized kernels. All timing
   here was collected on `cc5688d0` (the assigned base). The methodology and the
   placement bound transfer; the *absolute* per-kernel give-back attribution
   from #443 does not, because `routed_shared_nvfp4_down_residual` — the single
   largest give-back contributor at +8.0 µs/step — went from 2 to 8 references
   in the new runtime. See §7.

- Student / PR: maple-frieren / #457 (`maple-r85-c-placement-lever`,
  `r85-c-rev1`), branch `maple-frieren/r85-placement-lever`
- Decision: **dead hypothesis**, with a well-powered bound and a reusable
  instrument. Not a candidate.
- `BASE_SHA`: assigned `cc5688d0dfd6347bde0efd624cd6e10fdd4cfd26`; advisor
  branch now at `7687c2e` (see §7 for what changed and why I did not rebase).
- Submitted candidate files: **none**. The three probe dials were reverted out
  of `Sources/` before submission per rule 11; the mechanism ships as unapplied
  `research/maple-r85-placement-arms.patch`. Editable-surface growth **0 B**.
- Supporting research files: `research/maple_r85_arm_stats.py`,
  `maple_r85_dispatch_map.py`, `maple_r85_placement_arms.sh`,
  `maple_r85_dose_inertness.sh`, `maple_r85_session.sh`,
  `maple_r85_pad_session.sh`, `maple_r85_analyze.sh`,
  `maple_r85_pad_analyze.sh`, `maple_r85_wandb.py`,
  `research/maple-r85-noise-floor.md`, `research/maple-r85-logs/*.json`,
  `research/maple-pr443-result.md`.
- Official submission `--model` value: n/a (no candidate, no official run).
- Explicit API model-value rejection: n/a.

## 1. Hypothesis and why it mattered

PR #443 halved the shared gate/up scale plane. Its own kernel,
`laguna_shared_nvfp4_swiglu_qmv_rows1_bf16_v1`, got **−17.0 µs/step** faster,
but six kernels #443 never touched got **+13.5 µs/step** slower, so the net
decode effect was zero.

**H**: the give-back is caused by *buffer placement* — the prep-time allocation
order, the address the plane lands at, and the extra resident footprint — and is
therefore controllable. If true, #443's −17.0 µs/step becomes recoverable, worth
≈ **0.26 %** of score at the measured 0.015280 %/µs-step.

**Null**: the give-back is irreducible (it is the price of the read change) or
chaotic. Then the deliverable is a calibrated error bar and a programme rule,
which is not a failure — it is what stops the next three arms chasing it.

The design decomposes #443's single ON arm into two independent halves:

| arm | `HALVED` | `PLACEMENT_DOSE` | `PAD_PAGES` | retained extra planes | read set |
| --- | :-: | :-: | :-: | :-: | --- |
| `base` | 0 | 0 | 0 | 0 | full (81,920 B × 39) |
| `dose_one` | 0 | 1 | 0 | 39, **never read** | full |
| `dose_two` | 0 | 2 | 0 | 78, **never read** | full |
| `halved` | 1 | 0 | 0 | 39, **read** | halved (49,152 B × 39) |
| `halved_pad` | 1 | 0 | 5 | 39 read + 39 pads | halved |

`base → dose_one` moves placement and footprint with the read set held fixed.
`dose_one → halved` moves the read set with the footprint held fixed. #443 only
ever measured the sum of the two.

## 2. Correctness

Every arm is a default-OFF environment dial on **one binary**, so there is no
build differential at all. The dials only decide whether extra planes are
allocated and which of two byte-equivalent planes the kernel is handed.

- **Free-run digest gate (stage 1 and stage 3):** self-fed free run,
  `--free-run-bootstrap 9081 --steps 24 --dump-tokens`; every arm produced the
  identical token digest **`67d6111440bc`**. A free run compounds any
  divergence, so this is stronger than teacher forcing.
- **Plane-construction proof:** stderr shows
  `mlxfast: packed-scales active: shared gate/up halved scale plane` for every
  plane-building arm and never for `base`, and never the `(declined)` variant.
  The dial reaches the scored path rather than silently no-oping.
- **Teacher-forced tokens during timing:** 0 divergences across every timed run
  (33 steps each).
- No `run_upstream_equivalence.sh` run is claimed: rule 35 records that the
  oracle cannot reach `prepareFusedSharedGateUp()`, and there is no
  behaviour-changing candidate here to certify.

## 3. Result: the placement hypothesis is refuted

Estimator: adjacent-duplex, ratio-adjusted GPU-busy contrast over 32 steady
steps at 406 command buffers/step, 12 duplexes per contrast (72 timed runs, one
session, counterbalanced ABBA ordering). "Give-back sum (6)" is the
pre-registered sum over exactly the six kernels #443 moved. Units are µs/step,
brackets are 95 % CIs.

| contrast | isolates | n | **give-back sum (6)** | winner `shared_nvfp4_swiglu_qmv_rows1` | total adj | total abs |
| --- | --- | :-: | ---: | ---: | ---: | ---: |
| `base → dose_one` | placement + footprint | 12 | **−0.29 [−5.62, +5.06]** | −0.12 [−0.64, +0.39] | −1.1 [−8.4, +6.2] | −5.8 [−39.8, +28.3] |
| `base → dose_two` | double footprint | 12 | **−0.02 [−5.24, +5.22]** | −0.09 | +1.0 [−3.3, +5.4] | −8.9 [−39.4, +21.6] |
| `dose_one → dose_two` | second dose step | 12 | **−0.19 [−5.96, +5.60]** | +0.16 | −0.5 [−7.1, +6.1] | +0.9 [−30.9, +32.9] |
| `dose_one → halved` | **read set only** | 12 | **+15.39 [+10.54, +20.26]** | **−16.42 [−17.32, −15.52]** | −3.2 [−10.7, +4.4] | +14.6 [−19.3, +48.6] |
| `base → base` | in-session null | 11 | **+1.98 [−2.90, +6.86]** | +0.10 | +3.0 [−1.2, +7.3] | −13.4 [−48.9, +22.4] |

Reading:

- **Retaining 39 or 78 extra buffers is timing-inert.** All three
  footprint-only contrasts sit on zero with a half-width of ≈ ±5 µs/step, the
  same width as the same-arm null. The bound is not "we could not tell": the
  hypothesised +13.5 is **excluded**, 2.7 half-widths outside the interval.
- **No dose response.** Doubling to 78 planes / ≈6.4 MB does not move it, so
  this is not a capacity effect a larger dose would reveal.
- **The give-back belongs to the read switch and to nothing else.**
  `dose_one → halved`, which holds footprint fixed and changes only which plane
  the kernel reads, reproduces the entire +15.4 µs/step.
- **It very nearly conserves.** +15.39 give-back against −16.42 on the winner;
  the whole-surface ratio-adjusted total is **−3.2 [−10.7, +4.4]**, i.e. no
  demonstrated end-to-end effect.

Per-kernel breakdown of the read switch (`dose_one → halved`, ratio-adjusted
µs/step):

| kernel | adj | abs |
| --- | ---: | ---: |
| `laguna_shared_nvfp4_swiglu_qmv_rows1_bf16_v1` (the target) | **−16.42 [−17.32, −15.52]** | −16.4 |
| `routed_shared_nvfp4_down_residual` | **+8.03 [+7.13, +8.92]** | +9.85 |
| `full_fused_attn_grow` | +2.44 [+1.90, +2.99] | — |
| `sliding_fused_attn_ring` | +2.40 [+1.15, +3.65] | — |
| `gate_sp_h48` | +1.81 [+1.51, +2.11] | — |
| `oproj_act_h64` | +0.45 [−0.58, +1.48] | — |
| `dense_down_residual` | +0.27 [−0.57, +1.11] | — |

Anchor sensitivity (`base → dose_one` give-back sum, four control choices):
default **−0.29 [−5.62, +5.06]**; `residual_rms_router` +4.01 [−3.03, +11.07];
`dense_down_residual` +2.57 [−20.56, +25.89];
`decode_router_top8_ordinal_table_norm` −2.11 [−12.79, +8.61]. **Every interval
contains zero**, so the refutation is not an artifact of the anchor.

Honest note on power growth: at n=4 this contrast read **+5.7 µs/step**, which
looked like "half the give-back". At n=12 it is −0.29. The early hint was noise;
this is exactly why the arm was run to n=12 rather than stopped early.

### 3b. Address displacement (stage 3)

`halved → halved_pad` inserts a retained 5-page (5 × 16 KiB) pad, evaluated
inline strictly before each of the 39 planes, so every plane's address is
displaced and the per-plane stride becomes 8 × 16 KiB = 128 KiB — a power of
two, hence maximally aliasing in any set-associative structure. It ran in the
same session as a `base → halved` positive control, so a null result is
interpretable rather than merely quiet, plus two same-arm null floors from the
counterbalanced pairing phase.

<!-- STAGE3 -->

## 4. A code fact that changes the mechanism ranking

A frontier review ranked "39 new standalone Metal resources / VA islands versus
one big mmapped weight mapping" as the most likely mechanism, and recommended a
full-size fresh-copy arm to test it.

**Code inspection refutes that mechanism outright.**
`prepareFusedSharedGateUp()` builds

```swift
let fusedScales = concatenated([gate.scales, up.scales], axis: 0)
```

and assigns the result to `_fusedGateUpScales`. The **baseline** arm's read
plane is therefore *already* a freshly allocated standalone Metal buffer, not a
view into the mmapped weight blob. There is no mmap-versus-fresh-allocation
differential between `base` and `halved` to test, and the recommended
`copy-not-halve` arm would have been null by construction — a wasted session.

Two further code facts that constrain the interpretation:

- In the halved arm `_fusedGateUpScales` survives only for CPU-side dtype/shape
  guards on decode (`fusedSharedBankGuard`); the kernel is handed
  `_fusedGateUpHalvedScales`. The read set really does shrink by 32,832 B × 39
  per step. Freeing the full plane is not possible anyway — the prefill
  multi-row path still needs it.
- `Sources/MLXFastHarness/LagunaRuntimeWorker.swift:173-192`
  (`resetRuntimeWorkerAllocatorForPhaseStart`, non-editable) sets
  `Memory.cacheLimit = 6 << 30` and calls `Memory.clearCache()` at every phase
  start with a fail-closed `cacheMemory == 0` postcondition. Transient prep
  allocations and allocator-cache reuse therefore cannot reach the timed window;
  only *retained live* buffers differ between arms. The "clearCache epilogue"
  control an allocation-order hypothesis would need is already supplied by the
  trusted harness — a second, independent reason the allocation-order story was
  never viable.

Also ruled out before spending timing on them: residency/wiring
(`resident.h:31` `capacity_ = 0` on M4; `DARKBLOOM_WIRED_ZH` is gated ≥ 96 GiB
at `LagunaRuntimeWeights.swift:520-522`), and dispatch adjacency
(`research/maple_r85_dispatch_map.py`: the subject sits at dispatch indices
15, 25, 35 …; within ±2 only `oproj_act_h64` is a mover, the other five are 0 %,
and always-adjacent non-movers never move).

**Programme lesson:** a frontier mechanism ranking is a hypothesis generator,
not evidence. Ten minutes of `grep` invalidated its top-ranked mechanism and its
recommended arm.

## 5. Deliverable: the calibrated noise floor (this is what #460 needs)

From 55–72 timed runs of **one** binary in one session, arms differing only by
an environment variable — so every number below is pure measurement noise, not a
treatment effect. Durable copy: `research/maple-r85-noise-floor.md`.

| estimator | SD | 95 % half-width, 1 run/side | at n=8/side | resolves 38 µs/step? |
| --- | ---: | ---: | ---: | :-: |
| whole-step **wall clock** | ≈48 µs/step (robust IQR) | **±133** (≈2.0 % of score) | ±33 | **no** |
| whole-step **GPU busy sum** | 32–50 | ±100–139 | ±25–35 | **no** |
| whole-step GPU busy, **ratio-adjusted paired** | 6.1–12.0 per duplex | ±17–24 | **±5.1** (≈0.078 %) | **yes** |
| **per-kernel**, ratio-adjusted paired | — | — | **±0.3–2.0** | **yes** |

Supporting detail:

- Per-arm wall means (µs/step): base 9830.2 (SD 124.2, n=19), `dose_one` 9805.0
  (44.4, n=18), `dose_two` 9793.3 (49.9, n=9), `halved` 9795.6 (53.3, n=9).
  Busy means ≈8544–8553 (SD 32–50). The base SD of 124 is inflated entirely by
  slot 1 — see the next bullet.
- **First-run penalty: slot 1 = 10,244 µs/step versus a session median of 9,780
  ⇒ +464 µs/step, about 12× the effect being hunted. Always discard the first
  timed run of a session.** Every runner here numbers slots from 01 after an
  unscored warm-up for exactly this reason.
- No session drift: first half 9,814.5 versus second half 9,806.2 µs/step.
- Unpaired wall clock needs **n ≈ 26 runs per side** to see 38 µs/step
  (2·(1.96·48/38)²). Single-run A/B wall-clock comparison on this host is not
  evidence.
- The absolute (unadjusted) whole-step total is ≈4.4× noisier than the
  ratio-adjusted one (SD 39.75 versus 9.59 on #443's logs). **Whole-step
  absolute totals are effectively unidentifiable on this host** at any run count
  we can afford.

Conditions the ratio adjustment needs to stay honest — carry these into #460:

1. The control must be a kernel from a file **outside** the change under test,
   and it must be named in the write-up.
2. Report the absolute total as well, so a reader can see the adjustment's size.
3. The adjustment is invalid if the change moves **every** kernel; selectivity
   is the signal.
4. Diagnostic shapes: a real effect is selective (≈6 of ~40 kernels here);
   sibling kernel variants moving in **opposite** directions
   (`gate_sp_h48` +2.005 % versus `gate_sp_h64` −0.247 %; `oproj_act_h64`
   +0.13 % versus `oproj_act_h48` −0.20 %) is a signature of redistribution, not
   of a uniform session artifact. Anything uniform across all kernels is a
   session artifact.
5. The floor above was calibrated on the **`cc5688d0`-era** worker
   (≈9.8 ms/step). The new frontier changes step composition; the SDs should be
   re-checked, though the methodology and the first-run penalty carry over.

## 6. Free re-analysis of #443's archived logs

#443's 48 archived `.err` files were re-analysed with the same estimator at no
GPU cost, as an independent replication:

- Reproduces #443 exactly: give-back **+13.5 [+5.5, +21.6]**, total adj
  −3.5 [−7.6, +0.5], total abs +0.7 [−16.0, +17.5].
- Pooled n=24 adj/abs: winner **−16.95 [−17.34, −16.56] / −16.81**;
  `down_residual` +7.97/+8.41; `sliding_ring` +2.95/+3.26; `attn_grow`
  +2.10/+2.22; `gate_sp_h48` +1.55/+1.59; `oproj_h64` +1.39/+1.94; `dense_down`
  +0.62/+0.69; control abs +0.75 [−2.56, +4.06].
- Determinism across two independent counterbalanced orderings: +16.5 versus
  +16.7 on the winner.
- #443's defensible statement, restated: **net decode-step effect zero to within
  ≈±8 µs/step (≲0.12 % of score)**; anchor sensitivity spans −16.2 … +18.5
  across five anchors, and the pre-registered anchor gives −5.0 [−9.9, −0.0].
- Correction to #443's assignment text: the ≈80 µs/step decode bar it quotes is
  ≈**1.55 %** of score, not 27 µs.

## 7. Base movement and M5 transfer risk

- `cc5688d0 → f64456d` (R85-A, merged): one line in
  `Vendor/mlx-swift-lm/.../RoPEApplication.swift`, later reverted. Immaterial.
- `f64456d → 6ada66c`: **adopted organizer promoted frontier `c5b0a13c`** —
  `LagunaRuntimeModel.swift` 1,435 lines changed, `LagunaRuntimeWeights.swift`
  117, plus `LagunaLmHeadPrune.swift`, `fp_quantized_nax.{cpp,h}`,
  `matmul.cpp`, `quantized.cpp`.
- `6ada66c → 7687c2e` (R85-D): research-only.

I did **not** rebase. Reverting the dials leaves this branch touching only
`research/`, so it merges cleanly onto `7687c2e`; rebasing the dials through a
1,435-line rewrite of the file they patch would have risked silently changing
the instrument after the evidence was collected. The
`research/maple-r85-placement-arms.patch` header records that it applies to
`cc5688d0` and needs re-porting.

What survives the base move:

- The **noise-floor methodology**, the first-run penalty, the anchor rules, and
  the redistribution diagnostics — properties of the probe, not of the model.
- The **placement bound**. "Retaining ≤78 extra buffers / ≈6.4 MB of resident
  live allocations costs ≤5 µs/step" is allocator and memory-system physics, not
  a property of one kernel mix.

What does not survive:

- The **absolute per-kernel give-back attribution**.
  `routed_shared_nvfp4_down_residual`, which supplied +8.0 of the +13.5 µs/step,
  went from 2 to 8 references in the new runtime. Whether #443's halving is
  still net-zero on the new frontier is now an **open question**, not a settled
  one.
- M5 transfer generally: this host is Apple GPU generation 16, does not select
  `_nax`, and threadgroup geometry can change sign across core counts. A
  placement/aliasing term in particular need not transfer — different SLC
  geometry, different page behaviour, 128 GB versus 48 GiB, and residency
  actually enabled on the M5 (`capacity_ = 0` here). The refutation is therefore
  "placement is not the lever **on M4 Pro**"; what generalises is that we have
  no evidence for it anywhere plus a cheap way to check.

## 8. Ranked-channel facts (corrected per advisor comment 5227928788)

For anyone reading this arm as part of the R85 round: the ranked channel is
**not** red. Control receipt `25b0b722` (2026-08-08T19:38:03Z) reports
`status=rejected`, `rejectionReason="score did not improve current best"`,
officialScore **2.55158458026643**, `passed_correctness=true`,
`max_abs_diff=0`, 1,344 checked steps, GPQA 9/9, TTFT 9/9, decode speedup
2.804381, prefill 1.921890 — **both floors passed**. The recent failure series
belonged to the other (Birch) campaign's M5 build failures. Because
`--model "senpai"` is campaign-wide, the **note body** is the discriminator, not
the model tag.

Score landscape: base **2.5516**; our best-ever promoted **2.5888**
(`97a5090c`); external leaderboard bar **2.6165035** (`cc6ddc1`, solver
`a-github-name`). #443's −17.0 µs/step, had it survived, would have been
≈ **0.26 %** at 0.015280 %/µs-step. This arm produces no ranked receipt by
design — there is no candidate to submit.

## 9. Proposed programme rule

> **Per-kernel GPU-timestamp deltas redistribute under shared-bandwidth
> back-pressure and must not be summed into a net claim.** With ≈406 command
> buffers per step and only ≈12.5 % gap, the decode pipeline is near-saturated:
> when one kernel finishes earlier, its successors overlap its residual DRAM
> drain and absorb the time. Conservation is then partly *by construction*, and
> non-adjacency in the dispatch order is no defence.
>
> A read-set change is reportable only with (a) the whole-step ratio-adjusted
> estimate at n ≥ 8 duplexes, (b) a full-surface redistribution audit, and (c) a
> named control from outside the changed file. **|net| below ±5 µs/step means
> "no demonstrated end-to-end effect", not "no effect".**
>
> **Retained prep-time allocations up to 78 buffers / ≈6.4 MB are bounded at
> ≤5 µs/step on M4 Pro (95 %, n=12, three independent contrasts, four anchors).
> Do not spend further sessions on allocation-count or allocation-order
> hygiene.** M4 evidence is directional only.

Roofline sanity check supporting the "≈0 net is real" reading: halving removes
39 × 32,832 B ≈ **1.28 MB/step**. A −17 µs/step saving implies ≈75 GB/s of saved
stream against ≈273 GB/s of M4 Pro peak — physically plausible. So the true net
is roofline-bounded to single-digit µs/step *unless* the redistribution tax can
be removed, which is what §10 proposes.

## 10. Smallest useful next action

The one mechanism left that could turn #443's −17 µs/step into an identifiable
*net* win is **consolidation, not placement**: allocate all 39 halved planes as
slices of **one contiguous buffer**, taking 39 resources to 1. That attacks
per-resource argument-table and page-mapping overhead rather than the address
lottery this arm just closed. It was deliberately not attempted here because
byte-exact aliasing through MLX views/slices is implementation-risky and would
have confounded the clean footprint contrast. It should be a separate arm, run
**on the new frontier**, because `down_residual` has changed.

Second-cheapest: re-run `dose_one → halved` on `7687c2e` — 12 duplexes,
≈30 minutes, no new code beyond re-porting the patch — to learn whether #443's
give-back still exists at all after the frontier adoption. That is a
prerequisite for the consolidation arm being worth funding.

- Recommendation: **close** #457 as a well-powered negative plus a reusable
  instrument. Relay §5 to #460. Fund the frontier re-check before the
  consolidation arm.
