# PR #37 Part 0 — the lm_head coarse screen is at its floor

**Verdict: the level-0 family is closed. No Metal was written.**

The proposed screen fails at every configuration, and so does every other
coarser exhaustive screen, for one measurable reason: **the shipped screen is
operating on a cliff.** Widening its certified bound by 25% takes block
survival from 0.7–1.8% to 5.8–13%; doubling it takes survival to 98–99.5%. Any
screen that reads fewer bytes has a bound at least 2x wider (fewer bits) or
5.9x wider (fewer dimensions). There is no configuration in between.

Stop rule from the assignment: *"if the best configuration does not get
expected bytes below ~60 MB/step, stop."* The best configuration gets expected
bytes to **120.8 MB/step**, i.e. **above** the 112–117 MB/step the shipped
cascade already achieves. Every level-0 configuration is a regression.

---

## 0. Instrument, and its validation

Two real teacher-forced decode runs on the frontier tree
(`BASE_SHA=768bb9d4`, M4 Pro 48 GiB, `.build-worker` binary), with a temporary
env-gated hook writing the row entering `lm_head` after the final RMSNorm
(`LagunaRuntimeModel.swift:10857`) for every single-token forward. The hook was
reverted after the dumps; **no source file in `editablePaths` is modified by
this PR.**

| run | case | steps | worker |
| --- | --- | --- | --- |
| A | `public_longcopy_gate_english_512_256.json` | 128 | 0 divergences |
| B | `public_longcopy_gate_english_512_1024.json` | 512 | 0 divergences |

Offline (`research/maple_fern_pr37_stage_a.py`) the bf16 `lm_head.weight` is
read straight from `weights/model-00005-of-00005.safetensors` and the int5
planes are rebuilt exactly as `LagunaLmHeadPruner.buildInt5Planes`
(`LagunaLmHeadPrune.swift:864-919`) builds them: same scale rule, same bump
test, same offset-binary split, `max|q| = 15.0` (the init guard's boundary,
reproduced).

Three independent checks that the offline model *is* the shipped model:

1. **Token identity.** `argmax` of the offline fp32 logits equals the golden
   greedy token on **128/128** and **512/512** steps.
2. **Survivor identity.** The reproduced level-one screen yields **458.0 mean
   live 4-row blocks** on run A. The assignment states *"roughly 458 live 4-row
   blocks of 25,088"*. Independent agreement to the unit.
3. **Block fill.** 1.17 wanted rows per live block (run A), 1.14 (run B);
   assignment states ~1.2.

All tables below are run B (512 steps) unless marked; run A is quoted where it
differs, and the two never disagree qualitatively.

---

## 1. Q1 — concentration of `x`. The lm_head input is nearly flat in L1.

Share of `sum_j |x_j|` carried by the top-n channels (min / med / max over the
512 steps):

| top-n | 64 | 128 | 256 | 512 | 1024 |
| --- | --- | --- | --- | --- | --- |
| min | 0.119 | 0.202 | 0.335 | 0.534 | 0.798 |
| med | 0.132 | 0.212 | 0.342 | 0.540 | 0.806 |
| max | 0.142 | 0.220 | 0.347 | 0.547 | 0.815 |

Share of L2 energy `sum_j x_j^2`:

| top-n | 64 | 128 | 256 | 512 | 1024 |
| --- | --- | --- | --- | --- | --- |
| min | 0.299 | 0.423 | 0.589 | 0.772 | 0.940 |
| med | 0.358 | 0.471 | 0.619 | 0.789 | 0.946 |
| max | 0.420 | 0.517 | 0.648 | 0.804 | 0.951 |

At the **group-of-128 granularity** the bound requires (share of `sum_j |x_j|`
in the top-K groups):

| top-K groups | 1 | 2 | 4 | 8 | 12 |
| --- | --- | --- | --- | --- | --- |
| min | 0.068 | 0.136 | 0.267 | 0.520 | 0.765 |
| med | 0.071 | 0.140 | 0.275 | 0.531 | 0.773 |
| max | 0.076 | 0.147 | 0.284 | 0.544 | 0.783 |

Reading: the massive-activation literature is **half right here**. There is
real outlier structure — the top 64 of 2048 channels (3.1% of channels) carry
36% of the L2 energy, a 11x concentration. But the certificate's tail term is
an **L1** functional, and in L1 the same 64 channels carry only 13.2%, a 4.2x
concentration; the top 256 carry 34%, i.e. 2.7x uniform. At the group-of-128
granularity the selection must use, the top 2 of 16 groups carry **14.0%** —
*1.1x uniform*. Averaging 128 neighbouring channels destroys almost all of the
outlier structure, because the outliers are isolated channels, not contiguous
runs.

