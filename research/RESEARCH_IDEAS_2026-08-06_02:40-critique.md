# Skeptical Critique & New Hypotheses — 2026-08-06 02:40 UTC

Independent adversarial review of the MLXFast Laguna programme (fresh-context
subagent; no prior stake in any banked price). Sources: `research/CURRENT_RESEARCH_STATE.md`
(cited by section/line), code sites verified in this checkout, calibration
constants supplied by the advisor (Appendix A). No source edits; report only.

---

## Q1. What the programme is systematically getting wrong

**Diagnosis: prices are manufactured by a multi-stage unit-conversion pipeline
whose regime preconditions are never stored with the number.** Every one of the
audited casualties is a *derived* quantity banked as a *measurement*:

```
bytes ──(rate: assumes byte-boundedness)──> µs ──(fixed elasticity)──> %score
   ▲                                          ▲
   frontier-stale censuses          add-probe ⇒ remove-price (category error)
   M4 evidence ──(assumed transfer class)──> M5 claim
```

Each stage is individually defensible; the failure is composition. The ledger
stores the product and discards the assumptions, so provenance decays until a
receipt refutes the number. The programme's own audits confirm this shape:

- §0.9.13 (state file): **6 of 8 banked prices materially wrong**, with three
  named modes — conversion-step error, dispatch-count romance, and the
  category error of banking an *add-work* coefficient as a *remove-work*
  price (refuted by the #48 receipt: deleting 80 real dispatches moved `ns`
  −0.1488%).
- §0.9.18 (line ~2134): %-of-DRAM-ceiling was read as "recoverable time" when
  it is only an upper bound on byte-boundedness — sliding attention issues
  443 GB/s (170% of M4 ceiling, cache-served) while the table called it "36%
  of ceiling". This invalidated the M4 "recoverable" column (§0.9.11b struck:
  453 µs "recoverable" inside kernels costing ~390 µs/step total on M5).
- §0.9.11b's cross-check was **self-confirming by construction**: scaling all
  rows by one scalar (0.812) preserves sum/residual ratios on any two
  machines; it was read as independent confirmation.
- R12.14 casualties #22–24 (line ~424): a wrong byte census (24.36 vs true
  37.77 MB/step) spawned a fake "1.89× over-delivery law" (retracted RULE 20);
  a plane was priced at its stock width after #35 had already narrowed it
  (frontier staleness — and the advisor publicly overruled the student who
  was right); and 24,164 B was re-attached from fern's #40 deletion estimate
  to the Metal-literal pool (→ RULE 21: a price is a *(number, mechanism)*
  pair).

**Verdict on the pricing methodology itself.** The exchange rates are sound
*as ceilings under explicit preconditions*, and mostly validated: byte→time at
546.2 GB/s is legitimate only for kernels measured ≥~90% of ceiling in situ
(true for qkv/routed_swiglu/down/oproj/lmhead per the decode table, line
~4165; false for gate_sp at 2%, sliding attention (issue-bound), and the
rms/router rows the table itself flags "suspect"). µs→% linearization
(14.862%/ms decode, 0.371%/ms prefill) is conservative and receipt-validated at
small deltas. M4→M5 transfer is defined **only at its two ends** (DRAM traffic
106%, dispatch overhead 1%; §5, line ~2890); the entire middle is unknown and
sign-unstable. The constants are not the problem — **applying a conversion
outside its validated regime and banking the output is.** RULE 4's discount
ladder (byte arms at 0.30–0.50× face) exists but is applied to candidate
pricing, not to closures.

**Survivorship asymmetry (the unaudited half of the ledger).** Optimistic
errors meet ranked receipts and die publicly — that is what the 24-casualty
table is. Pessimistic errors never meet receipts: a family closed with the
*same invalid conversions* stays closed forever. Nobody re-screens closures
whose arguments used since-retracted logic (%-of-ceiling as recoverable time,
the struck M4 column, pre-RULE-14 instruction counting). Concrete Type-II
candidates: `residual_rms_router` (39×6.81 µs, ceiling "60% suspect") and
shared-expert K1 (39×6.24 µs, "73% suspect") were closed as individually
sub-MDE using exactly the per-kernel framing that the programme's own
"residual is diffuse" finding says is the wrong unit — their fusion pool is
D-STRAND (2.040 ms), which remains unowned.

