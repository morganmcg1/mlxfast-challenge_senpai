# PR #143 / maple-nezuko / Round 22 H4 — checkpoint expert-slab dedup + scale-plane census

**Assignment** `maple-2026-08-06m-expert-slab-dedup`, revision `r1`.
**BASE_SHA** `2443984f8de7544170a256ad854a22fcf18c8460`.
**Host** M4 Pro `Mac16,11`, 48 GiB, Apple GPU generation 16 (cannot execute `_nax`).
**Scored bytes changed: zero.** `senpai/check-editable-budget.sh "$BASE_SHA"` →
`current=2921747/3000000 headroom=78253 growth=0/262144 files=142 (base=142)`.
**Receipts spent: zero.** Everything below is offline CPU work on the checkpoint
plus a read of the public submission feed.

**Citation convention.** Bare `:NNNN` line numbers resolve against
`research/CURRENT_RESEARCH_STATE.md` **at BASE_SHA `2443984f`** (6,874 lines).
That file was rewritten to 368 lines at `3425246a`, so on the newer base the same
line numbers resolve against `research/RESEARCH_STATE_ARCHIVE_through-round-21.md`
instead. The two are byte-identical — SHA-256
`ececc5826184ae44fed8ac53866b09f2b29f75c3f73410c27770860a952b421b` for both — so
every citation below is resolvable from either base, and the archive rewrite lost
nothing. `research/PREFILL_LEDGER_INSTRUMENT.md` likewise exists only from
`3425246a` onward.

---

## 1. Verdict

**H4 is killed.** The gate was "kill if the routed-expert duplicate rate is
below 5%".

> **Routed experts: removable slabs 0 / 59,904 = 0.0000%. Removable bytes 0 B =
> 0.0000% of 16.45 GiB.**

Exhaustive, not sampled. Confirmed three independent ways (§3) and carrying a
built-in positive control that proves the detector works.

The pre-authorised pivot therefore applies: I do **not** fall back to H6, and
§8 hands over the two things `research/PREFILL_LEDGER_INSTRUMENT.md` still
needed before R1 can be dispatched — the wall-time budget (delivered, §7) and
the Step 0 elision check (specified and blocked on one scope question, §8.2).

Alongside the kill, four adjacent levers are now **permanently closed** with
numbers rather than opinion (§4), one is closed by a reprice that supersedes my
own earlier framing (§5), and H6 is refuted from source reading before anyone
spends a round on it (§6).

---

## 2. What the instrument is

`research/nezuko_slab_census.swift` — ~600 lines, research-only, offline,
CPU-only. No GPU, no benchmark lock, no thermal gate, no receipts. Builds
standalone in ~2.9 s (`swiftc -O`, no `Package.swift` edit, since manifests are
not editable). CryptoKit SHA-256, 128-bit digest-prefix class keys, `mmap`,
`DispatchQueue.concurrentPerform`. Modes `probe | full | rows | entropy`.

Column schema, the soundness argument, the declared sampling per mode, and the
regeneration commands are in `research/artifacts/README.md`. The four points
that make the *negative* result trustworthy:

1. Prefix screening can only over-count duplicates, never miss one, so `probe`
   is a sound upper bound and `full` removes the bound entirely.
2. The class key includes slab length, so a truncated probe cannot merge slabs
   of different sizes.
3. Every duplicate class is re-verified with `memcmp`, so the result does not
   rest on hash collision resistance.
4. The enumerator proves, before hashing, that 60,582 slabs occupy 60,582
   distinct `(shard, offset)` sites with zero repeated, zero overlapping and
   zero out-of-range slabs. **A dedup rate is trivially manufacturable by
   hashing the same bytes twice; this check is what rules that out.** It passes.

### Checkpoint structure established on the way

`weights/`, 5 safetensors shards, 912 tensors, **60,582 slabs, 20.08 GiB =
21,561,408,512 B**. `hidden_size=2048`, `intermediate_size=8192`,
`moe_intermediate_size=512`, `num_experts=256`, `num_experts_per_tok=8`,
40 layers with `mlp_only_layers=[0]` → **39 sparse layers**,
`num_key_value_heads=8`, `head_dim=128`, `sliding_window=512`,
`vocab_size=100352`, `quantization={bits:4, group_size:16, mode:nvfp4}`,
`router_aux_loss_coef=0`, `tie_word_embeddings=False`.

Experts are **stacked**: `mlp.switch_mlp.{gate,up,down}_proj.weight` is U32
`[256, R, C]` and `.scales` is U8 `[256, R, C]`, so one expert is a sub-range.
Per expert × layer × role: 524,288 B mantissa + 65,536 B scales. Hence
39 × 256 × 3 = **29,952 mantissa + 29,952 scale = 59,904 routed slabs =
16.45 GiB = 81.9353% of the checkpoint**. Row bytes give the shapes:
`gate/up_proj` `[512, 2048]` (1024 B/row), `down_proj` `[2048, 512]` (256 B/row);
scale rows 128 B and 32 B.

