# R110-B rev3 — zero-tgmem register prefetch wins on the non-`_nax` gather-GEMM

**Assignment** `maple-r110-b-gemm-double-buffer-staging` / **`r110-b-rev3`**
**PR** #693 · **base** `codex/mlxfast-maple-20260804-advisor` @
`30904ecbf180aa05d7ddf5cc957e83155fbfc6f4` (`BASE_SHA`; code-identical to the
`9fe37190` cited in rev2 — I did **not** re-baseline)
**Host** Apple M4 Pro (Apple GPU generation 16),
`maxThreadgroupMemoryLength = 32768 B`

## Headline

The rev2 STOP was correct about the mechanism it actually tested and wrong
about the mechanism's *name*. Double-buffering the gather-GEMM **through
threadgroup memory** loses because it halves occupancy, not because the prize
is small. The prize is real: I built the zero-tgmem variant the advisor asked
for and it is the best arm in the whole matrix.

| arm | tgmem | resident TGs | weighted kernel Δ (2 runs) |
|---|---|---|---|
| `base` | 3 840 B | 8 | — |
| `nobar` *(illegal ceiling)* | 3 840 B | 8 | **+0.721 %** |
| `dbmem` (tgmem DB, 2 barriers) | 7 680 B | 4 | −2.543 % |
| `db2` (tgmem DB, 1 barrier) | 7 680 B | 4 | −0.437 % |
| `regstage` (register routing, no overlap) | 3 840 B | 8 | −0.138 % |
| **`pf` (register prefetch, landed)** | **3 840 B** | **8** | **+0.853 %** |
| `pf2` (two register sets) | 3 840 B | 8 | +0.590 % |

`pf` **beats the illegal `nobar` ceiling** (+0.853 vs +0.721). Reordering the
device reads ahead of the barrier is worth more than deleting the barrier,
and it costs nothing in threadgroup memory or occupancy.

**But the ranked reach of the landed change is ≈ 0**, and I want that stated
before any of the arithmetic below: on a NAX-capable host `gather_qmm_rhs`
routes unconditionally to `gather_qmm_rhs_nax`
(`Vendor/mlx-swift/.../metal/quantized.cpp:1669-1671`; the gate is
`is_nax_available() && transpose && dtype != float32`, and Laguna is bf16 /
transposed). My two rewired call sites are both inside `fp_gather_qmm_rhs`
in the **non-`_nax`** family (`kernels/fp_quantized.h:2149,2165`). The M5
never executes them. I did not port the mechanism to `_nax`, for a specific
evidence-backed reason given in Deliverable 3.

So this is a **mechanism result with a landed, bit-exact, zero-risk
implementation that helps every non-NAX Apple Silicon host and is inert on
the ranked one.** Merging it into the research base preserves the mechanism;
including it in an official submission buys nothing. That is the advisor's
call and I have made the revert trivial (six files, one script).

## Correctness

- `research/run_upstream_equivalence.sh` — **NON-ZERO**: 1 test selected,
  `"promptTokenCount"` report present, `EQUIVALENCE_EXACT_STEPS=8`.
  All 8 decode steps `maximumAbsoluteLogitError = 0`; all 9 runtime/upstream
  token pairs identical. Prefill reports `0.125 / 0.011933609`, which is the
  **documented pre-existing M4 base signature** to 9 significant figures
  (`research/CURRENT_RESEARCH_STATE.md:1812`,
  `research/RESEARCH_ARCHIVE_through-round-91.md:4102`). `EQUIVALENCE_EXIT=1`
  is the wrapper's zero-tolerance prefill rule firing on that pre-existing
  near-tie, exactly as the archive describes; a genuine numerical change
  would move the mean, and it did not move at all.
  Log: `logs/08-upstream-equivalence.log`.
- Rig byte-compare (`verifyVariants()`, `ED_VERIFY=0` to skip): `nobar`,
  `dbmem`, `db2`, `regstage`, `pf`, `pf2` are all **bit-exact vs `base`** over
  32 700 / 32 768 non-zero reference bytes on a deterministic problem.
- `tools/build-mlx-metallib.sh` rebuilt clean (`logs/07-metallib-build.log`);
  the AOT `.h` edits compile.
- `git diff --numstat 30904ecb -- Sources Vendor benchmark.json Package.swift`
  is **non-empty**: six vendor files, **+236 / −4**.

  | file | ± |
  |---|---|
  | `mlx-generated/fp_quantized.cpp` | +48 / −2 |
  | `mlx-generated/gemm.cpp` | +21 / −0 |
  | `mlx-generated/quantized_utils.cpp` | +49 / −0 |
  | `metal/kernels/fp_quantized.h` | +48 / −2 |
  | `metal/kernels/quantized_utils.h` | +49 / −0 |
  | `metal/kernels/steel/gemm/loader.h` | +21 / −0 |

  All six are on `editablePaths`;
  `senpai/validate-assignment-scope.sh` passes and
  `senpai/check-editable-budget.sh` reports
  `current=2688038/3000000 headroom=311962 growth=6832/262144 files=142`.

---

# The six rev3 deliverables

## D1 — the rev2 finding is renamed and re-scoped

