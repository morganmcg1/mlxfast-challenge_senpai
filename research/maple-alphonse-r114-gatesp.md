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

### 3.1 The implemented arm: grid-append fusion

Shipped as `lagunaDecodeNVFP4QKVGate` in `Sources/MLXFastModel/LagunaRuntimeModel.swift`.

The scored decode QKV projection is `laguna_decode_nvfp4_qkv_h{64,48}_r1_v1_lm1_pw1_se1_sd1`
(the lane-major branch of `lagunaDecodeNVFP4QKVR1`), dispatched as

| | h64 | h48 |
|---|---|---|
| `rows = (heads + 2·8)·128` | 10240 | 8192 |
| QKV threadgroups (`rows/2`) | 5120 | 4096 |
| `gate_sp` threadgroups (`heads/8`) | 8 | 6 |
| grid growth | **+0.156 %** | **+0.146 %** |
| weight bytes/call | 10.49 MB | 8.39 MB |
| gate bytes/call | 0.152 MB | 0.115 MB |
| byte growth | **+1.45 %** | **+1.37 %** |

Both use `threadGroup (64,1,1)`, so the two grids are directly concatenable.
The fused kernel is one JIT source with a threadgroup-uniform branch:

```metal
constexpr uint laguna_gate_tiles = heads/8;
if (threadgroup_position_in_grid.x < laguna_gate_tiles) {  // gate_sp body
    ...; return;
}
uint tile = threadgroup_position_in_grid.x - laguna_gate_tiles;  // QKV body
```

Four properties make this the right shape:

1. **No new dependency edge.** QKV and `g_proj` are siblings, not producer and
   consumer, so this is a *grid* merge and not an encoder serialisation. The
   assignment's +2.55 µs/layer edge penalty does not apply.
2. **Gate tiles lead, not trail.** Appending them at the end would schedule
   them into the QKV drain tail, where the machine is emptying and their whole
   duration lands on the critical path. Leading, they are issued in the first
   wave and are hidden by 5120 following threadgroups.
3. **Bit-exact by construction.** Both bodies are the shipped sources verbatim
   (the two generators grew buffer-name / tile-offset parameters whose defaults
   reproduce the old text byte-for-byte). No cross-threadgroup interaction
   exists in either body, so scheduling order cannot change a value.
4. **No register-pressure regression.** QKV holds `x_thread[16]` floats plus
   `sb[4]`; the gate branch holds `x[8]` plus `r[4]`. The gate branch cannot
   raise the kernel's max live-register allocation, so QKV occupancy is
   unchanged.

Arm selector for the paired test is `DARKBLOOM_DECODE_QKV_GATE_FUSED`, read
once per worker process, so both ABBA arms come from a **single build** and the
only difference is dispatch shape. `=0` reproduces the two-dispatch base path.

Guards mirror the union of `lagunaDecodeNVFP4QKVR1`'s lane-major branch and
`lagunaGateSoftplus`; any failure falls back to the two separate dispatches.
The call site takes the fused path only when
`_nativeAffineQKVGateRows != nHeads` (i.e. the gate rows are *not* already
inside the QKV bank) and the activated-o-proj preconditions hold, which is
exactly the configuration in which `gate_sp` is dispatched today. The fused
gate output is pre-activated, so it sets `gateProjectionActivated = true` —
the landmine noted above.

### 3.2 Correctness gates on the fused build

Both gates were run at commit `a7a780de` with the fused path **default on**.

**`./benchmark.sh --local-iterate`** (job `c80c4f8e`, 2026-08-11T01:23:32Z):

```
passed_correctness : true      max_abs_diff : 0      passed : true
golden_hash b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63
```

The Metal JIT compiles and the fused kernel produces the checked 130-token
greedy stream exactly. No `MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT` override was used
or needed.

**`research/run_upstream_equivalence.sh`** (job `df421a01`):

| step | maxAbsLogitErr | meanAbsLogitErr | runtime tok | upstream tok |
|---|---|---|---|---|
| prefill | 0.125 | 0.011933609 | 5991 | 5991 |
| decode-0 … decode-7 | **0** | **0** | 509/902/5991/… | identical |

