# Step 0 occupancy audit — fused sliding / full attention kernels

Assignment `maple-2026-08-05e-sliding-attn-occupancy` r1, PR #56, student
maple-nezuko. Brief: `research/BRIEF_QUEUED_SLIDING_ATTN_REWRITE.md` §3 Step 0.

**Verdict: the threadgroup-memory occupancy premise is refuted, and the
occupancy premise itself is refuted a second time at the throughput level.
R1 (head split, 32→64 threadgroups) and R4 (epilogue plane shrink) are
predicted regressions or no-ops on both M4 Pro and a ~40-core M5 Max. R2
(deeper load pipeline) is the only rung of the ladder whose mechanism
survives. No ranked receipt was consumed.**

Host for every measurement below: Apple **M4 Pro**, `architecture.name =
applegpu_g16s` (Apple GPU generation 16, so `_nax` prefill kernels are *not*
reachable — irrelevant here, both fused attention kernels are plain JIT
`MLXFast.metalKernel` and do execute), **20 GPU cores**, 48 GB unified memory,
macOS 26.5.2. `maxThreadsPerThreadgroup = 1024×1024×1024`,
`maxThreadgroupMemoryLength = 32768 B`, `recommendedMaxWorkingSetSize =
40200896512`.

Reproduce everything in this document with:

```bash
xcrun swiftc -O research/nezuko_occupancy_probe.swift -o /tmp/nezocc && /tmp/nezocc
```

The probe is research-only (`research/nezuko_occupancy_probe.swift`, no scored
bytes). It **slices the two kernel bodies straight out of
`Sources/MLXFastModel/LagunaRuntimeModel.swift`** by label (`source:` /
`header:`), dedents to the closing-delimiter indent, and asserts on unexpected
escapes, so it cannot drift from the scored kernels. It rebuilds MLX's
generated buffer signature (`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/common/metal_kernel.cpp:90-158`)
so the compiled function is signature-identical to the one the runtime JITs.

---

## 1. The four required numbers, both kernels (Phase A)

Read from a **compiled `MTLComputePipelineState`**, not from source arithmetic
(`MTLComputePipeline.hpp:148` `maxTotalThreadsPerThreadgroup`, `:163`
`staticThreadgroupMemoryLength`, `:167` `threadExecutionWidth`). MLX itself
reads only the first of these, at
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/common/metal_kernel.cpp:104-112`;
the pipeline is created once and cached at
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp:705-727`, with
`setFastMathEnabled(false)` on the JIT library (`device.cpp:622-650`).

| | `laguna_sliding_fused_attn_ring_v1` | `laguna_full_fused_attn_grow_v1` |
|---|---|---|
| declaration | `LagunaRuntimeModel.swift:1381-1382` | `:1855-1857` |
| `source:` literal | `:1389-1694` (304 lines) | `:1864-2215` (350 lines) |
| assembled MSL | 15,146 B | 16,624 B |
| **`staticThreadgroupMemoryLength`** | **18,432 B** (18.000 KiB) | **18,432 B** (18.000 KiB) |
| **`maxTotalThreadsPerThreadgroup`** | **1024** | **1024** |
| `threadExecutionWidth` | 32 | 32 |
| simdgroups per dispatched TG | 32 | 32 |
| dispatched grid / TG | `((heads/2)*1024, 1, 1)` / `(1024,1,1)` (`:1799-1800`) | identical form (`:2272-2320`) |
| threadgroups per call | 64/2 = **32** | 48/2 = **24** |

`maxTotalThreadsPerThreadgroup` is 1024 for both, equal to the dispatched
width, so **the register file does not cap either kernel below its shipped
threadgroup size**. (Head-room *above* 1024 is not observable through this
property; see §7 for the reusable gate that re-checks it for any candidate
body.)

18,432 B is exactly the source arithmetic — 4 × `bfloat[128]` staging rows
(`tg_q0/tg_q1/tg_k/tg_v`, 1024 B) + `outputs[4 * BN * BDP]` = 4·32·33·4 =
16,896 B (`:1495`, full kernel `:1972`) + `max_scores[2*BN]` +
`sum_exp_scores[2*BN]` = 512 B (`:1496-1497`, `:1973-1974`). The compiler adds
nothing.

**Threadgroups per call:** `slidingAttentionHeads = 64` and
`fullAttentionHeads = 48` (`Sources/MLXFastModel/LagunaConfig.swift:26,24`),
two heads per threadgroup (`head0 = pair_tg * 2`), so 32 and 24.