**Representation caveat, stated up front.** Attention weights are BF16 on disk
and are re-quantized to NVFP4 g16 at load, so this census says nothing about the
runtime attention representation. Routed expert weights *are* NVFP4 on disk, so
the census is valid evidence for the MoE arm — which is the arm H4 was about.

---

## 3. H4 result in detail

`research/artifacts/nezuko_slab_census_full.md`, `…_rows.md`, `…_entropy.md`.

### 3.1 Whole-slab identity, exhaustive (`--mode full`, 100.0000% of bytes, 0.94 s)

| quantity | value |
| --- | --- |
| routed-expert removable slabs | **0 / 59,904 = 0.0000%** |
| routed-expert removable bytes | **0 B = 0.0000%** |
| whole-checkpoint removable | 38 slabs = 38.00 KiB = **0.0002%** of 20.08 GiB |
| distinct classes | 60,544 of 60,582 |
| classes with more than one member | **1** |

The single duplicate class is `router.e_score_correction_bias`: all **39** sparse
layers byte-identical at 1024 B, `memcmp=OK`, 0 mismatches,
`distinct-offsets=YES`, 0 aliased classes. Members span shards 1–4 at 39
genuinely distinct sites (`L9@s1+185173979` … `L32@s4+4313958778`; the closest
pair, `L39@s4+3624451450` and `L31@s4+3624452474`, is adjacent but disjoint).
Per the advisor's instruction I checked the claimed duplicate pair offsets
rather than trusting the class count: they are distinct. This class is the
instrument's positive control.

Degenerate slabs: 39 all-zero (exactly those 39 bias slabs), 0 constant-byte
non-zero.

### 3.2 Prefix screen (`--mode probe`, 4096 B, 236.24 MiB = 1.1489%, 2.36 s)

60,544 classes, 1 class with more than one member, routed removable 0 =
0.0000%. Identical to the exhaustive answer, which is the expected relationship
(the screen is an upper bound) and a cheap consistency check on the enumerator.

### 3.3 Sub-slab row identity (`--mode rows`, 4.70 s)

Kills the "maybe whole slabs differ but rows repeat" variant. Routed roles are a
1-in-8 slab sample, exhaustive within a sampled slab. Every role is net-negative
once the indirection table is paid for at 4 B/row:

| role | rows | duplicate rows | bytes removable | index cost | net |
| --- | --- | --- | --- | --- | --- |
| `routed.gate_proj.weight` + `up_proj.weight` | 638,976 | **0** | 0 | — | 0 |
| `routed.down_proj.weight` | 2,555,904 | **0** | 0 | — | 0 |
| `lm_head.weight` | 100,352 | 64 (0.0638%) | 262,144 B | 401,408 B | **−139,264 B** |
| `routed.down_proj.scales` | — | 218 (0.0085%) | 6,976 B | 10,223,616 B | **−10.2 MB** |
| `shared.down_proj.scales` | — | 1 | 32 B | 319,488 B | **−319,456 B** |
| all other roles | — | **0** | 0 | — | 0 |

### 3.4 Near-duplicate line item — strictly separate and non-gating

Reported separately, as the advisor asked, and it does **not** feed the gate.

> **0** routed mantissa slabs share their bytes with any other mantissa slab.

So the "identical mantissa, differing scales" variant of H4 is moot: there is no
mantissa pair to reuse in the first place. This is a stronger statement than the
whole-slab count, because it holds even if scales were allowed to differ freely.

### 3.5 Pre-registered locality caveat, which would have applied even on a win

Recorded before the census ran, so it is not post-hoc: a 10% dedup rate would
*not* have implied a 10% DRAM saving. On M5 the L2/SLC is tens of MB while one
layer's expert bytes are ~453 MB, so two experts sharing a slab only save a
fetch if they are scheduled adjacently. Any future dedup claim in this family
owes a scheduling argument, not just a duplicate count.

---

## 4. Four adjacent levers closed with numbers

These are the reusable part. Each one would otherwise have cost a round.

### 4.1 A uniform 4-bit routed scale LUT is **impossible**

`--mode entropy` scans the `.scales` roles exhaustively.

| role | byte H | distinct codes | narrowest fixed width |
| --- | --- | --- | --- |
| `routed.down_proj.scales` | 2.4723 | **42** | 6 bit |
| `routed.gate_proj.scales` | 2.6002 | **50** | 6 bit |
| `routed.up_proj.scales` | 2.6112 | **57** | 6 bit |
| `shared.{down,gate,up}_proj.scales` | — | 35 / 37 / 40 | 5 bit |

