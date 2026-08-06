# PR #72 — Group-32 effective scale granularity: expert-plane census, then bit-identical halving

Student: maple-nezuko. Assignment `maple-2026-08-06b-group32-scale-census`, revision `r1`.

**Base: `ab1f9a1323421703f944ac1895841e39b8302542`** (`codex/mlxfast-maple-20260804-advisor`
tip, "Merge pull request #73 from morganmcg1/maple-tanjiro/decode-kernel-census").
This is `accepted_base_sha` for the result. The branch was **rebased onto it**
mid-experiment; see §1.1 for why, and §8.3 for the consequence that timing was
measured twice — once on the old base as mechanism evidence, once on the new
base as the ranking-relevant number.

Earlier bases in this arm's history, for audit: the assignment marker base was
`00374ba91cae119bf45cd8f7247ddc87d05aa5b9`; a first baseline advance to
`20f1fb68f9b41b847c0f75c9822a10afba9aad97` was accepted **without** rebase
(advisor comment 5199099967: intersection with `editablePaths` = 0); the second
advance, to `ab1f9a13`, had intersection = 2 and **did** require a rebase.
Campaign `BASE_SHA` for the budget preflight: `768bb9d4adfc2baac7d74c0008afc92d010329da`.

Host: AWS Mac M4 Pro (Apple GPU generation 16, `applegpu_g16s`). No `_nax`
selection here; this arm changes no `_nax` source and no prefill kernel.

**W&B was not used for this arm.** There is no training or sweep here — the
evidence is (a) deterministic census programs whose full stdout is committed
under `research/nezuko-pr72-logs/`, (b) a standalone Metal differential
certificate, and (c) matched `./benchmark.sh --local-iterate` score artifacts.
`wandb_run_ids` is therefore empty and that is the honest value, not a
reporting gap.

---

## 0. Executive summary

The assignment asked two questions and then, conditionally, licensed one
implementation.

1. **Is the shipped NVFP4 scale plane pairwise-constant?** Yes, and much more
   sharply than the ≥99.9 % bar. Over all 985,300,992 aligned even-byte pairs
   in the 234 shipped routed/shared expert scale tensors, **99.999983 %** of
   pairs are byte-identical. Every one of the **168** exceptions sits at flat
   scale-pair 0 of its tensor. The odd-shifted control lands at 23.240469 %,
   which is what "no structure" looks like on this byte distribution.
2. **What is it worth?** Halving the *routed* expert scale plane removes
   **30.67 MB per decode step** out of ~1794 MB (1.71 %). Priced at the
   **routed** block's measured rate of 546.2 ± 23.3 GB/s (#73's independent
   confirmation, not attention's faster 651.8 GB/s), that is **56.1 µs** of a
   4.281 ms M5 step = **+0.834 %** score, quoted as a *roofline lower bound*.
   §0.9.11 forbids transferring #35's over-delivery across planes, so no
   elasticity multiplier is claimed. Pre-registered working estimate was
   **+0.5 %**, 80 % interval **[+0.1 %, +0.9 %]**; the advisor's own prior after
   the reprice is **+0.45 %**, 80 % interval **[−0.10 %, +0.95 %]**.
3. **Implementation.** Option (a), a load-time repack into a half-width scale
   plane plus a 128-byte patch header carrying the ≤2 exceptional pairs per
   plane, wired into all four routed MoE kernels. Bit-identical by
   construction and verified by a standalone differential harness with eight
   power controls.
4. **Does it measure faster?** *This host cannot say.* Two counterbalanced
   campaigns on two different bases put raw M4 decode at **+1.08 %** and
   **+0.73 %** — but the **prefill negative control, on an axis the change
   provably cannot reach, moved by the same margin in both** (+0.61 %,
   +0.77 %). Net of that offset the decode effect is +0.47 % and −0.04 %. The
   M4 evidence is consistent with the +0.834 % roofline bound and equally
   consistent with zero, and I am not presenting it as a win (§8.3.3).

Timing verdict is in §8. Correctness is bit-exact everywhere it was checked.

---

## 1. Ownership fences (checked, not asserted)

The advisor fenced the attention scale plane (frieren #35, holding the ranked
channel at r5): `prepareNativeAffineQKVWeight()` at
`LagunaRuntimeModel.swift:5592-5672`, `narrowScales`, `laneMajorScales`, and
generally `LagunaRuntimeModel.swift:5290-5700`.

Every hunk in this candidate, by `git diff -U0` hunk header:

```
7031, 7053, 7072, 7091, 7119, 7122, 7137, 7141, 7179, 7209, 7228, 7255,
7264, 7271, 7274, 7377, 7396, 7418, 7448, 7496, 7537, 7556, 7582, 7649,
7707, 7713, 7731, 7755, 7763, 7824, 9768, 9775, 9863, 9865, 9882, 9931,
9975, 9990, 10132, 10161
```

Minimum touched line is 7031. **Zero hunks intersect `5290-5700`.** The strings
`narrowScales`, `laneMajorScales`, and `prepareNativeAffineQKVWeight` appear
nowhere in the diff.

fern's #71 reads the same 552.08 MB/step routed-expert traffic from the
bandwidth angle. There is a **textual** collision in
`lagunaRoutedSwiGLUQMVPackedTop8R1Kernel`: both arms edit that kernel string.
Whoever lands second rebases; the mechanisms are orthogonal (fern reduces
weight bytes, this arm reduces scale bytes) so they should compose. #71 and #73
merged research-only, so neither is in the diff base for code purposes.

### 1.1 Rebase onto `ab1f9a13`, and the byte ceiling

The advisor's comment 5199364988 reported **INTERSECTION: 2** between this
arm's submitted surface and merged #35 (frieren's lane-major 4-bit attention
scale rows): `LagunaRuntimeModel.swift` and `LagunaRuntimeWeights.swift`. The
§0.9.24 inert-surface exemption therefore did not apply and a rebase was
mandatory before any further code work.

`git rebase --onto ab1f9a13 00374ba` applied **cleanly, zero conflicts**. That
is the expected outcome given §1's line census: #35's hunks live at
`LagunaRuntimeModel.swift:2903–6304`, this arm's start at `:7031`. The two
surfaces are disjoint at hunk granularity, which is the same fact the fence
check above already established — the rebase merely confirmed it mechanically.

The rebase did, however, make the **per-file byte ceiling binding**. #35 grew
`LagunaRuntimeModel.swift`, and after the rebase this arm's copy stood at
**528,136 B against the 524,288 B per-file cap — 3,848 B over.** Local timing
would have succeeded on a candidate the official static review would refuse.

The fix was pure relocation, no behaviour change: three file-scope constants
(`lagunaScalePatchHeaderBytes`, `lagunaPackedRoutedGateUpScaleBytes`,
`lagunaRoutedDownScaleBytes`), the module-level function
`lagunaHalvedGroup32ScalePlane(_:allowedFlatPairs:)` (it uses no `self`), and
`preparePackedRoutedGateUpBank` — the last moved verbatim into an
`extension LagunaRuntimeSparseMoEBlock { … }` appended to
`LagunaRuntimeWeights.swift`. Result:

| file | bytes | cap | headroom |
|---|---|---|---|
| `LagunaRuntimeModel.swift` | 521,506 | 524,288 | 2,782 |
| `LagunaRuntimeWeights.swift` | 50,951 | 524,288 | 473,337 |

```
$ senpai/check-editable-budget.sh ab1f9a1323421703f944ac1895841e39b8302542
editable budget OK: current=2973057/3000000 bytes headroom=26943 growth=6226/262144 files=142
```

**"Pure relocation" is verified, not asserted.** Concatenating both files before
and after the relocation (`c44fa50` → `41d4ede`), stripping indentation and
blank lines, and diffing the **non-comment** lines yields exactly two added
lines and zero removed lines:

```
3616a3617
> extension LagunaRuntimeSparseMoEBlock {
9216a9218
> }
```

The doc comments were re-wrapped to fit the new indentation level; their word
multiset is byte-identical before and after. So the only semantic change on the
whole surface is that one method now lives in an extension in a different file.
No expression, guard, constant, or kernel string was touched.

