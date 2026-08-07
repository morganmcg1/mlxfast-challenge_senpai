# PR #215 — NAX gather-GEMM: chunk-accurate staged-byte census + K-loop register prefetch

Assignment `maple-2026-08-07d-nax-kloop-pipeline`, revision `r1`.
Base `747d130be532383d3eabd190f54f8b1b2bc6f9fd` on
`codex/mlxfast-maple-20260804-advisor`.

Two parts. **Part A** is an offline census that re-derives how many bytes the
routed NAX gather-GEMM actually stages during the shipped 512-token prefill, and
therefore what fraction of peak bandwidth the kernel achieves. **Part B** is the
mechanism the census points at: a K-loop software pipeline that issues the
device reads for iteration `k+1` before the MMA chain for iteration `k`, so the
device latency stops being serialized behind every barrier.

---

## 0. Headline

Part A reproduces the advisor's pre-registered chunk-accurate table to within
**0.009 %**, and then corrects four things the corpus had wrong. The most
valuable correction makes the prize *bigger*: the carried all-slots byte count
(17.66641 GB) overstates real staged traffic by **16.1 %**, so the streaming
floor is 24.15 ms rather than 28.77 ms and the headroom inside the marginal
window `W = 43.2619 ms` is **19.11 ms**, worth up to **7.16 % of score** at the
corrected prefill elasticity (§A.10) — about **14×** the 3σ detection threshold.

Part A also produces a structural finding that independently kills the "67 % of
both roofline axes" ridge identity: **the M axis of this kernel is padded twice,
at two different granularities.** Staging and barriers are quantized to `BM=64`
(all 128 threads stage, unconditionally, outside the `sg_active` guard) while
MMA is quantized to `SM=16` (`sg_active` gates the A-tile load and the whole MMA
chain). A 3-row expert stages a full 64×64 tile on all 32 k-iterations while
issuing MMA on one of four simdgroups. Byte waste and FLOP waste therefore
cannot share a padding factor, and any identity that assumes they do is
ill-formed.

Part B is implemented, compiles and links for both ranked shapes, and is
verified bit-exact-by-construction with a basic-block-level IR proof. It adds
**zero barriers, zero MMA work, zero device stores and zero threadgroup memory**.
It is a receipt-only experiment: this host cannot dispatch the kernel at all.

**Part B is a clean, mechanistically explained negative, and that is the
deliverable.** On the ranked M5 the depth-1 pipeline is bit-exact — every hidden
correctness gate, both speedup floors, GPQA TTFT and the semantic judge pass, with
`max_abs_diff = 0` — and it moves the prefill axis by **+0.684 ms (+1.52σ)** against
its own same-session paired control, against a pre-registered **−7.6σ to −27.2σ**.
Any real gain above 0.665 ms is excluded at 3σ, so the entire predicted 450–614 GB/s
region is outside the confidence interval. The advisor's mandatory zero-receipt
Step-0 diagnostic shows threadgroup memory, `maxTotalThreadsPerThreadgroup`,
execution width and implied occupancy **bit-identical** between control and arm, which
by its pre-registered reading rules out register pressure and leaves added instruction
count in an issue-limited K-loop. **§6.9 therefore closes the `_nax` in-kernel
staging / prefetch / double-buffering family**: this loop is limited by memory-op
*issue*, not by exposed *latency*, and reordering loads conserves instruction count by
construction. §6.10 names the successor that instead *removes* load issues —
amortizing the two per-iteration scale-byte loads into one aligned 16 B load covering
four k-iterations, taking loads/thread/iteration from 3 to 1.25 with zero byte change.

The 19.11 ms of §A.9 headroom is untouched by this closure. It was the wrong
instrument, not a wrong prize.

---

## Part A — chunk-accurate staged-byte census

Deliverable: `research/tanjiro-nax-staged-byte-census.py` (runs clean, exit 0).

### A.1 Reproduction of the pre-registered table

| accounting | chunks `n` | staged bytes | rate @ `W`=43.2619 ms | % of 614 GB/s |
|---|---:|---:|---:|---:|
| chunk-accurate, 38 layers | 8379 | 14.8264 GB | 342.7 GB/s | 55.8 % |
| nonzero-expert floor, 38 layers | 7757 | 13.7258 GB | 317.3 GB/s | 51.7 % |
| all-slots (analytic), 38 layers | 9728 | 17.2134 GB | 397.9 GB/s | 64.8 % |
| chunk-accurate scaled to 39 layers | 8599.5 | 15.2166 GB | 351.7 GB/s | 57.3 % |

Max deviation from the advisor's pre-registered numbers: **0.009 %**.

### A.2 The per-chunk staging model, and its independent cross-check

Ranked instantiation is `BM=64, BN=64, BK=64, WM=4, WN=1` → 128 threads per
threadgroup.

* fused `gate_up`: `N=1024, K=2048` → 16 column tiles × `K_it=32` = 512
  cooperative `load_unsafe` calls
* `down`: `N=2048, K=512` → 32 column tiles × `K_it=8` = 256 calls

**768 calls per chunk × 2304 B per call = 1,769,472 B per chunk**, which is
exactly `3 × 512 × 2048 × 0.5625` (nvfp4: 4 bits of weight + 8 bits of scale per
group of 16 → 0.5625 B/value). The split is exactly 66.67 % gate/up, 33.33 %
down.

This is confirmed from the other direction by the route artifact:
`Σ chunk_dram_bytes × chunk_threadgroup_iterations = 14,826,405,888 B`, and
`8379 × 1,769,472 = 14,826,405,888 B`. Two independent derivations, byte-exact.

### A.3 The 38-vs-39 layer question — RESOLVED

`LagunaConfig.swift` gives 40 hidden layers with layer 0 dense, so the model has
**39 sparse MoE layers**. But the shipped 512-token prefill dispatches the routed
NAX gather-GEMM only **38 times**, and the reason in the corpus is wrong.

The real reason is not "because layer 0 is dense" alone. **Layer 39 diverts to an
M=1 GEMV path.** `LagunaRuntimeModel.swift:10862-10864` routes to
`callLastPrefillRow` when `h.dim(1) > 1` and the mask is `.causal`; that calls
`mlp(...)` on a single row (`:10504-10507`, `:10436`). So layers 1–38 take the
gather-GEMM and layer 39 does not.

Corpus files that state or imply the wrong reason, or hardcode 38 without
provenance:

* `research/h5-per-expert-fused-ffn-closure.md:27-29` — gives the reason as
  "because layer 0 is dense". That accounts for one of the two missing layers,
  not both.
* `research/artifacts/README-route-histogram.md:24-25` and `:31`
* `research/lpt_expert_queue_sim.py:48` — bare `38`
* `research/route_histogram.py:41` — bare `38`

### A.4 Basis conversion

Everything published on a 39-layer basis has to be rescaled to the 38 layers the
prefill actually dispatches.

| quantity | 39-layer (published) | 38-layer (shipped prefill) |
|---|---:|---:|
| weight bytes, all-slots | 17,666.41 MB | **17,213.42 MB** |
| useful GFLOP | 1005.02 | **979.25** |
| implied BW at `W`=43.2619 ms | 408.4 GB/s | **397.9 GB/s** |
| chunk-accurate bytes | 15.2166 GB | **14.8264 GB** |

Per-layer unit: **452.985 MB** and **25.775 GFLOP**.
`VALUES_PER_EXPERT = 3,145,728`; `FLOP_PER_ROW = 6,291,456`.

Caveat: layer 39's scale plane is not byte-identical to the others — it falls
back to the uint8 bank under the `maxCode <= 63` rule — so the rescale is
accurate to well within σ but is not exact.

### A.5 `dS_1 = 43.2619 ms` — two corrections

The `dS_1` figure comes from PR #34's injection instrument
(`research/tanjiro-pr34/instrument.patch`), with
`lagunaInjectBankRotation = 20` and a **39-modulus** routed-bank map, so there
are exactly 39 injected copies and the map is bijective.

