# Pre-registration — `DARKBLOOM_STAGE2_GATHER`, PR #40 (maple-fern)

Written and committed **before any official receipt for this branch exists**.
Assignment `maple-2026-08-05a-nax-stage2-double-buffer`, revision `r1`,
base `279b6e2409a2ca92f7b874e08a3dabc2c6ff4a0b`
(docs-only advance accepted at `ed02e9e69427f774628aaf69fee106931e7bc7cb`).

## What shipped as a lever

`DARKBLOOM_STAGE2_GATHER` is now an **integer** selector, resolved once per
process by one shared parser (`quantized.cpp: darkbloom_stage2_gather_variant()`)
so the JIT `#define` and the dispatch-site trace can never disagree:

| value | arm | threadgroup `Ws` | barriers / k-iter |
|---|---|---|---|
| `0` | inert control — preprocesses byte-identically to stock | 9,216 B | 2 |
| `1` | Deliverable-A double buffer: stage tile k+1 into the other half while MMA reads tile k | 18,432 B | **1** |
| `2` | **shipped default** — device 4-bit loads + scale reads hoisted into 18 B/thread registers across the loop back-edge; single `Ws`; both barriers kept | 9,216 B | 2 |

Ranked runs use default env only, so each arm is a **separate submission with a
different compiled-in default**, never an env-var flip.

## Why the default is 2 rather than the literal Deliverable A

The assignment names occupancy as "the risk being tested". Two facts settle the
prior before any receipt:

1. Apple per-core threadgroup SRAM is ~32 KB. At 9,216 B roughly **three**
   threadgroups are co-resident per core; at 18,432 B roughly **one**. The
   expert dispatch launches `grid.x = N/bn = 16`, `grid.y = egroups = 256`, i.e.
   **4,096 threadgroups**, so co-residency is the mechanism that hides DRAM
   latency here.
2. Variant 1's *unique* gain over variant 2 is only the 31 removed barriers
   (`K_it = 2048/64 = 32`), tens of nanoseconds each. That cannot pay for a
   2-3x co-residency loss.

Variant 2 targets the same serialisation without spending any threadgroup
memory: the **device-load latency** is what sits between the two barriers with
no arithmetic in flight. Carrying `StageRegs` (16 B packed weights + 2 B scales
per thread) across the back-edge issues iteration k+1's loads *before* the WAR
barrier and consumes them *after* it, so DRAM latency hides behind iteration k's
MMA. Register cost is 18 B/thread against ~80-128 registers already live, so
variant 2 has no occupancy cost at all.

## Pre-registered predictions

Sign convention: `ΔS = S_candidate − S_control` in ms, where
`S = 512000 * prefill_s_per_tok`. **Negative is a win.**

Conversion uses the advisor's own elasticity: +5.3% of score per 15.4 ms
recovered => **0.344% of `ns` per ms**.

| arm | point `ΔS` (ms) | 80% interval | point `ns` | mechanism claim |
|---|---|---|---|---|
| v0 control | 0.0 | [−0.6, +0.6] | 2.5297 | flag-OFF is stock; this family also measures same-window session drift |
| v1 double buffer | **+1.5** | [−4, +10] | 2.5166 | barrier saving is real but negligible; occupancy loss dominates |
| v2 register prefetch | **−4.0** | [−9, +1] | 2.5647 | ~25% of the 15.4 ms overlap gap is device-load latency, recoverable at zero occupancy cost |

Derived predictions for v2: `ns ≈ 2.5647`, i.e. **+1.38%** over the
`ns = 2.52973` frontier — above the 0.243% two-family 2σ floor.

Explicit falsifiers, all of which I will report as-is:

- **Correctness.** `max_abs_diff` must be **exactly 0** for both v1 and v2. A
  non-zero diff, however small, falsifies the bit-exactness claim outright.
- **Treatment reached.** Every receipt must carry
  `mlxfast: fusion active: stage2_gather v<N>` on stderr, and the dispatch-site
  line must show `expert=1`. A missing or `inactive` line means the run measured
  its own control and the number is void.
- **Null.** If both v1 and v2 are confirmed active, bit-exact, and land inside
  ±0.243% of the v0 family, the ~41%-overlap diagnosis is dead as a
  *scheduling* problem and the remaining 15.4 ms belongs to F2
  (staging-free B path) or to the 1.456x MMA row padding. That is the
  reported finding; I will not go looking for a rescue mechanism.
- **Wrong-sign v2.** If v2 regresses while v1 wins, the binding term was the
  threadgroup **store**/dequantize throughput rather than device-load latency,
  and the register carry merely lengthened the dependence chain.

## Local-evidence limitation, stated up front

This host is an M4 Pro. `quantized.cpp` routes to `gather_qmm_rhs_nax` only
under `metal::is_nax_available()`, which needs `arch_gen >= 17`; this host probes
`applegpu_g16s`, gen 16. **No `_nax` kernel runs here at all.** Local
`--local-iterate`, `run_upstream_equivalence.sh`, and `swift test` therefore
prove only that the untouched paths did not regress. The kernel itself is
evidenced locally by `research/nax_msl_compile_check.sh`, which compiles the
generated twin offline with the real Metal toolchain at both static Laguna MoE
shapes (`K=2048,N=1024` and `K=512,N=2048`) for all three variants, and by a
preprocessed-source diff proving variant 0 is byte-identical to stock.
Ranked evidence is official M5 receipts only.