Note the aggregate headroom: **26,943 B against a 3,000,000 B cap.** The
advisor's warning that a Step-2 repack must be designed to the ~2.5 kB that was
free — and must not be planned on the assumption that fern's ~24 kB
Metal-literal reclamation will land first — is confirmed by this number. Any
follow-on work on this surface is byte-constrained before it is
compute-constrained.

---

## 2. Why a PR comment could not be used for the pre-registration

§7 of the brief asked for the pre-registration to be posted as a PR comment
*before* any timed run. That was attempted and is not possible from this role:

- `gh` v2.97.0 is installed but **unauthenticated** in the student terminal;
  no GitHub credential is exposed to it (by harness design).
- The typed `github_transition` `respond_to_issue` operation **refuses pull
  requests**: `human messages must use an issue, not a pull request`.
- No other typed transition posts a free-text comment; `send_assignment_feedback`
  is an advisor→student direction.

The pre-registration was therefore committed to the branch as
`research/maple-nezuko-pr72-preregistration.md` in commit `c844df3`, which is
the commit that *precedes* every timed run in this report. That is a strictly
stronger ordering guarantee than a comment timestamp: the content is
content-addressed and its position in history is verifiable.

---

## 3. Step 0 / §4a — attention-plane positive control

Purpose: prove the census methodology reproduces the already-known result
before trusting it on unknown ground. #35 reported the attention plane is
pairwise-constant except at pair 0.

Method (`research/nezuko_attn_dump.py`, `research/nezuko_attention_scale_control.swift`):
dump the BF16 q/k/v projection weights for all 40 layers, then run MLX's own
NVFP4 quantizer over them through the exact runtime dispatch and read back the
raw uint8 E4M3 scale bytes.

Reconstruction of the dispatch, from source:

| Fact | Citation |
| --- | --- |
| kernel name `nvfp4_quantize_bfloat16_t_gs_16_b_4` | `quantized.cpp:2433-2442` |
| template def `fp_quantize<bfloat16_t, 16, 4>` | `jit_kernels.cpp:925-936`, `kernels.h:404-424` |
| buffers 0=w, 1=out, 2=scales; grid `(w.size(),1,1)`; tg `min(maxTotalThreadsPerThreadgroup, n)` | `quantized.cpp:2455-2478` |
| kernel body | `mlx-generated/fp_quantized.cpp:2335-2373` |
| pairwise predicate on the global grid coord | `fp_quantized.h:2192-2194`, store `:2203-2205` |
| embedded twins, no `_nax` override | `mlx-generated/fp_quantized.cpp:2349-2351`, `mlx-generated/metal/fp_quantized.h:1850-1852` |

Shapes: q `[6144,2048]`, k `[1024,2048]`, v `[1024,2048]` BF16 → 3 dispatches
per layer × 40 layers = 120 dispatches.

Measured (full log: `research/nezuko-pr72-logs/attn_control.txt`):

| Quantity | Value |
| --- | ---: |
| aligned even-byte pairs | 24,903,680 |
| pairs equal | 24,903,591 |
| **fraction equal** | **99.999643 %** |
| odd-shifted control equal | 26.943449 % |
| exceptions | 89 |
| dispatches carrying an exception | 89 of 120 |
| exceptions **not** at flat pair 0 | **0** |
| distinct E4M3 codes observed | 36 |
| subnormal share | 80.9699 % |

This reproduces #35 exactly on the structural claim (all exceptions at pair 0,
89 measured against 120 structurally possible). The subnormal share differs
from #35's 80.31 % because the two aggregate over different denominators
(per-byte here, per-code there); the structural conclusion is unaffected.

**Control passes.** The methodology is trustworthy.

### 3.1 This control is not invalidated by #35

Worth stating explicitly, because it is easy to assume otherwise: the 4a
control reads the **raw checkpoint `.scales` bytes** produced by MLX's own
NVFP4 quantizer. #35 changed only the *runtime-derived* representation — the
128 B per-row scale rows repacked lane-major into 65 B. It does not alter the
quantizer, the checkpoint, or the byte sequence this control measures.
Re-running 4a on the post-#35 base would produce the identical 24,903,680 /
99.999643 % / 89-exception figures. The control is therefore still a valid
positive control on the new base, and no re-measurement was spent on it.

---

## 4. Step 0 / §4b — shipped expert-plane census

`research/nezuko_scale_census.py --all`, ~6.5 s, reads the shipped safetensors
headers directly (no `mlx` python module on this host) and walks the raw uint8
E4M3 scale bytes.

Surface: 39 MoE layers (layer 0 is dense), 256 routed experts + the shared
expert, 3 projections each → **234 tensors, 985,300,992 aligned even-byte
pairs**.

| Quantity | Value |
| --- | ---: |
| aligned even-byte pairs | 985,300,992 |
| pairs equal | 985,300,824 |
| **fraction equal** | **99.999983 %** |
| odd-shifted control equal | 23.240469 % |
| exceptions | 168 |
| tensors carrying an exception | 168 of 234 (exactly one each) |
| exceptions **not** at flat pair 0 | **0** |
| distinct E4M3 codes observed | 59 |
| subnormal share | 73.47 % |

### The one-sentence structural rule

> **Only the first scale pair of a shipped expert scale tensor — flat scale
> indices 0 and 1, covering the tensor's first 32 weight elements — may hold two
> different bytes; every other aligned even-byte pair in every shipped routed
> and shared expert scale tensor is byte-identical.**

Why: the MLX NVFP4 quantizer writes scale index `i` from the thread whose
global 1-D grid coordinate covers group `i`, and the pairwise predicate
(`fp_quantized.h:2192-2194`) makes the *even* member of each pair the one that
survives, so pairs are constant by construction — except at the grid origin,
where the predicate's boundary condition lets index 1 keep its own value. The
mechanism is a property of the quantizer's grid, not of the data, which is why
the exception count equals the tensor count and never exceeds one per tensor.

### Geometry read from the checkpoint

NVFP4 group size **16**; hidden 2048; `moe_intermediate` 512;
`shared_expert_intermediate` 512; 256 experts; top-8.

| Tensor | Shape | dtype |
| --- | --- | --- |
| `switch_mlp.gate_proj.scales` / `up_proj.scales` | `[256, 512, 128]` | U8 |
| `switch_mlp.gate_proj.weight` / `up_proj.weight` | `[256, 512, 256]` | U32 |
| `switch_mlp.down_proj.scales` | `[256, 2048, 32]` | U8 |
| `switch_mlp.down_proj.weight` | `[256, 2048, 64]` | U32 |
| `shared_expert.gate_proj.scales` / `up_proj.scales` | `[512, 128]` | U8 |
| `shared_expert.down_proj.scales` | `[2048, 32]` | U8 |

**Bar cleared:** ≥99.9 % equal (99.999983 %) **and** a one-sentence provable
structural rule for the exceptions.

### 4.1 Relation to frieren's census (#35 r1 and r3)

`research/frieren-pr35-scale-census.md` and `research/frieren-pr35-c-census.md`
already census the same bytes, so it is worth being precise that these are
**complementary, not redundant** measurements of one array.

- Frieren asks: *how many distinct E4M3 codes appear in a row, and what is the
  `max − min` span within a 32-group block?* That question licenses a **4-bit
  code-alphabet** narrowing (128 B → 65 B lane-major rows).
- This census asks: *are adjacent even-byte pairs byte-equal?* That question
  licenses a **width halving** (32 B → 16 B) with no alphabet assumption.

The two answers are consistent and the numbers cross-check. Her plane sizes
(`routed.gate_up` 1,308,622,848 B, `routed.down` 654,311,424 B,
`shared.gate_up` 5,111,808 B, `shared.down` 2,555,904 B) sum with the packed
bank to the same surface this census walks. Her code statistics also explain
*why* the pairwise result is so extreme: global code mass is concentrated in
seven codes carrying ~97.9 % of all bytes (code 6 = 28.72 %, 7 = 24.21 %,
8 = 15.91 %, 5 = 15.47 %, 9 = 6.73 %, 4 = 3.77 %, 10 = 3.07 %). A plane that
concentrated would look pairwise-similar even by accident — which is exactly
why the **odd-shifted control at 23.24 %** is the load-bearing number here, not
the 99.999983 %. The control says the structure is positional, not
distributional.

