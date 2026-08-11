# R116-A — is the shipped-defaults audit a dead axis?

frieren, PR #705, written 2026-08-11T04:25Z, **before** the confirmation stage
finished (blocks 1–3 of 9 visible, blocks 4–9 still in flight).

The advisor asked at 03:50Z:

> If you think this whole audit is now a dead axis … say that in a committed
> file and argue it. I would rather redeploy you at 04:15Z than have you spend
> six hours confirming a null.

This is that file. Short answer: **yes, the axis is dead as a source of
shippable speed, and I recommend redeployment.** I want the in-flight
confirmation to finish (ETA ≈ 05:48Z) because it converts "nothing looked
faster" into a *numbered bound*, and because the host cannot run anything else
while it holds the benchmark lock. I do **not** want blocks 10–15. The argument
for both halves is below.


## 1. The minimum shippable effect, in micro-seconds

Campaign conversion (banked, r109): **0.00836 % of score per M4 wall µs/step at
τ = 1**, from `%score = 0.75 × τ × Δwall_µs / 8972`.

The advisor's 03:50Z screening threshold is "≥ +0.25 % **before** τ correction".
Inverting:

| bar | µs/step on this host | what it delivers on M5 at τ = 0.4 |
|---|---|---|
| campaign screening threshold (+0.25 % pre-τ) | **29.9 µs/step** | 0.10 % of score |
| +0.25 % *delivered* after τ = 0.4 | **74.8 µs/step** | 0.25 % of score |

So an arm in this audit has to move the steady decode step by **≥ 30 µs** to be
worth carrying to ABBA at all, and by **≥ 75 µs** to be worth the crown-odds
arithmetic fern published (×1.48 per +0.10 %).


## 2. What the screen actually bounded

9 arms, 27 runs, 3 paired blocks, all `passed_correctness=true`, a single golden
hash `b9509697…` across every run (so every arm is bit-exact — this is measured,
not assumed). Raw evidence in `research/frieren_r116_screen_results.jsonl` and
`research/frieren_r116_screen_steady.json`; W&B group `r116a-screen`.

Observed contrast range across all 8 non-control arms: **[−10.9, +51.1] µs**.

The only arm that cleared 30 µs in magnitude is `sfd1`
(`DARKBLOOM_SHARED_FIRST_DOWN=1`) at **+51.1 µs, t = +13.10** — i.e. decisively
in the *wrong* direction. Its default-OFF is correct and that is now settled.

Every other arm sits inside ±27 µs, which is inside the screening threshold
before any statistics are done.

**Honest caveat on screen power.** A 3-block screen has per-arm sem 3.9–26.3 µs.
Against a 29.9 µs true effect that is t = 7.7 on the quietest arm and t = 1.14
on the noisiest. So the screen alone was *not* powered to rule out a marginal
30 µs win on the noisier arms. That is exactly the gap the confirmation stage
was designed to close, and it is why I am letting it finish rather than
declaring the null now.


## 3. Why 12 blocks is the right stopping point, and 18 is not

Confirmation arms carry these 3-block screen sems: `qmvse0` 6.8, `sc0` 15.3,
`qmvsc0` 16.8 µs. sem scales as 1/√blocks. At the pooled block counts:

| arm | sem @ 3 (screen) | sem @ 12 (3 screen + 9 confirm) | t for a 30 µs effect | sem @ 18 | t @ 18 |
|---|---|---|---|---|---|
| `qmvse0` | 6.8 | 3.4 | **8.8** | 2.8 | 10.8 |
| `sc0` | 15.3 | 7.7 | **3.9** | 6.2 | 4.8 |
| `qmvsc0` | 16.8 | 8.4 | **3.6** | 6.9 | 4.3 |

**12 paired blocks is the first point at which the campaign's own minimum
shippable effect is resolvable at t ≥ 3 on all three candidate arms.** Blocks
13–18 buy resolution *below* 30 µs — a region that, by the campaign's published
economics, cannot change any decision. Six more blocks ≈ 2 h of exclusive host
time to sharpen a number nobody is allowed to act on.

That is the whole argument for stopping at 12. It is a stopping rule derived
from the decision threshold, not from the data.


## 4. The one live thread, pre-committed before the data lands

Blocks 1–3 of the confirmation currently read:

| arm | pairs | delta_us | sem | t |
|---|---|---|---|---|
| `qmvsc0` | 2 | **−20.2** | 3.1 | −6.59 |
| `qmvse0` | 3 | +2.3 | 7.8 | 0.30 |
| `sc0` | 2 | +12.7 | 8.7 | 1.46 |

`qmvsc0` (`DARKBLOOM_NVFP4_QMV_SIGN_CARRY=0`) has **flipped sign against its own
screen result** (+26.5 µs, t = 1.58 → −20.2 µs, t = −6.59). On 2 pairs and 1
degree of freedom that t is not evidence of anything; I record it only so that
nobody can later accuse me of having discovered it after choosing a stopping
rule.

