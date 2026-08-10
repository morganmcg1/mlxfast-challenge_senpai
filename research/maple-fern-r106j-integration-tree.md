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
| **V-T1** | `4b0e051b`'s `Sources/` beats ours locally beyond the stated bar → adopt as integration base | **no — see below** |
| **N-T1** | T1 builds but is indistinguishable, worse, or not transferable → stay on advisor HEAD | **YES** |
| **N-BUILD** | T1 does not build on our tree inside the timebox | **no — refuted** |
| **V-INTEGRATED** | one or more student patches land, verified, with a measured cumulative delta | see §5 |

Preregistered before any timing number was read: the bar for V-T1 is a
**block-contrast CI95 on `d(ln score)` that excludes zero**, with the
preregistered revert being "restore advisor-HEAD `Sources/` and hand frieren the
unmodified tree". The registered inferiority margin was **−0.40 % of `cs`**.

**Headline, in the order the evidence arrived.**

1. T1 builds with no source edits (**N-BUILD refuted**), is token-identical to T0
   on the full golden set across 24 paired runs (one single `golden_hash`), and is
   digit-for-digit equivalence-neutral against the vendored oracle.
2. On the *composite local score* T1 is faster: `d(ln score) = +0.3791 %`,
   CI95 `[+0.0492, +0.7091]` over six blocks. The preregistered V-T1 bar
   (CI excludes zero) is therefore met **on the letter**.
3. But **75 % of that composite is decode, and decode alone is a null**:
   `d(ln decode) = −0.3129 %`, CI95 `[−0.7847, +0.1588]`. The whole composite is
   carried by prefill (`−0.5777 %`, CI95 `[−0.8070, −0.3484]`), and **prefill on
   this host is `[M4-WALL]`**: PR #620 Stage 0 showed M4 prefill reproduces the
   ranked M5 prefill speedup at **1.1198× vs 1.9834× (−43.5 %)** because
   generation 16 cannot select `_nax`. A decode-only recomputation of the same
   blocks gives `+0.2347 %`, CI95 `[−0.1191, +0.5885]` — **not significant**.
4. §4.6 then identifies **what the T0↔T1 difference actually is**: after removing
   the `Sources/MLXFastTransform` offline code (923 of the 942 differing lines),
   the entire scored `Sources/MLXFastModel` delta reduces to **one loop-unroll
   depth in the decode-attention pairwise KV loop (T0 = 4-way, T1 = 2-way)**, plus
   a narrowed router-prefetch valid set and file-split cosmetics. Loop-unroll
   spelling is exactly the **#543 class the advisor has ruled non-transferable**,
   and unroll depth trades register pressure against occupancy — a quantity that
   differs between a 20-core M4 Pro and an M5 Max.

**Therefore the honest verdict for the purpose this experiment exists to serve —
choosing the tree frieren submits — is `N-T1`.** T0 (the current advisor base,
carrying the `bd33883e` promoted frontier) stays as the integration base. Adopting
T1 would mean **reverting a promoted frontier's 4-way unroll to 2-way on the
strength of an M4 prefill number that provably does not transfer**. T0 is also
**96,701 B cheaper on the submitted surface**, which is headroom I need for
sibling patches (§5).

`V-T1` is recorded as "fired on the letter of the preregistered bar, overturned
by the mechanism analysis in §4.6". Rule 72 requires me to say which; Rule 79
requires me to publish both.

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

---

## 4. Stage 1 result — T1 is correctness-neutral and measurably faster

### 4.1 T1 force-clean build and golden set

`research/r106j/scripts/clean_build_and_iterate.sh T1`, job `d29cb081`, rc 0, 305 s.
The `mlx.metallib` and its `.fingerprint` are preserved across the `rm -rf .build-worker`
so the AOT kernel set is provably held fixed; everything else is rebuilt from source.

| field | T0 | T1 | reading |
|---|---|---|---|
| `passed_correctness` | true | true | — |
| `max_abs_diff` | 0 | 0 | — |
| `checked_steps` | 130 | 130 | — |
| `golden_hash` | `b9509697c08a2cf3…` | `b9509697c08a2cf3…` | **identical** |
| `harness_hash` | `5cfe4988ee50e923…` | `67c7995898eacb35…` | **differs — positive control** |
| `peak_ram_gb` | 21 | 21 | — |
| decode s/token | 0.0129993912734375 | 0.0129027454453125 | T1 faster |
| prefill s/token | 0.001112037677734375 | 0.001124023681640625 | T0 faster on this single pair |

The pair of hashes is the point. `golden_hash` is a function of the emitted token
stream; it is unchanged, so **every checked greedy token is identical**. `harness_hash`
is a function of the submitted surface; it moved, so the harness did observe a
different tree and the identical `golden_hash` is not a stale-artefact reading.

Rule 75, BINDING, from `research/artifacts/maple-fern-r106j/{T0,T1}.status`:

| artefact | T0 | T1 |
|---|---|---|
| `mlxfast-runtime-worker` sha256 | `5cdfa7a1632001117deacbeed599439e5c8f84106cfc53a43bd9806e01a24199` | `ff2939002010fb610998958a8369587f64eb06a173bb6b6db6441e446aaa431e` |
| worker bytes | 49,185,640 | 49,091,304 (−94,336) |
| `mlx.metallib` sha256 | `8e8b18afaee1ed5a0190403f79a4cc74b9bebcb52b50c4b67d0ed91dc73097ec` | **identical** |
| `mlx.metallib` bytes | 158,502,072 | **identical** |

The byte-identical metallib is the empirical confirmation of the §2.3 comment-only
proof: the two arms differ only in Swift, never in a Metal kernel.

> ⚠️ **A binary hash is not an arm identity.** Across the sweep of §4.3 the worker
> sha256 took five distinct values on T0 and four on T1 — incremental relinks are not
> reproducible byte-for-byte. Only a *force-clean* build hash is a binding Rule 75
> artefact. Arm identity in the sweep is asserted by `git diff --numstat <arm-sha> --`
> being empty before every run, not by a binary digest.

### 4.2 T1 upstream equivalence — a null differential

`research/run_upstream_equivalence.sh` on T1: job `341f22cf`, exit 1, 40.03 s,
`EQUIVALENCE_EXACT_STEPS=8`, 1 real test executed.

**The T1 report is digit-for-digit identical to the T0 report of §2.6.** md5 over
every numeric line of the two reports is `740d5ab196ecaa4f5824175f8769ac3b` in both
cases; only the wall-clock line differs.

- prefill `maximumAbsoluteLogitError` 0.125, `meanAbsoluteLogitError` 0.011933609 — in **both** arms
- all 8 decode steps exactly 0.0 — in **both** arms
- all 9 argmax tokens identical (the 5991/509/902 pattern) — in **both** arms

The oracle exits 1 on this M4 for the *unchanged base too* (§2.6, Rule 83 prior art in
six campaign documents), so it is usable only as a **differential** instrument. As a
differential it returns exactly zero: **T1 is equivalence-neutral.**
`MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT` was never set, at any point, in any run in this report.

### 4.3 The paired ABBA sweep — the primary measurement

Design: **6 ABBA blocks, 24 runs**, `research/r106j/scripts/abba_t0_t1.sh`, run as
3 blocks (launched 2026-08-10T11:12:24Z, 2,229 s) then 3 more (2,242 s); the driver
continues the block phase across invocations rather than restarting it, so the
sequence is a single unbroken 6-block palindrome. Blocks alternate `T0 T1 T1 T0` and
`T1 T0 T0 T1`, so each block contributes one drift-cancelling contrast and the
**block is the independent unit**: dof = nblocks − 1.

Arm switching rewrites only the two `Sources/` grants, so every run in the sweep
shares one identical `Vendor/**` tree and one identical `mlx.metallib`. Before each
run `git diff --numstat <arm-sha> -- <the two grants>` is asserted empty; a
non-empty result aborts the sweep.

Estimator (Rule 40, named before the first number was read):

```
d(ln score) = -0.75 * d(ln decode_s_per_token) - 0.25 * d(ln prefill_s_per_token)
```

This is the exact log of the scored quantity, is dimensionless, and is therefore the
only form of this measurement that can survive the M4→M5 step-time mismatch.

