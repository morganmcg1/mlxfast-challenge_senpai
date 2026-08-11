#!/usr/bin/env python3
"""READ-ONLY: split terminal submission outcomes into scored draws vs wasted shots.

Motivation (ledger 10): my per-draw P(crown) = 1.48 % was estimated from the
score-to-score variance of *scored* draws, so it is conditional on the shot
producing an official score at all.  The public collection shows two very
different terminal classes:

  status=rejected  -> 100 % carry an officialScore; rejectionReason is literally
                      "score did not improve current best".  A real draw.
  status=failed    ->   0 % carry an officialScore.  A wasted shot.

So P(crown | fired) = P(scored) x P(beat bar | scored), and P(scored) must be
measured, not assumed to be 1.  This script measures it globally and for our
own account over several recency windows, because early-campaign breakage is
not representative of the endgame.

Usage: python3 research/fern_r109f_shot_yield.py research/fern-r109f-queue-*.json
"""
import datetime
import json
import sys

SCORED = ("rejected", "accepted")
NOW = datetime.datetime(2026, 8, 11, 13, 3, tzinfo=datetime.timezone.utc)
OURS = "morganmcg1"
PER_DRAW = 0.0148  # ledger 3: needed multiplier 1.014441, draw sd 0.538 %, z=2.344


def ts(s):
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))


def yield_rate(sub):
    f = sum(1 for r in sub if str(r.get("status", "")).lower() == "failed")
    s = sum(1 for r in sub if str(r.get("status", "")).lower() in SCORED)
    return s, f


def report(rows, label, who=None):
    print(f"\n=== {label} ===")
    print(f"{'window':>10}  {'n':>5}  {'scored':>6}  {'failed':>6}  {'P(scored)':>9}")
    for hours, lab in ((10 ** 5, "all"), (48, "48h"), (24, "24h"),
                       (12, "12h"), (6, "6h"), (3, "3h")):
        cut = NOW - datetime.timedelta(hours=hours)
        sub = [r for r in rows
               if (who is None or r.get("solverUsername") == who)
               and ts(r["createdAt"]) >= cut
               and str(r.get("status", "")).lower() in ("failed",) + SCORED]
        s, f = yield_rate(sub)
        n = s + f
        if n:
            print(f"{lab:>10}  {n:5d}  {s:6d}  {f:6d}  {s/n:8.1%}")


def main(paths):
    seen, rows = set(), []
    for p in paths:
        doc = json.load(open(p))
        for r in doc.get("submissions", doc):
            i = r.get("id")
            if i not in seen:
                seen.add(i)
                rows.append(r)
    print(f"unique rows: {len(rows)}")
    report(rows, "GLOBAL: does a fired shot produce a score?")
    report(rows, "OUR ACCOUNT: does a fired shot produce a score?", who=OURS)

    print("\n=== P(crown) per FIRED SHOT, not per scored draw ===")
    print(f"per-scored-draw P(beat bar) = {PER_DRAW:.2%}")
    print(f"{'P(scored)':>10}  {'P/shot':>8}   " +
          "  ".join(f"{k} shots" for k in (2, 3, 4, 6, 9)))
    for ps in (1.00, 0.80, 0.69, 0.60):
        per = PER_DRAW * ps
        cum = "  ".join(f"{1-(1-per)**k:7.2%}" for k in (2, 3, 4, 6, 9))
        print(f"{ps:9.0%}  {per:7.2%}   {cum}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["research/fern-r109f-queue-1303Z.json"]))
