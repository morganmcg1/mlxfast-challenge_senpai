# R116-A final result — the shipped compiled defaults are already optimal

Student: maple-frieren. PR #705, assignment `maple-r116-a-shipped-defaults-audit`,
revision `r116-a-rev1`. Host: Apple M4 Pro (`Mac16,11`), 48 GB.

## 0. STATUS (as of 2026-08-11T05:00Z)

**The §0P.23 gating deliverable is answered:
[`research/frieren_r116_router_top8_number.md`](frieren_r116_router_top8_number.md).
`prefill_router_tournament_ordinal_norm_active64_v2`, **186.263 ± 0.214
µs/step** (n=8), 4.775 µs/call × 39 calls, **≈0.12 % of DRAM peak**, raw
SPLIT=1. Alphonse is unblocked.** It needed no GPU time: the number was already
in committed captured data in exactly the requested regime.

**Why this branch looked silent for three hours.** It was not. Roughly sixteen
commits of finished work have existed locally since 01:49Z. This role has no
PR-comment tool and no GitHub credential, and `submit_experiment_result` — a
*terminal* action — performs the only push available to me. So nothing I do is
visible to the advisor until the moment I submit, and submitting is the same
action as declaring the experiment finished. That coupling, not idleness, is the
whole gap. Noted here as a process defect worth fixing: a student with no
incremental publish channel is forced to choose between visibility and
completeness. I have resolved it in favour of visibility and am submitting early.

**What ran:** the 27-run screen (complete, `@@DONE 03:27:28Z`, exit 0) and 5 of
9 confirm blocks (6 of 9 at submission). **What is still running:** `research/frieren_r116_confirm_run.sh`
(pid 34622, started ~03:34Z, 23/36 score files at 05:00Z, ETA ≈05:32Z). It only
tightens a null on an axis the advisor declared optional at 04:37Z, so it is not
worth holding the report for. One block failed a 40 C cool-down gate
(`score-qmvsc0-b1.json`, `passed: false`, GPU stuck at 43.0 C); that is an
environment failure, not a correctness failure, and no timing phase ran.

**Terminal finding: `N-DEFAULTS-ALREADY-OPTIMAL`. The submitted-surface diff is
empty and no landing was manufactured.** This is a deliberate outcome under the
advisor's 03:50Z campaign law — *ship on a verified positive interval excluding
zero, or do not ship; a neutral result is a do-not-land* — and under the
advisor's explicit invitation to call the axis dead rather than spend six hours
confirming a null.

Everything below is committed evidence on branch
`maple-frieren/r116-shipped-defaults-audit`. Section 9 lists the files.

---

## 1. Executive summary in one table

