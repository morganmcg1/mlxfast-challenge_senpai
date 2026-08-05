#!/usr/bin/env python3
"""Fit the pre-registered dispatch-saturation law dT(n) = max(0, c*(n - knee)).

Written before any r2 reading arrived; see research/tanjiro-pr34/prereg-r2.md for
the rules this implements.

Usage:
    pr34_fit_ladder.py n:dT[,dT...] n:dT ...
    pr34_fit_ladder.py --json <score.json> ...   # derive dT from paired baselines

The first form takes the differenced points directly. The second reads local or
official score JSON files and forms each point's dT against its own paired
baseline, which is the pre-registered estimator.
"""

from __future__ import annotations

import json
import sys

SIGMA = 0.024  # ms, pre-registered two-receipt differencing noise
PRED = {  # pre-registered point predictions, ms
    "H_sat": {0: 0.0, 400: 0.82, 800: 1.74, 1600: 3.58, 2400: 5.42},
    "H_gpu": {0: 0.0, 400: 0.0, 800: 0.89, 1600: 2.98, 2400: 5.06},
    "H_cpu": {0: 0.0, 400: 0.0, 800: 0.0, 1600: 0.91, 2400: 2.73},
}
STEP_MS = 5.087  # promoted M5 frontier decode step
# Measured full ms/token of the n=0 anchor c3ce66ec: T + S/128.
# score = decode_su**0.75 * prefill_su**0.25 and decode_su = bD / D_CAND_MS,
# so a saving of dT ms on a decode-only change is
#   d ln score = 0.75 * dT / D_CAND_MS.
# Reporting dT as a fraction of the step alone understates score by 1/0.75
# and invites confusing the two, so print both.
D_CAND_MS = 4.28121 + 97.9496 / 128.0
SCORE_PCT_PER_MS = 0.75 / D_CAND_MS * 100.0
SHIPPED = 406  # dispatches per shipped decode step
ACTION_MS = 0.1  # pre-registered fusion action threshold


def verdicts(c_us, slack_ms):
    print(f"\nscore conversion: 1 ms of decode saving = "
          f"{SCORE_PCT_PER_MS:.4f}% of score "
          f"(0.75 / {D_CAND_MS:.6f} ms full decode ms/token)")
    print(f"the pre-registered {ACTION_MS} ms threshold is therefore "
          f"{ACTION_MS * SCORE_PCT_PER_MS:.2f}% of score")
    print(f"\nfusion verdicts at c = {c_us:.3f} us, slack = {slack_ms:.3f} ms:")
    print(f"{'removed':>10}{'dT ms':>10}{'% of step':>11}{'% of score':>12}"
          f"{'verdict':>12}")
    ks = [(k, str(k)) for k in (40, 100, 200, 400)]
    ks += [(round(SHIPPED * f), f"{int(f * 100)}% ({round(SHIPPED * f)})")
           for f in (0.10, 0.25, 0.50)]
    for k, label in ks:
        gain = max(0.0, k * c_us / 1000.0 - max(0.0, slack_ms))
        print(f"{label:>10}{gain:>10.4f}{gain / STEP_MS * 100.0:>11.2f}"
              f"{gain * SCORE_PCT_PER_MS:>12.2f}"
              f"{'PURSUE' if gain > ACTION_MS else 'below thr':>12}")


def axes(metrics: dict, prefix: str = "") -> tuple[float, float]:
    """Return (S, T) in ms from a metrics dict; prefix='baseline_' for the pair."""
    p = metrics[prefix + "prefill_seconds_per_token"]
    d = metrics[prefix + "decode_seconds_per_token"]
    s = 512000.0 * p
    return s, 1000.0 * d - s / 128.0


def ols(xs: list[float], ys: list[float]) -> tuple[float, float]:
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return 0.0, my
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return slope, my - slope * mx


