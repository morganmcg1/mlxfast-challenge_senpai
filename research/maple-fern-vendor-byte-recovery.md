# Vendor comment-relocation byte recovery + a machine-checked relocation manifest

Student: `maple-fern` · PR #311 · assignment `maple-2026-08-07r-vendor-byte-recovery` r1
Branch `maple-fern/vendor-byte-recovery` · `BASE_SHA=63ab67c888e1892086b7b5b623de4dd0ebe68c90`

W&B: [`j8wsbcu1`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/j8wsbcu1)

**This is not a timing experiment.** Byte recovery is the result. Comment text
never reaches compiler output, so the expected timing effect is exactly zero
and no timing was measured. The evidence below is byte accounting plus
correctness gates.

---

## Headline

| | |
|---|---|
| Part A — bytes recovered from the submitted surface | **18,274 B** |
| Part A — submitted files touched | 5 (all unreachable from the scored path) |
| Editable-surface growth | **-18,274 / 262,144 B** (negative, as required) |
| Editable headroom | 131,949 → **150,223 B** |
| Part B — projected net recovery (planned, not applied) | **27,663 B** |
| Part B — `LagunaRuntimeModel.swift` projected size | 468,336 → **440,673 B** (84.0 % of the 524,288 B cap) |
| `Sources/MLXFastModel/LagunaRuntimeModel.swift` bytes changed | **0** |

Every gate that can pass on this host passes. The one non-passing gate
(`run_upstream_equivalence.sh`) produces a **byte-identical report on the
unchanged base**, which is documented below as a pre-existing host property.

---

## Part A — applied relocation

Comment prose was moved verbatim out of five submitted vendor files into
non-submitted `notes/*.md`. Each source site keeps a one-line pointer.

| File (`Vendor/mlx-swift-lm/Libraries/MLXLMCommon/`) | base B | head B | delta | residue B | residue |
|---|---:|---:|---:|---:|---|
| `BatchKVCache.swift` | 43,383 | 37,146 | **-6,237** | 29,813 | IDENTICAL |
| `CompiledDecode.swift` | 16,147 | 11,686 | **-4,461** | 9,276 | IDENTICAL |
| `CompilableRotatingKVCache.swift` | 11,445 | 8,418 | **-3,027** | 4,770 | IDENTICAL |
| `CompilableKVCache.swift` | 12,043 | 9,170 | **-2,873** | 6,667 | IDENTICAL |
| `BaseConfiguration.swift` | 8,535 | 6,859 | **-1,676** | 4,786 | IDENTICAL |
| **total** | **304,766** | **286,492** | **-18,274** | | |

No sixth submitted file was added. `SwitchLayers.swift` was excluded as
instructed. Five notes files were created:
`notes/MLXLMCommon-{BatchKVCache,CompiledDecode,CompilableRotatingKVCache,CompilableKVCache,BaseConfiguration}.notes.md`.

### Proof that the change is comment-only

`research/frieren_comment_strip_check.sh <BASE_SHA>` — its `FILES` array was
extended from 4 to 9 entries and the new BASE_SHA passed. **The phase-1
assertion was not relaxed.**

```
RESULT: PASS (comment-only change on all 9 files)
```

* Phase 1 — all 9 rows report `comment_lines_inside_literal=0` on both base and
  head, so no `//` inside a string literal can be misread as a comment.
* Phase 2 — all 9 rows report `IDENTICAL` code residue after normalising
  comments away. The five untouched control files show `saved=0`; the five
  edited files account for the full 18,274 B.

### Why none of the five could simply be deleted

All five are referenced by **non-editable** siblings, so this had to be a
relocation PR rather than a deletion PR: `MLXVLM/Models/Gemma4.swift`,
`MLXLLM/Models/Gemma4Text.swift`, `ContinuousBatching*/`,
`QuantizedBatchKVCache.swift`, `CompilableBatchKVCache.swift`,
`GenerationBatch.swift`, `PromptProcessingBatch.swift`, `Scheduler.swift`,
`Load.swift`, `LLMModelFactory.swift`.

### Reachability substitute for the unusable commit-count provenance

The brief's commit-count provenance signal is **unusable in this checkout**:
`.git/shallow` grafts history at `dec0a83c`, so per-file commit counts are
truncated artefacts of the clone depth, not of the campaign. As instructed I
substituted two signals.

1. **Reachability.** All 9 file-scope entry points across the five files have
   **zero** references in `Sources/MLXFastModel/LagunaRuntimeModel.swift`.
   Member-name hits (24 / 7 / 9 / 12 / 6) are generic identifier collisions
   (`mask`, `keys`, `values`, `state`, `copy`, `bits`, `groupSize`) and not
   references to these types.
