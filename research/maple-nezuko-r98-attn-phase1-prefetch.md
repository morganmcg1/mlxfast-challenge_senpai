# r98-B — pre-barrier phase-2 K/V prefetch in the fused decode attention kernels

- PR: #540 · assignment `maple-r98-b-attn-phase1-prefetch` · revision `r98-b-rev1`
- Student: maple-nezuko · branch `maple-nezuko/r98-attn-phase1-prefetch`
- BASE_SHA: `450953e5c8287bfa1f409addf568d7851458cf94`
- Host: Apple M4 Pro, 20 GPU cores, `applegpu_g16s`, macOS 26.5.2
- **Verdict: H-B falsified. Zero official receipts spent (0 of 6 allocated).**
- **Submitted surface: unmodified.** `git diff BASE_SHA HEAD -- Sources/ Vendor/` is 0 bytes.

---

## 1. Hypothesis and preregistration

**H-B.** In the fused decode attention kernels, issuing phase-2 K/V device loads
*before* the phase-1 `threadgroup_barrier` — from simdgroups that currently issue
nothing at all in that window — reduces decode seconds/token, because the
pre-barrier window is memory-idle and the loads are address-independent of
phase-1.

Structural facts that motivated it (all re-verified against the base source this
session, coordinates in §7):

- `laguna_sliding_fused_attn_ring_v1` dispatches 32 threadgroups of 1024 threads
  = **32 simdgroups per threadgroup**. Phase 1 is `if (sg < 3)` (RMSNorm+RoPE on
  Q0/Q1/K) plus `else if (sg == 3)` (V staging). **28 of 32 simdgroups issue
  nothing** between kernel entry and the phase-1 barrier at `:1590`.
- Every phase-2 device address (`pair_keys`, `pair_values`, and the strides) is
  computed from `head0`, `sg`, `lane` and the cache pointers. **None of them
  depends on any phase-1 result.** The only phase-2 datum that *does* depend on
  phase 1 is the single ring slot `widx`, which is read from threadgroup memory
  (`tg_k`/`tg_v`) rather than from device memory.
- So the trip-0 device load is legally hoistable above the barrier with **zero**
  change to arithmetic, and the transformation is bit-exact by construction.

**Preregistered go/no-go.** Advance to an official receipt only if a local
kernel-level improvement projects to **≥ 15 µs/step** of decode wall. Sliding
attention costs **636.0 µs/step** (21.20 µs × 30 layers) out of a 4893.7 µs/step
decode wall, so the threshold is a **−2.36 %** sliding-kernel improvement.

**Preregistered control obligation.** If an official receipt was read, a
revert-control leg had to be run in the same window. *This obligation never
triggered: no official result was requested or read for this arm.* The decision
to stop was made entirely on local paired evidence (§5), and §6 argues that the
receipt channel is strictly the worse instrument for this question.

**Rungs.** (1) sliding kernel, minimal hoist; (2) mechanism ablations; (3) port
to the full-attention kernel; (4) receipt. Rungs 1–2 completed and answered the
question; rung 3 was deliberately not run (§8); rung 4 was declined (§6).

---

## 2. Instrument

`research/nezuko_r98_ab_kernel_probe.swift` (research-only, added on this
branch) is a **paired A/B kernel-cost probe**:

```bash
xcrun swiftc -O research/nezuko_r98_ab_kernel_probe.swift -o /tmp/nezab
/tmp/nezab <base-source.swift> <candidate-source.swift> [kernel-name]
```

It extracts the named kernel's body and header from two copies of
`Sources/MLXFastModel/LagunaRuntimeModel.swift`, compiles **both in one
process**, prints the pipeline properties of each, then measures per-call
microseconds with `reps = 200` serial dispatches per command buffer over **15
alternating rounds** (arm order is flipped on odd rounds, so any within-session
drift cancels), across a threadgroup-count ladder `K ∈ {8, 16, 20, 24, 32, 40,
60}`. It reports `base_min`, `cand_min`, `d_min`, paired `d_mean`, `d_sd`,
paired `t`, and `%`.

`research/nezuko_r98_make_variants.py` generates the ablation sources:

```bash
python3 research/nezuko_r98_make_variants.py /tmp/base_laguna.swift /tmp/r98v
```

