# PR #60 — R2: deepen the sliding fused-attention K/V load pipeline (2-deep → 4-deep)

Assignment `maple-2026-08-05g-sliding-attn-load-pipeline`, revision `r1`.
Base branch `codex/mlxfast-maple-20260804-advisor` @ `5178d452c513c61e619f4dd788185c797e065529`.
Student: maple-nezuko.

---

## 0. Verdict

**The Step 2 hard stop fired. R2 retires as a measured negative.**

The pre-registered primary gate was `sliding_attn_lone_tg_us` at K = 1 ≤ **8.77 µs**
(−5% from the 9.23 µs baseline). The 4-deep pipeline delivers **9.112 µs**, i.e.
**−1.37%**. That is a real, reproducible, bitwise-safe improvement, and it is
roughly **3.6× short of the gate**.

24-pair matched ABBA, per-pair B/A ratios, median across pairs:

| K | TG/core | base µs | cand µs | median ratio | mean ± sem | pairs < 1 |
|---|---|---|---|---|---|---|
| **1 (primary)** | 0.05 | 9.218 | **9.112** | **0.9863 (−1.37%)** | −2.24% ± 1.26% | 20/23 |
| 16 (M5 shipped analogue) | 0.80 | 9.365 | 9.316 | 0.9913 (−0.87%) | −1.09% ± 0.87% | 13/23 |
| 20 (full single wave) | 1.00 | 9.461 | 9.338 | 0.9900 (−1.00%) | **−0.79% ± 0.34%** | 18/24 |
| 32 (M4 shipped, wave 2) | 1.60 | 18.565 | 18.798 | 1.0036 (+0.36%) | +0.63% ± 0.61% | 8/24 |

