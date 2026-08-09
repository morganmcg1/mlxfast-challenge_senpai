# Research ideas — 2026-08-09 14:45 UTC (round 99, plateau protocol)

Source: one frontier general-purpose reviewer, `include_context=false`, given a
self-contained brief (pools, prices, geometry, the five hard negatives, byte
constraints, in-flight arms) and three adversarial questions. It read the repo
read-only; no builds, no benchmarks, no edits. Advisor adjudication is in the
`⚖️` blocks — **the reviewer's text is not automatically programme fact.**

---

## 0. The reviewer's two corrections to the advisor's own numbers

Both were checked against the checkout and **both are upheld**.

### 0.1 ⚠️ M4/M5 pool confusion — upheld, corrected in `CURRENT_RESEARCH_STATE.md`

The advisor's 14:20 recalibration table priced decode attention at 636.0 and
229.7 µs/step and called them M5. **Those are the M4 numbers.** §12 of the
state doc records the M5 column as **≈290 (sliding)** and **≈100 (full)**, and
rule 67's own 4.14× M4:M5 decomposition is literally built on the 636.0/290
ratio. Consequences:

- Sliding attention is **33.9 %** of the +98.2 µs/step target, not 15.4 %.
- Full attention alone is 98.2 % of it ⇒ **dead as a standalone arm**.
- The largest M5 decode pools are now **QKV ≈650** and **routed gather-QMV
  ≈600** µs/step (scaled from the M4 ledger's T0b 1276 / T2c 1184).
- Any arm sized off 636 µs/step of M5 sliding attention was over-priced 2.2×.

### 0.2 The 950 µs/step launch pool is a category error — upheld

Not just "in tension" with rule 68: **rule 53's** bit-exact addition-probe
ledger already closed the launch pool to a **+0.3 µs residue**, i.e. launches
overlap execution and the queue does not drain. Marginal-cost × count is
invalid at queue depth > 1 (Little's law). With #527 (−78 dispatches, +0.639 ms
*slower*) and #48 (8× TG collapse, −0.1488 %), that is three independent
refutations. **The dispatch-count axis is closed. No dispatch-fusion arm.**

---

## 1. 🎯 The headline finding: the starvation ceiling is almost exactly the win target

Rule 67's free-combine probe measured decode attention's threadgroup-starvation
ceiling at **+18.36 % sliding / +36.04 % full**, matching the wave model within
1.5 pp. Nobody had ever priced it on the M5 pools:

```
0.1836 × 290  +  0.3604 × 100  =  53.2 + 36.0  =  89.2 µs/step  ≈  1.36 % score
```

Against a +98.2 µs/step p≈84 % target, **decode-attention starvation alone is
worth 91 % of a winning submission.** This is the largest quantified,
mechanism-identified headroom on the board.

And rule 67 recorded precisely why the last attempt failed, which was *not* the
mechanism: splitting the **N (position)** axis forces an online-softmax merge,
which is not a sum, so partials must cross a threadgroup boundary ⇒ +40
dispatches/step ⇒ 93.6 µs of M5 cost that ate the entire gain. **Only that
implementation route is closed.**

### The structural price of every alternative route, stated once

32 sliding TGs already share 8 KV heads 4 ways: unique K+V 62.9 MB/step,
**requested 251.7 MB = 4×**. Doubling TG count along *any* axis except N
doubles the **K** amplification 4× → 8×, i.e. **+31.5 MB/step requested**. This
is unavoidable: split-D recomputes identical scores over all K; split-q
computes different scores over the same K. Both need every K byte per TG.

The roofline says this is SLC-absorbed — measured sliding time is **2.5×** the
DRAM floor, not the **4×** that DRAM-resident re-reads would force. But rule 66
says traffic *structure* can dominate byte count. **"Is +31.5 MB/step of
re-requested K free?" is the pivotal question of the next round**, and it is
answerable on nezuko's zero-receipt A/B probe for zero receipts.

---

## 2. Sliding-attention roofline (reviewer's working, advisor-checked)

Dims from `Sources/MLXFastModel/LagunaConfig.swift:14-49`: window 512, 8 KV
heads, head_dim 128, 64 q-heads, 30 sliding layers.

| quantity | value |
| --- | --- |
| unique K+V bytes / layer | 512 × 8 × 128 × 2 × 2 B = **2.097 MB** (62.9 MB/step) |
| FLOPs / layer | QK 8.39 MF + PV 8.39 MF = **16.8 MFLOP** |
| DRAM floor | 2.097 MB ÷ 546 GB/s = **3.84 µs/layer** = **115 µs/step** |
| compute floor | 16.8 MF ÷ ~14 TFLOPS ≈ 1.2 µs/layer — not binding |
| measured M5 | ≈290 µs/step = 9.7 µs/layer |
| **ratio to DRAM floor** | **2.5×** |

⚖️ **Advisor**: the 546 GB/s and 14 TFLOPS constants are assumed, not measured
on our box, so treat 115 µs/step as order-of-magnitude. The *inference* is
robust regardless: 2.5× < 4× means the 4× K re-read is not paying DRAM, so the
residual gap is occupancy/latency, not bandwidth. That is independently
corroborated by rule 67's starvation measurement. Two unrelated methods agreeing
is why §1 is the headline and not a guess.

---

## 3. Hypotheses, advisor-ranked

### ★ H1 — Offline transform-stage sub-row interleave of routed gate/up NVFP4 codes

**Mechanism.** Verified in-checkout at `LagunaRuntimeModel.swift:7517-7534`:

```
uint gate_row = (logical_row / 32) * 64 + logical_row % 32;
uint up_row   = gate_row + 32;
... gate_weight = expert_weight + gate_row * fused_row_bytes + block/2 + lane*8;
... up_weight   = expert_weight + up_row   * fused_row_bytes + block/2 + lane*8;
```

Gate and up codes for the same logical row live **32 rows apart**, so each lane
issues two 8-B loads from addresses `32 × fused_row_bytes` apart. Repack
`fused_weight` offline in `Sources/MLXFastTransform/` at 8-byte granularity so
each lane's gate and up groups are adjacent ⇒ one contiguous **16 B** load, and
each simdgroup's per-(row, k-block) traffic becomes one 512-B chunk instead of
two 256-B chunks 32 KB apart. Kernel change is pointer arithmetic only. Scales
are *already* adjacent (`up_scale = gate_scale + scale_row_bytes`, `:7521-7523`)
and the expert-0 patch lane (`:7524-7528`) patches scales, not codes.

**Why it should win.** Routed QMV is the largest byte pool (521.4 MB/step, 33 %)
and ≈600 µs/step on M5. Rule 66 showed that a 20.263 MB byte *cut* which
fragmented streams **lost** 69.6 µs — this is its exact converse: bytes
constant, streams merged 4 → 2 per simdgroup, load width doubled. 5–10 % of the
kernel ⇒ 30–60 µs/step ⇒ **0.46–0.92 % score**. Clears the +30 µs/step bar.

**Bytes.** ~2–4 kB across LRM + Transform. Fits 12,870 B today; comfortable
after arm B lands.

**Correctness.** **Bit-exact by construction** — identical per-lane operand
bytes, identical `laguna_nvfp4_qdot_16` inputs, identical summation order. Only
source addresses permute.

⚖️ **Advisor — the one thing the reviewer missed.** `fused_weight` is also read
by the **prefill** routed gather-QMM path (≈54 % of prefill). A layout change
that only updates the decode QMV reader will corrupt prefill. The brief must
require an exhaustive reader census of the bank *before* any transform change,
and must update the generated top8keys twins (`:7600/7748/7771`) and the dim
preconditions (`:7576-7579`). This raises the cost but does not change the
verdict: still #1.

**Falsification.** M4 A/B is valid here (no `_nax` involvement, same kernel
family). Kill if routed-QMV kernel time does not drop ≥2 % in a matched
`--local-iterate` census. **Codegen-tax exposure: LOW** — inner-loop length and
structure untouched, addressing only. Sequence *after* #543 reads out so the
routed family's source-form sensitivity is known first.

---

### ★ H2 — Split-D attention: raise threadgroup count with no cross-TG softmax merge

**Mechanism.** Rule 67 falsified splitting **N**. Split the **D
(value-component)** axis instead: two TGs per current TG, each recomputing the
*full, identical* score/softmax pass over all 512 positions — bit-identical FP
sequence, same position→simdgroup mapping — but each accumulating and storing
only half the 128 V components (`attended[0:64]` / `[64:128]`). The output is a
**concatenation**; no cross-TG FP merge exists, therefore no partial shipping,
therefore **no extra dispatches**. Applies to
`laguna_sliding_fused_attn_ring_v1` (`LRM:1416-1892`) and the full twin. The
ring cache write (`LRM:1500-1511`) is assigned to exactly one D-half. Score ALU
doubles — free per rules 55/63-64, knee ≈96 fma/K-iter/thread. 32 → 64 TGs
= 1.6 TG/core.

**Why it should win.** It is the only identified route into the §1 ceiling.
Capturing half of 89.2 µs/step ⇒ **~0.68 %**; capturing it all ⇒ 1.36 %.
Composes multiplicatively with one-q-head-per-TG (also merge-free) ⇒ 128 TGs
= 3.2 TG/core.

⚖️ **Advisor.** Two amendments. (a) **Test one-q-head-per-TG first.** It reaches
the same 64 TGs, is also merge-free, and costs a grid change plus a head-mapping
change instead of an epilogue rewrite — far fewer bytes and far less codegen-tax
exposure. Split-D is the *second* doubling, not the first. (b) Both routes pay
the +31.5 MB/step K re-request of §1; measure that on the zero-receipt probe
before committing. Given (a), I rank this **#2, and its first rung is cheap**.

**Bytes.** One-q-head rung: a few hundred B. Split-D rung: 4–8 kB — land as a
**new file** under `Sources/MLXFastModel/` (directory-listed editablePath
dissolves the per-file cap). Wants arm B's reclamation first.

**Correctness.** Bit-exact by construction *if* per-component partial-sum order
across simdgroups is preserved. Positions stay within one TG, so the existing
`pair_planes` combine tree per component is unchanged. Needs
upstream-equivalence, the 64-step tripwire, and an M5 near-tie argmax check.

**Falsification.** M5 `--local-iterate` A/B on the combined attention pool; kill
if it does not drop ≥5 %. **M4 sign is not dispositive** — TG-geometry sign
flips across core counts. **Codegen-tax exposure: MEDIUM** (attention family,
where the +5–7 % tax was measured) — but the inner-loop *body* is textually
identical; only head/component mapping and the epilogue partition change.
Requires an unchanged-base same-session control. Sequence after arm A lands.

---

### ★ H3 — Post-rebase flag-default and dormant-variant audit (zero bytes)

**Mechanism.** The frontier rebase silently reset at least two tuned defaults
(4-deep ring depth, `DARKBLOOM_ROUTER_WEIGHT_PREFETCH`; arm A #539 is restoring
them). Diff every `ProcessInfo.processInfo.environment[` default in the editable
surface, pre-rebase lineage tip vs current base — a read-only `git diff` of the
flag-definition lines. Separately inventory built-but-dormant variants: QKV
`staged` / `pf{depth}` / `_idx_v1` (`LRM:5280-5328`, gated `:5060/:5281/:5304`),
routed `top8keys_r1_bf16_v2` (`:7771`, selected `:7900`), the fused-sliding
off-switch. Then one M5 session sweeping each never-receipted configuration.

**Why it should win.** Prior is high and empirical: **2 of 2** known
lineage-vs-frontier deltas were genuine losses, and our 4-deep lineage computed
~0.57 % faster on common-baseline merit. Each recovered default is pure upside
at **zero code cost**. This has the lowest cost of anything on the board and it
sequences H5 for free.

**Bytes.** Zero for the audit; ≤1 line per promoted flip.

**Correctness.** None for archaeology. Each variant already exists behind a flag
and was presumably equivalence-tested; re-run upstream-equivalence per flip.

**Falsification.** If the flag-default diff is empty beyond arm A's two AND no
swept configuration beats default by >0.15 % in matched local timing, close
permanently. **Codegen-tax exposure: none** — selecting between already-compiled
variants.

⚖️ **Advisor**: this is the best cost-adjusted item on the board and should go
to the first student who frees up, ahead of H1 if that student's slot is short.

---

### H4 — Codegen-tax autopsy via offline assembly diff (desk, zero score)

Compile the tax-inducing and clean sliding-kernel variants offline with
`xcrun metal -S` / `metal-objdump`, JIT flags mirrored (fast-math **off**, per
`Vendor/mlx-swift/.../device.cpp:631`), and diff instruction count, register
pressure/spills, and loop structure across ≥3 known taxed/untaxed pairs.
Correlate with #543's routed-family result: if the tax is register-spill driven,
it predicts *which* families tolerate restructuring (64-thread QMV TGs vs
1024-thread attention TGs have very different register budgets).

**Direct expected score: 0.** Value is that it converts a family-wide
prohibition into a *predictive* rule, re-opening the §1 ceiling to structural
work with known-safe form. Zero bytes, zero correctness risk. Kill if no stable
correlate distinguishes taxed from untaxed pairs.

⚖️ **Advisor**: qualifies under the arm-sizing rule's "retires a rule" carve-out.
Excellent *rider* on a student already inside the attention family (frieren,
after #539). Not a standalone slot.

---

### H5 — QKV LUT-indexed metadata variant (`_idx_v1`) M5 receipt

A fully-built QKV variant reads `metadata_indices` + `metadata_lut` instead of
full `weight_scales`/`weight_biases` (`LRM:5302-5328`), gated behind
`lagunaNormAffineQKVStaged` / `lagunaNormAffineQKVPrefetchDepth` (`:5060`,
`:5281`). QKV is ≈650 µs/step M5 and 411.3 MB/step. i8g32 metadata is ~12.5 % of
the bank (~46 MB/step); LUT-indexing cuts most of it → 20–34 MB/step. The
indices stream *replaces* the scales stream 1-for-1, so rule 66's fragmentation
penalty should not apply. Honest range **0.15–0.5 %**.

Zero bytes if the flag works as built. **Subsumed by H3's sweep** — not its own
slot. ⚖️ Check research notes first for a pre-existing negative: it may be
dormant *because* it lost.

**No conflict with #548 (corrected 2026-08-09).** An earlier draft of this
document claimed H5 depended on
`Sources/MLXFastTransform/AffineMetadataCoding.swift` and therefore collided
with the byte-reclamation deletion. That was wrong and is retracted. The
indices and LUT are built **in-process** by
`lagunaIndexedAffineMetadata(scales:biases:)` at `LRM:2829-2870`, gated by
`DARKBLOOM_AFFINE_METADATA_INDEXED` (`:2825`); no checkpoint sidecar is read.
The offline coder is reachable only from the `.gemma4` arm of
`Transform.swift:238-253`, whose `.laguna` arm (`:256-268`) emits empty reports
by contract. H5 and the 32,005 B deletion are independent.

---

### H6 — Prefill non-GEMM pool census

Prefill (~96 ms, 0.3794 %/ms all-in) has no in-flight arm. The reviewer verified
that `_nax` GEMM coverage is **already complete** — `use_nax` is unconditional
for BF16 on M5 (`Vendor/mlx-swift/.../matmul.cpp:957-1026`) — so the
"`steel_gemm_bf16` 12.30 ms pool" is an M4 census artifact and **must not be
chased on M5**. Falsifiable claim: ≥3 ms of prefill sits in non-GEMM pools
(QK-norm+RoPE prefill twins, MoE argsort/gather staging, mask construction,
cache writes), addressable by extending the proven decode-side fusions'
prefill twins. 3 ms × 0.3794 = **1.14 % score**.

Census costs zero bytes; fusion work 1–3 kB. One instrumented M4 prefill census
(pool *shares* of non-`_nax` kernels are family-valid) + one M5 confirmation. If
non-GEMM pools total <3 ms, close the prefill axis entirely — itself
decision-valuable. ⚖️ Good arm, uncontested axis, but decode carries 75 % of the
weight and H1/H2/H3 all target decode. Queue behind them.

---

## 4. Riders (each <0.3 % best case — attach, never a slot)

- Memoize the full-attention `params` MLXArray (`LRM:2359-2361`, 10 allocs/step).
- Delete the two provably-`.none` mask constructions (`LRM:8992-8993`).
- Sliding epilogue store widening (final store is `lane == 0` only, 32/1024
  threads); barriers cost 0.0293 µs (rule 41).
- Phase-1 redundant K-norm recompute (4× per kv_head, `LRM:1452-1498`) — 128-dim
  RMSNorm+RoPE; ALU is free on this machine. Explicitly **not worth touching**.

## 5. Developed then killed — do not re-derive

- **"Store roped K in the KV cache"** — already the implementation; phase 1
  writes post-RMSNorm+RoPE K to the ring (`LRM:1500-1508`). Dead on inspection.
- **Route prefill GEMMs onto `_nax`** — already unconditional for BF16 on M5
  (`matmul.cpp:957-960`). Dead.
- **Pre-dequantized BF16 expert bank for prefill MoE** (1.6 GB resident,
  input-independent ⇒ legal) — changes accumulation order vs the quantized
  gather path ⇒ logits differ ⇒ with 6.77 % exact BF16 ties observed in-model,
  greedy flips are likely. **Disqualified on correctness.**
- **K/V plane interleave in the sliding ring** — only 2 streams/TG, 64
  machine-wide; stream count is not this kernel's binding constraint (occupancy
  is), and prefill writers share the layout. Dead.
- **Shared+routed expert single-dispatch merge** — shared is already shadowed
  (E = 0.31); routed runs 25.6 TG/core, no starvation to fill. Dead.
- **Fast-math / compile-option flips** — changes FP semantics ⇒ token drift;
  `optimizationLevel` is already default-max. Only the H4 *audit* survives.

---

## 6. Advisor's assignment order for round 100

> **SUPERSEDED 2026-08-09 by three desk investigations. Read this block before
> the table below.** See `research/CURRENT_RESEARCH_STATE.md` §§ ROUND-100 PREP
> A–I for the working.
>
> - **H1 — DEAD.** There is no offline surface. The fused routed gate/up bank is
>   built in-process (`LRM:10587-10589` in `prepareFusedRoutedGateUp()`
>   `LRM:10523-10627`, driven from `LagunaRuntimeWeights.swift:643`); the
>   transform never emits fused tensors (`LagunaCheckpointValidation.swift:94-96,
>   163-170, 388-393`). Row contiguity is load-bearing across 13 lockstep sites
>   including vendor Metal, and a decode-only bank costs +11.78 GB resident
>   (21.6 → 33.4 GB, past the ~36 GiB host floor). Doubly dead under **rule 70**:
>   the pool is DRAM-saturated anyway.
> - **H3 — FALSIFIED, complete, earns no slot.** 133 env names at `e510bb3d` vs
>   132 at `4b631591`; all 132 shared names byte-identical; C++ getenv defaults
>   unchanged. Exactly one flag went missing
>   (`DARKBLOOM_ROUTER_WEIGHT_PREFETCH`, already relayed to #539) and none is new.
> - **H2 — flagship, but PROBE-FIRST.** My "+31.5 MB/step" was the *unique*
>   figure; Route A actually re-requests **+251.7 MB/step** (8× amplification)
>   and Route B **+125.8 MB/step**. The +18.36 %/+36.04 % free-combine ceiling was
>   measured on N-split geometry and **does not bound these routes**. Rule 60's
>   M4 wave model implies φ = t(64)/t(32) ≈ 1.8–1.9, and clearing +68.7 µs/step
>   needs φ(1−α) ≤ 0.763 — impossible at that φ. Assign the zero-receipt
>   **E1/E2/E3 discriminator ladder** first; Route-A implementation is deferred
>   behind its verdict.
> - **New desk task before any QKV arm:** resolve the QKV byte-floor
>   contradiction (420 MB/step of codes ⇒ a 769 µs floor at 546 GB/s, larger than
>   the ≈650 µs measured pool). One of the two numbers is wrong.

| # | arm | student slot | gate |
| --- | --- | --- | --- |
| 1 | ~~**H3** flag-default + dormant-variant audit~~ | — | **done, falsified** |
| 2 | ~~**H1** routed gate/up offline interleave~~ | — | **dead: no offline surface, +11.78 GB, rule 70** |
| 3 | **H2 probes E1/E2/E3** (grid-only ladder, uniqueness fold, Route-A text at K=32) | fern, now | rule-71 instrument validation in the same arm |
| 4 | **H2 Route A** one-q-head-per-TG | frieren, after #539 | gated on E1 absorption *and* α ≥ ~10 % from E3 |
| 5 | H6 prefill non-GEMM census | tanjiro, after #541 | — |
| — | H4 codegen autopsy | rider on frieren | — |
| — | H5 `_idx_v1` | folded into H3 | independent of #548 — see the correction in H5 |

Superseded by this document: the queued "arm C step-boundary/CPU tier" keeps its
place only if tanjiro's #541 Part 2 shows the 249 µs/step gap is (a) real on M5
and (b) ≥100 µs/step. The +30 µs/step arm-sizing floor applies to all of the
above.
