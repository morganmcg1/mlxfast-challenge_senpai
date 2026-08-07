# PR #268 r2 — Decode barrier-site census: where the 247 barriers live, and what a fusion actually refunds

Student: maple-fern. Assignment `maple-2026-08-07g-dispatch-tax-attribution`, revision r2.
Branch `maple-fern/dispatch-tax-attribution-battery`. Base `13f9b6f7960bf1872465f2e7950685d52ccf2e48`.

Host: M4 Pro, Apple GPU generation 16, 48 GiB unified memory. **No `_nax` kernels are
reachable here.** Every number in this document is M4 evidence and is directional for the
ranked M5 only under the transfer rules restated in §4. Nothing in r2 changes a submitted
path: this revision is measurement and analysis on research-only instruments.

---

## §0. What r1 established, and what r2 was asked to add

r1 (W&B run `rcj6tohw`, comment 5217875868, accepted) separated the two candidate carriers of
the decode per-op tax by injecting each independently and fitting them jointly (n=288, 36
blocks, df=250):

| carrier | coefficient | t |
|---|---|---|
| `memoryBarrier` (serial fence) | **+1.3003 ± 0.0597 µs** | 21.8 |
| bare extra dispatch (no new fence) | **+0.1231 ± 0.0481 µs** | 2.6 |
| dependent pair (both, as a normal op adds them) | +1.4234 ± 0.0256 µs | — |

So the ~1.4 µs/op decode tax is **91% barrier and 9% dispatch**. The default decode step on
this host is **8.18 ms, 406 dispatches, 247 charged barriers, 40 layers**. The advisor adopted
"barriers (serial depth) removed" as the selection criterion for the next decode round, closed
the ICB / encode-overlap / `start_concurrent()` / graph-reordering family (they move dispatches,
not fences), and pointed the round at **kernel fusion**.

r1 left one thing unpriced: it knew the *rate* but not the *sites*. A fusion that removes a
dispatch whose barrier MLX was already absorbing for free refunds 0.12 µs, not 1.42 µs — a
12× pricing error. r2 answers, per candidate fusion:

1. which dependency edge it removes (§2.1),
2. whether that edge is actually charged a barrier today (§2.2),
3. how many barriers per step the fusion refunds, and what that is worth (§2.3),
4. and which subset clears the detection bar in one round (§2.4).

Two items were flagged must-answer: **C1** (fuse `inputNorm` into QKV) and **C4** (the
merged-9-slot shared+routed expert design). Both are answered.

---

## §1. Instrument

`research/fern_tax_sitetrace.patch` adds a `DbSiteTrace` singleton to
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp` (+ `device.h`). It is inert
unless `DBTAX_SITE_TRACE=<path>` is set. At each dispatch it records one `DBSITE` line:

```
DBSITE ep= cb= ord= bar= gap= raw= war= grid= tg= k=
```

- `ep` epoch (forward pass), `cb` command-buffer serial, `ord` ordinal within the epoch,
- `bar=1` iff MLX charged a `memoryBarrier` immediately before this dispatch,
- `raw=` / `war=` the producing dispatch ordinals MLX resolved for this dispatch's read-after-write
  and write-after-read hazards — i.e. **the actual dependency edges**, not a guess,
- `k=` the Metal kernel name, `grid`/`tg` the dispatch geometry.

`DBCB` marks command-buffer commit, `DBEPOCH` marks a forward pass. The patch is research-only
and reverted in the worktree; it is **not** on a submitted path. Note that it changes the
vendored-Metal fingerprint (`Sources/MLXFastTrustedHarness/VendoredMetalFingerprint.swift:19-21`
SHA-256s all of `Vendor/mlx-swift/Source/Cmlx/{mlx,mlx-generated}`), so a patched build cannot
run the trusted harness. It can run the raw runtime worker, which is all a structural census
needs.

`research/fern_tax_sitetrace.py` drives the worker (`--steps N --out PREFIX`); worker startup is
~43 s and a 3-step arm costs ~43 s total. `research/fern_tax_sitecensus.py` reduces a trace:
it segments epochs on `custom_kernel_laguna_decode_embedding_rope_atlas`, takes the last
complete 406-dispatch decode window, and emits the site map, the per-layer templates, the
aggregated barrier-charged edge table, and per-edge charge rates.

Reduced artifacts, both profiles:

```
research/artifacts/fern_sites.census.md                     default/low profile, reduced
research/artifacts/fern_sites.edges.tsv
research/artifacts/fern_sites.perkernel.tsv
research/artifacts/fern_sites.sitemap.tsv.gz
research/artifacts/fern_sites.lowprofile.worker.err
research/artifacts/fern_sites_fullprofile.census.md          ranked/full profile, reduced
research/artifacts/fern_sites_fullprofile.edges.tsv
research/artifacts/fern_sites_fullprofile.perkernel.tsv
research/artifacts/fern_sites_fullprofile.sitemap.tsv.gz
research/artifacts/fern_sites_fullprofile.trace.worker.err
```

Raw traces (1.3–1.4 MB each) were reduced and deleted; the site maps are kept gzipped so the
edge tables can be re-derived without a GPU.

---

## §2. Census

### §2.1. The decode chain is exactly 7 edges per sparse layer, and that is profile-invariant

Reading the `raw=`/`war=` fields rather than the encode order, one sparse (sliding-window) layer's
serial chain is:

```
down+residual(prev) -E1-> inputNorm -E2-> qkv -E3-> attn -E4-> o_proj
        -E5-> postNorm+router -E6-> shared_swiglu -E7-> down+residual
