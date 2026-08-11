# R109 Arm G — result: the `rmsbfloat16` attention pre-norm is not recoverable

Student: maple-nezuko. PR #682, assignment `maple-r109-b-router-hybrid-selector`,
revision `r109-b-rev2`, research base
`1a6761bf46c282fcabd0577b618f0c1206757e6c`. Host: Apple M4 Pro, 20 GPU cores,
48 GiB, `applegpu_g16s`.

**Status: Arm G is refuted.** The 142.3 µs/step / 41-dispatch `rmsbfloat16`
attention pre-norm pool cannot be converted into a decode win by folding the
reduction into either of its two consumers. Two reusable rules and one
correction to a banked programme claim come out of it.

## 0. Verdict in one table

| what was tried | result | µs/step | CI95 |
|---|---|---|---|
| Fold RMS into the NVFP4 QKV matvec (5120 TGs) | decisive negative | kernel 34.25 → 55.50 µs/dispatch (1.62×) | — |
| Fold RMS into `gate_sp`, delete the pre-norm dispatch (mode C) | **slower** | **−51.73** | b4 |
| Fold RMS into `gate_sp`, keep the pre-norm (modes W/N) | faster, but not because of the fusion | +46.33 / +51.96 | see §2 |
| …of which pure threadgroup geometry (mode S) | **83% of it** | **+43.23** | [+37.06, +58.00] |
| …of which the fusion itself (S→N) | **not distinguishable from zero** | +8.73 | [−14.19, +22.77] |

Sign convention throughout: **positive = candidate faster than the shipped
control**. Every arm is bit-exact (`0 divergences` on teacher-forced greedy
tokens in all 25 b5 slots and all 19 b4 slots), so none of this is an accuracy
trade.

**The datum worth more than the arm** (§7, requested in comments 6/8/10) — busy
and wall side by side, and the barrier count next to both:

| arm | dispatches | isolated busy saved | barriers/step | **shipped wall** | conversion |
|---|---|---|---|---|---|
| A shipped | 406 | — | 247 | ref | — |
| S geometry only | 406 | +136.9 µs | 247 | **+43.23 µs** | **0.32** |
| W fused, pre-norm kept | 406 | **−6.0 µs** | 247 | **+46.33 µs** | sign flips |
| N fused, no emit | 406 | +18.1 µs | 247 | +51.96 µs | 2.87 |
| **C fused, pre-norm deleted** | **366** | **+204.9 µs** | **243** | **−51.73 µs** | **−0.25** |

Read the last row against the first: arm C removes the entire 41-dispatch
`rmsbfloat16` pool (142.3 → 3.5 µs of isolated busy, 40 launches gone) and is
**51.7 µs/step slower**. Isolated per-kernel busy did not merely over-predict the
gain, it got the **sign** wrong; and barrier count moved by 4 while wall moved by
98. The predictive quantity is neither — it is the latency of whichever kernel
ends up on the critical path (§7.6, forecast 113.4 µs vs measured 98.1 µs).

## 1. Why the arm was plausible, and the census claim it rested on

Arm G was commissioned against the decode-dispatch census: `rmsbfloat16` is 41
dispatches and 142.3 µs/step of pool, moves only 8 KB, and at 3.47 µs/dispatch
is launch-bound rather than work-bound. `research/maple-fern-r105d-decode-dispatch-census.md:229`
states H4: "the 41 `rmsbfloat16` dispatches are a 95.9 µs/step launch tax."

**That claim is arithmetically true and causally false, and it overstates the
recoverable amount by 21.7×.** Rule 65's 2.3403 µs/dispatch is an *addition*
price. The removal direction had already failed once: Rule 68 / PR #527 removed
78 prefill dispatches and *cost* +0.639 ms. And PR #483
(`research/maple-fern-r91-input-norm-fusion-price.md`, W&B `ubjfsywa`) *added*
80 redundant input-RMSNorm dispatches — the same kernel family — for only
**+8.61 µs/step busy, CI [−17.71, +35.02] = 0.108 µs/dispatch**, i.e. 21.7×
below the 2.34 µs sticker. Mode C is the first measurement in the *removal*
direction on this kernel, and it agrees: removing 41 dispatches did not return
95.9 µs, it lost 51.7 µs.