Every edit is confined to the sliding kernel's byte range (the file is split at
`name: "laguna_full_fused_attn_grow_v1"` first, because the phase-1 barrier text
is **byte-identical in both kernels**), and every anchor substitution fails
loudly unless it matches exactly once.

**Which `K` matters.** The ranked M5 Max runs 32 threadgroups on 40 cores =
**0.8 TG/core**. On this 20-core M4 Pro the matched operating point is
**K = 16**. Rule 60 established that at ≥ 2 TG/core the machine hides latency on
its own and ILP-style arms go structurally invisible, so K = 40 and K = 60
(2 and 3 TG/core) are included as *contrast*, not as the decision point.

**Null control (base source vs. a byte-identical copy of itself)** — this is the
instrument's noise floor, in the same 15-round alternating protocol:

| K | 16 | 20 | 24 | 32 | 40 | 60 |
|---|---|---|---|---|---|---|
| null `%` | −0.24 | −0.16 | −0.01 | −0.48 | −0.36 | −0.31 |

**The instrument is trustworthy to ±0.5 %.** (K = 8 is always noisy on this
machine and is excluded from every reading below.) At the sliding-attention
budget of 636.0 µs/step, ±0.5 % = **±3.2 µs/step** — **4.7× finer than the
2.36 % (15 µs/step) go-threshold.**

Base per-call cost: ~8.6 µs at K = 8/16/20, ~17.7 µs at K = 24/32/40, ~25.3 µs
at K = 60 — consistent with the rule-60 M4 step function.

---

## 3. Variants

All 11 variants edit only `laguna_sliding_fused_attn_ring_v1`.

| id | what it does |
|---|---|
| `v1_pre_barrier_prefetch` | branchy H-B: pointer hoist + guarded pre-barrier `vec<bfloat,4>` K+V load into `pre_k[4]`/`pre_v0..3`, consumed via a `pre_live` branch inside the loop |
| `v2_ptr_hoist_only` | pointer liveness moved across the barrier, **no** load moved |
| `v3_branch_only` | identical registers and control flow to v1, but the load stays *after* the barrier — **the codegen-matched control for v1** |
| `v4_rotated_pre_barrier` | branchless loop rotation; prologue device load emitted **before** the barrier, threadgroup fixup after |
| `v5_rotated_post_barrier` | identical rotation, prologue load emitted **after** the barrier — **the codegen-matched control for v4** |
| `v6_rotated_pre_barrier_idle_only` | v4 but the early load is taken only by `sg >= 4` (exactly the 28 idle simdgroups) |
| `v7_rotated_pre_barrier_k_only` | v4 but only K is hoisted; V stays after the barrier (halves early traffic) |
| `v9_extra_barrier_after_load` | v5 + a second barrier immediately after the prologue load, so the prefetch registers *do* cross a barrier |
| `v10_extra_barrier_before_load` | v5 + a second barrier *before* the load, wrapped in a uniform `if (widx < window)` so it cannot be folded away — control for v9 |
| `v11_pre_barrier_8_simdgroups` | dose point: early load taken by `sg >= 24` (8 simdgroups) |
| `v12_pre_barrier_1_simdgroup` | dose point: early load taken by `sg == 31` (1 simdgroup) |

**Loop rotation (v4–v12).** `LOOP_K_BASE` becomes `pipe_ka[j] = pre_k[j]`,
`LOOP_V_BASE` becomes `pipe_va{0..3} = pre_v{0..3}`, and the loop tail becomes:

```c
const int pre_adv = (i + 7 * BN < N) ? 4 * inner_k_stride : 0;
pair_keys   += pre_adv;
pair_values += pre_adv;
const bool pre_next = uint(i + 4 * BN) == widx;
T_LOAD_K(pre_k, pre_next, pair_keys);
T_LOAD_V(pre_v0, pre_v1, pre_v2, pre_v3, pre_next, pair_values);
```

The `pre_adv` clamp is a **required safety fix**, not a tuning knob: without it
the final speculative prefetch reads up to 7936 B past the end of the 1 MB
`k_cache` on the last of 8 KV heads. Clamping re-reads the current
(cache-resident) address instead, which also avoids a 6.25 % increase in real
device traffic that would have confounded the measurement.

