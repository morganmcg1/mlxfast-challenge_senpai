# Decode host overhead: the host/GPU knee, a host-CPU meter, and the editable byte budget

Student research note, 2026-08-04, PR #4 (`maple-frieren/decode-dispatch-overhead`).
Measured on Apple M4 Pro 48 GiB; the ranked host is M5 Max 128 GiB. Kept here
because the host-CPU measurement recipe and the byte-budget constraint apply to
every future assignment on this track, not just this candidate.

- Student / PR: `maple-frieren` / #4
- Hypothesis and target cost: decode non-bandwidth overhead — command-buffer
  boundaries, the async-fire ladder, and per-step host waste. Target cost is the
  host CPU time spent per decode step outside the GPU critical path.
- Decision: **ambiguous** (real, measured, bit-exact host-CPU win of ~3.4%;
  invisible in M4 wall time and projected at 0–3% on the ranked M5)
- `BASE_SHA` / candidate commit: `768bb9d4adfc2baac7d74c0008afc92d010329da` /
  `8728bcac49629c0439d4a9435fc4bd0a655bd70d`
- Submitted candidate files: `Sources/MLXFastModel/LagunaRuntimeModel.swift`
- Supporting test or documentation files: none

### Evidence

- Host, memory profile, toolchain, and thermal policy: Apple M4 Pro, 48 GiB
  unified memory (273 GB/s), 14 cores, macOS default toolchain. 48 GiB < 64 GiB
  so every run took the **low-memory startup profile** (6 GiB allocator cap,
  warmup cache clear, `MLX_MAX_MB_PER_BUFFER=64` / `MLX_MAX_OPS_PER_BUFFER=128`,
  `wireResidentWeightsIfEnabled()` skipped). The ranked M5 profile is 200/200
  with `MLX_BFS_MAX_WIDTH=50`. Standard 40 C thermal gate honoured on every run;
  it passed at 38–39 C with 0 s wait each time.
- Exact baseline and candidate commands: `./benchmark.sh --local-iterate` from
  the target checkout, launched through `run_training` with argv
  `["/usr/bin/env", "MLXFAST_LOCAL_FAN_PROMPT=0", "./benchmark.sh",
  "--local-iterate"]`, plus one `./benchmark.sh --local-submit` preflight on the
  final tip. The host-CPU meter arms add `DARKBLOOM_DECODE_HOST_SPIN_US=200` and
  require the diagnostics commits (`548a63b`, `394aed5`, `23705db`) to be
  present; they are reverted on the tip, so reproducing the meter means
  cherry-picking those three commits first.
- Tests and risk-based checks run: `swift test --force-resolved-versions` →
  **454 tests in 6 suites passed**, `Package.resolved` unmodified;
  `swift build -c release --force-resolved-versions --target MLXFastModel` clean
  except the pre-existing `mergedSharedActivated` never-mutated warning;
  editable-surface byte budget re-checked with a local reimplementation of
  `EditableSurfaceByteBudget` after every edit.
- Correctness and serial-protocol verdict: `--local-iterate` reports
  `passed=true` with **`max_abs_diff=0`** over `checked_steps=130`, and
  `./benchmark.sh --local-submit` reports `passed=true`,
  `passed_correctness=true`, **`max_abs_diff=0` over `checked_steps=1025`**, with
  `golden_hash=f49e4c2cbc0d3cee…` and no drift override. The trusted harness's
  editable-surface byte check runs immediately before each worker launch and both
  workers launched, so the surface is legal on the ranked path as well.
  (`prefill_speedup=0.33` and the acceptance-band WARNING in the `--local-submit`
  summary are local-host artifacts: they compare an M4 against the pinned M5
  baseline constants. `gpqa_ttft_passed` / `semantic_gpqa_passed` are false with
  `case_count=0` because those hidden gates are not available locally.)
  Serial-protocol verdict: unaffected. No caching, no lookahead, no deferred KV rows: the
  change only removes host-side heap allocations and one redundant reshape from
  the existing single-token path, so the serial non-speculative contract is
  untouched.
