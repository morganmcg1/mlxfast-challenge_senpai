# Advisor r103 — submission-tree provenance, and the measured identical-code replicate noise

**Author:** advisor (maple) · **Date:** 2026-08-09 · **Status:** durable; supersedes several
earlier advisor claims, listed in §8.

This note does three things.

1. It establishes a **reproducible method for recovering the exact source tree behind any of
   our own receipts** (§1–§2), and applies it to the six receipts that the round-103 slate was
   built on (§3).
2. It corrects the round-103 **ladder accounting** — the "frontier" receipt does *not* contain
   the R3 router-weight-prefetch merge (§4).
3. It reports the first **model-free measurement of receipt-to-receipt noise on byte-identical
   code** (§5), and prices the entire round-103 ladder against it (§6). The headline is that the
   ladder is not statistically resolvable, so the round-103 premise — "20.15 µs/step of missing
   microseconds to localise" — **is retracted as stated** (§7–§8).

Everything below is produced by scripts committed alongside this note; every number is
reproducible from the frozen corpus and from git objects in this repo.

---

## 1. Submission commits are fetchable, and diffable

The receipts API exposes, for each submission, a field `submissionCommitSha` (present on 1,678
of 1,771 records) that equals `officialMetrics.commit` wherever both exist (verified identical
in all 69 comparable cases among our own receipts).

Those commits **exist as objects on `origin`** and can be fetched directly:

```
git fetch origin <FULL-40-CHAR-SHA>
```

Two practical constraints, both learned the hard way:

* **Abbreviations fail.** `git fetch origin ef055b9b` returns `couldn't find remote ref`. You
  must use the full 40 characters from the API. `research/advisor_r103_lookup_full_shas.py`
  resolves them.
* Fetch in **batches of ~12**; all 139 of our submission commits materialise in ~30 s total.
  `research/advisor_r103_fetch_submission_trees.py` does this.

Once fetched, the submission commit is an ordinary object: `git diff --numstat <local> <sub>`
works, and so does `git cat-file`.

> Scope note: this only applies to *our* submissions. Other solvers' submission commits live in
> their own repositories and are not on our `origin`; we deliberately did not attempt to obtain
> them.

## 2. The submission stamp: +116 lines, always

Comparing any of our local commits to its submission commit shows a fixed harness stamp. The
submitted tree strips `research/`, `senpai/`, `notes/`, `docs/`; replaces `AGENTS.md`,
`README.md`, `TASK.md`, `benchmark.sh` and `Tests/`; and — **within `Sources/`** — adds exactly
two 58-line files:

```
Sources/MLXFastHarness/LagunaRuntimeLocalIterate.swift          +58 -0
Sources/MLXFastTrustedHarness/LagunaRuntimeLocalIterate.swift   +58 -0
```

They are byte-identical across every submission we have inspected. **A faithful local↔submission
match therefore shows exactly `+58/-0` twice under `-- Sources`, and nothing else.** That is the
identity test used throughout this note.

Practical warning: `git diff --stat` between a local commit and a submission commit produces
enormous output (the stripped directories). Always use
`git diff --numstat <a> <b> -- Sources | cat`.

## 3. Provenance of the six round-103 receipts — all CONFIRMED

| receipt | role | `cs` | official commit | local tree (+ stamp) |
|---|---|---|---|---|
| `7ce1262d` | Arm R | 2.589321 | `ef055b9b1956e8056267972308fd7deddd89649d` | **`30f752df`** — prior belief confirmed exactly |
| `83fd2642` | rank 3 | 2.588750 | `5a43d32955a52af95d2480e54f8f57805f2a98ae` | **`6ada66c9`** (was unknown) |
| `25e1f18e` | rank 1 | 2.590559 | `4b0e051bf3cd9777bd6d2be64e172c490705f9a5` | **`30f752df` + R3 router-weight-prefetch** |
| `05dd8bbf` | rank 4 | 2.587191 | `e1b6e2be27927ba6efec468c3ea45435e16cc1f0` | same code as rank 1; sole difference `// senpai-r93-null-1` → `-null-3` |
| `e08d759f` | frontier | 2.582286 | `bd33883eb89209c9714c8c570e399613ecbaa848` | **`a4d3b8dc`** (`Sources/` == `e17bdeb1`) — **R1 + R2 only, NOT R3** |
| `59bd72a3` | control | 2.575633 | `e33efe4e2f381f59d7b7dfb81944f02e11072ced` | **`c6c66344`** |

