# DARKBLOOM_NVFP4_NIBBLE_SPLIT — measurement verdict

Assignment: PR #692 comment 11, feedback `r116-a-fusion-closed-redirect-to-nibble-split`.
Student: maple-tanjiro. Host: Mac16,11 M4 Pro, 20 cores, 48 GB, Apple GPU gen 16
(`is_nax_available() == false`), low-memory startup profile.

Status: **FINAL. All sections complete.**

## `N-NIBBLE-SPLIT-DEFAULT-IS-OPTIMAL` — one paragraph

The shipped default (`SPLIT=1`) is the fastest of the three arms. Moving off it
costs +25.5 µs/step (median, 95 % CI [+13.7, +37.2], n=12/arm, paired ABBA,
ranking configuration) — 0.10 % of score in the wrong direction, against a bar
that wanted +68.7 µs/step of gain. No code change ships. The reusable output is
three laws: **ALU work in the NVFP4 QMV family converts to wall time at ≈5 %**
(§6), so no unpacking scheme in that family can clear the bar; **profiled
GPU-busy savings convert to ranked wall at ≈54 %** (§5.3), so halve them before
quoting; and the family **moves 621 MB/step at 86 % of DRAM peak** (§6.1), which
is why. The one live lead is the named target kernel itself, which sits at 58 %
of peak, does not respond to ALU removal at all, and carries ≈66 µs/step ≈ 0.26 %
of score of excess after fixed-overhead correction (§6.1.1).

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

## 3. ISA comparison — arms 0 and 2 are the *same program* (complete)

Source-level distinctness does not imply machine-code distinctness. The Metal
front end is LLVM-based and its demanded-bits analysis may canonicalise
different-looking bit manipulation to the same AIR. `nibble-split-isa.sh` wraps
each dumped header in a minimal kernel, compiles it offline with the same
toolchain MLX JITs with (`xcrun metal -std=metal3.1 -O3 -ffast-math`,
toolchain 32023.883), and diffs AIR text and instruction mix.

Result:

```
arm0 metallib sha256 f3d48f2007cecb8205e154a0b64cabb62b9c6325025403b3c882db84ed13168f
arm1 metallib sha256 ce43d632d40e998fc9d2c4cc96047b3105af825dbfe043e7696a4a43f314157d
arm2 metallib sha256 f3d48f2007cecb8205e154a0b64cabb62b9c6325025403b3c882db84ed13168f

AIR bitwise op mix (and / or / shl / lshr, total AIR lines)
  arm0   16   8   15   2     260
  arm1   12   4   11   2     248
  arm2   16   8   15   2     260   (cmp vs arm0: IDENTICAL modulo module ID + source filename)
```

Two conclusions, both load-bearing.

**(a) Arms 0 and 2 compile to a byte-identical metallib.** Mask-then-shift and
shift-then-mask are canonicalised to the same AIR; the only textual differences
are the LLVM module identifier and the source file name. So `[0 − 2]` is a
**built-in negative control**: two arms that are provably the same machine code,
measured through the entire rig — env var, JIT, dispatch, 200 decode steps,
process teardown. Any interval `[0 − 2]` produces that excludes zero is pure rig
noise, and it calibrates how much of any `[0 − 1]` or `[2 − 1]` signal to
believe. Almost no A/B rig in this campaign has had one.

**(b) Arm 1 is genuinely a different program**, and different in exactly the
predicted direction and magnitude: 29 bitwise ops versus 41, i.e. 12 fewer, the
same 2 × 6 saving hand-counted in §1.3 from the shared `xe/ge/yo/go`
subexpressions. The source-level op count is not being optimised away, so the
wall-clock experiment is measuring a real ALU delta rather than a no-op.

Because arms 0 and 2 are the same program, they may legitimately be **pooled**
into a single treatment arm `P` with double the sample size, giving the
contrast `[P − 1]` roughly √2 tighter than either raw pair. `nibble-split-analyze.py`
does this and separately prints and validates the negative control.

---

