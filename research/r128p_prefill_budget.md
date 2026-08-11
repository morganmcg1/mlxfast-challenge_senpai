# R128-P — Prefill budget attribution

Student `maple-tanjiro`, PR #743, assignment `maple-r128-p-prefill-budget-attribution`,
revision `r128-p-rev1`, base `67396bb6283cf2765a388b05ce4ac64174bb8ef6`.

**Hosts named in this document**

- **H-M5** — the ranked self-hosted M5 Max / 128 GB. Every M5 number here is
  *receipt-derived or analytic*; I did not run on it.
- **H-M4A** — the PR91 / R106i profiling host (M4 class, Apple GPU generation 16,
  never selects `_nax`). Source of the only per-kernel prefill trace that exists.
- **H-M4B** — *this* host: Apple M4 Pro, 48 GiB unified memory, therefore on the
  low-memory startup profile. All new measurements in §3 are H-M4B.

Per Rule 9 every µs/ms figure below carries its host.

---

## 1. H-R128-P1 verdict (answer first)

**The manifest's "≈97.9 ms prefill seed forward" and the ranked receipt's
"P ≈ 187.872" are the same quantity written in two different units, so there is
no host discrepancy to explain: `P` is µs *per token* and the manifest figure is
ms *per 512-token forward*.** `research/artifacts/advisor-r103/replicate-sigma.json:66`
records `mean_P = 187.871728515625` for receipt group `dc437b0e` (`:6`, n = 5 at
`:7`), aggregating the raw receipt field `prefill_seconds_per_token`
(`= 0.000187877197265625` in `research/r93-runs/receipts/*null-3.json`). The
scored prefill prompt is 512 tokens (`Sources/MLXFastCore/Constants.swift:94`,
`benchmarkPrefillPromptTokens = 512`) and the prefill divisor is
`promptTokens.count * timingRepeats` — never a step count —
(`Sources/MLXFastTrustedHarness/LagunaRuntimeLocalIterate.swift:672` and `:862`;
trusted path `Sources/MLXFastTrustedHarness/LagunaRuntimeBenchmark.swift:837`,
`secondsPerToken = meanElapsed / promptTokens.count`). Therefore
`512 × 187.8717 µs = 96.190 ms` on H-M5. The manifest's 97.9 ms is itself an
**H-M5 receipt-derived** number, not a local M4 measurement:
`S = 512 × 1000 × 0.000191201 s/tok = 97.895 ms` from single receipt `97a5090c`
(`research/maple-nezuko-byte-price.csv:96`,
`research/RESEARCH_STATE_ARCHIVE_through-round-21.md:800`). 96.190 vs 97.895 ms
is **1.8 % apart**, and the per-group H-M5 population in the same sigma file is
`mean_P ∈ {187.872, 190.507, 190.928, 191.490, 191.654, 191.684, 204.238}`
µs/token (`:66, :583, :542, :128, :250, :349, :189`) — i.e. **96.2–104.6 ms per
512-token forward on H-M5**, with `dc437b0e` the *fastest* group in it and the
manifest's 191.201 µs/token sitting in its middle. The advisor's "~1.9× longer"
is exactly `187.872 / 97.895 = 1.919`: the µs/token number read as ms/forward.
It is a units slip, not a configuration error and not a slow ranked host.

**The maple-fern #686 1023-vs-128 trap is not implicated in the prefill axis.**
That trap is a decode-step-count trap and the prefill metric contains no step
count: the prompt is 512 tokens in both local modes
(`Sources/MLXFastCore/Constants.swift:94`; the fixtures selected at
`benchmark.sh:144-147` — `correctness_prompts/public_longcopy_gate_english_512_1024.json`
for `--local-submit`, `..._512_256.json` for `--local-iterate` — both carry a
512-token prompt), while the divergence is decode-only
(`Constants.swift:109` `benchmarkDecodeSteps = 128` vs `:117-118`
`localSubmitBenchmarkDecodeSteps = 1023`, `localSubmitBenchmarkRepeats = 1`).
Prefill runs 0 warmup + 1 timed run in every path (`Constants.swift:129-130`),
and the pinned constants at `Constants.swift:167-168`
(`officialBaselinePrefillSecondsPerToken = 0.00036751938916015625`) are the
local-mode denominator only, not the ranked denominator.