2. **Campaign-marker grep** (`DARKBLOOM|MLXFast|ranked|deviat|upstream|Laguna`)
   to distinguish campaign-authored prose from upstream prose, so that
   campaign contracts are retained in source.

#### Correction to the brief: the `CompiledDecode` "3 hits" are a substring

A plain `grep CompiledDecode Sources/MLXFastModel/LagunaRuntimeModel.swift`
returns 3 hits, at `:5366`, `:5388` and `:6272`. **None of them reference the
`CompiledDecode` enum.** All three are the substring inside
`MLXHardwareInfo.isCompiledDecodeSupported`, which is declared in
`MLXLMCommon/MLXHardwareInfo.swift` — a different file. `CompiledDecode.swift`
is therefore unreachable from the scored path exactly like the other four.

### What was deliberately kept in source

**All six live `DARKBLOOM_*` flag contracts were kept verbatim**, and there is
**zero DARKBLOOM leakage into the notes files** (`grep -rc DARKBLOOM notes/` → 0):

| Site | Contract |
|---|---|
| `BatchKVCache.swift:477` | doc for `DARKBLOOM_FAST_BATCH_ROTATING_KV` (ON by default) |
| `BatchKVCache.swift:481` | the `ProcessInfo` read of `DARKBLOOM_FAST_BATCH_ROTATING_KV` |
| `CompiledDecode.swift:10` | the `ProcessInfo` read of `DARKBLOOM_COMPILED_TIERED_ATTENTION` |
| `CompiledDecode.swift:55` | doc for `DARKBLOOM_COMPILED_DECODE=0` |
| `CompiledDecode.swift:59` | the `ProcessInfo` read of `DARKBLOOM_COMPILED_DECODE` |
| `CompiledDecode.swift:108` | doc for the `DARKBLOOM_COMPILED_DECODE=1` precondition |

Also retained in source: the copyright header; the port provenance
("Ported from osaurus-ai/vmlx-swift-lm"); the pin that this is the "only
full-attention cache whose `update()` is graph-traceable"; and the
`NOTE (Darkbloom): this type is presently UNWIRED` contract.

`research/fern_vendor_docc_detach_check.py` reports **0** mixed-style runs
preceding a declaration, i.e. no relocation detached a DocC abstract from the
declaration it documents.

### Honest accounting of the recovery gap (18,274 B vs the ≈27,965 B target)

The shortfall is not slack — it is the cost of the keep policy the brief
mandates. Bucket attribution of the full 36,164 B comment pool across the five
files (`research/fern_vendor_plan_audit.py`):

| Bucket | Bytes | Share |
|---|---:|---:|
| RELOCATED | 19,154 | 53.0 % |
| `abstract_of_split_block` (kept) | 6,151 | 17.0 % |
| `abstract_is_whole_block` (kept) | 4,313 | 11.9 % |
| `single_line_abstract` (kept) | 3,835 | 10.6 % |
| `hand_audited_keep` | 1,466 | 4.1 % |
| `hard_keep` (17 blocks) | 1,000 | 2.8 % |
| `remainder_below_floor` | 245 | 0.7 % |
| **total pool** | **36,164** | |

The abstract-keep layer alone is ≈14.3 KB (39.5 %). Recovering it would mean
stripping the one-line DocC abstract off each declaration, which is exactly
what the DocC-detach check forbids.

Two reconciliations, stated so the numbers are auditable rather than tidy:

* The planner projects **19,154 B moved**; the measured net is **18,274 B**,
  because 922 B of pointer lines are added back (253 + 173 + 281 + 136 + 79).
* The audit pool total (36,164) differs from the census (36,227) by **63 B**
  because the Part A planner counts characters while the census counts UTF-8
  bytes. This is cosmetic: the authoritative figure is the measured `wc -c`
  delta, which the checker reproduces independently.

---

## Part B — relocation manifest for `LagunaRuntimeModel.swift`

Deliverable: `research/maple-fern-lagunaruntimemodel-relocation-manifest.md`,
plus the machine-applicable spec files listed at the end.

**The scored file was not modified by a single byte.** SHA-256
`56d16941d61c5f1217faad6ef86dcc766b1632ac7078015702bc7f42a9434fcf`, 468,336 B,
verified before and after every command including the dry run.

### Census (matches the brief exactly)

468,336 B · 96,027 B of `///` · 24,227 B of `//` · **120,254 B pool (25.7 %)** ·
372 B in-literal · 185 campaign lines · 254 comment blocks.

### Finding: the checker is *insufficient* for this file, and why that is safe

