#!/usr/bin/env python3
"""R107-F addendum arithmetic: re-price every % of `cs` figure in
research/maple-frieren-r107f-t2d-down-residual-amortisation.md under rule 105.13.

Every measured delta in R107-F is an M4 per-kernel GPU-busy time. The report
priced them at the bare M5 price (0.015228 % of `cs` per M5 us/step), which is
category (c) of rule 105.12. This script emits the corrected columns.
"""
PRICE = 0.015228          # % of cs per M5 us/step (rule 58 / 105)
CALLS = 39                # routed_shared_nvfp4_down_residual calls per decode step
ALPHA = 0.4369            # bytes-family M4->M5 factor
BETA = 0.5                # latency-family M4->M5 factor
K_DISPATCH = 1.890        # rule 105.13(c): rules 57/65 dispatch regime


def score_delta(us_per_step, k=1.0):
    """% of cs gained; positive delta-time is a slowdown, so the sign flips."""
    return -us_per_step * PRICE * k


def row(name, d_us_per_call):
    us = d_us_per_call * CALLS
    print(f"{name:26s} d_us/call={d_us_per_call:+.4f}  M4_us/step={us:+8.3f}  "
          f"bare={score_delta(us):+.4f}  beta={score_delta(us, BETA):+.4f}  "
          f"alpha={score_delta(us, ALPHA):+.4f}")


def main():
    print("=== arms (score delta, % of cs) ===")
    row("a1 run1", 1.040)
    row("a1 run2", 0.984)
    row("a1 mean", (1.040 + 0.984) / 2)
    row("a1 CI lo", 0.922)
    row("a1 CI hi", 1.106)
    row("a1_wide", (0.928 + 0.921) / 2)
    row("a3", (1.240 + 1.321) / 2)
    row("a2 control", (-0.026 - 0.029) / 2)
    row("a0_wide", (0.003 - 0.001) / 2)
    row("a0_act0 ceiling", (-0.424 - 0.457) / 2)
    row("a0_act0_min ceiling", -0.560)

    print("\n=== barrier drain, 3.081 us/call ===")
    us = 3.081 * CALLS
    print(f"  M4 = {us:.3f} us/step")
    for k, n in ((1.0, "bare (as published)"), (BETA, "beta"), (ALPHA, "alpha"),
                 (K_DISPATCH, "k_dispatch")):
        print(f"  {n:20s} {us * PRICE * k:+.4f} % of cs")

    print("\n=== bars ===")
    print(f"  ship bar in us/call: bare {0.4 / (CALLS * PRICE):.4f}  "
          f"beta {0.4 / (CALLS * PRICE * BETA):.4f}  "
          f"alpha {0.4 / (CALLS * PRICE * ALPHA):.4f}")
    print(f"  0.4 % bar in M4 us/step: bytes {26.27 / ALPHA:.1f}  "
          f"latency {26.27 / BETA:.1f}  dispatch {26.27 / K_DISPATCH:.1f}")

    print("\n=== sec 3.6 efficiency headroom (110.4 M4 us/step) ===")
    for n, bar in (("bare (as published)", 26.27), ("latency/beta", 52.5),
                   ("bytes/alpha", 60.1)):
        print(f"  {n:20s} required capture {bar / 110.4:6.1%}")

    print("\n=== the summand rule 105.13 newly prices: per-layer dispatch removal ===")
    for lo_hi, label in (((2.3403, 2.3403), "point (rule 65)"),
                         ((2.2766, 2.4040), "95 % CI")):
        a, b = lo_hi
        print(f"  39 removals, {label:16s} "
              f"{39 * a:.2f}..{39 * b:.2f} M5 us/step = "
              f"{39 * a * PRICE:+.4f}..{39 * b * PRICE:+.4f} % of cs")
    print(f"  two boundaries (3-kernel merge): {2 * 39 * 2.3403 * PRICE:+.4f} % of cs")

    print("\n=== levels (rule 105.13(b): levels, not contrasts -- quote with care) ===")
    for name, upc in (("unique-byte floor", 19.107), ("in-situ anchor", 22.07)):
        us = upc * CALLS
        print(f"  {name:20s} {upc:.3f} us/call = {us:.1f} M4 us/step; "
              f"bare {us * PRICE:.4f} %  beta {us * PRICE * BETA:.4f} %  "
              f"alpha {us * PRICE * ALPHA:.4f} %")


if __name__ == "__main__":
    main()
