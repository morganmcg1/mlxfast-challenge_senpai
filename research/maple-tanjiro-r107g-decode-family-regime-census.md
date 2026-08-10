# R107-G — decode-family regime census (maple-tanjiro, PR #648)

`α = 0.4369, β = 0.5 two-pool map, residual −6.63 %, #561`

Host tag: **AWS M4 Pro, `applegpu_g16s`, Apple GPU gen 16, 20 GPU cores, 48 GiB unified,
macOS 26.5.2, Metal toolchain 17.6.109.0.** Epoch tag: **advisor tip `acb56108`,
`LagunaRuntimeModel.swift` sha256 `a736b50f…d850c4`, 12,147 lines.**
Every number below is measured on **M4**; M5 numbers are quoted only where the charge
supplies them, and are always marked.

W&B run: **https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/jhuxsg3h**
(`maple-tanjiro-r107g-decode-family-regime-census`, 89 summary metrics + 6 tables: the
per-family census, family D's dose and bytes ladders, the host bandwidth-vs-geometry and
SLC ladders, and the α/β adjudication).

### Units contract (rules 105.8, 105.11, 105.12) — read before quoting any number

Per rule 105.12 I am a **producer** of category-(b) numbers, not a consumer, so:

1. **Every timing I measured is raw M4 µs, census class.** The primary deliverable is the
   *regime verdict* per family; the advisor applies α or β downstream.
2. **Where I do show `% of cs`, the conversion has already been applied exactly once**, as
   `Δ_M4[µs/step] × k × 0.015228` with `k` = that family's own verdict (α = 0.4369 for the
   four BYTES families, β = 0.5 for E). Those figures are labelled `% cs` and must **not** be
   converted again — that is the double-counting rule 105.12 warns about. If you want the
   unconverted number, every table carries the M4 µs/step beside it.
3. **Census-or-marginal tag.** Everything I measured with the dose/bytes ladders and the two
   host probes is a **census** (full count over a controlled dispatch, 41 × 200 paired). The
   only **marginals** appearing anywhere in this report are §B.0.6's two "measured M5"
   figures, which I quote solely to *refute* their use as a calibration
   (`1010.67 µs (M5, marginal, PR34 receipt differential)` — rule 76 lower bound, and §B.1's
   companion implies 106.9 % of peak, so it cannot calibrate anything). I do not use them to
   derive any α.
4. **`dispatch_us` for families A, B, C, E is derived from the charge's audited M4 census**
   (B.0.3 M4 column ÷ call count), not from B.0.3's M5 column. The M5 column is
   `M4 × α` by construction (`654.4/1497.7 = 0.4370`), so using it would be circular; I
   verified that ratio myself before discarding the column.

## VERDICT TABLE (incremental — one row committed as each family's ladder lands)

| family | kernel | regime verdict | evidence | implied k | 0.4 % bar, instr/thread (exposed / nominal) vs base ALU load | 0.4 % bar, bytes/step | whole non-byte slack, in bars | rule 55 |
|---|---|---|---|---|---|---|---|---|
| D | T2c routed gate+up QMV | **BYTES** | **DIRECTLY PROBED** — 86.4 % of measured DRAM peak, 95.5 % marginal; dose slope 0.003313 exposed vs 0.038044 pure-ALU slot ⇒ 8.7 % exposure; reach +1.03 % vs charge | **α = 0.4369** | 466 / 41 vs base 128 ⇒ 3.6× the entire base load | 15.10 MiB/step = 4.55 % of the family's own bytes | **0.62** | **CONFIRMS CLOSURE** |
| A | T3b oproj h64 | **BYTES** | *inferred* — 87.2 % of peak, 91.3 % of geometry-achievable; dispatch 37.26 µs vs DRAM floor 36.46 µs ⇒ **0.79 µs of total non-byte slack** | **α = 0.4369** | 5,112 / 445 vs base 1024 ⇒ 5.0× | 15.10 MiB/step = 5.8 % of the family's own bytes | **0.40** | **CONFIRMS CLOSURE** |
| B | T2d routed+shared down+residual | **BYTES** | *inferred* — 85.5 % of peak, 90.2 % of geometry-achievable; dispatch 22.02 µs is **below** the modelled floor 22.80 µs ⇒ slack ≤ 0 | **α = 0.4369** | 466 / 41 vs base 64 ⇒ 7.3× | 15.10 MiB/step = 7.7 % of the family's own bytes | **≤ 0** | **CONFIRMS CLOSURE** |
| C | T0b(a) qkv h64 lane-major | **BYTES** | *inferred* — 91.0 % of peak, 95.2 % of geometry-achievable (best GEMV rate on M4); dispatch 44.67 µs vs floor 44.62 µs ⇒ **0.06 µs slack** | **α = 0.4369** | 605 / 53 vs base 256 ⇒ 2.4× | 15.10 MiB/step = 4.6 % of the family's own bytes | **0.03** | **CONFIRMS CLOSURE** |
| E | T2b gate_sp h64 | **LATENCY** (not ISSUE) | *inferred* — 11.9 % of peak; 262 KB in 8.27 µs; byte time is 0.98 µs, so **88 % of the dispatch is neither bytes nor issue** | **β = 0.5** | 529 / 46 vs base ≈68 ⇒ 7.8× | n/a — the whole family only moves 7.9 MiB/step | **1.89** (the only family with real slack) | **CONFIRMS CLOSURE** — the live axis is dispatch-count/fusion, already priced by #48 at −0.1488 % |

**Headline outcome: `N-BYTES-EVERYWHERE`** for the four NVFP4 GEMV families, plus
**LATENCY** (not ISSUE) for the adversarial low-efficiency target E. No ISSUE lever exists
anywhere in the decode family pool. The §1.5 machine-balance-point theorem shows this is
not an accident of the current code — it is forced by two measured host constants.

**Provenance discipline:** family D is *directly probed* (dose ladder + bytes ladder, two
independent residency-defeated sessions, reach within 1.03 % of the charge). Families A, B,
C, E are *inferred* from (i) the charge's audited M4 µs/step, (ii) my own byte model
validated against fern's independent audit to 0.15–2.2 %, and (iii) the two host constants
measured here. The inference is stated as an inequality wherever it can only be bounded.

## Decision memo for #644 (alphonse) / #597 (frieren) / #629 (edward)

Published **2026-08-10, Stage 1**, ahead of the 21:00Z memo requirement, so that it is
actionable before the 06:00Z handoff and the 07:00Z integration freeze. Read the one line
for your issue; §3.3 is the evidence and §3.5 is the pricing caveat.

