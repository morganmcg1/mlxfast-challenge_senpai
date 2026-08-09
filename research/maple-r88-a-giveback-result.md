# R88-A result — the 42 % kernel-local give-back is an artefact of the SPLIT=1 instrument

PR #473, assignment `maple-r88-a-kernel-giveback`, revision `r88-a-rev1`,
branch `maple-frieren/r88-kernel-giveback`.
Pre-registration: [`research/maple-r88a-prereg.md`](maple-r88a-prereg.md)
(committed as `d397cc8`, before any natural-regime number was read).

Host: Apple **M4 Pro, 48 GiB**, low-memory startup profile, Apple GPU
generation 16 — the `_nax` decode kernels the ranked M5 selects are **not**
exercised. This is a **methodology / attribution** experiment. It makes **no
claim about ranked M5 seconds/token or score**.

W&B (group `maple-r88a-two-regime-giveback`):

| regime | run | url |
| --- | --- | --- |
| `s1` (SPLIT=1, 406 CBs/step) | `yi4h1mep` | https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/yi4h1mep |
| `nat` (shipped, 45 CBs/step) | `cud65xgb` | https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/cud65xgb |

---

## 1. Headline

The primary endpoint `c = NAT_total / S1_touched` — end-to-end time saved per
unit of kernel-local work removed by PR #457 — is

| estimator pairing | `c` | 95 % CI |
| --- | --- | --- |
| NAT ratio-adjusted busy / S1 ratio-adjusted touched | **1.247** | [0.90, 1.59] |
| NAT **wall** / S1 ratio-adjusted touched | **1.064** | [0.11, 2.02] |
| NAT absolute busy / S1 absolute touched | **0.879** | [0.44, 1.31] |

Every point estimate is at or above **1.0**. The pre-registered H1/H4/H5
prediction was `c ≈ 0.58`; it is rejected on the adjusted pair at
t = 4.51 on 7 df, p ≈ 0.003 — equivalently, the 95 % CI [0.90, 1.59] excludes
0.58. (SE_c = 0.148 from SE_NAT = 10.651/√8 = 3.766 and SE_S1touched = 0.763,
both propagated with t₇ = 2.3646; the same rejection read directly on the NAT
total against its H1/H4/H5-predicted −15.24 µs/step gives t = −4.65.) The
pre-registered H6 prediction was `c ≈ 1.0`: **supported**.

My own pre-registered point prediction was `c = 0.85` with an 80 % interval
[0.55, 1.10]. The measured adjusted value **1.247** sits above that interval —
I under-predicted, and I am recording that miss rather than re-centring on it.

**There is no give-back in the shipped dispatch regime.** In `nat` the
attention-free command-buffer signatures account for 855.4 of 7998 µs/step
(10.7 % of steady busy) and their summed delta is **+0.66 µs/step (+0.08 %)** —
flat. The +8.06 µs/step that `laguna_gate_sp_h64_v1` loses under SPLIT=1 does
not reappear.

**Consequence: standing rule 38's programme-wide 42 % give-back discount should
be withdrawn.**

---

## 2. What was run

One session, one pair of frozen sha256-pinned worker binaries, replayed in two
dispatch regimes.

- Driver: [`research/maple_r88a_two_regime_ab.sh`](maple_r88a_two_regime_ab.sh)
  (job `6510397b-9454-4ea6-a08d-a9ddd19416c1`, exit 0, 1592 s).