`N-GEMM-WAR-BARRIER-FREE` → **`N-GEMM-TGMEM-DB-OCCUPANCY-RENT`**.

The old name blamed the barrier and implied "no prize here". Both are wrong.
The true scope of the negative is:

- **mechanism**: double-buffering the staged tile *through threadgroup
  memory* — not prefetching, not barrier removal;
- **host/kernel**: M4 Pro, the **non-`_nax`** `fp_gather_qmm_rhs` family;
- **cause of death**: occupancy rent. 3 840 → 7 680 B of tgmem takes resident
  threadgroups from **8 → 4** on a 32 768 B budget. `db2` recovers most of the
  pipelining benefit and still lands at −0.437 % because it is paying that
  rent;
- **not** cause of death: a small prize. The prize is +0.85 %, and `pf`
  collects it at 3 840 B.

## D2 — corrected decomposition of `db2 − dbmem`

The advisor's corrected figure is **+2.06 pp**; I measure **+2.13 pp** (run 1)
and **+2.085 pp** (run 2). Confirmed.

The decomposition is *not* "one barrier is worth 2 pp". `dbmem` runs **two**
`threadgroup_barrier` calls per k-iteration (a WAR barrier before the store
into the idle half, and the RAW barrier after it); `db2` runs **one**, because
with two tgmem halves the WAR hazard is structurally impossible. So the gap
buys two things at once:

| component | value | how measured |
|---|---|---|
| deleting one barrier | **≈ 0.83 pp** | `nobar − base` on the *single-buffer* kernel (rev2 measurement, +0.72 pp in the rev3 re-runs) |
| genuine load/MMA **overlap** | **≈ 1.23 pp** | residual |

and rev3 gives that residual an independent, direct measurement rather than
leaving it as a subtraction:

> **`pf − regstage` = +1.005 pp (run 1), +0.978 pp (run 2).**

`regstage` routes the loads through the same registers but issues them in the
original order, so `pf − regstage` is pure overlap with the barrier count,
tgmem, and register routing all held fixed. ≈ 1.0 pp measured directly against
≈ 1.23 pp inferred by subtraction — the same effect, and the direct number is
the one I would quote.

`regstage − base = −0.138 %` also settles a side question: **the register
detour itself is free.** Nothing in the mechanism's cost is the extra register
file traffic; it is all in the tgmem footprint.

## D3 — I withdraw "do not fund `_nax`", but I did not port `pf` to it

**Withdrawn.** The rev2 report argued the `_nax` port should not be funded
because the mechanism was small. That argument came from the M4 non-`_nax`
kernel and it does not carry to the ranked kernel. The ranked-M5 causal
census (`research/artifacts/tanjiro-pr170-receipt-ctrl.json` §3, paired
against the earlier `97a5090` control, S = 97.895 ms, W = 43.2619 ± 0.402 ms)
says the opposite about where the time is:

| probe | ΔW | % of W | σ |
|---|---|---|---|
| **S2** — extra staging | **+15.961 ms** | **36.9 %** | 35 |
| **S3** — staging with zero extra DRAM | **+7.853 ms** | **18.2 %** | 17.5 |
| **M2** — double MMA | +2.046 ms | 4.7 % | 4.5 |
| **B2** — two barriers | +0.841 ms | 1.9 % | — |

The ranked kernel is **staging-bound by roughly 4× over MMA** (36.9 % vs
4.7 %). `_nax` is where the money is, and rev2 was wrong to tell the advisor
to leave it alone.

**However — the specific mechanism in this PR has already been tried there and
it lost.** maple-tanjiro's `pf1` arm implemented depth-1 register prefetch on
the ranked `_nax` kernel: an 18-byte `WidePrefetch` struct, a
`kloop_prefetch` template parameter, host lever
`DARKBLOOM_NAX_KLOOP_PREFETCH` (default `"1"`), in
`kernels/fp_quantized_nax.h`, `mlx-generated/fp_quantized_nax.cpp` and
`quantized.cpp`, with tgmem held at 9 232 B. Official ranked M5 result:

> control S = **97.5250 ms** → candidate S = **98.2092 ms**,
> **ΔS = +0.684 ms — a regression**, declared null. Prefill CV is 0.103 %
> (≈ 0.1 ms), so that is a **6–7σ** move in the wrong direction.

That is a direct, ranked-hardware refutation of transferring `pf` to `_nax`,
and it is why I stopped rather than spending the remaining hours on a port.
**Do not fund a duplicate `_nax` register-prefetch port.**

The two results are consistent, and the reconciliation is the useful part.
`S3 / S2 = 49.2 %` says the ranked staging cost splits ≈ 49 % load-*issue* /
51 % DRAM *bytes* (`R-S3-C MIXED`). Register prefetch reorders loads earlier;
it removes neither issue slots nor bytes. On a kernel whose staging is
issue- and byte-bound it can only add register pressure — which is what
`+0.684 ms` looks like. On the M4 non-`_nax` kernel the limiter is the
serialization around the barrier, not the byte stream, so the same reordering
wins. **The `_nax` lever is fewer or wider staged bytes and fewer load
instructions, not more overlap.**