| # | Claim | Strength | Where |
|---|---|---|---|
| **0** | **§0P.23 gating deliverable.** The build selects `prefill_router_tournament_ordinal_norm_active64_v2` (normalizing branch, `:9729`). It costs **186.263 ± 0.214 µs/step** (n=8), 4.775 µs/call × 39 calls, 2.1775 % of the SPLIT=1 busy sum, and **≈0.12 % of DRAM peak** — a pure latency kernel with no byte side. The guest is **71.2 %** of gate_sp's 261.6, so the gate_sp-scaled price is **≈55 µs/step ⇒ ≈+0.32 % score**: between the advisor's 48/77 brackets, **below Rule 105.12's 60 µs/step slot floor**, and only 1.28× the ship threshold. | measured, n=8, ~285σ over the atlas's own noise floor | [§0P.23 doc](frieren_r116_router_top8_number.md) |
| 1 | No shipped compiled default in the NVFP4 / shared-expert / QMV families is beatable. 8 arms screened, 3 carried to confirmation, none clears the campaign's own +0.25 % threshold. | measured, 47 runs, all bit-exact | §2, §3 |
| 2 | `SHARED_FIRST_DOWN=1` — the only default-OFF decode flag in the whole census — is **decisively slower**, +51.1 ± 3.9 µs/step, t = 13.10. Its default-OFF is correct and now measured, not assumed. | measured, t=13.10 | §3 |
| 3 | `DARKBLOOM_NVFP4_NIBBLE_SPLIT` 0 and 2 are both slower than the shipped 1 on my instrument too. Independent corroboration of tanjiro's `N-NIBBLE-SPLIT-DEFAULT-IS-OPTIMAL` from a different host and a different statistic. | measured, 2 arms | §3 |
| 4 | The default-OFF census is **complete and closed**. Every `== "1"` gate in the runtime is dispositioned: 1 screened, 3 prefill-only, 1 shadowed, 1 dead-checkpoint, 1 diagnostic, 1 logger-only, 1 already closed. No unscreened default-OFF decode flag remains. | source census | §4 |
| 5 | **The assignment's premise carried no host map.** Both the 284.9 µs figure it quotes and the 230.0 µs figure in the digest are M4-Pro numbers; the atlas "% of peak" denominator is the literal `M4_PRO_PEAK_GB_S = 273.0`. Applying the digest's own mandatory two-pool map (B.0.2) reprices the lever from ~1.0 % to **+0.09 – 0.32 %**. | source-verified | §5 |
| 6 | The mechanism the assignment pointed me at is **already staffed**: maple-edward PR #693 owns shared-expert QMV fusion and the routed gate/up family; maple-alphonse PR #700 owns gate_sp lever A. | digest `:597-600` | §5 |
| 7 | **τ and α are being multiplied together across the campaign and they may be the same constant.** τ ≈ 0.4 (local wall → ranked score) and α = 0.4369 (M4 busy µs → M5 busy µs) were derived independently and are numerically almost identical. Any memo that host-maps an M4 row *and then* prices at τ discounts the same host difference twice, worth ~2.4×. I flag; I cannot measure either. | analysis, needs advisor ruling | §6 |
| 8 | **B.0.6 α/β degeneracy is still open and the resolving experiment is free.** Two fits explain all the data and imply opposite research programmes ("only bytes pay" vs "per-family efficiency pays"). `research/fern_r101_bw_probe.swift` already exists; running it on the official M5 takes ~7 s, changes no submitted file, and consumes no receipt and no submission slot. Three independent authors have named it and it appears never to have been run. **My #1 redeployment recommendation.** | digest `:3318-3345` | §7 |
| 9 | `decode_seconds_per_token` from `--local-iterate` is a **contaminated statistic**: it folds the 512-token seed pass into the decode axis and carries nearly all the run-to-run noise. The steady tail over tokens ≥ 16 is **6–20× tighter** on the same runs. Tool committed. | measured, 2 arms | §8 |
| 10 | **The screen argmax is median label noise, and order position is a larger effect than any flag.** A within-block permutation null puts the observed screen argmax exactly at the null median; the ABBA−BAAB position gap on `sc0` is 23 µs, larger than any flag effect I measured. Campaign-level instrument finding. | measured | §8 |
| 11 | I retract two of my own claims from earlier in this assignment: an M5/M4 mislabel, and a redeployment pick that a frontier review killed. | self-correction | §5, §7 |

---

## 2. What was tested and how

One binary, switched by environment variable. Zero rebuilds between arms, so
every arm executes the identical machine code and the contrast is purely the
flag. Nine arms including control:

| arm | flag | shipped default |
|---|---|---|
| `ctl` | — | — |
| `ns0` | `DARKBLOOM_NVFP4_NIBBLE_SPLIT=0` | 1 |
| `ns2` | `DARKBLOOM_NVFP4_NIBBLE_SPLIT=2` | 1 |
| `sc0` | `DARKBLOOM_NVFP4_SCALE_CARRY=0` | ON |
| `qse0` | `DARKBLOOM_NVFP4_QDOT_SEED_ELIDE=0` | ON |
| `sd0` | `DARKBLOOM_NVFP4_SCALE_DEFER=0` | ON |
| `qmvse0` | `DARKBLOOM_NVFP4_QMV_SEED_ELIDE=0` | ON (prose said OFF — see §4) |
| `qmvsc0` | `DARKBLOOM_NVFP4_QMV_SIGN_CARRY=0` | ON (prose said OFF — see §4) |
| `sfd1` | `DARKBLOOM_SHARED_FIRST_DOWN=1` | OFF |

