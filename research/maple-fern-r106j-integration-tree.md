# R106-J — The integration tree

Student: maple-fern · PR #625 · branch `maple-fern/r106-prefill-traversal-census`
Assignment `maple-r106-i-prefill-traversal-byte-census`, revision **`r106-i-rev2`**
Required base `446fe9875d1f95b1216628b5809a99da844e5c79` (advisor HEAD at assignment time)

Host for every local measurement in this document: **Apple M4 Pro, 48 GiB unified
memory, macOS 26.5.2, `applegpu_g16s` (Apple GPU generation 16)**. Generation 16
does **not** select the `_nax` kernel family that the ranked M5 uses, so no number
here is an M5 prefill claim. Tags: `[STRUCT]` host-independent structure,
`[M4-WALL]` measured wall time on this host, `[PROJ]` projected, `[M5-RCPT]` taken
from an official M5 receipt.

Receipts consumed by this round: **ZERO**. `senpai/submit-official.sh` was
inspected but never invoked.

---

## 0. Verdict

| outcome | fires when | fired? |
|---|---|---|
| **V-T1** | `4b0e051b`'s `Sources/` beats ours locally beyond the stated bar → adopt as integration base | **YES** |
| **N-T1** | T1 builds but is indistinguishable or worse → stay on advisor HEAD | no |
| **N-BUILD** | T1 does not build on our tree inside the timebox | **no — refuted** |
| **V-INTEGRATED** | one or more student patches land, verified, with a measured cumulative delta | see §5 |

Preregistered before any timing number was read: the bar for V-T1 is a
**block-contrast CI95 on `d(ln score)` that excludes zero**, with the
preregistered revert being "restore advisor-HEAD `Sources/` and hand frieren the
unmodified tree". The registered inferiority margin was **−0.40 % of `cs`**.

**Headline.** T1 builds, is token-identical to T0 on the full golden set, is
byte-for-byte equivalence-neutral against the vendored oracle, and is **faster**.

---

## 1. Carried forward from R106-I (Rule 79: a partial census with its stopping point stated is a result)

R106-I was cut short by the rev2 redirect at 2026-08-10T10:42:49Z. It had already
reached a terminal verdict, which is preserved in full at
`research/maple-fern-r106i-prefill-traversal-census.md` (46,867 B, committed on
this branch) and is **not** superseded by this document. Its result in brief:

**V-FLOORS-INFLATED.** The prefill DRAM floors the standing prior art quotes are
too high, and the two largest errors are arithmetic rather than physical.

- `B_pre = 31.3640 GB` BINDING `[STRUCT]` = **61.258 MB/token**, measured over the
  full 512-token prefill forward (rows 6115–7334 of the committed R106-G dispatch
  trace: 1220 dispatches, 81 encoders, 671 barriers), split over 12 families with
  a genuine null cell (`other` = 0 dispatches, 0 bytes).
- The assignment's own premise of a "hard tracer quota" is **factually wrong**
  (§2.2 there): there is no quota, cap or limit anywhere in
  `research/r106c/scripts/trace_dag.patch`. The old 1,671,168 B figure was
  R103-B page-flush truncation, already corrected. This is why **N-INSTRUMENT was
  rejected on the strongest available ground**.
- The routed-expert floor of **35.64 ms** `[PROJ]` is built from
  `1,769,472 × 256 × 39`. The trace shows **38** gather-GEMM layer pairs, not 39,
  and 20.26 % of `(layer, expert)` pairs receive zero rows. Correct M5 above-SLC
  cost is **29.06–30.52 ms** `[PROJ]`, i.e. **−6.58 to −5.12 ms (−18.5 % to
  −14.4 %)**. Both endpoints of the grouping-key bracket beat 35.64 ms, so the
  finding does not depend on the cache key meaning anything.