`EQUIVALENCE_EXACT_STEPS=8`, `EQUIVALENCE_EXIT=1`.

The non-zero exit is the **pre-existing M4 artifact**, not a regression. The
`0.125 / 0.011933609 / token 5991 == 5991` triple is the same value recorded
for the *unmodified base* on this host in `research/fern-r104b-wkwv-tile-regroup.md:374`,
`research/frieren-r98-decode-qmv-result.md:162` and
`research/RESEARCH_ARCHIVE_through-round-91.md:4102`; the wrapper compares
against a `0.0` tolerance and so exits 1 on the base too. The signal that
belongs to this change is the decode column, and **all eight decode steps are
exactly zero** — the fused kernel is bit-identical to the two-dispatch path on
the scored decode axis.

### 3.3 Independent review of the fusion

A read-only reviewer checked the diff against seven specific failure modes and
returned SAFE-TO-MEASURE. The load-bearing confirmations, with the evidence it
cited:

- MLX binds custom-kernel inputs **positionally**, in `input_names` order
  (`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/common/metal_kernel.cpp:94-112`);
  names matter only for presence in the source and for `*_shape/_strides/_ndim`
  synthesis (`:214-220`). The fused argument order is the QKV five followed by
  the gate three, matching both call sites.
- The synthesised `[[...]]` attributes are emitted once per *unique* name from a
  fixed table (`metal_kernel.cpp:222-250`), so `threadgroup_position_in_grid`,
  `simdgroup_index_in_threadgroup` and `thread_index_in_simdgroup` are declared
  once even though two bodies use them.
- Every buffer exceeds `max_constant_array_size = 8` (`metal_kernel.cpp:19`),
  so all of them stay in the `device` address space in the fused kernel exactly
  as in the two originals — the `(const device uint8_t*)` casts remain legal.
- The branch is threadgroup-uniform, so the `simd_sum` in each body is fully
  converged.
- The fused guard set is the exact intersection of the two old paths; it adds
  only `heads % 8 == 0`, which the old gate path assumed implicitly.
- `??` is `@autoclosure`, so the unfused QKV dispatch is not evaluated when the
  fused result is non-nil; there is no double dispatch on either axis.
- MLX invalidates a cached JIT library when the source behind a name changes
  (`custom_kernel.cpp:56-68`), and the fused kernel name is distinct anyway, so
  there is no stale-library hazard between the two ABBA arms.

It raised one *performance* risk that my §3.1 claim 4 had dismissed too
quickly: register allocation for a fused kernel is the union over both branches
as the compiler sees it, not the max of the two branches' live sets as I
reasoned. If that pushes the QKV path over an occupancy cliff and spills
`x_thread[16]`, the fusion loses more than the 111.5 µs it can win. This is the
main way the arm can come back **correct but slower**, and it is exactly what
the paired ABBA measures.

### 3.4 The paired ABBA: **−76.8 µs/step, 95 % CI [−102.2, −51.4]**

**Instrument.** `research/maple-alphonse-r114-gatesp-fusion-abba.sh`, 36 runs of
`./benchmark.sh --local-iterate` in order `CFFC` × 9, SPLIT=0 (uninstrumented),
`MLXFAST_LOCAL_FAN_PROMPT=0`, M4 Pro / 20 GPU cores / 48 GiB. **Both arms come
from one build**; the selector is `DARKBLOOM_DECODE_QKV_GATE_FUSED`, read once
per worker process, so no rebuild can confound the comparison. All 36 runs
report `passed_correctness: true`. Raw data
`/tmp/r114-gatesp-fusion.tsv` (12) and `/tmp/r114-gatesp-fusion-2.tsv` (24);
statistics `research/maple-alphonse-r114-gatesp-abba-stats.py`.

Palindromic `CFFC` blocking is the answer to the **+53.59 µs/step block-lead
spike (se 29.9)** the brief warns about: control never occupies slot 1 alone,
and a linear drift cancels inside each block.

| arm | n | mean decode s/token | run-to-run sd |
|---|---:|---|---:|
| C — shipped two-dispatch path | 18 | 0.0129820197 | 46.5 µs (0.36 %) |
| F — fused grid-append | 18 | 0.0129052344 | 43.2 µs (0.34 %) |