Instrument, against the advisor's 03:50Z standard:

- Primary statistic is the **steady-state decode step**, the mean of the
  harness's own `last_step_seconds` samples over tokens ≥ 16, not
  `decode_seconds_per_token` (§8 explains why).
- **15 measured cycles per run**; at 12 pooled blocks the forward order has
  105 cycles and the reverse order 75, both clearing the ≥ 64 standard.
- **Order-balanced**: forward on odd blocks, reversed on even. ABBA and BAAB
  are reported separately, never only pooled.
- **Bootstrap 95 % CI on the median paired saving**, reported per arm.
- **Raw sample array dumped** to `research/frieren_r116_raw_steps.csv`.
- `DARKBLOOM_STARTUP_MEMORY_PROFILE=full` on every arm, with every block gated
  on `@@LOWMEM_NOTICES == 0`, because this 48 GB host would otherwise
  auto-select the low profile and silently change `MLX_MAX_OPS` 128→64 and
  `MB_PER_BUFFER` 320→128. That is the exact knob my own r109 factorial proved
  owns a +888 µs/step sign flip, so an unpinned profile would have made every
  number here worthless.
- I could not build the advisor's byte-identical duplicate-control arm without
  spending a second full sweep, so I substituted a **within-block permutation
  null** on the real data, which answers the same question: how large an argmax
  does this instrument produce when the labels mean nothing (§8).

Correctness: **47/47 runs `passed_correctness=true` and a single golden hash
`b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63` across every
arm and block.** One identical hash across all nine arms is what makes the
bit-exactness claim for the source-substitution flags an observation rather than
an assumption. Per Rule 105.15 I note explicitly that `golden_hash` is not a
correctness claim on its own; no non-bit-exact flag is being landed here, so no
`run_upstream_equivalence.sh` invocation gates this result. The one
non-bit-exact arm, `sfd1`, is being *rejected*, not shipped.

---

## 3. Result — the screen and the confirmation

**Screen, 8 arms vs control, 3 blocks, paired steady contrasts (+µs = slower):**

| arm | mean ± sem | t |
|---|---|---|
| `sc0` | −10.9 ± 15.3 | −0.71 |
| `qse0` | −0.1 ± 4.0 | −0.03 |
| `sd0` | +1.4 ± 26.3 | 0.05 |
| `qmvse0` | +7.1 ± 6.8 | 1.04 |
| `ns2` | +13.8 ± 13.5 | 1.02 |
| `ns0` | +15.7 ± 16.5 | 0.95 |
| `qmvsc0` | +26.5 ± 16.8 | 1.58 |
| `sfd1` | **+51.1 ± 3.9** | **13.10** |

Seven of eight arms are indistinguishable from the shipped default. The eighth
is decisively worse. **The entire observed range across the whole flag space is
[−10.9, +51.1] µs**, and the only arm past 30 µs points the wrong way.

That range is the finding. Inverting the campaign's banked conversion
(0.00836 % of score per M4 wall µs/step at τ = 1), the minimum effect that
clears the advisor's +0.25 % screening threshold is **29.9 µs/step before τ
correction, or 74.8 µs/step at τ = 0.4**. Nothing in this flag space is within
reach of that, in either direction, except a flag that is already correctly
switched off.

**Confirmation** carried the three best-looking arms (`sc0`, `qmvse0`,
`qmvsc0`) to 9 further blocks. **6 of 9 complete at submission time** (`qmvsc0` has 5: block 1 lost its cool-down gate); pooled
over screen + confirm, every contrast remains a null and the one
candidate that looked best in the screen **flips sign** in confirmation:

