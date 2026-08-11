# DARKBLOOM_NVFP4_NIBBLE_SPLIT — measurement verdict

Assignment: PR #692 comment 11, feedback `r116-a-fusion-closed-redirect-to-nibble-split`.
Student: maple-tanjiro. Host: Mac16,11 M4 Pro, 20 cores, 48 GB, Apple GPU gen 16
(`is_nax_available() == false`), low-memory startup profile.

Status of this file: **DRAFT — ceiling section final, measurement sections pending
the in-flight ABBA (job `0b7c3a6d`).**

---

## 1. Ceiling first

The advisor asked me to lead with the ceiling. Here it is, before any statistics.

### 1.1 What the flag can physically change

`DARKBLOOM_NVFP4_NIBBLE_SPLIT` selects among three algebraically identical
bit-extraction forms that unpack 8 FP4 codes from one packed 32-bit word into
four `half2` lanes, inside `laguna_nvfp4_qdot_codes_16`. Verified from the
dumped generated sources (`nibble-evidence/header_split{0,1,2}.metal`):

| arm | form | ALU ops per packed word | dependency depth |
|---|---|---|---|
| 0 | mask-then-shift | 19 | 2 |
| 1 (shipped default) | shared subexpression `xe/ge/yo/go` | 13 | 3 |
| 2 | shift-then-mask | 19 | 2 |

The flag moves **zero bytes**. Same weight loads, same stores, same dispatch
geometry, same thread count, same occupancy. It is purely ALU instruction
selection. Arms 0 and 2 are reorderings of each other with identical op counts,
so my prior is that they collapse.

### 1.2 Affected surface — the named target is not the denominator

The assignment names `laguna_shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1`. But
`lagunaSharedSwiGLUQMVHeader` is attached to 16 kernel registrations
(`LagunaRuntimeModel.swift` lines 6982, 7079, 7088, 7181, 7238, 7249, 7458,
7557, 7709, 7899, 8025, 8167, 8247, 8273, 8548, 8574). From my own decode
census (arm N, 200 steps, gpu_busy 8567 µs/step, 406 dispatches/step):

| kernel | µs/step | share of gpu_busy |
|---|---|---|
| `routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2` | 1502.1 | 17.53 % |
| `routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6` | 862.0 | 10.06 % |
| **`shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1`** (named target) | **288.7** | **3.37 %** |
| **family total** | **2652.8** | **30.97 %** |

This independently reproduces the advisor's 2,647 µs/step figure. The named
target is only **10.9 %** of the surface the flag actually touches, so the
family is the correct ceiling denominator. `decode_nvfp4_qkv_*` (1344.2 + 363.8)
and `oproj_act_*` (1116.7 + 304.7) use a *different* header and are unaffected.

Near miss checked and excluded: `dense_down_residual_bf16_v1` (134.4 µs/step) has
a similar name but its registration (line 8760) takes no `header:` argument at
all and is a plain bf16 dense kernel, not NVFP4. It is not in the family.

### 1.3 ALU accounting

Per `uint2` (16 FP4 codes, 8 bytes of weight), the body executes:

| component | ops, arms 0/2 | ops, arm 1 |
|---|---|---|
| nibble extract, ×2 blocks | 38 | 26 |
| `as_type<half2>` → `float2`, ×8 | 16 | 16 |
| FMA accumulate, ×16 | 16 | 16 |
| **total** | **70** | **58** |

Best-to-worst ALU spread = 12/70 = **17.1 %**.

### 1.4 Three ceilings, and why they differ by 100×

Rule 105.12 M4→M5 factor 30.0/68.7 = 0.4367; score law
`%score = 0.75 · τ · Δ_M5 / 8972`.

| model | assumption | Δ M4 µs/step | Δ M5 µs/step | % of score |
|---|---|---|---|---|
| **A. ALU-bound** | family time ∝ ALU ops, no DRAM floor | 2652.8 × 0.171 = 453.6 | 198.1 | **+1.66 %** |
| **B. sum model** | non-DRAM fraction (42 %) is all ALU, DRAM and ALU do not overlap | 2652.8 × 0.42 × 0.171 = 190.5 | 83.2 | **+0.70 %** |
| **C. overlap model** | ALU hides under the DRAM stream | ≈ 0 | ≈ 0 | **≈ 0 %** |

The 42 % in model B is the advisor's own figure for the named target: 153.1 GB/s
achieved against 256.7 GB/s peak, DRAM floor 165.6 µs of 284.9 µs.

Bar (Rule 105.12): +30 µs/step M5 = +68.7 µs/step M4 = **0.251 % of score**.

So the axis is *not* a priori dead. Under model B the ceiling is 2.8× the bar;
under model A, 6.6×. It earns a measurement. Under model C it is dead.

### 1.5 Which model is right — the core-count invariance argument

There is a cheap discriminator that does not need a single new run.

The named target kernel costs **288.7 µs/step on my 20-core M4 Pro** and, per the
assignment, **284.9 µs/step on the 40-core ranked M5 Max** — a 1.3 % difference
across a **2× core count**.

