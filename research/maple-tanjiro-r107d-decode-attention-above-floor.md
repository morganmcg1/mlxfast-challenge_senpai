# R107-D — Decode fused attention above the DRAM floor: what is the 280.8 µs/step actually made of?

Student: maple-tanjiro · PR #642 · assignment `maple-r107-d-decode-attention-above-floor`
revision `r107-d-rev1` · base `09525f5c0ea007118708179b5c190a4050d562a5`
Host: Apple M4 Pro, 20 GPU cores, 48 GiB unified, macOS 26.5.2 (25F84), `applegpu_g16s` gen 16.

**Verdict: `N-ISSUE-BOUND`.** The 280.8 µs/step that the two fused decode
attention kernels spend above their arithmetic DRAM floor is *instruction issue*,
not memory latency and not memory bandwidth. An injected arithmetic dose is paid
at 97.7 % of the host's theoretical peak fma issue rate, with a slope of
t = +36 … +151 across three independent sessions and both kernels. Per the
assignment's own Stage-1 decision rule this outcome is terminal: **lever P1
(the prologue prefetch hoist) was not built**, and no submitted-surface byte was
changed. The submitted diff for this experiment is **zero bytes**.

One extra session of the same instrument also prices the assignment's fallback
levers: masked instructions cost full price (a dose issued by 1 lane in 32 costs
99 % of the same dose on all 32), so widening a narrow lane region does convert
into time — but both target regions run once per dispatch and are worth
≈0.063 % (P2) and ≈0.036 % (P3) of `cs`, i.e. 6× to 60× below bar. **The whole
Stage-2 menu is therefore closed: P1 by rule 82 and #540, P2 and P3 by
arithmetic.**

This is offered as the assignment's "clean, well-controlled null": it closes the
latency/bandwidth reading of the 280.8 µs, and it replaces it with a measured
instruction-slot budget plus an exact exchange rate from instructions to score.

---

## 1. Deconfliction statement (rule 83)

This experiment is *not* any of the following previously-closed items. Each is
named with what makes it different.

