# A1 pre-registration: exposure factors from default-ON knobs

Committed **before** any A1 data exists. Written after A0 (`research/nezuko-a0-dispatch-type.txt`)
and before `research/nezuko_a1_exposure.sh` is launched.

## The prediction under test

A0 concluded that decode-time concurrency is **sibling shadowing** (R-B), not
uniform seam pipelining (R-A), and that exactly three kernels are shadowed:

| kernel | isolated us/step | predicted E |
| --- | ---: | ---: |
| `gate_sp_h64` | 232.5 | 0.10 |
| `gate_sp_h48` | 74.2 | 0.10 |
| `shared_nvfp4_swiglu_qmv_rows1` | 280.8 | 0.10 |
| everything else | 7869.5 | ~1.00 |

The A2 closure test is consistent with this (`E_rest = 1.007`), but it uses the
same A0 data. A1 is an **out-of-sample** test with a different mechanism: change
a kernel's duration with a shipped runtime knob and measure how much of that
change reaches the step wall.

## The discriminating pair

Both knobs make the *same class* of change -- one output row per simdgroup
instead of two, on a SwiGLU quantized matvec -- so kernel-specific confounds
largely cancel. They differ only in which kernel they land on.

| knob | kernel affected | isolated us/step | A0 predicts E |
| --- | --- | ---: | ---: |
| `DARKBLOOM_ROUTED_GATEUP_R1` | `routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2` | 1488.6 | **~1.0** |
| `DARKBLOOM_SHARED_QMV_R1` | `shared_nvfp4_swiglu_qmv_rows1` | 280.8 | **~0.1** |

Both default ON, so `=0` is the slower arm. `dI` is the knob-off-minus-on change
in the SPLIT=1 isolated per-kernel census (nothing overlaps there, and the
constant per-command-buffer overhead cancels in the difference). `dS` is the
knob-off-minus-on change in decode step wall time with the GPUPROF hook off.
`E = dS / dI`.

## Numbered predictions

1. **`ROUTED_GATEUP_R1`: `E` in `[0.7, 1.3]`.** The kernel is the single largest
   line in the census and A0 found no shadowing anywhere near it.
2. **`SHARED_QMV_R1`: `E` in `[-0.2, 0.4]`.** A0 says this kernel is ~90 %
   hidden underneath its sibling. Turning it off should barely move the step.
3. **`E(routed) - E(shared) > 0.4`**, i.e. the two knobs are separated. This is
   the base-independent form and is the actual claim; it survives even if both
   absolute `E` values are biased by a common factor.
4. Both knobs produce **0 token divergences** in every arm. They are documented
   exact-token-equivalent schedule changes.

## Falsification

- If `E(routed) - E(shared) < 0.2`, the per-kernel exposure model is **not**
  predictive out of sample and the A0 conclusion must be reported as an
  in-sample decomposition only, not as a targeting rule. Sections 4-6 of the
  report would then be downgraded to "consistent with" rather than "measured".
- If `E(shared) > 0.6`, R-B's specific kernel attribution is wrong even though
  R-A was rejected; the 448 us would have to be re-localized.
- If `E(routed) < 0.4`, something shadows the largest kernel on the decode path,
  which A0's group census excludes; that would indict the group census itself.

## Power and honesty

`WALL_ORDER='A B B A A B B A'`, n = 4 vs 4, 400 steps per point, 25-step settle:
the exact two-sided permutation minimum is `p = 4/70 = 0.057`, and the
campaign's arm-level between-session scatter is `+-70 us`. Predicted `dI` is
large for `ROUTED_GATEUP_R1` and the R1->R2 change is worth roughly 10-20 % of a
1489 us/step kernel, so `dS` should clear the floor comfortably. For
`SHARED_QMV_R1`, `dI` is ~5x smaller and `E` is predicted ~0.1, so `dS` is
predicted to be **within** the noise floor. That asymmetry is the point: the
prediction is that one arm separates and the other does not, and I will report
`E(shared)` with an interval that includes 0 rather than claiming a precise
small number.

If `dI` for either knob turns out smaller than ~150 us/step, that arm does not
clear the design bar and I will report it as underpowered rather than as a
measurement of `E`.
