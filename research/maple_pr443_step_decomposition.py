#!/usr/bin/env python3
"""Research-only (PR #443): whole-step attribution of a per-kernel win.

`maple_pr443_duplex_stats.py` answers "did kernel K get faster?". It cannot
answer "did the decode step get faster?", because a change that removes traffic
from one kernel may hand work, cache pressure, or residency back to another.
Reconciling the two is the difference between a per-call result and a scored
one.

The steady window is rebuilt from the GPUPROF stream alone (the driver-side
step spans live only in the probe process): dispatch order is deterministic and
G2-identical across arms, so the last `cbs_per_step * steady_steps` records are
exactly the steady window in every run. Every label is then contrasted inside
the same counterbalanced duplexes, ratio-adjusted against the invariant control
so the per-run clock factor cancels, and converted back to us/step. The sum
over labels is the causal step-time estimate under the single identifying
assumption that the control kernel is unaffected by the flag.

  python3 research/maple_pr443_step_decomposition.py --steps 33 \\
      --arms off halved /tmp/maple-pr443-abba/[0-9]*.err
"""
import argparse
import math
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decode_probe import parse_gpuprof_line, shorten  # noqa: E402
from maple_pr443_duplex_stats import CONTROL, PCT_PER_US_STEP, t95  # noqa: E402

SLOT_RE = re.compile(r"^(\d+)-rep(\d+)-([a-z_]+)\.err$")


def label_totals(path, cbs_per_step, steady_steps):
    """{label: us in the steady window}, plus the window's total busy us."""
    records = []
    with open(path, errors="replace") as fh:
        for line in fh:
            if not line.startswith("GPUPROF "):
                continue
            rec = parse_gpuprof_line(line)
            if rec is not None:
                records.append(rec)
    want = cbs_per_step * steady_steps
    if len(records) < want:
        raise SystemExit(f"{path}: {len(records)} records, need {want}")
    window = records[-want:]
    totals = {}
    busy = 0.0
    for start, end, nops, names in window:
        key = "|".join(shorten(p) for p in names.split("|"))
        if nops > 1:
            key = f"[{nops}] {key}"
        dur = (end - start) * 1e6
        totals[key] = totals.get(key, 0.0) + dur
        busy += dur
    return totals, busy


