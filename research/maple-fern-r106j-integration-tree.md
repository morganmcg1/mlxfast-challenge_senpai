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
| **V-INTEGRATED** | one or more student patches land, verified, with a measured cumulative delta | **no — resolved `N-INTEGRATED`, see below** |
| **N-PACK** | the packing-default flip (L3, candidate B) fails its preregistered 8-block checkpoint | **YES** — §5.3.6a |
| **N-UNROLL-PREEMPTED** | the unroll-depth isolation (T0U) is cancelled before it runs | **YES** — §5.3.5b |

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

**Resolution of `V-INTEGRATED` — the deliverable this assignment actually exists for.**

`V-INTEGRATED` **did not fire**. The integrated tree I hand frieren is, on the scored
surface, **byte-identical to the advisor tip `a30fa5f8`**:

```
git diff --numstat a30fa5f8 HEAD -- Sources/ Vendor/ benchmark.json Package.swift senpai/
   (empty)
```

Not one candidate on the Stage-2 slate cleared the **0.4 % of `cs`** promotion bar, so
by §5.0's own acceptance rule not one of them was allowed to land. In descending order
of what each was actually worth after pricing (§6.2):

| candidate | owner | disposition | measured / re-priced value |
|---|---|---|---|
| **A** — `C2a` gather-GEMM `bn` 64→32 | alphonse (#630/#636) | **carried, inert by default** (+998 B already in the advisor base) | 0.195 % of `cs`, Rule 103 — under bar, shelved upstream |
| **B** — L3 packing-default flip (`num_simdgroups 2→8`) | mine (T0P) | **`N-PACK`**, not landed (+29 B) | **d(ln score) +0.0328 %, CI95 [−0.2338, +0.2994]** over 10 blocks — bar excluded at 95 % |
| **C** — unroll-depth isolation | mine (T0U) | **`N-UNROLL-PREEMPTED`**, cancelled before it ran (−4,086 B) | would have byte-reverted #539's merged win, ≈ −0.130 % |
| decode fused-attention pool | tanjiro (#642) | **`N-ISSUE-BOUND`** at zero bytes | Rule 100 — pool is 97.7 % ISSUE-bound; §B.0.3 rows 5/13 are measured fiction |
| routed staging / floors | #643 | **`N-FLOOR` / `N-REACH`** | −0.038 % and unreachable |
| r106f′ | — | **`V-UNTOUCHED`** | never arrived (§5.4) |
| pf0 (B→C router prefetch) | frieren (#571) | **not mine to land**; re-priced for her | **+0.2301 % (α) / +0.2633 % (β)**, down from the quoted 0.53 % — under bar solo (§5.3.6c) |

So the answer to "what is the cumulative measured delta of the integrated tree?" is
**exactly 0 % of `cs`, by construction, and this is the correct answer rather than a
missing one** (§6.1, §6.2). The tree is build-verified from a forced-clean rebuild
(§6.1) and correctness-green on the exact HEAD (§6.3).

This is the outcome rev2 explicitly named as acceptable: *if nothing clears the bar we
take no draw.* It is also exactly what **Rule 101.2** independently concluded from
frieren's own resubmission variance — *"Hold our tree."* Two instruments that share no
inputs reached the same instruction, which is the strongest form of agreement available
here.

**Two findings in this document outrank its verdict**, and are flagged here so a reader
who stops at §0 still gets them:

- **§6.3.1 — instrument retraction.** `max_abs_diff` is **hard-coded to `0`** at all
  five emission sites; **no code path computes it**. `golden_hash` is `golden.sha256`,
  the hash of the golden *fixture file* — an **input**, not a function of the emitted
  token stream. My §4.1 claim that a shared `golden_hash` demonstrates token-identical
  output is **retracted in place**. The load-bearing correctness evidence is
  `passed`, `passed_correctness`, `checked_steps`, `case_count`, `first_failing_case`,
  `first_failing_step`, `error` — all of which I re-audited across all 43 runs (§6.3).
  No verdict in this document moves, because none of them rested on the retracted
  fields alone; but anything downstream that cited them must be re-read.
- **§5.3.6a/§5.3.6c — L3 does not replicate, and this is the hinge result three other
  arms are waiting on.** My candidate B *is* the `num_simdgroups 2→8` packing default
  flip — the same contrast edward's #629 Stage A was assigned, measured here as one
  pre-specified paired contrast (no argmax, so no selection bias to remove). Ten
  palindromic blocks, 42 complete runs: **d(ln score) = +0.0328 %, CI95
  [−0.2338, +0.2994]**; decode alone **−0.0686 %, CI95 [−0.3921, +0.2550]**. The
  estimate shrank monotonically as blocks accumulated (+0.1889 at 4 → +0.0920 at 8 →
  +0.0328 at 10). The interval **excludes the 0.4 % bar** and **excludes #308's
  as-reported relative-decode effect of 0.4502 %**; it barely contains the Rule 105.10
  de-biased 0.3611 %. In the advisor's own words on #629 this is the committed negative
  — *"L3 does not replicate; the contrast is 5 ± 20 µs/step M4"* — that lets the
  conditional framing of alphonse's T3b, frieren's T2d/T1a and the whole
  "can a sum reach 0.4 %" question be stood down. **It is not a failure to build or a
  failure to measure; it is a measured null on the campaign's largest ready-made item.**
- **§5.3.6c — Rule 105 supersession, applied to my own numbers first.** My §5.3.4
  "1.67× deflation" is superseded by the campaign's **2.29× (bytes) / 2.00× (latency)**
  over-credit factor, and Rule 105.10's winner's-curse de-bias removes a further 19.9 %.
  The published L3 figure of **0.562 %** is really **0.1966 %**, the product of three
  compounding errors. The consequence for the only paper route to the bar
  (`L3 + pf0`) is spelled out in §5.3.6c: **0.1966 + 0.2301 = 0.4267 %** on paper, but
  substituting my *measured* L3 gives **0.0328 + 0.2301 = 0.2629 %** — the stack does
  not reach the bar, and **the failure is L3, not pf0**.

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

> ⚠️ **RETRACTED, 2026-08-10T15:5xZ.** This paragraph originally read: "`golden_hash`
> is a function of the emitted token stream; it is unchanged, so every checked greedy
> token is identical." **That is false.** `golden_hash` is `golden.sha256`
> (`Sources/MLXFastTrustedHarness/LagunaRuntimeCorrectness.swift:127` and passim) — the
> sha256 of the golden *fixture file*, an **input**. It is constant by construction and
> carries no output information. The correct reading of this row, and the correct
> statement of the correctness evidence that replaces it, is in **§6.3.1**. The
> conclusion of §4.1 does not change — the token-identity claim is *better* supported by
> the fields I should have quoted — but the instrument I named was the wrong one.

`harness_hash` is a function of the submitted surface; it moved, so the harness did
observe a different tree and this is not a stale-artefact reading. `golden_hash` being
equal across the arms is a genuine control, but it is a control on the *fixture*: it
proves both arms were graded against the same reference, not that they produced the same
answer. What proves the latter is `passed_correctness == true` with `checked_steps == 130`
and `first_failing_step == null` in both arms (§6.3.1).

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

**Re-verified at 2026-08-10T14:05Z against the *current* advisor tip
`1decfba9410b3b873609feb7bcbabf299d3a700a`** (the branch has since moved
`2454cc01 → … → 1decfba9`, adding eight further commits). The compiled-surface delta from
my required base is **still exactly this one hunk and nothing else**:

```text
$ git diff --name-only 446fe987 1decfba9 | wc -l          # 91 paths
$ git diff --numstat  446fe987 1decfba9 -- Sources Vendor benchmark.json Package.swift Package.resolved
25	0	Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp
```

The other 90 changed paths are all under `research/`. `benchmark.json` is byte-identical,
so `harnessHash()` and the 97-entry `editablePaths` whitelist are unchanged.

⚠️ **A correction to the base notices, offered as a caution rather than a complaint.**
Four separate advisor comments on sibling PRs (#616 `5239585180`, #629 `5239585381`, and
two earlier) state that everything after `446fe987` is "docs-and-`research/`-only" and that
"no compiled path changed". That is **not accurate**: `quantized.cpp` is a compiled
translation unit *and* entry 1 of 3 `quantized.cpp` entries on the `editablePaths`
whitelist. Any sibling who took "no compiled path changed" literally and skipped a rebuild
after rebasing would be timing a stale binary. The conclusion the notices reach is right —
nothing *behavioural* changed — but it is right for a reason nobody had checked, which I
check next.

**Proof that the hunk is an identity at default env, on M5 as well as on M4.** §5.2's
first draft rested on "default `64`, which is the pre-existing value". That is a claim
about `darkbloom_expert_down_bn()`; it is *not* by itself a proof that the assignment
`bn = darkbloom_expert_down_bn()` is a no-op, because `bn` could have been re-written
between its initialisation and the guard. I read the intervening code at the tip:

```cpp
int bm = 64, bn = 64, bk = 64;
int wm = 2, wn = 2;
const int bm128 = darkbloom_stage_bm128_variant();
switch (bm128) {
  case 1: bm = 128; wm = 4; break;
  case 2: bm = 128; wm = 2; break;
  case 3: bm = 128; wm = 8; break;
  case 4: bm = 64;  wm = 4; break;
  case 5: bm = 64;  wm = 4; wn = 1; break;
  default: break;
}
if (… && bm == 64 && wm == 4 && (wn == 2 || wn == 1)) { bn = darkbloom_expert_down_bn(); }
```

**No arm of the `bm128` switch writes `bn`.** `bn` is therefore provably `64` at the
guard on every path, and with `DARKBLOOM_EXPERT_DOWN_BN` unset the assignment stores `64`
over `64`. The hunk is a **semantic identity for the default environment on every host**,
including the ranked M5 where `gather_qmm_rhs_nax` *is* reachable and where I have no way
to measure. This matters more than my host-reachability argument (reason 2 below): that
argument only ever established that the code is *dead on M4*, which says nothing about the
machine the score is set on. The switch-coverage argument closes M5 too, statically, and
it is the reason I am willing to hand frieren a tree containing a `_nax`-path edit I
cannot execute. It also means the change cannot be a *silent* regression on M5 — the only
way to activate it is to export the env var, which the harness does not do.

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

##### 5.3.5a Static trip-count ledger — this is an unusually clean controlled contrast

Everything in this loop is a **compile-time constant** in the kernel source string
(`LagunaRuntimeModel.swift:1516-1525`): `head_dim = 128`, `window = 512`, `BN = 32`,
`BD = 32`, `qk_per_thread = v_per_thread = 4`, and **`N = 512`** — `N` is *not* a
runtime parameter for this kernel, so the trip counts are fully determined statically.
Generator: `research/r106j/scripts/unroll_trip_ledger.py`.

| unroll depth | main-loop iters / simdgroup | **remainder iters** | blocks / simdgroup | union over 32 sg | exact cover |
|---|---:|---:|---:|---:|---|
| 2 (`T0U`, = T1) | 8 | **0** | 16 | 512 | ✅ |
| **4 (`T0`, shipped)** | **4** | **0** | **16** | **512** | ✅ |
| 8 (hypothetical) | 2 | **0** | 16 | 512 | ✅ |

Three things follow, and they matter more than the patch's size:

1. **The remainder loop is dead code at every depth that divides 16.** `N/BN = 16`
   blocks per simdgroup, and 16 is divisible by 2, 4 and 8, so the scalar tail never
   executes. The contrast is therefore *purely* unroll depth — there is no
   "remainder-handling overhead" confound in either direction, which is the usual
   thing that muddies unroll experiments.
2. **Identical work, identical traffic, identical visit order.** Each arm's simdgroup
   touches exactly the same 16 blocks in the same ascending order `sg, sg+32, …, sg+480`,
   and the 32 simdgroups partition all 512 positions with no duplicate and no gap
   (asserted in the generator). This is the *mechanical* reason the edit is bit-exact,
   and it is stronger than the program-order argument above because it is checked
   rather than reasoned.
3. **The only thing that changes is staged register pressure and memory-level
   parallelism.** Per stage the kernel holds `U pipe_k[4]` (4 × 4 B) plus four
   `bfloat` V components, i.e. ~8 live values; so the staged working set is roughly
   16 values at depth 2, **32 at depth 4**, 64 at depth 8, on top of `pair_q0/q1` and
   `pair_o0/o1` (16 more) and the softmax scalars.

Point 3 is why **the direction of this experiment is genuinely open**, and I want that
on the record before the data arrives. The naive prior is "T0's depth 4 was a measured
win (R2), so depth 2 must be worse". But alphonse's #630 established that this decode
kernel family is **issue-bound, not bandwidth-bound** (114.2 GB/s = 42.9 % of M4 Pro
peak). For an issue-bound kernel, extra memory-level parallelism buys little, while
halving the staged register footprint can raise simdgroup occupancy and therefore
latency hiding. So depth 2 trading MLP-4 for roughly half the staged registers is a
plausible *win*, not merely a plausible loss. That is the hypothesis, and it is the
reason this is worth 2.1 h of the endgame rather than being filed as a curiosity.

A note against my own convenience: depth **8** is equally exact by the table above and
is the direction that would compound if more MLP were the lever. I am not building it.
It is ~300 lines of hand-replicated Metal-in-a-Swift-string with a real chance of a
silent transcription error, I could not verify it and T0U in the time left, and the
issue-bound finding argues its prior is the *worse* of the two. Recording it as the
obvious next probe for anyone with more clock than I have.

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

**Preregistered design for the `T0U` sweep (Rule 40 — the DESIGN, not just `n`), written
2026-08-10T14:00Z, before the arm has been built even once.**

| element | value |
|---|---|
| design | paired ABBA/BAAB palindrome blocks, phase continued across invocations, `T0` control vs `T0U` candidate |
| arm guard | `LagunaRuntimeModel.swift` sha256 must equal `ebebe3fa…5735` (`T0U`) / `a736b50f…50c4` (`T0`) before every run, else abort |
| unit of analysis | the **block**, not the run: contrast = (mean of the block's two `T0U` rows) − (mean of its two `T0` rows), in natural log |
| dof | `blocks − 1` |
| planned `n` | **12 blocks = 48 runs** (~2.1 h at ≈160 s/run) |
| primary metric | `d(ln score)` composed from decode and prefill by the official weighting |
| quoted metric | the **conservative** row (prefill charged neutral), per Rule 99's nax wall |
| expected resolution | sd(d ln score)/block ≈ 0.3143 % (§4.4) ⇒ CI half-width ≈ **0.20 %** at n=12 |
| correctness gate | every run must report `passed` with `max_abs_diff == 0` and a single `golden_hash` `b9509697c08a2cf3` across both arms |

Acceptance criteria, all four required for **`V-UNROLL`**:

1. zero correctness failures and exactly one `golden_hash` across all 48 runs;
2. conservative `d(ln score)` CI95 excludes zero on the positive side;
3. conservative `d(ln score)` point estimate ≥ **+0.40 %** of `cs`;
4. `d(ln decode)` positive with a consistent block sign majority (≥ 9/12).

Anything else is **`N-UNROLL`** and the integration tree stays `T0`. Note criterion 3 is
already in tension with the prior: the *whole* T1 diff measured +0.3791 % composite and
its decode component alone was a null in the +0.23 % neighbourhood (§4.5). If `T0U` is a
strict subset of T1 and the router-prefetch component is not a drag, then `T0U` **cannot**
clear +0.40 % and the honest expectation is `N-UNROLL`. I am running it anyway, because
the §5.3.5 hypothesis is precisely that the subset may *exceed* the whole, and because a
measured decode-only number on a bit-exact, byte-negative edit is the one thing a sibling
handoff could later be stacked on top of. **No escape clause this time:** the 12 blocks
run to completion regardless of the interim point estimate, because §5.3's four-block
interim already showed how much a partial sweep can mislead.

##### 5.3.5b ⛔ `T0U` is CANCELLED before a single GPU-second was spent — verdict `N-UNROLL-PREEMPTED`

At 14:12Z, before launching the 12-block sweep preregistered above, I pulled the advisor
tip (`1decfba9` → **`4e9a8e16`**) and read the four new standing rules on it. **Rule 100
closes this axis, and the evidence is overwhelming enough that running the sweep would have
been a waste of 2.1 hours of a shared timing host.** Four independent sufficient reasons,
in ascending order of how badly I should have known better:

**(1) The axis is explicitly banned by name.** Rule 100.8 closes with: *"Do not re-open
prefetch hoisting, **ring depth**, split-K, or wider per-lane loads on this family."* `T0U`
varies the staging depth of the sliding fused-attention main loop. That *is* the ring-depth
axis, on that exact family.

**(2) The mechanism I hypothesised is measured dead.** My §5.3.5 rationale was that halving
the staged registers might raise occupancy and buy latency hiding. Rule 100.1 measures this
pool at **97.7 % of theoretical peak instruction issue** (3.969 × 10¹² fma/s against a
4.04 × 10¹² ceiling), and Rule 100.2's threadgroup ladder confirms there is **no latency
slack** — *"a latency-bound kernel absorbs extra threadgroups for free; this one does
not."* Occupancy buys latency hiding, and there is no latency to hide. **You cannot issue
faster than peak issue.**

**(3) My own trip-count ledger proves `T0U` cannot pay under the measured exchange rate.**
Rule 100.4 prices this kernel at **0.002097 % of `cs` per fma-per-thread removed**, so
clearing the 0.4 % bar requires removing **≈191 fma/thread**. §5.3.5a above establishes, by
static analysis, that `T0U` is *bit-exact with identical work, identical traffic and
identical visit order* — it removes **zero** fma per thread. Worse: dropping the depth from
4 to 2 doubles the main-loop iteration count from 4 to 8, which **adds** loop-control
instructions in a kernel where instructions *are* time. The predicted sign is **negative**.

**(4) 🚨 The decisive one: `T0U` is the byte-exact reversion of a shipped, merged win.**
The state doc's pre-cleared list for this family reads: *"❌ ring depth: shipped by #539
(**+4,086 B**, ≈0.130 % solo)."* My `T0U` patch changes `LagunaRuntimeModel.swift` by
**−4,086 B** (384,245 → 380,159), a figure I had already computed twice — in §2.4 and again
in §6.6.1 — and quoted approvingly as "byte-negative, which is free headroom." It is not
free headroom. **It is #539 run backwards.** The expected effect of `T0U` is not an unknown
worth 2.1 hours of sweep; it is **≈−0.130 %**, the negation of a merged result the campaign
already paid for.

**What went wrong in my process, and the check I am adding.** I built `T0U` by *reading the
kernel source*, noticing a staging constant I could halve, and verifying mechanically that
the change was bit-exact. Every step of that was sound and none of it asked the only
question that mattered: **who put that constant there, and what did it buy?** Rule 100.7 —
written this same day, after the advisor made the structurally identical mistake with the
P1 prefetch hoist — prescribes exactly the missing step: *"grep the numbered standing-rule
block for the MECHANISM WORD, not only the family section and the closed list."* I ran that
grep at 14:12Z for `ring depth`, `unroll`, `packing` and four other mechanism words; it
took under a minute and returned the `#539` line immediately.

There is a second, sharper check I want to record because I have not seen it written down
anywhere and it would have caught this even faster: **a candidate's byte delta is a
fingerprint.** My patch was −4,086 B; the ledger entry was +4,086 B. An exact
magnitude match between a proposed edit and a shipped ledger entry is near-conclusive
evidence that the edit is that entry's inverse. I had both numbers in my own report, in two
different sections, and never put them side by side. **Cross-reference candidate byte
deltas against the shipped-ledger byte deltas before measuring anything.**

**Disposition.** `T0U` is withdrawn, not shelved: the artefacts
(`research/r106j/scripts/t0u_unroll_depth.patch`, sha256 `6a714fdc…c670`, and the
`make_t0u_patch.py` generator) stay on the tree as a *negative* record so that nobody
reconstructs it, and `research/r106j/scripts/abba_arms.next.sh` — which was staged and
verified to add the `T0U` arm — is **not** promoted. §5.3.5a's trip-count ledger survives
on its own merits: it is a clean static proof that the depth-2/4/8 contrast has no
remainder confound, and it is now also the proof that the axis carries no instruction
saving. The 2.1 hours this frees go to final verification of the tree I actually hand over.
The preregistration in §5.3.5 is left standing above, unedited, so the record shows what I
intended to run and why I did not run it.

#### 5.3.6 Result — blocks 5–8, the preregistered checkpoint. Verdict `N-PACK`

Job `0ca1fee0-a277-4ece-9783-f74fc63c21cf`, launched 2026-08-10T13:38Z, appended runs
17–48 to the same `runs.tsv` (Rule 58: extend, never restart). At the moment blocks 5–8
completed, the preregistered eight-block readout is the one §5.3.3 committed me to, so it
is the one that decides the verdict. Verbatim from
`research/artifacts/maple-fern-r106j/abba_t0_t0p/analysis_8blocks.txt`:

```
usable runs: 32   complete ABBA blocks: 8
correctness failures: 0
distinct golden_hash values: 1 -> ['b9509697c08a2cf3']
  within-arm T0  decode mean=0.012965275 s/token  cv=0.3206%  n=16
  within-arm T0P decode mean=0.012945511 s/token  cv=0.3861%  n=16

d(ln decode)   : -0.1528%  CI95 [-0.5469, +0.2414]  sd=0.4714%  3/8 positive
d(ln prefill)  : +0.0904%  CI95 [-0.4536, +0.6343]  sd=0.6506%  6/8 positive
PRIMARY
d(ln score)    : +0.0920%  CI95 [-0.2347, +0.4187]  sd=0.3907%  6/8 positive
CONSERVATIVE (prefill charged neutral)
d(ln score|dec): +0.1146%  CI95 [-0.1811, +0.4102]  sd=0.3536%  5/8 positive

per-block d(ln score) %: +0.3022, -0.3693, -0.6056, +0.4303, +0.1674, +0.0146, +0.3232, +0.4731
```

**Against the four criteria fixed in §5.3.3:**

| # | criterion | result | verdict |
|---|---|---|---|
| 1 | zero correctness failures, exactly one `golden_hash` | 0 failures, 1 hash `b9509697c08a2cf3` over all 32 runs | **PASS** |
| 2 | CI95 on d(ln score) excludes zero | [−0.2347, +0.4187] straddles zero | **FAIL** |
| 3 | point estimate ≥ +0.40 % of `cs` | +0.0920 % | **FAIL** |
| 4 | surface census still passes Rule 75 | +29 B against 140,043 B of headroom; `check-editable-budget.sh` headroom 319,792 B (§6.6.1) | **PASS** |

Two of four fail, so the preregistered revert fires: **the handoff tree is `T0`
unchanged and the verdict is `N-PACK`.** The revert is the absence of a commit —
`RESTORE_ARM=T0` already left the worktree matching HEAD — so there is nothing to undo.

**The null cell, read as §5.3.3 requires.** d(ln prefill) = **+0.0904 %, CI
[−0.4536, +0.6343]**. The patch is a decode-only kernel geometry change and cannot touch
prefill, so this cell is a live estimate of per-block instrument noise, and it is
consistent with zero. That matters more than it looks: at five blocks this same cell read
**+0.4792 %**, which is larger than the effect I was hunting for and would have been a
loud instrument alarm had it persisted. It washed out. **The blocks were not thermally or
otherwise contaminated, and the effect cell's failure to clear the bar is therefore a
statement about the patch, not about the host.** I record the transient because the
honest version of "the null cell held" is "the null cell wandered and then held", and a
reader who only saw the final number would over-trust the instrument.

**Sign consistency.** 6/8 blocks positive on the primary estimator is exactly what an
effect of ≈+0.09 % against a per-block sd of ≈0.39 % should produce; it is not evidence of
a real win. The decode cell — the only cell the patch can physically move — is
**negative** (−0.1528 %, meaning T0P is *slower* on decode), with 3/8 blocks positive.
The primary estimator's positive sign is carried by the prefill term, i.e. by the null
cell, which is the one term the patch provably cannot affect. **On the mechanism's own
channel the patch is, if anything, slightly harmful.**

**Reconciliation with the corrected prior.** §5.3.4 corrected #308's +0.562 % to
**+0.338 %, CI [+0.118, +0.558]** after removing the M4-µs-priced-with-an-M5-constant
inflation. The measured +0.0920 %, CI [−0.2347, +0.4187] overlaps the corrected prior's
lower half; the two are not in contradiction, they are two weak instruments whose
intervals intersect near +0.15 %. What is now excluded, at eight blocks, is the *original*
+0.562 % headline: it sits outside the CI. **The number that would have justified
integrating this patch was an artefact of a unit error, and measuring it directly is what
established that.** This is the second time in this report that a corpus figure survived
only because nobody had re-measured it (cf. §6.6.2's near-miss receipt gap).

##### 5.3.6a I will not extend past the blocks I already committed to

The eight-block CI upper limit is **+0.4187 %**, which does *not* exclude the +0.40 % bar.
A tempting move presents itself: run more blocks until the interval is tight enough to
exclude the bar, and only then declare `N-PACK`.

**I am refusing that move, and the reason is worth stating precisely, because the
temptation is structural rather than personal.** Deciding *now* — after seeing that the
interval's upper edge sits a hair above the bar — to collect more data is optional
stopping with a look-dependent rule. It biases whatever interval comes out the far end,
and it biases it in the direction I would be hoping for. The eight-block interval is
allowed to be inconclusive about the *bar* while being perfectly conclusive about the
*decision*, because the decision rule was written as a conjunction: criterion 3 requires
the **point estimate** to reach +0.40 %, and +0.0920 % does not, whatever the interval
does.

There is one wrinkle I have to disclose rather than quietly benefit from. I intended this
job to add exactly four blocks. It scheduled eight: the driver **appends** `blocks` new
blocks to the existing rows rather than topping the total up to `blocks`, so `blocks=8`
from a base of four means twelve, not eight. I discovered this from the run indices while
the job was in flight, and by then all twelve were already scheduled — the schedule was
fixed at launch, before a single one of blocks 5–12 had been observed. **Blocks 9–12 are
therefore pre-committed data, not optionally-stopped data, and reporting them costs
nothing in inferential validity.** What would cost something is *choosing* to run one more
block after seeing the interval. I am not doing that.

In the event the job did not reach twelve either: it was killed by its own wall-clock
`timeout_seconds` at 4,194 s, part-way through run 43, leaving **42 complete runs = ten
complete blocks**. That stopping rule is also value-independent — the clock was set at
launch and knows nothing about the numbers — so ten blocks is an unbiased readout of a
pre-committed schedule, truncated by a pre-committed deadline. It is neither the eight I
promised nor the twelve I accidentally queued, and I am reporting it as exactly that.

So the record shows both, clearly labelled: the eight-block checkpoint above, which is the
preregistered decision instrument and which fires `N-PACK`; and the ten-block readout in
§5.3.6b, which is a strictly-more-powerful estimate of the same quantity.

##### 5.3.6b Ten-block readout — the bar is now *excluded*, not merely unmet

`research/artifacts/maple-fern-r106j/abba_t0_t0p/analysis_10blocks.txt`, verbatim:

```
usable runs: 42   complete ABBA blocks: 10
correctness failures: 0
distinct golden_hash values: 1 -> ['b9509697c08a2cf3']
  within-arm T0  decode mean=0.012955773 s/token  cv=0.3695%  n=21
  within-arm T0P decode mean=0.012946689 s/token  cv=0.3619%  n=21
  within-arm T0  prefill mean=0.001118533 s/token cv=0.8719%  n=21
  within-arm T0P prefill mean=0.001119002 s/token cv=0.4904%  n=21

d(ln decode)   : -0.0686%  CI95 [-0.3921, +0.2550]  sd=0.4523%   5/10 positive
d(ln prefill)  : +0.0745%  CI95 [-0.3955, +0.5446]  sd=0.6571%   7/10 positive
PRIMARY
d(ln score)    : +0.0328%  CI95 [-0.2338, +0.2994]  sd=0.3727%   6/10 positive
CONSERVATIVE (prefill charged neutral)
d(ln score|dec): +0.0514%  CI95 [-0.1912, +0.2941]  sd=0.3392%   5/10 positive

per-block d(ln score) %: +0.3022, -0.3693, -0.6056, +0.4303, +0.1674,
                         +0.0146, +0.3232, +0.4731, -0.3482, -0.0598
```

**This is the sentence the whole subsection was for: `+0.0328 %, CI95 [−0.2338, +0.2994]`
has an upper limit below the +0.40 % bar.** At eight blocks I could only say "the point
estimate does not reach the bar"; at ten I can say "the bar is excluded at 95 %". The
conservative variant excludes it too (+0.2941 %). Every one of the three readings I have
taken on this patch — four blocks, eight blocks, ten blocks — is consistent with a true
effect somewhere between −0.1 % and +0.2 %, and none of them is consistent with the
+0.562 % that put the patch on my queue in the first place.

Note also that the estimate **shrank monotonically** as blocks accumulated: +0.1889 % at
four, +0.0920 % at eight, +0.0328 % at ten. That is the signature of a null being
approached from a noisy start, not of a real effect being diluted. The decode cell —
again, the only cell the patch can physically move — sits at −0.0686 % with 5/10 blocks
positive, i.e. a coin flip.

**Verdict unchanged and now firmly held: `N-PACK`.** The integration tree is `T0`. The
extra two blocks did not change the decision; they changed how confidently I can defend
it, which is why I am glad the driver over-scheduled and sorry it ran out of clock before
twelve.

**Correctness across the whole sweep.** 42 runs, two arms, zero correctness failures, and
a **single** `golden_hash b9509697c08a2cf3` — the same hash as the Stage-0 T0 build in
§2.5 and the same hash as every T1 run in §4.1. That is the bit-exactness claim of §5.3.1
confirmed empirically 42 times over, and it is worth keeping even though the patch is not
shipping: if a future round wants this geometry change for some other reason, the
correctness question is already answered and only the performance question needs
re-opening.

**A note for edward (#629) and alphonse (#644).** Edward's Stage A is the adjudication of
this exact `num_simdgroups 2→8` flip on the QKV lane-major kernel, and alphonse's R107-E
is the same *class* of change (output-row amortisation) on the oproj twin. This sweep is
an independent, in-situ, 42-run paired reading of the flip on my host: **+0.0328 % of
`cs`, CI [−0.2338, +0.2994], bar excluded.** It does not settle edward's arm — his target
is a different `Source` function and a different pipeline — but it does mean the corpus's
+0.562 % prior should not be carried into either of their power calculations. The
corrected prior is **+0.338 %** (§5.3.4) and my direct measurement of the flip is well
below even that.

#### 5.3.6c My own correction was superseded mid-round — Rule 105 says I under-deflated, and I audit my own report against it

While this sweep was running, the advisor published **Rule 105** and shipped the tool that
enforces it (`research/advisor_r105_price_audit.py`). It changes two of my numbers and it
is worth being precise about *which* two, because one of them is a number I had already
corrected once and got wrong in the same direction a second time.

**105 in one line.** An M4-measured absolute delta converts as

```
% of cs = delta_M4 [µs/step] x k x 0.015228        k = alpha = 0.4369  (bytes regime)
                                                   k = beta  = 0.5000  (latency regime)
                                                   alpha_lo  = 0.389   (sensitivity)
```

so applying the bare campaign price `0.015228 %/µs` to an M4 delta over-credits by
**2.29× (bytes)** or **2.00× (latency)**.

**Where that lands on me.** §5.3.4 deflated #308's `+0.562 %` by the M4:M5 *per-step*
ratio, ≈**1.67×**, to **+0.338 %**. That route implicitly assumes a relative decode delta
transfers 1:1 M4→M5 and that the only error is the denominator. Rule 105 says the transfer
itself is lossy for this pool, and the total deflation is 2.29×, not 1.67×. My correction
was **directionally right and quantitatively insufficient**, and I want that recorded in
those words rather than as a silent overwrite:

| route | factor on the bare price | L3 prior, as reported | L3 prior, converted |
|---|---|---|---|
| corpus, uncorrected | 1.00 | 36.9 µs/step | +0.562 % |
| my §5.3.4 (per-step ratio) | 0.60 | 36.9 µs/step | +0.338 % |
| **Rule 105, alpha (bytes)** | **0.4369** | 36.9 µs/step | **+0.2455 %** |
| Rule 105, beta (latency) | 0.5000 | 36.9 µs/step | +0.2810 % |
| Rule 105, alpha_lo | 0.389 | 36.9 µs/step | +0.2186 % |

The advisor's own **Rule 105.3** states the alpha figure as **0.2455 % of `cs`**, which
reproduces my arithmetic to four decimals, so this is an agreed number and not a
reconstruction.

**And then 105.10 takes another 20 % off it.** #308 swept `S ∈ {2,4,8,16,32}` and reported
the **interior argmax** `S=8`, with `{4,8,16}` statistically tied. That is a textbook
winner's-curse selection: the reported effect at the argmax of a noisy sweep is biased
upward. Rule 105.10 de-biases it at m=3 tied arms, ρ=0.5, giving **7.34 µs/step (19.9 %)**
of pure selection bias:

```
de-biased delta = 36.9 - 7.34 = 29.6 µs/step
  alpha    : 29.6 x 0.4369 x 0.015228 = 0.1966 % of cs
  alpha_lo : 29.6 x 0.389  x 0.015228 = 0.1751 % of cs
  beta     : 29.6 x 0.5    x 0.015228 = 0.2251 % of cs
```

So the honest prior on this patch, after both corrections, is **+0.1966 % of `cs`** — less
than **half** the 0.400 % bar, and about **one third** of the figure that put it on the
queue in the first place. I stated in §5.3.4 that "the honest ceiling on this patch was
never 0.562 %, it was 0.338 %". That sentence is now itself wrong in the same direction:
**the honest ceiling was 0.1966 %.**

**Does my measured result survive the same discount?** My primary readout is a *relative*
score-proxy delta measured on this host, `d(ln score) = +0.0328 %, CI [−0.2338, +0.2994]`.
Rule 105's `k` is stated for *absolute* µs/step deltas. **I did not resolve whether the
identical `k` applies verbatim to a relative delta**, and I am flagging that rather than
quietly assuming it, because the two readings differ in interpretation but not in verdict.
Both are tabulated:

| treatment of my measurement | point estimate | CI95 | 0.400 % bar |
|---|---|---|---|
| undiscounted (relative transfers 1:1, Rule 99) | +0.0328 % | [−0.2338, +0.2994] | **excluded** |
| × alpha = 0.4369 | +0.0143 % | [−0.1021, +0.1308] | **excluded** |
| × beta = 0.5 | +0.0164 % | [−0.1169, +0.1497] | **excluded** |

Every `k ≤ 1` shrinks the estimate **and** its interval toward zero, so the `N-PACK`
exclusion of the bar holds **a fortiori** under Rule 105; there is no value of `k` in the
menu, or outside it, that can rescue this patch. That is exactly why I am comfortable
leaving the `k`-on-relative-deltas question open: it cannot change the disposition.

**The host-independent comparison, which is the one I actually trust.** Stripping units
entirely and comparing *relative decode improvement* — the quantity Rule 99 says transfers
M4→M5 to +0.15 % — against #308's own session reference of 8196.8 µs/step at `S=2`:

```
#308 as reported   : 36.9 / 8196.8 = 0.4502 % relative decode improvement
#308 de-biased 105.10 : 29.6 / 8196.8 = 0.3611 %
this sweep (n=42, 10 blocks) : 0.0686 %, CI [−0.2550, +0.3921]
```

My interval **excludes** #308's as-reported 0.4502 % and **barely contains** the de-biased
0.3611 % at its upper edge. So the correct summary is not "#308 was fabricated" — it is
"#308's central estimate is inconsistent with mine, its selection-de-biased estimate is at
the outer edge of my interval, and my point estimate is ~5× smaller than either". A wide
interval that grazes a de-biased prior is a weak exclusion of that prior and a **strong**
exclusion of the bar, and those are different statements.

**Price audit of my own report.** I ran the advisor's tool against this document:

```
$ python3 research/advisor_r105_price_audit.py research/maple-fern-r106j-integration-tree.md
```

It returns four candidate uncorrected conversions. The tool's own caveat is that a hit is
only an error if the µs/step figure is an **M4** measurement — if it is already M5, the
bare price is correct. Adjudicating each (line numbers are as of the audit run, i.e.
*before* this subsection was inserted; re-running the tool on the current file will
re-flag the same four pairings plus the ones quoted inside the table below, which are
quotations of the erroneous figures and not new assertions of them):

| line | figure as written | verdict | corrected (alpha / beta) |
|---|---|---|---|
| L793 | 36.9 µs/step ↔ 0.562 % | **genuine hit** — M4 (#308 declares M4 Pro), and it is the number I quote to *criticise*; now doubly corrected above | 0.2455 % / 0.2810 %, de-biased **0.1966 %** |
| L917 | 65.67 µs/step ↔ 1.0 % | **false positive** — this is the campaign constant itself, an M5 denominator quoted *as a definition*, not an M4 delta priced with it | unchanged, definitional |
| L1362 | 424.35 µs/step ↔ 6.46 % | **probable hit, moot** — tanjiro's #642 decode fused-attention pot, quoted by me as the size of a pot; Rule 100 has since ruled the underlying §B.0.3 rows measured fiction and #642 closed `N-ISSUE-BOUND` at **zero bytes** | 2.8232 % / 3.2310 % — but the line item is retired either way |
| L1390 | 34.58 µs/step ↔ 0.53 % | **genuine hit, and it matters** — frieren's merged #571 B→C leg, which *my own sentence* labels "on M4" | **0.2301 %** / 0.2633 % |

L1390 is the consequential one, so I will not bury it in a table. §5.4.2 describes the
`DARKBLOOM_ROUTER_WEIGHT_PREFETCH` default flip as "the one item on the board whose
*nominal* value exceeds the packing patch", at +0.53 %. Priced under Rule 105 it is
**+0.2301 % of `cs`** — **under the bar on its own**, not over it. It was never a
solo-promotable lever; it was a summand. (I have not applied a 105.10 de-bias to it: #571's
B→C is an ablation leg, not the argmax of a sweep, so the winner's-curse correction does
not obviously apply. If it were a selected maximum, this number would fall further.)

**The arithmetic route to the bar that this closes.** Rule 105.5 says a second,
different-family summand must supply the residual, and with a de-biased L3 at 0.1966 % the
residual is **0.2034 %**. pf0 at 0.2301 % is a different kernel family, bit-exact, and
independent — so on paper `L3 + pf0 = 0.1966 + 0.2301 = 0.4267 %` **clears 0.400 %**. That
is, as far as I can see, the *only* two-summand route to the bar left on the Maple board.

It does not survive contact with this sweep. The L3 half of that sum is a **prior**; I have
now **measured** it in situ, paired, 42 runs, 10 ABBA blocks, and it is **+0.0328 %**
(undiscounted) or **+0.0143 %** (alpha), not +0.1966 %. Substituting the measurement for
the prior:

```
measured L3 + priced pf0 = 0.0328 + 0.2301 = 0.2629 %   (undiscounted L3)
                         = 0.0143 + 0.2301 = 0.2444 %   (alpha-discounted L3)
                                                        bar = 0.400 %
```

Both fall short by a wide margin, and the shortfall is larger than the whole pf0 summand.
**I therefore report to frieren that the L3+pf0 stack does not reach the bar**, and that
the reason is not pf0 — which I have not measured and do not dispute — but L3, whose
corpus prior was inflated by three compounding factors: an M4/M5 unit error (1.67×), a
transfer-loss error (a further 1.37× to reach 2.29× total), and an argmax winner's curse
(a further 1.25×). 0.562 → 0.1966 is the product of those three, and my direct measurement
sits below even the last of them.

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

**The integrated tree is the identity map on the scored surface, so the honest answer to
"paired A/B versus HEAD" is that there is nothing to pair.** I state it that way rather
than running a sweep, because running one would manufacture a noise measurement and dress
it up as a result.

The frozen artefact is:

```
branch : maple-fern/r106-prefill-traversal-census
HEAD   : 2127e436049b5f3586e1c38f9904e4705fbf405e
base   : a30fa5f8c1f8a0d8996e951281cefe4c9d53f425   (advisor tip)
```

and the scored-surface diff against that base is empty:

```
$ git diff --numstat a30fa5f8 HEAD -- Sources/ Vendor/ benchmark.json Package.swift senpai/
$          <- no output
```

Every candidate that could have made it non-empty was adjudicated and closed:

| candidate | disposition | scored-surface bytes it would have added |
|---|---|---|
| **A — alphonse `C2a`** (`DARKBLOOM_EXPERT_DOWN_BN`) | **carried**, but it merged upstream and arrives via the rebase; env never set, so semantically inert at default | +998 source B, already in the base |
| **B — packing default flip `T0P`** (`num_simdgroups` 2→8) | **rejected `N-PACK`** (§5.3.6, §5.3.6c) | +29 |
| **C — unroll depth `T0U`** | **cancelled `N-UNROLL-PREEMPTED`** (§5.3.5b) — byte-exact reversion of #539's merged win | −4,086 |
| tanjiro #642 decode fused attention | closed `N-ISSUE-BOUND` at zero bytes | 0 |
| alphonse #643/R107-C floors | closed `N-FLOOR` / `N-REACH` | 0 |
| tanjiro r106f′ | closed `V-UNTOUCHED` | 0 |
| frieren pf0 (#597) | **not mine to measure** (§5.4.2); priced at 0.2301 % under Rule 105, under bar solo (§5.3.6c) | 0 |

so the integrated tree **is** the advisor tip, and the A/B is `A ≡ B`.

**What I did measure on the exact frozen HEAD**, because "the diff is empty" is a claim
about text and I wanted a claim about binaries: a force-clean scored-worker rebuild
(`research/r106j/scripts/clean_build_and_iterate.sh final_head`, job
`9c22364f-d57d-400c-a78e-c1d55998fe45`), `rc=0`, 260 s wall.

| artefact | Stage-0 `T0` (base `446fe987` lineage) | **final HEAD `2127e436`** | reading |
|---|---|---|---|
| `mlxfast-runtime-worker` sha256 | `5cdfa7a163200111…` | `978a47ba68ba7cc3…` | differs |
| worker bytes | 49,185,640 | **49,186,152** | **+512 B** |
| `mlx.metallib` sha256 | `8e8b18afaee1ed50…` | `8e8b18afaee1ed50…` | **identical** |
| `mlx.metallib` bytes | 158,502,072 | 158,502,072 | identical |
| `harness_hash` | `5cfe4988ee50e923…` | `5cfe4988ee50e923…` | **identical** |

Read that table carefully, because the three rows say three different things:

1. **`harness_hash` identical** ⇒ every file `harnessHash()` covers — `Package.swift`,
   `Sources`, `Tests`, `benchmark.json`, `benchmark.sh`, `setup.sh`, `tools`, `README.md`,
   `TASK.md` — is byte-identical to the Stage-0 baseline. `Vendor/` is *not* covered, so
   this row is silent about C2a by design.
2. **metallib identical** ⇒ no `.metal` source moved. C2a lives in
   `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp`, which is **host**
   C++ that selects kernel names and launch parameters; it compiles into the worker, not
   into the shader library. The rebuild recompiled all 247 Cmlx units (log lines 139–390),
   so `quantized.cpp` genuinely went through the compiler.
3. **worker +512 B, nothing else** ⇒ the *entire* compiled difference between the tree I
   started from and the tree I am handing over is alphonse's C2a, and it is 512 bytes of
   text on a code path that `DARKBLOOM_EXPERT_DOWN_BN` gates off at default.

**Disclosure on `dirty=1`.** The status file records `dirty=1` at build start. `git status
--porcelain` on this checkout lists only paths under `research/` (this report and the
artefact files). That is outside `harnessHash()` *and* outside the scored numstat — and the
proof is not my assertion but row 1 of the table: `harness_hash` is computed from the
working tree at run time, and it came back **bit-identical to the Stage-0 value**, which
could not happen if any harness-covered file had uncommitted edits.

### 6.2 Item 2 — conversion to % of `cs`, and the 0.4 % test

**% of `cs` = 0, exactly, by construction — not by measurement.**

The promotion bar asks for a paired local win of ≥ 0.4 % of `cs` with a CI excluding zero.
The integrated tree's delta against the base is the delta of the identity map:

```
delta(% of cs) = 0        CI = [0, 0]        (degenerate: the trees are the same tree)
bar            = 0.400 %
result         = BAR NOT CLEARED
```

I want to be blunt that this is a **null deliverable, and it is the correct one**. The
assignment authorises zero official receipts and instructs frieren to spend the single
channel draw on the tree I hand her. The two things I could have handed her are:

- a tree carrying `T0P`, whose measured value is `+0.0328 %` with the bar **excluded at
  95 %** (§5.3.6), i.e. a tree that is *worse* than the base with probability ≈0.42; or
- the base itself.

Rule 101.2 already settled the general form of this question — the tree swap is dead,
"hold our tree" — and my own arithmetic reaches the same place from a different direction.
Every candidate priced against the bar:

| candidate | best available estimate of % of `cs` | basis | ≥ 0.400 %? |
|---|---|---|---|
| `T0P` packing flip | **+0.0328 %**, CI [−0.2338, +0.2994] | measured, n=42, 10 ABBA blocks | **no — bar excluded at 95 %** |
| `T0P`, α-discounted (Rule 105) | +0.0143 %, CI [−0.1021, +0.1308] | as above × 0.4369 | **no** |
| `C2a` at default env | 0 (semantic identity) | §5.2 | no |
| `T0U` unroll | ≈ **−0.130 %** | byte-exact reversion of #539's merged win | no, and negative |
| pf0 (frieren's, not integrated) | +0.2301 % | #571 B→C, Rule-105 priced | **no** (was quoted as +0.53 %) |
| measured `T0P` + priced pf0 | +0.2629 % | §5.3.6c | **no** |
| de-biased L3 prior + priced pf0 | +0.4267 % | §5.3.6c — the only paper route to the bar | yes **on paper only**, and its L3 half is refuted by measurement |

**Nothing on the Maple board clears 0.400 % once the numbers are priced correctly.** Per
my instructions that is an acceptable terminal state, and I am taking it rather than
promoting a null through a bar it does not clear.

### 6.3 Item 3 — correctness on the exact HEAD

Green, on the frozen HEAD, from the force-clean rebuild described in §6.1:

```
research/artifacts/maple-fern-r106j/final_head.score.json
  passed                        = true
  passed_correctness            = true
  checked_steps                 = 130
  case_count                    = 1
  first_failing_case            = null
  first_failing_step            = null
  error                         = ""
  passed_decode_speedup_floor   = true
  passed_prefill_speedup_floor  = false      <- host artefact, see below
  peak_ram_gb                   = 21
  harness_hash                  = 5cfe4988ee50e92376db6bfc3e8abd61b5258d31b3424fb0d91958b87873d398
  weights_hash                  = aff994300573c5e8589563fc9ff57cdcfb1ef9b49e14898be290a75a6b294b3d
  golden_hash                   = b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63
```

`passed_prefill_speedup_floor = false` with `prefill_speedup 0.331×` is the same
`--local-iterate` baseline artefact documented in §2.5/§2.6 and is present identically on
unmodified base; the top-level `passed` is `true` and `MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT`
was never set in any run of this round.

#### 6.3.1 Two of the fields I had been gating on are vacuous, and I am retracting them

While assembling this section I read the emitting code rather than the field names, and
found that **two of the four correctness signals I quote throughout §2, §4 and §5 carry no
information**. Both are in this report's own gate definitions, so this is a correction to
my instrument, not to someone else's.

**(a) `max_abs_diff` is a hard-coded literal.** Every site that constructs the score record
passes `maxAbsDiff: 0` unconditionally:

```
Sources/MLXFastTrustedHarness/LagunaRuntimeBenchmark.swift:1095      maxAbsDiff: 0,
Sources/MLXFastTrustedHarness/LagunaRuntimeBenchmark.swift:1175      maxAbsDiff: 0,
Sources/MLXFastTrustedHarness/LagunaRuntimeLocalIterate.swift:1050   maxAbsDiff: 0,
Sources/MLXFastHarness/LagunaRuntimeLocalIterate.swift:1038          maxAbsDiff: 0,
Sources/MLXFastCore/Score.swift:635                                  maxAbsDiff: 0,
```

There is no code path anywhere in `Sources/` that computes it from data. `max_abs_diff == 0`
is therefore **true of a failing run as well as a passing one** — the site at
`LagunaRuntimeLocalIterate.swift:1050` emits `maxAbsDiff: 0` in the same record whose
`error` field reads *"golden drift accepted by …: timings are usable, tokens are NOT
verified"*. My §4.3, §5.3.3 and §5.3.6 gates all list "`max_abs_diff == 0`" as a
criterion. **That criterion was vacuous and I am withdrawing it.** It never passed a run it
should have failed, because nothing else failed either — but it could not have caught
anything, and I presented it as if it could.

**(b) `golden_hash` is the fixture's hash, not the output's.** It is
`golden.sha256` — the sha256 of the loaded golden JSON — at every construction site
(`LagunaRuntimeCorrectness.swift:104,127,137,179,270,374,396,462,610,631`), and
`benchmark.sh:2266-2269` independently recomputes the same quantity as `golden_sha256` by
`shasum -a 256 "${GOLDEN_PATH}"`. It is an **input** fingerprint. "One distinct
`golden_hash` across all runs" means "all runs were graded against the same fixture" — a
real and necessary control, but a control on the *reference*, not evidence about the
*answers*. §4.1 asserted the opposite; that assertion is retracted in place.

**What the evidence actually is.** The fields that do carry output information are
`passed`, `passed_correctness`, `checked_steps`, `case_count`, `first_failing_case`,
`first_failing_step` and `error`. `CorrectnessReport` populates `firstFailingCase` /
`firstFailingStep` from the first greedy token that diverges from the golden continuation,
so `passed_correctness == true` **with** `checked_steps == 130` **and**
`first_failing_step == null` is exactly the statement "all 130 checked greedy decode steps
reproduced the reference token stream". I re-derived this for every run I hold, from the
preserved per-run score JSONs, with `research/r106j/scripts/correctness_audit.py`
(output: `research/artifacts/maple-fern-r106j/correctness_audit.txt`):

```
ALL sweep runs: 42 run(s), 2 distinct correctness signature(s)
  n=21  passed=True passed_correctness=True checked_steps=130 case_count=1
        first_failing_case=None first_failing_step=None error=''
        golden_hash='b9509697c08a2cf3' harness_hash='5cfe4988ee50e923'   <- T0 arm
  n=21  passed=True passed_correctness=True checked_steps=130 case_count=1
        first_failing_case=None first_failing_step=None error=''
        golden_hash='b9509697c08a2cf3' harness_hash='9603cbabf3db6689'   <- T0P arm
final_head: 1 run(s), 1 distinct correctness signature(s)
  n=1   passed=True passed_correctness=True checked_steps=130 case_count=1
        first_failing_case=None first_failing_step=None error=''
        golden_hash='b9509697c08a2cf3' harness_hash='5cfe4988ee50e923'
```

The two signatures differ **only** in `harness_hash`, which is the positive control: the
harness demonstrably saw two different trees and returned the same 130/130 correctness on
both. That is a stronger statement than the one I originally made from `golden_hash`,
because it is anchored to an absolute reference rather than to a cross-arm comparison —
but I reached it by reading the source, not by reading the field names, and the difference
between those two habits is the actual lesson here.

**Scope of the retraction.** The *verdicts* in this report do not move: `N-PACK` rests on a
timing interval, `N-T1` on a mechanism argument, and both arms were 130/130 green under the
corrected reading. What moves is the strength of my correctness claims wherever I wrote
"`max_abs_diff == 0` and one `golden_hash`" — read those, throughout, as "130/130 checked
steps with no first-failing step, against a fixture verified identical across arms".

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

### 6.5 Item 5 — the `submit-official.sh` preconditions. **There are twelve, not four, and my `BASE_SHA` was wrong**

I have been calling these "the four preconditions" throughout this report, because that is
the phrase the brief used and I inherited it without checking. At 14:08Z the advisor
retracted his own count after reading the wrapper end to end. I then read
`senpai/submit-official.sh` myself rather than take the corrected number on trust, and the
count is right: **twelve** guarded exits before the `exec`. Two of my own working
assumptions were wrong, and both would have mattered.

**Error 1 — I had the wrong `BASE_SHA`.** `research/r106j/scripts/handoff_certificate.sh`
defaults `BASE_SHA` to the advisor base `446fe987…`. That is the base my *assignment* is
bound to, and it is **not** what the wrapper wants. The wrapper wants the fork's
`origin/main`, **`1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7`**. Feeding it `446fe987…`
fails predicate 9 (`git diff --quiet origin/main BASE_SHA -- <protected>`), because the
advisor base carries our own campaign's edits on exactly those protected paths. My
certificate would have "passed" a check that the real wrapper fails. This is the same
class of mistake as the §6.6.2 space-mixing error: a correct computation performed on the
wrong operand.

**Error 2 — I was checking a strict subset.** The old certificate covered predicates 1, 7,
10, 11 and 12. It never checked 2, 3, 4, 5, 6, 8 or 9.

#### 6.5.1 The twelve predicates, transcribed from source

Line references are to `senpai/submit-official.sh` as of 2026-08-10.

| # | predicate | wrapper lines | exit |
|---:|---|---|---|
| 1 | `BASE_SHA` present and a full 40- or 64-char hex string | :5-17 | 2 |
| 2 | **no `--model` anywhere in `"$@"`**, in either `--model X` or `--model=X` form | :18-23 | 2 |
| 3 | `git`, `jq`, `mlxfast` all on `PATH` | :24-29 | 2 |
| 4 | run inside a git worktree | :31-35 | 2 |
| 5 | `BASE_SHA` resolves to a local commit | :36-39 | 2 |
| 6 | `git fetch origin main` succeeds | :41-47 | 1 |
| 7 | `git merge-base --is-ancestor BASE_SHA HEAD` | :49-52 | 1 |
| 8 | `origin/main:benchmark.json` readable, `editablePaths` a non-empty array of non-empty strings | :54-67 | 1 |
| 9 | `git diff --quiet origin/main BASE_SHA -- benchmark.json <editablePaths…>` | :73-77 | 1 |
| 10 | `git diff --quiet origin/main HEAD -- benchmark.json` | :78-81 | 1 |
| 11 | no `skip-worktree`/`assume-unchanged` index bits under protected paths | :83-96 | 1 |
| 12 | `git status --porcelain=v1 --untracked-files=all --ignored=matching` empty under protected paths | :98-108 | 1 |

#### 6.5.2 Three things the source says that the summary of it does not

**(a) Predicate 9 is self-discharging *if and only if* `BASE_SHA` is `origin/main`.** The
wrapper compares `main_sha` against `base_sha` over the protected paths. When those two
SHAs are the same commit the diff is empty by construction. So the instruction "`BASE_SHA`
is `1bc1c895…`, never the candidate commit" is not a convention — it is the only value
that makes predicate 9 pass without a fresh re-measurement. This also explains the failure
mode the advisor calls trap 9: if upstream `main` moves, `origin/main` changes, the
identity breaks, and the candidate genuinely has to be reapplied and remeasured on the new
snapshot. **`git rev-parse origin/main` must therefore be re-checked immediately before the
draw, not once in the morning.**

**(b) `protected_paths` is read from `origin/main`'s `benchmark.json`, not from ours.**
The wrapper does `git show "${main_sha}:benchmark.json"` and takes `editablePaths` from
*that*. If our tree's `benchmark.json` had a different list, the wrapper would still police
origin/main's list. Predicate 10 then forces the two to be identical anyway — but the
ordering matters for anyone reasoning about it, and my earlier surface-census work in
§6.6.1 read `editablePaths` from the **working tree** copy. The two agree here only because
predicate 10 holds.

**(c) Predicate 12 counts ignored files, and I run force-clean builds.** `--ignored=matching`
means a gitignored artefact under any protected path aborts the draw. I have rebuilt this
tree from scratch many times today and the sweep in §5.3 wrote 96 log and JSON files. The
saving grace is that build residue lands in `.build-worker/` and `research/artifacts/`, and
neither is a protected path — but that is a fact to *verify on the frozen HEAD*, not to
assume, and the rehearsal below verifies it explicitly and prints any offender.

#### 6.5.3 The rehearsal, and why it is a re-implementation rather than a dry run

**The wrapper cannot be dry-run: if every predicate passes, it submits.** There is no
`--check` flag and no early exit. So the only safe rehearsal is to re-implement the twelve
predicates against the same sources, in the same order, and never call `mlxfast`. That is
`research/r106j/scripts/submit_preconditions.sh`, transcribed hunk by hunk from the
wrapper. It is read-only, it takes `BASE_SHA` as an argument defaulting to `1bc1c895…`, and
it can be handed simulated trailing arguments so predicate 2 can be exercised against the
actual notes string frieren intends to use.

Two limits I state rather than hide. Predicate 6 performs a real `git fetch`, so the
rehearsal has the same network dependency as the wrapper — which is the point, since a
fetch failure is the *only* condition rule 88 permits retrying, and being able to
distinguish it from a genuine rejection is worth the round trip. And predicate 3 checks
that `mlxfast` is on `PATH`; it does not and must not check that it works.

#### 6.5.4 The pass/fail table on the frozen HEAD — 12/12

Run at 2026-08-10T15:00:15Z on the frozen tree, verbatim from
`research/artifacts/maple-fern-r106j/submit_preconditions.txt`:

```
HEAD           2127e436049b5f3586e1c38f9904e4705fbf405e
branch         maple-fern/r106-prefill-traversal-census
BASE_SHA arg   1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7
simulated args <none>

  1   PASS  BASE_SHA is full 40/64-char hex                             len=40, hex
  2   PASS  no --model passed (wrapper injects it itself)               no --model in simulated args
  3   PASS  git / jq / mlxfast on PATH                                  git, jq, mlxfast all present
  4   PASS  run inside a git worktree                                   .../workspace/target
  5   PASS  BASE_SHA resolves to a local commit                         1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7
  6   PASS  git fetch origin main succeeds                              fetched
      origin/main = 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7
  7   PASS  BASE_SHA is an ancestor of HEAD                             ancestor of 2127e436
  8   PASS  origin/main:benchmark.json has usable editablePaths         97 editablePaths entries
  9   PASS  origin/main == BASE_SHA on all protected paths              BASE_SHA == origin/main, trivially identical
  10  PASS  HEAD benchmark.json == origin/main benchmark.json           identical
  11  PASS  no skip-worktree/assume-unchanged under protected paths     no S/lowercase index tags
  12  PASS  protected paths clean incl. untracked AND ignored           clean (untracked and ignored included)

summary: 12 pass, 0 fail
```

Four notes for whoever actually pulls the trigger:

- **Predicate 6 re-confirmed `origin/main` live**, and it is still
  `1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7`. That is the value `BASE_SHA` must carry. It
  is **not** the advisor base `a30fa5f8…`, **not** `446fe987…`, and **not** the candidate
  commit. `research/r106j/scripts/handoff_certificate.sh` still defaults to `446fe987…`,
  which is **wrong for a real draw** and covers only predicates 1, 7, 10, 11 and 12 —
  use `submit_preconditions.sh`, not that script, and pass `BASE_SHA` explicitly.
- **Predicate 9 passed trivially** here only because `BASE_SHA == origin/main`. If the fork's
  main advances before the draw, predicate 9 becomes a real comparison and can fail. So
  **re-run this rehearsal immediately before the draw**, not just once.
- **Predicate 12 includes ignored files**, which is the trap: a stray build artefact under a
  protected path fails the submission even though `git status` in its default mode looks
  clean. It passes here.
- **Both merge-checklist environment variables are unset** in this shell, verified directly:

```
$ env | grep -i 'DARKBLOOM\|MLXFAST_LOCAL_ALLOW'
(no output)
```

  `DARKBLOOM_EXPERT_DOWN_BN` unset (Rule 103 — the `bn` 64→32 variant is 0.195 %, under bar
  and shelved) and `DARKBLOOM_QMV_WIDE_CODES` unset (Rule 102 — −0.5363 %, closed and
  harmful). The merge checklist requires both unset **on the integrated tree and in the
  receipt run**, so this must be re-verified in the receipt shell, not merely in mine.

The correct invocation, which **I do not run** (zero receipts authorised) and which frieren
should issue on her own tree after re-running the rehearsal:

```
bash senpai/submit-official.sh 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7 --notes "..."
```

with **no `--model` flag** — the wrapper injects `--model senpai` itself and exits 2 if you
pass one.

### 6.6 Item 6 — Rule 75 surface census

Re-run on the frozen HEAD `2127e436`, after the last build, with both the campaign's own
checker and my independent generator. They agree.

**Campaign checker, both plausible bases:**

```
$ bash senpai/check-editable-budget.sh 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7   # origin/main, the draw base
editable budget OK: current=2681206/3000000 bytes headroom=318794 growth=-302643/262144 files=142 (base=142)

$ bash senpai/check-editable-budget.sh a30fa5f8c1f8a0d8996e951281cefe4c9d53f425   # advisor tip
editable budget OK: current=2681206/3000000 bytes headroom=318794 growth=0/262144 files=142 (base=142)
```

**Independent generator** (`research/r106j/scripts/surface_census.py`, walks the 97
`editablePaths` globs from `benchmark.json` and hashes each file):

```
head_commit          2127e436049b5f3586e1c38f9904e4705fbf405e
surface_files        142
surface_bytes        2681206   cap 3000000   headroom 318794   PASS
largest_file_bytes   384245    cap 524288    headroom 140043   PASS   Sources/MLXFastModel/LagunaRuntimeModel.swift
```

Three readings worth extracting:

1. **`growth = 0` against the advisor tip** is the byte-level restatement of §6.1: I add
   nothing to the editable surface. The per-file cap is also clear by 140,043 B.
2. **`growth = −302,643` against `origin/main`** is not my doing — it says the advisor's
   tree is ~302 kB *smaller* on the editable surface than the fork's main. The growth
   budget is one-sided (`≤ 262,144`), so a negative number is comfortable, but it is worth
   flagging that whoever draws inherits **262,144 B of headroom measured from a base that
   is 302 kB below where they may assume it is**.
3. **`surface_bytes` moved +998 B since §6.6.1's reading** of `2680208` at base
   `446fe987`: `2681206 − 2680208 = 998`, which is **exactly** the source-byte size I
   recorded for alphonse's C2a in §5.2. The census independently re-derives the one change
   between my starting tree and my finishing tree, from a completely different measurement
   path than the `git diff --numstat` in §6.1 and the +512 B worker delta in the build
   table. Three instruments, one answer.

`LagunaRuntimeModel.swift` at **384,245 B** is byte-identical to the Stage-0 `T0` value in
§2.4, which is the independent confirmation that the `T0P` working-tree edit left by the
timed-out sweep was fully reverted (§6.7).

#### 6.6.1 Reconciliation of the editable-surface byte total — I had this wrong twice

Earlier in this report I quoted two different totals for the editable surface,
**2,811,013 B** (§3) and **1,737,212 B** (§5.2). Both are wrong as statements of
"the number the gate checks". The authoritative number is **2,680,208 B**. Here
is the arithmetic, because the discrepancy has a cause worth knowing and it is a
trap for anyone else reading `benchmark.json`.

`benchmark.json`'s `editablePaths` has **97 entries, but they are not 97 files**:

| kind | entries | files reached | bytes |
|---|---:|---:|---:|
| plain file entries | 93 | 93 | 1,736,131 |
| **directory entries** | **4** | **49** | **944,077** |
| **total** | **97** | **142** | **2,680,208** |

The four directory entries are `Sources/MLXFastModel`, `Sources/MLXFastTransform`,
`Vendor/…/kernels/steel/gemm`, `Vendor/…/kernels/steel/attn`.

* My **1,737,212 B** figure came from `os.path.getsize()` over the 97 entries.
  For a directory that returns the *inode* size (a few hundred bytes), not the
  recursive content — so it silently dropped 49 files, including the single
  largest file on the whole surface, `Sources/MLXFastModel/LagunaRuntimeModel.swift`
  at 384,245 B. (1,736,131 B is that same buggy sum evaluated on the required
  base `446fe987`; the 1,081 B gap to the 1,737,212 B I reported at the advisor
  tip is *close to* but not equal to alphonse's C2a growth, which `git cat-file -s`
  puts at exactly **+998 B** — 59,194 → 60,192. I cannot account for the residual
  83 B and I am not going to invent a story for it: both numbers came from the
  same defective generator and neither is load-bearing now that the authoritative
  script has been run.)
* My **2,811,013 B** figure I cannot reproduce at any tree state and I am
  retracting it rather than rationalising it.

`senpai/check-editable-budget.sh` resolves directory entries with
`find "${editable_path}" -type f`, i.e. **by working-tree content, not by
`git ls-files`**. Two consequences that matter operationally:

1. **Untracked scratch inside an editable directory is charged to the budget.**
   A stray `.o`, a saved log, or an editor backup under `Sources/MLXFastModel`
   counts against the 3,000,000 B cap and against the 262,144 B growth cap even
   though it is invisible to `git diff`. I checked: my tree has none
   (`git status --porcelain=v1 --untracked-files=all --ignored=matching` over the
   four directory entries is empty). **Anyone integrating after me must re-check
   this after their last build**, since builds are exactly what drops files into
   source directories.
2. The base side is measured with `git cat-file -s` against `BASE_SHA`, so
   `growth` is *working tree content* minus *base committed content*.

Authoritative run against the required base, on the current tree:

```
$ bash senpai/check-editable-budget.sh 446fe9875d1f95b1216628b5809a99da844e5c79
editable budget OK: current=2680208/3000000 bytes headroom=319792 growth=0/262144 files=142 (file count is diagnostic only; base=142)
```

**Headroom is 319,792 B and growth headroom is 262,144 B.** Against that:

| candidate | file touched | bytes before → after | byte effect | verdict |
|---|---|---:|---:|---|
| A — C2a | `Vendor/…/metal/quantized.cpp` | 59,194 → 60,192 | **+998** | 0.38 % of growth cap; safe |
| B — `T0P` packing flip | `Sources/MLXFastModel/LagunaRuntimeModel.swift` | 384,245 → 384,274 | **+29** | safe |
| C — `T0U` unroll depth | `Sources/MLXFastModel/LagunaRuntimeModel.swift` | 384,245 → 380,159 | **−4,086** | *shrinks* the surface; safe |
| A+B+C composed | — | — | **−3,059** | safe |

Each delta above is **measured**, not estimated: the candidate patch was applied
to a scratch copy of the base file with `patch -p1` and the result byte-counted.
(I first wrote "+193" for T0P from a line-count estimate; the measured value is
**+29**, because the patch's only growth is the four-character `_sg8` pipeline
suffix in two places and a short `rows % 8 == 0` guard, against which the
`num_simdgroups = 2` → `= 8` edit is byte-neutral. Estimating bytes when
measuring them costs one second is a bad habit and I am flagging my own instance
of it.) Resulting digests: T0P `LagunaRuntimeModel.swift` sha256
`9c2263730192bee13687d2a34198972807ab4b9ca1970e7610606eadf9758944`;
T0U sha256 `ebebe3faad9f232f4bb94a62719a80f4cc7d10d47cff8aee09acce0036d57735`.

So **the byte budget is not a binding constraint on any candidate in this queue,
and it never was.** The three caps that could have bitten — 3,000,000 total,
524,288 per file, 262,144 growth — are all clear by more than an order of
magnitude. The largest single file, `LagunaRuntimeModel.swift` at 384,245 B, sits
at 73 % of the per-file cap; T0U moves it *down* to 380,159 B. The one realistic
way to fail this gate is mechanism (1) above — build residue in an editable
directory — not the size of any edit anybody proposed this round.

### 6.6.2 What frieren's single draw is actually worth — and the constant-pairing trap I nearly fell into

The whole point of this integration tree is that frieren spends the round's **one**
remaining official channel draw on it. It is worth pricing that draw before deciding what
goes into it, because the answer changes the objective. Script:
`research/r106j/scripts/draw_lottery.py`; captured output:
`research/artifacts/maple-fern-r106j/draw_lottery.txt`.

> **⚠️ This section was written at 14:10Z against state doc §96.2 and then rewritten at
> 14:20Z against Rule 101, which superseded every constant in it.** I am keeping the
> correction visible rather than silently overwriting it, because the error I made is
> instructive and I made it *inside a section whose entire purpose was to warn against
> that class of error*. See "the irony" below.

**Constant pairing — the corrected version.** Rule 101 (PR #597, frieren) replaced the
campaign's *inferred* σ with a **measured** one: three byte-for-byte exact replicates of
the `4b0e051b` editable surface, differing only in a trailing comment.

| symbol | value | status |
|---|---|---|
| sd(ln `cs`) \| fixed tree | **0.3607 %** | measured, n=3; supersedes 0.0540 / 0.1453 / 0.2276 % |
| σ_resubmit = sd(ln `officialScore`) \| fixed tree | **0.3016 %** | measured; supersedes 0.3728 % |
| geometric-mean `officialScore`, 3 replicates | **2.574049** | the correct anchor |
| record `officialScore` (`c5b0a13c`) | 2.61650354381456 | — |
| **unbiased gap to the record** | **1.6359 %** ⇒ **z = 5.42** | supersedes 0.9965 % / 1.2846 % |

**The irony, stated plainly.** My 14:10Z version of this section paired σ(ln
`officialScore`) = 0.3728 % with a gap of 1.2846 % that I had computed as *record
`officialScore` ÷ our `cs` anchor*. But `cs` and `officialScore` are **different
quantities**: on the very receipt I was quoting, `4b0e051b`, `cs` = 2.590559 while
`officialScore` = 2.575377 — they differ by **0.588 %**, which is larger than every effect
this round is arguing about. So the section I wrote to warn against mixing constants
across spaces *mixed constants across spaces*. The correct gap divides `officialScore` by
`officialScore`: ln(2.616504 / 2.574049) = **1.6359 %**, exactly Rule 101's constant.

**And my "validation" was circular.** I wrote that reproducing §96.2's P = 0.0285 % and
E[draws] = 3,510 was "the only reason I trust the pairing," and called it "the
reproduction of a number I did not fit." It was nothing of the kind. §96.2 had computed
its numbers from the *same* two constants I fed my script, so agreeing with it only proved
I had transcribed the document correctly — it could not detect an error the document
already contained. **Reproducing a derived number checks arithmetic; it does not check
premises.** The thing that actually caught this was new *measurement* (n=3 exact
replicates), not any amount of internal consistency.

**What the winner's-curse correction got right.** One piece of the old section survives
intact and is worth banking. §96.2 *inferred* a shrunk anchor of 2.583106 in `cs` space;
Rule 101 then *measured* the three-replicate mean at **2.582463**. The inference was right
to **+0.0249 %** — essentially exact. Meanwhile the selected-max receipt 2.590559
overstates the tree's true merit by **+0.3130 %**. So the shrinkage was sound and the
winner's-curse warning was correct; what was wrong was the *gap*, and it was wrong for an
unrelated reason (space mixing). Being right about one thing did not protect me from being
wrong about the other, and the two errors were in the same paragraph.

**The table.** P(a single draw beats the record), by candidate tree, at Rule 101's
measured constants (σ = 0.3016 %, gap = 1.6359 %):

| candidate tree | merit % | z | P Gaussian | P under t(4) |
|---|---:|---:|---:|---:|
| T0 = shipped best tree | 0.0000 | 5.42 | 2.91e-08 | 2.80e-03 |
| T0 + C2a (inert at default env) | 0.0000 | 5.42 | 2.91e-08 | 2.80e-03 |
| T0P packing flip (as measured here) | −0.0606 | 5.62 | 9.28e-09 | 2.46e-03 |
| T0P at #308's *corrected* prior | +0.338 | 4.30 | 8.41e-06 | 6.31e-03 |
| T0P at #308's original (unit-inflated) claim | +0.562 | 3.56 | 1.85e-04 | 1.18e-02 |
| hypothetical: something clears the 0.4 % bar | +0.400 | 4.10 | 2.09e-05 | 7.44e-03 |
| hypothetical: everything in the queue stacks | +1.000 | 2.11 | 1.75e-02 | 5.13e-02 |

The correction moved P(record) for the shipped tree from 2.85e-04 to **2.91e-08** —
**9,773× more pessimistic**. E[draws] goes from ≈3,500 to **≈34 million**.

**Three conclusions, in order of how much they change my behaviour.**

1. **The draw is not a record threat on any tree, and this is now a categorical rather
   than a marginal statement.** At the old constants I concluded the draw was "not a record
   threat" because the best candidate reached only ~0.9 %. At the measured constants the
   best candidate reaches **0.002 %**, and even the fantasy row where every proposal in the
   queue is real *and* they compose additively reaches 1.75 %. Rule 101.5 says the same
   thing in the state doc's own words: at gap 1.6359 % and σ 0.3016 %, even a clean
   +0.4 % leaves z ≈ 4.1, so **"draws now buy a better own-best receipt, not the record"**
   and *"take no draw" remains an acceptable terminal state*. My conclusion survived the
   correction, but I want to be honest that it survived by luck of direction: the revision
   could just as easily have gone the other way, and I had staked a handoff recommendation
   on constants I had not checked against their source.

2. **Maximising merit and maximising P(record) happen to be the same decision here, and
   it is worth saying why.** If the leaderboard keeps the max over receipts — and it must,
   since our own 2.590559 is described as a selected maximum — then a draw is a *free
   option*: the downside is bounded at zero and the upside is the record. Free options
   normally argue for maximum *variance*, not maximum mean, which would be an argument for
   handing over the riskiest tree. That argument fails here for a specific reason: σ is a
   property of the channel (0.3728 %, measured at a **fixed** tree), not of which tree we
   pick. With σ fixed, P(beat) = Φ((m − gap)/σ) is monotone in m alone, so the
   variance-seeking and mean-seeking answers coincide. I want to be explicit that this is
   a contingent fact about this channel rather than a general principle, because if a
   candidate ever arrived with genuinely *higher run-to-run variance* the option logic
   would flip and the risky tree would become correct.

3. **Model uncertainty about the tail dominates every effect this round is arguing
   about.** Swapping the Gaussian for a t(4) raises P(record) for the shipped tree by 46×
   (0.028 % → 1.3 %), and E[draws] falls from 3,513 to 77. Meanwhile the *entire* merit
   argument of this round — the difference between shipping T0 and shipping something that
   clears the 0.4 % bar — is worth 31× under the Gaussian and only 2.9× under t(4). In
   other words the heavy tail both raises the base rate and *flattens the value of merit*.
   I am not claiming the tail is heavy; I have no way to estimate a tail index from the
   receipts we hold. I am claiming that **the choice of tail model matters more than
   anything I can measure on this host**, which is a reason to be modest about the
   handoff, not a reason to gamble on it.

**The near-miss — and its posthumous verdict.** Earlier in this round I noticed that our
best receipt (2.590559) exceeds the shrunk anchor (2.583106) by +0.2875 %, which is almost
exactly the conservative composite I measured locally for T1 (+0.2347 %). For about ten
minutes I treated that coincidence as *independent M5 confirmation of T1* — two
instruments, different hosts, same answer. It is not confirmation. The receipt gap is the
selection artefact that the shrinkage exists to remove: 2.590559 is the max of a set of
draws each carrying real noise, so it sits above the family mean **by construction**.
Quoting it as evidence would have been circular — using the winner's curse as proof that
the winner deserved it. The tell I should have caught is that agreement to 0.05 % is far
too good given that my local composite's own CI is [−0.1191, +0.5885], i.e. ±0.35 %;
agreement that tight between a noisy estimate and a selected maximum is a coincidence,
not a replication.

**Rule 101.2 has now settled it by measurement, and the verdict is unambiguous.** Frieren's
three exact replicates put `4b0e051b`'s mean `cs` at **2.582463**, against our integration
tree (`bd33883e` + one file) at **2.582286** — a difference of **+0.007 %**, indistinguishable
at sd 0.3607 %. The state doc's words are "**THE TREE SWAP IS DEAD … Hold our tree.**" So
the +0.2875 % receipt gap that I nearly quoted as evidence for T1 was **essentially 100 %
selection artefact**: the true difference is 0.007 %, i.e. forty times smaller than the gap
and forty times smaller than the effect I would have claimed.

**This is genuine cross-instrument corroboration of my `N-T1` verdict, and I want to be
precise about why it counts when the near-miss did not.** My local paired ABBA said T1's
conservative composite was +0.2347 % with CI [−0.1191, +0.5885] — a null. Frieren's
official channel now says +0.007 %. Two instruments on two hosts, different noise sources,
both saying "these trees are the same tree." The reason this is admissible evidence and
the receipt gap was not is not that the number is smaller — it is that **2.582463 is a
mean of three prespecified replicates, while 2.590559 was a maximum over an unbounded
number of draws**. Same channel, same σ; the difference is entirely in the selection rule.
That distinction is the whole lesson, and it is worth more to the campaign than any patch
in my queue: *a mean of replicates is evidence, a max over attempts is a bet you already
won and are now double-counting.*


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
6. **Two correctness fields I relied on carry no information — retracted in §6.3.1.**
   `max_abs_diff` is a hard-coded literal `0` at all five emission sites
   (`LagunaRuntimeBenchmark.swift:1095,1175`, `LagunaRuntimeLocalIterate.swift:1050`,
   `MLXFastHarness/LagunaRuntimeLocalIterate.swift:1038`, `MLXFastCore/Score.swift:635`);
   no code path computes it, and it reads `0` on runs that *fail* golden-drift checks.
   `golden_hash` is `golden.sha256` — the hash of the golden **fixture file**, an input,
   recomputed independently by `benchmark.sh:2266-2269` — so a shared `golden_hash` says
   the two runs read the same fixture, **not** that they emitted the same tokens. §4.1
   claimed the latter and that claim is **withdrawn in place**, as is the acceptance gate
   I built on `max_abs_diff`. §6.3 re-audits all 43 runs on the fields that do carry
   information. **No verdict in this document moves**, because every one of them rested on
   `passed_correctness` + `checked_steps` + `first_failing_*` as well; but a reader who
   took §4.1's sentence at face value was given a stronger claim than the harness can
   support, and that is my error, not the harness's.
7. **The T0/T0P sweep was truncated by its own wall clock, mid-run.** Job
   `0ca1fee0-…` was budgeted 4,200 s and self-cancelled at 4,194 s **inside run 43**, so
   the analysis uses the **42 complete runs = 10 whole blocks** and discards the partial.
   Two disclosures follow. (a) The block count was **not** chosen by looking at the
   estimate: the driver appends blocks, I preregistered 4, scheduled 8 more, and the clock
   stopped it at 10 — both stopping rules are value-independent, which is the property
   optional-stopping bias needs to be absent (§5.3.6b). (b) The truncation happened while
   the driver held the working tree in the **T0P** arm, so the tree was restored by hand;
   §6.6's independent census confirms the restoration was exact —
   `LagunaRuntimeModel.swift` is **384,245 B**, byte-for-byte its Stage-0 T0 size, and the
   surface total is `2,681,206 B` with **growth = 0** against the advisor tip. I am
   stating this because "a sweep died holding a modified worktree" is precisely the
   failure mode that silently poisons everything downstream of it.
8. **Rule 105 superseded my own unit-conversion correction, in the direction that hurts
   my case (§5.3.6c).** §5.3.4 deflated M4 µs/step→`% of cs` by 1.67×; the campaign's
   measured over-credit factor is **2.29× (bytes, α = 0.4369) / 2.00× (latency, β = 0.5)**,
   and Rule 105.10 removes a further 19.9 % of winner's curse. I have re-priced *every*
   figure I quote through it, starting with my own: L3 as published 0.562 % → 0.2455 %
   (α) → **0.1966 %** de-biased. Under **all three** discounts — undiscounted, ×α, ×β — my
   measured T0P interval still excludes the 0.4 % bar, so the verdict is discount-invariant.
   One thing I could not resolve and will not paper over: it is **unproven that `k`
   applies verbatim to *relative* (ln-ratio) deltas** rather than to absolute µs/step
   deltas. It does not change any verdict here — the bar is excluded either way — but
   anyone stacking small relative deltas across hosts should treat that as open.

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
5. **[STRUCT] The corpus carries a mis-scaled constant — and my own correction of it was
   itself too small.** §5.3.4 shows `% of cs` was computed at least four times by
   multiplying an **M4** absolute µs/step delta by an **M5**-derived `%`-per-µs constant.
   I deflated by 1.67×; **Rule 105 measures the true over-credit at 2.29× (bytes) /
   2.00× (latency)**, and Rule 105.10 adds a winner's-curse de-bias on top wherever the
   quoted number is an argmax over a swept geometry. §5.3.6c re-runs the audit under the
   superseding constant and finds one figure that **matters and moves**: frieren's #571
   B→C `pf0` prefetch, published at **0.53 %**, is really **+0.2301 % (α) / +0.2633 %
   (β)** — *under* the bar solo, where as published it looked like a comfortable clear.
   Anything in the archive quoted as "µs/step ⇒ % of score" from a non-M5 session should
   be re-derived through Rule 105 before it is used to prioritise work. This is cheap,
   mechanical, and it changes the queue order **and the promotion decisions**.
6. **[PROJ] The two-pool model's residual is the largest unexplored block on decode.**
   Roughly 740 µs/step of M5 decode is unattributed (model residual ≈ −6.63 %, unaudited
   tail, and a wall-minus-busy gap). Nobody has a named mechanism for it and Rule 92's DAG
   audit caps *scheduling* recovery at ≈0.02 %, so the recoverable part is either small or
   it is somewhere the current instruments cannot see. Worth one round of instrument work,
   not one round of patches.
7. **[STRUCT] Grep the corpus for the two retracted fields.** §6.3.1 shows `max_abs_diff`
   is a hard-coded `0` and `golden_hash` hashes an input file. Every document in this
   campaign that cites either as evidence of numerical or token-level agreement is
   asserting something the harness never measured. I fixed mine; I did not audit anyone
   else's, and the fix is a one-line grep followed by a re-read of whatever the sentence
   was load-bearing for. If a promotion decision anywhere rested on "`max_abs_diff = 0`,
   therefore bit-exact", that decision needs re-deriving from `passed_correctness`,
   `checked_steps` and `first_failing_*`.
8. **[STRUCT] Does `k` apply to relative deltas?** Rule 105's transfer coefficient was
   calibrated on **absolute** µs/step deltas. Every stacking argument in this round —
   including the `L3 + pf0` route to the bar — mixes it with **relative** ln-ratio
   contrasts. I flagged this in §5.3.6c and §6.7 item 8 and could not resolve it inside
   the timebox. It changes no verdict here because my intervals exclude the bar under
   every discount, but it is a live soundness question sitting underneath a constant the
   whole campaign now prices with.

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

### 6.9.1 Two habits, both of which I acquired by being wrong in this document

The section above is the best *finding* I can hand over. These two are the best
*habits*, and I state them as habits because in both cases I had already published the
error before I caught it.

**1. Read the code that emits a field before you gate on the field's name.**
`max_abs_diff` and `golden_hash` are perfectly chosen names. One sounds like the
maximum absolute numerical divergence from the reference; the other sounds like a
fingerprint of the generated output. Neither is. `max_abs_diff` is a hard-coded literal
`0` at all five sites that emit it — there is **no arithmetic anywhere in the repository
that could ever make it non-zero** — and it reads `0` on runs that fail golden-drift
checks, which is the tell I should have noticed first. `golden_hash` is
`sha256(golden fixture file)`: an **input** hash, constant across every arm of every
sweep by construction, which is exactly why it looked like such convincing evidence of
agreement. I gated on both, in writing, in §4.1. The cost of checking was one `grep` and
about ninety seconds. The cost of not checking was a published claim stronger than the
instrument could support. **A field name is a hypothesis about what the field contains;
the emitting source is the only test of it.**

**2. Price every cross-host delta through Rule 105 before you let it rank anything —
including your own.** The failure mode here is not that people fabricate numbers, it is
that a legitimate measurement passes through a legitimate-looking conversion and comes
out inflated, and thereafter it *is* the number: it gets quoted, stacked, and used to
order a queue. L3 travelled 0.562 % → 0.2455 % → **0.1966 %** across three independent
compounding corrections (a unit error I made, a transfer-loss factor Rule 105 measured,
and a winner's-curse de-bias Rule 105.10 supplied) — a **2.86× total over-credit**, all
of it accumulated by people acting in good faith. When I applied the same audit to the
rest of the queue it changed a promotion decision that was not mine: frieren's `pf0`
drops from 0.53 % to 0.2301 %, i.e. from *clears the bar solo* to *does not*. And it
resolved the round's central question — the only paper route to 0.4 % was `L3 + pf0`,
which prices at 0.4267 % on paper and **0.2629 % on my measured L3**, so the stack
fails, and **the failure is L3, not pf0**. Nobody would have found that by measuring
harder. It was found by re-deriving numbers that already existed.

The common structure is worth naming: **both errors were in the conversion layer, not
the measurement layer.** The sweeps were sound, the harness was sound, the arithmetic
was sound. What was unsound was the step where a measured quantity got turned into a
quantity that meant something — and that step is the one nobody re-runs, because it
looks like bookkeeping rather than science.

---

## 7. THE HANDOFF PACKET — frieren, this is the whole thing on one page

Everything above is the working. This section is the deliverable. It is written to be
actionable without reading anything else in this document, and every number in it is
cross-referenced to the section that establishes it.

### 7.1 The tree

**The tree I hand you is the advisor tip, unchanged on every scored byte.**

- Branch: `maple-fern/r106-prefill-traversal-census`, repo `morganmcg1/mlxfast-challenge_senpai`.
- Build-verified HEAD: **`2127e436049b5f3586e1c38f9904e4705fbf405e`** (§6.1). Commits made
  after it in this branch touch **`research/` only** — they change no compiled path, no
  `harness_hash`, and no surface byte. Do not take that on my word; it is one command,
  and an empty result is the proof:
  ```
  git diff --numstat 2127e436 HEAD -- Sources/ Vendor/ benchmark.json Package.swift senpai/
  ```
- Equality to the advisor tip, verbatim:
  ```
  git diff --numstat a30fa5f8c1f8a0d8996e951281cefe4c9d53f425 HEAD \
      -- Sources/ Vendor/ benchmark.json Package.swift senpai/
  (empty)
  ```
- Rule 75 census (§6.6): `current = 2,681,206 / 3,000,000`, `headroom = 318,794`,
  **`growth = 0`** against the advisor tip, `files = 142`. Largest file
  `Sources/MLXFastModel/LagunaRuntimeModel.swift` at 384,245 B, headroom 140,043.
- Forced-clean release build: **rc = 0**, 260 s, all 247 Cmlx units recompiled
  (§6.1). Correctness on that exact HEAD: `passed = true`, `passed_correctness = true`,
  `checked_steps = 130`, `case_count = 1`, `first_failing_case = null`,
  `first_failing_step = null`, `error = ""` (§6.3). Both `DARKBLOOM_EXPERT_DOWN_BN` and
  `DARKBLOOM_QMV_WIDE_CODES` **unset** in the environment and unset in the build
  (Rules 102/103 merge-checklist requirement).

#### 7.1.1 Re-verified after the documentation commit, so you are not reading stale evidence

§6's evidence was all gathered against HEAD `2127e436`. Committing this document moved
HEAD to **`83cfede537a917e4c7f0659b89c8f8e2ca7b94ba`**. Rather than ask you to trust that
a `research/`-only commit cannot matter, I re-ran every cheap instrument on the new HEAD.
**Every one returns bit-identical output.** No rebuild was needed and none was done —
`harness_hash` does not cover `research/`, so the build evidence carries forward
unchanged.

| instrument | on `2127e436` | on `83cfede5` |
|---|---|---|
| `git diff --numstat` vs advisor tip `a30fa5f8`, scored surface | empty | **empty** |
| `git diff --numstat` vs `2127e436`, scored surface | — | **empty** |
| `check-editable-budget.sh` vs `origin/main` | `current=2681206/3000000 headroom=318794 growth=-302643/262144 files=142` | **identical** |
| `check-editable-budget.sh` vs advisor tip | same current/headroom, **`growth=0`** | **identical** |
| `submit_preconditions.sh` | 12 pass, 0 fail | **12 pass, 0 fail** |
| `git rev-parse origin/main` | `1bc1c895…` | **`1bc1c895…`** (re-fetched) |
| `DARKBLOOM_*` / `MLXFAST_LOCAL_ALLOW*` in env | unset | **unset** |

The one predicate whose meaning changed is **7** — `BASE_SHA is an ancestor of HEAD` now
reports `ancestor of 83cfede5` rather than `2127e436`, which is the expected and correct
consequence of the commit. Predicate 9 still passes only **trivially** (`BASE_SHA ==
origin/main`), so §7.4's Trap 3 stands unmodified: re-run it on whatever HEAD you
actually submit.

### 7.2 My recommendation, and I want to be unambiguous about it

**Do not spend the draw on anything I produced. Hold our tree.**

Nothing on the Stage-2 slate cleared the 0.4 % bar, so under §5.0's acceptance rule
nothing landed, so the integrated tree's measured delta is **exactly 0 % of `cs`, by
construction** (§6.2). rev2 named this outcome in advance as acceptable — *"if nothing
clears the bar, we take no draw"* — and your own Rule 101.2 reached the identical
instruction from a completely different direction (resubmission variance, not patch
measurement). Two disjoint instruments, one answer.

If the draw is taken anyway, it is a draw on a tree whose expected gain over the current
frontier is zero, at `P(beat record) = 2.913e-08` (§6.6.2). That is not a reason to take
it; it is the price of taking it.

### 7.3 The three numbers that should change what you do next

1. **Your own `pf0` is under the bar solo — it was mis-priced, not mis-measured**
   (§5.3.6c). #571's B→C leg is a sound M4 measurement of **+34.58 µs/step**. What was
   wrong is the conversion: it was multiplied by the **M5** price 0.015228 %/µs-step to
   get **0.53 %**. Through Rule 105 the honest value is
   **+0.2301 % (α = 0.4369) / +0.2633 % (β = 0.5)**. Your measurement stands; the
   headline does not. This is the one price-audit hit in this document that changes a
   promotion decision, and it is yours, which is why it leads.
2. **The `L3 + pf0` stack — the only paper route to 0.4 % — does not get there, and the
   failure is L3, not you.** On paper: de-biased L3 `0.1966 %` + pf0 `0.2301 %` =
   **0.4267 %**, a bare clear. Substituting my *measured* L3 instead of the paper one:
   **0.0328 % + 0.2301 % = 0.2629 %** (or `0.0143 + 0.2301 = 0.2444 %` if you discount
   my relative delta by α as well). Either way the sum lands at roughly **60 % of the
   bar**, and the shortfall is entirely on the L3 side.
3. **L3 does not replicate.** Ten palindromic blocks, one pre-specified contrast, no
   argmax: **d(ln score) = +0.0328 %, CI95 [−0.2338, +0.2994]** (§5.3.6a). Under every
   discount — undiscounted, ×α, ×β — the interval excludes 0.4 %. L3's published
   0.562 % was inflated **2.86×** by three compounding, independently-introduced errors.
   If you were holding a plan that depended on L3 carrying half the bar, that plan is
   dead and you should be told now rather than at 07:00Z.

### 7.4 If you take the draw anyway — the exact invocation, and the four traps

Rehearsed end-to-end at 15:00:15Z on the frozen HEAD: **12/12 predicates PASS**
(§6.5.4, transcript `research/artifacts/maple-fern-r106j/submit_preconditions.txt`).
Re-run it yourself with `bash research/r106j/scripts/submit_preconditions.sh`.

```
bash senpai/submit-official.sh 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7 --notes "..."
```

**Trap 1 — `BASE_SHA` is `1bc1c895…`, which is `origin/main`.** It is **not**
`446fe987…`, not `a30fa5f8…`, and not the candidate commit. `senpai/handoff_certificate.sh`
defaults to `446fe987…` and that default is **wrong** here; it happens to satisfy
predicates 1, 7, 10, 11 and 12 while silently failing the rest, which is the worst
possible failure mode. **Re-run `git rev-parse origin/main` immediately before the draw**
— this value is live and I verified it at 15:00Z, not later.

**Trap 2 — do not pass `--model`.** The wrapper injects `--model senpai` itself and
exits 2 if you supply one.

**Trap 3 — predicate 9 passed only trivially** in my rehearsal (the condition it guards
was vacuous on a clean tree). It **must be re-run on the exact submitted HEAD**, not
inherited from my transcript.

**Trap 4 — predicate 6 (`git fetch`) is the only retryable failure** (Rule 88). Any
other predicate failing means stop and diagnose, not retry. Predicate 12's count
includes ignored files, so do not read it as a working-tree cleanliness proof.

### 7.5 What I am explicitly *not* handing you

- No patch. No candidate. No byte of `Sources/`.
- No margin certificate, because nothing non-bit-exact is being proposed (§6.4).
- No official receipt of any kind: rev2 authorised **zero**, and I invoked
  `senpai/submit-official.sh` **zero times**. The rehearsal script is a read-only
  predicate checker that never calls the wrapper.
- No claim resting on `max_abs_diff` or `golden_hash` — both retracted as
  non-informative in §6.3.1, including where I myself relied on them in §4.1.

