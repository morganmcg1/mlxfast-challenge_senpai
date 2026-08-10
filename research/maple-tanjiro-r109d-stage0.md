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
| (i) extract-round kill number | **NOT A KILL on stage 0**, and now **REFUTED end to end**. The extract-round removal itself is real (isolated −1.505 us/dispatch × 40 = −60 us/step; measured end-to-end **−49.6 us/step**, so busy-additivity holds for that kernel). But *binding* the extra `indices` input — without reading it — costs **+102.0 us/step**, so the shipped-vs-candidate contrast is **+52.4 us/step, a loss**. The advisor's "expected removal ≈ 0" premise was wrong; the arm still fails, for a different reason. §1. |
| (ii) current + proposed threadgroup counts | current **8 TGs (h64) / 6 TGs (h48)** on a 20-core GPU. Ladder to R1NS2 gives **32 / 24**; R1NS1 gives 64 / 48 (>40, flagged). §2. |
| (iii) single-kernel timing of option (1) | measured fresh on this host: **−2.026 us/dispatch, −41.13%, t = −124** at R1NS2, bit-exact (40/40 comparisons `diff 0`). **But it is not an occupancy effect** — cost is a pure function of `R` and is *invariant* to threadgroup count (R4 costs 4.91 us at both 8 and 16 TGs; R2 4.31 at both 16 and 32; R1 ≈2.93 at both 32 and 64), so the stated mechanism is refuted by its own dose axis. §4.1. |

**Recommendation: do not spend the implementation budget on option (1).** Three
independent lines of evidence kill it:

1. **Prior end-to-end null.** The exact experiment (an env-gated `R`/`NS`
   occupancy knob on `laguna_gate_sp`) was already run to a full end-to-end ABBA
   conclusion in this campaign on PR #101 (student frieren, arm A). Isolated
   −43%; end-to-end **+0.04% (95% CI [−0.48%, +0.55%], permutation p = 0.886)** —
   the microbench prediction of −0.87% is *excluded* by that interval. §4.2.
2. **The dispatch is already hidden.** GPUPROF timestamp analysis of a shipped
   decode step shows `laguna_gate_sp` is **96.44% covered** by concurrently
   executing kernels (h64 98.01%, and 98.01% of h64 busy time is *wholly nested
   inside a single* `laguna_decode_nvfp4_qkv_h64…` dispatch). Exposed
   critical-path time is **61.7 of 1731.9 us** in that trace. It is the only
   substantially nested decode kernel; every other decode kernel is ~100%
   exposed. So busy-time additivity — which is sound elsewhere — is unsound
   *here*. §4.3b, §4.3b-ii.
3. **The stated mechanism is wrong.** The kernel is latency-bound on the serial
   chain of `R` row accumulations, not occupancy-starved: doubling threadgroups
   at fixed `R` (`R4xNS1`) is a resolvable **regression** (+0.053 us, +1.08%,
   t = +2.71), while halving `R` at fixed threadgroup count wins. §4.1.

Realistic ceiling: **≈4.4 M5 us/step** of critical path (124.0 M5 us/step for
this family × 3.56% exposed) ≈ **0.03% score** even if the kernel were deleted
outright — about 50× smaller than the −180 to −240 us/step the brief targets,
and far below this host's resolution floor (best paired half-width 8.91 us/step;
harness identical-code null `[−14.25, +32.09]`). §4.4.

Side finding worth banking campaign-wide: because decode dispatches *do* overlap
(sum/union of busy time = **1.1359**, 11.96% hidden), archive **§6333 "zero
dispatch concurrency in decode" should be treated as RETRACTED**. R109-C's
+102 us/step price for one added dependency edge is independent corroboration.
§4.3c.

A different, unmeasured gate_sp idea exists (fold the gate GEMV into the NVFP4
QKV kernel tail, using the already-wired dead hook `fusedTailGateLogits`). It was
priced at 0.76%–1.78% by three disagreeing routes; **all three of those routes
price gate_sp's busy time, so finding 2 above deflates them by ~28×** and the
fold's remaining value is whatever the *fusion* itself buys (one fewer dispatch,
one fewer `normalized` read), not the gate GEMV time. It also has a real
deconfliction hazard with nezuko and a "permanently closed" archive entry that
must be read first. Details and the revised pricing in §5.

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

