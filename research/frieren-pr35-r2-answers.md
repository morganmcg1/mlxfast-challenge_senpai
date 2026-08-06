# PR #35 r2 — the three analysis answers, in the order they were asked

The advisor's r2 ordering is: the OPS-value-per-arm answer, then deliverable A,
then the 4-bit lane-major plane. This file answers the analysis asks (§1-§4)
and states the ranked-slot request for A (§5) that I cannot deliver as a PR
comment, because the only GitHub transition available to a student is the
terminal `submit_result`.

All commit timestamps below are UTC. `git log --date=iso` on this checkout
prints `+0200`; earlier drafts of my notes misread two of those as UTC, so the
times here are the corrected ones.

---

## 1. `MLX_MAX_OPS_PER_BUFFER` per arm in the PR #23 r2 cap experiment

Definitive, and there is no contradiction between my two earlier statements.

| variable | arm **A** ("shipped" / control) | arm **B** (candidate) |
| --- | ---: | ---: |
| `MLX_MAX_MB_PER_BUFFER` | **200** (in-tree `setenv`, nothing exported) | **50** (exported) |
| `MLX_MAX_OPS_PER_BUFFER` | **400** (in-tree `setenv`, nothing exported) | **400** (exported) |

So the contrast was **50/400 vs 200/400**: a pure MB-axis move with ops held
fixed at 400.

### 1.1 Evidence

The arm definitions are in the experiment scripts, not reconstructed:

- `research/frieren_cap_abba.sh:5-9` — "A = shipped: no `MLX_MAX_*` in the
  environment, so `LagunaRuntimeWeights.swift:385-389` installs **200 MiB /
  400 ops**. B = candidate: `MLX_MAX_MB_PER_BUFFER=50
  MLX_MAX_OPS_PER_BUFFER=400`." The B export is at `:51`.
- `research/frieren_cap_prefill_abba.sh:4-5` — "A = shipped 200 MiB / **400
  ops** (no `MLX_MAX_*` in the environment); B = candidate 50 MiB / 400 ops."
  The B export is at `:37`.
- Companions used the same pair: `research/frieren_cap3_abba.sh:6,:43` and
  `research/frieren_verify_cap50.sh:41`.

The in-tree defaults that arm A inherited are installed at
`Sources/MLXFastModel/LagunaRuntimeWeights.swift:384-388`:

```swift
setenv("MLX_BFS_MAX_WIDTH", "50", 0)                    // :384
if env["DARKBLOOM_POST_WIRE_COMMAND_BUFFER"] != "0" {   // :385
    setenv("MLX_MAX_MB_PER_BUFFER", "200", 0)           // :386
    setenv("MLX_MAX_OPS_PER_BUFFER", "200", 0)          // :387
}
```

Two gates matter for reading that block: it only runs when
`config.numHiddenLayers >= 16` (`:359`) and only in the `else` branch of
`if policy.isLowMemory` (`:366`), i.e. the full ranked profile. Every call uses
`overwrite = 0`, so an exported value always wins over the in-tree default —
which is exactly why arm B could be set from the environment without a rebuild.

### 1.2 Why my two statements were both true

The tree changed underneath the two statements.

| commit | UTC | what it did |
| --- | --- | --- |
| `f4e33385` | 2026-08-04 15:37:25 | PR #23 r2's base ("Reorder 10h: the easy config is an M4 trap…") |
| `9a407ed6` | 2026-08-04 17:20:40 | "Cut 25.7 MB/token off the LM-head read stream" — flipped ops `400` → `200` |

`git merge-base --is-ancestor f4e33385 9a407ed6` is true, so the flip
**post-dates** r2's base and also post-dates r2's 15:53-16:12 UTC decode
session. At the base commit the tree shipped `400`; the `200` I quoted later is
today's tree. `git blame -L 387,387` attributes the `200` to `9a407ed6`
(Morgan McGuire), and `git blame -L 386,386` attributes the MB `200` to the
much older `814652a0`.

My own notes already recorded 400 at the time: `research/frieren-pr23-r2-result.md:239-240`
and `research/frieren-pr23-r2-cap.md:532-533`.

### 1.3 Reconciliation with nezuko's receipt — a strengthening, not a discrepancy

nezuko's ranked receipt tested the MB axis with ops at **200** (the current
tree value). Mine tested the MB axis with ops at **400**. The two agree:

| source | host | ops | MB contrast | wall effect |
| --- | --- | ---: | --- | ---: |
| my #23 r2 ABBA | M4 Pro, 48 GiB | 400 | 200 → 50 | **−1.76 %** |
| nezuko run `4db9908a` | ranked | 200 | 200 → 50 | **−1.99 %**, t = −3.2 |

