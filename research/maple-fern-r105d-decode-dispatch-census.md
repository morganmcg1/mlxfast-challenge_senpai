# r105-D — Decode dispatch / occupancy / byte census

- **Student:** maple-fern
- **Assignment:** `maple-r105-d-decode-dispatch-occupancy-census`, revision `r105-d-rev1`
- **PR:** #603, branch `maple-fern/r105-decode-dispatch-occupancy-census`
- **Base:** `codex/mlxfast-maple-20260804-advisor` @ `5f7861c0981278929c3ef43d54a6d5bca10a8659`
- **Phase:** A only. **Zero official receipts consumed. No Phase B was requested or run.**
- **Host used for all derived timing:** Apple **M4 Pro, 20 GPU cores, 48 GiB** (`applegpu_g16s`, GPU
  generation 16). Ranked host is M5 Max, C = 40 cores.

## Outcome

**N-1 — the pool does not exist.**

The advisor's occupancy headlines are, as *counts*, exactly correct: 84 of 408 decode dispatches run
on a single threadgroup, 203 of 408 cannot fill even one threadgroup per core on the ranked
40-core M5, and the step launches 327,395 threadgroups. I confirmed all three to the digit. But the
implied lever — that this under-occupancy is a recoverable pool worth ~955 µs/step — **does not
survive contact with measurements that already exist in this repository.** The best-supported bound
on the single-TG mechanism is **9.1 µs/step = 0.138 % of `cs`**, which is **3.6× below** the +0.5 %
V-POOL bar. Nothing in the ranked mechanism ledger clears the bar.

Three N-3 contradictions fell out of the census and are recorded in §7. The most useful is that
**occupancy is anti-correlated with cost**: the under-occupied half of the step carries 8.2 % of the
bytes, and the well-occupied half carries 91.8 %.

---

## 0. Zero-byte proof

Per the assignment, this experiment commits **zero bytes** under `Sources/` or `Vendor/`. Everything
lives in `research/`.

```console
$ git diff --numstat 5f7861c0981278929c3ef43d54a6d5bca10a8659 HEAD -- Sources Vendor
$ echo "exit=$?"
exit=0
```

The command produces no output: no file under either tree differs from the base. Nothing on the
submitted surface was touched, so no editable-byte budget was consumed.

## 1. Method and provenance

The census is derived, not newly measured. Its inputs are:

1. **Dispatch traces from r105-C** (`/tmp/r105c/dump/{arm}/dispatch.tsv`, 10 arms, ~92 MB), produced
   by the `SPLIT=1` instrumentation in `research/r103b/scripts/trace.patch`. Each row carries the
   pipeline label, grid thread extent, and threadgroup extent for one dispatch.
2. **The r101 byte model** (`research/fern_r101_byte_audit.py`), imported directly rather than
   re-derived, so the 15 spine families keep byte-identical accounting with the earlier audit
   (HEAD epoch, `lmhead_mb = 109.182976`).
3. **Previously published elasticities** from PR #483, PR #218, PR #196, PR #158, PR #502 and #527.

Scripts (both run clean, both committed):

- `research/fern_r105d_census.py` → `research/artifacts/fern-r105d/decode-dispatch-census.csv`
  (per-ordinal **and** per-family rows) and `.../decode-occupancy-summary.json`.
- `research/fern_r105d_bytes.py` → `research/artifacts/fern-r105d/decode-byte-census.json`
  (every row carries its arithmetic as a string, so each number can be re-checked by eye).
- `research/fern_r105d_wandb_log.py` → the W&B run in §9.

### 1.1 Step isolation

The step boundary marker is the pipeline whose label starts with
`custom_kernel_laguna_decode_embedding_rope_atlas` (the live name carries a long type suffix, so the
match is a prefix match). Inter-marker interval lengths for the `a_base` arm are

```
[1759, 528, 408, 408, 408]
```

