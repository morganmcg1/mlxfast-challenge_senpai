# Pre-registration for #72 Step 2 (required by §7)

**Published as a pushed commit, not a PR comment.** The student terminal holds no
GitHub credential and the typed `respond_to_issue` transition refuses pull
requests (`human messages must use an issue, not a pull request`). This file is
pushed to `maple-nezuko/group32-scale-census` **before any timed candidate is
run**, which gives the same immutable ordering guarantee the comment was for.

_Written by an AI agent (OpenHands) acting as research student on behalf of the
human team._

---

## 1. Step 0 census numbers

### 4a — attention-plane positive control (the plane where the mechanism is known)

I ran MLX's own `fp_quantize<bfloat16_t, 16, 4>` over the **real BF16
`q/k/v_proj` weights of all 40 layers** (120 dispatches), using the exact JIT
source assembly (`utils + gemm + quantized_utils + fp_quantized` plus the
`get_template_definition` line — `jit_kernels.cpp:925-936`, `kernels.h:404-424`,
kname from `quantized.cpp:2433-2442`) and the exact 1-D dispatch of
`quantized.cpp:2455-2478` (`per_thread = max(16/32,1) = 1`,
`nthreads = w.size()`, `grid = (nthreads,1,1)`).

```
pairs examined                24903680
even-pair equal               24903591  (99.999643%)
odd-pair (shift) equal         6709878  (26.943449%)
exceptions total                    89
dispatches with exception           89 of 120
exceptions off pair 0                0
distinct E4M3 codes                 36
subnormal code fraction         80.9699%
```

**89 of 120, distinct-code count 36 — frieren's numbers reproduced exactly.**
Every one of the 89 is at flat scale pair index 0 of its own dispatch; zero
elsewhere. The mechanism write-up in §1 of the brief is correct as stated.

Harness: `research/nezuko_attention_scale_control.swift` +
`research/nezuko_attn_dump.py`; log at
`research/nezuko-pr72-logs/attn_control.txt`.

My subnormal fraction is 80.97 % against #35's 80.31 %; I measure the three
separate per-projection scale arrays rather than the fused/narrowed plane, so a
small difference is expected. It does not bear on the pairing result.

### 4b — the real measurement: the SHIPPED routed-expert plane

All 39 MoE layers (layer 0 is dense), all 256 routed experts plus the shared
expert, all three projections, bitwise on the raw uint8 E4M3 code:

```
pairs examined               985300992   (234 scale tensors)
even-pair equal              985300824   (99.999983%)
odd-pair (shift) control                 (23.240469%)
exceptions total                   168
exceptions off flat pair 0           0
tensors carrying an exception  168 of 234
distinct E4M3 codes                 59   (73.47% subnormal)
```

Per family: `switch_mlp.{gate,up,down}_proj` = 100.0000 % even-equal (rounded);
`shared_expert.*` = 99.9976–99.9980 %.

**The shipped checkpoint carries the identical fingerprint.** The odd-pair
control at 23.2 % kills the "small alphabet" explanation — with 59 codes in use
a scattered-code plane would land near there, and the even pairing is
99.999983 %.

### The structural rule, in one sentence

> **Only the first scale pair — flat scale indices 0 and 1, covering the first
> 32 weight elements — of each shipped expert scale tensor may differ; every
> other pair is byte-identical.**

Same rule as 4a, because the shipped scales were produced by this same MLX Metal
`fp_quantize` kernel: for every simdgroup after the first of a 1-D dispatch,
`tidx.x >= 32` holds for all 32 lanes, so `w_max_l = simd_max(0) = 0`,
`scale = w_max_r` for every lane, and the two stored bytes of the span are the
same number (`mlx-generated/fp_quantized.cpp:2346-2352`).

Both 4c bars are met: 99.999983 % ≥ 99.9 %, and every exception matches a
one-sentence provable structural rule.

### Geometry note that matters downstream

NVFP4 group size here is **16**, so "group-32 granularity" means *adjacent
16-groups share a byte*. Confirmed shapes:
`switch_mlp.gate/up_proj.scales = [256,512,128] U8`,
`switch_mlp.down_proj.scales = [256,2048,32] U8`,
`shared_expert.down_proj.scales = [2048,32] U8`.

---

## 2. Step 1 pricing, re-derived (not trusted)

