# R103-B: what actually changed in the emitted and dispatched code across three revisions

Assignment `maple-r103-b-kernel-text-differential`, revision `r103-b-rev1`,
PR #572. Research-only: **zero submitted-surface bytes changed**.

> **Scope note after advisor feedback `r103-b-fb3` (2026-08-09T22:22Z).** The
> advisor withdrew the 20.149 us/step target: receipt-to-receipt noise on
> *byte-identical code* is sd(`T`) = 12.079-14.272 us/step, so the frontier-ArmR
> gap is z ~ 1.0-1.2 and no contrast in the receipt corpus survives its own
> 95 % CI. **Rung 3's absolute us attribution is withdrawn accordingly.** This
> document is a **mechanism inventory**, not a cost model. Where an ordering of
> the survivors by plausible cost is still useful it is kept and labelled as an
> ordering only; every "explains X % of the hole" figure has been struck.
> Section 7.0/7.1 are retained, struck through, purely so the arithmetic is
> auditable and nobody re-derives it.

## 0. Verdict in one paragraph

Three revisions were dumped and diffed:

| tag | commit | what it is |
|---|---|---|
| **OLD** | `30f752df` | arm-R receipt `7ce1262d`'s tree |
| **MID** | `e17bdeb1` | frontier receipt `e08d759f`'s tree (`Sources/` == `a4d3b8dc`) |
| **NEW** | `0f6862d0` | the advisor base = **MID + R3** (#558, LRM `+102/-11`), never submitted |

Across the whole OLD -> NEW range the runtime compiles and dispatches **exactly
the same 103 Metal libraries in the same order with the same grids,
threadgroups and buffer shapes**; the per-decode-step dispatch count is **408 at
every revision** and the traces are positionally identical for all 11,243
compared dispatches. Only **two** kernels change their final MSL text, and the
three-way dump separates them cleanly onto the two receipt intervals:

| # | kernel | introduced by | interval | change |
|---|--------|---------------|----------|--------|
| **A** | `custom_kernel_laguna_residual_rms_router_bf16_2048_rpg8_keys_v1` | R3 / PR #558 | **MID -> NEW** | router-weight prefetch hoisted across the RMSNorm reduction; kernel gains a `_pf1` suffix |
| **B** | `custom_kernel_laguna_sliding_fused_attn_ring_v1` | PR #565 | **OLD -> MID** | K/V software pipelining widened 2-way -> 4-way |

The separation is clean in both directions and was measured, not inferred:

| comparison | libraries | byte-identical | differing | only-A | only-B | verdict |
|---|---|---|---|---|---|---|
| **OLD vs MID** | 103 / 103 | **102** | **1** (B) | 0 | 0 | mechanism **B** alone |
| **MID vs NEW** | 103 / 103 | 102 | 0 | **1** (A, old name) | **1** (A, `_pf1`) | mechanism **A** alone |
| **MID vs `new_pf0`** | 103 / 103 | **103** | 0 | 0 | 0 | **bit-identical** |
| **NEW vs NEW (A/A)** | 103 / 103 | **103** | 0 | 0 | 0 | control passes |

That separation matters for frieren: the **OLD<->MID** interval - the receipt
pair everyone has been arguing about - contains **exactly one** emitted-code
change, mechanism B. Mechanism A is **not** in that interval at all; it is R3 in
isolation, which has never been submitted post-rebase. And the third row is the
sharpest single fact in this report: **R3's entire effect on the emitted code is
gated behind one environment variable** - at `DARKBLOOM_ROUTER_WEIGHT_PREFETCH=0`
the NEW binary compiles a corpus that is byte-identical to MID's across all 103
libraries.

Everything else in the 32-file OLD->NEW source diff is comment/whitespace-only
byte reclamation or offline transform code that provably does not touch the
scored runtime. Preregistered nulls N-A, N-B, N-C and N-D are all refuted.

Both survivors are the *same class* of change - extra live registers bought for
instruction-level parallelism - and both dispatch exactly **32 threadgroups**,
so on a >= 32-core ranked host they run one wave at <= 1 threadgroup per core
while on this 20-core M4 Pro they run two. Section 7.2 works this out from the
kernel text and concludes that an M4 probe cannot rank A against B even in
principle. Neither mechanism changes the amount of work: I verified the 4-way
unroll covers exactly the same 16 key slots per simdgroup as the 2-way loop and
leaves **no tail loop**, for every simdgroup index.

Mechanism A is **bit-exactly restorable with no code edit**:
`DARKBLOOM_ROUTER_WEIGHT_PREFETCH=0` at NEW reproduces MID's whole 103-library
corpus byte for byte, and its 11,247-row dispatch trace matches OLD's with zero
non-equal alignment opcodes. So if a rig is ever pointed at this, A costs one
environment variable and B costs a one-line source revert at
`LagunaRuntimeModel.swift:1639`.

**Zero official receipts were consumed.** Everything here is static text plus a
local instrumented `correctness-trace`, and every arm reproduced the public
golden token-for-token.

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
| `old` | `30f752df` | n/a (flag does not exist) | arm-R receipt `7ce1262d`'s revision |
| `mid` | `e17bdeb1` | n/a (flag does not exist) | frontier receipt `e08d759f`'s revision |
| `new` | `0f6862d0` | `1` (shipped default) | current advisor base = MID + R3 |
| `new_pf0` | `0f6862d0` | `0` | isolates mechanism A inside one binary |
| `new_aa` | `0f6862d0` | `1` | **A/A control** - `new` dumped a second time |

Three detached `git worktree`s under the gitignored `.mlxfast-private/` hold
OLD, MID and NEW simultaneously. One trusted CLI drives all three workers (the
CLI sources are byte-identical across the range). The full recipe, including
three harness traps that cost an hour, is written up for reuse in
[`research/r103-armr-build-notes.md`](r103-armr-build-notes.md).

**MID is the right third point, and MID -> NEW is R3 in isolation.**
`e17bdeb1` is the merge of PR #565; it is an ancestor of `0f6862d0`, and
`git diff --numstat e17bdeb1 0f6862d0 -- Sources Vendor Package.swift
Package.resolved benchmark.json` returns **exactly one file**,
`Sources/MLXFastModel/LagunaRuntimeModel.swift` at `+102/-11`, which is R3
(PR #558). So the three-way dump is a genuine interval decomposition of the
OLD -> NEW range, not a re-slicing of the same diff.

**Staleness guard.** The advisor warned (rule 58, from nezuko #575) that a naive
incremental rebuild silently reuses a stale object and produces a false PASS.
Each worker was built in its own `--scratch-path .build-worker`, and the build
script then asserted a positive detector before any dump: the literal
`DARKBLOOM_ROUTER_WEIGHT_PREFETCH` exists in the R3 source and in **neither**
older revision, so `strings -a <worker> | grep -c` must be zero at OLD and MID
and non-zero at NEW. Observed:

```
r103b-old: DARKBLOOM_ROUTER_WEIGHT_PREFETCH strings=0  sha256=9fce9f4c4cd3963e  bytes=49145848
r103b-mid: DARKBLOOM_ROUTER_WEIGHT_PREFETCH strings=0  sha256=725cc9ca676d3b0e  bytes=49240232
r103b-new: DARKBLOOM_ROUTER_WEIGHT_PREFETCH strings=1  sha256=26c6dc830d0f1907  bytes=49257896
```

Three distinct binaries, three distinct sizes, detector correct at all three.

**Metallib control.** The same `mlx.metallib` (158,502,072 B) is placed in all
three worktrees. This is sound and is itself part of the result: every AOT
`.metal`/`.h` source that differs across the range differs by comments and
whitespace only (section 4), so the three revisions would compile the same
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
identical for all five arms.

## 3. Rung 0 - all three trees build and all five arms agree, PASS

All five dumps are **token-identical and top-5-logit-identical**:

```
case longcopy-gate-english-512   step 5   matched_prefix_steps 6
generated_prefix [5991, 509, 902, 5991, 509, 902]   actual=expected=902 (rank 1)
top_logits [(902,24.125),(340,18.25),(5991,16.875),(4423,16.75),(750,16.625)]
top_logit_margin 5.875   golden_hash b9509697c08a2cf3...
```

```
[old]     rc=0  msl=103  dispatch=11247
[mid]     rc=0  msl=103  dispatch=11247
[new]     rc=0  msl=103  dispatch=11243
[new_pf0] rc=0  msl=103  dispatch=11247
[new_aa]  rc=0  msl=103  dispatch=11243
```

The `11247` vs `11243` split is **not** a behavioural difference; it is a
byte-quota truncation artifact, resolved quantitatively in section 6.

Working-set digests: `research/r103b/artifacts/working-set-manifest.tsv`
(82 rows). Git index-tree digest over the scored surface:

| | OLD | NEW |
|---|---|---|
| tree sha256 | `fe3d95764c6fdf92114267d589e8018e4f515133495fbbf2d980732048fcdcdb` | `f65b09e66f716ee14f3048b018401c2d37669d3f09b2c9e784339436b7f54a25` |
| `LagunaRuntimeModel.swift` | `119a17bc...` 398,661 B | `1e0c7d43...` 519,236 B |
| `LagunaRuntimeLayers.swift` | `b088a675...` 112,578 B | *(deleted)* |
| worker binary | 49,145,848 B | 49,257,896 B (MID: 49,240,232 B) |
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
the Metal compiler, for all arms
(`research/r103b/artifacts/msl_sha256_{old,mid,new,new_pf0}.tsv`).

### 5.0 Method, and why this dumper produced a corpus where nezuko's did not

Rule 58: nezuko's #575 reports that **instrumenting `Device::get_library`
produced an empty corpus after two full benchmark runs**, and she abandoned the
approach. I hit no such wall, and the reason is the hook site.

`get_library` is a *cache lookup*. On the paths Laguna actually uses it is
either not the function that receives the source text, or it returns an
already-cached `MTL::Library` without ever seeing MSL. The text only exists as a
string inside **`Device::build_library_`**
(`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp:622`), which is
where `MTL::CompileOptions` is configured (`setFastMathEnabled(false)`,
`setLanguageVersion(get_metal_version())`) and where `newLibrary` is called.
That is where I hooked, and it yields all 103 libraries on the first run.
The dispatch hook is in the same translation unit, on the encoder path.

The instrumentation is `research/r103b/scripts/trace.patch` (+148/-4) and it
touches **only** `device.cpp` / `device.h`, which are **outside**
`benchmark.json`'s `editablePaths`. It is applied in throwaway detached
worktrees under gitignored `.mlxfast-private/` and never in the assignment tree,
so it cannot reach the merged diff (verified: `git diff 0f6862d0 -- Sources
Vendor Package.swift Package.resolved benchmark.json` is empty).

**Scope limits I am claiming explicitly, per fb3:**

- **Device.** Every dump in this document was taken on an **Apple M4 Pro,
  20 GPU cores, 48 GiB** (`system_profiler SPDisplaysDataType`). MLX selects
  kernel variants by Apple GPU generation; an M4 Pro reports generation 16 and
  **does not select the `_nax` variants the ranked M5 uses**. Therefore: *this
  corpus is silent about `_nax` kernels.* A change confined to an `_nax`
  variant would be invisible here and this document must not be read as "no
  change" for that family. What I can say is that the *non-`_nax`* corpus is
  103 libraries at every revision and that the two differences found are in
  custom Laguna kernels emitted from `LagunaRuntimeModel.swift`, which are
  generation-independent string interpolations.
- **Aliasing.** Libraries are keyed by MLX's own library name, which for the
  Laguna custom kernels already encodes the specialisation constants (e.g.
  `..._h64_r1_v1_lm1_pw1_se1_sd1`). A name that appears in one revision and not
  the other is reported as `only_old` / `only_new` rather than being silently
  paired, which is exactly how mechanism A's `_pf1` rename surfaced.
- **Host-side selection.** A text diff alone cannot see a change in *which*
  kernel is chosen. That is why rung 2 (section 6) is a full dispatch trace and
  is treated as co-equal evidence, not a rider: it compares the ordered
  sequence, the counts, the grid and threadgroup geometry, and the bound buffer
  shapes and dtypes, position by position.

### 5.1 A/A control - the same revision dumped twice is byte-identical

Before reporting any A/B difference, the NEW tree was dumped **twice** from the
same binary in two separate worker processes (`new` and `new_aa`). If library
filenames, instantiation order, or the emitted text were nondeterministic, this
control would show it.

```
# MSL corpus new vs new_aa
libraries new=103 new_aa=103
common=103  byte_identical=103  differing=0
only_new=0  only_new_aa=0

# dispatch trace new vs new_aa
total dispatches: new=11244  new_aa=11244  delta=0
alignment (geom=False): len 11243 vs 11243, non-equal opcodes = 0
alignment (geom=True):  len 11243 vs 11243, non-equal opcodes = 0
kernels whose (kind,grid,group,args) multiset differs: 0
```

**The A/A control is clean on both axes.** 103/103 libraries byte-identical,
and 11,243/11,243 dispatch rows identical in name, kind, grid, threadgroup and
bound-buffer shape/dtype, in order. Both dumps also produced the *same*
truncation point, which is what section 6 uses to close out the `-4` rows.

So the measurement floor for this instrument is exact equality: **any**
difference reported below is a real difference in the emitted or dispatched
code, not dumper noise. This is the control fb3 asked for, and it is the reason
I am willing to state the rung-1 and rung-2 results without an error bar - they
are not sample statistics.

Artifacts: `research/r103b/artifacts/msl_new_vs_new_aa.txt`,
`disp_new_vs_new_aa.txt`, `seq_new_vs_new_aa.txt`, `msl_sha256_new_aa.tsv`.

### 5.2 The interval decomposition: B is OLD -> MID, A is MID -> NEW

This is the part fb3 asked for. Both intervals are reported.

```
# MSL corpus old vs mid                 # MSL corpus mid vs new
libraries old=103 mid=103               libraries mid=103 new=103
common=103                              common=102
byte_identical=102  differing=1         byte_identical=102  differing=0
only_old=0  only_mid=0                  only_mid=1  only_new=1
```

| interval | what differs | mechanism |
|---|---|---|
| **OLD -> MID** (arm-R receipt -> frontier receipt) | one library differs in text: `custom_kernel_laguna_sliding_fused_attn_ring_v1` 60,780 B `39412f51db8d4eb3` -> 64,866 B `4d12c05ab71ab44e` | **B alone** |
| **MID -> NEW** (frontier receipt -> advisor base, = R3) | one library is renamed and rewritten: `..._rpg8_keys_v1` 52,359 B `19d8e9fadbfafafa` -> `..._rpg8_keys_v1_pf1` 53,264 B `dd7a9210c57f86f7`; the other 102 are byte-identical | **A alone** |

Both intervals are *single-mechanism*. Nothing else in either interval reaches
the emitted code. In particular the PR #548 byte-reclamation pass, which lives
entirely in the OLD -> MID interval and touches 27 files, contributes **zero**
bytes of difference to any of the 103 compiled libraries - which is the
independent confirmation of section 4's comment-stripper argument.

**And R3's emitted-code effect is entirely flag-gated:**

```
# MSL corpus mid vs new_pf0
libraries mid=103 new_pf0=103
common=103  byte_identical=103  differing=0
only_mid=0  only_new_pf0=0
```

At `DARKBLOOM_ROUTER_WEIGHT_PREFETCH=0` the NEW binary - a different executable,
built from different sources, 17,664 bytes larger - compiles a corpus that is
byte-identical to MID's across **all 103 libraries**. So R3 (`+102/-11` lines of
Swift) changes the GPU program in exactly one place, behind exactly one switch.

Artifacts: `msl_old_vs_mid.txt`, `msl_mid_vs_new.txt`, `msl_mid_vs_new_pf0.txt`.

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

| segment | old | mid | new | new_pf0 | new_aa | delta |
|---------|----:|----:|----:|--------:|-------:|------:|
| prefill | 7334 | 7334 | 7334 | 7334 | 7334 | **0** |
| decode step 0 | 1759 | 1759 | 1759 | 1759 | 1759 | **0** |
| decode step 1 | 528 | 528 | 528 | 528 | 528 | **0** |
| decode steps 2-4 | 408 | 408 | 408 | 408 | 408 | **0** |
| decode step 5 (truncated) | 402 | 402 | 398 | 402 | 398 | -4 |

**The step-5 `-4` is fully explained and is not a workload difference.** The
three-revision plus A/A run pins it down exactly:

- every `dispatch.tsv`, at every arm, is **exactly 1,671,168 bytes**
  (= 0x198000, a hard tracer buffer/quota boundary) and every one ends
  **mid-line** with no trailing newline (`od -c`);
- the two independent NEW dumps truncate at the *identical* row, so it is
  deterministic per binary, not random;
- the arithmetic closes: the `_pf1` rename adds 4 characters to each of the
  **236** router dispatch rows in the trace = **944 bytes**, and the 4 rows NEW
  loses occupy **978 bytes** in OLD's file. Spending 944 bytes on longer kernel
  names inside a fixed 1,671,168-byte quota costs you the last ~4 rows. There is
  no other candidate explanation left.

Whole-sequence `difflib` alignment (with the `_pf1` rename canonicalised), run
both with and without grid/threadgroup geometry in the key:

| comparison | lengths | non-equal opcodes | differing `(kind,grid,group,args)` signatures |
|---|---|---|---|
| **OLD vs MID** | 11247 / 11247 | **0** | **0** |
| **MID vs NEW** | 11247 / 11243 | 1 (`delete a[11243:11247]`, the quota tail) | 0 |
| **OLD vs NEW** | 11247 / 11243 | 1 (same quota tail) | 0 |
| **OLD vs `new_pf0`** | 11247 / 11247 | **0** | **0** |
| **NEW vs NEW (A/A)** | 11243 / 11243 | **0** | **0** |

The OLD vs MID row is worth pausing on: mechanism B rewrites 4,086 bytes of one
kernel's MSL and **does not move a single dispatch row**, because it does not
change the kernel's name, its grid, its threadgroup, or any bound buffer. It is
invisible to dispatch-level instrumentation and only a text dump can see it.
Mechanism A is the opposite: it is visible in the trace, but *only* as a name.

Taking the last complete decode step (408 dispatches) and comparing
`(kernel, kind, grid, threadgroup, buffer shapes+dtypes)` row by row:

- **OLD vs MID**: 408 vs 408, positionally aligned, **0 of 408 rows differ**.
- **OLD/MID vs NEW**: positionally aligned, **39 of 408 rows differ, and only in
  the kernel *name*** (`_rpg8_keys_v1` -> `_rpg8_keys_v1_pf1`). Every geometry
  and every buffer shape/dtype is identical. After canonicalising the rename the
  two 408-row blocks are **equal**.
- **OLD vs `new_pf0`**: 11,247 vs 11,247 dispatches, **zero** non-equal
  opcodes, **zero** differing `(kind, grid, group, args)` signatures.

**So the per-decode-step dispatch delta is exactly 0, on every interval.** At
the rule 53/68 rate of +0.3 us/dispatch that is `0 x 0.3 = +0.00 us/step`. This
is the one quantitative statement in the report that survives fb3's retraction,
because its input is an exact integer count and its output is zero: whatever
separates these revisions, **it is not command-buffer or encoder overhead**.

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

## 7. Rung 3 - ranking the two survivors (pricing WITHDRAWN)

> **Withdrawn by `r103-b-fb3`.** Sections 7.0 and 7.1 priced the survivors
> against a 20.149 us/step target. The advisor has since measured
> sd(`T`) = 12.079 us/step (trimmed pooled, dof 14) on **byte-identical code**,
> which makes the frontier-ArmR contrast z ~ 1.0-1.2 - not significant - and
> fern (#576) reached the same verdict independently. **There is no established
> hole to apportion, so no us figure below should be used.** I have left 7.0 and
> 7.1 in place rather than deleting them so the arithmetic stays auditable and
> nobody re-derives it, but every conclusion drawn from them is void. What
> survives rung 3 is: the **restorability** table, the **ordering** below it
> (which is a qualitative exposure/testability ranking, not a cost estimate),
> and section 7.2's static occupancy analysis - none of which depend on a
> measured delta.

### 7.0 ~~The target is `T` = 20.149 us/step, not 19.405~~ (withdrawn; retained for audit)

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

### 7.1 ~~Pool-table budgets~~ (withdrawn; retained for audit)

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

**All six bullets above are void under `r103-b-fb3`.** The only one that
survives is the last, and only because its value is zero and its premise is a
count, not a timing: the per-step dispatch delta is exactly 0, so dispatch
overhead is 0 us regardless of what the true regression is or whether one
exists.

The one *non-timing* fact worth keeping from the pool table is the **regime
classification**, which is a property of the kernels rather than of the
contested contrast:

| id | family | calls/step | bytes/call | M5 GB/s | % M5 peak | regime |
|----|--------|-----------:|-----------:|--------:|----------:|--------|
| **T1a** | residual rms router (**A**) | 39 | 1 MiB | 261.5 | 42.8 | latency |
| **T3a** | sliding fused attn (**B**) | 30 | 2 MiB | 197.8 | 32.4 | latency |

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

### Ranking (ordering only - no cost is attached to either rank)

This is the part of rung 3 the advisor asked me to keep. It orders the two
survivors by *how much of the decode step each kernel family occupies* and by
*how cheaply each can be tested*. It does **not** claim either one costs
anything, and it is not evidence that a regression exists.

1. **B (sliding fused attention)** ranks first on exposure and on risk of an
   un-retested change: 2x the M5 pool residency of A (318 vs 156 us/step of
   occupied step time - a property of the *family*, not of the change), the largest
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

## 8. Optional causal probe - paired A/B of mechanism A on M4: LAUNCHED, THEN CANCELLED

> **Outcome: cancelled at 6 legs (K = 3 pairs). No timing claim is made from
> it.** The machine time was redirected into building the MID tree that fb3
> asked for, which I judged strictly more valuable: the three-revision
> decomposition is a result, whereas an M4 A/B at K = 3 would not have been one
> even if it had run to completion. Section 7.2 independently argues the probe
> was structurally uninformative for ranking A against B, so cancelling it cost
> nothing that section 7.2 had not already written off.

Design, fixed in advance: alternate
`DARKBLOOM_ROUTER_WEIGHT_PREFETCH=1` (shipped NEW default) and `=0` legs of
`./benchmark.sh --local-iterate` on the NEW assignment worktree - one binary,
one metallib, one host session, cool gate enabled, first leg discarded as
warm-up, arms alternating so thermal drift is first-order cancelled
(`research/r103b/scripts/ab_router_prefetch.sh`).

What actually ran, before cancellation at 1567 s
(`research/r103b/artifacts/ab_router_prefetch_cancelled_summary.tsv`, all six
legs `rc=0 correct=True`):

| leg | arm | decode s/token | prefill s/token |
|---|---|---:|---:|
| 01 | `pf1` | 0.0130230544 | 0.0011111346 |
| 02 | `pf0` | 0.0129822262 | 0.0011389356 |
| 03 | `pf1` | 0.0128927796 | 0.0011115600 |
| 04 | `pf0` | 0.0129672253 | 0.0011375085 |
| 05 | `pf1` | 0.0128992197 | 0.0011139014 |
| 06 | `pf0` | 0.0130233304 | 0.0011122929 |

Discarding leg 01 as warm-up leaves **K = 2 usable `pf1` legs and 3 `pf0`
legs**. My own preregistration (section 1) requires K >= 16 before any timing
sentence is written, so **no arm mean, no sign, and no delta is reported from
this table**; it is published only so the machine time is on the record and so a
future run can extend rather than restart it. The spread within the `pf1` arm
alone (0.0128928 to 0.0130231, 1.01 %) is already several times any effect this
probe could have resolved.

That power ceiling was known in advance and is the reason cancelling was cheap.
The pool table's `m4_us_split1` column is exactly 2x `m5_us` for both families,
so if A carried the entire (now-withdrawn) +20.15 us M5 `T` gap it would show as
roughly **+40.3 us out of ~12,957 us/token on this host - 0.31 %**, against a
per-leg spread an order of magnitude larger. Section 7.2 then removed the last
reason to want the number: both survivors dispatch exactly 32 threadgroups, and
this 20-core host runs them in two waves where the ranked M5 runs them in one,
so an M4 A/B could not have ranked A against B even at K = 16.

Kernel *reachability* is not in doubt, and that part of the probe is a real
result: this host does compile and dispatch both `..._rpg8_keys_v1_pf1_...` and
the 4-way sliding kernel, so unlike an `_nax` prefill question the M4 is at
least executing the same kernel family as the ranked M5. Correctness is also on
the record - all six legs passed the harness's own token check with the flag at
both settings, which is independent confirmation of the section 5 finding that
`DARKBLOOM_ROUTER_WEIGHT_PREFETCH=0` is a behaviour-preserving restore.

## 9. Riders

### 9.1 QKV `_idx_v1` / `_ns1` dormancy - RESOLVED

Scanning `library_index.tsv` and `dispatch.tsv` across all five arms:
**zero `_idx_v1` and zero `_ns1` kernels are ever compiled or dispatched** at
any of the three revisions. The only QKV and O-projection kernels that appear are

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
| **N-A** no textual/dispatch difference | **REFUTED** | 2 of 103 kernels differ in final MSL text OLD->NEW (rung 1), and each interval carries exactly one of them: OLD->MID = B alone, MID->NEW = A alone |
| **N-B** difference is only the file fold | **REFUTED** | the fold carries two real MSL payloads; 27 of 32 changed files are comment-only, but `LagunaRuntimeModel.swift` is not. MID->NEW is a single-file `+102/-11` on that file and yields mechanism A on its own |
| **N-C** dispatch-only | **REFUTED** | per-step dispatch delta 0 on *every* interval; OLD vs MID aligns 11247/11247 with 0 non-equal opcodes, MID vs NEW and OLD vs NEW differ only by the shared 4-row trace truncation, and every aligned row matches in kind/grid/threadgroup/buffer shapes, differing only in a kernel name |
| **N-D** diffuse (>8 kernels) | **REFUTED** | exactly 2 kernels differ across the whole OLD->NEW range, 1 per interval, out of 103 |

All four nulls are refuted on three-revision evidence rather than on the single
OLD->NEW comparison, and the A/A control (section 5.1) establishes that the
dumper's zero-difference verdict is a real zero and not an artefact of the
method.

## 11. Threats to validity

- **Device scope - this is an M4 Pro corpus, and it is not the M5 corpus.**
  Every dump in this report was taken on **Apple M4 Pro, 20 GPU cores, 48 GiB,
  Darwin 25.5.0, Metal `LanguageVersion4_0`, Apple GPU generation 16**. Rungs 0-2
  are textual and structural rather than timing, and the M5 emits the same text
  from the same Swift sources for these JIT kernels, so the *identity* of
  mechanisms A and B transfers. What does **not** transfer is any claim of
  *completeness*: the M5 selects `_nax` kernel variants that generation 16 never
  requests, so an `_nax` kernel that changed across these revisions would be
  absent from all five of my corpora and my "exactly 2 of 103 differ" count would
  silently miss it. The two mechanisms I did find are both dispatched on this
  host and are not `_nax`-gated, but "2" is a lower bound on M5, not a proven
  total. Resolving that needs one corpus dump on the ranked M5, which I did not
  run.
- **Corpus-diff blindness, in general (nezuko, #575, rule 58).** nezuko's warning
  applies to my method too, and I only mitigated part of it. A corpus diff cannot
  see (i) M5-only variants, as above; (ii) two libraries that alias to the same
  cache key so only one is ever compiled; or (iii) host-side *selection* changes
  that pick a different already-present kernel without altering any kernel's
  text. Mitigations actually taken: the dispatch trace (rung 2) is reported
  **co-equally** with the corpus rather than as a footnote, and it is exactly
  what would catch (iii) - a selection change would move dispatch rows even with
  a byte-identical corpus, and there are zero such rows per decode step on every
  interval. Case (ii) is bounded by the fact that all five arms compile the same
  103 libraries with the same names. Case (i) is not mitigated and is stated
  above as an open limit.
- **Host, for timing.** Only section 8 is a timing statement, it was cancelled at
  K = 3 pairs, and no number is claimed from it.
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
   code change, bit-exact OLD router, everything else at NEW. This is the only
   probe here that could carry a cost claim at all, and per fb3 it needs enough
   replicates to clear the receipt noise floor (`sd(T)` ~ 12-14 us/step on
   byte-identical code) before a single-receipt difference means anything. If a
   properly replicated pair shows A recovering time, the fix is a one-line
   default change (`lagunaRouterWeightPrefetch` default `1` -> `0`) - which costs
   **negative** editable bytes and clears `LagunaRuntimeModel.swift`'s
   5,052-byte headroom problem rather than adding to it. If it recovers nothing,
   A is exonerated and B is the remaining suspect.
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
# 0. three trees (see research/r103-armr-build-notes.md for the full recipe)
for r in old:30f752df mid:e17bdeb1 new:0f6862d0; do
  git worktree add --detach ".mlxfast-private/r103b-${r%%:*}" "${r##*:}"
  git -C ".mlxfast-private/r103b-${r%%:*}" apply research/r103b/scripts/trace.patch
done
# build mlxfast-runtime-worker with --scratch-path .build-worker in each tree,
# copy mlx.metallib + .fingerprint next to each worker.
# build_mid_and_aa.sh does exactly this for MID and then takes the A/A dump:
research/r103b/scripts/build_mid_and_aa.sh

# 0b. STALENESS GUARD - run before trusting any comparison.
#     A naive incremental rebuild silently keeps a stale object file and yields
#     a false PASS. Force a clean build per tree, then prove the three workers
#     are genuinely different binaries and that the R3 marker tracks revision:
for a in old mid new; do
  w=".mlxfast-private/r103b-$a/.build-worker/release/mlxfast-runtime-worker"
  printf 'r103b-%s: DARKBLOOM_ROUTER_WEIGHT_PREFETCH strings=%s sha256=%.16s bytes=%s\n' \
    "$a" "$(strings -a "$w" | grep -c DARKBLOOM_ROUTER_WEIGHT_PREFETCH)" \
    "$(shasum -a 256 "$w" | cut -d' ' -f1)" "$(stat -f%z "$w")"
done
# expected: old/mid strings=0, new strings=1; three distinct sha256 and sizes.

# 1. capture MSL corpora and dispatch traces for all five arms
ARMS="old mid new new_pf0 new_aa" STEP=5 research/r103b/scripts/run_all_traces.sh

# 2. differentials - both intervals, plus the two controls.
#    These scripts take ARM NAMES, not paths (they prefix /tmp/r103b/dump).
for pair in "old mid" "mid new" "old new" "mid new_pf0" "new new_aa"; do
  python3 research/r103b/scripts/compare_msl.py      $pair
  python3 research/r103b/scripts/compare_dispatch.py $pair
  python3 research/r103b/scripts/seqalign.py         $pair
done
python3 research/r103b/scripts/steps.py old mid new new_pf0 new_aa
# expected: old|mid -> 1 differing library (B); mid|new -> A only, as a rename;
#           mid|new_pf0 -> 103/103 byte-identical; new|new_aa -> 103/103
#           byte-identical AND 11243/11243 dispatch rows equal (the A/A control).

# 3. static classification of the 32-file diff
python3 research/r103b/scripts/comment_strip_diff.py 30f752df 0f6862d0

# 4. working-set digests
research/r103b/scripts/working_set_manifest.sh 30f752df 0f6862d0

# 5. rule-74 rider: is f720e9e7 emitted-code-neutral on the JIT path?
python3 research/r103b/scripts/rule74_check.py "$PWD"

# 6. optional M4 A/B of mechanism A (cancelled here at 6 legs; needs LEGS >= 33
#    for K >= 16 usable pairs after discarding leg 01)
LEGS=33 research/r103b/scripts/ab_router_prefetch.sh
python3 research/r103b/scripts/ab_summarize.py /tmp/r103b/ab/summary.tsv
```

---

## § Reply

**Headline, per fb3: what actually changed in the emitted/dispatched code
across the three revisions is two Metal kernels, one per interval, and nothing
else. `OLD -> MID` changes exactly one kernel (mechanism B, sliding fused
attention). `MID -> NEW` changes exactly one kernel (mechanism A, router weight
prefetch). Per-decode-step dispatch delta is zero on both intervals. No
microsecond figure is attached to either.**

### The three-revision inventory you asked for

MID = `e17bdeb1` is built, dumped and diffed. It is the merge of PR #565, an
ancestor of NEW, and `git diff --numstat e17bdeb1 0f6862d0` over the submitted
surface is **exactly one file** - `LagunaRuntimeModel.swift`, `+102/-11` - so
`MID -> NEW` really is R3 (PR #558) in isolation, not R3 plus stragglers.

| comparison | libs | byte-identical | differing | only-A | only-B | verdict |
|---|---:|---:|---:|---:|---:|---|
| OLD `30f752df` vs MID `e17bdeb1` | 103/103 | 102 | **1** | 0 | 0 | **B alone** |
| MID `e17bdeb1` vs NEW `0f6862d0` | 103/103 | 102 | 0 | **1** | **1** | **A alone** (a rename, `_pf1`) |
| MID vs NEW+`PREFETCH=0` | 103/103 | **103** | 0 | 0 | 0 | **bit-identical** |
| NEW vs NEW (A/A control) | 103/103 | **103** | 0 | 0 | 0 | **control passes** |

- **B** (`sliding_fused_attn_ring_v1`, PR #565, 60,780 -> 64,866 B): the sole
  semantic change is MSL line 1280, `for (; i + BN < N; i += 2*BN)` ->
  `for (; i + 3*BN < N; i += 4*BN)`, plus `pipe_keys_c/d`, `pipe_values_c/d`,
  `pipe_kc[4]`, `pipe_kd[4]` and the doubled pair-pointer stride. No env guard;
  never re-measured since it landed. The sibling `full_fused_attn_grow_v1` was
  left at 2-way.
- **A** (`residual_rms_router_..._rpg8_keys_v1` -> `..._pf1_...`, PR #558,
  52,359 -> 53,264 B): `thread vec<bfloat,4> laguna_pf[4]` declared *outside*
  the `if (simd_group < active_simd_groups)` guard between `simd_sum` and the
  threadgroup reduction, so it survives a barrier; the block loop is peeled
  `0..` -> `4..` with a 1-trip prologue.
- **The third row is the useful one for you.** Running NEW's own binary with
  `DARKBLOOM_ROUTER_WEIGHT_PREFETCH=0` reproduces **MID's entire 103-library
  corpus bit-for-bit**. So the difference between the two newest revisions is
  gated behind one environment variable, and reverting R3's emitted code costs
  zero source bytes and zero rebuild.

### Pricing: retracted, ordering kept

I accept the retraction in full. Every absolute-microsecond attribution in
section 7 is struck through and marked "withdrawn; retained for audit" - the
`T` = 20.149 us/step target, the 11.45 %-of-`T` pool share, the +4.25 % combined
figure and the A-alone/B-alone splits. Given `sd(T)` of 12.1-14.3 us/step on
byte-identical code, that gap is z ~ 1.0-1.2 and I should not have priced
against it. Section 0 and section 12 no longer quote it either.

What survives is **ordering, not cost**: B first on exposure (2x the pool
residency, 1024-thread threadgroup, no restore flag, never re-measured), A first
on testability (env flag, bit-exact restore, one measurement). And one
quantitative claim that is *not* receipt-derived: **per-decode-step dispatch
delta = 0 on every interval, so `0 x 0.3 us` = +0.00 us/step from dispatch
count**. That number comes from counting rows in a trace, not from timing.

### Dumper warnings (nezuko, #575, rule 58) - what I did about each

- **Why my corpus was non-empty where nezuko's was.** nezuko hooked
  `Device::get_library`. Custom-kernel MSL text only exists inside
  `Device::build_library_` (`Vendor/mlx-swift/.../metal/device.cpp:622`), which is
  where I hooked; `get_library` sees a cache handle, not source. That is a
  hook-site difference, not a difference in what the two of us were looking for.
- **Dispatch trace is co-equal, not a footnote.** Section 6 is reported at the
  same weight as section 5 precisely because a corpus diff cannot see host-side
  *selection* changes. Alignment: OLD vs MID **11247/11247 rows, 0 non-equal
  opcodes**; MID vs NEW and OLD vs NEW differ by exactly one deletion of 4 tail
  rows, and every aligned row matches on `(kind, grid, threadgroup, buffer
  shapes+dtypes)`.
- **The 4-row tail is now explained, not hand-waved.** Every `dispatch.tsv` at
  every arm is exactly **1,671,168 B (0x198000)** - a hard tracer buffer quota -
  and every one ends mid-line. `_pf1` adds 4 characters to each of 236 router
  rows = 944 B, and the 4 rows NEW loses occupy 978 B in OLD's file. Two
  independent NEW dumps truncate at the identical row.
- **A/A control, which I did not have before.** NEW dumped twice from the same
  binary: 103/103 libraries byte-identical and 11243/11243 dispatch rows equal,
  0 non-equal opcodes. The method's zero is a real zero.
- **Device stated.** All dumps: Apple **M4 Pro, 20 GPU cores, 48 GiB, Darwin
  25.5.0, Metal LanguageVersion4_0, Apple GPU generation 16**.
- **Scope limit I cannot close from here.** Generation 16 never requests the
  `_nax` variants the ranked M5 selects, so those kernels are absent from all
  five of my corpora. "Exactly 2 of 103 differ" is therefore a **lower bound on
  M5**, not a proven total. Closing it needs one corpus dump on the ranked host.
- **Staleness guard, per your rebuild warning.** Each tree was built clean into
  its own `--scratch-path .build-worker`, and I verified three genuinely distinct
  binaries before trusting any comparison:

  ```
  r103b-old: DARKBLOOM_ROUTER_WEIGHT_PREFETCH strings=0  sha256=9fce9f4c4cd3963e  bytes=49145848
  r103b-mid: DARKBLOOM_ROUTER_WEIGHT_PREFETCH strings=0  sha256=725cc9ca676d3b0e  bytes=49240232
  r103b-new: DARKBLOOM_ROUTER_WEIGHT_PREFETCH strings=1  sha256=26c6dc830d0f1907  bytes=49257896
  ```

  Distinct sha256 and distinct sizes at all three, and the R3 marker appears only
  at NEW.

### Rung 0 and the riders

- **Rung 0 PASS at all five arms.** old / mid / new / new+`PREFETCH=0` / new_aa
  all produce token-identical, top-5-logit-identical output, `golden_hash
  b9509697c08a2cf3...`, `matched_prefix_steps 6`. Reusable tree recipe and the
  three harness traps are in `research/r103-armr-build-notes.md`.
- **Rider 1 resolved.** Zero `_idx_v1` and zero `_ns1` QKV kernels are compiled
  or dispatched at any revision - dormant on reachability evidence, not on
  source reading.
- **Rider 2 (`f720e9e7`, rule 74) answered without a third tree, and the answer
  is your first branch - byte-identical.** `f720e9e7` is an ancestor of NEW and
  not of OLD, and for all four files the OLD->NEW range delta equals its own
  delta exactly, so **my OLD arm already is the comments-restored tree**.
  `sdpa_vector.h` compiles zero JIT libraries in the scored window (AOT only, so
  not applicable); `quantized.cpp`, `matmul.cpp` and `jit_kernels.cpp` feed 12 of
  the 103, **all 12 byte-identical**, dispatched 586x in prefill and 415x in
  decode step 0 and **zero times in every steady-state decode step**. The only
  channel left for it is host binary layout, which #548 declined to claim.

### Also on the record

- **Neither survivor changes work (section 7.2).** I walked B's loop bounds
  exhaustively: with `i = sg` striding by `BN = 32`, OLD runs 8 iterations and
  NEW runs 4, and both cover the same 16 slots `sg + 32m`, m = 0..15, for all 32
  simdgroups (32 x 16 = 512 = `N`), with **no tail loop in either**. So B is pure
  unroll depth and A is pure prefetch - latency hiding versus register pressure,
  +48 B/lane for B and +32 B/lane for A. Both dispatch **exactly 32
  threadgroups**, which on this 20-core host is two waves and on a >= 32-core
  ranked host is one. That makes a local A/B **structurally uninformative** for
  ranking A against B, not merely underpowered.
- **The M4 A/B was launched and then cancelled at 6 legs (K = 3 pairs).** All six
  passed correctness at both flag settings. My own preregistration needs K >= 16,
  so I report the legs and claim nothing from them; the machine time went into
  the MID tree instead, which I judged the better trade given the point above.
- **Zero official receipts taken**, and the merged diff touches **zero submitted
  bytes** - `git diff --stat 0f6862d0 -- Sources Vendor Package.swift
  Package.resolved benchmark.json` is empty. I did not implement either revert;
  the assignment asked for the mechanism, not the fix.
