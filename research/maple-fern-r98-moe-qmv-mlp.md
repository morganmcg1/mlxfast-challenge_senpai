# r98-D — memory-level parallelism in the MoE-side decode QMV kernels

Student: maple-fern. PR #543. Assignment `maple-r98-d-moe-qmv-mlp`, revision `r98-d-rev1`.
Base `e510bb3d094a59ae2d4285d6da4d1ba5361a2b23`, branch `maple-fern/r98-moe-qmv-mlp`.
Host for all local numbers: Apple **M4 Pro**, 48 GiB, macOS 26.5.2. The ranked host is M5 Max.

## 1. Hypothesis

**H-D.** The MoE-side decode QMV kernels are memory-*latency*-bound rather than
bandwidth-bound. Increasing the number of outstanding weight loads per thread —
with identical bytes read, identical arithmetic, and identical accumulation
order — reduces decode seconds/token.

Round-98 context: rules 66 (#525, mine), 67 (#528) and 68 (#527) each falsified a
"do less work" mechanism. The surviving explanation for the M5/M4 divergence is a
latency-bound hot path on M5 that needs roughly 191 kB in flight to saturate,
against roughly 80 kB on M4. H-D is the direct test of that survivor.

## 2. Rung 0 — where the decode MoE bytes actually are

All line numbers are `Sources/MLXFastModel/LagunaRuntimeModel.swift` at
`61c8763` unless noted. Exposure numbers are from
`research/nezuko-pr-decode-exposure-audit.md`.

### 2.1 The assignment's "Site 1" is dormant and not submittable

`laguna_shared_nvfp4_swiglu_qmv_rows1_halved_wide_bf16_v1` (`:7099`/`:7100`) is
gated on `DARKBLOOM_QMV_WIDE_CODES == "1"`, which is **default OFF** (`:314-325`).
`research/RESEARCH_ARCHIVE_through-round-91.md:267` further records the wide-codes
variant as *explicitly not bit-exact* (it reassociates lane→group sums). So it is
both off the scored path and outside the correctness envelope. It cannot be the
experiment.

### 2.2 The live shared gate/up kernel is the un-pipelined analogue — but it is shadowed

The kernel actually selected is
`laguna_shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1` (`:7084`/`:7085`), generated
by `lagunaSharedSwiGLUQMVRows1Source(halved:)` at `:6996-7074`. With
`input_width=2048`, `block_width=512`, `values_per_lane=16` it runs **4 fully
serial K iterations**, each calling the pointer form `laguna_nvfp4_qdot_16(...)`
which issues its own code loads inside the dot product. There is no prefetch of
any depth. It is textbook depth-0.

It is also almost entirely shadowed. The audit measures
`shared_nvfp4_swiglu_qmv_rows1` at 39 calls/step × 6.09 µs = **237.6 µs/step
isolated** but with **exposure E ≈ 0.10** (audit `:97-105`, `:380-420`,
`:470-530`) — it overlaps the routed work. A generous 30 % kernel-level win is
therefore worth ≈ 7 µs/step ≈ **0.107 % score**, well under the M4 detection bar
(≈ 80 µs/step) and inside submission noise. Every other MoE decode kernel has
E ≈ 1.0.

**Decision: Rung 1 is redirected** from the shadowed shared gate/up kernel to the
largest *exposed* MoE kernel. The mechanism under test (bytes in flight per lane)
is unchanged; only the site changes, so H-D is still what gets tested — and it
gets tested where a win is measurable.

### 2.3 The exposed sites

| kernel | line | µs/step | exposure | GB/s | % M4 roofline | prefetch depth today |
|---|---|---|---|---|---|---|
| `laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2` | `:7916`, src `:7920-8025` | **1497.3** | ≈1.0 | 248.3 | 91.0 % | **1** |
| `laguna_routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6` (generated) | src `:8278-8421` | **812.8** | ≈1.0 | 243.7 | 89.3 % | 4 (already fully staged) |
| `laguna_shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1` | `:7084`, src `:6996-7074` | 237.6 | ≈0.10 | — | — | 0 |

The routed gate/up R1 kernel is the shipped default: the enabling env flags
`DARKBLOOM_FUSED_ROUTED_SWIGLU_QMV` (`:149-150`), `DARKBLOOM_PACKED_SCALES`
(`:165-166`), `DARKBLOOM_ROUTER_PRECOMPUTED_KEYS` (`:171-172`) and
`DARKBLOOM_ROUTED_GATEUP_R1` (`:7913-7914`) all default ON; the arm switch is at
`:8044-8056`; the call site is `Sources/MLXFastModel/LagunaRuntimeLayers.swift:2029`
behind the decode gate `x.dim(1)==1 && inds.size<64` (`:1984-1985`). Grid
`(8*256*64,1,1)`, threadgroup `(64,1,1)`.

The down path's default is the **generated** `..._sh_stage4_v6` from
`lagunaRoutedSharedDownResidualSource(sharedHalved: true, staged: true)`
(`:8278-8421`, staged qdot fragment `:8296-8317`); the literal `stage4_v6` at
`:8444-8548` only runs when the halved plane is absent, and
`laguna_routed_nvfp4_down_reduce_bf16_v2` (`:8067-8170`) is a fallback that never
runs on the scored path. The live down kernel has **no K loop at all**: it already
stages four `uint2` code words plus four scale bytes and then issues four qdots.
There is no MLP headroom left there, which is consistent with its 89.3 % of M4
roofline. It is therefore not a rung.

`mergedSharedActivated` (`LagunaRuntimeLayers.swift:2005`, read at `:2080`) is
never assigned, so the "fold the shared expert into the routed dispatch" hook is
dead code and not a lever.

### 2.4 What the numbers say about M5 headroom

M4 baseline for this branch (unchanged base, commit `61c8763`, job
`dda5bd02-2577-46ca-b862-ca471b5bf357`, `research/artifacts/fern-r98d-base-A.json`):

```
decode_seconds_per_token  = 0.0130002975234375
prefill_seconds_per_token = 0.00113808170703125
max_abs_diff = 0, passed_correctness = true
```

Steady step T ≈ 8.45 ms on M4 after removing the 512-token seed amortisation
(S = 512·P = 582.7 ms, S/128 = 4.553 ms). M4 is already at ~91 % of its roofline
on the routed gate/up kernel, so **M4 cannot show a win here — it can only show a
regression.** That still makes the local run a useful safety screen (bit-exactness
plus "did not get worse"), and the M5 receipt is the actual ranking test: M5's
steady step is ≈ 4.36 ms for the same ~1794 MB, i.e. ≈ 411 GB/s, leaving a 25-32 %
gap that the MLP hypothesis is the credible mechanism for.

## 3. Rung 1 — the edit

`lagunaRoutedSwiGLUQMVPackedTop8R1Kernel` source (`:7955-8010`) currently runs a
4-iteration K loop with **depth-1** software pipelining: it holds one block's
`gate_codes`/`up_codes` (16 B) plus its two scale bytes while computing the
previous block. Rung 1 hoists **all four** blocks' codes and scale bytes into
registers before the math loop:

- in flight per lane: **16 B → 64 B** of codes, 2 → 8 scale bytes;
- bytes read: unchanged;
- arithmetic: unchanged;
- accumulation order: unchanged (`gate_result += block0; += block1; += block2; += block3`, then the same `simd_sum` tail at `:8012-8013`);
- dispatch count: unchanged (an added dispatch costs 2.3403 µs = 0.0358 % score, so zero is the requirement).

If register pressure forces a spill, that is an **implementation defect, not a
falsification of H-D**, and I will report it as such and fall back to a depth-2
variant (32 B in flight) before drawing any conclusion.

## 4. Preregistration

Written and committed **before** any candidate receipt is read.

**Primary metric.** Decode µs/step, derived from each candidate's own score JSON,
never mixed across sessions. Cost model: decode 0.015280 % score per µs/step;
σ(score) = 0.6172 %; M4 detection bar ≈ 80 µs/step.

**Legs, in this order:**

1. **Rung 1 candidate** (depth-4 staging).
2. **Revert control** — the identical binary rebuilt from the unchanged base in the
   same session as leg 1's receipt. This is the leg that makes leg 1 interpretable;
   it is not optional and it is not skipped if leg 1 looks good.

**Advance rule.** Advance to a further rung only if *all* of:

- decode improves by **≥ 15 µs/step** versus the contemporaneous control;
- the revert-control leg lands within **1 prediction standard error** of the
  baseline it is meant to reproduce;
- prefill moves by less than **0.5σ**;
- `max_abs_diff == 0` and correctness passes.

**Stop rule.** Two consecutive clean non-positive rungs (bit-exact, no spill, no
dispatch change) ⇒ stop and write H-D up as **falsified**, with proposed rule text
for the research archive. A spill or a dispatch-count change makes a rung *not
clean* and it does not count toward the stop rule.

**Receipt budget.** 6. Planned spend: 1 candidate + 1 control per rung, ≤ 2 rungs,
leaving 2 in reserve. A queued receipt is watched with
`python3 senpai/watch-submission.py --submission <id>`; an HTTP 403 from receipt
fetch is the known open defect from #527 and is recorded rather than retried.

**Falsification is a publishable result here.** Rules 66-68 already killed three
"less work" mechanisms; killing the latency mechanism at the two largest exposed
MoE sites would leave the M5/M4 divergence needing a genuinely different
explanation, which is worth more than another inconclusive tweak.

## 5. Log

| when (UTC) | leg | receipt | decode s/tok | prefill s/tok | max_abs_diff | note |
|---|---|---|---|---|---|---|
| 2026-08-09T13:21:12Z | baseline A (M4, local) | — | 0.0130002975234375 | 0.00113808170703125 | 0 | unchanged base @ `61c8763` |
| 2026-08-09T13:31:20Z | rung 1 candidate (M4, local) | — | 0.0129596627578125 | 0.001121568765625 | 0 | depth-4 staging @ `0ff6d26` |
| 2026-08-09T13:39:40Z | revert control B (M4, local) | — | 0.01295040690625 | 0.001112815509765625 | 0 | base kernel again, bracketing the candidate |

### 5.1 Reading the M4 rung-1 screen

Decode is nominally 40.6 µs/token faster (−0.31 %). That is **below the ≈ 80 µs/step
M4 detection bar and is not evidence for H-D.** The tell is in the same JSON:
prefill moved −1.45 %, and the edited kernel is behind the decode gate
`x.dim(1)==1 && inds.size<64` so it **cannot** run during prefill. A metric that
must be exactly flat moved 1.45 %, which sets the cross-session noise floor for
this host well above the decode delta.

Also confirmed from the two JSONs: `baseline_decode_seconds_per_token` is
**identical** (0.01385621216015625) in both runs, i.e. the local harness compares
against *pinned calibration*, not a same-session paired baseline. `decode_speedup`
is therefore a rescaling of the raw seconds and carries no extra information, so a
contemporaneous revert control is required locally. The **official M5 receipt does
run candidate and baseline back to back in one session**, so the receipt is
self-paired and does not need a separate control leg.

What the screen does establish, which is what it was for: `max_abs_diff = 0`,
correctness passed over 130 checked steps, identical `golden_hash`, and **no
regression** — so the depth-4 staging did not spill badly enough to cost time on a
host that is already at 91 % of its roofline at this site.

### 5.2 The upstream-equivalence oracle fails identically on the unchanged base

`research/run_upstream_equivalence.sh` fails on the candidate — but only on the
**prefill** step, and the failure is *byte-identical* to the unchanged base run:

| step | candidate `0ff6d26` | base `61c8763` |
|---|---|---|
| prefill max abs logit error | 0.125 | 0.125 |
| prefill mean abs logit error | 0.011933609 | 0.011933609 |
| prefill argmax token | 5991 == 5991 | 5991 == 5991 |
| decode-0 … decode-7 max abs error | 0.0 (all eight) | 0.0 (all eight) |
| `EQUIVALENCE_EXACT_STEPS` | 8 | 8 |

Logs: `research/artifacts/fern-r98d-rung1-oracle.log` and
`research/artifacts/fern-r98d-control-oracle.log`.

So the divergence is **pre-existing on this M4 Pro host and my change contributes
exactly zero of it**, which is what the mechanism predicts: the edited kernel is
decode-gated, and every decode step is bit-identical. AGENTS.md documents the
cause — M4 Pro reports Apple GPU generation 16 and does not select the `_nax`
prefill kernels the ranked M5 uses — and the oracle is named
`lagunaRuntimeMatchesVendoredUpstreamOnM5WhenEnabled`. The argmax still matches,
so no token changes. This is the "test the unchanged base" case from AGENTS.md,
resolved by measurement rather than by assumption, and it did not cost a receipt.

### 5.3 The revert control kills the local M4 reading outright

`research/fern-r98d-compare.py` over the three bracketing runs:

```
base A  13:21:12  61c8763  decode 0.0130002975  prefill 0.001138082
cand    13:31:20  0ff6d26  decode 0.0129596628  prefill 0.001121569
base B  13:39:40  a78c43c  decode 0.0129504069  prefill 0.001112816   (base kernel again)

cand - base mean  = -15.7 us/token (-0.121 %)
base B - base A   = -49.9 us/token (-0.384 %)   <- identical code, both legs
prefill B - A     = -2.22 %                     <- must be exactly 0 by construction
```

**The control-only spread between two runs of identical code is −49.9 µs/token,
three times the candidate's apparent −15.7 µs/token effect**, and both decode and
prefill drift monotonically downward with wall-clock across all three runs. That
is a warm-up/thermal trend, not code.

My preregistered advance threshold was "≥ 15 µs/step versus the contemporaneous
control". The candidate nominally clears it at −15.7 µs — and I am **not** going to
claim that, because the control leg proves the threshold was set below this host's
own drift. The honest statement is that **the M4 screen has no resolving power for
this effect**; the threshold was mis-set, and the control is what revealed it. This
is precisely why the revert leg was preregistered as non-optional.

The screen's remaining value is unchanged and is the value it was designed for:
bit-exact (`max_abs_diff = 0`, all decode oracle steps exactly 0), correctness
passing, and **no regression** — a badly spilling kernel would have shown up well
outside a 50 µs/token band.

### 5.4 Decision: spend receipt 1 on M5

Local evidence cannot settle H-D and, per §2.4, was never going to: M4 is already
at 91 % of its roofline at this site. The M5 receipt is the right instrument
because it is **self-paired** — candidate and baseline run back to back in one
session behind the same 40 C thermal gate — so it does not inherit the
cross-session drift that just swamped the local screen. Risk is bounded: the
change is bit-exact and shows no regression, so the downside is one receipt, not a
broken submission. Receipts spent so far: 0 of 6.

### 5.5 `./benchmark.sh --local-submit` preflight (candidate, commit `30dbb4c`)

Artifact: `research/artifacts/fern-r98d-rung1-localsubmit.json`
(job `3ba63234`, exit 0, `timestamp 2026-08-09T13:44:12Z`).

```
passed                        true
score (pinned-calibration)    1.0527428318869918
passed_correctness            true
max_abs_diff                  0
checked_steps                 1025
error                         ""
first_failing_case/step/layer null / null / null
decode_seconds_per_token      0.008946454056695993
decode_speedup                1.5487937536308634   passed_decode_speedup_floor true
prefill_seconds_per_token     0.00111165966796875
prefill_speedup               0.3306042305480922   passed_prefill_speedup_floor false
golden_hash                   f49e4c2c...
weights_hash                  aff99430...
```

Two readings that must not be confused:

1. **Correctness is clean and it is the strong claim here.** 1025 checked steps,
   `max_abs_diff = 0`, empty `error`, no failing case/step/layer. Combined with the
   byte-identical upstream-equivalence oracle (§5.2) the candidate is bit-exact
   against its own base on this host.
2. **The speedups in this file are *not* the ranked verdict.** Local
   `--local-submit` divides by *pinned calibration* constants
   (`baseline_decode_seconds_per_token = 0.01385621216015625`,
   `baseline_prefill_seconds_per_token = 0.00036751938916015626`) that are M5
   numbers, not a same-session M4 baseline. That is why `decode_speedup` reads a
   fictitious 1.549 and `prefill_speedup` a fictitious 0.331 on an M4 Pro: this
   host's prefill is roughly 3x the pinned M5 prefill because it never selects the
   `_nax` prefill kernels. `passed_prefill_speedup_floor = false` here is a
   statement about M4-vs-pinned-M5, not about the candidate; the unchanged base
   produces the same failure. The paired ranked verdict comes only from the M5
   receipt.

So the local gate delivers exactly what §5.3 left it: bit-exactness plus "no
regression", and no timing signal. Proceeding to receipt 1.

