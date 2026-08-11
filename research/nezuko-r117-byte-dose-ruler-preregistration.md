# R117-C — byte-dose ruler on the attention scale planes: PRE-REGISTRATION

*maple-nezuko · written **before** any measurement exists · assignment
`maple-r117-c-attn-scale-plane-byte-floor` rev `r117-c-rev1` · branch
`maple-nezuko/r117-attn-scale-plane-byte-floor` at `885431b9`*

## Why this ruler, and why it needs no new code

The advisor's revised Stage 0 (`#707` comment, 02:42Z) asks for a three-dose byte ruler on
`oproj_act_h64` — 0.5×, 1.0×, 2.0× of the kernel's scale-plane traffic — with each dose a
**genuinely re-sized allocation**, warns that a stride trick over the existing plane would
touch the same cache lines and manufacture a spurious τ≈0, and accepts bit-inexact output
because "this is a ruler, not a candidate".

My Stage 0 census (`research/nezuko-r117-stage0-attn-byte-floor.md`) found that the
assigned mechanism is **already shipped** — the `_lm1_pw1` in the kernel names *is* the
lane-major nibble-delta plane plus a pairwise halving. That kills the assignment's arm, but
it hands me a much better ruler than the synthetic one, because the tree already contains
**four independent, per-site, default-ON kill switches** that each swap the o_proj and QKV
scale planes for a genuinely larger, genuinely differently-allocated one:

| gate | effect | plane form |
|---|---|---|
| `DARKBLOOM_ATTN_SCALE_PAIRWISE_OPROJ=0` | o_proj keeps lane-major, drops the pairwise halving | `groups/2 + 1` B/row |
| `DARKBLOOM_ATTN_SCALE_NARROW_OPROJ=0` | o_proj falls all the way back to the stock plane | `groups` B/row |
| `DARKBLOOM_ATTN_SCALE_PAIRWISE_QKV=0` | same, QKV | `groups/2 + 1` B/row |
| `DARKBLOOM_ATTN_SCALE_NARROW_QKV=0` | same, QKV | `groups` B/row |

This ruler is strictly better than the synthetic one on five axes:

1. **It is the real address map.** Not a ballast buffer, not a stride — a different bank,
   built by a different encoder, read by a differently-named kernel. The cache-line trap
   the advisor warned about cannot occur, because at every rung the plane is a separate
   allocation of a different size, and every rung is a configuration that has actually
   shipped.
2. **Every rung is bit-exact.** `lagunaLaneMajorScaleBankReproducesScales` and
   `lagunaNarrowScaleBankReproducesScales` are init-time byte-exactness certificates, and
   the stock plane is the ground truth all of them reproduce. So `golden_hash` must be
   **identical at every rung**, which converts the usual "did the output change?" worry
   into a live per-run control. A bit-inexact ruler cannot offer that.
3. **It measures the REMOVE direction.** The advisor's synthetic ruler adds bytes. Here the
   *shipped default is the reduced state* and each arm **restores** bytes that were
   previously removed. τ measured this way is the elasticity of the mechanism that was
   actually banked, which is exactly the quantity the campaign wants to re-price.
4. **Five rungs, 6.8× dynamic range**, 9.83 → 66.38 MB/step, versus cedar's single 2×
   point. Linearity is therefore directly testable, and non-linearity is a first-class
   result.
5. **Zero implementation risk and zero build time**, so it starts the moment the GPU frees.

Cost: 5 arms × 7 blocks = 35 runs ≈ 116 min.

## The arms

Reference arm first, per the harness contract. Labels are what will appear in the TSV.

| label | gates | site(s) restored |
|---|---|---|
| `C` | *(none — shipped default)* | reference |
| `OP` | `DARKBLOOM_ATTN_SCALE_PAIRWISE_OPROJ=0` | o_proj, pairwise only |
| `ON` | `DARKBLOOM_ATTN_SCALE_NARROW_OPROJ=0` | o_proj, all the way to stock |
| `QN` | `DARKBLOOM_ATTN_SCALE_NARROW_QKV=0` | QKV, all the way to stock |
| `AN` | `DARKBLOOM_ATTN_SCALE_NARROW_QKV=0,DARKBLOOM_ATTN_SCALE_NARROW_OPROJ=0` | both, to stock |

**Why five arms and not six.** The natural sixth rung, `QP`
(`DARKBLOOM_ATTN_SCALE_PAIRWISE_QKV=0`, +12.452 MB), sits almost on top of `OP`
(+9.830 MB). Two rungs 27 % apart add essentially nothing to the leverage of a slope fit,
and the fixed budget is runs, not arms. Spending those six runs on a seventh *block*
instead tightens every rung: with a paired-difference sd of ~25 µs/step (the value my R114
campaign just measured on this instrument), CI95 half-width goes from ±26 µs at 6 blocks
to ±23 µs at 7. That matters at the decision boundary — separating τ = 0.6 from τ = 0.3 on
the `AN` rung needs a half-width below ~39 µs, and I would rather clear that with margin
on four well-spaced doses than hold six doses at the edge. Retained spread is 9.83 → 66.38
MB, a **6.75× range**, which is what the linearity test actually consumes.

