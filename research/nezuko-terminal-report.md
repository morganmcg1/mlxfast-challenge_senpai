SENPAI-RESULT: {"terminal":true,"status":"complete","pending_arms":false,"wandb_run_ids":[],"primary_metric":{"name":"same_host_paired_estimate","available":true,"value":1.05501},"test_metric":{"name":"passed_correctness","available":true,"value":1}}

- **Student / PR:** `maple-nezuko` / #7 (`maple-nezuko/decode-roofline-and-resident-footprint`, revision `r1`)
- **Hypothesis and target cost:** Build a measured decode roofline for the current frontier and identify where the step actually loses time, then cash the single largest item found. Target cost: decode seconds/token (75% of score weight).
- **Decision: green** — one measured, bit-exact, byte-neutral 4-line change worth **−6.8% decode** on this host, plus a full per-dispatch roofline that re-scopes three sibling arms. One hard blocker found that affects every arm in the campaign.
- **`BASE_SHA` / candidate commit:** `768bb9d4adfc2baac7d74c0008afc92d010329da` / branch head of `maple-nezuko/decode-roofline-and-resident-footprint`. The submitted **code** has been unchanged since `02d47f6`, which is the exact commit the candidate timings below were taken on; every later commit on the branch touches only `research/` (`git diff --stat 02d47f6 HEAD -- Sources/ Vendor/ Package.swift Package.resolved` is empty).
- **Submitted candidate files:** `Sources/MLXFastModel/LagunaRuntimeModel.swift` only (4 changed lines, **+4 bytes**). `Vendor/` is byte-identical to `BASE_SHA` (`git diff --stat BASE_SHA -- Vendor/` is empty).
- **Supporting test or documentation files:** `research/nezuko-decode-roofline.md` (Interim 1–12), `research/host_bandwidth_ceiling.swift`, `research/decode_probe.py`, `research/run_local_benchmark.sh`, `research/sweep_down_rps.sh`, `research/run_upstream_equivalence.sh`. None are on the submission surface; the candidate works without them.

---

## The change

`laguna_routed_shared_nvfp4_down_residual_bf16_r1_v4` → `_v5`, with
`outputs_per_simd` 1 → 4 and grid `hiddenSize * 288` → `hiddenSize / 4 * 288`
(`LagunaRuntimeModel.swift:7593-7595`, `:7613`, `:7772`). Threadgroup shape,
arithmetic, and accumulation order are untouched; only the row→threadgroup
mapping moves.

**Why it is bit-exact.** The per-row lane split, `laguna_nvfp4_qdot_16`
accumulation order, `simd_sum` reduction tree, BF16 rounding points, in-order
8-expert weighted accumulation, and the `2.5f` scaling are all unchanged. The
existing epilogue guard `slot == 0 && lane < outputs_per_simd` and the
`down_outputs[(routed_experts + 1) * outputs_per_simd]` buffer were already
written generically for `outputs_per_simd > 1`. Sole call site is `:9998`,
gated by `lagunaFusedRoutedSharedDownResidualEnabled` (default true) plus the
existing decode-only shape guard, so prefill is untouched.

## Evidence

- **Host, memory profile, toolchain, thermal policy:** Apple **M4 Pro**, 48 GiB
  unified memory, macOS 26.5.2, Swift 6.3.3. Low-memory startup profile active
  (48 < 64 GiB) — allocator management only, not ranked code paths. All timings
  taken through `benchmark.sh --local-iterate` behind the standard 40 C cool-down
  gate, with `MLXFAST_GPU_TEMP_CMD` pointed at a CPU-die sensor (see blocker
  below) and `macmon` at `$HOME/bin/macmon`.
- **Exact baseline and candidate commands:**
  ```bash
  bash research/run_local_benchmark.sh          # wraps ./benchmark.sh --local-iterate
  bash research/sweep_down_rps.sh               # rows/simd = 1,2,4,8, 120 steady steps each
  bash research/run_upstream_equivalence.sh     # vendored-Laguna oracle, zero tolerance
  ```
  Worker build used for every timed run:
  ```bash
  CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" swift build -c release \
    --force-resolved-versions --scratch-path .build-worker --product mlxfast-runtime-worker
  git checkout -- Package.resolved
  ```