Two of her findings bear directly on scope:

1. Her r1 doc states that routed/shared planes "are out of scope here; also
   routed/shared on-disk scales are read by prefill, so only a **decode-only
   side bank** could ever be narrowed." A decode-only side bank is precisely
   what §6 builds. This arm extends into the plane she deliberately excluded,
   by the mechanism she named.
2. Her r3 measured that 32-group `down` rows would narrow 32 B → 17 B (−46.9 %)
   under her scheme, but that this is **blocked** by the `groups % 64 == 0`
   guard in `lagunaLaneMajorNVFP4ScaleBank`
   (`LagunaRuntimeWeights.swift:850-853`), so she left the down projections
   undone. The pairwise halving in §6 is not subject to that guard: it operates
   on flat byte pairs, needs no 64-group alignment, and reaches `routed.down`
   (32 B → 16 B, a clean −50 %). §5's floor analysis shows including `down` is
   not optional — gate/up alone is below the MDE.

Her per-plane escape rates (fraction of rows *not* representable in her narrow
form) also rank the planes the same way this census does: `routed.down`
0.02 %, `routed.packed` 0.05 %, `routed.gate_up` 0.16 %, `shared.gate_up`
3.89 %. The routed planes are the clean ones; `shared.gate_up` is both the
worst-behaved and the smallest (5.1 MB), which independently supports §6.5's
decision to leave the shared expert alone.

Her census instrument is preserved out-of-tree as
`research/frieren-pr35-census-instrument.patch`; this arm's instruments are
committed under `research/` as plain scripts, so both are re-runnable.

---

## 5. Step 1 — pricing re-derivation

Per routed expert, per decode step:

```
weights  = 1,572,864 B   (gate 512×2048/2 + up 512×2048/2 + down 2048×512/2)
scales   =   196,608 B   (gate 512×128 + up 512×128 + down 2048×32)
total    = 1,769,472 B      scale share = 196,608 / 1,769,472 = 1/9 = 11.111 %
```

Activations per decode step: 39 layers × top-8 = 312.

```
routed traffic   = 312 × 1,769,472 B = 552.08 MB/step     (matches the CRS 552.08)
routed scales    = 312 ×   196,608 B =  61.34 MB/step
halving saves    = 312 ×    98,304 B =  30.67 MB/step  = 1.71 % of the 1794 MB step
   gate/up share = 20.45 MB/step
   down share    = 10.22 MB/step
shared expert    =  3.83 MB/step  (out of scope for this arm; see §6.5)
```

### 5.1 Reprice at the routed rate (advisor comment 5199364988, item 5)

The pre-registration priced 30.67 MB at **651.8 GB/s**, which is the rate
frieren measured on the *attention* plane. The advisor correctly rejected that
denominator. #73 (tanjiro's decode-kernel census) independently confirmed the
61.32 MB/step scale plane and the 552.09 MB/step routed total against the
552.08 MB certified here — agreement to 4 significant figures from an
independent instrument — and reported the **routed block's own achieved rate as
546.2 ± 23.3 GB/s**. The routed gather-GEMM is slower than attention because it
is a scattered read over 256 expert banks, not a dense contiguous one.

Repriced at the correct denominator:

```
30.67 MB / 546.2 GB/s = 56.1 us saved per M5 decode step
M5 decode step T      = 4.281 ms
```

Two conversions from "56.1 µs saved" to "% of score", which do not quite agree:

| route | arithmetic | result |
|---|---|---:|
| direct decode weight | `0.0561 / 4.281 x 0.75` | +0.983 % |
| campaign normalised-score constant | `0.0561 ms x 14.862 %/ms` | **+0.834 %** |

The campaign constant (14.862 %/ms, the advisor's own figure in comment
5199364988) is ~15 % more conservative than the naive `0.75·δ/T` linearisation.
I have not been able to rederive the constant from first principles from the
material available to me, so rather than pick the one I can derive I quote the
**smaller** of the two. If the advisor wants the other convention the number
becomes +0.98 % and every conclusion below strengthens, so nothing in this
report depends on resolving it.

**+0.834 % is quoted as a roofline lower bound**, not a point prediction. The
advisor's §0.9.11 explicitly forbids transferring #35's 1.89×/1.41×
over-delivery across planes, so no elasticity multiplier is applied here even
though the identical byte fraction (1.71 % of step traffic) is being removed.
The earlier "+1.091 % programme elasticity" figure is **withdrawn**.

The symmetry with #35 is worth recording precisely because it must *not* be
used as evidence: frieren's attention halving removed 30.6 MB/step = 1.71 % of
decode bytes and delivered +1.0512 %. This arm removes 30.67 MB/step = the same
1.71 %. Same byte fraction, different plane, different achieved rate, different
kernel. The coincidence is real and the inference from it is not licensed.

**Byte-resolvability floor.** The programme's MDE on this host is 0.278 %,
which maps to 27.8 MB/step of removed traffic (§0.5.8). The full routed halving
clears that floor by only **10.3 %**. Consequence, decided *before*
implementing: **gate/up alone (20.45 MB) is below the floor and is not a
measurable arm** — the down projection must be included or the experiment
cannot resolve. At the repriced +0.834 % against MDE 0.278 % the design sits at
**3.0σ**, which is thin but resolvable.

