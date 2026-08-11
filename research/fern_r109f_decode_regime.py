#!/usr/bin/env python3
"""fern R109-F: is the 41.9 us/token decode gap between our receipts and the
"fast cluster" a code regression, or a ranked-host / runner regime change?

Setup.  Four receipt packages we can read locally split into two tight clusters:

    cluster   package        cand decode us   normalized
    fast      pkg-e27f1ce         4890.7        2.582263
    fast      pkg-25e1f18         4894.1        2.582070
    slow      pkg-t1              4932.4        2.566838
    slow      pkg-t2              4932.6        2.566890

Within-cluster spread is 0.005-0.07%; between-cluster gap is 0.86%.  But the two
fast packages are structurally *unrelated* (one is fork main + a 30-line kernel
tweak, the other a 3000-line refactor), and no single feature we can grep for
separates fast from slow.  That pattern is equally consistent with two discrete
regimes of the measuring host.

Discriminator.  A code regression is solver-specific and content-specific.  A
runner regime change is universal: it moves *every* solver's candidate decode at
the same wall-clock moment, including solvers whose code did not change.  So:

  * bucket every receipt with full legs by day (and hour),
  * report the population mean and, more robustly, the *minimum* (frontier)
    candidate decode per bucket,
  * do the same for the reported baseline decode leg, which is re-measured by
    the runner on every submission and is by construction code-independent.

If the frontier candidate decode steps on a date and the baseline leg steps with
it, the host changed.  If the candidate steps while the baseline is flat, the
population's *code* got worse -- which for a shared fork means a regression
landed on main.

Usage:
    python3 research/fern_r109f_decode_regime.py [path/to/submissions.json]
"""

from __future__ import annotations

import collections
import json
import os
import statistics
import sys
import urllib.request

BENCH = "1854efdf-feba-4773-bae9-b80520881a74"
API = f"https://api.mlx.fast/api/benchmarks/{BENCH}/submissions"


def load(path: str | None) -> list[dict]:
    if path and os.path.exists(path):
        raw = json.load(open(path))
    else:
        req = urllib.request.Request(
            API,
            headers={"Authorization": f"Bearer {os.environ['MLXFAST_API_TOKEN']}"},
        )
        with urllib.request.urlopen(req, timeout=120) as fh:
            raw = json.load(fh)
    rows = raw["submissions"] if isinstance(raw, dict) else raw
    return rows


def main() -> int:
    rows = load(sys.argv[1] if len(sys.argv) > 1 else None)

    recs = []
    for r in rows:
        m = r.get("officialMetrics") or {}
        d = m.get("decode_seconds_per_token")
        bd = m.get("baseline_decode_seconds_per_token")
        bp = m.get("baseline_prefill_seconds_per_token")
        p = m.get("prefill_seconds_per_token")
        ts = r.get("createdAt") or ""
        if not (d and bd and ts):
            continue
        recs.append(
            {
                "day": ts[:10],
                "hour": ts[11:13],
                "ts": ts,
                "d": d * 1e6,
                "p": (p or 0) * 1e6,
                "bd": bd * 1e6,
                "bp": (bp or 0) * 1e6,
                "solver": r.get("solverUsername") or "?",
                "id": r.get("id"),
            }
        )
    recs.sort(key=lambda x: x["ts"])
    print(f"receipts with full legs: {len(recs)}")
    print()

    by_day: dict[str, list[dict]] = collections.defaultdict(list)
    for r in recs:
        by_day[r["day"]].append(r)

    hdr = (
        "%-11s %5s | %9s %9s %9s | %9s %9s | %9s"
        % ("day", "n", "cand_min", "cand_p10", "cand_med", "base_med", "base_min",
           "solvers")
    )
    print("CANDIDATE decode (us/token) vs the runner's own BASELINE decode leg")
    print(hdr)
    print("-" * len(hdr))
    for day in sorted(by_day):
        g = by_day[day]
        ds = sorted(x["d"] for x in g)
        bds = sorted(x["bd"] for x in g)
        p10 = ds[max(0, int(0.10 * (len(ds) - 1)))]
        print(
            "%-11s %5d | %9.1f %9.1f %9.1f | %9.1f %9.1f | %9d"
            % (
                day,
                len(g),
                ds[0],
                p10,
                statistics.median(ds),
                statistics.median(bds),
                bds[0],
                len({x["solver"] for x in g}),
            )
        )
    print()

    # Frontier walk: the best decode ever seen up to each day, and the best
    # decode seen *on* each day.  A host regime change moves the daily best even
    # for days where nobody improved their code.
    print("Interpretation guide:")
    print("  cand_min flat across days  -> frontier code unchanged")
    print("  cand_min steps up on a day -> either everyone regressed (a bad")
    print("     merge on the shared fork) or the host got slower that day")
    print("  base_med / base_min step with it -> host, not code, because the")
    print("     baseline leg is re-measured from unchanged reference code")
    print()

    # Correlate: per-day, is (cand_min / base_min) stable?  That ratio divides
    # out any uniform host speed factor.
    print("Host-normalised frontier: cand_min / base_med (dimensionless)")
    hdr2 = "%-11s %5s %9s %9s %10s" % ("day", "n", "cand_min", "base_med", "ratio")
    print(hdr2)
    print("-" * len(hdr2))
    ratios = []
    for day in sorted(by_day):
        g = by_day[day]
        cmin = min(x["d"] for x in g)
        bmed = statistics.median(x["bd"] for x in g)
        ratios.append((day, cmin / bmed))
        print(
            "%-11s %5d %9.1f %9.1f %10.5f"
            % (day, len(g), cmin, bmed, cmin / bmed)
        )
    print()
    if len(ratios) >= 2:
        vals = [v for _, v in ratios]
        print(
            "ratio spread: min %.5f  max %.5f  (%.2f%% range)"
            % (min(vals), max(vals), 100.0 * (max(vals) / min(vals) - 1.0))
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
