# Transform verifier to scored-runtime coverage audit

## Terminal verdict

`COVERAGE_DEFECT`

At required source revision `dd35f692f26a17c93f69065ea8208e349f23743a`,
the verifier omits a filesystem entry class that changes scored runtime
behavior. This falsifies the closure hypothesis before any source-marker edge
could make the verified output surface complete.

## First unclosed edge

A static synthetic tree is sufficient to reproduce the defect:

1. Keep the regenerated expected tree and supplied actual tree identical for
   every regular file and every byte.
2. Add an empty directory named `extra.safetensors` beneath the actual root.
3. `TransformVerification` skips directories during recursive enumeration, so
   the directory contributes no relative path to file-set equality, no size or
   byte comparison, and no entry to the reported tree digest
   (`Sources/MLXFastTrustedHarness/TransformVerification.swift:187-237`, with
   the directory branch at `217-218`).
4. The scored loader calls `contentsOfDirectory` on the weights root and treats
   every returned URL whose `pathExtension == "safetensors"` as a discovered
   shard without first requiring a regular file
   (`Sources/MLXFastModel/RuntimeWeightLoading.swift:29-39`). It then compares
   the indexed and discovered shard-name sets and throws for the unindexed
   `extra.safetensors` entry (`RuntimeWeightLoading.swift:89-110`). This loader
   feeds scored model materialization
   (`Sources/MLXFastModel/LagunaRuntimeWeights.swift:626-638`).

Thus `verify-transform` can report equality while the same actual root fails
the scored runtime. The benchmark-owned source marker binds reviewed transform
source identity; it does not add verifier-visible entries and cannot close this
runtime-significant directory omission.

No actual tree was created and no transform or model was run. The reproducer is
source-level reasoning over the specified branches, as required by the static
assignment.

## Inventories reached before the stop

### Laguna producer regular-file classes

| Class | Path construction and owner | Conditions and static bound | Verifier disposition |
|---|---|---|---|
| Configuration | `outputRoot/config.json`, written by the Laguna transform (`Sources/MLXFastTransform/Transform.swift:68-83,288-298`) | Exactly one | Exact path, size, bytes, and digest |
| Weight index | `outputRoot/model.safetensors.index.json` (`Sources/MLXFastTransform/CheckpointIndex.swift:28-57`; `Transform.swift:210-235,288-298`) | Exactly one | Exact path, size, bytes, and digest |
| Safetensors shards | `outputRoot/<validated local shardName>.safetensors` (`Transform.swift:210-235,349-375`) | Finite names selected by the produced index; separators and dot escapes rejected | Whole regular file compared, covering header and payload; newline-bearing paths abort verification |
| Tokenizer model | `outputRoot/tokenizer.json`, copied by the metadata pass (`Transform.swift:506-551`) | One top-level source file when supplied; required by semantic-GPQA preflight | Exact path, size, bytes, and digest |
| Tokenizer configuration | `outputRoot/tokenizer_config.json`, copied by the metadata pass (`Transform.swift:506-551`) | One top-level source file when supplied; required by semantic-GPQA preflight | Exact path, size, bytes, and digest |
| JSON chat template | `outputRoot/chat_template.json`, copied by the metadata pass when present (`Transform.swift:506-551`) | Conditional fixed child | Exact path, size, bytes, and digest when emitted |
| Jinja chat template | `outputRoot/chat_template.jinja` | Not emitted: `.jinja` is outside `shouldCopyMetadataFile`'s extension/name set (`Transform.swift:540-551`) | Proven absent from transform output, although the tokenizer helper probes the path |
| Other top-level metadata | Other eligible `.json`, `.model`, `.tiktoken`, `.txt`, tokenizer, or vocab basenames, excluding named config/index/tokenizer files and safetensors (`Transform.swift:506-551`) | Finite top-level source enumeration | Every emitted regular file is compared and digested; newline-bearing paths abort verification |
| Laguna sidecars | Affine-attention and tied-weight sidecars (`Transform.swift:256-269`) | Laguna emits neither class | Absent |

The producer's regular-file classes are statically bounded. The local shard
validator and metadata copier do not prohibit a newline in a basename, while
the verifier rejects any enumerated relative path containing a newline
(`Sources/MLXFastCore/PathValidation.swift:3-17`;
`TransformVerification.swift:225-228`). This is fail-closed for a valid report:
the entry cannot be silently omitted. The terminal defect instead permits a
successful equality report because the directory is skipped before any name
check, while the runtime consumes its basename.

### Scored and official semantic-correctness reads beneath the weights root

