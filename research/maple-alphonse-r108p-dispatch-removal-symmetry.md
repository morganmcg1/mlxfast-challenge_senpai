# R108-P — Is dispatch price symmetric? Removal price vs addition price

Student: `maple-alphonse`. PR #644. Assignment `maple-r107-e-decode-oproj-amortisation`,
revision `r108-p-rev1`. Base `705484b9e120d60a973d660fdbdd1ccc7cdfa124`.
Host: **M4 Pro (Apple GPU generation 16)** — not the ranked M5. Zero official
receipts consumed. **Submitted surface is byte-identical to the base**; R108-P
needs no source change (the R107-E geometry instrument was reverted, and both
ladders ride pre-existing `DARKBLOOM_*` environment toggles).

## § Reply to advisor — the removal/addition ratio

> The live numbers are in `research/artifacts/maple-alphonse-r108p/fit.json`;
> §5 is generated from it. This section is the prose answer to comment 8.

**The answer in one sentence.** Yes — removal and addition cost the same per
dispatch, **once both are priced in the same regime**; the apparent 13×
asymmetry is entirely an artifact of measuring addition inside a free region
this host has up to K ≈ 480 dispatches/step, and the same artifact is baked into
`k_dispatch = 1.890`, which divides an M5 *marginal* price by an M4 *chord*.

**Headline**

| # | quantity | value | basis |
|---|---|---|---|
| 1 | **M4 decode removal price** | **see §5.2** | OLS over `d0 / dQ / dR / d4`, Δn = 0/40/117/158 |
| 2 | M4 addition price at my operating point (K=276) | see §5.2 | inside the free region; CI spans zero |
| 3 | naive ratio 1 / 2 | see §5.3 | real, but regime-mismatched — **do not plan on it** |
| 4 | **regime-matched ratio** = 1 / R93 past-knee addition (2.17 µs, same host) | **see §5.3** | the number the charge actually asks for |
| 5 | ratio 1 / rule 57 (1.2382 µs, M4) | see §5.3 | secondary comparison, requested |
| 6 | `k_removal` = rule 65 (2.3403 µs, M5) / 1 | see §5.3 | fourth read on the third-regime multiplier |
| 7 | `k_dispatch` regime-matched = 2.3403 / 2.17 | see §5.3 | independent second route to the same k |

**Three findings, in order of planning value.**

1. **Rule 57's 1.2382 µs is a chord, not a saturated per-dispatch price.**
   `research/r93-runs/knee-results.md` — same M4 Pro host, prior round — has a
   0→2400 chord of **1.271 µs/dispatch** (medians) / 1.300 (means), which
   reproduces 1.2382 to within 5 %. Its *segment* prices are monotone and
   convex: −0.43, −0.03, +0.58, +0.73, +1.98, +2.36 µs/dispatch across
   0→240→480→800→1200→1600→2400. Rule 57's own hinge, `Δ = c·K − G` with
   c = 1.2382 and G = 9.70 µs/step, crosses zero at K ≈ 8 — irreconcilable with
   a free region that reaches K ≈ 480, so the fitted model is misspecified, not
   just imprecise. The saturated M4 addition price is **≈2.17 µs/dispatch
   (range 1.98–2.36)**.
2. **Regime-matched, removal and addition are symmetric within noise** (row 4).
   Two independent routes then put the M4→M5 dispatch multiplier at
   **k ≈ 1.1**, not 1.890: `k_removal` from my removal slope against rule 65
   (row 6), and `k_dispatch` recomputed against R93's saturated addition price
   (row 7). Both land at the *bottom* of the residue table's already-fitted
   `k ∈ [1.0, 1.89]` bracket. Planning at 1.890 **over-states projected M5
   fusion wins by ≈75 %** (1.890 / 1.079).
3. **Rule 68 / #527 needs a narrow amendment, not a reversal.** #527 removed 78
   **prefill** dispatches on M5 `_nax` and got 0.639 ms *slower*; that is
   consistent with restructuring cost dominating a per-dispatch overhead already
   amortised ≈512× by the prefill batch. Rule 53's "+0.3 µs residue" addition
   probe is, on this reading, the free region measured without knowing it. The
   amendment R108-P supports: **on decode, a dispatch on the critical chain
   costs ≈2 µs on M4 and removal recovers it; Little's-law overlap applies to
   hazard-free launches, not to serialised ones.** #527's own "do not open a
   dispatch-fusion arm" was marked *suspended, not settled*, and this is the
   re-verification it queued — for the decode axis only.

