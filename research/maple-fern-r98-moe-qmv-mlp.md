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


## 6. Terminal state: cancelled by advisor HOLD

The arm was halted at 13:46:53Z by the advisor HOLD, which replaced the research
base with the promoted organizer frontier. I am reporting **cancelled**, not a
result: no timing claim is made, and the candidate is not merge-eligible because
the base it was written against no longer exists in the form it assumed.

Full HOLD compliance and the requested occupancy numbers are in
`research/maple-fern-r98d-occupancy-and-m4-record.md`.

## 7. Revision `r99-e-rev1` — H_F probe

### 7.0 Hypothesis under test

**H_F**: the codegen tax maple-nezuko measured in the sliding-attention family is
*family-specific*, not a general property of restructuring Metal source. If it is
general, then any source restructuring of the routed gate/up QMV kernel pays a
flat penalty regardless of how much extra work is staged. If it is
family-specific, staging depth should move the cost *monotonically* — that is
real ILP, and H_F is supported.

Both outcomes are publishable. A flat penalty independent of staging depth
falsifies H_F and generalises nezuko's finding; a monotone dose-response supports
H_F and localises nezuko's finding to her kernel family.

### 7.1 The instrument

The scored `--local-iterate` loop cannot answer this: round 98-D showed its
identical-code control spread on this M4 host is −49.9 µs/token, far larger than
any plausible single-kernel effect. So this revision uses a **standalone paired
GPU probe** that compiles two fully-resolved MSL sources and times the routed
gate/up kernel directly.

Three research-only files (not on the submitted surface):

| file | role |
|---|---|
| `research/fern_r99_dump_header.sh` | dumps the compiler-resolved MSL string literals out of the runtime |
| `research/fern_r99_qmv_variants.py` | emits fully-resolved, standalone-compilable `.metal` variants |
| `research/fern_r99_qmv_probe.swift` | paired A/B timing harness (`xcrun swiftc -O … -o /tmp/fernqmv`) |

**Why a dumper was needed.** nezuko's extractor cannot read this literal: the
routed gate/up source contains four `\(…)` interpolations, so the on-disk text is
not valid MSL. `fern_r99_dump_header.sh` runs a temporary `@testable` test that
prints the *compiler-resolved* strings. Artifacts are committed under
`research/artifacts/fern-r99/`:
`shared_qmv_header.metal` (2547 B), `router_top8_prologue.metal` (1182 B),
`row_scale_suffix.txt` = ` * 4194304.0f`, `routed_gateup_r1_enabled.txt` = `true`.
That last file is the load-bearing one: it confirms from the runtime itself, not
from reading the flag default, that the pipelined R1 arm is what actually ships.

The generator resolves those interpolations
(`\(lagunaScalePatchHeaderBytes)`→128, the router prelude, the row-scale suffix)
and emits five variants, all of which compile clean under
`xcrun -sdk macosx metal -c`:

| variant | bytes | staged bytes | role |
|---|---|---|---|
| `depth1_shipped.metal` | 9561 | 16 | shipped rolling depth-1 prefetch — **common reference** |
| `tmpl_s1.metal` | 9546 | 16 | chunked template, S=1 |
| `tmpl_s2.metal` | 9546 | 32 | chunked template, S=2 |
| `tmpl_s4.metal` | 9546 | 64 | chunked template, S=4 |
| `stage4_cand.metal` | 9481 | 64 | the branch's actual rung-1 text |

`tmpl_s1` vs `depth1_shipped` isolates **pure source restructuring at identical
staged work** — that is the direct nezuko-tax probe. `tmpl_s1 → s2 → s4` is the
**dose**. `tmpl_s4` vs `stage4_cand` is a template-fidelity check, not a dose step.

All arms share one deterministic xorshift-filled buffer set (input bf16×2048,
257 MiB fused weight, packed scales, 256 router keys, 8×4096 activation), so
every arm sees identical NVFP4 codes, identical branch patterns and identical
router winners. Timing follows nezuko's proven method: serial compute encoder,
`reps` dispatches per command buffer, `(gpuEndTime − gpuStartTime)·1e6/reps`,
with the lead arm alternated on odd rounds so slow drift cancels within a round.

**The probe is ordering-enforcing by construction.** Invoked with one file it
runs a null control only; a dose number cannot be printed until extra arguments
are supplied. It was therefore impossible to see a candidate number before the
null spread.

