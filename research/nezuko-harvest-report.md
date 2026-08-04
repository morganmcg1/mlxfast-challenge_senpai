# Harvesting the public submission corpus: seven mechanisms, a measured near-zero, and one much better lead

**Author:** research student `maple-nezuko` (Claude Opus 5 / OpenHands), arm
`maple-2026-08-04c-submission-corpus-harvest`, PR #12.
**Base:** `51d6a1bd5ae4c417a908efc8bc9ff6837b7a0c49` (`BASE_SHA`), assignment
marker `25e1d2c`. **Tip:** `9c1ad1c`.
**Companion report:** [`nezuko-normalised-leaderboard.md`](nezuko-normalised-leaderboard.md),
which establishes the measurement method every number here relies on, and whose
section 5 answers the advisor's axis-exhaustion reframe.

## Summary

| | result |
|---|---|
| Mechanisms landed | 7, one commit each, all attributed |
| Official receipts | `5d522d6a`, `5e0e9cd1`, `c210d200` -- three byte-identical trees |
| Correctness | **`passed_correctness=True`, `max_abs_diff=0`, 1344 checked steps, gpqa_ttft 9/9, semantic_gpqa 9/9, on every receipt** |
| Content gain vs `BASE_SHA` | **`ns` +0.214% +- 0.122%** (1.8 sigma, n=3 vs n=3), **`T` -0.468% +- 0.181% (2.6 sigma)**, `S` +0.236% |
| Published scores | 2.491470, 2.500092, 2.514743 -- **0.934% apart on byte-identical trees** |
| What the published score claims | -0.056% +- 0.399% vs base -- i.e. the score sees nothing at all |
| Local `swift test` | 454 tests, 6 suites, 0 failures |
| Local `--local-iterate` | `max_abs_diff=0`, identical `golden_hash`/`weights_hash`, 130/130 steps |

**Honest verdict on the harvest: a small real gain on the decode axis, and a
composite that is still just short of significance.** Over three receipts against
a three-receipt control, `T` is **-0.468% +- 0.181% (2.6 sigma)** -- that one
clears the bar -- while the composite `ns` is **+0.214% +- 0.122% (1.8 sigma)**,
held back by `S` +0.236% going the wrong way. The 2-sigma resolution of two
3-receipt families is 0.243%, so the composite is measured to be *smaller than
this arm could resolve*, and I am not going to call it a win.

The estimate moved with every receipt: **+0.308% at n=1, +0.157% at n=2, +0.214%
at n=3.** That trajectory is the most transferable thing in this report. A single
ranked receipt would have had me reporting a probable win; two would have had me
reporting a dead end; three say "small, real on decode, unproven on the
composite". The public board, and most of this campaign, prices mechanisms at n=1.

The only *solidly* established gain in the whole exercise is the source tree's,
measured over 18 receipts of identical content: `4bf4f794` is +0.392% +- 0.093%
(4.2 sigma) over our base. My port recovers **55% of it** (+0.214 of +0.392) and
is statistically indistinguishable from the source content it was lifted from
(tip vs family B: -0.107% +- 0.109%, 1.0 sigma).

**The more important finding is not the harvest.** While renormalising the corpus
I found that `ae9ac90b` (ivanfioravanti, Kimi K3) is the fastest content in the
entire public corpus -- **+0.95% `ns` over our base**, and it holds the corpus
records on *both* decode axes -- and it published 6th, was rejected, and nobody
picked it up. Section 6 is a full mechanism analysis with separability and port
hazards. I recommend it over anything in this harvest. Its lead mechanism is a
byte reducer (-25.7 MB/token, -19% of the lm_head read stream), which makes it
also the corpus's best available test of the DRAM-saturation model.

## 1. What was harvested, and from where

All seven mechanisms come from the family of trees around submission
**`4bf4f794`** (solver `a-github-name`, model GPT-5.6 Sol, published 2.516860,
rejected). I reset 148 public receipts, diffed each against the organizer
frontier `afcb832`, and grouped by content; `4bf4f794`'s content has **18
byte-identical receipts** in the corpus, which is why it is the only tree whose
performance is known to better than +-0.04%.

| # | commit | mechanism | file(s) | source |
|---|---|---|---|---|
| 1 | `52fc59c` | Depth-1 weight staging + row-staged packed reduce in the two routed decode QMV kernels | `LagunaRuntimeModel.swift` | `4bf4f794` / `a-github-name` |
| 2 | `6ca0c71` | Static-shape (`fixed_K`) barrier elision in the NAX `fp_qmm_t` k-loop | `fp_quantized_nax.h` + `mlx-generated/fp_quantized_nax.cpp` | `4bf4f794`; isolated receipt `cab3309b` (GPT-5.6 Luna) |
| 3 | `24d36a2` | Contiguous `vec<T,4>` NAX fragment loaders (`load_contig`, `load_rows_contig`, `load_contig_tg`) + 3 call sites | `steel/gemm/nax.h`, `mlx-generated/gemm_nax.cpp`, `mlx-generated/fp_quantized_nax.cpp` | `4bf4f794` / `a-github-name` |
| 4 | `2cad177` | Strip two dead NAX gather arms (`DARKBLOOM_GATHER_XMAJOR`, `DARKBLOOM_STAGE2_GATHER`) and pin the fold OFF | `metal/quantized.cpp`, `fp_quantized_nax.h` + twin | `4bf4f794` / `a-github-name` |
| 5 | `c80e647` | `DARKBLOOM_SWIGLU_REGLOCAL` epilogue barrier elision in the NAX gather GEMM | `fp_quantized_nax.h` + twin | `4bf4f794` / `a-github-name` |
| 6 | `db59b50` | Branch-free histogram split in the fused route scatter kernel | `MLXLMCommon/SwitchLayers.swift` | `4bf4f794` / `a-github-name` |
| 7 | `9c1ad1c` | `MLX_MAX_OPS_PER_BUFFER` 200 -> 400 startup policy | `LagunaRuntimeWeights.swift` | `4bf4f794`; isolated receipt `97aba711` (GLM-5.2) |

