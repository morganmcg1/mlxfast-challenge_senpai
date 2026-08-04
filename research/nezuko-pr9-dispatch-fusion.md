# PR #9 — decode dispatch fusion: measured negative, and why the profile lied

Student `maple-nezuko`, assignment `maple-2026-08-04b-latency-dispatch-fusion`
revision `r1`. `BASE_SHA=0d980bb03040182b4595cab070fd249944ea3621`.
Host: Apple M4 Pro, 48 GiB, low-memory startup profile, measured 260.2 GB/s
read ceiling. All numbers below are from this host, back to back, one
model-holding process at a time.

## Verdict

**Reject the whole fusion family.** M2 (fold `gate_sp_h64/h48` into the fused
decode QKV dispatch) was implemented bit-exactly. It removes **40 of the 406
dispatches per step (10%)** and returns **nothing**: the full benchmark moves
0.0% (inside a measured 0.58% noise floor) and the low-noise probe says the
steady step gets **1.7-2.7% slower**. The two measurements disagree on the
magnitude of the loss; neither supports a gain, and the assignment predicted
+2.7% from this mechanism alone. M1 inherits the same shape and a prior
recorded negative. M3 is structurally blocked. The submitted surface on this
branch is byte-identical to `BASE_SHA`.

This directly falsifies the arm's premise. If the 118 near-zero-bandwidth
dispatches carried ~0.47 ms/step of recoverable launch and barrier latency,
deleting 40 of them had to return at least the ~0.21 ms/step attributed to
`gate_sp`. It returned zero.

The reusable result is the *reason*: **the per-dispatch `us/call` numbers this
campaign has been ranking work by are measured with one dispatch per command
buffer, and that configuration systematically overstates the cost of a cheap
dispatch and mispredicts the sign of a fusion.**

## The change that was measured

`laguna_decode_nvfp4_qkv_gate_h<64|48>_r1_v1[_se1][_sd1]`: one kernel whose
grid concatenates the two tile spaces, `((rows/2) + heads/8) * 64` threads at
threadGroup 64. `tile = threadgroup_position_in_grid.x - <gateTiles>` selects
the body; the gate owns the leading `heads/8` threadgroups so it is scheduled
first. Both Metal bodies are copied verbatim from
`laguna_gate_sp_h<heads>_v1` and `laguna_decode_nvfp4_qkv_h<heads>_r1_v1`
(the only edit is renaming the gate kernel's input `input` -> `normalized` so
the two bodies can share one input list). New kernel names, because the MLX
JIT cache is name-keyed.

Correctness: 0 teacher-forced divergences in all four sweep arms;
`--local-iterate` `passed_correctness=true`, `max_abs_diff=0`.

## The measurement that decides it

`research/sweep_qkv_gate_fuse.sh` — four arms, fresh worker each, 120
teacher-forced steps, step 0 discarded, GPU timestamps windowed to the steady
decode span. `SPLIT=1` forces one dispatch per command buffer; `SPLIT=0` is the
shipped batching.

| arm | cb/step | dispatch/step | wall/step | gpu_busy_union | host gap |
| --- | ---: | ---: | ---: | ---: | ---: |
| FUSE=1 SPLIT=1 | 366 | 366 | 9.783 ms | 8.749 ms | 1.034 ms |
| FUSE=0 SPLIT=1 | 406 | 406 | 10.289 ms | 9.030 ms | 1.261 ms |
| FUSE=1 SPLIT=0 | 45 | 366 | 8.773 ms | 8.487 ms | 0.286 ms |
| FUSE=0 SPLIT=0 | 45 | 406 | **8.545 ms** | 8.345 ms | 0.200 ms |

- Shipped batching: fusion is **+228 us/step (+2.7%)** on the median,
  **+144 us (+1.7%)** on the per-arm minimum (the estimator least contaminated
  by scheduler noise). The two step distributions barely touch (FUSE=1 p10
  8.608 > FUSE=0 median 8.538), so this is not run noise inside the arm, and
  the arm order favoured FUSE=1 (it ran first, on the cooler host).
- One dispatch per command buffer: fusion is **-506 us/step**. Opposite sign.
- Full `--local-iterate`, three passes: `BASE_SHA` **13.569** and **13.647
  ms/token** (two runs of identical code, a **0.58% noise floor**), fused
  candidate **13.604 ms/token** — exactly between the two baselines, i.e. no
  measurable change.

**The two instruments disagree on magnitude and I am not going to paper over
it.** A +228 us/step regression is ~1.7% of the reported decode metric after
seed dilution (~232 us), which is 3x the harness noise floor and should have
been visible; it was not. The probe was taken with the local-only GPU profiler
compiled in, so an interaction between the extra output array of the two-output
fused kernel and that instrumentation cannot be excluded. What both instruments
agree on, and what decides the arm:

1. Removing 40 of 406 dispatches produced **no gain** in either instrument.
2. The QKV body itself is **+0.95 us/call slower** when fused (h64: 47.71 vs
   46.76; h48: 38.69 vs 37.89), measured consistently, which is +38 us/step of
   new cost against a dispatch whose true cost is only 213 us/step.