- **Tests and risk-based checks run:** matched `--local-iterate` baseline and
  candidate on the same quiet host (130 checked steps each, `passed: true`,
  `max_abs_diff = 0`); the public 64-step drift tripwire inside that path; a
  4-arm `outputs_per_simd` sweep at 120 steady steps per arm with per-arm
  divergence counting (**every arm reported `0 divergences`**); and the gated
  `LagunaUpstreamEquivalence` oracle against the vendored model, run both with
  the candidate and with the runtime file reverted to `BASE_SHA` (see below).

**Upstream-equivalence oracle — decode is bit-exact.** Candidate report:

| step | max abs logit err | mean abs logit err | runtime vs upstream token |
| --- | ---: | ---: | --- |
| prefill | 0.125 | 0.011933609 | 5991 = 5991 |
| decode-0 … decode-7 | **0** | **0** | all match |

All eight decode steps are exactly zero, and decode is the only path the
change touches (the sole call site is behind a decode-only shape guard, so
prefill never enters the modified kernel). The prefill row's 0.125 is
**pre-existing frontier behaviour, not a regression**: re-running the same
oracle with `LagunaRuntimeModel.swift` reverted to `BASE_SHA` and everything
else held fixed produced a **byte-identical report** — same 0.125 / 0.011933609
prefill, same eight zeros.

Two things about this test that the campaign should know, because they made it
silently useless at first:

1. The oracle is a *free* swift-testing `@Test` function with no enclosing
   suite (`LagunaCorrectnessTests.swift:217`), so
   `--filter LagunaCorrectnessTests.<name>` selects **zero tests and still
   exits 0**. My first invocation "passed" having run nothing. Use the bare
   function name and confirm the log shows the test started.
2. `swift test` cannot reach the GPU as shipped: the debug test bundle has no
   colocated `mlx.metallib`, and MLX's lookup
   (`Vendor/mlx-swift/.../backend/metal/device.cpp:164-215`) has **no
   environment override** — `get_metallib_path()` is in-process only — so it
   throws `Failed to load the default metallib`. Fix is to copy the worker
   build's metallib next to the xctest binary;
   `research/run_upstream_equivalence.sh` now does this automatically.

Consequently the test still **exits 1** on both the candidate and the
unmodified base, because `MLXFAST_LAGUNA_EQUIVALENCE_MAX_ABS_ERROR` defaults to
`"0"` and that single tolerance is applied to every step including prefill.
Zero tolerance is right for the decode steps but unachievable for the batched
NVFP4 prefill path against a bf16 upstream reference. **The oracle cannot pass
as a gate on the current frontier** — it is usable as a per-step differential
check, so read the table, not the exit code. I am reporting the exit code
honestly rather than loosening the tolerance to manufacture a green.

- **Correctness and serial-protocol verdict:** pass. `max_abs_diff = 0` on 130
  checked steps. The change adds no state, no cache, no cross-request memory,
  and no extra rows: the kernel still computes exactly the one supplied token's
  down projection per invocation and advances KV by exactly the input length.
  It is a pure grid-mapping change inside one existing dispatch.
- **Divergent tokens or failure category:** none.
- **Peak RAM:** `peak_ram_gb = 21` for both baseline and candidate (unchanged).
  Process RSS 20.71 GiB, `mlx_active_gb = 33.29`, `mlx_peak_gb = 35.61`.

| Metric | Baseline | Candidate | Ratio / delta |
| --- | ---: | ---: | ---: |
| decode seconds/token | 0.0146281556 | 0.0136301139 | 0.9318x → speedup **1.0732x (−6.8% time)** |
| prefill seconds/token | 0.001125732 | 0.001123257 | 0.9978x → speedup 1.0022x |
| local estimated score | 0.72578 | 0.76570 | **1.0550x** |
| same-host paired estimate | — | **1.05501** | — |
| `max_abs_diff` | 0 | 0 | — |
| `peak_ram_gb` | 21 | 21 | — |

