#!/usr/bin/env python3
"""r116 -- is the crown a fixed target or a moving one?

Every EV table in this campaign (section 0P.13) computed

    P(crown) = E_mu[ 1 - Phi((crown - mu)/sigma)^n ]

with ``crown`` held FIXED at 2.61650354381456.  But ~75 solvers are drawing
against the same lottery we are.  If the field's running maximum rises over the
remaining hours, the fixed-crown figure overstates our chances, and the
optimal split between "more draws" and "more code" shifts toward code.

This script measures the drift directly from the receipt feed: the running
maximum official score, bucketed by hour, over the last few days.
"""
from __future__ import annotations

import json
import os
import statistics as st
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

BENCH = os.environ.get("MLXFAST_BENCHMARK_REF", "eigenlabs/mlxfast-challenge")
API = os.environ.get("MLXFAST_API_URL", "https://api.mlx.fast").rstrip("/")


def fetch() -> list:
    token = os.environ["MLXFAST_API_TOKEN"]
    url = f"{API}/api/benchmarks/{urllib.parse.quote(BENCH, safe='')}/submissions"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("submissions", [])
    return payload


def parse_ts(s: str):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def main() -> int:
    rows = fetch()
    recs = []
    for r in rows:
        ts = parse_ts(r.get("createdAt"))
        sc = r.get("officialScore")
        if ts is None or sc is None:
            continue
        try:
            sc = float(sc)
        except (TypeError, ValueError):
            continue
        recs.append((ts, sc, r.get("solverUsername"), str(r.get("id", ""))[:7]))
    recs.sort(key=lambda t: t[0])
    print(f"scored receipts: {len(recs)}")
    if not recs:
        return 1

    now = recs[-1][0]
    print(f"latest receipt at {now.isoformat()}")

    # (A) running max over the whole record, reported at each new high.
    print("\n== new all-time highs ==")
    best = -1e9
    highs = []
    for ts, sc, who, rid in recs:
        if sc > best:
            best = sc
            highs.append((ts, sc, who, rid))
    for ts, sc, who, rid in highs[-14:]:
        print(f"  {ts.strftime('%m-%d %H:%MZ')}  {sc:.8f}  {who:<16} {rid}")

    # (B) hourly max over the last 24 h -- is the FRONTIER rising, or is the
    #     all-time high just an old lucky draw nobody has beaten?
    print("\n== hourly max / count over the last 24 h ==")
    cutoff = now - timedelta(hours=24)
    buckets = {}
    for ts, sc, who, rid in recs:
        if ts < cutoff:
            continue
        key = ts.replace(minute=0, second=0, microsecond=0)
        buckets.setdefault(key, []).append((sc, who))
    hourly_max = []
    for key in sorted(buckets):
        vals = [v[0] for v in buckets[key]]
        top = max(buckets[key])
        hourly_max.append((key, top[0]))
        print(f"  {key.strftime('%m-%d %HZ')}  n={len(vals):3d}  "
              f"max={top[0]:.6f} ({top[1]:<16}) med={st.median(vals):.6f}")

    # (C) drift: OLS slope of hourly max on hour index.
    if len(hourly_max) >= 4:
        xs = list(range(len(hourly_max)))
        ys = [v for _, v in hourly_max]
        mx, my = st.mean(xs), st.mean(ys)
        num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        den = sum((x - mx) ** 2 for x in xs)
        slope = num / den if den else 0.0
        print(f"\nhourly-max OLS slope: {slope:+.6f} score/hour "
              f"({100*slope/my:+.4f} %/hour of the mean)")
        print(f"projected drift over 8.5 h: {8.5*slope:+.6f} "
              f"({100*8.5*slope/my:+.4f} %)")

    # (D) how many DISTINCT solvers have ever cleared our HEAD-class mean?
    head_mean = 2.58989575
    crown = 2.61650354381456
    over_head = sorted({w for _, sc, w, _ in recs if sc > head_mean and w})
    over_crown = sorted({w for _, sc, w, _ in recs if sc > crown and w})
    print(f"\nsolvers ever above HEAD-class mean {head_mean}: {len(over_head)}")
    print(f"  {', '.join(over_head)}")
    print(f"solvers ever above crown {crown}: {len(over_crown)}")
    print(f"  {', '.join(over_crown)}")

    # (E) in the last 6 h, how many receipts cleared the crown?
    for hrs in (6, 12, 24):
        c = now - timedelta(hours=hrs)
        recent = [r for r in recs if r[0] >= c]
        above = [r for r in recent if r[1] > crown]
        print(f"last {hrs:2d} h: {len(recent):4d} receipts, "
              f"{len(above)} above crown, max={max((r[1] for r in recent), default=0):.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
