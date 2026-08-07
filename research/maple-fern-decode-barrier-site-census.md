# Decode barrier-site census: where the 247 barriers are, and what each fusion refunds

PR #268 revision r2 (`maple-fern`). Host: **M4 Pro, Apple GPU generation 16**.
Every refund in this document is **M4-priced**; see
[§4 M5 transfer](#4-m5-transfer-and-what-this-host-cannot-tell-you) before
turning any number into a score.

## 0. What r1 left open

r1 (W&B `rcj6tohw`, comment 5217875868) priced the decode chain-link tax by
joint fit over 288 timings, 36 injection blocks, df=250:

| coefficient | estimate | t |
|---|---|---|
| MLX `memoryBarrier` | **+1.3003 ± 0.0597 µs** | 21.8 |
| compute dispatch | **+0.1231 ± 0.0481 µs** | 2.6 |
| dependent pair (sum) | +1.4234 ± 0.0256 µs | — |

Default decode step on this host: **8.18 ms, 406 dispatches, 247 barriers, 40
layers**. So the tax is a *barrier* (serial-depth) tax, and the selection
criterion for a decode candidate is **barriers removed**, not dispatches
removed.

r1 could not say **where** those 247 barriers are, so it could not price any
specific fusion. That is this revision's only job.

## 1. Instrument

`research/fern_tax_sitetrace.patch` adds a `DbSiteTrace` singleton to
`Vendor/mlx-swift/.../backend/metal/device.cpp` (+ `device.h`), enabled by
`DBTAX_SITE_TRACE=<path>`. For every compute dispatch it emits encode order,
command-buffer index, whether MLX inserted a `memoryBarrier` in front of it,
the RAW/WAR producer dispatches that forced it, grid/threadgroup, and kernel
name. `research/fern_tax_sitetrace.py` drives the unmodified decode path
(512-token seed from `correctness_prompts/public_longcopy_gate_english_512_256.json`,
then teacher-forced one-token steps). `research/fern_tax_sitecensus.py` reduces
the trace.

Research-only, never submitted, and the patch is reverted in this branch. Note
it changes `Vendor/mlx-swift/Source/Cmlx/mlx` bytes, so
`VendoredMetalFingerprint` refuses harness runs while it is applied — this
revision therefore carries **no new timing**, only structure. Timing
coefficients come from r1.

`CommandEncoder::synchronize()` is not called per decode step, so the whole run
lands in one MLX epoch and steps must be segmented post hoc. Segmenting on
`custom_kernel_laguna_decode_embedding_rope_atlas` gives 7 passes (1 warmup + 6
requested); the last four windows are **each exactly 406 dispatches / 247
barriers / 45 command buffers**, i.e. bit-identical in shape to the r1 baseline.
Canonical window used below: idx 10420–10825.

Artifacts: `research/artifacts/fern_sites.census.md` (reduced report),
`fern_sites.edges.tsv`, `fern_sites.perkernel.tsv`,
`fern_sites.sitemap.tsv.gz` (per-dispatch map; `gunzip -c` and pass to
`fern_tax_sitecensus.py` to reproduce every table).

## 2. Results

### 2.1 The step is a chain of 7 edges per sparse layer

Composition of the canonical 406-dispatch step:

| region | count | dispatches | barriers |
|---|---|---|---|
| sparse layers | 39 | 390 | 238 |
| dense layer 0 | 1 | 8 | 5 |
| lm-head tail | 1 | 7 | 4 |
| **total** | | **406** | **247** |

The **first structural finding** is about *fences*, not barriers. A dispatch
waits either because MLX charged a `memoryBarrier`, or because a command-buffer
boundary fell in front of it (a cb switch is a free fence — the GPU drains the
previous buffer anyway).

```
dispatches 406 | barriers 247 | cb switches 44 | fences (barrier ∪ cb) 291 | both 0
```

**`both = 0`: MLX never charges a barrier at a command-buffer boundary.** It
computes the dependency, sees the encoder already ended, and skips the barrier.
So some of the serial chain is already free. Dispatches per cb: min 1, max 12,
mean 9.02 — the binding limit is the **40 MB** byte budget
(`MLX_MAX_MB_PER_BUFFER`), not the 40-op budget, because routed expert weights
dominate. Both defaults live in `Vendor/.../mlx/utils.h:178-187`, selected by
arch in `device.cpp:740-756`.

Sparse-layer fences *including the entry edge* = **277 = 7.103 per layer**,
histogram `{7 fences: 35 layers, 8: 4}`; charged barriers per sparse layer
`{6: 35, 7: 4}`.

> **Each sparse layer is a 7-edge serial chain. 6.10 of those edges are paid as
> a charged `memoryBarrier`; 1.00 is absorbed free at a command-buffer
> boundary. Four layers pay one extra redundant in-wave cb split.**

The chain, with the three off-chain free riders:

```
down+residual(prev) ──E1──> inputNorm ──E2──> qkv ──E3──> attn ──E4──> o_proj
      ──E5──> postNorm+router ──E6──> shared_swiglu ──E7──> down+residual
                                       ^
free riders: gate_softplus  (inputNorm -> o_proj, rides inside attn's wave)
             router_top8    (postNorm+router -> down+residual)
             routed_swiglu  (postNorm+router -> down+residual)
```

Charge rate per chain edge, over the 39 sparse layers:

| edge | producer → consumer | charged | free | why free |
|---|---|---|---|---|
| E1 | down+residual → inputNorm | **31** | 8 | cb boundary at layer entry |
| E2 | inputNorm → qkv | **39** | 0 | — |
| E3 | qkv → attn | **24** | 15 | cb boundary (15 sliding, 9 full charged) |
| E4 | attn + gate_softplus → o_proj | **39** | 0 | 2 producers collapse to 1 barrier |
| E5 | o_proj → postNorm+router | **27** | 12 | cb boundary |
| E6 | postNorm+router → shared_swiglu | **39** | 0 | 3 consumers share 1 barrier |
| E7 | routed+top8+shared → down+residual | **39** | 0 | 3 producers collapse to 1 barrier |
| | **sum** | **238** | | matches sparse total |

238 + 5 (dense) + 4 (tail) = **247 ✓**. The site table and the aggregated
producer→consumer table are in `research/artifacts/fern_sites.census.md`.

**MLX already refunds about half the naïve cost.** A naïve one-barrier-per-edge
accounting of the 12 sparse-layer producer→consumer pairs would be 39 × 12 =
468 barriers; the measured sparse cost is 238, a 49% refund from wave
collapsing (E4, E6, E7) plus cb absorption (E1, E3, E5). Any fusion proposal
must be priced against 238, not against 468.

### 2.2 Per-layer templates

Six layer templates plus the tail; full tables in the artifact. Compressed:

| template | n | dispatches | barriers | charged edges |
|---|---|---|---|---|
| sliding, entry charged, E3 free, E5 charged | 15 | 10 | 6 | E1 E2 E4 E5 E6 E7 |
| sliding, E3 charged, E5 free | 12 | 10 | 6 | E1 E2 E3 E4 E6 E7 |
| full, E1 free | 5 | 10 | 6 | E2 E3 E4 E5 E6 E7 |
| full, all charged | 4 | 10 | 7 | E1 E2 E3 E4 E5 E6 E7 |
| sliding, E1 free | 3 | 10 | 6 | E2 E3 E4 E5 E6 E7 |
| dense layer 0 | 1 | 8 | 5 | — |
| lm-head tail | 1 | 7 | 4 | — |

Dense layer 0: `inputNorm[.] gate_softplus[BAR] qkv(h48)[.] attn(full)[.]
o_proj[BAR] postNorm[BAR] dense_gate_up[BAR] dense_down[BAR]`.

lm-head tail (cbs 1165/1167/1169): `inputNorm[.] lm:5a-coarse[BAR]
lm:5b-argmax1[BAR] lm:5c-winner[BAR] lm:5d-refine[.] lm:gather[.]
lm:argmax[BAR]`. `5c→5d` is already free via a cb split. Decode always takes
`refine == true` (`LagunaRuntimeModel.swift:10979`).

### 2.3 Refund rule

**Removing one charged chain edge by fusion refunds 39 barriers/step, i.e.
−1.0 per layer — not the 24–31 that edge is currently charged.**

Reasoning: the ~1.00 free fence per layer is a *cb split*, and cb splits are
placed by the 40 MB byte budget, which is set by routed expert weights. Fusing
away a 4 KB intermediate does not move a cb boundary, so the split stays where
it is and lands on whichever chain edge survives. Delete E2 and the layer's
7-edge chain becomes 6 edges of which ~1.00 is still absorbed → 5.10 charged,
down 1.00 from 6.10.

The conservative alternative assumes absorption scales with chain length
(6/7 × 6.10 × 39 ≈ 204, i.e. −34). **Quote the range −34 to −39 barriers per
removed chain edge.** §3 tests this directly.

Pricing at 1.3003 µs/barrier + 0.1231 µs/dispatch, 0.015280 %/µs of score:

| # | candidate | chain edge | Δbarriers | Δdispatch | µs/step (M4) | score (M4) | risk |
|---|---|---|---|---|---|---|---|
| **C1a** | fuse `inputNorm` into QKV; fused kernel still writes `normalized` | E2 | **−39** | −39 | **55.5** | 0.848% | low |
| **C1b** | fuse `inputNorm` + QKV + `gate_softplus` | E2 | **−39** | −78 | **60.3** | 0.922% | low-med |
| C2 | fuse `attn` into `o_proj` | E4 | −39 | −39 | 55.5 | 0.848% | **high** |
| **C2′** | fuse `o_proj` into `postNorm+router` | E5 | **−39** | −39 | **55.5** | 0.848% | medium |
| C3 | fuse `router_top8` into `postNorm+router` | off-chain | **0** | −39 | 4.8 | 0.073% | low |
| C4 | merge `shared_swiglu` into `routed_swiglu` (merged-9-slot) | off-chain | **0** | −39 | 4.8 | 0.073% | med |
| C5 | fuse `shared_swiglu` into `postNorm+router` | off-chain | **0** | −39 | 4.8 | 0.073% | med |
| C6 | collapse the whole lm-head cascade | tail | −4 | −6 | 5.9 | 0.091% | med |

Notes on each:

**C1a / C1b — the fused kernel already exists and is dead.**
`lagunaNormAffineQKV` (declared `LagunaRuntimeModel.swift:5301`, body `:4910`)
already fuses RMSNorm + affine QKV. It is dead on all 40 layers. The guard at
`LRM:5730-5744` requires `fusedAffine.mode == .affine`, `bits == 8`,
`groupSize == 32`, and `_nativeAffineQKVGateRows == nHeads`; its own comment
says the gate rows must be folded into the bank "so no consumer downstream of
here needs a device-visible normalized row" — the design already anticipates
C1b. It declines only because `lagunaNativeAffineNVFP4From` defaults to 0
(`LRM:2861-2867`), so every QKV bank is NVFP4 g16 b4. Two routes:

1. **Build the NVFP4-g16-b4 twin of `lagunaNormAffineQKV`** (new kernel,
   preserves 4-bit weight bandwidth). *Recommended primary.*
2. **Zero-new-kernel route:** have `MLXFastTransform` emit affine INT8 g32 QKV
   banks with gate rows folded, activating the existing dead path. This is
   inside the accepted attention re-quantization envelope, but INT8 g32 is
   ≈8.5 bits/weight vs NVFP4 g16 ≈4.5, i.e. **1.89× QKV bank bytes**, and
   decode is bandwidth-bound. That bandwidth cost must be priced before
   adoption; it could easily exceed a 55 µs refund.

`normalized` is consumed by `lagunaGateSoftplus` (`LRM:5800-5815`;
`fusedTailGateLogits` is `nil`, and `let normalized = fusedQKV ?? inputNorm(input)`
around `:5760`). C1a keeps that consumer and still removes E2; C1b removes the
consumer too and buys 39 more dispatches.

**C2 — high risk.** Attention is head-parallel; `o_proj` needs the full
2048-wide concatenation. Fusing them almost certainly needs a grid-wide sync,
which reintroduces the fence it was meant to remove.

**C2′ — the best structural companion to C1.**
`lagunaResidualRMSNormRouter` (call `LRM:10356`, def `:1055`) already fuses
residual-add + RMSNorm + router + ordinal keys. Adding `o_proj` in front is a
natural extension of an existing kernel, but it needs a single-threadgroup
2048×2048 gated NVFP4 GEMV.

**C3 / C5 — structurally worthless.** `router_top8` and `routed_swiglu` are
*off-chain*: they consume `postNorm+router` and their wait is already paid by
E6's single barrier (sites 10/11 in the artifact show one barrier serving three
consumers). Fusing either into a neighbour refunds dispatches only.

