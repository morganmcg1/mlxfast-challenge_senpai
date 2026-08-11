# R114-E — `laguna_gate_sp` latency excavation

Student `maple-alphonse`, PR #700, assignment `maple-r114-e-gate-sp-latency-excavation`
rev `r114-e-rev1`. Base `e400de7d095ffcfcde0462b174c7d22d737496fd`
(`codex/mlxfast-maple-20260804-advisor`). Host: Apple **M4 Pro, 20 GPU cores,
48 GiB**. All timings below are M4 directional evidence, not ranked M5 numbers.

---

## Step 0 — the ranked lever table, and a correction to the assignment

### 0.1 The atlas was already SPLIT-corrected. The assignment deflates it twice.

The assignment asks me to "SPLIT-correct" the R109-E bandwidth atlas by
subtracting `1.554 µs × calls/step`, and gives worked examples (lever B
`133.5 → 71.7`, lever C `373.4 → 326`).

**Those deflations are double-counting.** `research/maple-alphonse-r109e-bwatlas.py`
already removes the inflation *before* it multiplies up to per-step:

```python
SPLIT1_INFLATION_US = 1.554                                   # :34
us_call_c = secs * 1e6 / n - SPLIT1_INFLATION_US              # :91
us_step_c = us_call_c * n_step
```

and the table header states it: `8165.4 us/step corrected (SPLIT=1 inflation
1.554 us/call removed)`. The `_c` suffix on `us/step_c` and `us/call` is that
correction. Applying the assignment's arithmetic on top would deflate every
lever a second time.

Two further notes on the same table:

- The numbers quoted in the assignment (133.5, 373.4, 178.7) are from the
  **`headroom`** column, not `us/step_c`. `headroom = us/step_c − bytes-at-peak
  floor`. It is an *opportunity* estimate, not a time budget. The actual
  corrected costs are 134.2, 610.0 and 195.5 µs/step.
- The `GB/s` and `%peak` columns are computed from the **uncorrected** call
  time, so the reported bandwidths are lower bounds.

**Is the 1.554 µs constant fixed or size-dependent?** Fixed, and it is a
*per-command-buffer* constant, not a per-kernel one. It was fitted in
`research/maple-alphonse-r109e-qk-ceiling.md` §7.3.2 as a single global slope
from two captures that differ only in command-buffer granularity: `busy_sum`
+0.561 ms over +361 buffers/step ⇒ 1.554 µs/buffer. Under SPLIT=1 each kernel
gets its own command buffer, so it lands once per call regardless of the
kernel's size or byte count. It is an artefact of the instrument, and is
distinct from Rule 57's 1.2382 µs/dispatch *marginal wall* cost, which is a
property of the shipped un-split pipeline.

### 0.2 SPLIT-corrected ranked lever table, with calls/step

From `research/maple-alphonse-r109e-bwatlas.txt` (SPLIT=1 decode capture, this
M4 Pro, 8165.4 µs/step corrected total, peak 273.0 GB/s). Sorted by headroom.

| # | kernel | calls/step | µs/call_c | **µs/step_c** | share | MB/call | GB/s | %peak | headroom |
|---|---|---|---|---|---|---|---|---|---|
| C | `sliding_fused_attn_ring_v1` | 30.30 | 20.13 | 610.0 | 7.47 % | 2.131 | 105.9 | 38.8 % | 373.4 |
| **A1** | **`gate_sp_h64_v1`** | **30.30** | **6.45** | **195.5** | 2.39 % | 0.152 | 23.5 | 8.6 % | **178.7** |
| | `routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2` | 39.40 | 37.07 | 1460.7 | 17.89 % | 8.913 | 240.4 | 88.1 % | 174.3 |
| | `routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6` | 39.40 | 20.54 | 809.5 | 9.91 % | 4.474 | 217.8 | 79.8 % | 163.7 |
| B | `prefill_router_tournament_ordinal_norm_active64_v2` | 39.78 | 3.37 | 134.2 | 1.64 % | 0.004 | 1.3 | 0.5 % | 133.5 |
| | `full_fused_attn_grow_v1` | 10.01 | 23.37 | 233.9 | 2.86 % | 3.170 | 135.6 | 49.7 % | 117.7 |
| | `residual_rms_router_bf16_2048_rpg8_keys_v1_pf1` | 39.40 | 6.51 | 256.5 | 3.14 % | 1.072 | 164.6 | 60.3 % | 101.8 |
| | `rmsbfloat16` | 41.83 | 2.12 | 88.6 | 1.08 % | 0.053 | 24.8 | 9.1 % | 80.5 |
| | `shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1` | 39.40 | 5.84 | 230.0 | 2.82 % | 1.119 | 191.7 | 70.2 % | 68.5 |
| **A2** | **`gate_sp_h48_v1`** | **10.10** | **6.54** | **66.1** | 0.81 % | 0.115 | 17.5 | 6.4 % | **61.9** |
| | `dense_gate_up_swiglu_bf16_v1` | 1.01 | 268.70 | 271.4 | 3.32 % | 67.129 | 249.8 | 91.5 % | 23.0 |
| | `oproj_act_h48_v1_lm1_pw1_sc1_se1` | 10.10 | 28.85 | 291.4 | 3.57 % | 7.293 | 252.8 | 92.6 % | 21.6 |
| | `lmhead_int5_base_coarse_delta_bf16_v1` | 1.01 | 422.08 | 426.3 | 5.22 % | 109.789 | 260.1 | 95.3 % | 20.1 |
| | `dense_down_residual_bf16_v1` | 1.01 | 133.30 | 134.6 | 1.65 % | 33.579 | 251.9 | 92.3 % | 10.4 |
| | `oproj_act_h64_v1_lm1_pw1_sc1_se1` | 30.30 | 35.71 | 1082.0 | 13.25 % | 9.722 | 272.3 | 99.7 % | 2.9 |

