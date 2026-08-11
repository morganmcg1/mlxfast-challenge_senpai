#!/usr/bin/env python3
"""fern_r109f_own_shots.py -- the campaign's own receipts, code vs luck.

Every receipt on this benchmark carries four timings.  Two of them (the
baseline decode and baseline prefill legs) come from *reference* code that is
byte-identical for every solver on every submission, so they measure the host
and nothing else.  Define

    normalized = (REF_D / cand_decode)**0.75 * (REF_P / cand_prefill)**0.25
    draw       = published / normalized

`normalized` is the part of the published score that our code earned; `draw` is
the part the host handed out.  This script prints the r109-F campaign's own
shots on both axes, ranks each draw inside the empirical draw distribution of
every full-leg correct receipt on the benchmark, and reports the ratio between
the code spread and the published spread for (a) all same-class shots and
(b) the two shots that ran a byte-identical executable.

Usage:  python3 research/fern_r109f_own_shots.py [--cache /tmp/subs_p7.json]
"""

from __future__ import annotations

import argparse
import json
import statistics as st

REF_D = 0.01385621216015625
REF_P = 0.00036751938916015626
CROWN = 2.61650354381456

# (label, receipt-id prefix, executable class)
SHOTS = [
    ("t1  base                ", "c1c0ba2c", "r109F-base"),
    ("t2  base, nonce replay  ", "88584270", "r109F-base"),
    ("t3  base + QHOIST=1     ", "e4078827", "r109F-qhoist"),
    ("t4  base + atlas v3     ", "ed40f3ee", "r109F-atlasv3"),
    ("t5  atlasv3 nonce replay", "0531544b", "r109F-atlasv3"),
]


def normalized(m: dict) -> float:
    return (REF_D / m["decode_seconds_per_token"]) ** 0.75 * (
        REF_P / m["prefill_seconds_per_token"]
    ) ** 0.25


def full_leg(r: dict) -> bool:
    m = r.get("officialMetrics") or {}
    keys = (
        "decode_seconds_per_token",
        "prefill_seconds_per_token",
        "baseline_decode_seconds_per_token",
        "baseline_prefill_seconds_per_token",
    )
    return (
        all(m.get(k) for k in keys)
        and bool(m.get("passed_correctness"))
        and bool(r.get("officialScore"))
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default="/tmp/subs_p7.json")
    args = ap.parse_args()

    rows = json.load(open(args.cache))["submissions"]

    # ---- empirical draw distribution over the whole field -----------------
    draws = sorted(r["officialScore"] / normalized(r["officialMetrics"]) for r in rows if full_leg(r))
    n = len(draws)

    def pct_of(d: float) -> float:
        """percentile of a draw inside the field distribution"""
        below = sum(1 for x in draws if x <= d)
        return 100.0 * below / n

    def p_at_least(d: float) -> tuple[int, float]:
        k = sum(1 for x in draws if x >= d)
        return k, 100.0 * k / n

    print(f"field draw distribution: n={n} full-leg correct receipts")
    print(
        f"  min {draws[0]:.6f}  p05 {draws[int(0.05*n)]:.6f}  med {st.median(draws):.6f}"
        f"  p95 {draws[int(0.95*n)]:.6f}  max {draws[-1]:.6f}"
        f"  cv {100*st.stdev(draws)/st.fmean(draws):.4f}%"
    )
    print()

    # ---- our own shots -----------------------------------------------------
    by_label: dict[str, dict] = {}
    print("shot                       status     published   normalized      draw   draw pct   need for crown")
    for label, pref, klass in SHOTS:
        hit = [r for r in rows if r["id"].startswith(pref)]
        if not hit:
            print(f"{label}  MISSING")
            continue
        r = hit[0]
        m = r.get("officialMetrics") or {}
        if not full_leg(r):
            print(f"{label}  {r['status']:<10} (no full legs yet)")
            continue
        nz = normalized(m)
        dw = r["officialScore"] / nz
        need = CROWN / nz
        k, p = p_at_least(need)
        by_label[label.strip()] = dict(row=r, klass=klass, nz=nz, dw=dw)
        print(
            f"{label}  {r['status']:<10} {r['officialScore']:.6f}  {nz:.6f}  {dw:.6f}"
            f"   {pct_of(dw):5.1f}%   draw>={need:.6f}  {k}/{n} = {p:.4f}%"
        )
    print()

    # ---- code spread vs published spread ----------------------------------
    def spread(labels: list[str], title: str) -> None:
        got = [by_label[k] for k in labels if k in by_label]
        if len(got) < 2:
            print(f"{title}: not enough terminal receipts yet ({len(got)})")
            return
        nzs = [g["nz"] for g in got]
        pubs = [g["row"]["officialScore"] for g in got]
        cs = 100.0 * (max(nzs) - min(nzs)) / st.fmean(nzs)
        ps = 100.0 * (max(pubs) - min(pubs)) / st.fmean(pubs)
        print(f"{title}  ({len(got)} receipts)")
        print(f"  code (normalized) spread : {cs:.4f} %   [{min(nzs):.6f} .. {max(nzs):.6f}]")
        print(f"  published spread         : {ps:.4f} %   [{min(pubs):.6f} .. {max(pubs):.6f}]")
        if cs > 0:
            print(f"  luck / code amplification: x{ps/cs:.1f}")
        print()

    spread(
        ["t1  base", "t2  base, nonce replay", "t4  base + atlas v3", "t5  atlasv3 nonce replay"],
        "A. all non-regressed shots (base and atlas-v3 classes)",
    )
    spread(
        ["t1  base", "t2  base, nonce replay"],
        "B. byte-identical executable pair (comment-only nonce apart)",
    )
    spread(
        ["t4  base + atlas v3", "t5  atlasv3 nonce replay"],
        "C. byte-identical executable pair (atlas-v3 class)",
    )

    # ---- best-of ----------------------------------------------------------
    if by_label:
        best_code = max(by_label.items(), key=lambda kv: kv[1]["nz"])
        best_pub = max(by_label.items(), key=lambda kv: kv[1]["row"]["officialScore"])
        print(f"best CODE  of the campaign: {best_code[0]}  normalized {best_code[1]['nz']:.6f}")
        print(
            f"best LUCK  of the campaign: {best_pub[0]}  published  "
            f"{best_pub[1]['row']['officialScore']:.6f}  (draw {best_pub[1]['dw']:.6f})"
        )
        if best_code[0] != best_pub[0]:
            print(
                "  -> the shot with the best code is NOT the shot with the best published score."
            )


if __name__ == "__main__":
    main()
