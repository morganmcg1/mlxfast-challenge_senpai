#!/usr/bin/env python3
"""Research-only (PR #473, R88-A): paired duplex contrasts on the four
step-level quantities decode_probe already prints but no analyser reads.

`maple_r85_arm_stats.py` reports per-label and total GPU-busy time. Under
DARKBLOOM_GPU_PROFILE_SPLIT=1 the per-label totals sum identically to that
total, so a "give-back" on an untouched kernel and the net total are the same
measurement seen twice -- there is no independent end-to-end check inside that
table. decode_probe's profile summary line already carries the missing
quantities:

    per steady step: wall=.. gpu_busy_sum=.. gpu_busy_union=.. gap=.. cbs=..
                     dispatches=..

`gpu_busy_union` is the merged interval union of the command buffers, so
`sum - union` prices command-buffer overlap and `wall - union` prices GPU idle
inside the step. This reads those per run and runs the same adjacent-duplex
estimator on each, so the additivity audit is quantitative rather than a
narrative. Wall comes from the full-precision --dump-steps file; the log line
is quantised to 1 us.

  python3 research/maple_r88a_additivity.py --steps 200 --arms base cand \\
      --offset 0 /tmp/maple-r88a/nat/[0-9]*.log
"""
import argparse
import json
import math
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from maple_pr443_duplex_stats import PCT_PER_US_STEP, t95  # noqa: E402
from maple_r85_arm_stats import ci, contrast, select_duplexes  # noqa: E402

SLOT_RE = re.compile(r"^(\d+)-rep(\d+)-([a-z0-9_]+)\.log$")
SUMMARY_RE = re.compile(
    r"^per steady step: wall=([\d.]+) ms gpu_busy_sum=([\d.]+) ms "
    r"gpu_busy_union=([\d.]+) ms gap=([-\d.]+) ms \([-\d.]+% of wall\) "
    r"cbs=([\d.]+) dispatches=([\d.]+)")
METRICS = ("wall", "busy_sum", "busy_union", "overlap", "gap")


def load_run(path, drop_first):
    m = SLOT_RE.match(os.path.basename(path))
    if not m:
        raise SystemExit(f"cannot parse slot from {path}")
    summary = None
    with open(path, errors="replace") as fh:
        for line in fh:
            hit = SUMMARY_RE.match(line)
            if hit:
                summary = [float(g) for g in hit.groups()]
    if summary is None:
        raise SystemExit(f"{path}: no 'per steady step:' profile summary line")
    wall_log, bsum, union, gap, cbs, disp = summary
    steps_path = path[: -len(".log")] + ".steps"
    with open(steps_path) as fh:
        step_ms = [float(x) for x in fh if x.strip()][drop_first:]
    metrics = {
        "wall": statistics.mean(step_ms) * 1e3,
        "busy_sum": bsum * 1e3,
        "busy_union": union * 1e3,
        # sum - union is the command-buffer overlap the union collapses.
        "overlap": max(bsum - union, 1e-6) * 1e3,
        "gap": max(gap, 1e-6) * 1e3,
    }
    return dict(slot=int(m.group(1)), rep=int(m.group(2)), arm=m.group(3),
                path=os.path.basename(path),
                set=os.path.basename(os.path.dirname(path)),
                wall_log_us=wall_log * 1e3, cbs=cbs, dispatches=disp,
                **{k: v for k, v in metrics.items()})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--steps", type=int, required=True)
    ap.add_argument("--arms", nargs=2, required=True,
                    help="base cand; equal names select null duplexes")
    ap.add_argument("--offset", type=int, default=0, choices=(0, 1))
    ap.add_argument("--drop-first", type=int, default=1,
                    help="steps dropped from --dump-steps (KV growth on step 0)")
    ap.add_argument("--scale-to-n", type=int, default=0)
    ap.add_argument("--json-out")
    args = ap.parse_args()
    base_arm, cand_arm = args.arms

    runs = sorted([load_run(p, args.drop_first) for p in args.paths],
                  key=lambda r: (r["set"], r["slot"]))
    expect = args.steps - args.drop_first
    duplexes = select_duplexes(runs, base_arm, cand_arm, args.offset)
    if len(duplexes) < 2:
        raise SystemExit(f"only {len(duplexes)} duplex(es) for "
                         f"{base_arm}/{cand_arm} at offset {args.offset}")

    kind = "NULL" if base_arm == cand_arm else "CONTRAST"
    print(f"{kind}: {cand_arm} minus {base_arm}   offset={args.offset}   "
          f"n_duplex={len(duplexes)}   steady steps expected {expect}")
    cbs = {r["cbs"] for r in runs}
    print(f"cbs/step across runs: {sorted(cbs)}   "
          f"dispatches/step: {sorted({r['dispatches'] for r in runs})}")
    for i, sign in duplexes:
        print(f"  duplex {runs[i]['set']} slots {runs[i]['slot']:>2}"
              f"({runs[i]['arm']}) -> {runs[i+1]['slot']:>2}"
              f"({runs[i+1]['arm']})  sign {sign:+.0f}")

    base_slots = [i if runs[i]["arm"] == base_arm else i + 1
                  for i, _ in duplexes]
    print(f"\n{'metric':>11} {'base us/step':>13} {'delta':>9} {'95% CI':>19} "
          f"{'SD':>8} {'%':>8}  score%")
    out = {"kind": kind, "arms": [base_arm, cand_arm], "offset": args.offset,
           "n_duplex": len(duplexes), "metrics": {}}
    for metric in METRICS:
        base_us = statistics.mean([runs[j][metric] for j in base_slots])
        vals = contrast(runs, duplexes, lambda r, k=metric: r[k])
        mean, hw, sd = ci(vals)
        d = base_us * math.expm1(mean)
        lo = base_us * math.expm1(mean - hw)
        hi = base_us * math.expm1(mean + hw)
        score = (f"{d*PCT_PER_US_STEP:+.4f} "
                 f"[{lo*PCT_PER_US_STEP:+.4f},{hi*PCT_PER_US_STEP:+.4f}]"
                 if metric in ("wall", "busy_sum", "busy_union") else "")
        print(f"{metric:>11} {base_us:13.1f} {d:+9.2f} "
              f"[{lo:+8.2f},{hi:+8.2f}] {base_us*sd:8.2f} "
              f"{100*math.expm1(mean):+8.3f}  {score}")
        entry = {"base_us_step": base_us, "us_step": d, "ci": [lo, hi],
                 "sd_us_step": base_us * sd}
        if args.scale_to_n > 1:
            h = t95(args.scale_to_n - 1) * sd / math.sqrt(args.scale_to_n)
            entry[f"hw_at_n{args.scale_to_n}"] = base_us * h
        out["metrics"][metric] = entry

    print("\nadditivity per arm (mean over its slots):")
    for arm in sorted({r["arm"] for r in runs}):
        sel = [r for r in runs if r["arm"] == arm]
        w = statistics.mean([r["wall"] for r in sel])
        s = statistics.mean([r["busy_sum"] for r in sel])
        u = statistics.mean([r["busy_union"] for r in sel])
        print(f"  {arm:>5}: wall {w:9.1f}  sum {s:9.1f}  union {u:9.1f}  "
              f"sum/union {s/u:6.4f}  (wall-union)/wall {(w-u)/w*100:5.2f}%")

    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump(out, fh, indent=1, sort_keys=True)
        print(f"\nwrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