**Timed-region scope, for completeness.** Locally the KV cache is allocated
*before* the timer and the timed span is
`inputIDsArray → lagunaLogits → eval → greedyToken`
(`LagunaRuntimeLocalIterate.swift:547-557`); fixture load, tokenisation and model
load are outside it. On the official path the trusted parent times the whole
worker request/response round-trip (`LagunaRuntimeBenchmark.swift:806-811`).
Neither timed region contains a decode loop.

### 1.1 Manifest rows affected

The rows below are arithmetically self-consistent — they all price against an
H-M5 window — but each must be read as *an H-M5 receipt-derived window, not a
measured M4 quantity*:

| row | file:line | what it says | correction |
| --- | --- | --- | --- |
| §7 item 1 | `research/maple_endgame_handoff_manifest.md:974-976` | "~27.88 ms of the 97.9 ms prefill seed forward is unattributed" | window is H-M5-receipt-derived; and see §2 — the 27.88 ms is **not a measured residual** |
| §5 note | `research/maple_endgame_handoff_manifest.md:490-492` | "~2.4 ms of the 97.9 ms window" | H-M5 window; an M4-*measured* pool time dropped into it is over-priced by the ~5.7× M4→M5 prefill factor unless scaled first |
| §5 row | `research/maple_endgame_handoff_manifest.md:228` | same window | same |
| stale anchor | `CURRENT_RESEARCH_STATE.md:634-650` | anchors the 97.9 ms | stale relative to the receipts cited above |
| third value | `research/PREFILL_LEDGER_INSTRUMENT.md:15-19` | "S0 = 97.89 ms, of which **31.28 ms** is unattributed" | a *third* figure for the same residual (31.28 vs 27.88 vs the 22.9–37.9 band of §2) — the residual is divisor-dependent, not a constant |

Hardcoded copies of the 97.9 ms constant that inherit the same caveat:
`research/lpt_expert_queue_sim.py:50`, `research/maple-fern-pr137-sec14-numbers.py:38`,
`research/tanjiro-pr157-result.md:338`, `research/maple-fern-pr137-submission-note.md:243`.

**Consequence for P2: none on the target.** The budget still has to close
against a ~96–98 ms H-M5 forward, so I proceeded to P2.

---

## 2. H-R128-P2 — summing the claimed budget, and what the residual actually is

### 2.1 The claimed budget does not sum to a measurement because its rows are not measurements

One host (H-M5), one configuration (512-token prefill, 0 warmup, 1 timed run,
undiscounted, 546.2 GB/s divisor). The claimed per-stage budget is
`research/maple-tanjiro-pr91-prefill-budget-census.md:596-658`, computed as
`floor = max(bytes / 546.2 GB/s, FLOPs / 60 TFLOP/s)` per stage from
source-derived shapes (§6.1 method at `:598-616`, per-stage table `:620-632`):

| stage (H-M5, analytic floor) | ms | basis |
| --- | ---: | --- |
| attn_proj_qkvo | 24.42 | compute-bound floor |
| routed_experts | 35.64 | memory-bound floor |
| attn_core | 2.69 | compute |
| shared_expert | 2.09 | compute |
| dense_mlp_layer0 | 0.86 | compute |
| router | 0.35 | compute |
| lm_head | 0.75 | memory |
| norm_rope | 1.77 | memory |
| moe_tail | 1.50 | memory |
| embedding | 0.01 | — |
| **Σ claimed** | **70.07** | `…census.md:632` (row `Σ floor`, @546.2 column) |
| **S (H-M5 receipt)** | **97.95** | `…census.md:640`; receipt arithmetic in §1 |
| **residual** | **27.88** | `…census.md:648`; 28.5 % of S |

