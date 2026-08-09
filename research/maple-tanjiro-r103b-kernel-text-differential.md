# R103-B: kernel-text differential, `30f752df` (OLD) -> `0f6862d0` (NEW)

Assignment `maple-r103-b-kernel-text-differential`, revision `r103-b-rev1`,
PR #572. Research-only: **zero submitted-surface bytes changed**.

## 0. Verdict in one paragraph

Between arm-R's receipt commit `30f752df` (`cs` 2.589321, 4893.712 us/step) and
the current advisor base `0f6862d0` (`cs` 2.582286, 4913.117 us/step) the
reported decode metric gained +19.405 us/step, and the **true steady-state
per-step regression is `T` = +20.149 us/step** once the frontier's better
prefill is removed from the `D = 4P + T` identity (section 7.0). Over that range the
runtime compiles and dispatches **exactly the same 103 Metal libraries in the
same order with the same grids, threadgroups and buffer shapes**; the
per-decode-step dispatch count is **408 at both revisions** and the two traces
are positionally identical for all 11,243 compared dispatches. Only **two**
kernels change their final MSL text:

| # | kernel | family | calls/step | M5 us/step | change |
|---|--------|--------|-----------:|-----------:|--------|
| **A** | `custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1` | T1a | 39 | 156.4 | router-weight prefetch hoisted across the RMSNorm reduction (PR #558) |
| **B** | `custom_kernel_laguna_sliding_fused_attn_ring_v1` | T3a | 30 | 318.0 | K/V software pipelining widened 2-way -> 4-way (PR #565) |

Everything else in the 32-file source diff is comment/whitespace-only byte
reclamation or offline transform code that provably does not touch the scored
runtime. **The whole on-GPU regression must come from A, B, or their
interaction.** Dispatch overhead contributes **0.00 us/step**. Preregistered
nulls N-A, N-B, N-C and N-D are all refuted.

Both survivors are the *same class* of change - extra live registers bought for
instruction-level parallelism - and both dispatch exactly **32 threadgroups**,
so on a >= 32-core ranked host they run one wave at <= 1 threadgroup per core
while on this 20-core M4 Pro they run two. Section 7.2 works this out from the
kernel text and concludes that the M4 probe cannot rank A against B even in
principle. Neither mechanism changes the amount of work: I verified the 4-way
unroll covers exactly the same 16 key slots per simdgroup as the 2-way loop and
leaves **no tail loop**, for every simdgroup index.

The cheapest decisive follow-up is therefore one paired **M5** measurement with
`DARKBLOOM_ROUTER_WEIGHT_PREFETCH=0`, which restores A's kernel **bit-exactly**
with no code edit (proved in [rung 1](#5-rung-1-msl-text-differential)); if that
recovers the +20.149, A is convicted and B is exonerated, and if it does not,
B is convicted by elimination.

---

## 1. Preregistration (fixed before any measurement)

Nulls, as written in the assignment:

- **N-A** - no textual or dispatch difference exists on the scored decode path.
- **N-B** - the only difference is the `LagunaRuntimeLayers.swift` file fold.
- **N-C** - the difference is dispatch-side only (count/geometry/args), not
  kernel text.
- **N-D** - the difference is diffuse: more than 8 kernels differ, so no single
  mechanism can be named.

Stopping rule: first of (1) rungs 1+2+3 complete, (2) N-A fires, (3) rung 0
blocked after fallbacks are exhausted. Outcome: **(1)**.

Rule 83 prior-art disclosure: `research/RESEARCH_ARCHIVE_through-round-91.md`
was grepped for `msl`, `kernel text`, `dispatch trace`, `library dump` and
related terms. **Zero hits** - no prior R-round attempted a kernel-text or
dispatch differential.

## 2. Arms

| arm | commit | router prefetch | purpose |
|-----|--------|-----------------|---------|
| `old` | `30f752df` | n/a (flag does not exist) | arm-R receipt revision |
| `new` | `0f6862d0` | `1` (shipped default) | current advisor base |
| `new_pf0` | `0f6862d0` | `0` | isolates mechanism A inside one binary |

Two detached `git worktree`s under the gitignored `.mlxfast-private/` hold OLD
and NEW simultaneously. One trusted CLI drives both workers (the CLI sources are
byte-identical across the range). The full recipe, including three harness traps
that cost an hour, is written up for reuse in
[`research/r103-armr-build-notes.md`](r103-armr-build-notes.md).

**Metallib control.** The same `mlx.metallib` (158,502,072 B) is placed in both
worktrees. This is sound and is itself part of the result: every AOT
`.metal`/`.h` source that differs across the range differs by comments and
whitespace only (section 4), so the two revisions would compile the same
metallib. It also means the AOT-only families invisible to the MSL hook -
`arg_reduce`, `layer_norm`, `random`, `rms_norm`, `rope`,
`scaled_dot_product_attention` (+`sdpa_vector.h`), `conv`, `fence` - are held
constant by construction rather than by assumption.

**Instrumentation.** `research/r103b/scripts/trace.patch` (+148/-4) adds
`mlx::core::metal::mlxfast_trace` to
`Vendor/mlx-swift/.../backend/metal/device.cpp|.h`, which are **outside**
`editablePaths`. It dumps every JIT library's final MSL text
(`Device::get_library`) and logs every `dispatch_threadgroups` /
`dispatch_threads` with kernel name, grid, threadgroup and the shape+dtype of
every bound input array. It is enabled only by `MLX_TRACE_DUMP_DIR` and was
reverted before commit; the patch is kept as a research artifact, not applied.

Workload: `mlxfast-swift correctness-trace --step 5 --top-k 5` against the
public golden - one 512-token prefill plus 6 teacher-forced decode steps,
identical for all three arms.

## 3. Rung 0 - both trees build and agree, PASS

All three arms are **token-identical and top-5-logit-identical**:

```
case longcopy-gate-english-512   step 5   matched_prefix_steps 6
generated_prefix [5991, 509, 902, 5991, 509, 902]   actual=expected=902 (rank 1)
top_logits [(902,24.125),(340,18.25),(5991,16.875),(4423,16.75),(750,16.625)]
top_logit_margin 5.875   golden_hash b9509697c08a2cf3...
```

```
[old]     rc=0  msl=103  dispatch=11247
[new]     rc=0  msl=103  dispatch=11243
[new_pf0] rc=0  msl=103  dispatch=11247
```

Working-set digests: `research/r103b/artifacts/working-set-manifest.tsv`
(82 rows). Git index-tree digest over the scored surface:

| | OLD | NEW |
|---|---|---|
| tree sha256 | `fe3d95764c6fdf92114267d589e8018e4f515133495fbbf2d980732048fcdcdb` | `f65b09e66f716ee14f3048b018401c2d37669d3f09b2c9e784339436b7f54a25` |
| `LagunaRuntimeModel.swift` | `119a17bc...` 398,661 B | `1e0c7d43...` 519,236 B |
| `LagunaRuntimeLayers.swift` | `b088a675...` 112,578 B | *(deleted)* |
| worker binary | 49,145,848 B | 49,257,896 B |
| metallib | shared, 158,502,072 B | shared |
| weights | shared, byte-identical | shared |

## 4. Static differential: what actually changed in 32 files

`git diff --numstat 30f752df 0f6862d0 -- Sources Vendor Package.swift
benchmark.json` reports 32 files. A literal-aware comment/whitespace stripper
(`research/r103b/scripts/comment_strip_diff.py`) proves **27 of 32 are
comment/whitespace-only** - the byte-reclamation pass merged as PR #548
(`f720e9e7`). That includes:

- all 7 AOT `.metal` / `.h` kernel sources,
- `quantized.cpp`, `kernels.h`, `jit_kernels.cpp`, `matmul.cpp`,
- all 15 vendored `MLXLMCommon` / `Laguna` Swift files, and `LagunaConfig.swift`.

**No vendored MLX C++ or Metal behaviour changes across the range.**

The remaining 5 files: `LagunaRuntimeLayers.swift` (deleted, folded into
`LagunaRuntimeModel.swift`), `LagunaRuntimeModel.swift`, and three
`MLXFastTransform` files (`AffineMetadataCoding.swift`,
`TiedHeadMetadataCoding.swift`, `Transform.swift`). The transform files are
offline-only: the `.laguna` checkpoint emits no sidecars and `weights/` is
byte-identical between the arms, so they cannot move scored time.

Semantic payload of the fold, after removing pure-move hunks
(`research/r103b/artifacts/lrm_payload.txt`, ADDED 173 / REMOVED 24):
mechanism A, mechanism B, a duplicate-import removal, and `internal` -> `private`
narrowing on six symbols.

## 5. Rung 1 - MSL text differential

Every JIT library's *final* MSL text was captured at the point MLX hands it to
the Metal compiler, for all three arms
(`research/r103b/artifacts/msl_sha256_{old,new,new_pf0}.tsv`).

### OLD vs NEW

```
libraries old=103 new=103
common=102  byte_identical=101  differing=1
only_old=1  only_new=1
```

**Exactly two kernels change. 101 of 103 are byte-identical.**

#### Mechanism A - router weight prefetch (name *and* text change)

```
old  ..._rpg8_keys_v1_...       52,359 B  19d8e9fadbfafafa
new  ..._rpg8_keys_v1_pf1_...   53,264 B  dd7a9210c57f86f7
```

Full diff: `research/r103b/artifacts/msl_diff_residual_rms_router.diff` -
49 lines, 3 hunks, +25/-3. Hunk 1 is the `_pf1` name suffix. Hunk 2 inserts,
*between* `acc = simd_sum(acc)` and the threadgroup `local_sums` reduction:

```metal
thread vec<bfloat, 4> laguna_pf[4];
if (simd_group < active_simd_groups) {
    uint laguna_pf_row = tile * rows_per_group + simd_group * rows_per_thread;
    uint laguna_pf_column = simd_lane * n_reads;
    for (uint k = 0; k < 4; ++k) {
        const device vec<bfloat, 4>* pf_values =
            (const device vec<bfloat, 4>*)(router_weight +
                laguna_pf_row * axis_size + laguna_pf_column + k * block_width);
        laguna_pf[k] = pf_values[0];
    }
}
```

Hunk 3 peels the first four blocks of the router GEMV out of the main loop so
they consume `laguna_pf` instead of re-reading device memory
(`for (block = 0; ...)` becomes `for (block = 4; ...)`).

Kernel constants (from the dumped MSL): `axis_size 2048`, `n_reads 4`,
`rows_per_thread 1`, `active_simd_groups 8`, `block_width 128`,
`router_blocks 16`. Dispatch: `threads`, grid `16384x1x1`, threadgroup
`512x1x1` (32 threadgroups x 16 simdgroups, 8 active), `router_weight`
`bfloat16[256,2048]` = 1 MiB read per call.

The intent is clear and reasonable: overlap 1 MiB of router-weight latency with
the RMSNorm reduction. The cost is that **32 bytes/lane (8 extra 32-bit
registers) stay live across the threadgroup barrier region** in an
already-latency-bound kernel.

#### Mechanism B - sliding fused attention, 2-way -> 4-way K/V pipelining

```
custom_kernel_laguna_sliding_fused_attn_ring_v1_...
  60,780 B  39412f51db8d4eb3  ->  64,866 B  4d12c05ab71ab44e
```

Full diff: `research/r103b/artifacts/msl_diff_sliding_fused_attn.diff` -
124 lines, +92/-4. The **sole semantic change** is at MSL line 1280:

```metal
-for (; i + BN < N; i += 2 * BN) {
+for (; i + 3 * BN < N; i += 4 * BN) {
```

with the loop body gaining `pipe_keys_c/d`, `pipe_values_c/d`, `pipe_kc[4]`,
`pipe_kd[4]`, `pipec_score0/1`, `piped_score0/1`.

Reachability and coverage, from the dumped constants and the trace:
`BN = 32`, `BD = 32`, `N = 512`, `int i = sg`, threadgroup `1024x1x1`
(32 simdgroups), grid `32768x1x1`, K/V buffers `bfloat16[1,8,512,128]` (2 MiB
per call), output `bfloat16[1,64,1,128]`. Simdgroup `sg` therefore covers keys
`{sg, sg+32, sg+64, ...}` - 16 keys - as **8 two-way iterations** at OLD and
**4 four-way iterations** at NEW. Same total work over the full 512-position
sliding window; roughly **twice the in-flight K/V register state** per
simdgroup, in a kernel already running at the 1024-thread threadgroup maximum.
This kernel is live at decode: **30 dispatches per step**.

The sibling `custom_kernel_laguna_full_fused_attn_grow_v1` (T3a', 10 calls/step)
still uses the 2-way loop (`LagunaRuntimeModel.swift:2168`); only the sliding
kernel was widened (`LagunaRuntimeModel.swift:1639`).

### OLD vs `new_pf0` - A is bit-exactly restorable

```
libraries old=103 new_pf0=103
common=103  byte_identical=102  differing=1   (only the fused-attn kernel)
only_old=0  only_new_pf0=0
```

`DARKBLOOM_ROUTER_WEIGHT_PREFETCH=0` reproduces the OLD router kernel's **name
and MSL text bit-for-bit** from the NEW binary. That is the property that makes
the follow-up experiment in section 10 cost one measurement and no code edit.

## 6. Rung 2 - dispatch trace, over a fixed decode-step count

Traces were segmented on the per-step marker
`custom_kernel_laguna_decode_embedding_rope_atlas`
(`research/r103b/artifacts/steps_old_vs_new.txt`):

| segment | old | new | new_pf0 | delta (new-old) |
|---------|----:|----:|--------:|----------------:|
| prefill | 7334 | 7334 | 7334 | **0** |
| decode step 0 | 1759 | 1759 | 1759 | **0** |
| decode step 1 | 528 | 528 | 528 | **0** |
| decode steps 2-4 | 408 | 408 | 408 | **0** |
| decode step 5 (truncated) | 402 | 398 | 402 | -4 |

The step-5 `-4` is a **trace-teardown artifact, not a workload difference**:
both `dispatch.tsv` files end mid-line with no trailing newline (verified with
`od -c`), i.e. the tracer's last buffered writes are lost when the worker exits.

Whole-sequence `difflib` alignment (with the `_pf1` rename canonicalised), run
both with and without grid/threadgroup geometry in the key, gives **exactly one
non-equal opcode: `delete a[11243:11247]`** - that same truncated tail. The
first 11,243 dispatches match exactly, *including* `gridWxHxD` and
`groupWxHxD` (`research/r103b/artifacts/seq_old_vs_new.txt`).

Taking the last complete decode step (408 dispatches) and comparing
`(kernel, kind, grid, threadgroup, buffer shapes+dtypes)` row by row:

- **OLD vs NEW**: positionally aligned, **39 of 408 rows differ, and only in the
  kernel *name*** (`_rpg8_keys_v1` -> `_rpg8_keys_v1_pf1`). Every geometry and
  every buffer shape/dtype is identical. After canonicalising the rename the
  two 408-row blocks are **equal**.
- **OLD vs `new_pf0`**: 11,247 vs 11,247 dispatches, **zero** non-equal
  opcodes, **zero** differing `(kind, grid, group, args)` signatures.

**Priced at the rule 53/68 rate of +0.3 us/dispatch, the per-decode-step
dispatch delta is 0 -> +0.00 us/step, i.e. 0 % of the +19.405 us regression.**

Steady-state decode block composition (408 dispatches/step), which matches the
fern-r101 pool-table call counts exactly:

| calls | kernel |
|------:|--------|
| 41 | `rmsbfloat16` |
| 39 | `residual_rms_router...` (**A**) |
| 39 | `shared_nvfp4_swiglu_qmv_rows1_halved` |
| 39 | `prefill_router_tournament_ordinal_norm_active64_v2` |
| 39 | `routed_nvfp4_swiglu_qmv_packed_top8keys_r1` |
| 39 | `routed_shared_nvfp4_down_residual_sh_stage4_v6` |
| 30 | `decode_nvfp4_qkv_h64_r1_v1` |
| 30 | `sliding_fused_attn_ring_v1` (**B**) |
| 30 | `gate_sp_h64_v1` |
| 30 | `oproj_act_h64_v1` |
| 10 each | `gate_sp_h48`, `decode_nvfp4_qkv_h48`, `full_fused_attn_grow_v1`, `oproj_act_h48` |

Across the whole trace, the only kernel-count differences are the router rename
(-236 / +236) and four `-1`s on the truncated tail.

## 7. Rung 3 - ranking and pricing the two survivors

### 7.0 The target is `T` = 20.149 us/step, not 19.405

Per the advisor's 2026-08-09T21:47Z correction, rule 58's `D = 4P + T` is exact
harness arithmetic, not a fit: `decode_seconds_per_token = (S + 128*T)/128` with
seed prefill `S = 512*P`, so `D = 512P/128 + T = 4P + T`. Both `D` and `P` are on
every receipt, so the kernel-resident part separates cleanly:

| | `D` = `cand_dec` | `P` (us/tok) | `4P` | **`T = D - 4P`** |
|---|---:|---:|---:|---:|
| arm R `7ce1262d` | 4893.712 | 188.043 | 752.172 | **4141.540** |
| frontier `e08d759f` | 4913.117 | 187.857 | 751.428 | **4161.689** |
| **delta** | **+19.405** | **-0.186** | **-0.744** | **+20.149** |

The frontier's prefill is 0.186 us/tok *better*, which enters `D` as -0.744 and
masks 3.7 % of the decode regression. Kernel time lives entirely in `T`, so
**everything below is priced against 20.149**, and the dispatch-overhead product
is compared to 20.149 as well. `research/advisor_r103_T_decomposition.py` is not
present at this base sha (`0f6862d0`); the arithmetic above is reproduced
independently from the two receipt pairs.

### 7.1 Pool-table budgets

From `research/artifacts/fern-r101/m5-pool-table.csv`:

| id | family | calls | bytes/call | M5 us/step | us/call | M5 GB/s | % M5 peak | headroom us | regime |
|----|--------|------:|-----------:|-----------:|--------:|--------:|----------:|------------:|--------|
| **T1a** | residual rms router (**A**) | 39 | 1 MiB | **156.4** | 4.01 | 261.5 | 42.8 | 89.4 | latency |
| **T3a** | sliding fused attn (**B**) | 30 | 2 MiB | **318.0** | 10.60 | 197.8 | 32.4 | 215.0 | latency |
| | combined | | | **474.4** | | | | | |

Budget arithmetic against the **+20.149 us/step** `T` regression:

- combined T1a+T3a = 474.4 us = **11.45 %** of arm R's `T` = 4,141.5 us/step;
- +20.149 us = **+4.25 %** of that combined budget - comfortably inside it;
- if **A alone**: **+12.88 %** on T1a (156.4 -> 176.5 us);
- if **B alone**: **+6.34 %** on T3a (318.0 -> 338.1 us);
- **dispatch overhead**: measured per-step dispatch delta is 0, so rule 53's
  +0.3 us/dispatch gives `0 x 0.3` = **0.00 us = 0.00 % of 20.149**.

The 19.405 -> 20.149 correction moves each of these by about +3.8 % relative;
it does not change any qualitative conclusion, because both survivors have an
order of magnitude more budget than the hole.

Both families are **latency-regime** at 32-43 % of M5 peak bandwidth, which is
precisely the regime where kernel-text changes that alter occupancy or ILP move
wall time, and where extra live registers are not paid for by extra bandwidth.
Both candidate deltas are therefore physically plausible; neither is excluded on
magnitude grounds.

### Restorability

| mechanism | restore to OLD state | bit-exact? | evidence |
|-----------|----------------------|-----------|----------|
| **A** | `DARKBLOOM_ROUTER_WEIGHT_PREFETCH=0` (env only, no code edit) | **yes** - name and MSL text | `msl_old_vs_newpf0.txt`: 103 common, 102 byte-identical, 0 only-old, 0 only-new |
| **B** | source edit at `LagunaRuntimeModel.swift:1639` (MSL line 1280) reverting `i += 4*BN` -> `i += 2*BN` and dropping the `_c`/`_d` pipeline temporaries | not verified | no flag exists; **B has never been independently A/B'd since it landed** |

### Ranking

1. **B (sliding fused attention)** ranks first on exposure and on risk of an
   un-retested change: 2x the M5 budget of A (318 vs 156 us), the largest
   register-pressure delta of the two (4 in-flight K/V rows at the 1024-thread
   threadgroup maximum), and no restore flag, so nothing has re-measured it
   since PR #565 merged.
2. **A (router prefetch)** ranks first on *testability*: it is bit-exactly
   restorable from one environment variable, so it can be excluded or convicted
   with a single paired measurement and zero code change. Its mechanism -
   8 extra live registers held across a threadgroup barrier in a kernel with
   only 8 of 16 simdgroups active - is a textbook occupancy-versus-latency
   trade that can go either way per architecture.

Frieren's R103-A commit/receipt table had **not** landed in this base at the
time of writing (`research/` contains only the R103-A helper scripts
`advisor_r103_*.py`, no result table), so the "filter by R103-A" step could not
be applied. Both survivors are named with enough precision that R103-A can
filter them later: A merged as PR #558 (`9453d7b5`), B as PR #565 (`9d9da08e`,
`39b74028`).

### 7.2 Both survivors are the same class of change - and this host is in the wrong occupancy regime to rank them

Reading the two kernels statically settles three things that matter more than
the M4 timing probe in section 8.

**Neither mechanism changes the amount of arithmetic.** For B I checked the
loop bounds exhaustively rather than assuming. In the sliding kernel
`BN = 32`, `BD = 32`, `N = 512`, `head_dim = 128`, `gqa = 8`, `U = float`,
`qk_per_thread = v_per_thread = 4`, `sg = simdgroup_index_in_threadgroup` and
`lane = thread_index_in_simdgroup`, so a 1024-thread threadgroup is exactly
`BN = 32` simdgroups of 32 lanes and the loop `int i = sg` strides by `BN`, one
key position per simdgroup per stage.

| variant | loop | iterations, `sg = 0` | iterations, `sg = 31` | key slots covered | tail loop |
|---------|------|----------------------|-----------------------|-------------------|-----------|
| OLD 2-way | `i + BN < N; i += 2*BN` | `i = 0,64,...,448` = 8 | `i = 31,95,...,479` = 8 | `sg + 32m`, `m = 0..15` = **16** | **none** |
| NEW 4-way | `i + 3*BN < N; i += 4*BN` | `i = 0,128,256,384` = 4 | `i = 31,159,287,415` = 4 | `sg + 32m`, `m = 0..15` = **16** | **none** |

`32 simdgroups x 16 keys = 512 = N` in both cases, and in both cases the loop
is followed immediately by `if (lane == 0) { max_scores[sg] = ... }` with no
remainder loop at all - I read the post-loop text to confirm this, because a
4-way unroll that left a scalar tail would have been a far more interesting
finding. It does not. B is a *pure* unroll-depth change: identical loads,
identical FLOPs, identical output, only the instruction schedule and the live
register set differ.

**Both mechanisms buy instruction-level parallelism with registers, and both
are paid for by lanes that do not use them.**

| | mechanism A (router) | mechanism B (sliding attn) |
|---|---|---|
| extra live state per lane | `thread vec<bfloat,4> laguna_pf[4]` = 16 bfloat = **32 B = 8 GPRs** | `pipe_kc[4]`+`pipe_kd[4]` (8 float) + `pipe_vc0..3`,`pipe_vd0..3` (8 bfloat) = **48 B = 12 GPRs** |
| held across | a **threadgroup barrier** and the whole RMS reduction | straight-line code inside one iteration |
| declared for | all 16 simdgroups | all 32 simdgroups |
| actually filled for | `simd_group < active_simd_groups` = **8 of 16** | all 32 |
| threadgroup | 512 threads | 1024 threads |

A's asymmetry is worth naming explicitly: `laguna_pf[4]` is declared outside
the `if (simd_group < active_simd_groups)` guard, so every one of the 16
simdgroups pays the allocation while only 8 ever populate it, and the value
must survive a `threadgroup_barrier` where the compiler cannot rematerialise
it. That is the most expensive place in the kernel to hold 8 registers.

**Both dispatches are exactly 32 threadgroups, which is the crux.** Read
straight off `dispatch.tsv`:

| kernel | grid (threads) | threadgroup | threadgroups/dispatch | calls/step |
|--------|----------------|-------------|-----------------------|------------|
| A `residual_rms_router` | `16384x1x1` | `512x1x1` | **32** | 39 |
| B `sliding_fused_attn_ring_v1` | `32768x1x1` | `1024x1x1` | **32** | 30 |

For B the 32 is structural: the output is `bfloat16[1,64,1,128]`, the kernel
computes `head0 = pair_tg * 2` so each threadgroup owns a *pair* of query
heads, and 64 heads / 2 = 32 threadgroups.

Now compare the two machines:

| host | GPU cores | 32 TGs maps to |
|------|-----------|----------------|
| this **M4 Pro** | **20**, measured (`system_profiler SPDisplaysDataType` -> `Total Number of Cores: 20`) | **two waves, 20 then 12** |
| ranked **M5 Max** | not measured here; the Max tier has been >= 32 for several generations | **one wave, <= 1 TG/core**, with idle cores if the count exceeds 32 |

I deliberately do not assert an exact M5 Max core count, because I have no
access to that host and the argument does not need one. It needs only
`cores >= 32`, which holds for every Max-tier part, and that is enough to put
the two machines in different regimes.

This is not a power problem, it is a validity problem. The only thing either
mechanism changes is register pressure and instruction scheduling, and the cost
of register pressure is a function of how many threadgroups a core is trying to
keep resident. On a >= 32-core ranked host each core hosts at most one
threadgroup of this dispatch, so spare registers are nearly free and extra
in-flight loads are close to pure win - unless the allocator spills. On this
20-core M4 Pro the same dispatch runs two waves with cores contending, so the
same register delta is penalised differently and can plausibly change sign.
This is exactly the failure mode `AGENTS.md` warns about ("threadgroup geometry
can also change sign across core counts"), and it applies to *both* survivors
rather than to one of them.

The consequence for the advisor is concrete: **the M4 probe in section 8 is not
merely underpowered, it is structurally uninformative for ranking A against B
on the M5.** A single paired M5 receipt with
`DARKBLOOM_ROUTER_WEIGHT_PREFETCH=0` would settle A completely, because rung 1
proved that flag restores OLD's router kernel bit-exactly; nothing short of an
M5 measurement will settle B.

## 8. Optional causal probe - paired A/B of mechanism A on M4

Design, fixed in advance: alternate
`DARKBLOOM_ROUTER_WEIGHT_PREFETCH=1` (shipped NEW default) and `=0` legs of
`./benchmark.sh --local-iterate` on the NEW assignment worktree - one binary,
one metallib, one host session, cool gate enabled, first leg discarded as
warm-up, arms alternating so thermal drift is first-order cancelled
(`research/r103b/scripts/ab_router_prefetch.sh`).

Expected effect size sets the power ceiling in advance. The pool table's
`m4_us_split1` column is exactly 2x `m5_us` for both families, so if A carried
the entire +20.15 us M5 `T` regression it would show as roughly **+40.3 us out
of ~12,957 us/token on this host - 0.31 %**. This is a genuinely underpowered test
on an M4 Pro and is reported as directional evidence only. Kernel *reachability*
is not in doubt: this host does compile and dispatch both
`..._rpg8_keys_v1_pf1_...` and the 4-way sliding kernel, so unlike an `_nax`
prefill question the M4 is at least executing the same kernel family as the
ranked M5.

## 9. Riders

### 9.1 QKV `_idx_v1` / `_ns1` dormancy - RESOLVED

Scanning `library_index.tsv` and `dispatch.tsv` across all three arms:
**zero `_idx_v1` and zero `_ns1` kernels are ever compiled or dispatched** at
either revision. The only QKV and O-projection kernels that appear are

```
custom_kernel_laguna_decode_nvfp4_qkv_h{48,64}_r1_v1_lm1_pw1_se1_sd1
custom_kernel_laguna_oproj_act_h{48,64}_v1_lm1_pw1_sc1_se1
```

Both variants are therefore dormant, on JIT-reachability evidence rather than
source reading. `_idx_v1` is additionally gated on affine-INT8-g32 QKV, which
the NVFP4 checkpoint never selects. Cost: well under the 1 h drop threshold.

### 9.2 `f720e9e7` rule-74 JIT neutrality - ANSWERED, no third tree needed

The advisor's 2026-08-09T21:28Z comment asked for an *optional third tree*:
this base with `f720e9e7`'s `Vendor/` comment deletions reverted, corpus-dumped
and diffed against the base corpus, to close the rule-74 doubt that
`sdpa_vector.h`, `quantized.cpp`, `jit_kernels.cpp` and `matmul.cpp` embed
Metal source verbatim into JIT text.

**That tree already exists - it is my OLD arm.** `f720e9e7` is an ancestor of
NEW (`0f6862d0`) and **not** of OLD (`30f752df`), and for all four files the
OLD->NEW range delta is *exactly* `f720e9e7`'s own delta, i.e. no other commit in
the range touches them:

| file | OLD->NEW range | `f720e9e7` alone |
|------|---------------:|-----------------:|
| `sdpa_vector.h` | +0 / -294 | +0 / -294 |
| `quantized.cpp` | +10 / -405 | +10 / -405 |
| `jit_kernels.cpp` | +6 / -94 | +6 / -94 |
| `matmul.cpp` | +19 / -227 | +19 / -227 |

So OLD is "comments present" and NEW is "comments deleted", and rung 1 is
already the requested experiment - over the *entire* 103-library corpus rather
than only the kernels those four files feed.

**Reachability first** (the advisor's 5-minute check), from
`library_index.tsv` + `dispatch.tsv`:

| source file | JIT libraries in corpus | prefill dispatches | steady-state decode dispatches |
|---|---:|---:|---:|
| `quantized.cpp` + `jit_kernels.cpp` (nvfp4 / affine quant) | 5 | 274 | **0** |
| `matmul.cpp` + `jit_kernels.cpp` (steel gemm / gemv) | 6 | 312 | **0** |
| `jit_kernels.cpp` (steel attention) | 1 | 0 | **0** |
| `sdpa_vector.h` | **0** | - | - |

`sdpa_vector.h` compiles **no** JIT library in the scored window at all - its
SDPA path is AOT, and #548 already proved the metallib bit-identical, so for
that file the answer is *not applicable*. The other three **are** rule-74 live:
12 of the 103 libraries carry their embedded text. They are dispatched heavily
in prefill and in decode step 0, and **zero times in every steady-state decode
step** (per-step rule-74 dispatch count is 0 for steps 1-5; step 0 has 415).

**Verdict: byte-identical.** All 12 of those libraries have identical sha256 of
final MSL text between OLD and NEW - 0 differing, 0 one-sided. The only two
libraries that differ anywhere in the 103-library corpus are mechanisms A and B,
both emitted from `LagunaRuntimeModel.swift`, neither touched by `f720e9e7`.

This is the advisor's first branch: **`f720e9e7` is emitted-code-neutral on the
JIT path too.** The last rule-74 doubt about it is closed, for prefill as well as
decode, and the only channel it could still act through is host binary layout
(`#line`/`__LINE__`/`__FILE__` literals and code placement in the Swift/C++
binary), which #548 explicitly declined to claim. Cost: ~10 minutes, no third
build, reusing `research/nezuko-r99b/restore-comments.sh` was unnecessary.

Coverage caveat: this closes the question for every kernel the scored window
actually compiles. A JIT kernel that no scored workload reaches is not covered
and also cannot cost scored time.

## 10. Null verdicts

| null | verdict | evidence |
|------|---------|----------|
| **N-A** no textual/dispatch difference | **REFUTED** | 2 of 103 kernels differ in final MSL text (rung 1) |
| **N-B** difference is only the file fold | **REFUTED** | the fold carries two real MSL payloads; 27 of 32 changed files are comment-only, but `LagunaRuntimeModel.swift` is not |
| **N-C** dispatch-only | **REFUTED** | per-step dispatch delta 0; 408 vs 408 rows identical in kind/grid/threadgroup/buffer shapes, differing only in a kernel name |
| **N-D** diffuse (>8 kernels) | **REFUTED** | exactly 2 kernels differ |

## 11. Threats to validity

- **Host.** Everything here is measured on an M4 Pro / 48 GiB, but rungs 0-2 are
  *textual and structural*, not timing: the MSL corpus and the dispatch trace are
  properties of the code the runtime emits, and the M5 emits the same text from
  the same sources for these JIT kernels. Only section 8's A/B is a timing claim,
  and it is labelled directional.
- **Residual channel not excluded.** Rungs 1-2 bound the *GPU* difference to A
  and B and the *dispatch* difference to zero. They do not bound host-side CPU
  and encode work: the fold also narrowed six symbols from `internal` to
  `private` and merged two files into one. That can change Swift specialisation.
  Its expected sign is *faster*, not slower, and 408 identical dispatches per
  step leave little room, but it is not measured here.
- **Trace truncation.** The last 4 dispatch rows are lost to an unflushed write
  at worker exit. Verified by `od -c`; it affects only the final partial decode
  step and no per-step conclusion.
- **Instrumented build.** The traced binaries carry the `device.cpp` hook. It
  cannot change kernel text (the hook runs after the source string is built) or
  dispatch structure (it only observes), but the traced binaries are not the
  binaries used for any timing claim.
- **Interaction.** A and B are separately restorable in principle, but this study
  never ran a 2x2. If the regression is an interaction (e.g. both raising
  register pressure and shifting how the two kernels co-schedule), a
  single-mechanism revert would only partly recover it.

## 12. What the advisor can do with this (not implemented here)

Ordered by cost:

1. **One paired M5 measurement with `DARKBLOOM_ROUTER_WEIGHT_PREFETCH=0`.** Zero
   code change, bit-exact OLD router, everything else at NEW. If it recovers
   ~19 us, mechanism A is convicted and the fix is a one-line default change
   (`lagunaRouterWeightPrefetch` default `1` -> `0`) - which costs **negative**
   editable bytes and clears `LagunaRuntimeModel.swift`'s 5,052-byte headroom
   problem rather than adding to it. If it recovers ~0, A is exonerated and B is
   convicted by elimination.
2. **If B is implicated**, revert the sliding-attention loop stride at
   `LagunaRuntimeModel.swift:1639` (`i += 4 * BN` -> `i += 2 * BN` plus the
   `_c`/`_d` temporaries). Worth pairing with the observation that PR #565 left
   the sibling `full_fused_attn_grow_v1` at 2-way, so a 2-way sliding kernel is
   not an exotic configuration.
3. **A cheaper repair for A than switching it off, if A is convicted.**
   `thread vec<bfloat,4> laguna_pf[4]` is declared *outside* the
   `if (simd_group < active_simd_groups)` guard, so all 16 simdgroups of the
   512-thread threadgroup pay the 8-register allocation while only 8 of them
   ever populate it, and the value has to survive a `threadgroup_barrier`.
   Sinking the declaration into the guarded scope, or prefetching 2 blocks
   instead of 4, keeps most of the latency hiding at half the register cost.
   I did **not** measure this - it is a hypothesis generated by reading the MSL,
   and it only becomes worth trying after an M5 receipt convicts A.
4. **Structural lesson.** Both A and B merged on individually positive receipts
   and together net to a regression. Since rung 1 proves nothing else on the
   scored surface changed across ~250 commits, at least one of those two receipts
   was inside the noise floor. A restore flag - the thing A has and B does not -
   is what makes a landed kernel-text change re-testable a hundred commits later
   for the price of one measurement. That is cheap insurance worth making a
   convention.

## 13. Reproduction

```bash
# 0. two trees (see research/r103-armr-build-notes.md for the full recipe)
git worktree add --detach .mlxfast-private/r103b-old 30f752df
git worktree add --detach .mlxfast-private/r103b-new 0f6862d0
git -C .mlxfast-private/r103b-old apply research/r103b/scripts/trace.patch
git -C .mlxfast-private/r103b-new apply research/r103b/scripts/trace.patch
# build mlxfast-runtime-worker with --scratch-path .build-worker in each tree,
# copy mlx.metallib + .fingerprint next to each worker

# 1. capture MSL corpora and dispatch traces for all three arms
ARMS="old new new_pf0" STEP=5 research/r103b/scripts/run_all_traces.sh

# 2. differentials
python3 research/r103b/scripts/compare_msl.py      old new
python3 research/r103b/scripts/compare_dispatch.py old new
python3 research/r103b/scripts/seqalign.py         old new
python3 research/r103b/scripts/steps.py            old new

# 3. static classification of the 32-file diff
python3 research/r103b/scripts/comment_strip_diff.py 30f752df 0f6862d0

# 4. working-set digests
research/r103b/scripts/working_set_manifest.sh 30f752df 0f6862d0

# 5. rule-74 rider: is f720e9e7 emitted-code-neutral on the JIT path?
python3 research/r103b/scripts/rule74_check.py "$PWD"

# 6. optional M4 A/B of mechanism A
LEGS=20 research/r103b/scripts/ab_router_prefetch.sh
python3 research/r103b/scripts/ab_summarize.py /tmp/r103b/ab/summary.tsv
```

---

## § Reply

**Rungs 0, 1, 2 and 3 are complete, and the differential is unusually clean:
across ~250 commits only two kernels change their final MSL text, and the
per-decode-step dispatch delta is exactly zero.**

- **Rung 0 PASS.** OLD `30f752df` and NEW `0f6862d0` both build and produce
  token-identical, top-5-logit-identical output (`golden_hash
  b9509697c08a2cf3...`). Working-set digests are in
  `research/r103b/artifacts/working-set-manifest.tsv`; the reusable recipe -
  including the three harness traps (worker stderr is discarded, the worker env
  is a `DARKBLOOM_*`/`MLX_*` allowlist, and a nested `weights` symlink produces a
  misleading `exit_status=15`) - is in `research/r103-armr-build-notes.md` for
  frieren and anybody else standing up an arm-R tree.
- **Rung 1.** 103 JIT libraries at both revisions; **101 byte-identical, 2
  changed**: (A) `residual_rms_router_..._rpg8_keys_v1` gains a `_pf1` suffix and
  a router-weight prefetch hoisted across the RMSNorm reduction (PR #558), and
  (B) `sliding_fused_attn_ring_v1` widens K/V pipelining 2-way -> 4-way at MSL
  line 1280 (PR #565). Unified diffs are committed. 27 of the 32 changed source
  files are comment/whitespace-only byte reclamation (PR #548), including **all**
  AOT `.metal`/`.h` and vendored MLX C++ - so no metallib change is involved.
- **Rung 2.** 408 dispatches per decode step at both revisions. Positional
  comparison of a complete step over `(kernel, kind, grid, threadgroup, buffer
  shapes+dtypes)`: 39 of 408 rows differ **and only in the kernel name**; after
  canonicalising the `_pf1` rename the blocks are equal. Whole-trace alignment
  has exactly one non-equal opcode, a 4-row tail lost to an unflushed trace write
  at worker exit (confirmed with `od -c`). **Priced at +0.3 us/dispatch this is
  `0 x 0.3` = +0.00 us/step - dispatch contributes 0.00 % of the 20.149 us hole,
  so N-C is dead.** N-A, N-B and N-D are dead too.
- **Rung 3, repriced against `T` = 20.149 per your 21:47Z note.** Both survivors
  are latency-regime with room to hide the delta: T3a sliding attn 318.0 us/step
  (30 calls, 32.4 % of M5 peak) and T1a router 156.4 us/step (39 calls, 42.8 % of
  peak); +20.149 us is **+4.25 %** of their combined 474.4 us, which is **11.45 %**
  of arm R's `T` = 4141.540. A-alone would be **+12.88 %** on T1a, B-alone
  **+6.34 %** on T3a. **Mechanism A is bit-exactly restorable with no code
  change**: `DARKBLOOM_ROUTER_WEIGHT_PREFETCH=0` reproduces the OLD router
  kernel's name and MSL text exactly, and its dispatch trace is identical to OLD
  in all 11,247 rows. Mechanism B has no flag and has never been re-measured
  since it landed.
- **Neither mechanism changes work; both are occupancy bets (§7.2).** I walked
  B's loop bounds exhaustively: with `i = sg` striding by `BN = 32`, the OLD
  2-way loop runs 8 iterations and the NEW 4-way loop runs 4, and both cover
  exactly the same 16 key slots `sg + 32m`, m = 0..15, for all 32 simdgroups
  (32 x 16 = 512 = `N`). There is **no tail or remainder loop in either
  variant** - the loop is followed immediately by the `max_scores[sg]` write.
  So B is a pure unroll-depth change and A is a pure prefetch: the only thing
  either can buy or lose is latency hiding versus register pressure. Per lane,
  A costs **+32 B (8 GPRs)** held across a threadgroup barrier in a 512-thread
  TG, and B costs **+48 B (12 GPRs)** straight-line in a 1024-thread TG. Both
  dispatch **exactly 32 threadgroups** (A: 16384/512; B: 32768/1024, structural
  because `head0 = pair_tg * 2` and 64/2 = 32).
- **That 32-threadgroup number is why I want the M5 leg and not a local
  verdict.** This host is a 20-GPU-core M4 Pro, so 32 threadgroups is two waves
  (20 then 12); any >= 32-core Max-tier ranked host runs one wave at <= 1 TG per
  core. Register pressure that costs nothing at one TG per core can cost a
  second resident TG in the two-wave regime and vice versa, so the local A/B in
  §8 is **structurally uninformative** for ranking A against B, not merely
  underpowered - exactly the "threadgroup geometry can change sign across core
  counts" case in `AGENTS.md`. I am labelling it directional only.
- **Rider 1 resolved.** Neither `_idx_v1` nor `_ns1` QKV kernels are compiled or
  dispatched at either revision - dormant on reachability evidence, not just on
  reading the source.
- **Rider 2 (`f720e9e7`, your 21:28Z note): answered without a third tree, and
  the answer is your first branch - byte-identical.** I did not need to build
  one, because `f720e9e7` is an ancestor of NEW and *not* of OLD, and for all
  four rule-74 files the OLD->NEW range delta equals `f720e9e7`'s delta exactly
  (`sdpa_vector.h` -294, `quantized.cpp` +10/-405, `jit_kernels.cpp` +6/-94,
  `matmul.cpp` +19/-227). My OLD arm *is* the comments-restored tree, and rung 1
  already diffs it over all 103 libraries rather than just those four files.
  Taking your 5-minute reachability check first: `sdpa_vector.h` compiles **zero**
  JIT libraries in the scored window (AOT only, so *not applicable*), while
  `quantized.cpp`, `matmul.cpp` and `jit_kernels.cpp` feed **12** of the 103
  (5 nvfp4/affine-quant, 6 steel-gemm/gemv, 1 steel-attention). **All 12 have
  identical MSL sha256 between OLD and NEW.** Those 12 are dispatched 586 times
  in prefill and 415 times in decode step 0, and **zero times in every
  steady-state decode step**. So `f720e9e7` is emitted-code-neutral on the JIT
  path for prefill as well as decode; the only channel it can still act through
  is host binary layout, which #548 explicitly declined to claim. Artifact:
  `research/r103b/artifacts/rule74_f720e9e7_jit_neutrality.txt`.

**My recommendation, which is one measurement and zero code:** run a paired M5
leg with `DARKBLOOM_ROUTER_WEIGHT_PREFETCH=0`. It convicts or exonerates A
outright, and by elimination it does the same for B. If A is the culprit, the
fix is flipping one default - which *removes* editable bytes rather than adding
to `LagunaRuntimeModel.swift`'s 5,052-byte headroom. If A is clean, B's 4-way
loop at `LagunaRuntimeModel.swift:1639` is the remaining suspect and belongs to
whoever owns the attention path next.

I did **not** implement either revert - the assignment asked for the mechanism,
not the fix - and I took **zero official receipts**. The merged diff is
research-only: no submitted-surface byte changed.
