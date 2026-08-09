# r100-A preregistration — probe regime validation, then the H2 TG-doubling ladder

Student: maple-fern. PR #553, assignment `maple-r100-a-tg-doubling-probe-ladder`,
revision `r100-a-rev1`. Base `d90f854d4687605880b0baf99e93b4a0b786100e`.

**Written and committed before any number produced by this arm was read.** Every
figure quoted below is either (a) inherited from the brief / merged research
state, or (b) a threshold or an explanation registered in advance.

Host: Apple M4 Pro, 20 GPU cores, `applegpu_g16s` gen 16, macOS 26.5.2,
48 GiB unified memory. Ranked host is a 40-core M5 Max.

## 0. Contract

- Submitted bytes changed: **0**. Everything lands under `research/`, which is
  not in `benchmark.json:editablePaths`. A non-zero
  `senpai/check-editable-budget.sh` delta is a defect, not a result.
- Receipts: **0 expected**. I will not dispatch an official submission from this
  arm without an explicit advisor go.
- No model-holding process is required by any rung, so no thermal-gated
  benchmark run is planned.

## 1. Instrument definitions (registered, so they cannot be tuned later)

For one *timing call* = one command buffer containing `reps` serial dispatches of
one kernel (this is the unit each paired sample measures):

```
requested_bytes = reps * (per-dispatch bytes the kernel's own index arithmetic
                          touches, counting every re-read)
unique_bytes    = |union over the call's dispatches of the device byte ranges
                   touched|
amplification   = requested_bytes / unique_bytes
achieved_GB_s   = requested_bytes / wall_seconds
unique_GB_s     = unique_bytes    / wall_seconds
roofline_side   = ISSUE_BOUND if unique_GB_s < 0.40 * dram_peak_GB_s
                  else BYTE_BOUND
```

`dram_peak_GB_s` is printed by the probe. Documented constant for this host:
**260.2 GB/s** measured on this M4 Pro by earlier programme work (STREAM-style
read probe); Apple's specified LPDDR5X peak for M4 Pro is 273 GB/s. Both are
printed so a reader can redo the division.

All per-dispatch byte counts are derived from (i) the probe's own buffer lengths
and dispatch parameters and (ii) `constexpr` values **parsed out of the kernel
source being timed**, never hand-typed in the probe. If a parse fails the probe
must abort rather than print a stale constant.

## 2. P1.2 — SLC-defeat mode, and its acceptance gate

Mode `defeat`: the K/V-cache (attention probe) or router-keys (QMV probe) buffer
binding offset rotates per dispatch so consecutive dispatches touch disjoint
regions. Target `unique_bytes >= 128 MB` per timing call; the achieved number is
printed.

**Registered gate — the null control.** In `defeat` mode, two byte-identical
kernel source strings, same rotation, same footprint, must satisfy

- `|d_mean| <= 0.5 %` of the reference per-call cost, **and**
- `|t(paired)| < 3.0` (15+ rounds), **or** `|d_mean| <= 0.5 %` with any t
  (a tight-but-significant bias is reported as a known additive offset and
  subtracted from every dose in that mode).

If `|d_mean| > 0.5 %` the mode is **broken**: nothing measured in it counts, I
report that immediately as the arm's primary result, and I do not use `defeat`
numbers to kill or clear Route A.

The historical resident-mode null control is ±0.5 % ≈ ±3.2 µs/step, so this gate
is the same bar the resident mode already meets — no loosening.

## 3. P1.3 — the #543 calibration, prediction registered in advance

Ground truth available: the #543 unroll measured **−14 %** on the resident probe
(`tmpl_s1/s2/s4` d_mean −2.86…−3.16 µs against a ≈21.4 µs reference) and
**−25.5 µs/tok (−0.196 %)** in situ, inside a same-arm control spread of
**137.2 µs/tok** (base) from one ABBA block.

### 3.1 The comparison the brief calls "70×" is not apples-to-apples, and I register that first

The probe's −14 % is a fraction of **one kernel's** time. The in-situ −0.196 % is
a fraction of the **whole decode step**. Converting the probe number into a step
delta needs the pool time `P` of that kernel:

```
predicted_step_delta = -0.14 * P
```

Taking rule 70's routed-expert pool figure (≈600 µs/step for the routed expert
work; the gate/up QMV kernel is a subset of it, so P <= ~600 µs) gives
`predicted_step_delta >= -84 µs/step`. The in-situ instrument's own same-arm
spread was **137.2 µs/tok**, i.e. **1.6× larger than the effect it was asked to
resolve**. A single ABBA block therefore **could not have rejected the probe's
prediction**, and the observed −25.5 µs is consistent both with −84 µs and with
0.

So I register now: **the 70× figure conflates a kernel-relative with a
step-relative percentage, and the in-situ leg was underpowered.** The honest
prior is that the probe *may* still be overstating (the direction of rule 71 is
right) but the size of the overstatement is **not measured**. I will not treat
−0.196 % as a point calibration target; I will treat
`[-84 µs, 0]` as the in-situ-compatible band and ask which probe mode lands
inside it.

### 3.2 Registered prediction for resident vs defeat

- Resident mode reproduces **−14 % ± 3 %** (it is the same binary and buffers).
- Defeat mode: I predict the effect **shrinks in magnitude by at least 2×** —
  best estimate **−4 %**, registered interval **[−8 %, −1 %]**.
- Reasoning: the unroll removes issue slots and loop overhead. When each
  dispatch must pull ~8.5 MiB from DRAM instead of hitting SLC, per-dispatch
  duration is set by bytes delivered, and instruction savings hide under memory
  latency. It should not go to exactly 0 % because 2048 TGs on 20 cores is
  ~102 TG/core, so some of the saving is in address generation and scale
  unpacking that still occupies issue slots even while waiting on memory.