### 7.2 Occupancy-matched dispatch derivation

The shipped dispatch for `laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2`
is **2048 threadgroups × 64 threads**, i.e. 2 simdgroups per threadgroup. On the
ranked **M5 Max (40 GPU cores)** that is

```
2048 TG / 40 cores = 51.2 TG per core
```

This host is an **M4 Pro, `applegpu_g16s`, 20 GPU cores**. Reproducing the M5's
*per-core* occupancy therefore requires

```
TG_m4 = 2048 × 20 / 40 = 1024
```

**TG = 1024 is the occupancy-matched operating point** and is the row the verdict
is read from. Running the shipped TG = 2048 on this host would put 102.4 TG/core
— double the ranked machine — which is a different residency regime.

This is also a completely different regime from nezuko's arm: her kernel runs
K = 16 threadgroups, i.e. **0.8 TG/core** on M5, where a core may hold a single
threadgroup and register pressure translates directly into idle cores. At 51.2
TG/core the scheduler has ~64× more threadgroups to hide latency with. That
difference is the mechanistic reason H_F is worth testing rather than assuming
nezuko's result transfers.

The ladder spans 128 / 256 / 512 / 1024 / 2048 TG (6.4 → 102.4 TG/core) so the
occupancy dependence of any effect is visible, not just its value at one point.

### 7.3 Null control (run first, reported before any candidate number)

Identical source in both slots. Device line from the probe:
`Apple M4 Pro, applegpu_g16s, 20 GPU cores`.

A first pass at 100 reps/round was too noisy to preregister against (TG = 512
reference drifted 18.65 → 10.72 µs between passes, i.e. it had not warmed). Reps
were raised to 500/round and the null re-run **twice**. That tuning was done
against the null only — no candidate had been compiled into a timing run at that
point — which is precisely what a null control is for. All three null passes are
reported.

**Null pass A** — 21 rounds × 100 dispatches (rejected as under-warmed, shown for
completeness):

| TG | TG/core | ref_min µs | d_mean | d_sd | spread |
|---|---|---|---|---|---|
| 128 | 6.4 | 6.55 | +0.139 | 0.626 | 2.84 |
| 256 | 12.8 | 10.05 | +0.454 | 0.968 | 3.43 |
| 512 | 25.6 | 18.65 | −0.192 | 0.802 | 2.72 |
| 1024 | 51.2 | 20.97 | +0.133 | 0.619 | 2.23 |
| 2048 | 102.4 | 36.44 | −0.185 | 0.280 | 1.01 |

**Null pass B** — 21 rounds × 500 dispatches:

| TG | TG/core | ref_min µs | d_mean | d_sd | d_min | d_max | spread |
|---|---|---|---|---|---|---|---|
| 128 | 6.4 | 4.57 | −0.376 | 1.731 | −7.92 | +0.40 | 8.31 |
| 256 | 12.8 | 6.83 | −0.018 | 0.012 | −0.05 | +0.00 | 0.05 |
| 512 | 25.6 | 10.72 | −0.086 | 0.059 | −0.25 | +0.03 | 0.28 |
| 1024 | 51.2 | 21.49 | −0.016 | 0.151 | −0.30 | +0.30 | 0.60 |
| 2048 | 102.4 | 34.22 | −0.035 | 0.122 | −0.24 | +0.36 | 0.60 |

per-round deltas, TG=1024:
`+0.23 −0.09 +0.03 −0.13 −0.15 +0.07 +0.02 +0.05 −0.04 +0.04 +0.30 −0.05 +0.01 −0.25 −0.11 −0.07 −0.30 +0.05 +0.25 −0.04 −0.14`

per-round deltas, TG=2048:
`−0.02 −0.03 +0.01 −0.24 −0.12 −0.04 −0.09 +0.05 −0.03 +0.03 +0.06 −0.10 −0.02 −0.06 −0.24 +0.03 −0.04 −0.04 −0.04 +0.36 −0.16`

**Null pass C** — independent replicate, 21 rounds × 500 dispatches:

| TG | TG/core | ref_min µs | d_mean | d_sd | d_min | d_max | spread |
|---|---|---|---|---|---|---|---|
| 128 | 6.4 | 4.57 | −0.396 | 1.567 | −7.07 | +0.31 | 7.37 |
| 256 | 12.8 | 6.81 | +0.028 | 0.125 | −0.03 | +0.40 | 0.44 |
| 512 | 25.6 | 10.69 | −0.069 | 0.064 | −0.19 | +0.04 | 0.24 |
| 1024 | 51.2 | 21.38 | −0.030 | 0.141 | −0.33 | +0.19 | 0.52 |
| 2048 | 102.4 | 33.99 | +0.131 | 0.592 | −0.19 | +2.54 | 2.72 |

per-round deltas, TG=1024:
`−0.08 −0.02 +0.00 −0.09 −0.11 −0.17 +0.10 +0.08 −0.04 −0.14 −0.33 +0.04 +0.17 +0.00 −0.18 −0.16 +0.06 +0.13 +0.19 +0.13 −0.22`

per-round deltas, TG=2048:
`−0.07 −0.11 −0.02 +0.05 −0.07 +0.01 −0.07 +0.05 +0.01 −0.19 −0.12 −0.01 +0.07 +0.10 −0.09 +0.91 +2.54 −0.03 −0.06 −0.08 −0.04`

**Reading of the null.** With 500 reps/round the paired instrument is tight: the
null mean is |d_mean| ≤ 0.13 µs everywhere above TG = 128, and ≤ 0.03 µs at the
occupancy-matched TG = 1024 in both replicates. The `spread` statistic (max−min
of 21 rounds) is not robust — it is set by one or two isolated rounds
(TG = 128 round 1 is a −7.9 µs global warm-up transient; TG = 2048 pass C round
17 is a single +2.54 µs excursion) — so it is a deliberately conservative bar.

### 7.4 Preregistered detection threshold

Per the brief, the threshold is **3× the measured null spread**, taken as the
worst case across the two accepted 500-rep null replicates (B and C), per TG.
nezuko's ±0.5 % is *not* reused.

| TG | TG/core | null spread B | null spread C | worst-case | **threshold = 3× spread** | as % of ref |
|---|---|---|---|---|---|---|
| 128 | 6.4 | 8.31 | 7.37 | 8.31 | 24.93 µs | 545 % (unusable) |
| 256 | 12.8 | 0.05 | 0.44 | 0.44 | **1.32 µs** | 19.4 % |
| 512 | 25.6 | 0.28 | 0.24 | 0.28 | **0.84 µs** | 7.8 % |
| **1024** | **51.2** | 0.60 | 0.52 | **0.60** | **1.80 µs** | **8.4 %** |
| 2048 | 102.4 | 0.60 | 2.72 | 2.72 | 8.16 µs | 24 % |

**Decision rule, fixed before any candidate was timed:**

1. The verdict row is **TG = 1024** (occupancy-matched to the ranked M5).
   Threshold **|d_mean| ≥ 1.80 µs/dispatch**.
2. TG = 128 is **excluded from the verdict**: its null spread is 545 % of the
   reference, so it has no detection power. It is still reported.
3. A **monotone dose-response** across `tmpl_s1 → s2 → s4` that clears the
   threshold at TG = 1024 with `d_mean < 0` supports **H_F** and licenses one
   paired `--local-iterate` leg.
4. A **flat penalty** — `tmpl_s1` already paying most of the cost, with `s2`/`s4`
   adding little — falsifies **H_F** and generalises nezuko's codegen tax. No
   receipt is spent.
5. Anything under threshold is reported as **no detectable effect**, which is
   itself informative: it bounds the codegen tax in this family at < 1.80 µs on a
   ~21.4 µs kernel, i.e. **< 8.4 %**, versus the tax nezuko measured in hers.
6. **Zero receipts unless rule 3 fires with the right sign.**

Secondary statistic, reported for sensitivity only and **not** the gate: 3× the
null `d_sd` at TG = 1024 is 3 × 0.151 = **0.45 µs**. Where the primary and
secondary rules disagree, the primary (3× spread) governs and the disagreement is
stated explicitly.

### 7.4b Output-equivalence gate added before the dose ladder

A timing instrument that silently computes something else is worthless, so the
probe was extended (commit `3841f36`) with a byte-level equivalence gate that
runs **before** timing:

- `dActivated` is poisoned with `0xA5` between arms, so a kernel that fails to
  write is caught rather than inheriting the previous arm's output.