**(a) BASIS — the carried rescale has the wrong sign.** The correctly signed
rescale to the shipped basis is

```
43.2619 × 38/39 = 42.1526 ms      (DOWNWARD)
```

The `× 40/39 = 44.371 ms` proposal at
`research/tanjiro-pr34-r2-result.md:701-705` is **wrong**: it scales up toward 40
layers when the shipped prefill dispatches 38.

**(b) SCOPE — `dS_1` prices more than the kernel.** `dS_1` measures
`lagunaFusedSortedRoutedGateUp` end to end: sort/scatter, the gate_up
gather-GEMM, and down. PR #170's `W` is attributed to
`fp_gather_qmm_rhs_expert_nax` alone. So `dS_1` is an **upper** bound on the
denominator, and every rate computed against it is a **lower** bound on achieved
GB/s. The next read to tighten this is the sort's share at
`research/maple-tanjiro-pr91-prefill-budget-census.md:468`
(`sort_scatter | 154`).

### A.6 The 34.7 TFLOP/s "ceiling" is circular — CONFIRMED

`34.7 TFLOP/s` was back-solved from this kernel's own arithmetic intensity:
`34700 / 610 = 56.89 FLOP/B`. It is not an independent hardware limit. The
corpus's non-circular compute ceiling is **56 TFLOP/s**. The ridge identity that
rested on it was already formally retired at
`research/CURRENT_RESEARCH_STATE.md:1150-1157`; this confirms why.

### A.7 New structural finding — the M axis is padded twice

This is the part of Part A that generalizes beyond the census.

* **Staging and barriers are quantized to `BM = 64`.** `loader_w.load_unsafe()`
  is issued by all 128 threads, *before and outside* the `sg_active` guard.
* **MMA is quantized to `SM = 16`.**
  `sgp_sm = min(int(SM), max(0, int(chunk_rows) - int(tm)))`,
  `sg_active = sgp_sm > 0`, `tm = SM * (simd_group_id / WN)` ∈ {0,16,32,48}.
  `sg_active` gates both the A-tile load and the MMA chain.

So a 3-row expert stages a full 64×64 weight tile on all 32 k-iterations, but
only 1 of 4 simdgroups issues any MMA. **Byte waste and FLOP waste are quantized
at different granularities and cannot share a padding factor.** The measured
padding factors bear this out: FLOP padding **1.4556**, byte padding **3.4453**.

Roofline on the 38-layer basis: useful FLOP **979.25 GFLOP** (× 39/38 = 1005.02,
consistent), executed FLOP **1425.39 GFLOP**, staged **14.8264 GB**. Achieved
**55.8 %** of peak bytes versus **58.8 %** of executed FLOP. The "67 % / 67 %"
ridge is dead.

### A.8 The dead-bytes branch is refuted by construction

The hypothesis that empty expert slots waste DRAM bytes is **false for this
kernel**: the chunk loop never executes for a zero-row expert, so the loader is
never constructed and no bytes are staged. The 1349-chunk / 2.3870 GB difference
between the all-slots ledger and the chunk-accurate census is a ledger
bookkeeping artifact, not real traffic.

What empty and near-empty slots *do* cost is the **pure load-issue term** —
6.887 ms, **15.9 % of `W`** — isolated by PR #170's S3 arm. That is exactly what
Part B attacks.

### A.9 Two denominators, and the coincidence trap

Two rates appear in the assignment and they are **not** in conflict; they have
different denominators.

| | expression | value | % of 614 GB/s |
|---|---|---:|---:|
| (a) advisor's table | 14.8264 GB / 43.2619 ms | **342.7 ± 3.6 GB/s** | 55.8 % |
| (b) assignment's value table | 14.8264 GB / (43.2619 − 6.887) ms | **407.6 ± 4.2 GB/s** | 66.4 % |

(a) charges the whole marginal window. (b) charges only the byte-limited part,
having removed the 6.887 ms pure-issue term.

**TRAP.** The old headline `17.66641 / 43.2619 = 408.4 GB/s` is numerically
almost identical to (b)'s 407.6 GB/s. They are completely different
measurements — one uses inflated bytes over the full window, the other uses real
bytes over the byte-limited window — and the near-equality is a coincidence. Do
not treat agreement between them as corroboration.

### A.10 What Part A is worth, at the corrected prefill elasticity

**The prefill elasticity used across this campaign was wrong, and wrong in our
favour.** The retired value 0.2554 % of `officialScore` per ms removed from `S`
counted only the prefill axis. The correct value is **0.374750 % per ms**,
because the *decode* timing window contains a full 512-token seed prefill.

Source, in the trusted harness
`Sources/MLXFastTrustedHarness/LagunaRuntimeBenchmark.swift`: `measureWorkerDecode(...)`
begins at `:946`; the clock starts at `:966`; `worker.beginDecode(seedTokens:)`
is called at `:968`, i.e. **inside** the window; the progress line at `:980-:982`
emits `includes_seed_prefill=true`; and the reported value at `:1010`/`:1013` is
`measuredSeconds / decodeSteps` with `decodeSteps = 128`. So the published decode
metric is not a pure per-step cost but

```
decode_seconds_per_token = 4 * prefill_seconds_per_token + T
```

with the factor 4 = 512 seed tokens / 128 decode steps, and `T` the true
marginal per-step decode cost.

Verified against the promoted receipt `97a5090` to the last printed digit:

```
4 * 0.00019120068359375 + 0.004143569335937499 = 0.0049083720703125
                                                = decode_seconds_per_token   ✓
exp(0.75*ln(2.820661) + 0.25*ln(2.001471))      = 2.588828 = officialScore   ✓
```

A millisecond removed from `S` is therefore paid **twice**: 0.25537 %/ms on the
prefill axis plus 0.11938 %/ms through the amortized seed prefill on the decode
axis, which carries 75 % of the weight. Total **0.374750 %/ms**. Discrete check:
dropping `S` by 8.26 ms moves the score to 2.672902, i.e. **+3.2476 %**.

With that price:

Streaming floor at 614 GB/s = **24.15 ms**. Headroom inside `W` = 43.2619 −
24.15 = **19.11 ms**, i.e. up to **7.16 % of score** (19.11 × 0.374750).
σ(`W`) = √2 × 0.318 = **0.4497 ms** (1.04 % of `W`), so 3σ = 1.35 ms and the
headroom is **14.2×** the detection threshold. The smallest detectable win is
itself worth 1.35 × 0.374750 = **0.51 % of score**.

Re-priced outcomes for Part B, at the same achieved-bandwidth targets. Each row
holds the 6.887 ms pure-issue term of §A.9 **fixed** and improves only the
byte-limited part, i.e. `W' = 14.8264 GB / rate + 6.887 ms`:

| outcome | implied rate | ΔS | old (retired) price | corrected price |
|---|---:|---:|---:|---:|
| modest pipeline win | 450 GB/s | −3.43 ms | +0.88 % | **+1.29 %** |
| solid pipeline win | 500 GB/s | −6.72 ms | +1.72 % | **+2.52 %** |
| byte-limited ceiling | 614 GB/s | −12.23 ms | +3.12 % | **+4.58 %** |

Note that this table is *conservative* for Part B specifically. Holding the
6.887 ms issue term fixed is the right convention for a bandwidth-side
improvement, but a K-loop software pipeline attacks exposed load latency, which
is part of that issue term. If the mechanism works at all it can move both
addends, so the byte-limited ceiling is a floor on the mechanism's upside, not a
cap on it.

Had we kept the carried 17.67 GB, the advertised floor would have been 28.77 ms
and the headroom would have been understated by 4.63 ms. **The chunk-accurate
census makes the prize bigger, not smaller** — and the elasticity correction
makes it bigger again, by a further factor of 1.4675.

### A.11 Ledger label defect found (labels only)