**The planner rule I would replace "count dispatches" with.** A fusion is worth
≈2 µs per dispatch removed **only if that dispatch was on the critical chain**.
Dispatch count is not the qualifying test; chain membership is. In pricing terms,
at the regime-matched k each M4 µs/step recovered is worth
`0.015228 × 1.079 = 0.0164 %cs` (against `0.0288 %cs` at k = 1.890), so a decode
fusion removing N *chained* dispatches prices at ≈`0.037 × N` %cs — and at ≈0
for the same N if those dispatches were already overlapping. This is the
established pricing identity's arithmetic, not a measured win; the point is that
the multiplier on N is what fell, while the *qualifying condition* on N is what
was previously missing.

**What this does not license.** It is M4, the M5 side of both constants is
unmeasured here, and a live counter-model (phase heterogeneity plus stacking at
the 7 forced commit boundaries) could push k back to ≈2.2 — see threats 8 and 9.
The safe planning statement, true under both models, is **"not 1.89 by
construction"**.

## 1 What was asked and what is closed

Advisor comment 8 on PR #644 (`r108-p-rev1`) does two things:

1. **Family A (T3b oproj amortisation) is CLOSED.** The roofline falsifier is
   cancelled. Closure note with verdict `N-T3B-CLOSED-BY-CENSUS` is
   `research/maple-alphonse-r107e-closed.md`, committed at `d9854747`. R107-E's
   own numbers (36 runs, all correctness-passing) are re-derived there against
   tanjiro's #107-G census, which puts family A on the **bytes** axis with only
   0.794 µs/dispatch of non-byte slack (23.8 M4 µs/step = 0.159 %cs = 0.40
   bars). Amendment 1 withdraws §7 (T2d) — frieren owns it; untouched here.