### 1.1 End-to-end resolution (that risk is exactly what killed it)

The ABBA finished after this section was first written. Full report:
`research/maple-tanjiro-r109c-result.md`. Three-arm rotate design, 5 usable
reps × 36 slots, one token-stream checksum across all arms:

| contrast | mean us/step | 95% hw | sign |
| --- | --- | --- | --- |
| base→p1 (bind `indices`, never read it) | **+102.00** | 17.19 | 5/0 |
| base→p2 (ranked candidate) | **+52.38** | 8.91 | 5/0 |
| p1→p2 (the extract-round removal alone) | **−49.62** | 22.05 | 0/5 |

The mechanism decomposes cleanly. `p1→p2 = −49.62` versus the isolated
prediction of −60.2 us/step confirms busy-additivity for this
execution-dominated kernel to within 18%. But `base→p1 = +102.00 us/step`
(+2.55 us/layer) is the price of the *dependency edge* alone: the new
`indices` input is produced by `laguna_router_top8_ordinal` in the same MLX
command encoder, so `set_input_array` marks a RAW hazard and
`maybeInsertBarrier` emits an **encoder-global**
`memoryBarrier(BarrierScopeBuffers)` — serializing everything in flight, not
just this pair. Net **+52.4 us/step, a loss**, sign-consistent 5/0.

Consequence for the composition plan: the R109-C mechanism **cannot be
composed** into fern's B×C stack as written, because the `inds` dependency is
what pays for it. The reusable finding is that on the shipped decode path
`inds` carries a full-slot **ORDER** dependency (proved in
`research/maple-tanjiro-r109c-stage0.md`), so any consumer that wants it must
either produce it itself or accept an encoder-global barrier.

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

`research/maple_tanjiro_r109d_gatesp_probe.swift`, 21 alternating paired rounds
of 200 dispatches, reference arm = the shipped `R=4 NS=2`. Every arm runs the
same MSL body with only the two geometry constants changed, and the probe
refuses to print any timing until a bitwise gate passes.

**Bit-exactness gate: PASS.** All five variant arms produced byte-identical
`gate_values` versus the shipped geometry at both head counts (h64 128 B, h48
96 B) across binding slots {0, 1, 7, 199}: `diff 0` in 40/40 comparisons,
`ref self-diff 0`. This confirms §3's static argument empirically.

| arm | rows/TG | thr/TG | TG@h64 | TG@h48 | ref_min us | var_min us | d_mean us | d_sd | d%_ref | t_paired |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R4xNS2 (shipped) | 8 | 64 | 8 | 6 | 4.91 | — | — | — | — | — |
| R2xNS2 | 4 | 64 | 16 | 12 | 4.91 | 4.31 | −0.929 | 1.318 | −18.90% | −3.23 |
| **R1xNS2** | 2 | 64 | **32** | **24** | 4.93 | 2.94 | **−2.026** | 0.075 | **−41.13%** | **−124.3** |
| R4xNS1 | 4 | 32 | 16 | 12 | 4.91 | 4.94 | **+0.053** | 0.090 | **+1.08%** | +2.71 |
| R2xNS1 | 2 | 32 | 32 | 24 | 4.91 | 4.31 | −0.594 | 0.029 | −12.10% | −92.8 |
| R1xNS1 | 1 | 32 | 64 | 48 | 4.91 | 2.92 | −1.996 | 0.016 | −40.69% | −558.9 |

(h64 rows; h48 agrees within 1 percentage point on every arm. The R2xNS2 `d_sd`
of 1.318 is one cold first round at −6.51 us; rounds 8–21 are all −0.59 ± 0.05.)

Decode-step projection (30 h64 + 10 h48 dispatches, min-of-5 per-dispatch cost):

| arm | us/step | vs shipped |
| --- | --- | --- |
| R4xNS2 | 195.9 | +0.0 |
| R2xNS2 | 171.9 | −24.0 |
| **R1xNS2** | **116.4** | **−79.5** |
| R4xNS1 | 196.7 | +0.8 |
| R2xNS1 | 172.2 | −23.7 |
| R1xNS1 | 116.1 | −79.8 |

**The isolated win reproduces PR #101's −41% and it is not an occupancy win.**
Read the table by threadgroup count and it makes no sense; read it by `R` and it
is perfectly clean:

| R (rows serialized per simdgroup) | per-dispatch us | TG counts observed at this R |
| --- | --- | --- |
| 4 | 4.91 / 4.94 | 8 **and** 16 |
| 2 | 4.31 / 4.31 | 16 **and** 32 |
| 1 | 2.94 / 2.92 | 32 **and** 64 |

* `R4xNS1` **doubles the threadgroup count** (8 → 16) at fixed `R` and buys
  **+0.053 us, i.e. nothing** (+1.08%, `t` = +2.71 on a 0.09 us sd — a
  statistically resolvable *regression*, not a win).
* `R1xNS1` **doubles the threadgroup count again** versus `R1xNS2` (32 → 64) and
  is identical to it (−1.996 vs −2.026 us).
* Cost is a pure function of `R` at every threadgroup count tested.

So the kernel is **not** starved of parallelism at 8 threadgroups on a 20-core
GPU. It is limited by the serial chain of `R` row accumulations inside each
simdgroup — a latency bound, not an occupancy bound. **The advisor's stated
mechanism for option (1) ("8 threadgroups leaves 32 of the M5's 40 cores idle")
is refuted by its own dose axis**: supplying more threadgroups at constant `R`
changes nothing. This matters beyond this arm, because "raise the threadgroup
count" is the reusable half of the hypothesis and it is the half that does not
work here.

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

Two candidate mechanisms explain the PR #101 null. I measured both. **The second
one is the true mechanism, and it also retracts an archive claim.**

#### 4.3a Candidate 1 — "the kernel is its own dispatch overhead" (partly true, not sufficient)

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

This is not sufficient on its own, because the isolated probe (§4.1) shows the
per-dispatch cost *does* fall by half when threadgroups go 8 → 32. If the cost
were a pure launch price the isolated number would barely move. Something else
has to absorb the recovered execution time.

#### 4.3b Candidate 2 — the dispatch is already hidden behind QKV (measured, decisive)

