SENPAI-RESULT: {"terminal":true,"status":"complete","pending_arms":false,"wandb_run_ids":[],"primary_metric":{"name":"same_host_paired_estimate","available":false,"value":null},"test_metric":{"name":"passed_correctness","available":false,"value":null}}

- Student / PR: maple-edward / #684 (`maple-r109-d-sliding-attn-qk-mma`, rev `r109-d-rev1`)
- Hypothesis and target cost: replacing the 8 `simd_sum` QK reductions in
  `laguna_sliding_fused_attn_ring_v1` with a `simdgroup_matrix` MMA tile removes
  the cross-lane reduction cost and speeds up decode. Target: the sliding kernel
  is ≈6.9–9.0% of M5 decode time; a ~7% kernel win is ≈0.4% of score, against a
  0.378% deficit to the leader.
- Decision: **dead hypothesis** (mechanism measured slower than base, bit-exact),
  with a **live, quantified ceiling** handed back.
- `BASE_SHA` / candidate commit: `1a6761bf46c282fcabd0577b618f0c1206757e6c` /
  see PR head. No submitted-surface file was modified.
- Submitted candidate files: **none.** Stage 0 was a measurement stage; the Stage 1
  kernel was not built because Stage 0 refuted it.
- Supporting test or documentation files:
  `research/edward-r109/STAGE0_VERDICT.md` (full write-up),
  `research/edward-r109/{make_qk_arms.py,census_qk_reduction.py,run_probe.sh,run_stage0.sh,run_stage0c.sh,run_stage0d.sh,mma_price.metal,mma_throughput.metal,mma_throughput.swift,probe_*.txt}`.
- Official submission `--model` value (planned or used; default `senpai`): n/a —
  nothing to submit; maple-fern is the submission driver for this round.
- Explicit API model-value rejection, if fallback attribution was required: n/a.
- Assignment-scope preflight: `senpai/validate-assignment-scope.sh` and
  `senpai/check-editable-budget.sh` run against
  `1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7`; all changes are research-only under
  `research/edward-r109/`.
- Editable bytes / headroom / growth: submission surface **unchanged** (0 bytes of
  growth). `LagunaRuntimeModel.swift` remains 384,245 B of the 524,288 B per-file
  cap.
- Scored-path reachability evidence: `laguna_sliding_fused_attn_ring_v1` is
  declared at `LagunaRuntimeModel.swift:1504–1507`, dispatched at 1963–1972, and
  runs for the 30 of 40 layers with `layer % 4 != 0`; instrumented at 30 calls per
  decode step, per-call min 17.5–18.6 µs / p50 20.6–20.9 µs on this host.

### Evidence

- Host, memory profile, toolchain, and thermal policy: Apple **M4 Pro**,
  `applegpu_g16s` (arch gen 16), 20 GPU cores, 48 GiB (low-memory startup
  profile). Metal probes only; no `--local-iterate` run in this stage, so no
  thermal gate was involved. **All numbers are kernel-internal ratios on a gen-16
  host and are directional, never a ranked score.** Gen-16 hosts do not select
  the `_nax` kernels, but nothing here depends on `_nax`.
- Exact baseline and candidate commands: see §11 of
  `research/edward-r109/STAGE0_VERDICT.md`. Decisive sweep:
  `research/edward-r109/run_stage0d.sh null qk_pad4x_bcast0 qk_pad4x qk_bcast0 null`
  (`FERN_LADDER=32` = scored geometry, `FERN_REPS=200`, `FERN_ROUNDS=101`,
  `FERN_CACHE_COPIES=6`, `FERN_DEFEAT_SLOTS ∈ {64,1}`), supervised job
  `441a04a7-22e3-4ded-9717-5264ba8feae2`.
- Tests and risk-based checks run, including selected-test count: no numerical
  behaviour was changed on the scored path, so `LagunaUpstreamEquivalence` was not
  required and was not run. Probe validity checks instead: byte-identical `null`
  arms bracketing every sweep (**≤ ±0.05%** in all cases), two residency regimes
  (`FERN_DEFEAT_SLOTS` 64 and 1), static instruction census on **both**
  `applegpu_g16s` and `applegpu_g17s`, and a bit-exactness construction for the
  decisive arms (`pad_ * zero_`, `zero_ = U(widx > 0x3fffffffu)`).
- Correctness and serial-protocol verdict: **not applicable** — no scored-path
  edit. The two decisive arms are bit-exact by construction; the diagnostic arms
  are deliberately incorrect and were never candidates.
- Divergent tokens or failure category, if any: none (no candidate run).
- Peak RAM or generated-weight size, if relevant: n/a.
- Official ranking status versus correctness/floor status, if submitted: not
  submitted.

Paired kernel timing, `delta = arm − base` within a round, **negative = faster**:

| Arm (sliding kernel only) | slots=64 | t | slots=1 | t |
| --- | ---: | ---: | ---: | ---: |
| `null` (byte-identical bracket) | −0.043% | | −0.290% | |
| `qk_free` (no reduce at all) | −6.849% | −50.6 | −7.050% | |
| `qk_bcast0` (reduce → broadcast; **ceiling**) | −6.719% | −33.2 | −7.631% | −51.2 |
| `qk_ladder2` (W=8 tail) | −4.577% | | −4.677% | |
| `qk_quad_bcast` (W=4 tail) | −3.540% | −20.2 | −3.937% | |
| `qk_ladder5` (explicit 5-stage butterfly) | **+1.483%** | +12.9 | **+1.489%** | |
| `qk_pad4x` (4× MACs, bit-exact) | **+11.802%** | +119.5 | **+11.801%** | +88.2 |
| **`qk_pad4x_bcast0`** (MMA-shaped: 4× MACs + broadcast epilogue) | **+6.047%** | +24.4 | **+3.239%** | +19.8 |
| `null` (byte-identical bracket) | +0.019% | | +0.076% | |