### The binding occupancy term

**(b) thread / simdgroup slots per core: 96 simdgroups = 3072 threads per core**
on `applegpu_g16s`, i.e. 61,440 thread slots and 1,920 simdgroup slots across
the 20-core part. Not (a) threadgroup memory and not (c) the register file.

Resolved from the device and from compiled pipelines (§2, §3), not from a blog
post. The single invariant "3072 threads per core" reproduces every measured
residency limit exactly:

| threads/TG | measured max co-resident TGs (20 cores) | TG/core | threads/core |
|---|---|---|---|
| 1024 | 60 | 3 | 3072 |
| 512 | 120 | 6 | 3072 |
| 256 | 240 | 12 | 3072 |
| 128 | 480 | 24 | 3072 |

For the shipped 1024-thread shape that is **3 co-resident threadgroups per
core**, not one.

---

## 2. Phase B — residency is flat in threadgroup memory

Method (the third method I tried; §8 records why the first two were invalid). A
synthetic kernel whose static threadgroup allocation is a compile-time
parameter performs a **monotone all-or-nothing rendezvous**: thread 0 of each
threadgroup does one `atomic_fetch_add` on a device counter, spins on a relaxed
`atomic_load` until the counter reaches K or a 500,000-spin timeout, writes a
threadgroup flag, and after `threadgroup_barrier` a *different* thread stores
the result to `ok[tgpig.x]`. The dispatch passes iff all K slots report
success, which can only happen if all K threadgroups were resident
simultaneously. The kernel also fills its threadgroup array from a runtime
config value and folds the last element into the flag, so neither the
allocation nor the barrier is elidable. A binary search over K (invariant: `lo`
passes, `hi` fails) yields the maximum co-resident K.

Two independent runs; the table is the second (4 memory sizes), the first swept
9 sizes with identical results:

```
  variant                       maxK   TG/core   sg/core   maxMs
  1024t static 16B                 60      3.00      96.0     124.5
  1024t static 9984B               60      3.00      96.0     102.0
  1024t static 18432B              60      3.00      96.0     101.8
  1024t static 32768B              60      3.00      96.0      95.9
  512t static 16B                 120      6.00      96.0     203.4
  512t static 9984B               120      6.00      96.0     203.3
  512t static 18432B              120      6.00      96.0     204.7
  512t static 32768B              120      6.00      96.0     196.2
  256t static 16B                 240     12.00      96.0     406.6
  256t static 9984B               240     12.00      96.0     393.9
  256t static 18432B              240     12.00      96.0     388.8
  256t static 32768B              120      6.00      48.0     483.2
  128t static 16B                 480     24.00      96.0    1177.7
  128t static 9984B               480     24.00      96.0     810.5
  128t static 18432B              480     24.00      96.0     913.6
  128t static 32768B              367     18.35      73.4     735.2
```

**Residency is flat from 16 B to 32,768 B of static threadgroup memory at every
threadgroup width that the shipped kernels could plausibly use.** At
1024 threads it is 60 threadgroups whether the kernel allocates 16 B or the
full 32 KiB device maximum.

Consequences for the brief's arithmetic (§2 claim 1, `research/BRIEF_QUEUED_SLIDING_ATTN_REWRITE.md:136-141`):

* `18432 / 32768 = 0.562 ⇒ 1 TG/core` is **invalid**. `maxThreadgroupMemoryLength
  = 32768` is a **per-threadgroup API cap, not a per-core physical pool**. Three
  co-resident 1024-thread TGs at 32,768 B each is 96 KiB of simultaneously live
  threadgroup memory on one core; the 128-thread/18,432 B cell reaches 24
  TG/core = 432 KiB. No 32 kB/core budget exists.
* Honest residual: the two 32,768 B cells (256t → 6 TG/core = 192 KiB;
  128t → 18.35 TG/core = 576 KiB) *do* fall below 96 sg/core, and they do not
  fit any single per-core pool figure either (18,432 B admitted 432 KiB).
  Most likely allocation granularity or fragmentation exactly at the API
  maximum. Unexplained, and irrelevant to both shipped kernels, which use
  1024 threads and 18,432 B — a cell that is flat across two runs.