Pre-registered working estimate: **+0.5 %**, 80 % interval **[+0.1 %, +0.9 %]**
(the advisor's prior at pre-registration was +0.35 %, [−0.10 %, +0.75 %]; after
the #73 reprice the advisor raised it to **+0.45 %, [−0.10 %, +0.95 %]**).

**Abandonment criterion, pre-registered:** a measured regression, or a
converted estimate below **+0.30 %**, ends the arm.

Promotion bar: the frequently-quoted **+1.461 %** figure is **stale**. It was
computed against the pre-#35 control `ns` = 2.544360 (`c3ce66ec`). #35's
promotion moved the best-in-feed to `ns` = **2.556326** (receipt `0d123661`,
+1.0512 %). Any bar quoted against 2.544360 should be recomputed. This arm was
pre-registered as *not* expected to clear the bar on its own.

### This is not a re-quantization

The accepted attention quantization envelope restricts *changing the
representation*. This change does neither of the two things that would make it
a re-quantization:

1. The **stored** NVFP4 weight nibbles are untouched. Not one byte of
   `*.weight` is read, rewritten, or re-coded.
2. The **dequantized** value of every weight element is bit-identical. For every
   pair whose two bytes are equal, storing one byte and broadcasting it to both
   lanes reproduces the same two E4M3 scales. For the ≤2 pairs per plane where
   they differ, the patch header restores the exact original bytes.

So the effective quantization grid, the numeric values, and the output bits are
unchanged. The envelope rule does not apply. This is a *storage layout* change
of a redundant array, in the same class as the already-shipped fused and packed
banks.

---

## 6. Implementation

All changes are in `Sources/MLXFastModel/LagunaRuntimeModel.swift`.

### 6.1 Layout

`lagunaHalvedGroup32ScalePlane(_ scales: MLXArray, allowedFlatPairs: [Int]) -> MLXArray?`
(`:9902`) produces

```
[ 128-byte patch header ][ even-byte halved plane ]
```

and returns `nil` if any pair outside `allowedFlatPairs` differs — a fail-fast
contract, not a silent fallback to approximate data. `lagunaScalePatchHeaderBytes = 128`
(`:7031`).

- routed gate/up bank: `allowedFlatPairs: [0, 16]` (the fused bank concatenates
  two source planes, so it inherits two origins)
- routed down: `allowedFlatPairs: [0]`

Resulting sizes: `lagunaPackedRoutedGateUpScaleBytes = 16,777,344` (`:7038`),
`lagunaRoutedDownScaleBytes = 8,388,736` (`:7045`).

### 6.2 Kernels

Four routed MoE kernels index the scale plane and all four were changed
identically in structure: `scale_row_bytes` 32 → 16, a `scale_patch_bytes`
constant added to the base offset, the lane index changed to `lane >> 1`, and a
predicated select that substitutes the patch byte.

| Kernel | Line | Role in decode |
| --- | ---: | --- |
| `lagunaRoutedSwiGLUQMVPackedTop8R1Kernel` | 7377 | **primary** gate/up decode |
| `lagunaRoutedSharedDownResidualKernel` | 7707 | **primary** down decode |
| `lagunaRoutedDownReduceKernel` | 7537 | down fallback |
| `lagunaRoutedSwiGLUQMVPackedKernel` / `…PackedSelectedSource` | 7072 / 7209 | gate/up fallback |

`lagunaRoutedSharedDownResidualKernel` is the only kernel that reads **two**
planes with different widths in one dispatch: the shared expert's plane stays
full width (32 B rows) while the routed plane is halved (16 B rows). It
therefore carries runtime `uint scale_row_bytes` / `uint scale_lane` ternaries
selected off the same predicate that already distinguishes the two sources —
no extra branch, no extra register pressure beyond two uints.

The patch is applied only when `expert == 0 && logical_row == 0 && kblock == 0
&& lane == 1`. The R1 prefetch path (`next_block >= 512`) can never reach pair
0 and needs no patch.

### 6.3 Wrappers and dispatch guards

Four wrapper preconditions (`:7179`, `:7496`, `:7649`, `:7824`) were converted
from shape assertions to explicit size checks against the two new byte
constants, and the two decode dispatch guards (`:10132`, `:10161`) now test
`downScales.size == lagunaRoutedDownScaleBytes`.

### 6.4 Fallbacks

Fail-closed, both directions:

- gate/up: `preparePackedRoutedGateUpBank` (`:9939`) returns `[]` and logs
  `lagunaTrace("inactive", "packed routed gate/up bank (scale halving declined)")`,
  so the runtime falls back to the non-packed routed QMV path with the original
  full-width scales.
- down: `_routedDownScales` stays `nil` and the runtime falls back to the stock
  `downProj`.

Neither fallback can produce wrong numbers; each costs the gain.

### 6.5 What was deliberately *not* done, and why

| Rejected alternative | Reason |
| --- | --- |
| Re-code the fp4 nibbles so the pair is exactly constant | That *is* a re-quantization; changes output bits; outside the envelope. |
| Store the max (or either) byte and drop the exception | Changes 168 weight groups' scale; not bit-exact; the whole point of the census was to avoid needing this. |
| Correct on the output side instead of a patch header | Needs a second pass over the output, costs more bytes than it saves. |
| Per-expert pointer/stride select for the halved vs full plane | Adds an indirection to the hot inner loop to serve 2 pairs out of 8.4 M. |
| A synthetic "expert 256" patch slot appended to the bank | Would have made the bank size non-power-of-two and broken the existing `expert * stride` addressing everywhere. |
| Halve the shared expert's plane too (3.83 MB) | Its kernels are `:6515/:6597/:6698`, a different family, and 3.83 MB is 7.7× below the resolvability floor. Out of scope; recorded as future work. |

### 6.6 Memory

The halved gate/up plane *replaces* the full packed bank (−327 MB). The halved
down plane is added *alongside* the module-owned array (+327 MB) because the
module array is still referenced by the fallback path. Net ≈ 0.

### 6.7 Where the repack runs

`prepareFusedRoutedGateUp()` is called from `prepareFusedRuntimeWeights()`
(`:11052`), the existing load-time weight-preparation hook, and its arrays are
`eval`'d there with all the other prepared layouts. The repack is therefore
**untimed load-time work outside the scored window**, in the same place the
tree already builds its fused QKV, RoPE atlases, and lm_head screening plane.
It cannot charge the prefill axis.

---

## 7. §0.9.21 standalone differential certificate

An end-to-end token match is a weak test of a scale-indexing change: most of
the plane is redundant, so a broken patch would corrupt only 168 groups out of
8.4 M and might not move a greedy argmax. §0.9.21 therefore requires a
*standalone* harness that compiles the baseline and candidate kernel strings
side by side and compares raw output bytes, plus **power controls** that prove
the harness can actually detect a fault.

Three programs:

- `research/nezuko_g32_extract.py` — extracts the kernel bodies from either
  `HEAD` (`--tag baseline --rev HEAD`) or the worktree (`--tag candidate
  --worktree`), plus the shared `--preamble`. `KERNELS = {r1, down, sdr}`;
  `HEADER_EXPR` composes the right header chain per kernel (r1 needs
  `lagunaSharedSwiGLUQMVHeader + lagunaDecodeRouterOrdinalHeader +
  lagunaRouterTop8PrologueHeader`; down/sdr need only the first).
  Extracted sizes: baseline_r1 8,693 / candidate_r1 8,899; baseline_down 5,901 /
  candidate_down 6,049; baseline_sdr 5,658 / candidate_sdr 6,059;
  `preamble.metal` 47,412 B.
- `research/nezuko_g32_dump.py` — dumps layer-1 experts 0..7 plus the shared
  expert to `/tmp/nezuko_g32/*.bin` with a fixed seed
  (`np.random.default_rng(20260806)`) for the activation side.
- `research/nezuko_group32_halving_check.swift` — ports MLX's `write_signature`
  (all bindings `device`, 20-entry attribute table), sets `mathMode = .safe` to
  match the runtime, and compares all three kernel pairs in one process.

```bash
swiftc -O research/nezuko_group32_halving_check.swift -o /tmp/nezuko_g32/halving_check \
  -framework Metal -framework Foundation && /tmp/nezuko_g32/halving_check
```

Result (`research/nezuko-pr72-logs/halving_check.txt`):

| Pair | Differing output bytes |
| --- | ---: |
| r1 (routed gate/up) | **0** |
| down reduce | **0** |
| shared-down-residual | **0** |

Eight power controls — deliberately corrupted variants (1a/1b patch-byte
suppression, 2a/2b lane-index off-by-one, 1c/2c row-stride restoration,
3a/3b patch predicate widened) — **all FLAGGED**. A harness that reports 0 on
the candidate *and* non-zero on all eight faults is a real test.

Verdict: **PASS**.

---

## 8. Correctness and timing

### 8.1 Upstream equivalence

`research/run_upstream_equivalence.sh` (wrapper, bare test filter
`lagunaRuntimeMatchesVendoredUpstreamOnM5WhenEnabled`, oracle report marker
present, **1 test selected** — not a zero-selection false pass).

Candidate result:

| Step | max abs logit error | mean abs logit error | runtime token | upstream token |
| --- | ---: | ---: | ---: | ---: |
| prefill | 0.125 | 0.011933609 | 5991 | 5991 |
| decode-0 … decode-7 | **0** (all 8) | **0** (all 8) | 509/902/5991/509/902/5991/509/902 | identical |

`EQUIVALENCE_EXACT_STEPS=8`, `EQUIVALENCE_EXIT=1`. The wrapper's zero-tolerance
gate trips on the prefill row.

**This is pre-existing host drift, and it is proved, not assumed.** Following
the AGENTS.md rule ("if a non-M5 host disagrees with a public golden, test the
unchanged base"), the same wrapper was run on a temporary commit that reverts
`LagunaRuntimeModel.swift` to the assignment base `00374ba` and changes nothing
else. The unchanged base produces a report that is **identical in every field**:

```
base      prefill maximumAbsoluteLogitError 0.125   meanAbsoluteLogitError 0.011933609
candidate prefill maximumAbsoluteLogitError 0.125   meanAbsoluteLogitError 0.011933609
base      decode-0..7 all 0 ; candidate decode-0..7 all 0
all 9 runtimeToken/upstreamToken pairs equal and equal across base and candidate
```

The mean error agrees to all nine printed digits, so the candidate is not merely
"within the same tolerance" as the base — it is producing the same numbers.

The mechanism is understood: 0.125 is exactly 1 ULP of BF16 at magnitude
16–32, and prefill on this M4 Pro (`applegpu_g16s`, gen 16) runs an entirely
different kernel family from the ranked M5 — 94.2 % of prefill GPU time here is
non-`_nax` code the M5 never executes. Reduction order therefore differs from
the vendored oracle by one ULP on this host only.

Independently, **this change cannot reach prefill at all**. The fused/packed
routed path is gated on `x.dims(1, 1, LagunaConstants.hiddenSize)` — a single
token — and the source comment at the gate states it outright: *"Multi-token
forwards (prefill) below keep the fully stock sorted gather-GEMM path and never
see the fused bank."* All four kernels this arm edits are QMV (matrix-vector)
kernels reachable only from the one-token decode step.

**Verdict: decode is bit-exact against the upstream oracle; the prefill row is
a host artifact shared byte-for-byte with the unchanged base.** No
`MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT` override was used or needed — the wrapper
was simply run twice and the two reports compared.

#### 8.1.1 Repeated on the new base after the rebase

The pair above was collected on the old base `00374ba`, and its control was a
*temporary revert fixture* (`6563bb2`, `LagunaRuntimeModel.swift` reverted, the
rest of the tree left alone). After the rebase of §1.1 the whole pair was
re-run on the new base, and the control was strengthened: instead of a revert
fixture it is the **unchanged advisor base itself, checked out detached at
`ab1f9a1`**. Nothing in the tree differs from the promoted frontier.

| | candidate `41d4ede` | control, detached `ab1f9a1` |
| --- | --- | --- |
| training id | `e48ea245` | `bb8d2b9d` |
| tests selected | 1 | 1 |
| prefill max abs logit error | 0.125 | 0.125 |
| prefill mean abs logit error | 0.011933609 | 0.011933609 |
| decode-0 … decode-7 max/mean | 0 (all 16 fields) | 0 (all 16 fields) |
| tokens, all 9 steps | 5991/509/902/5991/509/902/5991/509/902 | identical |
| runtime vs upstream token | equal at every step | equal at every step |
| `EQUIVALENCE_EXACT_STEPS` | 8 | 8 |
| `EQUIVALENCE_EXIT` | 1 | 1 |

Every printed field agrees, to all nine digits of the mean, across **four**
wrapper invocations now: two bases × two arms. The prefill 1-ULP row is a
property of this M4 Pro host, not of the candidate, and the candidate's decode
steps are bit-exact against the vendored oracle on both bases.

### 8.2 Activation evidence — the halved planes really are the ones executing

A bit-exact change is invisible in output, so "is it on?" must be answered
separately from "is it correct?". Two independent proofs were collected.

**A correction over an earlier draft of this section.** Every activation
artifact below is a *within-build* certificate, **not** a between-arm log
difference. The base already ships a packed routed gate/up bank (promoted
before this experiment), and it emits the same strings from its own,
full-width code. Diffing the two arms' `mlxfast:` diagnostics gives an empty
set:

```
$ for f in <C1-log> <B1-log>; do grep -o 'mlxfast: [a-z0-9 :/-]*' $f | sort -u; done
mlxfast: narrow-scales built lane-major: qkv
mlxfast: narrow-scales built: oproj
mlxfast: packed-scales active: packed routed gate/up bank prepared
mlxfast: packed-scales active: routed swiglu qmv packed dispatch     # identical in both arms
```

An earlier draft read the `... bank prepared` line as proof *because the base
lacked it*. That is false and is withdrawn. The line is still valid evidence,
but only under the stated premise "this binary was built from `41d4ede`", which
is established separately by the commit SHA the run was launched from.

**(a) Static reachability of the gate/up site.** In the candidate source
(`LagunaRuntimeWeights.swift:1049`) the stderr line `packed routed gate/up bank
prepared` sits *strictly after*

```swift
guard let halved = lagunaHalvedGroup32ScalePlane(packed, allowedFlatPairs: [0, 16])
else {
    lagunaPackedScalesLog.note("inactive", "packed routed gate/up bank (scale halving declined)")
    return []
}
```

so within a candidate build it can only be reached once the halved plane exists
and has been bound to `_packedRoutedGateUpBank`. Every candidate run printed it
and **no** candidate run printed `(scale halving declined)`. Gate/up halving is
therefore active in each timed candidate replicate.

The routed-**down** site (`LagunaRuntimeModel.swift:10145`,
`allowedFlatPairs: [0]`) has no log note at all: on decline it silently leaves
`_routedDownScales` nil and falls back to the stock `downProj`. Worse, the
halved byte count is a *guard* rather than a `precondition` at the fused
dispatch site —

```swift
} else if ..., downScales.size == lagunaRoutedDownScaleBytes, ... {
```

— so a declined down halving degrades silently to the generic path and still
passes correctness. Static logs cannot prove that site; a dynamic trace can.

**(b) Dynamic dispatch trace.** The runtime carries an opt-in tracer,
`lagunaTrace`, gated on `DARKBLOOM_TRACE_FUSION=1`. Two extra full benchmark
runs were executed with the flag set: `15b91f96` on the old-base candidate
`c844df3`, and `47d13b3c` on the rebased candidate `41d4ede`. Both
passed correctness with `max_abs_diff` 0.
The trace contains **both** halved-path notes:

```
fusion active: routed gate/up QMV + SwiGLU (packed, producer keys)
fusion active: routed+shared down residual
```

and contains **none** of the stock fallbacks — no bare
`routed gate/up QMV + SwiGLU`, no non-producer-keys `packed scales`, no
`packed-scales inactive` of any kind. The second line is the decisive one: that
branch is guarded on `downScales.size == lagunaRoutedDownScaleBytes`, i.e. on
the *halved* byte count 8,388,736. Its presence proves the down plane is halved
and in use. (`routed down reduce` did not fire; the shared-down-residual kernel
takes precedence on this shape, so that fourth kernel is compiled-and-checked
but not exercised in the scored window.)

**The trace run is excluded from the timing pool.** With the flag on,
`note(site())` executes on *every* dispatch — a String allocation plus an
`NSLock` acquisition — and only the *printing* is deduplicated. Measured cost
was 0.19 % slower than the nearest clean candidate replicate on the old base,
which is the same order as the effect being measured. The new-base trace run
(`47d13b3c`, decode 0.0131990 s/token) landed 0.44 % above the mean of the three
clean candidate replicates and 1.10 % above the immediately preceding clean
candidate replicate — again the same order as the effect. Activation evidence
and timing evidence were therefore collected in separate runs, and no traced run
appears in §8.3.

### 8.3 Matched local timing

**Host and its limits.** All timing was collected on the AWS Mac research host,
an M4 Pro reporting `applegpu_g16s` (Apple GPU generation 16). This host does
**not** select the `_nax` kernels the ranked M5 uses, so per AGENTS.md an M4
prefill number is not evidence about an `_nax` change. This arm touches only
four QMV decode kernels, all of which *are* reachable here, so the decode axis
is directionally interpretable; the prefill axis is used below only as a
**negative control**, never as an effect estimate.

The published `decode_speedup` / `prefill_speedup` fields in
`score.local-iterate.json` compare against a *pinned M5 calibration* and are
meaningless on this host (they read ≈1.04 and ≈0.32 regardless of arm). Only
same-host paired `seconds_per_token` is used.

**Two measurement campaigns.** The rebase of §1.1 landed between them, so this
report contains two independent paired datasets and they answer different
questions. Both are reported; neither is dropped.

| | campaign A (old base) | campaign B (new base) |
|---|---|---|
| base commit | `00374ba` | `ab1f9a13` |
| candidate | `c844df3` | `41d4ede` |
| includes #35 lane-major attention scales | no | **yes** |
| replicates | 4 base / 3 candidate | 3 base / 3 candidate |
| role | **mechanism evidence** — does the halving move the clock at all | **ranking evidence** — what it is worth on the surface that would actually be submitted |

Campaign A is *not* discarded as stale. It is the cleaner mechanism test,
because on that base nothing else had recently changed the scale plane. But
only campaign B is quoted as the effect of this candidate, because only
campaign B's control is the commit the official runner would pair against.

**What actually changed between the two bases**, restricted to code:

```
$ git diff --stat 00374ba ab1f9a1 -- Sources Vendor Tests
 Sources/MLXFastModel/LagunaRuntimeModel.swift   | 330 +++++++++-------
 Sources/MLXFastModel/LagunaRuntimeWeights.swift | 272 +++++++++++++
 2 files changed, 585 insertions(+), 17 deletions(-)
```

All 585 lines are attention-side narrow-scale work — `lagunaNarrowNVFP4ScaleBank`,
`lagunaLaneMajorNVFP4ScaleBank`, narrow QKV/`o_proj` decode kernels, and their
dispatch log. Both campaign-B arms print `narrow-scales built lane-major: qkv`
and `narrow-scales built: oproj` at startup. The routed and shared expert planes
this arm narrows are **disjoint** from those tensors, so the two mechanisms do
not overlap in bytes. They do compete for the same decode step, though: the new
base's own decode is faster (campaign B base mean 0.0132372 s/tok vs campaign A
base mean 0.0133374 s/tok, −0.75 %), so an identical absolute saving is a
slightly larger *relative* one — and, more importantly, the step now has less
attention-scale traffic to hide behind, which is a reason to expect the routed
saving to show up *more* cleanly, not less. Whether it does is an empirical
question answered below, and the answer is not a clean "yes".

**Design, both campaigns.** One full `./benchmark.sh --local-iterate` per
replicate, arms interleaved, each behind the standard 40 °C cool gate
(`MLXFAST_LOCAL_COOL_GATE` left at its default — never disabled, never
shortened). Every replicate passed correctness with `max_abs_diff` 0.

In campaign A the base arm was a temporary local commit reverting
`Sources/MLXFastModel/LagunaRuntimeModel.swift` to `00374ba`, changing nothing
else. That commit (`6563bb2`) is a measurement fixture and **is never pushed**;
it does not appear anywhere in the submitted history. In campaign B no such
fixture was needed — the control is a plain detached checkout of the real
commit `ab1f9a13`, which is strictly better hygiene and is the reason the order
was replanned after the rebase.

Campaign B order was **counterbalanced C B B C B C**, with the candidate first
so that the coldest run in the series is charged to the candidate. Campaign A's
order was base-first (`base_r1, cand_r1, base_r2, cand_r2, base_r3, cand_trace,
cand_r3, base_r4`), which is the weaker design and is one reason campaign B was
run rather than simply extending A.

#### 8.3.1 Campaign A — old base, mechanism

Decode `seconds_per_token`:

| replicate | commit | decode s/tok | prefill s/tok |
|---|---|---:|---:|
| `base_r1` | `6563bb2` | 0.0133036497 | 0.0011464233 |
| `base_r2` | `6563bb2` | 0.0133802135 | 0.0011136754 |
| `base_r3` | `6563bb2` | 0.0133808932 | 0.0011256985 |
| `base_r4` | `6563bb2` | 0.0132847865 | 0.0011283250 |
| `cand_r1` | `c844df3` | 0.0132258141 | 0.0011245035 |
| `cand_r2` | `c844df3` | 0.0131870706 | 0.0011251380 |
| `cand_r3` | `c844df3` | 0.0131686631 | 0.0011154063 |
| ~~`cand_trace`~~ | `c844df3` | ~~0.0132515710~~ | ~~0.0011157728~~ |

`cand_trace` is **excluded** (`DARKBLOOM_TRACE_FUSION=1`, +0.19 % tracer
overhead — see §8.2). It is listed only so the exclusion is visible rather than
silent.

Every percentage in §8.3 uses the **reduction convention**, `(base − cand) /
base`, which is what `analyze.py` and `drift.py` compute. (The alternative
`base / cand − 1` "speedup" convention differs by at most 0.02 pp at these
magnitudes; mixing the two was an error in an earlier draft of this section and
has been removed.)

Primary analysis, all clean replicates (n=4 base, n=3 candidate):

```
base mean = 0.0133373857 s/tok   (sd 0.378 %)
cand mean = 0.0131938493 s/tok   (sd 0.221 %)
raw M4 improvement = +1.0762 %   SE 0.2274 %   95 % CI [+0.6305 %, +1.5219 %]
exact one-sided permutation p = 1/35 = 0.0286
```

**Honest caveat, stated up front:** `base_r4` (0.0132848) was the *fastest* base
replicate and it overlaps the candidate range. The separation is real in the
mean but it is not a clean gap between two non-overlapping clusters. The
estimate is therefore sensitive to pooling:

| pooling | decode reduction |
|---|---:|
| all replicates (n = 4 base / 3 cand) | **+1.0762 %** |
| drop `base_r1`, the coldest first run (3/3) | +1.1595 % |
| drop `base_r4`, the fastest base run (3/3) | +1.2061 % |
| `base_r2`,`base_r3` only, i.e. drop both extremes (2/3) | +1.3953 % |
| adjacent-pair (local) estimator, all six C/B neighbours | +1.1819 % |

Every defensible pooling of campaign A lies in **+1.08 % to +1.40 %**, and the
all-replicate figure is the *most conservative* of them, so I use it as the
headline. Baseline-to-baseline decode noise on this host is 0.575 %.

Campaign A's execution order is **B C B C B C B**, which places the four base
runs at slots 1,3,5,7 (mean slot 4) and the three candidate runs at slots 2,4,6
(mean slot 4). The arm indicator is therefore exactly orthogonal to slot index,
so the OLS drift adjustment `y = a + b·slot + d·arm` returns an arm coefficient
**identical to the unadjusted difference, +1.0762 %** — the design already
cancels any linear session trend (`drift.py oldbase`; fitted slope
−6.079 µs/slot). An earlier draft of this section quoted a "drift-corrected
+0.6042 %"; that number does not reproduce from the archived artefacts under
either convention or either estimator, and it has been withdrawn. The genuine
low-end reading for campaign A is the *control-subtracted* one below, not a
drift correction.

**Prefill negative control.** Prefill is untouched by this change and must not
move. Across the same replicates the prefill difference is **+0.6068 %**
(SE 0.6609 %, 95 % CI [−0.6885 %, +1.9021 %], permutation p = 8/35 = 0.2286),
with an adjacent-pair mean of +0.3366 % (sd 1.1942 %) and a base spread of
1.199 %. Taken alone this is statistically indistinguishable from zero, and at
the time I read it as an uninformative-but-not-contradicting control. Campaign
B reproduced the same positive sign on the same untouchable axis with a
*smaller* spread, and §8.3.3 explains why the two readings together are much
more worrying than either one was in isolation. Subtracting campaign A's own
control from its own decode figure gives **+0.4694 %**.

#### 8.3.2 Campaign B — new base, ranking

Six replicates, strictly counterbalanced **C B B C B C**, candidate first. The
control arm is a plain detached checkout of `ab1f9a13` — no revert fixture.
Each replicate's `metrics.commit` field independently records which binary
produced it, so arm identity is verifiable from the artefacts rather than from
my bookkeeping.

| slot | arm | `metrics.commit` | file | decode s/tok | prefill s/tok |
|---:|---|---|---|---:|---:|
| 1 | cand | `41d4ede` | `newbase_cand_r1` | 0.013227938 | 0.001112663 |
| 2 | base | `ab1f9a1` | `newbase_base_r1` | 0.013289508 | 0.001126176 |
| 3 | base | `ab1f9a1` | `newbase_base_r2` | 0.013248816 | 0.001115098 |
| 4 | cand | `41d4ede` | `newbase_cand_r2` | 0.013140407 | 0.001115531 |
| 5 | base | `ab1f9a1` | `newbase_base_r3` | 0.013173328 | 0.001125936 |
| 6 | cand | `41d4ede` | `newbase_cand_r3` | 0.013054988 | 0.001113270 |

All six passed correctness with `max_abs_diff = 0`. `peak_ram_gb` is 21 on
every replicate in both arms, so the halved planes do not change residency at
the harness's reporting granularity.

```
decode:  base n=3 mean=0.0132372177 sd=0.445%
decode:  cand n=3 mean=0.0131411110 sd=0.658%
decode:  improvement +0.7260%  SE 0.4565%  95% CI [-0.1687%, +1.6207%]
decode:  exact one-sided permutation p = 2/20 = 0.100
```

The permutation test is exact and enumerates all 20 arm assignments; the
smallest attainable one-sided p at n=3/3 is 0.05, so 0.10 means the observed
split is the *second* most extreme of twenty. That is suggestive and it is not
significant.

**Within-session drift.** Decode fell monotonically across the series
(−35.4 µs per slot, −0.267 %/slot by OLS). Because the counterbalanced order
puts the candidate at mean slot 3.67 and the base at 3.33, the raw difference
is *biased in the candidate's favour* by roughly 0.09 %. Two estimators that
remove that bias:

```
drift-adjusted (OLS on arm + slot) : +0.6370%
adjacent-pair mean (4 neighbouring C/B pairs)
        +0.4633%, +0.8183%, +0.2499%, +0.8983%  ->  +0.6074%  sd 0.3042%
```

Campaign B's decode estimate is therefore **+0.61 % to +0.73 %** of M4 decode
time, centred near +0.64 %, i.e. **+0.48 % to +0.57 % of normalised score**.
For comparison on a common axis, the +0.834 % score roofline bound (56.1 µs of
an M5 step) is equivalent to **+1.06 % of M4 decode time** on this host. So
campaign B lands *below* the roofline bound, campaign A's +1.08 % lands right
on it, and neither is above it — which is the direction one would expect if
the bound is genuinely a bound.

#### 8.3.3 The prefill negative control fails to be negative

This is the most important result in the report and it cuts against my own
hypothesis, so it goes in its own section rather than a footnote.

```
prefill: base n=3 mean=0.0011224032 sd=0.564%
prefill: cand n=3 mean=0.0011138214 sd=0.136%
prefill: improvement +0.7646%  SE 0.3346%  95% CI [+0.1087%, +1.4205%]
prefill: exact one-sided permutation p = 2/20 = 0.100
drift-adjusted +0.7743%   adjacent-pair mean +0.8025%
```

Prefill **cannot** be affected by this change. The fused/packed routed path is
gated on `x.dims(1, 1, LagunaConstants.hiddenSize)`; multi-token forwards keep
the stock sorted gather-GEMM path and never read the halved bank. All four
edited kernels are QMV kernels reachable only from the one-token decode step.
Yet the candidate arm is **+0.76 % faster on prefill too**, by the same margin,
with the same p-value, on all three estimators.

The only honest reading is that this M4 Pro host produces a **candidate-
favouring offset of roughly +0.7 % on an axis the change provably cannot
touch**. Campaign A showed the same sign (+0.6068 % across all replicates). Two
independent campaigns, six and seven replicates, both put the untouchable
control at about +0.6 % to +0.8 %.

I do not know the mechanism. Plausible candidates, none verified: binary layout
and code-size differences shifting instruction-cache or dyld behaviour; a
build-directory or page-cache asymmetry between a branch checkout and a
detached checkout; or simply that this host's true per-binary noise floor is
larger than the within-arm sd suggests. What I can say is what it implies:

**If each campaign's own control offset is subtracted from its own decode
figure, campaign B's decode effect is approximately zero (+0.7260 % − 0.7646 %
= −0.0386 %) and campaign A's falls to +0.4694 %.** The M4 measurement
therefore does **not** establish the effect. It is consistent with the
+0.834 % roofline lower bound, and it is equally consistent with nothing.