Loop-trip arithmetic was verified by hand: `N = 512`, `BN = 32`, `i` starts at
`sg ∈ [0, 32)`, condition `i + 3*BN < N` ⇒ **exactly 4 trips** at
`i = sg, sg+128, sg+256, sg+384`, and there is no tail loop. Manual expansions
of `T_LOAD_K`/`T_LOAD_V` in v4/v6/v7/v11/v12 were diffed byte-for-byte against
the macro definitions.

**Bit-exactness.** Structural, not empirical (no receipt was run, so there is no
official `max_abs_diff` for this arm): the ring slot `widx` is never read from
device memory in any variant — the `substitute` predicate that redirects a load
to `tg_k`/`tg_v` is preserved verbatim — and accumulation order is untouched.
The only change is *when* an address-independent device load is issued.

---

## 4. Register footprint and occupancy — every rung, including abandoned ones

Advisor requirement: report `staticThreadgroupMemoryLength` and
`maxTotalThreadsPerThreadgroup` for **every** rung.

| variant | `staticThreadgroupMemoryLength` | `maxTotalThreadsPerThreadgroup` | `threadExecutionWidth` |
|---|---|---|---|
| base | 18432 | 1024 | 32 |
| v1 | 18432 | 1024 | 32 |
| v2 | 18432 | 1024 | 32 |
| v3 | 18432 | 1024 | 32 |
| v4 | 18432 | 1024 | 32 |
| v5 | 18432 | 1024 | 32 |
| v6 | 18432 | 1024 | 32 |
| v7 | 18432 | 1024 | 32 |
| v9 | 18432 | 1024 | 32 |
| v10 | 18432 | 1024 | 32 |
| v11 | 18432 | 1024 | 32 |
| v12 | 18432 | 1024 | 32 |

**Identical at every rung.** `maxTotalThreadsPerThreadgroup` stays at the full
1024 the kernel actually dispatches, so **no variant spilled and none hit an
occupancy cliff**. This matters because it removes the single most common
confound for "adding live registers made it slower": the ~4 % penalty reported
in §5 is *not* a spill and *not* an occupancy loss. Whatever the extra 8×
`bfloat4` of liveness costs, it does not cost occupancy on this compiler.

---

## 5. Results

Paired probe, M4 Pro, 15 alternating rounds. Values are `%` change of the
candidate relative to the first-named arm (positive = **slower**). Null band is
±0.5 % (§2).

| pair | meaning | K=16 | K=20 | K=24 | K=32 | K=40 | K=60 |
|---|---|---|---|---|---|---|---|
| base→v2 | pointer hoist only | +0.10 | +0.21 | +0.31 | +0.69 | +0.90 | +0.47 |
| base→v3 | in-loop branch, load post-barrier | +6.15 | +6.19 | +6.23 | +6.14 | +5.58 | +7.60 |
| base→v1 | in-loop branch, load pre-barrier | +5.45 | +6.21 | +5.80 | +5.37 | +5.01 | +5.46 |
| **v3→v1** | **H-B with codegen held fixed** | **+0.24** | **+0.14** | **−0.54** | **−0.43** | **+0.59** | **−2.01** |
| base→v5 | loop rotation alone | +2.04 | +2.13 | +1.91 | +2.05 | +2.34 | +4.33 |
| **v5→v4** | **H-B, branchless form** | **+4.79** | **+4.87** | **+3.80** | **+3.91** | **+5.09** | **+2.64** |
| base→v4 | full branchless H-B | +6.88 | +7.12 | +7.16 | +6.62 | +5.97 | +7.16 |
| v5→v6 | pre-barrier, 28 idle sg only | +3.80 | +3.97 | +3.78 | +4.02 | +4.56 | +2.15 |
| base→v6 | — | +6.12 | +6.37 | +7.21 | +6.59 | +6.38 | +6.73 |
| v5→v7 | pre-barrier, **K only** (half traffic) | +5.46 | +5.45 | +3.65 | +3.37 | +3.83 | +3.48 |
| v5→v10 | extra barrier, nothing crosses | +1.29 | +0.46 | −0.81 | −0.83 | −0.54 | −2.38 |
| v10→v9 | — | −0.25 | −0.25 | +0.31 | +0.22 | −0.09 | +2.03 |
| **v5→v9** | **registers cross an extra barrier** | **−0.14** | **−0.03** | **+1.18** | **+1.22** | **+0.67** | **−0.35** |
| v5→v11 | pre-barrier, 8 sg | +4.28 | +6.17 | +4.27 | +3.40 | +4.61 | +4.00 |
| v5→v12 | pre-barrier, **1 sg** | +4.23 | +4.25 | +4.82 | +4.37 | +3.71 | +5.06 |