* First-run noise, for the record: individual cells occasionally under-report
  (256t/18432B gave 159 in run 1 and 240 in run 2; 128t/9984B gave 480 then
  319). A binary search is only sound if a passing K never fails, and a
  timeout-based rendezvous can produce a false negative under scheduling
  jitter, which then truncates the search. **Take the maximum over repeats.**
  Every disagreement resolved upward to the 3072 threads/core line; nothing
  ever exceeded it.

---

## 3. Phase C — the real kernel body, and the direct plane-shrink counterfactual

The same rendezvous prologue (flat function scope, all identifiers `db_`
prefixed) is injected ahead of the **extracted real sliding body**, which adds
16 B to the allocation (18,448 B). A second variant textually replaces
`threadgroup U outputs[4 * BN * BDP];` with `[2 * BN * BDP]` — 10,000 B,
deliberately *not* a functionally correct kernel, purely a resource
counterfactual that answers "would halving the epilogue buffer buy residency?".

```
  variant                       maxK   TG/core   sg/core   maxMs
  real 4 planes 18448B             60      3.00      96.0     102.0
    maxTotalThreadsPerThreadgroup 1024
  real 2 planes 10000B             60      3.00      96.0     101.9
    maxTotalThreadsPerThreadgroup 1024
```

* The real body, with its full register pressure, reaches **exactly the same 96
  simdgroups per core as a near-empty synthetic kernel**. The register file is
  not binding.
* **Halving the epilogue threadgroup buffer buys precisely zero extra
  residency.** This kills R4 outright, and it removes R1's threadgroup-memory
  rationale (the brief motivates R1's 4→2 plane shrink to ~9.9 kB as the enabler
  of higher residency; residency was never limited by that buffer).

Phase D is an independent cross-check that does not use a binary search: one
heavily oversubscribed dispatch, counting successful slots. It systematically
reports ~78% of the Phase B/C figure — drain is gradual, so it is a lower bound
— but it is **flat in threadgroup memory at 1024 threads (45, 45, 45 passing at
16 B / 18,432 B / 32,768 B) and identical for both real bodies (45, 45)**,
confirming Phase B/C by a different mechanism.

---

## 4. Phase E — the decisive result: co-resident threadgroups do not overlap

Residency is not the same question as throughput. Phase E times the **real
extracted sliding body** (plain MLX signature, no probe buffers,
`staticThreadgroupMemoryLength` asserted `== 18432`) as a function of
threadgroup count K: 200 serial dispatches in one command buffer (default
`MTLDispatchType.serial`, so each dispatch fully drains, exactly as the runtime
sees it), best of 3, GPU-busy time from `cb.gpuEndTime - cb.gpuStartTime`.
Dummy buffers; the kernel has no value-dependent control flow (the only
conditional is the index-derived `sub_a`/`sub_b` alpha-skip), so contents do not
change the instruction stream. Buffer contents are bf16 `1.0` so RMSNorm's
`rsqrt` never sees zero.

```
     K   TGs/core     us/call   us/TG    req GB/s   uniq GB/s   vs K=32
     1       0.05        9.23    9.23        28.4        28.4
     2       0.10        9.23    4.62        56.8        28.4
     4       0.20        9.39    2.35       111.7        27.9
     8       0.40        9.38    1.17       223.5        55.9
    16       0.80        9.45    0.59       443.7       110.9    0.500
    20       1.00        9.45    0.47       554.6       138.6
    24       1.20       17.41    0.73       361.4        90.4
    32       1.60       18.91    0.59       443.5       110.9    1.000  <- shipped
    40       2.00       19.28    0.48       544.0       136.0    1.019
    48       2.40       26.25    0.55       479.4       119.9    1.388
    56       2.80       26.52    0.47       553.5       138.4    1.402
    60       3.00       26.59    0.44       591.6       147.9    1.406
    64       3.20       33.87    0.53       495.3       123.8    1.791  <- R1
    72       3.60       34.90    0.48       540.7       135.2    1.845
    96       4.80       42.65    0.44       590.0       147.5    2.255
   120       6.00       50.03    0.42       628.8       157.2    2.645
   128       6.40       57.34    0.45       585.2       146.3    3.032
   240      12.00       98.19    0.41       640.7       160.2    5.192
```

`req` counts bytes *issued* (each TG streams 512×128 K and V rows = 262,144 B);
`uniq` counts *distinct* bytes (4 consecutive TGs share one KV head, `kv_head =
head0 / gqa`, `gqa = 8`).