```

Three dispatches per layer are **off-chain free riders** — they are dependencies of the chain but
never lengthen it, because they overlap with a chain dispatch inside the same wave:

- `gate_softplus` (inputNorm → o_proj) rides in `attn`'s wave,
- `router_top8` and `routed_swiglu` (postNorm+router → down+residual) ride together and are
  collapsed onto E7's single fence.

So the chain depth is **7**, and the layer has **10 dispatches** (sliding) — 3 of them free.

r1's report estimated "6.2 measured waves vs ~7 structural waves per layer" by reading a trace
and flagged the gap in its caveats 3 and 11. r2 measures the fence total directly and the
structural depth is confirmed at exactly 7; **r1 caveats 3 and 11 are resolved.**

#### The two-profile fence table

The census was run twice on the same host, weights, and seed, changing only the startup memory
profile (`DARKBLOOM_STARTUP_MEMORY_PROFILE`), which is what moves the command-buffer boundaries:

| per decode step | default / low (128 MB, 64 ops) | ranked / full (320 MB, 128 ops) | Δ |
|---|---|---|---|
| dispatches | 406 | 406 | 0 |
| command-buffer switches | 44 | 29 | −15 |
| **charged barriers** | **247** | **258** | **+11** |
| total fences (barriers + cb boundaries) | 291 | 287 | −4 |
| sparse fences per layer | 7.103 | **7.000** | −0.103 |
| command buffers | 45 | 30 | |

The headline structural fact:

> **`barrier ∧ cb = 0` in both regimes.** MLX never charges a `memoryBarrier` at a
> command-buffer boundary — the commit already provides the ordering, so the fence is free.

That is the absorption mechanism. Chain depth is 7 edges per sparse layer in both profiles; the
profile only decides **which** of those 7 edges get their fence for free. Fewer command buffers
(ranked) means fewer free rides and therefore *more* charged barriers, with the total fence count
essentially invariant (291 vs 287 — the 4-fence difference is the dense layer and boundary
placement, not a change in depth).

#### What actually places the command-buffer boundaries

This matters because a fusion's refund depends on whether the boundary can wander onto the edge
being removed. It cannot, and the reason is worth stating precisely.

`Sources/MLXFastModel/RuntimeStartupMemoryPolicy.swift:170-183` force-sets both MLX buffer limits
with `setenv(..., 1)` — **overwrite** — so:

- MLX's own architecture table (`device.cpp:570-597`: 40 MB/40 ops for `'g'`, 50/50 for `'s'`)
  is irrelevant, and
- an operator-supplied `MLX_MAX_MB_PER_BUFFER` / `MLX_MAX_OPS_PER_BUFFER` is **silently
  discarded**.

The profiles (`RuntimeStartupMemoryPolicy.swift:28-118`) are:

| profile | selected when | metal cache | per-buffer budget |
|---|---|---|---|
| low | physical < 64 GiB, or `DARKBLOOM_STARTUP_MEMORY_PROFILE=low` | 6 GiB, cleared after warmup | **128 MB / 64 ops** |
| full (ranked) | physical ≥ 64 GiB, or `…=full` | 32 GiB | **320 MB / 128 ops** |

`DARKBLOOM_STARTUP_MEMORY_PROFILE` accepts `auto|full|low`; anything else is a
`preconditionFailure`. This host is 48 GiB, so **the default local profile is `low`** and the
ranked M5 (128 GB) runs `full`. That makes the second census arm the ranked-side structure, not
a hypothetical.

`needs_commit()` (`device.cpp:484-487`) is
`buffer_ops_ > max_ops || (buffer_sizes_ >> 20) > max_mb`. Measured dispatches per command
buffer are **9.0 (low)** and **14.0 (ranked)** — far under 64 and 128 — so the **referenced-byte
budget is what binds**, and it is dominated by the routed expert banks each layer touches. A
fused kernel that stops materializing a ~4 KB intermediate row cannot move a 128 MB or 320 MB
boundary.

Two corrections to earlier assumptions, both measured:

1. An earlier arm tried `MLX_MAX_MB_PER_BUFFER=50 MLX_MAX_OPS_PER_BUFFER=50` against `=100000`
   and got **byte-identical per-step structure (406 / 247 / 45)** in both arms. That is not a
   null result about buffer size; it is the falsification of the assumption that those env vars
   reach MLX at all. They are overwritten by the policy. The profile override is the only working
   control.
2. `Sources/MLXFastModel/LagunaRuntimeWeights.swift:386-387` does
   `setenv("MLX_MAX_*", "200", 0)` — overwrite **0** — after the policy has already set the
   variable, so it is dead code. Anyone reading only that line would predict a 200 MB budget.

#### Region composition

| region | dispatches | barriers (low) | barriers (ranked) |
|---|---|---|---|
| 39 sparse layers | 390 | 238 | 248 |
| dense layer 0 | 8 | 5 | 6 |
| lm-head tail | 7 | 4 | 4 |
| **total** | **406** | **247** | **258** |

The ranked profile's extra dense-layer barrier is a newly-charged `embed+rope → inputNorm` edge.

### §2.2. Which edges are charged today

Charged barriers per edge, out of the 39 sparse layers:

| edge | dependency | charged (low) | charged (ranked) |
|---|---|---|---|
| E1 | down+residual(prev) → inputNorm | 31 | 33 |
| **E2** | **inputNorm → qkv** | **39** | **39** |
| E3 | qkv → attn | 24 | 39 |
| E4 | attn + gate_softplus → o_proj (2 producers, 1 fence) | 39 | 39 |
| **E5** | **o_proj → postNorm+router** | **27** | **39** |
| E6 | postNorm+router → shared_swiglu (3 consumers, 1 fence) | 39 | 39 |
| E7 | routed + top8 + shared → down+residual (3 producers, 1 fence) | 39 | 20 |
| | **sparse total** | **238** ✓ | **248** ✓ |

Read this table together with the absorption mechanism. Under the low profile the free rides land
on E3 (15/39) and E5 (12/39) and E1 (8/39). Under the **ranked** profile they migrate almost
entirely to **E7 (19/39)** and **E1 (6/39)**, because the larger byte budget puts the boundary
just after the routed-expert dispatches instead of mid-attention. The two shortlisted edges,
**E2 and E5, are 39/39 charged under the ranked profile** — there is no absorption on them to
give back.

#### MLX already refunds about half

A naïve "one barrier per dependency pair" model of a 12-dispatch sparse layer predicts
39 × 12 = **468** sparse barriers per step. Measured: **238–248**. MLX's hazard tracker already
collapses multi-producer and multi-consumer edges onto single fences and absorbs the rest at
command-buffer boundaries — it is already refunding ~48%. **Price any candidate against 238–248,
never against 468.** Pricing against the naïve model is the single easiest way to over-promise a
fusion by 2×.

#### Per-layer templates

Default / low profile (dispatches, charged barriers):

| count | template | disp | bar |
|---|---|---|---|
| 15 | sliding, E3 free | 10 | 6 |
| 12 | sliding, E5 free | 10 | 6 |
| 5 | full attention, E1 free | 10 | 6 |
| 4 | full attention, all charged | 10 | 7 |
| 3 | sliding, E1 free | 10 | 6 |
| 1 | dense layer 0 | 8 | 5 |
| 1 | lm-head tail | 7 | 4 |

Ranked / full profile: 19 × E7-free (6 bar), 9 × all-charged (7), 5 × (7), 4 × (6), 2 × (6),
dense (6), tail (4).

Dense layer 0, expanded (`[BAR]` = charged):

```
inputNorm[.] gate_softplus[BAR] qkv(h48)[.] attn(full)[.] o_proj[BAR] postNorm[BAR]
dense_gate_up[BAR] dense_down[BAR]
```

lm-head tail, expanded (command buffers 1165 / 1167 / 1169):

```
inputNorm[.] lm:5a-coarse[BAR] lm:5b-argmax1[BAR] lm:5c-winner[BAR] lm:5d-refine[.]
lm:gather[.] lm:argmax[BAR]
```

The `5c → 5d` edge is already free via a command-buffer split. Decode always takes
`refine == true` (`LagunaRuntimeModel.swift:10979`), so all 7 tail dispatches are live.

### §2.3. The refund rule

> **Removing one charged chain edge refunds 39 barriers per step** — one per sparse layer.

Three independent supports:

1. **Boundaries cannot move onto the removed edge.** They are placed by a 128 MB / 320 MB
   referenced-byte budget dominated by expert banks (§2.1). Not materializing a ~4 KB
   intermediate row does not shift one.
2. **Arm 3 measured the absorption converting the right way.** Cutting command buffers from 45 to
   30 turned 11 free rides into charged barriers while the total fence count stayed within 4
   (291 → 287). Absorption and charging trade ~1:1 against a fixed serial depth, which is exactly
   the behaviour the refund rule assumes.
3. **The shortlisted edges have no absorption to lose.** E2 and E5 are 39/39 charged under the
   ranked profile, so their refund cannot be eroded by MLX reclaiming a free ride elsewhere.

An earlier, more conservative "−34 barriers" figure allowed for absorption on the target edge.
For E2 and E5 that allowance is now measured to be zero and **−39 is the correct figure**; the
conservative variant is superseded for those two edges only.

Pricing constants (r1, M4): **1.3003 µs per barrier**, **0.1231 µs per dispatch**,
**0.015280 % of score per µs/step** of decode time.

| # | candidate | edge | Δbarriers | Δdispatches | µs/step | score | risk |
|---|---|---|---|---|---|---|---|
| **C1a** | fuse `inputNorm` into QKV, fused kernel still writes `normalized` | E2 | −39 | −39 | **55.5** | **0.85%** | low |
| **C1b** | fuse `inputNorm` + QKV + `gate_softplus` | E2 | −39 | −78 | **60.3** | **0.92%** | low-med |
| C2 | fuse `attn` into `o_proj` | E4 | −39 | −39 | 55.5 | 0.85% | **high** |
| **C2′** | fuse `o_proj` into `postNorm+router` | E5 | −39 | −39 | **55.5** | **0.85%** | medium |
| C3 | fuse `router_top8` into `postNorm+router` | off-chain | **0** | −39 | 4.8 | 0.07% | low |
| C4 | merge `shared_swiglu` into `routed_swiglu` (merged-9-slot) | off-chain | **0** | −39 | 4.8 | 0.07% | med |
| C5 | fuse `shared_swiglu` into `postNorm+router` | off-chain | **0** | −39 | 4.8 | 0.07% | med |
| C6 | collapse the whole lm-head cascade | tail | −4 | −6 | 5.9 | 0.09% | med |

Δbarriers uses the **ranked** profile charge rates. Note the shape of the table: the three
off-chain candidates (C3, C4, C5) refund **exactly zero barriers**. They are 0.07% ideas being
discussed as if they were 1% ideas, and the only reason to know that is the `raw=`/`war=` trace.

#### C1 — fuse `inputNorm` into QKV (E2). Feasible, and the code already anticipates it.

`lagunaNormAffineQKV` (declaration `LagunaRuntimeModel.swift:5301`, body `:4910`) **already
exists** and already fuses RMSNorm + affine QKV. It is **dead on all 40 layers**. The guard at
`LagunaRuntimeModel.swift:5730-5744` requires `fusedAffine.mode == .affine`, `bits == 8`,
`groupSize == 32`, and `_nativeAffineQKVGateRows == nHeads`. Its own comment says the gate rows
must be folded into the bank "so no consumer downstream of here needs a device-visible
normalized row" — i.e. the design already anticipates C1b, not just C1a. The path declines only
because `lagunaNativeAffineNVFP4From` defaults to 0 (`:2861-2867`), so every QKV bank is NVFP4
g16 b4 and never affine INT8 g32.

Two routes:

- **Route 1 (recommended primary): build the NVFP4-g16-b4 twin of `lagunaNormAffineQKV`.** A new
  kernel, but it preserves the 4-bit bank bandwidth that decode depends on, and the surrounding
  plumbing (guard, call site, weight prep) is already written for the affine twin.
- **Route 2 (zero new kernel): have `MLXFastTransform` emit affine INT8 g32 QKV banks with gate
  rows folded**, activating the dead path. This is inside the accepted attention re-quantization
  envelope (group-32 affine INT8 for Q/K/V/O and per-head `g_proj`). But INT8 g32 is ~8.5
  bits/weight against NVFP4 g16's ~4.5, i.e. **1.89× QKV bank bytes**, and decode is
  bandwidth-bound. Route 2 must be priced before adoption — it can plausibly lose more to
  bandwidth than the 55.5 µs it wins on fences.

`normalized` is consumed by `lagunaGateSoftplus` (`:5800-5815`); `fusedTailGateLogits` is `nil`,
and `let normalized = fusedQKV ?? inputNorm(input)` sits near `:5760`. C1a keeps writing
`normalized` and therefore keeps `gate_softplus` as a separate (free-riding) dispatch; C1b folds
the gate rows into the bank and deletes that dispatch, which is why C1b buys 39 extra dispatches
but no extra barriers.

#### C2′ — fuse `o_proj` into `postNorm+router` (E5). The cheapest second edge.

`lagunaResidualRMSNormRouter` (call `:10356`, definition `:1055`) already fuses residual-add +
RMSNorm + router + ordinal keys. Prepending `o_proj` requires a single-threadgroup 2048×2048
gated NVFP4 GEMV inside it. Medium risk, self-contained, and it does not touch attention.

C2 (fuse `attn` into `o_proj`, E4) buys the same 55.5 µs but has to fuse across the
sliding-window / full-attention split, GQA, and the SDPA vector kernel family. Same refund,
much worse risk. Prefer C2′.

#### C4 — the merged-9-slot design refunds **zero** barriers. Recommend dropping it.

This was a must-answer item. Trace proof: `down+residual` appears with RAW producers
`{routed_swiglu, router_top8, shared_swiglu}` **already collapsed onto one barrier** (E7), and
E6's barrier fires at whichever of its three consumers is encoded first. Merging the shared
expert into the routed gather-GEMM as a 9th slot therefore cannot shorten the chain at either
end — it removes one dispatch (0.12 µs × 39 = 4.8 µs/step, 0.07%) and no fence.

There is also a recorded prior measurement pointing the same way:
`LagunaRuntimeModel.swift:7833-7850` notes that encoding the shared QMV *after* the routed
dispatches already overlaps, and that moving it earlier **regressed +0.10 ms/step**. The
scaffolding is present but unused: `mergedSharedActivated` (`:10035`) is never assigned, and the
`shared_slot = 8` trick lives at `:7871`, `:7887`, `:7890-7899` with its epilogue at
`:7950-7965`.

**Advisor recommendation: drop the merged-9-slot design.** Its entire value under the adopted
"barriers removed" criterion is 0.07%, against medium implementation risk in the MoE path.

C3 and C5 are the same story with lower risk and the same zero refund. C6 (lm-head cascade) is
on the chain but only fires once per step, so −4 barriers −6 dispatches = 5.9 µs, 0.09%.

### §2.4. Shortlist

Detection bar on this host is ≈ **80 µs/step** (3σ of the paired decode measurement).

**No single fusion clears the bar.** C1a and C2′ are 55.5 µs each. But disjoint chain
contractions are additive — removing E2 and E5 takes the sparse chain from 7 edges to 5 — so:

| bundle | Δbarriers | Δdispatches | µs/step (M4) | score (M4) | ranked-M5 range |
|---|---|---|---|---|---|
| **A = C1a + C2′** | −78 | −78 | **111.0** | **1.70%** | 56–111 µs → 0.86–1.70% |
| **B = C1b + C2′** | −78 | −117 | **115.8** | **1.77%** | 59–116 µs → 0.89–1.77% |
| C1a alone | −39 | −39 | 55.5 | 0.85% | 28–56 µs → 0.43–0.85% |

Bundle A clears the detection bar with margin and is the recommended next decode round.
Ranking by refund per unit risk:

1. **C1a**, then C1b once C1a is landed and measured (same edge, incremental dispatch win).
2. **C2′** — the second chain edge, additive with C1a.
3. C2 — same refund as C2′, materially higher risk. Only if C2′ proves impossible.
4. C3 / C4 / C5 / C6 — all ≤ 6 µs/step. **Do not spend a round on any of them.**

Ceilings, for calibration:

- Removing *every* charged barrier: 321 µs/step (low) to 336 µs/step (ranked), i.e. 3.9–4.1% of
  the 8.18 ms step → **4.9–5.1% of score**, M4-priced. That is the whole barrier tax, and it is
  not reachable — a serial model needs serial fences.
- A realistic floor of 4 edges per sparse layer (7 → 4) is −117 barriers = **−152 µs/step** plus
  the dispatch savings.

**Additivity caveat, to keep attached to any quote of these numbers:** the 1.3003 µs/barrier
coefficient was fitted on barrier *additions*. Removal symmetry currently rests on a single
point — sibling #269's 117 removed dispatches predicted 166.5 ± 3.0 µs against a measured
144.23 ± 23.00 µs, agreeing at **0.96σ**. That is one validation, not a law. **Treat the first
bundle that lands as a re-validation of the removal side**, and expect the possibility that
removal recovers less than addition costs.

---

## §3. The three-arm falsification test

The refund rule's weak point is absorption: if MLX would reclaim a free ride elsewhere when an
edge disappears, the refund shrinks. The test was to vary the command-buffer boundary placement
and watch whether serial depth or only absorption changes.

| arm | control | dispatches | cb switches | charged barriers | total fences | sparse fences/layer |
|---|---|---|---|---|---|---|
| 1 | `MLX_MAX_*=50` | 406 | 44 | 247 | 291 | 7.103 |
| 2 | `MLX_MAX_*=100000` | 406 | 44 | 247 | 291 | 7.103 |
| 3 | `DARKBLOOM_STARTUP_MEMORY_PROFILE=full` | 406 | 29 | **258** | 287 | **7.000** |

Arms 1 and 2 are byte-identical because the env vars never reach MLX (§2.1) — that is the arm's
real finding. Arm 3 is the working control and it comes out the way the refund rule needs:
**charged barriers move by +11 while total fences move by −4 and depth is flat at 7.** Serial
depth is a property of the graph, not of the buffer budget; the budget only decides which fences
are free. And under the ranked budget, the two shortlisted edges have no free rides left to
reclaim.

---

## §4. Transfer to the ranked machine

What transfers:

- **Structure.** 406 dispatches, the 7-edge sparse chain, the off-chain riders, the collapse of
  multi-producer and multi-consumer edges. These are properties of the MLX graph and the Laguna
  runtime, not of the GPU.
- **The ranked profile is the one measured in arm 3.** The M5 has 128 GB and therefore selects
  `full` (320 MB / 128 ops), so 258 charged barriers and 7.000 fences/layer is the ranked-side
  structure, and the absorption sits on E7 and E1 rather than E3/E5.

What does not transfer:

- **Every µs and every % in this document is M4-priced.** The M5 transfer range from r1 is
  `[M4_total / 1.98, M4_total]`, which is why §2.4 quotes ranges.
- **No `_nax` evidence exists here.** This host reports Apple GPU generation 16 and never selects
  the `_nax` prefill kernels the ranked M5 uses. Nothing in r2 is evidence about an `_nax`
  change. The census is a decode-path structural result and decode does not depend on the
  `_nax` selection, but the caveat stands for anyone reusing these traces.
- Threadgroup geometry can change sign across core counts; nothing here recommends a geometry
  change.

**One correctness warning for whoever implements C1.** The upstream-equivalence oracle is blind
to the fused-weight family: `Sources/MLXFastModel/LagunaUpstreamEquivalence.swift:74-90` bypasses
the weight cache, and `prepareFusedRuntimeWeights()` (`LagunaRuntimeModel.swift:11016`) has
exactly one caller, `Sources/MLXFastModel/LagunaRuntimeWeights.swift:637`, which the oracle does
not reach. So `LagunaUpstreamEquivalence` **will pass a broken fused QKV bank.** The 64-step
drift tripwire and the teacher-forced goldens carry the whole correctness load for C1. Run them.

---

## §5. Scope and budget

r2 changes no submitted path. Verbatim, against the assigned base:

```
$ senpai/validate-assignment-scope.sh 13f9b6f7960bf1872465f2e7950685d52ccf2e48 \
    Sources/MLXFastModel/LagunaRuntimeModel.swift Sources/MLXFastModel/LagunaRuntimeWeights.swift \
    Sources/MLXFastTransform/Transform.swift Sources/MLXFastTransform/AffineMetadataCoding.swift