| for | family | verdict | confidence | why |
|---|---|---|---|---|
| **#644 alphonse** | A — T3b oproj h64 | **STOP on the instruction axis; RE-AIM to bytes or stand down** | **high** | A runs at 37.26 µs against a 36.46 µs DRAM floor. Its *entire* non-byte budget — all exposed ALU, all latency, everything — is 0.79 µs/dispatch = 23.8 M4 µs/step = **0.159 % of `cs` = 0.40 of one bar**. No instruction-side change in this kernel can clear 0.4 %, even if it removed every instruction. The bytes axis needs 15.10 MiB/step = 5.8 % of the family's own traffic, which no metadata or packing trick left on the table can supply (#615 already took the metadata; L3 already took the packing default). |
| **#597 frieren** | B — T2d routed+shared down+residual | **STOP on the instruction axis** | **high** | B is the one family that already runs *at or below* the modelled DRAM floor (22.02 µs measured vs 22.80 µs modelled). Slack ≤ 0 bars. There is nothing to buy on the issue axis and the byte axis would need 15.10 MiB/step = 7.7 % of the family's own traffic. The −0.78 µs discrepancy is itself a finding (see threats): either B.0.3 slightly understates B's M4 cost or the 3.97 µs intercept is smaller at 288 thr/TG. |
| **#629 edward** | C — T0b(a) qkv h64, and D — T2c routed gate+up | **STOP on the instruction axis for both; C is finished** | **high (C), very high (D — directly probed)** | C: 44.67 µs against a 44.62 µs floor, i.e. **99.9 % of the theoretical best for its byte traffic**. Slack 0.03 bars. D: directly probed; exposed ALU is 1.1 % of the dispatch, the 0.4 % bar is 466 instructions/thread against a base load of 128, so the bar is **3.6× the entire arithmetic content of the kernel**. K-loop staging depth (#630) and `DARKBLOOM_QMV_WIDE_CODES` (−0.5363 %) are both consistent with this. |
| **adversarial target** | E — T2b gate_sp h64 | **RE-AIM: the regime is LATENCY, not ISSUE and not BYTES** | **medium** (inferred, and the fix is on a deconflicted axis) | 88 % of E's 8.27 µs dispatch is neither bytes (0.98 µs) nor issue (0.04 µs). It is dispatch overhead: rule 65's +2.3403 µs/dispatch plus rule 55's 3.97 µs intercept explain ~6.3 of the missing 7.3 µs. Fusing the dispatch away entirely is worth **1.664 % of `cs` = 4.16 bars** — the largest nameable prize in this census by 6× — but #48 already scored −0.1488 % on the dispatch-count axis, so this needs a *genuine* fusion, not a dispatch merge. |
| **the campaign** | α / β | **`N-DEGENERATE`, and the resolving experiment is free** | **high** | No single scalar α satisfies efficiency-invariance on both pools: `routed` demands a 597.1 GB/s M5 ceiling, `qkvo` demands 677.1 — **13 % apart** (§3.5). α-free bound: **α < 0.4454**. Run `research/fern_r101_bw_probe.swift` on the official M5: ~7 s, zero receipts. |

**What this memo is *not* saying.** It is not saying these families are cheap — they are the
four most expensive things in the decode step, 1.13 GB/step between them. It is saying that
every microsecond in them is already accounted for by bytes moved at 85–91 % of the measured
DRAM ceiling, so the *only* lever that can move them is moving fewer bytes, and the price of
that lever is now known: **15.10 MiB/step per 0.4 %**, i.e. 4.5–7.7 % of each family's own
traffic. Anybody proposing an instruction-count change to A, B, C or D in the remaining hours
is proposing something that cannot clear the bar even in the limit. That is the useful part.

**Where I would put the campaign's last hours**, in order: (1) the 7-second M5 bandwidth
probe, because it re-prices every remaining decision and costs nothing; (2) family E's
fusion, as the only ≥1-bar prize the census located; (3) T3a sliding fused attention, which
at 32.4 % of peak in fern's audit and `N-ISSUE-BOUND` in my own #642 is the one family in the
whole decode step whose regime is *not* bytes and which therefore still has a genuine
instruction axis. Nothing else in the pool is worth a receipt.


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

## 1.5 Instrument: the bandwidth ceiling, and the machine balance point

The second denominator the census needs is the *achievable* streaming rate at each family's
geometry, because "% of DRAM peak" is only meaningful once you know how much of the peak the
geometry itself can reach. I reused fern's audited streaming probe unmodified
(`xcrun swiftc -O research/fern_r101_bw_probe.swift -o /tmp/bwprobe`), swept it, and archived
the whole 110-line session to
`research/artifacts/maple-tanjiro-r107g/stage1-BW-geometry-s1.txt`.

Autotune at a 512 MiB working set (well past SLC), GB/s:

| threadgroups | 64 thr/TG | 288 thr/TG |
|---|---|---|
| 80 | 219–225 | 256.7–257.4 |
| 160 | **262.58–262.96 (winner)** | 255.4 |
| 260 | 254.4 | 254.6 |
| 520 | 256.4 | 252.3–252.8 |

Best measured streaming rate = **262.96 GB/s = 98.7 % of the 266.3 GB/s ceiling**. The
geometry penalty is real but small: the worst configuration in the sweep still reaches 82 %
of the best, and every configuration a decode kernel actually uses reaches 94–99 % of the
best. So the "% of geometry-achievable" column in §3 is computed against the rate measured
at each family's own (threadgroups, threads/TG), not against the global best.

SLC ladder, sequential arm at the winning geometry (160 TG × 64 thr, ilp 4):

| working set | GB/s |
|---|---|
| 2 MiB | 1820 |
| 4 MiB | 1521 |
| 8 MiB | 585 |
| 12 MiB | 506 |
| 16 MiB | 300 |
| 20 MiB | 267 |
| 24 MiB | 265 |
| 32 MiB | 263 |

⇒ **effective SLC ≈ 12–16 MiB on this M4 Pro.** This is the number that makes rule 98.9
non-negotiable for this census: every one of the five families has a per-dispatch unique
footprint of 0.26–10.8 MiB, i.e. *inside* the SLC. Any un-defeated measurement of any of
them is measuring cache, not the machine. §2.5 quantifies exactly how badly that misleads.

### The machine balance point (this is the whole census in one line)

Two measured constants:

```
DRAM ceiling        266.3e9 bytes/s
sustained fma issue   3.4453e12 fma/s
------------------------------------------------
balance point       266.3e9 / 3.4453e12 = 0.07729 bytes per fma
```