## D4 — the zero-tgmem register-prefetch variant (main deliverable)

Constraints held exactly as specified: **tgmem stays 3 840 B, resident
threadgroups stay 8**, paired ABBA against `base`, bit-exact output.

Three new arms, all at 3 840 B:

- **`pf`** — one register set. The device reads for tile *k* are issued
  *before* the RAW barrier and *before* the MMA for tile *k−1*, then written
  to threadgroup memory after it. Two barriers per iteration (unchanged from
  base). `next()` is called exactly `k_iterations` times.
- **`pf2`** — two register sets unrolled over k-parity, removing the
  register-level WAR.
- **`regstage`** — identical register routing, original issue order. Isolates
  the cost of the detour from the benefit of the overlap.

### Result (two independent full ABBA runs)

`ED_TAGS=base,nobar,dbmem,db2,regstage,pf,pf2 ED_PAIRS=4 ED_CBS=9
ED_SHAPE=both`, median of 9 command buffers after 3 warm-ups, ABBA × 4,
null control at both ends, n = 8 slots per variant.
Shapes: `gate_up` M=4096 K=2048 N=1024 (base 5.1794 / 5.1813 ms) and
`down` M=4096 K=512 N=2048 (base 2.5837 / 2.5839 ms), weighted 0.664 / 0.336.

| variant | gate_up r1 / r2 | down r1 / r2 | weighted r1 / r2 / **mean** |
|---|---|---|---|
| `nobar` | +0.82 / +0.82 | +0.54 / +0.51 | +0.726 / +0.716 / **+0.721** |
| `dbmem` | −2.44 / −2.33 | −2.86 / −2.85 | −2.581 / −2.505 / **−2.543** |
| `db2` | −0.08 / −0.03 | −1.19 / −1.19 | −0.453 / −0.420 / **−0.437** |
| `regstage` | −0.22 / −0.14 | −0.05 / −0.06 | −0.163 / −0.113 / **−0.138** |
| **`pf`** | **+1.07 / +1.10** | **+0.39 / +0.40** | +0.842 / +0.865 / **+0.853** |
| `pf2` | +0.84 / +0.90 | +0.05 / +0.02 | +0.575 / +0.604 / **+0.590** |

Run-to-run agreement is 0.02–0.05 pp on every arm, i.e. the ranking is not
noise. Three things worth reading off it:

1. **`pf` > `nobar`.** The mechanism is not "avoid a barrier"; it is "have the
   loads already in flight when you reach it".
2. **`pf2` < `pf`.** Doubling the register set to remove the register WAR
   *costs* 0.26 pp, so single-set WAR was never a limiter and the extra
   pressure is real. Depth-1, one set, is the right design point.
3. `down` gains less than `gate_up` (+0.39 vs +1.07). Smaller K = fewer
   k-iterations = less to overlap, which is the expected shape dependence.

### Against the advisor's ceiling

The advisor priced the ceiling at ~2.4 % of score with a ⅓ capture ≈ 2 ms of
S ≈ 0.75 % score, against a 1.35 % deficit to the crown (~1.1 % genuine code).
`pf` captures **+0.853 % of the kernel**, which is well inside that ⅓ band on
the M4 column (D5) — but the ranked column is the one that decides, and it is
≈ 0 because the ranked host does not execute this kernel. I am not going to
present the M4 number as progress against the crown deficit.

## D5 — score-reach arithmetic, one column per host, never mixed

### M4 column (this host; measured)

`kernel % × M4 kernel share × elasticity 0.502`

| arm | kernel % | × share 0.504 | × 0.502 | score |
|---|---|---|---|---|
| `nobar` (illegal) | +0.721 | +0.363 | | **+0.182 %** |
| **`pf`** | **+0.853** | **+0.430** | | **+0.216 %** |
| `db2` | −0.437 | −0.220 | | −0.111 % |

At the advisor's 0.485 share the `pf` figure is **+0.208 %**; I quote the
0.504 corrected share (D6) as primary and both are within 0.01 pp.
Advisor's worked example reproduced for calibration:
`0.83 × 0.485 × 0.502 = +0.202 %`. ✓

*One derivation I could not reproduce and would like:* with a prefill-only
mechanism and `score = decode_sp^0.75 × prefill_sp^0.25`, a 0.430 % faster
prefill is `1.00430^0.25 = +0.107 %` of score, i.e. an elasticity of 0.25,
not 0.502. I have used 0.502 as instructed because the advisor owns the
elasticity, but the two differ by exactly 2× and I would rather flag that than
quietly pick one. If 0.502 folds in a decode contribution, note that on M4
this mechanism is prefill-only — decode drives `M = 1` and does not reach the
aligned branch I rewired.

### M5 column (ranked; projection, and the projection is refuted)

Ranked window **W ≈ 43.26 ms ≈ 44 % of S ≈ 97.86 ms**, elasticity **0.362**,
i.e. **1 ms off S ≈ 0.37 % of score**.

*If* the mechanism transferred at the same kernel percentage:
`0.853 % × 43.26 ms = 0.369 ms of S` → `× 0.37 %/ms` ≈ **+0.137 % score**.

