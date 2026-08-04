# PR #7 interim findings — decode roofline and resident footprint

Student `maple-nezuko`. `BASE_SHA=768bb9d4adfc2baac7d74c0008afc92d010329da`.
Host: Apple M4 Pro, 48 GiB (51539607552 B), macOS 26.5.2 (25F84), Swift 6.3.3.

Typed Senpai transitions cannot post a PR comment from a student, so interim
results land here as commits on the assignment branch.

## Interim 1 — measured host streaming ceiling: 260 GB/s read

Standalone Metal probe with no MLX in the path
(`research/host_bandwidth_ceiling.swift`): grid-stride `float4` streaming
kernels over 3 GiB shared buffers, best of 15 iterations, timed with
`MTLCommandBuffer.gpuStartTime/gpuEndTime` and wall clock (they agree within
1.5%).

| pattern | bytes moved | best GPU time | achieved |
| --- | ---: | ---: | ---: |
| read (`float4` load + accumulate) | 3.22 GB | 12.378 ms | **260.2 GB/s** |
| copy (read + write) | 6.44 GB | 28.605 ms | 225.2 GB/s |
| read-modify-write | 6.44 GB | 26.294 ms | 245.0 GB/s |

Read bandwidth rises monotonically with thread count (251.9 / 256.6 / 258.5 /
260.2 GB/s at 2^16 / 2^18 / 2^20 / 2^22 threads), so 260 GB/s is a saturated
ceiling rather than an occupancy artifact. Decode is read-dominated, so
**260 GB/s (95% of the 273 GB/s nameplate) is the correct ceiling for this
host**.

Restating the advisor's prediction against the measured ceiling:

| | at 1.65 GB/token | at 1.9 GB/token |
| --- | ---: | ---: |
| M4 Pro DRAM floor (260 GB/s) | 6.35 ms/token | 7.31 ms/token |
| 55-65% of ceiling | 9.8-11.5 ms/token | 11.2-13.3 ms/token |

### Incidental: this host's GPU working-set recommendation is 37.4 GiB

`MTLDevice.recommendedMaxWorkingSetSize` = 37.4 GiB of 48 GiB physical. The
shape-derived resident estimate for the runtime is 35-38 GB, i.e. at or above
the recommended working set — the regime where Metal begins making residency
decisions for us. That is a concrete mechanism by which a 48 GiB M4 Pro can
distort every arm's timing, independent of the M5 transfer question.

### Incidental: the wired-residency dose never engages on our student hosts

`wireResidentWeightsIfEnabled()`
(`Sources/MLXFastModel/LagunaRuntimeWeights.swift:548-550`) hard-guards on
`ProcessInfo.processInfo.physicalMemory >= 96 GiB`. On any 48 GiB student host
the shipped wired dose is inert, so an M4 footprint measurement is necessarily
the no-wiring regime; the interaction with `capacity = 1.0 x live bytes +
64 MiB` can only be evaluated on the official M5.

## Interim 2 — campaign-wide blocker: this host's GPU temperature sensor is dead

`./benchmark.sh --local-iterate` fails on an unmodified tree with

```text
local GPU cool-down gate failed for prefill
```

Cause: on this AWS-hosted M4 Pro `macmon` reports a frozen
`temp.gpu_temp_avg` of `2.37` C on every sample. The harness plausibility floor
is 5 C, so the gate treats the reading as invalid and refuses to run rather
than timing a hot GPU. The CPU sensor on the same host is live and tracks load
(38.3 C idle, 39.0-39.2 C after a run), so only the GPU die sensor is missing.

Sanctioned workaround, no harness edit, gate threshold untouched at 40 C
(`research/run_local_benchmark.sh`):

```bash
MLXFAST_MACMON_BIN="$HOME/bin/macmon"
MLXFAST_GPU_TEMP_CMD="$MLXFAST_MACMON_BIN pipe -s1 | jq -M -r '.temp.cpu_temp_avg'"
MLXFAST_LOCAL_FAN_PROMPT=0
```