**Point estimate F − C = −76.8 µs/step = −0.591 %.** Three estimators, and
because the design is balanced they share that point estimate exactly and
differ only in the variance model:

| estimator | n / df | sd | se | 95 % CI (µs/step) | sign |
|---|---:|---:|---:|---|---|
| block (per `CFFC` quadruple) | 9 | 33.1 | 11.0 | **[−102.2, −51.4]** | 9/9 negative |
| adjacent (disjoint C/F pairs) | 18 | 43.2 | 10.2 | **[−98.3, −55.3]** | 17/18 negative |
| unpaired Welch (pairing discarded) | 33 | — | 15.0 | **[−106.1, −47.5]** | — |

**All three exclude zero and all three clear the 36 µs/step bar.** The
unpaired interval is the conservative one — it throws away the blocking
entirely — and it still clears. I report the **block** interval as the headline
because it is the estimator whose assumptions the design was built to satisfy.

Prefill moves −2.5 µs/token (−0.224 %), C sd 11.5 µs vs F sd 8.8 µs. I do not
claim prefill: the fused kernel is a decode-path kernel and the 12-run subset
gave −5.0 µs, so this is drift, not signal. It is reported because prefill is
scored and the sign is not adverse.

**Growth path for the interval.** The 12-run subset gave −65.4 µs with a block
CI of [−209.6, +78.7] (straddling) and an adjacent CI of [−123.6, −7.3]. Going
to 36 runs moved the point estimate by 11 µs and cut the block se from 33.5 to
11.0. The two estimators, which disagreed at n=12 about whether zero was
excluded, now agree. That convergence is the reason I did not stop at 12.

#### What it is worth

At the corrected price of **0.0084 %/wall-µs** (`%score = 0.75 · Δ/8972`):

| transfer model | assumption | score |
|---|---|---:|
| absolute | the µs saved on M4 are saved on M5 | **+0.64 %** |
| relative | the −0.591 % fraction carries to M5 | **+0.45 %** |

Both are far above the campaign's +0.25 % threshold (+18.5 pp of crown
probability). The absolute model is the more apt one for a dispatch-shaped
saving — per-dispatch host cost does not scale with GPU throughput — but the
M5's host side is faster than this M4's, so I quote the **relative +0.45 %** as
the number I would defend, and note that neither model is measurable here.

#### The point estimate slightly exceeds its own ceiling

§1.4 priced the dispatch-shaped pool at **74.6 µs/step** (50.0 glue + 24.6
unattributed residual). The measured −76.8 µs is **2.2 µs above** it, well
inside the block interval's ±25 µs. Two readings, and §3.5 is built to separate
them:

1. the ceiling is simply 2.2 µs low — the residual row is a balancing term and
   absorbs everyone else's error; or
2. part of the saving is **not** dispatch-shaped at all: the 8 gate tiles, once
   appended to a 5120-tile grid, are co-scheduled onto cores that the
   DRAM-bound QKV tiles leave idle, so some of `gate_sp`'s 186.9 µs/step of
   in-kernel latency is now *hidden* rather than merely un-dispatched.

Reading 2 matters a great deal for τ_xfer: hidden real work is τ ≈ 1-class,
not τ ≈ 0.01-class. I do not assume it. §3.5 measures it.

**§3.5 resolves this in favour of reading 2**, and by a wide margin: the fused
kernel absorbs 93.8 % of `gate_sp`'s serialized GPU busy time. The ceiling was
built for a dispatch-only mechanism and does not bind this arm.

### 3.5 Busy attribution: **reading 2 is correct — 93.8 % of `gate_sp`'s busy is absorbed, not un-dispatched**

`research/maple-alphonse-r114-gatesp-split1-arms.sh` applies the PR-91 GPUPROF
hook, builds **one** instrumented worker, and takes three `decode_probe`
captures at `MLXFAST_GPUPROF_SPLIT=1` × 200 steps in the order **C1, F1, C2**.
The control is captured on both sides of the fused arm so the control repeat
price bounds drift for every quantity that gets differenced. Raw logs:
`/tmp/r114-split1-arms/{C1,F1,C2}.log`, job `221137e5`, wall clock 03:07–03:10Z.
Arithmetic: `research/maple-alphonse-r114-gatesp-split1-attrib.py`.