- `base` = source at `417f42c4167344afd2156b6f5d8ab76e2bf419f3` (first parent of
  the #457 merge, i.e. immediately pre-epilogue);
  `cand` = frontier `3217f111142346e004f41fae611a8bede172a659`.
  Binaries `/tmp/maple-r88a-snap/{base,cand}/mlxfast-runtime-worker`,
  sha256 `84850ac0…` and `692e741c…`, both 49,096,520 B, re-verified before
  every slot.
- 4 reps × 2 regimes × 4 slots = 32 runs of 200 decode steps.
  Slot order inside each regime block is **ABBA** (`base cand cand base`), and
  the regime block order is flipped on alternate reps (`order_regimes`, driver
  line 157), so regime is counterbalanced against session time. Observed
  interleaving from file mtimes: `s1` rep1 22:41:51 → `nat` rep1 22:44:43 → …
  → `nat` rep4 23:01:53 → `s1` rep4 23:04:52.
- Contrasts are offset-0 duplexes (1,2)(3,4)…(15,16) with alternating sign,
  **n = 8** per regime. Same-arm nulls use offset 1: n = 3 base/base, n = 4
  cand/cand.
- Only the regime environment variable differs between the two halves. Binary
  pair, host, thermal gate, prompt and token stream are held fixed.

**Correctness.** All 32 `.tokens` files are byte-identical
(md5 `9e0ec9a77526c895be77dbbe668ba6ff`, cksum `4007321606`) and all 32 logs
report `0 divergences (all match)` on the teacher-forced greedy stream. The
#457 change under test is bit-exact on both regimes on this host.

---

## 3. Regime constants

| | wall | busy_sum | busy_union | gap | CBs/step | dispatches/step | gap % of wall |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `s1` | 9872.0 | 8603.4 | 8602.4 | 1269.8 | **406.0** | 406.0 | 12.86 % |
| `nat` | 8230.3 | 7993.1 | 7993.1 | 237.0 | **45.0** | 406.0 | 2.88 % |

(µs/step, base arm, steps 1–199.) Both pre-registered regime checks pass:
`cbs/step ≈ 45` in `nat`, `dispatches/step = 406` in both.

**The instrument costs 1642 µs/step, 24× the effect it is used to measure.**
SPLIT=1 adds ≈+592 µs/step of *charged busy* and ≈+962 µs/step of *idle*, i.e.
≈1.46 µs per extra command buffer, against a #457 effect of ≈26 µs/step. It
also inflates per-duplex wall SD from **30.0 to 105.0 µs/step** (3.5×).

Independent corroboration of the per-CB overhead: under SPLIT=1
`gate_sp_h64_v1` costs 243.1 µs/step over 30 dispatches = **8.10 µs/dispatch**,
versus **5.004 µs** measured in isolation by PR #101 — ≈3.1 µs/CB of
instrument overhead, matching the 2.97 µs of measured idle per CB. The entire
give-back is **+0.269 µs/dispatch, ≈9 % of that overhead**, while the touched
attention kernels lost 0.689 µs/dispatch (ratio 0.39).

---

## 4. `s1` replicates #457

Per-kernel census, control
`routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2` (base 1505.6 µs/step);
labels cover 8585/8603 µs/step (99.8 %).

| kernel | base µs/step | ratio-adjusted Δ [95 % CI] | absolute Δ | #457 |
| --- | --- | --- | --- | --- |
| `sliding_fused_attn_ring_v1` | 649.6 | **−20.66 [−22.33, −18.99]** | −22.19 | touched |
| `full_fused_attn_grow_v1` | 255.6 | **−5.61 [−6.29, −4.93]** | −6.22 | touched |
| **Σ touched** | | **−26.27** | **−28.41** | −26.53 ✔ |
| `gate_sp_h64_v1` | 243.1 | **+8.06 [+6.68, +9.45]** | +7.45 | +8.14 ✔ |
| `gate_sp_h48_v1` | 79.4 | **+0.19 [−0.19, +0.58]** | −0.00 | +2.96 ✘ |
| `decode_nvfp4_qkv_h64…` | | — | −3.48 | |
| `oproj_act_h64…` | | — | −4.01 | |
| routed MoE (control family) | | — | −3.65 | |
| `routed_shared…down_residual…` | | — | −1.42 | |
| `shared_nvfp4_swiglu…` | | — | −1.03 | |
| `decode_nvfp4_qkv_h48…` | | — | −1.00 | |
| **total** | 8603.4 | **−16.70 [−24.7, −8.7]**, SD 9.62 | **−37.54**, SD 41.79 | −15.43 ✔ |

Both pre-registered replication checks pass (`S1_touched` within ±4 of −26.5,
`S1_total` within ±7 of −15.4).

**One #457 number does not replicate.** `gate_sp_h48_v1` moves
+0.19 [−0.19, +0.58] here, not +2.96. #457 reported the larger value for an h48
family label. With h48 flat, 97.7 % of the S1 give-back sits on the single
`gate_sp_h64_v1` label. That asymmetry is itself diagnostic — see §6.3.

---

## 5. `nat`: no give-back

Step-level deltas (cand − base, n = 8 duplexes):

| metric | `s1` Δ [95 % CI] (SD) | `nat` Δ [95 % CI] (SD) |
| --- | --- | --- |
| wall | −72.54 [−159.30, +14.99] (105.0) | **−27.95 [−52.88, −2.94] (30.0)** |
| busy_sum | −37.52 [−72.48, −2.41] (42.1) | −24.98 [−37.35, −12.59] (14.9) |
| busy_union | −36.77 [−71.40, −1.99] (41.7) | −24.98 [−37.35, −12.59] (14.9) |
| overlap | −0.86 (base 1.0) | **+0.00 (base 0.0, SD 0.0)** |
| gap | −32.77 [−98.51, +36.66] | −2.63 [−17.11, +12.79] |

`nat` per-CB-signature census (14 signatures, control
`[4] rmsbfloat16|lmhead_int5_base_coarse_delta_bf16_v1|lmhead_coarse_argmax_stage1_v5|lmhead_exact_winner_bf16_midpoint_threshold_v1`,
base 433.4 µs/step, its own absolute Δ +0.43 [+0.07, +0.78]):

- `NAT_total` ratio-adjusted **−32.75 [−41.6, −23.9]**, SD 10.65, ±8.91 at n=8
  (score −0.5005 %); absolute **−24.98**, SD 14.74.
- **Attention-free signatures: 6 of 14, 855.4 of 7998 µs/step (10.7 %), summed
  absolute Δ +0.66 µs/step (+0.08 %).** This is the direct test. If the
  give-back were physical, the untouched-kernel pool should still lose time when
  attention gets cheaper; it does not.

Control sensitivity (all valid attention-free controls give the same answer):

| control | `NAT_total` adj | SD |
| --- | --- | --- |
| lmhead `[4]` signature (used above) | −32.8 | 10.65 |
| `lmhead_exact_fused_int5_sparse_refine_v1` | −35.0 | 20.45 |
| `gather_frontbfloat16_int32_int_2` | −39.0 | 63.5 |
| *(a control substring that also matches an attention-containing signature)* | *−3.4* | *invalid — excluded* |

**Separability caveat, stated up front.** At `nat` grain the census resolves CB
signatures, not kernels. `sliding_fused_attn_ring_v1`, `gate_sp_h64_v1` and
`oproj_act_h64_v1` each appear in exactly 30 dispatches/step with **identical
signature columns** — they are perfectly collinear and **cannot be separated at
`nat` grain**. `full_fused_attn_grow_v1` (10 disp., rows 3/5/7) and
`gate_sp_h48_v1` (10 disp., rows 3/4/12) *are* separable. Dispatch counts sum
to 406/step as required. So §5 does not claim "`gate_sp_h64` is flat in `nat`"
directly; it claims the *total* and the *attention-free pool* are inconsistent
with a give-back of that size, and §6 closes the gap.

---

## 6. Why the give-back is an instrument artefact — four independent lines

### 6.1 H3 / H3′ (dispatch-overlap absorption) — **refuted**

Pre-registered, before the data: under SPLIT=1 there is one dispatch per CB, so
no two dispatches can overlap and H3 as originally stated cannot produce the
#457 give-back. The surviving form H3′ (real CB-grain absorption in the shipped
regime) predicted `busy_sum > busy_union` in `nat`. Measured:
`sum/union = 1.0001` in `s1` and **exactly 1.0000 in `nat`, in both arms, with
overlap SD = 0.0**. There is no measurable concurrent-dispatch overlap on this
host at all, so there is nothing for a give-back to be absorbed into. **This
also falsifies my own pre-registered `nat` prediction**, which expected real
intra-CB overlap.

