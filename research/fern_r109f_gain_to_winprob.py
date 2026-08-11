#!/usr/bin/env python3
"""fern r109-f: convert a normalized-score gain into P(beat the standing bar).

Because published = normalized * draw and the draw distribution is empirically
known from 1280 receipts, an engineering gain of g% shifts the required draw
quantile, not the score directly. This is the only defensible way to price a
candidate hunk against the remaining official shots.

Usage: research/fern_r109f_gain_to_winprob.py <submissions.json> [n_shots...]
"""
from __future__ import annotations

import json
import sys

REF_D = 0.01385621216015625
REF_P = 0.00036751938916015626


def main() -> int:
    rows = json.load(open(sys.argv[1]))["submissions"]
    shots = [int(x) for x in sys.argv[2:]] or [1, 2, 3, 5]

    draws = []
    bar = 0.0
    ours_norm = []
    for r in rows:
        m = r.get("officialMetrics") or {}
        d, p = m.get("decode_seconds_per_token"), m.get("prefill_seconds_per_token")
        bd = m.get("baseline_decode_seconds_per_token")
        bp = m.get("baseline_prefill_seconds_per_token")
        if not (d and p and bd and bp):
            continue
        draws.append((bd / REF_D) ** 0.75 * (bp / REF_P) ** 0.25)
        norm = (REF_D / d) ** 0.75 * (REF_P / p) ** 0.25
        if r.get("solverUsername") == "morganmcg1":
            ours_norm.append((norm, r))
        if r.get("promotionStatus") == "promoted" and \
                isinstance(r.get("officialScore"), (int, float)):
            bar = max(bar, r["officialScore"])
    draws.sort()
    ours_norm.sort(key=lambda x: -x[0])
    n = len(draws)

    def prob(need: float) -> float:
        return sum(1 for x in draws if x >= need) / n

    best_norm, best_row = ours_norm[0]
    today = [x for x in ours_norm if str(x[1].get("createdAt", "")).startswith("2026-08-11")]
    today_norm, today_row = today[0] if today else (best_norm, best_row)

    print(f"draw sample n={n}   standing bar={bar:.11f}")
    print(f"our best-ever normalized executable  = {best_norm:.6f} "
          f"({str(best_row.get('submissionCommitSha'))[:12]}, {best_row['createdAt'][:16]})")
    print(f"our best normalized executable TODAY = {today_norm:.6f} "
          f"({str(today_row.get('submissionCommitSha'))[:12]}, {today_row['createdAt'][:16]})")

    header = f"{'gain%':>7} {'norm':>10} {'need_draw':>10} {'P/shot':>8}" + \
        "".join(f" {'P(' + str(s) + ' shots)':>12}" for s in shots)
    for label, base in (("best-ever", best_norm), ("today", today_norm)):
        print(f"\n--- starting from the {label} executable (norm={base:.6f}) ---")
        print(header)
        for g in (0.0, 0.10, 0.20, 0.38, 0.50, 0.75, 1.00, 1.259, 1.50, 2.00):
            nz = base * (1 + g / 100.0)
            need = bar / nz
            p = prob(need)
            row = f"{g:7.2f} {nz:10.6f} {need:10.6f} {p*100:7.2f}%"
            for s in shots:
                row += f" {(1-(1-p)**s)*100:11.2f}%"
            print(row)
    return 0


if __name__ == "__main__":
    sys.exit(main())
