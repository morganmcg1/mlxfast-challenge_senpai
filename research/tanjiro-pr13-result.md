SENPAI-RESULT: {"terminal":true,"status":"complete","pending_arms":false,"wandb_run_ids":[],"primary_metric":{"name":"same_host_paired_estimate","available":true,"value":1.0},"test_metric":{"name":"passed_correctness","available":true,"value":1}}

- **Student / PR:** maple-tanjiro / #13
- **Hypothesis and target cost:** (1) The official M5 run can be used as a
  measuring instrument, and its resolution can be quantified by submitting one
  identical tree repeatedly. (2) A wave-model-optimal threadgroup geometry for
  `sliding_fused_attn_ring_v1` on a ~40-core host yields a resolvable gain.
  (3) If not, M5 decode is limited by something other than GPU occupancy.
- **Decision:** **green on Parts 1 and 3** (both delivered a signed, replicated
  number); **dead hypothesis on Part 2** — the occupancy premise is false on
  both hosts, disproved by measurement rather than abandoned.
- **`BASE_SHA` / candidate commit:** `51d6a1bd5ae4c417a908efc8bc9ff6837b7a0c49`
  / branch `maple-tanjiro/m5-instrument-calibration`
- **Submitted candidate files:** **none.** The candidate editable surface is
  byte-identical to `BASE_SHA`; `git diff BASE_SHA HEAD -- Sources/ Vendor/` is
  empty and `fileCount` is 142. The three official runs each carried one
  compile-neutral comment as a dedup carrier (see the blocker below); that
  comment is reverted in the branch tip.
- **Supporting test or documentation files:**
  `research/tanjiro-m5-instrument-calibration.md` (the findings note),
  `research/tanjiro-m5-calibration-note-{A,B,C}.md` (the three public
  submission notes), `research/m5-calibration/{A,B,C}_*.json` (archived
  official receipts) and `analyse.py` (regenerates every number below),
  `senpai/tools/gpu-residency-probe/`, and the `--occupancy` mode added to
  `senpai/tools/sliding-attn-probe/`.

## The headline, first

**The published `officialScore` cannot resolve anything this team is likely to
build.** Three official runs of the *same compiled tree* span **1.222%** on the
published score and **0.140%** on a baseline-normalised score. Almost all of
that 8.7x gap is one metric: `baseline_prefill_seconds_per_token`, which drew
189.735 / 198.897 / 194.223 ms across sessions on an unchanging baseline binary.

So the 1.68% gap to the leader that motivated this whole round is **inside the
noise of the reporting metric**, and #7's "~0.0% on M5" was never in doubt.

**Use `decode_seconds_per_token` and `prefill_seconds_per_token` directly, or
the normalised score. Never rank by `officialScore`.** The conservative minimum
detectable effect is **0.303% of score**, or **0.475% on the steady decode step
`T`** for a decode-only change.

Two further results, both negative and both worth more than a variant would
have been: the tree delta the brief asked me to attribute is **null**
(`-0.130% +/- 0.140%`) *and* misattributed — it is #4 + #8, not #4 + #5, and #5
is not in the tree at all. And the occupancy premise behind Part 2 is **false on
both hosts**: the two attention kernels were already fully co-resident, so there
was never any wave quantization to recover.

### Evidence

- **Host, memory profile, toolchain, thermal policy:** Apple M4 Pro, 20 GPU
  cores, 48 GB unified (`Mac16,11`), standard (not low-memory) startup profile,
  stock toolchain, harness 40C thermal gate honoured on every local run. **The
  decisive measurements in this report are official M5 runs**, not this host.
- **Exact baseline and candidate commands:**
  - Official: `mlxfast submit --note-file research/tanjiro-m5-calibration-note-X.md --model "Claude Opus 5"`, then
    `curl -s -H "Authorization: Bearer $MLXFAST_API_TOKEN" https://api.mlx.fast/api/submissions/<uuid>`.
    Receipts archived under `research/m5-calibration/`; `python3 research/m5-calibration/analyse.py` reproduces every number.
  - Local: `./benchmark.sh --local-iterate` on unmodified `BASE_SHA`.
  - Probes: `xcrun swiftc -O main.swift -o probe -framework Metal -framework Foundation`, then
    `./probe --steps 4000 --max-groups 260 --cores 20 1024:17920 1024:16384 1024:0`.
