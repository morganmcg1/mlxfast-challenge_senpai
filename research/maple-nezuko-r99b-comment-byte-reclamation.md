# r99-B rung 1: comment-only byte reclamation from the vendored editable surface

Student: maple-nezuko · PR #548 · branch `maple-nezuko/comment-byte-reclamation`
BASE_SHA: `ad39bfc6c36c0a8257ee0de1916edafdbf52278e`

## Headline

**176,468 bytes freed. Global editable headroom 16,151 B -> 192,619 B (11.9x).**
Zero files under `Sources/` touched. Timing sits inside the revert-control
spread. Correctness exact (`max_abs_diff = 0`) on every measured leg.

```
base:      current=2983849/3000000  headroom=16151   growth=0                files=142
candidate: current=2807381/3000000  headroom=192619  growth=-176468/262144   files=142
```

26 of the 99 in-scope vendored files changed. Nothing under
`Sources/` and nothing under `Vendor/mlx-swift/Source/Cmlx/mlx-generated/`:

```
git diff --name-only ad39bfc -- Sources/                                      -> 0 files
git diff --name-only ad39bfc -- Vendor/mlx-swift/Source/Cmlx/mlx-generated/   -> 0 files
```

## Per-file reclamation

| bytes | file |
|---|---|
| 27,366 | `Evaluate.swift` |
| 25,189 | `quantized.cpp` |
| 24,221 | `KVCache.swift` |
| 18,073 | `sdpa_vector.h` |
| 13,739 | `BatchKVCache.swift` |
| 10,194 | `matmul.cpp` |
| 6,894 | `CompiledDecode.swift` |
| 6,699 | `CompilableRotatingKVCache.swift` |
| 6,318 | `SwitchLayers.swift` |
| 5,813 | `jit_kernels.cpp` |
| 5,417 | `CompilableKVCache.swift` |
| 5,078 | `LanguageModel.swift` |
| 3,717 | `BaseConfiguration.swift` |
| 3,678 | `AttentionUtils.swift` |
| 2,549 | `Laguna.swift` |
| 1,951 | `RoPEApplication.swift` |
| 1,904 | `rms_norm.metal` |
| 1,849 | `RoPEUtils.swift` |
| 1,663 | `DynamicSlice.swift` |
| 1,320 | `scaled_dot_product_attention.metal` |
| 1,279 | `arg_reduce.metal` |
| 972 | `JSONDecodingTypes.swift` |
| 212 | `rope.metal` |
| 147 | `gemv.metal` |
| 140 | `binary.metal` |
| 86 | `kernels.h` |

## Method

`research/nezuko_comment_tool.py` implements literal-aware C and Swift
segmenters (`census` / `canon [--naive]` / `strip`). It computes a **canonical
digest** of each file: the token stream with all comment bytes removed and
runs of whitespace collapsed. `cmd_strip` refuses to write any file whose
canonical digest changes, so a byte can only be removed if it provably carried
no code.

`PRESERVE` regex keeps license, provenance and tooling-directive comments:

```
copyright | (c) YYYY | © | SPDX- | licen[sc]e | clang-format | NOLINT
| swiftlint | swift-format | IWYU | pragma | =\s*\*/\s*$
```

The final alternative is the **argument-label rule**: Swift and C++ call sites
of the form `f(/* label = */ value)` are load-bearing for readability of
positional arguments and, more importantly, in some vendored C++ they sit
inside macro expansions. Preserving them cost 10,348 B of otherwise-eligible
pool. That was a deliberate trade: correctness of the guard over maximum bytes.

`research/nezuko_comment_tool_test.py`: 16 adversarial cases (comment markers
inside string literals, raw strings, char literals, nested block comments,
line continuations, Swift multiline strings and interpolation) plus 4 negative
controls that must *fail* if the segmenter is naive. FAILURES: 0.

## Verification

### Canonical equivalence
99/99 in-scope files: canonical digest identical before and after.
(`research/nezuko-r99b/canon-before.txt`, `canon-after.txt`)

### Round trip
`strip` -> `research/nezuko-r99b/restore-comments.sh` -> re-`strip`.
The restore reproduces `ad39bfc` **byte-identically** (`check-editable-budget.sh`
reports `growth=0`), and the second strip reproduces the patch bit-identically:
sha256 `65ae209ff56ed1467ef38c549b531343eed930ad5e45c969866f8f1963119082`, 348,012 B.

### Trusted-literal guard
`research/nezuko_text_assertion_guard.py`: 14,046 string literals appearing in
trusted (non-editable) test and harness sources checked against the stripped
tree. **0 source-exact losses.** 91 soft prose-shaped matches, all manually
confirmed to be English sentences in documentation, not assertions.

10 of the 26 changed files are named by trusted tests that read source **as
text** (`NAXSplitKGEMMTests`, `NVFP4QuantizedMMTests`, `SetupScriptTests`,
`DefaultTrackTests`, `BenchmarkScriptTests`, `LagunaArtifactContractTests`).
All pass.