### 6.2 H5 (occupancy / shared pipeline state) — **refuted at the pipeline-state level**

The `GPUPSO` lines for all four cells (2 arms × 2 regimes) are byte-identical:

```
custom_kernel_laguna_gate_sp_h64_v1_…            maxThreads=1024 execWidth=32 tgMem=0
custom_kernel_laguna_gate_sp_h48_v1_…            maxThreads=1024 execWidth=32 tgMem=0
custom_kernel_laguna_sliding_fused_attn_ring_v1_… maxThreads=1024 execWidth=32 tgMem=18432
custom_kernel_laguna_full_fused_attn_grow_v1_…   maxThreads=1024 execWidth=32 tgMem=18432
```

#457 changed **no** occupancy limit and **no** threadgroup-memory allocation.

### 6.3 Structural anomaly: h48 attention won with **zero** h48 gate give-back

Any physical mechanism in which cheaper attention slows the neighbouring gate
kernel should scale with how much that attention family changed. h64 attention
lost −20.66 with a +8.06 gate cost (39 %). h48 attention lost −5.61 — the same
proportionality predicts **+2.19** on `gate_sp_h48_v1`; measured
**+0.19 [−0.19, +0.58]**, excluding +2.19 by more than five half-widths. The
give-back does not track the intervention. It tracks the *duty-cycle of one
label*.