I am deliberately not "fixing" this by dropping the control or by declaring
prefill too noisy to matter. Its sd (0.564 % base) is comparable to decode's
(0.445 %), so it is not a noisier plane; it is a plane that moved when it
should not have. Reporting a decode win while quietly discarding a
same-magnitude control win would be exactly the kind of result the advisor
should not be able to trust.

#### 8.3.4 Combined view across both campaigns

| campaign | base | n | decode raw | decode drift-adj. | decode adj.-pair | prefill control | decode − control |
|---|---|---|---:|---:|---:|---:|---:|
| A (base-first `B C B C B C B`) | `00374ba` | 4 / 3 | +1.0762 % | +1.0762 % † | +1.1819 % | +0.6068 % | **+0.4694 %** |
| B (counterbalanced `C B B C B C`) | `ab1f9a1` | 3 / 3 | +0.7260 % | +0.6370 % | +0.6074 % | +0.7646 % | **−0.0386 %** |

† Campaign A's arm indicator is exactly orthogonal to slot index, so its OLS
drift adjustment is identical to the raw difference by construction (§8.3.1).

Converted to the ranked axis (×0.399 M4→M5, ×14.862 % per M5 ms), the same
seven readings become:

| reading | M4 decode | M5 µs/step | score |
|---|---:|---:|---:|
| A raw | +1.0762 % | +57.3 | **+0.85 %** |
| A adjacent-pair | +1.1819 % | +62.9 | +0.93 % |
| A − control | +0.4694 % | +25.0 | +0.37 % |
| B raw | +0.7260 % | +38.3 | +0.57 % |
| B drift-adjusted | +0.6370 % | +33.6 | +0.50 % |
| B adjacent-pair | +0.6074 % | +32.1 | +0.48 % |
| B − control | −0.0386 % | −2.0 | **−0.03 %** |

