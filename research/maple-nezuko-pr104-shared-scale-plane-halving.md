# PR #104 — shared-expert scale-plane halving (Arm A) and the `ae9ac90b` re-audit

SENPAI-RESULT: {"terminal":true,"status":"complete","pending_arms":false,"wandb_run_ids":[],"primary_metric":{"name":"same_host_paired_estimate","available":false,"value":null},"test_metric":{"name":"passed_correctness","available":false,"value":null}}

- Student / PR: `maple-nezuko` / #104, branch `maple-nezuko/shared-scale-plane-halving`
- Hypothesis and target cost: Arm A claimed a 7.67 MB/step shared-expert
  group-32 scale plane could be halved losslessly, worth roughly 0.2 % of
  score. Deliverable 0 asked whether the `ae9ac90b` 1.47× observed/predicted
  ratio falsifies the single-band model in §0.9.36.
- Decision: **dead hypothesis for Arm A** (the 7.67 MB/step premise is a
  factor-2 bookkeeping error; the real removal is 3.83 MB/step, below every
  standing admissibility floor). **Deliverable 0 settled: (c) inconclusive**,
  the 1.47× is fully reproduced by a denominator choice and requires no new
  physics.
- `BASE_SHA` / candidate commit: `dec0a83c075d151ef5dec94f4005bd39ff2c2d69` /
  this commit. The advisor branch advanced to `bbc9e7b` mid-session, but that
  merge is research-only with zero submitted bytes, so per advisor comment
  `5202452697` I did not rebase or re-measure.
- Submitted candidate files: **none**. No byte of the submitted surface changed.
- Supporting test or documentation files:
  `research/maple-nezuko-pr104-r1-prereg.md`, this file.
- Official submission `--model` value: not applicable, nothing submitted.
- Explicit API model-value rejection: none.
- Assignment-scope preflight:
  `assignment scope OK: 3 submitted path(s) against BASE_SHA=dec0a83c075d151ef5dec94f4005bd39ff2c2d69`
- Editable bytes / headroom / growth:
  `editable budget OK: current=2934331/3000000 bytes headroom=65669 growth=0/262144 files=142 (base=142)`
- Scored-path reachability evidence: established for the Arm A control before
  it was cancelled — see the code map below. The shared-expert scale planes are
  read on the scored decode path by four live kernels. Reachability was never
  the blocker; magnitude was.

### Evidence

- Host, memory profile, toolchain, thermal policy: **no host was used.** No
  build, no benchmark, no GPU allocation, no thermal gate wait.
- Exact baseline and candidate commands: **none run.** Both deliverables were
  settled by counting against in-repo primary sources.
- Tests and risk-based checks run, including selected-test count: **none.** No
  code changed, so `research/run_upstream_equivalence.sh` has nothing to
  discriminate. Running it would have produced a pass that carried no
  information about this report.
- Correctness and serial-protocol verdict: unchanged from base by construction.
- Divergent tokens or failure category: none.
- Peak RAM or generated-weight size: unchanged.
- Official ranking status: nothing submitted.

| Metric | Baseline | Candidate | Ratio / delta |
| --- | ---: | ---: | ---: |
| decode seconds/token | 0.004908372 | not measured | — |
| prefill seconds/token | 0.000191201 | not measured | — |
| same-host paired estimate | — | not measured | — |

Baseline row is receipt `97a5090c-a408-4222-b6d6-dd85c4bce09e`
(`officialScore` 2.58882784082067, decode ×2.8207, prefill ×2.0015), quoted for
the exchange-rate arithmetic only. **No timing is claimed by this report and no
W&B run exists**; `wandb_run_ids` is empty because that is the honest value,
exactly as in #72.

---

## Deliverable 1 — the 7.67 MB/step premise is a factor-2 bookkeeping error

### The census

Geometry: hidden 2048, `moeIntermediate` 512, 256 experts, top-8,
`num_layers` 40 with layer 0 dense, so **39 sparse layers** (1–39). The shared
expert runs in every sparse layer, once per step, regardless of routing.

```text
shared gate_proj.scales  [512,128]  uint8 =  65,536 B
shared up_proj.scales    [512,128]  uint8 =  65,536 B
shared down_proj.scales  [2048,32]  uint8 =  65,536 B
                              per layer  = 196,608 B
                       × 39 sparse layers = 7,667,712 B = 7.67 MB/step
```

Shapes verified against `research/maple-nezuko-pr72-group32-scale-census.md`
lines 291–292 and against the live kernel strides quoted below.

**7.67 MB/step is the plane that is READ. It is not the bytes REMOVED.**
Halving a scale plane discards exactly one byte of every adjacent pair, so the
removal is half the plane:

```text
3,833,856 B = 3.83 MB/step  (3.824 MB net of 39 × 256 B of patch headers)
```

