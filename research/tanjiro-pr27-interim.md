# PR #27 interim — M4 instrument gate, two instrument bugs, and the cache-resident ceiling

Pushed before any official submission. Everything here is measured on this host
(M4 Pro, `Mac16,11`, 20 GPU cores, 48 GB, `applegpu_g16s`) with
`./benchmark.sh --local-iterate`, plus one standalone Metal probe,
`research/host_device_arch.swift`.

## 0. Headline for the advisor, in priority order

1. **The cache-resident ceiling arm is dead and I can price it now** (section 4).
   The fused-attention kernel at 375 GB/s on issued bytes is at **34% of the
   cache-resident aggregate ceiling at its own shape**, not at it. Packing 4 or
   8 query heads per threadgroup removes bytes the kernel is not bound by.
2. **Two instrument bugs found and fixed before spending a receipt**
   (sections 2 and 3). Both would have corrupted a constant in the direction
   that makes an arm look attractive.
3. **Your section-3 prediction about the commit thresholds is wrong in its
   premise but right in its conclusion** (section 1). This host is
   `applegpu_g16s`, not `*g`, so MLX picks **50/50**, not 40/40.
4. The M4 fit itself: **DRAM 244.97 GB/s in situ** against a **262.1 GB/s**
   isolated measurement of the identical kernel, and **7.455 TFLOP/s** achieved
   MLX steel bf16 GEMM at `512x8192x2048`.

## 1. `MTL::Device::architecture()->name()` — measured, and it is not `*g`

You asked for this one line and predicted `*g` with generation 16, giving 40/40.

```
device.name                 Apple M4 Pro
device.architecture.name    applegpu_g16s
MLX arch_gen                16
MLX class char              's'
MLX max_ops_per_buffer      50
MLX max_mb_per_buffer       50    (Mi *items*, not bytes)
```

`Device::Device()` switches on `arch_.back()` (`device.cpp:574-595`), and the
last character here is **`s`**, the "max" case, not `g`. Apple's GPU family
naming is `G13G` for base, `G13S` for **Pro and Max**, `G13C`/`G13D` for Ultra —
so a Pro lands in MLX's `'s'` bucket together with a Max.

**This strengthens your conclusion rather than weakening it.** You argued the
commit count is ~one per layer on both generations and therefore nezuko's
45-buffer decomposition transfers to the ranked host. It transfers for a better
reason than the one you gave: an M5 Max is `applegpu_g17s`/`g18s`, also `'s'`,
so **M4 Pro and M5 Max use the identical 50/50 thresholds**. There is no
generation-dependent threshold change to correct for at all. One routed-expert
bank is ~100 Mi uint32 words, 2.0x the 50 Mi threshold on both, so first touch
commits on both.

For my own instrument the same measurement re-prices your warning:

```
256 MiB uint32 scratch pool  = 67.1 Mi items = 1.34x the 50 Mi threshold
512x8192 + 8192x2048 bf16    = 21.0 Mi items = 0.42x
```

So the pool does trip `needs_commit()` on first bind in a command buffer, at
1.34x rather than the 5.1x you estimated, and the matmul operands do not trip it
at all. I applied your fix 3 regardless: **the injected bandwidth magnitude is
varied per dispatch, not by dispatch count.** `DARKBLOOM_INJECT_SWEEP_PASSES` is
a buffer-passed uniform, the sweep dispatch count is 1 per decode step in every
configuration, and all injected matmuls reuse one `matA`/`matB` pair, so the
injected commit count is identical in A and B and cancels in `T_B - T_A`.

## 2. Instrument bug 1: an injected dispatch that binds nothing GPU-written is free

This one would have destroyed run C outright.

MLX's compute encoder is created `DispatchTypeConcurrent` (`device.cpp:548`) and
inserts a barrier only through `maybeInsertBarrier()` (`device.cpp:363-374`),
which fires only when `needs_barrier_` was set because a dispatch bound a buffer
a previous dispatch in the same encoder wrote (`device.cpp:325`, `:339`).

My first instrument chained empty dispatches *within* a layer only, so with the
empties spread one per layer boundary every chain had length 1 and no injected
dispatch ever bound a GPU-written buffer. Measured consequence:

```
100 matmuls, 1 sweep, 40 decode + 40 prefill empties   T = 10.15260 ms
100 matmuls, 1 sweep,  0 decode +  0 prefill empties   T = 10.14644 ms
                                                       --------------
40 unchained empty dispatches per decode step                0.006 ms
                                             i.e. 0.154 us each
```

against 2.53 us isolated for the identical dispatch. **They ran concurrently
with real work and cost 6% of a dispatch each.** Reported as
`c_decode = 0.154 us` this would have looked like a spectacular argument for a
dispatch-count arm, and it is an artifact.

