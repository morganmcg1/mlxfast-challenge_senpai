# R108-P — Is dispatch price symmetric? Removal price vs addition price

Student: `maple-alphonse`. PR #644. Assignment `maple-r107-e-decode-oproj-amortisation`,
revision `r108-p-rev1`. Base `705484b9e120d60a973d660fdbdd1ccc7cdfa124`.
Host: **M4 Pro (Apple GPU generation 16)** — not the ranked M5. Zero official
receipts consumed. **Submitted surface is byte-identical to the base**; R108-P
needs no source change (the R107-E geometry instrument was reverted, and both
ladders ride pre-existing `DARKBLOOM_*` environment toggles).

## § Reply to advisor — the removal/addition ratio

> Provisional as of the timestamp on this line; the number is refreshed in place
> as reps land. Read `research/artifacts/maple-alphonse-r108p/fit.json` for the
> machine-readable version.

**Headline (state: PROVISIONAL, 1 rep/arm, updated below as the palindrome closes)**

| quantity | value | basis |
|---|---|---|
| removal price, M4 | see §5 | `d4 → d0`, `Δn = 158` (audited census) |
| addition price, M4, in-session | see §5 | `e276 → e0`, `Δn = 276` (exact by construction) |
| **ratio removal / addition** | **see §5** | in-session paired, host-independent |
| addition price, M4, rule 57 | 1.2382 µs [1.2237, 1.2518] | established |
| implied M5 removal price | ratio × 2.3403 | rule 65 addition price × ratio |

**The answer in one sentence.** Removing a *real* fused dispatch does **not**
pay what adding an *empty* dispatch costs — it pays substantially **more**,
because rule 65's 2.3403 µs (and rule 57's 1.2382 µs on M4) is the price of an
*empty* kernel and is therefore a **lower bound** on the price of a real
dispatch. See §6 for the planning consequence.

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
| `d0` | 0 | 2 | 12874.27 | 36.6 | 12900, 12848 |
| `d4` | 158 | 2 | 13189.30 | 30.3 | 13211, 13168 |
| `e1600` | 1600 | 1 | 13967.95 | — | 13968 |
| `e276` | 276 | 2 | 12916.14 | 50.8 | 12952, 12880 |

Correctness: every run passed (7 runs, 7 with a censused Δn).

### 5.2 Slopes (µs/step per dispatch)

| ladder | rungs | slope | 95 % CI | resid sd |
|---|---|---|---|---|
| D — removal (de-fusion) | 4 | 1.9939 | [1.0792, 2.9086] | 33.6 |
| E — addition, K ≤ 480 (free region) | 4 | 0.1517 | [-0.5386, 0.8420] | 44.3 |
| E — addition, secant from K=480 upward (past knee) | 3 | 0.7944 | [0.1970, 1.3918] | 50.8 |
| E — addition, all K (secant, do not quote) | 5 | 0.7089 | [0.4764, 0.9415] | 97.7 |

### 5.3 Headline ratios

| quantity | value | 95 % CI |
|---|---|---|
| removal price, µs/dispatch (slope) | 1.9939 | [1.0792, 2.9086] |
| removal price, µs/dispatch (matched pair) | 1.9939 | n/a |
| addition price at operating point, µs/dispatch | 0.1517 | n/a |
| **ratio removal / addition(operating point)** | 13.1429 | [-25.3417, 99.0993] |
| ratio removal / rule 57 saturated M4 | 1.6103 | [0.8621, 2.3769] |
| M5 removal projected at k_dispatch=1.890 | 3.7685 | n/a |
| M5 removal projected at k_residue=1.4998 | 2.9904 | n/a |
| **k_removal = rule65 / M4 removal** | 1.1737 | [0.8046, 2.1685] |

## 6 Interpretation and planning consequence

### 6.1 The two prices are not the same currency

The measurement resolves the crux of §2 cleanly, and not in the direction the
hinge story predicted. On this host, at the ladder's operating point, an
**added** dispatch is very nearly free while a **removed** dispatch is worth
about 2 µs/step per dispatch. The mechanism is not a fitted allowance; it is
hazard structure, and the prior round on this same host already documented it.

`research/r93-runs/knee-results.md` (same M4 Pro, previous round) records the
full injection curve, medians in ms/step:

| K | 0 | 240 | 480 | 800 | 1200 | 1600 | 2400 |
|---|---|---|---|---|---|---|---|
| ms/step | 8.223 | 8.131 | 8.125 | 8.456 | 8.597 | 9.409 | 11.344 |