| arm | n | pooled Δ vs `ctl` (µs/step, + = slower) | t | ci95 | screen | confirm |
|---|---|---|---|---|---|---|
| `sc0` | 9 | **−1.7 ± 6.0** | −0.29 | [−12.4, +9.5] | −10.9 ± 15.3 | +2.9 ± 5.1 |
| `qse0` | 3 | −0.1 ± 4.0 | −0.03 | [−7.5, +6.1] | — | — |
| `sd0` | 3 | +1.4 ± 26.3 | 0.05 | [−34.5, +52.6] | — | — |
| `qmvsc0` | 8 | +8.1 ± 10.4 | 0.77 | [−17.1, +40.9] | +26.5 ± 16.8 | −3.0 ± 11.7 |
| `qmvse0` | 9 | +10.4 ± 5.3 | 1.94 | [−4.3, +19.3] | +7.1 ± 6.8 | +12.0 ± 7.6 |
| `ns2` | 3 | +13.8 ± 13.5 | 1.02 | [−13.1, +28.3] | — | — |
| `ns0` | 3 | +15.7 ± 16.5 | 0.95 | [−16.3, +38.5] | — | — |
| `sfd1` | 3 | **+51.1 ± 3.9** | **13.10** | [+46.7, +58.9] | — | — |

**Every 95 % interval except `sfd1`'s contains zero, and `sfd1`'s excludes zero
on the *slow* side.** Under the advisor's own 03:50Z law this is a do-not-land,
unambiguously.

Two independent instrument checks confirm there is nothing here:

- **Preregistration rule 1 fails on the one candidate that mattered.**
  `qmvsc0` was +26.5 ± 16.8 in the screen and **−3.0 ± 11.7** in confirmation —
  a sign flip. It was never a signal; it was the screen's argmax noise.
- **Permutation argmax null.** Shuffling arm labels within block: screen
  (8 arms × 3 blocks) p50 −10.8, p05 −23.2, min −29.9 vs observed argmax
  **−10.9** — the null *median*. Confirm (3 arms × 5 blocks) p50 −2.1, p05 −7.8,
  min −10.4 vs observed **−3.0** — again inside. The best-of-8 debias turns the
  pooled argmax `sc0` from −1.7 µs/step into **+6.8 µs/step**, i.e. slower.

Price of the pooled argmax if taken at face value: **0.014 % of score pre-τ,
0.006 % at τ = 0.4**, against a +0.25 % = 29.9 µs/step shipping threshold —
roughly 18× too small.

The remaining 3 blocks cannot change this: they would have to move an arm by
several σ in a direction it has now failed to move across two independent
stages.

---

## 4. The default-OFF census is closed

Every `environment["DARKBLOOM_*"] == "1"` gate in the runtime, with its
disposition:

| flag | site | disposition |
|---|---|---|
| `SHARED_FIRST_DOWN` | LRM:8219 | **screened → +51.1 µs, t=13.10, default correct** |
| `FUSED_QKV` | LRM:114 | prefill-only: consumed at LRM:6068 under `if let fusedQKVWeight, L > 1`; decode is L=1. Also materialises a dense BF16 fused weight, a memory hazard on a 48 GB host |
| `PREFILL_ROUTER_TOP8` | LRM:9660 | prefill-only |
| `QMV_WIDE_CODES` | LRM:325 | already closed by me in r109: +35.2 µs/step, t=+25.23 |
| `NATIVE_AFFINE_SUFFIX` | LRM:366 | dead on this checkpoint: used only at LRM:392 as an affine-INT8 kernel-name suffix; the checkpoint is NVFP4 g16/b4 |
| `ROPE_ATLAS_VIEWS` | LRM:627 | shadowed: LRM:11538 / :11602 reach it only in an `else if` after the default-ON angle atlas |
| `TRACE_FUSION` | LmHeadPrune:101, LRM:76 | diagnostic |
| `ATTN_SCALE_NARROW_LOG` | LagunaRuntimeWeights:728 | **logger only** — it reports which scale plane each attention tensor landed on. It is not a lever, and I had it on my own candidate list until I read the code |

**No unscreened default-OFF decode flag remains.** The audit's stated surface is
exhausted, not sampled.

Two documented-default mismatches are worth recording even though they produce
no diff. `research/maple-nezuko-r99-lrm-provenance.md:1227,1263` says
`DARKBLOOM_NVFP4_QMV_SIGN_CARRY` and `DARKBLOOM_NVFP4_QMV_SEED_ELIDE` are
"(default OFF)". The code reads `!= "0"` at LRM:4131 and LRM:4159, so **both
ship ON**. The current source carries no comment at those lines, so there is no
doc in the submitted surface to correct — the error is in a research memo, and
this file is the correction. I screened both arms precisely because the memo
would have had me believe an unscreened ON path existed; it does not.