Per expert: weights `512*256*4 + 2048*64*4 = 1,572,864 B`; scales
`512*128*2 + 2048*32 = 196,608 B`. Scale share = `1/9 = 11.111 %` — the
advisor's figure confirmed from the shipped shapes rather than from the
`1/(16*0.5)` argument.

- 8 experts × 39 MoE layers = **312 expert activations/step** → 552.08 MB/step
  (matches the in-situ M5 measurement).
- Halving routed scales saves `312 × 98,304 = 30,670,848 B` = **30.67 MB/step**,
  i.e. 1.71 % of the 1794 MB step.
- Split: routed **gate/up = 20.45 MB**, routed **down = 10.22 MB**. The shared
  expert (3.83 MB) is out of scope for this arm.
- Ceiling route at the M5 651.8 GB/s roofline: 47.05 µs/step → **+0.699 % of
  score**.
- Elasticity route (0.638 × 30.67/1794 of `T`): **+1.091 %**.

**Byte-resolvability floor (§0.5.8):** 30.67 MB/step clears the 27.8 MB/step
floor by only **10.3 %**. That is thin. Consequence on the record: **routed
gate/up alone (20.45 MB) is BELOW the floor**, so a gate/up-only arm is not
receipt-resolvable. The down projection must be in the same candidate, and it
is — see §3.

**Expected value: point +0.5 %, 80 % interval [+0.1 %, +0.9 %].** Below the
ceiling for the advisor's reason (§0.9.18 — partial cache service), slightly
above the +0.35 % prior because the routed-expert scale reads are a strided
1-byte-per-16-weights stream over a 21.6 GB resident working set with 8-of-256
expert selection changing every step, which is close to the worst case for
reuse. Above the 0.278 % MDE either way.

**This is not re-quantization.** The stored scale *values* are byte-identical;
two entries that are provably the same number are stored once. The dequantized
weights are bit-identical, so the accepted-attention-quantization-envelope rule
does not apply.

---

## 3. What is implemented (shape (a), load-time repack)

No offline transform, no checkpoint regeneration, no new env flag, no duplicate
kernel variants. `Sources/MLXFastTransform/Transform.swift` is untouched.

`lagunaHalvedGroup32ScalePlane(_:allowedFlatPairs:)` builds a 1-D uint8 plane
laid out as `[128-byte patch header] ++ [even-byte halved plane]`. The kernels
add a compile-time `scale_patch_bytes` to the base pointer, halve
`scale_row_bytes` (32 → 16), index with `(lane >> 1)`, and recover the exception
with a predicated select from the patch header when
`expert == 0 && row == 0 && kblock == 0 && lane == 1`. No branches on data, no
flags.

Verified allowed exception pairs, empirically, on the shipped bytes: packed
gate/up bank `[0, 16]` (two source tensors are interleaved into that bank),
shipped down `[0]`. The repack **refuses** and returns nil if any pair outside
that set is unequal, in which case the runtime falls back to the stock
non-halved path.

Touched kernels: `lagunaRoutedSwiGLUQMVPackedTop8R1Kernel` (the decode gate/up
arm), `lagunaRoutedSharedDownResidualKernel` (the **primary** decode down arm),
`lagunaRoutedDownReduceKernel` (its fallback), plus the two non-R1 packed
variants for consistency.

**Ownership fences respected.** All hunks are in `LagunaRuntimeModel.swift` at
`:7035-7830` and `:9789-9990` / `:10131-10160`. Nothing between `:5290` and
`:5700`. `prepareNativeAffineQKVWeight()`, `narrowScales`, and `laneMajorScales`
are untouched. fern's #71 measures/widens the *device reads* of the packed
top8keys R1 kernel; this changes the *scale plane width* it reads. They compose,
but they collide textually in that kernel, so whoever lands second rebases.

---

## 4. §0.9.21 certificate — already run, already passing

`--local-submit` is not the certificate.
`research/nezuko_group32_halving_check.swift` compiles **both** kernel texts
(baseline extracted from `HEAD`, candidate from the worktree, both rendered
verbatim through the real Swift string-building code by
`research/nezuko_g32_extract.py`) via `makeLibrary` in **one process**,
dispatches them on identical real shipped fixture bytes at the real decode
geometries, and `memcmp`s the outputs.

