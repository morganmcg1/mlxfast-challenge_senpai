# R125-D — Prefill: N-tile width (BN) for the routed/shared **down** gather GEMM

Student: `maple-tanjiro` · PR #732 · assignment `maple-r125-d-prefill-routed-down-bn`
(revision `r125-d-rev1`) · base `codex/mlxfast-maple-20260804-advisor`
@ `a9de9e8f21188715f6d80ada4b581bcd50d4ec81`.

---

## §0 Verdict, branches, SHAs, preference order

**Verdict.** Ship **one** single-lever change: the down-shape N-tile width of the
NAX routed/shared gather GEMM moves `BN = 64 → 128`. The change is legal
(non-empty MMA at `TN=8`), bit-identical by construction (BN partitions output
columns only; the K-loop order and per-fragment arithmetic are unchanged — proven
by identical AIR `mma_run`/`fmul` counts across BN), and fits the M4-measured
threadgroup-memory envelope (18 448 B of 32 768 B). It is **unmeasurable on this
host**: the code path is `nax`-only and this M4 Pro reports Apple GPU
generation 16, so `metal::is_nax_available()` is false and the edited function is
never called locally (§3). The candidate is therefore submitted as a *derived*
prediction with an explicit interval, not as a locally timed win.

| item | value |
| --- | --- |
| branch | `maple-tanjiro/r125-d-prefill-routed-down-bn` |
| base SHA | `a9de9e8f21188715f6d80ada4b581bcd50d4ec81` |
| assignment commit | `ff51ac2c705e830ae9bb2871939f6fe65be147b9` |
| code commit (arm A1, shipped) | `965f2f4b` |
| submitted path (1) | `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp` |
| research-only paths | `research/maple-tanjiro-r125d-*.{py,swift,md}`, `research/artifacts/tanjiro-r125d/**` |
| scope gate | `assignment scope OK: 1 submitted path(s)` |
| editable budget | `current=2699804/3000000 headroom=300196 growth=-284045/262144` |

**Predicted effect (single transfer constant, applied once).**

| arm | lever | ΔS (ms, prefill+decode window) | Δscore | note |
| --- | --- | --- | --- | --- |
| **A1 (shipped)** | `BN 64 → 128` | central **−1.44**, interval **[−3.91, +2.00]** | central **+0.53 %**, interval **[−0.74 %, +1.45 %]** | 1.09 σ of receipt noise |
| A2 (patch artifact only) | `BN 64 → 32` | central **+2.40** | central **−0.89 %** | falsifier, not a candidate |

**Preference order for official draws.**

1. **A1 (`BN=128`)** — this branch, as shipped. Central prediction (+0.53 %)
   exceeds the +0.378 % needed for the best receipt `e27f1ce` (2.606 649 70) to
   pass the crown `c5b0a13` (2.616 503 54); predicted receipt 2.620 46.
2. **A2 (`BN=32`)** — only worth one draw **if** A1's receipt is ambiguous
   (|Δ| < 1 σ = 0.489 %). A2 is a pure sign test of the bytes-in-flight model:
   if 32 ≥ 64 the model is falsified and the programme should stop spending
   draws on BN and redirect to the `SM=16` row-padding waste (see §6).

A2 is not committed as code — it exists as `bn32.patch` under
`research/artifacts/tanjiro-r125d/` so the advisor can raise it in one command
without another census.

---

## §1 Lever choice and census arithmetic

### The shape

`gather_qmm_rhs_nax` serves three Laguna MoE shapes. The **down** projection is
the only one whose BN is *free*:

* down: `K=512, N=2048`, plain BN-wide `Dtile` slices in the epilogue;
* fused gate/up: `K=2048, N=1024`, the SwiGLU epilogue pairs column `c` with
  `c + BN/2` and writes `N/2` columns — its `BN == 64` is a **correctness lock**
  (`kSwigluRegLocal`), not a tuning knob.

The override at `quantized.cpp:1392-1399` is restricted to the down shape
(`K == 512 && N == 2048`), so raising the down BN cannot touch the locked shape.

### Census (M4 AIR, three instantiations)

`research/maple-tanjiro-r125d-air-census.py` reads
`xcrun air-objdump --disassemble` output for the JIT source that
`darkbloom_expert_down_bn()` selects (`research/maple-alphonse-r107c-jit-air.sh`
emits the exact instantiations). Rows per layer = 512 prefill tokens × 8 routed
experts = **4 096** (`experts_per_token = 8`,
`LagunaRuntimeModel.swift:8306`). Artifact:
`research/artifacts/tanjiro-r125d/air-census.json`.