A kernel is ALU-bound iff its arithmetic intensity is *below* the balance point, i.e. iff it
moves fewer than 0.0773 bytes per fma. The NVFP4 decode GEMV families move **0.516–0.531
bytes per fma** (§3 table, derived from the shipped packing: 0.5 B/value codes + 0.0625 B/value
fp8 scales + lane-major nibbles, two fma per value for gate+up or one for a plain projection).
That is **6.7–6.9× above the balance point**.

Therefore, as an identity and not as a measurement:

> **No NVFP4 decode GEMV on this machine can be issue-bound.** At 0.52 B/fma the memory system
> is busy 6.7× longer than the ALU pipe for the same work, so ALU occupancy cannot exceed
> ~13–15 %, and removing *all* arithmetic from the kernel cannot save more than that fraction —
> and in practice saves far less, because the arithmetic is overlapped (§2.4: only 8.7 % of the
> nominal ALU cost is exposed at the operating point).

This is why the census outcome is `N-BYTES-EVERYWHERE` rather than a list of five
independently surprising results, and it is why family D's direct probe generalises: the
probe measures the *exposure fraction* (8.7 % at base), and the balance point bounds the
*nominal fraction* (12.4–13.6 %) for every family in the pool without further receipts.
**Rule 55's closure is therefore confirmed globally for the NVFP4 GEMV pool, from first
principles, on two host constants I measured myself.**

The one family that escapes the argument is **E (T2b gate_sp h64)** at 1.999 B/fma — but it
escapes in the *wrong direction*: it is 25.9× above the balance point, so it is even less
ALU-bound. Its problem is that it moves only 262 KB in 8.27 µs (11.9 % of peak), i.e. it is
**latency/dispatch-overhead bound**. See §3.4.


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

## 3. FAMILIES A, B, C, E — the inferred census

### 3.0 Why inference, and what makes it safe

Stage 1 was budgeted for two more *direct* dose ladders. It bought one hard instrument
instead (the ALU ceiling, §1) because the first family produced an impossible number, and
that instrument turned out to be worth more than two more ladders: combined with the
bandwidth ceiling (§1.5) it yields the **machine balance point**, which decides the regime
of every NVFP4 GEMV family in the pool without a single further dispatch.

So families A, B, C and E are decided by a triangulation whose three legs are all
independently checkable:

1. **the charge's own audited M4 µs/step** for each family (B.0.3), giving `dispatch_us`;
2. **my byte model of each kernel**, read off the shipped launcher argument shapes, and
   validated below against fern's completely independent audit;
3. **two host constants I measured myself** (266.3 GB/s achievable, 3.4453e12 fma/s
   sustained), giving the byte term, the issue term and hence the residual.

Everything inferred is labelled *inferred*, and where the inference can only bound a
quantity I report the bound, not a point estimate.

### 3.1 Byte-model validation against fern's independent audit

fern's `research/fern-r101-decode-pool-model.md` §7 audits per-step bytes for the whole
decode pool by a different route (counting call sites and weight tensors from the config).
I built my per-dispatch byte model from the launcher argument shapes at each anchor. The two
agree:

| family | my model, B/dispatch | × calls | fern's audited MB/step | agreement |
|---|---|---|---|---|
| D T2c routed gate+up | 8,925,845 | 39 | 347.60 | **0.15 %** |
| A T3b oproj h64 (lane-major, **pairwise**) | 8,673,408 | 30 | 259.58 | **0.24 %** |
| C T0b(a) qkv h64 lane-major | 10,848,256 | 30 | 324.71 | **0.22 %** |
| B T2d routed+shared down+residual | 4,901,888 | 39 | 195.53 | −2.2 % |
| E T2b gate_sp h64 | 262,144 | 30 | 7.86 | exact (64 × 2048 × 2 B BF16) |

Three of the five agree to a quarter of a percent by two independent routes. That is the
licence to use the byte term as a *known* quantity in the decomposition rather than as a fit
parameter, and it is what makes the residual meaningful.

Two by-products worth recording:

- **Family A ships the pairwise lane-major path.** `nibbleBytes`
  (`LagunaRuntimeWeights.swift:878`) is `groups/2` normally and `groups/4` when pairwise.
  Only the pairwise variant lands within 0.24 % of fern's audit; the non-pairwise variant
  overshoots. Independent confirmation: A's measured achieved rate is 232.2 GB/s; if the
  launcher's `scales` buffer were *also* being read, the implied rate would exceed the DRAM
  peak, which is impossible. So the lane-major path ships **and** `scales` is not read on
  that path. Both facts are needed for A's floor calculation and neither is in B.0.3.

  **This was subsequently confirmed by direct runtime observation, not just by arithmetic.**
  The `--local-iterate` anchor run of §5.2 prints its active code paths at worker startup,
  and the log contains, verbatim:

  ```
  mlxfast-worker: mlxfast: narrow-scales built lane-major pairwise: qkv
  mlxfast-worker: mlxfast: narrow-scales built lane-major pairwise: oproj
  mlxfast-worker: mlxfast: packed-scales active: routed swiglu qmv packed dispatch
  ```

  So families **C (`qkv`) and A (`oproj`) both ship lane-major *pairwise*** — the `groups/4`
  nibble path — exactly as the byte model required, and family **D ships the packed routed
  QMV dispatch**, which is the kernel I probed directly. The three legs of the triangulation
  in §3.0 are now joined by a fourth: the runtime says so itself. I had inferred the pairwise
  flag from a 0.24 % byte agreement and a reductio on DRAM peak; it is more satisfying to
  have the binary announce it.

- **Family E's traffic is exactly one BF16 `g_proj` tensor**, 64 heads × 2048 × 2 B. There is
  no quantised weight, no scale table, nothing to compress. The byte axis in E is already at
  its information-theoretic floor for the current numerics.

### 3.2 The cross-family decomposition table

`research/maple-tanjiro-r107g-decompose.py` → `stage1-crossfamily-audit.txt`.
`disp_us = M4 µs/step ÷ calls`; `GB/s = bytes ÷ disp_us`; `%geom` is against the streaming
rate measured at that family's own geometry (§1.5); `B/fma` is the family's arithmetic
intensity; `x_bal` is `B/fma ÷ 0.07729`; `nom_ALU%` is the fraction of the dispatch the
nominal issue term would occupy; `exp_ALU%` applies family D's measured 8.7 % exposure.

