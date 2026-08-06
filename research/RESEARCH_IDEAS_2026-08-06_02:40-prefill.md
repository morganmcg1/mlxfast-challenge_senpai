# Prefill Strategy Under M5-Blindness — 2026-08-06 02:40 UTC

Scope: research/strategy only; no code changed. Frontier `ab1f9a13`. Exchange
rates (INFERRED from pinned calibration): 1 ms prefill = 0.371% of score;
MDE 0.278% ⇒ a prefill win must clear ~0.75 ms ≈ 3σ_dS (σ_dS = 0.254 ms,
MEASURED, §0.1 noise model). Candidate prefill ≈ 97.95 ms; unexplained
remainder 31.28 ms (subtraction leftover — upper bound, not a mechanism).
Evidence tags: **M** = measured (receipt/census), **I** = inferred
(arithmetic from M), **A** = assumed (unverified prior).

## 1. The measurement problem, ranked

M4 Pro hosts probe GPU gen 16 and fail the NAX gate
(`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp:913-931`:
macOS ≥ 26.2 AND gen ≥ 17/18; hardware lacks the ISA, so no bypass exists —
`_nax` sources compile locally but never execute). 94.2% of M4 prefill
wall-clock sits in NAX-divergent kernels (M, M4 profile). So M4 prefill
*timing* is inadmissible; the transfer law (§0.9.2) says **counts transfer
exactly, boundary timing does not, not even sign**. Channels for M5-valid
prefill evidence, best first:

