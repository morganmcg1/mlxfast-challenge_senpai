# R109 / PR #682 — terminal result (maple-nezuko)

SENPAI-RESULT: {"terminal":true,"status":"complete","pending_arms":false,"wandb_run_ids":["ucuwf20o","wc4nbji0"],"primary_metric":{"name":"decode_us_per_step_delta_vs_control","available":true,"value":-51.73},"test_metric":{"name":"passed_correctness","available":true,"value":1}}

`status: complete` means the report is complete, not that the candidate won —
the decision below is **dead hypothesis**. `primary_metric` is the arm that
actually tested the hypothesis (mode C, the only arm that deletes the 41
`rmsbfloat16` dispatches): **−51.73 µs/step, i.e. slower than the shipped
control**, minimise-direction. No same-host paired *score* estimate is reported
because the shipped default is unchanged behaviour, so there is no candidate to
score.

- **Student / PR:** maple-nezuko / #682, assignment
  `maple-r109-b-router-hybrid-selector`, revision `r109-b-rev2`
- **Hypothesis and target cost:** Arm G — the `rmsbfloat16` attention pre-norm
  is 41 dispatches and 142.3 µs/step of decode busy pool, moves only 8 KB, and
  at 3.47 µs/dispatch is launch-bound; folding its reduction into a consumer
  should recover a large fraction of that pool. Target: clear the ~0.07% score
  landing bar (≈10 µs of M4 decode busy per step).
- **Decision: dead hypothesis.** Arm G is refuted, with **three new reusable
  rules**, one refinement of a banked rule, and one correction to a banked census
  claim.
- **`BASE_SHA` / candidate commit:** base
  `1a6761bf46c282fcabd0577b618f0c1206757e6c`; candidate commit recorded in the
  typed result.
- **Submitted candidate files:**
  `Sources/MLXFastModel/LagunaNormFusedGateSoftplus.swift` (new, 240 lines),
  `Sources/MLXFastModel/LagunaRuntimeModel.swift` (+30 −3, call site only).
  **The shipped default is unchanged behaviour** (`DARKBLOOM_NORM_FUSED_GATE_SP`
  defaults to `0`); the four alternative modes are the measurement instrument.
- **Supporting documentation:** `research/nezuko-r109-armg-result.md` (verdict
  and rules), `research/nezuko-r109-armg-b5-attribution.md` (four-arm
  attribution), `research/nezuko_armg_stage1c.md` (rungs 1a/1b/1c and b4),
  `research/armg-runs/` (raw slots and stats).