### AOT metallib
`tools/build-mlx-metallib.sh` (exit 0):
`mlx.metallib` sha256 `8e8b18afaee1ed5a0190403f79a4cc74b9bebcb52b50c4b67d0ed91dc73097ec`,
158,502,072 B — **bit-identical to the baseline metallib**, re-confirmed after a
fresh re-checkout. This holds despite `rms_norm.metal` losing 37 lines and
`arg_reduce.metal` losing 26.

The metallib fingerprint sidecar changes (`5fbdc34b...` -> `53d786dd6fe8e043...`)
because it hashes *source text*, not compiled output. No expected fingerprint is
hardcoded anywhere, so nothing depends on its value.

### Unit tests
`swift test --force-resolved-versions`: **457 tests in 6 suites, 1 issue.**
`Package.resolved` untouched.

The single failure is environmental and provably unrelated:

```
SenpaiOperationalContractTests.swift:190:5
  senpaiOperationalGuidanceMatchesTheDeployedRankedPath()
```

Line 190 is exactly:

```swift
#expect(submitterTests.status == 0, Comment(rawValue: submitterTests.output))
```

which shells out to `/usr/bin/python3 senpai/test_submit_official.py`. Run
directly, that script fails **9/9 in `setUp`** at line 51:

```
['git','push','-qu','origin','main'] failed (2):
ERROR: refusing git push outside target repo;
cwd=.../tmp/mlxfast-submit-guard-*/candidate
```

That is the sandbox's own git-push policy hook rejecting the test fixture's
throwaway repo. It reads no file I modified; every file I modified is under
`Vendor/`.

### Upstream equivalence
`research/run_upstream_equivalence.sh`, **1 test executed** (not zero):

```
prefill: maxAbsLogitErr = 0.125, meanAbsLogitErr = 0.011933609
decode:  all 8 steps exactly 0
tokens:  match on all 9 steps
```

The same script on an **unchanged BASE checkout** produces a **byte-for-byte
identical report**. The prefill logit delta is a pre-existing non-M5 host
near-tie, not something this change introduced.

### Correctness under the benchmark harness
`./benchmark.sh --local-submit` on the candidate (exit 0):

```
passed_correctness: true      max_abs_diff: 0        partial_result: false
error: ""                     passed: true           first_failing_step/case/layer: null
golden_hash   f49e4c2cbc0d3ceee90195a3a12e1ff082636f8c031587485a9a2c10702b03d2
harness_hash  cd9e6d3058950974763f484d5a76c4db546ec73f95c5fcc1eadf8dfe01f1aee6
weights_hash  aff994300573c5e8589563fc9ff57cdcfb1ef9b49e14898be290a75a6b294b3d
```

## Timing: paired `--local-iterate`, control-first

Ordered control-A -> candidate -> control-B, all four legs green, no drift flags,
`passed_correctness=true` and `max_abs_diff=0` on every leg.

| leg | tree | prefill s/tok | decode s/tok | est score | ts |
|---|---|---|---|---|---|
| control-A | BASE | 0.00112423486 | 0.01295613118 | 0.79521 | 15:23:35Z |
| candidate | CAND | 0.00113816398 | 0.01307041178 | 0.78756 | 15:29:46Z |
| control-B | BASE | 0.00113764014 | 0.01302935091 | 0.78951 | 15:36:59Z |

**Revert-control spread (A vs B, both unchanged BASE): prefill +1.193%,
decode +0.565%, score -0.717%.**

Candidate vs nearest-in-time control B: prefill **+0.046%**, decode **+0.315%**.
Candidate vs control A: prefill +1.239%, decode +0.882%.

The candidate-vs-control decode difference (0.315%) is **smaller** than the
control-vs-control decode difference (0.565%). The candidate sits inside the
revert-control spread: **timing-neutral**, as predicted. The host shows clear
monotonic session drift (each successive run slower); a prior-session unchanged
baseline (2026-08-07: prefill 0.001125249673828125, decode 0.0129525791015625)
corroborates the BASE numbers.

`passed_prefill_speedup_floor: false` appears on **all** legs including both
unchanged BASE controls. That is an artifact of the pinned official-M5 baseline
constants evaluated on this non-M5 host, not a regression.

## Claim discipline: what is NOT claimed

`git diff --numstat ad39bfc f720e9e -- Vendor/` = added 55, deleted 3,072,
**net -3,017 lines**. Line numbers therefore shift, so `#line` / `__LINE__` /
`#file` positions embedded in the Swift and C++ binaries change.

- The **metallib is genuinely bit-identical** (verified twice).
- The **Swift/C++ binary is NOT claimed bit-identical.** It was not tested, and
  it almost certainly differs in `#line` literals and debug metadata.

The behavioral claim rests on canonical-digest equality plus the empirical
gates above, not on binary equality.

## New finding: the mlx-generated embedding invariant

`Tests/MLXFastTests/NVFP4QuantizedMMTests.swift:42,55` asserts that the **entire
body** (after `dropFirst(2)`) of `kernels/fp4.h` and `kernels/fp8.h` appears
**verbatim inside** `mlx-generated/fp_quantized.cpp`, `fp_quantized_nax.cpp`
and `unary_ops.cpp`.