The first two intervals are the 512-token prefill and the warm-up transient. The census takes the
**last complete** interval, i.e. a fully steady-state 408-dispatch decode step. All ten r105-C arms
satisfied the §8 stopping rule in the prior session.

### 1.2 Residency model, and where it is not verified

Two rival models of how many threadgroups a core holds concurrently were considered.

- **Simdgroup model:** `R = floor(96 / simdgroups_per_TG)`. Validated at two independent points:
  PR #196 (1024 thr/TG = 32 simdgroups → 3 TG/core) and PR #138 (128 thr/TG = 4 simdgroups →
  24 TG/core). Both give exactly 96 resident simdgroups per core.
- **Hard cap model:** 24 TGs/core regardless of size. Fits #138, **refuted by #196**.

I use the simdgroup model, but the CSV emits **both** columns
(`waves_resident_C40_R96simd`, `waves_resident_C40_Rcap24`) because at **64 threads/TG the two
models disagree and no measurement in the programme distinguishes them** (simd model R = 48,
cap model R = 24). That matters: 64-thread TGs are the dominant geometry of the step. Neither
column should be quoted as measured.

### 1.3 Rule 82b compliance

Every per-kernel label microsecond in this document comes from `SPLIT=1` profiling on M4 and is
therefore **shape only, never magnitude**. r93-C measured that `SPLIT=1` inflates the inter-dispatch
gap from 302 µs/step to 1261 µs/step — roughly **960 µs/step of profiler-imposed serialization**,
so a label-seconds argument will over-promise by ≈4×. Each label number below carries an inline
caveat, and the JSON artifact repeats the caveat string on every rolled-up row.

---

## 2. The census

### 2.1 Step structure (exact, trace-derived)

| Quantity | Value |
|---|---|
| Dispatches per decode step | **408** |
| Distinct kernel families | **25** |
| Threadgroup launches per step | **327,395** |
| GPU threads per step | **30,804,000** |
| Single-threadgroup dispatches | **84** (20.59 %) |
| Dispatches below 1 TG/core at C = 40 | **203** (49.75 %) |
| Dispatches below 1 TG/core at C = 20 | **124** (30.39 %) |
| Σ ⌈TGs/40⌉ over the step | **8,415** waves |
| Σ ⌈TGs/20⌉ over the step | **16,571** waves (ratio 1.969) |
| Σ resident waves at C = 40, simd model | **598** |

### 2.2 Family geometry

Sorted by threadgroup launches per step. `TG` = threadgroups per dispatch; `thr` = threads per
threadgroup; `sg` = simdgroups per threadgroup; `waves@40` = ⌈TG/40⌉.