The `dispatch_tiles` blocks in
`research/artifacts/route-histogram-prefill512-stats.json` and
`research/artifacts/README-route-histogram.md` have **swapped names**. The block
labelled `gate_up` carries `K=512, N=2048, column_tiles=32,
chunk_dram_bytes=18432` — those are the `down` numbers — and vice versa. Nothing
numerically downstream is affected, because every consumer sums the blocks. It
is a naming defect and should be fixed before someone reads a single block in
isolation.

---

## Part B — §8.2 K-loop software pipeline (register prefetch)

### B.1 The mechanism

The original K loop is `load → barrier → MMA → barrier` against a
**single-buffered** `Ws`. The device latency inside `load_unsafe` is therefore
fully exposed on all 32 iterations of the ranked shape: nothing else is in
flight while the loads resolve.

The fix keeps **one** `Ws` and splits the staging call in two:

* `prefetch()` — device → registers (raw packed nibbles + scale bytes, before
  any decode)
* `commit()` — registers → `Ws` (decode and threadgroup store, **no device
  latency**)

and then pipelines:

```
loader_w.prefetch();                            // device -> registers, k = 0
for (k = 0; k < K_it; ++k) {
    Atile loads                                  // unchanged, stays hoisted
    threadgroup_barrier();                       // WAR on Ws
    loader_w.commit();                           // registers -> Ws
    threadgroup_barrier();                       // RAW on Ws
    if (k + 1 < K_it) { loader_w.next(); loader_w.prefetch(); }
    MMA chain for k using Ws + Atile             // overlaps the k+1 device reads
}
```

The k+1 device reads are issued right after the RAW barrier and stay in flight
across the entire MMA chain for k.

Depth-1 register cost is small: `sb[16]` is four 32-bit registers, plus two scale
bytes ≈ one more, so **≈5 registers per thread**. For scale: `Dtile` is 32
registers, `Atile[2]` is 8, `Btile` is 32.

### B.2 Bit-exactness — the ordering constraints, and why they hold

**Constraint 1: `next()` must come after `commit()`.** The non-widened fallback
inside `commit()` calls `stage()`, which reads device memory at the *current* k
pointer. Advancing the pointer first would make that fallback read the wrong
tile. In the emitted code `commit()` is fully inlined ahead of the RAW barrier,
and `next()` is the first thing after it.

**Constraint 2: `next()` must come before `prefetch()`.** Prefetch is fetching
tile k+1, so the pointer must already be advanced. Verified directly in the IR
(§B.5): both `addrspace(1)` pointer stores precede every prefetch load.

**Constraint 3: alignment must be invariant across k.**
`src_byte_off() = bi*src_ld*bytes_per_pack/pack_factor + bj*bytes_per_pack`
depends only on `bi`, `bj` and compile-time constants — it never reads the
advancing pointer. So `load_ok` computed inside `prefetch` at iteration k is
identical to `load_ok` computed inside `commit` at iteration k. The real address
is `base + k*tile_stride + src_byte_off()` with `tile_stride = 32`, and
`32 % 16 == 0`, so 16-byte alignment holds at every k. This is a **pre-existing**
property: base's `load_unsafe_wide` made the identical check on every iteration.
No new risk is introduced.

**Constraint 4: the skipped final `next()` must be inert.** At PF=1, `next()`
runs `K_it − 1` times instead of `K_it`. `thread loader_w_t loader_w(...)` is
constructed at `fp_quantized_nax.h:1817`, **inside the M-chunk loop**, after
`const device T* xn = …`, and nothing reads `loader_w` after the k loop ends. The
loader is rebuilt for the next chunk. The difference is provably inert, and
strictly safer than base, which advanced `src` one tile stride past the last
valid tile.

**Also proved, and load-bearing:** on the ranked shape
`dst_byte_off() = 144*(thread_idx/2) + 64*(thread_idx%2)` is always a multiple
of 16, and `kWidenShapeOk` is true, so `store_ok` is true for **every** thread.
The scalar fallback branch inside `commit()` is therefore provably dead on the
ranked path. It is retained for the non-ranked instantiations that still reach
this loader.

### B.3 What the change does *not* touch

Explicitly out of scope, per the assignment: double-buffering `Ws`; M-chunk-loop
pipelining; §8.3 "stop staging the A operand" (VOID); §8.5 non-targets (wider
loads/relayout, split-K/atomics, per-expert `BM` variation — there is a hard
`bm==64 && wm==4` gate at `quantized.cpp:1734` — and anything outside the
attention quantization envelope); §8.4 tile-quantization padding.

PR #170's inert probe machinery is deliberately **not** pruned in this PR. Doing
so would change register allocation and confound the measurement.

### B.4 Offline evidence package

This host is an M4 Pro: Apple GPU generation 16. `is_nax_available()` requires
generation ≥ 17 and macOS ≥ 26.2, so **the kernel is never dispatched here**.
Every claim below is a static/offline claim; the timing claim is receipt-only.

**Compile and link.** `research/nax_msl_compile_check.sh` at `PF=0` and `PF=1`,
both ranked shapes: `COMPILE OK (std=metal4.0)`, `METALLIB OK`, `IR OK`, exit 0.
The script gained a `PF=<n>` knob that is byte-identical in behaviour when
`PF == 0`.

**Threadgroup memory is unchanged.**
`FILTER=expert swift research/tanjiro_metallib_stats.swift /tmp/naxpf0/unit.metallib /tmp/naxpf1/unit.metallib`
reports, for all four rows (`2048x1024` and `512x2048`, base and `_pf1`):

```
tgMem_B = 9232   maxThreads = 1024   width = 32   regs_bound <=32*
```

`kWsElems = BN*BK_padded = 64*72 = 4608` → `Ws_storage[576]` × 16 B = 9216 B,
plus 8 B of `bounds` = 9232 B. **PF=1 costs no threadgroup memory.**

**The kill-switch path is census-identical to base.** Base vs head at `PF=0`,
`FILTER=expert`:

```
functions defined: A=28 B=28   functions with a changed census: 0
axes that moved: (none)
TOTAL  mma 2  barrier 12  dev_load 12  dev_store 14  tg_load 6  tg_store 9
       const_load 2  other_load 24  other_store 48  int_alu 169  float_alu 5
       instrs 1041
```

Zero moved axes across all 12 axes. Unfiltered, exactly **one** function differs:
the outlined `load_unsafe_wide<true,true>`, where `store_ok`/`load_ok` are now
evaluated in both the inlined `prefetch` and the inlined `commit` and the front
end only partially CSE'd them (`int_alu 29→37`, `instrs 201→234`). Those
predicates are provably k-loop-invariant (Constraint 3 above), so backend LICM
hoists them; and PR #170's M2 arm showed that doubling MMA **and** ALU costs only
4.7 % of `W`, so a handful of loop-invariant integer ops is immaterial. This
affects only the `PF=0` kill-switch path — at `PF=1` `load_unsafe_wide` is
**entirely absent from the IR** because `prefetch`/`commit` are fully inlined.

**PF=1 adds no synchronization and no arithmetic work.** Unfiltered totals,
`PF=0` → `PF=1`:

```
mma        2 -> 2        barrier   12 -> 12      dev_store 60 -> 60
dev_load  76 -> 80       tg_load   26 -> 27      tg_store  15 -> 16
int_alu  614 -> 655      float_alu 19 -> 26      instrs  3520 -> 3784
functions defined A=28 B=27
```

`dev_load +4` is the **static** duplication of the prefetch code (a prologue copy
plus the in-loop copy), not dynamic duplication — the loop still issues one set
of device reads per iteration. The `expert`-filtered growth in
`tg_store`/`float_alu`/`instrs` is an **inlining accounting artifact**:
`load_unsafe_wide` is no longer emitted at PF=1 (28 → 27 functions), so its
decode-and-store body moved into the kernel body.

**Full local build and correctness pass.** `./benchmark.sh --local-iterate` on
the head commit completes with `"passed": true` (exit 0, 202 s), which exercises
the `quantized.cpp` host-side lever, the JIT path for every non-NAX kernel, and
the local greedy-token gates. Its timing numbers are **not** evidence for or
against the mechanism — this M4 Pro reports Apple GPU generation 16, so
`is_nax_available()` is false and the modified kernel is never dispatched. The
reported `prefill_speedup=0.326` is the ordinary non-NAX fallback cost on this
host and appears identically on the unchanged base.

