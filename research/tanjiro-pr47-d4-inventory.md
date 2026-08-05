# PR47 D4 — Ranked removal-target inventory for the 406 decode dispatches/step

Deliverable D4 of PR47 (`maple-2026-08-05c-dispatch-law-close`, r1).
Author: maple-tanjiro. Base `1849b376d73f69f9a6b9018619ac665ae4bceb33`.

This is an **inventory and ranking**, not a measurement. Every row is a
*candidate* priced against the current M5 per-dispatch bracket. No row here has
been measured on M5.

---

## 0. Honest headline — read this before ranking anything

**The only two direct tests of "remove N real decode dispatches" that this
programme has ever run both returned ≤ 0.**

| test | mechanism | dispatches removed | naive prediction at 2.088 µs | measured |
| --- | --- | ---: | ---: | ---: |
| PR9 M2 (nezuko) | fuse `gate_sp` into `decode_nvfp4_qkv` | 40 | −84 µs/step | **+228 µs/step (+2.7% slower)** |
| PR32 r1 (nezuko) | fuse `shared_swiglu` into `routed_swiglu` | 39 | −81 µs/step | **+8.3 ± 7.6 µs/step** |

Both are M4 measurements, and the **M4 transfer law** (PR44) makes M4
boundary/overhead timing inadmissible for M5. So neither result *refutes* the
M5 pool. But they do fix the epistemic status of this whole document:

1. Both tests are consistent with the *low* end of the bracket (0.36 µs, which
   predicts −14 µs for 39 dispatches — inside PR32 r1's ±7.6 µs bar only
   marginally, and comfortably swamped by any fused-body regression).
2. PR9 M2's fused body was independently **+0.95 µs/call slower**, so its
   +228 µs is confounded and is *not* evidence that boundary removal is
   worthless — it is evidence that fusion is only worth attempting when the
   fused body is provably not slower.
3. Therefore **every %-of-score figure below is conditional on the M5-side
   injection law**, i.e. on the `[0.36, 2.09] µs/dispatch` bracket that PR47 D2
   and D5 exist to narrow. Until that bracket closes, the correct reading of
   the "high" column is *upper bound*, not expectation.

Ancillary bound from the same source (`nezuko-pr32-r2-report.md:210-212`):
"inter-kernel overlap and command-buffer overhead together account for at most
**7%** of decode." That 7% is the ceiling on this entire category on M4.

---

## 1. Sources and their caveats