The paired estimate is `decode_speedup^0.75 * prefill_speedup^0.25` =
`1.073223^0.75 * 1.002203^0.25` = **1.05501**, which reproduces the harness's
own score ratio (0.76570 / 0.72578 = 1.055010) exactly. It is a same-host
research metric, not an official M5 score. Note the distinction that matters
for the band discussion below: the **decode component alone is 1.0732**, while
the composite is 1.0550.

---

## Answers to your explicit prediction, and to Parts 1/2/3

**Process failure I have to flag first: I could not post interim comments.**
You asked three times for interim PR comments "the moment each exists" because
three students were waiting. **Students cannot post PR comments in this
harness** — `respond_to_issue` rejects a PR target (`human messages must use an
issue, not a pull request`) and `push_branch` is advisor-owned. So every interim
deliverable had to accumulate in `research/nezuko-decode-roofline.md` and land
with this terminal submission. That is a real cost to the other three arms and
it needs a protocol fix, not a workaround by me. Interims 1–12 in that file are
what the comments would have said, in order, with timestamps implicit in the
commit history.

**Your falsifiable prediction: partly confirmed, and the conclusion it was
meant to support is refuted on this host.**

| your prediction | measured | verdict |
| --- | --- | --- |
| byte budget 1.65–1.9 GB/token | **1.7929 GB/step** | **confirmed** |
| M4 Pro streaming ceiling ≈273 GB/s nameplate | **260.2 GB/s measured** (95%) | confirmed, use 260.2 |
| DRAM floor 6.04 ms/token | **6.891 ms/step** at the measured budget | confirmed |
| baseline decode 9.5–11 ms/token | **9.816 ms/step** steady wall | **confirmed** |
| 55–65% of streaming ceiling | **72.5%** | **higher than predicted** |
| ⇒ 41–49% of decode is not DRAM traffic | **27.5% on M4** | **smaller gap** |
| ⇒ "the overhead tier is where this is won" | **96.7% GPU-busy; all 45 command buffers cost 60 µs/step total** | **refuted on M4** |

Two corrections matter more than the numbers:

1. **The 14.63 ms/token you would read off my baseline `score.json` is not a
   per-step number**, which is why it looks far outside your 9.5–11 range. The
   harness charges the 512-token seed prefill into the decode figure
   (`LagunaRuntimeBenchmark.swift:877-878`, `:966-1013`,
   `includes_seed_prefill=true`). Steady per-step wall is 9.816 ms — dead centre
   of your prediction. Anyone comparing a per-step measurement to a reported
   decode figure without this correction will be wrong by ~1.5x.
2. **The residual is not launch overhead.** The step is 96.7% GPU-busy, and
   command-buffer submission costs 1.33 µs each, so all 45 buffers together cost
   60 µs/step (0.6%). The 2.607 ms gap to the DRAM floor is **specific kernels
   sitting below their own roofline**, and I attributed 87% of it by name. This
   is the finding that should re-scope the campaign: the win is in kernel
   geometry, not in host hygiene or dispatch batching.

**Part 1 — delivered.** Measured ceiling, matched baseline, achieved bandwidth,
and a full per-dispatch table with achieved GB/s. All instrumentation was
reverted before any timed run: the local-only MLX profiler I added to
`device.cpp`/`device.h` is gone and `Vendor/` is byte-identical to `BASE_SHA`.
I also corrected the dispatch count: **405–406 per step, not ~324** — the NVFP4
attention arm is live, at 5 dispatches per layer.

**Part 2 — measured and confirmed, but deliberately not fixed.** Your 35–38 GB
estimate is **confirmed**: `mlx_peak_gb = 35.61`, `mlx_active_gb = 33.29`
against a 21.6 GB checkpoint. Process RSS is 20.71 GiB and the harness reports
`peak_ram_gb = 21`, so the duplication lives in MLX's allocator rather than in
resident process pages. Also relevant: `recommendedMaxWorkingSetSize` on this
host is **37.4 GiB**, so 35.61 GB is uncomfortably close to the limit but not
over it, and the wired-residency dose at
`LagunaRuntimeWeights.swift:440-460` never engages on a student host.

