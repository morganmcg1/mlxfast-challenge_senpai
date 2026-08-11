# R117-C Stage 0 — the attention scale-plane mechanism is already shipped; `N-ATTN-BYTE-FLOOR`

*maple-nezuko · assignment `maple-r117-c-attn-scale-plane-byte-floor` rev `r117-c-rev1` ·
base `fe8536ff` · PR #707 · posted before the 04:00Z Stage-0 gate*

## TL;DR for the advisor

**Do not spend a slot on this assignment as written.** The mechanism it asks me to
transplant — edward's nibble-delta scale plane — is already implemented, already
default-ON, and already dispatching on all 40 layers of *both* assigned kernel
families. It is visible in the very kernel names the assignment quotes: the `_lm1_pw1`
suffixes in `decode_nvfp4_qkv_h64_r1_v1_lm1_pw1_se1_sd1` and
`oproj_act_h64_v1_lm1_pw1_sc1_se1` **are** lane-major + pairwise. The 1342.1 µs/step and
1114.7 µs/step figures in the atlas are therefore *post*-optimization measurements.

Quantitatively: the transplant the advisor priced at **+0.747 %** is worth **+2.367 %**,
and **all of it is already banked**. What is left of the entire scale plane is
**96.6 µs/step = 0.811 % of score**, and that is the ceiling for the plane
*ceasing to exist*. The best physically-motivated residual arm is worth
**47.3 µs/step = 0.397 %** — below the rule 105.12 slot floor of 68.7 µs/step and below
the §0P.17 bar of +0.406 % — and is also structurally impossible for reasons given in
§0d. **The attention projection family is 96.9 % irreducible payload.**

Two consequences beyond my own assignment:

- **§0b-bis.** The r94 decode residue ledger — the source of the campaign's
  "bytes-bound = 6090.4 µs/step = 76.2 % of busy, irreducible" verdict — back-solves
  **exactly** onto the *stock* scale plane for all four of my kernels. It overcounts
  attention scale traffic 3.9×, publishes `qkv_h64` at **272.1 GB/s** (above this
  machine's measured 262.96 GB/s best), and used those impossible rows to argue the
  260.2 GB/s copy benchmark was a *floor* rather than a ceiling. The roofline the campaign
  measures headroom against is ~5 % too high, by a circular argument.
- **§0e.** With the bytes corrected, `oproj_h48` sits at **83.4 %** of peak against
  `qkv_h64`'s 94.3 % — a real efficiency gap the wrong byte model hid. Closing it to the
  family's own best is worth **76.5 µs/step = 0.643 %**, which clears both the floor and
  the bar. That is my proposed redirect, priced and bit-exactness-argued in §0e.

---

## 0a — Reachability (rule 39)

**VERDICT: reachable, unconditionally, and this was already adjudicated.**

Rule 69 grep of `research/RESEARCH_ARCHIVE_through-round-91.md` returned §(i)
"L3 reachability — rule 39 SATISFIED (advisor audit, round 89c)" at lines 194–252.
That audit already walks the exact selection chain and concludes:

> **VERDICT: YES.** On the default configuration the decode QKV projection dispatches
> the lane-major kernel on all 40 layers. Runtime name is
> `laguna_decode_nvfp4_qkv_h64_r1_v1_lm1_pw1_se1_sd1` (sliding) / `…_h48_…` (full).

I re-verified every link against the current tree (`fe8536ff` semantics unchanged):

| # | site | fact |
|---|---|---|
| 1 | `LagunaRuntimeModel.swift:5717–5718` | fused-QKV branch is decode-only (`B == 1, L == 1`) |
| 2 | `LRM:2869–2935` | every layer quantized `groupSize: 16, bits: 4, mode: .nvfp4` ⇒ the INT8 fused-norm arm can never fire ⇒ `lagunaDecodeNVFP4QKVR1(...)` always runs |
| 3 | `LRM:4628–4629`, guard `:4828` | `DARKBLOOM_DECODE_NVFP4_QKV_R1 != "0"` ⇒ default true |
| 4 | `LagunaRuntimeWeights.swift:673–674, 677, 680` | `…_ATTN_SCALE_NARROW`, `…_NARROW_QKV`, `…_NARROW_OPROJ` all `!= "0"` ⇒ default true |
| 5 | `LagunaRuntimeWeights.swift:886` (`lagunaLaneMajorNVFP4ScaleBank`), guard `:889`, shape guard `:891` | lane-major default true; `scales.dim(1) % 64 == 0` → 2048/16 = 128 ✔ |
| 6 | `LagunaRuntimeWeights.swift:702–703, 718–719, 721–722` | `DARKBLOOM_ATTN_SCALE_PAIRWISE_QKV` and `…_PAIRWISE_OPROJ`, **both `!= "0"` ⇒ both default ON** |
| 7 | dispatch `LRM:4842–4847` (QKV), `LRM:4609–4629` (o_proj) | lane-major bank is the **primary** path; the narrow block bank is built *only if* lane-major returned nil (`LRM:5582–5585`) |

**The kernel name is the proof.** `lagunaActivatedOProjLaneMajorKernels` (`LRM:4565–4580`)
builds its `metalKernel` name as

```swift
name: "laguna_oproj_act_h\(heads)_v1_lm1"
    + (lagunaAttnScalePairwiseOProjEnabled ? "_pw1" : "")
    + (lagunaNvfp4QmvSignCarryEnabled ? "_sc1" : "")
    + (lagunaNvfp4QmvSeedElisionEnabled ? "_se1" : "")
```

which emits **exactly** the atlas string `oproj_act_h64_v1_lm1_pw1_sc1_se1`. The `_lm1`
is only reachable from the lane-major dispatch arm and `_pw1` only when pairwise is on.
The same holds for `decode_nvfp4_qkv_h64_r1_v1_lm1_pw1_se1_sd1` (`LRM:4806–4809`). The
assignment's own kernel names already state that the mechanism is live.

There is no NAX gate on this path: these are custom Laguna `metalKernel` dispatches, and
decode is M=1/B=8 so `is_nax_available()` is never evaluated. The only non-static
condition is the init-time byte-exactness certificate
`lagunaLaneMajorScaleBankReproducesScales` (`LagunaRuntimeWeights.swift:935, 948`),
which *discards* a bank that does not reproduce the stock plane byte-for-byte — so no
dispatch can ever consume an approximate scale.

**Rule 69 statement of what I found:** the archive contains not only the reachability
audit above but §4.10b (line 3324, "Decode GEMV geometry census") which states in terms:

> QKV lane-major uses a pairwise 2-byte nibble read (32 B/row) where the stock plane
> would cost 128 B/row — **a 4× reduction already banked**.

and §4.10b again, which is the origin of the redirect in §0e:

> o_proj is the geometric outlier at 4 rows/simdgroup and 512 B/thread, 8–16× every
> other kernel. Whether that is good or bad is **untested**; it is the natural control
> for any rows-per-simdgroup arm.

---

## 0b — Byte census, reconciled against the atlas

Model: per output row a kernel streams `axis/2` payload bytes (NVFP4 nibbles) plus the
scale plane. The shipped plane is pairwise lane-major: `groups/4` nibble bytes
(`LagunaLaneMajorScaleBank.nibbleBytes`, `LagunaRuntimeWeights.swift:878`) plus **one**
uint8 row base. Activations are a 16 KB working set and are SLC-resident, so they do not
appear in DRAM traffic — which is exactly why the model closes.

| kernel | rows | axis | groups | payload B/row | stock plane | lane-major | **shipped `pw`** | B/row | MB/call | µs/call | **GB/s (model)** | atlas GB/s | % of 256.7 peak | scale % of bytes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `qkv_h64` (30×) | 10240 | 2048 | 128 | 1024 | 128 | 65 | **33** | 1057 | 10.824 | 44.74 | **241.9** | 242.1 | 94.3 % | 3.12 % |
| `oproj_h64` (30×) | 2048 | 8192 | 512 | 4096 | 512 | 257 | **129** | 4225 | 8.653 | 37.16 | **232.9** | 233.4 | 90.7 % | 3.05 % |
| `qkv_h48` (10×) | 8192 | 2048 | 128 | 1024 | 128 | 65 | **33** | 1057 | 8.659 | 36.35 | **238.2** | — | 92.8 % | 3.12 % |
| `oproj_h48` (10×) | 2048 | 6144 | 384 | 3072 | 384 | 193 | **97** | 3169 | 6.490 | 30.30 | **214.2** | — | 83.4 % | 3.06 % |

**Family total: 3123.3 µs/step, 735.8 MB/step, 235.6 GB/s = 91.8 % of the measured
asymptotic 256.7 GB/s DRAM peak.**

The model reproduces the atlas GB/s to **0.08 %** (QKV) and **0.21 %** (o_proj) *with the
pairwise plane included*. Had the stock plane still been live, the model would need
1152 B/row for QKV and would over-predict by 9 %. This is an independent confirmation,
from edward's own census, that `_pw1` is active in the measurement.

---

## 0b-bis — A standing ledger the board is using is built on the *stock* byte model

`research/maple-frieren-r94-decode-residue-ledger.md:176–182` publishes per-kernel
"achieved GB/s, % of 273" for exactly this family. It is the artifact behind the campaign's
biggest single claim — "bytes-bound (90–100 % of peak) = **6090.4 µs/step = 76.2 % of
busy**, irreducible without removing bytes" — and 3,123 µs/step of that pool is the family
I was assigned. Its timings are the same machine and the same scale as edward's atlas
(`qkv_h48` 362.8 µs/step over 10 calls; `oproj_h48` 301.8/10, then nat-deflated ~3.5 %).
Its **byte** column is where it breaks:

| kernel | ledger MB/step | back-solved B/row | shipped B/row (this census) | overcount |
|---|---|---|---|---|
| `decode_nvfp4_qkv_h64` | 353.9 | **1152** = 1024 payload + **stock 128** | 1057 = 1024 + pw 33 | +9.0 % |
| `decode_nvfp4_qkv_h48` | 94.4 | **1152** | 1057 | +9.0 % |
| `oproj_act_h64` | 283.1 | **4608** = 4096 + **stock 512** | 4225 = 4096 + pw 129 | +9.1 % |
| `oproj_act_h48` | 70.8 | **3456** = 3072 + **stock 384** | 3169 = 3072 + pw 97 | +9.1 % |

Every one of the four back-solves **exactly** onto `payload + stock plane`, to the byte
(10240 × 1152 × 30 = 353,894,400 B, etc.). The ledger was written against the pre-`pw1`
byte model, so it overcounts attention scale traffic by 3.9× and inflates every achieved
rate in the family by ~9 %. Correcting *only the bytes*, leaving the ledger's own timing
convention untouched:

| kernel | ledger GB/s | corrected GB/s | ledger % of 273 | corrected % of 260.2 |
|---|---|---|---|---|
| `decode_nvfp4_qkv_h64` | 272.1 | **249.7** | 100 % | 96 % |
| `decode_nvfp4_qkv_h48` | 269.9 | **247.6** | 99 % | 95 % |
| `oproj_act_h64` | 262.6 | **240.8** | 96 % | 93 % |
| `oproj_act_h48` | 245.2 | **224.8** | 90 % | **86 %** |

Two things follow, and the second one is the reason this belongs in a Stage 0 report rather
than a footnote.

**1. It is a third independent confirmation that the pairwise plane is live.** As published,
`qkv_h64` sits at **272.1 GB/s**, which this machine cannot do:
`research/maple-tanjiro-r107g-decode-family-regime-census.md:158` measures the asymptotic
streaming peak at **256.7–257.4 GB/s** and the best streaming run ever recorded here at
**262.96 GB/s** (98.7 % of a 266.3 GB/s ceiling). The only byte model that puts this family
*under* the machine's own measured ceiling is the shipped `_pw1` one. The ledger's
`lmhead_int5` row at **112 % of 273** is the same tell, and it is already flagged there.

**2. The ledger used the overcount to raise its own roofline.** Its text (line ~162) reads:
"an earlier local copy-microbenchmark figure of 260.2 GB/s turns out to be a *floor* on
achievable rate, **because several rows beat it**." The rows that beat it are precisely the
overcounted ones. Remove the overcount and no legitimate row exceeds 260.2 (`qkv_h64`
249.7, `routed_shared_down` 256.4, `routed_swiglu` 254.5), so 260.2 goes back to being a
**ceiling**, in agreement with tanjiro's independent 256.7–262.96. The roofline this
campaign has been measuring headroom against is ~5 % too high, and it was raised by a
circular argument.

Net effect on my assignment: three of the four kernels are genuinely near the floor — that
is exactly what `N-ATTN-BYTE-FLOOR` asserts and why the assigned mechanism is dead — but
`oproj_h48` is ~10 points of efficiency below its `qkv_h64` sibling in *both* timing
conventions, and that gap was invisible while the bytes were wrong. §0e converts it into
the redirect arm.

---

## 0c — The headline: the assigned mechanism is live, and the sizing double-counts it

`lagunaLaneMajorNVFP4ScaleBank` (`LagunaRuntimeWeights.swift:886`) is *precisely* the
"nibble-delta scale plane" the assignment describes: one uint8 base per row, a 4-bit
index per group, lane-major so the codes a lane reads are adjacent, rows outside the
16-code span escaped with base `0xFF` and read from the stock plane.

It also already has a second compression stage the assignment did not anticipate:

```swift
// Lane `2j` and `2j + 1` hold the two halves of one quantizer 32-element
// chunk, so the pairwise arm keeps the even lane and drops the odd one for
// every row where the two agree. A row that disagrees escapes.
```

| plane form | QKV B/row | o_proj h64 B/row | status |
|---|---|---|---|
| stock uint8 plane | 128 | 512 | superseded |
| lane-major 4-bit | 65 | 257 | superseded |
| **lane-major + pairwise (SHIPPED)** | **33** | **129** | live on all 40 layers, both sites |

**Already banked: 66.38 MB/step = 281.8 µs/step = +2.367 % of score.** The advisor
priced the transplant at +0.747 %; the true value of the mechanism is ~3.2× that, and it
has been in the tree since at least round 89. Re-landing it would measure **zero**.

This also matters for the board: any campaign arithmetic that adds +0.747 % for R117-C
is adding score that is already inside the 8,567 µs decode busy baseline.

---

## 0d — `N-ATTN-BYTE-FLOOR`

> **`N-ATTN-BYTE-FLOOR`.** The decode attention projection family (QKV + o_proj, h64 and
> h48; 3,123.3 µs/step = 36.5 % of decode busy) streams 735.8 MB/step of which **713.0 MB
> (96.91 %) is irreducible NVFP4 payload** and only **22.75 MB (3.09 %) is scale plane**.
> The plane is already at its pairwise lane-major minimum. Therefore the *entire*
> remaining scale-plane prize, taken at the physically impossible limit of the plane
> ceasing to exist, is **96.6 µs/step = 0.811 % of score**; every realizable arm is a
> fraction of that and none clears the rule 105.12 slot floor of 68.7 µs/step.

Residual arms, priced against the **shipped** pairwise baseline (not against stock):

| arm | MB/step saved | µs/step | % score | vs 68.7 µs floor | verdict |
|---|---|---|---|---|---|
| 3-bit index (needs full-row span ≤ 7) | 5.57 | 23.6 | 0.199 % | **below** | dead on size |
| quad-wise 4-bit (4 lanes share one nibble) | 11.14 | 47.3 | 0.397 % | **below** | dead on size *and* structure |
| 2-bit index (needs full-row span ≤ 3) | 11.14 | 47.3 | 0.397 % | **below** | dead on size *and* data |
| plane ceases to exist (unreachable bound) | 22.75 | 96.6 | 0.811 % | clears | not an arm |

Three independent reasons the residual is closed, not merely small:

1. **Structure.** Pairwise is not a compression heuristic — it is an *identity*. Lanes
   `2j` and `2j+1` are the two halves of one 32-element quantizer chunk, so they agree by
   construction. Lanes `4j…4j+3` span **two different** chunks, so quad-wise has no
   identity to exploit; it would be pure data coincidence. The one free structural
   halving has already been taken.
2. **Data.** `research/frieren-pr35-scale-census.md` (real shipped banks,
   `DARKBLOOM_SCALE_CENSUS=1`, 3 runs) measures per-32-group-block spans: fraction with
   span ≤ 3 is 0.3983 / 0.3913 / 0.1675 / **0.0833** for `attn.q/k/v/o`. A *row* has 4–16
   blocks, so full-row span ≤ 3 is far rarer still. A 2-bit plane would escape most rows.
3. **Escapes are asymmetric.** An escaped row reads the *stock* plane, so it costs
   +95 B/row (QKV) or +383 B/row (o_proj) against a saving of 8–16 B/row. Break-even
   escape rate is **7.8 % (QKV) / 7.7 % (o_proj)** — the 3-bit and 2-bit arms are
   negative at escape rates the census says are certain.

**Envelope check.** Halving the group count (NVFP4 at group 32) would halve the plane
and is worth ≈0.77 %, but `TASK.md:78–94` permits re-quantizing Q/K/V/O and `g_proj`
**only to group-32 affine INT8**, which is 1.125 B/param against the current
0.516 B/param — it *adds* ~118 % to family bytes. The envelope is closed.

---

## 0e — Redirect that does clear the bar: o_proj is 9 % off the family's own efficiency

Bytes in this family are pinned. **GB/s is not.** From the §0b table:

| kernel | GB/s | % of 256.7 peak | rows/simdgroup | TGs | B/thread |
|---|---|---|---|---|---|
| `qkv_h64` | 241.9 | 94.3 % | 1 | 5120 | 32 |
| `qkv_h48` | 238.2 | 92.8 % | 1 | 4096 | 32 |
| `oproj_h64` | 232.9 | 90.7 % | **4** | **256** | **512** |
| `oproj_h48` | 214.2 | **83.4 %** | **4** | **256** | **384** |

o_proj is the one geometric outlier — `results_per_simdgroup = 4`,
`num_simdgroups = 2`, `grid: ((outVec/8)*64, 1, 1)` ⇒ **256 threadgroups**
(`LRM:4356–4357, 4367, 4625`) against QKV's `out_row = tile * num_simdgroups + simd_gid`
⇒ 5120. The archive flagged this exact geometry as **untested** and as "the natural
control for any rows-per-simdgroup arm" (§4.10b).

Price, holding bytes fixed:

| target | µs/step | % score | vs 68.7 µs floor / 0.406 % bar |
|---|---|---|---|
| o_proj reaches `qkv_h64`'s 241.9 GB/s | **76.5** | **0.643 %** | **clears both** |
| o_proj reaches 256.7 GB/s peak | 153.6 | 1.291 % | clears both |

Bit-exactness argument: `results_per_simdgroup` only decides *which* simdgroup owns
*which* output row. Each row's accumulation remains 32 lanes × the same `values_per_thread
= 16` serial FP32 chain over the same K-block order, followed by the same `simd_sum`.
The summation tree is untouched ⇒ bit-exact by construction, unlike a `uint4` load-width
widening (which the archive correctly refuses at §4.10b because it repartitions the
per-lane accumulation).

Two prior results must be priced into the design, not ignored:

- **#298/#308** found an *interior* argmax for QKV geometry at ≈640 TGs (S = 8), i.e.
  coarser than shipped. **#309** found a cliff going further (`G128 − G640 = +174.9 ±
  11.0 µs/step`). o_proj sits at 256 TGs, *past* the 640 optimum in the coarse direction,
  which is the side #309 showed is expensive. That is a directional prediction, and it is
  falsifiable: a `results_per_simdgroup ∈ {1, 2, 4, 8}` ladder has an interior argmax or
  it does not.
- **Rule 33**: MLX caches compiled pipelines by function name, so every rung needs its
  own name suffix (`_rps1`, `_rps2`, …) or the sweep silently measures one geometry four
  times. The o_proj name is already built from a literal (`laguna_oproj_act_h\(heads)_v1…`)
  so the suffix must be threaded through.

I have **not** started this arm; it is offered for the advisor's Stage-1 call. If the
answer is "stay on the assignment", the honest terminal result for R117-C is
`N-ATTN-BYTE-FLOOR` above, delivered as a full-value negative.

---

## Boundaries respected

- No edits to `lagunaLaneMajorNVFP4ScaleBank` / `lagunaHalvedGroup32ScalePlane` or to
  K1/K4 — edward owns those (#704).
- Prefill view untouched: `lagunaPackedPrefillScaleView` aliases the M5 `_nax` prefill
  primitive and must stay bit-identical. Nothing in §0e touches it.

## Hand-off to edward (#704) — his 4-bit routed arm has a pre-existing closure

The archive (line 6455) already closes the routed variant of the same mechanism, and it
is not by a bar but by arithmetic:

> **Routed scale-plane recode is closed by a repricing, not by entropy.** Scale entropies
> are 2.4723/2.6002/2.6112 with 42/50/57 distinct codes ⇒ 6-bit, not 4-bit; per-slab
> maxima 35/38/41 with 705/2,247/1,301 slabs above 16 codes ⇒ **a uniform 4-bit recode is
> impossible**. Critically, **PR #72 already halves the routed scale plane at load**
> (`scale_row_bytes` 32→16), so runtime routed scale traffic is **30.67 MB/step, not
> 61.34**. Uniform 6-bit is therefore worth **+0.167 %** and mixed 4/6-bit **+0.310 %**.

`research/frieren-pr35-scale-census.md` corroborates: `routed.gate_up` per-block span
maxima reach **39**, outside a 4-bit (≤15) envelope, and 58 distinct codes globally.
Edward should reconcile his sizing against these two documents before building.

One more thing edward should check, from §0b-bis: the r94 residue ledger's attention rows
back-solve onto the *stock* scale plane. **PR #72 halved the routed plane at load too**, so
its `routed_nvfp4_swiglu_qmv` (368.1 MB/step, "93 % of peak") and
`routed_shared_down_residual` (207.0, "94 %") rows are worth re-deriving before they are
used to declare the routed family bytes-bound and closed. I did not re-derive them myself
because the routed geometry is his region, not mine.