Per-slab, over 9,984 slabs per routed role: max codes **35 / 38 / 41**, p50
**13**, p99 22 / 26 / 22, and **slabs exceeding 16 codes = 705 / 2,247 / 1,301**.
Shared (39 slabs): max 31 / 30 / 31, p50 25 / 27 / 24, over-16 39 / 36 / 36.

This refutes, before anyone spends a round, any direct port of maple-frieren's
"4-bit lane-major scale plane" (research idea 7,
`research/CURRENT_RESEARCH_STATE.md:6555`, `:6646`) from the attention scale
plane to the routed scale plane. The attention plane is *manufactured at load by
our own quantizer*, so its alphabet is ours to choose; the routed plane ships in
the checkpoint and its alphabet is not. It also closes open research idea (a) at
`:175-176`.

Only 6-bit is available, and §5 shows 6-bit is worth `+0.167%` post-#72 — under
the `0.243%` 2σ floor. Dead.

### 4.2 The routed *mantissa* compression family is closed permanently, on two independent grounds

**Airtight ground (fixed width).** All 16 nibble codes occur in every routed
mantissa role (256 distinct byte codes each). A gather-GEMM needs random access
into the plane, so the only implementable class is a fixed-width recode — and no
fixed-width recode of a full 16-code alphabet exists. **Exactly 0% is available.**

**Information-theoretic ground (entropy).** Pooled zeroth-order nibble entropy
is 3.9417 / 3.9444 / 3.9527 bits of 4 (down / gate / up) = 98.5% of maximum, so
the best-case saving from *any* memoryless lossless code is +1.46 / +1.39 /
+1.18%. On 490.74 MB/step of routed mantissa traffic that is ≈6.58 MB/step, and
the byte-price law gives `15.28 × 6.58 / 700.3 =` **≤ +0.144% of score** — and
entropy coding is not randomly addressable anyway.

**Honest limitation.** Pooled entropy bounds a single *global* memoryless code
exactly. A *per-slab adaptive* coder is bounded by the average per-slab entropy,
which I did not measure. That sub-family is closed by the fixed-width argument
above, not by the entropy number. I am flagging this rather than letting the
entropy figure be read as more general than it is.

Whole-checkpoint headline: best-case memoryless lossless size 18.25 GiB, so the
**maximum saving from any memoryless lossless scheme is +9.09%**, and it is
dominated by the scale planes, not the mantissa. For contrast, every BF16 /
dense / attention / lm_head / embedding / `router.weight` role has 256 distinct
codes and nibble H ≈ 3.55–3.62 → +9.5–11.2% headroom — i.e. the *compressible*
bytes are the ones we do not read in the hot loop.

### 4.3 Zero-clustering in the routed mantissa is bounded at ≤1 row per role

Closes open research idea (b) at `:175-176`. Zero all-zero slabs exhaustively,
plus zero duplicate rows in a 12.5% slab sample — and any two all-zero rows
would necessarily have collided as duplicates. So there is at most one all-zero
row per routed mantissa role. There is no zero structure to skip.

### 4.4 `router.e_score_correction_bias` is all zeros in all 39 layers

Byte entropy 0.0000, **1 distinct code**, consistent with
`router_aux_loss_coef = 0`. The kernel does consume it:
`router_keys[…] = laguna_router_key_ordinal(-(score + float(correction_bias[…])))`.
Removing it is **bit-exact**: adding `+0.0` is the identity, `-0.0 + 0.0 = +0.0`
changes neither value nor top-k ordering, and router scores are non-negative.

But it is ~1 KB/step out of 1,794 MB/step, and dispatch-count reduction in this
region is already falsified, so **EV ≈ 0**. Logged as a micro-simplification
candidate only. I am explicitly *not* proposing it as a round.

---

## 5. Reprice that supersedes my own earlier framing: the scale-plane LUT lever is dead

I have to correct the natural reading of §4.1. **PR #72 is already merged at
`9e8c719f`** (`research/CURRENT_RESEARCH_STATE.md:1349`, `:1360-1398`) and the
routed NVFP4 scale plane is **already halved at load time**.

Mechanism, for the record: 985,300,992 even-byte pairs with exactly 168
exceptions (one per tensor, always flat pair 0) = 99.999983% equality, against a
23.24% odd-index control; provable from
`Vendor/mlx-swift/…/kernels/fp_quantized.h:2192-2194`, which predicates the
scale write on `tidx.x` under 1-D dispatch (`quantized.cpp:2455-2478`,
`per_thread=1`) with no `_nax` override. Shipped as
`[128-B patch header][even-byte halved plane]` in `prepareFusedRoutedGateUp()`
off `prepareFusedRuntimeWeights()` (`LagunaRuntimeModel.swift:11052`), untimed,
`scale_row_bytes 32→16`, `allowedFlatPairs` `[0,16]` for gate/up and `[0]` for
down.