| Metric | Baseline | Candidate | Ratio / delta |
| --- | ---: | ---: | ---: |
| decode seconds/token | not measured this stage | not measured | — |
| prefill seconds/token | not measured this stage | not measured | — |
| same-host paired estimate | — | not measured | — |
| MMA-shaped QK tile, sliding-kernel time (bit-exact) | 0.000% | **+6.047%** | **+6.047% slower** |
| reduce-elimination ceiling, sliding-kernel time | 0.000% | −6.719% | −6.719% |

The paired estimate is a same-host research metric, not an official M5 score; this
stage produced no end-to-end score at all by design.

### Conclusion

- What happened and why: the ceiling the assignment was chasing is **real and
  bigger than the stop threshold** — deleting the 8 `simd_sum` QK reductions is
  worth −6.7 to −7.6% of sliding-kernel time (≈0.354–0.461% of normalized score
  vs a 0.378% deficit). But the assigned **mechanism cannot collect it**. An
  `simdgroup_matrix<8,8>` QK tile has only 2 useful score rows per pipeline stage
  (two heads), so it must issue 4× the QK MACs. Priced bit-exact, that padding
  alone costs **+11.8%** — 1.6–1.8× the entire prize — and the full MMA-shaped arm
  is net **+6.0% / +3.2% slower than base**.
- Evidence for or against the mechanism: four independent lines, all against.
  (1) Bit-exact padding cost +11.8%, replicated in both residency regimes, t up
  to +119, NULL brackets ≤0.05%. (2) `simdgroup_multiply_accumulate` MAC rate
  measures **0.87× the measured scalar FMA peak** (3,158 vs 3,470–3,612 GMAC/s),
  matching the published AGX 102.5-Matrix-FFMA16-vs-128-scalar-FMA ratio; it needs
  ≥4× to fund the padding. (3) `qk_ladder5` — a hand-written full 5-stage shuffle
  butterfly, the shape any MMA fragment-reduction tail needs — is **+1.5%
  slower** than the built-in `simd_sum`, so `simd_sum` is already the cheapest
  correct 32-wide all-reduce on AGX. (4) Apple Tech Talk 111432 profiles
  `simdgroup_matrix` at **0% Neural Accelerator utilization even on M5**; the real
  matrix path is MPP `mpp::tensor_ops::matmul2d` gated on arch gen ≥ 17 /
  macOS 26.2+, gen-1 NA has no bf16, and MLX's own M5-vs-M4 data shows NA helps
  prefill (3.33–4.06× TTFT) far more than decode (1.19–1.27×).
  A methodological correction is part of the evidence: my first 4×-MAC arms
  reported −5.3% and −7.9% (i.e. "more work is faster"). That was an artifact of
  the **value-dependent branch in `LAGUNA_RESCALE`** (`LagunaRuntimeModel.swift:1874`,
  `if (as_type<uint>(delta) == 0u) ... else fast::exp(delta)`): score-perturbing
  arms change how often `fast::exp` executes. Holding the score bit-identical
  flips the sign from −7.9% to +6.0%.
- Uncertainty or M5 transfer risk: measured on gen-16 M4 Pro. The reduce-cost
  ratio should transfer in direction (the shuffle network is the same family and
  the g17s census tracks g16s within 3%), but magnitudes need M5 confirmation. The
  MMA refutation is *less* M5-sensitive, not more: on M5 the legacy
  `simdgroup_matrix` intrinsic still misses the Neural Accelerators entirely, and
  the padding term is architecture-independent arithmetic (4× MACs for 2-of-8
  useful rows). Unverified: MPP NVFP4 support (MLX PR #3551 hints at a limit) and
  any direct measurement of legacy `simdgroup_matrix` throughput on M5 silicon.
  Neither can rescue a tile that must win by 1.6–1.8× to break even.
- Smallest useful next action: keep the reduce ceiling open as its own item and
  test the **half-width lane split** — give lanes 0–15 eight dims of head0 and
  lanes 16–31 eight dims of head1, so one 4-pass 16-wide butterfly plus a single
  `simd_shuffle_xor(s, 16)` yields both scores in all lanes (5 reduce passes per 2
  heads instead of 10) at unchanged q/k register count. Expected ≈half the
  ceiling ⇒ 0.17–0.22% score; non-bit-exact, so it needs a margin certificate.
  **It requires advisor clearance**: an 8-dims-per-lane layout is a "wider
  per-lane load", on round 107's banned-re-open list
  (`research/CURRENT_RESEARCH_STATE.md:3292–3308`). Second choice is the W=4
  `quad_sum` re-tile (measured −3.5%/−3.9% ⇒ 0.184–0.24%, +56 floats/lane).
  Note that §7 of the verdict argues this whole area is in fact the *one surviving
  axis* that closure left open (≈12 issue slots per pipeline stage): each
  `simd_sum` burns ≈8.4 slot-equivalents, ≈16.8 per stage, ~8× what a static byte
  census shows — which also suggests the 97.7%-of-peak-issue model underprices
  cross-lane ops.
- Recommendation: **close** R109-D as `N-QK-MMA-PADDING-BOUND` (mechanism dead,
  ceiling quantified and handed back). Nothing to merge — no submitted file
  changed. Please forward §10 of the verdict to **@alphonse**, whose R109
  assignment applies the same MMA technique to the full-attention twin at
  `LagunaRuntimeModel.swift:2027+`; three of these results (built-in `simd_sum`
  already optimal, the M-padding bill, and the `LAGUNA_RESCALE` probe hazard)
  should save that assignment a full stage.