**Live specimen, still wrong today.** R12.13 (line ~398) prices the dense MLP
as "layer 40 of 40". `LagunaConfig.swift:18-19` defines the 8192 dense
intermediate for **layer 0 only**, and the runtime gates the rung on
`layerIdx == 0` (`LagunaRuntimeModel.swift:5920`). The nezuko #9 decode census
sums 1657 MB of the 1794 MB budget with the dense layer absent — the ~100.66
MB gap *is* the dense layer. A 4.51%-of-score item is mislocated in the world
model right now; same class as casualty #22, caught only because this review
cross-read config against ledger.

**Governance observation.** The casualty table is advisor-authored self-audit:
the same author prices, banks, refutes, and writes the post-mortem. Candidate
pricing now has receipts as an adversary; closures have none. This report is
the first adversarial audit of the *closure* side.

**Fixes (cheap, procedural).** (1) Bank prices as 4-tuples: number, mechanism,
regime precondition, and the cheapest test that would refute the precondition.
(2) Any closure whose argument cites a retracted rule gets one funded
re-screen. (3) Censuses must state their frontier SHA (extends RULE 19).
(4) Prose/table contradictions (dense layer) are audit triggers, not typos.

---

## Q2. What has never been tried (avoiding closed families)

1. **Attribution before optimization on prefill.** 31.28 ms of prefill
   (11.60% of score, upper bound) is *unattributed*, and 94.2% of prefill time
   is NAX-divergent so M4 evidence is inadmissible. The in-tree M5 injection
   instrument (protected by the T0 veto) has never been pointed at it. One
   local M5 census converts an opaque pool into 2–3 priced arms. Highest
   information per session available; zero ranked receipts consumed.
2. **Structure-aware MoE dispatch.** Routing statistics are measured (CV 1.80,
   20.26% empty experts, busiest 32 = 54.7% of rows;
   `research/prefill-512-route-histogram.txt`) but never *exploited*. The
   gather-GEMM pads to 1.456× useful rows (453,120 vs 311,296 at the
   `kFragRows=16` floor). Two-regime dispatch (item 15) is the only route
   below that floor and needs exactly one hard argument: bit-exact MMA
   accumulation order for small-n_e experts.
3. **Lossless representation change on the only BF16 matmul.** Precision
   *reduction* is closed (envelope); a **bit-exact re-encode census** of the
   dense-layer weights (distinct BF16 patterns / mantissa occupancy across
   3×[8192,2048]; kernels at `LagunaRuntimeModel.swift:8131,:8228`) has never
   been run. If the tensors were ever dequantized from a quantized source,
   entropy is far below 16 bits/element.
4. **Porting the in-tree bit-identity technique to the branch the M5 takes.**
   A fused, bit-identical split-K replay already ships for the non-NAX path
   (`quantized.cpp:849-893`, env `DARKBLOOM_QMM_SPLITK_FUSED`) — it was never
   ported to `steel_gemm_splitk_axpby_nax` (`matmul.cpp:987-995`), which still
   round-trips fp32 `C_split` (~0.72 GB) plus a reduce dispatch in prefill.
5. **Fusion as the only admissible concurrency.** Encoder/scheduler files are
   *not editable* (verified against `benchmark.json`), so dispatch overlap is
   structurally out of reach — yet the two priced fusion arms (D-FUSE-GATESP,
   D-STRAND) remain unowned while sub-MDE rungs got receipts.
6. **Byte-budget rationality.** Headroom is 33,169 B; T1 dedent (27,192 B,
   byte-identical) is a free enabler. Mechanisms should ship byte-negative via
   pre-registered stacking receipts (§0.5.7) instead of being vetoed for byte
   cost; new files under `Sources/MLXFastModel/` are submittable (directory
   entry), which no arm has used.
7. **Instruction-issue framing for M5.** The ranked host is ~89%
   issue-occupied vs M4 ~74% (state lines 261–262): instruction-count cuts
   transfer >1.0 while byte cuts transfer ~1.06×face×discount. Only #82
   exploits this. The M=8 MMA descriptor (≤+1.66% ceiling, `relaxed_precision`
   caveat) is API-legal and unscreened — a one-day oracle kill-test.

---

## Q3. Ranked next experiments

Constants: 14.862 %/ms (decode), 0.371 %/ms (prefill), MDE 0.278% ⇒ 18.7 µs
decode / 0.75 ms prefill; byte floor ≥27.8 MB/step at RULE-4 0.367× realized.

