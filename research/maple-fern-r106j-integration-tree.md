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

Design: 3 ABBA blocks, 12 runs, `research/r106j/scripts/abba_t0_t1.sh 3 T1`,
launched 2026-08-10T11:12:24Z, 2,229 s wall. Blocks alternate `T0 T1 T1 T0` and
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

**Correctness across all 12 runs: 0 failures, `max_abs_diff` 0 everywhere, and exactly
one distinct `golden_hash` (`b9509697c08a2cf3`) across both arms.**

Within-arm dispersion, n = 6 per arm:

| arm | decode mean s/tok | decode CV | prefill mean s/tok | prefill CV |
|---|---|---|---|---|
| T0 | 0.012973630 | 0.4472 % | 0.001118728 | 0.7354 % |
| T1 | 0.012933703 | 0.2349 % | 0.001112900 | 0.4538 % |

Block contrasts, T1 minus T0, natural log, n = 3 blocks, dof = 2, t(0.975) = 4.303:

| quantity | estimate | CI95 | block sd | blocks favouring T1 |
|---|---|---|---|---|
| d(ln decode) | −0.3076 % | [−0.4942, −0.1210] | 0.0751 % | 3/3 |
| d(ln prefill) | −0.5209 % | [−1.2662, +0.2243] | 0.3000 % | 3/3 |
| **d(ln score)** | **+0.3610 %** | **[+0.2792, +0.4428]** | **0.0329 %** | **3/3** |

Per-block `d(ln score)`: +0.3489 %, +0.3982 %, +0.3358 %.

**V-T1 fires.** The CI95 on the primary metric excludes zero on the favourable side,
every block agrees in sign, and the registered −0.40 % inferiority margin is cleared
with room to spare. Raw rows: `research/artifacts/maple-fern-r106j/abba/runs.tsv`;
per-run logs and score JSON: `abba/run<idx>.<arm>.{log,json}`.

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
| freshly recompiled | 9 | −0.0973 % | −0.1350 % |
| **reused previous build** | 3 | **+0.2897 %** | **+0.3987 %** |

The reuse slot is always position 3 of a block. Over 3 blocks it was held by **T1
twice and T0 once**, so the artefact is *not* balanced and it penalises T1:

```
bias on d(ln score) = -0.75*(p_dec/2)*(2-1)/3 - 0.25*(p_pre/2)*(2-1)/3
                    = -0.75*(0.387/6) - 0.25*(0.534/6)  =  -0.071 %
```

The per-block pattern is exactly what that model predicts: block 2 is the one block
whose reuse slot was held by **T0**, and it is the largest at +0.3982 % against
+0.3489 % and +0.3358 % for the two T1-slot blocks.

So **the headline +0.3610 % understates T1 by roughly 0.07 %**; the artefact-corrected
point estimate is ≈ **+0.43 %**. I am *not* promoting the corrected figure — it is a
model-based adjustment on n = 3. The experimental fix is to run an even number of
blocks, which hands the slot to each arm three times and cancels the bias exactly.
Blocks 4–6 are running for that reason, and `abba_t0_t1.sh` now continues the block
phase across invocations instead of restarting it (which would have made the
imbalance *worse*, 4:2, rather than curing it).

### 4.5 What this measurement is, and what it is not

- It **is** a paired, blocked, drift-cancelled, correctness-gated M4 wall-clock result
  on a dimensionless log-ratio of the exact scored quantity.
- It is **not** an M5 result. M4 Pro reports Apple GPU generation 16 and cannot select
  the `_nax` prefill kernels the ranked M5 uses. The T0→T1 delta is entirely Swift-level
  (§2.3 proves the Metal side is untouched, and the byte-identical metallib of §4.1
  confirms it), so the kernel-family reachability objection does not apply to the
  *mechanism*; the campaign's recorded M4→M5 discount menu (×1.000 / ×0.622 / ×0.505 /
  ×0.436) still applies to the *magnitude*. At ×0.505 the +0.36 % becomes +0.18 %.
- It is corroborated, independently and on the ranked channel, by the fact that the
  `Sources/` tree it replays produced the campaign's **best-ever official receipt**
  (`cs` 2.590559) against the merged frontier's 2.582286 — a gap of +0.32 %, the same
  sign and very nearly the same size as the M4 paired estimate.