Because the MB effect reproduces at both ops values, **the MB lever is robust
across ops ∈ {200, 400}**. That is a stronger claim than either receipt alone.

The ops axis was closed separately and deliberately, as an A/A at MB = 200
(`research/frieren_ops_aa.sh:42-45`, A → 200, B → 400; same 12-arm balanced
`A B B A | B A A B | A B B A` design, 2000 steps/arm, discarded warm-up).
Result, `research/frieren-pr23-r2-cap.md:552-587`: **null on all three
estimators** — pooled +0.144 % ± 0.125 % (t = +1.15), within-block paired
+0.144 % ± 0.143 % (t = +1.00, 2 df), OLS with linear position +0.144 % ±
0.130 % (t = +1.10); drift −0.0008 ms/position (se 0.0017). Note that this A/A
calls 200 the "shipped pair", so it ran after `9a407ed6`. Two consequences
recorded there: the ops axis is closed in `T` rather than only in cb/step, so
the ops-400 and ops-200 control arms are interchangeable and none of those
screens need a rerun; and the design's own A/A noise floor is ±0.13 % at 1σ.

### 1.4 Caveat to carry forward

"GPU busy" in my cb/step table is a **union of command-buffer intervals**, so
raising the number of command buffers shrinks it artificially. Only the
**wall/step** numbers carry the finding. nezuko's receipt is consistent with
this: her GPU union shrank 2.0 % while the host gap stayed flat (0.249 vs
0.250 ms).

---

## 2. The in-tree "200 MB / 200-op" comment: which axis did the 6 Latin pairs test?

`Sources/MLXFastModel/LagunaRuntimeWeights.swift:378-380`, verbatim:

```
// 200 MB / 200-op command buffers: the post-anupsv-loader regime
// re-test winner (6 Latin pairs: decode 5/6, prefill 4/6). Explicit
// MLX_ values win; DARKBLOOM kill switch supports same-binary A/B.
```

**Answer: neither axis alone. It was a joint move on both axes at once.**
`git show 814652a0 -- Sources/MLXFastModel/LagunaRuntimeWeights.swift` changes
the two `setenv` values in the same hunk:

```
-                    setenv("MLX_MAX_MB_PER_BUFFER", "512", 0)
-                    setenv("MLX_MAX_OPS_PER_BUFFER", "50", 0)
+                    setenv("MLX_MAX_MB_PER_BUFFER", "200", 0)
+                    setenv("MLX_MAX_OPS_PER_BUFFER", "200", 0)
```

So the 6 Latin pairs compared **512 MB / 50 ops** against **200 MB / 200 ops**.
The comment's "re-test winner" is the pair, not either coordinate.

### 2.1 Provenance

- `814652a0` — "Accept submission 6b369022-5c92-45bf-bfe4-3a926e146ece",
  **yukon-autoresearch[bot], 2026-07-29 06:28:05 UTC**, co-author
  `Gajesh2007`. This is an **imported upstream competitor submission**, not our
  work.
- The prior `512/50` came from `51ffe9b8` — "Validate submission
  7a5bfede-…", yukon-autoresearch[bot], 2026-07-28 19:45:08 UTC, co-author
  `zeeshan8281`.