### 4.1 A pure wave staircase, quantised at 20 threadgroups

With `w = ceil(K / 20)` (20 = the core count) the whole sweep fits
`t ≈ 8.16·w + 1.1 µs` to within ±5%:

| K | 1..20 | 24 | 32 | 40 | 48..60 | 64..72 | 96 | 120 | 128 | 240 |
|---|---|---|---|---|---|---|---|---|---|---|
| w | 1 | 2 | 2 | 2 | 3 | 4 | 5 | 6 | 7 | 12 |
| µs measured | 9.2–9.5 | 17.4 | 18.9 | 19.3 | 26.3–26.6 | 33.9–34.9 | 42.7 | 50.0 | 57.3 | 98.2 |
| µs model | 9.3 | 17.4 | 17.4 | 17.4 | 25.6 | 33.7 | 41.9 | 50.1 | 58.2 | 99.0 |

The marginal cost of a wave, **8.16 µs, is 88% of the latency of one lone
threadgroup, 9.23 µs.** A machine that overlapped co-resident threadgroups
would show a marginal wave cost far *below* single-TG latency. It does not:
**three threadgroups are co-resident on a core (Phase B/C) and they serialise
almost perfectly.** The most direct reading is K=24 versus K=20 — adding 4
threadgroups to 4 of the 20 cores costs 17.41 vs 9.45 µs, i.e. two threadgroups
sharing a core take 1.84× as long as one, where perfect overlap would be 1.0×
and perfect serialisation 2.0×. **Overlap is worth ≤ 12%, not 2×.**

Equivalently, aggregate throughput (`µs/TG`) improves only from 0.472 (1
TG/core) to 0.409 (12 TG/core) — **13% total**. That is the entire
occupancy-side headroom of this kernel on this host, against the brief's
priced 428 µs/step (64% of 670 µs/step).

### 4.2 Probe versus the real runtime

K=32 measures **18.91 µs/call**, against the brief's M4-instrumented
**22.34 µs/call** (`research/nezuko-pr9-dispatch-fusion.md:120-144`, via
`research/BRIEF_QUEUED_SLIDING_ATTN_REWRITE.md:22`). The probe recovers 85% of
the real per-call cost with dummy buffers and no surrounding pipeline, which is
close enough to treat the K-sweep as a valid *relative* screen. It is not a
substitute for scored timing.

### 4.3 The bandwidth headroom does not exist

The brief prices 2.097 MB/call unique at 22.34 µs = 93.9 GB/s = 36% of the
260.2 GB/s M4 ceiling, and reads the missing 64% as recoverable. Phase E
reproduces the *unique* figure (110.9 GB/s at 18.91 µs) but also shows the
**issued** figure is **443 GB/s at the shipped K=32, already 170% of the DRAM
ceiling**, rising to 641 GB/s at K=240. Those reads are therefore served from
cache, not DRAM: the 2 MB working set of one layer's 8 KV heads fits, and four
threadgroups deliberately re-request the same 262,144 B. The kernel is
**latency-bound inside the core, not DRAM-bandwidth-bound**, so "36% of ceiling"
is a logical-byte framing and not evidence of 2.8× headroom.

---

## 5. What this does to the ladder

The wave model plus the serialisation result gives a prediction for each rung on
both hosts. M4 Pro has 20 cores; the brief and `AGENTS.md` describe the ranked
host as a ~40-core M5 Max (`research/BRIEF_QUEUED_SLIDING_ATTN_REWRITE.md:138`).
At ≥32 cores, the shipped 32-TG sliding dispatch is a **single wave**, so the
whole call costs one per-threadgroup latency and nothing else.

| arm | TGs | M4 Pro waves | M5 Max (~40c) waves | prediction |
|---|---|---|---|---|
| shipped sliding | 32 | 2 (20+12) | **1** (8 cores idle) | — |
| **R1** head split | 64 | **4** (measured 1.791× slower) | **2** | **regression on both** unless per-TG latency more than halves |
| **R4** plane shrink | 32 | 2 | 1 | **no-op** (Phase C: zero residency change) |
| **R2** deeper load pipeline | 32 | 2 | 1 | **the only surviving lever**: cuts per-TG latency, which multiplies through every wave on both hosts |
| R3 pre-barrier prefetch | 32 | 2 | 1 | same mechanism as R2, same sign |
| (new) head *merge*, 4 heads/TG | 16 | **1** | 1 | halves M4 cost at fixed per-TG work (K=16 is 0.500× K=32) but on M5 it is 1 wave either way and the TG gets fatter ⇒ **M4-only win, likely M5 regression**. Also needs > 32 KiB of `outputs` at the current 2 planes/head, so it is not free. Not recommended. |