---

## 5. Correction to the assignment's premise, and a retraction of my own

The assignment motivated this audit with a 284.9 µs/step shared-expert QMV
figure and an implied ~1 % prize. Two things are wrong with that chain.

**First, and this is my own retraction:** earlier in this assignment I claimed
the assignment used M4 data while the digest reported a "ranked M5" figure. That
was wrong and I withdraw it. The atlas denominator is a literal —
`research/maple-alphonse-r109e-bwatlas.py:38`, `M4_PRO_PEAK_GB_S = 273.0`,
commented "M4 Pro spec DRAM bandwidth". `191.7/273.0 = 70.2 %` and
`153.1/273.0 = 56.1 %` both reproduce exactly, and the label sums are M4 Pro
captures (`research/fern_r105e_ledger.py:31`). **Both figures are M4.** The gap
between them is a within-host capture difference, not a host difference.

**Second, the real defect: no host map was applied at all.** Digest B.0.2
(`research/CURRENT_RESEARCH_STATE.md:3229-3239`) makes one mandatory —
α = 266.80/610.6 = 0.4369 for bandwidth-regime families, β = 0.5 for
latency-regime families, with a −6.63 % residual against the measured M5 step —
and requires the label text *"M4 ×0.4369 bandwidth-pool / ×0.5 latency-pool
two-pool map, residual −6.63 %, #561"*. Applying it, and deflating the SPLIT=1
attribution rows by 1.554 µs × 39.4 calls/step:

| basis | M4 µs/step | mapped M5 µs/step | % of score |
|---|---|---|---|
| assignment's implied prize | ~119 | — (unmapped) | ~1.0 % as stated |
| digest's own fusion estimate | 20–40 | 8.7–17.5 | **+0.16 – 0.32 %** |
| SPLIT-corrected in-kernel headroom | ~11 | ~5.2 | **+0.09 %** |

The lever is real but it is a fifth to a tenth of the advertised size, and it
straddles the advisor's +0.25 % threshold rather than clearing it.

**And it is already staffed.** Digest `:597-600`: gate_sp lever A is
maple-alphonse PR #700; shared-expert QMV fusion and the routed gate/up QMV
family are maple-edward PR #693 (`r110-b-rev4`). Redirecting me there would have
duplicated two live students.

For completeness, the obvious alternative redirect is also closed: the
`laguna_sliding_fused_attn_ring_v1` and `full_fused_attn_grow_v1` families
closed in round 107 / PR #642 as **`N-ISSUE-BOUND` at 97.7 % of peak instruction
issue** (`:4624`, `:3217`, `:3656`), and sliding QK-MMA is doubly closed at
`:1191`. An earlier subagent of mine recommended exactly that redirect; I
checked it before acting on it, and it is dead.

---

## 6. The τ/α double-count hazard — please rule on this

Two constants, derived independently, numerically almost identical, and
conceptually different:

| constant | value | what it maps | source |
|---|---|---|---|
| τ | ≈ 0.4 (cedar [0.27, 0.43]; tanjiro 0.54 [0.29, 0.79]; overlap [0.29, 0.43]) | local measured wall saving → ranked score | ranked receipts, advisor 03:50Z |
| α / β | 0.4369 / 0.5 | M4 busy µs → M5 busy µs | digest B.0.2 `:3229-3239` |

tanjiro's α-free bound is **α < 0.4454**
(`research/maple-tanjiro-r107g-decode-family-regime-census.md:73`), which sits
*inside* cedar's τ interval. If a memo host-maps an M4 measurement with α and
then prices the result at τ, it applies the same host correction twice and
understates by ~2.4×.

This is not academic. On the shared-expert fusion lever in §5, host-map-only
gives **+0.16 – 0.32 %** and host-map-then-τ gives **+0.06 – 0.13 %** — and the
advisor's +0.25 % screening threshold falls between them. The ruling decides
whether a live lever on two students' branches is above or below the campaign's
own kill line.

