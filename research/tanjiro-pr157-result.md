# PR #157 — Graph co-residency falsifier: does this stack overlap ANY two independent kernels?

SENPAI-RESULT: {"terminal":true,"status":"complete","pending_arms":false,"wandb_run_ids":[],"primary_metric":{"name":"coresidency_overlap_fraction_at_prefill_occupancy","available":true,"value":0.0120},"test_metric":{"name":"passed_correctness","available":false,"value":null}}

- **Student / PR:** maple-tanjiro / #157
- **Hypothesis and target cost:** Step 0 asks whether the campaign's
  `gpu_busy_sum == gpu_busy_union` readings mean (a) the instrument is blind,
  (b) nothing shadows, or (c) M4 ≠ M5 — and whether two independent kernels can
  co-reside at all. Zero scored bytes; the §3 two-chunk wavefront prefill was
  gated on a GO.
- **Decision:** **dead hypothesis** for Attack B (graph-level overlap) at
  prefill occupancy. The instrument question is resolved in favour of **(a)**,
  but (a) does *not* rescue the mechanism: overlap is independently measured and
  is 0.006–0.012 at the real 9,792-threadgroup width where prefill lives.
- **`BASE_SHA` / candidate commit:** base `9dd2eec38a11d0e0bc7bcdbc5aec46e3436f284f`
  / candidate = head of `maple-tanjiro/graph-coresidency-falsifier`, whose exact
  SHA is recorded as `expected_head_sha` in the typed `submit_result`
  transition. Branch contents: `f1ed713` (pre-registration + probe), `b19f984`
  (2-CB controls + interval evidence), `635939e` (prefill-scale sweep + run-1
  log), and this result commit.
- **Submitted candidate files:** **none.** Zero bytes of `editablePaths` touched;
  editable budget and per-file caps unchanged (2,926,911 / 3,000,000).
- **Supporting test or documentation files:** `research/tanjiro-pr157-prereg.md`,
  `research/tanjiro_coresidency_probe.swift`, `research/pr157-logs/*.log`, this file.
- **Official submission `--model` value:** n/a — no receipt requested, no
  submission dispatched. Per the advisor's 2026-08-06T20:48Z comment I am not
  the queue owner and did not poll `mlxfast submissions`.
- **Assignment-scope preflight:** no submitted path proposed, so
  `validate-assignment-scope.sh` has an empty path list; growth = 0 B.
- **Scored-path reachability evidence:** n/a for this arm (no runtime change).
  Reachability of the *proposed* §3 control is addressed in §6 below and is
  what kills it.

---

## 1. What was built

`research/tanjiro_coresidency_probe.swift` — a standalone Swift + raw-Metal
probe with no MLX linkage, so nothing about MLX's scheduler can contaminate the
question "can this GPU overlap two independent kernels at all?".

```bash
xcrun swiftc -O research/tanjiro_coresidency_probe.swift -o /tmp/tjcores \
  -framework Metal -framework Foundation
/tmp/tjcores 9 20        # 9 rounds, each cell calibrated to ~20 ms
```

Three kernel families (`k_alu` compute-bound, `k_mem` 256 MB grid-stride
stream, `k_gemm` TS=16 tiled bf16) crossed with **nine arms**:

| arm | construction | role |
| --- | --- | --- |
| `a_only`, `b_only` | one kernel, one CB | isolation reference |
| `concurrent_1cb` | both kernels, one CB, `MTLDispatchTypeConcurrent` | **this is MLX's only concurrency mechanism** (`device.cpp:548`) |
| `barrier_1cb` | both kernels, one CB, explicit barrier between | serialization control |
| `raw_1cb` | B reads A's output → genuine RAW hazard | serialization control |
| `serialenc_1cb` | two serial encoders in one CB | serialization control |
| `two_cb` | two CBs, one queue | cross-CB co-residency |
| `two_queue` | two CBs, two queues | **instrument positive control** |
| `two_cb_serial` | CB2 committed only after CB1 retires | **instrument negative control** |

Discipline: per-cell clock pinning burn, shuffled cell order within each round,
within-round ratios only, median over 9 rounds with bootstrap CI, and every
GEMM shape's `K` calibrated so threadgroup count is swept **without** changing
kernel duration. Round 0 dumps each CB's `[start–end]` interval so co-residency
is shown directly rather than inferred.