## 4. Paired ABBA — arm 1 is the fastest arm (complete)

Job `05bd1725`. 36 runs = 12 blocks of 3, each block a permutation of {0,1,2};
each arm appears exactly once per block and occupies each within-block position
exactly 4 times, which balances first-in-block warm-up. SPLIT=0 (no profile
hook) — **ranking only**, per the standing rule that the SPLIT=1 profile hook
inflates wall by 19.6 % and mis-ranks arms.

The script refuses to run against a dirty `LagunaRuntimeModel.swift` and rebuilds
a clean worker first, guarding against the instrumented binary left by §2.

Analysis: `nibble-split-analyze.py`, blocked estimator, true
Welch–Satterthwaite df, all three arm pairs, bar constants `BAR_M4_US=68.7`,
`M4_TO_M5=0.4367`, `M5_DECODE_US=8972`, `TAU=1.06`.

Evidence: `nibble-evidence/abba36.tsv`, `nibble-evidence/abba36-analysis.txt`.
All 36 runs report **0 divergences** on the teacher-forced greedy tokens, so
every arm is bit-exact against the golden path — as expected, since the three
sequences are algebraically identical unpackings of the same nibbles.

```
                     mean us/step                 median us/step
  arm 0   n=12   8300.4  sd 20.7            8280.8  sd 15.2
  arm 1   n=12   8278.9  sd 24.1            8259.7  sd 11.0
  arm 2   n=12   8309.9  sd 36.5            8289.4  sd 25.2

  [0 - 2] NEGATIVE CONTROL   -9.5 [-35.1, +16.1]    -8.6 [-28.2, +11.0]
  [P - 1] TREATMENT         +26.2 [ +1.4, +51.1]   +25.5 [+13.7, +37.2]
```

(blocked estimator, k=12, Welch–Satterthwaite df; `P` = arms 0 and 2 pooled.)

Three things to read off this.

**The negative control passes.** Two arms that §3 proves are the same machine
code measure −9.5 µs/step apart with an interval that comfortably contains zero.
That is not an assumption about the rig, it is a measurement of the rig, and it
sets this host's true resolution on a known-null contrast at **±25.6 µs/step
(mean) / ±19.6 µs/step (median)** — 2.7× to 3.5× inside the 68.7 µs/step bar.
So a null on the treatment contrast is informative rather than underpowered.

**The treatment contrast is real but small.** `[P − 1] = +26.2 µs/step` mean and
`+25.5` median, both with intervals excluding zero, and the two independent
estimators agree to 0.7 µs/step. Arm 1 — the **shipped default** — is the
fastest arm, in exactly the direction §1.3 and §3 predict from its 12 fewer
bitwise ops. The flag is doing what it says; it just is not worth much.

**Nothing here clears the bar, and the sign is wrong anyway.** Switching away
from the default *costs* 26 µs/step = 0.10 % of score. Even the most generous
reading — the upper 95 % limit of the treatment interval, +51.1 µs/step — is
below 68.7, and it is an upper limit on a **loss**, not on an available gain.
There is no configuration of this flag that is faster than what ships.

---

## 5. Attribution — the delta lands on the family, but not on the named target (complete)

`nibble-split-profile.sh` + `nibble-split-profile-diff.py`. Six profiled runs in
the palindrome order `012210`, so each arm's two reps are symmetric about the
session midpoint and linear drift cancels within each arm's mean. The GPUPROF
hook lives in `research/pr91-gpuprof-hook.patch` (it touches `device.cpp`/`.h`,
which are **not** editable paths); the script applies it, builds one
instrumented worker, captures every arm from that single build, and reverts on
every exit path.

Question: the ABBA contrast is a whole-process number. Does the arm delta land
on the NVFP4 QMV family — the 16 registrations of `lagunaSharedSwiGLUQMVHeader`
— in proportion to each registration's share, or somewhere else? If it does not,
the §1 ceiling is computed against the wrong denominator and must be redone.

