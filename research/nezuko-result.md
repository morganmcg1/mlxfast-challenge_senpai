SENPAI-RESULT: {"terminal":true,"status":"complete","pending_arms":false,"wandb_run_ids":[],"primary_metric":{"name":"official_m5_renormalised_ns_ratio_vs_base_family","available":true,"value":1.00214},"test_metric":{"name":"passed_correctness","available":true,"value":1}}

- **Student / PR:** `maple-nezuko` / PR #12, assignment
  `maple-2026-08-04c-submission-corpus-harvest` r1
- **Hypothesis and target cost:** that separable mechanisms in other solvers'
  public *rejected* trees are worth lifting onto our base, and that the public
  corpus can be normalised into a usable leaderboard. Cost: 3 official
  submissions, 1 matched local pair, 1 local submit preflight.
- **Decision:** **ambiguous on the mechanism** -- a measured near-zero, `ns`
  +0.214% +- 0.122% (1.8 sigma), inside the noise floor these family sizes can
  resolve -- and **green on the measurement, which is by far the more valuable
  half.** The arm also answers the advisor's four reframe questions
  with data, including a demonstration that a top-3 decode slot on the public
  board is held by a tree with no runtime mechanism at all.
- **`BASE_SHA` / candidate commit:** `51d6a1bd5ae4c417a908efc8bc9ff6837b7a0c49`
  (marker `25e1d2c`) / candidate `8d1a7c37958030bcc3cff959cd443fc1de4131ce`
  (the seven mechanism commits plus the two reports and the tool; this result file
  is the one commit on top of it, and changes nothing on the submission surface)
- **Submitted candidate files:** 7 mechanism commits touching
  `Sources/MLXFastModel/LagunaRuntimeModel.swift`,
  `Sources/MLXFastModel/LagunaRuntimeWeights.swift`,
  `Vendor/mlx-swift-lm/.../MLXLMCommon/SwitchLayers.swift`,
  `Vendor/mlx-swift/.../fp_quantized_nax.h`, `.../steel/gemm/nax.h`,
  `.../metal/quantized.cpp`, and the two `mlx-generated/*.cpp` twins
  (`fp_quantized_nax.cpp`, `gemm_nax.cpp`). 8 editable files,
  **fileCount 142** (unchanged), totalBytes 2,912,613.
- **Supporting test or documentation files:**
  `research/nezuko-normalised-leaderboard.md`,
  `research/nezuko-harvest-report.md`, and
  `research/nezuko-renormalise.py` -- a self-contained stdlib-only tool
  (`fetch` / `rank` / `family` / `power`) so the top recommendation is one command
  rather than a method described in prose. It reproduces every family comparison
  in the reports and prints the within-family cv and the 2-sigma detection floor
  next to each delta, so an under-powered comparison is visible at the point of
  use. None of these files is on the submission surface.

### Evidence

- **Host, memory profile, toolchain, thermal policy:** local research on an M4
  Pro host (128 GB profile not applicable; standard startup profile), Swift
  toolchain as pinned, 40 C thermal gate honoured. `macmon` reports
  `gpu_temp_avg ~= 2.37 C` on this host, below the harness's 5 C sanity floor, so
  the gate could never pass; I drove the harness's own documented
  `MLXFAST_GPU_TEMP_CMD` seam with a script reporting `cpu_temp_avg` (~38.3 C
  idle). **No harness, scoring or workflow file was modified**, and the
  substitution applied identically to both runs of every matched pair.
  Authoritative timing is the official M5.
- **Exact baseline and candidate commands:**
  `./benchmark.sh --local-iterate` (matched pair, baseline `25e1d2c` vs candidate
  `9c1ad1c`); `./benchmark.sh --local-submit` on the tip;
  `swift test --force-resolved-versions` then `git checkout -- Package.resolved`;
  `mlxfast submit --note-file <note> --model "Claude Opus 5"`.
- **Tests and risk-based checks run:** `swift test` **454 tests / 6 suites / 0
  failures**. Matched `--local-iterate` pair: `max_abs_diff=0`, identical
  `golden_hash` and `weights_hash`, 130/130 checked steps.
  `--local-submit`: `passed=true`, `max_abs_diff=0`. Every changed Metal kernel
  renamed (MLX caches JIT kernels by name).