| source | what it gives | caveat |
| --- | --- | --- |
| `research/nezuko-pr9-dispatch-fusion.md:120-144` | per-dispatch `true us`, `us/step`, MB, GB/s, %ceil, "recoverable" | Apple M4 Pro, 48 GiB, 260.2 GB/s read ceiling. `us/call` inflation caveat at `:101-106`. Byte numerators are **unique** bytes — see §1.1. |
| `research/nezuko-pr32-r2-report.md:232-255` | per-family `serialised us/step`, `% of step`, `true us/call`, `dup/ser` | `true us/call` = serialised per-call − 1.33 µs CB floor. `skip` deltas are **lower** bounds; `dup` measures an *additional cache-warm* call (`:179-182`). |
| `research/nezuko-decode-roofline.md:221-240` | earlier roofline table | **Carries a STALE / DO-NOT-RANK banner** (advisor, 2026-08-04, after tanjiro #21). Do not rank from it. |
| `research/tanjiro-pr21-result.md` | current closed decode budget | authoritative for the budget, not for per-dispatch overhead |

### 1.1 The unique-vs-issued bytes artefact (affects two of PR9's biggest "recoverable" rows)

`nezuko-decode-roofline.md:221-240` records that `sliding_fused_attn_ring_v1`
and `full_fused_attn_grow_v1` **issue 4× their unique bytes**: 32 threadgroups
span 64 query heads but only 8 KV heads
(`Sources/MLXFastModel/LagunaRuntimeModel.swift:1400-1402`). On *issued* bytes
they run at **381 and 446 GB/s** = 1.45× and 1.70× the DRAM ceiling — i.e.
cache-served, with **no DRAM slack at all**.

PR9's table inherits the unique-byte numerators, so its
`sliding 36% / 428 µs recoverable` and `full 43% / ~130 µs recoverable`
columns are **artefacts**. PR32 `:331-332` re-prices sliding attention at
"~250-330 µs/step, not the ~428 µs my bandwidth arithmetic implied."

Additionally, PR32 `:322-325` retracts the causal reading outright:

> The "36% of bandwidth" figure is **real but not causal**. The DRAM floor is
> ~8.1 us/call against ~19-22 us measured; the system-level cache absorbs the
> 4x K/V re-read. The actual binder is the ~18 KiB threadgroup memory -> about
> one resident threadgroup per core -> a two-wave latency/occupancy limit.

**Consequence for D4:** the attention rows are an *occupancy/geometry* target
(class (b)), not a bandwidth or fusion target. This is the single largest
correction this inventory makes to the prior census.

### 1.2 Instrument totals do not agree with each other

| quantity | value | source |
| --- | ---: | --- |
| PR9 `gpu_busy_union` | 8.345 ms | PR9 |
| PR32 round-2 serialised | 8.2724 ms | PR32 `:232-255` |
| PR32 `SPLIT=1` `gpu_busy_sum` | 8.8503 ms | PR32 `:196-200` |
| PR32 `SPLIT=1` wall | 10.154 ms | PR32 `:196-200` |

The 0.578 ms gap between `SPLIT=1` sum and round-2 serialised, divided by 406,
is the **1.42 µs/dispatch** mid-bracket figure. It comes from **two different
runs and has no published error bar** — do not treat it as a measurement.

---

## 2. Structural account of the 406 dispatches

Derived by reading the call sites in
`Sources/MLXFastModel/LagunaRuntimeModel.swift` (11,230 lines) and matching
them to census counts.

**Per routed layer (L = 1..39), 10 dispatches, in dependency order:**

```
residual_rms_router ──> decode_router_top8_ordinal_table_norm_v1
        │
        ├──> decode_nvfp4_qkv_h{64,48}_r1 ──> {sliding|full}_fused_attn ──> oproj_act_h{64,48}
        └──> gate_sp_h{64,48}  ───────────────────────────────────────────┘
                                                                          │
                                                          rmsbfloat16 (post-attention)
                                                                          │
                                              ┌───────────────────────────┴───────────┐
                                    shared_nvfp4_swiglu_qmv_rows1        routed_nvfp4_swiglu_qmv_packed_top8keys_r1
                                              └───────────────┬───────────────────────┘
                                                    routed_shared_nvfp4_down_residual_r1_v5
```

39 × 10 = **390**. Layer 0 is dense (`dense_gate_up_swiglu` `:7835/:7912`,
`dense_down_residual` `:7932/:7988`, call `:10399`) ≈ **8**. Final norm
**1** (`:10857`, module `:10537-10538`). lmhead **4** kernels
(`LagunaLmHeadPruner`, `:10864-10875`, constructed `:10954-10956`; names in
`Sources/MLXFastModel/LagunaLmHeadPrune.swift:156,254,528`).

390 + 8 + 1 + 4 = **403**. PR9's table names **397**; adding the two dense
layer-0 kernels and counting lmhead as 4 rather than 1 gives 402. **Four
dispatches of 406 are unaccounted in the published census.** I did not resolve
them and I am not going to claim I did; they are worth at most
4 × 2.088 = 8.4 µs/step = 0.12% of score.

Two dependency facts that constrain fusion and are easy to get wrong:

- **`normalized` fans out to two GPU consumers per layer**: QKV at `:5564-5566`
  and per-head `g_proj` at `:5605-5606`. Any fusion that folds the norm into
  one consumer either duplicates the norm or must serialise the other.
- **Post-attention norm likewise fans out to two consumers**: shared and routed
  SwiGLU. Same constraint.

Call-site index (for whoever implements a row):

| family | name decl | dispatch | scored call site |
| --- | --- | --- | --- |
| `decode_nvfp4_qkv_h{64,48}_r1` | `:4646-4649` | `:4677` | **`:5564`** (attn `:5489`) |
| `gate_sp_h{64,48}` | `:4355-4356` | `:4371` | **`:5605`** |
| `sliding_fused_attn_ring_v1` | `:1382` | `:1793` | **`:5775`** |
| `full_fused_attn_grow_v1` | `:1857` | `:2310` | **`:5801`** |
| `oproj_act_h{64,48}` | `:4390-4393` | `:4432` | **`:5989`** |
| `residual_rms_router_bf16_2048_rpg8_keys_v1` | `:997-999` | `:1087` | **`:10262`** (prefill twin `:10359`) |
| `decode_router_top8_ordinal_table_norm_v1` | `:8631-8632` | `:8702` | **`:9401`**, `:9420` |
| `shared_nvfp4_swiglu_qmv_rows1` | `:6597-6598` | `:6689` | **`:8136`**, `:8275` |
| `routed_nvfp4_swiglu_qmv_packed_top8keys_r1` | `:7335-7336` | `:7468` | **`:9955`** |
| `routed_shared_nvfp4_down_residual_r1_v5` | `:7649-7652` | `:7801` | **`:10023`** |
| `rmsbfloat16` | MLX built-in RMSNorm (oracle ref `:1241`) | — | `:5561`, `:5670`, **`:10297`**, `:10857` |

`rmsbfloat16` is **not a Laguna kernel** — it is MLX's built-in. Which subset of
those four sites (plus `qNorm`/`kNorm` `:5473-5474`, invoked `:5861`, `:5864`,
`:6136-6137`) sums to exactly 41 is **not verified**.

---

## 3. Pricing convention

For a candidate removing `N` dispatches:

```
us/step(low)  = N * 0.36      us/step(high) = N * 2.088
%-of-score    = (us/step / 1000 ms) * 14.862 %/ms
```

`14.862 %/ms` is the programme exchange rate (= exactly `0.75/5.046441`).
`0.36` and `2.088 µs/dispatch` are the two ends of the current open M5
bracket; `2.088` is the paired M5 injection-law slope, `0.36` its low anchor.

Reference values, so no row needs re-deriving:

| N | µs/step @0.36 | %-score @0.36 | µs/step @2.088 | %-score @2.088 |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 0.36 | 0.005% | 2.09 | 0.031% |
| 3 | 1.08 | 0.016% | 6.26 | 0.093% |
| 10 | 3.60 | 0.054% | 20.88 | 0.310% |
| 30 | 10.80 | 0.161% | 62.64 | 0.931% |
| 39 | 14.04 | 0.209% | 81.43 | 1.210% |
| 40 | 14.40 | 0.214% | 83.52 | 1.241% |
| 41 | 14.76 | 0.219% | 85.61 | 1.272% |
| 78 | 28.08 | 0.417% | 162.9 | 2.421% |
| 80 | 28.80 | 0.428% | 167.0 | 2.483% |

Advisor promotion bar is **0.61%** on `ns`; the 2σ floor for two n=3 families
is **0.243%**. So at the *low* bracket end **no single row in this document
clears the bar**, and at the *high* end only the 39/40/41-count rows do. That
asymmetry is the whole reason D2/D5 are worth their submission slots.

---

## 4. RANKED INVENTORY

Ranked by expected value = (score at the high end) × (my credence that the
mechanism can be built without a fused-body regression). Class (b) rows are
priced on their *own* measured recoverable time, not on the dispatch bracket,
which is why they outrank everything in class (a).

### Rank 1 — (b) `sliding_fused_attn_ring_v1` + `full_fused_attn_grow_v1`: threadgroup-memory / occupancy geometry

- **Dispatches removed: 0.** This is not a boundary row. It is here at rank 1
  because it is the only row whose value does not depend on the open bracket.
- Value: PR32's re-priced estimate is **~250–330 µs/step** of *addressable*
  time against ~640 + 235 = 875 µs/step currently spent
  (30 sliding + 10 full). At the midpoint 290 µs/step ⇒ **4.31% of score**.
- Mechanism: the binder is **~18 KiB threadgroup memory ⇒ ~one resident
  threadgroup per core ⇒ a two-wave latency/occupancy limit**
  (PR32 `:322-325`). Reduce per-threadgroup scratch, or restructure the
  32-threadgroup-over-8-KV-head mapping (`:1400-1402`) so KV rows are read once
  per threadgroup instead of 4×.
- **Specific obstacle:** the 4× K/V re-read is currently *absorbed by the
  system-level cache*, so any restructuring that reduces issued bytes may buy
  nothing while any restructuring that reduces threadgroup memory changes the
  ring/grow tiling and therefore the numerics. Needs
  `research/run_upstream_equivalence.sh` on every variant.
- Prior art: none. **This row has never been attempted.**

### Rank 2 — (b) `gate_sp_h{64,48}` (40 dispatches, 213 µs/step for 0.033 MB)

- If the row went to **zero**: 0.213 ms ⇒ **3.165% of score**.
- Priced as a *boundary* removal only: N=40 ⇒ 0.214% (low) / 1.241% (high).
- The gap between those two prices is the point: `gate_sp` moves 0.033 MB, runs
  at **2% of the bandwidth ceiling**, and costs 5.32 µs `true us` per call. It
  is almost entirely launch + latency, so its value is far above its dispatch
  count. `dup/ser = 0.659` (PR32) — well below 1, i.e. the first call is paying
  first-touch cost.
- **Direction that has NOT been tried:** fuse `gate_sp` into its **producer**
  `residual_rms_router`, not into a consumer. PR9 M2 fused it into the
  *consumer* `decode_nvfp4_qkv` and failed at +228 µs/step. Fusing into the
  producer duplicates nothing and is exactly the documented successor
  condition from the defused PR9 attempt: **"amortise the norm producer
  once."** These are different experiments and the M2 negative does not cover
  this one.
- **Specific obstacle:** `gate_sp` consumes `normalized`, which fans out to two
  GPU consumers (`:5564-5566` QKV and `:5605-5606` `g_proj`). Folding it into
  the producer means the producer must emit both `normalized` *and* the gate
  activations, and the per-head `g_proj` weight must be resident in the
  producer's threadgroup. h64/h48 variants must both be handled.
- PR9's own verdict on this row is "**not recoverable by fusion**" — that
  verdict is about the consumer direction and I am flagging it as
  **not dispositive** for the producer direction.

### Rank 3 — (a) `decode_router_top8_ordinal_table_norm_v1` → `residual_rms_router` (39 dispatches)

- Boundary price: N=39 ⇒ **0.209% (low) / 1.210% (high)**.
- Row cost: 96 µs/step, 0.004 MB, **0% of ceiling**, 2.47 µs `true us`.
  Essentially pure launch + latency, so if the fusion also removes the
  round-trip the recovery could approach the full 96 µs ⇒ **1.43% of score**,
  above the boundary-only high price.
- **Permitting data dependency:** top-8 reads *only* the 256 router logits that
  `residual_rms_router` just wrote, in the same layer. There is no other
  producer and no other consumer between them. This is the cleanest
  single-producer/single-consumer pair in the whole decode graph.
- **Specific obstacle:** the fusion is only legal if all 256 router logits are
  produced **within one threadgroup**, so that a threadgroup barrier can
  replace the device barrier. `residual_rms_router_bf16_2048_rpg8_keys_v1` is
  rpg8 / 2048 threads (`:994`, `:997-999`) — this needs confirming before any
  code is written. If the logits are spread across threadgroups the fusion is
  impossible, not merely slow.
- Secondary obstacle: the top-8 selection is an argsort-like reduction; doing
  it inside the norm kernel adds registers/scratch and may push
  `residual_rms_router` into the same occupancy wall as rank 1.

### Rank 4 — (c→a) `oproj_act_h64` first-touch (`dup/ser = 0.601`)

- **Dispatches removed: 0.** Listed because it is the largest `dup/ser`
  anomaly among the big rows: 1183 µs/step, 38.11 µs `true us/call`, and a
  *duplicate* call costs only 0.601× the first. PR32 `:257`, `:264-268`
  interpret `dup/ser < 1` as the first call paying **first-touch weight
  streaming**.
- Value if first-touch could be pre-warmed outside the timed window:
  up to `(1 − 0.601) × 1183 = 472 µs/step` ⇒ **7.02% of score**. That is the
  largest single number in this document.
- **Specific obstacle, and it is severe:** the census is M4 and the M5 keeps
  the whole 21.6 GB tower RAM-resident with no expert cache or streaming, so
  "first-touch" on M5 is a *cache* effect, not an I/O effect, and pre-warming
  a 9.45 MB working set that will be evicted by the other 8.3 ms of decode
  work is likely impossible. Also `dup` measures an *additional cache-warm*
  call (`:179-182`), so `0.601` may be measuring the second call's cache hit
  rather than the first call's miss cost. **Do not rank this as actionable
  without an M5-side replication.** I include it because it is the only row
  large enough to matter at the low bracket end.

### Rank 5 — (a) `rmsbfloat16` post-attention + final (41 dispatches) — **CLAIMED (fern)**

- **Owner: fern.** `Sources/MLXFastModel/LagunaRuntimeModel.swift:5561`.
  Not available for reallocation. Listed for completeness and pricing only.
- Boundary price: N=41 ⇒ **0.219% (low) / 1.272% (high)**. Row cost 36 µs/step,
  0.87 µs `true us`, 2.17 µs/call serialised.
- Clean form: `oproj_act` → residual add → RMSNorm in **one** kernel — single
  producer, single consumer, no duplication.
- **Specific obstacle:** needs the whole 2048-dim row resident in one
  threadgroup, and must be written twice (h64 and h48 variants).
- **Prior negative on the adjacent site, and the successor condition:** the
  fused tail-norm + QKV + gate attempt at `:5554-5557` was re-measured
  **+2.7% slower** and defused. Its recorded successor condition is
  "amortise the norm producer once" — i.e. the *producer*-side framing, same as
  rank 2. Note also that the post-attention norm fans out to **two** consumers
  (shared and routed SwiGLU), so folding it into a consumer duplicates it.

### Rank 6 — (a) lmhead 4 kernels → fewer (3 dispatches)

- Boundary price: N=3 ⇒ **0.016% (low) / 0.093% (high)**. Below the 2σ floor at
  both ends.
- Row runs at **262 GB/s = 101% of ceiling** on 134.9 MB — genuinely
  bandwidth-saturated. There is no idle time to recover.
- **Obstacle:** none in particular; it is simply not worth the risk budget.
  Ranked last of the actionable rows for that reason.
- Note the census/source mismatch: PR9 lists the pipeline as
  `lmhead_int5_inline_coarse_v5`, but the shipping name in
  `Sources/MLXFastModel/LagunaLmHeadPrune.swift:156` is
  `..._ratio_bound_delta_bf16_v6` — **v6, not v5**. The census row may be stale.

---

## 5. DEAD — already measured ≤ 0, do not re-spend

| candidate | N | measured | source | may it be retried? |
| --- | ---: | ---: | --- | --- |
| **F1** fuse `gate_sp` → `decode_nvfp4_qkv` (consumer direction) | 40 | **+228 µs/step, +2.7% slower** | `nezuko-pr9-dispatch-fusion.md:11-19,53-84,99-115` | **No.** Report concludes "reject the whole fusion family". Fused body independently +0.95 µs/call slower. `SPLIT=1` showed the *opposite* sign (−506 µs), which is itself a warning that `SPLIT` is not a proxy for fusion. |
| **F5** fuse `shared_swiglu` → `routed_swiglu` | 39 | **+8.3 ± 7.6 µs** (null) | PR32 r1 | No. Naive prediction was −81 µs at 2.088; even −14 µs at 0.36 is outside the measured bar on the wrong side. |
| **F3/F4** fused tail norm + QKV + gate | — | **+2.7% slower**, defused | `LagunaRuntimeModel.swift:5554-5557` | Only via the producer-side successor condition (ranks 2 and 5). |
| **G1** merge h64 and h48 variants into one dispatch | 40 | not attempted | — | **Structurally impossible.** h64 and h48 are on *different layers*, hence sequential. There is nothing to merge. |

---

## 6. (c) STRUCTURALLY REQUIRED — approximately 160+ dispatches, and why

These cannot be removed by fusion or geometry at all, because each one's input
is the previous one's output across a genuine serial data dependency:

| chain | count | why it is required |
| --- | ---: | --- |
| layer *L* `down_residual` → layer *L+1* `residual_rms_router` | 39 | The residual stream is the model. Layer *L+1* cannot start before layer *L* finishes. This is the backbone of the 40-layer serial chain and admits no reordering. |
| `qkv` → `fused_attn` | 40 | Attention consumes Q/K/V. Fusing would require the whole KV window in threadgroup memory; the sliding window alone is 512 positions × 8 KV heads. |
| `fused_attn` → `oproj_act` | 40 | O-projection consumes the attention output over all 64 heads; attention is tiled 32 threadgroups over heads, so the reduction is inherently cross-threadgroup. |
| `{shared,routed}_swiglu` → `down_residual` | 39 | Down-projection consumes the SwiGLU activations of all 8 routed experts plus the shared expert. Cross-expert reduction, cross-threadgroup by construction. |
| `router_top8` → `routed_swiglu` | 39 | Expert selection must be *known* before the gather-GEMM can address expert weights. Data-dependent addressing cannot be fused with its own producer without speculating over all 256 experts. |

Sum ≈ 197 hard edges over ≈ 160 distinct dispatches (rows share endpoints).
Even at the high bracket end this floor costs 160 × 2.088 = **334 µs/step**
that no boundary work can reach.

---

## 7. What I would spend the next slot on

1. **Rank 1 (attention occupancy).** Only row whose value is independent of the
   open `[0.36, 2.09] µs` bracket, largest never-attempted number, and PR32 has
   already localised the binder to threadgroup memory. Everything else in this
   document is a bet on D2/D5 closing the bracket at the high end.
2. **Rank 3 (router fusion)**, gated on one cheap read: confirm whether all 256
   router logits land in one threadgroup. That is a code-reading task, not a
   GPU task — if the answer is no, the row dies for free.
3. **Rank 2 (gate_sp producer-side)** only after the bracket closes above
   ~1.4 µs/dispatch, because below that its boundary component cannot clear the
   advisor bar and its value rests entirely on the 213 µs launch-latency
   component, which no instrument here has isolated.

**Do not** start rank 2 or 3 as fusion experiments before D2 and D5 report. At
the low bracket end both are below the 0.243% two-family noise floor and would
burn a submission slot to measure nothing.
