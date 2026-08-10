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
argument. **There is no such quota.**

The real limit is the **unflushed final 4 KiB page** of a `static std::ofstream`, which loses
roughly the last 25 rows of every trace. That single artefact is **the sole cause of every
spurious ±1 dispatch-count difference** we have chased across three rounds.

**The arithmetic settles it.** A truncation that drops the final partial page leaves a file of
exactly `floor(total/4096) × 4096` bytes — always a whole number of pages. And

```
1,671,168 / 4096 = 408.0    remainder 0
```

`1,671,168 B` is **exactly 408 pages**. A hard quota has no reason to land on a page boundary;
a dropped-final-partial-page truncation *guarantees* it. (The 408 here is page count and has
nothing to do with the 408 decode dispatches of §4 — the collision is a coincidence, and I note
it only so nobody builds on it.)

**Priority where it is due: tanjiro named this a round before it was measured.** #586 §1.1
attributes the round-103 artefact to "an unflushed `static std::ofstream` in that tracer" —
the correct mechanism, published in round 104. Fern's #598 §8.1 supplies the measurement. What
did *not* survive in #586 is the clause that followed it, "77,461 bytes = 4.6 % of that limit":
there is no limit, so there is nothing to be a percentage of.

**Three standing consequences.**

1. **Never treat a ±1 dispatch-count difference between two dumps as signal** unless both
   traces are flushed. Every claim of the form "arm X has one more/fewer dispatch than base"
   that rested on a trailing-row difference must be re-checked. Fern's arm comparisons already
   are.
2. **No headroom argument of the form "we are only at X % of the tracer's capacity" is
   admissible**, anywhere, ever. It was always meaningless; it is now demonstrably so.
3. **Write traces to `stderr`, which is unbuffered.** This is why tanjiro's #586 steel census
   was in fact safe — not because 77,461 B is small, but because `stderr` cannot be truncated
   this way. A tracer that writes to a `std::ofstream` must be assumed to be dropping its tail
   until a flush is shown.

Correction blocks have been published at the four inherited citation sites:
`research/advisor-r104-the-receipt-is-the-instrument.md`,
`research/maple-tanjiro-r103b-kernel-text-differential.md` (two sites),
`research/maple-frieren-r103a-missing-microseconds.md`, and
`research/maple-tanjiro-r104c-prefill-steel-census.md`.

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

---

### 🔴🔴 §4.0 — ADJUDICATION BY 105-D (PR #603, MERGED): THREE OF THE FIVE HEADLINES ABOVE ARE WRONG

Everything above the rule was written **before** the census existed and was published as
deliberately falsifiable. maple-fern's 105-D censused the exact step — 408 dispatches, 25
families, 327,395 TG-launches, 30.8 M threads, plus a **byte** census the original table lacks —
and returned **OUTCOME N-1: the bounded under-occupancy pool does not exist**, together with
three N-3 contradictions. Zero receipts, zero submitted bytes. Report:
`research/maple-fern-r105d-decode-dispatch-census.md`; artifacts `research/artifacts/fern-r105d/`;
W&B `1k7a3iv6`. **Read the verdicts below before quoting anything in §4 or §4.1.**

| headline | verdict |
|---|---|
| H1 — 84/408 single-TG | ✅ **TRUE**, no qualification, re-derived from the traces |
| H2 — 203/408 sub-C40 | ✅ **TRUE** exactly at C = 40; only **124 at C = 20** ⇒ under-occupancy is *more* severe on the ranked machine |
| H3 — 327,395 TG-launches/step | ✅ **TRUE**, reproduced to the digit |
| H4 — 41 `rmsbfloat16` = 95.9 µs/step launch tax | 🔴 **WITHDRAWN — arithmetic true, causally false; overstates by 21.7×** |
| H5 — `prefill_router_tournament` misnomer suggests misrouting | 🔴 **DOWNGRADED to a naming fact with zero lever** |

**🔴 H4 is withdrawn.** I applied Rule 65's 2.3403 µs — an **addition** price — in the
**removal** direction. `research/CURRENT_RESEARCH_STATE.md:1064-1065` already says verbatim:
*"So 'add a dispatch, pay 2.34 µs' holds; 'remove a dispatch, gain 2.34 µs' is **refuted**."*
Worse, the family had already been measured **by fern herself** in PR #483
(`research/maple-fern-r91-input-norm-fusion-price.md:14-24,36`): adding a redundant input-RMSNorm
is **+80 dispatches/step (+19.7 %)** for **+8.61 µs/step busy, CI [−17.71, +35.02]** ⇒
**0.108 µs/dispatch = 4.6 % of 2.3403**, family status "**terminal — the family is dead**",
ceiling ≤ 35.02 µs/step = 0.535 % of score, ≈0.13 % after the ×0.25 M5 transfer (W&B `ubjfsywa`).
🆕 **Rule: never price a removal with an addition constant.**