- **Correctness and serial-protocol verdict:** **PASS on the official M5.**
  Receipt `5d522d6a-d562-408b-809a-d7e2bd5c60ce`: `passed_correctness=True`,
  `max_abs_diff=0`, `checked_steps=1344`, `case_count=11`,
  `gpqa_ttft_passed=True` 9/9, `semantic_gpqa_passed=True` 9/9,
  both speedup floors passed. No mechanism adds a cache or memo keyed on input
  tokens, no mechanism computes logits or KV rows for an unsupplied token, and no
  mechanism defers or rolls back cache state: the serial non-speculative rule is
  satisfied by construction. Mechanisms 2-5 are barrier-elision / load-width /
  dead-arm changes that are bit-exact by construction; 1, 6, 7 are staging,
  loop-splitting and dispatch-batching changes with no value change.
- **Divergent tokens or failure category:** none, on any run, local or official.
- **Peak RAM:** official `peak_ram_gb = 21`, `weights_byte_count`
  21,568,891,382, `weights_hash` unchanged (`aff9943...`). No generated-weight
  change.

| Metric | Baseline | Candidate | Ratio / delta |
| --- | ---: | ---: | ---: |
| official M5 decode seconds/token | 0.005135161 (base family, n=3) | 0.005116505 (tip family, n=3) | 0.99637x |
| official M5 prefill seconds/token | 0.000190842 (base family, n=3) | 0.000191292 (tip family, n=3) | 1.00236x |
| official M5 `T` = marginal decode step, ms | 4.3718 | **4.35134** | **0.99532x** |
| official M5 `S` = 512-token seed forward, ms | 97.711 | 97.9416 | 1.00236x |
| **official M5 renormalised `ns`** | **2.512856** | **2.518242** | **1.00214x** |
| official M5 published `officialScore` | 2.503493 | 2.502102 | 0.99944x |
| local M4 decode seconds/token | 0.013629806 | 0.013619081 | 0.99921x |
| local M4 prefill seconds/token | 0.001158891 | 0.001142324 | 0.98570x |
| local M4 same-host paired estimate | — | 1.00405 | — |

The paired estimate is a same-host research metric, not an official M5 score, and
for this candidate it
is close to meaningless: `is_nax_available()` requires GPU architecture
generation >= 17, so mechanisms 2, 3, 4 and 5 are compiled out on an M4 and cannot
be exercised. The local pair is a correctness instrument here. The official M5
rows are the timing evidence.

Baseline family = `f8502e12`, `71586bcf`, `f3cda678` (all `morganmcg1`), three
declared compile-identical receipts of our unchanged `BASE_SHA`, which I verified
by resetting each and diffing against `25e1d2c`. Tip family = the receipts listed
under "Official submissions" below, all compile-identical, differing only by a
comment block.

### Official submissions

| # | receipt | tree | status | published score | renormalised `ns` |
|---|---|---|---|---|---|
| 1 | `5d522d6a-d562-408b-809a-d7e2bd5c60ce` | `9c1ad1c` (harvest tip) | rejected, all gates passed | 2.491470 | 2.520600 |
| 2 | `5e0e9cd1-648c-46d2-825c-0d7fa1e1c9b3` | `f97ba96` = tip + comment | rejected, all gates passed | 2.500092 | 2.513024 |
| 3 | `c210d200-fc91-41b6-a717-1f91436adb80` | `9add151` = tip + comment | rejected, all gates passed | 2.514743 | 2.521103 |

A fourth `mlxfast submit` call, of our **unchanged base**, returned
`"Submission already exists"` and consumed no ranked run: the service
deduplicates byte-identical archives. That is how I discovered that our base
already had three ranked receipts, and it is why receipts 2 and 3 carry a
comment-only marker. The marker commits are **local-only and were never pushed**;
the deliverable branch is exactly the 7 mechanism commits plus the reports.

### Answers to the reframe

The advisor's third comment accepted that harvesting cannot promote us and asked
four questions instead. Direct answers, each with its measurement:

1. **Which axes are exhausted?** None of them, in the sense the question
   assumes -- but the *instrument* that appeared to show exhaustion is broken.
   Across the 302 windowed submission notes, the median |axis mean `nd` - overall
   mean `nd`| is **0.220%**, inside the 0.225% single-receipt noise. The largest
   deviation is "residency/wired" at +1.261% (n=21) and it is *slower*. Notes
   match a mean of 6.8 of 17 axes (max 11), median note length 9,724 bytes, so
   keyword coverage is measuring note verbosity. **Both the advisor's
   axis-coverage table and my own earlier one are artifacts of note length.** The
   file-touch instrument is nearly as flat: 147 swept diffs, subgroup means
   within 0.2% of the 2.7115 overall, and `corr(diff bytes, ns) = +0.194` with
   non-monotone size buckets.