That is the advisor's stated kill condition for this arm verbatim: "the
absorbing kernel slowing by more than the removed dispatch saved ... it would
close the whole fusion family."

## Why the split profile is wrong, quantitatively

Additive model for one sliding sparse layer (10 dispatches, one command
buffer), using split `us/call` minus the independently measured 1.33 us
command-buffer overhead:

```text
FUSE=0 predicted 188.42 us   observed 188.58 us   (+0.16, exact)
FUSE=1 predicted 184.05 us   observed 192.28 us   (+8.23, model breaks)
```

Two distinct errors, both biased toward "fusion looks good":

1. **Every split-mode `us/call` carries 1.33 us of command-buffer overhead**
   that does not exist at the shipped 45 buffers/step. For a 5.3 us kernel
   that is a 25% overstatement; for the 2.5 us top-8 kernel, 54%. Dispatches
   are ranked by exactly this inflated number, so the cheapest dispatches look
   the most wasteful.
2. **A two-body kernel selected by threadgroup index does not keep its
   isolated timing.** Alone in a command buffer the fused kernel is 4.4 us
   *cheaper* than the two kernels it replaces; as one of nine dispatches in a
   shared command buffer it is 8.2 us *more expensive* than additivity
   predicts. The QKV body itself also slows by +0.95 us/call in both modes,
   consistent with the register allocation being the max over both bodies and
   costing occupancy for all threadgroups, not only the 8 gate ones.

The base tree is additive to 0.1%, so on this host there is **no exploitable
intra-command-buffer concurrency to win by re-ordering either** —
`gpu_busy_sum == gpu_busy_union` to 6 ns in every arm, and MLX's encoder
dispatch policy lives in `Vendor/.../backend/metal/device.cpp`, which is not on
the editable surface.

## Re-scoped per-dispatch table (current base, command-buffer overhead removed)

`true us` = split `us/call` - 1.33. Bytes/call are the shape-derived figures
from `research/nezuko-decode-roofline.md` Interim 5. `%ceil` is against
260.2 GB/s. `recoverable` = `us/step - bytes/step / ceiling`.

| dispatch | n | true us | us/step | MB | GB/s | %ceil | recoverable us/step |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| decode_nvfp4_qkv_h64_r1 | 30 | 45.43 | 1363 | 11.80 | 260 | 100% | 0 |
| routed_nvfp4_swiglu_qmv_packed_top8keys_r1 | 39 | 39.05 | 1523 | 9.442 | 242 | 93% | 105 |
| oproj_act_h64 | 30 | 38.26 | 1148 | 9.45 | 247 | 95% | 60 |
| routed_shared_nvfp4_down_residual_r1_v5 | 39 | 21.63 | 844 | 5.311 | 245 | 94% | 51 |
| sliding_fused_attn_ring_v1 | 30 | 22.34 | 670 | 2.097 | 94 | **36%** | **428** |
| lmhead_int5_inline_coarse_v5 | 1 | 515 | 515 | 134.9 | 262 | 101% | 0 |
| decode_nvfp4_qkv_h48_r1 | 10 | 36.56 | 366 | 9.44 | 258 | 99% | 0 |
| oproj_act_h48 | 10 | 30.34 | 303 | 7.09 | 234 | 90% | 31 |
| full_fused_attn_grow_v1 | 10 | ~23.5 | 235 | 2.621 | 112 | **43%** | ~130 |
| residual_rms_router_bf16_2048_rpg8_keys_v1 | 39 | 6.81 | 266 | 1.062 | 156 | **60%** | **106** |
| shared_nvfp4_swiglu_qmv_rows1 | 39 | 6.24 | 243 | 1.184 | 190 | **73%** | 65 |
| gate_sp_h64 + gate_sp_h48 | 40 | 5.32 | 213 | 0.033 | 5 | 2% | 211 (**not recoverable by fusion**) |
| decode_router_top8_ordinal_table_norm_v1 | 39 | 2.47 | 96 | 0.004 | 1 | 0% | 96 (see M3) |
| rmsbfloat16 | 41 | 0.87 | 36 | 0.008 | - | - | 36 |
| command-buffer overhead, 45 buffers | 45 | 1.33 | 60 | - | - | - | 60 |

Total 8.345 ms `gpu_busy_union` + 0.200 ms host gap = 8.545 ms/step.

## Per-mechanism disposition

**M2 — reject, measured.** +228 us/step in the shipped batching. Reverted; not
on the submitted surface.

