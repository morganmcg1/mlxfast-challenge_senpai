#!/usr/bin/env python3
"""What does status='accepted' actually mean, and what is the real objective?

Three candidate semantics for acceptance/promotion:
  (a) score beat the solver's own running best  (personal record)
  (b) score beat the global running best         (leaderboard record)
  (c) score beat a fixed threshold
Only one of these makes 'submit many replicates of the best tree' rational.
"""
import json
import math
import os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, "artifacts", "advisor-r103")
CORPUS = json.load(open(os.path.join(ART, "receipt-corpus-frozen.json")))

rows = [r for r in CORPUS if r.get("score")]
rows.sort(key=lambda r: r["ts"])
print(f"receipts with a score: {len(rows)}  "
      f"span {rows[0]['ts']} .. {rows[-1]['ts']}")

st = defaultdict(int)
for r in rows:
    st[r.get("status")] += 1
print("status counts:", dict(st))

own_best = defaultdict(lambda: -1e9)
glob_best = -1e9
tab = {"acc_beat_own": 0, "acc_not_beat_own": 0,
       "rej_beat_own": 0, "rej_not_beat_own": 0,
       "acc_beat_glob": 0, "acc_not_beat_glob": 0,
       "rej_beat_glob": 0, "rej_not_beat_glob": 0}
acc_scores, rej_scores = [], []
for r in rows:
    s, sv, stt = r["score"], r["solver"], r.get("status")
    bo, bg = own_best[sv], glob_best
    if stt == "accepted":
        acc_scores.append(s)
        tab["acc_beat_own" if s > bo else "acc_not_beat_own"] += 1
        tab["acc_beat_glob" if s > bg else "acc_not_beat_glob"] += 1
    elif stt == "rejected":
        rej_scores.append(s)
        tab["rej_beat_own" if s > bo else "rej_not_beat_own"] += 1
        tab["rej_beat_glob" if s > bg else "rej_not_beat_glob"] += 1
    own_best[sv] = max(bo, s)
    glob_best = max(bg, s)

print("\n  hypothesis (a) accepted <=> beat OWN previous best:")
print(f"    accepted & beat own      = {tab['acc_beat_own']}")
print(f"    accepted & did NOT       = {tab['acc_not_beat_own']}")
print(f"    rejected & beat own      = {tab['rej_beat_own']}   <- falsifiers")
print(f"    rejected & did NOT       = {tab['rej_not_beat_own']}")
print("\n  hypothesis (b) accepted <=> beat GLOBAL running best:")
print(f"    accepted & beat global   = {tab['acc_beat_glob']}")
print(f"    accepted & did NOT       = {tab['acc_not_beat_glob']}")
print(f"    rejected & beat global   = {tab['rej_beat_glob']}   <- falsifiers")
print(f"    rejected & did NOT       = {tab['rej_not_beat_glob']}")
print("\n  hypothesis (c) fixed threshold:")
if acc_scores and rej_scores:
    print(f"    min accepted score = {min(acc_scores):.6f}   "
          f"max accepted = {max(acc_scores):.6f}")
    print(f"    min rejected score = {min(rej_scores):.6f}   "
          f"max rejected = {max(rej_scores):.6f}")
    overlap = sum(1 for s in rej_scores if s > min(acc_scores))
    print(f"    rejected receipts above the min accepted score = {overlap}"
          f"  (overlap => no fixed threshold)")

# per-solver accepted counts vs their receipt counts
cnt = defaultdict(lambda: [0, 0, -1e9])
for r in rows:
    c = cnt[r["solver"]]
    c[0] += 1
    if r.get("status") == "accepted":
        c[1] += 1
    c[2] = max(c[2], r["score"])
print("\n  solver           receipts  accepted   best score")
for sv, c in sorted(cnt.items(), key=lambda kv: -kv[1][1])[:14]:
    print(f"  {sv:16s} {c[0]:7d}  {c[1]:8d}   {c[2]:.6f}")

# our own trajectory of personal bests
print("\n  morganmcg1 personal-best ladder (score):")
b = -1e9
for r in rows:
    if r["solver"] != "morganmcg1":
        continue
    if r["score"] > b:
        b = r["score"]
        print(f"    {r['ts']}  score={r['score']:.6f}  cs={r['cs']:.6f}  "
              f"L={r['L']:.6f}  status={r.get('status')}")

print("\n  global-best ladder (score):")
g = -1e9
for r in rows:
    if r["score"] > g:
        g = r["score"]
        print(f"    {r['ts']}  score={r['score']:.6f}  cs={r['cs']:.6f}  "
              f"L={r['L']:.6f}  {r['solver']:16s} status={r.get('status')}")