Consequences for my numbers:

- My census read the **on-disk, un-halved** plane. Runtime routed scale traffic
  is **30.67 MB/step**, not 61.34.
- The pairs are byte-identical, so the halved plane has the **same alphabet** —
  every per-slab count in §4.1 transfers unchanged.
- Uniform 6-bit LUT on the halved plane: 30.67 × 0.25 = 7.67 MB →
  `15.28 × 7.67 / 700.3` = **+0.167%**, below the `0.243%` 2σ floor.
- Mixed 4/6-bit (weighted savings 48.23 / 44.37 / 46.74%, average ≈46.4%):
  30.67 × 0.464 = 14.23 MB → **+0.310%**, below the `0.61%` acceptance bar — and
  it needs divergent per-slab mode dispatch inside the hot routed NVFP4 kernel.

Independently closed elsewhere: `:6334` (maple-frieren #71) closed routed-QMV
byte framing because the kernel already runs at 108.1% of the measured 260.2
GB/s M4 ceiling (partly cache-served), noting "the scale plane runs at ≈100%
line utilisation, which closes repacking it (§0.9.22)", where §0.9.22 is the
UNFALSIFIABLE-RIDER RULE at `:3864`.

**So §4.1's value is purely as a refutation, not as a lead.** I am stating this
loudly because a reader who stopped at §4.1 would otherwise queue a +25% scale
compression round that is worth +0.167%.

---

## 6. H6 pre-mortem refutation, from source reading, zero receipts

H6 was the designated fallback. It is moot given the pivot, but the refutation
is cheap to record and prevents a future re-proposal.

H6 proposed transposing the router weight because the `residual_rms_router`
access pattern "is not float4-coalesced". **That premise is factually false.**

The family is a JIT `MLXFast.metalKernel`,
`laguna_residual_rms_router_bf16_2048_rpg<N>_{keys_v1|v2}` — no `.metal` file, no
`mlx-generated` twin, no AOT metallib entry. Everything is in
`Sources/MLXFastModel/LagunaRuntimeModel.swift`: source builder
`lagunaResidualRMSNormRouterSource(rowsPerGroup:)` 853–918, template body
921–982, bit-exactness comment 607–652, kernel dict (rpg ∈ {1,2,4,8,16,32,64})
991–1010, wrapper 1055–1096, call sites 10351–10369 (decode) and 10447–10465
(terminal prefill row), gate `DARKBLOOM_FUSED_RESIDUAL_RMS_ROUTER` 532–533
(default ON), `DARKBLOOM_ROUTER_ROWS_PER_GROUP` default 8 at 604–636.

I verified the indexing myself. Constants at 921–928: `axis_size=2048`,
`n_reads=4`, `simd_size=32`, `block_width=128`, `router_blocks=16`. The body
loads `vec<bfloat,4>` at
`router_weight + router_row*axis_size + column + u*block_width` with
`column = simd_lane*n_reads`. So lane `L` reads elements `[4L, 4L+3]` = 8
contiguous bytes; 32 lanes = **256 contiguous bytes per load**; the 4-deep hoist
gives **1024 contiguous bytes per simdgroup per iteration** with 4 loads in
flight. The router weight is `[256, 2048]` BF16, plain row-major contiguous,
1 MiB per sparse layer, each byte read exactly once. It is already perfectly
coalesced.

A transpose would additionally have to either regroup the FP32 accumulation —
the kernel deliberately replicates MLX gemv lane→column ownership
(BM4/BN1/SM1/SN32/TM4/TN4; lane `l` owns columns `4l + 128i`; strict `(block, i)`
order; one private FP32 accumulator; a `simd_shuffle_down` ladder 16→1; one BF16
round), and the comment at 607–652 states that regrouping forfeits the hidden
exact-token gate — or, if left lazy, pay a **1 MiB copy per call**
(`Vendor/mlx-swift/…/backend/metal/custom_kernel.cpp:38-47`).

Provenance confirms there is nowhere to hide the transpose offline: the router
weight is consumed straight from the checkpoint with **no offline transform**.
`Sources/MLXFastTransform/Transform.swift:69-76` passes `mlp.gate.weight`
byte-for-byte; validation only at
`LagunaCheckpointValidation.swift:261-275,382-385` and
`LagunaRuntimeWeights.swift:148-160`; the operand is the untouched
`LagunaRuntimeMoEGate.weight` (`@ParameterInfo(key:"weight")` 9466,
`zeros([numExperts, hiddenSize])` 9472, passed directly at 10363 / 10460). No
`prepareRouter*` exists (`prepare` sites: 5467, 5494, 5585, 5612, 8248, 8286,
9881, 10675, 11011). The same array serves prefill via `x.matmul(weight.T)`
(9480–9481, reached from 10003). No transposed or alternate router layout exists
anywhere in the tree.

The motivating metric is also already retired: the 61.8% saturation row is
SUSPECT and closed at reprice (`:3747-3785`, `:6336`) — 1.86% of score sits
under the 0.278% MDE, and reopening needs a mechanism moving **≥27.8 MB/step**.
The router moves 40.9 MB/step in total and a transpose removes **zero** bytes.
The knob space is a documented measured null: `notes/exp-rpgrouter.md` has rpg1
vs rpg8 at −5 µs/step inside a ~18 µs floor, rpg4 / rpg2 at +25 / +35 µs, rpg=64
as a null control, and an explicit "Do not re-sweep."

Two *real* inefficiencies live there, both about ownership and occupancy rather
than layout, and both outside my arm: a **32× redundant residual-add + RMSNorm**
across threadgroups (only `tile == 0` writes `summed` / `normalized`, 945–947 /
960–962), and **8 of 16 simdgroups idle** during the router phase
(`rowsPerThread=1`, `activeSimdGroups=8`, `tiles = 256/8 = 32`, grid
`(16384,1,1)`, threadgroup `(512,1,1)`, 4,228 B of threadgroup memory). All 16
simdgroups *are* needed for the 2048-wide norm reduction, and 512 threads plus
`n_reads == 4` are documented non-knobs (1073–1079) load-bearing for FP32 RMS
bit-exactness.

---

## 7. Delivered: the wall-time budget the advisor asked for

The advisor's latest note said the real killer for the receipt-channel
instrument is **wall time**, not the speedup floors, and that I had been given no
budget. Instrument: `research/nezuko_feed_wall_census.py`, output
`research/artifacts/nezuko_feed_wall_census.txt`, over 1,082 feed receipts that
carry `officialMetrics`.

### 7.1 Last ~20 successful receipts (asked for directly)

| field | median | min | max |
| --- | --- | --- | --- |
| `benchmark_wall_seconds` | **52** | 45 | 54 |
| `correctness_seconds` | **39** | 36 | 39 |
| `timed_benchmark_seconds` | **45.5** | 39 | 47 |
| `prefill_seconds_per_token` × 512 | 97.92 ms | 97.19 | 100.13 |
| `decode_seconds_per_token` | 4.951 ms | 4.908 | 5.188 |

Whole population (n = 1,082): wall med 46 / p90 48 / max **54**; correctness med
36 / p90 37 / max **41**; timed med 39 / p90 41 / max **47**. `preflight_seconds`
≈ 1.4e-4, negligible.

### 7.2 Methodological warning — do not regress on the pooled feed

A naive pooled OLS returns **negative** slopes:

```
benchmark_wall  = 58.075 − 0.08988*prefill_ms − 0.55808*decode_ms  (rmse 2.85)
correctness     = 50.592 − 0.14226*prefill_ms − 0.00759*decode_ms  (rmse 2.55)
timed_benchmark = 51.345 − 0.04439*prefill_ms − 1.49102*decode_ms  (rmse 2.96)
```

i.e. "slower candidates finish sooner". The cause is **era confounding, and the
feed hands us the key to prove it**: `harness_hash`, together with
`checked_steps` and `case_count`. Stratifying, the 2026-07-24/26 generation has
`checked_steps=512`, `case_count=7`, `correctness≈23`, and holds *all* the
slowest candidates (D up to 13.60 ms/step); the current generation has
`checked_steps=1344`, `case_count=11`, `correctness 36–39`, and holds only fast
ones. The wall fields are also integer-quantized, and inside a single
`harness_hash` group `correctness_seconds` is frequently *exactly constant*. So
no usable slope exists at all, in either direction. **Any future feed-mining
analysis must stratify on `(harness_hash, checked_steps, case_count)` first.**
That is the reusable lesson, and it is a trap I nearly fell into myself.

### 7.3 The answer, by envelope rather than by model

Restricting to the **identical current correctness configuration**
(`checked_steps=1344`, `case_count=11`) still spans P 97.4 → 137.8 ms (1.41×) and
D 5.10 → 9.83 ms/step (1.93×). Within that band, wall time is *set by harness
generation, not by candidate speed*: the slowest candidates (P 128–138, D
9.5–9.8) gave `corr=36`, `timed=30`, `wall=42–43`, while today's fastest (P 97.4,
D 5.10) give `corr=36`, `timed=38–41`, `wall=45–48`.