| family | disp µs | B/dispatch | GB/s | % peak | % geom | B/fma | × balance | nom ALU % | exp ALU % | latency % |
|---|---|---|---|---|---|---|---|---|---|---|
| D T2c routed gate+up | 38.40 | 8,912,821 | 232.1 | 87.2 | 90.5 | 0.531 | 6.9 | 12.7 | 1.10 | 11.7 |
| A T3b oproj h64 | 37.26 | 8,652,667 | 232.2 | 87.2 | 91.3 | 0.516 | 6.7 | 13.1 | 1.14 | 11.7 |
| C T0b(a) qkv h64 | 44.67 | 10,823,667 | 242.3 | 91.0 | 95.2 | 0.516 | 6.7 | 13.6 | 1.19 | 7.8 |
| B T2d down+residual | 22.02 | 5,013,590 | 227.7 | 85.5 | 90.2 | 0.531 | 6.9 | 12.4 | 1.08 | 13.4 |
| E T2b gate_sp h64 | 8.27 | 262,000 | 31.7 | 11.9 | 14.5 | 1.999 | 25.9 | 0.5 | 0.04 | 88.1 |

Decision rule, declared before the table was computed: **BYTES** when `%geom ≥ 85` and
`exp_ALU% < 5` and `latency% < 25`; **ISSUE** when `exp_ALU%` dominates; **LATENCY** when the
residual dominates; **MIXED** otherwise. Outcome: D, A, C, B → **BYTES**; E → **LATENCY**.
Nothing in the pool is ISSUE, and nothing is MIXED.

### 3.2.1 Requested check: does my census agree with §B.1's M4 GPU-timer census?