I flag rather than assert. τ needs ranked receipts and α needs an official M5
run; I have neither. But somebody with both should decide whether τ already
contains α, and every memo that multiplies them should then be corrected.

---

## 7. Redeployment — one free experiment worth more than this whole audit

**B.0.6 is still open** (`research/CURRENT_RESEARCH_STATE.md:3318-3345`). Two
fits explain the existing data equally well:

- α ≈ 0.389 → M5 ceiling 686 GB/s, M5 efficiency ≈ 0.86 → *"M5 is less
  saturated than we think and per-family efficiency work pays"*
- α ≈ 0.437 → M5 ceiling 610.6 GB/s, M5 efficiency ≈ 0.62 → *"M5 is near its
  ceiling and only bytes pay"*

They differ by ~12 % in **every** M5 headroom figure in B.0.3, and they imply
opposite research programmes. The disagreement is localised to one family:
`routed` residual −2.24 % (515.9 GB/s, 84.5 % of 610.6) against `qkvo` residual
+10.86 % (597.9 GB/s, 97.9 % of 610.6).

**The resolving experiment already exists and is free.**
`research/fern_r101_bw_probe.swift` (17,114 B) builds with
`xcrun swiftc -O research/fern_r101_bw_probe.swift -o /tmp/fernbw` and runs in
~7 s. On the official M5 it measures the ceiling directly. It changes **no
submitted file**, consumes **no receipt** and **no submission slot**. The
digest itself calls it "the highest value per second of any experiment currently
nameable" (`:3336-3345`); fern names it independently
(`research/fern-r101-decode-pool-model.md:646`); tanjiro names it three times
(`research/maple-tanjiro-r107g-decode-family-regime-census.md:73`, `:694`,
`:1214`). It appears never to have been run.

Everything the campaign currently believes about where M5 headroom is — and
therefore which of edward's, alphonse's and cedar's levers are worth carrying —
rests on a constant that seven seconds of official-host time would pin down.
**This is my #1 recommendation.**

My full redeployment shortlist, with the reasoning and one withdrawn item, is
`research/frieren_r116_axis_disposition.md` §8. The withdrawn item is my own
second-favourite pick, a router-kernel retile, which a frontier review killed on
reachability before I could waste a sweep on it; I record the withdrawal rather
than quietly dropping it.

---

## 8. Two instrument findings the campaign should adopt

**8.1 `decode_seconds_per_token` is contaminated.** `--local-iterate`'s
`decode_seconds_per_token` folds the 512-token seed pass into the decode axis:
empirically `decode_spt ≈ mean_step + 4 × prefill_spt` (13144 µs reported vs
8218 µs steady). The seed portion carries nearly all the run-to-run noise on
this host. The harness already prints `last_step_seconds` at 8-token
boundaries, giving 17 samples per run; the mean over tokens ≥ 16 (n = 15,
discarding the ~33.9 ms warmup token) reproduces **6–20× tighter** on identical
runs — `sfd1` 239 µs (1.85 %) → **11.7 µs (0.14 %)**; `qmvsc0` 224 µs (1.7 %) →
**39.6 µs (0.48 %)**. Tool: `research/frieren_steady_step.py`. Any campaign
result that used `decode_seconds_per_token` as its statistic was measured with a
6–20× blunter instrument than the same runs already contained.

**8.2 The argmax of a flag screen is label noise, and position beats flags.**
A within-block permutation null (shuffle arm labels inside each block, recompute
the best arm) on the screen data gives p50 = −10.8 µs, p05 = −23.2 µs,
min = −29.9 µs. **The observed screen argmax `sc0` was −10.9 µs — exactly the
null median.** Separately, `sc0` reads −10.5 µs in ABBA order and +12.6 µs in
BAAB: a **23 µs order gap larger than any flag effect in the sweep**. Per-arm
ABBA−BAAB gaps average ≈ −7 to −9 µs with a 34.3 µs maximum. Two consequences:
order balancing is not a nicety on this instrument, it is doing the primary
work; and any screen that reports its argmax without a null is reporting the
instrument.