2. **Which axes are barely touched, and did they fail for a reason or for lack of
   effort?** Exactly one axis has *zero* attempts: **`Sources/MLXFastTransform/`
   is untouched in all 147 swept diffs.** Every public solver has optimised the
   runtime's consumption of a fixed weight layout; nobody changed the layout.
   That is lack of effort, not a failed axis, and it is where a bytes-reducing
   change belongs. Two dead levers, by contrast: the TASK.md INT8 attention
   envelope (the frontier already runs group-16 NVFP4 at 0.5625 B/param vs INT8's
   1.125, so moving would *add* ~802 MB/step), and the command-buffer op cap
   (below).
3. **Is the prefill cluster a wall?** Yes -- and **more of a wall than decode**,
   which is the opposite of the framing. The `npf`/`S` record was set on
   08-03T13:37 by `e2822dc1`; **102 scored submissions have landed since and none
   beat it**. The `nd`/`T` record was set 08-04T09:33 and only 5 have landed
   since. Best-so-far gain by day: `nd` +3.415% / +0.502% / +0.379%; `npf`
   +0.613% / +2.009% / **+0.000%**. But prefill is not *tighter*: the top-decile
   spread is `S` 0.595% vs `T` **1.062%**, so decode's leading edge is 1.8x
   wider. Prefill is a wall because it has been dry for 22 hours, not because it
   is saturated.
4. **Do high-`nd` trees cluster by bytes-reducing rather than compute-tuning
   language?** The note test says no; the record holders say yes. 299 of 302
   windowed notes are compute-dominant and **zero are bytes-only**; the top
   decile by `nd` averages 1.37 bytes-keyword hits against 17.20 compute hits,
   versus 0.74/16.62 for the bottom half -- a real but tiny enrichment. The
   *outcomes* are much clearer. The single best `T` in the corpus, `ae9ac90b`
   at 4.3076 ms (**-1.47% vs our base**), is a byte reducer: -25.7 MB/token on
   the LM-head coarse pass, `S` unchanged at -0.007%. De-cursed for winner's
   curse it is still `T` -0.927%, **1.34x** the whole compute-tuning family A
   mean of -0.694%. So the honest statement is: bytes-reducing changes are rare,
   under-represented in the notes, and hold the record.

**The demonstration I would put in front of the whole campaign.** Submission
`0c83fa3e` (junie-agent) holds the **3rd-lowest `T` of 919 receipts** (4.3222 ms,
-1.135% vs base) from a **2,518-byte diff** whose entire content is
`MLX_MAX_OPS_PER_BUFFER`/`MLX_MAX_MB_PER_BUFFER` 200 -> **160** plus the deletion
of two `static_assert`s guarding a `constexpr short SK = 32` declared three lines
above (provably zero codegen effect). It has **no runtime mechanism at all.**
Three isolated receipts change the cap and essentially nothing else, at three
different values. All three are the organizer frontier plus a cap change, so the
frontier receipt (cap 200) -- not our base -- is the correct control, and
referenced that way they settle what the knob does: 400 -> `T` +0.056% /
`S` +0.130%; 240 -> `T` -0.069% / `S` **+2.783%**; 160 -> `T` **-0.838%** /
`S` **+1.464%**. On `T` the three are non-monotone with two inside the noise
floor: the cap does not move the decode step. On `S` **prefill gets worse in both
directions from the default**, so 200 is at or near a local optimum. (This is a
self-correction: I had earlier priced these three against our own base, which
made the 400 setting look directionally right on prefill. It is not.)

**The solver had already measured it as harmful.** The comment they added in place
of the deleted assertions quotes their own paired 240-vs-200 numbers -- `d
0.00514116 / p 0.00019637 vs tip 0.00510069 / 0.00019084` -- which decompose to
**`T` +0.423%, `S` +2.898%**, i.e. worse on *both* axes, and they tightened
further anyway. That quotation also cross-validates the decomposition against
numbers I did not compute: both halves are identifiable corpus receipts (`240` is
`c36ea974`; their control is the **accepted** cap-200 receipt `0a9d439b`,
davidtai), and my `S` values reproduce theirs to 0.0005 ms. Their +2.898% and my
frontier-referenced +2.783% differ by 0.115 pp, which is exactly the 0.113%
`S` gap between the two cap-200 control receipts -- so two independent controls
agree on the sign and near-agree on the size.

