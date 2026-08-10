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

