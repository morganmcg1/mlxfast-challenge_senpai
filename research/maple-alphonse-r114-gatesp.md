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

This arm removes **no busy work at all**. The gate tiles execute the identical
instruction stream on the identical bytes; they are merely appended to a grid
that was already being dispatched. So the honest prediction is
`D_busy ≈ 0`, which makes τ_bw = `D_wall / ~0` — unbounded, undefined, and
useless as a filter.

That is not an evasion, it is the point. The τ_bw filter exists to catch arms
that *claim* a wall win from a measured busy win. This arm never measures busy;
its Δ is measured **directly on the scored wall clock, at SPLIT=0, paired**.
There is no conversion step to be sceptical of. The applicable gate is
therefore not τ_bw but:

1. **is the wall interval real?** — §3.4, paired ABBA, SPLIT=0;
2. **is it the mechanism I claim?** — §3.5, SPLIT=1 attribution: if fused busy
   ≈ QKV busy + gate busy, the saving is dispatch-side, as predicted;
3. **does it survive on M5?** — τ_xfer, §4.3, argued not measured.

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

---

## Stage 5 — where grid-append goes next (not implemented here)

Grid-append is a *family*, and `gate_sp` is its smallest member. I asked for an
independent survey of the decode path for other dispatches with the same
`dep_scope = NONE` shape — small output, input already read by a larger sibling
in the same layer — and the two strongest candidates are both an order of
magnitude bigger than the one measured here.

1. **Shared-expert SwiGLU into the routed SwiGLU grid.** The plumbing already
   exists: `mergedSharedActivated` at `LagunaRuntimeModel.swift:10958` is the
   half-built version of exactly this merge. Ceiling ≈ 80–108 µs/step.
2. **Router top-8 retiled to 64 threads and appended to that same grid.**
   Ceiling ≈ 80–108 µs/step; combined with (1) the family ceiling is roughly
   −215 µs/step. Critically it must *not* be appended into the down-projection
   or residual dispatch, which would create a real producer→consumer edge and
   pay the +2.55 µs/layer = +102 µs/step penalty.
3. **`inputNorm` folded into the QKV+gate kernel.** Same ceiling, but it needs
   an 8-rows-per-threadgroup retile and it *is* a producer of `normalized`, so
   it is the risky one and should be attempted last.

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