I did **not** land the release change, for two reasons I want on the record
rather than buried:
- The **16-byte editable-surface budget** (next section) makes it physically
  impossible to land a change of that size without first reclaiming bytes. A
  release path with the prefill-safety enumeration you correctly asked for is
  hundreds of bytes minimum.
- Part 1 pointed at a **4-line change worth −6.8% decode**, which is a far
  better use of the remaining allocation than a footprint win you yourself
  scoped as high M5-transfer-risk. Your stop rule allows Part 3 as the second
  measured step, and it won on its own.

So Part 2's deliverable here is the confirmed number and the working-set
context, not a fix. The enumeration of what is genuinely dead is still owed and
is the natural next assignment, and it now has a hard prerequisite: reclaim
surface bytes first.

**Part 3 — delivered and it is the headline.** The largest gap was not the
routed gate/up QMV (93% of ceiling, fine) but `routed_shared_down_residual` at
**42% of ceiling**. Fixed below.

---

## The roofline (this is the reusable part)

**1. Measured host streaming ceiling: 260.2 GB/s read** (95% of the 273 GB/s
nameplate); copy 225.2, read-modify-write 245.0. `recommendedMaxWorkingSetSize`
is 37.4 GiB, so the 21.6 GB tower is comfortably resident and the 96 GiB
wired-residency guard never engages on a student host.

**2. The reported decode number is not a per-step number.** The trusted harness
(`LagunaRuntimeBenchmark.swift:877-878`, `:966-1013`, `includes_seed_prefill=true`)
charges the 512-token seed prefill into the decode figure and divides by 128.
Baseline split: **seed 546 ms (29.2%), 128 steady steps 1265 ms (67.5%),
harness IPC 61 ms (3.3%)**. Score elasticities: on M4 a 1% steady-step win is
worth 0.51% of the decode term and a 1% prefill-class win 0.47%; on M5 the
split is 0.36 / 0.64. **Anything measured per-step must be de-rated by ~0.51
(M4) / ~0.64 (M5) before it is quoted as a decode win.** This is the single
most useful correction for the other arms.

**3. The step is 96.7% GPU-busy — there is no host-side stall.** Per steady
step: wall 9.816 ms, `gpu_busy_sum` 9.492 ms = `gpu_busy_union` 9.498 ms,
**gap 0.322 ms (3.3%)**, across **45 command buffers and 406 dispatches**.

> **CORRECTED 2026-08-06.** Two defects in the sentence above.
> (a) The `gpu_busy_union` half of the "= `gpu_busy_union`" claim is retired
> programme-wide: the union merges *command-buffer* intervals from a CB
> completion handler, and MLX packs 20–50 ops per buffer on one queue, so
> `union == sum` holds **by construction** and proves nothing about
> serialization. This was first derived by tanjiro,
> `research/tanjiro-pr157-result.md` §2 (merged `f4bfa59`); his
> `concurrent_1cb` control reads `overlap_eff` 1.0024 (perfect hiding) while
> the CB-derived overlap statistic reads `0.000000`. Cite him, not this line.
> (b) The arithmetic is impossible: `9.816 − 9.498 = 0.318 ≠ 0.322`, and
> `union > sum` cannot occur. The row is retired; fresh measurements on
> `9dd2eec3` give `8.267 / 8.016 / 8.016 / 0.251` ms.
>
> The *conclusion* — the step is ~97% GPU-busy with no additive host stall —
> survives, on independent evidence that does not use the union: `wall −
> gpu_busy_sum` is 3.01% of wall, and a 19-row regression over a 9.2% busy
> range excludes an absolute (busy-independent) host pool at 3.10σ. See
> `research/nezuko-pr158-decode-dead-time.md` §1.1.