- "post-anupsv-loader" matches anupsv's NVFP4-loader rewrite promoted
  2026-07-29 04:48 UTC (`senpai/competition_notes/leaderboard_promotions_2026-08-02.md:115`,
  PR #280 / `a800d87`) — about 1.7 h before `814652a0`.

**The "6 Latin pairs" data is not in this repository.** Only the sentence
survived the import, so the win cannot be attributed to either coordinate from
anything in-tree.

### 2.2 What can be inferred (marked as inference, not measurement)

The ops axis is not merely null in this model — it is **structurally
unreachable**, which is a stronger statement than my earlier notes made. From
the `research/frieren_cb_binding_sweep.sh` counters, recorded at
`research/frieren-pr23-r2-cap.md:455-465`: the largest command buffer this model
ever produces holds **28 ops at the shipped byte cap and 39 ops at a 400 MiB
cap**, and `cbs at ops limit` is **exactly 0 in all six arms across 131,954
command buffers**. The byte rule always fires first. So any ops cap at or above
~40 is dead configuration, and the entire 200 → 400 → 200 churn moved a
threshold sitting 5-14× above the highest value the counter it guards can reach.
That is also the mechanism behind the ops A/A null in §1.3: it was an A/A by
construction, not by luck.

Applied to `814652a0`: the ops half of the pair moved 50 → 200, and 200 is
certainly unreachable. Whether **50** was reachable in the 512 MB arm is the
only open question, and the counters bracket it awkwardly — max ops/cb rises
28 → 39 as the byte cap goes 200 → 400 MiB, so linear extrapolation to 512 MiB
lands near ~45, just under 50. **Inference, not measurement:** the 6-pair win
was therefore most likely carried entirely by the MB move 512 → 200, with the
ops half inert at both ends. But the extrapolation is close enough to 50 that I
cannot exclude a small tail of buffers clipping on the ops rule in the 512 MB
arm, and the underlying 6-pair data is not in this repository to check. What is
safe to assert either way: **nothing in the current regime rewards moving ops
away from 200**, and the knob is a good candidate for deletion rather than
tuning.

---

## 3. officialScore re-audit of my own notes

Per the 12:07:10Z metric rule — baseline prefill rel sd 1.932 %, baseline decode
rel sd 0.248 %, injected into `officialScore` at ~0.52 % (σ_ln ≈ 0.73 %), so no
conclusion may rest on an `officialScore` delta and ranking must use `ns` or
candidate prefill µs / candidate decode ms directly.

**Outcome: essentially clean. One item retracted, two out-of-scope threads
flagged.**

`officialScore` appears in my notes in only two places
(`research/frieren-pr35-r2-prereg.md:97`, `research/frieren_receipt_ratio.py:41`)
and in both it is characterized as noise. Every "% of score" figure in my
campaign is either a forward prediction from candidate µs through the 0.638
elasticity, or a candidate-vs-candidate contrast on `T` / `S` / `ns`. Restated
on `ns`, the previously score-shaped statements are:

- `research/frieren-pr23-head-region.md:558-568` — score ratio 1.0001 becomes
  **ns +0.0082 %** at n = 1/arm. (The local variables are *named* `*_speedup`,
  which is precisely the trap that invites this error.)
- `research/frieren-pr23-head-region.md:544-550` — caps 400/240/160 become ns
  **−0.083 % / −0.949 % / +0.008 %**.
- `research/frieren-pr23-r2-result.md:141-147` already **refutes** this error
  class explicitly.
- Unchanged, because they were already candidate-side pricings:
  `research/frieren-pr35-result.md:9-16`,
  `research/frieren-pr35-scale-census.md:100-101`, and the "N % of score"
  figures in `research/frieren-host-cpu-budget.md:165,428-429`,
  `research/frieren-pr23-result.md:90,96,305,348,399-401`,
  `research/frieren-pr23-head-region.md:153,162,619,705`.

### 3.1 Retracted

`research/frieren-pr23-r2-result.md:165-177` claimed the PR #12 tip's
`S +0.236 %` regression "is still unexplained and should be reopened". That is
**retracted** in this revision. My own three bit-identical base controls put one
candidate-`S` σ at **0.2603 %** (`research/m5-calibration/`), so +0.236 % is
*below* 1σ. There is no evidence a regression exists. What that observation
needs is replicates, not a mechanism story.

### 3.2 Two threads flagged, not edited (not mine to change)

1. The inherited **0.61 % acceptance bar** and the **0.303 % / 0.243 %** floors
   trace to `research/nezuko-normalised-leaderboard.md` §5.2 with **unaudited
   provenance**. If they were calibrated on `officialScore` spread (my measured
   cv is 0.6353 %), the magnitude is coincidentally close to right but the
   derivation is wrong — and every decision gated on that bar inherits the
   error. Worth an explicit check by whoever owns that file.
2. `research/maple-fern-pr19-first-touch.md:111` builds an argument on the
   paired-ratio structure. Different author; flagging only.

---

## 4. Merge-forward: the deletion-set finding, and a generalized `baseline_advanced` procedure

### 4.1 The merge was necessary

Before merging, `git diff --diff-filter=D --name-only d18ebbb..HEAD` was
**non-empty**: 22 files, including `senpai/check-editable-budget.sh`,
`senpai/validate-assignment-scope.sh`,
`Tests/MLXFastTests/SenpaiOperationalContractTests.swift`, and 15 `research/`
files. That is the same failure mode fern hit — a branch that looks clean by
`git status` but would delete trusted harness files on merge. Merging `d18ebbb`
resolved it cleanly (merge commit `528bc17`, 40 files, +5653/−1873).

After the merge, both checks are what they should be:

- `git diff --stat d18ebbb..HEAD -- Sources Vendor benchmark.json` → exactly two
  files, `Sources/MLXFastModel/LagunaRuntimeModel.swift` and
  `Sources/MLXFastModel/LagunaRuntimeWeights.swift`, **+360 / −17**.
- `git diff --diff-filter=D --name-only d18ebbb..HEAD` → **empty**.

The merge also adopted harness source changes, so **a rebuild is mandatory
before any local timing on this branch.**

### 4.2 The `091e6015` base advance needs no action from me

Confirmed independently of the advisor's own intersection: the span
`eaedee84..091e6015` touches `AGENTS.md`, `README.md`, `TASK.md`, both
`LagunaRuntimeLocalIterate.swift` files (−58 each),
`Tests/MLXFastTests/SenpaiOperationalContractTests.swift` (+155),
`docs/benchmark-window-freeze.md`, `docs/thermal-variance-investigation.md`, and
files under `senpai/` and `research/`. Intersected with `editablePaths`: **empty**.
Both `LagunaRuntimeLocalIterate.swift` files are trusted harness, not submitted
surface. No rebase, no re-baseline, no discarded timing.

### 4.3 The rule I am replacing

My previous heuristic was "a `research/`-only span is safe". That is wrong in
general: it pattern-matches directory names instead of consulting the
authoritative list. The replacement, run on every `baseline_advanced` event:

```python
import json, subprocess
editable = set(json.load(open('benchmark.json'))['editablePaths'])
changed  = subprocess.run(['git', 'diff', '--name-only', '<old>', '<new>'],
                          capture_output=True, text=True).stdout.split()
print(sorted(editable.intersection(changed)))
```

Empty ⇒ accept the new base and keep the existing evidence. Non-empty ⇒ stop
and report exactly which paths moved, before touching any timing.

### 4.4 One thing I will not do

`Tests/MLXFastTests/SenpaiOperationalContractTests.swift` gained 155 lines in
that span. If `swift test --force-resolved-versions` now fails on a contract
assertion I did not write, I will **report it and not fix it** — it is trusted
harness.

---

## 5. Ranked-slot request for deliverable A — asking, not taking

The channel rule is that the ranked path accepts exactly one in-flight
submission per account and all four students share `morganmcg1`; the advisor is
the scheduler. **I have not run `mlxfast submit` and will not without an
explicit grant.** This section is the ask.

The full design is pre-registered in `research/frieren-pr35-r2-prereg.md` at
commit `e2ca0cc`, before any submission. Summary of what a grant would buy:

- **What A measures.** The byte-trading cell of the §5 M4→M5 transfer table,
  currently `unknown`. Only the endpoints are known: DRAM traffic 106 %,
  dispatch overhead 1 %.
- **Pre-registered prediction.** The advisor's arithmetic: 30.61 MB/step at the
  in-situ 651.8 GB/s gives −47 µs against a bandwidth-independent +43 µs, so
  net **−4 µs/step** = 0.09 % of `T` = **+0.06 % of score**.
- **Conversion at the control's operating point.** Inverting the control's
  `ns = 2.544360` at `S = 97.711 ms` gives `norm_prefill_su**0.25 = 1.191410`,
  `norm_decode_su = 2.749990`, `D = 5.050918 ms`, `T = 4.287551 ms`, hence
  **`dT = −6.734558 ms × d ln ns`**. That is 1.6 % off the coefficient I used
  earlier (6.84688) and puts σ(dT) at **±14.2 µs** for one receipt.
- **Honest power.** H_advisor (−4 µs) is **0.28σ** on one receipt, and H_model
  itself predicts −4 ± ≥8 µs, which overlaps both H_null and H_regression. **No
  replication count separates overlapping hypotheses at 3σ.** So A is framed as
  **estimation of `dT_M5` with an interval, not hypothesis testing**, and I will
  report **no p-value for H_advisor**. `dT_M5 = −5 ± 14 µs` is a *successful*
  execution of A, and I want that recorded before the receipt exists rather
  than after.
- **Fixed report form.** Primary `ΔT₅` µs/step with CI, plus `ΔT₅/T₅` %; byte
  term −47.0 ± ~10 µs; inferred fixed cost `C₅ = ΔT₅ + 47.0 µs`;
  `f_fixed = C₅/(43 ± 8) µs`; class rule `ΔT₅ = −B′/BW_eff,₅ + f_fixed·C₄′`,
  valid only where `ΔT₅ ≤ 0`. The scalar τ is demoted to a mix-specific,
  non-transferable footnote — its endpoints are 1.06 and 0.01, relative
  normalization bakes in `T₄/T₅ = 2.0` so a pure fixed cost gets τ = 2.0 by
  arithmetic, and a single net `ΔT₅` under-identifies the pair
  `(−B·v₅, C₅)`.
- **Known systematics.** (i) The 106 % DRAM endpoint with `T₄/T₅ = 2` implies
  `v₅/v₄ = 0.53`, so the byte term would be −58.6 µs rather than the −47.0 µs
  implied by in-situ 651.8 GB/s — a **±20-25 % average-vs-marginal**
  systematic. (ii) "107 % of nominal" hints at counter/SLC attribution.
- **Confounds the unpaired single receipt cannot remove**, enumerated in
  prereg §7.1: between-receipt drift, arm-dependent thermal coupling
  (0.01-0.1 %, material at H_model scale), σ-estimation risk from n = 1 on the
  control side, artifact identity, and flip-inertness risks (a boolean-default
  flip can change inlining, code layout, or Metal function-constant
  specialization at the few-µs scale).
- **Judged on `ns`**, never on `officialScore`.

### 5.1 The one confirmation I need before A is worth a slot

The design uses the advisor's permanent control `c3ce66e` (git commit
`e82d6cf`, submitted 2026-08-05 09:33, `ns = 2.544360`) as the reference arm,
because policy now forbids a receipt carrying its own control arm.

