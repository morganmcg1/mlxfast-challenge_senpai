# Arm G rung 1b/1c: folding the attention pre-norm into the gate softplus

Host: Apple M4 Pro, 20 GPU cores, 48 GiB, macOS 26.5.2, `applegpu_g16s`.
No `_nax` kernels are reachable here, so every number below is directional
evidence for the ranked M5 and is reported as M4 decode step wall.

Rig: `research/nezuko_armg_ab.sh` (one worker process per arm because the
`DARKBLOOM_*` knobs are read once at process start), 200 teacher-forced decode
steps per slot, step 0 and slot position 0 discarded, per-arm median of
per-slot medians, 20 000-draw percentile bootstrap over slot medians
(`research/nezuko_armg_stats.py`). Score pricing uses the campaign chain
`%score = 0.63 * tau * delta_step_wall_us / 8972`, i.e. 0.0070 %/M4 wall us.

## Arms

`DARKBLOOM_NORM_FUSED_GATE_SP`:

| arm | knob | pre-norm dispatch | gate_sp kernel | produces `normalized` |
| --- | ---- | ----------------- | -------------- | --------------------- |
| A | `0` | stock `rmsbfloat16` | shipped `gate_sp` (ns2r4) | pre-norm dispatch |
| C | unset / `1` | **deleted** | fused, recomputes RMS | fused gate_sp |
| W | `2` | stock `rmsbfloat16` | fused, recomputes RMS | pre-norm dispatch; fused output is written but unread |
| N | `3` | stock `rmsbfloat16` | fused, recomputes RMS, no `normalized` output | pre-norm dispatch |
| S | `4` | stock `rmsbfloat16` | fused kernel body at ns8r1 **consuming** `normalized` | pre-norm dispatch |

Arm A is the shipped frontier. Arm C is the assignment's Arm G proper
(remove the standalone pre-norm dispatch). W, N and S exist only to attribute
C's result.

## Rung 1b geometry ladder (blocks b1-b3)

Each block is A vs C only.

| block | fused-kernel form | A - C (us/step) | %score |
| ----- | ----------------- | ---------------- | ------ |
| b1 | recompute the normalized value inline in the matvec loop, ns2r4 (8 TG x 64 thr) | -344.75 | -3.008 |
| b2 | stage the normalized row in threadgroup memory, ns2r4 | -700.40 | -5.926 |
| b3 | staged row, ns8r1 (8 TG x 256 thr) | -48.04, CI95 [-60.02, -37.87] | -0.434 [-0.543, -0.342] |

A - C negative means the candidate C is **slower** than the shipped control.
b2 is worse than b1 despite doing less arithmetic: the threadgroup staging adds
two `threadgroup_barrier`s and 4 KiB of threadgroup memory to a kernel whose
occupancy at ns2r4 was already the thing hiding it, and the 64-thread
threadgroup cannot cover the staging store.

## Rung 1c three-arm attribution (block b4)

Job `2701a36a-f7dd-4625-9192-d86d3bd29761`, 946.7 s, 23:28-23:43Z,
GPU 39-42 degC, 6 replicates per arm, order
`C | A C W | W C A | C A W | W A C | A W C | C W A`.
All 19 slots exit 0 and report `teacher-forced greedy tokens: 0 divergences
(all match)`.

Arm medians (ms/step, within-arm spread across replicates in parentheses):

| arm | median step wall | spread |
| --- | ---------------- | ------ |
| A (shipped) | 8.2577915 | 0.20 % |
| C (candidate) | 8.3095205 | 0.31 % |
| W (work-only) | 8.2130620 | 0.20 % |

Contrasts:

| contrast | delta (us/step) | CI95 | %score |
| -------- | --------------- | ---- | ------ |
| A - C | -51.729 | [-61.21, -38.04] | -0.467 |
| **A - W** | **+44.729** | **[+37.08, +49.85]** | **+0.408 [+0.338, +0.455]** |
| C - W | +96.459 | [+81.21, +105.54] | +0.880 |

### Reading

Arm W does *strictly more work* than arm A: it keeps the stock `rmsbfloat16`
dispatch, restates the whole RMS reduction inside `gate_sp`, and additionally
stores a 4 KiB `normalized` buffer that nobody reads. It is nevertheless
**44.7 us/step faster**. The only structural thing W removes is the
`rms -> gate_sp` data dependency edge, which is worth about 2.55 us/layer under
the campaign's encoder-global barrier law, i.e. ~102 us/step at 40 layers, less
the added work.

Arm C is slower than A because deleting the pre-norm dispatch makes the
8-threadgroup, latency-bound `gate_sp` the *sole producer* of `normalized` and
therefore puts it in front of the 5120-threadgroup QKV matvec that used to hide
it. In the shipped schedule `gate_sp` is 96.4 % nested inside other work; a
kernel that is nearly free while nested is not free once it is on the critical
path. Removing a dispatch is not the same as removing its cost.

### Remaining confound

W also changes the gate kernel's geometry from the shipped ns2r4 (8 TG x 64
thr) to ns8r1 (8 TG x 256 thr). The offline single-dispatch geometry probe
(job `1d6556f9-68ad-4547-a65f-74901d3a6e64`, all 22 arms bit-exact) measured
stock gate_sp at ns8r1 as 2.125 us/dispatch faster than the shipped ns2r4,
which would be ~64 us/step of pure geometry. PR #7's precedent (+7.32 % on M4
collapsing to ~0 % on M5) makes geometry-derived wins the least transferable
kind, so the geometry share has to be separated before any of this is
shippable. That is block b5 (arms A, S, N, W).