A kernel whose runtime is invariant to core count is not ALU-throughput-bound.
If model A held, the M5 number should have been near 145 µs/step. It is not.
This places the family firmly between models B and C, and much closer to C.

Caveat I cannot close from here: I do not know the provenance of the advisor's
284.9 µs/step (profiled or not, step count, SPLIT arm). My 288.7 µs/step is
under the SPLIT=1 profile hook at 200 steps. But a 2× core ratio would have to
be almost entirely masked by measurement bias to be invisible, so I treat the
invariance as real pending correction.

### 1.6 Direction of the live hypothesis

Arm 1 already has the **fewest** ops (13 vs 19). So §1.4 bounds the *loss* from
choosing a worse arm, not a gain. For a gain, arms 0/2 must beat arm 1, which
requires a second-order effect:

> Arm 1 trades 6 fewer ops for a dependency chain of depth 3
> (`c → xe → ge → p0`). Arms 0/2 have depth 2 and more ILP. If the family is
> **latency**-bound at low occupancy rather than throughput-bound, the shallower
> chain can win despite the extra ops.

This is the only live gain mechanism, and it is bounded far below §1.4: the
difference is one ALU latency per packed word against a 58–70 op body.

**Ceiling verdict going in:** plausible upside is the low end of the 0–0.70 %
band, most likely indistinguishable from zero, against a 0.251 % bar. Measure
it, but expect a null and design the rig to *prove* a null rather than merely
fail to reject one.

---

## 2. Reachability proof (deliverable due 04:30Z — complete)

Method: `qmv-header-dump.patch` (27 lines) adds an env-gated
(`DARKBLOOM_DUMP_QMV_HEADER`) stderr dump of the generated header string at the
tail of the lazy global's initializer. `nibble-split-reachability.sh` applies it,
builds the worker, runs one decode per arm, extracts and hashes the emitted
source, and reverts via `trap revert EXIT`.

Job `600d0ecb`, exit 0, 108 s. All three arms: teacher-forced **0 divergences**.

```
split0 sha256 9c03666f36cf60f09a312cd04ade26e8f6f9a07390d5db84cb889191eb511e41
split1 sha256 7f0387756fcf7877e04f7578d06a33886858b4cc937e324cf5132b4a9bb7d138
split2 sha256 20b1f8d879357ac3badf0731ec72745c517496abc430b0639360ad6ca7085ef1
pairwise differing lines: 0v1=34, 0v2=18, 1v2=34
in-process marker lines confirm the parse: split=0, split=1, split=2
```

**Three distinct arms — none collapse at the source level.** Call chain proven:
the target kernel source calls `laguna_nvfp4_qdot_16` (lines 55/59 of
`lagunaSharedSwiGLUQMVRows1Source`) → `laguna_nvfp4_qdot_codes_16` → the
`extract` block, inlined twice per call (`packedWordBody(0)` and `(1)`).

MLX cache hazard from the assignment resolved: `library_map_` (`device.cpp:602`,
770–786) is a per-process `std::unordered_map`, **not** a disk cache. One arm per
process is sufficient; no stale-library risk across runs.

---

## 3. ISA comparison (pending)

Source-level distinctness does not imply machine-code distinctness. The Metal
front end is LLVM-based and its demanded-bits analysis may canonicalise all
three forms to the same AIR. `nibble-split-isa.sh` wraps each dumped header in a
minimal kernel, compiles with the same toolchain MLX JITs with
(`metal -std=metal3.1 -O3 -ffast-math`), and diffs AIR text and instruction
mix.

If the AIR is identical, the null is **proven** and no wall-clock interval is
needed to support it. Deferred until the ABBA finishes so the compile cannot
perturb timing.

---

## 4. Paired ABBA (deliverable due 07:30Z — pending)

Job `0b7c3a6d`. 36 runs = 12 blocks of 3, each block a permutation of {0,1,2};
each arm appears exactly once per block and occupies each within-block position
exactly 4 times, which balances first-in-block warm-up. SPLIT=0 (no profile
hook) — **ranking only**, per the standing rule that the SPLIT=1 profile hook
inflates wall by 19.6 % and mis-ranks arms.

The script refuses to run against a dirty `LagunaRuntimeModel.swift` and rebuilds
a clean worker first, guarding against the instrumented binary left by §2.

Analysis: `nibble-split-analyze.py`, blocked estimator, true
Welch–Satterthwaite df, all three arm pairs, bar constants `BAR_M4_US=68.7`,
`M4_TO_M5=0.4367`, `M5_DECODE_US=8972`, `TAU=1.06`.

Rig resolution on this host: **±8.1 µs/step = ±0.07 % of score**, against a
68.7 µs/step bar — 8.5× headroom, so a null here is informative rather than
underpowered.

---

## 5. Attribution (pending)

Three profiled runs, one per arm, `decode_probe.py --profile --profile-top 40`,
to answer: do the three family kernels actually move, and by how much each?
Achieved GB/s per arm computed against ~43.6 MB/step for the named target
(153.1 GB/s × 284.9 µs). **Attribution only — never ranked on a profiled run.**

---

## 6. Verdict (pending)