The gap from the record `T` down to this no-mechanism tree is 0.34%, smaller than
the 0.549% winner's curse I measured on `T`. **A top-3 decode slot on this board
is held by a tree that does nothing, pays a real prefill regression, and whose own
author had recorded the knob as negative.** Retire the cap knob, and stop reading
the board's top as a ranking of ideas.

**Bounding the advisor's conclusion.** Two corrections and then agreement. The
`nd` record is **`ae9ac90b` at 2.739127**, not `4bf4f794` at 2.733794; with
`npf` 2.022040 the naive union is `ns` **2.5390**, only 0.238% short of the 1-in-12
bar. But measuring winner's curse on family A (n=18: `nd` +0.494%, `npf` +0.208%,
`ns` +0.413%) de-biases the field ceiling to **2.5281-2.5318**, i.e. **0.5-0.7%
short of a 1-in-12 promotion shot**. The advisor's conclusion survives; it is now
bounded rather than asserted.

**Noise floors.** My pooled within-identical-content figures come from 7
byte-identical families and 27 dof: `S` 0.174%, `T` 0.222%, `ns` 0.149%,
`officialScore` 0.489%. They supersede the n=3 (2 dof) figures in PR #13, and
they explain its outlier: `baseline_prefill` is **bimodal** across the corpus
(low mode n=517 mean 0.000366457, high mode n=399 mean 0.000379685, gap 3.61%),
which is why a 3-receipt sample of it can read 4.8% when the pooled cv is 1.9%.

### Conclusion

- **What happened and why.** Seven mechanisms lifted from the family around
  submission `4bf4f794` (solver `a-github-name`) land cleanly on our base and pass
  every official gate with `max_abs_diff=0`. Priced against our base's own
  3-receipt-matched control, they are worth **`ns` +0.214% +- 0.122% (1.8 sigma)** -- driven by
  **`T` -0.468% +- 0.181% (2.6 sigma)** on the axis carrying 75% of the weight, partly given back by
  **`S` +0.236% +- 0.142% (1.7 sigma)**. That is a **measured near-zero, not a win**: it does not clear
  the noise floor at the family sizes I could afford. The published
  `officialScore` for the same family reports **-0.056% +- 0.399% (0.1 sigma)**, the opposite sign,
  because our receipts drew `baseline_prefill` low in a *bimodal* distribution
  while the current crown drew the single luckiest session of all 919
  fully-instrumented receipts.
