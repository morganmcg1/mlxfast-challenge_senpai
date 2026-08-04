#!/usr/bin/env python3
"""Score-weighted analysis of a multi-level, position-balanced cap screen.

Parses `[pNN-X] prefill_ms=... decode_ms=...` lines from
research/frieren_cap3_abba.sh, drops the discard arm, and reports per-level
means with standard errors on both axes plus the ranked-score estimate

    ns% ~= -(0.638 * dT% + 0.362 * dS%)

where dT% is the pure-decode-step change and dS% the 512-token prefill change,
both relative to the shipped level. Elasticities are the ranked-host values
recorded by the advisor (T 0.638, S 0.362); the optional --m5-factor scales only
the decode term, per the campaign M4->M5 pure-step convention.

Research-only.
"""

import argparse
import re
import statistics

LINE = re.compile(r"\[p(\d+)[^-\]]*-([A-Z])\] prefill_ms=([0-9.]+) decode_ms=([0-9.]+)")
E_T, E_S = 0.638, 0.362


def mean_se(vals):
    m = statistics.mean(vals)
    se = statistics.stdev(vals) / len(vals) ** 0.5 if len(vals) > 1 else 0.0
    return m, se


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--base", default="A", help="shipped level label")
    ap.add_argument("--m5-factor", type=float, default=1.0,
                    help="multiplier applied to the decode delta only")
    args = ap.parse_args()

    rows = [(int(p), a, float(s), float(t))
            for p, a, s, t in LINE.findall(open(args.log, errors="replace").read())
            if int(p) > 0]
    if not rows:
        raise SystemExit("no arm rows found")

    print(f"{'pos':>4} {'arm':>3} {'prefill ms':>11} {'decode ms':>10}")
    for p, a, s, t in rows:
        print(f"{p:>4} {a:>3} {s:>11.3f} {t:>10.4f}")

    levels = sorted({a for _, a, _, _ in rows})
    stats = {}
    for lv in levels:
        pre = [s for _, a, s, _ in rows if a == lv]
        dec = [t for _, a, _, t in rows if a == lv]
        stats[lv] = (mean_se(pre), mean_se(dec), len(pre))
    (bs, bse), (bt, bte), _ = stats[args.base]

    print(f"\n{'arm':>3} {'n':>2} {'S ms':>9} {'se':>6} {'dS%':>7} "
          f"{'T ms':>9} {'se':>6} {'dT%':>7} {'ns% est':>8}")
    for lv in levels:
        (s, sse), (t, tse), n = stats[lv]
        ds = (s - bs) / bs * 100
        dt = (t - bt) / bt * 100
        ns = -(E_T * dt * args.m5_factor + E_S * ds)
        print(f"{lv:>3} {n:>2} {s:>9.3f} {sse:>6.3f} {ds:>+7.3f} "
              f"{t:>9.4f} {tse:>6.4f} {dt:>+7.3f} {ns:>+8.3f}")

    print(f"\nelasticities T {E_T} S {E_S}; decode delta scaled by "
          f"{args.m5_factor}")
    print("ns% est > 0 means predicted ranked score improvement")


if __name__ == "__main__":
    main()
