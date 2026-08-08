# Calibrated local decode noise floor on M4 Pro (R85-C, PR #457)

Standing programme reference for how much decode µs/step signal a local M4 Pro
session can actually resolve, and with which estimator. Produced as a by-product
of R85-C's placement arm; written up separately because it is reusable by any
matched-pair arm, and because PR #460's bisection depends on it.

Host: Apple M4 Pro, 14 CPU, 48 GiB unified memory (low-memory startup profile),
macOS 26.5.2, Apple GPU generation 16. One quiet session, one model-holding
process at a time, 40 C thermal gate honoured between every run.

Measurement: `research/decode_probe.py --steps 33 --profile --profile-top 6`
under `DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=1`, 24 steady steps
after warm-up, driven by `research/maple_r85_placement_arms.sh`. All 72 timed
runs in the session used **one** worker binary; arms differ only by environment
variable, so every number below is pure measurement noise, not code.

## The table

Decode µs/step. "1-vs-1" is the 95 % half-width when each side is a single run.

| estimator | per-run / per-duplex SD | 95 % half-width, 1-vs-1 | resolves 38 µs/step? |
|---|---|---|---|
| whole-step **wall clock**, 1 run/side | **≈ 48** (robust IQR over all 55 runs analysed; per-arm SD 44 / 50 / 53 for the three inert arms) | **± 133** | no |
| whole-step **GPU busy sum**, 1 run/side | 32–50 | ± 100–139 | no |
| whole-step GPU busy, **adjacent-pair ratio-adjusted** to a control kernel | **6.1** per A/B duplex | ± 8.5 at n=1; **± 5.1 at n=8**; ± 4.0 at n=24 | yes, 7× margin |
| **per-kernel**, adjacent-pair ratio-adjusted | — | **± 0.3 … 2.0** at n=8 duplexes | per-kernel attribution |

Same-arm null control (`base` vs `base`, non-adjacent offset, n=8 duplexes,
byte-identical binary and environment): whole-step ratio-adjusted
**+3.2 µs/step [−1.9, +8.3]**; all 19 labelled kernels null within ±2.0 µs/step.
The estimator is unbiased on this host.

Score conversion: 0.015280 % of score per µs/step of decode. The paired
estimator's floor is therefore ≈0.078 % of score at n=8 and ≈0.061 % at n=24;
the unpaired wall-clock floor is ≈2.0 % of score at n=1, which is why
single-shot local wall clock cannot adjudicate anything at the scale this
programme works at.

## Consequences

**Unpaired wall clock is the wrong tool for tens of µs/step.** Resolving a
38 µs/step effect at 95 % from unpaired whole-step wall clock needs

```
n ≈ 2 · (1.96 · 48 / 38)² ≈ 26 runs per side
```

≈52 runs ≈40 min of pure timing plus gate waits — per comparison. The paired
ratio-adjusted estimator reaches ±5 µs/step in 8 duplexes = 16 runs.

**Whole-step absolute totals are not identifiable at the tens-of-µs scale on
this host.** The unadjusted paired estimator has a per-duplex SD of ~48 µs/step;
±4 µs/step would need ~480 duplexes. Quote it only as a sanity check alongside
the ratio-adjusted number, and always quote the control kernel's own absolute
movement so a reader can see whether the anchor drifted.

**Discard the first timed run after warm-up.** Slot 1 of the session measured
10244 µs/step against a session median of 9780 — a +464 µs/step first-run
penalty, ~12× the size of effects being hunted. Every counterbalanced design
must burn it.

**Counterbalance, and never pool across pairing offsets.** `maple_r85_arm_stats.py`
pairs adjacent slots; `--offset 0` and `--offset 1` reuse the same runs, so their
intervals are not independent and must not be combined.

## Conditions on the ratio adjustment

The adjustment divides out session-wide clock and thermal drift by referencing a
kernel asserted to be unaffected by the change. That is safe when the two arms
run the same binary (R85-C's dials) and requires care otherwise:

- for a revert-and-measure or bisection arm, pick the control from a file that is
  **not** part of the current change, and name it in the report;
- report the unadjusted absolute total as well;
- if the change plausibly moves every kernel, the adjustment is invalid — fall
  back to wall clock and pay the n≈26 per side.

## Diagnostic shapes

- **Selectivity is the signal.** In every real effect measured so far only ~6 of
  ~40 labelled kernels move. A change that moves *all* kernels proportionally is
  a session artifact (clock ramp, thermal, energy accounting), not a code effect.
- **Sibling kernel variants can move in opposite directions.** Observed:
  `gate_sp_h48` +2.0 % while `gate_sp_h64` −0.25 %; `oproj_act_h64` +0.13 %
  while `oproj_act_h48` −0.20 %. An explanation that is uniform in the kernel
  population cannot produce this.

## Reusable machinery

- `research/maple_r85_placement_arms.sh` — counterbalanced A/B/B/A runner.
  Applies the GPUPROF hook (`research/nezuko-pr158-gpuprof-hook.patch`), builds
  the worker **once**, runs one unscored warm-up, then `REPS × ORDER` runs tagged
  `%02d-rep%s-%s`, and reverts the hook plus rebuilds a clean worker in its EXIT
  trap. Set `ARMS` and `ORDER` for other arms.
- `research/maple_r85_arm_stats.py --steps N --arms A B --offset {0,1}
  [--control NAME] [--min-us-step X] [--only-giveback] [--scale-to-n N]
  [--strip-infix] [--json-out F] FILES…` — the estimator. Per-kernel and
  whole-step deltas with CIs, per-duplex SD, and the score conversion.
- `research/maple_r85_dose_inertness.sh` — free-run token-digest equality gate
  across arms, to be run before any timing so an "inert" arm is proven inert.
