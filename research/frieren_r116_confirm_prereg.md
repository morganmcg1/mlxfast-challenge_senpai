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

## Landing readiness, checked before the result is known

So that rule 2 cannot be delayed by a static-review surprise, the submission
surface was validated against the campaign base
`1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7` while the confirmation was still
running:

```
assignment scope OK: 1 submitted path(s)   # Sources/MLXFastModel/LagunaRuntimeModel.swift
editable budget OK: current=2681206/3000000 headroom=318794 growth=-302643/262144
```

The flip itself is byte-neutral (`!= "0"` and `== "1"` are the same length), so
a landing consumes none of the 262,144 B growth allowance. The three literals
that rule 2 would edit are:

| arm | line | current literal |
| --- | --- | --- |
| `qmvsc0` | `LagunaRuntimeModel.swift:4131` | `environment["DARKBLOOM_NVFP4_QMV_SIGN_CARRY"] != "0"` |
| `qmvse0` | `LagunaRuntimeModel.swift:4159` | `environment["DARKBLOOM_NVFP4_QMV_SEED_ELIDE"] != "0"` |
| `sc0` | `LagunaRuntimeModel.swift:6668` | `environment["DARKBLOOM_NVFP4_SCALE_CARRY"] != "0"` |

Bit-exactness of the three flips already has direct evidence rather than only
the construction argument: all nine screen arms, including these three,
published the identical golden hash
`b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63`.

## What a null will be allowed to claim (computed while blind)

`python3 research/frieren_r116_mde.py` turns each arm's screen between-block
scatter into the effect the `|t| >= 3` rule can resolve, so a null is reported
as a bound rather than as "no effect". For the three confirmation arms:

| arm | paired SD (us) | MDE at 18 blocks (local us) | true us (x1.28) | share of score |
| --- | --- | --- | --- | --- |
| `qmvse0` | 11.9 | 8.4 | 10.7 | 0.090 % |
| `sc0` | 26.5 | 18.8 | 24.0 | 0.202 % |
| `qmvsc0` | 29.0 | 20.5 | 26.3 | 0.221 % |

Two consequences are accepted in advance. First, a fixed `|t|` threshold buys a
different physical resolution per arm, so each null is reported with its own
bound and never as one campaign-wide statement. Second, every SD here comes
from two degrees of freedom, so these bounds are themselves wide; the
confirmation's own 17-df SD replaces them in the terminal report.

## What is *not* claimed by this stage

The five arms dropped after the screen (`ns0`, `ns2`, `qse0`, `sd0`, `sfd1`)
are closed only at screen precision (3 paired blocks). They are reported with
their screen error bars and explicitly not claimed at confirmation precision.
