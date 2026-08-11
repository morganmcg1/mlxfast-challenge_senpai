# R125-E pre-registration (committed before any confirm number is read)

Committed 2026-08-11 ~10:40Z, after the smoke check of the instrument and
*before* any confirm-stage run has been launched or inspected.

## Instrument

One arm = one worker process (`research/decode_probe.py` via
`research/frieren_r125e_arms.sh`), because every `DARKBLOOM_*` knob is a
file-scope Swift `let`. Golden `public_longcopy_gate_english_512_256`,
512-token seed, 224 teacher-forced one-token steps,
`DARKBLOOM_STARTUP_MEMORY_PROFILE=full` (ranked 200/200/50 atlas profile).
Statistic per run = median steady step in ms, step 0 dropped (one-time KV
concat). Drift handling: each arm run is differenced against the control level
linearly interpolated between the nearest earlier and later `C` runs of the same
pass (`research/frieren_r125e_analyze.py`). Pricing: 1 µs/step = 0.00586 %
score; ranking-relevant bar 25.6 µs/step = +0.378 %.

## Screen (no claims)

n = 2 per arm (two counterbalanced passes, pass 2 = exact reverse of pass 1),
all other knobs at shipped default. Screen output is a ranking only.

Screened family (22 arms + controls):
`FUS`, `PF0`, `PF1`, `PF2`, `PF3`, `U1`, `U4`, `U8`, `RP0`, `RP5`, `NS0`, `NS2`,
`STG`, `STGPF`, `ASOFF`, `ASDEN`, `ASSPA`, `ASLAD`, `ASNRM`, `OPR1`, `OPR4`,
`OPSG4`.

## Confirm-slot selection rule

At most three confirm arms, chosen as:

1. `FUS` (`DARKBLOOM_SHARED_ROUTED_QMV_FUSED=1`) unconditionally, whatever its
   screen sign, because the advisor needs its number with an interval to choose
   between the fused path and TG=256.
2. The two arms with the most negative drift-corrected screen mean delta, among
   arms whose screen mean is ≤ −10 µs/step. If fewer than two arms clear that
   bar, fewer confirm arms are run and the shortfall is reported.

Tie-break at equal screen mean: the brief's knob priority order
(FUSED > NORM_AFFINE_QKV_PF > L5_UNROLL > ROUTER_WEIGHT_PREFETCH >
NVFP4_NIBBLE_SPLIT > NORM_AFFINE_QKV_STAGE > DECODE_ASYNC_STAGE > OPROJ).

## Multiplicity treatment

Bonferroni over the **confirm family**, i.e. over the ≤ 3 arms actually
confirmed, not over the 22 screened arms. The screen is explicitly a ranking
device with no inferential claim attached, so it does not consume α; the price
of that choice is that a screen-selected winner is subject to selection bias,
which is exactly why the confirm stage re-measures it in a fresh interleaved
session at n ≥ 6.

- Family α = 0.05, two-sided, k = number of confirm arms (≤ 3).
- Per-arm α = 0.05 / k ⇒ for k = 3, α = 0.0167 ⇒ decisions are made on the
  **98.3 % paired bootstrap CI**; the 95 % CI is also reported for reference.
- A "win" claim requires all of: 98.3 % CI upper bound < 0 (faster than
  control), point estimate ≤ −10 µs/step, bit-identical output
  (`max_abs_diff == 0` + golden hash), and every correctness gate green.
- A claim of *ranking relevance* additionally requires the point estimate to be
  ≤ −25.6 µs/step; below that magnitude the finding is reported as real but
  sub-bar.
- Achieved detection floor is reported from the observed control run-to-run sd
  as 2·sd/√n for the confirm n actually run, not assumed from the campaign
  pooled cv.

## Pre-registered null statement

If no arm clears the confirm bar, the reported conclusion is that the shipped
defaults of the current composition are already at or within ~10 µs/step of the
best available setting for every knob screened, and the table of losers is the
deliverable.

## Addendum, written 11:10Z with 15/32 screen runs visible, before pass 2

Pass 1 (runs 1-15) is on disk; the counterbalanced reverse pass is still
running. The confirm-family selection rule is fixed now, so the choice cannot be
tuned on the replicate:

1. **Slot 1 (mandatory):** `NVFP4_NIBBLE_SPLIT` at whichever of `NS0`/`NS2`
   ranks better in the drift-corrected 32-run screen. Confirmed regardless of
   screen sign — the advisor asked for this number explicitly, so it is measured
   even if the screen ranks it a loser. A deliberate deviation toward *more*
   measurement than screen-then-confirm would buy.
2. **Slot 2:** the best drift-corrected arm among
   `{RP0, RP5, ASDEN, ASSPA, ASLAD, OPSG4}`. `OPR1`/`OPR4` are excluded from
   selection: the advisor closed that axis (#718 interior optimum at `rps=2`,
   #719) after this screen was already launched, so those two arms are reported
   as free replication only and are never promoted to a confirm slot.
3. **Slot 3:** the best drift-corrected `DECODE_ASYNC_STAGE` arm
   (`ASOFF/ASDEN/ASSPA/ASLAD/ASNRM`), if slot 2 did not already take one.

Family size stays 3, so the Bonferroni level stays 98.3% and the win bar is
unchanged: 98.3% CI upper bound < 0 **and** point estimate ≤ −10 µs/step.