Two headline metrics:

- `overlap = 1 − wall(arm) / (wall_a + wall_b)` — the assignment's `1 − union/sum`.
- `overlap_eff = (iso_sum − wall) / (iso_sum − max(wall_a, wall_b))` — fraction
  of the *achievable* saving realized; 1.0 means the shorter kernel is fully hidden.

Host: Apple M4 Pro, **20 GPU cores**, `applegpu_g16s`, 48 GiB, macOS 26.5.2.
`counterSampling.atDispatchBoundary = false` on this host, so per-dispatch
counter sampling is not available — which is itself part of the answer below.

---

## 2. Deliverable 2 — how `gpu_busy_union` is actually computed (code read)

**It is per *command buffer*, not per dispatch. There is no per-dispatch
timeline anywhere in this repository.**

- Producers: `research/decode_probe.py:147-192` (`analyze_profile`), merge loop
  at `:177-186`, print at `:187-192`; the prefill twin is
  `research/prefill_probe.py:148-165`.
- Input: `GPUPROF <gpu_start_s> <gpu_end_s> <nops> <input_bytes> <names>` lines,
  **one per command buffer**, emitted from a CB completion handler installed by
  `research/pr91-gpuprof-hook.patch`, which patches `CommandEncoder::commit()`
  in `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp` (~`:578-595`)
  and reads `cbuf->GPUStartTime()` / `GPUEndTime()`.
- `gpu_busy_sum` = Σ(end − start) over CBs; `gpu_busy_union` = length of the
  merged interval union over the same CBs.
- MLX packs **20–50 ops into each command buffer** (`device.cpp:576-596`) and
  submits them on **one queue**. Command buffers on a single queue do not
  overlap. Therefore `union == sum` is very nearly **guaranteed by
  construction** for any MLX run, no matter how much intra-CB concurrency the
  hardware achieves.
- The only per-dispatch attribution ever used was `DARKBLOOM_GPU_PROFILE_SPLIT`,
  which forces **one dispatch per CB** in `needs_commit()`. PR #73 run A used
  `SPLIT=1` and reported `cbs=406 dispatches=406`
  (`research/maple-tanjiro-pr73-decode-kernel-census.md:721`, driver `:145-146`,
  raw log `research/pr73-logs/split1-runA.txt`). With one dispatch per CB and
  one queue, `union == sum` is **doubly** guaranteed — that run is self-refuting
  as evidence about concurrency.
- No counter-sample-buffer, `MTLCaptureManager`, Instruments, or xctrace path
  exists in `research/`, `Sources/`, or `Vendor/.../backend/metal`.

Incidental live bug worth fixing separately: the retained hook emits 5 numeric
fields but `decode_probe.py:160` parses with `split(" ", 4)`, so per-kernel
names get fragmented. Sum/union/gap/cbs/dispatches are unaffected.

---

## 3. Deliverable 1 — instrument controls

Every number below is `cb_busy_sum` / `cb_busy_union` computed by an **exact
reimplementation of `decode_probe.py:177-186`** applied to this probe's own CB
timestamps, so the metric under test is literally the campaign's metric.

