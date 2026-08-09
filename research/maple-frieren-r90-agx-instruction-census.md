# R90-A — AGX instruction census: toolchain, encoding study, and two priced levers

- PR: #481 · assignment `maple-r90-a-agx-instruction-census` · revision `r90-a-rev1`
- Student: maple-frieren
- Base: `codex/mlxfast-maple-20260804-advisor` @ `2500a40f2d0fbaff84c151b4d36308049784ff22`
- W&B run: `yb1u9icz` — https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/yb1u9icz
- Editable-path bytes added by this PR: **0**. Nothing under `Sources/`, `Vendor/`,
  `Tests/`, or any `benchmark.json` `editablePaths` entry is touched.
- Raw data: `research/maple-frieren-pr481-census.tsv` (91 rows, every arm, both archs).
- Probe harness: `senpai/tools/agx-census-probe/` (shell + `.metal`, no `Package.swift`).

## TL;DR

1. **The capability check passes.** `applegpu-nt` targets both `applegpu_g16s` and
   `applegpu_g17s` on this host, which is toolchain-identical to the advisor's.
2. **The advisor's headline calibration does not survive faithful compile flags.**
   `metal-size __compute` is *static code size*, not a dynamic instruction count.
   Under MLX's real flags the 480-iteration loop is **rolled** and censuses
   *smaller* than the 60-iteration one. "8 bytes per instruction, holding over 16×"
   is not reproducible.
3. **Bytes per source op ranges 4.0 → 14.0 across opcode classes** (3.5×), so
   `(bytes − floor) / 8` cannot be used as an instruction estimator for any class
   measured here. Use *matched-null differences within one opcode class* instead.
4. **Lever 2 (router transform C+D): the target kernel in the assignment was the
   wrong one, and transform C is already shipped.** The censused proxy passes the
   ≥40% gate on the selection region (57.9% / 57.6%) and on an analytic dynamic
   count (−67.3%), and **fails** it on whole-kernel static bytes (30.1% / 30.0%).
5. **S4-b (completed, not deferred) is the most actionable result.** The shipping
   `DARKBLOOM_NVFP4_NIBBLE_SPLIT=1` bit-pattern reconstruct is the cheapest of five
   real dequant variants on **both** archs, and it wins *more* on the ranked g17s
   (−19.68%) than on g16s (−17.68%). The `=2` "fewer live constants" control arm is
   **byte-identical to stock on both archs at both sizes** — a degenerate control.
6. **Standing rule 42 needs weakening.** Float-class slopes transfer g16s→g17s
   exactly; the integer MAD slope does **not** (12.0 vs 14.0 B/op, +16.7%), and it
   touches no memory, so it is outside the advisor's §2 memory exception.

---

## 1. Capability check (S0)

**Result: PASS.**

```
$ xcrun applegpu-nt -archs
... applegpu_g16s ... applegpu_g17s ...
```

Both required architectures are selectable. Host environment:

| item | value |
| --- | --- |
| macOS | 26.5.2 (build 25F84) |
| SDK | macosx26.5 |
| Metal compiler | 32023.883 (metalfe-32023.883) |
| `applegpu-nt` toolchain | v17.6.109.0 |

This matches the advisor's host exactly, so the recipe transfers.

> **Reporting limitation (please read).** §5 of the assignment asked me to post the
> capability-check outcome as an early PR comment so the advisor could re-scope
> before the rest of the work. **I have no tool that can post an interim PR
> comment.** My only GitHub-write capabilities are `submit_experiment_result`
> (terminal, once) and `respond_to_human_issue` (needs a human-authored issue
> addressed to me, which did not exist). I therefore recorded the result here and
> continued with the full plan, since the check passed and no re-scope was needed.
> If a future assignment depends on an early checkpoint, the advisor needs to
> either grant a comment tool or split it into its own micro-assignment.

## 2. Toolchain recipe (S1) — two corrections

Working recipe, per architecture, per entry point:

```bash
xcrun metal -std=metal4.0 -fno-fast-math -c X.metal -o X.air
xcrun metallib X.air -o X.metallib
printf '{ "pipelines": { "compute_pipelines": [ { "compute_function": "%s" } ] } }\n' "$FN" > s_$FN.mtlp-json
xcrun applegpu-nt -arch "$ARCH" -platform_version macos 26.0 26.5 -N s_$FN.mtlp-json X.metallib -o out.bin
xcrun metal-size -m out.bin
```

Implemented as `senpai/tools/agx-census-probe/census.sh`.

**Correction 1 — the `metal-size` field index is wrong in the assignment.**
Output is `\tSection __compute: 1792`, i.e. tab-led. The assignment's
`awk '/__compute/ {print $2}'` returns the literal string `__compute:`. The correct
extraction is `$NF` of the `/Section __compute:/` line.

**Correction 2 — entry points must be discovered from the metallib, not the source.**
Laguna kernels are macro/string generated, so grepping the `.metal` text for
`kernel void` is unreliable. Use:

```bash
xcrun metal-objdump --syms X.metallib | awk '/FUNCTION_LIST/ {print $NF}'
```

**Compile flags matter and must be MLX-faithful.** MLX's JIT sets
`options->setFastMathEnabled(false)` and
`setLanguageVersion(get_metal_version())`
(`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp:622-651`), and
`get_metal_version()` returns `MTL::LanguageVersion4_0` on macOS ≥ 26
(`device.cpp:37-49`). So the faithful flag pair is **`-std=metal4.0 -fno-fast-math`**.
This is not cosmetic: the identical `cal.metal` censuses `1792 / 2128 / 7088 / 1392`
under default flags and `1520 / 2096 / 1648 / 1632` under faithful flags.
**Absolute byte counts are compile-flag-dependent; every arm in a comparison must
share flags.**

Also confirmed for the record: MLX's custom-kernel path compiles
`metal::utils() + source_` (`backend/metal/custom_kernel.cpp:71`), where
`metal::utils()` is the 47,531-byte raw string in
`Vendor/mlx-swift/Source/Cmlx/mlx-generated/utils.cpp` delimited
`R"preamble(` … `)preamble";`. A verbose-printed generated source contains **no**
`#include` lines — the preamble supplies them. A standalone reproduction must
prepend that preamble.

**Dead ends, do not retry:** there is no AGX disassembler in this toolchain
(`applegpu-nt` emits an opaque `.bin`), and `metal-objdump --archive-headers`
yields nothing useful about instruction counts.

## 3. Calibration (S2) — the advisor's 8 B/instruction claim does not reproduce

`senpai/tools/agx-census-probe/cal.metal`, `-std=metal4.0 -fno-fast-math`:

| fn | g16s | g17s |
| --- | --- | --- |
| `k_empty` | 1520 | 1504 |
| `k_fma00` | 1520 | 1504 |
| `k_fma30` | 1808 | 1808 |
| `k_fma60` | 2096 | 2096 |
| `k_fma480` | **1648** | **1648** |
| `k_fold` | 1632 | 1632 |

- 30 → 60 straight-line FMAs: slope **9.6 B/op**, exactly linear on both archs.
  Not 8.000.
- **`k_fma480` (1648) < `k_fma60` (2096).** A 480-iteration loop censuses *smaller*
  than 60 straight-line ops because the compiler **rolled** it. `__compute` is a
  static section size. It cannot see dynamic trip count.

This single row invalidates the assignment's premise that the 8 B/instruction
relation "holds over a 16× range". It held in the advisor's measurement because
their flag set happened to unroll; it does not hold under MLX's flags. Everything
downstream in this report is therefore reported as **static bytes**, with dynamic
claims made only from explicit analytic counts.

## 4. Encoding-length study — bytes per op by opcode class

`senpai/tools/agx-census-probe/encoding.metal`. Matched signature, matched null
(`e_null`), N ∈ {32, 64, 128}. The marginal byte cost per source-level op is
identical for the 32→64 and 64→128 steps in every class, i.e. perfectly linear:

| class | g16s B/op | g17s B/op | Δ |
| --- | --- | --- | --- |
| float add, `(reg, reg)` | 4.0 | 4.0 | 0 |
| float FMA, `(reg, reg, reg)` | 6.0 | 6.0 | 0 |
| float FMA with loop-varying immediate | 11.0 | 11.0 | 0 |
| uint multiply-add, `(reg, reg, reg)` | **12.0** | **14.0** | **+16.7%** |

Arch floor difference is a constant 16 B (`e_null` 1600 vs 1584; `k_empty` 1520
vs 1504).

Two consequences.

**(a) `(bytes − floor) / 8` is not defensible.** The true divisor spans 4.0 → 14.0,
a 3.5× range, and depends on opcode class, operand form (register vs immediate),
and architecture. The only sound use of `__compute` is a *matched-null difference
inside a single opcode class*, which is how all of §6 and §7 below are built.

**(b) Standing rule 42 has a float/integer split.** All three float classes agree
bit-for-bit between g16s and g17s. The integer MAD class does not (12 → 14). That
op touches no memory, so it is **not** covered by the advisor's §2
memory-instruction exception. Rule 42 should be restated as: *float-ALU slopes
transfer across g16s/g17s; integer-ALU and memory-touching slopes must be measured
on the ranked architecture.* The §7 NVFP4 result reinforces this — every one of
those arms is integer-bit-manipulation heavy and every one shows a g17s/g16s
divergence.

## 5. S3 — mechanical extraction of a real Laguna kernel

`senpai/tools/agx-census-probe/gen_router_metal.sh` builds a standalone,
compilable `.metal` for the live decode router kernel using **only committed
sources**:

| artifact | contents |
| --- | --- |
| `preamble.metal` | `mlx-generated/utils.cpp` raw string, extracted between the `R"preamble(` delimiters |
| `header.metal` | `lagunaDecodeRouterOrdinalHeader`, `LagunaRuntimeModel.swift:9239-9262` |
| `body_raw.metal` / `body.metal` | kernel source builder, `LagunaRuntimeModel.swift:9798-9931` |
| `gen.metal` | byte-faithful reproduction of MLX's `write_signature` output (5,345 B) |
| `full.metal` | `preamble.metal` + `gen.metal` (52,756 B) |

The buffer attribute list is **rescanned at run time from the table in
`backend/common/metal_kernel.cpp`**, not hardcoded, so the generator does not
silently rot if MLX changes attribute spelling.

Reconstructed entry point and signature:

```
custom_kernel_laguna_prefill_router_tournament_ordinal_active64_v2_bfloat16_t_float_uint32_t_float
  const device bfloat16_t* logits          [[buffer(0)]]
  const device float*      correction_bias [[buffer(1)]]
  device uint32_t*         router_indices  [[buffer(2)]]
  device float*            router_scores   [[buffer(3)]]
  uint3 thread_position_in_threadgroup
  uint3 threadgroup_position_in_grid
```

No `_shape` / `_strides` / `_ndim` parameters are emitted (both inputs are
row-major contiguous). Both inputs are `device`, not `constant`, because
`max_constant_array_size = 8` (`backend/common/metal_kernel.cpp:19`).

**Byte-exactness verdict: the WEAKER gate is met; byte-exactness is UNPROVEN.**
- Met: `full.metal` compiles cleanly under the faithful flags, censuses to
  **g16s 4304 / g17s 4272**, and reproduced *identically* across two independent
  passes of `run_s4a.sh`, so the count is stable and reportable.
- Not met: I did not diff `gen.metal` against a live `verbose:` dump. Capturing one
  requires instrumenting `Sources/`, building `mlxfast-runtime-worker`, and running
  a model-holding decode step (the `research/frieren_pr35_r5a_dump.sh` route, which
  applies `research/frieren-pr35-r5a-dump.patch`, builds, then
  `git checkout -- Sources/`). That is a GPU, model-holding, editable-path-touching
  operation and is outside this assignment's zero-byte / no-GPU scope.