| quantity | BN=32 | BN=64 | BN=128 |
| --- | --- | --- | --- |
| `ir_lines` | 2 351 | 3 635 | 5 808 |
| `mma_run` (non-empty MMA) | 3 | 3 | **3** |
| `mma_getptr` | 12 | 12 | 12 |
| `fmul` | 12 | 12 | 12 |
| `TN_frags` | 2 | 4 | **8** |
| `SM` (row frags) | 16 | 16 | 16 |
| `alloca` (reg-pressure hint) | 45 | 74 | **120** |
| `store_slice_spec` | 14 | 28 | 56 |
| TG memory (AIR) | 4 616 B | 9 224 B | **18 440 B** |
| TG memory (Metal pipeline probe) | 4 624 B | 9 232 B | **18 448 B** |
| threadgroups / layer | 16 384 | 8 192 | **4 096** |
| grid dims | (64, 256, 1) | (32, 256, 1) | (16, 256, 1) |
| staged **w** bytes / layer | 150.99 MB | 150.99 MB | 150.99 MB |
| **x** re-read / layer | 268.44 MB | 134.22 MB | **67.11 MB** |
| **x** re-read, all 38 MoE layers | 10.20 GB | 5.10 GB | **2.55 GB** |
| staged bytes per SK step | 576 B | 1 152 B | 2 304 B |

### The arithmetic that picks 128

*Weight traffic is BN-invariant.* Each layer touches all 256 routed experts plus
the shared expert; each expert's down weight is
`2048 × 512` 4-bit values + group-16 scales ≈ 0.590 MB, and with ≈16 rows per
expert (`≤ bm = 64`) there is exactly one row-tile per expert, so every expert's
columns are read exactly once whatever BN is:
`256 × 0.590 MB = 150.99 MB` per layer, `× 38 = 5.74 GB` per forward. **BN cannot
reduce the weight bytes; it can only change how many are in flight at once.**

*Activation traffic is BN-linear.* Each row's `x` is re-read once per N-tile,
i.e. `N/BN` times: `4.194 MB × 2048/BN`. Going 64 → 128 removes
`67.11 MB × 38 = 2.55 GB` of re-reads per forward — but `x` per layer is only
4.194 MB unique, so most of that traffic is SLC-resident and should **not** be
scored as saved DRAM bytes. It is counted here only as an upper bound
(§2 "pessimistic-cache view").

*Occupancy is sub-linear in TG memory.* `research/maple-tanjiro-r125d-occupancy-census.swift`
(8 reps, dynamic-TG-memory probe, 128-thread groups, 20-core M4 Pro) measures
peak co-resident threadgroups:

| static TG bytes | resident TGs (mean ± sd) | per core | staged **w** bytes in flight / core |
| --- | --- | --- | --- |
| 4 624 | 173.2 ± 29.2 | 8.66 | 9 976 B |
| 9 232 | 160.6 ± 21.5 | 8.03 | 18 505 B |
| 18 448 | **115.4 ± 1.77** | 5.77 | **26 588 B** |

Doubling the footprint 9 232 → 18 448 B costs only **28 %** of co-residency, not
50 %, so bytes of weight in flight per core rise **+44 %**. That is the whole
thesis: on a shape whose cost is `w` streaming at 398 GB/s against a 546 GB/s
DRAM ceiling (§2), more bytes in flight is the only lever that converts to time,
and BN=128 is the largest rung that still fits.

BN=256 is not a rung: TG memory would be 36 880 B > the 32 768 B limit measured
by the pipeline probe (`research/artifacts/tanjiro-r125d/pipeline-probe.txt`).

---

## §2 Code change and tile derivation

Single hunk, `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp`
(`darkbloom_expert_down_bn`, lines 1234-1250): default `64 → 128`; the
env ladder becomes `(n == 32 || n == 64 || n == 128) ? n : 128`. No other
line in the tree changes.

**Single-lever proof.** `bn` feeds exactly three things, and only the first is
BN-shaped:

1. `grid_dims((N + bn - 1)/bn, egroups, 1)` (dispatch, ~line 1628-1650) —
   4 096 TGs/layer instead of 8 192.
2. `darkbloom_stage_wide_load_ok(..., bn)` → `col_step = bn * (K/2) = bn * 256`,
   a multiple of 16 for 32/64/128 alike, so `expert_wideld` is unchanged and the
   kernel name keeps `_ws_1_wl_1` for all three rungs. **No second lever moves.**
