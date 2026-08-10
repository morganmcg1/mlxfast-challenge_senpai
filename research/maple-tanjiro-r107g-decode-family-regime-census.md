# R107-G — decode-family regime census (maple-tanjiro, PR #648)

`α = 0.4369, β = 0.5 two-pool map, residual −6.63 %, #561`

Host tag: **AWS M4 Pro, `applegpu_g16s`, Apple GPU gen 16, 20 GPU cores, 48 GiB unified,
macOS 26.5.2, Metal toolchain 17.6.109.0.** Epoch tag: **advisor tip `acb56108`,
`LagunaRuntimeModel.swift` sha256 `a736b50f…d850c4`, 12,147 lines.**
Every number below is measured on **M4**; M5 numbers are quoted only where the charge
supplies them, and are always marked.

## VERDICT TABLE (incremental — one row committed as each family's ladder lands)

| family | kernel | regime verdict (measured) | dose slope, exposed µs / fma-per-thread | implied k | 0.4 % bar (instr/thread) | 0.4 % bar (bytes/step) | rule 55 |
|---|---|---|---|---|---|---|---|
| D | T2c routed gate+up QMV | **BYTES** (86.4 % of measured DRAM peak; 95.5 % marginal) | 0.003313 (base) → 0.015645 (high dose); pure-ALU slot = 0.038044 | **α = 0.4369** | 465 = 3.64× the whole base ALU load ⇒ unreachable | 15.10 MiB/step = 4.55 % of the family's own bytes | **CONFIRMS CLOSURE** |
| A | T3b oproj h64 | _pending_ | | | | | |
| B | T2d routed+shared down+residual | _pending_ | | | | | |
| C | T0b(a) qkv h64 lane-major | _pending_ | | | | | |
| E | T2b gate_sp h64 | _pending_ | | | | | |

## 0. Base-hygiene statement (no rerun, no re-baseline)

The branch `maple-tanjiro/r107-decode-family-regime-census` was rebased from its
assignment commit `04c7ac47` onto advisor tip `acb56108`; my HEAD is a
docs/instruments-only descendant. The advisor branch advanced
`1decfba9 → 4e9a8e16 → 8695fb0e → acb56108` while this assignment was open. That
advance is **docs-only**:

```
$ git diff --numstat 1decfba9 acb56108 -- $(jq -r '.editablePaths[]' benchmark.json) benchmark.json Package.swift Sources/ Vendor/
(empty)
```