Fix: carry the chain tail across layer boundaries in
`LagunaInjectChain.tail`, so every injected dispatch binds the previous injected
dispatch's output and is barriered. That reproduces the strictly serialised real
stream — which is exactly the regime nezuko's `gpu_busy_sum == gpu_busy_union`
to 6 ns says the model runs in, and the regime whose marginal cost the constant
is supposed to describe.

Note the corollary for the programme: **it is cheap to make an MLX dispatch
overlap** if it has no data dependency. Real dispatches all have one, which is
why there is zero concurrency in the step, but any future arm that can break a
dependency gets overlap essentially for free.

## 3. Instrument bug 2: a shallow grid measures cache, not DRAM

`research/host_device_arch.swift` runs a byte-for-byte replica of the injected
sweep in isolation, 256 MiB pool, 4 passes, uint4 grid-stride:

| threads | uint4 per thread | GB/s |
| ---: | ---: | ---: |
| 32,768 | 512 | 244.5 |
| 65,536 | 256 | 241.7 |
| 131,072 | 128 | 247.3 |
| **262,144** | **64** | **262.1** |
| 524,288 | 32 | 370.9 |
| 1,048,576 | 16 | 553.4 |

The last two rows are **above M4 Pro's 273 GB/s hardware peak**, so they are not
DRAM. It is not lossless compression — scrambling the pool with a hash instead
of a uniform fill changes nothing (both columns above are the scrambled run).
It is pass-to-pass reuse: a threadgroup of 256 threads reads 4 KiB per
iteration, so its whole per-pass working set is `uint4_per_thread x 4 KiB`, which
falls to 128 KiB at 32 and 64 KiB at 16. At that size the second pass is served
from cache and the accounted bytes never reach DRAM.

**Any injected-bandwidth design that varies passes over a pool must keep the
per-threadgroup per-pass working set well above cache.** At 64 uint4 per thread
it is 256 KiB per threadgroup and ~50 MB resident, and the rate lands at
262.1 GB/s — reproducing #21's 262.5 GB/s sequential control **to 0.15%** with a
completely different kernel and harness. That is the strongest cross-validation
of the 262.5 number we have, and it is now two independent measurements.

I moved the injected sweep to that configuration: `2^18` threads, 1024
threadgroups of 256, 64 uint4 each.

## 4. The cache-resident ceiling you asked for — and it kills the head-packing arm

Same probe, `threadGroup: 1024` to match `sliding_fused_attn_ring_v1`, address
masked into a fixed window so the window stays resident across iterations:

| window | TGs | threads | GB/s |
| ---: | ---: | ---: | ---: |
| 256 KiB | 8 | 8,192 | 1779 |
| 1 MiB | 8 | 8,192 | 1776 |
| 1 MiB | 32 | 32,768 | 1069 |
| **2 MiB** | **8** | **8,192** | **1001** |
| **2 MiB** | **32** | **32,768** | **1213** |
| 2 MiB | 128 | 131,072 | 1116 |
| 8 MiB | 8 | 8,192 | 446 |
| 8 MiB | 32 | 32,768 | 711 |
| 8 MiB | 128 | 131,072 | 1376 |
| 32 MiB | 8 | 8,192 | 244 |
| 32 MiB | 32 | 32,768 | 278 |
| 32 MiB | 128 | 131,072 | 448 |

Read the 2 MiB rows: that is the 2.097 MB unique ring the sliding kernel
touches, at its own threadgroup size.

**The cache-resident aggregate ceiling at the attention kernel's shape is
~1000-1200 GB/s. The kernel achieves 375 GB/s. It is at 34% of its own byte
ceiling, not at it.**

Your stop rule was explicit: *"If the L2 ceiling is well above 375, the kernel is
limited by something else and I should not spend a student on it."* It is 2.7-3.2x
above 375. **Do not spend a student on head packing.** Halving issued bytes
removes a resource the kernel has 3x spare of; the predicted 22.34 -> 11 us does
not follow, and the honest prediction is close to no change.

Your second question — per-lane or aggregate — also has an answer. Going from 8
to 32 threadgroups at a 2 MiB window (4x the lanes, 4x the in-flight depth)
gains only 21%, and 128 threadgroups is *slower* than 32. **The cache-resident
rate is aggregate-limited and 8 threadgroups of 1024 already reach ~83% of it.**
The real kernel runs 16 threadgroups, so it is already in the saturated region
of the lane axis: it cannot be short of in-flight depth either.

The 32 MiB rows are a useful bonus: once the window exceeds cache the rate falls
straight back to the DRAM ceiling (244-278 GB/s at 8-32 TGs), which is a third
independent recovery of the same 262 GB/s number.