### 5.1 The clean answer: v3→v1 is exactly zero

`v3` and `v1` have **identical registers, identical control flow and identical
work**; the *only* difference is which side of the phase-1 barrier the trip-0
device load sits on. That contrast reads **+0.24, +0.14, −0.54, −0.43, +0.59,
−2.01** — a mean of about **0.0 %**, inside the ±0.5 % null band at the matched
operating point, with **no trend toward positive at low occupancy** where H-B
predicted the effect should be largest.

**Hoisting the load across the barrier buys nothing.**

### 5.2 Every way of *expressing* the transformation costs something

- an in-loop `pre_live` branch: **+5.6 to +7.6 %** (base→v3, which contains no
  hoist at all)
- a branchless loop rotation: **+1.9 to +4.3 %** (base→v5, also no hoist)
- splitting the ring-slot load across the barrier: a **further +3.4 to +5.1 %**
  (v5→v4)

Only the pointer hoist alone (v2, +0.1 to +0.9 %) is close to free, and it moves
no memory traffic.

### 5.3 The ~4 % cross-barrier penalty is static codegen, not hardware

Dose-response across the number of simdgroups that actually take the early path:

| issuing simdgroups | 1 (v12) | 8 (v11) | 28 (v6) | 32 (v4) |
|---|---|---|---|---|
| cost vs. v5, K=16 | +4.23 | +4.28 | +3.80 | +4.79 |
| cost vs. v5, K=32 | +4.37 | +3.40 | +4.02 | +3.91 |

**Flat.** A transformation whose *dynamic* footprint is 1/32 of the threadgroup
cannot produce a 4 % whole-kernel cost by executing. The penalty is therefore
emitted for all simdgroups regardless of which take it: splitting the ring-slot
load into a pre-barrier **device** block plus a post-barrier **threadgroup**
block prevents the compiler from forming the single predicated `T_LOAD` diamond
it emits in the base kernel, and that lost fusion is the whole cost.

### 5.4 Mechanisms explicitly ruled out

| candidate explanation | discriminator | reading | verdict |
|---|---|---|---|
| register liveness across a barrier is expensive | v5→v9 (same code, extra barrier that the prefetch registers must cross) | −0.14 / −0.03 / +1.18 / +1.22 / +0.67 / −0.35 | **ruled out** — crossing a barrier per se is free |
| the early loads add memory traffic | v5→v7 (K only, half the early traffic) | +5.46 / +5.45 / +3.65 / +3.37 / +3.83 / +3.48 | **ruled out** — same cost at half traffic |
| early loads contend with phase-1 simdgroups | v5→v6 (only the 28 idle sg load early) and v5→v12 (one sg) | +3.80…+4.56 and +4.23…+5.06 | **ruled out** — removing the contention changes nothing |
| register spill / occupancy cliff | pipeline properties, §4 | 18432 / 1024 / 32 for all 12 sources | **ruled out** |

---

## 6. Go/no-go, and why receipts were not spent

Preregistered threshold: **≥ 15 µs/step**, i.e. **−2.36 %** of the sliding
kernel. Best observed anywhere in the matrix at the matched operating point:
**−0.0 %** (v3→v1). Every arm that actually implements H-B end-to-end
(base→v1, base→v4, base→v6) is **+5 to +7 % slower**. The go condition fails by
a wide margin, in the correct direction, at every K.

I also declined the receipt on **scientific** grounds, not merely budgetary ones.
Measuring the H-B contrast officially means measuring `v3 → v1` on M5 — a
difference of differences, because `base → v1` is dominated by the +6 % branch
penalty that has nothing to do with the hypothesis. Its expected magnitude is
the local reading, **±3.2 µs/step**. One receipt's candidate-decode noise is
**σ(cand_dec) = 14.4 µs/step**. The official channel is therefore **≈4.5×
coarser than the instrument I already have**, and two receipts (~50 min of the
shared M5) could not have distinguished the observed effect from zero. Spending
them would have bought a strictly less informative answer.

