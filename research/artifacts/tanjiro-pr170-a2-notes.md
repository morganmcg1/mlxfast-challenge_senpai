# A2 diagnostic arm (`probe == 4`, `kProbeA2`) — implementation note

Target kernel: `fp_gather_qmm_rhs_expert_nax`.
Hypothesis under test: the NVFP4 staging path is limited by **scalar integer
ALU issue**, not by device bandwidth, threadgroup traffic, barriers, or MMA.
A2 adds integer-ALU work and nothing else, so its marginal wall time is a
direct read on that axis.

Everything below was developed and validated **entirely out of tree**. Nothing
in the repository working tree was modified.

## Artifacts

| path | what |
| --- | --- |
| `/tmp/a2.patch` | unified diff, 8 hunks, +91 lines, against `Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized_nax.cpp` |
| `/tmp/a2gen/fp_quantized_nax.cpp` | the patched twin that was actually compiled |
| `/tmp/a2pristine/` | untouched copy of `mlx-generated/` used as the baseline |
| `/tmp/a2_edit.py`, `/tmp/a2_edit2.py` | the two anchor-checked edit scripts that produce `/tmp/a2gen` from `/tmp/a2pristine` |
| `/tmp/a2_census.py` | new: per-function op census over `metal -S -emit-llvm` output |
| `/tmp/a2_blocks.py` | new: per-basic-block integer-ALU count inside one function |
| `/tmp/a2_map_header.py` | new: maps each patch hunk onto its `.h` line |

Reproduce from a clean checkout:

```sh
rm -rf /tmp/a2gen && cp -r Vendor/mlx-swift/Source/Cmlx/mlx-generated /tmp/a2gen
python3 /tmp/a2_edit.py && python3 /tmp/a2_edit2.py
GEN_DIR=/tmp/a2gen PROBE=4 OUT_DIR=/tmp/naxpb4 EMIT_LIB=1 EMIT_IR=1 \
  research/nax_msl_compile_check.sh
```

## Design

Three constraints drove the shape of the arm.

1. **Zero layout impact on the shipped build.** The gate is a *defaulted
   function* template parameter on `load_unsafe_wide`, not a class template
   parameter on `QuantizedBlockLoader`. An earlier draft put `bool kProbeA2`
   and a `uint4 a2acc` member on the class; that changed
   `%struct.QuantizedBlockLoader` from 10 fields to 11, moved its alloca from
   `align 8` to `align 16`, and changed the mangled name of all four
   instantiations — ~1844 changed IR lines at probe 0. Rejected.
2. **No extra load of any kind.** The skeleton reuses the *same*
   `fp4nv_pack4(sb + k0 + b * 4)` expression the real decode already
   evaluates, so CSE shares it instead of re-reading the staging buffer.
3. **Not removable by the optimizer.** The shadow code word is
   `real_pack4 ^ a2seed`, where `a2seed` derives from `run_skip_pct`, a
   runtime constant-buffer scalar. The compiler cannot prove `c2 == c`, so the
   mask/shift/or chain cannot be CSE'd against the real one, and cannot fold
   it to a constant either.

Payload, per 4 source bytes, is the integer half of `fp4nv_decode8` stopping
before the float tail — 18 IR ops (1 xor + 2 and + shl/or + lshr/or + four
accumulator updates). Four independent accumulators mirror the real chain's
ILP width of 4, so the arm adds *issue* pressure rather than a serial latency
chain.

The accumulator is a loop-carried local `uint4 a2local` declared **outside**
the `kWideChunks` loop and merged into `*a2acc` once per call. This matters:
the first draft did `a2acc->x ^= ...` directly, and because `a2acc` is a
pointer parameter of a function LLVM does not inline, that cost a 16 B
thread-memory load **and** store *per chunk* (IR block `163`,
`/tmp/naxpb4/unit.ll`). That is memory traffic, which would have contaminated
the whole point of the arm. See `/tmp/a2_edit2.py`.

The sink reuses the house idiom already used by the M2 arm: `if (run_skip_pct
> 1000) { y[0] = ...; }`, host-clamped to `[1,100]` so it never fires.

## Mirror edit — header line numbers

