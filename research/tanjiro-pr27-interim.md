# PR #27 interim — M4 instrument gate, the saturation law, and the first ranked receipt

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
4. The M4 fit itself: **DRAM 256.2 GB/s in situ marginal at the grid the
   instrument actually ships** (section 6), i.e. 97.6% of #21's 262.5 GB/s
   sequential control, and **7.40–7.46 TFLOP/s** achieved MLX steel bf16 GEMM at
   `512x8192x2048`. Both inside the ±10% gate you set. The FLOP figure is
   independently corroborated by fern's GPUPROF `attn_proj` steel bf16 at
   6.77 TFLOP/s.
5. **"Per-dispatch cost" is not a constant and the 2.18–2.46 us figure is the
   wrong number to plan against** (section 6). Swept over three barrier regimes
   and five widths, the fixed per-dispatch floor is **0.62 us** and the rest is
   ~13–17 ns per threadgroup. Removing a 160-threadgroup dispatch recovers
   0.6–1.4 us, not 2.2 us, and only if it sat on the dependency path.
6. **Every non-failed official submission publishes its full timings, and the
   feed is readable with our own token** (section 7). That gives us 929 pinned
   baseline measurements — so the real M5 session noise is **1.93% on prefill**
   and **0.34% on decode**, not the 0.497% the brief assumed — and the exact
   `S`/`T` of the current ranked frontier without spending a receipt.
7. **The in-situ dispatch cost obeys a saturation law and the decode path is
   below its knee** (section 8). `dT(n) = max(0, n*c - slack)` with
   `c = 2.64-2.80 us` and `slack = 4.2-4.8 ms`, fitted twice at threadgroup widths
   20x apart, with one confirmed out-of-sample null. The scored decode path issues
   ~406 ops into an absorption region that holds ~1600, so **an arm that only
   reduces MLX op count on the decode path is worth zero**, and your 0.884 ms
   launch-ramp term is not a recoverable line. What is absorbed is **host** time,
   not GPU time: one injected dispatch carrying 1.048 ms of real DRAM traffic
   showed up at 106%, while 600 carrying 1.68 ms of pure launch overhead showed up
   at 1%.
8. **The instrument survives the ranked host** (section 9). Config A's receipt is
   published with `passed_correctness = true`, `max_abs_diff = 0`, both floors
   passed, and `S_A = 103.5678 ms`, `T_A = 4.83241 ms` against a same-session
   `189.0284 / 12.40369 ms` pinned baseline. A deliberately slowed, output-neutral
   candidate is a legal, repeatable probe of the ranked machine.

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
It is pass-to-pass reuse. The pass loop lives *inside the thread*, and after
`perThread` grid strides the index wraps back to where it started, so each
thread immediately re-reads its own addresses. A threadgroup of 256 threads
touches 4 KiB per stride, so its per-pass window is `perThread x 4 KiB`, and
cross-pass hits appear as soon as `resident_threadgroups x window` fits in
cache. Pool size never enters that inequality, which is why "use a 256 MiB pool"
was not sufficient.

**And then the isolated replica misled me a second time.** The table above is an
*average* over 4 passes, so a cold first pass dilutes the cached ones. The fit
uses the **marginal** rate, and the harness measures it directly. Running the
A/B difference in situ at two grids:

| threads | TGs | uint4/thread | window/TG | isolated 4-pass average | **in-situ marginal** |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 131,072 | 512 | 128 | 512 KiB | 247.3 | **245.0** |
| 262,144 | 1024 | 64 | 256 KiB | 262.1 | **339.2** |

339 GB/s is 24% above the hardware peak. The isolated average hid it completely
and I picked 1024 threadgroups off that average, which cost a run. **Only the
marginal rate is diagnostic.** Retract the "262.1 reproduces 262.5 to 0.15%"
claim from my earlier note: it was an average over a partly-cached sweep and the
agreement was a coincidence of dilution.

The shipped configuration is now `2^16` threads = **256 threadgroups** of 256,
256 uint4 each. The reason to prefer it over 512 threadgroups is not the M4
number — the two agree to 1% — it is that at 256 total threadgroups *every*
threadgroup is resident, so the resident working set is the whole 256 MiB pool
and cross-pass reuse is arithmetically impossible at any cache size. That also
makes the error safe in the right direction for M5 Max: more GPU cores means
more resident threadgroups, so a larger machine raises the reuse threshold, and
the configuration with the fewest threadgroups is the one that cannot be fooled
by a cache we have never measured.