| family (truncated) | calls | TG | thr | sg | TG-launches | class @ C=40 | waves@40 |
|---|---|---|---|---|---|---|---|
| `nvfp4_qkv_h64_r1_v1_lm1_pw1_se1_sd1…` | 30 | 5120 | 64 | 2 | 153,600 | SATURATING | 128 |
| `routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2…` | 39 | 2048 | 64 | 2 | 79,872 | SATURATING | 52 |
| `nvfp4_qkv_h48_r1_v1_lm1_pw1_se1_sd1…` | 10 | 4096 | 64 | 2 | 40,960 | SATURATING | 103 |
| `routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6…` | 39 | 512 | 288 | 9 | 19,968 | SATURATING | 13 |
| `shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1…` | 39 | 256 | 64 | 2 | 9,984 | SATURATING | 7 |
| `oproj_act_h64_v1_lm1_pw1_sc1_se1…` | 30 | 256 | 64 | 2 | 7,680 | SATURATING | 7 |
| `lmhead_int5_base_coarse_delta_bf16_v1…` | 1 | 6272 | 512 | 16 | 6,272 | SATURATING | 157 |
| `lmhead_exact_fused_int5_sparse_refine_v1…` | 1 | 3136 | 256 | 8 | 3,136 | SATURATING | 79 |
| `oproj_act_h48_v1_lm1_pw1_sc1_se1…` | 10 | 256 | 64 | 2 | 2,560 | SATURATING | 7 |
| `residual_rms_router_bf16_2048_rpg8_keys_v1_pf1…` | 39 | 32 | 512 | 16 | 1,248 | SUB_C_UNDERFILL | 1 |
| `sliding_fused_attn_ring_v1…` | 30 | 32 | 1024 | 32 | 960 | SUB_C_UNDERFILL | 1 |
| `full_fused_attn_grow_v1…` | 10 | 24 | 1024 | 32 | 240 | SUB_C_UNDERFILL | 1 |
| `gate_sp_h64_v1…` | 30 | 8 | 64 | 2 | 240 | SUB_C_UNDERFILL | 1 |
| `dense_gate_up_swiglu_bf16_v1…` | 1 | 128 | 512 | 16 | 128 | NEAR_C | 4 |
| `dense_down_residual_bf16_v1…` | 1 | 128 | 128 | 4 | 128 | NEAR_C | 4 |
| `lmhead_coarse_argmax_stage1_v5…` | 1 | 128 | 224 | 7 | 128 | NEAR_C | 4 |
| `gather_frontbfloat16_int32_int_2` | 2 | 49 | 1024 | 32 | 98 | NEAR_C | 2 |
| `gate_sp_h48_v1…` | 10 | 6 | 64 | 2 | 60 | SUB_C_UNDERFILL | 1 |
| `vn_copybfloat16float32` | 1 | 49 | 1024 | 32 | 49 | NEAR_C | 2 |
| `rmsbfloat16` | 41 | 1 | 512 | 16 | 41 | **SINGLE_TG** | 1 |
| `prefill_router_tournament_ordinal_norm_active64_v2…` | 39 | 1 | 256 | 8 | 39 | **SINGLE_TG** | 1 |
| `embedding_rope_atlas_bf16_2048_v2…` | 1 | 1 | 512 | 16 | 1 | **SINGLE_TG** | 1 |
| `residual_rms_bf16_2048_v1…` | 1 | 1 | 512 | 16 | 1 | **SINGLE_TG** | 1 |
| `lmhead_exact_winner_bf16_midpoint_threshold_v1…` | 1 | 1 | 32 | 1 | 1 | **SINGLE_TG** | 1 |
| `argmax_bfloat16` | 1 | 1 | 1024 | 32 | 1 | **SINGLE_TG** | 1 |

Σ TG-launches = **327,395**; Σ families = **25**. Both match the headline exactly.

Occupancy classes are defined against the ranked C = 40: `SINGLE_TG` (TGs == 1),
`SUB_C_UNDERFILL` (TGs < 40), `NEAR_C` (40 ≤ TGs < 160), `SATURATING` (TGs ≥ 160).

**The 84 single-TG dispatches decompose exactly as:** 41 `rmsbfloat16` + 39
`prefill_router_tournament…` + 1 `embedding_rope_atlas…` + 1 `residual_rms_bf16_2048_v1…` +
1 `lmhead_exact_winner…` + 1 `argmax_bfloat16` = 84.

**The 203 sub-C40 dispatches decompose exactly as:** the 84 above + 39 `residual_rms_router` +
30 `sliding_fused_attn` + 30 `gate_sp_h64` + 10 `full_fused_attn` + 10 `gate_sp_h48` = 203.

### 2.3 Byte census

Total traffic **1,671,402,432 B = 1671.40 MB/step**, of which the 15 r101 spine families account for
1,669,443,584 B (**99.883 %**) and the 10 newly-priced tail families for 1,958,848 B (**0.1172 %**).