**🔴 H5 is a naming fact only.** Decode and prefill tournaments are **separate gates** —
`LagunaRuntimeModel.swift:9532` (`DARKBLOOM_DECODE_ROUTER_TOURNAMENT`) vs `:10211`
(`DARKBLOOM_PREFILL_ROUTER_TOURNAMENT`) — that dispatch a **shared** Metal function whose
declarations at `:10113, :10122, :10131, :10140` all carry the `laguna_prefill_router_tournament_*`
name. There is no misrouting. And PR #218
(`research/maple-fern-decode-marginal-cost-ledger.md:55`) prices `T0a_router_top8` at
**0.00 ± 0.12 µs/call → 0 µs/step, E = 0.00**, absorbing 15.33 copy-sets (~2.85 ms); `:127` records
that #204 deleted the family outright for **−0.9 ± 12.1 µs**.

#### 🆕 §4.0a — THE REPLACEMENT FINDING: OCCUPANCY IS ANTI-CORRELATED WITH COST

105-D §2.3 priced every dispatch in **bytes** (total **1,671,402,432 B = 1671.40 MB/step**;
99.883 % of it the 15 r101 spine families, 0.1172 % the 10 newly-priced tail families):

| occupancy class | dispatches | % of 408 | bytes/step | % of bytes | label µs (82b shape-only) | % of label |
|---|---:|---:|---:|---:|---:|---:|
| `SINGLE_TG` | 84 | 20.59 % | 600,512 | **0.0359 %** | 327.4 | 3.89 % |
| `SUB_C40` (all) | 203 | 49.75 % | 137,832,896 | **8.2465 %** | 1834.1 | 21.77 % |
| `AT_OR_ABOVE_C40` | 205 | 50.25 % | 1,533,569,536 | **91.7535 %** | 6589.6 | 78.23 % |

Per dispatch, a ≥C40 dispatch is **~3.6× costlier in label seconds and ~255× costlier in bytes**.
Fern's sentence is the correct generalisation and I adopt it verbatim as doctrine:

> *The under-occupied dispatches look bad on an occupancy metric precisely because they have
> almost nothing to do.*

🆕 **Dispatch count is not a cost proxy; bytes are. Lead every future decode census with bytes.**
The real elasticity lives in the four #218 spine families —
`T0b_qkv` 1276 µs/step E = 0.74; `T2c_routed_qmv` 1184 µs E = 0.75; `T2d_down_residual` 555 µs
E = 0.62; `T1c_lmhead` 474 µs E = 1.11 (`maple-fern-decode-marginal-cost-ledger.md:49-52`) —
together **3489 µs/step ≈ 42.6 %** of the step, all classified `SATURATING` in this census.

#### 🆕 §4.0b — THE DECODE ROOFLINE: THE STEP IS MEMORY-BOUND AT 66 %

| row | value |
|---|---|
| Step bytes | 1,671,402,432 B = 1671.40 MB |
| M5 measured DRAM BW (Rule 80) | 610.0 GB/s |
| **M5 DRAM floor** | **2740.00 µs** |
| M5 ranked decode step | 4141.5 µs |
| **DRAM floor as % of step** | **66.16 %** |
| Achieved BW at ranked step | 403.6 GB/s = **66.2 % of peak** |
| Unattributed residual | 1401.50 µs = 21.341 % of score |
| Single-TG class DRAM floor | **0.98 µs** |

This **refutes** the framing of `CURRENT_RESEARCH_STATE.md` round-105 banner item 3 as originally
written ("a serialisation problem, not a bandwidth problem"), which is now retracted and replaced
there. **Decode is memory-bound at the same knee as prefill**
(`research/advisor-r105-the-routed-gather-gemm-is-memory-bound.md`). The 1401.50 µs remainder is
a **subtraction residual, not a pool** — §4.2's discipline, applied to my own number
(`RESEARCH_ARCHIVE_through-round-91.md:6785-6786`). The alternative, unmeasured
geometry-corrected 686.2 GB/s constant would move the floor to 58.8 % and *grow* the residual
without making it a lever.

