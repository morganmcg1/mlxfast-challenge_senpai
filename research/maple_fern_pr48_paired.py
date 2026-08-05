#!/usr/bin/env python3
"""Research-only interleaved paired decode screen (not part of the submission).

Runs `pairs` A/B pairs of `steps`-step teacher-forced decode arms, alternating
process launches so drift and thermal trend are shared between the arms, then
reports a paired t-statistic on the per-pair mean-step-time difference.

  python3 research/maple_fern_pr48_paired.py --pairs 12 --steps 512 \
      --env DARKBLOOM_DECODE_NVFP4_QKV_R1_SIMDGROUPS=16

Every model-holding run must be the only one on the host.
"""
import argparse
import math
import os
import re
import statistics
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROBE = os.path.join(REPO, "research/decode_probe.py")
STATS = re.compile(
    r"decode steps=(\d+) mean=([\d.]+) ms median=([\d.]+) ms .* min=([\d.]+) ms")
DIVERGE = re.compile(r"teacher-forced greedy tokens: (\d+) divergences")


def run_arm(steps, overrides, tag):
    env = dict(os.environ)
    env.update(overrides)
    out = subprocess.run(
        [sys.executable, PROBE, "--steps", str(steps),
         "--stderr", f"/tmp/paired_{tag}.err"],
        cwd=REPO, capture_output=True, text=True, env=env).stdout
    m, d = STATS.search(out), DIVERGE.search(out)
    if not m or not d:
        raise SystemExit(f"arm {tag} produced no stats:\n{out}")
    return {
        "divergences": int(d.group(1)),
        "mean": float(m.group(2)),
        "median": float(m.group(3)),
        "min": float(m.group(4)),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", type=int, default=12)
    ap.add_argument("--steps", type=int, default=512)
    ap.add_argument("--env", action="append", default=[],
                    help="KEY=VALUE applied to the candidate arm only")
    args = ap.parse_args()
    cand = dict(kv.split("=", 1) for kv in args.env)
    print(f"control=stock candidate={cand} pairs={args.pairs} steps={args.steps}",
          flush=True)

    rows = []
    for i in range(args.pairs):
        # Alternate which arm leads so a monotone host trend cannot bias the
        # paired difference in one direction.
        order = [("control", {}), ("candidate", cand)]
        if i % 2:
            order.reverse()
        got = {}
        for name, ov in order:
            got[name] = run_arm(args.steps, ov, f"{name}_{i}")
            print(f"pair {i} {name}: {got[name]}", flush=True)
        rows.append(got)

    for stat in ("mean", "median", "min"):
        a = [r["control"][stat] for r in rows]
        b = [r["candidate"][stat] for r in rows]
        d = [y - x for x, y in zip(a, b)]
        md, sd = statistics.mean(d), statistics.stdev(d)
        t = md / (sd / math.sqrt(len(d))) if sd else float("inf")
        print(f"\n{stat}: control={statistics.mean(a):.4f} ms "
              f"candidate={statistics.mean(b):.4f} ms "
              f"delta={md:+.4f} ms ({md/statistics.mean(a)*100:+.3f}%) "
              f"sd={sd:.4f} t={t:+.3f} n={len(d)}")
        print("  pair deltas: " + " ".join(f"{x:+.4f}" for x in d))
    bad = sum(r[k]["divergences"] for r in rows for k in r)
    print(f"\ntotal teacher-forced divergences across all arms: {bad}")


if __name__ == "__main__":
    sys.exit(main())
