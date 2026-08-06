# P-CENSUS — closing the prefill budget

**PR #91 · maple-tanjiro · assignment `maple-2026-08-06h-prefill-budget-census` r1**
**Base:** `codex/mlxfast-maple-20260804-advisor` @ `6a19fd74bf64e6bde9d2a3c5d7f7970588803cab`

**Submitted diff: empty.** Every file in this experiment lives under `research/`.
Neither `Vendor/mlx-swift/.../metal/device.cpp` nor `device.h` — the two files the
profiling instrument touches — appears in `benchmark.json`'s `editablePaths`, and
both are reverted at the final head SHA. Submitted-byte growth is `0`.

**W&B: not in use for this campaign.** This is a static/profiling census with no
training or evaluation process, so no W&B run was created and `runs` is empty.

**No ranked submission was dispatched. The official channel is HELD.**

Column labels used throughout, per §0.9.33:

- **A** — *algorithmic*: derived from source constants and observed tensor
  shapes. Host-independent. Transfers to the M5 unchanged.
- **M** — *machine-determined*: measured on this M4 Pro. Carries this host's
  noise and this host's kernel selection. Does **not** transfer to the M5
  without an argued bridge.

---

## §0 Executive summary

### §0.1 The headline

A complete per-dispatch census of the frozen 512-token prefill forward:

- **1222 GPU dispatches** in **81 command buffers** per forward (M). Neither
  number has been published anywhere in this campaign before; both are new.
- Under shipped batching the GPU is **strictly serial**: busy-sum equals busy-union
  equals **540.455 ms**, 99.1 % of the 545.2 ms wall (M). There is no dispatch
  gap and no dispatch overlap to reclaim.
- Every dispatch is attributed to one of **12 kernel families**, and the family
  ledger closes against its own total to **0.022 %** (M).
- The derived byte budget (**A**) totals **26.676 GB** and **2830.2 GFLOP** for
  the forward, and cross-checks against measured bound bytes (**M**) to
  **+4.9 %** on the mapped subtotal.
- Against the M5 frontier forward **S ≈ 97.95 ms**, the per-family
  `max(DRAM floor, MMA floor)` sum accounts for **65.9–75.1 ms**, leaving an
  explicit **UNATTRIBUTED residual of 22.9–37.9 ms** — **23–39 % of S**, worth
  **8.5–14.1 % of score**. Central estimate at the campaign's own *measured*
  routed-plane bandwidth: **27.9 ms**.

The three-line result:

```
prefill = 1222 dispatches in 81 command buffers, strictly serial, 540.455 ms busy on M4.
Derived floors account for 65.9-75.1 ms of the M5's 97.95 ms forward.
UNATTRIBUTED = 22.9-37.9 ms (23-39 % of S; 8.5-14.1 % of score); central 27.9 ms.
```

### §0.2 Hard-stop verdict

**Mechanism C (fused split-K port) is REFUTED on the ranked M5.** Its entire
prize is the fp32 `C_split` round trip of the BF16 split-K GEMMs. On M4 that is
754.5 MB and worth 1.24–1.51 ms. On M5, source predicates put **87 % of that
prize (wk and wv, 654 MB) on a different branch that never creates the
intermediate**, collapsing M5 value to ≈0.16–0.21 ms = **+0.06–0.08 % of score,
below the campaign MDE of 0.278 %**. Do not spend a slot on C. Full derivation
in §7.

### §0.3 Reconciliation table

| quantity | value | label | source |
| --- | --- | --- | --- |
| dispatches / forward | 1222 | M | §2 |
| command buffers / forward (shipped) | 81 | M | §2 |
| busy sum = busy union (SPLIT=0) | 540.455 ms | M | §2 |
| wall / forward | 545.242 ms | M | §2 |
| serial fraction | 99.1 % | M | §2 |
| per-command-buffer overhead | 5.88 µs | M | §3.1 |
| family ledger closure | 0.022 % | M | §2.3 |
| deflated ledger vs SPLIT=0 union | +0.86 % | M | §3.2 |
| derived forward bytes | 26.676 GB | A | §5 |
| derived forward FLOPs | 2830.2 GFLOP | A | §5 |
| A-vs-M mapped byte agreement | +4.9 % | A/M | §5.2 |
| M5 accounted floor | 65.9–75.1 ms | A | §6 |
| **M5 UNATTRIBUTED** | **22.9–37.9 ms** | **A** | **§6** |

---

## §0.9 Four falsified premises in the assignment brief

I was instructed to re-derive every banked number and to say so when source
disagrees with the brief (§0.9.11). Four premises did not survive.

### §0.9.A `31.28 ms` does not exist in its cited source

The brief cites `research/maple-fern-prefill-roofline.md` for a `31.28 ms`
unattributed prefill residual.

```
$ grep -n "31.28" research/maple-fern-prefill-roofline.md
(no match)
```

Line `:96` of that file is `| whole forward | 2830.2 | 585.6 | 4.83 | 16.8% |`.
The nearest real quantities in the document are `steel_gemm_splitk_nt + _accum =
33.04 ms` (`:30`) and the `31.3 %` MMA padding ratio (`:248`, `:262`). Neither is
an unattributed residual.

I then tried to reconstruct the figure. **It is reproducible, but only under a
divisor/discount pair the brief does not state:** applying a 500 GB/s divisor
*and* the 20.26 % zero-row discount gives **31.37 ms**, 0.29 % away from 31.28.
At the divisor the brief itself mandates (610 GB/s) the same construction gives
**37.89 ms** discounted or **32.03 ms** undiscounted. The number is therefore
mis-sourced and silently divisor-dependent. **I report my own residual and do
not round it up to 31.28.**

### §0.9.B `prefill_probe.py --profile` could not parse any committed hook

The brief assumes the existing tooling can produce a per-dispatch byte census.
It cannot, and never could.

`research/prefill_probe.py:42-58` splits each `GPUPROF` line with
`line.split(" ", 5)`, skips any line with fewer than 6 fields, and reads
`nops, nbytes = int(parts[3]), int(parts[4])`. Every GPUPROF hook ever committed
to this repository (`a8a269d`, `64509eb`, `b6458d9`, `9470004`, `a7d2c0b`,
`ce74f15`) emits **five** fields via `"GPUPROF {:.9f} {:.9f} {} "`. So
`--profile` has silently printed "no GPUPROF records" for every user who tried
it. fern's byte-emitting hook variant was described but never committed.

**Fixed in this experiment.** §1.2 documents the 6-field hook.

### §0.9.C The brief's conversion factors are decode-derived and cannot be applied to prefill

The brief mandates M4→M5 conversion factors of ×0.3886 (attention), ×0.4324
(routed MLP), ×0.7565 (remainder). Applying them to my measured M4 families
gives **≥211 ms**, against the M5's actual `S ≈ 97.95 ms` — a **2.4× overshoot**.