Correct reading of #21's control: the honest in-situ marginal is **245 GB/s,
93% of the 262.5 GB/s sequential control**, i.e. this kernel shape gives up 7%
against the best sequential pattern. That is a normal kernel-efficiency figure
and it is what the gate should be judged against, not a suspiciously exact
match.

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

| run | grid | passes | matmuls | empties d/p | S (ms) | T (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| zero | — | 0 | 0 | 0/0 | 583.311 | 9.00680 |
| LA | 2^17 | 1 | 100 | 0/0 | 799.522 | 10.14644 |
| LB | 2^17 | 3 | 300 | 0/0 | 1260.390 | 12.33765 |
| LA2 | 2^18 | 1 | 100 | 0/0 | 802.075 | 10.05949 |
| LB2 | 2^18 | 3 | 300 | 0/0 | 1266.633 | 11.64213 |

All returned `passed_correctness: true`, `max_abs_diff: 0`, `peak_ram_gb: 21`.
The injection is output-neutral as designed.

```
2^17 grid
  DRAM    (T_LB  - T_LA ) = 2.191209 ms for 2 x 268.435456 MB   ->  244.97 GB/s
  matrix  (S_LB  - S_LA ) = 460.869  ms for 200 x 17.1799 GFLOP ->    7.455 TFLOP/s
2^18 grid
  DRAM    (T_LB2 - T_LA2) = 1.582642 ms for 2 x 268.435456 MB   ->  339.22 GB/s  <- cache-served
  matrix  (S_LB2 - S_LA2) = 464.558  ms for 200 x 17.1799 GFLOP ->    7.396 TFLOP/s
```

- **244.97 GB/s at 2^17 is the honest figure: 93.3% of the 262.5 GB/s control,
  -6.7%, inside the 10% gate.** The 2^18 pair is the retraction in section 3:
  339 GB/s is 24% above hardware peak. The FLOP axis is unaffected by the grid
  change and reproduces to **0.8%** across the two independent pairs, which is a
  useful control on the whole differencing method — one axis moved by exactly
  the amount the design change should move it and the other did not move at all.
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

## 6. The shipped grid, and why "per-dispatch cost" is not a constant

Section 3 shrank the sweep grid to `2^16` threads (256 threadgroups of 256
threads, 256 `uint4` per thread) because that is the only width where the
resident set is the whole 256 MiB pool and cross-pass cache reuse is
arithmetically impossible. Re-running the paired fit at the width the
instrument actually ships:

| run | grid | passes | matmuls | empties d/p | S (ms) | T (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| LA3 | 2^16 | 1 | 20 | 0/0 | 614.827 | 10.11366 |
| LB3 | 2^16 | 3 | 20 | 0/0 | 621.122 | 12.20914 |
| LC3 | 2^16 | 1 | 20 | 600/1000 | 619.864 | 10.13248 |

```
DRAM  (T_LB3 - T_LA3) = 2.095475 ms for 2 x 268.435456 MB -> 256.20 GB/s   (-2.4% vs 262.5)
```

**256.20 GB/s is the gate figure: 97.6% of #21's sequential control.** The
`2^17` pair in section 5 reads 245.0 GB/s and the `2^18` pair 339.2 GB/s, so the
same kernel spans 245 - 339 GB/s purely as a function of how much of the pool
one threadgroup re-touches. That spread is the whole reason section 3 exists.

Note also that `LA3 -> LB3` holds the matmul count fixed at 20 and still moves
`S` by +1.024%. That is the **cross-session prefill drift on this host** with
the injected prefill work held constant, and it is the noise term any
prefill-side constant has to beat.

### The isolated dispatch cost, swept properly

MLX's encoder is `DispatchTypeConcurrent` and inserts
`memoryBarrier(scope: .buffers)` only when a dispatch binds an input that an
earlier dispatch in the same encoder recorded as an output. So the isolated
figure is only interpretable if all three regimes are measured. 2000 dispatches
in one command buffer, best of five, microseconds per dispatch:

| threadgroups | no barrier | `memoryBarrier(resources:)` | `memoryBarrier(scope:.buffers)` |
| ---: | ---: | ---: | ---: |
| 1 | **0.624** | 1.735 | 1.400 |
| 8 | 0.730 | 2.034 | 1.494 |
| 40 | 2.083 | 1.959 | 1.501 |
| 160 | 2.788 | 3.400 | 3.036 |
| 512 | 7.223 | 7.128 | 7.144 |

Three things follow, and they change what a dispatch-count arm is worth.

1. **The fixed per-dispatch cost is 0.62 us, not 2.2 or 2.5 us.** The
   `2.5 +/- 0.4 us` I reported in #21 and repeated in section 5 above is the
   *160-threadgroup* number. At 160 threadgroups, 2.16 us of the 2.79 us is
   width, not dispatch: the marginal slope from tg=8 to tg=512 is **13.0 ns per
   threadgroup** and is regime-independent (12.9 ns unbarriered, 12.9 ns
   resource-scoped, 13.3 ns buffer-scoped). The width term is threadgroup
   *scheduling throughput* and it does not disappear when you merge two
   dispatches into one wider dispatch - the same threadgroups still have to be
   launched.
2. **Therefore merging two dispatches of width `w` into one of width `2w`
   recovers only the fixed part.** At `w = 160` that is 0.62-1.4 us out of the
   2.79-3.04 us the pair currently costs, i.e. **20-46%**, not 50% as section 5
   estimated and not 100% as a flat `count x 2.5 us` model implies. At `w = 8`
   (a decode-shaped GEMV) it is 0.73-1.5 us out of 1.46-3.0 us, so narrow
   dispatches are the ones where fusion actually pays.
3. **Barriers cost about 0.8 us each and only at narrow widths.** At tg=1 the
   unbarriered stream runs at 0.62 us and the barriered stream at 1.40 us; by
   tg=512 the three regimes are within 1.3% of each other because width
   dominates. So "MLX inserted a barrier here" is worth ~0.8 us at decode
   widths and nothing at prefill widths.

### RESOLVED in section 8: the in-situ cost obeys a saturation law

Everything from here to the end of section 6 was written before the four
large-lever-arm runs in section 8, which resolve it. The `0.031 us` below is
real but it is *not* the per-dispatch cost — it is the per-dispatch cost seen
from inside an absorption region. Read section 8 for the answer; this
subsection is kept because it records the two hypotheses the follow-up was
designed to separate.

### The in-situ figure is 90x lower and I do not yet trust either number

`LC3 - LA3` puts 600 chained injected dispatches per decode step at
**0.031 us each** (`dT = +0.0188 ms`), against 2.788 us isolated at the same
160-threadgroup width. `dT` is itself within the 0.03 ms decode noise, so this
is an upper bound of ~0.03 us, not a measurement of 0.031 us. The prefill side
(1000 dispatches, `dS = +5.04 ms`, 5.04 us each) is worse: the drift term
measured immediately above is +1.024% = 6.1 ms on this axis, i.e. **larger than
the entire signal**, so `c_prefill` is not measurable at this lever arm on this
host.

I ruled out the barrier explanation before drawing any conclusion: the table
above shows that even *fully unbarriered* at tg=160 the cost is 2.788 us, so
"MLX is not barriering my chain" cannot get from 2.788 to 0.031.

Three hypotheses survive, and only the third is good news:

- **(a) The injected dispatches are not executing.** MLX is lazy; the chain
  tail is the only array handed to `asyncEval`, and if the chain is not a real
  dependency in MLX's graph the interior could be dropped. Discriminator:
  cost per dispatch stays at ~0 when the count is raised.
- **(b) They execute but overlap completely.** The injected chain is
  independent of every model tensor, so the GPU can schedule it into whatever
  command- and threadgroup-scheduling capacity the real stream leaves idle.
  Discriminator: cost per dispatch stays at ~0.031 us and `dT` scales linearly
  with count until saturation, then jumps.
- **(c) The real decode stream has spare dispatch capacity.** Same observation
  as (b) but read as a property of the workload rather than of the probe.

A 4000-decode / 20000-prefill run is in flight to separate these: `~0 ms`
means (a), `~0.12 ms` means (b)/(c) with a linear law, `~11 ms` means the
isolated number was right all along and the 600-dispatch run was broken.

**What this already does to your decode budget.** Your 0.884 ms launch-ramp
term is `406 x 2.18 us`. Two independent corrections push it down hard: the
fixed per-dispatch cost is 0.62 us rather than 2.18 us (which alone takes the
term to 0.25 ms), and the width-dependent remainder is not recoverable by
fusion. Unless the real dispatches are much wider than 160 threadgroups - which
for decode GEMVs they are not - **the recoverable launch-ramp budget is a few
hundred microseconds, not 0.884 ms.** Even in the most favourable reading, an
arm that removes `n` decode dispatches should be priced at `n x 0.6 us`, and
only for dispatches that sit on the dependency path.

### Caveat I want on the record

Both the isolated probe and the injected kernel store nothing - the single
store sits inside `if (control[0] == 0xFFFFFFFFu)`, which is never true. A
threadgroup that early-exits without touching memory may retire faster than a
real one, which would make both numbers *lower* bounds on a real dispatch's
fixed cost. The relative decomposition (fixed vs per-threadgroup vs barrier) is
unaffected because all three regimes and all five widths use the same body.

## 7. The official receipt feed is public, and it re-prices the noise floor

`GET https://api.mlx.fast/api/benchmarks/eigenlabs%2Fmlxfast-challenge/submissions`
with our own bearer token returns **all 1399 submissions to date with complete
`officialMetrics`** - every field the ranked receipt carries, including
`prefill_seconds_per_token`, `decode_seconds_per_token`, the paired
`baseline_*`, `passed_correctness`, `max_abs_diff`, `gpqa_ttft_seconds`,
`benchmark_wall_seconds`, `peak_ram_gb`, the semantic-GPQA fields and the
`expert_*` diagnostics. Analysis script: `research/tanjiro-receipt-mine.py`.

Status split: 467 `failed`, 789 `rejected`, 140 `accepted`, 3 `validating`.
**`rejected` runs publish full metrics; only `failed` runs (a CI workflow step
that errored before the timed phase) publish none.** So a receipt is lost only
by failing a workflow step, not by scoring badly.

Four things this gives us for free.

**1. The M5 session noise floor, from 929 measurements of the same pinned
baseline.**

| axis | mean | sd | sd/mean | range |
| --- | ---: | ---: | ---: | --- |
| baseline `S` (prefill, ms) | 190.6091 | 3.6757 | **1.928%** | 185.817 - 203.080 |
| baseline `T` (decode step, ms) | 12.3655 | 0.0425 | **0.344%** | 12.2375 - 12.5452 |

The brief assumed 0.497% on both axes. Prefill is **4x noisier than that**, and
it enters `prefill_speedup` through the baseline slot, where we have no control
over it. Decode is 1.4x *better* than assumed. Two consequences: (i) a
prefill-only arm worth less than about 2% is not distinguishable in a single
official receipt no matter how clean the candidate is, and (ii) the 0.952 lower
edge of the `prefill_speedup` calibration band is roughly 2.5 baseline sigmas
from 1.0, which is why prefill regressions show up as band violations more
often than decode ones.

**2. The instrument's premise is verified against real data, not argued.** The
worst published receipt in the whole feed, `6447b89c`, scored 1.0004 - **39.2%
of the current best (2.552308)** - and still published complete metrics.
Observed ranges: `decode_speedup` 1.0097 / 2.0201 / 2.7421 (min/median/max),
`prefill_speedup` 0.9524 / 1.7982 / 2.0634, against a 0.95 hard floor. My
config-A injection lands at roughly `decode_speedup 2.40` and
`prefill_speedup 1.73`, i.e. about 2.5x clear of both floors. There are **zero
correctness failures and zero floor failures in 1399 submissions**, so the
floors are not where receipts die.

**3. Where receipts actually die**, by failing workflow step: 208 "Timed paired
benchmark (measure-job)", **73 "Review submitted code for benchmark bypasses"**,
49 workflow timeout, 47 correctness/hidden gates, 28 public behaviour gate, 17
overlay paired timing, 15 semantic GPQA, 13 modifiable surface. The bypass
review is the live risk for a deliberately-slowed instrument candidate, which
is exactly why the submission note documents the injection in full.
`benchmark_wall_seconds` is 33 / 45 / 50 (min/median/max) so the timeout is not
a risk, and `gpqa_ttft_seconds` is 0.26 / 0.32 / 0.60 against a 2.5 s gate, so
there is at least 4x headroom even on the slowed tree.

**4. The ranked frontier's actual `S` and `T`, which nobody had.** Top five by
score, converted with the brief's own formulas:

| submission | score | S (ms) | T (ms) |
| --- | ---: | ---: | ---: |
| `46eeccf0` | 2.552308 | 97.560 | 4.3449 |
| `8415f63c` | - | 97.820 | 4.3587 |
| `2df3a1d6` | - | 98.026 | 4.3271 |
| `0929b324` | - | 97.649 | 4.3331 |
| `21f1d1a3` | - | 97.810 | 4.3337 |

**The decode-step budget on M5 is ~4.35 ms, not the 8.545 ms in the brief** -
that figure is an M4 measurement. Every per-step term in the roofline
(34.32 ms DRAM, 0.884 ms launch ramp, the per-family shares) needs rescaling to
a 4.35 ms step before it can be used to rank arms, and a term that was 10% of
8.545 ms is 20% of 4.35 ms. The five frontier trees agree on `T` to 0.7% and on
`S` to 0.5%, which is tighter than the baseline-slot noise above and confirms
the candidate slot is the quiet one.


## 8. RESOLVED: in-situ dispatch cost is a saturation law, not a constant

The 600-dispatch result in section 6 was measured from inside an absorption
region. Raising the lever arm four ways settles it. All runs have
`sweeps = 0, matmuls = 0`, so the reference is the zero-injection control
(`S = 583.311 ms`, `T = 9.00680 ms`); all returned `passed_correctness: true`
and `max_abs_diff: 0`.

| run | tg | n (decode) | S (ms) | T (ms) | dT vs zero (ms) | dT/n (us) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| LC3* | 160 | 600 | 619.864 | 10.13248 | 0.0188 | 0.031 |
| LE | 160 | 2000 | 575.182 | 10.93761 | 1.9308 | 0.965 |
| LD | 160 | 4000 | 588.450 | 16.54604 | 7.5392 | 1.885 |
| LH | 8 | 2000 | 562.166 | 11.22364 | 2.2168 | 1.108 |
| LF | 8 | 8000 | 576.764 | 27.05580 | 18.0490 | 2.256 |
| LG | 512 | 4000 | 573.317 | 31.99681 | 22.9900 | 5.748 |

`*` LC3 also carried `sweeps = 1, matmuls = 20`; its `dT` is differenced against
LA3, which carried the same, so it is still a clean 600-dispatch delta.

The apparent per-dispatch cost rises 60x across the first three rows at fixed
width. A constant-cost model cannot produce that. A **saturation law** fits all
of it:

```
dT(n) = max(0, n * c  -  slack)
```

Fitting `c` and `slack` from the two saturated tg=160 points (LE, LD), with no
assumption imported from the isolated probe. The `n = 0` reference has to be LA3
(`T = 10.11366`, sweeps 1 / matmuls 20), not the zero-injection control, because
LE and LD both carry the sweep's +1.107 ms too; using the control instead
double-counts the sweep inside `slack` and under-reports it by exactly 1.107 ms:

```
c_decode(tg=160) = (16.54604 - 10.93761) ms / (4000 - 2000) = 2.804 us
slack            = 4000 * 2.804 us - (16.54604 - 10.11366)  = 4.784 ms
```

and then LC3 is a genuine out-of-sample prediction: `600 * 2.804 us = 1.682 ms`
is below the 4.784 ms slack, so the law predicts `dT = 0` and the measurement is
`+0.0188 ms`, i.e. **zero to within the 0.03 ms decode noise floor.** Three
points, two parameters, one prediction confirmed.

### The cost is width-independent below ~160 threadgroups

The tg=8 width has two counts of its own (LH, LF), so `c` and `slack` can be
fitted there **independently**, importing nothing from the tg=160 pair:

| tg | fitted from | **`c` (us)** | **`slack` (ms)** | knee (dispatches) |
| ---: | --- | ---: | ---: | ---: |
| 8 | LH (2000), LF (8000) | **2.639** | **4.167** | 1579 |
| 160 | LE (2000), LD (4000) | **2.804** | **4.784** | 1706 |

Two independent two-parameter fits at widths 20x apart agree to **6% on `c`**,
13% on `slack` and 8% on the knee. That is the strongest evidence that the law is
real and not an artifact of one configuration. Taking `slack ~ 4.5 ms` for the
third width:

| tg | isolated, no barrier | **in-situ `c`** | in-situ / isolated |
| ---: | ---: | ---: | ---: |
| 8 | 0.730 us | **2.639 us** | 3.62x |
| 160 | 2.788 us | **2.804 us** | 1.01x |
| 512 | 7.223 us | **6.667 us** | 0.92x |

The in-situ cost is **flat at 2.64-2.80 us from tg=8 to tg=160**, then picks up
`(6.667 - 2.804) / 352 = 11.0 ns` per extra threadgroup — which is the same
slope the isolated probe shows (13.0 ns/TG). So the in-situ cost decomposes as

```
c(tg) ~= 2.75 us  +  11 ns * max(0, tg - 160)
```

against the isolated probe's `0.62 us + 13 ns * tg`. **The isolated probe misses
a 2.1 us width-independent term that only exists inside the real runtime.**
That term cannot be GPU threadgroup scheduling, because it does not scale with
threadgroup count. It is MLX per-op framework cost: graph-node construction, the
Swift/C++ boundary, a fresh output allocation per op, the encoder's
barrier bookkeeping, and its every-50-ops command-buffer commit.

### What the two numbers actually mean for the programme

**Answer to your question.** In-situ `c_decode` is **2.72 +/- 0.09 us** for any
dispatch up to ~160 threadgroups, from two independent two-parameter fits at
widths 20x apart. Against your 2.18 us target that is +25%, and against your
1.9-2.4 us confirmation band it is 13% above the top. Against the same-day
isolated measurement at the same width (2.788 us) it agrees to 0.6%.
I think the honest reading is that your 2.18 us was low because it was derived
from a 160-threadgroup isolated figure while implicitly being used as a
per-op constant, and those happen to coincide only at tg=160.

**This makes op-count reduction more valuable than section 6 concluded, not
less.** Section 6 argued from the isolated probe that merging two narrow
dispatches recovers only the 0.62 us fixed part. That was wrong: in situ the
fixed part is 2.75 us and it is fully width-independent, so merging two
tg=8 dispatches into one recovers the whole 2.75 us, and merging two tg=160
dispatches into one tg=320 dispatch recovers 2.75 us minus the 11 ns/TG the
merged dispatch now pays above 160, i.e. about 0.99 us. Narrow decode-shaped
dispatches are where fusion pays, and it pays 4x more than the isolated probe
suggests.

**But it only pays above the saturation knee, and today we are below it.** The
4.2-4.8 ms slack is the load-bearing number here. On this host a decode step is
9.007 ms and absorbs 4.784 ms / 2.804 us = **1706 additional dispatches at zero
cost** (1579 at tg=8, an 8% spread). The scored path issues roughly 406. So the
decode stream is running at about a quarter of its dispatch-absorption capacity,
and *removing* a dispatch from it converts 2.75 us of overhead into 2.75 us of
extra slack, not into 2.75 us of saved wall time. That is the single most
important consequence of this measurement:

- **An arm that only reduces MLX op count on the decode path should be priced at
  zero** until the op count is high enough to saturate, and this path is 4.2x
  below saturation.
- The 0.884 ms launch-ramp line in your decode budget is therefore **not a
  recoverable term.** It is not even the right magnitude: `406 * 2.72 us =
  1.10 ms` of per-op overhead exists, but it is hidden inside a 4.5 ms
  absorption region, so it is not on the critical path and removing it recovers
  nothing measurable.

### What is being absorbed is host time, not GPU time

This distinction decides how the slack can be spent, and the instrument already
answers it without another run. Compare the two things it injects:

| injected | GPU work | dispatch overhead | appeared in `T` |
| --- | ---: | ---: | ---: |
| 1 DRAM sweep dispatch (`LA3 - zero`) | 1.048 ms | 2.8 us | **+1.107 ms = 106%** |
| 600 empty dispatches (`LC3 - LA3`) | ~0 | 1.68 ms | **+0.019 ms = 1%** |

One dispatch carrying 1.048 ms of real memory traffic shows up in full — 106%,
the extra 6% being the 0.044 ms cache-pollution term measured in section 5. Six
hundred dispatches carrying 1.68 ms of pure launch overhead and no memory
traffic show up not at all. **So the GPU is the critical path and has no idle
time to give; the absorbed resource is host-side.** The CPU encode thread runs
about 4.5 ms per decode step ahead of the GPU, and extra MLX ops spend that lead
at 2.72 us each until it is gone.

That kills the reading I would otherwise have preferred. The free budget is
**not** ~1300 dispatches' worth of free *GPU* work — any GPU work an extra op
performs is paid in full, immediately, as the sweep row proves. The free budget
is ~1700 ops' worth of free *host-side op construction*. Concretely:

- Building masks, RoPE tables, dequantisation state or resident views inside the
  scored step is free only to the extent it is host bookkeeping. If it dispatches
  real kernels, those kernels cost their full GPU time.
- Any arm whose mechanism is "issue fewer MLX ops" is worth zero here.
- Any arm whose mechanism is "do less GPU work" is worth its full arithmetic
  value, with no launch-overhead discount and no absorption.
- The one genuinely free lever is moving host work *into* the step from
  elsewhere, or restructuring so that host-side latency that currently blocks
  the GPU stops blocking it. There is 4.5 ms of head-room for the former and, by
  the same measurement, nothing to win from the latter today.

### Prefill absorbs more, and then the instrument stops behaving

Prefill is one forward pass over 512 tokens, so the injection lands as n
dispatches inside a single pass. Three counts, against the 571.857 ms mean of the
four zero-prefill-injection runs in this section (spread 1.16%):

| run | prefill empties | S (ms) | dS (ms) | serialised at 2.804 us | marginal us/dispatch |
| --- | ---: | ---: | ---: | ---: | ---: |
| LD | 20000 | 588.450 | +16.59 | 56.1 | **0.83** |
| LJ | 50000 | 873.950 | +302.09 | 140.2 | **6.04** |
| LI | 100000 | 922.739 | +350.88 | 280.4 | **3.51** |

The 20000-dispatch point behaves like the decode axis: 70% of the serialised cost
is absorbed, so **prefill slack is at least 39.5 ms per 512-token forward**, about
7% of the 583 ms pass, and a prefill arm that only removes dispatches is worth
nothing there either.

Above that the instrument contradicts itself. 50000 dispatches cost **2.2x more
than serialised**, and 100000 cost less per dispatch than 50000 — non-monotonic in
the marginal rate, 7x apart across the three counts. Two dispatches out of every
hundred-thousand are not becoming more expensive than a real kernel launch;
something else is entering, most plausibly encoder/command-buffer pressure or
clock throttling once a single pass carries 1250-2500 dispatches per layer. Two
consequences:

- The honest prefill result is the 20000-dispatch bound, not a `c_prefill` value.
  The 3.9-4.2 us two-point fits I computed from the (20000, 100000) and
  (20000, 50000) pairs are **not** hardware constants and should not be quoted.
- The prefill dispatch axis must not be spent on an official receipt. An
  instrument that disagrees with itself by 7x on the development host cannot be
  read on a machine where I get one point per receipt.

This is the second design error the M4 gate has caught before it cost a receipt,
after the 600-dispatch absorption trap.

### Consequences for the official configuration plan

The M5 decode step is ~4.35 ms (section 7), roughly half this host's 9.007 ms.
If the slack scales with the step, M5 absorbs about
`3.678 * 4.35 / 9.007 = 1.78 ms`, i.e. ~650 dispatches. **My planned config C
(600 decode empties, 1000 prefill empties) therefore sits inside the M5
absorption region and would have measured nothing** — it would have burned an
official receipt to reproduce the 0.031 us artifact on a second machine. This
is exactly the failure the M4 gate exists to catch, and it caught it.

The first revision was therefore two saturated points instead of one, so that `c`
comes from their difference and needs no assumption about the M5 slack. Config
A's receipt then showed even that does not fit under the floor; section 9 has the
final plan.

## 9. Config A's receipt, and what it forced

Submission `ff29f5c2-fdc2-4035-af6b-17e8a69c2d87`, created 16:06:06Z, resolved
16:42:52Z (37 min), status `rejected` — **with the full metric block published,
exactly as section 7 predicted from the 789 other rejected runs.**

| field | value |
| --- | ---: |
| **`S_A`** | **103.5678 ms** |
| **`T_A`** | **4.83241 ms** |
| baseline `S` | 189.0284 ms |
| baseline `T` | 12.40369 ms |
| `prefill_speedup` / `decode_speedup` | 1.82517 / 2.46041 |
| both speedup floors | passed |
| `passed_correctness` / `max_abs_diff` | true / 0 |
| `gpqa_ttft_seconds` | 0.42 (gate 2.5) |
| `semantic_gpqa_passed` | true |
| `benchmark_wall_seconds` | 47 |
| `peak_ram_gb` | 21 |

The protocol works: **a deliberately slowed, output-neutral candidate passes every
correctness gate on the ranked host and returns a complete receipt.** The
instrument is validated end to end.

It also says both levers were sized an order of magnitude too small:

- the 5 best published receipts put the frontier decode step at 4.340 +- 0.012 ms,
  so `A`'s single 268.44 MB sweep cost only ~0.49 ms of the 4.832 ms step, i.e. an
  apparent 550 GB/s — at M5 Max's nominal peak, and resting on an assumed base;
- `A`'s 20 GEMMs cost `103.57 - (96.8 +- 5) = 7 +- 5 ms` for 343.6 GFLOP, i.e.
  **26-69 TFLOP/s** — a 2.6x-wide bracket, useless as a denominator.

`T_A` also re-prices the whole dispatch question. The hard decode floor allows
`12.40369 / 0.95 - 4.83241 = 8.22 ms` of injected slowdown, i.e. **at most ~2300
extra dispatches** at this host's 2.8 us. The M4 knee alone is ~1600. So two
saturated decode points cannot both fit under the floor, and `c_decode` on M5 is
not bracketable the way it was on M4.

Final official plan, with the prefill dispatch axis dropped entirely:

| config | sweep passes | matmuls | decode empties | prefill empties | status |
| --- | ---: | ---: | ---: | ---: | --- |
| A | 1 | 20 | 0 | 0 | receipt above |
| B | 7 | 120 | 0 | 0 | `553ef9f0-df2b-4c7f-9308-ef8acd24a816`, validating |
| C | 1 | 20 | 600 | 0 | queued |
| D | 1 | 20 | 1800 | 0 | queued |

```
BW_M5       = 1610.612736 MB   / (T_B - T_A)      6 extra sweep passes
FLOP/s_M5   = 1717.986918 GFLOP/ (S_B - S_A)      100 extra GEMMs
c_decode_M5 = (T_D - T_C) / 1200                  if both are above the knee
slack_M5    = 1800 * c_decode_M5 - (T_D - T_A)
```

`B`'s magnitudes are the largest that clear both floors across the entire
plausible hardware range: `T_B` is 11.3 ms at a pessimistic 150 GB/s against the
13.02 ms limit, and `S_B` is 169.6 ms at a pessimistic 26 TFLOP/s against the
200.60 ms limit. That turns a 15-30% measurement into 5-12%.

`C`/`D` no longer try to bracket `c`. They ask the question that actually decides
programme priorities: **is the ranked decode path above or below its
dispatch-absorption knee?** Both outcomes are publishable:

- both null: M5 absorbs >= 1800 dispatches of launch overhead for free, which
  prices every "issue fewer MLX ops" decode arm at zero on the ranked host as
  well as here;
- either positive: `c_decode` and `slack` fall out directly.

Both keep `S` at `A`'s value, so the prefill axis is untouched and the `S/128`
term in `T` cancels exactly against `A` rather than approximately.

### The scaled-up lever re-gated on M4 before B's receipt lands

The shipped B defaults were run once on this host, so the 6x larger levers are
gated the same way the small ones were. `S = 853.829 ms`, `T = 16.89766 ms`,
`passed_correctness = true`, `max_abs_diff = 0`, `peak_ram_gb = 21`:

| constant | small lever (section 6) | large lever (config B) | agreement |
| --- | ---: | ---: | ---: |
| DRAM GB/s | 256.20 | **237.4** | -7.3% |
| bf16 GEMM TFLOP/s at `512x8192x2048` | 7.40-7.46 | **7.188** | -3.2% |

A 6x change in the injected magnitude moves the extracted rates by 3% and 7%.
That is the linearity check the instrument needs, and it is also the second
correctness pass at the shipped magnitudes: 120 GEMMs and 7 sweep passes per step
change no token. The bandwidth drop is in the expected direction — 7 passes is
1.88 GB of sustained streaming in a single dispatch rather than 268 MB, so it
holds the memory system at full load long enough to lose a little clock — and
both numbers remain ~90% of #21's 262.5 GB/s sequential control.

### The cross-session trap, and why every fit is a difference

One more reason not to read absolute numbers across receipts: this host's `S`
drifted **7% between run batches** (615-621 ms in one batch, 562-588 ms in the
next, same code) while `T` held to 0.19%. On the ranked host the published
baseline absorbs that, because it is measured in the same session as the
candidate: section 7's 929 pinned baselines have `sd(S) = 1.93%` and
`sd(T) = 0.34%`. So a candidate-only `S` comparison across two submissions
carries the full 1.93% session term (~2 ms), which is why `B`'s prefill lever was
sized to 25-66 ms rather than the 6.8 ms `A` used.

