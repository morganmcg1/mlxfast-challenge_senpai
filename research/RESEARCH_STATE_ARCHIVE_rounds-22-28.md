# SENPAI Research State — chronology archive, rounds 22–28

Pruned from `CURRENT_RESEARCH_STATE.md` on 2026-08-07 at the round-29 launch.
Earlier rounds live in `RESEARCH_STATE_ARCHIVE_through-round-21.md`.

---

# SENPAI Research State

- **2026-08-06 20:40 UTC** — round 22 closed, **round 23 launched**. #143 and
  #138 merged; the base advanced to `9dd2eec3`. Round 22's governing rule
  ("every arm has a free offline falsifier that runs FIRST") paid three times:
  #142, #143 and #137's Step 0 each reached a terminal verdict for **zero
  receipts**. Two whole byte families are now permanently closed by exhaustive
  offline evidence (§8), and the programme's centre of gravity moves from
  **bytes** to **time**: three of the four round-23 arms attack the §4.1
  contradiction directly. #137 pivoted off its refuted hypothesis into the
  round's first genuine green arm and holds the receipt slot.
- **2026-08-06 21:00 UTC** — no receipts yet; all four round-23 arms still
  `status:wip`. Two things changed. (1) A **human operator** amended
  `senpai/program.md` (`bdb77bb0`) to define a **cross-instance submission
  queue**; this closes §R21.7, retires our ~35 min per-receipt price, and
  reprices receipt-free work upward (§6, §10). (2) An audit of the **offline
  transform surface** found that 123 of our 142 editable files have never been
  touched, that the Laguna transform is a byte-identical CoW pass-through, and
  that its output is pinned by **no** golden digest — but also that editing
  `Sources/MLXFastTransform/` flips `source_hash()` and forces a full 21.6 GB
  regeneration on the official host, against 49/1399 submissions already dead
  on timeout. Recorded as §9 item 12 behind a null-layout cost probe.
- **2026-08-06 21:55 UTC** — two corrections that change how we assign work.
  (1) The human operator **replaced** the day-old queue rule with `55ab1b2`,
  "Let submitters manage validation retries": there is now **no queue owner**
  and each dispatcher owns its own retries (§10). (2) Direct source reading
  found that our **M4 prefill per-kernel census measures kernels the M5 never
  executes** — the long-standing "94.2% of prefill is `_nax`" claim is
  *inverted* (§3a). That closes the row-tile axis of the gather GEMM and
  **retracts its banked +1.9–2.6% prize** (§8), and it establishes that the
  steady decode step is **100% host-independent**, while an M4 host can still
  validate a prefill kernel change's implementation, correctness and
  reachability — only its *timing* is not M5 ranking evidence.
- **2026-08-06 21:55 UTC (operator `eae07f01`, "Soften Maple research
  heuristics")** — a direct critique of this advisor's posture: **we have been
  closing families too fast and applying numeric gates too rigidly.** Six
  binding changes, all recorded in §0a: the **+0.61% advisor acceptance bar is
  deleted**; 0.243% is noise context, **not** a submission or promotion
  threshold; **one receipt can justify a clear win**; student-host prefill
  experiments are **endorsed** for implementation/correctness/reachability
  validation; `officialScore` **is** authoritative for ranking (`ns` remains
  the attribution instrument); and a closed family may be reopened by a **new
  mechanism or new evidence**, not merely a repeat. The same commit
  independently confirms our §3a census correction ("94.2% of prefill GPU time
  on the M4 student hosts runs kernels the M5 never executes") and records
  that the public field has been stuck on the prefill axis for **102
  consecutive submissions**.
- **2026-08-06 23:20 UTC — round 23 closed, round 24 fully launched.** #158
  merged; the base advanced to **`268fb087`**. The round's headline result is a
  *retraction*: nezuko's own r2 withdrew the **1.9 µs/dispatch decode floor**
  and its 771 µs / 9.6% headline, replacing it with **no band at all** — the
  per-dispatch cost is real but **site-specific**, spanning ≈1.5–8 µs, and it
  lives *inside* GPU busy at a fixed 45 CBs/step, so it must never be summed
  with §4.5's per-CB idle gap or §1.1's host gap (§4, §4.1b). Two measurement
  laws came out of the same PR and now bind every arm: the **GPUPROF clock
  defect** (`perf_counter` has a process-relative epoch on macOS CPython 3.9.6;
  "0 records inside N steps" is a *failed run*, not a zero-work result) and
  **cross-sweep irreproducibility** (arm-level between-session scatter ≈ ±70 µs
  ⇒ design local decode arms with Δ ≥ 150 dispatches). Merging #158 also opened
  a contradiction rather than closing one: #101 measured **+0.456 ms/step** of
  decode concurrency that #158's `gpu_busy_sum` says cannot exist (≤0.06
  ms/step). That is now **§4.9**, and it is assigned as **#174**. All four
  students are live: #137 fern (lm-head cascade fusion, holds the only receipt
  slot), #148 frieren (prefill injection ledger), #170 tanjiro (`_nax`
  gather-GEMM régime discriminator), #174 nezuko (decode exposure audit).
- **2026-08-07 02:00 UTC** — ⭐ **#174 resolved §4.9 and rewrote the decode
  map.** The contradiction is settled as **R-B (sibling shadowing)**: #158's
  "hidden concurrency ≤ 0.06 ms/step" was an **arithmetic artifact**
  (`busy_c(k) = busy_s(k) − D(k)`), and the corrected per-CB price is
  **0.540 µs/CB**, not 1.588. Real decode concurrency is **382–448 µs/step**
  and **we are already collecting all of it** — #101's +456 µs now replicates
  across three sessions (421/448/456/490/580). Nested-group composition
  isolates the hiding to exactly three small kernels at **E ≈ 0.10**, while the
  big matvecs sit at **E ≈ 1.0**. Consequences: the whole *buy-more-overlap*
  branch (L1 multi-stream, L3 flush placement, dispatch-count pricing) is
  **closed**, and pricing a decode change by removed-dispatch count is now a
  banned move (§4.12.3). In its place #174 delivers a roofline re-pricing that
  says the **weight-streaming pool is FINISHED** (89–98% of the M4 Pro DRAM
  roofline, 338 µs/step left) and hands us a target nobody was working on:
  ⭐ **T1, decode attention occupancy — 564 µs/step = +8.26%**, one threadgroup
  per *pair* of query heads (32 and 24 TGs on a 20-core GPU), 37.1% / 34.7%
  unique-byte efficiency, and an **occupancy/latency** mechanism, which is
  §4.11.3's privileged transfer class. See §4.12 and the v3 sequencing.
- **2026-08-07 02:40 UTC** — #174 **merged** (advisor branch → `3b75a115`) and
  **T1 assigned as #196** (nezuko,
  `maple-2026-08-07a-decode-attention-occupancy`). Before writing that brief I
  read both attention kernels directly and **two of #174 §5.1's premises did
  not survive** (new **§4.12.8**): the threadgroups are **1024 threads**, not
  32, so the shipped grid is 32/24 threadgroups of 32 simdgroups each; and the
  kernel **already implements flash-decoding** (per-simdgroup running max/sum,
  a post-loop `simd_max`/`simd_sum` merge, no barrier in the KV loop), so a KV
  split is a *lift* of already-bit-exact code. Integer-wave arithmetic then
  kills the proposed **S=2** arm outright (zero gain on both host core counts)
  and picks **S=5** as the unique small exactly-optimal split, and it kills the
  head-axis repartition twice over. Everything downstream is gated by one
  unmeasured number — **32 vs 96 co-resident simdgroups per core** — so #196
  opens with a residency staircase that is merge-worthy on its own.
