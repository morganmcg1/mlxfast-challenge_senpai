# R88-A pre-registration — kernel-local vs end-to-end give-back

Assignment: PR #473 (`maple-r88-a-kernel-giveback`, rev `r88-a-rev1`), branch
`maple-frieren/r88-kernel-giveback`. Host: Apple M4 Pro, 48 GiB, low-memory
startup profile, Apple GPU generation 16 (`_nax` decode kernels unreachable).

**Honesty note on timing.** This file was written *after* the A0' session was
launched (job `6510397b-9454-4ea6-a08d-a9ddd19416c1`, started
2026-08-08T~22:5x UTC) but *before* any number from the natural-regime (`nat`)
arm was read. The only slot output visible at the time of writing was
`s1/01-rep1-base`, which reproduces the already-published #457 S1 constants
(wall 9.803 ms, `gpu_busy_sum` 8.590 ms, `cbs=406.0`, `dispatches=406.0`) and
contains no candidate-vs-base contrast. No `nat/*` slot had completed.

## 1. The question

Every number in `research/maple-r85-c-epilogue-result.md` (PR #457) came from a
single instrument: total steady GPU-busy time measured under
`DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=1`, which forces **one
dispatch per command buffer** (406 CBs/step instead of the shipped 45). Within
that instrument the fused decode-attention epilogue change measured
**-26.53 µs/step on the two touched kernels** but only **-15.43 µs/step
[-22.04, -8.82] on the total**, because two *byte-identical* untouched kernels
moved in the opposite direction (`laguna_gate_sp_h64_v1` +8.14,
`laguna_gate_sp_h48_v1`-family +2.96). Standing rule 38 turned that ratio into a
programme-wide **42 % give-back discount** now applied to unrelated proposals
(e.g. PR #462 reprices norm→QKV un-fusion from -124…-128 to -52…-55 µs/step
end-to-end using it).

The discount is only real if the give-back exists **in the shipped 45-CB
regime**. Nothing in #457 tested that: `Σ(per-kernel deltas) ≡ Δ(total busy)`
by construction in that table, so the "total" column is not an independent
end-to-end measurement.

## 2. Hypotheses on the board

| id | mechanism | prediction for A0' |
| --- | --- | --- |
| H1 | Real resource contention/steady-state slowdown of untouched kernels caused by the touched kernels' new code. | give-back persists in `nat` |
| H2 | Power/thermal/clock rebalancing. | give-back persists (possibly attenuated) |
| H3 | Dispatch-overlap absorption at CB grain. | *impossible under SPLIT=1* (one dispatch per CB); see §4 |
| H3' | Legitimate CB-grain overlap absorption in the natural regime only. | give-back appears in `nat` and is absent/different in `s1` |
| H4 | Code/data placement (I-cache, binary layout). | give-back persists in `nat` |
| H5 | Occupancy/scheduling change on shared GPU state. | give-back persists in `nat` |
| **H6** | **SPLIT=1 neighbour-coupling / fine-grained duty-cycle artefact of the instrument itself.** 406 CBs/step each preceded by ≈3 µs of measured idle; the per-CB fixed launch/ramp component charged to a *small* kernel depends on its neighbour's duration and on the duty cycle. | **give-back vanishes in `nat`** |

Supporting arithmetic for H6, already in hand: base `gate_sp` costs
242.9 µs/step over 30 head-64 dispatches = **8.10 µs/dispatch** under SPLIT=1,
versus **5.004 µs** measured in isolation by PR #101 — i.e. ≈3.1 µs/CB of
instrument overhead, matching the **2.97 µs of idle per CB** (gap = 1260 µs/step
= 12.8 % of wall / 406 CBs) measured directly this session. The whole give-back
is +0.27 µs/dispatch, about **9 % of that overhead**, while the touched
attention kernels lost ≈0.70 µs/dispatch.

## 3. Design and pre-registered quantities

One session, one pair of frozen binaries (`base` = source at
`417f42c4167344afd2156b6f5d8ab76e2bf419f3`, i.e. immediately before the #457
epilogue merge; `cand` = branch HEAD ≡ frontier `3217f111`), snapshotted and
sha256-pinned, replayed in **two regimes**:

- `s1`: `DARKBLOOM_GPU_PROFILE_SPLIT=1` (406 CBs/step) — reproduces #457.
- `nat`: profiling hook on, split **off** (expected ≈45 CBs/step) — the shipped
  dispatch grain.

4 reps × 2 regimes × 4 slots, ABBA within each regime block, regime block order
flipped on even reps, ratio-adjusted duplex contrasts, n = 8 duplexes per
regime. Only the regime env var differs between the two halves, so the binary
pair, host, thermal gate, prompt and token stream are held fixed.

Pre-registered estimands:

- `S1_touched` — Σ ratio-adjusted deltas on the two touched attention kernels in
  `s1`. Expected ≈ **-26.5 µs/step** (replication check on #457).
- `S1_total` — ratio-adjusted total steady busy delta in `s1`. Expected ≈
  **-15.4 µs/step** (replication check).
- `NAT_total` — ratio-adjusted total steady busy delta in `nat`.
- **`c = NAT_total / S1_touched`** — the conversion factor from kernel-local
  work removed to end-to-end time saved, measured in the shipped regime.

Discriminating values of `c`:

- H6 dominant ⇒ **c ≈ 1.0** (the give-back is an artefact; #457's true value is
  the full -26.5, and standing rule 38 must be withdrawn).
- H1/H4/H5 dominant ⇒ **c ≈ 0.58** (the give-back is physical; rule 38 stands).
- H3' ⇒ intermediate, with a different per-kernel pattern in `nat` than in `s1`.

## 4. Pre-registered claim that does not depend on the data

Under `DARKBLOOM_GPU_PROFILE_SPLIT=1` there is exactly one dispatch per command
buffer, so no two dispatches can overlap. **H3 as stated (dispatch-overlap
absorption) cannot produce the #457 give-back**, and the proposed discriminator
"Σ per-kernel vs total" is vacuous because the #457 table's total is the sum by
construction (-26.53 + 8.14 + 2.96 = -15.43 exactly). H3 survives only in the
H3' form above, which A0' tests directly. Similarly, H1's only causal route to
changing a *byte-identical* kernel's steady-state duration is code/data
placement (H4), and the parked placement arm already found no placement
correlation (r = -0.088); all pipelines are compiled before the steady window
(steps 1-199 of 200 are measured).

## 5. My predictions

- `c = 0.85`, 80 % interval **[0.55, 1.10]**.
- P(H6 is the dominant contributor) = **0.55**.
- P(give-back in `nat` is statistically indistinguishable from zero at the rig's
  per-kernel resolution) = 0.45.
- `s1` replication: `S1_total` within ±7 µs/step of -15.4, `S1_touched` within
  ±4 µs/step of -26.5.
- `nat` regime constants: `cbs/step ≈ 45`, `dispatches/step = 406`,
  `gpu_busy_sum > gpu_busy_union` (real intra-CB overlap, unlike `s1` where the
  session already measured `sum/union = 1.0001`).

## 6. Falsifiers / what would make me withdraw the H6 claim

- `NAT_total` ≈ `S1_total` (c ≈ 0.58) with the same per-kernel sign pattern
  (`gate_sp` positive in `nat` too) ⇒ H6 refuted, rule 38 confirmed, and A2
  (deterministic prewarm) becomes the correct next arm.
- `cbs/step` in `nat` not ≈45, or the two arms' token streams differing, or the
  binaries not differing ⇒ session void, no claim published.
- Same-arm null in `nat` wider than the base-vs-cand contrast ⇒ inconclusive,
  reported as such.

## 7. Rig floor restated

Per-run decode σ = 48.0 µs/step (M4 Pro, cross-process; standing rule 40).
n=1 → ±133; n=3 → ±109; counterbalanced ABBA ratio-adjusted n=8 → ±5.1…6.6 on
the ratio-adjusted total, ±0.3…2.0 per kernel. Measured this session for the
`s1` regime: **per-duplex wall SD = 131.7 µs/step** (±110 at n=8) and absolute
`busy_sum` SD = 29.9 µs/step (±25 at n=8). Wall clock is therefore *not* a
usable proxy for a 15-26 µs/step effect and is reported only as labelled
corroboration; `./benchmark.sh --local-iterate` resolves nothing below
≈130 µs/step. This is a **methodology/attribution** experiment on M4 Pro; it
makes no claim about ranked M5 seconds/token, and the `_nax` decode kernels the
M5 selects are not exercised here.
