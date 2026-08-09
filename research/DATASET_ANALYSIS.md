# Workload analysis — what "the data" is for this target

This is an inference-optimization target, so the analogue of a dataset analysis
is a characterisation of **the frozen measurement window and the work it
implies**. Everything below is measured or read from source, not assumed.

Last verified against base `8486638578a283de40369172f68c3a4d2d6a5365`.

---

## 1. The measurement window

Two axes, both scored:

| axis | shape | score weight |
|---|---|---|
| prefill | one 512-token prompt | 25 % |
| decode | teacher-forced, 512-token seed then **128 single-token steps** | 75 % |

`score = decode_speedup^0.75 * prefill_speedup^0.25`, both floors 0.95, paired
against a same-session baseline.

Two consequences that shape every experiment:

- **Decode is a batch-1, one-token-per-invocation regime.** Every matmul is a
  matrix-vector product. Arithmetic intensity is ~1, so decode is a *movement
  and latency* problem, not a FLOPs problem. This is why `_nax` tile kernels,
  the M5 Neural Accelerator (≥32×32 tiles), and every batching trick are
  structurally unavailable on the 75 %-weighted axis.
- **The serial non-speculative rule** means an invocation may compute logits and
  KV rows only for tokens supplied in that invocation, and must advance KV by
  exactly the supplied length. No drafting, lookahead, deferred rows, or
  cross-request state. Combined with batch-1, this fixes the shape of the work
  and leaves only *how* it is executed as the optimization surface.

Conversion constant for planning: **0.015280 % score per µs/step of decode**
(already bridges M4 → M5). Detection bar ≈ **80 µs/step** decode, ≈ **1.35 ms**
prefill.

---

## 2. Model constants (`Sources/MLXFastModel/LagunaConfig.swift:10–45`)

| quantity | value |
|---|---|
| vocabulary | 100,352 |
| hidden size | 2,048 |
| layers | 40 |
| dense intermediate (layer 0 only) | 8,192 |
| KV heads | 8 |
| head dim | 128 |
| **full-attention layers** | 0, 4, 8, …, 36 — **10 layers, 48 query heads** |
| **sliding-window layers** | the other **30 layers, 64 query heads** |
| sliding window | 512 positions |
| RMSNorm eps | 1e-6 |
| experts | 256 routed, top-8, + 1 shared |
| MoE intermediate | 512 (routed), 512 (shared) |
| routed scaling factor | 2.5 |
| bos / eos | 2 / [2, 24] |
| tensors | 912 |
| resident text tower | ≈21.6 GB, NVFP4, fully RAM-resident |

**The 10/30 layer split is the single most exploitable structural fact.** Two
distinct attention kernels, two distinct head counts, two distinct KV read
patterns, and two distinct dispatch geometries (h48 → 4,096 threadgroups, h64
→ 5,120) coexist on the same forward pass. A change that helps one can be
neutral or harmful on the other, and several past experiments failed
attribution because they did not separate them.

Also note: **the sliding layers only ever need the latest 512 KV positions**,
which is a standing invitation to reduce KV movement on 30 of 40 layers.

---

## 3. Decode byte census — where the bytes actually go

Measured round 87b. Total ≈ **1.69 GB per decode step**, amplification ≈1.0×
(i.e. essentially no re-reading; the pool is already close to optimal).

| component | MB/step | share |
|---|---|---|
| attention weights | 763.5 | 45 % |
| MoE (routed + shared) | 590.4 | 35 % |
| LM head | ~111 | 6.6 % |
| dense L0 MLP | 100.7 | 6.0 % |
| KV read | 86.5 | 5.1 % |
| router | 40.9 | 2.4 % |

Weights-only ≈1,606 MB; true DRAM traffic ≈1.42–1.50 GB.

---

## 4. Time census — where the microseconds actually go (M4 Pro, 8,234 µs/step)

