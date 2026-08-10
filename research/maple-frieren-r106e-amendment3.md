# Amendment 3 — R106-E draw 1 was not on `4b0e051b`'s surface (Rule 95 §7 close-out)

*Companion to `research/maple-frieren-r106e-replication.md`. Written after
merging advisor base `89c2d154` (Rule 95). This amendment settles the
tree-identity question the advisor raised in §93.4(f) and records the
corrected replay that Rule 95.6 mandates.*

## 25. The adjudication the advisor asked for

Rule 93.4(f) predicted a live failure mode: a "replay" performed with
`git checkout <tree> -- $PATHS` **silently keeps files that exist in HEAD but
not in `<tree>`**, because `git checkout` from a tree only writes the paths it
finds there — it never deletes. The claim under test was that R106-E draw 1,
which I had labelled a `4b0e051b` replay, was in fact submitted from a
different surface, and that its −3.09σ decode reading was therefore a tree
swap and not within-tree dispersion.

The test is a single command. Let `PATHS` be the 97 `editablePaths` globs:

```bash
PATHS=$(jq -r '.editablePaths[]' benchmark.json)
git diff --numstat 4b0e051bf3cd9777bd6d2be64e172c490705f9a5 8db6ffaf -- $PATHS
```

`8db6ffaf` is the local commit from which draw 1 was archived (reflog subject:
`R106-E rep 1: … restore Sources to the live base`). The output is **not**
empty — 32 changed files, including:

```
6	1	Sources/MLXFastModel/LagunaConfig.swift
0	2597	Sources/MLXFastModel/LagunaRuntimeLayers.swift
4330	1657	Sources/MLXFastModel/LagunaRuntimeModel.swift
438	0	Sources/MLXFastTransform/AffineMetadataCoding.swift
401	0	Sources/MLXFastTransform/TiedHeadMetadataCoding.swift
56	8	Sources/MLXFastTransform/Transform.swift
0	39	Vendor/mlx-swift-lm/Libraries/MLXLLM/Models/Laguna.swift
0	68	Vendor/mlx-swift-lm/Libraries/MLXLMCommon/AttentionUtils.swift
0	29	Vendor/mlx-swift-lm/Libraries/MLXLMCommon/BaseConfiguration.swift
4	112	Vendor/mlx-swift-lm/Libraries/MLXLMCommon/BatchKVCache.swift
…  (32 files total)
```

`LagunaRuntimeLayers.swift` loses 2,597 lines and `LagunaRuntimeModel.swift`
is rewritten 4330/1657. That is not a marker-comment perturbation; that is a
different program. **Gate 1 fails. Draw 1 was not a `4b0e051b` replay.**

For completeness, draw 1 was also not literally `origin/main`:
`git diff --numstat 1bc1c895…8db6ffaf -- $PATHS` is likewise non-empty. Draw 1
sat on the branch's own working base — the `bd33883e`/`e33efe4e` "main-like"
family of Rule 95.3, which that rule measures at **0.386 % lower merit**
(z ≈ 3.07) than the `4b0e051b` family.

### 25.1 What the draw-1 receipt actually measured

| field | value |
|---|---|
| submission | `2771067` |
| `submissionCommitSha` | `dbd0b684c9abb9052720269250ff504ca2e421e9` |
| `officialScore` | 2.5938073513119 |
| candidate score `cs` | 2.574073 |
| session factor `f` | +0.7637 % |
| baseline decode | 4931.369 µs/step |
| baseline prefill | 188.1609 µs/token |

`dbd0b684` **does not exist in the local object store** — the service rewrites
the archive into its own commit, so the receipt SHA can never be used to
re-derive the submitted surface. The only usable provenance is the local
commit plus a byte-level surface identity (Rule 75), which is exactly why
Rule 75 exists.

The −3.09σ decode reading is now fully explained: `cs = 2.574073` is
0.58 % below the `4b0e051b` family mean (2.588955) and only 0.19 % below the
main-like family mean (2.578960). Draw 1 is an unremarkable member of the
family it was actually drawn from. **The corpus σ estimates in §20 stand;
this receipt does not widen them.**

### 25.2 Consequence

Every "replay" receipt in this campaign that was produced with the bare
`git checkout <tree> -- $PATHS` recipe is suspect and must be re-gated before
it is used as evidence about a tree. The corrected recipe is Rule 95.6's:

```bash
PATHS=$(jq -r '.editablePaths[]' benchmark.json)
git rm  -r -q --ignore-unmatch --  $PATHS      # <-- the missing line
git checkout <tree> --              $PATHS
git add -A --                       $PATHS
```

## 26. The corrected replay: commit `2131f574`

Executed on top of the merge of advisor base `89c2d154`
(merge commit `35750969`). All four Rule 95.6 gates pass:

| gate | command | result |
|---|---|---|
| 1 surface identity | `git diff --numstat 4b0e051b HEAD -- $PATHS` | **empty** |
| 2 base ancestry | `git merge-base --is-ancestor 1bc1c895… HEAD` | pass |
| 3 harness untouched | `git diff --quiet 1bc1c895… HEAD -- benchmark.json` | pass |
| 4 worktree clean | `git status --porcelain -u all -- $PATHS` | **empty** |

Rule 75 surface identity of `2131f574`:

| quantity | value |
|---|---|
| files under `editablePaths` | 141 |
| total bytes | **2,895,412** |
| `surface_sha256` | `c7c508105dc04409b23391e7b6ab956cafcef30daca1e7944939f172d5f638bf` |

The byte count matches Rule 95.5's published `4b0e051b` row exactly, which is
an independent confirmation of gate 1 that does not go through git.
`surface_sha256` is computed as

```bash
sort <filelist> | xargs shasum -a 256 | shasum -a 256
```

so it is reproducible by anyone with the tree and does not depend on git
object identity.

## 27. The draw ladder (Rule 95.7)

Preregistered before any draw is fired:

* **Tree**: `2131f574`'s surface, held fixed for every leg. The only change
  between legs is one comment line at
  `Sources/MLXFastModel/LagunaRuntimeModel.swift:9474`
  (`// senpai-r93-null-1` → `// senpai-r106e-replay-NN`), which exists solely
  to defeat the service's byte-identical-archive dedup. Zero structural risk;
  the compiler sees the same program.
* **Base SHA**: `1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7` (`origin/main`).
  The wrapper requires that the base's snapshot equal `origin/main` under
  `benchmark.json` + `editablePaths`; `origin/main` satisfies that trivially
  and is an ancestor of HEAD.
* **Stopping rule**: draw continuously, **one submission in flight at a time**
  (Rule 88), until either an `officialScore` exceeds the record
  **2.61650354381456** or the campaign deadline arrives. There is no
  preregistered `n`; the stopping rule is the record or the clock. This
  supersedes the stale `revision | r105-b-rev3` / "n = 6" markers in the
  earlier draft. Every receipt is recorded whether it helps or not, so the
  ladder doubles as the within-tree σ estimate the board needs.
* **Per-leg record**: `submissionCommitSha`, `officialScore`, `cs`,
  `baseline_decode`, `baseline_prefill`, derived `f`, plus the surface sha256
  and byte size.

Draw table (appended as receipts land):

| # | marker | submission | commit sha | officialScore | cs | f (%) | base decode µs | base prefill µs |
|---|---|---|---|---|---|---|---|---|
| 1 | (not a replay — see §25) | 2771067 | `dbd0b684` | 2.5938073513119 | 2.574073 | +0.7637 | 4931.369 | 188.1609 |
| 2 | `senpai-r106e-replay-02` | `59d24187-efc1-4730-af55-9c2244bcea59` | local `3394aa09` | (validating) | | | | |

### 27.1 Local pre-flight for the ladder tree

Before the first leg was fired the replayed surface was rebuilt from scratch
(`rm -rf .build && ./benchmark.sh --local-iterate`, 428 s wall) at commit
`173add95`:

```
"passed_correctness" : true,
"max_abs_diff"       : 0,
"first_failing_case" : null,
"golden_hash"        : "b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63",
"harness_hash"       : "74a297a67fc023c862c0d3fdbce67085b7b40556bed5f3b609964e236d5fac4f",
"passed"             : true
```

Exact-token correctness against the public long-copy gate, zero divergences,
and the surface reproduces its own recorded local baseline to within the
local noise floor (prefill 0.001112 → 0.001115 s/tok, +0.2 %; decode
0.012988 → 0.012970 s/tok, −0.1 %). The local `est score` of 0.796 is *not*
comparable to the ranked `cs` of ~2.59: the local-iterate reference baseline
is measured on this M4 host, and its prefill leg in particular does not
transfer (local `prefill_speedup` 0.33× vs a ranked leg that must be well
above 1). That divergence is the M4→M5 transfer caveat this campaign has
documented repeatedly; it is a property of the reference, not of the tree.

Each subsequent leg changes exactly one comment line, so this pre-flight
covers the whole ladder. Per-leg Rule 75 identity:

| leg | marker | files | bytes | surface sha256 | local commit |
|---|---|---|---|---|---|
| — | `senpai-r93-null-1` (= `4b0e051b`) | 141 | 2 895 412 | `c7c5081…f5d638bf` | `2131f574` |
| 2 | `senpai-r106e-replay-02` | 141 | 2 895 417 | `06b6818…4ceddbd1` | `3394aa09` |

The +5-byte delta is exactly the marker string length difference
(`senpai-r106e-replay-02`, 22 chars, vs `senpai-r93-null-1`, 17 chars), which
is a cheap independent check that nothing else moved.