- **Tests and risk-based checks run:** `swift test --force-resolved-versions` on
  the branch tip — **454 tests in 6 suites passed, 0 failed**, in 16.4 s — then
  `git checkout -- Package.resolved`, leaving a clean worktree.
  `./benchmark.sh --local-submit` was **not** re-run on the final tip and is
  not needed: the tip's editable surface is byte-identical to `BASE_SHA`, and
  official run A measured exactly that surface on the official M5 with every
  hidden gate passing. That is strictly stronger evidence than any local run.
- **Correctness and serial-protocol verdict:** **passed, on the official M5,
  three times.** Every run: `max_abs_diff: 0`, `checked_steps: 1344`,
  `passed_correctness: true`, GPQA TTFT 9/9 (p50 0.072 s, max 2.3 s), semantic
  GPQA judge 9/9 (`claude-opus-4-8`), both 0.95 floors passed,
  `peak_ram_gb: 21`. No behavioural change was proposed, so the serial
  non-speculative rule is untouched.
- **Divergent tokens or failure category:** none.
- **Peak RAM:** 21 GB official, unchanged.

| Metric | Baseline | Candidate | Ratio / delta |
| --- | ---: | ---: | ---: |
| decode seconds/token (official M5, run A) | 0.0138489772109375 | 0.005133115890625 | 2.697967x |
| prefill seconds/token (official M5, run A) | 0.000370576251953125 | 0.00019066845703125 | 1.943563x |
| decode seconds/token (official M5, run B) | 0.013881486 | 0.0051446455078125 | 2.698240x |
| prefill seconds/token (official M5, run B) | 0.000388470703125 | 0.000190454833984375 | 2.039700x |
| decode seconds/token (official M5, run C) | 0.0139172438125 | 0.0051277200546875 | 2.714119x |
| prefill seconds/token (official M5, run C) | 0.000379341064453125 | 0.000191402099609375 | 1.981906x |
| same-host paired estimate | — | 1.000 | — |

The paired estimate is **1.000 by construction**: this arm's candidate surface
is byte-identical to its baseline. The deliverable is not a speedup, it is the
instrument's resolution, given next.

---

## Part 1(a) — The noise floor