| Prior work | What it changed | Why this is different |
|---|---|---|
| Split-K / flash-decoding over the KV length (#196 §4.12.8 C, #566) | Splits one head's KV range across more threadgroups and merges partials | Nothing here splits, re-partitions, or adds threadgroups. Both kernels keep their shipped grid exactly (32 / 24 TGs). The Phase-E K ladder below *measures* the cost of more co-resident TGs but ships none. |
| Ring-buffer depth change (#539) | Changed the software pipeline depth of the K/V prefetch ring | Ring depth is untouched: sliding stays 4-deep, full stays 2-deep. |
| float4 merge epilogue (#555) | Vectorised the epilogue store | The epilogue is unmodified. §8 *prices* the epilogue's lane mask; it does not rewrite it. |
| Fusion-for-bytes (#619, `N-ONCE`) | Fused stages to remove intermediate traffic | This is a measurement of what the existing fused kernels are bound by, not a new fusion. |
| Rule 98 (routed gate/up QMV null prior) | Scoped to the routed gate/up quantised matvec | Attention work is permitted by rule 98; its null prior is respected, and the whole 98.3/98.4/98.5/98.9 control apparatus is applied below. |
| `lagunaRoPEAtlasViewsEnabled` (`LagunaRuntimeModel.swift:628`, default OFF) | Alternate RoPE table views | Flag untouched, still OFF, and not exercised by this probe. |
| Wider per-lane loads (#597) | Widened the per-lane K/V load width | Forbidden without a frieren margin certificate; not attempted, not built, not measured as a candidate. #597 §:502-516 is cited below only as prior evidence about *cross-barrier placement*. |
| Cross-threadgroup redundant K RMSNorm + RoPE | Removes duplicated K-side normalisation across TGs | Not attempted. §9 shows the duplicated *reads* are cache hits worth ≤0.023 % of `cs`, which also bounds the value of de-duplicating them for bytes. |
| Dispatch-count reduction (rule 53, #502, #48, rule 65) | Fewer command-buffer dispatches | Dispatch count is unchanged; every number here is per-dispatch kernel time. |
| **R107-B (alphonse)** | Routed QMV kernel `LRM:7915-8027`, `threadgroupMemory = 0 B`, bitwise revert of depth-1 staging, verdict GATE CLOSED | A different kernel family and a different lever. R107-B's conclusion (issue-bound at 42.9 % of DRAM peak) is *corroborating context* for the MoE side; this report re-derives the same conclusion independently for the attention family from a dose curve rather than a revert. |
| **#540 (merged) — `CURRENT_RESEARCH_STATE.md` §5b `:2853-2881`, ledger row `:5736`; rule 82 `:804-812`, restated `:3898`** | Every prefetch-expressing variant of the attention kernel regressed **+5 … +7 %** at flat dose–response and identical occupancy. Verbatim: *"'issue work earlier across a barrier' is closed for the attention family."* Rule 82 **bans hoisting in the fused attention family**. #597 `:502-516`: *"the cost is the cross-barrier placement of the prefetch salvo, not the four loads."* | **This is a direct conflict with lever P1 as briefed**, and it is the reason the Stage-1 gate was worth running before touching the kernel. See §11 and the *Reply to advisor*. The present experiment does not hoist anything; it only measures. |

---

## 2. Anchors: what the brief said and what the tree says

The assignment's anchors have drifted by a few lines against base
`09525f5c`. Verified anchors in `Sources/MLXFastModel/LagunaRuntimeModel.swift`
(12,148 lines):

| Item | Briefed | Actual |
|---|---|---|
| Sliding kernel name line | `:1508` | **`:1505`** (`metalKernel(name:)` at `:1503`, env gate `:1500-1501`) |
| Sliding prologue `threadgroup_barrier` | `:1587` | **`:1589`** (`else if (sg == 3)` V copy is `:1583-1588`) |
| §12 stale reference | `:1940` | **`func lagunaSlidingFusedAttention` is at `:1927`**; `:1940` is inside its body, not the declaration. Anchor corrected here. |

Other verified anchors used below — sliding: RMSNorm `:1556-1561`,
`simd_shuffle` pairing `:1567-1570`, **`if (lane < 16)` RoPE `:1571-1582`**,
KV-cache write `:1591-1600`, ring setup `:1598-1620`, main loop
`int i = sg; for (; i + 3*BN < N; i += 4*BN)` `:1638-1639` (4 iterations × 4
unrolled stages = 16 rows/simdgroup), `T_LOAD_K` `:1654-1657`, `T_LOAD_V`
`:1662-1669`, dose anchor `U pair_score1 = 0;` **`:1672`**, epilogue `:1819-1872`
(three barriers, `simd_max`/`simd_sum`, `if (lane == 0)` store), macro header
`:1873-1920`. Full kernel: gate `:2010`, name `laguna_full_fused_attn_grow_v1`
`:2028`, loop `int i = sg; for (; i + BN < N; i += 2*BN)` `:2167-2168`
(`pipe_ka`/`pipe_kb` `:2173-2174`, 8 iterations × 2 stages), dose anchor
**`:2185`** (the visually identical line at `:2267` is the *tail* loop and is
deliberately not used), `func lagunaFullFusedAttention` `:2412`.

---

## 3. Rule 40 — the DESIGN and the arithmetic floor

**DESIGN.** One decode step runs 30 sliding-window layers through
`laguna_sliding_fused_attn_ring_v1` and 10 full-attention layers through
`laguna_full_fused_attn_grow_v1`. Per dispatch:

* sliding — 32 threadgroups × 1024 threads (32,768 threads), one TG per head
  pair (`head0 = 2 * tgpig.x`), `gqa = 8`, `headDim = 128`,
  `slidingWindow = N = 512`, 32 simdgroups/TG each walking 16 of the 512 rows;
* full — 24 threadgroups × 1024 threads (24,576 threads), `gqa = 6`, 8
  iterations × 2 pipeline stages.

**Arithmetic floor (bytes).** Sliding: 8 distinct KV heads × 512 positions ×
128 dims × 2 tensors × 2 B = **2,097,152 B** unique cache reads per dispatch,
plus 16,384 B of output. Requested bytes are 8,388,608 B — exactly **4.00×** the
unique figure, which is the GQA broadcast (four TGs read identical addresses);
see §9. At the host's measured 266.3 GB/s DRAM peak the unique bytes alone cost
**7.87 µs**; measured is **18.82 µs**, so the byte floor is **41.8 %** of the
call. The assignment's M5 arithmetic: sliding 309.5 µs/step against a 104.4 µs
floor, full 114.85 µs against 39.1 µs, i.e. **280.8 µs/step = 4.28 % of `cs`
sits above the floor**. This experiment asks *only* what that 280.8 µs is.

σ-table row (`CURRENT_RESEARCH_STATE.md` `:5649-5669`) for the decode axis is
the reference for what "detectable" means: 1 % of `cs` = 65.67 µs/step on M5,
decode price 0.015228 % per µs/step, and the assignment bar is **≥0.4 % of `cs`
= ≥26 µs/step with a CI95 excluding zero**.

---

## 4. Reachability (rule 77, stage 0) — artifact `stage0-arch-reach.txt`

The two kernels have **no `_nax` twin and no architecture predicate**:
`grep -c '_nax' Sources/MLXFastModel/LagunaRuntimeModel.swift` = **0**. The MLX
`_nax` gate is `can_use_nax &= gen >= (arch == 'p' ? 18 : 17)` at
`Vendor/mlx-swift/.../metal/device.cpp:926`; this host reports gen 16 so
`nax_available = false`, but because the attention kernels carry no variant,
**the same MSL program text runs on this host and on the ranked M5**. The only
residual difference is the Metal compiler target (`g16s` here vs `g17s` on M5)
and the core count (20 vs M5 Max's 40). Both are handled in §12.

## 5. Rule 75 — digests, and the register-report substitute

No submitted-surface file was modified at any point in this experiment, so the
before/after digests are identical by construction:

```
sources_digest  34ddd0032c26a8cc7960fcf6a1bfbdaeb21700768a814c62d780f3dd0267381f
vendor_digest   e408faf14f4a607fea0f0f9da0d462d0d4ab6769b70239a514cb8a23ee91debd
benchmark_json  e01d3ea1c9281cfe81e1693d987627005fed6963440fbef6a761e4f28dd67fb6
LagunaRuntimeModel.swift  a736b50f66b08b9004a807ff38226aaeb95ba836e6e833b51a8e862466d850c4
git diff --numstat <base> -- Sources Vendor benchmark.json  →  0 lines
```

All dosed variants were written to `/tmp` and handed to the probe as a *second
source path*; the probe extracts the kernel `source:`/`header:` string literals
from each file and compiles both in one process, so an A/B never requires a
worker rebuild and never touches the checkout.

**Register/spill report substitute.** Apple's toolchain publishes no register
allocation: `research/advisor-r89-agx-native-instruction-census.md` §5b
`:219-250` records that there is no `metal-dis`, and `metal-objdump -d` prints
AIR only. The campaign substitute, used here, is a live
`MTLComputePipelineState` read — `maxTotalThreadsPerThreadgroup`,
`staticThreadgroupMemoryLength`, `threadExecutionWidth` — plus the Phase-B/C
occupancy gate. Every dosed arm below reports
`maxTotalThreadsPerThreadgroup = 1024` and `staticThreadgroupMemoryLength =
18,432 B`, unchanged from base, which is the strongest available evidence that
the dose did not spill or change occupancy. That is the confound that would
otherwise fake an instruction-cost signal.

### 5b. Upstream-equivalence gate on the unmodified tree — artifact `stage0-upstream-equivalence-base.txt`

`research/run_upstream_equivalence.sh` was run on the exact tree reported here.
Because the submitted diff is zero bytes, this is a measurement of the **base**,
not of a candidate. It **fails on this host**, and the failure is worth stating
precisely rather than glossing:

* `EQUIVALENCE_EXACT_STEPS=8`, `EQUIVALENCE_EXIT=1`, 1 test executed (not a
  zero-test invocation), 37.3 s.
* Every greedy token matches: `runtimeToken == upstreamToken` on prefill and all
  8 decode steps (5991/509/902/5991/…).
* All 8 decode steps are **bit-exact**: `maximumAbsoluteLogitError = 0`.
* The single failing quantity is **prefill** `maximumAbsoluteLogitError = 0.125`
  (mean 0.0119) against the test's tolerance of exactly `0.0`.

The test is `lagunaRuntimeMatchesVendoredUpstreamOnM5WhenEnabled` — an
M5-targeted exactness assertion — and the divergence is confined to the prefill
axis, which is precisely the axis where this gen-16 host does not select the
`_nax` prefill kernels that the ranked M5 uses (§4). This is the documented
non-M5 base-divergence case; `MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT` was **not** set,
no gate was relaxed, and the failure is recorded here as a base property of a
non-ranked host. It cannot be attributed to this experiment: there is nothing to
attribute, the diff is empty. The decode axis — the only axis this experiment
touches or reasons about — is bit-exact and token-identical, and the
`--local-iterate` anchor on the same tree reports `max_abs_diff = 0` with the
expected `golden_hash`.

## 6. Geometry and occupancy control — artifact `stage0-occupancy-control.txt`

Both shipped kernels: `staticThreadgroupMemoryLength = 18,432 B`,
`maxTotalThreadsPerThreadgroup = 1024`, `threadExecutionWidth = 32`, 32
simdgroups/TG. Sliding is 356 source lines / 17,445 MSL bytes; full is 320 /
15,536. Phase-C measures **maxK = 60** co-resident threadgroups (3.00 TG/core).
Rule-77 assertion: the probe reproduces the shipped geometry exactly — sliding
`FERN_LADDER=32` TGs × 1024 threads with `gqa = 8`, full `FERN_LADDER=24` × 1024
with `gqa = 6`, tgMem 18,432 B in both — and the §7 reusable candidate gate for
this family is `maxTotalThreadsPerThreadgroup == 1024 && Phase-C maxK == 60 &&
tgMem ≤ 32768`.

### Phase-E threadgroup ladder — `[RESIDENT — NOT A HEADLINE]`

Real kernel body, dummy buffers, artifact lines `:85-107`. Resident numbers are
labelled per §98.5/98.9 and are used here *only* for the shape of the curve, not
for any headline delta:

| K (TGs) | µs | requested GB/s | unique GB/s |
|---|---|---|---|
| 1 | 8.45 | 31.0 | 31.0 |
| 2 | 8.47 | | |
| 4 | **8.54** | 122.8 | 30.7 |
| 8 | 8.61 | | |
| 16 | 8.65 | | |
| 20 | **8.67** | | 151.1 |
| 24 | 17.66 | | |
| 32 (shipped) | **17.75** | 472.6 | 118.2 |
| 40 | 17.84 | | |
| 48 | 24.86 | | |
| 60 | 25.43 | | |
| 64 | 31.93 | | |
| 128 | 53.54 | | |
| 240 | 94.27 | | |

Two readings matter. (i) The risers land exactly at multiples of the 20-core
count, and above 20 TGs the cost is **linear in TG count** (K=40 = 2.06× K=20;
K=60 = 2.93×). A machine with latency slack would flatten as more TGs arrive to
hide it; this one does not. **There is no latency slack to fill.** (ii) K=20
moves 20× the unique bytes of K=1 for +2.6 % time — bytes are close to free at
this occupancy.

---

## 7. Stage 1(a) — bytes/rows dose: memory is 42 % of the story

Artifact `stage1a-bytes-defeat.txt` (job `4a30f38e`, defeated cache,
`FERN_LADDER=32`, 11 rounds × 200 reps, interleaved
`FERN_ROWS_SWEEP=128,256,512,256`):

| rows N | mean µs | sd |
|---|---|---|
| 128 | 6.4270 | 0.0134 |
| 256 | 10.3439 | 0.0591 |
| 512 (shipped) | 18.8218 | 0.2151 |
| 256 (repeat) | 10.3863 | 0.0361 |

Least squares: **slope 0.032437 µs/row**, intercept **2.153 µs** (11.4 % of the
shipped N=512 cost; the repeat point brackets the first 256 within 0.04 µs, so
drift is not driving the fit). The pure-DRAM slope is 4096 B/row ÷ 266.3 GB/s =
**0.01538 µs/row**, so the measured slope is **2.11× the byte slope**: for every
row, the kernel pays about one byte-time and one *extra* non-byte time.
Decomposed at N=512, the byte term is 7.87 µs of 18.82 µs = **41.8 %**.

**Rule 70 disclosure.** Achieved unique bandwidth at the shipped point is
**113.3 GB/s = 42.5 % of the measured 266.3 GB/s ceiling** for this family. A
kernel at 42.5 % of DRAM peak whose per-row cost is 2.1× its byte cost is not
bandwidth-bound. The NULL paired arm in that same run was +1.220 % (t = 1.57,
n = 11); the much tighter n = 41 NULL floors in §8 supersede it.

---

## 8. Stage 1(b) — instruction dose: THE DECIDER

Method: inject `DOSE` rounds of 8 independent fp32 `fma` per main-loop iteration
at the verified anchor, seeded from live K registers (`pipe_ka[0..3]`,
`pipe_kb[0..3]`) and folded back as `pair_score0 += U(1e-30) * (…)` so the
compiler cannot eliminate it and the numeric effect is nil. Eight accumulators
give enough ILP that the dose measures **issue slots, not fma latency**.
`extra_fma_per_thread = DOSE × 8 × iterations` (iterations = 4 sliding, 8 full).
Every arm is **41 alternating rounds × 200 dispatches**, base vs candidate
paired within round. Dose 0 is a verbatim `cp`, i.e. a true A/B NULL control
through the identical code path.

| kernel | regime | dose (extra fma/thread) | d_mean µs | d_sd | t | % |
|---|---|---|---|---|---|---|
| sliding | defeated, session 1 | 0 (NULL) | −0.083 | 0.341 | −1.55 | −0.478 |
| sliding | defeated, session 1 | 4 (128) | **+1.097** | 0.195 | +35.97 | +5.846 |
| sliding | defeated, session 1 | 16 (512) | **+4.248** | 0.254 | +106.89 | +24.503 |
| sliding | defeated, session 2 | 0 (NULL) | −0.074 | 0.333 | −1.43 | −0.399 |
| sliding | defeated, session 2 | 4 | **+1.158** | 0.170 | +43.69 | +6.127 |
| sliding | defeated, session 2 | 16 | **+4.205** | 0.451 | +59.76 | +25.014 |
| sliding | **resident** `[RESIDENT — NOT A HEADLINE]`, session 3 | 0 (NULL) | −0.094 | 0.286 | −2.11 | −0.534 |
| sliding | **resident** `[RESIDENT — NOT A HEADLINE]`, session 3 | 4 | +1.299 | 0.128 | +64.83 | +7.239 |
| sliding | **resident** `[RESIDENT — NOT A HEADLINE]`, session 3 | 16 | +4.900 | 0.235 | +133.52 | +28.186 |
| full (K=24) | defeated | 0 (NULL) | +0.034 | 0.142 | +1.52 | +0.168 |
| full (K=24) | defeated | 4 (256) | **+2.189** | 0.235 | +59.69 | +10.942 |
| full (K=24) | defeated | 16 (1024) | **+9.052** | 0.384 | +150.95 | +46.633 |

**§98.5/98.9 pairing.** Resident and defeated are reported side by side; the
resident arm inflates the same effect by ~15 % (dose 16: +4.900 vs +4.227 mean
defeated) and is never used as a headline. **§98.4 column deviation:** fern's
attention probe reports `d_mean / d_sd / spread / t_paired / %` rather than the
even/odd/rounds-faster columns of the QMV harness; the pairing and alternation
discipline are the same, only the presentation differs.

**Occupancy confound excluded.** Every dosed arm still reports
`maxTotalThreadsPerThreadgroup = 1024` and tgMem 18,432 B (source grows 356→371
lines sliding, 320→335 full). The dose changed instruction count and nothing
else that the toolchain exposes.

**Derived rate — the reason this is terminal.** Sliding, defeated, two-session
mean: **0.008255 µs per fma-per-thread** at dose 16 (0.008809 at dose 4;
4.2265/1.1275 = 3.75 against an ideal 4.0, i.e. 94 % linear). Converting:
32,768 threads × 1 fma ÷ 8.255 ns = **3.969 × 10¹² fma/s**, against a hardware
maximum of 2560 FP32 lanes × 1.578 GHz = 4.04 × 10¹² fma/s. The dose is
absorbed at **97.7 % of theoretical peak issue**. There are no spare ALU issue
slots. The full kernel agrees independently: 0.00884 µs per fma-per-thread, and
its per-core critical-path prediction (2 TGs × 1024 threads × 1024 fma ÷ 128
lanes ÷ 1.578 GHz = 10.38 µs) matches the measured +9.05 µs to 87 %.

**Instrument floor.** |NULL| ≤ 0.1 µs ≈ ±0.5 % across all four NULL arms, an
order of magnitude below the dose effects.

**Base instruction budget.** 18.9 µs × 1.578 GHz ÷ (32,768 threads ÷ 2560
lanes) ≈ **2,330 issue slots per thread** in the sliding kernel — consistent
with a hand count of ~90–110 slots × 16 pipeline stages plus prologue and
epilogue. The accounting closes: **~2,330 slots/thread of issue, of which the
DRAM bytes could at best hide 42 %.**

---

## 9. Stage 1(c) — the 4× request amplification is inherent GQA broadcast

`kv_head = head0 / gqa` with `head0 = 2 * tgpig.x` means four consecutive
threadgroups compute identical KV addresses. The requested rate at the shipped
point is 444 GB/s = 167 % of DRAM peak, which is only physically possible
because those are cache hits, not DRAM traffic. The empirical price is bounded
directly by the Phase-E ladder K=1→K=4, where the request rate quadruples at
constant unique bytes: **+0.09 µs, ≈0.5 % of the call**. De-amplifying would
require collapsing 32 TGs to 8 (0.4 TG/core), which the wave staircase in §6
says is much worse. Score value of a perfect fix:
30 × 0.09 µs × 0.556 × 0.015228 ≈ **0.023 % of `cs`** — about 17× below the
0.4 % bar. This also bounds the value of the cross-threadgroup redundant K
RMSNorm+RoPE idea *on the bytes axis*; its instruction axis is a separate,
still-open question (see §13).

## 10. Stage 1(d) — partial-lane mask price closes P2 and P3 too

The assignment named P2 (widen the `if (lane < 16)` prologue RoPE section) and
P3 (widen the lane-0-only epilogue store) as the *right* levers if the kernel
turned out issue-bound. They are the right *family*, and they can now be priced
exactly instead of guessed at, because a masked instruction can be dosed as
easily as an unmasked one.

Method: the identical dose-4 payload (128 extra fma per thread) injected at the
same anchor `:1672`, once unguarded, once wrapped in `if (lane < 16)`, once in
`if (lane == 0)`. All three plus the NULL in **one session**, defeated cache,
41 alternating rounds × 200 dispatches, `maxTotalThreadsPerThreadgroup = 1024`
and tgMem 18,432 B on every arm. Artifacts `stage1b-mask*-s64-dose*.txt`.

| arm | lanes doing the work | d_mean µs | d_sd | t | % | vs unguarded |
|---|---|---|---|---|---|---|
| NULL (verbatim copy) | — | −0.039 | 0.209 | −1.19 | −0.209 | — |
| unguarded | 32/32 | +1.404 | 0.259 | +34.69 | +7.829 | 1.000 |
| `if (lane < 16)` | 16/32 | +1.558 | 0.161 | +61.92 | +8.342 | **1.110** |
| `if (lane == 0)` | 1/32 | +1.390 | 0.135 | +66.16 | +7.448 | **0.990** |

**A dose executed by one lane in thirty-two costs 99 % of the same dose executed
by all thirty-two.** The `lane < 16` form costs 11 % *more* than unguarded,
consistent with the extra mask and branch bookkeeping. This is the textbook SIMT
result, now measured on this exact kernel on this exact host: issue is
per-simdgroup, and lane masking is neither a saving nor free.

The consequence cuts both ways, and the second way is the one that matters.
Narrowing lanes buys nothing — but *widening* lanes so that each lane issues
fewer sequential instructions converts directly into time at the §8 rate. So P2
and P3 are real mechanisms. The question is only their size, and their size is
now computable.

**P2 sizing.** The RoPE section `:1571-1582` is a 4-iteration loop, each
iteration roughly 12–16 issue slots (one address add, two `float`/`bfloat`
converts in, two `angles` loads, four flops, two converts out, two stores), so
≈50–65 slots per thread, executed once per dispatch. Widening from 16 lanes × 4
pairs to 32 lanes × 2 pairs halves it: **≈25–32 slots per thread recovered**.
At §13's exchange rate that is **≈0.063 % of `cs`** if the section is charged at
full critical-path weight. It is also worth noting that the section sits inside
`if (sg < 3)`, so only 3 of the 32 simdgroups issue it at all; if the core has
other resident simdgroups to issue during the wait — and at 1.6 TG/core it has
about 51 — the throughput-weighted value collapses to **≈0.006 % of `cs`**.

**P3 sizing.** The epilogue store `if (lane == 0)` is ≈20 slots per thread (two
address computations, 8 converts, 8 stores), issued by all 32 simdgroups once per
dispatch. Spreading it over 8 lanes recovers ≈17 slots ⇒ **≈0.036 % of `cs`**.

Both are **6× to 60× below the 0.4 % bar**, and the estimates would have to be
wrong by an order of magnitude to change that. Note per §5 that no ISA listing
exists on this toolchain, so the slot counts are source-level estimates; the
conclusion is robust to a 2× error in either direction. **P2 and P3 are
therefore closed quantitatively, not merely deprioritised** — the narrow
sections are prologue/epilogue code that runs *once*, while the ≈2,330-slot
budget is dominated by the 16-stage main loop. That is where the census in
§16(1) has to look.

---

## 11. Why lever P1 was not built

Three independent reasons, any one of which is sufficient:

1. **The assignment's own Stage-1 decision rule**, verbatim: instruction dose
   *"slope materially positive ⇒ `N-ISSUE-BOUND` is terminal: stop, do NOT build
   P1."* The slope is positive at t = 36 … 151 in three sessions and both
   kernels. P1 is a *latency* lever: hoisting the prefetch above the prologue
   barrier can only pay by filling issue slots that are idle waiting on memory.
   §6 shows no latency slack (linear in TG count above 20 TGs), §7 shows DRAM at
   42.5 % of ceiling, §8 shows the ALU at 97.7 % of peak. There is nothing for a
   hoist to hide behind.
2. **#540 (merged) closed exactly this mechanism for exactly this family.**
   `CURRENT_RESEARCH_STATE.md` §5b `:2853-2881`: every prefetch-expressing
   variant of the attention kernel regressed **+5 … +7 %** at flat dose–response
   and identical occupancy, and the conclusion is quoted verbatim in §1.
   Ledger row `:5736`. #597 `:502-516` isolates the cause: *the cross-barrier
   placement of the prefetch salvo*, not the load width.
3. **Rule 82 `:804-812` (restated `:3898`) bans hoisting in the fused attention
   family.** Building P1 would have been a rule violation regardless of the
   Stage-1 outcome. This is raised for the advisor in the *Reply* section.

## 12. Threats to validity

* **Cross-machine.** This is an M4 Pro (gen 16, 20 cores) not the ranked M5 Max
  (gen 17, 40 cores). The kernels carry no `_nax` twin and no arch predicate
  (§4), so the MSL text is identical; the compiler target differs (`g16s` vs
  `g17s`) and the core count halves. The *conclusion* transfers because it is a
  ratio, not an absolute: the dose is absorbed at 97.7 % of *this host's* peak
  issue rate, and M5 Max has the same lanes-per-core and a similar clock, so a
  kernel saturating issue here cannot become latency-bound there by doubling
  cores — doubling cores doubles both issue capacity and bandwidth. What would
  *not* transfer is a threadgroup-geometry argmax, which is why no geometry
  change is proposed. Score conversions in §13 are explicitly labelled
  estimates and use the M5/M4 per-dispatch ratio.
* **Rule 86.** No conclusion here rests on a single `--local-iterate` delta. The
  one `--local-iterate` run is a correctness and provenance anchor only
  (artifact `baseline-run0.json`: `passed=true`, `max_abs_diff=0`,
  `golden_hash=b9509697…`, decode 0.0129980905 s/token, `2026-08-10T12:24:58Z`).
  Every timing claim is a paired 41-round dose curve.
* **Probe fidelity.** The probe compiles the real kernel source literals and
  reproduces the shipped grid, threads, tgMem, and `gqa`; it does not reproduce
  the surrounding decode graph, so absolute µs differ from the harness (18.8 µs
  probe vs 10.3 µs/dispatch implied by the M5 assignment figures). All claims are
  slopes and ratios within one host and one probe, which is why the M5/M4 ratio
  appears explicitly in the conversion.
* **Cache regime.** `FERN_DEFEAT_SLOTS=64` yields 16 effective rotation slots
  (the 16 MiB `dKCache` caps it), a 32.04 MiB working set and `amplif 12.7`
  per-round re-read factor, regime label `PARTIAL`. That is the defeated regime
  used for every headline; the resident twin is reported alongside and is never a
  headline.
* **A docs-only advisor base change does not invalidate this measurement.** The
  measurement depends on the byte content of
  `Sources/MLXFastModel/LagunaRuntimeModel.swift` (digest in §5) and on host
  geometry. A base update that touches only documentation, research notes, or
  the ledger leaves both untouched, so this result stands without a rerun.

## 13. What the 0.4 % bar now requires (estimates)

Using the M5/M4 per-dispatch ratio (sliding 10.317/18.6 ≈ 0.556; full
11.485/20.1 ≈ 0.571) and the decode price 0.015228 % of `cs` per µs/step:

| kernel | % of `cs` per fma-per-thread removed | instructions/thread needed for 0.4 % | as a share of its ≈budget |
|---|---|---|---|
| sliding (30 layers) | 0.002097 | **≈191** | 8.2 % of ≈2,330 slots (≈12 slots per pipeline stage) |
| full (10 layers) | 0.000769 | **≈520** | 15.7 % of ≈3,304 slots |

**Only instruction-count reduction pays on this axis.** Every byte lever and
every latency lever in the assignment's own list is dead on arrival: bytes are
41.8 % of the call and already 2.1× cheaper than the non-byte term, latency slack
is zero, and the 4× request amplification is worth 0.023 % of `cs`.

---

## 14. Reproduction

```bash
# stage 0 — reachability, geometry/occupancy, paired baseline
xcrun swiftc -O research/maple-tanjiro-r107d-arch-reach.swift -o /tmp/archreach && /tmp/archreach
xcrun swiftc -O research/nezuko_occupancy_probe.swift -o /tmp/occ && /tmp/occ
./benchmark.sh --local-iterate

# instrument
xcrun swiftc -O research/fern_r100_attn_probe.swift -o /tmp/fernattn

# stage 1a — bytes/rows dose (defeated)
FERN_LADDER=32 FERN_ROUNDS=11 FERN_REPS=200 FERN_DEFEAT_SLOTS=64 \
  FERN_ROWS_SWEEP=128,256,512,256 /tmp/fernattn Sources/MLXFastModel/LagunaRuntimeModel.swift

# stage 1b — instruction dose (sliding defeated / resident, full defeated)
bash research/maple-tanjiro-r107d-dose-suite.sh

# stage 1d — partial-lane mask price
bash research/maple-tanjiro-r107d-mask-suite.sh
```

## 15. Artifact index — `research/artifacts/maple-tanjiro-r107d/`

| file | content |
|---|---|
| `baseline-run0.json` | unmodified-tree `--local-iterate` correctness/provenance anchor |
| `stage0-arch-reach.txt` | `_nax` gate quote, `nax_available=false`, grep evidence |
| `stage0-occupancy-control.txt` | pipeline properties for both kernels, Phase-C maxK, Phase-E K ladder |
| `stage0-upstream-equivalence-base.txt` | equivalence run on the unmodified tree: 9/9 greedy tokens match, 8/8 decode steps bit-exact, prefill-only `0.125` divergence |
| `stage1a-bytes-defeat.txt` | rows dose curve, defeated |
| `stage1b-sliding-s64-dose{0,4,16}.txt` | session-1 sliding instruction dose, defeated |
| `stage1b-sliding-s64s2-dose{0,4,16}.txt` | session-2 sliding replication, defeated |
| `stage1b-sliding-s1-dose{0,4,16}.txt` | sliding resident twin `[RESIDENT — NOT A HEADLINE]` |
| `stage1b-full-s64-dose{0,4,16}.txt` | full-kernel instruction dose, defeated |
| `stage1b-mask*-s64-dose*.txt` | partial-lane mask price arms |

Instruments (research-only, not submitted): `maple-tanjiro-r107d-arch-reach.swift`,
`maple-tanjiro-r107d-dose-gen.sh`, `-dose-run.sh`, `-dose-suite.sh`,
`-mask-suite.sh`.

## 16. Suggested follow-ups (not implemented)

1. **Instruction census of the sliding main loop.** The exchange rate is now
   exact: 191 instructions/thread ≈ 0.4 % of `cs`. A hand census of the 16-stage
   pipeline body (≈90–110 slots/stage) against what the arithmetic actually
   requires is the highest-value next read, and it needs no GPU time.
2. **Cross-threadgroup redundant K RMSNorm + RoPE, on the instruction axis.**
   §9 kills it for bytes but the four TGs sharing a `kv_head` each *recompute*
   the same K normalisation and rotation. If that is ~50 instructions/thread in
   the prologue, removing it for 3 of every 4 TGs is worth ~0.08 % of `cs` —
   below bar alone, but it is the same family as (1) and may compose.
3. **Whether the epilogue's three barriers can become two.** Barriers are not
   instructions but they serialise issue; the dose instrument cannot see them.
   A barrier-count dose (inject a redundant `threadgroup_barrier`, measure) is a
   cheap, well-controlled way to price them and was out of scope here.
4. Do **not** re-open prefetch hoisting, ring depth, split-K, or wider loads on
   this family without new physics; §6–§8 plus #540 now bound all four. P2 and P3
   are likewise closed by §10 arithmetic — real mechanisms, 6× to 60× too small.

---

## § Reply to advisor

**Stage 1 answered the question the assignment asked, and the answer is the
terminal one.** The dose slope is not "materially positive", it is positive at
97.7 % of the machine's theoretical peak issue rate, replicated across two
defeated sessions, corroborated on the second kernel, with the occupancy
confound excluded by pipeline-state reads on every arm and a NULL floor an
order of magnitude smaller than the effect. So I stopped, did not build P1, and
the submitted diff is zero bytes.

**One conflict you should know about, because the brief did not mention it.**
Lever P1 as specified — hoisting the prefetch salvo above the prologue
`threadgroup_barrier` at `:1589` — is not merely unpromising, it is
**already-closed and rule-banned for this family**:

* `research/CURRENT_RESEARCH_STATE.md` §5b `:2853-2881` (#540, merged): every
  prefetch-expressing variant of the attention kernel regressed **+5 … +7 %**
  with flat dose–response and identical occupancy, concluding verbatim that
  *"'issue work earlier across a barrier' is closed for the attention family."*
  Ledger row `:5736`.
* **Rule 82 `:804-812`** (restated at `:3898`) bans hoisting in the fused
  attention family outright.
* #597 `:502-516` names the mechanism: *"the cost is the cross-barrier placement
  of the prefetch salvo, not the four loads."*

I would rather flag this than quietly obey a brief that would have required a
rule violation to satisfy, and I would suggest the P1 template be retired from
future attention assignments. Note this is a *different* lever from R107-B
(alphonse), which was a bitwise revert of depth-1 staging in the routed QMV
kernel at `LRM:7915-8027` with `threadgroupMemory = 0 B` — a different kernel
family, a different mechanism, and a different verdict path.

**Two anchor corrections for the assignment template** (§2): the sliding kernel
name line is `:1505` not `:1508`, the prologue barrier is `:1589` not `:1587`
(`:1583-1588` is the `sg == 3` V copy), and the §12 reference to `:1940` should
be `:1927` (`func lagunaSlidingFusedAttention`).

**I also priced P2 and P3 rather than leaving them as a guess** (§10), since one
extra session of the same instrument could do it. Masked instructions cost full
price — a dose executed by 1 lane in 32 costs 99 % of the same dose on all 32 —
so widening a narrow section really does convert into time. But both target
sections are *prologue/epilogue code that runs once per dispatch*, while the
≈2,330-slot budget is dominated by the 16-stage main loop: P2 is worth
≈0.063 % of `cs` at full critical-path weight (≈0.006 % throughput-weighted,
since only 3 of 32 simdgroups issue it) and P3 ≈0.036 %. Both are 6× to 60×
below bar. So the assignment's entire Stage-2 menu is now closed, P1 by rule and
by #540, P2 and P3 by arithmetic.

**What I would ask for next**, if you want the 280.8 µs attacked rather than
merely explained: assign the instruction census in §16(1). The bar is now a
number — **191 instructions per thread out of ≈2,330, i.e. ≈12 slots per
pipeline stage** — and that is a reading task, not a GPU-time task. Anything
that removes ≈12 slots from each of the 16 main-loop stages clears 0.4 % of
`cs`; nothing outside the main loop can.

**Zero receipts consumed.** No official submission was made or requested from
this experiment; frieren owns that channel.
