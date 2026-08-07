# PR #284 / H5 — certify-then-refine lm-head screen: KILLED at Step 1

Student `maple-nezuko`, assignment `maple-2026-08-07j-lmhead-sound-pruning` r1,
base `5daa8389c416928fce41a7cdee41649dbc9569fb`. Host: M4 Pro, Apple GPU gen 16.
All decode timing below is directional per standing rule 10; the byte accounting
and the R-distribution are host-independent.

**Verdict: no cheaper first screen in this certificate family can eliminate any
of the 109,187,072 B tier-0 read. The measured saving of the best sound design
is 0.00 MB / 0.0 µs, against the assignment's 164 µs target and its own 80 µs
kill threshold.**

Shipped artifact: Step 0.5 only — deletion of the dead row-major refine arm,
−8,166 B of the editable byte pool, timing-neutral by construction.

---

## Step 0 — per-dispatch byte accounting (read out of kernel source, not assumed)

`Sources/MLXFastModel/LagunaLmHeadPrune.swift`, decode arm (`useFusedRefinement:
true`), V = 100,352, hidden = 2,048 (4,096 B bf16):

| # | kernel | grid / tg | reads (B) | writes (B) |
|---|---|---|---|---|
| 5a | `laguna_lmhead_int5_base_coarse_delta_bf16_v1` | (V/16·512,1,1) / 512 | x 4,096 + codes_lo 102,760,448 + scales 6,422,528 = **109,187,072** | coarse f32 401,408 + delta bf16 200,704 |
| 5b | `laguna_lmhead_coarse_argmax_stage1_v5` | (224,128,1) / 224 | coarse 401,408 | 896 |
| 5c | `laguna_lmhead_exact_winner_bf16_midpoint_threshold_v1` | (32,1,1) / 32 | one bf16 row 4,096 | thr[1] f32 |
| 5d | `laguna_lmhead_exact_fused_int5_sparse_refine_v1` | (V/32·256,1,1) / 256 | coarse+delta 602,112 unconditional + survivors×320 B + refined×4,096 B | logits bf16 200,704 |

Arm-A decode lm-head total ≈ **110.99 MB/step**. Note the advisor's 109,182,976 B
excludes the 4,096 B `x` vector; the kernel reads it, hence 109,187,072 B.

### Marginal byte price, measured (3 reps × 3 arms, interleaved, one session)

`research/nezuko-pr284-byte-price.sh` → `research/artifacts/nezuko-pr284-byte-price.tsv`.
All 9 arms `passed: True` with correctness passing.

| arm | mean µs/token | sd |
|---|---|---|
| A — default (pruner on, fused refine on) | 12,899.4 | 57.0 |
| B — `DARKBLOOM_LMHEAD_FUSED_REFINEMENT=0` | 13,042.8 | 39.2 |
| C — `DARKBLOOM_LM_HEAD_PRUNE=0` (dense bf16 GEMV) | 14,112.0 | 24.0 |

**C−A paired = 1,212.6 µs (sd 80.9)** for +300.2 MB of traffic
⇒ **4.039 µs/MB ⇒ 247.6 GB/s effective on this M4 Pro.** This is the trustworthy
anchor: a dense contiguous bf16 GEMV, pure DRAM traffic, no kernel-family change.

B−A = 143.4 µs (sd 82.1) is **unusable** — it swaps the whole kernel family
rather than isolating a byte delta, and its sd exceeds half its mean.

### Step 0 kill criterion

5a's 109.187 MB is:
- **441.0 µs = 3.42 %** of the 12,899 µs M4 decode step at the measured 247.6 GB/s;
- **252.2 µs = 6.09 %** of the 4,143.6 µs M5 decode step at the programme's 433 GB/s.

The assignment's stated criterion was **"KILL if 5a is under 8 % of decode step
time."** It is 6.09 % on M5 and 3.42 % here. Step 0 already triggers the kill.
I continued to Step 1 anyway, because the 8 % threshold and the +2.50 % pricing
in the same brief are mutually inconsistent and I did not want to close the
largest open decode question on a threshold argument alone.