### 6.4 Model comparison on the `nat` signature table

Two same-parameter-count predictions of the 14 `nat` signature deltas
([`research/maple_r88a_nat_model_compare.py`](maple_r88a_nat_model_compare.py),
JSONs `/tmp/maple-r88a/nat-model-{adj,abs}_us_step.json`), each propagating S1
per-kernel rates through the measured `nat` dispatch counts:

- **Model A** — the give-back is real: apply *all* S1 per-kernel rates,
  including `gate_sp_h64_v1` +8.06.
- **Model B** — the give-back is an S1 artefact: apply only the two edited
  attention kernels' rates.

| S1 rates used | observed total | pred A | pred B | χ² A | χ² B |
| --- | --- | --- | --- | --- | --- |
| ratio-adjusted | −24.95 | −16.76 | −26.28 | 25.7 | **20.8** |
| absolute | −24.95 | −37.55 | −28.41 | 114.9 | **22.3** |

Model B wins under both, decisively under the absolute rates. Free in-situ fit
of the collinear h64 bundle (adjusted others): **−19.88 [−28.23, −11.54]**,
against −13.89 predicted with the give-back and −21.94 predicted without — the
CI excludes the with-give-back value and contains the without value.

### 6.5 Nulls: the estimator is unbiased in both regimes

| null | `s1` | `nat` |
| --- | --- | --- |
| base/base, adj total (n=3) | −1.7 [−24.6, +21.2], SD 9.22 | +3.2 [−18.2, +24.7], SD 8.62 |
| cand/cand, adj total (n=4) | +0.3 [−14.3, +14.9], SD 9.16 | −7.8 [−28.3, +12.9], SD 12.95 |
| base/base, wall (n=3) | +87.6 [−496, +708] | −2.7 [−72.8, +68.1] |
| cand/cand, wall (n=4) | −11.3 [−32.5, +10.0] | −8.9 [−37.5, +19.8] |