**Correctness across all 24 runs: 0 failures, `max_abs_diff` 0 everywhere, and exactly
one distinct `golden_hash` (`b9509697c08a2cf3`) across both arms.** That is the
strongest bit-exactness evidence in this document: 24 independent builds of two
different source trees produced one hash.

Within-arm dispersion, n = 12 per arm:

| arm | decode mean s/tok | decode CV | prefill mean s/tok | prefill CV |
|---|---|---|---|---|
| T0 | 0.012953958 | 0.4107 % | 0.001118236 | 1.0006 % |
| T1 | 0.012913502 | 0.4482 % | 0.001111749 | 0.3285 % |

Block contrasts, T1 minus T0, natural log, n = 6 blocks, dof = 5, t(0.975) = 2.571:

| quantity | estimate | CI95 | block sd | blocks favouring T1 | reach |
|---|---|---|---|---|---|
| d(ln decode) | −0.3129 % | **[−0.7847, +0.1588]** | 0.4494 % | 1/6 positive | `[M4-WALL]`, transfers |
| d(ln prefill) | −0.5777 % | [−0.8070, −0.3484] | 0.2185 % | 0/6 positive | **`[M4-WALL]`, does NOT transfer** |
| **d(ln score)** | **+0.3791 %** | **[+0.0492, +0.7091]** | 0.3143 % | 5/6 | mixed |
| d(ln score), prefill held neutral | +0.2347 % | **[−0.1191, +0.5885]** | 0.3372 % | — | conservative |

Per-block `d(ln score)`: +0.3489, +0.3982, +0.3358, +0.8501, **−0.1311**, +0.4729 %.

Three things this table says that the 3-block table did not:

1. **The 3-block tightness was luck.** Block sd on `d(ln score)` went from 0.0329 %
   to 0.3143 % — a factor of 9.6 — when blocks 4–6 arrived, and block 5 changed
   sign. Reporting the 3-block CI `[+0.2792, +0.4428]` as the result would have
   been a false-precision claim. Rule 79: the correction is published, not buried.
2. **Decode alone cannot distinguish the arms.** `d(ln decode)`'s CI spans zero and
   only 1 of 6 blocks favours T1. Decode is 75 % of the score weight and is the axis
   that *does* transfer M4→M5.
3. **The composite win is a prefill win**, and prefill is the axis this host cannot
   speak to (§4.5, and PR #620's −43.5 % non-reproduction of the ranked M5 prefill
   speedup). Holding prefill neutral — the conservative reading forced by the nax
   wall — the effect is `+0.2347 %` with a CI that includes zero.

Raw rows: `research/artifacts/maple-fern-r106j/abba/runs.tsv`; per-run logs and score
JSON: `abba/run<idx>.<arm>.{log,json}`.

### 4.4 An instrument artefact I found in my own design, and its sign

`abba_t0_t1.sh` rewrites `Sources/` before every run, but Swift's incremental build
is content-addressed: when a run's arm equals the previous run's, nothing recompiles.
That run therefore also skips ≈40 s of incidental GPU cooldown and **starts hotter**.
Its wall time drops from ≈195 s to ≈155 s and its measured time rises.

`research/r106j/scripts/abba_slot_diagnostic.py`, output in
`abba/slot_diagnostic.txt`, expresses every run as a log deviation from its own
arm's mean, which removes the arm effect and isolates the slot:

| slot | n | decode dev | prefill dev |
|---|---|---|---|
| freshly recompiled | 18 | −0.1160 % | −0.1405 % |
| **reused previous build** | 6 | **+0.3445 %** | **+0.4114 %** |

The reuse slot is always **position 3 of a block**, and it carries a **≈0.46 %
decode penalty** relative to a freshly-recompiled run. That is larger than the effect
being measured, so slot assignment is not a detail.

Over 3 blocks the slot had been held by **T1 twice and T0 once** and I computed a
−0.071 % bias against T1 from that imbalance. **Over the full 6 blocks the tally is
T0 : 3, T1 : 3, so the bias is exactly zero and the correction is withdrawn.** The
6-block headline needs no adjustment. This is the reason the design specifies an even
number of blocks and the reason `abba_t0_t1.sh` continues the block phase across
invocations rather than restarting it — restarting would have driven the imbalance to
4 : 2 instead of curing it.

**Design rule carried into every later sweep in this document**: run blocks in even
multiples, and check `slot_diagnostic.txt` for a balanced tally *before* reading any
headline. The `T0 vs T0P` sweep of §5 is 4 blocks for this reason.

### 4.5 What this measurement is, and what it is not

- It **is** a paired, blocked, drift-cancelled, correctness-gated M4 wall-clock result
  on a dimensionless log-ratio of the exact scored quantity.
- It is **not** an M5 result. M4 Pro reports Apple GPU generation 16 and cannot select
  the `_nax` prefill kernels the ranked M5 uses. The T0→T1 delta is entirely Swift-level
  (§2.3 proves the Metal side is untouched, and the byte-identical metallib of §4.1
  confirms it), so the kernel-family reachability objection does not apply to the
  *mechanism*; the campaign's recorded M4→M5 discount menu (×1.000 / ×0.622 / ×0.505 /
  ×0.436) still applies to the *magnitude*. At ×0.505 the conservative +0.2347 %
  becomes +0.119 %, which is a quarter of the 0.4 % handoff bar.
- The apparent ranked-channel corroboration I recorded at 3 blocks — that this
  `Sources/` tree produced `cs` 2.590559 against the merged frontier's 2.582286 —
  **does not survive scrutiny and is withdrawn**. 2.590559 was a max-of-five draw;
  the winner's-curse correction is +0.2881 %, giving a corrected best-tree `cs` of
  **2.583106**, i.e. a gap of ≈+0.03 % rather than +0.32 %. `sd(ln officialScore)` is
  0.3728 %, so the ranked channel cannot resolve an effect of this size at all. It is
  neither corroboration nor refutation; it is noise, and §4.6 explains why I no longer
  need it.

### 4.6 What the T0↔T1 difference actually *is* — and why that overturns V-T1

A timing number tells you *whether*; it does not tell you *what*. Before handing
frieren a tree I had to know which mechanism I would be shipping. A textual `git diff`
is useless here because T1 splits `LagunaRuntimeModel.swift`, moving ≈2,597 lines into
a new `LagunaRuntimeLayers.swift`: every moved line shows as both a deletion and an
insertion. I therefore wrote `research/r106j/scripts/tree_content_diff.py`, which
compares the two trees as **multisets of non-comment, whitespace-normalised lines**.
A moved line cancels; only genuinely added or removed content survives.

**Probe 1 — the identifier set.** Every `laguna*` identifier in each tree:

| tree | distinct `laguna*` identifiers | present in T0 but absent from T1 |
|---|---|---|
| T0 | 428 | — |
| T1 | 435 | **0** |

T1 is a strict superset at the identifier level: **no kernel, pipeline, or entry point
that T0 has is missing from T1**. Neither tree contains any `_nax` token at all —
`_nax` selection lives in `Vendor/mlx-swift`, which §2.3 proves is comment-only
between the two. `[STRUCT]`, host-independent.

**Probe 2 — the whole-`Sources/` line multiset.**

| direction | non-comment lines |
|---|---|
| in T0, not in T1 | **923** |
| in T1, not in T0 | 19 |

**Probe 3 — restrict to the scored path.** Re-running the same probe over
`Sources/MLXFastModel` only:

| direction | non-comment lines |
|---|---|
| in T0, not in T1 | **91** |
| in T1, not in T0 | 16 |

So **923 − 91 = 832 of the T0-only lines are not on the scored path at all**. They are
entirely `Sources/MLXFastTransform` — `AffineMetadataCoding.swift` and
`TiedHeadMetadataCoding.swift`: safetensors header parsing, `CheckpointIndex`,
a scale/bias LUT, `GeneratedAffineMetadataReport`. That is **offline weight
transformation**, which by the challenge contract runs before the timed window and
cannot appear in either the decode or prefill measurement.

**Probe 4 — read the surviving 91 lines.** They collapse into three items:

| # | what | lines | scored? |
|---|---|---|---|
| 1 | **decode-attention pairwise KV loop unroll depth** | ≈85 | **yes, hot** |
| 2 | router prefetch valid set `[0,1,5]` (T0) vs `[0,1,2,3,4,5]` (T1) | ~4 | compile-time variant count |
| 3 | `lagunaInjectPoolUInt4 = 1 << 24` respelled; access modifiers/imports from the file split | ~2 | no |

Item 1 is a **single localised hunk region** (diff lines 4064–4178) in the pairwise KV
traversal:

| | T0 (advisor base = promoted `bd33883e` frontier) | T1 (`4b0e051b`) |
|---|---|---|
| loop guard | `for (; i + 3*BN < N; i += 4*BN)` | `for (; i + BN < N; i += 2*BN)` |
| pipelined regs | `pipe_kc, pipe_kd, pipe_vc, pipe_vd` present | absent |
| pointer bump | `pair_keys += 4 * inner_k_stride` | `pair_keys += 2 * inner_k_stride` |
| effective depth | **4-way** | **2-way** |

**That is the whole of it.** The entire scored difference between the two trees — and
therefore the entire cause of the §4.3 timing contrast — is **how deeply one KV loop
is unrolled**. `[STRUCT]`.

**Why this overturns V-T1.**

1. **It is the #543 class the advisor has already ruled non-transferable.** Rule 98
   re-attributed my own R99 `+1.824 %` to *loop spelling*, with the explicit finding
   that loop spelling does not transfer across hosts. Unroll depth is loop spelling in
   its purest form.
2. **Unroll depth is exactly the quantity that trades register pressure against
   occupancy**, and register file per core, core count, and scheduler width all differ
   between a 20-core M4 Pro and an M5 Max. AGENTS.md warns in terms that "threadgroup
   geometry can also change sign across core counts"; unroll depth is the same kind of
   quantity. A 4-way unroll that spills on one part may fit on another.
3. **T0's 4-way unroll is the later, promoted state.** `4b0e051b` (2026-08-09 02:56)
   predates `bd33883e` (2026-08-09 18:27); T0 carries `bd33883e`'s `Sources/`.
   Adopting T1 does not mean "taking a newer frontier" — it means **reverting a
   promoted frontier's unroll depth from 4 back to 2 on M4 evidence whose only
   significant component is prefill, the axis this host provably cannot measure.**
4. **The decode axis — the one that does transfer, and 75 % of the weight — is a
   null.** `[−0.7847, +0.1588]`, 1/6 blocks positive.

**Verdict: `N-T1`.** T0 stays. The paired evidence for T1 is real but it is prefill
evidence about a non-transferable mechanism, and adopting it would silently revert a
promoted frontier.

**Two things T1 is still worth.**

- It is a **positive control on the whole instrument**: 24 runs, two genuinely
  different source trees, 0 correctness failures, one `golden_hash`, and a
  digit-for-digit identical equivalence differential. The rig can tell trees apart on
  timing while proving they are token-identical.
- **Unroll depth 4 vs 2 in the pairwise KV loop is a clean, single-hunk, empirically
  bit-exact knob** (24/24 runs, one hash) that is *cheap to test on M5* and that
  nobody in this campaign has adjudicated on the ranked host. I am not testing it — I
  cannot — but it is a concrete, pre-localised follow-up with the diff region already
  identified. See §6.

**Byte-budget consequence.** T0's surfaces are **96,701 B smaller** than T1's
(2,680,208 B vs 2,776,909 B against the 3,000,000 B cap). Choosing T0 leaves
**319,792 B** of headroom for sibling patches instead of 223,091 B — and the per-file
cap matters too, since `LagunaRuntimeModel.swift` is 384,245 B under T0 against
402,909 B under T1, both under the 524,288 B per-file cap but with materially
different room.

**Open question I did not close, and why it does not change the verdict.** I did not
verify whether `./benchmark.sh --local-iterate` re-runs `MLXFastTransform`, nor
whether T0's runtime consumes the T0-only affine metadata. If it does, some of the
832 offline lines could in principle touch a *pre-window* cost. Either way it applies
identically to both arms in every paired block, so the contrast in §4.3 stands; and
the mechanism identification in Probe 4 is unaffected because the scored-path probe
already excludes those lines.


## 5. Stage 2 — the integration queue and what I actually landed

### 5.0 The acceptance rule I apply, stated before the queue arrives

Rule 72 requires the decision procedure to be fixed before the evidence. Mine is:

> **A patch enters the integrated tree only if (a) it is bit-exact by construction or
> carries a margin certificate, (b) it has a paired, contemporaneous, locally measured
> win on *this* tree, and (c) it is behaviourally live on the ranked host.**

Clause (c) is the one this round adds, and it is the reason the queue is thinner than
it looks. Rule 99 (the nax wall) says prefill mechanisms that route through `_nax`
kernels cannot be measured here at all; my own §4.3 result is the worked example of
what happens when you forget that. Clause (b) is frieren's bar restated: a *composed*
paired win on the integrated tree, not a sum of siblings' isolated deltas. Clause (a)
is what keeps the correctness gate a formality rather than a gamble.

There is a fourth, weaker rule that only applies to sub-threshold patches:

> **A default-inert patch is carried but not activated.** Merging the code costs bytes
> and nothing else; flipping its default without a measurement is exactly the move
> this campaign has repeatedly punished.

### 5.1 The queue as of 2026-08-10T13:30Z

| # | student | charge | state at my freeze check | disposition |
| --- | --- | --- | --- | --- |
| #636 | alphonse | expert gather-GEMM floor (`C2a`, `DARKBLOOM_EXPERT_DOWN_BN`) | **terminated `N-FLOOR`, merged to advisor `main`** | **carried, inert** (§5.2) |
| #642 | tanjiro | decode fused attention, prologue prefetch hoist | **terminated `N-ISSUE-BOUND` at 12:57Z, `succeeded`, submitted diff is ZERO BYTES** | **nothing to integrate** (§5.4.1) |
| #629 | edward | routed gate/up packing; Stage A settles L3 | open, draft, head `526881c4`, no marker at 13:30Z | L3 measured independently by me (§5.3) |
| #616 | nezuko | round-103 revert residual | open, head `c8f2c87d`, no marker at 13:30Z | pending |
| #597 | frieren | bit-exactness shelf + margin-certificate script; also owns the pf-default adjudication | **terminated `r105-b-rev5` at head `95a0ef9e`, status `failed`, NO SHIP** | **nothing to integrate** — "Rule 75: nothing owed" (§5.4.2) |

Only the `senpai-result:v1` marker in a PR comment counts as termination for this
table.

**Correction to my own 13:05Z reading.** At 13:05Z I recorded #597 as carrying no
result marker. That was wrong, and the error was mine rather than the clock's: the
`r105-b-rev5` marker sits at head `95a0ef9e`, which was already #597's head when I
looked, so it was visible and I missed it. The 13:30Z re-poll found three markers on
#597 (rev1 `inconclusive`, rev4 `succeeded`, rev5 `failed`) and the last is terminal.
I am flagging the miss rather than silently overwriting the row, because §5.0's
acceptance rule keys on exactly this signal and an integrator who mis-reads it once
should say so.