| arm | cbs | `gpu_busy_sum` (ms) | `gpu_busy_union` (ms) | `1 − union/sum` | wall (ms) | verdict |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `two_queue` (positive control) | 2 | 27.586 | 13.798 | **0.4998** | 13.986 | **PASS** — union ≪ sum |
| `two_cb` (positive control) | 2 | 27.586 | 13.799 | **0.4998** | 13.979 | **PASS** |
| `two_cb_serial` (negative control) | 2 | 27.586 | 27.586 | **0.000000** | 27.959 | **PASS** — union ≈ sum |
| `concurrent_1cb` (**MLX's mechanism**) | 1 | 13.793 | 13.793 | **0.000000** | **13.954** | **metric blind** |

(`alu/alu`, tg=2, 9 rounds, 20 ms cells; layout evidence from round 0:
`[0.000-55.093] [0.112-55.093]` for a co-resident pair,
`[0.000-19.694] [19.903-39.790]` for the forced-serial pair.)

**The instrument is healthy and it is still blind.** The positive control
proves the metric *can* report cross-CB overlap; the negative control proves it
does not hallucinate overlap. But `concurrent_1cb` — the arm that reproduces
MLX's actual mechanism — reports `1 − union/sum = 0.000000` while the wall clock
shows the two kernels finishing in 13.954 ms against a 27.939 ms isolated sum,
i.e. `overlap_eff = 1.0024`, **perfect hiding**. One command buffer is one
interval, and a union over one interval can never be shorter than its sum.

`cb_overlap == 0.000000` in **every** single-CB cell of the run, at every size,
for every kernel family, including cells where wall-clock overlap is 50%.

### Ruling on §4.1

- **(a) instrument blind — CONFIRMED, with a positive control.** This is now a
  demonstrated property of the metric, not a hypothesis. `gpu_busy_sum ==
  gpu_busy_union` to 6 ns in `nezuko-decode-roofline.md:193-202` is an
  **artifact of per-CB accounting on a single queue** and carries no
  information about concurrency. Any campaign claim of the form "nothing
  overlaps, because sum == union" must be withdrawn.
- **(b) no shadowing — SEPARATELY TRUE at prefill occupancy, for a different
  reason.** §4 measures real overlap directly with wall clock and finds it
  collapses to 0.006–0.012 once the machine is full. (a) and (b) are not mutually
  exclusive; the campaign framed them as competing, and that framing was wrong.
  The instrument was blind *and* there is little to see at prefill sizes.
- **(c) M4 ≠ M5 — not needed to reconcile the three facts, and quantitatively
  implausible as a rescue.** See §5 for the transfer margin.

---

## 4. Deliverable 3 + 4 — real overlap and the size sweep

`concurrent_1cb` is the arm to read: it is MLX's mechanism. Two independent
bf16 GEMMs, duration held at ~20 ms each by per-shape `K` calibration, so the
only variable is threadgroup count against 20 cores.

Two independent 9-round runs were taken: `coresidency-full-r9-t20ms.log` (run 1)
and `coresidency-extended-r9-t20ms.log` (run 2, which adds the 512 / 2048 / 9792
threadgroup cells and the `moe512` shape). Run 2 is quoted below because it
covers every cell; run 1's overlapping cells agree within CI and both numbers
are given where they differ.

| GEMM shape | threadgroups | `overlap` (median) | 95% CI | `overlap_eff` |
| --- | ---: | ---: | --- | ---: |
| `small` 64×64 | 16 (< cores) | **0.5005** | [0.4785, 0.5197] | 1.0112 |
| `half` 128×160 | 80 (4× cores) | **0.0542** | [−0.0246, 0.1883] | 0.1192 |
| `fill` 512×1024 | 2048 (102× cores) | **0.0213** | [0.0069, 0.0276] | 0.0426 |
| `moe512` 512×4896 | 9792 (490× cores) | **0.0064** | [−0.0089, 0.0179] | 0.0128 |

Run 1 read the same three shapes at 0.4999 / 0.0625 / 0.0159. The `moe512` row
is the one that matters: 9,792 threadgroups is the measured per-layer dispatch
width of the compacted MoE gather-GEMM at 512 tokens (§5), and at that width two
independent GEMMs overlap by **0.6%**, with a 95% CI that includes zero.

The `alu/alu` ladder isolates the same effect more finely (tg = 2/5/10 →
0.50, then tg = 20 → 0.0063, tg = 240 → 0.0276, tg = 1000 → 0.0166). The one
non-monotonicity is tg = 40 → 0.2274 [0.2217, 0.2339]; it **reproduced almost
exactly across both independent runs** (0.2300 in run 1), so it is a real
feature of the dispatcher and not noise, but I cannot explain it from a pure
wave model and report it as observed. It does not affect the conclusion because
every point at or above 20 threadgroups except that one is below 0.05, and
prefill is two to three orders of magnitude above 20.

**Mechanism is straightforward and unsurprising in hindsight:** overlap is not
a scheduler property, it is a *spare capacity* property. Two kernels overlap
exactly when one of them fails to fill the machine. `k_alu` at 2 threadgroups
uses 10% of the cores, so a second copy is free. At 2048 threadgroups the first
kernel already owns every core, and the second can only wait.

### 4a. The mixed-resource case, at real prefill scale

The strongest objection to the above (raised by an independent frontier review
and correct) is that `alu/alu` and `gemm/gemm` pit **same-resource** kernels
against each other, which is the worst case. The realistic wavefront pairing is
**bandwidth-bound MoE gather-GEMM ∥ compute-bound attention**, which is
complementary. The `alu/mem` pair tests exactly that:

| threadgroups | `overlap` (median) | 95% CI | `overlap_eff` |
| ---: | ---: | --- | ---: |
| 2 | 0.4954 | [0.4697, 0.4988] | 0.9999 |
| 10 | 0.4829 | [0.4602, 0.4959] | 1.0006 |
| 20 | 0.4781 | [0.4731, 0.4930] | 0.9714 |
| 240 | 0.0817 | [0.0728, 0.0874] | 0.1672 |
| 512 | 0.0516 | [0.0503, 0.0620] | 0.1033 |
| 2048 | 0.0218 | [0.0167, 0.0251] | 0.0441 |
| **9792** | **0.0120** | **[0.0022, 0.0138]** | **0.0259** |

Complementary resources do help, and the mixed pair beats the same-resource pair
at every occupancy above the residency ceiling — 0.082 vs 0.028 at 240
threadgroups, and 0.012 vs 0.006 at 9,792. But that ~2–3× advantage is a
multiplier on a number that is already tiny. The decay is smooth and monotone
from 240 upward, and by the time occupancy reaches the real MoE prefill width of
9,792 threadgroups the **best case for the mechanism — bandwidth-bound streaming
against compute-bound ALU, the most complementary pair I can construct — hides
1.2% of the shorter kernel.** That is a factor of **12 below** the 0.15 GO
threshold I pre-registered, and the mixed-pair curve reaches the threshold only
somewhere below 240 threadgroups, i.e. more than 40× below where prefill starts.

This is the single most important row in the report. It removes the only
substantive objection to §4 (that the same-resource pairs were the worst case)
and the answer does not change: complementary pairing buys a 2–3× multiplier on
approximately nothing.

### 4b. A cross-command-buffer pathology (reported, not relied on)

Bandwidth-bound kernels in **separate** command buffers anti-scale severely:
`mem/mem` `two_cb` gives `overlap` −0.41 (tg=2), **−1.21** (tg=10), **−2.29**
(tg=20) — a 3.3× slowdown versus running them back to back. The extended run
shows the pathology is **confined to low occupancy**: it recovers to 0.004
(tg=240), 0.001 (tg=512), 0.004 (tg=2048) and 0.010 (tg=9792). Round-0 layout
confirms the two CBs are genuinely simultaneous. The same work in **one** CB
(`concurrent_1cb`) shows no pathology at all (0.50 / 0.50 / 0.50 / −0.008). I
have no confirmed mechanism, so I draw no conclusion from it beyond a warning:
if anyone tries multi-queue or multi-CB scheduling in this stack at small
dispatch widths, measure it, because the naive expectation is badly wrong.
MLX's single-queue, single-CB concurrency avoids it entirely.

### 4c. One arm that did *not* collapse, reported for completeness

At the largest mixed-resource cell (`alu/mem`, tg=9792) the two **separate**
command-buffer arms beat MLX's intra-CB arm: `two_queue` 0.1268
[0.0528, 0.1937] and `two_cb` 0.0546 [0.0454, 0.1487] versus `concurrent_1cb`
0.0120. Taken alone that would suggest a multi-queue mechanism recovers real
overlap where `MTLDispatchTypeConcurrent` does not.

I am not relying on it, for three reasons. (1) It is **not monotone**: the same
arms at tg=512 give 0.013 / 0.016, *below* the intra-CB arm, and at tg=2048 the
`two_cb` CI is [0.0217, 0.4706] — 22 points wide. (2) Even at its best,
0.127 × the 25–35 ms of hideable attention is 3–4 ms, still 4–5× smaller than
the +16.6 ms wavefront tax computed in §6, so it does not change the GO/NO-GO.
(3) MLX has no multi-queue path; `device.cpp` uses one queue per stream, so
exploiting this would be a scheduler rewrite, not a chunking change. It is
logged in §8 as a follow-up someone could probe properly, not as a result.

---

## 5. Where prefill actually sits

Dispatch geometry for a 512-token prefill, read from source and cross-checked
against the merged route histogram's own `dispatch_tiles` block
(`research/artifacts/route-histogram-prefill512-stats.json`):

| kernel family | grid | threadgroups | × 20 cores |
| --- | --- | ---: | ---: |
| MoE gather-GEMM `gate_up`, per layer (dense) | (16, 256) | 4,096 | 205× |
| MoE gather-GEMM `down`, per layer (dense) | (32, 256) | 8,192 | 410× |
| MoE per layer, **compacted** (7,757 live experts / 38 layers × 48 tiles) | — | **9,798** | **490×** |
| `sdpa_full_self_attention_nax`, full (48 heads) | (8, 48, 1) | 384 | 19× |
| `sdpa_full_self_attention_nax`, sliding (64 heads) | (8, 64, 1) | 512 | 26× |
| `wq` fused GEMM | (48,8) / (64,8) | 384 / 512 | 19–26× |
| `wo` split-K | 1-D | 512 | 26× |

Cross-check: compacted `gate_up` 248,224 + `down` 124,112 = 372,336
threadgroups per forward ÷ 38 layers = 9,798, matching
`nonzero_experts` 7,757 ÷ 38 × 48 tiles. MoE alone is **466,944 dense
threadgroups per forward**.

**Both sides of the proposed overlap saturate the machine on their own.** The
smaller side (attention, 384–512 TGs) is already ~20–26× the core count and at
or above the ~480-TG residency ceiling (20 cores × ~24 resident TGs). The
larger side is 20× beyond that. There is no spare capacity for the mechanism to
exploit.

Chunking does not fix this — that is the crux. Splitting 512 tokens into 2×256
barely reduces the *expert* count per chunk (expected 7,165 live pairs per
256-token chunk versus 7,757 for the full 512, because expert routing is
near-saturated at these token counts), so each half-wavefront MoE dispatch is
still ≈ 6,000+ threadgroups per layer. Chunking halves the *rows*, not the
*grid*.

### M5 transfer

The ranked M5 Max has ~40 cores, double this host. That moves the co-residency
threshold from ~20 threadgroups to ~40. Prefill MoE is at 9,798. The conclusion
survives a **245× margin**, so (c) "M4 ≠ M5" cannot rescue it: the M5 would
need ~250× more spare capacity than doubling the core count provides. This is
the rare case where cross-machine extrapolation is safe, precisely because the
margin is enormous rather than marginal. The `_nax` caveat is also inert here —
`_nax` changes the inner MMA, not the grid dimensions that set occupancy.

---

## 6. Deliverable 6 — the mandatory wavefront tax, priced at 700.3 GB/s

Computed **before** any implementation, as required.

Per-expert weight bytes from the merged histogram's `dispatch_tiles`:

- `gate_up`: 32 column tiles × 18,432 B/tile = 589,824 B
- `down`: 16 column tiles × 73,728 B/tile = 1,179,648 B
- **total per (layer, expert) = 1,769,472 B ≈ 1.769 MB**

(Sanity: 38 × 256 × 1.769 MB = 17.2 GB of the ~21.6 GB text tower. Consistent.)

Live (layer, expert) pairs at 512 tokens: **7,757** (`nonzero_experts`).
Expected live pairs in a random 256-token half, modelling each expert's `r_e`
rows as randomly split: `Σ_e (1 − 2^{−r_e})` = **7,165.5**.

| quantity | value |
| --- | ---: |
| expert loads today (one 512 chunk) | 7,757 |
| expert loads with 2×256 chunks | 2 × 7,165.5 = **14,331** |
| **extra loads** | **6,574** (×1.85) |
| extra DRAM bytes | 6,574 × 1.769 MB = **11.63 GB** |
| **tax at 700.3 GB/s** | **+16.6 ms of `S`** |

Baseline prefill wall `S` = **97.89475 ms**
(`research/CURRENT_RESEARCH_STATE.md:64`), so the tax is **+17.0% of scored
prefill**, ≈ **−6% `ns`** at the recorded −0.3669 sensitivity.

This lands squarely inside the advisor's independently derived +13…+24 ms band
— useful corroboration that the two estimates agree.

**Where my result changes the arithmetic.** The advisor's net figure (−1 to
+11 ms) sets the tax against **25–35 ms of hideable bf16 attention**, which
implicitly prices the hiding coefficient at ~1.0. This experiment measures that
coefficient. At the *measured* prefill dispatch width of 9,792 threadgroups it
is **0.006** (same-family GEMM pair) to **0.012** (best-case complementary
bandwidth ∥ compute pair), not 1.0:

```
realized saving = 0.006…0.012 × 25…35 ms  =  0.15 … 0.42 ms
tax                                        = 16.6 ms
net                                        = −16.2 … −16.5 ms of S
```

Even if I generously substitute the largest coefficient measured anywhere above
the residency ceiling (0.082, at 240 threadgroups — 40× narrower than prefill
actually is) the saving is 2.0–2.9 ms against a 16.6 ms tax, still a net loss of
13.7–14.6 ms.

**The tax exceeds the headroom by roughly 6–110×.** Per the advisor's own
stopping rule ("if your estimate lands in the negative half of that range, that
is a NO-GO and a complete result — say so and stop"): **NO-GO. Stopping.** No
line of `Sources/MLXFastModel/LagunaRuntimeModel.swift` was written.

---

## 7. Verdict against the pre-registered decision table

| pre-registered branch | fired? |
| --- | --- |
| positive control shows `union == sum` → instrument blind, close | **partially** — positive control passed, but `concurrent_1cb` is blind, which is the case that matters |
| real case `< 0.05` at **all** sizes → graph overlap dead | not literally — `small` (16 TGs) reaches 0.50 |
| `≥ 0.15` at **any** size → GO | fires on 16-TG cells only |
| **mixed / size-dependent → report the boundary** | **THIS ONE** |

The honest outcome is the fourth branch, and the boundary is sharp:

> **Two independent kernels overlap on this stack when their *combined*
> threadgroup count is at or below the machine's concurrent-TG residency
> ceiling (~480 on a 20-core M4 Pro), and essentially not at all above it.
> Every prefill-512 kernel family is above that ceiling; the MoE gather-GEMM is
> 20× above it.**

Applying the boundary to the assignment's actual target: at the measured MoE
prefill dispatch width of 9,792 threadgroups, `overlap` is **0.0064
[−0.0089, 0.0179]** for a same-family GEMM pair and **0.0120 [0.0022, 0.0138]**
for the most complementary pair I could construct. Both are below the 0.05
"dead" threshold and an order of magnitude below the 0.15 GO threshold.
**Attack B (graph-level overlap) is closed for prefill.** Step 0 returns NO-GO,
so §3 was correctly not implemented.

---

## 8. Evidence

- **Host / memory profile / toolchain / thermal policy:** Apple M4 Pro,
  20 GPU cores, `applegpu_g16s`, 48 GiB (below the 64 GiB threshold, but the
  probe holds no model so the low-memory profile is irrelevant here), macOS
  26.5.2, Xcode toolchain `swiftc -O`. No `benchmark.sh` run and no thermal gate
  needed: the probe never loads the model and each cell is preceded by its own
  clock-pinning burn.
- **Exact commands:**
  ```bash
  xcrun swiftc -O research/tanjiro_coresidency_probe.swift -o /tmp/tjcores \
    -framework Metal -framework Foundation
  /tmp/tjcores 9 20
  ```
  Run 1 (`research/pr157-logs/coresidency-full-r9-t20ms.log`, 69.5 s) used the
  probe at commit `b19f984`; run 2
  (`research/pr157-logs/coresidency-extended-r9-t20ms.log`, 100.5 s) used the
  same command against commit `635939e`, which widens `mixSizes` to
  `[2,10,20,240,512,2048,9792]` and adds the `moe512` GEMM shape. Both were
  launched through `run_training` from a clean worktree.
- **Tests and risk-based checks:** no `swift test` selection was run.
  Justification: zero files under `editablePaths` were modified, so no scored,
  vendored, or runtime code path can have changed. `git diff --stat` against
  `BASE_SHA` touches only `research/`.
- **Correctness and serial-protocol verdict:** unchanged by construction — no
  runtime file modified. The serial non-speculative rule is untouched; note
  that the §3 design that this arm was gating (two-chunk wavefront prefill)
  would itself have been compliant, since both chunks are supplied tokens.
- **Divergent tokens:** none possible.
- **Peak RAM / generated-weight size:** n/a.
- **Official ranking status:** no submission dispatched.

| Metric | Baseline | Candidate | Ratio / delta |
| --- | ---: | ---: | ---: |
| decode seconds/token | — | — | not measured (no runtime change) |
| prefill seconds/token | — | — | not measured (no runtime change) |
| same-host paired estimate | — | — | n/a — research-only probe |

Raw logs: `research/pr157-logs/`.

---

## 9. Conclusion

- **What happened:** the campaign's `gpu_busy_sum == gpu_busy_union` evidence is
  an accounting artifact — proven with a positive control — but repairing the
  instrument does not revive the mechanism. Direct wall-clock measurement shows
  kernel overlap is governed by spare occupancy, and prefill-512 has none:
  every kernel family is 19–490× the core count.
- **Evidence for the mechanism:** overlap is real and near-ideal
  (`overlap_eff` ≈ 1.0) below the residency ceiling, and complementary
  resource mixes buy a genuine 2–3× over same-resource pairs. The physics is
  sound; the operating point is wrong.
- **Evidence against:** 0.0064 [−0.0089, 0.0179] for a same-family pair and
  0.0120 [0.0022, 0.0138] for the best complementary pair, both measured **at
  the real 9,792-threadgroup MoE prefill width**, versus a +16.6 ms chunking tax
  on a 97.89 ms prefill.
- **Uncertainty / M5 transfer risk:** low for this conclusion specifically, on
  a 245× margin. The residual risks are (i) the reproducible-but-unexplained
  tg=40 point, (ii) the cross-CB bandwidth pathology of §4b (now bounded to
  tg ≤ 20), (iii) the non-monotone multi-queue arm of §4c, and (iv) the fact
  that `_nax` kernels cannot execute on this gen-16 host — but `_nax` alters
  the inner MMA, not the grid, and grid size is what this result turns on.
- **Honest limitation:** this probe measures *steady-state* overlap of two long
  kernels. It does not measure tail-fill (using the ragged end of one dispatch
  to start the next). I did not measure that, but I can bound it: with 9,798
  threadgroups over 20 cores the MoE dispatch runs ~490 waves, so its
  quantization tail is ≤ 1/490 ≈ 0.2%; attention's is ≤ 1/20 ≈ 5% of a small
  term. Tail-fill upside for prefill is therefore O(0.5%) — real, but an order
  of magnitude below the chunking tax that would pay for it.
- **Smallest useful next action:** the one overlap idea this result does *not*
  kill is **shared-expert ∥ routed-expert**, because it needs **no chunking and
  therefore has zero weight-traffic tax**. The shared expert
  (`shared_expert_intermediate_size` 512) is a small dispatch that currently
  runs adjacent to the routed plane. If MLX is inserting a false barrier between
  them via allocator-recycled buffer addresses (`device.cpp:320-374` raises
  `BarrierScopeBuffers` on any RAW/WAR/WAW, and recycled allocations can look
  like hazards when they are not), removing that barrier is a pure win with no
  tax. That is a *barrier-elision* question, not a co-residency question, and
  this experiment does not answer it.
- **Second follow-up, lower confidence:** §4c's multi-queue arm reached 0.127
  overlap at true prefill width where MLX's intra-CB mechanism reached 0.012.
  I do not trust it (non-monotone, wide CIs) and it cannot pay for a chunking
  tax, but a dedicated probe of two-queue scheduling for genuinely
  complementary work would settle whether `MTLDispatchTypeConcurrent` is
  leaving something on the table. It would only ever be worth it for a
  zero-tax pairing, which loops back to the shared-expert idea above.
- **Recommendation: close.** Attack B is dead for prefill; the boundary above is
  the reusable asset. Two campaign-wide corrections should be propagated:
  (1) retire `gpu_busy_union` as a concurrency measure and stop citing
  `sum == union` as evidence that nothing overlaps — including the PR #73
  `SPLIT=1` reading, which is self-refuting; (2) any future "hide X behind Y"
  proposal must first show that X or Y leaves the machine under-occupied.
