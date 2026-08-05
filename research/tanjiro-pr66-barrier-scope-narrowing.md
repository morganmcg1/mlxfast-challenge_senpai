# §0.9.23 — the barrier-width law: audit result

SENPAI-RESULT: {"terminal":true,"status":"complete","pending_arms":false,"wandb_run_ids":[],"primary_metric":{"name":"eligible_barrier_removal_share_of_score_pct","available":true,"value":0.089},"test_metric":{"name":"passed_correctness","available":false,"value":null}}

- **Student / PR:** `maple-tanjiro` / [#66](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/66), revision `r1`, assignment `maple-2026-08-05i-barrier-scope-narrowing`
- **Hypothesis and target cost:** §0.9.23 — barrier rendezvous cost is a
  meaningful fraction of kernel time *only in narrow kernels*, so
  `threadgroup_barrier` → `simdgroup_barrier` scope-narrowing is dead in wide
  kernels and alive in narrow ones. Target: find ≥3 provably within-simdgroup
  barrier sites in ≤128-thread kernels worth ≥0.15% of score in aggregate.
  Cost spent: 0 official receipts, 0 paired benchmark runs, ~2 h of census +
  one standalone Metal microbenchmark (114 s GPU).
- **Decision: dead hypothesis.** Both pre-registered hard stops fire
  independently, and the mechanism is inverted rather than merely too small.
- **`BASE_SHA` / candidate commit:** `fae11f91e5c5247fbb2c70113302aebbf1c571cb`
  / see submission commit on `maple-tanjiro/barrier-scope-narrowing`.
- **Submitted candidate files: none.** `git diff --stat fae11f91 -- Sources
  Vendor` is empty; the scored surface is byte-identical to base.
- **Supporting test or documentation files:**
  `research/tanjiro_barrier_cost_probe.swift` (standalone Metal microbenchmark,
  not on `editablePaths`), `research/tanjiro-pr66-barrier-scope-narrowing.md`
  (this file).
- **Official submission `--model` value (planned or used; default `senpai`):**
  `senpai` — planned only. **No official submission was dispatched by this
  arm**; the assignment reserved the ranked channel for frieren and set this
  arm's receipt budget to zero.
- **Explicit API model-value rejection, if fallback attribution was required:**
  none — no submission API call was made, so no rejection and no fallback.
- **Assignment-scope preflight:**
  `senpai/validate-assignment-scope.sh fae11f91… research/tanjiro-pr66-barrier-scope-narrowing.md research/tanjiro_barrier_cost_probe.swift`
  reports both as *outside* `benchmark.json` `editablePaths` — the intended
  result, confirming the two touched files are research-only and unsubmitted.
  The submitted-path list is empty, so there is nothing for the scope check to
  admit.
- **Editable bytes / headroom / growth:**
  `senpai/check-editable-budget.sh fae11f91e5c5247fbb2c70113302aebbf1c571cb` →
  `editable budget OK: current=2941175/3000000 bytes headroom=58825 growth=0/262144 files=142 (file count is diagnostic only; base=142)`.
  Growth is exactly 0 B, headroom unchanged.
- **Scored-path reachability evidence:** the census classifies every one of the
  39 in-kernel barrier sites as live-decode, live-prefill, or off-path, each
  with the runtime flag and line number that decides it (§ *Live vs off-path*
  below). 19 of 39 sites (49%) are unreachable under default flags. The three
  removable sites (`RM:8554`, `LHP:459`, `RM:9202`) are each pinned to a
  dispatch on the scored path with a per-step execution count; the eligible
  total is priced from those counts, not from static site counts.

### Evidence

- **Host, memory profile, toolchain, and thermal policy:** Apple M4 Pro, 20 GPU
  cores, `Mac16,11` / macOS `26.5.2`, 48 GiB (`hw.memsize = 51539607552`, so
  below the 64 GiB threshold — this host would use the low-memory startup
  profile, though no model was loaded by this arm). The
  probe is a standalone Metal binary with its own thermal discipline: an 800 ms
  heater kernel before the first timed rep and 12 ms before each subsequent
  rep, 2 warmups, all 18 pipelines precompiled before timing. **This host is
  not the ranked M5** (40 GPU cores); see M5 transfer risk below.
- **Exact baseline and candidate commands:** no baseline/candidate benchmark
  pair was run — there is no candidate. The only measurement command is
  ```sh
  xcrun swiftc -O research/tanjiro_barrier_cost_probe.swift -o /tmp/tjbar \
    -framework Metal -framework Foundation
  TJ_REPS=25 TJ_WAVES=1 /tmp/tjbar   # and TJ_WAVES=2, TJ_WAVES=4
  ```
  executed under `run_training` id `9eed58fc-4678-4068-899d-e30b2d323809`
  (exit 0, 113.8 s).
- **Tests and risk-based checks run, including selected-test count:** no Swift
  test target was selected (0 tests) and no correctness suite was run, because
  the submitted surface is empty — `git diff --stat fae11f91 -- Sources Vendor`
  produces no output, so no scored code path can have changed. The checks that
  *were* run are the injection tripwire
  (`grep -n -A1 'DARKBLOOM_INJECT_DECODE_EMPTY"\|DARKBLOOM_INJECT_EMPTY_TG"'`
  → `11046: "DARKBLOOM_INJECT_DECODE_EMPTY", 0)` and
  `11058: "DARKBLOOM_INJECT_EMPTY_TG", 160)`, both at their required defaults,
  run once before measurement and once before submission), the base-advance
  check (`origin/codex/mlxfast-maple-20260804-advisor` still at `fae11f91…`, no
  rebase needed), the scope check, and the byte-budget check above.
- **Correctness and serial-protocol verdict:** vacuously unchanged. Zero bytes
  of `Sources/` or `Vendor/` differ from base, so greedy tokens, the 64-step
  drift tripwire, and the serial non-speculative rules are bit-identical to the
  base commit by construction. No correctness measurement is claimed
  (`test_metric.available = false`); this is *not* a passing correctness run.
- **Divergent tokens or failure category, if any:** none possible — see above.
- **Peak RAM or generated-weight size, if relevant:** not relevant. The probe
  allocates three 4 MiB buffers and holds no model; no weights were generated.
- **Official ranking status versus correctness/floor status, if submitted:**
  not submitted. Zero official receipts consumed, as the assignment required.

| Metric | Baseline | Candidate | Ratio / delta |
| --- | ---: | ---: | ---: |
| decode seconds/token | not run | no candidate | — |
| prefill seconds/token | not run | no candidate | — |
| same-host paired estimate | — | not run | — |

The paired estimate is a same-host research metric, not an official M5 score.
No row is populated because this arm terminated at a pre-registered hard stop
*before* implementation, which is the outcome the gate was written to produce.
The measured quantities this arm does report are barrier latencies and the
derived eligible-saving share, tabulated below.

| Probe metric (M4 Pro, 20 cores, `TJ_REPS=25`, `TJ_WAVES=1`) | Value |
| --- | ---: |
| `threadgroup_barrier`, 32 threads (1 simdgroup) | 0.32 ns |
| `threadgroup_barrier`, 64 threads (2 simdgroups) | 21.56 ns |
| `threadgroup_barrier`, 256 threads (8 simdgroups) | 24.80 ns |
| `threadgroup_barrier`, 1024 threads (32 simdgroups) | 51.45 ns |
| `simdgroup_barrier`, every width 32…1024 | ≈0.00 ns |
| ceiling if *every* live decode barrier were free | 47.5 µs/step = 0.71% of score |
| **eligible (provably removable) subset** | **5.8 µs/step = 0.089% of score** |
| Step 1 hard-stop threshold | 0.15% of score |

### Conclusion

- **What happened and why:** the Step 0 census found exactly **1** of 39
  in-kernel barrier sites provably within-simdgroup in a ≤128-thread kernel
  (gate required ≥3), so the first hard stop fired on census alone. Rather
  than stop there, the arm spent one 114 s microbenchmark to price the
  population, and the Step 1 gate then fired independently: the complete
  eligible set is worth **0.089%** of score against a 0.15% floor. The
  microbenchmark also inverted the premise. `threadgroup_barrier` costs
  0.32 ns at one simdgroup and 51.45 ns at 32 — cost *grows* monotonically
  with width (roughly logarithmic in simdgroup count: +21.2 ns going 1→2,
  +0.6 for 2→4, +2.7 for 4→8, +9.1 for 8→16, +17.5 for 16→32). Narrow kernels
  are the **cheapest** place a barrier can sit. §0.9.23 predicted the opposite.
- **Evidence for or against the mechanism:** three independent strands agree.
  (1) The width law is measured on a slope-over-trip-count design that cancels
  launch overhead and body cost, reproduced in two orders (ascending and
  descending width) that agree to <1%. (2) `simdgroup_barrier` is free at
  *every* width (≈0.00 ns), which collapses two of §0.9.23's three levers into
  one: narrowing a barrier's scope saves exactly what deleting it saves, so
  "scope narrowing" was never a distinct mechanism. (3) The claimed positive
  precedent `9e06de6` (+1.73%, rank 15) is a **misattribution**: it is a
  32-thread sliding QK-norm+RoPE *fusion* (dispatch `RM:1347`,
  `threadGroup:(32,1,1)`); the barrier it removed was 32-wide, worth 0.32 ns ×
  30 dispatches = 9.6 ns/step = 0.00013% of score — five orders of magnitude
  short of the observed win, which came from the removed dispatch. Meanwhile
  the negative precedent `58864bf4` is *retro-explained* by the same law: it
  removed a 512-wide barrier, which really is expensive, and failed on ~10×
  local-measurement inflation (−0.70% local → −0.07% ranked), not on barrier
  physics. The width law is the only hypothesis consistent with both ranked
  precedents.
- **Uncertainty or M5 transfer risk:** the absolute latencies are M4 Pro
  (20 cores) numbers and the ranked M5 has 40; the *shape* of the law (free
  simdgroup barrier, monotone growth in simdgroup count) is an architectural
  property of the barrier primitive and should carry, but the constants may
  not. That risk is one-sided in a convenient direction: the eligible subset
  fails its gate by a factor of 1.7 **using an upper bound**, since every
  entry assumes the barrier's full latency is on the critical path and none of
  it overlaps. The arm also inherits round-9's lesson that an *added*-work
  slope is an upper bound on removal saving and never a price: fern's
  `c = 2.1828 µs/dispatch` predicted +2.568% and the ranked receipt
  (`285f79fa-089f-4184-b1ec-0647cb51e61b`, `officialScore 2.50450520378964`,
  `ns 2.540575`) measured **−0.1488%** against control `c3ce66ec`
  (`ns 2.544360`). Applying that same discipline here, the pre-registered
  prediction for the full eligible patch is a point estimate of **+0.086%**
  (`ns ≈ 2.5465`) with a 90% interval of **[−0.15%, +0.10%]**
  (`ns ∈ [2.5406, 2.5469]`) that straddles zero — i.e. **not resolvable by one
  receipt**, which is why no patch is offered even though the three removable
  sites are real and verified. `RM:8554` additionally costs +2 KB of
  threadgroup memory, which can reduce occupancy and flip the sign.
  Occupancy scaling was measured: barrier latency overlaps freely between
  concurrent threadgroups while the GPU is unsaturated (`TJ_WAVES=1` ≈
  `TJ_WAVES=2` at every width) and only adds at `TJ_WAVES=4` for widths ≥256,
  so the correct model is `ceil(TGs / TGs_resident) × latency(width)` — a
  40-core M5 is *less* saturated than this host at the same grid, which
  shrinks the eligible saving further rather than growing it.
- **Smallest useful next action:** successor item 4 in the sketch below —
  relabel two elements per lane in the prefill router tournament
  (`e0 = lane & 31`, `e1 = e0 + 32`) so the stride-32 exchange becomes a
  register swap. That is the only member of the eligible set with a plausible
  path above the resolvability floor, because it removes **two** barriers
  (`RM:9198` and `RM:9202`) *and* frees 2 KB of threadgroup memory, inverting
  the occupancy risk instead of taking it on. It should be scoped only if a
  future arm has spare receipt budget and pairs it with a §0.9.21 standalone
  bitwise oracle using an **incoherence** fault-power control (fern's #48
  showed `max_abs_diff 0` survives an *additive* fault, so additive controls do
  not prove an exchange oracle has power).
- **Recommendation: close.** §0.9.23 is falsified as stated and should not be
  re-scoped; the barrier-width law replaces it. The by-products — the 39-site
  census with live/off-path classification, the finding that 49% of barrier
  sites are unreachable under default flags, the `9e06de6` debunk, and the
  retro-explanation of `58864bf4` — are the durable output and are recorded
  below.

---

**Assignment** `maple-2026-08-05i-barrier-scope-narrowing` (PR #66, revision `r1`)
**Base** `fae11f91e5c5247fbb2c70113302aebbf1c571cb` on `codex/mlxfast-maple-20260804-advisor`
**Host** Apple M4 Pro, 20 GPU cores (`Mac16,11 / 26.5.2`) — *not* the ranked M5
**Official receipts consumed** 0 (by design; frieren holds the ranked channel)
**Scored surface changed** none — `Sources/`, `Vendor/` are byte-identical to base

---

## Verdict in one line

**Step 0 HARD STOP fires, and the hypothesis is inverted rather than merely
unmet.** Exactly **1** of 39 in-kernel barrier sites is provably
within-simdgroup in a kernel of ≤128 threads (the gate required ≥3); and an
independent standalone probe shows `threadgroup_barrier` cost *grows*
monotonically with threadgroup width, so narrow kernels are the **cheapest**
place a barrier can sit, not the most expensive. §0.9.23's premise — "barrier
rendezvous cost is a meaningful fraction of kernel time only in narrow
kernels" — is falsified in the direction of its own prediction.

No patch is proposed for the scored path. Three genuinely removable barriers
were found as a by-product; all three are priced below the resolvability floor
and are handed forward as named successors, not as a merge.

---

## What this arm attacks, and what it does not

fern's #48 census counted **host-side command-encoder barriers** —
`maybeInsertBarrier` in `Vendor/mlx-swift/.../backend/metal/device.cpp`, which
is *not* on `editablePaths`. Those are inter-dispatch dependency fences issued
by the Metal encoder between command buffers.

**This arm attacks in-kernel `threadgroup_barrier` rendezvous** — the
intra-threadgroup execution/memory barrier emitted inside Metal kernel source.
They are two different objects with two different cost models, and a result
about one is not evidence about the other. Every count, price, and verdict
below refers exclusively to the in-kernel object.

---

## Step 0 — width-stratified barrier census (39 sites)

Census method: for each site, resolve the enclosing kernel, resolve the
threadgroup width from the *actual dispatch site* (not from the kernel
declaration), determine reachability under the default ranked configuration,
and then prove or refute cross-simdgroup threadgroup traffic in the region the
barrier guards by quoting the write and read index expressions.

All 37 `LagunaRuntimeModel.swift` sites plus both `LagunaLmHeadPrune.swift`
sites already carry `mem_flags::mem_threadgroup`. Flag-narrowing is already
done project-wide; only scope-narrowing and elimination remained.

### Population by width

| TG width | simdgroups | sites | provably within-simdgroup |
|---|---|---|---|
| 32 | 1 | 1 | **1** |
| 64 | 2 | 9 | 0 |
| 128 | 4 | 0 | 0 |
| 224 | 7 | 1 | 0 |
| 256 | 8 | 13 | 0 |
| 288 | 9 | 1 | 0 |
| 512 | 16 | 6 | 0 |
| 1024 | 32 | 8 | 0 |
| **total** | | **39** | **1** |

**Sites in kernels of ≤128 threads that are provably within-simdgroup: 1.**
Gate required ≥3. **Step 0 HARD STOP.**

The single qualifying site is `LagunaLmHeadPrune.swift:459`.

### Per-site table

Path column: `decode` = runs in the scored decode window; `prefill` = scored
prefill only; `off` = unreachable under the default ranked configuration.

| Line | Kernel | width | path | ×/step | cross-simd traffic? | verdict |
|---|---|---|---|---|---|---|
| RM:775 | `lagunaNormReductionTail` template | 512 | decode | 39 | yes (16 sg → sg0) | required — **negative control (`58864bf4`)** |
| RM:779 | same template | 512 | decode | 39 | yes | required — negative control |
| RM:786 | same template | 512 | decode | 39 | yes | required — negative control |
| RM:964 | `laguna_residual_rms_router_bf16_2048_rpg*` | 512 | decode | 39 | yes: `normalized_row[base+i]` written by all 512, read by router accumulate across sg | **required** (PR body: provably ineligible — confirmed) |
| RM:1471 | sliding fused attention (decl 1381) | 1024 | decode | 30 | — | **reserved for nezuko, read-only** |
| RM:1638 | sliding fused attention | 1024 | decode | 30 | — | reserved for nezuko |
| RM:1661 | sliding fused attention | 1024 | decode | 30 | — | reserved for nezuko |
| RM:1669 | sliding fused attention | 1024 | decode | 30 | — | reserved for nezuko |
| RM:1953 | full fused attention (decl 1856) | 1024 | decode | 10 | — | reserved for nezuko |
| RM:2159 | full fused attention | 1024 | decode | 10 | — | reserved for nezuko |
| RM:2182 | full fused attention | 1024 | decode | 10 | — | reserved for nezuko |
| RM:2190 | full fused attention | 1024 | decode | 10 | — | reserved for nezuko |
| RM:3310 | `laguna_fused_norm_qkv_projection_bf16_h{48,64}_v3` | 512 | off | 0 | yes: write `normalized_row` 3308, read 3213/3346 up to 480 lanes apart | required; off-path |
| RM:3374 | same | 512 | off | 0 | yes: `gate_partials` sg `s` → sg `s+1..s+7` (3369-71 → 3379-81) | required; off-path |
| RM:3924 | `laguna_gated_affine_oproj_qmv_i8g32_h*_v1` | 64 | off | 0 | yes: `gate_table[lid]` 3922 → `gate_table[column>>7]` 3939, both sg read all slots | required; off-path |
| RM:4195 | `laguna_gated_affine_oproj_nvfp4_qmv_h*_v1` | 64 | off | 0 | yes: `gt[lid]` 4193 → `gt[column>>7]` 4204 | required; off-path |
| RM:4700 | `stagedNormalize` in `lagunaNormAffineQKVBody` | 64 | off | 0 | yes: `norm_row[(lid+64j)*4+i]` 4695 → `norm_row[simd_lid*8+i]` 4794/4798 | required; off-path |
| RM:4753 | `lagunaNormAffineQKVBody` | 64 | off | 0 | yes (WAW): zero-store `local_sums[lid]` 4751 (sg0 only) vs `local_sums[simd_gid+2j]` 4764 (sg1 odd) | removable-by-restructure; off-path |
| RM:4767 | `lagunaNormAffineQKVBody` | 64 | off | 0 | yes (RAW): sg1 lane0 writes odd idx 4764, sg0 reads `local_sums[simd_lid]` 4770 | **required** (narrowing would be *incorrect*); off-path |
| RM:4776 | `lagunaNormAffineQKVBody` | 64 | off | 0 | yes (RAW): `local_inv_mean[0]` sg0 lane0 4772 → all 64 read 4778 | removable-by-restructure; off-path |
| RM:4960 | prefetch twin `..._qmv_i8g32_r{R}` | 64 | off | 0 | as 4753 | removable-by-restructure; off-path |
| RM:4974 | prefetch twin | 64 | off | 0 | as 4767 | required; off-path |
| RM:4983 | prefetch twin | 64 | off | 0 | as 4776 | removable-by-restructure; off-path |
| RM:7575 | `laguna_routed_nvfp4_down_reduce_bf16_v2` | 256 | off | 0 | yes: 8 sg → sg0 (7570-72 → 7586) | required; off-path |
| RM:7732 | `laguna_routed_shared_nvfp4_down_residual_bf16_r1_v5` | 288 | decode | 39 | yes: 9 sg → sg0 (7728-29 → 7742-43, 7750) | **required** |
| RM:8389 | `laguna_decode_router_top8_v3/_norm_v2` | 256 | off | 0 | yes: `xchg_*[lane]` → `[lane^stride]`, stride ≥ 32 | required; off-path |
| RM:8394 | same | 256 | off | 0 | WAR only | removable; off-path |
| RM:8550 | `laguna_decode_router_top8_ordinal_table_norm_v1` | 256 | decode | 39 | yes: `xchg_*[lane]` 8548-49 → `[lane^stride]` 8552-53, stride ∈ {32,64,128} | **required** |
| RM:8554 | same | 256 | decode | 39 | **WAR only** — guards next stage's `xchg_*[lane]` write | **removable** (stage-parity double buffer) |
| RM:8832 | `laguna_prefill_router_top8_v1(_norm)` | 256 | off | 0 | yes: `choice_keys[lane]` 8831 → `choice_keys[j]` ∀j<256 | required; off-path |
| RM:8847 | same | 256 | off | 0 | yes: `selected_scores[rank]` 8845 → lanes 0-7 read 8849-51 | required; off-path |
| RM:9047 | `laguna_prefill_router_tournament_v1(_norm)` | 256 | off | 0 | yes: sg `b` writes `candidate_*[8b+rank]` → all read `[lane&63]` | required; off-path |
| RM:9070 | same | 256 | off | 0 | yes: `xchg_*[lane]` → `[lane^32]` | required; off-path |
| RM:9075 | same | 256 | off | 0 | WAR only | removable; off-path |
| RM:9183 | `laguna_prefill_router_tournament_ordinal_v1(_norm)` | 256 | prefill | — | yes ×2: `candidate_*` 9178-79 → `[lane&63]` 9186-87; `original_scores[lane]` 9143 → `[my_index2]` 9118/9132 | **required** |
| RM:9198 | same | 256 | prefill | — | yes: `xchg_*[lane]` 9196-97 → `[lane^32]` 9200-01 | **required** |
| RM:9202 | same | 256 | prefill | — | **WAR only** — single `stride==32` iteration, nothing writes TG memory after | **removable** (plain deletion, hazard-free) |
| LHP:382 | `laguna_lmhead_coarse_argmax_stage1_v5` | 224 | decode | 1 | yes: sg `g` lane0 → `shared_vals[simd_group]` 377-80, sg0 lanes 0-6 read 383-86 | **required** |
| LHP:459 | `laguna_lmhead_exact_winner_bf16_midpoint_threshold_v1` | **32** | decode | 1 | **no** — `winner_row[0]` written by `lid==0` 456-58, read by the same simdgroup 460 | **removable** ✅ (the only ≤128-thread within-simdgroup site) |

RM = `Sources/MLXFastModel/LagunaRuntimeModel.swift`;
LHP = `Sources/MLXFastModel/LagunaLmHeadPrune.swift`.

### Census by-products worth recording

**19 of 39 barrier sites (49%) are in kernels that are unreachable under the
default ranked configuration.** They live in ablation arms that lost:

- `lagunaNativeAffineNVFP4From` defaults to `0` (`RM:2917-2924`), so
  `lagunaNativeAffineWeight` returns `.nvfp4/gs16/b4` for every layer
  (`RM:2969-2981`). The INT8-`g32`-affine guard at `RM:5537-5541` therefore
  fails for all 40 layers, killing sites 4700/4753/4767/4776/4960/4974/4983 and
  3924. What actually runs is `lagunaDecodeNVFP4QKVR1` (`RM:4658-4687`,
  TG 64), which is **barrier-free** — its reduction is pure `simd_sum`
  (`RM:4634`).
- `gateIsActivated` is `true` (`RM:5605-5609 → 5650 → 5912`), so the
  activated o_proj twin (`RM:4387-4403`, built `preActivatedGate: true`) is
  selected. That arm emits `gateSetup == ""` — **no barrier at all** — killing
  site 4195.
- `lagunaFusedRoutedSharedDownResidualEnabled` is default-on (`RM:142-144`),
  so all 39 sparse layers take `RM:10023` and site 7575 never runs.
- `lagunaDecodeRouterOrdinalEnabled` is default-on (`RM:8637-38`), killing
  8389/8394; `lagunaPrefillRouterTournamentEnabled` is default-on
  (`RM:9320-21`), killing 8832/8847; and only the *ordinal* tournament is live,
  killing 9047/9070/9075.

This is not a cost, but it does mean any future census that greps for barriers
without resolving reachability will over-count the live population by ~2×.

**The `9e06de6` positive precedent does not survive contact with the census.**
That change (+1.73%, rank 15) is described as a 32-thread sliding QK-norm+RoPE
fusion "with the barrier removed". The resulting kernel is dispatched at
`RM:1347` with `threadGroup: (32,1,1)` and is now barrier-free. But a 32-thread
threadgroup is exactly one simdgroup, and §Step 1(a) below measures the cost of
a `threadgroup_barrier` at width 32 as **≈0.3 ns**. A saving of 0.3 ns × 30
dispatches/step = 9 ns/step is **0.00013% of score** — five orders of magnitude
short of +1.73%. The win came from the *fusion* (one fewer dispatch, one fewer
round-trip through device memory); the barrier disappeared as a side effect of
merging two kernels into one, and was never the mechanism. The "positive
precedent" for §0.9.23 is a misattribution.

---

## Step 1(a) — standalone price of a barrier vs. threadgroup width

`research/tanjiro_barrier_cost_probe.swift` (research-only; **not** on
`editablePaths`, never compiled by a scored build).

Design. Three arms share one kernel body: `none`, `sg`
(`simdgroup_barrier(mem_flags::mem_threadgroup)`), `tg`
(`threadgroup_barrier(mem_flags::mem_threadgroup)`). The body is a rotate-by-one
exchange through `threadgroup` memory indexed *within the same simdgroup*
(`partner = (tid & ~31u) + ((lane+1) & 31u)`), so all three arms are
semantically valid on Apple's lockstep simdgroups and the only difference
between them is the barrier instruction. Two barriers per loop iteration.

Cost is extracted as a **slope over trip count** (`iters ∈ {256, 1024, 4096}`,
least-squares), which cancels launch overhead and the body's own cost:

```
ns/tg_barrier      = (slope_tg   - slope_none) / 2
ns/sg_barrier      = (slope_sg   - slope_none) / 2
narrowing saving   = (slope_tg   - slope_sg  ) / 2
```

Confound found and fixed. The first version reported widths 32/64 at 266 ns/iter
against 98 ns/iter at ≥128 — a GPU clock-ramp artefact, because `makeLibrary`
CPU stalls let the GPU idle and the narrow widths happened to run first. Fix:
precompile all 18 pipelines up front, add a `heater` kernel (800 ms initial,
12 ms before every timed rep), take a median over reps, and run **two passes
per configuration — ascending and descending in width** so that any residual
order effect shows up as a disagreement between passes.

### Results (`TJ_REPS=25`, M4 Pro 20 cores, ns per single barrier)

At 25 reps every outlier present in the 9-rep and 15-rep runs disappears and
the two passes agree to better than 1% at every width — the remaining spread is
the honest error bar.

| TG width | simdgroups | `threadgroup_barrier` (A, B) | `simdgroup_barrier` (A, B) | narrowing saving (A, B) |
|---|---|---|---|---|
| 32 | 1 | 0.32, 0.32 | 0.01, 0.02 | 0.31, 0.30 |
| 64 | 2 | 21.58, 21.54 | 0.03, −0.00 | 21.55, 21.55 |
| 128 | 4 | 22.18, 22.20 | 0.00, 0.02 | 22.18, 22.19 |
| 256 | 8 | 24.94, 24.66 | 0.03, −0.28 | 24.91, 24.94 |
| 512 | 16 | 33.93, 33.89 | −0.02, 0.00 | 33.94, 33.88 |
| 1024 | 32 | 51.45, 51.45 | 0.02, −0.00 | 51.43, 51.45 |

**The barrier-width law, measured:** cost is ~0 at one simdgroup, jumps to
~21.5 ns at two, and then rises roughly logarithmically in simdgroup count —
+0.6 ns from 2→4, +2.7 ns from 4→8, +9.1 ns from 8→16, +17.5 ns from 16→32.

### Occupancy scaling (waves = threadgroups / cores)

| width | W=1 (20 TG) | W=2 (40 TG) | W=4 (80 TG) |
|---|---|---|---|
| 32 | 0.32 | 0.32 | 0.33 |
| 64 | 21.56 | 21.55 | 21.23 |
| 128 | 22.19 | 23.12 | 23.41 |
| 256 | 24.80 | 25.66 | 34.25 |
| 512 | 33.91 | 32.18 | 49.05 |
| 1024 | 51.45 | 54.70 | 83.19 |

Barrier latency **overlaps freely between concurrent threadgroups while the
machine is unsaturated** (W=1 and W=2 agree at every width), and only starts to
add once the wide kernels can no longer keep all threadgroups resident (W=4,
widths ≥ 256). Narrow kernels never saturate and stay flat. The correct cost
model is therefore `ceil(TGs / TGs_resident) × latency(width)`, using the
unsaturated latency from the W=1 column — not `TGs × latency`.

---

## Reading of the Step 1(a) result

1. **`simdgroup_barrier` is free at every width** — reproducibly 0.00 ns. On
   Apple's lockstep simdgroups it is a compiler scheduling fence, not a runtime
   rendezvous. Consequence: *narrowing a barrier saves the same amount as
   deleting it.* Scope-narrowing and elimination are the same optimisation
   priced identically, which collapses two of §0.9.23's three levers into one.
2. **`threadgroup_barrier` cost grows with width; it does not shrink.** This is
   the direct inversion of §0.9.23. A barrier at 32 threads has nothing to
   rendezvous (one simdgroup) and costs ~0.3 ns; the cost then rises with the
   number of participating simdgroups.
3. Therefore the optimisation surface §0.9.23 pointed at — *narrow* kernels —
   is precisely the surface where a barrier is worth the least. The sites where
   a barrier is expensive are the 512- and 1024-thread kernels, and in this
   codebase every one of those is a genuine cross-simdgroup rendezvous
   (`RM:964`, the `lagunaNormReductionTail` template, both fused attention
   kernels) that cannot be narrowed or deleted without changing results.
4. This also retro-explains the **negative precedent**. `58864bf4` made two
   barriers optional in the 512-thread `lagunaNormReductionTail` and measured
   −0.70% locally but **−0.07% ranked** — a 10× local over-statement. A
   512-wide barrier is one of the *expensive* ones by this law, so the sign of
   that attempt was right and only the magnitude was wrong; the arm failed on
   local-measurement inflation, not on barrier physics.

---

## Step 1 gate arithmetic

Exchange rate: 1 ms decode = 14.862% of score ⇒ decode step ≈ 6.73 ms.
0.15% of score needs **≥ 10.09 µs/step**; 0.278% (single-receipt resolvability
floor, §0.9.22) needs **≥ 18.7 µs/step**.

### (i) Ceiling on the whole family: what if *every* live decode barrier were free?

This is the number that decides whether the family is ever worth another
assignment, so it is worth computing even though it is unreachable. Wave counts
are `ceil(TGs / cores)` on this 20-core host and are the weakest link in the
estimate; they are marked.

| live decode group | width | disp/step | barriers/disp | TGs/disp | waves (20c) | µs/step |
|---|---|---|---|---|---|---|
| `lagunaNormReductionTail2048` + `RM:964` in `residual_rms_router` | 512 | 39 | 4 | tiles (≈32) | ~2 | ≈10.6 |
| sliding fused attention | 1024 | 30 | 4 | 24 | 2 | ≈12.5 |
| full fused attention | 1024 | 10 | 4 | 24 | 2 | ≈4.2 |
| `RM:7732` down+residual | 288 | 39 | 1 | 512 | ~8.5 | ≈8.6 |
| `RM:8550` + `RM:8554` ordinal router | 256 | 39 | 12 | 1 | 1 | ≈11.6 |
| `LHP:382` / `LHP:459` lm-head | 224 / 32 | 1 | 1 | 128 / 1 | ~7 / 1 | ≈0.02 |
| **total** | | | | | | **≈47.5** |

≈47.5 µs/step against a 6.729 ms step = **≈0.71% of score**. So the entire
in-kernel barrier family on the scored decode path — every site, required or
not — is worth at most about 0.7%, and **~93% of that total sits in barriers
this census proves are genuine cross-simdgroup rendezvous.**

Treat 0.71% as order-of-magnitude: the wave counts are estimates, the latencies
come from a standalone probe on a 20-core M4 Pro rather than the ranked 40-core
M5, and a real kernel with memory stalls to hide behind will expose less barrier
latency than a probe built to expose it. It is an upper bound in every term.

### (ii) The actually-eligible subset

Three sites are provably removable without changing any result. This is the
complete list, and it is what the gate is evaluated against.

| site | width | ns each (W=1) | executions/step | µs/step | % of score |
|---|---|---|---|---|---|
| `RM:8554` ordinal router, WAR-only, stage-parity double buffer | 256 | 24.80 | 6 × 39 = 234 | 5.80 | **0.0862%** |
| `LHP:459` lm-head exact winner, `simd_broadcast` | 32 | 0.32 | 1 | 0.00032 | 0.0000048% |
| `RM:9202` prefill tournament, plain deletion | 256 | 24.80 | prefill only | ≈12.6 µs/prefill | ≈0.003% |
| **total** | | | | | **≈0.089%** |

**0.089% < 0.15% ⇒ Step 1 HARD STOP.** Do not implement.

Both gates fire, and they fire independently: Step 0 on the census count
(1 < 3), Step 1 on the price (0.089% < 0.15%). The arm would have stopped at
Step 0 even if barriers had been ten times more expensive, and would have
stopped at Step 1 even if ten times more sites had qualified.

Note where the eligible value actually is. `RM:8554` supplies 97% of it, and it
is a **256-thread** kernel — squarely in the "wide" half of the census that
§0.9.23 predicted would be dead. The one site that matches §0.9.23's profile
exactly (`LHP:459`: 32 threads, one simdgroup, provably within-simdgroup, live
on the decode path) is worth **0.32 nanoseconds per step**. If this arm had been
run as specified — hunt narrow kernels, narrow their barriers — it would have
found that site, shipped it, and moved the score by nothing measurable.

---

## Caveat that this arm is required to state, and does

Step 1(b) was **not** run, and the reason is the same reason it would have been
useless: an **added-barrier slope is an upper bound on the saving from removing
a barrier, never a price for it.** Adding an instruction to a kernel measures
what that kernel costs *with the instruction present in that schedule*; removing
one recovers that cost only if nothing else — occupancy, register pressure,
instruction scheduling, or a downstream dependency — moves in to fill the gap.

This is round 9's error, and it is expensive enough to name precisely: fern's
`c = 2.1828 µs/dispatch` added-work slope was banked as a removed-work price,
predicting **+2.568%**; the ranked receipt measured **−0.1488%** (ticket
`285f79fa-089f-4184-b1ec-0647cb51e61b`, `officialScore 2.50450520378964`,
`ns 2.540575` against control `c3ce66ec` at `ns 2.544360`). The prediction was
wrong by 2.7 percentage points and in the wrong direction.

The Step 1(a) numbers above are a *differential slope between two arms of the
same kernel*, not an added-work measurement, so they are not exposed to this
error in the same way. But they are still an upper bound on realisable saving:
they say what the barrier instruction costs in a kernel built to expose it, and
a real kernel with memory stalls to hide behind will recover less, never more.

---

## Disposition

**No change to the scored surface. `Sources/` and `Vendor/` are byte-identical
to base `fae11f91`.** Both hard stops fire and both instruct "stop and post" /
"do not implement", so no patch is produced — producing one anyway would be
disobeying the gate that the arm was designed around.

§0.9.22's rider rule is satisfied in its analytic half: the family has a
**proven analytic ceiling of ≈0.71% for every barrier on the decode path** and
**≈0.089% for the eligible subset**, both established without spending a
receipt, and the eligible figure is below the 0.278% single-receipt
resolvability floor. What §0.9.22 asks for in that situation is a `research/`
patch plus a pre-registered aggregate prediction. Here the Step 1 gate
overrides the patch half, so the deliverable is the prediction plus an
implementation sketch precise enough that a successor can produce the patch
directly.

### Pre-registered prediction (written before any receipt exists)

Should a future arm implement the three eligible removals and stack them behind
a shared receipt, I predict:

- **Point estimate: +0.086% of score**, i.e. `ns = 2.5465` against fixed
  control `c3ce66ec` at `ns = 2.544360`.
- **90% interval: [−0.15%, +0.10%] of score**, i.e. `ns ∈ [2.5406, 2.5469]`.

The interval straddles zero and is wider on the downside than the point estimate
is on the upside, for three reasons. (1) The 0.086% is an upper bound throughout
— standalone-probe latency, unsaturated-wave model, no memory stalls to hide
behind. (2) The nearest precedent, `58864bf4`, over-stated locally by 10×
(−0.70% local → −0.07% ranked), and this estimate is not even local, it is
analytic. (3) The `RM:8554` fix costs +2 KB of threadgroup memory for the
double buffer, which can reduce resident threadgroups per core and cost more
than the barrier saves. Single-receipt noise alone is ±0.278%, so the honest
statement is that **this bundle is not resolvable by one receipt and is
predicted to be indistinguishable from zero.**

### Implementation sketch for a successor (not implemented here)

1. **`RM:8554`** — give the exchange arrays a stage-parity buffer
   (`threadgroup uint xchg_ordinals[2][256]`, `xchg_indices[2][256]`): write
   `buf[p][lane]`, barrier, read `buf[p][partner]`, and drop the trailing
   barrier, letting stage *k+1*'s leading barrier supply the WAR ordering.
   12 → 6 barriers per router dispatch, 468 → 234 per decode step. Stage
   schedule and payload are bit-identical. Costs +2 KB threadgroup memory
   alongside the existing 2 KB + 1 KB `original_scores` — **verify occupancy
   does not drop**, since that is the most likely way this loses.
2. **`LHP:459`** — replace the `winner_row[0]` round-trip with
   `simd_broadcast(metal::min(best_idx, uint(VOCAB-1)), 0)`. The threadgroup is
   32 threads = one simdgroup (dispatch `LagunaLmHeadPrune.swift:966-967`), so
   the broadcast is exact. Worth 0.32 ns/step; include only for hygiene.
3. **`RM:9202`** — plain deletion. The `stride>=32` branch runs exactly one
   iteration (`RM:9188-89`) and nothing writes threadgroup memory afterwards,
   so the trailing WAR barrier guards nothing.
4. A strictly better variant of (1)+(3) exists and should be preferred: relabel
   to two elements per lane (`e0 = lane & 31`, `e1 = e0 + 32`), which turns the
   stride-32 exchange into a register swap, removes `RM:9198` *and* `RM:9202`,
   and **frees** the 2 KB `xchg_*` allocation instead of doubling it — inverting
   the occupancy risk in (1). This is the only member of the family with a
   plausible path above the resolvability floor and is the one worth scoping.

Any such patch must be verified by a standalone bitwise oracle in the §0.9.21
form (`makeLibrary`, reference vs. candidate over a sweep of routing inputs)
with an **incoherence** fault-power control rather than an additive one —
fern's #48 showed `max_abs_diff 0` survives an additive fault injected into a
barrier-guarded region, because the additive perturbation is applied uniformly
and the missing barrier only manifests under lane-divergent timing.

### Net-bytes and budget status

Not applicable in the usual sense: net surface change is **0 bytes** (the
budget cap was ≤ 0 net, +2,000 B helper). The only file added is
`research/tanjiro_barrier_cost_probe.swift`, which is outside `editablePaths`
and is not compiled by a scored build.

---

## Deferred successor (named only, per assignment — not scoped, not implemented)

**Shrink a wide hot kernel's threadgroup to one simdgroup and widen the grid so
the barrier disappears.** The census makes the target list concrete: the
expensive barriers all sit in 512- and 1024-thread kernels (`RM:964`,
`lagunaNormReductionTail`, both fused attention kernels), and by the Step 1(a)
law those are worth 30–55 ns each. Restructuring such a kernel to 32 threads per
threadgroup with a proportionally wider grid removes the rendezvous entirely
rather than trying to narrow it.

**Occupancy risk at target core count, stated as required.** The ranked M5 has
40 GPU cores; this host has 20. A 512-thread threadgroup that becomes sixteen
32-thread threadgroups multiplies the threadgroup count by 16, which (a) raises
per-threadgroup launch and scheduling overhead by the same factor, (b) loses any
threadgroup-memory reuse that the wide form got for free — the reduction data
that used to live in one `threadgroup` array must now go through device memory
or a second dispatch, and (c) changes the occupancy fraction differently on 20
cores than on 40, so an M4 Pro measurement of the restructured kernel is *not*
transferable to M5 without re-deriving `ceil(TGs / cores)`. The barrier saving
(30–55 ns) is small next to a threadgroup launch, so this only wins where the
wide form was already leaving cores idle. It should be scoped against a specific
kernel with a measured occupancy fraction, not proposed generically.

---

## Reproduction

```sh
xcrun swiftc -O research/tanjiro_barrier_cost_probe.swift -o /tmp/tjbar \
  -framework Metal -framework Foundation
TJ_REPS=25 TJ_WAVES=1 /tmp/tjbar
TJ_REPS=25 TJ_WAVES=2 /tmp/tjbar
TJ_REPS=25 TJ_WAVES=4 /tmp/tjbar
```

Env knobs: `MLXFAST_GPU_CORES` (override core detection), `TJ_REPS` (timed reps
per config, median reported, default 9), `TJ_WAVES` (threadgroups = waves ×
cores, default 1).

Census reproduction:

```sh
grep -n 'threadgroup_barrier\|simdgroup_barrier' \
  Sources/MLXFastModel/LagunaRuntimeModel.swift \
  Sources/MLXFastModel/LagunaLmHeadPrune.swift
```

40 hits in `LagunaRuntimeModel.swift`: 37 real `threadgroup_barrier` calls, 2
doc mentions of `threadgroup_barrier` (`:834`, `:8938`), 1 doc mention of
`simdgroup_barrier` (`:464`). Plus 2 real calls in `LagunaLmHeadPrune.swift`
(`:382`, `:459`).