`research/nax_twin_check.py` requires the `.h` and the `mlx-generated/*.cpp`
twin to be textually identical in their shared region, so every hunk must be
applied to
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized_nax.h`
verbatim. Mapping (`/tmp/a2_map_header.py`):

| hunk | twin `.cpp` | header `.h` | anchor | +lines |
| --- | --- | --- | --- | --- |
| 1 | 540 | **391** | replaces the `template <bool wide_store, bool wide_load>` / `void load_unsafe_wide() const {` pair at `.h` 394–395 | +12 |
| 2 | 590 | **441** | declares `a2local` immediately before the `STEEL_PRAGMA_UNROLL` / `for (short c = 0; c < kWideChunks; c++)` at `.h` 444–445 | +9 |
| 3 | 623 | **474** | injected skeleton after the `if (store_ok)` store block, plus the `*a2acc ^= a2local` merge after the chunk loop | +29 |
| 4 | 1714 | **1571** | probe doc comment in the kernel template parameter list | +5 |
| 5 | 1739 | **1596** | `constexpr bool kProbeA2` + `a2seed`, right after `constexpr bool kProbeB2` (`.h` 1598) | +6 |
| 6 | 1879 | **1736** | `uint4 a2acc;` after `NAXTile<float, TM, TN> Dshadow;` | +7 |
| 7 | 1961 | **1818** | staging call site; the shipped spelling stays verbatim in the `else` arm (`.h` 1821) | +6 |
| 8 | 2023 | **1892** | A2 sink, inserted after the closing `}` of the M2 sink (`.h` 1888–1892) | +11 |

Line numbers are against the pristine `.h` (1988 lines); apply hunks bottom-up
or re-derive after each insertion.

## Offline validation

Host: Apple M4 Pro. **All of this is compile/IR evidence only — no benchmark
was run, and M4 is not the ranked M5.**

### Compiles

`COMPILE OK (std=metal4.0)` + `METALLIB OK` for probes 0, 1, 2, 3, 4 from the
patched twin, and for probe 4 at `BK` 32 / 64 / 128. Warning count under
`-Wall -Wextra` is unchanged at 8, all pre-existing.

### Probe-0 inertness (the important gate)

Pristine probe-0 and patched probe-0 were compiled **from the same source
path** (`/tmp/a2cmp/unit.metal`) so `ModuleID` could not differ.

- `%struct.QuantizedBlockLoader` type: **byte-identical**
  (`{ i32, i32, i32, i16, i16, i16, i16, bfloat addrspace(3)*, i8 addrspace(1)*, i8 addrspace(1)* }`),
  as are `WideSrc` and `WideChunk`.
- Op census over all 28 defined functions: **0 functions changed**, and
  *no axis moved* — mma 2, barrier 12, dev_load 75, dev_store 60, tg_load 26,
  tg_store 15, int_alu 606, float_alu 19, 3487 instructions, identical.
- Raw `.ll` diff is 446 lines; after normalising the mangled name and SSA
  numbering it is **68 lines, all of them basic-block label renumbering**,
  caused purely by the two extra (dead, `0` / `null`) function arguments
  consuming two SSA numbers.

The `.air`/`.metallib` are not byte-identical, because the mangled name of
`load_unsafe_wide` gains `Lb0E` and two dead parameters. That is a name-string
difference, not a code difference.

### A2 arm cost, probe 0 → probe 4

`python3 /tmp/a2_census.py /tmp/a2pb0/unit.ll /tmp/naxpb4/unit.ll`

| axis | probe 0 | probe 4 | delta |
| --- | --- | --- | --- |
| mma | 2 | 2 | **0** |
| barrier | 12 | 12 | **0** |
| device load | 75 | 75 | **0** |
| threadgroup load | 26 | 26 | **0** |
| threadgroup store | 15 | 15 | **0** |
| float ALU | 19 | 19 | **0** |
| **integer ALU** | 606 | 635 | **+29** |
| const-buffer load | 2 | 4 | +2 (one `run_skip_pct` read per kernel) |
| device store | 60 | 62 | +2 (the never-taken `y[0]` sink, one per kernel) |
| thread-space load/store | 274 / 164 | 277 / 167 | +3 / +3 |

The four axes the arm claims not to touch are exactly unchanged. The three
axes that do move are all **once per kernel or once per staging call**, never
per chunk:

- `+1` const load and `+5` int ops per kernel: the `a2seed` computation,
  hoisted to kernel entry (`%33 = load i32 addrspace(2)*`,
  `%34 = mul i32 %33, -1640531527`, `%35 = add i32 %34, -1640531527` —
  reassociated `A*(x+1)`, **not** constant-folded).
- `+1` device store per kernel: the guarded sink.
- `+1` thread load / `+1` thread store per `load_unsafe_wide` call, in the
  chunk-loop **exit** block `64` (`preds = %166`, the latch), i.e. *outside*
  the trip-4 loop. Inside the loop the accumulator is a register-resident
  `<4 x i32>` phi (`%69`).

### Achieved injected/real integer ratio

Per-basic-block counts inside `load_unsafe_wide<bfloat,…><1,1>`
(`python3 /tmp/a2_blocks.py …`), for one iteration of the trip-4
`kWideChunks` loop:

| | probe 0 | probe 4 |
| --- | --- | --- |
| addressing / scale select (blocks 65,75,79) | 3+1+2 = 6 | 6 |
| **real `fp4nv_decode8` integer core** (block 90/93) | **13** | **13** |
| chunk-loop latch (block 163/166) | 1 | **19** |
| chunk-body total (fast store path) | 20 | 38 |

So the arm injects exactly **18 integer ops per chunk**, precisely the 18
predicted from source — nothing was folded away and nothing extra appeared.

- against the 13-op decode core: **1.38 : 1**
- against the whole chunk-body integer work on the taken store path:
  **0.90 : 1**

Per `load_unsafe_wide` call that is 4 × 18 = **72 injected integer ops against
4 × 20 = 80 real ones**. That is the ~1:1 the arm was specified to hit.

### Compiler defeats — checked, none found

| risk | verdict | evidence |
| --- | --- | --- |
| CSE merging the shadow chain into the real one | **defeated by design** | block `166` of `/tmp/lw4.ll` holds 19 fresh ops; `%167 = xor i32 %110, %1` reuses the real `fp4nv_pack4` result `%110` (intended) but nothing downstream is shared |
| DCE removing the payload | **no** | 18/18 predicted ops present |
| LICM hoisting the payload out of the chunk loop | **no** | the payload is *in* the latch block of the `!llvm.loop !101` trip-4 chunk loop |
| loop unswitching on `run_skip_pct > 1000` duplicating the k-loop and DCE-ing the arm in one copy | **no** | both kernels have exactly **16** `!llvm.loop` latches and exactly **1** call to `load_unsafe_wide`; `%145 = icmp sgt i32 %33, 1000` is computed once in the pre-loop block |
| sinking the whole arm into the never-taken branch | **not possible at this level** | the payload lives inside `load_unsafe_wide`, which has threadgroup side effects and is called exactly once |
| register-pressure / occupancy shift | **no change measurable here** | `tgMem_B` 9232 and `maxThreads` 1024 identical for all four entry points; the 1024 ceiling saturates the register bound, so `research/tanjiro_metallib_stats.swift` cannot resolve it — this stays an open confound, as that tool's own footer states |

## Residual risks

1. **Driver-level DCE.** The `.metallib` is still AIR bitcode; the final ISA is
   produced at pipeline-creation time on the device. The driver may inline
   `load_unsafe_wide` into the kernel, at which point it could in principle
   sink the A2 chain into the never-taken `run_skip_pct > 1000` branch and
   delete it. Nothing offline can rule this out. The empirical tell is an A2
   marginal cost of ~0; if that happens, cross-check against the M2 arm, which
   uses the identical sink idiom and is known to cost something.
2. **`+1` thread-space load/store per staging call.** Small and amortised over
   4 chunks, but it is not zero. If the attribution needs to be perfectly
   clean, the alternative is to give `load_unsafe_wide` a `uint4` return value
   under the gate, which costs an overload.
3. **M4 Pro reports Apple GPU generation 16 and does not select the `_nax`
   prefill kernels the ranked M5 uses.** Every number above is from offline
   `xcrun metal` compilation, so it is architecture-independent IR evidence,
   but any *timing* of this arm must come from the ranked M5.
4. The header mirror edit has **not** been applied or checked with
   `research/nax_twin_check.py`, because that requires writing to the repo.