Those factors are decode-derived. The M4→M5 prefill wall ratio is
`97.95 / 545.0 = 0.180` (or `97.95 / 585.6 = 0.167` against the harness cold
forward), not decode's 0.5019. The root cause is already on the record: **94.3 %
of M4 prefill time runs NAX-divergent kernels the M5 never executes**
(independently reconfirmed here, §2.4).

**Step 3 is therefore answered from derived bytes and FLOPs against M5 ceilings
(A), not by rescaling M4 wall time (M).** This is a stronger method, not a
weaker one: it never passes through a host-specific kernel selection.

### §0.9.D `610 GB/s` is out of scope by the campaign's own record

The brief mandates a 610 GB/s divisor for the DRAM floor.
`research/CURRENT_RESEARCH_STATE.md:600` says the opposite, in bold:

> **610 GB/s | DEFINITIONAL.** It is `1794 MB / 2.941 ms` by construction. It is
> not a physical capability and must never be quoted as one. | *the decode
> roofline ledger only*

The correct prefill divisors on the same record are the **measured routed-plane
546.2 ± 23.3 GB/s** (`:602`) and `research/prefill_ridge.py:25`'s M5 achievable
band `DRAM_LO/MID/HI = 485/500/530 GB/s`.

I therefore report the DRAM floor as a **band over 485 / 500 / 530 / 546.2 /
610 GB/s** and label 610 as the optimistic definitional end. Note the direction
of the bias: **610 GB/s produces the largest UNATTRIBUTED residual**, so obeying
the brief's divisor would have inflated my own headline. I report the band and
quote the measured 546.2 GB/s as central.

---

## §1 The instrument

### §1.1 Host

| property | value |
| --- | --- |
| chip | Apple **M4 Pro** |
| CPU cores | 14 |
| GPU cores | **20** |
| unified memory | 51,539,607,552 B = **48 GiB** |
| macOS | **26.5.2**, Metal 4 |
| GPU arch string | `applegpu_g16s`, **gen 16**, `nax_gen_required=17`, `nax_available=false` |
| startup profile | `DARKBLOOM_STARTUP_MEMORY_PROFILE=full` on every run |
| peak RAM | ≈20.715 GB every run |

Below 64 GiB, so the low-memory startup profile would apply by default; every
probe run in this census forced the `full` profile so allocator behaviour is
constant across all five sessions.

**No `_nax` kernel is reachable on this host.** This is the single most important
fact about every M-labelled number below.

### §1.2 The hook, and its bias