### 3.3 Rule-72 explanations, written before the number is read

| outcome | what I will believe | how I would test it next |
|---|---|---|
| defeat collapses to `|d| <= 2 %` | Residency was the whole story. Every historical probe verdict on a byte-heavy kernel is a codegen measurement, not a performance prediction, and rule 71 should be strengthened to "resident-mode probe results on byte-heavy kernels are inadmissible as timing predictions". | Re-run one previously *accepted* probe verdict in defeat mode and check the sign/size against its receipt. |
| defeat lands in `[−8 %, −1 %]` (my prediction) | Residency inflated the effect by the predicted factor, and the true kernel-relative effect times the pool is `~0.04 * P <= 24 µs/step` — below both σ(cand_dec)=14.4 µs and the 68.7 µs record bar. The #543 close stands, and the probe is usable **only** in defeat mode with an explicit pool multiplication. | Nothing further for #543. Adopt defeat mode as the default for all byte-heavy kernels. |
| defeat stays at ≈−14 % | Residency was **not** the story and my §7.10 explanation was right for the wrong reason. Then the candidates for the gap are, in the order I would believe them: (1) the in-situ leg was simply underpowered (see §3.1 — this is now my leading alternative, and it predicts the probe was *right*); (2) the in-situ swap did not actually reach the JIT kernel text that the probe compiled; (3) 39-layer serialization plus MLX per-dispatch host cost dilutes any kernel-internal win. | Test (1) directly: N ABBA blocks until the standard error is below 30 µs/tok, which from a 137.2 µs range (σ≈60 µs) needs ~2×(60/30)² ≈ 8 blocks. Test (2) by dumping the JIT'd MSL from the in-situ worker and diffing against `stage4_cand.metal`. |
| defeat null control fails | Instrument broken. Report immediately; no verdict on anything else. | Bisect the rotation: rotate only reads, then only writes. |

## 4. P2 — registered bars for the ladder

Prices used (from the brief): decode **0.015280 % score per µs/step**;
σ(score) 0.452 %; σ(cand_dec) 14.4 µs/step; median-ties-record **+68.7 µs/step**;
attention pool ≈**390 µs/step** over 40 layers (30 sliding at 32 TGs, 10 full at
24 TGs).

Route A net model: `Δ ≈ 290 µs × [1 − φ(1−α)]`, with `φ = t(64)/t(32)` (identical
source, grid-only) and `α = 1 − t(routeA@32)/t(base@32)`.

| rung | readout | registered decision bar |
|---|---|---|
| E1 | `φ = t(64)/t(32)`, identical kernel text in both arms, K ∈ {16,24,32,40,48,64,80,96} | `φ >= 1.5` ⇒ **both routes dead, stop.** `φ <= 1.05` ⇒ proceed. Otherwise report the curve and let E3 decide. Also report the K=32 base-vs-base paired artifact; every later delta is quoted against it. |
| E2 | uniqueness fold at K=64 (`kv_head = (head0/gqa) % 8`), identity null at K=32 | The K=32 arm **must** time as `|d_mean| <= 0.5 %`; if it does not, E2 is void. |
| E3 | `α` at K=32 | `t(routeA@32) >= t(base@32)` ⇒ **route dead, stop.** `α < 0.10` ⇒ E4 not run. |
| E4 | `t(routeA@64)` vs `t(base@32)` | Promotion interest requires predicted step delta `<= −68.7 µs`, i.e. `φ(1−α) <= 0.763`. Anything between −68.7 µs and −14.4 µs is reported as "real but below the record bar"; `> −14.4 µs` is dead. |

Registered prior (not a bar): rule 60's M4 wave model
`t(K) = 1.413 + 7.849·ceil(K/20) µs` gives `φ_M4 ≈ 1.8–1.9`, so **I expect E1 to
kill this arm on M4**, and the only interesting question is whether the measured
φ curve is *smooth* (a memory-system/scheduler effect that a 40-core M5 would
absorb differently) or *stepped at multiples of 20* (a hard wave quantum that
would predict the same kill at 40 cores with the step moved to 40).

That distinction is the arm's real content and I register it now: **a stepped φ
whose riser sits at K = 20/40/60 predicts `φ_M5(64/32) ≈ 1.0` because 64 and 32
both fit inside two waves of 40 cores — i.e. the M4 kill would NOT transfer.** A
smooth φ predicts the kill does transfer. I will state which shape I observed
and therefore what I predict for the M5, and I will not convert either into a
receipt request without advisor go.

Every rung reports the §1 regime block and, where the rung's verdict could
plausibly depend on residency (E1's φ above all — waves and bytes are
confounded when 64 TGs request 2× the bytes of 32), the same rung in defeat
mode. A verdict that flips between modes is reported as an open question, not a
verdict.

## 5. Occupancy identity, reported for every timed variant

`staticThreadgroupMemoryLength`, `maxTotalThreadsPerThreadgroup`,
`threadExecutionWidth`, threadgroup count, threads/threadgroup. Per #543's own
finding, identical AIR opcode counts do **not** imply identical timing, so no
mechanism is attributed from AIR alone.

## 6. Stop rules

Stop and report at the first of: E1 `φ >= 1.5`; E3 `t(routeA@32) >= t(base@32)`;
E4 complete and priced; or the defeat-mode null control failing its §2 gate.

## 7. Things I am explicitly not doing

- Route B (split-D): excluded by the brief.
- Any edit to a file inside `editablePaths`.
- Any claim that an M4 φ measurement ranks Route A on the M5 beyond the
  shape-based prediction registered in §4.
