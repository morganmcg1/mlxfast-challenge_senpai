# Byte-recovery census — editable submission surface

Advisor-commissioned audit, 2026-08-07. Base `627c4973aa02930808a0a96bfbfdbc3ee486a4c3`
(byte-identical on the scored surface to the current advisor head). Read-only: no files
were modified, no builds run.

This is the assignment source-of-truth for the queued byte-recovery cleanup. It
**corrects four entries** in the old cleanup backlog — see §7.

---

## 1. Budget facts

`senpai/check-editable-budget.sh` at the base:

```
current=2950855/3000000  headroom=49145  growth=0/262144  files=142 (base=142)
```

Caps: `MAX_TOTAL_BYTES=3000000`, `MAX_FILE_BYTES=524288`, `MAX_GROWTH_BYTES=262144`.
`editablePaths` has 97 entries; 4 are directories expanded by `find -type f` → 142 files.

### ⚠ Second, previously-untracked constraint: the per-file cap

`Sources/MLXFastModel/LagunaRuntimeModel.swift` is **468,336 B** against the
**524,288 B per-file cap** ⇒ only **55,952 B of per-file headroom**. Any large addition
to that single file hits the *file* cap well before the *total* cap. Every concurrent
decode assignment edits this file, so this is a live constraint, not a cleanup nicety.

### Where the 2.95 MB lives

| bytes | share | group |
|---|---|---|
| 861,073 | 29.2% | `Vendor/mlx-swift/.../backend/metal/kernels/**` `.h`/`.metal` (80 files) |
| 773,714 | 26.2% | `Vendor/mlx-swift/.../mlx-generated/*.cpp` (29 files) |
| 468,336 | 15.9% | `Sources/MLXFastModel/LagunaRuntimeModel.swift` |
| ~848,000 | 28.7% | everything else |

---

## 2. Ranked levers

### Lever 1 — relocate measurement narrative out of the four `Sources/MLXFastModel/*.swift` files — **≈69,000 B target, LOW risk**

Comment-only-line bytes (lines whose first non-space chars are `//`, `///`, `*`, `/*`):

| file | comment bytes | % of file |
|---|---|---|
| `LagunaRuntimeModel.swift` | 120,960 | 25.8% |
| `LagunaLmHeadPrune.swift` | 23,687 | 43.1% |
| `LagunaRuntimeWeights.swift` | 23,194 | 43.0% |
| `LagunaConfig.swift` | 4,753 | 10.6% |
| **subtotal** | **172,594** | |

Comments are not compiled ⇒ removal is byte-for-byte behaviour-neutral. This prose is
campaign-authored measurement narrative (receipt IDs, µs/token deltas, ablation
history), not API documentation. `notes/` and `research/` are **not** in `editablePaths`
(verified: zero matches), so the narrative moves there at zero submitted-byte cost with
a one-line pointer left behind.

**Relocate, do not delete.** Losing the receipt-linked ablation history would be a real
cost; moving it is free.

At a conservative 40% relocation this recovers ≈69,000 B (headroom 49,145 → ≈118,000 B)
and drops `LagunaRuntimeModel.swift` to ≈420 KB (per-file headroom 55,952 → ≈104,000 B).
Ceiling if fully stripped: 172,594 B.

Comment-byte figures are ±2% (a `*`-leading continuation line could be code).

**Do not apply this lever inside `Vendor/mlx-swift/Source/Cmlx/`** — see §3.

### Lever 2 — delete Laguna-dead transform sidecar coders — **32,605 B, MED**

- `Sources/MLXFastTransform/AffineMetadataCoding.swift` (16,378 B, whole file)
- `Sources/MLXFastTransform/TiedHeadMetadataCoding.swift` (15,627 B, whole file)
- collapse `Sources/MLXFastTransform/Transform.swift:240-269` (`switch modelFamily`, ~600 B)

Dead for Laguna: the only callers are `Transform.swift:242` and `:249`, both inside
`case .gemma4:` (line 241). The `case .laguna:` arm emits nothing and states in-source
that `docs/laguna-weight-contract.md` forbids sidecars in the Poolside v2 contract. No
runtime consumer: `grep -rn "mlxfast-projection-metadata\|mlxfast-tied-head-metadata"
--include=*.swift .` outside `Sources/MLXFastTransform/` returns zero hits.

