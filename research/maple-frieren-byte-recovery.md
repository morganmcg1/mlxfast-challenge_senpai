# Editable-surface byte recovery — maple-frieren, PR #288

`assignment_id` `maple-2026-08-07k-editable-byte-recovery` · `revision_id` `r1`
`BASE_SHA` `e1d070f256a1f5cef5a62a1d001dfbfe8b81bd0c`
Branch `maple-frieren/editable-byte-recovery`

**Capacity experiment, not a score experiment.** No ranked slot, no timing claim,
no `mlxfast submit`, no W&B run. The primary metric is
`editable_surface_bytes_recovered`.

## Headline

**76,269 bytes recovered.** Editable surface `2,950,855 → 2,874,586`;
headroom against the 3,000,000 B cap `49,145 → 125,414` (2.55x).

| lever | mechanism | bytes |
|---|---|---|
| 1 | relocate comment prose out of 4 scored files into non-submitted `notes/` | **42,036** |
| 2 | delete the two `.gemma4`-only metadata sidecar generators + collapse their call site | **34,233** |
| | **total** | **76,269** |

Lever 1 alone clears the assignment's hard stopping condition (≥ 40,000 B) and
lands just under the 55,000–65,000 B target; Lever 2 (the §6 stretch goal)
carries the combined result past it.

The two levers are **separate commits** so Lever 2 can be dropped without
losing Lever 1:

```
d641df7  Lever 2: delete the unreachable .gemma4 metadata sidecar generators (-34,233 B)
8237f43  Lever 1: relocate 42,036 B of comment prose out of four scored files into notes/
7061c25  research: add comment-relocation helper scripts
68f1eaa  senpai assignment: maple-2026-08-07k-editable-byte-recovery
e1d070f  BASE_SHA
```

## ⚠️ Prominent flag: Lever 2 touches `Sources/MLXFastTransform/Transform.swift`