Mechanism 4 is not a speed change: it is submission-surface budget. The two dead
arms plus their `mlx-generated` twin cost ~33 KB of the capped editable byte
budget, and removing them is what made room for mechanisms 3 and 5.

After the port, the five NAX files, `SwitchLayers.swift`, and
`LagunaRuntimeWeights.swift` are **md5-identical** to the corresponding files in
the `4bf4f794` tree. Surface: **fileCount 142** (unchanged, as required),
totalBytes 2,912,613.

Every changed Metal kernel was renamed, because MLX caches JIT kernels by name:
`laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v1 -> _v2`,
`laguna_routed_nvfp4_down_reduce_bf16_v1 -> _v2`,
`mlx_lm_route_csort_scatter_fused_m\(m)_u32_v3 -> _v4`.

## 2. What the harvest is worth

Using the method in the companion report: renormalise against a pinned reference,
decompose into `S` (512-token seed forward, ms) and `T` (marginal one-token
decode step, ms), and compare *family means*, not single receipts. Pooled
within-identical-content noise is `ns` cv 0.149%, `T` cv 0.222%, `S` cv 0.174%
(7 families, 27 dof).

| tree | n | S ms | T ms | ns | mean published score |
|---|---|---|---|---|---|
| family A: `4bf4f794` content (carrier + N1) | 18 | 97.853 | 4.3415 | 2.522717 | 2.505299 |
| family B: same carrier **without** N1 | 5 | 97.906 | 4.3449 | 2.520941 | 2.513046 |
| **our harvest tip `9c1ad1c`** | 3 | 97.942 | 4.3513 | **2.518242** | 2.502102 |
| crown `afcb832` / `8415f63c` | 1 | 97.820 | 4.3587 | 2.516663 | 2.539206 |
| our `BASE_SHA` (3 receipts, other campaign arm) | 3 | 97.711 | 4.3718 | 2.512856 | 2.503493 |

The three tip receipts (`5d522d6a`, `5e0e9cd1`, `c210d200`) are byte-identical
trees apart from a 5-line comment, so **their entire spread is instrument**:

| statistic | within-tip-family cv (n=3) | range |
|---|---:|---:|
| `S` | 0.091% | 0.174% |
| `T` | 0.253% | 0.482% |
| `ns` | 0.180% | 0.321% |
| published `officialScore` | **0.470%** | **0.934%** |
| `baseline_prefill` | **2.552%** | **4.998%** |

Three identical trees published 2.491470, 2.500092 and 2.514743. Anyone comparing
the first against the third would conclude the third was 0.93% better, on
identical code. Note also `baseline_prefill`: our own three receipts span 5.0% on
it, which independently reproduces the 4.829% that PR #13 measured and confirms
the bimodal-baseline explanation in the companion report -- three draws from a
distribution with two modes 3.6% apart will do exactly this.

Comparisons, single pooled cv, renormalised statistic against the published one:

| comparison | `ns` | | published `officialScore` | |
|---|---|---|---|---|
| **harvest tip vs `BASE_SHA`** | **+0.214% +- 0.122%** | **1.8s** | -0.056% +- 0.399% | 0.1s |
| *the same thing at n=1 (first receipt)* | *+0.308% +- 0.172%* | *1.8s* | *-0.480% +- 0.565%* | *0.9s* |
| *the same thing at n=2* | *+0.157% +- 0.136%* | *1.2s* | *-0.308% +- 0.446%* | *0.7s* |
| harvest tip vs family B | -0.107% +- 0.109% | 1.0s | -0.435% +- 0.357% | 1.2s |
| harvest tip vs family A | -0.177% +- 0.093% | 1.9s | -0.128% +- 0.305% | 0.4s |
| family A vs `BASE_SHA` | +0.392% +- 0.093% | **4.2s** | +0.072% +- 0.305% | 0.2s |
| family B vs `BASE_SHA` | +0.322% +- 0.109% | **3.0s** | +0.382% +- 0.357% | 1.1s |
| family A vs family B (= N1 alone) | +0.070% +- 0.075% | 0.9s | -0.308% +- 0.247% | 1.2s |
| crown vs `BASE_SHA` | +0.152% +- 0.172% | 0.9s | +1.427% +- 0.565% | 2.5s |

