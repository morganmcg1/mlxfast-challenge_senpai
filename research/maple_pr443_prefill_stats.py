#!/usr/bin/env python3
"""Research-only (PR #443): paired duplex statistics for the prefill arm.

Reads the `prefill 512 tokens: X ms` line out of every
`research/maple_pr443_prefill_abba.sh` log, pairs adjacent runs into duplexes
(the ABBA order makes every adjacent pair one off/halved contrast), and reports
the mean log-ratio with a two-sided 95% t interval.

  python3 research/maple_pr443_prefill_stats.py /tmp/maple-pr443-prefill/[0-9]*.log
"""
import argparse
import math
import re
import statistics
import sys

# prefill ms -> % of the total score, from the campaign's pinned conversion
# (0.374750 %/ms on the prefill axis).
PCT_PER_MS = 0.374750
T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
       8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 15: 2.131,
       20: 2.086, 23: 2.069}

PREFILL_RE = re.compile(r"prefill 512 tokens:\s*([0-9.]+)\s*ms")


def t95(df):
    if df in T95:
        return T95[df]
    return 1.96 if df > 30 else T95[min(T95, key=lambda k: abs(k - df))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--arms", nargs=2, default=["off", "halved"])
    args = ap.parse_args()

    base, cand = args.arms
    runs = []
    for path in sorted(args.paths):
        arm = path.rsplit("-", 1)[-1].split(".")[0]
        text = open(path).read()
        m = PREFILL_RE.search(text)
        if not m:
            print(f"no prefill line in {path}", file=sys.stderr)
            return 1
        runs.append((path, arm, float(m.group(1))))

    for path, arm, ms in runs:
        print(f"{path.split('/')[-1]:28s} {arm:7s} {ms:8.2f} ms")

    for arm in (base, cand):
        vals = [ms for _, a, ms in runs if a == arm]
        print(f"\n{arm:7s} n={len(vals)} mean={statistics.mean(vals):.2f} ms "
              f"median={statistics.median(vals):.2f} ms "
              f"sd={statistics.pstdev(vals):.2f}")

    diffs = []
    for i in range(0, len(runs) - 1, 2):
        (_, a0, v0), (_, a1, v1) = runs[i], runs[i + 1]
        if {a0, a1} != {base, cand}:
            print(f"duplex {i//2+1} is not a {base}/{cand} pair", file=sys.stderr)
            return 1
        lo = math.log(v1 / v0) if a1 == cand else math.log(v0 / v1)
        diffs.append(lo)

    n = len(diffs)
    mean = statistics.mean(diffs)
    sd = statistics.stdev(diffs) if n > 1 else 0.0
    half = t95(n - 1) * sd / math.sqrt(n)
    base_ms = statistics.mean([ms for _, a, ms in runs if a == base])
    print(f"\nduplexes n={n}  mean log-ratio={mean:+.5f} "
          f"[{mean-half:+.5f}, {mean+half:+.5f}]")
    print(f"  = {100*(math.exp(mean)-1):+.3f}% "
          f"[{100*(math.exp(mean-half)-1):+.3f}%, "
          f"{100*(math.exp(mean+half)-1):+.3f}%] on a {base_ms:.2f} ms baseline")
    d_ms = base_ms * (math.exp(mean) - 1)
    d_lo = base_ms * (math.exp(mean - half) - 1)
    d_hi = base_ms * (math.exp(mean + half) - 1)
    print(f"  = {d_ms:+.3f} ms [{d_lo:+.3f}, {d_hi:+.3f}] "
          f"=> score {-d_ms*PCT_PER_MS:+.4f}% "
          f"[{-d_hi*PCT_PER_MS:+.4f}%, {-d_lo*PCT_PER_MS:+.4f}%]")
    floor = 0.95
    print(f"  prefill hard floor {floor}: needs the candidate within "
          f"{100*(1/floor - 1):.1f}% of baseline "
          f"({base_ms/floor:.2f} ms); "
          f"CI upper {base_ms*math.exp(mean+half):.2f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
