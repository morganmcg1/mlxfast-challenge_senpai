# Result — `_nax` expert gather-GEMM staging overlap (stage2 prefetch / double buffer)

SENPAI-RESULT: {"terminal":true,"status":"complete","pending_arms":false,"wandb_run_ids":[],"primary_metric":{"name":"official_score","available":true,"value":2.50505591848637},"test_metric":{"name":"passed_correctness","available":true,"value":1}}

> **r2 update.** The kernel arms below are reverted; the branch's submitted
> surface is byte-identical to base `d18ebbba`. r2's deliverable is the
> instrument analysis in
> [`maple-fern-pr40-r2-instrument.md`](maple-fern-pr40-r2-instrument.md), which
> resolves the baseline/candidate noise asymmetry raised here: the candidate arm
> is ~0.2% noisy, the pinned baseline arm ~1.9%, the two are **uncorrelated**
> (r = −0.011 [−0.125, +0.105]), and the baseline-prefill draw alone explains
> **86.5%** of `officialScore` variance. `ns` is confirmed as the instrument.

> **⚠️ Advisor, please read this first — it reverses your comment
> [#5191055555](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/40#issuecomment-5191055555).**
> You asked me to "report your own `S` and `T` per receipt so we replace my
> back-solve with your direct read." Here is the direct read, and it inverts the
> conclusion: **arm v1 did not win. Its candidate arm got *slower*.**
>
> `officialScore` is a ratio against a *separately measured* same-session
> baseline. Log-decomposing v1's `+0.896%` score gap versus the same-day control:
>
> | source | contribution |
> |---|---:|
> | **candidate** (my code — the only part I changed) | **−0.250%** |
> | **baseline** (pinned, unchangeable reference code) | **+1.142%** |
> | total | +0.892% |
>
> v1's paired baseline prefill came in at **388.398 µs — the 99.2nd percentile of
> 1029 draws of that same pinned code, and the single slowest baseline draw of the
> entire 2026-08-05 day.** My control drew 371.148 µs (54th percentile). Baseline
> prefill has **1.932% relative sd** across 1029 receipts; a +4.6% draw at 25%
> score weight is worth +1.16%, which is the whole "win."
>
> Direct reads, exactly as you asked (`S` = 512-token seed forward,
> `T` = marginal one-token step; negative = faster):
>
> | receipt | arm | `S` ms | `T` ms | `ΔS` vs control | `ΔT` vs control | `ns` | `Δns` |
> |---|---|---:|---:|---:|---:|---:|---:|
> | `c3ce66e` | v0 control | 97.950 | 4.2812 | — | — | 2.544360 | — |
> | `cdf71fa` | v2 register prefetch | 98.412 | 4.2820 | **+0.4626** | +0.00075 | 2.539719 | −0.182% |
> | `4058d0b` | v1 double buffer | 98.065 | 4.2952 | **+0.1150** | +0.01395 | 2.538013 | **−0.249%** |
>
> Your back-solve predicted `ΔS ≈ −2.42 ms` for v1. The measured value is
> **+0.115 ms** — wrong sign, and 21× smaller in magnitude. **Both arms are
> within-noise losses.** The `v2 regresses while v1 wins` branch of my
> pre-registered decision rule therefore does **not** fire; the branch that fires
> is "both null ⇒ close the family."
>
> Please **do not schedule the next slot on the +1.08% expectation** if that
> number was also read off `officialScore` deltas. §11 quantifies why: every
> published score carries **0.517% of pure baseline noise**, which is 2–3× larger
> than any single-mechanism effect this campaign has measured. §11 also shows the
> **crown itself is a +2.425% lottery premium**, which changes what "0.25% from the
> crown" means.

- **Student / PR:** maple-fern · [#40](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/40) `maple-2026-08-05a-nax-stage2-double-buffer` revision `r1`
- **Hypothesis and target cost:** `fp_gather_qmm_rhs_expert_nax` costs **43.26 ± 0.40 ms** of the 49.19 ms session-normalised prefill residual — the largest single attributable item on either axis. Measured cost is 0.80 of the serial DRAM+MMA sum (54.0 ms) against a perfect-overlap bound of 27.9 ms, so **15.4 ms is nominally recoverable** and only ~41% of the achievable overlap is realised. The hypothesis: the residual serialisation is **weight-load latency stranded behind the WAR threadgroup barrier**, and hoisting iteration *k+1*'s device reads above that barrier recovers a large part of it. Pre-registered point predictions: **ΔS = −4.0 ms** for v2 (register prefetch), **+1.5 ms** for v1 (double buffer).
- **Decision:** **hypothesis falsified on both arms; close the family.** Both candidates are bit-exact, rankable, and pass both floors with wide margins. Candidate-side effects are **v2 −0.183%** (`ΔS +0.4626 ms`, **+1.83σ**) and **v1 −0.250%** (`ΔS +0.1150 ms`, **+0.45σ**) — both inside my pre-registered ±3σ null band, both nominally the wrong sign. **Recommendation: merge nothing, delete all three arms and the `DARKBLOOM_STAGE2_GATHER` flag, reclaim the 24,164 bytes.**
- **`BASE_SHA` / candidate commit:** base `279b6e2409a2ca92f7b874e08a3dabc2c6ff4a0b`; accepted base `0b45de2261ee31b2f7fb46b6ddc3245775a02941`; candidate commit is the current HEAD. The submitted editable surface has been **frozen since `1f6f95c`** — every later commit touches only `research/`, verified by `git diff --name-only 1f6f95c..HEAD | grep -v '^research/'` → empty. Both ranked receipts therefore measure exactly the surface presented for review.
- **Submitted candidate files:** 4
  ```
  Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized_nax.h
  Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized_nax.cpp     # JIT twin — what actually runs on M5
  Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp
  Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/jit_kernels.cpp
  ```
- **Supporting test or documentation files:** research-only, not submitted — `research/nax_msl_compile_check.sh`, `research/stage2-gather-prereg.md`, `research/receipt_instrument_analysis.py`, `research/stage2-gather-decision-rule.md`, `research/receipt_baseline_lottery.py` (new — reproduces every number in §11).
- **Assignment-scope preflight:** `senpai/validate-assignment-scope.sh 279b6e24 <4 paths>` → `assignment scope OK: 4 submitted path(s)`.
- **Editable bytes / headroom / growth:** `senpai/check-editable-budget.sh 279b6e24` → `current=2965137/3000000 headroom=34863 growth=24164/262144 files=142`. ⚠️ **Only 34,863 bytes of total headroom remain — the squad is at 98.8% of the 3,000,000-byte cap.** This confirms your figure from the other direction: 59,027 − 24,164 = 34,863. Since I recommend merging nothing, **dropping this PR returns the surface to 59,027 bytes of headroom.**
- **Scored-path reachability evidence:** the two official receipts. The arms differ *only* by the integer that drives both the JIT `#define` and the kernel loop shape, and they move the prefill axis while decode stays essentially flat — a prefill-only shift in the axis the `_nax` expert kernel owns. Locally, the worker log demonstrably captures sibling fusion traces (`mlxfast-worker: mlxfast: packed-scales active: …`, `lm_head prune active`) yet `stage2_gather` prints **nothing at all** — not even "inactive" — confirming the `_nax` expert JIT kernel is never built on this Apple-GPU-generation-16 host. Local absence is the documented host limitation, not a broken lever.

### Evidence

- **Host, memory profile, toolchain, and thermal policy:** ranked measurements are the organizer M5 Max, 40C thermal gate, same-session paired baseline; `peak_ram_gb 21`, `weights_hash aff9943…`, `harness_hash 26581d9…`, `golden_hash be7738f…` **identical on all three receipts**, so baseline code, harness, weights, and goldens are provably the same across the comparison. Local host is an **M4 Pro, 48 GiB → low-memory startup profile** (allocator cache capped at 6 GiB; ranked code paths stay enabled), Metal toolchain 17.6.109.0. **The M4 Pro reports Apple GPU generation 16 and never selects `_nax`, so no local timing is evidence for this change** — local runs are regression guards only.
- **Exact baseline and candidate commands:**
  ```bash
  # arm selection is one integer lever; the default lives at quantized.cpp:1611
  bash /tmp/set_arm.sh 2                       # -> if (s.empty()) { return 2; }
  export PATH="${HOME}/.local/bin:${PATH}"
  mlxfast submit --note-file /tmp/note_v2.md --model "Claude Opus 5"
  bash /tmp/set_arm.sh 1                       # canary, never committed
  mlxfast submit --note-file /tmp/note_v1.md --model "Claude Opus 5"
  git checkout -- Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp

  # untruncated metrics (the CLI truncates the metrics column; the API does not)
  curl -sS -H "Authorization: Bearer ${MLXFAST_API_TOKEN}" \
    "https://api.mlx.fast/api/benchmarks/eigenlabs%2Fmlxfast-challenge/submissions"
  # every number in section 11, reproducible:
  MLXFAST_API_TOKEN=... python3 research/receipt_baseline_lottery.py \
      c3ce66e cdf71fa 4058d0b 46eeccf b6032ae

  # local regression guard + oracle
  ./benchmark.sh --local-iterate
  env DARKBLOOM_STAGE2_GATHER=0 research/run_upstream_equivalence.sh
  ```
- **Tests and risk-based checks run, including selected-test count:**

  | check | result |
  |---|---|
  | Frontier read-only bit-exactness audit, 4 questions | **PASS on all four** |
  | Independent frontier adversarial review of my own mechanism analysis | **found 6 real errors; all accepted and applied** (see §10) |
  | Offline MSL compile, arms 0/1/2, **both** real static Laguna MoE shapes | `COMPILE OK (std=metal4.0)`, 5095/5096/5096 lines |
  | Arm 0 preprocessed source vs stock | **byte-identical, 1,788,850 B** |
  | Header ↔ JIT twin sync | added 288 = 288, removed 0 = 0 |
  | `./benchmark.sh --local-iterate`, arm 2 | `passed: true`, `max_abs_diff: 0`, golden `b9509697…` |
  | Upstream-equivalence oracle, arm 2 (training `7b06e067`, 126.8 s) | 8 exact steps; identical to documented base |
  | Upstream-equivalence oracle, arm 0 control, **same binary** (training `352bdbd9`, 22.7 s) | byte-identical to arm 2 |

  The oracle is a **selected-test filter of 1** (`LagunaUpstreamEquivalence`), run twice via `research/run_upstream_equivalence.sh`, `EQUIVALENCE_EXACT_STEPS=8`. Both arms produced an identical report: prefill max abs logit err **0.125** / mean 0.011933609, decode steps 0–7 max abs err **0**, every runtime token equal to the upstream token. Those numbers match the base figures three siblings already documented (`research/CURRENT_RESEARCH_STATE.md:830-831`, `research/frieren-host-cpu-budget.md:471`). **`EQUIVALENCE_EXIT=1` is a pre-existing, documented M4 Pro limitation, not a regression** — the oracle applies zero tolerance to prefill, and the batched NVFP4 prefill path cannot meet that against the BF16 upstream reference. **Honest scope limit:** the oracle says nothing about the `_nax` kernel I actually changed (this host never selects `_nax`, and per `CURRENT_RESEARCH_STATE.md:832` the oracle never calls `prepareFusedRuntimeWeights()`); it is a no-regression guard on shared paths only. The two supervised-training terminal signals reporting `failed`/exit 1 for `7b06e067` and `352bdbd9` are exactly these two oracle runs.
- **Correctness and serial-protocol verdict:** **PASS on both receipts.** `max_abs_diff 0`, `passed_correctness True`, `partial_result False`, `case_count 11`, `checked_steps 1344`, `num_layers 40`, hidden GPQA TTFT 9/9 passed (0.41 s vs 2.3 s max, p50 0.071–0.072 s), semantic GPQA judge passed on both. Serial non-speculative rule is untouched by construction: the change is confined to how one GEMM kernel stages weight bytes from device into threadgroup memory. It adds no cache, no cross-invocation state, no extra rows, and no KV-position change; the only new state is 18 bytes/thread of *register* staging live within a single loop iteration.
- **Divergent tokens or failure category, if any:** none on either receipt. `first_failing_case`, `first_failing_layer`, `first_failing_step`, `actual_token`, `expected_token` are all `None`; `error` empty. One observation worth recording: `cdf71fa` returned `semantic_gpqa_pass_count 8` of 9 while still setting `semantic_gpqa_passed True`, where the control and `4058d0b` both returned 9/9. Since all three receipts are bit-exact with `max_abs_diff 0` and identical `golden_hash`, the generated tokens were identical, so this is **judge variance in the `claude-opus-4-8` semantic grader, not a model difference.** Worth knowing before someone reads an 8/9 as a regression.
- **Peak RAM or generated-weight size, if relevant:** `peak_ram_gb 21`, `weights_byte_count 21568891382` across 9 files, `weights_hash` unchanged — no transform or weight-layout change. `bandwidth_gb_per_token 0` as always (RAM-resident model).
- **Official ranking status versus correctness/floor status, if submitted:** these are **separate verdicts and must be read separately.** Both receipts are `rejected` on *ranking only* (`rejectionReason: "score did not improve current best"`) while passing correctness and **both** 0.95 floors with enormous margins (v2 prefill 1.921 / decode 2.737; v1 prefill 2.028 / decode 2.744 — against a 0.95 floor).

| Metric | Baseline (same-session paired) | Candidate (v2, shipped default) | Ratio / delta |
| --- | ---: | ---: | ---: |
| decode seconds/token | 0.0138231184921875 | 0.00505080403125 | **2.7368x** |
| prefill seconds/token | 0.000369242919921875 | 0.00019221134375 | **1.9210x** |
| official score | 2.52327585954979 (v0 control receipt) | 2.50505591848637 | **−0.722%** |
| fixed-normaliser `ns` | 2.5443596363978673 (v0 control) | 2.5397187649315867 | **−0.182%** |
| candidate-side effect only | — | — | **−0.183%** |

#### The comparison that carries the result

All three receipts ran on 2026-08-05 within 80 minutes, same host, same
`harness_hash`, `golden_hash`, `weights_hash`. The arms differ by one integer.

| receipt | UTC | arm | `cand_pre` µs | `cand_dec` ms | `ns` | officialScore | candidate-side Δ | baseline lottery Δ |
|---|---|---|---:|---:|---:|---:|---:|---:|
| `c3ce66e` | 09:33 | v0 control | 191.308 | 5.04644 | 2.544360 | 2.523276 | — | — |
| `cdf71fa` | 10:25 | v2 register prefetch | 192.211 | 5.05080 | 2.539719 | 2.505056 | **−0.183%** | −0.542% |
| `4058d0b` | 10:53 | v1 double buffer | 191.532 | 5.06130 | 2.538013 | **2.545892** | **−0.250%** | **+1.142%** |

Read the `candidate-side Δ` column, which is the only column that responds to my
code. **Both arms are slower than the control on both axes.** The `officialScore`
column ranks them in the opposite order purely because of the baseline draw.

### Conclusion

- **What happened, and why I think it happened.** Both staging arms are
  bit-exact and both are *slower* than the same-day control on both axes:
  v2 register prefetch `ΔS = +0.4626 ms` (+1.83σ, candidate seconds −0.183%),
  v1 double buffer `ΔS = +0.1150 ms` (+0.45σ, −0.250%). I pre-registered
  `ΔS = −4.0 ms` for v2 and `+1.5 ms` for v1; the discriminating branch
  (*v2 wins while v1 regresses ⇒ store/dequant throughput is binding*) did not
  fire, and the branch that did fire is *both null ⇒ close the family*. My best
  explanation, after independent adversarial review demoted my first one, is the
  most boring available: **the arms delivered no schedule change and only added
  instructions.** Splitting one load-store loop into a `prefetch()` + `commit()`
  pair costs roughly 5–15 extra ops per iteration — address recomputation, the
  18-byte register staging struct, the extra loop-carried copy — which is +1–2%
  of a kernel already at 64.5% of peak bandwidth. The observed shift is +1.07% of
  the kernel's time. That single mechanism explains the whole magnitude *and* the
  sign, without needing register pressure, occupancy, or latency arguments. The
  compiler was very likely already hoisting these loads: Metal's optimiser
  reorders device reads across a `threadgroup_barrier` freely as long as the
  addresses do not alias threadgroup memory, which is exactly the case here.
  I did the source-level transform the hardware had already done, and paid for
  the bookkeeping.
- **Evidence for and against the mechanism.** *For the null:* two independent
  arms, at opposite ends of the occupancy trade (v1 halves co-resident
  threadgroups from ~3 to ~1 and removes a barrier; v2 keeps 9,216 B/TG and both
  barriers), land within 0.35 ms of each other and of zero. If exposed weight
  latency behind the WAR barrier were the binding term, those two arms should
  have separated by several ms in opposite directions. They did not, so whatever
  binds the kernel is insensitive to how the staging loop is written. *Against
  my original framing:* my claim that "thread-level parallelism already hides
  the latency" does not survive scrutiny. A Little's-law estimate and a
  three-alternator phasing model both show 3 phase-locked threadgroups per core
  are *marginal* for covering DRAM latency, and the measured 64.5% bandwidth
  utilisation is a better fit for **stochastic phase collision** than for
  comfortable coverage. So the correct statement is narrower: *these two source
  transforms do not reach the binding term*, not *there is no latency to hide*.
  I also overreached in claiming the 15.4 ms roofline gap "is not a latency
  gap"; that violated my own pre-registered rule, which prescribed escalation
  rather than a verdict on a null. It is demoted to a hypothesis in §10.
- **Uncertainty and M5 transfer risk.** The mechanism conclusion rests entirely
  on two M5 receipts, because **this local M4 Pro host reports Apple GPU
  generation 16 and never builds the `_nax` expert kernel at all** — the fusion
  trace prints nothing, not even "inactive", while sibling traces print normally.
  So I have no local timing, no local profile, and no local register-occupancy
  readout for the kernel I changed; the ranked receipts are the only instrument.
  Both effects are inside my pre-registered ±3σ null band, so I cannot exclude
  that the true candidate-side effect is zero, nor that it is −0.5%. What I *can*
  exclude, at the size the hypothesis required, is a multi-millisecond win: a
  −4 ms `ΔS` would have shown as roughly −4.7% of prefill seconds, about 18σ
  away from what both arms delivered. The larger transfer risk runs the other
  way and is now quantified in §11: **a candidate-side effect below ~1% is not
  observable in `officialScore` at all**, because the paired baseline injects
  0.517% of noise into every published score. Any prior conclusion in this
  campaign that was drawn from an `officialScore` delta smaller than about 1.5%
  is not distinguishable from a baseline draw.
- **Smallest useful next action.** Not F2 or F3. First **mine the existing
  `fc204`/`fc205` (`WIDEST` / `WIDELD`) receipts already in the feed** for
  store- and load-width dose data — that is a pure analysis pass over receipts
  the squad has already paid for, and it costs zero submissions. If that shows a
  real slope, follow it with **one bit-exact `Ws` dead-padding dose-response**
  (1–2 receipts) that varies *only* the threadgroup-memory footprint and
  therefore isolates occupancy from every other mechanism. Independent review
  also corrected an attribution error I had propagated: **BN = 32 does not
  attack the 1.456× row-padding waste** (`BN` is the N dimension, the padding is
  in M), and the naive fix **BM = 32 would backfire** because routed experts
  average ~39 rows. F2 carries a `wm=4/wn=1` 4× dequant-duplication risk. None
  of the three deliverables I was handed is the cheapest next probe.
- **Recommendation.** **Merge nothing from this PR.** Delete all three arms and
  the `DARKBLOOM_STAGE2_GATHER` flag; to answer the advisor's explicit question,
  **no, it should not remain a flag** — there is no winning behaviour to promote
  to the unconditional path, and the official runner sets no environment
  variables, so keeping it would be 24,164 bytes of dead weight plus a
  silent-divergence surface. Dropping this PR returns the submitted surface from
  34,863 bytes of headroom (98.8% of the 3,000,000-byte cap) to **59,027 bytes**.
  Keep the five `research/` files: the pre-registration, the decision rule, the
  MSL compile checker, and especially `research/receipt_instrument_analysis.py`
  and `research/receipt_baseline_lottery.py`, which are the reusable part of
  this experiment's value.

#### One process change I would ask for

**Stop reading wins off `officialScore`, squad-wide, starting now.** §11 shows
the published score carries 0.517% of pure paired-baseline noise (bootstrap
cross-check: 0.535%), which is 2–3× larger than any single-mechanism effect this
campaign has measured. In a cohort of 18 receipts whose candidate speeds agree
to ±0.5% — that is, near-identical machine work — `officialScore` spans **1.805%**
and my losing v1 arm was the **maximum of all 18**. The current crown itself is
**+2.425% of lottery premium**: at a median baseline draw it scores 2.491874,
which is ~0.8–0.9% *slower in machine terms* than our own frontier code.

Two concrete asks:

1. **Adopt `ns` (fixed-normaliser speedup) or raw candidate seconds as the
   internal ranking statistic** in every assignment, comment, and merge
   decision. `ns` is a deterministic function of candidate seconds, so it
   inherits candidate-arm noise only. `officialScore` is what the leaderboard
   publishes and we cannot change it — but we should never *reason* with it.
2. **Re-audit the campaign's merged and scheduled conclusions** for any that
   rest on an `officialScore` delta under ~1.5%, explicitly including the
   "+1.08% expected from a 2-byte change" now holding the next slot. I am not
   claiming that one is wrong; I am claiming the evidence class cannot support it
   and that `research/receipt_baseline_lottery.py` can re-derive the answer for
   any receipt in about a second.

The honest promotion bar follows from the same arithmetic. From my control's
candidate speed, taking the crown at 50% probability across baseline draws needs
**+1.61% of score = −2.15% of decode seconds/token** (−0.109 ms on the 5.046 ms
step), or −6.45% of prefill seconds; 90% needs −3.08% of decode. That is roughly
**10× larger than any single mechanism measured this campaign**, mine included.
Lottery-farming is not the shortcut: bootstrapping over all 1029 observed
baseline pairs, my *best* receipt would need ~114 resubmissions to beat the
crown by luck, at ~28 min each and a hard limit of one submission in flight.

---

## Appendix — full detail

## 1. TL;DR

Both staging arms are **bit-exact within-noise losses**. Arm 2 (register
prefetch, shipped default) moved prefill kernel time by **ΔS = +0.4626 ms
(+1.83σ, candidate seconds −0.183%)**; arm 1 (double buffer, the pre-declared
canary) by **ΔS = +0.1150 ms (+0.45σ, −0.250%)**. My pre-registered
discriminating branch (*v2 wins while v1 regresses ⇒ store/dequant throughput is
binding*) **did not fire**; the branch that fired is *both null ⇒ close the
family*. Neither staging change reaches the term that binds this kernel; the
only effect either delivers is added instruction overhead.

**Recommendation: merge nothing.** Delete all three arms and the
`DARKBLOOM_STAGE2_GATHER` flag, reclaiming 24,164 bytes of the submitted
surface.

The larger finding is instrumental and campaign-wide: **the published
`officialScore` is dominated by paired-baseline measurement noise.** Arm 1's
apparently record `officialScore` of 2.545892 decomposes into **−0.250% of real
candidate change and +1.142% of baseline lottery** — it drew the slowest
baseline prefill of the entire day (99.2nd percentile of 1029). See §11.

---

## 2. What shipped

`DARKBLOOM_STAGE2_GATHER` is an **integer** lever resolved once per process by a
single shared parser, so the JIT `#define` and the dispatch-site trace cannot
disagree about which arm ran.

| arm | staging | `Ws` threadgroup bytes | barriers / k-iter | co-resident TGs |
|---|---|---|---|---|
| 0 | stock fused staging | 9,216 | 2 | ~3 |
| 1 | split + double buffer | 18,432 | 1 | ~1 |
| **2 (shipped default)** | split + register prefetch, single buffer | **9,216** | 2 | **~3 (unchanged)** |

The kernel change is a **288-line, zero-removed-line** insertion, byte-identical
in the AOT header and the JIT `mlx-generated` twin, entirely inside
preprocessor guards:

- `QuantizedBlockLoader` gains `struct StageRegs { uint8_t sb[kSrcBytes]; uint8_t sc[n_steps_per_read]; }` (18 B/thread),
  `template <bool wide_load> StageRegs prefetch() const` and
  `template <bool wide_store> void commit(thread const StageRegs&) const`.
- Arm 2's loop hoists iteration *k+1*'s device reads above the WAR barrier so
  DRAM latency flies across that barrier **and** across iteration *k*'s MMA
  chain, at **zero occupancy cost**:

```cpp
typename loader_w_t::StageRegs pf = loader_w.template prefetch<wide_load>();
for (int k = 0; k < K_it; ++k) {
  NAXTile<T, TM, TK> Atile[BK / SK];
  if (sg_active) { /* load_contig / load_rows_contig — same as stock */ }
  threadgroup_barrier(mem_flags::mem_threadgroup);            // WAR
  loader_w.template commit<wide_store>(pf);
  loader_w.next();
  if ((k + 1) < K_it) { pf = loader_w.template prefetch<wide_load>(); }
  threadgroup_barrier(mem_flags::mem_threadgroup);            // RAW
  if (sg_active) { /* MMA over Ws + tn*BK_padded + kk1 — same as stock */ }
  xn += BK;
}
```

Arm 2 was chosen as the shipped default over the textbook double buffer (arm 1)
because Apple's per-core threadgroup SRAM is ~32 KB: 9,216 B keeps ~3
threadgroups co-resident while 18,432 B allows ~1, and the expert grid launches
**4,096 threadgroups**. Arm 1's only unique benefit is 31 fewer barriers.

**Submitted paths (4, all scope-validated):**

```
Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized_nax.h
Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized_nax.cpp        # JIT twin — what actually runs
Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp
Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/jit_kernels.cpp
```

Research-only, not submitted: `research/nax_msl_compile_check.sh`,
`research/stage2-gather-prereg.md`, `research/receipt_instrument_analysis.py`.

---

## 3. Pre-registration (committed BEFORE any receipt)

`research/stage2-gather-prereg.md`, commit `b04cbfd`, **2026-08-05T09:45:02Z** —
the git commit timestamp is the ordering proof, since students cannot push and
the file reaches GitHub only via `submit_result`'s lease-push.

Sign convention `ΔS = S_cand − S_ctl` ms, **negative = win**:

| arm | point ΔS | 80% interval | point `ns` |
|---|---|---|---|
| v0 control | 0.0 | [−0.6, +0.6] | 2.5297 |
| v1 double buffer | +1.5 | [−4, +10] | 2.5166 |
| **v2 register prefetch** | **−4.0** | **[−9, +1]** | 2.5647 (+1.38%) |

Declared falsifiers: non-zero `max_abs_diff`; null within ±0.243%; wrong-sign v2
(⇒ store/dequant throughput, not load latency, is the binding constraint).

---

## 4. Verification performed

| check | result |
|---|---|
| Frontier read-only bit-exactness audit (4 questions) | **PASS on all four** |
| Offline MSL compile, both real static Laguna MoE shapes, arms 0/1/2 | `COMPILE OK (std=metal4.0)`, 5095/5096/5096 lines |
| Arm 0 preprocessed source vs stock | **byte-identical, 1,788,850 B** |
| Header ↔ JIT twin sync | added 288 = 288, removed 0 = 0 |
| `senpai/validate-assignment-scope.sh` | `assignment scope OK: 4 submitted path(s)` |
| `senpai/check-editable-budget.sh` | `current=2965137/3000000 headroom=34863 growth=24164/262144 files=142` |
| Host C++ compile (`setup.sh`) | clean |
| `./benchmark.sh --local-iterate`, arm 2 | `passed: true`, `max_abs_diff: 0`, golden `b9509697…` |
| Upstream-equivalence oracle, arm 2 (training `7b06e067`) | byte-identical to documented base — **no regression** |
| Upstream-equivalence oracle, arm 0 control, same binary (training `352bdbd9`) | byte-identical to arm 2 |

### Upstream-equivalence oracle — three-way byte-identical

I ran `research/run_upstream_equivalence.sh` on the shipped arm 2 and then, as a
same-binary control, with `DARKBLOOM_STAGE2_GATHER=0` (which I had already
verified preprocesses byte-identically to stock). Both produced **the same
report**, and it matches the base numbers already recorded by three siblings at
`research/CURRENT_RESEARCH_STATE.md:830-831` and
`research/frieren-host-cpu-budget.md:471`:

| step | max abs logit err | mean abs logit err | runtime token | upstream token |
|---|---:|---:|---|---|
| prefill | **0.125** | 0.011933609 | 5991 | 5991 |
| decode-0 … decode-7 | **0** | **0** | 509/902/5991 cycling | identical |

`EQUIVALENCE_EXACT_STEPS=8`, `EQUIVALENCE_EXIT=1`.

**The non-zero exit is a pre-existing, documented M4 Pro limitation, not a
regression.** The oracle applies its zero tolerance to prefill as well as
decode, and the batched NVFP4 prefill path cannot meet that against the BF16
upstream reference on this host. Every decode step is bit-exact and **every
token matches**. Candidate == arm-0 control == documented base, all three
byte-identical.

**Honest scope limit:** this oracle says nothing about the `_nax` kernel I
actually changed. This host is Apple GPU gen 16 and never selects `_nax`, and
per `CURRENT_RESEARCH_STATE.md:832` the oracle also never calls
`prepareFusedRuntimeWeights()`. It is a **no-regression guard on shared paths**,
and that is all I claim from it. Bit-exactness of the changed kernel rests on
the read-only audit, the byte-identical arm-0 preprocessing, and the ranked
receipt's `max_abs_diff`.

Audit detail: `prefetch`/`commit` replicate `load_unsafe_wide`
expression-by-expression with identical `load_ok`/`store_ok` predicates and a
lossless `uint8` scale snapshot; arm 1's single-barrier double buffer is
RAW/WAR-safe including the `gate_up_stage` alias (confined to buffer 0); arm 2
keeps both stock barriers; no barrier sits in divergent control flow; `next()`
is an unconditional pure advance executed exactly `K_it` times in all arms.

Residual risks the audit could not close: the unreachable value-identical
fallback rests on a pre-existing `STAGE_WIDEST` enumeration claim; the
`K_it == 0` corner is unreachable; and **arm 2's gain depends on the Metal
compiler not re-sinking the hoisted loads** — a performance question, not a
correctness one, and precisely what the receipt measures.

⚠️ **Budget flag for the advisor:** only **34,863 bytes** of editable-surface
headroom remain (2,965,137 / 3,000,000). Future kernel work on this surface
needs a byte-headroom plan before implementation.

⚠️ **Local `--local-iterate` is a regression guard only.** This M4 Pro host
reports Apple GPU generation 16 and never selects the `_nax` kernels, so its
prefill number carries no evidence about this change. It confirms only that the
host C++ still compiles and that untouched paths are unaffected
(`max_abs_diff: 0`).

---

## 5. 🔬 Instrument characterisation on n = 1022 receipts — squad-wide consequences

**This is the highest-value finding of the session and it changes evidence
budgets for all four students.** Reproducible via
`research/receipt_instrument_analysis.py`.

The ranked receipt feed is fully readable through the API that backs the CLI
(the CLI truncates `metrics`; the API does not):

```bash
curl -sS -H "Authorization: Bearer ${MLXFAST_API_TOKEN}" \
  "https://api.mlx.fast/api/benchmarks/eigenlabs%2Fmlxfast-challenge/submissions"
```

That returns every solver's receipts with full `officialMetrics`, full `note`
bodies, and `rejectionReason`. Restricting to correctness-passing receipts with
paired baselines gives **n = 1022 over 2026-07-24 … 2026-08-05**.

```
== baseline arm: identical pinned code on every receipt
   prefill rel sd 1.927%   decode rel sd 0.247%
   day-mean baseline decode spans 0.188% across 13 days -> host drift is negligible

== frontier-tight population (within 3% of best on both axes), n=302
   prefill  candidate 0.905%  baseline 2.006%  r=-0.062
            paired speedup 2.247% observed vs 2.200% predicted -> pairing costs 2.5x
   decode   candidate 0.517%  baseline 0.260%  r=-0.058
            paired speedup 0.592% observed vs 0.579% predicted -> pairing costs 1.1x

== ranking statistics, same population
   officialScore       rel sd 0.825%
   fixed-normaliser ns rel sd 0.569%   -> 1.45x tighter
```

### 5.1 The host is stable; the *paired baseline* is the noise source

With identical pinned code on 1022 receipts across 13 days, baseline decode has
rel sd 0.247% and its day-means span only **0.188%**. The ranked M5 is not
drifting in any way that matters.

### 5.2 The two arms are uncorrelated, so pairing *destroys* precision

r = −0.062 (prefill) and −0.058 (decode) at n = 302. The "same-session paired
baseline" cancels no common-mode effect **because there is none to cancel**.
Observed paired-ratio noise matches the independent-noise prediction to two
decimals on both axes: √(0.905² + 2.006²) = 2.20% predicted vs 2.247% observed.
Dividing by the baseline therefore *injects* the baseline's 2.0% prefill noise
into a candidate measurement that is intrinsically ~10× quieter.

### 5.3 On a homogeneous same-day population the asymmetry is 10.5×

Today's 41 frontier-tight receipts span 9.5 h, four solvers, dozens of code
versions: candidate prefill rel sd **0.183%** vs baseline prefill rel sd
**1.93%** in the same sessions. Because 0.183% still *contains real code
differences*, it is an **upper bound** on candidate-arm measurement noise.

### 5.4 Correction to a claim I previously made

I earlier attributed a "+0.321%, +12.4 sd" gap between `c3ce66e` and three
8/4-morning replicates to **cross-day host drift**. That was wrong. Candidate
decode moved 5.135 → 5.046 ms (**−1.76%**) between those groups, and a host
whose fixed-code baseline decode moves 0.188% over 13 days cannot produce a
1.76% candidate swing. **The frontier genuinely advanced; there was no drift.**

Revised rule, stated non-dogmatically because I cannot inspect organizer-side
diffs: **a same-day candidate-arm control is sufficient and an adjacent-day one
is defensible. What you must not do is compare through baseline-divided
statistics.**

### 5.5 Budget consequence: ~6 receipts → 1

The planned "run the control back-to-back with the treatment" protocol is
**unnecessary**. `c3ce66e` (today 09:33, our own submission) *is* a valid v0
control, and today's 41-receipt frontier-tight population supplies the noise
model for free. Combined with §5.6 this collapses the receipt budget for this
experiment from ~6 to **1 for the primary test**.

*Actual spend was 2:* the primary v2 receipt, plus the v1 canary that my
pre-registered decision rule triggered when v2 landed inside the null band. That
escalation was itself pre-declared, so the budget claim holds as stated — one
receipt per *question*, and the second question (did the lever activate at all)
only became live because the first answer was null.

### 5.6 Power, and why activation proof comes for free

Predicted v2 effect −4.0 ms on S = 97.95 ms is **−4.08%** of candidate prefill,
i.e. **~22σ at n = 1** against a 0.183% sd. Even the pessimistic tail of the
pre-registered 80% interval (+1 ms) is ~5.6σ, and the 15.4 ms recoverable
ceiling is ~86σ.

This also resolves the activation-proof problem. The assignment mandated
confirming `mlxfast: fusion active: stage2_gather v<N>` on stderr. **That is not
executable** (§6.2). But the arms differ only by the integer that drives *both*
the JIT define and the code path, so at 0.18% noise **any** real shift ≥0.5%
proves the define arrived. If v2 is null within ±0.5%, the **v1 canary** —
occupancy halving via 9,216 → 18,432 B threadgroup memory — becomes a
high-powered activation test rather than a hope.

### 5.7 Honest caveats

The frontier-tight population is other solvers' code, so its homogeneity is
*inferred* from its 0.18% tightness rather than proven. 0.183% is an upper
bound, not an unbiased noise estimate. My earlier hand-propagated figures
(`ns` ~0.45%, `officialScore` ~0.72%, "12× on the prefill axis") were loose and
are **superseded** by the measured 0.569% / 0.825% / 1.45× overall, with 2.5× on
the prefill axis at n = 302 and 10.5× on the same-day population.

§5 was computed at `n = 1022`; §11 re-fetched the feed later the same day and
works at `n = 1029`. The seven extra receipts move nothing materially, but the
two sections are not the same snapshot and I have not back-fitted either.

Useful reference constants now pinned: `NORM_DECODE = 0.013890`,
`NORM_PREFILL = 0.0003845` are fixed normalisers, **not** the session baseline
(a typical session reports `baseline_prefill ≈ 0.000371`,
`baseline_decode ≈ 0.013900`). Best-ever observed: cand_pre 190.155 µs,
cand_dec 5.03924 ms.

---

## 6. Operational findings the squad needs

### 6.1 The receipt channel is serialised per account — limit 1

```
{"error":{"code":"conflict","message":"account already has 1 submission(s)
 in flight for this benchmark (limit 1)"}}
```

Round trip ≈ 28 min, and the account is **shared with the three sibling
students**. This is not documented in `mlxfast submit --help`. It invalidates
the "run A and B concurrently" instruction present in all four live
assignments. Given §5.5 the right response is not to queue more receipts but to
**stop spending them on controls the public feed already provides**.

### 6.2 There is no official stderr / run-log access

The CLI is a bun shim over `mlxfast.js`; its only routes are
`/api/benchmarks/{id}/{submissions,notes,jobs}`, `/api/submissions/{uuid}`, and
`/api/challenges/{slug}`. No log route, and no log field anywhere in the API
payloads. `rejectionReason` on a `failed` run gives an organizer-repo Actions
URL, but `GITHUB_TOKEN` returns **401 Bad credentials** against
`api.github.com`, so those workflow logs are unreachable too. **Any assignment
step that requires reading benchmark stderr is unexecutable** and should be
replaced by a powered timing contrast.

Worth separating two things that are easy to conflate. The *stderr channel
itself works locally*: `/tmp/local_iterate_v2.log` contains worker-prefixed
fusion traces from sibling optimisations —

```
mlxfast-worker: mlxfast: packed-scales active: packed routed gate/up bank prepared
mlxfast-worker: mlxfast: lm_head prune active (coarse copy resident)
mlxfast-worker: mlxfast: packed-scales active: routed swiglu qmv packed dispatch
```

— and yet `stage2_gather` appears **zero times**, not even as `inactive`. That is
the expected signature of this host never building the `_nax` expert JIT kernel
(gen 16), so **local absence of the trace confirms the documented host
limitation rather than a broken lever**. The consequence stands: on the M5, where
the kernel *is* built, the trace would print to a stream nobody can read. Hence
the v1 canary.

### 6.3 Static review can fail a submission outright

Receipt `afec358a` failed at workflow step **"Review submitted code for
benchmark bypasses"** — a distinct outcome from `rejected`. Worth knowing that
`failed ≠ rejected ≠ low score`; all three need separate inspection.

### 6.4 A `rejected` receipt is still a full result

`rejectionReason: "score did not improve current best"` — the receipt still
carries complete metrics and both floor verdicts. `rejected` is a *ranking*
status, not a correctness or error status.

---

## 7. Roofline framing (conditional — please read the caveat)

`fp_gather_qmm_rhs_expert_nax` costs **43.2619 ± 0.402 ms** across 39 routed
layers.

| bound | value |
|---|---|
| weight DRAM floor | 27.9 ms (15.22 GB after 20.26% zero-row (layer,expert) pairs, 1.080× chunk re-read) |
| MMA floor (issued) | 26.1 ms (1.456× 16-row padding, 453,120/311,296) |
| serial D + M | 54.0 ms |
| measured | 43.26 ms = **0.80 of serial** |
| perfect-overlap bound max(D, M) | 27.9 ms |
| **recoverable** | **15.4 ms** — only ~41% of achievable overlap realised |

Elasticity: **0.344% of `ns` per ms**. Per the advisor's framing this block owns
**+26.4 ms** of the 49.19 ms session-normalised prefill residual — the largest
single identified item.

**Caveat, and I want to be explicit about it:** in-situ scaled-block
differencing prices the *marginal* cost of the block, not its standalone cost.
The 15.4 ms recoverable figure is therefore **conditional on `dS_1 = 43.26 ms`
being absolute rather than marginal**. I did not re-derive it. **A second caveat
was added by independent review after this table was written:** the DRAM floor
uses peak 545.5 GB/s, which no real kernel sustains, so the realistic recoverable
headroom is nearer **8–12 ms** than 15.4 ms. See §10.3.

Also confirmed negative: attention QKVO prefill already runs at **117% of the
dense bf16 ceiling** (22.21 ms at 65.74 TFLOP/s) — **no wins available there.**

---

## 8. Suggested follow-ups (NOT implemented here)

1. **Elide the materialised sorted `x` copy.** The fused gather-QMM consumes a
   materialised sorted copy of `x` (`SwitchLayers.swift:320-349`), ~32 MiB/layer
   ≈ **1.25 GB per prefill pass**, read by `lagunaFusedSortedRoutedGateUp`
   (`LagunaRuntimeModel.swift:9630-9700`). Feeding unsorted `x` + `rowOrder` as
   LHS indices elides it: estimated **2–2.9 ms, bit-exact**.
   **Risk:** contiguous sorted rows may be *why* this block sustains 408 GB/s;
   scattered 4 KB row reads could cost more than the copy saves. Needs its own
   assignment, not a bolt-on.
2. **Do the two cheap diagnostics before F2/F3.** Independent review corrected
   an attribution error I had made here: **BN = 32 does not attack the 1.456×
   row-padding waste.** `BN` is the *N* (output-column) dimension; the padding
   waste is in *M* (routed rows padded to a multiple of 16). BN = 32 is an
   **occupancy** lever, not a work-reduction lever, and the obvious
   work-reduction sibling **BM = 32 would backfire** — routed experts average
   ~39 rows per (layer, expert) pair, so halving BM roughly doubles the tile
   count without removing padding. F2 (staging-free) additionally carries a
   `wm=4/wn=1` **4× dequant-duplication risk**: every one of the four
   simdgroups would dequantise the same weight block.
   The cheaper decisive steps, in order:
   (i) **mine the existing `fc204`/`fc205` (`WIDEST`/`WIDELD`) receipts** for
   store/load-width dose data already paid for — zero receipt cost; then
   (ii) a **bit-exact `Ws` dead-padding occupancy dose-response** (1–2 receipts)
   that varies only threadgroup-memory footprint and therefore isolates
   occupancy from every other mechanism. Only if (ii) shows real slope is F2
   or F3 worth a slot. I did **not** implement any of these.
3. **Rank by `ns`, never `officialScore`** — now quantitatively justified
   (0.569% vs 0.825% rel sd, n = 302). Consider making this the squad-wide
   reporting default.
4. **Mine the note corpus.** The submissions API exposes **1495+ full note
   bodies from every solver** — a large untapped record of competitor findings.
   I deliberately did not explore it (rabbit hole); it deserves one bounded,
   time-boxed pass by someone.
5. **Re-audit every campaign conclusion drawn from an `officialScore` delta**
   under about 1.5%, explicitly including the "+1.08% from a 2-byte change" that
   currently holds the next slot. §11 shows why the evidence class cannot support
   effects of that size, and `research/receipt_baseline_lottery.py` re-derives the
   candidate-vs-lottery split for any receipt in about a second. This is analysis
   only — zero receipt cost — and it is the highest-leverage item on this list.

---

## 9. Reproduction

```bash
# arm selection (integer lever, default 2 is what shipped)
#   quantized.cpp:1611  darkbloom_stage2_gather_variant()  ->  if (s.empty()) { return 2; }
# or at runtime:
DARKBLOOM_STAGE2_GATHER=2 ./benchmark.sh --local-iterate

# offline MSL compile check, all three arms, both real Laguna MoE shapes
research/nax_msl_compile_check.sh

# instrument characterisation (needs MLXFAST_API_TOKEN)
python3 research/receipt_instrument_analysis.py
```

Commit chain: `be2a5a2` (assignment marker) → `342f931` → `1137956` →
`b04cbfd` (pre-registration) → `1f6f95c` (instrument analysis) → `e8ec86a`
(decision rule, committed after dispatch and before any result was visible) →
HEAD (baseline-lottery script + σ correction). **The submitted editable surface
has not changed since `1f6f95c`**: `git diff --name-only 1f6f95c..HEAD | grep -v
'^research/'` is empty.

---

## 10. Mechanism analysis — why both arms are null

Before writing this section I spawned an independent frontier agent with no
conversation context and asked it to attack my own mechanism analysis. It found
**six real errors**. All six are accepted and applied below; where a claim of
mine is now weaker or retracted, that is flagged in place rather than quietly
edited. Two of the six invalidated numbers I had already committed, so the
correction trail is: review arrived *after* commit `e8ec86a`, *before* any
submission. `research/stage2-gather-decision-rule.md` is corrected in this PR.

### 10.1 The σ my own tool got wrong

`ΔS = S_cand − S_ctl` is a **difference of two independent draws**, each with
single-draw σ ≈ 0.179 ms. The correct standard deviation of the difference is
therefore

```
sigma_dS = 0.179 * sqrt(2) = 0.253 ms
```

`/tmp/report_receipt.py` divided by the *single-draw* σ, so every "σ" it printed
was inflated by √2. Corrected significances:

| arm | `ΔS` | σ as first reported | **corrected** |
|---|---:|---:|---:|
| v2 register prefetch | +0.4626 ms | +2.6σ | **+1.83σ** |
| v1 double buffer | +0.1150 ms | +0.6σ | **+0.45σ** |

Neither reaches my pre-registered ±3σ band, so the *decision* is unchanged — but
v2 is meaningfully less exciting than I first wrote, and I would have reported a
false "borderline signal" had the review not landed. The bug is in my scratch
tool, not in the committed research script;
`research/receipt_baseline_lottery.py` computes the paired quantities directly.

### 10.2 Ranked mechanism candidates

**1 — Plain added instruction overhead (strongest; promoted to first place).**
Splitting one fused load-store loop into `prefetch()` + `commit()` costs roughly
5–15 extra instructions per k-iteration: recomputed addresses, the 18-byte
`StageRegs` struct, and the loop-carried copy that keeps the prefetched value
live across the barrier. On a kernel already running at 64.5% of peak bandwidth
with 32 k-iterations, that is **+1–2% of kernel time**. The measured shift is
**+1.07%** of the kernel's 43.26 ms. One mechanism, right magnitude, right sign,
no auxiliary assumptions. Independent review argued this is more parsimonious
than my original register-pressure story, and I agree.

**2 — The compiler had already done the hoist (explains the *zero* part).**
Metal's optimiser is free to move device loads across a
`threadgroup_barrier(mem_flags::mem_threadgroup)` when the loads do not alias
threadgroup memory, which is exactly true of the weight reads here. If the
hardware schedule was already overlapping iteration *k+1*'s reads with iteration
*k*'s MMA chain, then arm 2 changes nothing about the schedule and only adds the
bookkeeping from mechanism 1. This is consistent with arm 1 — which changes the
schedule *structurally* by removing a barrier — also landing at zero: there was
no stall to remove.

**3 — Register pressure and occupancy (demoted, not excluded).** 18 B/thread of
extra live state is small next to the accumulator tiles, and I have no register
readout for this kernel because the local host never builds it (§10.5). It
remains a plausible contributor to v2's slightly larger regression than v1's,
but it is no longer my leading explanation and the data cannot separate it from
mechanism 1.

**Retracted: "thread-level parallelism already hides the latency."** I asserted
this in the strong form *"~3 co-resident threadgroups per core give ample
latency coverage, so there was nothing to hide."* That does not hold. A
Little's-law estimate for the required memory-level parallelism, and a
three-alternator phasing model, both show 3 **phase-locked** threadgroups per
core are *marginal* rather than ample — they are phase-locked precisely because
every threadgroup hits the same two barriers per iteration. The measured 64.5%
bandwidth utilisation is a better fit for **stochastic phase collision** (three
alternators occasionally all in the same phase, leaving DRAM idle) than for
comfortable coverage. The defensible claim is narrower: **these two source
transforms do not reach the binding term.** Why the binding term is insensitive
to them is mechanism 2's job, not TLP's.

**Demoted to hypothesis: "the 15.4 ms roofline gap is not a latency gap."**
This was a verdict drawn from a null, which my own pre-registered decision rule
explicitly forbids — the rule prescribes *escalation* on a null, not a
conclusion about the underlying physics. Two null staging transforms are
evidence that *source-level staging restructuring* does not recover the gap.
They are weak evidence about what the gap *is*. Treat it as an open hypothesis
with two live alternatives: stochastic phase collision (above), and real MMA
work that the roofline's issued-instruction floor already counts but that the
overlap bound optimistically assumes is free.

### 10.3 The roofline framing, correctly qualified

The algebra in §7 is internally consistent — 41.2% of achievable overlap
realised, 15.4 ms nominally recoverable — but it rests on **peak 545.5 GB/s**,
which no real kernel sustains. Against a realistic sustained-bandwidth ceiling
the recoverable headroom is more like **8–12 ms**, not 15.4 ms. Every downstream
elasticity figure (0.344% of `ns` per ms; prefill score elasticity −0.362)
should be applied to that smaller number. This does not change the conclusion
that the kernel is the largest single attributable prefill item; it does mean
the prize for solving it is ~30% smaller than §7 advertises.

### 10.4 v1 was a three-way confound

I designed v1 as the pre-declared canary for "the opposite end of the occupancy
trade," and it does sit at the opposite end — but it changes **three** things at
once and I cannot attribute its 0.115 ms to any one of them:

1. occupancy: `Ws` doubles to 18,432 B/TG, co-resident threadgroups fall ~3 → ~1;
2. barrier count: 2 → 1 per k-iteration;
3. it *retains* the prefetch/commit split, so it also carries mechanism 1's
   overhead.

Worse, its **delivered dose is unknown**: I never observed the achieved
occupancy on M5 and cannot, so "co-resident TGs ~3 → ~1" is a static
threadgroup-memory calculation, not a measurement. As a *falsifier* for the
latency hypothesis it still works — a real exposed-latency stall should have
made these two arms diverge by millisecond amounts in opposite directions, and
they agree to 0.35 ms. As a *positive* measurement of any single mechanism it is
worthless. That is the reason §8 now asks for a dose-response that varies only
threadgroup-memory footprint.

### 10.5 Why there is no local mechanism evidence at all

The local host is an M4 Pro (Apple GPU generation 16, 48 GiB, low-memory startup
profile). It **never builds the `_nax` expert kernel**: the fusion trace channel
demonstrably works — sibling traces `packed-scales active` and `lm_head prune
active` both print — yet `stage2_gather` prints *nothing*, not even the
"inactive" branch. So there is no local profile, no local occupancy readout, no
local register count, and no local timing for the kernel this PR changes. The
assignment's mandated stderr check for
`mlxfast: fusion active: stage2_gather v<N>` is **not executable anywhere I have
access to**: the official runner exposes no stderr or run-log route (§6.2). Two
ranked receipts are the entire instrument, which is the deeper reason the next
probe should be a *dose-response* rather than another single point.

### 10.6 Corrected deliverable priority

| deliverable | as briefed | corrected assessment |
|---|---|---|
| F3 — BN = 32 | "attacks the 1.456× row-padding waste" | **Wrong attribution.** `BN` is the N (output-column) dimension; padding waste is in M. BN = 32 is an **occupancy** lever. Its work-reduction sibling **BM = 32 would backfire**: routed experts average ~39 rows per (layer, expert) pair, so halving BM roughly doubles tile count without removing padding. |
| F2 — staging-free path | "frees the occupancy-limiting resource" | Directionally sound (returns 9,216 B/TG) but carries a **`wm=4/wn=1` 4× dequant-duplication risk**: all four simdgroups would dequantise the same weight block. |
| — | not briefed | **Cheapest and most decisive: mine the existing `fc204`/`fc205` (`WIDEST` / `WIDELD`) receipts** for store/load-width dose data the squad already paid for. Zero receipt cost. |
| — | not briefed | Then **one bit-exact `Ws` dead-padding occupancy dose-response** (1–2 receipts), varying *only* threadgroup-memory footprint. |

§8 item 2 has been corrected to match this table.

---

## 11. The baseline lottery — why `officialScore` cannot see a 1% change

This section is the campaign-level finding, and it is more valuable than the
experiment it came out of. Every number here is reproduced by
`research/receipt_baseline_lottery.py` (new in this PR) against the live
submissions feed, `n = 1029` correctness-passing receipts with paired baselines.

```bash
MLXFAST_API_TOKEN=... python3 research/receipt_baseline_lottery.py \
    c3ce66e cdf71fa 4058d0b 46eeccf b6032ae
```

### 11.1 The baseline arm is pinned code, so its spread is pure noise

Every receipt measures a *baseline* built from unchangeable reference code. Its
variation across 1029 receipts is therefore, by construction, measurement noise:

```
baseline prefill : mean 372.353 us   rel sd 1.932%   min 362.924   max 396.641
baseline decode  : mean 13.85486 ms  rel sd 0.248%
day-mean baseline decode spans 0.188% across 13 days  ->  host drift negligible
```

At the score's 25% / 75% weights that injects

```
hypot(0.25 * 1.932%, 0.75 * 0.248%) = 0.517%
```

of pure noise into **every published `officialScore`**. An independent empirical
bootstrap over the same 1029 baseline pairs gives score sd 0.01349 absolute =
**0.535%**, confirming the propagated figure.

For contrast, the fixed-normaliser `ns` is a deterministic function of candidate
seconds alone, so it inherits **only** candidate-arm noise. That is the whole
argument for ranking on `ns`. (A caveat on my own earlier reasoning: I once
cited a cohort's `ns` spread as *measuring* `ns` noise — that is circular, since
the cohort was selected on candidate speed. The non-circular argument is the
functional one above.)

### 11.2 Decomposing arm v1's apparent record

Log-decomposition of v1's `+0.896%` `officialScore` gap versus my same-day
control:

```
candidate (real code effect)   -0.250%
baseline  (pure lottery)       +1.142%
total                          +0.892%
baseline prefill moved +4.648%  (371.148 -> 388.398 us);  baseline decode +0.008%
```

v1's baseline prefill draw of 388.398 µs is the **99.2nd percentile of 1029**
draws of that same pinned code (z = +2.23) and the **slowest baseline of the
entire 2026-08-05 day** (day n = 47; the day's maximum *is* v1's draw).

The cleanest demonstration is a cohort test. Taking all receipts whose candidate
speed is within ±0.5% of my control on **both** axes — n = 18, with cand_pre rel
sd 0.250% and cand_dec rel sd 0.184%, i.e. near-identical machine work —
`officialScore` spans **1.805%** (rel sd 0.595%). **My losing v1 arm scored the
maximum of all 18.**

### 11.3 The crown is a lottery artifact too

Re-scoring each receipt against the *median* baseline draw (prefill 368.490 µs,
decode 13.84835 ms) separates code from luck:

| receipt | cand_pre µs | cand_dec ms | officialScore | at median baseline | lottery premium | base_pre pct |
|---|---:|---:|---:|---:|---:|---:|
| `46eeccf` **crown** (lBroth) | 190.547 | 5.10706 | 2.552308 | **2.491874** | **+2.425%** | **99.7** (z +2.90) |
| `b6032ae` best-ever decode | 191.141 | 5.03924 | 2.514911 | 2.515025 | −0.005% | 16.5 |
| `c3ce66e` my v0 control | 191.308 | 5.04644 | 2.523276 | 2.511785 | +0.457% | 54.1 |
| `4058d0b` my v1 | 191.532 | 5.06130 | 2.545892 | 2.505520 | +1.611% | 99.2 |
| `cdf71fa` my v2 | 192.211 | 5.05080 | 2.505056 | 2.507204 | −0.086% | 52.2 |

**The crown holder's code is ~0.8–0.9% slower in machine terms than our own
frontier.** Its decode step of 5.10706 ms is 1.35% slower than the best decode
ever recorded in the feed (5.03924 ms), and its fixed-normaliser `ns` of
2.524190 is below both my control (2.544360) and the feed's best `ns`
(2.547641). It holds the crown on a **+2.90σ** baseline draw. "0.25% from the
crown" therefore does not mean what it appears to mean: in machine terms we are
already ahead, and in published-score terms the gap is a draw we do not control.

### 11.4 Lottery-farming is not a strategy (checked, then closed)

The obvious exploit is to resubmit a good candidate until it draws a lucky
baseline. Empirical bootstrap of `P(score > 2.552308)` resampling all 1029
observed baseline pairs:

| receipt | E[score] | sd | P(beat crown) | expected receipts |
|---|---:|---:|---:|---:|
| `c3ce66e` control | 2.519146 | 0.01349 | 0.9% | ~114 |
| `b6032ae` best-ns | 2.522395 | 0.01350 | 1.5% | ~69 |
| `cdf71fa` v2 | 2.514551 | 0.01346 | 0.4% | ~257 |
| `4058d0b` v1 | 2.512862 | 0.01345 | 0.4% | ~257 |
| `46eeccf` crown | 2.499176 | 0.01338 | 0.1% | ~1029 |

At ~28 minutes per round trip and a hard **limit of one submission in flight per
account, shared across all four students** (§6.1), ~69 receipts is over a day of
the squad's entire submission bandwidth for a 1-in-69 shot. Closed.

### 11.5 The honest promotion bar

Inverting the bootstrap gives the candidate-side improvement needed to take the
crown with a given probability, starting from my control's candidate speed:

```
50% promotion:  +1.61% of score  =  -2.15% decode seconds  or  -6.45% prefill seconds
90% promotion:  +2.31% of score  =  -3.08% decode seconds  or  -9.24% prefill seconds
```

A **−2.15% decode step — −0.109 ms off 5.046 ms — makes the crown a coin flip at
any baseline draw.** That is roughly **10× larger than any single-mechanism
effect this campaign has measured**, mine (0.18–0.25%) included. The strategic
implication is not "try harder on 0.2% mechanisms": it is that the remaining
promotion has to come from something structural on the **decode** axis, which
carries 75% of the weight and is the axis where the baseline injects only 0.248%
of noise — i.e. the axis where a real win is actually *visible*.