Doctrine to bank: **"add a dispatch, pay 2.34 µs" holds; "remove a dispatch,
gain 2.34 µs" is refuted.** Census pool sizes are an upper bound on opportunity,
not an estimate of it.

## 2. What was measured

Rungs, all on the local harness (`research/decode_probe.py`, one worker process
per arm so the knob is read once at process start, position 0 discarded as
warm-up, per-slot median over 199 steps, median-of-medians across slots, 20 000
bootstrap draws over slots):

- **Rung 1a** — RMS hosted in the QKV matvec: 34.25 → 55.50 µs/dispatch, a
  1.62× regression, because each of 5120 threadgroups recomputes the same
  2048-element normalize. Recorded in `research/nezuko_armg_stage1c.md`.
- **Rung 1b/1c (b1–b3)** — the fused `gate_sp` at successive geometries:
  −344.75, −700.40, −48.04 µs/step. All slower.
- **b4** (19 slots, 6 replicates): A 8257.79, C 8309.52, W 8213.06 µs/step →
  **A−W = +44.73 [+37.08, +49.85]**, **A−C = −51.73**, **C−W = +96.46 µs =
  2.35 µs/layer**.
- **b5** (25 slots, 6 replicates per arm, full four-arm attribution) — see
  `research/nezuko-r109-armg-b5-attribution.md`. A 8256.19, S 8212.96,
  W 8209.85, N 8204.23 µs/step.

The arms are defined in `Sources/MLXFastModel/LagunaNormFusedGateSoftplus.swift`
behind `DARKBLOOM_NORM_FUSED_GATE_SP`: `0` control, `1` fused kernel is the sole
producer of `normalized` (pre-norm deleted), `2` RMS restated from the residual
with an unread `normalized` store, `3` RMS restated with no `normalized` output,
`4` shipped gate math at the fused kernel's geometry. Only mode 1 deletes a
dispatch; the call site in `LagunaRuntimeModel.swift:5949–6025` keeps
`inputNorm(input)` alive whenever the fused kernel does not publish
`normalized`. **The shipped default is `0`** — see §5.

## 3. Rule 1: a sole producer of `normalized` inherits the QKV critical path

Mode C is the arm the assignment asked for and it is 51.73 µs/step slower than
the control. The reason is structural, not a tuning failure: `gate_sp` launches
`heads / (NS·R)` = 8 threadgroups and is latency-bound (PR #683,
`N-GATESP-TG-COUNT-IRRELEVANT`, already established it is insensitive to
threadgroup *count*). The QKV matvec launches 5120. When `gate_sp` becomes the
sole producer of `normalized`, those 8 threadgroups must retire before 5120 can
start, so an 8-wide latency-bound kernel is placed in series ahead of the widest
kernel in the encoder. The dispatch saved is worth ~0.1–2.3 µs; the
serialisation costs ~1.3 µs/layer.

Generalised: **fusing a reduction into a narrow consumer is only safe if that
consumer is not the sole producer for a wide one.** The width ratio, not the
dispatch count, decides.

## 4. Rule 2: the barrier law is conditional on the consumer being on the critical path

`N-INDS-DEPENDENCY-BARRIER` prices an intra-encoder dependency edge at
~2.55 µs/layer (+102 µs/step). This arm produced both a confirmation and a
bound:

- **Confirmation, different kernel pair.** b4's `C−W = +96.46 µs/step =
  2.35 µs/layer`. C and W run identical gate arithmetic; they differ only in
  whether the QKV matvec waits on `gate_sp`. That independently reproduces the
  2.55 µs/layer price to within 8%.
- **Bound, off-critical-path consumer.** b5's `S−N = +8.73 µs/step
  [−14.19, +22.77]` removes exactly one edge, `rmsbfloat16 → gate_sp`, and does
  not clear zero. Point estimate 0.218 µs/layer, upper bound 0.35 µs/layer.

The discriminator is the downstream kernel. `gate_sp` is 96.4% nested inside a
larger co-resident command-buffer record, so nothing waits on it; the QKV matvec
is on the critical path. **Refinement: the ~2.55 µs/layer edge price applies
only when the edge's downstream kernel is itself on the critical path. For a
nested, off-critical-path consumer it is 7–10× cheaper and indistinguishable
from zero.** This matters for arm selection: "count the dependency edges and
multiply by 2.55" over-prices any edge whose consumer is nested, which is most
of the small kernels in the encoder.

§7.5 then measured the barrier count directly and made the refinement much
sharper than "conditional". Across all five arms the shipped wall spans
**98 µs/step** while the per-step barrier count spans **4** (247, 247, 247, 247,
243), and the only arm that *reduces* the count is the only arm that
*regresses*. So:

> **`N-BARRIER-COUNT-NOT-PRICE`** — the per-step intra-encoder barrier count
> does not price a decode edit and is not a state variable. `N-INDS-DEPENDENCY-BARRIER`
> prices one *specific* substitution on the critical path; it must not be read
> as a per-edge multiplier over the encoder's 247 barriers (that would predict
> 630 µs/step of recoverable cost, which does not exist).

§7.6 supplies the replacement, which *is* predictive: the barrier diff A→C is
exactly conservative (31 edges leave `rmsbfloat16`, 31 arrive on `gate_sp`), so
the deletion **transplants** an edge rather than removing one, and the price is
set by the latency of the new producer:

```
cost = N_layers x ( isolated_latency(new producer) - isolated_latency(old producer) )
     = 30 x (6.30 - 3.45) + 10 x (6.24 - 3.45) = 113.4 us/step
