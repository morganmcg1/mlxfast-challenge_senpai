#!/usr/bin/env python3
"""Find which baseline axis actually decides promotion, by re-scoring one fixed
candidate against the JOINT empirical distribution of (baseline_decode,
baseline_prefill) pairs that official sessions actually drew.

An earlier version of this analysis varied only baseline_decode and concluded no
draw could promote the candidate. That was wrong: baseline_prefill carries far
more spread, so the pair must be resampled together.

usage: frieren_pr35_baseline_modes.py <feed.json> <candidate-id-prefix> [target-score]
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


def pct(v, q):
    s = sorted(v)
    i = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return s[i]


def main():
    feed = json.load(open(sys.argv[1]))
    cid = sys.argv[2]
    target = float(sys.argv[3]) if len(sys.argv) > 3 else None
    if isinstance(feed, dict):
        for k in ("submissions", "data", "items", "results"):
            if k in feed:
                feed = feed[k]
                break

    pairs, mine = [], None
    for s in feed:
        m = coerce(s.get("officialMetrics"))
        d, p = m.get("decode_seconds_per_token"), m.get("prefill_seconds_per_token")
        if not d or not p:
            continue
        if not (
            m.get("passed_correctness")
            and m.get("passed_prefill_speedup_floor")
            and m.get("passed_decode_speedup_floor")
        ):
            continue
        b_d = m.get("baseline_decode_seconds_per_token")
        b_p = m.get("baseline_prefill_seconds_per_token")
        if b_d and b_p:
            pairs.append((b_d, b_p))
        if (s.get("id") or "").startswith(cid):
            mine = (d, p, b_d, b_p, s.get("officialScore"))

    if mine is None:
        raise SystemExit("candidate %s not found" % cid)
    cand_d, cand_p, my_bd, my_bp, my_off = mine

    bps = sorted(p for _, p in pairs)
    print("baseline_prefill_seconds_per_token distribution (n=%d)" % len(bps))
    print("  min %.9f  p10 %.9f  median %.9f  p90 %.9f  max %.9f"
          % (bps[0], pct(bps, .10), st.median(bps), pct(bps, .90), bps[-1]))
    print("  spread max/min = %+.3f %%   stdev/mean = %.3f %%"
          % ((bps[-1] / bps[0] - 1) * 100, st.pstdev(bps) / st.mean(bps) * 100))

    # split the bimodal prefill baseline at its widest interior gap
    gaps = [(bps[i + 1] - bps[i], i) for i in range(len(bps) - 1)]
    gap, gi = max(gaps)
    cut = (bps[gi] + bps[gi + 1]) / 2
    lo = [x for x in bps if x <= cut]
    hi = [x for x in bps if x > cut]
    print("  widest interior gap %.9f at cut %.9f  => fast mode n=%d (mean %.9f), slow mode n=%d (mean %.9f)"
          % (gap, cut, len(lo), st.mean(lo), len(hi), st.mean(hi)))
    print("  mode separation = %+.3f %%" % ((st.mean(hi) / st.mean(lo) - 1) * 100))
    print()

    print("this candidate: cand_d %.9f cand_p %.9f" % (cand_d, cand_p))
    print("  drew baseline (d %.9f, p %.9f) -> officialScore %.6f"
          % (my_bd, my_bp, my_off))
    print("  its baseline_prefill sits in the %s mode" % ("SLOW" if my_bp > cut else "FAST"))
    print()

    print("same candidate re-scored against each observed baseline PAIR:")
    scores = [((b_d / cand_d) ** 0.75 * (b_p / cand_p) ** 0.25) for b_d, b_p in pairs]
    ss = sorted(scores)
    print("  min %.6f  p10 %.6f  median %.6f  p90 %.6f  max %.6f"
          % (ss[0], pct(ss, .10), st.median(ss), pct(ss, .90), ss[-1]))

    lo_s = [s for s, (bd_, bp_) in zip(scores, pairs) if bp_ <= cut]
    hi_s = [s for s, (bd_, bp_) in zip(scores, pairs) if bp_ > cut]
    if lo_s:
        print("  conditional on FAST baseline_prefill mode: mean %.6f (n=%d)" % (st.mean(lo_s), len(lo_s)))
    if hi_s:
        print("  conditional on SLOW baseline_prefill mode: mean %.6f (n=%d)" % (st.mean(hi_s), len(hi_s)))

    if target:
        wins = sum(1 for s in scores if s > target)
        print()
        print("against target officialScore %.6f:" % target)
        print("  beats it under %d of %d observed baseline pairs (%.1f %%)"
              % (wins, len(scores), 100.0 * wins / len(scores)))
        if lo_s:
            w = sum(1 for s in lo_s if s > target)
            print("    within FAST prefill mode: %d/%d (%.1f %%)" % (w, len(lo_s), 100.0 * w / len(lo_s)))
        if hi_s:
            w = sum(1 for s in hi_s if s > target)
            print("    within SLOW prefill mode: %d/%d (%.1f %%)" % (w, len(hi_s), 100.0 * w / len(hi_s)))


if __name__ == "__main__":
    main()