**C4 — the discriminator. The merged-9-slot design refunds zero barriers.**
This was the must-answer item. Trace proof: sites at idx …388/…398 show
`down+residual` with RAW producers `{routed_swiglu, router_top8,
shared_swiglu}` **collapsed onto one barrier** (E7, 39/39), and E6's single
barrier fires at whichever of the three consumers is encoded first. So whether
shared and routed SwiGLU are one dispatch or two changes neither E6 nor E7 —
the chain does not get shorter. Refund is 39 dispatches = **4.8 µs/step
(0.073%)**, an order of magnitude under the detection bar. Combined with the
already-recorded measurement at `LRM:7833-7850` — encoding the shared QMV
*after* routed already overlaps on the GPU, and moving it earlier regressed
+0.10 ms/step — **the advisor should drop the merged-9-slot design.**
(`mergedSharedActivated` at `LRM:10035` is never assigned; the `shared_slot = 8`
trick is at `:7871/:7887/:7890-7899` with epilogue `:7950-7965`.)

**C6 — not a decode lever.** The entire tail is 4 barriers + 6 dispatches =
5.9 µs/step even if collapsed to a single kernel.

### 2.4 Shortlist

Detection bar on this host is ≈**80 µs/step** (3σ of a matched decode pair).
**No single fusion clears it.** Chain contractions on *disjoint* edges are
additive in barrier count (7 → 5 edges gives −2/layer), so the shortlist is
bundles:

| bundle | edges | Δbarriers | Δdispatch | µs/step (M4) | score (M4) | M5 range |
|---|---|---|---|---|---|---|
| **A = C1a + C2′** | E2, E5 | −78 | −78 | **111.0** | 1.70% | 56–111 µs → 0.86–1.70% |
| B = C1b + C2′ | E2, E5 | −78 | −117 | 115.8 | 1.77% | 59–116 µs → 0.89–1.77% |
| C1a alone | E2 | −39 | −39 | 55.5 | 0.85% | 28–56 µs → 0.43–0.85% |

Ranked by refund-per-risk:

1. **C1a**, then **C1b** — an existing (dead) fused kernel path, the lowest
   new-kernel risk on the list. Route 1 (NVFP4 twin) preferred; route 2 must be
   bandwidth-priced first.
2. **C2′** — medium risk, extends an existing fused kernel, same refund.
3. C2 — same refund, high risk of reintroducing the fence.
4. C3, C4, C5, C6 — all ≤ 6 µs/step. **Do not spend a round on any of them.**

Ceilings, for calibration:

* Removing **all 247 barriers** = 321 µs/step = **3.9% of the 8.18 ms step**
  → 4.91% score M4-priced (5.67% including all 406 dispatches). That is the
  absolute roof on this whole family.