Arms 0 and 2 are the same metallib, so the row-by-row `|0 − 2|` spread is the
profiler's own reproducibility floor and a `[P − 1]` row only counts if it
clears that floor. **Attribution only — never ranked on a profiled run.**

Evidence: `nibble-evidence/p{1..6}_*.log`, `nibble-evidence/attribution-analysis.txt`.
All six runs: 0 token divergences, 406 command buffers and 406 dispatches each,
GPU-busy 8.55–8.61 ms/step, inter-dispatch gap 12.3–12.7 % of wall.

### 5.1 The causally reachable rows

`DARKBLOOM_NVFP4_NIBBLE_SPLIT` has **exactly one read site** in the whole
runtime — `LagunaRuntimeModel.swift:6653` — and it feeds only
`lagunaSharedSwiGLUQMVHeader`. Three kernels in the decode profile are built
from that header:

```
      P(0,2)     arm1      P-1   |0-2|   kernel
      1521.6   1500.8    +20.8     1.3   routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2
       887.4    861.0    +26.4     0.4   routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6
       288.4    288.7     -0.3     0.5   shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1
      2697.4   2650.5    +46.9           reachable subtotal
```

The §1 denominator survives: the reachable subtotal under SPLIT=1 is
2650.5 µs/step against the 2652.8 µs/step census, and it carries **+46.9 of the
+33.8 µs/step total** row movement. Every non-reachable row sums to −13.1, i.e.
the flag's effect is *more* than fully explained by the three kernels it can
actually reach. §1's ceiling arithmetic stands.

### 5.2 The finding that matters — the named target does not respond at all

The assignment named `laguna_shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1` as
the target kernel. It is the **one kernel in the family that shows no response
whatsoever**: −0.3 µs/step against a same-program `|0 − 2|` control of 0.5. Its
two siblings move by 20.8 and 26.4 against controls of 1.3 and 0.4.

Per-kernel ALU conversion efficiency, using §1.3's 12-of-58 op ratio:

```
kernel                          arm1 us/step   predicted-if-ALU-bound   measured   efficiency
routed gate+up  (swiglu_qmv)          1500.8                    310.5      +20.8         6.7 %
routed+shared down (stage4_v6)         861.0                    178.1      +26.4        14.8 %
shared gate+up  (NAMED TARGET)         288.7                     59.7       -0.3        -0.5 %
```

Deleting 12 arithmetic instructions per packed `uint2` from the named target
changes its runtime by nothing measurable. A kernel that does not respond to a
20 % cut in its own instruction count is not compute-bound. §6.1 shows it is not
bandwidth-bound either. That is the actionable output of this assignment, and it
came from the negative control rather than from the treatment.

### 5.3 A calibration constant: profiled GPU-busy over-predicts ranked wall

The same treatment measures **+46.9 µs/step of GPU-busy under SPLIT=1** and
**+25.5 µs/step of wall under SPLIT=0** (§4 median, n=12/arm). A kernel-level
saving therefore converts to ranked wall at

```
25.5 / 46.9 = 54 %      (CI from §4's median interval: 29 % .. 79 %)
```

**Halve any profiled per-kernel saving before believing it as a score delta.**
Under SPLIT=1 every dispatch sits in its own command buffer; in the ranking
configuration the 12.5 % inter-dispatch gap and the surrounding pipeline absorb
about half of any GPU-busy reduction. This is a campaign-reusable number: it is
the missing step between "the profiler says I saved X" and "the leaderboard
moves by Y", and every profiled proposal in this campaign has implicitly been
using a conversion factor of 1.0.

### 5.4 Honest residual

Two non-reachable rows move more than their control:
`decode_nvfp4_qkv_h64_r1_v1_lm1_pw1_se1_sd1` at −11.3 (control 0.5) and
`sliding_fused_attn_ring_v1` at −10.7 (control 1.5). Neither can be caused by
the flag: the QKV kernels are registered with `lagunaTailNVFP4QMVHeader`
(lines 4890, 4909, 4996), a different header that never reads the environment
variable, and the attention ring kernel contains no NVFP4 unpacking. With
n=2 per arm the `|0 − 2|` control understates true cross-run structure, so these
rows are the profiler's real reproducibility limit at this replication count,
not an effect. They are reported rather than dropped because they set the honest
per-row detection floor at ≈ ±11 µs/step, not ±1.5.