### B.5 The decisive proof — basic-block trace on the ranked geometry

Read directly off the IR for `fp_gather_qmm_rhs_expert_nax_check_2048x1024_bk64_pf1`:

```
283: BARRIER                                     <- WAR on Ws
297: CALL stage()          -> 401                <- commit's scalar fallback (dead on ranked shape)
298..388: TG_LOAD / TG_STORE loop                <- commit's widened decode + stores
401: preds = %398, %297
     call air.wg.barrier(2,1)                    <- RAW on Ws
     %403 = icmp ult i32 %206, 31
     br i1 %403, label %404, label %457           <- if (k+1 < K_it), K_it folded to 32
404: store i8 addrspace(1)* %408 -> %123          <- next(): src    += tile_stride
     store i8 addrspace(1)* %410 -> %130          <- next(): scales += 4  (= n_groups)
     br i1 %413, label %415, label %422
435: llvm.memcpy 16 B from addrspace(1) %408      <- prefetch(): WIDE 16 B device load
445: load i8, i8 addrspace(1)* %448 (loop)        <- prefetch(): scalar fallback
453: load i8 %410 ; load i8 %455                  <- prefetch(): 2 scale bytes
     br label %457
457: preds = %453, %422, %401
     br i1 %190, label %458, label %545           <- if (sg_active)
458: CALL load_contig_tg                          <- Btile from Ws
478..542: MMA chain (matmul2d x14)
```

Five things this establishes on the ranked geometry:

1. The guard is the compile-time-folded `k + 1 < 32`.
2. **`next()` executes before `prefetch()`** — both `addrspace(1)` pointer bumps
   precede every prefetch load — satisfying Constraints 1 and 2.
3. **The prefetch device loads are NOT dominated by `sg_active`.** The
   `sg_active` branch is at BB 457, a *join successor* of the prefetch region
   (`preds = %453, %422, %401`). All 128 threads issue the prefetch, exactly like
   the base staging call. Had the prefetch sunk into the guard, empty simdgroups
   would skip it and the arm would be void.
4. **The MMA chain (BB 478+) is downstream of the prefetch loads**, so the k+1
   device reads are in flight across it. That is the mechanism under test.
5. **Exactly one barrier (BB 401) separates commit from prefetch.** No barrier
   was added.

Trace produced with `/tmp/pf1trace.py <unit.ll> <kernel-name-substring>`, which
prints a per-basic-block ordered event trace with branch successors.

### B.6 Why safety-rig check 2 cannot pass, and what replaces it

`research/nax_safety_rig.sh` with `BASE_REV=747d130b`:

```
1. compile + link                    PASS BK=64, PASS BK=128
2. BK=64 inertness vs 747d130b       FAIL  (AIR differs)
3. non-empty MMA body                PASS BK=64: 3 calls, PASS BK=128: 3 calls
4. widened device load reachable     PASS BK=64 kSrcBytes=16, PASS BK=128 kSrcBytes=32
5. wide-load guard fires             PASS narrowed builds BK=64, PASS rejects BK=128
6. generated twin matches header     PASS (6 structural hunks)
```

**Check 2 is structurally unpassable for this PR — proven, not assumed.** Adding
the `int kloop_prefetch` template parameter lengthens every mangled kernel name,
and those names are embedded in the threadgroup-global symbols (`Ws_storage`,
`bounds.0`, `bounds.1`) and in every reference to them:

```
base: @_ZZ28fp_gather_qmm_rhs_expert_naxIDF16bLi16E...Lb1ELb1ELi0E    Ev...E10Ws_storage
head: @_ZZ28fp_gather_qmm_rhs_expert_naxIDF16bLi16E...Lb1ELb1ELi0ELi0EEv...E10Ws_storage
```

— one extra `Li0E`, the new `kloop_prefetch = 0` argument, for both shapes. A
byte-identical AIR comparison can therefore never succeed regardless of how inert
the code is.

Two strictly stronger substitute proofs were obtained instead:

1. **Identical defined-symbol sets**, 28 vs 28 — nothing appeared or vanished.
2. **`FILTER=expert` kernel-body IR census with zero moved axes** across all 12
   axes (§B.4) — the kill-switch bodies are semantically identical, not merely
   similar.

I considered restoring a duplicated monolithic `load_unsafe_wide` to make check 2
pass. **Rejected.** It would cost ~1.5 KB in the header and ~1.5 KB in the twin
(≈3 KB), breaching the self-imposed 12,000 B growth cap, for a path that (a)
never runs on the ranked host since the default is PF=1, (b) *still* could not
make check 2 pass because the mangling change is independent of it, and (c)
differs only by provably loop-invariant integer ALU. Adding
`store_ok`/`load_ok` to `WidePrefetch`, or hoisting the predicates to kernel
scope, was rejected for the same reason plus the new "commit must be paired with
prefetch" invariant it would introduce this close to the receipt budget.

### B.7 Scope, budget, twin

```
assignment scope OK: 3 submitted path(s) against BASE_SHA=747d130b...
editable budget OK: current=2960858/3000000 bytes headroom=39142
                    growth=11172/262144 files=142 (base=142)
TWIN CHECK: generated copy matches the header
```

Submitted paths:

* `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized_nax.h`
* `Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized_nax.cpp` (twin;
  `benchmark.json:94` — JIT-compiled on the M5, so it must stay in sync)
* `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp`

Growth of 11,172 B is under the self-imposed 12,000 B cap with ~830 B to spare;
39,142 B of true repository headroom remains. Files under `research/` are not in
`editablePaths` and do not count against the budget.

### B.8 Host lever

`DARKBLOOM_NAX_KLOOP_PREFETCH`, read by
`darkbloom_nax_kloop_prefetch()` at `quantized.cpp:1665-1678`, default `"1"`
(`kNaxKloopPrefetchDefault`, `:1663`). `"0"` is the kill switch. `"2"` returns 2
and fails loudly at the header `static_assert` during JIT — deliberately, so a
"depth 2" claim can never be silently clamped to depth 1.

The official runner strips the environment (`benchmark.sh`'s timed path runs
under `sudo env_reset` + `env -i`), so **for a ranked measurement the compiled-in
default is the arm.**

---

## 3. Residual risks

Stated plainly, because none of them is resolvable on this host.

1. **`metal -S -emit-llvm` is front-end output.** The IR ordering proof in §B.5
   establishes program order and dominance, not the backend's final instruction
   schedule. The backend could in principle sink the prefetch loads.
2. **`threadgroup_barrier(mem_flags::mem_threadgroup)` does not order
   `addrspace(1)` accesses.** The backend is formally free to move device loads
   across it. This is what makes the optimization *legal*, and it is also why the
   realized overlap cannot be proved offline.
3. **Register-driven occupancy is not establishable here.** `maxThreads`
   saturates the 1024 API ceiling in the metallib reflection, and the front-end
   IR is pre-SROA (even `NAXTile` accumulators appear as `alloca`), so allocas
   carry no residency information. A ~5-register increase could in principle cost
   residency on the M5. This is the single largest way the arm could come back
   negative despite a correct mechanism.

---

## 4. Corpus corrections requested

| file | issue |
|---|---|
| `research/artifacts/route-histogram-prefill512-stats.json` | `dispatch_tiles` `gate_up`/`down` labels swapped |
| `research/artifacts/README-route-histogram.md` | same label swap; `:24-25`, `:31` state 38 layers without the layer-39 GEMV reason |
| `research/h5-per-expert-fused-ffn-closure.md:27-29` | reason for 38 given as "layer 0 is dense"; the second missing layer is layer 39's `callLastPrefillRow` GEMV diversion |
| `research/tanjiro-pr34-r2-result.md:701-705` | `× 40/39 = 44.371 ms` has the wrong sign; correct rescale is `× 38/39 = 42.1526 ms` |
| `research/lpt_expert_queue_sim.py:48` | bare `38`, no provenance |
| `research/route_histogram.py:41` | bare `38`, no provenance |
| campaign-wide | prefill elasticity `0.2554 %/ms` is **retired**; the correct value is `0.374750 %/ms` because the decode window contains the 512-token seed prefill (§A.10). Anything priced off the old number understates the prefill axis by a factor of 1.4675 |

