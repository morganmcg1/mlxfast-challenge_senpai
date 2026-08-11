#!/usr/bin/env python3
"""fern r109-f: separate executable quality from the same-session baseline draw,
then price the probability that a given executable beats the standing bar.

The published identity is exact on every row that carries officialMetrics:

    published = (baseline_decode/decode)^0.75 * (baseline_prefill/prefill)^0.25
              = normalized * draw
    normalized = (REF_decode/decode)^0.75  * (REF_prefill/prefill)^0.25
    draw       = (baseline_decode/REF_decode)^0.75
               * (baseline_prefill/REF_prefill)^0.25

`normalized` is the only part an engineering change can move; `draw` is the
same-session baseline lottery, identical in distribution for every solver.

Usage: research/fern_r109f_draw_winprob.py <submissions.json>
"""
from __future__ import annotations

import json
import statistics as st
import sys

REF_D = 0.01385621216015625
REF_P = 0.00036751938916015626


def decompose(m):
    d = m.get("decode_seconds_per_token")
    p = m.get("prefill_seconds_per_token")
    bd = m.get("baseline_decode_seconds_per_token")
    bp = m.get("baseline_prefill_seconds_per_token")
    if not (d and p and bd and bp):
        return None
    norm = (REF_D / d) ** 0.75 * (REF_P / p) ** 0.25
    draw = (bd / REF_D) ** 0.75 * (bp / REF_P) ** 0.25
    return norm, draw


def pct(xs, q):
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def main() -> int:
    rows = json.load(open(sys.argv[1]))["submissions"]

    draws_all, draws_today, norms = [], [], []
    bar, bar_row = 0.0, None
    for r in rows:
        m = r.get("officialMetrics") or {}
        dc = decompose(m)
        if dc is None:
            continue
        norm, draw = dc
        draws_all.append(draw)
        norms.append((norm, r))
        if str(r.get("createdAt", "")).startswith("2026-08-11"):
            draws_today.append(draw)
        if r.get("promotionStatus") == "promoted" and \
                isinstance(r.get("officialScore"), (int, float)) and \
                r["officialScore"] > bar:
            bar, bar_row = r["officialScore"], r
    draws_all.sort()
    draws_today.sort()
    norms.sort(key=lambda x: -x[0])

    print(f"decomposable rows n={len(draws_all)} (today {len(draws_today)})")
    print(f"standing bar = {bar:.11f} "
          f"({str(bar_row.get('submissionCommitSha'))[:12]}, "
          f"{bar_row.get('solverUsername')}, promoted "
          f"{bar_row.get('promotionFinishedAt')})")

    print("\n=== baseline-draw distribution (the lottery) ===")
    print(f"  all-record: median={st.median(draws_all):.6f} "
          f"mean={st.mean(draws_all):.6f} sd={st.pstdev(draws_all):.6f} "
          f"({100*st.pstdev(draws_all)/st.mean(draws_all):.3f}% of mean)")
    for q in (0.05, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99):
        print(f"    p{int(q*100):02d} = {pct(draws_all, q):.6f}")
    print(f"    max = {draws_all[-1]:.6f}")
    if draws_today:
        print(f"  today only: n={len(draws_today)} "
              f"median={st.median(draws_today):.6f} "
              f"sd={st.pstdev(draws_today):.6f} max={max(draws_today):.6f}")

    print("\n=== best normalized executables on the whole record ===")
    for norm, r in norms[:10]:
        print(f"  norm={norm:.6f} pub={r['officialScore']:.8f} "
              f"draw={r['officialScore']/norm:.6f} "
              f"{str(r.get('submissionCommitSha'))[:12]} "
              f"{r.get('solverUsername'):>16} {r.get('status')}")

    print("\n=== P(beat the standing bar) per independent draw ===")
    interesting = {}
    for norm, r in norms:
        sha = str(r.get("submissionCommitSha"))[:8]
        u = r.get("solverUsername")
        key = None
        if r.get("promotionStatus") == "promoted" and r["officialScore"] == bar:
            key = f"CROWN {sha}"
        elif u == "morganmcg1":
            key = f"ours {sha} ({r['createdAt'][5:16]})"
        if key and key not in interesting:
            interesting[key] = (norm, r)
    ours = sorted(
        ((k, v) for k, v in interesting.items() if k.startswith("ours")),
        key=lambda kv: -kv[1][0])[:6]
    crown = [(k, v) for k, v in interesting.items() if k.startswith("CROWN")]
    for k, (norm, r) in crown + ours:
        need = bar / norm
        p_all = sum(1 for d in draws_all if d >= need) / len(draws_all)
        p_today = (sum(1 for d in draws_today if d >= need) / len(draws_today)
                   if draws_today else float("nan"))
        ex = f"{1/p_all:.1f}" if p_all > 0 else "inf"
        print(f"  {k:34s} norm={norm:.6f} need_draw>={need:.6f} "
              f"P_all={p_all*100:6.2f}%  P_today={p_today*100:6.2f}%  "
              f"E[draws to win]={ex}")

    print("\n=== how much normalized gain would make the bar a coin flip? ===")
    med = st.median(draws_all)
    p50_norm = bar / med
    best_ours = max(n for n, r in norms if r.get("solverUsername") == "morganmcg1")
    print(f"  median draw = {med:.6f} => need norm >= {p50_norm:.6f} for P=50%")
    print(f"  our best normalized executable = {best_ours:.6f}")
    print(f"  shortfall = {100*(p50_norm/best_ours - 1):.3f}% of normalized score")
    return 0


if __name__ == "__main__":
    sys.exit(main())