---

## 6. `L-NVFP4-ALU-CONVERTS-AT-5-PERCENT` — the reusable finding

The flag verdict is worth one line. The reusable output of this assignment is the
**exchange rate between removed ALU work and removed wall time** in the NVFP4 QMV
family, which nothing else in the campaign has pinned down, and which the arms
happen to measure exactly — because §1.3 and §3 independently agree on how much
ALU the flag moves, and §4 measures what that is worth in wall time.

```
predicted_if_ALU_bound = family_us_per_step × (Δops_per_uint2 / ops_arm1)
                       = 2652.8 × 12 / 58   = 548.9 µs/step
efficiency             = measured_Δ / predicted_if_ALU_bound
                       = 26.2 / 548.9 = 4.77 %   (mean,   CI [0.26 %, 9.31 %])
                       = 25.5 / 548.9 = 4.65 %   (median, CI [2.50 %, 6.78 %])
```

**Roughly 5 % of this family's nominal ALU cost is on the critical path. The
other 95 % is already hidden behind memory traffic and latency.** The two
estimators land 0.12 percentage points apart, and the tighter (median) interval
is [2.5 %, 6.8 %].

This is a bound on a whole class of future work, and it is the reason to publish
it rather than the flag result. Ask what it would take to earn the +68.7 µs/step
M4 bar out of this family by deleting arithmetic. Inverting the relation:

```
ops_to_delete = ops_arm1 × 68.7 / (family_us_per_step × efficiency)
              = 58 × 68.7 / (2652.8 × 0.0465) = 32.3 ops per packed uint2
```

against a **budget of 26**. Arm 1 spends 58 ops per `uint2`: 26 on nibble
extraction, 16 on `half2→float2` conversion and 16 on the FMAs. The last 32 are
the dot product itself and cannot be removed by any unpacking scheme. So the
requirement (32.3) exceeds the entire removable budget (26).

Equivalently, and more usefully stated: **if nibble extraction became completely
free — zero instructions, a physically impossible idealisation — the whole family
would gain 55 µs/step = 0.21 % of score, still short of the 0.27 % bar.** Using
the optimistic end of the efficiency interval it reaches 0.31 %, i.e. borderline
at best, for an unreachable idealisation.

The practical consequence: **stop proposing ALU-count micro-optimisations inside
the NVFP4 QMV family.** Not this flag, not a cleverer unpack, not a lookup table,
not `simd_shuffle` tricks on the codes — the ceiling on all of them jointly is
below the promotion bar. Wins in this family have to come from the other 95 %:
bytes moved, occupancy, or dispatch structure. That redirects effort rather than
just closing a door.

Two caveats stated honestly. `family_us_per_step = 2652.8` comes from a SPLIT=1
census; §5.1 confirms it independently (2650.5 µs/step of reachable rows in the
attribution session), so the denominator is not the weak link. And 4.65 % is an
M4 Pro number — an M5 with different ALU:bandwidth balance would have a different
exchange rate, though the direction (severely memory-bound) is a property of a
4-bit weight-stationary GEMV and is not plausibly reversed by one Apple Silicon
generation.

One reading could reopen the door and is worth stating so nobody has to
rediscover it. If you use the SPLIT=1 GPU-busy efficiency (46.9 / 548.9 = 8.5 %)
instead of the wall efficiency, the requirement drops to 17.7 ops and fits inside
the 26-op budget. That reading is wrong: §5.3 shows GPU-busy over-predicts ranked
wall by about 2×, and the leaderboard is scored on wall. **The ceiling is closed
in the ranking configuration and only appears open in a configuration proven to
over-predict.**

---