**Lever A (`gate_sp`, both widths): 40.40 calls/step, 261.6 µs/step_c,
240.6 µs/step of headroom.** That matches the assignment's target figure and is
the object of the rest of this document.

### 0.3 `L-RANKED-REACHABILITY` verdict for `gate_sp`: **REACHABLE, and identical on M4 and M5**

`gate_sp` is a hand-written `MLXFast.metalKernel` JIT kernel that lives entirely
inside the editable surface:

| item | location |
|---|---|
| MSL source | `Sources/MLXFastModel/LagunaRuntimeModel.swift:4466-4506` (`lagunaGateSoftplusSource`) |
| kernel registry | `:4508-4520` (`laguna_gate_sp_h\(heads)_v1`) |
| dispatch helper | `:4522-4546` (`lagunaGateSoftplus`) |
| scored call site | `:5988-6010` |

The grep verdict the assignment asks for:

```
$ grep -c 'gate_sp' Vendor/**/*nax*     →  0   (all 20 _nax files)
$ grep -c 'qmv'     Vendor/**/*nax*     →  0
```

There is **no `_nax` twin and no `mlx-generated/*.cpp` twin** for this kernel:
it is JIT-compiled from the Swift string literal on both machines. The call site
is gated only on `lagunaFusedGatedAffineOProjEnabled`,
`lagunaGatedAffineOProjNVFP4Enabled`, `lagunaUseNativeAffineOProj(layer:)` and
the nvfp4/`bits==4`/`groupSize==16` shape checks — **no Apple-GPU-generation or
NAX capability gate anywhere on the path**. So unlike the `_nax` prefill kernels,
an M4 measurement of `gate_sp` exercises the same kernel text the ranked M5 will
run. Differences between the two hosts are core-count and clock, not kernel
selection.

---

## Stage 1 — where the 240.6 µs/step actually goes

### 1.1 Instrument

`research/maple-alphonse-r114-gatesp-probe.swift` is a standalone Metal probe
(no MLX link) that reproduces `lagunaGateSoftplusSource` byte-for-byte in its
`V0` form with the shipped dispatch geometry — `grid ((heads/8)*64,1,1)`,
`threadGroup (64,1,1)`, i.e. **8 threadgroups / 512 threads for h64 and 6 for
h48**. It rotates over 1024 distinct 131 KB weight banks (134 MB working set, so
every call misses to DRAM, as it does in the real decode step where ~500 MB of
other weights pass between two `gate_sp` calls), and reports the min over 10
command buffers of 200 back-to-back dispatches.

Two instrument notes that materially changed the answer:

- **DVFS is the dominant hazard for a probe this small.** An 8-threadgroup
  dispatch on a 20-core GPU cannot hold the clock up on its own. Unwarmed, the
  probe reported V0 at 16.1 µs/call with incoherent variant ordering (V1 slower
  than V0, h48 V3 at half of h48 V2). With a saturating heat kernel keeping the
  GPU resident (`warmGPU`), V0 settles at 4.670 µs/call and the variant ordering
  becomes monotone and reproducible to ±0.05 µs across independent runs.
- **The bare Metal stdlib has no `log1p`**; MLX's `metal_kernel` preamble
  supplies it. The probe adds a one-line shim so the softplus tail is textually
  identical.

### 1.2 The dose ruler (V0, K-loop truncated to n of 8 outer iterations)