The spread across steps is negligible (max−min ≈ 0.01), so this is a property
of the model's final hidden state, not of a token or a prompt.

---

## 2. Q4 — the tolerance curve. **This is the result that closes the family.**

The screen's coarse value is held fixed and its certified bound `delta` is
multiplied by `m`. This prices *any* proposal that widens the bound, whatever
the mechanism:

| m | survivor rows | live blocks | block share | (run A blocks) |
| --- | --- | --- | --- | --- |
| 0.50 | 2.1 | 2.0 | 0.0001 | 45.6 |
| 0.75 | 20.1 | 19.2 | 0.0008 | 45.6 |
| 0.90 | 82.8 | 75.7 | 0.0030 | 189.2 |
| **1.00 (shipped)** | **207.4** | **182.4** | **0.0073** | **458.0** |
| 1.10 | 528.5 | 441.6 | 0.0176 | 1053.1 |
| 1.25 | 1916.5 | 1464.8 | 0.0584 | 3288.8 |
| 1.50 | 12428.2 | 7834.7 | 0.3123 | 13050.1 |
| 2.00 | 74491.3 | 24514.0 | 0.9771 | 24964.0 |
| 3.00 | 100117.0 | 25074.8 | 0.9995 | 25075.8 |
| ≥6.00 | 100352.0 | 25088.0 | 1.0000 | 25088.0 |

The economics of a two-level cascade: level-0 costs `B0`, survivors then pay
`survival x 109.2 MB` of level-one refill (at 4-row block granularity). Break
even needs `survival < 1 - B0/109.2`, and the assignment's target (~60 MB/step)
needs survival ≈ 5%. From the table, **5% survival is reached at m ≈ 1.22, and
25% at m ≈ 1.45.** The usable budget for widening the bound is therefore
**about 20–25%, not a factor of anything.**

---

## 3. Q2/Q3 — the proposed top-K screen, priced

`delta0_i = sum_{j in S} sd_g |x_j| + sum_{G not in S} M_iG * sum_{j in G} |x_j|`,
with `M_iG` the **exact** per-row, per-128-group maximum (i.e. the most
favourable possible version — no 1-byte rounding penalty applied), `S` chosen
per token as the top-K groups by `sum_{j in G} |x_j|`, and the level-0 argmax
used for the step-3 threshold exactly as the shipped rule does.

| K | dims | B/row | level0 MB | survivor rows | live blocks | share | L1 refill MB | **total MB/step** |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 128 | 84 | 8.4 | 100352.0 | 25088.0 | 1.000 | 109.2 | **120.8** |
| 2 | 256 | 152 | 15.3 | 100352.0 | 25088.0 | 1.000 | 109.2 | **127.7** |
| 4 | 512 | 288 | 28.9 | 100352.0 | 25088.0 | 1.000 | 109.2 | **141.3** |
| 8 | 1024 | 560 | 56.2 | 100352.0 | 25088.0 | 1.000 | 109.2 | **168.6** |
| 12 | 1536 | 832 | 83.5 | 100290.5 | 25081.6 | 1.000 | 109.2 | **195.9** |

**Every row of the vocabulary survives at every K.** Shipped baseline for
comparison: 112.4 MB/step (run B) / 117.3 MB/step (run A). The design's target
was ~40 MB/step.

The failure is not marginal, and §4 says it cannot be repaired by a better
selection rule, a finer granularity, or a cleverer tail bound.

---

## 4. Bound anatomy — why, in one number

Tail bound over the **whole** row, in units of the shipped level-one delta:

| form | ratio |
| --- | --- |
| per-group max x L1 of x (the assignment's form) | **12.72x** |
| per-group Cauchy–Schwarz `\|\|w_G\|\|2 \|\|x_G\|\|2` (tighter, 2 B/row/group) | **5.93x** |

Per-element, the level-one code bounds the error at `sd_g <= gmax_g/8`; the
tail bound has nothing better than `gmax_g` — a 12.7x per-element penalty for
*not reading* the code. Splitting by K:

| K | head/d1 | tail(max)/d1 | tail(CS)/d1 | best delta0/d1 | fits 1.25x? |
| --- | --- | --- | --- | --- | --- |
| 1 | 0.072 | 11.81 | 5.50 | 5.57 | FAIL |
| 2 | 0.141 | 10.92 | 5.08 | 5.22 | FAIL |
| 4 | 0.277 | 9.19 | 4.27 | 4.55 | FAIL |
| 8 | 0.534 | 5.93 | 2.72 | 3.25 | FAIL |
| 12 | 0.776 | 2.84 | 1.31 | 2.08 | FAIL |
| **15 of 16** | 0.946 | 0.68 | 0.31 | **1.26** | **FAIL** |

The last row is the decisive one. **Even reading 15 of the 16 groups — 94% of
the level-one bytes — the best available tail bound lands at 1.26x, just past
the cliff, for a 6% byte saving that a 5.8% survival rate immediately spends.**
There is no K that both saves bytes and keeps the bound.

Inverting: for the max-form tail to fit inside the 1.25x tolerance, the unread
channels may carry at most **1.97%** of `sum_j |x_j|`. The flattest split
available (top-15 of 16 groups) leaves **5.73%** there. Gap: **3x** — and that
is at the configuration that saves almost nothing.

The invariant behind this, worth keeping: a certified bound over `n` unread
dimensions costs `O(n · E|w| · E|x|)` while the true contribution is
`O(sqrt(n) · rms_w · rms_x)`. The bound is `sqrt(n)` too loose *by
construction*, and with `n = 1792` that is a factor of 42. Only near-total
concentration of `|x|` can beat it, and §1 measures the concentration as 1.1x
uniform at the required granularity.

---

## 5. The 2-bit / 3-bit fallback, evaluated the same way

Exact coarse recomputed for each plane width (not extrapolated), with the
matching certified bound `2^(4-b) x d`:

| b | B/row | exhaustive MB | survivor rows | live blocks | share | **total MB/step** |
| --- | --- | --- | --- | --- | --- | --- |
| **4 (shipped)** | 1088 | 109.2 | 207.4 | 182.4 | 0.0073 | **112.4** |
| 3 | 832 | 83.5 | 74355.6 | 24514.5 | 0.9771 | **516.5** |
| 2 | 576 | 57.8 | 100311.7 | 25081.7 | 0.9998 | **500.8** |

Dropping one bit doubles the bound, which the tolerance curve prices at 98%
survival. The 3-bit plane saves 25.7 MB and spends 430 MB. The nibble plane is
the floor of the bit-width axis, exactly as it is the floor of the
dimension-selection axis.

---

## 6. Can a *tighter* certificate buy headroom? No, and here is the number.

The strongest bound I know that costs no per-step bytes:
`|r_i · x| <= ||r_i||_2 ||x||_2` (Cauchy–Schwarz on the quantization residual),
with `||r_i||_2` one init-time scalar per row (0.2 MB resident) and `||x||_2`
computable for free where the row is already read.

| b | L1 bound/d1 | CS bound/d1 | min-of-two/d1 | live blocks |
| --- | --- | --- | --- | --- |
| 4 | 1.000 | **0.809** | 0.812 | 182.4 → **31.2** |
| 3 | 2.000 | 1.620 | 1.626 | → 13079.2 (52%) |
| 2 | 4.000 | 3.287 | 3.299 | → 25081.7 (99.98%) |

The CS bound is genuinely tighter — 0.809x, a 19% reduction, cutting live
blocks 5.9x — and it still leaves the 3-bit plane at 1.63x, i.e. **52%
survival**. A better certificate does not rescue a coarser plane.

**And its own value is near zero, which is the last thing this analysis
settles.** The shipped decode path is already a three-level cascade
(`lagunaLmHeadRefinedExactKernel`), so the bytes behind the level-one screen
are much smaller than the 7.5 MB a one-level model suggests:

| variant | stage-A live blocks | stage-B rows (BF16 GEMV) | residual re-read | BF16 GEMV |
| --- | --- | --- | --- | --- |
| shipped (L1 bound) | 182.4 (max 7261) | **2.1** (max 39) | 0.23 MB | 0.01 MB |
| min(L1, CS) | 30.3 (max 1469) | 1.3 (max 8) | 0.04 MB | 0.01 MB |

Run A: 458.0 / 3.8 rows / 0.59 MB / 0.02 MB, → 71.8 / 2.0 / 0.09 MB.

The entire refinement tail is **0.24–0.61 MB/step**, and the tightest bound
available removes at most **0.5 MB/step = 0.03% of the 1794 MB decode budget**.
This also explains nezuko's roofline entry
(`research/nezuko-decode-roofline.md:264`): `lmhead_exact_inline_mask_block_v1`
is **76.6 µs/step moving ~0.5 MB** and is correctly labelled *latency*, not
bandwidth. Its cost is 3136 threadgroups of launch and the 0.8 MB of
coarse/delta/output traffic, not the candidate GEMVs.

---

## 7. What this means for the module

- **The 109.2 MB exhaustive level-one read is irreducible under a certified
  screen.** Both axes that could shrink it — bits per element and elements per
  row — are measured and both are past the cliff at their first step.
- **The refinement tail is already at 0.2–0.6 MB/step.** Nothing downstream of
  the screen is worth optimizing for bytes; the remaining `lm_head` cost is the
  76.6 µs latency-bound exact dispatch, which is a *threadgroup-geometry* arm
  and therefore, per §2 of `CURRENT_RESEARCH_STATE.md`, must be settled on the
  official M5 rather than here.
- The one lever a certified screen leaves is **reducing `sum_j |x_j| · sd_g`
  itself**, i.e. a lm_head-specific *finer group scale* (smaller `sd`) at the
  same byte width. That is a transform-side question about the packing, not a
  screen question, and it is out of scope for this arm.

## 8. By-product — the 30.03 vs 22.34 µs/layer gap is instrument, not kernel

The assignment also asked me to reconcile PR #36's standalone probe (30.03
µs/layer for `sliding_fused_attn_ring_v1`) with PR #9's SPLIT dispatch profiler
(22.34 µs true). I extended `senpai/tools/sliding-attn-probe/main.swift` to time
every variant under both command-buffer layouts and both clocks, so all four
cells come from one process, one kernel, one set of buffers.

