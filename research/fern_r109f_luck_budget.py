#!/usr/bin/env python3
"""Where does leaderboard variance actually come from, and can firing time buy any of it?

published = normalized * draw, with
    draw = (base_decode/REF_D)**0.75 * (base_prefill/REF_P)**0.25

The baseline legs are the *unoptimised reference* timed inside the same grading
session, so across the whole receipt population they are repeated measurements of
one fixed executable.  Their spread is therefore a direct, assumption-free
measurement of harness noise, and the 0.75/0.25 score weights turn that spread
into the leaderboard's luck budget.

This script reports:
  * the luck budget split between the baseline decode and baseline prefill legs;
  * whether the draw drifts with wall-clock hour or calendar day, i.e. whether
    *when* a submission is fired changes its expected published score;
  * the draw a given normalized score needs in order to take a target crown, and
    how often the population has actually produced such a draw.
"""
import json
import math
import os
import statistics as st
import sys
import urllib.request
from collections import defaultdict

REF_D = 0.01385621216015625
REF_P = 0.00036751938916015626
BENCH = "1854efdf-feba-4773-bae9-b80520881a74"
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "artifacts", "fern-r109f", "receipts", "submissions.json")
CROWN = 2.61650354381456
HEAD_NORM = 2.566890498  # best normalized in the current Maple HEAD executable class


def load(argv):
    if len(argv) > 1 and argv[1] == "--fetch":
        tok = os.environ["MLXFAST_API_TOKEN"]
        url = f"https://api.mlx.fast/api/benchmarks/{BENCH}/submissions"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"})
        return json.load(urllib.request.urlopen(req, timeout=60))
    return json.load(open(argv[1] if len(argv) > 1 else CACHE))


def rowsof(raw):
    if isinstance(raw, dict):
        for k in ("submissions", "data", "items", "results"):
            if isinstance(raw.get(k), list):
                raw = raw[k]
                break
    return [r for r in raw if isinstance(r, dict)]


def axes(r):
    om = r.get("officialMetrics") or {}
    keys = ("decode_seconds_per_token", "prefill_seconds_per_token",
            "baseline_decode_seconds_per_token", "baseline_prefill_seconds_per_token")
    if any(not om.get(k) for k in keys):
        return None
    cd, cp, bd, bp = (om[k] for k in keys)
    return {
        "id": r.get("id", "")[:8], "user": r.get("solverUsername"),
        "created": r.get("createdAt") or "",
        "pub": r.get("officialScore") or 0.0,
        "norm": (REF_D / cd) ** 0.75 * (REF_P / cp) ** 0.25,
        "draw": (bd / REF_D) ** 0.75 * (bp / REF_P) ** 0.25,
        "bd": bd * 1e6, "bp": bp * 1e6,
    }


def main():
    rows = [a for a in (axes(r) for r in rowsof(load(sys.argv))) if a]
    rows.sort(key=lambda a: a["created"])
    n = len(rows)
    print(f"receipts with full legs: {n}")

    # --- luck budget ------------------------------------------------------
    bd = [a["bd"] for a in rows]
    bp = [a["bp"] for a in rows]
    mdec, sdec = st.fmean(bd), st.stdev(bd)
    mpre, spre = st.fmean(bp), st.stdev(bp)
    tdec = 75 * sdec / mdec
    tpre = 25 * spre / mpre
    draws = [a["draw"] for a in rows]
    print("\n[luck budget] the baseline legs are one fixed executable measured "
          f"{n} times")
    print(f"  baseline decode : mean {mdec:9.2f} us  cv {100 * sdec / mdec:.4f} %"
          f"  -> score term {tdec:.4f} %")
    print(f"  baseline prefill: mean {mpre:9.2f} us  cv {100 * spre / mpre:.4f} %"
          f"  -> score term {tpre:.4f} %")
    print(f"  quadrature {math.hypot(tdec, tpre):.4f} %  vs observed draw cv "
          f"{100 * st.stdev(draws) / st.fmean(draws):.4f} %")
    share = tpre ** 2 / (tdec ** 2 + tpre ** 2)
    print(f"  the baseline PREFILL leg carries {100 * share:.0f} % of leaderboard variance")
    print(f"  REF_D {REF_D * 1e6:.2f} us vs population mean {mdec:.2f} us "
          f"({100 * (mdec / (REF_D * 1e6) - 1):+.3f} %)")
    print(f"  REF_P {REF_P * 1e6:.2f} us vs population mean {mpre:.2f} us "
          f"({100 * (mpre / (REF_P * 1e6) - 1):+.3f} %)")

    # --- does firing time matter? ----------------------------------------
    byhour = defaultdict(list)
    byday = defaultdict(list)
    for a in rows:
        c = a["created"]
        if len(c) >= 13:
            byhour[c[11:13]].append(a["draw"])
            byday[c[:10]].append(a["draw"])
    print("\n[schedule] mean draw by UTC hour (n>=20 only)")
    grand = st.fmean(draws)
    for h in sorted(byhour):
        v = byhour[h]
        if len(v) < 20:
            continue
        m = st.fmean(v)
        se = st.stdev(v) / math.sqrt(len(v))
        z = (m - grand) / se if se else 0.0
        flag = "  <-- " + ("rich" if z > 2 else "poor") if abs(z) > 2 else ""
        print(f"  {h}:00Z n={len(v):4d} mean {m:.6f} ({100 * (m / grand - 1):+.3f} %)"
              f" se {se:.6f} z={z:+.2f}{flag}")

    print("\n[schedule] mean draw by calendar day (n>=20 only)")
    for d in sorted(byday):
        v = byday[d]
        if len(v) < 20:
            continue
        m = st.fmean(v)
        se = st.stdev(v) / math.sqrt(len(v))
        print(f"  {d} n={len(v):4d} mean {m:.6f} ({100 * (m / grand - 1):+.3f} %)"
              f" se {se:.6f} max {max(v):.6f}")

    # --- crown arithmetic -------------------------------------------------
    need = CROWN / HEAD_NORM
    hits = sum(1 for x in draws if x >= need)
    print(f"\n[crown] target published {CROWN:.11f} from normalized {HEAD_NORM:.9f}"
          f" needs draw >= {need:.6f}")
    print(f"  population draws at or above that: {hits}/{n} = {100 * hits / n:.3f} %")
    ln = [math.log(x) for x in draws]
    mu, sg = st.fmean(ln), st.stdev(ln)
    z = (math.log(need) - mu) / sg
    p = 0.5 * math.erfc(z / math.sqrt(2))
    print(f"  lognormal estimate: z={z:.3f} -> {100 * p:.3f} % per shot;"
          f" over 30 shots {100 * (1 - (1 - p) ** 30):.1f} %")
    for gain in (0.001, 0.002, 0.004, 0.0062, 0.010):
        nn = HEAD_NORM * (1 + gain)
        need2 = CROWN / nn
        z2 = (math.log(need2) - mu) / sg
        p2 = 0.5 * math.erfc(z2 / math.sqrt(2))
        print(f"  if the executable improves {100 * gain:5.2f} % -> normalized {nn:.6f},"
              f" need draw {need2:.6f}, p={100 * p2:6.3f} %/shot,"
              f" 30 shots {100 * (1 - (1 - p2) ** 30):5.1f} %")


if __name__ == "__main__":
    main()