Both instrumented arms reported `teacher-forced greedy tokens: 0 divergences`.

**Control repeat price (C2 − C1), µs/step:** wall −3.0, busy +4.0, gap −7.0,
`gate_sp` −0.6, `qkv` +0.2. Every difference below is 30–500× that.

| µs/step | C (mean of C1,C2) | F1 | Δ |
|---|---|---|---|
| `gate_sp_h64` + `gate_sp_h48` busy | 317.3 | 0 (gone) | |
| `decode_nvfp4_qkv_h64/h48` busy | 1706.2 | 1725.8 (fused) | |
| **targeted busy total** | **2023.5** | **1725.8** | **−297.7** |
| total GPU busy | 8556.0 | 8242.0 | −314.0 |
| gap (all dispatches) | 1218.5 | 990.0 | −228.5 |
| **probe wall** | **9773.5** | **9232.0** | **−541.5** |
| dispatches/step | 406 | 366 | **−40** |

`Δwall = Δbusy + Δgap` closes to +1.0 µs. Dispatches fall by **exactly 40**,
confirming the fusion removes the 40 `gate_sp` launches and nothing else.

Per call, this is the whole story:

| | gate alone | qkv alone | sum | fused | qkv grew by |
|---|---|---|---|---|---|
| h64 (30/step) | 7.90 | 44.77 | 52.67 | **45.24** | **+0.47** |
| h48 (10/step) | 8.02 | 36.31 | 44.33 | **36.85** | **+0.54** |

Appending the 8 gate threadgroups to the QKV grid costs **0.47–0.54 µs/call**.
Running those same threadgroups as their own dispatch costs **7.90–8.02
µs/call**. **93.8 % of `gate_sp`'s serialized GPU busy time disappears** —
19.6 µs/step of added busy against 317.3 µs/step standalone.

Per-kernel nesting confirms the accounting basis: within each arm
`laguna_gate_sp` shows 0.70–0.92 % nesting and `laguna_decode_nvfp4_qkv`
0.17–0.19 %, i.e. at `SPLIT=1` the two target kernels are effectively
serialized and `busy_sum` for them is additive. (The tool's global
`busy_sum/busy_union = 1.09–1.10` and its "NOT SPLIT=1" warning come from
0.8 % of command buffers carrying more than one dispatch — prefill and lmhead
work outside the two kernels of interest. It does not touch the rows above.)

**Verdict — `N-GRIDAPPEND-ABSORBS-LATENCY`.** The saving is *not* purely
dispatch-shaped. It has two mechanisms, and at `SPLIT=1` the larger one is
in-kernel: 55 % of the serialized Δwall is absorbed busy (−297.7 of −541.5) and
42 % is gap. §3.4's "2.2 µs above the ceiling" is therefore not an arithmetic
paradox and not measurement error: the 74.6 µs/step dispatch-shaped pool was
computed for a dispatch-only mechanism, and this arm has a second source the
ceiling never counted. **The ceiling does not bind this arm.**

The mechanism is the one §1.5/§1.6 predicted. `gate_sp` launches 8
threadgroups onto 20 cores and reaches 51.3 GB/s — 47 % of what 8 threadgroups
can attain — because it is memory-*latency* bound, not bandwidth bound. Its
cost is mostly idle cores waiting on DRAM. Appended to a grid whose QKV tiles
are themselves waiting on DRAM, those 8 tiles issue their loads into slots that
were already stalled, and the union of the two is barely longer than the QKV
tiles alone. This also disposes of the independent review's flagged risk
(§3.3): if the fused kernel's register allocation — the union over both
branches — had cost occupancy, the QKV portion would have slowed down. It grew
by 1.0 % (h64) and 1.5 % (h48), which is the gate tiles' own execution plus any
occupancy loss, jointly immaterial.

#### 3.5.1 `N-ATLAS-SPLIT1-OVERSTATES-OVERLAPPABLE` — the atlas needs a discount