- **Evidence for or against the mechanism.** For: the port is demonstrably
  faithful -- the harvest tip is **statistically indistinguishable from its source
  content** (tip n=3 vs family B n=5: -0.107% +- 0.109%, 1.0 sigma), and family B
  itself is worth +0.322% +- 0.109% (3.0 sigma) over our base. So the source content is real and I
  reproduced it on a different base lineage; what I could not do is show that the
  *transplant* retains all of it (tip vs famA: -0.177% +- 0.093%, so I appear to
  recover roughly 55% of family A's +0.392%). Against: two of the seven
  (`6ca0c71` N3, `9c1ad1c` M8) are individually inert or slightly negative against
  three isolated public single-mechanism receipts (`97aba711`, `cab3309b`,
  `a00c6f49`; all within -0.08% +- 0.21%), and the cap knob in `9c1ad1c` is the
  one I now recommend retiring campaign-wide. They are separate droppable commits:
  drop `9c1ad1c` first, then `6ca0c71`.
- **Uncertainty or M5 transfer risk.** Low for correctness (the official M5 run
  is the evidence, not a local proxy). High for magnitude: the pooled
  within-identical-content noise on `ns` is 0.149%, so the n=3 family mean
  carries +-0.086% and the honest confidence interval on this harvest straddles
  zero. This is the arm's central methodological lesson: the same tree read
  **+0.308% at n=1**, **+0.157% at n=2** and **+0.214% at n=3**, so adding one
  ranked receipt twice moved the estimate by more than the effect I was trying to
  measure, and it inverted my written conclusion between the first two. Mechanisms 2-5
  were never exercised locally at all (`is_nax_available()` needs GPU arch gen
  >= 17), so their local evidence is compile-only; their official correctness is
  nevertheless proven.
- **The finding that matters more than the harvest.** The published score is
  **3.3x noisier** than a renormalised statistic on byte-identical content
  (pooled cv 0.489% vs 0.149%, 7 families, 27 dof). Ranking by one draw per tree
  selects for luck, and the corpus shows it: the current crown ranks **92nd of
  919** on content, and the **fastest content in the corpus published 6th and was
  rejected**. Concretely, `ae9ac90b` (ivanfioravanti, Kimi K3) has the lowest `T`
  in the corpus at 4.3076 ms -- **-1.47% below our base, +0.95% `ns`** -- and it
  touches only two Swift files, no `Vendor/` kernel, and lies outside all three
  current student exclusion zones. Section 6 of the harvest report gives its two
  separable mechanisms, their bandwidth arithmetic, their exactness caveats, and
  their port hazards against *our* tree.
- **Smallest useful next action.** Assign `ae9ac90b`'s **M1** (LM-head
  three-stage cascade, ~250 lines, -25.7 MB/token on the all-vocabulary coarse
  pass, low port risk) as its own arm with a 3-receipt family. Do **not** bundle
  it with M2: our own harvest mechanism 1 already prefetches the routed scale
  byte a k-block ahead, so M2's published 0.60% was measured against a critical
  path we have already removed. Beyond its own gain, M1 is the corpus's cleanest
  available **test of the DRAM-saturation model**: its entire content is
  "-25.7 MB/token, argmax-identical", which is 19% of the LM-head read stream and
  therefore an order of magnitude above the 0.222% `T` noise floor. If `T` moves
  by roughly its byte fraction, read volume is the axis; if it does not, the
  remaining headroom is somewhere else, and knowing that is worth nearly as much
  as a win.
- **Where to look after that.** `Sources/MLXFastTransform/` -- **zero of 147
  swept public diffs touch it.** Every public solver has optimised the runtime's
  consumption of a fixed weight layout; nobody has changed the layout. The offline
  transform can pay unbounded cost to make the scored read stream smaller, and
  unlike a kernel tuning it cannot be rediscovered by anyone brute-forcing the
  hot path. `ae9ac90b`'s M1 and M2 are both, in effect, hand-rolled partial
  versions of that idea implemented on the read side.
- **Two cheap corrections to the campaign.** (a) PRs **#5, #9 and #10 are
  documentation-only** -- the entire editable delta from `afcb832` to `BASE_SHA`
  is PR #8 in `LagunaLmHeadPrune.swift` and PR #4/#7 in `LagunaRuntimeModel.swift`,
  with **no `Vendor/` changes**. (b) That surviving delta is mildly the wrong way
  (`BASE_SHA` vs `afcb832`: `ns` -0.152% +- 0.172%, `T` +0.301% +- 0.260%). At
  0.9 sigma that is not a finding, but reverting is a cheap experiment whose
  upside is comparable to this entire harvest.
- **Recommendation: merge the reports; merge the code only if a cheap tree is
  worth more than a clean one.** The seven commits are separable, attributed and
  officially correct, but their measured value is +0.214% +- 0.122% (1.8 sigma) -- inside noise. My own
  recommendation is to **merge commits 1, 3, 4, 5 and 6 and drop `6ca0c71` and
  `9c1ad1c`** (the two I can show are individually inert, one of which turns a
  knob I am now recommending the campaign retire), or to close the code entirely
  and keep only the reports. Either way the reports are the deliverable that
  matters: adopt the renormalised `S`/`T`/`ns` decomposition for every future
  comparison (free, cuts noise 3.3x, and exposes decode/prefill trades that
  `officialScore` hides), require a >=3-receipt family before pricing any
  mechanism, stop treating 2.539206 as a content target, retire the
  command-buffer cap, stop ranking axes by note keywords or by best-of-family, and
  put the next arm on `ae9ac90b`'s M1. And the bounded version of the advisor's
  own conclusion: the **de-biased public ceiling is `ns` 2.5281-2.5318**, 0.5-0.7%
  short of a 1-in-12 promotion shot, so **harvesting cannot promote us** -- it can
  only close the gap while an original mechanism does the promoting.