- Consequently: **treat 4304 / 4272 as the census of a faithful reconstruction, not
  as a proven census of the shipped kernel.** Any conclusion that depends on the
  absolute value rather than on a matched-null difference should be re-derived after
  a dump fixture exists.

## 6. Lever 2 — router transforms C and D

### 6.1 The assignment targeted the wrong kernel

The kernel actually dispatched on the decode path (all env flags at default) is
`lagunaPrefillRouterTournamentOrdinalKernel`, MLX name
`"laguna_prefill_router_tournament_ordinal_active64_v2"`:

| item | location |
| --- | --- |
| construction | `LagunaRuntimeModel.swift:9951-9958` |
| source builder | `LagunaRuntimeModel.swift:9798-9931` |
| header | `lagunaDecodeRouterOrdinalHeader`, `:9239-9262` |
| `laguna_router_ordinal_before` (verbatim) | `:9252-9261` (assignment cites stale `:9286-9294`) |
| test invocation | `lagunaPrefillRouterTournamentOrdinalForTesting`, `:9990-10010` |

Decode reuses the *prefill* tournament kernel with `rows: 1`. Invocation:
`grid: (256, rows, 1)`, `threadGroup: (256, 1, 1)`,
`outputShapes: [[1, rows, 8], [1, rows, 8]]`, `outputDTypes: [.uint32, .float32]`.

Gating, all default-ON (`!= "0"`): `DARKBLOOM_ROUTER_ORDINAL` (`:9300-9301`),
`DARKBLOOM_ROUTER_SCORE_TABLE` (`:9306-9307`),
`DARKBLOOM_DECODE_ROUTER_TOURNAMENT` (`:9352-9353`),
`DARKBLOOM_FUSED_ROUTER` (`:9450-9451`); dispatcher `lagunaDecodeRouterTop8`
(`:9418-9445`), decode arm (`:10098-10119`). It runs every decode step.

The sites the assignment cited — `laguna_router_top8_extract_round` and
`lagunaRouterTop8PrecomputedPrelude` — are a **different mechanism** and are now at
`:7667-7698` / `:7700-7711`. The line numbers in the assignment (7702-7736,
7745-7756, 7887-7920) are all stale.

### 6.2 Transform C is already shipped

The live kernel is literally named `active64_v2` and its source carries the
comment *"Sort one 64-candidate set instead of four duplicate copies … inactive
simdgroups can skip them entirely."* Transform C — collapsing the duplicated
per-simdgroup sorts to one 64-candidate set — is **already banked**. Only
transform D (monotone comparators / dropping the bitonic sequence mask) is
unpriced, and §6.4 prices it at ~1%.

### 6.3 Measured structure: 36 comparator stages, all rolled

From the extracted `body.metal`:

1. prologue (score table + ordinal packing)
2. **phase 1**: 15 bitonic stages over all 256 lanes (`body.metal:18-19`, nested loop)
3. local-top-8 extract into `candidate_ordinals/indices[64]` + barrier (`:42-45`)
4. **phase 2**: 15 bitonic stages guarded `if (lane < 64)` (`:56-58`)
5. cross-simdgroup: 1 threadgroup comparator + a rolled 5-stage loop (`:97`)
6. epilogue (`:111`)

All three comparator networks are written as loops, so **all three are rolled** by
the compiler. This is the structural reason static bytes mis-price this kernel.

### 6.4 S4-a census (both archs, matched nulls)

| arm | what it is | g16s | g17s |
| --- | --- | --- | --- |
| real | `full.metal` reconstruction | 4304 | 4272 |
| `r_cmp00` | **matched null**, 0 comparator stages | 2064 | 2048 |
| `r_cmp06` | rolled bitonic, 6 stages (k=3) | 2448 | 2448 |
| `r_cmp10` | rolled bitonic, 10 stages (k=4) | 2592 | 2608 |
| `r_cmp15` | rolled bitonic, 15 stages (k=5) | 2736 | 2752 |
| `r_u01` | explicitly unrolled, 1 stage | 2144 | 2144 |
| `r_u03` | explicitly unrolled, 3 stages | 2336 | 2336 |
| `r_u06` | explicitly unrolled, 6 stages | 2592 | 2592 |
| `r_u10` | explicitly unrolled, 10 stages | 2928 | 2928 |
| `r_u15` | explicitly unrolled, 15 stages | 3344 | 3344 |
| `r_m01` | monotone XCMP1 (transform D), 1 stage | 2128 | 2112 |
| `r_m03` | monotone XCMP1, 3 stages | 2288 | 2288 |
| `r_m05` | monotone XCMP1, 5 stages | 2464 | 2464 |
| `r_p15` | `#pragma clang loop unroll(full)`, 15 stages | 2736 | 2752 |
| `r_cd_mock` | C+D mock, 11 stages | 3008 | 2992 |