I am pre-committing the disposition now, with 6 of 9 confirmation blocks
unmeasured:

1. **My own preregistration (`research/frieren_r116_confirm_prereg.md`, rule 1)
   requires the confirmation sign to agree with the screen sign.** `qmvsc0`
   already fails that gate and cannot be landed by me under any confirmation
   result. I am not going to weaken rule 1 to let my argmax through.
2. If the 12-block interval on `qmvsc0` excludes zero on the win side, the
   correct output is a **named, priced follow-up handed to the advisor** with
   the exact re-test design — not a landing. It is bit-exact (proven by the
   shared golden hash), so it costs three characters to land whenever someone
   with a clean prereg wants it.
3. Even the best case is small. −20.2 µs = **0.169 % pre-τ, 0.068 % delivered
   at τ = 0.4**. It does not clear the screening threshold, let alone the
   +0.25 % delivered bar.

So the axis does not become live again even if `qmvsc0` is real.


## 5. Census completeness — the axis is closed, not merely unpromising

An audit is only a closure if the enumeration is complete. Every
`DARKBLOOM_*` default-OFF flag in the runtime (`environment[...] == "1"`) is now
dispositioned:

| flag | site | disposition |
|---|---|---|
| `TRACE_FUSION` | LRM:76, LmHeadPrune:101 | diagnostic tracing, not a perf lever |
| `FUSED_QKV` | LRM:114 | **prefill-only** — prepared LRM:11844, consumed LRM:6068 under `L > 1`; decode is L=1. Also materializes a dense BF16 fused weight (memory risk at 48 GB) |
| `QMV_WIDE_CODES` | LRM:325 | closed r109: +35.2 µs/step, t = +25.23 (`N-WIDE-CODES-SLOWER`) |
| `NATIVE_AFFINE_SUFFIX` | LRM:366 | used only at LRM:392 as a kernel-name suffix for affine INT8; this checkpoint is NVFP4 g16/b4 throughout — dead |
| `ROPE_ATLAS_VIEWS` | LRM:627 | shadowed: LRM:11538/:11602 reach it only as `else if` after the default-ON `lagunaRoPEAngleAtlasEnabled` — unreachable |
| `SHARED_FIRST_DOWN` | LRM:8219 | **screened: +51.1 µs/step, t = +13.10.** Default OFF is correct |
| `PREFILL_ROUTER_TOP8` | LRM:9660 | prefill-only, and prefill is adjudicable nowhere on this host (`is_nax_available()` false) |
| `ATTN_SCALE_NARROW_LOG` | LagunaRuntimeWeights:728 | **new this turn** — it only *reports* which scale plane each attention tensor landed on (comment at :724). A logger, not a lever |

`ATTN_SCALE_NARROW_LOG` was the last unscreened default-OFF decode flag in my
inventory and it turns out to compute nothing. **There is no unscreened
default-OFF decode flag left.**

On the default-ON side, flipping a default ON→OFF selects the fallback path by
construction, so the prior is "slower". The screen tested five of them
(`SCALE_CARRY`, `QDOT_SEED_ELIDE`, `SCALE_DEFER`, `QMV_SEED_ELIDE`,
`QMV_SIGN_CARRY`) plus both `NIBBLE_SPLIT` alternatives, and every one came back
null-to-worse. `NIBBLE_SPLIT` independently reproduces tanjiro's
`N-NIBBLE-SPLIT-DEFAULT-IS-OPTIMAL` from #692 (my `ns0` +15.7, `ns2` +13.8).


## 6. Why the axis was always going to be dead — the mechanism argument

Every flag in this audit is a *source-substitution* switch: it changes which
Metal source string is spliced into a kernel. It changes ALU instruction
selection, accumulator seeding, or scale-decode arithmetic. It does not change
bytes moved, dispatch count, or threadgroup geometry.

The campaign has now priced all four mechanism classes:

| mechanism | verdict | source |
|---|---|---|
| ALU instruction count | **dead** — deleting *every* removable extraction instruction across the whole NVFP4 path buys 0.21 % | `L-NVFP4-ALU-CONVERTS-AT-5-PERCENT`, tanjiro |
| dispatch count | **dead** — 0.4478 µs/dispatch, and removal is not symmetric (nezuko: −204.9 µs busy → wall *up* +51.73) | `N-DISPATCH-REMOVAL-NOT-SYMMETRIC` |
| threadgroup geometry | **dead** — τ ≈ 0 | advisor 03:50Z |
| bytes | open | advisor 03:50Z, "that leaves bytes" |

**This audit lives entirely inside the ALU class.** `L-NVFP4-ALU-CONVERTS-AT-5-PERCENT`
prices the *entire* class at 0.21 % of score if you delete every removable
instruction everywhere. A single default flip is a small fraction of that
ceiling. The audit was priced at approximately zero before I measured a single
step, and the measurement agrees.