The wrapper prints a three-sample `macmon` receipt before handing off to
`./benchmark.sh`, so every run records the substituted sensor. **All four
campaign arms on this host class are blocked until they adopt this or an
equivalent override** — worth broadcasting to fern, frieren and tanjiro.

## Interim 3 — matched baseline on this host (`--local-iterate`, clean tree)

`BASE_SHA` tree, no edits, PASSED including correctness. Saved locally as
`score.local-iterate.baseline.json`.

| metric | value |
| --- | ---: |
| `decode_seconds_per_token` | 0.0146281556 s (**14.628 ms/token**) |
| `prefill_seconds_per_token` | 0.0011257322 s (**1.126 ms/token**) |
| `score` | 0.7258 (decode_speedup 0.9472, prefill_speedup 0.3265) |
| `passed` / `passed_correctness` | true / true, 130 checked steps |
| `peak_ram_gb` | 21 |

The speedups are versus the pinned M5 calibration constants, so they only say
"this is an M4 Pro"; the seconds/token are the local decision metric.

## Interim 4 — the decode figure is not a per-step figure

`Sources/MLXFastModel/LagunaRuntimeLocalIterate.swift:826-834` divides the
whole decode phase — the charged 512-token seed prefill **plus** the 128
one-token steps — by 128. The local phase log times that seed forward at about
0.6 s, i.e. roughly 4.7 ms of the reported 14.63 ms/token is amortised seed
work, leaving a steady per-step decode near **9.9 ms/token**.

Applying the same correction to the published M5 frontier (5.249 ms/token, seed
about 100 ms) gives roughly **4.47 ms/token** steady, so achieved M5 streaming
is around 400 GB/s of 614.4 GB/s (~65%), not the ~45% the campaign thesis
assumes. The gap the campaign is chasing is real but materially smaller, and a
quarter of the reported decode number is prefill work that the prefill arm is
already optimising. Interim 5 measures the split directly instead of inferring
it from the phase log.

## Interim 5 — independent per-step byte budget: 1.794 GB, floor 6.90 ms

Derived from checkpoint shapes and the dispatches actually issued, counting
each byte once per step (unique footprint, no re-request inflation):

| group | bytes/step | share |
| --- | ---: | ---: |
| weights (all layers) | 1.5703 GB | 87.4% |
| lm_head coarse plane | 134.9 MB | 7.5% |
| KV cache reads | 84-89 MB | 4.8% |
| activations / norms / router | 3.6 MB | 0.2% |
| **total** | **1.794 GB** | |

At the measured 260 GB/s that is a **6.90 ms/token DRAM floor**, so the
corrected 9.9 ms/token steady decode is about **70% of ceiling**, and the
headroom on this host is roughly 3.0 ms/token rather than the 5-7 ms implied by
the uncorrected number.

Per-dispatch bytes for the largest sites (sparse layer, one token):

| dispatch | bytes | note |
| --- | ---: | --- |
| routed gate/up SwiGLU QMV (top-8) | 9.442 MB | NVFP4 g16, packed scales |
| fused QKV | 9.44 / 11.80 MB | full / sliding geometry |
| o_proj + act | 7.09 / 9.45 MB | |
| routed+shared down + residual | 5.322 MB | |
| shared gate/up QMV | 1.184 MB | separate dispatch, fusable |
| residual + RMSNorm + router | 1.062 MB | |
| dense layer-0 MLP | 100.7 MB | BF16, not 28 MB |
| lm_head coarse plane | 134.9 MB | int5 v5, 1344 B/row |

Representation costs used: NVFP4 group-16 = 0.5625 B/weight, INT8 group-32
`g_proj` = 1.125 B/weight, BF16 = 2.0 B/weight, lm_head int5 v5 = 1344 B/row.
Packed scales **replace** the fused bank scales rather than adding to them.
Caveat: sliding layers re-request KV rows from 4 threadgroups and full layers
from 3, so if the SLC does not absorb them the effective KV traffic can be up
to ~190 MB/step higher than the unique figure.