The official workflow passes the transformed weights root to the CLI, which
passes the same path as `semanticGPQATokenizerPath`
(`.github/workflows/benchmark.yml:1503-1515`;
`Sources/MLXFastCLI/main.swift:362-370`). Semantic correctness then loads the
local tokenizer through `swift-transformers` version `1.3.3` at revision
`2fa33e1f5e7131a7fc64c28e6d161dcec0d24820`
(`Package.resolved:266-271`). The manifest embeds the exact newline-terminated
`Sources/Hub/Hub.swift:247-298` excerpt from that revision, cites its
content-addressed URL, and binds it with SHA-256
`1cec8edb95382bee855ef929f63370e578548bd36ee61751782bcaa969f1cd65`.
This makes the five tokenizer path probes independently checkable from tracked
content without a dependency checkout or network access.

| Phase | Path expression | Consumer and fallback | Escape/bound |
|---|---|---|---|
| Config parse | `weightsRoot/config.json` | `LagunaConfig.swift:321-329`; required direct read | Fixed child path |
| Index parse | `weightsRoot/model.safetensors.index.json` | `DenseTensorStore.swift:166-227`; required direct read | Fixed child path |
| Root shard inventory | `contentsOfDirectory(weightsRoot).filter(pathExtension == "safetensors")` | `RuntimeWeightLoading.swift:29-39,89-110`; any suffix-matching root entry changes validation | Root-bounded but not regular-file bounded; **defect** |
| Shard headers | `weightsRoot/<validated index shardName>` | `DenseTensorStore.swift:166-227` and `RuntimeWeightLoading.swift:45-63`; required | Local basename validator in `Sources/MLXFastCore/PathValidation.swift:3-17` prevents path escape |
| Tensor payloads | Same index-derived shard, indexed byte ranges | `DenseTensorStore.swift:39-118`, reached by `LagunaRuntimeWeights.swift:626-638` | Same bounded local shard set |
| Semantic tokenizer root | `semanticTokenizerPath == weightsRoot` | Workflow/CLI binding above; harness checks required children at `LagunaRuntimeBenchmark.swift:314-332`, then correctness calls `loadLocalTokenizer` at `LagunaRuntimeCorrectness.swift:467-470` and `LagunaRuntimeSupport.swift:96-100` | Fixed root binding |
| Tokenizer model | `weightsRoot/tokenizer.json` | Required preflight file and required parse by pinned dependency evidence `swift-transformers:Sources/Hub/Hub.swift:247-298` | Fixed child path |
| Tokenizer configuration | `weightsRoot/tokenizer_config.json` | Required preflight file; pinned dependency evidence conditionally decodes it when present | Fixed child path |
| Tokenizer model configuration | `weightsRoot/config.json` | Pinned dependency evidence conditionally decodes model configuration when present | Fixed child path, joined to transform configuration |
| Preferred chat template | `weightsRoot/chat_template.jinja` | Pinned dependency evidence probes this fixed child first; transform output proves it absent | Fixed conditional probe |
| Fallback chat template | `weightsRoot/chat_template.json` | Pinned dependency evidence probes this fixed child only after the Jinja miss | Fixed conditional probe |

### Coverage join through the failure

- `config.json`, the index, every regular shard, and emitted tokenizer metadata
  are included in exact expected/actual relative-path equality, size equality,
  streamed byte equality, and the path-plus-file-digest tree hash
  (`TransformVerification.swift:119-170,244-273`).
- Whole-shard equality covers both safetensors headers and all payload ranges.
- `tokenizer.json`, `tokenizer_config.json`, generated `config.json`, and the
  conditional chat-template paths are explicitly joined from transform
  production or proven absence to the official semantic-GPQA tokenizer helper.
  Other copied metadata remains verifier-visible but runtime-inert for the
  enumerated model and semantic-tokenizer paths.
- The root-entry shard inventory is not a regular-file read. Its outcome still
  affects whether the runtime proceeds, and `extra.safetensors/` is omitted by
  the verifier. This is the first unclosed join.

## Ignored paths and source binding

The verifier ignores exactly `.gitkeep` and `.benchmark-source.sha256`
(`TransformVerification.swift:205-206,235-237`). Both are runtime-inert by
code path rather than filename convention: model loading reads exact config and
index paths, index-derived shard paths, and root entries ending `.safetensors`;
semantic tokenizer loading reads or probes exact `config.json`,
`tokenizer.json`, `tokenizer_config.json`, `chat_template.jinja`, and
`chat_template.json` children. Neither ignored basename matches these classes.

The separate marker chain reached before the stop is:

1. `source_hash` hashes relative path plus content SHA-256 for `Package.swift`,
   `Package.resolved`, `Sources/MLXFastCore`, and
   `Sources/MLXFastTransform` (`benchmark.sh:1579-1608`). It does not claim to
   identify `Sources/MLXFastCLI` or the trusted verifier harness; the marker's
   source identity is exactly this four-input scope.
2. Staging rejects transform-authored `.benchmark-source.sha256` and `.gitkeep`
   entries, validates staged output types, and only then injects the
   benchmark-owned files (`benchmark.sh:1820-1861`).
