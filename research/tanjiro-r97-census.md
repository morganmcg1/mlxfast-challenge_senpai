# r97-b prefill dispatch census — P2 (fused QKV) + P2b (copy-free consumption)

Host: Apple M4 Pro, 20 GPU cores, 48 GiB, Apple GPU generation 16.
Harness: `research/tanjiro-r97-census.sh` (job `37d994aa`, exit 0, 84.2 s), which runs
`research/prefill_probe.py --reps 3 --profile --profile-top 40` under
`DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=1`, once with
`DARKBLOOM_FUSED_QKV=0` and once with `=1`.
Raw output: `research/r97-logs/profile.{off,on}.log` (per-call `.err` streams are ~1.2 MB
each and are intentionally not committed).

The GPUPROF emit hooks live in `Vendor/mlx-swift/.../metal/device.{h,cpp}`, which are **not**
in `benchmark.json`'s `editablePaths`. They are research-only instrumentation and were
reverted immediately after this census; no timed A/B or submitted candidate contains them.

## Admissibility

This host is Apple GPU generation 16 and therefore never selects the `_nax` steel kernels
that the ranked M5 uses. Prefill **wall-clock** from this host is not evidence for any
`_nax`-shape claim. What *is* admissible is the **dispatch census**: which kernels the
runtime enqueues, how many times, and what buffers they bind. Those are decided by MLX's
Swift/C++ dispatch logic, not by the kernel variant the M5 later picks. P2b's claim is a
dispatch-count claim (78 general strided copies present vs. absent), so this census is
direct evidence for it.

## Headline

Both arms produced the identical greedy token (`token=5991`) and identical peak RAM
(20.7147 vs 20.7151 GB).

| quantity | OFF (plain) | P2 only (prior art, PR270 r2-f1 census) | P2+P2b (this run) |
| --- | ---: | ---: | ---: |
| total dispatches / request | 1222 | 1144 | **1066** |
| `steel_gemm_bf16` dispatches | 392 | 236 | **236** |
| `qk_norm_rope` dispatches | 41 | 119 | **41** |
| `qk_norm_rope` ms/request | 4.188 | 5.704 | **4.209** |

P2 alone converted 78 skinny wk/wv GEMMs into one wider fused GEMM per layer but paid for
it with 78 freshly-materialised `g2_copy` dispatches, because the four prefill QK-norm
custom kernels declare `ensureRowContiguous: true` and the bank's last-axis slices are not
row-contiguous. P2b removes that tax entirely: the QK-norm kernels now take the bank
directly plus a 4-element `layout` descriptor, so `qk_norm_rope` returns to exactly 41
dispatches and 4.209 ms — i.e. **P2b recovers 1.495 ms of the 1.516 ms P2 had given away,
leaving +0.021 ms of residual overhead.**

`1144 − 78 = 1066` reconciles exactly with the prior P2-only census, which is a useful
consistency check that nothing else changed.

## Per-family detail

| family | OFF n | OFF ms | ON n | ON ms | Δ ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| routed_gather_gemm | 76 | 265.275 | 76 | 265.207 | −0.068 |
| **steel_gemm_bf16** | **392** | **218.308** | **236** | **211.682** | **−6.626** |
| sort_scatter | 154 | 108.370 | 154 | 107.259 | −1.111 |
| attention_core | 40 | 28.146 | 40 | 28.168 | +0.022 |
| nvfp4_dense_qmm | 116 | 20.013 | 116 | 20.011 | −0.002 |
| elementwise | 234 | 4.820 | 234 | 5.193 | +0.373 |
| **qk_norm_rope** | **41** | **4.197** | **41** | **4.224** | **+0.027** |
| moe_tail | 38 | 2.545 | 38 | 2.563 | +0.018 |
| rms_norm | 83 | 1.757 | 83 | 1.723 | −0.034 |
| lm_head | 5 | 0.666 | 5 | 0.669 | +0.003 |
| router | 40 | 0.665 | 40 | 0.668 | +0.003 |

