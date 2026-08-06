#!/usr/bin/env python3
"""Quantify how much of `officialScore` is the candidate and how much is the
baseline draw it happened to be paired against.

`officialScore = (base_d/cand_d)^0.75 * (base_p/cand_p)^0.25`, so a candidate's
published score inherits the full noise of that session's baseline measurement.
This script holds one candidate fixed and re-scores it against the empirical
distribution of baselines other receipts actually drew.

usage: frieren_pr35_baseline_drift.py <feed.json> <candidate-id-prefix> [target-score]
"""
import json
import statistics as st
import sys

BASE_D = 0.013890
BASE_P = 0.0003845


def coerce(m):
    if isinstance(m, str):
        try:
            return json.loads(m)
        except Exception:
            return {}
    return m or {}


def pct(sorted_vals, q):
    if not sorted_vals:
        return float("nan")
    i = min(len(sorted_vals) - 1, max(0, int(round(q * (len(sorted_vals) - 1)))))
    return sorted_vals[i]


def main():
    feed = json.load(open(sys.argv[1]))
    cid = sys.argv[2]
    target = float(sys.argv[3]) if len(sys.argv) > 3 else None
    if isinstance(feed, dict):
        for k in ("submissions", "data", "items", "results"):
            if k in feed:
                feed = feed[k]
                break

    bd, bp, mine = [], [], None
    for s in feed:
        m = coerce(s.get("officialMetrics"))
        d, p = m.get("decode_seconds_per_token"), m.get("prefill_seconds_per_token")
        if not d or not p:
            continue
        gates = (
            m.get("passed_correctness")
            and m.get("passed_prefill_speedup_floor")
            and m.get("passed_decode_speedup_floor")
        )
        if not gates:
            continue
        b_d = m.get("baseline_decode_seconds_per_token")
        b_p = m.get("baseline_prefill_seconds_per_token")
        if b_d:
            bd.append(b_d)
        if b_p:
            bp.append(b_p)
        if (s.get("id") or "").startswith(cid):
            mine = (d, p, b_d, b_p, s.get("officialScore"))

    if mine is None:
        raise SystemExit("candidate %s not found among gate-passing receipts" % cid)

    cand_d, cand_p, my_bd, my_bp, my_off = mine
    bd.sort()
    bp.sort()

    print("gate-passing baselines sampled: decode n=%d prefill n=%d" % (len(bd), len(bp)))
    print()
    print("baseline_decode_seconds_per_token distribution")
    print("  min %.9f  p10 %.9f  median %.9f  p90 %.9f  max %.9f"
          % (bd[0], pct(bd, .10), st.median(bd), pct(bd, .90), bd[-1]))
    print("  spread max/min = %+.3f %%   stdev/mean = %.3f %%"
          % ((bd[-1] / bd[0] - 1) * 100, st.pstdev(bd) / st.mean(bd) * 100))
    print()
    print("this candidate")
    print("  cand_decode  %.9f   cand_prefill %.9f" % (cand_d, cand_p))
    print("  drew baseline_decode %.9f  = %+.3f %% vs median"
          % (my_bd, (my_bd / st.median(bd) - 1) * 100))
    print("  published officialScore %.6f" % my_off)
    print()

    print("same candidate re-scored against other receipts' baseline draws")
    hdr = "  %-10s %-15s %-12s %s"
    print(hdr % ("draw", "baseline_decode", "paired score", "beats target" if target else ""))
    for label, q in (("min", 0.0), ("p10", .10), ("median", .50), ("p90", .90), ("max", 1.0)):
        b_d = bd[0] if q == 0.0 else (bd[-1] if q == 1.0 else pct(bd, q))
        sc = (b_d / cand_d) ** 0.75 * (my_bp / cand_p) ** 0.25
        verdict = ("yes" if target and sc > target else "no") if target else ""
        print(hdr % (label, "%.9f" % b_d, "%.6f" % sc, verdict))

    if target:
        wins = 0
        for b_d in bd:
            sc = (b_d / cand_d) ** 0.75 * (my_bp / cand_p) ** 0.25
            if sc > target:
                wins += 1
        print()
        print("against target officialScore %.6f:" % target)
        print("  this candidate would out-score it under %d of %d observed baseline draws (%.1f %%)"
              % (wins, len(bd), 100.0 * wins / len(bd)))
        print("  => promotion of THIS candidate is decided mostly by the baseline draw,")
        print("     not by any further candidate-side change.")


if __name__ == "__main__":
    main()