**It does not transfer.** Two independent reasons, either sufficient:
(a) the landed code is in the non-`_nax` family and the M5 never dispatches
it; (b) the mechanism itself was measured on `_nax` by tanjiro's `pf1` at
**+0.684 ms of S, ≈ −0.25 % of score** (D3). The honest M5 entry for this PR
is **0.000 %**, and the `_nax` entry for the mechanism is **negative**.

The two columns are never added, averaged, or carried across.

## D6 — minor corrections

- **Dispatch count.** The routed gather-GEMM dispatches **38** times per
  prefill, not 39. The corrected kernel-time share is **50.4 %**, not 51.8 %.
- **Roofline.** **16.85 GMAC at 3 326 GMAC/s**, not 16.6 GMAC at
  3 274 GMAC/s.
- **Only paired ratios reproduce.** Between-run absolute drift on this rig is
  ±2.2 %. Every number I quote as a Δ is a within-run paired ratio and both
  runs agree to ≤ 0.05 pp. Every *absolute* — including the 50.4 % share,
  which divides a rig projection by a harness wall time captured in a
  different session — is **not** safe to carry across runs and should be read
  as one significant figure. That caveat applies to the share used in the D5
  M4 column: it moves the answer by ±0.01 pp at ±2.2 % drift, so it does not
  change any conclusion, but the share itself should not be quoted as
  precise.

## Submission recommendation

**I am not requesting a submission slot**, per the rule as given to me
(published receipts cannot resolve a 0.07 % landing bar against a 0.4–0.9 %
receipt sd; decide on the local rig; only maple-fern submits). Nothing here
would survive that arithmetic anyway, because the ranked expectation is
0.000 %.

Concretely, for the advisor's merge decision:

- **Merging into the research base is safe and I recommend it** — the code is
  bit-exact, adds no threadgroup memory, costs 6 832 B of a 262 144 B growth
  budget (`current=2688038/3000000 headroom=311962 files=142`), and preserves
  a mechanism that is worth ~0.2 % on any non-NAX host.
- **Do not include it in an official submission** unless the ranked host
  changes. It is dead code on the M5.
- **Reverting is one command** (then rebuild the metallib):

  ```bash
  git checkout 30904ecb -- \
    Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized.cpp \
    Vendor/mlx-swift/Source/Cmlx/mlx-generated/gemm.cpp \
    Vendor/mlx-swift/Source/Cmlx/mlx-generated/quantized_utils.cpp \
    Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized.h \
    Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/quantized_utils.h \
    Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/steel/gemm/loader.h
  ./tools/build-mlx-metallib.sh
  ```

**One residual risk I will not hide.** The additions to `fp_quantized.h` and
`quantized_utils.h` also land in the corresponding `mlx-generated/*.cpp`
preambles, which MLX JIT-compiles at runtime per kernel name. Roughly 70
extra lines of *uninstantiated template* text are parsed by every JIT
compilation from those two preambles. I did not measure that cost; template
bodies that are never instantiated are parse-only, and the preambles are
already thousands of lines, so I expect it to be far below noise — but on the
ranked host it is a pure cost with no offsetting benefit, which is a second
reason to keep this out of a submission.

## Protocol note — `§0P.8` / `§0P.9` are not in this checkout

I complied with the rule as stated to me (decide locally; do not request a
submission slot; only maple-fern submits). For the record, **neither `§0P.8`
nor `§0P.9` exists anywhere in this checkout** — I grepped `research/`,
`senpai/`, and the root `*.md` set, and a separate agent confirmed it
independently. The rule reached me only through the assignment text. If it is
meant to be citable, it needs to land in a tracked file.

---

# Appendix A — rev1 / rev2 report

Retained verbatim for provenance. Its *verdict* is superseded by the rev3
sections above: the STOP stands for the tgmem-double-buffering mechanism
(now `N-GEMM-TGMEM-DB-OCCUPANCY-RENT`), the "do not fund `_nax`"
recommendation is **withdrawn** (D3), and the "the prize is too small"
framing is **wrong** (D4).

## The stop rule

> If deleting the write-after-read barrier is worth **< 3 %** of
> `nvfp4_gather_qmm_rhs_nt` kernel time, stop.

Measured, kernel-time weighted: **0.83 %**. Rule fires with a 3.6× margin.

## Method

`research/edward_r110_gemm_db_bench.swift` is a standalone Swift + Metal rig
that reproduces the shipped kernel exactly rather than approximating it. It
extracts the `R"preamble( ... )preamble"` body from
`Vendor/mlx-swift/Source/Cmlx/mlx-generated/{utils,quantized_utils,gemm,fp_quantized}.cpp`
in the same order `get_gather_qmm_kernel` uses
(`jit_kernels.cpp:952-975`), appends the shipped template instantiation

```
nvfp4_gather_qmm_rhs_nt_bfloat16_gs_16_b_4_bm_16_bn_32_bk_32_wm_1_wn_2
```

and compiles it with `fastMathEnabled = false` to match `device.cpp:630`.
Function constants 200/201/202 (`align_M/N/K`) are all `true`; buffer indices
follow `quantized.cpp:1776-1789`. Every variant is produced by **string
mutation of that extracted source**, so no vendored file is edited and no MLX
rebuild is required — which is also why this experiment could run at all
without touching the submission surface.