**A comment-only edit to such a header therefore breaks a passing test without
changing any compiled code.** This is a cross-file *structural* invariant, so
the literal-based guard could not see it; `swift test` caught it, and
`research/nezuko_embedded_header_check.py` now generalises it.

`nezuko_embedded_header_check.py --exclusions BASE_SHA` derives the
do-not-touch set from BASE_SHA alone: **81 AOT sources**, written to
`research/nezuko-r99b/embedded-twin-exclusions.txt`. After applying it:

```
python3 research/nezuko_embedded_header_check.py ad39bfc  ->  embedded-twin risk: 0   (exit 0)
```

`mlx-generated/` is excluded entirely as policy. Forgone pool: 950 B (0.37%).

**Campaign lesson:** anyone editing `Vendor/mlx-swift/.../kernels/*.h` must
check this invariant first. It is invisible to symbol- and literal-level checks.

## License integrity

A first-pass checker flagged 17 apparent notice losses. All 17 were false
positives from bare `MIT` matching inside "li**mit**", "sub**mit**",
"com**mit**", "**Emit**". With `\bMIT\b`:

**0 license/copyright notice lines lost across all 26 files.**
(Checker reads both revisions straight from the git object store;
output `/tmp/nezuko_timing/license-check.txt`.)

## Operational hazard found: the controller-checkout race

The Senpai controller checks out the assignment branch whenever it delivers a
`student_assignment` event. The reflog shows checkouts at 15:23:46 and 15:37:18
— exactly matching event timestamps, and *inside* two of my timing legs' wall
windows. This can silently corrupt a mid-flight BASE control run.

Mitigation now in the pairing script: each leg records HEAD **and** a working-set
digest

```
git ls-files -z Sources Vendor | xargs -0 shasum -a 256 | shasum -a 256
```

before the build and again after the timed phase, and prints
`!!!!! TREE MOVED !!!!!` on mismatch. All four legs verified stable
(candidate surface `f08271ff2fed...`, BASE surface `54d33567568d...`).

**Recommendation: every paired BASE-vs-candidate timing run in this campaign
should carry this guard.** A silently-swapped tree produces a plausible,
completely wrong number.

## Rungs 2 and 3: prepared, not applied

### Rung 2 — `Sources/MLXFastModel/LagunaRuntimeModel.swift`
Measured, tooling committed, **nothing applied**.

- File is 511,418 B against the 524,288 B per-file cap: **12,870 B headroom.**
- Literal-aware census: **130,149 B** comment pool (25.4% of the file).
- `nezuko_relocate_tool.py plan` -> 282 blocks / 134,809 B prose;
  `darkbloom-flag` = 71 blocks, `receipt-provenance` = 4 blocks; sidecar 145,211 B.
- **Main hazard cleared:** no trusted test asserts on `LagunaRuntimeModel.swift`
  source text.
- `DARKBLOOM_*` flag docs and receipt-ID provenance must be **relocated
  verbatim** to `research/maple-nezuko-r99-lrm-provenance.md`, not deleted.

Whole-`Sources/` pool is 190,066 B: `LagunaRuntimeWeights.swift` 22,633,
`LagunaLmHeadPrune.swift` 18,179, `Transform.swift` 4,867, `LagunaConfig.swift`
4,523, `RuntimeStartupMemoryPolicy.swift` 3,867,
`LagunaCheckpointValidation.swift` 2,957.

**Rung 1 relieves the global cap; rung 2 relieves the per-file cap.** They are
independent instruments and rung 2 belongs in a follow-up, consistent with the
advisor's merge order (this PR -> #539/#543 -> rung 2).

Trap for whoever picks up rung 2: `research/frieren_comment_strip_check.sh` can
**never** pass on `LagunaRuntimeModel.swift` — its `normalise()` at lines 81-90
strips `//` regardless of literal state. A green result from that script proves
nothing.

### Rung 3a — dead Gemma4 metadata sidecars (32,005 B)
Advisor-confirmed live line item, not applied here.
`AffineMetadataCoding.swift` (16,378 B) + `TiedHeadMetadataCoding.swift`
(15,627 B). Only callers are the `case .gemma4:` arm of
`Sources/MLXFastTransform/Transform.swift:238,239,242,249,262,266`; the
`.laguna` arm at `:256-268` already emits empty reports. Runtime arrays come
from `lagunaIndexedAffineMetadata(scales:biases:)` at
`LagunaRuntimeModel.swift:2829-2870`, gated by
`DARKBLOOM_AFFINE_METADATA_INDEXED` at `:2825`.

Must be **kept** (non-editable `Tests/MLXFastTests/TransformTests.swift` uses
them): `TransformModelFamily.gemma4` (`Transform.swift:54`), detection return
`:595`, `isSelectedTextTowerKey` `.gemma4` arm `:496`, `makeRuntimeConfigData`
`.gemma4` arm `:634`.
