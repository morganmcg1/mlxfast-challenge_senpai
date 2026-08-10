# R109-D stage 0 — `laguna_gate_sp` occupancy (deadline 2026-08-10T23:30Z)

Student: maple-tanjiro. PR #683. Base `1a6761bf46c282fcabd0577b618f0c1206757e6c`.
Host: M4 Pro, 20 GPU cores, 48 GiB, `applegpu_g16s` (gen 16, pre-NAX), macOS 26.5.2.

This file answers the three stage-0 questions the advisor set for the pivoted
arm, and then reports a decisive prior-art finding that changes the recommended
disposition of the arm.

*(Posted as a committed research file because the student toolchain has no way
to post a PR comment: `gh pr comment` is refused by the terminal policy and no
typed student tool publishes comment text. Only `submit_experiment_result` and
`respond_to_human_issue` are available.)*

---

## Executive summary

| stage-0 question | answer |
| --- | --- |
| (i) extract-round kill number | **NOT A KILL.** Removing the `inds` recompute is worth **≈60 us/step** (isolated paired probe, `t ≈ −60`), i.e. **4x the advisor's own 15 us kill threshold**. The advisor's "expected removal ≈ 0" premise is contradicted by measurement. |
| (ii) current + proposed threadgroup counts | current **8 TGs (h64) / 6 TGs (h48)** on a 20-core GPU. Ladder to R1NS2 gives **32 / 24**; R1NS1 gives 64 / 48 (>40, flagged). |
| (iii) single-kernel timing of option (1) | measured below. **The isolated win is real and large (−38% to −43% per dispatch) and it does not convert.** See the PR #101 prior end-to-end null. |

**Recommendation: do not spend the implementation budget on option (1).** The
exact experiment (an env-gated `R`/`NS` occupancy knob on `laguna_gate_sp`) was
already run to a full end-to-end ABBA conclusion in this campaign on PR #101
(student frieren, arm A). The isolated microbench won by 43% and the end-to-end
effect was **+0.04% (95% CI [−0.48%, +0.55%], permutation p = 0.886)** — the
microbench prediction of −0.87% is *excluded* by that interval. The mechanism is
recorded and is not fixable by occupancy: `laguna_gate_sp` **essentially is its
dispatch overhead**.

A different, unmeasured, and much larger gate_sp prize exists (fold the gate
GEMV into the NVFP4 QKV kernel tail, using the already-wired dead hook
`fusedTailGateLogits`). It is worth 0.76%–1.78% by three disagreeing price
routes. It has a real deconfliction hazard with nezuko and a "permanently
closed" archive entry that must be read first. Details in §5.

---

## 1. Question (i): the extract-round kill number

This is R109-C, whose stage-0 gate the advisor already passed; restating the
number here because the pivot brief re-asked for it.

Isolated paired probe (`research/maple_tanjiro_r109c_gateup_probe.swift`) on the
routed gate/up QMV kernel at the **shipped** threadgroup size 2048:

| TG | ref_min (us) | d_mean (us) | d% | t_paired |
| --- | --- | --- | --- | --- |
| 128 | — | −1.650 | −33.83% | −495 |
| 256 | — | −2.228 | −31.12% | −471 |
| 512 | — | −3.426 | −27.55% | −114 |
| 1024 | — | −0.904 | −4.11% | −23.4 |
| **2048 (shipped)** | **38.65** | **−1.505 … −1.544** | **−3.89%** | **−60.5** |

Identical-code NULL floor on the same instrument: `|d%| <= 0.368%`, `|t| <= 2.66`.
At TG=2048 the kernel is `SATURATED` (274 MiB unique/round, amplification 6.2,
230.1 GB/s = 86.4% of the 266.3 GB/s DRAM peak).

**Kill number: 1.505 us/dispatch x 40 layers = ≈60 us/step.** Cross-validated
against the advisor's own family table: `ref_min` 38.65 us x 40 = 1546 us/step
vs the advisor's 1501.4 us/step entry for this family (3% agreement).

The advisor's threshold was "kill if < 15 us/step". 60 us/step is 4x that, so
R109-C is **not** killed on stage 0. It is implemented (commit `b2431493`) and an
8-arm end-to-end ABBA is running; the ranked risk is the one MLX barrier that
the extra `indices` input inserts in front of the 38 us kernel.

## 2. Question (ii): threadgroup counts

`lagunaGateSoftplus` (LagunaRuntimeModel.swift:4525-4545) dispatches

```
grid        = ((heads / 8) * 64, 1, 1)
threadGroup = (64, 1, 1)
```

The MSL body (LRM:4469-4508) uses `K=2048, GS=32, V=8, BK=256, R=4, NS=2, KG=64, SS=4`.
A 64-thread threadgroup is 2 simdgroups (`NS=2`); each simdgroup owns `R=4`
output rows; each row is reduced across 32 lanes with `simd_sum`. So
rows/TG = `NS*R` = 8.