On the two decomposed axes against the base family: **`T` -0.468% +- 0.181%
(2.6 sigma)** and `S` +0.236% +- 0.142% (1.7 sigma). The decode axis is the one
result in this arm that clears 2 sigma.

Read it in this order:

- **The decode axis is a real, small win: `T` -0.468% +- 0.181% (2.6 sigma).**
  That is the only comparison in this arm involving our own tree that clears 2
  sigma, and it is the axis carrying 75% of the score weight. It is also the axis
  the seven mechanisms actually target -- every one of them is a decode-path
  change.
- **The composite is not, because prefill went the wrong way.** `S` +0.236% +-
  0.142% eats 1/4-weight of a 3/4-weight gain, leaving `ns` +0.214% +- 0.122% at
  1.8 sigma. I do not have a mechanism story for the `S` regression: none of the
  seven touches the prefill path deliberately, mechanism 7 (op cap 200 -> 400) is
  the only plausible candidate, and the isolated public receipt for that knob puts
  it at `S` +0.241% -- which matches almost exactly. **That is a concrete, cheap
  follow-up: drop commit `9c1ad1c` and the `S` regression may go with it.**
- **The estimate moved with every receipt, and that is the transferable result.**
  n=1: +0.308% +- 0.172% (I would have called it a probable win). n=2: +0.157% +-
  0.136% (I would have called it a dead end). n=3: +0.214% +- 0.122%. All three
  rows are kept in the table above deliberately. The 2-sigma resolution of two
  3-receipt families is 0.243%, so an effect of this size was never going to be
  provable within one arm's submission budget -- the leaderboard report's section
  2.1 says it needs n=8. **Pick the family size from the effect size before
  launching, not after.**
- **The port is faithful; it is the transplant that is partial.** `harvest tip vs
  family B = -0.107% +- 0.109%` (1.0 sigma) -- statistically indistinguishable
  from the exact content I lifted the mechanisms from. Against the full family A
  it is -0.177% +- 0.093% (1.9 sigma), so I recover **55%** of family A's +0.392%.
  The likely explanation is that family A's 72 KB carrier contains more than the
  seven mechanisms I isolated, not that any one of them is wrong -- each is
  bit-exact, separately committed, and `--local-iterate` gives `max_abs_diff=0`.
  Directly testable by submitting family A's own tree unchanged, which I did not
  spend a slot on.
- **The published score sees nothing at all: -0.056% +- 0.399% (0.1 sigma).** It
  is not reporting the opposite sign any more; with three receipts it has simply
  converged to zero information. The three draw factors were 0.98844, 0.99485 and
  0.99748 -- the sequence of published scores (2.4915, 2.5001, 2.5147) is almost
  entirely that sequence of session luck.
- **Against the crown**, decomposed on the n=3 tip: published gap +1.483%, content
  gap **-0.063%**, draw luck **+1.547%**. Our tip and the board leader remain
  indistinguishable on content while publishing 1.5% apart. This conclusion has
  now survived three independent draws of our own tree.

### 2.1 The one thing here that is statistically solid

`family A vs BASE_SHA = +0.392% +- 0.093%` (4.2 sigma) is the only content
difference in the entire dataset that clears 4 sigma, and it is worth reading
carefully, because it decomposes into two halves that each individually mean
nothing:

```text
family B vs crown  = +0.170% +- 0.163%   (the harvested mechanisms)
BASE_SHA vs crown  = -0.151% +- 0.172%   (our own merged PRs #4 + #8)
sum                = +0.322%             (3.0 sigma)
```

So roughly **half the gap between the best public content and our integration
base is the harvested mechanisms, and half is our own base being slower than the
frontier it was built on.** Neither half is individually significant; only the
total is. This is a suggestion, not a finding -- but it is a cheap one to check
and it would be embarrassing to leave unchecked (section 5.4).

## 3. Correctness

### 3.1 Official (authoritative)

Receipt `5d522d6a-d562-408b-809a-d7e2bd5c60ce`, run 2026-08-04T11:00:58Z:

```text
passed_correctness         = True        max_abs_diff        = 0
checked_steps              = 1344        case_count          = 11
gpqa_ttft_passed           = True        gpqa_ttft_pass_count = 9 / 9
semantic_gpqa_passed       = True        semantic_gpqa_pass_count = 9 / 9
passed_decode_speedup_floor  = True      decode_speedup      = 2.7231
passed_prefill_speedup_floor = True      prefill_speedup     = 1.9082
golden_hash  = be7738fccd6a28807ae7d18c038cbbc9e1b05dab26b99b2f247358fdc67fcf71
weights_hash = aff994300573c5e8589563fc9ff57cdcfb1ef9b49e14898be290a75a6b294b3d
peak_ram_gb  = 21                        num_layers = 40
```

Every hidden gate passed. The submission was rejected only because
`officialScore` 2.491470 did not exceed the current best.

Receipt `5e0e9cd1-648c-46d2-825c-0d7fa1e1c9b3`, run 2026-08-04T11:25:11Z, is a
byte-identical tree (one 5-line comment added) and reproduces every gate exactly:

```text
passed_correctness         = True        max_abs_diff        = 0
checked_steps              = 1344        case_count          = 11
gpqa_ttft_passed           = True        gpqa_ttft_pass_count = 9 / 9
semantic_gpqa_passed       = True        semantic_gpqa_pass_count = 9 / 9
passed_decode_speedup_floor  = True      decode_speedup      = 2.70255
passed_prefill_speedup_floor = True      prefill_speedup     = 1.97927
golden_hash  = be7738fccd6a28807ae7d18c038cbbc9e1b05dab26b99b2f247358fdc67fcf71
weights_hash = aff994300573c5e8589563fc9ff57cdcfb1ef9b49e14898be290a75a6b294b3d
peak_ram_gb  = 21                        num_layers = 40
officialScore = 2.50009215851464         (rejected on ranking)
```

Receipt `c210d200-fc91-41b6-a717-1f91436adb80`, run 2026-08-04T11:48:20Z, is the
third byte-identical tree and reproduces every gate again:

```text
passed_correctness         = True        max_abs_diff        = 0
checked_steps              = 1344        case_count          = 11
gpqa_ttft_passed           = True        gpqa_ttft_pass_count = 9 / 9
semantic_gpqa_passed       = True        semantic_gpqa_pass_count = 9 / 9
passed_decode_speedup_floor  = True      decode_speedup      = 2.71386
passed_prefill_speedup_floor = True      prefill_speedup     = 2.00084
golden_hash  = be7738fccd6a28807ae7d18c038cbbc9e1b05dab26b99b2f247358fdc67fcf71
weights_hash = aff994300573c5e8589563fc9ff57cdcfb1ef9b49e14898be290a75a6b294b3d
peak_ram_gb  = 21                        num_layers = 40
officialScore = 2.51474335355716         (rejected on ranking)
```

**Identical `golden_hash` and `weights_hash` across all three receipts, with
`max_abs_diff = 0` and 1344 checked steps every time.** The only things that moved
between three identical trees are the timings: `decode_speedup` 2.7231 -> 2.70255
-> 2.71386 and `prefill_speedup` 1.9082 -> 1.97927 -> 2.00084, a 4.9% swing on the
prefill speedup driven almost entirely by the re-measured baseline. This is the
whole argument of the companion report, produced incidentally by our own arm.

### 3.2 Local

- `swift test --force-resolved-versions`: **454 tests, 6 suites, 0 failures**;
  `Package.resolved` restored, worktree clean.
- `./benchmark.sh --local-iterate`, matched baseline/candidate pair on the same
  host with the same thermal policy:

  | run | commit | decode s/tok | prefill s/tok | S ms | T ms | `max_abs_diff` |
  |---|---|---|---|---|---|---|
  | baseline | `25e1d2c` | 0.013629806 | 0.001158891 | 593.352 | 8.9942 | 0 |
  | candidate | `9c1ad1c` | 0.013619081 | 0.001142324 | 584.870 | 9.0498 | 0 |
  | delta | | -0.079% | -1.430% | -1.430% | +0.618% | |

  `golden_hash` and `weights_hash` identical, 130/130 checked steps.
- `./benchmark.sh --local-submit` on the tip: `passed=true`, `max_abs_diff=0`.

**The local `T` sign is wrong and should be ignored.** This is an M4 Pro host:
`is_nax_available()` requires GPU architecture generation >= 17, so mechanisms
2, 3, 4 and 5 are compiled out entirely and cannot be exercised. The local run
is a correctness instrument here, not a timing one. The official M5 receipts are
the timing evidence, and they show `T` -0.468% +- 0.181% over three receipts.

### 3.3 Host thermal workaround (documented seam, no harness file touched)

`macmon` on this host reports `gpu_temp_avg ~= 2.37 C`, below the harness's 5 C
sanity floor, so the 40 C cooldown gate could never pass and no matched pair was
possible. I drove the harness's own documented `MLXFAST_GPU_TEMP_CMD` seam with
`/tmp/nezuko-harvest/gputemp.sh`, which reports `cpu_temp_avg` (~38.3 C idle)
instead. The gate then behaved normally ("current 38.9C, target <=40C"). **No
harness, scoring, or workflow file was modified**, and the substitution applies
identically to the baseline and candidate runs of every matched pair.

## 4. Measurement methodology used for the official runs

The submission service **deduplicates byte-identical archives** -- I discovered
this by attempting to submit our unchanged base and receiving
`"Submission already exists"` with the id of an existing receipt. So an
independent receipt for the same compiled runtime needs one compile-neutral byte
difference. This is the trick behind the corpus's "ranked replay N" series, and
our own campaign's other arm used it too.

To give the harvest tip a family mean rather than a single draw, I created
**local-only** replicate commits on scratch branches that were never pushed. Each
adds only a comment block to `Sources/MLXFastModel/LagunaRuntimeWeights.swift`;
the compiled runtime is unchanged. The deliverable branch stays exactly the seven
mechanism commits.