New evidence this session: `research/maple-tanjiro-r109d-overlap.py` reconstructs
per-dispatch GPU busy intervals from a `SPLIT=1` GPUPROF worker log
(`research/pr270-logs/split1.worker.err`, 12,512 dispatches, exactly one decode
step's worth of gate_sp: 30 h64 + 10 h48) and asks, for each kernel, how much of
its busy time is *covered by the union of other kernels' intervals*.

| quantity | value |
| --- | --- |
| whole log `gpu_busy_sum` | 5,304,119.3 us |
| whole log `gpu_busy_union` | 4,669,500.3 us |
| sum / union | **1.1359** (11.96% of all busy time is overlapped) |
| `laguna_gate_sp` busy | 1,731.9 us |
| `laguna_gate_sp` covered by other kernels | 1,670.2 us |
| `laguna_gate_sp` **exposed** | **61.7 us ⇒ 96.44% HIDDEN** |
| h64 (30 dispatches, 1,303.5 us) | 98.01% hidden |
| h48 (10 dispatches, 428.3 us) | 91.67% hidden |

The covering kernel is overwhelmingly the QKV projection it is encoded next to:
`laguna_decode_nvfp4_qkv_h64_r1_v1_lm1_pw1_se1_sd1` covers **1,277.5 us** of it,
then `sdpa_vector_...` 234.0 us and `gg2_copybfloat16bfloat16` 133.6 + 96.8 us.

Worked example (two consecutive layers, same shape):

```
qkv      [.114653500, .114794750]   141.25 us
g3_copy  [.114675167, .114726167]   nested inside qkv
gate_sp  [.114726167, .114769500]   nested inside qkv
qkv      [.118796000, .118937000]   141.00 us
gate_sp  [.118850375, .118892417]   nested inside qkv
```

`gate_sp` is also encoded *after* `sliding_fused_attn` in file order yet executes
*before* it, which is direct evidence of genuine out-of-order concurrent
execution inside MLX's `MTLDispatchTypeConcurrent` encoder
(`Vendor/mlx-swift/.../metal/device.cpp:545-549`).

So the reason a 43% isolated win lands as +0.04% is not that the execution time
is unreal — it is that **the execution time was never on the critical path**.
Making a hidden kernel faster changes nothing until it stops being hidden.

#### 4.3b-ii Confirmation by an independent estimator, and the containment test

The number above comes from an O(n²) per-window set-difference. I added an
independent O(n log n) sweep (`--all`) that attributes every instant at which
*exactly one* dispatch is in flight to its owner. It reproduces the focus-loop
result exactly (h64 26.0 us and h48 35.7 us exposed) and ranks every kernel in
the trace at once.

That ranking exposes a trap that has to be handled or the table is misleading:
`%hidden` is symmetric, so a **long** kernel with **short** kernels nested inside
it also scores as "hidden". `laguna_decode_nvfp4_qkv_h64` reads 67.56% hidden —
but it is the *container*, and deleting a container does shorten the union. The
asymmetric test is containment: is this dispatch wholly inside one *other*
dispatch's window? I added that column too.

| decode kernel | n | busy us | exposed us | %hidden | %nested |
| --- | --- | --- | --- | --- | --- |
| `laguna_decode_nvfp4_qkv_h64_…` | 30 | 4,227.1 | 1,371.1 | 67.56% | **0.00%** |
| `laguna_decode_nvfp4_qkv_h48_…` | 10 | 1,207.8 | 300.4 | 75.13% | **0.00%** |
| `laguna_gate_sp_h64_v1` | 30 | 1,303.5 | **26.0** | 98.01% | **98.01%** |
| `laguna_gate_sp_h48_v1` | 10 | 428.3 | **35.7** | 91.67% | 0.00% |
| `laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2` | 46 | 6,662.5 | 6,662.5 | 0.00% | 0.00% |
| `laguna_residual_rms_bf16_2048_v1` | 274 | 6,572.2 | 6,572.2 | 0.00% | 0.00% |
| `laguna_oproj_act_h64_v1_…` | 30 | 3,171.7 | 3,171.7 | 0.00% | 0.00% |
| `laguna_sliding_fused_attn_ring_v1_…` | 30 | 2,633.2 | 2,633.2 | 0.00% | 0.00% |
| `laguna_routed_shared_nvfp4_down_residual_bf16_r1_v5` | 46 | 2,482.0 | 2,482.0 | 0.00% | 0.00% |
| `laguna_decode_router_top8_ordinal_table_norm_v1` | 46 | 774.7 | 628.8 | 18.83% | 0.00% |
| `laguna_shared_nvfp4_swiglu_qmv_rows1_bf16_v1` | 46 | 866.0 | 720.2 | 16.84% | 0.00% |

`laguna_gate_sp_h64_v1` is the **only** decode kernel in the trace that is
substantially nested: 98% of its busy time sits wholly inside one QKV dispatch's
window. h48 shows 91.67% covered but 0% *fully* nested, i.e. it is covered by a
union of neighbours while poking past the end of any single one; covered is still
the correct free-ness test for a short kernel, so its ≈8% exposed stands, but I
am flagging the weaker form of the evidence rather than rounding it up.

Everything else on the decode path is 0% nested and mostly 0% hidden. That is the
useful campaign-wide reading of this table: **`gate_sp` is the anomaly, and every
other decode kernel's busy time is real critical-path time.** The busy-additivity
conversion the campaign relies on is therefore sound *in general* and unsound
*specifically here* — which is exactly the pattern in this PR's two arms, where
the same conversion cross-validated to 18% on the execution-dominated gate/up
kernel (predicted −60.2, measured −49.6 us/step) and fails by ~30x on `gate_sp`.

#### 4.3c Retraction: archive §6333 "zero dispatch concurrency in decode"

`RESEARCH_STATE_ARCHIVE_through-round-21.md` §6333 records
`gpu_busy_sum == gpu_busy_union` in decode and concludes there is no dispatch
concurrency. My analyzer reproduces that equality exactly on a `SPLIT=0` log
(sum == union == 540.396 ms, "0.00% hidden") — **and it is an artifact of
profiling granularity.** With `SPLIT=0` the worker uses `cbs = 81` command
buffers per request, so each GPUPROF record is a whole *command buffer* spanning
2–3 decoder layers; the names are `A|B|C|…` concatenations that contain
`gate_sp` merged with `rms`, `decode_nvfp4_qkv`, `g3_copy`,
`sliding_fused_attn_ring`, `oproj_act`, `residual_rms_router`,
`shared_nvfp4_swiglu_qmv`, `decode_router_top8_ordinal`,
`routed_nvfp4_swiglu_qmv_packed_top8keys` and
`routed_shared_nvfp4_down_residual`. Command buffers cannot overlap each other,
so `sum == union` is *trivially* true at that granularity and says nothing about
dispatch concurrency. `SPLIT=1` (`cbs = 1066`) exposes per-kernel timestamps and
immediately shows sum/union = 1.1359.

**Recommendation: treat §6333 as retracted.** Decode does have real dispatch
concurrency. Independent corroboration from the *other* arm of this same PR: in
R109-C, merely adding one input binding — creating one dependency edge and hence
one encoder-global barrier — cost **+102 us/step (+2.55 us/layer)** end to end
with no change in work done. A barrier cannot cost that much if nothing was
overlapping.

Caveat on magnitude, stated honestly: `SPLIT=1` is not the shipped command-buffer
structure and its per-dispatch durations are inflated ~4–10x versus isolated
microbenchmarks (gate_sp 43.4 us there vs 5.56 us isolated; routed gate/up 162.2
us vs 38.65 us). Use the *hidden fraction*, not the absolute microseconds.

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

**Recommended magnitude to plan against.** Take the trusted family number (124.0
M5 us/step for family E) and apply the measured *exposed* fraction from §4.3b
(3.56%): **≈4.4 M5 us/step is on the critical path.** At the advisor's own score
conversion that is ≈0.03% score for *completely deleting* `laguna_gate_sp`, let
alone halving its execution time. The −180 to −240 us/step target is unreachable
by a factor of ~50, and the end-to-end interval needed to detect ≈4 us/step is
far narrower than this host's noise floor (my best paired half-width this session
was 8.91 us/step, and the harness' own identical-code null bound is
[−14.25, +32.09]).