## Interim 6 — the dispatch count is 405 per step, not 324

With default flags the NVFP4 attention arm is live
(`lagunaNativeAffineNVFP4From` defaults to 0,
`Sources/MLXFastModel/LagunaRuntimeModel.swift:2877-2883`), so attention costs
**five** dispatches per layer, not three:

```text
prologue                       1
layer 0 (dense MLP)            8
39 sparse layers x 10        390
epilogue (final norm + lm_head) 5
harness argmax                 1
total                        405
```

Steady-state KV append needs **zero** extra dispatches (fused ring append);
decode step 1 pays a one-time growth concat on the 10 full-attention layers
(about +8 dispatches per such layer) as the cache grows to capacity 768. A
per-step budget table therefore has 405 rows to explain, and any "dispatch
overhead" estimate scaled from 324 is 25% low.

`mergedSharedActivated`
(`Sources/MLXFastModel/LagunaRuntimeModel.swift:9898`) is declared but never
assigned, so the shared-expert gate/up projection always runs as its own
1.184 MB dispatch — 39 extra dispatches per step that a fusion into the routed
QMV would remove.

## Interim 7 — the decode step is 96.7% GPU-busy: there is no host-side stall

I instrumented every `compute_encoder` dispatch and command-buffer boundary in
the vendored MLX Metal backend
(`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp`) with
`MTLCommandBuffer` GPU start/end timestamps, then windowed the records to
steady decode steps (step 0 skipped). That instrumentation is **local-only**:
`device.cpp`/`device.h` are not in `editablePaths`, and they are reverted in
this branch, so the submitted `Vendor/` tree is byte-identical to the base
commit.

Per steady decode step, default batching:

```text
wall                    9.816 ms
gpu_busy_sum            9.492 ms
gpu_busy_union          9.498 ms
host/queue gap          0.322 ms  (3.3%)
command buffers            45
dispatches                406
```

`gpu_busy_sum == gpu_busy_union` to 6 ns, so the queue is fully serialized:
nothing overlaps, and there is no concurrency to reclaim by re-ordering.

Two consequences:

1. **Command-buffer overhead is 1.33 us each.** Forcing one dispatch per
   command buffer (406 buffers instead of 45) costs 0.48 ms/step more, i.e.
   `(406-45) x 1.33 us`. At the shipped 45 buffers that is only
   **60 us/step, 0.6%**.
2. **`MLX_MAX_OPS_PER_BUFFER` is inert here.** The runtime already commits
   about one buffer per layer because MLX's own 40 MB-per-buffer byte limit
   trips first: a sparse layer touches ~38 MB. Raising the op limit changes
   nothing.

So the remaining 2.6 ms above the DRAM floor is **inside kernels**, not
between them. Any arm premised on "reduce command-buffer / encode overhead"
has at most 60 us to win on this host.

## Interim 8 — measured per-dispatch table (split mode, cb overhead removed)

Sum over all rows is 9.498 ms, exactly `gpu_busy_union`. Bytes/call are the
Interim 5 analytic figures; `%ceil` is against the measured 260.2 GB/s read
ceiling.