- Divergent tokens or failure category, if any: none.
- Peak RAM or generated-weight size, if relevant: unchanged —
  `peak_ram_gb=21`, `weights_byte_count=21568891382`,
  `weights_hash=aff994300573c5e8…`.
- Branch layout (the tip is what I recommend; the middle two commits are the
  scaffolding history): `548a63b` diagnostics + low-memory command-buffer A/B
  seam → `394aed5` optimizer-proof spin → `23705db` spin counters → `52eaeb9`
  the host-allocation removals → `a874b2c` revert diagnostics → `8728bca`
  re-express the guards as `MLXArray` members. A squash of `52eaeb9 + a874b2c +
  8728bca` is the whole candidate; `548a63b`/`394aed5`/`23705db` are the
  cherry-pickable host-CPU meter.

### Conclusion

**What happened and why.** I looked for decode host overhead and found four
things, only one of which is a candidate.

*1. The M4 decode step is GPU-bound, so host savings are invisible in local wall
time.* I added a calibrated host-CPU load (`DARKBLOOM_DECODE_HOST_SPIN_US`,
N µs per layer × 40 layers per step) and swept it. The first version of the probe
had a side-effect-free body and was **optimizer-eliminated**, which produced a
convincing but completely fake "slope 0, host is free" reading; the shipped probe
uses a global sink, `@inline(never)`, and self-validating call/time counters.

| injected µs/layer | injected ms/step | steady period | Δ wall | decode s/token |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 0.00 | 9.87 ms | — | 0.014640 |
| 50 | 2.00 | 9.80 ms | ≈0 | 0.014558 |
| 200 | 8.00 | 12.68 ms | +2.81 ms | 0.017488 |

Fitting `wall = max(G, H + injected)` gives **host CPU H ≈ 4.7 ms/step,
GPU-bound wall G ≈ 9.87 ms, host slack ≈ 5.2 ms/step** on this M4. That is the
whole reason the ladder/command-buffer half of the assignment has no local
signal: there is 5.2 ms of host slack to hide behind.

*2. That same knee is a host-CPU meter.* Past the knee `wall = H + injected`, so
running any candidate at `DARKBLOOM_DECODE_HOST_SPIN_US=200` converts host-CPU
deltas into wall-time deltas one-for-one. This is the measurement that gives the
candidate below a real number instead of a noise-band shrug. (It also
invalidates `mean_host_build_ms` as a CPU meter: its steady span is 6.95–7.00 ms
in every arm, but it grows only +3.58 ms for +8.00 ms of injected CPU, so ~4.4 ms
of it is blocked waiting. Note also that `mean_period_ms` divides by `steps−1`
while `mean_host_build_ms` divides by `steps`.)

*3. The ranked M5 is nearly host-bound, which is where this matters.* The most
recent real frontier M5 numbers I could find in-repo
(`senpai/competition_notes/leaderboard_promotions_2026-08-02.md:18,180`, rank
126, commit `7702fab8a4…`) are decode 5.249092 ms/token, prefill 0.195665
ms/token. Removing the charged seed prefill (512 × 0.195665 / 128 = 0.783) gives
an M5 decode step of **4.47 ms** against M4's 9.85 ms — a ratio of 2.20 versus
the 2.25 bandwidth ratio, i.e. M5 decode is essentially purely bandwidth-scaled.
Host CPU does **not** scale with bandwidth: 4.7 ms on M4 becomes roughly
3.7–4.1 ms on M5's faster cores, against a 4.47 ms step. So the ranked machine
has only **~0.4–0.8 ms of host slack, with host CPU at ~83–92% of the decode
step.** Host-side work is nearly on the critical path there, which is why a
0.16 ms host saving is worth reporting even though it is invisible here.

*4. The roofline numbers the advisor asked for, and what they change.*

| | M4 Pro (mine) | M5 Max (ranked frontier) |
| --- | ---: | ---: |
| peak bandwidth | 273 GB/s | 614.4 GB/s |
| decode s/token as charged by the harness | 0.0146539 | 0.0052491 |
| amortized 512-token seed prefill inside that | 4.51 ms | 0.78 ms |
| **steady decode step** | **9.87 ms** (measured period) | **4.47 ms** (derived) |
| achieved at 1.65 GB/token | 167 GB/s | 369 GB/s |
| achieved at 1.90 GB/token | 193 GB/s | 425 GB/s |
| **fraction of peak** | **61–71%** | **60–69%** |
| host CPU per step | 4.7 ms (5.2 ms slack) | ~3.7–4.1 ms (~0.4–0.8 ms slack) |

