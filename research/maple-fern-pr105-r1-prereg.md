# PR #105 r1 — pre-registration: LM-head int5 base-plane re-split 4+1 → 3+2

Written **before** any measurement on this branch. Nothing below is edited
after a number is collected; corrections are appended as dated addenda.

- Assignment: `maple-2026-08-06k-lmhead-base-plane-resplit`, revision `r1`
- Branch `maple-fern/lmhead-base-plane-resplit`, `BASE_SHA`
  `dec0a83c075d151ef5dec94f4005bd39ff2c2d69`
- Host: this M4 Pro research box (Apple GPU gen 16, sub-64 GiB profile).
  Ranked hardware is M5 Max; every number here is directional evidence only.

## 0. Preflight (already run, quoted for the record)

```
senpai/check-editable-budget.sh dec0a83c…
editable budget OK: current=2934331/3000000 bytes headroom=65669
  growth=0/262144 files=142 (file count is diagnostic only; base=142)

senpai/validate-assignment-scope.sh dec0a83c… \
  Sources/MLXFastModel/LagunaLmHeadPrune.swift \
  Sources/MLXFastModel/LagunaRuntimeModel.swift
assignment scope OK: 2 submitted path(s)
```

Headroom is 65 669 B and PR #101 / PR #103 compete for the same pool, so the
3+2 rewrite must be close to byte-neutral in the submitted surface.

## 1. Mechanism under test

Stage 1 of the lm-head cascade (`laguna_lmhead_int5_base_coarse_delta_bf16_v1`)
today streams a 4-bit base plane (`codes_base`, 1024 B/row) plus a 64 B/row
e8m0 scale row over the full V = 100 352 vocabulary, every decode step:

```
(1024 + 64) B × 100 352 = 109.18 MB/step
```

The change moves the code split from 4+1 (nibble base, 1-bit residual) to 3+2
(3-bit base, 2-bit residual). Total stored bits are unchanged
(768 + 512 = 1024 + 256 = 1280 B/row); only the *screen width* changes:

```
(768 + 64) B × 100 352 = 83.49 MB/step      → −25.69 MB/step
```

The trade is exact and one-dimensional: a cheaper stage-1 read in exchange for
a weaker certificate, hence more rows surviving into tier 1 (the sparse refine
kernel), which must then read the wider 512 B residual row instead of 256 B.

## 2. Deliverable 0 — hard gate (survivor census)

### 2.1 What is measured

An env-gated (`DARKBLOOM_LMHEAD_PRUNE_STATS=1`) host-side MLX mirror of the
kernel screen inside `LagunaLmHeadPruner.logits(...)`, counting

```
survivors_k     = count( coarse + k·delta ≥ thr )
live4blocks_k   = count of 4-row blocks with any survivor
```

for `k ∈ {1, 1.5, 2, 2.5, 3, 4}` across all 128 timed decode steps.

`k = 1` reproduces today's 4+1 screen exactly. `k = 2` is the faithful proxy
for the proposed 3+2 screen, because:

- the 3-bit half-cell is exactly twice the 4-bit half-cell, so
  `delta₃ = 2·delta₄` identically (§Deliverable 1, item 1); and
- `coarse₃ − coarse₄` is a zero-mean rounding term. With `delta ≈ N·E[sd|x|]`
  and the centre shift having std `≈ 0.5·√N·rms(sd·x)`, the ratio is
  `O(1/√N) ≈ 1 %` at N = 2048. It cannot move a survivor count that is
  two orders of magnitude away from break-even.

The probe forces a host sync per call, so **timings from that build are
discarded; only counts are used.** The probe is removed before any timing run.

### 2.2 Pre-registered prediction

Prior evidence (nezuko census on the pre-#20 tree, 128 timed decode steps,
same M4 host): 4+1 survivors mean **534**, median 288, min 55, max 9193;
live 4-row blocks mean 458 (1.83 % of blocks).

I predict `survivors_{k=2}` has **mean below 6 000 rows** and
`live4blocks_{k=2}` **mean below 5 000 blocks**.

Rationale: the screen margin distribution is heavy in the tail but the bulk of
the vocabulary sits many `delta` widths below `thr`; doubling `delta` walks the
cut a fixed distance into a distribution that already discards 99.5 % of rows
at k = 1.

### 2.3 Cost model and the gate

Tier-1 (refine) cost per surviving row:

| split | residual B/row | scales B/row | total |
|---|---|---|---|
| 4+1 (today) | 256 | 64 | 320 |
| 3+2 (proposed) | 512 | 64 | 576 |

The refine kernel dispatches on 4-row blocks, so the physical unit is
`live4blocks × 4 × bytes_per_row`. Net saving per step:

```
net_MB = 25.69 − (live4blocks_{k=2}·4·576 − live4blocks_{k=1}·4·320) / 1e6
```

Break-even is at ≈ 44 600 live rows (44 % of the vocabulary). Net saving stays
at or above 20 MB for ≤ ≈ 10 300 live rows (10.3 %).

**Gate.**

- net ≥ 20 MB/step → proceed to the kernel rewrite;
- 10–20 MB/step → stop, report, ask the advisor;
- < 10 MB/step → stop and write the experiment up as a decisive negative.

### 2.4 The retro-diagnostic the advisor asked for