**M1 — not attempted, and the case for it is gone.** The shared-expert gate/up
QMV's true cost is 6.24 us/call = 243 us/step, of which only **65 us/step** is
above the bandwidth floor (the assignment's 0.24 ms figure is the whole
dispatch, including bytes that any merged kernel must still read). It is the
same two-body-kernel shape that just failed, and the campaign already has a
recorded negative for merging routed with shared gate/up ("independent kernels
overlap better, +0.010 to un-merge"), corroborated by the
`DARKBLOOM_SHARED_FIRST_DOWN` +0.10 ms/step note in the current tree. Best
case 0.5% of the step, with a measured mechanism arguing for a loss.

**Residual uncertainty, stated plainly:** M1 was not run, so the family kill
rests on M2's direct measurement plus M1's prior recorded negative and its much
smaller re-scoped prize. If the advisor wants direct evidence for M1
specifically, the `mergedSharedActivated` wiring is a contained change and the
sweep script generalises to it in a few lines — but on the arithmetic above it
is competing for 65 us/step, which is 0.5% of the decode metric before
de-rating, so it is not where the next student-week belongs.

**M3 — structurally blocked.**
`residual_rms_router_bf16_2048_rpg8_keys_v1` runs 32 threadgroups x 512 threads
holding 8 of the 256 router logits each; the top-8 selection needs all 256
logits visible to one 256-lane threadgroup. Folding them requires
cross-threadgroup synchronization, and folding top-8 into the routed QMV
instead requires a redundant 256-element bitonic sort in every routed
threadgroup. Changing the router's geometry is tanjiro's surface this round.
The prize is 96 us/step (0.7% of the step, ~0.5% of the reported decode metric)
so it does not justify forcing either route.

## What the evidence says to do instead

**This is an occupancy problem, not a dispatch-count problem.** Every
sub-ceiling kernel in the table is one with too few threadgroups to fill 20 GPU
cores, and the deficit is *worse* on the official ~40-core M5 Max:

- `sliding_fused_attn_ring_v1`, 36% of ceiling, **428 us/step recoverable** —
  the largest remaining pool on the step by a factor of four. After the merged
  "one threadgroup owns a whole GQA KV group" change it launches roughly 8
  threadgroups for a sliding layer. Raising parallelism *within* a threadgroup
  (more lanes over the 512 sliding positions, same reduction order) is the
  bit-exact direction; splitting positions across threadgroups is not, because
  a flash-decoding style combine changes the softmax accumulation order.
- `residual_rms_router` at `rpg8` launches 32 threadgroups for 256 router rows,
  60% of ceiling, 106 us/step. `rpg4`/`rpg2` doubles/quadruples occupancy with
  no change to per-row arithmetic. (tanjiro's surface this round.)
- `gate_sp` and `decode_router_top8` are latency, not bandwidth, and fusion
  cannot recover them; only 213 + 96 = 309 us/step is at stake and the family
  that would collect it has now been measured to lose.

**Also worth the advisor's attention:** `decode_seconds_per_token` is
`(charged 512-token seed forward + 128 one-token steps) / 128`
(`Sources/MLXFastTrustedHarness/LagunaRuntimeLocalIterate.swift:826-834`). The
seed forward is ~546 ms here against ~8.5-9.3 ms steps, i.e. **~31% of the
reported decode number is the 512-token forward**. That gives the prefill
forward an effective score weight of about `0.25 + 0.75 * 0.31 ~= 0.48`, and it
means a pure per-step decode win is diluted by ~0.69 before it reaches the
metric. Every "% of decode" estimate in this campaign should be multiplied by
0.69 unless it also speeds the seed forward.

## Reproduction

```bash
# worker build (no GPU)
mkdir -p .build-worker/clang-module-cache
CLANG_MODULE_CACHE_PATH="$PWD/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions \
  --scratch-path .build-worker --product mlxfast-runtime-worker
git checkout -- Package.resolved

# four-arm sweep (needs the local-only device.cpp GPU profiler, see below)
bash research/sweep_qkv_gate_fuse.sh

# end-to-end matched pair
research/run_local_benchmark.sh --local-iterate
```

The `SPLIT`/`GPU_PROFILE` instrumentation lives in
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.{cpp,h}`, which are
**not** on the editable surface; they were restored from an earlier local
commit for this sweep and reverted before submission, so `Vendor/` on this
branch is byte-identical to `BASE_SHA`. Restore them with
`git checkout 0288d18 -- Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.h`
to rerun the sweep.

Peak memory: worker RSS 20.71 GB, `peak_ram_gb` 21 under `--local-iterate`.
Sweep wall time 170 s for all four arms; one `--local-iterate` pass 115-138 s.

## Branch tip verification

`--local-iterate` on the reverted tip (submitted surface identical to
`BASE_SHA`): `passed=true`, `passed_correctness=true`, `checked_steps=130`,
`max_abs_diff=0`, `decode_seconds_per_token=0.0136469`,
`prefill_seconds_per_token=0.00115837`, `peak_ram_gb=21`. Worker rebuilds clean
from the reverted tree in 59 s. Editable surface 2,999,655 bytes across 142
files, i.e. 345 bytes free — exactly `BASE_SHA`. `gpqa_ttft_passed=false` and
`semantic_gpqa_passed=false` are the pre-existing local-mode states that also
occur on the unchanged base and are not part of `--local-iterate`'s verdict
(`passed=true`).