Caveat, stated plainly: my probe's inner loop is an independent-load XOR chain,
which is the friendliest possible consumer of the byte path. The attention
kernel has dependent softmax math and simdgroup reductions between loads. So
the correct claim is *"the byte path can sustain 2.7-3.2x what the kernel asks
of it at that shape"*, and therefore bytes are not the binding constraint. What
is binding is inside the kernel's dependency structure, which is a different arm
with a different owner.

## 5. Where the M4 gate stands

Paired local receipts, differencing exactly as the brief specifies
(`S = 512000 * prefill_s_per_token`, `T = 1000 * decode_s_per_token - S/128`):

| run | passes | matmuls | empties d/p | S (ms) | T (ms) |
| --- | ---: | ---: | ---: | ---: | ---: |
| zero | 0 | 0 | 0/0 | 583.311 | 9.00680 |
| LA | 1 | 100 | 0/0 | 799.522 | 10.14644 |
| LB | 3 | 300 | 0/0 | 1260.390 | 12.33765 |

All three returned `passed_correctness: true`, `max_abs_diff: 0`,
`peak_ram_gb: 21`. The injection is output-neutral as designed.

```
DRAM      (T_LB - T_LA) = 2.191209 ms for 2 x 268.435456 MB  ->  244.97 GB/s
matrix    (S_LB - S_LA) = 460.869  ms for 200 x 17.1799 GFLOP ->   7.455 TFLOP/s
```

- **244.97 GB/s vs 262.1 GB/s** isolated for the same kernel at the shallower
  grid it then used, and vs the 262.5 GB/s control: **-6.7%**, inside the 10%
  gate. The residual is the kernel's own grid depth, now fixed; the two numbers
  agree to **0.9%** once compared at the same configuration.
- The first pass costs more than the marginal passes — 1.1396 ms versus
  1.0956 ms — a **0.044 ms** cache-pollution term from evicting the model's own
  L2-resident KV re-reads. This is why the A/B difference and not the
  zero-control difference is the right estimator, exactly as the brief argued.
- **7.455 TFLOP/s** is MLX's *achieved steel bf16* rate, not the MMA ceiling.
  It is corroborated independently by fern's GPUPROF per-family profile on this
  same host: `attn_proj (steel bf16, fused + splitk) 1465.3 GFLOP / 216.41 ms =
  6.77 TFLOP/s`. My shape is a single clean GEMM with no split-k tail, so 10%
  faster is the expected direction. Against the 28.76 TFLOP/s MMA ceiling this
  is **25.9%**, which matches fern's 23.5% for the same kernel family.
- Two independent estimates of the FLOP axis (`zero -> LA` = 7.95, `LA -> LB` =
  7.455) bracket a 6% spread, all of which is explained by the +2.4% cross-session
  prefill drift on this host inflating the zero-control's `S`.

**This is the number that should worry the programme, and it is worth stating
before the M5 run.** Your roofline divides by a *ceiling*. The instrument
measures what MLX actually achieves. On this host those differ by 3.9x. If the
same ratio holds on M5, "60 TFLOP/s" is not the denominator for
`routed_experts`; something near a quarter of it is, and your own
`>= 44.3 TFLOP/s` lower bound derived from `98.153 - 34.32` would then be
impossible to satisfy with real GEMMs — which would mean the seed forward is not
compute-bound at all and the 34.32 ms DRAM term is doing more of the work than
the budget assumes. The M5 receipts settle it either way.

Still outstanding on the gate: the in-situ `c_decode` from run C, against your
2.18 us target and the 2.53 us isolated figure this probe reproduces (my #21 said
2.46 us; three runs of the standalone probe today gave 2.53, 2.55 and 3.25 us at
160 threadgroups, so treat the isolated number as 2.5 +/- 0.4 us rather than a
sharp 2.46).

One extra decomposition of the isolated cost, free from the same probe, because
it tells you what a dispatch-count arm would actually buy:

| threadgroups | us/dispatch |
| ---: | ---: |
| 1 | 1.56 |
| 8 | 1.11 |
| 40 | 1.19 |
| 160 | 2.53 |
| 512 | 6.74 |

That is **~1.15 us fixed plus ~11.9 ns per threadgroup** above ~40
threadgroups. The 160-threadgroup figure everyone has been quoting is therefore
*mostly ramp*: 1.15 us of it is fixed cost and 1.4 us is the ramp for that
specific width. A dispatch-count arm that merges two 160-threadgroup dispatches
into one 320-threadgroup dispatch saves the 1.15 us fixed part and none of the
ramp, so the recoverable amount is roughly **half** of what a flat
`count x 2.5 us` model predicts.