**R1 is the arm the brief expected to win, and it is the arm this audit
predicts to lose.** The brief's own §5 (`:296-302`) notes that 32 TGs is "a
single under-filled wave on a ~40-core M5 Max, so R1's win *should* be larger
on M5". Under measurement the inference inverts: if the shipped dispatch is
already one wave, doubling threadgroups adds a **second** wave, and co-resident
threadgroups do not overlap. R1's own named risk (K/V requests double, 4→8 TGs
per KV head) compounds it: per-TG K/V request volume is unchanged by a head
split, so 32 TGs already issue 8.389 MB/call against 2.097 MB unique, and R1
would issue 16.78 MB.

**R2 survives entirely.** Brief §2 claim 2 (`:142-150`) — in-order issue, only
4 vec4 loads (32 B/lane) in flight, then a long dependent stretch of 16 FMAs, 4
serialised `simd_sum` shuffle trees, 4 `exp`s and 32 accumulate FMAs
(`:1537-1616`), with the compiler unable to hoist next-trip loads because
`k_cache`/`v_cache` are also *written* in phase 2 (`:1486-1487`) so
non-aliasing cannot be proven — is untouched by anything measured here, and is
now the *only* diagnosed mechanism left. It attacks per-threadgroup latency,
which is the quantity that sets the cost of a wave, so its win multiplies
through on a 2-wave M4 Pro and on a 1-wave M5 alike. That also makes **M4 a
valid screen for R2** (unlike R1, whose sign depends on the core count).

The brief's §2 claim 4 (28 of 32 simdgroups idle before the `:1471` barrier,
because only sg 0/1/2 do Q0/Q1/K RMSNorm+RoPE and sg 3 copies V) is a source
fact and remains true, but Phase E cannot decompose the 9.23 µs single-TG
latency into prologue and main loop, so its share is unmeasured. Follow-up in
§9.

### 5.1 A pricing caveat the advisor should see before any further arm

The 670 µs/step price is 30 calls × 22.34 M4 µs, and the campaign's M4→M5
conversion (×0.812) was calibrated on end-to-end decode. For *this* kernel the
transfer is not a scalar: the wave count changes from 2 to 1 between the two
hosts. The naive wave model puts the sliding kernel at ≈9.4 M4-µs-equivalent
per call on a 40-core M5 — roughly **2× cheaper than the M4-derived price** —
which would shrink the recoverable envelope proportionally. I cannot verify
this without an M5 measurement, but it is the largest single uncertainty in the
brief's pricing and it argues for re-pricing the kernel on M5 (a cheap
instrumented run) before spending a receipt on any arm.

---

## 6. Reconciliation with the programme's "24 simdgroup slots per core"

`research/CURRENT_RESEARCH_STATE.md:1026-1027` carries a working figure of 24
simdgroup slots per core, sourced to §0.9.8 (`:515-545`). Measurement says 96.

The two are the same fact with a unit slip. §0.9.8 does not state 24
numerically; it observes that the gather-GEMM keeps ~4 active simdgroups per
threadgroup and that "a core needs ~4 co-resident threadgroups to keep its
simdgroup slots busy". A 4-simdgroup threadgroup is 128 threads, and the
128-thread row of Phase B measures **exactly 24 threadgroups per core**. So the
"24" is *threadgroups* per core for a 4-simdgroup threadgroup — the same 96
simdgroup slots, described one level up. §0.9.8's conclusion (ample threadgroup
headroom for the gather-GEMM) is unaffected; only the downstream unit needs
fixing.

Independently, `maxTotalThreadsPerThreadgroup = 1024` on both attention kernels
already proves at least 32 simdgroup slots per core must exist, which is
incompatible with a literal 24.

---

## 7. Reusable gate for any candidate body

Phase A + Phase C together are the occupancy gate for R2, R3, or any future
rewrite. Point the probe at the modified `source:` literal and require:

1. `maxTotalThreadsPerThreadgroup == 1024` — if a candidate spills enough to
   drop below 1024 the dispatch is illegal, and this catches it before any
   timing run. This is the concrete test of R2's "+12 registers/thread,
   occupancy is not register-bound" assumption; the brief asks for exactly this
   confirmation.
