# PR #60 pre-registration — sliding fused attention 4-deep load pipeline

Assignment `maple-2026-08-05g-sliding-attn-load-pipeline` r1.
Base `codex/mlxfast-maple-20260804-advisor` @ `5178d452c513c61e619f4dd788185c797e065529`.
Written and pushed at **2026-08-05T20:00Z**, before any candidate build, probe or
timing run existed. Nothing in this file was written after seeing a candidate
number; the Step 0 control numbers quoted below are from the unchanged base and
were recorded in `research/nezuko_pr60_probe_base.log` first.

Host: Apple M4 Pro, 20 GPU cores, `applegpu_g16s` (Apple GPU generation 16).
Not the ranked M5. Every number here is directional evidence for a kernel-shape
question, converted with the campaign M4 -> M5 factor **x0.812** for this class
of change when a score implication is stated.

## Step 0(a) — reachability verdict (recorded before Step 1)

`laguna_sliding_fused_attn_ring_v1` **is reachable** from the upstream
equivalence oracle, so `research/run_upstream_equivalence.sh` is a real check on
this change and not a vacuous one. Chain, all at base SHA:

| Link | Location | Value / condition |
| --- | --- | --- |
| env gate | `Sources/MLXFastModel/LagunaRuntimeModel.swift:1378-1379` | `DARKBLOOM_FUSED_SLIDING_ATTN != "0"`, default on |
| dispatch site | `Sources/MLXFastModel/LagunaRuntimeModel.swift:5763-5786` | guarded on sliding layer, bfloat16, `RotatingKVCache`, `maxSize == 512` |
| cache construction | `Sources/MLXFastModel/LagunaRuntimeModel.swift:10902` | `RotatingKVCache(maxSize: configuration.slidingWindow, keep: 0)` |
| ring gate | `Vendor/mlx-swift-lm/Libraries/MLXLMCommon/KVCache.swift:710-715` | needs `keep == 0`, `dim(2) == maxCacheSize`, `offset >= maxCacheSize` |
| window size | `Sources/MLXFastModel/LagunaConfig.swift:29` | `slidingWindow = 512` |
| oracle prompt | `Sources/MLXFastCore/Constants.swift:29` | `correctnessPromptTokens = 512` |
| oracle driver | `Tests/MLXFastTests/LagunaCorrectnessTests.swift:216-248` | 512-token prompt + 8 teacher-forced decode steps, tolerance `0` |
| observability | `Sources/MLXFastModel/LagunaRuntimeModel.swift:1790` | `lagunaTrace("sliding fused attention")` under `DARKBLOOM_TRACE_FUSION=1` |

The oracle prefills exactly 512 tokens into a 512-slot ring, so `offset == 512
>= maxCacheSize` already holds at the first decode step and `keep == 0` by
construction. All eight of its decode steps therefore take the fused sliding
branch, on every sliding layer. `DARKBLOOM_TRACE_FUSION=1` will be used to show
the branch firing rather than asserting it.

Consequence for Step 3: the oracle is necessary but *not* sufficient, because 8
decode steps is a small sample and because the loop restructure below is
exercised identically on every step. The injected-fault power control the
assignment requires is the part that gives the certificate teeth.

## The change under test

In the sliding fused attention Metal literal, deepen the hand-written load
pipeline in the ring-scan loop from **2 slots to 4**: step `i += 4 * BN`, issue
all four `T_LOAD_K` plus all four `T_LOAD_V` before any score math, then run the
four slot bodies in ascending `i` order. The existing 2-deep loop is retained
verbatim underneath as the fall-through; no new tail is written.

At `N = 512`, `BN = 32` the 4-deep loop with guard `i + 3 * BN < N` covers, for
every `sg` in `0..31`, exactly the slots `sg, sg+32, ..., sg+480` in ascending
order and exits at `i = sg + 512`, at which point the retained 2-deep guard
`i + BN < N` is already false. Same 16 slots per simdgroup, same ascending
order, same statement order inside each slot body, therefore the same
floating-point reduction order. This is an argument for bit-exactness, not a
measurement of it; Step 2 measures it.

To pay for the text, the per-slot body is factored into one
`do { ... } while (false)` macro used twice by the retained 2-deep loop and four
times by the new 4-deep loop. The macro body is a statement-for-statement copy
of the current slot-a body with block-scoped temporaries, so the emitted
arithmetic is unchanged.

## Decision rules — fixed now

### Step 1 (occupancy) — hard stop

Measured with `research/nezuko_occupancy_probe.swift`, the same probe and the
same phases that produced the base control.

- Report `staticThreadgroupMemoryLength`, `maxTotalThreadsPerThreadgroup`, and
  threadgroups per core for base and candidate side by side.
- Base control: 18432 B, 1024 threads, **3.00 TG/core**.
- **Stop condition:** if candidate residency falls to 2 TG/core, stop, post the
  occupancy table as the result, and do not run Step 2. A register-driven
  occupancy loss is the predicted failure mode and is itself the finding.

### Step 2 (matched latency) — hard stop

Harness `research/nezuko_pipeline_latency.swift`, both pipelines compiled in one
process from two source files (base copy and working tree), ABBA interleaved,
**>= 5 pairs** per K, K in {1, 32}. Primary K is **1**.

