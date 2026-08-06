# PR #110 — The price of a byte: a per-plane marginal-rate ledger

- **Assignment** `maple-2026-08-06l-m5-byte-price-ledger`, revision `r1`
- **Student** `maple-nezuko` · **PR** [#110](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/110)
- **Base** `codex/mlxfast-maple-20260804-advisor` @ `2f3ed2e2c8c36bdc6ac6f52b6f2c7e6d5c26921c`
- **Arm A surface** research-only. **Zero submitted bytes.** No GPU time consumed.
- **Machine-readable companion** [`research/maple-nezuko-byte-price.csv`](maple-nezuko-byte-price.csv)
  (153 data rows: 97 Table-R, 56 Table-K)

Every cell below is labelled **MEASURED** (read off an official receipt or a
profiler trace), **DERIVED** (exact arithmetic on MEASURED inputs, no free
parameter), or **PREDICTED** (a model output that no receipt has confirmed).
Every byte figure is labelled **READ** or **REMOVED** per §0.9.40
(`CURRENT_RESEARCH_STATE.md:164-168`). Every rate carries its kernel or block
name and a source line per §0.9.39 (`:75-100`). Every empirical number carries
`n` and a dispersion per §R20.6 (`:100-127`). Where the corpus does not contain
a number, this document says **UNKNOWN** and does not interpolate.

---

## S0 · Verdict

**Six findings, in order of how much they should change what we do next.**

1. **The pricing law does not need an elasticity constant, and does not need a
   per-kernel profiler.** The official receipt chain publishes candidate decode
   ms/token and prefill ms directly, so the marginal rate of a removed plane is
   *exactly* `MB_removed / Δ(decode ms)`. Reconstructing each arm's published
   normalised score from its two receipts closes **four times out of four with
   an RMS residual of 0.00019 %** — about **1431× tighter** than the 0.278 %
   one-vs-one MDE. This is an identity, not a fit.

2. **Hypothesis H cannot be evaluated at the granularity in which it is
   stated.** H prices bytes at `rate_kernel`. **No M5 per-kernel timing table
   exists anywhere in `research/`.** Every M-labelled per-kernel table in the
   corpus is M4 Pro / `applegpu_g16s` / GPU generation 16. The finest M5
   granularity in existence is **four block-level rates** obtained by
   differencing deliberately-slowed official receipts
   (`tanjiro-pr34-result.md:595-606`). H is therefore repriced here at
   **block** granularity, which is the granularity the evidence supports.

3. **The §0.9.36 "1.0–1.2×" band is an aggregate identity, not per-arm
   evidence.** Repriced per arm, σ = `R_avg / R_marg` spans **5.2×**
   (0.269 … 1.406) — never the 1.2× band. But aggregated over the whole
   `#35 → #72 → #80` chain, 96.138 MB removed over 175.63 µs gives
   **547.4 GB/s**, versus the routed block average of 546.2 GB/s: **σ_agg =
   0.998**. The band is what you get when you divide a sum by a sum. Each of
   its three "independent confirmations" is the same arithmetic.

4. **H is not falsifiable at the corpus's current precision — with one
   exception.** Three of the four rows are `n = 1` paired receipts; propagating
   the imported 0.278 % MDE, their σ intervals *all overlap* 1.0–1.2, and R3
   and R4 even overlap each other. Point estimates refuse H; intervals cannot.
   The exception is **R1 (#20)**, the only arm with real replication (4 control
   + 2 candidate receipts): σ = **0.269, 1-sem interval [0.201, 0.337]**, which
   excludes the band at >6σ. The binding constraint on H is **n = 1**, not the
   theory.

5. **The 1.71× gap between #72's `0.0272 %/MB` and §R20.2's `0.01595 %/MB`
   factorises exactly into three terms** — PLANE 1.3829 × ESTIMATOR 1.2821 ×
   CONVENTION 0.9621 = **1.7059**, against a target of 1.7053. None of the three
   is measurement noise. The largest is real physics; the second is an
   estimator bug; the third is bookkeeping.

6. **Two of the four "queued" arms do not exist and a third is already
   shipped.** Repricing kills the router plane outright on arithmetic alone
   (clearing the §R18.9 +1.0 % bar would require removing **112 % of the
   plane**) and shows the dense BF16 plane is worth **exactly 0.000 %** because
   it has zero *admissibly* removable bytes. Only **#105** survives, at
   **+0.405 %** — 1.46× the MDE, i.e. real but not comfortably resolvable on a
   single pair.

**Proposed replacement for §0.9.36 is in [S7](#s7--the-law).** The headline
number a planner should carry is not a price but an interval: an unpriced plane
costs somewhere in **[463, 969] GB/s — a factor of 2.09** — equivalently a
realised price of **[0.0158, 0.0330] %/MB**. Anyone quoting a point price for an
unmeasured plane is quoting a number the corpus does not have.

---

## S1 · Scope, method, and what "price" means

### S1.1 The quantity being estimated

For a change that removes `B` bytes per decode step from plane `P` and touches
nothing else, define the **marginal rate**

```
R_marg[P]  ==  B / Δt_decode
```

where `Δt_decode` is the fall in candidate decode ms/token. `R_marg` has units
of GB/s and answers: *how fast did the bytes we deleted actually move?*

Contrast the **average rate** of the enclosing kernel or block,

```
R_avg[K]  ==  bytes_read[K] / time[K]
```

which answers: *how fast does the average byte in that block move?* These are
different questions and the corpus has been silently substituting the second
for the first. Their ratio is the dimensionless

```
σ[P]  ==  R_avg[K] / R_marg[P]
```

`σ > 1` means the removed bytes moved **slower** than the block average — a
strided, awkward, or latency-bound sub-plane, so deleting it over-delivers
relative to a roofline estimate. `σ < 1` means they moved **faster**, so a
roofline estimate over-promises. σ is bookkeeping; `R_marg` is the physics.

### S1.2 Why this needs no elasticity constant

The corpus prices bytes through a constant `14.862 %/ms` (§0.9.36,
`CURRENT_RESEARCH_STATE.md:714-731`). That constant is not a constant. The
scored quantity is

```
score  ∝  decode_su^0.75 · prefill_su^0.25
```

and because the harness's normalised `ns` cancels baseline drift by
construction, the candidate-side score change is *exactly*

```
Δns%  =  100 · [ (D_before/D_after)^0.75 · (S_before/S_after)^0.25  −  1 ]
```

with `D` the candidate decode ms/token and `S` the candidate 512-token prefill
ms. To first order this is `75·ΔD/D + 25·ΔS/S`, so the "elasticity" is
**`75 / D_after` and nothing else**. Its value at each rung of the frontier:

| after | `D_after` ms | elasticity %/ms |
|---|---:|---:|
| #20 | 5.0869753 | 14.7435 |
| #35 r5 | 5.0119323 | 14.9643 |
| #72 | 4.9681367 | 15.0962 |
| #80 (current frontier) | 4.9083721 | **15.2800** |
| corpus constant `14.862` ⟺ | 5.04644 | 14.8620 |

The corpus constant is pinned to `c3ce66ec`'s decode
(`tanjiro-pr34-r2-result.md:353`), which is now **two promotions stale**. It
**understates the current elasticity by 2.81 %**. That is small, but it is a
systematic bias in the *conservative* direction and it drifts further with every
win — a self-defeating property for a constant used to decide what to try next.

### S1.3 Validation: the identity closes four times out of four

Applying the exact identity to the four promoted arms, using only receipt
numbers:

| row | arm | `75·ΔD/D` | `25·ΔS/S` | **reconstructed Δns%** | **published Δns%** | residual |
|---|---|---:|---:|---:|---:|---:|
| R1 | #20 lm-head cascade | 0.3911 | +0.0196 | **0.4105** | 0.4102 | +0.0003 |
| R2 | #35 r5 attn scale | 1.0785 | −0.0252 | **1.0511** | 1.0513 | −0.0002 |
| R3 | #72+#81 routed scale | 0.6611 | +0.0864 | **0.7473** | 0.7473 | −0.0001 |
| R4 | #80 attn pairwise | 0.9132 | −0.0268 | **0.8848** | 0.8847 | +0.0000 |

**RMS residual = 0.00019 score points.** All inputs MEASURED; all outputs
DERIVED by exact arithmetic. Published Δns% are ratios of the receipts' own `ns`
values (`CURRENT_RESEARCH_STATE.md:634-650`, `:4955-4960`, `:5539-5545`).

This matters for three reasons. It proves the decomposition is exact rather than
approximate, so every `R_marg` below inherits only *receipt* noise and no model
error. It supplies the prefill term that the corpus's decode-only bookkeeping
has been dropping — worth up to **0.0864 points** on a single arm, a third of
the MDE. And it means **any two receipts on a chain can be repriced
retroactively at zero cost**, which is how Table R was built without spending a
minute of GPU time.

### S1.4 What was NOT done

No candidate was built, timed, or submitted for Arm A. No M5 access was
available; the host for this session is an **Apple M4 Pro** (14 CPU / 20 GPU
cores, 48 GiB, low-memory startup profile, macOS 26.5.2), which per
`maple-tanjiro-pr91-prefill-budget-census.md:861-863` reports Apple GPU
generation 16 and does not select the `_nax` kernels the ranked M5 uses.
Everything in Table R is a re-analysis of receipts the campaign has already
paid for.

---

## S2 · What does not exist (and why H is unevaluable as stated)

The assignment states H as

```
Δscore% = bytes_removed_per_step / rate_kernel × 14.862 %/ms × σ_kernel
```

`rate_kernel` presupposes a per-kernel M5 rate table. **There is none.**

**MEASURED, by exhaustive search of `research/`:** no file contains
`gen 17`, `applegpu_g17`, or `nax_available=true`. Every per-kernel timing
table declares M4 Pro / `applegpu_g16s` / generation 16. The single most
detailed kernel census in the campaign,
`maple-tanjiro-pr73-decode-kernel-census.md`, is M4 Pro throughout, and its own
profiler lives in `Vendor/mlx-swift/.../metal/device.{cpp,h}` — **not in
`editablePaths`** — behind a local-only commit (`a8a269d`) that was reverted. It
cannot be shipped, so it cannot ever run on the ranked M5.

**The finest M5 granularity that exists is block-level**, obtained by
differencing deliberately-slowed official receipts in #34
(`tanjiro-pr34-result.md:38-40`, table at `:595-606`):

| M5 block | phase | bytes | time | **rate** | source |
|---|---|---:|---:|---:|---|
| attention q/k/v/o QMV | decode | 802.16 MB | 1.23070 ± 0.028 ms | **651.8 GB/s** | `tanjiro-pr34-result.md:599` |
| routed-expert QMV | decode | 552.08 MB | 1.01067 ± 0.034 ms | **546.2 GB/s** | `:602` |
| routed gather-GEMM | prefill | — | — | 408.4 GB/s · 23.23 TFLOP/s | `:595-606` |
| attention dense GEMM | prefill | — | — | 128.4 GB/s · 65.74 TFLOP/s | `:595-606` |

The routed decode rate is flagged **provisional** at
`maple-tanjiro-pr73-decode-kernel-census.md:829`. Everything else that looks
like an M5 rate in the corpus is one of:

- **415 GB/s** — an M5 *whole-step aggregate*, not a kernel rate
  (`tanjiro-pr27-result.md:152`);
- **610 GB/s** — **DEFINITIONAL**, being 1794 MB ÷ 2.941 ms, i.e. the ledger
  divided by the step time (`CURRENT_RESEARCH_STATE.md:1611`);
- **260.6 / 260.2 / 250.4 / 252.3 GB/s** — all **M4**;
- **281.3 GB/s** — M4 and **self-flagged non-physical** by its own author
  (`maple-fern-pr71-routed-qmv-bandwidth.md:134`, `:138`).

**Consequence.** H is repriced at block granularity throughout this document.
Where a plane's enclosing block has no M5 rate — the lm-head cascade, the
router plane, the dense BF16 plane — σ is either mixed-machine (flagged) or
**UNKNOWN**, and this document says so rather than substituting an M4 number.

### S2.1 One clause of the brief is refuted

The brief states that official receipts give "only paired score deltas." They do
not. They give candidate decode ms/token and candidate prefill ms to 7–9
significant figures, and the campaign has twice extracted physical rates from
them by differencing: the four block rates above, and 610 GB/s DRAM + 56 TFLOP/s
at `tanjiro-pr27-result.md:89-102`. **The receipt stream is a low-rate physical
instrument, and it is the only M5 instrument the campaign has.** S1.3 shows it
is also an exact one. Under-using it is the corpus's central methodological
error; every `R_marg` in Table R was free.

### S2.2 Citation erratum

The statement "every M-labelled timing in the corpus is M4 Pro generation 16"
is at **`maple-tanjiro-pr91-prefill-budget-census.md:861-863`**, not at
`CURRENT_RESEARCH_STATE.md:861-863` as cited in the assignment brief.

---

## S3 · Table R — exact receipt reconstruction

Four rows. All inputs MEASURED from official receipts; `Δt`, `R_marg`, and σ
DERIVED by exact arithmetic.

| row | arm | plane removed | `t_before` ms | `t_after` ms | `Δt` µs | **MB REMOVED** | **`R_marg` GB/s** | `R_avg` GB/s | **σ** |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| **R1** | #20 M1 cascade | lm-head stage-1 base | 5.1135025 | 5.0869753 | 26.527 | 25.690112 | **968.4** | 260.6 ⚠M4 | **0.269** |
| **R2** | #35 r5 frieren | attention NVFP4 scale | 5.0840029 | 5.0119323 | 72.071 | 37.770000 | **524.1** | 651.8 | **1.244** |
| **R3** | #72 + #81 | routed MoE g32 scale | 5.0119323 | 4.9681367 | 43.796 | 30.670000 | **700.3** | 546.2 | **0.780** |
| **R4** | #80 frieren | attention scale pairwise | 4.9681367 | 4.9083721 | 59.765 | 27.698336 | **463.5** | 651.8 | **1.406** |

**Receipts.** R1 `t_before` = mean of the four #20 control receipts `5d522d6a`,
`5e0e9cd1`, `c210d200`, `1feeabc8` (`CURRENT_RESEARCH_STATE.md:5539`, `:5540`,
`:5541`, `:5545`), reconstructed as `D = S/128 + T`; that identity is validated
against `tanjiro-pr34-r2-result.md:353`, which publishes `c210d200`'s `D_cand =
5.10820` against `S = 97.9730`, `T = 4.34279` — reproduced here to 6 decimal
places. R1 `t_after` = mean of the two Y receipts `0c21dc18`, `2dce5912`
(`:5542`, `:5543`), cross-checked against the 7-figure
`frieren-pr35-r5-result.md:288`. R2–R4 endpoints are the single receipts
`0c21dc18` → `0d123661` → `58e28b8d` → `97a5090c` (**PROMOTED**), decode fields
at `CURRENT_RESEARCH_STATE.md:634-650`.

**Bytes.** R1 25,690,112 B (`nezuko-m1-cascade-result.md:20`, `:28`). R2 37.77 MB
(`CURRENT_RESEARCH_STATE.md:1541-1548`). R3 = 312 × 98,304 B = 30.67 MB
(`maple-nezuko-pr72-group32-scale-census.md:363-368`). R4 27,698,336 B
(`maple-frieren-pr80-attn-scale-pairwise.md:31-32`, `:409-410`). All **REMOVED**.

### S3.1 Uncertainty — and the one row that has any

| row | `n` receipts | `Δt` dispersion | `R_marg` interval | **σ interval** |
|---|---:|---|---|---|
| **R1** | **6** (4 ctrl + 2 cand) | ±6.683 µs, 1 sem | **[773.6, 1294.6]** | **[0.201, 0.337]** |
| R2 | 1 pair | imported 0.278 % MDE | [418.6, 700.5] | [0.923, 1.564] |
| R3 | 1 pair | imported 0.278 % MDE | [493.1, 1207.9] | [0.452, 1.108] |
| R4 | 1 pair | imported 0.278 % MDE | [355.4, 666.1] | [0.978, 1.835] |

R1's interval is propagated from the **actual replicate spread** — control sd
0.0110495 ms over n=4, candidate range→sd over n=2 — giving `Δt = 26.527 ±
6.683 µs` and a reconstructed `Δns = 0.3911 ± 0.0985 %`, comfortably consistent
with the published `0.4102 ± 0.129 %`. R2–R4 have **no replication at all**;
their intervals import the campaign's 1v1 MDE and are therefore *assumptions*,
not measurements. This asymmetry drives the whole verdict in S6.

### S3.2 A seam worth declaring

R1's `t_after` is the n=2 mean `5.0869753`; R2's `t_before` is the single
receipt `0c21dc18` = `5.0840029`. The chain therefore has a **−2.972 µs seam**
where two rows meet at nominally the same tree. Chaining R2 from the n=2 mean
instead gives `Δt = 75.043 µs`, `R_marg = 503.3 GB/s`, `σ = 1.295` — a **4.0 %**
shift in `R_marg`. Both variants are in the CSV. Neither changes any conclusion,
but a ledger that hides its seams is not a ledger.

### S3.3 The rung structure inside R4

#80 shipped four rungs, individually costed at
`maple-frieren-pr80-attn-scale-pairwise.md:412-416`:

| rung | bytes REMOVED | Δ decode % | vs 0.278 % MDE |
|---|---:|---:|---|
| A→B | 5,698,368 | +0.1302 | 0.47× — **below** |
| B→C | 12,364,768 | +0.2825 | 1.02× — **at** |
| C→D | 9,635,200 | +0.2202 | 0.79× — **below** |
| **A→D** | **27,698,336** | **+0.9132** | 3.28× |

**Not one rung is individually resolvable.** #80 is only a measurement because
its rungs were shipped together. This is the strongest practical argument in the
whole ledger for **bundling** byte removals rather than attributing them, and it
directly contradicts the instinct to split a win for causal attribution.

---

## S4 · Table K — the per-kernel census (M4 Pro, for structure only)

Source: `maple-tanjiro-pr73-decode-kernel-census.md`. Apple M4 Pro,
`applegpu_g16s`, generation 16, n = 199 steady-state decode steps,
`DARKBLOOM_GPU_PROFILE=1`, driver `research/decode_probe.py --steps 200
--profile --profile-top 44`. δ-corrected table at `:341-367`; δ = 1.681 µs per
command buffer.

**This table cannot price an M5 byte.** It is included because it is the only
thing in the campaign that shows the *shape* of the decode step, and because
its achieved-rate column is what makes S6's plane ordering interpretable.

### S4.1 δ-corrected time (µs/step), M4 Pro

| kernel | µs | `n` disp. | | kernel | µs | `n` disp. |
|---|---:|---:|---|---|---:|---:|
| `routed_nvfp4_swiglu_qmv_packed_top8keys` | 1503.9 | 39 | | `full_fused_attn_grow` | 237.9 | 10 |
| `decode_nvfp4_qkv_h64` | 1358.4 | 30 | | `shared_nvfp4_swiglu_qmv_rows1` | 230.5 | 39 |
| `oproj_act_h64` | 1141.8 | 30 | | `gate_sp_h64` | 191.7 | 30 |
| `routed_shared_nvfp4_down_residual` | 833.4 | 39 | | `decode_router_top8_ordinal_table_norm` | 139.6 | 39 |
| `sliding_fused_attn_ring_v1` | 588.3 | 30 | | `dense_down_residual` | 133.0 | 1 |
| `lmhead_int5_base_coarse_delta` | 418.9 | 1 | | `lmhead_exact_fused_int5_sparse_refine` | 74.9 | 1 |
| `decode_nvfp4_qkv_h48` | 363.9 | 10 | | `rmsbfloat16` | 74.6 | 41 |
| `oproj_act_h48` | 302.9 | 10 | | `gate_sp_h48` | 67.3 | 10 |
| `dense_gate_up_swiglu` | 268.0 | 1 | | remaining 6 kernels | 17.4 | — |
| `residual_rms_router` | 254.3 | 39 | | **total** | **8200.7** | |

Step decomposition (`:330-336`): **8.2006 ms kernel + 0.0756 ms command-buffer
+ 0.2540 ms host gap = 8.5302 ms wall.** The raw (un-δ-corrected) table at
`:184-210` sums to 8883.1 µs.

**No ±half-range is published for any row.** The only stability evidence is an
A→C drift control: total −0.288 %, worst single kernel `gate_sp_h64` at
|1.24 %|. Per §R20.6 this is a **drift bound, not a dispersion**, and the CSV
records it as such.

### S4.2 Achieved rate vs the M4 streaming ceiling (260.2 GB/s, `:431`)

| kernel / block | GB/s | % of ceiling | reading |
|---|---:|---:|---|
| `dense_down_residual` | 252.3 | **97.0 %** | saturated |
| `dense_gate_up_swiglu` | 250.4 | **96.2 %** | saturated |
| `shared_nvfp4_swiglu_qmv_rows1` | 199.6 | 76.7 % | good |
| `residual_rms_router` | 160.8 | 61.8 % | **slack** |
| `gate_sp` (h64+h48) | 30.4 | 11.7 % | latency-bound |
| router top-8 / `rmsbfloat16` | ≈0 | ≈0 | compute/latency |
| *attn q/k/v/o block* (DERIVED) | 253.3 | **97.3 %** | saturated |
| *routed + shared block* (DERIVED) | 246.0 | **94.6 %** | saturated |
| *lm-head base plane* (DERIVED) | 260.6 | **100.2 %** | at ceiling |

The last three are my own DERIVED aggregates: 802.16 MB / 3167.0 µs,
575.08 MB / 2337.3 µs, 109.18 MB / 418.9 µs.

**The single most useful number here is 100.2 %.** On M4 the lm-head base plane
runs *at* the machine's streaming ceiling. If it is equally saturated on M5 —
untested, and flagged as such — then the **M5 streaming ceiling is at least
~917–968 GB/s**, since R1 measured that plane at 968.4 GB/s on M5. The corpus
has never measured an M5 ceiling; the CSV records it as `KC2 = UNKNOWN` with
this as a lower bound. It also makes R1's `R_marg` physically credible rather
than an outlier to be explained away.

### S4.3 Byte allocation (M4 census, `:402-422`, all READ)

`attn qkvo` 802.16 · `routed MLP` 552.08 · `lm-head cascade` 112.4 ·
`dense_gate_up_swiglu` 67.11 · `sliding_fused_attn_ring_v1` 62.91 ·
`shared_nvfp4_swiglu_qmv_rows1` 46.00 · `residual_rms_router` 40.89 ·
`dense_down_residual` 33.55 · shared-expert down 23.00 ·
`full_fused_attn_grow_v1` 20.97 · `gate_sp` 7.86 · `rmsbfloat16` ~0.17 ·
router top-8 ~0.02. **Allocated 414.88 of the 439.76 MB non-attn/non-routed
remainder; 24.9 MB (5.7 %) unallocated.** The M5 master ledger
(`CURRENT_RESEARCH_STATE.md:5602-5612`) agrees on the two large blocks.

The **5.7 % unallocated** is itself a finding: it is larger than every queued
arm in S8 except #105, so a census pass that closed it would be worth more than
most of the arms currently under consideration.

### S4.4 Rate cross-check on the M4→M5 step

M5 / M4 attention-block ratio = 3167.0 µs / 1230.7 µs = **2.573×**. Whatever
else is uncertain, the M5 moves attention bytes about 2.6× faster than this
host. Any M4-derived timing intuition should be discounted accordingly, and no
M4 rate is used to price an M5 byte anywhere in this document except R1's σ,
which is flagged ⚠.

---

## S5 · Reconciling 0.0272 vs 0.01595 %/MB

The corpus carries two byte prices that differ by **1.71×**. The assignment asks
which is right. **Neither. They price different things with different
estimators under different conventions**, and the gap factorises exactly.

Express each price as the rate it implies, using the corpus elasticity
`14.862 %/ms`:

| price | source | implied rate |
|---|---|---:|
| `0.0272 %/MB` | #72 roofline | **546.4 GB/s** |
| `0.01595 %/MB` | §R20.2, `CURRENT_RESEARCH_STATE.md:327-343` | **931.8 GB/s** |

The first number is `14.862 / 546.2` to four figures. **#72's price is not a
measurement; it is a restatement of the routed block's average rate.**

### S5.1 The three factors

| # | factor | value | what it is |
|---|---|---:|---|
| 1 | **PLANE** `R_marg,lm / R_marg,routed` = 968.4 / 700.3 | **1.3829** | real physics: lm-head bytes stream ~38 % faster than routed-scale bytes |
| 2 | **ESTIMATOR** `R_marg,routed / R_avg,routed` = 700.3 / 546.2 | **1.2821** | estimator bug: the roofline used the *block average*, but the removed sub-plane moved faster |
| 3 | **CONVENTION** `R_corp,lm / R_marg,lm` = 931.8 / 968.4 | **0.9621** | bookkeeping: §R20.2 uses the stale corpus elasticity and omits #20's prefill term |

**Product = 1.7059. Target = 0.0272 / 0.01595 = 1.7053.** Closes to 0.04 %.

### S5.2 Reading

Factor 1 is the finding. **The price of a byte is a property of the plane, not
of the model.** A single campaign-wide `%/MB` is a category error, and the two
numbers were never in competition.

Factor 2 is the actionable defect. Pricing a *sub-plane* removal at its
*enclosing block's average* rate is only valid if the sub-plane is
representative, and here it demonstrably was not — the routed scale bytes moved
**28 % faster** than the average routed byte. §R20.7
(`CURRENT_RESEARCH_STATE.md:128-139`) already caught the symptom and correctly
ruled "KEEP the empirical calibration, DROP the '0.59× of roofline' gloss." This
ledger supplies the mechanism behind that verdict.

Factor 3 is small and mechanical, and shrinks to zero the moment `75/D_after` is
used instead of a pinned constant.

### S5.3 #72's `+0.834 %` is DERIVED and circular, and should be retired

Verbatim at `maple-nezuko-pr72-group32-scale-census.md:382-406`: "30.67 MB /
546.2 GB/s = 56.1 us", then two conversions — `+0.983 %` direct and `+0.834 %`
using the campaign constant — with the document itself stating that "**+0.834 %
is quoted as a roofline lower bound**." The analyser hardcodes it
(`research/maple-nezuko-pr72/analyze.py:14`).

`+0.834 %` was therefore **never measured**. R3 measures the same arm at
**+0.7473 %** (`+0.6611 %` decode + `+0.0864 %` prefill). Yet
`CURRENT_RESEARCH_STATE.md:723-725` cites #72 as the "third confirmation at
1.18×" of §0.9.36 — a confirmation of a band by a number computed *from* the
band's own denominator. **This is circular and is retired here.**

### S5.4 The brief's "0.37× ratio" is a units mismatch

The brief flags a 0.37× discrepancy. It is an artefact of comparing a percentage
of `T` at an M4 rate against a percentage of score at an M5 rate. Like-for-like
the ratio is **0.60×**; in absolute time it is **0.280×**. The percentage view
silently embeds the machine factor 8.8831 / 5.04644 = **1.760**. There is no
physical discrepancy to explain.

### S5.5 `ae9ac90b` is retired as a pricing source

Per the assignment, the rival receipt `ae9ac90b` (`ivanfioravanti`) is **not**
used to price anything here. It is cited once, methodologically, as a clean
example of a denominator artefact: 1.47 / 1.316 = 1.12×, a "confirmation" of the
1.0–1.2 band produced entirely by choice of denominator. It is the same failure
mode as S5.3, on someone else's tree.

---

## S6 · Verdict on H

> **H** — repricing each arm at its own kernel rate collapses every
> observed/predicted ratio into 1.0–1.2×.

### S6.1 Point estimates: refused, by 5.2×

| row | plane | σ |
|---|---|---:|
| R1 | lm-head stage-1 | **0.269** ⚠ M4 `R_avg` |
| R3 | routed MoE scale | **0.780** |
| R2 | attention scale (#35) | **1.244** |
| R4 | attention scale (#80) | **1.406** |

Spread **5.23×**, or **1.80×** excluding the mixed-machine R1. The 1.0–1.2 band
contains **one** of four rows.

### S6.2 Intervals: cannot refuse — and that is the real finding

| row | σ | interval | overlaps 1.0–1.2? |
|---|---:|---|---|
| R1 | 0.269 | **[0.201, 0.337]** (n=6, real) | **NO** |
| R2 | 1.244 | [0.923, 1.564] (n=1, imported MDE) | yes |
| R3 | 0.780 | [0.452, 1.108] (n=1, imported MDE) | yes |
| R4 | 1.406 | [0.978, 1.835] (n=1, imported MDE) | yes |

R3 and R4 — σ = 0.780 and 1.406, an apparent 1.80× disagreement — **overlap each
other** on [0.978, 1.070]. At `n = 1` the corpus cannot distinguish a plane
running at 463 GB/s from one running at 700 GB/s.

**Honest verdict: H is not falsifiable at the corpus's current precision.** The
point estimates refuse it; the intervals cannot. The binding constraint is
`n = 1`, not the theory. The one exception is R1, which has genuine replication
and excludes the band at more than 6σ — but R1's σ mixes an M4 `R_avg` with an
M5 `R_marg`, so what it strictly refutes is "**price a byte with any rate you
happen to have**," which is a weaker and more useful claim than a statement
about plane physics.

### S6.3 Why the corpus kept seeing 1.0–1.2×

**Aggregate the whole M5-priced chain** `0c21dc18 → 97a5090c`:

```
96.138336 MB REMOVED  /  175.631 µs  =  547.4 GB/s
σ_agg = R_avg,routed / R_marg,agg = 546.2 / 547.4 = 0.998
```

**The band is an aggregate identity.** Sum the bytes, sum the time, divide, and
you recover the routed block average to within 0.2 % — because the routed block
dominates the ledger. Every "independent confirmation" of §0.9.36 was a
different slice of that same sum.

A second contributor: **both attention arms were priced at the routed
546.2 GB/s rather than the attention 651.8 GB/s**. That ratio is
651.8 / 546.2 = **1.1933** — the width of the band, almost exactly. The band's
upper edge is a mislabelled block.

### S6.4 σ orders by plane, not by bytes

| plane | σ | mechanism |
|---|---:|---|
| lm-head stage-1 | 0.269 | dense, sequential, at the M4 ceiling (S4.2) |
| routed MoE scale | 0.780 | gathered but coalesced |
| attention scale | 1.244 / 1.406 | strided; and `pr80:1546-1548` attributes +0.09…+0.14 % of #80 to the *instruction* channel, i.e. bytes were not the only thing removed |

σ has **no monotone relationship with bytes removed** (25.7 / 30.7 / 37.8 /
27.7 MB against 0.269 / 0.780 / 1.244 / 1.406). It is a property of *access
pattern*. That is exactly what a per-plane price should look like, and exactly
what a single campaign-wide `%/MB` cannot express.

### S6.5 The cost of settling this

To resolve σ to ±0.1 requires `0.278/√n ≤ 0.08`, i.e. **n ≥ 13 paired official
receipts per arm**. At one in-flight submission per account that is roughly a
day of wall-clock per arm, for a *bookkeeping* number. **Do not buy it.** Price
with intervals instead — which is what S7 does.

---

## S7 · The law

Replace §0.9.36's `14.862 %/ms × σ` with:

```
─────────────────────────────────────────────────────────────────────────────
  R_marg[P]   =  MB_removed / Δ(decode ms)                    MEASURED, exact
  Δns%        =  100·[ (D_b/D_a)^0.75 · (S_b/S_a)^0.25 − 1 ]  exact identity
              ≈  75·(MB / R_marg) / D_after  +  25·ΔS/S       working form
  σ[P]        =  R_avg[block] / R_marg[P]                     bookkeeping only
─────────────────────────────────────────────────────────────────────────────
```

with `D` = candidate decode ms/token, `S` = candidate prefill ms, both straight
off the receipt. At today's frontier (`D_after = 4.9083721`) the working form is

```
   Δscore%  =  15.2800 × MB_removed / R_marg[GB/s]        (decode term)
```

**Never use 14.862.** Use `75 / D_after` for the tree you are actually standing
on; it is exact and free.

### S7.1 Measured `R_marg` by plane

| plane | `R_marg` GB/s | `n` | dispersion |
|---|---:|---:|---|
| attention NVFP4 scale | **493.8** | 2 | ±30.3 GB/s (±6.1 %), half-range of {524.1, 463.5} |
| routed MoE scale | **700.3** | 1 | none — [493.1, 1207.9] on the imported MDE |
| lm-head cascade | **968.4** | 1 arm / 6 receipts | [773.6, 1294.6], 1 sem |
| everything else | **UNKNOWN** | 0 | — |

The attention plane is the only one measured twice, and its two independent
estimates agree to **±6.1 %**. That is the corpus's best evidence that `R_marg`
is a stable plane property at all, and it is *one* replication.

### S7.2 Residual dispersion — an interval, as required

For a plane with **no** measurement, the honest prior is the full observed
range:

```
   R_marg ∈ [463, 969] GB/s          — a factor of 2.09
   realised price ∈ [0.0158, 0.0330] %/MB
```

**A planner pricing an unmeasured plane must carry a 2.09× uncertainty.** Both
corpus constants sit inside it: §R20.2's `0.01595` at the fast end, #72's
`0.0272` at the slow end. They were never contradictory — they are the two ends
of one interval that nobody had drawn.

The practical rule that follows: **an arm whose *optimistic* price fails to
clear the bar is dead without a build.** That is how S8 closes two of the four
queued arms for zero GPU time.

---

## S8 · Repricing the four queued arms

| arm | MB REMOVED | `R_marg` used | **repriced Δ%** | × MDE | verdict |
|---|---:|---:|---:|---:|---|
| **#105** lm-head base resplit | 25.690112 | 968.4 (R1) | **+0.405** | 1.46× | **GO**, cautiously |
| #72 / #104 shared scale plane | 3.824 | 700.3 (R3) | **+0.083** | 0.30× | **unmeasurable** |
| router coarse screen | 40.894464 | 700.3 (R3) | **+0.892** | 3.21× | **CLOSE** — see S8.3 |
| dense BF16 layer-0 plane | **0.000** | 250.4 (M4) | **+0.000** | 0.00× | **CLOSE** — zero admissible bytes |

**Two of these four are not queued and never were.** The router coarse-screen
arm **does not exist anywhere in `research/`**. #72 is **shipped and merged** at
`9e8c719f` (`CURRENT_RESEARCH_STATE.md:42`, `:1200`, `:1211-1240`), live at
`LagunaRuntimeWeights.swift:1014`, `:1094-1103` and
`LagunaRuntimeModel.swift:9960-9964` — it is not prospective. The brief's queue
should be corrected.

### S8.1 #105 — lm-head base-plane resplit: **+0.405 %**

The only live arm, and **no research document exists for it** — only four
one-line references (`CURRENT_RESEARCH_STATE.md:136`, `:352`, `:363`, `:380`).

Mechanism: resplit the int5 cascade 4+1 → 3+2, taking stage-1 from 1024 to
768 B/row ⇒ **25,690,112 B REMOVED**, leaving an 83.49 MB stage 1. The base
plane is the 4-bit nibble plane 102.76 MB + 6.42 MB e8m0 = **109.18 MB**
(`LagunaLmHeadPrune.swift:58-63`, `:70-71`, `:119-120`, `:60`, `:234-235`,
`:820-821`).

It removes **exactly the same byte count as #20** from **exactly the same
plane** — so R1 prices it directly, with no plane-transfer assumption. This is
the single best-conditioned prediction in the ledger.

| pricing | Δ% | comment |
|---|---:|---|
| **R1 `R_marg` = 968.4 GB/s** | **+0.405** | **use this** |
| §R20.2 realised interval | **[0.25, 0.70]** | **quote this to the advisor** |
| roofline @ 546.2 (routed avg) | +0.719 | wrong plane — 1.8× over |
| roofline @ 260.6 (M4) | +1.506 | wrong machine — 3.7× over |

**Two debits are not in that number.** (i) The 1-bit → 2-bit survivor-tail
replane is **un-costed**: ~458 of 25,088 four-row blocks (≈1.8 %) at 16 kB per
live block (`CURRENT_RESEARCH_STATE.md:5903-5905`). (ii) §R20.1
(`:300-320`) states stage 1 has **zero access-pattern slack**, so there is no
headroom to absorb a worse pattern. At 1.46× the MDE, either debit could put
#105 below resolvability. **Recommend shipping it bundled**, per S3.3.

### S8.2 #104 shared scale plane — arithmetically unmeasurable

Already closed **NO-GO with zero GPU time**
(`maple-nezuko-pr104-shared-scale-plane-halving.md:10-11`, `:116-118`). This
ledger confirms it quantitatively: 3.824 MB net of the 39×256 B headers
(`lagunaScalePatchHeaderBytes = 128`, `LagunaRuntimeWeights.swift:979`) prices
at **+0.0836 %**, or **0.30× the MDE**. Detecting it at 3σ against the observed
0.16 % candidate sd needs **n ≥ 33 paired receipts**. Correctly closed; the
close should be recorded as *unmeasurable*, not *ineffective*.

### S8.3 Router coarse screen — closed on arithmetic

The plane READS **40.89 MB** (256 × 2048 BF16 × 39 layers,
`maple-tanjiro-pr73-decode-kernel-census.md:413`, `:529`) and is the corpus's
best slack candidate at **160.8 GB/s = 61.8 % of the M4 ceiling**
(cb-corrected 254.3 µs; the raw 319.9 µs would give 127.8).

**It still dies.** At `R_marg` = 700.3 GB/s, clearing §R18.9's **+1.0 % bar**
(`CURRENT_RESEARCH_STATE.md:907-921`) needs **45.83 MB — 112 % of the entire
plane**. Removing **100 %** of it is worth only **+0.892 %**. There is no
admissible design; the arm is closed for **zero GPU time**.

Three supporting reasons. (i) Negative precedent: fern #37's lm-head level-0
screen closed because every configuration *added* bytes (`:6196`) — and a
256-row router has **392× fewer rows** to amortise a screen over than a
100,352-row vocabulary. (ii) Re-quantization is rejected on **legality**: the
accepted envelope is attention-only
(`RESEARCH_IDEAS_2026-08-05_09:30.md:409-411`). (iii) ⚠ **Coincidence warning:**
the routed gate/up scale plane is *also* exactly **40,894,464 B**
(`maple-nezuko-pr104-shared-scale-plane-halving.md:222`,
`frieren-pr35-scale-census.md:59`). Two unrelated planes share a byte count to
the byte. Any future citation of "40.89 MB" must name which one.

### S8.4 Dense BF16 layer-0 plane — priced at exactly 0.000 %

READS **100.66 MB** (`gate_up` 67.11 + `down` 33.55,
`maple-tanjiro-pr73-decode-kernel-census.md:770-772`, `:777-779`) and runs at
**250.4 / 252.3 GB/s = 96.2 % / 97.0 %** of the M4 ceiling — **already
saturated**, no slack to recover.

**Admissibly REMOVABLE bytes: 0.** NVFP4-ing it is outside the attention-only
envelope (`:783-789`). The only admissible route is a **lossless
`Sources/MLXFastTransform/` re-layout** (`:791-796`), which removes no bytes and
is already being chased by #85. Under §0.9.40's READ/REMOVED discipline this
plane's price is **exactly 0.000 %**, and the 100.66 MB is a *read* figure that
must never be quoted as an opportunity.

Erratum: layer **0** is the dense layer (`LagunaConfig.swift:62`, `:495`,
`:542`); the wording at `pr73:774` and `:776` is wrong.

### S8.5 The whole remaining inventory, priced

At measured `R_marg`, assuming physically-unreachable 100 % removal:

| plane | MB | `R_marg` | Δ% |
|---|---:|---:|---:|
| lm-head after #105 | 83.490 | 968.4 | 1.317 |
| attention scale residue | 23.556 | 463.5 | 0.777 |
| routed scale residue | 30.670 | 700.3 | 0.669 |
| shared scale | 3.824 | 700.3 | 0.083 |
| **sum of admissible residues** | **141.5** | | **2.847** |
| *router plane (removability UNKNOWN)* | 40.894 | 700.3 | *0.892* |

**Every admissibly-removable byte the campaign has identified is worth
+2.85 % in total, at 100 % removal.** Realistically half of that is reachable.
The byte-removal seam is close to exhausted, and the next order-of-magnitude win
will have to come from somewhere else — the 5.7 % unallocated census remainder
(S4.3), the latency-bound `gate_sp` at 11.7 % of ceiling (S4.2), or the
0.2540 ms host gap (S4.1), which is **3.0 % of the step** and is not a byte
problem at all.

---

## S9 · Errata and retirements

| # | item | status |
|---|---|---|
| 1 | **`ae9ac90b`** as a pricing source | **RETIRED** per assignment; cited only as a denominator-artefact example (S5.5) |
| 2 | **#72's `+0.834 %`** | **RETIRED** — DERIVED, self-declared roofline lower bound, never measured. Measured value **+0.7473 %** (S5.3) |
| 3 | **§0.9.36's "1.0–1.2× band"** | **RETIRED as per-arm evidence** — an aggregate identity, σ_agg = 0.998 (S6.3) |
| 4 | **§0.9.27's "1.89× over-delivery law"** | already **RETRACTED** at `CURRENT_RESEARCH_STATE.md:1508-1523`; consistent with this ledger |
| 5 | `CURRENT_RESEARCH_STATE.md:1698-1699` **"+0.771 %/+0.770 %"** for #80 | **PREDICTED, presented as observed.** Measured Δns = **+0.8847 %** |
| 6 | **#80 has four different numbers in circulation** | 0.771 (predicted), 0.857 (drift-cancelled decode), 0.913 (raw decode-only), **0.8847 (actual Δns)**. Only the last is the score delta |
| 7 | `CURRENT_RESEARCH_STATE.md:666` attributes `285f79fa` to birch | detailed evidence assigns it to **maple #48** |
| 8 | `CURRENT_RESEARCH_STATE.md:325` cites `LagunaLmHeadPrune.swift:72-73` | file has drifted **2 lines**; now `:70-71` |
| 9 | assignment cites `CURRENT_RESEARCH_STATE.md:861-863` for the M4-gen-16 claim | actually **`maple-tanjiro-pr91-prefill-budget-census.md:861-863`** |
| 10 | `maple-tanjiro-pr73-decode-kernel-census.md:774`, `:776` on which layer is dense | wrong; layer **0** is dense (`LagunaConfig.swift:62`, `:495`, `:542`) |
| 11 | **"40.89 MB"** is ambiguous | two distinct planes share the exact byte count 40,894,464 (S8.3) |
| 12 | the elasticity constant **14.862 %/ms** | **stale by two promotions**; understates by 2.81 %. Use `75/D_after` |
| 13 | the brief's **"0.37× ratio"** | a units mismatch, not a physical discrepancy (S5.4) |
| 14 | the brief's claim that receipts give **"only paired score deltas"** | **refuted** (S2.1) |
| 15 | the brief's four-arm **queue** | #72 is shipped; #104 is closed; the router arm never existed. Only #105 is live |

---

## S10 · What to measure next

Ranked by information per unit of GPU time.

1. **Nothing, for pricing.** The ledger is now built entirely from receipts the
   campaign already bought. Every future promotion adds one more Table R row for
   free. **Reprice on every promotion; never spend GPU time on a price.**

2. **Ship #105 bundled, not split** (S3.3, S8.1). At 1.46× the MDE with two
   un-costed debits, a split #105 risks producing three sub-MDE rungs and no
   conclusion — exactly #80's failure mode, which was only rescued by having
   been shipped whole.

3. **Measure the M5 streaming ceiling.** It has never been done. S4.2 gives a
   lower bound of **≥ ~917–968 GB/s** from R1 plus the M4 saturation argument.
   The cheapest route is another #34-style deliberately-slowed receipt pair
   targeting a known dense plane. One pair; it would convert several UNKNOWNs
   in this ledger into numbers and tighten S7.2's 2.09× interval.

4. **Close the 5.7 % unallocated census remainder** (S4.3) — 24.9 MB, larger
   than every queued arm except #105, and it costs only analysis.

5. **Stop treating bytes as the frontier.** S8.5 caps *all* remaining admissible
   byte removal at +2.85 %. Meanwhile the host gap is 0.2540 ms = **3.0 % of the
   step** (S4.1) and `gate_sp` runs at **11.7 % of ceiling** (S4.2). Neither is
   a bandwidth problem, and together they are worth more than the entire
   remaining byte inventory.

6. **Do not buy σ.** Thirteen paired receipts per arm (S6.5) to resolve a
   bookkeeping ratio is the worst trade in the ledger.

---

## Appendix A · Reproduction

Arm A consumed **no GPU time** and touched **no submitted byte**. Every figure
reproduces from the corpus plus four short `awk` scripts, all inputs inline:

| script | produces |
|---|---|
| `/tmp/ctl.awk` | #20 control and Y decode means from published `S`, `T` via `D = S/128 + T` |
| `/tmp/final.awk` | Table R, the three-term factorisation, aggregate σ, repricing, inventory |
| `/tmp/r1err.awk` | R1's uncertainty propagated from real replicate spread |
| `/tmp/ident.awk` | the four-row `ns`-identity closure of S1.3 |

The CSV is the durable artefact; the scripts are scaffolding and are not
committed. `research/maple-nezuko-byte-price.csv` is long-format with columns
`table, row, arm, plane, kernel_or_block, machine, quantity, value, unit, label,
byte_basis, n, dispersion, dispersion_kind, source`.

## Appendix B · Arm B

Recorded separately below once the maintenance deletion has passed its four
gates. Arm A stands independently of Arm B's outcome.