Both hosts sit at the same fraction of very different peaks, which confirms the
campaign thesis that the limiter is machine-independent. **But the spin sweep
localizes it to the GPU timeline, not the host timeline.** On M4 the wall equals
the GPU-bound wall with 5.2 ms of host slack to spare, so the ~30–40% of decode
time that is not DRAM traffic is spent *inside GPU execution* — per-dispatch
launch latency, occupancy, and dependency stalls across the ~324 dispatches — not
in host graph construction. For the campaign that means **dispatch count is the
lever, not dispatch cost**, which is the advisor's own "Revise" branch.

It also gives host-cost reduction a second, larger reason to exist. On M5 the host
already occupies ~83–92% of the 4.47 ms step. If another arm halves GPU decode
time on M5 (4.47 → ~2.7 ms), the ~3.7–4.1 ms host becomes the **binding
constraint** and most of that GPU win is unrealizable. Host-side reduction is
therefore a prerequisite for cashing in any large GPU-side win on the ranked
machine, independent of what it scores on its own today.

**The candidate.** Three per-decode-step host allocations removed from the scored
runtime, all bit-exact:

1. 191 `x.shape == [literal]` guards → `x.dims(...)` and 15 `a.shape == b.shape`
   comparisons → `a.sameDims(b)`, all allocation-free.
   `MLXArray.shape` builds a fresh Swift `[Int]` via `.map`
   (`Vendor/mlx-swift/Source/MLX/MLXArray.swift:95-100`) and the literal builds a
   second array, so each guard was two heap allocations; `ndim`, `dim(i)` and
   `shapeN` are direct C accessors that allocate nothing, and the `ndim` test
   short-circuits `shapeN`'s dimensionality precondition.
2. `decodeFireMask` hoisted from a per-step recomputation to a stored `let` on
   `LagunaRuntimeModelInner`, built once in `init` from `config.numHiddenLayers`.
3. The head-major `values` reshape is skipped when `fusedAttended != nil`, which
   is every decode layer (`LagunaRuntimeModel.swift` ~`:5992-6003`).

| Metric | Baseline | Candidate | Ratio / delta |
| --- | ---: | ---: | ---: |
| decode seconds/token (no spin, mean of 2) | 0.0146473 | 0.0145917 | 1.0038x |
| prefill seconds/token (no spin, mean of 2) | 0.0011200 | 0.0011197 | 1.0002x |
| same-host paired estimate | — | 1.0029 | — |
| decode steady period, spin-200 arm | 12.68 ms | 12.52 ms | **−0.16 ms/step** |
| implied host CPU per step | ≈4.70 ms | ≈4.54 ms | **−3.4%** |

The paired estimate is a same-host research metric, not an official M5 score.

**Be careful with the no-spin row: on M4 it is not a real signal.** The
individual runs are

| arm | commit | decode s/token | prefill s/token | correctness |
| --- | --- | ---: | ---: | --- |
| baseline | `72d4798` | 0.014653925 | 0.001127762 | `max_abs_diff=0` |
| baseline + diagnostics, spin 0 | `23705db`-family | 0.014640325 | 0.001112248 | `max_abs_diff=0` |
| candidate | `52eaeb9` | 0.014536491 | 0.001125740 | `max_abs_diff=0` |
| candidate (final byte-legal tip) | `8728bca` | 0.014646837 | 0.001113743 | `max_abs_diff=0` |

Baseline spans 0.014640–0.014654 and the candidate spans 0.014536–0.014647:
**the ranges overlap, so M4 wall time cannot distinguish them.** That is exactly
what the 5.2 ms of host slack predicts. The spin-200 arm is the only load-bearing
timing evidence here, because it is the only measurement that puts the host on
the critical path.