Two knock-on consequences the advisor should fold in:

1. It also deflates the §5 QKV-tail gate fold. If gate_sp is 96% hidden, folding
   it into the QKV tail can only recover the exposed ≈4 us/step, while §5's own
   price routes cost 0.76%–1.78%. §5 should be repriced or dropped.
2. It is consistent with, not contradicted by, my own PR #663 result
   (`N-NO-MERGEABLE-PAIR`, dispatch-count reduction retired campaign-wide,
   70.6% of the decode step is genuine serial dependence): the serial 70.6% is
   the critical path, and `gate_sp` simply is not on it.

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

**Revised price after §4.3b.** Routes B and C recover gate_sp's *busy* time, and
96.44% of that busy time is hidden behind the very kernel this fold would merge
into — so those two routes must be scaled by the 3.56% exposed fraction, taking
1.69–1.78% down to **≈0.06%** and 0.756% down to **≈0.03%**. Route A (dispatch
count) is the only route that survives, because removing a dispatch removes
encode + barrier cost that is *not* hidden; but this campaign has already retired
generic dispatch-count reduction as a family (`N-NO-MERGEABLE-PAIR`, PR #663:
70.6% of the decode step is genuine serial dependence). The honest revised
estimate for the QKV-tail gate fold is therefore **route A only, and no more than
route A**, i.e. ~1% *if and only if* the encode/barrier saving is real for this
specific pair — which needs its own measurement before any implementation
budget. Do not carry 1.78% forward.

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

# overlap / nesting analysis (no GPU needed, reads a committed trace)
python3 research/maple-tanjiro-r109d-overlap.py research/pr270-logs/split1.worker.err
python3 research/maple-tanjiro-r109d-overlap.py research/pr270-logs/split1.worker.err --all

# prior art
sed -n '1,200p' research/pr101-gatesp-abba-analysis.txt
rg -n 'Family E essentially' research/CURRENT_RESEARCH_STATE.md
rg -n 'D-FUSE-GATESP' research/RESEARCH_STATE_ARCHIVE_through-round-21.md

# R109-C end-to-end ABBA (26 min GPU, needs /tmp/maple-r109c-snap)
SNAP=/tmp/maple-r109c-snap OUT=/tmp/maple-r109c/rung1 REPS=6 WARMUP_REPS=1 \
  STEPS=250 DESIGN=rotate ASSERT_DIFFER=" " ASSERT_SAME=s:s \
  ARMS="base:s p1:s:DARKBLOOM_GATEUP_INDS=1 p2:s:DARKBLOOM_GATEUP_INDS=2" \
  research/maple-frieren-r103a-abba.sh
python3 research/maple-frieren-r103a-analyze-multi.py /tmp/maple-r109c/rung1
```