I have verified as much of "the control's scored surface equals my base" as is
possible locally:

- (a) my editable diff vs base is the 2 files / +360 / −17 above, deletion set
  empty;
- (b) the scored editable surface has been frozen since `6f1289a`
  (2026-08-04 21:03 +0200); the later `279b6e2` (2026-08-05 09:30 +0200)
  touched only the two non-editable `LagunaRuntimeLocalIterate.swift` harness
  files, −116 lines;
- (c) the control's own public note (`mlxfast submission-note c3ce66e`,
  10,383 B) states at lines 16-17 that "the final commit of the research branch
  resets those literals to zero, at which point the file is byte-identical to
  the promoted base and the instrument is inert", and its tables at lines
  168-173 report 0 injected decode dispatches, 0 injected prefill dispatches,
  and ~406 dispatches unchanged;
- (d) the PR #27 instrument block is present in the base
  (`d18ebbb:Sources/MLXFastModel/LagunaRuntimeModel.swift:10975-11223`) and in
  my HEAD at 11158-11406, shifted only by my own +217 lines, with no hunk of
  mine entering that range; the injection literals are identical and zero in
  both;
- (e) my diff adds exactly four env reads, all in `LagunaRuntimeWeights.swift`
  (`DARKBLOOM_ATTN_SCALE_NARROW` `:399`, `…_QKV` `:403`, `…_OPROJ` `:406`, all
  default-ON; `…_LOG` `:412`, default-OFF), and three of those *are* the
  mechanism. There is no `DARKBLOOM_SCALE_ALTERNATE` anywhere in `Sources/`.

