# R110-B rev4 Part 2 — QMV decode family Stage-0

**Verdict: `N-QMV-BANDWIDTH-BOUND` fires. Do not build the 1-deep prefetch.**

Student: maple-edward · PR #693 · revision `r110-b-rev4` ·
base `ad3773a0a188cad3e4ac97479dd7da31341d41ab` · host Apple M4 Pro (GPU gen 16,
38,338 MiB recommendedMaxWorkingSetSize).

The advisor's Stage-0 protocol was: (1) `noload` probe to cap the exposed load
chain, (2) `nobar` if a barrier exists, (3) report achieved GB/s against the
ceiling — **if ≥80 % of peak, stop and report `N-QMV-BANDWIDTH-BOUND`**.

Every decode QMV kernel that carries real weight traffic measures at
**93.5–97.1 % of a same-geometry, same-byte-count do-nothing read**. The gate
fires with ~14 points of margin on the worst kernel.

---

## 0. Two corrections to the assignment brief

Both are instances of the campaign law `L-RANKED-REACHABILITY` (prove the ranked
path dispatches *that* kernel before optimizing it).

### 0.1 The reachable target is `LagunaRuntimeModel.swift`, not `mlx-generated/fp_quantized.cpp`

The brief pointed Stage-0 at the stock `fp_qmv*` / `fp_gather_qmv*` family. On
the current frontier a one-token decode dispatches **almost none of it**. Every
QMV-shaped projection is served by a hand-written `MLXFast.metalKernel` custom
Laguna kernel in `Sources/MLXFastModel/LagunaRuntimeModel.swift`, with the
`DARKBLOOM_*` flags defaulting on. The GPU profile in §2 lists the kernels that
actually run; none of them is a stock `fp_qmv` variant.

An instruction-level change to `fp_quantized.cpp` would therefore have measured
clean on a microbenchmark and produced **0.000 % ranked reach** — the exact
failure mode of rev3.

### 0.2 No `_nax` QMV exists, so M4 measures the ranked path directly

- `grep -c qmv mlx-generated/fp_quantized_nax.cpp` = **0**;
  `mlx-generated/quantized_nax.cpp` = **0**. NAX is a matmul-tile unit;
  matrix-vector has no NAX path at all.
- On the decode geometry (M=1, B=8) `sorted_rhs` is false (it needs B≥16) and
  `M < vector_limit`, so `is_nax_available()` is **never evaluated** on the
  decode QMV path.

This is the good news of the round: unlike rev3's `gather_qmm_rhs`, the decode
QMV family has no M5-only variant, so the M4 rig is a faithful instrument here.

### 0.3 The `nobar` probe is inapplicable

Stock `fp_qmv*` has **zero barriers and zero threadgroup memory**
(`mlx-generated/fp_quantized.h:464-748`; note
`fp_quantized.cpp = fp_quantized.h + 157` for line mapping). Among the custom
kernels that actually run, only K4 (`routed_shared_..._down_residual_...`) uses
threadgroup memory (72 B) and one barrier. K3's live variant
(`preActivatedGate: true`) has no tgmem and no barrier; only its non-preactivated
sibling does. There is no barrier to remove.

---

## 1. Method

Three instruments, all research-only, none touching the submitted surface:

| artifact | what it does |
|---|---|
| `research/edward_r110b_qmv_profile.sh` | applies the gpuprof hook, builds the worker, runs a 200-step teacher-forced decode with `DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=1`, reverts the hook |
| `research/edward_r110b_bw_bench.swift` | standalone Metal harness: asymptotic stream ceilings, **short-dispatch read ceilings at the exact real byte counts and grids**, and a `qmv_emul` dequant control |
| `research/edward_r110b_run_bw.sh` | driver (`ED_REPS=40 ED_MB=1024`) |

The short-dispatch probe is the load-bearing one. An asymptotic 1 GiB stream is
the wrong ceiling for a 35 µs dispatch: launch ramp, tail, and DRAM page-open
cost are a real fraction of the window. So each probe reads **the same number of
bytes with the same thread count and threadgroup size as the real kernel**, with
the read window rotating over a 1 GiB buffer so nothing stays SLC-resident.

`git diff --numstat ad3773a0 HEAD -- Sources Vendor benchmark.json Package.swift`
is **empty**. All artifacts live under `research/`.

---

## 2. Fresh decode profile at HEAD

Two runs, agreeing to <0.1 %. 0 divergences, 200 steps, 406 command
buffers/dispatches per step.

```
run A: wall=9.799 ms  gpu_busy_sum=8.561 ms  gap=1.238 ms (12.6 % of wall)
run B: wall=9.800 ms  gpu_busy_sum=8.550 ms  gap=1.250 ms (12.8 % of wall)
```

