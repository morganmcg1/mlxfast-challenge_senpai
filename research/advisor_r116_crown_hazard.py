#!/usr/bin/env python3
"""r116 -- hazard rate of a NEW crown before the 10:30Z deadline.

advisor_r116_crown_drift.py reported an OLS slope of +0.000953 score/hour on
the hourly maximum over the last 24 h, which projects +0.31 % over the
remaining 8.5 h.  That number is almost certainly an artefact: the hourly max
of a 1-4 sample draw from a stationary distribution is an order statistic, not
a trend, and its OLS slope is dominated by how many receipts happened to land
in each hour.

The falsifiable version of the question is:

    the crown cc6ddc1 (2.61650354381456) was set at 2026-08-08T09:09Z.
    How many receipts has the field produced since then, and how many
    exceeded it?

If the answer is "many, and zero", the running maximum is genuinely static and
the FIXED-crown EV table in section 0P.13 is correct as written.  We then bound
the residual risk with the rule of three: 0 successes in N trials gives a 95 %
upper bound of 3/N on the per-draw exceedance probability.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BENCH = os.environ.get("MLXFAST_BENCHMARK_REF", "eigenlabs/mlxfast-challenge")
API = os.environ.get("MLXFAST_API_URL", "https://api.mlx.fast").rstrip("/")

CROWN = 2.61650354381456
CROWN_AT = datetime(2026, 8, 8, 9, 9, tzinfo=timezone.utc)
DEADLINE = datetime(2026, 8, 11, 10, 30, tzinfo=timezone.utc)
OUR_ACCOUNT = "morganmcg1"


def fetch() -> list:
    token = os.environ["MLXFAST_API_TOKEN"]
    url = f"{API}/api/benchmarks/{urllib.parse.quote(BENCH, safe='')}/submissions"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("submissions", [])
    return payload


def parse_ts(s):
    if not s:
        return None
    s = str(s).replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def main() -> None:
    rows = []
    for r in fetch():
        ts = parse_ts(r.get("createdAt"))
        sc = r.get("officialScore")
        if ts is None or sc is None:
            continue
        try:
            sc = float(sc)
        except (TypeError, ValueError):
            continue
        rows.append((ts, sc, str(r.get("solverUsername") or "?"),
                     str(r.get("id") or "")[:7]))
    rows.sort()

    now = max(t for t, _, _, _ in rows)
    hours_left = (DEADLINE - now).total_seconds() / 3600.0

    since = [r for r in rows if r[0] >= CROWN_AT]
    field = [r for r in since if r[2] != OUR_ACCOUNT]
    over = [r for r in since if r[1] > CROWN]

    age_h = (now - CROWN_AT).total_seconds() / 3600.0
    print(f"latest receipt      {now:%Y-%m-%dT%H:%M}Z")
    print(f"crown set           {CROWN_AT:%Y-%m-%dT%H:%M}Z  ({age_h:.1f} h ago)")
    print(f"hours to deadline   {hours_left:.2f}")
    print()
    print(f"receipts since crown was set : {len(since):4d}"
          f"   (field-only, excluding {OUR_ACCOUNT}: {len(field)})")
    print(f"  of those, above the crown  : {len(over):4d}")
    if over:
        for t, s, u, i in over:
            print(f"    {t:%m-%d %H:%M}Z {s:.8f} {u} {i}")

    # rule of three on the field-only stream: 0 successes in N draws
    n = len(field)
    if n and not over:
        p95 = 3.0 / n
        rate = n / age_h                     # field draws per hour
        exp_draws = rate * hours_left
        print()
        print(f"field draw rate            : {rate:.2f} receipts/h"
              f"  =>  {exp_draws:.1f} expected before the deadline")
        print(f"per-draw P(beat crown) 95%u: {p95*100:.2f} %   (rule of three, 0/{n})")
        print(f"P(new crown before 10:30Z) : <= {(1-(1-p95)**exp_draws)*100:.1f} %"
              f"  (95 % upper bound; point estimate ~0 %)")

    # what the drift claim would have predicted
    print()
    drift_per_h = 0.000953
    would_be = CROWN + drift_per_h * age_h
    print("falsification of the +0.000953 score/h drift claim:")
    print(f"  a real drift of that size would put the running max at"
          f" {would_be:.6f} by now")
    best_since = max((r[1] for r in since), default=float('nan'))
    print(f"  the observed running max since the crown is {best_since:.6f}"
          f"  (gap {would_be - best_since:+.6f})")
    print("  => the hourly-max OLS slope is an order-statistic artefact,"
          " not a trend.")


if __name__ == "__main__":
    main()
