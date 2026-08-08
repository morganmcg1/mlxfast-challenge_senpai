# PR #441 — Q12: active-64 block tournament on the decode router top-8

**Verdict: KILL.** The port is bit-exact everywhere I can measure and it does
remove 9 of 12 charged threadgroup barriers, but the barriers were never the
cost. Pooled two-order in-situ ABBA over 48 runs × 248 kept steps puts the
tournament at **+4.2 µs/step (95 % CI [−4.6, +13.0])**, i.e. *slower* by a
hair. The bar is **−80 µs/step M4-equivalent**. Even the most favourable end of
the interval is a −4.6 µs/step gain — **17× below the bar**, and 0.118 µs off a
4.70 µs/call kernel.

The mechanism did not fail to be implemented; it failed to be worth anything.
The reason is a structural fact about the algorithm that the assignment brief
(and the frontier's own note) glosses over, documented in
[§6](#6-barrier-accounting-and-why-the-mechanism-cannot-pay).

| Assignment | `maple-2026-08-08a-decode-router-tournament` r1 |
|---|---|
| Branch / PR | `maple-nezuko/decode-router-tournament` / #441 |
| `BASE_SHA` | `730e9c2be89a4ed8cf860e52f930f7ff222d4c95` |
| Submitted surface | `Sources/MLXFastModel/LagunaRuntimeModel.swift` only |
| Guard | `DARKBLOOM_DECODE_ROUTER_TOURNAMENT`, default **OFF** (rule 21) |
| Host | M4 Pro, 20-core GPU, Apple GPU gen 16, ~8.20 ms/decode step |
| Gates | 64-step tripwire **green on all 3 arms**, one identical hash; oracle **red on prefill only**, but bit-identical to the unchanged `BASE_SHA` ([§7.1](#71-upstream-equivalence--the-oracle-fails-and-the-failure-is-the-host)) |

---

## 1. Stage 0 — reachability and price (evidence contract item 1)

The brief's attribution caveat was the first thing to resolve: with
`DARKBLOOM_ROUTER_PRECOMPUTED_KEYS` on, the routed QMV runs its own second
top-8 extraction, so it is not self-evident that the kernel I edit is on the
critical path 39×/step. **It is.**

From the existing M4 census `research/nezuko-a2-roofline.txt:36-37`:

```
decode_router_top8_ordinal_table_norm  39 x 4.70 us = 185.7 us/step;
    bytes 0.001 MB -> floor 0.1 us/step
```

- **39 dispatches/step**, matching the 39 sparse MoE layers on line 36. The
  precomputed-keys top-8 in the routed QMV is an *additional* consumer, not a
  replacement — `gate(...)` still dispatches this kernel to produce `weights`.
- The census kernel name (`_ordinal_table_norm`) pins the live configuration:
  **`normalizing = true`, `scoreTable = true`**. That is the only arm worth
  optimising, and it is the one I ported.
- **4.70 µs/call, of which only ~1.7–2.7 µs is sortable.** The comparable
  trivial kernel `rmsbfloat16` costs 3.00 µs/dispatch in the same census, so
  ~2–3 µs of the 4.70 µs is fixed launch overhead that no amount of algorithmic
  work inside the kernel can touch. The roofline floor is 0.1 µs/step — this
  kernel moves 0.001 MB and is 100 % latency-bound, never bandwidth-bound.

**Guard chain down to a default (rule 1).** The scored call site is
`LagunaRuntimeMoEGate.callAsFunction`, cast-sink branch, gated on
`lagunaDecodeRouterTop8Enabled && lagunaDecodeRouterCastSinkEnabled &&
projectedLogits.dtype == .bfloat16 && size == 256 && topK == 8`, all of whose
`DARKBLOOM_*` inputs default **on**. Verified live, not just read: the
`lagunaTrace` string `decode router top8 (cast sink + norm sink)` appears in
every arm of the Stage 3 smoke run.

**Price if the mechanism were free.** ~1.7–2.7 µs/call × 39 = 66–105 µs/step,
straddling the ~80 µs bar. So the idea was correctly *sized* — it just needed
essentially all of the sortable time, which no barrier change can deliver.

## 2. Stage 1 — the arm

Three additions, all inside my assigned region (~8688–9270), no reflow
elsewhere:

| Symbol | Lines | Role |
|---|---|---|
| `lagunaDecodeRouterTournamentOrdinalKernelSource(normalizing:scoreTable:)` | 8994–9119 | decode-indexed port of the prefill ordinal tournament |
| `lagunaDecodeRouterTournamentKernels` | 9125–9152 | 8 kernels, indexed `(inert ? 4 : 0) \| (scoreTable ? 2 : 0) \| (normalizing ? 1 : 0)` |
| `lagunaDecodeRouterTournamentArm` | 9157–9158 | the guard |
| `lagunaDecodeRouterTop8TournamentOrdinalForTesting(...)` | 9160+ | encoder, `grid (256,1,1)`, `threadGroup (256,1,1)` |
| dispatcher branch | 9248–9256 | first branch inside `if lagunaDecodeRouterOrdinalEnabled` |

The port is exactly what the brief predicted: take the prefill ordinal
tournament, drop the `row *` offsets, keep `grid (256,1,1)`, and reuse
`lagunaDecodeRouterOrdinalHeader` **unchanged**. No new comparator. Epilogue and
winner-score reads use `my_index2` / `my_score2` from the Phase-2 registers.

**Rule 33 compliance.** Each of the 8 kernels carries an arm-specific name
suffix — `laguna_decode_router_top8_{tournament|inert}_ordinal[_table][_norm]_v1`
— so MLX's static-name pipeline cache cannot alias two arms.

**Default-OFF is genuinely free**, not just semantically inert.
`lagunaDecodeRouterTournamentKernels` is a file-scope `private let` (9125), so
Swift initialises it lazily on first access; its only reader is line 9169 inside
the encoder, which is reachable only when the guard is not `"0"`. With the guard
at its default the 8 kernel descriptors are never constructed, and the added
cost on the shipped path is one comparison against a cached `String`. The
`lagunaTrace` at 9249 takes an `@autoclosure` gated by `DARKBLOOM_TRACE_FUSION`,
so its string interpolation is not evaluated when tracing is off.

## 3. Stage 2 — bit-exactness (evidence contract item 2)

Instrument: `research/nezuko_q12_router_tournament_bitwise.swift`, driven by
`research/nezuko_q12_router_tournament_check.sh`. Standalone Swift + Metal,
**outside `Sources/`** (rule 11). It carries byte-identical copies of both MSL
generators and the shared header, guarded by an `awk` drift check that fails the
run if the copies diverge from the Swift source — so this harness cannot silently
rot into testing a stale kernel.

```
drift guard OK: lagunaDecodeRouterOrdinalKernelSource (93 lines identical)
drift guard OK: lagunaDecodeRouterTournamentOrdinalKernelSource (126 lines identical)
drift guard OK: lagunaDecodeRouterOrdinalHeader (22 lines identical)
Metal device: Apple M4 Pro; 10 kernels, 5 row classes
```

`MTLCompileOptions.fastMathEnabled = false` to match MLX's own setting
(`device.cpp:631`); BF16 inputs are produced by host round-to-nearest-even.

**Result: every arm × class × precision is bit-identical.** 40 rows of output
(2 precisions × 5 classes × 4 arms), all reporting
`mismatch_words=0 mismatch_rows=0 max_abs_diff=0.0`.

| Axis | Coverage |
|---|---|
| Precision | BF16, FP32 |
| Arms | `plain_recompute`, `plain_table`, `norm_recompute`, `norm_table` (i.e. `normalizing` × `scoreTable`) |
| `random_smooth` | 4096 rows |
| `all_equal` | 4 rows |
| `heavy_ties` | 5 rows (exact score ties, distinct indices) |
| `nan_inf_zero` | 5 rows (NaN, ±inf, signed zero) |
| `block_skew` | 10 rows (mass concentrated in one 32-block) |

`candidate total mismatch_words: 0, mismatch_rows: 0` → `RESULT: SUPPORTED`.

Both index and score outputs match bit-for-bit against **both** oracles: the
existing full-256 decode ordinal network and the accepted prefill tournament.

**Why exactness is structural, not lucky.** `laguna_router_key_ordinal`
canonicalises NaN → `0xFFFFFFFF` and ±0 → `0x80000000` before the monotone IEEE
bit flip, and `laguna_router_ordinal_before` breaks equal keys on the index.
Because the index is part of the key, the order is **total** — no ties exist —
which is precisely the hypothesis the block theorem needs. `lane >> 5` gives 8
blocks of 32, each publishing 8 winners, so all 64 candidate slots are written;
at the final `seq = 32` the Phase-1 direction is
`block_ascending = (block & 1) == 0`.

## 4. Stage 3 — fault injection (evidence contract item 3, rule 16)

| Arm | Kind | Verdict | Live where |
|---|---|---|---|
| `candidate` (4 configs) | on-control | **0 mismatches** — required | n/a |
| `tourn_fault_drop8` | keep only local top-**7** per block (breaks the theorem) | **DETECTED**, 18 mismatch words | `block_skew` only |
| `tourn_fault_flatdir` | corrupt the alternating Batcher direction | **DETECTED**, 123 315 mismatch words | everywhere except `all_equal` |

**Non-detections, reported explicitly (#301's lesson).** `drop8` is **not**
detected on `random_smooth`, `all_equal`, `heavy_ties`, or `nan_inf_zero`. This
is a genuine semantic no-op there, not a blind spot in the harness, and I
verified the mechanism rather than assuming it (#308's lesson): the fault forces
block 7's rank-7 ordinal to `0xFFFFFFFF`, which under this comparator is the
*worst* possible key. On a smooth random row, block 7's 8th-best element is
essentially never in the global top-8, so discarding it changes nothing
observable. Only `block_skew` — which deliberately piles mass into one block, so
that block legitimately owns 8 of the global 8 — makes the fault load-bearing,
and there it fires on 9 words per precision.

That is the whole reason `block_skew` exists in the class list, and it is why a
"the fault wasn't detected, so we're fine" reading of a random-only suite would
have been wrong here.

`flatdir` perturbs a *value*, not a bijection over positions (#309's lesson: an
index permutation is bit-exact by construction and cannot falsify anything).

**Rule 35.** `LagunaUpstreamEquivalence.swift` never reaches
`prepareFusedRuntimeWeights()`, so the oracle is structurally blind to this
whole family. These injected faults, not the oracle, are what make the
exactness claim falsifiable.

## 5. Stage 4 — matched in-situ timing (evidence contract item 4)

Design: `research/nezuko_q12_stage4.sh` → `research/nezuko_q12_abba.sh`.
Three arms — `off` (incumbent), `on` (tournament), `inert` (rule-3 control:
incumbent network compiled under a distinct kernel name with a no-op MSL
suffix, so content-hash dedupe cannot silently reuse the `off` pipeline).
Two **reversed `ORDER` directions** so arm is never fixed to a slot position
(rule 36):

- `orderA` = `off on inert inert on off`
- `orderB` = `inert on off off on inert`

4 blocks × 6 slots per order + 1 discarded warm-up each = 50 runs, 48 usable.
256 decode steps/run, first 8 dropped, per-run estimator = upper-5 %-trimmed
mean. Job `4f1f835a-2544-4c5c-8342-d517168acb48`, exit 0, 2111 s.
**Every one of the 50 runs reported `0 divergences` on teacher-forced greedy
tokens.**

### Pooled, both orders (n = 16 per arm)

| arm | mean µs/step | sd of run means | within-run sd |
|---|---|---|---|
| `off` | 8205.1 | 6.4 | 40.9 |
| `on` | 8209.3 | 10.6 | 40.8 |
| `inert` | 8205.8 | 17.4 | 45.0 |

Two-way fixed effects (arm + block), residual sd **12.3 µs over 38 df**:

| contrast | µs/step | se | 95 % CI | µs/call | % score | meaning |
|---|---|---|---|---|---|---|
| **`on-off`** | **+4.2** | 4.4 | **[−4.6, +13.0]** | +0.108 | −0.064 % | HEADLINE |
| `inert-off` | +0.7 | 4.4 | [−8.1, +9.5] | +0.018 | −0.011 % | rule-3 null |
| `on-inert` | +3.5 | 4.4 | [−5.3, +12.3] | +0.090 | −0.054 % | net of that null |

Positive = tournament **slower**. Conversion uses 39 dispatches/step and the
campaign calibration **decode 0.015280 %/µs**.

### Per-order split (rule 36 check)

| order | `on-off` µs/step | 95 % CI | residual sd | df |
|---|---|---|---|---|
| `orderA` | +6.7 | [−3.2, +16.5] | 9.4 | 18 |
| `orderB` | +1.7 | [−14.0, +17.5] | 15.1 | 18 |

Both directions agree in sign and both are null. Arm is not confounded with
slot kind. `orderA`'s slightly larger point estimate is one block-4 `on` outlier
(8226.8 vs 8207.5 for `off` in the same block); `orderB` is the cleaner half and
sits at +1.7.

### Power

The pooled FE half-width is **±8.8 µs/step ≈ ±0.23 µs/call**. To clear the bar
the mechanism needed **−80 µs/step ≈ −2.05 µs/call**, so the design resolves the
target effect with ~9× margin. The `inert-off` null landing at +0.7 ± 8.8
confirms the instrument is not manufacturing an arm effect out of pipeline
identity. **This is a resolved negative, not UNDERPOWERED.**

## 6. Barrier accounting, and why the mechanism cannot pay

*(Evidence contract item 5. This section is the actual finding.)*

The barrier delta is real and I verified it by counting stages in both kernels:

| | stages | `stride >= 32` stages | charged TG barriers |
|---|---|---|---|
| incumbent full-256 network | 36 | 6 | **12** (2 per stage) |
| tournament (15 + 21) | 36 | 1 | **3** (1 repack + 2) |

So the port does what it claims: **12 → 3** intra-threadgroup barriers, and
~20 KB/dispatch less threadgroup round-trip traffic (5 fewer cross-SIMD
exchange stages × ~4 KB), replaced by register-only `simd_shuffle_xor`. Extra
threadgroup memory is 512 B (`candidate_ordinals` + `candidate_indices`),
3584 B total, irrelevant at one threadgroup.

**The correction the brief is missing.** Phase 2 indexes
`candidate_ordinals[lane & 63]`. All 256 lanes therefore redundantly sort *the
same* 64 candidates as four replicated groups of 64 (`partner = lane ^ 32`
never leaves a 64-lane group). Instruction-issue work is consequently
**unchanged**: 36 stages × 8 SIMD-groups = **288 SIMD-group-stages in both
kernels**. The tournament is not doing less arithmetic — it is doing the *same*
arithmetic with fewer fences. The only lever is the 9 removed barriers.

That lever is far too small, and it was possible to bound it before measuring.
A delegated frontier literature review found **no public Apple barrier-latency
measurement exists** (absent from philipturner/metal-benchmarks, Dougall
Johnson's G13 ISA notes, and the Mesa AGX compiler), so the best available
anchor is inference: ~10–60 cycles ≈ **7–45 ns per `threadgroup_barrier`** for
one 8-SIMD-group threadgroup. Budgeting the ~1.7–2.7 µs sortable body as
~1.0–1.5 µs instruction issue (36 × 8 stages, `ICMPSEL32` at 4.74 cy, ~2 IPC),
~0.15–0.3 µs prologue device load, and **~0.1–0.5 µs for all 12 barriers**,
removing 9 of them predicts **~0.06–0.4 µs/dispatch = 2.3–15.6 µs/step**. The
same review put P(≥1.0 µs/dispatch gain) at ~10 %.

**Measured [−4.6, +13.0] µs/step brackets that prediction's low end and
excludes its high end.** Barrier removal on this kernel is worth single-digit
µs/step at best — the honest reading is that the barriers were already nearly
free, consistent with the related finding that `simdgroup_barrier` compiles to
*zero instructions* in the Mesa AGX backend. Barrier accounting therefore
**does** explain the observed Δ: there was almost nothing there to remove.

Two further reasons the result is not surprising in hindsight:
- ~2–3 µs of the 4.70 µs/call is fixed launch overhead (`rmsbfloat16` = 3.00 µs
  for a trivial kernel), so at most ~40–57 % of the kernel was ever addressable.
- A single-threadgroup dispatch has no co-resident work to hide barrier latency
  behind, which *maximises* the exposure of barriers — this was the best case
  for the hypothesis, and it still did not pay.

**Rule 19 note.** I did not measure a barrier refund with the real kernel
removed. The bound above is reasoned, not measured, and I flag it as such; the
measured quantity is the end-to-end arm contrast, which is what the verdict
rests on.

## 7. Correctness gates (evidence contract item 6)

- **In-situ reachability + token smoke** (job `b5f0d940`, 32 steps × 3 arms):
  `off` shows `prefill router tournament` and `decode router top8 (cast sink +
  norm sink)` and **no** tournament line; `on` adds `decode router top8
  tournament arm=1`; `inert` adds `arm=inert`. All three arms: **0
  teacher-forced greedy divergences**.
- **Public 64-step drift tripwire**, run per arm via
  `research/nezuko_q12_gates.sh` (job `0193a10f-5224-4a95-b5ee-5797c71df9f6`).
  I gate all three arms, not just the shipped default, so the guard-ON candidate
  and the rule-3 control are both covered:

  | arm | `DARKBLOOM_DECODE_ROUTER_TOURNAMENT` | rc | `passed` | `checked_steps` | `golden_hash` |
  |---|---|---|---|---|---|
  | `off` | `0` | 0 | **True** | 64 | `b9509697c08a2cf3` |
  | `on` | `1` | 0 | **True** | 64 | `b9509697c08a2cf3` |
  | `inert` | `inert` | 0 | **True** | 64 | `b9509697c08a2cf3` |

  Identical golden hash across all three arms, no `first_failing_case`/`_step`,
  empty `error`. Golden
  `correctness_prompts/public_longcopy_gate_english_512_256.json`, which also
  exercises a 512-token prefill.
- **`research/run_upstream_equivalence.sh`** with an explicit non-zero
  selected-test assertion (a mismatched Swift Testing filter exits 0 after
  selecting nothing, so a bare pass is not evidence). Result in §7.1.

### 7.1 Upstream equivalence — the oracle fails, and the failure is the host

Reporting this exactly as measured, because the headline is a **red** gate.

The oracle exits non-zero on the candidate (job
`0193a10f-5224-4a95-b5ee-5797c71df9f6`, artifacts `/tmp/nezq12/gates/`):

```
EQUIVALENCE_EXACT_STEPS=8
EQUIVALENCE_EXIT=1
EQUIVALENCE_SELECTED_TESTS_PASSED=0
```

The failure is confined to one axis. Per-step, candidate:

| step | max abs logit err | mean abs logit err | runtime tok | upstream tok |
|---|---|---|---|---|
| `prefill` | **0.125** | 0.011933609 | 5991 | 5991 |
| `decode-0` … `decode-7` | **0** (all 8) | **0** (all 8) | 509/902/5991… | identical |

So all eight decode steps — the axis this experiment touches, carrying 75 % of
the score weight — are **bit-exact**, and even the prefill step selects the same
greedy token (`runtimeToken == upstreamToken == 5991`); the 0.125 is a logit
difference below the argmax margin.

`research/run_upstream_equivalence.sh` prescribes the disambiguation directly:
*"on a non-M5 host, compare the unchanged BASE_SHA before attributing drift."*
`research/nezuko_q12_equiv_base_control.sh` does that. The submission surface is
exactly one file, so the control restores that file to its `BASE_SHA` content
(blob `9c484729`, 475,647 B), reruns the oracle, and undoes the revert under an
EXIT trap that verifies the restored blob against `HEAD`:

```
=== base blob 9c484729b30e2d2769a3a40db16857851483d83e (475647 bytes)
 Sources/MLXFastModel/LagunaRuntimeModel.swift | 210 --------------------------
base    "label" : "prefill"
base    "maximumAbsoluteLogitError" : 0.125
base    "meanAbsoluteLogitError" : 0.011933609
base    "runtimeToken" : 5991 / "upstreamToken" : 5991
base    decode-0 … decode-7: maximumAbsoluteLogitError 0, meanAbsoluteLogitError 0
base EQUIVALENCE_EXACT_STEPS=8
BASE_EQUIVALENCE_EXIT=1
restore: Sources/MLXFastModel/LagunaRuntimeModel.swift matches HEAD (d548a4b1)
```

The rebuild is real, not a stale binary serving a vacuous control: the log shows
`[7/10] Compiling MLXFastModel LagunaRuntimeModel.swift` and the test bundle was
relinked at 15:54:17 inside the job's 15:53:58–15:54:26 window.

**The candidate-minus-base oracle delta is exactly zero on all nine steps**,
identical to the last significant digit. The zero-tolerance failure is therefore
a property of this non-M5 M4 Pro host, which does not select the `_nax` prefill
kernels the ranked M5 uses. It is also not new: the identical
`0.125 / 0.011933609 / 5991` triple is recorded in
`research/nezuko_equiv_control.log` from 2026-08-05, on an unrelated PR, across
three different `MLX_MAX_MB_PER_BUFFER` caps. It is a durable host signature.

**What I am and am not claiming.** I am *not* claiming an equivalence pass —
`EQUIVALENCE_SELECTED_TESTS_PASSED=0` and my gate script correctly refuses to
call this green. Nor is it the zero-selection false pass the wrapper guards
against: the `"promptTokenCount"` report marker is present, so the test really
was selected and really did run its comparison (39.0 s candidate, 5.0 s base).
What I claim is the decision-relevant quantity — a **zero candidate-vs-base
delta** — backed by the arm-sensitive gate that *is* green, the 64-step tripwire
passing on all three arms with one identical hash. And per rule 35 the oracle
never reaches `prepareFusedRuntimeWeights()`, so it is structurally blind to the
fused-router family this kernel lives in; that blindness is precisely why §3's
standalone bitwise harness and §4's fault injection exist.

**For the advisor (campaign-level, beyond this PR).** On this host the *base
tree itself* cannot pass the zero-tolerance oracle, so
`research/run_upstream_equivalence.sh` is not usable here as an absolute
pass/fail gate — only as a paired base-vs-candidate comparison. Any student
instructed to "make the oracle pass" on an M4 box will burn a cycle chasing a
pre-existing host artifact. Either the runbook should prescribe the paired form
on non-M5 hosts, or the wrapper should diff against a recorded base fingerprint
rather than against zero.

### Rule 17 — the guard is axis-local, and this is provable rather than measured

Rule 17 warns that `DARKBLOOM_*` flags are not axis-local, so I checked whether
the guard can perturb the prefill axis. **It cannot**, for two independent
structural reasons in `LagunaRuntimeMoEGate.callAsFunction`:

1. The `lagunaPrefillRouterTournamentEnabled` branch is tested **first** and
   `return`s. It matches on `projectedLogits.ndim == 3 && dim(0) == 1 &&
   dim(1) > 1 && dim(2) == 256`, i.e. exactly the multi-row prefill case, so
   control never reaches the decode branches during prefill.
2. Even with that branch disabled, both decode branches require
   `projectedLogits.size == 256`. A 512-token prefill tensor is `[1, 512, 256]`,
   size 131072 ≠ 256, so the guard I added is unreachable there regardless.

The guard itself is read at exactly one site (line 9248, inside
`lagunaDecodeRouterTop8`) and nowhere else. Corroborated empirically by the
Stage 3 traces: the `prefill router tournament` line is present and identical in
all three arms, and the 512-token prefill inside the golden gate above passes
with the same hash in all three arms.

I therefore did **not** spend a prefill ABBA on this axis. A 12-sample prefill
measurement would have been weaker evidence than a single-read guard behind two
mutually sufficient shape predicates.

### Why no `--local-iterate` pair

The stage plan suggests one "for context". I deliberately skipped it and report
that as a choice, not an omission:

- Its MDE is **±0.73 % ≈ ±60 µs/step**, an order of magnitude coarser than the
  ±8.8 µs/step the ABBA already achieved. It cannot resolve a 4.2 µs effect, and
  it cannot change a verdict that the ABBA has already settled with 9× margin.
- The only configuration it would time is the **default-OFF** one, which §2
  shows is free by construction: the kernel array is a lazily-initialised
  file-scope `private let` whose sole reader sits behind the guard, so with the
  guard at `"0"` nothing is constructed and nothing extra is dispatched. There is
  no mechanism by which the shipped default could regress.
- The verdict is KILL, so the surface is not a merge candidate and a
  promotion-grade build serves no decision.

Per the stopping rule's fourth clause, I am reporting explicit power analysis
rather than extending the run.

## 8. Bytes (evidence contract item 7)

```
LagunaRuntimeModel.swift: 475,647 B at BASE_SHA -> 483,982 B   (growth +8,335 B)
per-file cap 524,288 B  ->  40,306 B headroom remaining
assignment scope OK: 1 submitted path against BASE_SHA=730e9c2b
editable budget OK: current=2,865,423/3,000,000  headroom=134,577
                    growth=8,335/262,144  files=140 (base=140)
```

+8,335 B is inside rule 8's 12,000 B limit. Since the verdict is KILL, the
cheapest disposition is to **not** merge the surface change at all and keep the
40 KB of per-file headroom for a mechanism that pays.

## 9. Verdict (evidence contract item 8)

**KILL.** Pooled `on-off` = **+4.2 µs/step, 95 % CI [−4.6, +13.0]** against a
**−80 µs/step M4-equivalent** bar. The best case inside the interval is a
−4.6 µs/step gain — 5.8 % of the bar, 17× short.

**M5 transfer caveat.** The campaign's M5 range is `[M4_total / 1.98,
M4_total]`, giving `[2.1, 4.2] µs/step` for the point estimate and a best case
of `[−2.3, −4.6] µs/step`. Fixed costs are ~2× more significant on M5 in *score*
terms, but the bar is already quoted M4-equivalent, so the conclusion transfers:
even under the most generous transfer assumption this mechanism is ~5 % of a
rankable decode arm. There is no plausible M5 story in which 9 removed
intra-threadgroup barriers become 80 µs/step. The M5 also selects `_nax` prefill
variants my host cannot reach, but this change touches no `_nax` twin (rule 9
n/a), so that asymmetry does not apply.

The stopping rule is satisfied by its third clause: Stage 4 gave a resolved Δ
whose CI is decisively below the bar.

**What was nevertheless bought:** a verified-exact decode tournament kernel, a
falsifiable exactness harness for the family, and a quantitative retirement of
"remove intra-threadgroup barriers" as a lever on the glue pool. The frontier's
+0.39 % promotion note names this mechanism; on our tree, at our decode
configuration, the mechanism alone does not reproduce that. Either their gain
came from something else bundled with it, or their baseline's decode router
differed from ours. That is worth the advisor's attention (rule 37: notes are
untrusted public context).

## 10. Suggested follow-ups (not implemented — one hypothesis per PR)

Ranked by expected value, all strictly larger levers than barriers:

1. **Cut dispatch count / fuse the router gate.** 39 dispatches × ~2–3 µs of
   *fixed* overhead ≈ 80–115 µs/step — on its own, the entire bar. This is the
   dominant term in the 4.70 µs/call and the only one large enough to matter.
   Precedent: llama.cpp PR #9698. Rule 27 applies (the −2.2/−2.5 µs per removed
   dispatch figure holds only for an ON-CHAIN dispatch+barrier pair), and rule
   22 (threadgroup-geometry compatibility) must be checked first.
2. **Restrict Phase 2 to lanes < 64.** This falls straight out of the §6
   correction: 192 of 256 lanes redundantly re-sort the same 64 candidates, so
   gating Phase 2 on `lane < 64` removes **126 of 288 SIMD-group-stages (~44 %
   of instruction issue)**. The epilogue only reads lanes 0–7, so it should be
   correct as-is. This attacks the term that actually dominates the sortable
   body, and is plausibly a larger win than the barrier delta by an order of
   magnitude. Cheapest next experiment on this kernel by far.
3. **Fully register-resident selection** via `simd_shuffle_xor` down to 2
   barriers with roughly half the instructions — same target as (2), more work.
4. **Prune the sort network for top-8.** The final 21-stage Phase-2 network
   fully sorts 64 elements when only the first 8 in order are read.
5. **Cheap falsifier for the barrier term itself** (settles §6's reasoned bound,
   rule 19): either double-buffer the exchange to use 1 barrier per cross stage
   instead of 2, or time an on-box N-barrier microkernel to measure the Apple
   barrier coefficient directly. Worth ~30 min and it would retire the question
   for the whole campaign, not just this kernel.

## 11. Reproduction

```bash
BASE_SHA=730e9c2be89a4ed8cf860e52f930f7ff222d4c95

# worker build used by every probe below
bash research/nezuko_q12_build_worker.sh

# Stage 2 + 3: bit-exactness and fault injection
bash research/nezuko_q12_router_tournament_check.sh 4096

# Stage 3: in-situ arm reachability and token smoke (3 arms, 32 steps)
bash research/nezuko_q12_smoke.sh /tmp/nezq12/smoke 32

# Stage 4: two-order ABBA (50 runs, ~35 min)
bash research/nezuko_q12_stage4.sh /tmp/nezq12/stage4 4 256
python3 research/nezuko_q12_stats.py \
    /tmp/nezq12/stage4/orderA /tmp/nezq12/stage4/orderB --trim 0.05

# Gates
bash research/nezuko_q12_gates.sh /tmp/nezq12/gates

# Gates: BASE_SHA attribution control for the oracle's prefill delta
bash research/nezuko_q12_equiv_base_control.sh "$BASE_SHA" /tmp/nezq12/basectl
```

## 12. Files

Submitted (1): `Sources/MLXFastModel/LagunaRuntimeModel.swift`.

Research-only: `research/nezuko_q12_build_worker.sh`,
`research/nezuko_q12_router_tournament_bitwise.swift`,
`research/nezuko_q12_router_tournament_check.sh`,
`research/nezuko_q12_smoke.sh`, `research/nezuko_q12_abba.sh`,
`research/nezuko_q12_stage4.sh`, `research/nezuko_q12_stats.py`,
`research/nezuko_q12_wandb.py`, `research/nezuko_q12_gates.sh`,
`research/nezuko_q12_equiv_base_control.sh`, this document.

Archived logs under `research/pr441-logs/`: `bitwise.log` (Stage 2 + 3
exactness and fault matrix), `stage4_analysis_both.txt` and
`stage4_analysis_split.txt` (pooled and per-order ABBA analyses),
`equivalence.candidate.log` and `equivalence.base.log` (the §7.1 pair).