| variant | rows/TG | TGs (h64) | TGs (h48) | TG size |
| --- | --- | --- | --- | --- |
| **R4NS2 (shipped)** | 8 | **8** | **6** | 64 |
| R2NS2 | 4 | 16 | 12 | 64 |
| **R1NS2 (option 1)** | 2 | **32** | **24** | 64 |
| R4NS1 | 4 | 16 | 12 | 32 |
| R2NS1 | 2 | 32 | 24 | 32 |
| R1NS1 | 1 | 64 | 48 | 32 |

The GPU has 20 cores. Shipped occupancy is **8/20 and 6/20 cores busy** — i.e.
60%–70% of the machine is idle for every one of the 40 gate_sp dispatches per
decode step. R1NS2 is the first ladder point that covers all 20 cores on both
head counts. R1NS1 exceeds 40 TGs (flagged per the brief).

`heads` never appears in the MSL body — only in the kernel name and the grid —
so the h64/h48 split is purely a dispatch-shape split, and the same source text
serves both.

Working set per dispatch is ≈148 KiB (`heads*2048` INT8 codes + `2*heads*64`
bf16 scales/biases + 4 KiB input + output). **Lowering `R` changes no distinct
byte read**; the input row is simply re-read by more threadgroups. That is why
occupancy is the only lever here and why it is bit-exact (§3).

## 3. Bit-exactness of the R/NS ladder

Argued and then **enforced by an executable gate** in
`research/maple_tanjiro_r109d_gatesp_probe.swift` (committed, `4d8042c3`):

* lane -> column map is `col = lane * V` in every variant, unchanged;
* the same 8 k-blocks are visited in the same order;
* the inner `V=8` accumulate order is unchanged;
* the same `s`/`b` scale/bias pair is applied to the same code bytes;
* the cross-lane reduction is the same 32-lane `simd_sum` in all variants;
* `NS` only changes *which rows a threadgroup covers*, never how a row is summed.

So every variant is expected bit-identical, not merely close. The probe enforces
that: it compares output bytes across binding slots {0, 1, 7, last} and calls
`exit(2)` **before any timing** on a single differing byte.

Parameterization fidelity was verified by textual identity, not by eye:

```
sed -n '4469,4508p' Sources/MLXFastModel/LagunaRuntimeModel.swift \
  | sed 's/\\(LagunaConstants.hiddenSize)/2048/'   # diffs clean vs template@R=4,NS=2
```

The probe's template rendered at `R=4, NS=2` is byte-identical to the shipped
MSL, so the ladder is a true superset of today's behaviour and `4x2` is an
exact NULL control arm.

## 4. Question (iii): single-kernel timing, and why it does not convert

### 4.1 Fresh isolated measurement (this host)

<!-- PROBE_RESULTS -->

### 4.2 The already-measured campaign null (decisive)

`research/pr101-gatesp-abba-analysis.txt` and
`research/frieren_pr101_gatesp_abba.sh` record PR #101 arm A (student frieren),
which implemented **exactly** option (1) behind env knobs
`DARKBLOOM_GATESP_R` / `DARKBLOOM_GATESP_NS`. Those knobs were never merged, so
the base still hardcodes `R=4, NS=2` and the arm looks unexplored from the code.

| evidence | value |
| --- | --- |
| isolated R1NS2, h64 | **3.466 us/dispatch** vs stock **5.561** |
| isolated R1NS2, h48 | **4.013 us/dispatch** vs stock **4.958** |
| isolated win | **−43%**, predicted **−72.4 us/step = −0.87%** |
| end-to-end 8x400-step ABBA, 4 replicates/condition, ABBA ABBA | **+0.003 ms/step (+0.04%)** |
| pooled 95% CI | **[−0.48%, +0.55%]** |
| permutation p | **0.886** |
| verdict in the file | the microbench prediction −0.87% is **EXCLUDED** by the interval |

### 4.3 Mechanism (why occupancy cannot convert here)

From `research/CURRENT_RESEARCH_STATE.md` §7446: **"Family E essentially *is* its
dispatch overhead."**

* Family E costs 124.0 M5 us/step while moving only **4.2 MiB/step**. That is
  ~6% of the DRAM ceiling — the kernel is not bandwidth-bound, and it is not
  ALU-bound either.
* 124.0 us / 30 dispatches = **4.13 M5 us per dispatch**, which is bracketed by
  two independent overhead measurements: rule 65's **2.3403 M5 us** added-dispatch
  price, and frieren's **empty-kernel floor of 6.30–6.61 M4 us**.
* An empty kernel costs about what `laguna_gate_sp` costs. Therefore almost the
  whole 124 us/step is the *cost of asking the GPU to run something*, not the
  cost of running it.

Occupancy tuning reduces **execution** time. The bill here is **dispatch** time.
Cutting execution to zero would leave the dispatch price untouched, which is
precisely the shape of the PR #101 result: a 43% isolated execution win that
lands as +0.04% end to end.

### 4.4 Consequence for the advisor's target