- **2026-08-07 03:05 UTC** — **#137 r3 returned the anchoring receipt and
  §4.11.5 is RESOLVED.** Receipt `08ddee45` reads `ns = 2.59440830`, −0.147%
  = **−0.66σ** of the paired cross-session sd, and clears the HEALTHY edge at
  −1.01σ: **ROW A, the frontier is intact — the six promoted maple merges after
  `97a5090c` did not regress the M5 frontier.** Correctness was unanimous
  (`max_abs_diff 0` over 1344 checked steps, GPQA 9/9, both floors True). The
  receipt also convicted the **row-major sparse-refine arm** — r3 is r2's tree
  with one default flipped, and defaulting the arm OFF recovers **+0.2237% of
  `ns` (+1.01σ) and −16.59 µs/token** — so `DARKBLOOM_LMHEAD_ROWMAJOR_REFINE`
  is now a **twice-measured M5 negative** headed for the cleanup list, not
  another arm. Three constants fell out of it and are recorded in the new
  **§4.11.6**: the M5 host's own baseline drifts **monotonically +0.091% over
  ~3 h (≈0.03%/hour)**; `officialScore` again failed to attribute a small
  mechanism (−0.593% on a 3.7×-looser σ, almost all of it the prefill baseline
  draw); and one receipt now costs **43 min 55 s** dispatch→verdict, not ~35.
  ⚠️ The merge itself **failed on a conflict in `research/decode_probe.py`
  only** — fern and nezuko independently fixed the same GPUPROF parser bug, and
  nezuko's merged version is a strict superset — so #137 went to **r4** with a
  purely mechanical resolution instruction and no re-measurement. fern is
  effectively idle pending that resubmit.
- **2026-08-07 03:35 UTC** — **#137 merged (`ee914666`), and #196 refuted my own
  T1 hypothesis decisively.** nezuko's occupancy study returned zero submitted
  bytes and closed three things at once. (1) **T1 is DEAD.** Sliding dispatches
  **32** threadgroups and full dispatches **24**; both are ≤ the M5's **40**
  cores, so *both decode attention dispatches already run in exactly one wave on
  the ranked host*. The "80%/60% efficiency" numbers are idle slots, and **idle
  slots cost zero time** — there was never a tail. Worse, the correct cost law is
  `T = a + W·φ + work`, so a split of S ≥ 2 pays an extra per-wave φ that is not
  divided by S: **every split loses unconditionally** (wave-matched C=40: S=2
  1.144×, S=5 1.704×, S=10 2.185× worse). My §4.12.8(C) relative-makespan table
  and its "S=5 is uniquely optimal" conclusion are **RETRACTED**, along with the
  20%/40% tail, the ~227 µs/step M4 figure and the ~110 µs/step M5 / +1.6%
  prize. The refutation rests on `32 ≤ 40` and `24 ≤ 40` — arithmetic over
  runtime constants — so it transfers to M5 regardless of measurement host.
  (2) **The 32-vs-96 contradiction, open since round ~14, is RESOLVED**: 96
  simdgroups/core is the *residency ceiling* (invariant in TG size and flat in
  threadgroup memory from 16 B to 32768 B), 32 is the *throughput width*.
  **Model performance with 32; use 96 only for co-residency questions.**
  (3) Three new measured constants — once-per-call `a = 1.661 µs`, per-wave
  `φ = 1.469 µs`, marginal `g = 0.7483 µs/KV-iter` — plus the finding that
  co-residency recovers only ~17% of a wave, i.e. **these kernels are
  issue/ALU-bound, not latency-bound.** The successor she left behind is the
  *intra*-kernel merge epilogue: **1.068/1.072/1.170 µs, constant in N, 12.9% of
  a 512-row call**, ceiling +0.685% score. See §4.12.8 (C), (F), (G).
  **Standing lesson for me: a geometry argument expressed as a ratio hid a fixed
  additive cost. Price decode geometry additively or not at all.**

- **2026-08-07 04:35 UTC — round 26 is open on four PRs, and three new
  programme-level rules came out of writing the briefs.** Board: **#204**
  (fern, `maple-2026-08-07b-router-top8-fusion`, head `c5a3172c`) and **#205**
  (nezuko, `maple-2026-08-07c-attention-merge-epilogue`, head `31ffc91f`) are
  freshly assigned at r1 off base `1fe609eb`; **#170** (tanjiro, gather-regime
  discriminator, head `0a90df98`) and **#148** (frieren, prefill ledger, head
  `8f5bdba4`) were both silent under `stale_wip` and each received one
  content-bearing `send_assignment_feedback` nudge rather than a revision
  request. Region fences are declared in both new briefs so #204, #205 and
  #148 cannot collide inside `LagunaRuntimeModel.swift`.
  - **(i) The threadgroup-memory residency confound — now a binding design
    rule for every arm that adds threadgroup memory.** Reverse-engineered
    Apple7/8 numbers put *physical* threadgroup memory at **≈60 KB per shader
    core** against a 32 KB per-threadgroup API limit, so threadgroup memory is
    a genuine co-residency limiter independent of registers. The shipped
    `fp_gather_qmm_rhs_expert_nax` stages **9,232 B** ⇒ ≈6 TG/core on that
    axis; tanjiro's S2 arm adds a second ~9 KB buffer ⇒ ≈3 TG/core. Production
    dispatches 4,096 TGs (gate/up) and 8,192 (down) per layer — ~102/~205 per
    core on 40 cores — a deep many-wave regime in which **halving residency
    roughly doubles wave count**. As written, S2 therefore conflates "load and
    dequant are on the critical path" with "we halved occupancy". **Prescribed
    fix (preferred): make the extra work non-additive in threadgroup memory by
    reusing the existing staging buffer twice per k-iteration** — double the
    device traffic and dequant instructions at a constant 9,232 B footprint.
    Fallback: a fourth control arm that allocates ~9 KB and never reads it, at
    the cost of one receipt. **Every arm must now report, as Step 0,
    threadgroup bytes, compiled `maxTotalThreadsPerThreadgroup`, and implied
    TGs/core.** Caveat carried forward: #196's "residency flat in tgmem
    16 B→32768 B" was measured at **1024 threads/TG**, where thread count was
    the binding limiter; tanjiro's kernel is 128 threads / 4 simdgroups, a
    different regime, so #196 does not exempt it.
  - **(ii) Ledger measurement doctrine — read dose-response ledgers off raw
    candidate metrics, never off a speedup.** The paired *baseline* decode
    draw drifts monotonically **+0.091% over ~3 h** (~0.03%/h), and the paired
    *baseline* prefill draw swings far harder: `prefill_speedup` fell 2.0015 →
    1.9628 across three sessions, **−1.93% entirely baseline-side**. The
    *candidate* `prefill_seconds_per_token` has a run-to-run sd of **0.260%**,
    so the denominator is 7–8× noisier than the numerator. **Rule: every
    ledger row comes from `officialMetrics` raw `prefill_seconds_per_token` /
    `decode_seconds_per_token`, candidate arm only; paired baselines are
    recorded solely as a host-health check.** #148's design survives this
    unchanged (26 copies × 1.109 ms = ~28.8 ms on ~97.9 ms S = **+29%, about
    110× the 0.260% noise**). **Corollary now binding on every decode ledger:
    candidate decode cv ≈ 0.235% ⇒ the ranked channel resolves ~10 µs/step, so
    any decode ledger entry below ~10 µs/step must be reported as "below
    resolution", not as a number.**
  - **(iii) The receipt price is ~44 minutes, not ~35.** #137 r3 measured
    **43 min 55 s** dispatch → terminal (01:57:14Z → 02:41:08Z; 19.6 min
    queued + 20.8 min validating), receipt `08ddee45`. Four receipts is ~3 h of
    pure queue time, which is why #170 is now sequenced **M2 → S2 → B2 with
    explicit permission to stop at three**. Offsetting this: the queue is
    currently almost free, because #204 and #205 are M4-local with zero
    receipts and only #148 and #170 can dispatch.
  - **(iv) A fresh frontier slate (H1–H9) now exists in §11.** It was produced
    by a context-free frontier agent from the budget framing alone, and its
    organising claim is that the **~1.0 ms of decode time not claimed by any
    in-flight experiment is per-dispatch fixed cost**, because 1.0 ms over 406
    dispatches ≈ 2.5 µs ≈ the measured attention per-call fixed cost (1.661 µs)
    plus one wave (1.469 µs). **H1 — one Metal System Trace of 3–5 consecutive
    decode steps, split into inter-dispatch gaps, step-boundary bubble, and
    exposed small-kernel duration — is the decision node**: it prices H2, H3,
    H4, H7 and H9 exactly and costs about a day. Read §11 with the four
    advisor caveats recorded there before assigning any of it.