| µs/step | share | n/step | µs/call | kernel |
|---:|---:|---:|---:|---|
| 1499.5 | 17.5 % | 39 | 38.44 | `routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2` (**K1**) |
| 1342.1 | 15.7 % | 30 | 44.73 | `decode_nvfp4_qkv_h64_r1_v1_lm1_pw1_se1_sd1` (**K2**) |
| 1114.7 | 13.0 % | 30 | 37.15 | `oproj_act_h64_v1_lm1_pw1_sc1_se1` (**K3**) |
| 862.6 | 10.1 % | 39 | 22.09 | `routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6` (**K4**) |
| 647.0 | 7.6 % | 30 | 21.6 | `sliding_fused_attn_ring_v1` |
| 421.6 | 4.9 % | 1 | 421.6 | `lmhead_int5_base_coarse_delta_bf16_v1` |
| 363.0 | 4.2 % | 10 | 36.3 | `decode_nvfp4_qkv_h48_…` |
| 303.0 | 3.5 % | 10 | 30.3 | `oproj_act_h48_…` |
| 289.0 | 3.4 % | 39 | 7.41 | `shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1` |

K1/K4 fire on the 39 MoE layers; K2/K3 on the 30 sliding-window h64 layers (the
10 full-attention layers use the `_h48_` siblings). K1–K4 are 56.3 % of decode
GPU time — the whole addressable QMV surface.

---

## 3. Exact per-dispatch byte accounting

Storage costs read out of the runtime, not assumed: routed/shared planes are
**0.53125 B/elt** (halved plane, 1 scale byte per 32 elements); attention QKV is
**0.5161 B/elt**; attention o_proj is **0.5157 B/elt**. The NVFP4 global scale is
a compile-time literal (`4194304.0f`), not a buffer. Weight bytes are read
**exactly once** in all four kernels.

| # | grid / TG | weight codes | scales | **exact read** | as probed |
|---|---|---:|---:|---:|---:|
| K1 routed gate/up | 131,072 / 64 | 8,388,608 | 524,288 | **8,912,896 B** | 8,918,016 (+0.057 %) |
| K2 qkv_h64 (rows 10,240, K 2048) | 327,680 / 64 | 10,485,760 | 337,920 | **10,823,680 B** | 10,827,776 (+0.038 %) |
| K3 oproj_h64 (K 8192, N 2048) | 16,384 / 64 | 8,388,608 | 264,192 | **8,652,800 B** | 8,669,312 (+0.191 %) |
| K4 down+residual | 147,456 / 288 | 4,718,592 | 294,912 | **5,013,504 B** | 5,026,880 (+0.267 %) |

**Bias disclosure.** The probe byte counts were page-rounded and so read
0.04–0.27 % *more* than the exact accounting. That makes the ceiling probe
marginally slower than a byte-exact one, which flatters the real kernel by the
same 0.04–0.27 %. This is the non-conservative direction, so I state it
explicitly — but it is two orders of magnitude smaller than the 12–17 point
margin the verdict rests on, and correcting for it moves K4 from 96.7 % to
96.4 %.

---

## 4. Measured ceilings

Asymptotic pure read (512 MiB–1 GiB working set), two independent runs:

```
stream_u4     best 259.2 / 260.0 GB/s   median 256.7 / 256.9 GB/s
stream_u4x4   best 251.9 / 251.6 GB/s   median 250.6 / 250.2 GB/s   <- 4-way ILP does NOT help
stream_u1     best 256.4 / 256.2 GB/s   median 255.1 / 254.7 GB/s
stream_nvfp4  best 253.6 / 253.6 GB/s   median 252.0 / 252.0 GB/s
```

Short-dispatch read ceiling at the real geometries (median of 40 reps; both runs):

```
K1  8,918,016 B  131,072 thr tg=64   best 35.38/35.33 us   median 35.96/36.25 us  (248.0/246.0 GB/s)
K2 10,827,776 B  327,680 thr tg=64   best 42.38/42.38 us   median 42.67/42.88 us  (253.8/252.5 GB/s)
K3  8,669,312 B   16,384 thr tg=64   best 34.58/34.63 us   median 34.88/35.38 us  (248.6/245.1 GB/s)
K4  5,026,880 B  147,456 thr tg=288  best 21.00/21.04 us   median 21.46/21.37 us  (234.3/235.2 GB/s)
K3' 8,669,312 B  131,072 thr tg=64   best 34.50/34.50 us   median 34.88/34.96 us  (248.6/248.0 GB/s)
```

K3' is a control: K3's real grid is only 16,384 threads, so I re-ran its byte
count at 131,072 threads to confirm the low occupancy is not itself the ceiling.
It is not — 34.88 vs 34.88 µs, identical.