Every null CI contains zero. The pre-registered void condition ("same-arm null
in `nat` wider than the base-vs-cand contrast") is **not** triggered for the
adjusted census (±8.9 real vs ±8.6/±12.9 null point estimates well inside
their own CIs); it is closer for `nat` **wall**, where the cand/cand null point
estimate (−8.9) is a third of the real effect (−27.95). I therefore treat the
adjusted `nat` census as primary and the `nat` wall figure as corroboration.

---

## 7. Ranked posterior over the hypotheses

| id | mechanism | verdict | posterior |
| --- | --- | --- | --- |
| **H6** | SPLIT=1 neighbour-coupling / duty-cycle artefact | **supported** — `c ≈ 1`, attention-free pool flat, χ² model B, h48 anomaly | **0.75** |
| H4 | code/data placement | **untested here**, cannot be excluded; no positive evidence (parked arm r = −0.088) | 0.10 |
| H1 | real resource contention | **rejected** — `c ≈ 1`, χ² A ≫ B, h48 anomaly | 0.07 |
| H3′ | CB-grain overlap absorption | **refuted** — overlap is identically zero | 0.03 |
| H5 | occupancy / shared pipeline state | **refuted** — PSO identical | 0.03 |
| H2 | power / thermal / clock rebalancing | **not supported** — regime-dependent inside one gated session, nulls flat | 0.02 |

Advisor priors were H1 0.40 / H3 0.35 / H4 0.10 / H5 0.10 / H2 0.05.

**Proposed sub-mechanism for H6.** Under SPLIT=1 `gate_sp_h64_v1` is its own
command buffer, and the fixed launch/ramp component charged to a *small* kernel
depends on when its buffer arrives relative to the preceding one. Making the
preceding attention CB finish ≈0.7 µs/dispatch earlier shifts that arrival
phase and reprices the boundary by ≈0.27 µs/dispatch. In the shipped regime
`gate_sp_h64_v1` shares a command buffer with `sliding_fused_attn_ring_v1`
(signature rows in §5), so **there is no boundary to reprice** — which is
exactly why the effect is regime-specific.

---

## 8. Methodological finding: which census estimator is the scored one

`wall = busy_abs + gap` holds **exactly** in both regimes. The ratio-adjusted
census estimates a *control-matched* quantity, not the clock quantity, and the
two views disagree about where the give-back lives:

| view | `s1` touched | `s1` total | give-back |
| --- | --- | --- | --- |
| ratio-adjusted | −26.27 | −16.70 | 9.58 µs/step = 36.5 % |
| **absolute** | −28.41 | **−37.54** | **none — the total already exceeds the touched sum** |

The 42 % give-back exists **only inside the ratio-adjusted view of the SPLIT=1
regime**. In the clock-consistent absolute view of the same runs, S1's total
saving is *larger* than the sum over the touched kernels. Rule 38 was derived
from the one estimator/regime combination that produces it.

A second, separate point: #457's "total" column is **Σ per-kernel by
construction** (−26.53 + 8.14 + 2.96 = −15.43 exactly), so it was never an
independent end-to-end measurement, and the "Σ per-kernel vs total"
discriminator originally proposed for H3 is vacuous.

---

## 9. Recommendations

1. **Withdraw standing rule 38's 42 % give-back discount.** Use SPLIT=1
   per-kernel deltas for *attribution only*. Take end-to-end magnitude from a
   `nat`-regime paired ABBA census (wall **and** absolute busy, n ≥ 8
   duplexes). Same session cost, 3.5× lower wall variance, and it measures the
   grain that ships.
2. **Reprice #457** on this host: local end-to-end **−27.95 µs/step wall**
   (−0.34 % of decode wall, ≈−0.43 % score) or −24.98 absolute busy /
   −32.75 adjusted busy, rather than the −15.43 µs/step credited. The M5
   receipt remains the authority; this is M4 Pro local evidence only.
3. **Reprice #462's norm→QKV un-fusion.** Rule 38 discounted its
   −124…−128 µs/step to −52…−55. Removing the discount restores the full
   estimate, a **2.35× larger** predicted saving, which should move it back up
   the queue. #462's own byte-cost break-even threshold was derived from the
   discounted value and should be recomputed by its owner rather than taken
   from this report.
4. **Amend rule 40**: quote **wall** when the adjusted and absolute census
   estimators disagree in sign or magnitude, and never mix an adjusted total
   from one regime with an absolute total from another. Also record which σ an
   arm used (§10).
5. nezuko's rec-4 (semantically-null recompile of
   `laguna_sliding_fused_attn_ring_v1`) drops in priority: with H1/H3′/H5
   refuted it now only tests H4, which carries 0.10 posterior.
6. Mechanism class is **methodology/attribution**. No ranked-score claim, and
   nothing here is directly submittable.

---

## 10. Response to advisor feedback

### `r88-a-fb2` — "a cross-process contrast cannot resolve the give-back at any feasible n"

**Respectfully, the data say otherwise, and I think the σ was applied to the
wrong estimand.** σ = 48.0 µs/step is the cross-process spread of *per-run wall
medians*. The give-back arm is not a per-run comparison; it is a paired ABBA
census in which each contrast is a within-duplex difference. Measured **this
session, cross-process**:

| estimator | per-duplex SD | half-width at n=8 | resolves 9.6–11.1 µs/step? |
| --- | --- | --- | --- |
| `nat` ratio-adjusted busy total | **10.65** | **±8.91** | yes |
| `nat` absolute busy total | 14.74 | ±12.3 | marginal |
| `nat` wall | **29.96** | **±25.0** | as corroboration only |
| `s1` ratio-adjusted busy total | 9.62 | ±8.05 | yes |
| `s1` wall | 104.99 | ±88 | no — do not use wall under SPLIT=1 |
| per-kernel labels | 0.4–4.9 | ±0.3–4.1 | yes, comfortably |