| dispatch | n/step | us/call | us/step | MB/call | GB/s | %ceil |
|---|---|---|---|---|---|---|
| routed_shared_nvfp4_down_residual_bf16_r1_v4 | 39 | 48.5 | 1891 | 5.311 | **109.5** | **42%** |
| routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v1 | 39 | 38.9 | 1517 | 9.442 | 242.7 | 93% |
| decode_nvfp4_qkv_h64_r1_v1 (sliding) | 30 | 45.3 | 1358 | 11.80 | 260.6 | 100% |
| oproj_act_h64_v1 | 30 | 38.3 | 1149 | 9.45 | 246.7 | 95% |
| sliding_fused_attn_ring_v1 | 30 | 22.0 | 661 | 2.097 | 95.2 | 37% |
| lmhead_int5_inline_coarse_v5 | 1 | 510.9 | 511 | 134.88 | 264.0 | 101% |
| decode_nvfp4_qkv_h48_r1_v1 (full) | 10 | 36.5 | 365 | 9.44 | 258.9 | 100% |
| oproj_act_h48_v1 | 10 | 30.3 | 303 | 7.09 | 233.8 | 90% |
| dense_gate_up_swiglu_bf16_v1 (layer 0) | 1 | 267.6 | 268 | 67.11 | 250.8 | 96% |
| residual_rms_router_bf16_2048_rpg8_keys_v1 | 39 | 6.8 | 266 | 1.062 | 155.5 | 60% |
| shared_nvfp4_swiglu_qmv_rows1_bf16_v1 | 39 | 6.2 | 242 | 1.184 | 191.0 | 73% |
| full_fused_attn_grow_v1 | 10 | 23.5 | 235 | 2.621 | 111.6 | 43% |
| gate_sp_h64_v1 | 30 | 6.6 | 199 | 0.033 | 5.0 | 2% |
| decode_router_top8_ordinal_table_norm_v1 | 39 | 3.8 | 148 | 0.004 | 1.1 | 0% |
| dense_down_residual_bf16_v1 (layer 0) | 1 | 130.8 | 131 | 33.55 | 256.5 | 99% |
| rmsbfloat16 | 41 | 2.2 | 91 | 0.008 | - | - |
| lmhead_exact_inline_mask_block_v1 | 1 | 76.6 | 77 | ~0.5 | - | latency |
| gate_sp_h48_v1 | 10 | 6.7 | 67 | 0.033 | 5.0 | 2% |
| 6 remaining small dispatches | 6 | - | ~20 | - | - | - |

Aggregate: 1.7929 GB/step at 9.498 ms = **188.8 GB/s = 72.5% of ceiling**;
DRAM floor 6.891 ms.

**Headroom ranking** (us/step recoverable if the dispatch reached ceiling):

```text
1095  routed_shared_down_residual   <- largest single item on the step
 419  sliding_fused_attn_ring
 134  full_fused_attn_grow
 109  gate_sp_h64
 107  residual_rms_router
 102  routed_nvfp4_swiglu_qmv
  74  lmhead_exact_inline_mask_block
  64  shared_nvfp4_swiglu_qmv
  37  gate_sp_h48
-----
2280  us of the 2607 us gap to the DRAM floor (87% attributed)
```

Per-layer totals in the shipped batched mode: sliding sparse layer 218.75 us,
full sparse layer 202.30 us, lm_head block (4 ops) 528.3 us, layer-0 tail
(5 ops) 453.1 us, layer-0 head (3 ops) 41.35 us.

### What this re-scopes for the campaign

- **frieren (host/encode overhead):** ceiling is 60 us/step (0.6% of the step,
  0.3% of reported decode). Not a 5% arm on this host.
- **fern (attention):** `sliding_fused_attn_ring_v1` and
  `full_fused_attn_grow_v1` together are 0.90 ms/step at 95-112 GB/s —
  0.55 ms of headroom. Real, and second only to the down kernel.
- **tanjiro (lm_head):** `lmhead_int5_inline_coarse_v5` is already at 264 GB/s
  (ceiling); the remaining lm_head cost is the 76.6 us
  `lmhead_exact_inline_mask_block_v1` latency tail, not bandwidth.
- **Unfused latency dispatches** (`gate_sp_h64`/`h48`, router,
  `shared_nvfp4_swiglu_qmv`) are ~0.66 ms/step of which ~0.32 ms is pure
  launch/latency at 0-5 GB/s. Fusing them into their neighbours is a clean,
  bit-exactness-friendly arm nobody currently owns.

## Interim 9 — cashing the top headroom item: 4 down rows per simdgroup

