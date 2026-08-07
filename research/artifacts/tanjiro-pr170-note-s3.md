# PR170 arm S3 — prefill routed-gather regime discriminator (staging work *without* DRAM bytes)

## 0. What this submission is, and what it is not

This is the fourth and final diagnostic arm of a four-arm instrument. It is a
measurement, not a proposed speedup. It deliberately makes the scored prefill
kernel **slower** by adding bit-exact dead work along one resource axis, and it
is expected to come back `rejected` on ranking. The value is entirely in the
marginal wall-clock cost the official M5 reports, not in the score.

Every checked token is unchanged. The previous three arms of this same
instrument returned `passed_correctness = True` with `max_abs_diff = 0`, and
this arm uses the identical sinking discipline.

What this arm is *not*: it is not a candidate for promotion, it is not a
precision change, it is not a re-quantization, and it does not touch
`Sources/MLXFastModel/LagunaRuntimeModel.swift`.

## 1. Initial context and goal

The scored prefill wall is dominated by one kernel:
`fp_gather_qmm_rhs_expert_nax`, the routed MoE gather GEMM. Across 39 MoE
layers and two projections (fused `[gate32;up32]` at K=2048,N=1024, and routed
`down_proj` at K=512,N=2048), with E=256 experts and B=4096 routed rows at
T=512, it accounts for

- **GFLOP = 1005.02**
- **GBYTE = 17.66641**
- arithmetic intensity **56.89 FLOP/B**
- measured wall **W = 43.2619 ± 0.402 ms** of the 97.895 ms control prefill.

The goal of this instrument is to name the *binding constraint* of that kernel
so that later optimization effort is spent on the axis that actually pays.

## 2. Environment and setup

The local research host is an **M4 Pro, Apple GPU generation 16**.
`is_nax_available()` requires generation ≥ 17, so the `_nax` kernel family
**never executes locally**. Every timing number in this programme therefore
comes from official M5 receipts. The local host is used only for compile,
AIR/LLVM-IR census, twin consistency, and the safety rig.

Submitted surface is exactly three files:

- `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized_nax.h`
- `Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized_nax.cpp`
- `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp`

## 3. Prior work in this instrument, and what it already established

Control (promoted frontier `97a5090`): prefill wall `S = 97.895 ms`, score
`2.58882784082067`. Candidate-side prefill wall noise, measured
non-circularly over n=16 feed receipts, is `sigma_S = 0.318 ms` (0.33%). The
paired *baseline* prefill is 12.6x noisier, so all readings use the **raw
candidate prefill wall**, never the ratio.

**Arm M2 (probe 1) — MMA / integer-ALU axis.** Adds one extra cooperative
`matmul2d` plus 15 integer ALU ops per k-step. Receipt
`d786ad5c-cdd5-4383-b246-d9a7f3775a69`, prefill wall `S = 99.941 ms`.

  **dM2 = +2.046 ms**, i.e. 4.7% of W.

Reading: doubling the MMA issue count costs almost nothing. The kernel is not
NAX-issue-throughput-bound. H1 (compute-bound) eliminated; H0 with it. The
integer-ALU ceiling from this arm is 27.4% of W, which also capped and then
withdrew the optional H1b arm.

**Arm S2 (probe 2) — staging / load axis.** Adds a second device loader that
stages the *neighbouring* expert's tile into a scratch threadgroup buffer:
+2 device loads, +1 threadgroup store, +1 barrier, +4 integer ALU per k-step.
Receipt `a3e38005-5510-4529-93c5-da236eff0950`, prefill wall `S = 113.856 ms`.

  **dS2 = +15.961 ms**, i.e. **36.9% of W, 35 sigma**.

Reading: the staging/load path is the binding constraint. Body staging
instruction count is 11; the arm adds 3 (+27.3%) and the wall moves +36.9%.
Marginal cost per staging instruction is 5.138 ms versus a 3.933 ms average,
ratio **1.31**.

**Arm B2 (probe 3) — barrier axis.** Adds 2 threadgroup barriers and nothing
else (IR-verified: every other axis is byte-identical to the control).
Dispatched; its receipt prices the barrier term that currently sits inside the
S2 residual.

## 4. The question this arm exists to answer

S2 moved two things at once that the previous arms cannot separate:

1. **load-issue / staging-pipeline structure** — two more device load
   instructions, one more threadgroup store, one more barrier, and whatever
   serialization the extra load->barrier->use chain imposes; and
2. **DRAM byte volume** — the neighbouring expert's tile is, in general, not
   resident, so S2 also pulls roughly **+5.89 GB** of extra traffic across the
   frozen window.

Under the assumption that bytes scale with load count, S2's marginal rate is
**369 GB/s** against an effective body rate of **408 GB/s** (about 67% of
peak). But that assumption is exactly what is unverified: the neighbour slab
may be partly cache-served, in which case the byte term is smaller than 5.89 GB
and more of dS2 belongs to issue structure.

These two sub-causes imply **opposite** optimizations:

- if the cost is load-issue / pipeline structure, the payoff is in staging
  *structure* — double buffering, wider loads, fewer barriers, deeper software
  pipelining — and byte volume is nearly irrelevant;
- if the cost is DRAM bytes, the payoff is in *byte volume and reuse* — larger
  tiles, better expert blocking, less re-fetching — and restructuring the
  staging loop is wasted effort.

S3 separates them.

## 5. Approach selection and tradeoffs

**S3 (probe 4) is S2 with the DRAM-byte term removed and nothing else
changed.**

The shadow loader keeps its full instruction sequence, its threadgroup store,
its barrier and its address arithmetic. The only change is *which* address it
reads: instead of the neighbouring expert's tile, it reads **this expert's own
tile** — the exact lines that the real loader `loader_w` reads one barrier
later. Those lines are therefore guaranteed to be resident by the time the real
load issues (and in the common case already resident when the shadow load
issues), so the arm adds **zero incremental DRAM bytes** while keeping the
staging instruction count, the store, and the barrier identical to S2.

`dS3` is therefore the load-issue / staging-structure term alone, and

  **dS2 - dS3 = the DRAM-byte term for those +5.89 GB.**

Alternatives considered and rejected:

- *Replicating S2* — spends a receipt to re-measure a 35-sigma effect. The
  advisor's close criteria explicitly call that out. Rejected.
- *An occupancy arm* (padding `Ws_storage` to drop 3 threadgroups/core to 2) —
  a good arm, but it moves a different axis and cannot resolve the
  issue-vs-bytes split that S2 opened. Retained as a follow-up.
- *A dependent-MMA latency probe* — worthwhile, but M2 already bounds the MMA
  axis at 4.7% of W, so the upside is small. Retained as a follow-up.

## 6. Implementation

Six edits to the header, mirrored verbatim into the generated `.cpp` twin, and
two to the host selector.

Header (`fp_quantized_nax.h`):

1. template doc comment gains `4 = S3`;
2. `constexpr bool kProbeS3 = (probe == 4);` and
   `constexpr bool kProbeStage = kProbeS2 || kProbeS3;`;
3. the shadow loader is constructed from `shadow_expert` rather than a
   hardcoded neighbour;
4. the staging comment is generalised to S2/S3;
5. the load site is gated on `kProbeStage` rather than `kProbeS2`;
6. `loader_w2.next()` is gated on `kProbeStage`.

The address selection is:

```cpp
const int shadow_expert = kProbeS3
    ? int((expert + int(run_skip_pct > 1000)) % experts)
    : int((expert + 1) % experts);
```

**Why the guard is written that way.** `run_skip_pct` is a constant-buffer
scalar that the host clamps to `[1, 100]`, so `run_skip_pct > 1000` is always
false at runtime and `shadow_expert == expert`. But the compiler cannot fold
it, so the two loaders keep *statically distinct* base-address expressions and
the duplicate device reads survive common-subexpression elimination. That is
the whole arm: if CSE collapsed the two loads, S3 would silently degenerate
into the control and the measurement would be void.

At `probe == 0` the ternary folds to the pre-existing
`(expert + 1) % experts` and the shadow loader is dead, so the shipped control
path is unchanged.

Host (`quantized.cpp`): the probe-name map gains `if (s == "s3") { return 4; }`
and a documenting comment. No further plumbing is needed — `gather_probe` is
already forwarded as a template argument and the kernel-name suffix is
`"_pb_" + std::to_string(gather_probe)`, so `_pb_4` is automatic. The existing
interlock (`probe_requested != 0 && !expert_aligned && laguna_moe_shape` throws)
already covers value 4.

## 7. Offline verification

**LLVM-IR census, S3 (pb4) against S2 (pb2), both live threadgroup shapes:**

```
function                                        mma  barrier  dev_load  tg_load  tg_store  int_alu  float_alu
fp_gather_qmm_rhs_expert_nax_..._2048x1024_bk64   1        8         8        4         6       91          5
fp_gather_qmm_rhs_expert_nax_..._512x2048_bk64    1        6         8        2         5       86          0

functions with a changed census: 2
axes that moved: const_load   (1 -> 2, +3 total instructions)
```

**This is the arm's validity gate and it passed.** `dev_load` is still **8**,
not 6: CSE did not eat the duplicate read. Every axis M2, S2 and B2 move —
`mma`, `barrier`, `dev_load`, `tg_store`, `int_alu`, `float_alu` — is
*byte-identical to S2*. The single difference is one extra constant-buffer
scalar load for `run_skip_pct`, which is loop-invariant and three instructions
in total.

**Control inertness:** regenerating probe-0 IR from the S3-edited sources and
diffing against probe-0 IR from the pre-edit sources gives
`functions with a changed census: 0`, `axes that moved: (none)`. The shipped
path is provably untouched.

Also passing: the header/generated-twin consistency check (6 structural hunks,
exit 0); host `-fsyntax-only` (only the two pre-existing C++20 warnings); the
full safety rig (compile+link at BK=64 and BK=128, BK=64 AIR byte-identical to
HEAD, non-empty MMA body, widened device load reachable, wide-load guard fires
as a negative control, twin match) — **all 6 checks passed**; and the editable
budget (`current=2941461/3000000 headroom=58539 growth=14550/262144`).