2. Phase C `maxK == 60` (3 TG/core) — residency unchanged.
3. `staticThreadgroupMemoryLength <= 32768` — the per-threadgroup API cap is
   real even though the per-core pool story was not.

Phase E is the companion *scaling* gate: it prices a candidate body at the
shipped K=32 against the current 18.91 µs/call before committing to a
`./benchmark.sh --local-iterate` pair, at a cost of a few seconds.

---

## 8. Two earlier methods that were wrong, and why

Recorded because both produced confident, plausible, and false numbers.

1. **Atomic active-count with a spin loop.** Each threadgroup incremented a
   counter on entry, spun, decremented on exit, and tracked the maximum. It
   reported 98–126 co-resident 1024-thread threadgroups, i.e. up to 6.3 TG/core
   — impossible. Cause: the non-leader threads had no observable effect and the
   compiler eliminated their work, so the measured "threadgroups" were not
   carrying their real footprint. Any residency probe must make every thread's
   work observable.
2. **Sink store + LICM-defeating sampling + a timing model.** Adding a sink
   store fixed the dead-code problem but the kernel became ALU-latency-bound,
   and the two readings (40–59 counted co-resident; waves ≈ 7.1 inferred from
   time) were mutually inconsistent. A count that depends on how fast the
   probe's own arithmetic runs is not a residency measurement.

Both were replaced by the monotone pass/fail rendezvous of §2, whose answer is
a property of the schedule rather than of the probe's speed, and cross-checked
by the independent oversubscription count of Phase D.

---

## 9. Limitations

* **M4 Pro, 20 cores, generation 16 — not the ranked M5.** Every §5 M5 row is
  a model-based inference from the measured wave law plus an assumed ~40-core
  M5 Max, not a measurement. Per-core slot counts could also differ on M5,
  though 1024-thread dispatches there imply ≥32 simdgroup slots per core too.
* Phase E uses dummy buffers, a single layer's worth of cache addressing, and
  `widx = 0`. Control flow is data-independent, so the instruction stream is
  right, but cache residency in a real decode step is not identical.
* Per-cell residency search noise: a timeout-based rendezvous can false-negative
  and truncate a binary search. Conclusions here use the maximum over two
  independent runs, and nothing ever exceeded 3072 threads/core.
* The 32,768 B residency anomaly (§2) is unexplained.
* The 9.23 µs single-threadgroup latency is not decomposed into phase 1
  (`:1421-1471`), phase 2 (`:1473-1489`), the phase 3 ring loop (`:1491-1623`)
  and the epilogue (`:1624-1694`). A cheap follow-up is to time counterfactual
  bodies with each phase stubbed, using the harness that now exists.
* No scored-path timing was run and no ranked receipt was consumed. Nothing in
  `Sources/` changed: `LagunaRuntimeModel.swift` is byte-identical at
  508,529 B.
* The full kernel's K-sweep was not run (its buffer shapes differ: `params` is
  `uint32[3] = {widx, widx+1, capacity}` and the caches are capacity-sized).
  Phase A covers the four numbers the brief required for it; the timing sweep is
  a cheap addition now that the harness exists, and it would price the
  companion `full_fused_attn_grow_v1` Step 5 PR (24 TGs = 2 waves on M4 Pro,
  1 wave on M5, so the same conclusions are expected to carry).

---

## 10. Recommendation

1. **Merge this refutation** and retire R1, R1+R2, and R4 from the ladder
   without spending an M5 receipt on them. The brief pre-committed to this
   outcome: "If it refutes the threadgroup-memory premise, say so and I will
   merge the refutation."
2. **Proceed to R2 as the next arm**, which is where the brief's mandated order
   (Step 0 → R2 → …) already puts it, and which is now the only rung with a
   surviving mechanism. Gate it with §7 before timing it, screen it with Phase E
   at K=32, then run a matched `./benchmark.sh --local-iterate` pair.
3. **Re-price the sliding kernel on M5 before any receipt.** §5.1: the M4→M5
   scalar cannot be right for a kernel that changes wave count between the two
   hosts, and the whole 428 µs/step envelope depends on it.
4. Correct the "24 simdgroup slots per core" figure in
   `research/CURRENT_RESEARCH_STATE.md:1026-1027` to 96 simdgroup slots (24
   threadgroups per core *for a 4-simdgroup threadgroup*), per §6.