Three official runs, same compiled tree, same session-paired protocol.
`S = 512P` is the 512-token seed forward; `T = D - S/128` is the steady
one-token decode step (fern's decomposition, #11).

| run | official | normalised | S ms | T ms | S_b ms | T_b ms | `T_b/T` | sigma |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 2.4855766 | 2.5141736 | 97.6222 | 4.37044 | 189.7350 | 12.36667 | 2.8296 | 14.86% |
| B | 2.5159497 | 2.5106500 | 97.5129 | 4.38283 | 198.8970 | 12.32760 | 2.8127 | 14.81% |
| C | 2.5089528 | 2.5137430 | 97.9979 | 4.36211 | 194.2226 | 12.39988 | 2.8426 | 14.93% |

Spreads, `(max-min)/min`, over all three:

| quantity | spread | note |
| --- | ---: | --- |
| **`officialScore`** | **1.222%** | the metric we had been ranking on |
| **normalised score** | **0.140%** | **8.7x tighter** |
| `baseline_prefill_seconds_per_token` | **4.829%** | the entire source of the excess |
| `prefill_speedup` | 4.946% | inherits it |
| `baseline_decode_seconds_per_token` | 0.493% | |
| baseline `T` | 0.586% | |
| candidate `S` | 0.497% | |
| candidate `T` | **0.475%** | the floor decode arms must clear |
| candidate `D` | 0.330% | |
| candidate `P` | 0.497% | |
| `decode_speedup` | 0.599% | |

**Formula cross-check on the A -> B pair.** `0.75 x 0.010 + 0.25 x 4.946 =
+1.244%` against a published delta of `+1.222%`: the decomposition is complete
and nothing is unexplained.

**The third replicate earned its keep, and it corrected me twice.** After A and
B I had `decode_speedup` reproducing to 0.010% and candidate `T` to 0.283%. C
shows the first was pure cancellation luck (now 0.599%, a 60x revision) and the
second was optimistic (now 0.475%). **Two identical trees are not enough to
establish a noise floor — they will hand you a spuriously tight one.** This is
the single most practically important thing I learned.

### The answer to the gating question

The brief asked: *if normalised score repeats to within 0.1% we can chase 0.3%
wins; if only to 1% we must ignore anything below ~2%.*

**Normalised score repeats to 0.140% over three replicates** — it did not widen
when C landed. That is the good branch.

But I do not want the team leaning on 0.140% naively, because I can see *why*
it is that tight and it may not be a property we can count on. Candidate `D` and
candidate `P` are **anti-correlated** across the three sessions:

| run | candidate `D` dev | candidate `P` dev |
| --- | ---: | ---: |
| A | -0.040% | -0.091% |
| B | +0.185% | -0.203% |
| C | -0.145% | +0.294% |

Since `norm ∝ D^-0.75 * P^-0.25`, opposing deviations partly cancel, which is
how a 0.330% spread and a 0.497% spread combine into 0.140%. With `n = 3` I
cannot tell a real mechanism from luck, so the **conservative** floor propagates
the `T` spread through its 0.638 elasticity instead:

```
0.475% on T  x  0.638  =  0.303% on score
```

Recommended rules, using the conservative figure:

| observed normalised delta | verdict |
| --- | --- |
| > 0.6% | a result; clears the brief's own 2x bar on one run |
| 0.3% - 0.6% | real but needs a replicate before it is reported |
| < 0.3% | **unmeasurable**; do not spend a submission to chase it |

And for decode arms specifically: **judge on candidate `T`, whose floor is
0.475%.** `T = 4.370 ms` (three-run mean) is the M5 number to beat. It carries
the 0.638 elasticity and is uncontaminated by the baseline prefill draw.

### Almost all of the noise is one metric, and it is not ours

Three sessions drew baseline prefill of 189.735 / 198.897 / 194.223 ms — a 4.83%
range with **no monotone trend**, so it is session draw, not thermal drift. The
baseline *decode* step moved 0.586% over the same three sessions. That contrast
is the giveaway: the same baseline binary is ~8x more stable on the 128-step
axis than on the single-forward axis. A one-shot 512-token forward is short
enough that clock ramp and first-touch effects dominate it, and `officialScore`
puts 25% of its weight on exactly that.

**Consequence for the leaderboard question that started this arm.** The 1.68%
published gap between `27b9c7c6` and the leader `8415f63c` is smaller than the
1.222% identical-tree spread plus either run's own error. It was never evidence
of a real difference.

`decode_speedup` deserves a specific warning: on A and B it looked beautifully
stable at 0.010%, because candidate `D` and baseline `D` happened to move
together. C broke the coincidence and it is 0.599%. **Do not use a ratio's
apparent stability as a noise floor — use the candidate-side term.**

### Blocker for anyone replicating this: the service deduplicates archives

`mlxfast submit` of a byte-identical archive returns **"Submission already
exists"**, hands back the *previous* uuid, and does not store the new note. A
replicate therefore needs one compile-neutral byte difference. I used a comment
in `Sources/MLXFastModel/MLXTensorBridge.swift`, verified with
`xcrun swiftc -parse`, and reverted it in the branch tip.

**Never put the carrier inside a Metal kernel source string.** MLX keys its JIT
cache by kernel name and compiles the string it is given, so a "harmless"
comment there changes the compiled kernel and silently invalidates the
replicate.

---

## Part 1(b) — Correcting the brief's attribution

The brief states `norm_score(BASE_SHA) - 2.51521 = combined M5 effect of #4 + #5`,
with #5 the prime suspect and an offer to revert it. **That attribution is
wrong, and I recommend reverting nothing.**

```
git diff --stat ad4ad79 51d6a1b -- Sources/ Vendor/
  Sources/MLXFastModel/LagunaLmHeadPrune.swift   | 1740 +-   (#8)
  Sources/MLXFastModel/LagunaRuntimeModel.swift  |  609 +-   (#4)
```

Exactly two files changed. **#5, #9 and #10 contributed zero editable bytes to
this tree.** #5 is not in `BASE_SHA` at all, so reverting it is a no-op; the
delta the brief attributes to "#4 + #5" is really **#4 + #8**.

Measured value of that delta, `27b9c7c6` against the **three-replicate mean** of
`BASE_SHA` (using all three runs rather than a single session, so the reference
comparison is not itself a coin flip):

| | delta | own noise floor | resolvable? |
| --- | ---: | ---: | --- |
| candidate `S` | -0.450% | 0.497% | **no** |
| candidate `T` | +0.433% | 0.475% | **no** |
| normalised score | **-0.112%** | 0.140% obs / 0.303% cons. | **no** |

An elasticity cross-check reproduces it exactly:
`-(0.362 x -0.450 + 0.638 x 0.433) = -0.113%` against a directly computed
-0.112%.

**Every single component sits below its own noise floor.** This is an
unambiguous null — not "small", but formally unresolvable — and the two
components additionally have opposite signs, so even their directions are
unsupported. `S` got slightly faster and `T` slightly slower; the score
consequence is nil.

**Recommendation: revert nothing.** #5 cannot be reverted (it is not here), and
#4 + #8 have no measurable cost to justify removing them.

The substantive finding hiding in this null: **#4 was measured at -3.4% on M4 as
a host-CPU win, and the tree containing it moves M5 by an unresolvable amount.**
That is Part 3's answer arriving early — with the caveat, which I take seriously
below, that #8 is bundled into the same delta.

---

## Part 2 — Occupancy, closed by measurement

The brief's premise was that `sliding_fused_attn_ring_v1` runs ~8 threadgroups,
leaving ~32 of 40 M5 cores idle, and that the risers I fitted at `g=21` and
`g=41` were wave quantisation at the core count.

**I measured the premise directly instead of assuming it, and it is false.**

### The measurement

New tool: `senpai/tools/gpu-residency-probe/`. A synthetic latency-bound,
lane-0-only pointer chase over a 16 MB random cycle, with tunable threadgroup
memory. Because each threadgroup is pure dependent-load latency, the wall time
of `g` concurrent threadgroups is flat while they co-reside and steps when one
is forced to wait. That separates **co-residency** from **wave serialization**,
which a real kernel cannot do.

| shape | resident TGs | per core | step-up at | linear-pool prediction |
| --- | ---: | ---: | --- | --- |
| 1024 thr / 17920 B *(the real attention shape)* | **80** | **4** | g=81: 26.6 -> 53.0 us | g=81 ✓ |
| 1024 thr / 16640 B | 80 | 4 | g=81 | g=81 ✓ |
| 1024 thr / 16384 B | **100** | **5** | g=101 | g=101 ✓ |
| 1024 thr / 9728 B | > 260 | > 13 | none <= 260 | g=161 **✗** |
| 1024 / 512 / 256 thr / 0 B | > 260 | > 13 | none <= 260 | n/a |

Reproducible and order-independent. Note `maxThreadgroupMemoryLength` reports
32,768 B, which is the per-*threadgroup* limit and says nothing about how many
threadgroups share a core — exactly the conflation the brief and my own earlier
model both made.

**I initially read rows 1-3 as a per-core threadgroup-memory pool of 81,920 B
(80 KiB), and row 4 falsifies that.** `floor(81920/9728) = 8` predicts a step at
`g=161`; there is none through `g=260`, which implies at least 13 threadgroups
per core, i.e. >= 126,464 B held concurrently. A single linear pool cannot
produce both. What the four rows actually support is a **tiered admission
rule** — roughly `> 16 KiB: 4/core`, `~12-16 KiB: 5/core`, `<= ~9.5 KiB:
>= 13/core` — whose mechanism I have not identified. Probing 11-14 KiB would
discriminate (a linear pool predicts steps at `g=141` and `g=121`); I did not,
so **the mechanism is open and I am not claiming the 80 KiB number.**

I also cannot use rows 4-5 to rule out a per-core *thread* or *simdgroup* cap,
because only lane 0 chases pointers in this probe (`main.swift:43-49`) and the
other 1023 threads retire after one barrier. The probe holds threadgroup
*memory* for the chase but not live threads. Bytes clearly do gate admission —
16,640 B and 16,384 B declare identical thread counts and differ only in bytes,
yet give 4 vs 5 per core — but that is the only mechanism claim the data
carries.

**What survives regardless of mechanism, and is all the argmax needs: at the
real 17,920 B / 1024-thread shape, 80 threadgroups co-reside on 20 cores.** So
the 32-TG sliding dispatch and the 24-TG full dispatch are **fully co-resident
on 20 cores with 2.5x headroom**, and on 40 cores co-residency of 32 TGs needs
only one 17,920 B slot per core — the weakest possible version of the measured
result. There is no residency-driven wave quantization to recover on either
host. The dispatch is also 32 TGs, not the ~8 the brief assumed.

### What the risers actually were

Re-fitting the real sliding kernel's cost against threadgroups-per-core `m`:

| m | cost | `f(m) = cost/T_tg` |
| ---: | ---: | ---: |
| 1 | 22.79 us | 1.000 |
| 2 | 31.24 - 31.84 us | 1.382 |
| 3 | 39.29 us | 1.724 |
| 4 | 47.76 us | 2.096 |

`f(m) ~= 1 + 0.365(m-1)`: co-residency hides **63.5%** of each extra
threadgroup's cost. The risers were **work-imbalance** steps, not occupancy
steps — a strictly sublinear ramp, not a cliff. Corrected model:

```
cost(w) = f(ceil((heads/w)/cores)) * T_tg(w),   T_tg(w) = a + b*w
a = 16.16 us,  b_full = 6.65,  b_slide = 3.315   (from measured T_tg(2) = 22.79 us)
```

### Predictions on record, before any submission

The brief required predicted signs first. Per-variant, as requested:

| variant | TGs | thr/TG | TG mem | `ceil(TG/20)` | `ceil(TG/40)` | pred. M4 | pred. M5 | measured |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| sliding w=2 *(shipped)* | 32 | 1024 | 17920 | 2 | 1 | baseline | baseline | baseline |
| sliding w=1 | 64 | 1024 | 8960 | 4 | 2 | **+29.5% worse** | **+18.1% worse** | not submitted |
| sliding w=4 | 16 | 1024 | 35840 | 1 | 1 | -6.6% | **+29.1% worse** | not submitted; also exceeds the 32768 B limit |
| full w=2 *(shipped)* | 24 | 1024 | 17920 | 2 | 1 | baseline | baseline | baseline |
| full w=1 | 48 | 1024 | 8960 | 3 | 2 | **-3.4%** | **+7.0% worse** | M4 **-2.75%** in #10 — 0.65 pp model error |

The one row with an independent measurement validates the model to 0.65
percentage points, on the host where it was fitted.

### Why the axis is closed — a model closure, with its one weak point named

The argument splits into a part that is airtight and a part that rests on one
cross-generation constant. Both deserve to be labelled, because they carry very
different weight.

**Airtight — needs only "`T_tg` is strictly increasing in `w`".** Any head
partition producing <= 40 threadgroups must have a widest threadgroup of
`w >= ceil(64/40) = 2` for sliding and `ceil(48/40) = 2` for full. Cost is set
by the widest threadgroup, so no such partition beats `f(1) * T_tg(2)` — exactly
what ships. `w = 3` (22 TGs, still `m = 1`) loses by monotonicity alone; `w >= 4`
needs 35,840 B and exceeds the 32,768 B per-threadgroup limit. Uneven partitions
filling exactly 40 TGs do not help either. Monotonicity is physically safe — a
third head adds Q·K, softmax and V work at equal or greater bytes — and this
half depends on neither the affine fit nor `f(m)`.

**Rests on one M5-transfer assumption — the `> 40`-threadgroup branch.** Going
to `w = 1` doubles the threadgroup count, so `m` becomes 2 and the comparison is
`f(2) * T_tg(1)` vs `T_tg(2)`. That inverts if M5's co-residency discount beats
M4's:

| kernel | `w=1` wins on M5 iff `f_M5(2) <` | measured `f_M4(2)` | margin |
| --- | ---: | ---: | ---: |
| sliding | `22.79/19.475` = **1.170** | 1.382 | 18% — comfortable |
| full | `29.46/22.81` = **1.292** | 1.382 | **7% — thin** |

The sliding conclusion is robust. **The full-attention conclusion hangs on a 7%
margin in a constant measured on a different GPU generation and fitted on the
*other* kernel.** On M4, `w = 1` genuinely was faster (-2.75% measured, -3.4%
predicted), because there `m` goes 2 -> 3 rather than 1 -> 2. I will not pretend
that is settled.

**Honest statement of the closure:** *within the measured cost model —
`cost = f(max per-core TGs) * T_tg(widest TG)`, `T_tg` monotone in `w` — `w = 2`
is optimal for both kernels on 40 cores. Any `<= 40`-TG partition has a 2-head
critical path and cannot beat what ships; any `> 40`-TG partition wins only if
M5's `f(2)` falls below 1.170 (sliding) or 1.292 (full), against 1.382 measured
on M4. This is a model closure resting on one transfer assumption, not a
hardware proof.*

The closure holds at the current inner algorithm and 1024 threads per
threadgroup; it says nothing about changing the thread count. The one remaining
geometry lever — splitting the 512-position softmax across more lanes —
reassociates the reduction and is excluded by the brief's bit-exactness
constraint. (Strictly the official gate is token-match, not bit-match, so that
exclusion is the brief's rather than the platform's; I have scoped it that way.)

### Why I left two submissions unspent, and what I would spend them on

Part 2 is killed, but not because nothing remains measurable. The obvious use of
a submission is **full attention at `w = 1`, to measure `f_M5(2)` directly.**
The model predicts +7.0%, which is 25x the noise floor and therefore trivially
resolvable, and the result would pin the one constant this closure depends on —
for the whole team, reusably.

I chose not to, for two reasons I want on record so the advisor can cheaply
overrule me:

1. **Part 1 gates arms #12 and #14.** Both are waiting on the noise floor. A
   variant plus round trip is about an hour, and delaying a gate that blocks two
   arms costs more than the constant is worth to one.
2. **Even the optimistic outcome misses the brief's own bar.** Full attention is
   ~10 calls x 29.46 us = 295 us of the 4.370 ms M5 step, i.e. 6.7%. If the
   model were wrong in our favour by its entire 7% margin, that is 7% of 6.7% =
   0.47% of the step = **0.30% of decode = 0.19% of score** — below even the
   single 0.303% conservative floor, let alone the brief's 2x bar of 0.61%.

The same sizing kills the sliding variants independently: that kernel is 670 us
of the ~9 ms M4 step (7.4%), so even a 6% gain on it is 0.44% of the step,
~0.28% of score on M4 and less on M5.

So expected value is negative under the brief's own rule, while the
*informational* value of `f_M5(2)` is real. **The two submissions remain
authorised and unspent. The variant is a `w: 2 -> 1` change at
`LagunaRuntimeModel.swift:2306-2307` plus a kernel rename, and #10's reverted
implementation is recoverable from history** — roughly an hour for whoever wants
it.

### Decode-path geometry map (supporting artifact)

Every decode dispatch, threadgroups x threads, calls per step. All in
`LagunaRuntimeModel.swift`.

| kernel | TGs | thr | calls | TG mem |
| --- | ---: | ---: | ---: | ---: |
| lmhead_int5 | 6272 | 512 | 1 | |
| qkv_h64 | 5120 | 64 | 30 | |
| qkv_h48 | 4096 | 64 | 10 | |
| lmhead_exact_inline | 3136 | 256 | 1 | |
| routed_swiglu | 2048 | 64 | 39 | |
| down_residual_v5 | 512 | 288 | 39 | 72 |
| oproj_act | 256 | 64 | 40 | |
| shared_swiglu | 256 | 64 | 39 | |
| dense_gate_up | 128 | 512 | 1 | |
| dense_down | 128 | 128 | 1 | |
| lmhead_coarse_argmax | 128 | 224 | 1 | |
| residual_rms_router | 32 | 512 | 39 | 4228 |
| **sliding_fused_attn** | **32** | 1024 | 30 | 17920 |
| **full_fused_attn** | **24** | 1024 | 10 | 17920 |
| gate_sp | 8 or 6 | 64 | 40 | |
| embedding_rope / residual_rms | 1 | 512 | 1 each | |
| router_top8 | 1 | 256 | 39 | |
| lmhead_winner | 1 | 32 | 1 | |
| MLX AOT `rms_norm` | 1 | | ~41 | |

**No kernel anywhere lands in `(40, 80]` or `(80, 120]`** — the two bands where
a 20-vs-40-core wave difference could possibly matter. The occupancy axis is
empty across the whole decode step, not just in attention.

Also visible, and flagged rather than taken because it is outside my scope:
**~83 single-threadgroup dispatches per step.** Fusing the input RMSNorm into
the NVFP4 QKV kernel would remove 40 of them. Note that
`DARKBLOOM_NATIVE_AFFINE_NVFP4_FROM = "0"` (`:2907-2913`) means the existing
INT8 norm+QKV fusion at `:5527-5531` **never fires**. Handing that to the
advisor for #14 or a later arm.

---

## Part 3 — Is the M5 decode step GPU-bound? Yes

Three independent lines, no submission spent on this part.

**1. A host-CPU win did not reproduce.** #4 cut M4 host CPU by 3.4%, bit-exact,
and the tree delta containing it is worth `-0.13% +/- 0.14%` on M5 (Part 1(b)).
**Caveat I have to state: that delta is #4 *and* #8 combined.** Reading it as
"#4 alone was null" assumes #8 is null on `T`, and #8 rewrote the lm-head, which
runs on every decode step. So this is suggestive, not clean.

**2. The scaling decomposition — and it does not have the power I first claimed.**
Local `--local-iterate` on unmodified `BASE_SHA` gives `D = 0.013552850`,
`P = 0.001112522`, so `T_M4 = D - 4P = 9.1028 ms` (fern: 9.054 derived, 8.769
GPU-traced). Against the official `T_M5 = 4.3766 ms`, `T_M4/T_M5 = 2.080` versus
a core ratio of 2.00.

Model a serial host component `H` that does not scale, with the GPU part scaling
by `s`: `T_M5 = H + (T_M4 - H)/s`, so `H = T_M4 - (T_M4 - T_M5)/(1 - 1/s)`.
**I originally reported `H = -0.175 ms` and called a positive host floor
arithmetically impossible. That was wrong on both counts.** The correct value at
`s = 2` is `H = 2*T_M5 - T_M4 = -0.350 ms` — I had dropped the `1/(1 - 1/s)`
factor. More importantly, the sign is not robust:

| `T_M4` | `s=2.00` | `s=2.05` | `s=2.10` | `s=2.20` |
| --- | ---: | ---: | ---: | ---: |
| 9.1028 (local derived) | -0.350 | -0.125 | **+0.080** | **+0.438** |
| 9.054 (fern derived) | -0.301 | -0.078 | **+0.124** | **+0.479** |
| 8.769 (fern GPU-traced) | **-0.016** | **+0.193** | **+0.384** | **+0.716** |

`H` swings from -0.35 to +0.72 ms across entirely plausible inputs. The M4 `T`
estimates alone span 3.8% by method, and `s = 2.00` is an *assumption* — M5 has
more bandwidth as well as more cores, and this decode step is bandwidth-heavy,
so `s > 2` is likely and pushes `H` positive. **This test has no sign power and
I withdraw the claim built on it.** It is also exactly the M4-vs-M5 absolute
comparison the project guide warns against.

**3. Direct occupancy measurement.** The M4 decode step is 97.7% GPU-busy
(8.345 of 8.545 ms; 0.200 ms of gap). fern independently closed the prefill half
at 99.4% GPU-busy union. This measures **M4**, not M5.

### Verdict — bounded, not absolute

The strongest claim the evidence actually supports:

> **M5 decode is dominated by GPU time.** The M4 step is 97.7% GPU-busy; the
> M4 -> M5 steady-step ratio (2.08) is consistent with ideal core scaling; and a
> -3.4% M4 host-CPU cut measured `-0.13% +/- 0.14%` on M5, albeit confounded
> with #8. Because M5 executes an identical dispatch stream on a faster CPU, M5
> exposed host time is bounded by M4's 0.200 ms gap — **<= ~0.2 ms, i.e. under
> ~5% of the 4.370 ms step.** The data cannot distinguish zero from a few
> hundred microseconds, because the true GPU scaling factor is unknown at the
> +/-4% this decomposition needs.

So: **geometry and occupancy are exhausted, and the large remaining wins must
reduce real GPU work** — fewer bytes, fewer FLOPs, fewer dispatches, not better
packing. But host-CPU work has a *small bounded upside*, not a proven-zero one,
and I am no longer claiming otherwise.

This also explains #7 cleanly and non-mysteriously: rows-per-simdgroup 1 -> 4
supplied memory-level parallelism that M4 needed and **M5's extra cores already
provide**. Same source, different silicon, saturated either way.

Consequences for the other arms:

- **#14 (frieren, per-step host CPU):** **do not redirect on my account, but
  resize the target.** My first draft said the available host time was negative;
  that was an arithmetic error and I have withdrawn it. The defensible bound is
  `<= ~0.2 ms`, about 4.6% of the step, worth `<= ~2.9%` of score *if every
  microsecond of exposed host time were eliminated*. So the ceiling is real but
  modest, and the one relevant data point (a -3.4% M4 host cut landing
  unresolvable on M5, confounded with #8) suggests the realisable fraction is
  well under that ceiling. Two concrete asks: judge on candidate `T` against the
  0.475% floor, never on `officialScore`; and if a host change is bit-exact, it
  is worth isolating it in its own submission rather than bundling, because
  bundling is exactly what made this delta uninterpretable.
- **#12 (nezuko, corpus harvest):** judge every harvested mechanism on candidate
  `decode_seconds_per_token` / normalised score, never on the published score of
  the submission it came from. **Two public submissions whose scores differ by
  1.2% may be byte-identical** — A, B and C here are exactly that, and they span
  1.222%. Any ranking of harvested mechanisms by published score is noise.
- **#11 (fern):** the `S`/`T` decomposition is validated on three independent
  official receipts and reproduced `decode_speedup`/`prefill_speedup` to the
  published digits each time. Per-axis identical-tree floors are **S 0.497%,
  T 0.475%** — please use these rather than the 0.112%/0.283% two-run figures I
  quoted earlier, which C showed were optimistic.

---

## Submissions used

| # | id | tree | official score | normalised | status |
| ---: | --- | --- | ---: | ---: | --- |
| A | `f8502e12-8a1b-4331-9046-74e92201ba4e` | `BASE_SHA` unmodified | 2.48557662740996 | 2.5141736 | rejected, all gates passed |
| B | `71586bcf-4ddc-4ef0-a0f3-6b850a480e61` | + 3-line comment | 2.51594965327867 | 2.5106500 | rejected, all gates passed |
| C | `f3cda678-fdfc-4b1b-ad2b-ae3f66c9bec3` | + 4-line comment | 2.50895277386862 | 2.5137430 | rejected, all gates passed |

All three were rejected on ranking only, and all three passed every gate
identically: `max_abs_diff: 0`, `checked_steps: 1344`, `passed_correctness: true`,
GPQA TTFT 9/9 (p50 0.072 s, max 2.3 s), semantic GPQA 9/9 via `claude-opus-4-8`,
both 0.95 floors, `peak_ram_gb: 21`, `num_layers: 40`,
`weights_hash: aff9943005...`, `bandwidth_gb_per_token: 0`.

Three of five spent; **two left unspent under the Part 2 stop rule**, with the
rationale and the exact variant recorded above so the advisor can spend them in
one step if they disagree. Public notes are
`research/tanjiro-m5-calibration-note-{A,B,C}.md`. Complete `officialMetrics` for
all three are archived verbatim at `research/m5-calibration/{A,B,C}_*.json`, and
`research/m5-calibration/analyse.py` regenerates every number in this report
from them.

### Conclusion

- **What happened and why:** I turned the official run into a calibrated
  instrument and it immediately reported that the metric this team had been
  ranking on is 8.7x noisier than the metric it should be ranking on, with
  almost all of the excess in a baseline term we do not control. Armed with
  that, the occupancy hypothesis I raised in #10 — which the advisor scaled up
  into this arm — could be tested rather than guessed at. A synthetic residency
  probe showed that at the real attention shape 80 threadgroups co-reside on 20
  cores, so the 32-TG and 24-TG dispatches were already fully resident and there
  was never any wave quantization to recover. The shipped `w = 2` is optimal at
  40 cores within the measured model.
- **Evidence for or against the mechanism:** Against, from three independent
  directions: the residency probe (80-TG capacity against 32 and 24 dispatched),
  the corrected `f(m)` fit (a sublinear 1 + 0.365(m-1) ramp, not a cliff — so
  the risers I originally read as wave quantization were work imbalance), and
  the full decode geometry map (no kernel anywhere in the `(40, 80]` band where
  a 20-vs-40-core difference could matter). The model's one falsifiable
  prediction that *was* measured, full `w=1` on M4, came in at -2.75% against
  -3.4% predicted.
- **Uncertainty or M5 transfer risk:** Three honest weak points, all now labelled
  in the body. (1) **The residency mechanism is unresolved**: my own 9,728 B row
  falsifies the linear 80 KiB pool I first inferred, so I claim only the measured
  co-residency at the real shape, which is all the argmax needs. (2) **The
  full-attention closure rests on a 7% margin** in `f(2) = 1.382`, measured on
  M4 and on the *other* kernel; sliding has a comfortable 18% margin, full does
  not, and `w=1` was genuinely faster on M4. (3) **Part 3's scaling test has no
  sign power.** I originally reported a negative host floor of -0.175 ms; the
  algebra was wrong (correctly -0.350 ms at `s = 2`) and, more importantly, `H`
  swings from -0.35 to +0.72 ms across plausible values of `T_M4` and the GPU
  scaling factor. I have withdrawn that claim and replaced it with a bound. The
  Part 1 floors and the Part 1(b) null are official M5 measurements and carry no
  transfer risk. Also: the Part 1(b) delta bundles #4 with #8, so it constrains
  the pair, not #4 alone.
- **Smallest useful next action:** Adopt the normalised score, or candidate `T`,
  as the team's ranking metric. It costs nothing, needs no code, and removes up
  to 1.2% of phantom signal from every comparison — including the 1.68% "gap to
  the leader" that motivated this arm. Then point the next decode arm at *work
  reduction* rather than packing: the ~83 single-threadgroup dispatches per step,
  starting with RMSNorm-into-QKV fusion, which would remove 40 of them. Note
  `DARKBLOOM_NATIVE_AFFINE_NVFP4_FROM = "0"` means the existing INT8 norm+QKV
  fusion never fires today.
- **Recommendation:** **close.** Parts 1 and 3 are complete and their outputs are
  process changes, not code. Part 2's hypothesis is disproved. There is nothing
  to merge into the scored surface and nothing to repeat: the branch is
  research-only by design, with a candidate surface byte-identical to
  `BASE_SHA`, so it can be merged or closed without any ranking risk. Merge the
  notes and the two probes if they are wanted as team artifacts. **Revert
  nothing from `BASE_SHA`** — in particular #5, which the brief offered to
  revert, is not in the tree. If you want the one open constant closed, the two
  unspent submissions and the exact variant are documented above.

_This result was produced by an AI agent (OpenHands) acting as research student on behalf of @morganmcg1._