Consequently the preregistered revert-control leg was never required: **no
official result was read for this arm.** 0 of 6 receipts used.

---

## 7. Verified kernel coordinates (base numbering, `Sources/MLXFastModel/LagunaRuntimeModel.swift`)

**Sliding — `laguna_sliding_fused_attn_ring_v1`** (JIT `MLXFast.metalKernel`; no
`.metal` twin, so no metallib rebuild is involved):

- decl `:1508`, source literal `:1516-1873`, header/macros `:1874-1922`, close `:1924`
- constants `:1517-1526`: `head_dim=128, window=512, gqa=8, BN=32, BD=32, BDP=33, qk_per_thread=4, v_per_thread=4, rotary_pairs=64, N=512`; `typedef float U`
- phase-1 `if (sg < 3)` `:1544-1583`; `else if (sg == 3)` V stage `:1584-1589`
- **phase-1 barrier `:1590`**; KV-cache write `:1592-1603`; threadgroup planes `:1605-1607`; phase-2 pointers `:1609-1614`; strides `:1615-1616`
- phase-2 loop `int i = sg; for (; i + 3*BN < N; i += 4*BN)` `:1639-1818`, 4-way unrolled; `T_LOAD_K` `:1655-1658`; `T_LOAD_V` `:1663-1670`; pointer advance `:1816-1817`
- macros: `LAGUNA_RESCALE` `:1875-1883`, `T_LOAD_K` `:1885-1901`, `T_LOAD_V` `:1903-1919`
- dispatch `lagunaSlidingFusedAttention` `:1929`; grid `((heads/2)*1024,1,1)`, TG `(1024,1,1)` at `:1971-1972` → **32 TGs × 32 simdgroups**, heads = 64, kv heads = 8

**Full — `laguna_full_fused_attn_grow_v1`**: decl `:2028`, source `:2036-2406`;
`gqa=6`, `rotary_pairs=32`, `yarn_mscale=1.3465735912322998f`; barrier `:2118`;
phase-2 pointers `:2137-2142` (use `capacity`); loop `for (; i + BN < N; i += 2*BN)`
`:2168-2259`, 2-way unrolled; single-position tail `:2260-2302`; dispatch
`lagunaFullFusedAttention` `:2413`, grid/TG `:2456-2457` → 24 TGs.

⚠ The `} else if (sg == 3) { … } threadgroup_barrier…` text is **byte-identical
in both kernels**. Any future edit here must disambiguate with extra context or
byte-range splitting (the variant generator does the latter).

---

## 8. What this does and does not settle

**Settled.** On this stack, "issue an address-independent device load earlier, in
the window before a `threadgroup_barrier`, from simdgroups that are idle" is
worth **0.0 % ± 0.5 %** when codegen is held fixed, and costs a flat ~4 % static
penalty in every source form that actually expresses it — independent of how
many simdgroups issue early (1, 8, 28 or 32) and independent of traffic volume.

**Proposed rule text.**

> A hot path being latency-bound does not imply that its pre-barrier window is
> exploitable. In the Laguna fused decode attention kernels, hoisting a phase-2
> device load above the phase-1 `threadgroup_barrier` is worth 0.0 % ± 0.5 %
> when register pressure and control flow are held fixed, and costs a flat
> ~4 % static codegen penalty in every form that expresses it, independent of
> issuing-simdgroup count (1/8/28/32) and of traffic volume (K-only vs. K+V).
> The cost is not spill and not occupancy: `staticThreadgroupMemoryLength`
> (18432) and `maxTotalThreadsPerThreadgroup` (1024) are identical for the base
> and all 11 variants. "Issue work earlier across a barrier" is a systematically
> non-positive transformation here; close the family.

**Relation to the round-98 thesis.** The thesis after rules 66/67/68 was that the
M5 hot path is *latency-bound, not work-bound*. H-B was the cleanest positive
prediction that thesis makes, and it fails. The thesis is not thereby refuted —
the hot path may still be latency-bound — but it is now constrained: **the
latency is not exposed at the barrier boundary**, and it cannot be recovered by
software-pipelining loads across it, because on this compiler the source-level
transformation that expresses the hoist destroys more (a fused predicated load
diamond) than the hoist can win. If the path is latency-bound, the latency lives
somewhere the barrier boundary does not expose.

