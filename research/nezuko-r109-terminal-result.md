# R109 / PR #682 — terminal result (maple-nezuko)

- **Student / PR:** maple-nezuko / #682, assignment
  `maple-r109-b-router-hybrid-selector`, revision `r109-b-rev2`
- **Hypothesis and target cost:** Arm G — the `rmsbfloat16` attention pre-norm
  is 41 dispatches and 142.3 µs/step of decode busy pool, moves only 8 KB, and
  at 3.47 µs/dispatch is launch-bound; folding its reduction into a consumer
  should recover a large fraction of that pool. Target: clear the ~0.07% score
  landing bar (≈10 µs of M4 decode busy per step).
- **Decision: dead hypothesis.** Arm G is refuted, with two reusable rules and
  one correction to a banked census claim.
- **`BASE_SHA` / candidate commit:** base
  `1a6761bf46c282fcabd0577b618f0c1206757e6c`; candidate commit recorded in the
  typed result.
- **Submitted candidate files:**
  `Sources/MLXFastModel/LagunaNormFusedGateSoftplus.swift` (new, 232 lines),
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
   path**. Confirmation on a new kernel pair: b4's `C−W = +96.46 µs/step =
   2.35 µs/layer` (within 8% of 2.55). Bound for a nested consumer: `S−N` removes
   the `rmsbfloat16 → gate_sp` edge, whose consumer is 96.4% nested inside a
   larger co-resident record, and is worth ≤ 0.35 µs/layer — **7–10× cheaper**.
   Arm-selection consequence: "count edges × 2.55 µs" over-prices every edge
   whose consumer is nested, which is most small encoder kernels.

## Evidence

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
- **Correctness:** all 25 b5 slots and all 19 b4 slots reported
  `teacher-forced greedy tokens: 0 divergences (all match)`. Every arm is
  bit-exact against the shipped path, so nothing here is an accuracy trade.
- **Pricing used:** `%score = 0.63 × τ × Δ_M4_step_wall_µs / 8972`, i.e. at τ=1,
  0.0070 %/M4 wall µs. No published-receipt deltas are used as evidence
  anywhere: receipt sd is 0.4–0.9% on identical code, ~140 paired receipts would
  be needed to see this arm, so only the local harness decides.
- **Profiling discipline:** every decode profile in §7 of
  `research/nezuko-r109-armg-result.md` is taken at
  `DARKBLOOM_GPU_PROFILE_SPLIT=1` (busy_sum/busy_union = 1.1359 on this host and
  `gate_sp` is 96.4% nested, so SPLIT=0 per-kernel attribution is invalid).

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
- **Smallest useful next action:** if an M5 datapoint on threadgroup *width* (as
  opposed to tiling shape) is wanted, `DARKBLOOM_NORM_FUSED_GATE_SP=4` is a
  zero-risk one-env-var probe: bit-exact, +43.23 µs/step on M4. Flagged for
  maple-fern; I am not submitting it.
- **Recommendation: close.** Arm G is a dead hypothesis. Keep the file and the
  knob for the three banked rules and for reproducibility; ship no default
  change.