- Primary metric: `sliding_attn_lone_tg_us` at K = 1, minimize.
- Assignment baseline: **9.23 us** (from PR #56's staircase fit
  `t ~= 8.16 * ceil(K/20) + 1.1 us`). Same-process matched base measured in the
  same ABBA sweep is the number the decision uses; the 9.23 us figure is quoted
  for continuity with the assignment.
- **Pass:** candidate K=1 median <= **0.95 x matched-base K=1 median**
  (i.e. a >= 5% reduction; against the 9.23 us assignment baseline that is
  <= 8.77 us). Both must agree in sign for the result to be called positive.
- **Stop condition:** if the K=1 reduction is < 5%, stop and post the negative.
  Do not proceed to Step 3 or Step 4, and do not extend the pipeline to the full
  fused kernel at `:1857`. A clean negative is the deliverable in that case.
- Secondary, reported but not decision-bearing: K = 32 (base control 19.14 us on
  this host; assignment baseline 18.91 us), and a refit of `a`, `b`, `W`,
  fit residual and `a / t(1)` for the candidate staircase (base: `a = 8.16`,
  `a / t(1) = 0.88`).
- Also reported in Step 2 regardless of outcome: a **bitwise** comparison of the
  two kernels' output buffers over random bfloat16 inputs at several `widx`
  values. This is the direct bit-exactness evidence. It is diagnostic, not a
  gate; failure here means the change is wrong and the whole result becomes a
  negative.
- An exploratory 8-deep arm may be measured in the research harness only. It
  will not be proposed for the scored file in this revision regardless of what
  it shows.

### Step 3 (correctness) — only if Step 2 passes

Two halves, both required, reported separately:

1. `./benchmark.sh --local-submit` on **both** arms: `passed_correctness true`,
   `checked_steps >= 1024`, zero golden drift, no
   `MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT` override. Plus
   `research/run_upstream_equivalence.sh` with `EQUIVALENCE_EXIT=0` and a
   non-zero `EQUIVALENCE_EXACT_STEPS`.
2. **Injected-fault power control.** In a throwaway commit, drop one of the four
   slots' contribution to the `simd_sum` reduction in the candidate kernel, run
   the same certificate, and report `first_failing_step`. Then hard-reset the
   throwaway commit.
   - If the fault is caught: the certificate is load-bearing and the wording is
     "the certificate detects a single-slot arithmetic fault at step N".
   - If the fault is **silent**: the certificate is **void**. The strongest
     permissible claim becomes "no gross always-on corruption on the common
     path", and that is what will be written.
   - `max_abs_diff 0` will not be reported as a numerical bound anywhere.

### Step 4 (end-to-end) — only if Steps 2 and 3 pass

Matched `./benchmark.sh --local-iterate`, **>= 3 ABBA pairs**, fresh base and
fresh candidate on the same quiet host under the same 40C thermal gate.

- Report per-pair decode and prefill seconds/token, medians, and the implied
  local score ratio.
- Expectation fixed in advance: a 5% kernel win converts to about **+0.29%**
  score and a 10% win to about **+0.58%** after the x0.812 M4 -> M5 factor,
  both **below** single-receipt resolvability (0.278% on `ns`). So Step 4 is
  expected to be **consistent with but unable to resolve** the kernel win. A
  Step 4 that merely fails to resolve the effect is *not* a negative; only a
  Step 4 that shows a decode or prefill *regression* beyond noise contradicts
  the result. This is stated now so it cannot be re-read after the fact.
- No `mlxfast submit` in this assignment. The result is banked for stacking.

## Byte budget rules — fixed now

- Cap: net **<= +2,000 B** on `Sources/MLXFastModel/LagunaRuntimeModel.swift`,
  which is 508,711 B at base against a 524,288 B per-file cap. Frieren's #35
  will add +13,037 B, so headroom is genuinely contested.
- Budget at base, to be re-pasted verbatim after the change:
  `current=2941155/3000000 headroom=58845 growth=0/262144`.
- The only permitted payment is **reducing leading indentation inside the Metal
  string literals**. Newlines are never removed or joined: `T_LOAD_K`,
  `T_LOAD_V` and `LAGUNA_RESCALE` are `\\`-continued `#define`s and a joined
  line would change the program. Any such payment will be proven whitespace-only
  by piping `git diff -U0 <base> HEAD -- <file>` through
  `sed 's/^[[:space:]]*//'` and showing the added and removed lines match.
- `senpai/check-editable-budget.sh 5178d452c513c61e619f4dd788185c797e065529`
  output will be pasted in the final report.

## Out of scope, explicitly

Wider per-lane loads; splitting positions across threadgroups; any wave-merge
variant; removing the alpha-skip rescale; branching on `widx` at loop level;
touching Phase 1, Phase 2 or the epilogue; editing vendored `Laguna.swift`;
extending to the full fused kernel at `:1857` in this revision.

## Base-advance rule

If the base advances, intersect
`git diff --name-only <assigned base> <new base>` with `editablePaths`. Empty
intersection: accept silently. Non-empty: post the list and wait.