So the arm was feasible, and it ran at n = 8 within one 1592 s job. I agree
completely with the underlying rule that σ must not be imported across arms:
within-process 19.5 µs/step (df = 11) and cross-process 48.0/49.0 apply to
per-run medians and neither applies to this census. I have stated the
estimator-specific σ for every number above.

I also agree the concentration signature is informative — 73 % of #457's loss
on one label, 36× uniform — and §6.3 uses exactly that logic, but in the
direction that *disconfirms* H1: the concentration does not scale with the
intervention (h48 attention won −5.61 with a +0.19 h48 gate response).

### `r88-a-fb2` — cut A3

Accepted, A3 was not run. #462 already measured the dose-response
(1.4064 µs [1.3163, 1.4964] @ 4096 B; 0.7258 [0.5275, 0.9241] @ ≤64 B;
1.3 % bytes / 22.4 % fixed dispatch / 76.3 % ordering).

### `r88-a-fb1` — promote A2 (deterministic full prewarm) above completing A0′

**I ran A0′ first and I would make the same call again.** A2's expected value is
conditional on the give-back existing in the shipped regime, and A0′ shows it
does not; the four lines in §6 remove the mechanism A2 was meant to neutralise.
Prewarm/launch-latency is also the mechanism class with this programme's worst
transfer record:

- `DARKBLOOM_SHUF_NORM_*` — −0.70 % local vs −0.07 % ranked
  (`Sources/MLXFastModel/LagunaRuntimeModel.swift:763–792`);
- PR #137 — −63.7 µs/token on M4 vs **+24.6** µs/token on M5
  (receipt `99b71258`); transfer factor −0.40 ± 0.24.

A2 remains the only directly submittable arm on the R88 board, so I am not
arguing against running it — only against running it *before* the premise was
checked, at a cost of one session.

### `r88-a-fb1` — confirm `gate_sp` is in #462's six-CB pool

Confirmed, with a caveat that limits what #462 can be used for:

- `laguna_gate_sp_h64_v1` is **not separately resolvable in #462**: that census
  aggregates per CB signature, and h64 gate is collinear with sliding attention
  and `oproj_act_h64` (§5).
- **Both #457-touched attention kernels are themselves inside #462's
  "untouched" pool** (rows 1 and 4).
- #462 varied binary-sharing **and** dispatch regime simultaneously, so it
  cannot separate H1/H4 from H6. Its null is valid only as a statement about
  spillover from its *own* inserted CB boundaries.
- #462 pool detail for the record: 6 signatures, 17.55 % / 1398.9 µs/step;
  `w16−w0 = −2.20`, `t16−t0 = −2.70`; null SD 1.34 ⇒ ±8.2 band; i.e.
  −0.24 % (±0.9 %) of a 900.1 µs/step gross intervention.
  (nezuko PR #462, closed; W&B `o3ogyevp`; artifact
  `research/nezuko-r86b-artifacts/untouched-pool.txt`.)

---

## 11. Limitations

- **M4 Pro, not M5.** Apple GPU generation 16; `_nax` decode kernels are
  unreachable, and the ranked host may have non-zero dispatch overlap where
  this host measures exactly zero. The *methodological* conclusion (a 406-CB
  instrument cannot price a 45-CB regime) is architecture-independent; the
  numeric repricing of #457 is not.
- **`nat` grain is coarser than kernel grain.** The h64 bundle is collinear
  (§5). The flat attention-free pool, the χ² comparison and the h48 anomaly are
  what close that gap, not a direct per-kernel `nat` measurement.
- **`gate_sp_h48_v1` +2.96 from #457 did not replicate** here (+0.19). Either
  #457's h48 label aggregated differently or that number was noise; I have not
  resolved which.
- **n = 8 duplexes, one session.** The adjusted-census CIs are tight, but a
  second session on a different day would strengthen the repricing of #457.
- H4 (placement) is neither tested nor excluded.

---

## 12. Reproduction