Diagnosis. `laguna_routed_shared_nvfp4_down_residual_bf16_r1_v4`
(`Sources/MLXFastModel/LagunaRuntimeModel.swift:7592`) launched
`grid = hiddenSize * 288`, `threadGroup = 288` (9 simdgroups: 8 routed experts
plus the shared expert) with `outputs_per_simd = 1`. A down row is only
`input_width = 512` NVFP4 values, so each simdgroup issued a **256 B** code
burst plus a **32 B** scale burst and then hit `threadgroup_barrier`, and 2048
threadgroups each ran a single-lane epilogue. The 32 B scale read uses a
quarter of a 128 B cache line. That is why the dispatch sat at 42% of ceiling
while its 2048-wide siblings (routed gate/up QMV, o_proj, qkv) reached
93-100%.

Fix: `outputs_per_simd = 4`, `grid = hiddenSize / 4 * 288`, threadgroup
unchanged. Each simdgroup now streams **1024 B contiguous** with four
independent loads in flight, the four scale reads coalesce into exactly one
cache line, and the threadgroup count, barrier count and single-lane epilogue
count all drop 4x.

Bit-exactness argument: the per-row lane split, the `laguna_nvfp4_qdot_16`
accumulation order, the `simd_sum` reduction tree shape, the BF16 rounding
points, the in-order 8-expert weighted accumulation and the `2.5f` scaling are
all unchanged. Only the row-to-threadgroup mapping moves. The existing
epilogue guard `slot == 0 && lane < outputs_per_simd` and the
`(routed_experts + 1) * outputs_per_simd` threadgroup array already
generalized, so the whole change is a 4-line diff.

Measured sweep, 120 steady steps per arm, fresh worker per arm, GPU-profiler
build (so `wall` carries the +0.48 ms split-mode penalty and only the deltas
matter). **Every arm reported `0 divergences` on the 200 teacher-forced greedy
tokens.**

| rows/simd | down us/call | down us/step | GB/s | %ceil | step gpu_busy | step wall (median) |
|---|---|---|---|---|---|---|
| 1 (base) | 49.83 | 1943 | 106.6 | 41% | 10.048 ms | 11.405 ms |
| 2 | 26.56 | 1036 | 200.0 | 77% | 9.153 ms | 10.527 ms |
| **4** | **22.96** | **896** | **231.3** | **89%** | **9.033 ms** | **10.435 ms** |
| 8 | 24.10 | 940 | 220.4 | 85% | 9.044 ms | 10.464 ms |

Four rows is the optimum. It recovers **1.048 ms/step** on the dispatch and
**1.015 ms/step (-10.1%)** of the step's whole GPU-busy time — i.e. ~96% of
the 1.095 ms that Interim 8 predicted for this dispatch. Eight rows regress,
consistent with register pressure from `thread float result[8]` plus 16 live
input values, and with quartering the resident threadgroup count.

No other dispatch moved (routed QMV 40.2-40.4 us, qkv 46.6-46.7 us, o_proj
39.4-39.7 us, sliding attention 23.3-23.7 us across all four arms), so this is
a clean single-mechanism result.

### End-to-end, and why it is probably too large for one submission

Matched `--local-iterate` on this host, same saved baseline, both PASSED all
130 checked tokens with `max_abs_diff = 0`:

```text
                 prefill s/token     decode s/token    est score
baseline           0.001126            0.014628          0.726
candidate          0.001160            0.013647          0.759
                   +3.1% (noise)       -6.7%             +4.6%
```

decode_speedup versus the same-host baseline is **1.072**. The prefill move is
noise: the change only touches the `r1` (single-row) decode kernel, prefill
uses the multi-row path, and one 512-token prefill measurement on a
laptop-class host has that much run-to-run spread.

The acceptance band is a **hard programmatic gate on the ranked path**:
`Sources/MLXFastCore/AcceptanceBand.swift:49-50` builds
`lo = reference*(1-downTolerance)`, `hi = reference*(1+upTolerance)`, and
`Sources/MLXFastCore/Score.swift:101-114` feeds it the **candidate**
seconds/token against the pinned reference, with decode tolerances
`+0.02/-0.05` (`Sources/MLXFastCore/Constants.swift:145-148`) — the
`[0.980, 1.053]` speedup band. Failure surfaces as `acceptance_band_failed`
(`Score.swift:155-157`). Local modes only warn
(`LagunaRuntimeLocalIterate.swift:462-507`), which is why the run above
reported `passed: true`.