---

## Step 1 — the certificate-slack histogram (this is the decisive result)

### What the current screen actually is

5a emits, per row i, a coarse value `c_i` from the top 4 bits of the int5 code
plus a certified one-sided error `delta_i`. The kernel doc (`:237-252`) and the
source agree: on the refine/decode path the nibble midpoint is `q0 = 2H − 15.5`
so `|q − q0| = 0.5` exactly, giving `d_i = sd·Σ|x|` and
`delta_i = d_i·(1 + 32γ)` with γ = 2⁻¹⁵ (32γ = 2⁻¹⁰, exact in FP32), rounded
**up** into bf16. (The non-refine/prefill path uses the half-cell form
`d_i = (sd/2)·Σ|x|` in `...RatioBoundDeltaBF16Kernel`, 1,344 B/row.)

5d keeps row i iff `c_i + delta_i >= thr` (`:670`). So the screen is already a
sound branch-and-bound: `delta` **is** the certificate radius.

### The only quantity that matters

Write `Q = ½·sd·Σ|x|`, so today's `delta = B₁ = 2Q`. Dropping j LSBs from the
code multiplies the cell width by 2ʲ, giving certificate radius `B_j = Q·2ʲ`.
A row can be soundly dropped by a *j-bit* tier-0 iff

```
thr − c₁  >  B₁ + 2·B_j     ⟺     R > 1 + 2ʲ,    where R ≡ (thr − c₁)/delta
```

(the `B₁` term is the reference row's own uncertainty; the factor 2 is the
coarse-value shift plus radius of the coarser code). So:

| tier-0 width | plane B/row | MB/step | sound drop needs |
|---|---|---|---|
| 5-bit | 1,344 | 134.87 | — |
| **4-bit (today)** | **1,088** | **109.19** | **R > 1** |
| 3-bit | 832 | 83.49 | R > 5 |
| 2-bit | 576 | 57.80 | R > 9 |
| 1-bit | 320 | 32.11 | R > 17 |

Bit-plane re-slicing keeps 1,280 + 64 = 1,344 B/row resident, so none of these
cost extra RAM. **R is therefore the entire experiment.** If R is routinely > 5
we win; if it is pinned near 1–2 we lose, and no amount of kernel work changes it.

### Measurement

`research/nezuko-pr284-slack-probe.patch` (2,609 B, kept **out of `Sources/` in
committed form** per rule 11) adds a `DARKBLOOM_LMHEAD_SLACK_PROBE=1`-gated
kernel that emits, per decode step,
`SLACKHIST c1 c2 c3 c5 c7 c9 c13 c17 c25 c33` where `c_T = #{rows : R ≤ T}`.
It is dispatched between the `thr` dispatch and `let assembled =` in
`logits()`, i.e. on the real scored decode path with the real `thr`.

`research/nezuko-pr284-slack-histogram.sh` applies the patch, builds the worker,
runs `research/decode_probe.py --steps 128`, greps the result, and reverts via
`trap cleanup EXIT`.

Run `c99c9a2b-f660-4c4c-a87d-35831f910122`: 72 s, exit 0, **129 SLACKHIST lines**,
`teacher-forced greedy tokens: 0 divergences (all match)`.
Result: `research/artifacts/nezuko-pr284-slack-hist.txt`.

### The distribution (129 real decode steps)

```
  R<=T      mean    median      min      max   %vocab
     1     777.2     288.0       55    31914    0.775
     2   86057.6   89172.0    60760   100171   85.756
     3  100209.0  100242.0    99988   100352   99.858
     5  100352.0  100352.0   100352   100352  100.000
     7 .. 33     (identical: 100352 = 100.000 %)
```

**Not one row, in any of 129 steps, has R > 5.** 99.86 % of the vocabulary sits
at R ≤ 3 and 100 % at R ≤ 5. The 31,914 outlier at R ≤ 1 is the first decode step
after the seed (also the 9.58 ms step against an 8.4 ms steady state).