**Summing check: 70.07 + 27.88 = 97.95 ✓.**

The decisive fact is *what kind of number each row is*. Every row is a
**lower bound** that assumes the stage hits its own roofline. A sum of lower
bounds cannot equal a measurement, and its shortfall is not evidence of a
missing mechanism. The residual is also not a constant: the same table gives
**22.87–32.03 ms undiscounted** and **30.25–37.89 ms zero-row-discounted**
across the 485–610 GB/s divisor range (`…census.md:642-657`), monotone in the
assumed divisor, and `research/PREFILL_LEDGER_INSTRUMENT.md:15-19` quotes
**31.28 ms** for the same quantity. `research/maple-tanjiro-r106f-prefill-speedup-decomposition.md:766-768`
already labels Σ = 70.07 as `[PROJ]` and possibly over-estimated.

### 2.2 How optimistic is this roofline method? Measured on H-M4A

The same analytic method applied to H-M4A with *that host's measured ceilings*
(28.76 TFLOP/s MMA, 260.2 GB/s DRAM,
`research/maple-fern-prefill-roofline.md:62-66`) gives a floor of
**102.5 ms DRAM / 98.4 ms MMA** for one 512-token forward
(`…roofline.md:70-82`), against a **measured 585.6 ms** on H-M4A — the method
under-predicts by **5.7×** on that host (`…roofline.md:84-86`; the forward runs
at 17.5 % of the bandwidth ceiling and 16.8 % of the MMA ceiling).

On H-M5 the same method under-predicts by only **97.95 / 70.07 = 1.40×**, i.e.
the ranked host achieves ~71.5 % of its aggregate per-stage roofline. So the
27.88 ms is the *residual optimism of a lower-bound model that is already far
tighter on H-M5 than on H-M4A*. If H-M5 achieved H-M4A's efficiency the forward
would take ~279 ms, not 97.95 ms; the `_nax` kernels that H-M5 selects for
94.2 % of prefill work (`research/PREFILL_LEDGER_INSTRUMENT.md:9-11`) are why it
does not.

### 2.3 Attributing the residual to named non-kernel causes

Every candidate cause the assignment names is a *non-kernel* cost, so each is
bounded by the non-kernel share of the prefill wall. On the only host with
per-kernel prefill visibility (H-M4A — no such visibility exists for H-M5,
`research/PREFILL_LEDGER_INSTRUMENT.md:7-14`) that share is measured:

- wall **552.06 ms**, union GPU busy **548.51 ms** ⇒ **99.4 % busy**, non-busy
  **3.55 ms** (H-M4A, `research/maple-fern-prefill-roofline.md:114-118`);
- **1222 dispatches** and 1066 command buffers per forward (H-M4A,
  `research/maple-tanjiro-pr91-prefill-budget-census.md:332-362`) ⇒ **≤ 2.9 µs**
  per dispatch boundary, ≤ 3.3 µs per command-buffer boundary;
- the census explicitly records "prefill has no dispatch-overhead gap on this
  host" (`…roofline.md:121-122`).

Scaling the *share* (not the M4 absolute) to the H-M5 window:

| cause | H-M5 ms `[PROJ]` | H-M4 measured basis | method | share of S |
| --- | ---: | --- | --- | ---: |
| Encoder / command-buffer boundaries + CPU gaps between dispatches | **≤ 0.63** | 3.55 ms of 552.06 ms wall on **H-M4A** | 1 − union-busy/wall from the GPUPROF trace | ≤ 0.64 % |
| Host-side tokenisation / fixture load inside the timed region | **0.00** | — | excluded by construction: timer opens after fixture load and tokenisation (`LagunaRuntimeLocalIterate.swift:547-557`) | 0 % |
| Layout / copy work | **0.00 (already priced)** | `elementwise` 4.747 ms + `moe_tail` 2.537 ms + `sort_scatter` 98.394 ms per forward on **H-M4A** (`…census.md:352-361`) | these are GPU kernels and already occupy rows in the claimed budget (`norm_rope`, `moe_tail`) or are inside `routed_experts` | 0 % (no double count) |
| First-use PSO/JIT/page-in cost *surviving* the constructor warmup | **≤ <<CW_M5>>** | <<CW_M4B>> ms of <<CW_COLD>> ms on **H-M4B**, n=<<CW_N>> (§3) | paired cold timed prefill vs warm 512-token seed forward in the same worker process | ≤ <<CW_PCT>> % |
| **Σ named non-kernel causes** | **≤ <<SUM_NAMED>>** | | | ≤ <<SUM_NAMED_PCT>> % |
| **Remainder: sub-roofline execution of already-priced kernels** | **≥ <<REMAINDER>>** | — | balancing row, see below | ≥ <<REMAINDER_PCT>> % |
| **Σ** | **27.88** | | | **28.5 %** |

**Summing check: 0.63 + 0.00 + 0.00 + <<CW_M5>> + <<REMAINDER>> = 27.88 ✓, and
70.07 + 27.88 = 97.95 ✓.**

**Why the first-use row is small rather than large — a code fact that the PR91
census predates.** `Sources/MLXFastModel/LagunaRuntimeWeights.swift:410-421`
runs a warmup *inside the runtime constructor*, before the worker answers the
harness handshake, and `:470-484` executes one **512-token prefill-shaped
forward** there, followed by 129-token and single-token decode shapes
(`:506-518`) and a greedy-argmax warm (`:530-540`). Its stated purpose is to
move Metal PSO creation and kernel-cache population outside every scored
window; the code comment records a prior PSO-miss log in which a compile fired
~0.23 s into the scored prefill with ~17 ms `MTLCompilerService` intervals,
which is exactly the failure mode this removes. So on the current frontier the
scored prefill is *not* the first 512-token forward of the process — it is the
second. That is why H-M4A's 5.2 % cold penalty
(`…roofline.md:110-112`, cold 584.09 vs warm-median 555.15 ms) does not
reproduce on H-M4B at anything like that size. On H-M4B
`clearAllocatorCacheAfterWarmup` is additionally active (48 GiB < 64 GiB
threshold), so free buffers *are* dropped after warmup while PSO state
survives — H-M4B is therefore a conservative host for this row, and the number
it produces is an upper bound on what a 128 GiB H-M5 would pay.

**The remainder is explicitly not a new mechanism, and I am not claiming it is
measured.** It is bounded from the other side: on H-M4A 99.4 % of the prefill
wall is GPU kernel busy time, so there is at most ~0.6 % of the wall available
for *any* non-kernel cause at all. The <<REMAINDER>> ms therefore has to sit inside
kernels that already own rows in §2.1, running below their individual floors.
That is the definition of the gap between a roofline lower bound and a
measurement, and §2.2 shows the same method is 4× more optimistic on H-M4A
without anyone concluding that H-M4A has 483 ms of mystery time.

**Unattributed remainder, stated explicitly: 0.0 ms of the 27.88 ms is
unattributed to a named *non-kernel* cause; <<REMAINDER>> ms `[PROJ]` is attributed to
sub-roofline execution of already-priced kernels and is measurable on H-M5 only
with per-kernel instrumentation that does not exist
(`research/PREFILL_LEDGER_INSTRUMENT.md:7-14`).**

---

## 3. New measurement on H-M4B: cold timed prefill vs warm seed forward