**Not settled: the full-attention port (rung 3).** I deliberately did not run
it. The mechanism identified in §5.3 is *compiler behavior on a source-level
transformation*, not a property of the sliding kernel's shape, so the full
kernel should behave the same; and the probe's buffer set is hardcoded for the
sliding kernel (the full kernel needs `capacity`, `gqa=6`, `rotary_pairs=32`, so
it needs new buffer setup). Sliding attention is 636.0 of the 865.7 µs/step
decode-attention budget (73 %), so the untested remainder is small. If the
advisor disagrees, the port is a cheap follow-up — roughly one probe-setup
change and one variant-generator split point.

---

## 9. Files

**Submitted surface: none.** `Sources/MLXFastModel/LagunaRuntimeModel.swift` is
**unmodified**; the earlier hand-edited v1 was reverted and every variant is
reproduced from the generator. Verified: `git diff BASE_SHA HEAD -- Sources/
Vendor/` = 0 bytes; `senpai/check-editable-budget.sh` reports
`current=2899476/3000000 headroom=100524 growth=0/262144 files=141`.

**Research-only (added on this branch):**

- `research/nezuko_r98_ab_kernel_probe.swift` — paired A/B kernel-cost probe
- `research/nezuko_r98_make_variants.py` — ablation variant generator (11 variants)
- `research/maple-nezuko-r98-attn-phase1-prefetch.md` — this note

**Reproduction:**

```bash
git show 450953e5c8287bfa1f409addf568d7851458cf94:Sources/MLXFastModel/LagunaRuntimeModel.swift > /tmp/base_laguna.swift
python3 research/nezuko_r98_make_variants.py /tmp/base_laguna.swift /tmp/r98v
xcrun swiftc -O research/nezuko_r98_ab_kernel_probe.swift -o /tmp/nezab
/tmp/nezab /tmp/r98v/v5_rotated_post_barrier.swift /tmp/r98v/v4_rotated_pre_barrier.swift
/tmp/nezab /tmp/r98v/v3_branch_only.swift /tmp/r98v/v1_pre_barrier_prefetch.swift
```

---

## 10. Suggested follow-ups (not implemented)

1. **Full-attention port of the probe** (cheap). Generalize the probe's buffer
   set to `laguna_full_fused_attn_grow_v1` and re-run v3→v1 and v5→v4 there.
   Expected: the same flat zero. Worth doing only if the advisor wants the
   remaining 27 % of the attention budget closed explicitly rather than by
   mechanism argument.
2. **Full-attention 2-way → 4-way unroll** (independent of H-B). The full kernel
   unrolls its phase-2 loop 2-way (`:2168-2259`) where the sliding kernel
   unrolls 4-way. This is a *work-scheduling* change, not a barrier-crossing
   change, so §5 says nothing against it. Estimated ~9 kB of source growth,
   comfortably inside the 100,524 B headroom, and the existing probe measures it
   directly once its buffer set is generalized (shares all setup work with
   follow-up 1).
3. **Don't** retry any variant of "issue work earlier across a barrier" — that
   family is closed by §8.

---

## 11. Frontier-swap audit (advisor HOLD `r98-b-hold-frontier-cc6ddc1`, 13:46:12Z)

The HOLD arrived after all measurement was complete. Compliance first:

- **No GPU was spent after the hold.** Nothing was mid-flight; no build, no
  benchmark, no `run_job` launch has run since.
- **I did not rebase onto `4f3108c4`.** The branch sits on `450953e5`, the base
  this arm was assigned and measured against. The one rebase I did do
  (`e510bb3d` → `450953e5`) predates the hold and was the tidy-up the earlier
  base-moved comment explicitly permitted; it changed 0 bytes of submitted
  surface.
- **Nothing is being proposed for merge or submission.** This arm's submitted
  surface is empty — there is no candidate binary measured on `e510bb3d` to
  push, because the answer was "don't make this change".
- The hold asked: *"If you already have those numbers or any M4 measurements
  against `e510bb3d`, commit them to a `research/*.md` file so we can compare
  against the new frontier."* That is precisely §4 and §5 of this note.

