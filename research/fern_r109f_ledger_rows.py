#!/usr/bin/env python3
"""Print extended ledger rows (both legs, normalized, draw) for maple-fern receipts.

Reads the cached official-submissions snapshot written by
research/fern_r109f_receipt_axes.py fetch.

Usage:
  python3 research/fern_r109f_ledger_rows.py [--day 2026-08-10]
"""
import argparse
import json
import statistics as st

CACHE = "research/artifacts/fern-r109f/receipts/submissions.json"
REF_D = 0.01385621216015625
REF_P = 0.00036751938916015626


def load(path):
    rows = json.load(open(path))
    if isinstance(rows, dict):
        rows = rows.get("submissions", rows.get("items", []))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default="2026-08-10")
    ap.add_argument("--cache", default=CACHE)
    a = ap.parse_args()

    mine = []
    for r in load(a.cache):
        if r.get("solverUsername") != "morganmcg1":
            continue
        m = r.get("officialMetrics") or {}
        if not m.get("decode_seconds_per_token"):
            continue
        ts = r.get("createdAt", "")
        if a.day and not ts.startswith(a.day):
            continue
        cd = m["decode_seconds_per_token"]
        cp = m["prefill_seconds_per_token"]
        bd = m["baseline_decode_seconds_per_token"]
        bp = m["baseline_prefill_seconds_per_token"]
        norm = (REF_D / cd) ** 0.75 * (REF_P / cp) ** 0.25
        pub = (bd / cd) ** 0.75 * (bp / cp) ** 0.25
        mine.append(
            dict(
                ts=ts[:19],
                rcpt=str(r["id"])[:7],
                commit=m["commit"][:7],
                pub=pub,
                norm=norm,
                draw=pub / norm,
                cd=cd,
                cp=cp,
                bd=bd,
                bp=bp,
                dspd=m["decode_speedup"],
                pspd=m["prefill_speedup"],
                dfloor=m["passed_decode_speedup_floor"],
                pfloor=m["passed_prefill_speedup_floor"],
                corr=m["passed_correctness"],
                status=r.get("status"),
            )
        )
    mine.sort(key=lambda d: d["ts"])

    hdr = (
        f"{'utc':20}{'rcpt':9}{'commit':9}{'published':>14}{'normlzd':>13}"
        f"{'draw':>9}{'candD_us':>10}{'candP_us':>10}{'baseD_us':>10}{'baseP_us':>10}"
    )
    print(hdr)
    print("-" * len(hdr))
    for d in mine:
        print(
            f"{d['ts']:20}{d['rcpt']:9}{d['commit']:9}{d['pub']:14.9f}{d['norm']:13.9f}"
            f"{d['draw']:9.5f}{d['cd']*1e6:10.1f}{d['cp']*1e6:10.2f}"
            f"{d['bd']*1e6:10.1f}{d['bp']*1e6:10.2f}"
        )

    if len(mine) < 2:
        return
    for key, lbl, scale, fmt in (
        ("cd", "cand decode", 1e6, ".1f"),
        ("cp", "cand prefill", 1e6, ".2f"),
        ("bd", "base decode", 1e6, ".1f"),
        ("bp", "base prefill", 1e6, ".2f"),
        ("norm", "normalized", 1.0, ".9f"),
        ("pub", "published", 1.0, ".9f"),
    ):
        v = [d[key] * scale for d in mine]
        m = st.mean(v)
        cv = st.stdev(v) / m * 100
        print(
            f"n={len(v):2d}  {lbl:13s} mean {format(m, fmt):>14s}  "
            f"cv {cv:7.4f}%  min {format(min(v), fmt):>14s}  max {format(max(v), fmt):>14s}"
        )


if __name__ == "__main__":
    main()