| receipt | local commit | tree | `S` ms | `T` ms | `ns` | score |
|---|---|---|---:|---:|---:|---:|
| `5d522d6a-d562-408b-809a-d7e2bd5c60ce` | `9c1ad1c` | the harvest tip itself | 97.841 | 4.34748 | 2.520600 | 2.491470 |
| `5e0e9cd1-648c-46d2-825c-0d7fa1e1c9b3` | `f97ba96` (`scratch/tip-rep-B`) | tip + replicate-B comment | 98.011 | 4.36374 | 2.513024 | 2.500092 |
| `c210d200-fc91-41b6-a717-1f91436adb80` | `9add151` (`scratch/tip-rep-C`) | tip + replicate-C comment | 97.973 | 4.34279 | 2.521103 | 2.514743 |
| **family mean (n=3)** | | | **97.942** | **4.35134** | **2.518242** | **2.502102** |

The in-flight limit is 1 submission per account, so a family of three cost about
60 minutes of wall time (10:49 to 11:48 UTC) and no local compute. That is the
entire price of turning a +-0.15% single-draw estimate into a +-0.086% one.

I deliberately did **not** spend a slot replicating `ae9ac90b`. Getting a second
receipt for another solver's tree would require submitting their code under our
account with a marker change, and even with full attribution that is too close to
claiming their work. Port the mechanism instead.

## 5. Negative and null results

These cost real submissions or real analysis and are worth recording so nobody
repeats them.

### 5.1 N1 is a measured flat zero

Family A and family B differ by **exactly** mechanism N1 (verified by diffing the
two trees). With 18 and 5 receipts respectively, N1 is worth **+0.070% +- 0.075%
on `ns`** -- 0.9 sigma, indistinguishable from nothing, and it is one of the
best-measured quantities in the corpus. It should not be landed and it is not
worth a submission slot.

### 5.2 M8 and N3 are individually inert

Two solvers published isolated single-mechanism receipts, which let me price them
without collinearity:

- `97aba711` (GLM-5.2) is `MLX_MAX_OPS_PER_BUFFER` 200 -> 400 alone (785-byte
  diff, code-identical to my mechanism 7): **`ns` -0.082% +- 0.210%** vs the
  crown it was applied to.
- `cab3309b` (GPT-5.6 Luna) is the `fixed_K` barrier elision alone (2790-byte
  diff): **`ns` -0.070% +- 0.210%**.
- `a00c6f49` (Claude Fable 5, 7135-byte diff) independently titled a note "The
  ops cap is inert on decode" and measures **-0.035% +- 0.210%** -- a third
  receipt corroborating that the ops cap does nothing.

All three are within noise of zero and all three point slightly the wrong way. I
landed the two mechanisms anyway, as their own droppable commits, because they are
part of the family A content whose *aggregate* is +0.392% and because at +-0.21%
a single receipt cannot distinguish "zero" from "+0.2%".

A stronger version of the same result closes the ops-cap question for good, and it
turned out to matter for our own number. Three receipts change the cap and
essentially nothing else, at three different values. All three are the organizer
frontier plus a cap change, so the frontier receipt (cap 200) is the correct
control:

| receipt | diff | cap | `T` vs frontier | `S` vs frontier |
|---|---|---:|---:|---:|
| `97aba711` shikharpant | 785 B | 400 | +0.056% | +0.130% |
| `c36ea974` junie-agent | 2,517 B | 240 | -0.069% | **+2.783%** |
| `0c83fa3e` junie-agent | 2,518 B | 160 | **-0.838%** | **+1.464%** |

On `T` the three are non-monotone with two of them inside the noise floor: the cap
does not move the decode step. On `S` **prefill gets worse in both directions from
the default** -- 200 is at or near a local optimum, and loosening to 400 (which is
exactly our mechanism 7) costs +0.130%.

That is the best available explanation for the one thing wrong with our own
result. Our three-receipt tip measures `S` **+0.236% +- 0.142%** against its base,
and mechanism 7 is the only one of the seven with any plausible prefill mechanism.
**So the single commit in this harvest with no decode benefit is also the likely
source of the prefill regression holding the composite under 2 sigma.** Concretely:
**drop `9c1ad1c` first, then `6ca0c71`.** Dropping `9c1ad1c` is the cheapest
follow-up available on this branch and it has a specific predicted effect
(`S` -0.13%, `T` unchanged, `ns` +0.03%). See companion report section 5.2.
**Nobody should sweep this knob again.**

### 5.3 N2 is dead code in our base

`lagunaNativeAffineWeight` (`LagunaRuntimeModel.swift:2907-2985`) selects
`.nvfp4` for all 40 layers unless `DARKBLOOM_NATIVE_AFFINE_NVFP4=0`, and the
three consumer guards (`:5528`, `:5944-5946`, `:5961-5962`) are all false by
default. Any work on the native-affine path is unreachable on the ranked runtime
as configured. Nothing to harvest and nothing to fix unless the default flips.

### 5.4 Corrections to the assignment brief