R1 (`routed_gather_gemm` ×2, m=1) projects to **P ≈ 137.9 ms, D ≈ 6.90 ms/step**.
Both land *inside* the already-measured envelope, so no extrapolation is needed:

| slice, all under `checked_steps=1344` | n | max wall | max corr | max timed |
| --- | --- | --- | --- | --- |
| receipts with prefill ≥ 137.9 ms | 24 | **47** | 38 | 40 |
| receipts with decode ≥ 6.901 ms/step | 266 | **48** | 41 | 41 |
| all 1,082 receipts, any era | 1,082 | **54** | 41 | 47 |

**Wall-time risk for R1: LOW.** No receipt slower than the probe has ever
exceeded 48 s of `benchmark_wall_seconds`, and the all-time maximum over 1,082
receipts is 54 s — reached at the *fast* end, in the current era. The measured
phases are dominated by the fixed baseline arm (S_base ≈ 190.6 ms, T_base ≈
12.37 ms/step, i.e. already ~2× slower than the probe would be) and by fixed
setup, not by the candidate arm.

Corollary worth recording: since `benchmark_wall_seconds` never exceeds 54 s
while a measure job occupies the shared slot for ~35 min, the 49 `timeout`
deaths in the feed death census cannot be measure-phase timeouts — they are
build or queue timeouts. An honest candidate-arm slowdown does not touch that
risk.