## 8. How to read this receipt

Let `S` be `1000 * prefill_seconds_per_token * 512` (the raw candidate prefill
wall in ms) and `dS3 = S - 97.895`.

Pre-registered readings, decided before the receipt:

- **R-S3-A (issue/structure-bound).** `dS3 >= 0.75 * dS2 = 11.97 ms`.
  The byte term is small; the cost is load-issue and staging-pipeline
  structure. Optimize staging structure: double buffering, wider loads, fewer
  barriers, deeper pipelining. Byte-volume work is deprioritised.
- **R-S3-B (byte-bound).** `dS3 <= 0.35 * dS2 = 5.59 ms`.
  The cost is DRAM byte volume. Optimize bytes and reuse: larger tiles, better
  expert blocking, less re-fetch. Staging restructuring is deprioritised.
- **R-S3-C (mixed).** `5.59 < dS3 < 11.97`. Report the split explicitly:
  issue share `= dS3 / dS2`, byte share `= 1 - dS3 / dS2`, and the implied
  marginal bandwidth `5.89 GB / (dS2 - dS3)`. Both directions pay; rank them by
  the measured shares.
- **R-S3-V (void).** `passed_correctness` false, or `max_abs_diff != 0`, or
  either speedup floor false. The arm is void and no reading is taken.

Note that `dS3` is bounded above by `dS2` by construction (same instructions,
no more bytes), so a value materially above `dS2 + 3 sigma = 16.92 ms` would
itself be evidence that the neighbour tile was *already* cache-served and that
the byte accounting is wrong.

## 9. Floor safety

S2 — the strictly more expensive arm — returned
`prefill_speedup = 1.6294` and `decode_speedup = 2.7417`, against a `0.95`
floor on each. S3 costs no more than S2 by construction, so both floors have
very large margin.

Decode is untouched by construction, not merely by measurement: the probe
kernel is gated on `M == 1 && B >= 16 && right_sorted_ && B/E >= 4`, which
requires `B >= 1024` and hence `T >= 128`. At decode `T = 1`, `B = 8`, so the
probe kernel provably cannot dispatch.

## 10. Failures and course corrections

- The first attempt to mirror the header edits into the generated `.cpp` twin
  used a shell heredoc; the terminal mangled the multi-line Python and it
  failed with a `SyntaxError`. Redone with direct file edits and verified by
  the twin check.
- An earlier probe-4 arm ("A2", an integer-ALU dose-response arm) was built and
  then **formally withdrawn** once M2 capped the integer-ALU axis at 27.4% of
  W. Its patch is stale and must not be applied; probe 4 is now S3.
- An earlier reading of the decode column was wrong: the raw
  `decode_seconds_per_token` carries `dS/128` of the arm's own prefill by
  construction (512-token seed plus 128 one-token steps). The reader now
  reports `T_ms = 1000*decode - S_ms/128` and prints the raw column only as a
  labelled diagnostic.

## 11. Exact commands

```
python3 research/nax_twin_check.py
xcrun clang++ -std=c++17 -fsyntax-only -x c++ \
  Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp -I ...
PROBE=4 BK=64 EMIT_IR=1 OUT_DIR=/tmp/naxpb4 research/nax_msl_compile_check.sh
python3 research/tanjiro_ir_census_lib.py /tmp/naxpb2/unit.ll /tmp/naxpb4/unit.ll
bash research/nax_safety_rig.sh
senpai/check-editable-budget.sh f1f7c1b13f2d57e0a049a7af9072a0f88a0fd0e2
```

## 12. Caveats

- The +5.89 GB figure for S2 assumes bytes scale with device-load count. If the
  neighbour slab is partly cache-served the true byte delta is smaller, which
  compresses `dS2 - dS3`. This is precisely why the reading reports the implied
  marginal bandwidth rather than asserting one.
- S3's shadow load hits cache in the steady state, but the *first* touch of a
  tile in a given threadgroup may still miss. That makes `dS3` a slight
  over-estimate of the pure issue term, i.e. it biases the reading conservatively
  toward R-S3-A.
- All timing is from the official M5. The local M4 Pro cannot execute this
  kernel family at all.
- Register pressure remains unmeasured (`regs_est` is hardcoded at 32); an
  occupancy change induced by the extra loader cannot be fully excluded, though
  the measured `staticThreadgroupMemoryLength = 9232 B` is byte-identical
  across all probes.

## 13. Next steps

With the issue-vs-bytes split resolved, the follow-up work is:

1. the occupancy arm (pad `Ws_storage` to force 3 -> 2 threadgroups per core);
2. a second-generation staging redesign that removes the extra barrier and the
   `int_alu` confound by sinking into registers rather than threadgroup memory;
3. MoE gather tile-quantization padding — rows per expert are well below
   `BM = 64`, and the routing histogram makes this checkable at zero cost;
4. a dependent-MMA latency probe, to separate NAX issue throughput (already
   ruled out by M2) from NAX latency under low occupancy.