**Residual gap:** `e82d6cf` is not in my object store, so I cannot diff it. If
that commit was *not* built from the current base's scored surface, the unpaired
design is void and the slot should not be spent on A. That is the single
confirmation I need.

### 5.2 Three asks

1. Confirm `c3ce66e` / `e82d6cf` was built from the current base's scored
   surface.
2. Grant or refuse the ranked slot for A.
3. Say whether to skip A entirely and spend the slot on B once B screens.
   Given H_advisor sits at 0.28σ on one receipt, that is a defensible call and I
   would not argue with it.

---

## 6. What I do next without a slot

Deliverable **B** — the 4-bit lane-major scale plane with a per-row base and an
`0xFF` sentinel escape. It needs no ranked channel: the gate is the 12×512
pure-configuration M4 screen at ≥5σ, plus `max_abs_diff 0`, oracle decode 0..7
exactly 0, `swift test --force-resolved-versions`, and a clean
`--local-submit`. I proceed with B **regardless of A's sign**, because B is a
transaction-count / load-instruction change that a byte-rate model cannot see:
attention-qkvo QMV decode already measures 802.16 MB at 651.8 GB/s = 107 % of
nominal, i.e. cache-assisted. A null on A must not be read as evidence against
B.

**D stays last** and in its own commit, per the sequencing rule: measurement
first, reclamation last. Any evidence B needs from the PR #27 instrument block
gets captured *before* D deletes it.

Standing budget constraint to keep in view: base
`LagunaRuntimeModel.swift` is 508,529 B and my branch is 516,566 B against a
500,000 B contract ceiling, and #35 + #34 sum to 529,917 B, so the two cannot
both merge. D is the unblocking action, not an optional tidy-up.

Host state at the time of writing: `setup.sh` is still fetching safetensors
shards (91 % of 20.1 GiB) on a fresh checkout, so no local timing is possible
yet, and the merge's harness changes force a rebuild before the first
measurement regardless.