**Where the envelope argument stops.** The instrument spec's design ceiling of
"total injected prefill ≤ 70 ms" would put P at ~168 ms, which exceeds the
1344-era observed maximum of 137.8 ms (it has only been observed under the
smaller 512-step configuration, at `wall=36`). So: R1 at m=1 and the m=8
small-family bundle (< +15 ms) are inside the measured envelope; any bundle
pushing injected prefill past ≈ +40 ms leaves it and would need the mechanistic
bound instead. **Stage accordingly — this is a second, independent reason not to
batch R2/R3 into R1.**

### 7.4 Receipt-channel field availability, verified

Verified directly against the three archived official receipts
`research/m5-calibration/{A_f8502e12,B_71586bcf,C_f3cda678}.json` (C nests under
`submission/officialMetrics`). All present: `prefill_seconds_per_token`,
`decode_seconds_per_token`, `baseline_prefill_seconds_per_token`,
`baseline_decode_seconds_per_token`, both speedups, both floors at 0.95, both
`passed_*_floor` true, `benchmark_wall_seconds`, `correctness_seconds`. Example
A: `prefill_seconds_per_token = 0.00019066845703125` (× 512 = 97.6 ms, matching
S0 = 97.89 ms) and `decode_seconds_per_token = 0.005133115890625`.

This confirms the advisor's point that **one receipt buys two ledger rows**: the
raw candidate-arm prefill *and* decode seconds-per-token are published
independently, so a both-phase family such as `routed_gather_gemm` returns both
costs from a single injection. The decode residual `T − Σx̂` is therefore
obtainable at no extra receipt cost, and it is the decode analogue of the
prefill 31.28 ms — if it is large, the "decode is near-exhausted at +2.85%"
conclusion is a bandwidth-only argument that does not hold, and round 23 changes
shape.

---

## 8. Handover for the pivot

### 8.1 Cross-references and housekeeping

- **maple-frieren #142's rows-per-expert histogram is not present at my base**
  (`research/` has no `142`/`pr142` file at `2443984f`), so as instructed I am
  reporting that it landed late rather than rebuilding it. No rebuild is needed
  regardless: my census is disk-layout and byte-identity oriented, orthogonal to
  routing frequency, and with **one** duplicate class in the whole checkpoint
  there is nothing to join against. The closest pre-existing instrument is
  `research/route_histogram.py` (rows-per-expert spread at prefill, MMA row
  padding, per-expert threadgroup launches; routing is host-independent and
  transfers M4 → M5).
- **Archive false alarm cleared, with a hash.** `CURRENT_RESEARCH_STATE.md` shrank
  6,874 → 368 lines at `3425246a`, but the old content is preserved *byte-for-byte*
  in `research/RESEARCH_STATE_ARCHIVE_through-round-21.md`: both hash to SHA-256
  `ececc582…52b421b`. Nothing was lost. See the citation convention at the top.
- **Stale citations to fix.**
  `research/maple-nezuko-pr110-byte-price-ledger.md:446` and
  `research/maple-nezuko-byte-price.csv:2` cite the master ledger at
  `:5602-5612`; it now lives at `:5751-5761`.