Timing is `cb.gpuEndTime - cb.gpuStartTime` over `ED_REPS` dispatches, median
of `ED_CBS` command buffers after 3 warm-ups, with the variant list swept
ABBA (forward then reverse) `ED_PAIRS` times and an empty-kernel null control
at both ends. Observed spreads are 0.0–0.7 %, and the headline numbers
reproduced across two independent full runs.

### Variants

| tag | mutation | threadgroup memory |
|---|---|---|
| `base` | shipped source, unmodified | 3840 B |
| `nobar` | WAR barrier deleted — **numerically wrong**, upper-bound probe only | 3840 B |
| `db` | true ping-pong, runtime `cur` parity | 7680 B |
| `db2` | true ping-pong, unrolled parity | 7680 B |
| `dbmem` | 2× staging allocated, shipped single-buffer schedule — **bit-identical to base** | 7680 B |
| `noload` | `load_unsafe()` removed, both barriers and the mma kept | 3840 B |
| `nomma` | mma removed | **0 B — invalid, see below** |

`dbmem` is the control that makes this experiment interpretable: it pays the
double-buffer *footprint* without receiving any of its *benefit*, so
`db2 − dbmem` isolates the pipelining mechanism from the occupancy tax it
requires.

The ping-pong variants need no loader edits: both `QuantizedBlockLoader`
(generated `fp_quantized.cpp` ~517) and `mlx::steel::BlockLoader`
(`gemm.cpp:62`) expose a public mutable `dst`, so the buffer flip is
`loader.dst += / -= tile`.

## Results (M4 Pro, `ED_PAIRS=4 ED_CBS=9 ED_REPS=4`, n=8 slots/variant)

`gate_up` M=4096 K=2048 N=1024 · `down` M=4096 K=512 N=2048 · 256 experts,
group_size 16. Null control 0.0275 / 0.0248 ms.

| variant | gate_up ms | vs base | down ms | vs base | weighted |
|---|---|---|---|---|---|
| base | 5.0659 | — | 2.5610 | — | — |
| `nobar` (invalid) | 5.0163 | **+0.98 %** | 2.5472 | **+0.54 %** | **+0.83 %** |
| `db` | 5.2088 | −2.82 % | 2.6549 | −3.67 % | −3.11 % |
| `db2` | 5.0680 | −0.04 % | 2.5938 | −1.28 % | −0.46 % |
| `dbmem` | 5.1833 | −2.32 % | 2.6352 | −2.90 % | −2.51 % |
| `noload` | 4.2882 | +15.35 % | 2.1871 | +14.60 % | +15.10 % |

Weighting is by measured kernel time across 39 MoE layers (gate_up 197.6 ms
= 0.664, down 99.9 ms = 0.336). Raw logs in `logs/`.

`nomma` reported +96 % but its pipeline threadgroup memory is **0 B**, which
proves the compiler dead-code-eliminated the whole staging chain once nothing
consumed it. **It is an invalid probe and is excluded from every conclusion.**
I am reporting it rather than deleting it because the 0 B pipeline-state
readback is the mechanism that caught it, and that check is worth reusing.

## Causal decomposition

This is the part worth keeping.

1. **The footprint alone costs 2.51 %.** `dbmem` runs a bit-identical
   schedule to `base` and is 2.3–2.9 % slower purely because 3840 → 7680 B
   drops resident threadgroups per core from 8 to 4.
2. **The pipelining mechanism is real but cannot repay its own rent.**
   `db2 − dbmem` = **+2.06 pp**: against the same doubled footprint,
   overlapping the load with the mma genuinely wins. It just wins less than
   the footprint costs. Net **−0.46 %**.
3. **Runtime-parity addressing costs another 2.65 pp.** `db − db2`. Any
   implementation that cannot fully unroll the parity is far worse still.
4. **The entire exposed load chain is only 15 % of kernel time.** `noload`
   deletes device loads, NVFP4 dequant and threadgroup stores, keeping both
   barriers and the mma, and buys 15.10 %. So ~85 % is mma + barriers +
   control + store. **The kernel is mma-issue bound, not load-latency
   bound**, and double buffering optimises a resource that is not the
   constraint.

That is the whole result: latency is already hidden by inter-threadgroup
parallelism (3.84 KB of threadgroup memory, small register footprint, 8192
threadgroups on an 8-core-cluster part), so intra-threadgroup double
buffering can only add instructions and subtract occupancy. The −2.5 %
regression is the expected outcome, not a tuning failure.

## Roofline cross-check

Independent arithmetic agrees. For `gate_up`: 8.59 GMAC useful, ×1.96
segment-restart amplification (below) = 16.6 GMAC executed in 5.066 ms =
**3,274 GMAC/s ≈ 6.55 TFLOP/s**, which matches the independently measured
R109-D figure of 3,158 GMAC/s — i.e. the kernel is running at achieved mma
throughput. DRAM traffic is ≈583 MB per gate_up layer-set ≈ 115–130 GB/s
against a ~273 GB/s ceiling (~42 %), so it is not bandwidth bound either.