def fit(points: list[tuple[float, float]]) -> dict:
    """Scan the knee on a 1-dispatch grid and take the slope above it."""
    best = None
    for knee in range(0, 2401):
        above = [(n, d) for n, d in points if n > knee]
        if len(above) < 2:
            continue
        slope, intercept = ols([n for n, _ in above], [d for _, d in above])
        if slope <= 0:
            continue
        knee_eff = -intercept / slope
        rss = 0.0
        for n, d in points:
            pred = max(0.0, slope * (n - knee_eff))
            rss += (d - pred) ** 2
        if best is None or rss < best["rss"]:
            best = {"knee": knee_eff, "c_us": slope * 1000.0, "rss": rss,
                    "n_above": len(above)}
    if best is None:
        return {}
    best["slack_ms"] = best["c_us"] * best["knee"] / 1000.0
    lo, hi = None, None
    for knee in range(0, 2401):
        above = [(n, d) for n, d in points if n > knee]
        if len(above) < 2:
            continue
        slope, intercept = ols([n for n, _ in above], [d for _, d in above])
        if slope <= 0:
            continue
        ke = -intercept / slope
        rss = sum((d - max(0.0, slope * (n - ke))) ** 2 for n, d in points)
        if rss <= best["rss"] + SIGMA ** 2:
            lo = ke if lo is None else min(lo, ke)
            hi = ke if hi is None else max(hi, ke)
    best["knee_lo"], best["knee_hi"] = lo, hi
    return best


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    points: list[tuple[float, float]] = []
    if args[0] == "--json":
        for path in args[1:]:
            blob = json.load(open(path))
            m = blob.get("metrics", blob)
            _, t = axes(m)
            _, bt = axes(m, "baseline_")
            n = int(path.split("-n")[1].split("-")[0].split(".")[0])
            points.append((float(n), t - bt))
            print(f"{path}: n={n} T={t:.5f} baseline_T={bt:.5f} dT={t - bt:+.5f}")
    else:
        for a in args:
            n, _, ds = a.partition(":")
            for d in ds.split(","):
                points.append((float(n), float(d)))

    points.sort()
    print("\npoints (n, dT ms):", [(int(n), round(d, 5)) for n, d in points])

    print("\nresiduals against the pre-registered predictions (ms):")
    hdr = f"{'n':>6}" + "".join(f"{k:>10}" for k in PRED) + f"{'observed':>10}"
    print(hdr)
    for n, d in points:
        row = f"{int(n):>6}"
        for k in PRED:
            p = PRED[k].get(int(n))
            row += f"{(d - p):>+10.3f}" if p is not None else f"{'-':>10}"
        print(row + f"{d:>10.3f}")
    for k in PRED:
        chi = sum(((d - PRED[k][int(n)]) / SIGMA) ** 2
                  for n, d in points if int(n) in PRED[k])
        m = sum(1 for n, _ in points if int(n) in PRED[k])
        print(f"  {k}: chi2 = {chi:.1f} over {m} points (sigma = {SIGMA} ms)")

    f = fit(points)
    if not f:
        print("\nno monotone segmented fit with two points above a knee: "
              "report the raw points per the pre-registered fallback")
        above = [(n, d) for n, d in points if n > 0 and d > 0]
        if len(above) == 1:
            n, d = above[0]
            print(f"\nsingle non-zero point: c and the knee are not separately\n"
                  f"identified. Pricing below assumes knee = 0, which makes c\n"
                  f"an UPPER bound on the slope and the saving an upper bound\n"
                  f"too: any knee > 0 raises c but removes value below it.")
            verdicts(d / n * 1000.0, 0.0)
        return 0
    print(f"\nfit: c = {f['c_us']:.3f} us/dispatch, knee = {f['knee']:.0f} "
          f"dispatches [{f['knee_lo']:.0f}, {f['knee_hi']:.0f}], "
          f"slack = {f['slack_ms']:.3f} ms, rss = {f['rss']:.5f}, "
          f"points above knee = {f['n_above']}")
    if f["n_above"] < 2:
        print("  (bound, not a slope: fewer than two points above the knee)")
    margin = f["knee"] - SHIPPED
    print(f"shipped {SHIPPED} dispatches sit {margin:+.0f} dispatches from the "
          f"knee ({SHIPPED / (SHIPPED + max(0.0, margin)) * 100:.1f}% of the way)")

    verdicts(f["c_us"], f["slack_ms"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