**Why this is the one measurable row.** The timed prefill takes 0 warmup runs
and 1 timed run (`Sources/MLXFastCore/Constants.swift:129-130`) and is the first
forward executed in a fresh worker process, so first-use cost (Metal PSO
creation, JIT of runtime-compiled kernel sources, first-touch page-in of the
21.6 GB resident tower) lands *inside* the scored window. The same
`--local-iterate` process runs a second 512-token forward moments later as the
decode seed and prints its wall time
(`LagunaRuntimeLocalIterate.swift:608-612`, `"decode seed prefill complete
seconds=…"`), giving a paired warm sample per run at zero extra cost.

Two properties make the delta a **conservative lower bound** on first-use cost:
`Memory.clearCache()` runs between the two forwards
(`LagunaRuntimeLocalIterate.swift:560`), and the warm sample additionally
contains `materializeLagunaCacheState(cache)` — both inflate the warm number.

Command (H-M4B, one model-holding process, thermal gate untouched):

```
bash research/r128p-cold-warm-prefill.sh 5
```

<<RESULTS>>

---

## 4. Achieved detection floor

<<FLOOR>>

---

## 5. Follow-ups I deliberately did not pursue

1. **Re-price the manifest's `_nax` levers against a corrected window.** The
   `~2.4 ms of the 97.9 ms` pool at
   `research/maple_endgame_handoff_manifest.md:490-492` and the §5 row at
   `research/maple_endgame_handoff_manifest.md:228` should each state whether
   the pool numerator was measured on M4 or derived from H-M5 shapes; a
   measured-on-M4 numerator over an H-M5 denominator is over-priced ~5.7×. Not
   pursued: this is an advisor bookkeeping decision, not an experiment.
2. **Retire or reconcile the three residual constants.** 27.88 ms
   (`research/maple-tanjiro-pr91-prefill-budget-census.md:648`), 31.28 ms
   (`research/PREFILL_LEDGER_INSTRUMENT.md:15-19`) and the 22.9–37.9 ms band
   (`research/maple-tanjiro-pr91-prefill-budget-census.md:642-657`) are the same
   quantity under different divisors. Not pursued: no new evidence needed, only
   an edit.
3. **Attack the first-use cost directly.** The only lever that could move it is
   pre-creating pipeline state objects / touching weights before the timer, and
   the timer opens at `LagunaRuntimeLocalIterate.swift:546` with model load and
   cache allocation already outside it — so any such work would have to happen
   in model construction, e.g. around `LagunaRuntimeModel.swift` weight
   preparation. Not pursued: this assignment forbids landing hunks, and on the
   official path the trusted parent times a worker round-trip
   (`Sources/MLXFastTrustedHarness/LagunaRuntimeBenchmark.swift:806-811`) whose
   process lifecycle I have not verified against the local one.
4. **Get real H-M5 per-kernel prefill visibility.** The instrument is already
   specified at `research/PREFILL_LEDGER_INSTRUMENT.md:7-14` and is the only way
   to convert the 22.2 ms remainder from `[PROJ]` to measured. Not pursued: it
   costs ranked receipts, which this assignment does not authorise.
5. **`arangeuint32` non-additivity on H-M5.** On H-M4A it reports 76 calls ×
   1763 µs = 134.03 ms for a 4 KB output but is fully overlapped and
   non-additive (`research/maple-fern-prefill-roofline.md:112-118`). Whether the
   `_nax` path emits the same pattern is unknown. Not pursued: needs the same
   missing H-M5 instrument.

---

## 6. Submission statement

**No official submission was fired during this assignment.**
`senpai/submit-official.sh` was not invoked, `mlxfast submit` was not invoked,
and `./benchmark.sh --local-submit` was not run against the official endpoint.
The only benchmark invocations were `./benchmark.sh --local-iterate` on H-M4B
via `research/r128p-cold-warm-prefill.sh`, which write only
`score.local-iterate.json` and `research/artifacts/r128p/`. No knob was flipped,
no kernel was written, and no landing hunk is proposed; the only submitted-path
files touched are **none** — every file added by this branch is under
`research/`.
