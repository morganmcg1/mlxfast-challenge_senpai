#!/usr/bin/env python3
"""Extract the steady-state decode step time from --local-iterate logs.

The harness prints `last_step_seconds` at 8-token boundaries. The first
sample (token 1) carries kernel-compile and cache warmup and is discarded;
the remainder is a low-variance estimate of the timed decode step that the
ranked M5 measures. `decode_seconds_per_token` dilutes this with the seed
pass, so it under-reports per-step effects and carries extra run-to-run noise.
"""

import argparse
import glob
import json
import os
import re
import statistics

SAMPLE = re.compile(
    r"checked decode (\d+)/(\d+) tokens last_step_seconds=([0-9.]+)")
NAME = re.compile(r"log-(.+)-b(\d+)\.txt$")


def samples(path, min_token):
    out = []
    with open(path, errors="replace") as handle:
        for line in handle:
            hit = SAMPLE.search(line)
            if hit and int(hit.group(1)) >= min_token:
                out.append(float(hit.group(3)))
    return out


# E[max of m iid N(0,1)]; used to debias the best-of-m screen argmax.
EMAX = {1: 0.0, 2: 0.5642, 3: 0.8463, 4: 1.0294, 5: 1.1630, 6: 1.2672,
        7: 1.3522, 8: 1.4236, 9: 1.4850, 10: 1.5388, 12: 1.6292, 16: 1.7660}


def contrasts(rows, control):
    """Paired within-block contrasts against the control arm."""
    by_block = {}
    for r in rows:
        by_block.setdefault(r["block"], {})[r["arm"]] = r["steady_mean_us"]
    arms = sorted({r["arm"] for r in rows} - {control})
    out = []
    for arm in arms:
        diffs = [b[arm] - b[control] for b in by_block.values()
                 if arm in b and control in b]
        if not diffs:
            continue
        mean = statistics.mean(diffs)
        sd = statistics.stdev(diffs) if len(diffs) > 1 else float("nan")
        sem = sd / len(diffs) ** 0.5 if len(diffs) > 1 else float("nan")
        out.append({"arm": arm, "n_pairs": len(diffs), "delta_us": mean,
                    "sem_us": sem, "t": mean / sem if sem else float("nan")})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logdir")
    ap.add_argument("--min-token", type=int, default=16)
    ap.add_argument("--json-out", default="")
    ap.add_argument("--control", default="")
    args = ap.parse_args()

    rows = []
    for path in sorted(glob.glob(os.path.join(args.logdir, "log-*-b*.txt"))):
        hit = NAME.search(os.path.basename(path))
        if not hit:
            continue
        vals = samples(path, args.min_token)
        if len(vals) < 3:
            continue
        rows.append({
            "arm": hit.group(1),
            "block": int(hit.group(2)),
            "n": len(vals),
            "steady_mean_us": 1e6 * statistics.mean(vals),
            "steady_median_us": 1e6 * statistics.median(vals),
            "within_sd_us": 1e6 * statistics.stdev(vals),
        })

    rows.sort(key=lambda r: (r["block"], r["arm"]))
    width = max(len(r["arm"]) for r in rows) if rows else 4
    print(f"{'block':>5} {'arm':<{width}} {'n':>3} {'steady_us':>10} "
          f"{'median_us':>10} {'within_sd':>10}")
    for r in rows:
        print(f"{r['block']:>5} {r['arm']:<{width}} {r['n']:>3} "
              f"{r['steady_mean_us']:>10.1f} {r['steady_median_us']:>10.1f} "
              f"{r['within_sd_us']:>10.1f}")

    if args.control:
        cons = contrasts(rows, args.control)
        print(f"\npaired within-block contrasts vs {args.control} "
              f"(+us = slower)")
        print(f"{'arm':<{width}} {'pairs':>5} {'delta_us':>9} {'sem':>7} "
              f"{'t':>6}")
        for c in sorted(cons, key=lambda c: c["delta_us"]):
            print(f"{c['arm']:<{width}} {c['n_pairs']:>5} "
                  f"{c['delta_us']:>9.1f} {c['sem_us']:>7.1f} {c['t']:>6.2f}")
        best = min(cons, key=lambda c: c["delta_us"])
        m = len(cons)
        bias = EMAX.get(m, 1.4236) * best["sem_us"]
        print(f"\nargmax={best['arm']} raw={best['delta_us']:.1f}us "
              f"debias(+{bias:.1f}us for best-of-{m}) -> "
              f"{best['delta_us'] + bias:.1f}us")

    if args.json_out:
        with open(args.json_out, "w") as handle:
            json.dump(rows, handle, indent=1)


if __name__ == "__main__":
    main()
