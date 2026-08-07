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

_(pending receipts)_