MED because `.gemma4` **is** exercised by the non-editable trusted tests
(`Tests/MLXFastTests/TransformTests.swift`: `family: .gemma4` at :143, fixture at :1030,
used at :15/:84/:126/:984/:1035), including
`transformVerifierRejectsStaleExtraGeneratedFile` (:850) and
`transformAtomicallyReplacesExistingOutputAndRemovesStaleFiles` (:696).

Mitigating: **no trusted test asserts sidecar filenames, tensor counts, or byte counts.**
`grep -rn "mlxfast-\|generatedFiles\|tensorByteCount\|outputTensorByteCount"
Tests/MLXFastTests/TransformTests.swift` → 2 hits (:739, :1191), both
`.mlxfast-transform-` staging-dir prefixes.
`Sources/MLXFastTrustedHarness/TransformVerification.swift` has one `mlxfast-` hit (:71,
a temp UUID dir) and no `AffineMetadata`/`TiedHead` reference; it does a fresh-run
comparison, which stays self-consistent when both runs emit nothing.

Gate: `swift test --force-resolved-versions`, then `git checkout -- Package.resolved`.
This is the one claim in the census that was not verifiable without running the suite.

**HIGH — do not delete** in the same directory: `LagunaCheckpointValidation.swift`
(23,378 B; 6 refs from `LagunaArtifactContractTests.swift`,
`LagunaArtifactFixtureSupport.swift`, `Transform.swift:183,187,645`) and
`CheckpointIndex.swift` (3,810 B; refs from `Sources/MLXFastCLI/main.swift`,
`Tests/MLXFastTests/CheckpointIndexTests.swift`).

### Lever 3 — delete `DARKBLOOM_LMHEAD_ROWMAJOR_REFINE` — **7,985 B, MED**

All refs in `Sources/MLXFastModel/LagunaLmHeadPrune.swift` (:104, :106, :108, :856,
:1140, :1141).

| region | lines | bytes |
|---|---|---|
| flag decl + doc comment | 98-109 | 724 |
| `lagunaLmHeadRowMajorRefinedExactKernel` decl + doc | 824-976 | 6,759 |
| call-site ternary arm | 1140-1150 | 502 |

**⚠ Correction to the backlog: this flag is ALREADY DEFAULT OFF.** The gate at
`:106-108` reads `environment["DARKBLOOM_LMHEAD_ROWMAJOR_REFINE"] == "1"`. Its own doc
comment (:98-105) records "DEFAULT OFF after official receipt `99b71258` measured it
**+24.6 µs/token on the ranked M5** despite −63.7 µs on M4". **There is no default flip
left to take and no score to recover — this lever is bytes only.**

Structural edit: the call site is `let assembled =` (1137) / `refine` (1138) / `? (`
(1139) / flag (1140) / `? …RowMajor…(` (1141) … `)[0]` (1150) /
`: lagunaLmHeadRefinedExactKernel(` (1151). Deleting 1140-1150 requires collapsing
`? (` → `?` at 1139 and dropping the matching `)` after the kept arm.

**Keep** the sibling `lagunaLmHeadFusedRefinementEnabled` at :94
(`DARKBLOOM_LMHEAD_FUSED_REFINEMENT != "0"`, default ON) — it is the `refine` gate.

### Lever 4 — delete `DARKBLOOM_EXPERT_BK128` + its now-dead assert — **2,693 B, MED**

All in `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp`:

| region | lines | bytes |
|---|---|---|
| doc comment + `darkbloom_expert_bk128()` (fn :1383, env read :1384) | 1364-1387 | 1,277 |
| call-site comment + `if (…) { bk = 128; }` (live call :1715) | 1709-1720 | 688 |
| positive kernel-selection assert (`"[gather_qmm_rhs_nax] widened k-block escaped…"`) | 1734-1744 | 728 |

The assert exists *only* because `bk != 64` is reachable from the gate above it. With
BK128 removed `bk` is always 64 and the assert is provably dead — the backlog's ~5,164 B
estimate was high on the flag itself and missed this dependent block.

Keep `laguna_moe_shape` (1707-1708) — still used by `expert_aligned` at :1732.