```bash
# 1. two-regime ABBA session (frozen pinned binaries, 32 runs, ~27 min)
research/maple_r88a_two_regime_ab.sh          # writes /tmp/maple-r88a/{s1,nat}/

# 2. step-level additivity, per regime, real + same-arm nulls
for r in s1 nat; do
  python3 research/maple_r88a_additivity.py --steps 200 --arms base cand \
      --offset 0 --json-out /tmp/maple-r88a/$r-add.json /tmp/maple-r88a/$r/*.log
  for a in base cand; do
    python3 research/maple_r88a_additivity.py --steps 200 --arms $a $a \
        --offset 1 --json-out /tmp/maple-r88a/$r-add-null-$a.json \
        /tmp/maple-r88a/$r/*.log
  done
done

# 3. per-kernel (s1) / per-CB-signature (nat) ratio-adjusted census
python3 research/maple_r85_arm_stats.py --steps 200 --cbs-per-step 406 \
    --control routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2 \
    --arms base cand --offset 0 --scale-to-n 8 \
    --json-out /tmp/maple-r88a/s1-kern.json /tmp/maple-r88a/s1/*.err
python3 research/maple_r85_arm_stats.py --steps 200 --cbs-per-step 45 \
    --control lmhead_int5_base_coarse_delta_bf16_v1 \
    --arms base cand --offset 0 --scale-to-n 8 \
    --json-out /tmp/maple-r88a/nat-kern.json /tmp/maple-r88a/nat/*.err
# same-arm nulls: repeat each with `--arms base base` / `--arms cand cand`
#                 --offset 1 -> {s1,nat}-kern-null-{base,cand}.json

# 4. nat model comparison
for m in adj_us_step abs_us_step; do
  python3 research/maple_r88a_nat_model_compare.py --steps 200 --cbs-per-step 45 \
      --arms base cand --offset 0 --s1-json /tmp/maple-r88a/s1-kern.json \
      --s1-metric $m --json-out /tmp/maple-r88a/nat-model-${m%%_us_step}_us_step.json \
      /tmp/maple-r88a/nat/*.err
done

# 5. publish
python3 research/maple_r88a_wandb.py \
  --s1-kern /tmp/maple-r88a/s1-kern.json \
  --s1-kern-null /tmp/maple-r88a/s1-kern-null-{base,cand}.json \
  --s1-add /tmp/maple-r88a/s1-add.json \
  --s1-add-null /tmp/maple-r88a/s1-add-null-{base,cand}.json \
  --nat-kern /tmp/maple-r88a/nat-kern.json \
  --nat-kern-null /tmp/maple-r88a/nat-kern-null-{base,cand}.json \
  --nat-add /tmp/maple-r88a/nat-add.json \
  --nat-add-null /tmp/maple-r88a/nat-add-null-{base,cand}.json \
  --nat-model-adj /tmp/maple-r88a/nat-model-adj_us_step.json \
  --base-sha 417f42c4167344afd2156b6f5d8ab76e2bf419f3 \
  --cand-sha 3217f111142346e004f41fae611a8bede172a659
```

No file on the submitted `editablePaths` surface was modified; every commit on
this branch is under `research/`. Byte budget unchanged
(`current=2890889/3000000 headroom=109111 growth=0/262144 files=140`).

---

## 13. Suggested follow-ups (not implemented)

1. **Re-measure the top three pending proposals in the `nat` regime** with this
   rig before spending an official submission on any of them. #462's
   norm→QKV un-fusion is the obvious first candidate now that its estimate
   grows 2.35×.
2. **One `nat`-regime session on an M5**, if a ranked-host window is ever
   available, purely to check whether `busy_sum > busy_union` there. Zero
   overlap on M4 Pro is the single result most likely to be
   architecture-specific.
3. **A2 (deterministic full prewarm)** still deserves a run as the only
   directly submittable R88 arm, but it should be scored on `nat` wall with a
   paired ABBA design and carry the −0.40 ± 0.24 M4→M5 transfer prior
   explicitly.
4. **Retire `DARKBLOOM_GPU_PROFILE_SPLIT=1` totals from the rule base.** Keep
   the mode for attribution; stop letting any *total* or *ratio* derived under
   it enter a standing rule.
5. Resolve the `gate_sp_h48_v1` +2.96 vs +0.19 discrepancy against #457's raw
   labels — it is cheap and it is the one unexplained number in the table.