My own #72 note already recorded this correctly at line 368 — *"shared expert =
3.83 MB/step"* — and at line 535 — *"3.83 MB is 7.7× below the resolvability
floor. Out of scope; recorded as future work."* The 7.67 MB/step figure that
reached this assignment is that same plane counted as if reading it and
removing it were the same quantity.

### Pricing the real removal

At the routed-block achieved rate of 546.2 GB/s (tanjiro #73,
`CURRENT_RESEARCH_STATE.md:1271`), 3,833,856 B costs **7.019 µs/step**. At the
standing exchange rate of 14.862 % of score per ms of decode, that is
**+0.1043 % of score**, or **+0.104 % to +0.125 %** across the 1.0–1.2×
realisation band of §0.9.36.

That figure is:

- **2.3× below** the 0.243 % 2σ floor for two n=3 official families. Resolving
  it officially would need roughly 16 receipts per family.
- **5.9× below** the advisor's 0.61 % acceptance bar on `ns`.
- **6.1× below** the programme's own standing admissibility floor §0.5.8
  (`CURRENT_RESEARCH_STATE.md:2213`: *"≥27.8 MB/step at 651.8 GB/s or ≥23.3
  MB/step at 546.2 GB/s"*).
- Unmeasurable on M4: even at the generous 281.3 GB/s in-situ rate it is
  ≈0.155 % of an ~8.8 ms step, inside that host's own run-to-run noise.

### The pre-registered stop rule fires

The assignment says: *"If the true figure is materially below 7.67 MB/step, say
so and stop — a 3 MB/step arm is not worth the headroom."* The true figure is
3.83 MB/step. **Arm A is NO-GO. No GPU time was spent.**

This also means the arm would have consumed 2–3 kB of the remaining 65,669 B of
editable headroom (four new Metal kernel strings, two size constants, two
prepare sites, four wrapper preconditions, and dispatch guards) to buy an
effect the official harness cannot see.

### Code map, recorded so a future arm need not re-derive it

- `LagunaRuntimeWeights.swift:975-992` — `lagunaScalePatchHeaderBytes = 128`;
  `lagunaPackedRoutedGateUpScaleBytes = 128 + 256·1024·4·16 = 16,777,344`;
  `lagunaRoutedDownScaleBytes = 128 + 256·2048·16 = 8,388,736`.
- `lagunaHalvedGroup32ScalePlane` (`LagunaRuntimeWeights.swift:1014-1039`) —
  views a `uint8` plane as `[size/2, 2]`, keeps column 0, and returns `nil`
  unless every differing pair is in `allowedFlatPairs` (lossless-or-nothing).
  Output is `[128 B header][halved plane]` with `header[slot]` holding the
  discarded odd byte. Maximum 128 exceptions.
- Routed gate/up call site `:1052-1103` uses `allowedFlatPairs: [0, 16]`;
  routed down (`LagunaRuntimeModel.swift:9956-9965`) uses `[0]`. **#72's routed
  halving is already merged into this base**; the shared expert is what remains.
- Shared expert is **not** halved today.
  `LagunaRuntimeMLP.prepareFusedSharedGateUp()` (`:8248-8276`) is a plain
  row-concat producing `_fusedGateUpScales uint8 [1024,128]` = 131,072 B/layer;
  shared down is handed out live by `fusedSharedBankGuard` (`:8345-8377`) as
  `uint8 [2048,32]` = 65,536 B/layer.
- Kernel-side confirmation of the strides:
  `lagunaSharedSwiGLUQMVRows1Kernel` (`:6796`) and `lagunaSharedSwiGLUQMVKernel`
  (`:6714`) both declare `constexpr uint scale_row_bytes = 128`;
  `lagunaSharedDownResidualKernel` (`:6897`) declares `scale_row_bytes = 32`;
  `lagunaRoutedSharedDownResidualKernel` (`:7846`) declares
  `shared_scale_row_bytes = 32` / `routed_scale_row_bytes = 16` with
  `scale_lane = is_shared ? lane : (lane >> 1)` — that `>> 1` is the routed
  plane's existing halving, and its absence on the shared path is the gap Arm A
  proposed to close.
- Had the arm proceeded, the fused shared gate/up concat would have needed
  `allowedFlatPairs: [0, 32768]`, since the up-half begins at row 512, i.e.
  byte 65,536, i.e. flat pair 32,768.
- Alternatives checked and closed while scoping: attention Q/K/V/O scale
  repacking is closed by §0.9.22 (`CURRENT_RESEARCH_STATE.md:5837`, plane
  already at ≈100 % line utilisation), and no larger group-32 plane remains
  unhalved anywhere in the model.

---

## Deliverable 0 — `ae9ac90b` re-audit

### Sources, and one that does not exist

Receipt identity, from `research/nezuko-corpus-1253.json` (`submissions[]`):
id `ae9ac90b-4691-460c-bb63-8779b849ae4f`, solver `ivanfioravanti`, model
"Kimi K3", status `rejected`, `officialScore` 2.52698866954533, commit
`86a612d48d87479bb6da6dd4ab222b2c2877ef76`, created 2026-08-04T09:33:36.811Z.
`officialMetrics`: `decode_seconds_per_token` 0.00507095865625,
`prefill_seconds_per_token` 0.00019082877734375, `num_layers` 40.

**The diff does not exist in this checkout.** I scanned the corpus record for
`diff --git`, `--- a/`, and `@@ ` and found zero hits; the harvest-time diff
lived under `/tmp/nezuko-harvest/` on a host that has since been destroyed. The
corpus `note` field — 9,094 characters, 182 lines — **is** a primary source and
is in-repo; I extracted and read it in full, and it is the basis for everything
below. Second-hand shape is available from
`research/nezuko-harvest-report.md:437-438`: two files, **no `Vendor/` kernel**,
`LagunaLmHeadPrune.swift` (+293/−282) and `LagunaRuntimeModel.swift`
(+141/−77), with an M2 sizing of `~+55/-10` at `:479`.

### What the note actually says, verbatim

- *"A checkpoint census showed that **layers 1--38** use scale-code values no
  larger than 63… **Layer 39** contains four codes above 63 (maximum 73), so it
  uses the existing whole-layer uint8 bank."*
- *"gate and up codes for one lane form a **12-bit value**, and **two adjacent
  lanes occupy three bytes**"* — i.e. 32 B → 24 B per row, **−25 %**.
- Scope: *"The routed gate/up Top8-R1 QMV"*; *"Multi-token prefill continues to
  use the original fused scales and stock sorted gather-GEMM path."* The
  down-projection scale plane is **not** touched — confirmed independently by
  `CURRENT_RESEARCH_STATE.md:4399`, which lists routed down as a separate,
  unclaimed plane.
- Instruction channel, verbatim: *"The compact kernel uses a **distinct JIT
  name** and **two byte loads** from an alignment-safe address. **Lane parity
  selects** the appropriate 12-bit value; both recovered codes are **masked** to
  the exact original six used bits."*
- The A/B, verbatim: *"compact candidate steady mean: approximately **4.444
  ms/token**; uint8 control steady mean: approximately **4.471 ms/token**;
  steady decode improvement: approximately **0.60 %**; compact charged decode:
  0.004693277 s/tok; uint8-control charged decode: 0.004717620 s/tok; charged
  improvement ~0.52 %."* Method: `DARKBLOOM_PACKED_SCALE6=0` restores the
  pre-existing uint8 kernel from the same compiled source, `--local-submit`
  window, 1,023 checked decode steps per arm.

One correction to the corpus while I am here: the note also says *"Local
absolute scores compare this machine against pinned M5 constants and are
**directional only**."* So the 0.60 % is a **local** A/B, not a ranked-host
measurement. `CURRENT_RESEARCH_STATE.md:4431` labels it *"Field precedent on
the ranked host"*. That label is wrong and should be corrected.

### (b) — the census under-counted: **refuted, and the error runs the other way**

First-principles re-derivation of the plane the note says it packs:

```text
gate_proj.scales  [512,128] uint8 = 65,536 B/expert
up_proj.scales    [512,128] uint8 = 65,536 B/expert
gate+up                           = 131,072 B/expert
per layer, top-8                  = 1,048,576 B
× 39 sparse layers                = 40,894,464 B = 40.89 MB   (matches CRS:4398 "40.9")
ae9ac90b packs layers 1–38 only (38 layers) = 39,845,888 B = 39.85 MB
removal at −25 %                  =  9,961,472 B =  9.96 MB/step
```

The circulating figure was "~10 MB/token over 39 layers" = 10.22 MB. It
**over-counted by 2.63 %** because layer 39 falls back to the uint8 bank by the
note's own census. Correcting it makes the anomaly marginally *worse*, not
better. (b) is refuted.

### (a) — a bundled instruction/occupancy win: **directionally refuted**

Every instruction-channel hunk identifiable from the note is a **cost**, not a
benefit: two byte loads instead of one per scale fetch, a lane-parity select,
two masks, a shift-and-reconstruct, and a staged register that must hold a
12-bit word rather than a `uint8_t`
(`research/nezuko-harvest-report.md:501-510`). A net-cost instruction bundle
cannot inflate an observed win, so it cannot be the source of a ratio above 1.
The A/B is also two *different compiled kernels* — the note says "distinct JIT
name" — so it is not a clean byte-only isolation; but the confound is
directionally negative and therefore cannot rescue (a). The only speculative
positive cross-channel candidate is improved locality from the 24 B walk-order
side bank packing more tightly into cache lines, and the note contains nothing
that would let anyone quantify it.

### (c) — a real byte channel spanning 0.59× to 1.47×: **inconclusive**

Here is the root cause. **The same document prices this one arm two different
ways**, and the discrepancy is entirely the choice of denominator:

- `CURRENT_RESEARCH_STATE.md:4400` prices it at the **415 GB/s** achieved rate,
  and `:4443-4445` concludes *"My byte arithmetic independently predicts
  +0.36 % for that exact arm — two routes agreeing to 8 %."*
- `research/maple-nezuko-pr85-dense-mlp-lossless-repack.md:996` prices it at
  **546.2 GB/s**: *"10 MB / 546.2 GB/s = 18.3 µs on a 4.471 ms step =
  +0.41 %"*, which is where the 1.47× comes from.

Taking the corrected 9.96 MB removal against the note's own 4.471 ms step:

| denominator rate | provenance | predicted µs | % of step | ratio to observed 0.60 % |
| --- | --- | ---: | ---: | ---: |
| 281.3 GB/s | fern #71 in-situ routed-QMV duplication, M4 (`CRS:5837`) | 35.41 | 0.792 % | **0.76×** |
| 415 GB/s | whole-step average achieved (`CRS:4400`) | 24.00 | 0.537 % | **1.12×** |
| 546.2 GB/s | routed-block achieved, tanjiro #73 (`CRS:1271`) | 18.24 | 0.408 % | **1.47×** |
| 651.8 GB/s | attention-plane / M5 ceiling | 15.28 | 0.342 % | **1.75×** |

**Verdict: (c) inconclusive; the admissible interval is [0.76×, 1.76×].** The
"anomaly" is reproduced exactly by swapping 415 GB/s for 546.2 GB/s — those two
rates differ by 1.316×, and 1.47 / 1.316 = 1.12, which is inside §0.9.36's
1.0–1.2× band. No new physics is required, and **the single-band model
survives untouched**. There is no evidence that one byte channel delivered both
0.59× and 1.47×.

A second, independent identification failure is worth recording: the −0.60 % is
a **point estimate with no n, no half-range, and no confidence interval**. Held
at a fixed denominator, a plausible [0.3 %, 0.9 %] dispersion alone spans the
ratio interval [0.55×, 2.2×]. Even a perfect denominator would not settle this
arm from the evidence that survives.

### Answer to the advisor's question in comment `5202452697`

Plainly: **no.** The counting does not land on a kernel-dependent byte channel
capable of both 0.59× and 1.47×. The §R20.2 lm-head observation at 0.59× and
the `ae9ac90b` observation at 1.47× are not two readings of one strange
channel; the 1.47× is an artifact of which achieved rate the analyst reached
for, inside a single document, for a single arm. Once a consistent denominator
is applied, `ae9ac90b` sits at 1.12×. The single-band model in §0.9.36 is
intact and should not be revised on this evidence. §R20.2's 0.59 % shortfall
remains a live and separate question — but it is now a one-sided one, not half
of a spread.

### Proposed durable law

> An observed/predicted ratio is meaningless unless the denominator is the
> achieved bandwidth of **the kernel that reads those bytes, on the host where
> the measurement was taken**. Our corpus currently sanctions four such rates
> spanning **2.32×** (281.3, 415, 546.2, 651.8 GB/s) — a spread larger than any
> anomaly the programme has been chasing.

This is load-bearing because every MB → % conversion in every arm passes
through one of those four numbers, and nothing in the corpus currently forces
an analyst to declare which one and why.

### Conclusion

- What happened and why: Arm A died on arithmetic before reaching a compiler.
  Its 7.67 MB/step premise counted the shared-expert scale plane as read rather
  than as removed; the removal is 3.83 MB/step, which is 6.1× below the
  programme's own §0.5.8 admissibility floor and 2.3× below the official 2σ
  resolution floor. Deliverable 0 resolved to a denominator artifact.
- Evidence for or against the mechanism: the mechanism (halving a group-32
  scale plane losslessly) is sound and already merged for the routed planes in
  #72. Only the magnitude fails, and it fails by a factor that no amount of
  measurement care can recover.
- Uncertainty or M5 transfer risk: none introduced — nothing changed. The one
  residual uncertainty is `ae9ac90b`'s missing dispersion, which cannot be
  recovered from in-repo sources.
- Smallest useful next action: correct `CURRENT_RESEARCH_STATE.md:4431` (the
  0.60 % A/B is local, not ranked-host), correct the 10.22 MB figure to
  9.96 MB, and adopt the denominator law so future arms must name their rate.
- Recommendation: **close** Arm A as a dead hypothesis; **merge this note as
  research-only** for Deliverable 0 and the code map.
