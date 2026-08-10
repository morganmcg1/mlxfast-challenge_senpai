# R106-A — Decode byte composition: how much of `B` is quantisation metadata?

- PR: #615 · assignment `maple-r106-a-decode-byte-composition` · revision `r106-a-rev1`
- Base: `codex/mlxfast-maple-20260804-advisor` @ `0954002c16014a03091e1856cdf356fb0e6a3e38`
- W&B: <https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/2j6qgd7j> (`2j6qgd7j`, finished)
- Artifact: `research/artifacts/maple-tanjiro-r106a/decode-metadata-ledger.json`
- Instrument: `research/tanjiro_r106a_byte_ledger.py` (research-only; no submitted file changed)
- Official receipts consumed: **0**. No submitted-surface code was modified in this experiment.

## Verdict

**Quantisation metadata is 64,294,912 B/step = 3.8468 % of `B`.** Even if every
metadata byte were free, that is a ceiling of **+1.6156 % of `cs`** for the whole
axis. The *bit-exact addressable* fraction, using the one encoding at HEAD that
preserves an O(1) per-lane scale fetch, is **19,284,992 B = 1.1538 % of `B` =
+0.4846 % of `cs`**, and the **largest single component is 0.5926 % of `B`**.

The Stage-3 build gate required one REMOVABLE-BIT-EXACT component **≥ 1.2 % of
`B`**. The largest is 0.5926 %; the aggregate over all five metadata planes is
1.1538 %. **The gate does not open.** Preregistered nulls **N-A** (metadata
< 5 %) and **N-B** (the large remainder is not bit-exact) both fire. Per the
brief, the ledger is the full deliverable and no candidate was built.

Stage 1 also produced a correction to the accepted constant: **`B` is overstated
by 4,300,800 B (0.2573 %)** because the accepted census models `g_proj` as BF16,
while HEAD loads it as affine INT8 group-32.

## Price model (from the assignment)

```
T = B/BW + L          B = 1,671,402,432 B/step        B/BW = 2773.1 µs = 66.96 % of the 4141.5 µs M5 step
1 % of B  ≈ 27.73 µs/step ≈ +0.42 % of cs             1 % of cs = 65.67 µs/step
```

`cs` is the composite score. Because decode carries 75 % of the weight and
`B/BW` is 66.96 % of the step, the conversion 1 % of `B` → 0.42 % of `cs` is the
number every line below is judged against.

## Stage 1 — exact byte ledger for one decode step

Derived from `config.json` geometry plus the loaded representation in
`LagunaRuntimeWeights.swift` / `LagunaRuntimeModel.swift`, **not** from profiler
labels (Rule 82). Geometry: hidden 2048, 40 layers (layer 0 dense, 1–39 sparse),
30 sliding × 64 heads + 10 full × 48 heads, 8 kv heads, head_dim 128, window 512,
256 experts top-8, moe_intermediate 512, shared_expert_intermediate 512, dense
intermediate 8192, vocab 100,352, NVFP4 bits=4.

### Bucket split (bytes/step)

| bucket | payload | metadata | metadata % of `B` |
|---|---:|---:|---:|
| routed (gate+up qmv, router/RMS) | 368,050,176 | 20,447,232 | 1.2233 |
| routed+shared down + residual | 184,025,088 | 11,501,568 | 0.6881 |
| shared gate+up | 40,894,464 | 2,555,904 | 0.1529 |
| attention (qkv, oproj, `g_proj`) | 717,946,880 | 23,367,680 | 1.3979 |
| attention KV | 86,507,520 | 0 | 0 |
| dense (layer 0, BF16) | 100,663,296 | 0 | 0 |
| embeddings + lm_head | 102,760,448 | 6,422,528 | 0.3843 |
| activations (tail dispatches) | 1,958,848 | 0 | 0 |
| **total** | **1,602,806,720** | **64,294,912** | **3.8468** |

### Per-family reconciliation against the 205-dispatch ≥C40 list

