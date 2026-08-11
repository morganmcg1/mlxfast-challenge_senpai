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

### 2.2 Three measured kernel families have no row in the claimed budget at all

The §6.2 table prices ten *derived* stages. The measured family ledger has
twelve families, and the census's own byte crosscheck names exactly which ones
fall through: **"unmapped (sort_scatter, elementwise, other) — analytic
0.004 GB vs measured 2.979 GB"** (`…census.md:583`, H-M4A). The analytic model
prices **0.13 %** of the bytes those families actually move. The mapping table
above it (`…census.md:570-582`) shows why this is a real hole and not a
labelling artefact: for `routed_experts` the analytic bytes (19.465 GB) track
the measured family bytes (18.968 GB) at ratio **0.974**, so the
`routed_experts` row prices the gather-GEMM traffic and nothing else — the
sort/scatter that *builds* the gather indices is not inside it.

The three unpriced families, from `…census.md:352-360` (H-M4A):

| family | n/fwd | GB/fwd (measured, H-M4A) | H-M5 floor @546.2 GB/s | non-overlapped wall cost, H-M4A |
| --- | ---: | ---: | ---: | ---: |
| `sort_scatter` | 154 | 1.135 | **2.078 ms** | 2.173 deflated / 2.632 raw |
| `elementwise` | 235 | 1.633 | **2.990 ms** | 3.365 deflated / 4.747 raw |
| `other` | 3 | 0.211 | **0.386 ms** | 0.309 raw |
| **Σ unpriced** | **392** | **2.979** | **5.454 ms** | **≈ 5.8 – 7.7 ms** |

Two cautions on the middle column, stated rather than buried. First, the bytes
are **measured on H-M4A** and projected onto the H-M5 divisor; they are
activation- and index-traffic, so they should be close to algorithmic, but the
`_nax` families H-M5 selects are not the families that were counted. Second,
the raw H-M4A ms column is *not* the size of the omission: `sort_scatter`'s
98.394 ms headline (17.82 % of serial GPU time, `…census.md:352`) is almost
entirely `arangeuint32`, which the census's own deflation removes as **fully
overlapped** (76 calls, 95.762 ms, `…census.md:410-413`), leaving
`sort_scatter (− arange)` at 2.632 raw / 2.173 deflated ms (`…census.md:420`).
Composition for the record: 76 `arangeuint32` + 38 `gather_front` + 38
`csort_scatter_fused` + 2 (`…census.md:468`).

That the H-M5 roofline floor (5.45 ms) and the H-M4A non-overlapped wall cost
(≈ 5.8–7.7 ms) land in the same place is a coherence check, not independent
confirmation — small index/elementwise kernels are launch- and latency-bound
rather than bandwidth-bound, so their measured cost sits near their nominal
floor on both hosts for different reasons.

**Corrected floor sum: Σ' = 70.07 + 5.45 = 75.52 ms**, leaving a corrected
residual of **97.95 − 75.52 = 22.43 ms (22.9 % of S)**. This is the largest
concrete correction available to the claimed budget, and it is arithmetic on
numbers already inside the census rather than a new mechanism. It also lands
essentially on the census's own undiscounted low end (22.87 ms,
`…census.md:642-657`), which is reassuring about the direction.
**Summing check: 75.52 + 22.43 = 97.95 ✓.**

### 2.3 How optimistic is this roofline method? Measured on H-M4A

The same analytic method applied to H-M4A with *that host's measured ceilings*
(28.76 TFLOP/s MMA, 260.2 GB/s DRAM,
`research/maple-fern-prefill-roofline.md:62-66`) gives a floor of
**102.5 ms DRAM / 98.4 ms MMA** for one 512-token forward
(`…roofline.md:70-82`), against a **measured 585.6 ms** on H-M4A — the method
under-predicts by **5.7×** on that host (`…roofline.md:84-86`; the forward runs
at 17.5 % of the bandwidth ceiling and 16.8 % of the MMA ceiling).