The spin-200 pair was taken on `52eaeb9`, the immediate predecessor of the tip.
Both spin arms carried identical diagnostics, so the diagnostics cancel in that
comparison. The tip differs from `52eaeb9` only by (a) reverting those
diagnostics (see the byte-budget section below), and (b) renaming the
allocation-free guards from `lagunaShapeIs(x, …)` free functions to `x.dims(…)`
`MLXArray` members — same `@inline(__always)` bodies, same accessors, identical
semantics including the nil case. The host-CPU result therefore transfers to the
tip; re-running the meter on the tip would require re-applying the reverted
diagnostics.

**A programme-level finding the advisor needs before assigning anything else.**
`Sources/MLXFastTrustedHarness/EditableSurfaceByteBudget.swift` enforces
`defaultMaxTotalBytes = 3_000_000` and `defaultMaxFileBytes = 524_288` across all
97 `editablePaths`, and it is re-checked **immediately before every ranked worker
launch**. At `BASE_SHA` the surface is **2,999,984 bytes across 142 files — 16
bytes of headroom.** My first working tip was +7,513 bytes over the cap, which
`swift test` caught as
`staticReviewKernelPolicyAndLaunchBudgetCoverEnlargedSurface()`
(`BenchmarkScriptTests.swift:2553`). Two consequences:

- I reverted the diagnostics into `a874b2c` (+4,830 bytes reclaimed); the probe
  and host timing stay cherry-pickable at `548a63b`, `394aed5`, `23705db`. The
  spin-meter comparison remains valid because both arms carried identical
  diagnostics.
- I re-expressed the shape guards as `MLXArray` members instead of free
  functions. `x.dims(d0, d1)` is 5 bytes **shorter** per site than the
  `x.shape == [d0, d1]` it replaces, where `lagunaShapeIs(x, d0, d1)` was 5 bytes
  longer. Net effect: the candidate leaves the surface at 2,999,651 bytes,
  **333 bytes smaller than `BASE_SHA`**, instead of 2,699 bytes larger.

Every future assignment on this track must be byte-neutral or byte-negative, and
`Sources/MLXFastModel/LagunaRuntimeModel.swift` is already at 493,353 of its
524,288-byte per-file cap.

**Evidence for or against the mechanism.** For: the spin-200 arm moves 0.16
ms/step with `max_abs_diff=0`, and the mechanism (heap-allocation removal) is
exactly the kind of cost that does not shrink when memory bandwidth grows.
Against: the no-spin M4 wall time does not move outside run-to-run noise, so the
end-to-end claim cannot be validated on my hardware at all — only the host-CPU
component can.

**Uncertainty and M5 transfer risk.** The M5 host-slack estimate (~0.4–0.8 ms)
comes from one published frontier measurement one promotion behind the vendored
frontier plus a cores-versus-bandwidth argument, not from an M5 run. If M5 slack
is at the high end, the 0.16 ms host saving is fully hidden and the ranked gain is
~0%; if it is at the low end, the gain is up to ~3%. Either way the change cannot
regress: it is strictly less host work, bit-exact, and byte-negative, and 1.0
speedup sits comfortably inside the decode band [0.980, 1.053].

**Smallest useful next action.** One official M5 run of this branch; the host-CPU
mechanism is unmeasurable on any machine with M4-class host slack, so M5 is the
only instrument that can settle it. Separately and more importantly for the
campaign: **re-scope the non-bandwidth arms from dispatch cost to dispatch
count.** Items 1–6 of the follow-up list below, plus maple-fern's kernel work,
attack the GPU timeline where the 30–40% actually lives.

**Recommendation: merge** if the advisor is willing to spend one official run to
confirm, otherwise **repeat on M5** before merge. The change is bit-exact,
byte-negative, strictly-less-work, and it unblocks the byte budget for everyone
else. Note that per the assignment's own stop rule this is not a "green" result
(no >=1.0% decode gain on matched same-host pairs) and it is not "dead" either
(GPU-busy is ~100% of M4 decode wall, but achieved bandwidth is 61–71% of peak,
below the 85% the dead branch requires). It is the "revise" branch: the direct
overhead measurement is what carries the value.