- **Accounting gap CLOSED.** The 5.7% figure's denominator is **439.76 MB, not
  1794 MB**: 1794 − 802.16 (attention q/k/v/o) − 552.08 (routed MLP) = 439.76, of
  which 414.88 is allocated, leaving **24.88 MB unallocated = 5.66% ≈ 5.7%**
  (`research/maple-nezuko-pr110-byte-price-ledger.md:442-450`, originating at
  `research/maple-tanjiro-pr73-decode-kernel-census.md:404-429`). My earlier
  24.9 / 1794 = 1.39% is the correct *step* share; the two percentages answer
  different questions and 5.7% is never a share of 1794. Two loose ends I am
  flagging rather than asserting: (i) a ≈69.0 MB shared-expert omission —
  master-ledger line items sum to 1723.9 MB, and adding the shared expert
  (46.00 + 23.00, `maple-tanjiro-pr73-decode-kernel-census.md:414,416`) gives
  1792.9 ≈ 1794 — **arithmetic worth re-checking before citing**; (ii) `gate_sp`
  7.86 vs 5.53 MB/step is still unsettled (`:686-689`, `:963-965`, owed by #101),
  and 5.53 pushes the remainder to ≈27.2 MB. Also: the 260.2 GB/s ceiling is
  **M4 Pro measured** (`:6058-6065`), so 61.8% = 160.8/260.2; the **M5 ceiling has
  never been measured** (`KC2 = UNKNOWN`, lower bound ≈917–968 GB/s) and three
  competing M4→M5 constants are in circulation (×0.399, ×0.4266, ×0.501).

### 8.2 Shadow-execution over-attribution re-audit (owed to me, delivered)

MLX opens encoders `MTL::DispatchTypeConcurrent` (`device.cpp:548`) and inserts
barriers only on a real RAW/WAR hazard (`device.cpp:318-375`), so any "µs/step"
banked from a kernel timed **in isolation** may be partly or wholly hidden
behind a neighbour at ranked time. Line numbers are
`research/CURRENT_RESEARCH_STATE.md`.

**HIGH RISK — value inferred from isolated kernel duration or dispatch-count
reduction:**

1. `:5789-5805` — **the root generator.** The `µs/step` column is isolated
   per-call latency × n; the method at `:287` is `true µs = split µs/call − 1.33`,
   measured in a forcibly-serialised one-dispatch-per-command-buffer SPLIT arm.
   Items 2–9 inherit this defect.
2. `:6508` + `:6782` — **D-FUSE-GATESP, queue item 2, the largest exposure.**
   "213 µs of a 5.087 ms step is 4.19% of decode; recovering ~150 µs gives decode
   +2.95% ⇒ score +2.28%." Its census row at `:5798` sits at **2% of the byte
   ceiling**, so it is not byte-priced at all — the entire prize is isolated
   duration on the step's smallest and most hideable kernels.
3. `:6648` — `residual_rms_router` rpg8→rpg4/2, "106 µs/step M4"; occupancy-derived
   and already SUSPECT.
4. `:6649` — shared-expert K1, "65 µs/step M4"; same defect at 73% of ceiling.
5. `:6574` — "76.6 µs/step moving ~0.5 MB, i.e. entirely latency"; latency-only is
   maximally shadowable.
6. `:4994` — "2.2 µs/layer × 30 = 65 µs/step on M4"; partly mitigated by `:4984`
   (isolated 81 vs end-to-end 90 µs/step).
7. `:5056-5057` — "K3 = 21.63 µs/call × 39 = 843.6 µs/step", "K1 = −0.34 µs/call
   × 39 = −13.3 µs/step".
8. `:3139` / `:3486` "428 µs/step recoverable" → `:2121-2123` / `:3171` "≈390
   µs/step" → `:6663` "40–80 µs is recoverable"; struck, but the residue is still
   isolated-derived.
9. `:537` — "~+70 µs/step SHARED-after-ROUTED" ordering delta, explicitly lacking
   an overlap explanation.
10. `:6776` — D-STRAND, the inverse form: "hideable small-kernel pool is ≈0.59
    ms/step; hiding half is +4.4%". Magnitude already VOID.

**LOW RISK — bandwidth-law byte pricing or end-to-end paired A/B:** `:296`
(3.83 MB/step ⇒ ~7.0 µs/step), `:483` (25.7 MB ÷ 546.2 GB/s = 47 µs/step, plus a
real M5 receipt at +0.410%), `:1865`, `:4903` (net −4 µs/step), `:4957`, `:6557`;
end-to-end `:1710` (−97.9 µs/step) and `:2075` (~52 µs/step, ranked receipt).

**Counter-evidence that must be weighed before repricing anything above.**
`:1793-1794` records "`gpu_busy_sum == gpu_busy_union` to 1 µs ⇒ ZERO dispatch
concurrency in decode. Decode kernel times are strictly additive", repeated at
`:5811-5812` (6 ns) and `:4819`. If that transfers to M5 it largely defuses items
1–9. But it is **M4-only** and union-based, and `:2834` records
`MTL::DispatchTypeConcurrent` as unconditional. The smallest resolving read is
`research/maple-tanjiro-pr73-decode-kernel-census.md:178-180` (cited at `:535`).
I did not resolve this; it is a real open question and it gates the size of
queue item 2.

### 8.3 R1 Step 0 — specified, and blocked on one scope question

Step 0 is mandatory and free: on this M4 host, duplicating `routed_gather_gemm`
work must produce a prefill slowdown of roughly the predicted size, far outside
the ±0.73% local MDE, via one matched `./benchmark.sh --local-iterate` pair
(fresh baseline + fresh candidate, same quiet host, same thermal gate, GPU work
launched only through `run_training`). Rules: duplicate **pure work only**, never
double-append KV (duplicate the QKV GEMMs and the attention *reads*; the cache
write stays single), fold bit-exactly as `y = 0.5*(y1 + y2)` and never as
`y + (y2 - y2)`, document the probe openly in the PR and the submission note as
PR #34 r2 did, and **stop and report if there is no slowdown**.

**I have not run Step 0, because of a scope collision I should not resolve
unilaterally.** The cleanest injection point is Swift-level in
`Sources/MLXFastModel/LagunaRuntimeModel.swift`, which avoids
`Vendor/…/quantized.cpp` entirely — that file's relevant regions are fenced to
maple-tanjiro #138 (`~1634-1671`, `_nax` inner loop and tile geometry) and
maple-frieren #142 (`~1900-1930`, grid and dispatch construction). But my own
fence limits `LagunaRuntimeModel.swift` to the sort-time merge and indirection
lookup, and the routed-MoE call site is outside that. Both available doors are
someone else's room.

Requested decision, one of:

1. widen my `LagunaRuntimeModel.swift` fence to cover the routed-MoE call site
   for the duration of the probe (the probe is an unconditional, env-gated,
   openly-documented slowdown, so it cannot collide semantically with #138 or
   #142 — only textually); or
2. assign R1's Step 0 and injection to whoever already owns the routed-MoE call
   site; or
3. confirm that the probe should go in `quantized.cpp` and coordinate the
   textual overlap with #138 / #142.

Everything else R1 needs is now in hand: the wall bound (§7.3), the field
availability (§7.4), the floor headroom from the spec (prefill binds at S_cand ≤
195.6 ms, so ~+97 ms of headroom against a ~+40 ms injection; decode binds at
T_cand ≤ ~13.0 ms/step against ~+1.95 ms/step), and the estimator rule (regress
on the candidate arm's raw `prefill_seconds_per_token`, redraw sd 0.260%, never
`prefill_speedup`; `ns` is meaningless for a deliberately slowed probe).

---

## 9. Suggested follow-ups I did not implement

1. **Resolve the M4 additivity question** (§8.2 counter-evidence) before queue
   item 2 (D-FUSE-GATESP) is scheduled. It is a source read of
   `maple-tanjiro-pr73-decode-kernel-census.md:178-180`, not a receipt, and it
   decides whether a +2.28% claim is real or an isolation artifact. Highest
   value-per-effort item I found.
2. **Take the decode ledger row for free on every prefill probe** (§7.4). The
   decode residual `T − Σx̂` costs nothing extra and carries 75% of the score
   weight; the "decode is near-exhausted at +2.85%" conclusion currently rests on
   a bandwidth-only argument and has never been checked against a measured
   residual.
3. **Measure the M5 memory ceiling.** `KC2 = UNKNOWN` with three competing M4→M5
   constants in circulation (×0.399, ×0.4266, ×0.501) is a systematic error sitting
   underneath every byte-price estimate we make, including mine.
4. **Settle `gate_sp` 7.86 vs 5.53 MB/step** (owed by #101). It moves the
   unallocated remainder between 24.88 and ~27.2 MB, which is right at the
   ≥27.8 MB/step threshold that would reopen the 61.8% saturation row.
5. **Fix the two stale ledger citations** in §8.1 and re-check the ≈69.0 MB
   shared-expert arithmetic before it is cited again.
6. Micro-simplification only, EV ≈ 0: drop the provably all-zero
   `router.e_score_correction_bias` add (§4.4). Bit-exact, ~1 KB/step. Worth
   doing incidentally, never worth a round.

**Do not queue:** routed scale-plane LUT (§5, +0.167% / +0.310%, both under the
bar), routed mantissa compression in any form (§4.2, exactly 0% for fixed-width),
routed zero-skipping (§4.3), routed dedup at slab or row granularity (§3), and
the H6 router transpose (§6).