The brief and the advisor both state that this outcome **"is a merge, not a
failure."** Step 2's hard stop forbids, verbatim, proceeding to Step 3 or Step 4
("Do not proceed to Step 3, do not run `--local-iterate`, do not touch the full
attention kernel"). Not running them is **compliance, not discretion**.

The `median ratio` column is the *median of per-pair ratios*, not the ratio of
medians. For completeness the ratio-of-medians values are K=1 → 0.9885
(−1.15%) and K=32 → 1.0126 (+1.26%); the two estimators agree on sign and
order of magnitude at K=1 and at K=32.

---

## 1. Base-advance and injection state (advisor comment 5196871082)

### 1.1 Base advance accepted

Advisor comment `5196871082`, marker
`pr60-base-advance-f722c2d7-inject-revert-2026-08-05T2020Z`, reported two
advances of the integration base while this experiment was in flight:

| advance | intersection with my touched paths |
|---|---|
| `5178d452 → 720c13ff` (#48) | **empty** |
| `720c13ff → f722c2d7` (advisor) | **non-empty**: `Sources/MLXFastModel/LagunaRuntimeModel.swift`, 4 lines, +20 B |

The advisor explicitly **cleared** the non-empty intersection: "accept it, and
rebase before Step 4." I **accept** it. I did **not** rebase, because Step 4 was
never reached — the Step 2 hard stop fired first. `LagunaRuntimeModel.swift` is
508,731 B at `f722c2d7` (vs 508,711 B at my base), so re-applying my +1,198 B on
top of `f722c2d7` and frieren's +13,037 B still leaves ≈520 B of cap spare.

### 1.2 The decode-injection knobs are live on my head — and cannot contaminate my numbers

My head still carries the decode-work injection that the advisor reverted on
`f722c2d7`:

```
Sources/MLXFastModel/LagunaRuntimeModel.swift:11059:  "DARKBLOOM_INJECT_DECODE_EMPTY", 100)
Sources/MLXFastModel/LagunaRuntimeModel.swift:11071:  "DARKBLOOM_INJECT_EMPTY_TG", 8)
```

Post-revert defaults are `0` and `160`. **Steps 0–3 are unaffected**, and this is
structural rather than a judgement call: every harness in this report is a
standalone host-side Metal program (`research/nezuko_occupancy_probe.swift`,
`research/nezuko_pipeline_latency.swift`). They extract the kernel source text
out of `LagunaRuntimeModel.swift`, compile it with `MTLDevice.makeLibrary`, and
dispatch it directly. They never build the Swift runtime target, so
`lagunaInjectLayerWork` (base line 10797) is never called and the two knobs are
never read. Only Step 4 (`--local-iterate`) would have needed the rebase.

### 1.3 Power-control design endorsement

The advisor endorsed the deliberate power control in the 4-deep body — dropping
one of the four accumulator slots from the `simd_sum` at base lines 1556–1557 so
the reduction tree width is unchanged — with "keep it." It is kept, unmodified.

---

## 2. Host, and the M4 → M5 projection

All measurements in this report were taken on **Apple M4 Pro, 20 GPU cores,
`applegpu_g16s`**. This is **not** the ranked M5. Per the standing campaign rule
I apply the mandated **×0.812** M4→M5 factor when projecting:

| quantity | M4 measured | M5 projected (×0.812) |
|---|---|---|
| base, K = 1 | 9.218 µs | 7.49 µs |
| candidate, K = 1 | 9.112 µs | 7.40 µs |

The *ratio* is scale-free, so the projection does not change the verdict: the
gate is on the ratio, and the ratio misses it either way.

**Harness-validity cross-check.** The assignment's stated baseline for
`sliding_attn_lone_tg_us` is **9.23 µs**. My independent 24-pair harness measures
the unmodified base at **9.218 µs** — a **0.13%** discrepancy. That agreement is
the main reason to trust the rest of the numbers: two separately written
measurement paths land on the same absolute microseconds.

**Where M4 evidence is *not* admissible.** M4 Pro reports Apple GPU generation
16 and does not select the `_nax` prefill kernels the ranked M5 uses; nothing
here is evidence about `_nax`. Threadgroup geometry also changes sign across core
counts, which is exactly the trap §7.4 below walks into and corrects.

---

## 3. Step 0(a) — reachability of the sliding fused kernel: **PASS**

Verified at the base SHA, link by link:

| link | location | fact |
|---|---|---|
| env gate | `Sources/MLXFastModel/LagunaRuntimeModel.swift:1378-1379` | `DARKBLOOM_FUSED_SLIDING_ATTN != "0"` — **default on** |
| dispatch | `Sources/MLXFastModel/LagunaRuntimeModel.swift:5763-5786` | selects `lagunaSlidingFusedAttentionKernel` |
| cache | `Sources/MLXFastModel/LagunaRuntimeModel.swift:10902` | `RotatingKVCache(maxSize: slidingWindow, keep: 0)` |
| ring gate | `Vendor/mlx-swift-lm/Libraries/MLXLMCommon/KVCache.swift:710-715` | ring path active once offset ≥ maxSize |
| window | `Sources/MLXFastModel/LagunaConfig.swift:29` | `slidingWindow = 512` |
| prompt | `Sources/MLXFastCore/Constants.swift:29` | `correctnessPromptTokens = 512` |
| oracle driver | `Tests/MLXFastTests/LagunaCorrectnessTests.swift:216-248` | 512-token prompt + 8 teacher-forced steps, tolerance 0 |
| trace | `Sources/MLXFastModel/LagunaRuntimeModel.swift:1790` | dispatch trace hook |

Because `correctnessPromptTokens == slidingWindow == 512`, the ring wrap is
exercised on the very first decode step, so the modified loop is on the scored
path from step 1.

**Documented limit:** the oracle driver runs only **8** teacher-forced decode
steps. Reachability is therefore *necessary but not sufficient* for the hidden
512-step gates.

**Path correction I owe the record.** An earlier draft placed the
upstream-equivalence oracle under `Tests/`. It is
`Sources/MLXFastModel/LagunaUpstreamEquivalence.swift` (6,501 B), which is
**inside** the submitted editable surface. Any future edit to it consumes
submission bytes.

---

## 4. What changed, and proof of localization

### 4.1 Mechanism

The base sliding kernel walks the 512-position window with a **2-deep**
software-pipelined K/V load: issue loads for slot *i+1* while the FMA chain for
slot *i* is in flight. At K = 1 the kernel occupies 0.05 threadgroups per core,
so it is entirely latency-bound: the only thing that can be won is more
outstanding loads per thread. R2 deepens the pipeline to **4-deep**.

Three constraints from §2 of the brief, all satisfied:

1. **Bit-identical FP order.** Slots accumulate in strictly ascending position
   order; the reduction tree and the `simd_sum` width are untouched.
2. **Clean fall-through.** The 4-deep loop handles `⌊n/4⌋·4` positions, then
   falls through to the *existing* 2-deep loop, then to the *existing*
   single-slot tail. No new tail code.
3. **No `widx` branching.** `widx` remains a `select`, never an `if`.

### 4.2 Diff localization proof

Four hunks, **all** inside `lagunaSlidingFusedAttentionKernel`:

| hunk | base line | content |
|---|---|---|
| 1 | @@1493 | doc comment update |
| 2 | @@1531 | new 4-deep loop (42 lines) |
| 3 | @@1589 | rewritten 2-deep loop |
| 4 | @@1721 | `T_SLOT` macro definition (39 lines) |

**85 insertions, 72 deletions.** Zero changes anywhere else in the 509 KB file.
The full (non-sliding) fused kernel at base line 1857 is **untouched**.

A trap worth recording: the identical 2-deep loop *text* also appears near base
line 2007, inside the full kernel. Whole-loop string replacement on this file is
ambiguous and must never be used.

### 4.3 Byte accounting

```
Sources/MLXFastModel/LagunaRuntimeModel.swift: 508,711 → 509,909 B   (net +1,198 B)
```

Under the assignment's net **+2,000 B** cap, with no whitespace reclamation
needed.

```
$ senpai/check-editable-budget.sh 5178d452c513c61e619f4dd788185c797e065529
editable budget OK: current=2942353/3000000 bytes headroom=57647 growth=1198/262144 files=142
```

Base for comparison: `current=2941155 headroom=58845 growth=0`.

---

## 5. Step 0(b) — base control: **PASS**

The unmodified base kernel reproduces PR #56's published geometry exactly:

- threadgroup memory **18,432 B** (plain) / **18,448 B** (real body, +1 rendezvous word)
- `maxTotalThreadsPerThreadgroup` **1024**
- `threadExecutionWidth` **32**
- **3.00** threadgroups per core

Without this control the Step 1 numbers below would not be interpretable.

---

## 6. Step 1 — occupancy: **PASS, and the predicted register cost is free**

Predicted cost of 4-deep was +12 registers, with a possible occupancy cliff.
Phase C of the probe, base vs candidate, is **identical**:

| | base | candidate |
|---|---|---|
| planes | real 4 | real 4 |
| threadgroup memory | 18,448 B | 18,448 B |
| maxK | 60 | 60 |
| TG/core | 3.00 | 3.00 |
| simdgroups/core | 96.0 | 96.0 |
| threads | 1024 | 1024 |

Logs: `research/nezuko_pr60_probe_base.log`, `research/nezuko_pr60_probe_cand.log`.

**The +12 registers cost nothing.** Deeper pipelining here is not paid for in
occupancy — which makes the small measured gain more, not less, disappointing:
there is no register/occupancy tradeoff hiding the win.

### 6.1 The wave width is the core count, not the residency limit

Base latency staircase (from the candidate probe log, µs):

| K | 1 | 2 | 4 | 8 | 16 | 20 | 24 | 32 | 40 | 48 | 60 | 64 | 240 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| t | 9.16 | 9.23 | 9.17 | 9.30 | 9.38 | 9.33 | 18.87 | 19.25 | 19.30 | 26.34 | 26.99 | 33.74 | 98.26 |

The step is between K = 20 and K = 24 — exactly where TG/core crosses 1.00.
So the effective wave width is **W = 20 = the GPU core count**, *not* the
residency limit of 60 threadgroups per core. `ceil(K/20)` fits every point in
the table. This matters for §7.4.

The probe also prints, for the record: "Shipped sliding dispatch is K=32; R1
would be K=64."

---

## 7. Step 2 — correctness and matched latency

### 7.1 Harness

`research/nezuko_pipeline_latency.swift` builds both kernel variants from source
text, runs a **matched ABBA** schedule (base, cand, cand, base) so linear drift
cancels within each pair, and reports per-pair ratios. I added an `abbaK=`
argv option so the K set can be chosen (default `[1, 32]`).

```
xcrun swiftc -O research/nezuko_pipeline_latency.swift -o /tmp/nezlat
/tmp/nezlat /tmp/base_LagunaRuntimeModel.swift Sources/MLXFastModel/LagunaRuntimeModel.swift 24 nosweep abbaK=16,20
```

(`argv[3]` is the pair count and is parsed as `Int`, so `abbaK=` must follow it.)

### 7.2 Correctness: bitwise exact

10 window indices `{0, 1, 15, 31, 32, 33, 255, 288, 480, 511}` × K ∈ {1, 32} =
**20 configurations**. In **every** configuration, **every lane** of the output
buffer is bit-identical to base: `maxUlpDiff 0`, `maxAbsDiff 0`.

This is framed deliberately as a **direct bitwise buffer comparison**, which is
the one form of evidence the brief says licenses an exactness claim. It is
**not** a gate-based claim: `max_abs_diff 0` is not a numerical tolerance bound,
and 20 configurations on one host are not the hidden 512-step gates.

### 7.3 Primary gate: **FAIL**

K = 1: 9.218 → 9.112 µs, **−1.37%** median-of-ratios. Gate was −5%. Missed by
≈3.6×. 20 of 23 usable pairs favour the candidate, so the *sign* is solid; the
*magnitude* is not close.

### 7.4 Correction: the M5 shipped configuration is a **single** wave, so the defensible M5 number is −0.87%, not 0%

I owe the advisor an explicit correction here, because the naive reading of my
own K = 32 row is wrong for M5.

The shipped sliding dispatch is K = 32. On **this M4 (20 cores)** that is
32/20 = **1.60 TG/core** — i.e. it spills into a **second** wave, which is why
K = 32 costs ≈18.6 µs, about double K = 20. On the ranked **M5 (40 cores)**
K = 32 is 32/40 = **0.80 TG/core** — a **single** wave, still latency-bound.

So the M4 configuration that is structurally analogous to M5's shipped
dispatch is **not** K = 32; it is **K = 16** (16/20 = 0.80 TG/core, the same
fractional occupancy). That row measures **−0.87%**, not the +0.36% regression
seen at M4 K = 32.

Consequences:

- The honest projected M5 effect at the shipped dispatch is a **small
  improvement (≈−0.9%)**, not neutral and not a regression.
- The M4 K = 32 regression (+0.36%) is a **second-wave** artifact and should not
  be reported as an M5 risk.
- Either way the gate is missed, so the verdict is unchanged. But "0% on M5" or
  "regression on M5" would both have been wrong claims, and I would rather
  correct my own framing than have the advisor catch it.

K = 20 (exactly 1.00 TG/core, one full wave) is the tightest measurement in the
set: **−0.79% ± 0.34% sem**, 18 of 24 pairs favouring the candidate. It is the
single number I would defend most strongly.

### 7.5 Staircase refit — partial mechanism confirmation, and a hard ceiling

**Naming-collision warning.** The harness prints `t(K) = a + b·ceil(K/W)`, where
*its* `a` is the intercept. The brief writes `t ≈ a·ceil(K/W) + b`, where *its*
`a` is the marginal per-wave cost. Everything below is in **brief convention**.

| fit (brief convention) | W | a (marginal/wave) | b (intercept) | rms | a/t(1) |
|---|---|---|---|---|---|
| base | 20 | **8.023** | **1.827** | 0.629 | 8.023/9.246 = **0.868** |
| candidate | 20 | **8.056** | **1.475** | 1.125 | 8.056/9.142 = **0.881** |
| PR #56 reference | 20 | 8.16 | 1.1 | — | 0.88 |

The #56 reference is reproduced to within 1.7% on `a`, which validates the fit
procedure.

**`b` fell (1.827 → 1.475); `a` did not (8.023 → 8.056).** That is exactly the
signature the brief predicted for a *fixed-overhead* mechanism: deeper
prefetching hides launch/fill latency but does not change the marginal cost of
an additional wave. So the mechanism **is** doing what it was designed to do —
it is just aimed at a small target.

**And that target is bounded.** `b ≈ 1.8 µs` is **19.8%** of t(1) and **9.5%** of
the K = 32 time. Since the mechanism only attacks `b`, ≈1.8 µs is a hard ceiling
on *everything* this approach can ever recover, even at infinite pipeline depth.
The pre-registered −5% gate (−0.46 µs) was inside that ceiling, so the gate was
not unreasonable a priori — the mechanism simply captured ≈0.35 µs of the
available ≈1.8 µs.

Caveat: the candidate rms **doubled** (0.629 → 1.125). Treat the refit as
corroborating *structure* (which coefficient moved), not as a precise estimate
of either coefficient.

---

## 8. Depth-8 saturation arm — R2 is closed, not deferred

To distinguish "depth 4 is too shallow" from "the mechanism saturates," I built
a research-only depth-8 variant (`research/nezuko_depth8_variant.py` →
`/tmp/cand8.swift`). This was **never** put on the branch and is **not** part of
the submitted surface.

- threadgroup memory 18,432 B, 1024 threads — **no occupancy cliff** at depth 8 either
- **bitwise identical** to base
- K = 1: median ratio 0.9947 (−0.53%), but **ratio-of-medians 9.204/9.104 = +1.10%** — the two estimators *disagree in sign*, i.e. the effect is inside the noise
- K = 32: median 1.0138 (**+1.38%**), mean **+2.20% ± 1.15%** — a clear regression

Depth 8 is **worse than depth 4** on both axes. Combined with depth 2 (base) <
depth 4 > depth 8, there is an **interior optimum at or below depth 4**.

This is the finding that converts the result from "needs a bigger version" into
**"R2 is closed."** Nobody should spend another allocation on deeper
prefetching in this kernel.

---

## 9. Score arithmetic: below the single-receipt resolvability floor

Using §4 of the brief: sliding attention ≈290 µs/step, full attention ≈100
µs/step, together ≈390 µs/step ≈ **5.8%** of score, with sensitivity
**14.862 %/ms = 0.014862 % per µs·step**. Only the sliding kernel is touched.

| basis | per-call gain | µs/step saved | score gain |
|---|---|---|---|
| K = 16 (defensible M5 analogue, −0.87%) | −0.081 µs | 2.52 | **+0.037%** |
| K = 1 (primary metric, −1.37%) | −0.126 µs | 3.97 | **+0.059%** |
| hypothetical gate pass (−5%) | −0.46 µs | 14.5 | +0.216% |

The single-receipt resolvability floor on `ns` is **0.278%**. So:

- the measured result is **4.7–7.5× below** what one ranked receipt could
  distinguish from noise;
- **even a full gate pass** (+0.216%) would have sat below that floor.

That second point is the more useful one for planning: the pre-registered gate,
had it been met, would still not have produced a receipt-resolvable score
change on its own. Any future work in this kernel needs either a much larger
mechanism or must be bundled with other wins before spending a receipt.

---

## 10. What was **not** run, and what this result does not certify

Not run, because the Step 2 hard stop forbids it verbatim:

- **Step 3a / 3b** (extended correctness sweeps)
- **Step 4** (`./benchmark.sh --local-iterate`, end-to-end paired timing)
- any change to the **full** fused attention kernel (base line 1857)
- `research/run_upstream_equivalence.sh`

Therefore, explicitly:

> **This result is not certified for promotion, and the code change should not
> be merged as a numerical change.** No end-to-end paired timing exists, the
> upstream-equivalence oracle was not run, and the branch is not rebased onto
> `f722c2d7` (it still carries the reverted decode-injection defaults, §1.2).

**Offer to the advisor:** I am happy to revert the four hunks in
`Sources/MLXFastModel/LagunaRuntimeModel.swift` and merge this PR as a
**documentation-only negative result**, keeping the research artifacts and the
depth-8 saturation finding. That preserves the closure evidence at zero risk to
the submitted surface and zero byte cost. Say the word and I will push the
revert. Alternatively, if the +1,198 B is wanted for a later bundle, it needs a
rebase onto `f722c2d7` plus Steps 3 and 4 before it is rankable.

---

## 11. Reproduction

```bash
# occupancy / geometry probe (~5 min per file)
xcrun swiftc -O research/nezuko_occupancy_probe.swift -o /tmp/nezocc
/tmp/nezocc /tmp/base_LagunaRuntimeModel.swift          # base
/tmp/nezocc Sources/MLXFastModel/LagunaRuntimeModel.swift  # candidate

# matched ABBA latency + bitwise correctness
xcrun swiftc -O research/nezuko_pipeline_latency.swift -o /tmp/nezlat
/tmp/nezlat /tmp/base_LagunaRuntimeModel.swift Sources/MLXFastModel/LagunaRuntimeModel.swift 24 nosweep
/tmp/nezlat /tmp/base_LagunaRuntimeModel.swift Sources/MLXFastModel/LagunaRuntimeModel.swift 24 nosweep abbaK=16,20

# depth-8 saturation arm (research only, never on branch)
python3 research/nezuko_depth8_variant.py            # writes /tmp/cand8.swift
/tmp/nezlat /tmp/base_LagunaRuntimeModel.swift /tmp/cand8.swift 12 nosweep

# byte budget
senpai/check-editable-budget.sh 5178d452c513c61e619f4dd788185c797e065529
```

`/tmp/base_LagunaRuntimeModel.swift` is an unmodified copy of the base file
(508,711 B).

Logs in this PR:

| file | contents |
|---|---|
| `research/nezuko_pr60_probe_base.log` | Step 0(b) base control + geometry |
| `research/nezuko_pr60_probe_cand.log` | Step 1 candidate occupancy + staircase |
| `research/nezuko_pr60_matched_latency.log` | 6 pairs + K sweep + refit |
| `research/nezuko_pr60_matched_latency_hires.log` | 24 pairs, K ∈ {1, 32} |
| `research/nezuko_pr60_singlewave.log` | 24 pairs, K ∈ {16, 20} |
| `research/nezuko_pr60_depth8_probe.log` | 12 pairs, depth-8 arm |

---

## 12. Pre-registration and an honest limitation

Decision rules — gate value, primary metric, K set, ABBA schedule, and the
hard-stop semantics — were written down **before** any candidate was measured, in
`research/nezuko-pr60-prereg.md`, committed as
**`9743b619ff87465c59980da5f2edb1de51d80a20`**.

**Limitation I should state plainly:** as a student I have no PR-comment channel
and cannot call `github_transition push_branch`, so I cannot post a
pre-registration comment with a server-side timestamp. The local commit above is
the best available timestamp, and it is only as trustworthy as the commit graph.
The advisor should treat it as a *local* pre-registration, not a
tamper-evident one.

No ranked receipt was consumed. `mlxfast submit` was **not** called — frieren
holds the ranked channel for this window.

---

## 13. Suggested follow-ups (not implemented)

1. **Attack `a`, not `b`.** The refit says the marginal per-wave cost `a` ≈ 8.0 µs
   is ≈87% of t(1) and was completely unmoved by pipelining. Any mechanism with
   receipt-resolvable upside in this kernel must reduce `a` — fewer bytes moved
   per wave, or fewer waves — not hide fill latency. Candidates: narrower K/V
   staging, or exploiting that sliding layers only need the latest 512 positions.
2. **Re-measure the M5 wave structure directly.** My −0.87% M5 projection rests
   on an *occupancy-fraction analogy* (M4 K=16 ≈ M5 K=32 at 0.80 TG/core), not on
   an M5 measurement. One M5 geometry probe would either confirm the analogy or
   invalidate §7.4. Cheap, and it de-risks every future sliding-kernel estimate.
3. **Bundle sub-floor wins.** Since even a gate-passing −5% here would fall below
   the 0.278% single-receipt floor, the programme should maintain an explicit
   "sub-floor accepted wins" queue and spend one receipt on the bundle. Otherwise
   small true wins are individually unverifiable forever.
4. **Reuse the ABBA + bitwise harness.** `research/nezuko_pipeline_latency.swift`
   is generic over two kernel source files and produced a 0.13% match to the
   official baseline. It is a cheap pre-screen for any future kernel-text change,
   and would have retired R2 in one afternoon without touching the benchmark.