Only `research/` changed. **Therefore no measurement in this report needs rerunning and
no baseline needs re-taking**, and every carried prior from R107-D (#642) is still
in-epoch.

## 1. Instrument: the ALU issue ceiling had to be re-derived first

The assignment asks for "% of theoretical peak issue (re-derive)". The campaign has been
quoting **4.04e12 fma/s** (= 20 cores × 128 lanes × 1.578 GHz). Before that could be used
as a denominator I measured it, because a first pass at family D produced an *impossible*
number: the high-dose marginal slope implied 8.4e12 fma/s, i.e. 2.1× the quoted ceiling.

`research/maple-tanjiro-r107g-alu-ceiling.swift` — a dependency-free fp32 fma kernel
(8 independent accumulators per thread, rolled trip loop over {256, 512, 1024, 2048},
result sunk through an unreachable `if (r == 1e37f)` compare so nothing is dead-code
eliminated), best-of-15 rounds × 50 dispatches, run at each family's *own* geometry:

| geometry | threads | marginal µs per fma-per-thread | measured ceiling | vs quoted 4.04e12 | implied clock @ 20×128 |
|---|---|---|---|---|---|
| 2048 TG × 64 thr (family D) | 131,072 | **0.038044** | 3.4453e12 fma/s = 6.891 TFLOP/s | 0.853 | 1.346 GHz |
| 256 TG × 64 thr (family A) | 16,384 | **0.004506** | 3.6364e12 fma/s = 7.273 TFLOP/s | 0.900 | 1.420 GHz |

Artifacts: `research/artifacts/maple-tanjiro-r107g/stage1-ALU-ceiling-s1-tgs{2048,256}-tpt64.txt`.

Two consequences, both load-bearing for the rest of the report:

1. **The quoted 4.04e12 is an optimistic but roughly correct ceiling.** Sustained is
   85–90 % of it, at both grid sizes, with the two independent geometries agreeing to
   within 5.5 % on the derived fma/s. I will use the **measured, geometry-matched**
   0.038044 / 0.004506 µs-per-slot as the issue denominator, not the quoted number.
2. **The anomaly inverts, and that inversion is the family-D result.** Added fma on the
   real kernel cost *less* than the pure-ALU slot price (0.015645 vs 0.038044 at high
   dose; 0.003313 at the base operating point). An added instruction cannot be cheaper
   than a machine slot unless it is being hidden. So the correct reading is not "the
   ceiling is wrong" but **"the shipped kernel's ALU is 91 % hidden under memory stall at
   its operating point"**. That is a regime verdict, measured, not assumed.

Occupancy match for the denominator: both the QMV kernel and the ALU probe report
`tgMemB = 0`, `maxTotalThreadsPerThreadgroup = 1024`, `threadExecutionWidth = 32`, and
both are dispatched at 64 threads/TG. Residual register-pressure differences are the main
threat to this denominator; see §T.

## 2. FAMILY D — T2c routed gate+up QMV — regime **BYTES**, k = α = 0.4369

Anchors re-derived by `grep -n` (Stage 0): `lagunaRoutedSwiGLUQMVPackedTop8Kernel:7892`,
`…R1Kernel:7915`, wrapper `lagunaRoutedSwiGLUQMVPackedTop8:8030` (R1 branch `:8045`,
non-R1 `:8056`), call site `:10856`. The four given anchors for this family were all
correct. Kernel measured:
`laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2`.

### 2.1 Instruments and the "do not touch `Sources/`" route

`LagunaRuntimeModel.swift:7892-8065` is edward's reserved range, so the literal was never
edited, not even transiently. `research/maple-tanjiro-r107g-qmv-dose-gen.py` imports
fern's `research/fern_r99_qmv_variants.py` and re-emits the shipped MSL into
`research/artifacts/maple-tanjiro-r107g/qmv_dose{0,4,8,16}.metal`, compiled entirely
outside the tree by fern's `research/fern_r99_qmv_probe.swift`.

**Literal-drift gate (passed):** `qmv_dose0.metal` (9,561 B, 269 lines) is **byte-identical**
to fern's archived `research/artifacts/fern-r99/depth1_shipped.metal`. The routed R1
literal has not drifted since round 99, so fern's r100 QMV ladder and mine are directly
comparable.

**Dose construction.** Anchor = the single occurrence of
`    gate_result += laguna_nvfp4_qdot_codes_16(` (asserted exactly once). Dose = `DOSE`
rounds of 8 *independent* `metal::fma(dz, 1.0000001f, 1e-6f)` seeded from live
`input_values[0..7]`, sunk through `if (dzs == 1e37f) { gate_result += 1.0f; }`. The
compare is unreachable, so the arm is **bit-identical by construction**, and the
compare-plus-uniform-branch cost is identical in every dosed arm, so it cancels exactly
in the 4→8→16 slope. The anchor sits inside the K-loop
(`input_width 2048 / block_width 512 = 4` trips), so extra fma/thread = dose × 8 × 4 =
**128 / 256 / 512**.

**Instrument-validity gate (passed), via `xcrun metal -std=metal3.2 -O2 -S -emit-llvm`:**

| arm | IR lines | `fmul`+`fadd` count |
|---|---|---|
| dose0 | 601 | 71 |
| dose4 | 640 | 79 |
| dose8 | 640 | 79 |
| dose16 | 640 | 79 |

dose4/8/16 are identical in size ⇒ the dose changes only the trip count of a rolled loop,
never the code shape. The dose loop body carries exactly **8**
`air.fma.f32(x, 0x3FF0000020000000, 0x3EB0C6F7A0000000)` calls and the sink appears as
`fcmp fast oeq float %240, 0x479E17B840000000` + `select`, so nothing is folded, hoisted,
strength-reduced or vectorised away. The K-loop is rolled (one copy of the dose loop).

**Rule 75 / occupancy gate (arm-void check).** From the probe's pipeline reflection:
dose0 = 256 source lines, dose4/8/16 = 280; `tgMemB = 0`, `maxTotalThreads = 1024`,
`execWidth = 32` for **all four arms**. Occupancy does not move, so no arm is void.

**Correctness gate.** The probe's bitwise output-equivalence check reports
`diff 0 / 65536 bytes` for every arm at TG = 1024 and TG = 2048, plus a reference re-run
control: `VERDICT: all arms bitwise identical to the reference.`

### 2.2 Rule 39 reachability / calibration proof

The probe dispatch at shipped geometry is **38.80 µs** (M4, residency-defeated).
39 MoE layers × 38.80 = **1513.2 µs/step**, against the charge's T2c M4 cost of
**1497.7 µs/step**: **+1.03 %**. The instrument is measuring the thing the charge is
charging for, to within 1 %.

### 2.3 Bytes ladder (rows / K-block sweep), residency defeated

`FERN_DEFEAT_SLOTS=64`, `FERN_ROUNDS=41`, `FERN_REPS=200`. Per-dispatch requested bytes
equal per-dispatch *unique* bytes in this kernel (the probe's model is
`8 experts × rows × 2 × fusedRowBytes + scales + activations + writes`); the 6.2×
"amplification" column is round-level re-read across only 64 slots, which is the intended
residency defeat, not intra-dispatch re-reading. Session s1:

| TG | rows | uniq MiB/round | req MiB/round | amplif | ref µs | achieved GB/s | % of 266.3 | SLC fit | regime |
|---|---|---|---|---|---|---|---|---|---|
| 128 | 32 | 17.14 | 107.35 | 6.3 | 4.89 | 115.1 | 43.2 | yes | PARTIAL |
| 256 | 64 | 34.27 | 213.70 | 6.2 | 7.18 | 155.9 | 58.6 | no | PARTIAL |
| 512 | 128 | 68.54 | 426.39 | 6.2 | 12.92 | 173.0 | 65.0 | no | PARTIAL |
| 1024 | 256 | 137.07 | 851.78 | 6.2 | 22.12 | 201.9 | 75.8 | no | PARTIAL |
| **2048 (shipped)** | **512** | **274.14** | **1702.56** | **6.2** | **38.75** | **230.4** | **86.5** | no | **SATURATED** |

Session s2 reproduces this to within 0.3 % at every rung (`115.1/109.8`, `155.9/155.4`,
`173.0/175.2`, `201.9/202.6`, `230.4/229.7`).

**µs/row slope vs the ideal DRAM slope.** Marginal bandwidth between the top two rungs is
**254.4 GB/s = 95.5 % of the 266.3 GB/s ideal**, with a fitted intercept of ≈4.6 µs
against rule 55's 3.97 µs. So the *marginal* byte is being moved at 95.5 % of the machine's
measured peak, and the amplification factor over the ideal slope is **1.05×**.

Contrast with the R107-D reference for the sliding-attention kernel: **2.11× the ideal
slope, 113.3 GB/s = 42.5 % of peak**. Same host, same ladder methodology, 2× apart. The
decode families are *not* a single regime, which is itself the census's main finding so
far.

### 2.4 Dose ladder — two independent residency-defeated sessions

Shipped geometry TG = 2048 × 64 threads = 131,072 threads. 41 alternating rounds × 200
dispatches, paired within round (rule 40/68/86).

| arm | extra fma/thread | s1 Δµs (sd) | s1 Δ% | s1 t | s2 Δµs (sd) | s2 Δ% | s2 t |
|---|---|---|---|---|---|---|---|
| dose4 | 128 | +0.424 (0.179) | +1.095 | +15.20 | +0.369 (0.177) | +0.952 | +13.38 |
| dose8 | 256 | +1.860 (0.237) | +4.799 | +50.27 | +1.848 (0.223) | +4.769 | +53.00 |
| dose16 | 512 | +5.865 (0.209) | +15.120 | +179.59 | +5.808 (0.216) | +14.973 | +172.58 |

Both sessions agree within 13 % on the smallest arm and within 1.5 % on the two larger
arms. dose0 (a verbatim copy of the shipped literal) is the A/B null and is not a slope
point; the null control was run first in every session, per fern's probe contract.

**Marginal µs per fma-per-thread, and exposure against the measured slot price 0.038044:**

| interval | marginal µs / fma-per-thread | exposure vs pure ALU |
|---|---|---|
| 0 → 4 (base operating point) | **0.003313** | **8.7 %** |
| 4 → 8 | 0.011219 | 29.5 % |
| 8 → 16 | **0.015645** | **41.1 %** |
| 4 → 16 (span) | 0.014169 | 37.2 % |

**Linearity: Δ(dose16)/Δ(dose4) = 5.865/0.424 = 13.83 against 4.0 expected — strongly
superlinear.** This is the "hidden, then progressively exposed" signature: monotonically
rising exposure, 8.7 % → 29.5 % → 41.1 %, never reaching 100 % even after tripling the
kernel's ALU load. A linear dose-response would have been the ISSUE-bound signature and
would have licensed an instruction-removal lever. It is not what the machine did.

**Base issue-slot budget per thread.** 4 K-blocks × 2 (gate and up) × one
`laguna_nvfp4_qdot_codes_16` each ≈ **128 useful fma/thread**, which the reachability
proof in §2.2 independently corroborates.

### 2.5 Residency inflates apparent instruction sensitivity by 5.6× (rule 98.9 evidence)

A resident session (`FERN_DEFEAT_SLOTS=1`; unique footprint 8.51 MiB fits inside the
~24 MiB SLC estimate; ref 36.47 µs, 244.8 GB/s = 91.9 %) —
**`[RESIDENT — NOT A HEADLINE]`**:

| arm | resident Δµs | resident Δ% | defeated Δµs | resident / defeated |
|---|---|---|---|---|
| dose4 | +2.061 | +5.682 | +0.424 | **4.86×** |
| dose8 | +3.571 | +9.756 | +1.860 | 1.92× |
| dose16 | +7.617 | +21.100 | +5.865 | 1.30× |

Marginal rates, resident: 4→8 = 0.011797, 8→16 = **0.015805**.

This is a clean, first-class methodological result:

* At **high** dose the marginal rate is **identical** defeated vs resident
  (0.015645 vs 0.015805, 1.0 % apart). That is the pure hardware issue cost, and residency
  cannot change it.
* At the **base operating point** the two differ by **5.6×** (+0.40 vs +2.06 µs on the
  dose-4 arm). With the working set resident, memory stall largely disappears, there is
  nothing left to hide the ALU under, and the kernel *looks* ISSUE-bound.
* **A resident measurement of this family would have returned the wrong regime verdict**,
  and with it the wrong `k`, and with it a licensed-but-fictional instruction-removal
  lever. Rule 98.9 is not hygiene here; it is the difference between a GO and a STOP.

### 2.6 H-REGIME decomposition (the publish block)

```
dispatch_us                     38.800   (M4, residency-defeated, mean of two sessions)
unique bytes / dispatch      8,925,845 B
achieved                       230.0 GB/s = 86.4 % of measured DRAM peak

byte_term_us  = bytes / 266.3 GB/s        33.518   ( 86.4 % of the dispatch)
issue_term_us NOMINAL = 128 x 0.038044     4.870   ( 12.6 %)   <- if fully exposed
issue_term_us EXPOSED = 128 x 0.003313     0.424   (  1.1 %)   <- what removal actually buys
residual_latency_us                        4.858   ( 12.5 %)
  of which rule-55 fixed intercept         3.970   ( 10.2 %)
  UNEXPLAINED                              0.888   (  2.3 %)

regime = BYTES   (MIXED was considered and rejected: the issue term is 1.1 % exposed)
```

**Self-check, as the assignment requires.** The terms sum to 97.7 % of the dispatch with a
**positive** 2.3 % residual. Nothing exceeds the dispatch and there is no large-negative
residual, so the decomposition is not obviously wrong. The one place it *could* be wrong
is the choice of exposed-vs-nominal issue term: using the nominal 4.870 µs would
over-account by 4.4 µs and drive the residual to −3.6 %, which is exactly the failure mode
the self-check is meant to catch. **The exposed term is the correct one for a decomposition
whose purpose is pricing removal.**

### 2.7 Exchange rates and the two bars

Per-dispatch M5/M4 ratio used: **none applied.** All of §2 is measured on M4, the
reachability proof in §2.2 lands within 1.03 % of the charge's M4 T2c cost, and rule 105's
conversion `Δ%cs = Δ_M4 × k × 0.015228` consumes M4 µs/step directly. Quoting the M5
column would require the 0.4370 ratio that B.0.3 *derives* from α — the circularity trap.

| quantity | value |
|---|---|
| 1 instruction/thread removed | 0.003313 µs/dispatch × 39 = **0.12921 µs/step M4** = **0.000860 % of cs** (k = α = 0.4369) |
| **BAR: instructions/thread for 0.4 %** | **465** — i.e. **3.64× the entire base ALU load of the kernel** |
| 1 MiB/step removed | **0.02649 % of cs** (from 1 % of B = 16,714,024 B = 0.4223 % of cs) |
| **BAR: bytes/step for 0.4 %** | **15.10 MiB/step = 4.55 % of this family's own 332.0 MiB/step** |
| family bytes/step | 332.0 MiB = **20.8 % of B** |
| 0.4 % bar in M4 µs/step | **60.1** = **4.0 % of this family's own M4 cost** (1497.7) |
| efficiency ceiling at fixed bytes | 206.0 µs/step M4 = **1.371 % of cs** (rule 105-E caps this class at 1.548 % — consistent) |

**The two bars say opposite things and that is the whole answer for family D.** You cannot
delete 465 instructions per thread from a kernel that only issues 128; the instruction
lever is not merely weak, it is **arithmetically unreachable**. You *can* plausibly look
for 4.55 % of the family's bytes. Every remaining pound of pressure on T2c belongs on the
byte axis.

### 2.8 Rule 55: **CONFIRMS CLOSURE** for family D

Rule 55 closed the ALU-density lever. Family D confirms that closure independently and
quantitatively: the exposed issue term is **1.1 % of the dispatch**, so removing *all*
arithmetic from the kernel — an impossibility — would buy 0.424 µs × 39 = 16.6 µs/step M4
= **0.110 % of cs**, i.e. **27 % of one 0.4 % bar**. No instruction-side change in this
family can clear the bar. Family D does not re-open rule 55.

### 2.9 B.0.3 cross-check: the T2c row survives, but now for a measured reason

B.0.3 lists T2c as M5 654.4 / M4 1497.7, from which its M5 column is *derived* as
`654.4/1497.7 = 0.4370 ≈ α`. That is circular as evidence. My measurement supplies the
missing non-circular half: family D is genuinely bytes-dominated (86.4 % of measured DRAM
peak, 95.5 % marginal bandwidth, 8.7 % ALU exposure at the operating point), therefore
**k = α is the right constant for this family for measured reasons**, and B.0.3's T2c row
is confirmed rather than merely self-consistent. **No B.0.3 label fails measurement in
family D.**