| layout | clock | µs/layer (4 processes) | spread |
|---|---|---|---:|
| batched, 30 dispatches/buffer | host wall | 28.21, 26.37, 27.29, 28.10 | 7% |
| batched, 30 dispatches/buffer | GPU device | 23.98, 21.96, 22.93, 23.99 | 9% |
| split, 1 dispatch/buffer | GPU device | **22.78, 22.74, 22.66, 22.72** | **0.5%** |

Split GPU-clock gives 22.73 µs mean against nezuko's 22.34 (its split `us/call`
minus the 1.33 µs/command-buffer term). **1.7% apart — below the probe's own ~2%
resolution floor.** The two harnesses agree; 22.34 is the right kernel cost and
30.03 was the outlier. The gap decomposes as:

- **+4.1 µs/dispatch** host encode/commit/wait that `DispatchTime` counts and
  `gpuStartTime`/`gpuEndTime` do not (+18% on 22.7);
- **+1.2 µs/dispatch** command-buffer *window granularity*: a buffer spanning 30
  dispatches has its `gpuStart → gpuEnd` span include the inter-dispatch gaps a
  one-dispatch buffer excludes (batched GPU 23.99 vs split GPU 22.72);
- the remainder, cross-process variance of the host clock — which is exactly the
  ~10% the probe's own README already warned about.

The host tax is **constant per dispatch**, not proportional: 4.11 µs/dispatch for
the shipped 32-threadgroup grid and 4.13 µs/dispatch for the same kernel
under-dispatched to 8 threadgroups, whose GPU time differs by 1.5×. So it
cancels in an A/B difference and does not cancel in an absolute. That is the
precise reason PR #36's *differential* calibration held to 0.77% end-to-end
while its *absolute* per-layer figure was 24% high — both facts are true at once
and neither invalidates the probe for the A/B work it is used for.

**Consequence, and it is not small.** The probe README priced the family from
the absolute: 30 × 30.03 µs = 0.901 ms of a 14.622 ms decode token = 6.16% of
decode, zero-cost ceiling score 1.049. Corrected: 30 × 22.73 µs = **0.682 ms =
4.66% of decode, zero-cost ceiling score 1.0365**. Every headroom figure derived
from 30.03 µs is ~1.2 score points too generous, including the re-pricing of the
merged sliding-attention work (22.34/30.03 = 0.744, so a claimed ~0.48% becomes
~0.36%). I have corrected `senpai/tools/sliding-attn-probe/README.md` in place,
since other students read it as the calibration document.

I also found and documented a footgun there: the `label:file.metal:heads` field
sets *only* the dispatched threadgroup count, so reusing one `.metal` at two
heads values under-dispatches it instead of retiming it at a new width — and the
bitwise diff still prints 0, because the heads the shorter grid never writes
retain the reference's bytes.

## Reproduce

```bash
# temporary hook: dump `hidden` at LagunaRuntimeModel.swift:10857 for dims(1,1)
MLXFAST_DUMP_LMHEAD_X=/tmp/lmhead_x.f32 python3 research/decode_probe.py --steps 128 --prefill
python3 research/maple_fern_pr37_stage_a.py      # planes, exact logits, residual norms
python3 research/maple_fern_pr37_stage_b.py      # every table above

# §8 instrument reconciliation
cd senpai/tools/sliding-attn-probe
xcrun swiftc -O main.swift -o probe -framework Metal -framework Foundation
./probe shipped:probe_orig.metal:2
```