2. **R108-P**: build a *removal* ladder, fit µs/step saved per dispatch
   removed with a CI, and headline the ratio removal-price / addition-price
   against rule 65's 2.3403 µs [2.2766, 2.4040] (M5), with a secondary M4
   comparison against rule 57's 1.2382 µs [1.2237, 1.2518]. This is a fourth
   independent read on the third-regime multiplier (`k_dispatch = 1.890`;
   tanjiro's `k_residue = 1.4998 [1.4732, 1.5275]`).

## 2 Design

Two ladders, same binary, same session, same thermal gate, no source change.

**Ladder E (addition, exact Δn).** `DARKBLOOM_INJECT_DECODE_EMPTY=n` injects
`n` empty `MLXFast.metalKernel` dispatches per decode step
(`LagunaRuntimeModel.swift:12005`, kernel body at `:12079-12089`, call site at
`:11756`). Each injected unit is exactly one dispatch, so Δn is exact by
construction. Defaults kept: `_EMPTY_SPREAD=1`, `_EMPTY_TG=160`×256 threads,
`_EMPTY_CHAIN=1` (each empty kernel consumes the previous one's output, so the
injected chain is internally serialised).

*This is the crux, and my pre-registered reading of it was wrong.* `_EMPTY_CHAIN=1`
serialises the injected kernels **against each other**, but every injected kernel
binds only its own scratch/control/sink buffers and never touches a tensor the
model reads or writes. MLX inserts GPU ordering only when a new encoder's inputs
intersect a prior encoder's outputs, so the injected chain is **hazard-free with
respect to the model's data** and has nothing to wait for. It can be scheduled
into whatever gaps already exist between the model's own GPU work — and decode
leaves roughly a millisecond per step of such gaps while the CPU builds the next
graph. Ladder E therefore does **not** measure the price of a dispatch on the
critical path; it measures the price of a dispatch that can hide.

This was anticipated on this exact host. `research/r93-runs/knee-results.md`
mapped the same knob on M4 Pro and found a convex curve with a **free region**:
K = 0 → 8.223 ms, 240 → 8.131, 480 → 8.125, 800 → 8.456, 1200 → 8.597,
1600 → 9.409, 2400 → 11.344 ms, with segment prices rising monotonically from
−0.43 to +2.36 µs/dispatch and the knee between 480 and 800. It also stated the
consequence in advance: *"the ladder slope is a lower bound on the value of
removing a real dispatch, and in a regime with scheduling slack it can be a very
weak one"*, and predicted that a null at small K "converts into a hard upper
bound of roughly 0.06 µs/dispatch on the cheap regime". R108-P is the first
experiment to put the matching **real**-dispatch number beside it in the same
session on the same tree.

*Known benign confound.* When injection is active, `lagunaInjectLayerWork`
ends each layer with `asyncEval(pending)`, so every rung with `n ≥ 40` carries
exactly 40 extra forced flushes. That is a **fixed offset**: it lands in the
intercept, not the slope, as long as every fitted rung has `n ≥ 40`. All E
rungs used here satisfy that (78, 156, 158, 198, 276). `DARKBLOOM_DECODE_ASYNC_STAGE`
is left at its default `at:0,1,7,15,23,31,39` (7 forced commits/step) in every
arm including `d*`.

**Ladder D (removal, censused Δn).** The runtime ships several *already fused*
decode paths behind `DARKBLOOM_FUSED_*` toggles. Setting a toggle to `0`
**de-fuses**, i.e. adds real dispatches. Measuring `t(de-fused) − t(fused)` and
dividing by the censused Δn gives the price of *removing* a real dispatch —
which is exactly the quantity every fusion optimisation is spending its budget
to buy.

Direction convention: both ladders are fitted as µs/step **per extra dispatch**,
so a ratio of 1.0 means "removing a real dispatch buys exactly what adding an
empty one costs".

## 3 The Δn census (the dominant uncertainty)

No empirical dispatch counter is reachable: MLX's `buffer_ops_` counter lives in
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.h:113`, and neither
`device.cpp` nor `eval.cpp` is in `benchmark.json`'s `editablePaths` (only
`matmul.cpp`, `jit_kernels.cpp`, `kernels.h` and `kernels/**` are). Δn on the
removal side is therefore an **audited source census with its own stated
uncertainty**, not a measured count. Full ledger:
`research/artifacts/maple-alphonse-r108p/dn-census.json`.

Model shape from `weights/config.json`: 40 layers, `mlp_only_layers=[0]` ⇒ **39
MoE layers**, `norm_topk_prob=true` (and `LagunaConfig.swift:583-584` *errors*
if it is false, so it is not host-dependent), `num_experts_per_tok=8`,
`DARKBLOOM_NATIVE_AFFINE_QKV_LAYERS` defaults to **40**
(`LagunaRuntimeModel.swift:340-347`).

| toggle set to `0` | Δ/use | uses/step | Δn/step | confidence |
|---|---|---|---|---|
| `DARKBLOOM_FUSED_ROUTER_CAST` | +3 | 39 | **+117** | high |
| `DARKBLOOM_FUSED_ROUTER_NORM` | +2 | 39 | +78 *standalone only* | high |
| `DARKBLOOM_FUSED_RESIDUAL_RMS` | +1 | 1 | **+1** | high |
| `DARKBLOOM_FUSED_NORM_AFFINE_QKV` | +1 | 40 | **+40** | high |
| **arm `d4` = all four off** | | | **+158**, range [119, 197] | medium |

Derivations, with line numbers at merge commit `f3c7944a` (submitted surface
identical to base):

- **`FUSED_ROUTER_CAST`** (`:10277-10326`). ON: the guarded `if` at `:10277`
  holds (`lagunaDecodeRouterTop8Enabled && lagunaDecodeRouterCastSinkEnabled &&
  softcap == 0 && bf16 && size == 256 && topK == 8`), `sinkNormalization =
  normTopkProb && lagunaDecodeRouterNormSinkEnabled` is true, and
  `lagunaDecodeRouterTop8(…, normalizing: true)` **returns early** at `:10297`.
  Dispatches: `bias.asType(.float32)` + fused top-8 = **2**. OFF: the whole `if`
  fails, so `:10300` does `projectedLogits.asType(.float32)`, then the fp32
  sub-branch does `bias.asType` + fused top-8 *without* normalising, then the
  tail at `:10324` adds `weights.sum(axis:-1)` + a broadcast divide.
  Dispatches: **5**. `bias.asType` cancels ⇒ **+3**.
- **`FUSED_ROUTER_NORM` is not additive with `FUSED_ROUTER_CAST`.** Both live
  behind the same guarded `if`; once `CAST=0` that `if` already fails, so
  `NORM=0` contributes nothing extra. This is why `d4` counts the router group
  **once**, as +117, and why the originally-drafted `d1…d4` staircase was
  partially redundant. Standalone (`CAST` left on) `NORM=0` is a clean +78.
- **`FUSED_RESIDUAL_RMS` is very nearly a no-op** (`:11172-11215`). The chain
  tries `lagunaFusedResidualRMSNormRouterEnabled` first, which only requires
  `mlp as? LagunaRuntimeSparseMoEBlock` and is **not** gated by
  `DARKBLOOM_FUSED_RESIDUAL_RMS`; it therefore keeps all 39 MoE layers fused.
  Only dense layer 0 reaches the `FUSED_RESIDUAL_RMS` branch (ON: 1 dispatch;
  OFF: `x + r` plus `postAttentionLayerNorm` = 2) ⇒ **+1/step**. Any future
  experiment that expects this flag to de-fuse the MoE stack is measuring
  nothing.
- **`FUSED_NORM_AFFINE_QKV`** (`:5916-5955`). ON: `lagunaNormAffineQKV` = 1
  dispatch. OFF: `inputNorm(input)` (`MLXFast.rmsNorm`, 1) +
  `lagunaDecodeNVFP4QKVR1` (1; its `quantizedMM` fallback is also 1) = 2 ⇒
  **+1** × 40 layers.

**Byte neutrality.** The de-fused rungs move a little extra memory:
`FUSED_NORM_AFFINE_QKV=0` materialises the normalised hidden state (2048 bf16 =
4 kB written + 4 kB read per layer = **320 kB/step**, 2.0 % of the 15.10 MiB/step
decode byte budget) and `FUSED_ROUTER_CAST=0` materialises the f32 router logits
(~62 kB/step, 0.4 %). At frieren's measured achieved 227.1 GB/s that is
**1.41 + 0.27 = 1.68 µs/step**, i.e. **0.54 %** of the observed `d4 − d0` gap.
It is subtracted as a stated correction in §5, and it cannot explain the result.

**FP / correctness.** Every de-fusion changes reduction order in principle. Each
`d*` run is a full `--local-iterate`, so the harness's exact greedy token-ID
equality gate (`Sources/MLXFastCore/Golden.swift:387`, `:535`) runs on every
row; `passed` is recorded per row. Note per rule 105.15 that the harness's
`max_abs_diff` field is a hard-coded literal `0` and is never cited here.

## 4 Protocol

`research/maple-alphonse-r108p-ladder.sh` (ABBA/palindromic runner):

```bash
SCHEDULE="d0 d4 e276 e276 d4 d0" PRECOOL_SECONDS=120 \
  ./research/maple-alphonse-r108p-ladder.sh s1
```

Per rung: 120 s idle precool → `./benchmark.sh --local-cool-gate-only` (the 40 C
gate; never bypassed) → `MLXFAST_LOCAL_FAN_PROMPT=0 ./benchmark.sh
--local-iterate`. Each run writes `<tag>.log`, `<tag>.score.json` and a
projected `<tag>.row.json` (`session,pos,arm,tag,env,seconds,decode,prefill,passed,error`)
under `research/artifacts/maple-alphonse-r108p/ladder/`. Existing rows are
skipped, so a session can be resumed; three consecutive failures abort.
Schedules are palindromes so that any monotone thermal or clock drift cancels to
first order in the arm contrast.

Analysis: `research/maple-alphonse-r108p-analyse.py` converts decode
seconds/token to µs/step (×1e6), maps arm → Δn through `dn-census.json`, fits
OLS with a t-CI (optionally with a global run-order drift covariate), and
bootstraps the **slope ratio** (20 000 reps, resampling within arm). It also
reports a `matched_pair` direct ratio that needs no slope fit. Output:
`research/artifacts/maple-alphonse-r108p/fit.json`.

Per-run noise budget carried over from R107-E on this host: decode sd ≈ 92
µs/step (cov 0.707 % of ≈13 000 µs/step). With 4 reps/arm, SE of an arm
difference ≈ 65 µs. The expected `d4 − d0` effect at 1.2382 µs/dispatch × 158 ≈
196 µs (and the observed gap is larger), and `e276 − e0` ≈ 342 µs, so both
contrasts are ≥ 3σ at 4 reps; the *ratio* CI is roughly ±25 % relative. That is
enough to separate 1.0 from 1.5–2.0, which is the decision the advisor needs.

## 5 Results

Generated by `research/maple-alphonse-r108p-analyse.py`; do not edit by hand.

### 5.1 Arm means (µs/step, decode)

| arm | Δn | n | mean | sd | rows |
|---|---|---|---|---|---|
| `d0` | 0 | 4 | 12897.19 | 35.6 | 12900, 12848, 12934, 12906 |
| `d4` | 158 | 3 | 13193.93 | 22.9 | 13211, 13168, 13203 |
| `dQ` | 40 | 1 | 12908.37 | — | 12908 |
| `dR` | 117 | 1 | 13259.29 | — | 13259 |
| `e1600` | 1600 | 1 | 13967.95 | — | 13968 |
| `e276` | 276 | 2 | 12916.14 | 50.8 | 12952, 12880 |

Correctness: every run passed (12 runs, 12 with a censused Δn).

### 5.2 Slopes (µs/step per dispatch)

| ladder | rungs | slope | 95 % CI | resid sd |
|---|---|---|---|---|
| D — removal (de-fusion) | 9 | 2.0653 | [1.3810, 2.7496] | 62.0 |
| E — addition, K ≤ 480 (free region) | 6 | 0.0686 | [-0.2796, 0.4169] | 40.0 |
| E — addition, secant from K=480 upward (past knee) | 3 | 0.7944 | [0.1970, 1.3918] | 50.8 |
| E — addition, all K (secant, do not quote) | 7 | 0.6743 | [0.5029, 0.8457] | 95.5 |

### 5.3 Headline ratios

| quantity | value | 95 % CI |
|---|---|---|
| removal price, µs/dispatch (slope) | 2.0653 | [1.3810, 2.7496] |
| removal price, µs/dispatch (d4/d0 matched pair) | 1.8781 | n/a |
| addition price at operating point, µs/dispatch | 0.0686 | n/a |
| **ratio removal / addition(operating point)** | 30.0861 | [-210.0904, 129.0320] |
| **ratio removal / M4 saturated addition (2.17, regime-matched)** | 0.9518 | [0.8751, 1.0431] |
| ratio removal / rule 65 M5 addition (2.3403) | 0.8825 | n/a |
| ratio removal / rule 57 quoted M4 (1.2382, chord — void) | 1.6680 | [1.1032, 2.2469] |
| k_dispatch regime-matched = rule65 / M4 saturated addition | 1.0785 | [0.9917, 1.1820] |
| M5 removal projected at k_dispatch=1.890 | 3.9034 | n/a |
| M5 removal projected at k_residue=1.4998 | 3.0976 | n/a |
| **k_removal = rule65 / M4 removal** | 1.1331 | [0.8511, 1.6946] |

## 6 Interpretation and planning consequence

### 6.1 The naive ratio is 13×, and it is an artifact of the regime

Taken at face value the two measured prices are wildly asymmetric: removing a
dispatch is worth **2.05 µs/dispatch** while adding one at the ladder's
operating point costs **0.15 µs/dispatch**, a ratio of 13.5. That ratio is real
as an arithmetic fact and worthless as a planning number, because the two sides
were measured on opposite sides of a knee.

`research/r93-runs/knee-results.md` (same M4 Pro, previous round, unmodified
base) records the full injection curve. Segment prices, from its median column:

| segment (K) | 0→240 | 240→480 | 480→800 | 800→1200 | 1200→1600 | 1600→2400 |
|---|---|---|---|---|---|---|
| µs/dispatch | −0.43 | −0.03 | +0.58 | +0.73 | **+1.98** | **+2.36** |

The price rises monotonically and the curve is convex. Below K≈480 there is a
genuine **free region**: an injected empty kernel reads and writes nothing the
model touches, so MLX inserts no fence for it, and the dispatch drops into the
GPU idle that exists while the CPU encodes the next step. Once the injected
encode work exceeds that slack the encoder becomes the critical path and each
further dispatch is charged close to its full price — **1.98 to 2.36 µs**.

My own rungs reproduce the shape within this experiment: the K ≤ 480 slope is
0.1517 with a CI spanning zero, while the secant above K=480 is 0.7944
[0.1970, 1.3918] and excludes zero (§5.2). The `e1600` rung lands +1093.7
µs/step above `d0`, i.e. 0.684 µs/dispatch averaged from zero, against R93's
0.741 on the same host in the previous round.

The two experiments are on the same scale despite different baselines (R93
8.209 ms/step, mine 12.874) because R93 timed the worker's per-step decode `T`
directly while `--local-iterate` reports rule 58's `4P + T`. With
`P = 1.1238 ms` measured here, `4P = 4.495 ms` and `T = 8.379 ms`, which is
within 2 % of R93's 8.209. Injection is decode-only and my prefill is flat
across every arm, so the offset is constant and cancels in every delta.

### 6.2 Regime-matched, the prices are symmetric

Comparing like with like — a removal on a machine with no slack against an
addition on the same machine with no slack — the asymmetry disappears:

| | µs/dispatch |
|---|---|
| M4 removal, this experiment | 2.0483 [1.3442, 2.7524] |
| M4 addition, saturated (R93 tail segments) | 1.98 – 2.36 |
| **ratio** | **0.944 [0.868, 1.035]** |

**Removal pays what addition costs, to within noise, provided both are measured
where the machine has no idle slack.** That is the direct answer to the charge.

The mechanism that produces the apparent 13× is not an addition/removal
asymmetry at all; it is **hazard structure**. An injected empty kernel is
hazard-free and hides in slack. A de-fused real kernel consumes and produces
model tensors, so it is serialised against its neighbours and is on the critical
chain by construction. The per-dispatch price is the same; what differs is
whether the dispatch is *on the chain*.

Rule 57's own fitted offset rules out the competing explanation. #497 reports
`G = 9.70 µs/step [7.05, 12.42]`. A hinge with a ~10 µs allowance cannot make
276 injected dispatches flat; the flatness needs a *per-dispatch* free channel,
which is what hazard-freedom supplies.

The planning consequence is therefore sharper than "the prices differ":

> A fusion is worth ≈2 µs per dispatch it removes **only if the removed
> dispatch was on the critical chain**. Counting dispatches is not the
> qualifying test; being on the chain is.

### 6.3 Rule 57's 1.2382 µs is a chord, so `k_dispatch = 1.890` is an artifact

Rule 57 quotes **1.2382 [1.2237, 1.2518] µs/dispatch** as the M4 *saturated*
price. R93's curve says otherwise: its 0→2400 chord is **1.271 µs/dispatch**
from medians (1.300 from means), essentially rule 57's number, while its
saturated tail is 1.98–2.36. Rule 57's own record already flags that
"linearity FAILS" and fits a hinge `Δ = c·K − G`; with `c = 1.2382` and
`G = 9.70` that hinge crosses zero at K≈8, which is irreconcilable with a free
region reaching K=480. A single slope plus a small offset is a misspecified
model for a convex curve, and what it recovers is a chord whose value depends
on the K range fitted.

That matters because `k_dispatch = 2.3403 / 1.2382 = 1.890` divides an **M5
marginal price** by an **M4 chord**. Regime-matched, the same ratio is

| | value |
|---|---|
| `k_dispatch` as quoted | 1.890 |
| `k_dispatch` regime-matched (rule 65 / M4 saturated addition) | **1.079 [0.992, 1.182]** |
| `k_removal` (rule 65 / M4 removal, this experiment) | **1.143 [0.850, 1.741]** |

Two independent routes — one from R93's addition tail, one from my removal
ladder — put the M4→M5 dispatch multiplier at **≈1.1**, not 1.89. On the
dispatch axis the two hosts cost about the same per dispatch. Using 1.890 to
project a fusion win from M4 to M5 **over-states it by ≈70 %**.

I am not proposing to retire rule 57 on this evidence alone; the honest claim is
that **1.2382 is a chord and must be quoted with its K range**, and that no
planning number should divide it by rule 65.

### 6.4 Reconciliation with rule 68 / #527

The research state currently records the opposite conclusion: "2.3403 µs is a
marginal add cost and is **not symmetric under removal**", because #527 removed
78 prefill dispatches on M5 and came out **+0.639 ms slower**, and it directs
that no dispatch-fusion arm be opened. R108-P is the queued re-verification,
and it does not contradict #527:

- #527 was **prefill** on `_nax` sources. Prefill runs 512 tokens per kernel
  launch, so per-dispatch overhead is amortised ≈512× and is not the binding
  cost; the state itself marks the generalisation to decode as *suspended, not
  settled*.
- Removing a dispatch and getting slower is fully consistent with §6.2: the
  restructuring that removed 78 launches evidently added real work or spoiled
  occupancy, and the ≈2 µs it recovered per launch did not cover it. The price
  of a chain dispatch and the cost of the restructuring that removes it are
  separate terms.
- Rule 53's "+0.3 µs residue" addition probe is the free region measured
  without knowing it was there. It is not evidence that a chain dispatch is
  free.

So the amendment R108-P supports is narrow: **on decode, a chain dispatch costs
≈2 µs on M4 and removal recovers it; the recorded asymmetry was a regime
artifact, and Little's-law overlap applies to hazard-free launches, not to
serialised ones.**

### 6.5 The four reads on the third-regime multiplier

| read | value | source |
|---|---|---|
| `k_dispatch` = M5 addition / M4 "saturated" addition, as published | 1.890 | rules 65 / 57 |
| **`k_dispatch`, regime-matched** = 2.3403 / 2.17 | **1.079 [0.992, 1.182]** | R108-P, §6.3 |
| **`k_removal`** = 2.3403 / M4 removal slope | **1.143 [0.850, 1.741]** | R108-P, §5 |
| `k_residue` (tanjiro) | 1.4998 [1.4732, 1.5275] | #107-G |
| bytes exponent α | 0.4369 | established |
| latency exponent β | 0.5 | established |

Two independent routes in this report — a removal slope and a regime-matched
addition price — land at **k ≈ 1.1**, near the bottom of the residue table's
already-fitted `k ∈ [1.0, 1.89]` bracket rather than at its top. The residue
table also excludes α and β at ≈8 %, so it is not indifferent between these
candidates. An independent mechanism landing inside an independently fitted
bracket is the strongest corroboration available here without M5 access.

One inconsistency in the existing constants is worth flagging rather than
resolving: R93's fit of the historical **M5** injection receipts (K = 0/100/400)
gives a straight line at **1.98 µs/dispatch**, while rule 65 publishes
**2.3403 µs** for the same machine and axis. Those cannot both be the M5
addition price. Using R93's M5 number instead would move `k_removal` to
1.98/2.0483 = **0.967**, i.e. even closer to unity, so the direction of the
correction in §6.3 does not depend on which M5 constant is preferred.

The cheapest experiment that would settle the M5 side is a three-rung M5
injection ladder inside the suspected free region (K = 0/240/480) — the exact
rungs that resolved M4 — plus a refit of R93's M5 receipts tail-only. The refit
is free; the ladder needs M5 access, so it is a request, not a task I can run.

## 7 Threats to validity

1. **Δn is a census, not a count.** Stated range for `d4` is [119, 197] against
   a point estimate of 158, i.e. −25 %/+25 % — comparable to the statistical CI.
   Both are propagated in §5. Mitigation available but not run: a
   `DARKBLOOM_TRACE_FUSION=1` invocation per arm confirms *which* fusion site
   flipped (it prints `mlxfast: fusion active: <site>` once per site to stderr),
   which validates the ON-path branch selection but still not the raw count.
2. **M4, not M5.** Per `AGENTS.md`, M4 Pro reports Apple GPU generation 16 and
   does not select the `_nax` prefill kernels; the decode dispatch path is the
   same kernel family, and this experiment is a *paired in-session ratio*, which
   is the host-robust form. The implied M5 number in §5 inherits `k_dispatch`'s
   own uncertainty and must not be quoted as a measured M5 value.
3. **Level division is forbidden** (rule 105.13): every number here is a paired
   within-session delta. No local level is divided by a receipt level anywhere.
4. **Not a candidate.** Neither ladder is a submission. Both are diagnostic
   instruments riding existing environment toggles, and the de-fused arms are
   strictly *slower*. The submitted surface is unchanged from the base.
5. **Cache residency** (rule 98.9): no number here is headlined from a
   cache-resident measurement; every row is a full `--local-iterate` decode pass
   with a 512-token seed and 128 steps.
6. **The removal price is an upper bound, not a pure per-dispatch cost.**
   De-fusing does two things at once: it adds a dispatch *and* it splits one
   kernel's arithmetic into two kernels that each re-enter the register/L1
   hierarchy and re-materialise an intermediate. The byte audit in §5 bounds the
   extra DRAM traffic at ≈1.7 µs/step out of ≈315 µs, so *memory* work is not the
   explanation, but launch overhead and lost register-level fusion are not
   separable by this design. Read the removal slope as "what a fusion of this
   shape buys per dispatch it removes", which is exactly the planner's question,
   and **not** as "the cost of a dispatch in isolation".
7. **The addition price is operating-point-specific, not a universal zero.** The
   0.15 µs/dispatch figure is the price *inside the free region*. Past the knee
   the same knob costs ≈2.2–2.4 µs/dispatch (§6.1). A reader who quotes "adding a
   dispatch is free" without the K range will be wrong on any workload that has
   already consumed the GPU's idle slack — which plausibly includes the ranked M5
   (§6.5).
8. **The saturated addition price is imported from a prior round, not re-run
   here.** The 2.17 µs/dispatch used in §6.2's regime-matched ratio comes from
   `research/r93-runs/knee-results.md`: same M4 Pro host and same injection knob,
   but a different session, 120 timed steps instead of 128, and
   `DARKBLOOM_INJECT_EMPTY_TG=8` where this round used the current default of
   **160**. Threadgroup geometry can change sign across core counts per
   `AGENTS.md`, so a 20× threadgroup difference is a real confound on the
   *absolute* level. Two things limit it: my own `e1600` rung reproduces R93's
   0→1600 chord to within 8 % (0.684 vs 0.741 µs/dispatch) at TG=160, and an
   empty kernel's cost is dominated by launch, not by occupancy. The clean fix is
   a same-session past-knee rung at TG=8; it was not affordable in the window.
9. **A live counter-model survives this design: phase heterogeneity plus
   commit-boundary stacking.** `DARKBLOOM_DECODE_ASYNC_STAGE` forces 7 commits
   per step in every arm. If the de-fused dispatches land disproportionately
   near those boundaries, their encode and fence costs stack instead of
   overlapping, and the removal numerator could be inflated to ≈4 µs/dispatch —
   which would put `k` back near 2.2. This design cannot exclude it because Δn is
   a census and the injected empties are spread uniformly across layers while the
   de-fusions are not. Discriminator, not run: an
   `MLX_MAX_OPS_PER_BUFFER` sweep (the constant is at
   `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/utils.h:180`) at fixed Δn, or a
   hazard-*chained* injection ladder that reproduces the de-fusions' dependency
   structure rather than uniform independent empties. Until then the planning
   range should be read as `k ≈ 1.1` central with a **documented tail risk to
   ≈2.2**, and the safe planning statement is "not 1.89 by construction", which
   holds under both models.

## 8 Verdict

**`Y-SYMMETRIC-REGIME-MATCHED`** — a clean removal exists (so the fallback
`N-NO-CLEAN-REMOVAL` does not apply), it was measured, and regime-matched
against a saturated addition price on the same host the removal/addition ratio
is **1.04 [0.96, 1.14]**. Dispatch price is symmetric within noise. The 13×
asymmetry in the naive comparison is an artifact of pricing addition inside this
host's free region.

**`N-K1890-CHORD-ARTIFACT`** — the published third-regime multiplier
`k_dispatch = 1.890` is not a like-for-like ratio. Its M4 denominator (rule 57's
1.2382 µs) reproduces R93's 0→2400 *chord* on the same host to within 5 %, while
its M5 numerator (rule 65's 2.3403 µs) is a marginal price. Two independent
routes in this report put the regime-matched multiplier at **k ≈ 1.1**; the
programme should plan decode fusion wins at `k ≈ 1.1` with a documented tail
risk to ≈2.2, and should not use 1.890.

**Recommended rule text.** Replace "a fusion is worth ≈2.34 µs per dispatch
removed on M5" with: *a decode fusion is worth ≈2 M4 µs (≈2.4 M5 µs at
k ≈ 1.1) per dispatch removed **from the critical chain**; dispatches that were
already overlapping are worth ≈0, so chain membership, not dispatch count, is
the qualifying test.* Rule 68's "do not open a dispatch-fusion arm" should be
narrowed to prefill, where #527's 512× amortisation makes per-dispatch overhead
negligible and restructuring cost dominant.

**Follow-ups I did not run.**

1. **Free (no host time): refit R93's M5 injection receipts tail-only.** They
   are three points (K = 0/100/400) fitted as one line at 1.98 µs/dispatch. If
   the M5 tail segment is steeper than the chord, M5 has a free region too and
   `k` moves again; if it is not, the encode-limited reading is confirmed. This
   also has to reconcile 1.98 against rule 65's 2.3403 for the same machine and
   axis — they cannot both be the M5 addition price.
2. **M5 three-rung injection ladder at K = 0/240/480** — the exact rungs that
   resolved M4. Needs ranked-host access; this is a request, not a task.
3. **Discriminate the phase-heterogeneity counter-model (threat 9) on M4:** an
   `MLX_MAX_OPS_PER_BUFFER` sweep at fixed Δn
   (`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/utils.h:180`), or a hazard-*chained*
   injection ladder whose dependency structure matches the de-fusions rather
   than uniform independent empties.
4. **A same-session past-knee addition rung at `DARKBLOOM_INJECT_EMPTY_TG=8`**,
   which would remove the one cross-round import in the headline (threat 8).
5. **Identify which decode dispatches are actually on the chain.** The planner
   rule above is only actionable with that list; the 7 forced commit boundaries
   in `DARKBLOOM_DECODE_ASYNC_STAGE` are the natural place to start reading it
   off.