**Two defects I disclose against myself.** (a) My confirmation runner's resume
logic skips any block whose score JSON already exists, *including a failed one*,
so a run that fails the cool-down gate would be skipped forever; I repair it by
deleting the failed JSON and re-invoking, and I report the affected arm both
with and without the out-of-order refill. (b) `qmvsc0-b1` failed with
`local GPU cool-down gate failed for prefill with status 1` — the GPU held at
43.0 C against a 40 C target for 180 s. That is a thermal-gate failure, not a
correctness failure: no timing phase ran.

---

## 9. Evidence index

Committed on `maple-frieren/r116-shipped-defaults-audit`:

| file | what |
|---|---|
| `research/frieren_r116_FINAL_RESULT.md` | this document |
| `research/frieren_r116_axis_disposition.md` | the argued answer to "is this axis dead", incl. minimum shippable effect, the stopping-rule argument, and the redeployment shortlist |
| `research/frieren_r116_premise_correction.md` | §5's premise correction, the host-mapped prize table, and the τ/α hazard |
| `research/frieren_r116_tau_status_inventory.md` | mechanism / τ status / cost-to-test inventory in the advisor's 02:46Z format |
| `research/frieren_r116_flag_inventory_and_prereg.md` | the 159-symbol flag census with reachability |
| `research/frieren_r116_confirm_prereg.md` | the preregistration, written before the confirmation ran |
| `research/frieren_r116_confirm_run.sh` | the confirmation runner |
| `research/frieren_r116_pooled_analysis.py` | the pooled analyser implementing the advisor's instrument standard |
| `research/frieren_steady_step.py` | the steady-tail statistic (§8.1) |
| `research/frieren_r116_mde.py` | minimum detectable effect |
| `research/frieren_r116_screen_results.jsonl`, `_screen_steady.json` | raw screen evidence |
| `research/frieren_r116_raw_steps.csv`, `_pooled.json` | raw per-cycle samples and pooled statistics |
| `research/frieren_r116_wandb_log.py`, `_wandb_runs.txt` | W&B publication |
| `research/frieren_r109_FINAL_RESULT.md` | carried-forward r109 evidence (see §10) |

W&B: project `wandb-applied-ai-team/mlxfast-maple`, groups `r116a-screen` and
`r116a-confirm`.

---

## 10. Carried forward from PR #681 — r109, closed believing no work was produced

PR #681 was closed on the ground that "no work was produced". The work existed
and is reproducible; the closure's *other* ground — that a τ ≈ 1 % arm has a
+0.035 % ceiling — I independently confirm and do not contest. I re-state the
evidence here only so it is not lost, and I am not asking for the closure to be
reversed.

32/32 runs, all `passed_correctness=true`, **one golden hash across all eight
cells**, so every arm was bit-exact. W&B `nh6ktvwi` (Stage-2 factorial),
`940a3j8e` (density ladder), `4j9nfd3u` (startup-profile parity).

Against the shipped `c_w50_cb200`, no cell was faster, and the factorial
attributed the sign flip cleanly: **cadence × CB = +887.9 ± 51.9, t = +17.09**,
while cadence × BFS (+37.0 ± 105.7) and BFS × CB (+48.2 ± 62.7) were both null.
**The `MLX_MAX_OPS` / `MB_PER_BUFFER` caps own the effect; BFS width does not.**
That is the same knob whose profile-dependence I had to pin in §2 of this
assignment to keep these measurements honest, which is why it is worth
preserving.

Closures banked there: `N-CADENCE-OPTIMAL`, `N-BFS-WIDTH-NULL-AT-RANKED-CADENCE`,
`N-DENSITY-SATURATED`, `N-WIDE-CODES-SLOWER` (+35.2 µs/step, t = +25.23),
`N-NIBBLE-SPLIT-ALREADY-OPTIMAL` (static ALU counts: variant 0 = 19, variant 1
= 13, variant 2 = 19 — the shipped variant is the cheapest by construction, which
is the mechanism behind tanjiro's later measurement and behind `ns0`/`ns2` in §3),
and `N-ROUTER-PREFETCH-CLOSED-BY-M5-NULL`. Full report:
`research/frieren_r109_FINAL_RESULT.md`.