## 6.1 Where the 95 % actually goes — exact bytes from the scored checkpoint

If ALU is 5 % of this family, the honest next question is what the other 95 % is.
This is answerable exactly rather than by estimate, because the scored checkpoint
already stores NVFP4 and its safetensors headers give the byte counts directly.
`nvfp4-roofline.py` reads `weights/` and `config.json`; output in
`nibble-evidence/roofline.txt`.

Layout, read off the headers rather than assumed: per expert `gate_proj` stores
`weight` U32 `[512,256]` = 524,288 B and `scales` U8 `[512,128]` = 65,536 B, so
**group size 16, 4.0 bit/code, 0.5625 byte/weight all-in**. Layer 0 is dense;
layers 1–39 are MoE; top-8 of 256 experts; `moe_intermediate_size` 512,
`shared_expert_intermediate_size` 512, `hidden_size` 2048.

```
  MB/step   us/step     GB/s  % of 273 GB/s peak   kernel group
    368.1    1502.1    245.0        89.8 %         routed gate+up
    207.0     862.0    240.2        88.0 %         routed+shared down
     46.0     288.7    159.4        58.4 %         shared gate+up   <-- NAMED TARGET
    621.1    2652.8    234.1        85.8 %         FAMILY
```

**The family moves 621 MB per decode step and runs at 86 % of this host's
theoretical DRAM peak.** That is the physical reason §6's exchange rate is 5 %,
and it is a much stronger closure argument than the ALU count alone: two of the
three kernels are within 10–12 % of the memory roofline, and the residual there
is not worth a submission.

The exception is the named target at 58 % of peak. Two independent measurements
now say the same thing about that kernel — §5.2 says it does not respond to ALU
removal, and this says it does not saturate bandwidth either.

### 6.1.1 De-risking the number before anyone spends a run on it

The naive gap is worth 100.9 µs/step = 0.391 % of score, above the 0.27 % bar.
That number is too optimistic and should not be quoted. The shared kernel is
small — 1.18 MB and 7.39 µs per dispatch against 9.44 MB / 38.5 µs for routed
gate+up — so a fixed per-dispatch cost is a much larger fraction of it, and under
SPLIT=1 each dispatch carries its own command buffer.

Fit `t_call = c + bytes / BW` on the two sibling groups and use them as the
efficient frontier:

```
c  = 1.01 us fixed per dispatch,  BW = 251.7 GB/s
predicted shared gate+up = 1.01 + 1.1795 MB / 251.7 GB/s = 5.70 us/call
observed                 = 7.40 us/call
excess                   = 1.70 us/call x 39 layers = 66.4 us/step = 0.257 % of score
```

So the defensible lead is **≈66 µs/step, 0.26 % of score — at the bar, not
comfortably over it**, and the difference between 0.39 % and 0.26 % is entirely
the fixed-overhead correction that the naive reading omits. Anyone picking this
up should size it as a bar-grazing candidate that needs a second mechanism to be
worth promoting, not as a comfortable win.

Two further conditions, both of which change the answer:

- **The fix has to be occupancy or work distribution, not dispatch elimination.**
  The campaign's τ filter puts real work removal at τ≈1.06 and pure dispatch
  removal at τ≈0.01. The obvious "fuse the shared expert into the routed
  gate+up dispatch" idea removes 39 dispatches per step; if the gain is mostly
  the dispatches, it transfers to M5 at roughly nothing and the 0.26 % becomes
  0.002 %. Only the part that raises achieved bandwidth transfers.
- **The kernel is core-count invariant**, which is why this is worth writing
  down at all. It costs 288.7 µs/step on this 20-core M4 Pro against the 284.9
  µs/step figure quoted for the 40-core M5. Doubling the core count changes it
  by 1.3 %. A kernel that ignores core count is latency- or occupancy-bound, and
  it means **the ranked M5 has the same inefficiency, only with twice as many
  idle cores**. Per `L-RANKED-REACHABILITY` this is the reachability evidence
  the lead needs; the 284.9 figure's provenance is second-hand and should be
  re-derived on M5 before anyone commits a submission to it.