- **2026-08-07 05:30 UTC — #170 merged as `747d130b`; the prefill constraint is
  now NAMED; four carried constants are corrected; round 26 is fully staffed.**
  Board after this entry: **#215** (tanjiro, `maple-2026-08-07d-nax-kloop-pipeline`,
  head `e49d7a99`, base `747d130b`) is newly assigned at r1; **#204** (fern),
  **#205** (nezuko) and **#148** (frieren) remain `status:wip` at r1 and each
  received a byte-budget feedback item. All four students are busy; the
  post-merge cleanup PR is unassigned and is **top priority for the next idle
  student**.
  - **(a) #170's result — the prefill gather-GEMM constraint, stated.** Four M5
    receipts, all `passed_correctness true`, `max_abs_diff 0`, both floors true,
    each rejected on ranking only. Control `S = 97.895 ms`; marginal prefill
    wall `W = 43.2619 ms`. Arms, as ΔS against control: **M2** (double MMA+ALU)
    `+2.046 ms` (4.7% of W, 4.5σ, receipt `d786ad5c`); **S2** (stage +5.89 GB)
    `+15.961 ms` (36.9%, 35σ, `a3e38005`); **B2** (two extra barriers)
    `+0.841 ms` (1.9%, 1.9σ, `f2160f8f`); **S3** (stage-issue with zero extra
    bytes) `+7.853 ms` (18.2%, 17.5σ, `ec2b0a57`). `ΔS3 / ΔS2 = 49.2%` ⇒ the
    staging cost splits **≈49% load-issue/occupancy, ≈51% DRAM bytes**, with 49%
    an upper bound on the issue share. The pure-issue term is **6.887 ms =
    15.9% of W** and no bandwidth improvement can touch it; the implied
    *marginal* bandwidth of the byte term is **726 GB/s**, above the 614 GB/s
    peak, so the byte term is also not a clean roofline story. **Consequence:
    no single-branch plan works. H1 (MMA/compute-limited) and H0 (jointly
    saturated at the ridge) are both ELIMINATED; barriers are only 1.9%; the
    31% tile-quantization padding is not worth chasing.** The mandated Step 0
    passed for control and every arm on both ranked shapes — tgMem 9,232 B,
    `maxTotalThreadsPerThreadgroup` 1024, `threadExecutionWidth` 32,
    byte-identical across all ten rows
    (`research/artifacts/tanjiro-pr170-pipeline-stats.txt`) — so rule (i) above
    is now a *validated* instrument, not just a caution, and the S2 residency
    confound provably does not apply because tanjiro shipped the preferred
    fix: `loader_w2` reads the **same** `Ws`. `σ(S) = 0.318 ms` from n=16 feed
    receipts ⇒ **3σ = 1.35 ms** is the standing prefill kill threshold.
  - **(b) CORRECTION — the receipt price is ~20–22 minutes with slot
    discipline, not ~44. This supersedes (iii) in the 04:35 bullet.** #170 §9.1
    measured S3 end to end at **20.3 min**, with `benchmark_wall_seconds = 53`
    on all four receipts ⇒ ~98% of elapsed time is queue, and queue time
    collapses when a dispatcher holds its slot rather than re-entering. The
    ~44 min figure was a no-slot-discipline draw. Four receipts is therefore
    ~1.5 h, not ~3 h. **The retired constants are now "~35 min" AND "~44 min".**
  - **(c) CORRECTION — prefill score elasticity is `0.2554 % per ms` removed
    from S. The carried pair "−0.3669 / +0.362 %/ms" is RETIRED.** From #170
    §8.6, control `S = 97.895 ms` against baseline `195.93 ms`: −8.26 ms ⇒
    score 2.646512 (**+2.23%**); −10.26 ms ⇒ 2.661484 (**+2.81%**); −16.26 ms ⇒
    2.709095 (+4.65%). Every prefill proposal must be priced with 0.2554 %/ms
    from here on. The decode elasticity `0.01464 %/µs` still **needs
    reconciliation** (0.75/4143.57 µs = 0.0181 %/µs; 0.75/4908.4 µs =
    0.01528 %/µs) — treat it as ±20% until someone closes it.
  - **(d) CORRECTION — the `_nax` twin IS editable, and I was wrong.** I
    previously recorded that `mlx-generated/fp_quantized_nax.cpp` does not
    exist or is not submittable. **It exists** at
    `Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized_nax.cpp`
    (74,693 B) and **is listed in `benchmark.json` `editablePaths` (line 94)**;
    `python3 research/nax_twin_check.py` PASSES at `747d130b`. Other editable
    generated `*nax*.cpp` twins sit at lines 91, 94, 96, 98, 100, 102, 104
    (note `steel_gemm_segmented_nax.cpp` exists on disk but is **not** listed).
    **Binding consequence for every `_nax` assignment: a header edit must be
    mirrored into the twin, so byte growth roughly DOUBLES.** This is why the
    round-26 per-PR growth cap was tightened.
  - **(e) The byte budget is now the binding constraint on round 26.** At base
    `747d130b`: `current = 2,949,686 / 3,000,000 B`, **headroom 50,314 B**,
    growth `0 / 262,144`, 142 files. With four PRs in flight I tightened every
    cap to **12,000 B net growth per PR** (#204 `pr204-r1-tighten-byte-budget-to-12kb-2026-08-07`,
    #205 `pr205-r1-tighten-byte-budget-to-12kb-2026-08-07`, #148
    `pr148-r1-injection-byte-budget-2026-08-07`, and #215 in its brief).
    Worst case 4 × 12,000 = 48,000 B < 50,314 B — **zero slack**. #148 was
    additionally told to port only the `PREFILL_ROUTED` knob (dropping the
    other three) and to default it OFF via
    `lagunaInjectEnvInt("DARKBLOOM_INJECT_PREFILL_ROUTED", 0)`, following
    #170's `kNaxGatherProbeDefault` discipline. #205 was told to edit an
    attention kernel in place behind a switch rather than duplicate a kernel
    string (`LagunaRuntimeModel.swift` is already ≈467,167 B of the 524,288
    per-file cap). **The cleanup PR is now a byte-recovery instrument as much
    as a hygiene one**: dead BK128 machinery (5,164 B), tanjiro's nine
    near-duplicate `.metal` variants, fern's twice-measured-negative
    `DARKBLOOM_LMHEAD_ROWMAJOR_REFINE` dual-arm flag and its row-major kernel
    in `LagunaLmHeadPrune.swift`, #170's now-inert `kNaxGatherProbeDefault`
    probe machinery, #148's injection machinery once its ledger entry is
    answered, and optionally ~32 KB of Laguna-dead transform sidecar coders.
    **⚠️ Do NOT delete the dead `foldGateIntoBank` / `lagunaFusedNormAffineQKV`
    INT8 paths (`LagunaRuntimeModel.swift:5510-5533`, `:5733-5738`)** — they are
    the only shipped precedent for the accepted attention quantization
    envelope.
  - **(f) H1 is substantially de-risked DOWNWARD; its largest sub-hypothesis is
    dead.** A step-boundary audit of the scored decode loop found that
    **exactly 4 bytes cross GPU→host per decode step**. Sampling
    (`Sources/MLXFastHarness/LagunaCorrectness.swift:102-109`) does
    `logits.reshaped([-1,vocab])` → `rows[-1]` → `Int(last.argMax().item(Int32.self))`;
    `argMax` runs on the **GPU** and the ~100,352-wide bf16 row is never
    copied, so **the "big logits copy per step" sub-hypothesis is DEAD**.
    `item(_:)` is the single blocking device sync per step. No host sync fires
    per step anywhere in `Sources/MLXFastModel/`; KV advance is pure host `Int`
    arithmetic; masks return `nil` at `t == 1`; RoPE tables are zero-copy
    views; kernels are never rebuilt (all `MLXFast.metalKernel(` sites are
    `private let` globals or dict-cached); all 82 environment reads feed
    one-time file-scope globals. **The one concrete hoistable target left** is
    `LagunaRuntimeModel.swift:2254` — a fresh 12-byte uniform `MLXArray`
    minted per full-attention layer, **10×/step, with no atlas**, where the
    sliding path already uses `lagunaRingIdxAtlas` (`:1753-1754`, store
    `:1776-1785`, ablation `DARKBLOOM_PARAMS_ATLAS`). It is cheap and
    precedented but predicted **small**, because **PR #158 already measured the
    step-boundary gap at ~265 ± 20 µs (≈3.01%) and showed it scales WITH busy
    time** (slope +0.059 ± 0.019, rejecting the absolute-cost model at 3.1σ;
    per-dispatch coefficient NULL at −0.12 ± 0.22 µs). **H1's headline
    "+1.8–4.8%" must be revised down.** Feasibility: per-kernel *exposed*
    durations are **not** obtainable from either existing GPUPROF patch (both
    are per-command-buffer, and spans average ~9 dispatches, so `sum == union`
    is vacuous); getting them needs `sampleBufferAttachments` counter sampling
    or `kernelStartTime`/`kernelEndTime`, neither of which appears anywhere in
    the tree. Gap and bubble measurement *is* feasible with one new
    research-only patch to the non-editable `backend/metal/device.cpp`.
  - **(g) The §8.1 staged-byte census, done here — and it puts §4.10's
    "roofline-ridge identity" in question.** From the stored NVFP4 shapes, one
    expert stages `gate_proj` 589,824 B + `up_proj` 589,824 B + `down_proj`
    589,824 B = **1,769,472 B**. Then `1,769,472 × 256 × 39 = 17.66641 GB`
    reproduces the historical `GBYTE` constant **exactly**, proving that
    constant assumed *every one of 256 slots staged once, in 39 layers*. The
    route histogram (`research/artifacts/route-histogram-prefill512.csv`,
    9,728 rows = 38 × 256, sum 155,648, mean 16.00) gives
    `chunks_bm64 = 8,379` and `nonzero_experts = 7,757`. Chunk-accurate over 38
    layers that is **14.8264 GB ⇒ 342.7 GB/s ⇒ 55.8% of 614 GB/s**, against
    the analytic all-slots 17.2134 GB ⇒ 397.9 GB/s ⇒ 64.8%; the ratio
    `0.8613` says the analytic figure **overstates by ~13.9%**. Subtracting
    #170's 6.887 ms pure-issue term gives an implied byte-limited rate of
    **407.6 GB/s**. **Three consequences.** (1) The carried "408.4 GB/s = 67%
    of peak" headline likely **overstates** achievement; the true achieved rate
    is nearer 343 GB/s (55.8%), which means the floor is lower and the headroom
    is **larger** than we have been assuming. Sensitivity, issue term held
    fixed: reaching 450 GB/s = −3.43 ms = **+0.88%**; 500 GB/s = −6.72 ms =
    **+1.72%**; 614 GB/s = −12.23 ms = **+3.12%**. (2) The "dead bytes" branch
    is largely **refuted by construction** — zero-row experts stage nothing, so
    the ~20.3% of threadgroups that launch, binary-search and exit are an
    **issue/occupancy** cost, not a byte cost, which is exactly the term #170
    priced at 6.887 ms. (3) ⭐ **§4.10's roofline-ridge identity (67% of bytes
    AND 67% of FLOPs = one efficiency scalar θ) may be an artifact of using
    the analytic byte count on one axis only.** Both axes must be redone
    chunk-accurately before that identity is quoted again. Two reconciliations
    must close before anyone divides by `dS_1` again: (a) 38 vs 39 MoE layers,
    and (b) what layer set `dS_1 = 43.2619 ms` actually covers, since PR-91's
    injection binds layer `i` to bank `i+20` and "scaled to 40 layers" implies
    partial coverage. **Part A of #215 is exactly this census, pre-registered
    against the table above.** **H6 stays demoted until it lands.**
  - **(h) #215's Part B — the one surviving mechanism from #170.** The k-loop
    already hoists the **A** operand into registers (`NAXTile Atile[BK/SK]`),
    so §8.3's "stop staging the A operand frees ~8 KB" is **VOID**: all 9,232 B
    of threadgroup memory is `Ws`, the **B** operand. What #170 reopened is
    **register-staged prefetch of `Ws`** — issue iteration `k+1`'s weight load
    into registers before consuming iteration `k`'s staged tile, so the
    ~6.9 ms pure-issue term overlaps MMA instead of serialising with it. This
    is the only branch that attacks the 49% side, and it is byte-neutral, so it
    is not blocked by (g). Double-buffering `Ws` in threadgroup memory remains
    presumptively self-defeating (6 → 3 TG/core). #215 is capped at 3 receipts
    with a 3σ = 1.35 ms kill and a 12,000 B growth cap covering **both** the
    header and its twin.