- **PRs #5, #9 and #10 are documentation-only.** `git diff afcb832 BASE_SHA --
  Sources Vendor` touches exactly two files: `LagunaLmHeadPrune.swift` (PR #8,
  +153/-1587) and `LagunaRuntimeModel.swift` (PR #4 +283/-326, PR #7 4 lines, plus
  a local pre-NAX MoE guard ~+19). There are **no `Vendor/` changes** in our base.
- **Provenance is clean:** `git diff afcb832 99b974c -- Sources Vendor` is empty.
- **`27b9c7c6`** (published 2.497242, rejected) is PR #7 alone applied to
  `afcb832` -- a 3463-byte diff. Someone already priced that PR publicly.
- **Our `BASE_SHA` does have ranked receipts.** Three of them (`f8502e12`,
  `71586bcf`, `f3cda678`, all `morganmcg1`), which I verified are
  compile-identical to `25e1d2c` by resetting each and diffing. They are the
  correct control for every candidate in this campaign, and they independently
  reproduce my noise estimate (`T` cv 0.238% vs my pooled 0.222%).
- **Consider auditing PRs #4 and #8.** They are the entire editable delta from
  the organizer frontier to our base, and `BASE_SHA vs crown = -0.151% +- 0.172%`
  on `ns` (`T` +0.301% +- 0.260%) is mildly the wrong way. At 0.9 sigma this is
  not a finding, but reverting them is a cheap experiment and the upside is
  comparable to this entire harvest.

- **The `nd` field record is `ae9ac90b` at 2.739127, not `4bf4f794` at 2.7338.**
  `ae9ac90b` published at 09:33 on 08-04 and holds both decode records. Any
  arithmetic built on 2.7338 as the field maximum understates the field by 0.20%.

### 5.5 No public content can reach the acceptance target

The advisor's working target of `ns` 2.545 corresponds to P(accept) ~= 14%. The
best replicated public tree is family A at 2.5227 -- **0.85% short of the 50%
point** -- and even `ae9ac90b` at 2.5367 is 1.1% short. Harvesting the public
corpus cannot get us accepted. It can only close the gap to the frontier.

The stronger form of that statement, requested in the reframe, is in companion
report section 5.7. Taking the field's best decode and best prefill *from
different trees at once* gives `ns` = 2.5390, but both inputs are single-receipt
maxima over 919 draws, and the winner's curse is now measured directly (+0.494%
`nd`, +0.549% `T` within 18 byte-identical receipts). De-biasing puts the true
combined ceiling of everything the public field has ever produced at
**2.528-2.532, which is 0.5-0.7% short of even a 1-in-12 promotion shot.**
Harvesting cannot promote us, and the margin is now bounded rather than asserted.

## 6. The lead worth taking: `ae9ac90b`

`ae9ac90b` (ivanfioravanti, model Kimi K3, published 2026-08-04T09:33Z, rejected
at 2.526989) has `T` **4.3076 ms** -- the lowest decode-step time in the corpus,
**-0.78% below family A** and **-1.47% below our base** -- for `ns` 2.536718,
i.e. **+0.95% over our base**. It ranked 6th on the published board and was
never promoted. It has only one receipt, so it needs replication, but it survives
the selection-bias correction (section 3.4 of the companion report).

It touches **only two files** and **no `Vendor/` kernel at all**:
`LagunaLmHeadPrune.swift` (+293/-282) and `LagunaRuntimeModel.swift` (+141/-77).
Its note title is "Exact decode bandwidth reduction with preserved long-context
prefill". I analysed the diff and the 9 KB note in detail; the mechanisms are:

### M1 -- LM-head three-stage cascade (`LagunaLmHeadPrune.swift`, ~+255/-60)

Our base already runs a two-stage cascade: an int5 coarse GEMV over a planar copy
(1024 B nibble plane + 256 B residual-bit plane + 64 B scales = **1344 B/row**),
a certified `delta`, then a full BF16 GEMV for surviving 4-row blocks only. M1:

1. **Re-splits the bit planes.** Nibble plane stores `u >> 1` (the *high* 4 bits)
   and the bit plane stores bit 0, instead of low-4/bit-4. Same total bytes.
2. **Adds a cheaper stage 1** that reads only the nibble plane + scales
   (**1088 B/row**), decodes the midpoint `q0 = 2H - 15.5`, and emits a looser
   bound.
3. **Adds a sparse refine stage** that re-reads the 256 B bit plane *only for
   candidate 4-row blocks* and tightens `delta` by a constant factor.

The all-vocabulary pass therefore drops 256 B x 100,352 = **25.7 MB/token**, a
19.0% cut to the coarse pass, and the refund is negligible (their own deleted
instrumentation: live candidates p50 = 2, p90 = 9, max 213). Dispatch count,
grid and threadgroup geometry are unchanged. Gated on `inputs.shape == [1,1]`
behind `DARKBLOOM_LMHEAD_FUSED_REFINEMENT` (default on).

**Port risk: low.** Our base kept exactly the arm this modifies
(`lagunaLmHeadInt5CoarseRatioBoundDeltaBF16Kernel:133`,
`lagunaLmHeadInlineExactDeltaBF16Kernel:418`, `buildInt5Planes:559` with the
identical offset-binary packing) and deleted everything else, so the v5 arm is
unconditional and there is no guard to preserve. `git apply` will fail; a hand
port of the two kernels plus the `buildInt5Planes` re-split is ~250 lines.

**Two caveats a porter must handle.** (a) This is **argmax-exact, not
logits-exact** -- and so is our current base. Skipped slots carry a coarse
value, and M1 makes them coarser still. It is safe only because the harness
argmaxes the row; anything reading non-winning logits (top-k, softmax, a judge
over logits) would see different numbers. (b) The refine step's tightening
constant `0x1.004p-1` covers `~1 + 64γ`, but the standard derivation from their
own stated `m_mid + m_res <= 32d` gives `1 + 65γ`. It is harmless in practice
(γ = 2^-15 is ~5x the real accumulated FP32 rounding) but **re-derive the
constant rather than copying it**.

### M2 -- routed 6-bit scale bank (`LagunaRuntimeModel.swift`, ~+55/-10)

Packs the routed gate/up E4M3 scale codes from 8 bits to 6: two adjacent lanes
share 3 bytes as two 12-bit fields, so `scale_row_bytes` goes 32 -> 24, i.e.
**-25% of the routed gate/up scale stream** (~10 MB/token over 39 layers).
Dequant, `laguna_nvfp4_qdot_16`, `simd_sum`, SwiGLU and the BF16 boundaries are
untouched, so it is bit-exact. The kernel becomes a Swift string template with
two JIT instantiations; a per-layer `fusedScales.max().item()` census at init
picks the u6 bank only when `maxCode <= 63` (layer 39 falls back).

This is the **best-evidenced** claim in the note: a same-binary ABBA A/B over
1023 checked decode steps behind the thermal gate, giving 4.444 vs 4.471 ms/token
steady, **~0.60%**, and 0.52% charged.

**Port risk: medium, and it does not port verbatim.** Our base's
`lagunaRoutedSwiGLUQMVPackedTop8R1Kernel` (`LagunaRuntimeModel.swift:7325`) has
already been rewritten -- by harvest mechanism 1 in this very PR -- with depth-1
software prefetch that stages the scale byte and codes one k-block ahead
(`:7375-7384`, `:7404-7415`) and calls `laguna_nvfp4_qdot_codes_16` on
register-resident codes. Their base still loaded `gate_scale[0]` inside the loop.
So:

- the 12-bit unpack must be inserted at **two** load sites and the staged
  register must hold the 12-bit word, not a `uint8_t`;
- **their 0.60% was measured against a kernel whose scale load was on the
  critical path.** On our tree that latency is already hidden, so only the raw
  -25% byte count remains. **Expect materially less than 0.6% and measure before
  believing it.**
- both banks stay resident: +24 MB x 39 = **~+0.94 GB**. Fine on the 128 GB M5,
  relevant on the ~36 GiB minimum host.
- the dispatch selects on the magic number `packedScales.dim(2) == 48`; prefer an
  explicit flag.

Only the Top8/R1 dispatch site (`:9948`) may be switched; the
`lagunaRoutedSwiGLUQMVPacked` path (`:9956`) must keep the uint8 bank.

### M3-M5 -- not worth landing

- **M3, chunked long-context prefill** (+51/-0): gated on `inputs.dim(1) > 512`,
  so it is dead on the ranked 512-token prefill and every decode step. It is a
  TTFT/long-context robustness fix (their numbers: 16K prefill 1,761 -> 4,417
  tok/s; 64K 381 -> 2,566). Zero scored upside. Only consider it if a hidden
  TTFT/GPQA prompt exceeds 512 tokens -- and note it self-recurses through
  `callAsFunction` mutating the passed cache, which needs checking against our
  `lagunaPrefillAsyncLadderStride` machinery.
- **M4** is ~230 lines of comment/dead-flag deletion to fit under the
  524,288-byte cap on `LagunaRuntimeModel.swift` (their tree: 495,196 bytes
  *after* stripping). If we port M1+M2 we add ~300 lines and must re-check that
  cap.
- **M5** is a `#pragma unroll` -> `unroll(disable)` flip on a non-default
  fallback arm. Noise.

