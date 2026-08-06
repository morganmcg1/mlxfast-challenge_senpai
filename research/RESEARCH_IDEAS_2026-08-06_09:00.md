# RESEARCH IDEAS — 2026-08-06 09:00 (fresh outside review)

Scope: frontier `bbc9e7b`, officialScore 2.58882784082067 (decode 4908.372
µs/step, prefill 191.201 µs/token). Byte headroom 65,669 B total;
`LagunaRuntimeModel.swift` at 479,751/524,288 B. Pricing constants used
throughout: 1 ms decode = 14.862% of score; 1 ms prefill = 0.371%; decode
byte channel at 546.2 GB/s ⇒ **1 MB/step ≈ 1.83 µs ≈ 0.0272% of score**
(anchor: #72's 30.66 MB = +0.834%); single-receipt MDE ≈ 27.8 MB/step;
instruction-channel M4 numbers quoted as intervals only (§0.9.36).
Deliberately avoids the four in-flight arms (#101/#103/#104/#105) and all
closed families. Ranked by expected value per source byte spent.

---

## R1. Certified-exact router screen: INT8/INT4 coarse routing GEMV + exact BF16 refine (byte channel, stackable)

**Hypothesis.** The 40.9 MB/step BF16 router plane can be cut to ~13–24
MB/step with a two-pass certified screen that provably reproduces the exact
top-8 set and exact BF16 routing weights, worth **+0.45–0.78% of score** on
the pre-priceable byte channel.

**Mechanism.** Routing runs inside the fused
`laguna_residual_rms_router_bf16_2048_rpg*` kernel
(`LagunaRuntimeModel.swift:607, :882-:1001`), which reads the full
2048×256 BF16 router weight per layer (1.05 MB × 40 = 40.9 MB/step, census
`routers BF16 40.9`). Selection reproduces
`argPartition(-scoresForChoice, kth: 7)` with correction bias (`:8923-:9525`).
Only the top-8 *set* and the 8 exact BF16 logits matter downstream
(`router_weights` consumed at `:7783/:7947`). Replace the in-kernel GEMV with:
(a) an INT8 (rung 2: INT4) coarse GEMV over all 256 experts using a
load-time-quantized copy plus a precomputed per-row error bound
`ε_r = max|w−ŵ|·Σ|h|` (Σ|h| computed in the same kernel — the RMS pass
already reduces over `h`); (b) exact BF16 re-evaluation, in the stock FMA
order, of every expert whose coarse upper bound ≥ the 8th-best lower bound
(inclusive, so boundary ties are refined). This is the notes/68 lm-head
pruner argument (`LagunaLmHeadPruner`, `:10913-:10975`) transplanted from
vocab rows to expert rows, fused so **zero dispatches are added**.

**Exactness.** Bit-exact by construction: survivors are recomputed in BF16
with identical accumulation order; the screen only excludes experts whose
score provably cannot enter the top-8; inclusive bounds preserve
`argPartition` index-order tie semantics. Same certification class as the
already-accepted lm-head cascade.

**Size & channel.** Byte channel. INT8 rung: 40.9→(20.5+~2.6 survivors) ⇒
−17.8 MB ≈ +0.48%. INT4 rung: −28.1 MB ≈ +0.76% (clears MDE alone).
Exchange-law check at k=2.5: 8–12 bits removed/weight vs ~1 extra
dequant-FMA/weight — passes with margin. Instruction-side risk is bounded
because no dispatch is added and the kernel is glue-diffuse, not
ALU-saturated.

**Falsifier (free, no GPU).** A Python/offline simulation on the real router
weights: quantize, compute per-row ε, replay survivor counts over (i) fixture
activations, (ii) random RMS-normed vectors. If mean survivor count at INT4
exceeds ~48 (bytes saved < 20 MB) or boundary-tie ambiguity appears at BF16
resolution, kill or fall back to INT8 before writing any kernel code. Second
falsifier: 64-step drift tripwire is definitionally clean (exactness is
structural), so any local mismatch means an implementation bug, not a lost
bet.

**Byte cost.** ~8–10 kB (coarse-plane prep in the load-time fusion path
`:5536-:5637` + kernel-source edit + bound plumbing). **EV/byte: highest on
the board; stacks with #104/#105.**

---

## R2. Decode-traversal-order weight arena (fresh axis: VA/page locality)

**Hypothesis.** Packing all decode-hot weight banks into one (or few) jumbo
buffers laid out in exact decode traversal order removes page-walk/TLB and
buffer-switch overhead worth **0 to ~−150 µs/step (0 to +2.2%)** — an axis
the programme has never measured (no TLB/heap/placement result exists in
`CURRENT_RESEARCH_STATE.md`).

**Mechanism.** Load-time fusion builds per-layer banks via `concatenated`
(`LagunaRuntimeModel.swift:5536-:5637` QKV/scales, `:5602`, `:5635`,
`:8270-:8271` gate/up), yielding hundreds of independently allocated
MTLBuffers whose VA order is checkpoint-load order, not execution order.
Decode streams ~1.79 GB/step across them. The runtime already uses zero-copy
contiguous row views of load-time atlases (`:560-:567`), so the mechanism is
proven in-repo: allocate one arena array per weight class at the end of load,
copy banks into it in traversal order, rebind the kernels' arrays as
contiguous views, drop the originals. Load-time work is unscored (fern #22);
RAM is not binding.

**Exactness.** Trivially bit-exact: identical bits, identical kernels,
different base addresses.

**Size & channel.** Instruction/latency channel — interval only. Prior
evidence that placement effects reach score scale: the SHARED-after-ROUTED
ordering guard costs ~+70 µs/step with a residency/locality explanation
(§ ordering notes), and sliding-attention runs cache-served at 443 GB/s,
i.e. the memory hierarchy, not DRAM, prices much of decode. If TLB/residency
contributes even 1% of the step, recovering half is ~+0.35%; genuinely
unknown, which is the point of a cheap probe.

**Falsifier (cheap, M4).** Stage 0 (~1 h): log allocation order vs traversal
order and count distinct buffers touched per step — if fusion already yields
few, large, well-ordered banks, stop. Stage 1: A/B decode seconds/token on M4,
arena vs stock, same host, fresh baseline; sign-and-existence only. Any M4
null ⇒ close the axis for ~4 kB of throwaway code and one afternoon; an M4
positive ⇒ price on M5 via receipt.

**Byte cost.** ~4–6 kB, all in load-time code. **EV/byte: high due to option
value on an unprobed axis; worst case buys a durable closure.**

---

## R3. Prefill routed gather-GEMM tile fit — elevate queue item C2 (BN 64→32) with a pre-registered decision rule

**Hypothesis.** The prefill expert GEMM wastes ≥half its MMA issue on padding
because average rows/expert = 512·8/256 = **16** against BN=64 tiles;
BN=32/BM-repair recovers 1.5–4% of S₀ = **+0.55–1.45% of score**.

**Mechanism.** Prefill moves 14.09 GB of routed-expert weights (roofline
table: routed_experts 1005 GFLOP / 14,087 MB) through NAX gather-GEMM
(`fp_quantized_nax.h` fragment geometry `:583-:584`, BK=64/SK=32 unroll
notes `:1402, :1762`). With 16-row average expert groups, a 64-row tile
computes 75% dead rows; the receipt-differenced prefill arithmetic leaves a
**31.28 ms unattributed remainder** (glue + NVFP4/MoE efficiency deficit)
of which this is the largest identified constituent. This is queue item C2 —
unowned; the new content here is the decision rule below and the pairing
with R6's row-histogram so the tile choice is data-driven, not guessed.

**Exactness.** Tile shape changes scheduling only; dequant→MMA→accumulate
order per output element is preserved by the header's own design contract
(`:938`, `:1549`). Verify with the M4-runnable non-NAX twin bitwise oracle +
upstream equivalence; M4 cannot price it (gen16 never runs `_nax`).

**Size & channel.** Prefill instruction/occupancy channel; must be priced by
one M5 receipt. 1.5 ms → +0.55%; 4 ms → +1.45%. Decode is untouched (decode
QMV is a different kernel family), so the receipt is clean single-axis.

**Falsifier (cheap, before any receipt).** Offline: histogram actual
rows-per-expert per layer on fixture prefills (pure Swift/Python, no GPU).
If the distribution is bimodal with mass ≫32 rows (routing concentration:
census shows busiest 8 experts hold a large share and 20.26% of
(layer,expert) pairs get zero rows), BN=32 helps less than the mean
suggests — compute the expected issue-waste delta analytically first; abort
if <1.5% of S₀.

**Byte cost.** ~3–5 kB (tile constants + host-side selection in the
generated-twin `.cpp` kept consistent). **EV/byte: high, but consumes a
scarce receipt; run after R1/R2 evidence exists.**

---

## R4. lm-head stage-4 `sparse_refine` M5 geometry (queue #9, unowned, M5-only)

**Hypothesis.** The decode lm-head tail
`..._sparse_refine_v1` (~0.5 MB moved in 74.9 µs on M4) is latency/occupancy
bound, and an M5-tuned threadgroup geometry recovers **20–40 µs/step =
+0.3–0.6%**.

**Mechanism.** Stage-1 of the cascade is at 100.2% of its memory ceiling
(§R20.1 erratum — saturated, only fewer bytes help, and #105 already takes
that lane), but stage-4 moves trivial bytes in ~57 µs M5-equivalent: it is
the one lm-head stage priced by dispatch+occupancy, not bandwidth. Sweep
threadgroup width / rows-per-TG / split-K of the refine kernel (kernel decl
in the `LagunaLmHeadPruner` fused-refinement path, `:10958-:10975` call
site), choosing geometry by M5 receipt.

**Exactness.** Bit-exact: refinement already recomputes exact BF16 logits
for surviving rows; geometry changes lane assignment only; keep per-row
accumulation order fixed.

**Size & channel.** Instruction/latency channel, M5-only question (M4
geometry sign does not transfer). Price only via receipt; bundle as the
second axis of an otherwise-scheduled submission if possible, else it costs
one receipt for ≤0.6%.

**Falsifier.** M4 first: if stage-4 M4 time ≈ its M4 byte floor (i.e. it is
*not* latency-bound even on M4), the premise dies free. Then a single
two-variant receipt decides.

**Byte cost.** ~1–2 kB (geometry constants + one alternate dispatch). *EV/byte
good; absolute size modest.*

---

## R5. Prefill glue-pass reduction — queue C5, fully M4-local bisection of the 31.28 ms remainder

**Hypothesis.** A measurable slice (target 2–6 ms) of the 31.28 ms
unattributed prefill remainder is M4-visible glue — materialized
intermediates, sort/scatter around routing, mask/RoPE re-builds — removable
without touching NAX kernels, worth **+0.2–0.8% prefill-side** (0.371%/ms)
with no receipt needed.

**Mechanism.** 94.2% of M5 prefill time is NAX kernels M4 never runs, but the
glue (router+tournament, sort/scatter, copies, norm/rope reshapes) is
identical Swift/MLX code on both machines (prefill file C-items;
`lagunaLastTokenHidden` slicing at `:10948-:10952` shows the pattern of
already-banked glue wins). Enumerate per-op prefill dispatches on M4
(GPU trace), rank non-GEMM ops by µs, delete/fuse the top items (e.g.
argsort→argPartition-width reductions, avoided materializations before
`gather_qmm`).

**Exactness.** Restrict to ops with bitwise-identical outputs (elision of
materializations, dtype-preserving fusions); every change gated by the
upstream-equivalence oracle + public prefill fixtures.

**Size & channel.** Prefill; mixed byte+instruction, but M4-local: glue ops
are not `_nax`, so M4 wall-clock deltas are valid sign evidence, and byte
elisions price in advance. 1 ms = +0.371%; floor risk nil (changes are
strictly work-removing).

**Falsifier.** The M4 dispatch census itself: if non-GEMM glue sums to <3 ms
M4-equivalent, close for free. This also produces the first real attribution
of the 31.28 ms pool — negative evidence the programme currently lacks.

**Byte cost.** ~2–5 kB. **EV/byte solid; zero receipt cost until a win
exists.**

---

## R6. Free structure censuses on shipped planes: g64 quad-constancy and zero-cacheline clustering

**Hypothesis (two cheap bets, one script).** (a) If the checkpoint's expert
scale plane is pairwise-duplicated because the original quantizer was
coarser than g16, scale *quads* may also be equal (effective g64), enabling
a further lossless halving of the routed+shared scale planes: −15.3−3.8 ≈
**−19 MB/step ≈ +0.52%** stacked on #72/#104. (b) If NVFP4 nibble planes
contain all-zero 128-byte cachelines in clustered runs (pruned/dead expert
rows), a row-list skip in the routed QMV removes real bytes from the 552
MB/step stream.

**Mechanism.** #72 proved 99.999983% pairwise scale equality with 168
structured exceptions — evidence the shipped plane is a re-expansion of a
coarser artifact; nobody has tested stride-4. Census is `numpy` over the
safetensors, zero GPU, zero scored bytes. If (a) passes at ≥99.9% with a
provable exception rule, implement exactly as #72 did (predicate keyed on
grid coord, `fp_quantized.h:2186-2205` pattern). For (b), only whole-row /
whole-cacheline zeros count (sub-cacheline zeros save no bytes; ALU-only
skips fail the exchange-law test on a cache-served kernel).

**Exactness.** (a) is lossless re-indexing with a bitwise certificate
(§0.9.21); (b) skips rows that provably contribute 0 to the accumulator.

**Size & channel.** Byte channel, pre-priceable. (a) +0.52% if true;
(b) unknown — census decides; anything <27.8 MB/step banks as a stackable
rung only.

**Falsifier.** The census *is* the falsifier and costs an hour. Prior
probability for (a) is genuinely uncertain (the 168 exceptions sit at flat
pair 0, consistent with either g32-true or g64-true origins); for (b) low —
but both die silently with zero scored bytes if negative.

**Byte cost.** 0 until a census passes; then ~2–4 kB reusing #72's merged
predicate. **EV/byte: infinite on the census step by construction.**

---

## Checked and rejected while preparing this list

- **Attention scale plane g16→g32**: already banked losslessly by #35+#80
  (plane now ~23.1 MB/step; a further lossy halving is sub-MDE and buys risk).
- **KV-cache quantization, dense-layer-0 or router lossy requant**: outside
  the accepted attention envelope (R1 is *exact*, hence exempt, like the
  lm-head cascade).
- **RotatingKVCache rotation copies**: `updateInPlace` exists
  (`KVCache.swift:611`); sliding attention already closed at ~90% of issue
  floor.
- **Native FP4 NAX MMA for prefill projections**: `fp_quantized_nax.h`
  dequantizes to T before MMA (`:287-:289, :461-:464`); no native low-precision
  MMA path exists in-tree, so the "quantized prefill attention" closure
  stands.
- **Expert placement by co-activation popularity**: fixture-derived routing
  statistics — specialization smell, hidden-prompt risk.
- **Dispatch-count and barrier families, strand fusion, argmax duplication,
  encode reordering**: closed or in the 02:40 critique list; not repeated.

## Suggested sequencing under the 65,669-byte headroom

R1 offline falsifier + R6 censuses immediately (zero scored bytes), R2 stage-0
in parallel (one afternoon, M4). First submission wave: R1 (INT4 or INT8 rung
per survivor sim, ~10 kB) stacked per the wrapper's paired floors; R4 rides
the same session if a slot allows. R3 spends a receipt only after its
analytic issue-waste check passes. Total worst-case scored-byte spend
≈ 25 kB — well inside headroom, leaving room for the in-flight arms' growth.