measured W - C = 98.06 us/step        (within 16%)
```

Both latencies come from the SPLIT=1 profile, so this is a **forecast an arm can
be priced with before it is built**, from a census plus two kernel latencies.

## 5. Why nothing ships by default

A−N = +51.96 µs/step is a real, bit-exact, reproducible M4 decode win worth
+0.475% at τ=1. I am not proposing it, and the shipped default is mode `0`:

1. **83% of it is threadgroup geometry.** Mode S is the shipped gate arithmetic,
   byte for byte, at 8 TG × 256 threads instead of 8 TG × 64 threads. It removes
   no dispatch and no dependency edge, and it is worth +43.23 µs
   [+37.06, +58.00]. PR #7 measured +7.32% on M4 → ~0% on M5 for a threadgroup
   geometry change, so τ ≈ 0 is the prior and the honest expected M5 value of
   this share is ~0.
2. **The remaining 17% does not clear zero.** S−N = +8.73 [−14.19, +22.77].
   Even at τ = 1 the point estimate is +0.080%, marginal against the ~0.07%
   landing bar, and the interval covers both signs.
3. My preregistered ship rule was "mode 3 only if S−N's CI excludes zero." It
   does not, so mode 0 it is. The knob and the four instrument modes stay in the
   tree so the measurement is reproducible and so the geometry lever is one env
   var away if someone with an M5 wants to price it.

**Flagged for maple-fern (#686), not submitted by me.** If an M5 datapoint on
threadgroup width is wanted for its own sake, `DARKBLOOM_NORM_FUSED_GATE_SP=4`
is a zero-risk probe: bit-exact, one env var, +43.23 µs/step on M4, and it would
settle whether the "geometry does not transfer" rule from PR #7 also covers
*thread count per threadgroup for a latency-bound kernel* as opposed to tiling
shape. I did not run `senpai/submit-official.sh`.

## 6. Honest weaknesses

- `N−S`'s interval is wide because two of six N slots (p17, p22) ran while a
  helper process of mine was committing into the very directory the harness was
  writing. Both show a *widened* per-step distribution, not a shifted one, which
  is host I/O contention rather than a slower kernel. I did not drop them; the
  17/25-slot interim read of the same block said `−11.92 [−18.48, −8.52]`
  ("significant"), which is precisely why post-hoc slot exclusion is not
  available to me. §3.1 of the b5 doc records this.
- Everything is M4. τ for the geometry share is assumed ~0 from PR #7 rather
  than measured, and the direction of that assumption is conservative (it makes
  my candidate look worse, not better).
- The mode-C mechanism in §3 is inferred from the arm contrasts plus the known
  threadgroup counts. §7 tests it directly.

## 7. SPLIT=1 attribution and the encoder barrier census

Rig: `research/nezuko_armg_split_profile.sh p1 A S N W C`, job
`6bb1ee2b-d0d6-4fcf-8278-e33d8109bf4a`, raw in `research/armg-runs/p1/`.
Instrumented worker built into `.build-prof` (APFS clone of `.build-worker`);
`Vendor/` asserted clean before the build and reverted by an EXIT trap
**before any timing run**. 40 decode steps per arm, 39 steady, all arms
`0 divergences` on teacher-forced greedy tokens. SPLIT=1 on every pass-1 profile
per the advisor's standing instruction; pass 2 is SPLIT=0 because
`commit()` resets `needs_barrier_`, so a SPLIT=1 barrier census reads zero
by construction (see §7.4).

### 7.1 Per-step totals

`n = 1` run per arm — these are attribution instruments, not comparison
instruments (§7.3).

| arm | dispatches | wall µs | busy_sum µs | busy_union µs | sum/union | gap µs | gap % |
|---|---|---|---|---|---|---|---|
| A shipped | 406 | 9823 | 8537 | 8536 | 1.0001 | 1288 | 13.1 |
| S geom-only | 406 | 10008 | 8475 | 8472 | 1.0004 | 1536 | 15.4 |
| W restate+keep | 406 | 9740 | 8528 | 8425 | 1.0122 | 1315 | 13.5 |
| N restate+noemit | 406 | 9710 | 8512 | 8413 | 1.0118 | 1297 | 13.4 |
| **C fused sole-producer** | **366** | 9576 | 8377 | 8377 | 1.0000 | 1200 | 12.5 |

SPLIT=1 does what it is advertised to do: `busy_sum/busy_union` falls from
**1.1359** (SPLIT=0, prior census) to **1.000–1.012**, so per-kernel busy is
de-nested and additive. `gate_sp` was 96.4% nested at SPLIT=0; here it is not.

**Arm C removes exactly 40 dispatches (406 → 366)** — the structural check that
mode 1 really does delete the pre-norm pool rather than merely bypass it.

### 7.2 The two kernels the arm was about

`rmsbfloat16`, per steady step:

| arm | µs/step | dispatches | µs/dispatch |
|---|---|---|---|
| A | 141.6 | 41 | 3.45 |
| S | 142.7 | 41 | 3.48 |
| W | 142.4 | 41 | 3.47 |
| N | 142.3 | 41 | 3.47 |
| **C** | **3.5** | **1** | 3.45 |

Arm A reproduces the r105d census (142.3 µs / 41 / 3.47) to within 0.5%, so this
instrument agrees with the datum the arm was built on. Arm C collapses the pool
to a single surviving dispatch: **−138.1 µs/step of isolated GPU busy removed,
and 40 launches removed.** The arm did exactly what it set out to do.

`gate_sp` family, per steady step:

| arm | h64 (30 disp) | h48 (10 disp) | family total | Δ vs A |
|---|---|---|---|---|
| A `gate_sp_h64/h48_v1` (ns2r4) | 238.2 = 30×7.94 | 80.0 = 10×8.00 | 318.2 | — |
| S `..._geom_...` (ns8r1) | 135.3 = 30×4.51 | 44.9 = 10×4.49 | 180.2 | −138.0 |
| W `..._emit_...` | 208.0 = 30×6.93 | 116.2 = 10×11.62 | 324.2 | +6.0 |
| N `..._noemit_...` | 190.0 = 30×6.33 | 110.1 = 10×11.01 | 300.1 | −18.1 |
| C `..._emit_...` | 189.0 = 30×6.30 | 62.4 = 10×6.24 | 251.4 | −66.8 |

### 7.3 The headline: wall next to busy, and the sign inversion

This is the datum the advisor asked for in comments 6, 8 and 10. Isolated busy
saved is `rmsbfloat16 + gate_sp` versus arm A; shipped wall recovered is the
**uninstrumented harness** median-of-medians from b5 (n=6 slots/arm, C from b4).
Positive = candidate faster.

| arm | isolated busy saved µs/step | shipped wall recovered µs/step | conversion |
|---|---|---|---|
| S | **+136.9** | **+43.23** [+37.06, +58.00] | **0.32** |
| W | **−6.0** | **+46.33** [+40.15, +55.08] | **negative → positive** |
| N | +18.1 | +51.96 [+22.13, +59.94] | 2.87 |
| C | **+204.9** | **−51.73** | **−0.25** |

Three things fall out, and the second and third are worth more than the arm:

1. **The best-case conversion is ~0.31, not 1.0.** S removes 138.0 µs/step of
   isolated `gate_sp` busy and the shipped harness returns 43.23 µs/step of
   wall. A nested kernel's isolated duration is discounted by ~3.2× on the way
   to wall, which is what "96.4% nested" means in µs.

2. **Isolated busy has no predictive sign for these kernels.** S, W and N have
   shipped wall gains that agree inside their CIs (+43.2, +46.3, +52.0 — a
   spread of 8.7 µs) while their isolated `gate_sp` busy spans **144 µs**
   (180.2 → 324.2). W is *worse* than shipped A on isolated busy (+6.0) and
   *better* by 46 µs on shipped wall. Whatever S/W/N recover, it is not their
   own kernel time; it is the ns8r1 threadgroup geometry they share, and
   geometry is exactly the axis PR #7 showed does not transfer to M5 (τ≈0).

3. **The dispatch-removal arm inverts the sign.** C removes 40 dispatches and
   204.9 µs/step of isolated busy — the largest busy saving of any arm, and the
   only arm that touches the census pool at all — and it is **51.73 µs/step
   slower** in the shipped harness. C differs from W only by the deletion, so
   the deletion alone is worth
   **W − C = 46.33 − (−51.73) = 98.06 µs/step = 2.45 µs/layer of loss**,
   confirming b4's direct `C − W = +96.46 µs = 2.35 µs/layer` and landing within
   4% of the barrier law's 2.55 µs/layer.

The naive census prediction for arm C was "+95.9 µs/step of launch tax
recovered". The measured shipped result is −51.7 µs/step. The error is not 21.7×
in magnitude, it is **the wrong sign**, and the gap between prediction and
outcome is ~148 µs/step.

### 7.4 Encoder barrier census — and what SPLIT=1 does to it

Comment 10 asked whether the encoder barrier count changes under SPLIT=1, with
per-step µs both ways. It does, and the answer is degenerate in a way that is
itself useful:

**Under SPLIT=1 the intra-encoder barrier count is exactly 0, by construction.**
`CommandEncoder::maybeInsertBarrier()` only fires between dispatches that share
a command buffer, and `commit()` resets `needs_barrier_`. SPLIT=1 puts every
dispatch in its own command buffer, so every dependency edge is enforced by a
command-buffer boundary instead of a barrier. The census must therefore be run
at SPLIT=0 (pass 2), and the two regimes price the *same* dependency graph
through two different mechanisms:

| regime | cbs/step | dispatches/step | barriers/step | wall µs | gap µs | gap % |
|---|---|---|---|---|---|---|
| SPLIT=0 (ships) | 45 | 406 | **247** | 8211 | 250 | 3.0 |
| SPLIT=1 (profiling) | 406 | 406 | **0** | 9823 | 1288 | 13.1 |

Both rows are arm A on the same instrumented build.

- Trading 247 barriers for 361 extra command-buffer boundaries costs
  **+1612 µs/step of wall (+19.6%)**, of which **+1038 µs is gap**.
- That is **1038 / 361 = 2.875 µs per extra command buffer**, an independent
  reproduction of the programme's `CB_GAP_US_PER_DISPATCH = 3.03` constant to
  within 5%, measured here by a completely different route (regime contrast
  rather than dispatch-count regression).
- **SPLIT=0 instrumented wall is 8211 µs vs the uninstrumented harness's 8256
  µs for the same arm — 0.5% apart.** So the profile hook is nearly free at
  SPLIT=0, and SPLIT=0 wall is a usable sanity check; SPLIT=1 wall is inflated
  by 19.6% and must never be used to rank arms. (Note that S, the arm with the
  *best* shipped wall of the three same-dispatch-count arms, has the *worst*
  SPLIT=1 wall at 10008 µs. SPLIT=1 wall gets the ranking wrong.)
- `busy_sum` rises 7961 → 8537 µs (+576 µs) from SPLIT=0 to SPLIT=1. SPLIT=0
  attributes per command buffer, SPLIT=1 per dispatch, so +576 µs is an *upper
  bound* on genuine intra-command-buffer overlap: it also contains 361 command
  buffers' worth of per-CB GPU-side start/end overhead. Read as "≤7% of the sum
  of isolated kernel times is absorbed by overlap in shipped mode, on average" —
  and up to 3.2× for a specific nested kernel like `gate_sp`.

Arm A's 247 barriers/step, by downstream (blocked) kernel — recovered by finding
the exact repeat period of the barrier sequence with
`research/nezuko_r109_barrier_period.py` (decode steps are structurally
identical, so the tail is exactly periodic; period = 247):

| barriers/step | downstream kernel |
|---|---|
| 39 | `laguna_shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1` |
| 39 | `laguna_routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6` |
| **31** | **`rmsbfloat16`** |
| 30 | `laguna_decode_nvfp4_qkv_h64_r1_v1` |
| 30 | `laguna_oproj_act_h64_v1` |
| 27 | `laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf1` |
| 15 | `laguna_sliding_fused_attn_ring_v1` |
| 10 | `laguna_oproj_act_h48_v1` |
| 9 | `laguna_decode_nvfp4_qkv_h48_r1_v1` |
| 9 | `laguna_full_fused_attn_grow_v1` |
| 1 each | `gate_sp_h48_v1`, `residual_rms_bf16_2048_v1`, `dense_gate_up_swiglu`, `dense_down_residual`, `lmhead_int5_base_coarse_delta`, `lmhead_coarse_argmax_stage1_v5`, … |

Two readings:

- Only **31 of the 41** `rmsbfloat16` dispatches are actually blocked behind a
  barrier; 10 issue with no wait. And `gate_sp_h48_v1` is a *downstream* blocker
  exactly **once** per step out of 40 gate dispatches — the shipped gate is
  almost never on anyone's critical path, which is the mechanism behind its
  96.4% nesting.
- **"Count edges × 2.55 µs" is refuted as a global estimator.** 247 × 2.55 =
  630 µs/step, 7.7% of wall, and there is no 630 µs of barrier cost to
  recover — the 2.55 µs/layer figure is a *marginal* price for an edge whose
  downstream kernel is on the critical path, not an average over all 247. This
  is the quantitative backing for the §4 refinement.

### 7.5 Barrier count across all five arms: it has no explanatory power

| arm | barriers/step | Δ vs A | dispatches | shipped wall Δ vs A (+ = faster) |
|---|---|---|---|---|
| A | 247 | — | 406 | ref |
| S | 247 | **0** (one relabel) | 406 | **+43.23** |
| W | 247 | **0** (one relabel) | 406 | **+46.33** |
| N | 247 | **0** (one relabel) | 406 | **+51.96** |
| C | **243** | **−4** | 366 | **−51.73** |

The shipped wall spans **98 µs/step** across this family while the barrier count
spans **4**. And the one arm that *reduces* barrier count is the only arm that
*regresses*. Barrier count is not the state variable.

### 7.6 The mechanism, measured: edge transplantation onto a narrow producer

The A→C barrier diff is exactly conservative:

| Δ barriers/step | downstream kernel |
|---|---|
| **−31** | `rmsbfloat16` (31 → 0) |
| **+27** | `gate_sp_rms_emit_h64_v1` (0 → 27) |
| **+4** | `gate_sp_rms_emit_h48_v1` (0 → 4) |
| −4 / +1 / −1 | `oproj_act_h48` 10→6, `qkv_h48` 9→10, `gate_sp_h48` 1→0 |

**31 barriers out, 31 barriers in.** The dependency edge on the residual did not
disappear when the pre-norm was deleted; it was *transplanted* onto the fused
gate kernel, which then became the sole producer of `normalized` for the
5120-threadgroup QKV matvec.

Arm W is the control that proves this is the deletion's doing and not the fused
kernel's: W runs the *same* fused `gate_sp_rms_emit` kernel, also reading the
residual, and it takes **zero** barriers (0 → 0) because `rmsbfloat16` still runs
first and clears `needs_barrier_`. Only when the pre-norm is removed does the
fused kernel have to pay the wait itself and then hold the path.

So the shipped critical path per layer changes as:

| | A / W | C |
|---|---|---|
| producer on path | `rmsbfloat16` — wide, **3.45 µs** | `gate_sp_rms_emit` — **8 TGs**, **6.30 µs** (h64) / 6.24 (h48) |
| gate runs | concurrently, off-path | **on-path** |

Predicted cost of the substitution, from SPLIT=1 isolated latencies alone:

```
30 layers x (6.30 - 3.45) + 10 layers x (6.24 - 3.45)
  = 30 x 2.85 + 10 x 2.79
  = 85.5 + 27.9 = 113.4 us/step  (2.835 us/layer)