### Verdict table

Real µs/call ÷ pure-read µs of the *same bytes and same grid*, using the
**fastest** ceiling observed across both runs (the conservative choice — a faster
ceiling makes the real kernel look worse):

| kernel | real µs | pure-read median | ratio | **% of short-dispatch ceiling** | vs best-of ceiling |
|---|---:|---:|---:|---:|---:|
| K1 | 38.44 | 35.96 | 1.069 | **93.5 %** | 91.9 % |
| K2 | 44.73 | 42.67 | 1.048 | **95.4 %** | 94.7 % |
| K3 | 37.15 | 34.88 | 1.065 | **93.9 %** | 93.1 % |
| K4 | 22.09 | 21.37 | 1.034 | **96.7 %** | 95.1 % |

Achieved: 232.0 / 242.1 / 233.4 / 227.6 GB/s.

**All four clear the 80 % gate by 12–17 points.** Even measured against the
*best-of* ceiling — a number the real kernel has no obligation to reach, since it
is a best-case of 40 reps — the worst kernel is at 91.9 %.

This metric is robust to byte-accounting error in one direction, which is the
direction that matters: it is an **upper bound** on overhead. If I had
*under*-counted bytes, the probe would be reading too little and finishing too
early, making the real kernel look further from the ceiling than it is. The
measured ratios are therefore pessimistic.

Total headroom to a do-nothing read across K1–K4:
`39×2.48 + 30×2.06 + 30×2.27 + 39×0.72 = 254.7 µs/step`, i.e. **5.29 % of these
kernels' 4,817 µs**. At the advisor's conversion of 0.0070 % score per wall
µs/step that is a theoretical ceiling of **+1.78 % score for a kernel that does
literally no arithmetic** — physically unreachable, and the realistic fraction of
it available to a prefetch is a small part of that.

---

## 5. Why a 1-deep prefetch has ~0 expected value

Two independent controls, both pointing the same way.

**Control 1 — `stream_u4x4`.** Four-way unrolled ILP on a pure read is
*slower* than the scalar stream (250.6 vs 256.7 GB/s median), in both runs. If
the load chain were exposed at these geometries, added memory-level parallelism
would help. It does not; the memory system is already saturated by the natural
occupancy. A 1-deep prefetch is exactly a request for more MLP, and the control
says MLP is free of value here.

**Control 2 — `qmv_emul`.** A deliberately naive dequant kernel at K1's grid and
**exactly K1's true byte count** (8,912,896 B): reads `uint2` codes plus a halved
scale plane, unpacks 16 nibbles through a `constant float nvfp4_lut[16]`, does
the FMAs, `simd_sum`. It is byte-exact with K1 and reads 5,120 B *less* than the
K1 pure-read probe, so if anything it is flattered relative to the read floor.

```
pure read (K1 geometry)  median 36.25 us   (246.0 GB/s)
qmv_emul (dequant+FMA)   median 46.62 us   (191.2 GB/s)   +28.6 %
REAL K1 production       median 38.44 us                  + 6.0 %
```

This is the cleanest number of the round. The dequantize arithmetic **does** cost
something real — a naive implementation pays +28.6 % over the read floor. The
production kernel pays **+6.0 %**. It has already hidden roughly **79 % of the
dequant ALU cost inside the load shadow**.

So the residual 3–7 % is not an exposed load chain waiting for a prefetch; it is
the un-hideable remainder of arithmetic that the existing kernel has already
overlapped nearly as far as the machine allows. Prefetching moves loads earlier.
There is nothing left for an earlier load to uncover.

### The caveat I owe against my own verdict

The preregistered gate ("≥80 % of peak ⇒ stop") fires on its own terms, and I am
honouring it. But I should not overclaim what the ceiling number alone proves.

The advisor priced this arm at a `pf`-sized **0.85 %** win across the family ≈ 41
µs/step ≈ +0.29 % score. My measured headroom is **5.29 %**. So 0.85 % is *inside*
the ceiling — capturing it would mean harvesting 16 % of the remaining gap, which
is arithmetically possible. **The ceiling number by itself does not exclude the
advisor's sizing.**

What excludes it is the two controls, and that is where the verdict actually
rests:

- `stream_u4x4` says added MLP is worth **less than zero** at these geometries,
  and a 1-deep prefetch is precisely a request for added MLP;
- `qmv_emul` says the production kernel has already overlapped **79 %** of the
  dequant ALU, so the residual is the hard remainder, not a latency bubble a
  prefetch could drain.

If a future arm wants to reopen this, the honest target is not "prefetch the QMV
loop" — it is one of the 5.29 % that is *not* MLP-shaped. I could not find such a
mechanism, and I would rather say that plainly than dress the ceiling up as a
proof it is not.

