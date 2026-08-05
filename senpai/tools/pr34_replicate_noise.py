#!/usr/bin/env python3
"""Re-price the ranked receipt noise floor from our own account's replicates.

The 1.93% / 0.34% figures published earlier are the spread of the *pinned
baseline* pass across every account and tree. What a marginal-difference
measurement actually needs is the run-to-run spread of the *candidate* axes for
trees whose scored behaviour is unchanged. Those are different numbers, and if
the baseline pass is noisier than the candidate pass, normalising a receipt by
the baseline ratio injects noise instead of removing it.

Usage: pr34_replicate_noise.py /tmp/subs.json [account]
"""

from __future__ import annotations

import json
import statistics as st
import sys


def axes(m: dict) -> tuple[float, float]:
    s = 512_000.0 * m["prefill_seconds_per_token"]
    return s, 1000.0 * m["decode_seconds_per_token"] - s / 128.0


def rel_sd(xs: list[float]) -> tuple[float, float, float]:
    mu = st.fmean(xs)
    sd = st.stdev(xs)
    return mu, sd, 100.0 * sd / mu


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/subs.json"
    account = sys.argv[2] if len(sys.argv) > 2 else "morganmcg1"
    subs = json.load(open(path))["submissions"]
    mine = [
        s
        for s in subs
        if s.get("solverUsername") == account and (s.get("officialMetrics") or {}).get(
            "prefill_seconds_per_token"
        )
    ]
    mine.sort(key=lambda s: s["createdAt"])

    rows = []
    for s in mine:
        m = s["officialMetrics"]
        S, T = axes(m)
        rows.append(
            dict(
                created=s["createdAt"][:19],
                S=S,
                T=T,
                bS=512_000.0 * m["baseline_prefill_seconds_per_token"],
                bT=1000.0 * m["baseline_decode_seconds_per_token"],
                note=(s.get("note") or "")[:0],
            )
        )

    # Instrumented receipts are excluded from the unchanged-tree cluster by
    # their distance from the median, not by their note text.
    medS = st.median(r["S"] for r in rows)
    clean = [r for r in rows if abs(r["S"] / medS - 1.0) < 0.03]
    dirty = [r for r in rows if r not in clean]

    print(f"{account}: {len(rows)} timed receipts, {len(clean)} within 3% of median S")
    for r in rows:
        tag = "clean" if r in clean else "INSTR"
        print(
            f"  {r['created']}  {tag}  S={r['S']:8.3f}  T={r['T']:7.4f}  "
            f"baselineS={r['bS']:8.3f}  baselineT={r['bT']:8.4f}"
        )

    print("\nunchanged-tree candidate axes (this is the noise floor that matters)")
    for key, label in (("S", "S  (prefill, ms)"), ("T", "T  (decode step, ms)")):
        mu, sd, rsd = rel_sd([r[key] for r in clean])
        print(
            f"  {label:22s} mean {mu:9.4f}  sd {sd:8.4f}  rel sd {rsd:6.3f}%  "
            f"sem {sd/len(clean)**0.5:8.4f}"
        )

    print("\nsame receipts' pinned-baseline pass")
    for key, label in (("bS", "baseline S (ms)"), ("bT", "baseline T (ms)")):
        mu, sd, rsd = rel_sd([r[key] for r in clean])
        print(f"  {label:22s} mean {mu:9.4f}  sd {sd:8.4f}  rel sd {rsd:6.3f}%")

    print("\ncorrelation candidate vs baseline within the clean cluster")
    for a, b in (("S", "bS"), ("T", "bT")):
        xs = [r[a] for r in clean]
        ys = [r[b] for r in clean]
        print(f"  {a} vs {b}: r = {st.correlation(xs, ys):+.3f}")
    print(
        "  a near-zero r means the baseline pass drifts independently of the\n"
        "  candidate pass, so dividing by it can only add variance."
    )

    if dirty:
        print("\nreceipts outside the cluster (instrumented / different tree)")
        for r in dirty:
            print(f"  {r['created']}  S={r['S']:8.3f}  T={r['T']:7.4f}")


if __name__ == "__main__":
    main()