In-source rationale for removal on merit: BK128 is unmeasurable on any available host
(MLX only selects `_nax` on GPU generation ≥ 17), modelled at ~0.1–0.3% prefill /
~0.03–0.08% score against a ±0.73% local MDE, and mutually exclusive with
double-buffering (2×17408 > 32768 B threadgroup limit).

**Requires a metallib rebuild — see §3.**

### Lever 5 — `fusedTailGateLogits` constant-nil placeholder — **666 B, LOW (provably unreachable)**

`Sources/MLXFastModel/LagunaRuntimeModel.swift`: comment + `let fusedTailGateLogits:
MLXArray? = nil` at 5756-5760 (355 B), and the unreachable `if let fusedTailGateLogits
{ … }` branch at 5787-5791 (311 B).

The binding is a local `let … = nil`, so the `if let` can never bind. Comment 5756-5759
confirms the fused tail norm+QKV+gate kernel "was removed after the r=1-regime re-sweep
re-measured it +2.7%… the placeholder keeps the downstream defer/eager gate-activation
plumbing unchanged." Deletion requires collapsing
`} else if _nativeAffineQKVGateRows == nHeads {` at :5792 into a leading `if`.
`grep ": MLXArray? = nil"` finds only default parameter values elsewhere — this is the
unique instance.

Stage separately from any INT8 work: it sits immediately after the §4 region.

### Lever 6 — `mergedSharedActivated` write-never variable — **345 B, LOW**

`LagunaRuntimeModel.swift:10031-10035` (comment + `var mergedSharedActivated: MLXArray?`
at :10035). Exactly two occurrences in the corpus and **no assignment** ⇒ always `nil`;
the compiler already warns. Its comment claims it is "Set … below", but the merged
routed+shared dispatch was removed and orphaned it. Fix: drop the argument at :10110 —
`sharedActivation:` has a `= nil` default at :8332.

### Lever 7 — two unread `…Enabled` constants — **≈120 B, LOW**

`LagunaRuntimeModel.swift:307` `let lagunaNativeAffineQKVEnabled` and `:380`
`let lagunaNativeAffineOProjEnabled` — declaration is the only occurrence.
`lagunaNativeAffineGProjEnabled` at :419 **is** read at :5515 — keep it.

A whole-corpus identifier census over `Sources/**` + `Vendor/mlx-swift-lm/Libraries/**`
found these two and no others, so **there is no larger harvest of fully-dead flags.**

---

## 3. Operational trap: the vendored-metal fingerprint

`Sources/MLXFastTrustedHarness/VendoredMetalFingerprint.swift:19-21` fingerprints
**every file** under `Vendor/mlx-swift/Source/Cmlx/{mlx,mlx-generated}` (per-file
SHA-256, re-hashed). It is the Swift twin of `tools/build-mlx-metallib.sh`'s
`compute_vendored_metal_fingerprint`, and the trusted CLI **recomputes it immediately
before spawning the participant worker** so a stale metallib cannot mask edits.

Consequence: a **comment-only** edit anywhere in that tree changes the fingerprint and
requires re-running `tools/build-mlx-metallib.sh` / `./setup.sh`. This applies to
Lever 4 and to any incidental vendor-tree touch by any assignment. Sequence Lever 4
with its own rebuild; do not bundle it with Lever 1.

---

## 4. The INT8 fold/fused-QKV exclusion — reachable, but only via an ablation flag

**The transform is irrelevant. The INT8 attention banks are produced at runtime.**

Chain of evidence in `Sources/MLXFastModel/LagunaRuntimeModel.swift`:

- `lagunaNativeAffineWeight(_:layer:)` (**:2905-2937**) re-quantizes a BF16 checkpoint
  weight in-process. Its **fallback tail at :2929-2937** is exactly
  `quantized(source, groupSize: 32, bits: 8, mode: .affine)` with `guard biases != nil`
  — it *constructs* the bank the guard tests for.