| # | Experiment | Mechanism & verified site | Price arithmetic | Cheapest falsification | Class |
|---|---|---|---|---|---|
| 1 | **Prefill remainder census** via M5 injection instrument | Bin the 31.28 ms unattributed prefill by kernel family; instrument in-tree (T0-vetoed deletion) | Pool = 31.28 ms × 0.371 = **11.60% upper bound**; census prices it, wins come later | The census *is* the falsifier (one local M5 session, no receipt) | CHEAP screen |
| 2 | **Two-regime expert dispatch** (Block-1 gather-GEMM) | Small-n_e experts leave the 16-row MMA floor; padding 1.456× (453,120/311,296 rows); site: A2 table +14.30 ms in-situ excess (408.4 GB/s, 23.23 vs 34.7 TFLOP/s ceiling) | Recover half the excess: 7.15 ms × 0.371 = **+2.65%**; full = +5.31% | §0.9.21 standalone bitwise oracle on regime-split vs stock across config sweep — kills on first bit mismatch, no weights, M4-legal | EXPENSIVE build, oracle-first |
| 3 | **D-FUSE-GATESP** | Fuse `gate_sp_h64/h48` (40 disp., 213 µs/step, 2% ceiling = pure serialized latency; `LagunaRuntimeModel.swift:4415-4426`) into `oproj_act` (`:4455,:4473`, 95% ceiling) | Face 213 µs × 14.862 = 3.17%; #73 reprice ceiling 2.91%, realistic **+0.5–1.5%** | Oracle bit-compare of fused kernel text; byte cost pre-checked vs 33,169 B headroom (batch with T1 reclaim, 27,192 B) | MODERATE build |
| 4 | **Dense-layer lossless BF16 re-encode** | Census distinct bit patterns in 3×[8192,2048] BF16 (`:8131,:8228`); if mantissa-sparse, bit-exact narrower code + decode-side expand | 100.66 MB/step face = 184 µs = 2.74%; halving bytes ⇒ 50.3 MB = 92 µs face 1.37%, RULE-4 0.367× ⇒ **+0.50%**; also fixes the layer-0/40 ledger error for free | Census script (local, free); if distinct-pattern count ≈ 2^16-dense, family dies same day | CHEAP census → MODERATE build |
| 5 | **Split-K NAX fused port** | Port `DARKBLOOM_QMM_SPLITK_FUSED` replay (`quantized.cpp:849-893`) to NAX branch (`matmul.cpp:987-995`); removes ~0.72 GB fp32 round-trip + reduce dispatches in prefill | 0.72 GB / 546.2 GB/s = 1.32 ms × 0.371 = **+0.49%** + dispatch term; prior estimate +0.53% (unaudited) | Bit-identity already proven in the non-NAX twin; oracle the NAX port; local prefill timing before any receipt | MODERATE build |
| 6 | **D-STRAND barrier audit → 3-kernel strand fusion** | `residual_rms_router`+`router_top8`+shared-K1 chain: 39×(6.81+2.47+6.24) = 605 µs/step; ceilings flagged "suspect" — Type-II re-screen of a closure | Pool 605 µs = 8.99% face; 20% strand saving = 121 µs = **+1.8%**; even 25 µs clears MDE | Free barrier/dependency audit first (pre-registered analytic ceiling per RULE 14); build only if depth shortens | CHEAP audit → MODERATE build |
| 7 | **M=8 MMA descriptor bit-screen** | Decode QMV rows pad M=1→16; M=8 descriptor is API-legal but `relaxed_precision=true` (state line ~4576) | Ceiling **≤+1.66%**; zero if bits move | One-day §0.9.21 oracle sweep; any bit flip = closed with proof | CHEAP screen |

Ordering rationale: #1 buys attribution for the largest unpriced pool at zero
receipt cost; #2 is the largest single mechanism-bearing number on the board;
#3–5 are priced, unowned, bit-exactness-tractable; #6 doubles as the Type-II
closure audit this critique argues is missing; #7 is a one-day kill-test.

---

## Appendix A — Epistemic ledger

**MEASURED** (receipts/instruments): 1794 MB/step decode traffic; decode
dispatch table µs and ceiling %; +14.30 ms Block-1 excess; 31.28 ms prefill
remainder; #48 −0.1488%; δ=1.681 µs/cb; routing histogram; ns 2.556326 vs
crown 2.524190. **INFERRED** (valid conversions, regime-checked): all %score
figures via 14.862/0.371 %/ms; byte faces at 546.2 GB/s only where in-situ
ceiling ≥90%; MDE 0.278% ⇒ 18.7 µs / 27.8 MB floors. **ASSUMED** (flagged,
falsifiable): dense-tensor mantissa sparsity (#4); MMA-order bit-exactness for
small-n_e rows (#2); 20% strand saving (#6); calibration constants supplied by
advisor and consistency-checked against state-file arithmetic, not re-derived
from raw receipts.