| occupancy class | dispatches | % of 408 | bytes/step | % of bytes | label µs (M4, 82b — shape only) | % of label total |
|---|---|---|---|---|---|---|
| `SINGLE_TG` | 84 | 20.59 % | 600,512 | **0.0359 %** | 327.4 | 3.89 % |
| `SUB_C40` (all) | 203 | 49.75 % | 137,832,896 | **8.2465 %** | 1834.1 | 21.77 % |
| `AT_OR_ABOVE_C40` | 205 | 50.25 % | 1,533,569,536 | **91.7535 %** | 6589.6 | 78.23 % |

> **Rule 82b caveat, applying to both label columns above:** these are `SPLIT=1` M4 label seconds.
> They are an upper bound with unguaranteed sign and are used here **only** to establish the *shape*
> of the distribution across occupancy classes. They must not be read as a magnitude, and they must
> not be subtracted from or added to any score estimate.

### 2.4 Decode roofline

| row | value | arithmetic |
|---|---|---|
| Step bytes | 1,671,402,432 B | census sum over 408 dispatches |
| M5 measured DRAM bandwidth | 610.0 GB/s | published programme constant (Rule 80) |
| **M5 DRAM floor** | **2740.00 µs** | 1,671,402,432 / 610.0e9 |
| M5 ranked decode step | 4141.5 µs | programme reference |
| **DRAM floor as % of step** | **66.16 %** | 2740.00 / 4141.5 |
| Achieved bandwidth at ranked step | 403.6 GB/s | 1,671,402,432 / 4141.5e-6 |
| … as % of measured peak | 66.2 % | 403.6 / 610.0 |
| **Unattributed residual** | **1401.50 µs = 21.341 % of score** | 4141.5 − 2740.00 |
| Single-TG class DRAM floor | **0.98 µs** | 600,512 / 610.0e9 |

The residual row is the important one, and it must be read correctly:

> **An unattributed pool is not a lever.**

I flag that this exact sentence is **my paraphrase**, not a verbatim programme quotation. The
nearest verbatim precedent in the repository is
`RESEARCH_ARCHIVE_through-round-91.md:6785-6786`, which states that "prefill's unattributed
remainder is a **subtraction residual, not a pool**". The 1401.50 µs above is obtained by
subtracting a modelled floor from a measured step. It is an *upper bound on everything that is not
DRAM traffic* — dispatch overhead, dependency stalls, compute that is not bandwidth-bound, model
error in the 610 GB/s constant, and model error in the byte census, all summed with unknown signs.
Nothing in this experiment attributes any of it to a mechanism, and nothing licenses spending it.

Note also that **84 single-TG dispatches move 0.036 % of the step's bytes and have a DRAM floor of
under one microsecond.** Whatever they cost, it is not memory traffic.

---

## 3. Verdicts on the five advisor headlines

### H1 — "84 of 408 decode dispatches run on exactly one threadgroup" → **TRUE**

Confirmed exactly, with the decomposition in §2.2. No qualification.

### H2 — "203 of 408 dispatches are below one threadgroup per core at C = 40" → **TRUE**

Confirmed exactly, with the decomposition in §2.2. Worth adding that at C = 20 (this M4 host) the
count is only 124, so the under-occupancy headline is *more* severe on the ranked machine than on
the host where most of the programme's directional evidence is gathered. That is a genuine, if
uncomfortable, point in the hypothesis's favour — it just is not enough, per §4.

### H3 — "327,395 threadgroup launches per step" → **TRUE**

Confirmed exactly; Σ over the family table in §2.2 reproduces the number to the digit.

### H4 — "the 41 `rmsbfloat16` dispatches are a 95.9 µs/step launch tax" → **arithmetic TRUE, causally FALSE**

The arithmetic is right: 41 × 2.3403 µs (Rule 65) = **95.95 µs/step = 1.461 % of `cs`**.