The two campaigns do **not** agree as closely as I would like. On the raw axis
they differ by a factor of 1.5 (+1.08 % vs +0.73 %); on the control-subtracted
axis they differ in sign (+0.47 % vs −0.04 %). What they *do* agree on is that
the untouchable prefill plane moved positively by +0.61 % and +0.77 %, which is
the finding that dominates the interpretation.

Against the pre-registered thresholds (§7): every uncorrected reading lands in
**+0.48 % to +0.93 % of normalised score**, bracketing the pre-registered
+0.5 % point estimate and clearing the +0.30 % abandonment floor. Every
control-subtracted reading lands in **−0.03 % to +0.37 %**, so the
pre-registered abandonment condition ("<+0.30 % converted") is **met** on that
reading for campaign B and marginally met for campaign A. The two readings
disagree about whether this experiment should be abandoned, and the correct
summary is that **this host cannot answer the question**. I am reporting both
rather than choosing the flattering one.

---

## 9. Preflight

Re-run against the **new** base after the rebase and the byte relocation:

```
$ senpai/check-editable-budget.sh ab1f9a1323421703f944ac1895841e39b8302542
editable budget OK: current=2973057/3000000 bytes headroom=26943 growth=6226/262144 files=142
```

All three caps clear: aggregate 2,973,057 / 3,000,000 B; growth 6,226 /
262,144 B; per-file maximum 521,506 / 524,288 B (§1.1). The earlier run against
the campaign `BASE_SHA` (`current=2947543 headroom=52457 growth=-52441`) is
superseded — that base predates #35's growth of `LagunaRuntimeModel.swift`.