* A realistic floor of 4 chain edges per sparse layer (7 → 4) = −117 barriers
  = −152 µs/step plus dispatch savings.

**Additivity caveat that must travel with these numbers:** the 1.3003 µs
coefficient was fitted on barrier *additions* above the 247 baseline. Symmetry
on removal rests on one cross-check — sibling #269's 117 removed dispatches
predicted 166.5 ± 3.0 µs against a measured 144.23 ± 23.00 µs, agreeing at
0.96σ. That is a single removal-side point. Treat the first bundle to land as
a re-validation of the law, not only as a candidate.

## 3. Falsification test of the refund rule

The −39-vs-−34 question is exactly the question "do cb splits move when a chain
edge disappears?". Two cheap trace arms answer it by moving the cb budget
instead of the chain:

* **arm `m5budget`**: `MLX_MAX_MB_PER_BUFFER=50 MLX_MAX_OPS_PER_BUFFER=50` —
  the values `device.cpp:740-756` selects for arch `'s'`, i.e. **the ranked M5
  Max**. My M4 Pro is arch `'g'` (40/40).
* **arm `nosplit`**: both budgets 100000 — no cb splits at all. Prediction:
  barriers rise from 247 to **286** (the ~39 chain-absorbing splits become
  charged) and *not* to 291 (the ~5 redundant in-wave splits simply vanish).

Results are appended in §3.1 below.

### 3.1 Measured

<!-- FILLED IN BELOW -->

## 4. M5 transfer, and what this host cannot tell you

* Every µs figure above is **M4-priced**. r1's transfer range is
  `[M4_total / 1.98, M4_total]`, from the 8.18 ms (M4) vs 4.14 ms (M5-clock
  reference) step ratio. Use the interval, never the endpoint.
* **The 247 barrier count is itself M4-specific.** `device.cpp:740-756` gives
  arch `'g'` (M4 Pro) a 40 MB / 40 op budget and arch `'s'` (M5 Max) a
  50 MB / 50 op budget. A larger byte budget means *fewer* cb boundaries, hence
  *fewer* free absorptions and *more* charged barriers per step on the ranked
  machine. Direction of the error is favourable — the M5 has at least as much
  barrier headroom as the M4 — but the count must be re-measured there.
* This host selects no `_nax` kernels, so nothing here is evidence about
  prefill kernel choice. Prefill is untouched by every candidate above; all of
  them are decode-path fusions.
* **The equivalence oracle is blind to the fused-weight family.**
  `LagunaUpstreamEquivalence.swift:74-90` bypasses the weight cache, and
  `prepareFusedRuntimeWeights()` (`LRM:11016`) has exactly one caller
  (`LagunaRuntimeWeights.swift:637`). So a C1-route bug in fused weight
  preparation can pass the oracle. The 64-step drift tripwire and the
  teacher-forced goldens carry the correctness load for both C1 routes and for
  C2′. Any candidate in this family should run those explicitly.

## 5. Scope

No submitted path is touched by this revision. Surface growth is 0 bytes. All
new files are under `research/`.