### Pricing every design in the family

`research/nezuko-pr284-slack-analyze.py`, M5 @ 433 GB/s, baseline 109.38 MB/step
= 252.6 µs = 6.10 % of the decode step:

| design | bytes saved | µs saved | score | verdict |
|---|---|---|---|---|
| 3-bit tier-0 → +1b @R≤5 → +1b @R≤1 | 0.00 MB | 0.0 | +0.00 % | **DEAD** |
| 2-bit tier-0 → +2b @R≤9 → +1b @R≤1 | 0.00 MB | 0.0 | +0.00 % | **DEAD** |
| 1-bit tier-0 → +1b @R≤17 → +2b @R≤9 → +1b @R≤1 | 0.00 MB | 0.0 | +0.00 % | **DEAD** |
| 2-bit side plane (keep lo/hi, reread 4b @R≤9) | **−51.38 MB** | **−118.7** | −1.81 % | **DEAD (worse)** |

### Robustness: even the *unsound* optimistic bracket fails

To make sure the kill is not an artefact of my (conservative) `1 + 2ʲ` bracket, I
also priced the optimistic bracket `R > 2^(j−1)`, which assumes the `c_j − c₁`
shift concentrates instead of taking its worst case. This is **not a sound
screen** — it is a strict upper bound on what any coarser tier-0 could ever save:

- 3-bit, drop if R > 2 → 14,294 rows drop → **8.5 µs**
- 2-bit, drop if R > 4 → 143 rows drop → **0.2 µs**
- 1-bit, drop if R > 8 → 0 rows drop → **0.0 µs**

All three are an order of magnitude under the 80 µs 3-sigma floor.

### Why this generalises beyond bit-truncation (M1/M2/M3 all die here)

To drop 90 % of rows, *any* cheaper tier-0 must have a certified bound below the
10th percentile of `thr − c₁`. The histogram places that percentile between **1×
and 2× today's `delta`**. Halving the code width multiplies the bound by 4×.
**The whole "coarser first screen" family is off by roughly 10×.**

M1 (Cauchy–Schwarz per-row norm) is strictly looser than a magnitude-aware
per-row bound and therefore strictly worse than the 1-bit row above, which
already drops zero rows. M2 (blocked Hölder) interpolates between M1 and the
current bound and cannot beat the 1-bit row without approaching 1,088 B/row.
M3 (two-tier code plane) *is* the row set priced above. The histogram kills all
three with one measurement.

The converse is the useful part: today's screen already leaves only **777 rows
(0.78 % of vocab) on average**, so tiers 2 and 3 would cost ~0.6 µs. Beyond
tier-0 the pruner is already essentially optimal. The 109.19 MB tier-0 read is
irreducible in this certificate family. Any future attack must **tighten the
bound** (shrink `delta`), not coarsen the codes.

---

## Step 0.5 — the one shippable change (commit `61b064b`)

Deleted the dead row-major refine arm from `LagunaLmHeadPrune.swift`:
- the `lagunaLmHeadRowMajorRefineEnabled` flag and its doc comment,
- `lagunaLmHeadRowMajorRefinedExactKernel`
  (`laguna_lmhead_exact_fused_int5_sparse_refine_rowmajor_v1`) and its 33-line
  rationale block,
- the inner ternary arm in `LagunaLmHeadPruner.logits` (collapsed to two arms).

File 54,963 B → **46,797 B (−8,166 B)**. Zero remaining references; release build
clean. The flag was already default OFF and is a twice-measured M5 negative
(receipt `99b71258`: **+24.6 µs/token on M5** despite −63.7 µs on M4). No default
was flipped. Timing-neutral by construction.

Submitted-surface diff vs the assignment commit is **only**
`Sources/MLXFastModel/LagunaLmHeadPrune.swift`, +10/−189.

---

## Preflight and budget

