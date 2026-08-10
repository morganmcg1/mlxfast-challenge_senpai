# Advisor note, round 105 — the decode step is half empty, and five of my §12 claims were wrong

Provenance: written by the advisor after merging fern's 105-C result (PR #598,
`research/fern-r105c-gate-surface-masking-audit.md`, 959 lines, W&B run `xxko1538`) and
after reading tanjiro's 105-A Stage-1 report (PR #592,
`research/maple-tanjiro-r105a-afrag-ntile-reuse.md`, 882 lines).

This note does three things:

1. records the corrections fern's measurement forced on my round-105 §7.2 / §12 gate analysis;
2. publishes the decode-step dispatch map that falls out of her artifact
   (`research/artifacts/fern-r105c/dispatch-summary.json`) — the observation that motivates
   assignment 105-D;
3. records two methodological findings — tanjiro's D6 and fern's tracer-quota retraction —
   that both say the same thing: **our probes have been reporting success while the thing they
   probe was broken.**

---

## §1 — THE HEADLINE OF 105-C: `m = 0.0380`, AND §10 STANDS

Fern's preregistered metric was `m_dead_gate_fraction` = the fraction of the 79 runtime
default-ON gates that qualify as a live dormant-win candidate. Measured: **3 / 79 = 0.0380**,
against a preregistered kill threshold of 0.25 and a confirm-my-§10 threshold of 0.05.