- **2026-08-07 05:55 UTC — two programme-level corrections landed together.
  Read both before pricing any further experiment.**

  - **(A) ⭐⭐⭐ THE SCORE ELASTICITIES WERE WRONG. The 512-token seed prefill
    is INSIDE the scored decode window.** Source-verified in the trusted
    harness: `Sources/MLXFastTrustedHarness/LagunaRuntimeBenchmark.swift`,
    `measureWorkerDecode(...)` at `:946` — the clock starts at `:966`,
    `worker.beginDecode(seedTokens:)` runs at `:968` *inside* that window (the
    progress line literally reads `includes_seed_prefill=true`), and the
    reported figure is `measuredSeconds / decodeSteps` at `:1010`/`:1013`.
    Therefore

    ```
    decode_seconds_per_token = 4 × prefill_seconds_per_token + T
    D = (S + 128·T) / 128        (S = 512-token prefill wall, T = per-step cost)
    ```

    Numerically exact on the promoted receipt `97a5090`:
    `4 × 0.00019120068359375 + 0.004143569335937499 = 0.0049083720703125` ✓,
    and `exp(0.75·ln 2.820661 + 0.25·ln 2.001471) = 2.588828` reproduces
    `officialScore` to the last digit. **Corrected elasticities** at
    `D_c = 4908.372 µs`, `T_c = 4143.569 µs`, `S = 97.895 ms`:

    | axis | corrected price | composition | discrete check |
    |---|---|---|---|
    | **prefill** | **0.374750 % per ms removed from S** | 0.25537 prefill-axis + 0.11938 amortized-seed decode-axis | −8.26 ms ⇒ 2.672902 = **+3.2476%** |
    | **decode** | **0.015280 % per µs removed from per-step T** | pure decode axis, divided by `D` not `T` | −100 µs ⇒ 2.629157 = **+1.5578%** |

    **RETIRED:** `0.2554 %/ms` (the "Model A" prefill price this advisor
    canonized in the 05:30 bullet sub-item (c) — it understates prefill by
    ~46% because it ignores the amortized seed); `0.01464 %/µs` (4.4% low);
    `0.0181 %/µs` (18.5% high — §11 divided by `T` instead of `D`). The
    previously-"retired" `0.362 %/ms` was approximately right. **Net effect:
    prefill is reweighted ≈1.74× in favour relative to decode.** Consequences:
    tanjiro's #170 §8.6 table used Model A, so his `−8.26 ms ⇒ +2.23%` is
    really **+3.25%**; the #170/#215 bandwidth arms at 450/500/614 GB/s are
    worth **+1.29% / +2.52% / +4.58%**; §11 H8 (~6 ms) is **+2.25%**; #205's
    46.8 µs/step ceiling is **+0.715%**; H7 (60–95 µs) is **+0.92–1.45%**; H9
    (30–80 µs) is **+0.46–1.22%**.

  - **(B) ⭐⭐⭐ DELETING A DECODE DISPATCH IS WORTH ≈ ZERO UNLESS IT IS A
    CHAIN-LINK. PR #204 (maple-fern, merged as `0fd78d5c`) — the router top-8
    fusion family is closed NEGATIVE, with a zero-byte submitted diff.** Three
    arms in ONE binary via `DARKBLOOM_DECODE_ROUTER_EMIT_SINK ∈ {1,0,2}`:
    A = emit kernel used + standalone top-8 deleted, B = base, C = emit kernel
    runs but its output is ignored + standalone kept. 18 runs, three
    palindromic **ABCCBA** blocks, 1200 timed steps each, `research/decode_probe.py`
    with `CLOCK_UPTIME_RAW`, run-median as the unit of replication.

    | contrast | paired mean | sd | sem | t (df=5) | verdict |
    |---|---|---|---|---|---|
    | `ΔC = C − B` — the emit kernel's own cost | **+37.3 µs** | 12.1 | 4.9 | 7.6 | p ≈ 0.0006 |
    | **`ΔD = A − C` — 39 dispatches removed** | **−0.9 µs** | 29.7 | 12.1 | −0.07 | **p ≈ 0.94, NULL** |
    | `A − B` end-to-end | +36.4 µs | 24.2 | 9.9 | 3.7 | p ≈ 0.014 |

    The identity closes exactly (`+37.3 − 0.9 = +36.4`); the end-to-end figure
    replicates across sessions (an independent 8-run ABBA gave +36.3 µs); 0
    token divergences in all 26 runs. The pre-registered prediction was
    **−110 µs, 90% CI [−55, −175]**, so the kill rule fired. **Arm C is
    validated by fault injection** — one bf16 ULP added to the emit kernel's
    `router_scores` only, all three arms digested in ONE binary/driver run:
    `faultA` differs from `faultB` at 66/66 steps starting at step 0, while
    `faultC` is byte-identical to `faultB` at 0/66. So C genuinely runs the
    emit kernel and genuinely discards it, and `ΔD ≈ 0` is real.

    **What this establishes.** (1) Removing 39 decode dispatches/step is worth
    `−0.9 ± 12.1 µs`, 95% CI ≈ [−32, +30]; the census predicted −105…−185 µs.
    The point estimate is **two orders of magnitude** below the 185.7 µs/step
    headline. (2) `T = a + W·φ` is a **throughput-slot** cost — an *upper
    bound* on marginal cost, attained only when the encode front-end
    saturates, collapsing to ~0 when the streams have slack. (3) ⭐ **The
    chain-link / side-branch taxonomy.** A *chain-link* dispatch is the sole
    occupant of its barrier-bounded interval, so deleting it saves ≈ its full
    duration. A *side-branch* is issued inside a much larger sibling's
    concurrency interval, so deleting it saves ≈ 0. The router top-8 is a
    side-branch: `lagunaRoutedSharedDownResidual`
    (`Sources/MLXFastModel/LagunaRuntimeModel.swift:10100-10130`) consumes
    **both** `routerWeights` (from the standalone top-8) *and* `routedActivated`
    (from the big routed gate/up QMV), and both producers are siblings
    depending on `router_keys` — a classic diamond, and **the short arm of a
    diamond is free**. (4) **The census contains its own falsification**:
    `rmsbfloat16` is listed at 1.82 µs/call, *below* the fitted single-TG floor
    `a + φ = 3.13 µs`. No dispatch can sit below the floor if per-kernel costs
    are additive.

    ⭐ **STATIC SIDE-BRANCH PREDICATE (advisor formulation, free to evaluate,
    no GPU trace required):** *dispatch X is a side-branch iff every consumer
    of X also transitively depends on a sibling Y whose duration is ≫ X, where
    Y is issued no later than X.* This is readable straight off the Swift
    dataflow, so it yields a **pre-registrable per-target prediction** and
    converts any injection sweep from a survey into a real hypothesis test.

  - **(C) Queue re-pricing forced by (B).** **§11.0's organising claim ("the
    decode residual is per-dispatch fixed cost; the unpulled lever is
    fewer/fatter dispatches") is REFUTED and is rewritten below.** **H2**
    (shared expert as a 257th expert) is badly demoted: its kernel
    `shared_nvfp4_swiglu_qmv_rows1` is one of #174's three kernels measured at
    exposure `E = 0.10`, so the honest decode-side value is **≈+0.18–0.31%**,
    not +1.83–3.06%. **H4** (systematic absorption of the remaining
    elementwise dispatches) is seriously damaged and must be re-scoped to
    chain-link kernels only. **#205 survives** (intra-kernel work reduction
    inside `sliding_fused_attn_ring_v1`, measured at `E ≥ 0.90` — a
    chain-link). **H7 survives** (intra-kernel, attention). **H9 survives**
    (command-buffer granularity, orthogonal to dispatch count). **H1 survives
    and rises in importance**: if dispatches are free, the residual ~1.0–1.2 ms
    must be genuine critical-path kernel time or genuine gaps. **#148 is
    unaffected and convergent** — fern's §7 marginal-cost probe design is
    independently the same instrument as `research/tanjiro-pr34/instrument.patch`,
    which already exists and is M5-validated for `PREFILL_ROUTED`
    (`dS_1 = 43.2619 ms`). **#174's pooled `E_rest = 1.013` was too coarse** —
    it averaged over a pool that contained a kernel with `E ≈ 0`.

  - **(D) The reusable instrument that replaces census pricing (#204 §7).**
    Add `K−1` redundant copies of a target dispatch per layer under
    `DUP = K ∈ {1,2,3,5}`, each writing its **own scratch output**, and make
    every copy an **additional eval root** so MLX cannot DCE it. *Defeat DCE by
    reachability, never by fake arithmetic.* List the duplicate roots BEFORE
    the logits so the graph DFS encodes each copy adjacent to its own layer,
    and verify that `39·(K−1)` extra dispatches actually encode. Readout: slope
    ≈0–10 µs/step ⇒ phantom cost; ≈ the census row ⇒ real. A second variant
    chains the duplicates to force hazard serialization; the **ratio of the
    overlapped slope to the serialized slope is a reusable overlap discount**.
    This is now the mandatory gate before any decode fusion kernel is authored.

  - **(E) Doctrine changes.** Stop quoting a census µs/step figure as a saving;
    it is an upper bound with real mass at zero and a real chance of net loss.
    The realized-saving prior for a "delete a small decode kernel worth
    70–200 µs/step" target is now **10–20% of census**. Triage the whole
    remaining decode queue with ONE marginal-cost sweep rather than one fusion
    per hypothesis. Keep #204's correctness methodology verbatim: bitwise logit
    digest plus a fault-injection sensitivity control proven to fire, with all
    arms digested inside a single binary and driver run.

  - **(F) Byte budget.** #204 merged with a **zero-byte** submitted diff
    (`git diff --stat 747d130b..e92d09eb -- Sources/ Vendor/` is empty), so
    the three in-flight assignments (#215, #205, #148) are each capped at
    12,000 B against 50,314 B of headroom — worst case 36,000 B, leaving
    14,314 B of slack. The post-merge cleanup PR is therefore **less urgent**
    than the 05:30 bullet recorded, though the dead-surface list stands.

- **2026-08-07 06:30 UTC — the cold-seed-prefill thread is RESOLVED as a
  negative, and in resolving it the score identity became exact by
  construction. Three corrected-elasticity feedback items dispatched.**

  - **(A) Three feedback comments sent, all accepted.** #215 (tanjiro)
    `pr215-r1-corrected-prefill-elasticity-2026-08-07` → comment `5213028704`:
    re-priced his three bandwidth arms at 0.374750 %/ms to **+1.29% / +2.52% /
    +4.58%**, §8.6 to +3.25%; Part A remains a prerequisite; warned that
    #204's side-branch null does not touch his target. #148 (frieren)
    `pr148-r1-corrected-prefill-elasticity-2026-08-07` → comment `5213036368`:
    corrected elasticity plus a recomputed reference table (`dS_1` +16.21%,
    `dS_2` +8.32%, unattributed +12.14%, 40-layer-scaled +11.72%, one injected
    copy +0.4156%), and **two mandated hardening details** — every duplicate
    writes its own scratch output and becomes an additional eval root (defeat
    DCE by *reachability*, never by perturbing arithmetic), and the duplicate
    roots must be listed BEFORE the logits with `n_calls·(K−1)` extra
    dispatches verified to encode at each dose. #205 (nezuko)
    `pr205-r1-corrected-decode-elasticity-and-sidebranch-2026-08-07` → comment
    `5213048534`: decode price corrected to 0.015280 %/µs (ceiling **+0.715%**)
    and an explicit argument for why her target survives #204 — it is not a
    dispatch deletion, #174 §3.6 measured `E ≥ 0.90` for
    `sliding_fused_attn_ring_v1`, and #196 §7.1 measured the epilogue directly
    at 1.068/1.072/1.170 µs, constant in N. Her **Step 0 is now doubly
    load-bearing**: if she cannot decompose the 1.07 µs across the 3 barriers
    and 4 threadgroup passes, she reports and stops.

  - **(B) ⛔⛔⛔ THE "COLD SEED PREFILL" IS NOT A LEVER. Source-verified;
    add it to §8 closed families.** `Sources/MLXFastCore/Constants.swift:129`
    sets `benchmarkPrefillWarmupRuns = 0` and `:130` sets
    `benchmarkPrefillTimedRuns = 1`. **RETRACT my earlier claim that the
    scored prefill number is a warm mean — it is ONE single cold run.** The
    allocator reset is therefore *symmetric*:
    `resetRuntimeWorkerAllocatorForPhaseStart()` runs at the head of
    `case "prefill":` (`Sources/MLXFastHarness/LagunaRuntimeWorker.swift:360`)
    exactly as it does at the head of `case "decode_begin":` (`:382`). Both
    the scored prefill and the in-window seed forward are the *same operation*
    modulo token values: same reset, same fresh cache, same
    `model(inputIDs, cache:)` (`:201-209`), in a process whose constructor has
    already run a full 512-token prefill warmup
    (`LagunaRuntimeWeights.swift:404-420` → `warmLibraryModel` `:466-520`,
    itself preceded by `prepareFusedRuntimeWeights()` at `:620-639` "so the
    fused kernels warm with their production shapes").
    `materializeLagunaCacheState(cache)` is literally `eval(cache)`
    (`LagunaRuntimeWorker.swift:236-238`) and is free, because `greedyToken`'s
    `item()` already materialized the logits. There is no asymmetry to
    harvest.

  - **(C) ⭐⭐⭐ CONSEQUENCE: `D = 4P + T` IS EXACT BY CONSTRUCTION.** Because
    the seed forward and the scored prefill run are the same cold operation,
    `d(seed)/d(prefill) = 1` identically, hence `d(cand_D)/d(cand_P) = 4`.
    The circularity caveat I attached to the 05:55 identity check is
    **DISCHARGED**, and **0.374750 %/ms is now airtight** rather than
    numerically coincidental. Independent empirical confirmation from the
    shipped wired-limit dose table (doc comment on
    `wireResidentWeightsIfEnabled`, `LagunaRuntimeWeights.swift`): the 1.0×
    wire measured **−28.3% prefill and −4.2% decode composite**, annotated
    "seed-prefill share; steady step null". The identity predicts
    `4 × (191.2/4908.4) × 28.3% = 4.41%`. Measured 4.2%. ✓ That table also
    corrects an earlier note here: the **shipped** dose is
    `wiredZHDefaultFraction = 1.0` with `wiredZHDefaultSlackMB = 64`, i.e. the
    **full ~31.4 GiB wire**, not the 42 MiB the stale comment above it
    describes.

  - **(D) ⛔ OUT OF BOUNDS, not merely closed.** Holding warmup scratch
    buffers *live* across `Memory.clearCache()` and releasing them inside the
    scored window so the emptied buffer cache refills is **protocol bypass**.
    The trusted comment at `LagunaRuntimeWorker.swift:169-171` states the
    intent in terms: *"The substantive defense is `Memory.clearCache()`, which
    removes every free buffer accumulated during unscored initialization so it
    cannot subsidize the first charged forward."* Do not assign it, and refuse
    it if a student proposes it.

  - **(E) ⭐ ONE LEGITIMATE SURVIVOR FRAMING.** Because the scored prefill is
    a *single cold run*, the **coverage** of the constructor warmup is priced
    at the full 0.374750 %/ms: anything the scored forward needs that
    `warmLibraryModel` does not build is paid inside the window, and
    `warmLibraryModel` is editable. I checked the obvious hole and it is
    mostly closed — the warmup feeds **512 identical BOS tokens**, so routing
    is degenerate (all 512 rows hit the same 8 experts, ~64 chunks/layer
    against the real 220.5), but the dispatch grid is `(N/bn, egroups=256)`
    regardless, the sorted-row count is M=4096 either way, and attention is
    still 512×512 causal, so **shape and pipeline coverage look complete**.
    The one thing I cannot settle offline: whether any M5-only `_nax` variant
    (`steel_gemm_fused_nax`, `steel_attention_nax`, the NAX split-K branch,
    `fp_qmm_t_nax_static`) is reachable only under a *non-degenerate* route
    and therefore misses the warmup entirely. That is not observable on a
    gen-16 M4 host; it has to be read out of the selection code in
    `quantized.cpp` / `matmul.cpp`. Worth one bounded assignment if a slot
    frees up. Prior art in the same file already shows the shape of a win: the
    greedy-argmax warm (`DARKBLOOM_WARM_GREEDY_ARGMAX`) exists precisely
    because a timestamped PSO-miss log caught `argmax_bfloat16` compiling
    ~0.23 s *inside* the scored prefill.

- **2026-08-07 08:25 UTC — round 28 closes with TWO merges, THREE new
  standing rules, and the first honest per-family cost model of the decode
  step.** #218 (fern, merged `7127f5ea`) and #215 (tanjiro, merged
  `fe5d843f`) both landed with a **zero-byte submitted diff** — verified
  independently by `git diff <base>..<head> -- Sources/ Vendor/` returning
  empty for each. Budget unchanged at `current=2949686/3000000
  headroom=50314 growth=0/262144 files=142`. Round 29 opens with #241
  (fern, decode boundary-gap census) and #244 (tanjiro, H16 `_nax`
  scale-load amortization).

  **(A) ⭐⭐⭐ #218 gives us a marginal-cost ledger, and absorption turns out
  to be PER-FAMILY, not a global step budget.** Fern injected bit-identical
  duplicate work at eight wired decode sites and regressed wall time on
  copy-count. The result is the first thing this campaign has that deserves
  the name *cost model*:

  | target | calls/step | µs/step | % of step | E | absorbed slack |
  |---|---:|---:|---:|---:|---|
  | `T0b_qkv` | 40 | 1276 | 15.6% | 0.741 | −0.17 copy-sets |
  | `T2c_routed_qmv` | 39 | 1184 | 14.4% | 0.754 | −0.26 |
  | `T2d_down_residual` | 39 | 555 | 6.8% | 0.617 | 0.00 |
  | `T1c_lmhead` | 1 | 474 | 5.8% | 0.93–1.11 | 0.00 |
  | `T1a_residual_rms_router` | 39 | 106 | 1.3% | 0.349 / 0.129 | 15.16 |
  | `T2a_shared_qmv` | 39 | 74 | 0.9% | 0.311 | — |
  | `T0a_router_top8` | 39 | 0 | 0.0% | −0.045 | 15.33 (≈2.85 ms) |

  Priced rows sum to **3669 µs/step = 44.7% of the 8.20 ms M4 step**. The
  spine (QKV, routed QMV, down+residual, lm-head) pays for every added
  microsecond; the shadows (`T0a`, `T1a`) absorb **~15.2–15.3 copy-sets
  ≈ 2.85 ms of free idle-lane capacity per step** before wall time moves at
  all. This supersedes the §5.3 "static shadow ratio" naming: the true
  shadow ratio is the **absorbed-slack-in-µs** column, not census/roofline.

  Three corollaries that change how we price everything downstream:

  1. **A census row is an upper bound, never a price.** `rmsbfloat16`'s
     census of 1.82 µs/call sits *below* the single-TG floor `a + φ =
     3.13 µs`. Census ranks large streaming families correctly and fails
     completely on small kernels.
  2. **⭐ Every streaming-family E is a LOWER bound on the true cold
     deletion saving.** All three weight-streaming spine families land at
     **E = 0.62–0.75**, while the cache-resident lm-head lands at
     **0.93–1.11**. Duplicates are cache-warm, so the measured marginal cost
     understates the cold cost by roughly **26%**.
  3. **The 466 GB/s puzzle is resolved in favour of cache reuse.**
     Per-expert routed weights are **1,769,472 B** (gate `[512,256]` uint32
     + `[512,128]` uint8 scales; down `[2048,64]` + `[2048,32]`), read
     directly from the safetensors headers — this **matches the §8.1 census
     exactly**. 8×39 = 552 MB/step, but the per-layer working set is only
     **14.2 MB**, which is SLC-resident in the M4 Pro's 24 MiB. **True
     routed cost ≈2.5 ms = 27–31% of the M4 step**, and routed QMV has
     ~70% compute headroom, so only bytes matter there.

  QKV is independently measured at **100% of the M4 host roofline**
  (260.6 of 260.6 GB/s). Fern's §7 scorecard: 5 of 7 computable predictions
  landed inside pre-registered bands, with T0a/T1a/T1c/T2a genuine blind
  tests and T0b/T2c/T2d post-hoc census attributions. His own caveat stands
  and I endorse it: spine **ordering** should transfer to M5 because it is
  set by bytes/token, a checkpoint property; **magnitudes** and especially
  **shadow slack** should not, because M4 Pro gen 16 is bandwidth-bound
  where the ranked M5 gen 17 is ~89% instruction-bound.

  **(B) ⭐⭐⭐ NEW STANDING RULE — REACHABILITY BEFORE NULL.** #218's
  pre-registered wiring attached `T0b_qkv` to `lagunaNormAffineQKV` and
  produced two beautifully tight nulls (`−9.36 ± 6.54 µs`, `+0.50 ±
  1.09 µs` at K≤33) from **zero injected copies**. Root cause at
  `LagunaRuntimeModel.swift:5852-5858`: the bank is `mode == .nvfp4,
  bits == 4, groupSize == 16`; the guard wants `.affine && bits == 8`;
  `lagunaNativeAffineNVFP4From` defaults to `0`, so
  `_nativeAffineQKVGateRows` stays `0 != nHeads` and the branch is dead.
  Re-wired onto the live `lagunaDecodeNVFP4QKVR1` at `:5883-5887` it
  immediately returned `1276.01 ± 11.48 µs/copy-set` (t = 111).

  > **Rule: no null result is interpretable until the arm ships a
  > call-count census proving the instrumented site actually executes on
  > the scored path, with the observed count reported. A knob on an unused
  > fallback is not a measurement.**

  Reference implementation: the `DUPCOUNT:` line in
  `research/fern_dup_probe.py`; reachability census run `545b0c42-442e-4ee1-bbbc-9815e613ebe7`,
  exit 0, 44 s, all eight wired sites confirmed live. This also
  **measurement-confirms** that `lagunaNormAffineQKV` and the
  `foldGateIntoBank` INT8 precedent (`:5510-5533`, `:5733-5738`) are dead
  code. Keep them — they are documented precedent, and deleting them buys
  nothing — but never benchmark through them again.

  **(C) ⭐⭐⭐ NEW STANDING RULE — MATCHED CONTROLS.** Tanjiro's `0bc3eb4`
  is a **byte-exact base control receipt purchased in the same session as
  his arm**, and it is the single highest-value receipt of this campaign
  because it immediately falsified two of my own published negatives:

  - arm 1 `26b8e82` (`S = 98.2092 ms`) against control `0bc3eb4`
    (`S = 97.5250 ms`) is a **NULL at +0.0123%**, not the "−1.016%" I
    posted in #215 comment `5213645316` — **withdrawn**;
  - nezuko's float4 transpose-staging arm `c03dc11` is **−0.513%
    (≈0.7σ)**, not the "−1.53%" I posted — **withdrawn**.

  > **Rule: cross-session `officialScore` comparison at the 1% level is
  > invalid. Every ranked arm must be paired with a same-session byte-exact
  > control receipt. Budget two receipts per arm.**

  The physical justification was already in §4.11.6 and the ledger
  doctrine — M5 paired-baseline decode drifts monotonically **+0.091% over
  ~3 h**, candidate prefill sd is **0.260%**, decode cv ≈ **0.235%** — but
  we were not honouring it. We are now. Consequential amendment: my note
  that the campaign had suffered "three consecutive competent negatives" is
  **wrong and withdrawn**. The true record is **one null (#215 arm 1), one
  arm never cleanly measured, and one null-to-small-negative (−0.513%)**.
  The programme was in a *measurement* streak, not a losing streak, and
  #215 and #218 ended it.

  Anchor-debt consequence: `0bc3eb4` **is** a byte-exact control on the
  merged base, so §4.11.5's anchor obligation is substantially discharged
  even though two merges (#218, #215) have just landed. The prepared anchor
  note is retained but the slot is better spent on a student arm.

  **(D) ⭐⭐⭐ #215 closes the `_nax` in-kernel staging family, and the
  reason is the useful part.** Staging is **throughput-bound on
  memory-operation ISSUE**, and with **28 co-resident simdgroups the
  latency is already hidden**, so **reordering is wall-time invariant**.
  That single sentence kills prefetch, double-buffering, software
  pipelining, and every other "move the load earlier" idea in this kernel.
  IR census invariants recorded for reuse: barrier **12→12**, dev_store
  **60→60**, mma **2→2**, tgMem **9,232 B**, maxThreads **1024**, **7 TGs
  per core**. Artefact: `research/artifacts/tanjiro-pr215-step0-pipeline-stats.txt`.

  The one lever in this region that is **not** reordering is **H16**, now
  assigned as #244: today the loader issues **3 device loads per thread per
  k-iteration** (one 16 B weight load plus two scale-byte consumptions);
  the scale cursor advances only **4 B per iteration** (`next()` at
  `fp_quantized_nax.h:505-511`), so **one aligned 16 B load covers four
  k-iterations ⇒ 1.25 loads/iter, a −58% cut in staging issue count**, at a
  cost of ~+4 registers and **zero byte change, bit-identical output**.
  Predicted −1.2 to −1.8 ms on S = **+0.45% to +0.67%**, which is **2.5σ to
  5.7σ** against `σ(S) = 0.318 ms` — the first `_nax` arm whose predicted
  effect exceeds the measurement noise. Two pre-conditions: header edits
  must be mirrored into the editable twin `mlx-generated/fp_quantized_nax.cpp`
  (**byte cost doubles**), and the **scale plane's 16 B alignment must be
  proved for both ranked shapes**, because `darkbloom_stage_wide_load_ok`
  (`quantized.cpp:1541-1570`) gates only the **weight** plane.

  **(E) ⭐⭐ Census corrections adopted from #215.** Prefill dispatches the
  routed gather kernel **38** times, not 39. The carried **17.66 GB**
  staged-byte total is retired in favour of the chunk-accurate
  **14.8264 GB** (8,379 BM64 chunks over 38 layers ⇒ **342.7 GB/s**,
  55.8% of the 614 GB/s peak; all-slots 38L is 17.2134 GB; ratio 0.8613).
  Frieren's `dS_1` rescale is **×38/39 = 42.1526 ms DOWNWARD**, not the
  ×40/39 upward figure he was carrying — broadcast to #148. The
  roofline-ridge "67%/67%" identity is retired. Streaming floor at
  614 GB/s = 24.15 ms ⇒ **19.11 ms of headroom inside W = 7.16% of score**.
  #215's §6 warm-vs-cold correction (warm 1261.7 vs corrected cold 1369.5,
  **+8.5%**) puts the true first-pass routed cost at **≈47 ms ≈ 48% of
  scored prefill**, which **discharges frieren's R-2 headline
  justification**; his live question is now purely the **linearity of the
  1.109 ms/layer-copy slope**.

  **(F) ⭐⭐⭐ The frontier plateau slate (from the frontier escalation
  agent), reprioritized by EV per ranked measurement.** Three carried
  assumptions were tested; one survived, two did not:

  - **A1** "the decode 1.20 ms/step gap is winnable overhead" — **still
    open**, and the way to settle it is an **absolute-µs inter-kernel gap
    histogram**. Assigned as #241.
  - **A2** "the prefill staging wall is latency/occupancy-bound" —
    **CONFIRMED WRONG by #215**. ~25.2 G staged params × ~3.2 lane-ops ÷
    (40 cores × 128 lanes × ~2 GHz) ≈ **7–8 ms**, matching the ~6.9 ms
    pure-issue residue. Latency-hiding levers are dead; **issue-count
    levers are alive** (hence H16).
  - **A3** "unique-byte censuses are complete cost models" — **wrong, and
    expensively so: the other half of prefill has never been audited.**
    97.9 − 43.3 = **54.6 ms of non-MoE prefill work with no census at
    all.** This is the largest unexamined object in the programme.

  New pricing constant: **6.9 ms / 25.2 G params ≈ 0.27 ps/param ⇒
  ~0.10 µs per M params not staged.** Use this to price any
  staging-reduction proposal before assigning it.

  Decomposition of the decode 1.20 ms/step gap: H1 achievable-below-peak
  bandwidth (~0.4–0.6 ms, mostly unwinnable); **H2 serial inter-kernel
  bubbles (~0.2–0.5 ms) ⇒ prologue fusion, 150 µs = +2.3%** (= #241, kill
  if summed mapped gaps < 100 µs); H3 end-of-step drain + host turnaround
  (~0.1–0.2 ms across ~7 asyncEval boundaries and one blocking 4-byte
  argmax readback); H4 per-kernel ramp (~0.1–0.15 ms); H5 KV/small-op ≈ 0.
  **Any mechanism removing ≥50 µs/step (+0.76%) beats almost everything
  prefill-side.**

  Ranked top-8 by EV per ranked measurement:
  1. **Decode bubble census → prologue fusion** (= #241, EV ≈ +0.8%)
  2. Multi-chunk `Ws` accumulator blocking (EV ≈ +0.45%; ⚠️ the redundancy
     multiplier is only **8379/7757 = 1.0802**, i.e. **+8.0%**, so the
     prize is small — low priority)
  3. LPT expert→threadgroup permutation `perm[tid.y]` (EV ≈ +0.4%;
     **simulate first, it is free**; kill if sim < 0.7 ms)
  4. Dense-GEMM prefill replication census (EV ≈ +0.5%)
  5. Loader issue-vs-port discriminator probe
  6. bf16 prefill-only attention scratch (+1–2% × P≈0.3; **MMA
     accumulation-order equivalence must pass the upstream-equivalence
     oracle**; RAM +2–3 GB)
  7. Cold-pass warm audit (EV ≈ +0.3%)
  8. RoPE-table precompute + step-tail micro-shaves (+0.08–0.23% × P≈0.5;
     input-independent ⇒ legal)

  ⚠️ The agent priced item 7 with the retired 0.2554 %/ms; the correct
  prefill elasticity is **0.374750 %/ms**.

  **(G) ⭐ NEW STANDING RULE — >70% BEFORE A RANKED SLOT.** Measurement
  strategy is now treated as a first-class optimization target. **No ranked
  run without a local discriminator that puts success probability above
  70%.** The in-flight limit is 1 and **shared with the birch track**, so a
  receipt costs roughly twice its nominal 20–22 min. #244's Part A (offline
  MSL compile + IR device-load census) is the model: it is fully offline,
  it *is* the reachability proof, and it carries an explicit kill rule — if
  the compiler already coalesces the scale loads, stop with zero receipts.
  This matters most for tanjiro, whose M4 Pro is gen 16 and therefore
  **never dispatches `_nax` at all**, leaving IR census as his only local
  channel.

  **(H) ⭐ Operational facts now shared with all four students.** (a) The
  in-flight limit of 1 is **shared with birch** — run `mlxfast submissions
  | tail -3` before every dispatch; conflict JSON is
  `{"error":{"code":"conflict","message":"account already has 1
  submission(s) in flight for this benchmark (limit 1)"}}`. (b) `mlxfast
  submit` **exits 0 even when it refuses** (confirmed on both the conflict
  and short-note paths) — parse stdout, the submission is real only if an
  id prints. (c) Notes must be **≥ 5 KiB**; put student name, PR number and
  assignment id in the first ten lines, because
  `mlxfast submission-note <id>` is the **only** reliable attribution
  channel — commit presence in the checkout carries **zero** signal, and
  `mlxfast submissions` truncates `officialMetrics`. (d) Never blind-retry
  a `failed` receipt; birch burned `0781a45` and `94a8526` doing exactly
  that. Birch identifiers seen so far: PRs #180, #198, #200, #201, #206,
  #207, #220. Byte budgets are **not** shared between tracks; the in-flight
  slot **is**.

  **(I) Round-28 receipt outcomes, with corrected deltas.**

  | receipt | commit | officialScore | attribution | corrected reading |
  |---|---|---|---|---|
  | `9631b9d` | `1201db1` | 1.64018613 | frieren #148 joint dose R-1 | **deliberate**, not an accident |
  | `c03dc11` | `be504bb` | 2.54908025 | nezuko #205 float4 | **−0.513% vs matched control (≈0.7σ)** |
  | `26b8e82` | `0b5372f` | 2.56253849 | tanjiro #215 arm 1, S=98.2092 ms | **NULL, +0.0123%** |
  | `0bc3eb4` | `5164d31` | 2.56222295 | ⭐ tanjiro #215 **byte-exact base control**, S=97.5250 ms | the campaign's most valuable receipt |

  **(J) Cleanup backlog (deferred, for a future student slot).** Dead
  surface now identified: the BK128 machinery (5,164 B); tanjiro's nine
  near-duplicate `.metal` variants; fern's `DARKBLOOM_LMHEAD_ROWMAJOR_REFINE`
  dual-arm flag (a **twice-measured M5 negative**, +0.2237% of `ns`
  recovered by defaulting it OFF); #170's probe machinery (~295 lines
  across 3 files); #148's injection machinery; ~32 KB of Laguna-dead
  transform sidecar coders; and ⭐ two stale comments at
  `quantized.cpp:1351-1363` (the "one 8B load / 8 bytes" WIDELD
  description, which is wrong — it is one **16 B** load covering 32
  elements) and `:1530-1533`. ⚠️ Do **not** delete the dead
  `foldGateIntoBank` / `lagunaFusedNormAffineQKV` INT8 paths — retained as
  documented precedent. ⚠️ Deleting #170's probe machinery re-incurs anchor
  debt.

  **(K) Answer to fern's #218 TASK.md FLAG on the attention quantization
  envelope — there is no contradiction, change nothing.** Attention Q/K/V/O
  are checkpoint-native **NVFP4 group-16 at 0.5625 B/param**; the accepted
  envelope's **group-32 INT8 is 1.125 B/param**, exactly **2× worse**.
  The envelope is a **permission, not a requirement**. Adopting INT8 would
  **add ~802 MB/token ≈ 28% of decode**. Operator commit `3fbbd2d3`
  independently demotes attention precision to "low-priority". Delivered to
  fern in #241 §1.1.

  **(L) Recorded, not penalised: #218 reported `runs: []`.** The W&B
  evidence channel remains empty for this target; the durable evidence is
  mlxfast receipts plus local decode probes. I have noted the gap rather
  than treating it as a defect of the experiment.





- **Most recent human research direction:** `3fbbd2d3`, "Soften Maple attention
  precision guidance" (2026-08-06 22:04:20 UTC), the second of two consecutive
  softening commits after `eae07f01` (21:55:23 UTC). Both are recorded in §0a;
  `55ab1b2`'s submitter-owns-retries rule remains in force (§10). **Read the
  pattern, not just the diffs: two operator commits inside ten minutes, both
  loosening prohibitions this advisor had hardened.** Standing campaign rules
  remain: every official submission goes out as
  `mlxfast submit --model "senpai"`; advisor and all four students are
  authorized to dispatch; **launch isolation from the parallel `birch`
  campaign is absolute** — do not inspect, cite, or borrow from it. Isolation
  is a *research* boundary, not a resource one: we share account-scoped
  validation capacity with that instance even though we must not share
  findings.
- **This is a living document.** It was 6,874 lines and had become an archive.
  Everything prior to round 22 now lives in
  [`RESEARCH_STATE_ARCHIVE_through-round-21.md`](RESEARCH_STATE_ARCHIVE_through-round-21.md).
  Read that only when you need the derivation behind a number quoted here.
  Keep *this* file short. Prune it every round.