1.072 > 1.053, so on M5 this very likely trips the band. Scaling by the
Interim 4 elasticities (steady decode is ~0.675 of reported decode here versus
~0.64 on M5) puts a like-for-like transfer near **+6.4%**, still over. The
2-rows variant is ~+4.8% projected on M5 and is the obvious staging step, but
it leaves 0.12 ms/step on the table and would need its own M5 run to confirm.

The transfer is genuinely uncertain in **both** directions. The defect is
burst size and memory-level parallelism, not raw bandwidth, and a 614 GB/s M5
needs *more* outstanding requests to saturate — so the relative win there
could be larger, not smaller. It could also be smaller if M5's larger caches
already absorb the 288 B bursts. Only an M5 run answers this. **I did not add
any switch, regression, or benchmark-dependent branch to fit the band.**

## Interim 10 — BLOCKER: the frontier has 16 bytes of editable-surface budget

`Sources/MLXFastTrustedHarness/EditableSurfaceByteBudget.swift:18` sets
`defaultMaxTotalBytes = 3_000_000` and `:67-72` reports `.exceeded` above it.
The sum is over raw byte sizes of every regular file under the 97
`editablePaths` entries — no comment stripping, no extension filter.

Enforcement is asymmetric and easy to miss:

- `Sources/MLXFastCLI/main.swift:1394-1402`: **throws** ("refusing to spawn
  the participant worker") when `MLXFAST_OFFICIAL_BENCHMARK_RUN=1`, which the
  ranked workflow sets (`.github/workflows/benchmark.yml:184,1503`); otherwise
  it only writes a stderr warning.
- `.github/scripts/run-submission-static-review.sh:140-143`: unconditional
  `exit 1`, no local/official distinction
  (`.github/workflows/benchmark.yml:441`).

Measured surface totals (142 files, via `git ls-tree -r -l`, no checkout):

```text
base 768bb9d4  2,999,984 bytes   <- 16 bytes of headroom
```

My first version of the down-kernel change added a 17-line explanatory doc
comment: **+1,213 bytes**, surface 3,001,197. `--local-iterate` printed only
`mlxfast-swift: warning: editable surface is at least 3001197 bytes, above the
static review limit 3000000` and then happily reported `passed: true` with a
good score. On the official runner that same tree would have been **refused
before the worker started**, and the submission static review would have
exited 1.

Consequences for the whole campaign:

1. **Any student PR that adds more than 16 bytes to the editable surface
   cannot be ranked.** That includes a single added comment line. Every
   arm currently in flight is exposed.
2. The local warning is not a gate, so a student can complete a full
   `--local-iterate` **and** `--local-submit` cycle, see PASSED, and only
   discover the refusal on the official M5 run.
3. Net-negative-byte refactors are now worth score. The obvious candidates I
   noticed while reading the down/MoE path, none of which I touched:
   - `mergedSharedActivated`
     (`Sources/MLXFastModel/LagunaRuntimeModel.swift:9898`) is declared and
     never assigned — dead.
   - the `DARKBLOOM_SHARED_FIRST_DOWN` alternate-ordering scaffold duplicates
     a 9-entry `inputNames` array and threads a ternary through the whole
     `lagunaRoutedSharedDownResidual` call site (~450 bytes) for an
     experiment that is off by default.
4. My final change was rewritten to a **4-line, +4-byte diff** (surface
   2,999,988, 12 bytes of headroom). The reasoning that was in the doc comment
   is in this file instead, and `research/` is not part of the editable
   surface.

I would treat "reclaim editable-surface bytes" as a real, assignable arm, and
I would add the surface total to whatever dashboard the advisor uses to accept
a candidate.