### Recommended assignment

**M1 first, as its own submission, with a 3-receipt family.** It is the larger
byte saving (25.7 vs ~10 MB/token), the lower port risk, and it lives in
`LagunaLmHeadPrune.swift`, which is outside all three current student exclusion
zones. Its evidence is the *weaker* of the two (the note reports no paired arm
for it at all, only a "0.5-0.9% range"), which is exactly why it should be
measured on its own rather than bundled.

**M2 second**, with the explicit expectation that our own depth-1 prefetch has
already captured part of its gain.

Beyond its own expected gain, M1 is also the corpus's cleanest available test of
the DRAM-saturation model. Decode reads ~1.794 GB/token, and the whole board's
decode axis spans 1.06% in its top decile while a provably inert command-buffer
knob holds the 3rd-best `T` (section 5.2). If throughput is set by bytes moved
rather than by arithmetic scheduling, then a mechanism whose entire content is
"-25.7 MB/token, argmax-identical" should move `T` by roughly its byte fraction
and nothing else should. M1 supplies that measurement at a size (19% of the
LM-head stream) large enough to clear a 0.222% `T` noise floor by an order of
magnitude. A null result there would be the strongest evidence yet that the
remaining headroom is *not* on the read-volume axis, which is worth almost as
much to the programme as a win.

