#!/usr/bin/env python3
"""Audit the R1 control population: drift, prediction interval, subgroup structure.

The control is the candidate-prefill axis of every scored receipt on this
account between the promoted frontier and R1. Reviewer asked for three checks:
bookkeeping reconciliation, chronological drift, and prefill-code homogeneity.
"""
import math
from datetime import datetime

# (created_utc, submission, commit, candidate_prefill_ms, candidate_decode_ms)
ROWS = [
    ("2026-08-09T00:58", "7ce1262d", "ef055b9", 96.278, 4.8937),
    ("2026-08-09T01:32", "83fd2642", "5a43d32", 96.055, 4.8989),
    ("2026-08-09T02:56", "25e1f18e", "4b0e051", 96.070, 4.8941),
    ("2026-08-09T03:18", "d11026c9", "d6a5f9e", 96.120, 4.9312),
    ("2026-08-09T03:42", "99309c61", "-", 96.198, 5.5065),
    ("2026-08-09T04:06", "05dd8bbf", "e1b6e2b", 96.193, 4.9005),
    ("2026-08-09T04:31", "f8719c48", "03f249c", 96.328, 6.7809),
    ("2026-08-09T04:55", "ab6a15a1", "ca91d86", 96.316, 4.9161),
    ("2026-08-09T05:22", "b835a980", "86696a1", 95.870, 5.0770),
    ("2026-08-09T05:44", "4fec8e2d", "5d9060a", 96.253, 4.9126),
    ("2026-08-09T06:14", "ecd89cac", "057c519", 96.184, 4.9436),
    ("2026-08-09T06:49", "ab3a2433", "68ab5ce", 95.953, 5.2664),
    ("2026-08-09T07:14", "a000a397", "edfd81e", 96.236, 4.9157),
]
R1 = ("2026-08-09T11:24", "b3b6457f", "a4d7450", 96.797, 4.9243)


def hours(ts, t0):
    f = "%Y-%m-%dT%H:%M"
    return (datetime.strptime(ts, f) - datetime.strptime(t0, f)).total_seconds() / 3600.0


def mean(v):
    return sum(v) / len(v)


def sd(v):
    m = mean(v)
    return math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))


def main():
    t0 = ROWS[0][0]
    t = [hours(r[0], t0) for r in ROWS]
    y = [r[3] for r in ROWS]
    n = len(y)
    m, s = mean(y), sd(y)
    print(f"n={n} mean={m:.4f} sd={s:.4f} min={min(y):.3f} max={max(y):.3f}")

    # Welch-free prediction interval for a single new observation.
    # t_{0.975, 12} = 2.179
    tcrit = 2.179
    se_pred = s * math.sqrt(1 + 1 / n)
    lo, hi = m - tcrit * se_pred, m + tcrit * se_pred
    print(f"95% prediction interval for one new receipt: [{lo:.3f}, {hi:.3f}]")
    tstat = (R1[3] - m) / se_pred
    print(f"R1={R1[3]:.3f} delta={R1[3]-m:+.3f} ms  prediction-t={tstat:.2f} (df={n-1})")
    d_lo = (R1[3] - m) - tcrit * se_pred
    d_hi = (R1[3] - m) + tcrit * se_pred
    print(f"effect 95% CI: [{d_lo:+.3f}, {d_hi:+.3f}] ms")

    # Distribution-free: R1 is the max of n+1 exchangeable draws under the null.
    print(f"distribution-free p (max of {n+1}) = {1.0/(n+1):.4f}")

    # Chronological drift: OLS slope + its t.
    tm, ym = mean(t), m
    sxx = sum((x - tm) ** 2 for x in t)
    sxy = sum((x - tm) * (v - ym) for x, v in zip(t, y))
    slope = sxy / sxx
    icpt = ym - slope * tm
    resid = [v - (icpt + slope * x) for x, v in zip(t, y)]
    s_res = math.sqrt(sum(r * r for r in resid) / (n - 2))
    se_slope = s_res / math.sqrt(sxx)
    print(f"\ndrift slope={slope:+.4f} ms/h  se={se_slope:.4f}  t={slope/se_slope:+.2f} (df={n-2})")
    t_r1 = hours(R1[0], t0)
    pred = icpt + slope * t_r1
    print(f"R1 is {t_r1:.2f} h after first control; drift-extrapolated expectation={pred:.3f} ms")
    print(f"drift can explain {pred - m:+.3f} ms of the {R1[3]-m:+.3f} ms effect")
    se_dp = s_res * math.sqrt(1 + 1 / n + (t_r1 - tm) ** 2 / sxx)
    print(f"drift-adjusted prediction-t = {(R1[3]-pred)/se_dp:+.2f}, se_pred={se_dp:.3f}")

    # Prefill-code homogeneity proxy: decode-damaged arms must still sit in the
    # prefill cluster if their edits never touched prefill.
    bad = [r for r in ROWS if r[4] > 5.0]
    good = [r for r in ROWS if r[4] <= 5.0]
    print(f"\ndecode-damaged arms (n={len(bad)}): prefill mean={mean([r[3] for r in bad]):.3f}")
    print(f"decode-healthy arms (n={len(good)}): prefill mean={mean([r[3] for r in good]):.3f}")
    print(f"both subgroup means are below R1 by "
          f"{R1[3]-mean([r[3] for r in bad]):+.3f} / {R1[3]-mean([r[3] for r in good]):+.3f} ms")


if __name__ == "__main__":
    main()