Command-buffer submission costs **1.33 µs** each, so all 45 buffers cost only
60 µs/step. `MLX_MAX_OPS_PER_BUFFER` is **inert** here: MLX's 40 MB-per-buffer
limit trips first and a sparse layer is already ≈38 MB.

**4. Per-step byte budget: 1.7929 GB at 9.498 ms = 188.8 GB/s = 72.5% of
ceiling. DRAM floor 6.891 ms.** The full per-dispatch table and the headroom
ranking are in `research/nezuko-decode-roofline.md` (Interim 8); 2280 µs of the
2607 µs gap is attributed to named dispatches (87%). Top of that ranking:

```text
1095 us  routed_shared_down_residual   <- 42% of ceiling, largest single item
 419 us  sliding_fused_attn_ring       <- 37% of ceiling
 134 us  full_fused_attn_grow          <- 43% of ceiling
 109 us  gate_sp_h64                   <- 2% of ceiling (pure launch latency)
 107 us  residual_rms_router
 102 us  routed_nvfp4_swiglu_qmv
```

**5. Diagnosis of the top item, and why the obvious explanation is wrong.** At
`outputs_per_simd = 1` each of 9 simdgroups issued a 256 B code burst plus a
32 B scale burst (a quarter of a 128 B line) and then hit
`threadgroup_barrier`, and 2048 threadgroups each ran a single-lane epilogue.
It is **not** a coalescing defect: 8 B/lane is *forced* (512 NVFP4 values /
32 lanes = 16 values = 8 B), and a wider load would change the `simd_sum`
association and break bit-exactness. The real defects are insufficient memory
in flight per barrier-bounded threadgroup, max-of-9 barrier skew across the
gathered experts, and ~18 MB/step of redundant activation re-reads. Upstream
precedent for the fix: MLX's own `qmv_fast`
(`Vendor/mlx-swift/.../backend/metal/kernels/quantized.h`) uses
`results_per_simdgroup = 4`, and llama.cpp's Metal backend uses
`N_R0_Q4_0 = 4`.

**6. The sweep confirms the mechanism and picks N = 4** (120 steady steps per
arm, fresh worker per arm, **all arms `0 divergences`**):

| rows/simd | µs/call | µs/step | GB/s | gpu_busy | wall median |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 49.83 | 1943 | 106.6 | 10.048 ms | 11.405 ms |
| 2 | 26.56 | 1036 | 200.0 | 9.153 ms | 10.527 ms |
| **4** | **22.96** | **896** | **231.3** | **9.033 ms** | **10.435 ms** |
| 8 | 24.10 | 940 | 220.4 | 9.044 ms | 10.464 ms |

N = 4 recovers 1.048 ms/step on the dispatch and **1.015 ms/step (−10.1%) of
whole-step GPU busy**; no other dispatch moved across arms, which is the clean
signature of a local fix. The 231.3 GB/s achieved is 89% of ceiling, up from
41%. Also measured: a split load/accumulate loop variant (0.0136466 s/token)
was **no better** than the single loop, so the compiler already hoists the
loads; I kept the single loop and saved 70 bytes of surface (see blocker).

---

## BLOCKER the whole campaign needs to know about: 16 bytes of surface budget

`Sources/MLXFastTrustedHarness/EditableSurfaceByteBudget.swift:18` sets
`defaultMaxTotalBytes = 3_000_000` and sums the **raw** byte size of every
regular file under the 97 `editablePaths` entries — no comment stripping.

**At `BASE_SHA` the surface is already 2,999,984 bytes: 16 bytes of headroom.**

Enforcement is asymmetric and that is the trap:

- `Sources/MLXFastCLI/main.swift:1394-1402` **throws** only when
  `MLXFAST_OFFICIAL_BENCHMARK_RUN=1` (set by `.github/workflows/benchmark.yml:184,1503`).
  Otherwise it is a **stderr warning only**.
- `.github/scripts/run-submission-static-review.sh:140-143` is an
  unconditional `exit 1` (invoked from `benchmark.yml:441`).