Then, because it is read-only, free, and directly answers the audit you said
you were about to run, I diffed the two kernels at `4f3108c4` against my base
(`git show` plus string inspection — no build, no rebase, no GPU).

**The H-B premise survives the frontier swap intact.**

| property | base `450953e5` | frontier `4f3108c4` | |
|---|---|---|---|
| `laguna_sliding_fused_attn_ring_v1` exists | yes `:1508` | yes `:1417` | ✅ survives |
| phase-1 guard `if (sg < 3)` | `:1544` | `:1452` | ✅ same |
| V stage `else if (sg == 3)` | `:1584` | `:1492` | ✅ same |
| **phase-1 barrier** | `:1590` | **`:1498`** | ✅ same |
| dispatch grid | `((heads/2)*1024,1,1)` | `((heads/2)*1024,1,1)` | ✅ **identical** |
| threadgroup | `(1024,1,1)` | `(1024,1,1)` | ✅ **identical** |
| ⇒ idle simdgroups pre-barrier | **28 of 32** | **28 of 32** | ✅ **premise holds** |
| `T_LOAD_K` macro text | 1011 B | 1011 B | ✅ **byte-identical** |
| `T_LOAD_V` / `substitute` predicate | `:1903` | `:1740` | ✅ same mechanism |
| sliding phase-2 unroll | **4-way** (`i + 3*BN < N`) | **2-way** (`i + BN < N; i += 2*BN`) `:1548` | ⚠️ **changed** |
| sliding kernel source bytes | 21,722 | 17,863 | −3,859 |
| `laguna_full_fused_attn_grow_v1` | `:2028` | `:1866` | ✅ survives |
| full phase-1 barrier | `:2118` | `:1955` | ✅ same |
| full phase-2 unroll | 2-way | 2-way `:2006` | unchanged |
| full kernel source bytes | — | 15,397 | — |

Three consequences.

1. **The negative transfers with high confidence.** The mechanism I measured is
   a property of the compiler's handling of the `T_LOAD_K(dst, substitute, ptr)`
   predicated-load diamond, and that macro is **byte-identical** at the new
   frontier. The geometry that makes 28 simdgroups idle is identical. So the
   prefetch window still exists, still has the same shape, and splitting the
   same macro across the same barrier should still cost the same ~4 %.
   Re-confirming it at `4f3108c4` costs ~30 minutes of local probe time and
   **zero receipts** — the variant generator only needs its split point and
   loop-rotation anchors retargeted from the 4-way to the 2-way loop. Say the
   word and I will run it; otherwise I would not spend the time, because the
   dose-response evidence in §5.3 already localises the cost to codegen rather
   than to anything the frontier changed.

2. **Rung 4 of my brief is inverted at the frontier — and that is now the more
   interesting question.** The brief asked me to raise the *full* kernel from
   2-way to match *sliding's* 4-way, as the cheapest test of the round-98
   thesis. The promoted frontier went the **opposite** way: it dropped sliding
   from 4-way to 2-way, shrinking that kernel by 3,859 bytes. Given that
   headroom collapsed to 16,151 B at the new base, that looks like a
   **byte-motivated** change, not a speed-motivated one. If so, the frontier may
   have paid decode time for source bytes at exactly the site this assignment
   cares about, and restoring sliding to 4-way is a *work-scheduling* arm that
   §5 says nothing against — my negative closes "issue earlier across a
   barrier", not "issue more per trip". I did not measure it (out of scope, and
   the hold forbids GPU), but the probe already in this branch measures it
   directly with one anchor change.

3. **`DARKBLOOM_COMPILED_TIERED_ATTENTION` / `DARKBLOOM_COMPILED_DECODE` do not
   remove the window.** Whatever those gates select, the JIT
   `MLXFast.metalKernel` sliding path above is still present and still reached
   from `lagunaSlidingFusedAttention` at `:1766`, called at `:6019`. I did not
   audit which gate wins at runtime — that is your audit, and it needs the
   scored build I am not permitted to run.

Byte note: `senpai/check-editable-budget.sh 4f3108c4…` run against my
(deliberately un-rebased) tree reports `growth=-84373`, which simply reflects
that my tree still carries the *old* solver. It is not a budget claim for this
arm. This arm's growth is **0 bytes** by construction.

---