3. `align_N = (N % bn) == 0` — true for all three rungs.

`group_dims(32, wn, wm)` is BN-independent; the default geometry variant is 5
(`bm=64, wm=4, wn=1, bk=64`) and is untouched.

**Bit-exactness.** BN partitions output columns across threadgroups. The K loop
(`SK=32` staged steps), the accumulate order inside each fragment, and the
epilogue `Dtile.store` / `store_slice` are all BN-agnostic. The AIR census is
the mechanical check: `mma_run = 3` and `fmul = 12` are **identical** at BN
32/64/128, i.e. per-fragment arithmetic is the same program; only the number of
`store_slice` specialisations and the TG tile extent scale. There is no
cross-column reduction anywhere in the down epilogue, so no reassociation is
possible.

**Time budget it acts on.** PR170's ledger on control `3e165fa` (S = 97.895 ms)
attributes **W = 43.26 ± 0.40 ms** (~44 % of prefill) to the routed gather-GEMM
family. The down shape is one of three shapes and exactly one third of the
family's weight bytes (17.2 GB over 38 layers), so its share is
**≈ 14.42 ms**, an effective 5.74 GB / 14.42 ms = **398 GB/s**. At the
M5 DRAM ceiling of 546.2 GB/s the same bytes take **10.51 ms**, so the
addressable pool is **3.91 ms** — that is the hard cap on any BN win.