I stopped at Stage-0 as instructed rather than spending the build-and-ABBA budget
on a mechanism that two independent controls price at approximately zero, against
a preregistered per-draw σ of 0.6590 %.

---

## 6. Follow-ups I did **not** implement, sized against the +0.25 % bar

Under R113/§0P.13 the per-draw σ is 0.6590 % relative and a verified +0.25 % is
worth +18.5 pp of P(crown) at 20 draws.

### 6.1 KV-cache read amplification — ≈3.47 % of score (largest live item)

Unique K+V traffic is 89.1 MB/step but the attention split requests up to 4×
(+251.7 MB/step); attention sits ≈2.4× above its byte floor, ≈227 µs/step
(`CURRENT_RESEARCH_STATE.md:2672-2680, 3063-3075, 3490-3494`). This is an order
of magnitude larger than anything in the QMV pool and it is a *traffic* problem,
not an instruction-level one — the category this Stage-0 just showed is the only
category with room left.

### 6.2 Router GEMV is **not** bandwidth-bound — 47–49 % of peak

127.8–130.4 GB/s (`CURRENT_RESEARCH_STATE.md:1969-1971`). It is the one decode
kernel measured well below the ceiling, so it is the one place where the
instruction-level mechanism this round rejected could still apply. It is small,
so it needs a sizing pass before it is worth an arm.

### 6.3 Routed/shared nibble-delta scale planes — re-priced, now above bar, but three blockers

**This is prior work, not a new idea**: `research/maple-tanjiro-r106a-decode-byte-composition.md:180-200`
already ledgered applying the attention `laneMajor+pairwise` nibble-delta
encoding to the MoE scale planes (1 B/32 elements → ~1 B/64):

| site | metadata now (B/step) | saving | % of decode bytes |
|---|---:|---:|---:|
| routed_gate_up | 20,447,232 | 9,904,128 | 0.5926 |
| routed_down | 10,223,616 | 4,472,832 | 0.2676 |
| shared_gate_up | 2,555,904 | 1,238,016 | 0.0741 |
| shared_down | 1,277,952 | 559,104 | 0.0335 |
| lm_head int5 e8m0 | 6,422,528 | 3,110,912 | 0.1861 |
| **total** | | **19,284,992** | **1.1538 → +0.4846 % score** |

It was shelved because the largest single site (0.5926 %) missed that arm's
≥1.2 % Stage-3 gate. **Under the new +0.25 % bar the top two sites clear
individually.** Row-span statistics are favourable: ≤15 for **99.836 %** of
routed_gate_up rows and **99.980 %** of routed_down (shared_gate_up is poor at
96.1 % and should be dropped).

I am reporting this rather than proposing it, because it carries three concrete
blockers the advisor should price before assigning:

1. The nibble encoder guards require `ndim==2` and `dim(1)%64==0`; routed planes
   are 3-D `[256, rows, groups]` and routed-down rows have `groups=32`.
2. The packed routed bank's 16-byte granularity **is** its address map.
3. **Prefill coupling is the real blocker.**
   `lagunaPackedPrefillScaleView` / `…DownScaleView`
   (`LagunaRuntimeWeights.swift:998-1039`) alias the same halved buffer into the
   M5 `_nax` prefill primitive via `asStrided`. A nibble packing is not
   stride-expressible, so it needs a second resident plane (+337 MB) **and** an
   `_nax` change that only the ranked M5 can validate — i.e. blocker (3) is
   another `L-RANKED-REACHABILITY` wall, the same one that closed rev3.

Note this also runs against standing guidance
(`CURRENT_RESEARCH_STATE.md:3081-3086, 4848-4853`): "the remaining halving is
≤0.86 % … Treat the routed pool as closed to instruction-level work / Do not
assign another MoE-QMV codegen arm." My Stage-0 independently confirms the
instruction-level half of that guidance. The byte-reduction half is what changed
price.

---

## 7. Closed negatives this round independently reproduces

- **#71 routed-QMV bandwidth** — dead at step 0, kernel ≥92 % of ceiling. I
  reproduced this today from scratch with a different instrument (93.5 %).
- **#301(b) shared pairwise plane** — refuted, +5.4 µs/step despite fewer bytes.
- **#85/#513/#525 dense-MLP lossless BF16 repack** — −25.14/−20.263 MB/step
  realised and decode got *slower*.
- **#143 expert-slab dedup**.
- **group-64 re-halving** — only 23–24 % constant, not bit-exact.

The pattern across all five plus this round: on this hardware, at these decode
geometries, **byte count is the only lever that has ever moved decode**, and even
byte count fails when the removed bytes were already free. Instruction-level work
on the QMV pool is closed.
