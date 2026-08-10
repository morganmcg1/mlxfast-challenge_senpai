# R107-A — routed MoE gate/up threadgroup-packing curve (PR #629)

Student: maple-edward. Branch `maple-edward/r107-routed-gateup-packing`.
Assigned head `526881c4f6e2b879c1dfef67212b852cf5c9b7ed`, PR base
`ca39d2163255a4fdda39609447328b76acd7f0a9`.

Host: Apple M4 Pro, 14 CPU / 20 GPU cores, 48 GiB, macOS 26.5.2, Apple GPU
generation 16 (`applegpu_g16s`), low-memory startup profile. Every timing number
below is M4-local and directional; only the tagged structural claims are argued
to transfer.

---

## 0. Process note — routing defect, since repaired

PR #629 was created at 2026-08-10T10:03Z with **no
`<!-- senpai-assignment:v1 ... -->` marker**. Verified absent at 10:03Z, 10:46Z
and 10:59Z, with `updated_at` frozen at `2026-08-10T10:03:23Z`; the controller
re-emitted `malformed_assignment` on every poll during that window.

The advisor repaired routing at **2026-08-10T11:09:24Z**. The marker now carries
`assignment_id=maple-r107-a-routed-gateup-packing`, `revision_id=r107-a-rev1`,
`head_sha=526881c4…`, `student=maple-edward`, so `submit_experiment_result` is
unblocked and no result is at risk.

Recorded only because it cost roughly one hour of assignment wall-clock at the
start of the run, and because the marker's `base_sha` (`3241e5e5…`) still
differs from the PR's own base (`ca39d216…`). That drift is docs-only — no
`Sources/` or `Vendor/` file differs between the two — so no rebase or rebuild
was required and every binary below is valid against the assigned head.

## 0a. Correction to the PR body

The PR body names the site as `lagunaRoutedSwiGLUQMVPackedTop8Kernel`. That is
the **v1 fallback**
(`laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_bf16_v1`, declared at
`LagunaRuntimeModel.swift:7892-7902`). The shipped default on the scored decode
path is the **R1** variant
`lagunaRoutedSwiGLUQMVPackedTop8R1Kernel`
(`laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2`, declared at
`:7915-8028`, selected at `:8044` unless `DARKBLOOM_ROUTED_GATEUP_R1=0`).
The experiment parameterizes R1, which is the code that actually runs.

---

## 1. Rule-83 history search — the arm is open but repriced sharply downward

Searched for the routed kernel name, "packing", "rows per simdgroup", PR #308,
and `DARKBLOOM_ROUTED_GATEUP`.

**Open, and this is the named follow-up.**

- `research/maple-tanjiro-threadgroup-packing-curve.md` §6.1 (`:862-891`) lists
  site 1 as the routed MoE gate/up packed top-8 R1 kernel and classifies it
  "SAFE to repack"; §6.2 (`:892+`) calls S=4–8 "the highest-value single
  follow-up"; the `_sgN` JIT-cache warning is at `:930-943`; §7.5 (`:1040+`)
  specifies exactly the S ∈ {2,4,8,16} ABBA sweep this PR assigns.
- Restated as idea **L3** in
  `research/RESEARCH_IDEAS_2026-08-08_21:40.md:173-182`.
- Not on any closed-families list. Rule 70 explicitly re-permits MoE proposals
  that change "dispatch structure".

**Supporting prior.** PR #308 (QKV kernel, M4 Pro, W&B `8st0k26f`) swept
S ∈ {1,2,4,8,16,32} at fixed grid threads and fixed total simdgroups. It found a
shallow, non-monotone basin with a flat left shoulder, argmax at S=8 with
−36.9 µs/step, 95% CI [−61.0, −12.9], bit-exact, prefill null. Verdict PURSUE;
the patch was left unapplied.

**What that prior is worth under rule 105.** −36.9 M4 µs/step × 0.006653
= **−0.246 %`cs`** in the primary α (bytes) regime, k = 0.4369; −0.219 % at
k = 0.389 and −0.281 % at k = 0.5 [M4-WALL] [base_sha 3241e5e5]. So even if
Stage A reproduces #308 exactly, this arm alone does **not** clear the 0.4 %
bar — it is a rule-105.5 summation component in family T0b(a), and the routed
family T2c contributes nothing (see §6.1). The honest pre-registered ceiling for
this PR is therefore "one verified component worth ≈0.25 %", not a standalone
graduation.

**Counter-evidence that repriced my prior to null before any measurement.**

- L3 note, `research/CURRENT_RESEARCH_STATE.md:3327-3334`: PR #48's 8× threadgroup
  collapse earned **−0.1488% on M5 receipt `285f79fa`**, and "geometry
  neutrality is absolute until #496 says otherwise". **§5.0 corrects my reading
  of this bullet**: that collapse was on the *same* QKV lane-major site as `L3`,
  not a different one, but it was a 3-way composite whose M4 decomposition
  attributes only −35.4 of −55.0 µs/step to geometry, so the receipt does not
  price the geometry term.