I cherry-picked `a8a269d` ("LOCAL-ONLY: re-apply MLX dispatch profiler for the
PR73 decode kernel census"; reverted upstream by `8c8b7e6`) with `-n`, then
extended `CommandEncoder::record()` to emit a sixth field so
`prefill_probe.py --profile` could finally parse it (§0.9.B).

The first attempt reused the existing `buffer_sizes_` counter. That is wrong, and
finding out why produced a side result worth reporting on its own:

> `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/array.h:346` states verbatim: *"Note,
> `data_size` is in units of `item_size` (not bytes)."* `buffer_sizes_`
> accumulates `a.data_size()`, so it is an **element** counter, not a byte
> counter. `needs_commit()` (`device.cpp:558-563`) compares `buffer_sizes_ >> 20`
> against `max_mb`. **`MLX_MAX_MB_PER_BUFFER` is therefore a mebi-*element* cap,
> not a megabyte cap** — for BF16 it is off by exactly 2×, for NVFP4 packed
> words by more. The campaign has been sweeping a mis-scaled knob.

The final hook adds an independent `size_t profile_nbytes_{0}` on
`CommandEncoder` (`device.h` ~`:147-149`), accumulates `a.nbytes()` in
`set_input_array` beside the existing `buffer_sizes_ += a.data_size()`
(`device.cpp` ~`:396-399`), captures it in the `commit()` completion lambda
(~`:582`), resets it in `commit()` (~`:624`), and formats
`"GPUPROF {:.9f} {:.9f} {} {} "`. Line format:

```
GPUPROF <start_s> <end_s> <n_ops> <n_input_bytes> <name|name|...>
```

**Declared bias of the byte column (M).** `input_bytes` is a *binding* measure,
not a DRAM-traffic measure. Specifically it:

1. **excludes outputs** entirely;
2. **de-duplicates** an array bound more than once in the same command buffer;
3. **charges each bound array in full** whether or not the kernel reads all of
   it.

Bias 3 is visible and large: `laguna_lmhead_exact_winner_...` binds the full
392 MB weight, runs for 5.0 µs, and so reports an impossible **81,531 GB/s**.
Biases 1 and 3 push in opposite directions, which is exactly why the A-vs-M
agreements in §5.2 are *consistency* checks and not calibration.

The hook is saved verbatim as `research/pr91-gpuprof-hook.patch` (198 lines).

### §1.3 Instrument admissibility

The decisive check: **dispatch count is identical (1222) with and without the
instrument, and identical between SPLIT=0 and SPLIT=1.** The hook observes the
work; it does not change it. Command-buffer count does change (81 → 1066 under
SPLIT=1), and §3.1 measures exactly what that costs.

`DARKBLOOM_GPU_PROFILE_SPLIT=k>0` **overrides** `MLX_MAX_MB_PER_BUFFER` and
`MLX_MAX_OPS_PER_BUFFER` entirely (`device.cpp:558-563`). Any cap-related
measurement must therefore use SPLIT=0.

### §1.4 Local-only source state

The two touched files are **not** in `editablePaths`. Proof, and the reason the
budget preflight shows zero growth:

```
$ senpai/check-editable-budget.sh 6a19fd74bf64e6bde9d2a3c5d7f7970588803cab
editable budget OK: current=2930084/3000000 bytes headroom=69916 growth=0/262144
  files=142 (file count is diagnostic only; base=142)
```

The brief predicted `growth=-42973`. Actual growth is **0**, because the files
the instrument touches are outside the submitted surface. That zero *is* the
zero-submitted-byte proof.

`senpai/validate-assignment-scope.sh` **cannot be invoked for this experiment**:
its usage is `validate-assignment-scope.sh BASE_SHA SUBMITTED_PATH [...]` and
requires at least one path argument. With zero submitted paths there is nothing
to pass. The substitute proof is the `git diff --name-only` in §11.

### §1.5 Runs

| id | arm | reps | warm median | purpose |
| --- | --- | --- | --- | --- |
| `step0-baseline-A.log` | unhooked | 16 | 545.704 ms | resolution floor |
| `step0-baseline-B.log` | unhooked | 16 | 545.401 ms | resolution floor |
| `step0-baseline-C.log` | unhooked | 16 | 545.280 ms | resolution floor |
| `step1-split0.log` | hooked, shipped batching | 6 | 544.969 ms | serial ground truth |
| `step1-split1.log` | hooked, one dispatch per cb | 6 | 550.757 ms | per-dispatch attribution |

Rep 0 is discarded in every session (`prefill_probe.py:272`); in session A it was
544.04 ms against a 544.96–546.51 ms warm range. All five sessions load in
41–44 s. One model-holding process at a time throughout.

### §1.6 Resolution floor

- **Cross-session median spread: 0.424 ms = 0.078 %** (545.280 → 545.704).
- **Within-session peak-to-peak: 0.284 %** (544.96–546.51, 15 warm reps).

Per §0.9.32 I quote these as this host's resolution rather than ever writing "no
difference". Any M4 prefill effect below **0.284 %** is *below this host's
resolution*, and any effect below **0.078 %** is below its cross-session
resolution.

### §1.7 Screenability

**Prefill is not M4-screenable, and this census re-proves it.** §2.4 measures
94.3 % of M4 prefill GPU time in NAX-divergent kernels. Every M-labelled timing
below describes code the ranked M5 does not run. This is why §6 is built from
A-labelled bytes and FLOPs.

---

## §2 The SPLIT=1 per-dispatch census

### §2.1 Why SPLIT=1 is necessary

Under shipped batching (SPLIT=0) MLX packs many dispatches into one command
buffer, and the completion handler timestamps the *buffer*, not the dispatch.
The result is useless for attribution: `MIXED:` rows aggregate **1156 of 1222
dispatches** carrying **98.2 % of wall**.

Running the same census script on the SPLIT=0 trace makes the failure explicit
(`research/pr91-logs/step2-census-split0.log`): totals stay exact (sum = union =
**540.699 ms**) while family attribution is wrong by up to **7.6×** —
`routed_gather_gemm` reads 34.921 ms instead of 266.605, `elementwise` reads
107.988 instead of 4.747. **Totals are trustworthy at SPLIT=0; families are not.**

### §2.2 Both arms, side by side (M)

| quantity | SPLIT=0 (shipped) | SPLIT=1 (isolated) |
| --- | --- | --- |
| command buffers / forward | **81** | **1066** |
| dispatches / forward | **1222** | **1222** |
| warm median | 544.969 ms | 550.757 ms |
| wall | 545.242 ms | 551.315 ms |
| busy **sum** | 540.455 ms (99.1 %) | 671.677 ms (121.8 %) |
| busy **union** | 540.455 ms (99.1 %) | 548.059 ms (99.4 %) |
| bound bytes | 24.717 GiB = 26.540 GB | 28.834 GiB = 30.961 GB |

Two structural results fall straight out:

1. **At SPLIT=0, sum ≡ union to the last digit.** The GPU executes prefill
   strictly serially with zero dispatch concurrency. There is no overlap to
   exploit and no gap to close.
2. **At SPLIT=1, sum exceeds union by 123.6 ms.** That excess is almost entirely
   `arangeuint32`, which is fully overlapped and non-additive. The
   serial-equivalent basis is therefore `sum − arange`.

Command-buffer closure: 910 single-dispatch cbs + 156 two-dispatch cbs = 1066 ✓,
and 910 + 312 = 1222 ✓.

### §2.3 The family ledger (M)

Segmentation by idle gap **fails** on this trace — the largest inter-forward gap
(19.430 ms) is smaller than several intra-forward gaps, proven by
`research/pr91_gaps.py`. `research/pr91_census.py` instead cuts the trailing
**6 blocks of exactly 1222 dispatches** from the end and verifies each yields
1066 command buffers. The trace holds 13,072 records / 15,180 dispatches; the
8 `lm_head` markers are 6 timed forwards + 2 load/warm-up.

Medians over the 5 kept forwards: sum **648.007 ms**, union **547.993 ms**,
arange **95.762 ms**, serial-equivalent **552.245 ms** (0.78 % from union),
bound **30.961 GB**.

| family | n/fwd (M) | ms/fwd (M) | % serial | GB/fwd (M) |
| --- | ---: | ---: | ---: | ---: |
| routed_gather_gemm | 76 | 266.605 | 48.28 % | 18.968 |
| steel_gemm_bf16 | 392 | 219.295 | 39.71 % | 4.552 |
| sort_scatter | 154 | 98.394 | 17.82 % | 1.135 |
| attention_core | 40 | 28.209 | 5.11 % | 0.696 |
| nvfp4_dense_qmm | 116 | 20.135 | 3.65 % | 0.652 |
| elementwise | 235 | 4.747 | 0.86 % | 1.633 |
| qk_norm_rope | 41 | 4.323 | 0.78 % | 0.768 |
| moe_tail | 38 | 2.537 | 0.46 % | 0.878 |
| rms_norm | 82 | 1.687 | 0.31 % | 0.496 |
| router | 40 | 0.959 | 0.17 % | 0.012 |
| lm_head | 5 | 0.668 | 0.12 % | 0.959 |
| other | 3 | 0.309 | 0.06 % | 0.211 |
| **TOTAL** | **1222** | **647.868** | | **30.961** |

**Explicit column check.** Dispatch column: 1222 = 1222 ✓ exact. Time column:
647.868 vs the independently-taken median total 648.007 → **0.022 %**. The two
need not be identical because each family median is taken independently of the
total median; 0.022 % is the size of that effect. Percentages exceed 100 % in
sum because they are shares of the *serial-equivalent* basis, not of the union.

### §2.4 NAX divergence, reconfirmed independently (M)

| kernel | ms |
| --- | ---: |
| `nvfp4_gather_qmm_rhs_nt` | 266.643 |
| `steel_gemm_fused_nt_bfloat16_..._bm64_bn64_bk16_wm2_wn2` | 183.561 |
| `MIXED: steel_gemm_splitk_accum_ + steel_gemm_splitk_nt_` | 35.690 |
| `steel_attention_bfloat16_bq32_bk16_bd128_wm4_wn1` | 28.212 |
| `nvfp4_qmm_t` | 6.606 |
| **NAX-divergent subtotal** | **520.712 = 94.3 %** |

This replicates fern's independent measurement (517.92 ms / 94.2 %) closely.
Per-kernel agreement is strong: gather_qmm 266.643 vs 266.65; steel_gemm_fused
183.561 vs 183.37; steel_attention 28.212 vs 28.23; nvfp4_qmm_t 6.606 vs 6.64;
splitk_fused 13.479 vs 13.56. The one discrepancy is the split-K pair, 35.690 vs
33.04 (**+8.0 %**) — fern reported two separate rows where my trace has them
fused into a single `MIXED:` command buffer, so the comparison is not
like-for-like. `arangeuint32` differs widely (95.8–119.5 vs 134.03) because it is
pure latency inside a fully-overlapped region and is not on the critical path in
either measurement.

---

## §3 Self-consistency

### §3.1 Per-command-buffer overhead (M)

SPLIT=1 adds 985 command buffers. Three independent estimators of the tax:

| estimator | Δ | µs / cb |
| --- | ---: | ---: |
| warm-median delta (**headline**) | 5.788 ms | **5.88** |
| wall delta | 6.073 ms | 6.17 |
| union delta | 7.294 ms | 7.41 |

Headline **5.88 µs/cb**, range 5.9–7.4. The decode analogue measured in PR #73
is 1.681 µs/cb; prefill command buffers are ~3.5× more expensive to set up,
consistent with their much larger binding sets.

### §3.2 Deflating the ledger against the SPLIT=0 ground truth

`research/pr91_deflate.py` removes `n_family × 5.88 µs` from every family and
drops the fully-overlapped `arangeuint32` (76 calls, 95.762 ms), then compares
the total with the SPLIT=0 union — the same work, measured without the
instrument's batching distortion.

| family | n | raw ms | deflated ms | tax ms |
| --- | ---: | ---: | ---: | ---: |
| routed_gather_gemm | 76 | 266.605 | 266.158 | 0.447 |
| steel_gemm_bf16 | 392 | 219.295 | 216.990 | 2.305 |
| sort_scatter (− arange) | 78 | 2.632 | 2.173 | 0.459 |
| attention_core | 40 | 28.209 | 27.974 | 0.235 |
| nvfp4_dense_qmm | 116 | 20.135 | 19.453 | 0.682 |
| elementwise | 235 | 4.747 | 3.365 | 1.382 |
| qk_norm_rope | 41 | 4.323 | 4.082 | 0.241 |
| moe_tail | 38 | 2.537 | 2.314 | 0.223 |
| rms_norm | 82 | 1.687 | 1.205 | 0.482 |
| router | 40 | 0.959 | 0.724 | 0.235 |
| lm_head | 5 | 0.668 | 0.639 | 0.029 |
| other | 3 | 0.309 | 0.291 | 0.018 |
| **TOTAL** | | | **545.368** | |

**Self-consistency result: deflated 545.368 ms vs SPLIT=0 union 540.699 ms →
+4.669 ms = +0.86 % over-attribution.** The sign is stable across all three
overhead estimators (+0.86 % / +0.80 % / +0.54 %).

Interpretation: even after removing the per-cb tax, an isolated dispatch is
slightly slower than the same dispatch inside a shipped command buffer — cache
and state reuse across dispatches in one buffer is real but small. **Every
family figure in §2.3 is an upper bound with ≈0.86 % of headroom.**

---

## §4 Structural reconciliation: dispatches to source (A)

Every one of the 1222 dispatches reconciles to a source construct. This is an
A-column result: it depends only on the model geometry and the runtime's
branching, not on this host.

Geometry (`Sources/MLXFastModel/LagunaConfig.swift`, matching `weights/config.json`
exactly): 40 layers; layer type is `$0 % 4 == 0 ? .full : .sliding` (`:492`,
`:498`, `:826`) → **10 full** layers (0, 4, …, 36) at 48 q-heads and **30
sliding** at 64 q-heads; layer 0 is dense, layers 1–39 are MoE; 256 experts,
top-8; hidden 2048; head dim 128; 8 KV heads; sliding window **512**.

**Layer 39 is special.** `LagunaRuntimeModelInner.callAsFunction:10836-10838`
routes the last layer to `callLastPrefillRow` when `h.dim(1) > 1` and the mask is
`.causal`. That layer then runs at M = 1 (GEMV), and the lm_head slices to the
last row first (`:10928`). This single branch explains every "off by one" count:

| family | count | reconciliation |
| --- | ---: | --- |
| attention_core | 40 | 39 `steel_attention` (layers 0–38) + **1 `sdpa_vector`** (layer 39 at M=1) |
| qk_norm_rope | 41 | 29 sliding (30 − layer 39) + 10 full + `rope` + `rope_single` |
| routed_gather_gemm | 76 | 38 MoE layers (1–38) × 2 (fused gate/up, down) |
| moe_tail | 38 | layers 1–38 |
| nvfp4_dense_qmm | 116 | 76 shared gate+up (38×2) + 38 shared down + 1 routed qmv + 1 shared qmv (layer 39) |
| router | 40 | 38 prefill tournament (1–38) + 1 fused residual-rms-router + 1 decode router (layer 39) |
| sort_scatter | 154 | 76 `arangeuint32` + 38 `gather_front` + 38 `csort_scatter_fused` + 2 |
| steel_gemm_bf16 | 392 | 82 `steel_gemm_fused_nt` + **155 split-K × 2 dispatches** = 82 + 310 |

The 82 fused and 155 split-K BF16 GEMMs decompose exactly:

- **82 fused** = 39 `wq` + 39 `wo` + 1 layer-39 `[K;V]` bank + 3 layer-0 dense.
- **155 split-K** = 39 `wk` + 39 `wv` + 39 `g_proj` + 38 router.

### §4.1 The sliding window buys nothing at the frozen prefill point (A)

This is a new structural finding and it is host-independent.

`createAttentionMask` returns a materialised array mask only when
`windowSize != nil && n > windowSize` (`Vendor/mlx-swift-lm/.../KVCache.swift:169`),
and the rotating-cache override returns one only when
`cappedOffset + n > actualWindowSize` (`:807`). At the frozen prefill point
`n = 512`, `offset = 0`, `windowSize = 512`:

```
512 >  512   -> false
0 + 512 > 512 -> false
```

Both paths return **`.causal`**. So at exactly 512 tokens the *sliding* mask is
byte-identical in meaning to the *full* mask: **all 30 sliding layers attend over
all 512 positions.** Sliding attention costs more than full attention here, not
less, purely because it has more heads (64 vs 48).

Consequences:

1. AGENTS.md's suggestion that "sliding-window layers need only the latest 512
   positions" is a **decode** lever. At the frozen 512-token prefill it is
   structurally void — there is nothing to skip.
2. The benchmark sits **exactly one token below a cliff.** At 513 tokens both
   predicates flip and MLX materialises a 513×513 boolean mask plus the
   `linds < rinds + windowSize` elementwise pass, for all 30 sliding layers.
   Any change that alters effective sequence length by even one token at prefill
   crosses that cliff.
3. It is also what makes layer 39's `if case .causal = mask` gate fire for *both*
   attention families — confirmed independently by the measured dispatch counts
   in the table above. Source and measurement agree.

### §4.2 The 76 `arangeuint32` dispatches are synthesised identity indices (A)

There is no `arange` anywhere in `Sources/MLXFastModel/`. The dispatches come
from MLX itself. `indices_or_default` (`Vendor/mlx-swift/.../ops.cpp:67-81`):

```cpp
array indices_or_default(std::optional<array> indices, const array& x, StreamOrDevice s) {
  if (indices.has_value()) return indices.value();
  Shape shape(x.shape().begin(), x.shape().end() - 2);
  int total = ...;                       // prod of leading dims
  return reshape(arange(total, uint32, s), std::move(shape), s);
}
```

The MoE path calls `gather_qmm` supplying `rhs_indices` (which expert) but
**leaving `lhs_indices` unset**, so MLX synthesises a pure `arange` — an identity
map — one per `gather_qmm` call. 38 MoE layers × 2 calls = **76** ✓. And at
`ops.cpp:5430-5431` the flags are `sorted_indices && !rhs_indices_` (false) and
`sorted_indices && !lhs_indices_` (**true**), so the kernel is additionally told
the LHS indices are sorted.

This is the origin of mechanism A, and it prices A's *stated* framing at zero;
see §8.

---

## §5 The derived budget (A)

### §5.1 Bytes and FLOPs

`research/prefill_budget.py --tokens 512` derives the forward from
`LagunaConstants` plus observed shapes. It hardcodes nothing except the two
representation constants `BF16 = 2.0` and `NVFP4 = 0.5625` B/param (`:22-24`).
My run reproduces fern's table exactly.

| stage | weight GB | act GB | GFLOP | FLOP/B |
| --- | ---: | ---: | ---: | ---: |
| attn_proj_qkvo | 2.862 | 0.881 | 1465.3 | 391.5 |
| routed_experts | 17.666 | 1.799 | 1005.0 | 51.6 |
| attn_core | 0.000 | 0.713 | 161.4 | 226.3 |
| shared_expert | 0.069 | 0.225 | 125.6 | 427.4 |
| dense_mlp_layer0 | 0.101 | 0.029 | 51.5 | 396.4 |
| router | 0.041 | 0.092 | 20.9 | 157.5 |
| lm_head | 0.411 | 0.000 | 0.4 | 1.0 |
| norm_rope | 0.000 | 0.965 | 0.0 | 0.0 |
| moe_tail | 0.000 | 0.818 | 0.0 | 0.0 |
| embedding | 0.002 | 0.002 | 0.0 | 0.0 |
| **TOTAL** | **21.152** | **5.524** | **2830.2** | **106.1** |

**Attention weights are BF16 at prefill, and this is load-bearing.** The
group-32 affine INT8 attention layout is enabled by default
(`LagunaRuntimeModel.swift:300-306`) but is **decode-only**: every consumer gates
on `L == 1` (`:5678-5680`, `:6113-6115`), and the runtime's own comment at
`:294-298` says "Prefill stays on the original BF16 projections." Prefill reads
q/k/v/o **and** `g_proj` as plain BF16 through `Linear` (`:5634-5641`). So
2 B/param is correct for the 2.862 GB attention weight column, and
`LagunaConfig.swift:39-41` is right for prefill. Any prefill budget that applied
1.125 B/param here would understate attention traffic by 44 %.

### §5.2 A versus M: byte cross-check

`research/pr91_byte_crosscheck.py` maps derived stages onto measured families.

| derived stage(s) | A GB | M GB | M/A |
| --- | ---: | ---: | ---: |
| routed_experts | 19.465 | 18.968 | **0.974** |
| attn_proj_qkvo + router + dense_mlp_layer0 | 4.006 | 4.552 | 1.136 |
| attn_core | 0.713 | 0.696 | **0.976** |
| shared_expert | 0.294 | 0.652 | 2.218 |
| lm_head | 0.411 | 0.959 | 2.333 |
| norm_rope | 0.965 | 1.264 | 1.310 |
| moe_tail | 0.818 | 0.878 | 1.073 |
| **mapped subtotal** | **26.672** | **27.969** | **1.049** |
| unmapped (sort_scatter, elementwise, other) | 0.004 | 2.979 | — |
| **TOTAL** | **26.676** | **30.948** | **1.160** |

The two large-mass stages — routed experts (73 % of derived bytes) and attention
core — agree to within **2.6 %**. The outliers are all explained by the declared
bias 3 of §1.2: the three lm_head pruner stages each *bind* the full ~392 MB
weight while *reading* a slice, and shared_expert's `nvfp4_qmm_t_splitk_fused`
re-binds its operands. Since bias 1 (missing outputs) pushes the other way,
these agreements are consistency evidence, **not** a calibration of the derived
budget against a measured ground truth.

---

## §6 Closing the budget on the M5

### §6.1 Method

Per §0.9.C, the M4 wall cannot be rescaled. Instead, for each stage:

```
dram_ms = bytes / divisor            mma_ms = flops / 60e12
floor   = max(dram_ms, mma_ms)       # kernels alternate; they do not overlap
```

Ceilings: **MMA 60 TFLOP/s** (`research/prefill_ridge.py:26`); DRAM band **485 /
500 / 530 / 546.2 / 610 GB/s** (§0.9.D). `max` rather than sum because
`PREFILL_NAX_ANALYSIS.md` establishes that these kernels alternate between
memory and compute phases rather than overlapping them.

The **zero-row discount** is the routing fact that 20.26 % of experts receive
zero rows in a 512-token prefill (`research/prefill-512-route-histogram.txt`,
host-independent). Reported both ways because the shipped kernel does not
currently skip empty experts — undiscounted is what the code does, discounted is
what a routing-aware kernel could reach.

### §6.2 Per-family floors, undiscounted (A)

| stage | binding | ms @485 | @546.2 | @610 |
| --- | --- | ---: | ---: | ---: |
| attn_proj_qkvo | **compute** | 24.42 | 24.42 | 24.42 |
| routed_experts | **memory** | 40.13 | 35.64 | 31.91 |
| attn_core | compute | 2.69 | 2.69 | 2.69 |
| shared_expert | compute | 2.09 | 2.09 | 2.09 |
| dense_mlp_layer0 | compute | 0.86 | 0.86 | 0.86 |
| router | compute | 0.35 | 0.35 | 0.35 |
| lm_head | memory | 0.85 | 0.75 | 0.67 |
| norm_rope | memory | 1.99 | 1.77 | 1.58 |
| moe_tail | memory | 1.69 | 1.50 | 1.34 |
| embedding | — | 0.01 | 0.01 | 0.01 |
| **Σ floor** | | **75.08** | **70.07** | **65.92** |

Only **routed_experts** is memory-bound; every other compute-bearing stage is
MMA-bound at the M5's 60 TFLOP/s. This inverts the M4 picture, where the whole
forward is bandwidth-bound (machine balance 110.5 FLOP/B vs intensity 106.1).

### §6.3 The UNATTRIBUTED row

`S = 97.95 ms` (M5 frontier). `1 ms of S = 0.371 % of score`.

| divisor GB/s | Σ floor ms | **UNATTRIBUTED ms** | % of S | % of score |
| --- | ---: | ---: | ---: | ---: |
| *undiscounted* | | | | |
| 485.0 | 75.08 | 22.87 | 23.4 % | 8.49 % |
| 500.0 | 73.74 | 24.21 | 24.7 % | 8.98 % |
| 530.0 | 71.29 | 26.66 | 27.2 % | 9.89 % |
| **546.2 (measured)** | **70.07** | **27.88** | **28.5 %** | **10.34 %** |
| 610.0 (definitional) | 65.92 | 32.03 | 32.7 % | 11.88 % |
| *zero-row discounted 20.26 %* | | | | |
| 485.0 | 67.70 | 30.25 | 30.9 % | 11.22 % |
| 500.0 | 66.58 | 31.37 | 32.0 % | 11.64 % |
| 530.0 | 64.53 | 33.42 | 34.1 % | 12.40 % |
| 546.2 | 63.52 | 34.43 | 35.2 % | 12.77 % |
| 610.0 | 60.06 | 37.89 | 38.7 % | 14.06 % |

**Headline: UNATTRIBUTED = 22.9–37.9 ms, 23–39 % of S, 8.5–14.1 % of score.
Central estimate 27.88 ms at the measured 546.2 GB/s, undiscounted.**

The row is monotone in the divisor: a more optimistic bandwidth assumption
*enlarges* the residual. The brief's mandated 610 GB/s sits at the pessimistic
end of accounting and the optimistic end of opportunity.

### §6.4 What the residual is and is not

The UNATTRIBUTED row is **an upper bound on recoverable time, not recoverable
time.** It is everything the derived floors do not explain: launch overhead,
tile quantisation, staging serialisation, occupancy loss, MMA row padding,
un-modelled intermediates, and any error in the derived budget itself.

Two known named contributors, from the record and from this census:

- **MMA row padding.** The shipped routed GEMM issues 1.46 rows per useful row
  at SM=16 (31.3 % waste). Against routed_experts' 35.64 ms floor that is
  ≈11 ms of the residual on its own — roughly 40 % of the central estimate.
- **Staging serialisation.** `PREFILL_NAX_ANALYSIS.md` H1 measures expert-weight
  staging at 39.5 % of prefill with `Ws_storage` at 9.2 KB and no double
  buffering.

So the residual is not mysterious; it is dominated by two already-identified
mechanisms. That is a *positive* result for the campaign: the largest single
block of unexplained prefill time has named, testable causes.

---

## §7 Mechanism C, pre-priced

**Mechanism C** = port the fused split-K path to the BF16 `steel_gemm_splitk_*`
family, eliminating the fp32 `C_split` intermediate and halving the dispatch
count of those GEMMs.

### §7.1 Call sites (A)

From §4, the 155 BF16 split-K GEMMs are:

| call site | n | M | N | K |
| --- | ---: | ---: | ---: | ---: |
| `wk` | 39 | 512 | 1024 | 2048 |
| `wv` | 39 | 512 | 1024 | 2048 |
| `g_proj` | 39 | 512 | 48 or 64 | 2048 |
| router | 38 | 512 | 256 | 2048 |

Each runs the **minimum 2 partitions**
(`Vendor/mlx-swift/.../metal/matmul.cpp:560-566`:
`split_k_partitions = min(max(2, next_power_of_2(_tk/(_tm*_tn))), 32)`), with
`C_split({split_k_partitions, M, N}, float32)` at `:567-569`. So **310 dispatches
do the work of 155**, and each writes then re-reads an fp32 intermediate.

fp32 `C_split` traffic = `2 × split_k × M × N × 4` bytes:

| site | per call | × n | total |
| --- | ---: | ---: | ---: |
| `wk` | 8.389 MB | 39 | 327.2 MB |
| `wv` | 8.389 MB | 39 | 327.2 MB |
| `g_proj` | ≈0.524 MB | 39 | ≈20.4 MB |
| router | 2.097 MB | 38 | 79.7 MB |
| **total** | | | **≈754.5 MB** |

This **confirms `PREFILL_NAX_ANALYSIS.md` H3's 0.72 GB to within 4.8 % but
refutes its attribution.** H3 blamed `o_proj`. Both source and measurement say
`o_proj` takes the *fused, non-split-K* path (it is one of the 82
`steel_gemm_fused_nt` calls, §4). The real sites are `wk`, `wv`, `g_proj`, and
the router.

### §7.2 Price, and the M5 blindness (A)

Priced at M5 divisors, 0.7545 GB → 1.509 ms @500, 1.381 @546.2, 1.237 @610:
**band 1.24–1.51 ms = +0.46–0.56 % of score**. That re-derivation confirms and
slightly *widens upward* the banked 1.18–1.32 ms / +0.44–0.49 %, and puts C at
1.7–2.0× the campaign MDE of 0.278 %.

**But that is the M4 price.** The M5 selects a different branch. From
`matmul.cpp:953-991`:

```
use_nax = is_nax_available() && !complex && (enable_tf32() || dtype != float32)
Case 1 (non-NAX SIMD split-K, :965-966):
  !use_nax && batch_size_out == 1 && (_tm*_tn) <= min_tmn_threshold && _tk >= 8 && K >= max(M,N)
Case 2 (NAX split-K, :988-990):
  use_nax && batch_size_out == 1 && (K >= 3*max(M,N) || (max(M,N) <= 1024 && K > 2*max(M,N)))
Case 3 (:1025): if (use_nax) return steel_matmul_regular_axpby_nax<...>
```

Inputs are BF16, so `dtype != float32` and `use_nax` is **true** on the M5.
Evaluating Case 2 per site:

| site | K ≥ 3·max(M,N)? | max(M,N) ≤ 1024 ∧ K > 2·max(M,N)? | M5 split-K? |
| --- | --- | --- | --- |
| `wk` | 2048 ≥ 3072 ✗ | 1024 ≤ 1024 ✓ but 2048 > 2048 ✗ | **NO** → Case 3 regular NAX GEMM |
| `wv` | ✗ | ✗ (same boundary) | **NO** → Case 3 |
| `g_proj` | 2048 ≥ 1536 ✓ | — | YES |
| router | 2048 ≥ 1536 ✓ | — | YES |

**`wk` and `wv` — 654 MB, 87 % of the entire prize — fail Case 2 by an exact tie
(`K > 2·max(M,N)` with `2048 > 2048` false) and route to
`steel_matmul_regular_axpby_nax`, which never creates the intermediate C would
remove.** Only `g_proj` and router (77 of 155 sites, ≈100 MB) stay on split-K.

**M5 value of mechanism C ≈ 0.16–0.21 ms = +0.06–0.08 % of score — well below
the 0.278 % MDE. Mechanism C does not deserve a slot.**

(For completeness: on the M5 the *surviving* split-K sites still allocate fp32.
The NAX partition math at `matmul.cpp:709-736` gives `sks = 1024` for
`K = 2048`, hence 2 partitions and a `C_split({2, M, N}, float32)` at `:736`.
The NAX branch does not avoid the intermediate; it is simply not selected for
`wk`/`wv`.)

### §7.3 Two unknowns that could move this verdict

1. **`devc` is inferred, not observed.** `char devc = d.get_architecture().back()`
   (`:955`) sets `min_tmn_threshold = 2048` for `'s'`/`'d'` and `1024`
   otherwise. `wk`/`wv` sit **exactly on** `_tm*_tn == 2048`. If the ranked M5's
   architecture string ends in another character, even the M4-side
   classification changes. **Print `d.get_architecture()` on the ranked host.**
2. The tie at `K > 2*max(M,N)` is exact. Any future change to `wk`/`wv` output
   width (1024) or depth (2048) flips 87 % of the prize back on.

Both are cheap to resolve and both are prerequisites for reopening C.

---

## §8 Mechanism ranking

Campaign MDE on renormalised `ns` at 95 %: **0.278 %**. `1 ms of S = 0.371 % of
score`, so the MDE corresponds to **0.75 ms of S**.

| mechanism | banked | re-derived | verdict |
| --- | --- | --- | --- |
| **A** — kernel-side gather elision via `lhs_indices` | 2.15 ms | see below | **REFUTED as framed / OPEN as re-framed** |
| **B** — row-concat QKV (`DARKBLOOM_FUSED_QKV`) | 0.17 ms | ≤0.17 ms | **REFUTED** (sub-MDE) |
| **C** — fused split-K port | 1.18–1.32 ms | 1.24–1.51 M4 / **0.16–0.21 M5** | **REFUTED on M5** |
| **D** — LPT expert-launch permutation | 0.3–1.5 ms | not re-derived here | **OPEN** |
| C1 — double-buffered expert staging | 2–6 % | not re-derived | **OPEN, highest value** |
| C2 — routed GEMM BN 64→32 | 1.5–4 % | not re-derived | **OPEN, cheapest first receipt** |
| C3 — prefill row-concat QKV | 1–3 % | = B | **REFUTED** |
| C5 — glue reduction | 1–2 % | ≤ residual | **SUSPECT** |

### §8.A Gather elision — REFUTED as framed

§4.2 shows the 76 `arangeuint32` dispatches are MLX-synthesised identity indices.
Two independent measurements agree they are worth **zero wall time**: they are
fully overlapped and non-additive (my §2.2: sum exceeds union by 123.6 ms,
almost entirely arange), and fern independently killed "caching the arange
dispatches" for the same reason. Their byte cost is 0.016 MB × 76 = **1.2 MB**,
which at any divisor is under 3 µs.

**So the "eliminate 76 arange dispatches" framing is worth 0 ms and is REFUTED.**
Any real value in A must come from the kernel-side indirection *inside*
`nvfp4_gather_qmm_rhs_nt` — recognising the identity map and dropping the
per-row address indirection. That would be ≈0.8 % of a 266.6 ms kernel to reach
the banked 2.15 ms. **A byte/FLOP census cannot price a pure ALU/latency change**,
so A is re-framed as OPEN-but-unpriceable-by-this-method. It is also M5-blind
(the kernel is NAX-divergent).

### §8.B Row-concat QKV — REFUTED

The banked framing was "flip `DARKBLOOM_FUSED_QKV` off". **Source says it is
already off.** `LagunaRuntimeModel.swift:108-114` tests `== "1"`, so the L>1
row-concat QKV bank at `:5850-5866` never runs and prefill uses the stock
`wq`/`wk`/`wv` at `:5875-5877`. B is therefore a *flip-on* experiment, not a
flip-off one. At a banked 0.17 ms = 0.06 % of score it is **4.4× below MDE** in
either direction. REFUTED.

### §8.C / §8.D

C is settled in §7. D (LPT expert-launch permutation) is the only banked
mechanism this census neither refutes nor prices; its 0.3–1.5 ms band straddles
the 0.75 ms MDE-equivalent, so it needs its own arm.

### §8.E What this census says to spend slots on

The residual's two named contributors (§6.4) are **MMA row padding ≈11 ms** and
**staging serialisation**. Those map onto C2 (BN 64→32, bit-exact, cheapest) and
C1 (double buffering, largest). Both are worth multiples of the MDE and both
dwarf A, B, C, and D. The census's recommendation is to stop spending slots on
the sub-MDE mechanism list and put them on C2 first (bit-exact, safest receipt),
then C1 — **never bundled**, per `PREFILL_NAX_ANALYSIS.md`.

---

## §9 Prior-claim reconciliation

| queue item | prior claim | census verdict |
| --- | --- | --- |
| unattributed prefill = `31.28 ms` | brief | ~~as stated~~ **Re-derived: 22.9–37.9 ms band; 27.88 ms central. The cited figure is absent from its source and only reproducible at an unstated 500 GB/s + 20.26 % discount pair (31.37 ms). CLOSED.** |
| H3: fp32 split-K round trip ≈0.72 GB on `o_proj` + router + `g_proj` | `PREFILL_NAX_ANALYSIS.md` | ~~o_proj~~ **Re-derived: 0.7545 GB (+4.8 %, magnitude CONFIRMED) but the sites are `wk`, `wv`, `g_proj`, router. `o_proj` takes the fused non-split-K path. Attribution CORRECTED.** |
| mechanism C worth +0.44–0.49 % of score | `RESEARCH_IDEAS_2026-08-06_02:40` | ~~+0.44–0.49 %~~ **Repriced: +0.46–0.56 % on M4, +0.06–0.08 % on M5. REFUTED on the ranked host.** |
| mechanism A worth 2.15 ms | banked | ~~2.15 ms~~ **Bounded: the arange-elimination component is 0 ms (fully overlapped, 1.2 MB). REFUTED as framed.** |
| mechanism B = flip `DARKBLOOM_FUSED_QKV` off | banked | ~~flip off~~ **Corrected: the flag is default OFF; B is a flip-*on* experiment. Sub-MDE either way. REFUTED.** |
| 94.2 % of M4 prefill is NAX-divergent | fern | **CONFIRMED independently at 94.3 %.** |
| prefill busy union ≈99.4 % of wall | fern | **CONFIRMED at 99.4 % (SPLIT=1) and 99.1 % (SPLIT=0), and strengthened: sum ≡ union at SPLIT=0.** |
| `MLX_MAX_MB_PER_BUFFER` is a megabyte cap | implicit campaign-wide | ~~megabytes~~ **CORRECTED: it is a mebi-*element* cap (`array.h:346`). The knob has been mis-scaled in every sweep.** |
| sliding-window layers need only 512 positions | AGENTS.md optimisation ideas | **Void at prefill: at n = windowSize = 512 the mask is `.causal`, so all 30 sliding layers attend over all 512 positions. Decode-only lever.** |
| 610 GB/s as prefill divisor | brief | ~~610~~ **Out of scope per `CURRENT_RESEARCH_STATE.md:600`. Reported as a band with 546.2 GB/s central.** |
| `prefill_probe.py --profile` works | brief | **REFUTED: no committed hook has ever emitted the 6 fields its parser requires. Fixed here.** |

---

## §10 Limitations

1. **Every M-labelled timing is M4 Pro, gen 16, `nax_available=false`.** 94.3 %
   of it runs kernels the ranked M5 does not execute. No M-labelled figure here
   is a claim about M5 timing.
2. **The measured byte column is a *binding* measure, not DRAM traffic.** It
   excludes outputs, de-duplicates within a command buffer, and charges bound
   arrays in full. Declared in §1.2 with a worked example.
3. **The SPLIT=1 ledger over-attributes by ≈0.86 %** even after deflation
   (§3.2). All family figures are upper bounds.
4. **`max(dram, mma)` assumes memory and compute phases alternate rather than
   overlap.** This follows `PREFILL_NAX_ANALYSIS.md` but is an assumption. If
   the M5 overlaps them, the floors are too high and UNATTRIBUTED is larger.
5. **The MMA ceiling of 60 TFLOP/s is inherited, not measured by me.** It comes
   from `prefill_ridge.py:26`. I have no M5 access to verify it.
6. **`devc` in the split-K selector is inferred**, not observed on the ranked
   host (§7.3). It gates a boundary that `wk`/`wv` sit exactly on.
7. **The A-vs-M byte agreement is consistency, not calibration.** Two declared
   biases push in opposite directions, so a 2.6 % agreement on the large stages
   does not prove either column correct to 2.6 %.
8. **The zero-row discount is reported but not applied to the headline.** The
   shipped kernel does not skip empty experts, so the undiscounted row is what
   the code does today.

---

## §11 Hygiene

**Correctness.** All 60 forwards across all 5 sessions and both arms emitted the
same greedy token:

```
$ grep -ho 'token=[0-9]*' research/pr91-logs/step0-baseline-*.log \
                          research/pr91-logs/step1-split*.log | sort | uniq -c
  60 token=5991
```

The fixture `correctness_prompts/public_longcopy_gate_english_512_256.json`
(case `longcopy-gate-english-512`) has `expected_tokens[:3] = [5991, 509, 902]`.
The first checked greedy token matches the public golden in every forward.
`max_abs_diff = 0` **by construction** at the final head SHA, because the
submitted surface there is byte-identical to `6a19fd74`.

**Injection greps.** Before any work, and again at the final head SHA:

```
$ grep -rn 'DARKBLOOM_GPU_PROFILE' Vendor/ Sources/ Tests/ tools/
(no output)
$ grep -rn 'GPUPROF' Vendor/ Sources/
(no output)
```

**Submitted surface.** `git diff --name-only 6a19fd74bf64e6bde9d2a3c5d7f7970588803cab HEAD`
lists only `research/` paths. Byte budget: `growth=0/262144` (§1.4).

**Instrument lifecycle.** `git log --oneline` shows the hook applied and reverted
in separate commits, so the instrument's existence and its removal are both
auditable:

```
d0f51e9 Revert "LOCAL-ONLY: apply byte-emitting MLX dispatch profiler for the PR91 prefill census"
b27f360 LOCAL-ONLY: retain PR91 prefill dispatch-census evidence
a37e6b3 LOCAL-ONLY: apply byte-emitting MLX dispatch profiler for the PR91 prefill census
9c331e1 senpai assignment: maple-2026-08-06h-prefill-budget-census
6a19fd7 advisor: round-15 delta — census-transfer law and prefill axis reopening
```

`a37e6b3` added 116 lines across `device.cpp` and `device.h` only; `d0f51e9`
removed exactly those 116 lines. Neither file is in `editablePaths`, so the
submitted surface never changed even while the hook was live — which is why
`growth=0` rather than the brief's expected `growth=-42973` (§1.4).

**Campaign metadata.** No official submission was dispatched. The ranked channel
is **HELD**. `--model senpai` was not exercised; explicit API rejection: **none**
(no call made).

---

## §12 Suggested follow-ups

Not implemented here; listed so the advisor can price them.

1. **Print `d.get_architecture()` on the ranked M5.** One line of output resolves
   limitation 6, the `wk`/`wv` split-K boundary, and part of mechanism C's
   verdict. Cheapest high-value observation available.
2. **Re-scale every `MLX_MAX_MB_PER_BUFFER` sweep by the element/byte factor.**
   The knob is a mebi-element cap (§1.2). Prior sweeps explored a different
   range than they recorded, and the optimum may be outside the swept window.
3. **Commit the 6-field GPUPROF hook as a maintained research tool.**
   `prefill_probe.py --profile` has been silently dead for the whole campaign
   (§0.9.B); a maintained patch under `research/` prevents the next agent from
   rediscovering this.
4. **Take C2 (routed GEMM BN 64→32) as the next prefill receipt.** It is
   bit-exact, it targets the largest named contributor to the UNATTRIBUTED row
   (MMA row padding, ≈11 ms), and it needs no new instrument.
5. **Audit the 513-token cliff (§4.1).** The frozen window sits exactly one token
   below a mask materialisation boundary for all 30 sliding layers. Any
   mechanism that changes effective prefill length by one token pays a large,
   currently unmeasured cost.
6. **Re-derive the campaign's other decode-derived conversion factors.** §0.9.C
   shows the prefill set is wrong by 2.4×; the same construction may be in use
   elsewhere.

---

## SENPAI-RESULT

```yaml
status: succeeded
hypothesis: >
  The frozen 512-token prefill forward can be fully enumerated per dispatch and
  closed against derived byte and FLOP floors on the ranked M5, yielding an
  explicit UNATTRIBUTED residual and a falsifiable pre-price for mechanism C.
primary_metric:
  name: prefill_ms_attributed
  direction: maximize
  baseline: 66.67
  candidate: 70.07
  delta: 3.40
runs: []
summary: >
  1222 dispatches in 81 command buffers per prefill forward; strictly serial on
  M4 (busy sum == union == 540.455 ms, 99.1 % of wall). Twelve-family ledger
  closes to 0.022 % and survives per-cb deflation at +0.86 %. Derived budget
  26.676 GB / 2830.2 GFLOP. Against the M5 frontier S = 97.95 ms the per-family
  max(DRAM, MMA) floors account for 65.9-75.1 ms, leaving UNATTRIBUTED =
  22.9-37.9 ms (23-39 % of S; 8.5-14.1 % of score), central 27.88 ms at the
  campaign's measured 546.2 GB/s. Mechanism C REFUTED on M5: 87 % of its prize
  (wk/wv, 654 MB) fails the NAX split-K predicate by an exact tie and never
  creates the fp32 intermediate, collapsing M5 value to +0.06-0.08 % of score,
  below the 0.278 % MDE. Four brief premises falsified: the cited 31.28 ms is
  absent from its source; prefill_probe.py --profile could never parse any
  committed hook; the mandated M4->M5 conversion factors are decode-derived and
  overshoot by 2.4x; and 610 GB/s is definitional-decode-only by the campaign's
  own record. Zero submitted bytes; no ranked submission dispatched.
```

**Metric definition.** `prefill_ms_attributed = S - UNATTRIBUTED`, in
M5-equivalent ms of the 97.95 ms forward. The baseline is the brief's asserted
prior residual (`97.95 - 31.28 = 66.67`), retained as the stated starting point
even though §0.9.A shows it is mis-sourced. The candidate is this census's
central re-derivation (`97.95 - 27.88 = 70.07`) at the campaign's measured
546.2 GB/s, undiscounted. Across the full divisor/discount grid the candidate
ranges **60.06–75.08 ms**. Direction is `maximize` because a larger attributed
figure means less unexplained time.
