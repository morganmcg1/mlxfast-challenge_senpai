"""Advisor pricing for R119-A instance 3 (router tournament grid-append).

Calibrates the two separable payments of N-GRIDAPPEND-ABSORBS-LATENCY against
alphonse's measured gate_sp result, then applies them to the router tournament
guest whose cost is already recorded in the research archive.
"""

RULE57_US_PER_DISPATCH = 1.2382
SPLIT_INFLATION_US_PER_CALL = 1.554

# gate_sp calibration (merged R114-E, PR #700)
raw_g, calls_g, saved_g = 261.6, 40, 76.8
corr_g = raw_g - SPLIT_INFLATION_US_PER_CALL * calls_g
disp_g = calls_g * RULE57_US_PER_DISPATCH
absorbed_g = saved_g - disp_g
abs_frac = absorbed_g / corr_g
print(
    "gate_sp: raw %.1f -> corrected %.1f | dispatch %.1f + absorption %.1f "
    "= %.1f us/step | absorbed fraction of corrected guest %.2f%%"
    % (raw_g, corr_g, disp_g, absorbed_g, saved_g, 100 * abs_frac)
)

print()
disp_r = 39 * RULE57_US_PER_DISPATCH
for raw, calls, tag in ((133.5, 39.8, "R109-E atlas"), (186.2, 39.0, "r105 table")):
    corr = raw - SPLIT_INFLATION_US_PER_CALL * calls
    print(
        "router (%-12s) raw %.1f -> corrected %.1f | dispatch %.1f + "
        "absorption %.1f = %.1f us/step"
        % (tag, raw, corr, disp_r, abs_frac * corr, disp_r + abs_frac * corr)
    )
print("floor  (zero absorption)                        = %.1f us/step" % disp_r)
print(
    "optimistic (alphonse blended %.2f us/dispatch)  = %.1f us/step"
    % (saved_g / calls_g, 39 * saved_g / calls_g)
)

print()
SHOTS = 30
BASE_SHOT = 0.0190  # p(crown)/shot at current HEAD, post-gate_sp
print(
    "baseline (no further win): p/shot %.2f%%  P(crown | %d shots) %.1f%%"
    % (100 * BASE_SHOT, SHOTS, 100 * (1 - (1 - BASE_SHOT) ** SHOTS))
)
for us in (48.3, 58.1, 65.5, 74.9):
    gain_pct = 0.45 * us / saved_g  # linear in us/step, calibrated on gate_sp
    p = BASE_SHOT * (1.48 ** (gain_pct / 0.10))  # fern steepness law
    P = 1 - (1 - p) ** SHOTS
    print(
        "  %5.1f us/step -> %+.3f%% score -> p/shot %5.2f%%  "
        "P(crown | %d shots) %5.1f%%  (%+.1f pts)"
        % (us, gain_pct, 100 * p, SHOTS, 100 * P,
           100 * (P - (1 - (1 - BASE_SHOT) ** SHOTS)))
    )