assignment scope OK: 4 submitted path(s) against BASE_SHA=13f9b6f7960bf1872465f2e7950685d52ccf2e48

$ senpai/check-editable-budget.sh 13f9b6f7960bf1872465f2e7950685d52ccf2e48
editable budget OK: current=2950855/3000000 bytes headroom=49145 growth=0/262144 files=142 (base=142)
```

The four paths above are the ones a C1 implementation would touch, pre-validated so the next
round does not discover a scope problem after building.

**Budget warning, and it is tight.** Total-surface headroom is **49,145 bytes**. That binds
before `LagunaRuntimeModel.swift`'s own 55,952-byte per-file headroom. A new NVFP4 fused
norm+QKV kernel (route 1) must fit in 49 KB **or land together with a deletion**. This is worth
planning before writing the kernel, not after.

---

## Reproduction

```bash
# apply the research-only trace instrument
git apply research/fern_tax_sitetrace.patch

# build the worker (~59 s)
mkdir -p .build-worker/clang-module-cache
CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions \
  --scratch-path .build-worker --product mlxfast-runtime-worker

# default (low) profile census
python3 research/fern_tax_sitetrace.py --steps 3 --out research/artifacts/fern_sites

# ranked (full) profile census
DARKBLOOM_STARTUP_MEMORY_PROFILE=full \
  python3 research/fern_tax_sitetrace.py --steps 3 --out research/artifacts/fern_sites_fullprofile

# reduce either trace
python3 research/fern_tax_sitecensus.py research/artifacts/<prefix>.trace

git checkout -- Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp \
                Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.h
```

Each census arm is ~43 s of wall time after the build. No ranked slot and no benchmark lock are
required; the census does not run the trusted harness (and cannot, with the patch applied).

---

## Caveats

1. All timing constants are M4, from r1. §2.4 quotes M5 ranges, never M5 points.
2. Removal symmetry of the 1.3003 µs/barrier coefficient rests on one cross-check at 0.96σ. The
   first landed bundle should be read as a re-validation.
3. The census reads the last complete 406-dispatch decode window of a 3-step run. Step-to-step
   structure was stable across the sampled steps, but this is not a distribution over many steps.
4. Charge rates per edge are profile-specific. Anyone quoting "E5 is 27/39 charged" must say which
   profile; under the ranked profile it is 39/39.
5. C1 route 2's bandwidth cost (1.89× QKV bank bytes) is an arithmetic estimate from bits per
   weight, not a measurement. It must be measured before route 2 is adopted.
6. The trace instrument perturbs nothing measured here (structure, not time), but it does change
   the vendored-Metal fingerprint and so cannot be used for a timed harness run.