25 families; **23 reconcile to the byte** (`delta = 0`).

| family | bucket | calls | payload | metadata | derived | Δ vs accepted |
|---|---|---:|---:|---:|---:|---:|
| `routed_nvfp4_swiglu_qmv_packed_top8keys` | routed | 39 | 327,155,712 | 20,447,232 | 347,602,944 | 0 |
| `routed_shared_nvfp4_down_residual` | routed+shared | 39 | 184,025,088 | 11,501,568 | 195,526,656 | 0 |
| `shared_nvfp4_swiglu_qmv_rows1_halved` | shared | 39 | 40,894,464 | 2,555,904 | 43,450,368 | 0 |
| `nvfp4_qkv_h64` | attention | 30 | 314,572,800 | 10,137,600 | 324,710,400 | 0 |
| `nvfp4_qkv_h48` | attention | 10 | 83,886,080 | 2,703,360 | 86,589,440 | 0 |
| `oproj_act_h64` | attention | 30 | 251,658,240 | 7,925,760 | 259,584,000 | 0 |
| `oproj_act_h48` | attention | 10 | 62,914,560 | 1,986,560 | 64,901,120 | 0 |
| `gate_sp_h64` | attention | 30 | 3,932,160 | 491,520 | 4,423,680 | **−3,440,640** |
| `gate_sp_h48` | attention | 10 | 983,040 | 122,880 | 1,105,920 | **−860,160** |
| `sliding_fused_attn_ring` | attention_kv | 30 | 62,914,560 | 0 | 62,914,560 | 0 |
| `full_fused_attn_grow` | attention_kv | 10 | 23,592,960 | 0 | 23,592,960 | 0 |
| `residual_rms_router` | routed | 39 | 40,894,464 | 0 | 40,894,464 | 0 |
| `dense_gate_up_swiglu` | dense | 1 | 67,108,864 | 0 | 67,108,864 | 0 |
| `dense_down_residual` | dense | 1 | 33,554,432 | 0 | 33,554,432 | 0 |
| `lmhead_int5_base_coarse_delta` | embed_lmhead | 1 | 102,760,448 | 6,422,528 | 109,182,976 | 0 |
| 10 activation-tail families | activations | 1 ea | 1,958,848 | 0 | 1,958,848 | 0 |

```
derived 1,667,101,632   accepted 1,671,402,432   residual −4,300,800  (−0.2573 % of B)
```

### Published residual (Rule 79)

The residual is **one root cause, not noise**. The accepted census
(`research/fern_r101_byte_audit.py:172-176`) prices `g_proj` as BF16 at
4096 B/head, citing `LagunaRuntimeModel.swift:3383, 5734`. Those citations do
not support the claim: line 3383 is inside a Metal source string literal and
5734 is the fused *affine QKV* builder. HEAD actually loads `g_proj` as **affine
INT8 group-32 with bf16 scales and bf16 biases** (`LagunaRuntimeModel.swift:482-497`),
and the decode dispatch guard at `:4526-4540` refuses anything but
`mode == .affine, bits == 8, groupSize == 32`. `DARKBLOOM_NATIVE_AFFINE_GPROJ`
defaults on for all 40 layers.

So the real per-head cost is 2048 code B + 256 metadata B = **2304 B/head**, not
4096 B. Over 30×64 + 10×48 heads that is 4,300,800 B less than the accepted
model. Both mismatched lines are the same effect; every other family is exact.
0.2573 % is under the brief's 1 % "miss is itself a finding" threshold, but it is
recorded here because it means `B` — and therefore the 2773.1 µs bandwidth
floor — is very slightly pessimistic.

### Second-order effect the accepted census omits

The accepted census counts weight/KV traffic only. Summing every kernel's
declared `inputNames` / `outputShapes` adds **5,732,384 B (0.3430 % of `B`)** of
activation operands. Net of the `g_proj` correction, the two effects put true
step traffic ≈ +1.43 MB above the derived figure, i.e. within 0.09 % of the
accepted `B`. **The accepted constant is sound at the 0.1 % level; I recommend
keeping it rather than repricing.**