### Assignment items 1 and 2: why I could not test them here

**Item 1, the `MLX_MAX_OPS_PER_BUFFER` sweep, is untestable on my host.** The
brief points at `LagunaRuntimeWeights.swift:387` (200 ops / 200 MB). My host has
48 GiB, below the 64 GiB threshold, so `RuntimeStartupMemoryPolicy` takes the
**low-memory** branch and overrides that pair to `MLX_MAX_MB_PER_BUFFER=64` /
`MLX_MAX_OPS_PER_BUFFER=128`, and also skips `wireResidentWeightsIfEnabled()`
(which needs >=96 GiB) and applies a 6 GiB allocator cap plus a warmup cache
clear. **The line the brief asks me to sweep is dead code on this machine.**
Sweeping 200 → 400 → 512 there would have produced a perfectly clean null that
means nothing. I did build an A/B seam for the *low-memory* pair (a setenv
overwrite in `RuntimeStartupMemoryPolicy.apply()`) to check whether the
boundary matters at all, but a 64/128 result does not transfer to a 200/200
ranked path, so I reverted it with the rest of the diagnostics. Anyone sweeping
item 1 needs a >=64 GiB host, and `Tests/MLXFastTests/RuntimeStartupMemoryPolicyTests.swift`
asserts the 64/128 and 200/200 values, so the policy numbers themselves are
contract, not tuning knobs.

**Item 2, the async ladder, is on the do-not-retry list.** The default
`at: 0,1,7,15,23,31,39` has already been exhaustively swept in prior work; the
code default is 7 rungs, not the 6 the doc comment at `:609`/`:640` claims (the
comment is stale — the code is right). Given item 1 was untestable and item 2 was
already settled, I spent the arm on the direct overhead measurement the brief's
step 1 asked for, which is what produced the localization result above.

### Follow-ups I did not implement

Ranked by (host time saved) × (bytes reclaimed), from a code audit of the
per-step dispatch path:

1. **Minify the two big fused-attention kernel source literals.**
   `Vendor/.../backend/common/metal_kernel.cpp:253-368` rebuilds the *entire*
   kernel source string on **every** apply (`reserve(header + source + 16384)`,
   then moves it into `CustomKernel`). There are ~363 custom-kernel applies per
   decode step, and `laguna_full_fused_attn_grow_v1` (15.4 KB) plus
   `laguna_sliding_fused_attn_ring_v1` (13.3 KB) mean ~1.16 MB of alloc+copy per
   step; I estimate ~100–200 µs/step. (The audit I commissioned put this at
   0.4–0.8 ms by assuming the `std::regex` template path; I verified **no Laguna
   kernel passes `template:`**, so that path is not hit.) Stripping comments and
   indentation from those literals is bit-identical at the Metal level and is the
   only lever that buys host time *and* surface bytes at the same time. Note
   `metal_kernel.cpp` itself is editable but `MLXFastKernel.swift` and
   `MLXArray.swift` are **not**.
2. Hoist a per-layer "fusion plan" for the immutable bank/weight-shape guards
   (the `dims` guards above make each one cheap, but they are still re-evaluated
   40× per step for values that cannot change after load).
3. `static let` the `outputShapes` / `outputDTypes` literals and the
   `lagunaResidualRMSNormRouterKernels[rowsPerGroup]!` dictionary lookup
   (~9 per layer).
4. Multi-output QKV kernel to remove ~120 slice nodes per step.
5. Gate-rides-QKV, top-8 elimination, and a shared+routed QMV merge — each worth
   ~40 dispatches/step but each needs a bit-exactness proof first.
6. Memoize the full-attention `MLXArray([writeIdx, writeIdx + 1, capacity])`
   (~10/step, ~30–60 µs).

Do **not** revisit: the async-fire ladder is already exhaustively swept (default
`at: 0,1,7,15,23,31,39`); re-fusing RMSNorm into the QKV kernel measured +2.7%
worse; and full-profile command-buffer 200/200 is a prior 6-pair re-test winner.
The low-memory 64/128 command-buffer split is a local-host artifact, not a
ranked-path lever.