Derived:

- **Rolled form grows +144 B per additional bitonic outer `sequence` level,
  independent of that level's trip count** (g17s: +160 then +144). Static bytes are
  blind to how much work the loop actually does.
- **Unrolled slope = 85.7 B per comparator stage**, identical on both archs
  (per-step marginals 96.0, 85.3, 84.0, 83.2). At the FMA-class 6.1 B/op that is
  ≈14 source ops/stage; at a nominal 8 B/instruction, ≈10.7 instructions/stage.
- **Monotone XCMP1 = 84.0 (g16s) / 88.0 (g17s) B/stage.** Versus the 85.7
  unrolled baseline, dropping the bitonic direction mask saves **≈1 B/stage (~1%)**
  on g16s and is a small *regression* on g17s. **Transform D's value is entirely
  stage-count reduction, not mask elimination.** Do not budget for the mask.
- **`r_p15 == r_cmp15` exactly on both archs ⇒ `#pragma clang loop unroll(full)` is
  ignored** for this shape. And the rolled 15-stage form is 608 B (g16s) / 592 B
  (g17s) *smaller* than the unrolled one while executing the same 15 dynamic
  stages — a direct demonstration that static bytes and dynamic work move in
  opposite directions here.

### 6.5 The ≥40% gate: three scopes, two verdicts

The assignment's own arithmetic is internally inconsistent: §2 projects C+D at
−73% of the *prologue*, ≈ −12.5% of whole-kernel instructions, while §4 sets the
gate at ≥40% "on the censused region". A −12.5% whole-kernel projection can never
clear a ≥40% whole-kernel bar, so the gate must be read against the selection
region. I report all three scopes so the advisor can pick.

| scope | g16s | g17s | verdict |
| --- | --- | --- | --- |
| whole-kernel static bytes, `(real − mock) / real` | (4304−3008)/4304 = **30.11%** | (4272−2992)/4272 = **29.96%** | **FAIL** |
| censused region, `(real − mock) / (real − matched null)` | 1296/2240 = **57.86%** | 1280/2224 = **57.55%** | **PASS** |
| analytic dynamic comparator-simdgroup-units | real 162 → mock 53 = **−67.3%** | same | **PASS** |

The dynamic count assumes 256 threads = 8 simdgroups:
real = 15×8 (phase 1, all lanes) + 15×2 (phase 2, `lane<64`) + 5×2 + 1×2 = **162**;
mock = 6×8 + 5×1 = **53**.

**Headline caveat.** Static bytes *cannot* price a rolled-loop kernel; the
whole-kernel FAIL is an artifact of §3/§6.4, not evidence against the transform.
The region and dynamic scopes are the defensible ones and both pass comfortably.
Recommendation: treat Lever 2 as **worth one real implementation attempt**, but
size it from the dynamic stage count (162 → 53 comparator-simdgroup-units), not
from bytes.

**Non-negotiable constraints for any real implementation** (found while reading the
kernel, recorded so the next student does not rediscover them):
- `laguna_router_ordinal_before` at `LagunaRuntimeModel.swift:9252-9261` must be
  preserved **verbatim** — it defines the tie-break total order that the greedy
  token match depends on.
- It must pass `research/maple_fern_pr82_oracle.sh` (5,320 winner pairs, currently
  0 diffs).

## 7. S4-b — NVFP4 dequant encoding (completed, not deferred)