```
$ grep -n -A1 'DARKBLOOM_INJECT_DECODE_EMPTY"\|DARKBLOOM_INJECT_EMPTY_TG"' Sources/MLXFastModel/LagunaRuntimeModel.swift
11328:    "DARKBLOOM_INJECT_DECODE_EMPTY", 0)
11329-/// Empty dispatches injected per multi-token forward.
--
11340:    "DARKBLOOM_INJECT_EMPTY_TG", 160)
11341-/// 0 unchains the empties: each binds a never-written control array, so no
```

Both diagnostic injection knobs are at their defaults (0 and 160): no injected
empty dispatches are contaminating the measurement.

```
$ senpai/validate-assignment-scope.sh ab1f9a1323421703f944ac1895841e39b8302542 \
    Sources/MLXFastModel/LagunaRuntimeModel.swift \
    Sources/MLXFastModel/LagunaRuntimeWeights.swift \
    Sources/MLXFastTransform/Transform.swift \
    Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized_nax.h \
    Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized_nax.cpp
assignment scope OK: 5 submitted path(s) against BASE_SHA=ab1f9a1323421703f944ac1895841e39b8302542
```

Submitted surface validated against `benchmark.json` `editablePaths` — 5 paths
declared, of which **two** are now actually modified (the relocation of §1.1
brought `LagunaRuntimeWeights.swift` into the modified set):

```
Sources/MLXFastModel/LagunaRuntimeModel.swift          (modified)
Sources/MLXFastModel/LagunaRuntimeWeights.swift        (modified — §1.1 relocation)
Sources/MLXFastTransform/Transform.swift               (declared, unmodified)
Vendor/mlx-swift/.../kernels/fp_quantized_nax.h        (declared, unmodified)
Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized_nax.cpp (declared, unmodified)
```