**Harvest model (Little's law on the +44 % bytes in flight).**

| efficiency η | ΔS |
| --- | --- |
| 0.25 | −1.44 ms |
| 0.50 | −2.61 ms |
| 0.75 | −3.57 ms |
| 1.00 | −3.91 ms (capped by the DRAM floor) |

The pessimistic-cache view is an independent sanity check and lands in the same
band: if every `x` re-read were a DRAM miss, total down traffic falls
10.84 → 8.29 GB (−23.5 %), i.e. −3.39 ms on a 14.42 ms budget. I report the
**conservative η = 0.25 point, −1.44 ms**, as central and do **not** add the `x`
term on top of it (same memory system — adding both double counts).

**Downside branch.** `TN_frags` 4 → 8 doubles the register-resident `Dtile`
(~64 floats/lane, plus `Btile`/`Atile`: ≈140+ registers/lane). This host offers
no spill detector — `maxTotalThreadsPerThreadgroup = 1024` for all three
pipelines, which R107-C §6.3 already showed is uninformative — and `alloca`
45 → 74 → 120 is only a hint. If the M5 spills, the extra bytes in flight never
materialise and only the TG-count and `x` terms survive (≈ −0.3 ms); if spilling
costs traffic, up to **+2.0 ms** is possible. Hence the reported interval
**ΔS ∈ [−3.91, +2.00] ms**.

---

## §3 Kernel-selection evidence (why this is not locally measurable)

```
quantized.cpp:1671   if (metal::is_nax_available() && transpose && ...)
                       return gather_qmm_rhs_nax(...);          // sole caller
quantized.cpp:1398       bn = darkbloom_expert_down_bn();       // inside that callee
device.cpp:913-929   can_use_nax &= gen >= (arch == 'p' ? 18 : 17);
```

`research/artifacts/tanjiro-r125d/pipeline-probe.txt` records this host as
**Apple M4 Pro**, which reports Apple GPU generation **16**. Therefore
`is_nax_available()` is false, `gather_qmm_rhs_nax` is never entered, and
`darkbloom_expert_down_bn()` is never called on this box. Consistent with the
programme's earlier finding that 94.2 % of M4 prefill GPU time sits in kernels
the M5 never runs.

What *is* verifiable locally, and was verified:

* all three instantiations compile clean via the JIT-AIR harness
  (`air_bytes` 26 096 / 35 968 / 52 064;
  `research/artifacts/tanjiro-r125d/down-bn{32,64,128}.compile.log`);
* the surface digest of the generated kernel source is stable
  (`c4608572a5…`), and the `mlx-generated/*.cpp` twin differs from the header
  only by inlined `fp4.h`/`fp8.h` bodies and `PRAGMA-VARIANT` comment lines
  (`research/artifacts/tanjiro-r125d/twin-diff.txt`, 175 lines) — the header was
  not edited, so **no twin edit is required**;
* real Metal pipelines build for all three rungs with static TG memory
  4 624 / 9 232 / 18 448 B against `maxThreadgroupMemoryLength = 32 768`.

---

## §4 Correctness certificate

| gate | command | result |
| --- | --- | --- |
| release build | `swift build -c release --force-resolved-versions` (then `git checkout -- Package.resolved`) | **exit 0**, 57.9 s (job `9728a7d2`) |
| assignment scope | `senpai/validate-assignment-scope.sh $BASE_SHA Vendor/.../quantized.cpp` | **OK**, 1 submitted path |
| editable budget | `senpai/check-editable-budget.sh 1bc1c895…` | **OK** `current=2699804/3000000 headroom=300196 growth=-284045/262144 files=143` |
| upstream equivalence | `EQUIVALENCE_EXACT_STEPS=8 research/run_upstream_equivalence.sh` | see below (job `9c25baf4`) |
| 64-step drift tripwire | fixture `correctness_golden.json` | **absent from this checkout** (same as R121-A) — not runnable here |

Equivalence detail (candidate tree, `quantized.cpp` recompiled in the debug
bundle — see `[5/11] Compiling quantized.cpp` in the job log):

```
promptTokenCount 512, decodeTokenCount 8
prefill    runtimeToken 5991 == upstreamToken 5991   maxAbsLogitError 0.125   meanAbs 0.011933609
decode-0..7 all runtimeToken == upstreamToken        maxAbsLogitError 0
EQUIVALENCE_EXACT_STEPS=8
EQUIVALENCE_EXIT=1
```

**9 / 9 greedy tokens match** (prefill argmax plus all eight decode steps), and
all eight decode steps are bit-exact. The non-zero exit is the single prefill
`maximumAbsoluteLogitError = 0.125`, which is the documented pre-existing
gen-16 property of this **unchanged base** on this host, not a candidate
regression: the changed code is unreachable here (§3), so the candidate cannot
have produced it. `MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT` was **never** set.

**Scope of the certificate.** Because the edited path is unreachable on gen-16
(§3), the equivalence run proves that the candidate tree still builds and still
matches the vendored oracle on the paths this host *does* execute; it cannot
exercise BN=128 itself. The exactness argument for BN=128 is the structural one
in §2 plus the AIR-level evidence that the arithmetic program is identical
across BN. The official M5 run is the only place the claim can be observed, and
it is gated by the hidden 512-token teacher-forced cases and token validation.

---

## §5 Decode neutrality

Decode is 75 % of the score, so neutrality must be argued at the code level, not
just timed:

1. Decode is `M = 1`. The override gate requires `M >= 64`
   (`quantized.cpp:1396`), so a decode step can never take the branch even on
   the M5. `bn` for decode stays whatever the generic NAX path chooses.
2. The gate additionally requires `bm == 64 && wm == 4 && (wn == 2 || wn == 1)`,
   i.e. the prefill geometry variant. Decode's single row never selects it.
3. `darkbloom_expert_down_bn()` has no other caller
   (`grep -n darkbloom_expert_down_bn` → definition at 1240, one use at 1398).
4. `bn` does not feed any host-side allocation, cache-shape, or metadata
   decision, so no decode-visible state changes.

A paired local `--local-iterate` A/B was **not** used as the neutrality
argument, and deliberately so: on this host the candidate and the baseline
execute *the same machine code* (§3), so such a run measures only host noise and
would be evidence-shaped noise rather than evidence. The local prefill_speedup
floor failure (≈0.33) on this box is structural and independent of this change.
Decode neutrality on the official host is asserted from (1)-(4) and is
falsifiable there: any decode_speedup below 1.00 − noise on the M5 receipt
contradicts the argument and should trigger the §7 revert.

---

## §6 Transfer reasoning (one constant, applied once)

The programme's single calibrated constant: **1.022 ms off S ⇒ +0.378 % score**,
i.e. **0.3699 % per ms** at the operating point **S = 97.863 ms**. That constant
already contains the score's decode/prefill weighting and the harness's
window composition, so a millisecond estimate is multiplied by it exactly once —
no second deflation for "prefill is only 25 % of the score", which is the double
count this campaign has made before.

* central **−1.44 ms × 0.3699 = +0.53 %**;
* interval **−3.91 ms → +1.45 %**, **+2.00 ms → −0.74 %**;
* receipt noise **σ(officialScore) = 0.489 %**, so the central prediction is
  **1.09 σ** — a favourable but genuinely uncertain single draw;
* the crown `c5b0a13` = 2.616 503 54 sits **+0.378 %** above the best receipt
  `e27f1ce` = 2.606 649 70; central A1 predicts **2.620 46**, i.e. it clears the
  crown by ≈0.15 % if the central case holds.

**If A1 comes back flat or negative**, the correct read is that BN is not the
binding constraint on this shape, and the census already names the bigger prize:
`SM = 16` row fragments against ≈16 rows per expert means the row dimension is
padded, ≈31.3 % of the MMA work on this shape is on padding, worth ≈11 ms —
seven times A1's whole addressable pool. That is a BM/WM experiment (R107-C §8),
not a BN one.

---

## §7 Abort criteria

Stated before the draw so the receipt cannot be reinterpreted afterwards:

1. **Hard error or correctness failure on the M5** (not a slow score) ⇒ the
   cause is almost certainly the TG-memory or register envelope: 18 448 B is
   56 % of the M4-measured 32 768 B limit, and gen 17+ may reserve additional
   threadgroup memory for tensorops. **Action: revert to BN=64 immediately**; do
   not attempt BN=192 (not a divisor rung) or BN=256 (over the M4 limit).
2. **Receipt Δ ≤ −1 σ (≤ −0.489 %)** ⇒ the register-pressure branch of §2 won.
   **Action: revert to BN=64**, and record that TN=8 spills on gen 17 so no
   future experiment re-tries a wider N tile on this shape.
3. **Receipt |Δ| < 1 σ** ⇒ ambiguous. **Action: at most one A2 (`BN=32`) draw**
   as a sign test. If A2 ≥ A1, the bytes-in-flight model is falsified; abandon
   BN entirely and move to the `SM=16` row-padding lever (§6).
4. **Receipt Δ ≥ +0.378 %** ⇒ promote and rebase the frontier; the next BN
   question is closed (128 is the top rung that fits) and the follow-up is
   whether the *gate/up* shape can be unlocked from its `BN == 64` correctness
   lock by rewriting the SwiGLU pairing — a much larger change, not a knob.
5. **Any interpretation from a non-M5 host** is out of bounds for this lever:
   gen-16 cannot execute it at all.

---

## §8 Deviations from the assignment

1. **No local timing arm.** The assignment anticipated a paired
   `--local-iterate` A/B for decode neutrality. I ran the structural
   neutrality argument instead (§5) because the edited function is provably
   unreachable on this gen-16 host; a paired run here would compare identical
   machine code. This is a deliberate, documented deviation, not a skipped gate.
2. **A2 (`BN=32`) shipped as a patch artifact, not a second commit.** The
   assignment allows 1-2 single-lever arms; A2 is only useful *conditionally*
   (§0 preference order, §7 criterion 3), so committing it as a second arm would
   spend review surface on an arm that is predicted negative.
3. **64-step drift tripwire not run**: the fixture is absent from this checkout,
   as previously recorded for R121-A. The gate remains available on the official
   stack.
4. **Occupancy numbers differ from R107-C's run** (115.4 here vs 127.8 there at
   18 448 B; 173.2 vs 160.2 at 4 624 B). The instrument is noisy at small
   footprints and uses a trivial kernel, so it does not model register pressure.
   Only the **monotone, sub-linear** ordering is claimed, and that reproduces.

### Reproduction

```bash
# 1. instantiate and census the three BN rungs (no GPU, no model)
OUT_DIR=research/artifacts/tanjiro-r125d \
  bash research/maple-alphonse-r107c-jit-air.sh 32 64 128
for b in 32 64 128; do
  xcrun air-objdump --disassemble \
    research/artifacts/tanjiro-r125d/down-bn$b.air \
    > research/artifacts/tanjiro-r125d/down-bn$b.ir
done
python3 research/maple-tanjiro-r125d-air-census.py 32 64 128

# 2. real Metal pipeline TG-memory probe
swiftc -O research/maple-alphonse-r107c-pipeline-probe.swift -o /tmp/pipeprobe && /tmp/pipeprobe

# 3. occupancy census (8 reps)
swiftc -O research/maple-tanjiro-r125d-occupancy-census.swift -o /tmp/occ && \
  /tmp/occ 4624 9232 18448

# 4. gates
swift build -c release --force-resolved-versions && git checkout -- Package.resolved
EQUIVALENCE_EXACT_STEPS=8 research/run_upstream_equivalence.sh

# 5. raise the A2 counter-arm if §7 criterion 3 fires
git apply research/artifacts/tanjiro-r125d/bn32.patch
```