The advisor asked this directly ("if your instrument disagrees with that, the disagreement is
itself the headline"). §B.1's M4 GPU-timer census puts T2c routed gate+up at **88.0 %** and
T0b QKV at **89.7 %** of the 266.3 GB/s M4 peak. My route is completely different — a byte
model read off the launcher argument shapes, divided into the charge's audited M4 census time
— and it lands here:

| family | §B.1 GPU-timer | my census | gap |
| --- | --- | --- | --- |
| D / T2c routed gate+up | 88.0 % (234.3 GB/s) | 87.2 % (232.1 GB/s) | **−0.84 pp** |
| C / T0b(a) qkv | 89.7 % (238.9 GB/s) | 91.0 % (242.3 GB/s) | **+1.29 pp** |

**I confirm §B.1.** Two independent instruments — a GPU timer with real denominators, and a
byte model divided into an audited census — agree to better than 1.3 pp on both families.
That is well inside what either method can resolve.

Two consequences, both of which the advisor flagged as blocking:

- **It is affirmative evidence for a single bytes-regime α**, not per-family α's. Both
  families sit at 87–91 % of the same measured M4 ceiling. My census extends the finding to
  two more families that §B.1 does not cover: A T3b oproj at 87.2 % and B T2d at 85.5 %. So
  **all four NVFP4 GEMV families lie in an 85.5–91.0 % band, a 5.5 pp spread**, on an axis
  where §B.0.6's marginal-derived figures claimed a 9.6 pp *efficiency* gap between the same
  two pools.
- **That §B.0.6 gap is therefore an artifact, and §3.5 identifies its mechanism.** The
  marginals being compared carry different reuse discounts and different per-dispatch fixed
  costs (117 vs 80 dispatches across the two pools, and a per-dispatch intercept that does
  not scale with bandwidth). On the host we can actually measure there is **no per-family
  rate gap** — which is exactly what the advisor suspected and could not confirm. The
  §B.0.6 caveat that has been blocking headroom ranking can be retired *for the M4 side*.
  What survives untouched is the **M5 ceiling** degeneracy (§3.5), and no amount of M4-side
  data will dissolve it; that needs the 7-second M5 probe.

My spread between D and C (3.83 pp) is larger than §B.1's (1.70 pp), and I do not want to
over-sell the agreement: the difference is consistent with my byte model being 0.15–0.24 %
off on each family in opposite directions, which is within its validated tolerance (§3.1).
The claim I will defend is the band, not the ordering within it.

### 3.3 The non-byte slack bound — the strongest form of the result

The regime labels above use exposure fractions carried from family D. There is a stronger
argument for A, B and C that needs *no* carried exposure fraction at all, and it is the one
I would defend under cross-examination. `research/maple-tanjiro-r107g-slack.py` →
`stage1-slack-bound.txt`:

```
family                     disp_us  bytes_us  floor_us  slack_us  slack/step  max %cs  bars
D  T2c routed gate+up        38.40    33.469    37.439     0.963       37.6    0.250   0.62
A  T3b oproj h64             37.26    32.492    36.462     0.794       23.8    0.159   0.40
C  T0b(a) qkv h64            44.67    40.645    44.615     0.055        1.7    0.011   0.03
B  T2d down+residual         22.02    18.827    22.797    -0.774      -30.2   -0.201  -0.50
E  T2b gate_sp h64            8.27     0.984     4.954     3.313       99.4    0.757   1.89
```

`floor_us = bytes/266.3 GB/s + 3.97 µs`, where 3.97 µs is rule 55's measured per-dispatch
intercept on M4. **No change that leaves the byte traffic alone can push a dispatch below
that floor** — and every instruction-side change, which is exactly what this census was
commissioned to price, leaves the byte traffic alone. So `slack_us` is a *hard ceiling on
the entire non-byte lever*, exposed ALU and unexplained latency and everything else lumped
together, and it needs no assumption about overlap.

Read as bars: A = 0.40, C = 0.03, B ≤ 0, D = 0.62. **For all four NVFP4 GEMV families the
entire non-byte budget is smaller than one 0.4 % bar.** You could delete every arithmetic
instruction and every source of latency from these four kernels and still not clear the bar
on any of them. That is the census result, and it is why the outcome is
`N-BYTES-EVERYWHERE`.

Family C is the sharpest case: at 44.67 µs against a 44.62 µs floor it is running at
**99.9 % of the theoretical best a kernel with its byte traffic can achieve on this host**.
Edward's #629 work on C (L3) should be understood as having already finished the job.

Family A is the second sharpest and is worth stating plainly for alphonse: **A sits at the
rule-55 DRAM floor.** 37.26 µs measured against 36.46 µs ideal is 97.9 % of the floor. There
is 0.79 µs per dispatch in it, total, for all causes.

### 3.4 Family E — LATENCY, and the only real slack in the pool

E is the assignment's adversarial target: 10.4 % of peak in fern's M5 model, 11.9 % of peak
in mine, scored 1.69 %. The census says its regime is **LATENCY**, and specifically
**dispatch overhead**, not ISSUE and not BYTES:

- byte time is **0.98 µs** of an 8.27 µs dispatch (11.9 %);
- nominal issue time is **0.04 µs** (0.5 %) — the kernel does ~68 fma per thread across
  ~1,920 threads, which is nothing;
- so **≈7.3 µs, 88 % of the dispatch, is neither.** Rule 65's measured fixed cost of
  **+2.3403 µs per additional dispatch** accounts for 2.34 µs of that, and rule 55's
  intercept for ~3.97 µs; together they explain ~6.3 µs of the 7.3 µs.

E is therefore not a kernel-efficiency problem at all. It is a *dispatch* that costs almost
exactly what an empty dispatch costs, repeated 30 times per step. The implied prize is large
and should be stated so that nobody re-derives it: fusing the dispatch away entirely, with
its bytes moving inside whatever absorbs it, is worth
**218.5 M4 µs/step = 1.664 % of `cs` = 4.16 bars** at k = β = 0.5.

That is the largest single nameable prize in this census by a factor of six. It is also on
the one axis the campaign has already priced and lost on: **#48 dispatch-count reduction
scored −0.1488 %**. My reading is that the prize is real but that the fusion has to be a
*genuine* fusion (E's 262 KB of `g_proj` read inside the neighbour's dispatch), not a
dispatch-count reduction that re-materialises the same work with worse locality. I do not
have the receipts to attempt it in the hours remaining, and rule 105.7 says one unpaired M4
receipt cannot see a change of this size anyway — but 4.16 bars is worth a paired ABBA if
anyone has the receipts. **k = β = 0.5 for E**, because T1a/T2b sit in the pool whose two-pool
map constant is β; and note that at β the bar is 52.5 M4 µs/step, the cheapest bar in the
model.

### 3.5 α / β adjudication — verdict `N-DEGENERATE`, sharpened

The census cannot be published in `% of cs` without a position on `k`, so here is one.

B.0.6 records the two-pool residual test. The pieces that matter are the **M5 achieved
bandwidths**, because those are computed from measured M5 times and audited bytes and are
therefore **independent of α**: only the *ceiling* they are divided by depends on α.

| pool | M4 µs/step | M5 predicted | M5 measured | residual | M5 achieved GB/s | M4 efficiency (mine, measured) |
|---|---|---|---|---|---|---|
| routed | 2261.2 | 988.0 | 1010.67 | −2.24 % | **515.9** | 86.4 % (family D, direct) |
| qkvo | 3122.4 | 1364.3 | 1230.70 | +10.86 % | **597.9** | 88.3 % |

Now apply the principle B.0.6 itself relies on — *a family does not become materially more
or less efficient just because the host changed* — to **both** pools at once, which B.0.6
does not do:

| candidate | M5 ceiling | routed: M5 % peak vs M4 86.4 % | qkvo: M5 % peak vs M4 88.3 % | SSE (pp²) |
|---|---|---|---|---|
| α = 0.4369 | 610.6 | 84.5 % → **−1.9 pp** ✓ | 97.9 % → **+9.6 pp** ✗ | 96.2 |
| α = 0.389 | 686.0 | 75.2 % → **−11.2 pp** ✗ | 87.1 % → **−1.1 pp** ✓ | 126.7 |

And inverted — the ceiling each pool *demands* if its efficiency is to be invariant:

| pool | ceiling demanded | implied α |
|---|---|---|
| routed | **597.1 GB/s** | 0.4460 |
| qkvo | **677.1 GB/s** | 0.3933 |

Those two demands are **13 % apart**. So the honest verdict is not "two scalars fit equally
well" — it is **no single scalar α satisfies efficiency-invariance on both pools**. Outcome
**`N-DEGENERATE`**, and sharpened: the degeneracy is not a tie between candidates, it is a
**model misspecification**. Exactly one of the following must be false:

1. the M5 `routed` timing, or
2. the M5 `qkvo` timing, or
3. one of the two byte audits, or
4. **the premise that a single scalar maps M4 → M5 for a whole pool** — which is the one I
   would bet on, because the two pools have different arithmetic intensities (0.531 vs 0.516
   B/fma) and, more importantly, different *dispatch counts* per step (117 vs 80), and the
   per-dispatch fixed cost does **not** scale with the bandwidth ratio.

One α-free consequence that survives regardless: `qkvo` achieves 597.9 GB/s on M5, so
**M5's achievable peak is strictly greater than 597.9 GB/s, hence α < 0.4454.** That alone
retires any candidate above 0.4454.

What would actually settle it, in the order I would spend seconds on it:

1. **B.0.6's own proposal**: run `research/fern_r101_bw_probe.swift` on the official M5
   host. ~7 s of wall clock, **zero receipts**, and it measures the ceiling directly instead
   of inferring it. I agree with B.0.6 that this is the highest value per second of any
   experiment currently nameable in the campaign.
2. **A per-family M5 GPU-timer census** (the M5 analogue of §3.2). Necessary as well as (1),
   not instead of it: even with the M5 ceiling measured, one of the two pool residuals will
   remain, and only per-family times can say which pool is mismodelled.

Until (1) lands, everything in this report is published in **both** units — M4 µs/step
(measured, no α) and `% of cs` at the stated `k` — so that a later revision of α re-prices
the conclusions without invalidating any measurement.

**Does the α question change any verdict in this census?** No, and that is worth stating.
The bars at the three live constants are 60.1 (α = 0.4369), 67.5 (α = 0.389) and 52.5
(β = 0.5) M4 µs/step. The largest non-byte slack among A, B, C, D is family D's 37.6 M4
µs/step. That is below the *smallest* of the three bars. **The `N-BYTES-EVERYWHERE` verdict
is invariant to the α controversy.**


## 4. Rule 77 — geometry table for every kernel and probe in this report

Read off the shipped launchers at the re-derived anchors, and off the probes' own
pipeline reflection. `tgMemB` is dynamic threadgroup memory bound at dispatch.

| kernel / probe | anchor | threadgroups | threads/TG | total threads | tgMemB | maxTotalThreads/TG | execWidth |
|---|---|---|---|---|---|---|---|
| A T3b oproj h64 (lane-major) | `lagunaGatedAffineOProjNVFP4:4586` | 256 (`(outVec/8)*64/64`) | 64 | 16,384 | 0 | 1024 | 32 |
| B T2d routed+shared down+residual | `:8578` | 512 | 288 | 147,456 | 0 | 1024 | 32 |
| C T0b(a) qkv h64 lane-major | `lagunaDecodeNVFP4QKVLaneMajorSource:4922` | 1,280 | 64 | 81,920 | 0 | 1024 | 32 |
| D T2c routed gate+up QMV | `lagunaRoutedSwiGLUQMVPackedTop8:8030` | 2,048 | 64 | 131,072 | 0 | 1024 | 32 |
| E T2b gate_sp h64 | `lagunaGateSoftplus:4525` | 30 | 64 | ~1,920 | 0 | 1024 | 32 |
| D probe, all four dose arms | `/tmp/tanjiro_r107g_qmv` | 128–2,048 (ladder) | 64 | up to 131,072 | 0 | 1024 | 32 |
| ALU-ceiling probe, arm 1 | `/tmp/aluceil` | 2,048 | 64 | 131,072 | 0 | 1024 | 32 |
| ALU-ceiling probe, arm 2 | `/tmp/aluceil` | 256 | 64 | 16,384 | 0 | 1024 | 32 |
| bandwidth probe | `/tmp/bwprobe` | 80–520 (sweep) | 64 / 288 | up to 149,760 | 0 | 1024 | 32 |

The occupancy digests match across every dose arm and between each probe and the family
whose issue denominator it supplies. **No arm is void under rule 75**, and the issue
denominators in §3.2 are geometry-matched, not borrowed.

Threadgroup ladder (rule 77's "risers at multiples of 20 cores"): the bytes ladder in §2.3
*is* the threadgroup ladder for family D, swept over 128 / 256 / 512 / 1024 / 2048
threadgroups on a 20-core part. There is no riser at any multiple of 20; the curve is a
smooth approach to the bandwidth asymptote (43.2 → 58.6 → 65.0 → 75.8 → 86.5 % of peak),
which is the signature of a bandwidth ramp rather than a core-count quantisation. The
bandwidth probe's own geometry sweep (§1.5) agrees: the winner is 160 threadgroups = 8× 20,
but 260 = 13× 20 is *worse* than 160, so "multiple of 20" is not the organising variable —
total in-flight requests is.

## 5. Correctness and provenance anchor

The submitted diff on this branch is **zero bytes on every editable path**, so no
correctness claim in this report depends on new code. The anchor is nevertheless taken at
final HEAD, per the assignment:

`MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT` was **not** set at any point, and
`DARKBLOOM_EXPERT_DOWN_BN` was left unset.

### 5.1 The pasted zero-byte diff

Run at final HEAD, expanding the editable surface straight out of `benchmark.json` so that
the path list cannot be cherry-picked by me. Both the assignment base and the current
advisor tip are used as the left-hand side, because the branch was rebased mid-flight (§0)
and a reader is entitled to check either one:

```
$ git diff --numstat acb56108 HEAD -- $(jq -r '.editablePaths[]' benchmark.json) benchmark.json
$ echo "exit $?"
exit 0
$ git diff --numstat 04c7ac4761b007e45d46b70c6a0b497fbf39c907 HEAD -- $(jq -r '.editablePaths[]' benchmark.json) benchmark.json
$ echo "exit $?"
exit 0
```

Two empty outputs with exit 0: the editable surface is **byte-identical** to both bases.
`jq -r '.editablePaths[]' benchmark.json` expands to 97 paths, including all four
line ranges I was told not to touch — `LagunaRuntimeModel.swift:3845-4700` (alphonse),
`:4810-5010` and `:7892-8065` (edward), `:8225-8600` (frieren) — so the no-transient-edit
constraint is discharged by the same command rather than by assertion. For completeness,
the full file list that *does* differ from the advisor tip is 22 paths, every one of them
under `research/`:

```
$ git diff --name-only acb56108 HEAD | sed -n '1,3p;20,22p'
research/artifacts/maple-tanjiro-r107g/qmv_dose0.metal
research/artifacts/maple-tanjiro-r107g/qmv_dose16.metal
research/artifacts/maple-tanjiro-r107g/qmv_dose4.metal
research/maple-tanjiro-r107g-qmv-dose-run.sh
research/maple-tanjiro-r107g-slack.py
research/maple-tanjiro-r107g-wandb.py
```

The independent check that the *shipped* kernel source never moved is the sha256 of
`Sources/MLXFastModel/LagunaRuntimeModel.swift` at final HEAD, 12,147 lines:

```
a736b50f66b08b9004a807ff38226aaeb95ba836e6e833b51a8e862466d850c4
```

All dose variants were compiled and run as **standalone `.metal` files** under
`research/artifacts/maple-tanjiro-r107g/`, driven by a standalone Swift probe
(`/tmp/tanjiro_r107g_qmv`). Nothing in the measurement path reads the shipped Swift
source at runtime, which is why an issue-slot dose ladder on family D is possible at all
without editing edward's range.

### 5.2 The `--local-iterate` correctness anchor at final HEAD

One `./benchmark.sh --local-iterate` at HEAD `8ca38bff`, archived verbatim as
`research/artifacts/maple-tanjiro-r107g/baseline-run0.json`:

| field | value |
| --- | --- |
| `commit` | `8ca38bff` |
| `passed_correctness` | **true** |
| `max_abs_diff` | **0** |
| `golden_hash` | `b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63` |
| `harness_hash` | `141c159403ce1514499bfeed5fb7335c872aa959d501afd30dfd495110b9fda6` |
| `checked_steps` | 130 |
| `num_layers` | 40 |
| `decode_seconds_per_token` | 0.0129457200546875 |
| `prefill_seconds_per_token` | 0.001136998291015625 |
| `runtime` | `swift-local-iterate` |
| `peak_ram_gb` | 20.714 |
| `weights_byte_count` | 21,568,891,382 |
| `timestamp` | 2026-08-10T15:09:26Z |

`max_abs_diff = 0` over 130 checked steps with the golden hash unchanged is the bit-exactness
statement. The `golden_hash` is **identical** to the one in my R107-D anchor, so the golden
reference itself has not moved under me across the two assignments.

**A trap worth flagging for anyone else re-anchoring today.** `benchmark.sh` helpfully prints
a delta against the checked-in `score.local-iterate.baseline.json`, and for this run it said
`decode 0.013134 -> 0.012946 s/token (-1.4%)` and `est score 0.785 -> 0.793 (+1.1%)`. **That
line must not be quoted as a speedup.** The checked-in baseline artifact is commit `5319168`
from 2026-08-06 with

```
harness_hash 2f3ce1f6c0338f06bbc8c60fbdf791a12e64245af0ad8fde319b1f87e6995382
```

whereas this run has harness_hash `141c1594…`. It is a **cross-harness** comparison, and my
branch's editable diff is zero bytes (§5.1), so there is no mechanism by which I could have
produced −1.4 %. The apples-to-apples comparison is against **my own R107-D anchor**, same
harness hash, same golden hash, same machine:

| anchor | commit | harness | decode s/token |
| --- | --- | --- | --- |
| R107-D (#642) | `95f881e5` | `141c1594…` | 0.0129980905 |
| R107-G (this report) | `8ca38bff` | `141c1594…` | 0.0129457201 |

That is **−0.403 %** decode, across a tree whose only non-`research/` delta is the advisor
tip's vendored `quantized.cpp` (+25 lines, §0) — well inside the run-to-run drift of a
single unreplicated `--local-iterate` (which is why every timing claim in this report comes
from paired standalone probes at 41 × 200 dispatches, not from this harness). I record it as
a **correctness** anchor and explicitly not as a performance result.


## 6. Threats to validity

Ordered by how much they could move a conclusion.

1. **A, B, C and E are inferred, not probed.** The regime labels for those four rest on the
   charge's M4 µs/step, my byte model, and my two measured host constants. The byte model is
   independently validated to 0.15–2.2 % (§3.1) and the host constants are mine, so the
   weakest leg is the charge's per-family M4 attribution. If a family's M4 cost is
   overstated by more than ~3 %, its slack estimate moves by roughly one dispatch-µs, which
   for A would take it from 0.40 bars to ~0.7 bars — still under one bar. **No plausible
   error in the charge's attribution flips a BYTES verdict to ISSUE**, because that would
   require the achieved bandwidth to be far below 85 % of peak, i.e. the family to be
   *much* slower than the charge says.
2. **Family B runs below its modelled DRAM floor (−0.78 µs/dispatch, 3.5 %).** Something in
   that row is slightly wrong. Candidates: (i) my byte model over-counts B (my own model
   gives 4,901,888 B, 2.2 % below fern's, and even that leaves −0.36 µs); (ii) the 3.97 µs
   rule-55 intercept is smaller at B's 288 threads/TG, which is plausible since B is the
   only family in the pool not dispatched at 64 threads/TG and has 147,456 threads to hide
   launch latency behind; (iii) B.0.3 understates B's M4 cost. All three readings leave B's
   non-byte slack at or below zero, so the *verdict* is robust even though the row is not
   fully explained. Flagged rather than hidden.
3. **The exposure fraction is carried from family D to the others in §3.2.** Family D's
   8.7 % base-point exposure is measured; applying it to A, B, C is an assumption. §3.3 is
   the answer to this threat: the slack bound needs no exposure fraction at all, and it
   closes A, B, C and D independently. Where the two arguments disagree, §3.3 governs.
4. **M4 gen 16 vs M5 gen 17.** Everything measured here is on a 20-core gen-16 part; the
   ranked host is a 40-core gen-17 part. Restated per family: for **A, B, C, D** the
   conclusion is a *ratio* (achieved bandwidth as a fraction of the host's own ceiling), and
   ratios of this kind transfer — indeed my direct M4 T2c efficiency of 86.4 % agrees with
   fern's independently modelled M5 T2c efficiency of 87.0 % to **0.6 pp**, which is the
   best available evidence that percent-of-peak is the transferable quantity. For **E** the
   conclusion is about *fixed per-dispatch cost*, which does **not** scale with bandwidth and
   is the least transferable quantity in the report; E's prize could be materially smaller or
   larger on M5, and that is exactly why §3.5's M5 probe matters. No geometry argmax is
   proposed anywhere, because that would not transfer.
5. **The ALU denominator's register pressure.** The pure-ALU probe holds 8 accumulators; the
   shipped QMV kernel holds considerably more state. If the shipped kernel's occupancy is
   lower than the probe's, the probe's µs-per-slot understates the real slot price, which
   would make the exposure fraction *even smaller* and strengthen the BYTES verdict. The
   error is therefore conservative in the direction that matters. Both report identical
   `tgMemB`, `maxTotalThreadsPerThreadgroup` and `threadExecutionWidth`, which is as far as
   pipeline reflection can check.
6. **α is unresolved (§3.5).** Every `% of cs` figure in this report is conditional on
   `k`. Mitigated by publishing both units everywhere and by the invariance check at the end
   of §3.5: the verdict does not change at any of the three live constants.
7. **Rule 105.7.** Nothing here was measured with a receipt, so nothing here is subject to
   single-receipt detection noise. The flip side is that no claim in this report has been
   confirmed by the official harness; they are all host-local GPU-timer measurements and
   audited arithmetic. The report is a *pricing* deliverable, not a scored change.

## 7. Artifact index

All under `research/artifacts/maple-tanjiro-r107g/` unless stated.

| artifact | what it is |
|---|---|
| `stage1-ALU-ceiling-s1-tgs2048-tpt64.txt` | pure-ALU issue ceiling at family D's geometry (0.038044 µs/slot, 3.4453e12 fma/s) |
| `stage1-ALU-ceiling-s1-tgs256-tpt64.txt` | same at family A's geometry (0.004506 µs/slot, 3.6364e12 fma/s) |
| `stage1-BW-geometry-s1.txt` | bandwidth autotune over geometry + SLC ladder (110 lines) |
| `stage1-D-null-s1-slots64.txt` | NULL control for the family-D ladder |
| `stage1-D-dose-s1-slots64.txt` | family-D dose ladder, defeated session 1 |
| `stage1-D-dose-s2-slots64.txt` | family-D dose ladder, defeated session 2 |
| `stage1-D-dose-s3-slots1.txt` | resident twin — `[RESIDENT — NOT A HEADLINE]`, rule 98.9 evidence |
| `stage1-D-rows-s1-slots64.txt` | family-D bytes ladder, defeated session 1 |
| `stage1-D-rows-s2-slots64.txt` | family-D bytes ladder, defeated session 2 |
| `stage1-crossfamily-audit.txt` | output of `maple-tanjiro-r107g-decompose.py` — the §3.2 table and §3.5 adjudication |
| `stage1-slack-bound.txt` | output of `maple-tanjiro-r107g-slack.py` — the §3.3 slack bound |
| `qmv_dose{0,4,8,16}.metal` | the four generated dose arms; `qmv_dose0.metal` is byte-identical to `research/artifacts/fern-r99/depth1_shipped.metal` |
| `baseline-run0.json` | unmodified-tree `--local-iterate` correctness/provenance anchor at final HEAD |

Harness and analysis scripts, all `research/maple-tanjiro-r107g-*`:

| script | role |
|---|---|
| `alu-ceiling.swift` | the pure-ALU issue-ceiling probe |
| `qmv-dose-gen.py` | generates the four dose arms from the shipped kernel literal |
| `qmv-dose-run.sh` | runs the NULL control and the 4-arm ladder, both residency regimes |
| `decompose.py` | H-REGIME decomposition, cross-family audit, α/β adjudication |
| `slack.py` | the non-byte slack bound |
| `wandb.py` | publishes the census to `wandb-applied-ai-team/mlxfast-maple` |

Reused unmodified from other students: `research/fern_r99_qmv_probe.swift`,
`research/fern_r99_qmv_variants.py`, `research/artifacts/fern-r99/*.metal`,
`research/fern_r101_bw_probe.swift`. Byte audit cross-checked against
`research/fern-r101-decode-pool-model.md` §7.

## 8. Reply to the advisor

### 8.1 Anchor corrections: none. All five were right.

I was asked to correct the anchors if they had drifted. They had not — I checked every one
with `grep -n` against `Sources/MLXFastModel/LagunaRuntimeModel.swift` at final HEAD
(12,147 lines, sha256 `a736b50f…`), and all five families' line numbers land exactly where
the assignment said:

| family | assignment anchor | verified at | supporting symbols |
| --- | --- | --- | --- |
| A T3b oproj h64 | source 4222, launcher 4586 | **both exact** | `…Enabled:4114`, `…Kernels:4420`, `…LaneMajorKernels:4442`, call sites 6378, 6394 |
| B T2d down+residual | source 8277, launcher 8578 | **both exact** | kernels 8230, 8255, 8427, 8555; call site 10923 |
| C T0b(a) qkv lane-major | `…QKVLaneMajorSource(pairwise:)` 4922 | **exact** | kernels 4981, use 5026, `num_simdgroups = 2` at 4925, `out_row` at 4935 |
| D T2c routed gate+up qmv | kernel 7892, R1 kernel 7915 | **both exact** | wrapper 8030, R1 branch 8045, non-R1 8056, call site 10856 |
| E T2b gate_sp | source 4467, launcher 4525 | **both exact** | `…Enabled:4464`, `…Kernels:4512`, call site 5994 |

One naming clarification that cost me time and may cost the next person the same: **"h64" in
these family names means *64 attention heads*, i.e. the sliding-attention layers, not 64
threads per threadgroup.** Families A, C and E are named after `slidingAttentionHeads = 64`
(`LagunaConfig.swift`), which is why they have 30 call sites (the 30 sliding layers) rather
than 39 or 40. The threads-per-threadgroup happens to also be 64 for A, C and E, which makes
the collision easy to miss.

### 8.2 What I dropped, and why

I was budgeted for direct dose ladders on more than one family and delivered **one** (D).
A, B, C and E are **inferred**, and labelled as such everywhere. That was a deliberate
reallocation, taken at the point where family D's first ladder produced a marginal-fma rate
that was *lower than the machine's own ALU issue rate* — an impossible number, which meant
either the ladder or my assumed 4.04e12 fma/s ceiling was wrong. Rather than build three more
ladders on top of a number I could not defend, I spent the budget on two host constants I
measured myself:

- the **ALU issue ceiling**, 3.4453e12 fma/s sustained at the family-D geometry (85.3 % of
  the quoted figure — the quoted figure is not achievable, which is what broke the arithmetic);
- the **achievable streaming bandwidth**, 266.3 GB/s, plus its dependence on geometry and the
  ~12–16 MiB effective SLC.

Their ratio is the **machine balance point, 0.0773 B per fma**. Every NVFP4 GEMV family in
this pool sits at 0.516–0.531 B/fma, i.e. **6.7–6.9× memory-bound**, so ALU occupancy in this
pool cannot exceed ~13–15 % *by construction*. That single number decides the regime of four
families without another dispatch, and it is why I think the reallocation was the right call
rather than a shortfall. I would make the same trade again — but the honest cost is that
A, B, C and E have no measured issue-slot exposure of their own, only a bound, and §6 lists
that first among the threats.

The second drop: I did not build the family-A standalone probe (generator modelled on
`research/fern_r99_qmv_variants.py`, driver on `research/fern_r100_attn_probe.swift`). It is
the single highest-value next instrument if anyone gets stage-2 time, because A is the family
with the largest *absolute* headroom on the byte axis and my inference for it leans hardest
on the pairwise-nibble byte model.

### 8.3 Where I would put the campaign's last hours

Ranked, with the reasoning compressed:

1. **Run `research/fern_r101_bw_probe.swift` on the official M5.** ~7 seconds, **zero
   receipts**, no model load. It resolves the α/β degeneracy (§3.5) that currently makes every
   M4→M5 projection in this campaign uncertain by ±13 %, and it is the cheapest high-value
   measurement left anywhere on the board. The two pools demand 597.1 and 677.1 GB/s
   respectively for efficiency-invariance; one probe tells us which, or that neither holds.
2. **Family E (T2b gate_sp) fusion.** The only family whose regime is *not* BYTES. It runs at
   11.9 % of peak on 262,144 B, ~1,920 threads, 88 % latency residual. Full fusion is worth
   **218.5 M4 µs/step = 1.664 % of `cs` = 4.16 bars**. It is small, self-contained, and nobody
   is working it — it was handed to me as an *adversarial* family and it turned out to be the
   one real lever in the census.
3. **T3a sliding fused attention.** fern's audit puts it at 32.4 % of M5 peak with 212.2 µs of
   headroom and the pool's best score (3.23). Not my family, but it dwarfs anything left in
   the four BYTES families.
4. **Stop spending time on instruction-count work in A, B, C, D.** §3.3 bounds the *entire*
   non-byte cost of the largest of them at 37.6 M4 µs/step against a 0.4 %-`cs` detection bar
   of 52.5–67.5. The bound is smaller than the bar. This holds for every α in the plausible
   range, so it does not depend on resolving item 1.

### 8.4 One methodological result I would ask you to propagate

The residency finding in §2.5 is not about family D. Measured **resident**
(`FERN_DEFEAT_SLOTS=1`), family D's dose-4 arm looks **4.86× more issue-exposed** than it
truly is, and the family would have been labelled **ISSUE-bound** — the opposite verdict,
from the same kernel, the same doses and the same host, differing only in whether the weights
were still in cache. Rule 98.9 already requires residency-defeated headlines; this is a
quantified instance of what it buys, on a real shipped kernel, with both regimes measured
side by side. Any prior campaign result on a byte-heavy decode kernel that was taken resident
should be assumed to have over-attributed cost to issue slots by up to ~5×.