## Reply

H-B is **falsified**, cleanly, and I spent **zero of the six allocated
receipts**.

The decisive contrast is `v3 → v1`: two kernels with byte-identical register
pressure and control flow, differing only in which side of the phase-1 barrier
the trip-0 device load sits on. It reads **0.0 % ± 0.5 %** at the M5-matched
operating point (K = 16 on this 20-core M4 Pro ≈ 0.8 TG/core), with no trend
toward positive at low occupancy. The 28 idle simdgroups are idle for a reason
the barrier boundary does not expose.

Worse for the family: every source form that *implements* the hoist costs
**+5 to +7 %** end to end. I traced that to static codegen, not hardware, via a
dose-response ablation — 1, 8, 28 and 32 issuing simdgroups all cost the same
~4 %, which is impossible for a dynamic effect with a 1/32 footprint. Splitting
the ring-slot load into a pre-barrier device block plus a post-barrier
threadgroup block stops the compiler forming the fused predicated `T_LOAD`
diamond, and that lost fusion is the entire cost. I ruled out barrier-crossing
register liveness (v5→v9 ≈ 0), traffic volume (v5→v7, half the traffic, same
cost) and cross-simdgroup contention (v6, v12) as alternatives.

Per your standing requirement, register footprint for **every** rung including
the abandoned ones is in §4: `staticThreadgroupMemoryLength = 18432` and
`maxTotalThreadsPerThreadgroup = 1024` for the base and all 11 variants. Nothing
spilled and nothing lost occupancy, so the ~4 % is genuinely codegen.

On receipts: measuring H-B officially means measuring the `v3 → v1` difference
of differences, expected magnitude ±3.2 µs/step against σ(cand_dec) =
14.4 µs/step per receipt. The official channel is 4.5× *coarser* than the local
instrument, whose null band I validated at ±0.5 % (≈ ±3.2 µs/step, 4.7× finer
than the 15 µs/step go-threshold). I declined the receipt on that basis rather
than on budget. Because no official result was read, the preregistered
revert-control-leg obligation never triggered.

Proposed rule text is in §8. I did not port to the full-attention kernel — §8
explains why (mechanism is compiler-level, sliding is 73 % of the attention
budget, and the probe's buffer set is sliding-specific); say the word and it is
a cheap add.

**On the HOLD.** It landed after all measurement was finished, so nothing was
wasted and no GPU has run since. I did not rebase onto `4f3108c4` and I am not
asking you to merge anything — this arm's submitted surface is empty, so there
is no `e510bb3d`-measured candidate to push. What I am publishing is exactly
what your hold asked for: the occupancy and M4 numbers, committed to a
`research/*.md`, so you can compare them against the new frontier.

**Two things from §11 that I think change your audit**, both established
read-only with `git show`:

1. **The premise survives the swap.** At `4f3108c4` the sliding kernel still
   dispatches `grid ((heads/2)*1024)` × `threadGroup (1024)` — identical
   geometry, so still 28 of 32 simdgroups idle before the phase-1 barrier
   (now `:1498`) — and the `T_LOAD_K` macro is **byte-identical**, 1011 bytes,
   same `substitute` predicate. Since §5.3 localises the ~4 % to the compiler's
   handling of *that macro*, the negative should transfer unchanged. I can
   re-confirm it at the new base for ~30 min of local probe time and **zero
   receipts** if you want it nailed down; I would otherwise not spend it.

2. **The frontier moved sliding's phase-2 loop from 4-way to 2-way unrolled**
   (`for (; i + BN < N; i += 2 * BN)` at `:1548`), shrinking that kernel by
   3,859 bytes. With headroom collapsing to 16,151 B, that reads as a
   **byte-motivated** trade. If it is, the promoted frontier may have paid
   decode time for source bytes at precisely the site this arm was pointed at —
   and rung 4 of my brief is inverted: instead of raising *full* to 4-way, the
   live question is whether restoring *sliding* to 4-way pays. That is a
   work-scheduling arm, which my negative explicitly does **not** close, and the
   probe already on this branch measures it with one anchor change. It is the
   cheapest surviving test of the round-98 thesis I can see, and it needs a byte
   answer before a timing answer.

I am holding as instructed and will take either a fresh revision bound to
`4f3108c4` or a close.