- Each arm runs once at TG = 1024 and once at TG = 2048; every output byte is
  compared against the `depth1_shipped` reference.
- A reference-vs-reference re-run is included as a determinism self-check.

**Result: 0 / 65536 differing bytes for every arm at both TGs, and 0 for the
determinism self-check.** The four variants are bitwise identical to the shipped
kernel on this input, which is consistent with the source-level claim that
addresses, bytes and `qdot` accumulation order are untouched. This is a
necessary, not sufficient, correctness argument — the authoritative gates are
`LagunaUpstreamEquivalence` and the hidden M5 suite.

### 7.5 Dose ladder — results

Two independent replicates, run back to back, `FERN_ROUNDS=21`, `FERN_REPS=500`.
`d_mean` is candidate − reference in µs/dispatch; **negative = candidate faster**.

| arm | staging bytes | TG=1024 rep 1 | TG=1024 rep 2 | TG=2048 rep 1 | verdict vs 1.80 µs |
|---|---|---|---|---|---|
| `tmpl_s1` | 16 B | **−3.002** | **−3.087** | −3.2 | **clears, faster** |
| `tmpl_s2` | 32 B | **−3.096** | **−3.142** | −3.4 | **clears, faster** |
| `tmpl_s4` | 64 B | **−2.860** | **−3.162** | −3.6 | **clears, faster** |
| `stage4_cand` | 64 B | −1.804 | −1.841 | −3.3 | at threshold, faster |

Pipeline reflection for all arms: `threadgroupMemoryLength` 0 B,
`maxTotalThreadsPerThreadgroup` 1024, `threadExecutionWidth` 32. Generated line
counts 256 / 254 / 254 / 254 / 253. **No arm lost occupancy** — the register
pressure risk flagged in §7.2 did not materialise at any staging depth.

### 7.6 What the ladder actually shows — the proposed mechanism is falsified

Two things are true at once, and separating them is the result:

**(a) The direction is the opposite of nezuko's codegen tax.** Every restructured
variant is ~14 % *faster* than the shipped depth-1 body, clearing the
preregistered 1.80 µs threshold with `d_mean < 0`. In its literal form —
"restructuring this kernel body does not impose nezuko's penalty here" — **H_F is
supported**, and the tax does not generalise across kernel families. Decision
rule 3 fires and licenses one `--local-iterate` leg.

**(b) The dose is flat, so the *staging-depth* mechanism is falsified.** Going
16 B → 32 B → 64 B moves `d_mean` by ≤ 0.08 µs between replicate-matched arms —
about 2.5 % of the effect, well inside the 0.60 µs null spread and far under the
1.80 µs threshold. Depth-1 already captures essentially the whole win. The
round-98 premise that *deeper staging buys ILP* is **not what is happening**.

The `diff` of `depth1_shipped.metal` against `tmpl_s1.metal` locates the real
mechanism. The shipped kernel runs a **runtime-trip-count four-iteration K loop
with an `if (next_block < input_width)` prefetch guard**; every template variant
is `#pragma clang loop unroll(full)` over a `constexpr` trip count. The win is
**full unrolling of a four-block K loop** — removal of the loop-carried guard and
trip test — and staging depth is a passenger. That is why the shipped candidate
kept `stage_depth = 1`: it is the cheapest form that carries the whole effect,
with scalars rather than arrays and therefore the lowest register footprint on
the M5 I cannot measure.

**A third observation, reported but not claimed.** `tmpl_s4` and `stage4_cand`
are both 64 B staged and both fully unrolled; they differ only in scoping and
index naming, and they differ reproducibly by ~1.3 µs/dispatch. That is under the
conservative 1.80 µs threshold, so it does not meet my own bar for a claim. It
does mean cosmetically equivalent rewrites are **not** free in this family, which
is why the committed body is the exact measured `tmpl_s1` text rather than a
hand-collapsed version of it.

### 7.7 Caveat that bounds the claim

The probe is a **relative codegen instrument, not a performance measurement**.
Its working set is synthetic: at TG = 1024 it writes 4096 B of a 65536 B buffer,
at TG = 2048 it writes 8192 B. Real decode dispatches this kernel against
resident expert weights with a different cache footprint and different
neighbouring work in the command buffer. The probe can say *this kernel body
compiles to faster code at matched occupancy*; it cannot say *decode gets
faster*. Only the in-situ paired leg can, and on this M4 Pro even that is below
the ≈80 µs/step detection bar established in §5.3. The honest ceiling on what
this rung can establish locally is therefore: **the mechanism is real and
correctly signed, the end-to-end magnitude is unmeasurable here.**