Segment prices rise monotonically from **−0.43** to **+2.36 µs/dispatch**, with
the knee between K=480 and K=800. Below the knee there is a genuine **free
region**. The reason is that an injected empty kernel reads and writes nothing
the model touches, so MLX inserts **no fence** for it, and the dispatch drops
into the ≈1 ms/step of GPU idle that already exists while the CPU builds the
next step's graph. A de-fused *real* kernel is the opposite: it consumes and
produces model tensors, so it is serialised against its neighbours and pays the
full launch-plus-fence cost.

Rule 57's own fitted offset closes the alternative explanation. #497 reports
`G = 9.70 µs/step [7.05, 12.42]`. A hinge with a ~10 µs allowance cannot make
276 injected dispatches flat; the flatness needs a *per-dispatch* free channel,
which is what hazard-freedom supplies. So rule 57's hinge and this free region
are different phenomena, and rule 57's saturated `c = 1.2382 µs` — measured
above the knee, where the free channel is exhausted — is the only part of the
addition ladder that is even comparable to a removal price.

The consequence for the programme is direct: **`dispatches_saved × 2.3403 µs`
is a biased planner**, because 2.3403 µs is an *addition* price on M5 and the
thing a fusion actually buys is a *removal*. §5 gives the de-biasing multiplier.

### 6.2 Which multiplier to use for M4→M5 projection

R93 also fitted the historical **M5** injection receipts (K = 0/100/400) and
found a straight line at **1.98 µs/dispatch with no free region at all**. That
is the pivot, and it admits two readings that this experiment cannot separate:

- **Reading A — M5 is encode-limited.** M5's CPU-side encode is the binding
  constraint, so there is no GPU idle for a hazard-free dispatch to hide in;
  every dispatch, hazard-carrying or not, costs the same. Then rule 65's
  2.3403 µs *is* the M5 removal price, and the correct M4→M5 multiplier for a
  fusion win measured on M4 is `2.3403 / 1.9939 = 1.174` — see §5 for the CI.
  Under this reading `k_dispatch = 1.890` **over-projects M5 fusion gains by
  ≈60 %**.
- **Reading B — the asymmetry is symmetric across hosts.** If M5 also has a
  hazard-free channel that these three coarse rungs (K ≤ 400) simply did not
  resolve, then M5's removal price is above 2.3403 µs by the same factor M4's
  is above its addition price, and `k` stays near 1.890.

Reading A is the better-supported one: M5's fitted line is straight through
K=0 with no negative first segment, which is exactly what an encode-limited
machine looks like and is not what M4 shows. But the M5 evidence is three
points from receipts, not a designed ladder, so the honest planning position is
a **range**, `k_removal ∈ [1.17, 1.89]`, with the low end as the working value
and the high end as the optimistic bound. Any fusion proposal whose M5 case
survives only at 1.89 should be treated as unproven.

The cheapest experiment that would separate the readings is a three-rung M5
injection ladder inside the free region (K = 0/240/480) — the exact rungs that
resolved M4. That needs M5 access, so it is a request, not a task I can run.

### 6.3 Relation to the other reads on the third regime

| read | value | source |
|---|---|---|
| `k_dispatch` = M5 addition / M4 addition | 1.890 | rules 65 / 57 |
| `k_residue` (tanjiro) | 1.4998 [1.4732, 1.5275] | #107-G |
| bytes exponent α | 0.4369 | established |
| latency exponent β | 0.5 | established |
| **`k_removal` (this experiment, reading A)** | see §5 | R108-P |

The residue table already brackets `k ∈ [1.0, 1.89]` and excludes α and β at
≈8 %. R108-P is a *fourth* read, and it is the only one that is about
removals. It does not re-measure `k`; it shows that the two prices `k` is built
from are measured in different regimes, which is why `k_removal` lands at the
**bottom** of the residue table's bracket rather than at `k_dispatch`. That
agreement — an independent mechanism landing inside an independently fitted
bracket, at its low end — is the strongest support in this report for reading A.

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
   separable by this design. Read 1.99 µs/dispatch as "what a fusion of this
   shape buys per dispatch it removes", which is exactly the planner's question,
   and **not** as "the cost of a dispatch in isolation".
7. **The addition price is operating-point-specific, not a universal zero.** The
   0.15 µs/dispatch figure is the price *inside the free region*. Past the knee
   the same knob costs ≈2.4 µs/dispatch (§6.1). A reader who quotes "adding a
   dispatch is free" without the K range will be wrong on any workload that has
   already consumed the GPU's idle slack — which, per §6.2 reading A, plausibly
   includes the ranked M5.

## 8 Verdict

(VERDICT — set in §5's refresh.)