The same three captures calibrate the tool the whole round is being steered by,
and this is the finding with the longest shelf life.

Deflating the SPLIT=1 Δwall by the atlas's own per-dispatch instrumentation
constant (40 × 1.554 = 62.2 µs) gives a **serialized-world saving of 479.3
µs/step**. The scored `SPLIT=0` measurement is **76.8 µs/step**. So:

- **16.0 %** of the serialized saving survives into the real pipeline. The other
  84 % is work MLX's existing `SPLIT=0` dispatch pipelining *already* overlaps,
  and which forced serialization credits to the fusion by construction.
- Against the R109-E atlas entry for `gate_sp` (261.6 µs/step, already
  SPLIT-corrected per §0.1), the realized wall is **29.4 %**.

This arm is close to the best case for that atlas row — it removes 100 % of the
kernel's dispatches and 93.8 % of its serialized busy — and it returns under a
third of the row. The reason is structural, not a bug: **`SPLIT1_INFLATION_US`
corrects for per-dispatch instrumentation overhead only. It does not correct
for the loss of dispatch overlap that `SPLIT=1` also imposes.** For a large
kernel that saturates the machine on its own, that omission is harmless,
because there was little overlap to lose. For a small, latency-bound,
overlappable kernel it is the dominant error, and the atlas overstates
recoverable wall — here by **3.4×**.

Practical rule for picking the next lever off that table: an atlas row's
realizable wall should be discounted by how overlappable the kernel is. The
cheap proxy is threadgroup count — a row whose kernel launches fewer
threadgroups than the machine has cores is a row whose atlas figure is mostly
already hidden at `SPLIT=0`. All three §5 follow-ups are of exactly this shape,
so their ≈80–108 µs/step estimates should be read as **≈25–30 µs/step** each
until measured. That reduces the combined §5 ceiling from ≈−215 µs/step to
≈−60 µs/step, which is barely above this round's 36 µs bar, and is the single
most decision-relevant number in this note.

#### 3.5.2 What this does to the τ_xfer argument

§4.3 argues the M4→M5 transfer risk as a risk. §3.5 sharpens it by splitting
the surviving 76.8 µs/step into two mechanisms with different transfer
behaviour:

- **Gap / dispatch glue** — host- and driver-side, roughly independent of GPU
  throughput. The M5's host side is faster, so this component likely shrinks in
  absolute µs.
- **Absorbed in-kernel latency** — depends on there being idle cores for the
  appended tiles. The M5 Max has *more* GPU cores than this M4 Pro's 20, so a
  standalone 8-threadgroup `gate_sp` is *even more* under-occupied there, while
  8 appended tiles remain at least as free. Directionally this component should
  not weaken, and may strengthen as a fraction.

I cannot measure either on this host, so I claim neither. The point is only
that the arm is no longer a pure τ ≈ 0.01-class dispatch-count change, which is
the class the round's prior was most sceptical of; a majority of its
`SPLIT=1` mechanism is real work being hidden, and hidden work is the
τ ≈ 1-class category. This is an argument that the transfer risk is *lower*
than §4.3 assumes, not evidence that it is zero.

One loose end I am not claiming: non-targeted busy also fell by 16.3 µs/step,
almost all of it `sliding_fused_attn_ring_v1` (−13.3 µs/step against a control
repeat drift of −0.8). That is larger than drift and I have no mechanism for
it. It is 2 % of the total busy delta and I have left it unattributed rather
than folded into the result.

## Stage 4 — τ, and a definitional problem with it

Feedback `r116-e-tau-filter-and-0p15` asks me to attach a measured τ, defined as

```
tau = D_wall_per_step / D_targeted_busy_per_step
```

with `D_wall` from a paired ABBA at SPLIT=0 and `D_busy` from SPLIT=1. I will
report that number, but the τ table in that comment mixes **two different
ratios**, and my arm sits exactly on the seam, so I have to separate them
before the number means anything.

### 4.1 There are two τ's, and only one of them is measurable on this host