---

## 5. Receipts

Budget 3, with slot discipline. The assignment listed these as a budget
allocation; I reordered them temporally:

1. **R1 = PF=1 (depth 1)** — the candidate
2. **R2 = fresh control at `747d130b`**
3. optional third — depth 2 or a variant, **only if R1 vs R2 shows signal**

**Why candidate first.** 5 of the last 22 receipts on this benchmark returned
`failed` (no score, no metrics). A `failed` candidate is the cheapest
high-information outcome available, and discovering a JIT or build failure
*after* spending the control would waste two of three receipts rather than one.
Submitting the candidate first also banks a promotion sooner if the win is real.
The pairing is unaffected: both rows are read off raw candidate
`officialMetrics` in the same way regardless of order, and the control is a
byte-exact checkout of the three submitted paths at `747d130b`, not a
same-session paired draw.

Every ledger row is read off **raw candidate `officialMetrics`**, never off
speedup ratios: the baseline prefill draw swings ±1.93 % while candidate
run-to-run sd is only 0.260 %, so ratios are the noisier statistic.

```
S = 512000 * prefill_seconds_per_token          (ms)
T = 1000 * decode_seconds_per_token - S/128     (ms)
norm_decode_su  = 0.013890  / decode_seconds_per_token
norm_prefill_su = 0.0003845 / prefill_seconds_per_token
ns = norm_decode_su**0.75 * norm_prefill_su**0.25
```

The `- S/128` term in `T` is not a convention, it is the seed-prefill identity of
§A.10: the decode window contains a 512-token prefill, so `T` is only recoverable
by subtracting it. This is also why one ms off `S` is worth **0.374750 %** of
score and not 0.2554 % — the frontier being defended is `ns = 2.5982`, so a
500 GB/s outcome is a **+2.5 % single-mechanism move**.

**Kill rule: if depth 1 shows `ΔS ≥ −1.35 ms` (3σ on the paired difference),
stop after two receipts and write a clean negative.**

**Pricing caution carried from PR #204 (fern).** That PR removed 39 decode
dispatches per step against a pre-registered −110 µs prediction and measured
**−0.9 ± 12.1 µs, p = 0.94** — a clean null. The lesson is that a *census*
µs/step figure is a throughput-slot upper bound, not a marginal cost: a dispatch
that sits inside a larger sibling's concurrency interval is free to delete and
free to keep. Nothing in this PR is priced as "N dispatches × µs/dispatch", and
the prefill gather-GEMM is the sole occupant of its interval with real bytes on
the wire, so §A.10's headroom is not exposed to that failure mode. It is
recorded here so the next reader does not import a dispatch-count price without
re-reading #204 §7 first.

Results are appended in §6 as they land.

---

## 6. Results

### 6.1 Receipt ledger

| # | arm | submitted commit | submission id | dispatched | terminal | wall | ΔS vs control |
|---|---|---|---|---|---|---|---|
| R1 | arm 1, `kloop_prefetch=1` (candidate) | `0b5372f5377f028407bd9bfc785fe666b8710eb6` | `26b8e82a-9158-4fe1-83d5-fcf71a301e7e` | 06:26:47Z | 06:47:18Z | 20.5 min | **+0.684 ms (+1.52σ)** |
| R2 | control, the three submitted paths checked out at `747d130b` | `5164d313fae0cd5d601b1cda4e1c4620207c1dfc` | `0bc3eb4c-95b0-4c47-bdb1-28b266a76acd` | 06:49:45Z | 07:10:01Z | 20.3 min | 0 by definition |
| R3 | — | — | **deliberately not spent, see §6.11** | — | — | — | — |

Both receipts returned `status = rejected` with
`rejectionReason = "score did not improve current best"`, i.e. ranking-only. Every
correctness and floor gate passed in both (§6.2, §6.5).

Ordering rationale is in §5: candidate first, control second. The candidate is the
only dispatch that can fail a hidden correctness gate, so spending receipt 1 on it
buys the gate verdict earliest and makes receipt 2 worth dispatching at all.

R2 was dispatched at 06:49:45Z, about eleven minutes **before** the advisor's second
feedback comment arrived at 07:00:47Z. That comment records "one spent" because it
predates R2. No instruction was overridden; the two events simply crossed.