```
senpai/validate-assignment-scope.sh 5daa8389c416928fce41a7cdee41649dbc9569fb \
  Sources/MLXFastModel/LagunaLmHeadPrune.swift \
  Sources/MLXFastModel/LagunaRuntimeModel.swift \
  Sources/MLXFastTransform/Transform.swift
→ assignment scope OK: 3 submitted path(s)

senpai/check-editable-budget.sh 5daa8389c416928fce41a7cdee41649dbc9569fb
→ current=2942689/3000000 headroom=57311 growth=-8166/262144 files=142 (base=142)
```

Only `LagunaLmHeadPrune.swift` was actually modified. Net −8,166 B, i.e. a
net-negative PR as requested.

---

## Correctness

No behavioural change was shipped, so there is no soundness obligation to
discharge — but the evidence collected is:

- 9/9 `--local-iterate` arms in Step 0 report `passed: True` with correctness
  passing, on the post-deletion tree.
- The Step 1 probe run reports
  `teacher-forced greedy tokens: 0 divergences (all match)` over 128 steps.

### Finding worth acting on: the equivalence oracle never reaches the pruner

`LagunaUpstreamEquivalence.compare` constructs `LagunaRuntimeModel(runtimeConfig)`
directly and never calls `prepareFusedRuntimeWeights()`. That function's only
caller is `LagunaRuntimeWeights.swift:637` (`loadLibraryModel`), and it is where
`lmHeadPruner` is built (`LagunaRuntimeModel.swift:11016`, pruner at `:11055`).
So `research/run_upstream_equivalence.sh` exercises stock `lmHead(hidden)` and
covers **neither the lm-head pruner nor the fused-QKV / shared-expert layouts**.
This statically explains the ambiguous `research/frieren_pr35_lm_fault_oracle.sh`
result. The real gates for anything in this file are the 64-step drift tripwire,
hidden teacher-forced / anchor / free-run token identity,
`correctnessLogitDiagnostics` top-8 validation, and a pruner-on vs
`DARKBLOOM_LM_HEAD_PRUNE=0` argmax A/B.

I did not run `run_upstream_equivalence.sh` for the shipped tree because it is a
pure dead-code deletion and, per the above, the oracle does not reach the file.
Say the word if you want it on the record anyway.

---

## Suggested follow-ups (not implemented)

1. **Fix the equivalence oracle gap.** Have `LagunaUpstreamEquivalence` go
   through `loadLibraryModel` / `prepareFusedRuntimeWeights()` so the pruner,
   fused QKV and shared-expert layouts are actually covered. Today a
   representation bug in any of those three passes the oracle silently.
2. **Retire the lm-head as a decode target.** 5a is 6.09 % of the M5 step and
   irreducible in this family; everything downstream of it already costs under
   1 µs. The remaining decode pool is elsewhere.
3. **If anyone revisits this, attack `delta`, not the code width.** The
   certificate radius is currently 1–2× the entire top-of-distribution logit
   spread. A tighter bound — e.g. exploiting that `Σ|x|` is a gross
   over-estimate of the realised inner-product error — is the only direction
   with headroom. Coarser codes are provably a dead end.

---

## Artifacts on this branch

| path | what |
|---|---|
| `research/nezuko-pr284-byte-price.sh` | Step 0 A/B/C interleaved driver |
| `research/artifacts/nezuko-pr284-byte-price.tsv` | Step 0 evidence, 3 reps × 3 arms |
| `research/nezuko-pr284-slack-probe.patch` | Step 1 instrument (out of `Sources/`) |
| `research/nezuko-pr284-slack-histogram.sh` | Step 1 runner (apply → build → run → revert) |
| `research/artifacts/nezuko-pr284-slack-hist.txt` | 129 raw `SLACKHIST` lines |
| `research/nezuko-pr284-slack-analyze.py` | tier pricing + optimistic bracket |

_This result was produced by an AI agent (OpenHands) acting as research student
on behalf of the Senpai maple campaign._
