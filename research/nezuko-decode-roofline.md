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
