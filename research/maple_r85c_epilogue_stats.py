#!/usr/bin/env python3
"""Research-only (PR #457, R85-C rev2): wall-clock paired-duplex statistics for
a two-binary ABBA session produced by `research/maple_r85c_epilogue_ab.sh`.

`maple_r85_arm_stats.py` answers the per-kernel GPU-time question from the same
runs. This answers the end-to-end one: does the whole decode step get shorter?

Each slot contributes one per-step statistic over the steady window (step 0 is
dropped; it pays the one-time KV growth concat). Adjacent slots form duplexes
exactly as in the per-kernel analyser, so drift between neighbouring runs is
differenced out and the ABBA sign counterbalancing removes within-duplex drift.
`--offset 1` selects same-arm duplexes: the in-session null.

  python3 research/maple_r85c_epilogue_stats.py --arms base cand \\
      /tmp/maple-r85c-epi/[0-9]*.steps
"""
import argparse
import json
import math
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from maple_pr443_duplex_stats import PCT_PER_US_STEP, t95, trimmed_mean  # noqa: E402

SLOT_RE = re.compile(r"^(\d+)-rep(\d+)-([a-z_]+)\.steps$")


def load(paths, drop_first):
    runs = []
    for path in paths:
        m = SLOT_RE.match(os.path.basename(path))
        if not m:
            raise SystemExit(f"cannot parse slot from {path}")
        with open(path) as fh:
            ms = [float(x) for x in fh if x.strip()]
        steady = ms[drop_first:]
        runs.append(dict(slot=int(m.group(1)), rep=int(m.group(2)),
                         arm=m.group(3), n=len(steady),
                         median=statistics.median(steady) * 1e3,
                         trimmed=trimmed_mean(steady) * 1e3,
                         mean=statistics.mean(steady) * 1e3))
    runs.sort(key=lambda r: r["slot"])
    return runs


def duplexes(runs, base_arm, cand_arm, offset):
    out = []
    null = base_arm == cand_arm
    for i in range(offset, len(runs) - 1, 2):
        a, b = runs[i], runs[i + 1]
        if null:
            if a["arm"] != base_arm or b["arm"] != base_arm:
                continue
            out.append((i, 1.0 if len(out) % 2 == 0 else -1.0))
        else:
            if {a["arm"], b["arm"]} != {base_arm, cand_arm}:
                continue
            out.append((i, 1.0 if b["arm"] == cand_arm else -1.0))
    return out


def report(runs, pairs, base_arm, stat, label):
    contrasts = [sign * (math.log(runs[i + 1][stat]) - math.log(runs[i][stat]))
                 for i, sign in pairs]
    base_slots = [i if runs[i]["arm"] == base_arm else i + 1 for i, _ in pairs]
    base_us = statistics.mean([runs[j][stat] for j in base_slots])
    n = len(contrasts)
    m = statistics.mean(contrasts)
    sd = statistics.stdev(contrasts) if n > 1 else float("nan")
    hw = t95(n - 1) * sd / math.sqrt(n) if n > 1 else float("nan")
    d = base_us * math.expm1(m)
    lo = base_us * math.expm1(m - hw)
    hi = base_us * math.expm1(m + hw)
    sig = "***" if (m - hw) * (m + hw) > 0 else ""
    print(f"  {label:>9}  base {base_us:9.1f} us/step   "
          f"cand-base {-d:+8.2f} [{-hi:+8.2f},{-lo:+8.2f}] us/step   "
          f"score {-d*PCT_PER_US_STEP:+.4f}% "
          f"[{-hi*PCT_PER_US_STEP:+.4f}%,{-lo*PCT_PER_US_STEP:+.4f}%] {sig}")
    return -d, -hi, -lo


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--arms", nargs=2, required=True)
    ap.add_argument("--offset", type=int, default=0, choices=(0, 1))
    ap.add_argument("--drop-first", type=int, default=1)
    ap.add_argument("--json-out")
    args = ap.parse_args()
    base_arm, cand_arm = args.arms

    runs = load(args.paths, args.drop_first)
    pairs = duplexes(runs, base_arm, cand_arm, args.offset)
    if len(pairs) < 2:
        raise SystemExit(f"only {len(pairs)} duplex(es) at offset {args.offset}")

    kind = "NULL" if base_arm == cand_arm else "CONTRAST"
    print(f"{kind}: {cand_arm} minus {base_arm}  offset={args.offset}  "
          f"n_duplex={len(pairs)}  steady_steps={runs[0]['n']}")
    for i, sign in pairs:
        print(f"  duplex slots {runs[i]['slot']:>2}({runs[i]['arm']}) -> "
              f"{runs[i+1]['slot']:>2}({runs[i+1]['arm']})  sign {sign:+.0f}")
    print("  a negative cand-base delta means the candidate is FASTER; "
          "sign is flipped so positive = win")
    out = {"kind": kind, "base_arm": base_arm, "cand_arm": cand_arm,
           "offset": args.offset, "n_duplex": len(pairs),
           "steady_steps": runs[0]["n"], "stats": {},
           "slots": [{k: r[k] for k in ("slot", "rep", "arm", "median",
                                        "trimmed", "mean")} for r in runs]}
    for stat, label in (("median", "median"), ("trimmed", "trim10"),
                        ("mean", "mean")):
        d, lo, hi = report(runs, pairs, base_arm, stat, label)
        out["stats"][label] = {"delta_us_step": d, "ci95_lo": lo,
                              "ci95_hi": hi,
                              "score_pct": d * PCT_PER_US_STEP}
    print("\n  per-slot medians (us/step):")
    for r in runs:
        print(f"    slot {r['slot']:>2} rep{r['rep']} {r['arm']:>4}  "
              f"{r['median']:9.1f}")
    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump(out, fh, indent=2)
        print(f"\n  wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