---

## 7. Verdict

**`N-NIBBLE-SPLIT-DEFAULT-IS-OPTIMAL`. No code change ships. The axis is closed.**

`DARKBLOOM_NVFP4_NIBBLE_SPLIT` already ships on its fastest setting. Moving off
the default costs **+25.5 µs/step (median, 95 % CI [+13.7, +37.2], n=12/arm,
paired ABBA in the ranking configuration)**, which is 0.10 % of score in the
wrong direction. The bar was +68.7 µs/step of *gain*; the flag offers a loss, and
even the optimistic end of its interval is a loss.

| deliverable | due | status |
| --- | --- | --- |
| reachability proof | 04:30Z | done — §2, three distinct generated sources, 34/18/34 differing lines |
| paired ABBA | 07:30Z | done — §4, 36 runs, 0 divergences, negative control brackets zero |
| verdict | 09:30Z | done — this section |
| terminal result | 10:30Z | submitted |

Also closed, and more useful than the flag itself:

1. **`L-NVFP4-ALU-CONVERTS-AT-5-PERCENT` (§6).** About 5 % of the NVFP4 QMV
   family's nominal ALU cost is on the critical path. Deleting *all* removable
   nibble-extraction arithmetic — a physically impossible idealisation — buys
   0.21 % of score against a 0.27 % bar. **Stop proposing ALU-count
   micro-optimisations in this family.** Not a cleverer unpack, not a LUT, not
   `simd_shuffle` on the codes; the joint ceiling on all of them is under the bar.
2. **§6.1's byte accounting explains why.** The family moves 621 MB per decode
   step at 86 % of theoretical DRAM peak. It is memory-bound by construction, and
   the two routed kernels are within 10–12 % of the roofline.
3. **`L-PROFILED-BUSY-OVERPREDICTS-WALL-2X` (§5.3).** A per-kernel saving seen
   under `DARKBLOOM_GPU_PROFILE_SPLIT=1` converts to ranked wall at 54 %
   (CI 29–79 %). Halve profiled savings before quoting them as score deltas.

### What to do instead

§6.1.1: `laguna_shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1` runs at 58 % of
peak bandwidth while its two siblings run at 88–90 %, and it is the one kernel in
the family that does not respond to ALU removal at all. After correcting for
fixed per-dispatch cost using the siblings as the efficient frontier, the excess
is **≈66 µs/step ≈ 0.26 % of score** — at the bar, conditional on the fix raising
achieved bandwidth rather than merely removing dispatches. It is core-count
invariant, so the ranked M5 has the same inefficiency.

That is a lead, not a result. It is handed over sized and de-risked rather than
quoted at its flattering 0.39 % headline.

### Correctness

No code change ships, so `research/run_upstream_equivalence.sh` is not required
by Rule 105.15 and was not run. The behavioural evidence is nonetheless complete:
**42 teacher-forced runs across all three arms — 36 in §4 and 6 in §5 — reported
0 divergences, every checked greedy token matching.** The flag is
behaviour-neutral on all three settings, which is what §3's ISA comparison
predicts for arms 0 and 2 (byte-identical metallib) and what §1's op accounting
predicts for arm 1 (same values, different instruction schedule).

### Note for frieren (#705, flag inventory)

Two facts that change how this flag should be inventoried:

- It is **not a ternary knob**. §3 proves arms 0 and 2 compile to a
  byte-identical metallib (`f3d48f20…`); only arm 1 differs. Any inventory that
  lists three distinct configurations is over-counting the search space by one.
- Its default is optimal and its non-default settings are strictly slower, so
  there is no shipping decision to make. If the inventory is being pruned for
  code size, this flag and its two dead arms are pure dead weight on the
  submitted surface; deleting the branch and hard-coding arm 1 would be a
  behaviour-preserving simplification. That is a decision for #705, not for this
  assignment, and it is worth bytes rather than time.
