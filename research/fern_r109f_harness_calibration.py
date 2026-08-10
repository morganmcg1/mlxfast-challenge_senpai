#!/usr/bin/env python3
"""Print the score-axis operating point of every harness this campaign uses.

The score is `(D_ref/D)^0.75 * (S_ref/S)^0.25` on two measured rates, but the
reported decode rate carries an amortized share of the 512-token seed, so
`D = T + S/128` with `T` the true marginal per-step cost.  Every elasticity
below follows from that identity; none of it is a regression fit.

The point of the table is the two right-hand columns.  A local harness reports
its own `ns` ratio at its own sigma, so the same physical saving scores
differently on each harness.  `normT` is the factor that converts a locally
observed pure-steady-step win into the official-M5 score change, and `normS`
does the same for a pure prefill win.
"""

import importlib.util
import pathlib

_SPEC = importlib.util.spec_from_file_location(
    "ledger", pathlib.Path(__file__).with_name("fern_r109_timing_ledger.py")
)
L = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(L)

# (label, decode s/token, prefill s/token, provenance)
POINTS = [
    (
        "M5 pinned baseline",
        0.01385621216015625,
        0.00036751938916015626,
        "benchmark.sh local baseline constants",
    ),
    (
        "M5 frontier e27f1ce",
        (4.3224 + 97.863 / 128) / 1000.0,
        97.863 / 512000.0,
        "advisor comment 6: S=97.863ms T=4.3224ms",
    ),
    (
        "M4 --local-iterate",
        0.012912969,
        0.001122800,
        "R109-F fusion probe arm A median, n=3",
    ),
    (
        "M4 --local-submit",
        0.008955730,
        0.001111910,
        "R109-F stage-0 baseline median, n=4 steady",
    ),
]


def main():
    hdr = (
        f"{'operating point':22s} {'S_ms':>8s} {'D_ms':>9s} {'T_us':>8s} "
        f"{'sigma':>7s} {'el_S':>6s} {'el_T':>6s} {'normT':>6s} {'normS':>6s}"
    )
    print(hdr)
    print("-" * len(hdr))
    rows = {}
    for label, d, p, _ in POINTS:
        a = L.axes(d, p)
        rows[label] = a
        print(
            f"{label:22s} {a['S_ms']:8.2f} {a['D_ms']:9.4f} "
            f"{a['T_ms'] * 1000:8.1f} {a['sigma'] * 100:6.2f}% "
            f"{a['elast_S']:6.3f} {a['elast_T']:6.3f} "
            f"{L.M5_ELAST_T / a['elast_T']:6.3f} "
            f"{L.M5_ELAST_S / a['elast_S']:6.3f}"
        )
    for label, _, _, prov in POINTS:
        print(f"  {label:22s} <- {prov}")

    print()
    print("absolute-us pricing of a steady-step saving, tau=1")
    print("  %score_M5 = elast_T_M5 * tau * dT / T_host")
    for label in ("M4 --local-iterate", "M4 --local-submit", "M5 frontier e27f1ce"):
        t_us = rows[label]["T_ms"] * 1000
        per_us = L.M5_ELAST_T / t_us * 100
        print(
            f"  {label:22s} T={t_us:7.1f}us  {per_us:.5f} %/us  "
            f"bar {L.BAR_WEIGHTED_RATIO - 1:.6%} needs {0.378 / per_us:6.1f} us"
        )
    print(f"  advisor canonical chain 0.63/8972 = {0.63 / 8972 * 100:.5f} %/us "
          f"-> bar needs {0.378 / (0.63 / 8972 * 100):.1f} us")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