- Its **NVFP4 branch (:2914-2928)** fires when `lagunaNativeAffineNVFP4From != nil &&
  layer >= from && dim(1) % 16 == 0`. `lagunaNativeAffineNVFP4From` (**:2861-2867**)
  defaults to **0** (`DARKBLOOM_NATIVE_AFFINE_NVFP4 != "0"`, `…_NVFP4_FROM ?? "0"`), and
  Q/K/V have `dim(1) == hiddenSize == 2048`. **On the shipped default every layer's
  Q/K/V bank is NVFP4 group-16 bits-4**, `foldGateIntoBank` (:5526-5527) is `false`, and
  the `lagunaFusedNormAffineQKV` guard at :5738-5744 is not taken.
- The g_proj gate bank is separate: `:389-396` states it is "**ALWAYS group-32 INT8**
  (never the NVFP4 tail window)", and `:5535-5539` routes it to `_nativeAffineGProj`
  with its own dispatch precisely because the QKV bank is NVFP4. So the
  `else if let affineGate = _nativeAffineGProj` arm at **:5798 is the live default path**.
- Nothing in `Sources/MLXFastTransform/` emits any attention bank. The pinned Laguna
  config is NVFP4 4-bit group-16; the only other family, `.gemma4`, is 4-bit group-64
  affine. Neither is bits==8 / group==32.

**Verdict:** `LagunaRuntimeModel.swift:5510-5533` (1,250 B) and `:5733-5744` (760 B),
≈2,010 B total, are reachable only by setting `DARKBLOOM_NATIVE_AFFINE_NVFP4=0` (or
`…_NVFP4_FROM > 0`) — mechanically the same category as Lever 4, i.e. **MED, not HIGH**.

**Recommendation: still do not delete.** 2 KB is 3% of the LOW-risk pool, while these
lines are the only in-binary exact ablation/fallback for the entire accepted attention
quantization envelope — the largest shipped optimization family and the one most exposed
to a hidden-gate surprise. Keep the HIGH label as an *operational* rule.

---

## 5. Negative findings — backlog items that pay nothing

- **The "≈9 near-duplicate `.metal` variants" → ZERO recoverable.** A pairwise scan over
  all 113 `.h`/`.cpp`/`.metal` files in the editable surface found 21 pairs above 0.75
  similarity, and **every high-similarity pair is a `kernels/X.h` ↔ `mlx-generated/X.cpp`
  AOT/JIT twin** (`quantized.h`/`quantized.cpp` 0.996; `quantized_nax.h`/`.cpp` 0.994;
  `fp_quantized_nax.h`/`.cpp` 0.963). AGENTS.md requires both to exist and stay
  consistent. The only non-twin pairs are `steel/gemm/gemm.h` ↔ `steel/attn/attn.h`
  (0.995) and `steel/gemm/transforms.h` ↔ `steel/attn/transforms.h` (0.986) — upstream
  vendor headers included by different kernels — and `steel_gemm_fused_nax.metal` ↔
  `steel_gemm_fused.metal` (0.785), the live `_nax` variant the M5 selects. This also
  explains the 773,714 B of `mlx-generated` as structurally non-recoverable.
- **"Stale comments" at `quantized.cpp:1351-1363` and `:1530-1533` → not stale.**
  1350-1362 is the live doc for `darkbloom_expert_stage_wideld()` (:1359, default ON);
  1523-1540 is the live doc for `darkbloom_stage_wide_load_ok()` (:1541).
- **`deferGateActivation` (`LagunaRuntimeModel.swift:5838-5852`) → HIGH, load-bearing.**
  The backlog called it "non-load-bearing"; that is wrong. It is computed, not constant:
  `lagunaFusedGateProductEnabled && lagunaUseNativeAffineOProj(layer:) &&
  _nativeAffineOProj != nil && wo.bias == nil` (:5839-5842), and all three gates are
  **default ON** (`:3737` `DARKBLOOM_FUSED_GATE_PRODUCT != "0"`; `:372-379`
  `DARKBLOOM_NATIVE_AFFINE_OPROJ != "0"` with `…_OPROJ_LAYERS` defaulting to `"40"`).
  It is read twice with behavioural effect — `:5844/:5846` selects deferred vs eager
  `softplus`, `:5852` supplies the 5th tuple element to `fusedNormQKV`. **Do not touch**,
  and the dependent "decode-unreachable `softplus`" sub-item falls with it.

---

## 6. Ranked summary

