#!/usr/bin/env python3
"""R113 -- structure of the per-draw noise on the public MLXFast leaderboard.

Motivation
----------
Section 0P.12 established that the crown (2.61650354381456, receipt cc6ddc1,
solver `a-github-name`) is the running maximum of a noisy replay process rather
than a code frontier.  The single largest remaining uncertainty in the plan is
the *per-draw relative standard deviation*: at sd=0.56% (our own n=3) twenty
draws give P(crown)=32%, at sd=0.911% (the crown holder's n=16 burst) they give
87%.  Everything downstream hangs on that number.

This script pools EVERY scored submission on the public board to answer:

  Q1. What is the pooled within-solver-within-day per-draw sd?  (many more df
      than either of our two current estimates)
  Q2. Is there a systematic hour-of-day effect?  If the ranked host is quieter
      at some hours, firing in the quiet window is a free mean shift, worth the
      same as a code win and costing nothing.
  Q3. Has the field mean drifted over calendar time (harness/host changes)?
      A drifting mean would mean the crown was set on a *different* machine
      population and is not comparable to today's draws at all.

Method notes
------------
* `mlxfast submissions --all` is the only source.  Bare `submissions` silently
  omits rows.  Output is ANSI-coloured; strip before parsing.
* The score column is the normalized official score.  Rows with status `failed`
  carry no score and are dropped.
* Q1 uses a *within-group* (solver x calendar-day) decomposition so that genuine
  code differences between solvers, and code changes across days, do not leak
  into the noise estimate.  Only groups with >= 3 scored rows contribute, and
  each group contributes its own (n-1) degrees of freedom.  This is the pooled
  within-group variance, i.e. exactly the replication noise we care about.
* All sds are reported RELATIVE (sd / group mean), because the score scale has
  changed by 2.6x over the life of the competition (1.00 -> 2.61) and an
  absolute sd would be meaningless across eras.
"""

from __future__ import annotations

import math
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def strip_ansi(s: str) -> str:
    return ANSI_RE.sub("", s)


