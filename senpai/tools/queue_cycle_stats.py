#!/usr/bin/env python3
"""Estimate submission-channel cycle time from a captured `mlxfast submissions --all` dump.

Each solver appears to hold at most one in-flight submission, so the gap between one
solver's consecutive creation times is an upper bound on (service time + turnaround).
That is a closed-loop estimator and is robust to the sampling error that corrupts
"backlog growth" estimates taken from two widely spaced polls.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import statistics as st

PAT = re.compile(
    r"^([0-9a-f]{7})\s+(\S+)\s+(promoted|rejected|failed|validating|queued|running|pending)\b"
)
CRE = re.compile(r"(\d+/\d+/\d+,\s+\d+:\d+\s+[AP]M)\s*$")
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def load(path: str):
    rows = []
    with open(path) as fh:
        for line in fh:
            s = ANSI.sub("", line.rstrip()).strip()
            m = PAT.match(s)
            c = CRE.search(s)
            if not m or not c:
                continue
            rows.append(
                (
                    m.group(1),
                    m.group(2),
                    m.group(3),
                    dt.datetime.strptime(c.group(1), "%m/%d/%y, %I:%M %p"),
                )
            )
    rows.sort(key=lambda r: r[3])
    return rows


def gaps_for(rows, hours, last):
    sel = [r for r in rows if r[3] >= last - dt.timedelta(hours=hours)]
    by = {}
    for _sid, solver, _stt, t in sel:
        by.setdefault(solver, []).append(t)
    out = []
    for solver, v in by.items():
        v.sort()
        out += [
            (solver, round((v[i + 1] - v[i]).total_seconds() / 60))
            for i in range(len(v) - 1)
        ]
    return sel, [(s, g) for s, g in out if 0 < g < 400]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dump")
    args = ap.parse_args()
    rows = load(args.dump)
    last = rows[-1][3]
    print(f"record: n={len(rows)} last_creation={last}")

    for hours in (24, 12, 6, 3):
        sel, gs = gaps_for(rows, hours, last)
        vals = [g for _s, g in gs]
        if not vals:
            continue
        print(
            f"\nwindow=last {hours}h  arrivals={len(sel)} ({len(sel)/hours:.1f}/h)  "
            f"solvers={len({r[1] for r in sel})}"
        )
        print(
            f"  per-solver cycle gaps n={len(vals)} median={st.median(vals):.0f} "
            f"mean={st.mean(vals):.0f} p25={sorted(vals)[len(vals)//4]} "
            f"p75={sorted(vals)[3*len(vals)//4]} min={min(vals)} max={max(vals)}"
        )

    sel, gs = gaps_for(rows, 6, last)
    print("\nlast-6h gaps by solver:")
    by = {}
    for s, g in gs:
        by.setdefault(s, []).append(g)
    for s, v in sorted(by.items(), key=lambda kv: -len(kv[1])):
        print(f"  {s:14s} n={len(v):2d} {v}")

    pend = [r for r in rows if r[2] not in {"promoted", "rejected", "failed"}]
    print(f"\nnon-terminal now: {len(pend)} across {len({r[1] for r in pend})} solvers")
    for sid, solver, stt, t in pend:
        print(f"  {sid} {solver:14s} {stt:10s} created {t:%H:%M}")


if __name__ == "__main__":
    main()