```

Measured: **W − C = 98.06 µs/step (2.45 µs/layer)**; b4's direct `C − W`
contrast gave **96.46 µs/step (2.35 µs/layer)**. Prediction is within **16%** of
measurement, with the residual in the expected direction (C also banks the ns8r1
geometry win and returns 3.45 µs/layer of wide kernel work to the machine).

This is the whole result in one line: **the census priced the *pool*
(142 µs/step of `rmsbfloat16`), when the thing that actually moves is the
*critical-path substitution* (+113 µs/step). Same order of magnitude, opposite
sign.**

### 7.7 A drift floor that limits all of §7.2

Comparing A→S per kernel, the only change above noise is `gate_sp`
(−138.0 µs/step, −43%). But ~12 kernels that neither arm touches each drifted
+0.2…+0.6 µs/call, **+~75 µs/step in total**. With `n = 1` per arm that sets a
**single-run global drift floor of ~0.5% ≈ ±40 µs/step** on `busy_sum`. So:

- per-kernel deltas of the size seen for `rmsbfloat16` (−138 µs) and `gate_sp`
  (−138 µs) are trustworthy;
- `busy_sum` deltas in §7.1 (−62 to −160 µs) are drift-contaminated and are
  reported for structure, not for ranking;
- nothing in §7 overrides the b5 harness numbers, which is where the verdict
  comes from.
