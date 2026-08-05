#!/usr/bin/env python3
"""Serialised (SPLIT=1) decode budget vs the SPLIT=0 union, and the dup/serialised
first-touch ratio per family.

Inputs are the measured constants from run 1c8aded9 (SPLIT=1, 250 steps) and the
round-2 dup census (run c9893c28, SPLIT=0, 150 steps).
"""

SPLIT1_SUM = 8850.3   # us/step, sum of all per-kernel serialised times
SPLIT0_UNION = 8272.4  # us/step, real overlapped GPU union (round-2 base, n=5)
N_DISPATCH = 406
CB_FLOOR = 1.33        # us/dispatch, legacy command-buffer floor

# name, calls, serialised us/step, serialised us/call, dup dUnion us, dup calls
FAMILIES = [
    ("routed_nvfp4_swiglu_qmv", 39, 1561.5, 40.04, 1446.3, 39),
    ("decode_nvfp4_qkv_h64", 30, 1402.3, 46.74, 1048.4, 30),
    ("oproj_act_h64", 30, 1183.1, 39.44, 686.7, 30),
    ("down_residual", 39, 894.8, 22.94, 753.7, 40),
    ("sliding_fused_attn", 30, 637.7, 21.26, 580.3, 30),
    ("lmhead_int5 (4 kernels)", 4, 505.0, None, 405.5, 1),
    ("decode_nvfp4_qkv_h48", 10, 378.7, 37.87, None, 0),
    ("gate_sp h64+h48", 40, 325.6, 8.09, 178.3, 40),
    ("residual_rms_router", 39, 319.2, 8.18, 161.6, 39),
    ("oproj_act_h48", 10, 317.6, 31.76, None, 0),
    ("shared_nvfp4_swiglu_qmv", 39, 295.0, 7.56, 175.2, 39),
    ("dense_gate_up_swiglu", 1, 267.4, 267.35, None, 0),
    ("full_fused_attn", 10, 259.9, 25.99, 193.7, 10),
    ("decode_router_top8_ordinal", 39, 205.4, 5.27, None, 0),
    ("rmsbfloat16", 41, 143.3, 3.50, None, 0),
    ("dense_down_residual", 1, 135.0, 134.98, None, 0),
]

# families that also have a round-1 skip arm, with skip-recoverable us
SKIP_CENSUSED = [1561.5, 1402.3, 637.7, 894.8, 378.7, 419.5, 1183.1, 325.6,
                 259.9, 295.0]
SKIP_RECOVERABLE_SUM = 3860.0


def main():
    excess = SPLIT1_SUM - SPLIT0_UNION
    print("SPLIT=1 serialised sum   %.1f us/step" % SPLIT1_SUM)
    print("SPLIT=0 overlapped union %.1f us/step" % SPLIT0_UNION)
    print("excess %.1f us = %.2f%% of the step = %.3f us/dispatch"
          % (excess, 100 * excess / SPLIT0_UNION, excess / N_DISPATCH))
    print("=> overlap + command-buffer overhead together are at most %.1f%% "
          "of the decode step" % (100 * excess / SPLIT0_UNION))

    hdr = "%-28s %5s %9s %8s %10s %9s"
    print("\n" + hdr % ("family", "calls", "ser us", "%% step", "true/call", "dup/ser"))
    total = 0.0
    for name, calls, tot_us, per_call, dup, dup_calls in FAMILIES:
        total += tot_us
        true_pc = (per_call - CB_FLOOR) if per_call else None
        ratio = (dup / dup_calls) / true_pc if (dup and dup_calls and true_pc) else None
        print("%-28s %5d %9.1f %7.2f%% %10s %9s"
              % (name, calls, tot_us, 100 * tot_us / SPLIT0_UNION,
                 ("%.2f" % true_pc) if true_pc else "-",
                 ("%.3f" % ratio) if ratio else "-"))
    print("%-28s %5s %9.1f %7.2f%%"
          % ("SUM of listed", "", total, 100 * total / SPLIT0_UNION))
    print("unlisted small kernels: %.1f us" % (SPLIT1_SUM - total))

    shared = 295.0
    print("\nshared QMV serialised %.1f us = %.2f%% of step" % (shared, 100 * shared / SPLIT0_UNION))
    print("  a -4.5%% kernel-body win on it = %.1f us = %.3f%% of decode "
          "(resolution is +/- 16 us)" % (0.045 * shared, 100 * 0.045 * shared / SPLIT0_UNION))

    ser = sum(SKIP_CENSUSED)
    print("\nskip-instrument cross-check: censused families serialised %.1f us, "
          "skip-recoverable %.1f us -> skip accounts for only %.0f%%"
          % (ser, SKIP_RECOVERABLE_SUM, 100 * SKIP_RECOVERABLE_SUM / ser))


if __name__ == "__main__":
    main()