```
=== fixture ===
packed_scales    1048576 B -> halved 524416 B (allowed pairs [0, 16], violations 0)
down_scales      524288 B -> halved 262272 B (allowed pairs [0], violations 0)

=== equivalence ===
r1 activated      8192 B, differing bytes = 0
down routed       4096 B, differing bytes = 0
sdr output        4096 B, differing bytes = 0
baseline outputs non-degenerate: true

=== power controls (each MUST flag) ===
1a. packed patch header dropped (even byte substituted): differing bytes = 2 -> FLAGGED
1b. down patch header dropped (even byte substituted): differing bytes = 1 -> FLAGGED
2a. ordinary halved packed scale byte bit-flipped: differing bytes = 1 -> FLAGGED
2b. ordinary halved down scale byte bit-flipped: differing bytes = 2 -> FLAGGED
1c. sdr patch header dropped (even byte substituted): differing bytes = 1 -> FLAGGED
2c. ordinary halved sdr scale byte bit-flipped: differing bytes = 1 -> FLAGGED
3a. down weight byte corrupted: differing bytes = 1 -> FLAGGED
3b. sdr weight byte corrupted: differing bytes = 1 -> FLAGGED

=== verdict ===
PASS
```

Controls **1a/1b/1c are the specific incoherent fault the brief warned about**:
they drop the patch header so the first span silently takes the even byte. Each
flags. A harness where the naive "one byte per pair everywhere" repack passes
would be a broken harness; this one rejects it in three places.

---

## 5. Exact commands

```bash
# census + pricing (already run)
python3 research/nezuko_scale_census.py --all
python3 research/nezuko_attn_dump.py --layers 40
swiftc -O research/nezuko_attention_scale_control.swift -o /tmp/nezuko_g32/attn_control \
  -framework Metal -framework Foundation && /tmp/nezuko_g32/attn_control

# §0.9.21 certificate (already run, PASS above)
python3 research/nezuko_g32_dump.py
python3 research/nezuko_g32_extract.py --tag baseline  --rev HEAD
python3 research/nezuko_g32_extract.py --tag candidate --worktree
swiftc -O research/nezuko_group32_halving_check.swift -o /tmp/nezuko_g32/halving_check \
  -framework Metal -framework Foundation && /tmp/nezuko_g32/halving_check

# still to run at the time this file is pushed
research/run_upstream_equivalence.sh
./benchmark.sh --local-iterate                       # matched baseline and candidate, same quiet host
senpai/check-editable-budget.sh 768bb9d4adfc2baac7d74c0008afc92d010329da
grep -n -A1 'DARKBLOOM_INJECT_DECODE_EMPTY"\|DARKBLOOM_INJECT_EMPTY_TG"' \
  Sources/MLXFastModel/LagunaRuntimeModel.swift    # must print 0 and 160
```

Timing is M4 Pro (Apple GPU generation 16, **no `_nax`**). Raw M4 seconds/token
will be reported and the **byte-arm ×0.399** conversion applied, never ×0.501.
**No official submission will be dispatched** — the ranked channel is held by
frieren #35 r5.

---

## 6. What would make me abandon

1. **`run_upstream_equivalence.sh` fails, or the 64-step drift tripwire moves.**
   Immediate stop, no timing. The §0.9.21 harness covers the three kernels
   edited; it does not cover a load-time repack bug that never reaches them.
2. **Matched M4 decode shows a regression, or a gain below +0.30 % after the
   ×0.399 conversion.** The byte saving is 30.67 MB/step against a 27.8 MB/step
   resolvability floor — a 10.3 % margin. If the measured decode delta is inside
   noise on a plane whose *ceiling* is +0.70 %, the cache-service hypothesis
   (§0.9.18) has won and there is nothing here. No re-running for a better draw.
3. **The load-time repack costs measurable startup time or memory that shows up
   as a prefill regression.** Halved gate/up replaces the full bank (−327 MB);
   halved down is added alongside the module-owned array (+327 MB), so net
   memory is ~flat, but the prefill floor gets checked explicitly rather than
   assumed.
4. **Any exception outside `[0]` / `[0, 16]` appears** when the repack runs over
   the full checkpoint rather than the census sample. The repack self-rejects
   and logs `inactive`; that would be reported as a census-sampling failure
   rather than quietly shipping a fallback.

If (2) fires this is written up as a negative and stopped.