- **Official submission `--model`:** none. maple-fern (#686) is the sole
  submission driver; I did not run `senpai/submit-official.sh`.
- **Stage-0 null already banked:** `N-ROUTER-STAGE2-CHEAP` (commit `0eb218a5`) —
  the originally assigned router stage-2 hybrid selector arm was pre-empted
  because stage 2 is already cheap.
- **Assignment-scope preflight:**
  `senpai/validate-assignment-scope.sh 1bc1c895…0888d7 Sources/MLXFastModel/LagunaNormFusedGateSoftplus.swift Sources/MLXFastModel/LagunaRuntimeModel.swift`
  → `assignment scope OK: 2 submitted path(s)`. The submitted surface is verified
  non-empty against the research base:
  `git diff --numstat 1a6761bf… -- Sources Vendor benchmark.json Package.swift`
  = `240 0 …/LagunaNormFusedGateSoftplus.swift` and `30 3 …/LagunaRuntimeModel.swift`;
  **`Vendor/` does not appear in the diff** (the profiling patch is applied only
  inside a throwaway `.build-prof` clone and reverted by an EXIT trap before any
  timing run).
- **Editable bytes / headroom / growth:** `senpai/check-editable-budget.sh` →
  `editable budget OK: current=2693517/3000000 headroom=306483
  growth=-290332/262144 files=143 (base=142)`.
- **Scored-path reachability evidence:** the edited call site is
  `LagunaRuntimeModel.swift:5949–6025`, inside the per-layer decode attention
  path, and it is reached on all **40** gated encoder layers in every steady
  decode step — confirmed structurally by the SPLIT=1 profile, which shows the
  new kernels dispatching **30× (h64) + 10× (h48) per step** in modes 1–4 and the
  shipped `gate_sp_h64/h48_v1` dispatching 30+10 in mode 0. The arithmetic closes:
  `rmsbfloat16` is 41 dispatches = 40 layer pre-norms + 1 final norm, and mode C
  leaves **exactly 1** surviving dispatch (the final norm). Steady decode on this
  runtime has no NAX path and no `#available` gate, so the M4 host reaches the
  same code the M5 scorer would.

## Result

Sign convention: **positive = candidate faster than shipped control.**

| arm | mechanism | µs/step vs control | CI95 | clears 0 |
|---|---|---|---|---|
| C (mode 1) | fused `gate_sp` is sole producer of `normalized`; **pre-norm dispatch deleted** | **−51.73** | b4, 19 slots | slower |
| W (mode 2) | RMS restated in `gate_sp`, pre-norm kept, unread `normalized` store | +46.33 | [+40.15, +55.08] | yes |
| N (mode 3) | RMS restated in `gate_sp`, pre-norm kept, no `normalized` output | +51.96 | [+22.13, +59.94] | yes |
| S (mode 4) | **shipped gate math at 8 TG × 256 thr instead of 8 TG × 64** — no dispatch or edge removed | **+43.23** | [+37.06, +58.00] | yes |
| S→N | the fusion itself, net of geometry | **+8.73** | [−14.19, +22.77] | **no** |

The only arm that removes the 41 dispatches is 51.7 µs/step **slower**. Of the
+51.96 µs/step that the best surviving arm does win, **83% is threadgroup
geometry** (mode S changes no arithmetic and removes nothing), and per PR #7
(+7.32% M4 → ~0% M5) geometry carries τ ≈ 0. The residue attributable to the
fusion is +8.73 µs/step and does not clear zero.

## Busy next to wall next to barriers — the requested datum

Comments 6, 8 and 10 asked for the wall delta reported next to the busy delta,
and for the encoder barrier count under SPLIT=1. All five arms, SPLIT=1
per-kernel attribution against the uninstrumented harness wall
(`research/armg-runs/p1`, job `6bb1ee2b-d0d6-4fcf-8278-e33d8109bf4a`, 39 steady
steps/arm, `0 divergences`):

| arm | dispatches | isolated busy saved | barriers/step | **shipped wall** | conversion |
|---|---|---|---|---|---|
| A shipped | 406 | — | 247 | ref | — |
| S | 406 | +136.9 µs | 247 | **+43.23 µs** | **0.32** |
| W | 406 | **−6.8 µs** | 247 | **+46.33 µs** | sign flips |
| N | 406 | +17.4 µs | 247 | +51.96 µs | 2.99 |
| **C** | **366** | **+204.9 µs** | **243** | **−51.73 µs** | **−0.25** |

"Isolated busy saved" is the **targeted-family** delta, i.e. the SPLIT=1 busy of
`rmsbfloat16` plus the whole `gate_sp*` family — the only two families any arm
touches — against arm A's 459.8 µs/step. It is deliberately *not* the whole-step
`busy_sum` delta (which is +62 / +9 / +25 / +160 µs for S/W/N/C) because
whole-step `busy_sum` at `n=1` carries the ±40 µs/step drift floor documented
below and would credit each arm with savings in kernels it never touched. Every
number in this table is regenerated from the committed `.prof`/`.err.gz`
artifacts by `research/nezuko_r109_profile_summary.py`
(→ `research/armg-runs/p1/summary.json`), so the prose cannot drift from the
measurement; the shipped-wall column is the b5/b4 harness, not the profile.

1. **Arm C really does delete the pool.** `rmsbfloat16` goes from
   **41 dispatches / 141.6 µs** to **1 dispatch / 3.5 µs**, and total dispatches
   from 406 to 366 — exactly the 40 removed. And it is 51.7 µs/step slower.
   **Isolated per-kernel busy got the sign wrong, not just the magnitude.**
2. **Best-case conversion is ~0.31, not 1.0.** S removes 138.0 µs/step of
   isolated `gate_sp` busy and the harness returns 43.23 µs/step of wall — the
   µs meaning of "96.4% nested".
3. **Isolated busy has no predictive power here.** S, W and N agree on shipped
   wall within their CIs (+43.2 / +46.3 / +52.0) while their isolated `gate_sp`
   busy spans **144 µs** (180.2 → 324.2 µs/step). W is *worse* than control on
   isolated busy and 46 µs *better* on wall.
4. **Barrier count under SPLIT=1 is exactly 0, by construction** —
   `maybeInsertBarrier()` only fires within a command buffer and `commit()`
   resets `needs_barrier_`, so SPLIT=1 replaces all 247 barriers with 406
   command-buffer boundaries. Per-step, both ways, same instrumented build:

   | regime | cbs | dispatches | barriers | wall µs | gap µs |
   |---|---|---|---|---|---|
   | SPLIT=0 (ships) | 45 | 406 | **247** | 8211 | 250 (3.0%) |
   | SPLIT=1 (profiling) | 406 | 406 | **0** | 9823 | 1288 (13.1%) |

   +1038 µs of gap over +361 command buffers = **2.875 µs/cb**, an independent
   reproduction of `CB_GAP_US_PER_DISPATCH = 3.03` by a different route. SPLIT=0
   instrumented wall (8211) is 0.5% from the uninstrumented harness (8256), so
   the hook is nearly free at SPLIT=0; SPLIT=1 wall is +19.6% and **mis-ranks the
   arms** (S is best on shipped wall and worst on SPLIT=1 wall), so SPLIT=1 is
   for attribution only.
5. **The mechanism, measured.** The A→C barrier diff is exactly conservative:
   **−31 on `rmsbfloat16`, +27 and +4 on `gate_sp_rms_emit_h64/h48` = +31.**
   Deleting the pre-norm does not remove the dependency edge, it **transplants**
   it onto a narrow (8-threadgroup) producer that then holds the critical path in
   front of the 5120-threadgroup QKV matvec. Arm W is the control that isolates
   this: it runs the *same* fused kernel and takes **0** barriers, because
   `rmsbfloat16` still runs first and clears `needs_barrier_`.
6. **Why the 25-slot block was necessary, shown rather than asserted.** Pass 2
   also yields an `n=1` SPLIT=0 *wall* per arm (A 8211, W 8183, N 8226, S 8254,
   C 8267 µs/step). Read as an A/B those single runs would say A−W = +28, A−N =
   **−15**, A−S = **−43**, A−C = −56 — they agree in sign with the b5/b4 verdict
   for W and C but get the sign **wrong** for S and N, on which they disagree
   with a 25-slot block by ~86 and ~67 µs/step. The arm-to-arm spread of those
   single-run walls is 84 µs = 1.0%, i.e. larger than every effect being
   measured. So the profile block is reported as attribution only; nothing in
   the verdict rests on a wall figure taken at `n=1`, and this is the direct
   demonstration of the ±0.5% drift floor quoted in Evidence.

## Rules produced

1. **`N-DISPATCH-REMOVAL-NOT-SYMMETRIC`** — "add a dispatch, pay 2.34 µs" (Rule
   65) holds; "remove a dispatch, gain 2.34 µs" is refuted. This corrects
   `research/maple-fern-r105d-decode-dispatch-census.md:229` (H4: "the 41
   `rmsbfloat16` dispatches are a 95.9 µs/step launch tax"), which is
   arithmetically true and causally false, overstating the recoverable amount by
   **21.7×**. Independent agreement: Rule 68 / PR #527 removed 78 prefill
   dispatches and *cost* +0.639 ms; PR #483 (W&B `ubjfsywa`) *added* 80
   dispatches of this same kernel family for +8.61 µs/step
   [−17.71, +35.02] = 0.108 µs/dispatch. Census pool size is an upper bound on
   opportunity, not an estimate of it.
2. **`N-SOLE-PRODUCER-WIDTH-RATIO`** — a reduction may be fused into a narrow
   consumer only if that consumer does not thereby become the sole producer for a
   wide one. `gate_sp` launches 8 threadgroups and is latency-bound; the QKV
   matvec launches 5120. Making `gate_sp` the sole producer of `normalized` puts
   an 8-wide latency-bound kernel in series ahead of the widest kernel in the
   encoder, which costs more than the dispatch saves.
3. **`N-INDS-DEPENDENCY-BARRIER` refinement** — the ~2.55 µs/layer edge price
   applies only when the edge's **downstream kernel is itself on the critical
   path**. Confirmation on a new kernel pair: b4's `C−W = +96.46 µs/step [+81.21, +105.54] =
   2.35 µs/layer` (within 8% of 2.55). Bound for a nested consumer: `S−N` removes
   the `rmsbfloat16 → gate_sp` edge, whose consumer is 96.4% nested inside a
   larger co-resident record, and is worth ≤ 0.35 µs/layer — **7–10× cheaper**.
   Arm-selection consequence: "count edges × 2.55 µs" over-prices every edge
   whose consumer is nested, which is most small encoder kernels.
4. **`N-BARRIER-COUNT-NOT-PRICE`** (new, from the census) — the per-step
   intra-encoder barrier count is **not** a state variable for pricing a decode
   edit. Across these five arms the shipped wall spans **98 µs/step** while the
   barrier count spans **4** (247/247/247/247/243), and the only arm that
   *reduces* the count is the only arm that *regresses*. Reading
   `N-INDS-DEPENDENCY-BARRIER` as a per-edge multiplier over the encoder's 247
   barriers predicts 630 µs/step of recoverable cost, which does not exist.
   **Replacement, which is predictive:** when an edit changes which kernel
   produces a wide consumer's input, price it as
   `N_layers × (isolated_latency(new producer) − isolated_latency(old producer))`
   using SPLIT=1 latencies. Here
   `30×(6.30−3.45) + 10×(6.24−3.45) = 113.4 µs/step` forecast versus
   **98.06 µs/step measured** (`W − C`), i.e. within 16% — and both inputs are
   available from a census *before the arm is built*.

## Evidence

- **W&B runs** (project `wandb-applied-ai-team/mlxfast-maple`, group
  `r109-armg-norm-fused-gate-softplus`):
  - **`ucuwf20o`** — `r109-armg-b5-refuted`: the 25-slot four-arm attribution
    block (A/S/W/N), plus the full SPLIT=1 per-kernel profile and SPLIT=0
    barrier census for all five arms, plus the `--local-iterate` correctness
    receipt. <https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/ucuwf20o>
  - **`wc4nbji0`** — `r109-armg-b4-primary-metric`: the 19-slot A/C/W block that
    contains arm C and therefore carries the primary metric
    `−51.73 µs/step [−61.21, −38.04]`.
    <https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/wc4nbji0>
  Both runs' config and summary are built by
  `research/nezuko_armg_wandb_log.py` from committed artifacts only
  (`stats.json`, `p1/summary.json`, `score.local-iterate.json`), so W&B, the
  result docs and the repository cannot disagree.
- **Host:** Apple M4 Pro, 20 GPU cores, 48 GiB, macOS 26.5.2, `applegpu_g16s`.
  Steady decode on this runtime is host-independent (no NAX path, no `#available`
  gate), so M4 decode is a structurally valid instrument for an M5-scored arm;
  only the throughput-scaling factor τ is at issue. GPU steady ≈ 42 °C, logged
  per slot with `macmon`; no throttling.
- **Harness:** `research/nezuko_armg_ab.sh` — one worker process per arm so the
  env knob is read once at process start, position 0 discarded as warm-up,
  `ARMG_STEPS=200`. Statistics `research/nezuko_armg_stats.py`: per-slot median
  over 199 steps → median-of-medians per arm → 20 000-draw bootstrap over slots.
  b5 order `A | A S W N | S W N A | W N A S | N A S W | N W S A | A N W S`, so
  every arm appears in every position class.
- **Exact baseline and candidate commands.** All arms are one binary and one env
  knob, so baseline and candidate are the *same* command with a different value
  of `DARKBLOOM_NORM_FUSED_GATE_SP` (`A`=0 control, `C`=1, `W`=2, `N`=3, `S`=4):
  - build: `research/fern_r93_build_worker.sh` (release worker into `.build-worker`)
  - headline A/B (b5, 25 slots): `research/nezuko_armg_b5.sh`, i.e.
    `ARMG_STEPS=200 research/nezuko_armg_ab.sh b5 A  A S W N  S W N A  W N A S  N A S W  N W S A  A N W S`
  - per-arm slot, as issued by that script:
    `DARKBLOOM_NORM_FUSED_GATE_SP=<0|1|2|3|4> python3 research/decode_probe.py --steps 200 --dump-steps <slot>.json`
  - attribution profile (both passes, all five arms):
    `ARMG_PROF_STEPS=40 research/nezuko_armg_split_profile.sh p1 A S W N C`,
    which internally runs pass 1 at `DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=1`
    and pass 2 at `DARKBLOOM_GPU_PROFILE_SPLIT=0` with the `GPUBARRIER` census edit
  - barrier period recovery: `python3 research/nezuko_r109_barrier_period.py research/armg-runs/p1/split0-A.err.gz`
    and `--diff … split0-A.err.gz split0-C.err.gz`
  - shipped-default tripwire: `./benchmark.sh --local-iterate` at HEAD
  - upstream oracle: `bash research/run_upstream_equivalence.sh` at HEAD, and its
    base control `bash research/nezuko_r109_equivalence_base_control.sh`
    (swaps both submitted files to `BASE_SHA`, reruns, restores)
- **Tests and risk-based checks run, including selected-test count.**
  - `./benchmark.sh --local-iterate` at HEAD (commit `375619b2`), exit 0,
    217 s: **`case_count = 1`, `checked_steps = 130`** (128 teacher-forced decode
    steps + 2 prompt-boundary steps), `preflight_seconds = 43`.
    `passed = true`, `passed_correctness = true`.
  - Per-slot teacher-forced greedy check inside the A/B harness: **44 slots**
    (25 b5 + 19 b4) and **10 profile runs** (5 arms × 2 passes), each reporting
    `0 divergences`. This is the risk-based check that matters here, because it
    covers all five modes, whereas `--local-iterate` only exercises the shipped
    default.
  - Vendored-upstream equivalence oracle — the M5 operator gate of
    `docs/laguna-weight-contract.md` — run at HEAD by
    `research/run_upstream_equivalence.sh`: **1 selected test**
    (`lagunaRuntimeMatchesVendoredUpstreamOnM5WhenEnabled`; swift-testing reports
    "1 test in 0 suites", and the `Executed 0 tests` line above it in the log is
    the *XCTest* harness, which owns none of this file's tests. The wrapper also
    fails closed with exit 3 if the report marker is missing, so a
    zero-selection false pass is excluded.) Result: **greedy tokens match
    upstream at all 9 steps**, **8/8 decode steps bit-exact**
    (`maximumAbsoluteLogitError = 0`), and the single 512-token **prefill step
    differs by 0.125 max / 0.011934 mean** absolute logit error. The oracle's
    tolerance is exactly `0`, so it **exits 1**. I am reporting that as a
    non-pass, not rounding it into the PASS above.
  - **That prefill delta is pre-existing at the research base, not this arm.**
    `research/nezuko_r109_equivalence_base_control.sh` restores both submitted
    files to `1a6761bf…`, verifies the swap left **no** `git diff --numstat` rows
    against the base under `Sources` (so the control binary *is* the base
    binary), rebuilds, and re-runs the identical oracle. The report comes back
    **byte-identical**: prefill `0.125` / `0.011933609`, all decode steps `0`,
    the same nine token pairs, the same exit 1
    (job `8b4df1ad-52de-40ec-8d80-23cab268756c`; HEAD run
    `3cf24652-5b6c-4a57-83d0-72bf3844d0ae`). The trap restored `Sources` cleanly
    (`CONTROL_SOURCES_DIRTY_AFTER_RESTORE=0`). Two independent structural reasons
    this arm *cannot* reach prefill: the shipped default is mode `0`, which
    returns `nil` at `guard lagunaNormFusedGateSoftplusEnabled` before any
    dispatch is built, and in *every* mode the fused path additionally requires
    `residual.dims(1, 1, 2048)` — a single decode token. So the honest reading is
    that the base is not bit-exact against vendored upstream on one prefill step
    **on this M4 host**, which is consistent with the gate being documented for
    the M5 ("operators invoke its gated test on the M5"); it is an unresolved
    pre-existing observation, and it is unchanged by this arm.
  - `senpai/validate-assignment-scope.sh` and `senpai/check-editable-budget.sh`
    both run and passing (quoted above).
  - Not run: the full official ranked runner (`senpai/submit-official.sh`) — by
    instruction, maple-fern (#686) is the sole submission driver.
- **Correctness and serial-protocol verdict: PASS on every gate this arm can
  affect**, with the one documented exception above (the M5 prefill-exactness
  oracle, which fails identically at `BASE_SHA` and at HEAD).
  `passed_correctness = true`, `max_abs_diff = 0`, `first_failing_step = null`,
  `first_failing_case = null`, `first_failing_layer = null`, and the
  `golden_hash` at HEAD is **`b9509697…a58d7a63`, byte-identical to the
  `score.local-iterate.baseline.json` recorded at commit `ad39bfc`**. The serial
  worker protocol is unchanged: the shipped default adds no dispatch, no host
  round-trip and no new tensor to the decode step, and `harness_hash`
  (`ce964eb0…`), `weights_hash` (`aff99430…`), `weights_file_count = 9` and
  `num_layers = 40` all match the baseline receipt.
- **Divergent tokens or failure category: none.** 0 divergent tokens in every
  one of the 54 timed/profiled runs above and 0 in the 130-step
  `--local-iterate` check; `error = ""`, `partial_result = false`. The upstream
  oracle likewise agrees on the **greedy token at all 9 of its steps**, at HEAD
  and at base. All four non-default modes are bit-exact against the shipped path,
  so nothing in this arm is an accuracy trade — the refutation is purely about
  time. The one non-pass on record (prefill logit exactness) is a base/host
  property with **no token divergence at all**.
- **Peak RAM and generated-weight size: unchanged.** `peak_ram_gb = 21` and
  `weights_byte_count = 21568891382` at HEAD, identical to the baseline receipt;
  `process_resident_memory_gb = 0.025`. No weights are generated or repacked by
  this arm. The fused kernel's only new memory is **4240 B of threadgroup
  memory** per threadgroup (8 threadgroups), which is not host RAM. Note the
  worker starts in the "low-memory startup profile" on this 48 GiB host
  (allocator cache capped at 6 GiB) with all ranked code paths still enabled;
  observed `worker_rss_gb ≈ 20.72`, `mlx_peak_gb ≈ 35.33`.
- **Official ranking status: not submitted, by instruction.** No
  `senpai/submit-official.sh` run and no receipt was produced by me; published
  receipts cannot resolve an effect of this size anyway (receipt sd 0.4–0.9% on
  identical code vs. a 0.07% landing bar). The shipped default is unchanged
  behaviour, so there is nothing here that needs a ranking slot. `mode=4` is
  flagged to maple-fern (#686) as a zero-risk, bit-exact, one-env-var M5 probe.
- **Metric table.** `--local-iterate` at HEAD vs. the repo's recorded
  `score.local-iterate.baseline.json`. These two numbers are **not** the arm
  measurement — the shipped default is unchanged behaviour, so this row is a
  tripwire confirming "no regression", and the ±0.1–0.2% wobble is single-run
  harness noise well inside the ±0.5% drift floor below.

  | metric | baseline (`ad39bfc`) | candidate (`375619b2`) | delta |
  |---|---|---|---|
  | decode s/token | 0.0129561 | 0.0129708 | +0.11% |
  | prefill s/token | 0.00112423 | 0.00111129 | −1.15% |
  | local est score | 0.7952 | 0.7968 | +0.2% |
  | decode speedup | 1.0695 | 1.0683 | −0.11% |
  | `peak_ram_gb` | 21 | 21 | 0 |
  | `max_abs_diff` | 0 | 0 | 0 |

  `passed_prefill_speedup_floor = false` on **both** baseline and candidate
  (0.327 vs 0.331 against a 0.95 floor): that is a pre-existing property of
  `--local-iterate`'s short prompt, not a candidate regression, and it is why
  this row is a tripwire rather than a score.

  **Same-host paired estimate for the actual hypothesis** comes from the A/B
  blocks, not from this table. Mode C — the only arm that deletes the 41
  dispatches — is *slower* than the shipped control on three independent blocks:
  **b4 `A−C` = −51.73 µs/step [−61.21, −38.04]** (19 slots, 6 replicates/arm),
  **b3 `A−C` = −48.04 µs/step [−60.02, −37.87]** (9 slots), and the earlier
  coarser b1/b2 rungs at −344.75 and −700.40 before the kernel was tuned. The two
  independent CIs overlap almost exactly and neither comes within 38 µs of zero.
  `−51.73` is the value carried in the typed result as the primary metric (the b4
  point estimate, the best-tuned version of the arm that actually tests the
  hypothesis). The best *alternative* mode is +51.96 µs/step
  faster, but +43.23 of that is threadgroup geometry: at τ=1 the best case is
  +0.475% of M4 score and the non-geometry residue is +0.080% with a CI
  straddling zero.
- **Evidence for or against the mechanism.** Against, on four independent
  measurements that all point the same way:
  1. *Direct.* Mode C removes exactly the 40 dispatches the hypothesis targets
     (41 → 1) and saves **+204.9 µs/step of isolated busy** — more than the
     census pool predicted — yet shipped wall goes the **wrong way** by 51.73
     µs/step. Conversion factor **−0.25**.
  2. *Counterfactual.* Mode W leaves all 41 dispatches in place, does strictly
     more arithmetic (it recomputes the RMS *and* stores an unread `normalized`),
     is **−6.8 µs/step worse in isolated busy**, and is **+46.33 µs/step faster
     shipped**. If the launch tax were the mechanism, this arm could not exist.
  3. *Decomposition.* A−S = +43.23 µs is a pure threadgroup-geometry contrast
     (ns8r1 vs ns2r4, identical gate math, still consuming `normalized`), i.e.
     **83% of the best arm's gain has nothing to do with the pre-norm at all**,
     and N−S = +8.73 [−14.19, +22.77] is the fusion residue and does not clear
     zero.
  4. *Structural.* The barrier census shows why: mode C reduces barriers by only
     4 (247 → 243) because the removal is exactly conservative — 31 `rmsbfloat16`
     barriers are replaced by 31 `gate_sp_rms_emit_*` barriers — while the fused
     kernel becomes sole producer for the 5120-threadgroup QKV matvec at
     8-threadgroup width, raising `gate_sp_h64` from 3.45 to 6.30 µs/dispatch.
     The predictive form `N_layers × Δ isolated_latency(producer)` forecasts
     113.4 µs/step against 98.06 measured (`W−C`), within 16%.
- **Correctness:** all 25 b5 slots and all 19 b4 slots reported
  `teacher-forced greedy tokens: 0 divergences (all match)`. Every arm is
  bit-exact against the shipped path, so nothing here is an accuracy trade.
- **Pricing used:** `%score = 0.63 × τ × Δ_M4_step_wall_µs / 8972`, i.e. at τ=1,
  0.0070 %/M4 wall µs. No published-receipt deltas are used as evidence
  anywhere: receipt sd is 0.4–0.9% on identical code, ~140 paired receipts would
  be needed to see this arm, so only the local harness decides.
- **Profiling discipline:** every per-kernel decode profile in §7 of
  `research/nezuko-r109-armg-result.md` is taken at
  `DARKBLOOM_GPU_PROFILE_SPLIT=1` (busy_sum/busy_union = 1.1359 on this host and
  `gate_sp` is 96.4% nested, so SPLIT=0 per-kernel attribution is invalid).
  SPLIT=1 verified de-nested in-run: `busy_sum/busy_union` = 1.0001–1.0122 across
  the five arms. The barrier census is the one measurement that *must* be SPLIT=0,
  because SPLIT=1 makes the barrier count identically zero (§7.4) — reported both
  ways rather than substituted.
- **Single-run drift floor:** comparing A→S per kernel, ~12 kernels that neither
  arm touches each drifted +0.2…+0.6 µs/call, +~75 µs/step total, so `n=1`
  `busy_sum` carries a **~0.5% ≈ ±40 µs/step** floor. Per-kernel deltas of the
  size reported (−138 µs) are above it; `busy_sum` deltas are reported for
  structure only, and no verdict rests on them.
- **Self-inflicted confound, disclosed and not corrected:** b5 slots p17-N and
  p22-N ran while a helper process was committing into
  `research/armg-runs/b5/`. Both show *widened*, not shifted, distributions
  (p17 p10–p90 = 8151.5–8321.1 µs). They are **not dropped**: the 17-slot interim
  read gave `N−S = −11.92 [−18.48, −8.52]` ("significant"), which is exactly the
  reason post-hoc exclusion is unavailable to me. The reported `N−S = +8.73
  [−14.19, +22.77]` includes them, and the conclusion "the fusion residue does
  not clear zero" is the conservative direction for my own arm.

## Conclusion

- **What happened and why:** the launch-tax framing of the `rmsbfloat16` pool
  does not survive contact with either consumer. The wide consumer (QKV matvec,
  5120 TGs) makes the reduction 1.62× more expensive because every threadgroup
  recomputes it; the narrow consumer (`gate_sp`, 8 TGs) can host the reduction
  cheaply but only becomes a *saving* if it also becomes the sole producer of
  `normalized`, at which point it serialises the encoder in front of the QKV
  matvec and loses more than it saves.
- **Uncertainty / M5 transfer risk:** the one reproducible M4 win here is
  threadgroup width, whose τ is assumed ≈ 0 from PR #7 rather than measured. That
  assumption is conservative — it makes my own candidate look worse. The
  fusion-only residue (+8.73 µs) has an interval covering both signs.
- **Why I did not buy a tighter `N−S`.** The fusion-only residue is the one
  component whose τ is plausibly ~1, it sits at ~0.06–0.08% (i.e. astride the
  0.07% bar), and the preregistered rule "mode 3 only if `S−N` clears zero" turns
  on it, so I started a dedicated 24-replicate-per-arm S-vs-N block on a quiet
  host and then **cancelled it after 2 slots**, because tightening it cannot
  change a decision: mode 3 is only reachable *through* the ns8r1 geometry, and a
  threadgroup-geometry change is out of headline scope by instruction (PR #7,
  +7.32% M4 → ~0% M5). A significant `N−S` would therefore buy a ~0.06% arm
  bundled with a change I am told not to headline — so the residue is left
  honestly wide rather than pursued. The two completed slots do corroborate the
  b5 S arm across sessions (fresh medians 8210 / 8215 µs vs b5's 8212.96 µs,
  `n = 2`), which is a useful reminder that *within*-arm reproducibility here is
  far better than the *across*-arm single-run drift documented above.
- **Smallest useful next action:** if an M5 datapoint on threadgroup *width* (as
  opposed to tiling shape) is wanted, `DARKBLOOM_NORM_FUSED_GATE_SP=4` is a
  zero-risk one-env-var probe: bit-exact, +43.23 µs/step on M4. Flagged for
  maple-fern; I am not submitting it.
- **Incidental observation for whoever runs the M5 gate next** (not part of this
  arm, and not a rule): on this M4 host the *research base itself* fails the
  vendored-upstream oracle's exact-prefill expectation by 0.125 max absolute
  logit error while matching every greedy token and every decode logit exactly.
  Anyone who runs `--filter lagunaRuntimeMatchesVendoredUpstreamOnM5WhenEnabled`
  on an M4 will get exit 1 and should not read it as their own regression;
  `research/nezuko_r109_equivalence_base_control.sh` is the 30-second control
  that settles it. Whether the delta is genuinely M4-specific or an unnoticed
  base-vs-upstream prefill difference is **unresolved** — I did not have an M5 to
  discriminate, and I am not claiming which.
- **Recommendation: close.** Arm G is a dead hypothesis. Keep the file and the
  knob for the three banked rules and for reproducibility; ship no default
  change.
