#!/usr/bin/env python3
"""Diagnose the r109-f-rev2 figure 2.610307795.

The advisor's revision 2 states that the leader's 19 receipts "normalize to a
mean of 2.610307795", and derives P(win) ~= 26% per shot from it.  No receipt
in the population has a normalized score anywhere near that.  This script
tests the alternative reading: that 2.610307795 is crown / mean_draw, i.e. the
BREAK-EVEN normalized level at which the crown becomes the median outcome --
a target, not an observation.
"""
import json
import statistics as st

CACHE = "research/artifacts/fern-r109f/receipts/submissions.json"
REF_D = 0.01385621216015625
REF_P = 0.00036751938916015626
CROWN = 2.61650354381456
CLAIM = 2.610307795

rows = json.load(open(CACHE))
if isinstance(rows, dict):
    rows = rows.get("submissions", rows.get("items", []))

recs = []
for r in rows:
    m = r.get("officialMetrics") or {}
    if not m.get("decode_seconds_per_token"):
        continue
    cd, cp = m["decode_seconds_per_token"], m["prefill_seconds_per_token"]
    bd, bp = (
        m["baseline_decode_seconds_per_token"],
        m["baseline_prefill_seconds_per_token"],
    )
    norm = (REF_D / cd) ** 0.75 * (REF_P / cp) ** 0.25
    pub = (bd / cd) ** 0.75 * (bp / cp) ** 0.25
    recs.append(
        dict(
            who=r.get("solverUsername"),
            ts=r.get("createdAt", ""),
            rcpt=str(r["id"])[:7],
            norm=norm,
            pub=pub,
            draw=pub / norm,
        )
    )

print(f"population with both legs: n={len(recs)}")
print(f"max normalized ever observed: {max(d['norm'] for d in recs):.9f}")
best = max(recs, key=lambda d: d["norm"])
print(f"  held by {best['rcpt']} ({best['who']}) published {best['pub']:.9f}")
print(f"max published ever observed:  {max(d['pub'] for d in recs):.9f}")
print(f"claim under test: {CLAIM:.9f}")
n_above = sum(1 for d in recs if d["norm"] >= CLAIM)
print(f"receipts with normalized >= claim: {n_above}")

print("\n-- is the claim crown / mean_draw for some cohort? --")
cohorts = {
    "whole population": recs,
    "2026-08-10 only": [d for d in recs if d["ts"].startswith("2026-08-10")],
    "maple-fern 08-10": [
        d
        for d in recs
        if d["who"] == "morganmcg1" and d["ts"].startswith("2026-08-10")
    ],
}
by_solver = {}
for d in recs:
    by_solver.setdefault(d["who"], []).append(d)
for who, ds in sorted(by_solver.items(), key=lambda kv: -len(kv[1]))[:4]:
    cohorts[f"solver {who} (n={len(ds)})"] = ds
    ds20 = sorted(ds, key=lambda d: d["ts"])[-19:]
    cohorts[f"solver {who} last 19"] = ds20

print(f"{'cohort':34}{'n':>4}{'mean_draw':>12}{'crown/draw':>14}{'rel err vs claim':>18}")
for label, ds in cohorts.items():
    if len(ds) < 2:
        continue
    md = st.mean(d["draw"] for d in ds)
    implied = CROWN / md
    print(
        f"{label:34}{len(ds):4d}{md:12.6f}{implied:14.9f}"
        f"{(implied/CLAIM-1)*1e6:15.1f} ppm"
    )