3. Reuse requires a regular, non-symlink, digest-formatted marker and compares
   its value with the current wanted source hash
   (`benchmark.sh:1389-1397,2116-2148`).
4. Integrity evidence records `transform_source_sha256: wanted_hash`
   (`benchmark.sh:2271-2290`).

This chain prevents a transform-authored marker from claiming trust and makes
ordinary reuse conditional on the limited source identity above. A valid
`verify-transform` report separately binds actual regular-file bytes to a fresh
regeneration by the current verifier library; the marker is not a hash of the
CLI, harness, or output tree. Neither mechanism binds a runtime-significant
entry absent from verifier enumeration, so the terminal state remains
`COVERAGE_DEFECT`.

## Path-safety classification

| Case | Static verifier/runtime result |
|---|---|
| Symlink | Descendant symlinks are rejected unless their exact ignored basename is skipped first; benchmark separately owns and validates marker creation. The runtime follows index/shard final-component symlinks, but such a tree cannot produce a valid report without a later replacement, which is excluded TOCTOU authority. Index shard names cannot contain `/` or `\\`. |
| Hardlink | Seen as a regular file and compared independently at each relative path. Inode identity and aliasing are not in the digest; alias lifetime and post-enumeration mutation are excluded TOCTOU authority. |
| Non-regular entry | Symlinks and non-directory/non-regular entries fail. Directories are skipped, causing the first defect for a root basename ending `.safetensors`. |
| Duplicate/reassigned shard | Local shard names are validated and indexed/discovered sets must agree, so missing, extra, or reassigned regular shard names fail. A suffix-matching directory improperly joins the discovered set. |
| Normalization/root escape | Foundation standardizes roots and relative URLs, but does not establish Unicode/case/inode identity. Index shard names reject separators, `.`, and `..`, closing lexical escape; verifier rejection closes pre-report symlink escape. |
| Missing/extra regular file | Exact file-set equality fails before byte comparison. |
| Created after enumeration | A late entry or replacement is absent from the verifier snapshot. That is excluded load-epoch/TOCTOU authority and cannot establish a closure PASS; it does not cure the static directory omission. |

## Historical novelty

A bounded search of the authorized revision and `research/` found no prior
complete verifier-to-runtime coverage proof. Existing transform mutation tests
cover ignored marker files, changed metadata, extra regular files, and byte
limits (`Tests/MLXFastTests/TransformTests.swift:793-888`), but not a
runtime-significant directory. PR #671's merged provenance report records
regular-file digest semantics and explicitly states that exact worker-open
inventory parity was not evaluated after its earlier authority stop
(`research/ranked-weight-load-provenance-audit.md:67-84,112-115`).

## Machine controls

`research/check_transform_verifier_runtime_coverage.py` validates row
uniqueness, required producer/verifier/runtime/ignored/marker classes, the main
and pinned dependency revisions, producer-to-runtime joins, marker ownership,
source-hash binding, per-runtime-row path bounds, normalization, and the known
first defect. Tracked citations must resolve to existing repository files with
valid line ranges. The dependency citation resolves to the manifest's exact
52-line, final-newline excerpt; its SHA-256 and five source anchors are checked,
and its repository, revision, and version are structurally bound to tracked
`Package.resolved` metadata.

The checker mutates only copied manifest objects for seventeen controls:

1. omit config;
2. omit index metadata;
3. reassign one shard join;
4. ignore a runtime-consumed path;
5. trust a transform-authored marker;
6. remove source-hash binding;
7. insert an actual `runtime_read` row whose path bound is
   `unbounded_dynamic`;
8. add an extra verifier-visible regular file;
9. allow normalization/root escape;
10. omit the `tokenizer.json` producer row;
11. omit the `tokenizer_config.json` runtime row;
12. reassign the tokenizer producer/runtime join;
13. replace a real citation with a nonexistent source path;
14. replace a real citation with an out-of-bounds line range;
15. drift the pinned dependency revision;
16. mutate the embedded dependency excerpt; and
17. remove a required dependency source anchor.

Every control produces machine-readable errors while the unmodified manifest
has an empty `manifest_errors` array. The checker prints one canonical JSON line
containing the canonical manifest SHA-256, terminal verdict, baseline errors,
known defect, and all control errors. Repeated executions are byte-identical.
The SHA-256 of that exact newline-terminated checker output is:

`b4b9aa16af187824d053d6a7af8cb45696aff0a76aa7568ecb55c7502b3b7a18`

## Scope statement

Only the assigned Markdown, manifest, and static checker are changed. No Swift
test, build, transform, model load, inference, timing, W&B operation, receipt,
MLXFast challenge API operation, installed artifact, cache, or official
submission was used. No production or workflow fix is proposed or implemented.