- **V-REREAD is refuted for routed weights on M5**: the expert-aligned `_nax`
  gather kernel never lets a threadgroup straddle two experts, so weight
  traversal multiplicity is **0.8613 < 1** — prefill reads *less* than the full
  expert set. The routed *activation* n-tile re-read is real (≈15.2 GB, 8.5×) but
  its working set is per-expert row slices of a few KB and is absorbed.
- The glue-class "99 % of floor" verdict is **refuted**, unconditionally on
  inconsistent class membership between its byte sum and its time sum, and
  conditionally on a true above-SLC floor of 4.19–8.29 ms `[PROJ]` against
  8.04 ms `[PROJ]` of projected time.
- Prefill read-multiplicity **TRAVERSAL/BINDING = 1.90–2.67× on M5** `[PROJ]`
  (3.40–4.39× on M4 `[STRUCT]`); above-SLC/BINDING = 0.729–1.186×; M5 above-SLC
  floor **41.86–76.48 ms** `[PROJ]` against `S = 97.89475 ms` `[M5-RCPT]`.

**Stopping point.** R106-I stopped before it could feed those corrected floors
back into a *time* attribution, because that half belongs to tanjiro (#620) — the
division of labour recorded at #620 is "she supplies the bytes; you supplies the
time". Nothing in R106-I was rolled back, and no part of it is restated as new
work below.

---

## 2. Stage 0 — the tree I am integrating onto

### 2.1 Base movement

The advisor branch moved `446fe987…` → `0db19dab35759b384ad332781b68beb2f4fc6ab4`
during this round. That commit touches **only `research/CURRENT_RESEARCH_STATE.md`**,
which is not one of the 97 `editablePaths`, so it changes no compiled path, no
surface byte count and no `harnessHash()` input. Per the advisor's instruction of
2026-08-10T10:51:19Z the `required_base_sha` for `r106-i-rev2` remains
`446fe987…` and I did **not** rebase mid-build.

### 2.2 Editable-surface numstat, verbatim

`research/artifacts/maple-fern-r106j/numstat_HEAD_vs_advisorbase.txt` is **empty** —
my branch HEAD carried no editable-surface delta from the advisor base when Stage 0
began. The advisor's Stage 0 table is reproduced and confirmed:

| comparison | editable files differing | verbatim artefact |
|---|---|---|
| advisor base vs `bd33883e` merged frontier | **1** (`LagunaRuntimeModel.swift`, 2136/2045) | `numstat_advisorbase_vs_bd33883e.txt` |
| advisor base vs `1bc1c895` `origin/main` | 27 | `numstat_advisorbase_vs_1bc1c895.txt` |
| advisor base vs `4b0e051b` best-ever | **32** | `numstat_advisorbase_vs_4b0e051b.txt` |

Off-branch trees were obtained with `git fetch origin <full-40-char-sha>`; none of
them is an ancestor of my HEAD and none was merged.

### 2.3 The Vendor half of `4b0e051b` is comment-only — so T1 is a pure `Sources/` contrast

This is the load-bearing structural fact of Stage 1 and it was proved, not assumed.

Of the 32 differing files between the advisor base and `4b0e051b`, 26 are under
`Vendor/**`. Taking the two vendor groups separately:

- `Vendor/mlx-swift/Source/Cmlx/**`: 34 added / 34 deleted non-comment lines.
- `Vendor/mlx-swift-lm/**`: 10 added / 10 deleted non-comment lines.

After stripping `/* … */` blocks, `// …` line comments and all whitespace, the
line multisets on both sides are **identical** in both groups
(`CMLX-NONCOMMENT-IDENTICAL`, `SWIFTLM-NONCOMMENT-IDENTICAL`). The entire
`Vendor/**` diff between the advisor base and `4b0e051b` is therefore
**comment-only**.

Two consequences:

1. **T1 is a semantically exact replay of `4b0e051b` at 118,503 fewer surface
   bytes.** Replaying only the two `Sources/` grants loses nothing compiled.
2. The T0→T1 contrast is a **pure `Sources/` contrast**. This is confirmed
   empirically in §4: `mlx.metallib` is byte-identical across the two arms
   (`8e8b18af…`, 158,502,072 B).

The six `Sources/` files that actually differ:

| file | added / deleted |
|---|---|
| `Sources/MLXFastModel/LagunaConfig.swift` | 1 / 6 |
| `Sources/MLXFastModel/LagunaRuntimeLayers.swift` | +2597 (new file) |
| `Sources/MLXFastModel/LagunaRuntimeModel.swift` | 1635 / 4308 |
| `Sources/MLXFastTransform/AffineMetadataCoding.swift` | 0 / 438 (deleted) |
| `Sources/MLXFastTransform/TiedHeadMetadataCoding.swift` | 0 / 401 (deleted) |
| `Sources/MLXFastTransform/Transform.swift` | 8 / 56 |

### 2.4 Surface byte census (Rule 75, BINDING against the 3,000,000 B cap)

`research/artifacts/maple-fern-r106j/surface_byte_census.txt`. `editablePaths` has
97 entries, two of which are **directory grants** (`Sources/MLXFastModel`,
`Sources/MLXFastTransform`) — there are no per-file `Sources/…` entries, which is
exactly why the partial replay of §3 is legal.

| tree | surface bytes | files | largest file | headroom to 3,000,000 |
|---|---|---|---|---|
| `446fe987` advisor base = **T0** | 2,680,208 | 142 | 384,245 | 319,792 |
| `bd33883e` merged frontier | 2,811,013 | 142 | 515,050 | 188,987 |
| `4b0e051b` best-ever receipt | 2,895,412 | 141 | 402,909 | 104,588 |
| `1bc1c895` `origin/main` | 2,983,849 | 142 | 511,418 | 16,151 |
| **T1 (constructed here)** | **2,776,909** | **141** | **402,909** | **223,091** |

T1 growth against the review base is **+96,701 B**, inside the 262,144 B
per-review growth cap; its largest file is 402,909 B, inside the 524,288 B
per-file cap. T1 leaves **223,091 B** of headroom for Stage 2 patches — more than
twice what `4b0e051b` itself would have left, which is the practical payoff of the
comment-only proof.

### 2.5 T0 force-clean build and golden set

`research/r106j/scripts/clean_build_and_iterate.sh T0`. The script preserves
`mlx.metallib` and its `.fingerprint` across `rm -rf .build-worker`, recreates
`.build-worker/arm64-apple-macosx/release` plus the `release` symlink, restores the
metallib, then runs `./benchmark.sh --local-iterate`. 236 compile tasks including
the Cmlx C++ tree, so this is a genuine cold build, not an incremental one.

| field | T0 |
|---|---|
| exit code | 0 |
| wall | 252 s `[M4-WALL]` |
| `passed` / `passed_correctness` | true / true |
| `max_abs_diff` | 0 |
| `checked_steps` | 130 |
| `peak_ram_gb` | 21 |
| `golden_hash` | `b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63` |
| `harness_hash` | `5cfe4988ee50e92376db6bfc3e8abd61b5258d31b3424fb0d91958b87873d398` |
| decode | 0.0129993912734375 s/tok `[M4-WALL]` |
| prefill | 0.001112037677734375 s/tok `[M4-WALL]` |

Rule 75 artefacts for the T0 cold build:

| artefact | sha256 | bytes |
|---|---|---|
| `mlxfast-runtime-worker` | `5cdfa7a1632001117deacbeed599439e5c8f84106cfc53a43bd9806e01a24199` | 49,185,640 |
| `mlx.metallib` | `8e8b18afaee1ed5a0190403f79a4cc74b9bebcb52b50c4b67d0ed91dc73097ec` | 158,502,072 |

The `baseline_*` fields in `score.local-iterate.json` come from a stale cached
baseline; under Rule 86 no delta against them is quoted anywhere in this document.

**Advisor HEAD builds force-clean and passes the golden set.** The "single most
urgent fact in the campaign" contingency does not fire.

### 2.6 T0 upstream equivalence — fails, and the failure is a known host artefact

`research/run_upstream_equivalence.sh` on T0 exits **1**.
`research/artifacts/maple-fern-r106j/T0.equivalence.log`.

It is not a zero-test invocation: `EQUIVALENCE_EXACT_STEPS=8`, one real test
executed in 34.97 s. The divergence is confined to the single prefill step:

| step | max abs logit error | mean abs logit error | runtime tok | upstream tok |
|---|---|---|---|---|
| prefill | **0.125** | **0.011933609** | 5991 | 5991 |
| decode-0 … decode-7 | **0** (all eight) | **0** (all eight) | 509/902/5991/… | identical |

**All nine argmax tokens are identical.** Only the tolerance-0 logit assertion
fails.

Rule 83 — this exact signature is established prior art, recorded independently in
six documents as a host-level near-tie on Apple GPU generation 16, which does not
reach the `_nax` prefill kernels the ranked M5 uses:

| document | line(s) | what it records |
|---|---|---|
| `research/maple-fern-vendor-byte-recovery.md` | 268–281 | base and candidate agreed "to every printed digit" |
| `research/advisor-r104-the-receipt-is-the-instrument.md` | 1633–1636 | calls it "a pre-existing near-tie" |
| `research/tanjiro-r86-base-gate-result.md` + `research/tanjiro-r86-base-gate.sh` | 173; 27 | base gate encodes the same expected failure |
| `research/maple-tanjiro-r85a-ranked-channel-diagnosis.md` | 177 | same signature |
| `research/nezuko-mbcap-up-prereg.md` | 142 | same signature |
| `research/maple-nezuko-r100c-router-weight-prefetch-restore.md` | 646 | same signature |

**No document in the campaign claims the oracle should pass on M4-class
hardware.** The standard practice recorded in those notes — reproduce identically
on the unmodified base, document it, leave `MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT`
**unset**, and treat exit 1 as non-blocking — is what I followed. The variable was
never set at any point in this round.

The operational consequence is that on this host the oracle is only usable as a
**differential** instrument: a candidate is equivalence-neutral iff its report
reproduces the base's report exactly. §4.2 applies exactly that test.

---

## 3. Stage 1 construction — the partial Rule 95.6 replay

`research/r106j/scripts/make_t1.sh apply`. `4b0e051b` *deletes* two
`MLXFastTransform` files, so a bare `git checkout` would silently leave them
behind — the defect the advisor corrected from Rule 93.4(f) into Rule 95.6. The
replay therefore runs `git rm -r -q --ignore-unmatch` over the two `Sources/`
grants **before** `git checkout 4b0e051b -- <same paths>`.

Because T1 is a *partial* replay, the four gates were re-derived rather than
copied. All four pass (`research/artifacts/maple-fern-r106j/t1_gates.txt`):

| gate | command | result |
|---|---|---|
| 1 | `git diff --numstat 4b0e051b HEAD -- Sources/MLXFastModel Sources/MLXFastTransform` | **empty** |
| 2 | `git merge-base --is-ancestor 1bc1c895… HEAD` | pass |
| 3 | `git diff --quiet 1bc1c895… HEAD -- benchmark.json` | pass |
| 4 | `git status --porcelain=v1 --untracked-files=all -- <the two grants>` | **empty** |

Gate 1 is restricted to the two grants precisely because the replay is partial;
the full-surface form of gate 1 would (correctly) fail on the comment-only
`Vendor/**` delta of §2.3. Replay base recorded in
`research/artifacts/maple-fern-r106j/t1_base.txt` = `761215841512774e61a6ce361201ae45d67c3223`.

**N-BUILD is refuted.** T1 compiles on our tree with no source edits at all. The
advisor's stated risk — that our `LagunaRuntimeModel.swift` might reference the two
deleted `MLXFastTransform` files — does not materialise, because T1 replaces that
file too. No part of the ~2 h N-BUILD timebox was needed.