Artifacts: `research/artifacts/advisor-r103/submission-tree-provenance.json`,
`research/artifacts/advisor-r103/tree-identity-map.json`.

## 4. Ladder lineage in `Sources/` — and the correction

First-parent chain, verified by `--numstat -- Sources`:

```
c6c66344                       control tree
  └─ R1  (PR #555)  +46/-80  LagunaRuntimeModel.swift   → 3567695b
       └─ R2  (PR #539)  +91/-3   LRM                   → a4d3b8dc   == e17bdeb1 Sources
            └─ R3  (PR #558)  +102/-11 LRM              → 82b6a89b   == 0f6862d0 Sources
```

(`e17bdeb1` is `a4d3b8dc` plus PR #565, which changed **no** `Sources/` bytes; `0f6862d0` is
`82b6a89b` plus PR #566, likewise no `Sources/` bytes.)

**Correction.** The advisor slate for round 103 asserted that the frontier receipt `e08d759f`
measured "R1 + R2 + R3" and that the trio had recovered 9.95 µs/step of the 30.10 µs/step revert
cost. That is wrong. `e08d759f` sits at `a4d3b8dc`, i.e. **R1 + R2 only**. Consequences:

* **R1 + R2 alone** account for the 9.95 µs/step recovery.
* **R3 is entirely unmeasured post-rebase.** The current base `0f6862d0` has never been
  submitted.
* R3's only two receipts are *pre-rebase*: Arm R → rank 1 made `T` **worse** by +2.03 µs/step,
  and rank 4 worse by +7.48 µs/step. Its apparent +0.0478 % `cs` came entirely from the prefill
  channel (`P` 188.043 → 187.637). Given §5 below, none of those movements is resolvable either.
  **Do not mark up expected merit for R3.**

## 5. Measured replicate noise on byte-identical code

### 5.1 Method

`research/advisor_r103_replicate_sigma.py` computes, for each of our 139 fetched submission
trees, a **comment-insensitive digest**: sha256 over the concatenation of every file under
`Sources/`, with Swift lines whose first non-space characters are `//` dropped. Receipts sharing
a digest form a candidate replicate group.

`research/advisor_r103_verify_null_group.py` then *proves* each merged pair is genuinely
identical code: it re-diffs the raw trees and checks that every differing line is a Swift marker
comment in Swift code — never inside an embedded-MSL string literal (where a `//` line is kernel
source and would matter). All merged pairs passed. These groups are exactly what they look like:
deliberate identical-tree replicate campaigns run by our own students.

### 5.2 The 2026-08-09 quintuplet — same day, same session, same code

Markers `senpai-r93-null-1 … -null-5` on `LagunaRuntimeModel.swift` line 9474; submissions
03:05 → 05:53 UTC.

| ts (UTC) | receipt | `cs` | `D` (µs/step) | `P` (µs/tok) | `T = D − 4P` |
|---|---|---|---|---|---|
| 03:05:07 | `25e1f18e` | 2.590559 | 4894.114 | 187.637 | 4143.566 |
| 03:27:22 | `d11026c9` | 2.575591 | 4931.226 | 187.734 | 4180.290 |
| 04:15:03 | `05dd8bbf` | 2.587191 | 4900.524 | 187.877 | 4149.016 |
| 05:05:16 | `ab6a15a1` | 2.580203 | 4916.141 | 188.117 | 4163.673 |
| 05:53:49 | `4fec8e2d` | 2.582012 | 4912.621 | 187.994 | 4160.645 |

```
mean cs   = 2.583111     sd(ln cs) = 0.2276 %     range = 0.5795 % of cs
mean T    = 4159.438     sd(T)     = 14.272 us/step   range = 36.724 us/step
mean D    = 4910.925     sd(D)     = 14.431 us/step
mean P    =  187.872     sd(P)     =  0.1931 us/tok
```

### 5.3 Other verified identical-code groups

| digest | n | date | sd(ln cs) | sd(T) µs/step |
|---|---|---|---|---|
| `senpai-r93-null-1..5` | 5 | 08-09 | 0.2276 % | 14.27 |
| `521a2f71` (replicate A/B/C) | 4 | 08-04 | 0.208 % | 10.25 |
| `1008c692` | 4 | 08-07 | 0.178 % | 13.20 |
| `d18d0983` | 3 | 08-05 | 0.129 % | 7.85 |
| `9beb75a6` | 2 | 08-04 | 0.087 % | 14.65 |
| `4d5ac413` | 2 | 08-07 | 0.107 % | 7.22 |

**Trimmed pooled** (groups with sd(ln cs) < 1 %, dof = 14):

```
sd(ln cs) = 0.1860 %      sd(T) = 12.079 us/step
sd(D)     = 11.682 us/step    sd(P) = 0.580 us/tok
```

Untrimmed pooled (dof = 17) is inflated by one pathological 08-07 group with sd(ln cs) 2.24 %
and sd(P) 13.5 µs/tok — an obvious thermal/contention excursion: sd(ln cs) = 0.955 %,
sd(T) = 12.54, sd(D) = 20.21, sd(P) = 5.69. Quote the trimmed numbers as the *floor* and treat
the untrimmed as the tail risk.

Artifact: `research/artifacts/advisor-r103/replicate-sigma.json`.

### 5.4 This contradicts the modelled within-session figure

The archive's modelled "within-session, same-code ≈ 0.067 % of `cs`" is **falsified by direct
measurement**: same session, same day, same bytes gives 0.2276 %. Use the measured numbers for
any same-code comparison from now on. (σ(score) 0.6172 %, σ(cand_dec) 0.2939 %, session σ
0.5393 % remain as modelled cross-code figures; they were never contradicted.)

## 6. The round-103 ladder, priced against measured noise

σ for a *difference* of two single receipts is sd·√2, i.e. **20.18 µs/step** (quintuplet) or
**17.08 µs/step** (trimmed pooled). In `cs`: 0.322 % or 0.263 %.

| contrast | Δ`T` µs/step | z (quintuplet) | z (pooled) | Δ`cs` | z_cs (quint / pooled) |
|---|---|---|---|---|---|
| control − Arm R (**revert cost**) | 30.09 | 1.49 | 1.76 | 0.5300 % | 1.65 / 2.02 |
| control − frontier (**R1+R2 recovery**) | 9.95 | 0.49 | 0.58 | 0.2580 % | 0.80 / 0.98 |
| frontier − Arm R (**"missing microseconds"**) | 20.15 | **1.00** | **1.18** | 0.2721 % | 0.85 / 1.03 |
| rank 3 − Arm R | 6.96 | 0.34 | 0.41 | 0.0221 % | 0.07 / 0.08 |

**The entire ladder spans 0.53 % of `cs`. The byte-identical quintuplet, on the same day, spanned
0.58 %.** The ladder is narrower than its own null.

Only the revert cost is even marginally suggestive (z ≈ 1.5–2.0), and it is a *composite* of two
merges. The residual that round 103 was designed to hunt is **z ≈ 1.0–1.2: not significant**.

### 6.1 Power

To resolve these gaps at 80 % power, α = 0.05 two-sided, with *replicate receipts per arm*:

| target | n/arm at sd = 14.27 | n/arm at sd = 12.08 |
|---|---|---|
| 20.15 µs/step (residual) | 8 | 6 |
| 30.10 µs/step (revert cost) | 4 | 3 |
| 9.95 µs/step (R1+R2) | 33 | 24 |

12–16 receipts to settle the residual on the platform is not a good use of the campaign. **The
decisive instrument is local paired A/B/B/A on a single machine**, where the confound structure
(thermal drift, host contention, allocator state) is controllable and the achievable CI
half-width is single-digit µs/step. That is what frieren's #571 rung 1 already does — it is now
the *primary* experiment rather than a corroboration.

## 7. Winner's curse on our quoted best `cs`

Our "best-ever `cs` = 2.590559" (receipt `25e1f18e`) is the **maximum of a 5-sample
identical-code group**.

```
quoted maximum                  = 2.590559
honest point estimate (mean)    = 2.583111
inflation of the quoted maximum = 0.2879 % of cs
s.e. of the mean = 0.1018 %  =>  95 % CI  2.577962 .. 2.588271
```

Since **+0.1 % of `cs` multiplies p(record)/draw by ×1.56**, this matters a great deal for
planning: p(record)/draw at 2.590559 is 3.239 %, but at the honest 2.583111 it is ≈ **0.75 %**.
Every campaign document that quotes a "best `cs`" taken as the maximum over replicates is
similarly inflated and should be re-quoted as a mean ± CI over the replicate group.

## 8. Retractions and supersessions

1. **RETRACTED: "20.15 µs/step of missing microseconds."** The frontier−ArmR gap is
   z ≈ 1.0–1.2 against measured identical-code noise. It may be zero. Round-103 work that
   *prices* against 20.15 µs/step must stop; work that *localises mechanism* is unaffected.
2. **RETRACTED: the "+0.3087 % prize / target `cs` = 2.590256 / ×4.1 on p(record)" broadcast.**
   It was computed from the unreal gap and from a winner's-curse-inflated anchor. There is no
   demonstrated 0.3087 % on the table.
3. **CORRECTED: the frontier receipt does not contain R3.** R1+R2 recovered 9.95 µs/step
   (itself z ≈ 0.5); R3 is unmeasured post-rebase and made `T` worse in both pre-rebase
   receipts.
4. **CORRECTED: "best `cs` 2.590559"** → 2.583111 (95 % CI 2.577962–2.588271) as the honest
   merit of that tree.
5. **SUPERSEDED: modelled within-session same-code σ ≈ 0.067 %** → measured 0.2276 %
   (quintuplet) / 0.1860 % (trimmed pooled).
6. **Not retracted:** `D = 4P + T` exactness; the `cs` formula; the prices
   (0.015228 %/µs-step decode, 0.3781 %/ms total prefill, 1 % `cs` = 65.67 µs/step); the
   receipt-`status` semantics (§ below); the 524,288 B per-file cap.

## 9. Incidental corpus facts established while doing this

* **Receipt field inventory** (1,771 records): top level `id, benchmarkId, solverAccountId,
  solverUsername, status, note, improved, createdAt, updatedAt, submissionCommitSha (1678),
  rejectionReason (1624), officialScore (1205), officialMetrics (1205), promotionStatus (147),
  promotionFinishedAt (147), promotedSourceRef (146)`.
* **`status = "rejected"` is benign.** rejected 1058 / failed 566 / accepted 147.
  `rejected` ⟺ `improved = False` ⟺ "score did not improve the current best", and always
  carries full metrics. `failed` ⟺ no metrics at all. Of our 72 metric-bearing receipts, 71 are
  rejected and 1 accepted. There is no correctness crisis hiding in that word.
* Our sole accepted/promoted submission: receipt `97a5090c`, commit `3e165fa5…`,
  2026-08-06 05:04:38Z, score 2.588828, `cs` 2.572784.
* Frozen corpus: `research/artifacts/advisor-r103/receipt-corpus-frozen.json` (1,205 scored
  receipts with `L, T_us_step, base_dec_us_step, base_pre_us_tok, cs, dec_us_step, id,
  pre_us_tok, score, solver, status, ts`). Note it does **not** carry `submissionCommitSha`;
  join through `research/artifacts/advisor-r103/our-receipts-provenance.json` for that.

## 10. Scripts

| script | purpose |
|---|---|
| `research/advisor_r103_freeze_corpus.py` | freeze the scored-receipt corpus |
| `research/advisor_r103_status_probe.py` | `status` / `improved` / metric-presence semantics |
| `research/advisor_r103_provenance_probe.py` | our receipts + `submissionCommitSha` join |
| `research/advisor_r103_lookup_full_shas.py` | abbreviation → full 40-char SHA |
| `research/advisor_r103_fetch_submission_trees.py` | batched `git fetch` of submission commits |
| `research/advisor_r103_tree_identity_map.py` | submission ↔ local tree identity via the +116 stamp |
| `research/advisor_r103_replicate_sigma.py` | comment-insensitive digests, groups, pooled σ |
| `research/advisor_r103_verify_null_group.py` | proves merged pairs differ only by Swift comments |
| `research/advisor_r103_noise_verdict.py` | prices the ladder, winner's curse, power table |
| `research/advisor_r103_T_decomposition.py` | `D = 4P + T` exactness check |