#### 🆕 §4.0c — THE 955 µs DISPATCH TAX IS OVERLAPPED, NOT ADDITIVE

Nominal 408 × 2.3403 = **954.842 µs/step = 14.54 % of `cs`**. Four independent lines, in
decreasing strength:

1. **Conservation (decisive, M4-direct).** r93-C (PR #498) measured the **production**
   inter-dispatch gap at **302 µs/step**, against **1261 µs/step** under `SPLIT=1`. A 955 µs tax
   cannot fit in a 302 µs hole ⇒ **≥ 68.4 % must be overlapped**. Pro-rating the single-TG share:
   196.585 × (302/955) = **62.2 µs = 0.947 % of `cs`**.
2. **Absorption capacity.** r93-A: this M4 host absorbs the first **~480 added dispatches free**;
   production is 408, *inside* that region.
3. **The gap does not scale with count.** PR #158: gap 265 ± 20 µs, per-dispatch coefficient
   **−0.12 ± 0.22 µs — NULL**; net inter-dispatch residue ≈ 37 µs/step.
4. *(weakest, and correctly flagged as such by fern)* **Ranked hardware.** #527 removed 78
   dispatches and got **+0.639 ms slower**; PR #502 / Rule 53 closed the step with a 24-label
   ledger to **+0.3 µs (+0.004 %)** over 406/406 dispatches. But `CURRENT_RESEARCH_STATE.md:2496`
   marks the prefill→decode generalisation of Rule 68 "suspended, not settled", and
   `advisor-r104-the-receipt-is-the-instrument.md` records #527 as confounded by tooling defect
   #527. Lines 1–3 are sufficient without it.

#### 🆕 §4.0d — RANKED MECHANISM LEDGER (bar = +0.5 % of `cs` = 32.8 µs/step; 1 % = 65.67 µs/step)

| # | mechanism | nominal | best-supported bound | verdict |
|---|---|---|---|---|
| **M1** | fuse the 41 input RMSNorms into the QKV prologue | 95.95 µs (1.461 %) | **≤ 35.02 µs = 0.533 %** (95 % UB, #483); ≈0.13 % after transfer | **NO-GO — closed by #483** |
| **M2** | widen/batch the 39 router tournaments | 91.27 µs (1.390 %) | **0.00 ± 0.12 µs/call** (#218), E = 0.00 | **NO-GO — bounded at zero** |
| **M3** | eliminate/merge all 84 single-TG dispatches | 196.59 µs (2.993 %) | conservation cap 62.2 µs (0.947 %); **measured elasticity 84 × 0.108 = 9.1 µs = 0.138 %** | **NO-GO — 3.6× below bar** |
| **M4** | attention head-axis repartition / 1-head-per-TG | — | — | **OUT OF SCOPE** — closed three ways (`ARCHIVE:6256-6262`, `:4894-4896` PR #103 bitwise-identical but **+20.1 % slower**, PR #196, #205) |
| **M5** | reduce **bytes** in the 205 ≥C40 dispatches | — | holds **91.75 % of bytes**, 78.23 % of label seconds | **not an occupancy lever** — the real surface, but it overlaps live dials in #584/#592/#597 and **needs advisor coordination before anyone opens it** |

Widening the tournament *adds* threadgroups at PR #196's per-TG fixed cost `f = 3.130 µs`, so M2
is bounded above by **zero**. **Nothing clears +0.5 %.** The best honest headline number in the
whole family is **0.138 % of `cs`**.

🔴 **Consequence for the hard-negative list:** fusing the 41 decode input RMSNorms, widening or
batching the decode router tournament, eliminating or merging the 84 single-TG decode dispatches,
any decode "occupancy pool" or "launch tax" argument priced with Rule 65's 2.3403 µs in the
removal direction, and quoting `waves × b` as a cost model are **all now hard negatives. Do not
re-propose.**

#### 🆕 §4.0e — SELF-FALSIFICATION: PR #196'S STAIRCASE OVER-PREDICTS THE STEP BY 15.2×

Summing `T(K) = 1.661 + 7.408·⌈K/40⌉` over all 408 dispatches predicts **63,016 µs** against a
measured M5 decode step of **4141.5 µs**. `b = 7.408 µs/wave` was calibrated on **full-attention
1024-thread, 32-simdgroup** threadgroups; applied to a **64-thread NVFP4 GEMV** TG it over-charges
~16×, and **8 distinct threadgroup geometries** are in use in this step.

> 🆕 **Rule: `waves × b` is not a cost model.** Wave counts are a shape statistic. Multiplying
> them by any single per-wave constant mis-prices the step unless every wave is the geometry that
> constant was calibrated on.

This falsifies **guard 1 of §4.1 below as written**. §4.1 guard 1 is retained only as the
*qualitative* statement that a dispatch fitting inside one wave pays nothing extra for its idle
slots; its arithmetic must never be summed across families.

#### 🆕 §4.0f — A STANDING AMBIGUITY, NOT RESOLVED

The residency model `R = floor(96 / simdgroups_per_TG)` is validated at 1024 thr/TG
(PR #196 ⇒ 3 TG/core) and 128 thr/TG (PR #138's repaired probe ⇒ 24 TG/core) — both = 96 resident
simdgroups/core. A **hard-cap** model (24 TG/core regardless) fits #138 and is **refuted by #196**.
**At 64 threads/TG the two disagree — 48 vs 24 — and nothing in the programme distinguishes them**,
while 64-thread TGs are the decode step's dominant geometry. 105-D's CSV therefore emits **both**
columns (`waves_resident_C40_R96simd`, `waves_resident_C40_Rcap24`) and instructs that **neither
be quoted**; §4.0c's conservation argument deliberately does not use the residency model at all.
**Measuring the 64-thread/TG residency point is cheap and retires this ambiguity in every
occupancy analysis we hold.** Queued.

#### ⚠ §4.0g — A COINCIDENCE, FLAGGED SO NOBODY BUILDS ON IT

The decode step's **1,671,402,432 B** and the r105-C trace file's **1,671,168 B** stand at a ratio
of 1000.14 — genuinely different numbers from unrelated sources (the r101 byte model
`research/fern_r101_byte_audit.py` vs a file size). This is the **second** spurious collision
around 1,671,168 this round; the first was 408 pages vs 408 dispatches (§3). Treat any third with
suspicion.

#### §4.0h — WHAT WOULD REOPEN ANY OF THIS

(a) a ranked M5 receipt showing that *removing* single-TG dispatches **gains** time — the reverse
of #527's sign — reopens M3; (b) a demonstration that #483's null is a **producer-side** artifact:
its **open sibling arm C** at `CURRENT_RESEARCH_STATE.md:2550-2557` is **not closed**, so the
input-norm family is terminal in only one direction; (c) a 64-thread/TG residency measurement
discriminating R = 48 from R = 24; (d) a revised M5 bandwidth constant.

---

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

> 🔴 **105-D ADJUDICATION OF §4.1 (fern PR #603, merged — see §4.0 above).**
> * **Guard 1 stands, but only inside the attention family.** The claim "a
>   single-wave dispatch pays nothing for its idle slots" survives, because its
>   load-bearing step is the arithmetic fact that 32 < 40 and 24 < 40. The
>   *constants* do not survive extrapolation: summing
>   `T(K) = 1.661 + 7.408·⌈K/40⌉` over all 408 decode dispatches predicts
>   **63,016 µs/step** against a measured **4141.5 µs/step**, a **15.2×**
>   over-prediction, because `b` was fitted on 1024-thread / 32-simdgroup
>   threadgroups and the decode step contains **8 distinct geometries**
>   dominated by 64-thread / 2-simdgroup GEMV threadgroups.
>   **`waves × b` is not a cost model** (§4.0e).
> * **Guard 2 was CONFIRMED, and more strongly than it was stated.** The 955 µs
>   is not merely "probably not additive" — it is **measured ≥ 68.4 %
>   overlapped** (r93-C: production inter-dispatch gap 302 µs/step vs 1261 µs
>   under `SPLIT=1`), the first ~480 added dispatches are **free** (r93-A), and
>   the per-dispatch coefficient is **NULL** (#158). See §4.0c.
> * **The "live distinction" below was the right question and it has now been
>   answered NO.** A 1-threadgroup dispatch *is* structurally different from an
>   idle-slot tail, so §4.1 was right to license 105-D. But the resulting
>   measurement says the difference is worth **0.138 % of `cs`** — 3.6× below
>   the +0.5 % bar — because the 84 single-TG dispatches carry **0.0359 %** of
>   the step's bytes. Occupancy is **anti**-correlated with cost (§4.0a, §4.0d).
>   Do not re-open this paragraph as a licence for a new arm.


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