| component | µs/step | share | character |
|---|---|---|---|
| weight streaming | 5,700–5,900 | ~70 % | 86.9–98.2 % of achievable 239.7 GB/s |
| fused SDPA | ~880 | ~10.5 % | issue / latency-bound |
| glue | ~640 | ~7.6 % | latency-bound, floor ≈152 µs |
| boundaries and gaps | 25–450 | ~2–5 % | scheduling |

**The byte floor is ≈5,582 µs, leaving ≈338 µs of headroom in the streaming
pool.** That pool is finished. The remaining M4-visible money is in glue
latency, dispatch boundaries and overlap — roughly 1,100–1,500 µs of
addressable surface, of which the practically reachable fraction is far
smaller (see §6).

---

## 5. The regime split — the most important caveat about all of §4

**§4 was measured on M4 Pro, which is bandwidth-bound. The ranked host is an
M5 Max, which is instruction-bound at ~89 % utilization.**

These are different bottlenecks, so the two census tables above rank levers
differently on the two machines. The measured transfer factor for
byte-reduction levers is **−0.40 ± 0.24** — they *hurt* on the ranked host.
The load-bearing datum: PR #137 delivered −63.7 µs/token on M4 and **+24.6
µs/token on M5** (receipt `99b71258`).

Practical rule: **declare a mechanism class for every decode lever.** "Move
fewer bytes" should be expected to transfer negatively; "issue fewer
instructions", "remove a dispatch boundary", and "hide latency" should not.

Offline evidence for the M5 side comes from `xcrun applegpu-nt -arch
applegpu_g17s`; see rule 42 in
`research/advisor-r92-rule42-rewrite-and-lever2-obituary.md`. Its key finding
for lever selection: **float ALU encodes identically on both architectures,
integer ALU is +16.7 % denser on the M5 generation.**

---

## 6. Cost constants for planning

| item | value | source |
|---|---|---|
| dispatch boundary | **1.4064 µs** flat (WIDE); TINY 0.7258; ratio 1.94× | rule 41 |
| — of which serialization/ordering | 1.073 µs (76.3 %) | rule 41 |
| — of which fixed cost | 0.315 µs (22.4 %) | rule 41 |
| — of which bytes at 4,096 B | 0.018 µs (1.3 %) | rule 41 |
| in-kernel `threadgroup_barrier` | **0.0293 µs**/barrier/dispatch, saturating after ~8 | #469 |
| SPLIT=1 → end-to-end conversion `c` | **1.247 [0.90, 1.59]** | #473 |
| profiler overhead under SPLIT=1 | **+1,642 µs/step** (24× a typical effect) | #473, #475 |
| submitted-byte price | 0.015224 % per MB | PR #110 |
| decode dispatches per step | 406 | #473 |
| decode command buffers per step, `nat` | 45.0 | #473 |
| decode command buffers per step, `s1` | 406.0 | #473 |

The barrier-vs-dispatch ratio is ≈48×, which is why removing a *dispatch* is
worth roughly fifty times more than removing a *barrier* and why the two must
never be priced with the same constant.

---

## 7. What this analysis implies for experiment design

1. **Never quote an unpaired timing.** Cross-process σ on per-run wall medians
   is 48–49 µs/step, which is over half the detection bar. Use paired ABBA
   census in the `nat` regime; see the σ table in
   `research/CURRENT_RESEARCH_STATE.md` §7.
2. **Measure the overlap ceiling before building a latency-hiding lever.** #475
   found a 12.80 µs/step ceiling at a site where naive arithmetic predicted
   4× more, and captured 54 % of it.
3. **Separate the h48 and h64 paths** in any attention or QKV experiment; they
   are different kernels with different geometry.
4. **Treat geometry as neutral-until-proven.** #48's threadgroup collapse on
   the QKV grid looked like a win on M4 and returned **−0.1488 %** on the
   ranked host (receipt `285f79fa`).
5. **A per-round gain of ~0.13 % is below a useful cadence.** Prefer levers
   whose *family* aggregate clears the 80 µs/step bar over single sites that
   individually do not.