## Kernel-time share on this host (Stage-0 item 3)

The brief prices this family at 48.5 % of M4 prefill GPU time. My rig gives an
independent cross-check without a harness profile: the 39-layer projection is
gate_up 197.6 ms + down 99.9 ms = **297.5 ms**, against a local baseline
prefill of S = 0.001122769125 s/token × 512 = **574.7 ms**
(`score.local-iterate.json` @ `9469ac4d`) — a **51.8 %** share. That is
consistent with 48.5 % and I am using the brief's figure below.

Caveats: this compares a synthetic-routing microbenchmark projection against
harness wall time, and assumes one dispatch of each shape per MoE layer. I did
**not** run a `SPLIT=1` harness profile, because there is no runtime change to
profile — see the limitations section.

## Score reach — and where I have to correct myself

Using the brief's prefill elasticity of 0.362 (1 ms off S ≈ 0.37 % score),
**not** the raw 0.25 exponent:

| arm | kernel time | × 48.5 % share | × 0.362 | vs 0.11 % bar |
|---|---|---|---|---|
| `nobar` (illegal ceiling) | +0.83 % | +0.403 % of prefill | **+0.146 % score** | *above* |
| `db2` (implementable) | −0.46 % | −0.223 % of prefill | **−0.081 % score** | negative |

I want to be precise about this rather than round it my way. The *ceiling* —
a kernel that computes the wrong answer — is worth about 0.15 % score, which
is modestly **above** the 0.11 % landing bar. Even at an absurd 100 % share
it would only reach 0.30 %. What actually decides the arm is the other two
facts:

- the **preregistered** rule was 3 % of kernel time and the measurement is
  0.83 %, so the rule fires on its own terms with a 3.6× margin; and
- every legal implementation of the mechanism measures **negative**
  (−0.46 % weighted, −0.081 % score), because the staging footprint costs
  more than the pipelining returns.

So the correct statement is not "the prize is too small to see" — it is
"the prize is small, and the only way to collect it costs more than it pays."

## Two findings that change what should be funded next

### 1. The segment-restart tax is 48 % — and the ranked path already fixes it

I added an `ED_IDX=aligned` control: identical weight bytes, identical useful
MAC count, but exactly one expert per BM=16 row tile instead of the
multinomial routing that makes most tiles straddle an expert boundary.

| shape | multinomial | aligned | tax | K-loop ratio |
|---|---|---|---|---|
| gate_up | 5.1815 ms | 2.6630 ms | **48.60 %** | 1.961× |
| down | 2.5882 ms | 1.3467 ms | **47.97 %** | 1.961× |

Time scales at 1.945× against 1.961× more K-loop executions — near-perfectly
linear, which is an independent confirmation that the kernel is issue bound.
`noload` is 15.4 % / 16.1 % in *both* routings, so the load:mma balance is
invariant to routing; the ~15 % load share is a robust property of the
kernel, not an artefact of the index distribution.

**But this does not transfer.** `quantized.cpp:1669` routes to
`gather_qmm_rhs_nax` whenever `is_nax_available()`, so the ranked M5 never
dispatches the kernel I measured. And the kernel it does dispatch,
`fp_gather_qmm_rhs_expert_nax`, is **expert-major by construction**: it
iterates expert slots, binary-searches `[run_start, run_end)`, and chunks
that run by BM (`fp_quantized_nax.cpp:1900-1975`), so every K-loop covers
rows of exactly one expert. The 48 % I measured is already zero on the ranked
path.

I am reporting this as the correction it is. Before I ran the aligned
control, "48 % of mma work is wasted on out-of-segment rows" was my headline
follow-up recommendation. It would have been a wasted assignment. Reporting
it as a *negative transfer* result is the actual deliverable.

### 2. The `_nax` port (Part 2) should not be funded

Byte figures, since the assignment asked for them: `kWsElems = BN × BK_padded
= 64 × 72 = 4608` elems × 2 B = **9216 B**, +8 B bounds = **9224 B**.
Doubled = **18,440 B**, which does fit under 32,768 B. But fitting is the
wrong test:

- **Occupancy collapses harder than on M4.** 32768/9224 = **3** resident
  threadgroups; 32768/18440 = **1**. That is a 3× reduction, where the 2×
  reduction I measured on M4 already cost 2.5 %. (Threadgroup limit measured
  on M4; if M5 offers 64 KB the reduction is 6→3, still 2×, still at least as
  bad as the measured tax.)
- **The cheap half of the overlap is already shipped.** `_nax` hoists the A
  operand into registers before the WAR barrier
  (`kernels/fp_quantized_nax.h:1875-1888`); only Ws staging sits between the
  two barriers, so there is less left to win than in the kernel I measured.
- **`gate_up_stage` aliases `Ws_storage`** (`h:1738-1739`, written
  `:1985-1988`, consumed `:1990-2011`), so any doubling must also
  de-alias the swiglu epilogue — more code, more footprint.
- Larger tiles (BM=BN=64, BK=64) mean *higher* arithmetic intensity than the
  kernel I measured, so `_nax` is if anything **more** mma-bound and **less**
  load-bound. The sign of my result transfers; the magnitude gets worse.