| | definition | what it answers | measurable here? |
|---|---|---|---|
| **τ_bw** | `D_wall_M4 / D_busy_M4` | did removing GPU busy time actually shorten the step? | **yes** — SPLIT=0 ABBA over SPLIT=1 attribution |
| **τ_xfer** | `D_score_M5 / (0.75 · D_wall_M4 / 8972)` | does an M4 wall win survive on the ranked M5? | **no** — needs an M5 |

The table's rows are not the same quantity:

- "removes real DRAM traffic → τ ≈ 1.06, evidence: byte-census arms track wall
  1:1" is **τ_bw**.
- "threadgroup geometry → τ ≈ 0, evidence: PR #7 +7.32 % on M4 → ~0 % on M5"
  is **τ_xfer**. Nothing about that row says busy did not convert to wall on
  M4; it says the M4 wall win did not exist on M5.
- "pure dispatch → τ ≈ 0.01, evidence: frieren's 100 % harvest of the
  413 µs/step host gap = +0.035 % of score" is neither: it is a **census-pool
  ceiling**, i.e. the very quantity `N-DISPATCH-REMOVAL-NOT-SYMMETRIC` says
  bounds opportunity but never estimates it.

The scoring formula in the same comment,
`%score = 0.75 · tau · D_wall / 8972`, applies τ to `D_wall`. If τ is τ_bw
(`D_wall/D_busy`) that expression divides the wall saving by the busy saving
and then multiplies by the wall saving again, which is dimensionally wrong. The
formula only makes sense with τ_xfer. **I therefore report τ_bw as the
measurement, and treat τ_xfer as an argued risk, never as a measured number.**

### 4.2 Why τ_bw is the wrong gate for *this* arm, and what the right one is

I wrote this section before §3.5 ran, and predicted that this arm removes **no
busy work at all** — the gate tiles execute the identical instruction stream on
the identical bytes and are merely appended to a grid that was already being
dispatched, so `D_busy ≈ 0` and τ_bw = `D_wall / ~0` is undefined.

**§3.5 refuted that prediction.** Measured `D_busy = −314.0 µs/step` at
`SPLIT=1`, of which −297.7 is the targeted kernels: the appended tiles cost
0.47–0.54 µs/call instead of 7.90–8.02, because their DRAM latency now hides
behind the QKV tiles' stalls. The instruction stream is indeed identical; what
changed is that it no longer needs its own serialized slot. I was wrong that
"same instructions on same bytes" implies "same busy".

That leaves τ_bw computable but still the wrong gate, for a different reason
than I gave. Taking the SPLIT=0 wall Δ over the SPLIT=1 busy Δ gives
`76.8 / 314.0 = 0.24`, and that ratio is a mongrel: numerator and denominator
come from different dispatch regimes. Within `SPLIT=1` alone the conversion is
`541.5 / 314.0 = 1.72`, which exceeds 1 only because removing dispatches also
removed 228.5 µs of gap. Neither number is the "did busy convert to wall"
quantity the filter was designed to test, because `SPLIT=1` manufactures the
very serialization whose removal it is being asked to price (§3.5.1).

So the applicable gates remain:

1. **is the wall interval real?** — §3.4, paired ABBA, SPLIT=0, three intervals;
2. **is it the mechanism I claim?** — §3.5, SPLIT=1 attribution: **answered,
   and not the mechanism I predicted**;
3. **does it survive on M5?** — τ_xfer, §4.3 and §3.5.2, argued not measured.

The Δ that is being claimed is still measured **directly on the scored wall
clock, at SPLIT=0, paired**, with no busy→wall conversion step in it.

### 4.3 The τ_xfer argument, stated as a risk and not as a result

The ceiling this arm can harvest is exactly the dispatch-shaped part of §1.4:

```
74.6 us/step = 50.0 MLX per-dispatch glue + 24.6 unattributed in-situ residual
```

Nothing else in the table is touched — weight loading (102.9), the rest of the
K loop (47.2) and the in-kernel fixed cost (36.9) are all still executed, byte
for byte, by the appended tiles.

The nearest prior is **nezuko's #682**, and the contrast is the whole argument.
She also removed **40 dispatches/step** (406 → 366) on **this same kernel**, and
her wall went **up** +51.73 µs/step. Two things separate the arms:

| | nezuko #682 | this arm |
|---|---|---|
| dispatches removed / step | 40 | 40 |
| new dependency edge | **yes** — `gate_sp` became the sole producer of `normalized` | **no** — `gate_sp` and QKV are siblings, both consume `normalized`; `dep_scope = NONE` |
| threadgroup geometry | **changed**; arm S alone, bit-exact, cost +43.23 µs = 83 % of the regression | **unchanged** — both tile families keep `threadGroup (64,1,1)` |
| busy removed | −204.9 µs/step (the pre-norm deleted) | ≈ 0 by construction |

Her regression is 83 % geometry, and geometry is the row with τ_xfer ≈ 0. This
arm changes no geometry, so the single largest term in the only prior that
refutes dispatch removal **does not apply to it**. What remains is the honest
residual risk: the M5's per-dispatch glue may simply be cheaper than the M4's
1.2382 µs, in which case the same structural change harvests proportionally
less. That shrinks the win; it does not invert it, because there is no
mechanism here that trades a dispatch for added work.

I cannot measure τ_xfer. I state the exposure plainly: **if M5 per-dispatch
glue were zero, this arm would be worth zero.** It is not a geometry arm, it is
not a busy-census arm, and it introduces no dependency edge, so it is not
covered by any of the three negatives the τ filter is built from.

### 4.4 The arithmetic consistency check, and what this arm tests about `N-DISPATCH-REMOVAL-NOT-SYMMETRIC`

Rule 57's M4 marginal dispatch cost, **1.2382 [1.2237, 1.2518] µs/dispatch**,
was fitted on **wall**, not on busy. It is the forward half of the asymmetry
law: *add* a dispatch and wall grows. This arm removes 40 dispatches/step
(one `gate_sp` per layer), so Rule 57 predicts

```
40 x 1.2382 = 49.5 [49.0, 50.1] us/step   if removal were exactly symmetric
```

and §1.4's dispatch-shaped ceiling, glue plus the unattributed in-situ
residual, is **74.6 µs/step**. The 36-run ABBA measures **−76.8 µs/step
[−102.2, −51.4]**: **155 % of the symmetric Rule 57 prediction** and **103 % of
the ceiling**, with both reference values sitting inside the interval. The
27 µs by which it beats Rule 57 is the size of the 24.6 µs unattributed
residual, which is where a per-command-buffer term that does not scale with
dispatch count would live. I do not claim to have separated those; I claim the
saving is bracketed by two independent estimates that §1.4 produced before the
arm existed, which is the strongest statement the data supports.

Removal is therefore **not merely symmetric with Rule 57 — it over-delivers by
about 55 %**. A dispatch costs more to have than its marginal add-one price
suggests, which is what you would expect if part of the cost is per-command-
buffer rather than per-dispatch.

That is the reason this arm is worth running even if it were not shippable.
`N-DISPATCH-REMOVAL-NOT-SYMMETRIC` currently rests on a single counter-example
in which dispatch removal was **confounded with** a new dependency edge and a
threadgroup-geometry change worth 83 % of the observed regression. This arm
removes the same 40 dispatches on the same kernel with neither confound. If its
interval excludes zero, the law does not fall — it **sharpens**, to something
like: *dispatch removal converts to wall only when it adds no dependency edge
and changes no threadgroup geometry.* If the interval straddles zero, the law
stands in its current strong form and I will say so.

**Which floor applies.** The brief set the landing bar at **36 µs/step**
(+0.25 % of score at 0.0070 %/µs); the τ-filter comment restates Rule 105.12's
floors as **68.7 µs/step bytes-bound / 60.0 µs/step latency-bound** and revises
the price to 0.0084 %/wall-µs. At the revised price, 36 µs/step is +0.30 % and
60 µs/step is +0.50 %. I report the interval against **both**, and treat the
stricter 60.0 µs/step figure as the one that has to be cleared before I call
this shippable rather than merely non-zero.