| outer iters | h64 µs/call | h48 µs/call |
|---|---|---|
| 0 | 0.885 | 0.856 |
| 1 | 1.354 | 1.344 |
| 2 | 1.509 | 1.488 |
| 4 | 2.427 | 2.186 |
| 8 | 3.684 | 3.655 |

OLS: **h64 fixed = 0.924 µs, 0.349 µs/iter (2.795 µs of loop work);
h48 fixed = 0.877 µs, 0.343 µs/iter.** The intercept is the in-kernel fixed
cost — threadgroup launch/ramp, the tail `simd_sum` ×4, the softplus, the
store — and it is **25 % of the whole kernel**.

### 1.3 Variant A/B (full 8 iterations)

Bit-exactness of V1/V2/V3 against V0 is checked in-probe on the 40-bank arm and
holds for every variant (only the fetch width changes; arithmetic order is
untouched). `NOLD` replaces the weight code with a constant and is numerically
wrong by construction — it is a **load-cost ceiling**, not a candidate.

Cold arm (1024 banks / 134 MB — the faithful one):

| variant | h64 µs/call | h48 µs/call | Δ vs V0 (h64) | projected µs/step |
|---|---|---|---|---|
| V0 shipped | 4.670 | 4.493 | — | 186.9 |
| V1 `uint2` weight loads | 4.645 | 4.504 | −0.025 | 186.2 |
| V2 V1 + 16 B input loads | 4.577 | 4.416 | −0.093 | 183.3 |
| V3 V2 + paired scale/bias | 4.562 | 4.423 | −0.108 | 182.9 |
| `NOLD` (no weight loads) | 2.116 | 1.972 | −2.554 | 84.0 |

40-bank (5 MB, partly cache-resident) and 1-bank (fully hot) arms are in
`research/maple-alphonse-r114-gatesp-probe-out.txt`; the variant ordering is the
same, with V0 at 3.691 and 3.001 µs/call respectively.

### 1.4 The decomposition

Combining the ruler intercept, the `NOLD` ceiling, the cold V0 total, Rule 57's
M4 marginal dispatch cost (1.2382 [1.2237, 1.2518] µs/dispatch) and the atlas
in-situ figure:

| component | h64 µs/call | h48 µs/call | **µs/step** | share of 261.6 |
|---|---|---|---|---|
| in-kernel fixed (launch, `simd_sum` ×4, softplus, store) | 0.924 | 0.877 | **36.9** | 14.1 % |
| weight-code loading (131 KB / 98 KB from DRAM) | 2.554 | 2.521 | **102.9** | 39.3 % |
| rest of the K loop (input + scale/bias loads, FMA) | 1.192 | 1.095 | **47.2** | 18.0 % |
| *isolated kernel total (probe, cold)* | *4.670* | *4.493* | *186.9* | *71.5 %* |
| MLX per-dispatch glue (Rule 57) | 1.238 | 1.238 | **50.0** | 19.1 % |
| unattributed in-situ residual | 0.542 | 0.809 | **24.6** | 9.4 % |
| **in-situ, SPLIT-corrected (atlas)** | **6.45** | **6.54** | **261.6** | 100 % |

Subtracting the 21.0 µs/step bytes-at-peak floor gives the assignment's
240.6 µs/step, split into named components:

```
240.6 = 81.9  weight-code loading above the peak-rate floor
      + 50.0  MLX per-dispatch glue
      + 47.2  rest of the K loop
      + 36.9  in-kernel fixed cost
      + 24.6  unattributed in-situ residual
```

**Interval.** The probe's per-variant reproducibility is ±0.05 µs/call across
independent runs (V0 h64 3.691 / 3.691 on the 40-bank arm in two runs), i.e.
±2 µs/step per component. The Rule 57 term carries its published
[1.2237, 1.2518] interval, i.e. **50.0 [49.4, 50.6] µs/step**. The residual row
is a balancing term and absorbs the error of every other row.

### 1.5 Verdict: **in-kernel work, not dispatch overhead — and it is memory, not issue**

The assignment asks for an explicit verdict. It is:

- **In-kernel: 186.9 µs/step (71.5 %). Dispatch overhead: 74.6 µs/step (28.5 %)**
  (50.0 glue + 24.6 residual).
- Within the in-kernel part, **weight-code loading alone is 102.9 µs/step —
  39 % of the entire lever.**
- The requested "no-barrier" probe is **moot**: `lagunaGateSoftplusSource`
  contains **zero `threadgroup_barrier` calls and zero `threadgroup` memory**.
  Its only cross-lane operation is the four tail `simd_sum`s, which are part of
  the 0.92 µs fixed cost. There is no barrier to remove.