**⇒ `advisor-r104-the-receipt-is-the-instrument.md` §10 ("there is no dormant-win
inventory") STANDS, on measurement rather than on my static census.** Zero receipts were spent
to establish it. This is the second time in three rounds that the most valuable result of a
round has been a negative.

---

## §2 — FIVE CORRECTIONS TO MY §12 "SEVEN SILENT SWITCHES"

`research/advisor-r105-the-routed-gather-gemm-is-memory-bound.md` §7.2 tabulated seven
default-ON fusion gates and my static verdicts on each. Fern instrumented them. Five verdicts
were wrong, and the two decode-side ones were wrong in the direction that mattered.

| # | gate | my static verdict | measured verdict |
|---|---|---|---|
| 1 | `DARKBLOOM_FUSED_SHARED_DOWN_RESIDUAL` | "very likely masked" | 🔴 **DEAD** |
| 2 | `DARKBLOOM_FUSED_ROUTED_DOWN_REDUCE` | "very likely masked" | 🔴 **DEAD** |
| 3 | `DARKBLOOM_PREFILL_FUSED_RESIDUAL_RMS` | live | live (confirmed) |
| 4 | `DARKBLOOM_PREFILL_SORTED_MOE_TAIL` | live, bit-exact — clean | live (confirmed) |
| 5 | `DARKBLOOM_INVERSE_SCATTER` | "PROVABLY UNREACHABLE" | 🔴 **dead by DOMINATION, not unreachable** |
| 6 | `DARKBLOOM_ROUTE_COUNTING_SORT` | dominates gate 7 | confirmed |
| 7 | `DARKBLOOM_ROUTE_FUSED_SCATTER` | live; I derived 2 vs ~7 dispatches | live; **measured ON = 1 vs OFF = 6** |

### §2.1 — Gates 1 and 2 are dead, so there were never any decode-side candidates

One `DARKBLOOM_TRACE_FUSION=1` run over 8 decode steps settled both. `routed+shared down
residual` (**LRM:10922**) fires **39× per step**; `routed down reduce` (**LRM:10949**) and
`shared down residual` (**LRM:9065**) are **absent**. The dispatch-trace differential
corroborates: arms `d` (`ROUTED_DOWN_REDUCE=0`) and `e` (`SHARED_DOWN_RESIDUAL=0`) are
byte-identical to base — 103 JIT libraries, 11,244 trace rows, md5 `4ac08364…`.

Gates 3–7 are all prefill-only, which carries 25 % of the score weight. **Gates 1 and 2 were
the only decode-side gates in my shortlist, and both are dead.** My §12 shortlist therefore
never contained a decode lever at all.

Note also that my line references were wrong: I published :9064 / :10930 / :10897. The correct
sites are **LRM:9065 / :10949 / :10922**.

### §2.2 — 🆕 RULE: unreachable code can be deleted; dominated code cannot

I wrote that `DARKBLOOM_INVERSE_SCATTER` was "provably unreachable". It is not.
`SwitchLayers.swift:64` **is** reachable; what kills it is the early return at `SL:285`, inside
`gatherSort`, taken because the fused counting-sort path at `:284` always succeeds at prefill
`n = 4096`. Release **either** dominator and `inverse_permutation_scatter_u32_v1` fires 76×
(fern's arms `f` and `g`).

The distinction is not pedantic and I am adopting it as a rule:

> **Unreachable code can be deleted. Dominated code cannot.** A dominated path is live under a
> legal environment; deleting it changes behaviour for some admissible configuration. #558's
> claim that the scatter path costs 4,186 editable bytes still stands, but the bytes are not
> free to reclaim.

### §2.3 — `DARKBLOOM_FUSED_RESIDUAL_RMS` is live at exactly 1 of 408 decode dispatches

It fires in the dense layer 0 and is masked in all 39 sparse layers, which route through
`lagunaResidualRMSNormRouter` instead. It was not in my §7.2 table at all.

> **Generalisation, now doctrine:** counting a gate's *read sites*, or even counting how many
> distinct kernels its name appears in, does not measure its weight. **Only the steady-state
> dispatch interval measures it.** Every static gate census in this repository — mine included
> — is a list of candidates, never a list of magnitudes.

### §2.4 — A7: `predicted_gain < 0` for all seven

Fern's ranking rule was `predicted_gain = occupancy_deficit_ms − (added_dispatches × 2.3403 µs)`.
Against a 512-token prefill plus 128 decode steps (M4 reference 8.247 ms/decode step ⇒ 1055.6 ms
decode, 547.19 ms prefill):

| gate family | added dispatches | tax | as % of the affected phase | score effect |
|---|---:|---:|---:|---:|
| `FUSED_SLIDING_ATTN` off | 11,520 | 26.96 ms | 2.554 % of decode | **−1.92 %** |
| `FUSED_RESIDUAL_RMS_ROUTER` off | 4,992 | 11.68 ms | — | **−0.83 %** |
| `FUSED_FULL_ATTN` off | 3,840 | 8.99 ms | — | **−0.64 %** |
| `ROUTE_COUNTING_SORT` off | 228 | 0.534 ms | — | small negative |
| `INVERSE_SCATTER` / scatter family | 190 | 0.445 ms | — | small negative |

And the occupancy deficit on the other side of the ledger is **structurally ≤ 0** for the router
and both route-sort gates — the router's OFF-path RMS collapses to **one threadgroup**. For the
two attention gates the deficit is bounded above by attention's share of decode bytes (sliding
2.6–5.3 %, full 1.1–2.2 %), which is below the tax; and the OFF path additionally re-reads the
same KV, adds a qk-norm pass, and materialises two `gg2_copy` buffers.

**⇒ Turning any of the seven off is a loss. The family is closed.** Note that per Rule 82b
nothing here was ranked off a `SPLIT=1` label.

### §2.5 — `DARKBLOOM_FUSED_RESIDUAL_RMS_ROUTER` is not an isolate

Turning it off also swaps the routed decode GEMM from
`..._packed_top8keys_r1_bf16_v2` (2048 threadgroups) to `..._packed_bf16_v1` (1024
threadgroups). Any A/B on this gate is therefore **confounded with a change of GEMM variant**,
which matters directly for frieren's #597 and is recorded here so nobody prices the two
together.

---

## §3 — 🔴 THE 1,671,168-BYTE TRACER QUOTA IS RETRACTED

`research/advisor-r104-the-receipt-is-the-instrument.md` §4 and tanjiro's #572 write-up both
carried a "1,671,168-byte tracer quota", and #586 quoted "4.6 % of the quota" as a headroom
argument. **There is no such quota.** The figure is a coincidence of two identical traces
happening to reach the same size.

The real limit is the **unflushed final 4 KiB page**, which loses roughly the last 25 rows of
every trace. That single artefact is **the sole cause of every spurious ±1 dispatch-count
difference** we have chased across three rounds.

Every claim of the form "arm X has one more/fewer dispatch than base" that rested on a
trailing-row difference must be re-checked against a flushed trace. Fern's arm comparisons
already are.

---

## §4 — THE DECODE STEP, MEASURED: 25 FAMILIES, 408 DISPATCHES, HALF OF THEM UNDER-OCCUPIED

`research/artifacts/fern-r105c/dispatch-summary.json` records the grid and threadgroup geometry
of every dispatch in the steady decode step. The step is stable: the last three marker
intervals are **408, 408, 408** (the first two, 1759 and 528, are prefill and warm-up).

Derived by the advisor from that artifact — **to be independently re-derived under 105-D, not
taken on trust:**

| n/step | TGs | thr/TG | sg/TG | TG/core @40 | family |
|---:|---:|---:|---:|---:|---|
| 41 | **1** | 512 | 16 | **0.03** | `rmsbfloat16` (generic MLX RMSNorm) |
| 39 | **1** | 256 | 8 | **0.03** | `laguna_prefill_router_tournament_ordinal_norm_active64_v2` |
| 39 | 32 | 512 | 16 | 0.80 | `laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf1` |
| 39 | 2048 | 64 | 2 | 51.20 | `laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2` |
| 39 | 512 | 288 | 9 | 12.80 | `laguna_routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6` |
| 39 | 256 | 64 | 2 | 6.40 | `laguna_shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1` |
| 30 | 5120 | 64 | 2 | 128.00 | `laguna_decode_nvfp4_qkv_h64_r1_v1_lm1_pw1_se1_sd1` |
| 30 | **8** | 64 | 2 | **0.20** | `laguna_gate_sp_h64_v1` |
| 30 | 256 | 64 | 2 | 6.40 | `laguna_oproj_act_h64_v1_lm1_pw1_sc1_se1` |
| 30 | 32 | 1024 | 32 | 0.80 | `laguna_sliding_fused_attn_ring_v1` |
| 10 | 4096 | 64 | 2 | 102.40 | `laguna_decode_nvfp4_qkv_h48_r1_v1_lm1_pw1_se1_sd1` |
| 10 | 24 | 1024 | 32 | 0.60 | `laguna_full_fused_attn_grow_v1` |
| 10 | **6** | 64 | 2 | **0.15** | `laguna_gate_sp_h48_v1` |
| 10 | 256 | 64 | 2 | 6.40 | `laguna_oproj_act_h48_v1_lm1_pw1_sc1_se1` |
| 2 | 49 | 1024 | 32 | 1.23 | `gather_frontbfloat16_int32_int_2` |
| 1 | 3136 | 256 | 8 | 78.40 | `laguna_lmhead_exact_fused_int5_sparse_refine_v1` |
| 1 | 6272 | 512 | 16 | 156.80 | `laguna_lmhead_int5_base_coarse_delta_bf16_v1` |
| 1 | 128 | 512 | 16 | 3.20 | `laguna_dense_gate_up_swiglu_bf16_v1` |
| 1 | 128 | 128 | 4 | 3.20 | `laguna_dense_down_residual_bf16_v1` |
| 1 | 128 | 224 | 7 | 3.20 | `laguna_lmhead_coarse_argmax_stage1_v5` |
| 1 | 49 | 1024 | 32 | 1.23 | `vn_copybfloat16float32` |
| 1 | **1** | 1024 | 32 | **0.03** | `argmax_bfloat16` |
| 1 | **1** | 512 | 16 | **0.03** | `laguna_decode_embedding_rope_atlas_bf16_2048_v2` |
| 1 | **1** | 512 | 16 | **0.03** | `laguna_residual_rms_bf16_2048_v1` |
| 1 | **1** | **32** | 1 | **0.03** | `laguna_lmhead_exact_winner_bf16_midpoint_threshold_v1` |

**Advisor-derived headlines (unverified, deliberately falsifiable):**

- **84 of 408 decode dispatches (20.6 %) run on exactly ONE threadgroup.**
- **203 of 408 (49.8 %) run at fewer than one threadgroup per M5 core.**
- ≈ **327,395 threadgroup launches per decode step**, but spread over 25 serially dependent
  families, half of which cannot fill the machine once.
- The generic `rmsbfloat16` fires **41× per step on a single threadgroup**, to normalise a
  single 2048-wide row. At Rule 65's 2.3403 µs/dispatch that is **95.9 µs/step = 1.46 % of
  `cs`** in launch tax alone.
- A kernel named `laguna_**prefill**_router_tournament_…` fires **39× per decode step**.
  Either the name is a misnomer or decode is taking a prefill path;
  `DARKBLOOM_DECODE_ROUTER_TOURNAMENT` (`LRM:9532`) exists separately from
  `DARKBLOOM_PREFILL_ROUTER_TOURNAMENT` (`LRM:10211`).

### §4.1 — Why this is not simply "the machine is idle, go fill it"

Two guards, both already in the record, and any 105-D proposal must clear both:

1. **PR #196's staircase.** `T(K) = a + b·⌈K/C⌉` with `a = 1.661`, `b = 7.408`, **C = 40**,
   3 TGs/core. A dispatch whose threadgroups fit inside one wave pays nothing for its idle
   slots. Both attention families (32 and 24 TGs) are single-wave on ranked M5. "Idle slots
   below C cost time" is separately closed at `RESEARCH_ARCHIVE_through-round-91.md:6288`.
2. **408 × 2.3403 µs = 955 µs/step** against a step of T ≈ 4141 µs/step is 23 %, which is almost
   certainly *not* additive: #158 measured the per-dispatch coefficient of the step-boundary gap
   as **NULL**, with a net inter-dispatch total of ≈37 µs/step and a gap of ~265 ± 20 µs that
   scales *with* busy time. Rule 65's 2.3403 µs is a **marginal** price, not an occupancy tax.

The live distinction — and the only reason 105-D is worth running — is that a **1-threadgroup**
dispatch is not an idle-slot tail. It is **serialisation of work**: one threadgroup's latency
sits directly in the dependency chain. PR #196's closure does not reach it. Whether that
serialisation is measurable, and whether it can be removed by anything that is not already a
standing hard negative, is exactly what 105-D must decide — with **zero receipts**.

### §4.2 — 🔴 The §9a discipline applies in advance

`advisor-r104-…md` §9a already killed "the 31.28 ms unattributed prefill pool" — it did not
exist. **An unattributed pool is not a lever.** If 105-D finds a gap between bytes-implied time
and wall time, that gap earns a name and a mechanism or it earns nothing.

---

## §5 — TWO PROBES THAT PASSED WHILE THE THING THEY PROBED WAS BROKEN

These arrived independently in the same round from two students and they say the same thing.

### §5.1 — Tanjiro's D6: the `_ws_1_wl_1` name test does not detect a degraded loader

My 105-A brief told tanjiro to confirm the widened device load survived BN=128 by checking that
the emitted kernel name still ended in `_ws_1_wl_1`. He showed the test is **worthless at
BN=128**: `kSrcBytes` goes 16 → 32, which makes `kWideLoadShapeOk` and `kWideLoad8ShapeOk`
statically false, **yet `darkbloom_stage_wide_load_ok` still returns true**, so the name is
unchanged. **My test would have PASSED while the loader was silently degraded.** His repair is
`WideSrc32` — two 16 B vector loads, bit-exact because `bj == 0`.

This is the **same failure mode as #138's Finding D** (BK=128 silently disabling the widened
device load, `RESEARCH_ARCHIVE:6486-6510`), now shown to recur on the **N** axis and to be
invisible to the obvious probe. Recorded together:

> **Doctrine:** the emitted kernel *name* is a record of what the host asked for, not of what the
> device kernel compiled to. Never use a name string as evidence that a template specialisation
> took the intended path. Verify against emitted AIR/MSL, or against a byte-identical-AIR
> control at a configuration where the feature is known inert.

Tanjiro's own inertness proof is the positive form of this: both of his repairs were shown inert
at BN=64 by **byte-identical AIR (39,392 B)**, not by a name.

### §5.2 — Fern's tracer retraction is the same lesson at the instrument level

The tracer reported a stable byte count that we read as a quota. It was an artefact of an
unflushed page. See §3.

---

## §6 — WHAT 105-C DOES **NOT** LICENCE

Fern's §8.4 follow-up 1 — "one head per threadgroup" for the fused attention kernels — is a
**standing hard negative** and was killed in the acceptance of #598. It is *attention head-axis
repartition*, closed three independent ways:

- `RESEARCH_ARCHIVE_through-round-91.md:6256-6262` — integer-wave arithmetic **and** a byte
  argument. Doubling the grid gives 64/80 = 80 % and 48/60 = 80 %, **exactly the shipped
  efficiencies on both 20 and 40 cores**, so the quantization gain is identically zero; and the
  paired heads share the staged `tg_k`/`tg_v` planes (`kv_head = head0 / gqa`), so the split
  **doubles K/V read traffic**.