That is the honest terminal statement: **`N-DEFAULTS-ALREADY-OPTIMAL`**, and the
deeper reason is `L-NVFP4-ALU-CONVERTS-AT-5-PERCENT`, not luck.


## 7. Two instrument defects, disclosed

1. **Failed runs are silently never retried.** `frieren_r116_confirm_run.sh`
   skips a block when `score-<arm>-b<n>.json` exists, so it can resume a
   timed-out job. A run that *fails* also writes that file. `qmvsc0-b1` failed
   at 03:46Z — `error = "local GPU cool-down gate failed for prefill with
   status 1"`, GPU stuck at 43.0 C against a 40 C target for 180 s — and the
   resume logic would skip it forever. **Not correctness**: `passed_correctness`
   is false only because no timing phase ran. I will refill the hole by deleting
   the failed score JSON and re-invoking the runner after the job ends, and I
   will report `qmvsc0` both with and without that out-of-order refill. I am not
   editing the script while it is executing.
2. **One further cool-gate near-miss**: `sc0-b1` waited 120 s before passing.
   Every other run cooled in ≤ 10 s. This is the second cool-gate incident I
   have recorded on this branch (the first is disclosed in commit `1f648b3b`)
   and it is an argument against extending to blocks 10–15 on a host that has
   been benchmarking continuously for six hours.


## 8. Redeployment proposal

I would rather be pointed at something live than sharpen this null. Ranked, with
citations, and with what I already know about who owns what:

1. **`residual_rms_router_bf16_2048_rpg8_keys_v1_pf1`** — 256.4 µs/step, 60.3 %
   of peak bandwidth, ≈ 40 µs of corrected headroom, `LagunaRuntimeModel.swift:1131`.
   Genuinely byte-side (it is 40 % off the roofline, so there is traffic to
   remove), and I believe unstaffed. This is the best fit to "that leaves bytes".
2. **`rmsbfloat16`** — 88.7 µs/step at 9.1 % of peak. Small and
   latency-bound rather than byte-bound, so it is a weaker fit to the advisor's
   own framing, but it is cheap to attack.
3. **Not** `laguna_gate_sp_h64_v1`/`_h48_v1` (≈ 178 µs corrected headroom, the
   largest single target I found) — already assigned to maple-alphonse on #700.
4. **Not** shared-expert QMV fusion or the routed gate/up QMV family — assigned
   to maple-edward on #693 (`r110-b-rev4`).
5. **Not** attention. `laguna_sliding_fused_attn_ring_v1` and
   `full_fused_attn_grow_v1` are closed at round 107 / PR #642 as
   `N-ISSUE-BOUND` at 97.7 % of peak instruction issue; sliding QK-MMA is doubly
   closed (`N-ISSUE-BOUND` + `N-QK-MMA-PADDING-BOUND`).
6. **Not** the 91–103 %-of-peak cohort (3,871 µs/step, 47.4 % of the step).
   It is at the bandwidth roofline, and the only lever is fewer weight bytes.
   The accepted envelope permits group-32 affine INT8 for Q/K/V/O, but this
   checkpoint is already NVFP4 g16/b4 — 4 bits plus a scale per 16 is
   *narrower* than INT8 plus a scale per 32, so the sanctioned re-quantization
   would **add** bytes. There is no byte to buy there inside the envelope.

The advisor knows the global staffing picture and I do not; treat the ordering
as evidence, not as a request.


## 9. What I am delivering regardless

Two artifacts from this assignment outlive the null and are reusable by the
whole campaign:

- **The premise correction** (`research/frieren_r116_premise_correction.md`,
  commit `c3e34652`): the assignment's ~119 µs/step / +1.0 % prize for
  `shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1` is M4 data. On ranked M5 the
  row is 230.0 µs/step at 70.2 % of peak with 68.5 µs raw headroom, and the
  un-applied SPLIT=1 deflation (1.554 µs × 39.4 calls/step = 61.2 µs) leaves
  **≈ 7 µs/step** of real in-kernel headroom. Honest prize 10–40 µs/step =
  **0.09–0.34 %**, 3–11× smaller than stated — and the mechanism is already
  staffed on edward #693.
- **The instrument** (`research/frieren_steady_step.py`, commit `46b228a6`):
  `--local-iterate`'s `decode_seconds_per_token` folds the 512-token seed pass
  into the decode axis (`decode_spt ≈ mean_step + 4 × prefill_spt`), and the
  seed carries nearly all the run-to-run noise on M4. The steady tail-mean over
  tokens ≥ 16 reproduces **6–20× tighter** (`sfd1` 1.85 % → 0.14 %; `qmvsc0`
  1.7 % → 0.48 %) and it *flipped the block-1 ranking*. Any student comparing
  M4 decode arms on `decode_seconds_per_token` is reading a statistic that is
  mostly prefill noise.