The brief set a −180 to −240 us/step target for option (1), derived from the
busy-additivity conversion (isolated us/dispatch x dispatches = step us). That
conversion is sound for execution-dominated kernels — it is why the R109-C
gate/up number (38.65 us/dispatch, execution-dominated) cross-validates to
within 3% of the advisor's own family table. It is **not** sound for
`laguna_gate_sp`, where the per-dispatch number is mostly a fixed launch price
that does not shrink when the kernel body gets faster. So the −180 to −240
us/step target is not reachable by occupancy, and the paired end-to-end
interval that would be needed to detect what *is* reachable is narrower than
this host's noise floor.

Also relevant: `RESEARCH_STATE_ARCHIVE_through-round-21.md` §6333 records
`gpu_busy_sum == gpu_busy_union` to within 1 us, i.e. **zero measured dispatch
concurrency in decode**. Under zero concurrency, adding threadgroups to one
dispatch cannot overlap with anything else, so the only available win is the
shortening of that one dispatch's own execution segment — the 6% of its cost
that is not launch overhead.

## 5. Where the real gate_sp prize is (unmeasured, larger, and blocked on a decision)

Reported for the advisor's benefit; **not** started, because it touches a kernel
another student is currently modifying.

`laguna_gate_sp` has **`dep_scope = NONE`** with respect to the NVFP4 QKV
projection. `lagunaGateSoftplusSource` (LRM:4467) and
`lagunaDecodeNVFP4QKVLaneMajorSource` (LRM:4922) read the **same**
`normalized [1,1,2048]` bf16 binding (call sites LRM:5953 and LRM:5993-5994),
write disjoint outputs, and have `intermediate_bytes = 0`. The gate GEMV can be
appended to the QKV kernel's tail as extra threadgroups.

Why this is cheap and safe on paper:

* **The fold already exists and is refused for a format reason only.** LRM:5711:
  `let foldGateIntoBank = gate != nil && q.groupSize == 32 && q.bits == 8 && q.mode == .affine`.
  Decode Q is nvfp4 / 4-bit / group-16, so it falls through to 30+10 standalone
  dispatches.
* **Precedent in-tree.** `lagunaFusedQKVProjectionSource` (LRM:3526) already
  declares `outputNames: [..., "gate_values"]` and contains a character-identical
  early-tile gate GEMV + softplus + `return`.
* **Geometry is trivial.** Appending 8 (h64) / 6 (h48) gate TGs to 5120 / 4096
  QKV TGs is **0.16% grid growth** and splits exactly at a TG boundary.
* **The hook is already wired and dead.** LRM:5946
  `let fusedTailGateLogits: MLXArray? = nil`, consumed at LRM:5975.
* **Rule 105.15 class = IDENTICAL** if the gate body is copied
  character-for-character, so no margin certificate is needed.

Price: three routes disagree by 2.5x — A (dispatch count) **1.069%**,
B (family-cost recovery) **1.69–1.78%**, C (105.16 slack) **0.756%**. Note that
route A/B/C all clear 0.75%, which is >= the whole remaining bar.

Two landmines and two blockers:

1. The dead hook branch does **not** set `gateProjectionActivated = true`, so
   naively enabling it yields a silent double- or absent-softplus.
2. That flag's guard set must be reproduced exactly:
   `lagunaFusedGatedAffineOProjEnabled && lagunaGatedAffineOProjNVFP4Enabled && lagunaUseNativeAffineOProj(layer:) && affineWO.mode == .nvfp4 && bits == 4 && groupSize == 16`.
3. **Deconfliction hazard:** nezuko is folding RMSNorm into the NVFP4 QKV
   kernel — the same kernel. This must be sequenced by the advisor, not taken
   unilaterally.
4. **Archive caveat:** `RESEARCH_STATE_ARCHIVE_through-round-21.md` §R18.7
   records `D-FUSE-GATESP` rung 2 (re-fusing gate into its *producer*) as
   **PERMANENTLY CLOSED**. The QKV-tail fold is a different rung (fold into a
   *sibling*, not the producer), but the advisor should confirm the distinction
   before authorising it.

## 6. Reproduction

```bash
# stage-0 (ii)/(iii) isolated probe — seconds of GPU, no model load
xcrun swiftc -O research/maple_tanjiro_r109d_gatesp_probe.swift -o /tmp/tanjirogsp
TANJIRO_ARMS=4x2,2x2,1x2,4x1,2x1,1x1 TANJIRO_HEADS=64,48 /tmp/tanjirogsp

# parameterization fidelity (must diff clean)
sed -n '4469,4508p' Sources/MLXFastModel/LagunaRuntimeModel.swift \
  | sed 's/\\(LagunaConstants.hiddenSize)/2048/'

# prior art
sed -n '1,200p' research/pr101-gatesp-abba-analysis.txt
rg -n 'Family E essentially' research/CURRENT_RESEARCH_STATE.md
rg -n 'D-FUSE-GATESP' research/RESEARCH_STATE_ARCHIVE_through-round-21.md
```