- `:4894-4896` — PR #103 **measured** 1-head/TG as bitwise identical and **+20.1 % slower**.
- PR #196 — the C = 40 staircase, above.

Her follow-ups 2 and 3 survive and are folded into 105-D §A5. Her follow-up 4
(retire-or-document `DARKBLOOM_INVERSE_SCATTER`) is accepted as **documentation only** — see
§2.2; a dominated path is not free to delete and must never be receipted.

---

## §7 — TOOLING DEFECT #527, EXTENDED

Fern's §1.5 reported that she could not satisfy the 105-C stopping rule because it required her
to post a PR comment, and **the student role has no PR-comment tool at all** — only
`submit_experiment_result` and `respond_to_human_issue`, the latter of which returns HTTP 403.
The obligation was unsatisfiable. That was my error.

> **Standing constraint, extended:** students cannot comment on PRs, cannot comment on each
> other's PRs, and cannot use `get_prs`. Every relay between students goes through the advisor,
> and **no brief may contain a reporting obligation that requires a tool the student does not
> have.** Everything must be satisfiable with `submit_experiment_result` plus files on the
> branch.

---

## §8 — PROVENANCE

- Fern, PR #598, `research/fern-r105c-gate-surface-masking-audit.md` (959 lines),
  `research/artifacts/fern-r105c/{dispatch-summary.json,gate-classification.{csv,json}}`,
  scripts `research/fern_r105c_*`. W&B run `xxko1538`. Method: MLX `device.cpp` dispatch tracer
  applied at `cfb418a` and reverted at `dd3d2f9`; 10 arms on Apple M4 Pro (20 cores, gen 16).
  No decode dial was perturbed, so nothing in it confounds #597 or #584.
- Tanjiro, PR #592, `research/maple-tanjiro-r105a-afrag-ntile-reuse.md` §D6, §2.
- Advisor derivations in §4 computed directly from `dispatch-summary.json`
  (`arms.a_base.steady_step_profile`), 25 families summing to 408.
