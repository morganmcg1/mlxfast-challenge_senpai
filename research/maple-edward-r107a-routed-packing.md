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

**Counter-evidence that repriced my prior to null before any measurement.**

- L3 note, `research/CURRENT_RESEARCH_STATE.md:3327-3334`: PR #48's 8× threadgroup
  collapse earned **−0.1488% on M5 receipt `285f79fa`**, and "geometry
  neutrality is absolute until #496 says otherwise".
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
(54 insertions / 7 deletions), well inside the 8 KiB cap.

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

Per-arm level (median statistic, mean over 18 reps, µs/step):

| arm | level | sd(rep) |
| --- | --- | --- |
| base | 8235.4 | 13.3 |
| null1 | 8232.4 | 13.5 |
| sg2 | 8232.3 | 8.9 |
| sg4 | 8237.6 | 12.5 |
| sg8 | 8240.5 | 6.0 |
| sg16 | 8298.8 | 7.1 |

Drift-cancelled paired contrasts (later − earlier, µs/step, K = 18):

| contrast | mean | 95 % hw | lo | hi | sign +/− | % of `cs` |
| --- | --- | --- | --- | --- | --- | --- |
| base→null1 | −2.91 | 9.80 | −12.72 | +6.89 | 9/9 | −0.044 |
| base→sg2 | −3.03 | 8.64 | −11.66 | +5.61 | 9/9 | −0.046 |
| base→sg4 | +2.22 | 8.67 | −6.46 | +10.89 | 11/7 | +0.034 |
| base→sg8 | +5.15 | 7.64 | −2.49 | +12.79 | 15/3 | +0.078 |
| **base→sg16** | **+63.49** | **7.83** | **+55.66** | **+71.32** | **18/0** | **+0.967** |
| sg2→sg4 | +5.24 | 5.87 | −0.63 | +11.12 | 14/4 | +0.080 |
| sg2→sg8 | +8.18 | 4.97 | +3.21 | +13.15 | 15/3 | +0.125 |
| sg4→sg8 | +2.94 | 6.17 | −3.24 | +9.11 | 15/3 | +0.045 |

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
   ±0.28 % and ±0.26 % of `cs`. Under a Bonferroni correction across all 15
   pairwise contrasts, no pair differs by more than 27.0 µs. The 26 µs/step
   graduation bar therefore cannot be met at this site by any S in {4, 8}: the
   *upper* end of the `base→sg8` interval is +12.8 µs on the slow side, and even
   the most favourable reading of the interval is a 2.5 µs gain, one tenth of
   the bar.
3. **PR #48's collapse penalty reproduces here, and it is not site-specific.**
   `base→sg16` is +63.5 µs/step = +0.967 % of `cs` with 18/18 slower signs — the
   largest clean single-knob regression measured in this arm. That is the same
   direction and, allowing for the M4-vs-M5 scale factor, roughly the same size
   as the −0.1488 % official receipt `285f79fa` charged to #48's 8× collapse.
   The mechanism is visible in the stage-0 ledger: total simdgroups and
   rows-per-simdgroup are invariant, only threadgroup count changes, so
   collapsing threadgroups can only lose — it removes independent scheduling
   units from a kernel that is already issue-bound (maple-alphonse measured this
   kernel at 114.2 GB/s = 42.9 % of M4 Pro peak, PR #630). At S = 16 the routed
   site keeps just 256 threadgroups = 12.8 per GPU core on this host, and the
   tail of a 256-threadgroup dispatch is no longer hidden.

## 5. Prefill

TODO

## 6. Verdict against the graduation gate

TODO

## 7. Suggested follow-ups (not implemented)

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

## 8. Artefacts

TODO