**Consequence: the slate is closed.** Three of the five siblings are terminal and all
three hand the integrator zero bytes (#636 inert, #642 zero-byte diff, #597 "nothing
owed"). The two still open at 13:30Z — #629 and #616 — have produced no marker with
~17 h to my freeze. So the integrated tree is `T0` plus, at most, the one candidate I
am measuring myself: the §5.3 packing flip.

### 5.2 Candidate A — alphonse's `C2a`: carried as merged, deliberately left inert

`C2a` is already in my base. It arrived with the advisor tip `2454cc01`, not through a
patch file, and it is the **only** non-documentation change between my required base
`446fe987` and that tip:

```text
$ git diff --numstat 446fe987 2454cc01 -- Sources Vendor benchmark.json Package.swift
25	0	Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp
```

One file, +25 lines, 0 deletions, commit `c768d21f`. It adds `darkbloom_expert_down_bn()`
reading `DARKBLOOM_EXPERT_DOWN_BN` — **default `64`, which is the pre-existing value** —
and accepts only `32` or `64`. The guard that consumes it lives inside
`gather_qmm_rhs_nax` and is further restricted to `K==512 && N==2048 && bm==64 &&
wm==4 && (wn==2 || wn==1)`, non-affine, transposed, `gs==16`, `bits==4`, `M>=64`.

**Decision: carry it, do not set the env var.** Three independent reasons, any one of
which is sufficient:

1. **Its own author says so.** §11.1 of `maple-alphonse-r107c-expert-gather-gemm-floor.md`
   reads *"Recommendation: do NOT integrate C2a on its own"*, verdict `N-FLOOR`, priced
   at **0.195 % of score** (robust band 0.19 %–0.30 %) against this round's 0.4 % gate,
   and below the 1.35 ms 3σ bar. The family is **DRAM-bound on M5** (51.6 FLOP/B
   measured against an M5 balance of 63.5–104), which is adverse to an arm whose only
   lever is latency hiding while it doubles A-side request multiplicity 32× → 64×.
2. **I cannot measure it here.** The guard sits in `gather_qmm_rhs_nax`. This host is
   GPU generation 16 and never selects a `_nax` variant (Rule 99), so on my box the
   flip is *dead code*, not a slow path. `N-REACH` is alphonse's own reachability
   verdict and it matches mine. Activating an unmeasured default would be a submission
   with zero local evidence behind it.
3. **It violates my own clause (b) and frieren's bar.** A composed paired win must be
   measured. There is no measurement of `BN=32` on any host in this campaign.

**What "carried" costs.** Nothing behavioural, and 1,740 B of surface. Rule 75 digests,
reproduced from alphonse's ledger so the handoff is self-contained:

| artefact | sha256 |
| --- | --- |
| `quantized.cpp` blob at alphonse's `BASE_SHA e1d206da` | `cf6d3847d583730fc7366110d91f54c676405869634cd0ae4eebbd362363c612` |
| `quantized.cpp` candidate blob (pre-compile == post-compile) | `e5dac8a08c2a04c565fb575d86e710721d548413e826fa113f9b99dc23f33258` |
| offline preamble+kernel surface during the AIR census | `803fe16405b346e41b80f5202c4d5135c137f95c94051e69b37c5679ae3c2eba` |

I verified the third digest is *not* something I need to reproduce: it is an offline
census artefact, not a submitted path.

**One finding of his I am propagating even though it is not a patch.** With `BM=64,
WM=4`, only **1 of 4 simdgroups per threadgroup issues MMA** on the largest prefill
family — a ~4× MMA-occupancy deficit, invariant under `bn`. That is a structural
`[STRUCT]` observation about the ranked host, it is worth more than every patch in this
queue, and no one currently owns it. See §6.9.

### 5.3 Candidate B — the packing default flip (L3)

#### 5.3.1 What the patch is, and why I claim it is bit-exact without a certificate

`research/tanjiro_packing_default_flip.patch` — 1,844 B, sha256
`96161c17d68a1091934bb0d4de5e15097cfb3ba7f227efca9e04ac7bc23c493d`. Three hunks, all
inside `lagunaDecodeNVFP4QKVLaneMajorSource(pairwise:)`:

| hunk | change |
| --- | --- |
| 1 | `num_simdgroups` 2 → 8 |
| 2 | pipeline rename `..._r1_v1_lm1` → `..._lm1_sg8` |
| 3 | a `rows % 8 == 0` guard, and grid `((rows/2)*64)` / TG 64 → `((rows/8)*256)` / TG 256 |

The bit-exactness argument is structural rather than empirical, which is why it needs no
margin certificate. The kernel is **lane-major**: each output row is computed
independently by a fixed set of lanes, and `num_simdgroups` participates in exactly one
place — the map `out_row → (tile, simd_gid)`. It is not a reduction width, not an
accumulation order, and not a tiling of the K dimension. Changing it re-labels which
simdgroup computes which row; it does not change what any row computes, in what order,
or at what precision. Hunk 3 keeps `threads = rows * 32` invariant
(`(rows/2)*64 == (rows/8)*256 == rows*32`), so the launch is the same thread count in a
different threadgroup shape. And `rows` on this model is always a multiple of 128, so the
new guard can never fire on any production configuration.

⚠️ I state the limit of that argument honestly: it establishes that the *arithmetic* is
identical, not that the *compiler output* is. A different threadgroup shape can change
register allocation and therefore scheduling. That cannot change results in a kernel with
no cross-lane reduction, but it is the reason I still gate on `max_abs_diff == 0` and a
single `golden_hash` across every run of every arm rather than declaring victory from the
source diff. The first two runs of the aborted sweep already agreed on
`golden_hash b9509697c08a2cf3`, so the empirical check is not merely hypothetical.

#### 5.3.2 The contested prior — stated before the result, not after

This lever arrives with a **genuine sign conflict** and I want it on the record before my
own number exists:

- **#308** measured it at **−36.9 µs/step, CI [−61.0, −12.9]** ⇒ **+0.562 % of `cs`**,
  CI [+0.196 %, +0.929 %].
- **#48** measured an 8× threadgroup collapse in a neighbouring family at **−0.1488 %**,
  i.e. the opposite sign.

These are not trivially reconcilable, and the campaign's own doctrine says threadgroup
geometry can change sign across core counts. So the honest prior is *wide and centred
near, not far above, the 0.4 % bar*. That is precisely why the state doc shelved it as
"L3 — do not assign yet" rather than banking it.

#### 5.3.3 Preregistration (written 2026-08-10T13:20Z, while the sweep is still running)

**Design.** Paired ABBA, arms `T0` (HEAD) and `T0P` (HEAD + the patch), four runs per
block in palindrome order with the order reversed every block, `--local-iterate` in
situ, force-clean per-arm selection with a sha256 guard on
`Sources/MLXFastModel/LagunaRuntimeModel.swift` before every run
(T0 `a736b50f…`, T0P `9c226373…`). Estimator, fixed in advance:

```
d(ln score) = -0.75 * d(ln decode) - 0.25 * d(ln prefill)
```

with the block as the unit of analysis and a Student-t CI95 on the per-block deltas.

**Power, stated in advance.** sd(d ln score) per block is 0.3143 % from my own T0↔T1
sweep. Four blocks therefore give a CI half-width of ≈0.50 %, eight blocks ≈0.26 %.
Against a 0.4 % bar and a prior centred at +0.562 %, four blocks **cannot** produce a
decisive answer and I say so now: I am launching four to get a fast read and I have
already decided to extend to eight unless the four-block point estimate is so far from
the bar that eight cannot move the verdict. Rule 58 — I extend the same sweep, I do not
restart it.

**Acceptance, fixed before the numbers.** `T0P` becomes the handoff tree if and only if
all four hold:

1. zero correctness failures and exactly one `golden_hash` across every run of both arms;
2. the CI95 on d(ln score) excludes zero;
3. the point estimate is **≥ +0.40 % of `cs`**;
4. the surface census still passes Rule 75 (the patch adds 29 B to a file with 140,043 B
   of headroom, so this is a formality, but it is checked, not assumed).

**Preregistered revert.** If any of the four fails, the handoff tree is `T0` unchanged
and I report `N-PACK`. The revert is mechanical: `RESTORE_ARM=T0` in the sweep driver
already leaves the worktree matching HEAD, so "revert" is the absence of a commit, not an
undo.

**The null cell I will report either way (Rule 79).** d(ln prefill) for a decode-only
kernel change is a null cell by construction — the patch cannot touch prefill — so its
measured value is a live estimate of my instrument's per-block noise on this host, and I
report it next to the effect cell whatever it says. If prefill moves *significantly* in
either direction, that is evidence of an instrument or thermal problem, not of a prefill
effect, and it invalidates the block rather than supporting a claim.

#### 5.3.4 Result — blocks 1–4

Job `2da318e3-ce34-4635-a247-3594ccf4b77b`, exit 0, 2,509 s, 16 runs, four complete
blocks in alternating `ABBA`/`BAAB` phase. Artifacts committed at `79d504e5`.

**Acceptance criterion 1 passes, and it is the most valuable thing in this subsection.**

```
correctness failures : 0 / 16
distinct golden_hash : 1  -> b9509697c08a2cf3
max_abs_diff         : 0 on every run of both arms
```

The `golden_hash` is also the same value Stage 0 recorded for unmodified `T0`
(`b9509697c08a2cf3…`, §2.5). So the §5.3.1 bit-exactness argument — lane-major
addressing means `num_simdgroups` only re-labels `out_row → (tile, simd_gid)`, the
`threads = rows*32` invariant is untouched, and the `rows % 8` guard is unreachable
because `rows` is always a multiple of 128 — is now an **argument with 8 independent
confirmations** rather than an argument alone. That result is robust and I report it as
the durable finding of this arm regardless of what the timing does.

**The timing does not clear the bar, and is not even the right sign.**

| cell | estimate | CI95 | sd/block | blocks positive |
|---|---|---|---|---|
| d(ln decode) | −0.0923 % | [−1.0474, +0.8627] | 0.6003 % | 2/4 |
| d(ln prefill) *(null cell)* | **+0.5193 %** | [−0.0150, +1.0537] | 0.3359 % | **4/4** |
| **PRIMARY d(ln score)** | **−0.0606 %** | **[−0.8640, +0.7428]** | 0.5050 % | 2/4 |
| conservative (prefill neutral) | +0.0692 % | [−0.6471, +0.7855] | 0.4502 % | 2/4 |

Per-block d(ln score) %: **+0.3022, −0.3693, −0.6056, +0.4303**.

Criterion 2 (CI excludes zero) fails. Criterion 3 (point ≥ +0.40 %) fails, and fails on
the *wrong side of zero*: the point estimate is a 0.06 % **regression**, six times the
distance from the bar in the unhelpful direction.

**The null cell fired, and I am reporting it as preregistered.** d(ln prefill) is
+0.5193 % with 4/4 blocks positive. The patch is three hunks inside
`lagunaDecodeNVFP4QKVLaneMajorSource(pairwise:)` — a decode-only kernel that the prefill
pass never dispatches — so a real prefill effect is mechanically impossible and this is
my instrument talking. Two contributors are identifiable in the raw rows:

1. **A warm-up row.** Run 1, the first run of the whole sweep and a `T0` row, has
   prefill 0.001125031 against ≈0.001111 for every later `T0` row. That single row
   inflates block 1's control mean and therefore pushes block 1's prefill contrast
   positive on its own.
2. **The slot artefact from §4.4, now visible on the prefill axis.** The worker binary
   sha256 differs run to run (six distinct prefixes per arm across eight runs — the
   release build is not byte-reproducible on this host), and consecutive same-arm rows
   share a binary while the outer pair of an `ABBA` block does not. §4.4 measured this as
   a decode-side penalty for reused-build slots; the `T0P` sweep shows it also has a
   prefill-side component, and the palindrome phase alternation is exactly what is
   supposed to cancel it over an even number of blocks.

Because the null cell is not clean, the *conservative* row (prefill charged as neutral,
which is also the row the M4 nax wall of Rule 99 demands I quote for anything
prefill-touching) is the row I weight: **+0.0692 %, CI [−0.6471, +0.7855]**. Still a
dead null, still nowhere near +0.40 %.

**The prior was wrong before I measured it — a unit audit of #308.**

I did not go looking for this; I went to the source to state the prior fairly in §5.3.2
and found the arithmetic does not hold. #308's own report
(`research/maple-tanjiro-threadgroup-packing-curve.md:342-380`) says, verbatim:

> Reference `S=2` absolute mean **8196.8 µs/step**. `%` of score uses the campaign
> constant 0.015280 % per µs/step of decode.

and `36.9 × 0.015280 = 0.5638`, which reproduces the quoted **+0.56 %** to three
decimals. But those two numbers are from different machines. `0.015280 % per µs/step` is
`0.75 / decode_M5_µs_per_step`, an **M5** constant — it is the same object as this
campaign's "1 % of `cs` = 65.67 µs/step". The `−36.9 µs/step` and the `8196.8 µs/step`
reference are both **M4 Pro** (#308 declares M4 Pro in its own limitations section).
Pricing an M4 absolute µs delta with an M5 µs-denominator silently asserts that the two
hosts have the same per-step time. They do not.

The host-independent route is to stay in relative units, which is what the score formula
actually consumes:

```
relative decode delta = 36.9 / 8196.8      = 0.4502 %   (within #308's own session)
% of cs               = 0.75 x 0.4502      = 0.3376 %
CI                    = 0.75 x [12.9, 61.0] / 8196.8 = [+0.118 %, +0.558 %]
```

So the correctly-transferred prior is **+0.338 % of `cs`, CI [+0.118, +0.558]** — under
the +0.40 % bar *before a single run*, with a CI whose upper end only grazes it. The
inflation factor is exactly the M4:M5 per-step ratio, ≈1.67×. This assumes only that a
*relative* decode delta transfers 1:1 M4→M5, which is the one transfer this campaign has
direct evidence for (Rule 99: my decode ln-ratio reproduced M5's to +0.15 %); every other
transfer route in the menu (×0.622, ×0.505, ×0.436) discounts it **further**, and the
bytes-pool route that this kernel actually sits in (×0.4369) lands at ≈+0.245 %.

This does not change the corpus's own posture — `RESEARCH_ARCHIVE:161-171` already labels
the figure "+0.56 % **undiscounted**", attaches #48's contrary M5 receipt at −0.1488 %
for the same 8× collapse on the same QKV grid, and `CURRENT_RESEARCH_STATE:3327-3332`
holds L3 at "**do not assign yet** … geometry neutrality is absolute until #496". What it
changes is the headline number that a hurried integrator would have read off the queue. I
am recording the correction because the wrong figure appears in at least four places in
the corpus and would otherwise be re-inherited by the next round: **the honest ceiling on
this patch was never 0.562 %, it was 0.338 %, and the bar is 0.400 %.**

**Interim disposition.** §5.3.3 said I had "already decided to extend to eight unless the
four-block point estimate is so far from the bar that eight cannot move the verdict".
Eight *can* still move it arithmetically — blocks 5–8 would need to average +0.90 % to
carry the mean to the bar — so the escape clause does not fire and I extend rather than
stop, exactly as written. Job `0ca1fee0-a277-4ece-9783-f74fc63c21cf`, launched
2026-08-10T13:38Z, resumes the *same* `runs.tsv` at row 17 (Rule 58: extend, never
restart).

#### 5.3.5 Candidate C, held in reserve — `T0U`, the unroll-depth hunk of the T1 contrast

Declared here **before** the §5.3 result is known, so that it cannot be read as a
post-hoc rescue. §4.6 established that the measured T0→T1 score contrast
(**+0.3791 %, CI [+0.0492, +0.7091]**) is carried by a small number of mechanisms, of
which the largest is a *loop-spelling* change in the fused sliding-attention decode
kernel. I have now isolated it in the git objects, without touching the worktree:

```
git diff -U3 446fe987 4b0e051b -- Sources/MLXFastModel/LagunaRuntimeModel.swift
  @@ -1636,37 +1637,21 @@   -for (; i + 3 * BN < N; i += 4 * BN) {
                             +for (; i + BN < N; i += 2 * BN) {
  @@ -1740,80 +1725,8 @@   -    pair_keys   += 4 * inner_k_stride;
                             -    pair_values += 4 * inner_v_stride;
                             +    pair_keys   += 2 * inner_k_stride;
                             +    pair_values += 2 * inner_v_stride;
```

T0 runs the pairwise KV block loop **4 pipeline stages deep** (`a,b,c,d`); T1 runs it
**2 deep** (`a,b`). Everything between those two hunk anchors is the deletion of the
`pipec_*`/`piped_*` stage bodies, which are textual replicas of the `pipea_*`/`pipeb_*`
bodies with different pointers.

**Why it is bit-exact.** The online-softmax state (`pair_max*`, `pair_sum*`,
`pair_o*[0..3]`) is updated strictly in program order by each stage, and each stage
accumulates into the *same* registers rather than into per-stage partials — T1's own
doc comment at diff line 1247 says so explicitly ("on into the same register. Giving
each unrolled step its own partial and … "). Both spellings visit keys
`sg, sg+BN, sg+2BN, …` in identical order and apply the identical rescale/accumulate
sequence; only the number of key positions consumed per trip of the `for` changes.
Summation order is therefore invariant. This is not merely an argument: §4.1 already
measured it, and T1's `golden_hash` came back **identical to T0's**, so the complete
T0→T1 `Sources/` change — this hunk included — is token-identical on the local golden
set.

**Why it is worth holding.** It is a strictly smaller edit than the T1 replay (two
hunk sites in one kernel, a net *deletion*, so it cannot consume byte headroom), it
inherits an already-measured positive contrast rather than a sibling's unreplicated
claim, and it is in a different kernel family from §5.3's packing flip, so the two
could in principle compose.

**Why it is not the primary.** The +0.3791 % it inherits is the effect of the *whole*
T1 `Sources/` diff, not of this hunk alone; attributing all of it here would be exactly
the error §4.6 accused the r99 result of. `T0U` therefore needs its own paired ABBA and
must clear the bar on its own numbers. It is queued **only** if §5.3 returns `N-PACK`,
and it is measured, never assumed.

**Materialised 2026-08-10T13:41Z** (while the §5.3 extension runs, so the arm is ready
the moment the verdict lands). `research/r106j/scripts/make_t0u_patch.py` reads both
blobs from git objects, keeps only the two hunks anchored at old lines 1636 and 1740,
replays their bodies onto the base with a per-line context assertion, and emits a
standalone patch. Round-tripped independently: `git show 446fe987:<TARGET>` into a scratch
directory, `patch -p1`, re-hash.

| artifact | value |
|---|---|
| `research/r106j/t0u_unroll_depth.patch` | 5,424 B, sha256 `6a714fdc5dfb6578137a86973e42c00d18f9e9d20847e1f9c61242e843bec670`, 2 hunks |
| `T0U` `LagunaRuntimeModel.swift` | sha256 `ebebe3faad9f232f4bb94a62719a80f4cc7d10d47cff8aee09acce0036d57735`, **380,159 B** |
| vs `T0` (384,245 B) | **−4,086 B** — a net deletion, so Rule 75 headroom is *increased*, not spent |

That sha256 is the arm guard `abba_arms.sh` will check before every `T0U` run, on the
same footing as the `T0`/`T1`/`T0P` guards.

**One sharpening of the hypothesis, recorded now rather than after the numbers.** §4.6
found the T0→T1 `Sources/` contrast is not a single mechanism: besides this unroll
spelling it also widens the router-prefetch valid set from `[0,1,5]` to `[0,1,2,3,4,5]`.
#597 rev5 has since made the router-prefetch axis terminal-negative (§5.4.2). If that
component is a drag inside T1, then `T0U` alone is not bounded above by T1's +0.3791 % —
isolating the helper from the hindrance is precisely why a decomposition is worth
running. That is a hypothesis, not a claim, and the sweep is what decides it.

### 5.4 Candidates that did not arrive

Rule 79 says the null cell gets reported, so: at my Stage-2 freeze check, **three of the
five sibling channels had produced no integrable artefact**. #642 (tanjiro, decode fused
attention, the largest single pot on the slate at 6.46 % of `cs`), #616 (nezuko, 0.3204 %
of `cs`) and #629 (edward, Stage A) were all still open with no handoff payload. #597
(frieren) is not an integration input at all — frieren is the channel owner and I consume
his margin-certificate script rather than his patch.

This is not a complaint about the siblings; the slate was issued at ~11:50Z and their
handoffs are due ~06:00Z, seventeen hours later. It is a statement about **what the
integrated tree could possibly contain at this timestamp**, which is the thing a reader
of this report needs in order to interpret §6. If later handoffs arrive before my
07:00Z freeze I extend §5 and re-measure the composed tree; I do not sum deltas.

#### 5.4.1 The largest pot on the slate closed at zero bytes

At 12:57:27Z tanjiro published a `succeeded` result on #642 with verdict
**`N-ISSUE-BOUND`** and a **zero-byte submitted diff** (`git diff --numstat` against base
over `Sources/`, `Vendor/`, `benchmark.json` = 0 lines). That retires the single largest
line item on the slate — 424.35 µs/step ≡ **6.46 % of `cs`** of decode fused-attention
time — as *not slack*. The load-bearing datum is an instruction dose-response measured
through a cache-defeated A/B probe that extracts the exact `source:`/`header:` literals
out of `LagunaRuntimeModel.swift`, so both arms compile the MSL the ranked path
compiles: 0.008255 µs per fma-per-thread on the sliding kernel, which is **97.7 % of the
host's peak issue rate**, with a byte term contributing only 41.8 % of the 18.82 µs
`N=512` dispatch.

For me as integrator the consequence is arithmetic, not rhetorical. Of the 6.46 % pot,
tanjiro's own pricing leaves P2 at 0.063 % of `cs` at *full critical-path weight*
(0.006 % throughput-weighted) and P3 at 0.036 %. Both are 6×–60× under the 0.4 % bar,
so there is no tree in which they are worth the build. **My integration queue lost its
biggest nominal contributor and gained a certainty**: whatever tree I hand over will not
contain a decode-attention change, and nobody should spend the endgame looking for one.

I record one caveat against over-reading it. The dose-response and the threadgroup
ladder are M4 Pro numbers, and issue-boundedness is an occupancy-relative property: the
M5 Max has roughly twice the cores at similar clock, so the same kernel at the same
dispatch geometry sits at a different point on the issue/DRAM balance. Tanjiro's
conclusion is safe *for what it forbids* (do not expect hoists to pay here) and weaker
*for what it asserts about M5*. It does not change my disposition either way, because in
both readings there is no patch.

#### 5.4.2 The pf0 default flip is a standing arm I have deliberately not measured

frieren's #597 carries the one item on the board whose *nominal* value exceeds the
packing patch: flipping `DARKBLOOM_ROUTER_WEIGHT_PREFETCH`'s default from `1` to `0` at
`LagunaRuntimeModel.swift:696-704`, priced from his own merged #571 B→C leg at
**+34.58 µs/step = +0.53 % of `cs`** on M4 with 7/7 cycles and 21/21 reps. It is a
one-line, bit-exact change and it is independent of the packing patch — different
kernel family (fused residual+RMSNorm+router GEMV vs the routed QKV lane-major QMV),
different dispatch, no shared state.

I am not measuring it, and the reason is a scope rule rather than a technical one: the
advisor's slate makes frieren the sole owner of that adjudication, and the composition
rule is *nobody composes before both sides terminate*. #597 has no result marker. If it
terminates `V-CONFIRM` before my 07:00Z freeze, the composed arm `T0 + packing + pf0` is
pre-specified here and I run it as a fresh paired ABBA against the then-current tree —
**composed, never summed**, because two independent-looking levers in the same decode
step share the same command stream and the same memory system, and this campaign has
already been burned once by adding µs across arms.

I flag one integration risk in advance. #597's own §1 shows two instruments that
disagree by 41 µs/step *with opposite signs* on this exact lever, and the per-kernel
instrument says pf1 is **faster**. A tree-level ABBA of my own would not resolve that;
it would just add a sixth row to a five-row contradiction table. That is the second
reason I am content to wait for the owner's verdict rather than produce a duplicate.

**RESOLVED 2026-08-10T13:30Z — the precondition did not fire, so pf0 is not integrated.**
I re-polled #597 and it has now terminated. Head `95a0ef9eb148a6d5c707811cd4e84498b39577ba`,
revision `r105-b-rev5`, marker status **`failed`**, primary metric
`wide_codes_score_delta_pct_of_cs = −0.5363`, verdict **NO SHIP** with outcome cells
`N-CORRECT` and `N-NULL` both firing on the `DARKBLOOM_QMV_WIDE_CODES` lever. Two lines of
that result bind me directly:

- **"Rule 75: nothing owed. No tree is handed on, the flag stays false at
  `LagunaRuntimeModel.swift:323-324`."** frieren hands the integrator zero bytes. Combined
  with #642's zero-byte closure (§5.4.1) and C2a's inertness (§5.2), the packing patch of
  §5.3 is now the *only* live candidate on the entire slate.
- The router-prefetch lever was never the rev5 charge. The advisor's rev5 assignment §8
  states it explicitly: *"rev4's Phase A (A0/A1/M2, pf0/pf1/pf5) stays **suspended, not
  withdrawn**; your §8 already made the router-prefetch verdict terminal-negative and I am
  not asking you to revisit it."*

So the arm I pre-specified above is decided by its own stated condition. I required
`V-CONFIRM` from #597 before composing `T0 + packing + pf0`. #597 terminated `failed`, on a
different lever, with the pf0 lever standing as *suspended and terminal-negative* by both
its owner's §8 and the advisor's ruling. **`V-CONFIRM` did not fire ⇒ pf0 does not enter my
tree.** I am recording this rather than quietly dropping it, because the honest summary is
uncomfortable: rev4's own A1 leg measured pooled(P1,P1B) − P0 = **+28.00 µs/step
[+22.23, +33.77] = +0.426 % of `cs`**, bit-exact across 144 slots (one distinct token
sha256), and that number would clear the advisor's +0.40 % ship bar on its own.

I am still not taking it, for three reasons I want on the record so a future round can
reopen it deliberately rather than by accident:

1. **It is not mine to adjudicate.** The owner's §8 called it terminal-negative and the
   advisor affirmed that in writing. An integrator who overrides a terminal verdict from
   the lever's owner on the strength of a leg the owner themselves de-rated is not
   integrating, they are re-litigating — at T−17 h, with one draw left in the campaign.
2. **The contradiction in §1 above is unresolved, not resolved.** Five rows, two
   instruments, 41 µs/step apart with opposite signs. `+0.426 %` is one reading of that
   table, not its conclusion.
3. **Composition risk is asymmetric here.** Adding an unadjudicated second lever to the
   one candidate that does have a clean bit-exactness argument puts the *whole* payload
   behind the weaker of the two claims, and there is no second draw to recover from that.

If a future round wants it, the cheapest correct next step is stated in rev4's own
summary: it is a one-line source default flip, bit-exact, and it needs one paired
tree-level ABBA composed against the then-current tree — not a re-run of Phase A.

### 5.5 The byte budget of the integrated tree, and a headroom discrepancy I resolved

Two independent tools agree on the state of the editable surface at the advisor tip:

| tool | current | cap | headroom | growth | files |
| --- | --- | --- | --- | --- | --- |
| my `research/r106j/scripts/surface_census.py` | 2,680,208 B (base `446fe987`, pre-`C2a`) | 3,000,000 | 319,792 B | — | 142 |
| alphonse's `senpai/check-editable-budget.sh` (§11.1) | **2,681,206 B** (tip `2454cc01`) | 3,000,000 | **318,794 B** | 998 / 262,144 | **142** |

The two differ by exactly 998 B, which is `C2a`'s committed growth — i.e. they agree.

**The discrepancy, and what it actually was.** The slate text in
`research/CURRENT_RESEARCH_STATE.md` states that *"the file is 384,245 B with 140,043 B
of headroom, and the whole editable surface has 188,987 B against `bd33883e`"*. The
first half matches my base; the second is 129,807 B tighter than either tool reports,
so one sentence appeared to carry two incompatible budgets. It does not — it carries
**two different revisions**, and running my census at each one closes it exactly:

```text
$ python3 research/r106j/scripts/surface_census.py bd33883e…
base_surface_files   142
base_surface_bytes   2811013          # 3,000,000 − 2,811,013 = 188,987 B headroom
  MOD  …  384245  (was 515050, -130805)  Sources/MLXFastModel/LagunaRuntimeModel.swift

$ python3 research/r106j/scripts/surface_census.py 446fe987…
base_surface_bytes   2680208          # 319,792 B headroom
```

The advisor's **188,987 B is exactly right against `bd33883e`**, and the **384,245 B /
140,043 B file figure is exactly right against `446fe987`**; the two halves are simply
measured at different revisions. The whole 130,805 B gap is one commit, `54d0cfb1`
*"r103-C rung 1-2: relocate 134,991 B of comment prose out of `LagunaRuntimeModel.swift`"*
— comment prose deleted from the surface, not code, and not moved into another editable
file (the surface total falls by the same 130,805 B).

Two consequences worth recording:

- **Nothing is wrong with either number, and no advisor retraction is needed.** The
  binding budget for this round is the one against my required base: **318,794 B of
  surface headroom and 140,043 B of file headroom**, with `C2a` already counted.
- `bd33883e` and `446fe987` are **not ancestors of each other in either direction**, and
  at `bd33883e` the scored file sat 515,050 B against the 524,288 B per-file cap — only
  **9,238 B** clear. Anyone reasoning from a `bd33883e`-era byte statement is reasoning
  from a tree where a 10 KB patch was impossible. That is no longer the constraint.

**Since neither revision is an ancestor of the other, I checked that my base is not
behind the promoted frontier.** Running the §4.6 multiset differ across the two trees
(`TCD_A=bd33883e TCD_B=446fe987 tree_content_diff.py 12 Sources/MLXFastModel`) gives
12 lines present only in `bd33883e` and 86 only in `446fe987` out of ~12.3 k
non-comment lines. Reading all 98: the 12 are re-indentation fallout from the comment
relocation, and the 86 are one coherent addition — `lagunaRouterWeightPrefetch`
(`DARKBLOOM_ROUTER_WEIGHT_PREFETCH`, valid set `[0,1,5]`, default 1),
`lagunaRouterPrefetchGroups`, and the `prefetchEarly`/`prefetchLate` hoist threaded
through `lagunaResidualRMSNormRouterSource`, i.e. commit `d38b17bb` *"R100-C: restore
DARKBLOOM_ROUTER_WEIGHT_PREFETCH router GEMV load hoist"*. `ResidualRMSNormRouter`
occurs 10× in both trees, so nothing was dropped.

**`446fe987` is `bd33883e` plus the r100-C router prefetch restore, minus 134,991 B of
comment prose. It is strictly forward of the promoted frontier**, which is the property
frieren needs before submitting anything built on it.

**Per-file cap.** `Sources/MLXFastModel/LagunaRuntimeModel.swift` is the binding file:
384,245 B under T0 against the 524,288 B per-file cap, i.e. 140,043 B of file headroom.
The packing patch grows it by 29 B (384,245 → 384,274). T1 would have consumed 18,664 B
of that headroom for no measured decode benefit, which is a second, independent reason
§4.6 lands where it does.

---

## 6. Stage 3 — the handoff to frieren

frieren's acceptance bar, restated so it can be checked rather than remembered: a locally
measured paired win on the **integrated tree versus HEAD, composed rather than summed**,
with a CI excluding zero and a gain of **≥ 0.4 % of `cs`**; green correctness on the exact
submitted tree; a margin certificate for any non-bit-exact component; and the four
`senpai/submit-official.sh` preconditions checked by me on that exact HEAD. §6.1–§6.6 are
those six items in one place. I hold **zero receipts** and I never invoke
`senpai/submit-official.sh` myself; this section is evidence, not a submission.

### 6.1 Item 1 — paired A/B for the integrated tree versus HEAD

_Filled once §5.3 and, if it runs, §5.3.5 are terminal._

### 6.2 Item 2 — conversion to % of `cs`, and the 0.4 % test

_Filled with §6.1._

### 6.3 Item 3 — correctness on the exact HEAD

_Filled with §6.1._

### 6.4 Item 4 — margin certificate: **N/A, and here is why that is a claim and not an omission**

Every component that could enter my candidate tree is **bit-exact**, so there is no
numerical margin to certify:

| component | bit-exactness basis | empirical confirmation |
|---|---|---|
| `T0` itself | it *is* HEAD; the identity | Stage 0 golden `b9509697c08a2cf3…`, `max_abs_diff 0` (§2.5) |
| `C2a` (alphonse) | default-inert; dead code on GPU gen 16 | carried, never enabled (§5.2) |
| `T0P` (packing flip) | lane-major addressing; `num_simdgroups` re-labels `out_row → (tile, simd_gid)` only; no cross-lane reduction; `rows % 8` guard unreachable (§5.3.1) | 16/16 runs, **one** `golden_hash`, `max_abs_diff 0` (§5.3.4) |
| `T0U` (unroll depth) | online-softmax state accumulates into the *same* registers in program order; identical key-visit order (§5.3.5) | T1's `golden_hash` identical to T0's across 24 runs (§4.1, §4.3) |

A margin certificate answers "how far is this from flipping a token?" for a change that
*perturbs arithmetic*. None of the above perturbs arithmetic: they change which thread
computes a row, or how many rows are consumed per trip of a loop. The correct answer is
therefore not a large safety factor, it is **zero perturbation**, and the evidence for it
is a token-identical golden hash on every run of every arm rather than a distance.

**Prior art, and where it is not.** frieren shipped a reusable margin-certificate script
and exercised it on #597 rev5 (verdict MARGINAL, safety factor 1.37×). Two facts belong
in the handoff so nobody wastes time looking: **(a)** its path is not published anywhere
in the #597 thread, and **(b)** it does not exist at my base `446fe987`. So if a future
round hands over a non-bit-exact component, that tool has to be located or rewritten
first. I did not need it and did not reimplement it.

### 6.5 Item 5 — the four `submit-official.sh` preconditions

_Re-run on the final HEAD and pasted here; the generator is
`research/r106j/scripts/handoff_certificate.sh`, which also emits the exact command
frieren runs._

### 6.6 Item 6 — Rule 75 surface census

_Re-run on the final HEAD; generator `research/r106j/scripts/surface_census.py`._

### 6.7 Deviations, caveats and known-imperfect instruments — disclosed, not buried

1. **The nax wall (Rule 99) bounds what any prefill number here means.** This host is an
   M4 Pro reporting Apple GPU generation 16; `device.cpp:1083-1101` requires generation
   ≥ 17 to select the `_nax` prefill kernels the ranked M5 uses, and that file is not on
   the editable surface. §1 measured the consequence directly: my decode ln-ratio
   reproduced M5's to **+0.15 %**, my prefill ln-ratio missed M5's by **−43.5 %**. Every
   prefill cell in this document is therefore tagged **[M4-WALL]** and I quote the
   *conservative* score row — prefill charged as neutral — wherever a decision depends on
   it.
2. **My T1 is a partial Rule 95.6 replay.** I granted two `Sources/` trees, not the whole
   surface, so the full-surface numstat gate does not pass by construction. The substitute
   I ran and recorded in §2.3 is the grants-only numstat gate plus a comment-only Vendor
   certificate (`CMLX-NONCOMMENT-IDENTICAL`, `SWIFTLM-NONCOMMENT-IDENTICAL`, and a
   byte-identical `mlx.metallib`). This is a real deviation from the letter of 95.6 and I
   am flagging it rather than letting the reader infer a full replay.
3. **`run_upstream_equivalence.sh` exits 1 on the unmodified base.** Prefill
   `maximumAbsoluteLogitError` is 0.125 on **T0 itself** (§2.6). Rule 83 prior art in six
   documents, and #597 rev5 §3.2.1 independently re-confirms it on the unchanged base. The
   oracle is therefore usable here **only as a differential**: I compare candidate against
   base and require the digits to match, which §4.2 did (md5 `740d5ab196ecaa4f…`,
   identical). `MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT` was **never** set at any point in this
   round.
4. **The release build is not byte-reproducible on this host.** Across eight runs of a
   single arm the worker binary shows six distinct sha256 prefixes. Combined with the §4.4
   slot artefact — a same-arm consecutive run skips the recompile and therefore skips
   ≈40 s of incidental cooldown — this is the dominant nuisance term in every sweep here.
   The palindrome `ABBA`/`BAAB` phase alternation is what cancels it, which is why every
   block count I report is **even** and why §5.3.4's prefill null cell is read as
   instrument noise rather than signal.
5. **`analyze_abba.py`'s block contrast is a difference of arm means inside a block**, so
   it is phase-agnostic by construction and `ABBA` and `BAAB` blocks are pooled without a
   sign fix. Stated because it is the one place where a reader could reasonably suspect an
   ordering bug.

### 6.8 Follow-ups I did not implement

Ranked by what I would hand the next round first. Reachability tags follow §1:
**[STRUCT]** structural/desk, **[M4-WALL]** not measurable here, **[PROJ]** projected,
**[M5-RCPT]** needs a ranked receipt.

1. **[STRUCT] The prefill MMA-occupancy deficit** — §6.9. Unowned, and larger than
   anything in this queue.
2. **[M5-RCPT] `T0P` on the ranked host.** My verdict is `N-PACK` *on M4 Pro*, and the
   campaign's own doctrine is that threadgroup geometry can change sign across core
   counts — which cuts both ways. The decisive experiment is one paired M5 measurement,
   and it costs 29 B. It is not worth a scarce draw at a corrected prior of +0.338 %
   (§5.3.4), but it is exactly the kind of item that should ride along free if a future
   round ever gets a cheap ranked A/B channel.
3. **[STRUCT] Decompose the rest of the T0↔T1 contrast.** §4.6 identified at least two
   mechanisms inside a **+0.3791 %** whole-tree effect: the unroll spelling (isolated as
   `T0U`, §5.3.5) and the router-prefetch valid set. If `T0U` under-explains the total,
   the residual is worth naming — an unattributed +0.38 % is a lead, not a nuisance.
4. **[M4-WALL] Unroll depth as an axis, not a binary.** T0 is 4-deep, T1 is 2-deep, and
   nobody has tried 1, 3, 6 or 8. It is bit-exact by the same argument, it is a net
   deletion at every depth ≤ 4, and #308's own lesson was that the argmax of a geometry
   curve is **interior** and monotonicity is refuted. A depth curve is the natural sequel
   and it needs an M5 to be worth believing.
5. **[STRUCT] The corpus carries a mis-scaled constant.** §5.3.4 shows `% of cs` was
   computed at least four times by multiplying an **M4** absolute µs/step delta by an
   **M5**-derived `%`-per-µs constant, inflating by the M4:M5 per-step ratio ≈1.67×.
   Anything in the archive quoted as "µs/step ⇒ % of score" from a non-M5 session should
   be re-derived in relative units before it is used to prioritise work. This is cheap,
   mechanical, and changes the queue order.
6. **[PROJ] The two-pool model's residual is the largest unexplored block on decode.**
   Roughly 740 µs/step of M5 decode is unattributed (model residual ≈ −6.63 %, unaudited
   tail, and a wall-minus-busy gap). Nobody has a named mechanism for it and Rule 92's DAG
   audit caps *scheduling* recovery at ≈0.02 %, so the recoverable part is either small or
   it is somewhere the current instruments cannot see. Worth one round of instrument work,
   not one round of patches.

### 6.9 The one thing I would hand over above every patch in this queue

alphonse's #636 produced a `[STRUCT]` observation that no one owns and that I am
propagating verbatim because it outlives this round: on the **largest prefill kernel
family**, with `BM = 64` and `WM = 4`, only **one of the four simdgroups in each
threadgroup issues MMA**. Three quarters of the matrix-unit issue capacity in that
threadgroup is idle, and the deficit is **invariant under `bn`** — so it is not a tuning
constant anyone can sweep away, it is a tiling decision.

Why this matters more than the queue it sits behind: every candidate on the Stage-2 slate
was priced in tenths of a percent (§5.3.4's corrected +0.338 %, #642's 0.063 % and
0.036 %, the routed staging null at −0.038 %), against a gap to the record of **1.2846 %
of `cs`**. A ~4× occupancy deficit on the largest prefill family is a different order of
quantity. It is also **unreachable from this desk** — prefill on generation-16 hardware
does not select the `_nax` family at all (§6.7 item 1) — which is precisely why it has
survived unowned: the people who can measure it were not looking, and the people looking
cannot measure it.

I am not claiming a number for it. I am claiming that "1 of 4 simdgroups issues MMA" is a
statement about the ranked host that can be checked from the source without any GPU at
all, and that if it is true, it dominates everything else written in this document.