def ci(values):
    n = len(values)
    mean = statistics.mean(values)
    hw = t95(n - 1) * statistics.stdev(values) / math.sqrt(n) if n > 1 else float("nan")
    return mean, hw


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--steps", type=int, required=True)
    ap.add_argument("--cbs-per-step", type=int, default=406)
    ap.add_argument("--control", default=CONTROL)
    ap.add_argument("--arms", nargs=2, default=["off", "halved"])
    ap.add_argument("--min-us-step", type=float, default=5.0)
    args = ap.parse_args()
    base_arm, cand_arm = args.arms
    steady_steps = args.steps - 1

    runs = []
    for path in args.paths:
        m = SLOT_RE.match(os.path.basename(path))
        if not m:
            raise SystemExit(f"cannot parse slot from {path}")
        totals, busy = label_totals(path, args.cbs_per_step, steady_steps)
        runs.append(dict(slot=int(m.group(1)), arm=m.group(3),
                         path=os.path.basename(path),
                         set=os.path.basename(os.path.dirname(path)),
                         totals=totals, busy=busy))
    runs.sort(key=lambda r: (r["set"], r["slot"]))

    control = None
    for key in runs[0]["totals"]:
        if args.control in key:
            control = key
            break
    if control is None:
        raise SystemExit(f"control {args.control} not found")

    labels = sorted(set().union(*[set(r["totals"]) for r in runs]),
                    key=lambda k: -runs[0]["totals"].get(k, 0.0))
    shared = [r["totals"] for r in runs]
    missing = [k for k in labels if any(k not in t for t in shared)]
    print(f"window: last {args.cbs_per_step * steady_steps} command buffers "
          f"= {args.cbs_per_step}/step x {steady_steps} steady steps")
    print(f"labels: {len(labels)}  control: {control}")
    if missing:
        print(f"labels absent from some run (arm-specific): {missing}")

    duplexes = list(range(0, len(runs) - 1, 2))
    for i in duplexes:
        if {runs[i]["arm"], runs[i + 1]["arm"]} != {base_arm, cand_arm}:
            raise SystemExit(f"slots {runs[i]['slot']},{runs[i+1]['slot']} not a duplex")

    def duplex_log_contrast(getter):
        out = []
        for i in duplexes:
            a, b = runs[i], runs[i + 1]
            sign = 1.0 if b["arm"] == cand_arm else -1.0
            out.append(sign * (math.log(getter(b)) - math.log(getter(a))))
        return out

    print(f"\nper-label ratio-adjusted contrast ({cand_arm} minus {base_arm}, "
          "negative = candidate faster)")
    print(f"{'us/step':>9} {'delta%':>9} {'CI low%':>9} {'CI high%':>9} "
          f"{'us/step d':>10} {'sig':>4}  kernel")
    total_point = 0.0
    total_lo = 0.0
    total_hi = 0.0
    rows = []
    for key in labels:
        if any(key not in r["totals"] for r in runs):
            continue
        base_us = statistics.mean([r["totals"][key] / steady_steps
                                   for r in runs if r["arm"] == base_arm])
        if base_us < args.min_us_step and args.control not in key:
            continue
        vals = duplex_log_contrast(
            lambda r, k=key: r["totals"][k] / r["totals"][control])
        mean, hw = ci(vals)
        d_us = base_us * math.expm1(mean)
        lo_us = base_us * math.expm1(mean - hw)
        hi_us = base_us * math.expm1(mean + hw)
        sig = "***" if (mean - hw) * (mean + hw) > 0 else ""
        rows.append((base_us, mean, hw, d_us, lo_us, hi_us, sig, key))
        total_point += d_us
        total_lo += lo_us
        total_hi += hi_us
    for base_us, mean, hw, d_us, lo_us, hi_us, sig, key in rows:
        print(f"{base_us:9.1f} {100*math.expm1(mean):+9.3f} "
              f"{100*math.expm1(mean-hw):+9.3f} {100*math.expm1(mean+hw):+9.3f} "
              f"{d_us:+10.2f} {sig:>4}  {key}")

    covered = sum(r[0] for r in rows)
    base_busy = statistics.mean([r["busy"] / steady_steps
                                 for r in runs if r["arm"] == base_arm])
    print(f"\nlabels shown cover {covered:.0f} of {base_busy:.0f} us/step "
          f"({100*covered/base_busy:.1f}%)")
    print(f"sum of shown per-label deltas: {total_point:+.1f} us/step "
          f"[{total_lo:+.1f}, {total_hi:+.1f}] (CI sum is indicative, not exact)")

    busy_ratio = duplex_log_contrast(lambda r: r["busy"] / r["totals"][control])
    busy_raw = duplex_log_contrast(lambda r: r["busy"])
    for name, vals in (("ratio-adjusted vs control", busy_ratio),
                       ("unadjusted (absolute)", busy_raw)):
        mean, hw = ci(vals)
        print(f"\ntotal steady GPU busy, {name}: "
              f"{base_busy*math.expm1(mean):+.1f} us/step "
              f"[{base_busy*math.expm1(mean-hw):+.1f}, "
              f"{base_busy*math.expm1(mean+hw):+.1f}]  "
              f"({100*math.expm1(mean):+.3f}%)")
        print(f"  score: {base_busy*math.expm1(mean)*PCT_PER_US_STEP:+.4f}% "
              f"[{base_busy*math.expm1(mean-hw)*PCT_PER_US_STEP:+.4f}, "
              f"{base_busy*math.expm1(mean+hw)*PCT_PER_US_STEP:+.4f}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
