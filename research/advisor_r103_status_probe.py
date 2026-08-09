#!/usr/bin/env python3
"""Advisor r103: what does submission `status` mean, and why are ALL of our
best receipts marked `rejected`?

The provenance probe turned up that every one of the six receipts round 103 is
built on carries `status = "rejected"` while still having complete
officialMetrics (passed_correctness true, max_abs_diff 0). Either `rejected` is
benign bookkeeping ("did not improve on the leaderboard best") or it means our
measurements are not counted at all. That distinction is worth the five minutes.

READ-ONLY. Never submits. Never prints the token.
"""

import collections
import json
import os
import pathlib
import sys
import urllib.parse
import urllib.request

BENCHMARK = "eigenlabs/mlxfast-challenge"
US = "morganmcg1"
LEADER = "a-github-name"
MB_D = 0.013855009542
MB_P = 0.000372473193

token = os.environ.get("MLXFAST_API_TOKEN")
base = os.environ.get("MLXFAST_API_BASE", "https://api.mlx.fast").rstrip("/")
cfg = pathlib.Path.home() / ".config/mlxfast/config.json"
if not token and cfg.exists():
    c = json.loads(cfg.read_text())
    base = c.get("apiBaseUrl", base).rstrip("/")
    token = c["token"]
if not token:
    sys.exit("no token")
SECRET = token


def get(path):
    req = urllib.request.Request(f"{base}{path}", headers={"Authorization": f"Bearer {SECRET}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def cs_of(d, p):
    return (MB_D / d) ** 0.75 * (MB_P / p) ** 0.25


bid = get(f"/api/benchmarks/{urllib.parse.quote(BENCHMARK, safe='')}")["benchmark"]["id"]
rows = get(f"/api/benchmarks/{bid}/submissions")["submissions"]

print("===== status distribution, whole corpus =====")
for k, v in collections.Counter(r.get("status") for r in rows).most_common():
    print(f"  {str(k):16s} {v:5d}")

print("\n===== status x has-officialScore =====")
tab = collections.Counter((r.get("status"), r.get("officialScore") is not None) for r in rows)
for (s, has), n in sorted(tab.items(), key=lambda x: -x[1]):
    print(f"  {str(s):16s} metrics={str(has):5s}  {n:5d}")

print("\n===== status x improved =====")
tab = collections.Counter((r.get("status"), r.get("improved")) for r in rows)
for (s, imp), n in sorted(tab.items(), key=lambda x: -x[1]):
    print(f"  {str(s):16s} improved={str(imp):5s}  {n:5d}")

print("\n===== rejectionReason: distinct prefixes among records WITH metrics =====")
c = collections.Counter()
for r in rows:
    if r.get("officialScore") is None:
        continue
    rr = r.get("rejectionReason")
    c[(rr or "<none>")[:110]] += 1
for k, v in c.most_common(15):
    print(f"  {v:5d}  {k}")

print("\n===== our own receipts WITH metrics: status / improved / reason =====")
ours = [r for r in rows if r.get("solverUsername") == US and r.get("officialScore") is not None]
print(f"  n = {len(ours)}")
for k, v in collections.Counter((r.get("status"), r.get("improved")) for r in ours).most_common():
    print(f"  status={str(k[0]):12s} improved={str(k[1]):6s}  {v}")
for k, v in collections.Counter((r.get("rejectionReason") or "<none>")[:110] for r in ours).most_common(8):
    print(f"  {v:5d}  {k}")

print("\n===== the leader's RECORD receipt, for comparison =====")
best = None
for r in rows:
    if r.get("officialScore") is None:
        continue
    if best is None or r["officialScore"] > best["officialScore"]:
        best = r
print(f"  solver={best.get('solverUsername')}  score={best.get('officialScore')}")
print(f"  status={best.get('status')}  improved={best.get('improved')}")
print(f"  promotionStatus={best.get('promotionStatus')}  promotedSourceRef={best.get('promotedSourceRef')}")
print(f"  rejectionReason={(best.get('rejectionReason') or '<none>')[:200]}")

print("\n===== promotionStatus distribution =====")
for k, v in collections.Counter(r.get("promotionStatus") for r in rows).most_common():
    print(f"  {str(k):16s} {v:5d}")
print("\n  promoted records by solver:")
for k, v in collections.Counter(r.get("solverUsername") for r in rows
                                if r.get("promotionStatus")).most_common(12):
    print(f"    {str(k):22s} {v:4d}")

print("\n===== do WE have any promoted submissions? =====")
mine = [r for r in rows if r.get("solverUsername") == US and r.get("promotionStatus")]
print(f"  n = {len(mine)}")
for r in sorted(mine, key=lambda x: x.get("promotionFinishedAt") or "")[-8:]:
    m = r.get("officialMetrics") or {}
    d, p = m.get("decode_seconds_per_token"), m.get("prefill_seconds_per_token")
    print(f"    {r['id'][:8]} {(r.get('promotionFinishedAt') or '')[:19]} "
          f"{r.get('promotionStatus'):10s} score={r.get('officialScore')} "
          f"cs={cs_of(d,p) if d and p else None} ref={r.get('promotedSourceRef')}")