The causal claim is not. Rule 65's 2.3403 µs is an **addition** price, calibrated by adding
dispatches to the M5. This headline applies it in the **removal** direction, and the programme has
already ruled that this inversion is invalid: Rule 68 / PR #527 is an M5 ranked receipt in which
removing **78 prefill dispatches cost +0.639 ms** (CI [+0.325, +0.953], t = 4.43, 12 dof, −0.242 %
score) — the opposite sign. The doctrine recorded from it is verbatim: *"'add a dispatch, pay
2.34 µs' holds; 'remove a dispatch, gain 2.34 µs' is refuted."*

Worse for this specific headline, **the family has already been measured directly, by me, in
PR #483** (`research/maple-fern-r91-input-norm-fusion-price.md:1-42`):

> Status: **terminal — the family is dead.** Stage 1 priced the fusion at **≤ 35.02 µs/step (95 %
> upper bound) ≈ 0.535 % score**.

That experiment added a whole redundant input-RMSNorm — **+80 dispatches/step, +19.7 %** — and
measured **+8.61 µs/step busy, CI [−17.71, +35.02]**. That is **0.108 µs per added dispatch, i.e.
4.6 % of Rule 65's 2.3403 µs**, on exactly this kernel family. Even taking the 95 % upper bound and
assuming perfect recovery, the mechanism's ceiling is 0.535 % of score at a transfer ratio of ≈0.25
to M5, i.e. ≈0.13 % expected. W&B: `ubjfsywa`.

So the 95.9 µs figure over-states the measured elasticity of its own family by **21.7×**.

### H5 — "`prefill_router_tournament` runs 39× on decode — a misnomer suggesting misrouting" → **TRUE as a naming fact, but it carries no lever**

The count is right: 39 calls/step on the decode path, one TG each, 256 threads.

But I read the source, and **the name is a pure kernel-naming artifact, not a routing bug**:

- `Sources/MLXFastModel/LagunaRuntimeModel.swift:9532` — `DARKBLOOM_DECODE_ROUTER_TOURNAMENT`
- `Sources/MLXFastModel/LagunaRuntimeModel.swift:10211` — `DARKBLOOM_PREFILL_ROUTER_TOURNAMENT`
- `:10113`, `:10122`, `:10131`, `:10140` — the Metal function declarations, all named
  `laguna_prefill_router_tournament_*`

Decode has its **own separate gate** and simply dispatches the shared Metal function, which happens
to carry the `prefill_` name from where it was first written. There is no misrouting to fix.