Recommendation: do not spend M5 receipts on the `_nax` double-buffer port, and
do not produce the Part-2 handoff to maple-fern. I have not written a
`READY.md` for it. If the advisor wants it anyway, the port is understood and
the byte budget is above.

## What I would not recommend chasing

- **Raising BM above 16** on the non-`_nax` kernel. My own first instinct;
  a frontier review of the dispatch geometry puts it at 2.93× executed work
  at BM=32 — strictly worse. Recorded so nobody re-derives it.
- **Predicated store instead of K-loop restart.** Not reachable bit-exact.
- **BK=64 / register-A on the non-`_nax` path.** ≤5 % cleanups on a kernel
  the ranked M5 does not run.

## One thing genuinely worth a look (unmeasured, flagged not recommended)

At the shipped variant-5 geometry (`bm=64, wm=4, wn=1`, `quantized.cpp:1385`)
`SM = BM/WM = 16`, while prefill routing gives ≈16 rows per expert on average
(512 tokens × 8 experts / 256 experts). Since `sgp_sm = min(SM, max(0,
chunk_rows - tm))` gates simdgroups, a typical 16-row expert run leaves 3 of
4 simdgroups inactive for that chunk. I could not measure this — the kernel is
unreachable on gen-16 hardware — and the `DARKBLOOM_*` macros show this kernel
has already been worked over hard, so this may well be known and already
priced. I am flagging it with source pointers rather than proposing it as an
assignment.

## Reproduction

```bash
ED_TAGS=base,nobar,db,db2,dbmem,noload ED_PAIRS=4 ED_CBS=9 ED_REPS=4 \
  research/edward_r110_run_bench.sh          # variant table
ED_IDX=both ED_TAGS=base,noload \
  research/edward_r110_run_bench.sh          # segment-restart tax
```

Requires Metal; no model weights, no network, no benchmark lock. Runs in
~10 s. Research-only — neither file is on `editablePaths`.

## Honest limitations

- Everything here is M4 Pro, gen-16, on a kernel family the ranked M5 does
  not dispatch. The mechanism conclusion (staging footprint costs more than
  pipelining returns, in an mma-bound kernel) is what transfers; no absolute
  number does.
- `nobar` is not a legal kernel; it exists only to bound the prize.
- `nomma` is invalid (dead-code eliminated) and excluded.
- **Several reporting-contract items are not applicable and I did not fake
  them.** No `SPLIT=1` harness profile, no `--local-iterate` paired ABBA, no
  harness correction factor, no `FERN_DEFEAT_SLOTS=64` residency-defeated
  number, no `run_upstream_equivalence.sh` non-zero-count pass, and a
  deliberately empty `git diff --numstat` on the submitted surface — because
  the Stage-0 refutation fired before any runtime code was written, so there
  is no candidate to profile, time, correct, or validate. The ABBA discipline,
  null-control bracketing and preregistered threshold were applied to the
  microbenchmark instead.
- The `_db` name-collision precaution (MLX caches libraries by kernel name,
  `device.cpp:602, 770`) never became relevant: the rig compiles each variant
  into its own `MTLLibrary` from mutated source, so there is no shared cache
  to collide in.
- No M5 receipt was spent, by design: the stop fired at Stage 0.
- Ownership: I touched nothing in `quantized.cpp`, so the deconfliction split
  with maple-tanjiro's PR #692 is trivially intact.

---

## Addendum — answer to advisor feedback 5247182180 (2026-08-10T23:28Z)

This addendum was written after the terminal result at commit `86679f40` was
posted. It adds no code and changes no measurement; it answers the questions
the advisor raised and closes out one lead I had left open.

### 1. The WAR-barrier probe answer: 0.83 %, so no re-weighting

The advisor asked me to run the cheap WAR-barrier refutation first and, **if
the probe says >= 3 %, to say so in the PR immediately** so the team could be
re-weighted toward this arm.

The probe says **0.83 %**, not >= 3 %. Stated explicitly so the advisor does
not have to infer it from the tables above:

- Deleting the WAR barrier alone (`nobar`, an illegal kernel that races) buys
  +0.98 % decode-shape and +0.54 % prefill-shape, i.e. **0.83 % weighted** of
  `nvfp4_gather_qmm_rhs_nt` time.
- The preregistered Stage-0 stop threshold was 3 %. The margin is 3.6x in the
  direction of stopping.
- **No re-weighting toward this arm is warranted.** The arm is terminal and
  Part 2 (the `_nax` port) should not be funded. The reasons are in the
  Findings section above: the ranked M5 takes `gather_qmm_rhs_nax`, doubling
  `Ws` 9,224 -> 18,440 B collapses residency 3 -> 1 TG/core, the A operand is
  already register-hoisted, and `gate_up_stage` aliases `Ws_storage`.

### 2. Repricing against the newly-stated 1.407 % deficit

The feedback restates maple's real gap to the crown as **~1.407 %** (three
replays of the `4b0e051b` surface, mean 2.58020 vs crown 2.61650, sd 0.545 %),
which is ~200 us/step of M4 decode wall or ~3.8 ms off S.

Against that target this arm is not close:

| quantity | value | vs 1.407 % gap |
| --- | --- | --- |
| `nobar` ceiling (illegal, races) | +0.146 % score | ~10x short |
| implementable arm (`db2`, best legal variant) | -0.081 % score | wrong sign |

The `nobar` number clears the replacement for the withdrawn 0.378 % bar
(~0.11 %), which is why I reported it against my own verdict rather than
suppressing it -- but it is a ceiling on an illegal kernel, and every legal
variant I measured is negative. Nothing here contributes to the 1.407 %.

### 3. Closing the one lead I left open: the idle-simdgroup observation

The main report flagged, without verifying, that the ranked `_nax` expert
kernel appears to leave simdgroups idle at mean routing. I verified it from
source this session (read-only; no files modified). It is real, it is
**already known**, and I recommend **against** staffing it.

Verified, in `.../metal/kernels/fp_quantized_nax.h` and `.../metal/quantized.cpp`:

- Shipped geometry is `darkbloom_stage_bm128_variant()` default **5**
  (`quantized.cpp:1250-1256`) => `bm=64, bn=64, bk=64, wm=4, wn=1`
  (`quantized.cpp:1377-1387`), so `SM = BM/WM = 16` and `TM=1, TN=4, TK=2`
  (`fp_quantized_nax.h:1759-1774`).
- `tm = SM * (simd_group_id / WN)`, `sgp_sm = min(SM, max(0, chunk_rows - tm))`,
  `sg_active = sgp_sm > 0` (`:1766, :1824-1826`). At mean routing
  (512 tokens x top-8 / 256 experts = **16 rows per expert**) only `sgid = 0`
  is active: **1 of 4 simdgroups does MMA while all 4 stage weights.**
- An inactive simdgroup still clears `Dtile` (`:1828-1829`), builds its loader
  (`:1836-1846`), **fully participates in the cooperative `Ws` load**
  (`:1899, :1901, :1934`, outside the `sg_active` guard) and hits every barrier
  (`:1889, :1903, :1940, :1989, :2012`). It skips only the A-tile loads
  (`:1876-1886`) and the MMA loop (`:1905-1928`). It cannot exit early.

**Why the obvious fix is not a win.** The naive move is to re-partition
`WM=1, WN=4` so all four simdgroups get MMA work. But the MMA tile-op count is
**100 % compile-time** and is never bounded by `sgp_sm`: `tile_matmad_nax`
loops over the `TM`/`TN`/`TK` constants
(`steel/gemm/nax.h:996-1000, :1014-1018`) and `Atile` is a compile-time-sized
`NAXTile<T,TM,TK>` whose invalid rows are **zero-filled**
(`nax.h:138-167, :813-825`). So `WM=1, WN=4` gives `TM=4, TN=1`: 4x the
A-fragment registers and the *same* per-simdgroup MMA instruction count. The
idle simdgroups are not burning issue slots that a re-partition would recover;
re-partitioning moves the same total MMA work around rather than creating
parallelism.

**Two hard locks on top of that.** (a) The dispatch predicate requires
`wm == 4` (`quantized.cpp:1404-1408`; `wn` may be 1 or 2, but `wm` is fixed and
no `bm128` case emits `wm == 1`), so a WM=1 geometry needs edits to both the
switch at `quantized.cpp:1381-1387` and the predicate at `:1407`. (b)
`kSwigluRegLocal = (WN == 1) && (BN == 64) && ((BM/WM) == 16)`
(`fp_quantized_nax.h:1785-1786`), so any WM/WN change also disables the
register-local swiglu epilogue -- a known-good optimization that would have to
be re-won.

**Prior art / duplicate.** This is maple-alphonse's R107C section 8 finding
(`research/maple-alphonse-r107c-expert-gather-gemm-floor.md:504-524`): "1 of 4
simdgroups per threadgroup does any MMA work, while all 4 stage weights"; "the
kernel is weight-staging bound at mean routing", flagged there with the same
two obstacles. Alphonse's section 9.5(b) additionally records tanjiro's R106-F'
measurement that this family is **51.6 FLOP/B -- compute-bound on M4 but
DRAM-bound on M5** (M5 machine balance 63.5-104), at 22.64 TFLOP/s on M5, with
the caveat that anyone taking section 8 forward must first split the family's
FLOPs and bytes by routed vs shared before assuming 4x headroom.

**Recommendation: do not staff it.** Compile-time TM/TN plus zero-filled A rows
remove the naive 4x; the `wm == 4` gate and the `kSwigluRegLocal` lock make the
change expensive; and the family is DRAM-bound on the ranked M5, where more MMA
parallelism is not the binding constraint. I am recording this as a closed lead
rather than a new prize.

### 4. Ownership and protocol

`quantized.cpp:1380-1520` is maple-tanjiro's range under the binding split, so
any WM/WN geometry move belongs to him or needs advisor arbitration. I touched
nothing in `quantized.cpp` in this arm, so the deconfliction with PR #692
remains trivially intact. Per the feedback I have not submitted officially and
have not composed with tanjiro's A1; only maple-fern submits.

_This addendum was written by an AI agent (OpenHands) acting as student
maple-edward._

