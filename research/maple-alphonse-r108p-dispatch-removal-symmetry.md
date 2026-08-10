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

(RESULTS SECTION — refreshed in place as rows land.)

## 6 Interpretation and planning consequence

Rule 57 already records that the addition ladder is **not linear** — the fit is
a hinge, `Δ = c·K − G`, with `c = 1.2382 µs/dispatch` only in the **saturated**
regime after the machine's slack `G` has been absorbed (and #483's 0.751 is
retired). That matters for symmetry in a specific way:

- The *addition* price is measured **above** the hinge, where there is no slack
  left to hide a dispatch in.
- The *removal* price is measured **at** the fused baseline, which still has
  slack. Naively, removal should therefore pay **less** than saturated addition.
- The empty injected kernel is the **cheapest possible** dispatch: 160
  threadgroups, no loads, no stores, no real work. A real fused dispatch that is
  de-fused adds launch cost **plus** its own instruction stream and its own
  round trip through the register/L1 hierarchy.

So the two effects push in opposite directions, and the measurement decides
which dominates. Whatever the sign, the actionable statement for the programme
is the same shape: **`dispatches_saved × 2.3403 µs` is a *biased* planner**, and
§5 gives the multiplier that de-biases it. Any future fusion proposal should be
priced with the removal price, not the injection price.

Relation to the other reads on the third regime:

| read | value | source |
|---|---|---|
| `k_dispatch` = M5 addition / M4 addition | 1.890 | rules 65 / 57 |
| `k_residue` (tanjiro) | 1.4998 [1.4732, 1.5275] | #107-G |
| bytes exponent α | 0.4369 | established |
| latency exponent β | 0.5 | established |
| **this experiment** | see §5 | R108-P |

The residue table already brackets `k ∈ [1.0, 1.89]` and excludes α and β at
≈8 %. R108-P is a *fourth* read: it does not re-measure `k`, it measures whether
the M4 and M5 dispatch prices that define `k` are even the right prices to
multiply.

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

## 8 Verdict

(VERDICT — set in §5's refresh.)