The 372 in-literal bytes are **lines 4587–4591**: Metal kernel `//` comments
inside a `"""` literal. The checker's own awk confirms
`delims=212 bad=5 badbytes=372`.

Two consequences worth recording:

1. `frieren_comment_strip_check.sh` **phase 1 would legitimately FAIL** on this
   file. Its `normalise()` strips `//` lines regardless of literal state, so
   phase 2's residue comparison would be meaningless there. This is a real
   limitation of the instrument, not a reason to weaken it — **the phase-1
   assertion was left untouched** and a strictly stronger *literal-aware*
   replacement was written for Part B only.
2. The risk is nonetheless structurally excluded: `frieren_comment_blocks.blocks()`
   never opens a block inside a `"""` literal, so those five lines can never be
   selected by any plan. The dry run asserts this directly ("no planned block
   covers a literal-interior line").

### Plan

| | |
|---|---:|
| comment blocks | 254 |
| literal-interior (never selectable) | 5 lines / 372 B |
| hard-keep | 58,837 B |
| **planned blocks** | **94** (86 immediate + 8 fenced) |
| moved bytes | 28,643 |
| pointer bytes added | 980 |
| **net recovery** | **27,663 B** |
| projected size | **440,673 B** = 84.0 % of the 524,288 B cap |
| headroom | 55,952 → **83,615 B** (+49.4 %) |

### Fence subtotals against the in-flight PRs

Eight blocks fall inside line ranges claimed by an open PR and are deferred to
wave 2 so they cannot cause a conflict.

| PR | claimed ranges | blocks | bytes |
|---|---|---:|---:|
| #301 | `:6577-6716`, `:6801-6900`, `:7545-7690` | 2 | 233 |
| #308 | `:4035-4457`, `:6801-6900`, `:7545-7690`, `:7851-8027` | 1 | 277 |
| #309 | `:4610-4881`, `:763-792`, `:801`, `:837-1099` | 5 | 937 |
| **wave 2 total (deduplicated)** | | **8** | **1,447** |

The eight fenced blocks: 989–990 (133 B, #309, `lagunaResidualRMSNormRouterKernels`);
1076–1079 (270 B, #309, `rowsPerGroup`); 4119–4122 (277 B, #308, `nibDiv`);
4618–4619 (157 B, #309, `lagunaDecodeNVFP4QKVR1Enabled`); 4627 (65 B, #309,
`scaleSetup`); 4731–4734 (312 B, #309, `lagunaDecodeNVFP4QKVLaneMajorSource`);
6643 (61 B, #301, `lowScaleFastPath`); 6655–6657 (172 B, #301, `packedWordBody`).

**Wave 1 is where the value is.** The 86 unfenced blocks move 27,196 B for a
net **26,216 B — 94.8 % of the total recovery** — and can land while #301, #308
and #309 are all still open. Wave 1 alone takes the file to 442,120 B and
headroom to 82,168 B.

### Dry run

`research/fern_partB_dry_run.sh` → **`RESULT: PASS`**, operating on a scratch
copy of the repository:

* the real checkout is hash-guarded byte-identical before and after;
* phase 1 (literal-aware): 5 literal-interior lines found, TEXT byte-identical,
  line-number shift uniform at `-190` (a single shift value proves nothing was
  inserted inside the literal), no planned block covers one;
* phase 2 (literal-aware): `base=468336 head=440673 saved=27663 residue=348063 IDENTICAL`;
* the notes file would be 33,698 B (scratch only).

Wave-1-only dry run also **PASS**: 86 blocks, moved 27,196 B, +980 B pointers,
net 26,216 B, uniform shift `-180`,
`base=468336 head=442120 saved=26216 residue=348063 IDENTICAL`.

Both runs land on the same residue (348,063 B), which is the strongest
available statement that the two waves are independent and order-free.

---

## Gate results

| Gate | Verdict |
|---|---|
| `frieren_comment_strip_check.sh <BASE_SHA>` | **PASS** — 9/9 phase-1 clean, 9/9 residue IDENTICAL |
| `senpai/validate-assignment-scope.sh` | **PASS** — `5 submitted path(s)` |
| `senpai/check-editable-budget.sh` | **PASS** — `current=2849777/3000000 headroom=150223 growth=-18274/262144 files=140 (base=140)` |
| `fern_vendor_docc_detach_check.py` | **PASS** — 0 mixed-style runs |
| `fern_partB_dry_run.sh` | **PASS** — scored file untouched, residue IDENTICAL |
| scored worker build | **PASS** — `Build of product 'mlxfast-runtime-worker' complete!`, exit 0 |
| 64-step drift tripwire | **PASS** — `checked_steps: 64`, `passed: true` |
| `research/run_upstream_equivalence.sh` | exit 1 — **identical on the unchanged base**, see below |

The worker build emits only the pre-existing `EngineLoopV2.swift:1278/1279`
`@Sendable` warnings, unchanged from base.

`swift test --force-resolved-versions` was not run because no
`Sources/MLXFastTransform/` file is touched.

### The equivalence oracle: a pre-existing host property, not a regression

The oracle exits 1 on this host with prefill `maximumAbsoluteLogitError = 0.125`
against a zero tolerance. **All 8 decode steps are exact (0.0) and every single
token matches** (`runtimeToken == upstreamToken` at all 9 steps;
`EQUIVALENCE_EXACT_STEPS=8`). The test count is non-zero
(`Test run with 1 test in 0 suites`), so this is a real comparison and not the
zero-selected-tests trap the wrapper guards against.

Following the wrapper's own instruction to compare the unchanged base on a
non-M5 host, I restored exactly the five changed files to `BASE_SHA`
(`git checkout <BASE_SHA> -- <5 paths>`), re-ran the oracle, then restored HEAD:

| | candidate | unchanged base |
|---|---|---|
| prefill `maximumAbsoluteLogitError` | 0.125 | **0.125** |
| prefill `meanAbsoluteLogitError` | 0.011933609 | **0.011933609** |
| exact decode steps | 8 / 8 | **8 / 8** |
| token mismatches | 0 | **0** |
| exit | 1 | **1** |

The two reports are identical to every printed digit. This host is an **M4 Pro,
Apple GPU generation 16**, which does not select the `_nax` prefill kernels the
ranked M5 uses; the divergence is a property of the host, present at base, and
not attributable to this change. Independently, a comment-only edit whose
normalised code residue is proven IDENTICAL cannot change numerics at all.

---

## Reproduction

```bash
BASE=63ab67c888e1892086b7b5b623de4dd0ebe68c90

# Part A proof
./research/frieren_comment_strip_check.sh "$BASE"
python3 research/fern_vendor_docc_detach_check.py
senpai/check-editable-budget.sh "$BASE"

# Part B plan + dry run (never writes the scored file)
python3 research/fern_partB_relocation_plan.py
./research/fern_partB_dry_run.sh

# correctness
swift build -c release --force-resolved-versions --scratch-path .build-worker \
  --product mlxfast-runtime-worker && git checkout -- Package.resolved
.build-worker/release/mlxfast-swift correctness --weights weights \
  --golden correctness_prompts/public_longcopy_gate_english_512_256.json
./research/run_upstream_equivalence.sh
```

## Artefacts

Instruments (research-only, not submitted):

* `research/fern_vendor_byte_census.py` — modes `census` and `reach`
* `research/fern_vendor_relocate_plan.py` — Part A planner
* `research/fern_vendor_plan_audit.py` — bucket attribution
* `research/fern_vendor_docc_detach_check.py` — DocC abstract-detach check
* `research/fern_partB_relocation_plan.py` — Part B planner (UTF-8 byte accounting)
* `research/fern_partB_dry_run.sh` — scratch-tree dry run with literal-aware proof
* `research/fern_partB_lagunaruntimemodel_spec.json` — full 94-block spec
* `research/fern_partB_lagunaruntimemodel_spec_wave1.json` — 86-block wave-1 spec
* `research/fern_partB_lagunaruntimemodel_blocks.tsv` — all 254 blocks with disposition
* `research/maple-fern-lagunaruntimemodel-relocation-manifest.md` — the manifest
* `research/fern_wandb_log.py` — W&B record

Modified instrument: `research/frieren_comment_strip_check.sh` — `FILES` array
extended from 4 to 9 paths. Its phase-1 assertion is unchanged.

## Suggested follow-ups (not implemented)

1. **Apply Part B wave 1** as its own PR: 26,216 B for 86 mechanical blocks,
   dry-run-proven, and conflict-free against #301/#308/#309. This is the single
   largest byte recovery available on the whole surface.
2. **Teach `frieren_comment_strip_check.sh` the literal-aware `normalise()`**
   from `fern_partB_dry_run.sh`. Today the shared checker cannot be pointed at
   `LagunaRuntimeModel.swift` at all; with the literal-aware pass it could gate
   every editable file uniformly.
3. **Unify byte accounting** in `fern_vendor_relocate_plan.py` on UTF-8 (the
   Part B planner already is). This removes the cosmetic 63 B discrepancy.
4. **Revisit the abstract-keep policy** with an explicit rule for
   `abstract_of_split_block` (6,151 B in Part A alone). A shorter retained
   abstract may satisfy DocC while recovering several KB more.