The advisor's §R20.2 forward price for PR #20 was **+0.41 % of score per
25.7 MB/step**, i.e. 0.59× of the byte roofline and below the §0.9.36
1.0–1.2× band. The live hypothesis is that survivor traffic ate the
difference. The `k = 1` arm of this same census tests that directly: at 534
surviving rows × 320 B = **171 KB/step**, tier-1 re-read recovers 0.7 ‰ of the
25.69 MB. I pre-register the prediction that **survivor traffic does not
explain the shortfall** and that the residual must be attributed to refine
kernel latency, dispatch overhead, or the M4→M5 transfer itself.

## 3. Deliverable 1 — superset proof obligations

Stated here so the acceptance criteria are fixed before the code exists. Each
must hold for the 3+2 kernel to be a sound screen (proof written up in the
result note):

1. **Level-1 interval.** `q₀ = 4·H₃ − 14.5`, `|q − q₀| ≤ 1.5`, so
   `|w − sd·q₀| ≤ 2·sd`: the delta term is exactly `2×` today's.
   Implemented as `2.0f * d_acc` — a power of two, hence exact.
2. **Ratio bound.** `|q₀| ≤ 14.5` ⇒ `m ≤ 7.25·d` termwise ⇒
   `d(1+γ) + 2γm ≤ d(1 + 15.5γ)`. The kernel emits the strictly wider
   `d·(1 + 16.0f·GAMMA)`; `1 + 2⁻¹¹` is exact in FP32 and monotone-safe.
3. **Refine correction exactness.** `4H₃ − 14.5 + (r − 1.5) = 4H₃ + r − 16 = q`
   exactly: all terms are multiples of 0.5 with ≤ 6 significand bits.
4. **Refined certificate.** With half-cell `d`, `D₃ = 4d` and
   `m ≤ 29d + 3d = 32d`, giving `d(1 + 65γ)` — **identical to today's refined
   bound**, so tier-2 survivor count is unchanged by construction.
5. **Refined multiplier.** `4d(1+16γ)·c ≥ d(1+65γ)` requires
   `c = (1+56γ)/4 = 0x1.007p-2` (margin 7γ), replacing `0x1.005p-1f`. The
   product is exact: widened bf16 delta ≤ 8 significand bits + 13-bit constant
   = 21 < 24.
6. **Init guard unchanged.** `maxCode ≤ 15.0` still gives `u ∈ [1,31]` ⇒
   `H₃ ∈ [0,7]`, `r ∈ [0,3]`. The decline-to-stock-head path is untouched.
7. **Threshold soundness unchanged.** The exact-winner BF16-predecessor proof
   at `LagunaLmHeadPrune.swift:404-422` depends only on `e_r ≤ e_winner` and
   is independent of the split.

## 4. Layout (Layout E), fixed before implementation

- `codes_base` → **[V, 768]**. Per 32-element group `g` at byte offset
  `g·12`: 8 B of 2-bit codes (`hi2 = u>>3 ∈ [0,3]`) then 4 B of 1-bit codes
  (`b1 = (u>>2)&1`). One buffer, one DRAM stream, 4-byte aligned.
- `codes_resid` → **[V, 512]**, group `g` at `g·8`, 2-bit `r = u&3`.
- Reconstruction: `hcode = (hi2<<3)|(b1<<2) ∈ {0,4,…,28}`,
  `ve = float4(hcode) − 14.5f`; residual `ve = float4(r) − 1.5f`.
- The one-pass prefill / control kernel is rewritten to the same planes,
  reconstructing `q = 8·hi2 + 4·b1 + r − 16` at the unchanged 20 B/group.

## 5. Timing protocol (conditional on the gate passing)

- Build and time **only** through `research/run_local_benchmark.sh
  --local-iterate`. No bare `swift build -c release`.
- Counterbalanced within-binary interleave, order
  `on off off on off on on off on off off on`, n ≥ 3 pairs per arm.
- Mandatory base↔base A/A arm; analysis with `research/maple-nezuko-pr72/
  analyze.py` and `drift.py`.
- Renormalise with `research/nezuko-renormalise.py`
  (`norm_decode_su = 0.013890/decode`, `norm_prefill_su = 0.0003845/prefill`).
  Local prefill is **not** an instrument on this host (`prefill_speedup ≈ 0.32`
  even byte-identical), so only decode µs/step is interpreted.

### Pre-registered timing prediction

At the §0.9.36 byte-channel band of 1.0–1.2× roofline, 25.69 MB/step removed
against the M4 ceiling of 260.2 GB/s is **98.7 µs/step**; net of the tier-1
re-read predicted in §2.3 this is ≈ 95–99 µs/step on M4. Converting at
1 µs/step = 0.0149 % of score against the 4908 µs frontier step gives a
**predicted +1.42 % of score**, interval [+0.85 %, +1.70 %] once the observed
0.59× PR #20 transfer is admitted as the pessimistic end.

**Falsifier.** If the matched interleaved M4 decode delta is below
**+40 µs/step** (i.e. under 0.41× of roofline, worse than PR #20's own
already-sub-band transfer), the mechanism is declared not to transfer and the
result is reported as a negative regardless of sign.

## 6. Correctness acceptance

- Identical `golden_hash` under a differing `harness_hash` (per §0.9.35,
  `max_abs_diff` is a hardcoded literal and is **not** evidence).
- `research/run_upstream_equivalence.sh` passing with a reported non-zero test
  count. Noting the known scope gap: `LagunaUpstreamEquivalence.swift:74` never
  calls `prepareFusedRuntimeWeights()`, so the oracle does not exercise the
  pruner; this is reported, not worked around.