The assignment offered three toy variants. **None of them is what ships.** The live
NVFP4 dequant path is a *bit-pattern reconstruct*
(`LagunaRuntimeModel.swift:6596-6692`, `packedWordBody`) with three arms selected by
`lagunaNvfp4NibbleSplit` (`:6472-6478`, env `DARKBLOOM_NVFP4_NIBBLE_SPLIT`,
**default `1`**; design rationale in the doc comment at `:6429-6471`).
`senpai/tools/agx-census-probe/nvfp4.metal` censuses BP0/BP1/BP2 **verbatim** plus
the LUT and sign/magnitude alternatives, against a matched null `n_null`, at 4-group
(64-code) and 8-group (128-code) sizes.

Marginal bytes per 64 codes (8-arm minus 4-arm — this differencing is immune to
constant folding and to the arch floor):

| variant | g16s | g17s | B/code g16s | B/code g17s | vs BP0 g16s | vs BP0 g17s |
| --- | --- | --- | --- | --- | --- | --- |
| `bp0` — stock reconstruct | 2896 | 3008 | 45.25 | 47.00 | — | — |
| **`bp1` — nibble split (SHIPPING)** | **2384** | **2416** | **37.25** | **37.75** | **−17.68%** | **−19.68%** |
| `bp2` — 2-constant control | 2896 | 3008 | 45.25 | 47.00 | 0.00% | 0.00% |
| `lut` — `constant float[16]` | 3296 | 3312 | 51.50 | 51.75 | +13.81% | +10.11% |
| `sm` — sign/magnitude | 5152 | 5360 | 80.50 | 83.75 | +77.90% | +78.19% |

Three findings:

1. **BP1 is cheapest on both targets, and wins more on the ranked g17s.** It saves
   592 B/64 codes on g17s vs 512 B on g16s — 74 vs 64 bytes per packed word, i.e.
   ≈9.25 vs ≈8.0 instructions/word at a nominal 8 B. The doc comment at `:6429-6471`
   claims 6 ops/word saved; the real saving is larger. **This is the first
   ranked-host-architecture evidence validating an already-merged decision, and it
   says the default is correct and should stay.**
2. **BP2 is a degenerate control.** It is byte-identical to BP0 at *both* sizes on
   *both* archs. The compiler canonicalises the "fewer live constants" variant back
   to stock, so that arm cannot isolate register pressure and answers the doc
   comment's own open experimental question in the negative. Recommend retiring
   `DARKBLOOM_NVFP4_NIBBLE_SPLIT=2`.
3. **LUT loses on both targets at real kernel scale**, confirming the advisor's §5b
   expectation — but the gap narrows on g17s (+13.81% → +10.11%) exactly as their
   toy 16→10 result predicted, so the *direction* of their toy finding was right
   while its *magnitude* was not. Against the shipping BP1, LUT is +38.26% (g16s) /
   +37.09% (g17s). Sign/magnitude is ~1.78× BP0, far worse than the toy table's
   38-vs-24 suggested.

Rule-42 slope check on these integer-heavy mixes, g17s vs g16s: `bp0` +3.87%,
`bp1` +1.34%, `lut` +0.49%, `sm` +4.04%. Every arm diverges — see §4(b).

## 8. Honest limits

The six the advisor asked for:

1. **Instructions, not cycles.** `__compute` bytes are a static code-size proxy.
   The AGX cycle table is strongly non-uniform (RSHIFT32 ≈ 7.89, bitop ≈ 1.06,
   FFMA32 = 1.0), so a byte or instruction delta does not linearly imply a time
   delta. The §7 NVFP4 arms are shift-heavy and therefore the *most* exposed to
   this: BP1's byte win could be larger or smaller in cycles.
2. **Blind to scheduling.** Occupancy, issue slots, latency hiding, and memory
   stalls are invisible here. A kernel can shrink and get slower.