On H-M5 the same method under-predicts by only **97.95 / 70.07 = 1.40×**
(**1.30×** against the §2.2-corrected Σ' = 75.52), i.e. the ranked host achieves
~71.5 % (77.1 % corrected) of its aggregate per-stage roofline. So the
22.43 ms is the *residual optimism of a lower-bound model that is already far
tighter on H-M5 than on H-M4A*. If H-M5 achieved H-M4A's efficiency the forward
would take ~279 ms, not 97.95 ms; the `_nax` kernels that H-M5 selects for
94.2 % of prefill work (`research/PREFILL_LEDGER_INSTRUMENT.md:9-11`) are why it
does not.

### 2.4 Attributing the corrected residual to named non-kernel causes

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

Two projections of that non-busy time to H-M5 are defensible and they differ:
scaling the *share* gives 0.0064 × 97.95 = **0.63 ms**; treating per-dispatch
CPU encode cost as roughly host-invariant carries the **3.55 ms absolute**
across, which is 3.6 % of the smaller H-M5 window. Share-scaling is the
optimistic direction, so the row below reports the range and uses **3.55 ms as
the conservative bound** in the summing check.

| cause | H-M5 ms `[PROJ]` | H-M4 measured basis | method | share of S |
| --- | ---: | --- | --- | ---: |
| Encoder / command-buffer boundaries + CPU gaps between dispatches | **0.63 – 3.55** (use 3.55) | 3.55 ms of 552.06 ms wall on **H-M4A** | 1 − union-busy/wall from the GPUPROF trace; share-scaled (0.63) vs host-invariant absolute (3.55) | 0.6 – 3.6 % |
| Host-side tokenisation / fixture load inside the timed region | **0.00** | — | excluded by construction: timer opens after fixture load and tokenisation (`LagunaRuntimeLocalIterate.swift:547-557`) | 0 % |
| Layout / copy work (`elementwise`, `sort_scatter`, `other`) | **0.00 here — moved into the floor** | 2.979 GB/forward on **H-M4A** (`…census.md:583`) | these are GPU kernels, not overhead; §2.2 prices them at 5.45 ms and folds them into Σ', which is exactly why the residual attributed here is 22.43 and not 27.88 | 0 % (no double count) |
| First-use PSO/JIT/page-in cost *surviving* the constructor warmup | **≤ 1.48** | ≤ 8.67 ms of 574.65 ms on **H-M4B**, n=5 (§3, §4) | the warmup-off ablation proves the warmup removes 1252 ms (§3.2), so the *surviving* part is whatever the warmup misses; it did not separate from noise, so this row carries the achieved detection floor 8.67 ms / 574.65 ms = 1.509 %, share-scaled to the H-M5 window | ≤ 1.5 % |
| **Σ named non-kernel causes** | **≤ 5.03** | | | ≤ 5.1 % |
| **Remainder: sub-roofline execution of already-priced kernels** | **≥ 17.40** | — | balancing row, see below | ≥ 17.8 % |
| **Σ (corrected residual, §2.2)** | **22.43** | | | **22.9 %** |

**Summing check: 3.55 + 0.00 + 0.00 + 1.48 + 17.40 = 22.43 ✓, and
75.52 + 22.43 = 97.95 ✓ (§2.2 corrected Σ').**

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
for *any* non-kernel cause at all. The 17.40 ms therefore has to sit inside
kernels that already own rows in §2.1, running below their individual floors.
That is the definition of the gap between a roofline lower bound and a
measurement, and §2.3 shows the same method is 4× more optimistic on H-M4A
without anyone concluding that H-M4A has 483 ms of mystery time.

**Unattributed remainder, stated explicitly: 0.0 ms of the 22.43 ms is
unattributed to a named *non-kernel* cause; 17.40 ms `[PROJ]` is attributed to
sub-roofline execution of already-priced kernels and is measurable on H-M5 only
with per-kernel instrumentation that does not exist
(`research/PREFILL_LEDGER_INSTRUMENT.md:7-14`).**

---

## 3. New measurement on H-M4B

All numbers in this section are **H-M4B** (Apple M4 Pro, 48 GiB, low-memory
startup profile), one model-holding process at a time, thermal gate untouched,
`./benchmark.sh --local-iterate`.

### 3.1 What I first intended to measure, and why that design is void

I set out to price the "first-use cost inside the scored window" row by
comparing the timed prefill against the 512-token forward the decode phase runs
as its seed. Reading the harness while the runs were in flight killed that
interpretation, and the correction matters more than the measurement:

- `Sources/MLXFastTrustedHarness/LagunaRuntimeLocalIterate.swift:726` creates a
  **`prefillWorker`** and closes it at `:728`; `:770` then creates a **separate
  `decodeWorker`**. The two 512-token forwards run in **different processes**,
  each behind its own thermal gate (`:730`, `:774`).
- `Sources/MLXFastModel/LagunaRuntimeWeights.swift:410-421` runs a warmup in the
  **runtime constructor**, before the protocol handshake, and `:470-484` makes
  that warmup a full **512-token prefill-shaped forward** (plus 129-token and
  single-token decode shapes at `:506-518`).

So both arms are the *second* 512-token forward of their own process, not a
cold/warm pair, and neither is "the first forward" the assignment's first-use
row imagined. The timed prefill takes 0 warmup and 1 timed run at the harness
level (`Sources/MLXFastCore/Constants.swift:129-130`), but the runtime warms
itself one level below that.

The n=5 result is still worth recording as a **path-difference** bound, because
the two arms differ by exactly the prefill request path (IPC round-trip, timer
opened at `LagunaRuntimeLocalIterate.swift:731` before the request at `:740`)
versus the decode seed path (cache allocation plus
`materializeLagunaCacheState`):

| run | timed prefill (ms) | decode-seed forward (ms) | delta (ms) | delta (%) |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 571.242 | 569.698 | +1.544 | +0.271 |
| 2 | 569.171 | 576.249 | −7.078 | −1.228 |
| 3 | 575.454 | 575.004 | +0.449 | +0.078 |
| 4 | 574.598 | 570.273 | +4.325 | +0.758 |
| 5 | 582.805 | 569.750 | +13.055 | +2.291 |
| **mean** | **574.654** | **572.195** | **+2.459** | **+0.43** |
| sd | 5.215 | 3.172 | 7.273 | |

95 % CI on the delta: **[−6.57, +11.49] ms — consistent with zero.** The
"pairing" buys nothing (sd of the delta exceeds sd of either arm) precisely
because the arms are independent processes after independent thermal gates.
Reproduce with `bash research/r128p-cold-warm-prefill.sh 5` then
`python3 research/r128p-analyse.py`; raw logs and scores in
`research/artifacts/r128p/`.

Derivation of each column, for audit: timed prefill =
`prefill_seconds_per_token × 512`; decode-seed forward =
`(decode_seconds_per_token − mean_step_seconds) × 128`. The printed
`decode seed prefill complete seconds=0.6` line is useless for this — it goes
through `formatSeconds`, which rounds to 0.1 s
(`Sources/MLXFastTrustedHarness/LagunaRuntimeSupport.swift:58`).

### 3.2 The measurement that does isolate first-use cost

Because the constructor warmup is the thing that moves first-use cost out of
the scored window, the clean experiment is to **switch it off**. The runtime
worker child gets a strict allowlist environment built from empty
(`Sources/MLXFastTrustedHarness/LagunaRuntimeWorker.swift:1993-2024`), and
`DARKBLOOM_` is one of six forwarded prefixes (`:2008-2015`) — so a
`DARKBLOOM_R128P_SKIP_WARMUP` gate around `Self.warmLibraryModel(model)` is the
only way to reach the child without touching a trusted file. With the warmup
off, the timed prefill is the genuinely first forward of the process: no
warmup request sits between `RuntimeWorkerClient` construction at `:726` and
the timed `prefill(...)` call at `:740`.

**This gate is research-only instrumentation and is reverted in the result
commit** (added in `d1e34e83`, removed before submission); the submitted
surface is unchanged.

```
bash research/r128p-warmup-ablation.sh 5
python3 research/r128p-analyse.py nowarm.tsv nowarm
python3 research/r128p-ablation-stats.py    # -> artifacts/r128p/ablation-stats.txt
```

All four quantities below are **H-M4B**, n=5 per arm, both arms behind the same
40 C thermal gate, one model-holding process at a time. Raw logs
`research/artifacts/r128p/nowarm-{1..5}.log`, scores `nowarm-score-{1..5}.json`,
table `nowarm.tsv`, statistics `ablation-stats.txt`.

| metric (**H-M4B**) | warm-on | warm-off | delta (off − on) | ratio | t | 95 % CI on delta |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| timed 512-token prefill (ms) | 574.654 (sd 5.215) | 1826.913 (sd 22.361) | **+1252.259** | 3.179× | 122.0 | [+1223.7, +1280.8] |
| decode-seed forward (ms) | 572.195 (sd 3.172) | 1810.367 (sd 25.990) | +1238.173 | 3.164× | 105.7 | [+1205.6, +1270.7] |
| mean decode step (ms) | 8.402 (sd 0.037) | 11.155 (sd 0.043) | +2.754 | 1.328× | 109.4 | [+2.7, +2.8] |
| decode step 1 (ms) | 34.981 (sd 4.483) | 335.190 (sd 4.452) | +300.209 | 9.582× | 106.3 | [+292.4, +308.1] |

**Reading, in the order that matters for the budget.**

1. **The constructor warmup is worth ~1.25 s of the H-M4B prefill window, i.e.
   68.6 % of what that window would otherwise cost** (1252.259 / 1826.913). Two
   independent 512-token forwards in two different processes agree on the size
   (+1252.3 ms in the prefill worker, +1238.2 ms in the decode worker's seed),
   and every t here is >100, so this is not a noise artefact. First-use
   PSO/JIT/page-in cost is real and large; it is simply already paid outside the
   scored window on the current frontier.
2. **Therefore the PR91-era intuition that first-use cost explains the residual
   is backwards.** The residual to explain is 22.43 ms `[PROJ]` on H-M5. The
   first-use cost is ~20× that on this host — and the warmup already removes it.
   What could still leak into the scored window is only the part the warmup
   *misses*, and that is what §2.4's first-use row bounds.
3. **This design cannot resolve the surviving part.** The ablation measures
   `warmup − no warmup`, not `warmup − perfect warmup`. To isolate the residue
   you need per-kernel PSO-miss attribution inside the timed region, which does
   not exist on H-M5 (`research/PREFILL_LEDGER_INSTRUMENT.md:7-14`). So the
   surviving cost is bounded from above by what this experiment could have seen
   and did not: the achieved detection floor in §4, 8.67 ms on 574.65 ms =
   1.509 %, which share-scales to **≤ 1.48 ms** of the H-M5 window.
4. **The decode side shows the same shape and is not part of this budget.**
   Warm-off decode step 1 costs 335 ms against a 11.2 ms steady step; warm-on it
   costs 34.98 ms (sd 4.483) against 8.402 ms. So ~26.8 ms of one-off cost still
   lands inside the *decode* window even with warmup on — a decode observation,
   recorded here because it fell out of the same runs, and listed as follow-up 5.
   Note also that warm-off inflates the *steady* decode step by 1.328×, which
   means the warm-off arm is not merely "the same work plus a compile": dropping
   the warmup also changes allocator and cache state for the whole run. That is
   a second reason not to read 1252 ms as a bound on anything inside the
   warm-on window.

---

## 4. Achieved detection floor at the n actually run

This is the floor **achieved at n=5**, the n that actually ran — not a target n
computed from an assumed sd. Convention (identical in both scripts:
`research/r128p-analyse.py:51-61`, `research/r128p-ablation-stats.py:70-78`):
two-sided α = 0.05, power = 0.80, MDE = (t₀.₉₇₅,₄ + t₀.₈₀,₄) · sd/√n =
3.717 · sd/√5.

| quantity (**H-M4B**) | sd (ms) | n | MDE (ms) | MDE as % of the 574.654 ms window | share-scaled to the 97.95 ms **H-M5** window |
| --- | ---: | ---: | ---: | ---: | ---: |
| timed 512-token prefill, single arm | 5.215 | 5 | **8.669** | **1.509 %** | **1.478 ms** |
| paired (timed prefill − decode-seed forward) delta | 7.273 | 5 | 12.090 | 2.104 % | 2.061 ms |

**What this licenses and what it forbids.**

- The single-arm floor 8.669 ms / 1.509 % is the one to quote. The paired floor
  is *worse* (12.090 ms) because the two arms are independent processes behind
  independent thermal gates (§3.1), so differencing adds variance instead of
  cancelling it. Pairing was the original design's premise and it is void.
- Any effect this experiment reports as "consistent with zero" is only
  established as **smaller than 8.669 ms on H-M4B**, i.e. smaller than ~1.5 %
  of the window. Concretely: §3.1's +2.459 ms cold-vs-warm delta is *not*
  evidence that first-use residue is zero; it is evidence that it is under
  ~8.7 ms here.
- Share-scaling that relative floor onto the H-M5 window gives **1.478 ms**,
  which is why §2.4's first-use row reads ≤ 1.48 ms. Share-scaling is the
  assumption that the effect is a fixed *fraction* of the window; for a
  first-use compile cost that is questionable in both directions (a PSO miss is
  closer to host-invariant absolute cost, like the encoder row at §2.4), so
  treat 1.48 ms as an order-of-magnitude bound, not a measurement.
- The ablation in §3.2 is far above every floor here (t > 100, smallest CI
  half-width 28.6 ms against a 1252 ms effect), so no floor caveat applies to
  it.
- What n would be needed to resolve the interesting quantity? To detect the
  17.40 ms remainder as a *relative* effect (17.8 % of the window) at this sd,
  n = 1 suffices — the remainder is not small. The obstacle is not statistical
  power on a wall-clock number; it is that no experiment on this host can
  attribute wall-clock to per-kernel sub-roofline execution without the M5
  per-kernel instrumentation that does not exist
  (`research/PREFILL_LEDGER_INSTRUMENT.md:7-14`). Adding runs would not have
  changed the attribution conclusion.

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
   to convert the §2.4 remainder from `[PROJ]` to measured. Not pursued: it
   costs ranked receipts, which this assignment does not authorise.
5. **`arangeuint32` non-additivity on H-M5.** On H-M4A it reports 76 calls ×
   1763 µs = 134.03 ms for a 4 KB output but is fully overlapped and
   non-additive (`research/maple-fern-prefill-roofline.md:112-118`). Whether the
   `_nax` path emits the same pattern is unknown. Not pursued: needs the same
   missing H-M5 instrument.
6. **The first decode step is 3.6–4.9× a steady step, despite a warmup that
   already exercises the single-token decode shape.** Across all five warm-on
   H-M4B runs step 1 costs 40.018 / 32.591 / 29.777 / 39.337 / 33.180 ms
   (mean 34.98) against a steady ~8.16–8.24 ms
   (`research/artifacts/r128p/iterate-{1..5}.log`, the
   `local-iterate checked decode 1/128 … last_step_seconds=` and
   `128/128 …` lines), i.e. **~26.8 ms of one-off cost inside the *decode*
   window**, which carries 75 % of the score weight and is 2.5 % of the whole
   128-step decode pass. `Sources/MLXFastModel/LagunaRuntimeWeights.swift:506-518`
   does warm a single-token decode shape, so the residue is shape- or
   cache-state-dependent (the warmup runs before
   `materializeLagunaCacheState`, and the seed cache length differs). Not
   pursued: it is a decode question and this assignment is prefill attribution
   — but as a fraction of its own window it is far larger than anything in
   §2.4, and it is the follow-up I would run next.

---

## 6. Submission statement

**No official submission was fired during this assignment.**
`senpai/submit-official.sh` was not invoked, `mlxfast submit` was not invoked,
and `./benchmark.sh --local-submit` was not run against the official endpoint.
The only benchmark invocations were `./benchmark.sh --local-iterate` on H-M4B
(10 runs: 5 via `research/r128p-cold-warm-prefill.sh`, 5 via
`research/r128p-warmup-ablation.sh`), which write only
`score.local-iterate.json` and `research/artifacts/r128p/`. No knob was flipped,
no kernel was written, and no landing hunk is proposed.

**Submitted surface, as delivered: unchanged.** One editable-path file,
`Sources/MLXFastModel/LagunaRuntimeWeights.swift`, carried the
`DARKBLOOM_R128P_SKIP_WARMUP` research gate in intermediate commit `d1e34e83`
so the §3.2 ablation could reach the worker child; it is reverted in this
branch's final commit, so `git diff "$BASE_SHA" -- Sources Vendor` is empty and
every file this branch adds or changes lives under `research/`.