So a local `--local-iterate` run still prints `passed: true` for a candidate
that the official runner will refuse. My first version of this change carried a
1,213-byte explanatory comment, reached 3,001,197 bytes, and **would have been
rejected on M5 while looking green locally.** The submitted version is
**2,999,988 bytes (12 bytes headroom)** and I verified it prints no surface
warning.

Every student should count surface bytes before submitting. Two reclaim
candidates I found and deliberately did **not** touch, since they are outside
this assignment: `mergedSharedActivated` at `LagunaRuntimeModel.swift:9898` is
declared and never assigned (dead), and the `DARKBLOOM_SHARED_FIRST_DOWN`
scaffold duplicates a 9-entry `inputNames` array plus ternaries (~450 B) for a
default-off experiment.

## Second blocker: the acceptance-band reference is documented two ways

This determines whether the result above is submittable as one change, so I am
flagging it rather than working around it.

- `TASK.md:44-52` reads as though the two-sided band applies to each timed
  run's seconds/token against the `officialBaseline*` constants
  (`Constants.swift:167-168`), giving `[0.980, 1.053]` decode and
  `[0.952, 1.053]` prefill, "per submission, not cumulative".
- `Constants.swift:154-167` states those constants are **NOT** the ranked
  scoring denominator, and that the ranked runner uses a live same-session
  paired baseline (pinned Poolside commit `15852ee5…`) folded in by
  `.github/scripts/overlay-paired-timing.sh:131-146`; the constants only serve
  local estimates and gates-only placeholders.

Under the `TASK.md` reading, the **published frontier itself (2.6466x decode)
would fail the band**, so the operative denominator must be the paired
baseline. Mechanism: `AcceptanceBand.swift:49-50`, `Score.swift:101-114`,
failing via `Score.swift:155-157` `acceptance_band_failed`; local modes only
warn (`LagunaRuntimeLocalIterate.swift:462-507`).

**Why it matters here.** The band applies to `decode_speedup` and
`prefill_speedup` individually, not to the composite. This candidate's
**`decode_speedup` is 1.0732** against the same-host baseline, and I project
~1.064 on M5 (steady steps carry more weight there: 0.64 vs 0.51). Both are
above the 1.053 fast edge, even though the composite (1.0550) sits right at it.
A staging step at `outputs_per_simd = 2` delivers 88% of the win (~1.057
projected decode on M5) and is *still* over the edge, so staging does not
obviously solve it. **I did not add a switch, a regression, or
any benchmark-dependent behaviour to fit the band** — that is explicitly
disallowed, and it would also be dishonest. The advisor should decide whether
to submit as-is against the paired-baseline reading or to ask the organizers to
reconcile the two documents.

## Hand-offs to the sibling arms

- **frieren (host/encode overhead):** the ceiling is **60 µs/step, 0.6% of the
  step and 0.3% of reported decode**. The step is 96.7% GPU-busy. This is not a
  5% arm on this host; recommend re-scoping.
- **fern (attention):** real and second-largest (0.55 ms/step of headroom), but
  the mechanism is **latency/occupancy, not bandwidth**.
  `laguna_sliding_fused_attn_ring_v1` (`:1351-1661`, dispatch `:1764`) and
  `laguna_full_fused_attn_grow_v1` (`:1821-2172`, dispatch `:2276`) each use
  ~17.5 KB of threadgroup memory, so at most one threadgroup is resident per
  core; grids of `(heads/2)*1024` give 32 and 24 threadgroups over 16–20 cores,
  i.e. ~2 waves with a ~40% idle tail. The DRAM floor is 8.1 µs against 22.0 µs
  measured. Cheapest first move: halve the `outputs` buffer to 8 KB using two
  barrier-separated combine passes — the epilogue at `:1609-1648` is already
  two-pass — for ~0.25 ms/step with a small diff and unchanged arithmetic.
  Follow-up: 4 query heads per threadgroup (KV re-read 4x → 2x), but that drops
  to 16/12 threadgroups. Worth disambiguating with Xcode Metal capture
  occupancy counters, a window 256-vs-512 A/B, and a back-to-back duplicate
  dispatch (SLC-hot) probe.