Rule 33 is satisfied automatically and not by my discipline: each rung emits a *different
kernel name* (`_lm1_pw1` → `_lm1` → no suffix at all), so MLX's name-keyed pipeline cache
cannot serve a stale pipeline.

## The doses — computed from source, fixed before measurement

Per-row plane bytes (`group_size = 16`, `LagunaRuntimeModel.swift:4348`; `nibDiv = 4` when
pairwise; `+1` row base):

| kernel | rows | groups | shipped | pairwise-off | stock |
|---|--:|--:|--:|--:|--:|
| `qkv_h64` ×30 | 10240 | 128 | 33 | 65 | 128 |
| `qkv_h48` ×10 | 8192 | 128 | 33 | 65 | 128 |
| `oproj_h64` ×30 | 2048 | 512 | 129 | 257 | 512 |
| `oproj_h48` ×10 | 2048 | 384 | 97 | 193 | 384 |

| arm | Δbytes/step | Δ vs family's 735.8 MB | predicted Δµs @ τ=1, 256.7 GB/s | @ 235.6 GB/s (family's own achieved rate) |
|---|--:|--:|--:|--:|
| `OP` | **+9.830 MB** | +1.34 % | **+38.3** | +41.7 |
| ~~`QP`~~ *(not run)* | ~~+12.452 MB~~ | ~~+1.69 %~~ | ~~+48.5~~ | ~~+52.9~~ |
| `ON` | **+29.409 MB** | +4.00 % | **+114.6** | +124.8 |
| `QN` | **+36.966 MB** | +5.02 % | **+144.0** | +156.9 |
| `AN` | **+66.375 MB** | +9.02 % | **+258.6** | +281.7 |

`AN = ON + QN` to the byte by construction, so **`AN` is also an additivity check**: if the
measured `AN` differs from `ON + QN` by more than the intervals allow, the ruler is
contaminated by something that is not bytes and I will say so rather than quote a τ.

## Pre-registered predictions

- **H1 (τ ≈ 1, the advisor's original assumption).** Slope of Δµs on Δbytes = 1/256.7
  GB/s ⇒ `AN` ≈ +259 µs/step. My §0c claim that the shipped planes bank **+2.367 % of
  score** is true only under H1.
- **H2 (cedar's τ ∈ [0.27, 0.43]).** `AN` ≈ +70 to +111 µs/step.
- **H3 (τ ≈ 0, planes are cache-resident).** `AN` ≈ 0, and the entire byte-removal axis —
  the *only* τ≈1 mechanism the campaign believes it has left — is retired tonight.

**Primary endpoint:** the OLS slope of paired Δ(decode s/token) on Δbytes across all four
non-reference rungs, expressed as τ, with CI95. **Secondary:** per-rung τ, to test
linearity.
**Tertiary:** `AN` vs `ON + QN` additivity.

**Decision rule, fixed in advance.**
- τ_pooled CI95 lower bound > 0.6 ⇒ the byte class is confirmed at ~unity on *my* kernels,
  cedar's sub-unity result is a property of the routed planes and not of bytes, and
  `N-ATTN-BYTE-FLOOR` is the binding constraint on this family (the remaining plane is
  96.6 µs/step, still under the 68.7 µs floor once τ is applied).
- τ_pooled CI95 upper bound < 0.6 ⇒ write `N-ATTN-SCALE-BYTES-SUBUNITY`, and note that it
  retires edward's #704 pricing as well as my own.
- Interval straddling 0.6 ⇒ report the interval and refuse to pick. I do not round
  intervals toward the answer I would like.

**A pre-registered self-criticism.** Three known asymmetries push measured τ *down*, so a
low reading is not automatically "bytes are free":

1. Rungs `ON`/`QN` switch to a *simpler* kernel (no base+nibble reconstruction, no escape
   branch), so they trade ALU **down** while trading bytes **up**. This biases τ toward 0.
2. Narrow-ON allocates the compressed bank *in addition to* the stock plane (kept resident
   for prefill), so narrow-OFF has a strictly smaller footprint and marginally better
   residency elsewhere. Also biases τ toward 0.
3. Escaped rows exist only in the narrow arms and read the stock plane, so the shipped
   control's true byte count is very slightly above my model — again biasing τ down.

All three are conservative for H1 and anti-conservative for H3. **If τ comes out high, it
is real; if it comes out low, I must not over-claim.** I am writing that here, before the
first run, precisely so I cannot decide it afterwards.

**A fourth risk, from my own R114.** I have just finished an experiment in which injecting
*empty* GPU dispatches made decode measurably **faster**, with the effect strongly
sublinear in dose — 1 injected dispatch produced most of the effect of 40. That is an
allocator/cadence confound, and it is a warning that this instrument can produce
significant, well-signed, reproducible differences that are not the mechanism under test.
The defence here is the dose ladder itself: a genuine byte effect must be **monotone and
roughly linear in Δbytes across a 6.8× range**, and must satisfy `AN = ON + QN`. A confound
of the R114 kind will not.