### 7.8 In-situ leg and correctness

_(pending)_

## Reply (r98-d rung — retained for the record, superseded by the Reply below)

**1. Your occupancy request is answered, and it dissolves the confound for this
rung.** The table (six kernels, grid / threads-per-TG / TG count / simds-per-TG)
is in the record file. The key line: my rung changes only the kernel body, and
`git diff <base> HEAD -- Sources/` contains **no `grid:` or `threadGroup:` hunk
at all**. Both legs dispatch 2048 TGs × 64 threads. So this rung raises ILP at
**fixed** TLP — it is not one of the "more rows per simdgroup" rungs your warning
targets, and a negative here would be attributable to ILP or register pressure
alone. The residual risk is *residency* loss from register pressure at fixed
geometry, which the table cannot show; the prepared fallback was a depth-2 (32 B)
variant.

**2. Correction to my own earlier statement: the branch is rooted on
`e510bb3d`, not `450953e5`.** Verified by `git merge-base`. Since you confirmed
`450953e5` was inert on the submitted surface and said no rebase was needed, I
never took it. So every measurement here is on **exactly** the base your HOLD
names as unpushable. That reinforces, not weakens, the decision to claim nothing.

**3. No receipt was spent and no submission exists.** A `mlxfast submit` had been
dispatched minutes before your HOLD; it failed *client-side* note-length
validation in 0.6 s, before any network call. I verified against the server
rather than assuming: `mlxfast submissions` returns 141 rows, none carrying any
commit from this branch. **Budget intact at 6 of 6.** I did not retry, per the
standing rule that a non-explicit-rejection failure must not be retried.

**4. Three findings from rung 0 that may shorten your audit.** All were measured
on the old tree and all need re-derivation, but the *questions* they answer are
base-independent and worth carrying into whatever replaces this brief:

- **The brief's nominated Site 1 was dead code**, on two independent grounds:
  `laguna_shared_nvfp4_swiglu_qmv_rows1_halved_wide_bf16_v1` requires
  `DARKBLOOM_QMV_WIDE_CODES=1`, which defaults OFF, *and*
  `RESEARCH_ARCHIVE_through-round-91.md:267` records that variant as **not
  bit-exact**. Any successor brief should re-check the flag default before
  re-nominating it.
- **You asked which routed-QMV arm ships by default: the pipelined R1 arm did.**
  So the "free win" hypothesis in the brief was not available — but the arm was
  only depth-1 over a 4-block K loop, which is what made deepening it the real
  lever rather than introducing pipelining from scratch.
- **The down/residual family had no staging headroom**: the shipped default was
  a *generated* `..._sh_stage4_v6` with no K loop, already fully staged, at
  89.3 % of this host's roofline; `down_reduce` was a never-taken fallback. This
  is the finding most at risk from your swap, since it is exactly the family you
  say was rewritten — but if the frontier's version is similarly staged, rung 2
  as written has no target and the successor brief should say so up front.

**5. The methodological result is the durable one, and it is a negative about my
own instrument.** I preregistered a 15 µs/step advance bar and a mandatory revert
leg. The candidate cleared the bar at −15.7 µs/token — and the revert leg showed
the identical-code control spread was **−49.9 µs/token**, three times larger,
with prefill drifting −2.2 % when it must be exactly 0 by construction. The bar
was set below the host's own drift. I am not claiming the number. Had I skipped
the revert leg I would have reported a false positive, which is precisely the
rule-68 failure mode you built the protocol to catch. Suggest the successor brief
require the control leg's *measured* spread to be reported **before** any
threshold is fixed, rather than fixing the threshold from the price list.

**6. What I want escalated.** If the frontier's MoE gate/up kernel is still
shallow-pipelined, H-D remains open and cheap to test, and the transformation is
byte-negative (−80 B), so it survives the collapsed 16,151 B headroom where new
kernel variants would not. If the frontier already stages it deeply, that is
itself evidence for H-D from the organizer's own solver, and the round-98 thesis
should be updated on that basis rather than on a fresh receipt.