Every family except `steel_gemm_bf16` is dispatch-count-identical. That is the shape of a
clean, single-mechanism change.

## Inside `steel_gemm_bf16`

| dispatch | OFF n | OFF us/call | OFF ms | ON n | ON us/call | ON ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `steel_gemm_fused_nt_..._bm64_bn64_bk16_wm2_wn2` (regular) | 82 | 2230.7 | 182.919 | 82 | 2487.1 | 203.944 |
| `MIXED:steel_gemm_splitk_accum+steel_gemm_splitk_nt` | 310 | 114.2 | 35.390 | 154 | 50.2 | 7.738 |

The MIXED entry fuses the two halves of each split-K launch, so 310 = 2x155 launches and
154 = 2x77. The 78 removed split-K launches are exactly `wk` and `wv` on 39 layers.

On this M4 the regular GEMM count is unchanged at 82 because `wq` was already regular and
simply becomes wider: bytes bound per call rise 19.598 -> 21.976 MB and time rises
182.919 -> 203.944 ms (+21.03 ms), while split-K falls 35.390 -> 7.738 ms (−27.65 ms).
Net steel: **−6.63 ms**.

## Why the M5 arithmetic differs, and why that is fine

On M5 the `wk`/`wv` shape (M=512, N=1024, K=2048) does **not** qualify for split-K: Case-2
needs `K >= 3*max(M,N)` = 3072 > 2048, and the older `K > 2*max(M,N)` is the exact tie
`2048 > 2048` = false. So on M5 those 78 launches are *regular* 64-threadgroup GEMMs
rather than split-K, and P2's M5 delta is "−78 regular 64-TG GEMMs, +1 wider GEMM per
layer" instead of "−78 split-K". The registered prediction (preregistration §10.2) is
therefore that P2 alone is worth roughly 0 to −0.4 ms on M5 — below the 0.3 ms NO-GO bar —
because a 64-threadgroup dispatch on 40 cores wastes ~20-25% of its makespan in the tail
round, and folding it into the `wq` dispatch (512 -> 640 TGs) amortises that.

What this census establishes independently of the M4/M5 split-K difference is the part
that transfers unchanged: **P2b's 78 avoided copies are 78 avoided copies on any Apple
GPU generation**, because `custom_kernel.cpp`'s `ensure_row_contiguous_` path is generation-
independent. That is the mechanism carrying the registered −1.4 ms M5 estimate for
P2+P2b, and it is why R1 carries the two together rather than P2 alone.

## Buffer-binding evidence that the kernels really consume the bank

`laguna_prefill_sliding_qk_norm_rope_bf16_128_h1_v3` binds 9.500 MB/call OFF and
10.000 MB/call ON. 10.000 MiB is exactly the full fused bank `[1, 512, 10240]` in bf16,
counted **once** even though it is passed as both `raw_queries` and `raw_keys` — MLX's
input tracking in `device.cpp` is set-based, so the duplicated argument is idempotent.
OFF binds the separate `queries` (8.0 MiB) + `keys` (1.0 MiB) + the small tensors.
Per-call time moves 113.3 -> 114.2 us (+0.8%), so reading Q and K out of a wider bank with
a strided row descriptor costs essentially nothing.

The full-attention twin behaves the same way: 7.250 -> 7.750 MB/call, 89.6 -> 89.6 us.

## Registered NO-GO check discharged: the fused shape cannot leave `_nax`

The preregistration listed "the fused shape leaves `_nax` on generation >= 17" as a NO-GO.
Reading `Vendor/mlx-swift/.../metal/matmul.cpp` settles this structurally rather than
empirically.

At line 957 the selector is

```cpp
bool use_nax = metal::is_nax_available() &&
    !issubdtype(a.dtype(), complexfloating) &&
    (env::enable_tf32() || a.dtype() != float32);
```

`use_nax` is a function of the device and the dtype only. It does not read `M`, `N`, or
`K`. For bf16 on an M5 it is unconditionally true, so widening `N` from 8192 to 10240
cannot demote the dispatch off the `_nax` family. **The NO-GO is not merely unobserved; it
is unreachable.**