- **tanjiro (lm_head):** `lmhead_int5_inline_coarse_v5` is already at
  **264 GB/s (at ceiling)**. The remaining lm_head cost is the 76.6 µs
  `lmhead_exact_inline_mask_block_v1` latency tail, not bandwidth.
- **Unowned arm worth creating:** the unfused latency dispatches
  `gate_sp_h64`/`h48`, the router, and `shared_nvfp4_swiglu_qmv` total
  ~0.66 ms/step, of which ~0.32 ms is pure launch latency at 0–5 GB/s. Fusing
  them into their neighbours is bit-exactness-friendly and nobody owns it.
- **Correction for everyone:** the step issues **405–406 dispatches, not 324**.
  The NVFP4 attention arm is live, which is 5 dispatches per layer.
- **Campaign-wide tooling blocker:** this host's GPU temperature sensor reads
  dead, so the cool-down gate never satisfies. Workaround is
  `MLXFAST_GPU_TEMP_CMD` pointed at a CPU-die sensor (see
  `research/run_local_benchmark.sh`). This affects all four student hosts.
- **Second tooling blocker for anyone touching numerics:** the upstream
  equivalence oracle needs the bare-function-name filter and a colocated
  metallib, and it cannot return zero on prefill. `AGENTS.md` tells us to use
  this test whenever a change affects numerical behaviour, so every arm will hit
  both defects. `research/run_upstream_equivalence.sh` handles them and prints
  `EQUIVALENCE_EXACT_STEPS=` alongside the exit code; reuse it rather than
  rediscovering this.

## Conclusion

- **What happened and why:** the roofline localised 1.095 ms of the 2.607 ms
  step-level gap to a single dispatch that was running at 42% of the measured
  memory ceiling because each simdgroup had only one 256 B row in flight before
  a barrier. Giving each simdgroup four rows lifted it to 89% of ceiling and
  removed 10.1% of whole-step GPU-busy time, which showed up end to end as
  −6.8% reported decode.
- **Evidence for the mechanism:** monotone improvement 1 → 2 → 4 with a
  turnover at 8 (register/occupancy limit), the achieved-bandwidth curve moving
  106 → 200 → 231 GB/s in step with it, no other dispatch changing across arms,
  and the split-loop null result confirming the win is memory-parallelism and
  not instruction scheduling.
- **Uncertainty and M5 transfer risk:** all timings are M4 Pro. M5 has more
  bandwidth and NAX-capable variant selection, so the *absolute* ms/step will
  differ and the down kernel may already sit at a different fraction of its
  local ceiling. The *direction* should transfer — the defect is architectural
  (memory in flight per barrier-bounded threadgroup) and upstream MLX and
  llama.cpp both choose 4 rows per simdgroup — but the M5 steady-step weight is
  higher (0.64 vs 0.51), so I project a **larger** relative decode win there,
  `decode_speedup` ~1.064, which is precisely what may trip the acceptance band.
  I did not attempt to tune the size of the win. Second transfer caveat: M5
  selects `_nax` kernel variants where available, so the down dispatch may
  already start from a different fraction of its local ceiling than the 42% I
  measured here; the sweep should ideally be repeated on the M5 before assuming
  4 is still the argmax rather than 8.
- **Smallest useful next action:** decide the band question (submit as-is under
  the paired-baseline reading, or ask the organizers to reconcile
  `TASK.md:44-52` with `Constants.swift:154-167`), then reclaim surface bytes
  from the two dead-code sites above so the next arm has room to land at all.
- **Recommendation: merge.** The change is 4 lines, +4 bytes, bit-exact on 130
  checked steps with `max_abs_diff = 0`, exactly zero logit error on all eight
  decode steps of the vendored-upstream oracle, and worth −6.8% decode on a
  matched same-host pair. Its value should be confirmed on the official M5, and
  the band question resolved before dispatch.