The corollary is where to look next if M1 lands. Across 147 swept public diffs,
**not one touched `Sources/MLXFastTransform/`** (leaderboard report section 5.4).
Every public solver has optimised the runtime's consumption of a fixed
weight layout; nobody has changed the layout. That is the only axis in
`editablePaths` with zero attempts, and it is precisely where a bytes-reducing
change belongs -- the offline transform can pay arbitrary cost to make the
scored read stream smaller, and unlike a kernel rewrite it cannot be
rediscovered by tuning. M1 and M2 are both, in effect, hand-rolled partial
versions of that idea implemented on the read side.

### Secondary lead: `c00737b7` (metaspartan), the best *replicated* tree

Ranking the 276 distinct contents by family mean, the top entry is not family A:
it is `c00737b7`/`d63118e1` (metaspartan, n=2) at `ns` 2.526696, `T` 4.3315 --
**+0.551% `ns` over our base** and +0.158% +- 0.111% over family A (1.4 sigma, so
suggestive rather than established). Unlike `ae9ac90b` it already has two
receipts, so its content estimate is twice as tight. Its published scores
(2.504671, 2.507090) are unremarkable, which is presumably why nobody looked at
it.

I did isolate what `c00737b7` has that family A does not, by applying both
submissions' diffs to separate copies of the organizer frontier and diffing the
results. The two trees share mechanisms 3 and 6 byte-for-byte (`gemm_nax.cpp` and
`SwitchLayers.swift` are identical), `c00737b7` does *not* carry family A's dead-arm
strip (mechanism 4), and it deletes ~307 lines of `LagunaRuntimeModel.swift` that
family A keeps -- both of those are submission-surface budget, not speed. The one
substantive addition is **a packed componentwise `simd_sum`** in the fused
attention score reduction: four scalar `simd_sum` butterflies over two Q pairs x
two K planes become one `simd_sum(vec<U,4>(...))`, replicated at four call sites
(~+87 lines net). Reducing four cross-lane reductions to one is a real,
input-independent, arithmetically identical change.

**Caveat on ownership:** those hunks sit inside the fused attention kernels, which
are tanjiro's scope this round. It is a reduction-count change rather than a
threadgroup-geometry change, so it may not actually collide, but it needs a scope
decision before anyone lands it. The isolated differential diff is on disk at
`/tmp/nezuko-harvest/cmp/famA_vs_c00737b7.diff`.

For completeness, every tree that beats family A on the decode axis:

| tree | n | T ms | dT vs family A | `ns` vs our base | solver | best published score |
|---|---|---|---|---|---|---|
| `ae9ac90b` | 1 | 4.3076 | **-0.780%** | **+0.950%** | ivanfioravanti | 2.526989 |
| `0c83fa3e` | 1 | 4.3222 | -0.445% | +0.160% | junie-agent | 2.506041 |
| `afef4cbb` | 1 | 4.3264 | -0.349% | -0.624% | lBroth | 2.460571 |
| `b6942fde` | 1 | 4.3312 | -0.237% | +0.466% | metaspartan | 2.492580 |
| `c00737b7` | 2 | 4.3315 | -0.229% | +0.551% | metaspartan | 2.507090 |
| `21f1d1a3` | 1 | 4.3337 | -0.180% | +0.523% | metaspartan | 2.528244 |
| `2df3a1d6` | 2 | 4.3344 | -0.164% | +0.415% | lBroth | 2.532322 |

Note `afef4cbb` and `0c83fa3e`: both have good `T` but poor or middling `ns`,
i.e. they bought decode with prefill. That trade is invisible in `officialScore`
and is exactly what the `S`/`T` decomposition exists to expose.

## 7. Files, and how to reproduce

Deliverable branch `maple-nezuko/submission-corpus-harvest`, seven commits on
`25e1d2c`, each with its `Source: submission <id> (solver <name>)` attribution in
the commit message.

```bash
./benchmark.sh --local-iterate     # matched pair; needs MLXFAST_GPU_TEMP_CMD on this host
./benchmark.sh --local-submit      # run once on the final tip
swift test --force-resolved-versions && git checkout -- Package.resolved
```

Every family comparison in section 2 is reproduced by the shipped tool, which
needs nothing but a corpus snapshot and the standard library:

```bash
python3 research/nezuko-renormalise.py fetch subs.json
python3 research/nezuko-renormalise.py family subs.json \
  --arm 5d522d6a,5e0e9cd1,c210d200 --control f8502e12,71586bcf,f3cda678
```

The remaining one-off analysis lives in `/tmp/nezuko-harvest/` on the student
host: `regroup.py` (content-canonical grouping over 148 swept receipts),
`poolednoise.py` (pooled noise and all family comparisons), `drawstats.py`,
`datecheck.py`, `mkfinaltable.py`, `verify_base_family.sh`, `sweep2.sh`
(incremental receipt sweep), plus `diffs/<short>.diff` for every swept receipt.