`Transform.swift` is the offline transform driver and a plausible collision
point with other campaign work. It is isolated in `d641df7`. Lever 1 (`8237f43`)
touches only the four assigned files plus non-submitted `notes/` and
`research/`, and has **zero** overlap with the three live `LagunaRuntimeModel.swift`
fences (PR #268, PR #284, queued F1) or with `LagunaLmHeadPrune.swift`
(maple-nezuko, PR #284).

## Lever 1 — comment relocation (42,036 B)

### Per-file result

| file | base B | head B | saved B | code residue |
|---|---|---|---|---|
| `Vendor/mlx-swift-lm/Libraries/MLXLMCommon/Evaluate.swift` | 75,312 | 48,319 | **26,993** | IDENTICAL |
| `Vendor/mlx-swift-lm/Libraries/MLXLMCommon/KVCache.swift` | 81,231 | 68,533 | **12,698** | IDENTICAL |
| `Sources/MLXFastModel/LagunaRuntimeWeights.swift` | 53,980 | 51,943 | **2,037** | IDENTICAL |
| `Sources/MLXFastModel/LagunaConfig.swift` | 44,726 | 44,418 | **308** | IDENTICAL |
| total | 255,249 | 213,213 | **42,036** | |

Prose landed in four non-submitted note files (57,875 B, all outside
`editablePaths` — verified programmatically, `notes/` and `research/` are not
prefixes of any of the 97 entries, and the budget script's file count stayed at
140/142 rather than rising to 144):

```
notes/MLXLMCommon-Evaluate.notes.md    35,283
notes/MLXLMCommon-KVCache.notes.md     18,369
notes/LagunaRuntimeWeights.notes.md     3,407
notes/LagunaConfig.notes.md               816
```

Every relocated block is stored verbatim under a `## \`symbol\`` heading with a
`_relocated from lines A-B at base e1d070f2_` provenance line, so the prose is
recoverable by symbol, not just by diff archaeology.

### Proof that nothing but comments changed

`research/frieren_comment_strip_check.sh` normalises comments away identically
on BASE and HEAD and `cmp`s the code residue. Final output:

```
ok    Sources/MLXFastModel/LagunaRuntimeWeights.swift            head tripleQuotes=0    comment_lines_inside_literal=0
ok    Sources/MLXFastModel/LagunaConfig.swift                    base tripleQuotes=0    comment_lines_inside_literal=0
ok    Sources/MLXFastModel/LagunaConfig.swift                    head tripleQuotes=0    comment_lines_inside_literal=0
ok    Vendor/mlx-swift-lm/Libraries/MLXLMCommon/KVCache.swift    base tripleQuotes=0    comment_lines_inside_literal=0
ok    Vendor/mlx-swift-lm/Libraries/MLXLMCommon/KVCache.swift    head tripleQuotes=0    comment_lines_inside_literal=0
ok    Vendor/mlx-swift-lm/Libraries/MLXLMCommon/Evaluate.swift   base tripleQuotes=4    comment_lines_inside_literal=0
ok    Vendor/mlx-swift-lm/Libraries/MLXLMCommon/Evaluate.swift   head tripleQuotes=4    comment_lines_inside_literal=0

--- code residue equality (base vs head, comments normalised away) ---
ok    Sources/MLXFastModel/LagunaRuntimeWeights.swift            base=53980   head=51943   saved=2037    residue=30869 IDENTICAL
ok    Sources/MLXFastModel/LagunaConfig.swift                    base=44726   head=44418   saved=308     residue=39973 IDENTICAL
ok    Vendor/mlx-swift-lm/Libraries/MLXLMCommon/KVCache.swift    base=81231   head=68533   saved=12698   residue=56988 IDENTICAL
ok    Vendor/mlx-swift-lm/Libraries/MLXLMCommon/Evaluate.swift   base=75312   head=48319   saved=26993   residue=47938 IDENTICAL

--- totals ---
base bytes = 255249
head bytes = 213213
recovered  = 42036

RESULT: PASS (comment-only change on all 4 files)
```

The `tripleQuotes` precondition matters: a `//`-looking line inside a Swift
multi-line string literal is *code*. Evaluate.swift has 4 `"""` (L1049/1052,
L1874/1877) and the checker confirms `comment_lines_inside_literal=0` on both
sides for all four files.

### The relocation policy I actually applied

The discriminating rule, stated so it can be reused:

> **Relocate** a line iff it reports a *measurement outcome or session/receipt
> identity* (timings, percentages, Latin-square counts, ranked scores,
> `notes/NN §` references, log observations) **or** is *design history*.
> **Keep** every line that states a rule the code or kernel must obey, a flag's
> contract, a byte layout, or the derivation of a numeric constant.

Concretely:

1. **KEEP** every `///` abstract paragraph so each declaration retains a usable
   summary — *except* where a whole vendored file is provably unreachable from
   the scored worker and carries zero campaign knowledge, in which case
   relocate everything and leave one banner (see Evaluate.swift below).
2. **KEEP** non-obvious invariants, required ordering, aliasing/lifetime
   constraints, wire-format and key-name pins, "must match the Metal kernel"
   pins, upstream-deviation markers, `MARK:` separators, copyright.
3. **RELOCATE** long DocC bodies once the abstract is kept.
4. **RELOCATE** measurement narrative and design history.
5. **RELOCATE** (never delete) single-line comments that only restate the code.

This is what produces the 26,993 vs 2,037 asymmetry between Evaluate.swift and
LagunaRuntimeWeights.swift. It is a **content** distinction, not per-file
inconsistency: Evaluate.swift is inherited upstream prose about unreachable
code; LagunaRuntimeWeights.swift is campaign-authored invariant documentation
about the scored quantised-weight path.

### Evaluate.swift — why full relocation is safe (26,993 B, the largest single win)

Three independent arguments:

1. **Provenance.** The file has exactly one commit in this repository,
   `2ebae10` — the organizer's vendoring add. The campaign has never edited it.
2. **Zero campaign knowledge.**
   `grep -n "DARKBLOOM\|MLXFast\|notes/4\|ranked\|deviat\|upstream\|Laguna"`
   returns **no hits**. Nothing in this prose was learned here.
3. **Unreachable from the scored worker.**
   `grep -rn "TokenIterator\|generateTokens\|GenerateParameters\|generateTask\|LogitProcessor\|TopPSampler\|GenerateCompletionInfo" Sources/`
   returns exactly **one** hit:
   `LagunaRuntimeModel.swift:10998: public func newCache(parameters _: GenerateParameters?)`
   — an *ignored* protocol parameter. The generation machinery is never called
   by the scored worker, and `SpeculativeTokenIterator` plus the speculative
   `generate` overloads are forbidden outright by the serial non-speculative
   track rules.

So the prose is recoverable from two places (`notes/`, and upstream
`mlx-swift-lm` at the pinned vendoring base) and costs zero information about
the scored program. All 152 comment-only blocks (27,372 B) moved; in their place
one hand-written 5-line banner at the top of the file (~379 B):

```swift
// Vendored upstream MLXLMCommon generation API, unreachable from the scored
// Laguna worker (`GenerateParameters` survives only as an ignored protocol
// parameter) and partly forbidden by the serial non-speculative track. All of
// its upstream DocC prose is relocated verbatim, block by block, to
// notes/MLXLMCommon-Evaluate.notes.md so it does not spend submitted bytes.
```

**Trade-off, stated honestly:** relocating inherited vendored prose widens the
textual diff against upstream `mlx-swift-lm` and will produce merge noise if we
re-vendor. Evaluate.swift is now the largest instance of this in the tree. The
banner and the per-block provenance lines in `notes/` are the mitigation; a
re-vendor should take upstream's file wholesale and re-apply the banner.

### KVCache.swift (12,698 B) — and why it is now exhausted

77 blocks, 13,276 B of prose moved, 578 B of pointers added. The seven surviving
pointers (post-edit lines 274, 327, 586, 1772, 1845, 1881, 1920) were each read
in context to confirm they sit in `//` (non-doc) runs, so **no `///` doc comment
was detached from its declaration**. Campaign-authored fused-decode append and
ring-buffer invariants were deliberately kept.

A second pass found only **506 B** of DocC bodies left (4 blocks at 153-155,
178-180, 1716-1718, 1755-1757). **KVCache.swift is exhausted — do not revisit
it.**

### LagunaRuntimeWeights.swift (2,037 B) — the file where I overruled the tooling

Two smart-tier classification passes booked **9,240 B** here. After reading
every block ≥ 200 B myself I relocated only **5** hand-audited sub-ranges
(2,971 B gross, 377 B pointers, ~560 B of hand-written repairs) and **rejected
the rest**. Base-relative ranges moved: `420-431` (wired-residency measurement
history), `451-459` (wired-residency host headroom), `503-507` (greedy-argmax
PSO miss trace), `526-537` (wired-residency dose curve), `1001-1004` (group-16
scale-pair census).

Rejected bookings, with reasons — this list is the substance of the
"honest judgement" the assignment asked for:

| range | why kept |
|---|---|
| `352-357` | low-memory profile contract; states flag behaviour |
| `370-380` | the 512 MiB command-buffer sizing derivation. The one measurement line (378-379, "post-anupsv-loader regime re-test winner (6 Latin pairs: decode 5/6, prefill 4/6)") sits *mid-sentence* inside the ~507 MiB derivation. Splitting it breaks the sentence for ~200 B. |
| `382` | BFS width default provenance; trivial |
| `481-487` | the "regressed ranked prefill 11.3%" clause runs into "Reproducing that retired rewarm…" with no clean boundary. ~180 B not worth the sentence-repair risk. |
| `657-666` | encoding invariants: `max - min <= 31`, `code = base + nibble + (bit << 4)`, "no escape path and no data-dependent branch", "routed/shared reach span 39 and are out of this envelope" |
| `677-686` | the `0xFF` escape-sentinel invariant and the full-row span ≤ 15 bound |
| `690-698`, `700-711` | the o_proj byte math (193/257 vs 252/336) and the **exactness proof** for group-16 pairwise halving (`per_thread = max(group_size/simd_size,1)`, the `tidx.x < 16` first-simdgroup argument, "at most three fused-QKV rows and one o_proj row per layer differ", "the certificate still requires byte-for-byte reproduction, so a failing build loses speed not correctness") |
| `994-1013` | only the 4 census-number lines `1001-1004` moved; the `fp_quantize` per-simdgroup-absmax mechanism (972-1000) and the `allowedFlatPairs` / `lagunaScalePatchHeaderBytes` / returns-nil-unless-lossless contract (1006-1013) stay |

**This is the assignment's escape hatch being used deliberately.** The advisor
wrote: *"I would rather have 35 KB and honest judgement than 60 KB of gutted
invariants."* 7,200 B of the tooling's booking on this one file was refused on
exactly that basis, and the shortfall was made up from a file where the prose is
provably free (Evaluate.swift) rather than by weakening this one.

### LagunaConfig.swift (308 B)

One block: base lines `8-13`, the "Laguna is a 256-expert MoE decoder…"
architecture paragraph, which is duplicated verbatim in `program.md` and
`TASK.md`. A `///` pointer replaces it at line 8; lines 5-7 remain a valid
abstract. The remaining 4,383 B here is a frozen-invariant contract and was left
alone.

### Five hand-written repairs after the mechanical tool

Mechanical deletion can leave a dangling antecedent or an unterminated
sentence. `research/frieren_relocate_repairs.patch` (3,487 B) isolates the five
places I repaired by hand in `LagunaRuntimeWeights.swift`:

1. **420-425** — bare pointer replaced by a 6-line opener restoring the
   antecedent for "that hole": MLX's `MTLResidencySet` defaults to
   `capacity_ == 0`, so the driver re-establishes residency for the whole
   resident text tower on every command buffer; an oversized wired limit
   removes that work but then commits on every scored-window allocation and
   eviction.
2. **444-445** — sentence closed with a period, pointer relabelled
   "Host headroom: …". The `DARKBLOOM_WIRED_ZH=0` kill switch,
   `DARKBLOOM_WIRED_ZH_FRACTION` and `DARKBLOOM_WIRED_ZH_SLACK_MB` names all
   remain in code, and the ≥ 96 GiB guard remains documented at the
   `wireResidentWeightsIfEnabled` doc comment.
3. **489-491** — argmax-warmup sentence repaired: "INSIDE the measured window
   (trace: …). Replicating the same ops here moves that compile to untimed
   init."
4. **510-511** — DocC sentence completed: "discipline. Measured dose curve and
   ranked receipt: …". The SHIPPED DOSE derivation
   (1.0 × live bytes + 64 MiB ≈ 31.4 GiB) that explains
   `wiredZHDefaultFraction = 1.0` / `wiredZHDefaultSlackMB = 64` was kept, as
   were the engagement guards at 513-516.
5. **975** — "…carry the same byte. Census: …".

### Tooling gotcha worth remembering

`frieren_relocate_comments.py` originally always emitted a `// See notes/…`
pointer. **Dropping a `//` line into a `///` run detaches the kept abstract from
its declaration** — Swift stops treating the run as that declaration's doc
comment. Fixed at lines 95-100 by mirroring the block's own marker:

```python
marker = '///' if block[0].lstrip().startswith('///') else '//'
```

All 9 `///` pointers that existed in Evaluate.swift before that file switched to
full relocation, and every pointer in LagunaRuntimeWeights/LagunaConfig, were
then verified in context.

## Lever 2 — delete the `.gemma4`-only sidecar generators (34,233 B)

`Sources/MLXFastTransform/AffineMetadataCoding.swift` (16,378 B) and
`TiedHeadMetadataCoding.swift` (15,627 B) were reachable from exactly one place:
`case .gemma4:` in `Transform.swift`. The scored `case .laguna:` branch already
returned empty reports, because `docs/laguna-weight-contract.md` forbids derived
layouts and metadata sidecars in the Poolside v2 contract and Laguna's untied
`lm_head` makes the Gemma packed13 tied-head sidecar meaningless.

**This is not plain dead code**, which is why it needed care rather than a
delete: `Transform.swift` referenced it at `:242` and `:249`, and shared the
`GeneratedAffineMetadataReport` type at `:238-239`, `:262-269`, `:339-343`.

Collapsing the site once every report is provably empty removed a further
2,228 B (`Transform.swift` 28,787 → 26,559) by retiring:

- the `switch modelFamily` and both `let` report bindings;
- two `addingReportingOverflow` calls and their `guard` — vacuous, since adding
  0 cannot overflow;
- the `merging(...) { preconditionFailure("generated metadata tensor names collide") }`
  closure — unreachable when both maps are empty;
- the `+ .tensorCount` / `+ .shardCount` terms in `TransformReport`.

**The Laguna transform output is bit-identical:** `totalTensorByteCount + 0 + 0`
became `totalTensorByteCount`, `additionalWeightMap:` was already `[:]`, and
`denseTensorCount: copiedTensors + 0 + 0` became `copiedTensors`.

`TransformModelFamily.gemma4` and its `detectModelFamily` /
`isSelectedTextTowerKey` branches are **retained** — `TransformTests.swift`
asserts them at `:129` and `:143`, and the `gemmaReferenceConfigJSON()` fixture
(`:1068`) exists precisely to cover that family path.

Reachability checks run before deleting: no test, script, doc, or workflow
references `AffineMetadataCoding`, `TiedHeadMetadataCoding`,
`GeneratedAffineMetadataReport`, the sidecar shard names, the overflow error
string, or the collision precondition. `swift test` compiles the entire Tests
module, so a clean test build is itself a proof of no compile-time reference.
`DefaultTrackTests.swift:61,231` independently assert that gemma4 models are
*absent* from the shipped workflow and setup script.

## Gates

All commands run on the final tree (`d641df7`).

**Scope** — all seven touched submitted paths are inside `editablePaths`
(note `Sources/MLXFastTransform` is a *directory* entry, so every file under it
counts; an exact-string membership test on the 97 entries misleadingly says
"not editable"):

```
$ senpai/validate-assignment-scope.sh e1d070f2… \
    Vendor/…/KVCache.swift Vendor/…/Evaluate.swift \
    Sources/MLXFastModel/LagunaRuntimeWeights.swift Sources/MLXFastModel/LagunaConfig.swift \
    Sources/MLXFastTransform/Transform.swift \
    Sources/MLXFastTransform/AffineMetadataCoding.swift \
    Sources/MLXFastTransform/TiedHeadMetadataCoding.swift
assignment scope OK: 7 submitted path(s) against BASE_SHA=e1d070f256a1f5cef5a62a1d001dfbfe8b81bd0c
```

**Budget** — before, after Lever 1, after Lever 2:

```
editable budget OK: current=2950855/3000000 bytes headroom=49145  growth=0/262144       files=142 (base=142)
editable budget OK: current=2908819/3000000 bytes headroom=91181  growth=-42036/262144  files=142 (base=142)
editable budget OK: current=2874586/3000000 bytes headroom=125414 growth=-76269/262144  files=140 (base=142)
```

**Release build** — `swift build -c release --force-resolved-versions`:
`Build complete!` after both levers; `Package.resolved` restored each time.

**Comment-only equivalence** — `research/frieren_comment_strip_check.sh`:
`RESULT: PASS`, 42,036 B (full output above).

**Transform tests** — `swift test --force-resolved-versions --filter "transform|checkpointIndex"`:
`Test run with 36 tests in 1 suite passed`, including
`transformDetectsModelFamilyFromSourceConfig` (gemma4 detection),
`transformKeySelectionDropsRotaryInvFreqOnlyForLaguna` (gemma4 key selection),
`transformVerifierAcceptsFreshSubmittedTransformOutputAndIgnoresLocalCacheMarkers`,
`transformVerifierRejectsOutputThatDiffersFromFreshTransformRun` and
`transformVerifierRejectsStaleExtraGeneratedFile` (fresh-transform reproduction).

**Upstream equivalence oracle** — `research/run_upstream_equivalence.sh` with
`EQUIVALENCE_EXACT_STEPS=8`, 1 test selected (non-vacuous):

| | candidate (final tree) | base-state control |
|---|---|---|
| prefill `maximumAbsoluteLogitError` | 0.125 | 0.125 |
| prefill `meanAbsoluteLogitError` | 0.011933609 | 0.011933609 |
| decode steps 0-7 | all 0.0 / 0.0 | all 0.0 / 0.0 |
| tokens (`runtimeToken` vs `upstreamToken`) | all match: 5991/509/902 cycling | all match |
| `EQUIVALENCE_EXIT` | 1 | 1 |

**Bit-identical.** The exit 1 is the zero-tolerance prefill assertion at
`LagunaCorrectnessTests.swift:249` failing on this host, which is an M4 Pro
(Apple GPU generation 16, no `_nax` prefill kernels). I confirmed it is
pre-existing rather than caused by my change by restoring the base
`KVCache.swift` via `git show $BASE_SHA:$KV` (head copy parked at
`/tmp/frieren_kvcache_head.swift`) and re-running: identical 0.125 /
0.011933609, identical 8/8 exact decode steps, identical tokens, identical exit
code. `MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT=1` is the sanctioned handling for this
class of non-M5 divergence.

**Public 64-step drift tripwire — deliberately not run.** I could not locate a
standalone invocation; the only vehicle I found is
`./benchmark.sh --local-iterate` (`senpai/program.md:401`), which is a full
model-holding paired timing run behind the 40 C thermal gate. It would add no
information here: Lever 1's code residue is `cmp`-identical to base, Lever 2
does not touch `Sources/MLXFastModel` or `Vendor/` at all, and the equivalence
oracle already drove 512-token prefill plus 8 decode steps through the runtime
on the final tree with results bit-identical to the base control. The advisor
should still expect the official M5 stack to run the tripwire; nothing in this
change can move it.

## Reproduction

Deterministic, from `BASE_SHA`:

```bash
git checkout e1d070f2 -- \
  Vendor/mlx-swift-lm/Libraries/MLXLMCommon/KVCache.swift \
  Vendor/mlx-swift-lm/Libraries/MLXLMCommon/Evaluate.swift \
  Sources/MLXFastModel/LagunaRuntimeWeights.swift \
  Sources/MLXFastModel/LagunaConfig.swift

cd research && python3 frieren_build_relocate_spec.py && cd ..   # writes research/frieren_relocate_spec.json
python3 research/frieren_relocate_comments.py research/frieren_relocate_spec.json
patch -p0 Sources/MLXFastModel/LagunaRuntimeWeights.swift < research/frieren_relocate_repairs.patch
# then insert the 5-line Evaluate.swift banner at line 1 (quoted above)

research/frieren_comment_strip_check.sh                          # expect RESULT: PASS, recovered 42036
senpai/check-editable-budget.sh e1d070f2…                        # expect growth=-42036
```

Verified: `cmp` after applying the repairs patch matched the hand-edited file
exactly, so the recipe reproduces the committed tree rather than approximating
it.

### Tooling inventory (all in non-submitted `research/`, zero surface cost)

| script | purpose |
|---|---|
| `frieren_comment_strip_check.sh` | asserts the `"""` hazard precondition, normalises comments identically on BASE and HEAD, `cmp`s code residues, prints per-file/total bytes and `RESULT: PASS/FAIL` |
| `frieren_relocate_comments.py` | JSON-spec driven relocation: moves 1-based inclusive line ranges verbatim into `notes/<note>` under `## \`symbol\`` + provenance line, deletes bottom-up, optional **marker-matched** pointer at original indentation. `validate()` `sys.exit`s on out-of-range, overlapping, non-comment-only, or in-literal lines. |
| `frieren_comment_census.py` | per-file comment bytes split `outside` vs `inside` string literals |
| `frieren_comment_blocks.py` | maximal comment-only blocks: `start-end bytes UNSAFE\|ok next='<decl>'` plus bodies; `argv[2]` = min-bytes filter. Its own module docstring must not contain literal triple quotes. |
| `frieren_gen_docc_spec.py` | `<path> <minb> [body\|abstract\|all]`; run from inside `research/`. `all` relocates whole blocks, `body` starts at the first `- Parameters:`/`- Returns:`/`- Throws:`/`### ` line, `abstract` keeps only the leading paragraph. |
| `frieren_build_relocate_spec.py` | single-shot reproduction record; pins `BASE`, `POINTER_MIN_BYTES = 500`, forces `pointer=False` in `all` mode. Emits the exact spec used: Evaluate 152 blocks, LagunaRuntimeWeights 5 hand-listed, LagunaConfig 1. |
| `frieren_relocate_repairs.patch` | the five hand repairs, isolated as `diff -u` |

## Where the remaining bytes are

Whole editable surface at `7061c25`: **outside=535,162 B, inside=3,384 B**
across 142 files.

**Correction to the advisor's census.** My re-census of
`LagunaRuntimeModel.swift` gives **120,254 B outside / 372 B inside**
(468,336 B total, 212 `"""`, 0 `/*`); the assignment quoted 120,409 / 742. Cause:
my `is_comment` predicate skips lines containing an odd count of `"""`, so a
comment-looking line that *opens or closes* a multi-line literal is excluded
from both buckets. Mine is the conservative direction — it never counts code as
comment.

**Next round's pool, sized and de-risked (do not expand this PR's scope).**
`Vendor/mlx-swift-lm` totals outside 99,320 / inside 1,115 over 15 files.
Excluding my two in-scope files leaves **60,413 B** that needs **no metallib
rebuild** (this tree is outside the fingerprinted `Vendor/mlx-swift/Source/Cmlx/`
region) and has **no `LagunaRuntimeModel.swift` fence conflict**:

```
BatchKVCache              13,565
CompiledDecode             6,871
CompilableRotatingKVCache  6,670
SwitchLayers               6,318   (+1,115 inside, 10 """ — hazard, check first)
CompilableKVCache          5,372
LanguageModel              5,110
BaseConfiguration          3,749
AttentionUtils             3,678
Laguna.swift               2,581
RoPEApplication            1,983
RoPEUtils                  1,849
DynamicSlice               1,663
JSONDecodingTypes          1,004
```

The Evaluate.swift precedent — *provenance* + *reachability* +
*upstream-recoverability* ⇒ full relocation with one banner — should be applied
file by file there, and `Laguna.swift` in particular is the upstream-equivalence
oracle whose prose is pure inherited documentation. Combined with this PR that
would put total headroom near 190 KB.

## Honest assessment

- Lever 1 landed at 42,036 B, **below** the 55,000–65,000 B target and above the
  40,000 B floor. The gap is entirely the 7,200 B I refused to take from
  `LagunaRuntimeWeights.swift` invariant prose. I stand by that: those blocks
  document the group-16 halving exactness proof, the `0xFF` escape sentinel, and
  the span bounds that a future editor must not violate.
- The change is provably behaviour-preserving on the scored path — `cmp`-identical
  code residue for Lever 1, and a bit-identical equivalence oracle including a
  base-state control.
- The real cost is upstream diff noise in `Vendor/mlx-swift-lm/`, concentrated in
  Evaluate.swift. Flagged above with a mitigation.
- Lever 2 is the only part with any behavioural surface at all, and it is
  confined to the unscored offline `.gemma4` transform family. It is isolated in
  its own commit for exactly that reason.

### Suggested follow-ups (not implemented here)

1. The 60,413 B `Vendor/mlx-swift-lm` pool above, as one or two follow-up
   assignments. Check `SwitchLayers`' 10 `"""` before touching it.
2. `LagunaRuntimeModel.swift` holds 120,254 B of comment prose — by far the
   largest single pool — but is fenced by three concurrent experiments. Worth
   scheduling as a dedicated quiet-window assignment once #268/#284/F1 land.
3. Promote `frieren_comment_strip_check.sh` into the standard preflight for any
   future comment-relocation assignment; it is the gate that makes this class of
   change reviewable in seconds instead of by reading a 42 KB diff.
