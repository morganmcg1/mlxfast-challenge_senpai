#!/usr/bin/env python3
"""Resolve the fixed-executable published-score sd from the draw/normalized split.

The advisor's r111 §0P.8 estimates the fixed-executable published sd from three
same-executable pairs (3 df) and lands on the interval [0.4 %, 0.9 %], noting
that the interval is too wide to act on.  That interval can be narrowed by an
order of magnitude without any attribution work at all, because the published
score factorises exactly:

    published = normalized x draw

    normalized = (REF_dec / cand_dec)^0.75 * (REF_pre / cand_pre)^0.25
    draw       = (base_dec / REF_dec)^0.75 * (base_pre / REF_pre)^0.25

`normalized` is a function of the *candidate* legs only -> it carries the
executable's quality plus candidate measurement noise.
`draw` is a function of the *baseline* legs only -> it is pure harness/session
noise and is **independent of which campaign's executable was submitted**.

Therefore every receipt on the account, ours or cedar's, is a legitimate draw
sample.  That turns a 3-df problem into an n-1-df problem, and it brackets the
fixed-executable published sd as

    sd(draw)  <=  sd_fixed_exec  <=  sqrt( var(draw) + var(normalized) )

with the upper bound conservative because var(normalized) over a mixed set of
executables also contains genuine between-executable spread.

Usage:
    python3 research/fern_r109f_sd_decomposition.py [--date 2026-08-10]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics as st
import urllib.request

BENCHMARK = "1854efdf-feba-4773-bae9-b80520881a74"
API = f"https://api.mlx.fast/api/benchmarks/{BENCHMARK}/submissions"
REF_DECODE = 0.01385621216015625
REF_PREFILL = 0.00036751938916015626
CROWN = 2.61650354381456
W_DEC, W_PRE = 0.75, 0.25


def fetch(token: str) -> list[dict]:
    req = urllib.request.Request(API, headers={"Authorization": f"Bearer {token}"})
    payload = json.load(urllib.request.urlopen(req, timeout=40))
    rows = payload["submissions"] if isinstance(payload, dict) else payload
    return rows


def axes(row: dict):
    om = row.get("officialMetrics") or {}
    need = (
        "decode_seconds_per_token",
        "prefill_seconds_per_token",
        "baseline_decode_seconds_per_token",
        "baseline_prefill_seconds_per_token",
    )
    if any(om.get(k) in (None, 0) for k in need):
        return None
    cd = om["decode_seconds_per_token"]
    cp = om["prefill_seconds_per_token"]
    bd = om["baseline_decode_seconds_per_token"]
    bp = om["baseline_prefill_seconds_per_token"]
    normalized = (REF_DECODE / cd) ** W_DEC * (REF_PREFILL / cp) ** W_PRE
    draw = (bd / REF_DECODE) ** W_DEC * (bp / REF_PREFILL) ** W_PRE
    published = row.get("officialScore")
    if published is None:
        published = (bd / cd) ** W_DEC * (bp / cp) ** W_PRE
    return {
        "id": row["id"],
        "short": row["id"][:7],
        "created": row.get("createdAt", ""),
        "commit": om.get("commit"),
        "published": published,
        "normalized": normalized,
        "draw": draw,
        "cand_dec_us": cd * 1e6,
        "cand_pre_us": cp * 1e6,
        "base_dec_us": bd * 1e6,
        "base_pre_us": bp * 1e6,
        "note": row.get("note") or "",
    }


def cv(xs: list[float]) -> float:
    return 100.0 * st.stdev(xs) / st.fmean(xs)


def normal_sf(z: float) -> float:
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="2026-08-10")
    ap.add_argument("--user", default="morganmcg1")
    args = ap.parse_args()

    token = os.environ["MLXFAST_API_TOKEN"]
    rows = [r for r in fetch(token) if r.get("solverUsername") == args.user]
    recs = [a for a in (axes(r) for r in rows) if a]
    recs.sort(key=lambda a: a["created"])
    day = [a for a in recs if a["created"].startswith(args.date)]

    print(f"# receipts with full legs: all-time n={len(recs)}, {args.date} n={len(day)}")
    print()
    max_err = max(abs(a["normalized"] * a["draw"] / a["published"] - 1.0) for a in recs)
    print(f"identity published == normalized x draw : max rel err {max_err:.3e} over n={len(recs)}")
    print()

    for label, pool in (("all-time", recs), (args.date, day)):
        if len(pool) < 3:
            continue
        dr = [a["draw"] for a in pool]
        no = [a["normalized"] for a in pool]
        pu = [a["published"] for a in pool]
        sd_draw = cv(dr)
        sd_norm = cv(no)
        sd_pub = cv(pu)
        lo = sd_draw
        hi = math.sqrt(sd_draw**2 + sd_norm**2)
        print(f"## pool {label}  (n={len(pool)}, df={len(pool)-1})")
        print(f"  draw       mean {st.fmean(dr):.9f}  cv {sd_draw:.4f} %")
        print(f"  normalized mean {st.fmean(no):.9f}  cv {sd_norm:.4f} %")
        print(f"  published  mean {st.fmean(pu):.9f}  cv {sd_pub:.4f} %")
        print(f"  draw share of published variance: {100*sd_draw**2/sd_pub**2:.1f} %")
        print(f"  => fixed-executable published sd in [{lo:.4f} %, {hi:.4f} %]")
        print()

    # HEAD-class receipts named by the advisor's r111 section 0P.8.
    head_prefixes = ("c1c0ba2", "2771067")
    head = [a for a in recs if a["short"].startswith(head_prefixes)]
    print("## maple HEAD executable class (advisor r111 0P.8)")
    for a in head:
        print(
            f"  {a['short']}  {a['created']}  published {a['published']:.11f}"
            f"  normalized {a['normalized']:.9f}  draw {a['draw']:.6f}"
            f"  cand_dec {a['cand_dec_us']:.1f} us  cand_pre {a['cand_pre_us']:.2f} us"
        )
    if head:
        hp = [a["published"] for a in head]
        hn = [a["normalized"] for a in head]
        print(f"  class published mean {st.fmean(hp):.9f}")
        print(f"  class normalized mean {st.fmean(hn):.9f}")
        print()

        dr = [a["draw"] for a in day] or [a["draw"] for a in recs]
        sd_draw = cv(dr)
        sd_norm = cv([a["normalized"] for a in day] or [a["normalized"] for a in recs])
        mean_pub = st.fmean(hp)
        deficit = 100.0 * (CROWN / mean_pub - 1.0)
        print(f"  crown {CROWN}  deficit of class mean {deficit:.3f} %")
        for tag, sd in (
            ("lower bound sd(draw)", sd_draw),
            ("upper bound sqrt(var draw + var norm)", math.sqrt(sd_draw**2 + sd_norm**2)),
        ):
            z = deficit / sd
            p = normal_sf(z)
            print(f"    {tag:<40s} sd {sd:.4f} %  z {z:.3f}  P/shot {100*p:.3f} %"
                  f"  P over 30 shots {100*(1-(1-p)**30):.1f} %")
        print()

        # Empirical (non-parametric) version: best HEAD-class normalized times
        # every observed draw on the account.
        best_norm = max(hn)
        emp = sum(1 for a in recs if best_norm * a["draw"] >= CROWN)
        print(f"  non-parametric: best class normalized {best_norm:.9f} x each of "
              f"{len(recs)} observed draws clears the crown {emp} times "
              f"({100*emp/len(recs):.3f} %)")
        need_draw = CROWN / best_norm
        print(f"  draw needed with the best class executable: {need_draw:.6f} "
              f"(max observed draw {max(a['draw'] for a in recs):.6f})")
        need_norm = CROWN / st.fmean([a["draw"] for a in recs])
        print(f"  normalized needed at the mean draw: {need_norm:.9f} "
              f"= +{100*(need_norm/best_norm-1):.3f} % over the class best")


if __name__ == "__main__":
    main()