The two `_nax` paths remain declared-but-unmodified deliberately. This arm
changes no `_nax` source, so the `mlx-generated/fp_quantized_nax.cpp` ↔
`fp_quantized_nax.h` consistency requirement is satisfied vacuously — but they
stay declared because any Step-2 follow-on would touch them, and re-declaring a
path mid-experiment is a scope change.

**No official submission was dispatched from this arm.** The ranked channel is
free, but the advisor is the scheduler, so dispatch is requested in the PR
rather than taken. The `--model` value, when this or a successor is dispatched,
is `senpai` — confirmed accepted by the API on frieren's r5, so the one-retry
fallback path is not expected to be exercised. No API model-value rejection
occurred here because no submission was made.

---

## 10. Conclusion

### What is established

1. **The census question is answered, decisively.** The shipped routed and
   shared expert NVFP4 scale plane is pairwise-constant at **99.999983 %** over
   985,300,992 aligned even-byte pairs, with all **168** exceptions at flat pair
   0 — one per tensor, exactly as the quantizer's grid predicts. The
   odd-shifted control at 23.24 % rules out the "concentrated distribution makes
   everything look equal" explanation. The structural rule in §4 is provable
   from `fp_quantized.h:2192-2194`, not merely observed.
2. **The halving is bit-identical, and that is verified four ways**: by
   construction (§6), by the standalone eight-control differential certificate
   (§7), by `max_abs_diff == 0` on every one of the timed replicates in both
   campaigns (§8.3), and by the upstream-equivalence wrapper run four times —
   two bases × {candidate, unchanged base} — returning reports that agree in
   every printed field, with all eight decode steps bit-exact against the
   vendored oracle and the single 1-ULP prefill row shared byte-for-byte with
   the untouched frontier (§8.1, §8.1.1).
3. **The halved planes are the ones that actually execute** — under a
   *within-build* reading of the activation artifacts, not a between-arm log
   diff. The base already ships a packed routed gate/up bank and emits the
   identical `mlxfast:` strings from its own full-width code, so the two arms'
   diagnostic sets are indistinguishable; an earlier draft's claim to the
   contrary is withdrawn in §8.2. Gate/up is certified in every candidate
   replicate by a log line the candidate source can only reach past the halving
   guard; `down` has no such line and is certified by dynamic trace on both
   bases, in runs kept out of the timing pool because the tracer costs the same
   order as the effect (§8.2).
4. **The relocation forced by the byte ceiling changed nothing.** Two added
   lines, both braces (§1.1).

### What is not established

- **Nothing about the M5.** This is an M4 Pro (`applegpu_g16s`, gen 16). It does
  not select `_nax`, and the ranked host does. This arm changes no `_nax`
  source and no prefill kernel, so the decode direction should transfer — but
  "should transfer" is a hypothesis, not a measurement, and only the official
  runner can settle it.
- **A confident point estimate.** §8.3's honest range across defensible
  poolings is wide relative to the effect. The design sits at ~3σ against the
  MDE by construction (§5.1); that was known and pre-registered, and it is the
  reason `down` had to be in scope.
- **That the M4 decode difference is the mechanism at all.** This is the
  finding I least wanted and the one the advisor most needs. The prefill
  negative control — an axis this change *provably cannot reach*, because every
  edited kernel is a one-token QMV kernel behind the
  `x.dims(1, 1, hiddenSize)` gate — moved **+0.76 %** in campaign B and
  **+0.61 %** in campaign A, i.e. by the same margin as decode, with the same
  p-value, on all three estimators (§8.3.3). Subtract that offset and campaign
  B's decode effect is ≈ 0. Two campaigns on two bases with two different
  control constructions reproduce the offset, so it is not a one-off. **The M4
  evidence in this report is consistent with the +0.834 % roofline bound and
  equally consistent with no effect at all**; it does not discriminate between
  them, and I am not going to present it as if it does.

### Recommendation

**Send it to the official M5 runner, and do not spend more M4 hours on it.**

To be explicit about what this recommendation now rests on: **not** the M4
timing. §8.3.3 removes the M4 numbers from the evidence column. The case is
(a) a bandwidth-roofline lower bound of +0.834 % derived from #73's measured
routed rate on the ranked geometry, and (b) a risk side that is as close to
zero as this programme gets. That is a weaker case than the one I expected to
be writing, and the advisor should weigh it as such — it is a "cheap lottery
ticket with a physics argument behind it", not a demonstrated win.

The reasoning, in order of weight:

1. **The risk side is as close to zero as this programme gets.** The transform
   is bit-identical by construction, by an eight-control differential
   certificate, and by `max_abs_diff == 0` on every timed replicate in both
   campaigns. Memory is net-neutral. Nothing outside the accepted quantization
   envelope is touched — the change does not re-quantize anything; it removes a
   provably redundant copy of bytes the checkpoint already duplicates.
2. **M4 cannot settle an effect this size, and more M4 replicates will not
   change that.** This is now demonstrated rather than asserted: the negative
   control moves as much as the treatment (§8.3.3). More replicates shrink the
   *sampling* error but do nothing about a systematic candidate-favouring
   offset, and the offset is the binding term. Halving the confidence interval
   needs 4× the replicates; at ~3 minutes a run plus a thermal gate, that is
   hours spent sharpening a number whose bias I cannot bound on this host.
3. **The M5 is where the effect is both larger in relative terms and cheaper to
   measure.** The ranked wrapper runs candidate and baseline back to back in one
   session behind the same thermal gate, which removes exactly the drift that
   dominates the M4 estimate. The roofline lower bound of +0.834 % (§5.1) is
   derived from #73's measured *routed* rate on the ranked geometry, not from
   this host.
4. **Do not bundle it.** §0.9.11's rule against stacking unmeasured mechanisms
   applies with full force here: the whole value of this arm is that it isolates
   one clean, provable byte reduction. Folding it into a larger routed-traffic
   change before it has a paired M5 number would destroy the attribution that
   makes it worth having.

If the advisor would rather not spend a ranked slot on a sub-1 % candidate, the
fallback is to **bank §3–§7 and shelve §8**: the census result, the structural
proof from `fp_quantized.h`, and the differential certificate are reusable
assets that stand on their own, and any future arm that wants to narrow a
group-32 NVFP4 plane — routed, shared, or otherwise — can cite them instead of
re-deriving them. In that case the code should stay on the branch, unmerged,
rather than being promoted on an M4 number that cannot carry it.

The one thing I would *not* do is request more local replication. §8.3 already
reports the honest range; another three runs would narrow it by about a third
and still leave the decision resting on a cross-architecture extrapolation.

### Suggested follow-ups (not implemented here)

- **Step 2, the real prize, is byte-blocked before it is compute-blocked.**
  §9 shows 26,943 B of aggregate headroom. Any repack that would let the
  *shared* expert plane (3.83 MB/step) or a combined narrow+halved
  representation land must be written into `Sources/MLXFastTransform/` or
  `LagunaRuntimeWeights.swift` and must be budgeted in bytes first. This is now
  the binding constraint on this whole line of work and the advisor may want to
  prioritise fern's ~24 kB Metal-literal reclamation on that basis alone,
  independent of its own timing value.
- **Compose with #35 rather than merely coexisting with it.** Frieren narrows
  the *alphabet* (128 B → 65 B); this arm halves the *width* (32 B → 16 B).
  They are orthogonal transforms of the same array. On the routed plane the two
  could in principle stack to ~4× narrowing. Her `groups % 64 == 0` guard in
  `lagunaLaneMajorNVFP4ScaleBank:850-853` is the first thing that would need to
  move. I did not attempt this; it is a different experiment with a different
  correctness surface.
- **The fourth kernel is compiled but never exercised.**
  `lagunaRoutedDownReduceKernel` is correctness-checked and byte-halved but the
  shared-down-residual kernel takes precedence on the scored shape, so it never
  fires in the timed window (§8.2). Either it is dead on this shape and should
  be deleted for bytes, or there is a shape where it wins and nobody has found
  it. Worth ten minutes from whoever owns that dispatch.
- **Re-derive the 14.862 %/ms constant, or retire it.** §5.1 documents a ~15 %
  disagreement between it and the direct `0.75·δ/T` linearisation. Every arm in
  this campaign is converting µs to score through one of these; they should
  agree, and right now the choice quietly moves every roofline estimate by
  15 %.
