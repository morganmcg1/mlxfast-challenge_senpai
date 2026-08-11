# R116-A confirmation preregistration

Written 2026-08-11T03:0xZ, before any confirmation-stage run started, and
committed before the job launched.

## Why a second stage

The 3-block screen (`research/r116-defaults/screen`, 9 arms) exists only to
triage. Its paired contrasts have 3 replicates, so a single-arm SE is roughly
25-35 us/step and the best-of-8 argmax carries an expected upward bias of
`sem * 1.4236`. No screen-stage ranking is reportable as a result.

## Instrument

Primary statistic is the **steady-state decode step**, not
`decode_seconds_per_token`.

`--local-iterate`'s `decode_seconds_per_token` folds the 512-token seed pass
into the decode axis (`decode_spt ~= mean_step + 4 * prefill_spt`), and the
seed portion carries nearly all of the run-to-run noise on this M4 Pro host.
Measured reproducibility across two independent runs of the same arm:

| arm      | `decode_spt` spread | steady tail-mean spread |
| -------- | ------------------- | ----------------------- |
| `sfd1`   | 239 us (1.85 %)     | **11.7 us (0.14 %)**    |
| `qmvsc0` | 224 us (1.70 %)     | **39.6 us (0.48 %)**    |

`research/frieren_steady_step.py` parses the harness's own
`checked decode N/128 tokens last_step_seconds=...` lines (17 samples per run)
and takes the mean over tokens >= 16, discarding warmup. Secondary analysis
still runs `research/frieren_r109_analyze.py` on `decode_spt` for continuity
with r109 and for W&B logging.

## Arms (4, control first)

Every arm carries `DARKBLOOM_STARTUP_MEMORY_PROFILE=full` because this host has
48 GB and would otherwise auto-select the low profile
(`RuntimeStartupMemoryPolicy.swift`: MB=128/OPS=64 instead of MB=320/OPS=128).
Each block is gated on `@@LOWMEM_NOTICES == 0`.

| arm      | flip                             | role                     |
| -------- | -------------------------------- | ------------------------ |
| `ctl`    | (shipped defaults)               | control                  |
| `qmvse0` | `DARKBLOOM_NVFP4_QMV_SEED_ELIDE=0` | **P1** (preregistered) |
| `qmvsc0` | `DARKBLOOM_NVFP4_QMV_SIGN_CARRY=0` | **P2** (preregistered) |
| `sc0`    | `DARKBLOOM_NVFP4_SCALE_CARRY=0`    | screen argmax, exploratory |

`sc0` is carried forward *only* because it was the screen argmax. Its mechanism
predicts the opposite sign: with `SCALE_CARRY` OFF the kernel emits
`ushort(bits & 127) << 7` plus a `(bits & 128) ? -converted : converted`
select, which is strictly more ALU work than the ON path's
`ushort(uint(bits) << 7)` carrying add. It is labelled exploratory and its
screen lead (-41.5 us, block 1) is at the best-of-8 chance expectation
(`E[max of 8] * sem ~= 36 us`). The prior on record is that it regresses to
null or to the predicted positive (slower) sign.

## Design

18 blocks, ABBA-style order reversal on even blocks (the harness already does
this), contemporaneous, one model-holding process, 40 C thermal gate honoured.
Target paired SE ~8 us/step ~= 0.07 % of score at the recorded conversion of
0.0084 % of score per M4 wall us/step.

Output directory is **outside the git checkout**
(`.../workspace/r116-confirm`) so the running job cannot dirty the worktree.

## Decision rule, fixed in advance

1. An arm is a **candidate win** only if its paired steady contrast is
   negative with `|t| >= 3` over the 18 confirmation blocks *and* the screen
   blocks agree in sign.
2. A candidate win that is bit-exact by construction (all four arms here are
   pure source-substitution or kernel-name-suffix variants of the same
   arithmetic; `qmvse0`/`qmvsc0` change the kernel name, so they are immune to
   the name-keyed library-cache hazard) is landed by editing the compiled
   default literal in `Sources/MLXFastModel/LagunaRuntimeModel.swift`
   (`!= "0"` -> `== "1"`), then re-verified.
3. Any arm not meeting rule 1 is reported as null and the shipped default is
   confirmed. If no arm meets rule 1 the terminal finding is
   `N-DEFAULTS-ALREADY-OPTIMAL` and the submitted-surface diff stays empty.
   A negative is the honest deliverable for an audit; no landing will be
   manufactured to make the diff non-empty.
4. Escalate immediately, before validating, if any bit-exact flag moves the
   paired steady step by >= 50 us.

## What is *not* claimed by this stage

The five arms dropped after the screen (`ns0`, `ns2`, `qse0`, `sd0`, `sfd1`)
are closed only at screen precision (3 paired blocks). They are reported with
their screen error bars and explicitly not claimed at confirmation precision.
