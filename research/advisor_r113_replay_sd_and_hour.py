#!/usr/bin/env python3
"""R113b -- clean per-draw replication sd, and a fair test of the hour-of-day effect.

Why this exists
---------------
`advisor_r113_noise_structure.py` showed the naive pooled within-(solver x day)
sd is 3.97%.  That number is USELESS: it is dominated by solvers submitting
*different code* on the same day (morganmcg1's own modern-window rel_sd is
5.96% with a 1.64 minimum -- obviously not replication noise).

The quantity we need is the sd of repeated draws of ONE unchanged executable.
The only honest proxies on the public board are solvers whose recent activity
is a replay burst.  Four qualify in the modern window, and their means agree to
four decimal places, which is itself strong evidence they are all drawing the
same converged base tree:

    a-github-name  n=39  mean 2.57783
    MyatKaung      n=10  mean 2.57789
    fyrsta7        n= 7  mean 2.57870
    newjordan      n= 4  mean 2.57792

Each solver's own sd is an UPPER bound on replication noise (any code they did
change inflates it).  Pooling gives many more df than either estimate the
campaign has used so far (our n=3 -> 2 df; the crown burst -> 15 df).

The hour test is run WITHIN a single solver (a-github-name, n=39, essentially
one tree) so that neither solver skill nor code drift can manufacture a signal.
"""

from __future__ import annotations

import math
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
CROWN = 2.61650354381456
OURS_MEAN = 2.58643891   # maple HEAD executable class
OURS_N = 3


def rows():
    out = subprocess.run(["mlxfast", "submissions", "--all"],
                         capture_output=True, text=True, check=True).stdout
    for raw in out.splitlines():
        line = ANSI_RE.sub("", raw).rstrip()
        if not line or line.startswith(("eigenlabs", "submission", "\u2500")):
            continue
        p = re.split(r"\s{2,}", line.strip())
        if len(p) < 4:
            continue
        try:
            score = float(p[3])
            ts = datetime.strptime(p[-1], "%m/%d/%y, %I:%M %p")
        except ValueError:
            continue
        yield dict(sub=p[0], solver=p[1], status=p[2].strip().lower(),
                   score=score, ts=ts)


def norm_cdf(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def main():
    all_rows = [r for r in rows() if r["status"] in ("promoted", "rejected")]
    cutoff = datetime(2026, 8, 7)
    modern = [r for r in all_rows if r["ts"] >= cutoff]

    REPLAYERS = ["a-github-name", "MyatKaung", "fyrsta7", "newjordan"]
    print("== pooled replication sd from replay-like solvers (modern window) ==")
    ss = 0.0
    df = 0
    for s in REPLAYERS:
        v = [r["score"] for r in modern if r["solver"] == s]
        if len(v) < 3:
            print(f"  {s:16s} SKIP n={len(v)}")
            continue
        m = sum(v) / len(v)
        sd = math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))
        ss += sum(((x - m) / m) ** 2 for x in v)
        df += len(v) - 1
        print(f"  {s:16s} n={len(v):3d} mean={m:.5f} rel_sd={sd/m*100:6.3f}% df={len(v)-1}")
    pooled = math.sqrt(ss / df)
    print(f"  POOLED           rel_sd={pooled*100:.4f}%  df={df}")

    print("\n== EV against the STATIC crown, done properly ==")
    print("   (predictive sd for a new draw = sigma*sqrt(1 + 1/n_ours), since our")
    print("    class mean is itself estimated from only n=3)")
    for label, sigma, n in (
        ("point (sigma known, mean known)", pooled, None),
        ("predictive, our n=3", pooled, OURS_N),
    ):
        s = sigma * (math.sqrt(1 + 1.0 / n) if n else 1.0)
        z = (CROWN - OURS_MEAN) / (s * OURS_MEAN)
        p = 1 - norm_cdf(z)
        line = f"  {label:34s} sd={s*100:5.3f}% z={z:5.3f} p/draw={p*100:5.2f}%  "
        for k in (10, 20, 30, 40):
            line += f"n{k}={100*(1-(1-p)**k):5.1f}% "
        print(line)

    print("\n== what a locally-verified code win is worth (predictive sd) ==")
    s = pooled * math.sqrt(1 + 1.0 / OURS_N)
    print("   gain   new mean    p/draw    P@10    P@20    P@30")
    for g in (0.0, 0.0025, 0.005, 0.0075, 0.010):
        mu = OURS_MEAN * (1 + g)
        z = (CROWN - mu) / (s * mu)
        p = 1 - norm_cdf(z)
        print(f"  {g*100:+5.2f}%  {mu:.5f}   {p*100:6.2f}%  " +
              "  ".join(f"{100*(1-(1-p)**k):5.1f}%" for k in (10, 20, 30)))

    print("\n== hour-of-day, tested WITHIN a-github-name only (n=39, one tree) ==")
    v = [r for r in modern if r["solver"] == "a-github-name"]
    m = sum(r["score"] for r in v) / len(v)
    byh = defaultdict(list)
    for r in v:
        byh[r["ts"].hour].append(r["score"])
    print("  hourUTC  n   mean      rel_dev")
    for h in sorted(byh):
        vv = byh[h]
        mm = sum(vv) / len(vv)
        print(f"    {h:02d}   {len(vv):3d}  {mm:.5f}  {(mm-m)/m*100:+7.3f}%")
    # One-way ANOVA F test across hours with >=2 obs.
    grps = [vv for vv in byh.values() if len(vv) >= 2]
    if len(grps) >= 2:
        nt = sum(len(g) for g in grps)
        gm = sum(sum(g) for g in grps) / nt
        ssb = sum(len(g) * (sum(g) / len(g) - gm) ** 2 for g in grps)
        ssw = sum(sum((x - sum(g) / len(g)) ** 2 for x in g) for g in grps)
        dfb, dfw = len(grps) - 1, nt - len(grps)
        if dfw > 0 and ssw > 0:
            F = (ssb / dfb) / (ssw / dfw)
            print(f"  one-way ANOVA over {len(grps)} hour-bins: "
                  f"F({dfb},{dfw}) = {F:.3f}   "
                  f"(F<~2 => no detectable hour effect)")
            print(f"  between-hour sd = {math.sqrt(max(ssb/dfb,0))/gm*100:.3f}% "
                  f"vs within-hour sd = {math.sqrt(ssw/dfw)/gm*100:.3f}%")

    print("\n== our own draws, for the record ==")
    for r in sorted([r for r in modern if r["solver"] == "morganmcg1"],
                    key=lambda r: r["ts"])[-8:]:
        print(f"  {r['sub']}  {r['ts']}  {r['score']:.8f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