### Instrument validation

The census in Part B of my script was written from geometry and reads the shipped
U8 scale planes directly. Over all 39 sparse layers it independently reports
**234 tensors, 985,300,992 group pairs, 168 run-2 exceptions** — byte-for-byte
the same three numbers the shipped `lagunaHalvedGroup32ScalePlane` docstring
records for its own certificate (`LagunaRuntimeWeights.swift:1059-1060`: "234
tensors, 985,300,992 pairs … 985,300,824 pairs are byte-identical and all 168
exceptions are the very first pair of a tensor"). The
instrument is verified against live code before any new claim rests on it.

## Stage 2 — three-way classification of every metadata line

Metadata sub-splits of the 64,294,912 B:

| metadata line | bytes/step | % of `B` | class |
|---|---:|---:|---|
| routed gate/up NVFP4 g32 scale plane | 20,447,232 | 1.2233 | REMOVABLE-BIT-EXACT (partly) |
| routed + shared down g32 scale plane | 11,501,568 | 0.6881 | REMOVABLE-BIT-EXACT (partly) |
| attention lane-major nibble scale banks | 22,753,280 | 1.3613 | IRREDUCIBLE (already recoded, #35) |
| shared gate/up g32 scale plane | 2,555,904 | 0.1529 | REMOVABLE-BIT-EXACT (partly) |
| lm_head int5 e8m0 coarse scale bytes | 6,422,528 | 0.3843 | REMOVABLE-BIT-EXACT (partly) |
| `g_proj` affine INT8 scales + biases | 614,400 | 0.0368 | REMOVABLE-BIT-EXACT (partly) |
| **NVFP4 scale metadata subtotal** | **57,257,984** | **3.4256** | |

### Census of the shipped group-32 scale planes

Full 39-layer pool (1.97 GB U8, 18.5 s, CPU only). "run-`k` equal" is the
fraction of `k`-consecutive group codes within a row that are bitwise identical —
i.e. whether the plane could be re-halved again losslessly.

| class | tensors | run2 equal | run4 (g64) equal | run8 (g128) equal | row span ≤15 | row distinct mean / max | g32 entropy |
|---|---:|---:|---:|---:|---:|---:|---:|
| routed_gate_up | 78 | 0.99999991 | **0.2298** | 0.01996 | 0.99836 | 7.02 / 22 | 2.592 b |
| routed_down | 39 | 0.99999992 | **0.2377** | 0.02172 | 0.99980 | 5.07 / 13 | 2.453 b |
| shared_gate_up | 78 | 0.99997926 | **0.3011** | 0.04841 | 0.96111 | 6.15 / 22 | 2.461 b |
| shared_down | 39 | 0.99997574 | **0.2640** | 0.03145 | 0.99403 | 4.88 / 14 | 2.341 b |

Three conclusions:

1. **run-2 ≈ 1.0** confirms #72's pairwise result — and that saving is *already
   banked* at HEAD (`lagunaHalvedGroup32ScalePlane` is live). It is not
   available again.
2. **group-64 merge is only 23–30 % constant, group-128 only 2–5 %.** Halving
   again is **REMOVABLE-NOT-BIT-EXACT** and therefore out of scope. This kills
   the single cleanest way to get a ≥1.2 % line.
3. **Row code span ≤ 15 for 96.1–99.98 % of rows.** The shipped attention
   nibble-delta encoding — one 4-bit delta per group-32 code plus one uint8 row
   base, with `0xFF` escaping to the stock plane
   (`LagunaRuntimeWeights.swift:857-943`) — *is* applicable to routed/shared.
   This is the only bit-exact mechanism the data supports, so it defines the
   addressable ceiling.

### Addressable bit-exact ceiling, per site

`nibble-delta` = `g/2 + 1` bytes/row instead of `g` bytes/row, where `g` is the
group-32 code count per row (64 for a 2048-wide row). It keeps fixed-width O(1)
per-lane addressing. `entropy` = Shannon floor of the measured group-32 code
distribution — a bound on *any* coder.

| site | metadata now | nibble-delta saving | % of `B` | entropy-floor saving | % of `B` |
|---|---:|---:|---:|---:|---:|
| routed_gate_up | 20,447,232 | 9,904,128 | 0.5926 | 13,822,262 | 0.8270 |
| routed_down | 10,223,616 | 4,472,832 | 0.2676 | 7,088,942 | 0.4241 |
| shared_gate_up | 2,555,904 | 1,238,016 | 0.0741 | 1,769,486 | 0.1059 |
| shared_down | 1,277,952 | 559,104 | 0.0335 | 904,005 | 0.0541 |
| lmhead int5 e8m0 | 6,422,528 | 3,110,912 | 0.1861 | — | — |
| **total** | | **19,284,992** | **1.1538** | **26,695,607** | **1.5972** |

- Largest single addressable component: **0.5926 %** of `B` → +0.249 % of `cs`.
- Addressable aggregate: **1.1538 %** of `B` → **+0.4846 % of `cs`**.
- Routed + shared only (my scope fence): 16,174,080 B = 0.9677 % of `B`.

### Stage-3 gate arithmetic

The gate was one component **≥ 1.2 % of `B` (≥ 20,056,829 B)**. Largest = 0.5926 %.
Even summing all five planes — five independent mechanisms, each needing its own
kernel variant, transform pass and equivalence certificate — reaches 1.1538 %,
still short. **The gate does not open and I did not build.**

The only column that clears 1.2 % is the entropy floor (1.5972 %, and 1.4111 %
for routed+shared alone). Reaching it requires **variable-length codes**, so a
lane can no longer compute its own scale offset from its index. Every qmv and
gather-qmv family in this runtime depends on that O(1) fetch. This is exactly the
Rule-66 precondition — price a byte cut at 0.015224 %/MB *only if* it preserves a
single contiguous read — and every realised member of this family failed it
(#85, #301b, #525, below). I score the entropy column as
**REMOVABLE-NOT-BIT-EXACT-IN-PRACTICE / expected loss**, not as an open lever.

### Two further mechanisms considered and rejected on arithmetic

- **3-bit LUT per row** (needs row-distinct ≤ 8; true for 89–99.96 % of rows).
  On 2048-wide rows it costs 24 index bytes + 8 LUT bytes = 32 B vs the
  nibble-delta 33 B — a 1-byte gain, i.e. nothing. Only oproj's 6144/8192-wide
  rows benefit, worth ~1.88 MB = 0.113 % of `B`.
- **Adding `g_proj`** (0.0368 %) plus that oproj line lifts the grand aggregate
  to ≈1.30 % — but only as the sum of **six** independent mechanisms, which is
  precisely the "combine several unmeasured mechanisms before any one wins end to
  end" failure mode the guide warns against.

## Blockers discovered in code (why the nominal 0.59 % is optimistic)

These are the reasons I would not recommend the routed nibble-delta candidate
even if the gate had been set lower:

1. **The routed scale plane is shared with the prefill path by strided alias.**
   `lagunaPackedPrefillScaleView` / `lagunaPackedPrefillDownScaleView`
   (`LagunaRuntimeWeights.swift:998-1039`) hand the *same* halved buffer to the
   expert-aligned M5 prefill primitive using `asStrided` with a zero stride on
   the last axis. A nibble-packed re-encode cannot be expressed as a stride, so
   it would need a **second resident plane** plus a matching prefill-kernel
   change — and the M5-selected `_nax` GEMM family is prefill-only
   (`fp_quantized_nax.metal:54-73` instantiates no `qmv_nax`), so an M4 result
   would be inadmissible evidence for it.
2. **The packed routed gate/up bank has 16-B granularity.** Its layout is
   `[tile 128][k-block 4][sub 8][16 B]` (`preparePackedRoutedGateUpBank`).
   Halving the 16-byte unit again breaks the walk-order address map the custom
   kernel bakes in.
3. **The 128-byte patch header holds at most 128 exceptions.**
   `lagunaScalePatchHeaderBytes = 128`; routed_gate_up alone already spends 57 of
   them. A nibble-delta encoding adds `0xFF`-escape rows on top, and the stock
   plane must stay resident to serve them — as it already does for attention.
4. **Double residency, already present.** The full 32 MiB/layer stock routed
   gate/up plane is retained alongside the 16.78 MB packed bank. This is a
   footprint issue rather than a bytes-read issue on a 128 GB host, but a further
   encoding layer would compound it.

## Transform-side cost

**Zero offline cost; no `MLXFastTransform` metadata or checkpoint change is
needed.** Every existing recode in this family — group-32 halving, the packed
routed bank, the attention lane-major nibble bank — is built **at load time from
the shipped planes** using MLXArray ops
(`lagunaHalvedGroup32ScalePlane`, `preparePackedRoutedGateUpBank`,
`LagunaRuntimeWeights.swift:857-943`). Each ships with a fail-closed certificate
that verifies losslessness for the *loaded* checkpoint and returns `nil` — falling
back to the full-resolution path — if any discarded byte differs.

So the cost of a hypothetical routed nibble-delta bank is:

- **Load time**: one extra gather/compare pass over the 1.97 GB U8 pool plus the
  certificate's compare-and-sum. Precedent: the packed routed bank already does a
  `take` + `contiguous` over 32 MiB/layer at init. Model load is outside the
  frozen timing window, so this is **not scored**.
- **Resident memory**: +337 MB for a routed gate/up nibble bank
  (10,223,616 rows × 33 B) *on top of* the retained stock plane. Fine on 128 GB;
  material on the ≥36 GiB low-memory profile.
- **Build/verification**: one new kernel-name suffix per variant (Rule 33), a new
  equivalence certificate, and — because of blocker 1 — a paired prefill change
  that only the ranked M5 can validate.

The costs are not the reason this closes; the arithmetic is. But they confirm the
axis is not cheap even at its nominal rate.

## Rule 83 — prior art, per candidate

For each candidate I state whether it was already closed and whether my
instrument is materially better.

| candidate | prior status | my instrument | verdict |
|---|---|---|---|
| pairwise g32 halving of routed/shared planes | **#72 MERGED and live** (`lagunaHalvedGroup32ScalePlane`, −30.67 MB/step) | reproduces its certificate exactly (234 tensors / 985,300,992 pairs / 168 exceptions) — **equal, not better** | already banked; not re-available |
| attention scale code-width 128 → 33 B/row | **#35 MERGED, confirmed on M5** (+1.05 % ns, −30.61 MB/step, −67.6 ± 7.9 µs/step) | none — I only priced it | closed, banked |
| shared pairwise plane as a separate mechanism | **#301 mech (b) REFUTED**: +0.139 µs/call (+5.4 µs/step) *despite fewer bytes* | my ceiling says the target is only 0.1529 % of `B` | closed; direct Rule-66 counter-example |
| shared-scale-plane halving | **#104** killed on arithmetic (real target 3.83 MB/step), never measured | agrees | closed |
| routed g32 → global 4/6-bit scale recode | closed by entropy in `RESEARCH_ARCHIVE_through-round-91.md:6455-6465`: 42–57 distinct codes globally ⇒ uniform 4-bit impossible; uniform 6-bit worth +0.167 %, under the 0.243 % 2σ line | **materially better**: I measure *per-row* span and distinct count (span ≤15 for 99.8 % of routed rows) instead of a global distinct count, which is why my number is 0.968 % rather than 0.167 % | **still under the 1.2 % gate** — better instrument, same conclusion |
| group-64 / group-128 re-halving | not previously measured | **new**: 23–30 % / 2–5 % constant | newly closed as not bit-exact |
| lossless repack of BF16 weight planes | **#85 NO-GO** (bit-exact, −25.14 MB/step, decode **+0.905 % slower**); **#513/#525** best 20.263 MB/step realised **+69.60 µs/step slower** | none | closed; the strongest evidence that a fragmenting byte cut loses |
| expert slab dedup | **#143 KILLED**: 0 of 59,904 slabs removable | none | closed |
| routed qmv bandwidth headroom | **#71** dead at step 0 (kernel ≥ 92 % of M4 ceiling) | consistent | closed |

The honest summary of this table: **the metadata axis has already been mined
twice (#72, #35) and both winners are live.** What remains is the residue, and
the residue is 1.15 % of `B` spread over five planes.

## Preregistered nulls

| null | condition | fired? |
|---|---|---|
| **N-A** | metadata < 5 % of `B` ⇒ axis closed | **YES** — 3.8468 % |
| **N-B** | large but not bit-exact, or transform-negative | **YES** — the ≥1.2 % column exists only under variable-length coding |
| **N-C** | reconciliation fails ⇒ stop | no — 23/25 families exact, residual 0.2573 % with a single identified cause |
| **N-D** | built candidate not bit-exact ⇒ halt | n/a — nothing was built |

## Answer to the assigned question

Quantisation metadata is **3.8468 % of the 1,671,402,432 B a decode step moves**
— 64.29 MB, of which 57.26 MB is NVFP4 scale planes, 6.42 MB is lm_head int5
e8m0 bytes and 0.61 MB is `g_proj` affine INT8 scales/biases. **Almost none of it
is removable without changing an output bit.** The one pairwise redundancy that
was genuinely free has already been taken (#72, live), and the attention planes
have already been recoded to 33 B/row (#35, live, M5-confirmed). Of what is left,
group-64 merging is only 23–30 % constant so it is not bit-exact; the best
bit-exact encoding the data supports — extending the shipped lane-major
nibble-delta scheme to routed and shared — is worth **0.5926 % of `B` at its
largest single site and 1.1538 % summed over all five planes**, i.e. **+0.485 %
of `cs`** in the impossible case where all five land free. That is below the
1.2 % Stage-3 gate, and the routed plane's strided alias into the M5-only `_nax`
prefill path plus the Rule-66 contiguity requirement make even the nominal figure
optimistic. **The metadata axis of 105-D's M5 lever is closed.** If decode is to
be improved further, the remaining `B` is 96.15 % weight payload, and payload
reduction requires leaving the bit-exactness constraint — which is a different
assignment.

## Suggested follow-ups (not implemented)

1. **Reclaim the double residency**, not the bytes read. The stock 32 MiB/layer
   routed gate/up scale plane stays resident alongside the packed bank (~1.25 GB
   total). Freeing it after the certificate passes is a footprint win that could
   matter for the low-memory startup profile. Not a scored-bytes change.
2. **The payload side is where the mass is**: `attention` payload alone is
   717.9 MB/step (43.0 % of `B`), of which oproj is 314.6 MB. A 1 % payload cut
   there is worth more than the entire metadata axis.
3. **Do not reprice `B`.** The `g_proj` overstatement (−4.30 MB) and the omitted
   activation operands (+5.73 MB) nearly cancel; the accepted constant is right
   to within 0.09 %. Fixing `research/fern_r101_byte_audit.py:172-176` to model
   `g_proj` as affine INT8 g32 would keep future ledgers honest, but the
   downstream 2773.1 µs floor should stand.

## Reproduction

```bash
python3 research/tanjiro_r106a_byte_ledger.py --ledger --scales --all \
  --out research/artifacts/maple-tanjiro-r106a/decode-metadata-ledger.json
python3 research/tanjiro_r106a_wandb_log.py
```

Part A (`--ledger`) is pure arithmetic over geometry and takes under a second.
Part B (`--scales --all`) reads the 1.97 GB U8 scale pool from the checkpoint on
CPU and takes ~18 s. Neither builds, dispatches, or times anything, so no
benchmark lock and no GPU are required.