§3.5 settles *which* of the two Rule 105.12 floors is the right one. The arm
moves no bytes — the appended tiles read the identical `g_proj` weights the
standalone kernel read — and its measured mechanism is absorbed memory
*latency*. It is therefore a **latency-bound** change, so the applicable floor
is **60.0 µs/step**. The point estimate of −76.8 µs/step clears it by 28 %.
The honest qualifier is unchanged: the upper bounds of all three intervals
(−51.4 block, −55.3 adjacent, −47.5 Welch) sit below 60.0, so the *interval*
clears the 36 µs landing bar but not the stricter floor. What I claim is a
point estimate above the floor with an interval that excludes zero, not an
interval entirely above the floor.

---

## Stage 5 — where grid-append goes next (not implemented here)

Grid-append is a *family*, and `gate_sp` is its smallest member. I asked for an
independent survey of the decode path for other dispatches with the same
`dep_scope = NONE` shape — small output, input already read by a larger sibling
in the same layer — and the two strongest candidates are both an order of
magnitude bigger than the one measured here.

1. **Shared-expert SwiGLU into the routed SwiGLU grid.** The plumbing already
   exists: `mergedSharedActivated` at `LagunaRuntimeModel.swift:10958` is the
   half-built version of exactly this merge. Atlas ceiling ≈ 80–108 µs/step.
2. **Router top-8 retiled to 64 threads and appended to that same grid.**
   Atlas ceiling ≈ 80–108 µs/step. Critically it must *not* be appended into the
   down-projection or residual dispatch, which would create a real
   producer→consumer edge and pay the +2.55 µs/layer = +102 µs/step penalty.
3. **`inputNorm` folded into the QKV+gate kernel.** Same ceiling, but it needs
   an 8-rows-per-threadgroup retile and it *is* a producer of `normalized`, so
   it is the risky one and should be attempted last.

**Apply the §3.5.1 discount before believing any of those three ceilings.**
They are read off the same R109-E atlas whose `gate_sp` row returned 29.4 % of
its face value, and all three are the same shape that causes the overstatement:
few threadgroups, latency-bound, already partly overlapped at `SPLIT=0`. At
this round's realized ratio each is worth **≈25–30 µs/step**, and (1)+(2)
together ≈ **−60 µs/step**, not the −215 µs/step the raw atlas suggests. That
still clears the 36 µs bar as a pair, but neither clears it alone, and the
`0.95` prefill floor has to be re-checked for a SwiGLU-grid change because that
grid is also on the prefill path. My recommendation is to sequence (1) and (2)
as one assignment with a shared ABBA, rather than as two arms that each look
like noise.

The offline alternative — folding the gate weight matrix onto the QKV weight
matrix in `Sources/MLXFastTransform/` so the gate is just extra output rows of
the QKV matmul — was checked and **rejected on three independent grounds**:

- the two banks use different quantisation schemes (per-head affine INT8 for
  `g_proj` vs NVFP4 group-16 for QKV), so a single bank cannot represent both
  without a re-quantisation that is neither bit-exact nor inside the accepted
  attention envelope in `TASK.md`;
- `Transform.swift:57-85` fixes a byte-for-byte artifact contract; and
- the runtime *already* has this folding for the affine world (`foldGateIntoBank`,
  ~`LagunaRuntimeModel.swift:5813`) and it costs 2× the QKV bytes, which on a
  bandwidth-bound decode step is a worse trade than the dispatch it removes.

The dispatch-level grid append measured here is the bit-exact realisation of
the same idea, and the softplus is already fused in-kernel, so there is nothing
left for an offline pass to win.

### The diagnostic this round did not buy

To tell "the appended tiles were hidden" from "the appended tiles serialised"
the sharpest cheap probes are (a) append-**last** vs append-**first** as a
paired arm, and (b) inflating the gate body's K loop 4× and watching whether
step wall time is insensitive (hidden) or grows ~1:1 (serialised). Both are
single-flag variants of the kernel already in the tree. I did not run them
because they only matter once the family is worth scaling, and the assignment
asked for one clean causal arm rather than a stack of unmeasured mechanisms.

Two caveats on all of the above: threadgroup **launch order is not guaranteed**
by Metal, so "gate tiles lead" is a scheduling expectation and not a contract,
and it must be re-verified on the M5 Max; and every µs/step projection in this
section rests on the M4 Pro per-dispatch fixed-cost decomposition of §1.4.