def load_rows() -> list[dict]:
    out = subprocess.run(
        ["mlxfast", "submissions", "--all"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    rows = []
    for raw in out.splitlines():
        line = strip_ansi(raw).rstrip()
        if not line or line.startswith(("eigenlabs", "submission", "\u2500")):
            continue
        # Fixed-ish columns; split on 2+ spaces is reliable for the leading
        # fields (submission / solver / status / score) which is all we need,
        # plus the trailing created timestamp.
        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) < 4:
            continue
        sub, solver, status, score = parts[0], parts[1], parts[2].strip().lower(), parts[3]
        created = parts[-1]
        try:
            val = float(score)
        except ValueError:
            continue  # 'n/a' -> failed run, no score
        try:
            ts = datetime.strptime(created, "%m/%d/%y, %I:%M %p")
        except ValueError:
            continue
        rows.append(
            dict(sub=sub, solver=solver, status=status, score=val, ts=ts)
        )
    return rows


def pooled_within_rel_sd(groups: dict, label: str) -> tuple[float, int, int]:
    """Pooled within-group relative sd.  Returns (rel_sd, df, n_groups)."""
    ss = 0.0
    df = 0
    used = 0
    for _, vals in groups.items():
        if len(vals) < 3:
            continue
        m = sum(vals) / len(vals)
        if m <= 0:
            continue
        # relative residuals so eras with different score scales pool correctly
        ss += sum(((v - m) / m) ** 2 for v in vals)
        df += len(vals) - 1
        used += 1
    if df == 0:
        return float("nan"), 0, 0
    return math.sqrt(ss / df), df, used


def norm_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def main() -> int:
    rows = load_rows()
    scored = [r for r in rows if r["status"] in ("promoted", "rejected")]
    print(f"total rows parsed        : {len(rows)}")
    print(f"scored rows (prom/rej)   : {len(scored)}")
    if not scored:
        return 1
    print(f"date span                : {min(r['ts'] for r in scored)} .. "
          f"{max(r['ts'] for r in scored)}")

    # ---------------------------------------------------------------- Q3 drift
    print("\n== Q3. field mean by calendar day (scored rows) ==")
    byday = defaultdict(list)
    for r in scored:
        byday[r["ts"].date()].append(r["score"])
    days = sorted(byday)
    for d in days[-14:]:
        v = byday[d]
        m = sum(v) / len(v)
        hi = max(v)
        print(f"  {d}  n={len(v):4d}  mean={m:.5f}  max={hi:.5f}")

    # Restrict the noise analysis to the modern era: the score scale is only
    # comparable once the frontier stopped moving by large code steps.
    modern = [r for r in scored if r["ts"].date() >= days[-1].replace(day=days[-1].day)]
    # ...that is just today; use an explicit window instead.
    cutoff = sorted(days)[-5]
    modern = [r for r in scored if r["ts"].date() >= cutoff]
    print(f"\nmodern window            : {cutoff} onwards, n={len(modern)}")

    # ---------------------------------------------------------------- Q1 noise
    print("\n== Q1. pooled within-(solver x day) relative sd ==")
    for name, subset in (("ALL TIME", scored), ("MODERN", modern)):
        g = defaultdict(list)
        for r in subset:
            g[(r["solver"], r["ts"].date())].append(r["score"])
        sd, df, ng = pooled_within_rel_sd(g, name)
        print(f"  {name:9s}  rel_sd={sd*100:.4f}%   df={df:5d}   groups={ng}")

    # per-solver detail in the modern window
    print("\n  modern per-solver (n>=3 in window):")
    gs = defaultdict(list)
    for r in modern:
        gs[r["solver"]].append(r["score"])
    for s, v in sorted(gs.items(), key=lambda kv: -len(kv[1])):
        if len(v) < 3:
            continue
        m = sum(v) / len(v)
        sd = math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))
        print(f"    {s:22s} n={len(v):3d} mean={m:.5f} rel_sd={sd/m*100:6.3f}% "
              f"min={min(v):.5f} max={max(v):.5f}")

    # ------------------------------------------------------------ Q2 hour effect
    print("\n== Q2. hour-of-day effect (modern window, within-solver centred) ==")
    # Centre each solver's scores on that solver's own mean so that solver skill
    # does not masquerade as an hour effect.
    solver_mean = {}
    for s, v in gs.items():
        solver_mean[s] = sum(v) / len(v)
    byhour = defaultdict(list)
    for r in modern:
        m = solver_mean.get(r["solver"])
        if m is None or len(gs[r["solver"]]) < 3:
            continue
        byhour[r["ts"].hour].append((r["score"] - m) / m)
    tot_n = sum(len(v) for v in byhour.values())
    print(f"  usable rows: {tot_n}")
    print("  hourUTC   n    mean_rel_dev")
    for h in range(24):
        v = byhour.get(h, [])
        if not v:
            continue
        mm = sum(v) / len(v)
        se = (math.sqrt(sum((x - mm) ** 2 for x in v) / (len(v) - 1)) / math.sqrt(len(v))
              if len(v) > 1 else float("nan"))
        flag = ""
        if len(v) > 1 and abs(mm) > 2 * se:
            flag = "  <-- 2se"
        print(f"    {h:02d}   {len(v):4d}   {mm*100:+7.3f}%  (se {se*100:5.3f}%){flag}")

    # ------------------------------------------------------- crown EV restated
    print("\n== EV against the static crown, using the pooled modern sd ==")
    g = defaultdict(list)
    for r in modern:
        g[(r["solver"], r["ts"].date())].append(r["score"])
    sd_pooled, df, _ = pooled_within_rel_sd(g, "MODERN")
    crown = 2.61650354381456
    ours = 2.58643891  # maple HEAD executable class, n=3
    for label, sd in (("ours n=3 0.5603%", 0.005603),
                      ("crown burst n=16 0.911%", 0.00911),
                      (f"POOLED df={df} {sd_pooled*100:.4f}%", sd_pooled)):
        z = (crown - ours) / (sd * ours)
        p = 1.0 - norm_cdf(z)
        line = f"  sd={label:28s} z={z:5.3f} p/draw={p*100:6.2f}%  "
        for n in (10, 20, 30, 40):
            line += f"n{n}={100*(1-(1-p)**n):5.1f}% "
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