R2's control archive was produced by `git checkout 747d130b -- <the three submitted
paths>`, submitting, and then `git checkout HEAD -- <same paths>`. This works because
`createSubmissionArchive(repoPath, manifest)` (`mlxfast.js:24530`) tars
`manifest.editablePaths` from the **working tree on disk**, not from git HEAD. Both
directions were verified: an empty `git diff --stat` against the base and
`grep -c kNaxKloopPrefetchDefault quantized.cpp` = 0 before submitting, and a restored
count of 2 with a clean `git status --porcelain` afterwards.

---

### 6.2 R1 — arm 1 passes every correctness gate on the ranked M5

This is the single most valuable thing the receipt bought, and no amount of offline
work could have established it. The depth-1 software pipeline is **bit-exact on real
hardware**, on the GPU generation that actually selects the `_nax` kernel family.

| gate | value |
|---|---|
| `passed_correctness` | **True** |
| `max_abs_diff` | **0** |
| `error` | `''` (empty) |
| `first_failing_step` / `_case` / `_layer` | `None` |
| `partial_result` | **False** |
| `gpqa_ttft_passed` | **True** |
| `semantic_gpqa_passed` | **True (9/9)** |
| `passed_decode_speedup_floor` | **True** |
| `passed_prefill_speedup_floor` | **True** |
| `rejectionReason` | `"score did not improve current best"` |

The rejection is **ranking-only**. Per the campaign guidance, correctness, error, and
both floor verdicts are read independently of ranking status, and all five are clean.

This retires the three offline residual risks of §3 as *safety* concerns. §3 worried
that `metal -S -emit-llvm` is front-end output so IR scheduling need not match the
backend schedule, and that `threadgroup_barrier(mem_flags::mem_threadgroup)` does not
order `addrspace(1)` accesses so the backend is free to move device loads across it.
Both remain true as *performance* caveats — and §6.8 shows the second one is in fact a
live hypothesis for the null — but neither produced a numerical difference. The
reordering is value-preserving on the ranked hardware.

Receipt JSON archived at `research/artifacts/tanjiro-pr170-receipt-pf1.json`.

---

### 6.3 R1 — the S axis is a null, not a regression

Raw candidate `officialMetrics`, converted with the §5 constants
(`S = 512000 × prefill_seconds_per_token`, `T = 1000 × decode_seconds_per_token − S/128`):

| quantity | frontier `97a5090` (commit `3e165fa`) | R1 arm 1 | Δ |
|---|---:|---:|---:|
| `prefill_seconds_per_token` | 0.000191201… | 0.00019181477734375 | — |
| `decode_seconds_per_token` | — | 0.0049374427109375 | — |
| **`S` (prefill, ms)** | **97.895** | **98.2092** | **+0.314** |
| **`T` (decode step, ms)** | **4.143569** | **4.17018** | **+0.0266** |
| `nd` | 2.820661 | 2.813197 | — |
| `np` | 2.001471 | 2.004538 | — |
| **`ns` (normalized score)** | **2.5982163** | **2.584662** | **−0.522 %** |
| published `officialScore` | 2.58882784082067 | 2.56253848898976 | −1.016 % |

**ΔS = +0.314 ms = +0.70 σ_diff** (σ(S) = 0.318 ms, σ_diff = √2 × 0.318 = 0.4497 ms,
3σ = 1.35 ms). That is **inside the band**, so by the pre-registered kill rule of §5
this is a null. As a fraction of the marginal window it is +0.73 % of W = 43.2619 ms.

The advisor pre-computed both branches of this test in feedback comment `5213645316`:
if the whole −1.016 % `officialScore` drop had been prefill-side it would have implied
ΔS ≈ +2.71 ms = +8.5σ, a real regression; if `S` landed inside ±1.35 ms of 97.895 the
arm is a null and the score move was baseline-side. **The measurement selects the
second branch.**

Pre-registration for scale: the predicted win was −3.43 ms at 450 GB/s, −6.72 ms at
500 GB/s, and −12.23 ms at 614 GB/s, i.e. **7.5σ to 27σ**. Even 25 % coverage of the
predicted latency would have been ≥2σ. Measuring +0.70σ does not mean "it partly
worked"; it falsifies the exposed-latency model outright. This distinction is the whole
value of §6.8.

This subsection compares R1 against the *frontier* receipt, which was measured in a
different session. §6.5 replaces it with the paired same-session control and is the
entitled read; the two sessions differ by 0.370 ms on the candidate axis, so the paired
ΔS is +0.684 ms rather than +0.314 ms. Both are nulls; only the paired figure supports
a confidence bound.

---

### 6.4 Why `officialScore` fell 1.016 % while `S` moved 0.70σ

Because 78 % of the drop is on an axis this mechanism **provably cannot reach**.

Decomposing Δ`ns` = −0.522 % by *physical* quantity, using
`decode_seconds_per_token = S/128 + T` from §A.10:

| source | arithmetic | contribution to Δ`ns` |
|---|---|---:|
| `S` (prefill, incl. its amortized share of the decode seed) | 0.374750 %/ms × 0.314 ms | **−0.118 pp** |
| `T` (pure decode step time) | 0.75 × 0.0266 / 4.908374 | **−0.407 pp** |
| total | | **−0.525 pp** vs −0.522 pp observed |

Decomposed instead by *score axis*: `nd` contributes −0.442 pp and `np` −0.080 pp;
same total, different cut.

`T` is the pure per-step decode cost, and **the NAX routed expert kernel is
prefill-only**. `expert_aligned` (`quantized.cpp:1760-1763`) requires `M >= 64`;
teacher-forced decode issues one token per step, so the M=1 GEMV path is taken and
`fp_gather_qmm_rhs_expert_nax` is never dispatched during the 128 decode steps.
Arm 1 changes exactly one template parameter of that kernel. It cannot move `T` by
any causal route, so ΔT = +0.0266 ms is session noise by construction.

**Methodological consequence, worth carrying campaign-wide: Δ`ns` and Δ`officialScore`
are the wrong statistic for judging a prefill-only mechanism.** Three quarters of the
score weight sits on a decode axis the mechanism cannot touch, so its noise dominates
the read. Only the `S` ledger is diagnostic. Had this arm been judged on
`officialScore` alone it would have been written up as a −1 % regression; it is a
+0.7σ null.

This subsection reasons from the frontier session. §6.5 supersedes it with a direct
measurement: the paired control, which is *identical code* to the frontier, published
`officialScore` −1.028 % below it — a slightly **larger** drop than the candidate's
−1.016 %. The score move is therefore not merely "mostly unreachable by this
mechanism", it is entirely baseline-side, and the candidate finished +0.0123 % *above*
its own identical-code control.

---

### 6.5 R2 — paired control, and the confirmation that the score move was baseline-side

Receipt `0bc3eb4c-95b0-4c47-bdb1-28b266a76acd`, official commit
`5164d313fae0cd5d601b1cda4e1c4620207c1dfc`, `timestamp = 2026-08-07T06:58:43Z`,
23 min after R1. The archive is the three submitted paths checked out at the
assignment base `747d130b` — byte-exact base code, no `kloop_prefetch` template
parameter at all — via the `createSubmissionArchive` working-tree mechanism recorded
in §6.1. Receipt at `research/artifacts/tanjiro-pr170-receipt-ctrl.json`.

**Gates.** The control passes everything the candidate passes, as it must:
`passed_correctness = True`, `max_abs_diff = 0`, `error = ''`,
`gpqa_ttft_passed = True`, `semantic_gpqa_passed = True (9/9)`, both speedup floors
`True`, `partial_result = False`, `first_failing_step = None`. `weights_hash`,
`harness_hash` and `golden_hash` are identical to R1's, so the two receipts are
comparable measurements of the same benchmark.

| quantity | R2 control (`5164d31`) | R1 arm 1 (`0b5372f`) | Δ (cand − ctrl) |
|---|---:|---:|---:|
| `prefill_seconds_per_token` | 0.000190478435546875 | 0.00019181477734375 | — |
| `decode_seconds_per_token` | 0.0049417265625 | 0.0049374427109375 | — |
| **`S` (prefill, ms)** | **97.525** | **98.2092** | **+0.684** |
| **`T` (decode step, ms)** | **4.1798** | **4.1702** | **−0.0096** |
| `nd` | 2.810759 | 2.813197 | +0.087 % |
| `np` | 2.018601 | 2.004538 | −0.697 % |
| **`ns`** | **2.587500** | **2.584662** | **−0.110 %** |
| published `officialScore` | 2.56222295324231 | 2.56253848898976 | **+0.0123 %** |

**Paired ΔS = +0.684 ms = +1.52 σ_diff.** Inside the ±1.35 ms band, so the
pre-registered kill rule of §5 fires: null, stop at two receipts. The pre-registered
win was −3.43 ms (−7.6σ), −6.72 ms (−14.9σ) or −12.23 ms (−27.2σ). The paired read is
on the *wrong side of zero* and two orders of magnitude short.

**Exclusion bound.** The paired measurement does not merely fail to confirm the
hypothesis, it bounds it. At 3σ the true effect is at worst −0.665 ms; at 2σ, at worst
−0.215 ms. So **any real improvement larger than 0.665 ms is excluded at 3σ** — that is
19.4 % of the weakest arm of the pre-registration. In §A.9's units, −0.665 ms is the
gain from lifting the effective streaming rate from 407.6 GB/s to 415.2 GB/s; the
prediction required 450–614 GB/s. The whole predicted region is outside the confidence
interval.

**The control independently confirms the §6.4 diagnosis.** This is the part that could
not have been obtained from a same-arm re-draw. Code that is byte-identical to the
promoted frontier on the submitted surface published `officialScore = 2.56222`, which
is **−1.028 % below the frontier's own published 2.58883** — a slightly *larger* drop
than the candidate's −1.016 %. The candidate scored **+0.0123 % above an
identical-code control.** The −1 % that would have been the headline of a naive
write-up is fully reproduced by code containing none of the change. Its source is
visible in the raw metrics: the baseline draw in R1's session was 1.06 % slower on
prefill than in R2's session (`baseline` `S` = 193.518 ms vs 191.494 ms) and 0.19 %
faster on decode.

**Two identical-code draws of the candidate axis.** The frontier measured
`S = 97.895 ms` and this control measured `S = 97.525 ms` from the same source. They
differ by 0.370 ms = 0.82 σ_diff, consistent with the σ(S) = 0.318 ms used throughout.
That drift is exactly why the paired control was worth a receipt: judged against the
frontier, arm 1 read +0.314 ms; judged against its own paired control it reads
+0.684 ms. The 0.37 ms difference between those two verdicts is cross-session drift
that an unpaired comparison would have silently attributed to the mechanism. Both
readings are nulls, so the conclusion is unchanged — but only the paired one is
entitled to state a bound.

**Where the −0.110 % `ns` move comes from.** It is not a prefill regression net of
noise; it is the prefill axis partly cancelled by decode noise:

- `np` −0.697 % × 0.25 = **−0.174 pp** — this is the ΔS = +0.684 ms.
- `nd` +0.087 % × 0.75 = **+0.065 pp** — and this is *not* the mechanism. Decode
  seconds/token is `S/128 + T`; ΔS contributes +0.00534 ms and ΔT contributes
  −0.0096 ms, netting −0.0043 ms on a 4.9417 ms step. `T` is unreachable by this
  change (§6.4: decode is M=1 GEMV, `expert_aligned` requires `M >= 64`), so ΔT is
  session noise that happened to fall the candidate's way.
- Sum −0.109 pp, against −0.110 pp observed.

**Campaign-wide datum.** An identical-code control re-measured in a fresh session moved
`officialScore` by 1.028 %. Cross-session `officialScore` differences of order 1 % are
therefore not evidence of anything, in either direction. Only same-session paired
candidate-axis metrics are diagnostic, and for a prefill-only mechanism only `S` is.

**Ordering note.** R2 was dispatched at ~06:52Z, about eight minutes before advisor
feedback comment `5213645316` landed at 07:00:47Z; nothing in that comment was
overridden. The comment's §3.4 authorised at most one further receipt, a same-arm
confirmation, conditional on `S` landing inside the band and Step 0 being flat — both
conditions hold. The receipt in flight was a paired control rather than a same-arm
re-draw, and it is strictly the better spend of the two: a re-draw would have halved
the variance of a number already known to be a null, whereas the control removed a
0.37 ms systematic, produced the 3σ exclusion bound above, and settled the advisor's
§3.1 branch question with an actual measurement instead of an inference.

---

### 6.6 Step 0 — the advisor's zero-receipt discriminator

Advisor feedback comment `5213645316` §2 made this mandatory before any further
dispatch, and pre-registered its reading. Full artifact:
`research/artifacts/tanjiro-pr215-step0-pipeline-stats.txt`.

`fp_gather_qmm_rhs_expert_nax`, both ranked shapes, control vs arm 1:

| function | tgMem_B | maxThreads | width | regs_bound | TGs/core |
|---|---:|---:|---:|---|---:|
| `…_2048x1024_bk64` (control) | 9232 | 1024 | 32 | `<=32*` | 7 |
| `…_2048x1024_bk64_pf1` (arm 1) | **9232** | **1024** | **32** | `<=32*` | **7** |
| `…_512x2048_bk64` (control) | 9232 | 1024 | 32 | `<=32*` | 7 |
| `…_512x2048_bk64_pf1` (arm 1) | **9232** | **1024** | **32** | `<=32*` | **7** |

Implied threadgroups per shader core, for the ranked geometry `bm=64 bn=64 wm=4 wn=1`
= 128 threads = **4 simdgroups** per threadgroup:

- threadgroup-memory bound: `floor(P / 9232)` = **7** at the standard 64 KiB per-core
  pool. This bound is *invariant under P* because `tgMem_B` is bit-identical between
  the variants — that half is proven, not assumed.
- simdgroup-slot bound: **8** at ≤104 half-registers (32 simdgroups/core ÷ 4),
  falling to 6 at 128 and 5 at 160 half-registers.
- binding value **7 for both**, i.e. 28 resident simdgroups per core.

**Reading: the second branch.** A drop in `maxTotalThreadsPerThreadgroup` would have
meant occupancy/register pressure is the mechanism. It held at 1024 with `tgMem_B`
still 9232 B on both shapes, so register pressure is not the story and the explanation
is added instruction count in a loop PR #170 already showed is issue-limited.

Caveat kept explicit rather than buried: `maxThreads` saturates at the 1024 Metal API
ceiling, which is far below the 104/128/160 half-register cliffs, so this host cannot
*fully* close the register-step question. What is closed is that arm 1 costs zero extra
threadgroup memory and does not change launch geometry. §6.8 gives an independent
argument that a register step is not the explanation either.

---

### 6.7 The lever provably reached the scored path

A null is only informative if the knob was live. It was.

The arm is gated `kloop_prefetch = expert_aligned ? darkbloom_nax_kloop_prefetch() : 0`
at `quantized.cpp:1823`. That is the **identical gate** that carried PR #170's four
probes — `gather_probe = expert_aligned ? probe_requested : 0` at `:1818` — and those
probes moved `S` on this same ranked M5 by up to **+15.961 ms**. A gate that can move
`S` by 16 ms is not an unreached lever.

Two further confirmations from R1 itself: the kernel name carries the `_pf_1` suffix
only when the template argument is non-zero, and the arm changed the measured
`prefill_seconds_per_token` at all (+0.7σ is small but the correctness gates prove a
*different binary* ran and produced identical values). The official runner strips the
environment (`sudo env_reset` + `env -i`), so the compiled-in default
`kNaxKloopPrefetchDefault = "1"` **is** the arm for a ranked measurement — there is no
path by which the control code could have been measured.

This is therefore a real null about a real mechanism, not a null result about a dead
switch.

---

### 6.8 Mechanism — why a depth-1 pipeline cannot help this loop

Ranked hypotheses, after an independent frontier-agent critique that re-derived the
loader structure from source.

**H1 (~75 %) — the staging path is throughput-bound on memory-op issue, and per-warp
latency was already hidden by co-resident simdgroups.** Software pipelining conserves
instruction count; it only buys time when an issue pipe would otherwise sit *idle*
waiting on a dependency. §6.6 puts 7 threadgroups = 28 simdgroups on each core. A warp
stalled inside `commit()` does not idle the core; another simdgroup's MMA or staging
issues in that slot. Wall time is then ≈ total issued ops ÷ pipe rate, which is
**invariant under reordering**. Four independent facts fit this and only this:

1. PR #170's S3 probe added staging with **zero extra DRAM bytes** and cost
   **+7.853 ms**. That is linear in issued staging ops, not in bytes and not in
   latency. If those 7.853 ms were exposed latency, arm 1 — which removes the device
   load from the barrier-to-barrier span entirely, leaving only decode and stores —
   had to recover several ms. It recovered 0.0.
2. S2 minus S3 is +8.108 ms for +5.89 GB, a **marginal** rate of ~726 GB/s against a
   ~343 GB/s average (§A.9). DRAM has roughly 2× headroom, so the average rate is
   being set *upstream* of DRAM — at issue and pipe occupancy. (Plausibly a chunk of
   the 14.83 GB requested traffic is A-fragment re-reads absorbed by SLC.)
3. M2 doubled MMA and ALU work for only **+2.046 ms**: the arithmetic pipes have
   headroom. The scarce resource is memory-op issue, and on M3+ threadgroup memory is
   the same dynamic-caching SRAM as L1, so device loads and threadgroup stores contend
   for it.
4. The A-operand hoist already shipped in this kernel (header comment at :1863-1876,
   "overlapping the sorted-x device reads with the weight staging they previously
   serialized behind") had already harvested precisely the overlap arm 1 targets.
   Independent device reads were in flight across the staging span before this PR.

**H2 (~10 %) — the backend was already hoisting the device loads.** This was §3's
second residual risk: `threadgroup_barrier(mem_flags::mem_threadgroup)` does not order
`addrspace(1)` accesses, so a hoist is legal. Against it: to hide the W-load latency in
the *baseline*, the AGX backend would have to move a device load across the loop
back-edge, i.e. modulo-schedule a loop containing convergent barrier intrinsics. AIR
models `air.wg.barrier` conservatively (convergent, with memory side effects), and the
AGX backend does local post-RA scheduling rather than loop rotation. It is also
**strategically irrelevant**: if true, it implies the same conclusion as H1 — only
removing operations helps.

**H3 (~5–10 %) — register pressure or spill cancelled the win.** Step 0 (§6.6) shows no
threadgroup-memory or geometry change. M5 has dynamic caching, so a ~5-register delta
rarely produces a hard cliff, and a cliff would cost several percent rather than
+1.52σ. The sharper sub-case — the backend spilling `pf` across the MMA chain — would
*still* hide DRAM latency, since the refill comes from L1-backed stack, so a genuine
latency win would have survived in attenuated form. The §6.5 exclusion bound rules out
even a 20 % attenuated win at 3σ; none appeared at all.

**H4 — noise.** The paired +0.684 ms is +1.52σ, short of the 3σ bar the campaign uses
for a signal. The sign carries no information and is not interpreted anywhere in this
report. Note that H4 does not rescue the hypothesis: a null is exactly what H1
predicts, and the exclusion bound of §6.5 is what does the falsifying work regardless
of which side of zero the point estimate lands on.

The front-end IR census is the direct fingerprint of H1: `instrs` **3520 → 3784**,
`dev_load` **76 → 80**, `int_alu` **614 → 655**, with `barrier` **12 → 12**, `mma`
**2 → 2** and `dev_store` **60 → 60** unchanged. Arm 1 added ~7.5 % more instructions
to a loop whose residual cost #170 measured as a **pure-issue term of 6.887 ms**
(15.9 % of W) and removed none. Under H1 that predicts a small positive ΔS, which is
what was measured.

---

### 6.9 Family closure

> **In-kernel register-staged prefetch for the `_nax` routed gather-GEMM is dead on
> ranked hardware, and the measured reason is that its K-loop is limited by memory-op
> *issue*, not by exposed memory *latency*. Reordering loads conserves instruction
> count, so it cannot buy time in this loop by construction; arm 1 in fact added ~7.5 %
> more instructions and moved `S` by +0.684 ms (+1.52σ) against its own paired control,
> a null that excludes any real gain above 0.665 ms at 3σ.**

This permanently retires the last surviving descendant of the `_nax` in-kernel
staging / prefetch / double-buffering family, which was reopened specifically on the
strength of PR #170 §8.2. The closure is mechanistic rather than merely empirical: it
names the resource (memory-op issue bandwidth), gives the falsified alternative
(exposed latency), and states the discriminating measurement (a −7.6σ to −27.2σ
prediction that measured +1.52σ, with occupancy and geometry held provably constant by
§6.6, and with the whole predicted 450–614 GB/s region outside the 3σ interval per
§6.5).

What it does **not** retire: the §A.9 headroom itself. The streaming floor at 614 GB/s
is 24.15 ms against W = 43.2619 ms, leaving **19.11 ms = 7.16 % of score** on the
table. That headroom is real; this family was simply the wrong instrument for
collecting it. §6.10 says what the right instrument looks like.

---

### 6.10 Handoff — the next mechanism must *remove* load issues, not reorder them

This is the operative distinction the closure produces, and it should be the first
filter applied to any successor proposal in this family's neighbourhood.

**Ranked successor candidates.** These are proposals, grounded in read-only source
inspection; none is measured, and each line number should be re-verified before
implementation.

**1. Amortize / widen the scale loads — REDUCES issue count. Highest expected value.**
Today each thread issues **3 device loads per k-iteration to move 18 bytes**: one
128-bit load for 16 B of packed weights, plus **two single-byte scale loads**. So two
thirds of the load issues move one ninth of the bytes. But a row's scale bytes are
contiguous and `next()` advances the scale pointer by `n_groups` = BK/16 = **4 bytes
per iteration**, while the thread consumes only `n_steps_per_read` = 2 of them. Hence
**one aligned 16 B scale load covers four k-iterations** (offsets {0,1, 4,5, 8,9,
12,13} all fall in one 16 B window). Loads per thread per iteration drop 3 → **1.25**,
about **−58 % of staging load issues**, for roughly +4 registers, **zero byte change**
and bit-identical decode inputs. Scaling the 6.887 ms pure-issue term by the removed
share of staging memory ops (~1.75 of ~7) predicts **−1.2 to −1.8 ms on `S`, i.e.
2.5–4σ** — decisive with a single receipt in either direction. A minimal fallback (one
`uint16_t` load for the pair) still removes 1 of 3 loads. `MLXFastTransform` could
later repack the scales to eliminate the 50 % over-fetch, but no offline repack is
needed to run the experiment.

**2. A-fragment N-tile reuse — reduces *requested bytes*, the other term.** Each
simdgroup re-reads its sorted-x fragments once per N-tile; at N=1024 with BN=64 that is
~16 re-reads of the A slab. Processing two N-tiles per A load halves it. Potentially
the largest single lever, but accumulators double, `Ws` or the B-fragments double, it
perturbs a tuned tile shape, and if SLC already absorbs the re-reads the win collapses
toward another null. High variance; sequence it *after* candidate 1 has confirmed the
cost model.

**3. `BK=128` — reduces barrier and loop-overhead ops, not loads.** Already a supported
instantiation. Halves barrier rendezvous, worth ~0.4–0.8 ms by #170's own barrier
coefficient (B2 = +0.841 ms for two extra barriers), but 17.4 KB of `Ws` drops the
tgmem-limited residency from 7 to 3 threadgroups per core. Low priority given §6.6.

**4. Dead by this closure — do not re-propose without new evidence.** Depth-2
pipelining, double-buffered `Ws`, and any further reordering of the same operations all
remove **zero** issues. Double-buffering does delete one barrier per iteration
(~−0.4 ms by #170's coefficient) but costs 18.4 KB of threadgroup memory, which halves
residency for a sub-noise prize.

**The filter, stated once:** before proposing anything else in this neighbourhood,
count the device-load and threadgroup-store *issues* per thread per k-iteration, before
and after. If the count does not go down, §6.8 predicts a null and the proposal should
not consume a receipt.

---

### 6.11 Receipt 3 was deliberately not spent

Three independent lines of authority converge on stopping at two receipts.

1. **The pre-registered kill rule (§5).** The paired ΔS = +0.684 ms ≥ −1.35 ms,
   therefore "stop after two receipts and write a clean negative".
2. **Advisor feedback comment `5213645316` §3.** Arms 2 (depth 2) and 3 (extend
   prefetch to `Atile`) are explicitly demoted: "either outcome closes the same door",
   and both explanations predict depth 2 is *worse*, being a strictly larger
   register-pressure and instruction-count perturbation of the same loop.
3. **The frontier critique.** Independent verdict on depth 2: throwing the receipt
   away. Depth 2 helps only if exposed latency exceeded one full MMA chain, a world in
   which depth 1 would necessarily have captured a large partial win of several σ.
   Depth 1 captured nothing, so there is no residual latency for depth 2 to cover and
   its point estimate is the same +0.684 ms.

The one narrow case the advisor left open was a **re-draw of the same arm**, justified
only where `S` lands inside 1.35 ms *and* Step 0 shows no occupancy or geometry
change — i.e. where the evidence says "draw noise" and a second draw would resolve it.
Both halves are in fact satisfied here. It was still declined, for three reasons:

- R2 (§6.5) already spent the second receipt on the *better* version of that question,
  and it worked. A control measured in the same queue conditions removed the
  cross-session drift between the `97a5090` frontier session and now — drift that
  turned out to be real and large, 0.370 ms of the 0.684 ms paired difference — and it
  is what makes the §6.5 exclusion bound entitled at all. A same-arm re-draw would have
  bought no such thing.
- The decision does not turn on it. §6.8's argument is falsification of a 7.6–27σ
  prediction by a +1.52σ measurement. A second candidate draw averaged against the one
  control shrinks σ_diff from 0.4497 ms to σ·√1.5 = 0.3895 ms, tightening the 3σ
  exclusion bound only from 0.665 ms to 0.485 ms. Both bounds sit two orders of
  magnitude below the weakest predicted arm, so the extra receipt closes no additional
  door.
- The operational bulletin in the same advisor comment prices a receipt at ~double its
  quoted wall time on a queue **shared with the `birch` campaign**, and asks for one
  decisive dispatch over a sweep. The next genuinely decisive dispatch is candidate 1
  of §6.10, which attacks the confirmed issue term and is out of scope for this
  assignment.

**Operational notes carried forward** (from the same bulletin, all confirmed in this
session): `mlxfast submit` **exits 0 even when it refuses**, so a dispatch is real only
if stdout prints a submission id — never trust `$?`. Notes must be ≥ 5120 B or the CLI
refuses while still exiting 0. Run `mlxfast submissions | tail -3` immediately before
every dispatch and only dispatch when the last row is terminal. Never blind-retry a
`failed` receipt.