| # | Channel | Cost | Fidelity | Notes |
|---|---------|------|----------|-------|
| 1 | Receipt free-riding: read cand_pre µs/tok + `ns` on every submission, incl. rejected-but-correct | free | σ ≈ 0.18–0.26 ms (M) | Never read officialScore (baseline arm sd 1.93% dominates it) |
| 2 | Two-axis bundling: one ticket publishes cand_pre and cand_dec separately | 1 ticket | same | Gather-GEMM is prefill-only (#57), QMV decode-only ⇒ axis-disjoint attribution is clean |
| 3 | Correctness-preserving added-work dose arms (instrument est. #27/#34; 141.13 ms probe receipt precedent) | 1 ticket | marginal cost only | Floor headroom ≈ 106 ms (candidate 97.95 vs 203.7 ms floor I) — any sane probe passes floors and still publishes timings |
| 4 | Analytic pricing vs calibrated in-situ constants: 408.4 GB/s gather-GEMM, 546.2/651.8 GB/s QMV planes, 610 GB/s streaming, 6.77 TFLOP/s in-situ steel, +27.2 µs/added-cb (all M) | free | ±30–50% | §0.9.18: SLC can absorb round trips ⇒ byte prices are upper bounds |
| 5 | Static/census evidence: byte, dispatch, MMA, routing censuses; pipeline-state occupancy; MSL compile checks | free | exact for counts | M4-legal per §0.9.2/§0.9.10 |
| 6 | M4 twin timing (non-NAX kernel family) | free | mechanism sign only, kernel-internal classes | Admissible for kernel-internal efficiency and byte-stream size; never for overhead/boundary/concurrency |
| — | Not viable | — | — | NAX bypass on M4 (hardware); M4-share apportionment of the M5 remainder (2.6× disagreement, R12.12) |

Bundling discipline (I): promotion needs both floors plus beat-best. A prefill
probe that *regresses* r ms dilutes a bundled decode win by 0.371·r % — so
carry a speculative prefill arm on a decode ticket only when the prefill arm
is expected non-regressing; a believed-win prefill mechanism plus a decode
mechanism is the ideal ticket (compounds, separately attributed via per-axis
receipts plus DARKBLOOM kill-switch constants).

The missing instrument: the 31.28 ms remainder has never been decomposed. A
prefill analogue of the decode census — bracket remainder blocks (shared
expert, router+tournament glue, sort/scatter, steel_attention, RMSNorm/RoPE,
dense L40, KV writes) by free byte/dispatch counts priced at channel-4 rates,
then at most one dose receipt on the largest bracket — costs nothing until
the final receipt.

Scheduling note: the ranked channel is currently held by #80 (frieren); any
prefill receipt queues behind it.

## 2. Candidate mechanisms

All are structurally distinct from closed families (staging/prefetch/overlap
#40/#57, SM=16 banding, in-kernel barriers #66, cb-cap #44, attention qkvo
in-situ, M2 host-side gather elision §Ø.6).

| Mech | Site | Central price | % score | M4 role | Falsifier |
|------|------|--------------|---------|---------|-----------|
| C. Fused split-K port to NAX steel (queue item 11) | recipe `quantized.cpp:852-893` (`splitk_fused_enabled` :858); target `matmul.cpp:689` (`steel_gemm_splitk_axpby_nax`), fp32 `C_split` :736-738, selection :988-991 | 1.18–1.32 ms (I: 0.72 GB ÷ 610/546 GB/s) minus overlap discount | +0.44–0.49% pre-discount | **Unique: mechanism locally testable** — port to non-NAX twin first (M4 splitk = 33.04 ms M); equivalence-testable | M4 twin + equivalence, then 1 receipt |
| A. Kernel-side gather elision | `fp_quantized_nax.h:1568` (`fp_gather_qmm_rhs_expert_nax`); A-loads read a host-gathered copy built by `SwitchLayers.swift:309/345`; landmine: `quantized.cpp:2212` rhs path ignores `lhs_indices` | 2.15 ms (I: 1.309 GB ÷ 610 GB/s; range 0.75–3.2) | +0.28–1.19%, central +0.80% | correctness + byte census only | census (free) → M4 twin correctness → 1 receipt |
| B. Row-concat family: `DARKBLOOM_FUSED_QKV` flip; optionally extend `[gate;up]` bank to prefill | flag `LagunaRuntimeModel.swift:107-114` (default OFF; provenance = predecessor's *local paired* benchmark, i.e., M4-class A); bit-exact class documented :100-105; shared-expert prefill deliberately on separate banks :115-122 | 0.17 ms dispatch removal (I: 78 × 2.18 µs) + unknown tile gain | +0.06–0.30% | none (M5 tile behavior unknowable locally) | zero-code env flip; 1 receipt |
| D. LPT expert-launch permutation | `fp_quantized_nax.h:1673-1679`: `expert = tid.y·(experts/expert_groups)+expert_slot` (identity map); grid `quantized.cpp:1920-1924` | 0.3–1.5 ms (A: makespan-tail bound under CV 1.80, top-32/256 = 54.7% of rows M) | +0.11–0.56% | correctness; launch-order sign may differ | 1 receipt; no prior proposal (grep-verified) |
| 0. Remainder bracket census | §1 channel 5+4 | n/a (instrument) | de-risks all of the above | fully M4-legal | free until 1 optional dose receipt |

**C (recommended).** The `qmm_t_splitk_fused` recipe already ships bit-identical
on the quantized path: one dispatch replays per-partition loader/MMA order,
emulates partition-store rounding in-register, chains partitions in fp32 in
reduce order — no intermediate buffer, no second dispatch
(`quantized.cpp:852-857`). The NAX steel split-K still allocates a fp32
`C_split` (`matmul.cpp:736-738`) and a separate reduce; prefill split-K sites
are o_proj/g_proj/router (per PREFILL_NAX_ANALYSIS.md C4; A until census
confirms). Honest caveat: o_proj sits in the attention block audited at 117%
of its naive ceiling (M, dS₃ = 22.21 ms), so latency-hiding may shrink the
realized win below the byte price; only the receipt decides. But the port is
the sole prefill mechanism whose kernel-internal correctness *and* mechanism
sign can be established on the M4 twin before spending a ticket.

**A** is the largest honest price but M5-blind on timing, adjacent to the
§Ø.6 landmine (must be a new kernel parameter that reads A rows via
`lhs_indices`; never a host-side flag), and its byte price is an upper bound
if SLC absorbs the 16 MiB/layer round trip (§0.9.18). It is the natural
second experiment once C's receipt calibrates how byte prices convert on M5.

**B** is the cheapest receipt (env flip, zero bytes of diff) but the same
117% audit caps its plausible gain; likely sub-MDE alone. Worth carrying only
as the non-regressing second axis of a decode ticket, never standalone.

**D** is genuinely new and bit-exact (experts write disjoint row segments;
per-row arithmetic order unchanged), but its price is assumed and
scheduler-dependent — a hypothesis to hold until a receipt slot is cheap.

## 3. Honest null and recommendation

Prefill is *workable but slow*: one informative M5 number per ticket, each
needing ≥0.75 ms to clear noise, behind #80 in the queue. The binding
capability gap is an M5/M5-Max host running `./benchmark.sh --local-iterate`
— that single unblock collapses channels 1–6 into ordinary local iteration
and would also let the 31.28 ms remainder be profiled directly rather than
bracketed. Name it to the operators every round until it exists.

**Single recommendation:** assign **mechanism C — bit-exact fused split-K on
the NAX steel path** — as the next prefill experiment, staged so the ticket
is spent only on a survivor: (1) free byte/dispatch census confirming which
prefill GEMMs take the split-K branch and the C_split byte volume; (2) port
the shipped fused recipe to the *non-NAX* twin, prove upstream equivalence
and M4-twin mechanism sign locally; (3) apply the identical port to
`steel_gemm_splitk_axpby_nax`, compile-check, and spend one receipt (ideally
bundled as the prefill axis of the round's decode candidate). Expected
+0.44–0.49% pre-discount; abort before the ticket if the census shows <0.4 GB
of C_split traffic or the M4 twin shows no win. Fold the §1 remainder-bracket
census into the same assignment as its free first work item.