3. **Resolution.** Sections are 16 B-aligned, so a single-instruction difference
   can be invisible or can appear as a 16 B step. Treat any |Δ| ≤ 16 B as noise.
   All differences reported above are ≥ 128 B except the §6.4 monotone/unrolled
   comparison (≈1 B/stage over 4 stages), which I have explicitly labelled as ~1%
   and not load-bearing.
4. **No register counts.** `__descriptor` (96 B) and `__reflection` (368 B) were
   invariant across every arm, so this method cannot detect register-pressure or
   occupancy changes at all. This is the single biggest blind spot for §7, where
   the whole BP2 hypothesis was about live constants.
5. **`g17s = M5 Max` is an inference, not a documented fact.** It rests on the
   CpuSubtype ordering (g16s `0x1D3`, g17s `0x163`, g17p `0x143`, g18p `0x173`) and
   on g16s matching the known M4 generation. If that mapping is wrong, every
   "ranked host" claim above re-labels.
6. **Constant-folding hazard is real.** All toy arms must consume their results and
   must not be foldable. I mitigated by (a) always differencing two sizes of the
   same arm, and (b) matched nulls. §3's `k_fold` (1632) is the positive control
   showing folding does happen when you are careless.

Four more that this work exposed:

7. **Bytes ≠ instructions, per opcode class.** 4.0 → 14.0 B/op measured (§4). Any
   conversion to an instruction count is class-specific and should be stated as
   such.
8. **Loop rolling defeats static counting, and the unroll pragma is ignored**
   (§3, §6.4). For the router kernel — three loop-structured comparator networks —
   static bytes and dynamic work move in *opposite* directions.
9. **Absolute counts are compile-flag-dependent** (§2). Cross-report comparison of
   raw `__compute` values is only valid when flags match.
10. **`r_cd_mock` is a mock, not an implementation.** It reproduces the *stage
    count* of a C+D kernel, not its semantics. It produces no tokens and has not
    been through the oracle. The §6.5 numbers are a sizing estimate, nothing more.

## 9. Reproduction

```bash
cd senpai/tools/agx-census-probe
./census.sh cal.metal              # §3
./census.sh encoding.metal         # §4
./gen_router_metal.sh              # §5, emits full.metal
./run_s4a.sh                       # §5 real kernel + §6.4 arms
./census.sh nvfp4.metal            # §7
```

No GPU, no benchmark lock, no model weights, no network. Each script prints
`study arch fn compute_bytes` rows matching
`research/maple-frieren-pr481-census.tsv`.

W&B logging: `research/maple-frieren-pr481-log-wandb.py` reads that TSV and
publishes every raw arm plus the derived slopes and gate verdicts to run summary
(`yb1u9icz`).

## 10. Suggested follow-ups (not implemented)

1. **A real C+D router implementation**, sized from the dynamic stage count
   (162 → 53 comparator-simdgroup-units), preserving
   `laguna_router_ordinal_before` verbatim and gated on
   `research/maple_fern_pr82_oracle.sh`. Note transform C is already shipped, so
   the remaining headroom is smaller than the assignment assumed.
2. **A `verbose:`-dump fixture** captured in a separate GPU-enabled assignment, to
   upgrade §5 from the weaker gate to proven byte-exactness. `verbose:` is exposed
   to Swift on *invocation* (`Vendor/mlx-swift/Source/MLX/MLXFastKernel.swift:98-108`,
   `verbose: Bool = false` at `:106`, forwarded at `:148`) and prints at
   graph-construction time (`backend/common/metal_kernel.cpp:337-347`, before
   `array::make_arrays`), so it needs no eval — but it does need a worker build.
3. **Retire `DARKBLOOM_NVFP4_NIBBLE_SPLIT=2`** — §7 shows it is byte-identical to
   `=0` on both archs, so it is dead configuration surface.
4. **Revise standing rule 42** to "float-ALU slopes transfer g16s→g17s; integer-ALU
   and memory-touching slopes do not" (§4b, §7).
5. **Cycle-level, not byte-level, pricing.** Every conclusion here would be
   sharper with a cycle model. If the toolchain has no path to one, the honest
   alternative is to stop using static census for shift-heavy kernels and measure
   them on hardware instead.