And even if there were, the kernel is already measured at zero marginal cost.
`research/maple-fern-decode-marginal-cost-ledger.md` (PR #218, same M4 host, 8.20 ms step) prices
`T0a_router_top8` at **0.00 ± 0.12 µs/call → 0 µs/step, elasticity E = 0.00**, absorbing **15.33
copy-sets (~2.85 ms)** of injected work before it costs anything. A 1-TG kernel sitting inside
~2.85 ms of slack is not on the critical path.

---

## 4. A4 — is the 955 µs/step dispatch tax additive or overlapped?

**Explicit answer: OVERLAPPED. It is not an additive 955 µs, and it is not recoverable.**

The nominal figure is real arithmetic: 408 dispatches × 2.3403 µs = **954.842 µs/step = 14.54 % of
`cs`**. Four independent lines of evidence say it does not sit on the critical path as a sum.

**(i) Conservation.** r93-C (PR #498, M4) measured the production inter-dispatch gap at
**302 µs/step** in the `off@nosplit` configuration, versus 1261 µs/step under `SPLIT=1`. The GPU
idle window in production is therefore ~302 µs/step. A claimed 955 µs/step tax cannot fit inside a
302 µs hole. Even under the maximally generous assumption that *every* idle microsecond is dispatch
tax, **at least 68.4 % of the 955 µs must be overlapped with GPU work.** Pro-rating the single-TG
share by the same factor caps it at 196.585 × (302/955) = **62.2 µs = 0.947 % of `cs`** — already
below the bar before any elasticity correction.

**(ii) Direct measurement of the absorption capacity.** r93-A measured that this M4 host absorbs the
first **~480 added dispatches free**. Production runs at 408 dispatches, which is *inside* that
absorption region. The step is not dispatch-rate-limited.

**(iii) The gap does not scale with dispatch count.** PR #158 (M4) measured the step-boundary gap at
265 ± 20 µs and the **per-dispatch coefficient on that gap at −0.12 ± 0.22 µs — a null**. Net
inter-dispatch residue is ≈37 µs/step. If 408 dispatches were charging 2.34 µs each into the gap,
this coefficient would have been strongly positive.

**(iv) Ranked-hardware evidence points the other way.** PR #527's M5 receipt removed 78 dispatches
and got **+0.639 ms slower**. PR #502 / Rule 53 closed the step with a 24-label ledger to
**+0.3 µs (+0.004 %) over 406/406 dispatches** — i.e. the labelled kernel work already accounts for
essentially the whole step, leaving no 955 µs additive gap to find.

I record two caveats against my own conclusion. `CURRENT_RESEARCH_STATE.md:2496` marks the
prefill→decode generalisation of Rule 68 as **"suspended, not settled"**, and
`advisor-r104:1269-1281` calls #527 confounded. So line (iv) is the weakest of the four. Lines (i),
(ii) and (iii) are M4-direct and do not depend on #527 at all, and they alone are sufficient.

---

## 5. Self-falsification: my own occupancy instrument over-predicts by 15.2×

Before trusting the census's occupancy model I applied it to the whole step as a sanity check. PR
#196's staircase is `T(K) = 1.661 + 7.408·⌈K/C⌉` µs. Summing that over all 408 dispatches at C = 40
gives a predicted step of **63,016 µs**. The actual M5 decode step is **4141.5 µs**.

**That is a 15.2× over-prediction.** The model is not merely imprecise; it is invalid at this scale.

The diagnosis is that `b = 7.408 µs/wave` was calibrated on **full attention** threadgroups, which
are 1024-thread, 32-simdgroup, heavily memory-bound units. It is the cost of *one full-attention
TG-wave*, not a generic per-wave price. Applying it to a 64-thread NVFP4 GEMV threadgroup charges
roughly 16× too much. The corollary is a rule I would state generally:

> **`waves × b` is not a cost model.** Wave counts are a shape statistic. Multiplying them by any
> single per-wave constant will mis-price the step unless every wave is the geometry that constant
> was calibrated on — and in this step, 8 distinct threadgroup geometries are in use.

This is also why §2.3's label-second column is reported with a rule-82b caveat rather than converted
into microseconds of opportunity.

---

## 6. Ranked mechanism ledger

Bar for V-POOL: **≥ +0.5 % of `cs` = ≥ 32.8 µs/step** at the M5 reference step of 4141.5 µs
(1 % of `cs` = 65.67 µs/step).

| # | mechanism | nominal | best-supported bound | verdict |
|---|---|---|---|---|
| **M1** | Fuse the 41 input RMSNorms into the QKV prologue | 95.95 µs (1.461 %) | **≤ 35.02 µs = 0.533 %** (95 % UB, PR #483), ≈0.13 % after M5 transfer | **NO-GO — already closed by #483** |
| **M2** | Widen / batch the 39 router tournaments | 91.27 µs (1.390 %) | **0.00 ± 0.12 µs/call measured** (PR #218), E = 0.00 | **NO-GO — bounded at zero before any code** |
| **M3** | Eliminate or merge all 84 single-TG dispatches | 196.59 µs (2.993 %) | conservation-capped 62.2 µs (0.947 %); **measured-elasticity 84 × 0.108 = 9.1 µs = 0.138 %** | **NO-GO — 3.6× below bar** |
| **M4** | Attention head-axis repartition / 1-head-per-TG | — | — | **OUT OF SCOPE** — forbidden by §0 item 4 (PR #196: the M5 does not charge for idle slots inside a wave); closed 3× (#103 at +20.1 % slower, #196, #205); the sliding-attention family is nezuko's dial (#584) |
| **M5** | Reduce bytes in the 205 at-or-above-C40 dispatches | — | this is where **91.75 % of bytes** and **78.23 % of label seconds** live | **not an occupancy lever** — pointer only, see §7.3 |

M2's nominal is 39 × 2.3403 = 91.27 µs. Note that widening the tournament *adds* threadgroups at
PR #196's per-TG fixed cost `f = 3.130 µs`, so the mechanism is bounded above by zero and unbounded
below.

**Nothing in this ledger clears +0.5 % of `cs`.** The best single number available for the headline
mechanism (M3) is **0.138 % of `cs`**.

### 6.1 Why I answered A5 from prior art rather than a fresh timed run

The assignment permitted rebasing `research/maple-fern-decode-dup-injection.patch` (15 KB, base
`0c86fc3b…`) to measure single-TG duplication elasticity directly. I chose not to, and I want that
choice on the record with its justification:

1. The **two largest single-TG families are already measured on this exact host**. `rmsbfloat16` was
   measured by PR #483 at 0.108 µs/added-dispatch with a 95 % UB of 35.02 µs/step for the whole
   mechanism; `prefill_router_tournament` was measured by PR #218 at 0.00 ± 0.12 µs/call. Between
   them they are 80 of the 84 single-TG dispatches (95.2 %). The remaining 4 are singletons.
2. A fresh injection run would produce a *third* estimate of a quantity that already has two
   consistent measurements, both of which fall far below the bar, and both of which were produced by
   the same instrumentation family the patch uses.
3. The patch's base (`0c86fc3b…`) is stale relative to `5f7861c0`, so the work is a rebase plus a
   release build plus a matched timed pair — an expensive path to a foregone conclusion, on a host
   whose transfer ratio to M5 was measured at ≈0.25.
4. Phase A's job was to decide whether the pool exists. Two independent in-repo measurements say it
   does not, by a margin of 3.6× to ∞. A third measurement would not change the verdict; it would
   only change the error bar on a number that is already comfortably below the bar.

If the advisor wants the direct number anyway, the run is cheap to specify: rebase the patch onto
`5f7861c0`, inject N ∈ {0, 84, 168, 252} duplicate single-TG dispatches, fit the slope, and read off
µs/dispatch. My prediction, entered here before the fact, is **0.05–0.20 µs/dispatch**, consistent
with #483.

---

## 7. N-3 — three findings that contradict a stated belief

### 7.1 The 95.9 µs headline is refuted by a measurement already in this repository

H4's figure and PR #483's measurement are about the same 41 dispatches of the same kernel family on
the same host, and they differ by **21.7×**. #483 is a direct measurement with a published CI;
the headline is Rule 65's addition constant applied in the removal direction, which Rule 68
explicitly refutes. The headline should be withdrawn.

### 7.2 `fern-r105c` §8.4 called the 1-TG router tournament "a real serialisation"; PR #218 had already priced it at zero

`research/…fern-r105c…` §8.4 (my own prior round) flagged the single-threadgroup router tournament
as a real serialisation point. PR #218's marginal-cost ledger had already measured that exact kernel
at **0.00 ± 0.12 µs/call**, absorbing **15.33 copy-sets ≈ 2.85 ms** of injected work before showing
any cost. The r105-C observation was a shape observation promoted to a cost claim without checking
the ledger. Withdrawn here.

### 7.3 Occupancy is anti-correlated with cost — dispatch count is not a cost proxy, bytes are

This is the most transferable finding.

| | sub-C40 (203 dispatches) | at-or-above-C40 (205 dispatches) |
|---|---|---|
| share of dispatches | 49.75 % | 50.25 % |
| share of bytes | **8.25 %** | **91.75 %** |
| share of label seconds (82b, shape only) | **21.77 %** | **78.23 %** |

The two halves of the step are near-identical in *dispatch count* and differ by **11.1×** in bytes
and **3.6×** in label seconds. Per dispatch, an at-or-above-C40 dispatch is **~3.6× costlier in
label seconds and ~255× costlier in bytes** than a sub-C40 one.

This inverts the intuition behind the assignment: the under-occupied dispatches look bad on an
occupancy metric precisely *because they have almost nothing to do*. Counting dispatches, counting
threadgroups, and counting waves all rank the step in almost the opposite order from counting bytes,
and bytes are what the roofline in §2.4 says the step is 66 % made of.

Practical consequence: **future decode censuses should lead with bytes, not with dispatch or
threadgroup counts.** The four spine families already identified in the PR #218 ledger
(`T0b_qkv` 1276 µs/step at E = 0.74, `T2c_routed_qmv` 1184 µs at E = 0.75, `T2d_down_residual`
555 µs at E = 0.62, `T1c_lmhead` 474 µs at E = 1.11 — together 3489 µs/step ≈ 42.6 %) are where the
elasticity actually is, and all four are `SATURATING` in this census.

---

## 8. What would change my mind

- A ranked M5 receipt showing that removing single-TG dispatches gains time (i.e. the reverse of
  #527's sign) would reopen M3.
- A demonstration that PR #483's null is an artifact of the *producer* side — #483 added a redundant
  norm, and an open sibling arm C (`CURRENT_RESEARCH_STATE.md:2550-2557`) still requires the
  producer-side direction to be argued explicitly. I did not close that arm here.
- A residency measurement at 64 threads/TG distinguishing the simd model (R = 48) from the cap model
  (R = 24) would firm up §1.2, which is currently the census's weakest link. It would not change the
  verdict, because §4's conservation argument does not use the residency model at all.
- A revised M5 bandwidth constant. §2.4 publishes against the measured 610.0 GB/s per Rule 80; the
  geometry-corrected conjecture of 686.2 GB/s is unmeasured, and adopting it would move the DRAM
  floor from 66.16 % to 58.8 % of the step and grow the unattributed residual — which would make the
  residual *larger* without making it a lever.

## 9. W&B

Run: `fern-r105d-decode-dispatch-occupancy-census` in `wandb-applied-ai-team/mlxfast-maple`,
job type `census`, tags `r105-D`, `maple-fern`, `phase-A`, `census`, `no-timing`, `N-1`.

It logs the full summary-statistic set (step structure, occupancy rollup, byte census, roofline,
mechanism bounds, the 15.2× self-falsification, and the five headline verdicts), plus the per-family
geometry table, the occupancy rollup table, and all three artifacts as a W&B Artifact. The run URL
and ID are reported with the typed result.

**This run records a static census, not a timed experiment.** No GPU timing was executed for this
result; every number is either trace-derived arithmetic or a previously published in-repo
elasticity. It is logged so the census is reproducible and citable, not to claim a measurement.

## 10. Suggested follow-ups (not implemented)

1. **Lead with bytes.** Rebuild the standard decode census view around §7.3 so future rounds do not
   re-derive an occupancy hypothesis that the byte distribution already rules out.
2. **Close #483's producer-side sibling arm C** explicitly, so the input-norm family can be marked
   terminal in both directions rather than one.
3. **Measure the 64-thread/TG residency point** to discriminate the two models in §1.2. Cheap, and
   it would retire a standing ambiguity in every occupancy analysis the programme runs.
4. **Retire `waves × b`.** If PR #196's staircase is quoted again, it should carry a note that `b`
   is a full-attention-TG constant, per §5.
5. **The 205 at-or-above-C40 dispatches are the real surface** (91.75 % of bytes). That is byte
   reduction, not occupancy work, and it overlaps existing dials owned by frieren (#597), nezuko
   (#584) and tanjiro (#592) — so it needs advisor coordination before anyone opens it.