| # | lever | location | bytes | risk |
|---|---|---|---|---|
| 1 | Relocate narrative to non-editable `notes/` | `Sources/MLXFastModel/{LagunaRuntimeModel,LagunaLmHeadPrune,LagunaRuntimeWeights,LagunaConfig}.swift` | **69,000** target / 172,594 ceiling | **LOW** |
| 2 | Delete Laguna-dead sidecar coders | `MLXFastTransform/{AffineMetadataCoding,TiedHeadMetadataCoding}.swift`, `Transform.swift:240-269` | 32,605 | MED |
| 3 | Delete rowmajor refine (bytes only — already default OFF) | `LagunaLmHeadPrune.swift:98-109, 824-976, 1140-1150` | 7,985 | MED |
| 4 | Delete BK128 + dead assert | `quantized.cpp:1364-1387, 1709-1720, 1734-1744` | 2,693 | MED |
| 5 | Constant-nil placeholder + unreachable branch | `LagunaRuntimeModel.swift:5756-5760, 5787-5791` | 666 | **LOW** |
| 6 | Write-never variable | `LagunaRuntimeModel.swift:10031-10035` | 345 | **LOW** |
| 7 | Two unread constants | `LagunaRuntimeModel.swift:307, :380` | ~120 | **LOW** |
| — | INT8 fold/fused-QKV | `LagunaRuntimeModel.swift:5510-5533, 5733-5744` | *(2,010)* | HIGH by policy |
| — | `deferGateActivation` | `LagunaRuntimeModel.swift:5838-5852` | *(0)* | **HIGH — live** |
| — | `.h`/`.cpp` "duplicates" | 21 pairs, all AOT/JIT twins | 0 | — |
| — | `quantized.cpp` "stale" comments | live lever docs | 0 | — |

**LOW-risk total ≈ 70,131 B** → headroom 49,145 → **≈119,276 B**.
LOW-risk ceiling (100% comment relocation) ≈ 173,725 B → headroom ≈ 222,870 B.
All LOW + MED at the conservative comment target ≈ 113,414 B → headroom ≈ 162,559 B.

## 7. Corrections this census makes to the old cleanup backlog

1. `DARKBLOOM_LMHEAD_ROWMAJOR_REFINE` is **already default OFF**. The "+0.2237% `ns`
   from flipping the default" line was wrong — deletion is a **bytes-only** lever.
2. The "≈9 near-duplicate `.metal` variants" recover **0 B**.
3. The `quantized.cpp` "stale comments" are **live** documentation, 0 B.
4. `deferGateActivation` is **load-bearing**, not a dead flag.
5. BK128 is **2,693 B**, not ~5,164 B (smaller flag, plus a dependent dead assert).
6. New: the **per-file 524,288 B cap** on `LagunaRuntimeModel.swift` (55,952 B headroom).
7. New: the **vendored-metal fingerprint** makes even comment edits under
   `Vendor/mlx-swift/Source/Cmlx/` require a metallib rebuild.
8. New: the INT8 exclusion is mechanically MED, and reachable only via
   `DARKBLOOM_NATIVE_AFFINE_NVFP4=0`.

## 8. Suggested sequencing for the cleanup assignment

1. **Lever 1 alone, first PR.** Zero build risk, no metallib rebuild, no test exposure,
   and it fixes the per-file-cap pressure. Instruct *relocate to `notes/`*, not delete.
2. **Levers 5+6+7** in the same PR or immediately after —
   `swift build -c release --force-resolved-versions` is sufficient proof; Lever 6 also
   clears a live compiler warning.
3. **Lever 2 as its own PR**, gated on `swift test --force-resolved-versions` then
   `git checkout -- Package.resolved`.
4. **Levers 3+4 last**, each with `./benchmark.sh --local-iterate`, and Lever 4 with a
   mandatory `./setup.sh` / `tools/build-mlx-metallib.sh` rebuild (§3).
5. Leave §4 alone.

**Next unresolved read:** Lever 2's `swift test` outcome. Also untriaged —
`Vendor/mlx-swift-lm/Libraries/MLXLMCommon/{KVCache,Evaluate}.swift` hold
24,235 + 27,465 comment bytes; if Lever 1 under-delivers that is the next ≈50 KB, and
being outside the fingerprinted tree it stays LOW risk.