### 1.6 Why the 8.6 %-of-peak figure is not 91 % of headroom

The atlas prices headroom against 273.0 GB/s. **An 8-threadgroup dispatch cannot
reach that.** With 8 of 20 cores occupied the attainable share is ~109 GB/s, and
the measured weight-load rate is 131072 B / 2.554 µs = **51.3 GB/s, i.e. 47 % of
what 8 cores can actually pull.** The kernel is not leaving 91 % of the machine
on the table; it is leaving about half of an eighth-of-the-machine on the table,
and the reason is DRAM latency with only 512 threads in flight to hide it.

The two structural fixes for that are (a) more parallelism, i.e. more
threadgroups — **excluded**, `N-GATESP-TG-COUNT-IRRELEVANT` (tanjiro #683) and
explicitly rejected on sight by this assignment; and (b) fewer weight bytes,
which would mean sub-INT8 `g_proj` — **excluded by the accepted attention
quantization envelope** (`TASK.md`, group-32 affine INT8 only).

---

## Stage 2 — `N-GATESP-LOADWIDTH-IRRELEVANT`

**The primary hypothesis of this assignment is refuted.**

The hypothesis was that `gate_sp` is issue-bound on narrow scalar fetches: each
thread executes 384 memory instructions per call, 256 of which are single-byte
`uint8_t` loads, and replacing them with 32 aligned 8-byte `uint2` loads (base
`packed_codes + orow*K + lane*8` is always 8-byte aligned; the input offset
`16*lane + 2k` is always 16-byte aligned) would cut memory instructions 3.7× at
bit-exactness.

The transformation works and is bit-exact. **It buys 2.3 %.**

| | h64 | h48 | total |
|---|---|---|---|
| V3 saving per call | 0.108 µs | 0.070 µs | |
| calls/step | 30.30 | 10.10 | |
| **saving per step** | **3.27 µs** | **0.71 µs** | **3.98 µs/step** |

Against the campaign bar of a verified **+0.25 % ≈ 36 µs/step**, this is **9×
too small**. It is also below the M4 paired-ABBA resolution: the block-lead
spike alone is +53.59 µs/step with se 29.9, so a 4 µs/step effect cannot be
given an interval excluding zero on this rig at any feasible run count. Running
the ABBA would produce a number, not evidence.

**Why it failed, mechanically.** The eight `wl[i]` loads in an iteration are
eight *consecutive bytes* — one 64-byte cache line serves all of them, and
several rows' worth besides. The hardware already coalesces them into a single
memory transaction, so the wide load removes instruction slots that were never
the constraint. The cost is the transaction and its DRAM latency, not the
instructions that request it. `NOLD` confirms this from the other side: deleting
the weight loads entirely saves 2.554 µs/call, 24× what vectorising them saves.

This closes the load-width family — V1, V2 and V3 — as a lever. I did not ship
it. Per the assignment's "never ship on *no worse*" rule, a bit-exact 3.98 µs/step
that cannot be measured is not a result.

---

## Stage 3 — the one component that is large enough

Stage 1 leaves exactly one item in the decomposition that clears the 36 µs/step
bar and is not excluded by a prior negative or by the quantization envelope:

**per-dispatch cost. 50.0 µs/step of Rule 57 glue + 36.9 µs/step of in-kernel
fixed cost + 24.6 µs/step of residual = 111.5 µs/step (0.78 % of M4 decode)
is spent on the fact that `gate_sp` is 40 separate dispatches per step rather
than zero.**

`gate_sp` is unusually well suited to removing that: `dep_scope = NONE`
(`research/CURRENT_RESEARCH_STATE.md:8335-8400`) — it reads only `normalized
[1,1,2048]` and its own weight bank, exactly like the QKV projection, and
nothing between them consumes its output. Folding it into a neighbouring
dispatch as extra threadgroups adds **no new intra-encoder dependency edge**
(and so does not incur the assignment's +2.55 µs/layer edge penalty); it only
grows a grid.

The existing `foldGateIntoBank` hook (`LagunaRuntimeModel.swift:5711`) refuses
this because it wants one *concatenated* weight bank, and `g_proj` is affine-8 /
group-32 while our Q path is nvfp4 / 4-bit / group-16. A grid-append fusion does
not need a shared bank — it needs one kernel with two weight-format branches
selected by threadgroup index.

That is the arm I take to the 07:30Z milestone. Documented landmine to respect:
the `fusedTailGateLogits` path at `:5946` (consumed at `:5975`) does **not** set
`gateProjectionActivated = true`, which silently double-applies or drops the
softplus.