- 105-D (PR #603): decode is memory-bound, occupancy is *anti*-correlated with
  cost, bytes are the cost proxy, "nothing clears +0.5%". Item 3b flags an
  unresolved residency ambiguity at 64 threads/TG (48 vs 24 TG per core), so
  neither figure may be quoted as fact.
- 105-E (PR #609): this kernel family's M5 occupancy is 0.975 and its
  occupancy penalty is 14.8 µs = **0.226% of the candidate score**; the whole
  PARALLELISM bucket tops out at 0.384% against a 0.5% bar → verdict N-1.
  *Caveat I am obliged to state*: 105-E's derate is a function of **grid
  threads**, which this experiment holds fixed, so it bounds the family but is
  not strictly on-point for threadgroup geometry at fixed grid threads.
- PR #543 §I: probe→in-situ non-transfer, a 14% probe gain became −25.5 µs/tok
  in situ with an error bar 5.4× the effect. §H: threadgroup-doubling DEAD,
  φ=1.8008, threadgroup cost is a step function with risers at K=20n+1.
  `#543:2718-2723`: site 1 at S=2 already runs 51.2 threadgroups per M5 core,
  so there is no residency deficit to recover.

**Pre-registered prior (written before stage 1 ran): null.** The primary
deliverable is therefore the exclusion bound, not a win. PR #308's basin was
measured on a *bandwidth-lighter* attention kernel; this site moves the largest
bytes-per-step of any decode kernel, and every byte-bound geometry result in the
record has come back null or negative.

## 2. Mechanism and implementation

### 2.1 What the shipped kernel does

`laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2` is dispatched
**39 times per decode step** (40 layers, layer 0 dense). The call site is
`LagunaRuntimeSparseMoEBlock.forward` (`LagunaRuntimeModel.swift:10801`), the
decode guard is `x.dim(1) == 1 && inds.size < 64` (`:10809`) and the packed path
is `:10833-10858`. It is a **decode-only** path, so prefill is structurally
untouched by anything in this experiment.

Grid is 131,072 threads = 4,096 simdgroups; each simdgroup owns exactly one of
512 logical rows (8 experts × 64 rows), one row per simdgroup. The kernel has
**no threadgroup memory and no barriers** — the only cross-lane primitive is
`simd_sum` — so simdgroups are fully independent and can be re-bundled into
threadgroups freely.

### 2.2 The one-line change

The whole mechanism is the row-ownership stride:

```metal
uint logical_row = tile * S + simd_group;   // shipped: S = 2
```

with the dispatch changed from `threadGroup: (64,1,1)` to
`threadGroup: (32*S,1,1)` and **grid threads unchanged**. For any S dividing
512, `tile ∈ [0, 512/S)` and `simd_group ∈ [0,S)` make `logical_row` a bijection
onto `[0,512)`, so the set of rows computed, the bytes each simdgroup reads, the
qdot order and the reduction order are all invariant. The change is bit-exact
**by construction**, not by luck.

The scale-tile mapping bakes in 4 rows per tile
(`scale_tile_bytes = 4 * scale_kblock_bytes`, with R1 re-deriving
`(logical_row/4) * scale_tile_bytes` and `sub = logical_row % 4`). Because it is
re-derived from `logical_row` it survives repacking untouched; that is the
invariant the store-row fault control in §3.3 deliberately breaks.

### 2.3 Submitted surface

Only `Sources/MLXFastModel/LagunaRuntimeModel.swift`, **+2,021 bytes net**
(54 insertions / 7 deletions) for the routed selector alone. With the stage-A
QKV lane-major selector of §5 added, the branch's whole submitted surface is
still that one file at **+3,655 bytes** net (107 insertions / 23 deletions)
against base `4e9a8e16`, i.e. 45 % of the 8 KiB assignment cap, 387,900 bytes
against the 524,288-byte per-file cap, and 1.4 % of the 262,144-byte
per-review growth allowance. No other submitted path is touched: the one
`Vendor/mlx-swift/.../quantized.cpp` hunk visible against the older
`3241e5e5` is the advisor's own default-inert `c768d21f` base advance, not mine.

- `lagunaRoutedSwiGLUQMVPackedTop8R1Source(_ sg: Int) -> String` (~`:7917`) —
  the previous literal, with the single substitution above. At `sg = 2` it
  renders byte-identical to the shipped literal; §3.1 proves that with a hash.
- `lagunaRoutedSwiGLUQMVPackedTop8R1Kernel` (~`:8026`) — name and body
  unchanged, now built from `…R1Source(2)`.
- `lagunaRoutedGateUpPackingSimdgroups` (`:8039-8046`) — parses
  `DARKBLOOM_ROUTED_GATEUP_SG`, accepts only `{2,4,8,16,32}`, and returns 0 for
  anything else, which leaves the shipped path completely untouched.
- `lagunaRoutedSwiGLUQMVPackedTop8SGKernel` (`:8048-8061`) — `nil` at selector
  0; otherwise a **distinct** pipeline named `…r1_bf16_v2_sg\(sg)`.

The distinct name is mandatory, not cosmetic: MLX caches JIT libraries by kernel
name (`mlx/backend/metal/jit/custom_kernel.cpp:56-72`, `device.cpp:820-861`), so
reusing one name across arms would serve arm A's compiled library to arm B and
silently destroy the A/B comparison (rule 33). §3.1 shows the separation costs
nothing arithmetically: `base` and `sg2` render the identical Metal body.

`verbose: true` on `MLXFastKernel` prints to `std::cout`
(`mlx/backend/metal/metal_kernel.cpp:342`), which corrupts the worker's JSON
stdout protocol. The instrumented build therefore writes its receipt to stderr.

## 3. Stage 0 — reached geometry, parity, fault control

Driver `research/maple-edward-r107a-stage0.sh` (job `b23cb4f0`, exit 0, full run;
job `84de6c21`, exit 0, geometry top-up for the SG=1 receipt).

Rule 75: `digest_before = digest_after =`
`9f22da52768e28b2fb9b10b13d6806509bd3e8e44f89808fbe7504e842b7526b` on both runs
— the instrumented and fault builds left `Sources` and `Vendor` byte-identical.

### 3.1 Reached geometry (rule 77)

Receipts are emitted from inside the dispatch call, not inferred. On every arm:
`grid_threads = 131072`, `total_simdgroups = 4096`, `rows_per_simdgroup = 1`,
`logical_rows = 512`.

| arm | selector | simdgroups/TG | threads/TG | threadgroups | pipeline suffix | Metal source SHA-256 (prefix) | row stride |
|---|---|---|---|---|---|---|---|
| base  | 0  | 2  | 64  | 2048 | *(none)* | `d709725f8351a0af` | `tile * 2` |
| sg1   | 0  | 2  | 64  | 2048 | *(none)* | `d709725f8351a0af` | `tile * 2` |
| sg2   | 2  | 2  | 64  | 2048 | `_sg2`   | `d709725f8351a0af` | `tile * 2` |
| sg4   | 4  | 4  | 128 | 1024 | `_sg4`   | `9eaa9134451cc956` | `tile * 4` |
| sg8   | 8  | 8  | 256 | 512  | `_sg8`   | `9bf93a0146166271` | `tile * 8` |
| sg16  | 16 | 16 | 512 | 256  | `_sg16`  | `50306db5122b76e7` | `tile * 16` |

Three things this proves.

1. **Every arm matches the shipped dispatch on the quantities rule 77 names.**
   Grid threads, total simdgroups, rows per simdgroup and bytes written per
   row are constant; only `(threadgroups, threads/TG)` moves, and their product
   is invariant.
2. **No arm spills or exceeds 1024 threads/TG.** The maximum reached is 512 at
   S=16. Metal rejects a `threadsPerThreadgroup` above the pipeline's
   `maxTotalThreadsPerThreadgroup`, so a *successful* run at 32·S threads is
   itself the proof of support. Headroom exists for S=32 (1024) if the advisor
   wants that dose later.
3. **`base` and `sg2` share `metal_src_sha`.** The rule-33 name separation
   demanded by the assignment is arithmetically free: `sg2` is the shipped
   kernel body compiled under a distinct pipeline name. That is what makes
   `base → sg2` a clean price for the machinery alone.

`sg1` is the receipt for the stage-1 `null1` arm: `DARKBLOOM_ROUTED_GATEUP_SG=1`
is not an accepted value, so it parses to selector 0, the `_sgN` pipeline is
never built, and the unsuffixed shipped pipeline runs with the identical source
hash. `null1` is therefore a genuine **identical-execution** null (rule 79), not
an approximation of one.

### 3.2 Greedy token parity

96 teacher-forced steps on the public golden
(`correctness_prompts/public_longcopy_gate_english_512_256.json`), shipped
candidate binary, one arm per selector:

| arm | divergences | decode median | token checksum |
|---|---|---|---|
| base | 0 | 8.216 ms | `3157477821` |
| sg2  | 0 | 8.208 ms | `3157477821` |
| sg4  | 0 | 8.208 ms | `3157477821` |
| sg8  | 0 | 8.221 ms | `3157477821` |
| sg16 | 0 | 8.279 ms | `3157477821` |

Distinct checksums across all five arms: **1**, as required.

### 3.3 Store-row fault control (must fail — it did)

The control compiles the `_sgN` pipeline from `…R1Source(2)` — i.e. the *wrong*
row stride — while dispatching 32·S threads. Rows are then mis-owned: roughly
74% of the 512 output rows are left unwritten or raced.

| control | divergences | first divergence |
|---|---|---|
| fault-sg8  | 1 | step 9, position 509, token 83 |
| fault-sg16 | 2 | step 1, position 902, token 5991 |

Both failed, so the parity probe is demonstrably wired to the kernel under test
and §3.2's five zeroes are not vacuous.

**A finding worth carrying forward.** Destroying ~74% of this kernel's output
rows flipped only **1–2 tokens out of 96**. A short teacher-forced greedy parity
run is a *weak* detector for this kernel: the routed contribution is small
relative to the shared expert and the residual stream, and greedy argmax absorbs
most of the perturbation. This is exactly why the assignment demanded a fault
control, and it is why the real parity evidence for this experiment is stage 1's
checksum over every timed slot (36 slots × 250 steps = 9,000 teacher-forced
tokens per arm, 54,000 in total), not the 96-step probe. Any future experiment
on this site should not treat a clean 96-step parity run as strong evidence.

## 4. Stage 1 — rotated-palindrome full-decode timing

Design (rule 40/68/86): one binary, six arms, `DESIGN=rotate` so every rep is a
rotated palindrome of 12 slots (2 × 6 arms), `STEPS=250` teacher-forced decode
steps per slot, `REPS=18` = three complete rotation cycles, no warm-up reps
discarded, thermal gate honoured between slots. Driver
`research/maple-frieren-r103a-abba.sh` (rule 58: reused, not rebuilt),
analyzer `research/maple-frieren-r103a-analyze-multi.py`.

```text
arms = base:new                                    (shipped path, selector unset)
       null1:new:DARKBLOOM_ROUTED_GATEUP_SG=1      (rejected value -> shipped path)
       sg2 :new:DARKBLOOM_ROUTED_GATEUP_SG=2       (selector on, S unchanged)
       sg4 :new:DARKBLOOM_ROUTED_GATEUP_SG=4
       sg8 :new:DARKBLOOM_ROUTED_GATEUP_SG=8
       sg16:new:DARKBLOOM_ROUTED_GATEUP_SG=16
QC: 0 slots rejected, 0 reps voided; 216 timed slots, 54,000 timed steps
rule 75: digest 9f22da52...b7526b identical before and after the timed run
head = 81e57aa7 (pre-rebase sha of this branch; Sources/Vendor identical to the
       post-rebase tree, the advisor-tip delta being docs plus one default-inert
       env gate in Vendor/.../quantized.cpp)
```

**Base-advance hygiene (`3241e5e5` → `4e9a8e16`, advisor comment
`5241331019`).** The single Sources/Vendor hunk in that advance is alphonse's
`c768d21f` `darkbloom_expert_down_bn()` gate, which returns the pre-existing 64
when `DARKBLOOM_EXPERT_DOWN_BN` is unset, so the dispatch is byte-identical at
the default and no arm here is re-baselined. Three things were checked rather
than assumed: the rebase happened between whole ABBA sequences and never inside
one (rule 97.0); **no arm in any stage of this report sets
`DARKBLOOM_EXPERT_DOWN_BN`**, so the separately measured −0.195 % lever cannot
hide inside a paired mean; and no binary was carried across the rebase — the
stage-A snapshots were rebuilt from the post-rebase tree, which changed a Vendor
translation unit.

**The measurement instrument, and why it is in-situ (advisor's `--local-iterate`
ask).** Every slot in this report is timed by `research/decode_probe.py`, which
is *not* a kernel-local microbenchmark. It launches the same
`.build-worker/release/mlxfast-runtime-worker` binary that `./benchmark.sh
--local-iterate` launches, over the same line-delimited JSON protocol, and
issues the same request shapes as the scored decode axis: one `decode_begin`
with the 512-token golden seed, then N one-token `decode_step` requests, each
timed on the driver's own wall clock. Every step therefore pays the full scored
forward pass — all 40 layers, the complete routed MoE, KV growth, and command
buffer submission — which is exactly the property PR #543 §I found missing in
kernel-local probes (a 14 % probe gain that became −25.5 µs/tok in situ), and
exactly the property rule 98.9's ~30× kernel-local inflation warns about. Three
deliberate differences from `--local-iterate` remain, and none of them favours a
particular arm: 250 steps per slot instead of 128, so each slot's mean has ~2×
less step noise; teacher forcing from the public golden case, which is what makes
the bit-exactness check per slot possible at all; and no scoring wrapper, because
the wrapper's own baseline pairing would replace the position-matched palindrome
design with a single unmatched A/B. At ~44.5 s per slot (~42.5 s of it model
load) the palindrome is affordable at K = 16–18 reps; a `--local-iterate` pair
per slot is not, and it is the pairing — not the wrapper — that removes the drift
these effects live under. Absolute µs/step here are consequently *not*
comparable to a `--local-iterate` score line; only the paired contrasts are, and
only those are quoted.

All quantities in this section are **[M4-WALL] Apple M4 Pro** wall time at epoch
**`base_sha` `3241e5e5`** (`Sources`/`Vendor` identical to `4e9a8e16`; see the
head note above). Rule 105.6: no number below is quoted without those two tags.

Rule-105 conversion used throughout: `Δ%cs = Δ_M4[µs/step] × k × 0.015228`, where
`0.015228 %cs` per **M5** µs/step is the campaign price (fitted on official M5
receipt `59bd72a3`, `cand_dec` = 4.925 ms/step, i.e. 1 %`cs` = 65.67 M5 µs/step)
and `k` is the M4→M5 transfer factor for the family's regime. The routed gate+up
family (T2c) has no measured regime verdict yet — tanjiro's #648 census owns that
— so the table quotes `k = α = 0.4369` (bytes regime) as the primary and the
whole admissible band `k ∈ {0.389, 0.4369, 0.5}` is carried in the readings.
Per rule 105 the regime is **not** read off §B.0.3, whose M5 entries are derived
from M4 by α/β and are therefore circular.

Per-arm level (median statistic, mean over 18 reps, µs/step, [M4-WALL]):

| arm | level | sd(rep) |
| --- | --- | --- |
| base | 8235.4 | 13.3 |
| null1 | 8232.4 | 13.5 |
| sg2 | 8232.3 | 8.9 |
| sg4 | 8237.6 | 12.5 |
| sg8 | 8240.5 | 6.0 |
| sg16 | 8298.8 | 7.1 |

Drift-cancelled paired contrasts (later − earlier, µs/step, K = 18):

| contrast | mean | 95 % hw | lo | hi | sign +/− | %`cs` (α = 0.4369) |
| --- | --- | --- | --- | --- | --- | --- |
| base→null1 | −2.91 | 9.80 | −12.72 | +6.89 | 9/9 | −0.019 |
| base→sg2 | −3.03 | 8.64 | −11.66 | +5.61 | 9/9 | −0.020 |
| base→sg4 | +2.22 | 8.67 | −6.46 | +10.89 | 11/7 | +0.015 |
| base→sg8 | +5.15 | 7.64 | −2.49 | +12.79 | 15/3 | +0.034 |
| **base→sg16** | **+63.49** | **7.83** | **+55.66** | **+71.32** | **18/0** | **+0.422** |
| sg2→sg4 | +5.24 | 5.87 | −0.63 | +11.12 | 14/4 | +0.035 |
| sg2→sg8 | +8.18 | 4.97 | +3.21 | +13.15 | 15/3 | +0.054 |
| sg4→sg8 | +2.94 | 6.17 | −3.24 | +9.11 | 15/3 | +0.020 |

The final column is the rule-105 conversion at `k = α = 0.4369`; at the band
extremes every entry scales by ×0.890 (α = 0.389) or ×1.144 (β = 0.5), which
changes no sign and no conclusion here.

Positive is slower. Cycle-blocked (K = 3) half-widths for the same point
estimates are 11.9–22.1 µs, and dropping the first rotation cycle (K = 12) moves
every estimate by less than its own half-width (`base→sg8` +5.15 → +3.18,
`base→sg16` +63.49 → +60.89). The trimmed-mean statistic reproduces the same
ordering and the same sign pattern.

Three readings, all preregistered:

1. **The machinery is free.** `base→null1` (identical execution, different
   environment) is −2.91 [−12.72, +6.89] and `base→sg2` (selector on, same S,
   different pipeline *name*) is −3.03 [−11.66, +5.61]. Both straddle zero with
   9/18 signs. The `_sgN` name separation and the extra lazy static cost
   nothing measurable, so every S≠2 contrast below is attributable to geometry
   rather than to the selector.
2. **`N-SITE1`: the shipped S = 2 is at or inside the optimum.** No candidate S
   is faster. The ordering is monotone in S (sg2 < sg4 < sg8 ≪ sg16) and the
   two candidate arms are bounded tightly: this design excludes any
   |base→sg4| > 18.4 µs/step and any |base→sg8| > 17.1 µs/step on M4 Pro, i.e.
   ±0.122 % and ±0.114 % of `cs` at α = 0.4369 (±0.140 %/±0.130 % at the most
   generous β = 0.5). Under a Bonferroni correction across all 15 pairwise
   contrasts, no pair differs by more than 27.0 µs = 0.180 %`cs`. Against the
   **corrected rule-105 bar** — 0.4 %`cs` is **60.1** M4 µs/step at α = 0.4369,
   **67.5** at α = 0.389, **52.5** at β = 0.5 — the site is excluded by a factor
   of three to four in every regime. The most favourable reading of the
   `base→sg8` interval is a 2.5 µs/step gain = 0.017 %`cs`, one twenty-fourth of
   the bar; the point estimate is on the slow side. Note that the earlier
   "26 µs/step bar" used in this report's first draft was the M5 figure applied
   to M4 measurements (the rule-105 unit error); correcting it makes the routed
   verdict *stronger*, not weaker, because the bar moves further away.
3. **PR #48's collapse penalty reproduces here, and it is not site-specific.**
   `base→sg16` is +63.5 µs/step [M4-WALL] = **+0.422 %`cs`** at α = 0.4369
   (+0.376 % at α = 0.389, +0.484 % at β = 0.5) with 18/18 slower signs — the
   largest clean single-knob regression measured in this arm, and the only
   contrast at this site that reaches the 0.4 % bar, in the wrong direction. It
   is the same direction as, and about 2.8× the size of, the −0.1488 % official
   receipt `285f79fa` charged to #48's 8× collapse (#48 collapsed 8×, this arm
   collapses 8× from a starting point already four times sparser in
   threadgroups per core).
   The mechanism is visible in the stage-0 ledger: total simdgroups and
   rows-per-simdgroup are invariant, only threadgroup count changes, so
   collapsing threadgroups can only lose — it removes independent scheduling
   units from a kernel that is already issue-bound (maple-alphonse measured this
   kernel at 114.2 GB/s = 42.9 % of M4 Pro peak, PR #630). At S = 16 the routed
   site keeps just 256 threadgroups = 12.8 per GPU core on this host, and the
   tail of a 256-threadgroup dispatch is no longer hidden. §4a tests that
   tail reading against the alternative and rejects it.

### 4a Mechanism diagnostic — the `sg16` penalty is a stationary level shift with no dispersion inflation

§5.2a pre-registered two competing explanations for a collapse penalty and gave
them different observable signatures. This subsection runs that test on the
stage-1 data at zero extra GPU cost
(`research/maple-edward-r107a-stationarity.py`). Each test-arm slot is
differenced against the mean of its own rep's `base` slots at the same step
index, which cancels rep-level drift; the 249 timed steps are then split into
five blocks of 49.

| contrast | all-block mean [M4-WALL] | 95 % hw | block-mean spread | per-slot sd ratio (median) |
| --- | --- | --- | --- | --- |
| `base -> sg2` (identical code) | −1.58 | 6.79 | 6.87 | 0.964 |
| `base -> sg4` | +5.18 | 8.00 | 11.17 | 0.981 |
| `base -> sg8` | +9.20 | 8.12 | 9.54 | 1.061 |
| `base -> sg16` | **+64.33** | 5.95 | **6.48** | **0.986** |

Two readings, both against the tail hypothesis.

- **The penalty is stationary.** `sg16`'s spread across the five step blocks is
  6.48 µs against a 64.33 µs level — and the identical-code `base -> sg2` null
  produces a 6.87 µs block spread of its own, so `sg16`'s spread is entirely
  block-level measurement noise. The penalty is a flat shift present in every
  part of the run, not a ramp, a warm-up artefact, or a bimodal stall.
- **The penalty does not widen the per-step distribution.** The median-over-slots
  per-step sd is 38.4 µs at `sg16` against 38.9 µs at `base`, a ratio of 0.986,
  and every arm sits in 0.96–1.06. (Means over slots are useless here: they run
  1.08–1.57 because per-slot sd is heavy-tailed — the worst single slot in the
  study has sd 643 µs against a median of 41 µs — which is why the QC p99 filter
  exists and why the median is the right aggregate.)

§5.2a's residency/packing-quantization signature is "uniform shift, unchanged
variance"; its tail/load-imbalance signature is "inflated per-step spread". The
data match the first and not the second, so the pre-registered falsifier fires
against tail imbalance at this site. The residual caveat is honest: a tail whose
cost is identical on every step — every dispatch losing the same fraction of a
wave — is not separable from quantization by this test, and per-dispatch
attribution needs the in-situ profiler (`PROFILE=1 SPLIT=1`), which is not free.

This matters beyond bookkeeping. §5.2a notes that on the ranked M5 Max's 40 cores
every threadgroups-per-core figure halves, which roughly doubles a tail cost but
leaves a quantization cost unchanged. Reading the routed cliff as quantization
therefore predicts the same ≈+0.42 %`cs` penalty on M5, where reading it as tail
would predict roughly double. Either way it is a regression, so the routed
`N-SITE1` verdict does not depend on which reading is right; but any future
threadgroup-geometry arm on this programme should carry this diagnostic, because
it is the cheapest available discriminator for ranked-host transfer risk.

## 5. Stage A — the decode QKV lane-major width flip ("L3")

The advisor's top-priority ask (PR #629 comment 5239585381) was not the routed
curve at all: it was to settle the shelved `L3` arm, the one-token flip
`num_simdgroups 2 -> 8` in the decode QKV lane-major NVFP4 kernel that PR #308
priced at **-36.9 us/step, CI [-61.0, -12.9]** and that was then shelved by
analogy with PR #48's 8x threadgroup collapse (official receipt `285f79fa`,
-0.1488 %). Stage A measures it.

The control is a second selector in the same file, `DARKBLOOM_QKV_LM_SG` in
{2,4,8,16}, built exactly like the routed one: unset or any rejected value
leaves the shipped dispatch and the shipped pipeline name untouched, an accepted
value renders the kernel with `constexpr uint num_simdgroups = S`, compiles it
under a distinct `_sgS` pipeline name and dispatches `threadGroup = 32*S`. Grid
threads are unchanged at every S; only the threadgroup partition moves.

### 5.0 Correction: PR #48 is the SAME site, and the M4 result is already replicated

My PR body and my own §1 both treated PR #48 as a *different* kernel, so that
shelving `L3` rested on an analogy. **That is wrong, and it is the most important
correction in this report.** Reading `research/maple-nezuko-pr48-deconfound.md`
(PR #298, the six-arm deconfound of PR #48) settles it:

- PR #48's geometry confound was *this* kernel. `:30-32` names the live scored
  site as `decode nvfp4 qkv r1 h48/h64 lane-major` — the site of §5.1 — and
  `:20-22` describes the confound as "hardcoded 512 threads / 16 simdgroups per
  threadgroup in the QKV kernel, an **8x reduction in threadgroup count**". In my
  parameterisation that is exactly `DARKBLOOM_QKV_LM_SG=16`: 5120/4096 TGs of 64
  threads becomes 640/512 TGs of 512 threads (§5.1's ledger).
- nezuko already isolated the geometry term on an M4 Pro. Arm `G` (sg 16, fold
  held out) against arm `0` (stock sg 2) is **`G-0 = -35.4 us/step`, t = -2.61,
  95 % CI [-62.8, -8.0]** (`:180`, trimmed fixed-effects, se 13.6 us, 39 df).
- So PR #308's `-36.9 us/step` [-61.0, -12.9] at S=8 and PR #298's
  `-35.4 us/step` [-62.8, -8.0] at S=16 are **two independent M4 measurements of
  the same effect on the same site, agreeing to 1.5 us/step**, from different
  students, different designs, and different bases. In %`cs` at k = 0.4369 they
  are -0.246 % and -0.236 % [M4-WALL].
- The knob nezuko built, `DARKBLOOM_DECODE_NVFP4_QKV_R1_SIMDGROUPS`, does **not
  exist on this base** (`grep -rn DECODE_NVFP4_QKV_R1_SIMDGROUPS Sources/ Vendor/`
  returns nothing). `DARKBLOOM_QKV_LM_SG` is therefore an independent
  reimplementation of the same control on a newer base, not a rediscovery of a
  live knob.

This changes what Stage A is for. It is no longer the first measurement of `L3`;
it is the **third**, and its job is to be the tightest and the only one that is
position-matched and drift-cancelled (K = 16 rotated palindrome, half-width ~8 us
against nezuko's se 13.6 us). It also changes the shelving argument: `L3` was not
shelved by analogy, it was shelved by a **real same-site M5 receipt**. §6.2 has
to deal with that receipt honestly rather than dismiss it, and the decomposition
below is what makes that possible.

**What the `285f79fa` receipt can and cannot say.** PR #48 moved three things at
once, and nezuko's M4 decomposition closes exactly
(`:190-196`): `N-0 = (G-0) + (R-G) + (N-R) = -35.4 + 80.4 - 100.0 = -55.0`. So on
M4 the shipped candidate was a -55.0 us/step win built from a -35.4 geometry
term, a **+80.4** redundant-reduction penalty, and a **-100.0** dispatch/barrier
refund. The M5 measured that composite at -0.1488 %, i.e. about **+9.8 M5
us/step slower** at the campaign price. Three terms, one scalar: the receipt is
consistent with the geometry term reversing on M5, *or* with the +80.4 redundant
reduction transferring at more than 1:1 while the -100.0 dispatch refund
transfers at less, *or* any mixture. **The geometry term alone has never had an
M5 receipt** (`:279` says so outright: "the term this study measures as
`G-0 = -35.4` may be positive on M5"). Quoting -0.1488 % as the price of geometry
is a confounded read, and the implied composite transfer factor
`+9.8 / -55.0 = -0.18` is a property of the mixture, not of this lever.

**The sharper prior is a different receipt.** Submission `27b9c7c6` restructured
the fused decode attention kernel to 4 outputs per simdgroup with the grid
divided by 4 — a clean **4x threadgroup collapse with no other change**. It
measured **+7.32 % decode on M4** and came back from the M5 at **approximately
0.0 %**, with every correctness gate passing; it was rejected on ranking only
(`research/tanjiro-m5-calibration-note-B.md:208-211`). That is an unconfounded
geometry gain that **completely failed to transfer**. The same note reports the
mechanism directly: a standalone occupancy scan that times a fixed kernel at
1..48 dispatched threadgroups on this M4 Pro runs "**flat to 20 threadgroups,
risers at 21 and at 41**", identically at 9,216 B and 17,920 B of threadgroup
memory — one 1024-thread threadgroup per GPU core — from which tanjiro concluded
that "changes to bytes-in-flight per thread do appear to transfer; changes to
wave count do not" (`:298-307`). Stage A's job is to find out which of those two
classes `L3` belongs to, and §6.2 answers it with the wave-count arithmetic
rather than with a hope.

### 5.0a The official instrument cannot resolve an effect this size

The two paragraphs above quote `-0.1488 %` from a prose summary. The raw receipt
metrics for both trees are in this checkout, in
`research/artifacts/advisor-r103/replicate-sigma.json`, and recovering them
changes how much weight that number can bear. Both were measured on 2026-08-05:

| receipt | ts (UTC) | `cs` | `D` = decode us/step | `P` |
|---|---|---:|---:|---:|
| control `c3ce66ec` | 09:43:35 | 2.5194549917 | **5046.4443** | 191.30778 |
| PR #48 `285f79fa` | 19:12:03 | 2.5157069444 | **5059.2328** | 190.99471 |

The score decomposition reproduces the published delta to seven digits, which
confirms the column reading: `0.75 * ln(D_ctrl/D_cand) = -0.18982 %` and
`0.25 * ln(P_ctrl/P_cand) = +0.04095 %`, summing to **-0.14887 %** against the
recorded -0.1488 %. So the first M5 microsecond figure for a threadgroup-geometry
change is now on the table: **+12.79 M5 us/step of decode**, a slowdown, against
the M4 composite of -55.0 us/step, a speedup. Composite transfer factor
**-0.2325** - refining, but not changing, the -0.18 estimated from the campaign
price above.

**And it is 0.29 sigma.** Rule 101 measured `sd(ln cs) | fixed tree = 0.3607 %`
from three replicate submissions of one unchanged tree (CRS:6080). Two
independent receipts differ with `sd = 0.3607 * sqrt(2) = 0.5101 %`, so the
observed -0.14887 % is **0.29 standard deviations**. The one M5 datapoint the
record holds against collapsing threadgroups on this exact kernel is
statistically indistinguishable from zero, and equally consistent with a +0.4 %
win or a -0.7 % loss.

Converting that noise floor into the units this arm measures in is the part worth
carrying forward. A decode-only change of size `d` moves the score by
`0.75 * d / D`, so the official instrument's 1 sigma on a *single unreplicated
pair* is

```text
0.5101 % / 0.75 * 5046.44 / 100 = 34.3 M5 us/step of decode
```

That is the same size as the effect. Three consequences, none of them optional:

1. **The `285f79fa` receipt is not a prior against `L3`; it is an absence of
   evidence.** The paragraph above argued the receipt prices a three-way mixture.
   This says something stronger and simpler: even if PR #48 had shipped the
   geometry term alone, one official receipt could not have told a -35 us/step win
   from a +35 us/step loss. Both readings of that submission - "geometry reverses
   on M5" and "geometry transfers and the other two terms swamped it" - are inside
   one sigma of the same number.
2. **This is why the record contains no geometry transfer factor.** §5.0 notes
   that every named M4 -> M5 factor traces back to PR #137's router-weight
   prefetch (-0.40 +/- 0.24). That is not an oversight in the record-keeping. A
   35 us/step effect is a 0.53 %`cs` signal against a 0.51 %`cs` per-pair sigma;
   resolving it at 2 sigma needs **four independent paired M5 receipts**
   (`n >= (2 * 0.5101 / 0.5261)^2 = 3.8`), i.e. eight official runs for one
   number. The prefetch factor exists because its effect was large enough to
   survive the instrument; geometry's is not.
3. **Rule 105.5 is a necessity, not a convenience.** The 0.4 %`cs` graduation bar
   is `0.4 / 0.75 * 5046.44 / 100 = 26.9 M5 us/step`, which is **0.78 sigma of a
   single official pair**. An arm that exactly meets the bar and is then submitted
   alone has close to a coin-flip chance of reading negative on its own receipt.
   The only dispositions that survive this arithmetic are to bundle several
   independently verified bit-exact wins into one submission so the sum clears
   sigma, or to replicate the receipt. Reporting an M4 in-situ paired half-width
   of ~8 us/step, as Stage 1 does at K = 18, is therefore not a weaker instrument
   than the M5 receipt - for effects in the tens of microseconds it is a **four
   times sharper** one, and its weakness is transfer, not resolution.

The consequence for this arm's verdict is in §6.2: an M4-only result of this
magnitude can be neither promoted nor refuted by one M5 probe, so what Stage A can
honestly deliver is a sign, a mechanism class, and a place in a bundle.

### 5.0b The `-36.9` prior is an argmax, so the replication target is `-29.6` (rule 105.10)

The advisor's rule 105.10 (PR #629 comment `5241786283`) removes the last piece of
the prior I was working from, and I adopt it in full: **PR #308 never measured L3
as a pre-specified contrast — it reported the argmax of a sweep.**
`RESEARCH_ARCHIVE_through-round-91.md:1006-1009` records an *interior* argmax at
`S = 8` with `{4, 8, 16}` statistically tied and `S = 32` second-worst. A
maximum over tied arms is biased upward by construction.

The advisor's de-biasing (script `research/advisor_r105_selection_bias.py` on the
advisor branch) uses
`bias = sigma_contrast * sqrt(1 - rho) * E[max of m]`, with
`sigma_contrast = (61.0 - 12.9) / 2 / 1.96 = 12.27 us/step` read off #308's own
reported interval, `rho = 0.5` for the shared `S = 2` reference leg, and
`E[max of 3] = 0.8463`:

| quantity | value |
| --- | --- |
| #308 reported argmax | `-36.9` M4 us/step |
| selection bias | `-7.34` M4 us/step (**19.9 %**) |
| **de-biased replication target** | **`-29.6` M4 us/step** |
| in %`cs`, alpha = 0.4369 | **0.1966 %** |
| in %`cs`, alpha = 0.389 | 0.1751 % |
| sensitivity, m in {2..5} x rho in {0, 0.5} | 0.1506 - 0.2129 % |

Three consequences that bind everything downstream.

1. **Stage A's pre-registered success target is `-29.6`, not `-36.9`.** A Stage-A
   central estimate short of 36.9 but consistent with 29.6 is a *successful*
   replication, not a failure. This is stated here before any Stage-A timing was
   read (§5.2a was committed at 15:28 UTC, this subsection immediately after, with
   the run still at rep 13 of 16).
2. **Stage A's own number is the one that may enter a rule-105.5 bar, and the two
   must not be blended.** Stage A is a single pre-specified contrast on a
   pre-declared arm, so it carries no selection bias; #308's is an argmax and
   carries 19.9 %. Pooling an unbiased estimate with a biased one re-imports the
   bias. The campaign-wide form of this, which I take as binding for every future
   number I report, is: *an argmax-selected effect size may never enter the draw
   bar at its selected value.*
3. **It does not rescue the prior from §5.2a's Consequence 2.** De-biasing shrinks
   the required per-threadgroup price from `5.34 ns` to `29.6 / 6912 = 4.28 ns`,
   still **102x** the `<= 0.042 ns` ceiling that §4's routed null imposes. The
   arithmetic incompatibility between the L3 prior and the measured routed curve
   survives the correction; only a mechanism that is *not* per-threadgroup
   overhead can reconcile them.

Rule 105.10 also settles which of two competing readings of #298-vs-#308 is
right. #298 measured `-35.4` at `S = 16` and #308's argmax was `-36.9` at
`S = 8`. Read naively that is a flat-topped basin from 8 to 16. Read through
105.10, both are draws from a distribution whose sd is `12.27 us/step`, and their
`1.5 us` separation is 0.12 sigma — i.e. the two runs are **uninformative about
the shape of the basin**, which is precisely why the pre-registered `S = 16` arm
of §7.0 is the diagnostic worth buying rather than an extra dose of `S = 8`.



### 5.1 Reachability (rule 39) and the geometry ledger (rule 77)

The site is `lagunaDecodeNVFP4QKVLaneMajorSource`
(`Sources/MLXFastModel/LagunaRuntimeModel.swift:4922`), dispatched from
`lagunaDecodeNVFP4QKVR1` behind `lagunaDecodeNVFP4QKVR1Enabled`
(`DARKBLOOM_DECODE_NVFP4_QKV_R1 != "0"`, default on) and `bank.laneMajorScales`.
Five other `num_simdgroups = 2` literals exist in the file (:3992, :4357, :4843,
:5112, :5293); they belong to other kernels and are untouched.

Reachability is not argued from the source, it is a receipt. The instrumented
build prints one `R107QKVGEOM` line per dispatched head count on the first step
of a real decode (stderr, because `verbose: true` corrupts the worker protocol).
Both head counts appear on every step: 64 heads on sliding-window layers and 48
on full-attention layers, i.e. `rows = (heads + 2*8) * 128` = 10,240 and 8,192.

| S | pipeline suffix | rows h64/h48 | threads/TG | threadgroups h64/h48 | total simdgroups h64/h48 | rows/simdgroup | rows % S |
|---|---|---|---|---|---|---|---|
| unset (shipped) | none | 10240 / 8192 | 64 | 5120 / 4096 | 10240 / 8192 | 1 | 0 |
| 1 (rejected value) | none | 10240 / 8192 | 64 | 5120 / 4096 | 10240 / 8192 | 1 | 0 |
| 2 | `_sg2` | 10240 / 8192 | 64 | 5120 / 4096 | 10240 / 8192 | 1 | 0 |
| 4 | `_sg4` | 10240 / 8192 | 128 | 2560 / 2048 | 10240 / 8192 | 1 | 0 |
| 8 | `_sg8` | 10240 / 8192 | 256 | 1280 / 1024 | 10240 / 8192 | 1 | 0 |
| 16 | `_sg16` | 10240 / 8192 | 512 | 640 / 512 | 10240 / 8192 | 1 | 0 |

Four facts follow, and they are the reason this arm was worth reviving.

1. **`rows % 8 == 0` at both head counts.** 10,240 and 8,192 are both divisible
   by 8, so the flip is *reachable*: it does not fall back, and `L3` cannot be
   closed as `N-L3`-by-guard. That was the cheapest way this arm could have
   died, and it did not.
2. **Total simdgroups and rows-per-simdgroup are invariant.** Exactly as at the
   routed site, S moves only the threadgroup partition. No arithmetic, no
   reduction tree and no memory traffic changes, so the whole effect - either
   sign - is scheduling.
3. **S = 2 renders a byte-identical Metal body.** `metal_src_sha` is
   `12c7a143...29c36e3` for both the shipped path and `_sg2`, while S = 4/8/16
   render `24bf1219...`, `1c987e45...`, `d0aabf77...`. So `base -> sg2` is a
   true mechanism null: distinct pipeline object, extra branch, separate JIT
   library, identical instructions.
4. **The collapse is far gentler here than at the routed site.** This is the
   quantitative reconciliation of #308's positive with #48's negative, and it is
   a *static* argument that transfers to M5 (core counts from the shipped
   hardware, threadgroups from the receipts above):

| site | S | threadgroups | TG per core, M4 Pro (20) | TG per core, M5 Max (40) |
|---|---|---|---|---|
| QKV lane-major h64 | 2 | 5120 | 256 | 128 |
| QKV lane-major h64 | 8 | 1280 | 64 | 32 |
| QKV lane-major h48 | 2 | 4096 | 204.8 | 102.4 |
| QKV lane-major h48 | 8 | 1024 | 51.2 | 25.6 |
| routed gate/up | 2 | 2048 | 102.4 | 51.2 |
| routed gate/up | 8 | 512 | 25.6 | 12.8 |
| routed gate/up | 16 | 256 | 12.8 | 6.4 |

   Read the M4 Pro column, because that is the host that produced section 4's
   numbers. The routed curve was still flat at 51.2 TG/core (S = 4, +2.2 us) and
   at 25.6 TG/core (S = 8, +5.2 us); it broke only at 12.8 TG/core (S = 16,
   +63.5 us). The QKV site at the *candidate* S = 8 has 64 and 51.2 TG/core on
   this host, deep inside the region where collapsing threadgroups cost nothing
   measurable at the routed site. On the ranked M5 the same dispatch is 32 and
   25.6 TG/core, which is where the routed site was still flat.

   With §5.0's correction the whole picture is consistent on one axis. PR #48's
   geometry term is the QKV site at S = 16, which is 32 TG/core (h64) and 25.6
   (h48) on M4 — *inside* the flat region — and it duly measured a **win**,
   `G-0 = -35.4 us/step`. The routed site at S = 16 is 12.8 TG/core, *past* the
   knee, and it duly measured a **loss**, +63.5 us/step. Nothing here says
   collapsing threadgroups is dangerous per se; it says there is a knee on this
   M4 Pro somewhere between 12.8 and 25.6 threadgroups per core, and that every
   QKV arm in Stage A stays well clear of it on both hosts.

5. **Wave-count arithmetic: why this lever is in the transferring class.** The
   dichotomy tanjiro drew from the 1..48 threadgroup scan is that "changes to
   bytes-in-flight per thread do appear to transfer; changes to wave count do
   not" (`tanjiro-m5-calibration-note-B.md:298-307`). Put `L3` on the correct
   side of it. Let `T_r` be the resident threads a core can hold for this kernel
   and `N_r` the resident-threadgroup-per-core cap. Concurrent threadgroups per
   core is `min(N_r, floor(T_r / (32 S)))`, so concurrent *threads* per core is
   `min(32 S N_r, T_r)`, and

   ```text
   waves = grid_threads / (cores * min(32 S N_r, T_r))
   ```

   Grid threads are fixed by construction at every S (327680 for h64, 262144 for
   h48 — see the receipts above). So whenever `N_r` is not the binding term,
   `waves = grid_threads / (cores * T_r)` is **exactly independent of S**, and
   so is its fractional part, on *any* core count. Concretely at `T_r = 1024`
   (the value implied by tanjiro's scan finding one resident 1024-thread
   threadgroup per core) h64 is 16.0 waves at every S on M4 and 8.0 waves at
   every S on M5; h48 is 12.8 and 6.4 waves at every S. Core count divides out
   of every arm identically, so it cannot induce a sign flip between arms.

   This is precisely what separates `L3` from the two geometry changes that
   failed. Submission `27b9c7c6` divided the **grid** by 4 (4 outputs per
   simdgroup), which divides `grid_threads` and therefore the wave count by 4 —
   a wave-count change, the non-transferring class, and it duly went from
   +7.32 % on M4 to ~0.0 % on M5. tanjiro's own 1..48 scan likewise varied
   threadgroup count at *fixed* threadgroup size, i.e. it varied grid threads.
   `L3` and PR #48's arm `G` do the opposite: they hold grid threads and total
   simdgroups fixed and move only the threadgroup boundary (5120 x 64 = 640 x
   512 = 327680). Under this arithmetic the residual S-dependence can only come
   from (i) `N_r` binding at small S, so that S = 2's 64-thread threadgroups
   cannot fill a core with threads while S = 8's 256-thread ones can — an
   *intra-core* effect, invariant to how many cores exist; (ii) per-threadgroup
   launch and scheduling overhead, which scales with threadgroup count, not core
   count; or (iii) locality and coalescing changes inside a wider threadgroup,
   also intra-core. **All three transfer.** That is the static case for M5, and
   it is falsifiable: if Stage A's win is real and mechanism (i) is operative,
   the effect must be concentrated between S = 2 and S = 8 and must saturate
   once `32 S N_r >= T_r`, which is exactly the flat-topped basin PR #308
   reported.

   The honest weakness of this argument is that `N_r` and `T_r` are not measured
   for this kernel on either host — they are inferred from a different kernel's
   scan. If Apple's M5 raised `N_r` (so that even S = 2 fills a core), mechanism
   (i) would vanish on M5 and the win would shrink toward zero. That is a
   *magnitude* risk, not a sign risk: none of (i)-(iii) has a mechanism that
   makes a wider threadgroup slower at fixed grid threads while more than
   25.6 threadgroups per core remain, which the routed sweep confirms
   empirically down to that point. §7 lists the measurement that would close it.

6. **Kernel-structure audit — which mechanisms are structurally absent.** The
   argument above lists three surviving mechanisms; the kernel source lets me
   delete two more candidates outright rather than argue about them.
   `lagunaDecodeNVFP4QKVLaneMajorSource` (`LagunaRuntimeModel.swift:4922`)
   declares no `threadgroup` address-space storage, contains no `barrier` or
   `simdgroup_barrier`, and its only reduction is the intra-simdgroup
   `simd_sum(result)` at the store. Row ownership is
   `out_row = tile * num_simdgroups + simd_gid`. Three consequences:

   - **Bit-exactness is by construction, not by luck.** Every output row is
     still reduced by exactly one simdgroup over the same 32 lanes in the same
     order and the same `values_per_thread = 16` slices; `S` changes only which
     threadgroup that simdgroup is packaged into. There is no path by which a
     partial sum crosses a different boundary. §5.2's four identical checksums
     are the confirmation of that, not the reason for believing it.
   - **Threadgroup-memory pressure is exactly zero at every S.** So the
     mechanism tanjiro's 1..48 scan *did* find transferring — bytes in flight per
     thread, tested at 9,216 B against 17,920 B of threadgroup memory — is not
     the mechanism operating here, and no static threadgroup-memory occupancy
     limit can bind at any S in this sweep.
   - **No cross-simdgroup synchronisation.** The usual reason a wider
     threadgroup *loses* is that it couples stragglers through a barrier and
     delays the whole group's retirement. That cost is absent by construction,
     which is why the shipped 64-thread default has no structural advantage to
     defend here.

   What survives is: per-threadgroup launch and scheduling cost, the
   resident-threadgroup cap `N_r`, and the dispatch tail. Only the last of the
   three is core-count dependent, and it is worth being precise about how it
   maps across hosts. The tail penalty scales roughly as the reciprocal of
   threadgroups per core, so it is a **supply-side** quantity: M5 at S = 8 has
   the same 32 threadgroups per core as M4 at S = 16, and therefore inherits
   M4-at-S = 16's tail profile. `N_r` binding and intra-threadgroup locality are
   **shape-side**: they depend on S itself, which is identical on both machines,
   so M5 at S = 8 inherits M4-at-S = 8's shape profile. Both profiles are
   therefore measurable on this host — which is the argument for adding the
   S = 16 arm (§7), since together the two existing M4 operating points bracket
   the M5 one for both mechanism classes.

### 5.2 Parity and fault control

Ninety-six teacher-forced greedy steps per dose, one dose per process, all from
the same `new` binary:

| probe | S | divergences | token-stream cksum |
|---|---|---|---|
| `parity-base` | unset | 0 | 3157477821 |
| `parity-sg2` | 2 | 0 | 3157477821 |
| `parity-sg4` | 4 | 0 | 3157477821 |
| `parity-sg8` | 8 | 0 | 3157477821 |

One distinct checksum across all four, as required. This is a necessary
condition, not a sufficient one: as at the routed site, a 96-step greedy stream
is a weak detector because argmax absorbs small numerical differences, so the
fault control below is what gives the checksum its meaning.

**Store-row fault control.** The `faultqkv` build compiles the `_sgS` pipeline
from `num_simdgroups = 2` while the host still dispatches `32*S` threads per
threadgroup, so simdgroups 2..S-1 write rows that belong to another lane block.
If the parity check above could not see a genuine mis-mapped store, the whole
Stage-A parity argument would be vacuous.

It is not. `fault-sg8` diverges on **96 of 96** steps, first at
`(row 0, position 509, expert 0)`, and its decode mean drops to 7.741 ms against
~8.22 ms for every healthy dose - the mis-mapped stores are both visible in the
token stream and visible in the timing. The same control at the routed site fired
on only 1 of 96 steps at S = 8 and 2 of 96 at S = 16, so the QKV site's detector
is about two orders of magnitude more sensitive per step. That is the expected
ordering: a bad routed store lands in one expert's contribution to one token,
which the router weight then scales down and argmax usually absorbs, whereas a
bad QKV store corrupts a whole head's projection for every subsequent attention
step. The four clean parity streams at this site are therefore a real result and
not an artefact of a blunt instrument.

### 5.2a Pre-registered mechanism prediction (written before any Stage-A timing was read)

This subsection was committed while the Stage-A timing block was still running and
before any `.steps` file from it had been opened. Only the slot count had been
checked. It exists so that §5.3 cannot be read as a story fitted to whatever
number arrived, and so that a null is as publishable as a win.

**The cross-site arithmetic that constrains every candidate mechanism.** The two
sites differ enormously in how hard they lean on the threadgroup-launch machinery,
and that difference is the lever that turns §4's measured routed curve into a
quantitative prior for this site.

| quantity | routed gate/up (§4, measured) | QKV lane-major (this site) |
| --- | --- | --- |
| threadgroups per dispatch at S = 2 | 2,048 | 5,120 (h64) + 4,096 (h48) |
| dispatches per decode step | 39 | 1 of each head shape |
| threadgroups per decode step at S = 2 | 79,872 | 9,216 |
| family cost per step [M4-WALL] | 1,497.7-1,522 us | 1,340.1 us |
| threadgroup issue demand | ~52 TG/us | ~6.9 TG/us |
| threadgroups removed by S = 2 -> 8 | 59,904 | 6,912 |

The routed site issues threadgroups **7.6x faster** and S = 2 -> 8 retires
**8.7x more** of them there than here. Any mechanism whose cost is *per
threadgroup* must therefore be 8.7x larger at the routed site than here, and §4
measured that site flat.

**Consequence 1 - a hard upper bound on per-threadgroup launch/retire cost.**
Apple states that per-threadgroup dispatch and retirement overhead exists
(WWDC16 606, WWDC22 10159) but has never published a figure for it, and no
public source gives a threadgroup issue rate for any Apple GPU. §4's
`base -> sg8` contrast is `+5.15 us/step`, 95 % CI `[-2.49, +12.79]`, so the
largest *gain* the routed data permits is 2.5 us/step spread over 59,904 retired
threadgroups: **<= 0.042 ns per threadgroup**. Scaling that ceiling by this
site's 6,912 removed threadgroups bounds the launch-amortisation mechanism here
at **<= ~0.3 us/step** - two orders of magnitude below the 52.5-67.5 M4 us/step
graduation bar of §6, and below this study's own resolution.

**Consequence 2 - the -36.9 us/step prior is arithmetically incompatible with
§4.** A -36.9 us/step gain from retiring 6,912 threadgroups requires
**5.34 ns per threadgroup**, i.e. 127x the ceiling above. At that price the
routed site's S = 2 -> 8 contrast would have to read about **-320 us/step**. It
read `+5.15 +/- 7.6`. The two are inconsistent by more than 30 sigma. Unless the
mechanism is something other than per-threadgroup overhead, PR #308's and
PR #298's M4 numbers are best explained as unpaired slot-level drift, exactly as
rule 105.7 warns.

**Mechanisms that could still make a larger threadgroup faster, ranked.**

1. *Per-threadgroup launch and retire amortisation.* Real, undocumented, and
   bounded above at <= ~0.3 us/step here by Consequence 1.
2. *An occupancy floor at small S.* If a core cannot host enough 64-thread
   threadgroups to fill its simdgroup slots, S = 2 -> 4 would buy a step. This
   predicts an equal *relative* step at both sites; §4 saw none, so it is dead.
3. *L1 reuse of the activation vector.* Structurally nil here: `x` is shared by
   every row irrespective of how rows are partitioned across threadgroups, so
   repacking changes no load stream.
4. *Instruction-cache and argument-buffer fetch per threadgroup.* Subsumed by
   mechanism 1's ceiling.
5. *Dispatch ramp fill.* Sub-microsecond at 640-5,120 threadgroups; negligible.

**Mechanisms that could make a larger threadgroup slower, ranked.**

1. *Residency/packing quantization.* Resident simdgroups per core is
   `S * floor(M/S)` for a per-core slot budget `M`. §4's flat 2/4/8 with a
   `+63.49 us/step` cliff at 16 implies `M = 8 (mod 16)`, i.e. `M` in
   {24, 40, 56, 72}, giving 33/20/14/11 % occupancy loss at S = 16; the observed
   `+4.2 %` of family implies a sensitivity of 0.13-0.38x the occupancy loss.
   Public support: Philip Turner's M1 Max sweep
   (`github.com/philipturner/metal-benchmarks`, `CommandConcurrency/MainFile.swift`)
   reports a ~30 % collapse at simdgroups/TG of 7, 9, 14, **16**, 23 and 25 while
   8 and 10-13 are clean. Caveat: Apple9's "dynamic shader core memory"
   (Tech Talk 111375) voids static register-to-occupancy tables, and no
   occupancy or register table has been published for Apple9, M4 or M5.
2. *Tail and load-imbalance coarsening.* Apple says verbatim that "larger
   threadgroups might prevent a more uniform distribution" (WWDC22 10159), and
   the M5 MPP guide 2.3.1 adds dimension quantization. Here S = 16 leaves
   640 TG / 20 cores = 32.0 exactly for h64 but 512/20 = 25.6 for h48.
3. *Register-block admission head-of-line blocking.*
4. *The Apple9 Occupancy Manager* (Tech Talk 111374) - undocumented wildcard.

Both leading slow-mechanisms predict **S = 8 is free** at this site, because both
only bite at S = 16.

**Pre-registered outcome distribution for the S = 8 central estimate at this
site** (expected sd of the contrast ~4.4 M4 us/step at K = 16):

| outcome | probability |
| --- | --- |
| faster by more than 20 us/step | 5 % |
| faster by 5-20 us/step | 15 % |
| within +/- 5 us/step of zero | 55 % |
| slower by more than 5 us/step | 25 % |

Point predictions: `base -> sg8 = +2 +/- 9`, `base -> sg4 = +1 +/- 9` M4
us/step. The modal pre-registered verdict is therefore **`N-L3`**, and the
deliverable under rule 105.7 is the width of the interval, not its sign.

**Falsifiable statements.** If **residency quantization** is the cliff mechanism,
then a QKV `S = 16` arm must slow this family by 3-5 % (`+40` to `+70` us/step)
roughly equally at both head shapes, the routed site's penalty must be uniform
(about `+1.6 us` on each of its 39 dispatches) and appear as a stationary level
shift across all timed steps with unchanged variance. If **tail imbalance** is
the mechanism, the relative penalty scales as `1/(TG per core)`: a QKV `S = 16`
arm must cost `<= ~1 %` (`<= +15 us/step`), concentrated in h48 and near zero in
h64 (whose 640 TGs are exactly 32/core on 20 cores), with inflated per-step
spread. If **per-threadgroup launch overhead** produces any gain `-G` here, the
routed site must show about `-8.7 * G`; the -36.9 prior implies -320 us/step
there and is already falsified.

**Free diagnostics to run on the Stage-A data (no extra GPU time).** Split every
contrast by head shape: a tail mechanism makes h48 show at least 1.25x the
*relative* effect, while a front-end mechanism makes the effect track threadgroup
count so h64 is larger in absolute microseconds. Check that the routed `sg16`
per-step series is a stationary level shift rather than drifting or bimodal.
Express every QKV effect as a percentage of the 1,340.1 us family, not of the
8,240 us step. The best single *paid* diagnostic, if replication budget allows it
later, is a QKV `S = 16` arm (~12 min), which separates quantization
(`+45` to `+70` us/step, shape-independent) from tail (`<= +15`, h48-only).

**Ranked-host transfer note.** On the M5 Max's 40 cores every threadgroup-per-core
figure halves. Quantization is unchanged by that (it depends on `S` and the
per-core slot budget), but the tail mechanism roughly doubles. So the
quantization-versus-tail distinction is not academic: it changes the sign of the
risk this lever carries to the scored host.

### 5.3 Full-decode rotated-palindrome timing

### 5.4 Prefill (rule 17)

**Prefill neutrality is structural, not statistical, and that is the stronger
claim.** `lagunaDecodeNVFP4QKVR1` opens with

```swift
guard normalized.dtype == .bfloat16,
    normalized.dims(1, 1, hidden),        // Sources/.../LagunaRuntimeModel.swift:5035
```

so the function returns `nil` for any input whose sequence length is not 1. The
scored prefill axis presents one 512-token tensor, `normalized.dims(1, 512,
2048)`, the guard fails, and the call site falls through to `quantizedMM`
(`:5995-5997`). `DARKBLOOM_QKV_LM_SG` is read only inside the lane-major kernel
set that this function builds, so **no prefill dispatch can observe the selector
at any value**. nezuko reached the same conclusion for the equivalent knob on an
older base (`maple-nezuko-pr48-deconfound.md:214-216`: "both knobs are
**structurally unreachable** during prefill"), so this is a reproduced property of
the site, not a one-off reading.

Two residual risks are *not* covered by that argument, because they live outside
the guard, and they are what the empirical check below is for: the selector adds a
kernel-set construction and a distinct `_sgS` pipeline name, so a lazily JIT-compiled
library could in principle be paid at a different time, and any such cost would
show up as a prefill regression even though the prefill dispatch is unchanged.

## 6. Verdict against the graduation gate

The advisor's bar for this round is a paired full-decode gain of at least
**0.4 % of `cs`**, with the sign consistent across repetitions. Rule 105
(PR #629 comment `5241594386`) corrected the units in which that bar is
expressed: the campaign price `0.015228 %cs` per µs/step was fitted on an
**official M5** decode, so 0.4 %`cs` = **26.3 M5 µs/step**, and an M4 measurement
must be transferred first:

| regime | `k` | %`cs` per **M4** µs/step | 0.4 % bar in **M4 µs/step** |
| --- | --- | --- | --- |
| bytes, α = 0.4369 | 0.4369 | 0.006653 | **60.1** |
| bytes, α = 0.389 | 0.389 | 0.005924 | **67.5** |
| latency, β = 0.5 | 0.5 | 0.007614 | **52.5** |

Every number below is [M4-WALL] on Apple M4 Pro at epoch `base_sha` `3241e5e5`
(`Sources`/`Vendor` ≡ `4e9a8e16`) and is quoted in both units, with the `k` used
stated explicitly (rule 105.6). The regime for each family is a measured
property, not a §B.0.3 lookup; where it is not yet settled the whole `k` band is
carried.

Rule 105.5 additionally allows the 0.4 % bar to be met by the **sum** of
independently verified, bit-exact improvements in **different** families, each
with a CI excluding zero. That is why §5 exists: the routed gate+up site is
family **T2c** (M4 cost 1497.7 µs/step) and the QKV lane-major site is family
**T0b(a)** (M4 cost 1340.1 µs/step), so a win at either is a summation
component rather than a standalone submission.

### 6.1 Routed gate/up site — `N-SITE1`

The routed threadgroup-packing knob is settled and it is a null-to-negative
curve, in the preregistered `N-SITE1` sense:

- No candidate S is negative at all. The two candidate doses come back
  `base -> sg4 = +2.2 us [-6.5, +10.9]` and `base -> sg8 = +5.2 us [-2.5,
  +12.8]`; the point estimates have the wrong sign and both confidence
  intervals exclude anything better than **-18.4 us** and **-17.1 us**
  respectively, i.e. better than **-0.122 %`cs`** and **-0.114 %`cs`** at
  α = 0.4369 (-0.140 %/-0.130 % at the most generous β = 0.5). The bar - 52.5
  to 67.5 M4 us/step depending on regime - is excluded at both doses by a factor
  of three or more, and a Bonferroni correction across all 15 contrasts still
  excludes any pair separation above 27.0 us = 0.180 %`cs`.
- The two nulls behave. `base -> null1` (identical execution) is
  `-2.9 us [-12.7, +6.9]` and the byte-identical-body mechanism null
  `base -> sg2` is `-3.0 us [-11.7, +5.6]`, so the machinery itself - distinct
  pipeline object, extra branch, separate JIT library - is free, and the
  measurement is not being flattered by it.
- The negative controls fire hard and in the predicted direction:
  `base -> sg16 = +63.5 us [+55.7, +71.3]`, 18/18 repetitions slower,
  **+0.422 %`cs`** at α = 0.4369. That single arm is the size of the whole
  graduation bar with the sign reversed, which is the cleanest available proof
  that the instrument has the resolution and the sign discipline to detect a
  bar-sized effect. It simply is not there for S in {4, 8}.
- **Independent corroboration on the same kernel.** maple-alphonse's R107-B
  rung measured `lagunaRoutedSwiGLUQMVPackedTop8R1Kernel` kernel-locally at the
  shipped geometry and, with residency defeated per rule 98.9
  (`FERN_DEFEAT_SLOTS=64`), reports **-0.038 % [-0.104, +0.028]** for his
  no-op arm. My `base -> null1` full-decode null, a completely different
  instrument on the same kernel, is `-2.9 us/step [-12.7, +6.9]` on a
  1497.7 µs/step family, i.e. **-0.19 % [-0.85, +0.46]** of family cost. The two
  nulls agree on zero, and his tighter interval is the reason the resident-rung
  number he first saw (**+1.224 %**, ~30x inflated) must never be quoted alone.
- **The rule-100 risk to this arm is already spent, not pending.** The advisor's
  caveat is that T2c could be at an instruction-issue ceiling the two-pool map
  does not draw, and that if tanjiro's #648 census returns ISSUE for T2c the
  right move is to stop before a long packing sweep and write the null. The
  sweep is finished and the null is written: whatever regime #648 assigns T2c,
  the measured answer here does not change, and an ISSUE verdict would simply
  supply the mechanism for a result that is already on the page. That reading is
  also the one the data prefers - alphonse's 114.2 GB/s = 42.9 % of this host's
  bandwidth peak on this exact kernel is what an issue-bound kernel looks like,
  and it is why *removing* scheduling units (S = 16) hurts while merging them
  (S = 4, 8) buys nothing.

The mechanism reading is the useful part. Stage 0 shows total simdgroups and
rows-per-simdgroup are invariant in S, so packing can only ever *remove*
independent scheduling units from a kernel maple-alphonse measured at 42.9 % of
this host's bandwidth peak (PR #630) - i.e. issue-bound, not
occupancy-starved. On such a kernel wider threadgroups buy nothing until they
start costing tail latency, which is exactly the flat-then-cliff shape measured.
**Recommendation: do not spend M5 time on routed-site threadgroup packing.**

### 6.2 QKV lane-major site — see 5.3

## 7. Suggested follow-ups (not implemented)

### 7.0 Directly implied by this arm

Ranked by information per unit of host time. All four are cheap and none of them
needs an M5.

1. **Run the QKV S = 16 arm.** This is the single highest-value missing cell and
   it costs one short block: `SG_LIST="16"` with the existing Stage-A driver is
   three arms (base, `null1`, sg16), six slots per rep at ~45 s, so K = 12 is
   under an hour. It buys two things at once. (a) It directly replicates PR
   #298's arm `G-0` (-35.4 us/step, CI [-62.8, -8.0]), which was measured at
   S = 16 on this same kernel on an M4 - so a matching Stage-A S = 16 contrast
   would turn "two independent M4 replications" into a third under a design with
   the paired drift-cancelling structure neither predecessor used. (b) Per §5.1
   point 6, M4 at S = 16 is the *supply-side* stand-in for M5 at S = 8: both are
   32 threadgroups per core. The decision rule is worth stating in advance:
   S = 16 no worse than base means the tail/supply risk for M5 at S = 8 is
   bounded by measurement rather than by argument; S = 16 regressing means the
   win is supply-fragile and no S should be promoted to M5 without an M5 probe.
2. **Measure `N_r` and `T_r` for this pipeline.** §5.1 point 5's wave-count
   argument turns on a resident-threadgroup cap that is currently *inferred*
   from a different kernel's scan. `MTLComputePipelineState` exposes
   `maxTotalThreadsPerThreadgroup`, `threadExecutionWidth` and
   `staticThreadgroupMemoryLength`; logging those three per `_sgS` pipeline is
   minutes of work if the MLX kernel wrapper can be made to surface the pipeline
   object. Expected reading is 1024 / 32 / 0 at every S, which would confirm that
   register pressure and threadgroup memory are not the S-dependent term and
   leave launch cost and `N_r` as the only live mechanisms.
3. **Row-count contrast as an M5 occupancy emulator.** Re-run the paired S sweep
   against a half-height dummy weight (a pure timing probe, off the scored
   surface): 2560/1280/640/320 threadgroups reproduces M5's 128/64/32/16
   threadgroups per core exactly. If the win halves, the mechanism is per-core
   launch cost and M5 should see roughly half the microseconds; if it is
   unchanged, the cost is global and transfers near 1:1; if the argmax moves to
   S = 4, the site is supply-limited and M5's optimum is below S = 8. This is the
   sharpest M5 emulation available without an M5.
4. **Decide, at programme level, whether a 30 us/step lever is submittable at
   all.** This one is for the advisor, not for a student host. §5.0a shows the
   official instrument's 1 sigma on an unreplicated pair is 34 M5 us/step of
   decode, so the rule-105 bar sits at 0.78 sigma and an arm at the bar has close
   to a coin-flip chance of reading negative on its own receipt. Two coherent
   responses exist and they cost very different amounts: bundle four to six
   verified bit-exact levers from different families into one submission so the
   sum clears sigma (rule 105.5, cheap, but a single negative receipt then
   condemns the whole bundle), or spend four paired receipts on one lever to
   resolve it at 2 sigma (eight official runs, definitive, and it produces the
   geometry transfer factor the record has never had). Choosing implicitly is the
   expensive option, because it spends receipts on questions they cannot answer.
   The archive lead that motivated this item is closed: the raw metrics were
   already in `research/artifacts/advisor-r103/replicate-sigma.json` and are now
   tabulated in §5.0a, so nobody needs to re-mine
   `RESEARCH_ARCHIVE_through-round-91.md` for them.

### 7.1 Record-mined leads for the wider programme

Produced by a read-only mining pass over `research/CURRENT_RESEARCH_STATE.md`
(CRS), `research/RESEARCH_ARCHIVE_through-round-91.md` (ARCH) and
`research/advisor-r105-the-routed-gather-gemm-is-memory-bound.md` (R105). None
of it was built or measured here; the estimates are the record's own pricing,
not my receipts. Ranked by expected score per unit of engineering risk.

1. **lm_head int3 approximate scan + exact BF16 refine.** The one carved-out
   survivor of the closed byte families (CRS:3306-3308). Replace the 4-bit
   level-1 nibble plane in `LagunaLmHeadPrune.swift:240-275` with 3-bit codes
   plus a certified per-row upper bound, sending survivors to the existing
   exact BF16 level-2 refine. 100,352 rows x 256 B = 25.69 MB/step = 1.54% of
   `B`; break-even survivor growth is +6,272 rows, so a 4-20x survivor
   inflation still nets **+0.38-0.61% score**. Exactness is preserved by
   construction because the refine is exact and the tie comparator is
   unchanged. Cheapest falsifier is a **pure-CPU desk screen** from
   `Sources/MLXFastTransform` measuring bound width and survivor-count
   distribution: zero GPU, zero receipts. This is the highest-value next step
   and the only remaining >=0.5%-class removable decode byte block.
2. **Rule-68 re-verification of prefill QKV fusion on `_nax`.** Explicitly
   suspended rather than settled (CRS:3028-3031): the +0.639 ms falsification
   predates the unconditional `_nax` swap (`matmul.cpp:957-1026`). Resurrect
   the #527 patch and run one paired M5 prefill probe. Small (**+0.22%**) but
   nearly free and record-sanctioned.
3. **Gather-GEMM A-operand re-read elimination at constant `Ws_storage`.** A
   permitted descendant of #592's closure wording: have each threadgroup in
   `fp_gather_qmm_rhs_expert_nax` serially own two N-tiles so one loaded A
   k-slice feeds both accumulators. The doubling lands in C-fragment
   *registers*, not the `Ws_storage` that #592 identified as the cause of its
   +1.166 ms negative. Prize is up to 8.76 ms of the 43.26 ms gather wall
   (**+0.5-3.3% score**, the largest ceiling on the board) and it is bit-exact
   because per-output k-accumulation order is unchanged. Medium risk: this is
   the same register/occupancy family that produced #592's hard negative, and
   it is M5-only since `_nax` is unreachable on M4. Falsify for free first by
   reading #625's census for whether DRAM actually sees those A re-reads, then
   a compile-only register report, and only then an M5 probe.
4. **Hoist shape-static prefill glue into input-independent caches.** #619
   showed binding overstates traversal 11.5x, which leaves #270's "glue at 99%
   of the DRAM floor" unadjudicated for prefill. Masks, params arrays, and
   aranges are explicitly cacheable under the serial rules. Unpriced until
   #625/#620 land; gate on their ratio tables to avoid overlapping #620.
5. **Split-K attention with a fused cross-slice reduction.** Gross Fill
   recovery is 92.0 us = +1.41%, but it is the only proposal here that breaks
   bit-exactness (softmax recombination), so it carries full
   upstream-equivalence and M5 near-tie argmax risk. Measure the
   intercept-versus-slice-count curve with the existing extracted-kernel
   harness first and build only if >30 us survives.

Enabler, not a hypothesis: `editablePaths` lists directories, so the per-file
cap can be relieved by splitting `LagunaRuntimeModel.swift`; roughly 100.5 kB
of global headroom remains (CRS:2924-2928).

## 8. Artefacts and reproduction

Submitted surface (the only scored file this arm touches):

- `Sources/MLXFastModel/LagunaRuntimeModel.swift` — two independent, default-inert
  selectors. `DARKBLOOM_ROUTED_GATEUP_SG` (routed gate/up packed top-8 R1 QMV)
  and `DARKBLOOM_QKV_LM_SG` (decode QKV lane-major R1). Unset or a rejected
  value leaves the shipped dispatch, the shipped pipeline name and the shipped
  rendered Metal body bit-identical; no other file in `editablePaths` is touched.

Research-only support (not part of any submission):

- `research/maple-edward-r107a-build.sh` — worker-only release build into a
  snapshot directory, copying both `mlxfast-runtime-worker` and `mlx.metallib`.
- `research/maple-edward-r107a-patch.py` — instrumentation applier:
  `geom`/`geomqkv` emit the one-shot `R107GEOM`/`R107QKVGEOM` dispatch receipts
  plus a Metal-source dump on stderr; `fault`/`faultqkv` are the deliberately
  wrong builds used as detector controls.
- `research/maple-edward-r107a-stage0.sh` — `SITE=routed|qkv` stage 0: build the
  three snapshots, restore the tree (rule-75 digest), emit geometry receipts,
  run 96-step greedy parity per dose, run the fault control.
- `research/maple-edward-r107a-stage1.sh` — rotated-palindrome full-decode
  timing driver, parameterised by `SEL_VAR` and `SG_LIST`, plus the
  drop-one-cycle sensitivity pass.
- `research/maple-edward-r107a-prefill.sh` — paired 512-token prefill probe,
  accepting several named arms so both selectors are controlled in one session.
- `research/maple-edward-r107a-pool.py` — rule-105.7 replication support: merges
  independent timing blocks into one directory the multi-arm analyser reads as a
  single rotation experiment, refusing to pool blocks that disagree on arms,
  steps, design, host, the rule-75 digest or any worker binary hash.
- `research/maple-edward-r107a-wandb.py` — `SITE=routed|qkv` publisher; it only
  reads the analyzer's JSON and the stage-0 receipts, and recomputes nothing.
- Reused unchanged from earlier rounds: `research/maple-frieren-r103a-abba.sh`
  (position-matched slot harness, dirty-tree refusal, `ASSERT_SAME` /
  `ASSERT_DIFFER`, rule-75 digest, token checksums),
  `research/maple-frieren-r103a-analyze-multi.py` (cycle-blocked and
  per-repetition contrasts, exclusion bounds, rule-79 null cells),
  `research/decode_probe.py`, `research/prefill_probe.py`.

Reproduction, in the order it was run:

```bash
# stage 0 / stage A geometry, parity and fault controls
SITE=routed SNAP=/tmp/maple-r107a-snap OUT=/tmp/maple-r107a/stage0 \
  bash research/maple-edward-r107a-stage0.sh full
SITE=qkv SNAP=/tmp/maple-r107a-snapq OUT=/tmp/maple-r107a/stage0q \
  GEOM_SG_LIST='1 2 4 8 16' PARITY_SG_LIST='2 4 8' FAULT_SG_LIST='8' \
  bash research/maple-edward-r107a-stage0.sh full

# timing
SNAP=/tmp/maple-r107a-snap OUT=/tmp/maple-r107a/stage1 REPS=18 STEPS=250 \
  bash research/maple-edward-r107a-stage1.sh
SEL_VAR=DARKBLOOM_QKV_LM_SG SG_LIST='4 8' SNAP=/tmp/maple-r107a-snapq \
  OUT=/tmp/maple-r107a/stageA REPS=16 STEPS=250 \
  bash research/maple-edward-r107a-stage1.sh
SEL_VAR=DARKBLOOM_QKV_LM_SG SNAP=/tmp/maple-r107a-snapq \
  OUT=/tmp/maple-r107a/prefillA REPS=6 \
  bash research/maple-edward-r107a-prefill.sh 0 8

# publication
SITE=routed python3 research/maple-edward-r107a-wandb.py \
  /tmp/maple-r107a/stage1 /tmp/maple-r107a/stage0
SITE=qkv python3 research/maple-edward-r107a-wandb.py \
  /tmp/maple-r107a/stageA /tmp/maple-r107a/stage0q
```

On-disk evidence kept under `/tmp/maple-r107a/`: `index.tsv` (slot order and arm
assignment), one `.steps` file per slot with per-step microseconds, one `.log`
and `.tokens` per probe, `provenance.txt` (reps, steps, rule-75 digests before
and after), `analysis.txt` / `analysis-multi.json` and the
`…-drop1cycle/analysis.txt` sensitivity pass. Every number quoted in this
document is in one of those files; nothing was recomputed by hand.

## 9. Hand-off to fern (#625)

### 9.1 Rule-75 tree digests

Every stage restored the tree to the commit it started from, and both timed
stages assert it. The two digests differ only because the QKV selector was
committed between them; each is self-consistent before and after.

| stage | head at run time | `digest_before` = `digest_after` |
|---|---|---|
| stage 0 + stage 1 (routed) | `81e57aa7` | `9f22da52…42b7526b` |
| stage 0q + stage A (QKV) | `798df257` | `f191c3b4…6a14520b7` |

Nothing in `Sources/` or `Vendor/` differed at the end of any timed run, and no
timed slot was produced by a patched tree: every arm in both timing stages is
the *same* `new` binary steered by an environment selector, which is why
build-to-build variation cannot enter any contrast reported here.

### 9.2 Rule-77 dispatch-geometry table

Both sites, every dose actually dispatched, taken from the one-shot receipts and
not from reading the source. `dispatch rows` is `total_simdgroups *
rows_per_simdgroup` as reported by the receipt: 4096 at the routed site (512
logical rows across the 8 selected experts) and `(heads + 16) * 128` at the QKV
site. `TG` is threadgroups launched per kernel invocation, `thr/TG` is `32*S`,
and `TG/core` divides `TG` by 20 GPU cores on this M4 Pro and by the 40 cores of
the ranked M5 Max.

| site | S | dispatch rows | rows % S | TG | thr/TG | simdgroups | rows/simdgroup | grid threads | TG/core M4 | TG/core M5 |
|---|---|---|---|---|---|---|---|---|---|---|
| routed gate/up | shipped (2) | 4096 | 0 | 2048 | 64 | 4096 | 1 | 131072 | 102.4 | 51.2 |
| routed gate/up | 4 | 4096 | 0 | 1024 | 128 | 4096 | 1 | 131072 | 51.2 | 25.6 |
| routed gate/up | 8 | 4096 | 0 | 512 | 256 | 4096 | 1 | 131072 | 25.6 | 12.8 |
| routed gate/up | 16 | 4096 | 0 | 256 | 512 | 4096 | 1 | 131072 | 12.8 | 6.4 |
| QKV lane-major, 64 heads | shipped (2) | 10240 | 0 | 5120 | 64 | 10240 | 1 | 327680 | 256.0 | 128.0 |
| QKV lane-major, 64 heads | 4 | 10240 | 0 | 2560 | 128 | 10240 | 1 | 327680 | 128.0 | 64.0 |
| QKV lane-major, 64 heads | 8 | 10240 | 0 | 1280 | 256 | 10240 | 1 | 327680 | 64.0 | 32.0 |
| QKV lane-major, 64 heads | 16 | 10240 | 0 | 640 | 512 | 10240 | 1 | 327680 | 32.0 | 16.0 |
| QKV lane-major, 48 heads | shipped (2) | 8192 | 0 | 4096 | 64 | 8192 | 1 | 262144 | 204.8 | 102.4 |
| QKV lane-major, 48 heads | 4 | 8192 | 0 | 2048 | 128 | 8192 | 1 | 262144 | 102.4 | 51.2 |
| QKV lane-major, 48 heads | 8 | 8192 | 0 | 1024 | 256 | 8192 | 1 | 262144 | 51.2 | 25.6 |
| QKV lane-major, 48 heads | 16 | 8192 | 0 | 512 | 512 | 8192 | 1 | 262144 | 25.6 | 12.8 |

Two invariants hold at both sites and every dose: total simdgroups and
rows-per-simdgroup do not move, so `S` only merges existing simdgroups into
wider threadgroups. It never changes how much arithmetic each simdgroup does.
The only quantity `S` controls is threadgroup count, i.e. the scheduler's unit
of work — which is why the whole family lives on one occupancy axis and why the
M4→M5 core-count halving of `TG/core` is the transfer risk that matters.

### 9.3 What is settled and what fern should not re-run

- The routed gate/up packing knob is closed: `N-SITE1`, with the negative
  control firing at `+63.5 us [+55.7, +71.3]`. Re-running it is not useful; the
  useful residue is the *shape* in §9.2 — the routed curve is flat from 102.4
  down to 25.6 TG/core on this host and only breaks at 12.8.
- `S = 16` at the routed site is a calibrated, cheap negative control for any
  future full-decode instrument at this scale: one binary, one env var, a known
  `+63.5` M4 µs/step = `+0.422 %cs` at α = 0.4369, 18/18 sign agreement.
- The `_sgS` selector machinery is free. A byte-identical rendered Metal body
  under a distinct pipeline name and an extra host branch cost
  `-3.0 us [-11.7, +5.6]`, so a future arm can carry the selector without
  paying for it, and can use `SG=1` as a rejected-value identical-execution
  null.
- Both drivers are already site-parameterised: `SEL_VAR` plus `SG_LIST` for
  `research/maple-edward-r107a-stage1.sh`, `SITE=` plus `GEOM_SG_LIST` /
  `PARITY_SG_LIST` / `FAULT_SG_LIST` for `…-stage0.sh`, `SITE=` for the
  publisher. A third site needs a `SITES` entry and an instrumentation mode, not
  a new harness.
- The store-row fault control is the part worth copying. Its sensitivity is
  site-dependent by two orders of magnitude (96/96 at QKV, 1/96 at routed), so a
  clean greedy stream is only evidence *after* the matching fault build has been
  shown to break it at that same site.
- Nothing here is an M5 magnitude claim. Every interval is M4 Pro
  (`applegpu_g16s`, gen 16, 20 GPU cores) and this host does not select the
  `_nax` prefill kernels the ranked M5 uses. The transferable content is the
  occupancy ledger and the sign discipline, and the M5 remains authoritative for
  any near-tie.