The two remaining branch points are also safe:

- Case 1 (the non-`_nax` SIMD split-K at line 965) is guarded by `!use_nax`, so the M5
  never enters it. This is exactly why M4 and M5 disagree about `wk`/`wv`: on this gen-16
  host `use_nax` is false, `_tm*_tn = 32*64 = 2048 <= min_tmn_threshold`, and the pair goes
  to split-K; on M5 that branch is closed.
- Case 2 (`_nax` split-K, line 988) needs `K >= 3*max(M,N)` or
  `(max(M,N) <= 1024 && K > 2*max(M,N))`. For `wk`/`wv` (M=512, N=1024, K=2048) the first
  fails (2048 < 3072) and the second is the exact tie `2048 > 2048` = false. For the fused
  bank (N=10240) both fail trivially. So the shapes involved are regular `_nax` both before
  and after fusion, and P2 on M5 is a clean 3-dispatches-into-1 merge of regular `_nax`
  GEMMs.

The router (N=256) and `g_proj` (N=64/48) do satisfy `K >= 3*max(M,N)` and remain `_nax`
split-K on M5. They are untouched by this arm.

### Tile geometry and the alignment fast path

`steel_matmul_regular_axpby_nax` (line 200) starts from `bm=128, bn=128, bk=512, wm=4,
wn=4`, then for large devices (`devc` in `{'s','c','d'}`, which covers this Max-class part)
sets `bm=64, wm=2` and `bk = (K >= 8192 && K > M+N) ? 64 : 256`. With `K=2048` that gives
the M5 regular tile **bm=64, bn=128, bk=256, wm=2, wn=4**.

Three function constants gate the fast path:

```cpp
const bool align_M = (M % bm) == 0;   // 512 % 64  == 0   ok
const bool align_N = (N % bn) == 0;   // 10240 % 128 == 0 ok, 8192 % 128 == 0 ok
const bool align_K = (K % bk) == 0;   // 2048 % 256 == 0  ok
```

The fused widths were chosen so all three stay true; a misaligned `N` would silently select
the bounds-checked variant and could easily eat the whole gain. This also independently
confirms the earlier decision to **not** fold `g_proj` into the bank: that would give
`N = 10240 + 64 = 10304`, and `10304 % 128 = 64`, so `align_N` would flip to false.

Threadgroup counts follow as `tm = ceil(512/64) = 8`, `tn = ceil(N/128)`:

| dispatch | N | tn | threadgroups |
| --- | ---: | ---: | ---: |
| `wk` (unfused) | 1024 | 8 | 64 |
| `wv` (unfused) | 1024 | 8 | 64 |
| `wq` sliding (unfused) | 8192 | 64 | 512 |
| `wq` full (unfused) | 6144 | 48 | 384 |
| fused sliding | 10240 | 80 | **640** |
| fused full | 8192 | 64 | **512** |

These are the counts the preregistration's occupancy argument was built on, and they hold
under the geometry actually selected by the code. A 64-threadgroup dispatch on 40 cores
needs two scheduling rounds to retire 1.6 rounds of work; folding it into the `wq` launch
is what recovers that tail.

Note that this same geometry is the premise of P3: `bn=128, wn=4` is exactly the pair the
skinny-N tile design proposes to halve, and its guard `bn==128 && wn==4` matches the
selected values rather than the `bm=128` defaults.

## Wall clock on this host (directional only)

| | OFF | ON | Δ |
| --- | ---: | ---: | ---: |
| wall ms/request | 548.235 | 546.918 | −1.317 |
| gpu busy (sum) | 655.087 | 647.689 | −7.398 |
| gpu busy (union) | 545.402 | 540.506 | −4.896 |

Consistent in sign with the family table, but this is a 2-request warm profile under
active instrumentation and is not offered as a timing result. The timing evidence is the
uninstrumented ABBA A/B, and the ranked answer is the M5 receipt.
